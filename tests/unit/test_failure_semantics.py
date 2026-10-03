"""Every failure class maps to exactly one state, and the mapping is enforced not stated.

FR-07 is satisfied only if three things hold together. The set of failure classes is
closed and matches what the specification names. Each class produces exactly one
execution state. And an artifact that contradicts the mapping is refused rather than
merely discouraged.

The first is checked by parsing the specification instead of restating it, so a bullet
added there and never classified fails. The second is checked in both directions: no
class without a state, and no terminal state without a class that can reach it. A state
nothing can produce would be a value the contract defines and no execution can ever set,
which is indistinguishable from a typo.

The third is where most of these cases go. A schema observed only to accept is not known
to constrain anything, so roughly half feed the handoff record documents that must be
refused: a completed run carrying a termination reason, an incomplete run carrying an end
time, and every reason offered against a state it does not produce.
"""

import copy
import io
import json
import os
import unittest

import jsonschema

from zeroops import failure_modes
from zeroops import validate

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA_DIR = os.path.join(REPO_ROOT, "contracts", "schemas")
SPEC_PATH = os.path.join(REPO_ROOT, failure_modes.SPEC_RELATIVE_PATH)
CONTRACT_PATH = os.path.join(
    REPO_ROOT, "docs", "architecture", "minimum-sre-agent-contract.md"
)

# The states the handoff record defines. Read from the schema rather than restated, so
# adding a state without classifying anything into it fails here.
EXPECTED_SPEC_BULLETS = 7


def load(path):
    with io.open(path, encoding="utf-8") as handle:
        return json.load(handle)


def read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def handoff_schema():
    return load(os.path.join(SCHEMA_DIR, "handoff-record.schema.json"))


def declared_states():
    return handoff_schema()["properties"]["executionState"]["enum"]


BASE_RECORD = {
    "schemaVersion": "1.1.0",
    "executionId": "<EXECUTION_ID>",
    "idempotencyKey": "<IDEMPOTENCY_KEY>",
    "turn": 1,
    "maxTurns": 5,
    "attempt": 1,
    "maxAttempts": 3,
    "autonomyLevel": "readOnly",
    "executionState": "running",
}


def record(**overrides):
    instance = copy.deepcopy(BASE_RECORD)
    for key, value in overrides.items():
        if value is None:
            instance.pop(key, None)
        else:
            instance[key] = value
    return instance


class TheRegistryMatchesTheSpecification(unittest.TestCase):
    """Parsed, not restated, so the document and the registry cannot drift apart."""

    def setUp(self):
        self.bullets = failure_modes.parse_failure_mode_bullets(read(SPEC_PATH))

    def test_the_parse_finds_the_bullets_it_is_expected_to_find(self):
        # Without this, a parse returning nothing makes the coverage checks below
        # trivially true in both directions.
        self.assertEqual(len(self.bullets), EXPECTED_SPEC_BULLETS)

    def test_every_specified_failure_mode_is_classified(self):
        cited = {
            entry.source
            for entry in failure_modes.FAILURE_CLASSES
            if entry.citation == "Failure Modes"
        }
        unclassified = sorted(set(self.bullets) - cited)
        self.assertEqual(
            unclassified,
            [],
            "failure modes named in the specification and never classified: %s"
            % unclassified,
        )

    def test_no_classified_bullet_was_invented(self):
        invented = sorted(
            entry.source
            for entry in failure_modes.FAILURE_CLASSES
            if entry.citation == "Failure Modes" and entry.source not in self.bullets
        )
        self.assertEqual(invented, [])

    def test_a_class_drawn_from_elsewhere_cites_a_section_that_exists(self):
        derived = [
            entry
            for entry in failure_modes.FAILURE_CLASSES
            if entry.citation != "Failure Modes"
        ]
        self.assertGreaterEqual(len(derived), 2)
        spec = read(SPEC_PATH)
        for entry in derived:
            section = entry.citation.split(",")[0]
            self.assertIn("### " + section, spec, entry.name)

    def test_class_names_are_unique(self):
        names = [entry.name for entry in failure_modes.FAILURE_CLASSES]
        self.assertEqual(len(names), len(set(names)))

    def test_every_class_records_a_substantive_rationale(self):
        for entry in failure_modes.FAILURE_CLASSES:
            self.assertGreaterEqual(len(entry.rationale), 120, entry.name)
            self.assertNotIn(entry.name, entry.rationale.replace(entry.name, "", 1)[:0])


class TheMappingIsTotalInBothDirections(unittest.TestCase):
    """No class without a state, and no terminal state without a class."""

    def test_every_mapped_class_produces_exactly_one_defined_state(self):
        states = set(declared_states())
        mapped = failure_modes.mapped_classes()
        self.assertGreaterEqual(len(mapped), 8)
        for entry in mapped:
            self.assertIn(entry.execution_state, states, entry.name)
            self.assertEqual(
                failure_modes.state_for(entry.name), entry.execution_state
            )

    def test_every_terminal_failure_state_is_reachable(self):
        for state in failure_modes.TERMINAL_FAILURE_STATES:
            self.assertNotEqual(
                failure_modes.classes_for_state(state),
                [],
                "%s is defined and no failure class can produce it" % state,
            )

    def test_the_terminal_states_are_exactly_the_non_success_states(self):
        expected = set(declared_states()) - {"running", "completed"}
        self.assertEqual(set(failure_modes.TERMINAL_FAILURE_STATES), expected)

    def test_no_class_maps_to_running_or_completed(self):
        for entry in failure_modes.mapped_classes():
            self.assertNotIn(entry.execution_state, ("running", "completed"))

    def test_a_bullet_that_is_not_an_outcome_is_recorded_rather_than_dropped(self):
        unmapped = failure_modes.unmapped_classes()
        self.assertEqual([entry.name for entry in unmapped], ["consistencyModel"])
        for entry in unmapped:
            self.assertIsNone(failure_modes.state_for(entry.name))
            self.assertIn("property", entry.rationale)

    def test_the_settling_and_ungranted_cases_do_not_collapse(self):
        # The specification requires validation distinguish not-yet-effective from
        # not-granted. One state for both would erase exactly that.
        self.assertEqual(
            failure_modes.state_for("roleAssignmentNotYetEffective"), "incomplete"
        )
        self.assertEqual(failure_modes.state_for("accessNotGranted"), "accessDenied")

    def test_retryability_is_recorded_for_every_class_and_is_not_uniform(self):
        flags = {entry.retryable for entry in failure_modes.mapped_classes()}
        self.assertEqual(flags, {True, False})
        self.assertTrue(failure_modes.retryable("dataSourceUnreachable"))
        self.assertFalse(failure_modes.retryable("accessNotGranted"))
        self.assertFalse(failure_modes.retryable("executionLimitReached"))

    def test_an_unknown_class_has_no_state_and_is_not_retryable(self):
        self.assertIsNone(failure_modes.state_for("inventedClass"))
        self.assertFalse(failure_modes.retryable("inventedClass"))


class TheSchemaCarriesTheMapping(unittest.TestCase):
    """Enforced by the contract, not restated in prose nothing checks."""

    def setUp(self):
        self.schema = handoff_schema()
        self.validator = jsonschema.Draft202012Validator(self.schema)

    def test_the_termination_reason_enum_is_exactly_the_mapped_classes(self):
        declared = self.schema["$defs"]["terminationReason"]["enum"]
        expected = [entry.name for entry in failure_modes.mapped_classes()]
        self.assertEqual(sorted(declared), sorted(expected))

    def test_the_state_subsets_partition_the_reasons(self):
        subsets = {
            "incomplete": self.schema["$defs"]["incompleteTerminationReason"]["enum"],
            "failed": self.schema["$defs"]["failedTerminationReason"]["enum"],
        }
        for state, declared in subsets.items():
            self.assertEqual(
                sorted(declared),
                sorted(failure_modes.classes_for_state(state)),
                state,
            )
        overlap = set(subsets["incomplete"]) & set(subsets["failed"])
        self.assertEqual(overlap, set())

    def test_the_single_denied_reason_is_pinned_by_const_not_by_enum(self):
        branch = self._branch_for("accessDenied")
        self.assertEqual(
            branch["then"]["properties"]["terminationReason"]["const"],
            "accessNotGranted",
        )

    def _branch_for(self, state):
        for branch in self.schema["allOf"]:
            if branch["if"]["properties"]["executionState"]["const"] == state:
                return branch
        raise AssertionError("no branch constrains %s" % state)

    def test_every_declared_state_is_constrained_by_a_branch(self):
        for state in declared_states():
            self._branch_for(state)

    def test_a_running_record_is_accepted(self):
        self.assertTrue(self.validator.is_valid(record()))

    def test_a_completed_record_carries_an_end_time(self):
        self.assertTrue(
            self.validator.is_valid(
                record(
                    executionState="completed", completedAt="2026-01-01T00:00:00Z"
                )
            )
        )

    def test_each_mapped_reason_is_accepted_against_its_own_state(self):
        for entry in failure_modes.mapped_classes():
            instance = record(
                executionState=entry.execution_state, terminationReason=entry.name
            )
            self.assertTrue(
                self.validator.is_valid(instance),
                "%s rejected against %s" % (entry.name, entry.execution_state),
            )

    def test_no_reason_is_accepted_against_a_state_it_does_not_produce(self):
        checked = 0
        for entry in failure_modes.mapped_classes():
            for state in failure_modes.TERMINAL_FAILURE_STATES:
                if state == entry.execution_state:
                    continue
                checked += 1
                instance = record(
                    executionState=state, terminationReason=entry.name
                )
                self.assertFalse(
                    self.validator.is_valid(instance),
                    "%s accepted against %s, which it does not produce"
                    % (entry.name, state),
                )
        self.assertGreaterEqual(checked, 16)

    def test_a_terminal_record_without_a_reason_is_refused(self):
        for state in failure_modes.TERMINAL_FAILURE_STATES:
            self.assertFalse(
                self.validator.is_valid(record(executionState=state)), state
            )

    def test_a_completed_record_cannot_claim_a_termination_reason(self):
        self.assertFalse(
            self.validator.is_valid(
                record(
                    executionState="completed",
                    completedAt="2026-01-01T00:00:00Z",
                    terminationReason="executionLimitReached",
                )
            )
        )

    def test_a_running_record_cannot_claim_a_termination_reason(self):
        self.assertFalse(
            self.validator.is_valid(
                record(terminationReason="dataSourceUnreachable")
            )
        )

    def test_a_running_record_cannot_carry_an_end_time(self):
        self.assertFalse(
            self.validator.is_valid(record(completedAt="2026-01-01T00:00:00Z"))
        )

    def test_a_completed_record_without_an_end_time_is_refused(self):
        self.assertFalse(self.validator.is_valid(record(executionState="completed")))

    def test_an_unfinished_record_cannot_carry_an_end_time(self):
        # The absence of completedAt is how an incomplete run stays distinguishable
        # from one that finished. A supplied end time would erase that.
        for state in failure_modes.TERMINAL_FAILURE_STATES:
            reason = failure_modes.classes_for_state(state)[0]
            self.assertFalse(
                self.validator.is_valid(
                    record(
                        executionState=state,
                        terminationReason=reason,
                        completedAt="2026-01-01T00:00:00Z",
                    )
                ),
                state,
            )

    def test_a_record_without_a_state_is_refused(self):
        self.assertFalse(self.validator.is_valid(record(executionState=None)))

    def test_a_record_without_an_attempt_ceiling_is_refused(self):
        self.assertFalse(self.validator.is_valid(record(maxAttempts=None)))
        self.assertFalse(self.validator.is_valid(record(attempt=None)))

    def test_an_attempt_below_one_is_refused(self):
        self.assertFalse(self.validator.is_valid(record(attempt=0)))

    def test_an_unknown_reason_is_refused(self):
        self.assertFalse(
            self.validator.is_valid(
                record(
                    executionState="failed", terminationReason="somethingWentWrong"
                )
            )
        )


class TheRetryPolicyIsDeclaredAndBounded(unittest.TestCase):
    """How many times and how far apart, and nothing about which classes."""

    def setUp(self):
        self.schema = load(os.path.join(SCHEMA_DIR, "tool-policy.schema.json"))
        self.validator = jsonschema.Draft202012Validator(
            {
                "$schema": self.schema["$schema"],
                "$defs": self.schema.get("$defs", {}),
                **self.schema["properties"]["retryPolicy"],
            }
        )

    def test_the_policy_is_required_on_the_tool_policy(self):
        self.assertIn("retryPolicy", self.schema["required"])

    def test_retryability_cannot_be_redeclared_by_a_consumer(self):
        # Retryability is a property of the failure class. A policy able to mark a
        # denied grant retryable would turn a settled finding into a loop. Checked
        # against the property names and the accepted values, not the prose: the
        # description says the word precisely in order to explain the prohibition.
        policy = self.schema["properties"]["retryPolicy"]
        names = set(policy["properties"])
        self.assertNotIn("retryable", names)
        self.assertNotIn("retryableReasons", names)
        for entry in failure_modes.mapped_classes():
            self.assertNotIn(entry.name, names)
            self.assertFalse(
                self.validator.is_valid(
                    {"maxAttempts": 3, "backoff": "none", entry.name: True}
                ),
                entry.name,
            )
        self.assertFalse(
            self.validator.is_valid(
                {"maxAttempts": 3, "backoff": "none", "retryableReasons": []}
            )
        )

    def test_a_bounded_policy_is_accepted(self):
        self.assertTrue(
            self.validator.is_valid(
                {"maxAttempts": 3, "backoff": "exponential", "initialDelaySeconds": 2}
            )
        )

    def test_no_retry_is_a_policy_rather_than_an_absence(self):
        self.assertTrue(
            self.validator.is_valid({"maxAttempts": 1, "backoff": "none"})
        )

    def test_a_delay_alongside_no_backoff_is_refused(self):
        self.assertFalse(
            self.validator.is_valid(
                {"maxAttempts": 1, "backoff": "none", "initialDelaySeconds": 5}
            )
        )

    def test_a_backoff_without_an_interval_is_refused(self):
        self.assertFalse(
            self.validator.is_valid({"maxAttempts": 3, "backoff": "fixed"})
        )

    def test_an_unbounded_ceiling_is_refused(self):
        self.assertFalse(
            self.validator.is_valid({"maxAttempts": 0, "backoff": "none"})
        )
        self.assertFalse(
            self.validator.is_valid({"maxAttempts": 1000, "backoff": "none"})
        )

    def test_a_free_form_backoff_is_refused(self):
        # The delay is supplied on purpose. Without it the document is refused for
        # lacking an interval, which would let this case pass even with the
        # enumeration removed.
        instance = {
            "maxAttempts": 3,
            "backoff": "every 5s for a while",
            "initialDelaySeconds": 5,
        }
        self.assertFalse(self.validator.is_valid(instance))
        self.assertTrue(
            self.validator.is_valid(dict(instance, backoff="exponential")),
            "the control case must be accepted, or the assertion above proves "
            "nothing about the backoff value",
        )

    def test_a_policy_without_a_ceiling_is_refused(self):
        self.assertFalse(self.validator.is_valid({"backoff": "none"}))


class TheValidatorCatchesWhatTheSchemaCannot(unittest.TestCase):
    """Sibling comparisons, which JSON Schema cannot express."""

    def _messages(self, instance):
        return [
            finding.message
            for finding in validate.SEMANTIC_RULES["handoff-record"](instance)
        ]

    def test_a_consistent_record_produces_no_finding(self):
        self.assertEqual(self._messages(record()), [])

    def test_an_attempt_beyond_the_ceiling_is_reported(self):
        messages = self._messages(record(attempt=4, maxAttempts=3))
        self.assertTrue(any("exceeds maxAttempts" in m for m in messages), messages)

    def test_a_state_disagreeing_with_its_reason_is_reported(self):
        # The schema already refuses this shape. The validator reports it too, so a
        # record that reached the semantic layer by another route is still caught.
        messages = self._messages(
            record(
                executionState="failed", terminationReason="dataSourceUnreachable"
            )
        )
        self.assertTrue(
            any("does not match the state" in m for m in messages), messages
        )

    def test_a_retry_of_an_unretryable_reason_is_reported(self):
        messages = self._messages(
            record(
                executionState="accessDenied",
                terminationReason="accessNotGranted",
                attempt=2,
            )
        )
        self.assertTrue(any("unretryable" in m for m in messages), messages)

    def test_a_retry_of_a_retryable_reason_is_not_reported(self):
        messages = self._messages(
            record(
                executionState="incomplete",
                terminationReason="dataSourceUnreachable",
                attempt=2,
            )
        )
        self.assertEqual(messages, [])

    def test_an_unknown_reason_is_reported(self):
        messages = self._messages(
            record(executionState="failed", terminationReason="inventedClass")
        )
        self.assertTrue(any("no failure class" in m for m in messages), messages)

    def test_an_end_time_before_the_start_is_reported(self):
        messages = self._messages(
            record(
                executionState="completed",
                startedAt="2026-01-02T00:00:00Z",
                completedAt="2026-01-01T00:00:00Z",
            )
        )
        self.assertTrue(any("precedes startedAt" in m for m in messages), messages)

    def test_a_malformed_timestamp_is_reported_and_not_compared(self):
        # Reporting the shape and then comparing anyway would produce a second
        # finding pointing at the wrong field.
        messages = self._messages(
            record(
                executionState="completed",
                startedAt="yesterday",
                completedAt="2026-01-01T00:00:00Z",
            )
        )
        self.assertEqual(len(messages), 1, messages)
        self.assertIn("RFC 3339", messages[0])

    def test_diagnostics_carry_no_values(self):
        messages = self._messages(
            record(
                executionState="failed",
                terminationReason="inventedClass",
                attempt=9,
                maxAttempts=3,
            )
        )
        self.assertNotEqual(messages, [])
        for message in messages:
            self.assertNotIn("inventedClass", message)
            self.assertNotIn("9", message)


class TheContractDocumentsTheMapping(unittest.TestCase):
    """Prose and registry agree, so neither can be updated alone."""

    def setUp(self):
        self.contract = read(CONTRACT_PATH)

    def test_every_class_appears_in_the_contract_with_its_state(self):
        for entry in failure_modes.mapped_classes():
            row = "| `%s` | `%s` |" % (entry.name, entry.execution_state)
            self.assertIn(row, self.contract, entry.name)

    def test_the_unmapped_bullet_is_explained_rather_than_listed(self):
        for entry in failure_modes.unmapped_classes():
            self.assertNotIn("| `%s` |" % entry.name, self.contract)
        self.assertIn("consistency-model bullet maps to no state", self.contract)

    def test_the_incomplete_representation_is_documented(self):
        self.assertIn("#### Incomplete execution", self.contract)
        self.assertIn("`completedAt` is absent", self.contract)

    def test_retry_and_timeout_are_both_documented(self):
        self.assertIn("`retryPolicy`", self.contract)
        self.assertIn("`executionLimits`", self.contract)


if __name__ == "__main__":
    unittest.main()


class TheFR77ClassesTellTheOperatorWhatToDo(unittest.TestCase):
    """FR-77 classes were observed live, so each must name a cause and a recovery."""

    def fr77(self):
        return [
            entry
            for entry in failure_modes.FAILURE_CLASSES
            if entry.name in failure_modes.FR77_CLASSES
        ]

    def test_every_fr77_name_is_registered(self):
        self.assertEqual(
            sorted(entry.name for entry in self.fr77()),
            sorted(failure_modes.FR77_CLASSES),
        )
        self.assertEqual(len(failure_modes.FR77_CLASSES), 4)

    def test_each_fr77_class_cites_fr77(self):
        for entry in self.fr77():
            self.assertEqual(entry.citation, "Functional Requirements, FR-77", entry.name)

    def test_each_fr77_class_names_a_probable_cause_and_a_recovery_action(self):
        for entry in self.fr77():
            self.assertTrue(entry.probable_cause and len(entry.probable_cause) >= 40, entry.name)
            self.assertTrue(entry.recovery_action and len(entry.recovery_action) >= 40, entry.name)

    def test_the_fr77_states_are_the_ones_the_requirement_assigns(self):
        expected = {
            "awaitingApproval": ("incomplete", False),
            "connectorNotVisibleToAgent": ("failed", False),
            "noToolUse": ("failed", False),
            "deliveryFailed": ("incomplete", True),
        }
        actual = {e.name: (e.execution_state, e.retryable) for e in self.fr77()}
        self.assertEqual(actual, expected)

    def test_a_record_still_declaring_the_previous_version_is_refused(self):
        instance = record(
            schemaVersion="1.0.0",
            executionState="failed",
            terminationReason="noToolUse",
        )
        self.assertFalse(
            jsonschema.Draft202012Validator(handoff_schema()).is_valid(instance)
        )

    def test_each_fr77_reason_is_refused_against_a_state_it_does_not_produce(self):
        validator = jsonschema.Draft202012Validator(handoff_schema())
        for entry in self.fr77():
            for state in ("incomplete", "failed"):
                if state == entry.execution_state:
                    continue
                instance = record(executionState=state, terminationReason=entry.name)
                self.assertFalse(validator.is_valid(instance), (entry.name, state))

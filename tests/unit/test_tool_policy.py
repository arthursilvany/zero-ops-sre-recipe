"""The tool policy baseline and the one rule the schema cannot express.

Most of FR-51 and FR-52 is pinned by `tool-policy.schema.json` with `const`,
`minItems` and closed enumerations. Those properties are asserted here against
the *schema*, not against the instance: an assertion that the baseline says
`deny` would pass for any document the schema admits, which is every document
that gets this far. Asserting that the schema admits nothing else is the
statement that has content.

What the schema cannot express is an upper bound on a limit. That is what the
baseline adds, and it is tested against instances.
"""

import copy
import json
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")

if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from zeroops import core_paths, policy, validate  # noqa: E402

# The seven categories FR-52 enumerates, written out here rather than read
# from the schema. Deriving them from the thing under test would make the
# assertion true by construction.
FR_52_CATEGORIES = {
    "write",
    "destructiveOperation",
    "arbitraryExecution",
    "secretsAccess",
    "selfApproval",
    "externalPublication",
    "agentCreatedSchedule",
}

# The four limits FR-53 enumerates, likewise stated independently.
FR_53_LIMITS = {
    "maxToolCalls",
    "maxWallClockSeconds",
    "maxResultSetRows",
    "perQueryTimeoutSeconds",
}


def load(relative):
    with open(os.path.join(REPO_ROOT, relative.replace("/", os.sep)), "r", encoding="utf-8") as handle:
        return json.load(handle)


class TheBaselineExists(unittest.TestCase):
    def setUp(self):
        self.baseline = policy.load_baseline()

    def test_the_declaration_records_the_directory_as_present(self):
        """core/policy/ was `planned`. A directory that exists while the
        declaration calls it planned is the declaration describing a
        repository that is no longer there."""
        declaration = core_paths.load_declaration(REPO_ROOT)
        entries = {
            entry["path"]: entry["status"]
            for entry in declaration["categories"]["core"]
        }
        self.assertEqual("present", entries["core/policy/"])

    def test_the_baseline_validates_against_its_schema(self):
        _artifact, findings = validate.validate(policy.BASELINE_PATH)
        self.assertEqual([], [str(f) for f in findings])

    def test_the_baseline_denies_every_category_fr_52_names(self):
        declared = {rule["category"] for rule in self.baseline["denyRules"]}
        self.assertEqual(FR_52_CATEGORIES, declared)

    def test_every_denial_carries_a_justification(self):
        for rule in self.baseline["denyRules"]:
            with self.subTest(category=rule["category"]):
                self.assertGreater(len(rule["justification"]), 40)

    def test_the_baseline_declares_every_limit_fr_53_names(self):
        self.assertEqual(FR_53_LIMITS, set(self.baseline["executionLimits"]))

    def test_the_baseline_is_a_legal_policy_under_its_own_ceiling(self):
        """A ceiling its own author could not satisfy would be a number
        picked without reference to anything. The comparison is inclusive."""
        self.assertEqual([], policy.ceiling_findings(self.baseline, self.baseline))


class TheSchemaPinsTheEnforcementModel(unittest.TestCase):
    """Asserted against the schema, not the instance.

    `self.baseline["defaultDecision"] == "deny"` would pass for every document
    the schema admits, so it says nothing about whether anything else could
    arrive. What has content is that the schema admits nothing else, which is
    why no code re-checks these and why this file says so.
    """

    def setUp(self):
        self.schema = load("contracts/schemas/tool-policy.schema.json")

    def test_the_default_decision_is_pinned_to_deny(self):
        self.assertEqual("deny", self.schema["properties"]["defaultDecision"]["const"])

    def test_conflicts_are_pinned_to_deny_wins(self):
        self.assertEqual(
            "denyWins", self.schema["properties"]["conflictResolution"]["const"]
        )

    def test_evaluation_failure_is_pinned_to_deny(self):
        self.assertEqual(
            "deny", self.schema["properties"]["onEvaluationFailure"]["const"]
        )

    def test_all_seven_categories_are_forced_present(self):
        """minItems 7 with uniqueItems over a seven-member enumeration. Remove
        any one of the three and a policy can drop a category."""
        rules = self.schema["properties"]["denyRules"]
        self.assertEqual(7, rules["minItems"])
        self.assertTrue(rules["uniqueItems"])
        categories = self.schema["$defs"]["denyRule"]["properties"]["category"]["enum"]
        self.assertEqual(FR_52_CATEGORIES, set(categories))

    def test_all_four_limits_are_required(self):
        limits = self.schema["properties"]["executionLimits"]
        self.assertEqual(FR_53_LIMITS, set(limits["required"]))

    def test_the_allowed_capability_classes_are_read_shaped(self):
        """A closed enumeration is how a write-shaped class is refused
        structurally rather than filtered later."""
        classes = self.schema["$defs"]["capabilityClass"]["enum"]
        for name in classes:
            with self.subTest(name=name):
                self.assertTrue(
                    name.startswith("read") or name == "runCataloguedQuery", name
                )

    def test_the_schema_sets_no_upper_bound_on_any_limit(self):
        """The reason the baseline exists. If a maximum ever appears here,
        the ceiling belongs in the schema and this module is redundant."""
        limits = self.schema["properties"]["executionLimits"]["properties"]
        for name, subschema in limits.items():
            with self.subTest(name=name):
                self.assertNotIn("maximum", subschema)
                self.assertNotIn("exclusiveMaximum", subschema)


class ThePolicyCeilingIsEnforced(unittest.TestCase):
    def setUp(self):
        self.baseline = policy.load_baseline()

    def widened(self, section, key, amount=1):
        instance = copy.deepcopy(self.baseline)
        instance[section][key] = instance[section][key] + amount
        return instance

    def test_every_execution_limit_is_capped(self):
        for key, _unit in policy.CEILINGS:
            with self.subTest(key=key):
                findings = policy.ceiling_findings(
                    self.widened("executionLimits", key), self.baseline
                )
                self.assertEqual(1, len(findings), findings)
                self.assertEqual("/executionLimits/" + key, findings[0][0])

    def test_the_capped_limits_are_exactly_the_four_fr_53_names(self):
        self.assertEqual(FR_53_LIMITS, {key for key, _unit in policy.CEILINGS})

    def test_retry_attempts_are_capped(self):
        findings = policy.ceiling_findings(
            self.widened("retryPolicy", "maxAttempts"), self.baseline
        )
        self.assertEqual(1, len(findings), findings)
        self.assertEqual("/retryPolicy/maxAttempts", findings[0][0])

    def test_narrowing_a_limit_is_accepted(self):
        """The control case. A check that reported every policy would satisfy
        the assertions above."""
        instance = copy.deepcopy(self.baseline)
        for key, _unit in policy.CEILINGS:
            instance["executionLimits"][key] = 1
        instance["retryPolicy"]["maxAttempts"] = 1
        self.assertEqual([], policy.ceiling_findings(instance, self.baseline))

    def test_the_message_names_both_numbers_and_the_baseline(self):
        """A refusal that gave only the offending value would leave the reader
        to guess what was permitted, and the file to guess where."""
        findings = policy.ceiling_findings(
            self.widened("executionLimits", "maxToolCalls", 800), self.baseline
        )
        message = findings[0][1]
        self.assertIn("1000", message)
        self.assertIn("200", message)
        self.assertIn(policy.BASELINE_PATH, message)

    def test_a_missing_limit_is_left_to_the_schema(self):
        """Two findings on one fault sends a reader looking for two faults.
        The schema has already refused a document missing a required limit."""
        instance = copy.deepcopy(self.baseline)
        del instance["executionLimits"]["maxToolCalls"]
        self.assertEqual([], policy.ceiling_findings(instance, self.baseline))

    def test_a_non_integer_limit_is_left_to_the_schema(self):
        instance = copy.deepcopy(self.baseline)
        instance["executionLimits"]["maxToolCalls"] = "lots"
        self.assertEqual([], policy.ceiling_findings(instance, self.baseline))

    def test_a_non_object_instance_is_not_read(self):
        self.assertEqual([], policy.ceiling_findings([], self.baseline))


class TheValidatorReportsTheCeiling(unittest.TestCase):
    """Wired into `zeroops validate`, not into a gate of its own. A consumer
    editing their own policy learns about it where they are working."""

    def test_the_validator_has_a_rule_for_tool_policies(self):
        self.assertIn("tool-policy", validate.SEMANTIC_RULES)

    def test_a_widened_policy_is_refused_through_the_validator(self):
        instance = copy.deepcopy(policy.load_baseline())
        instance["executionLimits"]["maxToolCalls"] = 100000
        findings = validate.semantic_findings_for("tool-policy", instance)
        self.assertEqual(1, len(findings), findings)
        self.assertEqual("/executionLimits/maxToolCalls", findings[0].pointer)
        self.assertIn("100000", findings[0].message)

    def test_the_baseline_passes_through_the_validator(self):
        """The control case."""
        self.assertEqual(
            [], validate.semantic_findings_for("tool-policy", policy.load_baseline())
        )

    def test_every_shipped_example_policy_is_within_the_ceiling(self):
        for relative in (
            "examples/minimal/tool-policy.json",
            "examples/two-environments/tool-policy.json",
        ):
            with self.subTest(relative=relative):
                self.assertEqual(
                    [], validate.semantic_findings_for("tool-policy", load(relative))
                )

    def test_a_shipped_example_sits_at_the_ceiling(self):
        """Not decoration. A ceiling every shipped artifact clears by a wide
        margin is a ceiling nothing has ever pressed against, and a rule
        nothing exercises is a rule nobody notices breaking."""
        baseline = policy.load_baseline()["executionLimits"]
        widest = load("examples/two-environments/tool-policy.json")["executionLimits"]
        at_ceiling = [k for k in FR_53_LIMITS if widest[k] == baseline[k]]
        self.assertTrue(at_ceiling, "no shipped example reaches any ceiling")


class ThePageStatesTheEnforcementModel(unittest.TestCase):
    def setUp(self):
        with open(
            os.path.join(REPO_ROOT, "core", "policy", "README.md"),
            "r",
            encoding="utf-8",
        ) as handle:
            self.doc = handle.read()

    def test_the_page_says_this_layer_is_not_the_authority(self):
        """FR-51 and SEC-001. A page that let a reader take this policy for
        the guarantee would misdirect a reviewer to the wrong artifact."""
        self.assertIn("Azure Resource Manager", self.doc)
        self.assertIn("defence in depth", self.doc)

    def test_the_page_carries_the_declared_not_runtime_verified_status(self):
        self.assertIn("declared, not runtime-verified", self.doc)

    def test_the_page_carries_the_declared_not_framework_enforced_status(self):
        """FR-53. The limits are not enforced by anything the framework can
        observe, and the page must not imply otherwise."""
        self.assertIn("declared, not framework-enforced", self.doc)

    def test_the_page_points_at_the_document_that_owns_the_consolidated_status(self):
        self.assertIn("FR-74", self.doc)

    def test_the_page_and_the_baseline_agree_on_every_ceiling(self):
        """Two statements of the same number drift. The table is the one a
        reader sees, and the JSON is the one the validator uses."""
        baseline = policy.load_baseline()
        expected = dict(baseline["executionLimits"])
        expected["maxAttempts"] = baseline["retryPolicy"]["maxAttempts"]
        for name, value in expected.items():
            with self.subTest(name=name):
                self.assertRegex(
                    self.doc,
                    r"`[^`]*%s`\s*\|\s*%d\b" % (name, value),
                    "the page does not record %s as %d" % (name, value),
                )


if __name__ == "__main__":
    unittest.main()

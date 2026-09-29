"""CC-016, CC-017 and CC-020: the three things the agent must not do.

Each of the three is a Must NOT, and a Must NOT is the hardest kind of claim
to evidence. A capability that works can be demonstrated by using it. A
capability that is absent looks exactly like a capability nobody tried.

So each case here drives the real refusal path rather than reading the
configuration that is supposed to produce it:

CC-016, write denial. The broker's allow-list decides. The test issues write
    and destructive verbs and asserts the plan refuses, and separately asserts
    that the refusal does not depend on recognising the verb as a write, since
    the set of verbs nobody thought of is the interesting one.

CC-017, self-approval denial. A ledger recording an approval whose decider is
    the agent's own principal must be rejected. The comparison is between
    principal object identifiers: a rule written against display names is
    defeated by a rename rather than by an argument.

CC-020, no secret in an emitted artifact. Enforced by there being nowhere to
    put one. Every contract schema is closed and every credential-shaped
    property is a reference, so a secret has no valid position in any emitted
    document. The test plants one anyway and asserts the document is rejected.

What none of this establishes: the running agent's permissions. The read-only
guarantee is the RBAC grant Azure Resource Manager enforces (SEC-001). These
are the second layer, and a failure here is a failure of defence in depth
rather than of the first line.
"""

import json
import os
import shutil
import tempfile
import unittest

from zeroops import broker, schema_lint, validate


AGENT = "<AGENT_PRINCIPAL_OBJECT_ID>"
HUMAN = "<HUMAN_PRINCIPAL_OBJECT_ID>"
HASH = "b" * 64
PREVIOUS = "c" * 64
SECRET_PLACEHOLDER = "<SECRET_VALUE_PLACEHOLDER>"


def ledger(entries, agent=AGENT):
    return {
        "schemaVersion": "1.0.0",
        "name": "release-approvals",
        "agentPrincipalObjectId": agent,
        "entries": entries,
    }


def entry(sequence, decider, previous=None):
    out = {
        "sequence": sequence,
        "approvedArtifactHash": HASH,
        "decision": "approved",
        "deciderPrincipalObjectId": decider,
        "decidedAt": "2026-01-01T00:00:00Z",
    }
    if previous is not None:
        out["previousEntryHash"] = previous
    return out


class CC017TheAgentCannotApproveItsOwnProposal(unittest.TestCase):
    def messages(self, document):
        return [
            finding.render("approval-ledger.json")
            for finding in validate.semantic_findings_for("approval-ledger", document)
        ]

    def test_a_ledger_decided_by_a_third_party_is_accepted(self):
        """The control. Without it every assertion below is satisfied by a
        rule that rejects everything, which is not the rule under test."""
        self.assertEqual([], self.messages(ledger([entry(1, HUMAN)])))

    def test_an_approval_decided_by_the_agent_is_rejected(self):
        messages = self.messages(ledger([entry(1, AGENT)]))
        self.assertTrue(messages)
        self.assertTrue(
            any("approved its own proposal" in message for message in messages),
            messages,
        )

    def test_self_approval_is_caught_at_any_position_in_the_ledger(self):
        """A rule reading only the first entry would pass a ledger whose
        self-approval was appended after a legitimate one."""
        document = ledger(
            [entry(1, HUMAN), entry(2, AGENT, PREVIOUS), entry(3, HUMAN, PREVIOUS)]
        )
        messages = self.messages(document)
        self.assertTrue(any("/entries/1/" in message for message in messages), messages)

    def test_a_rejection_recorded_by_the_agent_is_also_refused(self):
        """Deciding is the prohibited act. An agent that can reject its own
        proposal can clear a queue without a human ever seeing it."""
        document = ledger([dict(entry(1, AGENT), decision="rejected")])
        self.assertTrue(self.messages(document))

    def test_the_comparison_is_on_identifiers_and_not_on_any_display_name(self):
        """The whole point of SEC-016. Two different principals stay two
        different principals however they are labelled, and the schema gives
        the rule no display name to read even if it wanted one."""
        document = ledger([entry(1, HUMAN)])
        document["entries"][0]["justification"] = "approved by the agent"
        self.assertEqual([], self.messages(document))

    def test_a_ledger_whose_entries_were_reordered_is_detected(self):
        document = ledger([entry(2, HUMAN), entry(1, HUMAN, PREVIOUS)])
        messages = self.messages(document)
        self.assertTrue(
            any("append-only sequence" in message for message in messages), messages
        )

    def test_an_entry_removed_from_the_middle_is_detected(self):
        document = ledger([entry(1, HUMAN), entry(3, HUMAN, PREVIOUS)])
        self.assertTrue(self.messages(document))

    def test_an_entry_that_does_not_link_to_its_predecessor_is_detected(self):
        """Without the chain, a removed entry leaves a document that is not
        merely valid but unremarkable."""
        document = ledger([entry(1, HUMAN), entry(2, HUMAN)])
        messages = self.messages(document)
        self.assertTrue(
            any("does not link to the entry before it" in m for m in messages), messages
        )

    def test_the_first_entry_must_not_claim_a_predecessor(self):
        document = ledger([entry(1, HUMAN, PREVIOUS)])
        self.assertTrue(self.messages(document))

    def test_an_empty_ledger_is_accepted(self):
        """An empty ledger records that nothing has been approved, which is a
        fact rather than an omission."""
        self.assertEqual([], self.messages(ledger([])))

    def test_the_rule_is_registered_so_the_public_entry_point_reaches_it(self):
        """A rule nothing dispatches to is a rule that does not run."""
        self.assertIn("approval-ledger", validate.SEMANTIC_RULES)


class TheCoverageRegistryIsTotalAndAgreesWithTheSchemas(unittest.TestCase):
    """The claim that used to be in a docstring with nothing behind it.

    `semantic_findings_for` told the reader a test asserted every kind with a
    relational constraint had a rule. No such test existed, and four kinds had
    silently become structure-only. The registry and these assertions are what
    that sentence was describing.
    """

    def defers(self, kind):
        with open(validate.schema_path_for(kind), encoding="utf-8") as handle:
            return "semantic check" in handle.read()

    def test_every_known_kind_is_classified(self):
        for kind in validate.known_kinds():
            self.assertIn(
                kind,
                validate.SEMANTIC_COVERAGE,
                "%s has no entry, so nobody decided whether it needs a "
                "semantic rule" % kind,
            )

    def test_the_registry_names_no_kind_that_does_not_exist(self):
        """A stale entry would let a deleted kind keep vouching for coverage."""
        known = set(validate.known_kinds())
        for kind in validate.SEMANTIC_COVERAGE:
            self.assertIn(kind, known, "%s is classified but has no schema" % kind)

    def test_a_kind_classified_as_having_a_rule_has_one(self):
        for kind, (status, _) in validate.SEMANTIC_COVERAGE.items():
            if status == validate.HAS_RULE:
                self.assertIn(kind, validate.SEMANTIC_RULES, kind)

    def test_a_kind_with_a_rule_is_classified_as_having_one(self):
        for kind in validate.SEMANTIC_RULES:
            status, _ = validate.SEMANTIC_COVERAGE[kind]
            self.assertEqual(validate.HAS_RULE, status, kind)

    def test_a_schema_that_defers_to_a_semantic_check_is_not_called_structure_only(self):
        """The second, independent source. The registry is one author's
        classification; the schema text is another's, written when the
        constraint was designed. Agreement between them is the evidence.
        """
        for kind in validate.known_kinds():
            status, _ = validate.SEMANTIC_COVERAGE[kind]
            if self.defers(kind):
                self.assertNotEqual(
                    validate.STRUCTURE_ONLY,
                    status,
                    "%s defers a constraint to a semantic check but is "
                    "classified structure-only" % kind,
                )

    def test_the_schema_cross_check_actually_finds_deferrals(self):
        """The control for the assertion above, which passes vacuously if no
        schema happens to use the phrase it looks for."""
        deferring = [kind for kind in validate.known_kinds() if self.defers(kind)]
        self.assertGreaterEqual(len(deferring), 5, deferring)

    def test_every_classification_carries_a_reason(self):
        for kind, (status, reason) in validate.SEMANTIC_COVERAGE.items():
            self.assertIn(
                status,
                (validate.HAS_RULE, validate.CROSS_DOCUMENT, validate.STRUCTURE_ONLY),
                kind,
            )
            self.assertTrue(reason.strip(), kind)

    def test_the_cross_document_layer_is_recorded_as_absent_rather_than_implied(self):
        """Naming the gap is the point. These two kinds are not checked
        relationally by anything today, and a reader of the registry learns
        that instead of assuming the rule table is complete."""
        pending = [
            kind
            for kind, (status, _) in validate.SEMANTIC_COVERAGE.items()
            if status == validate.CROSS_DOCUMENT
        ]
        self.assertEqual(["assessment-result", "workload-extension"], sorted(pending))


class TheEnvironmentBindingPeriodIsOrdered(unittest.TestCase):
    """Added because mutation found the rule had no test at all.

    Disabling it entirely left the whole suite green, which is the same
    false green this project has now hit eighteen times: a check nothing
    exercises is indistinguishable from a check that is not there.
    """

    def messages(self, override):
        document = {"observationPeriodOverride": override}
        return [
            finding.render("environment-binding.production.json")
            for finding in validate.semantic_findings_for(
                "environment-binding", document
            )
        ]

    def test_an_ordered_period_is_accepted(self):
        self.assertEqual(
            [],
            self.messages(
                {"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"}
            ),
        )

    def test_an_end_that_precedes_its_start_is_rejected(self):
        self.assertTrue(
            self.messages(
                {"start": "2026-02-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"}
            )
        )

    def test_a_period_of_zero_length_is_rejected(self):
        """An observation window that observes nothing is not an observation."""
        self.assertTrue(
            self.messages(
                {"start": "2026-01-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"}
            )
        )

    def test_a_binding_with_no_override_is_accepted(self):
        """The override is optional; its absence defers to the environment."""
        self.assertEqual([], validate.semantic_findings_for("environment-binding", {}))

    def test_the_shipped_bindings_are_semantically_clean(self):
        """A rule that rejects what the repository ships would have been
        caught here rather than by a customer."""
        for name in (
            "environment-binding.production.json",
            "environment-binding.nonproduction.json",
        ):
            path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "examples",
                "two-environments",
                name,
            )
            with open(path, encoding="utf-8") as handle:
                document = json.load(handle)
            self.assertEqual(
                [],
                validate.semantic_findings_for("environment-binding", document),
                name,
            )


class CC016TheAgentCannotWrite(unittest.TestCase):
    def refusal(self, command):
        try:
            broker.plan(command)
        except Exception as error:  # the broker's own refusal type
            return str(error)
        return None

    def test_a_read_verb_is_planned(self):
        """The control. A broker that refused everything would satisfy every
        denial assertion below while being useless."""
        self.assertIsNotNone(broker.plan(["az", "account", "show"]))

    def test_write_verbs_are_refused(self):
        for command in (
            ["az", "vm", "create"],
            ["az", "vm", "delete"],
            ["az", "group", "delete"],
            ["az", "role", "assignment", "create"],
            ["az", "vm", "restart"],
        ):
            self.assertIsNotNone(
                self.refusal(command), "%s was not refused" % " ".join(command)
            )

    def test_a_verb_nobody_thought_of_is_refused(self):
        """The refusal must not depend on recognising a write. A deny-list
        permits every verb its author did not anticipate, and the verbs
        nobody anticipated are the ones worth worrying about."""
        self.assertIsNotNone(self.refusal(["az", "vm", "zzzunheardofverb"]))
        self.assertIsNotNone(self.refusal(["az", "vm", "update"]))

    def test_the_allow_list_is_scoped_to_verbs_and_not_to_command_groups(self):
        """A named boundary rather than an oversight.

        An unrecognised command group with an allowed read verb is planned,
        because the broker allow-lists verbs. Pinned here so that the limit
        of this layer is on the record: what the agent may read is decided by
        the RBAC grant (SEC-001), not by this list. Turning this into a group
        allow-list would mean every new Azure service is refused until
        somebody edits this repository, which is the failure mode CON-11
        exists to prevent.
        """
        self.assertIsNone(self.refusal(["az", "totally-unknown-group", "show"]))

    def test_a_refused_unknown_verb_is_not_refused_for_some_other_reason(self):
        """An unknown verb refused because the token looked malformed, or
        because the program was wrong, would leave the allow-list untested."""
        message = self.refusal(["az", "vm", "zzzunheardofverb"])
        self.assertIn("verb", message)

    def test_the_refusal_is_not_resolvable_by_asking_for_more_permission(self):
        """CC-016 is explicit that escalation must not be a way out. There is
        no grant argument anywhere in the broker's surface, which is why no
        request can carry one."""
        self.assertIsNotNone(self.refusal(["az", "role", "assignment", "create"]))
        self.assertIsNotNone(self.refusal(["az", "ad", "sp", "credential", "reset"]))

    def test_a_command_must_be_a_token_list_and_never_a_string(self):
        """A string would have to be split here, and every quoting bug in
        that split is an injection. Asserted on the reason, because a string
        is refused by the program check too and that would pass for the
        wrong reason."""
        message = self.refusal("az account show")
        self.assertIn("not a string", message)


class CC020NoSecretHasAValidPositionInAnEmittedArtifact(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)

    def reject(self, kind, document):
        target = os.path.join(self.workspace, kind + ".json")
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(document, handle)
        structural, _ = validate.validate_artifact(target)
        return structural

    def test_a_secret_cannot_be_smuggled_into_an_undeclared_property(self):
        """Closure is what makes the guarantee total. Without it, every
        schema would need to anticipate the name somebody chooses."""
        document = ledger([entry(1, HUMAN)])
        document["connectionString"] = SECRET_PLACEHOLDER
        self.assertTrue(self.reject("approval-ledger", document))

    def test_the_same_document_without_the_extra_property_is_accepted(self):
        self.assertEqual([], self.reject("approval-ledger", ledger([entry(1, HUMAN)])))

    def test_no_shipped_schema_declares_a_property_that_holds_a_secret(self):
        """Driven through the real lint detector rather than by a list of
        names written here, because a check that reimplements what it checks
        keeps passing after the thing it checks stops working."""
        names = []
        for kind in validate.known_kinds():
            with open(validate.schema_path_for(kind), encoding="utf-8") as handle:
                document = json.load(handle)
            for name in schema_lint.declared_property_names(document):
                leaf = name[-1] if isinstance(name, (list, tuple)) else name
                if schema_lint.secret_marker(leaf):
                    names.append((kind, name))
        self.assertEqual([], names, names)

    def test_the_secret_marker_detector_detects(self):
        """The control for the assertion above. A detector that matched
        nothing would report a clean result on a schema full of secrets."""
        for name in ("password", "clientSecret", "connectionString", "apiKey"):
            self.assertTrue(schema_lint.secret_marker(name), name)

    def test_a_reference_is_not_mistaken_for_a_secret(self):
        """The design is that credentials are referenced, not carried. A
        detector that rejected the reference too would force the opposite."""
        for name in ("credentialRef", "secretRefs"):
            self.assertFalse(schema_lint.secret_marker(name), name)


if __name__ == "__main__":
    unittest.main()

"""The published eligibility rules and the drift check that makes FR-12 real.

FR-12 is a statement about sameness. It does not ask for the rules to be
written down; it asks that the rules a reader finds in the published document
and the rules the empty result reports are the same rules. A document and a
reporter can each be correct on the day they are written and disagree a month
later, with neither looking wrong on its own. Most of this file exists to make
that disagreement detectable.

The tamper cases drive `drift_findings` with synthetic documents rather than
with the file on disk. An assertion about one fixed file cannot distinguish a
check that compares from a check that always returns nothing, because there is
only ever one answer to observe. Every negative case here is paired with the
control that would pass, so a check that stopped comparing would fail both.
"""

import copy
import json
import os
import re
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")

if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from zeroops import core_paths, eligibility, validate  # noqa: E402

# The five stages FR-12 discovery passes through, written out here rather than
# read from the schema or the instance. Deriving them from either thing under
# test would make the assertion true by construction.
STAGES_IN_ORDER = ["scope", "permission", "signal", "extension", "exclusion"]

# A resource type in Azure is written as a provider namespace followed by a
# type, and the provider namespace always begins `Microsoft.` or a vendor
# equivalent containing a dot. Matching the shape rather than a list of names
# is deliberate: a list would only catch the types someone thought to add.
RESOURCE_TYPE_SHAPE = re.compile(r"\b[A-Z][A-Za-z]+\.[A-Z][A-Za-z]+/[a-zA-Z]+")

# Forbidden in any core path (FR-04). wizard/eligibility/ is a core path, so
# none of these may appear in the rules or in the rendered document.
RUNTIME_IDENTIFIERS = [
    "agent.json",
    "sreagent",
    "sre-agent",
    "Microsoft.App/agents",
    "new-agent",
]


def read(relative):
    with open(os.path.join(REPO_ROOT, relative.replace("/", os.sep)), "r", encoding="utf-8") as handle:
        return handle.read()


def document_with_block(block):
    """A minimal document carrying the supplied block between the markers."""
    return "# Heading\n\nProse.\n\n%s\n%s\n%s\n\nMore prose.\n" % (
        eligibility.BEGIN_MARKER,
        block,
        eligibility.END_MARKER,
    )


class TheRulesAreShipped(unittest.TestCase):
    def setUp(self):
        self.rules = eligibility.load_rules(REPO_ROOT)

    def test_the_declaration_records_the_directory_as_present(self):
        """wizard/eligibility/ was `planned`. A directory that exists while
        the declaration calls it planned is the declaration describing a
        repository that is no longer there."""
        declaration = core_paths.load_declaration(REPO_ROOT)
        entries = {
            entry["path"]: entry["status"]
            for entry in declaration["categories"]["core"]
        }
        self.assertEqual("present", entries["wizard/eligibility/"])

    def test_the_directory_no_longer_claims_a_materialising_task(self):
        declaration = core_paths.load_declaration(REPO_ROOT)
        entry = next(
            item
            for item in declaration["categories"]["core"]
            if item["path"] == "wizard/eligibility/"
        )
        self.assertNotIn("materialisedBy", entry)

    def test_the_shipped_rules_validate_against_their_schema(self):
        _artifact, findings = validate.validate(eligibility.rules_path(REPO_ROOT))
        self.assertEqual([], ["%s: %s" % (f.pointer, f.message) for f in findings])

    def test_the_schema_is_registered_with_a_version(self):
        register = json.loads(read("contracts/schema-versions.json"))
        entries = {entry["schema"]: entry for entry in register["entries"]}
        self.assertIn("eligibility-rules", entries)
        self.assertEqual("1.0.0", entries["eligibility-rules"]["version"])

    def test_every_stage_is_covered_exactly_once(self):
        """A stage with no rule would be a decision point nothing published
        explains, and an operator reading an empty result would find no
        account of the step that produced it."""
        stages = [rule["stage"] for rule in self.rules["rules"]]
        self.assertEqual(STAGES_IN_ORDER, stages)

    def test_exclusion_is_applied_last(self):
        """The document states that exclusions are applied last and always
        win. If the rule order changed, the document would describe a
        precedence the rule set no longer has."""
        self.assertEqual("exclusion", self.rules["rules"][-1]["stage"])

    def test_rule_identifiers_are_sequential(self):
        expected = ["ELI-%03d" % (index + 1) for index in range(len(self.rules["rules"]))]
        self.assertEqual(expected, [rule["id"] for rule in self.rules["rules"]])

    def test_every_rule_explains_what_an_empty_result_means(self):
        """A rule list that explains only itself tells an operator which rule
        applied and not what to do about it (FR-10)."""
        for rule in self.rules["rules"]:
            with self.subTest(rule=rule["id"]):
                self.assertGreater(len(rule["whyEmpty"]), 60)


class TheCoreShipsNoWorkloadContent(unittest.TestCase):
    """FR-63, CC-022, CON-11, SC-13.

    A default list of admitted resource types in a core path would be workload
    content, and a default list of excluded types would be the same content
    written backwards. Type eligibility arrives from an installed extension
    (ELI-004), which is why a fresh installation correctly discovers nothing.
    """

    def setUp(self):
        self.rules_text = read(eligibility.RULES_PATH)
        self.document_text = read(eligibility.DOCUMENT_PATH)

    def test_the_rules_name_no_resource_type(self):
        self.assertIsNone(RESOURCE_TYPE_SHAPE.search(self.rules_text))

    def test_the_document_names_no_resource_type(self):
        self.assertIsNone(RESOURCE_TYPE_SHAPE.search(self.document_text))

    def test_the_detector_recognises_a_resource_type(self):
        """The control. Two assertions that a pattern is absent would pass
        against a pattern that matches nothing at all."""
        self.assertIsNotNone(
            RESOURCE_TYPE_SHAPE.search("candidates include Microsoft.Compute/virtualMachines")
        )

    def test_neither_file_names_a_runtime(self):
        for name, text in (
            (eligibility.RULES_PATH, self.rules_text),
            (eligibility.DOCUMENT_PATH, self.document_text),
        ):
            for identifier in RUNTIME_IDENTIFIERS:
                with self.subTest(path=name, identifier=identifier):
                    self.assertNotIn(identifier.lower(), text.lower())


class TheRenderingIsDeterministic(unittest.TestCase):
    def setUp(self):
        self.rules = eligibility.load_rules(REPO_ROOT)

    def test_rendering_twice_gives_the_same_text(self):
        self.assertEqual(
            eligibility.render_rules(self.rules),
            eligibility.render_rules(copy.deepcopy(self.rules)),
        )

    def test_every_rule_appears_in_the_rendering(self):
        rendered = eligibility.render_rules(self.rules)
        for rule in self.rules["rules"]:
            with self.subTest(rule=rule["id"]):
                self.assertIn(rule["id"], rendered)
                self.assertIn(rule["title"], rendered)
                self.assertIn(rule["statement"], rendered)
                self.assertIn(rule["whyEmpty"], rendered)

    def test_every_rule_names_who_supplies_the_fact_it_tests(self):
        """The fix differs by owner: operator input, an Azure change, or an
        installed extension. A rendering that dropped the hint would tell the
        reader a rule excluded them and not where to go."""
        rendered = eligibility.render_rules(self.rules)
        for rule in self.rules["rules"]:
            with self.subTest(rule=rule["id"]):
                self.assertIn(eligibility.DECIDED_BY_HINT[rule["decidedBy"]], rendered)

    def test_the_rendering_carries_no_trailing_blank_line(self):
        rendered = eligibility.render_rules(self.rules)
        self.assertEqual(rendered, rendered.rstrip("\n"))

    def test_an_unknown_owner_is_reported_rather_than_rendered_blank(self):
        tampered = copy.deepcopy(self.rules)
        tampered["rules"][0]["decidedBy"] = "committee"
        findings = eligibility.hint_findings(tampered)
        self.assertEqual(1, len(findings))
        self.assertIn("committee", findings[0])

    def test_the_shipped_rules_have_no_unknown_owner(self):
        self.assertEqual([], eligibility.hint_findings(self.rules))


class TheEmptyResultReportsTheSameRules(unittest.TestCase):
    """FR-10 and FR-12. The report is built from the same rendering the
    document carries, so the two cannot disagree while the drift check
    passes."""

    def setUp(self):
        self.rules = eligibility.load_rules(REPO_ROOT)
        self.report = eligibility.empty_result_report(self.rules)

    def test_the_report_opens_with_the_published_preamble(self):
        self.assertTrue(self.report.startswith(self.rules["emptyResultPreamble"]))

    def test_the_preamble_is_not_written_in_code(self):
        """The framing is the part an operator reads first and the part most
        likely to be reworded. Written in code, it would be the only part of
        the report no drift check covered."""
        source = read("tools/zeroops/eligibility.py")
        self.assertNotIn(self.rules["emptyResultPreamble"], source)

    def test_the_report_names_every_rule(self):
        for rule in self.rules["rules"]:
            with self.subTest(rule=rule["id"]):
                self.assertIn(rule["id"], self.report)

    def test_the_report_contains_the_rendering_verbatim(self):
        self.assertIn(eligibility.render_rules(self.rules), self.report)


class TheBlockIsExtracted(unittest.TestCase):
    def test_a_well_formed_document_yields_its_block(self):
        self.assertEqual("body", eligibility.extract_block(document_with_block("body")))

    def test_a_document_without_a_begin_marker_yields_nothing(self):
        document = "prose\n%s\n" % eligibility.END_MARKER
        self.assertIsNone(eligibility.extract_block(document))

    def test_a_document_without_an_end_marker_yields_nothing(self):
        document = "prose\n%s\nbody\n" % eligibility.BEGIN_MARKER
        self.assertIsNone(eligibility.extract_block(document))

    def test_markers_in_the_wrong_order_yield_nothing(self):
        """An end marker before a begin marker would otherwise extract a
        negative-length span or silently succeed on nonsense."""
        document = "%s\nbody\n%s\n" % (eligibility.END_MARKER, eligibility.BEGIN_MARKER)
        self.assertIsNone(eligibility.extract_block(document))

    def test_carriage_returns_do_not_change_the_block(self):
        """The document is compared against a rendering built in memory, and
        a checkout on Windows may carry CRLF."""
        document = document_with_block("line one\nline two")
        self.assertEqual(
            eligibility.extract_block(document),
            eligibility.extract_block(document.replace("\n", "\r\n")),
        )


class TheDocumentCannotDriftFromTheRules(unittest.TestCase):
    """FR-12, driven with synthetic documents.

    Every case below is paired with a control, because a check that stopped
    comparing and always returned no findings would satisfy any number of
    assertions that a clean document is clean.
    """

    def setUp(self):
        self.rules = eligibility.load_rules(REPO_ROOT)
        self.rendered = eligibility.render_rules(self.rules)

    def test_the_published_document_agrees_with_the_rules(self):
        self.assertEqual([], eligibility.drift_findings(REPO_ROOT))

    def test_a_matching_document_produces_no_finding(self):
        findings = eligibility.drift_findings(
            REPO_ROOT, rules=self.rules, document=document_with_block(self.rendered)
        )
        self.assertEqual([], findings)

    def test_an_edited_block_is_reported(self):
        edited = self.rendered.replace("ELI-001", "ELI-009")
        findings = eligibility.drift_findings(
            REPO_ROOT, rules=self.rules, document=document_with_block(edited)
        )
        self.assertEqual(1, len(findings))
        self.assertIn(eligibility.RULES_PATH, findings[0])

    def test_the_finding_shows_what_the_block_should_say(self):
        """A drift finding that only says the two differ leaves the reader to
        work out the correct text, which is the step most likely to introduce
        a second difference."""
        findings = eligibility.drift_findings(
            REPO_ROOT, rules=self.rules, document=document_with_block("nothing like it")
        )
        self.assertIn(self.rendered, findings[0])

    def test_a_rule_added_without_regenerating_is_reported(self):
        tampered = copy.deepcopy(self.rules)
        added = copy.deepcopy(tampered["rules"][0])
        added["id"] = "ELI-006"
        tampered["rules"].append(added)
        findings = eligibility.drift_findings(
            REPO_ROOT, rules=tampered, document=document_with_block(self.rendered)
        )
        self.assertEqual(1, len(findings))

    def test_a_rule_removed_without_regenerating_is_reported(self):
        tampered = copy.deepcopy(self.rules)
        tampered["rules"].pop()
        findings = eligibility.drift_findings(
            REPO_ROOT, rules=tampered, document=document_with_block(self.rendered)
        )
        self.assertEqual(1, len(findings))

    def test_a_reworded_statement_is_reported(self):
        tampered = copy.deepcopy(self.rules)
        tampered["rules"][0]["statement"] = "Anything goes."
        findings = eligibility.drift_findings(
            REPO_ROOT, rules=tampered, document=document_with_block(self.rendered)
        )
        self.assertEqual(1, len(findings))

    def test_a_removed_marker_is_reported_as_a_missing_block(self):
        """Deleting a marker must not read as agreement. Without the markers
        there is nothing to compare, and a check that treated an absent block
        as a match would pass on a document saying whatever it liked."""
        document = document_with_block(self.rendered).replace(
            eligibility.BEGIN_MARKER, ""
        )
        findings = eligibility.drift_findings(
            REPO_ROOT, rules=self.rules, document=document
        )
        self.assertEqual(1, len(findings))
        self.assertIn(eligibility.BEGIN_MARKER, findings[0])

    def test_an_unknown_owner_is_reported_alongside_the_comparison(self):
        tampered = copy.deepcopy(self.rules)
        tampered["rules"][0]["decidedBy"] = "committee"
        findings = eligibility.drift_findings(
            REPO_ROOT, rules=tampered, document=document_with_block(self.rendered)
        )
        self.assertEqual(2, len(findings))

    def test_line_endings_alone_are_not_drift(self):
        document = document_with_block(self.rendered).replace("\n", "\r\n")
        findings = eligibility.drift_findings(
            REPO_ROOT, rules=self.rules, document=document
        )
        self.assertEqual([], findings)


class TheRuleSetIsCheckedForWhatTheSchemaCannotExpress(unittest.TestCase):
    """Three constraints that compare two sibling rules (FR-10, FR-12).

    Driven with synthetic instances rather than the shipped file. Asserting
    only that the shipped rule set is clean would pass against a check that
    returned nothing at all, because there is one answer to observe.
    """

    def setUp(self):
        self.rules = eligibility.load_rules(REPO_ROOT)

    def findings(self, instance):
        return [
            "%s: %s" % (f.pointer, f.message)
            for f in validate.semantic_findings_for("eligibility-rules", instance)
        ]

    def test_the_kind_is_registered_as_having_a_rule(self):
        self.assertIn("eligibility-rules", validate.SEMANTIC_RULES)
        status, _reason = validate.SEMANTIC_COVERAGE["eligibility-rules"]
        self.assertEqual(validate.HAS_RULE, status)

    def test_the_shipped_rule_set_is_clean(self):
        self.assertEqual([], self.findings(self.rules))

    def test_a_repeated_identifier_is_reported(self):
        tampered = copy.deepcopy(self.rules)
        tampered["rules"][1]["id"] = tampered["rules"][0]["id"]
        self.assertEqual(1, len(self.findings(tampered)))

    def test_a_repeated_stage_is_reported(self):
        tampered = copy.deepcopy(self.rules)
        tampered["rules"][1]["stage"] = tampered["rules"][0]["stage"]
        self.assertEqual(1, len(self.findings(tampered)))

    def test_an_exclusion_that_is_not_last_is_reported(self):
        tampered = copy.deepcopy(self.rules)
        tampered["rules"].insert(0, tampered["rules"].pop())
        findings = self.findings(tampered)
        self.assertEqual(1, len(findings))
        self.assertIn("withholding", findings[0])

    def test_a_rule_set_with_no_exclusion_is_not_reported(self):
        """The control for the precedence rule. A check that flagged any rule
        set whose last stage is not `exclusion` would also flag a rule set
        that deliberately declares no exclusion at all."""
        tampered = copy.deepcopy(self.rules)
        tampered["rules"] = [r for r in tampered["rules"] if r["stage"] != "exclusion"]
        self.assertEqual([], self.findings(tampered))


class TheBlockCanBeRegenerated(unittest.TestCase):
    """A drift check with no documented remedy is a failing test only its
    author can satisfy. `--write` is that remedy, so it is tested."""

    def setUp(self):
        self.rules = eligibility.load_rules(REPO_ROOT)
        self.rendered = eligibility.render_rules(self.rules)

    def test_regenerating_repairs_an_edited_block(self):
        stale = document_with_block("stale text")
        repaired = eligibility.replace_block(stale, self.rendered)
        self.assertEqual([], eligibility.drift_findings(
            REPO_ROOT, rules=self.rules, document=repaired
        ))

    def test_regenerating_leaves_the_surrounding_prose_alone(self):
        """The prose is authored and the block is generated. Refreshing the
        second must not quietly discard the first."""
        repaired = eligibility.replace_block(document_with_block("stale"), self.rendered)
        self.assertIn("Prose.", repaired)
        self.assertIn("More prose.", repaired)

    def test_regenerating_a_document_without_markers_refuses(self):
        """Appending a block to a document this tool has never owned would
        guess where the rules belong. Refusing is the better outcome."""
        with self.assertRaises(ValueError):
            eligibility.replace_block("# Heading\n\nNo markers here.\n", self.rendered)

    def test_the_checking_entry_point_passes_on_the_shipped_repository(self):
        self.assertEqual(0, eligibility.main([]))


if __name__ == "__main__":
    unittest.main()

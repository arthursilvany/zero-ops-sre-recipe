#!/usr/bin/env python3
"""FR-59: the prohibition page an operator reads cannot drift from the policy.

Evidence for User Story 2. The page in `docs/prohibited-actions.md` is what
somebody reads when deciding whether to point this agent at a subscription.
They do not open `core/policy/tool-policy.json`, so the page is load-bearing
and its correspondence to the policy has to be checked rather than assumed.

The direction that matters most is the one that looks fine in review: a
prohibition documented and no longer denied. The page still reads correctly.
Only a diff against the policy catches it.

The reader itself is tested rather than trusted. A section reader that quietly
found nothing would report every identifier as undocumented, which is a
message pointing at the wrong file.

Run with:
    python -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from zeroops import core_paths  # noqa: E402
from zeroops import prohibitions  # noqa: E402

DOC_PATH = os.path.join(REPO_ROOT, prohibitions.DOC.replace("/", os.sep))
POLICY_PATH = os.path.join(REPO_ROOT, prohibitions.POLICY.replace("/", os.sep))

# Enough of a page to exercise the rules without depending on the real one.
# Both sections are present and agree with SAMPLE_POLICY.
SAMPLE_DOC = """# Title

Some prose.

## What the agent must not do

| Policy category | What is prohibited | What to do instead |
|---|---|---|
| `write` | No mutation. | Apply the change through your own deployment path. |
| `secretsAccess` | No credential is read. | Reference the secret externally. |

## What the agent may reach

| Capability class | What it reaches | Where it stops |
|---|---|---|
| `readMetrics` | Metric series. | It does not emit metrics. |

## Something else

Trailing prose that is not a table.
"""

SAMPLE_POLICY = {
    "denyRules": [
        {"category": "write", "justification": "x"},
        {"category": "secretsAccess", "justification": "y"},
    ],
    "allowedCapabilityClasses": ["readMetrics"],
}


def real_policy():
    with open(POLICY_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def real_doc():
    with open(DOC_PATH, encoding="utf-8") as handle:
        return handle.read()


def scan_against(document, text):
    """Run the real `scan` over a synthetic repository holding this pair.

    An earlier version of this helper reassembled the calls `scan` makes,
    which meant `scan` could stop comparing altogether and every test here
    would still pass. Mutation caught it. The comparison is only evidence if
    the entry point performs it, so the pair is written to a temporary root
    and the entry point is what runs.
    """
    root = tempfile.mkdtemp(prefix="prohib-")
    try:
        policy_file = os.path.join(root, prohibitions.POLICY.replace("/", os.sep))
        doc_file = os.path.join(root, prohibitions.DOC.replace("/", os.sep))
        os.makedirs(os.path.dirname(policy_file))
        os.makedirs(os.path.dirname(doc_file))
        with open(policy_file, "w", encoding="utf-8") as handle:
            json.dump(document, handle)
        with open(doc_file, "w", encoding="utf-8") as handle:
            handle.write(text)
        problems, _ = prohibitions.scan(
            root, [prohibitions.POLICY, prohibitions.DOC], None
        )
        return problems
    finally:
        shutil.rmtree(root, ignore_errors=True)


class TheReaderIsTestedRatherThanTrusted(unittest.TestCase):
    """A reader that silently found nothing would make every rule above it pass.

    Every rule in this module is a comparison against what the reader
    extracted. If extraction returned nothing the comparison would blame the
    policy, so the extraction is pinned on its own.
    """

    def test_a_level_two_heading_starts_a_section(self):
        found = prohibitions.sections("## One\nbody\n## Two\nother\n")
        self.assertEqual(sorted(found), ["## One", "## Two"])

    def test_the_body_of_a_section_stops_at_the_next_level_two_heading(self):
        found = prohibitions.sections("## One\nalpha\n## Two\nbeta\n")
        self.assertEqual(found["## One"], ["alpha"])
        self.assertEqual(found["## Two"], ["beta"])

    def test_a_level_three_heading_stays_inside_its_section(self):
        found = prohibitions.sections("## One\n### Deeper\nalpha\n")
        self.assertIn("### Deeper", found["## One"])
        self.assertNotIn("### Deeper", found)

    def test_a_level_one_heading_ends_a_section_without_starting_one(self):
        found = prohibitions.sections("## One\nalpha\n# Top\nbeta\n")
        self.assertEqual(found["## One"], ["alpha"])
        self.assertNotIn("# Top", found)

    def test_content_before_any_heading_belongs_to_no_section(self):
        found = prohibitions.sections("preamble\n## One\nalpha\n")
        self.assertEqual(list(found), ["## One"])

    def test_the_delimiter_row_is_what_marks_the_rows_after_it_as_data(self):
        table = prohibitions.rows(["| h |", "|---|", "| `a` |"])
        self.assertEqual(table, [["`a`"]])

    def test_a_table_with_no_delimiter_row_yields_no_data(self):
        self.assertEqual(prohibitions.rows(["| h |", "| `a` |"]), [])

    def test_a_delimiter_row_may_carry_alignment_colons(self):
        table = prohibitions.rows(["| h | h |", "|:---|---:|", "| `a` | b |"])
        self.assertEqual(table, [["`a`", "b"]])

    def test_prose_before_the_table_is_skipped(self):
        table = prohibitions.rows(["intro", "", "| h |", "|---|", "| `a` |"])
        self.assertEqual(table, [["`a`"]])

    def test_a_second_table_in_the_same_section_is_not_read(self):
        """Reading it would silently widen what the section is understood to mean."""
        table = prohibitions.rows(
            ["| h |", "|---|", "| `a` |", "", "| h |", "|---|", "| `b` |"]
        )
        self.assertEqual(table, [["`a`"]])

    def test_a_section_with_no_table_at_all_yields_no_rows(self):
        self.assertEqual(prohibitions.rows(["just prose", ""]), [])


class TheRowLabelIsAnExactToken(unittest.TestCase):
    """Prose containing an identifier is not the same as naming one.

    If a row label were matched by substring, a sentence mentioning `write`
    would satisfy the comparison, and the link between the page and the policy
    would be a coincidence rather than a reference.
    """

    def test_a_single_backticked_identifier_is_accepted(self):
        problems = []
        names = prohibitions.documented(SAMPLE_DOC, prohibitions.PROHIBITION_HEADING, problems)
        self.assertEqual(names, ["write", "secretsAccess"])
        self.assertEqual(problems, [])

    def test_an_unbackticked_label_is_rejected(self):
        text = SAMPLE_DOC.replace("| `write` |", "| write |")
        problems = []
        names = prohibitions.documented(text, prohibitions.PROHIBITION_HEADING, problems)
        self.assertNotIn("write", names)
        self.assertTrue(any("not a single backticked identifier" in p for p in problems))

    def test_prose_containing_a_backticked_identifier_is_rejected(self):
        text = SAMPLE_DOC.replace("| `write` |", "| the `write` category |")
        problems = []
        names = prohibitions.documented(text, prohibitions.PROHIBITION_HEADING, problems)
        self.assertNotIn("write", names)
        self.assertTrue(any("not a single backticked identifier" in p for p in problems))

    def test_an_identifier_followed_by_prose_is_rejected(self):
        """The trailing anchor is what rejects this. Without it the cell reads
        as a reference while saying something the comparison never sees."""
        text = SAMPLE_DOC.replace("| `write` |", "| `write` and anything else |")
        problems = []
        names = prohibitions.documented(text, prohibitions.PROHIBITION_HEADING, problems)
        self.assertNotIn("write", names)
        self.assertTrue(any("not a single backticked identifier" in p for p in problems))

    def test_the_same_identifier_documented_twice_is_reported(self):
        """A set comparison would agree with itself and hide the duplicate row."""
        text = SAMPLE_DOC.replace(
            "| `secretsAccess` | No credential is read. | Reference the secret externally. |",
            "| `write` | Again. | Something. |",
        )
        problems = []
        prohibitions.documented(text, prohibitions.PROHIBITION_HEADING, problems)
        self.assertTrue(any("more than once" in p for p in problems))


class GuidanceIsWhatMakesThePageOperatorFacing(unittest.TestCase):
    """Without it the page is the policy restated, and passes the diff forever.

    The check establishes that somebody wrote guidance. It cannot establish
    that the guidance is good, and does not claim to.
    """

    def test_an_empty_guidance_cell_is_reported(self):
        text = SAMPLE_DOC.replace(
            "| `write` | No mutation. | Apply the change through your own deployment path. |",
            "| `write` | No mutation. |  |",
        )
        problems = []
        prohibitions.documented(text, prohibitions.PROHIBITION_HEADING, problems)
        self.assertTrue(any("no guidance" in p for p in problems))

    def test_a_placeholder_dash_is_reported(self):
        text = SAMPLE_DOC.replace(
            "| Apply the change through your own deployment path. |", "| - |"
        )
        problems = []
        prohibitions.documented(text, prohibitions.PROHIBITION_HEADING, problems)
        self.assertTrue(any("no guidance" in p for p in problems))

    def test_a_placeholder_is_recognised_regardless_of_case(self):
        text = SAMPLE_DOC.replace(
            "| Apply the change through your own deployment path. |", "| N/A |"
        )
        problems = []
        prohibitions.documented(text, prohibitions.PROHIBITION_HEADING, problems)
        self.assertTrue(any("no guidance" in p for p in problems))

    def test_a_bare_question_mark_is_reported(self):
        text = SAMPLE_DOC.replace(
            "| Apply the change through your own deployment path. |", "| ? |"
        )
        problems = []
        prohibitions.documented(text, prohibitions.PROHIBITION_HEADING, problems)
        self.assertTrue(any("no guidance" in p for p in problems))

    def test_real_guidance_is_accepted(self):
        problems = []
        prohibitions.documented(SAMPLE_DOC, prohibitions.PROHIBITION_HEADING, problems)
        self.assertFalse(any("no guidance" in p for p in problems))


class DriftIsReportedInBothDirections(unittest.TestCase):
    """The two directions fail differently and neither is the minor one.

    A rule nobody wrote down leaves an incomplete picture of a safe system.
    A rule written down and no longer denied leaves the reader relying on a
    promise nothing keeps, and the page still reads correctly.
    """

    def test_the_sample_pair_agrees(self):
        """The control case. Without it a rule that always fired would look right."""
        self.assertEqual(scan_against(SAMPLE_POLICY, SAMPLE_DOC), [])

    def test_a_deny_rule_that_is_not_documented_is_reported(self):
        policy = copy.deepcopy(SAMPLE_POLICY)
        policy["denyRules"].append({"category": "externalPublication", "justification": "z"})
        problems = scan_against(policy, SAMPLE_DOC)
        self.assertTrue(any("does not document `externalPublication`" in p for p in problems))

    def test_a_documented_prohibition_with_no_rule_behind_it_is_reported(self):
        policy = copy.deepcopy(SAMPLE_POLICY)
        policy["denyRules"] = [r for r in policy["denyRules"] if r["category"] != "write"]
        problems = scan_against(policy, SAMPLE_DOC)
        self.assertTrue(any("documents `write`" in p for p in problems))
        self.assertTrue(any("promises something no rule keeps" in p for p in problems))

    def test_an_allowed_capability_that_is_not_documented_is_reported(self):
        policy = copy.deepcopy(SAMPLE_POLICY)
        policy["allowedCapabilityClasses"].append("readLogs")
        problems = scan_against(policy, SAMPLE_DOC)
        self.assertTrue(any("does not document `readLogs`" in p for p in problems))

    def test_a_documented_capability_with_no_grant_behind_it_is_reported(self):
        policy = copy.deepcopy(SAMPLE_POLICY)
        policy["allowedCapabilityClasses"] = []
        problems = scan_against(policy, SAMPLE_DOC)
        self.assertTrue(any("documents `readMetrics`" in p for p in problems))

    def test_the_two_sections_are_compared_separately(self):
        """Read into one set, a prohibition in the capability table would satisfy the diff.

        That is the failure hardest to see by eye, because both identifiers
        are present on the page and only their placement is wrong.
        """
        text = SAMPLE_DOC.replace(
            "| `readMetrics` | Metric series. | It does not emit metrics. |",
            "| `readMetrics` | Metric series. | It does not emit metrics. |\n"
            "| `write` | Misplaced. | Somewhere useful. |",
        )
        text = text.replace(
            "| `write` | No mutation. | Apply the change through your own deployment path. |\n",
            "",
        )
        problems = scan_against(SAMPLE_POLICY, text)
        self.assertTrue(any("does not document `write`" in p for p in problems))
        self.assertTrue(any("promises something no rule keeps" in p for p in problems))


class AMissingSectionSaysSoRatherThanBlamingThePolicy(unittest.TestCase):
    """A check whose failure describes a different problem is barely better than none."""

    def test_a_renamed_prohibition_heading_is_reported_as_a_missing_section(self):
        text = SAMPLE_DOC.replace(prohibitions.PROHIBITION_HEADING, "## Forbidden things")
        problems = []
        prohibitions.documented(text, prohibitions.PROHIBITION_HEADING, problems)
        self.assertEqual(len(problems), 1)
        self.assertIn("has no", problems[0])
        self.assertIn("section", problems[0])

    def test_a_renamed_capability_heading_is_reported_as_a_missing_section(self):
        text = SAMPLE_DOC.replace(prohibitions.CAPABILITY_HEADING, "## Reachable")
        problems = []
        prohibitions.documented(text, prohibitions.CAPABILITY_HEADING, problems)
        self.assertEqual(len(problems), 1)
        self.assertIn("has no", problems[0])

    def test_a_section_that_exists_with_no_table_is_reported_as_empty(self):
        text = SAMPLE_DOC.replace(
            "| Policy category | What is prohibited | What to do instead |\n"
            "|---|---|---|\n"
            "| `write` | No mutation. | Apply the change through your own deployment path. |\n"
            "| `secretsAccess` | No credential is read. | Reference the secret externally. |\n",
            "We have not written this yet.\n",
        )
        problems = []
        prohibitions.documented(text, prohibitions.PROHIBITION_HEADING, problems)
        self.assertEqual(len(problems), 1)
        self.assertIn("no table rows", problems[0])

    def test_an_empty_section_is_distinguished_from_a_missing_one(self):
        """Two different repairs. Reporting them as one sends the reader to the wrong file."""
        missing = []
        prohibitions.documented("# Title\n", prohibitions.PROHIBITION_HEADING, missing)
        empty = []
        prohibitions.documented(
            prohibitions.PROHIBITION_HEADING + "\n\nnothing here\n",
            prohibitions.PROHIBITION_HEADING,
            empty,
        )
        self.assertNotEqual(missing[0], empty[0])


class TheScanReportsWhatItCouldNotRead(unittest.TestCase):
    """A scan of nothing looks exactly like a scan that agreed."""

    def test_the_real_repository_passes(self):
        files = core_paths.tracked_files(REPO_ROOT)
        problems, examined = prohibitions.scan(REPO_ROOT, files, None)
        self.assertEqual(problems, [])
        self.assertEqual(examined, {"policies": 1, "pages": 1})

    def test_counts_are_reported_by_kind_rather_than_as_a_total(self):
        """A single total lets one artifact fall to zero unnoticed."""
        files = core_paths.tracked_files(REPO_ROOT)
        _, examined = prohibitions.scan(REPO_ROOT, files, None)
        self.assertEqual(sorted(examined), ["pages", "policies"])

    def test_an_untracked_page_is_reported_rather_than_skipped(self):
        files = [f for f in core_paths.tracked_files(REPO_ROOT) if f != prohibitions.DOC]
        problems, examined = prohibitions.scan(REPO_ROOT, files, None)
        self.assertTrue(any("is missing" in p for p in problems))
        self.assertEqual(examined["pages"], 0)

    def test_an_untracked_policy_is_reported_rather_than_skipped(self):
        files = [f for f in core_paths.tracked_files(REPO_ROOT) if f != prohibitions.POLICY]
        problems, examined = prohibitions.scan(REPO_ROOT, files, None)
        self.assertTrue(any("nothing to compare" in p for p in problems))
        self.assertEqual(examined["policies"], 0)

    def test_an_unreadable_policy_does_not_report_every_identifier_as_unbacked(self):
        """One cause, one finding. Seven derived findings would bury it."""
        files = [f for f in core_paths.tracked_files(REPO_ROOT) if f != prohibitions.POLICY]
        problems, _ = prohibitions.scan(REPO_ROOT, files, None)
        self.assertFalse(any("promises something no rule keeps" in p for p in problems))

    def test_a_policy_that_is_not_an_object_is_reported_rather_than_crashing(self):
        self.assertEqual(prohibitions.declared_categories({}), [])
        self.assertEqual(prohibitions.declared_capabilities({}), [])

    def test_a_deny_rule_without_a_category_is_ignored_rather_than_crashing(self):
        found = prohibitions.declared_categories({"denyRules": [{"justification": "x"}, 7]})
        self.assertEqual(found, [])


class TheRealPageCoversTheRealPolicy(unittest.TestCase):
    """The end-to-end assertion. Everything above establishes it can fail."""

    def test_every_deny_rule_in_the_shipped_policy_is_on_the_page(self):
        problems = []
        written = prohibitions.documented(
            real_doc(), prohibitions.PROHIBITION_HEADING, problems
        )
        self.assertEqual(problems, [])
        for category in prohibitions.declared_categories(real_policy()):
            self.assertIn(category, written)

    def test_every_allowed_capability_in_the_shipped_policy_is_on_the_page(self):
        problems = []
        written = prohibitions.documented(
            real_doc(), prohibitions.CAPABILITY_HEADING, problems
        )
        self.assertEqual(problems, [])
        for name in prohibitions.declared_capabilities(real_policy()):
            self.assertIn(name, written)

    def test_the_page_does_not_overclaim_the_policy_as_the_guarantee(self):
        """The RBAC grant is the authority. A page implying otherwise misleads.

        This is the one claim on the page that, if wrong, would cause somebody
        to trust the wrong layer. The sentence carrying it is pinned rather
        than the word, because the word appears three more times and a page
        that dropped the sentence would still contain it.

        Naming the residual: this pins phrases, not meaning. A page could be
        rewritten to mislead while keeping all three. Nothing mechanical
        reaches further than this.
        """
        text = real_doc()
        self.assertIn("the RBAC grant Azure Resource Manager", text)
        self.assertIn("defence in depth", text)
        self.assertIn("declared, not runtime-verified", text)

    def test_the_gate_runs_this_check(self):
        """Wiring is the failure mode nothing else here would catch."""
        problems = core_paths.check(REPO_ROOT)
        self.assertEqual(problems, [])
        source = core_paths.check.__code__.co_names
        self.assertIn("check_prohibited_actions", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)

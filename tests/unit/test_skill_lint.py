"""Quality lint checks for consumer extension skills."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from zeroops import skill_lint, validate


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(REPO_ROOT, "tests", "fixtures", "skills")


class SkillGuidanceLint(unittest.TestCase):
    def stage_extensions(self):
        temporary = tempfile.TemporaryDirectory()
        target = os.path.join(temporary.name, "extensions")
        shutil.copytree(FIXTURES, target)
        return temporary, target

    def test_topic_only_billing_deployment_and_error_rate_skills_get_all_warnings(self):
        temporary, target = self.stage_extensions()
        self.addCleanup(temporary.cleanup)

        count, findings = skill_lint.lint_directory(target)

        self.assertEqual(6, count)
        for domain in ("billing", "deployment", "error-rate"):
            with self.subTest(domain=domain):
                matching = [finding for finding in findings if domain in finding]
                self.assertEqual(4, len(matching), matching)
        self.assertEqual(12, len(findings))

    def test_skills_with_all_four_guidance_sections_pass(self):
        temporary, target = self.stage_extensions()
        self.addCleanup(temporary.cleanup)

        findings = skill_lint.lint_directory(target)[1]

        useful = [finding for finding in findings if "useful" in finding]
        self.assertEqual([], useful)

    def test_each_guidance_dimension_is_required(self):
        content = """# Example

## When to use
Use when the billing forecast changes.

## What to check
Compare the forecast and invoice period.

## When not to use
Do not use for disputed invoice adjustments.

## Common mistake
Do not compare different billing periods.
"""
        headings = (
            "## When to use",
            "## What to check",
            "## When not to use",
            "## Common mistake",
        )
        for removed in headings:
            with self.subTest(removed=removed):
                body = "\n".join(line for line in content.splitlines() if line != removed)
                with tempfile.TemporaryDirectory() as temporary:
                    target = os.path.join(temporary, "extensions")
                    os.mkdir(target)
                    path = os.path.join(target, "skill.md")
                    with open(path, "w", encoding="utf-8") as handle:
                        handle.write(body)
                    findings = skill_lint.lint_directory(target)[1]
                self.assertEqual(1, len(findings), findings)

    def test_headings_and_text_inside_fenced_code_are_not_guidance(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = os.path.join(temporary, "extensions")
            os.mkdir(target)
            path = os.path.join(target, "skill.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "```markdown\n"
                    "## When to use\nUse when needed.\n"
                    "## What to check\nInspect the service.\n"
                    "## When not to use\nDo not use for approval.\n"
                    "## Common mistake\nAvoid assumptions.\n"
                    "```\n"
                )
            findings = skill_lint.lint_directory(target)[1]
        self.assertEqual(4, len(findings), findings)

    def test_multiline_html_comments_do_not_count_as_guidance(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = os.path.join(temporary, "extensions")
            os.mkdir(target)
            path = os.path.join(target, "skill.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "## When to use\n<!-- hidden\nUse when needed.\n-->\n"
                    "## What to check\n<!-- hidden\nInspect the service.\n-->\n"
                    "## When not to use\n<!-- hidden\nDo not approve.\n-->\n"
                    "## Common mistake\n<!-- hidden\nAvoid assumptions.\n-->\n"
                )
            findings = skill_lint.lint_directory(target)[1]
        self.assertEqual(4, len(findings), findings)

    def test_headings_and_guidance_inside_html_comments_are_not_visible(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = os.path.join(temporary, "extensions")
            os.mkdir(target)
            path = os.path.join(target, "skill.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "<!--\n"
                    "## When to use\nUse when needed.\n"
                    "## What to check\nInspect the service.\n"
                    "## When not to use\nDo not use for approval.\n"
                    "## Common mistake\nAvoid assumptions.\n"
                    "-->\n"
                )
            findings = skill_lint.lint_directory(target)[1]
        self.assertEqual(4, len(findings), findings)

    def test_visible_guidance_after_html_comment_closure_is_recognized(self):
        content = """<!--
## When to use
Hidden guidance.
-->
# Billing skill

## When to use
Use when the billing forecast changes.

## What to check
Compare the forecast and invoice period.

## When not to use
Do not use for disputed invoice adjustments.

## Common mistake
Do not compare different billing periods.
"""
        with tempfile.TemporaryDirectory() as temporary:
            target = os.path.join(temporary, "extensions")
            os.mkdir(target)
            path = os.path.join(target, "skill.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
            findings = skill_lint.lint_directory(target)[1]
        self.assertEqual([], findings)

    def test_html_comments_inside_fenced_code_do_not_hide_visible_guidance(self):
        content = """```markdown
<!--
## When to use
Hidden code sample.
-->
```
## When to use
Use when the billing forecast changes.

## What to check
Compare the forecast and invoice period.

## When not to use
Do not use for disputed invoice adjustments.

## Common mistake
Do not compare different billing periods.
"""
        with tempfile.TemporaryDirectory() as temporary:
            target = os.path.join(temporary, "extensions")
            os.mkdir(target)
            path = os.path.join(target, "skill.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
            findings = skill_lint.lint_directory(target)[1]
        self.assertEqual([], findings)

    def test_empty_or_placeholder_guidance_does_not_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = os.path.join(temporary, "extensions")
            os.mkdir(target)
            path = os.path.join(target, "skill.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("## When to use\nTODO\n")
            findings = skill_lint.lint_directory(target)[1]
        self.assertIn("when it applies", findings[0])

    def test_only_markdown_skills_under_extensions_are_scanned(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = os.path.join(temporary, "extensions")
            os.makedirs(os.path.join(target, "nested"))
            with open(os.path.join(target, "README.md"), "w", encoding="utf-8") as handle:
                handle.write("Extension guide")
            with open(os.path.join(target, "notes.txt"), "w", encoding="utf-8") as handle:
                handle.write("not a skill")
            with open(os.path.join(target, "nested", "SKILL.md"), "w", encoding="utf-8") as handle:
                handle.write("# Topic only\n")
            count, findings = skill_lint.lint_directory(target)
        self.assertEqual(1, count)
        self.assertEqual(4, len(findings))
        prefix = os.path.join("nested", "SKILL.md")
        self.assertTrue(all(finding.startswith(prefix) for finding in findings))

    def test_a_non_extensions_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(skill_lint.SkillLintError):
                skill_lint.lint_directory(temporary)

    def test_warning_only_cli_returns_success_and_does_not_echo_skill_content(self):
        temporary, target = self.stage_extensions()
        self.addCleanup(temporary.cleanup)
        marker = "PRIVATE-CONTENT-MUST-NOT-APPEAR"
        vague = os.path.join(target, "vague", "billing.md")
        with open(vague, "a", encoding="utf-8") as handle:
            handle.write("\n" + marker)

        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = validate.main(["lint-skills", target])

        self.assertEqual(validate.EXIT_OK, result)
        self.assertIn("warning:", stderr.getvalue())
        self.assertIn("warnings do not change the exit status", stderr.getvalue())
        self.assertNotIn(marker, stdout.getvalue() + stderr.getvalue())

    def test_cli_reports_a_missing_extensions_directory_as_an_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = os.path.join(temporary, "extensions")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = validate.main(["lint-skills", target])
        self.assertEqual(validate.EXIT_USAGE, result)
        self.assertIn("error:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

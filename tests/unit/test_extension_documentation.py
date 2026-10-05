"""The extension guide covers the declared v1 extension-point inventory."""

import os
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXTENSIONS = os.path.join(REPO_ROOT, "extensions")
SOURCE_ANALYSIS = os.path.join(REPO_ROOT, "docs", "architecture", "source-analysis.md")
GUIDE = os.path.join(EXTENSIONS, "README.md")
SOURCE_HEADING = "### 5.3 Category 3"
GUIDE_HEADING = "## Extension-point coverage"


def table_rows_in_section(markdown, heading):
    section = markdown.split(heading, 1)[1]
    level = len(heading) - len(heading.lstrip("#"))
    for index, line in enumerate(section.splitlines()):
        if line.startswith("#" * level + " "):
            section = "\n".join(section.splitlines()[:index])
            break

    rows = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and all(not cell or set(cell) <= {"-", ":"} for cell in cells):
            continue
        if cells and cells[0] != "Extension point":
            rows.append(cells)
    return rows


class ExtensionDocumentation(unittest.TestCase):
    def test_every_source_analysis_point_has_an_input_output_and_upgrade_disposition(self):
        with open(SOURCE_ANALYSIS, "r", encoding="utf-8") as handle:
            source = handle.read()
        with open(GUIDE, "r", encoding="utf-8") as handle:
            guide = handle.read()

        source_points = [row[0] for row in table_rows_in_section(source, SOURCE_HEADING)]
        documented = table_rows_in_section(guide, GUIDE_HEADING)
        documented_points = [row[0] for row in documented]

        self.assertEqual(source_points, documented_points)
        for row in documented:
            with self.subTest(extension_point=row[0]):
                self.assertEqual(5, len(row), row)
                self.assertTrue(all(row[1:]), row)

    def test_framework_extension_directory_ships_only_its_contract(self):
        shipped_files = []
        for current, _, filenames in os.walk(EXTENSIONS):
            shipped_files.extend(
                os.path.relpath(os.path.join(current, filename), EXTENSIONS)
                for filename in filenames
            )
        self.assertEqual(["README.md"], sorted(shipped_files))


if __name__ == "__main__":
    unittest.main()

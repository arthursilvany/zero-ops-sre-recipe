"""Keep the framework configuration reference complete with its schema."""

import json
import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA_PATH = os.path.join(
    REPO_ROOT, "contracts", "schemas", "framework-config.schema.json"
)
REFERENCE_PATH = os.path.join(
    REPO_ROOT, "docs", "architecture", "framework-configuration-reference.md"
)


def load_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_pointer(document, reference):
    if not reference.startswith("#/"):
        raise ValueError("Only local JSON Pointer references are supported")
    target = document
    for token in reference[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        target = target[token]
    return target


def schema_instance_paths(schema):
    """Expand local refs and arrays into the property's effective instance paths."""
    paths = set()

    def visit(node, path, references=()):
        reference = node.get("$ref")
        if reference:
            if reference in references:
                raise ValueError("Recursive references are not supported in this schema")
            visit(resolve_pointer(schema, reference), path, references + (reference,))

        for name, definition in node.get("properties", {}).items():
            property_path = path + "/" + name.replace("~", "~0").replace("/", "~1")
            paths.add(property_path)
            visit(definition, property_path, references)

        if "items" in node:
            visit(node["items"], path + "/*", references)

    visit(schema, "")
    return paths


def documented_property_rows(markdown):
    rows = {}
    section = None
    pattern = re.compile(
        r"^\|\s*`(/[^`]+)`\s*\|([^|]+)\|([^|]+)\|([^|]+)\|\s*$"
    )
    for line in markdown.splitlines():
        if line.startswith("## "):
            section = line[3:]
        match = pattern.match(line)
        if match:
            path = match.group(1)
            if path in rows:
                raise AssertionError("duplicate documented property path: " + path)
            rows[path] = (section,) + tuple(
                value.strip() for value in match.groups()[1:]
            )
    return rows


def coverage_errors(schema_paths, documented_paths):
    missing = sorted(schema_paths - documented_paths)
    stale = sorted(documented_paths - schema_paths)
    errors = []
    errors.extend("undocumented schema property: " + path for path in missing)
    errors.extend("unknown documented property: " + path for path in stale)
    return errors


class FrameworkConfigurationReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(REFERENCE_PATH, "r", encoding="utf-8") as handle:
            cls.markdown = handle.read()
        cls.rows = documented_property_rows(cls.markdown)
        cls.schema_paths = schema_instance_paths(load_schema())

    def test_reference_documents_exactly_the_current_schema_properties(self):
        errors = coverage_errors(self.schema_paths, set(self.rows))
        self.assertEqual(errors, [])
        self.assertEqual(len(self.rows), len(self.schema_paths))
        concern_by_root = {
            "schemaVersion": "Shared contract metadata",
            "frameworkDefaults": "Concern 1: Global framework defaults",
            "environments": "Concern 2: Environment settings",
            "workloads": "Concern 3: Workload-specific settings",
            "toolIntegrations": "Concern 4: Tool and integration settings",
            "observability": "Concern 5: Observability settings",
            "remediationPermissions": "Concern 6: Remediation permissions",
            "approvalPolicies": "Concern 7: Approval policies",
            "externalReferences": "Concern 8: Externally referenced sensitive values",
        }
        for path, fields in self.rows.items():
            with self.subTest(path=path):
                self.assertTrue(all(fields), "incomplete reference row: " + path)
                root = path.split("/")[1]
                self.assertEqual(fields[0], concern_by_root[root])

    def test_coverage_check_reports_missing_and_stale_paths(self):
        schema_paths = {
            "/schemaVersion",
            "/workloads/*/inScope/*/selector",
        }
        documented_paths = {
            "/schemaVersion",
            "/workloads/*/inScope/*/oldSelector",
        }
        self.assertEqual(
            coverage_errors(schema_paths, documented_paths),
            [
                "undocumented schema property: /workloads/*/inScope/*/selector",
                "unknown documented property: /workloads/*/inScope/*/oldSelector",
            ],
        )

    def test_local_references_expand_into_each_nested_instance_path(self):
        expected = {
            "/frameworkDefaults/observationPeriod/start",
            "/environments/*/observationPeriod/end",
            "/workloads/*/inScope/*/kind",
            "/workloads/*/outOfScope/*/selector",
        }
        self.assertTrue(expected.issubset(self.schema_paths))

#!/usr/bin/env python3
"""T5.02: no Terraform, no ARM JSON, no re-authored upstream resource.

ADR-0002 makes Bicep composed over pinned upstream modules the only authored
Infrastructure as Code, keeps ARM JSON a compiled output, and CON-12 leaves
Terraform to upstream. These tests hold the repository to that and show the
check can both refuse and accept: every rejection pairs with a control that
changes one thing and passes.

The fixtures are written to a temporary directory, never committed, because a
committed fixture would itself be the artifact the check forbids.

Run with:
    python -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from zeroops import core_paths  # noqa: E402
from zeroops import iac_structure  # noqa: E402

WORKSPACE = "Microsoft.OperationalInsights/workspaces"
WORKFLOW = "Microsoft.Logic/workflows"
PARENT = "Example.Provider/parents"
CHILD = "Example.Provider/parents/children"
NOT_UPSTREAM = "Microsoft.Storage/storageAccounts"
UPSTREAM = [WORKSPACE, WORKFLOW, CHILD]


def findings_for(bicep, types=UPSTREAM):
    return iac_structure.bicep_findings("deploy/compose/main.bicep", bicep, types)


class Workspace:
    """A throwaway tree holding only the files a test writes."""

    def __enter__(self):
        self.root = tempfile.mkdtemp(prefix="zo-t502-")
        self.files = []
        return self

    def __exit__(self, *_):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, path, text=""):
        full = os.path.join(self.root, *path.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.files.append(path)

    def check(self, types=UPSTREAM):
        return iac_structure.check(self.root, self.files, types)


class TheRepositoryHolds(unittest.TestCase):
    """The acceptance: the tracked tree carries none of the three."""

    def test_no_tracked_file_breaks_a_rule(self):
        files = core_paths.tracked_files(REPO_ROOT)
        types = iac_structure.load_upstream_types(REPO_ROOT)
        findings = iac_structure.check(REPO_ROOT, files, types)
        self.assertEqual([], ["%s: %s" % f for f in findings])

    def test_the_check_read_real_input(self):
        files = core_paths.tracked_files(REPO_ROOT)
        json_files = [f for f in files if f.lower().endswith(".json")]
        # A tree that listed no JSON would pass the ARM rule vacuously.
        self.assertGreater(len(json_files), 10)

    def test_the_measured_list_is_pinned_to_the_lock(self):
        with open(os.path.join(REPO_ROOT, iac_structure.UPSTREAM_LOCK_PATH), encoding="utf-8") as h:
            pinned = json.load(h)["upstream"]["commit"]
        with open(os.path.join(REPO_ROOT, iac_structure.UPSTREAM_TYPES_PATH), encoding="utf-8") as h:
            measured = json.load(h)
        self.assertEqual(pinned, measured["upstreamCommit"])
        types = iac_structure.load_upstream_types(REPO_ROOT)
        self.assertIn(WORKSPACE, types)
        self.assertIn("Microsoft.Authorization/roleAssignments", types)


class TerraformIsRefused(unittest.TestCase):
    def test_every_terraform_artifact_is_refused(self):
        for path in (
            "deploy/main.tf",
            "deploy/main.tf.json",
            "examples/minimal/prod.tfvars",
            "examples/minimal/prod.tfvars.json",
            "deploy/terraform.tfstate",
            "deploy/terraform.tfstate.backup",
            "deploy/out.tfplan",
            "deploy/.terraform.lock.hcl",
            "deploy/terragrunt.hcl",
            "deploy/terraform/README.md",
            "deploy/.terraform/providers/x",
            "DEPLOY/MAIN.TF",
        ):
            with self.subTest(path=path):
                self.assertIsNotNone(iac_structure.terraform_finding(path))

    def test_a_name_that_only_mentions_terraform_passes(self):
        for path in (
            "docs/terraform-notes.md",
            "tools/zeroops/validate.py",
            "deploy/main.bicep",
            "deploy/tf.md",
        ):
            with self.subTest(path=path):
                self.assertIsNone(iac_structure.terraform_finding(path))

    def test_the_repository_check_reports_it(self):
        with Workspace() as w:
            w.write("deploy/main.tf", 'resource "x" "y" {}\n')
            w.write("deploy/README.md", "Bicep only.\n")
            self.assertEqual(["deploy/main.tf"], [f.path for f in w.check()])


class ArmJsonIsRefused(unittest.TestCase):
    def test_every_arm_schema_is_refused(self):
        for schema in (
            "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "https://schema.management.azure.com/schemas/2018-05-01/subscriptionDeploymentTemplate.json#",
            "https://schema.management.azure.com/schemas/2019-08-01/managementGroupDeploymentTemplate.json#",
            "https://schema.management.azure.com/schemas/2019-08-01/tenantDeploymentTemplate.json#",
            "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
            "HTTPS://SCHEMA.MANAGEMENT.AZURE.COM/SCHEMAS/2019-04-01/DEPLOYMENTTEMPLATE.JSON#",
        ):
            with self.subTest(schema=schema):
                text = json.dumps({"$schema": schema})
                self.assertIsNotNone(iac_structure.arm_json_finding("x.json", text))

    def test_a_template_without_a_schema_is_still_recognised(self):
        for document in (
            {"contentVersion": "1.0.0.0", "resources": []},
            {"contentVersion": "1.0.0.0", "parameters": {}},
        ):
            with self.subTest(document=document):
                text = json.dumps(document)
                self.assertIsNotNone(iac_structure.arm_json_finding("x.json", text))

    def test_a_framework_document_passes(self):
        for document in (
            {"$schema": "https://example.invalid/contracts/framework-config.schema.json"},
            {"contentVersion": "1.0.0.0"},
            {"resources": [], "parameters": {}},
            ["contentVersion", "resources"],
            {"$schema": "https://schema.management.azure.com/schemas/0.1.2-preview/CreateUIDefinition.MultiVm.json#"},
        ):
            with self.subTest(document=document):
                self.assertIsNone(iac_structure.arm_json_finding("x.json", json.dumps(document)))

    def test_json_that_cannot_be_read_fails_closed(self):
        finding = iac_structure.arm_json_finding("x.json", "{ not json")
        self.assertIsNotNone(finding)
        self.assertIn("cannot be decided", finding.message)

    def test_the_repository_check_reports_json_and_jsonc(self):
        template = json.dumps({"contentVersion": "1.0.0.0", "resources": []})
        with Workspace() as w:
            w.write("deploy/main.json", template)
            w.write("deploy/legacy.JSONC", template)
            w.write("examples/minimal/framework-config.json", json.dumps({"name": "x"}))
            self.assertEqual(
                ["deploy/legacy.JSONC", "deploy/main.json"], [f.path for f in w.check()]
            )


class ReauthoringUpstreamIsRefused(unittest.TestCase):
    def test_declaring_an_upstream_type_is_refused(self):
        bicep = "resource law '%s@2023-09-01' = {\n  name: 'x'\n}\n" % WORKSPACE
        findings = findings_for(bicep)
        self.assertEqual(1, len(findings))
        self.assertIn(WORKSPACE, findings[0].message)

    def test_a_type_upstream_does_not_create_passes(self):
        bicep = "resource sa '%s@2023-01-01' = {\n  name: 'x'\n}\n" % NOT_UPSTREAM
        self.assertEqual([], findings_for(bicep))

    def test_an_existing_reference_passes(self):
        bicep = "resource law '%s@2023-09-01' existing = {\n  name: 'x'\n}\n" % WORKSPACE
        self.assertEqual([], findings_for(bicep))

    def test_a_module_passes(self):
        bicep = "module core 'upstream/agent-core.bicep' = {\n  name: 'core'\n}\n"
        self.assertEqual([], findings_for(bicep))

    def test_the_type_is_compared_without_case(self):
        bicep = "resource law '%s@2023-09-01' = {}\n" % WORKSPACE.upper()
        self.assertEqual(1, len(findings_for(bicep)))

    def test_conditional_and_looped_declarations_are_seen(self):
        for bicep in (
            "resource w '%s@2019-05-01' = if (deploy) {\n  name: 'x'\n}\n" % WORKFLOW,
            "resource w '%s@2019-05-01' = [for n in names: {\n  name: n\n}]\n" % WORKFLOW,
            "@description('d')\nresource w '%s@2019-05-01' = {}\n" % WORKFLOW,
        ):
            with self.subTest(bicep=bicep):
                self.assertEqual(1, len(findings_for(bicep)))

    def test_a_child_nested_in_its_parent_is_resolved(self):
        bicep = (
            "resource p '%s@2025-01-01' existing = {\n"
            "  name: 'p'\n"
            "  resource c 'children@2025-01-01' = {\n"
            "    name: 'c'\n"
            "  }\n"
            "}\n" % PARENT
        )
        findings = findings_for(bicep)
        self.assertEqual(1, len(findings))
        self.assertIn(CHILD, findings[0].message)

    def test_nesting_resolves_against_the_right_parent(self):
        bicep = (
            "resource p '%s@2025-01-01' existing = {\n"
            "  name: 'p'\n"
            "}\n"
            "resource q 'Example.Provider/others@2025-01-01' = {\n"
            "  name: 'q'\n"
            "  resource c 'children@2025-01-01' = {}\n"
            "}\n" % PARENT
        )
        self.assertEqual([], findings_for(bicep))

    def test_a_closed_parent_no_longer_encloses(self):
        bicep = (
            "resource p '%s@2025-01-01' existing = {\n"
            "  name: 'p'\n"
            "}\n"
            "resource c 'children@2025-01-01' = {}\n" % PARENT
        )
        findings = findings_for(bicep)
        self.assertEqual(1, len(findings))
        self.assertIn("outside any parent", findings[0].message)

    def test_a_child_declared_with_its_full_type_is_refused(self):
        bicep = "resource c '%s@2025-01-01' = {\n  parent: p\n}\n" % CHILD
        self.assertEqual(1, len(findings_for(bicep)))

    def test_comments_and_strings_are_not_declarations(self):
        for bicep in (
            "// resource law '%s@2023-09-01' = {}\n" % WORKSPACE,
            "/* resource law '%s@2023-09-01' = {} */\n" % WORKSPACE,
            "var s = 'resource law \\'%s@2023-09-01\\''\n" % WORKSPACE,
            "var s = '''\nresource law '%s@2023-09-01' = {}\n'''\n" % WORKSPACE,
            "output resource string = 'x'\n",
        ):
            with self.subTest(bicep=bicep):
                self.assertEqual([], findings_for(bicep))

    def test_an_interpolated_brace_does_not_shift_the_parent(self):
        bicep = (
            "resource p '%s@2025-01-01' existing = {\n"
            "  name: '${prefix}-}{'\n"
            "  resource c 'children@2025-01-01' = {}\n"
            "}\n" % PARENT
        )
        self.assertEqual(1, len(findings_for(bicep)))


class WhatCannotBeResolvedFails(unittest.TestCase):
    def assert_refused(self, bicep, fragment):
        findings = findings_for(bicep)
        self.assertEqual(1, len(findings))
        self.assertIn("cannot be audited offline", findings[0].message)
        self.assertIn(fragment, findings[0].message)

    def test_an_interpolated_type(self):
        self.assert_refused("resource x '${ns}/workspaces@2023-09-01' = {}\n", "interpolated")

    def test_a_type_without_an_api_version(self):
        self.assert_refused("resource x '%s' = {}\n" % WORKSPACE, "API version")

    def test_a_relative_type_with_no_parent(self):
        self.assert_refused("resource x 'children@2025-01-01' = {}\n", "outside any parent")

    def test_a_declaration_with_no_literal_type(self):
        self.assert_refused("resource x existing = {}\n", "no literal type")

    def test_an_unterminated_comment(self):
        self.assert_refused("/* never closed\n", "unterminated")

    def test_the_repository_check_reports_bicep(self):
        with Workspace() as w:
            w.write("deploy/compose/main.bicep", "resource w '%s@2019-05-01' = {}\n" % WORKFLOW)
            w.write("deploy/compose/ok.bicep", "resource w '%s@2019-05-01' existing = {}\n" % WORKFLOW)
            self.assertEqual(["deploy/compose/main.bicep"], [f.path for f in w.check()])


class TheMeasurement(unittest.TestCase):
    def test_measure_lists_created_types_and_where(self):
        with Workspace() as w:
            w.write("bicep/a.bicep", (
                "resource law '%s@2023-09-01' = {}\n"
                "resource p '%s@2025-01-01' existing = {\n"
                "  resource c 'children@2025-01-01' = {}\n"
                "}\n" % (WORKSPACE, PARENT)
            ))
            w.write("bicep/b.bicep", "resource law '%s@2023-09-01' = {}\n" % WORKSPACE)
            w.write("bicep/notes.md", "resource law '%s@2023-09-01' = {}\n" % WORKFLOW)
            measured = iac_structure.measure(w.root)
        self.assertEqual(
            [
                {"type": CHILD, "declaredIn": ["bicep/a.bicep"]},
                {"type": WORKSPACE, "declaredIn": ["bicep/a.bicep", "bicep/b.bicep"]},
            ],
            measured,
        )


class TheMeasuredListIsTrustedOnlyWhenWellFormed(unittest.TestCase):
    COMMIT = "a" * 40

    def load(self, document, commit=COMMIT):
        with Workspace() as w:
            w.write("deploy/upstream.lock", json.dumps({"upstream": {"commit": commit}}))
            w.write("deploy/upstream-resource-types.json", json.dumps(document))
            return iac_structure.load_upstream_types(w.root)

    def document(self, **changes):
        document = {
            "$comment": "c",
            "upstreamCommit": self.COMMIT,
            "measurement": "m",
            "resourceTypes": [{"type": WORKSPACE, "declaredIn": ["bicep/a.bicep"]}],
        }
        document.update(changes)
        return document

    def test_a_well_formed_list_loads(self):
        self.assertEqual([WORKSPACE], self.load(self.document()))

    def test_a_list_measured_at_another_commit_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Re-measure"):
            self.load(self.document(), commit="b" * 40)

    def test_malformed_lists_are_refused(self):
        entry = {"type": WORKSPACE, "declaredIn": ["bicep/a.bicep"]}
        for changes in (
            {"resourceTypes": []},
            {"resourceTypes": [entry, dict(entry, type=WORKSPACE.lower())]},
            {"resourceTypes": [{"type": "workspaces", "declaredIn": ["a"]}]},
            {"resourceTypes": [{"type": WORKSPACE, "declaredIn": []}]},
            {"resourceTypes": [dict(entry, extra=True)]},
            {"upstreamCommit": "main"},
            {"extra": True},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.load(self.document(**changes))


class TheCheckRunsWithNoCredentials(unittest.TestCase):
    def test_the_check_opens_no_connection(self):
        def refuse(*_args, **_kwargs):
            raise AssertionError("the structural check attempted a network connection")

        environment = {
            k: v for k, v in os.environ.items() if not k.upper().startswith(("AZURE", "ARM_"))
        }
        with Workspace() as w:
            w.write("deploy/main.tf", "")
            with mock.patch.object(socket, "socket", refuse), mock.patch.object(
                socket, "create_connection", refuse
            ), mock.patch.dict(os.environ, environment, clear=True):
                self.assertEqual(1, len(w.check()))

    def test_the_module_imports_no_process_or_network_layer(self):
        with open(iac_structure.__file__, encoding="utf-8") as handle:
            source = handle.read()
        for module in ("subprocess", "socket", "urllib", "http", "broker", "requests"):
            with self.subTest(module=module):
                self.assertNotRegex(source, r"(?m)^\s*(import|from)\s+(zeroops\.)?%s\b" % module)


if __name__ == "__main__":
    unittest.main()

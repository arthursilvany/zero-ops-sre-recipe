#!/usr/bin/env python3
"""NEG-A: every role definition in the compiled deployment output is read-only.

This is the evidence for User Story 5 acceptance criterion 4 and the offline
part of CC-009 (FR-33, SEC-001 layer one). The fixtures are compiled ARM
templates built in memory, shaped the way the Bicep build emits them. They are
not committed as JSON files because hand-authored ARM JSON in the repository is
what T5.02 forbids.

Every rejection pairs with a control that changes only the role definition
identifier and passes, so each test shows the audit can both accept and refuse.
A check only ever shown rejecting is not known to accept anything.

Run with:
    python -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import io
import json
import os
import socket
import sys
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from zeroops import role_audit  # noqa: E402
from zeroops import validate  # noqa: E402

# Stated independently of the allow-list under test, so no assertion here is
# true by construction.
READER = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
CONTRIBUTOR = "b24988ac-6180-42a0-ab88-20f7382dd24c"
OWNER = "8e3af657-a8ff-443c-a75c-2fe8c4bcb635"
# The built-in role that administers role assignments. Named by its initials
# because the scanner reads a long name ending in a key-like value as a secret.
UAA_ROLE = "18d7d88d-d35e-4fb5-a5c3-7773c20a72d9"
# A built-in role that writes to the resource it is scoped to, and lists its
# secrets. The pinned upstream template grants it to the agent's own identity.
AGENT_ADMINISTRATOR = "e79298df-d852-4c6d-84f9-5d13249d1e55"

SCHEMA = "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"


def by_resource_id(guid):
    return "[resourceId('Microsoft.Authorization/roleDefinitions', '%s')]" % guid


def by_subscription_resource_id(guid):
    return (
        "[subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '%s')]"
        % guid
    )


def by_literal_path(guid):
    return (
        "/subscriptions/00000000-0000-0000-0000-000000000000/providers/"
        "Microsoft.Authorization/roleDefinitions/%s" % guid
    )


def assignment(role_definition_id, **extra):
    resource = {
        "type": "Microsoft.Authorization/roleAssignments",
        "apiVersion": "2022-04-01",
        "name": "[guid(resourceGroup().id, 'example')]",
        "properties": {
            "roleDefinitionId": role_definition_id,
            "principalId": "[parameters('principalId')]",
            "principalType": "ServicePrincipal",
        },
    }
    resource.update(extra)
    return resource


def template(*resources, **extra):
    document = {
        "$schema": SCHEMA,
        "contentVersion": "1.0.0.0",
        "parameters": {"principalId": {"type": "string"}},
        "resources": list(resources),
    }
    document.update(extra)
    return document


def nested(inner):
    return {
        "type": "Microsoft.Resources/deployments",
        "apiVersion": "2022-09-01",
        "name": "rbac",
        "properties": {
            "expressionEvaluationOptions": {"scope": "inner"},
            "mode": "Incremental",
            "template": inner,
        },
    }


def audit(document):
    return role_audit.audit(document)


class TheAcceptanceCriterion(unittest.TestCase):
    """Criterion 4 as written: a Contributor identifier added to a fixture fails."""

    def test_a_reader_assignment_passes(self):
        findings, count = audit(template(assignment(by_resource_id(READER))))
        self.assertEqual([], findings)
        self.assertEqual(1, count)

    def test_adding_contributor_to_the_same_fixture_fails(self):
        document = template(
            assignment(by_resource_id(READER)),
            assignment(by_resource_id(CONTRIBUTOR)),
        )
        findings, count = audit(document)
        self.assertEqual(2, count)
        self.assertEqual([CONTRIBUTOR], [f.role_definition_id for f in findings])
        self.assertEqual("/resources/1/properties/roleDefinitionId", findings[0].pointer)

    def test_every_privileged_built_in_fails(self):
        for guid in (CONTRIBUTOR, OWNER, UAA_ROLE, AGENT_ADMINISTRATOR):
            with self.subTest(guid=guid):
                findings, _ = audit(template(assignment(by_resource_id(guid))))
                self.assertEqual([guid], [f.role_definition_id for f in findings])


class EveryResolvableFormIsJudged(unittest.TestCase):
    """Each spelling ARM uses for a role definition, refused and accepted."""

    FORMS = {
        "resourceId": by_resource_id,
        "subscriptionResourceId": by_subscription_resource_id,
        "literal path": by_literal_path,
    }

    def test_contributor_fails_in_every_form(self):
        for name, form in self.FORMS.items():
            with self.subTest(form=name):
                findings, _ = audit(template(assignment(form(CONTRIBUTOR))))
                self.assertEqual([CONTRIBUTOR], [f.role_definition_id for f in findings])

    def test_reader_passes_in_every_form(self):
        for name, form in self.FORMS.items():
            with self.subTest(form=name):
                findings, _ = audit(template(assignment(form(READER))))
                self.assertEqual([], findings)

    def test_uppercase_identifiers_are_compared_case_insensitively(self):
        findings, _ = audit(template(assignment(by_resource_id(CONTRIBUTOR.upper()))))
        self.assertEqual([CONTRIBUTOR], [f.role_definition_id for f in findings])
        findings, _ = audit(template(assignment(by_resource_id(READER.upper()))))
        self.assertEqual([], findings)

    def test_an_identifier_held_in_a_variable_is_resolved(self):
        """The shape the pinned upstream module compiles to."""
        expression = (
            "[subscriptionResourceId('Microsoft.Authorization/roleDefinitions', "
            "variables('roleId'))]"
        )
        rejected = template(assignment(expression), variables={"roleId": CONTRIBUTOR})
        accepted = template(assignment(expression), variables={"roleId": READER})
        self.assertEqual(
            [CONTRIBUTOR],
            [f.role_definition_id for f in audit(rejected)[0]],
        )
        self.assertEqual([], audit(accepted)[0])


class WhatCannotBeResolvedFails(unittest.TestCase):
    def test_a_role_from_a_parameter_fails_closed(self):
        document = template(
            assignment(
                "[subscriptionResourceId('Microsoft.Authorization/roleDefinitions', "
                "parameters('roleId'))]"
            ),
            parameters={
                "principalId": {"type": "string"},
                "roleId": {"type": "string", "defaultValue": READER},
            },
        )
        findings, _ = audit(document)
        self.assertEqual(1, len(findings))
        self.assertIn("cannot be resolved offline", findings[0].message)

    def test_a_role_built_with_format_fails_closed(self):
        expression = (
            "[format('/providers/Microsoft.Authorization/roleDefinitions/{0}', '%s')]"
            % READER
        )
        findings, _ = audit(template(assignment(expression)))
        self.assertTrue(findings)
        self.assertIn("cannot be resolved offline", findings[0].message)

    def test_a_missing_role_definition_fails_closed(self):
        resource = assignment(by_resource_id(READER))
        del resource["properties"]["roleDefinitionId"]
        findings, _ = audit(template(resource))
        self.assertEqual(1, len(findings))

    def test_a_variable_that_is_not_an_identifier_fails_closed(self):
        expression = (
            "[subscriptionResourceId('Microsoft.Authorization/roleDefinitions', "
            "variables('roleId'))]"
        )
        document = template(
            assignment(expression), variables={"roleId": "[parameters('roleId')]"}
        )
        findings, _ = audit(document)
        self.assertEqual(1, len(findings))
        self.assertIn("cannot be resolved offline", findings[0].message)

    def test_a_linked_template_fails_closed(self):
        resource = nested(template())
        del resource["properties"]["template"]
        resource["properties"]["templateLink"] = {"uri": "https://example.invalid/t.json"}
        findings, _ = audit(template(resource))
        self.assertEqual(["/resources/0/properties/templateLink"], [f.pointer for f in findings])

    def test_a_custom_role_definition_fails(self):
        custom = {
            "type": "Microsoft.Authorization/roleDefinitions",
            "apiVersion": "2022-04-01",
            "name": "[guid('custom')]",
            "properties": {"permissions": [{"actions": ["*/read"]}]},
        }
        findings, _ = audit(template(custom))
        self.assertEqual(1, len(findings))
        self.assertIn("custom role definition", findings[0].message)


class AConditionDoesNotHideAGrant(unittest.TestCase):
    """The pinned upstream module grants Contributor when a parameter reads
    High. The audit cannot see the parameter file, so the grant is judged."""

    def test_a_conditional_contributor_fails_even_when_the_condition_is_false(self):
        for condition in ("[equals(parameters('accessLevel'), 'High')]", False):
            with self.subTest(condition=condition):
                document = template(
                    assignment(by_resource_id(CONTRIBUTOR), condition=condition)
                )
                findings, count = audit(document)
                self.assertEqual(1, count, "the conditional grant was not read")
                self.assertEqual([CONTRIBUTOR], [f.role_definition_id for f in findings])

    def test_a_conditional_reader_passes(self):
        document = template(assignment(by_resource_id(READER), condition=False))
        self.assertEqual(([], 1), audit(document))


class NestedAndAlternativeLayoutsAreRead(unittest.TestCase):
    def test_a_grant_inside_a_nested_deployment_fails(self):
        inner = template(assignment(by_resource_id(CONTRIBUTOR)))
        findings, count = audit(template(nested(inner)))
        self.assertEqual(1, count)
        self.assertEqual(
            "/resources/0/properties/template/resources/0/properties/roleDefinitionId",
            findings[0].pointer,
        )

    def test_a_reader_inside_a_nested_deployment_passes(self):
        inner = template(assignment(by_resource_id(READER)))
        self.assertEqual([], audit(template(nested(inner)))[0])

    def test_two_levels_of_nesting_are_read(self):
        inner = template(nested(template(assignment(by_resource_id(OWNER)))))
        findings, _ = audit(template(nested(inner)))
        self.assertEqual([OWNER], [f.role_definition_id for f in findings])

    def test_symbolic_name_resources_are_read(self):
        """languageVersion 2.0 emits resources as an object, not a list."""
        document = template(languageVersion="2.0")
        document["resources"] = {
            "reader": assignment(by_resource_id(READER)),
            "contributor": assignment(by_resource_id(CONTRIBUTOR)),
        }
        findings, count = audit(document)
        self.assertEqual(2, count)
        self.assertEqual(
            ["/resources/contributor/properties/roleDefinitionId"],
            [f.pointer for f in findings],
        )

    def test_an_extension_resource_type_is_recognised(self):
        resource = assignment(by_resource_id(CONTRIBUTOR))
        resource["type"] = "Microsoft.Web/sites/providers/Microsoft.Authorization/roleAssignments"
        self.assertEqual(1, audit(template(resource))[1])
        self.assertTrue(audit(template(resource))[0])

    def test_a_child_resource_grant_is_read(self):
        parent = {
            "type": "Microsoft.Example/things",
            "apiVersion": "2020-01-01",
            "name": "thing",
            "resources": [assignment(by_resource_id(CONTRIBUTOR))],
        }
        self.assertTrue(audit(template(parent))[0])


class AReferenceOutsideAnAssignmentIsSeen(unittest.TestCase):
    """An identifier passed as a value, held in a variable or exposed in an
    output is outside every role assignment, and is still judged."""

    def test_a_privileged_reference_in_a_nested_parameter_value_fails(self):
        resource = nested(template())
        resource["properties"]["parameters"] = {
            "roleId": {"value": by_subscription_resource_id(CONTRIBUTOR)}
        }
        findings, _ = audit(template(resource))
        self.assertEqual([CONTRIBUTOR], [f.role_definition_id for f in findings])

    def test_a_reader_reference_in_an_output_passes(self):
        document = template(
            outputs={"role": {"type": "string", "value": by_resource_id(READER)}}
        )
        self.assertEqual([], audit(document)[0])

    def test_a_privileged_reference_in_an_output_fails(self):
        document = template(
            outputs={"role": {"type": "string", "value": by_resource_id(OWNER)}}
        )
        self.assertEqual([OWNER], [f.role_definition_id for f in audit(document)[0]])

    def test_a_grant_is_reported_once_not_twice(self):
        findings, _ = audit(template(assignment(by_resource_id(CONTRIBUTOR))))
        self.assertEqual(1, len(findings))


class NothingPassesVacuously(unittest.TestCase):
    def test_a_document_that_is_not_a_compiled_template_fails(self):
        for document in (
            {"resources": [assignment(by_resource_id(READER))]},
            {"$schema": "https://example.invalid/parameters.json#", "parameters": {}},
            [],
        ):
            with self.subTest(document=str(document)[:40]):
                findings, _ = audit(document)
                self.assertEqual(["/$schema"], [f.pointer for f in findings])

    def test_a_template_that_grants_nothing_passes_with_a_count_of_zero(self):
        findings, count = audit(template())
        self.assertEqual(([], 0), (findings, count))

    def test_an_empty_allow_list_admits_nothing(self):
        """Control on the allow-list itself: the Reader pass above comes from
        the list, not from the audit admitting Reader on its own."""
        findings, _ = role_audit.audit(
            template(assignment(by_resource_id(READER))), {"roles": []}
        )
        self.assertEqual([READER], [f.role_definition_id for f in findings])


class TheAuditRunsWithNoCredentials(unittest.TestCase):
    """CC-009 requires the offline half to need nothing from a subscription."""

    def test_the_audit_opens_no_connection(self):
        def refuse(*_args, **_kwargs):
            raise AssertionError("the role audit attempted a network connection")

        environment = {
            k: v for k, v in os.environ.items() if not k.upper().startswith(("AZURE", "ARM_"))
        }
        document = template(
            assignment(by_resource_id(READER)), assignment(by_resource_id(CONTRIBUTOR))
        )
        with mock.patch.object(socket, "socket", refuse), mock.patch.object(
            socket, "create_connection", refuse
        ), mock.patch.dict(os.environ, environment, clear=True):
            findings, _ = role_audit.audit(document)
        self.assertEqual([CONTRIBUTOR], [f.role_definition_id for f in findings])

    def test_the_module_imports_no_process_or_network_layer(self):
        path = role_audit.__file__
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        for module in ("subprocess", "socket", "urllib", "http", "broker", "requests"):
            with self.subTest(module=module):
                self.assertNotRegex(source, r"(?m)^\s*(import|from)\s+(zeroops\.)?%s\b" % module)


class TheCommandReportsTheVerdict(unittest.TestCase):
    def run_command(self, document):
        import tempfile

        handle, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(document, stream)
            out, err = io.StringIO(), io.StringIO()
            with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
                code = validate.main(["audit-roles", path])
            return code, out.getvalue(), err.getvalue()
        finally:
            os.remove(path)

    def test_a_contributor_grant_exits_non_zero_and_names_the_location(self):
        code, _, err = self.run_command(template(assignment(by_resource_id(CONTRIBUTOR))))
        self.assertEqual(role_audit.EXIT_REJECTED, code)
        self.assertIn(CONTRIBUTOR, err)
        self.assertIn("#/resources/0/properties/roleDefinitionId", err)

    def test_a_reader_grant_exits_zero_and_counts_what_it_read(self):
        code, out, _ = self.run_command(template(assignment(by_resource_id(READER))))
        self.assertEqual(role_audit.EXIT_OK, code)
        self.assertIn("1 role assignment(s)", out)

    def test_an_unreadable_target_is_a_usage_error(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            code = validate.main(["audit-roles", os.path.join(REPO_ROOT, "no-such.json")])
        self.assertEqual(role_audit.EXIT_USAGE, code)


if __name__ == "__main__":
    unittest.main()

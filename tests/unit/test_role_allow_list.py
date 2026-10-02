"""The read-only role allow-list, and the rule its schema cannot express.

The schema requires every role to record its measured permissions and to carry
its accepted non-read permissions, even when that list is empty. What it cannot
say is that the two agree: that every non-read permission a role holds is
accepted by name, that nothing is accepted the role does not hold, and that no
acceptance takes a shape that would admit writes broadly. That is
`role_audit.allow_list_findings`, exercised here against mutated copies of the
committed list so every rule is shown failing and the committed list passing.
"""

import copy
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from zeroops import core_paths, role_audit, validate  # noqa: E402

READER = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
# Identifiers that must never appear, stated here rather than read from the
# list under test.
PRIVILEGED = {
    "b24988ac-6180-42a0-ab88-20f7382dd24c": "Contributor",
    "8e3af657-a8ff-443c-a75c-2fe8c4bcb635": "Owner",
    "18d7d88d-d35e-4fb5-a5c3-7773c20a72d9": "User Access Administrator",
    "e79298df-d852-4c6d-84f9-5d13249d1e55": "agent administrator",
}


def path_of(relative):
    return os.path.join(REPO_ROOT, relative.replace("/", os.sep))


class TheCommittedList(unittest.TestCase):
    def setUp(self):
        self.allow_list = role_audit.load_allow_list()

    def test_it_validates_against_its_schema_including_the_semantic_rule(self):
        _artifact, findings = validate.validate(path_of(role_audit.ALLOW_LIST_PATH))
        self.assertEqual([], [str(f) for f in findings])

    def test_reader_is_listed_with_no_accepted_exception(self):
        reader = [r for r in self.allow_list["roles"] if r["roleDefinitionId"] == READER]
        self.assertEqual(1, len(reader))
        self.assertEqual(["*/read"], reader[0]["actions"])
        self.assertEqual([], reader[0]["acceptedNonReadActions"])
        self.assertEqual([], reader[0]["acceptedNonReadDataActions"])

    def test_no_privileged_role_is_listed(self):
        listed = role_audit.allowed_identifiers(self.allow_list)
        for guid, name in PRIVILEGED.items():
            with self.subTest(role=name):
                self.assertNotIn(guid, listed)

    def test_every_listed_role_holds_no_write_or_delete(self):
        for role in self.allow_list["roles"]:
            for permission in role["actions"] + role["dataActions"]:
                with self.subTest(role=role["roleName"], permission=permission):
                    self.assertNotRegex(permission.lower(), r"(^\*$|/write$|/delete$)")

    def test_the_core_declaration_covers_the_list(self):
        declaration = core_paths.load_declaration(REPO_ROOT)
        core = [entry["path"] for entry in declaration["categories"]["core"]]
        self.assertIn("core/policy/", core)
        self.assertTrue(role_audit.ALLOW_LIST_PATH.startswith("core/policy/"))


class TheSemanticRuleFails(unittest.TestCase):
    def setUp(self):
        self.allow_list = copy.deepcopy(role_audit.load_allow_list())

    def role(self, name):
        return [r for r in self.allow_list["roles"] if r["roleName"] == name][0]

    def findings(self):
        return [f.message for f in role_audit.allow_list_findings(self.allow_list)]

    def test_control_the_committed_list_has_no_finding(self):
        self.assertEqual([], self.findings())

    def test_an_unaccepted_non_read_action(self):
        self.role("Reader")["actions"].append("Microsoft.Example/things/restart/action")
        self.assertEqual(1, len(self.findings()))
        self.assertIn("is not a read", self.findings()[0])

    def test_an_unaccepted_non_read_data_action(self):
        self.role("Reader")["dataActions"].append("Microsoft.Example/blobs/write")
        self.assertIn("acceptedNonReadDataActions", self.findings()[0])

    def test_an_acceptance_for_a_permission_the_role_does_not_hold(self):
        self.role("Reader")["acceptedNonReadActions"].append(
            {"permission": "Microsoft.Support/*", "reason": "x" * 40}
        )
        self.assertIn("was not recorded holding it", self.findings()[0])

    def test_a_duplicate_role(self):
        self.allow_list["roles"].append(copy.deepcopy(self.role("Reader")))
        self.assertIn("listed twice", self.findings()[0])

    def test_forbidden_acceptance_shapes(self):
        for permission in (
            "*",
            "*/write",
            "*/action",
            "Microsoft.Authorization/roleAssignments/write",
            "Microsoft.Authorization/*/action",
            "Microsoft.Example/things/write",
            "Microsoft.Example/things/delete",
        ):
            with self.subTest(permission=permission):
                allow_list = copy.deepcopy(self.allow_list)
                reader = [r for r in allow_list["roles"] if r["roleName"] == "Reader"][0]
                reader["actions"].append(permission)
                reader["acceptedNonReadActions"].append(
                    {"permission": permission, "reason": "x" * 40}
                )
                messages = [f.message for f in role_audit.allow_list_findings(allow_list)]
                self.assertEqual(1, len(messages), messages)
                self.assertIn("cannot be accepted on a read-only agent", messages[0])

    def test_a_wildcard_read_is_not_a_forbidden_shape(self):
        """Control for the shape rules: `*/read` is a read and needs no
        acceptance, so the rule is about the verb, not the wildcard."""
        self.assertTrue(role_audit.is_read("*/read"))
        self.assertFalse(role_audit.is_read("*/write"))


if __name__ == "__main__":
    unittest.main()

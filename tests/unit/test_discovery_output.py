"""T4.03 — discovery output hygiene (SEC-007, FR-17, NFR-01).

The three properties under test are the three SEC-007 asks for, plus the one
that makes them worth having: that each check can fail.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from zeroops import discovery, discovery_output  # noqa: E402


# Fixtures are schematic rather than realistic, and deliberately so. A
# realistic resource identifier in a test file is a real-looking identifier in
# a public repository, and the history scanner cannot tell a convincing
# example from a leak. Nothing here needs the realism: redaction is driven by
# the field a value arrives in, not by what the value looks like.
SUBSCRIPTION = "sub-one"


def sample_rows():
    return [
        {
            "id": "/subscriptions/sub-one/rg-one/site-one",
            "name": "site-one",
            "type": "microsoft.web/sites",
            "location": "uksouth",
            "resourceGroup": "rg-one",
            "subscriptionId": SUBSCRIPTION,
            "flagged": True,
        },
        {
            "id": "/subscriptions/sub-one/rg-one/site-two",
            "name": "site-two",
            "type": "microsoft.web/sites",
            "location": "uksouth",
            "resourceGroup": "rg-one",
            "subscriptionId": SUBSCRIPTION,
            "flagged": False,
        },
    ]


def sample_result(denials=()):
    return discovery.DiscoveryResult(
        SUBSCRIPTION,
        rows=sample_rows(),
        denials=list(denials),
    )


def unredacted_document():
    return discovery_output.document(sample_result())


class GitTempRepo(object):
    """A throwaway repository, so ignore behaviour is exercised for real.

    Writing into the real repository to test a write would leave the artifact
    this module exists to keep out of repositories inside one.
    """

    def __init__(self, ignore_lines=(".zeroops/\n", "*.discovery.json\n")):
        self.ignore_lines = ignore_lines

    def __enter__(self):
        self.root = tempfile.mkdtemp(prefix="zeroops-out-")
        subprocess.run(
            ["git", "init", "-q"], cwd=self.root, capture_output=True, text=True
        )
        with open(
            os.path.join(self.root, ".gitignore"), "w", encoding="utf-8", newline="\n"
        ) as handle:
            handle.writelines(self.ignore_lines)
        return self.root

    def __exit__(self, *_):
        shutil.rmtree(self.root, ignore_errors=True)


class TheDefaultPathIsThePathGitIgnores(unittest.TestCase):
    """An ignore rule protects a path something writes to, or nothing at all.

    The existing rule is asserted elsewhere against a hardcoded string. That
    assertion holds whatever default this module picks, so it cannot notice
    the case it exists for: output written somewhere the rule does not reach.
    These ask git about the value the module publishes.
    """

    def check_ignore(self, path, root=REPO_ROOT):
        return subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", os.path.abspath(path)],
            cwd=root,
            capture_output=True,
            text=True,
        ).returncode

    def test_the_published_default_is_ignored_by_this_repository(self):
        self.assertEqual(
            0,
            self.check_ignore(discovery_output.default_path()),
            "discovery output would be committable at its own default path",
        )

    def test_the_redacted_copy_of_the_default_is_also_ignored(self):
        self.assertEqual(
            0,
            self.check_ignore(
                discovery_output.redacted_path_for(discovery_output.default_path())
            ),
        )

    def test_the_check_can_report_not_ignored(self):
        """Without this the assertions above pass on a broken check."""
        self.assertEqual(
            1, self.check_ignore(os.path.join(REPO_ROOT, "contracts", "core-paths.json"))
        )

    def test_path_is_ignored_agrees_with_git(self):
        self.assertTrue(discovery_output.path_is_ignored(discovery_output.default_path()))
        self.assertFalse(
            discovery_output.path_is_ignored(
                os.path.join(REPO_ROOT, "contracts", "core-paths.json")
            )
        )

    def test_a_directory_that_is_not_a_repository_cannot_confirm_protection(self):
        holder = tempfile.mkdtemp(prefix="zeroops-bare-")
        try:
            self.assertFalse(
                discovery_output.path_is_ignored(
                    os.path.join(holder, "discovery.json"), root=holder
                ),
                "an unconfirmed protection must read as absent, not as present",
            )
        finally:
            shutil.rmtree(holder, ignore_errors=True)


class TheHeaderReportsWhatTheFileHolds(unittest.TestCase):
    def test_an_unredacted_document_warns_that_the_values_are_real(self):
        document = unredacted_document()
        self.assertEqual(discovery_output.REDACTION_NONE, document["redaction"])
        self.assertEqual(discovery_output.WARNING_NONE, document["warning"])

    def test_the_two_headers_are_different_text(self):
        """Identical headers would train a reader to skip both."""
        self.assertNotEqual(
            discovery_output.WARNING_NONE, discovery_output.WARNING_REDACTED
        )

    def test_the_unredacted_header_names_the_remedy(self):
        self.assertIn("--redact", discovery_output.WARNING_NONE)

    def test_the_header_is_the_first_thing_in_the_written_file(self):
        with GitTempRepo() as root:
            path = discovery_output.write(unredacted_document(), root=root)
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
        self.assertTrue(
            text.lstrip().startswith('{\n  "warning"'),
            "the warning must be visible without scrolling past an inventory",
        )

    def test_the_stamped_header_follows_the_mode_not_the_caller(self):
        lying = unredacted_document()
        lying["warning"] = "nothing to see here"
        with GitTempRepo() as root:
            path = discovery_output.write(lying, root=root)
            written = discovery_output.read(path)
        self.assertEqual(discovery_output.WARNING_NONE, written["warning"])


class RedactionKeepsOnlyWhatItWasToldToKeep(unittest.TestCase):
    def setUp(self):
        self.source = unredacted_document()
        self.redacted = discovery_output.redact(self.source, salt="fixed-salt")

    def test_types_and_regions_survive(self):
        self.assertEqual("microsoft.web/sites", self.redacted["resources"][0]["type"])
        self.assertEqual("uksouth", self.redacted["resources"][0]["location"])

    def test_identifiers_names_and_groups_do_not(self):
        row = self.redacted["resources"][0]
        for field in ("id", "name", "resourceGroup", "subscriptionId"):
            self.assertRegex(row[field], discovery_output.PSEUDONYM_PATTERN)

    def test_the_subscription_is_replaced(self):
        self.assertRegex(
            self.redacted["subscription"], discovery_output.PSEUDONYM_PATTERN
        )

    def test_booleans_survive_because_they_identify_nobody(self):
        self.assertTrue(self.redacted["resources"][0]["flagged"])
        self.assertFalse(self.redacted["resources"][1]["flagged"])

    def test_equal_values_produce_equal_tokens_inside_one_document(self):
        """Without this a redacted inventory cannot be reasoned about."""
        self.assertEqual(
            self.redacted["resources"][0]["resourceGroup"],
            self.redacted["resources"][1]["resourceGroup"],
        )

    def test_different_values_produce_different_tokens(self):
        self.assertNotEqual(
            self.redacted["resources"][0]["name"],
            self.redacted["resources"][1]["name"],
        )

    def test_a_second_run_cannot_be_lined_up_against_the_first(self):
        other = discovery_output.redact(self.source, salt="another-salt")
        self.assertNotEqual(
            self.redacted["resources"][0]["name"], other["resources"][0]["name"]
        )

    def test_a_default_salt_is_generated_when_none_is_supplied(self):
        first = discovery_output.redact(self.source)
        second = discovery_output.redact(self.source)
        self.assertNotEqual(
            first["resources"][0]["name"], second["resources"][0]["name"]
        )

    def test_a_field_nobody_thought_about_is_redacted_rather_than_kept(self):
        """The direction of the list is the whole control.

        A denylist would pass a newly projected field through untouched, and
        the leak would arrive with the next change to the query catalogue
        rather than with a change to this module.
        """
        self.source["resources"][0]["ownerContact"] = "someone@example.invalid"
        redacted = discovery_output.redact(self.source, salt="fixed-salt")
        self.assertRegex(
            redacted["resources"][0]["ownerContact"],
            discovery_output.PSEUDONYM_PATTERN,
        )

    def test_a_nested_value_is_reached(self):
        self.source["resources"][0]["properties"] = {"host": "host-one"}
        redacted = discovery_output.redact(self.source, salt="fixed-salt")
        self.assertRegex(
            redacted["resources"][0]["properties"]["host"],
            discovery_output.PSEUDONYM_PATTERN,
        )

    def test_a_list_of_strings_is_reached(self):
        self.source["resources"][0]["aliases"] = ["alias-one", "alias-two"]
        redacted = discovery_output.redact(self.source, salt="fixed-salt")
        for alias in redacted["resources"][0]["aliases"]:
            self.assertRegex(alias, discovery_output.PSEUDONYM_PATTERN)

    def test_the_envelope_is_rebuilt_so_a_stray_field_cannot_ride_along(self):
        self.source["operatorNote"] = "ring me on the usual number"
        redacted = discovery_output.redact(self.source, salt="fixed-salt")
        self.assertNotIn("operatorNote", redacted)

    def test_denials_survive_because_they_name_framework_values(self):
        source = discovery_output.document(
            sample_result(
                denials=[
                    discovery.Denial(
                        discovery.RESOURCES_QUERY,
                        discovery.PERMISSION_FOR[discovery.RESOURCES_QUERY],
                    )
                ]
            )
        )
        redacted = discovery_output.redact(source, salt="fixed-salt")
        self.assertEqual(
            [
                {
                    "query": discovery.RESOURCES_QUERY,
                    "permission": discovery.PERMISSION_FOR[discovery.RESOURCES_QUERY],
                }
            ],
            redacted["denials"],
        )
        self.assertFalse(redacted["complete"])


class TheVerifierCatchesWhatRedactionMissed(unittest.TestCase):
    def test_a_correctly_redacted_document_reports_nothing(self):
        """The control. Without it every assertion below passes on a stub."""
        redacted = discovery_output.redact(unredacted_document(), salt="fixed-salt")
        self.assertEqual([], discovery_output.residual_findings(redacted))

    def test_an_unredacted_string_is_reported_even_though_it_looks_ordinary(self):
        redacted = discovery_output.redact(unredacted_document(), salt="fixed-salt")
        redacted["resources"][0]["name"] = "billing-api"
        findings = discovery_output.residual_findings(redacted)
        self.assertEqual(1, len(findings), findings)
        self.assertIn("/resources/0/name", findings[0])

    def test_an_identifier_shaped_value_is_reported_under_a_preserved_field(self):
        """The allow-list is a judgement about a field, not about a value."""
        redacted = discovery_output.redact(unredacted_document(), salt="fixed-salt")
        redacted["resources"][0]["location"] = (
            "00000000-0000-0000-0000-000000000002"
        )
        findings = discovery_output.residual_findings(redacted)
        self.assertTrue(any("guid" in finding for finding in findings), findings)

    def test_each_shape_can_be_detected(self):
        cases = {
            "guid": "00000000-0000-0000-0000-000000000003",
            "resource group path segment": "/subscriptions/x/resourceGroups/rg-one",
            "electronic mail address": "person@example.invalid",
            "endpoint": "https://example.invalid/path",
            "long hexadecimal run": "a" * 40,
        }
        for label, value in cases.items():
            redacted = discovery_output.redact(unredacted_document(), salt="s")
            redacted["resources"][0]["type"] = value
            findings = discovery_output.residual_findings(redacted)
            self.assertTrue(
                any(label in finding for finding in findings),
                "%s was not detected: %s" % (label, findings),
            )

    def test_the_framework_envelope_does_not_trip_the_verifier(self):
        """The headers and permission strings are written by this framework.

        A verifier that reported them would be switched off by the first
        person who read its output.
        """
        for text in (
            discovery_output.WARNING_NONE,
            discovery_output.WARNING_REDACTED,
        ):
            for _, pattern in discovery_output.IDENTIFIER_SHAPES:
                self.assertIsNone(
                    pattern.search(text), "the header itself matches %r" % pattern
                )
        for permission in discovery.PERMISSION_FOR.values():
            for label, pattern in discovery_output.IDENTIFIER_SHAPES:
                self.assertIsNone(
                    pattern.search(permission),
                    "%s reads as a %s" % (permission, label),
                )


class WritingRefusesRatherThanRepairs(unittest.TestCase):
    def test_an_unredacted_document_goes_to_the_default_path(self):
        with GitTempRepo() as root:
            path = discovery_output.write(unredacted_document(), root=root)
            self.assertEqual(discovery_output.default_path(root), path)
            self.assertTrue(os.path.exists(path))

    def test_an_unredacted_document_is_refused_by_an_unprotected_path(self):
        with GitTempRepo(ignore_lines=("nothing-relevant\n",)) as root:
            target = os.path.join(root, "inventory.json")
            with self.assertRaises(discovery_output.OutputError):
                discovery_output.write(unredacted_document(), path=target, root=root)
            self.assertFalse(
                os.path.exists(target), "the refusal must happen before the open"
            )

    def test_an_unprotected_path_is_allowed_when_the_caller_says_so(self):
        with GitTempRepo(ignore_lines=("nothing-relevant\n",)) as root:
            target = os.path.join(root, "inventory.json")
            discovery_output.write(
                unredacted_document(),
                path=target,
                root=root,
                acknowledge_unignored=True,
            )
            self.assertTrue(os.path.exists(target))

    def test_a_document_that_claims_redaction_falsely_is_not_written(self):
        with GitTempRepo() as root:
            lying = discovery_output.redact(unredacted_document(), salt="s")
            lying["resources"][0]["name"] = "billing-api"
            target = os.path.join(root, "bug-report.json")
            with self.assertRaises(discovery_output.OutputError) as caught:
                discovery_output.write(lying, path=target, root=root)
            self.assertIn("says it is redacted and is not", str(caught.exception))
            self.assertFalse(os.path.exists(target))

    def test_a_redacted_document_needs_no_ignored_path(self):
        """Its safety comes from the content, so the path adds nothing."""
        with GitTempRepo(ignore_lines=("nothing-relevant\n",)) as root:
            target = os.path.join(root, "bug-report.json")
            discovery_output.write(
                discovery_output.redact(unredacted_document(), salt="s"),
                path=target,
                root=root,
            )
            self.assertTrue(os.path.exists(target))

    def test_a_document_declaring_an_unknown_mode_is_refused(self):
        with GitTempRepo() as root:
            document = unredacted_document()
            document["redaction"] = "partial"
            with self.assertRaises(discovery_output.OutputError):
                discovery_output.write(document, root=root)

    def test_the_written_file_ends_with_a_newline(self):
        with GitTempRepo() as root:
            path = discovery_output.write(unredacted_document(), root=root)
            with open(path, "rb") as handle:
                self.assertTrue(handle.read().endswith(b"\n"))

    def test_the_written_file_uses_line_feed_endings(self):
        """ADR-0003 wants this diffable, and a diff across platforms is not."""
        with GitTempRepo() as root:
            path = discovery_output.write(unredacted_document(), root=root)
            with open(path, "rb") as handle:
                self.assertNotIn(b"\r\n", handle.read())


class RedactingAFileOnDisk(unittest.TestCase):
    def test_it_writes_a_redacted_sibling(self):
        with GitTempRepo() as root:
            source = discovery_output.write(unredacted_document(), root=root)
            written = discovery_output.redact_file(source, salt="fixed-salt")
            self.assertEqual(discovery_output.redacted_path_for(source), written)
            document = discovery_output.read(written)
            self.assertEqual(
                discovery_output.REDACTION_PSEUDONYMISED, document["redaction"]
            )
            self.assertEqual([], discovery_output.residual_findings(document))

    def test_the_original_is_left_alone(self):
        with GitTempRepo() as root:
            source = discovery_output.write(unredacted_document(), root=root)
            before = discovery_output.read(source)
            discovery_output.redact_file(source, salt="fixed-salt")
            self.assertEqual(before, discovery_output.read(source))

    def test_redacting_an_already_redacted_file_is_refused(self):
        """A second pass would change every token and lose the joins."""
        with GitTempRepo() as root:
            source = discovery_output.write(unredacted_document(), root=root)
            written = discovery_output.redact_file(source, salt="fixed-salt")
            with self.assertRaises(discovery_output.OutputError):
                discovery_output.redact_file(written)

    def test_the_suffix_replaces_the_extension_rather_than_appending_to_it(self):
        self.assertEqual(
            os.path.join("a", "b.redacted.json"),
            discovery_output.redacted_path_for(os.path.join("a", "b.json")),
        )

    def test_a_path_without_the_extension_still_gets_one(self):
        self.assertEqual("report.redacted.json", discovery_output.redacted_path_for("report"))


class ThePageDocumentsTheMode(unittest.TestCase):
    """A redaction mode nobody can find is not a redaction mode.

    SEC-007 asks for a *documented* one, so the page is part of the control
    and not a description of it.
    """

    @classmethod
    def setUpClass(cls):
        with open(
            os.path.join(REPO_ROOT, "docs", "discovery-output.md"),
            "r",
            encoding="utf-8",
        ) as handle:
            cls.page = handle.read()

    def test_it_names_the_default_path(self):
        self.assertIn(discovery_output.DEFAULT_DIRECTORY, self.page)
        self.assertIn(discovery_output.DEFAULT_FILENAME, self.page)

    def test_it_names_the_command(self):
        self.assertIn("python -m zeroops.discovery_output --redact", self.page)

    def test_it_names_every_preserved_field_so_the_reader_knows_what_travels(self):
        for field in discovery_output.PRESERVED_FIELDS:
            self.assertIn("`%s`" % field, self.page)

    def test_it_carries_no_real_identifier(self):
        """NFR-01. The page is tracked; the artifact it describes is not.

        An identifier-shaped run is allowed only where it is visibly an
        example: an angle-bracket placeholder, or the all-zero illustrative
        identifier. Anything else read from a live tenant fails here.
        """
        for label, pattern in discovery_output.IDENTIFIER_SHAPES:
            for match in pattern.finditer(self.page):
                found = match.group(0)
                self.assertTrue(
                    "0000" in found or "<" in found,
                    "%s reads as a %s and is not marked as an example"
                    % (found, label),
                )


if __name__ == "__main__":
    unittest.main()

"""The tracer bullet's proof: validation must be able to fail.

A gate that has only ever been observed to pass is not known to be a gate. Each
rejection case below starts from the shipped minimal example and changes exactly
one thing, so a failure here identifies the rule that broke rather than the
fixture that drifted.
"""

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
MINIMAL_DIR = os.path.join(REPO_ROOT, "examples", "minimal")
MINIMAL_CONFIG = os.path.join(MINIMAL_DIR, "framework-config.json")
SCHEMA_PATH = os.path.join(REPO_ROOT, "contracts", "schemas", "framework-config.schema.json")
INVALID_FIXTURE = os.path.join(REPO_ROOT, "tests", "fixtures", "framework-config.invalid.json")

if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from zeroops import validate as validator  # noqa: E402


def load_minimal():
    with open(MINIMAL_CONFIG, "r", encoding="utf-8") as handle:
        return json.load(handle)


class SchemaIsWellFormed(unittest.TestCase):
    def test_schema_is_a_legal_2020_12_schema(self):
        from jsonschema import Draft202012Validator

        with open(SCHEMA_PATH, "r", encoding="utf-8") as handle:
            schema = json.load(handle)
        Draft202012Validator.check_schema(schema)

    def test_every_object_forbids_unknown_properties(self):
        """An object that accepts unknown properties silently absorbs typos."""
        with open(SCHEMA_PATH, "r", encoding="utf-8") as handle:
            schema = json.load(handle)

        offenders = []

        def walk(node, pointer):
            if isinstance(node, dict):
                if node.get("type") == "object" and "additionalProperties" not in node:
                    offenders.append(pointer)
                for key, value in node.items():
                    walk(value, "%s/%s" % (pointer, key))
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, "%s/%d" % (pointer, index))

        walk(schema, "")
        self.assertEqual([], offenders)

    def test_no_property_name_is_shaped_like_a_secret(self):
        """SEC-013: an inline secret must be inexpressible, not merely rejected."""
        with open(SCHEMA_PATH, "r", encoding="utf-8") as handle:
            raw = json.load(handle)

        forbidden = ("password", "secret", "apikey", "clientsecret", "token", "connectionstring")
        found = []

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    flat = key.replace("-", "").replace("_", "").lower()
                    if any(term in flat for term in forbidden):
                        found.append(key)
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(raw.get("properties", {}))
        walk(raw.get("$defs", {}))
        self.assertEqual([], found)


class MinimalExampleIsAccepted(unittest.TestCase):
    def test_shipped_example_validates(self):
        artifact, findings = validator.validate(MINIMAL_DIR)
        self.assertEqual(MINIMAL_CONFIG, artifact)
        self.assertEqual([], [f.render(artifact) for f in findings])

    def test_example_is_workload_neutral(self):
        """FR-63 and CC-022: the core ships no workload-type content."""
        with open(MINIMAL_CONFIG, "r", encoding="utf-8") as handle:
            text = handle.read().lower()
        for term in ("aks", "kubernetes", "aro", "vmss"):
            self.assertNotIn(term, text, "minimal example mentions %r" % term)


class RejectionCases(unittest.TestCase):
    """Each case changes exactly one thing in an otherwise valid document."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="zeroops-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def check(self, mutate):
        instance = load_minimal()
        mutate(instance)
        path = os.path.join(self.tmp, "framework-config.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(instance, handle)
        _, findings = validator.validate(path)
        return [(f.pointer, f.message) for f in findings]

    def test_unknown_property_is_rejected_and_located(self):
        findings = self.check(lambda i: i.__setitem__("unknownProperty", "x"))
        self.assertTrue(findings, "an unknown property was accepted")
        pointers = [p for p, _ in findings]
        self.assertIn("/", pointers)
        self.assertTrue(
            any("unknownProperty" in m for _, m in findings),
            "rejection did not name the offending property: %r" % findings,
        )

    def test_nested_unknown_property_is_located_by_pointer(self):
        def mutate(instance):
            instance["environments"][0]["typo"] = "x"

        findings = self.check(mutate)
        self.assertIn("/environments/0", [p for p, _ in findings])

    def test_missing_required_concern_is_rejected(self):
        findings = self.check(lambda i: i.pop("approvalPolicies"))
        self.assertTrue(findings)

    def test_mutating_remediation_mode_is_inexpressible(self):
        findings = self.check(
            lambda i: i["remediationPermissions"].__setitem__("mode", "remediate")
        )
        self.assertTrue(findings, "a mutating remediation mode was accepted")

    def test_self_approval_cannot_be_enabled(self):
        findings = self.check(
            lambda i: i["approvalPolicies"].__setitem__("selfApprovalPermitted", True)
        )
        self.assertTrue(findings, "self-approval was accepted")

    def test_empty_scope_is_rejected(self):
        def mutate(instance):
            instance["workloads"][0]["inScope"] = []

        findings = self.check(mutate)
        self.assertTrue(findings, "a workload observing nothing was accepted")

    def test_dangling_external_reference_is_rejected(self):
        def mutate(instance):
            instance["environments"][0]["subscriptionRef"] = "not-declared"

        findings = self.check(mutate)
        self.assertIn("/environments/0/subscriptionRef", [p for p, _ in findings])

    def test_default_environment_must_exist(self):
        def mutate(instance):
            instance["frameworkDefaults"]["defaultEnvironment"] = "no-such-environment"

        findings = self.check(mutate)
        self.assertIn("/frameworkDefaults/defaultEnvironment", [p for p, _ in findings])

    def test_inverted_observation_period_is_rejected(self):
        def mutate(instance):
            period = instance["frameworkDefaults"]["observationPeriod"]
            period["start"], period["end"] = period["end"], period["start"]

        findings = self.check(mutate)
        self.assertIn("/frameworkDefaults/observationPeriod", [p for p, _ in findings])

    def test_malformed_timestamp_is_rejected(self):
        def mutate(instance):
            instance["frameworkDefaults"]["observationPeriod"]["end"] = "next tuesday"

        findings = self.check(mutate)
        self.assertIn("/frameworkDefaults/observationPeriod/end", [p for p, _ in findings])

    def test_duplicate_environment_names_are_rejected(self):
        def mutate(instance):
            instance["environments"].append(copy.deepcopy(instance["environments"][0]))
            instance["environments"][1]["description"] = "a distinct object, same name"

        findings = self.check(mutate)
        self.assertIn("/environments/1/name", [p for p, _ in findings])

    def test_contradictory_scope_is_rejected(self):
        def mutate(instance):
            entry = copy.deepcopy(instance["workloads"][0]["inScope"][0])
            instance["workloads"][0]["outOfScope"] = [entry]

        findings = self.check(mutate)
        self.assertIn("/workloads/0/outOfScope/0", [p for p, _ in findings])

    def test_error_text_never_echoes_the_supplied_value(self):
        """SEC-017: diagnostics are pasted into issues; values must not ride along."""
        marker = "zz-leaked-value-marker"

        def mutate(instance):
            instance["environments"][0]["subscriptionRef"] = marker

        findings = self.check(mutate)
        self.assertTrue(findings)
        for pointer, message in findings:
            self.assertNotIn(marker, message)
            self.assertNotIn(marker, pointer)


class CommandLineSurface(unittest.TestCase):
    """The shims forward arguments; the exit code is what callers branch on."""

    def run_cli(self, *args):
        env = dict(os.environ)
        env["PYTHONPATH"] = TOOLS_DIR + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run(
            [sys.executable, "-m", "zeroops"] + list(args),
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_valid_example_exits_zero(self):
        result = self.run_cli("validate", MINIMAL_DIR)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_invalid_document_exits_nonzero(self):
        tmp = tempfile.mkdtemp(prefix="zeroops-cli-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "framework-config.json")
        instance = load_minimal()
        instance["unknownProperty"] = "x"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(instance, handle)

        result = self.run_cli("validate", path)
        self.assertEqual(1, result.returncode)
        self.assertIn("unknownProperty", result.stderr)

    def test_missing_artifact_is_a_usage_error_not_a_pass(self):
        result = self.run_cli("validate", os.path.join(self.__class__.__name__, "absent"))
        self.assertEqual(2, result.returncode)

    def test_no_subcommand_prints_help_and_exits_nonzero(self):
        result = self.run_cli()
        self.assertEqual(2, result.returncode)

    def test_output_is_ascii(self):
        """Non-ASCII renders as replacement characters on the Windows console."""
        result = self.run_cli("validate", MINIMAL_DIR)
        result.stdout.encode("ascii")
        result.stderr.encode("ascii")

    def test_on_disk_invalid_fixture_is_rejected(self):
        """The fixture CI hands to the shims must stay invalid."""
        result = self.run_cli("validate", INVALID_FIXTURE)
        self.assertEqual(1, result.returncode, result.stdout)


class PlatformShim(unittest.TestCase):
    """The shim for the running platform must forward arguments and exit codes."""

    def shim(self):
        if os.name == "nt":
            return [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                os.path.join(REPO_ROOT, "bin", "zeroops.ps1"),
            ]
        return [os.path.join(REPO_ROOT, "bin", "zeroops")]

    def run_shim(self, *args):
        return subprocess.run(
            self.shim() + list(args),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def test_shim_accepts_the_minimal_example(self):
        result = self.run_shim("validate", MINIMAL_DIR)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_shim_propagates_a_rejection(self):
        """A shim that swallowed the exit code would make every caller blind."""
        result = self.run_shim("validate", INVALID_FIXTURE)
        self.assertEqual(1, result.returncode, result.stdout)


if __name__ == "__main__":
    unittest.main()

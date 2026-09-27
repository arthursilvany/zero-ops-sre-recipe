"""The static call-site check, NEG-H.

The broker refuses at runtime. A wizard that only fails when a user runs it
has already shipped, so the same rule is applied to the source.

`core/` and `wizard/` do not exist yet, so the real repository cannot
demonstrate either rule firing. Most of what follows runs against synthetic
trees for that reason, and the difference between "the core is clean" and
"there is no core yet" is asserted rather than left to be inferred.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")

if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from zeroops import broker, callsites, core_paths  # noqa: E402

ALLOWED = broker.allowed_verbs()

DECLARATION = {
    "categories": {
        "core": [{"path": "core/policy/", "status": "present", "purpose": "x"}],
        "binding": [{"path": "core/binding/", "status": "present", "purpose": "x"}],
        "frameworkOwned": [{"path": "tools/", "status": "present", "purpose": "x"}],
    },
    "runtimeIdentifiers": [{"term": "irrelevant-here", "reason": "x"}],
    "selfExclusions": [],
}


class Tree(unittest.TestCase):
    def build(self, contents):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        for relative, text in contents.items():
            full = os.path.join(root, relative.replace("/", os.sep))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as handle:
                handle.write(text)
        return root

    def scan(self, contents):
        root = self.build(contents)
        return callsites.scan(root, sorted(contents), DECLARATION, ALLOWED)


class NoCorePathMayInvokeAnything(Tree):
    """Rule one. The rule is about the capability to invoke, not about
    recognising Azure: a list of ways to reach Azure is a list somebody has
    to keep complete, and the day it is not is the day this passes for the
    wrong reason."""

    def test_subprocess_in_a_core_path_is_reported(self):
        problems, _ = self.scan({"core/policy/run.py": "import subprocess\n"})
        self.assertEqual(1, len(problems), problems)
        self.assertIn("core/policy/run.py:1", problems[0])

    def test_a_harmless_looking_subprocess_is_still_reported(self):
        """The control that shows the rule is about capability. A core path
        that can spawn anything can spawn the CLI, so a benign command is not
        an exception."""
        problems, _ = self.scan(
            {"core/policy/run.py": "import subprocess\nsubprocess.run(['echo', 'hi'])\n"}
        )
        self.assertTrue(problems)

    def test_an_azure_sdk_import_is_reported(self):
        problems, _ = self.scan({"core/policy/x.py": "from azure.mgmt import resource\n"})
        self.assertTrue(problems)

    def test_a_credential_import_is_reported(self):
        problems, _ = self.scan(
            {"core/policy/x.py": "import azure.identity as identity\n"}
        )
        self.assertTrue(problems)

    def test_a_powershell_cmdlet_is_reported(self):
        problems, _ = self.scan({"core/policy/x.ps1": "Get-AzResourceGroup\n"})
        self.assertTrue(problems)

    def test_each_marker_is_exercised_on_its_own(self):
        """One example per marker, each chosen so it matches only that marker.

        The scenario tests above use realistic lines, and a realistic line
        trips several markers at once. That hides a broken pattern: delete
        the `azure.identity` marker and `import azure.identity` is still
        caught by the plain-import marker, so nothing fails. The registry is
        total, so each entry has to be shown to work by itself.
        """
        cases = {
            r"\bsubprocess\b": ("x.py", "handle = subprocess\n"),
            r"\bos\.system\b": ("x.py", "os.system\n"),
            r"\bos\.popen\b": ("x.py", "os.popen\n"),
            r"^\s*(?:from|import)\s+azure\b": ("x.py", "import azure\n"),
            r"\bazure\.mgmt\b": ("x.py", "handle = client.azure.mgmt\n"),
            r"\bazure\.identity\b": ("x.py", "handle = client.azure.identity\n"),
            r"(?:Get|New|Set|Remove|Update|Invoke|Start|Stop)-Az[A-Za-z]+": (
                "x.ps1",
                "Get-AzContext\n",
            ),
            r"\baz\s+(?:account|group|resource|role|graph|rest|vm|aks)\b": (
                "x.sh",
                "az account show\n",
            ),
        }
        registry = [pattern for pattern, _reason in callsites.INVOCATION_MARKERS]
        self.assertEqual(
            sorted(registry),
            sorted(cases),
            "a marker was added or renamed without an example of its own",
        )
        for pattern, (name, line) in cases.items():
            with self.subTest(pattern=pattern):
                found = callsites.marker_findings(line)
                matched = [entry[1] for entry in found]
                self.assertEqual(
                    [pattern],
                    matched,
                    "expected only %r to match %r" % (pattern, line),
                )

    def test_a_literal_cli_line_is_reported(self):
        problems, _ = self.scan({"core/policy/x.sh": "az group list\n"})
        self.assertTrue(problems)

    def test_the_binding_layer_is_not_exempt(self):
        """It names the runtime, which is why it exists. That is not a licence
        to invoke it."""
        problems, _ = self.scan({"core/binding/adapter.py": "import subprocess\n"})
        self.assertTrue(problems)

    def test_a_clean_core_path_produces_nothing(self):
        """The control case. A check that reported every file would satisfy
        every assertion above."""
        problems, examined = self.scan(
            {"core/policy/rules.py": "RULES = ['deny-by-default']\n"}
        )
        self.assertEqual([], problems)
        self.assertEqual(1, examined)

    def test_a_file_outside_the_scanned_categories_is_ignored(self):
        """tools/ holds the broker, which is the one place allowed to invoke.
        Scanning it would make the rule unsatisfiable."""
        problems, examined = self.scan({"tools/zeroops/broker.py": "import subprocess\n"})
        self.assertEqual([], problems)
        self.assertEqual(0, examined)

    def test_the_reported_line_number_is_the_offending_one(self):
        problems, _ = self.scan(
            {"core/policy/x.py": "# a comment\n# another\nimport subprocess\n"}
        )
        self.assertIn(":3:", problems[0])

    def test_every_marker_carries_a_reason(self):
        for pattern, reason in callsites.INVOCATION_MARKERS:
            with self.subTest(pattern=pattern):
                self.assertGreater(len(reason), 20)

    def test_the_marker_registry_is_not_empty(self):
        self.assertGreaterEqual(len(callsites.INVOCATION_MARKERS), 6)


class BrokeredCommandsMayNameOnlyAllowedVerbs(Tree):
    def test_a_write_verb_in_a_literal_command_is_reported(self):
        problems, _ = self.scan(
            {"core/policy/x.py": "broker.invoke(['az', 'group', 'delete'])\n"}
        )
        self.assertEqual(1, len(problems), problems)
        self.assertIn("'delete'", problems[0])

    def test_an_allowed_verb_is_accepted(self):
        """The control case."""
        problems, _ = self.scan(
            {"core/policy/x.py": "broker.invoke(['az', 'group', 'show'])\n"}
        )
        self.assertEqual([], problems)

    def test_every_allowed_verb_is_accepted(self):
        for verb in ALLOWED:
            with self.subTest(verb=verb):
                problems, _ = self.scan(
                    {"core/policy/x.py": "broker.invoke(['az', 'g', %r])\n" % verb}
                )
                self.assertEqual([], problems)

    def test_a_bare_plan_call_is_read_too(self):
        problems, _ = self.scan(
            {"core/policy/x.py": "plan(['az', 'group', 'create'])\n"}
        )
        self.assertTrue(problems)

    def test_options_do_not_become_the_verb(self):
        problems, _ = self.scan(
            {"core/policy/x.py": "broker.invoke(['az', 'g', 'show', '--name', 'delete'])\n"}
        )
        self.assertEqual([], problems)

    def test_a_command_with_no_verb_is_reported(self):
        problems, _ = self.scan({"core/policy/x.py": "broker.invoke(['az'])\n"})
        self.assertTrue(problems)

    def test_a_command_with_no_verb_is_reported_as_having_no_verb(self):
        """Not as a disallowed verb. If the program name were read as a verb
        the message would say `'az'` is not on the allow-list, which sends a
        reader looking for a verb that was never there."""
        problems, _ = self.scan({"core/policy/x.py": "broker.invoke(['az'])\n"})
        self.assertEqual(1, len(problems), problems)
        self.assertIn("no verb at all", problems[0])
        self.assertNotIn("'az'", problems[0])

    def test_a_disallowed_verb_is_not_reported_as_having_no_verb(self):
        """The counterpart. Without it a single message covering both cases
        would satisfy the assertion above."""
        problems, _ = self.scan(
            {"core/policy/x.py": "broker.invoke(['az', 'group', 'delete'])\n"}
        )
        self.assertNotIn("no verb at all", problems[0])
        self.assertIn("allow-list", problems[0])

    def test_only_options_after_the_program_name_is_reported(self):
        problems, _ = self.scan(
            {"core/policy/x.py": "broker.invoke(['az', '--version'])\n"}
        )
        self.assertEqual(1, len(problems), problems)
        self.assertIn("no verb at all", problems[0])

    def test_an_argument_that_is_not_a_sequence_is_not_read(self):
        """`broker.invoke(command)` where the command is a variable. The
        reader must decline rather than reach into a node that has no
        elements."""
        problems, _ = self.scan({"core/policy/x.py": "broker.invoke(command)\n"})
        self.assertEqual([], problems)

    def test_a_string_argument_is_not_read_as_a_command(self):
        """The verb reader declines a string. Rule one still catches this
        line, which is the point: the two rules cover each other."""
        text = "broker.invoke('az group delete')\n"
        self.assertEqual([], callsites.verb_findings(text, ALLOWED))
        problems, _ = self.scan({"core/policy/x.py": text})
        self.assertEqual(1, len(problems), problems)
        self.assertIn("literal Azure CLI command line", problems[0])

    def test_a_runtime_assembled_command_is_not_guessed_at(self):
        """It cannot be read statically, and pretending otherwise would
        produce findings nobody can act on. Rule one is what covers this
        case: a core path has no way to run the command it assembled."""
        problems, _ = self.scan(
            {"core/policy/x.py": "broker.invoke(['az', group, verb])\n"}
        )
        self.assertEqual([], problems)

    def test_an_unparsable_file_does_not_crash_the_verb_reader(self):
        problems, _ = self.scan({"core/policy/x.py": "def (:\n"})
        self.assertEqual([], problems)

    def test_a_call_to_something_else_named_invoke_is_read(self):
        """Deliberate. Narrowing to `broker.invoke` would let a wrapper hide
        the command, and a false finding here costs a rename."""
        problems, _ = self.scan(
            {"core/policy/x.py": "helper.invoke(['az', 'group', 'delete'])\n"}
        )
        self.assertTrue(problems)


class TheGateRunsTheCheck(unittest.TestCase):
    """check-core is where this runs. A check wired nowhere is a function.

    The obvious test calls `check_call_sites` directly, and it is worthless:
    delete the call from `check()` and it still passes. These go through the
    real entry point.
    """

    def declaration(self):
        """The real declaration with the core and binding paths swapped for
        synthetic ones. Built from the real file rather than by hand so it
        stays schema-valid; `check()` stops at a schema failure, and a test
        that tripped that would report nothing about call sites."""
        declaration = core_paths.load_declaration(REPO_ROOT)
        declaration["categories"]["core"] = [
            {"path": "core/policy/", "status": "present", "purpose": "synthetic"}
        ]
        declaration["categories"]["binding"] = [
            {"path": "core/binding/", "status": "present", "purpose": "synthetic"}
        ]
        return declaration

    def synthetic_repo(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, "core", "policy"))
        schema = os.path.join(root, core_paths.SCHEMA_PATH.replace("/", os.sep))
        os.makedirs(os.path.dirname(schema), exist_ok=True)
        shutil.copyfile(
            os.path.join(REPO_ROOT, core_paths.SCHEMA_PATH.replace("/", os.sep)),
            schema,
        )
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        return root

    def write(self, root, relative, text):
        full = os.path.join(root, relative.replace("/", os.sep))
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_the_gate_reports_a_planted_violation(self):
        root = self.synthetic_repo()
        self.write(root, "core/policy/x.py", "import subprocess\n")
        problems = core_paths.check(root=root, declaration=self.declaration())
        offending = [p for p in problems if "core/policy/x.py" in p]
        self.assertEqual(1, len(offending), problems)
        self.assertIn("subprocess", offending[0])

    def test_the_gate_accepts_a_clean_core_path(self):
        """The control case. A gate that reported every core file would
        satisfy the assertion above."""
        root = self.synthetic_repo()
        self.write(root, "core/policy/x.py", "RULES = ['deny-by-default']\n")
        problems = core_paths.check(root=root, declaration=self.declaration())
        offending = [p for p in problems if "core/policy/x.py" in p]
        self.assertEqual([], offending)

    def test_the_gate_reports_a_disallowed_verb(self):
        root = self.synthetic_repo()
        self.write(root, "core/policy/x.py", "broker.invoke(['az', 'g', 'delete'])\n")
        problems = core_paths.check(root=root, declaration=self.declaration())
        offending = [p for p in problems if "allow-list" in p]
        self.assertEqual(1, len(offending), problems)

    def test_the_real_repository_passes_the_gate(self):
        self.assertEqual([], core_paths.check())


class TheScanReportsWhatItExamined(unittest.TestCase):
    """A scan that examined nothing reports no problems and is
    indistinguishable from a clean repository."""

    def setUp(self):
        self.root = core_paths.repo_root()
        self.files = core_paths.tracked_files(self.root)
        self.declaration = core_paths.load_declaration(self.root)

    def test_this_repository_is_clean(self):
        problems, _ = callsites.scan(
            self.root, self.files, self.declaration, ALLOWED
        )
        self.assertEqual([], problems)

    def test_the_scan_examined_a_meaningful_number_of_files(self):
        _problems, examined = callsites.scan(
            self.root, self.files, self.declaration, ALLOWED
        )
        self.assertGreaterEqual(examined, 15)

    def test_the_gate_runs_the_check(self):
        """check-core is the build gate. A check wired nowhere is a function."""
        problems = []
        examined = core_paths.check_call_sites(
            self.root, self.files, self.declaration, problems
        )
        self.assertEqual([], problems)
        self.assertGreaterEqual(examined, 15)


class OnlyTextIsScanned(Tree):
    def test_a_binary_suffix_is_skipped(self):
        problems, examined = self.scan({"core/policy/logo.png": "import subprocess\n"})
        self.assertEqual([], problems)
        self.assertEqual(0, examined)

    def test_every_scannable_suffix_is_examined(self):
        for suffix in callsites.SCANNABLE_SUFFIXES:
            with self.subTest(suffix=suffix):
                _problems, examined = self.scan({"core/policy/file%s" % suffix: "x\n"})
                self.assertEqual(1, examined)

    def test_the_suffix_list_is_not_empty(self):
        self.assertTrue(callsites.SCANNABLE_SUFFIXES)


if __name__ == "__main__":
    unittest.main()

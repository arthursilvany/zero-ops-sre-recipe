"""The local, credential-free command surface (T1.14).

US-1's independent test is performed by a person on a machine with no Azure
login. That only happens if the command they are told to run exists, is
reachable without installing our package, and is documented in a form that can
be pasted without editing.

Three things are checked here that are easy to let rot and hard to notice:

The command surface and the documentation agree, in both directions. A command
documented but absent sends the reader to a dead end; a command present but
undocumented is a surface nobody reviewed. Only the first is obvious.

The offline guarantees can fail. Scrubbing that removes nothing, and a network
block that blocks nothing, both look exactly like a passing run.

Discovery is non-vacuous. Zero tests discovered is the failure mode this whole
repository has hit seven times, so the command that runs the suite refuses to
report success having run nothing.
"""

import io
import os
import re
import subprocess
import sys
import unittest

from zeroops import core_paths, localtest, validate

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMMANDS_DOC = os.path.join(REPO_ROOT, "docs", "commands.md")
PLAN = os.path.join(
    REPO_ROOT, "docs", "features", "sre-agent-recipe-framework", "plan.md"
)

# Every subcommand the CLI offers. Stated here rather than derived from the
# parser, so that adding one to the parser without deciding to document it
# fails. A list derived from the thing it checks agrees with it by
# construction and checks nothing.
EXPECTED_COMMANDS = {"validate", "check-core", "test", "hash", "audit-roles"}

# The credential-shaped environment the local test run removes, written out
# here rather than read from the registry it checks. A list derived from the
# thing it verifies agrees with it by construction: an entry quietly dropped
# disappears from both sides at once, and the scrub gets weaker while every
# test keeps passing.
EXPECTED_PREFIXES = {"AZURE_", "ARM_", "MSI_", "IDENTITY_"}
EXPECTED_EXACT = {
    "AZURE_CLIENT_ID",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_URL",
}


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def parser_commands():
    return set(_subparsers_action().choices)


def _subparsers_action():
    import argparse

    holder = {}

    original = argparse.ArgumentParser.add_subparsers

    def capture(self, *args, **kwargs):
        action = original(self, *args, **kwargs)
        holder["action"] = action
        return action

    argparse.ArgumentParser.add_subparsers = capture
    stdout, stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    try:
        try:
            validate.main(["--help"])
        except SystemExit:
            pass
    finally:
        sys.stdout, sys.stderr = stdout, stderr
        argparse.ArgumentParser.add_subparsers = original
    return holder["action"]


def parser_flags():
    """Every optional flag each command offers, as {command: {flag}}.

    Derived from the parser rather than listed here on purpose: the point is
    to compare the parser against the documentation, and a list written in
    this file would only compare it against itself.
    """
    out = {}
    for name, sub in _subparsers_action().choices.items():
        flags = set()
        for action in sub._actions:
            for option in action.option_strings:
                if option.startswith("--") and option != "--help":
                    flags.add(option)
        out[name] = flags
    return out


class TheCommandSurfaceIsWhatIsDocumented(unittest.TestCase):
    """Checked in both directions. An undocumented command is a surface nobody
    reviewed, which is the direction that happens without anyone choosing it."""

    def setUp(self):
        self.doc = read(COMMANDS_DOC)

    def test_the_expectation_is_not_empty(self):
        self.assertTrue(EXPECTED_COMMANDS)

    def test_the_parser_offers_exactly_the_expected_commands(self):
        self.assertEqual(parser_commands(), EXPECTED_COMMANDS)

    def test_every_command_appears_in_the_documentation(self):
        for command in EXPECTED_COMMANDS:
            with self.subTest(command=command):
                self.assertIn(command, self.doc)

    def test_every_command_has_a_section_of_its_own(self):
        """A bare substring is too weak to notice a section going missing.
        `hash` matches `--require-hashes` in prose, so a command could lose
        its documentation entirely while the check above still passed.

        A heading naming the command is the property that actually holds:
        each command is explained somewhere a reader can find it.
        """
        headings = [line for line in self.doc.splitlines() if line.startswith("## ")]
        self.assertGreaterEqual(len(headings), len(EXPECTED_COMMANDS))
        for command in EXPECTED_COMMANDS:
            with self.subTest(command=command):
                self.assertTrue(
                    any(command in self.documented_under(heading) for heading in headings),
                    "no section documents %r" % command,
                )

    def documented_under(self, heading):
        """The invocations that appear under one heading."""
        body = self.doc.split(heading, 1)[1].split("\n## ", 1)[0]
        return re.findall(r"bin[\\/]zeroops(?:\.ps1)? (\S+)", body)

    def test_every_documented_invocation_names_a_real_command(self):
        invocations = re.findall(r"bin[\\/]zeroops(?:\.ps1)? (\S+)", self.doc)
        self.assertTrue(invocations, "no invocations found; the check is vacuous")
        for name in invocations:
            with self.subTest(invocation=name):
                if name.startswith("<"):
                    continue
                self.assertIn(name, EXPECTED_COMMANDS)

    def test_the_documentation_does_not_promise_a_pip_install_of_our_package(self):
        """The lock is explicit that the package is not installed. A doc that
        says otherwise sends a reader to a command that cannot work."""
        self.assertNotIn("pip install -e tools", self.doc)

    def install_lines(self):
        """The lines a reader would copy, not the prose about them.

        The distinction is the whole point. Prose explaining why a flag
        matters keeps mentioning the flag after the command has lost it, so a
        search of the whole document reports the control is present while the
        command a reader actually runs no longer carries it.
        """
        return [
            line.strip()
            for line in self.doc.splitlines()
            if "pip install" in line and not line.strip().startswith("`")
        ]

    def test_the_document_shows_exactly_one_install_command(self):
        """A count guard. Zero would make the flag checks vacuous, and more
        than one would let a reader copy whichever came first."""
        self.assertEqual(1, len(self.install_lines()), self.install_lines())

    def test_the_install_command_keeps_both_flags(self):
        """Either flag dropped removes the control and leaves the command
        looking the same."""
        line = self.install_lines()[0]
        self.assertIn("--require-hashes", line)
        self.assertIn("--only-binary=:all:", line)
        self.assertIn("tools/requirements.lock", line)

    def test_the_prose_also_explains_both_flags(self):
        """Separate from the command, and asserted separately. A command with
        the flags and no explanation invites the next reader to drop them."""
        self.assertIn("--require-hashes", self.doc)
        self.assertIn("--only-binary", self.doc)

    def test_the_validator_points_at_the_lock_rather_than_an_editable_install(self):
        source = read(os.path.join(REPO_ROOT, "tools", "zeroops", "validate.py"))
        self.assertNotIn("pip install -e tools", source)
        self.assertIn("--require-hashes", source)


class EveryFlagIsDocumented(unittest.TestCase):
    """Commands were compared against the documentation. Flags were not.

    `--negative` changes which suite a release gate runs. A flag that decides
    what a gate covers is part of the surface a reviewer has to see, and it
    was possible to add one, and to remove one, without the documentation
    disagreeing.
    """

    def setUp(self):
        self.doc = read(COMMANDS_DOC)

    def test_the_expectation_is_not_empty(self):
        """A parser that offered no flags would satisfy the check below
        without anybody documenting anything."""
        flags = parser_flags()
        self.assertTrue(any(flags.values()), flags)

    def test_every_flag_the_parser_offers_appears_in_the_documentation(self):
        for command, flags in sorted(parser_flags().items()):
            for flag in sorted(flags):
                with self.subTest(command=command, flag=flag):
                    self.assertIn(
                        flag,
                        self.doc,
                        "%s %s is offered but documented nowhere" % (command, flag),
                    )

    def test_every_flag_in_a_documented_invocation_is_real(self):
        """The other direction, restricted to lines a reader would copy.

        Prose mentions pip's flags, which are not ours, so the reverse check
        reads only the invocations. A documented flag that the parser does
        not offer sends a reader to a command that fails.
        """
        offered = set()
        for flags in parser_flags().values():
            offered |= flags
        invocations = re.findall(r"bin[\\/]zeroops(?:\.ps1)? ([^\n`]*)", self.doc)
        self.assertTrue(invocations, "no invocations found; the check is vacuous")
        seen = 0
        for line in invocations:
            for flag in re.findall(r"--[a-z][a-z0-9-]*", line):
                seen += 1
                with self.subTest(flag=flag):
                    self.assertIn(flag, offered, "%s is documented but not offered" % flag)
        self.assertGreater(seen, 0, "no flags appear in any invocation")

    def test_the_negative_gate_flag_is_documented_with_its_purpose(self):
        """Named specifically because this one is a release gate. Knowing the
        flag exists is not the same as knowing failing it means a prohibition
        is gone."""
        self.assertIn("--negative", self.doc)

    def test_the_negative_flag_appears_in_a_command_a_reader_would_copy(self):
        """Presence anywhere in the document is too weak, and this repository
        already learned that once with the install flags. Prose explaining why
        a flag matters keeps mentioning it after the invocation has lost it,
        so the document reports the gate exists while the command a reader
        runs no longer reaches it.
        """
        invocations = re.findall(r"bin[\\/]zeroops(?:\.ps1)? ([^\n`]*)", self.doc)
        self.assertTrue(
            any("--negative" in line for line in invocations),
            "--negative is mentioned but never shown in a command: %s" % invocations,
        )


class TheReleaseGateIsWiredIntoCI(unittest.TestCase):
    """A gate nothing runs is a gate.

    The command exists, the suite passes and the documentation describes it.
    None of that makes a pull request fail. The workflow invoking the command
    is the only part that does, and it is a separate file from everything
    above, which is exactly the kind of gap that survives review.
    """

    def setUp(self):
        self.workflow = read(
            os.path.join(REPO_ROOT, ".github", "workflows", "verify.yml")
        )

    def test_a_job_invokes_the_negative_gate(self):
        self.assertIn("test --local --negative", self.workflow)

    def test_the_gate_has_a_job_name_of_its_own(self):
        """Sharing a job with the offline suite would mean a red check could
        not be read as 'a prohibition is gone' without opening the log."""
        self.assertIn("Release gate", self.workflow)

    def test_the_gate_installs_the_reviewed_dependency_closure(self):
        """The same supply-chain flags as every other job. A gate that
        installed dependencies loosely would be the weakest path into CI."""
        self.assertIn("--require-hashes", self.workflow)
        self.assertIn("--only-binary=:all:", self.workflow)

    def test_the_gate_runs_the_shim_rather_than_unittest_directly(self):
        """The command carries the credential scrub, the network refusal and
        the fail-closed discovery checks. Invoking unittest instead would
        leave all three untested in CI while the check still went green."""
        self.assertIn("bin/zeroops test --local --negative", self.workflow)


class TheDocumentedLintCoversEveryMarkdownFile(unittest.TestCase):
    """The lint command carries its own scope, and a scope is a list that
    silently stops being complete.

    It was `docs/**/*.md` and `*.md`, which left `contracts/schema-register.md`
    and `deploy/README.md` unlinted from the day they were written. Nothing
    said so, because a lint that examines fewer files still reports success.
    The scope is now one glob with its exclusions written beside it, so the
    documented command is the only statement of what is covered.
    """

    @staticmethod
    def matches(path, pattern):
        """Glob semantics, not fnmatch semantics.

        fnmatch lets `*` cross a directory separator, so `*.md` would match
        every markdown file in the repository and the coverage assertion
        below would hold no matter what the documented globs said. The
        control case is what caught that.
        """
        parts = []
        index = 0
        while index < len(pattern):
            if pattern.startswith("**/", index):
                parts.append("(?:[^/]+/)*")
                index += 3
            elif pattern.startswith("**", index):
                parts.append(".*")
                index += 2
            elif pattern[index] == "*":
                parts.append("[^/]*")
                index += 1
            else:
                parts.append(re.escape(pattern[index]))
                index += 1
        return re.fullmatch("".join(parts), path) is not None

    def lint_globs(self):
        for line in read(COMMANDS_DOC).splitlines():
            if "markdownlint-cli2" in line and not line.strip().startswith("`"):
                return re.findall(r'"([^"]+)"', line)
        return []

    def covered(self, path):
        included, excluded = [], []
        for pattern in self.lint_globs():
            (excluded if pattern.startswith("!") else included).append(
                pattern.lstrip("!")
            )
        if any(self.matches(path, pattern) for pattern in excluded):
            return False
        return any(self.matches(path, pattern) for pattern in included)

    def tracked_markdown(self):
        root = core_paths.repo_root()
        return [
            path for path in core_paths.tracked_files(root) if path.endswith(".md")
        ]

    def test_the_command_declares_at_least_one_glob(self):
        self.assertTrue(self.lint_globs())

    def test_there_is_markdown_to_cover(self):
        """Without this the assertion below passes over an empty list."""
        self.assertGreater(len(self.tracked_markdown()), 10)

    def test_every_tracked_markdown_file_matches_a_documented_glob(self):
        for path in self.tracked_markdown():
            if path.startswith(".github/"):
                continue
            with self.subTest(path=path):
                self.assertTrue(
                    self.covered(path),
                    "%s is not covered by %s" % (path, self.lint_globs()),
                )

    def test_the_exclusion_is_stated_in_the_command_rather_than_assumed(self):
        """`.github/` carries files this repository did not author and does
        not lint. Skipping them silently and skipping them by an exclusion
        somebody can read are different things."""
        self.assertFalse(self.covered(".github/workflows/notes.md"))

    def test_a_new_top_level_directory_would_be_covered(self):
        """The control, and the point of the change. The previous globs
        listed directories, so every new one started out unlinted."""
        self.assertTrue(self.covered("somewhere/new/notes.md"))


class ThePlanNoLongerDefersWhatExists(unittest.TestCase):
    """A [TBD] marker beside a command that shipped is a claim the repository
    contradicts. The marker's whole job is to be removed."""

    def setUp(self):
        self.plan = read(PLAN)

    def test_the_shipped_commands_carry_no_marker(self):
        for command in ("validate", "test --local"):
            with self.subTest(command=command):
                self.assertNotIn("[TBD until S3-12]", self.plan)

    def test_unshipped_commands_keep_their_markers(self):
        """The control case. Removing every marker would pass the check above
        and would be a lie about commands that do not exist."""
        self.assertIn("[TBD until S3-09]", self.plan)
        self.assertIn("[TBD until S4-06]", self.plan)

    def test_the_name_is_recorded_as_confirmed(self):
        self.assertIn("The `zeroops` name is confirmed", self.plan)

    def test_the_plan_points_at_the_command_documentation(self):
        self.assertIn("docs/commands.md", self.plan)


class TheShimsExistOnBothPlatforms(unittest.TestCase):
    """One shim is a command that works where its author was sitting."""

    def test_both_shims_are_present(self):
        for name in ("zeroops", "zeroops.ps1"):
            with self.subTest(shim=name):
                self.assertTrue(os.path.isfile(os.path.join(REPO_ROOT, "bin", name)))

    def test_neither_shim_carries_behaviour(self):
        """Logic in a shim exists on one platform only, and the two drift the
        first time either is edited. Both stay short enough to read."""
        for name in ("zeroops", "zeroops.ps1"):
            with self.subTest(shim=name):
                body = read(os.path.join(REPO_ROOT, "bin", name))
                lines = [
                    line for line in body.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
                self.assertLessEqual(len(lines), 12)

    def test_both_shims_forward_arguments(self):
        posix = read(os.path.join(REPO_ROOT, "bin", "zeroops"))
        powershell = read(os.path.join(REPO_ROOT, "bin", "zeroops.ps1"))
        self.assertIn('"$@"', posix)
        self.assertIn("@args", powershell)

    def test_the_powershell_shim_propagates_the_exit_code(self):
        """Without this the shim reports success for every failure, which is
        the only bug a shim can really have."""
        powershell = read(os.path.join(REPO_ROOT, "bin", "zeroops.ps1"))
        self.assertIn("exit $LASTEXITCODE", powershell)


class ScrubbingActuallyRemovesThings(unittest.TestCase):
    """A scrub that removes nothing is indistinguishable from a scrub that
    works, from the outside."""

    def test_a_named_variable_is_removed(self):
        environ = {"AZURE_CLIENT_SECRET": "x", "PATH": "/usr/bin"}
        self.assertNotIn("AZURE_CLIENT_SECRET", localtest.scrub_environment(environ))

    def test_an_unrelated_variable_survives(self):
        """The control case. A scrub that removed everything would pass the
        test above and break every run."""
        environ = {"AZURE_CLIENT_SECRET": "x", "PATH": "/usr/bin"}
        self.assertIn("PATH", localtest.scrub_environment(environ))

    def test_every_registered_prefix_is_removed(self):
        for name in EXPECTED_PREFIXES:
            with self.subTest(prefix=name):
                environ = {name + "THING": "x"}
                self.assertEqual(localtest.scrub_environment(environ), {})

    def test_every_registered_exact_name_is_removed(self):
        for name in EXPECTED_EXACT:
            with self.subTest(name=name):
                self.assertEqual(localtest.scrub_environment({name: "x"}), {})

    def test_the_registry_holds_exactly_what_is_expected(self):
        """Stated independently of the registry rather than read from it. A
        test that iterated CREDENTIAL_ENVIRONMENT would agree with it by
        construction: an entry silently dropped would drop from the assertion
        too, and the check would keep passing while the scrub got weaker."""
        prefixes = {n for n, kind, _ in localtest.CREDENTIAL_ENVIRONMENT if kind == "prefix"}
        exact = {n for n, kind, _ in localtest.CREDENTIAL_ENVIRONMENT if kind == "exact"}
        self.assertEqual(prefixes, EXPECTED_PREFIXES)
        self.assertEqual(exact, EXPECTED_EXACT)

    def test_the_pattern_sweep_catches_an_unregistered_name(self):
        """The registry names what is known to matter; the sweep catches what a
        future CI template introduces."""
        for name in ("SOME_VENDOR_TOKEN", "acme_password", "X_API_KEY", "MY_SECRET"):
            with self.subTest(name=name):
                self.assertEqual(localtest.scrub_environment({name: "x"}), {})

    def test_every_registry_entry_carries_a_reason(self):
        self.assertTrue(localtest.CREDENTIAL_ENVIRONMENT)
        for name, kind, reason in localtest.CREDENTIAL_ENVIRONMENT:
            with self.subTest(name=name):
                self.assertIn(kind, ("prefix", "exact"))
                self.assertGreater(len(reason), 20)

    def test_no_registry_entry_is_listed_twice(self):
        names = [n for n, _, _ in localtest.CREDENTIAL_ENVIRONMENT]
        self.assertEqual(len(names), len(set(names)))

    def test_scrubbed_names_reports_what_was_removed(self):
        environ = {"AZURE_TENANT_ID": "x", "PATH": "/usr/bin", "GH_TOKEN": "y"}
        self.assertEqual(
            localtest.scrubbed_names(environ), ["AZURE_TENANT_ID", "GH_TOKEN"]
        )

    def test_scrubbed_names_is_empty_when_nothing_matches(self):
        self.assertEqual(localtest.scrubbed_names({"PATH": "/usr/bin"}), [])


class TheNetworkBlockActuallyBlocks(unittest.TestCase):
    """Asserted in a subprocess, because the patch is global and a test that
    installed it in this process would disarm the network for everything
    running after it."""

    def child(self, body):
        return subprocess.run(
            [sys.executable, "-c", body],
            cwd=REPO_ROOT,
            env=dict(os.environ, PYTHONPATH=os.path.join(REPO_ROOT, "tools")),
            capture_output=True,
            text=True,
        )

    def test_connect_is_refused_after_the_block(self):
        result = self.child(
            "import socket\n"
            "from zeroops import localtest\n"
            "localtest.forbid_network()\n"
            "try:\n"
            "    socket.socket().connect(('127.0.0.1', 9))\n"
            "    print('NOT BLOCKED')\n"
            "except OSError as exc:\n"
            "    print('BLOCKED' if 'refused by' in str(exc) else 'OTHER')\n"
        )
        self.assertIn("BLOCKED", result.stdout)
        self.assertNotIn("NOT BLOCKED", result.stdout)

    def test_create_connection_is_refused(self):
        result = self.child(
            "import socket\n"
            "from zeroops import localtest\n"
            "localtest.forbid_network()\n"
            "try:\n"
            "    socket.create_connection(('127.0.0.1', 9))\n"
            "    print('NOT BLOCKED')\n"
            "except OSError as exc:\n"
            "    print('BLOCKED' if 'refused by' in str(exc) else 'OTHER')\n"
        )
        self.assertIn("BLOCKED", result.stdout)

    def test_connect_ex_is_refused(self):
        """connect_ex returns an error number instead of raising, so a caller
        that used it would get a plausible-looking failure code and carry on.
        It is patched to raise for the same reason connect is."""
        result = self.child(
            "import socket\n"
            "from zeroops import localtest\n"
            "localtest.forbid_network()\n"
            "try:\n"
            "    socket.socket().connect_ex(('127.0.0.1', 9))\n"
            "    print('NOT BLOCKED')\n"
            "except OSError as exc:\n"
            "    print('BLOCKED' if 'refused by' in str(exc) else 'OTHER')\n"
        )
        self.assertIn("BLOCKED", result.stdout)
        self.assertNotIn("NOT BLOCKED", result.stdout)

    def test_a_library_that_goes_through_sockets_is_refused_too(self):
        """Patched at the socket layer rather than higher up, because anything
        higher is one library away from being bypassed."""
        result = self.child(
            "import urllib.request\n"
            "from zeroops import localtest\n"
            "localtest.forbid_network()\n"
            "try:\n"
            "    urllib.request.urlopen('http://127.0.0.1:9', timeout=1)\n"
            "    print('NOT BLOCKED')\n"
            "except Exception as exc:\n"
            "    print('BLOCKED' if 'refused by' in str(exc) else 'OTHER: %s' % exc)\n"
        )
        self.assertIn("BLOCKED", result.stdout)

    def test_a_connection_succeeds_without_the_block(self):
        """The control case. Port 9 on localhost refuses anyway, so without it
        every assertion above could be measuring an unrelated refusal."""
        result = self.child(
            "import socket\n"
            "try:\n"
            "    socket.socket().connect(('127.0.0.1', 9))\n"
            "except OSError as exc:\n"
            "    print('OURS' if 'refused by' in str(exc) else 'THEIRS')\n"
        )
        self.assertIn("THEIRS", result.stdout)


class DiscoveryIsNeverVacuous(unittest.TestCase):
    """Zero tests discovered is the shape of every false green this repository
    has produced. The command that runs the suite refuses to report success
    having run nothing.

    Every fixture below runs in a subprocess. Run in-process, discovery of a
    temporary `tests` package resolves against the one this suite was loaded
    from, so a fixture designed to pass fails on an import collision and a
    fixture designed to fail fails for the wrong reason. Both look like the
    expected outcome from the assertion's side.
    """

    def fixture(self, files):
        import shutil
        import tempfile

        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        tests = os.path.join(root, "tests")
        os.makedirs(tests)
        for name, body in files.items():
            with open(os.path.join(tests, name), "w", encoding="utf-8") as handle:
                handle.write(body)
        return root

    def discover(self, root):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys\n"
                "from zeroops import localtest\n"
                "code, n = localtest.run_in_process(sys.argv[1], stream=sys.stdout)\n"
                "print('RESULT %d %d' % (code, n))\n",
                root,
            ],
            cwd=REPO_ROOT,
            env=dict(os.environ, PYTHONPATH=os.path.join(REPO_ROOT, "tools")),
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        match = re.search(r"RESULT (\d+) (\d+)", output)
        self.assertIsNotNone(match, "child produced no result: %s" % output)
        return int(match.group(1)), int(match.group(2)), output

    PASSING = (
        "import unittest\n"
        "class T(unittest.TestCase):\n"
        "    def test_x(self):\n"
        "        self.assertTrue(True)\n"
    )
    FAILING = (
        "import unittest\n"
        "class T(unittest.TestCase):\n"
        "    def test_x(self):\n"
        "        self.fail('deliberate')\n"
    )

    def test_an_empty_tests_directory_is_a_failure(self):
        code, discovered, output = self.discover(self.fixture({"__init__.py": ""}))
        self.assertNotEqual(code, 0)
        self.assertEqual(discovered, 0)
        self.assertIn("no tests", output)

    def test_a_tests_directory_that_cannot_be_imported_is_a_failure(self):
        """Discovery that cannot start arrives as a traceback rather than a
        result, so it would otherwise be the one way to exit saying neither
        pass nor fail."""
        code, discovered, output = self.discover(self.fixture({}))
        self.assertNotEqual(code, 0)
        self.assertEqual(discovered, 0)
        self.assertIn("could not start", output)

    def test_a_directory_with_one_test_reports_success(self):
        """The control case. A runner that failed on every temporary tree
        would pass both checks above."""
        root = self.fixture({"__init__.py": "", "test_one.py": self.PASSING})
        code, discovered, _ = self.discover(root)
        self.assertEqual(code, 0)
        self.assertEqual(discovered, 1)

    def test_a_failing_test_produces_a_failing_exit(self):
        root = self.fixture({"__init__.py": "", "test_bad.py": self.FAILING})
        code, discovered, output = self.discover(root)
        self.assertEqual(code, 1)
        self.assertEqual(discovered, 1)
        self.assertIn("deliberate", output)

    def test_the_real_suite_discovers_many(self):
        """The control case for the check above."""
        loader = unittest.TestLoader()
        suite = loader.discover(
            os.path.join(REPO_ROOT, "tests"), pattern="test_*.py", top_level_dir=REPO_ROOT
        )
        self.assertGreater(localtest.count_tests(suite), 100)

    def test_count_tests_counts_nested_suites(self):
        inner = unittest.TestSuite([unittest.FunctionTestCase(lambda: None)] * 3)
        outer = unittest.TestSuite([inner, unittest.TestSuite([inner])])
        self.assertEqual(localtest.count_tests(outer), 6)


class TheReleaseGateFailsClosed(unittest.TestCase):
    """`--negative` names a release gate, so every way it could pass having
    checked nothing has to be a failure instead.

    The subprocess pattern is inherited from DiscoveryIsNeverVacuous for the
    same reason: discovery of a temporary `tests` package run in-process
    resolves against the one this suite was loaded from.
    """

    PASSING = (
        "import unittest\n"
        "class T(unittest.TestCase):\n"
        "    def test_x(self):\n"
        "        self.assertTrue(True)\n"
    )
    NO_TEST_CLASS = "VALUE = 1\n"

    def fixture(self, files, area="negative"):
        import shutil
        import tempfile

        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        tests = os.path.join(root, "tests")
        os.makedirs(tests)
        with open(os.path.join(tests, "__init__.py"), "w", encoding="utf-8"):
            pass
        if area is not None:
            target = os.path.join(tests, area)
            os.makedirs(target)
            for name, body in files.items():
                with open(os.path.join(target, name), "w", encoding="utf-8") as handle:
                    handle.write(body)
        return root

    def discover(self, root, area="negative"):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys\n"
                "from zeroops import localtest\n"
                "code, n = localtest.run_in_process(\n"
                "    sys.argv[1], stream=sys.stdout, area=sys.argv[2] or None)\n"
                "print('RESULT %d %d' % (code, n))\n",
                root,
                area or "",
            ],
            cwd=REPO_ROOT,
            env=dict(os.environ, PYTHONPATH=os.path.join(REPO_ROOT, "tools")),
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        match = re.search(r"RESULT (\d+) (\d+)", output)
        self.assertIsNotNone(match, "child produced no result: %s" % output)
        return int(match.group(1)), int(match.group(2)), output

    def test_a_negative_suite_with_one_test_passes(self):
        """The control. A gate that failed on every tree would satisfy every
        assertion below while proving nothing."""
        root = self.fixture({"__init__.py": "", "test_guard.py": self.PASSING})
        code, discovered, output = self.discover(root)
        self.assertEqual(code, 0, output)
        self.assertEqual(discovered, 1)

    def test_a_missing_negative_directory_is_a_failure(self):
        """A gate pointed at a directory somebody moved would otherwise pass
        having run nothing."""
        code, discovered, output = self.discover(self.fixture({}, area=None))
        self.assertNotEqual(code, 0)
        self.assertEqual(discovered, 0)
        self.assertIn("release gate", output)

    def test_an_empty_negative_directory_is_a_failure(self):
        code, discovered, output = self.discover(self.fixture({"__init__.py": ""}))
        self.assertNotEqual(code, 0)
        self.assertIn("no tests", output)

    def test_a_module_that_produces_no_test_is_reported_by_name(self):
        """The realistic way a guard disappears. Not deleted: emptied of its
        last test class, or renamed, which lowers a total nobody compares
        against anything.
        """
        root = self.fixture(
            {
                "__init__.py": "",
                "test_guard.py": self.PASSING,
                "test_gone.py": self.NO_TEST_CLASS,
            }
        )
        code, _, output = self.discover(root)
        self.assertNotEqual(code, 0, output)
        self.assertIn("test_gone", output)
        self.assertIn("produced no test", output)

    def test_the_real_negative_suite_collects_every_module_on_disk(self):
        """Run against this repository rather than a fixture, because the
        fixtures establish the check works and only this establishes it
        holds here."""
        start = localtest.area_directory(REPO_ROOT, localtest.NEGATIVE_AREA)
        suite = unittest.TestLoader().discover(
            start, pattern="test_*.py", top_level_dir=REPO_ROOT
        )
        self.assertEqual([], localtest.uncollected_modules(REPO_ROOT, start, suite))
        self.assertGreater(localtest.count_tests(suite), 100)

    def test_the_uncollected_check_can_detect(self):
        """The control for the assertion above, which is satisfied by a
        function that returns an empty list unconditionally."""
        start = localtest.area_directory(REPO_ROOT, localtest.NEGATIVE_AREA)
        empty = unittest.TestSuite()
        self.assertTrue(localtest.uncollected_modules(REPO_ROOT, start, empty))

    def test_the_negative_area_is_a_real_directory_in_this_repository(self):
        self.assertTrue(
            os.path.isdir(os.path.join(REPO_ROOT, "tests", localtest.NEGATIVE_AREA))
        )


class TheNegativeFlagReachesTheRunner(unittest.TestCase):
    """The gate is only a gate if `--negative` actually narrows the run.

    A flag that parses, is documented, and is named in the workflow while
    silently running the full suite would leave every check above green: the
    suite passes either way. So the flag is followed all the way from argv
    into the argument `run_local` receives, rather than stopping at the
    parser.
    """

    def invoke(self, argv):
        seen = {}

        def stub(pattern, area=None):
            seen["pattern"] = pattern
            seen["area"] = area
            return 0

        original = localtest.run_local
        localtest.run_local = stub
        self.addCleanup(setattr, localtest, "run_local", original)
        code = validate.main(argv)
        self.assertEqual(code, 0)
        self.assertIn("area", seen)
        return seen

    def test_the_flag_selects_the_negative_area(self):
        self.assertEqual(
            self.invoke(["test", "--local", "--negative"])["area"],
            localtest.NEGATIVE_AREA,
        )

    def test_without_the_flag_no_area_is_selected(self):
        """The control. Without it the assertion above would also hold for a
        runner that always ran the negative area."""
        self.assertIsNone(self.invoke(["test", "--local"])["area"])

    def test_the_selected_area_is_not_the_whole_suite(self):
        """`area=None` means the whole tree, so the flag would be a no-op if
        NEGATIVE_AREA were empty or None."""
        self.assertTrue(localtest.NEGATIVE_AREA)


class TheCommandRefusesRatherThanGuesses(unittest.TestCase):
    def test_a_directory_outside_a_checkout_is_refused(self):
        import tempfile

        outside = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, outside, True)
        with self.assertRaises(localtest.LocalTestError) as caught:
            localtest.repository_root(outside)
        self.assertIn("clone", str(caught.exception))

    def test_a_directory_inside_the_checkout_resolves_to_the_root(self):
        """The control case. A finder that refused everywhere would pass the
        test above."""
        found = localtest.repository_root(os.path.join(REPO_ROOT, "tests", "unit"))
        self.assertEqual(os.path.normcase(found), os.path.normcase(REPO_ROOT))

    def test_test_without_local_is_a_usage_error(self):
        stderr = io.StringIO()
        original = sys.stderr
        sys.stderr = stderr
        try:
            code = validate.main(["test"])
        finally:
            sys.stderr = original
        self.assertEqual(code, validate.EXIT_USAGE)
        self.assertIn("--local", stderr.getvalue())

    def test_the_refusal_stays_ascii(self):
        stderr = io.StringIO()
        original = sys.stderr
        sys.stderr = stderr
        try:
            validate.main(["test"])
        finally:
            sys.stderr = original
        stderr.getvalue().encode("ascii")

    def test_the_command_refuses_to_run_inside_its_own_child(self):
        """Without the guard a nested invocation spawns a child that runs the
        suite, which invokes the command, and so on. This is not hypothetical:
        it happened during development and reached four hundred processes
        before it was noticed. The symptom is a machine that stops responding
        rather than a message, which is the worst kind of failure to debug."""
        self.assertTrue(localtest.already_running({localtest.CHILD_FLAG: "1"}))

    def test_the_guard_is_not_always_on(self):
        """The control case. A guard that fired unconditionally would pass the
        test above and make the command unusable."""
        self.assertFalse(localtest.already_running({}))
        self.assertFalse(localtest.already_running({"PATH": "/usr/bin"}))

    def test_an_empty_flag_does_not_arm_the_guard(self):
        """Windows deletes a variable set to the empty string, so an empty
        value is what an absent one looks like on the way past."""
        self.assertFalse(localtest.already_running({localtest.CHILD_FLAG: ""}))

    def test_the_guard_survives_the_environment_being_edited(self):
        """The environment can be edited by the very suite the child is
        running, and a guard the guarded code can switch off is not a guard.
        The module global is what holds when the variable is removed."""
        self.assertFalse(localtest.IN_CHILD)
        localtest.IN_CHILD = True
        self.addCleanup(setattr, localtest, "IN_CHILD", False)
        self.assertTrue(localtest.already_running({}))

    def test_run_local_consults_the_guard_before_anything_else(self):
        """Ordering matters: the guard has to fire before the spawn, not
        after it, and before the checkout search so that a nested run inside a
        temporary directory is still refused as nested."""
        localtest.IN_CHILD = True
        self.addCleanup(setattr, localtest, "IN_CHILD", False)
        with self.assertRaises(localtest.LocalTestError) as caught:
            localtest.run_local(out=io.StringIO(), err=io.StringIO())
        self.assertIn("already running", str(caught.exception))

    def test_the_child_arms_the_guard_for_its_own_process(self):
        """Asserted in a subprocess, because arming it here would disarm the
        command for everything running after this test."""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from zeroops import localtest\n"
                "localtest._child([__import__('sys').argv[1], 'no_such_pattern_*.py'])\n"
                "print('ARMED' if localtest.already_running({}) else 'NOT ARMED')\n",
                REPO_ROOT,
            ],
            cwd=REPO_ROOT,
            env=dict(os.environ, PYTHONPATH=os.path.join(REPO_ROOT, "tools")),
            capture_output=True,
            text=True,
        )
        self.assertIn("ARMED", result.stdout)
        self.assertNotIn("NOT ARMED", result.stdout)


if __name__ == "__main__":
    unittest.main()

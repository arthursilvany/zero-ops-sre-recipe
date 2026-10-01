"""The read-only command broker.

The broker is the only place the core and the wizard reach Azure. Roughly
half of what follows feeds it something it must refuse, because a broker
observed only to accept is not known to restrict anything.

Two properties are checked in a way that does not derive the expectation from
the code being checked. The allow-list is stated again here as a literal, so
renaming a verb in the module cannot rename it in the assertion at the same
moment. And the refusal of an unknown verb is tested with verbs that appear
in neither list, because a denial that depended on recognising a write verb
would permit every verb nobody thought of.
"""

import os
import subprocess
import sys
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")

if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from zeroops import broker  # noqa: E402

# Stated independently of READ_ONLY_VERBS. Deriving this from the module
# would make the two agree by construction: a renamed verb would leave both
# sides and the assertion would still pass.
EXPECTED_VERBS = ("list", "query", "rest", "show", "version")

# The one shape `az rest` is admitted in. Every refusal in TheRestVerbIsAGet
# varies one thing from this, so each one is known to be refused for that
# thing and not for some other part of the command.
REST_GET = ["az", "rest", "--method", "get", "--url", "/subscriptions/x/providers/p"]

# Verbs in neither the allow-list nor the write-list. These are the ones that
# matter: they are what a deny-list approach would let through.
UNCLASSIFIED_VERBS = ("frobnicate", "wait", "download", "export", "connect", "ssh")


class TheAllowListIsWhatItSaysItIs(unittest.TestCase):
    def test_the_expectation_is_not_empty(self):
        self.assertTrue(EXPECTED_VERBS)

    def test_the_allow_list_matches_the_stated_expectation(self):
        self.assertEqual(sorted(EXPECTED_VERBS), sorted(broker.allowed_verbs()))

    def test_every_allowed_verb_records_why_it_is_allowed(self):
        for verb in broker.allowed_verbs():
            with self.subTest(verb=verb):
                reason = broker.reason_for(verb)
                self.assertTrue(reason)
                self.assertGreater(len(reason), 20, "a reason has to say something")

    def test_no_verb_appears_in_both_lists(self):
        """A verb that is both allowed and write-capable would make the
        refusal depend on which list was consulted first."""
        self.assertEqual(
            set(), set(broker.allowed_verbs()) & set(broker.WRITE_VERBS)
        )

    def test_the_write_list_is_not_empty(self):
        """It explains rather than decides, but an empty one would make the
        explanatory branch unreachable and untested."""
        self.assertGreater(len(broker.WRITE_VERBS), 10)

    def test_an_unknown_verb_has_no_reason(self):
        self.assertIsNone(broker.reason_for("frobnicate"))


class TheVerbIsTheLastWordBeforeTheOptions(unittest.TestCase):
    def test_a_group_and_a_verb(self):
        self.assertEqual("list", broker.verb_of(["az", "resource", "list"]))

    def test_options_do_not_become_the_verb(self):
        self.assertEqual(
            "list", broker.verb_of(["az", "resource", "list", "--subscription", "x"])
        )

    def test_a_value_after_an_option_does_not_become_the_verb(self):
        """Reading the last token instead would make the verb whatever the
        caller passed as a value, which the caller controls."""
        self.assertEqual(
            "show",
            broker.verb_of(["az", "group", "show", "--name", "delete"]),
        )

    def test_a_deep_group_path_still_resolves(self):
        self.assertEqual(
            "list",
            broker.verb_of(["az", "role", "assignment", "list", "--scope", "/x"]),
        )

    def test_a_bare_cli_has_no_verb(self):
        self.assertIsNone(broker.verb_of(["az"]))

    def test_an_option_only_command_has_no_verb(self):
        self.assertIsNone(broker.verb_of(["az", "--version"]))


class ReadsArePlanned(unittest.TestCase):
    def test_every_allowed_verb_plans(self):
        for verb in broker.allowed_verbs():
            with self.subTest(verb=verb):
                tail = REST_GET[2:] if verb == "rest" else []
                planned = broker.plan(["az", "resource", verb] + tail)
                self.assertEqual("az", planned[0])
                self.assertIn(verb, planned)

    def test_the_planned_command_keeps_the_original_tokens_in_order(self):
        planned = broker.plan(["az", "resource", "list", "--subscription", "abc"])
        self.assertEqual(
            ["az", "resource", "list", "--subscription", "abc"], planned[:5]
        )

    def test_the_output_format_is_pinned(self):
        """Evidence is compared across runs and platforms, so the format
        cannot depend on a caller's configuration file."""
        self.assertIn("--output", broker.plan(["az", "resource", "list"]))
        self.assertIn("json", broker.plan(["az", "resource", "list"]))

    def test_a_caller_supplied_output_format_is_not_overridden(self):
        planned = broker.plan(["az", "resource", "list", "--output", "tsv"])
        self.assertEqual(1, planned.count("--output"))
        self.assertNotIn("json", planned)

    def test_the_short_output_flag_is_also_respected(self):
        """Appending --output beside -o would make the CLI reject the command,
        turning a broker decision into a confusing Azure error."""
        planned = broker.plan(["az", "resource", "list", "-o", "tsv"])
        self.assertNotIn("--output", planned)

    def test_warnings_are_suppressed_so_evidence_stays_clean(self):
        self.assertIn("--only-show-errors", broker.plan(["az", "resource", "list"]))

    def test_the_suppression_flag_is_not_duplicated(self):
        planned = broker.plan(["az", "resource", "list", "--only-show-errors"])
        self.assertEqual(1, planned.count("--only-show-errors"))


class WritesAreRefused(unittest.TestCase):
    def assert_refused(self, command, fragment):
        with self.assertRaises(broker.BrokerRefusal) as caught:
            broker.plan(command)
        self.assertIn(fragment, str(caught.exception))

    def test_every_write_verb_is_refused(self):
        for verb in broker.WRITE_VERBS:
            with self.subTest(verb=verb):
                self.assert_refused(["az", "resource", verb], "read-only")

    def test_a_write_verb_is_refused_by_name(self):
        self.assert_refused(["az", "group", "delete"], "'delete'")

    def test_an_unclassified_verb_is_refused_too(self):
        """The property that makes the allow-list load-bearing. A deny-list
        would permit every verb nobody thought of, and that set is the
        interesting one."""
        for verb in UNCLASSIFIED_VERBS:
            with self.subTest(verb=verb):
                self.assert_refused(["az", "resource", verb], "allow-list")

    def test_the_unclassified_verbs_really_are_unclassified(self):
        """The control for the case above. If one of these were quietly added
        to either list, that subtest would be asserting nothing."""
        for verb in UNCLASSIFIED_VERBS:
            with self.subTest(verb=verb):
                self.assertNotIn(verb, broker.allowed_verbs())
                self.assertNotIn(verb, broker.WRITE_VERBS)

    def test_the_refusal_names_the_allowed_set(self):
        with self.assertRaises(broker.BrokerRefusal) as caught:
            broker.plan(["az", "group", "delete"])
        for verb in broker.allowed_verbs():
            self.assertIn(verb, str(caught.exception))


class TheRestVerbIsAGet(unittest.TestCase):
    """`az rest` can write, because its method is a parameter. It is allowed
    for one ARM GET, and everything else it can do is refused."""

    def assert_refused(self, command, fragment):
        with self.assertRaises(broker.BrokerRefusal) as caught:
            broker.plan(command)
        self.assertIn(fragment, str(caught.exception))

    def replaced(self, flag, value):
        command = list(REST_GET)
        command[command.index(flag) + 1] = value
        return command

    def test_the_admitted_shape_plans(self):
        # The control. Without it, a broker refusing every az rest would
        # pass each refusal below.
        planned = broker.plan(REST_GET)
        self.assertEqual(REST_GET, planned[: len(REST_GET)])

    def test_the_method_is_compared_without_case(self):
        broker.plan(self.replaced("--method", "GET"))

    def test_every_other_method_is_refused(self):
        for method in ("put", "post", "patch", "delete", "head", "options"):
            with self.subTest(method=method):
                self.assert_refused(self.replaced("--method", method), "--method get")

    def test_a_missing_method_is_refused_rather_than_left_to_the_default(self):
        self.assert_refused(["az", "rest", "--url", "/subscriptions/x"], "--method get")

    def test_a_full_url_is_refused(self):
        for url in ("https://example.com/x", "//example.com/x", "subscriptions/x"):
            with self.subTest(url=url):
                self.assert_refused(self.replaced("--url", url), "single '/'")

    def test_a_missing_url_is_refused(self):
        self.assert_refused(["az", "rest", "--method", "get"], "--url")

    def test_a_flag_outside_the_shape_is_refused(self):
        for extra in (
            ["--body", "{}"],
            ["--headers", "a=b"],
            ["--resource", "https://example.com"],
            ["--uri-parameters", "a=b"],
            ["--skip-authorization-header"],
        ):
            with self.subTest(extra=extra):
                self.assert_refused(REST_GET + extra, "not one of the flags")

    def test_the_short_and_joined_spellings_are_refused(self):
        self.assert_refused(
            ["az", "rest", "-m", "get", "--url", "/subscriptions/x"], "'-m'"
        )
        self.assert_refused(
            ["az", "rest", "--method=put", "--url", "/subscriptions/x"],
            "not one of the flags",
        )

    def test_a_repeated_flag_is_refused(self):
        self.assert_refused(REST_GET + ["--method", "put"], "twice")

    def test_a_flag_with_no_value_is_refused(self):
        self.assert_refused(["az", "rest", "--url", "/x", "--method"], "no value")

    def test_the_url_is_structure_and_cannot_chain_a_command(self):
        self.assert_refused(self.replaced("--url", "/x&calc"), "'&'")

    def test_the_shape_applies_to_no_other_verb(self):
        broker.plan(["az", "resource", "show", "--ids", "/x", "--api-version", "1"])

    def test_every_flag_in_the_shape_has_a_reason(self):
        for flag, reason in broker.REST_FLAGS:
            with self.subTest(flag=flag):
                self.assertGreater(len(reason), 10)


class ACommandIsAListOfTokens(unittest.TestCase):
    def assert_refused(self, command, fragment):
        with self.assertRaises(broker.BrokerRefusal) as caught:
            broker.plan(command)
        self.assertIn(fragment, str(caught.exception))

    def test_a_string_command_is_refused(self):
        """Splitting it here would put another shell's quoting rules inside
        this process."""
        self.assert_refused("az resource list", "not a string")

    def test_a_string_that_would_have_been_allowed_is_still_refused(self):
        """The control case. The refusal is about the type, not about the
        content, so a read expressed as a string must fail too."""
        self.assert_refused("az resource list --output json", "not a string")

    def test_an_empty_command_is_refused(self):
        self.assert_refused([], "empty command")

    def test_an_empty_token_is_refused(self):
        """Usually an interpolated value that did not exist."""
        self.assert_refused(["az", "resource", "list", "--name", ""], "empty")

    def test_a_non_string_token_is_refused(self):
        self.assert_refused(["az", "resource", "list", "--top", 5], "not a string")

    def test_every_metacharacter_is_refused(self):
        for bad in broker.SHELL_METACHARACTERS:
            with self.subTest(character=bad):
                self.assert_refused(
                    ["az", "resource", "show", "--name", "rg%sthing" % bad], repr(bad)
                )

    def test_the_metacharacter_list_is_not_empty(self):
        self.assertTrue(broker.SHELL_METACHARACTERS)

    def test_an_ordinary_identifier_is_accepted(self):
        """The control case. A check that refused every value would satisfy
        the cases above while making the broker useless."""
        planned = broker.plan(
            ["az", "group", "show", "--name", "rg-zero-ops_01.demo"]
        )
        self.assertIn("rg-zero-ops_01.demo", planned)


class OnlyTheAzureCliIsBrokered(unittest.TestCase):
    def test_another_program_is_refused(self):
        with self.assertRaises(broker.BrokerRefusal) as caught:
            broker.plan(["curl", "https://example.invalid"])
        self.assertIn("CON-02", str(caught.exception))

    def test_a_path_to_the_cli_is_refused(self):
        """An absolute path is how a call site reaches a different binary
        while still looking like the broker was used."""
        with self.assertRaises(broker.BrokerRefusal):
            broker.plan(["/usr/bin/az", "resource", "list"])

    def test_a_bare_cli_invocation_is_refused(self):
        with self.assertRaises(broker.BrokerRefusal) as caught:
            broker.plan(["az"])
        self.assertIn("no verb", str(caught.exception))


class ConfirmationFlagsAreRefused(unittest.TestCase):
    def test_every_confirmation_flag_is_refused(self):
        for flag in broker.CONFIRMATION_FLAGS:
            with self.subTest(flag=flag):
                with self.assertRaises(broker.BrokerRefusal) as caught:
                    broker.plan(["az", "resource", "list", flag])
                self.assertIn(flag, str(caught.exception))

    def test_the_flag_list_is_not_empty(self):
        self.assertTrue(broker.CONFIRMATION_FLAGS)

    def test_a_read_without_them_is_accepted(self):
        self.assertTrue(broker.plan(["az", "resource", "list"]))


class InvokeDecidesNothing(unittest.TestCase):
    def test_a_refused_command_never_reaches_the_runner(self):
        calls = []
        with self.assertRaises(broker.BrokerRefusal):
            broker.invoke(["az", "group", "delete"], runner=calls.append)
        self.assertEqual([], calls)

    def test_an_allowed_command_reaches_the_runner_as_planned(self):
        calls = []
        broker.invoke(["az", "resource", "list"], runner=calls.append)
        self.assertEqual(1, len(calls))
        self.assertEqual(broker.plan(["az", "resource", "list"]), calls[0])

    def test_the_runner_result_is_returned_unchanged(self):
        marker = object()
        self.assertIs(marker, broker.invoke(["az", "resource", "list"], runner=lambda _: marker))

    def test_the_default_runner_never_uses_a_shell(self):
        """shell=True would make the token list above decorative."""
        with open(
            os.path.join(TOOLS_DIR, "zeroops", "broker.py"), "r", encoding="utf-8"
        ) as handle:
            source = handle.read()
        self.assertIn("shell=False", source)
        self.assertNotIn("shell=True", source)


class TheDefaultRunnerReadsTheCliEncoding(unittest.TestCase):
    """Issue 141. Each case runs a real child process, because the failure
    lived at the     process boundary that injected runners never reach."""

    def run_child(self, stdout_bytes, stderr_bytes=b"", code=0):
        script = (
            "import sys; sys.stdout.buffer.write(%r); "
            "sys.stderr.buffer.write(%r); sys.exit(%d)"
            % (stdout_bytes, stderr_bytes, code)
        )
        return broker.default_runner([sys.executable, "-c", script])

    def test_output_in_the_cli_encoding_is_read_as_text(self):
        with mock.patch.object(broker, "output_encoding", return_value="cp1252"):
            completed = self.run_child(b'["caf\xe7"]')
        self.assertEqual(0, completed.returncode)
        self.assertEqual('["caf\u00e7"]', completed.stdout)

    def test_undecodable_output_raises_instead_of_returning_nothing(self):
        # The observed failure returned stdout=None with exit code zero.
        with mock.patch.object(broker, "output_encoding", return_value="utf-8"):
            with self.assertRaises(broker.UndecodableOutput) as caught:
                self.run_child(b'["caf\xe7"]')
        self.assertIn("utf-8", str(caught.exception))

    def test_undecodable_stderr_still_returns_the_exit_code(self):
        # stderr is searched for denial signatures, never read as data, so a
        # stray byte there must not hide the failure it describes.
        with mock.patch.object(broker, "output_encoding", return_value="utf-8"):
            completed = self.run_child(b"", b"AuthorizationFailed \xe7", code=1)
        self.assertEqual(1, completed.returncode)
        self.assertIn("AuthorizationFailed", completed.stderr)

    def test_the_encoding_does_not_follow_this_interpreters_utf8_mode(self):
        # The CLI runs isolated and writes in the locale encoding whatever
        # mode this interpreter is in. Compared across two children, so the
        # assertion means something on a Windows runner, where the two
        # encodings differ.
        environment = dict(os.environ)
        environment.pop("PYTHONUTF8", None)
        environment["PYTHONPATH"] = TOOLS_DIR
        ours = subprocess.run(
            [sys.executable, "-X", "utf8", "-c",
             "from zeroops import broker; print(broker.output_encoding())"],
            capture_output=True, text=True, env=environment, check=True,
        ).stdout.strip()
        cli_like = subprocess.run(
            [sys.executable, "-I", "-c",
             "import locale; print(locale.getpreferredencoding(False))"],
            capture_output=True, text=True, env=environment, check=True,
        ).stdout.strip()
        self.assertEqual(cli_like.lower(), ours.lower())


class TheRefusalIsDistinguishableFromAFailure(unittest.TestCase):
    def test_a_refusal_is_its_own_exception_type(self):
        """A caller that could not tell the two apart would report an Azure
        error for a request that never left the machine."""
        self.assertTrue(issubclass(broker.BrokerRefusal, Exception))

    def test_a_runner_error_is_not_converted_into_a_refusal(self):
        def angry(_planned):
            raise OSError("the CLI is not installed")

        with self.assertRaises(OSError):
            broker.invoke(["az", "resource", "list"], runner=angry)


class TheBrokerStaysOffline(unittest.TestCase):
    """The whole decision surface is exercisable with no Azure and no network,
    which is what lets the negative suite run credential-free."""

    def test_planning_imports_nothing_that_talks_to_azure(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.path.insert(0, %r);\n"
                "from zeroops import localtest, broker\n"
                "localtest.forbid_network()\n"
                "print(' '.join(broker.plan(['az', 'resource', 'list'])))" % TOOLS_DIR,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            "az resource list --output json --only-show-errors",
            result.stdout.strip(),
            result.stdout + result.stderr,
        )


class TheDocumentationMatchesTheAllowList(unittest.TestCase):
    """Checked in both directions. A verb allowed in code and absent from the
    page is a capability nobody reviewed; a verb on the page and absent from
    the code is a promise the broker does not keep."""

    DOC = os.path.join(REPO_ROOT, "docs", "command-broker.md")

    def setUp(self):
        with open(self.DOC, "r", encoding="utf-8") as handle:
            self.doc = handle.read()

    def documented_verbs(self):
        """Rows of the allowed-verbs table, unfiltered.

        Filtering by what the code allows would make the comparison below
        agree by construction: a verb on the page and absent from the code
        would be dropped before the assertion ever saw it.

        Scoped to one section, because a later table also opens its rows with
        a code span and would otherwise contribute rows that are not verbs.
        """
        section = self.doc.split("## Allowed verbs", 1)[1].split("\n## ", 1)[0]
        verbs = []
        for line in section.splitlines():
            if line.startswith("| `") and "Why it is allowed" not in line:
                verbs.append(line.split("`")[1])
        return verbs

    def test_the_table_was_actually_found(self):
        """A parse that silently matched nothing would make both directions
        below pass by comparing two empty sets."""
        self.assertEqual(len(EXPECTED_VERBS), len(self.documented_verbs()))

    def test_every_allowed_verb_is_documented(self):
        self.assertEqual(sorted(broker.allowed_verbs()), sorted(self.documented_verbs()))

    def test_the_page_records_which_gate_enforces_the_choke_point(self):
        """The page once said the check did not exist. It does now, and a
        page that still said otherwise would leave a reader treating an
        enforced rule as a convention. Naming the gate is what lets a reader
        find out whether it actually runs."""
        self.assertIn("check-core", self.doc)
        self.assertNotIn("not yet implemented", self.doc)

    def test_the_page_agrees_with_the_check_about_the_binding_layer(self):
        """Stated twice on purpose: the page says the binding layer is not
        exempt, and the check is asked whether it would scan one. Either half
        alone can drift - prose nothing reads, or behaviour nobody wrote
        down."""
        from zeroops import callsites

        self.assertIn("binding layer is not exempt", self.doc)
        declaration = {
            "categories": {
                "core": [{"path": "core/policy/", "status": "present", "purpose": "x"}],
                "binding": [
                    {"path": "core/binding/", "status": "present", "purpose": "x"}
                ],
            }
        }
        self.assertEqual(
            ["core/binding/adapter.py"],
            callsites.scanned_paths(["core/binding/adapter.py"], declaration),
        )

    def test_the_page_states_where_the_real_guarantee_lives(self):
        """SEC-001: authority for read-only is the role assignment, not this
        module. A page that claimed otherwise would misdirect a reviewer."""
        self.assertIn("Azure Resource Manager", self.doc)


if __name__ == "__main__":
    unittest.main()

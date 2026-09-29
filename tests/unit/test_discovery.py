"""Evidence for T4.02: read-only Resource Graph discovery (FR-10, FR-11, FR-22).

Where a check could be satisfied by the module doing nothing, there is a
paired control asserting the clean case is reported clean. A denial detector
that returned nothing and a subscription with nothing withheld produce the
same output, and only the control tells them apart.

Tamper cases work on synthetic catalogues rather than on the file on disk. An
assertion about one fixed document cannot distinguish a check that compares
from a check that always returns an empty list.
"""

import copy
import json
import os
import unittest

from zeroops import broker, canonical, discovery, policy, validate


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SUBSCRIPTION = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"

# The one Azure type a core-path query may name, and why. An exception that
# lives in a list with a reason beside it is reviewable; the same exception
# spread through the queries is not.
PLATFORM_TYPE_EXCEPTIONS = {
    "microsoft.insights/diagnosticsettings": (
        "The platform mechanism by which any resource emits diagnostics. "
        "Naming it admits no workload and excludes none."
    ),
    "microsoft.resources/subscriptions": (
        "The container for a subscription, which is the scope itself rather "
        "than anything inside it."
    ),
}


class Completed(object):
    """What subprocess.run returns, as much of it as the module reads."""

    def __init__(self, returncode=0, stdout="[]", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class Recorder(object):
    """A runner that answers per query and remembers what it was asked."""

    def __init__(self, answers=None, default=None):
        self.answers = answers or {}
        self.default = default if default is not None else Completed()
        self.calls = []

    def __call__(self, planned):
        self.calls.append(planned)
        text = " ".join(planned)
        for marker, reply in self.answers.items():
            if marker in text:
                return reply
        return self.default


def rows(*items):
    return Completed(stdout=json.dumps(list(items)))


CONTAINER = {"id": "/subscriptions/%s" % SUBSCRIPTION, "name": "target"}
RESOURCE_A = {"id": "/subscriptions/s/rg/a", "name": "a", "type": "type.one/kind"}
RESOURCE_B = {"id": "/subscriptions/s/rg/b", "name": "b", "type": "type.two/kind"}
SETTING_A = {
    "id": "/subscriptions/s/rg/a/providers/microsoft.insights/diagnosticSettings/d"
}


def healthy_runner(resources=(RESOURCE_A, RESOURCE_B), settings=(SETTING_A,)):
    return Recorder(
        {
            "ResourceContainers": rows(CONTAINER),
            "microsoft.insights": rows(*settings),
        },
        default=rows(*resources),
    )


class TheCatalogueIsSound(unittest.TestCase):
    def setUp(self):
        self.catalogue = discovery.load_catalogue(REPO_ROOT)

    def test_it_validates_against_the_query_catalogue_schema(self):
        _path, findings = validate.validate(
            os.path.join(REPO_ROOT, "wizard", "discovery", "query-catalogue.json")
        )
        self.assertEqual([], list(findings))

    def test_every_recorded_hash_matches_its_query(self):
        self.assertEqual([], discovery.integrity_findings(self.catalogue))

    def test_every_query_discovery_issues_is_catalogued_and_nothing_else_is(self):
        self.assertEqual([], discovery.coverage_findings(self.catalogue))

    def test_every_entry_is_a_framework_default(self):
        # A consumer extension in the shipped catalogue would be consumer
        # content in a core path, and the two halves must stay separable or
        # the sanitization gate cannot tell a customisation from a tamper.
        self.assertEqual(
            ["frameworkDefault"],
            sorted({e["origin"] for e in self.catalogue["entries"]}),
        )

    def test_every_capability_class_is_one_the_tool_policy_permits(self):
        permitted = set(policy.load_baseline(REPO_ROOT)["allowedCapabilityClasses"])
        for item in self.catalogue["entries"]:
            self.assertIn(item["capabilityClass"], permitted, item["id"])

    def test_every_query_is_a_single_line(self):
        # A line break would be refused by the broker as payload, and would
        # split the evidence line recording the query in two.
        for item in self.catalogue["entries"]:
            self.assertNotIn("\n", item["queryText"], item["id"])
            self.assertNotIn("\r", item["queryText"], item["id"])

    def test_no_query_names_a_type_outside_the_stated_exceptions(self):
        # wizard/discovery/ is a core path, so it ships no workload type in
        # either direction (FR-63, CC-022). The exceptions are platform
        # mechanisms, listed with the reason each one is acceptable.
        for item in self.catalogue["entries"]:
            for named in self._types_named_in(item["queryText"]):
                self.assertIn(
                    named,
                    PLATFORM_TYPE_EXCEPTIONS,
                    "%s names the resource type %r, which is workload content "
                    "in a core path. Either remove it or add it to "
                    "PLATFORM_TYPE_EXCEPTIONS with the reason it is a platform "
                    "mechanism rather than a workload." % (item["id"], named),
                )

    def test_the_type_detector_finds_a_type_when_one_is_there(self):
        # Without this, a detector that found nothing at all would pass the
        # test above over any catalogue whatsoever.
        found = self._types_named_in(
            "Resources | where type =~ 'contoso.widgets/gadgets' | project id"
        )
        self.assertEqual({"contoso.widgets/gadgets"}, found)

    @staticmethod
    def _types_named_in(query):
        found = set()
        for chunk in query.split("'")[1::2]:
            if "/" in chunk and "." in chunk.split("/")[0]:
                found.add(chunk.lower())
        return found


class TheCatalogueIsChecked(unittest.TestCase):
    """Tamper cases, on copies. The real file is never edited."""

    def setUp(self):
        self.catalogue = discovery.load_catalogue(REPO_ROOT)

    def tampered(self):
        return copy.deepcopy(self.catalogue)

    def test_a_query_edited_after_review_is_reported(self):
        catalogue = self.tampered()
        catalogue["entries"][0]["queryText"] += " | take 1"
        findings = discovery.integrity_findings(catalogue)
        self.assertEqual(1, len(findings), findings)
        self.assertIn("edited after it was reviewed", findings[0])

    def test_a_hash_that_was_never_correct_is_reported(self):
        catalogue = self.tampered()
        catalogue["entries"][1]["queryHash"] = "0" * 64
        self.assertEqual(1, len(discovery.integrity_findings(catalogue)))

    def test_an_untampered_copy_is_reported_clean(self):
        self.assertEqual([], discovery.integrity_findings(self.tampered()))

    def test_a_query_discovery_issues_but_the_catalogue_lacks_is_reported(self):
        catalogue = self.tampered()
        catalogue["entries"] = [
            e
            for e in catalogue["entries"]
            if e["id"] != discovery.RESOURCES_QUERY
        ]
        findings = discovery.coverage_findings(catalogue)
        self.assertEqual(1, len(findings), findings)
        self.assertIn("fail at the point of use", findings[0])

    def test_a_catalogued_query_nothing_issues_is_reported(self):
        catalogue = self.tampered()
        spare = copy.deepcopy(catalogue["entries"][0])
        spare["id"] = "unreferenced-query"
        catalogue["entries"].append(spare)
        findings = discovery.coverage_findings(catalogue)
        self.assertEqual(1, len(findings), findings)
        self.assertIn("covers no call site", findings[0])

    def test_asking_for_a_query_that_is_not_catalogued_is_refused(self):
        with self.assertRaises(discovery.DiscoveryError) as caught:
            discovery.entry(self.catalogue, "improvised-query")
        self.assertIn("catalogue holds no query", str(caught.exception))

    def test_a_broken_catalogue_stops_discovery_before_anything_is_issued(self):
        catalogue = self.tampered()
        catalogue["entries"][0]["queryHash"] = "1" * 64
        runner = healthy_runner()
        with self.assertRaises(discovery.DiscoveryError):
            discovery.discover(SUBSCRIPTION, runner=runner, catalogue=catalogue)
        self.assertEqual(
            [],
            runner.calls,
            "a catalogue that cannot be trusted must not issue the entries "
            "that happen to still verify; a partial catalogue produces a "
            "shorter candidate list, which is the failure being guarded",
        )


class TheSubscriptionIsChecked(unittest.TestCase):
    def test_a_guid_is_accepted_and_lowercased(self):
        self.assertEqual(
            SUBSCRIPTION, discovery.check_subscription(SUBSCRIPTION.upper())
        )

    def test_a_lowercase_guid_is_accepted_unchanged(self):
        self.assertEqual(SUBSCRIPTION, discovery.check_subscription(SUBSCRIPTION))

    def test_anything_that_is_not_a_guid_is_refused(self):
        for value in [
            "",
            "my-subscription",
            SUBSCRIPTION[:-1],
            SUBSCRIPTION + "0",
            "/subscriptions/" + SUBSCRIPTION,
            SUBSCRIPTION + " --debug",
            None,
            12345,
            ["a"],
        ]:
            with self.assertRaises(discovery.DiscoveryError, msg=repr(value)):
                discovery.check_subscription(value)

    def test_the_refusal_says_the_scope_is_one_subscription(self):
        with self.assertRaises(discovery.DiscoveryError) as caught:
            discovery.check_subscription("all of them")
        self.assertIn("exactly one subscription", str(caught.exception))


class PlanningGoesThroughTheBroker(unittest.TestCase):
    def setUp(self):
        self.catalogue = discovery.load_catalogue(REPO_ROOT)

    def planned(self, identifier):
        return discovery.plan_query(self.catalogue, identifier, SUBSCRIPTION)

    def test_every_query_the_step_issues_is_a_command_the_broker_accepts(self):
        for identifier in discovery.QUERY_ORDER:
            command = self.planned(identifier)
            self.assertEqual(broker.CLI, command[0])
            self.assertEqual("query", broker.verb_of(command))

    def test_the_planned_command_pins_the_output_format(self):
        command = self.planned(discovery.RESOURCES_QUERY)
        self.assertIn("--output", command)
        self.assertIn("json", command)
        self.assertIn("--only-show-errors", command)

    def test_the_query_text_is_the_catalogued_text_and_not_a_rebuilt_one(self):
        command = self.planned(discovery.RESOURCES_QUERY)
        catalogued = discovery.entry(self.catalogue, discovery.RESOURCES_QUERY)
        self.assertIn(catalogued["queryText"], command)

    def test_the_row_cap_comes_from_the_tool_policy(self):
        # Not a literal here. A second number would be a second policy, and
        # the two would drift with nothing comparing them. Comparing against
        # the policy's current value alone would not show that: a hardcoded
        # 1000 matches it exactly. So the policy is moved and the command has
        # to move with it.
        cap = policy.load_baseline(REPO_ROOT)["executionLimits"]["maxResultSetRows"]
        command = self.planned(discovery.RESOURCES_QUERY)
        self.assertEqual(str(cap), command[command.index("--first") + 1])

        moved = copy.deepcopy(policy.load_baseline(REPO_ROOT))
        moved["executionLimits"]["maxResultSetRows"] = 17
        original = discovery.policy.load_baseline
        discovery.policy.load_baseline = lambda root=None: moved
        try:
            command = self.planned(discovery.RESOURCES_QUERY)
        finally:
            discovery.policy.load_baseline = original
        self.assertEqual("17", command[command.index("--first") + 1])

    def test_a_subscription_that_is_not_a_guid_never_becomes_a_token(self):
        with self.assertRaises(discovery.DiscoveryError):
            discovery.plan_query(self.catalogue, discovery.RESOURCES_QUERY, "x")

    def test_the_subscription_reaches_the_command_lowercased(self):
        command = discovery.plan_query(
            self.catalogue, discovery.RESOURCES_QUERY, SUBSCRIPTION.upper()
        )
        self.assertIn(SUBSCRIPTION, command)


class TheBrokerSeparatesStructureFromPayload(unittest.TestCase):
    """The broker change T4.02 required, and the boundary it must hold."""

    QUERY = "Resources | where type =~ 'x/y' | project id"

    def test_a_query_value_may_contain_the_pipes_that_make_it_a_query(self):
        planned = broker.plan(["az", "graph", "query", "--graph-query", self.QUERY])
        self.assertIn(self.QUERY, planned)

    def test_the_joined_spelling_of_the_flag_is_payload_too(self):
        token = "--graph-query=" + self.QUERY
        self.assertIn(token, broker.plan(["az", "graph", "query", token]))

    def test_the_short_spelling_of_the_flag_is_payload_too(self):
        self.assertIn(self.QUERY, broker.plan(["az", "graph", "query", "-q", self.QUERY]))

    def test_an_ordinary_token_containing_a_pipe_is_still_refused(self):
        # The control. Without it, a payload rule that exempted everything
        # would pass every test above.
        with self.assertRaises(broker.BrokerRefusal):
            broker.plan(["az", "resource", "show", "--ids", "a | b"])

    def test_a_pipe_after_a_flag_that_is_not_value_bearing_is_refused(self):
        # What makes the exemption a registry rather than a guess: following
        # some flag is not enough, it has to follow one that is listed.
        with self.assertRaises(broker.BrokerRefusal):
            broker.plan(["az", "graph", "query", "--subscriptions", "a | b"])

    def test_a_line_break_in_a_query_value_is_refused(self):
        with self.assertRaises(broker.BrokerRefusal) as caught:
            broker.plan(["az", "graph", "query", "--graph-query", "Resources\n| take 1"])
        self.assertIn("single line", str(caught.exception))

    def test_a_carriage_return_in_a_query_value_is_refused(self):
        with self.assertRaises(broker.BrokerRefusal):
            broker.plan(["az", "graph", "query", "--graph-query", "Resources\r| take 1"])

    def test_a_nul_in_a_query_value_is_refused(self):
        with self.assertRaises(broker.BrokerRefusal):
            broker.plan(["az", "graph", "query", "--graph-query", "Resources\0"])

    def test_an_empty_query_value_is_refused(self):
        with self.assertRaises(broker.BrokerRefusal):
            broker.plan(["az", "graph", "query", "--graph-query", ""])

    def test_payload_does_not_excuse_a_verb_that_writes(self):
        with self.assertRaises(broker.BrokerRefusal) as caught:
            broker.plan(["az", "graph", "create", "--graph-query", self.QUERY])
        self.assertIn("changes state", str(caught.exception))

    def test_payload_does_not_excuse_a_confirmation_flag(self):
        with self.assertRaises(broker.BrokerRefusal):
            broker.plan(["az", "graph", "query", "--graph-query", self.QUERY, "--yes"])

    def test_every_value_bearing_flag_is_listed_with_a_reason(self):
        self.assertTrue(broker.VALUE_BEARING_FLAGS)
        for flag, reason in broker.VALUE_BEARING_FLAGS:
            self.assertTrue(flag.startswith("-"), flag)
            self.assertTrue(len(reason) > 20, flag)

    def test_the_registry_is_narrow(self):
        # It exists for one caller. If it grows, that should be a decision
        # somebody made rather than something that happened.
        self.assertEqual(
            ("--graph-query", "-q"), broker.value_bearing_flags()
        )

    def test_the_broker_page_documents_every_flag_in_the_registry(self):
        # An exemption that is in the code and not on the page is an
        # exemption nobody reviewing the page can see.
        with open(
            os.path.join(REPO_ROOT, "docs", "command-broker.md"),
            "r",
            encoding="utf-8",
        ) as handle:
            page = handle.read()
        self.assertIn("payload", page.lower())
        for flag in broker.value_bearing_flags():
            self.assertIn(flag, page, flag)


class DenialsAreDetected(unittest.TestCase):
    def test_each_authorisation_signature_is_recognised(self):
        for signature in discovery.AUTHORISATION_SIGNATURES:
            denial = discovery.denial_for(
                discovery.RESOURCES_QUERY, "ERROR: %s (code)" % signature
            )
            self.assertIsNotNone(denial, signature)

    def test_recognition_ignores_case(self):
        self.assertIsNotNone(
            discovery.denial_for(discovery.RESOURCES_QUERY, "AuthorizationFailed")
        )

    def test_a_failure_that_is_not_a_denial_is_not_described_as_one(self):
        # The control that stops the detector from labelling everything.
        # "Grant this permission" is advice that wastes an operator's time
        # when the cause was a network timeout.
        self.assertIsNone(
            discovery.denial_for(discovery.RESOURCES_QUERY, "connection timed out")
        )

    def test_empty_error_output_is_not_a_denial(self):
        self.assertIsNone(discovery.denial_for(discovery.RESOURCES_QUERY, ""))
        self.assertIsNone(discovery.denial_for(discovery.RESOURCES_QUERY, None))

    def test_a_denial_names_the_action_that_was_missing(self):
        denial = discovery.denial_for(discovery.READABILITY_QUERY, "Forbidden")
        self.assertEqual("Microsoft.Resources/subscriptions/read", denial.permission)
        self.assertIn("Microsoft.Resources/subscriptions/read", denial.describe())

    def test_a_denial_says_it_is_not_an_empty_subscription(self):
        denial = discovery.denial_for(discovery.RESOURCES_QUERY, "AuthorizationFailed")
        self.assertIn("not an empty subscription", denial.describe())

    def test_every_query_the_step_issues_has_a_named_permission(self):
        for identifier in discovery.QUERY_ORDER:
            self.assertIn(identifier, discovery.PERMISSION_FOR)
            self.assertTrue(discovery.PERMISSION_FOR[identifier].endswith("/read"))


class DiscoveryReportsWhatItCouldNotSee(unittest.TestCase):
    """FR-22. The load-bearing behaviour of this task."""

    def test_a_readable_subscription_yields_its_resources(self):
        result = discovery.discover(SUBSCRIPTION, runner=healthy_runner())
        self.assertTrue(result.complete)
        self.assertEqual(
            ["/subscriptions/s/rg/a", "/subscriptions/s/rg/b"],
            [row["id"] for row in result.rows],
        )

    def test_a_resource_with_a_diagnostic_setting_is_marked_as_emitting(self):
        result = discovery.discover(SUBSCRIPTION, runner=healthy_runner())
        emitting = {row["id"]: row["emitsSignal"] for row in result.rows}
        self.assertEqual(
            {"/subscriptions/s/rg/a": True, "/subscriptions/s/rg/b": False}, emitting
        )

    def test_a_resource_is_matched_to_its_setting_regardless_of_case(self):
        # Azure returns the provider segment of a setting identifier in mixed
        # case, and a resource identifier need not be spelled the same way in
        # both answers. Comparing them as given would mark every resource as
        # emitting no signal, which is a plausible wrong answer rather than
        # an obvious failure.
        resource = {"id": "/subscriptions/S/RG/A", "name": "a", "type": "t/k"}
        setting = {
            "id": "/subscriptions/s/rg/a"
            "/providers/Microsoft.Insights/diagnosticSettings/d"
        }
        result = discovery.discover(
            SUBSCRIPTION, runner=healthy_runner((resource,), (setting,))
        )
        self.assertEqual([True], [row["emitsSignal"] for row in result.rows])

    def test_an_empty_subscription_is_a_complete_answer(self):
        # The control for the case below. An empty subscription is an answer,
        # and reporting it as a denial would be the mirror-image failure.
        runner = Recorder(
            {"ResourceContainers": rows(CONTAINER)}, default=rows()
        )
        result = discovery.discover(SUBSCRIPTION, runner=runner)
        self.assertTrue(result.complete)
        self.assertEqual([], result.rows)

    def test_an_unreadable_subscription_is_not_reported_as_an_empty_one(self):
        # The whole reason the readability query exists. Resource Graph
        # answers both with no rows, no error and exit code zero.
        result = discovery.discover(
            SUBSCRIPTION, runner=Recorder(default=rows())
        )
        self.assertFalse(result.complete)
        self.assertEqual(
            ["Microsoft.Resources/subscriptions/read"],
            [d.permission for d in result.denials],
        )

    def test_a_refused_readability_read_stops_before_enumerating(self):
        runner = Recorder(
            default=Completed(returncode=1, stderr="AuthorizationFailed")
        )
        result = discovery.discover(SUBSCRIPTION, runner=runner)
        self.assertFalse(result.complete)
        self.assertEqual(1, len(runner.calls))

    def test_a_refused_enumeration_is_reported_as_a_denial(self):
        runner = Recorder(
            {"ResourceContainers": rows(CONTAINER)},
            default=Completed(returncode=1, stderr="AuthorizationFailed: no"),
        )
        result = discovery.discover(SUBSCRIPTION, runner=runner)
        self.assertFalse(result.complete)
        self.assertEqual(
            [discovery.RESOURCES_QUERY, discovery.DIAGNOSTIC_SETTINGS_QUERY],
            [d.query for d in result.denials],
        )

    def test_a_partial_result_cannot_be_read_as_a_whole_one(self):
        runner = Recorder(
            {
                "ResourceContainers": rows(CONTAINER),
                "microsoft.insights": Completed(
                    returncode=1, stderr="AuthorizationFailed"
                ),
            },
            default=rows(RESOURCE_A),
        )
        result = discovery.discover(SUBSCRIPTION, runner=runner)
        with self.assertRaises(discovery.IncompleteDiscovery) as caught:
            result.rows
        self.assertIn("partial_rows", str(caught.exception))

    def test_the_partial_result_is_reachable_by_saying_so(self):
        runner = Recorder(
            {
                "ResourceContainers": rows(CONTAINER),
                "microsoft.insights": Completed(
                    returncode=1, stderr="AuthorizationFailed"
                ),
            },
            default=rows(RESOURCE_A),
        )
        result = discovery.discover(SUBSCRIPTION, runner=runner)
        self.assertEqual(1, len(result.partial_rows()))

    def test_a_complete_result_reads_its_rows_without_ceremony(self):
        result = discovery.discover(SUBSCRIPTION, runner=healthy_runner())
        self.assertEqual(result.partial_rows(), result.rows)

    def test_an_empty_result_with_a_denial_reads_differently_from_one_without(self):
        withheld = discovery.discover(SUBSCRIPTION, runner=Recorder(default=rows()))
        empty = discovery.discover(
            SUBSCRIPTION,
            runner=Recorder({"ResourceContainers": rows(CONTAINER)}, default=rows()),
        )
        self.assertNotEqual(withheld.complete, empty.complete)
        self.assertNotEqual("", withheld.describe_denials())
        self.assertEqual("", empty.describe_denials())

    def test_a_failure_that_is_not_a_denial_is_raised_rather_than_reported(self):
        runner = Recorder(
            {"ResourceContainers": rows(CONTAINER)},
            default=Completed(returncode=1, stderr="the CLI is not installed"),
        )
        with self.assertRaises(discovery.DiscoveryError) as caught:
            discovery.discover(SUBSCRIPTION, runner=runner)
        self.assertIn("not a denial", str(caught.exception))

    def test_output_that_is_not_json_is_a_failure_and_not_an_empty_result(self):
        runner = Recorder(default=Completed(stdout="Please run az login"))
        with self.assertRaises(discovery.DiscoveryError) as caught:
            discovery.discover(SUBSCRIPTION, runner=runner)
        self.assertIn("not JSON", str(caught.exception))

    def test_a_wrapped_data_envelope_is_unwrapped(self):
        runner = Recorder(
            {
                "ResourceContainers": Completed(
                    stdout=json.dumps({"data": [CONTAINER], "count": 1})
                ),
                "microsoft.insights": rows(),
            },
            default=Completed(stdout=json.dumps({"data": [RESOURCE_A], "count": 1})),
        )
        result = discovery.discover(SUBSCRIPTION, runner=runner)
        self.assertEqual(["/subscriptions/s/rg/a"], [r["id"] for r in result.rows])

    def test_discovery_refuses_a_subscription_that_is_not_a_guid(self):
        with self.assertRaises(discovery.DiscoveryError):
            discovery.discover("not-a-guid", runner=healthy_runner())

    def test_nothing_is_issued_for_a_subscription_that_is_not_a_guid(self):
        runner = healthy_runner()
        with self.assertRaises(discovery.DiscoveryError):
            discovery.discover("not-a-guid", runner=runner)
        self.assertEqual([], runner.calls)


class TheParentOfASettingIsItsPrefix(unittest.TestCase):
    def test_the_parent_is_read_from_the_setting_identifier(self):
        self.assertEqual(
            "/subscriptions/s/rg/a", discovery._parent_of(SETTING_A["id"])
        )

    def test_the_comparison_is_case_insensitive(self):
        # Azure returns the provider segment in mixed case and the resource
        # enumeration in lower case. Comparing them as given would mark every
        # resource as emitting no signal, which is a plausible wrong answer.
        self.assertEqual(
            discovery._parent_of(SETTING_A["id"]),
            discovery._parent_of(SETTING_A["id"].upper()),
        )

    def test_an_identifier_that_is_not_a_setting_keeps_its_whole_value(self):
        self.assertEqual(
            "/subscriptions/s/rg/a", discovery._parent_of("/SUBSCRIPTIONS/S/RG/A")
        )


class TheTextDigestIsDefinedOverText(unittest.TestCase):
    """`canonical.text_digest`, added for the query hashes."""

    def test_a_known_value(self):
        self.assertEqual(
            "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
            canonical.text_digest("foo"),
        )

    def test_the_two_spellings_of_a_character_agree(self):
        # A query authored on one platform and verified on another must not
        # fail integrity over which spelling of an accent was stored.
        composed = "caf\u00e9"
        decomposed = "cafe\u0301"
        self.assertNotEqual(composed, decomposed)
        self.assertEqual(
            canonical.text_digest(composed), canonical.text_digest(decomposed)
        )

    def test_it_is_not_the_document_digest(self):
        # The reason it exists. The document digest would canonicalise a bare
        # string as a JSON string, quotes included, so the two would disagree
        # about what was hashed while both returning a plausible value.
        self.assertNotEqual(canonical.text_digest("foo"), canonical.digest("foo"))

    def test_a_value_that_is_not_text_is_refused(self):
        for value in [None, 7, ["a"], {"a": 1}, b"foo"]:
            with self.assertRaises(canonical.CanonicalisationError, msg=repr(value)):
                canonical.text_digest(value)


class ThePermissionsPageNamesTwoSets(unittest.TestCase):
    """FR-11's documentation half."""

    @classmethod
    def setUpClass(cls):
        with open(
            os.path.join(REPO_ROOT, "docs", "permissions.md"), "r", encoding="utf-8"
        ) as handle:
            cls.text = handle.read()

    def test_it_names_the_discovery_set_and_the_agent_set_distinctly(self):
        self.assertIn("Discovery permission set", self.text)
        self.assertIn("Agent permission set", self.text)

    def test_it_says_the_two_are_not_the_same_set(self):
        self.assertIn("not the same set", self.text)

    def test_every_action_it_lists_for_discovery_is_a_read(self):
        section = self.text.split("## Discovery permission set")[1].split(
            "## Agent permission set"
        )[0]
        actions = [
            chunk
            for chunk in section.split("`")[1::2]
            if chunk.startswith("Microsoft.")
        ]
        self.assertTrue(actions, "no actions found; the check would pass vacuously")
        for action in actions:
            self.assertTrue(action.endswith("/read"), action)

    def test_it_names_the_permissions_discovery_actually_asks_for(self):
        # The page and the code must not drift. A document naming a
        # permission nothing requests sends an operator to grant the wrong
        # thing, and reads as correct either way.
        for permission in set(discovery.PERMISSION_FOR.values()):
            self.assertIn(permission, self.text, permission)


if __name__ == "__main__":
    unittest.main()

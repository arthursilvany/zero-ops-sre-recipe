"""The shipped examples, and what makes a configuration set complete.

FR-26 requires a minimal valid example and a fuller reference example, both of
which must validate. Validating each file on its own is not enough to make that
claim mean anything: a framework configuration naming a tool policy that no
file defines validated for as long as both examples existed, because no
per-artifact rule can reach another document. Completeness here means every
cross-artifact reference resolves inside the set.

CC-022 and FR-63 add a second property for the minimal example alone: it must
name no workload type, so that the core ships nothing a consumer has to remove.

Roughly half of what follows breaks a set on purpose. A resolver that returned
"resolved" unconditionally would pass every positive case in this file.
"""

import copy
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
SCHEMA_DIR = os.path.join(REPO_ROOT, "contracts", "schemas")
EXAMPLES_DIR = os.path.join(REPO_ROOT, "examples")
MINIMAL = os.path.join(EXAMPLES_DIR, "minimal")
TWO_ENVIRONMENTS = os.path.join(EXAMPLES_DIR, "two-environments")

if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from zeroops import canonical, references, validate  # noqa: E402

# Guards for the discoveries below. A walk that finds nothing satisfies every
# "for each found" assertion while proving nothing, which is the failure this
# file is partly about.
EXPECTED_REFERENCE_PROPERTIES = 22
EXPECTED_EXAMPLE_DIRECTORIES = 2

# FR-63 and CC-022. Matched case-insensitively on a word boundary so that a
# substring inside an unrelated identifier does not produce a false positive,
# and so that a capitalised spelling does not slip through.
WORKLOAD_TYPES = ("aks", "kubernetes", "aro", "vmss")


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def example_directories():
    """Every example directory, discovered rather than listed.

    A rule naming the two directories that exist today stops covering anything
    the moment a third is added, which is exactly when nobody is checking.
    """
    return sorted(
        os.path.join(EXAMPLES_DIR, name)
        for name in os.listdir(EXAMPLES_DIR)
        if os.path.isdir(os.path.join(EXAMPLES_DIR, name))
    )


def staged(directory):
    """A writable copy of one example, for tests that must break it."""
    staging = tempfile.mkdtemp()
    for name in os.listdir(directory):
        shutil.copy(os.path.join(directory, name), staging)
    return staging


def write(directory, filename, document):
    with open(os.path.join(directory, filename), "w", encoding="utf-8") as handle:
        json.dump(document, handle)


def rendered(results):
    return [f.render(a) for a, findings, _ in results for f in findings]


class TheRegistryCoversEveryReferenceProperty(unittest.TestCase):
    """A reference nobody classified is a reference nobody resolves."""

    @staticmethod
    def properties_in_schemas():
        pattern = re.compile(r"^[a-z][A-Za-z]*Refs?$")
        found = set()

        def walk(node, schema):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "properties" and isinstance(value, dict):
                        for name in value:
                            if pattern.match(name):
                                found.add((schema, name))
                    walk(value, schema)
            elif isinstance(node, list):
                for item in node:
                    walk(item, schema)

        for name in sorted(os.listdir(SCHEMA_DIR)):
            if not name.endswith(".schema.json"):
                continue
            schema = name[: -len(".schema.json")]
            walk(read_json(os.path.join(SCHEMA_DIR, name)), schema)
        return found

    def test_the_walk_actually_finds_something(self):
        found = self.properties_in_schemas()
        self.assertEqual(EXPECTED_REFERENCE_PROPERTIES, len(found))

    def test_every_reference_property_in_a_schema_is_registered(self):
        registered = {(r.schema, r.property) for r in references.REFERENCES}
        for entry in sorted(self.properties_in_schemas()):
            with self.subTest(reference=entry):
                self.assertIn(entry, registered)

    def test_the_registry_invents_no_reference_that_no_schema_declares(self):
        found = self.properties_in_schemas()
        for reference in references.REFERENCES:
            with self.subTest(reference=(reference.schema, reference.property)):
                self.assertIn((reference.schema, reference.property), found)

    def test_every_entry_records_why_it_is_resolved_where_it_is(self):
        for reference in references.REFERENCES:
            with self.subTest(reference=(reference.schema, reference.property)):
                self.assertIn(reference.resolution, references.RESOLUTIONS)
                self.assertGreater(len(reference.rationale), 60)

    def test_a_cross_set_reference_carries_a_path_and_a_target(self):
        across = references.by_resolution(references.ACROSS_SET)
        self.assertGreaterEqual(len(across), 12)
        for reference in across:
            with self.subTest(reference=(reference.schema, reference.property)):
                self.assertIsNotNone(reference.path)
                self.assertIsNotNone(reference.target)
                # The path must actually lead to the property it claims to be
                # about. A path ending in "*" is an array of names, so the
                # property is the last element that is not the span marker.
                named = [p for p in reference.path if p != "*"]
                self.assertEqual(reference.property, named[-1])

    def test_a_reference_resolved_elsewhere_carries_neither(self):
        """Carrying a path it never walks would make the entry look checked."""
        for resolution in (references.WITHIN_DOCUMENT, references.RUNTIME_PRODUCED):
            for reference in references.by_resolution(resolution):
                with self.subTest(reference=(reference.schema, reference.property)):
                    self.assertIsNone(reference.path)
                    self.assertIsNone(reference.target)

    def test_every_target_names_a_schema_that_exists(self):
        for reference in references.by_resolution(references.ACROSS_SET):
            path = os.path.join(SCHEMA_DIR, reference.target.kind + ".schema.json")
            with self.subTest(target=reference.target.kind):
                self.assertTrue(os.path.isfile(path))

    def test_an_unknown_resolution_is_refused(self):
        with self.assertRaises(ValueError):
            references.by_resolution("someOtherPlace")


class ThePathWalkerSpansArrays(unittest.TestCase):
    """collect is what every cross-set rule depends on to find its values."""

    def test_a_plain_path_yields_one_pointer(self):
        self.assertEqual(
            [("/a/b", "x")], references.collect({"a": {"b": "x"}}, ("a", "b"))
        )

    def test_a_star_spans_every_item(self):
        document = {"a": [{"b": "x"}, {"b": "y"}]}
        self.assertEqual(
            [("/a/0/b", "x"), ("/a/1/b", "y")],
            references.collect(document, ("a", "*", "b")),
        )

    def test_an_absent_path_yields_nothing_rather_than_raising(self):
        self.assertEqual([], references.collect({}, ("a", "b")))

    def test_a_star_over_a_non_list_yields_nothing(self):
        self.assertEqual([], references.collect({"a": {"b": "x"}}, ("a", "*")))

    def test_a_non_string_value_is_not_collected(self):
        """A reference is a name. Collecting an integer would produce a
        finding about a value that was never a reference."""
        self.assertEqual([], references.collect({"a": 3}, ("a",)))


class EveryShippedExampleIsACompleteSet(unittest.TestCase):
    """FR-26, applied to every example directory rather than to a list."""

    def test_the_discovery_actually_finds_the_examples(self):
        directories = example_directories()
        self.assertGreaterEqual(len(directories), EXPECTED_EXAMPLE_DIRECTORIES)
        self.assertIn(MINIMAL, directories)
        self.assertIn(TWO_ENVIRONMENTS, directories)

    def test_every_example_validates_with_no_finding(self):
        for directory in example_directories():
            with self.subTest(example=os.path.basename(directory)):
                self.assertEqual([], rendered(validate.validate_set(directory)))

    def test_every_example_contains_a_framework_configuration(self):
        """A set with no configuration is a folder of fragments."""
        for directory in example_directories():
            with self.subTest(example=os.path.basename(directory)):
                self.assertTrue(
                    os.path.isfile(os.path.join(directory, "framework-config.json"))
                )

    def test_the_tool_policy_a_configuration_names_is_shipped_with_it(self):
        """The defect this whole check exists because of: both examples named
        read-only-baseline and neither shipped it."""
        for directory in example_directories():
            config = read_json(os.path.join(directory, "framework-config.json"))
            named = config["toolIntegrations"]["toolPolicyRef"]
            policy = os.path.join(directory, "tool-policy.json")
            with self.subTest(example=os.path.basename(directory)):
                self.assertTrue(os.path.isfile(policy))
                self.assertEqual(named, read_json(policy)["name"])

    def test_every_scope_contract_reproduces_its_own_digest(self):
        for directory in example_directories():
            path = os.path.join(directory, "scope-contract.json")
            if not os.path.isfile(path):
                continue
            document = read_json(path)
            with self.subTest(example=os.path.basename(directory)):
                self.assertEqual(
                    document["canonicalHash"],
                    canonical.digest(document, hash_field="canonicalHash"),
                )


class TheMinimalExampleIsWorkloadNeutral(unittest.TestCase):
    """FR-63 and CC-022. The core ships nothing a consumer has to remove."""

    def minimal_files(self):
        return sorted(
            os.path.join(MINIMAL, name)
            for name in os.listdir(MINIMAL)
            if name.endswith(".json")
        )

    def test_the_scan_actually_covers_something(self):
        self.assertGreaterEqual(len(self.minimal_files()), 4)

    def test_no_workload_type_appears_anywhere_in_the_minimal_example(self):
        for path in self.minimal_files():
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for workload_type in WORKLOAD_TYPES:
                pattern = re.compile(r"(?<![a-z0-9])%s(?![a-z0-9])" % workload_type, re.I)
                with self.subTest(file=os.path.basename(path), term=workload_type):
                    self.assertIsNone(pattern.search(text))

    def test_the_neutrality_check_can_actually_fail(self):
        """Without this, a pattern that matches nothing would pass silently."""
        pattern = re.compile(r"(?<![a-z0-9])aks(?![a-z0-9])", re.I)
        self.assertIsNotNone(pattern.search('{"description": "Runs on AKS"}'))
        self.assertIsNone(pattern.search('{"name": "flaks-workload"}'))

    def test_scope_is_expressed_as_a_selection_not_a_workload_type(self):
        contract = read_json(os.path.join(MINIMAL, "scope-contract.json"))
        for entry in contract["inScope"]:
            with self.subTest(entry=entry):
                self.assertIn(entry["kind"], ("resourceGroup", "tag", "resource"))

    def test_the_minimal_example_is_smaller_than_the_reference_example(self):
        """FR-26 asks for two examples that differ. Two copies of the same set
        would satisfy every other assertion here."""
        minimal = {n for n in os.listdir(MINIMAL) if n.endswith(".json")}
        fuller = {n for n in os.listdir(TWO_ENVIRONMENTS) if n.endswith(".json")}
        self.assertLess(len(minimal), len(fuller))

    def test_the_minimal_example_carries_placeholders_only(self):
        guid = re.compile(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
        )
        for path in self.minimal_files():
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            with self.subTest(file=os.path.basename(path)):
                self.assertIsNone(guid.search(text))
                self.assertNotIn("/subscriptions/", text)


class TheSetCheckCanActuallyFail(unittest.TestCase):
    """Every rejection below is paired with the control case that makes it
    attributable to the rule under test rather than to the fixture."""

    def findings_after(self, source, mutate):
        staging = staged(source)
        try:
            self.assertEqual(
                [],
                rendered(validate.validate_set(staging)),
                "the unmodified copy must be accepted, or the rejection below "
                "cannot be attributed to the change",
            )
            mutate(staging)
            return rendered(validate.validate_set(staging))
        finally:
            shutil.rmtree(staging)

    def test_a_missing_tool_policy_is_named_as_missing(self):
        def remove(staging):
            os.unlink(os.path.join(staging, "tool-policy.json"))

        findings = self.findings_after(MINIMAL, remove)
        self.assertEqual(1, len(findings))
        self.assertIn("/toolIntegrations/toolPolicyRef", findings[0])
        self.assertIn("tool-policy.json", findings[0])

    def test_a_tool_policy_under_another_name_does_not_resolve(self):
        def rename(staging):
            policy = read_json(os.path.join(staging, "tool-policy.json"))
            policy["name"] = "some-other-policy"
            write(staging, "tool-policy.json", policy)

        findings = self.findings_after(MINIMAL, rename)
        self.assertEqual(1, len(findings))
        self.assertIn("/toolIntegrations/toolPolicyRef", findings[0])
        self.assertIn("a tool policy", findings[0])

    def test_an_agent_bound_to_a_different_scope_is_rejected(self):
        def rebind(staging):
            agent = read_json(os.path.join(staging, "agent-definition.json"))
            agent["targetScopeRef"] = "a" * 64
            write(staging, "agent-definition.json", agent)

        findings = self.findings_after(MINIMAL, rebind)
        self.assertEqual(1, len(findings))
        self.assertIn("/targetScopeRef", findings[0])

    def test_a_scope_contract_naming_an_undeclared_subscription_is_rejected(self):
        def repoint(staging):
            contract = read_json(os.path.join(staging, "scope-contract.json"))
            contract["subscriptionRef"] = "undeclared-subscription"
            contract["canonicalHash"] = canonical.digest(
                contract, hash_field="canonicalHash"
            )
            write(staging, "scope-contract.json", contract)
            agent = read_json(os.path.join(staging, "agent-definition.json"))
            agent["targetScopeRef"] = contract["canonicalHash"]
            write(staging, "agent-definition.json", agent)

        findings = self.findings_after(MINIMAL, repoint)
        self.assertEqual(1, len(findings))
        self.assertIn("/subscriptionRef", findings[0])
        self.assertIn("an external reference", findings[0])

    def test_an_agent_naming_an_undeclared_deployment_is_rejected(self):
        def repoint(staging):
            agent = read_json(os.path.join(staging, "agent-definition.json"))
            agent["modelProvider"]["deploymentRef"] = "undeclared-deployment"
            write(staging, "agent-definition.json", agent)

        findings = self.findings_after(MINIMAL, repoint)
        self.assertEqual(1, len(findings))
        self.assertIn("/modelProvider/deploymentRef", findings[0])

    def test_a_binding_naming_an_undeclared_environment_is_rejected(self):
        def repoint(staging):
            binding = read_json(
                os.path.join(staging, "environment-binding.production.json")
            )
            binding["environmentRef"] = "staging"
            write(staging, "environment-binding.production.json", binding)

        findings = self.findings_after(TWO_ENVIRONMENTS, repoint)
        self.assertEqual(1, len(findings))
        self.assertIn("/environmentRef", findings[0])
        self.assertIn("an environment", findings[0])

    def test_a_binding_naming_an_undeclared_workload_is_rejected(self):
        def repoint(staging):
            binding = read_json(
                os.path.join(staging, "environment-binding.production.json")
            )
            binding["workloadRef"] = "another-workload"
            write(staging, "environment-binding.production.json", binding)

        findings = self.findings_after(TWO_ENVIRONMENTS, repoint)
        self.assertEqual(1, len(findings))
        self.assertIn("/workloadRef", findings[0])

    def test_a_binding_naming_an_undeclared_connector_is_rejected(self):
        def repoint(staging):
            binding = read_json(
                os.path.join(staging, "environment-binding.production.json")
            )
            binding["connectorRefs"] = ["missing-connector"]
            write(staging, "environment-binding.production.json", binding)

        findings = self.findings_after(TWO_ENVIRONMENTS, repoint)
        self.assertEqual(1, len(findings))
        self.assertIn("/connectorRefs/0", findings[0])

    def test_a_connector_naming_an_undeclared_credential_is_rejected(self):
        def repoint(staging):
            connector = read_json(os.path.join(staging, "connector-config.json"))
            connector["authentication"]["credentialRef"] = "undeclared-identity"
            write(staging, "connector-config.json", connector)

        findings = self.findings_after(TWO_ENVIRONMENTS, repoint)
        self.assertEqual(1, len(findings))
        self.assertIn("/authentication/credentialRef", findings[0])

    def test_a_configuration_naming_an_absent_query_catalogue_is_rejected(self):
        def add(staging):
            config = read_json(os.path.join(staging, "framework-config.json"))
            config["observability"]["queryCatalogueRef"] = "default-catalogue"
            write(staging, "framework-config.json", config)

        findings = self.findings_after(MINIMAL, add)
        self.assertEqual(1, len(findings))
        self.assertIn("/observability/queryCatalogueRef", findings[0])
        self.assertIn("query-catalogue.json", findings[0])

    def test_a_workload_naming_an_absent_extension_is_rejected(self):
        def add(staging):
            config = read_json(os.path.join(staging, "framework-config.json"))
            config["workloads"][0]["extensionRef"] = "some-extension"
            write(staging, "framework-config.json", config)

        findings = self.findings_after(MINIMAL, add)
        self.assertEqual(1, len(findings))
        self.assertIn("/workloads/0/extensionRef", findings[0])

    def test_an_artifact_with_a_set_finding_stops_carrying_advice(self):
        """Warnings assume the document is worth advising about. Advising on a
        configuration whose references do not resolve buries the fault under
        guidance about a deployment that cannot happen yet."""
        staging = staged(MINIMAL)
        try:
            advised = [
                a for a, _, w in validate.validate_set(staging) if w
            ]
            self.assertTrue(
                any("framework-config.json" in a for a in advised),
                "the control case must carry a warning, or its absence below "
                "proves nothing",
            )
            os.unlink(os.path.join(staging, "tool-policy.json"))
            for artifact, findings, warnings in validate.validate_set(staging):
                if findings:
                    with self.subTest(artifact=os.path.basename(artifact)):
                        self.assertEqual([], warnings)
        finally:
            shutil.rmtree(staging)


class AMalformedMemberSuppressesTheSetPass(unittest.TestCase):
    """The set pass is gated on the set being well-formed, for the same reason
    the semantic pass is gated on one document being well-formed."""

    def test_one_broken_member_produces_one_offender_not_a_cascade(self):
        staging = staged(TWO_ENVIRONMENTS)
        try:
            connector = read_json(os.path.join(staging, "connector-config.json"))
            connector["unexpectedProperty"] = "x"
            write(staging, "connector-config.json", connector)

            results = validate.validate_set(staging)
            offenders = sorted(os.path.basename(a) for a, f, _ in results if f)
            self.assertEqual(["connector-config.json"], offenders)
        finally:
            shutil.rmtree(staging)

    def test_the_bindings_that_pointed_at_it_are_not_blamed(self):
        """Without the gate, removing the connector's shape would report both
        bindings as naming a connector nobody defined, which is true and
        useless: the one fault that matters is the connector."""
        staging = staged(TWO_ENVIRONMENTS)
        try:
            connector = read_json(os.path.join(staging, "connector-config.json"))
            connector["unexpectedProperty"] = "x"
            write(staging, "connector-config.json", connector)
            results = validate.validate_set(staging)
            blamed = [
                f.render(a)
                for a, findings, _ in results
                for f in findings
                if "environment-binding" in a
            ]
            self.assertEqual([], blamed)
        finally:
            shutil.rmtree(staging)

    def test_the_gate_is_what_suppresses_it_not_the_absence_of_a_rule(self):
        """Feed the resolver the same set with the broken member removed from
        the loaded list, and it does report the bindings. The suppression is a
        decision, not a rule that never fires."""
        loaded = []
        for name in sorted(os.listdir(TWO_ENVIRONMENTS)):
            if not name.endswith(".json") or name.startswith("connector-config"):
                continue
            path = os.path.join(TWO_ENVIRONMENTS, name)
            loaded.append((path, validate.kind_of(path), read_json(path)))

        findings = validate.set_findings(loaded)
        pointers = sorted(f.pointer for _, f in findings)
        self.assertEqual(["/connectorRefs/0", "/connectorRefs/0"], pointers)


class ASingleArtifactIsStillASet(unittest.TestCase):
    """The case a set-level check is most tempting to skip, and the one where
    a dangling reference is most likely: nothing else is present to define it."""

    def test_a_lone_framework_configuration_is_still_resolved(self):
        staging = tempfile.mkdtemp()
        try:
            shutil.copy(
                os.path.join(MINIMAL, "framework-config.json"), staging
            )
            findings = rendered(validate.validate_set(staging))
            self.assertEqual(1, len(findings))
            self.assertIn("/toolIntegrations/toolPolicyRef", findings[0])
        finally:
            shutil.rmtree(staging)


class TheExamplesStayDeclared(unittest.TestCase):
    """examples/ subdirectories are declared individually, unlike tools/ and
    tests/, so a new example that nobody declared is invisible to check-core."""

    def test_every_example_directory_is_declared(self):
        declaration = read_json(os.path.join(REPO_ROOT, "contracts", "core-paths.json"))
        declared = set()
        for entries in declaration["categories"].values():
            for entry in entries:
                declared.add(entry["path"])
        for directory in example_directories():
            name = os.path.basename(directory)
            with self.subTest(example=name):
                self.assertIn("examples/%s/" % name, declared)


if __name__ == "__main__":
    unittest.main()

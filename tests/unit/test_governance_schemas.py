"""The governance schemas hold the cross-cutting rules, and the rules are enforced.

The lint here runs over every file in contracts/schemas/, present and future, rather
than over a list. A rule that applies to five named schemas stops applying the moment a
sixth is added, which is exactly when nobody is looking.

Roughly half of these cases feed the schemas documents that must be rejected. A schema
observed only to accept is not known to constrain anything.
"""

import json
import os
import re
import unittest

import jsonschema

from zeroops import canonical

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA_DIR = os.path.join(REPO_ROOT, "contracts", "schemas")
EXAMPLE_DIR = os.path.join(REPO_ROOT, "examples", "two-environments")

# The governance set T1.07 names. core-paths is framework-internal, not a governance
# contract, so it is linted by the cross-cutting rules but is not required here.
GOVERNANCE = [
    "scope-contract",
    "framework-config",
    "environment-binding",
    "connector-config",
    "agent-definition",
]

# Matched against a lowercased property name. A name ending in "Ref" is an
# indirection and is allowed: it names where a value lives, never the value.
SECRET_NAME_PATTERNS = [
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "credential",
    "apikey",
    "privatekey",
    "connectionstring",
    "sharedaccesssignature",
]

# A property that accepts an arbitrary object or an unconstrained blob would let a
# workload payload ride inside a governed artifact, which is what SEC-013 forbids.
FREEFORM_NAMES = ["payload", "data", "body", "content", "raw", "extra", "metadata"]


def schema_files():
    return sorted(
        os.path.join(SCHEMA_DIR, name)
        for name in os.listdir(SCHEMA_DIR)
        if name.endswith(".schema.json")
    )


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def walk(node, pointer=""):
    """Yield every (pointer, node) pair in a schema document."""
    yield pointer, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, "%s/%s" % (pointer, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, "%s/%d" % (pointer, index))


def object_nodes(schema):
    """Yield schema nodes that describe a JSON object."""
    for pointer, node in walk(schema):
        if isinstance(node, dict) and node.get("type") == "object":
            yield pointer, node


def declared_property_names(schema):
    for pointer, node in walk(schema):
        if isinstance(node, dict) and isinstance(node.get("properties"), dict):
            for name in node["properties"]:
                yield "%s/properties/%s" % (pointer, name), name


class TheGovernanceSetExists(unittest.TestCase):
    def test_every_named_schema_resolves_to_exactly_one_file(self):
        for name in GOVERNANCE:
            matches = [
                path
                for path in schema_files()
                if os.path.basename(path) == "%s.schema.json" % name
            ]
            self.assertEqual(
                1, len(matches), "%s resolves to %d files, expected 1" % (name, len(matches))
            )

    def test_every_schema_is_a_valid_2020_12_schema(self):
        for path in schema_files():
            with self.subTest(schema=os.path.basename(path)):
                jsonschema.Draft202012Validator.check_schema(read_json(path))

    def test_every_schema_declares_the_2020_12_dialect(self):
        for path in schema_files():
            with self.subTest(schema=os.path.basename(path)):
                self.assertEqual(
                    "https://json-schema.org/draft/2020-12/schema",
                    read_json(path).get("$schema"),
                )

    def test_every_schema_declares_a_unique_id_and_a_title(self):
        seen = {}
        for path in schema_files():
            schema = read_json(path)
            identifier = schema.get("$id")
            self.assertTrue(identifier, "%s has no $id" % path)
            self.assertNotIn(identifier, seen, "$id %s is used twice" % identifier)
            seen[identifier] = path
            self.assertTrue(schema.get("title"), "%s has no title" % path)


class CrossCuttingRulesHold(unittest.TestCase):
    """The rules the data model applies to every schema without exception (NEG-I)."""

    def test_every_object_forbids_unknown_properties(self):
        # Without this an unknown property is silently accepted, and a typo in a
        # security-relevant name reads as a default rather than an error (FR-27).
        for path in schema_files():
            schema = read_json(path)
            for pointer, node in object_nodes(schema):
                with self.subTest(schema=os.path.basename(path), pointer=pointer):
                    self.assertIs(
                        False,
                        node.get("additionalProperties"),
                        "object at %s does not set additionalProperties: false" % pointer,
                    )

    def test_every_governance_schema_requires_an_explicit_version(self):
        for name in GOVERNANCE:
            schema = read_json(os.path.join(SCHEMA_DIR, "%s.schema.json" % name))
            with self.subTest(schema=name):
                self.assertIn("schemaVersion", schema.get("properties", {}))
                self.assertIn("schemaVersion", schema.get("required", []))

    def test_no_property_is_named_like_a_secret(self):
        # SEC-013 is structural: an inline secret must be inexpressible, not merely
        # invalid. A name ending in Ref is an indirection and is allowed.
        for path in schema_files():
            schema = read_json(path)
            for pointer, name in declared_property_names(schema):
                if name.endswith("Ref") or name.endswith("Refs"):
                    continue
                lowered = name.lower()
                for pattern in SECRET_NAME_PATTERNS:
                    with self.subTest(schema=os.path.basename(path), property=name):
                        self.assertNotIn(
                            pattern,
                            lowered,
                            "%s names a property that could carry a secret (%s)"
                            % (pointer, pattern),
                        )

    def test_no_property_is_a_free_form_payload(self):
        for path in schema_files():
            schema = read_json(path)
            for pointer, name in declared_property_names(schema):
                with self.subTest(schema=os.path.basename(path), property=name):
                    self.assertNotIn(
                        name.lower(),
                        FREEFORM_NAMES,
                        "%s is a free-form payload field (SEC-013)" % pointer,
                    )

    def test_no_schema_refs_outside_itself(self):
        # A cross-file $ref is unresolvable without a registry, so the validator
        # would try to fetch the $id over the network. That would make offline
        # validation depend on reachability. Verified in the suite below.
        for path in schema_files():
            schema = read_json(path)
            for pointer, node in walk(schema):
                if isinstance(node, dict) and "$ref" in node:
                    with self.subTest(schema=os.path.basename(path), pointer=pointer):
                        self.assertTrue(
                            node["$ref"].startswith("#"),
                            "%s refs %s, which is outside this document"
                            % (pointer, node["$ref"]),
                        )

    def test_a_cross_file_ref_really_would_break_offline_validation(self):
        # The rule above is only worth enforcing if the failure it prevents is real.
        external = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "properties": {
                "a": {
                    "$ref": "https://zero-ops-sre-recipe.contracts/schemas/"
                    "framework-config.schema.json#/$defs/identifier"
                }
            },
        }
        with self.assertRaises(Exception):
            jsonschema.Draft202012Validator(external).validate({"a": "x"})

    def test_every_string_property_is_bounded_or_enumerated(self):
        # An unbounded string is where a pasted credential or a customer blob would
        # land. Every one must carry a length ceiling, a pattern, an enum or a format.
        for path in schema_files():
            schema = read_json(path)
            for pointer, node in walk(schema):
                if not isinstance(node, dict) or node.get("type") != "string":
                    continue
                bounded = any(
                    key in node for key in ("maxLength", "pattern", "enum", "const", "format")
                )
                with self.subTest(schema=os.path.basename(path), pointer=pointer):
                    self.assertTrue(bounded, "%s is an unbounded string" % pointer)


class SchemasRejectWhatTheyMust(unittest.TestCase):
    """Feed each schema documents it has to refuse."""

    def validator(self, name):
        return jsonschema.Draft202012Validator(
            read_json(os.path.join(SCHEMA_DIR, "%s.schema.json" % name))
        )

    def valid(self, name):
        mapping = {
            "scope-contract": "scope-contract.json",
            "framework-config": "framework-config.json",
            "environment-binding": "environment-binding.production.json",
            "connector-config": "connector-config.json",
            "agent-definition": "agent-definition.json",
        }
        return read_json(os.path.join(EXAMPLE_DIR, mapping[name]))

    def assert_rejects(self, name, document):
        with self.assertRaises(jsonschema.ValidationError):
            self.validator(name).validate(document)

    def test_every_shipped_example_validates(self):
        for name in GOVERNANCE:
            with self.subTest(schema=name):
                self.validator(name).validate(self.valid(name))

    def test_an_unknown_property_is_rejected_everywhere(self):
        for name in GOVERNANCE:
            document = dict(self.valid(name))
            document["somethingNobodyDeclared"] = "x"
            with self.subTest(schema=name):
                self.assert_rejects(name, document)

    def test_an_inline_secret_cannot_be_added(self):
        for name in GOVERNANCE:
            document = dict(self.valid(name))
            document["clientSecret"] = "not-a-real-value"
            with self.subTest(schema=name):
                self.assert_rejects(name, document)

    def test_a_missing_version_is_rejected(self):
        for name in GOVERNANCE:
            document = {k: v for k, v in self.valid(name).items() if k != "schemaVersion"}
            with self.subTest(schema=name):
                self.assert_rejects(name, document)

    def test_an_empty_scope_selection_is_rejected(self):
        document = self.valid("scope-contract")
        document["inScope"] = []
        self.assert_rejects("scope-contract", document)

    def test_an_absent_exclusion_list_is_rejected(self):
        # Exclusions are declared explicitly and never implied by omission.
        document = {k: v for k, v in self.valid("scope-contract").items() if k != "outOfScope"}
        self.assert_rejects("scope-contract", document)

    def test_an_uppercase_digest_is_rejected(self):
        document = self.valid("scope-contract")
        document["canonicalHash"] = document["canonicalHash"].upper()
        self.assert_rejects("scope-contract", document)

    def test_a_non_utc_timestamp_is_rejected(self):
        document = self.valid("scope-contract")
        document["generatedAt"] = "2026-01-08T00:00:00+01:00"
        self.assert_rejects("scope-contract", document)

    def test_prose_masquerading_as_a_timestamp_is_rejected(self):
        # format is an annotation by default, so the pattern is what refuses this.
        document = self.valid("scope-contract")
        document["generatedAt"] = "next tuesday"
        self.assert_rejects("scope-contract", document)

    def test_an_omitted_execution_limit_is_rejected(self):
        document = self.valid("scope-contract")
        document["executionLimits"] = {"maxToolCalls": 1}
        self.assert_rejects("scope-contract", document)

    def test_a_mutating_remediation_mode_is_inexpressible(self):
        document = self.valid("framework-config")
        document["remediationPermissions"]["mode"] = "remediate"
        self.assert_rejects("framework-config", document)

    def test_self_approval_cannot_be_enabled(self):
        document = self.valid("framework-config")
        document["approvalPolicies"]["selfApprovalPermitted"] = True
        self.assert_rejects("framework-config", document)

    def test_an_authentication_method_holding_material_is_inexpressible(self):
        document = self.valid("connector-config")
        document["authentication"]["method"] = "sharedKey"
        self.assert_rejects("connector-config", document)

    def test_a_writable_connector_is_inexpressible(self):
        document = self.valid("connector-config")
        document["access"]["mode"] = "readWrite"
        self.assert_rejects("connector-config", document)

    def test_a_connector_reference_cannot_carry_a_url(self):
        # The pattern is narrow enough that a pasted endpoint fails validation
        # rather than being committed.
        document = self.valid("connector-config")
        document["endpointRef"] = "https://example.invalid/api?key=abc"
        self.assert_rejects("connector-config", document)

    def test_an_agent_without_an_explicit_capability_list_is_rejected(self):
        # NEG-D. A runtime given no list inherits its global tool set, which
        # includes write tools, so omission must be inexpressible.
        document = {k: v for k, v in self.valid("agent-definition").items() if k != "capabilities"}
        self.assert_rejects("agent-definition", document)

    def test_an_empty_capability_list_is_accepted_because_it_is_explicit(self):
        document = self.valid("agent-definition")
        document["capabilities"] = []
        self.validator("agent-definition").validate(document)

    def test_an_unclassified_capability_is_rejected(self):
        # NEG-C. A capability the runtime advertises and the contract does not
        # classify must fail rather than default to allowed.
        document = self.valid("agent-definition")
        document["capabilities"] = ["runArbitraryQuery"]
        self.assert_rejects("agent-definition", document)

    def test_a_write_access_level_is_inexpressible(self):
        document = self.valid("agent-definition")
        document["accessLevel"] = "readWrite"
        self.assert_rejects("agent-definition", document)

    def test_a_mutating_action_mode_is_inexpressible(self):
        document = self.valid("agent-definition")
        document["actionMode"] = "remediate"
        self.assert_rejects("agent-definition", document)

    def test_a_binding_cannot_lower_the_self_approval_prohibition(self):
        document = self.valid("environment-binding")
        document["approvalPolicyOverride"]["selfApprovalPermitted"] = True
        self.assert_rejects("environment-binding", document)

    def test_a_binding_cannot_declare_its_own_scope(self):
        # This is what keeps FR-36's "without duplicating" structural.
        document = self.valid("environment-binding")
        document["inScope"] = [{"kind": "resourceGroup", "selector": "x"}]
        self.assert_rejects("environment-binding", document)

    def test_an_override_that_overrides_nothing_is_rejected(self):
        document = self.valid("environment-binding")
        document["executionLimitOverrides"] = {}
        self.assert_rejects("environment-binding", document)

    def test_an_undeclared_tier_is_rejected(self):
        document = self.valid("environment-binding")
        document["tier"] = "staging"
        self.assert_rejects("environment-binding", document)


class OneWorkloadTwoEnvironments(unittest.TestCase):
    """FR-36, shown rather than asserted."""

    def setUp(self):
        self.config = read_json(os.path.join(EXAMPLE_DIR, "framework-config.json"))
        self.nonprod = read_json(
            os.path.join(EXAMPLE_DIR, "environment-binding.nonproduction.json")
        )
        self.prod = read_json(
            os.path.join(EXAMPLE_DIR, "environment-binding.production.json")
        )

    def test_two_environments_are_declared(self):
        names = {e["name"] for e in self.config["environments"]}
        self.assertEqual({"non-production", "production"}, names)

    def test_the_bindings_cover_both_tiers(self):
        self.assertEqual(
            {"nonProduction", "production"}, {self.nonprod["tier"], self.prod["tier"]}
        )

    def test_both_bindings_reference_the_same_single_workload(self):
        self.assertEqual(self.nonprod["workloadRef"], self.prod["workloadRef"])
        self.assertEqual(1, len(self.config["workloads"]))
        self.assertEqual(self.config["workloads"][0]["name"], self.prod["workloadRef"])

    def test_the_workload_definition_appears_exactly_once(self):
        # The point of FR-36. If a binding could carry a selection, the two copies
        # would drift and nothing would notice.
        for binding in (self.nonprod, self.prod):
            self.assertNotIn("inScope", binding)
            self.assertNotIn("outOfScope", binding)
            self.assertNotIn("workloads", binding)

    def test_each_binding_names_an_environment_that_exists(self):
        declared = {e["name"] for e in self.config["environments"]}
        for binding in (self.nonprod, self.prod):
            self.assertIn(binding["environmentRef"], declared)

    def test_the_environments_differ_where_they_should(self):
        self.assertNotEqual(self.nonprod["environmentRef"], self.prod["environmentRef"])
        self.assertIn("observationPeriodOverride", self.prod)
        self.assertNotIn("observationPeriodOverride", self.nonprod)


class ExamplesCarryPlaceholdersOnly(unittest.TestCase):
    """Every shipped example is committed, so none may carry a real identifier."""

    GUID = re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    )

    def example_files(self):
        # Every example directory, not a list of them. A rule that covers the two
        # directories that exist today stops covering anything the moment a third
        # is added, which is precisely when nobody is checking.
        root = os.path.join(REPO_ROOT, "examples")
        for directory, _, names in os.walk(root):
            for name in sorted(names):
                if name.endswith(".json"):
                    yield os.path.join(directory, name)

    def test_the_scan_actually_covers_something(self):
        # Guards every assertion below: a generator that yields nothing passes
        # them all while proving nothing.
        found = list(self.example_files())
        self.assertGreaterEqual(len(found), 6)

    def test_every_example_directory_is_declared_in_the_core_declaration(self):
        # check-core verifies that declared paths exist. It does not notice a
        # directory nobody declared, so a shipped example could sit outside the
        # declaration entirely. This closes that direction for examples/.
        with open(
            os.path.join(REPO_ROOT, "contracts", "core-paths.json"), "r", encoding="utf-8"
        ) as handle:
            declaration = json.load(handle)
        declared = set()
        for entries in declaration["categories"].values():
            for entry in entries:
                declared.add(entry["path"])
        root = os.path.join(REPO_ROOT, "examples")
        for name in sorted(os.listdir(root)):
            if os.path.isdir(os.path.join(root, name)):
                with self.subTest(example=name):
                    self.assertIn("examples/%s/" % name, declared)

    def test_no_example_contains_a_guid(self):
        for path in self.example_files():
            with open(path, "r", encoding="utf-8") as handle:
                with self.subTest(example=os.path.basename(path)):
                    self.assertIsNone(self.GUID.search(handle.read()))

    def test_no_example_contains_an_azure_resource_identifier(self):
        for path in self.example_files():
            with open(path, "r", encoding="utf-8") as handle:
                with self.subTest(example=os.path.basename(path)):
                    self.assertNotIn("/subscriptions/", handle.read())

    def test_selectors_are_placeholders(self):
        contract = read_json(os.path.join(EXAMPLE_DIR, "scope-contract.json"))
        for entry in contract["inScope"] + contract["outOfScope"]:
            self.assertTrue(
                entry["selector"].startswith("<") and entry["selector"].endswith(">"),
                "selector %r is not a placeholder" % entry["selector"],
            )


class TheExampleChainIsInternallyConsistent(unittest.TestCase):
    """The recorded hash is real, and the agent binds to it."""

    def test_the_recorded_scope_hash_recomputes(self):
        # If this drifts, the example ships a digest that authenticates nothing
        # and the first thing a consumer copies is already wrong.
        path = os.path.join(EXAMPLE_DIR, "scope-contract.json")
        with open(path, "r", encoding="utf-8") as handle:
            document = canonical.load(handle.read())
        self.assertEqual(
            document["canonicalHash"],
            canonical.digest(document, hash_field="canonicalHash"),
        )

    def test_the_agent_binds_to_that_exact_scope(self):
        contract = read_json(os.path.join(EXAMPLE_DIR, "scope-contract.json"))
        agent = read_json(os.path.join(EXAMPLE_DIR, "agent-definition.json"))
        self.assertEqual(contract["canonicalHash"], agent["targetScopeRef"])

    def test_every_reference_name_resolves_to_an_external_reference(self):
        config = read_json(os.path.join(EXAMPLE_DIR, "framework-config.json"))
        declared = {e["name"] for e in config["externalReferences"]["entries"]}
        contract = read_json(os.path.join(EXAMPLE_DIR, "scope-contract.json"))
        connector = read_json(os.path.join(EXAMPLE_DIR, "connector-config.json"))
        agent = read_json(os.path.join(EXAMPLE_DIR, "agent-definition.json"))
        self.assertIn(contract["subscriptionRef"], declared)
        self.assertIn(connector["endpointRef"], declared)
        self.assertIn(connector["authentication"]["credentialRef"], declared)
        self.assertIn(agent["modelProvider"]["deploymentRef"], declared)

    def test_each_binding_names_a_connector_that_exists(self):
        connector = read_json(os.path.join(EXAMPLE_DIR, "connector-config.json"))
        for name in ("environment-binding.nonproduction.json", "environment-binding.production.json"):
            binding = read_json(os.path.join(EXAMPLE_DIR, name))
            with self.subTest(binding=name):
                self.assertEqual([connector["name"]], binding["connectorRefs"])


if __name__ == "__main__":
    unittest.main()

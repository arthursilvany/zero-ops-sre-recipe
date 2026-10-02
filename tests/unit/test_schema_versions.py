"""Schema versioning: the pin, the register, the digest and the gate (T1.13).

FR-05 already required every instance to declare the version it conforms to, and
every schema already enforced that. The declaration was still decorative, because
no schema said what version *it* was: an instance declaring 9.9.9 validated
against a 1.0.0 schema and exited 0. The letter of the requirement was met and
none of its substance was.

NFR-21 asks that the version identifier change when a schema changes in a way that
breaks existing configurations. Nothing about declaring a version obliges anyone to
change it, so the recorded content digest is what turns that from an intention into
a check: a schema edited in place with its version left alone is otherwise
indistinguishable from one nobody touched.

Roughly half of what follows feeds the machinery something it must refuse, because
a check observed only to pass is not known to be able to fail. Where a rejection
could plausibly come from the fixture rather than from the rule, the control case
is asserted alongside it.
"""

import copy
import json
import os
import shutil
import tempfile
import unittest

import jsonschema

from zeroops import canonical, validate

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA_DIR = os.path.join(REPO_ROOT, "contracts", "schemas")
REGISTER = os.path.join(REPO_ROOT, "contracts", "schema-versions.json")
SUFFIX = ".schema.json"

# A discovery that returns nothing satisfies every "for each found" assertion
# vacuously, so the count is guarded rather than trusted.
EXPECTED_SCHEMAS = 20


def schema_files():
    return sorted(n for n in os.listdir(SCHEMA_DIR) if n.endswith(SUFFIX))


def load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def register():
    return load(REGISTER)


def entries_by_schema():
    return {entry["schema"]: entry for entry in register()["entries"]}


class TheDiscoveryIsNotVacuous(unittest.TestCase):
    def test_the_schema_directory_holds_what_is_expected(self):
        self.assertEqual(len(schema_files()), EXPECTED_SCHEMAS)

    def test_the_register_is_not_empty(self):
        self.assertGreater(len(register()["entries"]), 0)


class EverySchemaPinsItsOwnVersion(unittest.TestCase):
    """The pin is the whole point: without it the declaration checks nothing."""

    def test_every_schema_pins_a_version(self):
        for name in schema_files():
            with self.subTest(schema=name):
                pinned = validate.pinned_version(load(os.path.join(SCHEMA_DIR, name)))
                self.assertIsNotNone(
                    pinned, "%s does not pin the version it is" % name
                )

    def test_every_pin_is_a_semantic_version(self):
        for name in schema_files():
            with self.subTest(schema=name):
                pinned = validate.pinned_version(load(os.path.join(SCHEMA_DIR, name)))
                parts = pinned.split(".")
                self.assertEqual(len(parts), 3)
                for part in parts:
                    self.assertTrue(part.isdigit())

    def test_the_pattern_survives_alongside_the_pin(self):
        """The pin makes the pattern redundant today and load-bearing later.

        When a schema reaches 2.0.0 the const moves with it; the pattern is what
        still refuses a version that is not a version at all.
        """
        for name in schema_files():
            with self.subTest(schema=name):
                schema = load(os.path.join(SCHEMA_DIR, name))
                for container in ("$defs", "properties"):
                    definition = (schema.get(container) or {}).get("schemaVersion")
                    if isinstance(definition, dict) and "const" in definition:
                        self.assertIn("pattern", definition)
                        break
                else:
                    self.fail("no pinned schemaVersion in %s" % name)

    def test_pinned_version_is_none_when_nothing_is_pinned(self):
        """The reader returns None rather than raising, so it stays usable
        against a schema written before the pin existed."""
        self.assertIsNone(validate.pinned_version({}))
        self.assertIsNone(
            validate.pinned_version({"$defs": {"schemaVersion": {"type": "string"}}})
        )

    def test_pinned_version_reads_either_shape(self):
        under_defs = {"$defs": {"schemaVersion": {"const": "3.1.4"}}}
        under_properties = {"properties": {"schemaVersion": {"const": "3.1.4"}}}
        self.assertEqual(validate.pinned_version(under_defs), "3.1.4")
        self.assertEqual(validate.pinned_version(under_properties), "3.1.4")


class TheRegisterAndTheSchemasAgree(unittest.TestCase):
    """Checked in both directions. A schema with no entry is unversioned and
    undetectably so, which is the state the register exists to end."""

    def test_every_schema_has_an_entry(self):
        registered = entries_by_schema()
        for name in schema_files():
            with self.subTest(schema=name):
                self.assertIn(name[: -len(SUFFIX)], registered)

    def test_every_entry_names_a_schema(self):
        present = {name[: -len(SUFFIX)] for name in schema_files()}
        for name in entries_by_schema():
            with self.subTest(entry=name):
                self.assertIn(name, present)

    def test_no_schema_is_registered_twice(self):
        names = [entry["schema"] for entry in register()["entries"]]
        self.assertEqual(len(names), len(set(names)))

    def test_the_recorded_version_equals_the_pin(self):
        for name, entry in entries_by_schema().items():
            with self.subTest(schema=name):
                pinned = validate.pinned_version(load(os.path.join(SCHEMA_DIR, name + SUFFIX)))
                self.assertEqual(entry["version"], pinned)

    def test_the_current_version_is_the_last_in_history(self):
        for name, entry in entries_by_schema().items():
            with self.subTest(schema=name):
                self.assertEqual(entry["history"][-1]["version"], entry["version"])

    def test_history_versions_are_unique_and_ordered(self):
        for name, entry in entries_by_schema().items():
            with self.subTest(schema=name):
                seen = [record["version"] for record in entry["history"]]
                self.assertEqual(len(seen), len(set(seen)))
                keys = [tuple(int(p) for p in v.split(".")) for v in seen]
                self.assertEqual(keys, sorted(keys))


class TheDigestMakesTheVersionEnforceable(unittest.TestCase):
    """NFR-21 is unenforceable without this. Declaring a version obliges nobody
    to change it, so an in-place edit under an unchanged version is the failure
    the digest exists to catch."""

    def test_every_recorded_digest_matches_the_schema_on_disk(self):
        for name, entry in entries_by_schema().items():
            with self.subTest(schema=name):
                document = load(os.path.join(SCHEMA_DIR, name + SUFFIX))
                self.assertEqual(
                    entry["contentDigest"],
                    canonical.digest(document),
                    "%s changed without its digest being updated. If the change "
                    "was deliberate, bump the version and record the migration "
                    "action; if it was not, revert it." % name,
                )

    def test_a_changed_schema_produces_a_different_digest(self):
        """The control case: the check above passing has to mean something."""
        name = schema_files()[0]
        document = load(os.path.join(SCHEMA_DIR, name))
        before = canonical.digest(document)
        mutated = copy.deepcopy(document)
        mutated["title"] = mutated.get("title", "") + " (edited)"
        self.assertNotEqual(before, canonical.digest(mutated))

    def test_reformatting_does_not_change_the_digest(self):
        """Canonicalisation is why a whitespace change demands no version bump."""
        name = schema_files()[0]
        with open(os.path.join(SCHEMA_DIR, name), encoding="utf-8") as handle:
            raw = handle.read()
        reformatted = json.loads(json.dumps(json.loads(raw), indent=8))
        self.assertEqual(canonical.digest(json.loads(raw)), canonical.digest(reformatted))

    def test_every_digest_is_lowercase_hex_of_the_pinned_length(self):
        for name, entry in entries_by_schema().items():
            with self.subTest(schema=name):
                digest = entry["contentDigest"]
                self.assertEqual(len(digest), 64)
                self.assertEqual(digest, digest.lower())
                self.assertTrue(all(c in "0123456789abcdef" for c in digest))


class EveryVersionStatesWhatItCosts(unittest.TestCase):
    """FR-29, with no exceptions. Silence and 'nothing breaks' are identical
    from outside, and only one of them is a claim someone made."""

    def test_every_record_lists_breaking_changes(self):
        for name, entry in entries_by_schema().items():
            for record in entry["history"]:
                with self.subTest(schema=name, version=record["version"]):
                    self.assertIn("breakingChanges", record)
                    self.assertIsInstance(record["breakingChanges"], list)

    def test_every_record_states_a_migration_action(self):
        for name, entry in entries_by_schema().items():
            for record in entry["history"]:
                with self.subTest(schema=name, version=record["version"]):
                    self.assertTrue(record["migration"].strip())

    def test_every_breaking_change_names_what_it_affects(self):
        for name, entry in entries_by_schema().items():
            for record in entry["history"]:
                for change in record["breakingChanges"]:
                    with self.subTest(schema=name, version=record["version"]):
                        self.assertTrue(change["affects"].strip())
                        self.assertTrue(change["change"].strip())

    def test_the_initial_version_records_rather_than_omits(self):
        for name, entry in entries_by_schema().items():
            with self.subTest(schema=name):
                first = entry["history"][0]
                self.assertIn("breakingChanges", first)
                self.assertIn("migration", first)


class TheRegisterSchemaCanActuallyRefuse(unittest.TestCase):
    """Half of this file's job. A schema observed only to accept is not known
    to constrain anything."""

    def setUp(self):
        self.schema = load(os.path.join(SCHEMA_DIR, "schema-versions" + SUFFIX))
        self.valid = register()

    def accepts(self, document):
        jsonschema.Draft202012Validator(self.schema).validate(document)

    def refuses(self, document):
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(document)

    def test_the_shipped_register_is_accepted(self):
        """The control case for everything below."""
        self.accepts(self.valid)

    def test_a_record_without_breaking_changes_is_refused(self):
        document = copy.deepcopy(self.valid)
        del document["entries"][0]["history"][0]["breakingChanges"]
        self.refuses(document)

    def test_a_record_without_a_migration_action_is_refused(self):
        document = copy.deepcopy(self.valid)
        del document["entries"][0]["history"][0]["migration"]
        self.refuses(document)

    def test_an_empty_migration_action_is_refused(self):
        document = copy.deepcopy(self.valid)
        document["entries"][0]["history"][0]["migration"] = ""
        self.refuses(document)

    def test_an_empty_breaking_change_list_is_accepted(self):
        """Explicitly. An empty list is the claim that nothing breaks; the
        refusal above is of the absent field, not of the empty one."""
        document = copy.deepcopy(self.valid)
        document["entries"][0]["history"][0]["breakingChanges"] = []
        self.accepts(document)

    def test_an_empty_history_is_refused(self):
        document = copy.deepcopy(self.valid)
        document["entries"][0]["history"] = []
        self.refuses(document)

    def test_an_entry_without_a_digest_is_refused(self):
        document = copy.deepcopy(self.valid)
        del document["entries"][0]["contentDigest"]
        self.refuses(document)

    def test_an_uppercase_digest_is_refused(self):
        document = copy.deepcopy(self.valid)
        document["entries"][0]["contentDigest"] = "A" * 64
        self.refuses(document)

    def test_a_short_digest_is_refused(self):
        document = copy.deepcopy(self.valid)
        document["entries"][0]["contentDigest"] = "a" * 63
        self.refuses(document)

    def test_a_non_semantic_version_is_refused(self):
        document = copy.deepcopy(self.valid)
        document["entries"][0]["version"] = "v1"
        self.refuses(document)

    def test_a_malformed_date_is_refused(self):
        document = copy.deepcopy(self.valid)
        document["entries"][0]["history"][0]["date"] = "26/09/2026"
        self.refuses(document)

    def test_a_breaking_change_without_a_location_is_refused(self):
        document = copy.deepcopy(self.valid)
        document["entries"][0]["history"][0]["breakingChanges"] = [
            {"change": "The workload identifier is now required."}
        ]
        self.refuses(document)

    def test_an_unknown_property_is_refused(self):
        document = copy.deepcopy(self.valid)
        document["entries"][0]["supersededBy"] = "something"
        self.refuses(document)

    def test_the_registers_own_version_is_pinned(self):
        document = copy.deepcopy(self.valid)
        document["schemaVersion"] = "9.9.9"
        self.refuses(document)

    def test_an_empty_entry_list_is_refused(self):
        document = copy.deepcopy(self.valid)
        document["entries"] = []
        self.refuses(document)


class TheVersionGateRefusesBeforeStructure(unittest.TestCase):
    """A mismatched version makes every structural finding noise about a
    contract the document was never written against: all true, none the fault."""

    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory)
        source = os.path.join(REPO_ROOT, "examples", "minimal")
        self.artifact = os.path.join(self.directory, "framework-config.json")
        shutil.copy(os.path.join(source, "framework-config.json"), self.artifact)

    def write(self, document):
        with open(self.artifact, "w", encoding="utf-8") as handle:
            json.dump(document, handle)

    def current(self):
        return load(self.artifact)

    def test_the_unmodified_example_passes(self):
        """The control case. Without it, every refusal below could be the
        fixture rather than the rule."""
        findings, _ = validate.validate_artifact(self.artifact)
        self.assertEqual(findings, [])

    def test_a_mismatched_version_is_refused(self):
        document = self.current()
        document["schemaVersion"] = "9.9.9"
        self.write(document)
        findings, _ = validate.validate_artifact(self.artifact)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].pointer, "/schemaVersion")

    def test_the_mismatch_suppresses_structural_noise(self):
        """A document both out of date and malformed reports the version only."""
        document = self.current()
        document["schemaVersion"] = "9.9.9"
        document.pop("frameworkVersion", None)
        document["unknownProperty"] = "x"
        self.write(document)
        findings, _ = validate.validate_artifact(self.artifact)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].pointer, "/schemaVersion")

    def test_a_matching_version_lets_structural_findings_through(self):
        """The gate opens. Otherwise it could be refusing everything."""
        document = self.current()
        document["unknownProperty"] = "x"
        self.write(document)
        findings, _ = validate.validate_artifact(self.artifact)
        self.assertTrue(findings)
        self.assertTrue(all(f.pointer != "/schemaVersion" for f in findings))

    def test_the_message_names_the_expected_version(self):
        document = self.current()
        document["schemaVersion"] = "9.9.9"
        self.write(document)
        findings, _ = validate.validate_artifact(self.artifact)
        self.assertIn("1.0.0", findings[0].message)

    def test_the_message_never_echoes_the_declared_version(self):
        """FR-27 holds for this finding as for every other: the expected value
        comes from the schema, which is ours; the declared one came from the
        document."""
        marker = "7.7.7"
        document = self.current()
        document["schemaVersion"] = marker
        self.write(document)
        findings, _ = validate.validate_artifact(self.artifact)
        self.assertNotIn(marker, findings[0].message)

    def test_the_message_points_somewhere(self):
        document = self.current()
        document["schemaVersion"] = "9.9.9"
        self.write(document)
        findings, _ = validate.validate_artifact(self.artifact)
        self.assertIn("schema-register.md", findings[0].message)

    def test_the_message_stays_ascii(self):
        document = self.current()
        document["schemaVersion"] = "9.9.9"
        self.write(document)
        findings, _ = validate.validate_artifact(self.artifact)
        findings[0].message.encode("ascii")

    def test_a_missing_version_falls_through_to_structure(self):
        """An absent declaration is a required-property fault, which the
        structural pass already reports precisely. The gate does not intercept
        it, or the author would be told to migrate a document that has no
        version to migrate from."""
        document = self.current()
        del document["schemaVersion"]
        self.write(document)
        findings, _ = validate.validate_artifact(self.artifact)
        self.assertTrue(findings)
        self.assertTrue(any("schemaVersion" in f.message for f in findings))

    def test_a_non_string_version_falls_through_to_structure(self):
        document = self.current()
        document["schemaVersion"] = 1
        self.write(document)
        findings, _ = validate.validate_artifact(self.artifact)
        self.assertTrue(findings)

    def test_version_findings_tolerates_a_non_object_instance(self):
        self.assertEqual(validate.version_findings([], {}), [])

    def test_version_findings_is_inert_without_a_pin(self):
        self.assertEqual(validate.version_findings({"schemaVersion": "9.9.9"}, {}), [])


class TheRegisterIsItselfValidatable(unittest.TestCase):
    """The register is described by a schema in the directory it describes, so
    it is subject to the same machinery as everything else rather than being a
    file only its own tests look at."""

    def test_the_register_validates_through_the_validator(self):
        findings, _ = validate.validate_artifact(REGISTER)
        self.assertEqual(findings, [])

    def test_the_register_schema_registers_itself(self):
        self.assertIn("schema-versions", entries_by_schema())

    def test_the_register_is_a_declared_core_path(self):
        declaration = load(os.path.join(REPO_ROOT, "contracts", "core-paths.json"))
        declared = {
            entry["path"]
            for paths in declaration["categories"].values()
            for entry in paths
        }
        self.assertIn("contracts/schema-versions.json", declared)


if __name__ == "__main__":
    unittest.main()

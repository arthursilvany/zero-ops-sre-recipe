"""The English vocabulary is complete, and its provenance is recorded rather than asserted.

Two properties are under test here, and they fail in opposite directions.

The first is totality. Every enumerated value set defined anywhere in contracts/schemas/
appears in the register exactly once, and every registered pointer resolves to a real
enum whose members match verbatim. Checking only one direction would let the register
drift: a set added to a schema and never registered is silent, and a register entry
pointing at a set that was deleted is equally silent. Both are checked, and the sweep is
guarded by the counts it is expected to find, so an empty discovery cannot pass
vacuously.

The second is that reference tokens stay data. The exclusion list forbids the eight
Portuguese values as identifiers, while FR-03 requires their originals be recorded as
provenance. Those are compatible only if the tokens appear in exactly one place and in
exactly one role. That is asserted against the whole of contracts/ and examples/, not
against the vocabulary alone.

Roughly half of these cases feed the schema documents that must be rejected. A schema
observed only to accept is not known to constrain anything.
"""

import copy
import json
import os
import re
import unittest

import jsonschema

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA_DIR = os.path.join(REPO_ROOT, "contracts", "schemas")
CONTRACT_DIR = os.path.join(REPO_ROOT, "contracts")
EXAMPLE_DIR = os.path.join(REPO_ROOT, "examples")
VOCABULARY_PATH = os.path.join(
    REPO_ROOT, "contracts", "vocabulary", "vocabulary.json"
)
VOCABULARY_SCHEMA_PATH = os.path.join(SCHEMA_DIR, "vocabulary.schema.json")

# The eight values the exclusion list forbids as identifiers. They may appear as
# recorded provenance and nowhere else.
REFERENCE_TOKENS = [
    "SEM_ACESSO",
    "EVIDENCIA_INSUFICIENTE",
    "PROVISORIO",
    "COMPLETO",
    "ALTA",
    "MEDIA",
    "BAIXA",
    "INSUFICIENTE",
]

# What the sweep is expected to find. Present so that a discovery bug which returns
# nothing fails loudly instead of satisfying every "for each found" assertion.
EXPECTED_ENUM_OCCURRENCES = 51
EXPECTED_DISTINCT_VALUE_SETS = 38


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def schema_name(filename):
    return filename[: -len(".schema.json")]


def enum_sites(node, pointer, sink):
    """Yield (pointer, values) for every enum in a schema document."""
    if isinstance(node, dict):
        if isinstance(node.get("enum"), list):
            sink.append((pointer, list(node["enum"])))
        for key, value in node.items():
            enum_sites(value, pointer + "/" + key, sink)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            enum_sites(value, pointer + "/" + str(index), sink)


def discover_enums():
    """Every enum defined under contracts/schemas/, keyed by schema-name#/pointer."""
    found = {}
    for filename in sorted(os.listdir(SCHEMA_DIR)):
        if not filename.endswith(".schema.json"):
            continue
        sink = []
        enum_sites(load(os.path.join(SCHEMA_DIR, filename)), "", sink)
        for pointer, values in sink:
            found[schema_name(filename) + "#" + pointer] = values
    return found


def text_files(root):
    for directory, _, filenames in os.walk(root):
        for filename in sorted(filenames):
            if filename.endswith((".json", ".md", ".yaml", ".yml", ".py")):
                yield os.path.join(directory, filename)


class TheRegisterIsTotal(unittest.TestCase):
    """Coverage in both directions, guarded so an empty sweep cannot pass."""

    def setUp(self):
        self.vocabulary = load(VOCABULARY_PATH)
        self.enums = discover_enums()

    def test_the_sweep_finds_what_it_is_expected_to_find(self):
        # Without this, a discovery that returns nothing makes every other case in
        # this class trivially true.
        self.assertEqual(len(self.enums), EXPECTED_ENUM_OCCURRENCES)
        distinct = {tuple(values) for values in self.enums.values()}
        self.assertEqual(len(distinct), EXPECTED_DISTINCT_VALUE_SETS)

    def test_every_enum_in_every_schema_is_registered(self):
        claimed = set()
        for entry in self.vocabulary["entries"]:
            claimed.update(entry["appliesTo"])
        unregistered = sorted(set(self.enums) - claimed)
        self.assertEqual(
            unregistered,
            [],
            "enumerated value sets defined but not registered: %s" % unregistered,
        )

    def test_every_registered_pointer_resolves(self):
        dangling = []
        for entry in self.vocabulary["entries"]:
            for pointer in entry["appliesTo"]:
                if pointer not in self.enums:
                    dangling.append(pointer)
        self.assertEqual(sorted(dangling), [])

    def test_no_pointer_is_claimed_twice(self):
        seen = {}
        for entry in self.vocabulary["entries"]:
            for pointer in entry["appliesTo"]:
                self.assertNotIn(
                    pointer,
                    seen,
                    "%s claimed by both %s and %s"
                    % (pointer, seen.get(pointer), entry["name"]),
                )
                seen[pointer] = entry["name"]

    def test_registered_values_match_the_schema_verbatim(self):
        for entry in self.vocabulary["entries"]:
            for pointer in entry["appliesTo"]:
                self.assertEqual(
                    entry["values"],
                    self.enums[pointer],
                    "%s drifted from %s" % (entry["name"], pointer),
                )

    def test_a_concept_defined_in_several_schemas_agrees_across_them(self):
        multi = [e for e in self.vocabulary["entries"] if len(e["appliesTo"]) > 1]
        # capabilityClass alone spans five schemas; if this list were empty the
        # cross-schema check below would assert nothing.
        self.assertGreaterEqual(len(multi), 2)
        for entry in multi:
            sets = {tuple(self.enums[p]) for p in entry["appliesTo"]}
            self.assertEqual(
                len(sets), 1, "%s differs between schemas" % entry["name"]
            )

    def test_entry_names_are_unique(self):
        names = [entry["name"] for entry in self.vocabulary["entries"]]
        self.assertEqual(len(names), len(set(names)))


class ProvenanceIsRecordedNotAsserted(unittest.TestCase):
    """An entry that renames nothing still has to say why."""

    def setUp(self):
        self.vocabulary = load(VOCABULARY_PATH)

    def test_every_entry_carries_a_substantive_note(self):
        for entry in self.vocabulary["entries"]:
            note = entry["note"]
            self.assertGreaterEqual(len(note), 60, entry["name"])
            # A note that only restates the name records nothing.
            stripped = re.sub(r"[^a-z]", "", note.lower())
            self.assertNotEqual(stripped, entry["name"].lower())

    def test_a_reference_derived_entry_maps_or_explains(self):
        derived = [
            e for e in self.vocabulary["entries"] if e["origin"] == "referenceDerived"
        ]
        self.assertGreaterEqual(len(derived), 5)
        for entry in derived:
            if "referenceValues" in entry:
                continue
            # No mapping means the reference had no counterpart, or its
            # counterpart was deliberately dropped. Either way the note has to
            # engage with the reference rather than describe the values alone.
            self.assertIn(
                "reference",
                entry["note"].lower(),
                "%s claims reference ancestry, maps nothing and explains nothing"
                % entry["name"],
            )

    def test_every_mapped_value_is_one_the_entry_actually_declares(self):
        mapped = 0
        for entry in self.vocabulary["entries"]:
            for pair in entry.get("referenceValues", []):
                mapped += 1
                self.assertIn(pair["value"], entry["values"], entry["name"])
        self.assertGreaterEqual(mapped, 8)

    def test_a_reference_token_is_never_mapped_from_two_concepts_inconsistently(self):
        # SEM_ACESSO legitimately appears under two concepts. Both must rename it
        # the same way, or the contract carries two spellings of one state.
        spellings = {}
        for entry in self.vocabulary["entries"]:
            for pair in entry.get("referenceValues", []):
                spellings.setdefault(pair["referenceValue"], set()).add(pair["value"])
        self.assertIn("SEM_ACESSO", spellings)
        self.assertEqual(spellings["SEM_ACESSO"], {"accessDenied"})

    def test_framework_originated_entries_claim_no_ancestry(self):
        originated = [
            e
            for e in self.vocabulary["entries"]
            if e["origin"] == "frameworkOriginated"
        ]
        self.assertGreaterEqual(len(originated), 5)
        for entry in originated:
            self.assertNotIn("referenceValues", entry)


class ReferenceTokensStayData(unittest.TestCase):
    """The exclusion list and FR-03 coexist only if the tokens appear in one role."""

    def setUp(self):
        self.vocabulary = load(VOCABULARY_PATH)

    def _occurrences(self, token):
        pattern = re.compile(r"(?<![A-Z_])" + token + r"(?![A-Z_])")
        hits = []
        for root in (CONTRACT_DIR, EXAMPLE_DIR):
            for path in text_files(root):
                with open(path, encoding="utf-8") as handle:
                    for number, line in enumerate(handle, start=1):
                        if pattern.search(line):
                            hits.append((os.path.relpath(path, REPO_ROOT), number))
        return hits

    def test_every_forbidden_token_is_recorded_exactly_once_as_provenance(self):
        recorded = set()
        for entry in self.vocabulary["entries"]:
            for pair in entry.get("referenceValues", []):
                recorded.add(pair["referenceValue"])
        missing = [t for t in REFERENCE_TOKENS if t not in recorded]
        self.assertEqual(
            missing, [], "renamed without recording the original: %s" % missing
        )

    def test_a_forbidden_token_appears_nowhere_outside_the_vocabulary(self):
        for token in REFERENCE_TOKENS:
            stray = [
                hit
                for hit in self._occurrences(token)
                if hit[0].replace("\\", "/") != "contracts/vocabulary/vocabulary.json"
            ]
            self.assertEqual(
                stray, [], "%s leaked outside the vocabulary: %s" % (token, stray)
            )

    def test_a_forbidden_token_is_never_a_canonical_value_or_a_concept_name(self):
        for entry in self.vocabulary["entries"]:
            self.assertNotIn(entry["name"], REFERENCE_TOKENS)
            for value in entry["values"]:
                self.assertNotIn(value, REFERENCE_TOKENS)

    def test_the_search_can_actually_find_something(self):
        # Guards the regex: if it matched nothing anywhere, the leak check above
        # would pass no matter what the repository contained.
        self.assertGreaterEqual(len(self._occurrences("SEM_ACESSO")), 2)


class FrThreeNamesAreCovered(unittest.TestCase):
    """The concepts FR-03 names by hand exist, spelled consistently."""

    def setUp(self):
        self.vocabulary = load(VOCABULARY_PATH)
        self.by_name = {e["name"]: e for e in self.vocabulary["entries"]}
        self.enums = discover_enums()

    def test_the_named_concepts_are_registered(self):
        for name in (
            "executionState",
            "provenanceClassification",
            "unobservedReason",
            "assessmentStatus",
            "confidence",
        ):
            self.assertIn(name, self.by_name)

    def test_access_denied_is_spelled_identically_wherever_it_appears(self):
        carriers = [
            entry
            for entry in self.vocabulary["entries"]
            if "accessDenied" in entry["values"]
        ]
        self.assertGreaterEqual(len(carriers), 2)
        for entry in carriers:
            for pointer in entry["appliesTo"]:
                self.assertIn("accessDenied", self.enums[pointer])
        # The near-miss spelling must not survive anywhere in the schemas.
        for pointer, values in self.enums.items():
            self.assertNotIn("deniedAccess", values, pointer)

    def test_no_registered_value_is_non_english_or_accented(self):
        for entry in self.vocabulary["entries"]:
            for value in entry["values"]:
                self.assertRegex(value, r"^[a-z][A-Za-z0-9]*$", entry["name"])


class TheVocabularySchemaRejects(unittest.TestCase):
    """Half the point of a schema is what it refuses."""

    def setUp(self):
        self.schema = load(VOCABULARY_SCHEMA_PATH)
        self.validator = jsonschema.Draft202012Validator(self.schema)
        self.document = load(VOCABULARY_PATH)

    def _mutate(self, change):
        document = copy.deepcopy(self.document)
        change(document)
        return document

    def _assert_rejected(self, document, reason):
        self.assertFalse(
            self.validator.is_valid(document),
            "accepted a document that should have been refused: %s" % reason,
        )

    def test_the_shipped_vocabulary_is_accepted(self):
        jsonschema.Draft202012Validator.check_schema(self.schema)
        errors = sorted(self.validator.iter_errors(self.document), key=str)
        self.assertEqual([e.message for e in errors], [])

    def test_a_framework_originated_entry_cannot_claim_provenance(self):
        def change(document):
            entry = next(
                e for e in document["entries"] if e["origin"] == "frameworkOriginated"
            )
            entry["referenceValues"] = [
                {"value": entry["values"][0], "referenceValue": "COMPLETO"}
            ]

        self._assert_rejected(self._mutate(change), "invented ancestry")

    def test_a_reference_token_cannot_be_a_concept_name(self):
        def change(document):
            document["entries"][0]["name"] = "SEM_ACESSO"

        self._assert_rejected(self._mutate(change), "token as identifier")

    def test_a_reference_token_cannot_be_a_canonical_value(self):
        def change(document):
            document["entries"][0]["values"] = ["PROVISORIO"]

        self._assert_rejected(self._mutate(change), "token as value")

    def test_an_accented_value_is_refused(self):
        def change(document):
            document["entries"][0]["values"] = ["provis\u00f3rio"]

        self._assert_rejected(self._mutate(change), "not English by construction")

    def test_a_trivial_note_is_refused(self):
        def change(document):
            document["entries"][0]["note"] = "Renamed."

        self._assert_rejected(self._mutate(change), "note records nothing")

    def test_an_entry_without_a_note_is_refused(self):
        def change(document):
            del document["entries"][0]["note"]

        self._assert_rejected(self._mutate(change), "silent rename")

    def test_an_entry_without_a_location_is_refused(self):
        def change(document):
            document["entries"][0]["appliesTo"] = []

        self._assert_rejected(self._mutate(change), "unanchored entry")

    def test_a_pointer_cannot_escape_the_schema_directory(self):
        for pointer in (
            "../secrets#/a",
            "contracts/schemas/scope-contract#/a",
            "scope-contract.schema.json#/a",
            "scope-contract",
        ):
            def change(document, pointer=pointer):
                document["entries"][0]["appliesTo"] = [pointer]

            self._assert_rejected(self._mutate(change), pointer)

    def test_an_unknown_origin_is_refused(self):
        def change(document):
            document["entries"][0]["origin"] = "unknown"

        self._assert_rejected(self._mutate(change), "provenance gap as an answer")

    def test_an_unknown_property_is_refused(self):
        def change(document):
            document["entries"][0]["waived"] = True

        self._assert_rejected(self._mutate(change), "unknown property")

    def test_a_missing_schema_version_is_refused(self):
        def change(document):
            del document["schemaVersion"]

        self._assert_rejected(self._mutate(change), "unversioned register")

    def test_an_empty_register_is_refused(self):
        def change(document):
            document["entries"] = []

        self._assert_rejected(self._mutate(change), "totality by vacancy")

    def test_a_mapping_missing_its_original_is_refused(self):
        def change(document):
            entry = next(e for e in document["entries"] if "referenceValues" in e)
            del entry["referenceValues"][0]["referenceValue"]

        self._assert_rejected(self._mutate(change), "half-recorded rename")

    def test_a_lower_case_original_is_refused(self):
        def change(document):
            entry = next(e for e in document["entries"] if "referenceValues" in e)
            entry["referenceValues"][0]["referenceValue"] = "completo"

        self._assert_rejected(self._mutate(change), "original indistinguishable")

    def test_duplicate_values_within_an_entry_are_refused(self):
        def change(document):
            first = document["entries"][0]["values"][0]
            document["entries"][0]["values"] = [first, first]

        self._assert_rejected(self._mutate(change), "duplicate member")


class TheRegisterIsDeclaredAndDescribed(unittest.TestCase):
    """The register is only reachable if the repository declares it."""

    def test_the_vocabulary_directory_is_a_present_core_path(self):
        declaration = load(os.path.join(CONTRACT_DIR, "core-paths.json"))
        paths = [
            entry
            for category in declaration["categories"].values()
            for entry in category
        ]
        self.assertGreater(len(paths), 10)
        matches = [p for p in paths if p["path"] == "contracts/vocabulary/"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["status"], "present")

    def test_the_register_lists_the_vocabulary_schema(self):
        with open(
            os.path.join(CONTRACT_DIR, "schema-register.md"), encoding="utf-8"
        ) as handle:
            register = handle.read()
        self.assertIn("`vocabulary.schema.json`", register)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""NEG-I: no core schema leaves a way in.

Evidence for User Story 2. This is SEC-013 and FR-49, and its third rule is
the third leg of NEG-E's containment argument: that check names free-form
fields as the boundary it cannot see, and this one closes it.

Three rules, which fail for different reasons on purpose:

1.  Closed objects, required where a shape is defined and nowhere else. The
    exemption for `if`/`then` is evidence-driven: all fifteen open objects in
    this repository are conditionals, and closing one makes it never match.
2.  No secret-named property. The vocabulary was checked against the 180
    property names these schemas actually declare before it was written.
3.  No free-form field. Structure only; prose fields exist by design and the
    module says so rather than banning `description` and taking an exception.

Every test here makes the check fail, and each pairs with a control that makes
it pass by changing only the thing under test.

Run with:
    python -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from zeroops import core_paths  # noqa: E402
from zeroops import instructions  # noqa: E402
from zeroops import schema_lint  # noqa: E402


def schema(**body):
    """A minimal valid-shaped schema document, closed unless told otherwise.

    Carries `$id` because an earlier check requires one; without it every
    synthetic schema here would also trip that rule and these assertions would
    be reading somebody else's finding.
    """
    document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.invalid/synthetic.schema.json",
    }
    document.update(body)
    return document


def reasons(document):
    return [reason for _, reason in schema_lint.shape_findings(document)]


class TheRealRepositoryIsClean(unittest.TestCase):
    """The control for everything below, plus proof it looked at something."""

    def setUp(self):
        self.root = core_paths.repo_root()
        self.files = core_paths.tracked_files(self.root)
        self.declaration = core_paths.load_declaration(self.root)

    def scan(self):
        return schema_lint.scan(self.root, self.files, self.declaration)

    def test_no_core_schema_leaves_a_way_in(self):
        problems, _ = self.scan()
        self.assertEqual([], problems)

    def test_schemas_were_examined(self):
        # A scan of nothing reports nothing and is indistinguishable from a
        # clean repository.
        _, examined = self.scan()
        self.assertGreater(examined["schemas"], 0)

    def test_instances_were_examined(self):
        # Counted apart from schemas: the closure and free-form rules only
        # apply to schemas, so a run that stopped recognising instances would
        # still report a healthy schema count.
        _, examined = self.scan()
        self.assertGreater(examined["instances"], 0)

    def test_the_two_counts_are_reported_apart(self):
        _, examined = self.scan()
        self.assertEqual({"schemas", "instances"}, set(examined))

    def test_every_scanned_json_file_is_counted_once(self):
        _, examined = self.scan()
        chosen = instructions.scanned_paths(self.files, self.declaration)
        expected = len([p for p in chosen if p.lower().endswith(".json")])
        self.assertEqual(expected, examined["schemas"] + examined["instances"])


class ClosureIsRequiredWhereAShapeIsDefined(unittest.TestCase):
    def test_an_open_root_is_a_finding(self):
        self.assertIn(
            schema_lint.CLOSED, reasons(schema(properties={"a": {"type": "string"}}))
        )

    def test_a_closed_root_is_clean(self):
        self.assertEqual(
            [],
            reasons(
                schema(properties={"a": {"type": "string"}}, additionalProperties=False)
            ),
        )

    def test_additional_properties_true_does_not_satisfy_closure(self):
        # The control for a check that merely looked for the key.
        self.assertIn(
            schema_lint.CLOSED,
            reasons(
                schema(properties={"a": {"type": "string"}}, additionalProperties=True)
            ),
        )

    def test_an_open_def_is_a_finding(self):
        found = reasons(
            schema(
                additionalProperties=False,
                properties={},
                **{"$defs": {"entry": {"properties": {"a": {"type": "string"}}}}}
            )
        )
        self.assertIn(schema_lint.CLOSED, found)

    def test_an_open_nested_property_object_is_a_finding(self):
        found = reasons(
            schema(
                additionalProperties=False,
                properties={
                    "inner": {"type": "object", "properties": {"a": {"type": "string"}}}
                },
            )
        )
        self.assertIn(schema_lint.CLOSED, found)

    def test_an_open_array_item_object_is_a_finding(self):
        found = reasons(
            schema(
                additionalProperties=False,
                properties={
                    "list": {
                        "type": "array",
                        "items": {"properties": {"a": {"type": "string"}}},
                    }
                },
            )
        )
        self.assertIn(schema_lint.CLOSED, found)

    def test_the_location_names_the_open_object(self):
        found = schema_lint.shape_findings(
            schema(
                additionalProperties=False,
                properties={},
                **{"$defs": {"entry": {"properties": {"a": {"type": "string"}}}}}
            )
        )
        locations = [where for where, reason in found if reason == schema_lint.CLOSED]
        self.assertEqual(["/$defs/entry"], locations)


class ConditionalsAreExemptAndTheExemptionIsNarrow(unittest.TestCase):
    """All fifteen open objects in this repository are `if` or `then`.

    Closing an `if` makes it reject every instance carrying the properties its
    sibling `then` describes, so the branch never fires and the conditional
    validates everything. Requiring closure there would break the contract
    silently.
    """

    def conditional(self, **outer):
        body = {
            "additionalProperties": False,
            "properties": {"status": {"type": "string"}},
            "allOf": [
                {
                    "if": {"properties": {"status": {"const": "present"}}},
                    "then": {"properties": {"path": {"type": "string"}}},
                    "else": {"properties": {"note": {"type": "string"}}},
                }
            ],
        }
        body.update(outer)
        return schema(**body)

    def test_an_open_if_is_not_a_finding(self):
        self.assertEqual([], reasons(self.conditional()))

    def test_the_real_repository_really_does_have_open_conditionals(self):
        # Without this the exemption could be exempting nothing.
        root = core_paths.repo_root()
        path = os.path.join(
            root, "contracts", "schemas", "handoff-record.schema.json"
        )
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        branches = document["allOf"]
        open_conditionals = [
            b
            for b in branches
            if "properties" in b.get("if", {})
            and b["if"].get("additionalProperties") is not False
        ]
        self.assertTrue(open_conditionals)

    def test_a_not_branch_is_exempt(self):
        self.assertEqual(
            [],
            reasons(
                schema(
                    additionalProperties=False,
                    properties={"a": {"type": "string"}},
                    **{"not": {"properties": {"b": {"const": 1}}}}
                )
            ),
        )

    def test_the_exemption_does_not_leak_to_the_schema_that_owns_it(self):
        # The hole the exemption would otherwise leave: a root whose properties
        # all live under allOf branches has nothing of its own to close, so the
        # requirement lands on it whenever a branch names properties.
        self.assertIn(
            schema_lint.CLOSED,
            reasons(schema(allOf=[{"properties": {"a": {"type": "string"}}}])),
        )

    def test_closing_that_root_clears_it(self):
        self.assertEqual(
            [],
            reasons(
                schema(
                    additionalProperties=False,
                    allOf=[{"properties": {"a": {"type": "string"}}}],
                )
            ),
        )

    def test_a_branch_nested_two_deep_still_reaches_the_owner(self):
        self.assertIn(
            schema_lint.CLOSED,
            reasons(
                schema(oneOf=[{"anyOf": [{"properties": {"a": {"type": "string"}}}]}])
            ),
        )

    def test_a_schema_with_no_properties_anywhere_needs_no_closure(self):
        # The control: closure is required of objects, not of every schema.
        self.assertEqual([], reasons(schema(type="string", pattern="^a$")))


class TheSecretVocabularyWasCheckedAgainstRealNames(unittest.TestCase):
    def declared_names(self):
        root = core_paths.repo_root()
        names = set()
        for path in instructions.scanned_paths(
            core_paths.tracked_files(root), core_paths.load_declaration(root)
        ):
            if not path.endswith(".json"):
                continue
            with open(os.path.join(root, path.replace("/", os.sep)), encoding="utf-8") as h:
                document = json.load(h)
            for name, _ in schema_lint.declared_property_names(document):
                names.add(name)
        return names

    def test_idempotency_key_exists_and_is_clean(self):
        # Why `key` alone is not a marker. It is not secret material, and it is
        # the mechanism that makes a retried write safe.
        self.assertIn("idempotencyKey", self.declared_names())
        self.assertIsNone(schema_lint.secret_marker("idempotencyKey"))

    def test_key_alone_is_not_a_marker(self):
        self.assertNotIn(("key",), schema_lint.SECRET_MARKERS)

    def test_credential_ref_exists_and_is_clean(self):
        # A rule that flagged credentialRef would flag the mitigation.
        self.assertIn("credentialRef", self.declared_names())
        self.assertIsNone(schema_lint.secret_marker("credentialRef"))

    def test_the_bare_word_is_still_a_finding(self):
        # The control that keeps the reference exemption narrow: without it,
        # the clean result above would also hold for a rule carrying no
        # credential marker at all.
        self.assertEqual("credential", schema_lint.secret_marker("credential"))

    def test_no_marker_fires_on_any_name_this_repository_already_declares(self):
        offenders = {
            name: schema_lint.secret_marker(name)
            for name in self.declared_names()
            if schema_lint.secret_marker(name)
        }
        self.assertEqual({}, offenders)

    def test_the_reference_convention_is_widespread_enough_to_rely_on(self):
        # The exemption rests on `Ref` meaning locator throughout these
        # contracts, not on one name.
        refs = [n for n in self.declared_names() if n.endswith("Ref")]
        self.assertGreater(len(refs), 5, refs)


class EverySecretMarkerIsExercisedOnItsOwn(unittest.TestCase):
    EXAMPLES = {
        ("secret",): "secret",
        ("secrets",): "secrets",
        ("password",): "password",
        ("passwd",): "passwd",
        ("token",): "token",
        ("credential",): "credential",
        ("credentials",): "credentials",
        ("api", "key"): "apiKey",
        ("private", "key"): "privateKey",
        ("connection", "string"): "connectionString",
        ("certificate",): "certificate",
        ("thumbprint",): "thumbprint",
        ("bearer",): "bearer",
        ("pfx",): "pfx",
        ("pem",): "pem",
        ("sas",): "sas",
    }

    def test_each_marker_has_an_example(self):
        # The guard: adding a marker without an example leaves it unexercised,
        # and an unexercised marker can be deleted with nothing failing.
        self.assertEqual(set(schema_lint.SECRET_MARKERS), set(self.EXAMPLES))

    def test_each_example_trips_only_its_own_marker(self):
        for marker, name in self.EXAMPLES.items():
            with self.subTest(name=name):
                self.assertEqual(" ".join(marker), schema_lint.secret_marker(name))

    def test_no_marker_is_a_prefix_of_a_longer_one(self):
        # `api key` and `key` would be ambiguous. `key` is absent, so the
        # compound forms are unambiguous; this keeps it that way.
        singles = {m[0] for m in schema_lint.SECRET_MARKERS if len(m) == 1}
        for marker in schema_lint.SECRET_MARKERS:
            if len(marker) > 1:
                with self.subTest(marker=marker):
                    self.assertEqual(set(), set(marker) & singles)


class SecretNamesAreFoundWhereverTheyAppear(unittest.TestCase):
    def test_a_top_level_property(self):
        problems = schema_lint.shape_findings(schema())
        self.assertEqual([], problems)
        names = schema_lint.declared_property_names(
            schema(additionalProperties=False, properties={"apiKey": {"type": "string"}})
        )
        self.assertIn(("apiKey", "/properties/apiKey"), names)

    def test_a_nested_property(self):
        names = dict(
            schema_lint.declared_property_names(
                schema(
                    additionalProperties=False,
                    properties={
                        "auth": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {"clientSecret": {"type": "string"}},
                        }
                    },
                )
            )
        )
        self.assertIn("clientSecret", names)
        self.assertEqual("secret", schema_lint.secret_marker("clientSecret"))

    def test_snake_case_is_found(self):
        self.assertEqual("api key", schema_lint.secret_marker("api_key"))

    def test_screaming_case_is_found(self):
        self.assertEqual("connection string", schema_lint.secret_marker("CONNECTION_STRING"))

    def test_a_word_merely_containing_a_marker_is_clean(self):
        self.assertIsNone(schema_lint.secret_marker("tokeniser"))

    def test_only_a_trailing_ref_exempts(self):
        # A mutant that accepted `ref` anywhere in the name passed everything,
        # because every reference under test had it last. `refSecret` names the
        # material, not a locator, and reading the word positionally is what
        # tells the two apart.
        self.assertEqual("secret", schema_lint.secret_marker("refSecret"))
        self.assertIsNone(schema_lint.secret_marker("secretRef"))

    def test_the_two_checks_share_one_splitter(self):
        # A second spelling of the word splitter could drift from the first,
        # and then one check would accept a name the other rejected with no
        # test reading both.
        self.assertIs(schema_lint.words_of, instructions.words_of)


class FreeFormFieldsAreRefused(unittest.TestCase):
    """The third leg of NEG-E's containment argument."""

    def test_an_untyped_object_is_a_bag(self):
        self.assertEqual(schema_lint.BAG, schema_lint.free_form_reason({"type": "object"}))

    def test_an_object_with_properties_is_not_a_bag(self):
        self.assertIsNone(
            schema_lint.free_form_reason(
                {"type": "object", "properties": {"a": {"type": "string"}}}
            )
        )

    def test_additional_properties_true_is_refused(self):
        self.assertEqual(
            schema_lint.OPEN_TRUE,
            schema_lint.free_form_reason(
                {"type": "object", "properties": {}, "additionalProperties": True}
            ),
        )

    def test_a_map_is_refused(self):
        self.assertEqual(
            schema_lint.OPEN_MAP,
            schema_lint.free_form_reason(
                {"type": "object", "additionalProperties": {"type": "string"}}
            ),
        )

    def test_an_array_without_items_is_refused(self):
        self.assertEqual(
            schema_lint.LOOSE_ARRAY, schema_lint.free_form_reason({"type": "array"})
        )

    def test_an_array_with_items_is_clean(self):
        self.assertIsNone(
            schema_lint.free_form_reason({"type": "array", "items": {"type": "string"}})
        )

    def test_a_schema_with_no_constraint_at_all_is_refused(self):
        self.assertEqual(
            schema_lint.UNCONSTRAINED,
            schema_lint.free_form_reason({"description": "anything"}),
        )

    def test_a_union_type_including_object_is_refused(self):
        self.assertEqual(
            schema_lint.UNION_OBJECT,
            schema_lint.free_form_reason({"type": ["object", "string"]}),
        )

    def test_a_nullable_union_is_clean(self):
        # The control. Nullable scalars are the repository's own convention and
        # a rule that refused them would refuse what is already committed.
        self.assertIsNone(schema_lint.free_form_reason({"type": ["string", "null"]}))

    def test_a_ref_is_clean(self):
        self.assertIsNone(schema_lint.free_form_reason({"$ref": "#/$defs/thing"}))

    def test_an_object_constrained_by_a_ref_is_not_a_bag(self):
        # A mutant that ignored the sibling $ref passed everything, because no
        # test paired `type: object` with one. In 2020-12 a $ref composes with
        # its siblings, so the referenced schema is what names the properties;
        # calling that a bag would refuse a legitimate spelling.
        self.assertIsNone(
            schema_lint.free_form_reason(
                {"type": "object", "$ref": "#/$defs/entry"}
            )
        )
        # The control, so the clean result above is not just a rule that
        # stopped looking at objects.
        self.assertEqual(
            schema_lint.BAG, schema_lint.free_form_reason({"type": "object"})
        )

    def test_an_enum_is_clean(self):
        self.assertIsNone(schema_lint.free_form_reason({"enum": ["a", "b"]}))

    def test_a_plain_string_is_clean(self):
        # Named out loud in the module: prose fields exist by design, and this
        # rule is about structure. Banning `description` would take an
        # exception on first use.
        self.assertIsNone(schema_lint.free_form_reason({"type": "string"}))

    def test_a_free_form_property_is_reported_with_its_location(self):
        found = schema_lint.shape_findings(
            schema(additionalProperties=False, properties={"payload": {"type": "object"}})
        )
        self.assertIn(("/properties/payload", schema_lint.BAG), found)


class SchemasAndInstancesAreTreatedDifferently(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "core", "policy"))
        self.declaration = {
            "categories": {"core": [{"path": "core/policy/"}], "binding": []}
        }

    def write(self, name, document):
        with open(
            os.path.join(self.root, "core", "policy", name), "w", encoding="utf-8"
        ) as handle:
            json.dump(document, handle)
        return ["core/policy/" + name]

    def test_a_schema_is_recognised_by_its_dollar_schema(self):
        self.assertTrue(schema_lint.is_schema_document(schema()))

    def test_an_instance_is_not(self):
        self.assertFalse(schema_lint.is_schema_document({"defaultDecision": "deny"}))

    def test_an_instance_is_not_held_to_the_closure_rule(self):
        # An instance has no additionalProperties to declare. Holding it to the
        # rule would report every instance document in the repository.
        files = self.write("policy.json", {"defaultDecision": "deny", "rules": []})
        problems, examined = schema_lint.scan(self.root, files, self.declaration)
        self.assertEqual([], problems)
        self.assertEqual(1, examined["instances"])
        self.assertEqual(0, examined["schemas"])

    def test_an_instance_key_naming_a_secret_is_still_a_finding(self):
        files = self.write("policy.json", {"clientSecret": "x"})
        problems, _ = schema_lint.scan(self.root, files, self.declaration)
        self.assertEqual(1, len(problems))
        self.assertIn("clientSecret", problems[0])

    def test_a_secret_key_nested_in_an_instance_array_is_found(self):
        files = self.write("policy.json", {"entries": [{"password": "x"}]})
        problems, _ = schema_lint.scan(self.root, files, self.declaration)
        self.assertEqual(1, len(problems))
        self.assertIn("/entries/0/password", problems[0])

    def test_a_schema_is_held_to_all_three_rules(self):
        files = self.write(
            "thing.schema.json",
            schema(properties={"token": {"type": "object"}}),
        )
        problems, examined = schema_lint.scan(self.root, files, self.declaration)
        self.assertEqual(1, examined["schemas"])
        self.assertEqual(3, len(problems), problems)
        self.assertTrue(any(schema_lint.CLOSED in p for p in problems))
        self.assertTrue(any(schema_lint.BAG in p for p in problems))
        self.assertTrue(any(schema_lint.SECRET in p for p in problems))


class TheGateRunsTheCheck(unittest.TestCase):
    """A check wired nowhere is a function. These go through check()."""

    def declaration(self):
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
        target = os.path.join(root, core_paths.SCHEMA_PATH.replace("/", os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(
            os.path.join(REPO_ROOT, core_paths.SCHEMA_PATH.replace("/", os.sep)), target
        )
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        return root

    def write(self, root, relative, document):
        full = os.path.join(root, relative.replace("/", os.sep))
        with open(full, "w", encoding="utf-8") as handle:
            json.dump(document, handle)

    def offending(self, document, name="core/policy/x.schema.json"):
        root = self.synthetic_repo()
        self.write(root, name, document)
        problems = core_paths.check(root=root, declaration=self.declaration())
        return [p for p in problems if name in p]

    def test_the_gate_reports_an_open_object(self):
        found = self.offending(schema(properties={"a": {"type": "string"}}))
        self.assertEqual(1, len(found), found)
        self.assertIn(schema_lint.CLOSED, found[0])

    def test_the_gate_reports_a_secret_named_property(self):
        found = self.offending(
            schema(additionalProperties=False, properties={"password": {"type": "string"}})
        )
        self.assertEqual(1, len(found), found)
        self.assertIn(schema_lint.SECRET, found[0])

    def test_the_gate_reports_a_free_form_field(self):
        found = self.offending(
            schema(additionalProperties=False, properties={"payload": {"type": "object"}})
        )
        self.assertEqual(1, len(found), found)
        self.assertIn(schema_lint.BAG, found[0])

    def test_the_gate_accepts_a_clean_schema(self):
        """The control. A gate reporting every core file would satisfy all
        three assertions above."""
        self.assertEqual(
            [],
            self.offending(
                schema(additionalProperties=False, properties={"a": {"type": "string"}})
            ),
        )

    def test_the_real_repository_passes_the_gate(self):
        self.assertEqual([], core_paths.check())


class TheContainmentArgumentIsNowWhole(unittest.TestCase):
    """NEG-E names free-form fields as the boundary it cannot see, and NEG-H's
    first rule is what makes both safe. All three run from one gate, so none
    can be dropped while the others keep reporting success."""

    def called_from_check(self):
        source = os.path.join(REPO_ROOT, "tools", "zeroops", "core_paths.py")
        with open(source, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "check":
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call):
                        name = getattr(inner.func, "id", None)
                        if name:
                            called.add(name)
        return called

    def test_all_three_legs_run_from_the_one_gate(self):
        called = self.called_from_check()
        self.assertIn("check_call_sites", called)
        self.assertIn("check_instruction_regions", called)
        self.assertIn("check_schema_lint", called)

    def test_a_free_form_field_would_have_let_instruction_text_through(self):
        # The concrete case NEG-E documented and left open: a bag under an
        # innocuous key can hold anything, including an assembled prompt.
        self.assertEqual(
            schema_lint.BAG, schema_lint.free_form_reason({"type": "object"})
        )
        self.assertIsNone(instructions.marker_of("metadata"))


class BadInputIsSkippedRatherThanReported(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "core", "policy"))
        self.declaration = {
            "categories": {"core": [{"path": "core/policy/"}], "binding": []}
        }

    def test_malformed_json_is_skipped(self):
        with open(
            os.path.join(self.root, "core", "policy", "x.json"), "w", encoding="utf-8"
        ) as handle:
            handle.write("{not json")
        problems, examined = schema_lint.scan(
            self.root, ["core/policy/x.json"], self.declaration
        )
        self.assertEqual([], problems)
        self.assertEqual(0, examined["schemas"] + examined["instances"])

    def test_an_absent_file_is_skipped(self):
        problems, examined = schema_lint.scan(
            self.root, ["core/policy/gone.json"], self.declaration
        )
        self.assertEqual([], problems)
        self.assertEqual(0, examined["schemas"] + examined["instances"])

    def test_a_python_file_is_not_parsed_as_json(self):
        # scanned_paths is shared with the instruction-region check, which also
        # reads .py. Without this the first Python core path would be reported
        # as malformed JSON, or worse, silently skipped and counted.
        with open(
            os.path.join(self.root, "core", "policy", "x.py"), "w", encoding="utf-8"
        ) as handle:
            handle.write("limit = 3\n")
        problems, examined = schema_lint.scan(
            self.root, ["core/policy/x.py"], self.declaration
        )
        self.assertEqual([], problems)
        self.assertEqual(0, examined["schemas"] + examined["instances"])

    def test_a_python_file_that_is_also_valid_json_is_still_not_scanned(self):
        # A mutant that dropped the suffix filter passed everything, because
        # every Python file under test failed to parse as JSON and was skipped
        # for the wrong reason. A bare dict literal is both a valid Python
        # module and a valid JSON document, so only the filter separates them,
        # and the instruction-region check is what reads Python.
        with open(
            os.path.join(self.root, "core", "policy", "y.py"), "w", encoding="utf-8"
        ) as handle:
            handle.write('{"password": 1}\n')
        problems, examined = schema_lint.scan(
            self.root, ["core/policy/y.py"], self.declaration
        )
        self.assertEqual([], problems)
        self.assertEqual(0, examined["schemas"] + examined["instances"])


if __name__ == "__main__":
    unittest.main()

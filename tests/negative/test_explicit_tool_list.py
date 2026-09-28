#!/usr/bin/env python3
"""NEG-D: an emitted agent binding lacking an explicit tool list fails.

This is the evidence for User Story 2 acceptance criterion 4, and the NEG-D half
of CC-021. It is SEC-001's third layer: the first is the read-scoped RBAC grant
that Azure Resource Manager enforces, the second is the deployment-time role
audit, and this one is the assertion that the binding handed to the runtime
names what the agent may do rather than letting the runtime decide.

Every test here makes the check fail, and each one pairs with a control that
makes it pass by changing only the thing under test. A check that is only ever
shown rejecting is not known to accept anything, and one only ever shown
accepting has not been shown to reject.

Run with:
    python -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import copy
import json
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from zeroops import binding  # noqa: E402
from zeroops import core_paths  # noqa: E402

POINTER = "/toolConfiguration/allowedTools"

# A mapping shaped like the contract, carrying a location and no runtime name
# this repository recognises. The runtime identifiers are placeholders on
# purpose: NFR-02 forbids a customer environment identifier in a committed file,
# and FR-04 keeps a real runtime's names out of everything but core/binding/.
MAPPING = {
    "schemaVersion": "1.1.0",
    "runtimeName": "example-runtime",
    "runtimeVersion": "1.0.0",
    "verificationState": "unverified",
    "toolListPointer": POINTER,
    "entries": [
        {
            "capabilityClass": "readMetrics",
            "runtimeToolNames": ["example.readMetrics"],
        }
    ],
}


def emitted(**overrides):
    document = {
        "name": "example-agent",
        "toolConfiguration": {"allowedTools": ["example.readMetrics"]},
    }
    document.update(overrides)
    return document


def mapping(**overrides):
    document = copy.deepcopy(MAPPING)
    document.update(overrides)
    return document


class TheControlPasses(unittest.TestCase):
    """If this fails, no rejection below proves anything.

    Every other test in this file asserts a refusal. Without a case the check
    accepts, all of them would still pass against a function that refused
    everything, including a correct binding.
    """

    def test_a_binding_naming_its_tools_is_accepted(self):
        self.assertEqual(binding.tool_list_findings(emitted(), mapping()), [])


class AnOmittedToolListFails(unittest.TestCase):
    """Acceptance criterion 4, stated three ways, because a list can go missing
    at three different depths and a check that catches one is not evidence for
    the others."""

    def refusal(self, document, mapping_document=None):
        findings = binding.tool_list_findings(
            document, mapping_document if mapping_document is not None else mapping()
        )
        self.assertEqual(len(findings), 1, findings)
        return findings[0]

    def test_the_whole_tool_section_is_missing(self):
        document = emitted()
        del document["toolConfiguration"]
        self.assertIn(POINTER, self.refusal(document))

    def test_the_section_is_present_and_the_list_is_not(self):
        document = emitted(toolConfiguration={"model": "example-model"})
        self.assertIn(POINTER, self.refusal(document))

    def test_a_binding_that_is_entirely_empty_fails(self):
        self.assertIn(POINTER, self.refusal({}))

    def test_the_refusal_says_the_binding_carries_no_tool_list(self):
        document = emitted()
        del document["toolConfiguration"]
        self.assertIn("carries no tool list", self.refusal(document))


class AnEmptyToolListFails(unittest.TestCase):
    """An empty list is the case the agent-definition schema deliberately
    allows and this layer deliberately does not.

    In a definition, `capabilities: []` is an author saying the agent gets
    nothing. In an emitted binding the same value is indistinguishable from an
    emitter that lost the list, and a serializer that drops empty collections
    turns it into the absent property NEG-D exists to prevent.
    """

    def test_an_empty_list_is_refused(self):
        document = emitted(toolConfiguration={"allowedTools": []})
        findings = binding.tool_list_findings(document, mapping())
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("empty list", findings[0])

    def test_the_refusal_names_the_reason_rather_than_the_rule(self):
        document = emitted(toolConfiguration={"allowedTools": []})
        findings = binding.tool_list_findings(document, mapping())
        self.assertIn("unverified", findings[0])

    def test_one_tool_is_enough_to_pass(self):
        # The control for the rule above: the list, not its contents, is what
        # this check is about.
        document = emitted(toolConfiguration={"allowedTools": ["a"]})
        self.assertEqual(binding.tool_list_findings(document, mapping()), [])

    def test_an_empty_list_and_an_absent_one_are_refused_differently(self):
        absent = emitted()
        del absent["toolConfiguration"]
        empty = emitted(toolConfiguration={"allowedTools": []})
        first = binding.tool_list_findings(absent, mapping())[0]
        second = binding.tool_list_findings(empty, mapping())[0]
        self.assertNotEqual(first, second)


class SomethingThatIsNotAListFails(unittest.TestCase):
    """Each JSON kind separately.

    The call-site check shipped a version where five of eight markers were never
    exercised alone, because every test used a realistic input and a realistic
    input trips several rules at once. One minimal case per kind is the fix.
    """

    def refusal(self, value):
        document = emitted(toolConfiguration={"allowedTools": value})
        findings = binding.tool_list_findings(document, mapping())
        self.assertEqual(len(findings), 1, findings)
        return findings[0]

    def test_null_is_not_a_list(self):
        self.assertIn("null", self.refusal(None))

    def test_a_string_is_not_a_list(self):
        self.assertIn("a string", self.refusal("example.readMetrics"))

    def test_an_object_is_not_a_list(self):
        self.assertIn("an object", self.refusal({"example.readMetrics": True}))

    def test_a_number_is_not_a_list(self):
        self.assertIn("a number", self.refusal(7))

    def test_a_boolean_is_not_a_list(self):
        # Before the boolean branch, this said "a number", because bool is a
        # subclass of int in Python. A binding claiming its tools are True is
        # nonsense either way, but a message that misnames what it found sends
        # the reader to the wrong place.
        self.assertIn("a boolean", self.refusal(True))

    def test_null_is_refused_as_a_value_and_not_as_an_absence(self):
        # A property holding null is something the emitter wrote. A property
        # that is not there is something it never produced. Conflating them
        # would hide an emitter that writes the key and forgets the value.
        present = self.refusal(None)
        absent_document = emitted(toolConfiguration={})
        absent = binding.tool_list_findings(absent_document, mapping())[0]
        self.assertNotEqual(present, absent)

    def test_every_kind_the_describer_names_is_exercised_here(self):
        # A guard, not an assertion about behaviour: if somebody adds a kind to
        # describe() without adding a case above, this fails rather than
        # leaving the new branch untested.
        exercised = {"null", "a boolean", "an object", "a string", "a number"}
        produced = {
            binding.describe(value)
            for value in (None, True, {}, "", 0, 1.5, -3)
        }
        self.assertEqual(produced, exercised)


class TheCheckFailsClosedOnTheBindingLayer(unittest.TestCase):
    """A check that cannot find its own configuration must refuse, not abstain.

    The binding layer is where the location of the tool list is declared. If it
    is missing, or present and silent about the location, the check has no way
    to tell a correct binding from a broken one. Abstaining there would mean
    NEG-D passes for every binding on a repository where core/binding/ was
    deleted.
    """

    def test_a_missing_binding_layer_refuses_every_binding(self):
        findings = binding.tool_list_findings(emitted(), None)
        self.assertEqual(len(findings), 1)
        self.assertIn("core/binding", findings[0])

    def test_a_mapping_without_a_location_refuses_every_binding(self):
        silent = mapping()
        del silent[binding.POINTER_PROPERTY]
        findings = binding.tool_list_findings(emitted(), silent)
        self.assertEqual(len(findings), 1)
        self.assertIn(binding.POINTER_PROPERTY, findings[0])

    def test_an_empty_location_is_the_same_as_none(self):
        findings = binding.tool_list_findings(emitted(), mapping(toolListPointer=""))
        self.assertIn(binding.POINTER_PROPERTY, findings[0])

    def test_a_location_that_is_not_a_pointer_is_refused_on_its_own_terms(self):
        findings = binding.tool_list_findings(
            emitted(), mapping(toolListPointer="toolConfiguration.allowedTools")
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("not a", findings[0])
        self.assertIn("JSON Pointer", findings[0])

    def test_a_malformed_location_is_not_reported_as_a_missing_list(self):
        malformed = binding.tool_list_findings(
            emitted(), mapping(toolListPointer="toolConfiguration")
        )[0]
        missing = binding.tool_list_findings(
            emitted(), mapping(toolListPointer="/nowhere")
        )[0]
        self.assertNotEqual(malformed, missing)

    def test_the_three_binding_layer_refusals_are_distinct(self):
        silent = mapping()
        del silent[binding.POINTER_PROPERTY]
        messages = [
            binding.tool_list_findings(emitted(), None)[0],
            binding.tool_list_findings(emitted(), silent)[0],
            binding.tool_list_findings(emitted(), mapping(toolListPointer="x"))[0],
        ]
        self.assertEqual(len(set(messages)), 3, messages)


class TheRepositoryIsInTheStateItDeclares(unittest.TestCase):
    """A tripwire on the binding layer, driven by the core declaration.

    Today core/binding/ is declared planned, so load_mapping finds nothing and
    every emitted binding is refused. When T2.04 materialises it, this test
    stops asserting the planned branch and starts requiring the mapping to
    declare where the tool list lives, which is the one thing T2.04 could
    otherwise ship without and leave NEG-D permanently fail-closed against an
    empty set.
    """

    def status(self):
        declaration = core_paths.load_declaration(REPO_ROOT)
        for entry in declaration["categories"]["binding"]:
            if entry["path"] == "core/binding/":
                return entry["status"]
        self.fail("core/binding/ is not declared in any category")

    def test_the_binding_layer_agrees_with_the_declaration(self):
        found = binding.load_mapping(REPO_ROOT)
        if self.status() == "planned":
            self.assertIsNone(found)
        else:
            self.assertIsNotNone(
                found,
                "core/binding/ is declared present but holds no capability mapping",
            )
            self.assertTrue(
                found.get(binding.POINTER_PROPERTY),
                "the capability mapping must declare where an emitted binding "
                "carries its tool list, or NEG-D can never accept anything",
            )

    def test_a_binding_is_refused_today_for_the_declared_reason(self):
        if self.status() != "planned":
            self.skipTest("core/binding/ has been materialised")
        findings = binding.tool_list_findings(
            emitted(), binding.load_mapping(REPO_ROOT)
        )
        self.assertEqual(findings, [binding.NO_MAPPING])


class TheLocationIsReadFromTheBindingLayerAndNotGuessed(unittest.TestCase):
    """The check must follow the declared location and nothing else.

    Searching a runtime-shaped document for something that looks like a tool
    list is the mistake the call-site check refused to make with commands
    assembled at run time: a check that infers its own subject cannot tell "the
    list is absent" from "the list is somewhere I did not look".
    """

    def test_a_list_at_another_location_does_not_satisfy_the_check(self):
        document = {
            "name": "example-agent",
            "somewhereElse": ["example.readMetrics"],
        }
        findings = binding.tool_list_findings(document, mapping())
        self.assertEqual(len(findings), 1)

    def test_moving_the_location_moves_the_check(self):
        document = {"name": "example-agent", "somewhereElse": ["example.readMetrics"]}
        relocated = mapping(toolListPointer="/somewhereElse")
        self.assertEqual(binding.tool_list_findings(document, relocated), [])

    def test_the_declared_location_is_reported_when_it_holds_nothing(self):
        document = {"name": "example-agent"}
        findings = binding.tool_list_findings(document, mapping(toolListPointer="/a/b"))
        self.assertIn("/a/b", findings[0])


class ThePointerFollowsRfc6901(unittest.TestCase):
    """Pointer resolution, exercised directly.

    The escaping rules have an order that is easy to get backwards, and a
    pointer that silently resolves to the wrong place would make NEG-D pass
    against a document that never carried a tool list.
    """

    def test_a_nested_object_is_traversed(self):
        found, value = binding.resolve({"a": {"b": {"c": 1}}}, "/a/b/c")
        self.assertTrue(found)
        self.assertEqual(value, 1)

    def test_an_array_index_is_traversed(self):
        found, value = binding.resolve({"a": [10, 20]}, "/a/1")
        self.assertTrue(found)
        self.assertEqual(value, 20)

    def test_an_index_past_the_end_is_not_found(self):
        found, _ = binding.resolve({"a": [10]}, "/a/5")
        self.assertFalse(found)

    def test_the_index_exactly_one_past_the_end_is_not_found(self):
        # The boundary, not a value comfortably beyond it. A mutation loosening
        # the bound from >= to > survived every other case here, because an
        # index of five into a one-element list is out of range under both.
        # Only the first index that does not exist tells the two apart.
        found, _ = binding.resolve({"a": [10]}, "/a/1")
        self.assertFalse(found)

    def test_the_last_index_that_does_exist_is_found(self):
        # The control for the bound above: off by one in the other direction
        # would refuse a pointer that addresses a real element.
        found, value = binding.resolve({"a": [10, 20]}, "/a/1")
        self.assertTrue(found)
        self.assertEqual(value, 20)

    def test_a_non_numeric_index_into_an_array_is_not_found(self):
        found, _ = binding.resolve({"a": [10]}, "/a/b")
        self.assertFalse(found)

    def test_descending_into_a_scalar_is_not_found(self):
        found, _ = binding.resolve({"a": 1}, "/a/b")
        self.assertFalse(found)

    def test_a_key_containing_a_slash_is_escaped_as_tilde_one(self):
        found, value = binding.resolve({"a/b": 1}, "/a~1b")
        self.assertTrue(found)
        self.assertEqual(value, 1)

    def test_a_key_containing_a_tilde_is_escaped_as_tilde_zero(self):
        found, value = binding.resolve({"a~b": 1}, "/a~0b")
        self.assertTrue(found)
        self.assertEqual(value, 1)

    def test_tilde_zero_one_is_a_tilde_then_a_one_and_not_a_slash(self):
        # The order of the two replacements decides this. Unescaping ~0 first
        # turns ~01 into ~1 and then into a slash, addressing a key nobody
        # wrote.
        self.assertEqual(binding.unescape("a~01b"), "a~1b")
        found, _ = binding.resolve({"a/b": 1}, "/a~01b")
        self.assertFalse(found)

    def test_a_key_that_is_present_and_null_is_found(self):
        found, value = binding.resolve({"a": None}, "/a")
        self.assertTrue(found)
        self.assertIsNone(value)


class TheMappingIsLoadedFromTheBindingLayer(unittest.TestCase):
    """load_mapping, against a synthetic tree.

    The real binding layer does not exist yet, so without this the loader would
    only ever be exercised on the path where it returns None.
    """

    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.addCleanup(self._clean)
        self.directory = os.path.join(self.tmp, "core", "binding")
        os.makedirs(self.directory)

    def _clean(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, document):
        with open(os.path.join(self.directory, name), "w", encoding="utf-8") as handle:
            json.dump(document, handle)

    def test_a_mapping_in_the_binding_layer_is_found(self):
        self.write("capability-mapping.json", MAPPING)
        found = binding.load_mapping(self.tmp)
        self.assertIsNotNone(found)
        self.assertEqual(found[binding.POINTER_PROPERTY], POINTER)

    def test_a_json_file_that_is_not_a_mapping_is_ignored(self):
        self.write("something-else.json", {"schemaVersion": "1.0.0"})
        self.assertIsNone(binding.load_mapping(self.tmp))

    def test_a_non_json_file_is_ignored(self):
        with open(os.path.join(self.directory, "README.md"), "w", encoding="utf-8") as h:
            h.write("# binding layer\n")
        self.assertIsNone(binding.load_mapping(self.tmp))

    def test_an_absent_directory_yields_nothing(self):
        import tempfile

        empty = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(empty, ignore_errors=True))
        self.assertIsNone(binding.load_mapping(empty))


class TheContractCarriesTheLocation(unittest.TestCase):
    """The schema must admit the location, and must not admit a non-pointer.

    Without this the check would read a property the contract never described,
    which is the same as reading a property the binding layer is free to name
    anything.
    """

    def schema(self):
        path = os.path.join(
            REPO_ROOT, "contracts", "schemas", "capability-mapping.schema.json"
        )
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def test_the_schema_describes_the_location_property(self):
        self.assertIn(binding.POINTER_PROPERTY, self.schema()["properties"])

    def test_the_location_is_optional_in_the_schema(self):
        # Deliberate. A required location would move NEG-D's refusal into JSON
        # Schema, and then the test above would be asserting that jsonschema
        # works rather than that NEG-D does.
        self.assertNotIn(binding.POINTER_PROPERTY, self.schema()["required"])

    def test_a_mapping_declaring_a_location_validates(self):
        import jsonschema

        jsonschema.Draft202012Validator(self.schema()).validate(MAPPING)

    def test_a_location_that_is_not_a_pointer_is_rejected_by_the_schema(self):
        import jsonschema

        document = mapping(toolListPointer="toolConfiguration.allowedTools")
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema()).validate(document)

    def test_the_empty_pointer_is_rejected_by_the_schema(self):
        import jsonschema

        document = mapping(toolListPointer="")
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema()).validate(document)


if __name__ == "__main__":
    unittest.main()

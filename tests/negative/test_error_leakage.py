#!/usr/bin/env python3
"""NEG-K: a validation error never echoes the value that failed.

Evidence for User Story 2 (SEC-017, FR-49).

The threat is ordinary and quiet. Somebody points the validator at a
configuration that contains a connection string, a resource identifier or a
customer name. The document is wrong in some unrelated way. The validator
rejects it and, in doing so, writes the failing value into a message. That
message goes to a terminal, into CI output, and from there into an issue
somebody pasted it into. The document was never committed; the value was
published anyway.

`jsonschema` does this by default. Its messages quote the instance:
`'hunter2' is not of type 'integer'`. So the defence cannot be a habit of
writing careful messages. It has to be that the rendering path does not have
the value in its hands.

How this is checked
--------------------

Not by reading the code for careless formatting. A sentinel is planted in
every value position of every shipped example, one position at a time, the
real entry point is run, and every rendered finding is searched for it. A
rule about what messages contain is checked by looking at messages.

Two things make that evidence rather than ceremony.

The walk must reject a document. A position whose substitution happens to
stay valid produces no findings, and "the sentinel did not appear in zero
messages" is not a result. Those positions are counted and the count is
asserted, so a walk that stopped rejecting anything fails instead of passing
quietly.

The detector must be able to detect. A deliberately leaky renderer is run
through the same assertion, because a search that cannot find a planted value
would report every real leak as clean.

Why the sentinel is not shaped like a real secret
---------------------------------------------------

It would be better evidence if it were. It cannot be: this repository scans
its own full history for secret-shaped strings, and a realistic connection
string committed in a test file would fail that gate. The two controls
genuinely conflict here, and the sentinel is distinctive rather than
realistic as a result. What that costs is narrow: the rule under test is
about whether a value reaches a message at all, and a message does not
inspect the shape of what it is interpolating.

The residual, named
--------------------

One value does reach a message. When a document carries a property the schema
does not allow, the property *name* is reported, because an unnamed rejection
is unactionable and a typo is the usual cause (FR-27). That name is
author-supplied. A secret used as a property name would be echoed.

It is pinned below rather than left implicit, so that closing it later is a
deliberate change with a failing test attached, rather than something that
drifts one way or the other unnoticed.

Run with:
    python -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from zeroops import core_paths  # noqa: E402
from zeroops import validate  # noqa: E402

# Distinctive rather than realistic, for the reason in the module docstring.
SENTINEL = "ZZ-NEG-K-PLANTED-VALUE-9c1f"

EXAMPLES = os.path.join(REPO_ROOT, "examples")


def example_artifacts():
    found = []
    for directory, _, names in os.walk(EXAMPLES):
        for name in sorted(names):
            if name.endswith(".json"):
                found.append(os.path.join(directory, name))
    return sorted(found)


def positions(node, prefix=()):
    """Every position in a document that holds a value, including containers.

    Containers are included because replacing one with a string is how a
    `type` failure is produced, and `type` is the keyword whose default
    message quotes the instance most readily.
    """
    if prefix:
        yield prefix
    if isinstance(node, dict):
        for key, value in node.items():
            for found in positions(value, prefix + (key,)):
                yield found
    elif isinstance(node, list):
        for index, value in enumerate(node):
            for found in positions(value, prefix + (index,)):
                yield found


def plant(document, pointer, value):
    copied = copy.deepcopy(document)
    node = copied
    for step in pointer[:-1]:
        node = node[step]
    node[pointer[-1]] = value
    return copied


class Harness(unittest.TestCase):
    """Writes a document where the real entry point will read it.

    `validate_artifact` takes a path and derives the schema from the file
    name, so the document has to be on disk under its real name. Reassembling
    the call would test a copy of the validator rather than the validator.
    """

    def setUp(self):
        self.workspace = tempfile.mkdtemp(prefix="negk-")
        self.addCleanup(shutil.rmtree, self.workspace, True)

    def render(self, source_path, document):
        """Validate `document` under `source_path`'s name; return rendered text."""
        target = os.path.join(self.workspace, os.path.basename(source_path))
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(document, handle)
        try:
            findings, warnings = validate.validate_artifact(target)
        except validate.ValidationError as error:
            # A document the validator refuses to read at all still produces
            # text somebody sees, so it is in scope for this rule.
            return [str(error)]
        return [finding.render(target) for finding in findings] + [
            warning.render(target) for warning in warnings
        ]


class ThePlantedValueNeverReachesAMessage(Harness):
    """The rule itself, over every value position of every shipped example."""

    def test_no_rendered_finding_quotes_a_planted_value(self):
        rejected_by_artifact = {}
        checked = 0
        for path in example_artifacts():
            with open(path, encoding="utf-8") as handle:
                original = json.load(handle)
            rejected_by_artifact[path] = 0
            for pointer in positions(original):
                checked += 1
                rendered = self.render(path, plant(original, pointer, SENTINEL))
                if rendered:
                    rejected_by_artifact[path] += 1
                for line in rendered:
                    self.assertNotIn(
                        SENTINEL,
                        line,
                        "planting at %s in %s produced: %s"
                        % ("/".join(str(p) for p in pointer), os.path.basename(path), line),
                    )
        self.assertGreater(checked, 200, "the walk found far fewer positions than expected")
        # Per artifact rather than in total. A global count stays healthy while
        # one artifact quietly stops being validated at all, and that artifact
        # is then covered by nothing while the suite still reports a number.
        for path, count in rejected_by_artifact.items():
            self.assertGreater(
                count,
                0,
                "nothing in %s was rejected, so the absence of the sentinel "
                "there means nothing" % os.path.relpath(path, REPO_ROOT),
            )

    def test_a_planted_number_is_not_echoed_either(self):
        """A bound reports the bound, not the value that missed it."""
        for path in example_artifacts():
            with open(path, encoding="utf-8") as handle:
                original = json.load(handle)
            for pointer in positions(original):
                if not isinstance(
                    _at(original, pointer), (int, float)
                ) or isinstance(_at(original, pointer), bool):
                    continue
                for line in self.render(path, plant(original, pointer, -987654321)):
                    self.assertNotIn("987654321", line)


def _at(node, pointer):
    for step in pointer:
        node = node[step]
    return node


class TheDetectorCanDetect(Harness):
    """A search that cannot find a planted value reports every leak as clean."""

    def test_the_default_library_message_would_be_caught(self):
        """`jsonschema` quotes the instance. If it did not, this rule is moot.

        Pinning it also records *why* the validator rewrites messages: the
        behaviour being defended against is the library's default, not a
        hypothetical mistake.
        """
        from jsonschema import Draft202012Validator

        schema = {"type": "integer"}
        errors = list(Draft202012Validator(schema).iter_errors(SENTINEL))
        self.assertTrue(errors)
        self.assertIn(SENTINEL, errors[0].message)

    def test_a_leaky_renderer_fails_the_same_assertion(self):
        leaked = validate.Finding("/x", "value was %s" % SENTINEL).render("a.json")
        with self.assertRaises(AssertionError):
            self.assertNotIn(SENTINEL, leaked)

    def test_the_walk_reaches_nested_positions(self):
        document = {"a": {"b": [{"c": 1}]}}
        found = {"/".join(str(p) for p in pointer) for pointer in positions(document)}
        self.assertIn("a/b/0/c", found)
        self.assertIn("a/b/0", found)
        self.assertIn("a/b", found)
        self.assertIn("a", found)

    def test_the_walk_does_not_yield_the_root(self):
        """There is no way to replace the root in place, so yielding it would
        produce a position the planting helper cannot serve."""
        self.assertNotIn((), set(positions({"a": 1})))


class TheMessageBuildersUseSchemaContentOnly(unittest.TestCase):
    """Both hints draw from the schema, which is never instance content."""

    def test_the_shape_hint_reports_the_constraint(self):
        hint = validate.expected_shape_hint("maxLength", 12)
        self.assertIn("maxLength", hint)
        self.assertIn("12", hint)

    def test_the_shape_hint_refuses_a_composition_keyword(self):
        """A subschema printed into a diagnostic dumps the schema into an issue."""
        self.assertEqual(validate.expected_shape_hint("allOf", [{"type": "string"}]), "")

    def test_the_shape_hint_refuses_an_unlisted_keyword(self):
        self.assertEqual(validate.expected_shape_hint("not", {"type": "string"}), "")

    def test_the_allowed_properties_hint_names_schema_properties(self):
        hint = validate.allowed_properties_hint({"properties": {"alpha": {}, "beta": {}}})
        self.assertIn("alpha", hint)
        self.assertIn("beta", hint)

    def test_the_allowed_properties_hint_says_nothing_when_it_cannot_tell(self):
        """A placeholder would read as a statement about the schema rather than
        about this function's reach."""
        self.assertEqual(validate.allowed_properties_hint({"allOf": []}), "")
        self.assertEqual(validate.allowed_properties_hint("not a schema"), "")


class TheOneValueThatIsEchoedIsPinned(Harness):
    """The residual, recorded so that changing it is deliberate.

    An unexpected property's *name* is reported, because an unnamed rejection
    is unactionable. The name is author-supplied, so a secret used as a
    property name would be echoed. Nothing else is.
    """

    def test_an_unexpected_property_name_is_reported(self):
        path = os.path.join(EXAMPLES, "minimal", "scope-contract.json")
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        document[SENTINEL] = "anything"
        rendered = self.render(path, document)
        self.assertTrue(rendered)
        self.assertTrue(any(SENTINEL in line for line in rendered))

    def test_the_value_under_that_property_is_not_reported(self):
        """The name is the residual. The value is not, and must not become one."""
        path = os.path.join(EXAMPLES, "minimal", "scope-contract.json")
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        document["unexpectedProperty"] = SENTINEL
        for line in self.render(path, document):
            self.assertNotIn(SENTINEL, line)

    def test_a_required_property_name_comes_from_the_schema(self):
        """`required` names a property the schema listed, not one the author
        wrote, so reporting it cannot echo anything supplied."""
        path = os.path.join(EXAMPLES, "minimal", "scope-contract.json")
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        removed = sorted(document)[0]
        del document[removed]
        rendered = self.render(path, document)
        self.assertTrue(rendered)
        self.assertNotIn(SENTINEL, " ".join(rendered))


class TheSemanticLayerObeysTheSameRule(unittest.TestCase):
    """Driven directly, because the public path gates semantics behind structure.

    `validate_artifact` stops at the first structural failure, so planting a
    sentinel in a field the schema constrains never reaches the semantic
    checks: the pattern rejects it first. The sentinel walk therefore covers
    the semantic message builders only where a field happens to be loosely
    typed, which is an accident of the schemas rather than a property of the
    rule.

    Mutation found this. Making a semantic message quote its value left every
    test passing. So the semantic layer is driven on its own here, which is
    the only way these builders are reached with a value somebody planted.
    """

    def test_no_semantic_finding_quotes_a_planted_value(self):
        reached = {}
        for path in example_artifacts():
            kind = validate.kind_of(path)
            with open(path, encoding="utf-8") as handle:
                original = json.load(handle)
            reached.setdefault(kind, 0)
            for pointer in positions(original):
                candidate = plant(original, pointer, SENTINEL)
                try:
                    findings = validate.semantic_findings_for(kind, candidate)
                except (TypeError, AttributeError, KeyError):
                    # The semantic layer assumes a well-formed shape, which is
                    # why the public path gates it. Replacing a container with
                    # a string breaks that assumption, and a crash here is not
                    # the rule under test.
                    continue
                if findings:
                    reached[kind] += 1
                for finding in findings:
                    self.assertNotIn(
                        SENTINEL,
                        finding.render(os.path.basename(path)),
                        "semantic check for %s quoted a planted value at %s"
                        % (kind, "/".join(str(p) for p in pointer)),
                    )
        self.assertTrue(
            any(count for count in reached.values()),
            "no semantic check produced a finding, so nothing was exercised",
        )

    def test_a_malformed_timestamp_is_reported_without_the_timestamp(self):
        """The branch the public path cannot reach, driven on its own.

        A schema that constrains the format catches this first today. That is
        a fact about today's schemas, and the check stays as defence in depth,
        so its message has to obey the rule regardless.
        """
        findings = []
        validate._check_period({"start": SENTINEL, "end": SENTINEL}, "/p", findings)
        self.assertTrue(findings)
        for finding in findings:
            self.assertNotIn(SENTINEL, finding.render("a.json"))

    def test_an_undefined_environment_is_reported_without_its_name(self):
        findings = validate.semantic_findings(
            {"frameworkDefaults": {"defaultEnvironment": SENTINEL}, "environments": []}
        )
        self.assertTrue(findings)
        for finding in findings:
            self.assertNotIn(SENTINEL, finding.render("a.json"))

    def test_an_undefined_reference_is_reported_without_its_name(self):
        findings = []
        for kind in ("framework-config",):
            findings.extend(
                validate.semantic_findings_for(
                    kind,
                    {
                        "externalReferences": [],
                        "workloads": [
                            {"name": "w", "inScope": [], "outOfScope": [], "reference": SENTINEL}
                        ],
                    },
                )
            )
        for finding in findings:
            self.assertNotIn(SENTINEL, finding.render("a.json"))

    def test_backwards_timestamps_are_reported_without_the_timestamps(self):
        findings = []
        validate._check_ordering(
            {"startedAt": "2026-01-02T00:00:00Z", "completedAt": "2026-01-01T00:00:00Z"},
            "startedAt",
            "completedAt",
            findings,
        )
        self.assertTrue(findings)
        for finding in findings:
            rendered = finding.render("a.json")
            self.assertNotIn("2026-01-01", rendered)
            self.assertNotIn("2026-01-02", rendered)


class ADocumentThatCannotBeReadDoesNotLeakEither(Harness):
    """Failing before validation starts still produces text somebody sees."""

    def test_unparseable_json_is_located_without_being_quoted(self):
        """The parser reports line and column. Pinned, because the message is
        produced by the standard library and could change under us."""
        target = os.path.join(self.workspace, "scope-contract.json")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write('{"a": "%s"' % SENTINEL)
        with self.assertRaises(validate.ValidationError) as caught:
            validate.validate_artifact(target)
        self.assertNotIn(SENTINEL, str(caught.exception))
        self.assertIn("not valid JSON", str(caught.exception))

    def test_an_unterminated_string_is_not_quoted_back(self):
        target = os.path.join(self.workspace, "scope-contract.json")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write('{"a": "%s' % SENTINEL)
        with self.assertRaises(validate.ValidationError) as caught:
            validate.validate_artifact(target)
        self.assertNotIn(SENTINEL, str(caught.exception))

    def test_the_harness_reports_a_read_failure_instead_of_swallowing_it(self):
        """Without this the harness could return nothing on every input and
        the whole sentinel walk would assert against empty lists.

        Driven through an unknown artifact kind, because the harness writes
        the document itself and so cannot produce a parse failure.
        """
        rendered = self.render(
            os.path.join(self.workspace, "not-a-kind.json"), {"a": SENTINEL}
        )
        self.assertTrue(rendered, "the harness returned nothing for a failing read")
        self.assertNotIn(SENTINEL, " ".join(rendered))

    def test_an_unknown_artifact_kind_names_the_kind_and_not_the_content(self):
        """The kind comes from the filename, which is chosen rather than
        supplied inside the document. Named here so the distinction is on
        record: this rule is about document content."""
        target = os.path.join(self.workspace, "not-a-kind.json")
        with open(target, "w", encoding="utf-8") as handle:
            json.dump({"secret": SENTINEL}, handle)
        with self.assertRaises(validate.ValidationError) as caught:
            validate.validate_artifact(target)
        self.assertNotIn(SENTINEL, str(caught.exception))
        self.assertIn("not-a-kind", str(caught.exception))


class TheCoreGateUsesTheSameRenderingPath(unittest.TestCase):
    """The declaration was the one place still echoing the library message.

    The declaration is a repository file, so nothing secret is expected in it.
    That is a fact about today's input rather than about the gate, and a rule
    that holds only while its input stays benign is not a rule.
    """

    def test_a_planted_value_in_the_declaration_is_not_echoed(self):
        declaration = core_paths.load_declaration(REPO_ROOT)
        declaration["schemaVersion"] = SENTINEL
        problems = core_paths.check(REPO_ROOT, declaration)
        self.assertTrue(problems, "the planted value did not cause a rejection")
        for problem in problems:
            self.assertNotIn(SENTINEL, problem)

    def test_the_declaration_rejection_still_says_where_and_what(self):
        """Suppressing the value must not suppress the diagnosis."""
        declaration = core_paths.load_declaration(REPO_ROOT)
        declaration["schemaVersion"] = SENTINEL
        problems = core_paths.check(REPO_ROOT, declaration)
        self.assertTrue(any("schemaVersion" in problem for problem in problems))

    def test_the_real_declaration_still_passes(self):
        """The control. Without it a gate that rejected everything would look
        like a gate that suppressed everything."""
        self.assertEqual(core_paths.check(REPO_ROOT), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""The three validation levels, and the boundaries between them.

Structural, then semantic, then Recommended-area warnings (FR-25, FR-27, FR-28).
The ordering is not cosmetic. Semantic checks assume a well-formed shape, and
warnings assume the document is worth advising about at all, so each level is
gated behind the one before it.

Roughly half of what follows feeds the validator documents it must reject or
advise about. A test suite that only supplies good input measures nothing: a
validator that returned "valid" unconditionally would pass every positive case.
"""

import copy
import json
import os
import re
import subprocess
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
SCHEMA_DIR = os.path.join(REPO_ROOT, "contracts", "schemas")
CONTRACT_DOC = os.path.join(
    REPO_ROOT, "docs", "architecture", "minimum-sre-agent-contract.md"
)
MINIMAL = os.path.join(REPO_ROOT, "examples", "minimal")
TWO_ENVIRONMENTS = os.path.join(REPO_ROOT, "examples", "two-environments")

if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from zeroops import obligations, validate  # noqa: E402


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_example(directory, filename):
    return read_json(os.path.join(directory, filename))


class ArtifactDispatch(unittest.TestCase):
    """Which schema an artifact is checked against, and how that is decided."""

    def test_every_schema_in_the_directory_is_a_dispatchable_kind(self):
        on_disk = sorted(
            name[: -len(validate.SCHEMA_SUFFIX)]
            for name in os.listdir(SCHEMA_DIR)
            if name.endswith(validate.SCHEMA_SUFFIX)
        )
        self.assertEqual(on_disk, validate.known_kinds())
        # Guard against the discovery itself silently matching nothing, which
        # would make every assertion in this class vacuously true.
        self.assertGreaterEqual(len(on_disk), 15)

    def test_kind_is_the_filename_before_the_first_dot(self):
        self.assertEqual("framework-config", validate.kind_of("framework-config.json"))
        self.assertEqual(
            "environment-binding",
            validate.kind_of("environment-binding.production.json"),
        )
        self.assertEqual(
            "environment-binding",
            validate.kind_of(os.path.join("a", "b", "environment-binding.x.y.json")),
        )

    def test_a_label_lets_one_kind_appear_more_than_once_in_a_set(self):
        artifacts = validate.resolve_artifacts(TWO_ENVIRONMENTS)
        bindings = [a for a in artifacts if validate.kind_of(a) == "environment-binding"]
        self.assertEqual(2, len(bindings))

    def test_an_unknown_kind_is_a_usage_error_not_a_pass(self):
        with self.assertRaises(validate.ValidationError) as caught:
            validate.schema_path_for("not-a-real-kind")
        # The message has to be actionable, so it lists what would have worked.
        self.assertIn("framework-config", str(caught.exception))

    def test_a_document_cannot_choose_its_own_schema(self):
        """Dispatch is on the filename, never on a field inside the document.

        A document that named its own schema could claim a laxer kind, and the
        cheapest way to pass validation would be to lie about what you are.
        """
        instance = load_example(MINIMAL, "framework-config.json")
        instance["$schema"] = "tool-policy.schema.json"
        findings = validate.structural_findings(
            instance, read_json(validate.schema_path_for("framework-config"))
        )
        # The claim is rejected as an unknown property rather than honoured.
        self.assertTrue(findings)


class DirectoryIsASetNotAFile(unittest.TestCase):
    """Validating a directory must look at every artifact it holds."""

    def test_every_recognised_artifact_in_a_set_is_checked(self):
        results = validate.validate_set(TWO_ENVIRONMENTS)
        checked = sorted(os.path.basename(a) for a, _, _ in results)
        on_disk = sorted(
            name for name in os.listdir(TWO_ENVIRONMENTS) if name.endswith(".json")
        )
        self.assertEqual(on_disk, checked)
        self.assertGreaterEqual(len(checked), 6)

    def test_the_shipped_examples_are_accepted(self):
        for directory in (MINIMAL, TWO_ENVIRONMENTS):
            for artifact, findings, _ in validate.validate_set(directory):
                self.assertEqual([], [f.render(artifact) for f in findings])

    def test_a_broken_member_rejects_the_whole_set(self):
        """A set is valid only if every member is, or the report is a lie."""
        results = validate.validate_set(TWO_ENVIRONMENTS)
        self.assertFalse(any(f for _, f, _ in results))

        import tempfile
        import shutil

        staging = tempfile.mkdtemp()
        try:
            for name in os.listdir(TWO_ENVIRONMENTS):
                shutil.copy(os.path.join(TWO_ENVIRONMENTS, name), staging)
            broken = os.path.join(staging, "connector-config.json")
            document = read_json(broken)
            document["unexpectedProperty"] = "x"
            with open(broken, "w", encoding="utf-8") as handle:
                json.dump(document, handle)

            results = validate.validate_set(staging)
            offenders = [os.path.basename(a) for a, f, _ in results if f]
            self.assertEqual(["connector-config.json"], offenders)
        finally:
            shutil.rmtree(staging)

    def test_a_directory_with_nothing_recognisable_is_a_usage_error(self):
        import tempfile
        import shutil

        empty = tempfile.mkdtemp()
        try:
            with self.assertRaises(validate.ValidationError):
                validate.resolve_artifacts(empty)
        finally:
            shutil.rmtree(empty)


class LevelsAreOrderedAndGated(unittest.TestCase):
    """A later level never runs over input the earlier one rejected."""

    def staged(self, mutate):
        instance = load_example(MINIMAL, "framework-config.json")
        mutate(instance)
        return instance

    def test_semantic_checks_do_not_run_over_a_malformed_shape(self):
        def mutate(instance):
            instance["unexpectedProperty"] = "x"
            # Also inverted, which the semantic layer would report if it ran.
            instance["frameworkDefaults"]["observationPeriod"]["end"] = (
                "2020-01-01T00:00:00Z"
            )

        instance = self.staged(mutate)
        schema = read_json(validate.schema_path_for("framework-config"))
        structural = validate.structural_findings(instance, schema)
        self.assertTrue(structural)

        messages = " ".join(f.message for f in structural)
        self.assertNotIn("ends at or before it starts", messages)

    def test_warnings_do_not_run_over_a_rejected_document(self):
        import tempfile

        handle, path = tempfile.mkstemp(suffix=".json", prefix="framework-config.")
        os.close(handle)
        try:
            instance = self.staged(lambda d: d.pop("observability"))
            instance["unexpectedProperty"] = "x"
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(instance, stream)
            findings, warnings = validate.validate_artifact(path)
            self.assertTrue(findings)
            # The missing observability block would otherwise warn on area 9.
            self.assertEqual([], warnings)
        finally:
            os.unlink(path)

    def test_a_semantic_fault_suppresses_advice(self):
        """Advice about production is noise while the document is broken."""
        import tempfile

        handle, path = tempfile.mkstemp(suffix=".json", prefix="framework-config.")
        os.close(handle)
        try:
            instance = self.staged(
                lambda d: d["frameworkDefaults"]["observationPeriod"].update(
                    {"end": "2020-01-01T00:00:00Z"}
                )
            )
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(instance, stream)
            findings, warnings = validate.validate_artifact(path)
            self.assertTrue(findings)
            self.assertEqual([], warnings)
        finally:
            os.unlink(path)


class SemanticChecksBeyondOneArtifact(unittest.TestCase):
    """FR-28 checks now apply to the kinds that can express the fault."""

    def findings_for(self, kind, instance):
        return validate.semantic_findings_for(kind, instance)

    def base_scope_contract(self):
        return load_example(TWO_ENVIRONMENTS, "scope-contract.json")

    def test_the_shipped_scope_contract_is_semantically_clean(self):
        self.assertEqual(
            [], self.findings_for("scope-contract", self.base_scope_contract())
        )

    def test_an_inverted_period_in_a_scope_contract_is_rejected(self):
        document = self.base_scope_contract()
        start = document["observationPeriod"]["start"]
        document["observationPeriod"]["end"] = start
        findings = self.findings_for("scope-contract", document)
        self.assertTrue(findings)
        self.assertIn("ends at or before it starts", findings[0].message)

    def test_a_contradictory_scope_contract_is_rejected(self):
        document = self.base_scope_contract()
        document["outOfScope"] = [copy.deepcopy(document["inScope"][0])]
        findings = self.findings_for("scope-contract", document)
        self.assertTrue(findings)
        self.assertIn("ambiguous", findings[0].message)

    def test_an_execution_cannot_finish_before_it_began(self):
        document = {
            "startedAt": "2026-01-02T00:00:00Z",
            "completedAt": "2026-01-01T00:00:00Z",
        }
        findings = self.findings_for("evidence-manifest", document)
        self.assertTrue(findings)
        self.assertIn("before it began", findings[0].message)

    def test_a_manifest_that_never_completed_is_not_a_fault(self):
        """An execution still running has no completedAt. That is a state, not
        an error, and reporting it as one would punish the honest manifest."""
        self.assertEqual(
            [],
            self.findings_for("evidence-manifest", {"startedAt": "2026-01-02T00:00:00Z"}),
        )

    def test_a_malformed_timestamp_is_reported_once_not_twice(self):
        document = {"startedAt": "yesterday", "completedAt": "2026-01-01T00:00:00Z"}
        findings = self.findings_for("evidence-manifest", document)
        self.assertEqual(1, len(findings))
        self.assertIn("RFC 3339", findings[0].message)

    def test_a_malformed_period_start_is_reported_once_not_twice(self):
        """A malformed timestamp must not also be compared.

        With a malformed start and a well-formed end, a lexical comparison
        reports "ends before it starts" as well, because digits sort below
        letters. The second finding is false and points at the wrong field,
        which is worse than saying nothing: the author fixes the period rather
        than the timestamp.
        """
        document = self.base_scope_contract()
        document["observationPeriod"]["start"] = "yesterday"
        findings = self.findings_for("scope-contract", document)
        self.assertEqual(
            1,
            len(findings),
            [f.render("scope-contract") for f in findings],
        )
        self.assertIn("RFC 3339", findings[0].message)
        self.assertEqual("/observationPeriod/start", findings[0].pointer)

    def test_a_handoff_past_its_bound_is_rejected(self):
        findings = self.findings_for("handoff-record", {"turn": 6, "maxTurns": 5})
        self.assertTrue(findings)
        self.assertIn("exceeds maxTurns", findings[0].message)

    def test_a_handoff_on_its_final_turn_is_accepted(self):
        self.assertEqual(
            [], self.findings_for("handoff-record", {"turn": 5, "maxTurns": 5})
        )

    def test_a_kind_without_a_rule_is_structure_only_and_says_nothing(self):
        self.assertEqual([], self.findings_for("tool-policy", {"anything": True}))


class RecommendedAreasAreTheThirdLevel(unittest.TestCase):
    """Warnings advise; they never reject unless the caller asks."""

    def contract_recommended_areas(self):
        """Parse the obligation table in the contract document.

        The registry in obligations.py is the runtime source, and this reads the
        document that governs it. If the two disagree, one of them is wrong and
        CI should say so rather than letting the validator drift away from the
        contract it claims to enforce.
        """
        with open(CONTRACT_DOC, encoding="utf-8") as handle:
            text = handle.read()
        row = re.compile(r"^\|\s*(\d+)\s*\|[^|]+\|([^|]+)\|", re.M)
        areas = {}
        for number, cell in row.findall(text):
            # Rows 13 and 14 read "**Required** as contract", so the cell is
            # taken whole and stripped rather than matched by a narrow pattern.
            # A pattern that silently skipped them would leave this parse
            # short by two and still agree with the registry, because both
            # are Required.
            areas[int(number)] = cell.replace("*", "").strip()
        return areas

    def test_the_contract_table_parses(self):
        """Without this, an empty parse would make the next test vacuous."""
        areas = self.contract_recommended_areas()
        self.assertEqual(25, len(areas))
        self.assertEqual("Required", areas[1])
        # The document states its own totals: 18 Required, 6 Recommended,
        # 1 Optional. Checking the parse against them catches a pattern that
        # drops rows whose obligation happens to be worded differently.
        obligations_seen = list(areas.values())
        self.assertEqual(
            18, len([o for o in obligations_seen if o.startswith("Required")])
        )
        self.assertEqual(6, obligations_seen.count("Recommended"))
        self.assertEqual(1, obligations_seen.count("Optional"))

    def test_the_registry_covers_exactly_the_recommended_areas(self):
        areas = self.contract_recommended_areas()
        recommended = sorted(n for n, o in areas.items() if o == "Recommended")
        self.assertEqual(recommended, sorted(obligations.RECOMMENDED_AREAS))
        self.assertEqual(6, len(recommended))

    def test_no_required_area_is_demoted_to_a_warning(self):
        """A Required area handled by advice would be a Required area in name
        only, because advice does not fail the build."""
        areas = self.contract_recommended_areas()
        required = {n for n, o in areas.items() if o.startswith("Required")}
        self.assertEqual(set(), required & set(obligations.RECOMMENDED_AREAS))

    def test_every_area_is_either_checked_or_explains_why_not(self):
        observable = set(obligations.observable_areas())
        unobservable = set(obligations.unobservable_areas())
        self.assertEqual(set(obligations.RECOMMENDED_AREAS), observable | unobservable)
        self.assertEqual(set(), observable & unobservable)
        for area in unobservable:
            reason = obligations.RECOMMENDED_AREAS[area][1]
            # A blank or token reason would make the category a dumping ground.
            self.assertGreater(len(reason), 80, "area %d has no real reason" % area)

    def test_an_absent_recommended_field_warns_and_names_its_area(self):
        instance = load_example(MINIMAL, "framework-config.json")
        instance["observability"].pop("workspaceRef", None)
        warnings = obligations.warnings_for("framework-config", instance)
        self.assertEqual([9], [w.area for w in warnings])
        self.assertEqual("/observability/workspaceRef", warnings[0].pointer)

    def test_a_present_recommended_field_warns_about_nothing(self):
        instance = load_example(TWO_ENVIRONMENTS, "framework-config.json")
        areas = [w.area for w in obligations.warnings_for("framework-config", instance)]
        self.assertNotIn(9, areas)

    def test_an_empty_value_counts_as_absent(self):
        """A declared-but-empty field advertises coverage it does not provide."""
        instance = load_example(TWO_ENVIRONMENTS, "agent-definition.json")
        instance["skills"] = []
        self.assertEqual(
            [3], [w.area for w in obligations.warnings_for("agent-definition", instance)]
        )

    def test_an_unbound_tool_policy_warns_on_retry_and_timeout(self):
        instance = load_example(MINIMAL, "framework-config.json")
        instance["toolIntegrations"].pop("toolPolicyRef", None)
        areas = [w.area for w in obligations.warnings_for("framework-config", instance)]
        self.assertIn(17, areas)

    def test_a_connector_without_a_timeout_warns(self):
        instance = load_example(TWO_ENVIRONMENTS, "connector-config.json")
        instance.pop("timeoutSeconds", None)
        areas = [w.area for w in obligations.warnings_for("connector-config", instance)]
        self.assertEqual([17], areas)

    def test_a_rule_does_not_fire_on_an_unrelated_kind(self):
        """Warnings are scoped by kind; a tool policy has no workspace to lack."""
        self.assertEqual([], obligations.warnings_for("tool-policy", {}))

    def test_a_warning_is_not_a_finding(self):
        instance = load_example(MINIMAL, "framework-config.json")
        self.assertEqual([], validate.semantic_findings_for("framework-config", instance))
        self.assertTrue(obligations.warnings_for("framework-config", instance))


class DiagnosticsCarryNoValues(unittest.TestCase):
    """SEC-017, swept over every schema rather than spot-checked.

    Error text is pasted into issues, chat transcripts and CI logs. A message
    that echoes the rejected value moves that value into every one of those
    places, and for a secret-bearing or identifier-bearing field that is the
    disclosure the validator was supposed to prevent.
    """

    MARKER = "zz-leaked-value-marker-8f21"

    def kinds(self):
        return validate.known_kinds()

    def test_no_message_echoes_a_string_value_for_any_kind(self):
        checked = 0
        for kind in self.kinds():
            schema = read_json(validate.schema_path_for(kind))
            # A document of the wrong type at every property forces a spread of
            # keywords: type, enum, const, pattern, format, minimum.
            instance = {"schemaVersion": self.MARKER}
            for name in (schema.get("properties") or {}):
                instance[name] = self.MARKER
            findings = validate.structural_findings(instance, schema)
            self.assertTrue(findings, "%s rejected nothing" % kind)
            for finding in findings:
                self.assertNotIn(self.MARKER, finding.message, kind)
                self.assertNotIn(self.MARKER, finding.pointer, kind)
            checked += 1
        self.assertGreaterEqual(checked, 15)

    def test_no_message_echoes_a_nested_value(self):
        schema = read_json(validate.schema_path_for("framework-config"))
        instance = load_example(MINIMAL, "framework-config.json")
        instance["externalReferences"]["entries"][0]["locator"] = self.MARKER * 40
        instance["externalReferences"]["entries"][0]["provider"] = self.MARKER
        findings = validate.structural_findings(instance, schema)
        self.assertTrue(findings)
        for finding in findings:
            self.assertNotIn(self.MARKER, finding.message)

    def test_an_unknown_property_names_the_property_but_not_its_value(self):
        """The name is needed to act on the error; the value never is."""
        schema = read_json(validate.schema_path_for("framework-config"))
        instance = load_example(MINIMAL, "framework-config.json")
        instance["misspelledConcern"] = self.MARKER
        findings = validate.structural_findings(instance, schema)
        self.assertTrue(findings)
        joined = " ".join(f.message for f in findings)
        self.assertIn("misspelledConcern", joined)
        self.assertNotIn(self.MARKER, joined)

    def test_a_warning_carries_no_value_either(self):
        instance = load_example(MINIMAL, "framework-config.json")
        instance["observability"].pop("workspaceRef", None)
        instance["frameworkDefaults"]["defaultEnvironment"] = self.MARKER
        for warning in obligations.warnings_for("framework-config", instance):
            self.assertNotIn(self.MARKER, warning.render("artifact"))

    def test_a_semantic_finding_carries_no_value(self):
        instance = load_example(MINIMAL, "framework-config.json")
        instance["environments"][0]["subscriptionRef"] = self.MARKER
        findings = validate.semantic_findings_for("framework-config", instance)
        self.assertTrue(findings)
        for finding in findings:
            self.assertNotIn(self.MARKER, finding.render("artifact"))


class CommandSurface(unittest.TestCase):
    """What a caller branches on: the exit code."""

    def run_cli(self, *args):
        env = dict(os.environ)
        env["PYTHONPATH"] = TOOLS_DIR + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run(
            [sys.executable, "-m", "zeroops"] + list(args),
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_a_warning_alone_does_not_fail_the_quick_win(self):
        result = self.run_cli("validate", MINIMAL)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("warning:", result.stderr)

    def test_strict_promotes_the_same_warning_to_a_failure(self):
        result = self.run_cli("validate", MINIMAL, "--strict")
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("--strict", result.stderr)

    def test_a_full_set_validates_end_to_end(self):
        result = self.run_cli("validate", TWO_ENVIRONMENTS)
        self.assertEqual(0, result.returncode, result.stderr)
        expected = len(
            [n for n in os.listdir(TWO_ENVIRONMENTS) if n.endswith(".json")]
        )
        # Guarded rather than hardcoded: a literal count silently stops
        # describing the set the moment an artifact is added, and a guard of
        # zero would make the comparison below pass over an empty directory.
        self.assertGreaterEqual(expected, 7)
        self.assertEqual(expected, result.stdout.count("Configuration valid:"))

    def test_an_unrecognised_filename_is_a_usage_error_not_a_pass(self):
        import tempfile

        handle, path = tempfile.mkstemp(suffix=".json", prefix="mystery-")
        os.close(handle)
        try:
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("{}")
            result = self.run_cli("validate", path)
            self.assertEqual(2, result.returncode, result.stdout)
        finally:
            os.unlink(path)

    def test_output_stays_ascii(self):
        """Windows consoles are cp1252; a non-ASCII byte turns a report into a
        crash on exactly the platform the framework promises to support."""
        for args in (("validate", MINIMAL), ("validate", MINIMAL, "--strict")):
            result = self.run_cli(*args)
            (result.stdout + result.stderr).encode("ascii")


if __name__ == "__main__":
    unittest.main()

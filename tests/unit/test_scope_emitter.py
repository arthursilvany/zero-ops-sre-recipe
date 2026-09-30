"""The scope contract carries the selection, and nothing else from the row.

Fixtures here are schematic. A convincing resource identifier in a test file
is indistinguishable from a leaked one to the history scanner that guards this
repository, and the scanner is right to refuse to tell them apart.
"""

import json
import os
import re
import shutil
import tempfile
import unittest

from zeroops import canonical, scope_emitter, validate
from zeroops.schema_lint import SECRET_MARKERS


SUBSCRIPTION = "sub-one"

PERIOD = {"start": "2026-09-01T00:00:00Z", "end": "2026-09-29T00:00:00Z"}

LIMITS = {
    "maxToolCalls": 50,
    "maxWallClockSeconds": 600,
    "maxResultSetRows": 1000,
    "perQueryTimeoutSeconds": 30,
}

GENERATED_AT = "2026-09-29T12:00:00Z"

MARKER = "discovery-run-17"

# Shaped like a directory identifier and beginning with a letter, which is the
# case the schema's own pattern admits.
GUID_SHAPED = "a1b2c3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d"

# The forms that name credential material in a value and never in a property
# name, which is why the schema linter has no use for them.
VALUE_SECRET_CASES = (
    "AccountKey=not-a-real-key",
    "SharedAccessKey=not-a-real-key",
    "PrimaryKey=not-a-real-key",
    "SecondaryKey=not-a-real-key",
    "clientSecret=not-a-real-value",
    "sig=not-a-real-signature",
    "pwd=not-a-real-password",
)


def row(identifier, group="rg-one", **overrides):
    built = {
        "id": "/subscriptions/%s/%s/%s" % (SUBSCRIPTION, group, identifier),
        "name": identifier,
        "type": "microsoft.example/units",
        "location": "westeurope",
        "resourceGroup": group,
        "subscriptionId": SUBSCRIPTION,
    }
    built.update(overrides)
    return built


def build(**overrides):
    rows = overrides.pop("rows", [row("unit-alpha")])
    kind = overrides.pop("kind", "resource")
    arguments = {
        "subscription_ref": "primary-subscription",
        "in_scope": scope_emitter.select(
            rows, [one["id"] for one in rows], kind=kind
        ),
        "out_of_scope": [],
        "observation_period": dict(PERIOD),
        "execution_limits": dict(LIMITS),
        "generated_at": GENERATED_AT,
        "generated_against": MARKER,
    }
    arguments.update(overrides)
    return scope_emitter.build(**arguments)


def projected_fields():
    """The columns the discovery query actually asks Resource Graph for.

    Read from the catalogue rather than copied into this file, so that adding
    a column without deciding what it means for the contract fails here.
    """
    path = os.path.join(
        validate.repo_root(), "wizard", "discovery", "query-catalogue.json"
    )
    catalogue = validate.load_json(path, "query catalogue")
    for entry in catalogue["entries"]:
        if entry["id"] != "subscription-resources":
            continue
        match = re.search(r"\|\s*project\s+([^|]+)", entry["queryText"])
        return [part.strip() for part in match.group(1).split(",")]
    raise AssertionError("the catalogue no longer enumerates resources")


class TemporaryDirectory(object):
    def __enter__(self):
        self.path = tempfile.mkdtemp()
        return self.path

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)
        return False


class OnlyTheAllowListedFieldTravels(unittest.TestCase):
    """SEC-007: the emitter never copies a discovery row."""

    def test_every_allow_listed_field_is_a_column_the_query_projects(self):
        projected = projected_fields()
        for kind, field in scope_emitter.SELECTOR_FIELD.items():
            self.assertIn(
                field,
                projected,
                "kind %s selects on a column discovery does not read" % kind,
            )

    def test_no_other_projected_field_reaches_the_emitted_bytes(self):
        forbidden = [
            field
            for field in projected_fields()
            if field not in scope_emitter.SELECTOR_FIELD.values()
        ]
        self.assertTrue(forbidden, "the allow-list would be vacuous")

        marked = {field: "forbidden-%s-value" % field for field in forbidden}
        source = row("unit-alpha", **marked)
        for kind in sorted(scope_emitter.SELECTOR_FIELD):
            rendered = scope_emitter.render(build(rows=[source], kind=kind))
            text = rendered.decode("utf-8")
            for field, value in marked.items():
                self.assertNotIn(
                    value,
                    text,
                    "%s reached a contract built by kind %s" % (field, kind),
                )

    def test_an_entry_has_exactly_the_two_contract_fields(self):
        built = scope_emitter.entry("resource", "unit-alpha")
        self.assertEqual(
            sorted(built), sorted(scope_emitter.ENTRY_FIELDS)
        )

    def test_a_tag_selector_cannot_be_derived_from_a_row(self):
        with self.assertRaises(scope_emitter.EmitError) as caught:
            scope_emitter.selector_for("tag", row("unit-alpha"))
        self.assertIn("no discovery row carries", str(caught.exception))

    def test_a_tag_selector_supplied_by_the_operator_is_accepted(self):
        built = scope_emitter.entry("tag", "environment=production")
        self.assertEqual(built["selector"], "environment=production")

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(scope_emitter.EmitError):
            scope_emitter.selector_for("workloadType", row("unit-alpha"))

    def test_an_entry_of_an_unknown_kind_is_refused(self):
        with self.assertRaises(scope_emitter.EmitError):
            scope_emitter.entry("workloadType", "unit-alpha")

    def test_a_row_missing_its_selector_field_is_refused(self):
        source = row("unit-alpha")
        del source["resourceGroup"]
        with self.assertRaises(scope_emitter.EmitError):
            scope_emitter.selector_for("resourceGroup", source)


class SelectionIsExactlyWhatWasChosen(unittest.TestCase):
    """FR-13."""

    def test_every_chosen_candidate_appears(self):
        rows = [row("unit-alpha"), row("unit-beta"), row("unit-gamma")]
        chosen = [rows[0]["id"], rows[2]["id"]]
        entries = scope_emitter.select(rows, chosen)
        self.assertEqual([one["selector"] for one in entries], chosen)

    def test_nothing_unchosen_appears(self):
        rows = [row("unit-alpha"), row("unit-beta")]
        entries = scope_emitter.select(rows, [rows[0]["id"]])
        self.assertEqual(len(entries), 1)
        self.assertNotIn(
            rows[1]["id"], [one["selector"] for one in entries]
        )

    def test_a_candidate_the_discovery_never_returned_is_refused(self):
        rows = [row("unit-alpha")]
        with self.assertRaises(scope_emitter.EmitError) as caught:
            scope_emitter.select(rows, ["/subscriptions/%s/rg-one/ghost" % SUBSCRIPTION])
        self.assertIn("does not", str(caught.exception))

    def test_two_rows_in_one_group_select_that_group_once(self):
        rows = [row("unit-alpha"), row("unit-beta")]
        entries = scope_emitter.select(
            rows, [one["id"] for one in rows], kind="resourceGroup"
        )
        self.assertEqual(entries, [{"kind": "resourceGroup", "selector": "rg-one"}])

    def test_two_groups_stay_two_entries(self):
        rows = [row("unit-alpha"), row("unit-beta", group="rg-two")]
        entries = scope_emitter.select(
            rows, [one["id"] for one in rows], kind="resourceGroup"
        )
        self.assertEqual(
            [one["selector"] for one in entries], ["rg-one", "rg-two"]
        )

    def test_selecting_nothing_is_refused_by_the_contract(self):
        with self.assertRaises(scope_emitter.EmitError):
            build(in_scope=[])


class TheReferenceIsAReferenceNotTheThingItNames(unittest.TestCase):
    """The schema's pattern cannot make this distinction."""

    def test_the_schema_pattern_would_have_accepted_a_directory_identifier(self):
        schema = validate.load_json(
            validate.schema_path_for(scope_emitter.KIND), "schema"
        )
        pattern = schema["$defs"]["externalReferenceName"]["pattern"]
        self.assertIsNotNone(
            re.match(pattern, GUID_SHAPED),
            "if the pattern rejected this, the emitter check would be dead code",
        )

    def test_the_emitter_refuses_it(self):
        with self.assertRaises(scope_emitter.EmitError) as caught:
            build(subscription_ref=GUID_SHAPED)
        self.assertIn("directory identifier", str(caught.exception))

    def test_an_ordinary_reference_name_is_accepted(self):
        document = build(subscription_ref="primary-subscription")
        self.assertEqual(document["subscriptionRef"], "primary-subscription")

    def test_an_empty_reference_is_refused(self):
        with self.assertRaises(scope_emitter.EmitError):
            build(subscription_ref="")

    def test_a_shape_name_that_does_not_exist_is_an_error_not_a_pass(self):
        with self.assertRaises(scope_emitter.EmitError) as caught:
            scope_emitter.shape_findings("anything", ("no such shape",))
        self.assertIn("pass by not running", str(caught.exception))

    def test_every_named_shape_resolves(self):
        names = set(scope_emitter.REFERENCE_FORBIDDEN)
        names.update(scope_emitter.MARKER_FORBIDDEN)
        self.assertEqual(scope_emitter.shape_findings("", sorted(names)), [])


class TheMarkerIsOpaque(unittest.TestCase):
    """generatedAgainst is documented as not a resource identifier."""

    def test_a_directory_identifier_is_refused(self):
        with self.assertRaises(scope_emitter.EmitError) as caught:
            build(generated_against=GUID_SHAPED)
        self.assertIn("resource identifier", str(caught.exception))

    def test_a_resource_group_path_is_refused(self):
        with self.assertRaises(scope_emitter.EmitError):
            build(generated_against="/resourceGroups/rg-one")

    def test_an_endpoint_is_refused(self):
        with self.assertRaises(scope_emitter.EmitError):
            build(generated_against="https://example.invalid/run")

    def test_an_electronic_mail_address_is_refused(self):
        with self.assertRaises(scope_emitter.EmitError):
            build(generated_against="operator@example.invalid")

    def test_a_digest_is_accepted_because_it_names_nobody(self):
        digest = canonical.text_digest("a discovery run")
        document = build(generated_against=digest)
        self.assertEqual(document["generatedAgainst"], digest)

    def test_an_empty_marker_is_refused(self):
        with self.assertRaises(scope_emitter.EmitError):
            build(generated_against="")


class NoCredentialReachesTheContract(unittest.TestCase):
    """CC-020."""

    def test_every_marker_the_schema_linter_knows_is_also_refused_in_a_value(self):
        for words in SECRET_MARKERS:
            candidate = "".join(words) + "=something"
            self.assertTrue(
                scope_emitter.secret_findings(candidate),
                "%s names secret material in a schema but not in a value"
                % candidate,
            )

    def test_each_value_only_marker_is_refused(self):
        for candidate in VALUE_SECRET_CASES:
            self.assertTrue(
                scope_emitter.secret_findings(candidate),
                "%s is credential material" % candidate,
            )

    def test_every_value_only_marker_has_a_case(self):
        for pattern in scope_emitter.VALUE_SECRET_MARKERS:
            compiled = re.compile("(?i)" + pattern)
            self.assertTrue(
                any(compiled.search(one) for one in VALUE_SECRET_CASES),
                "%s is declared but never exercised, so dropping it would "
                "cost nothing" % pattern,
            )

    def test_a_tag_selector_holding_a_connection_string_is_refused(self):
        selector = "config=Endpoint=example;SharedAccessKey=not-a-real-key"
        with self.assertRaises(scope_emitter.EmitError) as caught:
            scope_emitter.entry("tag", selector)
        self.assertIn("credential material", str(caught.exception))

    def test_a_web_token_is_refused(self):
        token = ".".join(("eyJhbGciOiJub25l", "eyJzdWIiOiJ0ZXN0"))
        self.assertIn("web token", scope_emitter.secret_findings(token))

    def test_a_private_key_block_is_refused(self):
        header = "-----BEGIN RSA " + "PRIVATE KEY-----"
        self.assertIn("private key block", scope_emitter.secret_findings(header))

    def test_a_shared_access_signature_is_refused(self):
        self.assertIn(
            "shared access signature",
            scope_emitter.secret_findings("sv=2026-01-01&sr=c"),
        )

    def test_the_refusal_reaches_build_through_any_field(self):
        with self.assertRaises(scope_emitter.EmitError) as caught:
            build(generated_against="token=not-a-real-token")
        self.assertIn("credential material", str(caught.exception))

    def test_ordinary_selectors_are_not_flagged(self):
        for value in (
            "/subscriptions/%s/rg-one/unit-alpha" % SUBSCRIPTION,
            "rg-one",
            "environment=production",
            "cost-centre=44120",
            # A marker word is not credential material on its own. A team that
            # names a resource group after the service it runs would otherwise
            # find the contract refused for saying the word.
            "rg-token-service",
            "secrets-platform",
            "certificate-authority",
        ):
            self.assertEqual(
                scope_emitter.secret_findings(value),
                [],
                "%s is an ordinary selector" % value,
            )

    def test_the_framework_own_field_names_are_not_flagged(self):
        document = build()
        for key in document:
            self.assertEqual(scope_emitter.secret_findings(key), [])


class ExclusionsAreDeclaredNeverImplied(unittest.TestCase):
    def test_omitting_the_exclusion_list_is_not_available(self):
        with self.assertRaises(TypeError):
            scope_emitter.build(
                subscription_ref="primary-subscription",
                in_scope=[{"kind": "resource", "selector": "unit-alpha"}],
                observation_period=dict(PERIOD),
                execution_limits=dict(LIMITS),
                generated_at=GENERATED_AT,
                generated_against=MARKER,
            )

    def test_an_empty_exclusion_list_is_a_statement_and_is_accepted(self):
        self.assertEqual(build()["outOfScope"], [])

    def test_a_selector_in_both_lists_is_refused(self):
        entry = {"kind": "resource", "selector": "unit-alpha"}
        with self.assertRaises(scope_emitter.EmitError) as caught:
            build(in_scope=[dict(entry)], out_of_scope=[dict(entry)])
        self.assertIn("ambiguous", str(caught.exception))

    def test_an_exclusion_is_carried_through(self):
        document = build(
            out_of_scope=[{"kind": "resourceGroup", "selector": "rg-two"}]
        )
        self.assertEqual(
            document["outOfScope"],
            [{"kind": "resourceGroup", "selector": "rg-two"}],
        )


class TheEmittedFileValidatesWithoutModification(unittest.TestCase):
    """FR-14."""

    def test_the_written_file_passes_the_ordinary_validator(self):
        with TemporaryDirectory() as directory:
            path = scope_emitter.write(build(), scope_emitter.default_path(directory))
            findings, _ = validate.validate_artifact(path)
            self.assertEqual(
                [finding.render("scope-contract") for finding in findings], []
            )

    def test_the_default_filename_is_one_the_validator_dispatches_on(self):
        self.assertEqual(
            validate.kind_of(scope_emitter.DEFAULT_FILENAME), scope_emitter.KIND
        )
        self.assertTrue(
            os.path.isfile(validate.schema_path_for(scope_emitter.KIND))
        )

    def test_a_name_the_validator_cannot_dispatch_on_is_refused(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(scope_emitter.EmitError) as caught:
                scope_emitter.write(
                    build(), os.path.join(directory, "scope.json")
                )
            self.assertIn("validates against no schema", str(caught.exception))
            self.assertEqual(os.listdir(directory), [])

    def test_a_missing_directory_is_created(self):
        with TemporaryDirectory() as directory:
            target = os.path.join(directory, "nested", "scope-contract.json")
            scope_emitter.write(build(), target)
            self.assertTrue(os.path.isfile(target))

    def test_an_observation_period_running_backwards_is_refused(self):
        with self.assertRaises(scope_emitter.EmitError) as caught:
            build(
                observation_period={
                    "start": "2026-09-29T00:00:00Z",
                    "end": "2026-09-01T00:00:00Z",
                }
            )
        self.assertIn("ends at or before it starts", str(caught.exception))

    def test_an_incomplete_limit_set_is_refused(self):
        limits = dict(LIMITS)
        del limits["maxToolCalls"]
        with self.assertRaises(KeyError):
            build(execution_limits=limits)


class TheHashIsOfTheDocumentItTravelsIn(unittest.TestCase):
    """FR-23, ADR-0004."""

    def test_recomputation_reproduces_the_recorded_value(self):
        document = build()
        self.assertEqual(
            document[scope_emitter.HASH_FIELD],
            canonical.digest(document, hash_field=scope_emitter.HASH_FIELD),
        )

    def test_the_hash_field_is_excluded_from_its_own_input(self):
        document = build()
        without = {
            key: value
            for key, value in document.items()
            if key != scope_emitter.HASH_FIELD
        }
        self.assertEqual(
            document[scope_emitter.HASH_FIELD], canonical.digest(without)
        )

    def test_it_is_lowercase_hexadecimal_of_the_pinned_length(self):
        self.assertRegex(build()[scope_emitter.HASH_FIELD], r"^[0-9a-f]{64}$")

    def test_a_different_selection_produces_a_different_hash(self):
        one = build(rows=[row("unit-alpha")])
        other = build(rows=[row("unit-beta")])
        self.assertNotEqual(
            one[scope_emitter.HASH_FIELD], other[scope_emitter.HASH_FIELD]
        )

    def test_the_same_inputs_render_the_same_bytes(self):
        self.assertEqual(scope_emitter.render(build()), scope_emitter.render(build()))

    def test_the_rendered_bytes_carry_no_carriage_return(self):
        self.assertNotIn(b"\r", scope_emitter.render(build()))

    def test_the_rendered_keys_are_sorted(self):
        loaded = json.loads(
            scope_emitter.render(build()).decode("utf-8"),
            object_pairs_hook=lambda pairs: [key for key, _ in pairs],
        )
        self.assertEqual(loaded, sorted(loaded))

    def test_verify_accepts_what_the_emitter_wrote(self):
        with TemporaryDirectory() as directory:
            path = scope_emitter.write(build(), scope_emitter.default_path(directory))
            self.assertEqual(
                [finding.render("x") for finding in scope_emitter.verify(path)], []
            )

    def test_verify_reports_a_contract_edited_after_emission(self):
        with TemporaryDirectory() as directory:
            path = scope_emitter.write(build(), scope_emitter.default_path(directory))
            document = validate.load_json(path, "contract")
            document["inScope"].append(
                {"kind": "resourceGroup", "selector": "rg-smuggled"}
            )
            with open(path, "w", encoding="utf-8", newline="") as handle:
                json.dump(document, handle, indent=2, sort_keys=True)
            findings = scope_emitter.verify(path)
            self.assertEqual(len(findings), 1)
            self.assertIn("changed after it was approved", findings[0].message)

    def test_verify_reports_a_contract_that_stopped_validating(self):
        with TemporaryDirectory() as directory:
            document = build()
            document["schemaVersion"] = "9.9.9"
            # Rehashed, so the digest agrees with the file and only schema
            # validation can catch this. Without that the hash check alone
            # would report, and this test would pass whether or not verify
            # validated at all.
            document[scope_emitter.HASH_FIELD] = canonical.digest(
                document, hash_field=scope_emitter.HASH_FIELD
            )
            path = scope_emitter.write(
                document, scope_emitter.default_path(directory)
            )
            findings = scope_emitter.verify(path)
            self.assertTrue(findings)
            for finding in findings:
                self.assertNotIn("changed after it was approved", finding.message)


class TheCommandChecksAFile(unittest.TestCase):
    def test_it_succeeds_on_an_emitted_contract(self):
        with TemporaryDirectory() as directory:
            path = scope_emitter.write(build(), scope_emitter.default_path(directory))
            self.assertEqual(scope_emitter.main([path]), 0)

    def test_it_fails_on_a_tampered_contract(self):
        with TemporaryDirectory() as directory:
            path = scope_emitter.write(build(), scope_emitter.default_path(directory))
            document = validate.load_json(path, "contract")
            document["generatedAgainst"] = "another-run"
            with open(path, "w", encoding="utf-8", newline="") as handle:
                json.dump(document, handle, indent=2, sort_keys=True)
            self.assertEqual(scope_emitter.main([path]), 1)

    def test_it_reports_rather_than_raises_on_a_missing_file(self):
        with TemporaryDirectory() as directory:
            missing = os.path.join(directory, "scope-contract.json")
            self.assertEqual(scope_emitter.main([missing]), 2)


class ThePageDocumentsTheEmitter(unittest.TestCase):
    def page(self):
        path = os.path.join(validate.repo_root(), "docs", "scope-contract.md")
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_it_names_the_command_that_exists(self):
        self.assertIn("python -m zeroops.scope_emitter", self.page())

    def test_it_names_every_selection_kind_the_schema_allows(self):
        schema = validate.load_json(
            validate.schema_path_for(scope_emitter.KIND), "schema"
        )
        text = self.page()
        for kind in schema["$defs"]["scopeEntry"]["properties"]["kind"]["enum"]:
            self.assertIn("`%s`" % kind, text)

    def test_it_names_every_allow_listed_row_field(self):
        text = self.page()
        for field in scope_emitter.SELECTOR_FIELD.values():
            self.assertIn("`%s`" % field, text)


if __name__ == "__main__":
    unittest.main()

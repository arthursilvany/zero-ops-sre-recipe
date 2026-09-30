"""NEG-G: a secret-shaped tag value cannot reach the emitted scope contract.

A tag is free text an operator controls, and is the likeliest place in an
Azure subscription that a connection string ends up. The scope contract is
committed. CC-020 says no secret may be written into one, and SEC-007 asks for
this specific case to be driven rather than argued.

`test_must_not.py` already covers the structural half of CC-020: a secret has
no valid position in any emitted document, because every schema is closed and
every credential-shaped property is a reference. That establishes there is
nowhere to *put* a secret. It says nothing about whether a value that was
never meant to be a secret position could carry one, which is what a tag does.

So this drives the value rather than the shape, in four layers. Each layer
alone passes the case the next one exists for:

One, the value never enters. Discovery projects no tag column at all, checked
    against the query catalogue rather than against a claim in prose, so a
    query that starts reading tags fails here rather than in a bug report.

Two, containment. A row that carries tags anyway, which an extension or a
    later projection change could produce, puts nothing from them into a
    contract, because the emitter reads one named field per selection kind.
    The control matters more than the assertion: the same row with a harmless
    tag also emits nothing from it, *and the emission succeeds*. Without that,
    this layer would pass just as well if the contract were never emitted.

Three, refusal on the one route in. An operator can select by tag, and that
    selector is typed rather than derived. A secret-shaped one is refused and
    nothing is emitted. The control is that a benign tag selector is accepted,
    so the refusal is about the value and not about the kind.

Four, the field that is copied. A resource group genuinely named after a
    credential assignment reaches the contract through the allow-list, which
    is the one way an allow-list cannot help. It is refused too, which is what
    "anywhere in the emitted contract" has to mean.
"""

import os
import re
import unittest

from zeroops import scope_emitter, validate


# Schematic throughout. A convincing credential in a test file is
# indistinguishable from a leaked one to the scanner that guards this
# repository, and the scanner is right to refuse to tell them apart.
SUBSCRIPTION = "sub-one"

SECRET_TAG_VALUE = "AccountKey=not-a-real-key"

BENIGN_TAG_VALUE = "owned-by-platform"

PERIOD = {"start": "2026-09-01T00:00:00Z", "end": "2026-09-29T00:00:00Z"}

LIMITS = {
    "maxToolCalls": 50,
    "maxWallClockSeconds": 600,
    "maxResultSetRows": 1000,
    "perQueryTimeoutSeconds": 30,
}


def row(identifier, group="rg-one", tag_value=None):
    """A discovery row, optionally carrying tags discovery would not read."""
    built = {
        "id": "/subscriptions/%s/%s/%s" % (SUBSCRIPTION, group, identifier),
        "name": identifier,
        "type": "microsoft.example/units",
        "location": "westeurope",
        "resourceGroup": group,
        "subscriptionId": SUBSCRIPTION,
    }
    if tag_value is not None:
        built["tags"] = {"connection": tag_value}
    return built


def contract(in_scope, out_of_scope=()):
    return scope_emitter.build(
        subscription_ref="primary-subscription",
        in_scope=in_scope,
        out_of_scope=list(out_of_scope),
        observation_period=dict(PERIOD),
        execution_limits=dict(LIMITS),
        generated_at="2026-09-29T12:00:00Z",
        generated_against="discovery-run-17",
    )


def catalogue():
    path = os.path.join(
        validate.repo_root(), "wizard", "discovery", "query-catalogue.json"
    )
    return validate.load_json(path, "query catalogue")


class TheValueNeverEntersBecauseNoQueryReadsATag(unittest.TestCase):
    """Layer one, upstream of the emitter entirely."""

    def test_no_catalogued_query_names_a_tag(self):
        entries = catalogue()["entries"]
        self.assertTrue(entries, "an empty catalogue would pass vacuously")
        for entry in entries:
            self.assertIsNone(
                re.search(r"(?i)\btags?\b", entry["queryText"]),
                "query %s reads tags, so a tag value now reaches the "
                "discovery output and every artifact made from it"
                % entry["id"],
            )

    def test_the_enumerating_query_projects_a_fixed_field_list(self):
        for entry in catalogue()["entries"]:
            if entry["id"] != "subscription-resources":
                continue
            match = re.search(r"\|\s*project\s+([^|]+)", entry["queryText"])
            self.assertIsNotNone(
                match, "the enumerating query no longer names its columns"
            )
            projected = [part.strip() for part in match.group(1).split(",")]
            self.assertIn("id", projected, "the projection is unreadable")
            self.assertNotIn("tags", projected)
            return
        self.fail("the catalogue no longer enumerates resources")


class ARowCarryingATagEmitsNothingFromIt(unittest.TestCase):
    """Layer two: containment, for the row discovery does not produce yet."""

    def emitted(self, tag_value, kind):
        source = row("unit-alpha", tag_value=tag_value)
        document = contract(
            scope_emitter.select([source], [source["id"]], kind=kind)
        )
        return document, scope_emitter.render(document).decode("utf-8")

    def test_a_secret_shaped_tag_appears_nowhere_in_the_contract(self):
        for kind in sorted(scope_emitter.SELECTOR_FIELD):
            document, text = self.emitted(SECRET_TAG_VALUE, kind)
            self.assertTrue(
                document, "nothing was emitted, so absence proves nothing"
            )
            self.assertNotIn(SECRET_TAG_VALUE, text, "kind %s" % kind)
            self.assertNotIn("not-a-real-key", text, "kind %s" % kind)

    def test_a_harmless_tag_appears_nowhere_either(self):
        """The control. Absence has to come from the allow-list.

        If the secret case above passed because the contract was refused, this
        one would fail, because a harmless tag gives the emitter no reason to
        refuse anything.
        """
        for kind in sorted(scope_emitter.SELECTOR_FIELD):
            document, text = self.emitted(BENIGN_TAG_VALUE, kind)
            self.assertTrue(document)
            self.assertNotIn(BENIGN_TAG_VALUE, text, "kind %s" % kind)

    def test_the_tag_bearing_row_still_produces_the_selection_it_should(self):
        source = row("unit-alpha", tag_value=SECRET_TAG_VALUE)
        document, _ = self.emitted(SECRET_TAG_VALUE, "resource")
        self.assertEqual(
            document["inScope"],
            [{"kind": "resource", "selector": source["id"]}],
        )

    def test_no_selector_can_be_derived_from_a_tag(self):
        source = row("unit-alpha", tag_value=SECRET_TAG_VALUE)
        with self.assertRaises(scope_emitter.EmitError):
            scope_emitter.selector_for("tag", source)


class TheOneRouteInIsRefused(unittest.TestCase):
    """Layer three: a tag selector is typed, not derived."""

    def test_a_secret_shaped_tag_selector_is_refused(self):
        with self.assertRaises(scope_emitter.EmitError) as caught:
            scope_emitter.entry("tag", "connection=%s" % SECRET_TAG_VALUE)
        self.assertIn("credential material", str(caught.exception))

    def test_the_refusal_does_not_depend_on_capitalisation(self):
        for spelling in (
            "accountkey=not-a-real-key",
            "ACCOUNTKEY=not-a-real-key",
            "Account_Key=not-a-real-key",
            "account-key: not-a-real-key",
        ):
            self.assertTrue(
                scope_emitter.secret_findings(spelling),
                "%s is the same credential written differently" % spelling,
            )

    def test_nothing_is_emitted_when_a_tag_selector_carries_one(self):
        with self.assertRaises(scope_emitter.EmitError):
            contract([{"kind": "tag", "selector": SECRET_TAG_VALUE}])

    def test_a_benign_tag_selector_is_accepted(self):
        """The control. The refusal is about the value, not about the kind."""
        document = contract(
            [{"kind": "tag", "selector": "environment=production"}]
        )
        self.assertEqual(
            document["inScope"],
            [{"kind": "tag", "selector": "environment=production"}],
        )

    def test_an_excluded_tag_selector_is_scanned_too(self):
        with self.assertRaises(scope_emitter.EmitError):
            contract(
                [{"kind": "resourceGroup", "selector": "rg-one"}],
                out_of_scope=[{"kind": "tag", "selector": SECRET_TAG_VALUE}],
            )

    def test_the_document_scan_reaches_inside_lists(self):
        """The net behind the per-entry refusal.

        Every selector is scanned as its entry is assembled, so the whole
        document scan cannot currently see a string in a list that was not
        already checked. That makes the traversal defence in depth, and an
        untested defence is the one that quietly stops working, so it is
        pinned here directly rather than through a path that cannot reach it.
        """
        found = scope_emitter._strings(
            {"a": [{"b": SECRET_TAG_VALUE}], "c": "plain"}
        )
        self.assertIn(("/a/0/b", SECRET_TAG_VALUE), found)
        self.assertIn(("/c", "plain"), found)


class TheAllowListedFieldIsScannedAsWell(unittest.TestCase):
    """Layer four: the one way an allow-list cannot help.

    A resource group named after a credential assignment reaches the contract
    through the field the allow-list permits. Allow-listing decides which
    field travels, never what is in it.
    """

    def test_a_resource_group_named_after_a_credential_is_refused(self):
        source = row("unit-alpha", group=SECRET_TAG_VALUE)
        with self.assertRaises(scope_emitter.EmitError) as caught:
            scope_emitter.select(
                [source], [source["id"]], kind="resourceGroup"
            )
        self.assertIn("credential material", str(caught.exception))

    def test_a_resource_identifier_carrying_one_is_refused(self):
        source = row(SECRET_TAG_VALUE)
        with self.assertRaises(scope_emitter.EmitError):
            scope_emitter.select([source], [source["id"]], kind="resource")

    def test_the_opaque_marker_is_scanned_too(self):
        with self.assertRaises(scope_emitter.EmitError):
            scope_emitter.build(
                subscription_ref="primary-subscription",
                in_scope=[{"kind": "resourceGroup", "selector": "rg-one"}],
                out_of_scope=[],
                observation_period=dict(PERIOD),
                execution_limits=dict(LIMITS),
                generated_at="2026-09-29T12:00:00Z",
                generated_against=SECRET_TAG_VALUE,
            )

    def test_an_ordinary_group_name_is_accepted(self):
        """The control, again. Refusal has to be about the value."""
        source = row("unit-alpha", group="rg-token-service")
        entries = scope_emitter.select(
            [source], [source["id"]], kind="resourceGroup"
        )
        self.assertEqual(
            entries, [{"kind": "resourceGroup", "selector": "rg-token-service"}]
        )


if __name__ == "__main__":
    unittest.main()

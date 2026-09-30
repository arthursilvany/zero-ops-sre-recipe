# -*- coding: utf-8 -*-
"""T4.07 — non-interactive execution, `--set` parity, byte-identical output.

The acceptance sentence these cover is S4-06: `--non-interactive` consuming a
previously emitted file completes with no prompt and emits a byte-identical
scope contract on Windows and on Linux, and full `--set` parity is asserted so
that a prompt without a `--set` key fails a test.

Each class carries at least one control, because most of these assertions pass
trivially when the thing under test does not happen at all. A byte-comparison
between two documents that were never built is a comparison of two exceptions.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unicodedata
import unittest

from zeroops import canonical, guided, prompts, scope_emitter, validate


SELECTION = {
    "inScope": [
        {"kind": "resource", "selector": "/subscriptions/sub-one/rg-one/unit-alpha"}
    ],
    "outOfScope": [
        {"kind": "resourceGroup", "selector": "/subscriptions/sub-one/rg-two"}
    ],
    "generatedAgainst": "discovery-run-one",
    "generatedAt": "2026-01-08T00:00:00Z",
}

ANSWERS = {
    "subscription-reference": "sub-one",
    "observation-start": "2026-01-01T00:00:00Z",
    "observation-end": "2026-01-08T00:00:00Z",
    "max-tool-calls": "10",
    "max-wall-clock-seconds": "60",
    "max-result-set-rows": "100",
    "per-query-timeout-seconds": "30",
}

SETTINGS = ["%s=%s" % (key, value) for key, value in ANSWERS.items()]

# Values that must never appear in any message this module writes. The
# credential shapes are SEC-017's original subject; the directory identifier is
# there because SEC-017 covers identifier-bearing fields too, and because the
# reference pattern would otherwise accept one.
SECRETS = (
    "AccountKey=not-a-real-key",
    "password=hunter2hunter2hunter2",
    "Server=x;AccountKey=also-not-a-real-key;",
)

IDENTIFIER = "a1b2c3d4-0000-0000-0000-000000000000"

LEAKY = SECRETS + (IDENTIFIER,)


def assert_refused_at_collection(case, caught):
    """The refusal came from the input check, not from the emitter behind it.

    `scope_emitter.build` scans for credential material as well, and
    `contract` turns its `EmitError` into a `GuidedError`, so asserting only
    the exception type cannot tell the two layers apart. A mutation replacing
    the input check with a bare type coercion left all of these tests green
    for exactly that reason: the value was refused, one layer too late and
    with a message naming neither the input nor the expected format, which is
    what FR-16 actually asks for.

    The emitter is the backstop and is meant to catch this. It is not the
    thing under test here.
    """
    message = str(caught.exception)
    case.assertIn("was not accepted", message)
    case.assertIn("Expected format:", message)


def typed(order=None):
    """A reader that answers each prompt in register order."""
    order = prompts.REGISTER if order is None else order
    supply = iter([ANSWERS[entry.id] for entry in order])
    return lambda: next(supply)


def refuses_to_be_read():
    """A reader whose only behaviour is to fail if a prompt is issued."""

    def reader():
        raise AssertionError(
            "a prompt was issued during a non-interactive run"
        )

    return reader


def interactive_document(config=None, writer=None):
    return guided.run(
        config=SELECTION if config is None else config,
        reader=typed(),
        writer=(lambda line: None) if writer is None else writer,
        interactive=True,
    )


def non_interactive_document(config=None, settings=None):
    return guided.run(
        settings=SETTINGS if settings is None else settings,
        config=SELECTION if config is None else config,
        reader=refuses_to_be_read(),
        interactive=False,
    )


class EveryPromptHasASetKey(unittest.TestCase):
    """CC-005: full `--set` parity, with no gap expressible."""

    def test_every_register_entry_is_a_settable_key(self):
        self.assertEqual(
            set(guided.setting_keys()),
            {entry.id for entry in prompts.REGISTER},
        )

    def test_a_new_prompt_becomes_a_new_set_key_without_being_listed(self):
        """The parity test that can actually fail.

        Comparing the keys to the register passes by construction while the
        keys are derived from it, and would also pass against a restated list
        that happens to be current. Injecting a register the module has never
        seen is what separates the two: a restated list does not grow.
        """
        invented = prompts.Input(
            id="an-input-that-did-not-exist",
            pointer="/subscriptionRef",
            explanation="present only to prove the keys follow the register",
        )
        entries = prompts.REGISTER + (invented,)
        self.assertIn(invented.id, guided.setting_keys(entries))
        self.assertIs(guided.entry_for(invented.id, entries), invented)

    def test_an_unknown_key_is_refused_and_the_valid_keys_are_named(self):
        with self.assertRaises(guided.GuidedError) as caught:
            guided.parse_settings(["not-an-input=1"])
        message = str(caught.exception)
        for key in guided.setting_keys():
            self.assertIn(key, message)

    def test_a_key_set_twice_is_refused(self):
        """Order-dependent input is not reproducible input (FR-18)."""
        with self.assertRaises(guided.GuidedError):
            guided.parse_settings(["max-tool-calls=10", "max-tool-calls=11"])

    def test_control_the_same_keys_are_accepted_once(self):
        parsed = guided.parse_settings(SETTINGS)
        self.assertEqual(set(parsed), set(guided.setting_keys()))


class NonInteractiveRunsWithoutPrompting(unittest.TestCase):
    """FR-18: a run driven entirely by a version-controlled file."""

    def test_a_full_set_of_settings_never_reaches_the_reader(self):
        document = non_interactive_document()
        self.assertEqual(document["subscriptionRef"], "sub-one")

    def test_a_previously_emitted_contract_needs_no_settings_at_all(self):
        """CC-005 exactly: the file a prior run emitted drives the next one."""
        prior = json.loads(
            scope_emitter.render(interactive_document()).decode("utf-8")
        )
        document = guided.run(
            config=prior,
            reader=refuses_to_be_read(),
            interactive=False,
        )
        self.assertEqual(document["subscriptionRef"], "sub-one")

    def test_a_missing_answer_stops_rather_than_blocking_on_a_terminal(self):
        with self.assertRaises(guided.GuidedError) as caught:
            guided.run(
                settings=SETTINGS[:2],
                config=SELECTION,
                reader=refuses_to_be_read(),
                interactive=False,
            )
        self.assertIn("--non-interactive", str(caught.exception))

    def test_a_run_without_a_selection_is_refused_naming_what_is_missing(self):
        with self.assertRaises(guided.GuidedError) as caught:
            guided.run(
                settings=SETTINGS,
                config={},
                reader=refuses_to_be_read(),
                interactive=False,
            )
        message = str(caught.exception)
        for name in guided.FROM_CONFIG:
            if name == guided.CLOCK_FIELD:
                continue
            self.assertIn(name, message)

    def test_control_the_reader_would_have_fired_if_a_prompt_were_issued(self):
        """Without this, every test above passes on a reader nobody calls."""
        with self.assertRaises(AssertionError):
            guided.run(
                settings=SETTINGS[:2],
                config=SELECTION,
                reader=refuses_to_be_read(),
                writer=lambda line: None,
                interactive=True,
            )


class BothModesEmitTheSameBytes(unittest.TestCase):
    """FR-19: equivalent inputs, identical artifacts."""

    def test_interactive_and_non_interactive_render_identically(self):
        typed_in = scope_emitter.render(interactive_document())
        scripted = scope_emitter.render(non_interactive_document())
        self.assertEqual(typed_in, scripted)

    def test_the_recorded_digest_is_the_same_in_both_modes(self):
        self.assertEqual(
            interactive_document()["canonicalHash"],
            non_interactive_document()["canonicalHash"],
        )

    def test_a_round_trip_through_the_emitted_file_is_byte_stable(self):
        first = scope_emitter.render(non_interactive_document())
        again = scope_emitter.render(
            guided.run(
                config=json.loads(first.decode("utf-8")),
                reader=refuses_to_be_read(),
                interactive=False,
            )
        )
        self.assertEqual(first, again)

    def test_a_set_overrides_the_configuration_it_was_given(self):
        """The control for the three tests above.

        They compare two documents, and two documents built from inputs that
        cannot differ would compare equal however the code behaved. This is
        the case that proves a difference in input reaches the bytes.
        """
        prior = json.loads(
            scope_emitter.render(non_interactive_document()).decode("utf-8")
        )
        changed = guided.run(
            settings=["max-tool-calls=11"],
            config=prior,
            reader=refuses_to_be_read(),
            interactive=False,
        )
        self.assertEqual(changed["executionLimits"]["maxToolCalls"], 11)
        self.assertNotEqual(
            scope_emitter.render(changed), scope_emitter.render(prior)
        )

    def test_the_clock_is_an_input_so_a_fresh_run_records_a_fresh_moment(self):
        """Parity is about equivalent inputs, and the clock is one of them.

        A run with no recorded moment is starting, not reproducing. Saying so
        here keeps the parity claim from being read as a promise the module
        does not make.
        """
        selection = {
            name: value
            for name, value in SELECTION.items()
            if name != guided.CLOCK_FIELD
        }
        document = guided.run(
            settings=SETTINGS,
            config=selection,
            reader=refuses_to_be_read(),
            interactive=False,
            clock=lambda: "2030-06-01T12:00:00Z",
        )
        self.assertEqual(document["generatedAt"], "2030-06-01T12:00:00Z")
        self.assertNotEqual(
            scope_emitter.render(document),
            scope_emitter.render(non_interactive_document()),
        )

    def test_a_missing_moment_with_no_clock_is_refused_rather_than_invented(self):
        selection = {
            name: value
            for name, value in SELECTION.items()
            if name != guided.CLOCK_FIELD
        }
        with self.assertRaises(guided.GuidedError):
            guided.run(
                settings=SETTINGS,
                config=selection,
                reader=refuses_to_be_read(),
                interactive=False,
            )


class TheBytesAreTheSameOnEveryPlatform(unittest.TestCase):
    """NEG-J: the same input produces the same artifact on Windows and Linux."""

    def test_the_rendered_file_carries_no_carriage_return(self):
        self.assertNotIn(b"\r", scope_emitter.render(non_interactive_document()))

    def test_two_canonically_equivalent_selectors_render_identically(self):
        """The hole this task closed.

        `canonical.digest` normalises to NFC internally, so a composed and a
        decomposed form of the same name hashed the same while rendering to a
        different number of bytes. Both files validated and both verified, so
        nothing reported the divergence. A name typed on a platform that
        produces decomposed forms committed a file that differed from the one
        produced elsewhere, with a matching hash saying they were the same.
        """
        composed = "rg-caf\u00e9"
        decomposed = "rg-cafe\u0301"
        self.assertNotEqual(composed, decomposed)
        self.assertEqual(
            unicodedata.normalize("NFC", composed),
            unicodedata.normalize("NFC", decomposed),
        )

        def emit(selector):
            config = dict(
                SELECTION,
                inScope=[{"kind": "resourceGroup", "selector": selector}],
            )
            return scope_emitter.render(non_interactive_document(config=config))

        self.assertEqual(emit(composed), emit(decomposed))

    def test_the_emitted_selector_is_the_composed_form(self):
        """The control: equal bytes would also follow from dropping both."""
        config = dict(
            SELECTION,
            inScope=[{"kind": "resourceGroup", "selector": "rg-cafe\u0301"}],
        )
        document = non_interactive_document(config=config)
        self.assertEqual(
            document["inScope"][0]["selector"],
            unicodedata.normalize("NFC", "rg-caf\u00e9"),
        )

    def test_the_digest_still_matches_the_file_after_normalisation(self):
        document = non_interactive_document()
        self.assertEqual(
            document[scope_emitter.HASH_FIELD],
            canonical.digest(
                {
                    name: value
                    for name, value in document.items()
                    if name != scope_emitter.HASH_FIELD
                },
                hash_field=scope_emitter.HASH_FIELD,
            ),
        )


class OneCheckGovernsEverySource(unittest.TestCase):
    """A configuration must not accept what a prompt refuses."""

    def test_a_credential_supplied_by_set_is_refused(self):
        for secret in SECRETS:
            with self.subTest(secret=secret):
                with self.assertRaises(guided.GuidedError) as caught:
                    guided.run(
                        settings=["subscription-reference=%s" % secret],
                        config=SELECTION,
                        reader=refuses_to_be_read(),
                        interactive=False,
                    )
                assert_refused_at_collection(self, caught)

    def test_a_credential_supplied_by_configuration_is_refused(self):
        for secret in SECRETS:
            with self.subTest(secret=secret):
                with self.assertRaises(guided.GuidedError) as caught:
                    guided.run(
                        settings=[
                            setting
                            for setting in SETTINGS
                            if not setting.startswith("subscription-reference=")
                        ],
                        config=dict(SELECTION, subscriptionRef=secret),
                        reader=refuses_to_be_read(),
                        interactive=False,
                    )
                assert_refused_at_collection(self, caught)

    def test_a_directory_identifier_is_refused_from_either_source(self):
        without = [
            setting
            for setting in SETTINGS
            if not setting.startswith("subscription-reference=")
        ]
        with self.assertRaises(guided.GuidedError) as caught:
            guided.run(
                settings=without + ["subscription-reference=%s" % IDENTIFIER],
                config=SELECTION,
                reader=refuses_to_be_read(),
                interactive=False,
            )
        assert_refused_at_collection(self, caught)
        with self.assertRaises(guided.GuidedError) as caught:
            guided.run(
                settings=without,
                config=dict(SELECTION, subscriptionRef=IDENTIFIER),
                reader=refuses_to_be_read(),
                interactive=False,
            )
        assert_refused_at_collection(self, caught)

    def test_a_malformed_value_is_refused_naming_the_expected_format(self):
        """FR-16, at the layer that has the format to name."""
        with self.assertRaises(guided.GuidedError) as caught:
            guided.run(
                settings=[
                    setting
                    for setting in SETTINGS
                    if not setting.startswith("max-tool-calls=")
                ]
                + ["max-tool-calls=not-a-number"],
                config=SELECTION,
                reader=refuses_to_be_read(),
                interactive=False,
            )
        assert_refused_at_collection(self, caught)
        self.assertIn("max-tool-calls", str(caught.exception))

    def test_a_value_of_an_unexpected_type_is_refused(self):
        with self.assertRaises(guided.GuidedError) as caught:
            guided.run(
                settings=[
                    setting
                    for setting in SETTINGS
                    if not setting.startswith("max-tool-calls=")
                ],
                config=dict(SELECTION, executionLimits={"maxToolCalls": [1]}),
                reader=refuses_to_be_read(),
                interactive=False,
            )
        self.assertIn("max-tool-calls", str(caught.exception))

    def test_control_the_same_field_is_accepted_when_it_is_well_formed(self):
        """Without this, every refusal above could be about the wrong field."""
        document = guided.run(
            settings=[
                setting
                for setting in SETTINGS
                if not setting.startswith("subscription-reference=")
            ],
            config=dict(SELECTION, subscriptionRef="sub-two"),
            reader=refuses_to_be_read(),
            interactive=False,
        )
        self.assertEqual(document["subscriptionRef"], "sub-two")


class NoRefusalRepeatsTheValue(unittest.TestCase):
    """SEC-017, extended to arguments and to configuration files."""

    def test_no_refusal_from_any_source_echoes_a_leaky_value(self):
        without = [
            setting
            for setting in SETTINGS
            if not setting.startswith("subscription-reference=")
        ]
        for value in LEAKY:
            for label, call in (
                (
                    "set",
                    lambda v=value: guided.run(
                        settings=without + ["subscription-reference=%s" % v],
                        config=SELECTION,
                        reader=refuses_to_be_read(),
                        interactive=False,
                    ),
                ),
                (
                    "config",
                    lambda v=value: guided.run(
                        settings=without,
                        config=dict(SELECTION, subscriptionRef=v),
                        reader=refuses_to_be_read(),
                        interactive=False,
                    ),
                ),
            ):
                with self.subTest(source=label, value=value):
                    with self.assertRaises(guided.GuidedError) as caught:
                        call()
                    self.assertNotIn(value, str(caught.exception))

    def test_an_argument_that_is_not_a_pair_is_not_quoted_back(self):
        """A bare argument may be the value itself, with no key to hide behind.

        This is the one shape where naming what was supplied would name the
        secret: there is no `=` to split on, so there is nothing that is
        safely only the key.
        """
        for value in LEAKY:
            with self.subTest(value=value):
                with self.assertRaises(guided.GuidedError) as caught:
                    guided.parse_settings([value])
                self.assertNotIn(value, str(caught.exception))

    def test_a_pair_keeps_the_whole_value_on_the_value_side(self):
        """Splitting on the first `=` is what makes naming the key safe."""
        key, text = guided.parse_setting("subscription-reference=a=b=c")
        self.assertEqual(key, "subscription-reference")
        self.assertEqual(text, "a=b=c")

    def test_the_refusal_helper_cannot_be_handed_the_value(self):
        """Structural, so a later edit cannot reintroduce the echo quietly."""
        import inspect

        self.assertNotIn(
            "value", inspect.signature(prompts.refusal).parameters
        )

    def test_control_each_leaky_value_is_actually_refused(self):
        """Otherwise a value that was quietly accepted passes the sweep."""
        without = [
            setting
            for setting in SETTINGS
            if not setting.startswith("subscription-reference=")
        ]
        for value in LEAKY:
            with self.subTest(value=value):
                with self.assertRaises(guided.GuidedError) as caught:
                    guided.run(
                        settings=without + ["subscription-reference=%s" % value],
                        config=SELECTION,
                        reader=refuses_to_be_read(),
                        interactive=False,
                    )
                assert_refused_at_collection(self, caught)


class EveryRequiredPropertyHasExactlyOneSource(unittest.TestCase):
    """Adding a contract property must force a decision about who supplies it."""

    def required(self):
        return set(prompts.schema()["required"])

    def settable_properties(self):
        return {
            entry.pointer.split("/")[1] for entry in prompts.REGISTER
        }

    def test_the_three_sources_account_for_every_required_property(self):
        self.assertEqual(
            self.settable_properties()
            | set(guided.FROM_CONFIG)
            | set(guided.UNSUPPLYABLE),
            self.required(),
        )

    def test_no_property_is_claimed_by_two_sources(self):
        settable = self.settable_properties()
        from_config = set(guided.FROM_CONFIG)
        unsupplyable = set(guided.UNSUPPLYABLE)
        self.assertEqual(settable & from_config, set())
        self.assertEqual(settable & unsupplyable, set())
        self.assertEqual(from_config & unsupplyable, set())

    def test_the_configuration_fields_are_the_derived_ones_that_can_be_given(self):
        self.assertEqual(
            set(guided.FROM_CONFIG),
            set(prompts.DERIVED) - set(guided.UNSUPPLYABLE),
        )

    def test_neither_unsupplyable_property_can_be_given(self):
        """They are excluded because supplying them is meaningless, not to
        make the arithmetic work."""
        self.assertEqual(
            scope_emitter.SCHEMA_VERSION,
            non_interactive_document()["schemaVersion"],
        )
        forced = guided.run(
            settings=SETTINGS,
            config=dict(
                SELECTION, schemaVersion="9.9.9", canonicalHash="0" * 64
            ),
            reader=refuses_to_be_read(),
            interactive=False,
        )
        self.assertEqual(forced["schemaVersion"], scope_emitter.SCHEMA_VERSION)
        self.assertNotEqual(forced[scope_emitter.HASH_FIELD], "0" * 64)


class TheCommandLineIsUsable(unittest.TestCase):
    """The surface an operator and a CI job actually touch."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="zeroops-guided-")
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.config = os.path.join(self.directory, "selection.json")
        with open(self.config, "wb") as handle:
            handle.write(
                json.dumps(SELECTION, indent=2).encode("utf-8")
            )
        self.out = os.path.join(self.directory, "scope-contract.json")

    def run_main(self, argv):
        captured = io.StringIO()
        original = sys.stdout
        sys.stdout = captured
        try:
            code = guided.main(argv)
        finally:
            sys.stdout = original
        return code, captured.getvalue()

    def test_a_non_interactive_invocation_writes_the_contract(self):
        argv = ["--non-interactive", "--config", self.config, "--out", self.out]
        for setting in SETTINGS:
            argv += ["--set", setting]
        code, output = self.run_main(argv)
        self.assertEqual(code, guided.EXIT_OK, output)
        with open(self.out, "rb") as handle:
            written = handle.read()
        self.assertEqual(
            written, scope_emitter.render(non_interactive_document())
        )

    def test_explain_lists_every_set_key_and_every_configuration_field(self):
        code, output = self.run_main(["--explain"])
        self.assertEqual(code, guided.EXIT_OK)
        for key in guided.setting_keys():
            self.assertIn("--set %s=" % key, output)
        for name in guided.FROM_CONFIG:
            self.assertIn(name, output)

    def test_an_unrecognised_argument_is_refused(self):
        code, output = self.run_main(["--deploy-now"])
        self.assertEqual(code, guided.EXIT_REFUSED)
        self.assertIn("--deploy-now", output)

    def test_a_flag_without_its_value_is_refused(self):
        code, _ = self.run_main(["--config"])
        self.assertEqual(code, guided.EXIT_REFUSED)

    def test_a_missing_configuration_file_is_refused_by_name(self):
        missing = os.path.join(self.directory, "not-here.json")
        code, output = self.run_main(["--non-interactive", "--config", missing])
        self.assertEqual(code, guided.EXIT_REFUSED)
        self.assertIn("not-here.json", output)

    def test_a_configuration_that_is_not_json_is_refused(self):
        broken = os.path.join(self.directory, "broken.json")
        with open(broken, "wb") as handle:
            handle.write(b"{not json")
        code, _ = self.run_main(["--non-interactive", "--config", broken])
        self.assertEqual(code, guided.EXIT_REFUSED)

    def test_a_refused_run_writes_no_file(self):
        code, _ = self.run_main(
            ["--non-interactive", "--config", self.config, "--out", self.out]
        )
        self.assertEqual(code, guided.EXIT_REFUSED)
        self.assertFalse(os.path.exists(self.out))


class ThePageDocumentsTheNonInteractiveRun(unittest.TestCase):
    """The documentation is derived from the module, so it cannot drift."""

    def page(self):
        path = os.path.join(validate.repo_root(), "docs", "non-interactive.md")
        with open(path, "rb") as handle:
            return handle.read().decode("utf-8")

    def test_the_page_names_every_set_key(self):
        text = self.page()
        for key in guided.setting_keys():
            self.assertIn("`%s`" % key, text)

    def test_the_page_names_every_configuration_field(self):
        text = self.page()
        for name in guided.FROM_CONFIG:
            self.assertIn("`%s`" % name, text)

    def test_the_page_names_the_command(self):
        self.assertIn("python -m zeroops.guided", self.page())

    def test_the_page_states_that_a_refusal_does_not_repeat_the_value(self):
        self.assertIn("never repeats the value", self.page())


if __name__ == "__main__":
    unittest.main()

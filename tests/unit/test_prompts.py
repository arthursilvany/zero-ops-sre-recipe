"""The guided step's input collection (FR-15, FR-16, FR-17, SEC-017).

Four properties, and the fourth is the one the other three make hard.

Every collected input is consumed by the contract. Every input is explained
before it is asked for, not merely somewhere. The accepted format is the
schema's, read at run time rather than restated. And no rejection ever
repeats what was typed, which is what stops the most actionable possible
error message from being the thing that writes a credential to a scrollback.

Each class carries a control, because every one of these properties has a
degenerate way to pass: a register that is empty, an explanation nobody
reads, a format check that rejects everything, a message that says nothing.
"""

import copy
import inspect
import os
import unittest

from zeroops import prompts, scope_emitter, validate


PERIOD_START = "2026-09-01T00:00:00Z"

PERIOD_END = "2026-09-29T00:00:00Z"

# One accepted value per register entry. Kept as data so a new input without
# a known-good value fails the completeness check below rather than being
# quietly skipped by every test that iterates the register.
ACCEPTED = {
    "subscription-reference": "primary-subscription",
    "observation-start": PERIOD_START,
    "observation-end": PERIOD_END,
    "max-tool-calls": "50",
    "max-wall-clock-seconds": "600",
    "max-result-set-rows": "1000",
    "per-query-timeout-seconds": "30",
}

# One rejected value per entry, each distinctive enough that its presence in
# a message is unambiguous.
REJECTED = {
    "subscription-reference": "Not_A_Reference_Name",
    "observation-start": "next tuesday",
    "observation-end": "2026-09-29",
    "max-tool-calls": "zero",
    "max-wall-clock-seconds": "0",
    "max-result-set-rows": "-7",
    "per-query-timeout-seconds": "1.5",
}

SECRETS = (
    "AccountKey=not-a-real-key",
    "SharedAccessKey=not-a-real-key",
    "client_secret=not-a-real-key",
    "pwd=not-a-real-key",
)

# Shaped like a directory identifier and deliberately not one. SEC-017 covers
# identifier-bearing fields as well as secret-bearing ones, and this is the
# value the reference input exists to keep out of a committed file, so it is
# the last thing a rejection should write to a terminal.
IDENTIFIER = "a1b2c3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d"

# Everything that must never come back out, whichever branch refuses it.
LEAKY = SECRETS + (IDENTIFIER,)


def entries():
    return {entry.id: entry for entry in prompts.REGISTER}


class Recorder:
    """An injectable terminal that remembers the order things happened in."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.events = []

    def write(self, line):
        self.events.append(("write", line))

    def read(self):
        self.events.append(("read", None))
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)

    def written(self):
        return [line for kind, line in self.events if kind == "write"]


class EveryCollectedInputIsConsumed(unittest.TestCase):
    """FR-15: nothing is asked for that no downstream field uses."""

    def test_the_register_is_not_empty(self):
        self.assertTrue(
            prompts.REGISTER, "an empty register passes every other test here"
        )

    def test_every_pointer_resolves_in_the_real_schema(self):
        for entry in prompts.REGISTER:
            subschema, _ = prompts.subschema_at(entry.pointer)
            self.assertIsInstance(subschema, dict, entry.id)

    def test_a_pointer_at_no_property_is_refused(self):
        bogus = prompts.Input(
            id="invented", pointer="/notAProperty", explanation="none"
        )
        with self.assertRaises(prompts.PromptError) as caught:
            prompts.subschema_at(bogus.pointer)
        self.assertIn("collected and never used", str(caught.exception))

    def test_the_register_and_the_derived_list_account_for_the_schema(self):
        """The completeness check, in both directions.

        Adding a required property to the contract has to force a decision
        about who supplies it. Checking only one direction would let a
        property appear with nobody filling it, or an input persist after the
        field it fed was removed.
        """
        required = set(prompts.schema()["required"])
        collected = {
            entry.pointer.split("/")[1] for entry in prompts.REGISTER
        }
        self.assertEqual(
            collected | set(prompts.DERIVED),
            required,
            "the register and DERIVED together must name every required "
            "property of the scope contract, and nothing else",
        )
        self.assertEqual(
            collected & set(prompts.DERIVED),
            set(),
            "a property cannot be both collected and derived",
        )

    def test_every_derived_property_says_where_it_comes_from(self):
        for name, reason in prompts.DERIVED.items():
            self.assertTrue(reason.strip(), name)

    def test_every_entry_has_an_accepted_and_a_rejected_value_here(self):
        self.assertEqual(set(ACCEPTED), set(entries()))
        self.assertEqual(set(REJECTED), set(entries()))

    def test_the_collected_answers_drive_the_emitter(self):
        """Consumption proven by consuming, not by a table.

        This is the only assertion in the class that would notice if
        `arguments` produced a shape the emitter cannot take.
        """
        answers = {
            name: prompts.check(entries()[name], text)[0]
            for name, text in ACCEPTED.items()
        }
        supplied = prompts.arguments(answers)
        document = scope_emitter.build(
            in_scope=[{"kind": "resourceGroup", "selector": "rg-one"}],
            out_of_scope=[],
            generated_at="2026-09-29T12:00:00Z",
            generated_against="discovery-run-17",
            **supplied
        )
        self.assertEqual(document["subscriptionRef"], "primary-subscription")
        self.assertEqual(
            document["observationPeriod"],
            {"start": PERIOD_START, "end": PERIOD_END},
        )
        self.assertEqual(document["executionLimits"]["maxToolCalls"], 50)

    def test_an_answer_that_was_never_collected_is_refused(self):
        with self.assertRaises(prompts.PromptError):
            prompts.arguments({"subscription-reference": "primary-subscription"})


class EveryInputIsExplainedWhereItIsAsked(unittest.TestCase):
    """FR-15: at the point of collection, not in a manual somewhere."""

    def test_the_explanation_names_the_input_and_the_format(self):
        for entry in prompts.REGISTER:
            text = prompts.explain(entry)
            self.assertIn(entry.id, text)
            self.assertIn(entry.explanation, text)
            self.assertIn(
                prompts.expected_format(entry.pointer), text, entry.id
            )

    def test_no_explanation_is_empty_or_shared(self):
        seen = set()
        for entry in prompts.REGISTER:
            self.assertTrue(len(entry.explanation.strip()) > 30, entry.id)
            self.assertNotIn(entry.explanation, seen, entry.id)
            seen.add(entry.explanation)

    def test_the_explanation_is_written_before_the_value_is_read(self):
        """The ordering is the requirement.

        Explaining every input after collecting them all would satisfy a test
        that only looked for the text.
        """
        first = prompts.REGISTER[0]
        terminal = Recorder([ACCEPTED[entry.id] for entry in prompts.REGISTER])
        prompts.collect(reader=terminal.read, writer=terminal.write)
        self.assertEqual(terminal.events[0][0], "write")
        self.assertIn(first.explanation, terminal.events[0][1])
        self.assertEqual(terminal.events[1][0], "read")

    def test_every_input_is_explained_during_a_run(self):
        terminal = Recorder([ACCEPTED[entry.id] for entry in prompts.REGISTER])
        answers = prompts.collect(
            reader=terminal.read, writer=terminal.write
        )
        written = "\n".join(terminal.written())
        for entry in prompts.REGISTER:
            self.assertIn(entry.explanation, written, entry.id)
        self.assertEqual(set(answers), set(entries()))


class TheFormatComesFromTheSchema(unittest.TestCase):
    """FR-16: derived at run time, not restated in this module."""

    def test_the_format_quotes_the_schema_pattern_verbatim(self):
        document = prompts.schema()
        pattern = document["$defs"][prompts.REFERENCE_DEF]["pattern"]
        self.assertIn(pattern, prompts.expected_format("/subscriptionRef"))

    def test_tightening_the_schema_tightens_the_stated_format(self):
        """The test that a restated constant would fail.

        If the pattern were written into this module, the format would keep
        naming the old one while the schema rejected against the new one.
        """
        document = copy.deepcopy(prompts.schema())
        document["$defs"][prompts.REFERENCE_DEF]["pattern"] = "^only-this$"
        self.assertIn(
            "^only-this$",
            prompts.expected_format("/subscriptionRef", document),
        )

    def test_tightening_the_schema_tightens_what_is_accepted(self):
        document = copy.deepcopy(prompts.schema())
        document["$defs"][prompts.REFERENCE_DEF]["pattern"] = "^only-this$"
        entry = entries()["subscription-reference"]
        value, reason = prompts.check(entry, "only-this", document)
        self.assertEqual(value, "only-this")
        self.assertIsNone(reason)
        value, reason = prompts.check(entry, "primary-subscription", document)
        self.assertIsNone(
            value, "the previously accepted value survived a tightening"
        )
        self.assertIsNotNone(reason)

    def test_a_field_with_no_stated_constraint_is_refused(self):
        """A prompt that cannot name a format must not silently omit one."""
        document = copy.deepcopy(prompts.schema())
        document["$defs"][prompts.REFERENCE_DEF] = {"description": "none"}
        with self.assertRaises(prompts.PromptError) as caught:
            prompts.expected_format("/subscriptionRef", document)
        self.assertIn("no checkable constraint", str(caught.exception))

    def test_only_schema_defined_keywords_reach_the_message(self):
        for entry in prompts.REGISTER:
            subschema, _ = prompts.subschema_at(entry.pointer)
            stated = prompts.expected_format(entry.pointer)
            for keyword in validate.SHAPE_KEYWORDS:
                if keyword in subschema:
                    self.assertIn(keyword, stated, entry.id)
            self.assertNotIn(
                "description", stated, "schema prose is not a format"
            )


class InvalidInputIsRejectedNamingTheFormat(unittest.TestCase):
    """FR-16, the rejection itself."""

    def test_the_accepted_value_is_accepted(self):
        """The control. Without it, rejecting everything would pass below."""
        for name, text in ACCEPTED.items():
            value, reason = prompts.check(entries()[name], text)
            self.assertIsNone(reason, name)
            self.assertIsNotNone(value, name)

    def test_the_rejected_value_is_rejected_and_the_format_is_named(self):
        for name, text in REJECTED.items():
            entry = entries()[name]
            value, reason = prompts.check(entry, text)
            self.assertIsNone(value, name)
            self.assertIn("Expected format:", reason, name)
            self.assertIn(prompts.expected_format(entry.pointer), reason, name)
            self.assertIn(entry.id, reason, name)

    def test_a_wrong_answer_is_followed_by_another_chance(self):
        entry = prompts.REGISTER[0]
        terminal = Recorder(
            [REJECTED[entry.id]]
            + [ACCEPTED[item.id] for item in prompts.REGISTER]
        )
        answers = prompts.collect(reader=terminal.read, writer=terminal.write)
        self.assertEqual(answers[entry.id], ACCEPTED[entry.id])

    def test_collection_gives_up_rather_than_asking_forever(self):
        entry = prompts.REGISTER[0]
        terminal = Recorder([REJECTED[entry.id]] * prompts.MAX_ATTEMPTS)
        with self.assertRaises(prompts.PromptError) as caught:
            prompts.collect(reader=terminal.read, writer=terminal.write)
        self.assertIn("after %d attempts" % prompts.MAX_ATTEMPTS,
                      str(caught.exception))

    def test_exhausted_input_ends_collection_instead_of_spinning(self):
        """End of input is not a wrong answer.

        A loop that re-prompts on EOF spins forever the first time it runs
        with anything other than a person on the other end, which is every
        automated run.
        """
        terminal = Recorder([])
        with self.assertRaises(prompts.PromptError) as caught:
            prompts.collect(reader=terminal.read, writer=terminal.write)
        self.assertIn("input ended", str(caught.exception))


class NoRejectionRepeatsTheValue(unittest.TestCase):
    """SEC-017: the tension between FR-16 and FR-17, resolved."""

    def test_the_rejected_value_appears_in_no_message(self):
        for name, text in REJECTED.items():
            _, reason = prompts.check(entries()[name], text)
            self.assertNotIn(text, reason, name)

    def test_a_secret_or_identifier_appears_in_no_message(self):
        for entry in prompts.REGISTER:
            for value in LEAKY:
                _, reason = prompts.check(entry, value)
                self.assertIsNotNone(reason, "%s %s" % (entry.id, value))
                self.assertNotIn(value, reason)
                self.assertNotIn("not-a-real-key", reason)

    def test_every_leaky_value_is_refused_by_a_branch_that_names_itself(self):
        """The control on the sweep above.

        A value nothing refuses is absent from every message trivially. This
        pins that each one is actually rejected, and that the reason given is
        about the value rather than a generic fallback.
        """
        entry = entries()["subscription-reference"]
        _, secret_reason = prompts.check(entry, SECRETS[0])
        self.assertIn("credential material", secret_reason)
        _, identifier_reason = prompts.check(entry, IDENTIFIER)
        self.assertIn("directory identifier", identifier_reason)

    def test_a_secret_appears_nowhere_a_run_writes(self):
        terminal = Recorder(
            [SECRETS[0], IDENTIFIER]
            + [ACCEPTED[item.id] for item in prompts.REGISTER]
        )
        prompts.collect(reader=terminal.read, writer=terminal.write)
        written = "\n".join(terminal.written())
        self.assertNotIn(SECRETS[0], written)
        self.assertNotIn("not-a-real-key", written)
        self.assertNotIn(IDENTIFIER, written)

    def test_the_message_still_says_something(self):
        """The control. An empty message repeats nothing either."""
        for name, text in REJECTED.items():
            _, reason = prompts.check(entries()[name], text)
            self.assertIn(name, reason)
            self.assertTrue(len(reason) > 40, name)

    def test_the_refusal_is_not_given_the_value_to_leak(self):
        """Structural, so a future edit cannot reintroduce the echo quietly.

        A test on the text alone passes again the moment somebody adds the
        value back under a fixture this file does not happen to use.
        """
        taken = set(inspect.signature(prompts.refusal).parameters)
        self.assertEqual(taken, {"entry", "reason", "document"})


class NoSecretIsCollectedInPlainText(unittest.TestCase):
    """FR-17, including the identifier the reference exists to keep out."""

    def test_every_secret_shape_is_refused_for_every_input(self):
        for entry in prompts.REGISTER:
            for secret in SECRETS:
                value, reason = prompts.check(entry, secret)
                self.assertIsNone(value, "%s %s" % (entry.id, secret))
                self.assertIn("credential material", reason)

    def test_the_reference_input_refuses_a_directory_identifier(self):
        entry = entries()["subscription-reference"]
        value, reason = prompts.check(entry, IDENTIFIER)
        self.assertIsNone(value)
        self.assertIn("directory identifier", reason)

    def test_the_schema_alone_would_have_accepted_that_identifier(self):
        """Otherwise the check above is dead code passing for a wrong reason.

        `externalReferenceName` admits lowercase hyphenated text, and a GUID
        beginning with a letter is lowercase hyphenated text.
        """
        document = prompts.schema()
        subschema, _ = prompts.subschema_at("/subscriptionRef", document)
        self.assertEqual(
            validate.structural_findings(IDENTIFIER, subschema), []
        )

    def test_which_input_is_a_reference_is_decided_by_the_schema(self):
        for entry in prompts.REGISTER:
            _, name = prompts.subschema_at(entry.pointer)
            expected = name == prompts.REFERENCE_DEF
            self.assertEqual(
                bool(prompts.forbidden_shapes(name)), expected, entry.id
            )
        self.assertEqual(
            prompts.forbidden_shapes(prompts.REFERENCE_DEF),
            scope_emitter.REFERENCE_FORBIDDEN,
        )

    def test_a_reference_name_that_is_not_an_identifier_is_accepted(self):
        """The control. The refusal is about the shape, not about the field."""
        entry = entries()["subscription-reference"]
        value, reason = prompts.check(entry, "primary-subscription")
        self.assertIsNone(reason)
        self.assertEqual(value, "primary-subscription")


class ThePageDocumentsTheCollection(unittest.TestCase):
    """The page is derived from the register, so it cannot fall behind it."""

    def page(self):
        path = os.path.join(validate.repo_root(), "docs", "guided-inputs.md")
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_the_page_names_the_command(self):
        self.assertIn("python -m zeroops.prompts --explain", self.page())

    def test_every_input_and_its_pointer_is_on_the_page(self):
        text = self.page()
        for entry in prompts.REGISTER:
            self.assertIn("`%s`" % entry.id, text)
            self.assertIn("`%s`" % entry.pointer, text)

    def test_every_derived_field_is_accounted_for_on_the_page(self):
        text = self.page()
        for name in prompts.DERIVED:
            self.assertIn("`%s`" % name, text)

    def test_the_page_states_that_a_rejection_never_repeats_the_value(self):
        self.assertIn("never repeats the value", self.page())


if __name__ == "__main__":
    unittest.main()

"""The guided step's input collection: explained, format-checked, secret-free.

Three requirements meet here, and two of them pull against each other.

FR-15 asks that only required inputs are collected and that each is explained
where it is asked for. FR-16 asks that an invalid value is rejected with a
message naming the expected format. FR-17 asks that no secret is collected or
persisted in plain text.

The tension is in FR-16. The most actionable rejection a prompt can write is
"'hunter2' is not a valid connection reference", and that is also how a secret
reaches a terminal scrollback, a screen recording and the issue somebody
pastes it into. SEC-017 resolves it: a rejection names the input, the
explanation and the expected format, and never the supplied value. Every
string this module writes is either schema content or register content, and
neither is ever the value that was typed.

The second design commitment is that the accepted format is *derived* from
`contracts/schemas/scope-contract.schema.json` rather than restated here. A
prompt that restates a constraint is a second copy of it, and the copy is the
one that goes stale: the schema tightens, the prompt keeps accepting, and the
rejection arrives later from the validator with less context. Each register
entry therefore carries a JSON pointer, and the pattern, bounds and type come
from the schema at that pointer at run time.

What is not collected is as deliberate as what is. `DERIVED` names every
remaining required property of the contract together with where it actually
comes from, and a test asserts that the register and `DERIVED` together
account for the schema's `required` list exactly. Adding a property to the
contract therefore forces a decision about who supplies it, rather than
silently producing an input nobody asks for or a field nobody fills.
"""

import collections
import re
import sys

from zeroops import scope_emitter, validate


KIND = "scope-contract"

MAX_ATTEMPTS = 3

REFERENCE_DEF = "externalReferenceName"

EXIT_OK = 0
EXIT_REFUSED = 1


class PromptError(Exception):
    """Collection could not continue."""


Input = collections.namedtuple("Input", "id pointer explanation")


REGISTER = (
    Input(
        id="subscription-reference",
        pointer="/subscriptionRef",
        explanation=(
            "The name of the entry in the framework configuration's "
            "externalReferences that resolves to the subscription to "
            "observe. This is a name, not a subscription identifier: the "
            "contract is committed, so the identifier stays outside it."
        ),
    ),
    Input(
        id="observation-start",
        pointer="/observationPeriod/start",
        explanation=(
            "The earliest point in time the agent may look back to. "
            "Anything before this is outside the window it was granted."
        ),
    ),
    Input(
        id="observation-end",
        pointer="/observationPeriod/end",
        explanation=(
            "The latest point in time the agent may look at. Together with "
            "the start this bounds the window, so an agent cannot widen its "
            "own view by running for longer."
        ),
    ),
    Input(
        id="max-tool-calls",
        pointer="/executionLimits/maxToolCalls",
        explanation=(
            "How many tool calls a single run may make before it stops. The "
            "bound on how much work one run can cause."
        ),
    ),
    Input(
        id="max-wall-clock-seconds",
        pointer="/executionLimits/maxWallClockSeconds",
        explanation=(
            "How long a single run may take before it stops, in seconds. "
            "The bound that still applies when each individual call is fast."
        ),
    ),
    Input(
        id="max-result-set-rows",
        pointer="/executionLimits/maxResultSetRows",
        explanation=(
            "How many rows a single query may return. The bound on how much "
            "of the environment one answer can carry back."
        ),
    ),
    Input(
        id="per-query-timeout-seconds",
        pointer="/executionLimits/perQueryTimeoutSeconds",
        explanation=(
            "How long one query may run before it is abandoned, in seconds. "
            "The bound that keeps a single slow query from consuming the "
            "whole wall-clock allowance."
        ),
    ),
)


DERIVED = {
    "schemaVersion": "pinned by the schema, so asking would invite a wrong answer",
    "inScope": "taken from the discovery selection, not typed",
    "outOfScope": "taken from the discovery selection, not typed",
    "generatedAt": "the clock at the moment the contract is emitted",
    "generatedAgainst": "the marker for the discovery run the selection was taken against",
    "canonicalHash": "computed over the finished document, so it cannot be supplied",
}


def schema():
    return validate.load_json(
        validate.schema_path_for(KIND), "scope contract schema"
    )


def resolve(node, document):
    """Follow a local $ref, returning the subschema and the def it names."""
    name = None
    seen = 0
    while isinstance(node, dict) and "$ref" in node:
        seen += 1
        if seen > 10:
            raise PromptError("the schema's $ref chain does not terminate")
        reference = node["$ref"]
        prefix = "#/$defs/"
        if not reference.startswith(prefix):
            raise PromptError(
                "only local $defs references are resolvable, not '%s'"
                % reference
            )
        name = reference[len(prefix):]
        definitions = document.get("$defs", {})
        if name not in definitions:
            raise PromptError(
                "the schema has no definition named '%s'" % name
            )
        node = definitions[name]
    return node, name


def subschema_at(pointer, document=None):
    """The subschema a register pointer names, with its $defs name."""
    document = schema() if document is None else document
    node, name = resolve(document, document)
    for part in pointer.split("/")[1:]:
        properties = node.get("properties") if isinstance(node, dict) else None
        if not isinstance(properties, dict) or part not in properties:
            raise PromptError(
                "the scope contract schema has no property at '%s', so the "
                "input that names it would be collected and never used"
                % pointer
            )
        node, name = resolve(properties[part], document)
    return node, name


def forbidden_shapes(name):
    """Identifier shapes an input may not carry, decided by its schema def.

    An input that names an external reference must not be given the thing the
    reference exists to keep out of the file. The schema cannot enforce that
    on its own: `externalReferenceName`'s pattern admits any lowercase
    hyphenated string, and a directory identifier is one.
    """
    return scope_emitter.REFERENCE_FORBIDDEN if name == REFERENCE_DEF else ()


def expected_format(pointer, document=None):
    """The accepted shape, in the schema's own words (SEC-017)."""
    subschema, _ = subschema_at(pointer, document)
    parts = []
    for keyword in validate.SHAPE_KEYWORDS:
        if keyword not in subschema:
            continue
        hint = validate.expected_shape_hint(keyword, subschema[keyword])
        if hint:
            parts.append(hint.replace(". Expected ", "", 1))
    if not parts:
        raise PromptError(
            "the schema states no checkable constraint at '%s', so a "
            "rejection there could not name a format" % pointer
        )
    return "; ".join(parts)


def explain(entry, document=None):
    """What is asked for, and what will be accepted (FR-15)."""
    return "%s\n  %s\n  Expected format: %s" % (
        entry.id,
        entry.explanation,
        expected_format(entry.pointer, document),
    )


def refusal(entry, reason, document=None):
    """Why the value was not accepted, without repeating it (SEC-017).

    Every fragment is either register content or schema content. The supplied
    value is not a parameter of this function, so it cannot leak through it.
    """
    return "%s was not accepted: %s. Expected format: %s" % (
        entry.id,
        reason,
        expected_format(entry.pointer, document),
    )


_INTEGER = re.compile(r"^-?[0-9]+$")


def coerce(subschema, text):
    """The typed value the schema asks for, or None if the text is not one."""
    if subschema.get("type") == "integer":
        if not _INTEGER.match(text.strip()):
            return None
        return int(text.strip())
    return text


def check(entry, text, document=None):
    """(value, reason). A reason of None means the value was accepted.

    Secret and identifier shapes are refused before the schema is consulted,
    because the schema would accept several of them: a connection string is a
    perfectly valid string, and a directory identifier matches the reference
    pattern. Order matters for the message as well as for the outcome, since
    "does not match the pattern" would be a true and useless thing to say
    about a leaked credential.
    """
    document = schema() if document is None else document
    subschema, name = subschema_at(entry.pointer, document)

    if scope_emitter.secret_findings(text):
        return None, refusal(
            entry,
            "it carries credential material, which is never collected in "
            "plain text (FR-17)",
            document,
        )

    shapes = forbidden_shapes(name)
    if shapes and scope_emitter.shape_findings(text, shapes):
        return None, refusal(
            entry,
            "it looks like a directory identifier rather than the name of a "
            "reference to one",
            document,
        )

    value = coerce(subschema, text)
    if value is None:
        return None, refusal(entry, "it is not of the required type", document)

    if validate.structural_findings(value, subschema):
        return None, refusal(entry, "it does not match the schema", document)

    return value, None


def collect(entries=REGISTER, reader=None, writer=None, document=None):
    """Ask for each input in turn, explaining it and checking what comes back.

    The reader is a parameter so this is drivable without a terminal. An
    exhausted reader is a refusal rather than a re-prompt: a loop that treats
    end of input as a wrong answer spins forever the moment it is run with
    anything other than a human on the other end.
    """
    document = schema() if document is None else document
    reader = input if reader is None else reader
    writer = (lambda line: print(line)) if writer is None else writer

    answers = {}
    for entry in entries:
        for _ in range(MAX_ATTEMPTS):
            writer(explain(entry, document))
            try:
                text = reader()
            except EOFError:
                raise PromptError(
                    "input ended while %s was still being asked for" % entry.id
                )
            if text is None:
                raise PromptError(
                    "input ended while %s was still being asked for" % entry.id
                )
            value, reason = check(entry, text, document)
            if reason is None:
                answers[entry.id] = value
                break
            writer(reason)
        else:
            raise PromptError(
                "%s was not supplied in an accepted form after %d attempts"
                % (entry.id, MAX_ATTEMPTS)
            )
    return answers


def arguments(answers):
    """The collected answers, shaped for the emitter that consumes them.

    Built from the register's pointers rather than from a second list of
    names, so an input that is collected and never consumed is not
    expressible here.
    """
    nested = {}
    for entry in REGISTER:
        if entry.id not in answers:
            raise PromptError("%s was never collected" % entry.id)
        parts = entry.pointer.split("/")[1:]
        target = nested
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = answers[entry.id]
    return {
        "subscription_ref": nested["subscriptionRef"],
        "observation_period": nested["observationPeriod"],
        "execution_limits": nested["executionLimits"],
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "--explain":
        for entry in REGISTER:
            print(explain(entry))
            print("")
        return EXIT_OK
    try:
        answers = collect()
    except PromptError as failure:
        print(str(failure))
        return EXIT_REFUSED
    for key in sorted(arguments(answers)):
        print("%s collected" % key)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

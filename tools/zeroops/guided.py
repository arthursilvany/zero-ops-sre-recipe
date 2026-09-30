"""Non-interactive execution, `--set` parity, and byte-identical output.

FR-18 asks that the guided step be drivable entirely from a version-controlled
file. FR-19 asks that interactive and non-interactive execution with equivalent
inputs produce identical artifacts, where identical means what ADR-0004 pins:
NFC normalisation, then RFC 8785 canonicalisation, then LF.

The parity claim is precise, and worth stating plainly because the loose
version of it is false. Two runs are byte-identical when their *inputs* are
equivalent, and the clock is an input. A non-interactive run that invents a
fresh `generatedAt` is not reproducing an earlier run and is not meant to; it
is starting a new one. That is why the clock is supplied rather than read here,
and why a configuration that already records a `generatedAt` reuses it. CC-005
is the case that matters: the file a prior interactive run emitted drives a
later run to the same bytes.

The emitted scope contract is itself a valid configuration. No second file
format is introduced, because a second format is a second thing that can drift
from the contract, and the contract already carries every value needed to
rebuild itself. Answers are found in a configuration by following the register
pointers that define them, so a contract and a bare selection file are read by
one code path rather than two.

Three properties are structural rather than asserted by convention.

Every settable key *is* a register entry id, computed from the register, so a
prompt without a `--set` key is not expressible. The test that matters injects
a register and asserts the key set moves with it; a restated list fails it.

Configuration values and `--set` values are converted to one representation and
passed through the same `prompts.check`. Two validation paths is how a
configuration comes to accept what a prompt refuses.

A refusal never repeats a supplied value, extending SEC-017 to this surface. A
`--set` argument is the likeliest place for a pasted connection string, and it
already reaches shell history and CI logs; quoting it in the rejection copies
it into the build output too. Splitting on the first `=` is what makes naming
the key safe, since everything after it stays in the value.
"""

import datetime
import json
import os
import sys

from zeroops import prompts, scope_emitter


# `schemaVersion` is pinned by the emitter and `canonicalHash` is computed over
# the finished document. Neither can be supplied, so neither is a setting nor a
# configuration field. Everything else the register does not ask for has to
# arrive from somewhere, and this is the statement of where.
UNSUPPLYABLE = ("schemaVersion", scope_emitter.HASH_FIELD)

FROM_CONFIG = tuple(sorted(set(prompts.DERIVED) - set(UNSUPPLYABLE)))

CLOCK_FIELD = "generatedAt"

EXIT_OK = 0
EXIT_REFUSED = 1

USAGE = (
    "usage: python -m zeroops.guided [--explain] [--non-interactive] "
    "[--config PATH] [--set key=value ...] [--out PATH]"
)


class GuidedError(Exception):
    """The run could not continue."""


def setting_keys(entries=prompts.REGISTER):
    """Every prompt's `--set` key, computed from the prompts themselves.

    CC-005 requires that no interactive prompt lack a scriptable equivalent.
    Deriving the keys is stronger than testing for the gap afterwards: the
    gap has no representation.
    """
    return tuple(entry.id for entry in entries)


def entry_for(key, entries=prompts.REGISTER):
    """The register entry a `--set` key names, or a refusal listing the keys."""
    for entry in entries:
        if entry.id == key:
            return entry
    raise GuidedError(
        "'%s' is not a settable input. The settable inputs are: %s"
        % (key, ", ".join(setting_keys(entries)))
    )


def parse_setting(argument, entries=prompts.REGISTER):
    """(key, text) from one `--set` argument, refused without being echoed."""
    if not isinstance(argument, str) or "=" not in argument:
        raise GuidedError(
            "a --set argument must be written key=value, and the one "
            "supplied was not. It is not repeated here, because an argument "
            "that is not a pair may be a bare value (SEC-017). The settable "
            "inputs are: %s" % ", ".join(setting_keys(entries))
        )
    key, _, text = argument.partition("=")
    return key.strip(), text


def parse_settings(arguments, entries=prompts.REGISTER):
    """Every `--set` argument, as a mapping of register id to supplied text."""
    settings = {}
    for argument in arguments:
        key, text = parse_setting(argument, entries)
        entry_for(key, entries)
        if key in settings:
            raise GuidedError(
                "%s was set more than once. Which value won would depend on "
                "argument order, and a run whose outcome depends on argument "
                "order is not the reproducible one FR-18 asks for." % key
            )
        settings[key] = text
    return settings


def read_config(path):
    """A configuration document, which may be a previously emitted contract."""
    if not os.path.isfile(path):
        raise GuidedError(
            "there is no configuration at '%s'. A non-interactive run is "
            "driven by a file, so there is nothing to run from." % path
        )
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as failure:
        raise GuidedError(
            "the configuration at '%s' is not readable JSON: %s"
            % (path, failure)
        )
    if not isinstance(document, dict):
        raise GuidedError(
            "the configuration at '%s' is not an object, so it names no "
            "inputs." % path
        )
    return document


def config_answers(config, entries=prompts.REGISTER):
    """The answers a configuration already carries, found by register pointer.

    Following the pointers is what lets an emitted contract be a configuration
    without declaring it one. A field the register does not name is not read,
    so a contract's derived fields do not arrive here as answers.
    """
    found = {}
    for entry in entries:
        node = config
        for part in entry.pointer.split("/")[1:]:
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if node is not None:
            found[entry.id] = node
    return found


def as_text(value, entry):
    """One representation, so a configuration and a `--set` meet one check."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise GuidedError(
            "%s was supplied as a %s, and an input is either text or a "
            "number. The value is not repeated here (SEC-017)."
            % (entry.id, type(value).__name__)
        )
    return value if isinstance(value, str) else str(value)


def resolve_answers(
    settings,
    config,
    entries=prompts.REGISTER,
    document=None,
    reader=None,
    writer=None,
    interactive=True,
):
    """Every register answer, from `--set`, then configuration, then prompting.

    A `--set` overrides a configuration, because the configuration is the
    committed baseline and the argument is the deliberate deviation from it.
    """
    document = prompts.schema() if document is None else document
    writer = (lambda line: print(line)) if writer is None else writer

    supplied = dict(config_answers(config, entries))
    supplied.update(settings)

    answers = {}
    pending = []
    for entry in entries:
        if entry.id not in supplied:
            pending.append(entry)
            continue
        value, reason = prompts.check(
            entry, as_text(supplied[entry.id], entry), document
        )
        if reason is not None:
            raise GuidedError(reason)
        answers[entry.id] = value

    if pending:
        if not interactive:
            raise GuidedError(
                "--non-interactive was requested, but %s had no value from "
                "--config or --set. A non-interactive run does not prompt, "
                "so it stops here rather than blocking on a terminal that is "
                "not there. Supply it with --set <key>=<value>."
                % ", ".join(entry.id for entry in pending)
            )
        try:
            answers.update(
                prompts.collect(tuple(pending), reader, writer, document)
            )
        except prompts.PromptError as failure:
            raise GuidedError(str(failure))
    return answers


def utc_now():
    """The wall clock, in the shape the contract records."""
    moment = datetime.datetime.now(datetime.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def reproduction(config, clock=None):
    """The required contract fields no prompt asks for.

    The selection and the discovery marker come from the discovery stage that
    produced them; a guided run asks questions and does not invent a scope.
    The clock is the one field with a fallback, because a first run has no
    earlier moment to reuse, and reusing the recorded one is exactly what
    makes a later run reproduce the earlier bytes.
    """
    required = [name for name in FROM_CONFIG if name != CLOCK_FIELD]
    missing = [name for name in required if name not in config]
    if missing:
        raise GuidedError(
            "the configuration supplies no %s. Those come from the discovery "
            "stage that produced the selection, not from an answer."
            % ", ".join(missing)
        )

    generated_at = config.get(CLOCK_FIELD)
    if generated_at is None:
        if clock is None:
            raise GuidedError(
                "the configuration records no %s and no clock was supplied, "
                "so the run has no defensible moment to record." % CLOCK_FIELD
            )
        generated_at = clock()

    fixed = {name: config[name] for name in required}
    fixed[CLOCK_FIELD] = generated_at
    return fixed


def contract(answers, config, clock=None, document=None):
    """The built contract, from answers plus the fields no prompt asks for."""
    shaped = prompts.arguments(answers)
    fixed = reproduction(config, clock)
    try:
        return scope_emitter.build(
            subscription_ref=shaped["subscription_ref"],
            in_scope=fixed["inScope"],
            out_of_scope=fixed["outOfScope"],
            observation_period=shaped["observation_period"],
            execution_limits=shaped["execution_limits"],
            generated_at=fixed[CLOCK_FIELD],
            generated_against=fixed["generatedAgainst"],
        )
    except scope_emitter.EmitError as failure:
        raise GuidedError(str(failure))


def run(
    settings=(),
    config=None,
    entries=prompts.REGISTER,
    document=None,
    reader=None,
    writer=None,
    interactive=True,
    clock=None,
):
    """One guided run, in either mode, as a document.

    Both modes reach the same `contract` call with the same shaped arguments,
    which is what makes byte-identity a property of the code rather than a
    coincidence the tests happen to observe.
    """
    if config is None:
        raise GuidedError(
            "a guided run needs a configuration carrying the selection: %s."
            % ", ".join(FROM_CONFIG)
        )
    answers = resolve_answers(
        parse_settings(settings, entries),
        config,
        entries,
        document,
        reader,
        writer,
        interactive,
    )
    return contract(answers, config, clock, document)


def arguments(argv):
    """The parsed command line, refusing anything it does not recognise."""
    parsed = {
        "explain": False,
        "interactive": True,
        "config": None,
        "settings": [],
        "out": None,
    }
    rest = list(argv)
    while rest:
        token = rest.pop(0)
        if token == "--explain":
            parsed["explain"] = True
        elif token == "--non-interactive":
            parsed["interactive"] = False
        elif token in ("--config", "--set", "--out"):
            if not rest:
                raise GuidedError("%s needs a value. %s" % (token, USAGE))
            value = rest.pop(0)
            if token == "--set":
                parsed["settings"].append(value)
            else:
                parsed[token[2:]] = value
        else:
            raise GuidedError("unrecognised argument '%s'. %s" % (token, USAGE))
    return parsed


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    try:
        parsed = arguments(argv)
    except GuidedError as failure:
        print(str(failure))
        return EXIT_REFUSED

    if parsed["explain"]:
        print(USAGE)
        print("")
        print("Settable inputs, one --set key each:")
        for entry in prompts.REGISTER:
            print("  --set %s=<value>" % entry.id)
        print("")
        print("Supplied by the configuration, never asked for:")
        for name in FROM_CONFIG:
            print("  %s  (%s)" % (name, prompts.DERIVED[name]))
        return EXIT_OK

    try:
        config = read_config(parsed["config"]) if parsed["config"] else None
        document = run(
            settings=parsed["settings"],
            config=config,
            interactive=parsed["interactive"],
            clock=utc_now,
        )
        target = scope_emitter.write(document, parsed["out"])
    except GuidedError as failure:
        print(str(failure))
        return EXIT_REFUSED
    except scope_emitter.EmitError as failure:
        print(str(failure))
        return EXIT_REFUSED

    print("wrote %s" % target)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

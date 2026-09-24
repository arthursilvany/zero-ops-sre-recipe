"""Offline validation of framework configuration artifacts.

Two layers run here, and the split is deliberate.

Structural validation is delegated to a JSON Schema implementation. Re-authoring
one would mean re-solving a solved problem, and a subtly wrong validator is
worse than no validator: it reports success it has not established.

Semantic validation covers the constraints JSON Schema cannot express, because
they relate two values rather than constrain one (FR-28). An observation window
that ends before it starts, or a reference naming an entry that does not exist,
is structurally well-formed and operationally broken. Leaving those to deploy
time would move the failure to the point where it costs the most.

Every failure names the artifact path and the JSON pointer to the offending
location, and reports the shape of what was wrong, never the supplied value
(FR-27, SEC-017): error text is pasted into issues and chat transcripts, so a
message that echoes a value would exfiltrate it through the diagnostic channel.
"""

import argparse
import json
import os
import re
import sys

# JSON Schema treats "format" as an annotation by default, so a malformed
# timestamp would pass structural validation. The semantic comparison below
# relies on UTC RFC 3339 strings ordering lexically, so the shape is asserted
# here rather than assumed.
UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2

SCHEMA_FILENAME = "framework-config.schema.json"
CONFIG_FILENAME = "framework-config.json"


class ValidationError(Exception):
    """A configuration artifact was rejected, or could not be checked."""


class Finding(object):
    """One rejection: where it is, and what is wrong with it."""

    def __init__(self, pointer, message):
        self.pointer = pointer or "/"
        self.message = message

    def render(self, artifact):
        return "%s#%s: %s" % (artifact, self.pointer, self.message)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def default_schema_path():
    return os.path.join(repo_root(), "contracts", "schemas", SCHEMA_FILENAME)


def load_json(path, what):
    if not os.path.isfile(path):
        raise ValidationError("%s not found: %s" % (what, path))
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except ValueError as exc:
        # The parser reports line and column, which locates the fault without
        # reproducing the content at it.
        raise ValidationError("%s is not valid JSON: %s (%s)" % (what, path, exc))


def pointer_of(parts):
    out = []
    for part in parts:
        token = str(part).replace("~", "~0").replace("/", "~1")
        out.append(token)
    return "/" + "/".join(out) if out else ""


def structural_findings(instance, schema):
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        raise ValidationError(
            "jsonschema is not installed. Install the tooling package first:\n"
            "    python -m pip install -e tools\n"
            "Refusing to report success without having validated anything."
        )

    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    findings = []
    for error in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path)):
        pointer = pointer_of(list(error.absolute_path))
        keyword = error.validator
        if keyword == "additionalProperties":
            # Name the unknown property so the author can find it; a typo is the
            # common cause and an unnamed rejection is unactionable (FR-27).
            message = "unknown property rejected: %s" % error.message
        elif keyword == "required":
            message = error.message
        else:
            # Other keywords can quote the failing value. Report the constraint
            # instead, so a locator or identifier never lands in a log.
            message = "does not satisfy '%s' constraint of the schema" % keyword
        findings.append(Finding(pointer, message))
    return findings


def _names(items, key="name"):
    return [item.get(key) for item in items if isinstance(item, dict)]


def _check_period(period, pointer, findings):
    if not isinstance(period, dict):
        return
    start = period.get("start")
    end = period.get("end")

    malformed = False
    for key in ("start", "end"):
        value = period.get(key)
        if isinstance(value, str) and not UTC_TIMESTAMP.match(value):
            malformed = True
            findings.append(
                Finding(
                    "%s/%s" % (pointer, key),
                    "is not a UTC RFC 3339 timestamp of the form YYYY-MM-DDThh:mm:ssZ",
                )
            )
    if malformed:
        # Comparing an unparseable timestamp would report a second, misleading
        # fault on top of the real one.
        return

    if isinstance(start, str) and isinstance(end, str) and end <= start:
        # Both are RFC 3339 UTC strings, so lexical order is chronological order.
        findings.append(
            Finding(pointer, "observation period ends at or before it starts")
        )


def _check_duplicates(names, pointer, label, findings):
    seen = set()
    for index, name in enumerate(names):
        if name in seen:
            findings.append(
                Finding(
                    pointer_of(pointer + [index, "name"]),
                    "duplicate %s name" % label,
                )
            )
        seen.add(name)


def semantic_findings(instance):
    """Constraints that relate two values, which JSON Schema cannot express."""
    findings = []
    if not isinstance(instance, dict):
        return findings

    defaults = instance.get("frameworkDefaults") or {}
    environments = instance.get("environments") or []
    workloads = instance.get("workloads") or []
    references = (instance.get("externalReferences") or {}).get("entries") or []

    if isinstance(defaults, dict):
        _check_period(
            defaults.get("observationPeriod"),
            "/frameworkDefaults/observationPeriod",
            findings,
        )

    if isinstance(environments, list):
        _check_duplicates(_names(environments), ["environments"], "environment", findings)
        for index, environment in enumerate(environments):
            if isinstance(environment, dict):
                _check_period(
                    environment.get("observationPeriod"),
                    pointer_of(["environments", index, "observationPeriod"]),
                    findings,
                )

    if isinstance(workloads, list):
        _check_duplicates(_names(workloads), ["workloads"], "workload", findings)

    if isinstance(references, list):
        _check_duplicates(
            _names(references), ["externalReferences", "entries"], "external reference", findings
        )

    known_references = set(_names(references)) if isinstance(references, list) else set()
    known_environments = set(_names(environments)) if isinstance(environments, list) else set()

    default_environment = defaults.get("defaultEnvironment") if isinstance(defaults, dict) else None
    if default_environment is not None and default_environment not in known_environments:
        findings.append(
            Finding(
                "/frameworkDefaults/defaultEnvironment",
                "names an environment that is not defined in this configuration",
            )
        )

    for pointer, name in _reference_uses(instance):
        if name not in known_references:
            findings.append(
                Finding(pointer, "names an external reference that is not defined")
            )

    if isinstance(workloads, list):
        for index, workload in enumerate(workloads):
            if not isinstance(workload, dict):
                continue
            in_scope = workload.get("inScope") or []
            out_of_scope = workload.get("outOfScope") or []
            for position, entry in enumerate(out_of_scope):
                if entry in in_scope:
                    findings.append(
                        Finding(
                            pointer_of(["workloads", index, "outOfScope", position]),
                            "selector appears in both inScope and outOfScope, "
                            "so the resolved scope is ambiguous",
                        )
                    )

    return findings


def _reference_uses(instance):
    """Yield (pointer, name) for every property that names an external reference."""
    uses = []

    for index, environment in enumerate(instance.get("environments") or []):
        if isinstance(environment, dict) and "subscriptionRef" in environment:
            uses.append(
                (
                    pointer_of(["environments", index, "subscriptionRef"]),
                    environment["subscriptionRef"],
                )
            )

    integrations = instance.get("toolIntegrations") or {}
    if isinstance(integrations, dict):
        for index, connector in enumerate(integrations.get("connectors") or []):
            if not isinstance(connector, dict):
                continue
            for key in ("endpointRef", "credentialRef"):
                if key in connector:
                    uses.append(
                        (
                            pointer_of(["toolIntegrations", "connectors", index, key]),
                            connector[key],
                        )
                    )

    observability = instance.get("observability") or {}
    if isinstance(observability, dict) and "workspaceRef" in observability:
        uses.append(("/observability/workspaceRef", observability["workspaceRef"]))

    approvals = instance.get("approvalPolicies") or {}
    if isinstance(approvals, dict) and "approverGroupRef" in approvals:
        uses.append(("/approvalPolicies/approverGroupRef", approvals["approverGroupRef"]))

    return uses


def resolve_artifact(target):
    """Accept either the configuration file or the directory that holds it."""
    if os.path.isdir(target):
        candidate = os.path.join(target, CONFIG_FILENAME)
        if not os.path.isfile(candidate):
            raise ValidationError(
                "no %s in directory: %s" % (CONFIG_FILENAME, target)
            )
        return candidate
    return target


def validate(target, schema_path=None):
    """Return the findings for one artifact. An empty list means it is valid."""
    artifact = resolve_artifact(target)
    schema = load_json(schema_path or default_schema_path(), "schema")
    instance = load_json(artifact, "configuration")

    findings = structural_findings(instance, schema)
    if findings:
        # Semantic checks assume a well-formed shape. Running them over a
        # structurally invalid document produces noise that buries the real
        # fault, so they are gated rather than merged.
        return artifact, findings
    return artifact, semantic_findings(instance)


def _run_check_core():
    from zeroops import core_paths

    try:
        problems = core_paths.check()
    except core_paths.CoreDeclarationError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return EXIT_USAGE

    if problems:
        sys.stderr.write(
            "Core declaration does not hold: %d problem(s).\n" % len(problems)
        )
        for problem in problems:
            sys.stderr.write("  %s\n" % problem)
        return EXIT_INVALID

    sys.stdout.write("Core declaration holds: %s\n" % core_paths.DECLARATION_PATH)
    return EXIT_OK


def _run_hash(args):
    from zeroops import canonical

    try:
        with open(args.target, "r", encoding="utf-8") as handle:
            document = canonical.load(handle.read())
    except OSError as exc:
        sys.stderr.write("error: cannot read %s: %s\n" % (args.target, exc.strerror))
        return EXIT_USAGE
    except UnicodeDecodeError:
        sys.stderr.write(
            "error: %s is not valid UTF-8. The canonical form is defined over "
            "UTF-8 bytes.\n" % args.target
        )
        return EXIT_USAGE

    try:
        if args.canonical:
            # Written as bytes so the platform's newline translation cannot
            # touch output whose exact byte sequence is the point.
            sys.stdout.buffer.write(canonical.canonicalise(document))
            sys.stdout.buffer.flush()
            return EXIT_OK
        sys.stdout.write("%s\n" % canonical.digest(document, args.hash_field))
        return EXIT_OK
    except canonical.CanonicalisationError as exc:
        sys.stderr.write("%s: %s\n" % (args.target, exc))
        return EXIT_INVALID


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="zeroops",
        description="Validate Zero Ops SRE Agent Recipe artifacts offline.",
    )
    subparsers = parser.add_subparsers(dest="command")

    validate_parser = subparsers.add_parser(
        "validate", help="Validate a framework configuration against its schema."
    )
    validate_parser.add_argument(
        "target",
        help="Path to framework-config.json, or to the directory containing it.",
    )
    validate_parser.add_argument(
        "--schema",
        default=None,
        help="Override the schema path. Defaults to contracts/schemas/%s." % SCHEMA_FILENAME,
    )

    subparsers.add_parser(
        "check-core",
        help="Check the core path declaration against the repository (FR-04, FR-61).",
    )

    hash_parser = subparsers.add_parser(
        "hash",
        help="Print the canonical SHA-256 of a JSON document (FR-23).",
    )
    hash_parser.add_argument("target", help="Path to the JSON document.")
    hash_parser.add_argument(
        "--hash-field",
        default=None,
        help=(
            "Top-level field removed before hashing, so a document can carry its "
            "own digest and still reproduce it."
        ),
    )
    hash_parser.add_argument(
        "--canonical",
        action="store_true",
        help="Print the canonical bytes instead of the digest, for diffing.",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return EXIT_USAGE

    if args.command == "check-core":
        return _run_check_core()

    if args.command == "hash":
        return _run_hash(args)

    try:
        artifact, findings = validate(args.target, args.schema)
    except ValidationError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return EXIT_USAGE

    if findings:
        sys.stderr.write(
            "Configuration rejected: %d finding(s).\n" % len(findings)
        )
        for finding in findings:
            sys.stderr.write("  %s\n" % finding.render(artifact))
        return EXIT_INVALID

    sys.stdout.write("Configuration valid: %s\n" % artifact)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

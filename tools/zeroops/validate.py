"""Offline validation of framework configuration artifacts.

Three layers run here, in order, and the ordering is the design.

Structural validation is delegated to a JSON Schema implementation. Re-authoring
one would mean re-solving a solved problem, and a subtly wrong validator is
worse than no validator: it reports success it has not established.

Semantic validation covers the constraints JSON Schema cannot express, because
they relate two values rather than constrain one (FR-28). An observation window
that ends before it starts, or a reference naming an entry that does not exist,
is structurally well-formed and operationally broken. Leaving those to deploy
time would move the failure to the point where it costs the most. Semantic
checks are gated behind structural success rather than merged with it, because
running them over a malformed shape produces noise that buries the real fault.

Recommended-area warnings are the third layer (FR-01, CON-11). They report what
a production deployment will want and a first result does not need. A warning
never changes the exit code unless the caller passes --strict, so the quick win
stays reachable while the gap stays visible. See obligations.py.

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

from zeroops import failure_modes
from zeroops import obligations
from zeroops import references

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
SCHEMA_SUFFIX = ".schema.json"


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


def schema_directory():
    return os.path.join(repo_root(), "contracts", "schemas")


def known_kinds():
    """Every artifact kind the register makes validatable, from the files."""
    directory = schema_directory()
    if not os.path.isdir(directory):
        return []
    return sorted(
        name[: -len(SCHEMA_SUFFIX)]
        for name in os.listdir(directory)
        if name.endswith(SCHEMA_SUFFIX)
    )


def kind_of(path):
    """The artifact kind an instance filename declares.

    The part before the first dot, so that a set can hold more than one
    instance of a kind: environment-binding.production.json and
    environment-binding.nonproduction.json are both environment bindings.
    Dispatching on the filename rather than on a field inside the document is
    deliberate. A document that names its own schema can lie about which one
    it is, and the cheapest way to pass validation would be to claim a laxer
    kind.
    """
    return os.path.basename(path).split(".")[0]


def schema_path_for(kind):
    candidate = os.path.join(schema_directory(), kind + SCHEMA_SUFFIX)
    if not os.path.isfile(candidate):
        raise ValidationError(
            "no schema for artifact kind '%s'. Known kinds: %s.\n"
            "The kind is taken from the filename before the first dot."
            % (kind, ", ".join(known_kinds()))
        )
    return candidate


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


SHAPE_KEYWORDS = (
    "pattern",
    "format",
    "enum",
    "const",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "minItems",
    "maxItems",
    "type",
)


def expected_shape_hint(keyword, value):
    """State the shape the schema asked for, using schema content only.

    Naming the keyword alone tells an author that something called 'pattern'
    was not satisfied, which is a fact about JSON Schema rather than about
    their document. The constraint itself is what makes the message
    actionable.

    Restricted to an allow-list of keywords whose value is a literal the
    schema author wrote. Composition keywords such as allOf carry whole
    subschemas, and printing one would dump the schema into a diagnostic that
    gets pasted into an issue.

    A schema value is never instance content, so this cannot echo a supplied
    value (SEC-017).
    """
    if keyword not in SHAPE_KEYWORDS:
        return ""
    if isinstance(value, (list, tuple)):
        rendered = ", ".join(str(item) for item in value)
    else:
        rendered = str(value)
    if not rendered:
        return ""
    return ". Expected %s: %s" % (keyword, rendered)


def allowed_properties_hint(subschema):
    """Name the properties the failing subschema accepts, or say nothing.

    An empty string rather than a placeholder when the set is unavailable:
    a schema that composes with allOf or $ref may not carry `properties` at
    the level the error was raised, and "allowed: (unknown)" would read as a
    statement about the schema instead of about this function's reach.

    Property names are schema content, never instance content, so this cannot
    echo a supplied value (SEC-017).
    """
    if not isinstance(subschema, dict):
        return ""
    properties = subschema.get("properties")
    if not isinstance(properties, dict) or not properties:
        return ""
    return ". Allowed here: %s" % ", ".join(sorted(properties))


def structural_findings(instance, schema):
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        raise ValidationError(
            "jsonschema is not installed. Install the pinned closure:\n"
            "    python -m pip install --require-hashes --only-binary=:all: "
            "-r tools/requirements.lock\n"
            "Both flags are part of the control: --require-hashes refuses "
            "anything not listed, and --only-binary refuses a source "
            "distribution, which would run a build at install time.\n"
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
            # Name the accepted set too: the usual cause is a misspelling, and
            # knowing the property is wrong without knowing what was expected
            # leaves the author guessing at the schema.
            message = "unknown property rejected: %s%s" % (
                error.message,
                allowed_properties_hint(error.schema),
            )
        elif keyword == "required":
            message = error.message
        else:
            # Other keywords can quote the failing value. Report the constraint
            # instead, so a locator or identifier never lands in a log.
            message = "does not satisfy '%s' constraint of the schema%s" % (
                keyword,
                expected_shape_hint(keyword, error.validator_value),
            )
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


def _scope_contract_semantics(instance):
    findings = []
    _check_period(
        instance.get("observationPeriod"), "/observationPeriod", findings
    )
    in_scope = instance.get("inScope") or []
    out_of_scope = instance.get("outOfScope") or []
    if isinstance(in_scope, list) and isinstance(out_of_scope, list):
        for position, entry in enumerate(out_of_scope):
            if entry in in_scope:
                findings.append(
                    Finding(
                        pointer_of(["outOfScope", position]),
                        "selector appears in both inScope and outOfScope, "
                        "so the resolved scope is ambiguous",
                    )
                )
    return findings


def _check_ordering(instance, earlier, later, findings):
    """Two timestamps that must not run backwards."""
    first = instance.get(earlier)
    second = instance.get(later)
    malformed = False
    for key in (earlier, later):
        value = instance.get(key)
        if isinstance(value, str) and not UTC_TIMESTAMP.match(value):
            malformed = True
            findings.append(
                Finding(
                    "/" + key,
                    "is not a UTC RFC 3339 timestamp of the form "
                    "YYYY-MM-DDThh:mm:ssZ",
                )
            )
    if malformed:
        return
    if isinstance(first, str) and isinstance(second, str) and second < first:
        findings.append(
            Finding(
                "/" + later,
                "is earlier than %s, so the execution would have finished "
                "before it began" % earlier,
            )
        )


def _evidence_manifest_semantics(instance):
    findings = []
    _check_ordering(instance, "startedAt", "completedAt", findings)
    return findings


def _handoff_record_semantics(instance):
    findings = []
    turn = instance.get("turn")
    max_turns = instance.get("maxTurns")
    if isinstance(turn, int) and isinstance(max_turns, int) and turn > max_turns:
        findings.append(
            Finding(
                "/turn",
                "exceeds maxTurns, so the handoff records an execution that "
                "has already passed the bound meant to stop it",
            )
        )

    attempt = instance.get("attempt")
    max_attempts = instance.get("maxAttempts")
    if (
        isinstance(attempt, int)
        and isinstance(max_attempts, int)
        and attempt > max_attempts
    ):
        findings.append(
            Finding(
                "/attempt",
                "exceeds maxAttempts, so the handoff records a retry the "
                "declared ceiling should have prevented",
            )
        )

    reason = instance.get("terminationReason")
    state = instance.get("executionState")
    if isinstance(reason, str):
        expected = failure_modes.state_for(reason)
        if expected is None:
            findings.append(
                Finding(
                    "/terminationReason",
                    "names no failure class the contract defines, so no "
                    "execution state can be derived from it",
                )
            )
        elif isinstance(state, str) and state != expected:
            findings.append(
                Finding(
                    "/executionState",
                    "does not match the state its terminationReason produces, "
                    "so the record disagrees with itself about what happened",
                )
            )
        if (
            isinstance(attempt, int)
            and attempt > 1
            and not failure_modes.retryable(reason)
        ):
            findings.append(
                Finding(
                    "/attempt",
                    "records a retry of a termination reason the contract "
                    "declares unretryable, which spends a budget that a "
                    "transient failure would have needed",
                )
            )

    started_at = instance.get("startedAt")
    completed_at = instance.get("completedAt")
    malformed = False
    for pointer, value in (("/startedAt", started_at), ("/completedAt", completed_at)):
        if isinstance(value, str) and not UTC_TIMESTAMP.match(value):
            malformed = True
            findings.append(
                Finding(
                    pointer,
                    "is not a UTC RFC 3339 timestamp, so no ordering can be "
                    "established from it",
                )
            )
    if (
        not malformed
        and isinstance(started_at, str)
        and isinstance(completed_at, str)
        and completed_at < started_at
    ):
        findings.append(
            Finding(
                "/completedAt",
                "precedes startedAt, so the record describes an execution "
                "that finished before it began",
            )
        )

    return findings


SEMANTIC_RULES = {
    "framework-config": semantic_findings,
    "scope-contract": _scope_contract_semantics,
    "evidence-manifest": _evidence_manifest_semantics,
    "handoff-record": _handoff_record_semantics,
}


def semantic_findings_for(kind, instance):
    """Semantic checks for one artifact kind.

    A kind with no entry here is structurally checked only. That is reported by
    the absence of a rule rather than hidden: a test asserts every kind whose
    schema carries a relational constraint has a rule, so a kind is never
    silently downgraded to structure-only by someone forgetting to add one.
    """
    rule = SEMANTIC_RULES.get(kind)
    if rule is None or not isinstance(instance, dict):
        return []
    return rule(instance)


def _reference_uses(instance):
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


def resolve_artifacts(target):
    """Every artifact a target names, in a stable order.

    A directory is a configuration set, not a single file. Validating only
    framework-config.json inside it would report success for a set whose other
    members were never looked at, which is the failure mode this whole tool
    exists to prevent.
    """
    if not os.path.isdir(target):
        if not os.path.isfile(target):
            raise ValidationError("artifact not found: %s" % target)
        return [target]

    kinds = set(known_kinds())
    found = sorted(
        os.path.join(target, name)
        for name in os.listdir(target)
        if name.endswith(".json") and kind_of(name) in kinds
    )
    if not found:
        raise ValidationError(
            "no recognised artifact in directory: %s.\n"
            "An artifact is named <kind>.json or <kind>.<label>.json, where "
            "kind is one of: %s." % (target, ", ".join(sorted(kinds)))
        )
    return found


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


def pinned_version(schema):
    """The version a schema declares itself to be, or None.

    Read from wherever the schema keeps its schemaVersion definition, because
    two shapes are in use: most schemas define it under $defs and reference it,
    one carries it inline under properties. Looking in both is cheaper than a
    convention nothing enforces, and returning None rather than raising keeps
    this usable against a schema written before the pin existed.
    """
    for container in (schema.get("$defs"), schema.get("properties")):
        if isinstance(container, dict):
            definition = container.get("schemaVersion")
            if isinstance(definition, dict) and "const" in definition:
                return definition["const"]
    return None


def version_findings(instance, schema):
    """Refuse a document written against a different version of the schema.

    Structural findings from a version mismatch are noise: they describe a
    contract the document was never written against, so every one of them is
    true and none of them is the fault. Reporting the mismatch alone, with
    somewhere to look, is the difference between a diagnosis and a list of
    symptoms (FR-27, FR-29).

    The message names the version the schema expects and never the version the
    document declared. The expected value comes from the schema, which is ours;
    the declared value came from the document, and FR-27 holds that values out
    of documents do not go into messages.
    """
    if not isinstance(instance, dict):
        return []
    expected = pinned_version(schema)
    declared = instance.get("schemaVersion")
    if expected is None or not isinstance(declared, str) or declared == expected:
        return []
    return [
        Finding(
            "/schemaVersion",
            "declares a different version of this schema than the one in this "
            "repository, which is %s. Structural findings are suppressed "
            "because they would describe a contract this document was never "
            "written against. See contracts/schema-register.md for the "
            "migration action recorded for each version." % expected,
        )
    ]


def validate_artifact(artifact, schema_path=None):
    """Version, then structural, then semantic, then Recommended-area warnings."""
    kind = kind_of(artifact)
    path = schema_path or schema_path_for(kind)
    schema = load_json(path, "schema")
    instance = load_json(artifact, "configuration")

    findings = version_findings(instance, schema)
    if findings:
        return findings, []

    findings = structural_findings(instance, schema)
    if findings:
        # Semantic checks and warnings both assume a well-formed shape. Running
        # them over a structurally invalid document produces noise that buries
        # the real fault, so they are gated rather than merged.
        return findings, []

    findings = semantic_findings_for(kind, instance)
    if findings:
        return findings, []
    return [], obligations.warnings_for(kind, instance)


def validate(target, schema_path=None):
    """Return (artifact, findings) for one artifact. Kept for callers that
    validate a single document and do not consume warnings."""
    artifact = resolve_artifact(target)
    findings, _ = validate_artifact(artifact, schema_path)
    return artifact, findings


def validate_set(target, schema_path=None):
    """Return [(artifact, findings, warnings)] for every artifact in a target.

    Per-artifact checks run first, then the set-level reference resolution.
    An artifact that failed structurally is excluded from the set pass: a
    document whose shape is wrong cannot meaningfully define or resolve a name.
    """
    results = []
    loaded = []
    incomplete = False
    for artifact in resolve_artifacts(target):
        kind = kind_of(artifact)
        findings, warnings = validate_artifact(artifact, schema_path)
        if findings:
            incomplete = True
        else:
            loaded.append((artifact, kind, load_json(artifact, "configuration")))
        results.append([artifact, findings, warnings])

    # The set pass is gated on the whole set being well-formed, for the same
    # reason the semantic pass is gated on one document being well-formed. A
    # malformed connector still defines the name its bindings point at, but
    # nothing here can read it, so resolving around it would report every
    # binding as broken and bury the one fault that is real.
    by_artifact = {}
    if not incomplete:
        for artifact, finding in set_findings(loaded):
            by_artifact.setdefault(artifact, []).append(finding)

    for result in results:
        extra = by_artifact.get(result[0])
        if extra:
            result[1] = result[1] + extra
            result[2] = []

    return [tuple(result) for result in results]


def set_findings(loaded):
    """Cross-artifact references, checked once the set is known.

    ``loaded`` is a list of (artifact path, kind, instance). It is passed only
    when every member of the set validated structurally: see validate_set for
    why resolving around a malformed member is worse than not resolving.

    A set with a single artifact is still a set. Checking is not skipped for
    it, because a lone framework configuration naming a tool policy is exactly
    the case where nothing else in the directory can define the name.
    """
    findings = []
    documents = {}
    for _, kind, instance in loaded:
        if isinstance(instance, dict):
            documents.setdefault(kind, []).append(instance)

    for artifact, kind, instance in loaded:
        if not isinstance(instance, dict):
            continue
        for reference in references.for_schema(kind):
            if reference.resolution != references.ACROSS_SET:
                continue
            uses = references.collect(instance, reference.path)
            if not uses:
                continue
            target = reference.target
            known = references.defined_names(documents, target)
            for pointer, value in uses:
                if value in known:
                    continue
                if target.kind not in documents:
                    message = (
                        "names %s that no artifact in this set defines. "
                        "No %s.json is present in the set." % (target.label, target.kind)
                    )
                else:
                    message = "names %s that this set does not define" % target.label
                findings.append((artifact, Finding(pointer, message)))

    return findings


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


def _run_test(args):
    from zeroops import localtest

    if not args.local:
        sys.stderr.write(
            "error: 'zeroops test' requires --local. There is one test mode "
            "today and it is the offline one; naming it keeps a later mode "
            "that does reach a subscription from being run by accident.\n"
        )
        return EXIT_USAGE
    try:
        return localtest.run_local(args.pattern)
    except localtest.LocalTestError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return EXIT_USAGE


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
        help="Override the schema path. Defaults to the schema whose name "
        "matches the artifact kind in contracts/schemas/.",
    )
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Treat Recommended-area warnings as failures. Off by default so a "
            "first result stays reachable without authoring anything bespoke "
            "(CON-11); on in a production readiness gate."
        ),
    )

    subparsers.add_parser(
        "check-core",
        help="Check the core path declaration against the repository (FR-04, FR-61).",
    )

    test_parser = subparsers.add_parser(
        "test",
        help="Run this repository's offline suite with no credentials and no "
        "network (NFR-12).",
    )
    test_parser.add_argument(
        "--local",
        action="store_true",
        help=(
            "Required. Spelled out rather than implied, so that a future "
            "command that does reach a subscription cannot be reached by "
            "typing 'zeroops test' and forgetting which one it is."
        ),
    )
    test_parser.add_argument(
        "--pattern",
        default="test_*.py",
        help="Discovery pattern. Defaults to test_*.py.",
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

    if args.command == "test":
        return _run_test(args)

    if args.command == "hash":
        return _run_hash(args)

    try:
        results = validate_set(args.target, args.schema)
    except ValidationError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return EXIT_USAGE

    rejected = [(a, f) for a, f, _ in results if f]
    warned = [(a, w) for a, _, w in results if w]

    if rejected:
        total = sum(len(f) for _, f in rejected)
        sys.stderr.write("Configuration rejected: %d finding(s).\n" % total)
        for artifact, findings in rejected:
            for finding in findings:
                sys.stderr.write("  %s\n" % finding.render(artifact))
        return EXIT_INVALID

    for artifact, _, _ in results:
        sys.stdout.write("Configuration valid: %s\n" % artifact)
    sys.stdout.flush()

    for artifact, warnings in warned:
        for warning in warnings:
            sys.stderr.write("  warning: %s\n" % warning.render(artifact))

    total = sum(len(w) for _, w in warned)
    if warned and args.strict:
        sys.stderr.write(
            "Rejected under --strict: %d Recommended-area warning(s).\n" % total
        )
        return EXIT_INVALID
    if warned:
        sys.stderr.write(
            "%d Recommended-area warning(s). Valid for a first result; "
            "review before production.\n" % total
        )
    return EXIT_OK

if __name__ == "__main__":
    sys.exit(main())

"""Emitting the scope contract without carrying the inventory into it.

The scope contract is the anchor of the evidence chain (FR-13, FR-14, FR-23),
and it is committed. The discovery result it is built from is a
subscription-wide inventory of real identifiers and real names, and is not
committed. Those two facts sit either side of this module, which is the whole
reason it exists (SEC-007).

## What travels is named, not what is stripped

`SELECTOR_FIELD` maps a selection kind to the single discovery-row field that
becomes its selector. Nothing else from a row reaches a contract, and no code
path here copies a row: every entry is assembled key by key from that one
field plus the kind.

The direction is the control. A denylist of fields to remove would pass the
next column added to the query projection straight into a committed file, and
the failure would be silent, because a contract carrying an extra field still
looks like a contract. Under an allow-list a new column is inert until
somebody decides what it means, and the test that pins this reads the
projection out of `wizard/discovery/query-catalogue.json` rather than from a
list copied into a test, so adding a column without deciding fails.

`tag` is in `OPERATOR_SUPPLIED_KINDS` and has no row field. Tags are not
projected by discovery at all, precisely because a tag is operator-controlled
free text and the likeliest place a secret-shaped value appears. A tag
selector therefore comes from the operator, and is the one selector this
module cannot trace back to something Azure chose.

## Two refusals the schema asks for and cannot make

`subscriptionRef` names an entry in the framework configuration. Its pattern
is `^[a-z][a-z0-9-]{1,62}[a-z0-9]$`, which a subscription identifier beginning
with a letter satisfies: `a1b2c3d4-5e6f-...` is a valid `identifier` as far as
JSON Schema is concerned. So the check that the reference is a reference and
not the thing it exists to avoid naming has to live here.

`generatedAgainst` is documented as an opaque marker and explicitly not a
resource identifier, because the file is committed. `maxLength: 200` does not
express that. A digest is a legitimate opaque marker, so a long hexadecimal
run is allowed here while the identifier shapes that name a tenant are not.

## A secret is refused rather than redacted

CC-020 says no secret may be written into a scope contract. Redacting one
would still be a decision this module is not entitled to make on the
operator's behalf, and a redacted secret is still a secret that was typed
somewhere. So `build` refuses and emits nothing.

The scan finds named secret material: an assignment whose left-hand side is a
word that names a credential, a web token, a private key block, a shared
access signature. It shares its marker vocabulary with `schema_lint`, so the
names a schema may not use and the values a contract may not carry cannot
drift apart. It does not, and cannot, detect a high-entropy value that names
itself nothing. That limit is stated rather than papered over: a check that
claimed to catch every secret would be believed.
"""

import argparse
import json
import os
import re

from . import canonical, validate
from .discovery_output import IDENTIFIER_SHAPES
from .schema_lint import SECRET_MARKERS


KIND = "scope-contract"

SCHEMA_VERSION = "1.0.0"

HASH_FIELD = "canonicalHash"

DEFAULT_FILENAME = KIND + ".json"

SELECTOR_FIELD = {
    "resourceGroup": "resourceGroup",
    "resource": "id",
}

OPERATOR_SUPPLIED_KINDS = ("tag",)

ENTRY_FIELDS = ("kind", "selector")

# Named by shape rather than filtered by exclusion, so that a shape renamed in
# discovery_output fails the test that asserts these resolve, instead of
# quietly disabling the check that used to run here.
REFERENCE_FORBIDDEN = ("guid",)

MARKER_FORBIDDEN = (
    "guid",
    "resource group path segment",
    "electronic mail address",
    "endpoint",
)


def _marker_alternatives(words):
    return "[ _-]?".join(re.escape(word) for word in words)


SHARED_SECRET_MARKERS = tuple(
    _marker_alternatives(words) for words in SECRET_MARKERS
)

# Words that name credential material in a value but never in a property name,
# which is why schema_lint has no use for them. Azure storage and service bus
# connection strings are the reason the list is not empty.
VALUE_SECRET_MARKERS = (
    "account[ _-]?key",
    "shared[ _-]?access[ _-]?key",
    "primary[ _-]?key",
    "secondary[ _-]?key",
    "client[ _-]?secret",
    "sig",
    "pwd",
)

_ASSIGNED_SECRET = re.compile(
    r"(?i)(?:^|[^a-z0-9])(?:%s)[ _-]?\s*[=:]\s*\S"
    % "|".join(SHARED_SECRET_MARKERS + VALUE_SECRET_MARKERS)
)

SECRET_SHAPES = (
    ("named secret assignment", _ASSIGNED_SECRET),
    (
        "web token",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    ),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "shared access signature",
        re.compile(r"(?i)\bsv=[0-9]{4}-[0-9]{2}-[0-9]{2}\b"),
    ),
)


class EmitError(Exception):
    """Nothing was emitted, and the reason is not recoverable here."""


def default_path(directory="."):
    """Where a contract is written, named so the validator can find its schema.

    `validate.kind_of` takes the artifact kind from the filename before the
    first dot. A contract under any other name validates against nothing,
    which would make FR-14 pass by never running.
    """
    return os.path.join(directory, DEFAULT_FILENAME)


def shape_findings(value, names):
    """Which of the named identifier shapes appear in a value."""
    available = dict(IDENTIFIER_SHAPES)
    findings = []
    for name in names:
        pattern = available.get(name)
        if pattern is None:
            raise EmitError(
                "no identifier shape named '%s' is published by "
                "discovery_output. The check that depended on it would "
                "otherwise pass by not running." % name
            )
        if pattern.search(value):
            findings.append(name)
    return findings


def secret_findings(value):
    """Which secret shapes appear in a value (CC-020)."""
    return [name for name, pattern in SECRET_SHAPES if pattern.search(value)]


def selector_for(kind, row):
    """The one field of a discovery row that becomes this kind's selector."""
    if kind in OPERATOR_SUPPLIED_KINDS:
        raise EmitError(
            "'%s' selects by a value no discovery row carries, so a selector "
            "for it cannot be derived from one. Supply it explicitly." % kind
        )
    field = SELECTOR_FIELD.get(kind)
    if field is None:
        raise EmitError(
            "unknown selection kind '%s'. Known kinds: %s."
            % (kind, ", ".join(sorted(SELECTOR_FIELD) + list(OPERATOR_SUPPLIED_KINDS)))
        )
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise EmitError(
            "the discovery row carries no usable '%s', so no selector for "
            "kind '%s' can be built from it." % (field, kind)
        )
    return value


def entry(kind, selector):
    """One scope entry, assembled field by field.

    Never a row with extra keys removed. A contract built by subtraction is
    correct only for as long as the subtracting list is complete.
    """
    if kind not in SELECTOR_FIELD and kind not in OPERATOR_SUPPLIED_KINDS:
        raise EmitError("unknown selection kind '%s'." % kind)
    if not isinstance(selector, str) or not selector:
        raise EmitError("a scope entry needs a selector.")
    found = secret_findings(selector)
    if found:
        raise EmitError(
            "the selector holds what looks like credential material (%s), and "
            "a scope contract is committed (CC-020)." % ", ".join(found)
        )
    return {"kind": kind, "selector": selector}


def select(rows, chosen, kind="resource"):
    """The entries for exactly the chosen rows, and no others (FR-13).

    `chosen` holds resource identifiers taken from the discovery result. One
    that no row carries is refused rather than passed through: a contract that
    accepted an unrecognised identifier would satisfy "contains exactly the
    selected candidates" by containing something never discovered.

    Two rows that resolve to the same selector produce one entry. That is the
    same selection, written once, and `uniqueItems` on the schema rejects the
    alternative.
    """
    known = {}
    for row in rows:
        identifier = row.get("id")
        if isinstance(identifier, str) and identifier:
            known[identifier] = row

    missing = [one for one in chosen if one not in known]
    if missing:
        raise EmitError(
            "selected %d candidate(s) that the discovery result does not "
            "contain, so the selection cannot be what was discovered: %s"
            % (len(missing), ", ".join(sorted(missing)))
        )

    entries = []
    seen = set()
    for one in chosen:
        selector = selector_for(kind, known[one])
        if selector in seen:
            continue
        seen.add(selector)
        entries.append(entry(kind, selector))
    return entries


def _strings(node, pointer="", found=None):
    """Every string in the document, with the pointer that reaches it."""
    if found is None:
        found = []
    if isinstance(node, dict):
        for key in node:
            _strings(node[key], pointer + "/" + str(key), found)
    elif isinstance(node, list):
        for position, item in enumerate(node):
            _strings(item, pointer + "/" + str(position), found)
    elif isinstance(node, str):
        found.append((pointer or "/", node))
    return found


def build(
    subscription_ref,
    in_scope,
    out_of_scope,
    observation_period,
    execution_limits,
    generated_at,
    generated_against,
):
    """A complete, hashed, validated contract, or nothing at all.

    `out_of_scope` has no default. An exclusion list that appeared on its own
    when a caller said nothing would make "declared explicitly and never
    implied by omission" a property of the schema alone. Passing an empty list
    is a statement; omitting the argument is not available.
    """
    if not isinstance(subscription_ref, str) or not subscription_ref:
        raise EmitError("a scope contract needs a subscription reference.")
    found = shape_findings(subscription_ref, REFERENCE_FORBIDDEN)
    if found:
        raise EmitError(
            "subscriptionRef holds what looks like a directory identifier "
            "(%s). It names an entry in the framework configuration, and this "
            "file is committed." % ", ".join(found)
        )

    if not isinstance(generated_against, str) or not generated_against:
        raise EmitError("a scope contract needs a generatedAgainst marker.")
    found = shape_findings(generated_against, MARKER_FORBIDDEN)
    if found:
        raise EmitError(
            "generatedAgainst holds what looks like a resource identifier "
            "(%s). It is an opaque marker, and this file is committed."
            % ", ".join(found)
        )

    document = {
        "schemaVersion": SCHEMA_VERSION,
        "subscriptionRef": subscription_ref,
        "inScope": [entry(one["kind"], one["selector"]) for one in in_scope],
        "outOfScope": [
            entry(one["kind"], one["selector"]) for one in out_of_scope
        ],
        "observationPeriod": {
            "start": observation_period["start"],
            "end": observation_period["end"],
        },
        "executionLimits": {
            "maxToolCalls": execution_limits["maxToolCalls"],
            "maxWallClockSeconds": execution_limits["maxWallClockSeconds"],
            "maxResultSetRows": execution_limits["maxResultSetRows"],
            "perQueryTimeoutSeconds": execution_limits["perQueryTimeoutSeconds"],
        },
        "generatedAt": generated_at,
        "generatedAgainst": generated_against,
    }

    leaks = []
    for pointer, value in _strings(document):
        for name in secret_findings(value):
            leaks.append("%s holds %s" % (pointer, name))
    if leaks:
        raise EmitError(
            "nothing was emitted: a scope contract is committed and must "
            "carry no credential material (CC-020).\n%s" % "\n".join(leaks)
        )

    document[HASH_FIELD] = canonical.digest(document, hash_field=HASH_FIELD)

    findings = _contract_findings(document)
    if findings:
        raise EmitError(
            "the assembled contract does not validate against its own schema, "
            "so it would not be emittable without modification (FR-14).\n%s"
            % "\n".join(finding.render(KIND) for finding in findings)
        )
    return document


def _contract_findings(document):
    schema = validate.load_json(validate.schema_path_for(KIND), "schema")
    findings = validate.version_findings(document, schema)
    if findings:
        return findings
    findings = validate.structural_findings(document, schema)
    if findings:
        return findings
    return validate.semantic_findings_for(KIND, document)


def render(document):
    """The exact bytes of the committed file.

    Keys are sorted and the newline is fixed, so the same inputs produce the
    same bytes on Windows and on Linux. The digest is over the canonical form
    rather than over these bytes, which is what lets the file stay readable
    without making the hash depend on how it was laid out.
    """
    text = json.dumps(
        document, indent=2, ensure_ascii=False, sort_keys=True
    )
    return (text + "\n").encode("utf-8")


def write(document, path=None):
    """Write the contract and return where it went."""
    target = path or default_path()
    if validate.kind_of(target) != KIND:
        raise EmitError(
            "a contract written as '%s' validates against no schema, because "
            "the artifact kind is read from the filename before the first "
            "dot. Name it '%s'." % (os.path.basename(target), DEFAULT_FILENAME)
        )
    directory = os.path.dirname(os.path.abspath(target))
    if not os.path.isdir(directory):
        os.makedirs(directory)
    with open(target, "wb") as handle:
        handle.write(render(document))
    return target


def verify(path):
    """Re-read an emitted contract and check it against its own record.

    Two independent questions. Whether it still validates, which the ordinary
    validator answers. And whether the recorded digest is the digest of what
    is in the file, which nothing else asks: a contract edited after emission
    validates perfectly and no longer describes the approved scope.
    """
    findings, _ = validate.validate_artifact(path)
    if findings:
        return findings

    document = validate.load_json(path, "scope contract")
    recorded = document.get(HASH_FIELD)
    recomputed = canonical.digest(document, hash_field=HASH_FIELD)
    if recorded != recomputed:
        return [
            validate.Finding(
                "/" + HASH_FIELD,
                "records %s but the document canonicalises to %s, so the "
                "contract changed after it was approved (FR-23)"
                % (recorded, recomputed),
            )
        ]
    return []


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m zeroops.scope_emitter",
        description=(
            "Check an emitted scope contract against its schema and against "
            "the canonical hash it records."
        ),
    )
    parser.add_argument("path", help="the scope contract to check")
    args = parser.parse_args(argv)

    try:
        findings = verify(args.path)
    except (EmitError, validate.ValidationError) as exc:
        print(str(exc))
        return 2

    if findings:
        for finding in findings:
            print(finding.render(os.path.basename(args.path)))
        return 1
    print("%s validates and matches the hash it records." % args.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

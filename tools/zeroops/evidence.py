"""NEG-F: an evidence entry has nowhere to put retrieved content.

The threat
----------

FR-55 requires that every evidence entry persist a content hash and a data
classification, never the raw retrieved content. A manifest able to carry a
log line is a manifest able to carry an injected instruction, a credential or
a customer identifier, and it carries them into the one artifact this
framework hashes, stores, diffs and hands on.

This is the second structural half of FR-55. The first, NEG-E, keeps content
out of the instruction region. This one keeps it out of the record.

Why the rule is about shape and not about names
------------------------------------------------

The obvious rule is a vocabulary: refuse a property called `content`, `body`,
`payload`, `log`, `text`. That rule was written, checked against the schemas
this repository actually has, and thrown away.

`contentHash` and `contentDigest` both exist and are the mitigation. So do
`dataClassification`, `queryText`, `maxResultSetRows`, `referenceValue` and
`values`. Thirteen committed property names collide with an ordinary content
vocabulary, and every one of them is correct. A name rule would need seven
exceptions on the day it shipped, and a rule with exceptions is a rule
somebody maintains until they stop.

The shape rule needs none. An evidence entry may declare a property only if
that property's schema admits a closed set of values: an enumeration, a
constant, a hash, a timestamp, a constrained identifier, or a bounded number.
Nothing that admits free text, at any length. `contentHash` passes because it
is a 64-character lowercase hex pattern, which is the point of it.

Two tiers, because they fail for different reasons
---------------------------------------------------

**An evidence entry admits no free text at all.** Not bounded free text,
none. This is the strong rule and it applies to the entry definition, where
retrieved content would land.

**Every string anywhere in the manifest is bounded.** Weaker, and it applies
to the rest of the document, where `conclusion.statement` legitimately holds
a sentence somebody wrote. A sentence somebody wrote is not retrieved content,
but an unbounded one is a place a whole log could go, so it is capped rather
than banned. Today no string in any core schema is unbounded, so this rule
fails closed on anything new rather than on anything committed.

Naming the boundary: a 1000-character statement can hold an instruction. It is
safe here for a reason that belongs to a different check, which is that no
core path can retrieve anything to put in it (NEG-H). The entry, which is the
part fed from observation, has no such field at all.

Fail-closed on renaming
------------------------

The rule names the manifest schema and its entry definition explicitly, and
reports a problem when either is missing. A check that located its subject by
guessing would go quiet the day somebody renamed `evidenceEntry`, and a quiet
check reports the same thing as a clean one.
"""

import json
import os


MANIFEST_SCHEMA = "contracts/schemas/evidence-manifest.schema.json"
ENTRY_DEF = "evidenceEntry"

# What an evidence entry property may be. Each admits a closed set of values,
# which is what makes it unable to carry something that was retrieved.
#
# Numeric bounds are deliberately absent. A number cannot hold text at all, so
# it is closed by its type before any bound is read, and a bound on a string is
# meaningless. Listing them would be listing keywords no input can reach, and a
# branch nothing reaches is a branch nothing tests.
CLOSED_FORMS = ("enum", "const", "pattern")

# Types that cannot hold text at all.
CLOSED_TYPES = ("integer", "number", "boolean")

# An entry must record these two for an observation, which is the positive
# half of FR-55: the hash and the handling class, in place of the content.
ENTRY_MUST_RECORD = ("contentHash", "dataClassification")

MISSING_SCHEMA = (
    "%s is missing. NEG-F cannot assert anything about an evidence entry it "
    "cannot find, and reporting nothing would look exactly like reporting a "
    "clean one."
)
MISSING_DEF = (
    "%s declares no $defs/%s. The entry definition is where retrieved content "
    "would land, so a check that could not find it has stopped asserting "
    "anything."
)
FREE_TEXT = (
    "admits free text. An evidence entry records the hash of what was seen and "
    "never the thing itself, so every property must admit a closed set of "
    "values."
)
UNBOUNDED = (
    "is an unbounded string. A string with no enum, const, pattern or "
    "maxLength is somewhere a whole retrieved document could go."
)
NOT_RECORDED = (
    "is not declared by the evidence entry. FR-55 requires an entry to persist "
    "a content hash and a data classification in place of the content."
)
NOT_CONDITIONAL = (
    "does not make the content hash conditional on the observation state. An "
    "unobserved entry carrying a hash would be a hash of nothing, and a value "
    "that compares, sorts and validates like a real one."
)


def resolve(defs, schema, depth=0):
    """Follow local $defs references so a property is judged by what it is."""
    if depth > 8 or not isinstance(schema, dict):
        return schema if isinstance(schema, dict) else {}
    target = schema.get("$ref")
    if isinstance(target, str) and target.startswith("#/$defs/"):
        return resolve(defs, defs.get(target.split("/")[-1], {}), depth + 1)
    return schema


def admits_free_text(schema):
    """Whether this resolved schema can hold text nobody constrained.

    `oneOf` and `anyOf` are satisfied by a single branch, so a value can take
    the shape of the loosest one and the union is free when any branch is.
    `allOf` is the opposite: every branch applies at once, so one branch that
    closes the value closes it regardless of what the others permit.
    """
    if not isinstance(schema, dict):
        # JSON Schema permits `true` and `false` as whole schemas. `true`
        # admits anything, and a non-dict that is not a schema at all is
        # something this rule cannot read, which is the same answer: open.
        return True
    for keyword in ("oneOf", "anyOf"):
        branches = schema.get(keyword)
        if isinstance(branches, list) and branches:
            return any(admits_free_text(b) for b in branches)
    branches = schema.get("allOf")
    if isinstance(branches, list) and branches:
        return all(admits_free_text(b) for b in branches)
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = [k for k in kind if k != "null"]
        kind = kind[0] if len(kind) == 1 else kind
    if kind in CLOSED_TYPES:
        return False
    if kind == "array":
        return admits_free_text(schema.get("items"))
    if kind == "object":
        return True
    if any(keyword in schema for keyword in CLOSED_FORMS):
        return False
    return True


def unbounded_strings(node, defs, trail=()):
    """Every string property in a document that nothing constrains."""
    found = []
    if isinstance(node, dict):
        for name, sub in (node.get("properties") or {}).items():
            target = resolve(defs, sub)
            if isinstance(target, dict) and target.get("type") == "string":
                bounds = ("enum", "const", "pattern", "maxLength", "format")
                if not any(keyword in target for keyword in bounds):
                    found.append("/" + "/".join(trail + ("properties", name)))
        for keyword, value in node.items():
            found.extend(unbounded_strings(value, defs, trail + (keyword,)))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(unbounded_strings(item, defs, trail + (str(index),)))
    return found


def hash_is_conditional(entry):
    """Whether the entry ties the content hash to the observation state.

    An unobserved entry must carry no hash rather than an empty or zero one,
    because a substituted default validates and compares like a real digest.
    """
    for branch in entry.get("allOf") or []:
        if not isinstance(branch, dict) or "if" not in branch:
            continue
        rendered = json.dumps(branch)
        if "contentHash" in rendered and "observationState" in rendered:
            return True
    return False


def entry_findings(document):
    """Everything wrong with the evidence entry definition."""
    problems = []
    defs = document.get("$defs") or {}
    entry = defs.get(ENTRY_DEF)
    if not isinstance(entry, dict):
        return [MISSING_DEF % (MANIFEST_SCHEMA, ENTRY_DEF)]

    properties = entry.get("properties") or {}
    for name in sorted(properties):
        if admits_free_text(resolve(defs, properties[name])):
            problems.append("$defs/%s/properties/%s %s" % (ENTRY_DEF, name, FREE_TEXT))

    for name in ENTRY_MUST_RECORD:
        if name not in properties:
            problems.append("%r %s" % (name, NOT_RECORDED))

    if "dataClassification" in properties:
        if "dataClassification" not in (entry.get("required") or []):
            problems.append(
                "'dataClassification' is declared but not required. An entry "
                "that may omit it records how the observation may be handled "
                "only when somebody remembers."
            )

    if not hash_is_conditional(entry):
        problems.append("$defs/%s %s" % (ENTRY_DEF, NOT_CONDITIONAL))

    return problems


def scan(root, files, declaration):
    """Return (problems, examined).

    `examined` counts the manifest schema, so a run that stopped finding it
    reports zero rather than reporting nothing and looking clean.
    """
    problems = []
    examined = {"manifests": 0}
    full = os.path.join(root, MANIFEST_SCHEMA.replace("/", os.sep))
    if MANIFEST_SCHEMA not in files or not os.path.exists(full):
        return [MISSING_SCHEMA % MANIFEST_SCHEMA], examined

    try:
        with open(full, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, UnicodeDecodeError, ValueError):
        return [MISSING_SCHEMA % MANIFEST_SCHEMA], examined

    if not isinstance(document, dict):
        # A schema document is an object. Anything else is not the subject
        # this rule was written against, and crashing on it would stop the
        # whole gate rather than report the one thing that is wrong.
        return [MISSING_SCHEMA % MANIFEST_SCHEMA], examined

    examined["manifests"] += 1
    defs = document.get("$defs") or {}
    for location in entry_findings(document):
        problems.append("%s: %s" % (MANIFEST_SCHEMA, location))
    for location in unbounded_strings(document, defs):
        problems.append("%s: %s %s" % (MANIFEST_SCHEMA, location, UNBOUNDED))
    return problems, examined

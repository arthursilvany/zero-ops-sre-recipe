"""NEG-I: no core schema leaves a way in.

The threat
----------

A contract is a promise about what a document may contain. Three ways that
promise leaks:

1.  An open object accepts properties nobody named, so a producer can attach
    anything and every consumer still validates.
2.  A property named for secret material invites somebody to put it there, and
    the first time one is written it is written into an artifact the framework
    hashes, stores and hands on (SEC-013, FR-49).
3.  A free-form field accepts arbitrary structure, which is an open object
    under a different spelling and is also where instruction-shaped text would
    land.

The third rule is the third leg of NEG-E's containment argument. That check
enforces that no core path *has* an instruction region, and names as its own
boundary the case it cannot see: instruction-shaped text pasted into a JSON
value under an innocuous key. A field that cannot hold arbitrary structure is
what closes it.

Closure is required where a shape is defined, not everywhere
-------------------------------------------------------------

`additionalProperties: false` is required of a schema that *defines the shape*
of an object: a document root, a `$defs` entry, a named property, an array
item. It is not required of a schema sitting under `if`, `then`, `else`,
`not`, `allOf`, `anyOf` or `oneOf`.

That exemption is evidence, not taste. Every open object in this repository
today, all fifteen of them, is an `if` or a `then`. `additionalProperties` is
an annotation over the properties its own subschema names, so a closed `if`
rejects every instance carrying the properties its sibling `then` describes,
and the branch never fires. Requiring closure there would not harden the
contract. It would break it, and it would break it silently, because a
conditional that never matches validates everything.

The exemption leaves a hole and the hole is closed from outside. A root whose
properties all live under `allOf` branches would have nothing to close. So the
requirement lands on the outer shape-defining schema whenever *it or any of
its combinator branches* names properties. The branch stays open; the schema
that owns it does not.

Why `key` is not a secret word and `credentialRef` is not a finding
--------------------------------------------------------------------

The vocabulary was checked against the 180 distinct property names these
schemas actually declare, before it was written down.

`key` was rejected. It matches `idempotencyKey`, which is not secret material
and is the mechanism that makes a retried write safe. `key` also names
dictionary keys and partition keys, so a rule carrying it would be a rule that
needs exceptions, and a rule with exceptions is a rule somebody maintains. The
compound forms `api key` and `private key` are kept, because those do name
secret material and neither collides with anything.

`credential` is kept, and `credentialRef` passes, because a name ending in
`ref` denotes a locator resolved elsewhere and never the material itself. That
is the established convention across these contracts, which is why they also
carry `endpointRef`, `environmentRef`, `workloadRef`, `queryRef` and
`sourceRef`. A rule that flagged `credentialRef` would be flagging the
mitigation, exactly as a rule carrying `content` would have flagged the
`contentHash` that keeps retrieved content out of the evidence manifest.

What this does not claim
-------------------------

The free-form rule is about *structure*. A `type: "string"` property can still
hold a paragraph, and several deliberately do: `description`, `rationale`,
`justification`, `summary`. This check does not pretend otherwise.

Prose fields are safe here for a different reason, and it belongs to a
different check: no core path can retrieve anything, so there is nothing
untrusted in scope to write into one. That is NEG-H's first rule. Saying so
plainly is better than a rule that bans `description` and gets an exception on
its first use.
"""

import json
import os

from .instructions import words_of


# Keywords whose subschemas constrain rather than define a shape. A schema
# under one of these describes when a rule applies, not what a document is.
APPLICATORS = ("if", "then", "else", "not", "allOf", "anyOf", "oneOf")

# Keywords that introduce a schema defining the shape of some value.
COMBINATORS = ("allOf", "anyOf", "oneOf")

# Word sequences that name secret material. Checked as consecutive words, so
# apiKey and api_key trip `api key` while idempotencyKey trips nothing.
SECRET_MARKERS = (
    ("secret",),
    ("secrets",),
    ("password",),
    ("passwd",),
    ("token",),
    ("credential",),
    ("credentials",),
    ("api", "key"),
    ("private", "key"),
    ("connection", "string"),
    ("certificate",),
    ("thumbprint",),
    ("bearer",),
    ("pfx",),
    ("pem",),
    ("sas",),
)

# A name ending in one of these denotes a locator, never the material. See the
# module docstring: credentialRef is the mitigation, not the finding.
REFERENCE_SUFFIXES = ("ref", "refs")

# What makes a property schema constrained. A schema carrying none of these
# admits anything.
CONSTRAINING_KEYWORDS = (
    "type",
    "$ref",
    "enum",
    "const",
    "allOf",
    "anyOf",
    "oneOf",
)

CLOSED = "must declare additionalProperties: false; an open object accepts properties nobody named."
SECRET = "names secret material; contracts carry a reference to a secret, never the secret."
BAG = "is an untyped object; a field that accepts arbitrary structure is an open object under another name."
OPEN_MAP = "declares additionalProperties as a schema, which admits keys the contract never names."
OPEN_TRUE = "declares additionalProperties: true."
LOOSE_ARRAY = "is an array with no declared items, so it admits elements of any shape."
UNCONSTRAINED = "declares no type, $ref, enum, const or combinator, so it admits any value."
UNION_OBJECT = "declares a union type including object, which is a catch-all branch."


def is_schema_document(document):
    """A JSON Schema, as opposed to an instance document it governs."""
    return isinstance(document, dict) and "$schema" in document


def secret_marker(name):
    """The secret marker this property name trips, or None."""
    words = words_of(name)
    if words and words[-1] in REFERENCE_SUFFIXES:
        return None
    for marker in SECRET_MARKERS:
        span = len(marker)
        for start in range(len(words) - span + 1):
            if tuple(words[start:start + span]) == marker:
                return " ".join(marker)
    return None


def mentions_properties(node):
    """Whether this schema, or a branch it composes, names properties.

    Used to decide whether a shape-defining schema has anything to close. A
    root whose properties all live under allOf branches still owns them.
    """
    if not isinstance(node, dict):
        return False
    if "properties" in node:
        return True
    for keyword in COMBINATORS:
        branches = node.get(keyword)
        if isinstance(branches, list):
            for branch in branches:
                if mentions_properties(branch):
                    return True
        elif mentions_properties(branches):
            return True
    return False


def free_form_reason(schema):
    """Why this property schema admits arbitrary values, or None."""
    if not isinstance(schema, dict):
        return None
    if schema.get("additionalProperties") is True:
        return OPEN_TRUE
    if isinstance(schema.get("additionalProperties"), dict):
        return OPEN_MAP
    kind = schema.get("type")
    if isinstance(kind, list):
        if "object" in kind:
            return UNION_OBJECT
        return None
    if kind == "object" and "properties" not in schema and "$ref" not in schema:
        return BAG
    if kind == "array" and not ({"items", "prefixItems", "$ref"} & set(schema)):
        return LOOSE_ARRAY
    if not ({k for k in CONSTRAINING_KEYWORDS} & set(schema)):
        return UNCONSTRAINED
    return None


def shape_findings(node, trail=(), inside_applicator=False):
    """Closure and free-form findings for one schema document."""
    found = []
    if isinstance(node, dict):
        if not inside_applicator and mentions_properties(node):
            if node.get("additionalProperties") is not False:
                found.append(("/" + "/".join(trail), CLOSED))
        for name, sub in (node.get("properties") or {}).items():
            reason = free_form_reason(sub)
            if reason:
                found.append(("/" + "/".join(trail + ("properties", name)), reason))
        for keyword, value in node.items():
            found.extend(
                shape_findings(
                    value,
                    trail + (keyword,),
                    inside_applicator or keyword in APPLICATORS,
                )
            )
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(shape_findings(item, trail + (str(index),), inside_applicator))
    return found


def declared_property_names(node, trail=()):
    """Every property name a schema declares, with its location."""
    found = []
    if isinstance(node, dict):
        for name in (node.get("properties") or {}):
            found.append((name, "/" + "/".join(trail + ("properties", name))))
        for keyword, value in node.items():
            found.extend(declared_property_names(value, trail + (keyword,)))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(declared_property_names(item, trail + (str(index),)))
    return found


def instance_keys(node, trail=()):
    """Every object key in an instance document, with its location."""
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append((key, "/" + "/".join(trail + (key,))))
            found.extend(instance_keys(value, trail + (key,)))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(instance_keys(item, trail + (str(index),)))
    return found


def scan(root, files, declaration):
    """Return (problems, examined).

    `examined` counts schemas and instances apart. The closure and free-form
    rules only apply to schemas, so a run that stopped recognising schemas
    would report nothing and look exactly like a clean repository.
    """
    from .instructions import scanned_paths

    problems = []
    examined = {"schemas": 0, "instances": 0}
    for path in scanned_paths(files, declaration):
        if not path.lower().endswith(".json"):
            continue
        full = os.path.join(root, path.replace("/", os.sep))
        try:
            with open(full, "r", encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, UnicodeDecodeError, ValueError):
            continue

        if is_schema_document(document):
            examined["schemas"] += 1
            for location, reason in shape_findings(document):
                problems.append("%s: %s %s" % (path, location, reason))
            for name, location in declared_property_names(document):
                marker = secret_marker(name)
                if marker:
                    problems.append(
                        "%s: %s property %r %s (%s)"
                        % (path, location, name, SECRET, marker)
                    )
        else:
            examined["instances"] += 1
            for key, location in instance_keys(document):
                marker = secret_marker(key)
                if marker:
                    problems.append(
                        "%s: %s key %r %s (%s)" % (path, location, key, SECRET, marker)
                    )
    return problems, examined

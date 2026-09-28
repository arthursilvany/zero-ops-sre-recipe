#!/usr/bin/env python3
"""NEG-D: an emitted agent binding must carry an explicit tool list.

What this guards against
------------------------

A runtime handed no tool list does not run with no tools. It runs with whatever
its global default is, and that default includes write tools. So the failure
this check exists to catch is silent by construction: the binding deploys, the
agent works, and the only visible difference is that it can now do more than
anybody declared.

Why the check lives here and not in a schema
--------------------------------------------

`agent-definition.schema.json` already requires `capabilities`, so a *definition*
without a capability list cannot validate. That is a different artifact. The
definition is runtime-agnostic and names capability classes; the binding is the
runtime-shaped document emitted from it, and the list can be lost between them
without either artifact becoming invalid.

The emitted binding has no schema in this repository, deliberately: FR-04
confines runtime-specific names to the binding layer, so no contract under
`contracts/` may name the properties of a runtime's own file. That leaves the
check with a problem it cannot solve by guessing. Searching an arbitrary
document for something that looks like a tool list is the same mistake the
call-site check refused to make with runtime-assembled commands: a check that
infers its own subject cannot distinguish "the list is absent" from "the list is
somewhere I did not look".

So the binding layer says where the list is, through the capability mapping's
`toolListPointer`, and this module reads that location and nothing else. The
contract states that such a location exists and constrains its shape; the value
is supplied under `core/binding/`, which is the one place runtime-shaped
knowledge is allowed to live.

Why an empty list is refused
----------------------------

`capabilities: []` is valid in an agent *definition*, where it is an author
saying "this agent gets nothing". In an emitted *binding* the same empty array
means something the framework cannot distinguish: either the author's intent, or
an emitter that lost the list. It then crosses into a runtime whose behaviour on
an empty collection nobody here has verified (SEC-011, FR-74), and a serializer
that omits empty collections turns it into an absent property, which is exactly
the state NEG-D exists to prevent.

An operator who genuinely wants an agent with no tools has asked for an agent
that can answer nothing. That is a request worth failing on rather than
satisfying quietly.

Why nothing calls this from a gate yet
--------------------------------------

There is no emitted binding in this repository to scan. Bindings are produced at
deployment time, which is User Story 5. Wiring a gate now would scan an empty
set, and a scan of nothing reports nothing and is indistinguishable from a clean
result. The deployment path calls this instead, and until then the negative
suite is where it is exercised.
"""

from __future__ import annotations

import json
import os

POINTER_PROPERTY = "toolListPointer"

BINDING_DIRECTORY = "core/binding"

BINDING_SEGMENTS = BINDING_DIRECTORY.split("/")

NO_MAPPING = (
    "no capability mapping was found under %s, so nothing declares where an "
    "emitted binding carries its tool list" % BINDING_DIRECTORY
)

NO_POINTER = (
    "the capability mapping declares no %s, so the binding layer does not say "
    "where an emitted binding carries its tool list" % POINTER_PROPERTY
)

ABSENT = "the emitted binding has nothing at %s, so it carries no tool list"

NOT_A_LIST = "the emitted binding holds %s at %s, which is not a list of tools"

EMPTY = (
    "the emitted binding holds an empty list at %s; an empty list and an absent "
    "one are the same thing to a runtime whose defaulting behaviour is unverified"
)

MALFORMED = (
    "the capability mapping gives %s as the tool-list location, which is not a "
    "JSON Pointer and cannot address anything"
)


def unescape(token):
    """Reverse RFC 6901 escaping. ~1 is a slash and ~0 is a tilde.

    The order matters: unescaping ~0 first would turn ~01 into ~1 and then into
    a slash, which is not what the pointer said.
    """
    return token.replace("~1", "/").replace("~0", "~")


def resolve(document, pointer):
    """Resolve an RFC 6901 pointer. Returns (found, value).

    A separate found flag rather than a sentinel, because a binding is allowed
    to hold null at the pointer and that is a different fault from holding
    nothing: one is a value the emitter wrote, the other is a property it never
    produced.

    The pointer is assumed well formed; the caller checks that separately, so
    that a malformed location and an absent property do not share a message.
    """
    current = document
    for token in pointer.split("/")[1:]:
        key = unescape(token)
        if isinstance(current, dict):
            if key not in current:
                return False, None
            current = current[key]
        elif isinstance(current, list):
            if not key.isdigit():
                return False, None
            index = int(key)
            if index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def describe(value):
    """Name the kind of thing found, never the thing itself.

    An emitted binding is a customer artifact. Echoing its contents into a
    failure message is what NEG-K forbids, and a message that says "an object"
    is as useful for fixing the fault as one that quotes it.

    Exhaustive over the five JSON kinds that are not arrays, which is every kind
    that can reach it: the caller has already established that the value is not
    a list. A branch for arrays would be a branch no input could take.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, dict):
        return "an object"
    if isinstance(value, str):
        return "a string"
    return "a number"


def load_mapping(root):
    """Return the capability mapping declared by the binding layer, or None.

    None means the binding layer has not been materialised, which is the state
    this repository is in until T2.04 lands. That is a refusal, not an
    exemption.
    """
    directory = os.path.join(root, *BINDING_SEGMENTS)
    if not os.path.isdir(directory):
        return None
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
        if isinstance(document, dict) and "entries" in document and "runtimeName" in document:
            return document
    return None


def tool_list_findings(emitted, mapping):
    """Every reason this emitted binding fails NEG-D.

    Each reason gets its own message. Two faults that read the same send the
    reader looking for one fault, and the call-site check already shipped that
    mistake once: a command with no verb and a command with a forbidden verb
    produced identical text until a mutant proved no test could tell them apart.
    """
    if mapping is None:
        return [NO_MAPPING]
    pointer = mapping.get(POINTER_PROPERTY)
    if not pointer:
        return [NO_POINTER]
    if not pointer.startswith("/"):
        return [MALFORMED % pointer]

    found, value = resolve(emitted, pointer)
    if not found:
        return [ABSENT % pointer]
    if not isinstance(value, list):
        return [NOT_A_LIST % (describe(value), pointer)]
    if not value:
        return [EMPTY % pointer]
    return []

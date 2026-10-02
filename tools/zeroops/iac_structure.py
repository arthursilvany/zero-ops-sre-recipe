"""Structural Infrastructure as Code checks (T5.02, ADR-0002, CON-12).

Three things must never be tracked in this repository, and each is decided from
the file itself rather than from a convention:

1.  A Terraform artifact. Terraform is reachable only through upstream entry
    points (CON-12), so any Terraform source, variable, state, plan or lock file
    here is implementation work this repository does not own.
2.  An ARM JSON deployment template or parameter file. ARM JSON is a compiled
    output and a compatibility surface, never an authored input (ADR-0002).
    Compiled output is produced at build time and is not committed, so a tracked
    one is indistinguishable from a hand-authored one and is refused either way.
3.  A Bicep declaration that re-authors a resource type the pinned upstream
    already creates. The composition consumes upstream modules; it does not
    write its own copy of what they provide (ADR-0001, ADR-0002). An `existing`
    reference creates nothing and is allowed.

The list of upstream-created types is a measurement of the pinned tree, stored
in ``deploy/upstream-resource-types.json`` and tied to the commit in
``deploy/upstream.lock``. Raising the pin without re-measuring fails the check.

Anything that cannot be decided offline fails closed: an unparseable JSON file,
a Bicep declaration whose type is not a literal, or a child resource whose
parent cannot be resolved.

This module reads files only. It starts no process and opens no socket.
"""

import argparse
import json
import os
import re
import sys
from collections import namedtuple

UPSTREAM_TYPES_PATH = os.path.join("deploy", "upstream-resource-types.json")
UPSTREAM_LOCK_PATH = os.path.join("deploy", "upstream.lock")

Finding = namedtuple("Finding", "path message")

_TERRAFORM_SUFFIXES = (
    ".tf",
    ".tf.json",
    ".tfvars",
    ".tfvars.json",
    ".tfstate",
    ".tfstate.backup",
    ".tfplan",
    ".terraform.lock.hcl",
)
_TERRAFORM_NAMES = ("terragrunt.hcl",)
_TERRAFORM_DIRECTORIES = ("terraform", ".terraform")

_ARM_SCHEMA = re.compile(r"deploymentTemplate|deploymentParameters", re.IGNORECASE)
_FULL_TYPE = re.compile(r"^[A-Za-z0-9]+(\.[A-Za-z0-9]+)+(/[A-Za-z0-9]+)+$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
# Keywords that introduce a name. After one of them, `resource` is the name
# being declared, as in `output resource string`, not a resource declaration.
_NAMING_KEYWORDS = ("output", "param", "var", "type", "func", "metadata")


# --------------------------------------------------------------------------- #
# Terraform and ARM JSON
# --------------------------------------------------------------------------- #


def terraform_finding(path):
    lowered = path.replace("\\", "/").lower()
    segments = lowered.split("/")
    if any(segment in _TERRAFORM_DIRECTORIES for segment in segments[:-1]):
        return Finding(path, "a Terraform directory is tracked. CON-12 reserves "
                             "Terraform to upstream entry points.")
    name = segments[-1]
    if name in _TERRAFORM_NAMES or name.endswith(_TERRAFORM_SUFFIXES):
        return Finding(path, "a Terraform artifact is tracked. CON-12 reserves "
                             "Terraform to upstream entry points.")
    return None


def is_arm_document(document):
    if not isinstance(document, dict):
        return False
    schema = document.get("$schema")
    if isinstance(schema, str) and _ARM_SCHEMA.search(schema):
        return True
    return "contentVersion" in document and (
        "resources" in document or "parameters" in document
    )


def arm_json_finding(path, text):
    try:
        document = json.loads(text)
    except ValueError:
        return Finding(path, "is not valid JSON, so whether it is an ARM template "
                             "cannot be decided; refused rather than assumed safe.")
    if is_arm_document(document):
        return Finding(path, "is an ARM JSON deployment template or parameter file. "
                             "ARM JSON is a compiled output, never a committed "
                             "input (ADR-0002); author Bicep instead.")
    return None


# --------------------------------------------------------------------------- #
# Bicep
# --------------------------------------------------------------------------- #

Declaration = namedtuple("Declaration", "symbol type existing")


class BicepParseError(ValueError):
    pass


def _skip_string(text, i):
    """Return (index after the string starting at i, literal value or None).

    The value is None when the string interpolates, because its runtime value
    cannot be known offline.
    """
    if text.startswith("'''", i):
        end = text.find("'''", i + 3)
        if end < 0:
            raise BicepParseError("unterminated multi-line string")
        return end + 3, text[i + 3:end]
    i += 1
    chars = []
    interpolated = False
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            chars.append(text[i + 1])
            i += 2
            continue
        if c == "'":
            return i + 1, None if interpolated else "".join(chars)
        if c == "\n":
            break
        if text.startswith("${", i):
            interpolated = True
            i = _skip_expression(text, i + 2)
            continue
        chars.append(c)
        i += 1
    raise BicepParseError("unterminated string")


def _skip_expression(text, i):
    depth = 1
    while i < len(text):
        c = text[i]
        if c == "'":
            i, _ = _skip_string(text, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise BicepParseError("unterminated interpolation")


def _tokens(text):
    """Yield (kind, value) with kind in ident, string, punct. Comments vanish."""
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise BicepParseError("unterminated block comment")
            i = end + 2
        elif c == "'":
            i, value = _skip_string(text, i)
            yield "string", value
        elif c.isalpha() or c == "_":
            start = i
            while i < n and (text[i].isalnum() or text[i] == "_"):
                i += 1
            yield "ident", text[start:i]
        else:
            yield "punct", c
            i += 1


def _is_full_type(type_name):
    return bool(_FULL_TYPE.match(type_name))


def bicep_declarations(text):
    """Return every resource declaration in a Bicep file, with full types.

    A child declared inside its parent's body carries a relative type; it is
    resolved against the enclosing resource so that nesting cannot hide a
    re-authored type. Raises BicepParseError when a declaration cannot be
    resolved offline.
    """
    tokens = list(_tokens(text))
    declarations = []
    stack = []
    depth = 0
    pending = None
    i = 0
    while i < len(tokens):
        kind, value = tokens[i]
        if kind == "punct" and value == "{":
            depth += 1
            if pending is not None:
                stack.append((depth, pending))
                pending = None
        elif kind == "punct" and value == "}":
            if stack and stack[-1][0] == depth:
                stack.pop()
            depth -= 1
        elif (
            kind == "ident"
            and value == "resource"
            and i + 1 < len(tokens)
            and tokens[i + 1][0] == "ident"
            and not (i > 0 and tokens[i - 1][0] == "ident" and tokens[i - 1][1] in _NAMING_KEYWORDS)
        ):
            symbol = tokens[i + 1][1]
            if i + 2 >= len(tokens) or tokens[i + 2][0] != "string":
                raise BicepParseError("resource %s has no literal type" % symbol)
            literal = tokens[i + 2][1]
            if literal is None:
                raise BicepParseError(
                    "resource %s has an interpolated type that cannot be "
                    "resolved offline" % symbol
                )
            if "@" not in literal:
                raise BicepParseError("resource %s names no API version" % symbol)
            type_name = literal.split("@", 1)[0]
            if not _is_full_type(type_name):
                if not stack:
                    raise BicepParseError(
                        "resource %s has a relative type outside any parent" % symbol
                    )
                type_name = stack[-1][1] + "/" + type_name
                if not _is_full_type(type_name):
                    raise BicepParseError(
                        "resource %s resolves to a malformed type" % symbol
                    )
            existing = (
                i + 3 < len(tokens)
                and tokens[i + 3] == ("ident", "existing")
            )
            declarations.append(Declaration(symbol, type_name, existing))
            pending = type_name
            i += 3
            continue
        i += 1
    return declarations


def bicep_findings(path, text, upstream_types):
    forbidden = {t.lower() for t in upstream_types}
    try:
        declarations = bicep_declarations(text)
    except BicepParseError as error:
        return [Finding(path, "cannot be audited offline: %s." % error)]
    return [
        Finding(
            path,
            "declares resource %s of type %s, which the pinned upstream already "
            "creates. Compose the upstream module instead of re-authoring it "
            "(ADR-0002); reference it with `existing` if it is only read."
            % (d.symbol, d.type),
        )
        for d in declarations
        if not d.existing and d.type.lower() in forbidden
    ]


# --------------------------------------------------------------------------- #
# The measured upstream list
# --------------------------------------------------------------------------- #


def measure(tree):
    """Measure every resource type the Bicep files under ``tree`` create."""
    declared_in = {}
    canonical = {}
    for directory, subdirectories, names in os.walk(tree):
        subdirectories.sort()
        for name in sorted(names):
            if not name.lower().endswith(".bicep"):
                continue
            full = os.path.join(directory, name)
            relative = os.path.relpath(full, tree).replace(os.sep, "/")
            with open(full, encoding="utf-8") as handle:
                declarations = bicep_declarations(handle.read())
            for d in declarations:
                if d.existing:
                    continue
                key = d.type.lower()
                canonical.setdefault(key, d.type)
                declared_in.setdefault(key, set()).add(relative)
    return [
        {"type": canonical[key], "declaredIn": sorted(declared_in[key])}
        for key in sorted(canonical)
    ]


def load_upstream_types(root):
    """Load the measured list, refusing any shape or pin it cannot vouch for."""
    with open(os.path.join(root, UPSTREAM_TYPES_PATH), encoding="utf-8") as h:
        document = json.load(h)
    with open(os.path.join(root, UPSTREAM_LOCK_PATH), encoding="utf-8") as h:
        pinned = json.load(h)["upstream"]["commit"]
    expected = {"$comment", "upstreamCommit", "measurement", "resourceTypes"}
    if not isinstance(document, dict) or set(document) != expected:
        raise ValueError("%s: expected exactly the keys %s"
                         % (UPSTREAM_TYPES_PATH, sorted(expected)))
    commit = document["upstreamCommit"]
    if not isinstance(commit, str) or not _COMMIT.match(commit):
        raise ValueError("%s: upstreamCommit is not a commit digest" % UPSTREAM_TYPES_PATH)
    if commit != pinned:
        raise ValueError(
            "%s measures upstream %s but the lock pins %s. Re-measure the "
            "pinned tree before trusting this list." % (UPSTREAM_TYPES_PATH, commit, pinned)
        )
    entries = document["resourceTypes"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("%s: resourceTypes must be a non-empty list" % UPSTREAM_TYPES_PATH)
    seen = set()
    types = []
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"type", "declaredIn"}
            or not isinstance(entry["type"], str)
            or not _is_full_type(entry["type"])
            or not isinstance(entry["declaredIn"], list)
            or not entry["declaredIn"]
            or not all(isinstance(p, str) and p for p in entry["declaredIn"])
        ):
            raise ValueError("%s: malformed resourceTypes entry" % UPSTREAM_TYPES_PATH)
        key = entry["type"].lower()
        if key in seen:
            raise ValueError("%s: %s is listed twice" % (UPSTREAM_TYPES_PATH, entry["type"]))
        seen.add(key)
        types.append(entry["type"])
    return types


# --------------------------------------------------------------------------- #
# The repository check
# --------------------------------------------------------------------------- #


def check(root, files, upstream_types):
    """Return every finding over the given tracked files."""
    findings = []
    for path in sorted(files):
        finding = terraform_finding(path)
        if finding:
            findings.append(finding)
            continue
        lowered = path.lower()
        if not lowered.endswith((".json", ".jsonc", ".bicep")):
            continue
        with open(os.path.join(root, path), encoding="utf-8") as handle:
            text = handle.read()
        if lowered.endswith(".bicep"):
            findings.extend(bicep_findings(path, text, upstream_types))
        else:
            finding = arm_json_finding(path, text)
            if finding:
                findings.append(finding)
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m zeroops.iac_structure",
        description="Measure the resource types a fetched upstream tree creates.",
    )
    parser.add_argument("--measure", metavar="TREE", required=True,
                        help="a fetched and verified upstream template tree")
    arguments = parser.parse_args(argv)
    try:
        measured = measure(arguments.measure)
    except BicepParseError as error:
        print("cannot measure: %s" % error, file=sys.stderr)
        return 2
    json.dump(measured, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

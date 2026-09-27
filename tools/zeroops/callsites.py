"""The check that makes the command broker a guarantee rather than a habit.

FR-11 requires that a build fail when a call site inside a declared core path
reaches Azure without going through `tools/zeroops/broker.py`, or names a verb
outside the read-only allow-list. Without this, the broker is a function
people are asked to remember.

Two rules, and they fail for different reasons on purpose:

1.  **No core path may invoke anything itself.** Not the Azure CLI, not an
    SDK, not a shell. The rule is about the capability to invoke rather than
    about recognising Azure, because a list of ways to reach Azure is a list
    somebody has to keep complete, and the day it is not is the day this
    check passes for the wrong reason. `subprocess` in a core path is a
    finding whether or not the command it runs looks like Azure.

2.  **A brokered call may name only an allowed verb.** The broker refuses at
    runtime, but a wizard that only fails when a user runs it has already
    shipped. Literal commands are readable statically, so they are read.

Neither rule can be satisfied by `core/` being empty. The scan reports how
many files it examined, and the suite asserts the count, because a scan of
nothing returns no findings and looks identical to a clean repository.
"""

import ast
import os
import re


# What a core path must never contain. A total registry: each entry records
# why the capability is wrong in a core path, so adding an exception means
# writing down what changed.
INVOCATION_MARKERS = (
    (
        r"\bsubprocess\b",
        "spawns a process. Every Azure call goes through the broker (CON-02), "
        "and a core path that can spawn anything can spawn az.",
    ),
    (
        r"\bos\.system\b",
        "runs a command through a shell, which is the broker's token rule "
        "inverted.",
    ),
    (
        r"\bos\.popen\b",
        "runs a command through a shell.",
    ),
    (
        r"^\s*(?:from|import)\s+azure\b",
        "imports an Azure SDK directly, reaching past the broker.",
    ),
    (
        r"\bazure\.mgmt\b",
        "names an Azure management SDK, reaching past the broker.",
    ),
    (
        r"\bazure\.identity\b",
        "acquires credentials directly. The broker is the only place a "
        "credential is used.",
    ),
    (
        r"(?:Get|New|Set|Remove|Update|Invoke|Start|Stop)-Az[A-Za-z]+",
        "is an Azure PowerShell cmdlet, reaching past the broker.",
    ),
    (
        r"\baz\s+(?:account|group|resource|role|graph|rest|vm|aks)\b",
        "is a literal Azure CLI command line, reaching past the broker.",
    ),
)

# Calls whose first argument is read as a brokered command.
BROKER_CALLS = ("invoke", "plan")

SCANNABLE_SUFFIXES = (".py", ".ps1", ".sh", ".psm1", ".bicep", ".json", ".md")


def scannable(path):
    return path.lower().endswith(SCANNABLE_SUFFIXES)


def scanned_paths(files, declaration):
    """Files under a category the core rule applies to.

    `core` and `binding` together: the binding layer names the runtime, which
    is why it exists, but it is not exempt from routing its calls through the
    broker.
    """
    prefixes = []
    for category in ("core", "binding"):
        for entry in declaration["categories"].get(category, []):
            prefixes.append(entry["path"])
    chosen = []
    for path in files:
        if not scannable(path):
            continue
        for prefix in prefixes:
            if (path.startswith(prefix) if prefix.endswith("/") else path == prefix):
                chosen.append(path)
                break
    return chosen


def marker_findings(text):
    """Return (line number, marker, reason) for every invocation capability."""
    found = []
    lines = text.splitlines()
    for pattern, reason in INVOCATION_MARKERS:
        compiled = re.compile(pattern, re.MULTILINE)
        for number, line in enumerate(lines, start=1):
            if compiled.search(line):
                found.append((number, pattern, reason))
    return found


def _literal_tokens(node):
    """The tokens of a list literal, or None if it is not one.

    A command assembled at runtime is not readable here, and saying so is the
    honest answer. Rule one is what covers the case where the command cannot
    be read: a core path has no way to run it.
    """
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    tokens = []
    for element in node.elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
            return None
        tokens.append(element.value)
    return tokens


def verb_findings(text, allowed):
    """Return (line number, verb) for every literal brokered command whose
    verb is not on the allow-list."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
        if name not in BROKER_CALLS:
            continue
        tokens = _literal_tokens(node.args[0])
        if tokens is None:
            continue
        verb = _verb_of(tokens)
        # A missing verb and a disallowed one are both findings here. They
        # are separated where they are reported, not where they are found:
        # branching in both places is redundant, and a redundant branch is a
        # branch no test can distinguish.
        if verb is None or verb not in allowed:
            found.append((node.lineno, verb))
    return found


def _verb_of(tokens):
    words = []
    for token in tokens[1:]:
        if token.startswith("-"):
            break
        words.append(token)
    return words[-1] if words else None


def scan(root, files, declaration, allowed):
    """Return (problems, examined). The count is part of the result.

    A scan that examined nothing reports no problems and is indistinguishable
    from a clean repository, which is how a check quietly stops covering the
    thing it was written for.
    """
    problems = []
    paths = scanned_paths(files, declaration)
    for path in paths:
        full = os.path.join(root, path.replace("/", os.sep))
        try:
            with open(full, "r", encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        for number, pattern, reason in marker_findings(text):
            problems.append(
                "%s:%d: matches %s, which %s" % (path, number, pattern, reason)
            )
        for number, verb in verb_findings(text, allowed):
            if verb is None:
                problems.append(
                    "%s:%d: brokered command names no verb at all, so there is "
                    "nothing to check against the read-only allow-list."
                    % (path, number)
                )
            else:
                problems.append(
                    "%s:%d: brokered command names verb %r, which is not on the "
                    "read-only allow-list (%s)."
                    % (path, number, verb, ", ".join(allowed))
                )
    return problems, len(paths)

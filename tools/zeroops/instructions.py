"""NEG-E: no declared core path contains an instruction region.

The threat
----------

Untrusted diagnostic content is logs, payloads, documents and pull-request
text. FR-55 requires it be treated as data and never as instructions. At the
model layer that property is probabilistic, so it is measured rather than
gated (CC-023). At the structural layer it is deterministic, and this is the
structural half.

The rule, and why it is stronger than the requirement
-----------------------------------------------------

FR-55 asks that no core path *admit* retrieved content into the instruction or
prompt-assembly region. The rule enforced here is that no core path *has* such
a region at all.

That is deliberate. Checking "content does not flow into the region" needs a
taint analysis, which needs a list of the functions that return untrusted
content, which is a list somebody has to keep complete. The call-site check
already refused that shape of rule for the same reason: it made its rule about
the capability to invoke rather than about recognising Azure, because the day
the list is incomplete is the day the check passes for the wrong reason.

A region that does not exist cannot be filled. This framework never assembles a
prompt: the agent definition names skills and never inlines them, and the
runtime assembles what it sends. So the rule costs nothing today, and the day
it costs something is the day somebody is adding an instruction region to a
core path, which is a decision that should be made out loud.

The containment argument, which this check is only one third of
---------------------------------------------------------------

Retrieved content cannot reach an instruction region inside a core path
because:

1.  A core path cannot retrieve anything. No invocation capability may appear
    in one, which is NEG-H's first rule in `callsites.py`.
2.  A core path has no instruction region. That is this check.
3.  No core schema carries a free-form field that could hold one. That is
    NEG-I, which T2.08 owns.

Each leg fails for a different reason, and none of them implies the others.
The first leg matters most to this one: if the invocation rule were unwired,
this check would keep passing while the claim built on it stopped being true.
A test therefore asserts that NEG-H is still wired into the same gate, because
a check whose argument rests on a neighbour should notice when the neighbour
leaves.

Structure is scanned. Prose is not.
------------------------------------

In JSON, object keys are read and values are not. In Python, bound names are
read and string literals are not.

This is not a convenience. `contracts/schemas/readiness-result.schema.json`
contains the sentence "A hint for a person, never an instruction for the
agent", and `contracts/core-paths.json` describes a directory as holding
"authoring instructions". A text scan would flag both, and the first of them
is a file stating the very rule this check enforces. A check that fails a file
for explaining its own compliance has stopped measuring anything.

Markdown is not scanned at all, for the same reason: a markdown file in a core
path is prose, and prose is where the rule gets explained.

The boundary that leaves behind is real and is named rather than papered over:
this check would not notice instruction-shaped text pasted into a JSON value
under an innocuous key. That is what the free-form field prohibition is for,
and it is the third leg above.

Why these words and not more
----------------------------

The vocabulary was chosen against the keys this repository actually has, not
against a guess. All 242 distinct keys across the core JSON files were
enumerated first. None contains prompt, instruction, instructions, message or
messages as a word, so each marker below fails closed on a real new key rather
than on something already committed.

Two candidates were rejected on that evidence:

`content` and `text` would fire on `contentHash` and `queryText`, which exist
today. `contentHash` in particular is the mechanism NEG-F uses to keep
retrieved content out of the evidence manifest, so a rule that flagged it
would be a rule that flagged the mitigation.

`completion` was rejected on meaning rather than collision. It names model
output, not an instruction region, and `handoff-record` already uses
completion in its ordinary English sense for a finished execution.
"""

import ast
import json
import os
import re


# What a core path must never name. A total registry: each entry records why
# the name is an instruction region, so adding an exception means writing down
# what changed.
INSTRUCTION_MARKERS = (
    (
        "prompt",
        "names a prompt. A prompt is the instruction region itself, and a core "
        "path that has one has somewhere for retrieved content to land.",
    ),
    (
        "instruction",
        "names an instruction. Diagnostic content reaching an instruction is "
        "the failure FR-55 exists to prevent.",
    ),
    (
        "instructions",
        "names an instruction set, which is the instruction region under its "
        "plural spelling.",
    ),
    (
        "message",
        "names a chat message. A message is what an assembled prompt is made "
        "of, so a core path that builds one is assembling a prompt.",
    ),
    (
        "messages",
        "names a chat message sequence, which is the canonical prompt-assembly "
        "structure.",
    ),
)

MARKER_WORDS = {word for word, _ in INSTRUCTION_MARKERS}

REASONS = dict(INSTRUCTION_MARKERS)

# Read for structure. Markdown is deliberately absent; see the module
# docstring on prose.
SCANNED_SUFFIXES = (".json", ".py")

_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|[0-9]+")


def words_of(name):
    """Split an identifier into lowercase words.

    Handles camelCase, snake_case, kebab-case and screaming acronyms, so
    systemPrompt, system_prompt and SYSTEM_PROMPT all reduce to the same pair.
    Splitting rather than substring matching is what keeps completedAt and
    contentHash clean: a substring rule would have to special-case them, and a
    rule with exceptions is a rule somebody has to maintain.
    """
    return [piece.lower() for piece in _WORD.findall(name)]


def marker_of(name):
    """The marker this name trips, or None."""
    for word in words_of(name):
        if word in MARKER_WORDS:
            return word
    return None


def json_names(node, trail=()):
    """Every object key in a JSON document, with the trail that reaches it.

    Keys only. Values carry prose, and prose is where this rule gets
    explained rather than broken.
    """
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append((key, trail))
            found.extend(json_names(value, trail + (key,)))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(json_names(item, trail + (str(index),)))
    return found


def python_names(tree):
    """Every name a module binds, imports or accepts, with its line.

    Bound names, imported names and parameters, never string constants. A core
    path that mentions the word prompt in a comment is documenting something;
    one that binds a name called prompt has a place to put a prompt.

    Loads are not read, and that is not an omission. Python cannot read a name
    a module did not bind or import somewhere, so every load has a binding
    already reported. Reporting the load as well would report one region once
    per use and bury the line that created it.

    Imports are read for both spellings. `from x import prompt as p` binds `p`
    locally, but what it reaches for is still a prompt, and a rule that only
    read the local spelling could be satisfied by renaming. Dotted module names
    are read segment by segment for the same reason: `import prompts.loader`
    binds `prompts` while `import loader.prompts` binds `loader`, so a rule
    that picked either end would be a rule with a way around it.
    """
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            found.append((node.id, node.lineno))
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            found.append((node.attr, node.lineno))
        elif isinstance(node, ast.alias):
            for segment in node.name.split("."):
                found.append((segment, node.lineno))
            if node.asname:
                found.append((node.asname, node.lineno))
        elif isinstance(node, ast.arg):
            found.append((node.arg, node.lineno))
        elif isinstance(node, ast.keyword) and node.arg:
            found.append((node.arg, node.lineno))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.append((node.name, node.lineno))
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    found.append((key.value, key.lineno))
    return found


def scanned_paths(files, declaration):
    """Files under a category this rule applies to.

    The same selection the call-site check makes, narrowed to the suffixes
    read here. Core and binding together: the binding layer names the runtime,
    which is why it exists, and that is not a reason to let it hold a prompt.
    """
    prefixes = []
    for category in ("core", "binding"):
        for entry in declaration["categories"].get(category, []):
            prefixes.append(entry["path"])
    chosen = []
    for path in files:
        if not path.lower().endswith(SCANNED_SUFFIXES):
            continue
        for prefix in prefixes:
            if (path.startswith(prefix) if prefix.endswith("/") else path == prefix):
                chosen.append(path)
                break
    return chosen


def scan(root, files, declaration):
    """Return (problems, examined).

    `examined` counts by kind rather than in total, because the two halves of
    this rule cover different file types and one of them legitimately covers
    nothing today: no core path is Python yet. A single total would let the
    Python half fall to zero without anybody noticing, and a scan of nothing
    reports no problems and looks exactly like a clean repository.
    """
    problems = []
    examined = {"json": 0, "python": 0}
    for path in scanned_paths(files, declaration):
        full = os.path.join(root, path.replace("/", os.sep))
        try:
            with open(full, "r", encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError):
            continue

        if path.lower().endswith(".json"):
            try:
                document = json.loads(text)
            except ValueError:
                continue
            examined["json"] += 1
            for name, trail in json_names(document):
                marker = marker_of(name)
                if marker:
                    problems.append(
                        "%s: key %r at /%s %s"
                        % (path, name, "/".join(trail), REASONS[marker])
                    )
        else:
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            examined["python"] += 1
            for name, line in python_names(tree):
                marker = marker_of(name)
                if marker:
                    problems.append(
                        "%s:%d: name %r %s" % (path, line, name, REASONS[marker])
                    )
    return problems, examined

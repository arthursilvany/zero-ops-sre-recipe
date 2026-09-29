"""Eligibility rules: one source, two renderings (FR-12, FR-10).

FR-12 does not ask for the rules to be written down. It asks that the rules a
reader finds in the published document and the rules the step reports when it
finds nothing are *the same rules*. Those are different sentences. A document
and a reporter can both be correct on the day they are written and disagree a
month later, and nothing about either one would look wrong in isolation.

So the rules live in `wizard/eligibility/eligibility-rules.json` and nowhere
else. This module renders them, and the published README carries a generated
block that must equal that rendering. The drift check is what makes FR-12
falsifiable: adding a rule to the JSON without regenerating the block fails,
and editing the block by hand fails, and both fail with the difference shown.

Why a generated block rather than a document that simply cites the file: an
operator reading the README has to be able to see the rules. A README that
said "the rules are in the JSON" would satisfy 'single source' and fail
'published', and no check would notice, because there would be nothing left to
compare.

Why the preamble is in the JSON too. The empty result is framing plus rules.
If the framing lived here in code, it would be the one part of what the
operator reads that no drift check covered, and it is the part most likely to
be reworded.

## Why this module decides nothing

It renders. It does not filter, and it holds no resource type. Type
eligibility arrives from an installed extension (ELI-004), because the core
ships no workload-type content of its own in either direction (FR-63, CC-022,
CON-11). A default list of admitted types here would be workload content in a
core path, and a default list of excluded types would be the same content
written backwards.
"""

import json
import os
import sys


RULES_PATH = "wizard/eligibility/eligibility-rules.json"
DOCUMENT_PATH = "wizard/eligibility/README.md"

BEGIN_MARKER = "<!-- BEGIN GENERATED RULES -->"
END_MARKER = "<!-- END GENERATED RULES -->"

# What each value of decidedBy tells an operator to go and change. Kept here
# rather than in the JSON because it is a property of the vocabulary the schema
# already constrains, not of any individual rule, and duplicating it onto every
# rule would let two rules disagree about what 'operator' means.
DECIDED_BY_HINT = {
    "operator": "you supplied this",
    "azure": "the platform answered this",
    "extension": "an installed extension declared this",
}

MISSING_MARKERS = (
    "%s: the generated rules block is missing. Expected a %s line and a %s "
    "line, in that order. Without them there is nothing to compare the "
    "published rules against, and FR-12 would pass on a document that says "
    "whatever it likes."
)

DRIFT = (
    "%s: the generated rules block does not match %s. The document and the "
    "empty-result report would tell an operator different things. Replace the "
    "block with the rendering below.\n\n%s"
)

UNKNOWN_DECIDED_BY = (
    "%s: decidedBy %r has no operator-facing hint. The rule would render "
    "without telling the reader which of the three things to go and change."
)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def rules_path(root=None):
    root = root or repo_root()
    return os.path.join(root, RULES_PATH.replace("/", os.sep))


def document_path(root=None):
    root = root or repo_root()
    return os.path.join(root, DOCUMENT_PATH.replace("/", os.sep))


def load_rules(root=None):
    with open(rules_path(root), "r", encoding="utf-8") as handle:
        return json.load(handle)


def hint_findings(rules):
    """Every decidedBy value must have a hint.

    The schema constrains decidedBy to three values and this module maps those
    three to operator-facing text. Adding a fourth to the schema without adding
    its hint would render a rule that names no owner, and the renderer would
    otherwise do that silently.
    """
    findings = []
    for rule in rules.get("rules", []):
        decided = rule.get("decidedBy")
        if decided not in DECIDED_BY_HINT:
            findings.append(UNKNOWN_DECIDED_BY % (rule.get("id"), decided))
    return findings


def render_rules(rules):
    """Render the rule set as the markdown block the document carries.

    Deterministic and newline-normalised, because this string is compared
    against a file that may have been checked out with either line ending.
    """
    lines = []
    for rule in rules["rules"]:
        hint = DECIDED_BY_HINT.get(rule["decidedBy"], rule["decidedBy"])
        lines.append("### %s %s" % (rule["id"], rule["title"]))
        lines.append("")
        lines.append(rule["statement"])
        lines.append("")
        lines.append("Decided at the %s stage; %s." % (rule["stage"], hint))
        lines.append("")
        lines.append("If this rule excluded everything: %s" % rule["whyEmpty"])
        lines.append("")
    return "\n".join(lines).rstrip("\n")


def empty_result_report(rules):
    """What discovery prints when it finds no candidate (FR-10, FR-12).

    Built from the same rendering the document carries, so the two cannot
    disagree without the drift check failing. The preamble comes from the JSON
    for the same reason.
    """
    return "%s\n\n%s" % (rules["emptyResultPreamble"], render_rules(rules))


def _normalise(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def extract_block(document):
    """Return the text between the markers, or None if either is missing or
    they appear in the wrong order."""
    document = _normalise(document)
    begin = document.find(BEGIN_MARKER)
    end = document.find(END_MARKER)
    if begin == -1 or end == -1 or end < begin:
        return None
    return document[begin + len(BEGIN_MARKER) : end].strip("\n")


def drift_findings(root=None, rules=None, document=None):
    """Compare the published document against the rendering (FR-12).

    Returns findings rather than raising, matching the other checks, so the
    caller can report every problem in one pass.
    """
    rules = rules if rules is not None else load_rules(root)
    if document is None:
        with open(document_path(root), "r", encoding="utf-8") as handle:
            document = handle.read()

    findings = hint_findings(rules)
    expected = render_rules(rules)
    block = extract_block(document)
    if block is None:
        findings.append(
            MISSING_MARKERS % (DOCUMENT_PATH, BEGIN_MARKER, END_MARKER)
        )
        return findings
    if block != expected:
        findings.append(DRIFT % (DOCUMENT_PATH, RULES_PATH, expected))
    return findings


def replace_block(document, block):
    """Return the document with the generated block replaced.

    Only the text between the markers changes. The prose around it stays as
    written, because the prose is a document an author maintains and the block
    is a rendering a machine owns; regenerating must not silently discard the
    first to refresh the second.

    Raises ValueError when the markers are absent, rather than appending a
    block, because a document without markers is not a document this tool has
    ever owned and guessing where the rules belong in it would be a worse
    outcome than refusing.
    """
    normalised = _normalise(document)
    begin = normalised.find(BEGIN_MARKER)
    end = normalised.find(END_MARKER)
    if begin == -1 or end == -1 or end < begin:
        raise ValueError(
            MISSING_MARKERS % (DOCUMENT_PATH, BEGIN_MARKER, END_MARKER)
        )
    head = normalised[: begin + len(BEGIN_MARKER)]
    tail = normalised[end:]
    return "%s\n%s\n%s" % (head, block, tail)


def main(argv=None):
    """Regenerate or check the published block.

    `--write` exists so that anyone who changes the JSON can bring the
    document back into agreement. Without it the drift check would be a test
    only its author could satisfy, which is a failing test with no documented
    remedy rather than a gate.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    write = "--write" in argv
    root = repo_root()
    rules = load_rules(root)

    invalid = hint_findings(rules)
    if invalid:
        for finding in invalid:
            print(finding)
        return 1

    if not write:
        findings = drift_findings(root)
        for finding in findings:
            print(finding)
        if findings:
            return 1
        print("wizard/eligibility/README.md is in agreement with the rules.")
        return 0

    path = document_path(root)
    with open(path, "r", encoding="utf-8") as handle:
        document = handle.read()
    updated = replace_block(document, render_rules(rules))
    if _normalise(document) == updated:
        print("wizard/eligibility/README.md already up to date.")
        return 0
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(updated)
    print("Rewrote the generated block in wizard/eligibility/README.md.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

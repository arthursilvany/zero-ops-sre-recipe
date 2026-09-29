"""FR-59: the operator-facing prohibition list and the policy cannot drift apart.

The threat
----------

An operator deciding whether to point this agent at a subscription reads
`docs/prohibited-actions.md`. They do not read `core/policy/tool-policy.json`,
and they should not have to. That makes the page a load-bearing artifact: if
it says the agent cannot publish findings and the policy stopped denying
publication, the operator's decision was made on a false statement.

Drift runs in both directions and the two are not equally bad.

A deny rule added to the policy and not written down leaves the operator with
an incomplete picture of a *safe* system. That is a documentation gap.

A prohibition written down and not present in the policy leaves the operator
relying on a promise nothing keeps. That is the failure this check exists for,
and it is the one that looks fine in review, because the page reads correctly
and the policy is a separate file nobody opened.

Both directions are reported. Neither is treated as the minor one.

Why diffed rather than generated
---------------------------------

The task allowed either. Generating the page from the policy would make drift
impossible by construction, and it was rejected for what it would cost.

The justification strings in the policy are written for a reviewer deciding
whether the rule is right. An operator needs a different thing: what to do
instead. "No finding leaves the environment" explains the rule; "read findings
from inside the environment, and exporting one is a disclosure decision that
is yours to make deliberately" is what someone at three in the morning needs.
No generator produces the second from the first.

So the page is written by hand and the correspondence is checked. The check
also requires that the *what to do instead* column is not empty, because
without it the page would decay into the policy restated in Markdown: it would
pass the diff forever while being worth nothing to the reader it exists for.

Naming the residual: the check establishes that a human wrote guidance, not
that the guidance is good. Nothing mechanical can establish the second.

The boundary half
------------------

FR-59 asks for boundaries as well as prohibitions, and a list of what the
agent cannot do is not a boundary on its own. The allowed capability classes
are diffed the same way, in their own section. Keeping the two sections
separate matters: if both tables were read into one set, a prohibition
documented in the capability table would satisfy the comparison, and the page
would be wrong in exactly the way that is hardest to see.

Failing loudly rather than quietly
------------------------------------

The sections are located by their headings. A renamed heading yields no rows,
which would show up as every identifier being undocumented, and that message
would send the reader looking for the wrong thing. So a missing section and an
empty section are reported as themselves. A check whose failure describes a
different problem is only marginally better than one that does not fail.
"""

import json
import os
import re


DOC = "docs/prohibited-actions.md"
POLICY = "core/policy/tool-policy.json"

PROHIBITION_HEADING = "## What the agent must not do"
CAPABILITY_HEADING = "## What the agent may reach"

# A first-column cell must be exactly one backticked identifier, so the link
# between a row and a policy value is an exact token rather than prose that
# happens to contain one.
IDENTIFIER = re.compile(r"^`([A-Za-z][A-Za-z0-9]*)`$")

# What an author writes in the guidance column when they have nothing to say.
# Rejected so the column cannot be satisfied by a placeholder, which would let
# the page pass while telling the operator nothing.
PLACEHOLDERS = frozenset({"", "-", "--", "---", "\u2014", "n/a", "na", "none", "tbd", "todo", "?"})

MISSING_DOC = "%s is missing, so the prohibitions an operator reads cannot be compared with the policy."
MISSING_POLICY = "%s is missing or unreadable, so there is nothing to compare the documented prohibitions against."
POLICY_NOT_OBJECT = "%s does not contain a JSON object, so its deny rules cannot be read."
NO_SECTION = "%s has no '%s' section, so nothing was compared. The heading is how the section is found."
NO_ROWS = "%s section '%s' has no table rows, so nothing was compared."
BAD_IDENTIFIER = "%s section '%s' has the row label %r, which is not a single backticked identifier."
DUPLICATE = "%s section '%s' documents `%s` more than once."
UNDOCUMENTED = "%s does not document `%s`, which %s declares. An operator reading the page would not know about it."
UNBACKED = "%s documents `%s` under '%s', which %s does not declare. The page promises something no rule keeps."
NO_GUIDANCE = "%s documents `%s` with no guidance in the last column. Without it the page restates the policy rather than helping the reader."


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sections(text):
    """Split Markdown into {heading line: [body lines]} for level-two headings.

    Only level two, because a level-three heading inside a section is part of
    that section rather than a new one.
    """
    found = {}
    current = None
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("## "):
            # A level-three heading does not match: its third character is a
            # hash rather than a space, so no guard against it is needed.
            current = stripped
            found[current] = []
        elif stripped.startswith("#") and not stripped.startswith("##"):
            # A level-one heading ends any section without starting one.
            current = None
        elif current is not None:
            found[current].append(line)
    return found


def rows(body):
    """Return the data rows of the first table in a section body.

    The header row and the delimiter row are dropped. A delimiter row is the
    one whose cells are made only of dashes and colons, which is how a table
    header is written; finding it is what marks the rows after it as data.
    """
    table = []
    seen_delimiter = False
    for line in body:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if table:
                # A blank line or prose after rows have been collected ends
                # the table. A second table in the same section is not read,
                # because it would silently widen what the section means.
                break
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not seen_delimiter:
            if cells and all(re.fullmatch(r":?-{1,}:?", cell) for cell in cells):
                seen_delimiter = True
            continue
        table.append(cells)
    return table


def documented(text, heading, problems, path=DOC):
    """Return the identifiers documented under `heading`, in order.

    Reports its own inability to find anything, rather than returning an empty
    set and letting the comparison blame the policy.
    """
    body = sections(text).get(heading)
    if body is None:
        problems.append(NO_SECTION % (path, heading))
        return []
    table = rows(body)
    if not table:
        problems.append(NO_ROWS % (path, heading))
        return []

    names = []
    for cells in table:
        match = IDENTIFIER.match(cells[0]) if cells else None
        if match is None:
            problems.append(BAD_IDENTIFIER % (path, heading, cells[0] if cells else ""))
            continue
        name = match.group(1)
        if name in names:
            problems.append(DUPLICATE % (path, heading, name))
            continue
        names.append(name)
        guidance = cells[-1].strip().lower() if len(cells) > 1 else ""
        if guidance in PLACEHOLDERS:
            problems.append(NO_GUIDANCE % (path, name))
    return names


def compare(declared, written, heading, problems, path=DOC, policy=POLICY):
    """Report both directions of drift between a policy list and a doc section."""
    for name in declared:
        if name not in written:
            problems.append(UNDOCUMENTED % (path, name, policy))
    for name in written:
        if name not in declared:
            problems.append(UNBACKED % (path, name, heading, policy))


def declared_categories(document):
    rules = document.get("denyRules")
    if not isinstance(rules, list):
        return []
    names = []
    for rule in rules:
        if isinstance(rule, dict) and isinstance(rule.get("category"), str):
            names.append(rule["category"])
    return names


def declared_capabilities(document):
    classes = document.get("allowedCapabilityClasses")
    if not isinstance(classes, list):
        return []
    return [name for name in classes if isinstance(name, str)]


def scan(root, files, declaration):
    """Return (problems, examined).

    `examined` counts the two artifacts separately. A single total would let
    one of them fall to zero while the other kept the count non-zero, and a
    comparison against nothing looks exactly like a comparison that agreed.
    """
    problems = []
    examined = {"policies": 0, "pages": 0}

    policy_full = os.path.join(root, POLICY.replace("/", os.sep))
    if POLICY not in files or not os.path.exists(policy_full):
        problems.append(MISSING_POLICY % POLICY)
        document = None
    else:
        try:
            with open(policy_full, "r", encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, UnicodeDecodeError, ValueError):
            problems.append(MISSING_POLICY % POLICY)
            document = None
        else:
            if not isinstance(document, dict):
                problems.append(POLICY_NOT_OBJECT % POLICY)
                document = None
            else:
                examined["policies"] = 1

    doc_full = os.path.join(root, DOC.replace("/", os.sep))
    if DOC not in files or not os.path.exists(doc_full):
        problems.append(MISSING_DOC % DOC)
        return problems, examined
    try:
        with open(doc_full, "r", encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError):
        problems.append(MISSING_DOC % DOC)
        return problems, examined
    examined["pages"] = 1

    if document is None:
        # The page cannot be checked against a policy that was not read. Say
        # so once, above, rather than reporting every identifier as unbacked.
        return problems, examined

    written_rules = documented(text, PROHIBITION_HEADING, problems)
    written_classes = documented(text, CAPABILITY_HEADING, problems)
    compare(declared_categories(document), written_rules, PROHIBITION_HEADING, problems)
    compare(declared_capabilities(document), written_classes, CAPABILITY_HEADING, problems)
    return problems, examined

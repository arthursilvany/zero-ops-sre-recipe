"""Writing discovery output without leaking it (SEC-007, FR-17, NFR-01).

ADR-0003 requires discovery output to be reviewable and diffable separately
from selection. That means a subscription-wide inventory of real resource
identifiers, names and resource-group names is written into the consumer's
repository, in a repository the consumer may well push. This module exists
because that artifact is a leak path, and three decisions keep it from being
one.

## The ignore rule and the write path are the same fact

`.gitignore` already names `.zeroops/` and `*.discovery.json`. An ignore rule
protects nothing on its own: it protects a path something writes to. If this
module chose any other default, the rule would still be there, the test
asserting the rule works would still pass, and the inventory would still be
committable. So `default_path` is the declared default, the ignore test drives
`git check-ignore` with the value this module publishes, and writing an
unredacted document to a path git does not ignore is refused unless the caller
states in the call that it wants that.

## The header is derived from the content, not from the caller's intent

A redaction flag that stamped the header would produce, on the day the
redactor has a bug, a file that says it is redacted and is not. That file is
worse than no redaction mode at all, because it is the one an operator
attaches to a public bug report without reading. So `write` verifies a
document that claims to be redacted, and refuses to write anything at all when
the verification reports. The claim in the header is therefore a result, not
an assertion.

## Redaction is an allow-list

Only fields named in `PRESERVED_FIELDS` survive a redaction with their value.
Every other string becomes a per-run salted pseudonym. The direction matters:
a denylist would let the next field added to the query projection through by
default, and the failure would be silent. An allow-list makes a forgotten
field redact instead of leak, and the verifier can then decide, structurally,
whether anything unredacted remains, rather than guessing from shape whether a
value looked sensitive. A resource named for its owner matches no pattern.

Pseudonyms preserve joins inside one document, because two rows in the same
resource group produce the same token, which is what makes a redacted
inventory still useful in a bug report. The salt is generated per run and is
never written down, so the tokens in two documents cannot be lined up, and a
token cannot be walked back to a short name by trying candidates.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess

from . import discovery


SCHEMA_VERSION = "1.0.0"

DEFAULT_DIRECTORY = ".zeroops"
DEFAULT_FILENAME = "discovery.json"
REDACTED_SUFFIX = ".redacted.json"

REDACTION_NONE = "none"
REDACTION_PSEUDONYMISED = "pseudonymised"

# The only fields whose value survives redaction. Both are chosen by Azure
# from a closed published set and describe a category rather than an instance:
# a resource type and a region name identify nobody. Everything else in a
# discovery row (identifier, name, resource group, subscription) names a
# specific thing in a specific tenant.
PRESERVED_FIELDS = ("type", "location")

# Framework-authored envelope text. These strings are written by this module
# and reviewed here, so they are not redacted and the verifier does not treat
# them as leftovers.
ENVELOPE_FIELDS = ("schemaVersion", "redaction", "warning", "query", "permission")

PSEUDONYM_PREFIX = "redacted-"
PSEUDONYM_LENGTH = 12
PSEUDONYM_PATTERN = re.compile(
    r"^%s[0-9a-f]{%d}$" % (re.escape(PSEUDONYM_PREFIX), PSEUDONYM_LENGTH)
)

WARNING_NONE = (
    "This file contains real resource identifiers, real resource names and "
    "real resource-group names read from a live Azure subscription. It is "
    "ignored by git on purpose. Do not commit it, do not paste it into an "
    "issue and do not attach it to a support ticket. Produce a redacted copy "
    "instead: python -m zeroops.discovery_output --redact <path>."
)

WARNING_REDACTED = (
    "Redacted copy, safe to attach to a bug report. Identifying values were "
    "replaced with per-run salted pseudonyms; resource types and regions were "
    "kept because they name a category rather than an instance. Equal "
    "pseudonyms mean equal original values within this file only. The salt "
    "was generated for one run and never written down, so tokens here cannot "
    "be matched against tokens in any other file."
)

WARNING_FOR = {
    REDACTION_NONE: WARNING_NONE,
    REDACTION_PSEUDONYMISED: WARNING_REDACTED,
}

# Shapes that are identifying regardless of which field carries them. This is
# the second of two independent checks, and the weaker one: it catches a value
# that leaked through an allow-listed field, and it cannot catch a name that
# looks like an ordinary word. The structural check is what covers that.
IDENTIFIER_SHAPES = (
    (
        "guid",
        re.compile(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
            r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
        ),
    ),
    ("resource group path segment", re.compile(r"(?i)/resourcegroups/[^/\s]+")),
    ("electronic mail address", re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")),
    ("endpoint", re.compile(r"(?i)https?://")),
    ("long hexadecimal run", re.compile(r"(?i)\b[0-9a-f]{32,}\b")),
)


class OutputError(Exception):
    """The document was not written, and the reason is not recoverable here."""


def repo_root():
    return discovery.repo_root()


def default_path(root=None):
    """Where discovery output goes unless the caller says otherwise.

    Published rather than inlined, so the test that asks git whether the
    default is ignored asks about this value and not about a string that
    happened to be true when it was typed.
    """
    return os.path.join(root or repo_root(), DEFAULT_DIRECTORY, DEFAULT_FILENAME)


def redacted_path_for(path):
    base = path[: -len(".json")] if path.endswith(".json") else path
    return base + REDACTED_SUFFIX


def document(result):
    """The unredacted document for one discovery result.

    `partial_rows` rather than `rows` is deliberate: a result with a denial is
    exactly the one worth writing down, and the denials travel in the same
    file so the reduction is visible to whoever reads it.
    """
    return {
        "warning": WARNING_NONE,
        "schemaVersion": SCHEMA_VERSION,
        "redaction": REDACTION_NONE,
        "subscription": result.subscription,
        "complete": result.complete,
        "denials": [
            {"query": denial.query, "permission": denial.permission}
            for denial in result.denials
        ],
        "resources": result.partial_rows(),
    }


def new_salt():
    return os.urandom(16).hex()


def pseudonym(value, salt):
    material = ("%s\x00%s" % (salt, value)).encode("utf-8")
    return PSEUDONYM_PREFIX + hashlib.sha256(material).hexdigest()[:PSEUDONYM_LENGTH]


def _redact_value(value, key, salt):
    if isinstance(value, dict):
        return {name: _redact_value(item, name, salt) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item, key, salt) for item in value]
    if isinstance(value, str) and key not in PRESERVED_FIELDS:
        return pseudonym(value, salt)
    return value


def redact(source, salt=None):
    """A copy of a discovery document with every identifying value replaced.

    The envelope is rebuilt rather than edited, so a field this module does
    not know about cannot survive in the envelope, and the header is written
    from the mode rather than carried over from the input.
    """
    salt = new_salt() if salt is None else salt
    return {
        "warning": WARNING_REDACTED,
        "schemaVersion": SCHEMA_VERSION,
        "redaction": REDACTION_PSEUDONYMISED,
        "subscription": pseudonym(source.get("subscription", ""), salt),
        "complete": source.get("complete", False),
        "denials": [
            {"query": denial.get("query"), "permission": denial.get("permission")}
            for denial in source.get("denials", [])
        ],
        "resources": [
            _redact_value(row, None, salt) for row in source.get("resources", [])
        ],
    }


def _walk_strings(value, pointer, key, out):
    if isinstance(value, dict):
        for name, item in value.items():
            _walk_strings(item, "%s/%s" % (pointer, name), name, out)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_strings(item, "%s/%d" % (pointer, index), key, out)
    elif isinstance(value, str):
        out.append((pointer or "/", key, value))


def residual_findings(document_to_check):
    """Everything in a redacted document that is not demonstrably redacted.

    Two independent checks, because either alone passes the case the other
    exists for.

    Structural: a string must be a pseudonym, or sit under a field this module
    decided to preserve, or be envelope text. This is what catches a field
    added to the query projection after redaction was written, and it catches
    it whatever the value looks like.

    Shape: a value that is identifying by form is reported even when it sits
    under a preserved field, because the allow-list is a judgement about a
    field and a judgement can be wrong about one row.
    """
    findings = []
    strings = []
    _walk_strings(document_to_check, "", None, strings)
    for pointer, key, value in strings:
        for label, pattern in IDENTIFIER_SHAPES:
            if pattern.search(value):
                findings.append(
                    "%s: holds a value shaped like a %s. A redacted document "
                    "must not carry one, whichever field it arrived in."
                    % (pointer, label)
                )
        if PSEUDONYM_PATTERN.match(value):
            continue
        if key in PRESERVED_FIELDS or key in ENVELOPE_FIELDS:
            continue
        findings.append(
            "%s: is neither a pseudonym nor a field redaction was told to "
            "preserve, so it reached the output unredacted. Add the field to "
            "PRESERVED_FIELDS with a reason, or let it be pseudonymised."
            % pointer
        )
    return findings


def path_is_ignored(path, root=None):
    """Whether git would refuse to track this path.

    Asked of git rather than read out of .gitignore, because what protects the
    repository is git's decision. A missing git, or a directory that is not a
    repository, is reported as not ignored: the protection cannot be confirmed,
    and an unconfirmed protection is the same risk as an absent one.
    """
    root = root or repo_root()
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", os.path.abspath(path)],
            cwd=root,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0


def write(document_to_write, path=None, root=None, acknowledge_unignored=False):
    """Write a discovery document, or refuse and write nothing.

    Refusing before opening the file is the whole point. A document written
    and then found wanting is already on disk, already in the editor's recent
    files, and possibly already staged.
    """
    root = root or repo_root()
    path = default_path(root) if path is None else path
    mode = document_to_write.get("redaction")

    if mode not in WARNING_FOR:
        raise OutputError(
            "the document declares redaction %r, which is not a mode this "
            "module can vouch for. Build it with document() or redact()."
            % (mode,)
        )

    if mode == REDACTION_PSEUDONYMISED:
        findings = residual_findings(document_to_write)
        if findings:
            raise OutputError(
                "this document says it is redacted and is not, so nothing "
                "was written. Writing it would produce the one file an "
                "operator attaches to a public issue without reading:\n%s"
                % "\n".join(findings)
            )
    elif not acknowledge_unignored and not path_is_ignored(path, root):
        raise OutputError(
            "%s holds real identifiers and git does not ignore it, so it "
            "could be committed. Write it under %s, or pass "
            "acknowledge_unignored=True to record at the call site that an "
            "unprotected path is what was wanted."
            % (path, DEFAULT_DIRECTORY)
        )

    # The header is stamped here, after the checks, so it reports what the
    # document turned out to be rather than what the caller called it.
    stamped = dict(document_to_write)
    stamped["warning"] = WARNING_FOR[mode]

    ordered = {"warning": stamped.pop("warning")}
    ordered.update(stamped)

    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(ordered, indent=2, ensure_ascii=False))
        handle.write("\n")
    return path


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def redact_file(path, destination=None, salt=None):
    source = read(path)
    if source.get("redaction") == REDACTION_PSEUDONYMISED:
        raise OutputError(
            "%s is already redacted. Redacting it again would replace the "
            "pseudonyms with different ones and lose the joins the first "
            "redaction preserved." % path
        )
    destination = redacted_path_for(path) if destination is None else destination
    return write(redact(source, salt=salt), path=destination)


def main(argv=None):  # pragma: no cover - exercised through redact_file
    parser = argparse.ArgumentParser(
        prog="python -m zeroops.discovery_output",
        description=(
            "Produce a redacted copy of a discovery output file, safe to "
            "attach to a bug report."
        ),
    )
    parser.add_argument("--redact", metavar="PATH", required=True)
    parser.add_argument("--out", metavar="PATH", default=None)
    arguments = parser.parse_args(argv)
    try:
        written = redact_file(arguments.redact, destination=arguments.out)
    except OutputError as error:
        print(str(error))
        return 1
    print("Wrote %s" % written)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

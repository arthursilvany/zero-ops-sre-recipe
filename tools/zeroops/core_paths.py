"""Check the core declaration against the repository it describes.

FR-61 asks for a declaration; on its own that is prose. Three properties make
it load-bearing, and each is checked here:

1.  Every tracked file falls under exactly one declared category. Without this
    the declaration decays the moment someone adds a directory, and the SC-01
    diff would silently stop covering the thing it was meant to cover.
2.  No core path names a runtime-specific identifier (FR-04, CON-03). The core
    is only runtime-agnostic if that is enforced rather than intended.
3.  The binding layer does name at least one. A binding that mentions no
    runtime identifier would mean the identifiers had leaked elsewhere, or that
    the forbidden-term list had quietly been emptied, and the FR-04 check above
    would then pass for the wrong reason.

The third check is the one that keeps the other two honest. An allow-list that
forbids nothing passes trivially, so the suite asserts the search can find
something as well as that it finds nothing where it must not.
"""

import json
import os
import subprocess

DECLARATION_PATH = os.path.join("contracts", "core-paths.json")
SCHEMA_PATH = os.path.join("contracts", "schemas", "core-paths.schema.json")

CATEGORY_CORE = "core"
CATEGORY_BINDING = "binding"

# Binary and vendored content is not searched for identifiers: a byte sequence
# inside an image is not a reference to a runtime.
UNSEARCHABLE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".xlsx", ".docx", ".pptx")


class CoreDeclarationError(Exception):
    """The repository and its core declaration disagree."""


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def tracked_files(root):
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CoreDeclarationError(
            "git ls-files failed, so the set of tracked files is unknown. "
            "Refusing to report a result computed from an unknown input."
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def load_declaration(root):
    path = os.path.join(root, DECLARATION_PATH)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _matches(path, prefix):
    if prefix.endswith("/"):
        return path.startswith(prefix)
    return path == prefix


def classify(path, declaration):
    """Return the categories a path falls under. More than one is a conflict."""
    hits = []
    for category, entries in declaration["categories"].items():
        for entry in entries:
            if _matches(path, entry["path"]):
                hits.append((category, entry["path"]))
    return hits


def check_declaration_shape(root, declaration, problems):
    """A 'present' path must exist, and a 'planned' path must not."""
    for category, entries in declaration["categories"].items():
        for entry in entries:
            path = entry["path"].rstrip("/")
            exists = os.path.exists(os.path.join(root, path))
            if entry["status"] == "present" and not exists:
                problems.append(
                    "%s: declared present in '%s' but absent from the repository"
                    % (entry["path"], category)
                )
            if entry["status"] == "planned" and exists:
                problems.append(
                    "%s: declared planned (by %s) but it already exists; flip its "
                    "status to 'present' so the declaration keeps describing reality"
                    % (entry["path"], entry.get("materialisedBy", "an unnamed task"))
                )


def check_coverage(files, declaration, problems):
    """Content must not appear in the repository outside the declaration."""
    for path in files:
        hits = classify(path, declaration)
        if not hits:
            problems.append(
                "%s: is tracked but falls under no declared category. Add it to "
                "contracts/core-paths.json, or the SC-01 baseline stops covering it."
                % path
            )
        elif len(hits) > 1:
            where = ", ".join("%s via %s" % (c, p) for c, p in hits)
            problems.append(
                "%s: falls under more than one category (%s). Exactly one owner is "
                "required, or the SC-01 diff result depends on iteration order."
                % (path, where)
            )


def _searchable(path):
    return not path.lower().endswith(UNSEARCHABLE_SUFFIXES)


def _occurrences(root, path, terms):
    full = os.path.join(root, path)
    try:
        with open(full, "r", encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError):
        return []
    lowered = text.lower()
    return [term for term in terms if term.lower() in lowered]


def check_runtime_identifiers(root, files, declaration, problems):
    terms = [item["term"] for item in declaration["runtimeIdentifiers"]]
    excluded = set(item["path"] for item in declaration.get("selfExclusions", []))

    core_files = []
    binding_files = []
    for path in files:
        if not _searchable(path):
            continue
        for category, _prefix in classify(path, declaration):
            if category == CATEGORY_CORE and path not in excluded:
                core_files.append(path)
            elif category == CATEGORY_BINDING:
                binding_files.append(path)

    for path in core_files:
        found = _occurrences(root, path, terms)
        if found:
            problems.append(
                "%s: a core path names runtime-specific identifier(s) %s. FR-04 "
                "confines these to the binding layer; move the dependency to "
                "core/binding/ rather than widening the exclusion list."
                % (path, ", ".join(sorted(found)))
            )

    if not binding_files:
        # Not a failure while the binding layer is still declared 'planned':
        # there is nothing yet for the counter-check to search. The shape check
        # above is what guarantees this state cannot persist unnoticed.
        return

    if not any(_occurrences(root, path, terms) for path in binding_files):
        problems.append(
            "core/binding/: contains no runtime identifier from the declared list. "
            "Either the binding is empty of runtime specifics, which means they "
            "leaked elsewhere, or the list no longer describes this runtime. Both "
            "make the FR-04 check above pass for the wrong reason."
        )


def check(root=None, declaration=None):
    """Return a list of problems. An empty list means the declaration holds.

    A declaration can be supplied to exercise the checks against a deliberately
    broken one. That is how the suite establishes these checks can fail, which
    the real repository cannot demonstrate precisely because it passes.
    """
    root = root or repo_root()
    if declaration is None:
        declaration = load_declaration(root)
    problems = []

    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        raise CoreDeclarationError(
            "jsonschema is not installed, so the declaration cannot be validated "
            "against its own schema. Refusing to report success."
        )

    with open(os.path.join(root, SCHEMA_PATH), "r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    for error in Draft202012Validator(schema).iter_errors(declaration):
        pointer = "/" + "/".join(str(p) for p in error.absolute_path)
        problems.append("%s#%s: %s" % (DECLARATION_PATH, pointer, error.message))

    if problems:
        # A structurally invalid declaration cannot be reasoned about; the
        # checks below would report faults caused by the malformed input.
        return problems

    files = tracked_files(root)
    check_declaration_shape(root, declaration, problems)
    check_coverage(files, declaration, problems)
    check_runtime_identifiers(root, files, declaration, problems)
    return problems

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
    """Every file git would carry, tracked or merely not ignored.

    --others --exclude-standard is load-bearing. With plain ls-files the gate
    sees only what is already staged or committed, so a contributor who writes
    a new core file and runs this check gets a green result, and the violation
    surfaces only after `git add`. A file that is not ignored is a file that is
    about to be committed, so it belongs in scope now rather than one step later.
    """
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CoreDeclarationError(
            "git ls-files failed, so the set of tracked files is unknown. "
            "Refusing to report a result computed from an unknown input."
        )
    seen = []
    for line in result.stdout.splitlines():
        path = line.strip()
        if path and path not in seen:
            seen.append(path)
    return seen


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


def duplicate_ids(mapping):
    """Return {id: [paths]} for every $id claimed by more than one file.

    Pure, so the suite can show it reports a duplicate rather than only
    observing that the repository currently has none.
    """
    by_id = {}
    for path, identifier in sorted(mapping.items()):
        by_id.setdefault(identifier, []).append(path)
    return dict((k, v) for k, v in by_id.items() if len(v) > 1)


def schema_ids(root, files):
    """Map every tracked *.schema.json path to the $id it declares.

    A schema with no $id maps to None rather than being skipped: dropping it
    would make an absent identifier indistinguishable from a unique one.
    """
    mapping = {}
    for path in files:
        if not path.endswith(".schema.json"):
            continue
        try:
            with open(os.path.join(root, path), "r", encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, ValueError):
            mapping[path] = None
            continue
        identifier = document.get("$id") if isinstance(document, dict) else None
        mapping[path] = identifier
    return mapping


def check_schema_ids(root, files, problems):
    """FR-05: a schema resolves to exactly one definition.

    Two files claiming the same $id make resolution order decide which
    definition wins, and the loser validates nothing while still appearing
    to be in force.
    """
    mapping = schema_ids(root, files)
    for path, identifier in sorted(mapping.items()):
        if identifier is None:
            problems.append(
                "%s: declares no $id, so nothing can reference it and a second "
                "copy of it could not be detected as a duplicate." % path
            )
    named = dict((p, i) for p, i in mapping.items() if i is not None)
    for identifier, paths in sorted(duplicate_ids(named).items()):
        problems.append(
            "%s: claimed by more than one schema (%s). Resolution order would "
            "decide which definition is in force." % (identifier, ", ".join(paths))
        )


KEEP_FILENAMES = (".gitkeep", ".keep", "KEEP", "placeholder")


def check_no_placeholder_directories(files, problems):
    """NFR-24: a directory holding only a keep-file is a promise, not content.

    The keep-file exists to make an empty directory survive git. A directory
    that still needs one has nothing in it, and the structure it implies is
    not yet real.
    """
    contents = {}
    for path in files:
        directory = os.path.dirname(path)
        contents.setdefault(directory, []).append(os.path.basename(path))
    for directory, names in sorted(contents.items()):
        if all(name in KEEP_FILENAMES for name in names):
            problems.append(
                "%s: contains only %s. A keep-file marks a directory that has no "
                "content yet; declare the directory when it holds something."
                % (directory or "<repository root>", ", ".join(sorted(names)))
            )


def check_call_sites(root, files, declaration, problems):
    """FR-11: reaching Azure outside the broker fails the build.

    Folded into this gate rather than given a command of its own. A separate
    command is a step somebody has to remember to add to CI, and the first
    time it is forgotten the build goes green for a reason nobody chose.
    This gate already runs on both runners.
    """
    from . import broker, callsites

    found, examined = callsites.scan(root, files, declaration, broker.allowed_verbs())
    problems.extend(found)
    return examined


def check_instruction_regions(root, files, declaration, problems):
    """FR-55 structural half: no core path holds an instruction region.

    Folded into the same gate as the call-site check, and for the same reason.
    It also matters that the two run together: this check's argument depends on
    the invocation rule holding, so running them apart would let one be dropped
    while the other kept reporting success.
    """
    from . import instructions

    found, examined = instructions.scan(root, files, declaration)
    problems.extend(found)
    return examined


def check_schema_lint(root, files, declaration, problems):
    """SEC-013 and FR-49: no core schema leaves a way in.

    Closed objects, no secret-named property, no free-form field. The third of
    those is the third leg of the instruction-region argument above, which
    names free-form fields as the boundary it cannot see. Running the two in
    one gate is what keeps that argument whole.
    """
    from . import schema_lint

    found, examined = schema_lint.scan(root, files, declaration)
    problems.extend(found)
    return examined


def check_evidence_entry(root, files, declaration, problems):
    """FR-55 second structural half: an evidence entry cannot hold content.

    The companion to the instruction-region check above. That one keeps
    retrieved content out of the instruction region; this one keeps it out of
    the record. Both run here so neither can be dropped while the other keeps
    reporting success.
    """
    from . import evidence

    found, examined = evidence.scan(root, files, declaration)
    problems.extend(found)
    return examined


def check_prohibited_actions(root, files, declaration, problems):
    """FR-59: the page an operator reads still matches the policy it describes.

    The other checks here keep the framework's guarantees true. This one keeps
    the statement of those guarantees true, which is a separate failure: a
    page promising a prohibition the policy stopped making reads correctly and
    is wrong, and nothing else in this gate would notice.
    """
    from . import prohibitions

    found, examined = prohibitions.scan(root, files, declaration)
    problems.extend(found)
    return examined


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
    check_schema_ids(root, files, problems)
    check_no_placeholder_directories(files, problems)
    check_call_sites(root, files, declaration, problems)
    check_instruction_regions(root, files, declaration, problems)
    check_schema_lint(root, files, declaration, problems)
    check_evidence_entry(root, files, declaration, problems)
    check_prohibited_actions(root, files, declaration, problems)
    return problems

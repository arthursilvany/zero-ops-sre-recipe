"""Offline, warning-only checks for consumer skill guidance."""

import os
import re
import sys

EXIT_OK = 0
EXIT_USAGE = 2
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXTENSIONS_DIR = os.path.join(REPO_ROOT, "extensions")
HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
FENCE_PATTERN = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")
FENCE_END_PATTERN = re.compile(r"^\s{0,3}(`+|~+)\s*$")
REQUIRED_SECTIONS = (
    (
        "when it applies",
        {"when to use", "when this skill applies", "when it applies"},
    ),
    ("what to check", {"what to check", "checks", "what to inspect"}),
    (
        "when it does not apply",
        {"when not to use", "when this does not apply", "out of scope"},
    ),
    ("mistake to avoid", {"common mistake", "mistake to avoid", "pitfall"}),
)
PLACEHOLDER = re.compile(
    r"^(?:todo|tbd|n/?a|describe (?:this|here)|add guidance here)[.! ]*$", re.I
)


class SkillLintError(Exception):
    """The requested extension directory could not be inspected."""


def _normalise_heading(value):
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _has_guidance(lines):
    for line in lines:
        text = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", line).strip()
        if (
            text not in {"-", "*", "+", "---", "***"}
            and text
            and not PLACEHOLDER.fullmatch(text)
        ):
            return True
    return False


def _file_findings(path, display_path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except (OSError, UnicodeError) as exc:
        raise SkillLintError("cannot read skill file: %s" % display_path) from exc

    sections = {name: [] for name, _ in REQUIRED_SECTIONS}
    active = None
    active_level = 0
    fence = None
    in_comment = False
    aliases = {alias: name for name, names in REQUIRED_SECTIONS for alias in names}
    for line in lines:
        if fence is not None:
            closing = FENCE_END_PATTERN.match(line)
            if (
                closing
                and closing.group(1)[0] == fence[0]
                and len(closing.group(1)) >= fence[1]
            ):
                fence = None
            continue

        visible = []
        index = 0
        while index < len(line):
            if in_comment:
                end = line.find("-->", index)
                if end < 0:
                    break
                index = end + 3
                in_comment = False
                continue

            start = line.find("<!--", index)
            if start < 0:
                visible.append(line[index:])
                break
            visible.append(line[index:start])
            end = line.find("-->", start + 4)
            if end < 0:
                in_comment = True
                break
            index = end + 3

        visible_line = "".join(visible)
        opening = FENCE_PATTERN.match(visible_line)
        if opening:
            marker = opening.group(1)
            fence = (marker[0], len(marker))
            continue

        heading = HEADING_PATTERN.match(visible_line)
        if heading:
            level = len(visible_line.lstrip().split()[0])
            section = aliases.get(_normalise_heading(heading.group(1)))
            if section is not None:
                active = section
                active_level = level
            elif level <= active_level:
                active = None
        elif active is not None:
            sections[active].append(visible_line)

    return [
        "%s: missing non-empty guidance for %s" % (display_path, name)
        for name, _ in REQUIRED_SECTIONS
        if not _has_guidance(sections[name])
    ]


def lint_directory(target=None):
    """Return Markdown skill findings, without reading outside an extensions root."""
    directory = os.path.abspath(target or EXTENSIONS_DIR)
    if os.path.basename(directory).casefold() != "extensions":
        raise SkillLintError("target directory must be named extensions")
    if os.path.islink(directory) or not os.path.isdir(directory):
        raise SkillLintError("extensions directory does not exist or is not a directory")

    findings = []
    files_seen = 0

    def walk_error(error):
        name = os.path.relpath(error.filename or directory, directory)
        raise SkillLintError("cannot inspect extension directory: %s" % name) from error

    for current, directories, filenames in os.walk(
        directory, topdown=True, onerror=walk_error, followlinks=False
    ):
        kept_directories = []
        for name in sorted(directories):
            path = os.path.join(current, name)
            if os.path.islink(path):
                findings.append(
                    "%s: symbolic link not inspected" % os.path.relpath(path, directory)
                )
            else:
                kept_directories.append(name)
        directories[:] = kept_directories

        for name in sorted(filenames):
            if not name.lower().endswith(".md") or name.casefold() == "readme.md":
                continue
            path = os.path.join(current, name)
            relative = os.path.relpath(path, directory)
            if os.path.islink(path):
                findings.append("%s: symbolic link not inspected" % relative)
                continue
            files_seen += 1
            findings.extend(_file_findings(path, relative))
    return files_seen, findings


def run(target=None):
    try:
        files_seen, findings = lint_directory(target)
    except SkillLintError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return EXIT_USAGE

    if not files_seen:
        sys.stdout.write("No skill Markdown files found under the extensions directory.\n")
    if findings:
        for finding in findings:
            sys.stderr.write("warning: %s\n" % finding)
        sys.stderr.write(
            "%d skill guidance warning(s); warnings do not change the exit status.\n"
            % len(findings)
        )
    elif files_seen:
        sys.stdout.write(
            "Skill guidance sections are present in %d file(s).\n" % files_seen
        )
    return EXIT_OK

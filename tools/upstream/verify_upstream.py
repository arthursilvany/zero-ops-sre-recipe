#!/usr/bin/env python3
"""Verify the pinned upstream template layer before any of its code executes.

Why this exists
---------------
ADR-0001 composes the upstream ``microsoft/sre-agent`` template layer rather
than forking it, which means upstream code runs on the operator workstation,
the highest-privilege boundary in the system (CON-06). Acquiring that code is a
trust-boundary crossing, not a download.

SEC-004 requires the pin to be an immutable commit digest. A git tag is mutable:
the owner of the upstream repository can move it, so a tag-pinned dependency can
change underneath a verified build without the pin appearing to change. A tag is
a convenience, not an integrity control.

Digest definition
-----------------
``contentSha256`` is a SHA-256 over the fetched tree, computed so the same tree
produces the same digest on any platform and over any transport (git clone,
release tarball, archive export). Following ADR-0004:

* Files are enumerated recursively, excluding ``.git``.
* Paths are POSIX-relative to the tree root and sorted by their UTF-8 bytes,
  so directory iteration order and filesystem collation cannot affect the result.
* For each file the hash absorbs ``<path>\\0<size>\\0`` followed by the exact
  file bytes. The length prefix prevents a boundary-shifting collision between
  a path and the content that follows it.
* The digest is rendered as lowercase hexadecimal.

File bytes are hashed verbatim. No line-ending normalisation is applied, because
normalising would make two materially different trees hash identically, and it
is precisely a difference that this check exists to detect.

Exit codes
----------
``0`` success, ``1`` verification failure, ``2`` usage or I/O error. Every
failure path is fail-closed: the caller must treat a non-zero exit as "do not
execute the upstream code".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

LOCK_RELATIVE_PATH = "deploy/upstream.lock"
FULL_COMMIT_DIGEST = re.compile(r"^[0-9a-f]{40}$")
EXCLUDED_DIRECTORY_NAMES = {".git"}


class VerificationError(Exception):
    """A condition that must stop the caller from executing upstream code."""


def compute_tree_digest(root: Path) -> str:
    """Return the lowercase hex SHA-256 of a directory tree."""
    if not root.is_dir():
        raise VerificationError(f"not a directory: {root}")

    files = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and not EXCLUDED_DIRECTORY_NAMES.intersection(path.relative_to(root).parts)
        ),
        key=lambda path: path.relative_to(root).as_posix().encode("utf-8"),
    )

    if not files:
        raise VerificationError(
            f"tree contains no files: {root}. An empty tree would otherwise hash to a "
            "stable value and appear to verify successfully."
        )

    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(content)
    return digest.hexdigest()


def load_lock(lock_path: Path) -> dict:
    try:
        return json.loads(lock_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise VerificationError(f"lock file not found: {lock_path}") from error
    except json.JSONDecodeError as error:
        raise VerificationError(f"lock file is not valid JSON: {error}") from error


def check_lock(lock: dict) -> list[str]:
    """Return the reasons the lock is not a valid immutable pin."""
    problems: list[str] = []
    upstream = lock.get("upstream")

    if not isinstance(upstream, dict):
        return ["lock has no 'upstream' object"]

    for field in ("repository", "path", "commit"):
        if not upstream.get(field):
            problems.append(f"'upstream.{field}' is missing or empty")

    commit = upstream.get("commit")
    if isinstance(commit, str) and commit:
        if not FULL_COMMIT_DIGEST.match(commit):
            if re.match(r"^[0-9a-fA-F]{7,39}$", commit):
                problems.append(
                    f"'upstream.commit' is an abbreviated ref ({commit!r}, "
                    f"{len(commit)} characters). An abbreviation can become "
                    "ambiguous as the upstream repository grows; pin the full "
                    "40-character digest."
                )
            elif re.match(r"^[0-9a-f]{40}$", commit, re.IGNORECASE):
                problems.append(
                    "'upstream.commit' must be lowercase hexadecimal so the pin "
                    "compares byte for byte."
                )
            else:
                problems.append(
                    f"'upstream.commit' is not a commit digest ({commit!r}). A tag "
                    "or branch name is mutable and is not an integrity control "
                    "(SEC-004, ADR-0001)."
                )

    return problems


def verify_tree(lock: dict, tree: Path) -> None:
    recorded = lock.get("upstream", {}).get("contentSha256")
    if not recorded:
        raise VerificationError(
            "'upstream.contentSha256' is not set. An unset content digest cannot "
            "attest to anything, so acquisition is refused. Record it with "
            "--record once the tree has been reviewed."
        )

    actual = compute_tree_digest(tree)
    if actual != recorded:
        raise VerificationError(
            "fetched tree does not match the pinned digest.\n"
            f"  expected: {recorded}\n"
            f"  actual:   {actual}\n"
            "Refusing to execute upstream code. Either the fetch was tampered "
            "with, or the pin is stale, in which case updating it is a "
            "security-reviewed change, not a version bump (ADR-0001)."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_upstream",
        description="Verify the pinned upstream template layer, fail closed.",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path(LOCK_RELATIVE_PATH),
        help=f"path to the lock file (default: {LOCK_RELATIVE_PATH})",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check-lock",
        action="store_true",
        help="validate the pin offline; no network and no fetched tree required",
    )
    group.add_argument(
        "--verify",
        type=Path,
        metavar="TREE",
        help="verify a fetched tree against the pinned content digest",
    )
    group.add_argument(
        "--record",
        type=Path,
        metavar="TREE",
        help="compute and write the content digest of a reviewed tree into the lock",
    )
    group.add_argument(
        "--digest",
        type=Path,
        metavar="TREE",
        help="print the content digest of a tree and exit, changing nothing",
    )
    args = parser.parse_args(argv)

    try:
        lock = load_lock(args.lock)

        problems = check_lock(lock)
        if problems:
            print(f"Upstream pin is invalid ({args.lock}):", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1

        if args.check_lock:
            commit = lock["upstream"]["commit"]
            recorded = lock["upstream"].get("contentSha256")
            print(f"Pin OK: {lock['upstream']['repository']}@{commit}")
            print(f"  path:          {lock['upstream']['path']}")
            print(f"  contentSha256: {recorded or 'NOT RECORDED'}")
            return 0

        if args.digest is not None:
            print(compute_tree_digest(args.digest))
            return 0

        if args.record is not None:
            digest = compute_tree_digest(args.record)
            lock["upstream"]["contentSha256"] = digest
            args.lock.write_text(
                json.dumps(lock, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            print(f"Recorded contentSha256: {digest}")
            return 0

        verify_tree(lock, args.verify)
        print(f"Upstream tree verified against {lock['upstream']['commit']}")
        return 0

    except VerificationError as error:
        print(f"FAIL CLOSED: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"I/O error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

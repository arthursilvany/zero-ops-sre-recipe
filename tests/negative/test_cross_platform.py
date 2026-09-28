#!/usr/bin/env python3
"""NEG-J: a digest is identical across platforms, and CI is what makes that true.

Evidence for User Story 2 (SEC-009, FR-19, FR-23).

The pinned digests in `tests/unit/test_canonical.py` are already the right
shape: literal constants, compared against `hashlib` directly so a
transcription error cannot pass as agreement. What was missing is the reason
they are cross-platform evidence at all.

A constant compared against itself agrees on any machine. These constants mean
something only because two different operating systems both had to reproduce
them, and that property lives in `.github/workflows/verify.yml`. Nothing
checked it. Three test docstrings asserted it in prose. Removing
`windows-latest` from the matrix would have left all 967 tests passing while
the cross-platform claim silently became a single-platform one.

This file closes that, and adds the platform-varying inputs no existing test
pins: a path spelled with a backslash, and a string carrying a carriage
return. Both are values that differ by platform if anything ever lets the
running platform choose them.

Run with:
    python -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools", "upstream"))

from zeroops import canonical  # noqa: E402
from zeroops import workflows  # noqa: E402

import verify_upstream  # noqa: E402

WORKFLOW_PATH = os.path.join(REPO_ROOT, workflows.WORKFLOW.replace("/", os.sep))


def workflow_text():
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


class TheReaderIsTestedRatherThanTrusted(unittest.TestCase):
    """A reader that silently found nothing would make every rule below pass.

    There is no YAML parser in the reviewed dependency closure, and adding one
    to read four lines would widen the supply chain for a test. The hand
    written reader is therefore exercised against documents whose contents are
    known, including the shapes it is expected to refuse.
    """

    SAMPLE = "\n".join(
        [
            "name: Example",
            "on: [push]",
            "jobs:",
            "  first:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - run: echo one",
            "  second:",
            "    strategy:",
            "      matrix:",
            "        os: [ubuntu-latest, windows-latest]",
            "    runs-on: ${{ matrix.os }}",
            "    steps:",
            "      - run: python -m unittest discover -s tests",
            "",
        ]
    )

    def test_every_job_is_found(self):
        self.assertEqual(["first", "second"], sorted(workflows.jobs(self.SAMPLE)))

    def test_a_job_block_stops_at_the_next_job(self):
        first = workflows.jobs(self.SAMPLE)["first"]
        self.assertIn("echo one", first)
        self.assertNotIn("unittest discover", first)

    def test_a_document_with_no_jobs_key_reads_as_empty(self):
        self.assertEqual({}, workflows.jobs("name: Example\non: [push]\n"))

    def test_a_key_after_the_jobs_block_does_not_become_a_job(self):
        # A later top-level key whose own nested key has no inline value is
        # the shape that gets misread as a job. `permissions:\n  contents:
        # read` does not, because the nested key carries a value; `defaults:\n
        # run:` does.
        text = self.SAMPLE + "defaults:\n  run:\n    shell: bash\n"
        self.assertEqual(["first", "second"], sorted(workflows.jobs(text)))

    def test_a_later_top_level_key_with_a_value_is_also_excluded(self):
        text = self.SAMPLE + "permissions:\n  contents: read\n"
        self.assertEqual(["first", "second"], sorted(workflows.jobs(text)))

    def test_a_comment_cannot_make_a_job_look_like_the_suite_job(self):
        # A comment is not configuration. A job whose comment mentioned the
        # suite command would otherwise be picked as the job that runs it,
        # and every rule below would then be checked against the wrong job.
        text = "\n".join(
            [
                "jobs:",
                "  decoy:",
                "    # this job used to run unittest discover",
                "    runs-on: ubuntu-latest",
                "    steps:",
                "      - run: echo nothing",
                "  real:",
                "    strategy:",
                "      matrix:",
                "        os: [ubuntu-latest, windows-latest]",
                "    runs-on: ${{ matrix.os }}",
                "    steps:",
                "      - run: python -m unittest discover -s tests",
                "",
            ]
        )
        name, _block = workflows.suite_job(text)
        self.assertEqual("real", name)

    def test_a_runner_named_only_in_a_comment_line_is_not_counted(self):
        block = "\n".join(
            [
                "    strategy:",
                "      matrix:",
                "        os:",
                "          - ubuntu-latest",
                "          # - windows-latest",
            ]
        )
        self.assertEqual(["ubuntu-latest"], workflows.runners_of(block))

    def test_an_empty_entry_is_not_reported_as_a_runner(self):
        # A trailing comma is ordinary YAML. A reader that reported an unnamed
        # runner would produce a count nobody can act on.
        block = "        os: [ubuntu-latest, windows-latest, ]"
        self.assertEqual(
            ["ubuntu-latest", "windows-latest"], workflows.runners_of(block)
        )

    def test_the_suite_job_is_the_one_running_the_suite(self):
        name, block = workflows.suite_job(self.SAMPLE)
        self.assertEqual("second", name)
        self.assertIn("unittest discover", block)

    def test_no_suite_job_is_reported_as_absent_rather_than_guessed(self):
        text = self.SAMPLE.replace("python -m unittest discover -s tests", "echo two")
        self.assertEqual((None, None), workflows.suite_job(text))

    def test_runners_are_read_from_a_flow_sequence(self):
        block = workflows.jobs(self.SAMPLE)["second"]
        self.assertEqual(
            ["ubuntu-latest", "windows-latest"], workflows.runners_of(block)
        )

    def test_runners_are_read_from_a_block_sequence(self):
        block = "\n".join(
            [
                "    strategy:",
                "      matrix:",
                "        os:",
                "          - ubuntu-latest",
                "          - windows-latest",
            ]
        )
        self.assertEqual(
            ["ubuntu-latest", "windows-latest"], workflows.runners_of(block)
        )

    def test_a_step_is_not_mistaken_for_a_runner(self):
        # `- uses: actions/checkout@...` is a list member too. A reader that
        # counted it would find runners in a job that has no matrix at all.
        block = workflows.jobs(self.SAMPLE)["first"]
        self.assertEqual([], workflows.runners_of(block))


class TheMatrixIsWhatMakesAPinnedDigestEvidence(unittest.TestCase):
    def scan_with(self, text):
        root = tempfile.mkdtemp(prefix="neg_j_")
        self.addCleanup(__import__("shutil").rmtree, root, True)
        full = os.path.join(root, workflows.WORKFLOW.replace("/", os.sep))
        os.makedirs(os.path.dirname(full))
        with open(full, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return workflows.scan(root)

    def test_the_committed_workflow_passes(self):
        problems, examined = workflows.scan(REPO_ROOT)
        self.assertEqual([], problems)
        self.assertEqual(1, examined["workflows"])

    def test_the_workflow_was_actually_read(self):
        # A scan of nothing reports the same empty list as a clean one.
        _problems, examined = workflows.scan(REPO_ROOT)
        self.assertEqual(1, examined["workflows"])

    def test_the_committed_workflow_names_both_runners(self):
        _name, block = workflows.suite_job(workflow_text())
        present = workflows.runners_of(block)
        for runner in workflows.REQUIRED_RUNNERS:
            with self.subTest(runner=runner):
                self.assertIn(runner, present)

    def test_dropping_windows_is_a_problem(self):
        # The case this file exists for. Every pinned digest in the repository
        # keeps passing; only this reports that they stopped meaning anything.
        text = workflow_text().replace(
            "os: [ubuntu-latest, windows-latest]", "os: [ubuntu-latest]"
        )
        problems, _ = self.scan_with(text)
        self.assertTrue(any("windows-latest" in p for p in problems), problems)

    def test_dropping_linux_is_a_problem(self):
        text = workflow_text().replace(
            "os: [ubuntu-latest, windows-latest]", "os: [windows-latest]"
        )
        problems, _ = self.scan_with(text)
        self.assertTrue(any("ubuntu-latest" in p for p in problems), problems)

    def test_a_runner_named_only_in_a_comment_does_not_count(self):
        text = workflow_text().replace(
            "os: [ubuntu-latest, windows-latest]",
            "os: [ubuntu-latest] # windows-latest was here",
        )
        problems, _ = self.scan_with(text)
        self.assertTrue(any("windows-latest" in p for p in problems), problems)

    def test_a_matrix_no_leg_reads_is_a_problem(self):
        # Two legs that both run the same platform report two passes for one.
        text = workflow_text().replace(
            "runs-on: ${{ matrix.os }}", "runs-on: ubuntu-latest"
        )
        problems, _ = self.scan_with(text)
        self.assertTrue(any(workflows.NOT_MATRIX_BOUND in p for p in problems), problems)

    def test_fail_fast_left_on_is_a_problem(self):
        # A real divergence between platforms would be reported as a
        # cancellation rather than as a disagreement.
        text = workflow_text().replace("fail-fast: false", "fail-fast: true")
        problems, _ = self.scan_with(text)
        self.assertTrue(any(workflows.FAIL_FAST in p for p in problems), problems)

    def test_a_matrix_that_runs_no_suite_is_a_problem(self):
        text = workflow_text().replace(
            'python -m unittest discover -s tests -p "test_*.py" -t . -v',
            "echo nothing",
        )
        problems, _ = self.scan_with(text)
        self.assertTrue(any(workflows.SUITE_COMMAND in p for p in problems), problems)

    def test_an_absent_workflow_is_a_problem(self):
        root = tempfile.mkdtemp(prefix="neg_j_empty_")
        self.addCleanup(__import__("shutil").rmtree, root, True)
        problems, examined = workflows.scan(root)
        self.assertEqual(1, len(problems))
        self.assertIn(workflows.WORKFLOW, problems[0])
        self.assertEqual(0, examined["workflows"])

    def test_a_workflow_with_no_jobs_is_a_problem(self):
        problems, _ = self.scan_with("name: Example\non: [push]\n")
        self.assertEqual(1, len(problems))

    def test_the_required_runners_are_named_here_not_read_from_the_file(self):
        # Reading them out of the file under test would make the rule agree
        # with whatever the file happened to say.
        self.assertEqual(
            ("ubuntu-latest", "windows-latest"), workflows.REQUIRED_RUNNERS
        )


class TheSuiteTheMatrixRunsContainsThePinnedDigests(unittest.TestCase):
    """The matrix is only evidence for tests the matrix actually runs."""

    PINNED = (
        ("tests/unit/test_canonical.py", "CrossPlatformDeterminism"),
        ("tests/unit/test_canonical.py", "ShippedScopeContractsHashIdentically"),
    )

    def test_the_pinned_digest_classes_load_from_where_the_suite_looks(self):
        # Loaded by name rather than by re-running discovery. A full discover
        # inside a test re-imports every module in the repository and tripled
        # the suite, which would have cost that on both runners for an
        # assertion that can be made against two modules.
        import unittest as ut

        for relative, class_name in self.PINNED:
            with self.subTest(class_name=class_name):
                module = relative[: -len(".py")].replace("/", ".")
                loaded = ut.defaultTestLoader.loadTestsFromName(
                    "%s.%s" % (module, class_name)
                )
                self.assertGreater(loaded.countTestCases(), 0)

    def test_the_pinned_digest_files_sit_under_the_discovery_root(self):
        _name, block = workflows.suite_job(workflow_text())
        self.assertIn("-s tests", block)
        self.assertIn('-p "test_*.py"', block)
        for relative, _class_name in self.PINNED:
            with self.subTest(path=relative):
                self.assertTrue(relative.startswith("tests/"), relative)
                self.assertTrue(
                    os.path.basename(relative).startswith("test_"), relative
                )
                self.assertTrue(
                    os.path.exists(
                        os.path.join(REPO_ROOT, relative.replace("/", os.sep))
                    ),
                    relative,
                )

    def test_this_file_sits_where_the_workflow_looks(self):
        _name, block = workflows.suite_job(workflow_text())
        self.assertIn("-s tests", block)
        self.assertIn('-p "test_*.py"', block)
        here = os.path.abspath(__file__)
        self.assertTrue(
            here.startswith(os.path.join(REPO_ROOT, "tests") + os.sep), here
        )
        self.assertTrue(os.path.basename(here).startswith("test_"), here)


class PlatformVaryingValuesArePinned(unittest.TestCase):
    """Values whose spelling depends on the running platform.

    `os.sep` and `os.linesep` differ between the two runners. Nothing in the
    pipeline is allowed to choose them, so the digests below are pinned. A
    change that let the platform decide would move one of these on one leg.
    """

    VECTORS = [
        (
            {"path": "a\\b\\c"},
            b'{"path":"a\\\\b\\\\c"}',
            "e1259687c61025b2abef9dfcd4f80b0c955270f592f1f1bc7ec35291a4bb920b",
        ),
        (
            {"path": "a/b/c"},
            b'{"path":"a/b/c"}',
            "b0bb36063beff86f9be05d097c2aa7a0f9f3145b982d3650bd75549cdc4fd7a1",
        ),
        (
            {"body": "a\r\nb"},
            b'{"body":"a\\r\\nb"}',
            "a5004d9c1671db56f0c867a38cadf9ddc32f8c73ab3b99fb0cfee677c3802739",
        ),
    ]

    def test_every_vector_produces_its_recorded_bytes_and_digest(self):
        for document, expected_bytes, expected_digest in self.VECTORS:
            with self.subTest(document=document):
                self.assertEqual(expected_bytes, canonical.canonicalise(document))
                self.assertEqual(expected_digest, canonical.digest(document))

    def test_the_recorded_digests_are_sha256_of_the_recorded_bytes(self):
        for _document, expected_bytes, expected_digest in self.VECTORS:
            with self.subTest(expected_bytes=expected_bytes):
                self.assertEqual(
                    hashlib.sha256(expected_bytes).hexdigest(), expected_digest
                )

    def test_a_carriage_return_is_not_silently_translated(self):
        # The control. If some layer normalised newlines on the way in, these
        # two would collapse and a document would hash the same as a different
        # document, which is the failure the pins above cannot see on their own.
        self.assertNotEqual(
            canonical.digest({"body": "a\r\nb"}), canonical.digest({"body": "a\nb"})
        )

    def test_a_separator_is_not_silently_translated(self):
        self.assertNotEqual(
            canonical.digest({"path": "a\\b"}), canonical.digest({"path": "a/b"})
        )

    def test_the_running_platform_never_supplies_the_value(self):
        # Written with the literals rather than with os.sep, so the assertion
        # states one thing on both runners.
        self.assertEqual(
            canonical.digest({"path": "a" + "\\" + "b"}),
            canonical.digest({"path": "a\\b"}),
        )


class TheTreeDigestIsSeparatorInvariant(unittest.TestCase):
    """The one digest taken over raw bytes rather than a parsed document.

    `compute_tree_digest` walks a directory, so the relative paths it feeds
    into the hash are spelled by the filesystem. It calls `as_posix()` for
    exactly this reason. The constant below is what makes that load-bearing:
    it was produced on one platform and must be reproduced on the other.
    """

    EXPECTED = "a435f6ab9f83f2385cc9554d17f61bbb9b7ed1276ea8b85d0e3dfa852275ed8e"

    FILES = (
        (("top.txt",), b"alpha\n"),
        (("nested", "mid.txt"), b"beta\n"),
        (("nested", "deeper", "leaf.txt"), b"gamma\n"),
    )

    def build(self):
        root = tempfile.mkdtemp(prefix="neg_j_tree_")
        self.addCleanup(__import__("shutil").rmtree, root, True)
        for parts, content in self.FILES:
            path = os.path.join(root, *parts)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(content)
        return pathlib.Path(root)

    def test_a_nested_tree_reproduces_the_pinned_digest(self):
        self.assertEqual(
            self.EXPECTED, verify_upstream.compute_tree_digest(self.build())
        )

    def test_the_pin_matches_an_independent_computation(self):
        # Rebuilt here from the documented framing rather than by calling the
        # implementation, so a change to both at once cannot pass unnoticed.
        digest = hashlib.sha256()
        for relative, content in (
            ("nested/deeper/leaf.txt", b"gamma\n"),
            ("nested/mid.txt", b"beta\n"),
            ("top.txt", b"alpha\n"),
        ):
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(len(content)).encode("ascii"))
            digest.update(b"\0")
            digest.update(content)
        self.assertEqual(self.EXPECTED, digest.hexdigest())

    def test_the_digest_covers_the_nested_paths_not_only_the_names(self):
        # The control. If only basenames were hashed, moving a file between
        # directories would not move the digest, and the pin above would still
        # hold on both platforms while meaning less than it claims.
        root = self.build()
        moved = root / "moved.txt"
        (root / "nested" / "deeper" / "leaf.txt").rename(moved)
        self.assertNotEqual(
            self.EXPECTED, verify_upstream.compute_tree_digest(root)
        )


if __name__ == "__main__":
    unittest.main()

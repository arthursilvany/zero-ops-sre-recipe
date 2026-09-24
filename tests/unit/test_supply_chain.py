"""The dependency closure is pinned, and the pin can be shown to fail.

SEC-005 is about third-party code reaching the operator workstation, inside the
component that computes the scope-contract hash. A lock file that has only ever
been observed to pass is not known to be a control, so roughly half of this
module feeds the verifier deliberately broken input and asserts it objects.
"""

import json
import os
import re
import unittest

from supply_chain import generate_lock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCK = os.path.join(REPO_ROOT, "tools", "requirements.lock")
DECLARATION = os.path.join(REPO_ROOT, "tools", "supply-chain.json")
CONTRIBUTING = os.path.join(REPO_ROOT, "CONTRIBUTING.md")
WORKFLOW = os.path.join(REPO_ROOT, ".github", "workflows", "verify.yml")

HASH_LINE = re.compile(r"^--hash=sha256:[0-9a-f]{64}$")


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def declaration():
    return json.loads(read(DECLARATION))


def write_lock(tmpdir, text):
    path = os.path.join(tmpdir, "requirements.lock")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


class CommittedLockHolds(unittest.TestCase):
    def test_lock_exists(self):
        self.assertTrue(
            os.path.isfile(LOCK),
            "tools/requirements.lock is missing, so nothing pins the tree.",
        )

    def test_verifier_accepts_the_committed_lock(self):
        self.assertEqual([], generate_lock.verify_lock(declaration(), lock_file=LOCK))

    def test_every_reviewed_package_is_pinned_at_the_reviewed_version(self):
        pinned = generate_lock.parse_lock(read(LOCK))
        for package in declaration()["packages"]:
            self.assertIn(package["name"], pinned)
            self.assertEqual(package["version"], pinned[package["name"]][0])

    def test_nothing_is_pinned_that_was_never_reviewed(self):
        pinned = set(generate_lock.parse_lock(read(LOCK)))
        reviewed = {p["name"] for p in declaration()["packages"]}
        self.assertEqual(set(), pinned - reviewed)

    def test_every_package_carries_at_least_one_hash(self):
        for name, (_version, hashes) in generate_lock.parse_lock(read(LOCK)).items():
            self.assertTrue(hashes, "%s carries no hash" % name)

    def test_every_hash_is_a_well_formed_sha256(self):
        for line in read(LOCK).splitlines():
            stripped = line.strip().rstrip("\\").strip()
            if stripped.startswith("--hash"):
                self.assertRegex(stripped, HASH_LINE)

    def test_no_source_distribution_is_referenced(self):
        # An sdist runs its build at install time, which is the arbitrary code
        # execution ADR-0004 rules out.
        self.assertNotIn(".tar.gz", read(LOCK))
        self.assertNotIn(".zip", read(LOCK))

    def test_the_compiled_member_is_pinned_for_every_supported_platform(self):
        spec = declaration()
        expected = len(spec["pythonTags"]) * len(spec["platformTags"])
        _version, hashes = generate_lock.parse_lock(read(LOCK))["rpds-py"]
        self.assertEqual(
            expected,
            len(hashes),
            "rpds-py ships platform-specific binaries. One hash per supported "
            "python and platform pair is what makes an unlisted platform fail "
            "loudly instead of falling back to a source distribution.",
        )

    def test_the_header_names_both_load_bearing_flags(self):
        # An operator who copies the command without both flags gets an install
        # with no control and no warning, so the file has to say so itself.
        header = read(LOCK)
        self.assertIn("--require-hashes", header)
        self.assertIn("--only-binary=:all:", header)

    def test_the_lock_is_not_hand_editable_without_saying_so(self):
        self.assertIn("Do not edit by hand", read(LOCK))


class InterpreterFloorIsDerivedNotChosen(unittest.TestCase):
    def test_floor_is_at_least_every_package_requirement(self):
        self.assertEqual([], generate_lock.interpreter_floor_problems(declaration()))

    def test_floor_matches_the_strictest_member(self):
        spec = declaration()
        strictest = max(
            generate_lock._lower_bound(p["requiresPython"]) for p in spec["packages"]
        )
        self.assertEqual(
            strictest,
            generate_lock._lower_bound(">=" + spec["interpreterFloor"]),
            "The floor must equal the strictest member of the closure. A higher "
            "floor excludes interpreters for no recorded reason; a lower one "
            "resolves an older package silently.",
        )

    def test_the_floor_reason_is_recorded(self):
        self.assertTrue(declaration()["interpreterFloorReason"].strip())

    def test_a_floor_below_a_package_requirement_is_reported(self):
        spec = declaration()
        spec["interpreterFloor"] = "3.9"
        problems = generate_lock.interpreter_floor_problems(spec)
        self.assertTrue(problems)
        self.assertTrue(any("rpds-py" in p for p in problems))

    def test_an_unreadable_requirement_is_not_treated_as_no_floor(self):
        # Silently reading an unparseable specifier as "imposes nothing" is how
        # a package requiring a newer interpreter slips past the check.
        spec = declaration()
        spec["packages"][0] = dict(spec["packages"][0], requiresPython="~=3.11")
        self.assertTrue(generate_lock.interpreter_floor_problems(spec))

    def test_a_missing_requirement_is_not_treated_as_no_floor(self):
        spec = declaration()
        spec["packages"][0] = {
            k: v for k, v in spec["packages"][0].items() if k != "requiresPython"
        }
        self.assertTrue(generate_lock.interpreter_floor_problems(spec))

    def test_lower_bound_reads_the_supported_form(self):
        self.assertEqual((3, 11), generate_lock._lower_bound(">=3.11"))
        self.assertEqual((3, 0), generate_lock._lower_bound(">=3"))

    def test_lower_bound_refuses_forms_it_cannot_read(self):
        for specifier in ("~=3.11", ">3.11", "<4", "", None, "3.11"):
            with self.assertRaises(generate_lock.LockError):
                generate_lock._lower_bound(specifier)


class TheVerifierCanReject(unittest.TestCase):
    """Feed the verifier broken locks and assert it objects to each."""

    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        self.spec = declaration()
        self.text = read(LOCK)

    def assert_rejected(self, text, fragment):
        problems = generate_lock.verify_lock(
            self.spec, lock_file=write_lock(self.tmp, text)
        )
        self.assertTrue(problems, "the verifier accepted a lock it should reject")
        self.assertTrue(
            any(fragment in p for p in problems),
            "expected a problem mentioning %r, got %r" % (fragment, problems),
        )

    def test_a_bad_floor_is_reported_through_the_verifier_ci_runs(self):
        # CI calls verify_lock, not interpreter_floor_problems. Testing the
        # floor check only in isolation lets the wiring between them be removed
        # without any test noticing.
        self.spec["interpreterFloor"] = "3.9"
        problems = generate_lock.verify_lock(self.spec, lock_file=LOCK)
        self.assertTrue(problems)
        self.assertTrue(any("rpds-py" in p for p in problems))

    def test_a_missing_lock_is_reported(self):
        problems = generate_lock.verify_lock(
            self.spec, lock_file=os.path.join(self.tmp, "absent.lock")
        )
        self.assertTrue(problems)

    def test_a_package_absent_from_the_lock_is_reported(self):
        trimmed = [
            line
            for line in self.text.splitlines()
            if not line.startswith("attrs==")
        ]
        self.assert_rejected("\n".join(trimmed) + "\n", "attrs")

    def test_a_version_the_review_did_not_admit_is_reported(self):
        self.assert_rejected(
            self.text.replace("attrs==26.1.0", "attrs==25.0.0"), "attrs"
        )

    def test_a_package_nobody_reviewed_is_reported(self):
        extra = self.text + "leftpad==0.0.1 \\\n    --hash=sha256:%s\n" % ("a" * 64)
        self.assert_rejected(extra, "leftpad")

    def test_a_package_with_its_hashes_removed_is_reported(self):
        stripped = [
            line
            for line in self.text.splitlines()
            if "--hash" not in line
        ]
        self.assert_rejected("\n".join(stripped) + "\n", "no hash")

    def test_a_malformed_hash_is_reported(self):
        self.assert_rejected(
            re.sub(r"--hash=sha256:[0-9a-f]{64}", "--hash=sha256:dead", self.text, count=1),
            "malformed",
        )

    def test_a_hash_using_a_weaker_digest_is_reported(self):
        self.assert_rejected(
            re.sub(r"--hash=sha256:", "--hash=md5:", self.text, count=1), "malformed"
        )


class TheGeneratorRefusesToFallBack(unittest.TestCase):
    def test_a_source_distribution_is_never_selected(self):
        spec = declaration()
        urls = [
            {"packagetype": "sdist", "filename": "x-1.0.tar.gz"},
            {"packagetype": "bdist_wheel", "filename": "x-1.0-py3-none-any.whl"},
        ]
        selected = generate_lock.select_wheels(urls, spec)
        self.assertEqual(["x-1.0-py3-none-any.whl"], [w["filename"] for w in selected])

    def test_an_unsupported_platform_wheel_is_not_selected(self):
        spec = declaration()
        urls = [
            {
                "packagetype": "bdist_wheel",
                "filename": "x-1.0-cp311-cp311-musllinux_1_2_x86_64.whl",
            }
        ]
        self.assertEqual([], generate_lock.select_wheels(urls, spec))

    def test_an_unsupported_python_tag_is_not_selected(self):
        spec = declaration()
        urls = [
            {"packagetype": "bdist_wheel", "filename": "x-1.0-cp39-cp39-win_amd64.whl"}
        ]
        self.assertEqual([], generate_lock.select_wheels(urls, spec))

    def test_generation_refuses_a_floor_that_does_not_hold(self):
        spec = declaration()
        spec["interpreterFloor"] = "3.9"
        with self.assertRaises(generate_lock.LockError):
            generate_lock.generate(spec)


class TheClosureIsReviewed(unittest.TestCase):
    def test_every_package_records_why_it_is_admitted(self):
        for package in declaration()["packages"]:
            self.assertTrue(
                package.get("reason", "").strip(),
                "%s is in the closure with no recorded reason. A dependency "
                "nobody justified is one nobody decided to admit." % package["name"],
            )

    def test_every_package_declares_its_role(self):
        for package in declaration()["packages"]:
            self.assertIn(package.get("role"), ("direct", "transitive"))

    def test_exactly_one_package_is_a_direct_dependency(self):
        roles = [p["role"] for p in declaration()["packages"]]
        self.assertEqual(1, roles.count("direct"))

    def test_the_platform_list_records_why_it_is_short(self):
        self.assertTrue(declaration()["platformReason"].strip())


class NoInstallablePackageIsReintroduced(unittest.TestCase):
    def test_tools_carries_no_build_manifest(self):
        # Installing the tooling tree would run a build backend, so "executes no
        # code at install time" would stop being literally true. PYTHONPATH via
        # the bin/ shims is the only entry point.
        for manifest in ("pyproject.toml", "setup.py", "setup.cfg"):
            self.assertFalse(
                os.path.isfile(os.path.join(REPO_ROOT, "tools", manifest)),
                "tools/%s reintroduces an install path that was deliberately "
                "removed. See the lock header." % manifest,
            )


class TheDocumentedCommandCarriesBothFlags(unittest.TestCase):
    def test_contributing_documents_the_hash_pinned_install(self):
        text = read(CONTRIBUTING)
        self.assertIn("--require-hashes", text)
        self.assertIn("--only-binary=:all:", text)
        self.assertIn("tools/requirements.lock", text)

    def test_contributing_no_longer_documents_installing_the_tree(self):
        self.assertNotIn("pip install ./tools", read(CONTRIBUTING))

    def test_ci_installs_with_both_flags(self):
        text = read(WORKFLOW)
        self.assertIn("--require-hashes", text)
        self.assertIn("--only-binary=:all:", text)

    def test_ci_does_not_install_the_tooling_tree(self):
        self.assertNotIn("pip install --disable-pip-version-check ./tools", read(WORKFLOW))

    def test_ci_verifies_the_lock(self):
        self.assertIn("generate_lock.py --verify", read(WORKFLOW))


if __name__ == "__main__":
    unittest.main()

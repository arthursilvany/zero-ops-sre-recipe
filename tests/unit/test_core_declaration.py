"""The core declaration, the ignore rules and the documented structure.

Each of these three is the kind of control that looks fine until the day it
matters. A declaration nobody checks drifts; an ignore rule nobody tests is a
line of text; a documented path nobody verifies becomes a lie after the first
rename. Every assertion below is paired with a case proving the check can fail,
because a gate observed only to pass is not known to be a gate.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")

if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from zeroops import core_paths  # noqa: E402


def load_declaration():
    with open(os.path.join(REPO_ROOT, core_paths.DECLARATION_PATH), "r", encoding="utf-8") as handle:
        return json.load(handle)


def copy_declaration():
    return json.loads(json.dumps(load_declaration()))


class CoreDeclarationHolds(unittest.TestCase):
    def test_declaration_holds_against_this_repository(self):
        self.assertEqual([], core_paths.check(REPO_ROOT))

    def test_the_gate_sees_a_file_that_is_written_but_not_yet_staged(self):
        """A green result before `git add` would be a false green.

        The check enumerates files through git. With plain `ls-files` it sees
        only what is already staged or committed, so a contributor could write
        a new core file, run the gate, be told the declaration holds, and learn
        otherwise only after staging. The file is scanned while it is still
        untracked, which is when the author is actually looking at it.
        """
        import tempfile

        directory = os.path.join(REPO_ROOT, "contracts", "schemas")
        handle, path = tempfile.mkstemp(suffix=".probe.json", dir=directory)
        os.close(handle)
        relative = os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")
        try:
            self.assertIn(relative, core_paths.tracked_files(REPO_ROOT))
        finally:
            os.remove(path)

    def test_the_gate_ignores_a_file_git_would_ignore(self):
        """Widening the scan must not drag in files that are never committed."""
        import tempfile

        handle, path = tempfile.mkstemp(suffix=".pyc", dir=REPO_ROOT)
        os.close(handle)
        relative = os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", relative],
            cwd=REPO_ROOT, capture_output=True, text=True,
        ).returncode == 0
        try:
            if not ignored:
                self.skipTest("%s is not ignored by this repository" % relative)
            self.assertNotIn(relative, core_paths.tracked_files(REPO_ROOT))
        finally:
            os.remove(path)

    def test_declaration_validates_against_its_own_schema(self):
        from jsonschema import Draft202012Validator

        with open(os.path.join(REPO_ROOT, core_paths.SCHEMA_PATH), "r", encoding="utf-8") as handle:
            schema = json.load(handle)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(load_declaration())

    def test_every_planned_entry_names_the_task_that_materialises_it(self):
        """A planned path with no owner is permanent fiction, not a plan."""
        for category, entries in load_declaration()["categories"].items():
            for entry in entries:
                if entry["status"] == "planned":
                    self.assertIn(
                        "materialisedBy",
                        entry,
                        "%s in %s is planned but names no task" % (entry["path"], category),
                    )

    def test_named_tasks_exist_in_the_decomposition(self):
        """A reference to a task that was never written would not survive review."""
        tasks_path = os.path.join(
            REPO_ROOT, "docs", "features", "sre-agent-recipe-framework", "tasks.md"
        )
        with open(tasks_path, "r", encoding="utf-8") as handle:
            tasks = handle.read()
        for entries in load_declaration()["categories"].values():
            for entry in entries:
                task = entry.get("materialisedBy")
                if task:
                    self.assertIn(
                        task + " ",
                        tasks,
                        "%s names %s, which is not a task in tasks.md" % (entry["path"], task),
                    )

    def test_binding_is_declared_exactly_once(self):
        """FR-04 requires the binding layer enumerated; two homes is no home."""
        self.assertEqual(1, len(load_declaration()["categories"]["binding"]))

    def test_self_exclusions_are_exact_paths_not_patterns(self):
        """A pattern exclusion widens silently as the repository grows."""
        for exclusion in load_declaration()["selfExclusions"]:
            self.assertNotIn("*", exclusion["path"])
            self.assertFalse(exclusion["path"].endswith("/"))
            self.assertTrue(
                os.path.isfile(os.path.join(REPO_ROOT, exclusion["path"])),
                "%s is excluded from the FR-04 search but does not exist" % exclusion["path"],
            )


class CoreDeclarationCanFail(unittest.TestCase):
    """Each case removes one guarantee and asserts the check notices."""

    def test_undeclared_file_is_reported(self):
        stripped = copy_declaration()
        stripped["categories"]["tests"] = []
        problems = core_paths.check(REPO_ROOT, declaration=stripped)
        self.assertTrue(
            any("falls under no declared category" in p for p in problems),
            "removing a category did not make its files undeclared: %r" % problems,
        )

    def test_overlapping_categories_are_reported(self):
        overlapping = copy_declaration()
        overlapping["categories"]["repositoryMeta"].append(
            {"path": "tests/", "status": "present", "purpose": "deliberate conflict"}
        )
        problems = core_paths.check(REPO_ROOT, declaration=overlapping)
        self.assertTrue(
            any("more than one category" in p for p in problems),
            "a file owned by two categories was accepted: %r" % problems,
        )

    def test_runtime_identifier_in_a_core_path_is_reported(self):
        """The FR-04 check, exercised against a core file that violates it.

        deploy/upstream.lock names the upstream repository by design. Declaring
        it core is exactly the mistake FR-04 exists to catch.
        """
        planted = copy_declaration()
        planted["categories"]["frameworkOwned"] = [
            entry
            for entry in planted["categories"]["frameworkOwned"]
            if entry["path"] != "deploy/upstream.lock"
        ]
        planted["categories"]["core"].append(
            {"path": "deploy/upstream.lock", "status": "present", "purpose": "deliberate violation"}
        )
        problems = core_paths.check(REPO_ROOT, declaration=planted)
        self.assertTrue(
            any("runtime-specific identifier" in p for p in problems),
            "a core path naming the upstream runtime was accepted: %r" % problems,
        )

    def test_a_self_exclusion_does_not_silence_other_files(self):
        """The exclusion list must exempt only what it names."""
        planted = copy_declaration()
        planted["selfExclusions"].append(
            {"path": "deploy/upstream.lock", "reason": "deliberate over-exclusion"}
        )
        planted["categories"]["frameworkOwned"] = [
            entry
            for entry in planted["categories"]["frameworkOwned"]
            if entry["path"] not in ("deploy/upstream.lock", "deploy/README.md")
        ]
        planted["categories"]["core"].extend(
            [
                {"path": "deploy/upstream.lock", "status": "present", "purpose": "excluded"},
                {"path": "deploy/README.md", "status": "present", "purpose": "not excluded"},
            ]
        )
        problems = core_paths.check(REPO_ROOT, declaration=planted)
        reported = [p for p in problems if "runtime-specific identifier" in p]
        self.assertTrue(reported, "the unexcluded sibling was not reported: %r" % problems)
        self.assertTrue(all("upstream.lock" not in p for p in reported))

    def test_present_path_that_is_absent_is_reported(self):
        broken = copy_declaration()
        broken["categories"]["repositoryMeta"].append(
            {"path": "no-such-file.md", "status": "present", "purpose": "deliberate absence"}
        )
        problems = core_paths.check(REPO_ROOT, declaration=broken)
        self.assertTrue(any("absent from the repository" in p for p in problems))

    def test_planned_path_that_already_exists_is_reported(self):
        stale = copy_declaration()
        for entry in stale["categories"]["tests"]:
            if entry["path"] == "tests/":
                entry["status"] = "planned"
                entry["materialisedBy"] = "T1.01"
        problems = core_paths.check(REPO_ROOT, declaration=stale)
        self.assertTrue(
            any("already exists" in p for p in problems),
            "a stale 'planned' status was accepted: %r" % problems,
        )

    def test_empty_runtime_identifier_list_is_rejected_by_the_schema(self):
        """An empty forbidden-term list would make the FR-04 check vacuous."""
        from jsonschema import Draft202012Validator, ValidationError

        with open(os.path.join(REPO_ROOT, core_paths.SCHEMA_PATH), "r", encoding="utf-8") as handle:
            schema = json.load(handle)
        vacuous = copy_declaration()
        vacuous["runtimeIdentifiers"] = []
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(vacuous)


class IgnoreRulesCoverTheUpstreamSecretsFile(unittest.TestCase):
    """FR-49 requires these rules on day one, and a test that they work.

    The assertion runs git against the real ignore rules rather than reading
    .gitignore as text, because what protects the repository is git's decision,
    not the presence of a line that looks like it should produce it.
    """

    def assert_ignored(self, relative_path):
        result = subprocess.run(
            ["git", "check-ignore", "-v", "--no-index", relative_path],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            0,
            result.returncode,
            "%s is NOT ignored; a push could carry it. %s" % (relative_path, result.stdout),
        )

    def assert_not_ignored(self, relative_path):
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", relative_path],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            1,
            result.returncode,
            "%s is ignored, which would silently drop committed content" % relative_path,
        )

    def test_upstream_connector_secrets_file_is_ignored(self):
        self.assert_ignored("connectors.secrets.env")

    def test_upstream_connector_secrets_file_is_ignored_at_any_depth(self):
        """The upstream tree is fetched, not vendored, so it can land anywhere."""
        self.assert_ignored("deploy/compose/recipes/minimal/connectors.secrets.env")
        self.assert_ignored("some/nested/path/custom.secrets.env")

    def test_upstream_assembled_parameter_files_are_ignored(self):
        self.assert_ignored(".parameters.json")
        self.assert_ignored(".extras.json")

    def test_discovery_output_is_ignored(self):
        self.assert_ignored(".zeroops/discovery.json")
        self.assert_ignored("wizard/run.discovery.json")

    def test_committed_paths_are_not_ignored(self):
        """A rule broad enough to catch real content is its own kind of failure."""
        self.assert_not_ignored("bin/zeroops")
        self.assert_not_ignored("contracts/core-paths.json")
        self.assert_not_ignored("examples/minimal/framework-config.json")
        self.assert_not_ignored("deploy/upstream.lock")


class LineEndingPolicyCoversEmittedArtifacts(unittest.TestCase):
    def test_every_tracked_text_extension_has_an_eol_rule(self):
        with open(os.path.join(REPO_ROOT, ".gitattributes"), "r", encoding="utf-8") as handle:
            attributes = handle.read()

        result = subprocess.run(
            ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True
        )
        binary = (
            ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf",
            ".zip", ".gz", ".xlsx", ".docx", ".pptx", ".html",
        )
        extensions = set()
        for path in result.stdout.splitlines():
            _, ext = os.path.splitext(os.path.basename(path.strip()))
            if ext and ext.lower() not in binary:
                extensions.add(ext.lower())

        missing = [ext for ext in sorted(extensions) if ("*%s " % ext) not in attributes]
        self.assertEqual(
            [],
            missing,
            "tracked text extensions with no eol rule: %s" % ", ".join(missing),
        )

    def test_extensionless_shim_has_an_explicit_rule(self):
        """Extension rules cannot reach a file that has no extension."""
        with open(os.path.join(REPO_ROOT, ".gitattributes"), "r", encoding="utf-8") as handle:
            self.assertIn("bin/zeroops text eol=lf", handle.read())


class ContributingNamesOnlyRealPaths(unittest.TestCase):
    """NFR-25: documentation that names a path the repository does not have."""

    PATH_LIKE = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9._/-]*/[A-Za-z0-9._/-]*)`")

    def declared_paths(self):
        out = set()
        for entries in load_declaration()["categories"].values():
            for entry in entries:
                out.add(entry["path"].rstrip("/"))
        return out

    def test_every_path_named_in_contributing_exists_or_is_declared(self):
        with open(os.path.join(REPO_ROOT, "CONTRIBUTING.md"), "r", encoding="utf-8") as handle:
            text = handle.read()

        # The sentence naming the superseded layout is asserting those paths do
        # not exist, so it must not be read as a reference to them.
        text = text.replace(
            "There is no `src/`, `infra/`, `config/` or `terraform/` directory", ""
        )

        declared = self.declared_paths()
        unknown = []
        for match in self.PATH_LIKE.finditer(text):
            candidate = match.group(1).rstrip("/")
            if "://" in candidate:
                continue
            if os.path.exists(os.path.join(REPO_ROOT, candidate)):
                continue
            if candidate in declared:
                continue
            # A parent of a declared path is itself named honestly: CONTRIBUTING
            # describes 'core/' while the declaration is finer-grained.
            if any(path.startswith(candidate + "/") for path in declared):
                continue
            unknown.append(candidate)

        self.assertEqual(
            [],
            sorted(set(unknown)),
            "CONTRIBUTING.md names paths that neither exist nor are declared: %s"
            % ", ".join(sorted(set(unknown))),
        )

    def test_the_superseded_structure_is_gone(self):
        """The old layout must not be reachable as guidance."""
        with open(os.path.join(REPO_ROOT, "CONTRIBUTING.md"), "r", encoding="utf-8") as handle:
            text = handle.read()
        # The one permitted mention is the sentence stating these do not exist.
        text = text.replace(
            "There is no `src/`, `infra/`, `config/` or `terraform/` directory", ""
        )
        for stale in ("`src/`", "`infra/`", "`config/`"):
            self.assertNotIn(
                stale, text, "CONTRIBUTING.md still points contributors at %s" % stale
            )


class SchemaIdentityIsUnique(unittest.TestCase):
    """FR-05, acceptance criterion 5 of US-1.

    The register already checks that every entry resolves to exactly one file.
    That is about names. This is about identity: two files under different
    names can still claim the same $id, and then whichever the resolver
    reaches first defines the schema while the other silently validates
    nothing.
    """

    def test_the_repository_declares_more_than_a_handful_of_schemas(self):
        """A count guard. If the sweep found nothing, every check below would
        pass by iterating an empty mapping."""
        mapping = core_paths.schema_ids(REPO_ROOT, core_paths.tracked_files(REPO_ROOT))
        self.assertGreaterEqual(len(mapping), 18)

    def test_every_schema_in_this_repository_declares_an_id(self):
        mapping = core_paths.schema_ids(REPO_ROOT, core_paths.tracked_files(REPO_ROOT))
        self.assertEqual([], sorted(p for p, i in mapping.items() if i is None))

    def test_no_two_schemas_claim_the_same_id(self):
        mapping = core_paths.schema_ids(REPO_ROOT, core_paths.tracked_files(REPO_ROOT))
        self.assertEqual({}, core_paths.duplicate_ids(mapping))

    def test_a_repeated_id_is_reported_with_both_paths(self):
        found = core_paths.duplicate_ids(
            {"a.schema.json": "urn:x", "b.schema.json": "urn:x", "c.schema.json": "urn:y"}
        )
        self.assertEqual({"urn:x": ["a.schema.json", "b.schema.json"]}, found)

    def test_distinct_ids_are_not_reported(self):
        """The control case. Without it a function that reported everything
        would satisfy the assertion above."""
        self.assertEqual(
            {}, core_paths.duplicate_ids({"a.schema.json": "urn:x", "b.schema.json": "urn:y"})
        )

    def test_a_missing_id_is_a_problem_rather_than_a_skip(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        with open(os.path.join(root, "nameless.schema.json"), "w", encoding="utf-8") as handle:
            json.dump({"type": "object"}, handle)
        problems = []
        core_paths.check_schema_ids(root, ["nameless.schema.json"], problems)
        self.assertEqual(1, len(problems))
        self.assertIn("declares no $id", problems[0])

    def test_two_files_sharing_an_id_are_reported(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        for name in ("one.schema.json", "two.schema.json"):
            with open(os.path.join(root, name), "w", encoding="utf-8") as handle:
                json.dump({"$id": "urn:zeroops:shared"}, handle)
        problems = []
        core_paths.check_schema_ids(root, ["one.schema.json", "two.schema.json"], problems)
        self.assertEqual(1, len(problems))
        self.assertIn("one.schema.json", problems[0])
        self.assertIn("two.schema.json", problems[0])

    def test_a_file_that_is_not_a_schema_is_not_inspected(self):
        mapping = core_paths.schema_ids(REPO_ROOT, ["README.md", "contracts/core-paths.json"])
        self.assertEqual({}, mapping)


class NoDirectoryHoldsOnlyAPlaceholder(unittest.TestCase):
    """NFR-24, acceptance criterion 10 of US-1.

    A keep-file exists so git will carry an empty directory. A directory that
    still needs one holds nothing, so the structure it suggests is a promise
    rather than a fact.
    """

    def test_this_repository_has_no_placeholder_only_directory(self):
        problems = []
        core_paths.check_no_placeholder_directories(
            core_paths.tracked_files(REPO_ROOT), problems
        )
        self.assertEqual([], problems)

    def test_a_directory_holding_only_a_keep_file_is_reported(self):
        problems = []
        core_paths.check_no_placeholder_directories(["core/binding/.gitkeep"], problems)
        self.assertEqual(1, len(problems))
        self.assertIn("core/binding", problems[0])

    def test_a_keep_file_beside_real_content_is_accepted(self):
        """The control case: the rule is about emptiness, not about the
        filename. A check that fired on the name alone would fail here."""
        problems = []
        core_paths.check_no_placeholder_directories(
            ["core/binding/.gitkeep", "core/binding/adapter.md"], problems
        )
        self.assertEqual([], problems)

    def test_every_recognised_placeholder_name_is_caught(self):
        for name in (".gitkeep", ".keep", "KEEP", "placeholder"):
            with self.subTest(name=name):
                problems = []
                core_paths.check_no_placeholder_directories(["somewhere/%s" % name], problems)
                self.assertEqual(1, len(problems))


class TheBindingCounterCheckCanFire(unittest.TestCase):
    """The second half of acceptance criterion 6 of US-1.

    check_runtime_identifiers asserts two things: no core path names a runtime
    identifier, and the binding layer names at least one. Only the first is
    exercised against the real repository, because core/binding/ is still
    declared planned and the function returns early when the binding layer is
    empty.

    An early return nothing reaches is indistinguishable from a check that was
    deleted. These cases run the same function against a synthetic repository
    where the binding layer does exist, so the counter-check is known to work
    before the slice that turns it on arrives.
    """

    TERM = "acme-runtime"

    def declaration(self):
        return {
            "categories": {
                "core": [{"path": "core/policy/", "status": "present", "purpose": "x"}],
                "binding": [{"path": "core/binding/", "status": "present", "purpose": "x"}],
            },
            "runtimeIdentifiers": [{"term": self.TERM, "reason": "synthetic"}],
            "selfExclusions": [],
        }

    def root_with(self, contents):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        for relative, text in contents.items():
            full = os.path.join(root, relative.replace("/", os.sep))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as handle:
                handle.write(text)
        return root

    def problems_for(self, contents):
        root = self.root_with(contents)
        problems = []
        core_paths.check_runtime_identifiers(
            root, sorted(contents), self.declaration(), problems
        )
        return problems

    def test_a_binding_naming_no_runtime_is_reported(self):
        problems = self.problems_for(
            {
                "core/policy/rules.md": "nothing specific here",
                "core/binding/adapter.md": "also nothing specific here",
            }
        )
        self.assertEqual(1, len(problems), problems)
        self.assertIn("core/binding/", problems[0])

    def test_a_binding_naming_the_runtime_is_accepted(self):
        """The control case. Without it, a counter-check that reported every
        binding would satisfy the assertion above."""
        problems = self.problems_for(
            {
                "core/policy/rules.md": "nothing specific here",
                "core/binding/adapter.md": "targets %s" % self.TERM,
            }
        )
        self.assertEqual([], problems)

    def test_a_core_file_naming_the_runtime_is_still_reported(self):
        """Both halves fire independently; a binding that satisfies the
        counter-check must not excuse a leak into core."""
        problems = self.problems_for(
            {
                "core/policy/rules.md": "targets %s" % self.TERM,
                "core/binding/adapter.md": "targets %s" % self.TERM,
            }
        )
        self.assertEqual(1, len(problems), problems)
        self.assertIn("core/policy/rules.md", problems[0])

    def test_an_empty_binding_layer_is_not_reported(self):
        """Why the real repository passes today. Stated so the difference
        between 'the binding is clean' and 'there is no binding yet' is
        recorded rather than inferred."""
        self.assertEqual([], self.problems_for({"core/policy/rules.md": "clean"}))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""NEG-E: no declared core path contains an instruction region.

This is the evidence for User Story 2 acceptance criterion 9, and the
structural half of CC-019. It is SEC-002.

The rule enforced is stronger than FR-55 asks: not that retrieved content fails
to reach an instruction region, but that no core path has one. A region that
does not exist cannot be filled, and checking flow instead would need a list of
every function that returns untrusted content, which is a list somebody has to
keep complete.

Every test here makes the check fail, and each pairs with a control that makes
it pass by changing only the thing under test.

Run with:
    python -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from zeroops import core_paths  # noqa: E402
from zeroops import instructions  # noqa: E402


def keys_of(document):
    return [name for name, _ in instructions.json_names(document)]


def names_of(source):
    return [name for name, _ in instructions.python_names(ast.parse(source))]


class TheRealRepositoryIsClean(unittest.TestCase):
    """The control for everything below, plus the proof it looked at something."""

    def setUp(self):
        self.root = core_paths.repo_root()
        self.files = core_paths.tracked_files(self.root)
        self.declaration = core_paths.load_declaration(self.root)

    def scan(self):
        return instructions.scan(self.root, self.files, self.declaration)

    def test_no_core_path_holds_an_instruction_region(self):
        problems, _ = self.scan()
        self.assertEqual([], problems)

    def test_the_scan_examined_core_json(self):
        # A scan of nothing returns no problems and is indistinguishable from a
        # clean repository. This is the assertion that separates the two.
        _, examined = self.scan()
        self.assertGreater(examined["json"], 0)

    def test_the_python_count_matches_what_is_actually_there(self):
        # Zero today: no core path is Python yet. Asserted against the tracked
        # files rather than hardcoded, so the day wizard/discovery/ lands the
        # count moves on its own instead of this test quietly staying true.
        _, examined = self.scan()
        chosen = instructions.scanned_paths(self.files, self.declaration)
        expected = len([p for p in chosen if p.lower().endswith(".py")])
        self.assertEqual(examined["python"], expected)

    def test_the_two_counts_are_reported_apart(self):
        # A single total would let the Python half fall to zero unnoticed.
        _, examined = self.scan()
        self.assertEqual(set(examined), {"json", "python"})


class EveryMarkerIsExercisedOnItsOwn(unittest.TestCase):
    """One minimal example per marker.

    The call-site check shipped with five of its eight markers never exercised
    alone, because every test used a realistic line and a realistic line trips
    several rules at once. Deleting a marker changed nothing observable.
    """

    EXAMPLES = {
        "prompt": "systemPrompt",
        "instruction": "agentInstruction",
        "instructions": "agentInstructions",
        "message": "systemMessage",
        "messages": "chatMessages",
    }

    def test_each_marker_has_an_example(self):
        self.assertEqual(set(self.EXAMPLES), instructions.MARKER_WORDS)

    def test_each_example_trips_only_its_own_marker(self):
        for marker, example in self.EXAMPLES.items():
            with self.subTest(marker=marker):
                self.assertEqual(instructions.marker_of(example), marker)

    def test_each_marker_carries_its_own_reason(self):
        reasons = [reason for _, reason in instructions.INSTRUCTION_MARKERS]
        self.assertEqual(len(set(reasons)), len(reasons))

    def test_every_reason_says_something(self):
        for word, reason in instructions.INSTRUCTION_MARKERS:
            with self.subTest(marker=word):
                self.assertGreater(len(reason), 40)

    def test_the_registry_has_no_duplicate_words(self):
        words = [word for word, _ in instructions.INSTRUCTION_MARKERS]
        self.assertEqual(len(set(words)), len(words))


class TheVocabularyWasChosenAgainstRealKeys(unittest.TestCase):
    """The rejected candidates, and the reason they were rejected.

    `content` and `text` are the obvious additions to this vocabulary, and both
    would fire on keys this repository already has. These tests keep the
    justification attached to the evidence, so a later contributor adding them
    finds out why rather than rediscovering it.
    """

    def test_content_hash_exists_and_is_clean(self):
        # It is also the mechanism NEG-F uses to keep retrieved content out of
        # the evidence manifest. A rule flagging it would flag the mitigation.
        path = os.path.join(
            REPO_ROOT, "contracts", "schemas", "evidence-manifest.schema.json"
        )
        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
        self.assertIn("contentHash", keys_of(document))
        self.assertIsNone(instructions.marker_of("contentHash"))

    def test_query_text_exists_and_is_clean(self):
        path = os.path.join(
            REPO_ROOT, "contracts", "schemas", "query-catalogue.schema.json"
        )
        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
        self.assertIn("queryText", keys_of(document))
        self.assertIsNone(instructions.marker_of("queryText"))

    def test_completed_at_is_clean_despite_looking_like_completion(self):
        self.assertIsNone(instructions.marker_of("completedAt"))

    def test_completion_is_not_a_marker(self):
        # Rejected on meaning, not collision: it names model output rather than
        # an instruction region.
        self.assertNotIn("completion", instructions.MARKER_WORDS)

    def test_no_marker_fires_on_any_key_this_repository_already_has(self):
        # The whole vocabulary against the whole core surface. If this fails,
        # a marker was added that flags something already committed, which
        # makes the check unshippable rather than strict.
        root = core_paths.repo_root()
        files = core_paths.tracked_files(root)
        declaration = core_paths.load_declaration(root)
        problems, _ = instructions.scan(root, files, declaration)
        self.assertEqual([], problems)


class StructureIsScannedAndProseIsNot(unittest.TestCase):
    """The load-bearing distinction, with the repository's own prose as proof.

    Two real files would be flagged by a text scan, and one of them is stating
    the rule this check enforces.
    """

    def read(self, *parts):
        with open(os.path.join(REPO_ROOT, *parts), "r", encoding="utf-8") as handle:
            return handle.read()

    def test_a_core_schema_really_does_say_instruction_in_prose(self):
        # If this sentence is ever removed the justification above loses its
        # example, and this test says so rather than letting the reasoning
        # drift away from the file it was drawn from.
        text = self.read("contracts", "schemas", "readiness-result.schema.json")
        self.assertIn("never an instruction for the agent", text)

    def test_the_declaration_really_does_say_instructions_in_prose(self):
        text = self.read("contracts", "core-paths.json")
        self.assertIn("authoring instructions", text)

    def test_those_files_are_scanned_and_still_pass(self):
        root = core_paths.repo_root()
        declaration = core_paths.load_declaration(root)
        chosen = instructions.scanned_paths(
            core_paths.tracked_files(root), declaration
        )
        self.assertIn("contracts/core-paths.json", chosen)
        self.assertIn("contracts/schemas/readiness-result.schema.json", chosen)

    def test_a_json_value_holding_the_word_is_not_a_finding(self):
        document = {"purpose": "Never an instruction for the agent. No prompt."}
        self.assertEqual([], [k for k in keys_of(document) if instructions.marker_of(k)])

    def test_the_same_word_as_a_key_is_a_finding(self):
        # The control. Without it the assertion above holds for a scanner that
        # found nothing anywhere.
        document = {"prompt": "Never an instruction for the agent."}
        found = [k for k in keys_of(document) if instructions.marker_of(k)]
        self.assertEqual(["prompt"], found)

    def test_a_python_string_literal_holding_the_word_is_not_a_finding(self):
        source = 'HELP = "build the prompt"\n# assemble the messages\n'
        self.assertEqual([], [n for n in names_of(source) if instructions.marker_of(n)])

    def test_the_same_word_as_a_bound_name_is_a_finding(self):
        source = "prompt = 'x'\n"
        found = [n for n in names_of(source) if instructions.marker_of(n)]
        self.assertEqual(["prompt"], found)

    def test_markdown_is_not_scanned(self):
        self.assertNotIn(".md", instructions.SCANNED_SUFFIXES)

    def test_a_core_markdown_file_is_not_selected(self):
        root = core_paths.repo_root()
        chosen = instructions.scanned_paths(
            core_paths.tracked_files(root), core_paths.load_declaration(root)
        )
        self.assertNotIn("contracts/schema-register.md", chosen)


class AJsonKeyAnywhereIsFound(unittest.TestCase):
    """Depth and arrays, because a rule that only reads the top level would
    pass on every schema in this repository, which nests everything."""

    def found(self, document):
        return [
            (name, trail)
            for name, trail in instructions.json_names(document)
            if instructions.marker_of(name)
        ]

    def test_a_top_level_key(self):
        self.assertEqual(1, len(self.found({"prompt": 1})))

    def test_a_nested_key(self):
        self.assertEqual(1, len(self.found({"a": {"b": {"systemPrompt": 1}}})))

    def test_a_key_inside_an_array(self):
        self.assertEqual(1, len(self.found({"a": [{"messages": []}]})))

    def test_a_key_under_defs_as_a_schema_would_nest_it(self):
        document = {"$defs": {"entry": {"properties": {"instructions": {}}}}}
        self.assertEqual(1, len(self.found(document)))

    def test_the_trail_locates_the_finding(self):
        found = self.found({"a": {"b": {"prompt": 1}}})
        self.assertEqual(("a", "b"), found[0][1])

    def test_a_clean_document_yields_nothing(self):
        self.assertEqual([], self.found({"schemaVersion": "1.0.0", "entries": []}))


class APythonNameOfAnyBindingKindIsFound(unittest.TestCase):
    """Each binding kind separately.

    A check that only read assignments would miss a function that accepts a
    prompt as a parameter, which is how an instruction region enters a module
    without ever being assigned in it.
    """

    def found(self, source):
        return [n for n in names_of(source) if instructions.marker_of(n)]

    def test_an_assignment(self):
        self.assertEqual(["prompt"], self.found("prompt = 'x'\n"))

    def test_an_annotated_assignment(self):
        self.assertEqual(["prompt"], self.found("prompt: str = 'x'\n"))

    def test_an_attribute_assignment(self):
        self.assertEqual(["systemPrompt"], self.found("o.systemPrompt = 'x'\n"))

    def test_a_function_parameter(self):
        self.assertEqual(["messages"], self.found("def f(messages):\n    pass\n"))

    def test_a_keyword_argument(self):
        self.assertEqual(["prompt"], self.found("f(prompt='x')\n"))

    def test_a_function_name(self):
        self.assertEqual(
            ["build_prompt"], self.found("def build_prompt():\n    pass\n")
        )

    def test_a_class_name(self):
        self.assertEqual(
            ["PromptBuilder"], self.found("class PromptBuilder:\n    pass\n")
        )

    def test_a_dict_literal_key(self):
        self.assertEqual(["messages"], self.found("d = {'messages': []}\n"))

    def test_a_tuple_unpacking_target(self):
        self.assertEqual(["prompt"], self.found("prompt, other = 1, 2\n"))

    def test_a_clean_module_yields_nothing(self):
        self.assertEqual([], self.found("RULES = ['deny']\ndef load(path):\n    pass\n"))

    def test_a_read_of_a_name_is_not_a_binding(self):
        # Reading an instruction region defined elsewhere is not what this rule
        # is about; a core path that has nowhere to put one cannot be handed
        # one either, because rule one denies it the means to fetch anything.
        self.assertEqual([], self.found("x = other.prompt\n"))

    def test_a_load_is_not_counted_a_second_time(self):
        # A mutant that also read Load-context names passed everything, because
        # no test looked at how many times one region was reported. Python
        # cannot read a name the module did not bind or import, so the binding
        # is already the finding and the load would only repeat it, once per
        # use, with the line that created it buried.
        self.assertEqual(
            ["prompt"], names_of("prompt = build()\nsend(prompt)\nsend(prompt)\n")
        )

    def test_an_imported_name(self):
        # `from x import prompt` binds prompt here with no assignment anywhere
        # in the module, so a rule that read only assignments would miss the
        # one way a core path can acquire a region without writing one.
        self.assertIn("prompt", names_of("from x import prompt\n"))

    def test_an_import_renamed_locally(self):
        # Both spellings are read. A rule that read only the local name could
        # be satisfied by renaming, and what the module reaches for is still a
        # prompt.
        found = names_of("from x import prompt as helper\n")
        self.assertIn("prompt", found)

    def test_a_module_imported_under_a_marker_name(self):
        self.assertIn("messages", names_of("import chatlib as messages\n"))

    def test_a_dotted_import_is_read_at_both_ends(self):
        # A mutant that took only one end of a dotted name passed everything,
        # because every other import here has one segment. Either end alone is
        # a rule with a way around it.
        self.assertIn("prompts", names_of("import prompts.loader\n"))
        self.assertIn("prompts", names_of("import loader.prompts\n"))

    def test_a_dotted_import_is_read_in_the_middle_too(self):
        self.assertIn("prompts", names_of("import a.prompts.loader\n"))

    def test_an_ordinary_import_is_clean(self):
        self.assertEqual([], self.found("import json\nfrom os import path\n"))


class NamesAreSplitIntoWords(unittest.TestCase):
    """Substring matching would need exceptions for completedAt and
    contentHash, and a rule with exceptions is a rule somebody maintains."""

    def test_camel_case(self):
        self.assertEqual(["system", "prompt"], instructions.words_of("systemPrompt"))

    def test_snake_case(self):
        self.assertEqual(["system", "prompt"], instructions.words_of("system_prompt"))

    def test_kebab_case(self):
        self.assertEqual(["system", "prompt"], instructions.words_of("system-prompt"))

    def test_screaming_snake_case(self):
        self.assertEqual(["system", "prompt"], instructions.words_of("SYSTEM_PROMPT"))

    def test_an_acronym_run_stays_together(self):
        self.assertEqual(["http", "prompt"], instructions.words_of("HTTPPrompt"))

    def test_digits_do_not_merge_words(self):
        self.assertEqual(["prompt", "2"], instructions.words_of("prompt2"))

    def test_a_word_that_merely_contains_a_marker_is_clean(self):
        # promptly is not a prompt. A substring rule would say it was.
        self.assertIsNone(instructions.marker_of("promptlyDone"))

    def test_a_marker_at_the_end_is_still_found(self):
        self.assertEqual("prompt", instructions.marker_of("agent_prompt"))

    def test_a_marker_at_the_start_is_still_found(self):
        self.assertEqual("prompt", instructions.marker_of("promptText"))


class TheGateRunsTheCheck(unittest.TestCase):
    """check-core is where this runs. A check wired nowhere is a function.

    Calling `scan` directly proves nothing about the gate: delete the call from
    `check()` and every test above still passes. These go through the real
    entry point.
    """

    def declaration(self):
        declaration = core_paths.load_declaration(REPO_ROOT)
        declaration["categories"]["core"] = [
            {"path": "core/policy/", "status": "present", "purpose": "synthetic"}
        ]
        declaration["categories"]["binding"] = [
            {"path": "core/binding/", "status": "present", "purpose": "synthetic"}
        ]
        return declaration

    def synthetic_repo(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, "core", "policy"))
        schema = os.path.join(root, core_paths.SCHEMA_PATH.replace("/", os.sep))
        os.makedirs(os.path.dirname(schema), exist_ok=True)
        shutil.copyfile(
            os.path.join(REPO_ROOT, core_paths.SCHEMA_PATH.replace("/", os.sep)),
            schema,
        )
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        return root

    def write(self, root, relative, text):
        full = os.path.join(root, relative.replace("/", os.sep))
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_the_gate_reports_a_planted_json_region(self):
        root = self.synthetic_repo()
        self.write(root, "core/policy/x.json", '{"systemPrompt": "you are"}')
        problems = core_paths.check(root=root, declaration=self.declaration())
        offending = [p for p in problems if "core/policy/x.json" in p]
        self.assertEqual(1, len(offending), problems)
        self.assertIn("systemPrompt", offending[0])

    def test_the_gate_reports_a_planted_python_region(self):
        root = self.synthetic_repo()
        self.write(root, "core/policy/x.py", "def build(messages):\n    pass\n")
        problems = core_paths.check(root=root, declaration=self.declaration())
        offending = [p for p in problems if "core/policy/x.py" in p]
        self.assertEqual(1, len(offending), problems)
        self.assertIn("messages", offending[0])

    def test_the_gate_accepts_a_clean_core_path(self):
        """The control. A gate reporting every core file would satisfy both
        assertions above."""
        root = self.synthetic_repo()
        self.write(root, "core/policy/x.json", '{"defaultDecision": "deny"}')
        problems = core_paths.check(root=root, declaration=self.declaration())
        offending = [p for p in problems if "core/policy/x.json" in p]
        self.assertEqual([], offending)

    def test_the_gate_does_not_flag_prose_in_a_core_path(self):
        root = self.synthetic_repo()
        self.write(
            root,
            "core/policy/x.json",
            '{"purpose": "A hint for a person, never an instruction for the agent."}',
        )
        problems = core_paths.check(root=root, declaration=self.declaration())
        offending = [p for p in problems if "core/policy/x.json" in p]
        self.assertEqual([], offending)

    def test_the_real_repository_passes_the_gate(self):
        self.assertEqual([], core_paths.check())


class TheContainmentArgumentRestsOnItsNeighbour(unittest.TestCase):
    """This check is one leg of three, and the other legs are not decoration.

    Retrieved content cannot reach an instruction region inside a core path
    because a core path cannot retrieve anything (NEG-H rule one) and has no
    region to fill (this check). If the first leg were unwired, this check
    would keep passing while the claim resting on it stopped being true, and
    nothing here would say so.
    """

    def test_the_invocation_rule_is_wired_into_the_same_gate(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, "core", "policy"))
        schema = os.path.join(root, core_paths.SCHEMA_PATH.replace("/", os.sep))
        os.makedirs(os.path.dirname(schema), exist_ok=True)
        shutil.copyfile(
            os.path.join(REPO_ROOT, core_paths.SCHEMA_PATH.replace("/", os.sep)),
            schema,
        )
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        with open(
            os.path.join(root, "core", "policy", "x.py"), "w", encoding="utf-8"
        ) as handle:
            handle.write("import subprocess\n")

        declaration = core_paths.load_declaration(REPO_ROOT)
        declaration["categories"]["core"] = [
            {"path": "core/policy/", "status": "present", "purpose": "synthetic"}
        ]
        declaration["categories"]["binding"] = []
        problems = core_paths.check(root=root, declaration=declaration)
        self.assertTrue(
            any("subprocess" in p for p in problems),
            "NEG-H's invocation rule is no longer wired into check-core, so "
            "NEG-E's containment argument no longer holds: a core path could "
            "retrieve content even though it has nowhere to put it.",
        )

    def test_both_checks_run_from_the_one_gate(self):
        source = os.path.join(REPO_ROOT, "tools", "zeroops", "core_paths.py")
        with open(source, "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "check":
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call):
                        name = getattr(inner.func, "id", None)
                        if name:
                            called.add(name)
        self.assertIn("check_call_sites", called)
        self.assertIn("check_instruction_regions", called)


class BadInputIsSkippedRatherThanReported(unittest.TestCase):
    """A file the scanner cannot read is not a finding.

    Reporting one would produce a problem whose cause is the scanner, and a
    reader chasing it looks for an instruction region that is not there.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "core", "policy"))
        self.declaration = {
            "categories": {
                "core": [{"path": "core/policy/"}],
                "binding": [],
            }
        }

    def write(self, name, text):
        with open(
            os.path.join(self.root, "core", "policy", name), "w", encoding="utf-8"
        ) as handle:
            handle.write(text)

    def test_malformed_json_is_skipped(self):
        self.write("x.json", "{not json")
        problems, examined = instructions.scan(
            self.root, ["core/policy/x.json"], self.declaration
        )
        self.assertEqual([], problems)
        self.assertEqual(0, examined["json"])

    def test_unparseable_python_is_skipped(self):
        self.write("x.py", "def (:\n")
        problems, examined = instructions.scan(
            self.root, ["core/policy/x.py"], self.declaration
        )
        self.assertEqual([], problems)
        self.assertEqual(0, examined["python"])

    def test_an_absent_file_is_skipped(self):
        problems, examined = instructions.scan(
            self.root, ["core/policy/gone.json"], self.declaration
        )
        self.assertEqual([], problems)
        self.assertEqual(0, examined["json"])

    def test_a_readable_file_is_still_counted(self):
        # The control: without it the three assertions above hold for a scanner
        # that counted nothing at all.
        self.write("good.json", '{"schemaVersion": "1.0.0"}')
        _, examined = instructions.scan(
            self.root, ["core/policy/good.json"], self.declaration
        )
        self.assertEqual(1, examined["json"])

    def test_a_readable_python_file_is_still_counted(self):
        # The Python control. No core path is Python today, so the real
        # repository exercises this half at zero, and zero is also what a
        # scanner that stopped counting Python would report. Only a synthetic
        # core path can tell the two apart.
        self.write("good.py", "limit = 3\n")
        _, examined = instructions.scan(
            self.root, ["core/policy/good.py"], self.declaration
        )
        self.assertEqual(1, examined["python"])


class OnlyCoreAndBindingAreScanned(unittest.TestCase):
    """tools/ holds the broker and the checks themselves, and this very module
    binds names like `marker_of`. Scanning framework-owned code would report
    the checker for describing what it checks."""

    def setUp(self):
        self.root = core_paths.repo_root()
        self.declaration = core_paths.load_declaration(self.root)
        self.chosen = instructions.scanned_paths(
            core_paths.tracked_files(self.root), self.declaration
        )

    def test_tools_are_not_scanned(self):
        self.assertEqual([], [p for p in self.chosen if p.startswith("tools/")])

    def test_tests_are_not_scanned(self):
        self.assertEqual([], [p for p in self.chosen if p.startswith("tests/")])

    def test_examples_are_not_scanned(self):
        self.assertEqual([], [p for p in self.chosen if p.startswith("examples/")])

    def test_core_is_scanned(self):
        self.assertTrue([p for p in self.chosen if p.startswith("contracts/")])

    def test_the_binding_category_is_scanned_too(self):
        # A mutant that scanned only the core category passed everything. The
        # binding layer is not reached by the core prefixes: the declaration
        # names core/policy/ and core/evidence/, never core/, so core/binding/
        # is selected by its own category or not at all. The binding layer
        # names the runtime, which is why it exists, and that is not a reason
        # to let it hold a prompt.
        declared = [e["path"] for e in self.declaration["categories"]["binding"]]
        self.assertTrue(declared)
        for prefix in declared:
            candidate = prefix + "emitted.json"
            self.assertEqual(
                [candidate], instructions.scanned_paths([candidate], self.declaration)
            )

    def test_a_region_planted_in_a_binding_path_is_reported(self):
        # Selection is not the whole claim: the finding has to come out.
        prefix = self.declaration["categories"]["binding"][0]["path"]
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        relative = prefix + "emitted.json"
        full = os.path.join(root, relative.replace("/", os.sep))
        os.makedirs(os.path.dirname(full))
        with open(full, "w", encoding="utf-8") as handle:
            json.dump({"systemPrompt": "you are"}, handle)
        problems, _ = instructions.scan(root, [relative], self.declaration)
        self.assertEqual(1, len(problems))
        self.assertIn("systemPrompt", problems[0])

    def test_this_test_file_would_be_a_finding_if_it_were_scanned(self):
        # Proof that the exclusion is doing work rather than being harmless:
        # this file binds names the rule refuses, and is not reported.
        with open(os.path.abspath(__file__), "r", encoding="utf-8") as handle:
            source = handle.read()
        found = [n for n in names_of(source) if instructions.marker_of(n)]
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()

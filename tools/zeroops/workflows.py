"""NEG-J: the claim that a digest is identical across platforms is a claim about CI.

Every pinned digest in this repository is a cross-platform assertion only
because the suite runs on more than one runner. A constant compared against
itself agrees on any machine; what makes it evidence is that two different
operating systems both had to reproduce it.

That property lives in a YAML file, and until this module existed nothing
checked it. Three separate test docstrings stated in prose that the suite runs
on `windows-latest` and `ubuntu-latest`. Deleting one of those runners would
have left every test passing while the cross-platform claim quietly became a
single-platform one, which is the same false green this project has now hit
fifteen times: a check that cannot distinguish its own absence from success.

Why a hand-written reader
-------------------------

The dependency closure is reviewed and pinned, and no YAML parser is in it.
Adding one to read four lines would widen the supply chain for a test, so the
reader here extracts only what the rule needs: the blocks under `jobs:`, and
whether a key appears inside one of them. It is not a YAML parser and does not
pretend to be. It is tested against synthetic documents rather than trusted,
because a reader that silently found nothing would make every rule below pass.

What this cannot defend
-----------------------

A test that asserts the suite runs on two runners is itself run by that suite.
If the job were deleted outright, nothing here would execute and nothing would
report it. Only a required status check can catch that, which is #36. The
boundary is named rather than papered over.
"""

import os
import re


WORKFLOW = ".github/workflows/verify.yml"

# The runners the pinned digests are evidence for. Both are named literally:
# reading them out of the file under test would make the rule agree with
# whatever the file happened to say.
REQUIRED_RUNNERS = ("ubuntu-latest", "windows-latest")

# The command whose presence makes the matrix mean something. A matrix that
# runs two copies of a job that does not run the suite proves nothing.
SUITE_COMMAND = "unittest discover"

MISSING_WORKFLOW = (
    "%s is missing. The cross-platform claim behind every pinned digest is a "
    "claim about this file, so a rule that could not read it would be "
    "asserting nothing while reporting success."
)
NO_JOBS = "%s declares no jobs. There is nothing here to run the suite."
NO_SUITE_JOB = (
    "no job in %s runs `%s`. Every pinned digest in this repository is "
    "evidence only because two operating systems reproduced it, and no job "
    "reproduces anything."
)
MISSING_RUNNER = (
    "the job that runs the suite does not name %r. A digest compared against "
    "itself agrees on any machine; what makes it evidence is that a second "
    "platform had to produce the same value."
)
NOT_MATRIX_BOUND = (
    "the job that runs the suite does not set `runs-on` from the matrix. A "
    "matrix that every leg ignores runs the same platform twice and reports "
    "two passes for one."
)
FAIL_FAST = (
    "the job that runs the suite leaves `fail-fast` on. The first leg to fail "
    "cancels the other, so a genuine disagreement between platforms would be "
    "reported as a cancellation rather than as the divergence it is."
)


def jobs(text):
    """Return the block of lines belonging to each job, keyed by job name.

    Indentation-based and deliberately small. `jobs:` sits at the left margin,
    each job name one level in, and everything more indented than the job name
    belongs to that job.
    """
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^jobs:\s*$", line):
            start = index + 1
            break
    if start is None:
        return {}

    found = {}
    name = None
    indent = None
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.startswith("#"):
            # Dropped rather than kept. A comment is not configuration, and a
            # job whose comment happened to mention the suite command would
            # otherwise be picked as the job that runs it.
            continue
        if not stripped:
            if name is not None:
                found[name].append(line)
            continue
        current = len(line) - len(line.lstrip())
        if current == 0:
            break
        header = re.match(r"^(\s+)([A-Za-z0-9_-]+):\s*$", line)
        if header and (indent is None or len(header.group(1)) == indent):
            indent = len(header.group(1))
            name = header.group(2)
            found[name] = []
            continue
        if name is not None:
            found[name].append(line)
    return {key: "\n".join(value) for key, value in found.items()}


def suite_job(text):
    """Return (name, block) for the job that runs the offline suite."""
    for name, block in jobs(text).items():
        if SUITE_COMMAND in block:
            return name, block
    return None, None


def runners_of(block):
    """Every runner label named in a job's matrix, in flow or block form."""
    found = []
    flow = re.search(r"^\s*os:\s*\[([^\]]*)\]", block, re.MULTILINE)
    if flow:
        found.extend(part.strip().strip("'\"") for part in flow.group(1).split(","))
    for match in re.finditer(r"^\s*-\s*([A-Za-z0-9._-]+)\s*$", block, re.MULTILINE):
        found.append(match.group(1))
    return [item for item in found if item]


def scan(root, files=None, declaration=None):
    """Return (problems, examined).

    `examined` counts workflows rather than reporting a total, so a run that
    stopped finding the file reports zero instead of reporting nothing and
    looking exactly like a clean one.
    """
    examined = {"workflows": 0}
    full = os.path.join(root, WORKFLOW.replace("/", os.sep))
    if not os.path.exists(full):
        return [MISSING_WORKFLOW % WORKFLOW], examined

    with open(full, "r", encoding="utf-8") as handle:
        text = handle.read()
    examined["workflows"] += 1

    if not jobs(text):
        return [NO_JOBS % WORKFLOW], examined

    name, block = suite_job(text)
    if block is None:
        return [NO_SUITE_JOB % (WORKFLOW, SUITE_COMMAND)], examined

    problems = []
    present = runners_of(block)
    for runner in REQUIRED_RUNNERS:
        if runner not in present:
            problems.append(MISSING_RUNNER % runner)

    if not re.search(r"runs-on:\s*\$\{\{\s*matrix\.os\s*\}\}", block):
        problems.append(NOT_MATRIX_BOUND)

    if not re.search(r"fail-fast:\s*false", block):
        problems.append(FAIL_FAST)

    return ["%s: job %r: %s" % (WORKFLOW, name, p) for p in problems], examined

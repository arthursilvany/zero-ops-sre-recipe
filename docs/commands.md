# Commands

Every command this repository offers today, in a form that can be pasted without
editing. Commands that do not exist yet are not listed here; they are recorded in
[`plan.md`](../features/sre-agent-recipe-framework/plan.md) against the work item that
creates each one (NFR-13, NFR-18).

## Prerequisites

Python 3.11 or later, and the pinned dependency closure. Nothing else. No Azure
subscription, no Azure CLI, no login.

```powershell
python -m pip install --require-hashes --only-binary=:all: -r tools/requirements.lock
```

Both flags are part of the control rather than decoration. `--require-hashes` makes pip
refuse anything whose hash is not in the lock. `--only-binary=:all:` makes it refuse a
source distribution, which would run a build script at install time. Dropping either one
removes the control while leaving the command looking the same.

The `zeroops` package itself is not installed. `bin/zeroops` and `bin/zeroops.ps1`
forward arguments to `python -m zeroops` with `tools/` on `PYTHONPATH`, so the only
third-party code reaching the machine is the closure above.

## Running the commands

```powershell
.\bin\zeroops.ps1 <command>
```

```bash
./bin/zeroops <command>
```

Set `ZEROOPS_PYTHON` if the interpreter is not on `PATH` as `python` (Windows) or
`python3` (everywhere else). The shims hold no logic of their own: any behaviour placed
in them would exist on one platform only, and the two would drift the first time either
was edited. Every example below is written with the PowerShell shim; substitute
`./bin/zeroops` on Linux and macOS.

## Validate a configuration

```powershell
.\bin\zeroops.ps1 validate examples\minimal\
```

Accepts either a directory or a single artifact. Given a directory, every artifact in it
is validated, and then the directory is validated as a set: a reference that names
nothing defined anywhere in it is a finding, which no per-artifact rule can reach.

Four levels run in order, each gated on the one before, because findings drawn from a
document whose shape is already wrong are noise that buries the fault:

| Level | Refuses |
|-------|---------|
| Version | A document written against a different version of the schema |
| Structural | A shape the schema does not admit |
| Semantic | A shape the schema admits and the contract does not, such as an observation period that ends before it starts |
| Set | A cross-document reference that resolves to nothing |

Exit codes: `0` valid, `1` rejected, `2` the command could not run.

```powershell
.\bin\zeroops.ps1 validate examples\minimal\ --strict
```

`--strict` turns Recommended-area warnings into failures. Off by default so a first
result stays reachable without authoring anything bespoke (CON-11); on in a production
readiness gate.

```powershell
.\bin\zeroops.ps1 validate examples\minimal\framework-config.json --schema contracts\schemas\framework-config.schema.json
```

`--schema` overrides schema selection. Selection is otherwise by filename, not by a field
inside the document: a document that names its own schema can name a laxer one, and that
would be the cheapest way to pass.

## Run the offline suite

```powershell
.\bin\zeroops.ps1 test --local
```

This is the command US-1's independent test calls for: a person on a machine with no
Azure login runs it and watches it pass. Three properties are enforced rather than
asserted:

- **Credential-free.** The suite runs in a child process with every credential-shaped
  variable removed from its environment, and the command prints which ones it removed. A
  test that quietly depends on an ambient token fails here instead of on a reviewer's
  machine, where the failure arrives far from its cause.
- **Offline.** Outbound sockets are refused inside the test process before anything of
  ours is imported. The scope is exactly that process: git is invoked by the core
  declaration checks and is not covered, which is stated rather than left to be
  discovered.
- **Non-vacuous.** Discovering zero tests is a failure, not an empty report. A suite that
  stopped being discovered looks identical to a suite that passed. The same applies to a
  single module: a file under the start directory that produces no test is reported by
  name, because a module that stops being collected lowers the count and fails nothing.

`--local` is required. There is one test mode today and it is the offline one; naming it
keeps a later mode that does reach a subscription from being run by accident.

Run it from inside a clone. Invoked elsewhere it refuses by name rather than finding no
tests and reporting success.

`--pattern` changes the discovery pattern. It defaults to `test_*.py` and exists for
narrowing a run during development, not for the gate.

## Run the release gate

```powershell
.\bin\zeroops.ps1 test --local --negative
```

`--negative` restricts the run to `tests/negative`, the guards whose failure means a
prohibition is gone rather than a feature being broken. This is the gate a release is
held against (FR-40, SC-06).

It inherits every property of the offline suite, which is the point: the gate needs no
credentials, no network and no Azure subscription, so it runs on any checkout of any
fork, including one belonging to somebody evaluating the framework before adopting it.

Two failure modes are refused rather than reported as success:

- A missing `tests/negative` directory is an error. A gate pointed at a directory
  somebody moved would pass having run nothing.
- A negative test module that exists but produces no test is an error, named. This is the
  way a guard realistically disappears: not deleted, but renamed, or emptied of its last
  test class, which lowers a total nobody was comparing against anything.

What a failure here means: reverting any single guard in this repository makes this
command fail, and the failure names the guard. That property is what the command is for,
and it is verified by mutation rather than assumed.

### Requiring the gate on the default branch

Running the gate in CI is not the same as requiring it. A fork adopting this framework
should also protect its default branch, otherwise a pull request can be merged while the
gate is red, and the gate becomes a report rather than a gate.

```powershell
gh api -X PUT repos/OWNER/REPO/branches/main/protection --input protection.json
gh api -X POST repos/OWNER/REPO/branches/main/protection/enforce_admins
```

`protection.json` lists every job name from `verify.yml` under
`required_status_checks.contexts`, with `strict` set to true so a branch must be current
with the default branch before it merges.

The second call is the one that matters and is easy to skip. Without it a repository
administrator still pushes straight past every required check, and the account doing the
merging in a small project is usually an administrator, so the protection applies to
nobody. Confirm it by attempting a direct push and reading the refusal:

```text
remote: error: GH006: Protected branch update failed for refs/heads/main.
remote: - 5 of 5 required status checks are expected.
```

A push that reports `Bypassed rule violations` and then succeeds means the checks are
configured but not enforced.

## Check the core declaration

```powershell
.\bin\zeroops.ps1 check-core
```

Checks `contracts/core-paths.json` against what is actually on disk, in both directions.
A declared path that is absent fails, and so does a file that exists and is declared
nowhere. Only the first direction is the obvious one; the second is the one that happens
by accident (FR-04, FR-61).

The same command carries the structural rules about what a declared core path may hold.
They live here rather than in commands of their own because a separate command is a step
somebody has to remember to add to CI, and the first time it is forgotten the build goes
green for a reason nobody chose.

| Rule | What fails |
|------|------------|
| No core path may invoke anything | A CLI call, an SDK call or a shell from a declared core path, whether or not the command looks like Azure (FR-52) |
| A brokered command may name only an allowed verb | A literal command list naming a verb outside the read-only set (FR-52) |
| No core path holds an instruction region | A JSON key or a Python name meaning prompt, instruction or message (FR-55, SEC-002) |
| No core schema leaves a way in | An object that is not closed, a property named for secret material, or a field that accepts arbitrary structure (FR-49, SEC-013) |
| An evidence entry cannot hold content | A property of `$defs/evidenceEntry` that admits text nobody constrained, an entry that does not record a content hash and a data classification, or a hash not made conditional on the observation state (FR-55, CC-019) |
| The operator page matches the policy it describes | A deny rule or an allowed capability class the page does not document, a prohibition the page states that the policy does not make, or a row with no guidance for the reader (FR-59) |

The three rules before the last are one argument in three legs. Retrieved content cannot
reach an instruction region inside a core path because a core path cannot retrieve
anything, has nowhere to put a prompt, carries no field able to hold one, and leaves no
place in the record where the thing itself could be written down instead of its hash.
Each leg fails for a different reason and none implies the others, which is why all of
them run from this one command.

The evidence rule is about shape rather than names. A vocabulary of content-sounding
property names was written and discarded: `contentHash`, `dataClassification`,
`queryText` and ten others collide with it and every one of them is correct. Outside the
entry the rule relaxes to bounding rather than closing, because a conclusion holds a
sentence somebody wrote. That bound is the named residual: a capped statement could still
hold an instruction, and it is safe only because no core path can retrieve anything to
put there.

Reading is deliberately narrow for the content rules. JSON object keys are read and
values are not; Python bound, imported and parameter names are read and string literals
are not; markdown is not read at all by those rules. Core files describe them in prose,
so a scanner reading prose would fail a schema for explaining its own compliance.

The last rule is the exception, and reads markdown on purpose. It compares
`docs/prohibited-actions.md` with `core/policy/tool-policy.json` in both directions,
because the page is what an operator reads when deciding whether to point the agent at a
subscription and they do not open the policy. The direction that matters most is the one
that looks fine in review: a prohibition still written on the page and no longer denied
by the policy. The page reads correctly and the promise is empty.

The page is written by hand rather than generated, because the column an operator
actually needs is *what to do instead*, and no generator produces that from a
justification written for a reviewer. The cost of that choice is drift, which is what
this rule removes. The rule also requires the guidance column to be non-empty, otherwise
the page would decay into the policy restated in Markdown and pass the comparison
forever. Naming the residual: that establishes somebody wrote guidance, not that the
guidance is good.

## Hash a document

```powershell
.\bin\zeroops.ps1 hash examples\minimal\scope-contract.json --hash-field canonicalHash
```

Prints the lowercase-hex SHA-256 over the RFC 8785 canonical form. `--hash-field` removes
a top-level field before hashing, so a document can carry its own digest and still
reproduce it. The same input produces the same digest on every platform, which is what
makes the evidence chain checkable by someone who was not there (FR-19, FR-23).

```powershell
.\bin\zeroops.ps1 hash examples\minimal\scope-contract.json --canonical
```

Prints the canonical bytes instead of the digest, for diffing two documents that should
hash alike and do not.

## Audit role definitions in a compiled template

```powershell
.\bin\zeroops.ps1 audit-roles main.json
```

Reads a compiled ARM template, the JSON output of the Bicep build, and fails unless every
role definition it can grant resolves to `core/policy/role-allow-list.json` (NEG-A,
FR-33, CC-009). It needs no credentials and opens no connection, so it runs in CI on
every change.

The audit is deliberately strict in four places:

| Situation | Verdict | Why |
|-----------|---------|-----|
| A role assignment with a `condition` | Judged as if it always deploys | The condition is a deployment-time value the audit cannot see. A Contributor grant behind `accessLevel == 'High'` is a grant the template can issue |
| A role taken from a parameter, or built with `format()` | Fails as unresolvable | Moving the identifier one indirection away must not be the cheapest way past the audit |
| A linked template | Fails as unauditable | Its grants are not in the output being read. Compile modules inline |
| A custom role definition | Fails | Its permissions are whatever the template says; only measured built-in roles are listed |

Beyond role assignments, any string anywhere in the template that names a role
definition is checked too, so an identifier passed into a nested template as a value, or
exposed as an output, is not outside the audit's view.

```powershell
.\bin\zeroops.ps1 audit-roles main.json --allow-list my-allow-list.json
```

`--allow-list` audits against another list, for reviewing a proposed change to it. The
gate uses the committed one.

Exit codes: `0` every role read-only, `1` rejected, `2` the template or the list could
not be read.

The audit judges the grants a template issues. It cannot see what a consumer-supplied
identity already holds elsewhere in the subscription; that is checked at preview and
after deployment (SEC-003).

## Lint the documentation

```powershell
npx --yes markdownlint-cli2 "**/*.md" "!.github/**" "!node_modules/**"
```

## What these commands never do

No command here reads a credential, contacts a subscription, or writes to one. The
read-only boundary is a property of the framework and not of an operator's discipline
(FR-41, CON-03). Commands that do reach Azure arrive with the work items that create
them, and each is listed in `plan.md` until it exists.

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
  stopped being discovered looks identical to a suite that passed.

`--local` is required. There is one test mode today and it is the offline one; naming it
keeps a later mode that does reach a subscription from being run by accident.

Run it from inside a clone. Invoked elsewhere it refuses by name rather than finding no
tests and reporting success.

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

The last two rules are two thirds of one argument. Retrieved content cannot reach an
instruction region inside a core path because a core path cannot retrieve anything, has
nowhere to put a prompt, and carries no field able to hold one. Each leg fails for a
different reason and none implies the others, which is why all of them run from this one
command.

Reading is deliberately narrow. JSON object keys are read and values are not; Python
bound, imported and parameter names are read and string literals are not; markdown is not
read at all. Core files describe these rules in prose, so a scanner reading prose would
fail a schema for explaining its own compliance.

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

## Lint the documentation

```powershell
npx --yes markdownlint-cli2 "**/*.md" "!.github/**" "!node_modules/**"
```

## What these commands never do

No command here reads a credential, contacts a subscription, or writes to one. The
read-only boundary is a property of the framework and not of an operator's discipline
(FR-41, CON-03). Commands that do reach Azure arrive with the work items that create
them, and each is listed in `plan.md` until it exists.

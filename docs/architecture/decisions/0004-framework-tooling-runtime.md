# Framework Tooling Runtime

**Status**: Accepted
**Date**: 2026-09-23
**Accepted**: 2026-09-23
**Depends on**: [0001 — Upstream Template Relationship](0001-upstream-template-relationship.md),
[0002 — Infrastructure as Code](0002-infrastructure-as-code.md),
[0003 — Guided Deployment Experience](0003-guided-deployment-experience.md)
**Amends**: ADR-0003, priority 5 ("no new runtime") — see *Relationship to ADR-0003*

## Context

ADR-0003 settles *what* the guided experience is: a CLI wizard extending the upstream
`new-agent` pattern, adding read-only Azure Resource Graph discovery and emitting a
schema-validated scope contract. It deliberately does not settle *what the tooling is
written in*.

That question is now blocking, because three v1 requirements are language decisions in
disguise:

- **FR-02, FR-05, FR-25, FR-27** — JSON Schema 2020-12 validation, offline, with
  unknown-property rejection reporting the offending property path. This needs a
  conformant 2020-12 validator, not a hand-rolled check.
- **FR-19, FR-23** — a byte-identical artifact across interactive and non-interactive
  runs, plus a canonical hash that recomputes to the same value. This needs deterministic
  serialization, which is a property of the chosen library and not of the language.
- **FR-41, NFR-12** — a local test suite that runs with no Azure access.

The framework also inherits a prerequisite set it did not choose. `source-analysis.md`
section 3.6 records what the upstream kit already demands of an operator: **Azure CLI,
`jq`, Python 3 with PyYAML, `curl`**, PowerShell 7+ for the PowerShell path, and
optionally `azd` and Terraform. Section 2.9 records that the single-customer reference
implementation already ships **Python validation helpers and a canonical JSON script**
among its fourteen scripts.

Two constraints bound the choice. **CON-11** requires a first useful read-only result in
one working session without writing code, which makes every added prerequisite a direct
cost. **CON-06** makes the operator workstation — which holds live Azure credentials
during discovery and deployment — the highest-privilege boundary in the system, so any
dependency tree installed there is a security surface, not just an ergonomic one.

## Priorities and Requirements (ordered)

1. **No new operator prerequisite** (blocking) — every additional runtime is paid on every
   adoption, by every customer, before the first result. This is CON-11 expressed as a
   constraint on tooling.
2. **Conformant JSON Schema 2020-12 validation with property-path error reporting**
   (blocking) — FR-02, FR-05, FR-27 are unimplementable without it.
3. **Deterministic, reproducible serialization and hashing** (blocking) — FR-19 and FR-23
   are verification-grade requirements; a library that reorders keys or varies escaping
   silently breaks them.
4. **Minimal, auditable dependency surface on the operator workstation** — CON-06.
5. **Cross-platform on Windows, macOS and Linux** — the persona set spans all three.
6. **Testability with no Azure access** — FR-41, NFR-12, and the negative-test release
   gate (FR-40, SC-06).
7. **Precedent in the reference sources** — ADR-0001 commits the framework to composing
   rather than re-inventing; the same logic applies to tooling patterns.

## Options Considered

### Option 1: Python 3, with thin Bash and PowerShell entry points

- **No new prerequisite**: **Meets fully, verified directly against the upstream kit.**
  Python 3 with PyYAML is not merely documented as a prerequisite — it is *enforced* by the
  exact entry points this framework extends. `bin/ps/New-Agent.ps1` line 55,
  `bin/ps/Deploy-Agent.ps1` line 72 and `bin/ps/Deploy-Tf.ps1` line 59 each call
  `Test-Prerequisites -IncludePython` and `exit 1` when it is absent, and
  `bin/check-prerequisites.sh` lines 15 to 21 check `python3` and `import yaml`
  unconditionally on the Bash path. Python is additionally used at runtime by `deploy.sh`,
  `diff-agent.sh` and `export-agent.sh` for YAML processing. An operator who cannot run
  Python already cannot run the upstream deployment path at all, so adopting it adds
  nothing.
- **2020-12 validation**: Meets. The `jsonschema` library implements Draft 2020-12 and
  exposes a JSON pointer path per error, which is exactly what FR-27 requires.
- **Deterministic serialization**: Meets. An RFC 8785 (JSON Canonicalization Scheme)
  implementation is available, and canonicalisation plus hashing is pinned explicitly in
  this ADR rather than left to library defaults.
- **Dependency surface**: Meets. Two runtime dependencies. Wheel-only, hash-pinned
  installation is available through pip.
- **Cross-platform**: Meets fully.
- **Testability**: Meets fully. `pytest` as a development-only dependency.
- **Precedent**: Meets fully. The reference implementation already carries Python
  validation helpers and a canonical JSON script.

### Option 2: Node.js and TypeScript

- **No new prerequisite**: **Fails.** Node is not in the upstream prerequisite set. It
  would be a net-new install for every operator, paid before the first result, against
  CON-11. The repository's existing `npx markdownlint-cli2` usage does not change this:
  that is a documentation gate run by maintainers and CI, never by a consuming operator.
- **2020-12 validation**: Meets, and better than any alternative — Ajv is the most
  complete 2020-12 implementation available in any ecosystem. This is the option's real
  and unmatched advantage.
- **Deterministic serialization**: Meets.
- **Dependency surface**: **Partially meets.** npm's transitive trees are large and
  lifecycle install scripts are the ecosystem's primary supply-chain attack vector. This
  lands on the workstation holding live Azure credentials. Mitigable with
  `npm ci --ignore-scripts`, but it is a surface Option 1 does not open at all.
- **Cross-platform, testability**: Meets fully.
- **Precedent**: Fails. Neither reference source uses Node for any lifecycle concern.

### Option 3: PowerShell only

- **No new prerequisite**: Partially meets. PowerShell 7+ is an upstream prerequisite only
  *for the PowerShell path*; the Bash path does not require it, so mandating it narrows
  the supported entry points rather than widening them.
- **2020-12 validation**: **Fails.** `Test-Json` schema support is version-dependent,
  incompletely conformant against 2020-12, and does not produce the property-path
  diagnostics FR-27 demands. This alone eliminates the option.
- **Deterministic serialization**: **Fails.** `ConvertTo-Json` does not guarantee key
  ordering, escaping or depth behaviour suitable for a hash input. FR-23 would rest on
  undefined behaviour.
- **Precedent**: Meets — upstream's PowerShell path is real and must stay supported.

### Option 4: Compiled binary in Go or Rust

- **No new prerequisite**: Meets at run time — a static binary has no runtime dependency.
- **Everything else**: **Fails on cost.** It introduces a build toolchain, a release and
  distribution mechanism, per-platform artifacts and a signing obligation, for a wizard
  and a validator. ADR-0003 rejected the equivalent argument for a standalone application
  as disproportionate; the same reasoning holds.

## Decision

**Python 3 is the framework tooling runtime.** The wizard, the validator, the scope
contract emitter and the local test suite are a single installable Python package.
Thin Bash and PowerShell entry points wrap it, preserving the dual-entry-point parity the
upstream kit already establishes. No behaviour lives in the entry points.

Priority 1 decides it. Python is already on the operator's machine for any upstream
deployment; Node is not. Under CON-11 — a first useful result in one session, for a
customer nobody has met before — "one fewer thing to install" is not an ergonomic
preference, it is the constraint.

Option 2's advantage is real and is recorded rather than dismissed: **Ajv is a better
2020-12 validator than anything available in Python.** It is not decisive because
`jsonschema` is conformant for the features this framework's schemas actually use, and
because the gap is a library-quality difference while the prerequisite gap is a structural
cost paid by every consumer forever.

### What this decision pins

These are not implementation details. FR-19 and FR-23 are unverifiable until each is
fixed, so they are settled here (closing security finding SEC-009):

| Concern | Decision |
|---|---|
| Canonicalisation | RFC 8785 JSON Canonicalization Scheme |
| Unicode normalisation | NFC, applied before canonicalisation |
| Digest algorithm | SHA-256 |
| Digest encoding | Lowercase hexadecimal |
| Self-exclusion | The hash field is removed from the document before the digest is computed over it |
| Line endings | The digest input is the canonical byte sequence with no trailing newline; emitted files use LF and are marked as such in `.gitattributes` |
| Determinism proof | A test asserts the same input yields the same digest on Windows and on Linux |

### What this decision pins about dependencies

Closing security finding SEC-005, which applies to any third-party tree on the operator
workstation regardless of which ecosystem it comes from:

- Runtime dependencies are minimised and enumerated: a JSON Schema 2020-12 validator and
  an RFC 8785 implementation. Test and lint dependencies are development-only and are
  never required to run the wizard or the validator.
- Dependencies are pinned with hashes and installed wheel-only, so no arbitrary code
  executes at install time.
- The Python major and minor version floor is pinned and tested in CI.
- Dependency drift and known-vulnerability alerting are CI gates; an unlocked or drifted
  dependency set fails the build.

### Relationship to ADR-0003

ADR-0003 scored its chosen option "Adoption friction: Meets fully. No new runtime." That
statement stands **only under this decision**. It was evaluated before the tooling runtime
was settled, and it would have become factually incorrect had a new runtime been selected.
This ADR makes the claim true rather than leaving it as an unexamined assumption.

### Consequences

- The repository gains a Python package as its single tooling artifact. Executable logic
  does not live in Bash or PowerShell; those remain argument-forwarding shims, which keeps
  behavioural parity between the two entry points structurally guaranteed rather than
  maintained by hand.
- `jq`, `curl` and PowerShell remain upstream's prerequisites for upstream's own scripts.
  This framework adds none of its own beyond Python, which was already there.
- The validator is the single implementation of FR-25, FR-27 and FR-28. Documentation must
  never describe a second, divergent way to validate.
- Because Python's validator is good but not best-in-class, schema authoring stays within
  broadly supported 2020-12 features. Exotic keyword combinations are avoided by
  convention, and the schema register records this.
- Node remains in the repository **for documentation linting only**, invoked through `npx`
  by maintainers and CI. It is never an operator prerequisite, and no framework behaviour
  may depend on it.
- Revisit if schema complexity outgrows `jsonschema`'s conformance, or if Python ceases to
  be an upstream prerequisite. Either would reopen Option 2 on new evidence.

## Acceptance Note

Accepted on 2026-09-23. The deciding evidence — that Python 3 is already an unavoidable
upstream prerequisite — was **verified directly against the upstream kit rather than taken
from the source analysis**. The verification is stronger than the summary suggested:
`-IncludePython` is passed by `New-Agent.ps1`, `Deploy-Agent.ps1` and `Deploy-Tf.ps1`, each
exiting non-zero without it, and the Bash prerequisite check is unconditional. `new-agent`
is the exact entry point ADR-0003 extends, so the dependency is already paid before this
framework runs any code.

One nuance is recorded rather than smoothed over: `Check-Prerequisites.ps1` gates the Python
check behind an `-IncludePython` switch, so Python is conditional *at the helper level* on
the PowerShell path. It is unconditional in practice only because every relevant caller
passes the switch. If a future upstream change stopped passing it, the premise of this ADR
would weaken, and the upgrade compatibility test required by ADR-0001 should therefore
assert that the prerequisite is still enforced.

## Implementation Notes

- Package layout is declared in the implementation plan: declarative artifacts stay in
  their layer directories (`contracts/`, `core/`, `wizard/`); executable tooling lives in
  one package so that the layer directories remain diffable evidence for SC-01.
- Route every Azure invocation through a single command broker restricted to a read-only
  verb allow-list, and fail the build on any call site outside it. This is what makes
  FR-11's `Automated` verification method achievable rather than aspirational, and closes
  security finding SEC-008.
- Emit errors that name the property path and the expected shape, never the supplied
  value, for any secret-bearing or identifier-bearing field (SEC-017).

## References

- `prd.md` — sections *Guided Deployment Experience*, *Testing and Quality Gates*
- [ADR-0001](0001-upstream-template-relationship.md),
  [ADR-0002](0002-infrastructure-as-code.md),
  [ADR-0003](0003-guided-deployment-experience.md)
- `docs/architecture/source-analysis.md` — sections 2.9, 3.6
- `docs/features/sre-agent-recipe-framework/spec.md` — FR-02, FR-05, FR-11, FR-19, FR-23,
  FR-25, FR-27, FR-28, FR-41, NFR-12, CON-06, CON-11
- `docs/features/sre-agent-recipe-framework/security-review-architecture.md` — SEC-005,
  SEC-008, SEC-009, SEC-017

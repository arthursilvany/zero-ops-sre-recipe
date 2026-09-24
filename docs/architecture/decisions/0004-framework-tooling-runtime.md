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
- **Dependency surface**: Meets. Two runtime dependencies (corrected to a five-package
  closure by the 2026-09-24 addendum). Wheel-only, hash-pinned
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

## Addendum, 2026-09-24: the measured dependency closure

Recorded during T1.05, when the closure was resolved against PyPI for the first time.
The decision is unchanged. Two statements made when it was accepted are not accurate,
and are corrected here rather than edited in place.

**The closure is five packages, not two.** The *Dependency surface* evaluation of Option 1
says "Two runtime dependencies", counting direct imports. The installed tree is:

| Package | Version | Role | requires_python | Wheels pinned |
|---------|---------|------|-----------------|---------------|
| `jsonschema` | 4.23.0 | direct | `>=3.8` | 1 |
| `attrs` | 26.1.0 | transitive | `>=3.9` | 1 |
| `jsonschema-specifications` | 2025.9.1 | transitive | `>=3.9` | 1 |
| `referencing` | 0.37.0 | transitive | `>=3.10` | 1 |
| `rpds-py` | 2026.6.3 | transitive | `>=3.11` | 15 |

The count matters because priority 4 is *auditable* surface, and what an auditor installs
is the closure, not the import list. The reviewed closure and the reason each package is
admitted now live in `tools/supply-chain.json`.

**One member is compiled.** `rpds-py` ships platform-specific binaries built from Rust,
without a stable ABI, so it needs one hash per supported interpreter and platform pair.
This sharpens the hash pin rather than weakening it: for the other four packages the hash
covers source an auditor can read, and for this one it is the only thing standing between
the operator workstation and a substituted binary. It is also why the platform list is
deliberately short, and why an unlisted platform fails the install loudly instead of
falling back to a source distribution.

**The interpreter floor is 3.11, and is derived rather than chosen.** It is the strictest
`requires_python` in the closure. An earlier floor of `>=3.10`, written before the closure
was measured, would have resolved an older `rpds-py` silently, which is precisely the
drift the lock exists to prevent. `generate_lock.py --verify` now fails the build if the
declared floor ever drops below what a member requires, so this class of error cannot
recur unnoticed.

**The tooling package is not installed.** The bullet above states that hash pinning means
"no arbitrary code runs at install time". Installing the project's own source tree would
run a build backend and break that property, so `tools/pyproject.toml` was removed: the
`bin/` shims put `tools/` on `PYTHONPATH`, and the only third-party code entering the
workstation is the closure above. The second runtime dependency anticipated here, an
RFC 8785 implementation, is still outstanding and is a T1.10 decision; if it is taken as a
dependency rather than written, this table and the lock must both be regenerated.
Resolved in T1.10: it was written rather than taken as a dependency, so the closure and
the lock are unchanged. See the next section.

**The RFC 8785 implementation is written here rather than taken as a dependency, and
covers a proven subset.** T1.05 left this open. The closure was deliberately held to five
packages, and the candidate on PyPI is a `0.1.x` release, single-maintainer, untouched
since 2024, which would sit on the same high-privilege boundary the hash pin exists to
protect. Against that, the input domain is fully controlled: every document this
canonicalises is validated first against closed schemas that admit only strings,
integers, booleans, null, arrays and objects. The one genuinely difficult part of
RFC 8785, ECMAScript number formatting for non-integral doubles, is therefore outside the
domain and is **not implemented**. A value that would need it is refused, not
approximated, and so is an integer beyond 2^53-1, which a JavaScript runtime could not
hold exactly. The closure therefore stays at five packages and the lock is unchanged.

Two further refusals follow the same principle, that a digest which is stable and wrong
is worse than one that stops: a JSON text naming the same member twice is rejected rather
than resolved by last-wins, and two keys that collide under NFC are reported rather than
silently merged, since either resolution would drop a value from the digest without
anyone noticing.

Conformance was checked against the reference implementation's published test vectors at
authoring time. Those files are not committed: their repository states no licence. The
committed cases are authored against RFC 8785 section 3.2 and carry literal expected
digests, independently confirmed with a non-Python SHA-256 implementation, so the two CI
runners cannot agree with themselves while disagreeing with each other.

One deviation from plain JCS is deliberate and is the normalisation this ADR already
pins: RFC 8785 does not normalise and requires pre-normalised input. Of the six reference
vectors, three match byte for byte, two differ **solely** because of the NFC step, which
was confirmed by re-running them with normalisation bypassed, and one is refused for
containing non-integral numbers.

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

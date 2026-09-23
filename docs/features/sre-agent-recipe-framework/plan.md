# Implementation Plan: Zero Ops SRE Agent Recipe Framework

**Feature**: `sre-agent-recipe-framework`
**Date**: 2026-09-23
**Status**: Draft
**Specification**: [spec.md](spec.md) v1.3
**Binds to**: [ADR-0001](../../architecture/decisions/0001-upstream-template-relationship.md),
[ADR-0002](../../architecture/decisions/0002-infrastructure-as-code.md),
[ADR-0003](../../architecture/decisions/0003-guided-deployment-experience.md),
[ADR-0004](../../architecture/decisions/0004-framework-tooling-runtime.md) (Accepted)
**Security review**: [security-review-architecture.md](security-review-architecture.md) —
`APPROVED_WITH_CONTROLS`

## Summary

Slices 1 and 2 of the `prd.md` delivery strategy are complete on disk. This plan covers
**Slices 3, 4 and 5**: building the contract and offline validation, then the deployment
composition and quality gates, then the reference workload, lifecycle procedures and
traceability.

One architecture decision was opened and resolved during planning — the framework tooling
runtime (ADR-0004, Proposed). The architectural security review returned
`APPROVED_WITH_CONTROLS` with no Critical findings and six High findings, none of which
reverses an accepted decision.

The plan's central correction, carried from that review: **the read-only guarantee derives
from the RBAC grant and the compiled ARM, not from the tool policy.** The tool policy is
retained as defence-in-depth, reconciled against the pinned runtime rather than assumed to
match it.

## State at the Start of This Plan

| Slice | Content | State |
|---|---|---|
| 1 | Initialization, preflight, envisioning, source inventory, initial requirements, gap and risk report | Complete |
| 2 | Minimum contract, architecture proposal, Infrastructure as Code matrix, ADRs, repository structure proposal | Complete, with two residual actions below |
| 3 | Contract, schemas, offline validation, minimal example | This plan |
| 4 | Guided experience, deployment composition, CI gates, security validation, documentation | This plan |
| 5 | Reference workload, integration validation, operations guidance, final traceability | This plan |

Two Slice 2 actions remained and blocked task decomposition. **Both are now closed:**

1. **ADR-0004 acceptance.** Accepted on 2026-09-23. It settles the tooling runtime
   and pins the canonicalisation and hashing rules without which FR-19 and FR-23 are not
   verifiable claims.
2. **Specification amendment.** The security review identified eleven requirements marked
   `Automated` that could not fail as written. They are listed in *Required Specification
   Amendments* below and landed in `spec.md` v1.3. A release gate built on an
   unfalsifiable requirement produces false assurance, which is worse than an
   acknowledged gap.

## Architecture Recap

Three layers, as established by ADR-0001 and detailed in
[`overview.md`](../../architecture/overview.md): a pinned upstream deployment layer that is
composed and never forked, a governance layer owned here, and a guided discovery layer
owned here. Consumer workload extensions sit outside all three.

### Refinement: declarative artifacts separated from executable tooling

`contracts/`, `core/` and `wizard/` hold declarative artifacts only. Executable tooling is
one installable Python package under `tools/`, with argument-forwarding entry points under
`bin/`.

This refines `overview.md` rather than departing from it, for one reason: SC-01 is measured
by diffing declared core paths, and a diff that mixes contract changes with implementation
churn is weaker evidence than one that does not. Keeping behaviour in a single package also
makes Bash and PowerShell parity structural instead of hand-maintained.

### Resulting structure

```text
.
├── bin/                          # argument-forwarding entry points, no behaviour
├── contracts/
│   ├── schemas/                  # JSON Schema 2020-12, single source of truth
│   ├── vocabulary/               # English identifiers with recorded provenance
│   └── core-paths.json           # the declared core; input to the SC-01 check
├── core/
│   ├── policy/                   # tool policy in capability classes
│   ├── evidence/                 # evidence manifest model
│   └── binding/                  # Azure SRE Agent binding; only home of agent.json
├── wizard/
│   ├── discovery/                # read-only Resource Graph query definitions
│   └── eligibility/              # published eligibility rules
├── tools/                        # the Python package: validator, wizard, emitter, broker
├── deploy/
│   ├── upstream.lock             # immutable commit digest plus fetched-tree digest
│   └── compose/                  # Bicep composition over pinned upstream modules
├── examples/
│   ├── minimal/                  # workload-neutral
│   └── reference-workload/       # AKS, placeholders only
├── extensions/README.md          # the extension contract; ships no content
├── tests/
│   ├── unit/
│   ├── validation/               # offline, credential-free
│   ├── negative/                 # release gate
│   └── azure/                    # requires a subscription; separated per FR-41
└── .github/workflows/
```

### Deviations from the structure proposed in `prd.md` — NFR-25

| Proposed | Actual | Reason |
|---|---|---|
| `infra/modules/`, `infra/environments/` | `deploy/compose/` | ADR-0001 composes pinned upstream modules; authoring modules here would be the duplication `prd.md` exists to prevent |
| `config/schemas/` | `contracts/schemas/` | FR-05 single source of truth, and CON-03 keeps the contract separable from its implementation |
| `src/agent/` | `core/binding/` | Runtime-specific content is confined to one named path so CON-03 is a check rather than a promise |
| `scripts/` | `tools/` plus `bin/` | One package with shims, so cross-platform parity is structural (ADR-0004) |
| `tests/{unit,integration,validation}` | `tests/{unit,validation,negative,azure}` | `negative` is named for what it proves; `azure` isolates subscription-requiring tests per FR-41 |
| `docs/getting-started/`, `docs/security/`, `docs/operations/`, `docs/examples/` | Created in Slices 4 and 5 when their first real artifact exists | NFR-24 forbids empty folders |
| (not proposed) | `extensions/` | The seam CON-11 depends on; ships a contract and no content |
| `terraform/` | Does not exist | CON-12 |

`CONTRIBUTING.md` currently references `src/`, `infra/` and `config/`. It is updated to the
settled structure in Slice 3, item S3-01.

## Required Specification Amendments

**Status: landed in `spec.md` v1.3 on 2026-09-23.** Each row below is now amended in the
specification, and decomposition is unblocked on this count. The table is retained as the
audit trail from finding to amendment. Each was a requirement that could not fail, which
means the gate built on it would have passed on false evidence. The
amendment belongs to the specification agent, not to this plan.

| Requirement | Amendment | Finding |
|---|---|---|
| FR-51, CC-021 | State RBAC as the authority for the read-only guarantee and the tool policy as defence-in-depth; add the runtime reconciliation gate as the verification | SEC-001 |
| FR-55, CC-019 | Split into a structural gating assertion, a containment gating assertion, and a measured non-gating injection-corpus result | SEC-002 |
| FR-33, CC-009 | Audit the agent principal's effective permissions across the subscription, not only grants on declared scopes | SEC-003 |
| FR-11 | Name the read-only command broker plus static call-site check as the automated mechanism | SEC-008 |
| FR-53, CC-012 | Reclassify as declared-not-enforced; verify through the post-deployment posture check | SEC-011 |
| FR-19, FR-23 | Reference ADR-0004's pinned canonicalisation, digest, encoding, self-exclusion, normalisation and newline rules | SEC-009 |
| CC-018 | Reframe as a static structural assertion over declared core paths | SEC-012 |
| FR-49 | Make structural — schema-level prevention — with scanning as corroboration | SEC-013 |
| NFR-01, NFR-04, SC-05 | Extend scanning to full git history; add push protection as a precondition | SEC-006 |
| SC-13 | Resolve the denylist disclosure paradox before the gate is designed | SEC-014 |
| SC-08 | Restate as a per-execution schema invariant, with sampling as corroboration | Review section 4 |

## Engineering Practices

No ADR is required for these. They are conventions derivable from `CONTRIBUTING.md`,
`SECURITY.md` and the accepted decisions, recorded here so they are reviewable.

| Practice | Decision | Reference |
|---|---|---|
| Branch strategy | Trunk-based off `main`; short-lived `feature/`, `fix/`, `docs/` branches; no direct pushes to `main` | `CONTRIBUTING.md` |
| Commits | Conventional Commits | `CONTRIBUTING.md` |
| Code review | Pull request required, linked to a specification or ADR, all gates green | `CONTRIBUTING.md` |
| CI/CD | GitHub Actions; all actions pinned by commit digest; least-privilege `permissions:` per workflow; federated credentials only, no long-lived secrets | SEC-015, NFR-14 |
| Infrastructure as Code | Bicep primary, composed from pinned upstream; ARM JSON compiled output only; no Terraform artifacts | ADR-0002, CON-12 |
| Tooling runtime | Python package, hash-pinned wheel-only dependencies, pinned interpreter floor | ADR-0004 |
| Secret management | External references only; platform secret scanning with push protection enabled; full-history scanning in CI | SEC-006, CON-06 |
| Observability of the framework itself | Out of scope. The framework defines observability consumers and contracts; it does not provision a telemetry pipeline | `spec.md` Non-Scope |
| Versioning | Semantic versioning with a changelog per release; breaking schema changes named explicitly | FR-69, NFR-21 |
| Documentation | Markdown linted to zero issues; every procedure step carries a command or an explicit manual marker | NFR-08, NFR-18 |

A DevSecOps or Infrastructure epic does not exist on the board. The CI gates in Slice 4 are
substantial enough to warrant one; creating it belongs to decomposition, not to this plan.

## Slice 3 — Contract, Schemas and Offline Validation

**Goal**: a consumer clones the repository with no Azure access, reads the contract, copies
the minimal example, edits it, and validates it. Nothing touches a subscription.

**Exit criterion**: User Story 1 passes end to end, credential-free. CC-001, CC-002,
CC-013, CC-022 pass.

| ID | Work item | Satisfies | Notes |
|---|---|---|---|
| S3-01 | Repository skeleton, core-path declaration, ignore rules, `.gitattributes` LF policy, `CONTRIBUTING.md` structure correction | FR-61, NFR-24, NFR-25 | `contracts/core-paths.json` is the input to the SC-01 check. Ignore rules cover the upstream secrets-file pattern on day one (SEC-013) |
| S3-02 | Full-history secret and identifier scanning, plus platform push protection | NFR-01, NFR-02, SC-05 | **Effective immediately, before any further commit.** A working-tree scan proves nothing about the repository that goes public (SEC-006) |
| S3-03 | English vocabulary with recorded provenance | FR-03 | Original reference values are provenance metadata, never identifiers |
| S3-04 | Author every schema in the register | FR-02, FR-05, FR-06, FR-24, FR-30 | Single location; `additionalProperties: false` throughout; no secret-shaped property (SEC-013) |
| S3-05 | Canonicalisation and hashing implementation | FR-23, FR-19 | Exactly as pinned by ADR-0004. Cross-platform determinism test (NEG-J) |
| S3-06 | Validator: structural, semantic, warning levels, path-named errors | FR-25, FR-27, FR-28 | Errors name path and shape, never the supplied value (SEC-017) |
| S3-07 | Read-only command broker plus static call-site check | FR-11, CON-02 | Makes FR-11's automated half real, and CON-02 mechanically true for the wizard (SEC-008) |
| S3-08 | Tool policy in capability classes, plus the binding-layer capability mapping marked unverified | FR-51, FR-52, FR-53 | The indirection that contains the unconfirmed-identifier open item |
| S3-09 | Offline negative tests | FR-40, FR-06, FR-56 | CC-016 to CC-022 plus NEG-D, NEG-E, NEG-F, NEG-H, NEG-I, NEG-J, NEG-K. Self-approval compares principal object identifiers (SEC-016) |
| S3-10 | `examples/minimal/`, workload-neutral | FR-26, FR-63 | CC-022 asserts no workload-type identifier |
| S3-11 | Zero-core-edit check | FR-60, SC-01 | Diffs an onboarding change against the declared core paths |
| S3-12 | Local test and validation commands, documented | FR-41, NFR-12 | Runs to completion with no Azure access |
| S3-13 | Pin upstream by immutable commit digest, record the fetched-tree digest, verify before execution | ADR-0001, NFR-06 | Tag-only pins are rejected in CI (SEC-004) |
| S3-14 | Resolve the customer-vocabulary denylist location | SC-13, NFR-03 | Blocks the sanitization gate design (SEC-014) |

## Slice 4 — Guided Experience, Deployment and Quality Gates

**Goal**: an operator discovers workloads, emits a scope contract, previews, deploys and
validates.

**Exit criterion**: User Stories 2 and 3 pass. CC-004 to CC-009 pass. The negative suite
gates the deployment path.

| ID | Work item | Satisfies | Notes |
|---|---|---|---|
| S4-01 | Eligibility rules, published and reported on an empty result | FR-12, FR-10 | The same rules the step reports when nothing is found |
| S4-02 | Discovery over a single subscription via read-only Resource Graph | FR-10, FR-11, FR-22 | Denied portions are reported as explicit access-denied states, never silently dropped |
| S4-03 | Discovery output hygiene | FR-17, NFR-01 | Ignored by default, headed as containing real identifiers, with a documented redaction mode (SEC-007) |
| S4-04 | Selection and field-allow-listed scope contract emission | FR-13, FR-14, FR-23 | Never copies a discovery row. NEG-G asserts a secret-shaped tag cannot reach the contract |
| S4-05 | Input collection, explanation and format validation | FR-15, FR-16 | No secret collected in plain text (FR-17) |
| S4-06 | Non-interactive parity and byte-identical output | FR-18, FR-19 | Covered by tests, not by documentation alone |
| S4-07 | Bicep composition over pinned upstream modules | FR-31, FR-34, FR-35, FR-36 | Compose and parameterize; never re-author (ADR-0002) |
| S4-08 | Preview, including every existing role held by a supplied principal | FR-20, FR-21, FR-33, FR-34 | NEG-B: a supplied principal holding any non-read role anywhere in the subscription blocks the preview until explicitly confirmed. Explicit confirmation required. Stale scope entries fail before provisioning (SEC-003) |
| S4-09 | Compiled-ARM role audit, offline | FR-33 | NEG-A. The authoritative read-only check, credential-free |
| S4-10 | Deployment idempotency and actionable failure messages | FR-32, FR-38 | Failing step, probable cause, recovery action |
| S4-11 | Post-deployment validation | FR-39, FR-43 | Fails when the principal holds any non-read role anywhere in the subscription. Distinguishes not-yet-effective from not-granted |
| S4-12 | Runtime capability reconciliation gate | FR-51, FR-54 | NEG-C: an advertised capability the policy does not classify fails the build. Until it runs against a real runtime, the policy stays documented as declared, not verified |
| S4-13 | Injection-corpus measurement, non-gating | NFR-05, CC-023 | Reported as a measured rate with evidence, never claimed as proof (FR-42 discipline) |
| S4-14 | CI quality gates | NFR-06, NFR-08 to NFR-14 | Markdown lint, link check, example validation, Bicep build and lint, static Infrastructure as Code analysis, unit tests, negative gate, command-consistency check, dependency drift |
| S4-15 | CI supply-chain hardening | SEC-015, NFR-14 | Digest-pinned actions, least-privilege permissions, federated credentials |
| S4-16 | Security model, configuration reference, deployment and validation guides | NFR-05, FR-54, FR-59, NFR-16 | The security model states RBAC as the authority and names the test covering each of the five threats |

## Slice 5 — Reference Workload, Operations, Lifecycle and Traceability

**Goal**: a second workload is onboarded with zero core edits, evidence is defensible, and
the deployment can be upgraded, rolled back and removed.

**Exit criterion**: User Stories 4, 5 and 6 pass. CC-010 to CC-015 and CC-C01 pass. The
Definition of Done in `prd.md` is satisfied or its gaps are explicitly recorded.

| ID | Work item | Satisfies | Notes |
|---|---|---|---|
| S5-01 | `examples/reference-workload/`, AKS with placeholders | FR-64, CON-04 | Added additively; produces no core diff |
| S5-02 | Evidence manifest production and validation | FR-44, FR-45, FR-46 | Entries carry a content hash and never the content. Unreachable sources produce an explicit unobserved state |
| S5-03 | Conclusion-to-evidence resolution as a schema invariant | FR-47, SC-08 | Per execution, not by sampling |
| S5-04 | Audit record and emitted-artifact scanning | FR-48, FR-49 | No secret, no raw workload payload |
| S5-05 | Query catalogue with integrity verification, shipped defaults separable from extensions | FR-50 | Arbitrary construction denied by policy |
| S5-06 | Extension guide and extension-point documentation | FR-62, NFR-20 | Inputs, outputs, and the guarantees that survive a core upgrade |
| S5-07 | Cleanup: complete, safe, idempotent, verified | FR-66, FR-67, NFR-23 | Removes only what the framework created |
| S5-08 | Rollback and upgrade procedures, exercised | FR-68, FR-70, NFR-22 | Executed at least once with the result recorded |
| S5-09 | Versioning and changelog | FR-69, NFR-21, CC-C01 | Breaking schema changes named; no lockstep upgrade |
| S5-10 | Operations and troubleshooting guide, ownership and escalation | FR-08, FR-09 | Includes the consumption limit and execution limits, with the action on reaching either |
| S5-11 | Known limitations | FR-74 | Unconfirmed runtime identifiers, declared-not-enforced limits, unsigned scope contract (SEC-010), no native drift detection |
| S5-12 | Deviations register | FR-73 | Including the deprecated signing workflow not carried forward |
| S5-13 | Traceability matrix | FR-71, FR-72, SC-10 | Requirement to ADR to task to test to artifact |
| S5-14 | Quickstart with counted files and steps; `README.md` | FR-65, SC-02, SC-03, SC-12 | Counts match the executed procedure |
| S5-15 | Sanitization audit as a precondition for public visibility | NFR-04 | Full history, not the working tree |

## Commands

No command exists yet; this repository contains documentation only. The commands below are
the ones the plan commits to creating, each attributed to the work item that creates it.
They are recorded here so that NFR-13's consistency check has a target.

### Documentation lint — exists today

```powershell
npx --yes markdownlint-cli2 "docs/**/*.md" "*.md"
```

### Offline validation — created by S3-06, S3-12

```powershell
[TBD until S3-12] zeroops validate --config examples/minimal/
```

### Local tests, credential-free — created by S3-12

```powershell
[TBD until S3-12] zeroops test --local
```

### Negative suite, release gate — created by S3-09

```powershell
[TBD until S3-09] zeroops test --negative
```

### Guided setup — created by S4-02, S4-04, S4-06

```powershell
[TBD until S4-06] zeroops init --subscription <SUBSCRIPTION_ID>
[TBD until S4-06] zeroops init --non-interactive --config <CONFIG_FILE>
```

### Preview and deploy — created by S4-07, S4-08

```powershell
[TBD until S4-08] zeroops preview --config <CONFIG_FILE>
[TBD until S4-08] zeroops deploy --config <CONFIG_FILE>
```

### Post-deployment validation — created by S4-11

```powershell
[TBD until S4-11] zeroops verify --config <CONFIG_FILE>
```

### Cleanup — created by S5-07

```powershell
[TBD until S5-07] zeroops cleanup --config <CONFIG_FILE>
[TBD until S5-07] zeroops cleanup --verify --config <CONFIG_FILE>
```

The `zeroops` name is provisional and is confirmed when S3-12 lands. Every `[TBD]` marker
is removed by the work item named beside it, in the same pull request that creates the
command.

## Risks

| Risk | Impact | Likelihood | Handling |
|---|---|---|---|
| Runtime capability identifiers never reconcile against a real runtime | The tool policy stays declared rather than verified | Medium | RBAC and the compiled-ARM audit carry the guarantee independently. The gap is documented under FR-74, not hidden |
| The framework cannot compel the runtime to emit an evidence manifest | FR-44 to FR-47 become partially consumer-side | Medium | FR-48 already scopes the audit record to "where the architecture supports it". The evidence model is a schema plus a collector; an attribute the runtime cannot supply is recorded as unobserved rather than estimated |
| Upstream is preview-era and may break the pinned composition | Slice 4 rework | Medium | Immutable digest pin plus a compatibility test; an upstream bump is a security-reviewed change |
| Specification amendments are not made before decomposition | Gates built on unfalsifiable requirements | High if unaddressed | Declared blocking above |
| A public-visibility event precedes the full-history scan | Irreversible disclosure | Low, high impact | S3-02 is effective immediately, before any further commit |
| The denylist paradox is unresolved when the sanitization gate is designed | SC-13 gate is self-defeating | Medium | S3-14 blocks the gate design |

## Traceability

| Requirement group | Slice | Work items |
|---|---|---|
| A — Minimum contract | 2 complete, 3 | `minimum-sre-agent-contract.md`, S3-03, S3-04, S3-08 |
| B — Guided discovery | 4 | S4-01 to S4-06 |
| C — Configuration | 3 | S3-04, S3-06, S3-10 |
| D — Provisioning and deployment | 4 | S4-07 to S4-10, S3-13 |
| E — Validation | 3, 4 | S3-09, S3-12, S4-09, S4-11 |
| F — Observability and evidence | 5 | S5-02 to S5-05 |
| G — Safe operational controls | 3, 4 | S3-07 to S3-09, S4-12, S4-13, S4-16 |
| H — Extensibility | 3, 5 | S3-01, S3-10, S3-11, S5-01, S5-06 |
| I — Upgrade, rollback, cleanup | 5 | S5-07 to S5-09 |
| J — Traceability | 5 | S5-11 to S5-14 |
| NFR-01 to NFR-07 | 3, 4 | S3-02, S3-14, S4-14 to S4-16 |
| NFR-08 to NFR-14 | 4 | S4-14, S4-15 |
| NFR-15 to NFR-19 | 4, 5 | S4-16, S5-10, S5-14 |
| NFR-20 to NFR-23 | 5 | S5-06 to S5-09 |
| NFR-24 to NFR-26 | 3 | S3-01 |

## References

- [`prd.md`](../../../prd.md)
- [Specification](spec.md), [Research](research.md), [Data model](data-model.md),
  [Schema register](contracts/schema-register.md),
  [Security review](security-review-architecture.md)
- [Architecture overview](../../architecture/overview.md),
  [Minimum SRE Agent Contract](../../architecture/minimum-sre-agent-contract.md),
  [Source analysis](../../architecture/source-analysis.md)
- ADR-0001, ADR-0002, ADR-0003, ADR-0004

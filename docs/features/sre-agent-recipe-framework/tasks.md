# Tasks: Zero Ops SRE Agent Recipe Framework — Slices 3, 4 and 5

**Feature**: `sre-agent-recipe-framework`
**Date**: 2026-09-23
**Status**: Draft
**Source plan**: [plan.md](plan.md) (Slices 3, 4, 5)
**Source specification**: [spec.md](spec.md) v1.4
**Security review**: [security-review-architecture.md](security-review-architecture.md)
**Binds to**: ADR-0001, ADR-0002, ADR-0003, ADR-0004 (all Accepted)
**Board**: GitHub — `arthursilvany/zero-ops-sre-recipe`

## How to Read This Document

Every task carries the `plan.md` work item identifier it implements (`S3-xx`, `S4-xx`,
`S5-xx`). That identifier is the traceability spine: no work item is renamed, merged away
or silently dropped. Five identifiers are **new** (`S3-15`, `S4-17`, `S5-16`, `S5-17`,
`S5-18`) and
exist because a required security control or requirement had no owner in `plan.md`; each is
flagged in *Coverage Gaps Found During Decomposition* below.

Markers:

- `[P]` — parallelisable with its siblings inside the same story.
- `[copilot]` — agent-autonomous candidate: deterministic, credential-free, fully specified.
- `[human]` — requires an Azure subscription, a judgement call, or a trust decision.

Tests are **not** separate tasks. Each task is accepted only with the tests named in its
story's acceptance criteria.

## Labels

Per `.memory/board-config.md` (`type:user-story`, `type:task`, `feature:<name>`), extended
with the category and slice labels the decomposition needs. **Assumption stated**: no
`priority:` convention exists in the repository, so story priority is carried in the title
(`(P1)`) and not as a label, while `slice:` is added because the plan sequences all work by
slice and the board is otherwise unorderable.

| Label | Applies to |
|---|---|
| `type:user-story`, `type:task` | Every item |
| `feature:sre-agent-recipe-framework` | Every item |
| `slice:3`, `slice:4`, `slice:5` | Every item |
| `security` | Tasks implementing a SEC-xxx control |
| `schema` | Contract and schema authoring |
| `infra` | Bicep composition, provisioning, deployment |
| `ci-cd` | Workflows and quality gates |
| `docs` | Documentation deliverables |
| `negative-test` | Tasks whose deliverable is a release-gating negative assertion |
| `copilot-candidate`, `needs-human` | Delegation routing |

---

## User Story 1 — Validate a configuration offline against the published contract (P1)

**Slice**: 3
**Spec story**: User Story 1
**Work items**: S3-01, S3-03, S3-04, S3-05, S3-06, S3-10, S3-12, S3-15 (new)
**Satisfies**: FR-01, FR-02, FR-03, FR-04, FR-05, FR-06, FR-07, FR-24, FR-25, FR-26,
FR-27, FR-28, FR-29, FR-30, FR-41, FR-57, FR-61, FR-63, NFR-12, NFR-15, NFR-24, NFR-25,
NFR-26, CON-01, CON-03, CON-11
**Conformance**: CC-001, CC-002, CC-003, CC-022
**Security controls owned**: SEC-005 (via S3-15), SEC-009 (via S3-05), SEC-013 (schema
half), SEC-017

**Independent test**: On a machine with no Azure CLI login and no credentials, clone,
install the tooling package, run the documented validation command against
`examples/minimal/` and against three deliberately broken fixtures, and observe one pass
and three distinct, path-named failures.

**Risk**: Medium. The canonicalisation and hashing rules (S3-05) are the load-bearing
element of FR-19, FR-23 and FR-44; getting them wrong invalidates the evidence chain
downstream. Everything else in this story is deterministic authoring.

### Acceptance criteria

1. `zeroops validate examples/minimal/` exits `0` in an environment where
   `az account show` fails, and the process makes no outbound network call (asserted by
   running it with network egress blocked).
2. A fixture adding the property `notAThing` to the framework configuration causes a
   non-zero exit whose message contains the artifact path and the JSON pointer of the
   offending property, and contains the allowed property set. (CC-002)
3. A fixture with an empty in-scope selection, and a second fixture whose observation
   period ends before it starts, each cause a non-zero exit with a message naming the
   semantic rule violated. (CC-003, FR-28)
4. A fixture whose scope contract carries a secret-shaped field value produces an error
   message that contains the property path and the expected shape and **does not contain
   the supplied value** (asserted by substring absence). (NEG-K, SEC-017)
5. Every schema named in `contracts/schema-register.md` exists at exactly one path under
   `contracts/schemas/`, and a duplicate-definition check fails the build when the same
   `$id` appears twice. (FR-05)
6. `grep` over every path listed in `contracts/core-paths.json` returns zero matches for
   the runtime-specific identifier list, and the same search over `core/binding/` returns
   at least one. (FR-04, CON-03)
7. A grep for non-English enum values across `contracts/` and `core/` returns zero, and
   every renamed reference value appears in `contracts/vocabulary/` with its provenance.
   (FR-03, CON-01)
8. The same scope-contract fixture produces the identical lowercase-hex SHA-256 digest on
   `windows-latest` and `ubuntu-latest` in CI. (NEG-J, FR-19, FR-23)
9. `examples/minimal/` contains zero occurrences of any workload-type identifier
   (`aks`, `kubernetes`, `aro`, `vmss`, case-insensitive). (CC-022, FR-63)
10. No directory in the repository contains only a keep-file. (NFR-24)

### Tasks

- [ ] T1.01 `[human]` **(S3-01, S3-04, S3-06, S3-12, S3-15) Tracer bullet — walking skeleton from clone to a passing validation.** Create `contracts/`, `core/`, `wizard/`, `tools/`, `bin/`, `examples/minimal/`, `tests/` per the structure in `plan.md`; author `contracts/schemas/framework-config.schema.json` only; implement `tools/` far enough that `bin/zeroops validate examples/minimal/` exits `0`; wire `tests/validation/test_minimal_example.py`. Done when the command runs end to end on Windows and Linux with no Azure access. This is the thinnest vertical slice and it unblocks every other task in the story.
- [ ] T1.02 `[copilot]` **(S3-01) Declare the core.** Author `contracts/core-paths.json` plus `contracts/schemas/core-paths.schema.json`. Done when the file enumerates every core path and validates against its own schema. (FR-61)
- [ ] T1.03 `[copilot]` **(S3-01) Repository hygiene rules.** `.gitignore` covering the upstream secrets-file pattern and the discovery output path, `.gitattributes` enforcing LF for every emitted artifact type, and a test in `tests/unit/` asserting the upstream secrets-file pattern is matched by the ignore rules. (SEC-013, FR-49)
- [ ] T1.04 `[copilot]` **(S3-01) Correct `CONTRIBUTING.md`.** Replace the `src/`, `infra/`, `config/` references with the settled structure. Done when no path named in `CONTRIBUTING.md` is absent from the repository. (NFR-25)
- [ ] T1.05 `[human]` **(S3-15, NEW) Tooling package baseline with pinned supply chain.** `tools/pyproject.toml` with an enumerated, hash-pinned, wheel-only runtime dependency set, a pinned interpreter floor, development dependencies excluded from the runtime path, and `bin/` shims for Bash and PowerShell that forward arguments and hold no behaviour. Done when installation from a clean environment resolves only hash-pinned wheels and executes no code at install time. (SEC-005, ADR-0004) **New work item — see Coverage Gaps.**
- [ ] T1.06 `[copilot]` `[P]` **(S3-03) English vocabulary with recorded provenance.** `contracts/vocabulary/` covering execution states, evidence provenance classifications, the access-denied state, and the assessment status and confidence enumerations. Done when every renamed value carries its original reference value as provenance metadata and no original value is used as an identifier. (FR-03)
- [ ] T1.07 `[copilot]` **(S3-04) Author the governance schemas.** `scope-contract`, `framework-config`, `environment-binding`, `connector-config`, `agent-definition` under `contracts/schemas/`. Each sets `additionalProperties: false`, declares an explicit version identifier, declares no secret-named or free-form payload property, and `$ref`s nothing outside `contracts/schemas/`. (FR-02, FR-24, FR-30, FR-36, SEC-013)
- [ ] T1.08 `[copilot]` `[P]` **(S3-04) Author the contract-only schemas.** `change-set`, `approval-ledger`, `evidence-manifest`, `query-catalogue`, `workload-extension`, `handoff-record`, `assessment-result`, `readiness-result`, `tool-policy`, `capability-mapping`. Done when every entry in `contracts/schema-register.md` resolves to exactly one file. (FR-02, FR-05, FR-06, FR-57, FR-58)
- [ ] T1.09 `[copilot]` `[P]` **(S3-04) Error, retry, timeout and incomplete-execution semantics.** Add the failure-class-to-state mapping and the schema-backed incomplete-execution representation to the evidence manifest and execution-state vocabulary, and document it in the contract. Done when every failure class named in `spec.md` *Failure Modes* maps to exactly one defined state value. (FR-07) **Previously unowned — see Coverage Gaps.**
- [ ] T1.10 `[human]` **(S3-05) Canonicalisation and hashing.** Implement RFC 8785 canonicalisation, NFC normalisation before canonicalisation, SHA-256, lowercase hex, self-exclusion of the hash field, no trailing newline, LF output — exactly as ADR-0004 pins. Done when the cross-platform determinism test (NEG-J) passes in CI on both runners. (FR-19, FR-23, SEC-009)
- [ ] T1.11 `[copilot]` **(S3-06) Validator: structural, semantic and warning levels.** Structural conformance first, then semantic checks, then Recommended-area warnings. Errors name artifact and JSON pointer; errors for secret-bearing or identifier-bearing fields name path and shape only. (FR-25, FR-27, FR-28, SEC-017)
- [ ] T1.12 `[copilot]` `[P]` **(S3-10) `examples/minimal/`, workload-neutral.** A complete, valid configuration set with placeholders only and no workload-type identifier. (FR-26, FR-63, CC-022)
- [ ] T1.13 `[copilot]` `[P]` **(S3-04) Schema versioning and migration guidance.** Document the version identifier rule and the migration-guidance obligation in `contracts/schema-register.md`, plus a check asserting every instance declares the version it conforms to. (FR-29, NFR-21)
- [ ] T1.14 `[human]` **(S3-12) Local, credential-free command surface, documented.** `zeroops validate` and `zeroops test --local`, documented with copy-pasteable commands, and the `[TBD]` markers in `plan.md` *Commands* removed in the same pull request. Confirms the `zeroops` name. (FR-41, NFR-12, NFR-18)

---

## User Story 2 — Prove the read-only and safety boundary offline (P1)

**Slice**: 3
**Spec story**: User Story 1 (safety half) and User Story 3 (offline precondition)
**Work items**: S3-07, S3-08, S3-09
**Satisfies**: FR-06, FR-11, FR-40, FR-51 (layers one and three), FR-52, FR-53, FR-55
(structural half), FR-56, FR-59, CON-02, CON-06, CON-07
**Conformance**: CC-016, CC-017, CC-018, CC-019 (structural), CC-020, CC-021 (NEG-D half),
CC-022
**Security controls owned**: SEC-001 (layers one and three), SEC-002 (structural), SEC-008,
SEC-011 (classification), SEC-012, SEC-016

**Independent test**: Run `zeroops test --negative` in a credential-free environment. Then
revert each guard one at a time and confirm the suite fails for that specific reason. A
negative suite that cannot be made to fail is not evidence.

**Risk**: High. This is the story the entire safety argument rests on, and the security
review's root finding is that the framework tends to verify its own declaration rather than
the enforcement. Every assertion here is deliberately structural or RBAC-derived.

### Acceptance criteria

1. Deleting the read-only verb allow-list entry for a verb used by the wizard causes the
   static call-site check to fail the build with the offending file and line. (NEG-H,
   FR-11, SEC-008)
2. Adding a direct `az`/SDK invocation that bypasses the command broker to any file under
   `core/` or `wizard/` causes the build to fail. (NEG-H, CON-02)
3. Adding a write-capable Azure verb to any core or wizard call site causes the build to
   fail. (NEG-H, CC-018, SEC-012)
4. A fixture agent binding with its tool list omitted causes the negative suite to fail.
   (NEG-D, CC-021, SEC-001 layer three)
5. The tool policy declares a deny rule for each of the seven FR-52 categories, and
   deleting any one of the seven causes a test to fail naming the missing category.
6. A capability-mapping entry not classified as allowed or denied fails validation locally;
   the runtime-advertised reconciliation is explicitly deferred to S4-12 and the mapping
   file carries a machine-readable `verification: declared-not-runtime-verified` marker.
   (FR-51, SEC-001)
7. The emitted tool policy declares all four execution limits, schema-validated; a policy
   missing any one fails. The limits are marked declared-not-framework-enforced. (FR-53,
   SEC-011)
8. An approval-ledger entry whose decider principal object identifier equals the agent's
   principal object identifier is rejected; an entry differing only in display name is
   still rejected. (NEG, CC-017, FR-56, SEC-016)
9. A static assertion fails when any core path admits retrieved or diagnostic content into
   the instruction or prompt-assembly region. (NEG-E, CC-019, SEC-002)
10. An evidence-entry fixture carrying raw retrieved content instead of a content hash plus
    classification fails. (NEG-F, CC-019)
11. Every schema lacking `additionalProperties: false`, or declaring a secret-named or
    free-form payload property, fails the schema lint. (NEG-I, FR-49, SEC-013)
12. `zeroops test --negative` is wired as a required check and its failure blocks the merge.
    (FR-40, SC-06)

### Tasks

- [ ] T2.01 `[human]` **(S3-07) Read-only command broker.** A single choke point in `tools/` through which every Azure invocation from `core/` and `wizard/` passes, restricted to a read-only verb allow-list. (FR-11, CON-02, SEC-008)
- [ ] T2.02 `[copilot]` **(S3-07) Static call-site check.** Fails the build on any Azure invocation outside the broker or naming a verb outside the allow-list. Delivers NEG-H. (FR-11, CC-018, SEC-008, SEC-012)
- [ ] T2.03 `[copilot]` **(S3-08) Tool policy in capability classes.** `core/policy/` authoring the deny-by-default, deny-wins, fail-closed policy with explicit deny rules for all seven FR-52 categories and the four FR-53 execution limits. (FR-51, FR-52, FR-53)
- [ ] T2.04 `[human]` **(S3-08) Binding-layer capability mapping, marked unverified.** `core/binding/` maps capability classes to the pinned runtime's identifiers, carrying an explicit declared-not-runtime-verified marker and the per-runtime-version reconciliation hash field that S4-12 populates. (FR-51, FR-53, SEC-001, SEC-011)
- [ ] T2.05 `[copilot]` `[P]` **(S3-09) NEG-D — explicit tool list assertion.** An emitted binding lacking an explicit tool list fails. (SEC-001 layer three, CC-021)
- [ ] T2.06 `[copilot]` `[P]` **(S3-09) NEG-E — instruction-region containment, static.** No declared core path admits retrieved or diagnostic content into the instruction or prompt-assembly region. (SEC-002, CC-019)
- [ ] T2.07 `[copilot]` `[P]` **(S3-09) NEG-F — evidence stores hashes, never content.** (SEC-002, CC-019)
- [ ] T2.08 `[copilot]` `[P]` **(S3-09) NEG-I — schema lint.** `additionalProperties: false` everywhere, no secret-named property, no free-form payload field. (SEC-013, FR-49)
- [ ] T2.09 `[copilot]` `[P]` **(S3-09) NEG-J — cross-platform digest determinism.** Runs on `windows-latest` and `ubuntu-latest`. (SEC-009, FR-19, FR-23)
- [ ] T2.10 `[copilot]` `[P]` **(S3-09) NEG-K — validation errors never echo the value.** (SEC-017, FR-49)
- [ ] T2.11 `[copilot]` `[P]` **(S3-09) CC-016, CC-017, CC-020 assertions.** Write denial, self-approval denial comparing principal object identifiers, and no secret in any emitted artifact. (FR-52, FR-56, SEC-016)
- [ ] T2.12 `[human]` **(S3-09) Negative suite runner and release gate.** `zeroops test --negative`, credential-free, wired as a required status check. Done when reverting any single guard above makes the suite fail for that specific reason. (FR-40, SC-06)
- [ ] T2.13 `[copilot]` `[P]` **(S3-08) Prohibited-actions list.** An operator-facing list that is generated from, or automatically diffed against, the tool policy deny rules, so drift fails. (FR-59)

---

## User Story 3 — Make the repository safe to publish and safe to execute (P1)

**Slice**: 3
**Spec story**: cross-cutting precondition of every story
**Work items**: S3-02, S3-13, S3-14
**Satisfies**: NFR-01, NFR-02, NFR-03, NFR-06, SC-05, SC-13, CON-06, ADR-0001
**Security controls owned**: SEC-004, SEC-006, SEC-014

**Independent test**: Push a commit containing a synthetic, clearly fake but pattern-valid
secret and confirm push protection rejects it before it lands. Separately, plant the same
pattern in a scratch branch's history and confirm the full-history CI scan fails while the
working tree is clean.

**Risk**: High and time-critical. `plan.md` marks S3-02 as effective immediately, before
any further commit, because the repository is expected to become public and history is
irreversible.

### Acceptance criteria

1. Platform secret scanning **and** push protection are enabled on the repository, verified
   by an API read recorded in the pull request. (NFR-02, SEC-006)
2. A synthetic secret planted in a commit that is not the tip causes the CI gate to fail
   while `git status` is clean. A working-tree-only scan would pass here; that is the
   defect being closed. (NFR-01, SC-05, SEC-006)
3. The scan covers secrets, tenant identifiers, subscription identifiers, resource
   identifiers, endpoints and customer names, over every commit reachable from `main`.
4. The history-rewrite remediation path is documented and is reachable from `SECURITY.md`
   before the first commit that could require it. (NFR-04, SEC-006)
5. `deploy/upstream.lock` records a 40-character commit digest; a CI check fails the build
   when the pin is a tag or an abbreviated ref. (SEC-004, ADR-0001)
6. The fetched upstream tree digest is verified before any upstream script executes, and a
   deliberately altered fetched tree causes a fail-closed abort with a non-zero exit.
   (SEC-004, NFR-06)
7. The SC-13 denylist decision is recorded with its rationale: the repository stores only
   salted SHA-256 digests of forbidden terms, and the plaintext vocabulary and salt are
   supplied at run time from outside the repository. A committed plaintext denylist fails a
   check. (SC-13, NFR-03, SEC-014)

### Tasks

- [ ] T3.01 `[human]` **(S3-02) Enable platform secret scanning with push protection.** Effective before any further commit. Record the verification in the pull request. (NFR-02, SEC-006)
- [ ] T3.02 `[human]` **(S3-02) Full-history secret and identifier scanning gate.** `.github/workflows/`, scanning every commit reachable from `main`, blocking on any finding. (NFR-01, SC-05, SEC-006)
- [ ] T3.03 `[copilot]` `[P]` **(S3-02) Document the history-rewrite remediation path.** In `SECURITY.md`, with commands. (NFR-04, NFR-18, SEC-006)
- [ ] T3.04 `[human]` **(S3-13) Pin upstream by immutable commit digest.** `deploy/upstream.lock` carrying the commit digest and the fetched-tree digest; a tag-only or abbreviated pin fails in CI. (ADR-0001, SEC-004)
- [ ] T3.05 `[human]` **(S3-13) Verify the fetched tree before execution, fail closed.** Plus documentation of the acquisition step as a trust-boundary crossing and of an upstream bump as a security-reviewed change, not a version bump. (NFR-06, SEC-004)
- [ ] T3.06 `[human]` **(S3-14) Resolve the customer-vocabulary denylist location.** Decision record: salted-digest matching with the plaintext held outside the repository. Blocks T6.05, the SC-13 gate. (SC-13, NFR-03, SEC-014)

---

## User Story 4 — Discover candidate workloads and emit a scope contract (P2)

**Slice**: 4
**Spec story**: User Story 2
**Work items**: S4-01, S4-02, S4-03, S4-04, S4-05, S4-06
**Satisfies**: FR-10, FR-11, FR-12, FR-13, FR-14, FR-15, FR-16, FR-17, FR-18, FR-19,
FR-22, FR-23, NFR-01, CON-11
**Conformance**: CC-004, CC-005, CC-006, CC-020
**Security controls owned**: SEC-007

**Independent test**: Run interactively against one operator-supplied subscription, commit
the emitted configuration, then re-run non-interactively from that file and diff the two
emitted scope contracts byte for byte.

**Risk**: Medium-High. This is net-new capability with no reference implementation, and it
introduces the discovery-artifact leak path the security review flagged.

### Acceptance criteria

1. Discovery against a subscription containing at least one eligible workload returns a
   candidate list and creates, changes or deletes nothing — asserted by an activity-log
   diff over the run window showing zero write operations. (CC-004, FR-10)
2. Discovery against a subscription with zero eligible workloads returns an explicit empty
   result that prints the eligibility rules applied, and emits no scope contract file.
   (FR-12, `spec.md` Edge Cases)
3. The published eligibility rules document and the rules the empty result prints are the
   same source, asserted by a test comparing the two. (FR-12)
4. A scope spanning a readable and an unreadable resource group reports the unreadable
   portion as an explicit access-denied state naming the missing permission, and the
   candidate list is not silently shortened. (CC-006, FR-22)
5. The discovery output path is ignored by default, the file carries a header stating it
   contains real identifiers, and a documented redaction mode produces a version safe to
   attach to a bug report. (SEC-007, FR-17, NFR-01)
6. The emitted scope contract contains exactly the selected candidates and no others, and
   is produced by a field allow-list — a test asserting the emitter never copies a
   discovery row wholesale. (FR-13, FR-14)
7. A discovery row carrying a secret-shaped tag value cannot produce that value anywhere in
   the emitted scope contract. (NEG-G, SEC-007, CC-020)
8. No input prompt requests a secret in plain text; secret-bearing settings resolve to
   external references. (FR-17)
9. Every collected input maps to a field consumed by a downstream artifact, asserted by a
   test that fails on an input with no consumer, and every input prints a plain-English
   explanation at the point of collection. (FR-15)
10. For each input, a malformed value is rejected with a message naming the expected format
    and the step does not continue. (FR-16)
11. `--non-interactive` consuming the previously emitted file completes with no prompt and
    emits a byte-identical scope contract on Windows and on Linux. Full `--set` parity is
    asserted: every interactive prompt has a corresponding `--set` key, and a test fails
    when a prompt exists without one. (CC-005, FR-18, FR-19, ADR-0003)

### Tasks

- [ ] T4.01 `[copilot]` **(S4-01) Publish the eligibility rules.** `wizard/eligibility/`, plus the empty-result reporter reading the same source. (FR-12, FR-10)
- [ ] T4.02 `[human]` **(S4-02) Read-only Resource Graph discovery over a single subscription.** Query definitions in `wizard/discovery/`, all invocations routed through the S3-07 broker. Denied portions surface as explicit access-denied states. (FR-10, FR-11, FR-22)
- [ ] T4.03 `[copilot]` `[P]` **(S4-03) Discovery output hygiene.** Ignored-by-default path, identifier-warning header, documented redaction mode. (FR-17, NFR-01, SEC-007)
- [ ] T4.04 `[human]` **(S4-04) Field-allow-listed scope contract emitter.** Selection to contract, never copying a discovery row, computing the canonical hash from S3-05. (FR-13, FR-14, FR-23)
- [ ] T4.05 `[copilot]` `[P]` **(S4-04) NEG-G — secret-shaped tag cannot reach the contract.** (SEC-007, CC-020)
- [ ] T4.06 `[copilot]` **(S4-05) Input collection, explanation and format validation.** No secret collected in plain text; every input explained; invalid input rejected with the expected format. (FR-15, FR-16, FR-17)
- [ ] T4.07 `[human]` **(S4-06) Non-interactive and `--set` parity with byte-identical output.** Covered by tests rather than documentation. (FR-18, FR-19, CC-005, ADR-0003)

---

## User Story 5 — Provision, deploy and validate a read-only agent (P3)

**Slice**: 4
**Spec story**: User Story 3
**Work items**: S4-07, S4-08, S4-09, S4-10, S4-11, S4-12
**Satisfies**: FR-20, FR-21, FR-31, FR-32, FR-33, FR-34, FR-35, FR-36, FR-38, FR-39,
FR-43, FR-51 (layer two), FR-53 (posture check), FR-54, CON-09, CON-12
**Conformance**: CC-007, CC-008, CC-009, CC-012, CC-021
**Security controls owned**: SEC-001 (layer two), SEC-003, SEC-011 (verification)
**Added by spec v1.4**: FR-75, FR-76, FR-77, FR-78; CC-024, CC-025, CC-026, CC-028

**Independent test**: Preview against a real subscription without applying, apply, re-apply
unchanged, then run `zeroops verify`. Separately, run the compiled-ARM role audit offline
with no credentials at all.

**Risk**: High. This is the first journey that changes a live environment, and SEC-003 —
an over-privileged consumer-supplied identity — is the failure mode that breaks the
read-only invariant silently.

### Acceptance criteria

1. `zeroops preview` lists every resource to be created, changed or deleted and every role
   assignment to be granted, and applies nothing. Confirmation is explicit and the default
   answer is decline. (CC-007, FR-20)
2. The generated Infrastructure as Code inputs are visible, reviewable files, and the
   documentation shows a deployment path that does not use the wizard. (FR-21)
3. `deploy/compose/` composes and parameterises pinned upstream modules. A check fails the
   build when a Bicep module under `deploy/compose/` re-authors a resource that upstream
   already provides, and when any hand-authored ARM JSON is committed. Zero Terraform
   artifacts exist in the repository. (ADR-0001, ADR-0002, CON-12)
4. Every role definition identifier in the compiled ARM output resolves to a read-only
   allow-list; adding a `Contributor` role definition identifier to a fixture fails the
   check. The check runs with no credentials. (NEG-A, FR-33, CC-009)
5. A consumer-supplied existing principal holding any non-read role at any scope in the
   subscription blocks the preview until the operator explicitly confirms, and the preview
   enumerates each such assignment with its scope. (NEG-B, FR-34, SEC-003)
6. A scope entry naming a resource that no longer resolves fails at preview, before any
   provisioning. (`spec.md` Edge Cases, FR-20)
7. Re-running deployment with unchanged configuration succeeds and reports no unintended
   changes. (CC-008, FR-32)
8. An induced deployment failure produces a message naming the failing step, the probable
   cause and the documented recovery or cleanup action — all three asserted. (FR-38)
9. The same workload definition deploys to a non-production and a production environment
   binding without duplicating the workload definition. (FR-36)
10. No Infrastructure as Code parameter accepts a secret value, asserted by a parameter-type
    check. (FR-35)
11. `zeroops verify` reports a pass or fail per check across identity, role assignments,
    data-source connectivity and tool-policy posture, and **fails** when the agent principal
    holds any non-read role anywhere in the subscription, not only on declared scopes.
    (FR-39, FR-33, CC-009, SEC-003)
12. Validation distinguishes "permission not yet effective" from "permission not granted",
    producing two distinguishable result codes with documented settling behaviour. (FR-43)
13. The posture check reports the execution limits the runtime actually holds and fails on
    any mismatch against the declared values. (CC-012, FR-53, SEC-011)
14. A capability advertised by the pinned runtime that the tool policy neither allows nor
    denies fails the build; the reconciled set is recorded as a hash per runtime version,
    and the declared-not-runtime-verified marker from T2.04 is cleared only for the runtime
    version actually reconciled. (NEG-C, FR-51, CC-021, SEC-001)
15. `zeroops verify` proves each declared connector usable through a probe the agent executes; a connector that is provisioned but absent from the agent's listing fails as `connectorNotVisibleToAgent`. (FR-75, CC-024)
16. A canary trigger is read back after creation and its run is read back after firing; an empty stored instruction or a run with no tool call fails, and an accepted-for-processing response is never a pass. (FR-76, CC-025)
17. The failure registry carries `awaitingApproval`, `connectorNotVisibleToAgent`, `noToolUse` and `deliveryFailed`, and an on-behalf-of request in a read-only agent is classified as a permission gap. (FR-77, CC-028)
18. A custom agent with an empty, missing or wider-than-parent capability list fails offline, and the runtime meaning of an empty list is recorded by the reconciliation gate. (FR-78, CC-026)

### Tasks

- [ ] T5.01 `[human]` **(S4-07) Bicep composition over pinned upstream modules.** `deploy/compose/`; compose and parameterise, never re-author. Includes the managed-identity default and the existing-identity binding path. (FR-31, FR-34, FR-35, FR-36, ADR-0002) **Blocked by ADR-0007 (Proposed): how the composition obtains read-only role assignments.**
- [x] T5.02 `[copilot]` `[P]` **(S4-07) Anti-duplication and anti-Terraform structural checks.** Fail on hand-authored ARM JSON, on re-authoring an upstream-provided resource, and on any Terraform artifact. (ADR-0002, CON-12, NFR-25)
- [ ] T5.03 `[human]` **(S4-08) Preview with full existing-assignment enumeration.** Includes stale-scope-entry detection and explicit confirmation defaulting to decline. Delivers NEG-B. (FR-20, FR-33, FR-34, SEC-003)
- [x] T5.04 `[copilot]` **(S4-09) NEG-A — compiled-ARM role audit, offline.** The authoritative read-only check, credential-free. (FR-33, CC-009, SEC-001 layer one)
- [ ] T5.05 `[human]` **(S4-10) Idempotent deployment with actionable failure messages.** Failing step, probable cause, recovery action. (FR-32, FR-38, CC-008)
- [ ] T5.06 `[human]` **(S4-11) `zeroops verify` post-deployment validation.** Per-check results; fails on any non-read role anywhere in the subscription; distinguishes not-yet-effective from not-granted; reports runtime execution limits against declared values. (FR-39, FR-43, FR-53, CC-009, CC-012)
- [ ] T5.07 `[human]` **(S4-12) NEG-C — runtime capability reconciliation gate.** Enumerates the capability set advertised by the pinned runtime, fails closed on any unclassified capability, records the reconciled set as a per-version hash. (FR-51, FR-54, CC-021, SEC-001 layer two)
- [ ] T5.08 `[copilot]` `[P]` **(S4-07) Expose the non-wizard deployment path.** Document and test deploying from the committed Infrastructure as Code inputs alone. (FR-21)
- [ ] T5.09 `[human]` **(SA-01, NEW) Functional connector probe in `zeroops verify`.** Probe thread per declared connector, data plane audience token, classification as `connectorNotVisibleToAgent`. Depends on T5.06. (FR-75, CC-024)
- [ ] T5.10 `[human]` **(SA-02, NEW) End-to-end canary with stored-instruction read-back.** Create, read back, fire, poll the run skipping the instruction message, assert sentinel and tool use within the measured Log Analytics propagation window, delete the canary. Depends on T5.09. (FR-76, CC-025)
- [x] T5.11 `[copilot]` `[P]` **(SA-03, NEW) Four failure classes.** `tools/zeroops/failure_modes.py`, each with citation, probable cause and recovery action; symptom to first check table handed to T11.01. (FR-77, CC-028)
- [ ] T5.12 `[human]` **(SA-04, NEW) Custom agents with explicit non-empty capabilities.** Schema property, three negative cases, schema version bump; empty-list runtime behaviour measured within T5.07. (FR-78, CC-026)

---

## User Story 6 — Gate every change with a hardened CI supply chain (P3)

**Slice**: 4
**Spec story**: cross-cutting; this is the DevSecOps unit `plan.md` states does not yet
exist on the board
**Work items**: S4-14, S4-15, S4-17 (new)
**Satisfies**: NFR-06, NFR-08, NFR-09, NFR-10, NFR-11, NFR-12, NFR-13, NFR-14, SC-13,
CON-06
**Security controls owned**: SEC-015, SEC-014 (gate implementation)

**Independent test**: Open a pull request that violates one gate at a time — a lint error,
a broken internal link, an invalid example, a malformed Bicep template, a documented
command that does not exist, an unpinned action — and confirm each fails for its own
reason.

**Risk**: Medium. Mechanical, but the workflows hold credentials that reach a customer
subscription, which is why SEC-015 applies to the workflows themselves.

### Acceptance criteria

1. Each of the following fails the build independently, verified by one deliberate
   violation each: Markdown lint, internal link check, example schema validation, Bicep
   build and lint, static Infrastructure as Code analysis, unit tests, the negative suite,
   the documented-command consistency check, dependency drift. (NFR-06, NFR-08 to NFR-13)
2. A documented command that does not exist fails the consistency check, naming the
   document and the command. (NFR-13)
3. Every `uses:` in every workflow is pinned to a 40-character commit digest; a tag-pinned
   action fails a check. (SEC-015)
4. Every workflow declares an explicit least-privilege `permissions:` block; a workflow
   without one fails a check. (SEC-015)
5. No workflow trigger checks out an untrusted ref with elevated rights, asserted by a
   check over trigger and checkout-ref combinations. (SEC-015)
6. The Azure-touching CI path authenticates through federated credentials and completes
   with no committed or printed credential. (NFR-14)
7. A dependency whose hash does not match the pinned value fails the build, and a
   vulnerability alert on a runtime dependency opens as a blocking signal. (SEC-005)
8. The SC-13 gate matches on salted SHA-256 digests supplied at run time, fails the build
   on a match inside a declared core path, and fails a separate check if a plaintext
   denylist is ever committed. (SC-13, SEC-014)

### Tasks

- [ ] T6.01 `[human]` **(S4-14) CI quality gate workflow.** Markdown lint, link check, example validation, Bicep build and lint, static Infrastructure as Code analysis, unit tests, negative gate. (NFR-06, NFR-08 to NFR-12)
- [ ] T6.02 `[copilot]` `[P]` **(S4-14) Documented-command consistency check.** Parses documented commands and asserts each exists. (NFR-13)
- [ ] T6.03 `[copilot]` `[P]` **(S4-14) Dependency drift and vulnerability gate.** Hash mismatch fails; vulnerability alerting on the runtime dependency set. (SEC-005)
- [ ] T6.04 `[human]` **(S4-15) CI supply-chain hardening.** Digest-pinned actions with an enforcement check, least-privilege `permissions:` on every workflow with an enforcement check, untrusted-ref trigger check, federated credentials with no long-lived secret. (SEC-015, NFR-14)
- [ ] T6.05 `[human]` **(S4-17, NEW) SC-13 salted-digest sanitization gate.** Implements the decision from T3.06: digests committed, plaintext and salt supplied at run time, corroborated by FR-63 and CC-022 structural checks and by NFR-03 review. (SC-13, NFR-03, SEC-014) **New work item — see Coverage Gaps.**

---

## User Story 7 — Publish the security model and measure injection resistance honestly (P3)

**Slice**: 4
**Spec story**: cross-cutting safety documentation
**Work items**: S4-13, S4-16
**Satisfies**: FR-42, FR-54, FR-59, NFR-05, NFR-16, NFR-18
**Conformance**: CC-023
**Security controls owned**: SEC-002 (empirical, non-gating half)
**Added by spec v1.4**: open decision on delivery of findings

**Independent test**: Read the security model and confirm each of the five NFR-05 threats
names a mitigation and a test, and that each named test is classified gating or measured.
Run the injection corpus against a deployment and confirm the result is reported with its
corpus version and evidence and is not wired to any required check.

**Risk**: Medium. The failure mode here is rhetorical rather than technical: presenting a
measured rate as proof. That is the exact defect the security review named.

### Acceptance criteria

1. The security model documents all five NFR-05 threats, each with a named mitigation and a
   named test, and each named test labelled gating or measured. A test asserts every named
   test identifier resolves to a test that actually exists. (NFR-05)
2. The security model states that RBAC is the authority for the read-only guarantee and the
   tool policy is defence-in-depth, in those terms. (SEC-001, FR-51)
3. The documentation states explicitly that read-only is **not** the runtime default and
   names the configuration action required to avoid inheriting write-capable tools. (FR-54)
4. The injection corpus is versioned, and its result is published as a resistance rate
   naming the corpus version, the execution identifiers and the supporting evidence
   manifests. (CC-023)
5. The corpus result is not a required status check — asserted by a check over the required
   checks list — and no document presents it as proof of prevention. A non-zero failure
   rate does not block a release. (CC-023, FR-42, NFR-05)
6. Configuration reference, deployment guide and validation guide each exist, and every
   procedure step carries a copy-pasteable command or an explicit manual marker. (NFR-16,
   NFR-18)
7. The delivery-of-findings decision is recorded in an ADR before any change to the `externalPublication` deny rule, and any resulting policy change is covered by an updated negative test. (`spec.md` open decisions)

### Tasks

- [ ] T7.01 `[human]` **(S4-16) Security model document.** Five threats, mitigation, named test, gating or measured classification; RBAC as authority; the FR-54 runtime-default warning. (NFR-05, FR-54, SEC-001)
- [ ] T7.02 `[copilot]` `[P]` **(S4-16) Configuration reference.** Every schema property documented with its owning concern per FR-24. (NFR-16, FR-24)
- [ ] T7.03 `[human]` `[P]` **(S4-16) Deployment and validation guides.** Every step with a command or a manual marker. (NFR-16, NFR-18, FR-59)
- [ ] T7.04 `[human]` **(S4-13) Versioned injection corpus, measured and non-gating.** Reported with corpus version and evidence; explicitly excluded from required checks. (NFR-05, CC-023, FR-42)
- [ ] T7.05 `[human]` **(SA-10, NEW) ADR: delivery of findings to customer-owned channels.** Evaluates keeping the deny rule against splitting it into leaving the tenant, still denied, and draft delivery to an owned channel as an opt-in capability with an approval ledger entry beyond drafts. (FR-52)

---

## User Story 8 — Observe agent behaviour through a defensible evidence chain (P4)

**Slice**: 5
**Spec story**: User Story 4
**Work items**: S5-02, S5-03, S5-04, S5-05
**Satisfies**: FR-44, FR-45, FR-46, FR-47, FR-48, FR-49, FR-50, CON-07
**Conformance**: CC-010, CC-011, SC-08
**Security controls owned**: SEC-002 (evidence half), SEC-013 (audit half)
**Added by spec v1.4**: FR-80, FR-81; CC-027

**Independent test**: Execute one diagnostic run against a deployed agent, validate the
emitted evidence manifest against its schema, and confirm every conclusion resolves or
carries a non-observed classification.

**Risk**: Medium-High. `plan.md` records the open risk that the framework cannot compel the
runtime to emit a manifest; the mitigation is that an attribute the runtime cannot supply
is recorded as unobserved rather than estimated.

### Acceptance criteria

1. The evidence manifest validates against its schema and its recorded scope hash equals
   the hash of the deployed scope contract; a manifest whose scope hash differs fails.
   (CC-010, FR-44)
2. An evidence entry omitting any one of provenance classification, collection timestamp,
   freshness, data classification or content hash fails validation, asserted once per
   attribute. (FR-45, CC-010)
3. A run with a deliberately unreachable data source records an explicit unobserved state,
   and a fixture substituting an estimate, a default or zero fails. (CC-011, FR-46)
4. A conclusion whose evidence reference does not resolve, and which carries no derived,
   inferred or recommended classification, makes the execution's output artifact invalid.
   This is enforced per execution at validation time, not by sampling; one sampled full
   execution corroborates that the invariant is exercised. (FR-47, SC-08)
5. The audit record lists the actions taken, and a scan asserts it contains no secret and
   no raw workload payload. Where the architecture cannot supply an action record, that is
   recorded explicitly rather than omitted. (FR-48, FR-49)
6. The query catalogue is version-controlled and integrity-verified; a tampered catalogue
   entry fails verification, and an attempt at arbitrary query construction is denied by the
   tool policy. (FR-50)
7. Shipped default queries and consumer extensions are separable, asserted by a check that
   a consumer extension produces no diff inside the declared core. (FR-50, SC-13)
8. The shipped catalogue includes a workload-neutral change-correlation query that validates offline, carries an integrity hash and stays within the result-set limit. (FR-80)
9. An observed conclusion citing only evidence collected before the execution window is rejected. (FR-81, CC-027)

### Tasks

- [ ] T8.01 `[human]` **(S5-02) Evidence manifest production and validation.** Bound to execution identifier and scope hash; entries carry a content hash and never the content; unreachable sources produce an explicit unobserved state. (FR-44, FR-45, FR-46, CC-010, CC-011)
- [ ] T8.02 `[copilot]` **(S5-03) Conclusion-to-evidence resolution as a schema invariant.** Per execution, not by sampling. (FR-47, SC-08)
- [ ] T8.03 `[copilot]` `[P]` **(S5-04) Audit record plus emitted-artifact scanning.** No secret, no raw workload payload; corroborating scan reported separately from the structural guarantee. (FR-48, FR-49)
- [ ] T8.04 `[human]` `[P]` **(S5-05) Query catalogue with integrity verification.** Shipped defaults separable from extensions; arbitrary construction denied by policy. (FR-50)
- [ ] T8.05 `[copilot]` `[P]` **(SA-06, NEW) Change-correlation catalogue query.** Resource changes and control-plane writes within a time window, integrity hashed per T8.04. (FR-80)
- [ ] T8.06 `[copilot]` **(SA-07, NEW) Evidence window invariant for observed conclusions.** Extends T8.02. (FR-81, CC-027)
- [ ] T8.07 `[human]` **(SA-11, NEW) Verify runtime run-state and score exposure.** Records whether the runtime exposes approval backlog and evaluation scores; no design and no release gate until it does. (`spec.md` open decisions)

---

## User Story 9 — Onboard a second workload with zero core edits (P5)

**Slice**: 5, with its enabling check scheduled in Slice 3
**Spec story**: User Story 5
**Work items**: S3-11 (Slice 3), S5-01, S5-06
**Satisfies**: FR-60, FR-61, FR-62, FR-64, NFR-20, NFR-26, CON-04, CON-05, CON-11
**Conformance**: CC-013, CC-022, SC-01
**Added by spec v1.4**: FR-79; open decision on incident routing

**Independent test**: In one clone at a released version, onboard `examples/minimal/` and
then the AKS reference workload, and inspect the resulting diff against
`contracts/core-paths.json`.

**Risk**: Low-Medium. The check is mechanical; the risk is that the reference workload
leaks a real identifier, which T9.02 guards with placeholders only.

### Acceptance criteria

1. Onboarding the reference workload produces a diff touching only configuration, example
   and extension paths, and zero files inside `contracts/core-paths.json`. (CC-013, SC-01,
   FR-60)
2. Deliberately modifying one declared core path during an onboarding run makes the check
   fail and names the file. A check that cannot fail is not the criterion. (FR-60)
3. `examples/reference-workload/` demonstrates AKS using placeholders only; a scan finds no
   real subscription, tenant, resource identifier, endpoint or customer name, and
   `<REFERENCE_CUSTOMER>` is the only customer token form present. (FR-64, NFR-01, CON-04)
4. Every extension point named in `source-analysis.md` section 5.3 is either documented
   with its inputs, outputs and the guarantees that survive a core upgrade, or explicitly
   declared out of scope with a reason. A test asserts the two lists together cover the
   section. (FR-62, NFR-20)
5. Adding a workload, a query, a connector and an extension are each demonstrated as purely
   additive operations in the reference workload example. (NFR-20)
6. `extensions/README.md` ships the extension contract and no content. (SC-13)
7. A skill whose guidance only names a topic is reported, and a skill stating when it applies, what to check, when it does not apply and which mistake to avoid passes. (FR-79)

### Tasks

- [ ] T9.01 `[copilot]` **(S3-11, Slice 3) Zero-core-edit check.** Diffs an onboarding change against `contracts/core-paths.json`; fails and names the file on any core modification. Scheduled in Slice 3 because it gates this story's acceptance. (FR-60, SC-01, CC-013)
- [ ] T9.02 `[human]` **(S5-01) `examples/reference-workload/` — AKS with placeholders only.** Added additively; produces no core diff. (FR-64, CON-04)
- [ ] T9.03 `[copilot]` `[P]` **(S5-06) Extension guide and extension-point documentation.** Inputs, outputs, and the guarantees that survive a core upgrade; `extensions/README.md` ships the contract and no content. (FR-62, NFR-20)
- [X] T9.04 `[copilot]` `[P]` **(SA-05, NEW) Skill guidance check.** Offline, warning level, fixtures for vague and useful skills. (FR-79)
- [ ] T9.05 `[human]` **(SA-09, NEW) ADR: incident routing contract.** Decides whether a workload extension routes incident classes to named custom agents in v1. Depends on T5.12. (Contract area 11)

---

## User Story 10 — Upgrade, roll back and clean up safely (P6)

**Slice**: 5
**Spec story**: User Story 6
**Work items**: S5-07, S5-08, S5-09
**Satisfies**: FR-66, FR-67, FR-68, FR-69, FR-70, NFR-21, NFR-22, NFR-23
**Conformance**: CC-014, CC-015, CC-C01, SC-09

**Independent test**: Deploy, place one pre-existing resource inside the target scope, run
cleanup and its verification, then run cleanup a second time.

**Risk**: Medium-High. FR-67 is the criterion that matters: a cleanup that removes a
resource the framework did not create is worse than no cleanup, and it is only provable
with a pre-existing resource deliberately planted in the target scope.

### Acceptance criteria

1. After cleanup, the verification step reports that no resource and no role assignment
   created by the framework remains. (CC-014, FR-66, SC-09)
2. A pre-existing resource planted inside the target scope survives cleanup untouched,
   asserted by identity and by last-modified time. (CC-014, FR-67)
3. Running cleanup a second time completes successfully with a zero exit code. (CC-015,
   FR-67, NFR-23)
4. The rollback procedure is documented with its trigger conditions and ordered steps, and
   is **executed at least once against a real deployment with the result recorded**,
   including elapsed time and any step that required improvisation. Documentation alone
   does not satisfy this. (FR-68, NFR-22)
5. A previously committed configuration is redeployable using the same documented commands,
   demonstrated by executing it. (FR-68)
6. A consumer pinned to version N continues to validate and deploy unchanged after N+1
   ships with a schema change; the check fails if the pinned path breaks. (CC-C01, FR-70)
7. Every release records a changelog entry; a release whose schema version identifier
   changed without a listed breaking change and migration guidance fails a check. (FR-69,
   NFR-21)

### Tasks

- [ ] T10.01 `[human]` **(S5-07) `zeroops cleanup` and `zeroops cleanup --verify`.** Complete, safe, idempotent, verified; removes only what the framework created. (FR-66, FR-67, NFR-23, CC-014, CC-015)
- [ ] T10.02 `[human]` **(S5-08) Rollback and upgrade procedures, exercised.** Executed at least once with the result recorded. (FR-68, FR-70, NFR-22)
- [ ] T10.03 `[copilot]` `[P]` **(S5-09) Versioning, changelog and schema-evolution check.** Breaking schema changes named with migration guidance; no lockstep upgrade required. (FR-69, NFR-21, CC-C01)

---

## User Story 11 — Hand the framework over with defensible documentation and traceability (P6)

**Slice**: 5
**Spec story**: closes the Definition of Done in `prd.md`
**Work items**: S5-10, S5-11, S5-12, S5-13, S5-14, S5-15, S5-16 (new), S5-17 (new),
S5-18 (new)
**Satisfies**: FR-08, FR-09, FR-42, FR-65, FR-71, FR-72, FR-73, FR-74, NFR-04, NFR-16,
NFR-17, NFR-18, NFR-19, SC-02, SC-03, SC-10, SC-12, SC-13, CON-11
**Security controls owned**: SEC-010, SEC-006 (public-visibility precondition)
**Added by spec v1.4**: FR-82

**Independent test**: Hand the quickstart to someone who has never seen the repository and
have them reach a first useful read-only result in one working session against a clean
subscription, recording elapsed time and every point where they had to improvise.

**Risk**: Medium. SC-12 is the criterion that can only be falsified by an actual person
executing it; a self-assessment is not evidence (FR-42).

### Acceptance criteria

1. The operations guide names the owning role, the escalation path and the conditions that
   trigger escalation, and documents the consumption limit and the four execution limits
   with the action on reaching either. (FR-08, FR-09)
2. Health-check outputs and audit records are described with their required fields and
   their producer. (FR-08)
3. The known-limitations document includes, at minimum: unconfirmed runtime capability
   identifiers, the declared-not-framework-enforced execution limits, the unsigned scope
   contract with the note that signing becomes mandatory if FR-58 is implemented, and the
   absence of native drift detection. A check asserts every item the security review
   classified as a limitation appears. (FR-74, SEC-010, SEC-011, SEC-001)
4. The deviations register records every deviation from the reference implementation with
   its rationale, including the deprecated signed scope-contract workflow that was not
   carried forward. (FR-73, SEC-010)
5. The traceability matrix resolves every FR, NFR, SC and CC identifier in `spec.md` v1.4
   to at least one ADR, task, test or artifact, or records it as deferred with a reason. A
   check fails on any unresolved identifier. (FR-71, FR-72, SC-10)
6. The quickstart states the counted number of files edited and the counted number of
   manual steps, and a check compares both counts against the executed procedure and fails
   on a mismatch. (FR-65, SC-02, SC-03)
7. SC-12 is recorded as an executed result — elapsed time, and every point the operator
   improvised — or is explicitly stated as unvalidated. No claim of a passing live
   execution without evidence. (SC-12, FR-42)
8. Quickstart, deployment, validation, operations, extension and cleanup guides all exist
   and are cross-linked in both directions. (NFR-19, NFR-16)
9. The public-visibility sanitization audit runs over the full git history, push protection
   is verified as enabled as a precondition, and the audit result is recorded before
   visibility is changed. (NFR-04, SEC-006)
10. Each of the eighteen `prd.md` *Required Documentation* items resolves to an artifact or
    is explicitly deferred with a reason. (NFR-16)
11. `docs/architecture/overview.md` renders at least one Mermaid diagram. (NFR-17)
12. The quickstart carries a first-scenario procedure that ends with a reviewed consumer skill under the extension paths, and the SC-12 run records it. (FR-82)

### Tasks

- [ ] T11.01 `[human]` **(S5-10) Operations and troubleshooting guide.** Ownership, escalation, health checks, audit trail, consumption limit and execution limits with the action on reaching either. (FR-08, FR-09)
- [ ] T11.02 `[copilot]` `[P]` **(S5-11) Known limitations.** Unconfirmed runtime identifiers, declared-not-enforced limits, unsigned scope contract, no native drift detection. (FR-74, SEC-010)
- [ ] T11.03 `[copilot]` `[P]` **(S5-12) Deviations register.** Including the deprecated signing workflow not carried forward. (FR-73, SEC-010)
- [ ] T11.04 `[copilot]` **(S5-13) Traceability matrix plus its completeness check.** Requirement to ADR to task to test to artifact; fails on any unresolved identifier. (FR-71, FR-72, SC-10)
- [ ] T11.05 `[human]` **(S5-14) Quickstart and `README.md` with counted files and steps.** Counts asserted against the executed procedure. (FR-65, SC-02, SC-03, SC-12)
- [ ] T11.06 `[human]` **(S5-14) Execute SC-12 end to end and record the result.** Elapsed time and every improvisation point, or an explicit unvalidated statement. (SC-12, FR-42)
- [ ] T11.07 `[human]` **(S5-15) Public-visibility sanitization audit.** Full history, push protection verified as a precondition, result recorded. (NFR-04, SEC-006)
- [ ] T11.08 `[copilot]` `[P]` **(S5-16, NEW) Required-documentation completeness check.** Asserts each of the eighteen `prd.md` items resolves to an artifact or a recorded deferral, and that the architecture overview renders a Mermaid diagram. (NFR-16, NFR-17, NFR-19) **New work item — see Coverage Gaps.**
- [ ] T11.09 `[human]` **(S5-17, NEW) Customer onboarding checklist, quick wins first.** Phase one installs the agent, adds the sources and answers the team integration before anything is asked of the customer, then uses the Level 100 prompts of the external playbook, linked by pinned commit and never copied because that repository carries no licence. Phase two maps the customer's existing documents onto the recipe artifacts they can populate. (CON-11, SC-12, SC-13) **New work item — see Coverage Gaps.**
- [ ] T11.10 `[human]` `[P]` **(S5-18, NEW) Review the practitioner community thread against committed artifacts.** Examines ADR-0001, the minimum SRE agent contract, `core/policy/`, the known limitations, the deviations register and the environment binding against what practitioners report about the runtime, recording confirmed, contradicted or no-evidence for each. Every contradiction produces a concrete follow-up; no author, customer, tenant or resource identifier reaches a committed artifact. (FR-73, FR-74, SEC-010) **New work item — see Coverage Gaps.**
- [ ] T11.11 `[human]` **(SA-08, NEW) First-scenario quickstart.** Interactive session, distilled skill, human review, commit under the extension paths; agent-drafted text is untrusted until reviewed. Depends on T9.04. (FR-82, SC-12)

---

## Coverage Verification

### Every `plan.md` work item is mapped

| Work item | Story | Work item | Story | Work item | Story |
|---|---|---|---|---|---|
| S3-01 | US-1 | S4-01 | US-4 | S5-01 | US-9 |
| S3-02 | US-3 | S4-02 | US-4 | S5-02 | US-8 |
| S3-03 | US-1 | S4-03 | US-4 | S5-03 | US-8 |
| S3-04 | US-1 | S4-04 | US-4 | S5-04 | US-8 |
| S3-05 | US-1 | S4-05 | US-4 | S5-05 | US-8 |
| S3-06 | US-1 | S4-06 | US-4 | S5-06 | US-9 |
| S3-07 | US-2 | S4-07 | US-5 | S5-07 | US-10 |
| S3-08 | US-2 | S4-08 | US-5 | S5-08 | US-10 |
| S3-09 | US-2 | S4-09 | US-5 | S5-09 | US-10 |
| S3-10 | US-1 | S4-10 | US-5 | S5-10 | US-11 |
| S3-11 | US-9 | S4-11 | US-5 | S5-11 | US-11 |
| S3-12 | US-1 | S4-12 | US-5 | S5-12 | US-11 |
| S3-13 | US-3 | S4-13 | US-7 | S5-13 | US-11 |
| S3-14 | US-3 | S4-14 | US-6 | S5-14 | US-11 |
| S3-15 *(new)* | US-1 | S4-15 | US-6 | S5-15 | US-11 |
| | | S4-16 | US-7 | S5-16 *(new)* | US-11 |
| | | S4-17 *(new)* | US-6 | S5-17 *(new)* | US-11 |
| | | | | S5-18 *(new)* | US-11 |

**No `plan.md` work item is unmapped.** 45 existing work items, all placed. Four new
identifiers added, each justified below.

### Every SEC finding has an owning task

| Finding | Owning task(s) | Status |
|---|---|---|
| SEC-001 | T2.03, T2.04, T2.05 (layer 3), T5.04 (layer 1), T5.07 (layer 2), T7.01 | Fully owned |
| SEC-002 | T2.06, T2.07 (structural), T5.04 + T2.05 (containment), T7.04 (measured) | Fully owned |
| SEC-003 | T5.03, T5.04, T5.06 | Fully owned |
| SEC-004 | T3.04, T3.05 | Fully owned |
| SEC-005 | **T1.05 (new S3-15)**, T6.03 | Was unowned — now owned |
| SEC-006 | T3.01, T3.02, T3.03, T11.07 | Fully owned |
| SEC-007 | T4.03, T4.04, T4.05 | Fully owned |
| SEC-008 | T2.01, T2.02 | Fully owned |
| SEC-009 | T1.10, T2.09 | Fully owned |
| SEC-010 | T11.02, T11.03 | Fully owned |
| SEC-011 | T2.03, T2.04, T5.06, T11.02 | Fully owned |
| SEC-012 | T2.02 | Fully owned |
| SEC-013 | T1.03, T1.07, T2.08, T8.03 | Fully owned |
| SEC-014 | T3.06 (decision), **T6.05 (new S4-17, gate)** | Decision owned; gate was unowned — now owned |
| SEC-015 | T6.04 | Fully owned |
| SEC-016 | T2.11 | Fully owned |
| SEC-017 | T1.11, T2.10 | Fully owned |

All eleven NEG tests are owned: NEG-A (T5.04), NEG-B (T5.03), NEG-C (T5.07), NEG-D (T2.05),
NEG-E (T2.06), NEG-F (T2.07), NEG-G (T4.05), NEG-H (T2.02), NEG-I (T2.08), NEG-J (T2.09),
NEG-K (T2.10).

### Coverage Gaps Found During Decomposition

Four gaps in `plan.md`, each closed by a new work item rather than silently absorbed.

| New ID | Gap | Evidence | Closed by |
|---|---|---|---|
| S3-15 | SEC-005's required controls — enumerated, hash-pinned, wheel-only runtime dependencies, development dependencies excluded, pinned interpreter floor — are assigned to "Slice 3 controls" in the security review but no `plan.md` work item owns them. S4-14 covers drift alerting only, which is detection after the fact, not prevention at install time. | `security-review-architecture.md` SEC-005 row, Slice column "2 (ADR), 3 (controls)"; no S3-xx row names dependency pinning | T1.05 |
| S4-17 | SEC-014's control has two halves. S3-14 resolves *where the denylist lives*. Nothing implements the SC-13 gate itself. S4-14's enumerated gates do not include it. | `plan.md` S3-14 notes "Blocks the sanitization gate design" — the gate it blocks has no work item | T6.05 |
| S5-16 | NFR-16 requires all eighteen `prd.md` documentation items to resolve, and NFR-17 requires a Mermaid diagram. S5-13's traceability matrix covers requirement identifiers, not the documentation inventory. | `plan.md` traceability table maps NFR-15 to NFR-19 to S4-16, S5-10, S5-14, none of which asserts the eighteen-item inventory | T11.08 |
| S5-17 | CON-11 requires quick wins for any customer and SC-12 requires a first useful result in one working session, but both are asserted only as properties of this repository. No work item expresses the engagement-facing order in which a new customer reaches that result, and S5-14's quickstart answers a different question for a different audience. | `plan.md` maps CON-11 and SC-12 to S5-14 alone, whose acceptance is about counted files and steps in the repository quickstart | T11.09 |
| S5-18 | FR-73, FR-74 and SEC-010 require deviations, unconfirmed runtime behaviour and declared-not-enforced limits to be recorded, but every work item that records them draws only on this repository. Nothing checks the contract surface against external reports of how the runtime actually behaves, so a wrong assumption passes every internal check because a check can only test what it was told. | `plan.md` maps FR-73, FR-74 and SEC-010 to S5-11 and S5-12, whose acceptance is the completeness of the registers rather than the truth of what they record | T11.10 |

Two requirements were also **previously unowned within existing work items** and are now
explicitly scoped rather than assumed:

- **FR-07** — error, retry, timeout and incomplete-execution semantics. No `plan.md` work
  item named it. Scoped into S3-04 as task T1.09.
- **FR-57** — contract-level separation of diagnostic output from proposed mutation. Implied
  by S3-04's schema set but never stated. Made explicit in T1.08's acceptance.

### External guidance work items (spec v1.4)

Eleven work items come from assessing the external guidance in `spec.md` v1.4 against this
repository. They carry `SA-xx` identifiers because no `plan.md` work item exists for them.

| Work item | Task | Story | Requirement or decision |
|---|---|---|---|
| SA-01 | T5.09 | US-5 | FR-75, CC-024 |
| SA-02 | T5.10 | US-5 | FR-76, CC-025 |
| SA-03 | T5.11 | US-5 | FR-77, CC-028 |
| SA-04 | T5.12 | US-5 | FR-78, CC-026 |
| SA-05 | T9.04 | US-9 | FR-79 |
| SA-06 | T8.05 | US-8 | FR-80 |
| SA-07 | T8.06 | US-8 | FR-81, CC-027 |
| SA-08 | T11.11 | US-11 | FR-82 |
| SA-09 | T9.05 | US-9 | Open decision, incident routing |
| SA-10 | T7.05 | US-7 | Open decision, delivery of findings |
| SA-11 | T8.07 | US-8 | Open decision, approval backlog signals |

### Requirements deliberately not decomposed

- **SC-11** — carries `[DEFERRED]` in `spec.md` v1.4; no baseline exists. No task.
- **FR-58** — deferred capability; the contract half is covered by T1.08, and no execution
  path is created, which is what T2.02 asserts.
- **CON-12** — creates no work. Its only artifact is the negative assertion in T5.02 that no
  Terraform exists. **No task in this decomposition implements, tests or maintains
  Terraform.**

## Assumptions Made During Decomposition

Stated because they resolved ambiguity without a user decision.

1. **Story boundaries.** `spec.md` defines six user stories. Five additional stories were
   created — US-3 (repository safety), US-6 (CI supply chain), US-7 (security
   documentation), plus splitting spec US-1 into US-1 and US-2 — because the work items in
   those groups trace to NFRs and SEC findings rather than to a user journey, and folding
   them into a journey story would have produced stories that cannot be independently
   tested. `plan.md` explicitly anticipates this: "A DevSecOps or Infrastructure epic does
   not exist on the board... creating it belongs to decomposition."
2. **S3-11 placement.** The zero-core-edit check is scheduled in Slice 3 per `plan.md` but
   is placed in US-9, whose acceptance it gates. The task carries its Slice 3 label.
3. **Priority labels.** Not created, because `.memory/board-config.md` records that no
   `priority:` convention exists in the repository. Priority is carried in the story title.
4. **`slice:` label added.** Not in the board config, but the plan sequences all work by
   slice and the board would otherwise carry no execution order.
5. **`zeroops` command name.** Used throughout as `plan.md` uses it, provisionally, and is
   confirmed when S3-12 lands (T1.14).
6. **Tracer bullet.** T1.01 deliberately spans five work items to produce a walking skeleton
   that runs end to end before any of those work items is individually complete. Each of
   those work items still has its own task; T1.01 delivers the thinnest path through them.

## References

- [plan.md](plan.md) — Slices 3, 4, 5 work item tables
- [spec.md](spec.md) v1.4 — FR-01 to FR-82, NFR-01 to NFR-26, CON-01 to CON-12,
  SC-01 to SC-13, CC-001 to CC-028, CC-C01, Invariants
- [security-review-architecture.md](security-review-architecture.md) — SEC-001 to SEC-017,
  NEG-A to NEG-K
- [data-model.md](data-model.md), [contracts/schema-register.md](contracts/schema-register.md)
- [Architecture overview](../../architecture/overview.md),
  [Minimum SRE Agent Contract](../../architecture/minimum-sre-agent-contract.md)
- ADR-0001, ADR-0002, ADR-0003, ADR-0004

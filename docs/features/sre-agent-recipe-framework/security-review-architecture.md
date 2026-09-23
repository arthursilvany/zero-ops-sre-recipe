# Architectural Security Review — SRE Agent Recipe Framework

**Mode**: Architectural (design-level; no implementation exists yet)
**Date**: 2026-09-23
**Phase**: Plan, before task decomposition
**Verdict**: `APPROVED_WITH_CONTROLS`
**Reviewed**: `prd.md`, `spec.md` v1.2, `overview.md`, `minimum-sre-agent-contract.md`,
ADR-0001, ADR-0002, ADR-0003, ADR-0004 (Proposed), `source-analysis.md`

## Verdict

Approved with controls. No Critical findings. Six High findings. Nothing found requires
reversing ADR-0001, ADR-0002 or ADR-0003.

The safety architecture is sound in intent: deny-by-default with deny-wins and fail-closed,
an evidence chain bound to a scope hash, negative tests placed *before* the deployment gate
rather than after, and remediation defined-but-unimplemented so that enabling it later is
additive rather than breaking.

The concern is not the intent but the **verification substrate**. The framework's safety
argument is evidentiary — it claims safety because negative tests prove it — which makes
the quality of the tests, not the quality of the intent, the security property under
review. Eleven requirements marked `Automated` cannot fail as currently written. A
negative test that passes against the framework's own fixture while the runtime behaves
differently is worse than no test, because it converts an open risk into false assurance.

**Root pattern behind every High finding**: the framework declares a control that a system
it does not own enforces, then verifies the declaration rather than the enforcement.

**Uniform remedy**: relocate authority to the one layer the framework controls end to end —
the RBAC grant and the compiled ARM output — and demote everything above it to
defence-in-depth that is *reconciled* against the runtime rather than assumed to match it.

## Trust Boundaries

| Boundary | Crossing | Data | Modelled before this review |
|---|---|---|---|
| Operator workstation to Azure control plane | `az` invocations under operator credentials | Subscription-wide inventory | No |
| Upstream repository to operator workstation | Fetched Bicep plus executable lifecycle scripts run with live credentials | Code | Partially — pinned, integrity unspecified |
| Package registry to operator workstation | Tooling dependency tree | Code | No |
| Workload telemetry to agent reasoning context | Logs, exception text, pull-request bodies, tags | Untrusted, attacker-influenceable | Yes (CON-07, FR-55) |
| Agent identity to workload resources | Tool calls, RBAC | Read-only claim | Yes (FR-33) |
| Discovery output to consumer repository | Real resource identifiers, names, tags | Customer-identifying | No |
| Private repository history to public visibility | Every commit ever made | Everything | No |

The four previously unmodelled boundaries carry four of the six High findings.

## The Five Threats Required by NFR-05

| Threat | Planned mitigation | Test | Sufficient |
|---|---|---|---|
| Prompt injection | Untrusted content never enters the instruction region | CC-019 | No — a probabilistic property asserted by a single sample. Reframe from prevention to containment (SEC-002) |
| Unsafe tool invocation | Deny-by-default tool policy | CC-016, CC-021 | No — exercises the framework's evaluator, not the runtime, using identifiers the source declares unconfirmed (SEC-001) |
| Excessive permissions | Read-scoped roles, managed identity | CC-009 | Partial — blind to what a consumer-supplied existing identity already holds elsewhere (SEC-003) |
| Data leakage | External secret references, sanitization scanning | CC-020 | Partial — silent on git history and on the discovery intermediate artifact (SEC-006, SEC-007) |
| Untrusted diagnostic content | Content is data, never instruction | CC-019 | Partial — the structurally testable half, that evidence stores a content hash and never the content, is implicit rather than required (SEC-002) |

## Findings

| ID | Severity | Finding | Affected | Required control | Slice |
|---|---|---|---|---|---|
| SEC-001 | High | Tool-policy enforcement rests on capability identifiers the source explicitly declares unconfirmed, against a runtime whose documented default inherits global tools including write tools when explicit selection is omitted. "Unlisted" and "unknown" are conflated: an allow-list denies what it names, not what it cannot see. | FR-51, FR-52, CC-021 | Three layers in this order of authority. One: RBAC is ground truth — the read-only guarantee derives from the role grant, so a mis-named identifier cannot produce a write because Azure Resource Manager denies it. Two: a reconciliation gate enumerates the capability set advertised by the pinned runtime and fails closed on any unclassified capability, with the reconciled set hashed per runtime version. Three: assert that the emitted binding always carries an explicit tool list. Until layer two runs against a real runtime, document the policy as declared, not runtime-verified (FR-74). | 3 (layers 1 and 3), 4 (layer 2) |
| SEC-002 | High | FR-55 and CC-019 assert a probabilistic property as a deterministic release gate. "Must not alter agent behavior" is not falsifiable by one sample against a language model. The strongest-sounding safety claim is the weakest-evidenced. | FR-55, CON-07, CC-019, SC-06 | Split into three. Structural and gating: no code path admits retrieved content into the instruction region; evidence persists hash and classification, never raw content; assert statically over core paths. Containment and gating: blast radius is zero because the capability set and the RBAC grant make the action impossible — this is SEC-001 layer one. Empirical and non-gating: an injection corpus run against a deployment, reported as a measured rate with evidence, never claimed as proof. | 3 (structural), 4 (containment, measurement) |
| SEC-003 | High | FR-34 permits binding to a consumer-supplied existing identity that may already hold Contributor or Owner elsewhere in the tenant. FR-33 is satisfied — the core grants no write role — while the deployed agent nonetheless holds write capability. The read-only invariant breaks silently and CC-009 cannot see it. | FR-33, FR-34, CC-009, Invariant 1 | Preview must enumerate every existing role assignment held by a supplied principal, at every scope, and require explicit confirmation. Post-deployment validation must fail when the agent principal holds any non-read role anywhere in the subscription, not merely on declared scopes. | 3 (logic), 4 (gate) |
| SEC-004 | High | ADR-0001 pins by commit or tag and deliberately does not vendor, so the operator fetches and executes upstream lifecycle scripts locally while holding live Azure credentials. A git tag is mutable and is not an integrity control. Upstream is preview-era. | ADR-0001, NFR-06 | Pin by immutable commit digest only and reject tag-only pins in CI. Record a digest of the fetched tree and verify it before any script executes; mismatch fails closed. Document the acquisition step as a trust-boundary crossing. Treat an upstream bump as a security-reviewed change, not a version bump. | 3 |
| SEC-005 | High | Any third-party dependency tree installed on the operator workstation lands on the highest-privilege boundary in the system and inside the component that computes the scope-contract hash. | ADR-0004, CON-06 | Carried into ADR-0004: minimal enumerated runtime dependencies, hash-pinned and wheel-only so no code executes at install time, development dependencies excluded from the runtime path, a pinned interpreter floor, and drift plus vulnerability alerting as CI gates. ADR-0004 selecting a runtime the operator already installs reduces but does not eliminate this surface. | 2 (ADR), 3 (controls) |
| SEC-006 | High | Git history is outside every sanitization requirement. A working-tree scan passes while a secret or a real subscription identifier remains in an earlier commit — and the repository is private today and expected to become public. | NFR-01, NFR-02, NFR-04, SC-05, Invariant 8 | Secret and identifier scanning runs over full history, not the working tree, and is an explicit precondition of NFR-04. Enable platform secret scanning with push protection in addition to the CI job, because a CI job runs after the push has already landed. Define the history-rewrite remediation path before the first commit that could need it. | 3, effective immediately |
| SEC-007 | Medium-High | The discovery intermediate artifact is an unmodelled leak path. ADR-0003 requires discovery output to be reviewable and diffable separately from selection, which means a subscription-wide inventory of real identifiers, names and tags is written into the consumer's repository. Tags are a well-known place operators stash connection strings. | FR-10, FR-13, FR-17, NFR-01, CC-020 | Discovery output defaults to an ignored path, carries a header stating it contains real identifiers, and has a documented redaction mode for bug reports. The emitter field-allow-lists what flows from a discovery row into the scope contract and never copies the row. Add a negative test that a secret-shaped tag value cannot reach the emitted contract. | 4 |
| SEC-008 | Medium | FR-11 is marked `Automated` but names no mechanism by which the automated half could work. Absent one it is inspection only. | FR-11, CC-006 | Route all Azure invocations through a single command broker restricted to a read-only verb allow-list; a static check over call sites fails the build on any invocation outside it. This makes CON-02 mechanically true for the wizard rather than merely intended. | 3 |
| SEC-009 | Medium | Canonicalisation defines byte ordering; it does not define the digest. Algorithm, encoding, self-exclusion of the hash field, Unicode normalisation and line-ending handling were all unspecified, leaving FR-19 and FR-23 unverifiable. | FR-19, FR-23, FR-44, Invariant 7 | Resolved in ADR-0004, which pins all six, plus a cross-platform determinism test. | 2 (ADR), 3 (test) |
| SEC-010 | Medium | The reference source had a signed scope-contract workflow that was deprecated in favour of a bare hash. A hash detects accidental drift; it authenticates nothing. A modified contract with a recomputed hash is indistinguishable from an approved one. | FR-23, FR-73, FR-74 | Acceptable under a read-only v1, but record explicitly as a deviation with rationale and as a known limitation. Signing becomes required the moment FR-58 is implemented, because at that point the hash is what authorises a change. | 5 (documentation) |
| SEC-011 | Medium | FR-53's execution limits are declared by the framework and enforced by the runtime. "All four limits are configurable and enforced" is not provable by the framework. | FR-53, CC-012 | Classify as declared-not-enforced in the known-limitations document, and verify through the post-deployment tool-policy-posture check rather than a local automated gate. | 3 |
| SEC-012 | Medium | CC-018 requires proving a negative. Non-existence is not testable by exercising behaviour. | FR-06, CC-018, CON-02 | Reframe as a static structural assertion over declared core paths: no symbol, module or import applies a change-set, and no write-capable Azure verb appears in core or wizard source. That is executable and genuinely gating. | 3 |
| SEC-013 | Medium | Leak prevention is specified as scanning. Scanning detects known shapes; structure prevents the class. | FR-30, FR-49, CC-020 | Make it structural and lint it: every schema sets `additionalProperties: false`; no schema declares a free-form workload-payload field; no property name matches a secret-bearing pattern. Ship ignore rules covering the upstream secrets-file pattern on day one, with a test asserting coverage. | 3 |
| SEC-014 | Medium | SC-13 is measured by a gate that scans the core for customer-specific vocabulary — and committing that denylist to a repository destined to become public discloses exactly what it exists to protect. The control is self-defeating as specified. | SC-13, NFR-03 | Hold the vocabulary denylist outside the repository, or match on salted hashes of the forbidden terms rather than the terms themselves. Resolve before the sanitization gate is built. | 3 |
| SEC-015 | Medium | The quality gates say nothing about the CI supply chain itself, though the workflows will hold credentials that touch a customer subscription. | NFR-06, NFR-14, CON-06 | Pin all workflow actions by commit digest; least-privilege permissions on every workflow; no workflow trigger that checks out an untrusted ref with elevated rights; satisfy NFR-14 through federated credentials with no long-lived secrets. | 4 |
| SEC-016 | Low | FR-56 compares decider against agent identity. If identity is a display name or a configured string, self-approval is defeated by renaming. | FR-56, CC-017, Invariant 3 | Bind the comparison to the managed identity principal object identifier, never a name or label. Record that CC-017 guards a capability that does not exist in v1 and therefore tests the validator, which is correct and worth stating. | 3 |
| SEC-017 | Low | Maximally actionable validation errors commonly echo the rejected value, which is sometimes the secret. | FR-16, FR-38, FR-49 | Error messages name the path and the expected shape, never the supplied value, for any secret-bearing or identifier-bearing field. | 3 |

## Requirements Unverifiable As Written

These are marked `Automated`, or asserted as measurable, but cannot be discharged as
stated. Each must be reworded before task decomposition, or the release gate will pass on
false evidence. The rewording is a specification amendment and is tracked as such in
`plan.md`.

| Requirement | Why unverifiable | Remedy |
|---|---|---|
| FR-51, CC-021 | Asserts runtime behaviour using unconfirmed identifiers; the evaluator is not the runtime | SEC-001 |
| FR-55, CC-019 | Probabilistic system, single sample, presented as deterministic | SEC-002 |
| FR-53, CC-012 | Enforcement belongs to the runtime, not the framework | SEC-011 |
| FR-11 | Names no mechanism for the automated half | SEC-008 |
| FR-33, CC-009 | Audits grants, not the principal's effective permissions | SEC-003 |
| FR-19, FR-23 | "Byte-identical" undefined without pinned canonicalisation rules | SEC-009, resolved in ADR-0004 |
| CC-018 | Requires proving non-existence behaviourally | SEC-012 |
| FR-49 | Absence of a known pattern is not absence of a secret | SEC-013 |
| NFR-01, NFR-04, SC-05 | Silent on git history | SEC-006 |
| SC-13 | Requires committing the denylist that constitutes the disclosure | SEC-014 |
| SC-08 | Sampling one execution cannot establish a universal | Restate as a per-execution schema invariant enforced at validation, with sampling as corroboration |

## Negative Tests Required Beyond CC-016 to CC-021

CC-016 to CC-021 identify the right four safety boundaries but are not a sufficient v1
release gate, because they test the framework's own artifacts rather than the system.

| ID | Test | Closes | Credential-free |
|---|---|---|---|
| NEG-A | Parse the compiled ARM of the composed deployment; every role definition identifier must appear in a read-only allow-list | SEC-003, SEC-001 layer 1 | Yes |
| NEG-B | A supplied existing identity holding any non-read role anywhere in the subscription blocks the preview | SEC-003 | No |
| NEG-C | Any capability advertised by the pinned runtime that the policy does not classify fails the build | SEC-001 | No |
| NEG-D | An emitted binding lacking an explicit tool list fails | SEC-001 | Yes |
| NEG-E | Static: no retrieved or diagnostic content reaches the instruction or prompt-assembly region in any core path | SEC-002 | Yes |
| NEG-F | Evidence entries carry a content hash and classification, never raw retrieved content | SEC-002 | Yes |
| NEG-G | A secret-shaped tag value present in a discovery row cannot reach the emitted scope contract | SEC-007 | Yes |
| NEG-H | Static: no write-capable Azure verb appears in any core or wizard call site | SEC-008, SEC-012 | Yes |
| NEG-I | Every schema sets `additionalProperties: false` and declares no secret-named property | SEC-013 | Yes |
| NEG-J | The same input yields the same canonical digest on Windows and on Linux | SEC-009 | Yes |
| NEG-K | A validation error for a secret-bearing field names the path and shape but never the supplied value | SEC-017 | Yes |

## Effect on Accepted Decisions

| ADR | Security effect | Action |
|---|---|---|
| ADR-0001 | The operator executes remotely fetched scripts with live credentials; upstream least privilege is only partially specified | SEC-004, NEG-A. No reversal |
| ADR-0002 | Net positive. The compiled ARM is what makes NEG-A possible offline, and having no Terraform state removes a state-secret handling obligation inside the customer tenant — a security benefit the ADR argues only on operational grounds | State it in the security model; it strengthens the decision |
| ADR-0003 | Net positive: lowest permission bar, read-only, no form hiding the deployment model. Creates the discovery-artifact leak path | SEC-007. Its "no new runtime" claim is made true by ADR-0004 rather than left assumed |
| ADR-0004 | Selecting a runtime the operator already installs reduces the workstation trust surface relative to the alternative | SEC-005 and SEC-009 are carried inside the ADR, not deferred to a task |

## Controls Recognised As Already Correct

Recorded deliberately, because the design gets several hard things right that commonly go
wrong.

- Negative tests gate the deployment rather than follow it. This ordering is correct and
  is rare.
- Denial is built and proven before the capability it guards exists.
- Missing data is recorded as missing, never estimated, defaulted or zeroed, and absence
  of access is never resolved by requesting or assuming permission. This closes the
  standard agent escalation path by contract.
- Evidence carries a content hash rather than content, with a data classification per
  entry. This is the right structural answer to both leakage and injection.
- Credential-free offline validation removes the deploy-to-discover-you-were-wrong loop,
  which is a security property and not merely a usability one.
- Single-subscription read-only discovery is the lowest defensible permission bar, and
  separating discovery permissions from runtime permissions is explicit rather than
  accidental.

## Threats Considered and Deliberately Not Raised

- **Evidence manifest tampering** — real, but out of scope for a read-only v1 with no
  approval workflow. Folded into SEC-010 as the trigger condition for signing.
- **Denial of service through unbounded agent execution** — already addressed by the four
  execution limits; the gap is enforcement authority (SEC-011), not the control itself.
- **Cross-subscription escalation** — structurally excluded by the single-subscription v1
  scope. Must be re-reviewed when discovery breadth widens.
- **Repudiation** — adequately covered by the execution-identifier and scope-hash binding.
- **Terraform state secrecy** — CON-12 means this repository owns no Terraform; recorded
  instead as a security benefit of ADR-0002.

## References

- `prd.md` — section *Security and Responsible AI Requirements*
- `docs/features/sre-agent-recipe-framework/spec.md`
- `docs/features/sre-agent-recipe-framework/plan.md`
- `docs/architecture/overview.md`, `docs/architecture/minimum-sre-agent-contract.md`
- `docs/architecture/source-analysis.md` — sections 2.5, 2.9, 2.10, 3.5 to 3.8, 5.1, 5.4,
  7.1, 7.2
- ADR-0001, ADR-0002, ADR-0003, ADR-0004
- `SECURITY.md`

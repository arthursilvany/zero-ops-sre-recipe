# Minimum SRE Agent Contract

**Status**: Draft
**Date**: 2026-09-23
**Satisfies**: FR-01, FR-02
**Binds to**: [ADR-0001](decisions/0001-upstream-template-relationship.md),
[ADR-0002](decisions/0002-infrastructure-as-code.md),
[ADR-0003](decisions/0003-guided-deployment-experience.md)

## Purpose

`prd.md` lists 25 candidate areas for the minimum SRE agent contract and explicitly
instructs that **not every candidate area is mandatory**. Each must be classified as
Required, Recommended, Optional or Out of scope, with recorded rationale and evidence.

This document performs that classification. It defines what a configuration must declare to
be a valid SRE agent under this framework, independently of any runtime. Per CON-03, the
contract is runtime-agnostic; `agent.json` is the concrete binding (ADR-0001) and appears
only in the binding layer.

## How to Read These Classifications

**Obligation levels:**

| Level | Meaning |
|-------|---------|
| **Required** | A configuration that omits this area is invalid. Schema validation fails. |
| **Recommended** | Valid without it, but validation emits a warning and the quickstart provides it. Production readiness assumes it. |
| **Optional** | Declared only when the consumer needs it. Absence is silent and normal. |
| **Out of scope** | Not part of this contract in any form. |

**Two axes, deliberately separated.** Several areas are Required *as a declared contract*
while their behavior is *not implemented in v1*. This is not a contradiction — it is CON-02.
The core is read-only in v1, and remediation is a defined contract plus an unimplemented
extension point. Declaring the contract now is what prevents a breaking change later.
The summary table therefore carries both an obligation and a v1 implementation state.

**The quick-wins filter (CON-11).** An area is pushed down from Required to Recommended or
Optional when requiring it would force a customer to author something bespoke before seeing
a first useful result. The test applied throughout: *can a customer nobody has met before
reach a useful read-only result in one working session without writing code?* Anything that
answers "no" belongs in a consumer-supplied extension, not in the required core.

## Summary Classification

| # | Candidate area | Obligation | v1 implementation | Primary evidence |
|---|----------------|-----------|-------------------|------------------|
| 1 | Agent identity and metadata | **Required** | Implemented | Present in both sources |
| 2 | Workload context | **Required** | Implemented | Scope contract; upstream target scopes |
| 3 | Supported operational scenarios | Recommended | Implemented | Declared in one source only |
| 4 | Instructions and behavioral boundaries | **Required** | Implemented | Both sources; CON-07 |
| 5 | Tool definitions | **Required** | Implemented | Deny-by-default depends on enumeration |
| 6 | Authentication and authorization | **Required** | Implemented | Managed identity in upstream modules |
| 7 | Least-privilege role assignments | **Required** | Implemented | Dedicated upstream module |
| 8 | Data-source connections | **Required** | Implemented | Without a source there is no diagnosis |
| 9 | Observability of the agent itself | Recommended | Implemented | Optional in upstream lifecycle |
| 10 | Health checks | Recommended | Implemented | Upstream verification entry point |
| 11 | Incident detection | Optional | Extension point | Absent from both sources as an agent duty |
| 12 | Diagnostic collection | **Required** | Implemented | The core value of a read-only v1 |
| 13 | Remediation actions | **Required** as contract | **Not implemented** | CON-02 |
| 14 | Human approval gates | **Required** as contract | Enforced by denial | Approval ledger; no self-approval |
| 15 | Audit trail | **Required** | Implemented | Evidence manifest with content hashing |
| 16 | Error handling | **Required** | Implemented | FR-38; fail-closed posture |
| 17 | Retry and timeout behavior | Recommended | Implemented | Execution limits in tool policy |
| 18 | Configuration schema | **Required** | Implemented | Present in one source, absent upstream |
| 19 | Deployment assets | **Required** | Implemented | ADR-0002 |
| 20 | Validation tests | **Required** | Implemented | SC-06, SC-07; upstream validation workflow |
| 21 | Runbooks | Recommended | Partially | Quickstart required; per-scenario runbooks are extensions |
| 22 | Security guidance | **Required** | Implemented | CON-06; `prd.md` security section |
| 23 | Operational ownership | Recommended | Implemented | Declared by consumer; absent from both sources |
| 24 | Versioning and upgrade guidance | **Required** | Implemented | ADR-0001 version pinning makes it unavoidable |
| 25 | Rollback and cleanup guidance | **Required** | Implemented | SC-09, FR-66 to FR-70 |

**Totals**: 18 Required, 6 Recommended, 1 Optional, 0 Out of scope.

Of the 18 Required areas, 2 (remediation actions and human approval gates) are Required as a
declared contract only, with behavior deliberately unimplemented in v1.

No candidate area was classified Out of scope. Each earned at least Optional status on
evidence. Where an area is not part of the *core*, it is retained as a declared extension
point rather than discarded, because discarding it would make later support a breaking
change.

## Rationale and Evidence by Area

### 1. Agent identity and metadata — Required

Both reference sources carry it independently: the upstream agent definition exposes an
identity block, and the reference suite's agent definitions carry a name and description.
Nothing downstream works without it — evidence entries, audit records and role assignments
all need a stable subject to attribute to. Omission makes the audit trail unattributable,
which breaks area 15.

### 2. Workload context — Required

This is what makes the recipe reusable rather than customer-specific, so it carries CON-11
directly. The reference suite expresses it as a scope contract declaring resource types and
boundaries; upstream expresses it as operator-supplied target scopes. ADR-0003 makes the
guided wizard emit exactly this artifact.

It is Required and **consumer-owned**: the framework ships the schema and never ships real
values. This is the seam that keeps the core customer-agnostic (SC-13).

### 3. Supported operational scenarios — Recommended

Declared explicitly in the reference suite, which defines assessment and readiness flows.
Upstream implies scenarios through its recipes but never declares them as a contract field.

Recommended rather than Required because an agent with tools, instructions and a data source
produces useful output without a formal scenario declaration, and requiring consumers to
enumerate scenarios up front is exactly the bespoke-authoring step CON-11 rejects. The
framework ships default scenarios so the quick win needs no authoring; declaring custom ones
is how a consumer narrows or extends.

### 4. Instructions and behavioral boundaries — Required

Present in both sources. Required for two independent reasons. First, behavior is
undetermined without it. Second and more important, CON-07 requires that untrusted
diagnostic content never be treated as instructions — that boundary has to be stated
somewhere enforceable, and this is where.

### 5. Tool definitions — Required

A deny-by-default policy is meaningless unless the permitted capability set is enumerated,
so this area is a precondition for area 22. The reference suite enumerates allowed tools and
skills; upstream exposes capability toggles.

**This area is defence-in-depth, not the read-only guarantee.** The architectural security
review (SEC-001) corrected an earlier framing here: the guarantee derives from the role
grant in area 7, because an allow-list denies what it *names*, not what it cannot see, and
the documented runtime default inherits global tools — including write tools — when explicit
selection is omitted. Treating the tool policy as the primary control would make the safety
claim depend on identifiers that may be wrong.

Carried risk, recorded rather than hidden: the reference suite states that its runtime tool
identifiers are **unconfirmed** against the real runtime. Until a reconciliation gate has
run against a real runtime and failed closed on any unclassified capability, the policy is
documented as **declared, not runtime-verified**. Reconciling identifiers is required before
the tool-policy enforcement model is settled, and that reconciliation remains an open
decision in the spec.

### 6. Authentication and authorization — Required

Upstream provisions a managed identity as part of the core module. CON-06 mandates managed
identity and forbids committed secrets, so a configuration that leaves authentication
undeclared cannot be validated against the security constraint. There is no credential-free
alternative that still permits reading customer telemetry.

### 7. Least-privilege role assignments — Required

Upstream ships a dedicated module for target-scope role assignments, which is direct
evidence that this is a first-class deployment concern rather than an afterthought. In a
read-only v1 the grants are read-scoped, and that narrowness is the entire safety argument.
Leaving assignments implicit would mean either over-granting or a non-functional agent.

**This area, not area 5, carries the read-only guarantee.** The architectural security
review (SEC-001) established the order of authority: RBAC is ground truth, because Azure
Resource Manager denies a write regardless of what the agent believes it may do. The tool
policy in area 5 is defence-in-depth layered above it, not the primary control. The
distinction matters because area 5 depends on capability identifiers the reference source
declares unconfirmed — if those identifiers are wrong, the tool policy silently weakens,
and only the role grant still holds.

A consequence recorded by SEC-003 and carried into planning: binding to a
consumer-supplied existing identity can break this guarantee invisibly, because that
principal may already hold write roles elsewhere in the tenant. Validation must therefore
assert the absence of non-read roles across the subscription, not merely the absence of
write grants made by this framework.

### 8. Data-source connections — Required

Upstream ships connector configuration in its minimal recipe, which is the strongest
available signal: the *minimal* case still includes it. An SRE agent with no data source
produces no diagnosis, so this cannot be Recommended without making the first useful result
unreachable.

Credentials are held externally by reference; the connection declaration itself is committed.

### 9. Observability of the agent itself — Recommended

Upstream treats workspace and application-insights wiring as **optional** environment
inputs in its lifecycle definition. That is direct evidence that a deployment succeeds
without it.

Recommended rather than Required because of CON-11: requiring a customer to have a workspace
provisioned and wired before the first run adds a prerequisite that blocks the quick win.
Production readiness assumes it, and the quickstart provides it — but a first result does
not depend on it.

Note the distinction from area 15. This area covers observing *the agent*; area 15 covers
the defensible record of *what the agent concluded*. The second is Required, the first is
not.

### 10. Health checks — Recommended

Upstream ships a verification entry point, establishing post-deployment verification as an
existing practice.

Split deliberately: **post-deployment verification is Required**, but it is covered by area
20 rather than here. What remains in this area is *continuing* health checking, which is
Recommended — valuable in production, not needed to reach a first result.

### 11. Incident detection — Optional

Neither source assigns detection to the agent. Detection is already owned by the customer's
existing alerting stack, and in a read-only v1 the agent is invoked rather than watching.

Optional rather than Out of scope because a consumer may legitimately wire detection into a
workload extension, and the contract should not have to change to permit that. Classifying
it Out of scope would turn later support into a breaking change for no benefit.

### 12. Diagnostic collection — Required

This is the core value proposition of a read-only v1 — the thing the agent actually does.
The reference suite contributes a reviewed, integrity-verified query catalogue as the
mechanism.

Required, with an important split preserving CON-11: the *capability* is Required and ships
with defaults, while the *queries* are a workload extension point. A customer gets a useful
result from shipped defaults without authoring anything, then narrows or extends.

### 13. Remediation actions — Required as contract, not implemented in v1

CON-02 is explicit: mutating remediation is a defined contract plus an extension point,
explicitly not implemented. The change-set entity in the spec already carries preconditions,
blast radius, rollback plan, verification method and a canonical hash.

Required *as a declared contract* precisely because it is unimplemented. Defining the shape
now means enabling remediation later is additive. Leaving it undefined would guarantee a
breaking change at the moment the framework is most widely deployed.

Enforcement in v1 is negative: a negative test proves change-set execution is impossible.

### 14. Human approval gates — Required as contract, enforced by denial in v1

The reference suite contributes an append-only approval ledger referencing the hash of the
approved artifact, with agents unable to self-approve.

Required as contract for the same reason as area 13. In v1 there are no mutations to
approve, so the requirement manifests as an enforced prohibition rather than a workflow: a
negative test proves self-approval is denied. This ordering matters — the denial is built
and proven before the capability it guards exists.

### 15. Audit trail — Required

The reference suite contributes the strongest pattern found in either source: an evidence
manifest binding every observation to an execution identifier, scope hash, provenance
classification, timestamp, freshness state, data classification and content hash.

Required because SC-08 demands that every conclusion resolve to an evidence entry or carry
an explicit non-observed classification. Without this area that criterion is unverifiable,
and the framework's central claim — defensible conclusions — collapses to assertion.

### 16. Error handling — Required

FR-38 requires that deployment errors identify the failing step, the probable cause and the
documented recovery action. CON-06 requires fail-closed behavior.

Required because silent or ambiguous failure is the specific failure mode CON-11 cannot
tolerate: a customer hitting an unexplained error in the first session does not get a quick
win, they get an abandoned evaluation. The reference suite's fail-closed posture applies —
an unresolvable condition is reported and excluded, never silently included.

#### Failure class to execution state

FR-07 requires that every failure class map to a defined state value. The mapping is total
in both directions: every bullet in the specification's *Failure Modes* section appears
below, and every terminal state other than `completed` is produced by at least one class. A
state no class can reach would be a value the contract defines and nothing can ever set.

| Failure class | Execution state | Retryable | Source |
|---|---|---|---|
| `discoveryProviderUnavailable` | `failed` | Yes | Failure Modes |
| `deploymentPartiallyApplied` | `incomplete` | Yes | Failure Modes |
| `roleAssignmentNotYetEffective` | `incomplete` | Yes | Failure Modes |
| `dataSourceUnreachable` | `incomplete` | Yes | Failure Modes |
| `concurrentScopeConflict` | `failed` | No | Failure Modes |
| `frameworkVersionIncompatible` | `failed` | No | Failure Modes |
| `executionLimitReached` | `incomplete` | No | Edge Cases |
| `accessNotGranted` | `accessDenied` | No | Failure Modes, derived distinction |

The consistency-model bullet maps to no state. It records which operations are eventually
consistent and states that contract validation is immediate, which is a property of the
system rather than an outcome a run can reach. It is listed in the registry with that reason
rather than omitted, because a bullet absent from the registry and a bullet deliberately
excluded from it are otherwise the same thing.

Two distinctions carry weight. `incomplete` is not a weaker `failed`: every reason mapping to
it left partial work that remains valid, and calling a partly applied deployment failed would
imply nothing was applied. `roleAssignmentNotYetEffective` and `accessNotGranted` are separate
because the specification requires validation distinguish permission that is still propagating
from permission that does not exist; collapsing them turns a deployment that is still settling
into one that looks misconfigured.

The mapping is enforced by `contracts/schemas/handoff-record.schema.json` rather than stated
here alone. A record whose `executionState` is `incomplete` admits only the four reasons that
produce it, a `completed` record cannot carry a termination reason at all, and only a
`completed` record may carry a `completedAt`. `tools/zeroops/failure_modes.py` holds the
registry, and a test parses the specification so that a bullet added there and never
classified fails rather than drifts.

#### Incomplete execution

An incomplete execution is represented by three things together, not by a flag. The
`executionState` is `incomplete`, a `terminationReason` from the incomplete subset says which
limit or gap stopped it, and `completedAt` is absent. The absence is load-bearing: a
substituted end time would let an incomplete run join, sort and report exactly like one that
finished. At the entry level the counterpart is an evidence entry with `observationState` set
to `unobserved` and an `unobservedReason`, which carries no content hash at all rather than a
zero digest. No value is extrapolated to fill either gap.

### 17. Retry and timeout behavior — Recommended

The reference suite declares execution limits within its tool policy, so there is precedent.

Recommended rather than Required because sensible framework-level defaults make explicit
declaration unnecessary for a first result, while production deployments against rate-limited
data sources will need to tune it. Declaring nothing must be safe, so defaults are
conservative and fail closed on exhaustion rather than retrying unbounded.

Timeout is declared in the tool policy as `executionLimits`, covering tool-call count,
wall-clock duration, result-set size and per-query timeout, as FR-53 enumerates. Retry is
declared alongside it as `retryPolicy`, carrying an attempt ceiling and a backoff strategy.

Which failure classes are retryable is not declared there and cannot be. Retryability is a
property of the class, fixed by the table above, because a policy able to mark a denied grant
retryable would turn a settled finding into a loop. The handoff record carries `attempt` and
`maxAttempts` so that a record can be shown to have respected a ceiling, and a record whose
attempt exceeds one while naming an unretryable reason is rejected by the validator: it spends
a budget that a genuinely transient failure would have needed.

`attempt` is separate from `turn` on purpose. A turn advances the work and an attempt repeats
it, so collapsing the two would make a retry of turn 3 indistinguishable from turn 4, which is
the difference between repeating an observation and making a new one. The idempotency key is
what lets a retried handoff be recognised as the same logical work.

### 18. Configuration schema — Required

The sharpest asymmetry found in the source analysis: the reference suite ships formal JSON
Schema 2020-12 contracts, and **upstream ships no formal schema at all**.

Required, and it is the single most load-bearing area in this contract. It is what makes
SC-07 achievable — authoring and fully validating a configuration with no subscription and
no credentials. That credential-free local validation is also what makes the quick win
safe to attempt: a customer can be certain their configuration is valid before touching
their environment.

#### A directory is a configuration set

A configuration is a set of artifacts, not a file. Each member validates on its own, and a
set whose members all validate can still be incoherent, because no per-artifact rule can
reach another document. A framework configuration naming a tool policy that no shipped file
defines is the concrete case: it validated for as long as both examples existed.

Every reference-shaped property in `contracts/schemas/` is therefore classified in
`tools/zeroops/references.py`, which is total. A property is resolved in exactly one of
three places, and a property with no entry fails the suite rather than going unchecked.

| Resolution | Meaning | Example |
|---|---|---|
| `withinDocument` | The name is defined in the same document, and the per-artifact semantic rule already resolves it | `framework-config.subscriptionRef` |
| `acrossSet` | The name is defined by another artifact in the same directory | `framework-config.toolPolicyRef` |
| `runtimeProduced` | The reference exists only in an emitted artifact, so a configuration set has nothing to resolve it against | `assessment-result.evidenceRefs` |

The set pass is gated on every member validating structurally, for the same reason the
semantic pass is gated on one document validating structurally. A malformed connector still
defines the name its bindings point at, but nothing can read it, so resolving around it
would report every binding as broken and bury the one fault that is real.

A directory holding one artifact is still a set. Checking is not skipped for it: that is
precisely the case where nothing else is present to define the name being referenced.

### 19. Deployment assets — Required

ADR-0002 settles the form: Bicep as primary, composed from pinned upstream modules rather
than re-authored, with ARM JSON only as compiled output and no Terraform implementation
work owned here.

Required because reproducibility (SC-04) demands every provisioned resource trace to a
committed input.

### 20. Validation tests — Required

Three independent drivers. SC-06 makes negative tests covering the safety boundary a release
gate. SC-07 requires credential-free local validation. Upstream already ships a template
validation workflow, so the practice exists to extend.

Required and non-negotiable: the read-only guarantee is a claim until a negative test proves
write denial, self-approval denial, change-set execution denial and untrusted-content
handling. This area is what converts the safety argument into evidence.

### 21. Runbooks — Recommended

Split by audience. The **quickstart is Required** and lives under area 25's documentation
obligations, because CON-11 makes it the artifact the quick win depends on.

Per-scenario operational runbooks are Recommended, because they are workload-specific by
nature. Requiring them would force bespoke authoring before a first result, and would push
customer-specific content toward the core, violating SC-13.

### 22. Security guidance — Required

CON-06 and the `prd.md` security section make the posture mandatory: deny-by-default,
fail-closed, least privilege, managed identity, no committed secrets, placeholders only.
`SECURITY.md` already exists in this repository with repo-specific secure-by-default rules.

Required because the framework is designed to be deployed into other organizations'
subscriptions. Guidance that is implicit in that setting is guidance that will be missed.

### 23. Operational ownership — Recommended

**Neither source declares it**, which is itself the finding — ownership is organizational
and cannot be shipped by a framework.

Recommended and consumer-declared: the contract provides the field so ownership is
recordable and auditable, but the framework cannot supply a value and must not block a first
result waiting for an organizational decision.

### 24. Versioning and upgrade guidance — Required

ADR-0001 pins the upstream template version. That decision makes this area unavoidable: a
pinned dependency without a defined upgrade procedure is a liability, not a control.

Required. The procedure includes a compatibility test over the Bicep path, per ADR-0002.

### 25. Rollback and cleanup guidance — Required

SC-09 requires that a deployment be completely removable, with verification reporting that
nothing created by the framework remains and that no pre-existing resource was removed.

Required, and it is a direct consequence of CON-11. A recipe intended to be tried quickly by
any customer must be equally easy to remove. An evaluation that cannot be cleanly undone is
not a quick win — it is a liability the customer did not agree to take on. The asymmetry
between "created by the framework" and "pre-existing" is the part that must be provably
handled.

## Consequences

- The 18 Required areas become schema-enforced. A configuration omitting any of them fails
  validation, offline and with no credentials (SC-07).
- The 6 Recommended areas emit validation warnings rather than errors, and the shipped
  quickstart populates them so the documented path is the production-ready path.
- The 1 Optional area is a declared extension point with schema support and no default.
- Areas 13 and 14 are Required as contract and unimplemented as behavior. Their v1
  enforcement is a set of negative tests proving the capability is absent. Those tests are
  release gates under SC-06.
- Areas where the framework ships defaults so that no authoring is needed for a first result
  — 3, 12, 17 — must keep the default and the extension point separable, otherwise SC-13
  fails as soon as a consumer customizes.
- The unconfirmed runtime tool identifiers noted in area 5 remain an open risk and block the
  tool-policy enforcement model decision. This must be reconciled against the real runtime
  before area 5 can be considered settled.

## Open Items Carried Forward

| Item | Blocks | Note |
|------|--------|------|
| English renaming of the reference vocabulary | Area 4, area 12 | Provenance of original values must be preserved |
| Tool-policy enforcement model | Area 5, area 22 | Runtime capability identifiers are explicitly unconfirmed in the source |
| Evidence retention and immutability policy | Area 15 | Retention duration and storage location depend on the binding and on customer policy |
| Single source of truth for schemas | Area 18 | The reference implementation duplicates schemas across two directories, creating drift |

## References

- `prd.md` — section *Minimum SRE Agent Contract*
- `docs/architecture/source-analysis.md` — sections 2, 3, 5, 6, 7
- `docs/features/sre-agent-recipe-framework/spec.md` — FR-01, FR-02, Key Entities,
  CON-02, CON-03, CON-06, CON-07, CON-11, SC-04, SC-06, SC-07, SC-08, SC-09, SC-13
- [ADR-0001](decisions/0001-upstream-template-relationship.md),
  [ADR-0002](decisions/0002-infrastructure-as-code.md),
  [ADR-0003](decisions/0003-guided-deployment-experience.md)

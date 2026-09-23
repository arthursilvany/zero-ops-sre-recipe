# Research and Decision Consolidation

**Feature**: `sre-agent-recipe-framework`
**Date**: 2026-09-23
**Status**: Draft
**Traces to**: `spec.md` v1.2, ADR-0001 to ADR-0004

## Purpose

This document consolidates what was settled before planning, what planning itself settled,
and what remains deliberately open. It exists so that the plan can reference conclusions
instead of re-arguing them, and so that a reader can tell at a glance which statements rest
on evidence and which rest on a decision.

## What the Evidence Already Settled

| Question | Answer | Where it was settled |
|---|---|---|
| Relationship to upstream tooling | Extend. Compose and parameterize the pinned `microsoft/sre-agent` kit; never fork it | ADR-0001, Accepted |
| Primary Infrastructure as Code | Bicep. ARM JSON is compiled output only; no Terraform work is owned here | ADR-0002, Accepted |
| Guided experience | CLI wizard extending the upstream `new-agent` pattern, emitting a schema-validated scope contract | ADR-0003, Accepted |
| Discovery mechanism | Read-only Azure Resource Graph, single operator-supplied subscription in v1 | ADR-0003 acceptance note |
| Agent binding format | `agent.json`, isolated to the binding layer | ADR-0001 |
| Contract-area obligations | 18 Required, 6 Recommended, 1 Optional, 0 Out of scope | `minimum-sre-agent-contract.md` |
| Layering and repository shape | Three layers plus consumer extensions; directory boundaries, not conventions | `overview.md` |

## What Planning Settled

### Framework tooling runtime — ADR-0004, Proposed

The wizard, validator, emitter and local tests are one Python package with thin Bash and
PowerShell entry points.

The deciding evidence is `source-analysis.md` section 3.6: **Python 3 is already an
upstream prerequisite**, so adopting it adds nothing an operator does not already install.
Section 2.9 records that the reference implementation already carries Python validation
helpers and a canonical JSON script, so the pattern has precedent in both directions.

The alternative, Node with Ajv, has a genuinely better JSON Schema 2020-12 validator. It
was rejected because it would be a net-new prerequisite paid by every consumer before the
first result, which CON-11 does not permit, and because it would open a dependency surface
on the workstation holding live Azure credentials that the chosen option does not open.

ADR-0004 also pins canonicalisation, digest algorithm, encoding, self-exclusion, Unicode
normalisation and line-ending handling. Without those six, FR-19 and FR-23 are not
verifiable claims.

### Executable tooling is separated from declarative artifacts

`contracts/`, `core/` and `wizard/` hold **declarative artifacts only** — schemas,
vocabulary, policy documents, binding templates, discovery query definitions, eligibility
rules. Executable tooling lives in one installable package under `tools/`.

This is a refinement of the structure in `overview.md`, not a departure from it, and it has
one specific purpose: the layer directories stay readable as evidence. SC-01 is measured by
diffing declared core paths, and a diff that mixes contract changes with implementation
churn is weaker evidence than one that does not.

### Authority for the read-only guarantee is the RBAC grant

This is the single most consequential correction from the security review. Before it, the
read-only guarantee rested on the tool policy — a policy whose capability identifiers the
source itself declares unconfirmed against the real runtime.

The ordering is now explicit, strongest first:

1. **The RBAC grant.** Azure Resource Manager denies a write the agent identity has no
   role for. This holds regardless of whether a capability identifier was named correctly.
2. **The compiled ARM.** Every role definition in the composed deployment is checkable
   offline, with no credentials, before anything is provisioned.
3. **The tool policy.** Deny-by-default defence-in-depth, reconciled against the pinned
   runtime rather than assumed to match it.

The framework's own guarantees must rest on layers one and two, which it controls end to
end. Layer three is real protection and is retained, but it cannot be the load-bearing
claim.

## Open Items Carried Into Implementation

These were open before planning and remain open. None is resolved here, because none can be
resolved from the artifacts available.

| Item | Why still open | Handling in v1 |
|---|---|---|
| Tool-policy enforcement model | The reference source states its runtime tool identifiers are explicitly unconfirmed against the real runtime, and its enforcement is procedural rather than programmatic | Policy is authored in framework-neutral capability classes, mapped to runtime identifiers only in the binding layer. The mapping is recorded as unverified until a reconciliation gate runs against a real runtime. Documented under FR-74 |
| English renaming of the reference vocabulary | Requires a value-by-value decision with provenance preserved | A vocabulary artifact pairs each English identifier with its original reference value as provenance metadata. The original values are never identifiers |
| Evidence retention and immutability | Depends on the binding and on each customer's own policy | The contract declares retention as a consumer-supplied setting and ships no default retention period. Recorded as a known limitation |
| Single source of truth for schemas | Settled in principle, unenforced in practice | One location, `contracts/schemas/`, plus an automated duplicate-definition check. The reference implementation's drift across two directories is the evidence that a convention alone is insufficient |
| Environment naming convention | Deliberately deferred by the specification | Environment binding is separable by structure; the names themselves are consumer-chosen |
| Customer-vocabulary denylist location | Committing the denylist to a soon-to-be-public repository discloses what it protects | Resolve before building the sanitization gate. Candidates: hold the list outside the repository, or match salted hashes rather than terms |

## Constraints That Shape Every Work Item

- **CON-11 is a design filter, not a goal.** Anything requiring bespoke authoring before a
  first useful result belongs in an extension, not in the required path. Applied to
  tooling, it eliminated a new runtime prerequisite. Applied to the contract, it pushed
  six candidate areas from Required to Recommended.
- **CON-05 is measured by file path.** Onboarding touches only consumer-owned paths. This
  is why the core-path declaration is an artifact rather than a statement in a document.
- **CON-02 is enforced negatively.** The absence of a capability is proven by a static
  structural assertion, because exercising behaviour cannot prove non-existence.
- **CON-12 means no Terraform artifact of any kind exists here.** A file-existence check
  covers it.

## References

- `prd.md`
- `docs/features/sre-agent-recipe-framework/spec.md`
- `docs/features/sre-agent-recipe-framework/security-review-architecture.md`
- `docs/architecture/overview.md`, `docs/architecture/minimum-sre-agent-contract.md`,
  `docs/architecture/source-analysis.md`
- ADR-0001, ADR-0002, ADR-0003, ADR-0004

# Schema Register

**Traces to**: FR-02, FR-05, FR-06, FR-57, FR-58
**Binds to**: [ADR-0004](../docs/architecture/decisions/0004-framework-tooling-runtime.md)

Every artifact the minimum agent contract classifies as Required or Recommended resolves to
exactly one schema, at exactly one path, under `contracts/schemas/`. That document is not
linked from here by path: its filename carries a runtime-specific name, and FR-04 keeps
those out of core paths, so this register names it by title and the reader finds it under
`docs/architecture/`. FR-05 requires the single location; the reference implementation this
framework draws from duplicated schemas across two directories and drifted, which is the
failure this register exists to prevent.

An entry in this table that resolves to no file, or to more than one, fails the build. The
check runs over the register and the directory together, so a schema added without an entry
fails just as an entry with no schema does.

## Obligation levels

| Level | Meaning |
|---|---|
| Required | The contract does not hold without it |
| Required as contract | The schema is Required; no execution path exists in v1 (CON-02) |
| Recommended | Expected in a complete deployment; its absence is recorded, not silent |

## Register

| Artifact | Schema | Obligation | Produced by | Notes |
|---|---|---|---|---|
| Scope contract | `scope-contract.schema.json` | Required | Consumer, via the guided step | Anchor of the evidence chain. Every downstream artifact binds to its canonical hash |
| Framework configuration | `framework-config.schema.json` | Required | Consumer | The eight concerns FR-24 separates |
| Environment binding | `environment-binding.schema.json` | Required | Consumer | Binds one workload to one environment without restating its scope (FR-36) |
| Connector configuration | `connector-config.schema.json` | Required when any connector is used | Consumer | Declaration committed, credential never |
| Agent definition | `agent-definition.schema.json` | Required | Framework | Runtime-agnostic. Names capability classes, not runtime tool identifiers |
| Tool policy | `tool-policy.schema.json` | Required | Framework | Deny-by-default, deny-wins, fail-closed. Declared, not framework-enforced (FR-53) |
| Capability mapping | `capability-mapping.schema.json` | Required | Binding layer | Maps classes to one pinned runtime version. Starts unverified until the reconciliation gate runs (NEG-C) |
| Evidence manifest | `evidence-manifest.schema.json` | Required | Execution | Holds content hashes, never content (NEG-F) |
| Change set | `change-set.schema.json` | Required as contract | Not produced in v1 | No executed lifecycle state exists, so no artifact can claim application (FR-06) |
| Approval ledger | `approval-ledger.schema.json` | Required as contract | Not produced in v1 | Decider recorded as a principal object identifier, never a display name (SEC-016) |
| Query catalogue | `query-catalogue.schema.json` | Recommended, framework ships defaults | Framework and consumer | Every entry declares default or extension, so the two stay separable |
| Workload extension | `workload-extension.schema.json` | Optional per workload; the mechanism is Required | Consumer | Lives in consumer-owned paths, so a second workload produces no core diff (FR-63) |
| Handoff record | `handoff-record.schema.json` | Recommended | Execution | Idempotency key distinguishes a retry from new work |
| Assessment result | `assessment-result.schema.json` | Recommended | Execution | A diagnostic finding, deliberately not a change set (FR-57) |
| Readiness result | `readiness-result.schema.json` | Recommended | Execution | Whether the workload can be observed at all |
| Core path declaration | `core-paths.schema.json` | Required | Framework | Describes `contracts/core-paths.json`, including the runtime identifiers it forbids |

## Rules every schema satisfies

Linted as a group over the directory rather than over this list, so a schema added tomorrow
is covered without anyone remembering to add it (NEG-I):

- `additionalProperties: false` on every object, so an unknown property is rejected and the
  offending path is named (FR-27).
- An explicit `schemaVersion`, required (FR-05).
- No property name matching a secret-bearing pattern. A name ending in `Ref` is an
  indirection and is permitted, because it names where a value lives and never the value
  (SEC-013).
- No free-form workload-payload property.
- Every string bounded by a length, a pattern, an enumeration or a format. An unbounded
  string is where a pasted credential or a customer blob would land.
- No `$ref` outside the file itself. Cross-file references are unresolvable without a
  registry and would otherwise be fetched over the network, which would make offline
  validation depend on reachability.
- Authored within broadly supported 2020-12 features, per ADR-0004.

## What the schemas deliberately cannot express

Structural denial, rather than a rule applied after the fact. Each of these is a shape the
contract has no way to represent:

| Denied | Mechanism |
|---|---|
| An inline secret | No property can hold credential material; every such value is an external reference name whose pattern cannot express a URL or a token |
| A write-capable agent | No write access level and no mutating action mode exist in the enumerations |
| Lowering the self-approval bar | `selfApprovalPermitted` is absent from the binding override, so it can be raised and not lowered (SEC-016) |
| A change set that was applied | No executed lifecycle state exists (FR-06) |
| Evidence holding retrieved content | The manifest records hashes; no property accepts content (NEG-F) |
| A substituted value for an unreachable source | An unobserved entry carries no content hash at all, rather than a zero (FR-28) |
| An implicit capability set | `capabilities` is required even when empty, because a runtime handed no list inherits write-capable tools (NEG-D) |
| An unclassified capability | `capabilityClass` is a closed enumeration, so an unknown capability fails rather than defaulting to allowed (NEG-C) |
| A consumer query posing as a default | A workload extension pins entry origin to `consumerExtension` |
| An agent-created schedule | Cadence is a closed enumeration, not a free-form expression (FR-52) |
| A policy that fails open | Default decision, conflict resolution and evaluation-failure behaviour are all pinned to deny |

## What structure cannot check

Recorded here so the boundary is explicit rather than assumed. These are semantic checks,
enforced by the validator and not by any schema (FR-28):

- An observation period whose end precedes its start.
- A reference name that resolves to no declared external reference.
- A decider equal to the agent's own principal.
- An approval-ledger sequence with a gap, or a broken previous-entry chain.
- A conclusion whose evidence references resolve to no entry.
- A recomputed canonical hash that does not match the recorded one.
- A scope entry that no longer resolves, which fails at preview rather than after
  provisioning.

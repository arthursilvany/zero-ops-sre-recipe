# Schema Register

**Feature**: `sre-agent-recipe-framework`
**Date**: 2026-09-23
**Status**: Draft
**Satisfies**: FR-02, FR-05
**Binds to**: [ADR-0004](../../../architecture/decisions/0004-framework-tooling-runtime.md)

## Purpose

FR-05 requires that each schema exist exactly once and carry an explicit version. The
reference implementation duplicated its schemas across two directories and drifted, which
is the evidence that a convention alone does not hold. This register is the single list of
what exists, where, and who owns it. An automated duplicate-definition check enforces it.

All schemas are JSON Schema 2020-12 and live under `contracts/schemas/`. No schema may
exist anywhere else in the repository.

## Register

| Schema | Path under `contracts/schemas/` | Obligation | Validated instances | Owner layer |
|---|---|---|---|---|
| Scope contract | `scope-contract.schema.json` | Required | Wizard output; consumer-committed | Governance |
| Framework configuration | `framework-config.schema.json` | Required | `examples/minimal/`, `examples/reference-workload/` | Governance |
| Environment binding | `environment-binding.schema.json` | Required | One per environment, consumer-owned | Governance |
| Tool policy | `tool-policy.schema.json` | Required | `core/policy/` | Governance |
| Capability mapping | `capability-mapping.schema.json` | Required | `core/binding/`, one per pinned runtime version | Binding |
| Agent definition | `agent-definition.schema.json` | Required | The runtime-agnostic definition; `agent.json` is its emitted binding | Governance, bound in binding layer |
| Connector configuration | `connector-config.schema.json` | Required when used | Consumer-owned | Governance |
| Evidence manifest | `evidence-manifest.schema.json` | Required | One per execution | Governance |
| Change-set | `change-set.schema.json` | Required as contract | None in v1; no producer exists | Governance |
| Approval ledger | `approval-ledger.schema.json` | Required as contract | None in v1; validator only | Governance |
| Query catalogue | `query-catalogue.schema.json` | Recommended | Shipped defaults; consumer extensions | Governance |
| Workload extension | `workload-extension.schema.json` | Mechanism Required | `examples/reference-workload/` | Governance |
| Handoff record | `handoff-record.schema.json` | Recommended | None shipped | Governance |
| Assessment result | `assessment-result.schema.json` | Recommended | Sample fixture | Governance |
| Readiness result | `readiness-result.schema.json` | Recommended | Sample fixture | Governance |
| Core path declaration | `core-paths.schema.json` | Required | `contracts/core-paths.json` | Governance |

## Versioning

Every schema carries a version identifier, and every instance declares the version it
conforms to. A change to any schema follows FR-29, FR-69, NFR-21 without exception: the
version identifier changes, breaking changes are listed, and migration guidance is
supplied, or the release states that none apply.

A consumer pinned to version N continues to validate and deploy unchanged when N+1 ships
(CC-C01). No lockstep upgrade is ever required.

## Canonical Form and Hashing

Pinned by ADR-0004 and restated here because it is a contract property, not an
implementation detail:

| Concern | Value |
|---|---|
| Canonicalisation | RFC 8785 JSON Canonicalization Scheme |
| Unicode normalisation | NFC, before canonicalisation |
| Digest | SHA-256 |
| Encoding | Lowercase hexadecimal |
| Self-exclusion | The hash field is removed before the digest is computed |
| Newlines | No trailing newline in the digest input; emitted files use LF |

The same input produces the same digest on Windows and on Linux, and a test asserts it
(NEG-J).

## Authoring Rules

Enforced by a schema lint that runs in CI (NEG-I):

- `additionalProperties: false` on every object.
- An explicit version identifier on every schema.
- No property name matching a secret-bearing pattern; no free-form payload field.
- No `$ref` to a schema outside `contracts/schemas/`.
- Only broadly supported 2020-12 keywords, per ADR-0004's recorded validator trade-off.
- Every enumeration value is English, with any original reference value recorded as
  provenance in `contracts/vocabulary/` rather than used as an identifier (FR-03).

## Validation Behaviour

- Offline and credential-free, always (FR-25, SC-07).
- Unknown properties are rejected, and the failure names the artifact and the property
  path (FR-27).
- Semantic checks run after structural conformance (FR-28).
- Error messages name the path and the expected shape, never the supplied value, for any
  secret-bearing or identifier-bearing field (SEC-017).
- Recommended areas produce warnings; Required areas produce failures, per the obligation
  levels in the minimum contract.

## References

- `docs/features/sre-agent-recipe-framework/spec.md` — FR-02, FR-05, FR-24 to FR-30
- `docs/features/sre-agent-recipe-framework/data-model.md`
- `docs/architecture/minimum-sre-agent-contract.md`
- [ADR-0004](../../../architecture/decisions/0004-framework-tooling-runtime.md)

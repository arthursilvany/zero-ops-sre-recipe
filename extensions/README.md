# Consumer extension contract

This directory ships this contract and no workload or skill content. Consumer-authored
extensions belong in a consumer-owned repository. The v1 interfaces are declarations
validated against closed schemas; a valid declaration does not by itself provision a
connector, grant access, run a query, or schedule an agent.

## Compatibility across core upgrades

The [core path declaration](../contracts/core-paths.json) separates framework-owned
paths from consumer-owned examples. `extensions/README.md` is a core path here. The
framework repository intentionally does not accept extra tracked files in `extensions/`:
`zeroops check-core` reports paths that are not classified. Keep actual extension files
in a consumer-owned repository and pass that repository's `extensions` directory to
`zeroops lint-skills`.

Every configuration interface below is defined by a versioned JSON Schema. Schema
objects reject undeclared properties, and each instance declares the schema version it
uses. [`schema-versions.json`](../contracts/schema-versions.json) records the schema
version, content digest, breaking changes, and migration guidance. A core upgrade does
not silently reinterpret an old extension: validate it against the target release and
follow that release's migration entry. The framework does not automatically merge,
migrate, or execute consumer content. Skill lint findings are warnings, not a
compatibility or safety guarantee.

The offline validator checks schema shape and declared references. It does not establish
that an Azure identity has access, that a connector can connect, that a query matches a
live telemetry schema, or that a runtime implements a declaration. Those guarantees
remain with the consumer's platform configuration and review.

## Extension-point coverage

The point names below match [source analysis section 5.3](../docs/architecture/source-analysis.md).
The inputs and outputs describe the v1 contract, not implied runtime behavior.

| Extension point | v1 status | Consumer input | Validated output or behavior | Upgrade guarantee or out-of-scope reason |
|---|---|---|---|---|
| Target resources, resource groups and subscriptions | Supported, bounded | `framework-config.environments[*].subscriptionRef` and `workload-extension.targetResources[*]`; scope kinds are `resourceGroup`, `tag`, or `resource` with a selector. | Validated environment and workload scope declarations with references resolved across the configuration set. | Closed `framework-config` and `workload-extension` schemas are versioned. Scope declarations do not grant permissions; Azure RBAC remains an independent control. |
| Data-flow stage topology | Out of scope in v1 | None. No v1 schema accepts stage nodes or edges. | None. The framework does not validate or execute a workload stage graph. | There is no provider-neutral stage contract or runtime consumer. Workload-specific pipeline names cannot be treated as a stable v1 interface. |
| Correlation identifiers | Out of scope in v1 | None. No v1 extension property defines correlation fields. | None. | There is no correlation schema or consumer in the v1 contracts. Adding one requires an explicit versioned contract. |
| KQL queries and the telemetry schema they assume | Supported, bounded | `workload-extension.queries[*]`: `id`, `origin` fixed to `consumerExtension`, `capabilityClass`, `queryText`, and `queryHash`; optional `purpose`. Record telemetry assumptions in the consumer review. | Validated, origin-separated query entries. Validation does not execute the query or verify its assumptions against a live telemetry schema. | The closed query shape, permitted capability classes, and query digest are part of the versioned schema. Telemetry semantics remain consumer-owned and have no automatic migration guarantee. |
| Alert catalogue and symptom definitions | Supported, bounded | `workload-extension.alertDefinitions[*]`: `id`, `severity`, `condition`, and optional `queryRef`. | Validated alert definitions and references. The platform where an alert is configured evaluates its condition; the framework does not provision or evaluate alerts. | The schema pins the allowed severity and shape. Condition meaning and platform behavior are not guaranteed by a core upgrade. |
| Connector selection and credentials | Supported, bounded | `workload-extension.connectorRefs[*]` names a connector. `connector-config` declares its kind, endpoint reference, authentication method, access mode, and optional timeout. Endpoint and credential values are external references. | Validated connector declarations and resolved names. No secret value is accepted in the schema, and validation does not provision the connection or grant RBAC. | Connector kinds and read-only access are closed, versioned schema values. A changed connector contract requires an explicit schema version and migration entry. |
| Execution limits and thresholds | Supported, bounded | `workload-extension.executionLimitOverrides` may narrow `maxToolCalls`, `maxWallClockSeconds`, `maxResultSetRows`, or `perQueryTimeoutSeconds`. | Validated limit overrides; semantic validation rejects overrides that widen the tool-policy ceiling. No general workload threshold field is defined. | The supported limit names and bounds are schema-versioned. Platform enforcement is separate; alert conditions are not a substitute for an enforced execution limit. |
| Network access mode | Supported as a declaration | `workload-extension.networkAccessMode` is `publicEndpoint` or `privateEndpoint`; connector configuration can declare the same access boundary. | Validated network mode declaration. It does not create a route, firewall rule, or prove endpoint reachability. | The allowed modes are closed schema values. Network enforcement and connectivity remain external to the extension contract. |
| Scheduling and recurrence | Supported, bounded | `workload-extension.schedule.cadence` is `manual`, `hourly`, `daily`, or `weekly`; an optional time zone may be declared. | Validated schedule declaration only. This contract does not create or run a scheduled task. | The cadence set is versioned and closed. A core upgrade cannot imply that a runtime scheduler exists or that a schedule was applied. |
| Report branding and audience | Partial: section selection only | `workload-extension.reportShaping.sections` selects from `summary`, `findings`, `evidence`, `readiness`, and `limitations`. | Validated section selection. Arbitrary branding, audience text, and consumer-authored report content are not accepted. | The section set is a versioned enum. Branding and audience customization remain out of scope until they have a reviewed schema. |
| Remediation actions, once the extension point is implemented | Proposal contract only; execution out of scope | `change-set` defines a proposal record with preconditions, blast radius, a rollback plan, and a verification method. `remediationPermissions.mode` is `readOnly` or `proposeOnly`. | A change-set proposal may be represented by its contract. No v1 state represents an applied change, and the framework has no execution path. | The v1 schemas do not permit a mutating mode or an executed change state. Adding execution requires a separate reviewed contract and versioned change. |

## Consumer-authored skill guidance

Markdown skills are an independent extension surface. A consumer supplies files under a
directory named `extensions` and can lint that directory with
`zeroops lint-skills <path-to-extensions>`. The offline check looks for non-empty
sections stating when the skill applies, what to check, when it does not apply, and
which mistake to avoid. It skips `README.md` files and reports findings as warnings.

The linter reports structure only. It does not assess whether guidance is correct,
safe, useful, or loaded by an agent. Review every skill before use and after a core
upgrade. No consumer skill ships in this repository.

# Framework Configuration Reference

This reference covers the instance properties defined by [`framework-config.schema.json`](../../contracts/schemas/framework-config.schema.json). It documents the eight configuration concerns in FR-24 and the shared schema-version metadata. It does not describe every contract schema in `contracts/schemas/`.

Use the [minimal example](../../examples/minimal/framework-config.json) as a workload-neutral starting point. The [two-environments example](../../examples/two-environments/framework-config.json) shows environment-specific periods, exclusions and connector declarations. Both are examples, not sources of implicit defaults. Validate from the repository root with `.\bin\zeroops.ps1 validate examples\minimal\` as described in [Commands](../commands.md).

The property paths below use JSON Pointer notation. `*` represents one array item. Requiredness describes whether a property must appear in its parent object. The identifier and external-reference-name patterns are both `^[a-z][a-z0-9-]{1,62}[a-z0-9]$`, allowing 3 to 64 lowercase letters, digits and hyphens, with a lowercase letter first and a letter or digit last. Every configuration object is closed to undeclared properties. The schema declares no `default` values; omission of an optional property leaves it absent. Descriptions and values in examples do not establish defaults.

## Shared contract metadata

| Instance path | Required | Schema constraints | Purpose |
|---|---|---|---|
| `/schemaVersion` | Yes | String; pinned to `1.0.0`; three numeric dot-separated components (`major.minor.patch`) | Identifies the configuration contract version. The validator rejects a version different from the schema pin. |

## Concern 1: Global framework defaults

| Instance path | Required | Schema constraints | Purpose |
|---|---|---|---|
| `/frameworkDefaults` | Yes | Closed object; requires `observationPeriod` | Holds settings that apply unless an environment provides an override. |
| `/frameworkDefaults/observationPeriod` | Yes | Closed object; requires `start` and `end`; semantic validation rejects an end at or before the start | Sets the default interval used for observation. |
| `/frameworkDefaults/observationPeriod/start` | Yes | String with `date-time` format; semantic validator requires UTC RFC 3339 form `YYYY-MM-DDThh:mm:ssZ` | Inclusive start of the default observation interval. |
| `/frameworkDefaults/observationPeriod/end` | Yes | String with `date-time` format; semantic validator requires UTC RFC 3339 form `YYYY-MM-DDThh:mm:ssZ` | End of the default observation interval. |
| `/frameworkDefaults/defaultEnvironment` | No | Identifier pattern described above | Names the environment selected when no explicit environment is supplied. It must identify an entry in `environments`. |
| `/frameworkDefaults/evidenceRetentionDays` | No | Integer, minimum `1` | Sets the requested retention period for evidence. |

## Concern 2: Environment settings

| Instance path | Required | Schema constraints | Purpose |
|---|---|---|---|
| `/environments` | Yes | Array with at least one unique item; each item is a closed object | Declares the environments to which workload bindings can refer. |
| `/environments/*/name` | Yes | Identifier pattern | Names one environment. |
| `/environments/*/description` | No | String, maximum 500 characters | Explains the environment for operators. |
| `/environments/*/subscriptionRef` | Yes | External-reference name pattern | Refers to an entry in `externalReferences`; never place a subscription identifier here. |
| `/environments/*/observationPeriod` | No | Closed object; requires `start` and `end`; semantic validation rejects an end at or before the start | Overrides the global observation interval for this environment. |
| `/environments/*/observationPeriod/start` | Yes when the period is present | String with `date-time` format; semantic validator requires UTC RFC 3339 form `YYYY-MM-DDThh:mm:ssZ` | Inclusive start of this environment's observation interval. |
| `/environments/*/observationPeriod/end` | Yes when the period is present | String with `date-time` format; semantic validator requires UTC RFC 3339 form `YYYY-MM-DDThh:mm:ssZ` | End of this environment's observation interval. |

## Concern 3: Workload-specific settings

| Instance path | Required | Schema constraints | Purpose |
|---|---|---|---|
| `/workloads` | Yes | Array with at least one unique item; each item is a closed object | Declares workload names and the scope selections shared across environments. |
| `/workloads/*/name` | Yes | Identifier pattern | Names a workload for environment bindings and references. |
| `/workloads/*/description` | No | String, maximum 500 characters | Describes the workload without embedding customer-sensitive data. |
| `/workloads/*/extensionRef` | No | Non-empty string, maximum 200 characters | Names a workload extension when workload-specific behavior is needed. |
| `/workloads/*/inScope` | Yes | Array with at least one unique item; each item is a closed object | Selects resources the agent may observe. An empty selection is rejected. |
| `/workloads/*/inScope/*/kind` | Yes | One of `resourceGroup`, `tag`, or `resource` | Selects the scope-selection mechanism, not a workload type. |
| `/workloads/*/inScope/*/selector` | Yes | String, 1 to 300 characters | Holds the selector value. Shipped examples use placeholders, not resource identifiers. |
| `/workloads/*/outOfScope` | No | Array of unique items; each item is a closed object | Records explicit exclusions from the workload scope. |
| `/workloads/*/outOfScope/*/kind` | Yes when an exclusion is present | One of `resourceGroup`, `tag`, or `resource` | Selects the exclusion mechanism. |
| `/workloads/*/outOfScope/*/selector` | Yes when an exclusion is present | String, 1 to 300 characters | Holds the exclusion selector. |

## Concern 4: Tool and integration settings

| Instance path | Required | Schema constraints | Purpose |
|---|---|---|---|
| `/toolIntegrations` | Yes | Closed object; requires `toolPolicyRef` | Connects the configuration to its tool policy and optional connector declarations. |
| `/toolIntegrations/toolPolicyRef` | Yes | Non-empty string, maximum 200 characters | Names the tool policy that applies. It does not replace RBAC as the authority for the read-only guarantee. |
| `/toolIntegrations/connectors` | No | Array of unique items; each item is a closed object | Declares optional tool connectors without embedding credentials. The property may be omitted or supplied as an empty array. |
| `/toolIntegrations/connectors/*/name` | Yes when a connector is present | Identifier pattern | Names the connector. |
| `/toolIntegrations/connectors/*/endpointRef` | No | External-reference name pattern | Refers to the connector endpoint through `externalReferences`. |
| `/toolIntegrations/connectors/*/credentialRef` | Yes when a connector is present | External-reference name pattern | Refers to externally held credential material. |

## Concern 5: Observability settings

| Instance path | Required | Schema constraints | Purpose |
|---|---|---|---|
| `/observability` | Yes | Closed object; requires `evidenceRequired` | Controls evidence requirements and optional observability references. |
| `/observability/evidenceRequired` | Yes | Boolean | When `true`, a conclusion with no resolvable evidence entry is a validation failure. |
| `/observability/workspaceRef` | No | External-reference name pattern | Refers to the observability workspace through `externalReferences`. |
| `/observability/queryCatalogueRef` | No | Non-empty string, maximum 200 characters | Names the query catalogue to use. |

## Concern 6: Remediation permissions

| Instance path | Required | Schema constraints | Purpose |
|---|---|---|---|
| `/remediationPermissions` | Yes | Closed object; requires `mode` | Declares the permitted remediation posture. |
| `/remediationPermissions/mode` | Yes | One of `readOnly` or `proposeOnly`; no mutating mode is defined | Selects observation-only behavior or proposal generation without execution. |
| `/remediationPermissions/changeSetRequired` | No | Boolean | States whether a change-set artifact is required for a proposal. |

## Concern 7: Approval policies

| Instance path | Required | Schema constraints | Purpose |
|---|---|---|---|
| `/approvalPolicies` | Yes | Closed object; requires `selfApprovalPermitted` | Declares the approval boundary for proposals. |
| `/approvalPolicies/selfApprovalPermitted` | Yes | Boolean, fixed to `false` | Declares that one principal may not both propose and approve the same change. |
| `/approvalPolicies/minimumApprovers` | No | Integer, minimum `1` | Sets the minimum number of approvers. |
| `/approvalPolicies/approverGroupRef` | No | External-reference name pattern | Refers to an externally configured approver group. |

## Concern 8: Externally referenced sensitive values

| Instance path | Required | Schema constraints | Purpose |
|---|---|---|---|
| `/externalReferences` | Yes | Closed object; requires `entries` | Holds names and locations of externally stored values, never the values themselves. |
| `/externalReferences/entries` | Yes | Array of unique items; each item is a closed object | Declares the available external references. An empty array is structurally permitted. |
| `/externalReferences/entries/*/name` | Yes when an entry is present | Identifier pattern | Names a reference consumed by another configuration property. |
| `/externalReferences/entries/*/provider` | Yes when an entry is present | One of `keyVault`, `managedIdentity`, or `environmentVariable` | Identifies the external source category. |
| `/externalReferences/entries/*/locator` | Yes when an entry is present | String, 1 to 300 characters | Locates the value. It must identify where the value lives, not contain a literal credential. |

## Validation boundaries

JSON Schema enforces the structural requirements and constraints shown above. Per-artifact semantic validation checks that external references resolve, that the default environment exists, that environment, workload and external-reference names are unique, and that observation-period start and end values are ordered. Set-level validation resolves cross-artifact references such as `toolPolicyRef`, `queryCatalogueRef` and `extensionRef`. The schema cannot compare sibling values or resolve references across configuration sections.

The schema intentionally has no property for inline secrets. Keep real identifiers and secret values out of committed configurations. Replace example placeholders in consumer-owned files and resolve sensitive values through the declared external-reference mechanism.

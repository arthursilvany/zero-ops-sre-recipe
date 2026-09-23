# Source Analysis and Pattern Inventory

> **Status:** In Validation
>
> **Last updated:** 2026-09-23
>
> **Phase:** Slice 1 — repository and source analysis
>
> **Inputs:** `prd.md`, `docs/envisioning/README.md`

This document records the mandatory preflight, the structured inventory of the two
authoritative reference sources, the extraction of their content into reuse categories,
and the resulting gaps, risks and open decisions. It is evidence for later phases; it is
not a design and it does not select any technology.

Every finding cites a source path. Findings without evidence were excluded. No secret,
credential, tenant identifier, subscription identifier, resource identifier, endpoint or
customer identifier from the reference sources is reproduced here.

---

## 1. Preflight Status

Required by `prd.md`, section *Mandatory Preflight*.

| Check | Result |
|---|---|
| Reference source 1 accessible | **Redirected.** The path named in `prd.md`, `C:\dev\zero-ops-sre-cortex`, exists but is empty. The user confirmed `C:\dev\ZeroOps-Cortex` as the correct source (git remote `arthursilvany/zeroops-cortex`, branch `main`, clean tree, head `70451df`). |
| Reference source 2 accessible | **Yes.** `C:\dev\sre-agent\GUIA-SRE-AGENT-PTBR.html` (~27 KB), plus the surrounding repository `C:\dev\sre-agent` containing `sreagent-templates/`, `labs/`, `appendix/` and `.github/workflows/validate-templates.yml`. |
| Target repository is the writable workspace | **Yes.** `C:\dev\zero-ops-sre-recipe`, git initialized on `main`, remote `arthursilvany/zero-ops-sre-recipe`. |
| Target repository prior state | One file, `prd.md`. No source, infrastructure, configuration or documentation existed before this effort. |
| Sensitive content present in sources | **Yes, in source 1.** See section 6.3. Nothing sensitive was copied into this repository. |

Both sources were read. No source-dependent analysis was blocked.

### 1.1 Method and limitations

- Both sources were treated as strictly read-only. Nothing in them was created, modified,
  renamed, moved, formatted, staged or committed.
- Large evidence archives and binary office documents inside source 1 were inventoried by
  path only and not parsed.
- The HTML guide was read as extracted text.
- Where a file was sampled rather than read exhaustively, or where a finding could not be
  fully verified, this document says so explicitly rather than inferring.

---

## 2. Source 1 — `ZeroOps-Cortex`

a Portuguese-language, single-customer Azure SRE Agent suite for one public-sector customer, referred to here as `<REFERENCE_CUSTOMER>`, described by its
own `README.md` as read-only, review-first and fail-closed, with the product framed as the
chain of evidence rather than the agent itself.

### 2.1 Architecture and execution model

A five-agent directed acyclic graph executed in epochs:

1. `cortex-orchestrator` — foundation epoch: maturity baseline, signal foundation, data-flow
   assurance.
2. `cortex-operations` — operations epoch: alert engineering, incident intelligence,
   recovery assurance.
3. `cortex-cost-optimization` and `cortex-executive` — parallel cost and reporting epoch.
4. `cortex-zero-ops` — final epoch: DAG routing, handoff governance, pull-request canary
   validation.

The root agent closes a snapshot before downstream agents consume it, and downstream agents
are prohibited from reopening or recalculating earlier epochs
(`agents\cortex-orchestrator.agent.yaml:14-15`, `agents\cortex-operations.agent.yaml:10-11`).

**No executable runtime exists in the repository.** The `agents/*.agent.yaml` files are
Azure SRE Agent custom-agent definitions; invocation, handoff execution, lock enforcement
and idempotency enforcement are specified in prose but not implemented locally. Execution
modes, schedules and response plans are all configured as `Review`
(`config\tool-policies.json`).

### 2.2 Agent contract as actually declared

All five definitions share exactly five top-level keys: `name`, `description`,
`instructions`, `tools`, `allowed_skills` (`agents\cortex-orchestrator.agent.yaml:28-85`).

There are **no formal input or output schemas** on the agent definition. Inputs and outputs
are expressed textually inside `instructions` by referencing external contracts and
snapshot rules. This is the single most significant gap between the reference
implementation and a machine-validatable contract.

Behavioural invariants stated by every agent:

- A missing or invalid scope contract yields `BLOCKED_SCOPE_NOT_APPROVED`.
- Missing access yields `SEM_ACESSO` — never an estimate, and never treating absent data
  as zero.
- Permission must never be requested or assumed in order to clear an access failure; the
  correct result is `SEM_ACESSO` plus a proposed change set
  (`agents\cortex-orchestrator.agent.yaml:68-71`).
- External content — logs, payloads, documents, pull-request text — is untrusted and must
  not be treated as instructions (`agents\cortex-orchestrator.agent.yaml:65-66`).

### 2.3 Skills model

A skill is a single `SKILL.md` file. There is no per-skill code, schema or test directory.
Each `SKILL.md` carries front-matter-like fields: name, description, procedure identifier,
host agent, source prompt, inputs, outputs, guardrails and referenced contracts
(`skills\cortex-alert-engineering\SKILL.md:1-35`).

`config\skill-manifest.json` maps prompt to skill to agent to procedure identifier to
recurrence, and constrains the model: one skill per procedure, at most three skills per
agent, distinct agent and skill names, and skill bodies that must be derived from prompts
and verifiable.

Recurrences declared: manual for assessment and orchestration, daily for observability,
data-flow and live report, event-driven for incident intelligence, weekly for executive
summary, monthly for FinOps and ROI, on demand for pull-request canary.

### 2.4 Schemas and data contracts

Seven JSON schemas under `schemas/`, all JSON Schema 2020-12, all with
`additionalProperties: false`, explicit `required`, fixed `schemaVersion` constants, and a
64-hex-character pattern for SHA-256 fields.

| Schema | Purpose | Notable enums |
|---|---|---|
| `scope-contract` | Authorized tenant, subscriptions, resource groups, period, sources, exclusions, classification, network mode, data-flow stages, correlation identifiers, limits, scope hash | Classification `PUBLIC` / `INTERNAL` / `CONFIDENTIAL` / `HIGHLY_CONFIDENTIAL`; network mode `TELEMETRY_ONLY` / `AKS_API_DIRECT` / `PRIVATE_WORKLOAD`; VNet mode `NOT_REQUIRED` / `PROPOSED` / `CONFIGURED` / `VALIDATED`; validation `READY_TELEMETRY_ONLY` / `READY_PRIVATE_ACCESS` / `PARTIAL` / `BLOCKED_DNS` / `BLOCKED_ROUTE` / `BLOCKED_FIREWALL_OR_NSG` / `BLOCKED_IDENTITY_OR_RBAC` / `NOT_REQUIRED` / `REQUIRES_HUMAN_APPROVAL` |
| `evidence-manifest` | Execution-level evidence index binding evidence to execution, scope hash and time | Classification `OBSERVED` / `DERIVED` / `INFERRED` / `RECOMMENDED`; state `NA` / `DISCOVERED` / `STATICALLY_VALIDATED` / `SCHEMA_VALIDATED` / `EXECUTED`; freshness `FRESH` / `STALE` / `UNKNOWN` / `NA` |
| `assessment` | Maturity assessment, domain scores, snapshots, evidence references | Status `EVIDENCIA_INSUFICIENTE` / `PROVISORIO` / `COMPLETO`; confidence `ALTA` / `MEDIA` / `BAIXA` / `INSUFICIENTE` (Portuguese) |
| `observability-readiness` | Review-only readiness assessment; `mode` must be `Review` and `changeExecuted` must be `false` | Health `HEALTHY` / `DEGRADED` / `UNAVAILABLE` / `UNKNOWN` / `PARTIAL` / `INCONCLUSIVE` / `BLOCKED` |
| `change-set` | Proposed mutation package with dry-run, preconditions, blast radius, rollback, verification and canonical hash | Classification `REVERSIBLE` / `COMPENSATABLE` / `IRREVERSIBLE`; risk `LOW` / `MEDIUM` / `HIGH` / `CRITICAL`; status `PROPOSED` / `APPROVED` / `EXECUTING` / `VERIFIED` / `ROLLED_BACK` / `REJECTED` / `EXPIRED` / `BLOCKED` |
| `approval-ledger` | Human decision record; agents cannot self-approve | Decision `APPROVED` / `REJECTED` / `REVOKED` |
| `handoff` | Agent-to-agent execution transfer with execution identity, idempotency, epoch, turn and maximum turns | State `RECEIVED` / `VALIDATING` / `RUNNING` / `PARTIAL_SUCCESS` / `AWAITING_APPROVAL` / `BLOCKED` / `FAILED` / `COMPLETED`; autonomy `READ_ONLY` / `REVIEW_FIRST` / `HUMAN_ONLY` |

Enforcement is **procedural, not programmatic**: agent instructions, policy configuration
and PowerShell validation scripts. Duplicate copies of the schemas exist under `knowledge/`
as well as `schemas/`, creating a drift risk.

The `change-set` schema is notable: it fully specifies a mutation lifecycle that the
runtime deliberately never executes. The contract for remediation exists ahead of the
capability.

### 2.5 Configuration and policy model

`config\tool-policies.json` is the safety core:

- `defaultDecision: DENY`, `conflictResolution: DENY_WINS`, `failureMode: FAIL_CLOSED`.
- An explicit allow-list of read and query capabilities.
- Regular-expression deny rules covering writes, destructive operations, arbitrary
  execution, secrets access, self-approval, external publication and agent-created
  schedules.
- Execution limits: 200 tool calls, 1,800 seconds, 5,000 query rows, 120-second query
  timeout.
- An explicit warning that omitting portal tool selection causes inheritance of global
  tools including write tools — **read-only is not the platform default**.
- An explicit note that the declared runtime tool identifiers are **unconfirmed** against
  the actual runtime.

Five Markdown policy documents under `policies/`: `agent-cost-controls.md`,
`autonomy-and-approval.md`, `contracts-operating-order.md`, `failure-handling.md`,
`kql-security.md`.

Configuration weaknesses: only one scope contract exists (`config\scope-contracts\prod.json`)
with no non-production counterpart; `config\change-sets\` contains only `.gitkeep`;
`config\schedules\` holds a single weekly report schedule; and global policy, agent
definitions and workload specifics are not cleanly separated.

### 2.6 Infrastructure as Code

The entire IaC surface is two files: `infra\rbac.bicep` and
`infra\parameters\prod.bicepparam`. It assigns access to pre-existing resources; it does
not provision the application platform, Log Analytics, Application Insights, Event Hubs,
Stream Analytics, Logic Apps, Azure DevOps, schedules or the agent runtime.

This matters for a later decision: **the existing Bicep footprint is too small to justify
selecting an IaC technology by inertia.**

### 2.7 Observability

Data sources: Azure Resource Graph, Azure Monitor Metrics, Log Analytics, Application
Insights, Azure DevOps read APIs.

The KQL catalogue is fixed and SHA-256 verified, and arbitrary query construction is
prohibited (`config\tool-policies.json`, `agents\cortex-orchestrator.agent.yaml:62-63`).
Four queries exist: `api-5xx-rate-by-role.kql`, `api-latency-percentiles.kql`,
`api-top-exceptions.kql`, `appversion-coverage.kql`.

Alerting is symptom-only and deliberately separated from cause analysis
(`skills\cortex-alert-engineering\SKILL.md`). Reports are self-contained HTML and are never
published automatically; external publication requires human approval of an exact hash
(`agents\cortex-executive.agent.yaml:62-65`).

The repository defines observability *consumers and contracts*. It does not implement a
workload observability stack.

### 2.8 Evidence and traceability

Evidence is classified, bound to an execution identifier and a scope hash, timestamped,
scored for freshness, assigned a data classification, and hashed with SHA-256
(`schemas\evidence-manifest.schema.json:1-72`). The scope hash propagates across scope,
evidence, change-set and handoff contracts. Reports may only consume closed snapshots.

This combination — scope contract, hashing, schema validation, snapshot closure, evidence
references, approval and change-set records — is what substantiates the repository's claim
that the chain of evidence is the product.

### 2.9 Validation, scripts and CI

`tests/` contains `run-negative-tests.ps1` plus `negative/README.md` and `negative/.gitkeep`.
The negative-test script exists and is designed to exercise prohibited behaviour, but its
assertions were not verified line by line in this inventory.

Fourteen scripts under `scripts/` cover applying collected identifiers and regenerating the
scope hash, RBAC auditing, agent-payload build, knowledge build, KQL catalogue build,
skills build, CI gate, publication-package generation, publication, pending-work display,
artifact validation, canonical JSON, foreign-suite support and Python validation helpers.

CI exists at `.github\workflows\validate.yml`.

### 2.10 Knowledge, prompts, templates and documentation

`knowledge/` holds operating rules, cost controls, approval and failure handling, KQL
security, runbook, capability matrix, report contract — and duplicate schema copies.
`prompts/` holds numbered procedure prompts `0` through `12`. `templates/` holds
`capability-matrix.md`, `report-contract.md`, `runbook.md`.

`docs/` mixes generalizable guidance (architecture, operating sequence, runbook, report
contract, KQL security, approval and failure policy) with customer deliverables
(`docs\gestao\`, `docs\pacote-cliente\`, `docs\relatorios\`, dated assessments under
`docs\assessments\`, and real environment evidence and publication archives under
`docs\evidencias\`).

`deprecated/` retains a signed scope-contract workflow (`apply-assinatura.ps1`,
`compute-scope-hash.ps1`, `termo-assinatura-escopo.md`), indicating evolution toward the
current contract-and-hash publication process.

---

## 3. Source 2 — SRE Agent guide and `sreagent-templates`

### 3.1 What the guide actually is

`GUIA-SRE-AGENT-PTBR.html` is a **repository navigation and inventory page**, not a
normative specification. Its sections cover getting started, an operational warning, path
selection, the reusable template kit, recipe generation, a complete Azure Monitor example,
labs, a script catalogue, and Azure SRE Agent usage examples.

The normative content lives in `sreagent-templates/`, not in the HTML.

### 3.2 The most significant finding

**`sreagent-templates/` is already a recipe framework**, and it overlaps substantially with
the deliverable described in `prd.md`. It provides:

- `recipes/` — reusable recipe directories, including a `minimal` recipe.
- `bin/` — Bash and PowerShell lifecycle scripts (`new-agent.sh`, `New-Agent.ps1`,
  `deploy.sh`, `Deploy-Agent.ps1`, `verify-agent.sh`, `Verify-Agent.ps1`).
- `bicep/` **and** `terraform/` — two deployment backends, plus `azure.yaml` for `azd`.
- `tests/` — dry-run and end-to-end tests.
- `docs/` — architecture, getting started, export and restore, test plan.
- `VERSION` and `CHANGELOG.md`.
- `.github\workflows\validate-templates.yml` — a working definition of a valid recipe.

This is a first-order input to scoping and to the Infrastructure as Code decision, and it
is treated as an explicit risk in section 7.

### 3.3 Prescribed agent structure

From `sreagent-templates\docs\ARCHITECTURE.md`:

```text
<agent-name>/
├── agent.json
├── connectors.json
├── connectors.secrets.env       # gitignored
├── .gitignore
├── config/
│   ├── skills/                  # .yaml + .md
│   ├── subagents/               # .yaml + .instructions.md
│   ├── tools/
│   ├── hooks/
│   ├── common-prompts/
│   ├── scheduled-tasks/
│   ├── incident-filters/
│   ├── http-triggers/
│   ├── repos/
│   └── plugin-configs/
├── automations/
│   ├── incident-platforms/
│   └── incident-filters/
└── data/                        # optional knowledge
    └── synthesized-knowledge/
```

`agent.json` keys observed in `recipes\minimal\agent.json`: `_scenario`, `_description`,
`_prerequisites`, `_prompts`, `identity.agentName`, `identity.resourceGroup`,
`identity.subscription`, `identity.location`, `identity.targetResourceGroups`,
`access.accessLevel`, `access.actionMode`, `upgradeChannel`, `defaultModelProvider`,
`monthlyAgentUnitLimit`, `tags`, `toggles.enableWebhookBridge`,
`toggles.webhookBridgeTriggerUrl`, `existingUamiId`, `existingAgentAppInsightsId`.

`connectors.json` keys observed: connector toggles for Application Insights, Log Analytics
and Azure Monitor, a lookback window (`azureMonitorLookbackDays`), Grafana URL and API key,
and a `connectors` collection. Connector authentication patterns named in the architecture
document include App Insights, Log Analytics, Azure Monitor, Kusto, MCP, GitHub, PagerDuty
and ServiceNow.

### 3.4 Artifact classification as stated by the source

| Artifact | Classification stated by the source |
|---|---|
| `agent.json` | Required |
| `connectors.json` | Required by the recipe checklist; may contain zero connectors |
| `config/skills/` with at least one skill | Required for a contributed recipe |
| Skill `.yaml` and `.md` pair | Required for contributed recipe skills |
| `expected-config.json` | Required by the recipe contribution checklist |
| `README.md` with `## Quick Start`, `## Parameters`, `## What You Get` | Required, enforced in CI |
| Dry-run test | Required for contributed recipes |
| `roles.yaml` | Present in most examples; not explicitly classified |
| `config/subagents/`, `config/tools/`, `config/hooks/` | Optional components |
| `config/common-prompts/` | The minimal recipe expects one common prompt |
| `automations/` | Required only for recipes that use incident filters or platforms |
| `data/` | Explicitly optional |
| `connectors.secrets.env` | Expected for secrets, gitignored; not mandatory for secret-free recipes |
| Terraform, Bicep, PowerShell and `azd` assets | Shared implementation assets, not per-recipe artifacts |

**No formal JSON Schema exists** for `agent.json`, `connectors.json`, skills, subagents,
tools or automations. `expected-config.json` is an expected-content manifest, not a schema.

### 3.5 Deployment flow and the workload selection question

Documented flow: choose a recipe, run `new-agent.sh` or `New-Agent.ps1`, supply parameters,
review generated files and secrets, run dry-run or what-if, deploy with Bicep, Terraform,
PowerShell or `azd`, then verify with `verify-agent.sh` or `Verify-Agent.ps1`.

**There is no native workload discovery or workload selection step.** The consumer supplies
`targetRGs` manually, and that parameter delimits where the agent acts. No "discover
workloads" or "select your workloads" experience is described anywhere in the guide, the
templates or the labs.

This settles an open product question: a guided workload discovery and selection step is
**not** an existing capability of the Azure SRE Agent tooling. If the recipe is to offer
one, it must build it — and `prd.md` already constrains how (inputs explained in plain
English, format validation, no plain-text secrets, non-interactive automation supported, a
version-controlled configuration file, a preview step, and no hiding of the underlying
deployment model).

### 3.6 Prerequisites stated by the source

Azure subscription and at least one target resource group; Azure CLI, `jq`, Python 3 with
PyYAML, and `curl`; Terraform and `azd` optional; PowerShell 7+ for the PowerShell path; a
region from the recipe's supported list — the minimal recipe lists `eastus2`,
`swedencentral`, `uksouth`, `australiaeast`; target resource groups via `targetRGs`;
optionally an existing user-assigned managed identity and Application Insights resource;
appropriate RBAC for the agent identity; connector-specific credentials or OAuth where
required.

Unsupported workload types, subscription quotas, feature registrations and a complete
supported-region matrix are **not covered**.

### 3.7 Security posture stated by the source

Covered: managed identity for Azure Monitor, Log Analytics, Application Insights and Kusto;
external secrets in a gitignored `connectors.secrets.env`; an explicit prohibition on
committing tokens, passwords and webhook URLs; target-resource-group scoping; `Reader`,
`Log Analytics Reader` and `Monitoring Reader` roles on target resource groups in the
standard deployment; review mode and approval hooks for sensitive operations; hook-based
denial of destructive production actions, for example `config\hooks\deny-prod-deletes.yaml`
and `require-approval-for-restarts.yaml`.

Not comprehensively covered: private networking and private endpoints, secret rotation,
prompt-injection resistance, and the treatment of untrusted diagnostic content. Least
privilege is only partially specified — named reader roles coexist with recipes and Bicep
assets carrying broader role and action patterns.

### 3.8 What CI considers a valid recipe

`.github\workflows\validate-templates.yml` runs on pull requests touching recipes, Bicep,
`bin` scripts, Terraform or tests, and performs: YAML `safe_load` of every
`recipes/**/*.yaml` and `.yml`; `bash -n` on `bin/*.sh` and `bicep/*.sh`; PowerShell parser
checks when `pwsh` is available; `terraform init -backend=false` and `terraform validate`
when Terraform is available; changed-recipe detection, running all recipe tests when shared
assets changed and otherwise the matching per-recipe dry-run test, with an inline fallback
using `new-agent.sh` and `deploy.sh --dry-run`; a required-README-sections check; a
comparison of `_prompts` keys in `agent.json` against README content, emitting warnings for
undocumented parameters; and a warning when a README exceeds 80 lines.

A placeholder check for unsubstituted `{{...}}` markers is mentioned in workflow comments,
but no corresponding executable step was confirmed. This is recorded as ambiguous.

### 3.9 Examples, labs and the minimum viable agent

Examples include Azure Monitor with Log Analytics and Application Insights incident
response, PagerDuty with virtual machine and Cosmos DB investigation, Dynatrace via MCP,
GitHub pull-request deployment protection, deployment compliance, Terraform drift
detection, Zava Learning, Zava AKS with PostgreSQL, a starter lab, and Container Apps and
virtual machine labs.

AKS examples exist: `labs\zava-aks-postgres\` and `labs\zava-learning\`. This corroborates
AKS as the reference workload archetype selected during envisioning.

The apparent minimum viable agent is the `minimal` recipe: agent infrastructure and RBAC,
one common prompt, zero connectors, zero skills, zero subagents, zero hooks and zero
incident automations (`recipes\minimal\expected-config.json`).

Labs deliberately include destructive failure-injection scripts. The guide warns that these
alter demonstration environments and must be run in isolated labs with a paired fix script.
They are demonstrations, not production-safe procedures.

---

## 4. Consistency and Conflicts Between the Sources

| Topic | `ZeroOps-Cortex` | Guide and templates | Assessment |
|---|---|---|---|
| Agent definition format | `*.agent.yaml` with `name`, `description`, `instructions`, `tools`, `allowed_skills` | `agent.json` with `identity`, `access`, toggles, plus `config/` directories | **Direct conflict.** Two incompatible shapes for the same concept. The recipe must choose one binding and keep the contract above it runtime-agnostic. |
| Default safety posture | Deny-by-default, fail-closed, deny-wins, explicit allow-list | Reader roles plus optional hooks; the guide notes read-only is not automatic | **Cortex is materially safer.** The deny-by-default policy is a reusable asset the templates lack. |
| Schema rigour | Seven JSON Schema 2020-12 contracts with `additionalProperties: false` and fixed versions | No formal JSON Schema anywhere | **Cortex is materially stronger.** This is the clearest reusable-core candidate. |
| Evidence model | Formal evidence manifest, classification, hashing, freshness, snapshot closure | Evidence-before-mitigation is encouraged in prose and examples | **Cortex is materially stronger.** No equivalent contract exists in the templates. |
| Query safety | Fixed, SHA-256-verified KQL catalogue; arbitrary queries prohibited | Kusto tool available; no catalogue or query-construction restriction found | **Cortex is materially stronger.** |
| Deployment mechanics | Two-file RBAC-only Bicep surface; no runtime | Full lifecycle: generate, dry-run, deploy via Bicep/Terraform/PowerShell/`azd`, verify | **Templates are materially stronger.** Cortex has essentially no deployment story. |
| Validation and CI | One CI workflow and PowerShell validators; negative tests present but thin | Multi-language syntax validation, per-recipe dry-run tests, README contract checks | **Templates are materially stronger** on breadth; Cortex is stronger on safety semantics. |
| Workload targeting | Scope contract with explicit resources, exclusions, limits and hash | `targetRGs` parameter only | **Cortex is materially stronger**, but its scope contract is entangled with customer specifics. |
| Workload discovery | Not present | Not present | **Neither source provides it.** It is net-new work for the recipe. |
| Remediation | Contract fully specified, execution deliberately absent | Demonstrated in labs and hooks; not standardized | Cortex's contract-ahead-of-capability approach matches the read-only v1 decision. |
| Language | Portuguese throughout, including enum values | English artifacts, Portuguese guide page | The recipe is English-only; Cortex enums require renaming. |

The two sources are complementary, not redundant. Cortex contributes **governance,
evidence and safety semantics**. The templates contribute **deployment mechanics and a
validation harness**. Neither contributes workload discovery.

---

## 5. Pattern Extraction

`prd.md` requires everything found to be separated into four categories.

### 5.1 Category 1 — Reusable core

Runtime-neutral and workload-neutral concepts.

| Pattern | Source evidence | Generalization required |
|---|---|---|
| Scope contract binding identity, time window, resources, exclusions, limits and a hash | `schemas\scope-contract.schema.json` | Remove customer topology; separate tenant configuration from the schema; make data-flow stages an extension point |
| Evidence manifest with provenance, classification, state, freshness and SHA-256 | `schemas\evidence-manifest.schema.json:1-72` | English taxonomy; define retention and immutability |
| Evidence classification `OBSERVED` / `DERIVED` / `INFERRED` / `RECOMMENDED` | `schemas\evidence-manifest.schema.json:31-33` | Adopt as-is; already English |
| Canonical execution-state vocabulary | Agent instructions and handoff schema | Rename `SEM_ACESSO` and the Portuguese assessment enums to English, recording originals as provenance |
| Change-set contract with dry-run, preconditions, blast radius, rollback and verification | `schemas\change-set.schema.json` | Keep as a contract only in v1; define a provider-neutral execution adapter later |
| Approval ledger with no self-approval | `schemas\approval-ledger.schema.json` | Adopt; bind to identity provider generically |
| Handoff contract with idempotency, epoch, turn and `maxTurns` | `schemas\handoff.schema.json` | Generalize epoch names away from Cortex's DAG |
| Deny-by-default, deny-wins, fail-closed tool policy | `config\tool-policies.json` | Use provider-neutral capability identifiers; make enforcement programmatic rather than conventional |
| Closed-snapshot discipline for reports | `agents\cortex-executive.agent.yaml:49-60` | Generalize epoch naming |
| Separation of read-only diagnostics from proposed mutations | `agents\cortex-operations.agent.yaml:48-52` | Adopt as a core invariant |
| Untrusted-content rule: telemetry, documents and pull-request text are data, never instructions | `agents\cortex-orchestrator.agent.yaml:65-66` | Adopt; strengthen with runtime enforcement |
| Negative tests as a release gate | `tests\run-negative-tests.ps1` | Expand into comprehensive executable assertions with CI reporting |
| Recipe README contract enforced in CI | `validate-templates.yml` | Adopt the required-sections and parameter-documentation checks |

### 5.2 Category 2 — Azure-specific reusable implementation

| Pattern | Source evidence | Note |
|---|---|---|
| Read-only Azure capability set: Resource Graph, Monitor Metrics, Log Analytics, Application Insights, Cost Management, Azure DevOps read | `config\tool-policies.json` | Runtime tool identifiers are explicitly unconfirmed and must be reconciled |
| Reader-role model on target resource groups | `sreagent-templates` architecture and deployment documentation | `Reader`, `Log Analytics Reader`, `Monitoring Reader` |
| RBAC-only Bicep with separated parameter file | `infra\rbac.bicep`, `infra\parameters\prod.bicepparam` | Small surface; does not pre-decide the IaC technology |
| Fixed, hash-verified KQL catalogue | `kql\queries\`, `config\tool-policies.json` | Queries themselves are workload-specific; the catalogue pattern is reusable |
| Connector toggle model for Azure data sources | `recipes\minimal\connectors.json` | Application Insights, Log Analytics, Azure Monitor, lookback window |
| Agent lifecycle scripting with dry-run and verify | `sreagent-templates\bin\` | Generate, dry-run, deploy, verify |
| Managed identity and optional existing user-assigned identity | `recipes\minimal\agent.json` | `existingUamiId` |
| Hook-based guardrails | `config\hooks\deny-prod-deletes.yaml`, `require-approval-for-restarts.yaml` | Complements the deny-by-default policy |

### 5.3 Category 3 — Workload-specific extension points

Things a consuming team must supply, which the core must never hard-code.

| Extension point | Evidence for why it must be an extension point |
|---|---|
| Target resources, resource groups and subscriptions | `targetRGs`; Cortex scope contract holds concrete resources |
| Data-flow stage topology | Cortex's stages are `<REFERENCE_CUSTOMER>`-specific: `EVENT_HUB_INPUT`, `STREAM_ANALYTICS`, `CYCLONE`, `LOGIC_APPS_APIS`, `EVENT_HUB_OUTPUT`, `CONSUMER` |
| Correlation identifiers | Cortex uses `OperationId` and `DeviceId` |
| KQL queries and the telemetry schema they assume | Cortex queries assume specific API role, exception and application-version tables |
| Alert catalogue and symptom definitions | `skills\cortex-alert-engineering\SKILL.md` |
| Connector selection and credentials | `connectors.json` toggles |
| Execution limits and thresholds | Cortex hard-codes production limits |
| Network access mode | `TELEMETRY_ONLY` / `AKS_API_DIRECT` / `PRIVATE_WORKLOAD` |
| Scheduling and recurrence | `config\skill-manifest.json`, `config\schedules\` |
| Report branding and audience | `templates\report-contract.md` |
| Remediation actions, once the extension point is implemented | `schemas\change-set.schema.json` |

### 5.4 Category 4 — Must not be included

Exclusion list. None of the following may enter this repository in any form.

1. Customer and product naming: the customer name, the suite product name, the sector-identifying descriptions, and the customer-derived prefix on agent and skill names.
2. Portuguese-language output requirements and `pt-BR` response directives.
3. Portuguese identifiers and enum values: `SEM_ACESSO`, `EVIDENCIA_INSUFICIENTE`,
   `PROVISORIO`, `COMPLETO`, `ALTA`, `MEDIA`, `BAIXA`, `INSUFICIENTE`.
4. `CTX-01` through `CTX-13` procedure numbering and the customer procedure mapping.
5. Customer platform references and operating context.
6. Reference-customer data-flow stage names and correlation identifiers.
7. Resource group and workload names derived from the customer or the suite name, for example `<RESOURCE_GROUP_NAME>` and `<LOG_ANALYTICS_WORKSPACE_NAME>`.
8. Production tenant, subscription and resource identifiers present in
   `config\scope-contracts\prod.json`, `infra\parameters\prod.bicepparam`, scripts and
   evidence files.
9. Fixed production dates and the `PROD` environment contract.
10. Customer-specific exclusions and scope caveats.
11. Customer decision references `D-09`, `D-10`, `D-12` and reference-customer gap references.
12. Azure DevOps pull-request canary assumptions tied to the customer's pipeline.
13. Customer deliverables and evidence: `docs\assessments\`, `docs\evidencias\`,
    `docs\gestao\`, `docs\pacote-cliente\`, dated reports under `docs\relatorios\`, and
    publication archives.
14. Portuguese filenames such as `coleta`, `relatorio`, `operacao`, `pacote-cliente`,
    `gerar-pacote-publicacao.ps1`.
15. Hard-coded blocked-capability state, such as Cost Management being blocked pending a
    customer decision.
16. Lab failure-injection scripts from the guide repository, which intentionally damage
    environments.

---

## 6. Reusable Artifact Register

Required by `prd.md`: for each reusable artifact, purpose, obligation, inputs, outputs,
dependencies, extension points, security considerations, validation method and source
evidence. Obligation is a **proposal for the contract phase**, not a settled decision.

### 6.1 Contract artifacts

| Artifact | Purpose | Proposed obligation | Inputs | Outputs | Dependencies | Extension points | Security considerations | Validation method | Source evidence |
|---|---|---|---|---|---|---|---|---|---|
| Scope contract | Declares exactly what the agent may observe, for how long, under which limits | Required | Tenant, subscriptions, resource groups, environments, period, sources, exclusions, classification, network mode, limits | Canonical document plus scope hash | None; it is the root contract | Data-flow topology, correlation identifiers, limits, network mode | Contains environment identifiers; must be consumer-owned and never committed to the framework with real values | JSON Schema validation plus hash verification | `schemas\scope-contract.schema.json` |
| Evidence manifest | Binds every conclusion to a classified, timestamped, hashed observation | Required | Execution identifier, scope hash, evidence entries | Evidence index | Scope contract | Evidence source adapters | Must carry data classification; must never contain secrets or personal data | JSON Schema validation plus SHA-256 verification | `schemas\evidence-manifest.schema.json` |
| Tool policy | Declares allowed capabilities and denies everything else | Required | Capability allow-list, deny patterns, execution limits | Runtime enforcement decision | Runtime capability identifiers | Capability allow-list per workload | Read-only is not the platform default; omission inherits write tools | Negative tests asserting denied operations | `config\tool-policies.json` |
| Handoff contract | Transfers execution between agents with idempotency and turn limits | Recommended | Execution identity, idempotency key, epoch, turn, `maxTurns`, autonomy level | Handoff record | Scope contract, evidence manifest | Epoch naming | Autonomy level must default to `READ_ONLY` | JSON Schema validation | `schemas\handoff.schema.json` |
| Change-set | Specifies a proposed mutation without executing it | Required as contract, not implemented in v1 | Proposed actions, preconditions, blast radius, rollback plan, verification method | Proposal document plus canonical hash | Scope contract, approval ledger | Execution adapter, when implemented | Must never be self-approved or auto-executed | JSON Schema validation; negative test asserting no execution path exists | `schemas\change-set.schema.json` |
| Approval ledger | Records human decisions immutably | Required when any change-set exists | Decision, decider, timestamp, hash of the approved artifact | Append-only decision record | Change-set | Identity provider binding | Agents must be structurally incapable of self-approval | JSON Schema validation plus negative test | `schemas\approval-ledger.schema.json` |
| Assessment result | Structured maturity or readiness output | Recommended | Domain scores, snapshots, evidence references | Assessment document | Evidence manifest | Domain model | Portuguese status and confidence enums must be renamed | JSON Schema validation | `schemas\assessment.schema.json` |
| Readiness result | Review-only readiness output that asserts no change was executed | Recommended | Readiness data, mode | Readiness document | Evidence manifest | Health taxonomy | `mode` must be review and `changeExecuted` must be false | JSON Schema validation | `schemas\observability-readiness.schema.json` |

### 6.2 Operational and packaging artifacts

| Artifact | Purpose | Proposed obligation | Inputs | Outputs | Dependencies | Extension points | Security considerations | Validation method | Source evidence |
|---|---|---|---|---|---|---|---|---|---|
| Agent definition | Declares identity, access level, action mode, tools and skills | Required | Identity, target resources, access level, model provider, limits | Deployable agent configuration | Tool policy, scope contract | Skills, tools, connectors, hooks | Tools must be explicitly listed; omission inherits global write tools | Structural validation; no formal schema exists in either source | `agents\*.agent.yaml`; `recipes\minimal\agent.json` |
| Skill definition | Encapsulates one procedure with inputs, outputs and guardrails | Recommended | Procedure definition, host agent, referenced contracts | Procedure execution | Agent definition | The skill body itself | Guardrails must be explicit and testable | YAML parse plus manifest consistency | `skills\*\SKILL.md`; `config\skill-manifest.json` |
| Query catalogue | Restricts diagnostics to reviewed, hash-verified queries | Recommended | Query files | Verified catalogue plus hashes | Data-source connection | The queries themselves | Prevents query injection and arbitrary data access | Hash verification in CI | `kql\queries\`; `config\tool-policies.json` |
| Connector configuration | Declares data-source connections and credential handling | Required when any connector is used | Resource identifiers, toggles, lookback | Connected data sources | Agent identity and RBAC | Connector types | Secrets must live in a gitignored external file, never in configuration | Dry-run deployment | `recipes\minimal\connectors.json` |
| RBAC assignment | Grants least-privilege read access on target scopes | Required | Target scopes, principal, role definitions | Role assignments | Agent identity | Role set per workload | Reader-only in v1; any write role is a contract violation | Deployment what-if plus an RBAC audit | `infra\rbac.bicep`; template deployment documentation |
| Guided setup | Discovers candidate workloads, selects scope and emits a scope contract | To be decided by ADR | Subscription context, operator selections | Scope contract and configuration files | Read-only discovery permissions | Discovery provider, eligibility rules | Must not collect secrets in plain text; must support non-interactive use; must not hide the deployment model | Preview step plus schema validation of the emitted contract | Net-new; absent from both sources |
| Negative test suite | Proves prohibited actions are actually impossible | Required | Prohibited operation catalogue | Pass or fail gate | Tool policy | Additional prohibitions | The primary evidence that the safety boundary holds | Executed in CI as a release gate | `tests\run-negative-tests.ps1` |
| Recipe README contract | Guarantees every recipe documents its parameters | Recommended | Recipe parameters | Documented recipe | Agent definition | Additional sections | Prevents undocumented parameters that hide behaviour | CI section and parameter checks | `validate-templates.yml` |

### 6.3 Handling of sensitive content found in the sources

Source 1 contains committed environment-specific identifiers and real customer evidence:
production tenant, subscription and resource identifiers in `config\scope-contracts\prod.json`
and `infra\parameters\prod.bicepparam`; dated assessment artifacts in `docs\assessments\`;
and real environment evidence and publication archives in `docs\evidencias\`.

No value from any of these was copied into this repository. Categories and file paths are
recorded above; values are not. This repository uses placeholders such as
`<SUBSCRIPTION_ID>`, `<TENANT_ID>` and `<WORKLOAD_NAME>` exclusively.

---

## 7. Gaps and Risks

### 7.1 Gaps in the sources that this framework must close

| Gap | Evidence | Consequence |
|---|---|---|
| No machine-validatable agent contract | Cortex agent YAML has no input/output schema; templates have no JSON Schema at all | The central deliverable of `prd.md` does not exist in either source and must be created |
| No workload discovery or selection | Absent from the guide, templates and labs | Net-new capability; the operator supplies `targetRGs` by hand today |
| No runtime enforcement of the tool policy | `config\tool-policies.json` is configuration and convention; no broker exists | The safety boundary is only as strong as correct portal configuration |
| Runtime tool identifiers unconfirmed | Stated explicitly in `config\tool-policies.json` | Deny rules may not match real tool names; must be reconciled before the policy can be trusted |
| No non-production environment separation | Only `prod.json` exists | Environment separation must be designed rather than inherited |
| Schema duplication | Identical schemas in `schemas\` and `knowledge\` | Drift risk; the framework needs a single source of truth |
| Retry, timeout and failure classification undefined | Not covered by the guide; only limits exist in Cortex | Error-handling semantics must be specified |
| Operational ownership and escalation undefined | Not covered by the guide | Runbook and ownership model must be authored |
| Rollback guarantees undefined | Cleanup exists via Terraform destroy and `azd down`; rollback policy does not | Rollback and cleanup guidance must be authored |
| No sanitization automation | Cortex relies on declarative instructions to remove secrets and personal data | An automated secret and identifier scan is required, especially before this repository becomes public |
| Prompt-injection defence is declarative only | Untrusted-content rules exist in prompts but are not enforced | Needs runtime enforcement and negative tests |
| Portuguese enum values | Assessment and state enums | Must be renamed with provenance recorded |
| Health-check and audit-trail semantics not standardized | Partial coverage in the guide | Must be specified in the contract phase |

### 7.2 Risks

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| **The framework duplicates `sreagent-templates`** | High | High | `sreagent-templates` already provides recipes, lifecycle scripts, two IaC backends and a validation workflow. Before building deployment mechanics, decide explicitly whether to consume, extend or replace it. This warrants an ADR of its own and must precede the IaC decision. |
| Generalization discards the safety semantics that make Cortex effective | High | Medium | Treat deny-by-default, the evidence chain and negative tests as core, not optional |
| Sensitive content leaks from source 1 into a repository destined to become public | High | Low | Exclusion list in section 5.4; placeholders only; automated secret scanning as a CI gate |
| Azure SRE Agent specifics leak into the runtime-agnostic core | Medium | High | Keep the binding in a separate layer; review every core artifact for runtime assumptions |
| Unconfirmed runtime tool identifiers invalidate the policy | High | Medium | Reconcile capability identifiers against the runtime before relying on deny rules |
| The two agent formats are irreconcilable | Medium | Medium | Define the contract above both; treat `agent.json` and `*.agent.yaml` as emitted bindings |
| Guided setup becomes interactive-only or hides the deployment model | Medium | Medium | `prd.md` requires non-interactive support, a version-controlled configuration file, a preview step and no hiding of the IaC model |
| Discovery requires broader permissions than the agent itself | Medium | Medium | Scope discovery to a read-only role, separate from the agent runtime identity, and document each step's permissions |
| Guide content ages | Medium | Medium | `upgradeChannel: "Preview"` and a finite region list are version-specific; pin and date any inherited assumption |
| Lab failure-injection scripts are mistaken for operational procedures | Medium | Low | Excluded by section 5.4 |

---

## 8. Open Decisions Arising From This Analysis

Each item below requires an Architecture Decision Record before implementation.

| Decision | Why it is open | Depends on |
|---|---|---|
| Relationship to `sreagent-templates`: consume, extend, or replace | The templates already implement much of the proposed deliverable | Nothing; this should be decided first |
| Infrastructure as Code technology | `prd.md` requires a weighted matrix; both Bicep and Terraform backends already exist in the templates, and Cortex's Bicep footprint is too small to be decisive | The `sreagent-templates` decision |
| Guided deployment experience and its technology | Justified by the absence of workload discovery in both sources; `prd.md` forbids assuming the technology | The IaC decision |
| Workload discovery mechanism and eligibility rules | Net-new; candidate approaches include Azure Resource Graph queries and subscription enumeration | The guided experience decision |
| Agent binding format | Two incompatible formats exist across the sources | The `sreagent-templates` decision |
| English renaming of the Portuguese vocabulary | Required by the English-only constraint; provenance must be preserved | Nothing |
| Obligation level of each contract area: required, recommended, optional or out of scope | `prd.md` requires classification with rationale and evidence; section 6 proposes but does not settle it | Nothing |
| Tool-policy enforcement model | Configuration alone is insufficient | Runtime capability reconciliation |
| Single source of truth for schemas | Cortex duplicates schemas across two directories | Nothing |

---

## 9. Traceability

| `prd.md` requirement | Where satisfied |
|---|---|
| Mandatory preflight, items 1 to 6 | Section 1 |
| Source analysis of the existing implementation | Section 2 |
| Source analysis of the guide | Section 3 |
| Inconsistencies between guide and implementation | Section 4 |
| Pattern extraction into four categories | Section 5 |
| Per-artifact documentation of purpose, obligation, inputs, outputs, dependencies, extension points, security, validation and evidence | Section 6 |
| Sensitive-content handling with placeholders | Sections 1, 5.4 and 6.3 |
| Gaps and technical debt | Section 7.1 |
| Risks | Section 7.2 |
| Decisions requiring human review | Section 8 |

Not yet produced, and deferred to later slices: the Minimum SRE Agent Contract, the
architecture overview and diagram, the Infrastructure as Code decision record, the guided
deployment decision record, the configuration schema, and the implementation plan.

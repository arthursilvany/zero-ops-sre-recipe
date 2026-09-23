# Feature Specification: Zero Ops SRE Agent Recipe Framework

- **Created on**: 2026-09-23
- **Status**: Draft

## Executive Summary

- **Objective**: Provide a reusable, version-controlled recipe that lets a team define, configure, deploy, validate, observe, extend and safely remove a read-only SRE agent for an Azure workload without editing the framework core.
- **Primary user**: Platform and SRE engineers at customer organizations; secondary, consultants and CSAs delivering on the customer's behalf.
- **Value delivered**: Removes the per-engagement rebuild of the agent contract, evidence model, configuration shape and deployment path, so reliability outcomes stop depending on the individual engineer.
- **Scope**: Included — minimum agent contract, machine-validatable configuration and evidence model, guided workload discovery and scope selection, IaC-based provisioning, repeatable deployment, local and post-deployment validation, safety controls, extension points, rollback and cleanup, traceability. Excluded — executing mutating remediation, multi-runtime bindings, multi-cloud, self-service by application teams, and any technology selection.
- **Change type**: new surface
- **Describes AI capability**: yes
- **Primary success criterion**: A new workload is onboarded with zero edits to the framework core, and the read-only boundary is proven by executable negative tests.

This specification is the requirements baseline for Slice 1 of the `prd.md` delivery
strategy. It states WHAT the framework must do. It deliberately selects no technology:
the Infrastructure as Code technology, the guided-experience technology, the workload
discovery mechanism and the agent binding format are settled by Architecture Decision
Records listed in the *Open Decisions This Specification Depends On* section.

## Non-Scope *(required)*

- **Executing mutating remediation.** The core performs diagnostics only. The change-set and approval-ledger contracts exist ahead of the capability, as a defined contract plus an extension point that is explicitly not implemented. Reason: the read-only boundary is the primary safety guarantee of the first version.
- **Multi-runtime agent bindings.** Azure SRE Agent is the first and only concrete binding. Reason: a second binding cannot be validated without a second runtime, and the runtime-agnostic core already preserves the option.
- **Multi-cloud or non-Azure targets.** Reason: all reference evidence and the deployment model are Azure-specific.
- **Self-service adoption by application teams without an SRE intermediary.** Reason: the guided experience is calibrated for an operator accountable for subscription-scoped permissions.
- **Selecting any technology.** IaC language, guided-experience technology, discovery mechanism, binding format and tool-policy enforcement model are decided by ADR, not here.
- **Reproducing customer-specific content.** The exclusion list in `source-analysis.md` section 5.4 is binding: reference-customer naming, the `CTX-01..CTX-13` procedure numbering, reference-customer data-flow stage names and correlation identifiers, real environment evidence, and lab failure-injection scripts.
- **Implementing a workload observability stack.** The framework defines observability consumers and contracts; it does not provision the workload's own telemetry pipeline.
- **Settling the final Required / Recommended / Optional / Out-of-scope classification of every contract area.** This specification carries forward the proposed obligation levels from `source-analysis.md` section 6; `prd.md` assigns the final classification to the contract phase.

## Assumptions

- **Obligation levels in `source-analysis.md` section 6 are proposals, not decisions.** They are carried into this specification as requirements so the contract phase has a baseline to confirm, refine or overturn with recorded rationale and evidence.
- **The consuming team owns its own Azure subscription and target resource groups.** Basis: both reference sources assume subscription-scoped access held by the operator; the framework never provisions a subscription.
- **Discovery permissions and agent runtime permissions are separable.** Basis: `envisioning/README.md` risk "Workload discovery requires broader read permissions than the agent itself". Each step documents exactly which permissions it needs.
- **The scope contract is consumer-owned.** The framework ships the schema and examples with placeholders only; a populated scope contract lives in the consumer's repository, never in the framework.
- **`examples/minimal/` proves neutrality structurally.** Basis: `envisioning/README.md` constraint that the reference workload is AKS while the minimal example stays workload-neutral.
- **The repository is private today and is expected to become public.** Sanitization discipline is therefore a day-one requirement, not a pre-release task.
- **"Zero core edits" is measured by file path.** Onboarding a workload touches only configuration, example and extension paths; any diff inside a path declared as core fails the criterion.
- **No fixed external delivery date.** Basis: `envisioning/README.md` constraints. Sequencing follows Slice 1 through Slice 5.

## AI Cost Posture *(required when "Describes AI capability" is "yes"; omit otherwise)*

The framework specifies and deploys an agent; it does not host a model. Model selection,
inference cost and latency are governed by the agent runtime, which is Azure SRE Agent for
the first and only binding. The commitments below are therefore stated as governance
obligations on the framework rather than as tiers chosen by this specification.

- **Model-tier commitment** (per step where relevant): N/A - model chosen by runtime. The agent runtime governs model selection; the framework declares a model-provider setting in configuration and must not hard-code a model identifier in the runtime-agnostic core.
- **Latency budget**: N/A - governed by the runtime platform. The framework instead commits to bounded execution: every agent execution is constrained by explicit limits on tool calls, wall-clock duration, result-set size and per-query timeout, declared in configuration. *Behavior on breach:* halt the execution and record the partial result with an explicit incomplete state; never extrapolate or treat missing data as zero.
- **Prompt-stability invariant**: agent instructions, tool policy and the diagnostic query catalogue are version-controlled artifacts in the consuming repository. Any change to them is a configuration change that is reviewable in version control and recorded in the changelog. Untrusted diagnostic content is never appended to instructions, so retrieved content cannot alter the prompt contract.
- **Per-call cost ceiling**: N/A - billed via the runtime platform plan. The framework requires a configurable consumption limit for the agent and requires it to be surfaced in the preview step before deployment, so the operator sees the committed ceiling before any resource is provisioned. *Behavior on breach:* governed by the runtime platform.
- **Cost-incident escalation**: N/A - cost governed by the runtime platform plan. The framework requires the consumption limit and the execution limits to be documented in the operations guide together with the action to take when either is reached.

## User Scenarios & Tests *(required)*

### User Story 1 - Understand the contract and validate a configuration offline (Priority: P1)

A platform engineer clones the repository, reads the minimum SRE agent contract, copies the
minimal example, edits configuration to describe their workload, and validates it locally
against the published schemas. No Azure subscription, no credentials and no deployment are
involved.

**Why this priority**: This is the smallest slice that delivers the core value of the
framework, which is removing the need to read another customer's source code in order to
learn what an SRE agent must declare. It is also the precondition for every other journey:
if the contract and schemas are not usable offline, nothing downstream is trustworthy.

**Independent Test**: Can be fully tested by cloning the repository on a machine with no
Azure access, running the documented validation command against `examples/minimal/`, then
against a deliberately invalid configuration, and confirming a pass and an actionable
failure respectively. Delivers a reviewed, schema-valid workload configuration.

**Acceptance Scenarios**:

1. **Given** a clone of the repository and no Azure credentials, **When** the engineer runs the documented local validation command against `examples/minimal/`, **Then** every schema-backed artifact validates and the command exits successfully.
2. **Given** a configuration with an unknown property, **When** local validation runs, **Then** it fails, names the offending artifact and property path, and states the allowed values or shape.
3. **Given** the minimum SRE agent contract document, **When** the engineer looks up any candidate area listed in `prd.md`, **Then** that area is classified as Required, Recommended, Optional or Out of scope, with a rationale and a citation to source evidence.
4. **Given** the contract document, **When** the engineer searches for runtime-specific identifiers in any artifact declared as core, **Then** none are present, and every runtime-specific element appears only in the binding layer.

---

### User Story 2 - Discover candidate workloads and emit a scope contract (Priority: P2)

The engineer runs the guided pre-deployment step. It discovers candidate workloads within
a subscription scope they supply, presents them with enough context to choose, lets them
select which are in scope, and writes a version-controlled scope contract plus the
configuration files that the deployment will consume. Nothing is provisioned.

**Why this priority**: Neither reference source provides workload discovery
(`source-analysis.md` section 4). It is the net-new capability that converts a hand-written
`targetRGs` parameter into a reviewable, hashed declaration of exactly what the agent may
observe, which is the root contract every other artifact depends on.

**Independent Test**: Can be fully tested against a subscription scope in interactive mode,
then re-run in non-interactive mode consuming the previously emitted configuration, and
confirming the emitted scope contract is schema-valid and identical across both runs.
Delivers a committed scope contract.

**Acceptance Scenarios**:

1. **Given** a subscription scope and read-only discovery permissions, **When** the guided step runs, **Then** it lists candidate workloads with the attributes needed to decide, and provisions nothing.
2. **Given** a candidate list, **When** the operator selects a subset, **Then** the emitted scope contract contains exactly the selected resources, plus the declared exclusions, limits and period, and validates against the scope-contract schema.
3. **Given** the guided step in non-interactive mode with a previously emitted configuration file, **When** it runs, **Then** it completes without prompting and produces a byte-identical scope contract.
4. **Given** an input in an invalid format, **When** it is supplied, **Then** the step rejects it, explains the expected format in plain English, and does not continue.
5. **Given** insufficient permission to enumerate part of the requested scope, **When** discovery runs, **Then** the unreachable portion is reported as an explicit access-denied state, is never silently omitted, and the operator is told which permission is missing.
6. **Given** any input field, **When** it is presented, **Then** no field requests a secret in plain text, and secret-bearing settings are expressed as references to externally held values.

---

### User Story 3 - Provision, deploy and validate a read-only agent (Priority: P3)

Using the committed configuration, the engineer previews what would be created, provisions
the required Azure resources through Infrastructure as Code, deploys the agent binding,
then runs validation to confirm the deployment is healthy and read-only.

**Why this priority**: This is the first journey that changes a live environment, so it
depends on both preceding stories. It is the point at which the framework's claim of a
repeatable deployment becomes verifiable.

**Independent Test**: Can be fully tested by running the preview against a real
subscription without applying, then applying, then running the validation command and
confirming every check reports a result. Delivers a deployed, validated agent.

**Acceptance Scenarios**:

1. **Given** a validated configuration, **When** the engineer runs the preview step, **Then** it lists every resource that would be created, changed or deleted, and every role assignment that would be granted, without changing anything.
2. **Given** an approved preview, **When** deployment runs, **Then** every resource is created from version-controlled configuration and the underlying Infrastructure as Code model remains visible rather than hidden behind the guided experience.
3. **Given** a completed deployment, **When** the same deployment command is run again with unchanged configuration, **Then** it completes successfully and reports no unintended changes.
4. **Given** a completed deployment, **When** the validation command runs, **Then** it reports a pass or fail result for each check, including identity, role assignments, data-source connectivity and tool-policy posture.
5. **Given** a completed deployment, **When** the granted role assignments are audited, **Then** only read-scoped roles are present on the declared scopes and no role granting write, delete or action permissions exists.
6. **Given** a deployment failure, **When** it occurs, **Then** the error identifies the failing step, the probable cause and the documented recovery or cleanup action.

---

### User Story 4 - Observe agent behavior through a defensible evidence chain (Priority: P4)

The engineer inspects what the agent did and why: which observations it made, where each
one came from, how fresh it was, what it could not observe, and which conclusions are
derived rather than observed.

**Why this priority**: `envisioning/README.md` records that the value proposition of the
reference implementation is the chain of evidence rather than the agent itself. Without it,
agent output is an unverifiable assertion.

**Independent Test**: Can be fully tested by executing one diagnostic run against a
deployed agent, then validating the emitted evidence manifest against its schema and
confirming that every conclusion resolves to at least one evidence entry.

**Acceptance Scenarios**:

1. **Given** a completed diagnostic execution, **When** the evidence manifest is inspected, **Then** it is bound to an execution identifier and to the hash of the scope contract in force.
2. **Given** an evidence entry, **When** it is inspected, **Then** it declares its provenance classification, its collection timestamp, its freshness, its data classification and its content hash.
3. **Given** a data source the agent could not reach, **When** the manifest is inspected, **Then** the gap is recorded explicitly as unobserved, and no estimated or zero value is substituted for it.
4. **Given** any conclusion in agent output, **When** it is traced, **Then** it resolves to one or more evidence entries, or is explicitly marked as derived, inferred or recommended rather than observed.
5. **Given** a completed execution, **When** the audit record is inspected, **Then** it lists the actions the agent took, and contains no secret and no sensitive workload payload.

---

### User Story 5 - Onboard a second workload with zero core edits (Priority: P5)

A different workload is onboarded by adding configuration and, where needed, a workload
extension. The framework core is untouched, and the engineer can prove it.

**Why this priority**: This is the headline KPI from envisioning. It is placed after the
first end-to-end deployment because it can only be demonstrated once one workload has
already been onboarded.

**Independent Test**: Can be fully tested by onboarding the workload-neutral minimal
example and then the AKS reference workload in the same clone, and inspecting the resulting
diff. Delivers a second working configuration plus evidence that the core was not modified.

**Acceptance Scenarios**:

1. **Given** a clone at a released version, **When** a second workload is onboarded, **Then** the resulting diff touches only configuration, example and extension paths, and no path declared as core.
2. **Given** the extension guide, **When** an engineer needs workload-specific behavior, **Then** each supported extension point is documented with its inputs, outputs and the guarantees that survive a core upgrade.
3. **Given** `examples/minimal/`, **When** it is inspected, **Then** it contains no reference to any specific workload type, proving the core is not coupled to AKS.
4. **Given** `examples/reference-workload/`, **When** it is inspected, **Then** it demonstrates AKS as the reference workload using placeholders only.

---

### User Story 6 - Upgrade, roll back and clean up safely (Priority: P6)

The engineer upgrades to a newer framework version, or reverts to the previously committed
configuration, or removes everything the framework provisioned.

**Why this priority**: It closes the lifecycle. It is last because it presupposes a
deployed agent, but it is a release blocker: an asset that cannot be removed cleanly cannot
be recommended for a customer environment.

**Independent Test**: Can be fully tested by deploying, running cleanup, and confirming
that no resource or role assignment created by the framework remains. Delivers a verified
teardown path.

**Acceptance Scenarios**:

1. **Given** a deployed agent, **When** the documented cleanup procedure runs, **Then** every resource and role assignment created by the framework is removed, and a verification step confirms none remains.
2. **Given** a deployed agent and a previously committed configuration, **When** rollback is performed, **Then** the prior configuration is redeployable using the same documented commands, and the rollback trigger conditions and steps are documented.
3. **Given** a new framework version, **When** the upgrade guidance is followed, **Then** breaking changes to any schema are listed with migration guidance, and the schema version identifier changes.
4. **Given** cleanup, **When** it runs, **Then** it never removes a resource that the framework did not create.

### Edge Cases

- What happens when discovery finds no eligible workload in the supplied scope? The step must report an empty result with the eligibility rules that were applied, and exit without producing an empty or partial scope contract.
- What happens when discovery is permitted for some subscriptions but denied for others? Partial results are returned, the denied portion is reported as an explicit access-denied state, and the operator decides whether to proceed with a reduced scope.
- What happens when the operator selects a workload that is later deleted before deployment? Preview must detect that a declared resource no longer resolves and fail before provisioning, rather than deploying against a stale scope.
- What happens when a configuration is valid against the schema but semantically impossible, for example an empty selection or a period whose end precedes its start? Validation must include semantic checks beyond structural schema conformance and must fail with an actionable message.
- What happens when the runtime offers tools that the tool policy does not name? The policy denies by default, so unnamed capabilities are unavailable; the framework must document that omitting an explicit tool selection at the runtime can otherwise inherit global tools including write tools.
- What happens when a diagnostic result contains text that resembles an instruction? It is treated as data, never as an instruction, and this is asserted by a negative test.
- What happens when the same scope contract is deployed to two environments? Environment settings must be separable from workload settings so that the same workload definition can be bound to a non-production and a production environment.
- What happens when an execution limit is reached mid-run? The execution halts, the partial result is recorded with an explicit incomplete state, and no value is extrapolated.
- What happens when a consumer edits the core anyway? The framework cannot prevent it, but the upgrade guidance must state that core edits void the zero-core-edit guarantee, and the documented onboarding check must surface such a diff.

### Failure Modes *(include if the feature has external dependencies or shared state)*

- **Discovery provider unavailable or throttled**: the guided step fails closed with an actionable error naming the provider and the retry guidance. It must not emit a scope contract from a partial enumeration without marking it as partial.
- **Deployment partially applies**: some resources created, others not. The framework must leave the environment inspectable, report exactly which step failed, and point to the documented cleanup or re-run path. Re-running with unchanged configuration must converge rather than duplicate.
- **Role assignment propagation delay**: a deployment succeeds but validation fails because permissions are not yet effective. Validation must distinguish "not yet effective" from "not granted", and document the expected settling behavior.
- **Data source unreachable at execution time**: the agent records an explicit unobserved state; it never substitutes an estimate, and the affected conclusions are downgraded from observed.
- **Two operators deploy against overlapping scopes concurrently**: role assignments and resources must be deterministic and idempotent so that concurrent convergent deployments do not corrupt state. Divergent concurrent configurations are a documented conflict, resolved in version control, not at deployment time.
- **Consistency model**: eventual is acceptable for role assignment propagation and telemetry availability, and must be documented as such. Contract validation is immediate: an invalid artifact is rejected before any provisioning occurs.
- **A consumer pins an older framework version while the core advances**: schema version identifiers and migration guidance must let the older consumer keep operating without adopting the new version.

## Requirements *(required)*

Every requirement carries a unique identifier, a v1 scope decision and a verification
method. Verification methods are limited to three kinds so that later phases can automate
them: **Inspection** (a reviewer or a documented check reads the artifact), **Automated**
(a check runs in CI or locally and returns pass or fail), and **Command** (a documented
command is executed and its output is the evidence).

### Functional Requirements

#### Group A - Minimum SRE agent contract

Traces to `prd.md` sections *Functional Outcome* item 1 and *Minimum SRE Agent Contract*.

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| FR-01 | The framework MUST publish a Minimum SRE Agent Contract that classifies every candidate area listed in `prd.md` as Required, Recommended, Optional or Out of scope, with a recorded rationale and a citation to source evidence. | v1 | Every candidate area named in `prd.md` appears exactly once with a classification, a rationale and an evidence citation. No area is unclassified. | Inspection |
| FR-02 | The framework MUST provide a machine-validatable schema for every artifact the contract classifies as Required. | v1 | Each Required artifact resolves to exactly one schema, and a documented command validates an instance against it. | Automated |
| FR-03 | The framework MUST define a canonical English vocabulary for execution states and evidence provenance, and MUST record the original reference values as provenance without using them as identifiers. | v1 | No non-English identifier or enum value exists in any published artifact. A provenance mapping exists for every renamed value, including the access-denied state and the assessment status and confidence enums. | Automated |
| FR-04 | Artifacts declared as core MUST NOT depend on any runtime-specific identifier, format or capability name. Runtime-specific elements MUST live in a separately identified binding layer. | v1 | Core paths contain no runtime-specific identifier. The binding layer is explicitly enumerated, and removing it leaves the core internally consistent. | Inspection, Automated |
| FR-05 | Each schema MUST exist exactly once in the repository and MUST carry an explicit version identifier. | v1 | No duplicate schema definition exists at two paths. Every schema instance declares the version it conforms to. | Automated |
| FR-06 | The contract MUST define the change-set artifact, the approval-ledger artifact and their relationship, while providing no execution path for any mutation. | v1, contract only | Both artifacts have schemas and documentation. A negative test asserts that no code path executes a change-set. | Automated |
| FR-07 | The contract MUST define error handling, retry and timeout semantics, including how an incomplete execution is represented. | v1 | Each failure class maps to a defined state value, and the incomplete-execution representation is schema-backed. | Inspection |
| FR-08 | The contract MUST define health-check and audit-trail semantics. | v1 | Health-check outputs and audit records are described with their required fields and their producer. | Inspection |
| FR-09 | The contract MUST define operational ownership and escalation expectations for a deployed agent. | v1, documentation only | The operations guide names the owning role, the escalation path and the conditions that trigger escalation. | Inspection |

#### Group B - Guided scope definition and workload discovery

Traces to `prd.md` section *Guided Deployment Experience* and the envisioning scope item
"a guided pre-deployment step that discovers and selects the target workloads and emits a
version-controlled scope contract". This capability is net-new: neither reference source
provides it (`source-analysis.md` section 4).

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| FR-10 | The framework MUST provide a guided pre-deployment step that discovers candidate workloads within an operator-supplied scope. | v1 | Running the step against a scope returns a candidate list, or an explicit empty result with the eligibility rules applied. | Command |
| FR-11 | Discovery MUST require read-only permissions only, and the exact permissions required MUST be documented separately from the permissions the deployed agent requires. | v1 | The documentation names the discovery permission set and the agent permission set distinctly. Discovery performs no write operation. | Inspection, Automated |
| FR-12 | The framework MUST publish the eligibility rules that determine whether a discovered resource is a candidate. | v1 | The rules are documented and are the same rules the step reports when it returns an empty result. | Inspection |
| FR-13 | The operator MUST be able to select which discovered candidates are in scope. | v1 | The emitted scope contract contains exactly the selected candidates and no others. | Command |
| FR-14 | The guided step MUST emit a version-controlled scope contract that validates against its schema. | v1 | The emitted artifact is a file suitable for commit and passes schema validation without modification. | Automated |
| FR-15 | The guided step MUST collect only inputs that are required, and MUST explain each input in plain English at the point of collection. | v1 | Every collected input maps to a field consumed by a downstream artifact. Every input has an explanation. No input is collected that is never used. | Inspection |
| FR-16 | The guided step MUST validate the format of every input and MUST reject invalid input with an actionable message naming the expected format. | v1 | For each input, an invalid value produces a rejection that states the expected format and does not proceed. | Automated |
| FR-17 | The guided step MUST NOT collect or persist any secret in plain text. Secret-bearing settings MUST be expressed as references to externally held values. | v1 | No emitted artifact contains a secret. Secret-bearing settings resolve to external references. | Automated |
| FR-18 | The guided step MUST support non-interactive execution driven entirely by a version-controlled configuration file. | v1 | A non-interactive run consuming a previously emitted configuration completes without prompting. | Command |
| FR-19 | Interactive and non-interactive execution with equivalent inputs MUST produce identical output artifacts. | v1 | Byte-identical scope contracts result from both modes given the same inputs. | Automated |
| FR-20 | The guided step MUST provide a preview or validation step before any resource is provisioned, and MUST provision nothing until the operator explicitly confirms. | v1 | Preview lists intended creations, changes, deletions and role assignments, and exits without side effects. | Command |
| FR-21 | The guided step MUST NOT hide the underlying Infrastructure as Code deployment model. | v1 | The generated Infrastructure as Code inputs are visible, reviewable files, and the documentation shows how to deploy without the guided step. | Inspection |
| FR-22 | When discovery is not permitted for part of the requested scope, the step MUST report that portion as an explicit access-denied state, name the missing permission, and MUST NOT silently reduce the scope. | v1 | A scope containing an unreadable portion yields a reported denial rather than a shorter candidate list. | Command |
| FR-23 | The guided step MUST record the scope contract's canonical hash so that downstream artifacts can bind to the exact approved scope. | v1 | The emitted contract carries a hash, and recomputing it over the canonical form reproduces the same value. | Automated |

#### Group C - Configuration model

Traces to `prd.md` section *Configuration Design*.

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| FR-24 | The framework MUST define a versioned configuration contract that distinguishes global framework defaults, environment settings, workload-specific settings, tool and integration settings, observability settings, remediation permissions, approval policies, and externally referenced sensitive values. | v1 | Each of the eight concerns is separately addressable, and the documentation states which file or section owns each. | Inspection, Automated |
| FR-25 | Configuration MUST be validatable offline, with no Azure subscription and no credentials. | v1 | The documented validation command succeeds on a machine with no Azure access. | Command |
| FR-26 | The framework MUST ship a minimal valid configuration example and a fuller reference example, both of which MUST validate. | v1 | Both examples pass validation in CI. | Automated |
| FR-27 | Configuration validation MUST reject unknown properties and MUST report the offending artifact and property path. | v1 | An instance with an unknown property fails and names the path. | Automated |
| FR-28 | Configuration validation MUST include semantic checks beyond structural conformance, at minimum an empty in-scope selection and an inverted time period. | v1 | Both cases fail validation with an actionable message. | Automated |
| FR-29 | The framework MUST publish backward-compatibility and migration guidance for every schema version change. | v1 | Each version change lists breaking changes and the migration action, or states that none apply. | Inspection |
| FR-30 | Sensitive values MUST be referenced externally and MUST NOT be storable in committed configuration. | v1 | No schema permits an inline secret field; the documented mechanism is external reference. | Automated |

#### Group D - Provisioning and deployment

Traces to `prd.md` sections *Functional Outcome* items 3 and 4, *Infrastructure as Code
Decision*, and *Security and Responsible AI Requirements*.

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| FR-31 | The framework MUST provision the Azure resources an agent requires through Infrastructure as Code driven by version-controlled configuration. | v1 | Every provisioned resource traces to a version-controlled input. No resource is created by an undocumented manual step. | Command, Inspection |
| FR-32 | Deployment MUST be repeatable: a documented command sequence MUST produce the same result, and re-running with unchanged configuration MUST report no unintended changes. | v1 | A second run against an unchanged configuration converges. | Command |
| FR-33 | The framework MUST grant least-privilege, read-scoped role assignments only. No role granting write, delete or action permissions on workload resources may be granted by the core. | v1 | An audit of granted assignments finds read-scoped roles only. A negative test asserts that no write-capable role is requested. | Automated |
| FR-34 | The agent identity MUST use managed identity where the selected architecture supports it, and MUST support binding to an existing identity supplied by the consumer. | v1 | The configuration accepts an existing identity reference, and the default path creates a managed identity rather than a credential. | Inspection, Command |
| FR-35 | No credential, key or token may be required as an Infrastructure as Code input. | v1 | No parameter accepts a secret value. | Automated |
| FR-36 | The framework MUST support at least a non-production and a production environment binding for the same workload definition without duplicating the workload definition. | v1 | The same workload configuration deploys to two environment configurations. | Command |
| FR-37 | The framework MUST document whether it consumes, extends or replaces existing SRE agent template tooling, and MUST NOT maintain equivalent implementations in more than one Infrastructure as Code language without a recorded justification. [NEEDS CLARIFICATION: `sreagent-templates` already provides recipes, lifecycle scripts, Bicep and Terraform backends, `azd` integration and a validation workflow (`source-analysis.md` sections 3.2 and 8). Whether this framework consumes, extends or replaces it materially changes the scope of Group D and Group E, and that decision precedes the Infrastructure as Code decision.] | v1 | An ADR records the relationship and its consequences for this requirement group. | Inspection |
| FR-38 | Deployment errors MUST identify the failing step, the probable cause and the documented recovery or cleanup action. | v1 | An induced failure produces a message satisfying all three elements. | Command |

#### Group E - Validation

Traces to `prd.md` sections *Functional Outcome* item 5 and *Testing and Quality Gates*.

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| FR-39 | The framework MUST provide a post-deployment validation command that reports a pass or fail result for each check, covering at minimum identity, role assignments, data-source connectivity and tool-policy posture. | v1 | Running it against a deployment yields a per-check result set. | Command |
| FR-40 | The framework MUST provide an executable negative test suite that asserts prohibited operations are actually denied, and this suite MUST be enforced as a release gate. | v1 | The suite runs in CI, fails the build when an assertion fails, and covers at minimum write denial, self-approval denial, change-set execution denial and untrusted-content handling. | Automated |
| FR-41 | Tests that require an Azure subscription MUST be separated from tests that run locally, and the separation MUST be documented. | v1 | The local test command runs to completion with no Azure access. | Command |
| FR-42 | The framework MUST NOT claim that a live deployment passed unless it was executed and evidence is available. | v1 | Any claim of a live deployment result is accompanied by its evidence, or is stated as unvalidated. | Inspection |
| FR-43 | Validation MUST distinguish "permission not yet effective" from "permission not granted". | v1 | The two conditions produce distinguishable results and documented guidance. | Command |

#### Group F - Observability and evidence

Traces to `prd.md` sections *Functional Outcome* item 6 and *Security and Responsible AI
Requirements*.

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| FR-44 | Every diagnostic execution MUST produce an evidence manifest bound to an execution identifier and to the hash of the scope contract in force. | v1 | The manifest validates against its schema and its scope hash matches the deployed contract. | Automated |
| FR-45 | Every evidence entry MUST declare its provenance classification, collection timestamp, freshness, data classification and content hash. | v1 | No entry omits any of the five attributes. | Automated |
| FR-46 | Data that could not be observed MUST be recorded explicitly as unobserved. The framework MUST NOT substitute an estimate, a default or zero for missing data. | v1 | A run with an unreachable source records an explicit unobserved state. A negative test asserts no default substitution. | Automated |
| FR-47 | Every conclusion in agent output MUST resolve to one or more evidence entries, or be explicitly marked as derived, inferred or recommended rather than observed. | v1 | Sampled conclusions all resolve or carry a non-observed classification. | Inspection, Automated |
| FR-48 | The framework MUST preserve an auditable record of the actions the agent took, where the architecture supports it. | v1 | An audit record exists for an execution and lists actions taken. | Command |
| FR-49 | Audit records, evidence manifests and logs MUST NOT contain secrets or sensitive workload payloads. | v1 | An automated scan of emitted artifacts finds no secret pattern and no raw payload field. | Automated |
| FR-50 | The framework MUST support restricting diagnostics to a reviewed catalogue of queries rather than permitting arbitrary query construction. | v1 | The catalogue is version-controlled and integrity-verified, and arbitrary construction is denied by the tool policy. | Automated |

#### Group G - Safe operational controls

Traces to `prd.md` section *Security and Responsible AI Requirements* and
`source-analysis.md` sections 2.5 and 5.1.

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| FR-51 | The framework MUST declare a tool policy that is deny-by-default, resolves conflicts in favor of denial, and fails closed. | v1 | The policy declares all three properties, and a capability absent from the allow-list is denied. | Automated |
| FR-52 | The tool policy MUST express explicit deny rules for writes, destructive operations, arbitrary execution, secrets access, self-approval, external publication and agent-created schedules. | v1 | Each named category has a deny rule and a corresponding negative test. | Automated |
| FR-53 | The tool policy MUST declare execution limits covering tool-call count, wall-clock duration, result-set size and per-query timeout. | v1 | All four limits are configurable and enforced; exceeding one halts the execution with an incomplete state. | Automated |
| FR-54 | The framework MUST document that read-only is not the runtime default, and MUST state the configuration action required to avoid inheriting write-capable tools. | v1 | The security documentation states this explicitly, citing the risk. | Inspection |
| FR-55 | Untrusted diagnostic content, including logs, payloads, documents and pull-request text, MUST be treated as data and MUST NOT be treated as instructions. | v1 | A negative test supplies instruction-shaped content in a diagnostic result and asserts it is not acted upon. | Automated |
| FR-56 | The framework MUST make the agent structurally incapable of approving its own proposals. | v1 | The approval ledger requires a human decider distinct from the agent identity, and a negative test asserts self-approval is rejected. | Automated |
| FR-57 | Read-only diagnostic actions MUST be separated from proposed mutations at the contract level. | v1 | Diagnostic outputs and change-set proposals are distinct artifacts with distinct schemas. | Inspection |
| FR-58 | Any future mutating remediation MUST require an explicit recorded approval before execution. | Deferred, contract defined in v1 | The change-set lifecycle requires an approval-ledger entry referencing the hash of the approved proposal. No execution path exists in v1. | Inspection, Automated |
| FR-59 | The framework MUST document agent boundaries and prohibited actions in operator-facing documentation. | v1 | A prohibited-actions list exists and matches the deny rules in the tool policy. | Inspection, Automated |

#### Group H - Extensibility

Traces to `prd.md` section *Functional Outcome* item 8 and the envisioning technical
objective.

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| FR-60 | Onboarding a new workload MUST require zero edits to the framework core. | v1 | A diff after onboarding touches only configuration, example and extension paths. | Automated |
| FR-61 | The framework MUST declare explicitly which paths constitute the core and which are consumer-editable. | v1 | The declaration exists and is the input to the check in FR-60. | Inspection |
| FR-62 | The framework MUST document every supported extension point with its inputs, outputs and the guarantees that survive a core upgrade. | v1 | Each extension point identified in `source-analysis.md` section 5.3 is either documented or explicitly declared out of scope. | Inspection |
| FR-63 | `examples/minimal/` MUST remain workload-neutral and MUST contain no reference to any specific workload type. | v1 | An automated check finds no workload-type-specific identifier in the minimal example. | Automated |
| FR-64 | `examples/reference-workload/` MUST demonstrate AKS as the reference workload using placeholders only. | v1 | The example deploys conceptually against AKS and contains no real identifier. | Inspection, Automated |
| FR-65 | The quickstart MUST state the counted number of files a team edits and the counted number of manual steps from clone to a validated deployment. | v1 | Both counts are present and match the documented procedure. | Inspection |

#### Group I - Upgrade, rollback and cleanup

Traces to `prd.md` sections *Functional Outcome* item 9 and *Required Documentation* item 16.

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| FR-66 | The framework MUST provide a documented cleanup procedure that removes every resource and role assignment it created, plus a verification step confirming removal. | v1 | After cleanup, the verification step reports nothing remaining. | Command |
| FR-67 | Cleanup MUST NOT remove any resource the framework did not create. | v1 | A pre-existing resource inside the target scope survives cleanup. | Command |
| FR-68 | The framework MUST document rollback: its trigger conditions, its ordered steps, and the fact that a prior committed configuration is redeployable with the same commands. | v1 | The rollback procedure is documented and executable. | Inspection, Command |
| FR-69 | The framework MUST be versioned, and every release MUST record its changes, including any breaking schema change. | v1 | A changelog entry exists per release and names breaking changes. | Inspection |
| FR-70 | A consumer pinned to an older framework version MUST be able to continue operating without adopting a newer version. | v1 | Version identifiers permit pinning, and upgrade guidance does not require a lockstep upgrade. | Inspection |

#### Group J - Traceability

Traces to `prd.md` sections *Functional Outcome* item 10 and *Definition of Done*.

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| FR-71 | The framework MUST maintain a traceability record linking requirements, ADRs, tasks, tests and implemented artifacts. | v1 | Every requirement in this specification resolves to at least one downstream artifact, or is explicitly recorded as deferred. | Inspection, Automated |
| FR-72 | Every material architectural decision MUST be recorded in an ADR, and artifacts affected by a decision MUST reference it. | v1 | Each decision listed in this specification's open-decisions section resolves to an ADR before the affected implementation merges. | Inspection |
| FR-73 | Deviations from the reference implementation MUST be explicit and justified. | v1 | Each deviation is recorded with its rationale. | Inspection |
| FR-74 | Known limitations and unvalidated assumptions MUST be documented. | v1 | A known-limitations document exists and includes every unvalidated assumption, including unconfirmed runtime capability identifiers. | Inspection |

### Non-Functional Requirements

#### Security and sanitization

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| NFR-01 | All environment-specific values in the repository MUST be placeholders, for example `<SUBSCRIPTION_ID>`, `<TENANT_ID>` and `<WORKLOAD_NAME>`. | v1 | An automated scan finds no tenant identifier, subscription identifier, resource identifier, endpoint or customer name. | Automated |
| NFR-02 | No secret, token, credential, certificate or private key may be committed. | v1 | Secret scanning runs as a CI gate and blocks the build on detection. | Automated |
| NFR-03 | The exclusion list in `source-analysis.md` section 5.4 MUST be enforced; no excluded item may appear in any form. | v1 | An automated check covers the machine-detectable items; the remainder is covered by review. | Automated, Inspection |
| NFR-04 | A sanitization audit MUST pass before repository visibility is changed to public. | v1 | The audit is defined, executable and recorded as a precondition. | Automated, Inspection |
| NFR-05 | The security model MUST document threat considerations for prompt injection, unsafe tool invocation, excessive permissions, data leakage and untrusted diagnostic content, each with its mitigation and the test that covers it. | v1 | All five threats are covered with a named mitigation and a named test. | Inspection |
| NFR-06 | Static security analysis MUST run against Infrastructure as Code in CI where practical, and any exclusion MUST be recorded with a reason. | v1 | The check runs or its absence is justified in writing. | Automated, Inspection |
| NFR-07 | Where a reference source conflicts with these security principles, the conflict MUST be documented and a safer design proposed rather than reproduced. | v1 | Each such conflict identified in the source analysis has a recorded resolution. | Inspection |

#### Quality gates

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| NFR-08 | CI MUST validate formatting and linting for every authored language in the repository, including Markdown. | v1 | The gate fails on a lint violation. | Automated |
| NFR-09 | CI MUST validate documentation links. | v1 | A broken internal link fails the build. | Automated |
| NFR-10 | CI MUST validate every shipped configuration example against its schema. | v1 | An invalid example fails the build. | Automated |
| NFR-11 | CI MUST validate Infrastructure as Code syntax or compilation. | v1 | A malformed template fails the build. | Automated |
| NFR-12 | CI MUST run unit tests for reusable logic. | v1 | Unit tests execute and report results. | Automated |
| NFR-13 | CI MUST verify consistency between documented commands and the commands that actually exist. | v1 | A documented command that does not exist fails the check. | Automated |
| NFR-14 | Deployment validation in CI MUST NOT require exposing credentials. | v1 | The CI path completes without a committed or printed credential. | Automated |

#### Documentation

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| NFR-15 | All repository content MUST be in English, without exception, including configuration names, enum values, comments and examples. | v1 | An automated check plus review finds no non-English content. | Automated, Inspection |
| NFR-16 | The framework MUST deliver every document enumerated in `prd.md` section *Required Documentation*. | v1 | Each of the eighteen documentation items resolves to an artifact, or is explicitly deferred with a reason. | Inspection |
| NFR-17 | The architecture documentation MUST include at least one Mermaid diagram. | v1 | At least one Mermaid diagram renders in the architecture overview. | Inspection |
| NFR-18 | Every documented procedure step MUST have a copy-pasteable command or an explicit statement that the step is manual. | v1 | No step is described in prose without a command or a manual marker. | Inspection |
| NFR-19 | Documentation MUST be sufficient to serve as the engagement handover artifact for the secondary persona. | v1 | Quickstart, deployment, validation, operations, extension and cleanup guides exist and are cross-linked. | Inspection |

#### Extensibility, upgradeability, rollback and cleanup

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| NFR-20 | The core MUST be extensible without modification: adding a workload, a query, a connector or an extension MUST be an additive operation. | v1 | Each extension type is added additively in the reference workload example. | Command, Inspection |
| NFR-21 | Schema evolution MUST be explicit: the version identifier changes, breaking changes are listed, and migration guidance is supplied. | v1 | Any schema change satisfies all three conditions. | Inspection |
| NFR-22 | Rollback MUST be exercisable before it is needed: the procedure MUST be testable against a deployment. | v1 | The rollback procedure is executed at least once and its result recorded. | Command |
| NFR-23 | Cleanup MUST be idempotent: running it twice MUST NOT fail. | v1 | A second cleanup run completes successfully. | Command |

#### Structure and governance

| ID | Requirement | v1 scope | Acceptance criterion | Verification |
|----|-------------|----------|----------------------|--------------|
| NFR-24 | The repository MUST NOT contain empty folders or placeholder files without a defined purpose. | v1 | No directory exists solely to hold a keep-file. | Automated |
| NFR-25 | Material deviations from the proposed repository structure in `prd.md` MUST be recorded in an ADR or the implementation plan. | v1 | Each deviation is recorded. | Inspection |
| NFR-26 | The reusable core MUST be clearly separated from workload-specific and customer-specific extensions in the repository layout. | v1 | The layout makes the boundary visible without reading file contents. | Inspection |

### Constraints

Constraints are not negotiable by design choice. They bound every requirement above.

| ID | Constraint | Source | Verification |
|----|------------|--------|--------------|
| CON-01 | English only, without exception, including enum values and identifiers. | `prd.md`; `envisioning/README.md` section 8 | Automated |
| CON-02 | The core is read-only in v1. Mutating remediation is a defined contract plus an extension point, explicitly not implemented. | `envisioning/README.md` sections 2.1 and 8 | Automated |
| CON-03 | The core contract, configuration schema and evidence model are runtime-agnostic. Azure SRE Agent is the first and only concrete binding, isolated in a binding layer. | `envisioning/README.md` section 8 | Inspection |
| CON-04 | The reference workload is AKS; `examples/minimal/` stays workload-neutral. | `envisioning/README.md` section 8 | Automated |
| CON-05 | Onboarding a workload requires zero core edits. | `envisioning/README.md` section 6.2 and section 7 | Automated |
| CON-06 | Secure by default: deny-by-default tool policy, fail-closed, least privilege, managed identity, no committed secrets, placeholders only. | `prd.md` section *Security and Responsible AI Requirements* | Automated |
| CON-07 | Untrusted diagnostic content is never treated as instructions, and the evidence chain is preserved. | `source-analysis.md` sections 2.2 and 2.8 | Automated |
| CON-08 | This specification selects no technology. Infrastructure as Code, guided-experience technology, discovery mechanism, binding format and tool-policy enforcement model are ADR decisions. | `prd.md` sections *Infrastructure as Code Decision* and *Guided Deployment Experience* | Inspection |
| CON-09 | Targets are Azure only. Multi-cloud is out of scope. | `envisioning/README.md` section 2.1 | Inspection |
| CON-10 | No fixed external deadline; sequencing follows Slice 1 through Slice 5, preferring a correct foundation over speed. | `prd.md` section *Delivery Strategy*; `envisioning/README.md` section 8 | Inspection |

### Key Entities *(include if the feature involves data)*

Obligation levels below are carried forward as **proposals** from `source-analysis.md`
section 6. Per `prd.md`, the final Required, Recommended, Optional or Out-of-scope
classification is settled in the contract phase with recorded rationale and evidence
(FR-01).

- **Scope contract**: the root declaration of what the agent may observe, for how long, under which limits and exclusions, plus a canonical hash that downstream artifacts bind to. Proposed obligation: Required. Consumer-owned; never committed to the framework with real values.
- **Evidence manifest**: the execution-level index binding every observation to an execution identifier, the scope hash, a provenance classification, a timestamp, a freshness state, a data classification and a content hash. Proposed obligation: Required.
- **Tool policy**: the declaration of allowed capabilities, deny rules and execution limits. Proposed obligation: Required. Deny-by-default, deny-wins, fail-closed.
- **Agent definition**: identity, target scope, access level, action mode, model provider, consumption limit, tools and skills. Proposed obligation: Required. Its concrete format is a binding-layer concern decided by ADR.
- **Change-set**: a proposed mutation with preconditions, blast radius, rollback plan, verification method and a canonical hash. Proposed obligation: Required as contract, not implemented in v1.
- **Approval ledger**: an append-only record of human decisions, referencing the hash of the approved artifact. Proposed obligation: Required whenever a change-set exists. Agents cannot self-approve.
- **Handoff record**: an execution transfer carrying execution identity, idempotency key, turn and maximum turns, and an autonomy level defaulting to read-only. Proposed obligation: Recommended.
- **Assessment result** and **readiness result**: structured diagnostic outputs referencing evidence. Proposed obligation: Recommended. Their reference-source status and confidence enums require English renaming with recorded provenance.
- **Query catalogue**: the reviewed, integrity-verified set of diagnostic queries the agent may run. Proposed obligation: Recommended. The queries themselves are a workload extension point.
- **Connector configuration**: declared data-source connections, with credentials held externally. Proposed obligation: Required when any connector is used.
- **RBAC assignment set**: the least-privilege read-scoped grants on the declared scopes. Proposed obligation: Required.
- **Negative test suite**: the executable proof that prohibited actions are impossible. Proposed obligation: Required; enforced as a release gate.
- **Workload extension**: the consumer-supplied package carrying target resources, queries, alert definitions, connectors, limits, network access mode, scheduling and report shaping. Proposed obligation: Optional per workload, but the extension mechanism itself is Required.

## Success Criteria *(required)*

### Measurable Outcomes

- **SC-01**: Onboarding a new workload produces a diff that touches zero files inside the declared core. Measured by an automated diff check against the declared core paths.
- **SC-02**: The number of files a team edits to onboard a new workload is counted, documented in the quickstart, and matches the actual onboarding procedure. Measured by comparing the documented count to the diff.
- **SC-03**: Every manual step from clone to a validated deployment is counted and documented, and each step has a documented command or an explicit manual marker. Measured by inspection of the quickstart against the executed procedure.
- **SC-04**: 100 percent of provisioned resources and agent configuration are reproducible from version-controlled configuration. Measured by confirming each provisioned resource traces to a committed input.
- **SC-05**: Zero sanitization findings in the repository across secrets, tenant identifiers, subscription identifiers, resource identifiers, endpoints and customer names. Measured by an automated CI gate that blocks on any finding.
- **SC-06**: Negative tests covering the safety boundary are present, executable and enforced as a release gate, covering at minimum write denial, self-approval denial, change-set execution denial and untrusted-content handling. Measured by CI pass or fail.
- **SC-07**: A configuration can be authored and fully validated with no Azure subscription and no credentials. Measured by executing the local validation command in a credential-free environment.
- **SC-08**: Every conclusion produced by a deployed agent resolves to an evidence entry or carries an explicit non-observed classification. Measured by sampling one full execution and checking every conclusion.
- **SC-09**: A deployment can be completely removed, with a verification step reporting that nothing created by the framework remains, and with no pre-existing resource removed. Measured by executing cleanup and its verification.
- **SC-10**: Every requirement identifier in this specification resolves to at least one downstream ADR, task, test or artifact, or is explicitly recorded as deferred. Measured by the traceability record.
- **SC-11**: Time from zero to a validated SRE agent deployment for a new workload shows a directional reduction against the first measured adoption. **[DEFERRED]** No baseline exists; `docs/envisioning/README.md` requires instrumenting the first two real adoptions before any number is stated.

## Conformance Criteria *(required)*

### Conformance Cases

| ID | Scenario | Input | Expected Output |
|----|----------|-------|-----------------|
| CC-001 | Offline contract validation, happy path | A clone with no Azure credentials, plus `examples/minimal/` unmodified | Local validation succeeds; every schema-backed artifact validates; the command exits successfully |
| CC-002 | Structural validation failure | A configuration containing a property not defined by the schema | Validation fails, names the artifact and the property path, and states the allowed shape; no partial artifact is emitted |
| CC-003 | Semantic validation failure | A scope selection containing zero in-scope workloads | Validation fails with an actionable message; no scope contract is emitted |
| CC-004 | Guided discovery, happy path | A subscription scope with at least one eligible workload, read-only discovery permissions | A candidate list is returned, the operator selection produces a schema-valid scope contract containing exactly the selected resources plus its canonical hash, and nothing is provisioned |
| CC-005 | Non-interactive determinism | The configuration file emitted by a prior interactive run | The step completes without prompting and emits a byte-identical scope contract |
| CC-006 | Discovery permission denied for part of the scope | A scope spanning a readable and an unreadable portion | The unreadable portion is reported as an explicit access-denied state naming the missing permission; the candidate list is not silently shortened |
| CC-007 | Preview before provisioning | A validated configuration and a real subscription | Every resource to be created, changed or deleted and every role assignment to be granted is listed; no change is applied; provisioning requires explicit confirmation |
| CC-008 | Deployment idempotency | A completed deployment re-run with unchanged configuration | The command succeeds and reports no unintended changes |
| CC-009 | Least-privilege audit | A completed deployment | An audit of granted assignments returns read-scoped roles only; no role granting write, delete or action permissions on workload resources exists |
| CC-010 | Evidence completeness | One completed diagnostic execution | The evidence manifest validates, is bound to the execution identifier and the scope hash, and every entry declares provenance, timestamp, freshness, data classification and content hash |
| CC-011 | Unobserved data handling | A diagnostic execution where one configured data source is unreachable | The gap is recorded as an explicit unobserved state; no estimate, default or zero is substituted; affected conclusions are not classified as observed |
| CC-012 | Execution limit reached | An execution that exceeds the configured tool-call or duration limit | The execution halts, the partial result is recorded with an explicit incomplete state, and no value is extrapolated |
| CC-013 | Zero core edits | A clone at a released version, onboarding a second workload | The resulting diff touches only configuration, example and extension paths; zero files inside the declared core are modified |
| CC-014 | Cleanup completeness and safety | A deployment, plus one pre-existing resource inside the target scope | Cleanup removes every resource and role assignment created by the framework, the verification step reports nothing remaining, and the pre-existing resource is untouched |
| CC-015 | Cleanup idempotency | Cleanup executed a second time | The command completes successfully without error |
| CC-016 | Must NOT: write capability | A request to perform a write, delete or destructive operation against a workload resource | The operation is denied by the tool policy. Must NOT execute, and must NOT be resolvable by requesting or assuming additional permission |
| CC-017 | Must NOT: self-approval | A change-set proposal accompanied by an approval attributed to the agent identity | The approval is rejected. Must NOT record an approval whose decider is the agent |
| CC-018 | Must NOT: change-set execution in v1 | A schema-valid, approved change-set | No execution occurs. Must NOT exist any code path that applies a change-set in v1 |
| CC-019 | Must NOT: instruction injection via diagnostic content | A log line or document field containing instruction-shaped text, for example a directive to ignore prior constraints or to grant a permission | The content is treated as data. Must NOT alter agent behavior, tool selection, or policy evaluation |
| CC-020 | Must NOT: secret in an emitted artifact | Guided setup run with a connector requiring credentials | Credentials are referenced externally. Must NOT write any secret into a scope contract, configuration file, evidence manifest, audit record or log |
| CC-021 | Must NOT: unnamed capability inherited | A runtime capability that the tool policy neither allows nor explicitly denies | The capability is denied by default. Must NOT be available because it was merely unlisted |
| CC-022 | Must NOT: workload coupling in the minimal example | `examples/minimal/` inspected by an automated check | No workload-type-specific identifier is present. Must NOT reference AKS or any other specific workload type |
| CC-C01 | Version coexistence and pinning | A consumer pinned to framework version N while version N+1 is released with a schema change | The pinned consumer continues to validate and deploy using version N unchanged; version N+1 declares a changed schema version identifier and supplies migration guidance; no lockstep upgrade is required |

## Invariants

- The core never mutates a workload resource. Every capability reachable by the core is read-scoped, and any write-capable capability is a contract violation.
- A capability that is not explicitly allowed is denied. Conflicts between an allow rule and a deny rule resolve to denial, and an evaluation failure resolves to denial.
- No agent can approve its own proposal. An approval record is valid only when its decider is distinct from the agent identity.
- Missing data is recorded as missing. No estimate, default or zero is ever substituted for an unobserved value, and absence of access is never resolved by requesting or assuming permission.
- Content retrieved from a workload, a log, a document or a pull request is data. It never becomes an instruction, a tool selection or a policy change.
- Every conclusion is traceable to evidence, or is explicitly classified as derived, inferred or recommended.
- Every artifact produced by an execution is bound to the hash of the scope contract in force at that execution, so the authorized scope is always reconstructable.
- No committed artifact contains a secret, a real tenant identifier, a real subscription identifier, a real resource identifier, a real endpoint or a customer name.
- Onboarding a workload never modifies a file inside the declared core.
- The core contains no runtime-specific identifier; runtime specificity exists only inside the declared binding layer.
- A change-set may be proposed and approved, but in v1 it can never be executed, because no execution path exists.
- Cleanup removes only what the framework created.

## Compatibility and Transition *(required when Change type is not "new surface")*

N/A: purely additive new surface. This repository has no prior functional surface, no
existing consumer and no previously written state. The reference sources are read-only
inputs, not consumers: nothing in them depends on this framework, and this framework
publishes no replacement contract for them.

Forward-looking compatibility obligations for the framework's own releases are captured as
requirements rather than as a transition plan, specifically FR-29, FR-69, FR-70, NFR-21 and
conformance case CC-C01.

## Open Decisions This Specification Depends On

Each item requires an Architecture Decision Record before the dependent requirements can be
implemented. Sourced from `source-analysis.md` section 8 and `envisioning/README.md`
section 10.

| Decision | Blocks | Why it is open | Depends on |
|----------|--------|----------------|------------|
| Relationship to existing SRE agent template tooling: consume, extend or replace | FR-31, FR-32, FR-37, FR-39, Group E | `sreagent-templates` already provides recipes, lifecycle scripts, Bicep and Terraform backends, `azd` integration and a validation workflow. Building parallel deployment mechanics would duplicate it. | Nothing; decide first |
| Infrastructure as Code technology | FR-31, FR-32, FR-34, FR-35, NFR-06, NFR-11 | `prd.md` requires a weighted decision matrix. Both Bicep and Terraform backends already exist in the templates, and the reference implementation's Bicep footprint is too small to be decisive. | The template-relationship decision |
| Guided deployment experience and its technology | Group B entirely | Justified by the absence of workload discovery in both sources. `prd.md` forbids assuming the technology and lists seven candidate approaches. | The Infrastructure as Code decision |
| Workload discovery mechanism and eligibility rules | FR-10, FR-11, FR-12, FR-22 | Net-new. Candidates include resource-graph querying and subscription enumeration. Must define eligibility rules, required read-only permissions, and behavior when discovery is denied. | The guided experience decision |
| Agent binding format | FR-04, FR-31, Group D | Two incompatible agent definition shapes exist across the sources. The contract must sit above both. | The template-relationship decision |
| English renaming of the reference vocabulary | FR-03 | Required by the English-only constraint; provenance must be preserved. | Nothing |
| Obligation level of each contract area | FR-01, FR-02, Key Entities | `prd.md` requires classification with rationale and evidence. `source-analysis.md` section 6 proposes but does not settle it. | Nothing |
| Tool-policy enforcement model | FR-51, FR-52, FR-53, FR-55, FR-56 | Configuration alone is insufficient; the reference implementation enforces procedurally, not programmatically. Runtime capability identifiers are explicitly unconfirmed in the source. | Runtime capability reconciliation |
| Single source of truth for schemas | FR-05 | The reference implementation duplicates schemas across two directories, creating drift. | Nothing |
| Discovery scope breadth | FR-10, FR-11, FR-22 | [NEEDS CLARIFICATION: whether guided discovery must span multiple subscriptions or multiple tenants in v1, or may be limited to a single operator-supplied subscription scope. This changes the required permission model and the shape of the emitted scope contract.] | The discovery mechanism decision |
| Evidence retention and immutability policy | FR-44, FR-48 | `[DEFERRED: retention duration and storage location depend on the binding and on customer policy; specify during the contract phase.]` | The binding decision |
| Non-production and production environment naming convention | FR-36 | `[DEFERRED: a naming convention is an implementation-time choice that does not change the requirement that the two bindings be separable.]` | The configuration schema work |

## Traceability

### Requirements to `prd.md`

| Requirement group | `prd.md` section | Functional Outcome item |
|-------------------|------------------|-------------------------|
| Group A - Minimum SRE agent contract | *Minimum SRE Agent Contract*; *Required Documentation* item 4 | 1 |
| Group B - Guided scope definition and discovery | *Guided Deployment Experience* | 2 |
| Group C - Configuration model | *Configuration Design*; *Required Documentation* item 10 | 2 |
| Group D - Provisioning and deployment | *Infrastructure as Code Decision*; *Security and Responsible AI Requirements*; *Required Documentation* items 7, 8, 12 | 3, 4 |
| Group E - Validation | *Testing and Quality Gates*; *Required Documentation* item 13 | 5 |
| Group F - Observability and evidence | *Security and Responsible AI Requirements*; *Minimum SRE Agent Contract* | 6 |
| Group G - Safe operational controls | *Security and Responsible AI Requirements*; *Required Documentation* item 9 | 7 |
| Group H - Extensibility | *Pattern Extraction*; *Required Documentation* items 15, 17 | 8 |
| Group I - Upgrade, rollback and cleanup | *Required Documentation* item 16 | 9 |
| Group J - Traceability | *Required Documentation* item 19; *Definition of Done* | 10 |
| NFR-01 to NFR-07 | *Security and Responsible AI Requirements* | Cross-cutting |
| NFR-08 to NFR-14 | *Testing and Quality Gates* | Cross-cutting |
| NFR-15 to NFR-19 | *Required Documentation*; *Mission* | Cross-cutting |
| NFR-20 to NFR-23 | *Configuration Design*; *Required Documentation* item 16 | 8, 9 |
| NFR-24 to NFR-26 | *Proposed Repository Deliverables*; *Pattern Extraction* | Cross-cutting |
| CON-01 to CON-10 | *Mission*; *Delivery Strategy*; *Security and Responsible AI Requirements* | Cross-cutting |

### Requirements to envisioning KPIs

| Envisioning KPI | Target | Requirements | Success criteria |
|-----------------|--------|--------------|------------------|
| Core edits required to onboard a new workload | Zero | FR-60, FR-61, FR-63, CON-05 | SC-01 |
| Files a team must edit to onboard a new workload | Configuration files only, counted and documented | FR-62, FR-65, NFR-20 | SC-02 |
| Manual steps from clone to a validated deployment | Counted and documented, each with a command | FR-65, NFR-18, NFR-19 | SC-03 |
| Share of the deployment reproducible from version-controlled configuration | 100 percent | FR-14, FR-18, FR-24, FR-31, FR-32 | SC-04 |
| Time from zero to a validated deployment | Directional reduction against the first measured adoption | FR-65 | SC-11 `[DEFERRED: baseline]` |
| Sanitization findings | Zero, enforced by an automated CI gate | NFR-01, NFR-02, NFR-03, NFR-04, FR-49, CON-06 | SC-05 |
| Negative tests covering safety boundaries | Present and enforced as a release gate | FR-40, FR-52, FR-55, FR-56, FR-06 | SC-06 |

### Requirements to `source-analysis.md` evidence

| Requirement | Evidence anchor |
|-------------|-----------------|
| FR-01, FR-02 | Section 6 reusable artifact register; section 7.1 "No machine-validatable agent contract" |
| FR-03 | Section 5.1 canonical execution-state vocabulary; section 5.4 items 2 and 3 |
| FR-04, FR-37 | Section 4 agent definition format conflict; section 3.2 |
| FR-05 | Section 7.1 schema duplication |
| Group B | Section 3.5 absence of workload discovery; section 4 "Neither source provides it" |
| FR-23, FR-44 | Section 2.8 evidence and traceability; section 6.1 scope contract and evidence manifest |
| FR-33, FR-34 | Section 5.2 reader-role model; section 6.2 RBAC assignment |
| FR-40, FR-52 | Section 5.1 negative tests as a release gate; section 6.2 negative test suite |
| FR-46, FR-47 | Section 2.2 behavioural invariants; section 2.8 |
| FR-50 | Section 2.7 fixed, hash-verified query catalogue |
| FR-51, FR-53, FR-54 | Section 2.5 configuration and policy model |
| FR-55 | Section 2.2 untrusted-content rule |
| FR-56, FR-57, FR-58 | Section 2.4 change-set and approval ledger; section 6.1 |
| FR-63, FR-64 | Section 3.9 minimum viable agent; envisioning constraint on AKS |
| NFR-01 to NFR-04 | Section 5.4 exclusion list; section 6.3 sensitive-content handling |
| NFR-08 to NFR-13 | Section 3.8 what CI considers a valid recipe |
| FR-74 | Section 2.5 unconfirmed runtime tool identifiers; section 7.2 |

## Related Specs

No sibling feature or migration specification exists yet. This specification is the
requirements baseline that the following planned artifacts will trace back to:

- Minimum SRE Agent Contract - settles FR-01, FR-02 and the obligation levels proposed in Key Entities.
- Architecture overview and ADRs - settle every item in *Open Decisions This Specification Depends On*.
- Implementation plan and task decomposition - trace to the requirement identifiers defined here, per FR-71.

Upstream inputs to this specification:

- [Product requirements](../../../prd.md) - authoritative source for the Functional Outcome and all mandated sections.
- [Envisioning](../../envisioning/README.md) - vision, personas, non-goals, KPIs, constraints, risks and open items.
- [Source analysis and pattern inventory](../../architecture/source-analysis.md) - the evidence base for every requirement, including the reusable artifact register and the open decisions.

## Spec Evolution Log *(required)*

| Version | Date | Change Summary | Trigger | Author |
|---------|------|----------------|---------|--------|
| 1.0 | 2026-09-23 | Initial draft. Framework-level requirements baseline for Slice 1: 74 functional requirements across ten groups, 26 non-functional requirements, 10 constraints, 11 success criteria, 23 conformance cases, 12 invariants, and traceability to `prd.md`, the envisioning KPIs and the source analysis. Status: Draft. | new work | DevSquad specify agent |

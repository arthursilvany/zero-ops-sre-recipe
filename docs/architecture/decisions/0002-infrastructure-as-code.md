# Infrastructure as Code

**Status**: Proposed
**Date**: 2026-09-23
**Depends on**: [0001 — Upstream Template Relationship](0001-upstream-template-relationship.md)

## Context

`prd.md` requires evaluating Terraform, Bicep and ARM JSON against a defined criteria set,
producing a weighted decision matrix and an ADR, and recommending one primary
implementation. It also states explicitly that the choice must not be made on personal
preference, that ARM JSON should be treated as a deployment output or compatibility option
unless the analysis shows otherwise, and that a second implementation should only be built
with documented justification.

ADR-0001 materially narrows this decision. Because the framework **extends** the upstream
`microsoft/sre-agent` template kit rather than replacing it, the question is no longer
which technology to author from scratch. Both backends already exist upstream and were
inspected directly:

| Backend | Files | Lines | Notes |
|---|---|---|---|
| `bicep/` | `main.bicep`, `agent-core.bicep`, `agent-extensions.bicep`, `role-assignments-target.bicep`, `logic-app-bridge.bicep` | 768 lines of Bicep across 5 modules | Plus the shared assemble and apply-extras scripts |
| `terraform/` | `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf` | 632 lines | Requires `azure/azapi >= 2.0` and `hashicorp/azurerm >= 4.0` |

Two findings from inspecting the upstream kit shape this decision:

1. **The data plane is backend-agnostic and already shared.** `bin/deploy-tf.sh` reuses
   `bicep/assemble-agent.sh` for assembly, and skills, subagents, tools and prompts are
   applied through `apply-extras.sh` in both paths. Only **control-plane provisioning**
   actually differs between the two backends.
2. **Lifecycle parity is complete.** Both Bash and PowerShell entry points exist for both
   backends: `deploy.sh` / `Deploy-Agent.ps1` and `deploy-tf.sh` / `Deploy-Tf.ps1`.
3. **Upstream already declares a primary.** `azure.yaml` sets `infra.provider: bicep` and
   documents `azd up` as new-agent plus assemble plus **Bicep** deploy plus apply-extras.
   There is no equivalent Terraform-first lifecycle declaration.

So the real question is: **which existing backend does this framework treat as primary**,
and what happens to the other.

Deployment context matters and is established in `docs/envisioning/README.md`: the primary
persona is a platform or SRE engineer at a customer organization, with consultants
deploying on the customer's behalf during time-boxed engagements. The provisioned footprint
is small and read-only in v1 — the agent resource, a managed identity, reader-role
assignments on target scopes, and connector wiring. FR-10 to FR-23 require a guided
workload discovery and selection step before deployment.

## Priorities and Requirements (ordered)

The criteria are those `prd.md` mandates. Weights reflect this framework's context: a small,
read-only footprint deployed repeatedly into *other organizations'* subscriptions, often by
someone who will hand the result over and leave.

1. **State management** (weight 5) — anything requiring durable state infrastructure in a
   customer subscription adds a prerequisite, a security surface and a cleanup obligation
   before the first deployment can happen.
2. **Guided deployment experience** (weight 5) — FR-10 to FR-23 are headline capability.
3. **Azure service coverage** (weight 5) — the agent resource type is recent; the backend
   must support it without waiting on provider releases.
4. **Reusability, modularity, parameter validation, maintainability, testing support,
   deployment experience, CI/CD integration, upgrade and rollback, customer-specific
   extensions** (weight 4 each) — core framework qualities.
5. **Readability, global adoption, security scanning, drift considerations** (weight 3
   each) — important, but secondary to the above in this context.

## Weighted Decision Matrix

Scores are 1 to 5. Each option has a raw score column and a weighted column (weight
multiplied by raw score). Maximum possible weighted total is 315.

| Criterion | Weight | Bicep raw | Bicep weighted | Terraform raw | Terraform weighted | ARM raw | ARM weighted |
|---|---|---|---|---|---|---|---|
| Azure service coverage | 5 | 5 | 25 | 4 | 20 | 5 | 25 |
| Reusability | 4 | 4 | 16 | 5 | 20 | 2 | 8 |
| Modularity | 4 | 4 | 16 | 5 | 20 | 2 | 8 |
| Parameter validation | 4 | 4 | 16 | 4 | 16 | 3 | 12 |
| Maintainability | 4 | 4 | 16 | 4 | 16 | 1 | 4 |
| Readability | 3 | 5 | 15 | 4 | 12 | 1 | 3 |
| Testing support | 4 | 3 | 12 | 5 | 20 | 2 | 8 |
| Deployment experience | 4 | 5 | 20 | 4 | 16 | 4 | 16 |
| CI/CD integration | 4 | 4 | 16 | 5 | 20 | 3 | 12 |
| State management | 5 | 5 | 25 | 2 | 10 | 5 | 25 |
| Upgrade and rollback | 4 | 4 | 16 | 4 | 16 | 3 | 12 |
| Global adoption | 3 | 3 | 9 | 5 | 15 | 2 | 6 |
| Customer-specific extensions | 4 | 4 | 16 | 5 | 20 | 2 | 8 |
| Security scanning | 3 | 4 | 12 | 5 | 15 | 3 | 9 |
| Drift considerations | 3 | 2 | 6 | 5 | 15 | 2 | 6 |
| Guided deployment experience | 5 | 5 | 25 | 3 | 15 | 5 | 25 |
| **Total** | **63** | | **261** | | **266** | | **187** |
| **Percentage of maximum** | | | **82.9%** | | **84.4%** | | **59.4%** |

**The matrix does not produce a winner between Bicep and Terraform.** They are 5 points
apart out of 315, a 1.6% gap, which is well inside the noise of subjective scoring. Treating
that as a decision would be false precision. ARM JSON is decisively last and is eliminated.

The matrix is still useful, because it shows *where* each option wins, and those differences
are real rather than marginal:

- **Terraform wins** on drift detection, testing support, security scanning tooling,
  modularity, reusability and ecosystem reach.
- **Bicep wins** on state management, guided deployment experience, readability, immediate
  coverage of recent Azure resource types, and deployment simplicity.

## Options Considered

### Option 1: Bicep primary

**Evaluation against priorities**:

- **State management**: Meets fully. Azure Resource Manager is the state. There is nothing
  to provision, secure, back up or clean up before the first deployment, and nothing left
  behind in the customer's subscription afterwards.
- **Guided deployment experience**: Meets fully. An ARM-based guided experience, including a
  portal deployment surface, is available because Bicep compiles to ARM JSON. Note that the
  upstream kit does **not** currently ship a `createUiDefinition.json`; the capability is
  available but unexercised.
- **Azure service coverage**: Meets fully. Recent resource types are addressable natively
  without waiting for a provider release.
- **Testing and drift**: **Partially meets.** What-if provides a preview, but there is no
  native drift detection and no first-class unit-test framework.

### Option 2: Terraform primary

**Evaluation against priorities**:

- **State management**: **Fails for this context.** Every customer environment needs a
  remote state backend provisioned and secured before the first deployment. State contains
  resource metadata, creating a data-handling obligation inside the customer's tenant, and
  an orphaned state backend is a cleanup failure mode. For a framework whose headline metric
  is manual steps from clone to validated deployment, this is a structural cost paid on
  every adoption.
- **Guided deployment experience**: Partially meets. A CLI or workflow-driven experience is
  achievable; a portal-based one is not.
- **Azure service coverage**: Partially meets. Recent resource types require `azapi`, which
  upstream already depends on. This works, but it is an extra abstraction layer over the
  resource contract.
- **Testing, drift, security scanning**: Meets fully, and better than any alternative. These
  are genuine advantages.

### Option 3: ARM JSON primary

**Evaluation against priorities**:

- Scores 59.4%, far behind both alternatives, losing decisively on maintainability,
  readability, modularity and reusability. Hand-authoring ARM JSON is not justified by any
  finding in the source analysis.
- `prd.md` already anticipates this outcome and directs that ARM JSON be treated as a
  deployment output or compatibility option unless the analysis shows otherwise. It does
  not.

## Decision

**Bicep is the primary Infrastructure as Code implementation. Terraform remains a supported
alternative, maintained upstream. ARM JSON is a compiled output and compatibility surface
only, never hand-authored.**

Because the weighted matrix is effectively tied, the decision is made on the two criteria
carrying the highest weight, where the gap between the options is largest and least
subjective:

**State management is the deciding factor.** This framework is deployed repeatedly into
other organizations' subscriptions, frequently by someone who will hand over and leave.
Terraform requires a remote state backend to exist, be secured, and later be cleaned up in
every one of those environments. That is a prerequisite before the first deployment, a
data-handling obligation inside the customer's tenant, and a documented failure mode at
cleanup. Bicep has none of it. This directly serves SC-03, manual steps from clone to a
validated deployment, and FR-66 to FR-70, safe removal and rollback.

**The guided deployment experience is the confirming factor.** FR-10 to FR-23 require guided
workload discovery and selection, and the source analysis established that no such
capability exists in either reference source. Keeping a portal-based deployment surface
available — which Bicep provides through ARM and Terraform does not — preserves an option
the framework is very likely to want, without committing to it here. The technology of the
guided experience itself remains open and is decided in its own ADR, per `prd.md`.

**Upstream's own declaration corroborates this.** `azure.yaml` sets `infra.provider: bicep`
and defines the `azd` lifecycle around the Bicep path. Choosing Bicep as primary aligns this
framework with the path upstream already treats as canonical, which lowers the cost of the
version-pinning and upgrade procedure defined in ADR-0001.

**Terraform is retained, not rejected.** `prd.md` warns against maintaining equivalent
implementations in multiple IaC languages without a documented reason. The documented reason
here is specific and strong: the Terraform backend **already exists and is maintained
upstream**, not by this framework. Under ADR-0001 it costs this project nothing to keep, and
dropping it would remove a working option from consumers who have an existing Terraform
practice — a real constraint in enterprise environments. Its genuine advantages in drift
detection and testing are acknowledged rather than dismissed.

The asymmetry is deliberate and must stay explicit: **this framework's own quality gates,
examples and documentation target the Bicep path.** Terraform is supported by upstream, and
this repository verifies compatibility rather than owning the implementation.

### Consequences

- Quality gates in this repository validate Bicep compilation and run what-if previews.
  Terraform validation is a compatibility check, not a primary gate.
- The reference example and the quickstart use the Bicep path.
- The absence of native drift detection is an accepted, recorded limitation. Anything
  needing drift detection must be solved outside the deployment backend, for example through
  the agent's own read-only diagnostics, which is a natural fit for this framework.
- Testing support is weaker than Terraform's. Deployment validation therefore leans on
  what-if previews plus the framework's own negative tests rather than on backend-native
  testing.
- Bicep security scanning must be explicitly selected and wired into CI (NFR-08 to NFR-14).
  It is not inherited.
- ARM JSON appears only as compiled output. Any hand-authored ARM JSON in this repository is
  a defect.
- Terraform remains available through the upstream `deploy-tf.sh` and `Deploy-Tf.ps1` entry
  points. Consumers choosing it accept the state-management obligations described above,
  which must be documented rather than hidden.

## Implementation Notes

- Do not re-author the upstream Bicep modules. Compose and parameterize them, consistent
  with ADR-0001.
- Pin the upstream version, and cover the Bicep path with a compatibility test as part of
  the upgrade procedure.
- Record the state-management trade-off in the operations documentation so that a consumer
  choosing Terraform understands the prerequisite and the cleanup obligation before
  starting, satisfying `prd.md`'s requirement that the guided experience never hides the
  underlying deployment model.
- Revisit this decision if drift detection becomes a v1 requirement, or if a future
  requirement makes multi-cloud targets in scope. Both are currently non-goals in
  `docs/envisioning/README.md`.

## References

- `prd.md` — section *Infrastructure as Code Decision*
- [ADR-0001 — Upstream Template Relationship](0001-upstream-template-relationship.md)
- `docs/architecture/source-analysis.md` — sections 2.6, 3.2, 3.5, 8
- `docs/features/sre-agent-recipe-framework/spec.md` — FR-10 to FR-23, FR-31 to FR-38,
  FR-66 to FR-70, NFR-08 to NFR-14, SC-03
- `docs/envisioning/README.md` — sections 2.1, 8
- Upstream backends: `sreagent-templates/bicep/` and `sreagent-templates/terraform/` in
  <https://github.com/microsoft/sre-agent>

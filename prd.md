# Zero Ops SRE Agent Recipe - Product Requirements

## Mission

Build a reusable, production-oriented "Zero Ops SRE Agent Recipe" in this repository:

<https://github.com/arthursilvany/zero-ops-sre-recipe.git>

The repository must become a reference framework that teams can use to create and deploy new SRE agents consistently across customer workloads.

The primary business goal is to reduce the time, ambiguity, and duplicated effort required to implement Zero Ops capabilities for new workloads.

All repository content, source code, documentation, diagrams, configuration names, comments, examples, tests, commit-ready artifacts, and user-facing text must be written in English.

## Operating Mode

Use the DevSquad delivery workflow.

Follow this artifact sequence:

1. Envisioning
2. Repository and source analysis
3. Requirements and feature specification
4. Architecture decisions
5. Thin-slice implementation plan
6. Incremental implementation
7. Testing, security review, and documentation
8. Final validation and traceability report

Do not jump directly into implementation.

Treat this as a production-quality reusable framework, not as a throwaway prototype.

## Target Repository

Implement all new artifacts only in the currently opened target repository:

`<workspace-root>`

Remote repository:

<https://github.com/arthursilvany/zero-ops-sre-recipe.git>

If the local target path differs from the actual workspace root, use the current Git workspace as the target repository.

## Authoritative Reference Sources

Analyze the following local sources before proposing the design:

1. Existing implementation:
   `<reference-implementation-checkout>`

2. SRE Agent guide:
   `<sre-agent-guide>`

The guide may be written in Portuguese, but every artifact produced in the target repository must be in English.

Treat both source locations as read-only references.

Do not modify, rename, move, format, or commit files in either source repository.

## Mandatory Preflight

Before planning or writing implementation files:

1. Verify whether both reference sources are accessible.
2. Verify whether the target repository is the current writable Git workspace.
3. Inspect the target repository state and identify any existing files.
4. Report which sources were successfully accessed.
5. Identify any missing, inaccessible, malformed, or ambiguous inputs.
6. Check whether the source repositories contain secrets, credentials, customer identifiers, subscription IDs, tenant IDs, private endpoints, personal data, or environment-specific values.

If either reference source is inaccessible:

- Do not invent its content.
- Do not claim to have analyzed it.
- Stop source-dependent design work.
- Clearly state which path is inaccessible.
- Provide precise instructions for making the source available, such as adding the folder to a multi-root VS Code workspace or copying an approved sanitized snapshot into a temporary reference directory.
- Continue only with repository initialization and a documented list of blocked analysis tasks.

## Source Analysis

Create a structured inventory of the existing implementation and guide.

For the reference implementation, identify only what is actually present, including:

- Architecture and major components
- SRE agent responsibilities
- Entry points
- Agent instructions and prompts
- Tools and integrations
- Infrastructure resources
- Deployment mechanism
- Configuration model
- Identity and access model
- Secrets handling
- Observability
- Logs, metrics, traces, alerts, and dashboards
- Incident or remediation workflows
- Human approval controls
- Safety constraints
- Tests and validation
- CI/CD automation
- Documentation
- Environment-specific assumptions
- Customer-specific coupling
- Reusable patterns
- Gaps and technical debt

For the SRE Agent guide, identify:

- Recommended SRE agent structure
- Required and optional artifacts
- Examples and patterns
- Preconditions
- Deployment guidance
- Security guidance
- Operational guidance
- Validation guidance
- Any inconsistencies between the guide and the existing implementation

Do not copy customer-specific content into the target repository.

Do not expose secrets or sensitive values in analysis documents. Replace sensitive examples with clearly named placeholders.

## Pattern Extraction

Separate everything found in the sources into four categories:

1. Reusable core
2. Azure-specific reusable implementation
3. Workload-specific extension points
4. Customer-specific or environment-specific content that must not be included

For each reusable artifact, document:

- Purpose
- Whether it is mandatory or optional
- Inputs
- Outputs
- Dependencies
- Extension points
- Security considerations
- Validation method
- Source evidence, including the relevant source file path

The resulting repository must be a generalized recipe. It must not be a direct clone or rename of the reference implementation.

## Functional Outcome

The framework must enable a team to:

1. Understand the minimum contract of an SRE agent.
2. Configure a new agent for a workload.
3. Provision required Azure resources through Infrastructure as Code.
4. Deploy the agent in a repeatable way.
5. Validate the deployment.
6. Observe agent behavior.
7. apply safe operational controls.
8. Extend the framework without changing its reusable core.
9. Remove or roll back deployed resources safely.
10. Trace implementation decisions back to specifications and ADRs.

## Minimum SRE Agent Contract

Derive the final contract from the references, but evaluate at least the following candidate areas:

- Agent identity and metadata
- Workload context
- Supported operational scenarios
- Instructions and behavioral boundaries
- Tool definitions
- Authentication and authorization
- Least-privilege role assignments
- Data-source connections
- Observability
- Health checks
- Incident detection
- Diagnostic collection
- Remediation actions
- Human approval gates
- Audit trail
- Error handling
- Retry and timeout behavior
- Configuration schema
- Deployment assets
- Validation tests
- Runbooks
- Security guidance
- Operational ownership
- Versioning and upgrade guidance
- Rollback and cleanup guidance

Do not automatically treat every candidate area as mandatory.

Classify each item as:

- Required
- Recommended
- Optional
- Out of scope

Record the rationale and evidence for the classification.

## Infrastructure as Code Decision

Evaluate these implementation alternatives:

1. Terraform
2. Bicep
3. ARM JSON templates

Do not select a technology based only on personal preference.

Evaluate each option against:

- Azure service coverage required by the reference implementation
- Reusability
- Modularity
- Parameter validation
- Maintainability
- Readability
- Testing support
- Deployment experience
- CI/CD integration
- State management
- Upgrade and rollback experience
- Global adoption
- Ability to support customer-specific extensions
- Security scanning
- Drift considerations
- Ability to provide a guided deployment experience

Create a weighted decision matrix and an Architecture Decision Record.

Recommend one primary implementation.

Only implement a second IaC option if the source analysis or an explicit requirement provides a strong justification. Avoid maintaining equivalent implementations in multiple IaC languages without a documented reason.

Treat ARM JSON as a deployment output or compatibility option unless the decision analysis shows that hand-authored ARM JSON is the best primary source.

## Guided Deployment Experience

If a wizard or guided deployment experience is justified, do not assume its technology.

Evaluate suitable approaches based on the selected IaC implementation, such as:

- Azure deployment experience
- Portal-based deployment UI
- CLI-based interactive bootstrap
- PowerShell-based guided deployment
- Bash-based guided deployment
- GitHub Actions workflow dispatch
- Configuration file generator

Document the selected experience in an ADR.

The guided experience must:

- Collect only required inputs
- Explain each input in plain English
- Validate input formats
- Avoid collecting secrets in plain text
- Support non-interactive automation
- Produce or consume a version-controlled configuration file where appropriate
- Provide a preview or validation step before deployment
- Display actionable deployment errors
- Document rollback and cleanup
- Avoid hiding the underlying IaC deployment model

## Proposed Repository Deliverables

After source analysis, validate and refine the following proposed structure:

.github/
  copilot-instructions.md
  workflows/
docs/
  architecture/
  decisions/
  envisioning/
  features/
  getting-started/
  security/
  operations/
  examples/
src/
  agent/
infra/
  modules/
  environments/
config/
  schemas/
  examples/
scripts/
tests/
  unit/
  integration/
  validation/
examples/
  minimal/
  reference-workload/
README.md
CONTRIBUTING.md
SECURITY.md
LICENSE
CHANGELOG.md
CODE_OF_CONDUCT.md
.gitignore
.markdownlint.yaml

Do not create empty folders or placeholder files without a defined purpose.

Adapt the structure to actual findings and document material deviations in an ADR or implementation plan.

## Required Documentation

At minimum, produce:

1. Project vision and problem statement
2. Scope and non-goals
3. Source analysis and pattern inventory
4. Minimum SRE Agent Contract
5. Architecture overview
6. At least one architecture diagram using Mermaid
7. IaC decision ADR
8. Guided deployment decision ADR, if applicable
9. Security model
10. Configuration reference
11. Quickstart
12. Deployment guide
13. Validation guide
14. Operations and troubleshooting guide
15. Extension guide
16. Upgrade, rollback, and cleanup guidance
17. Example implementation
18. Known limitations
19. Traceability between requirements, ADRs, tasks, tests, and implemented artifacts

## Security and Responsible AI Requirements

Apply secure-by-default principles.

At minimum:

- Use placeholders for tenant IDs, subscription IDs, resource IDs, endpoints, and customer names.
- Never commit secrets, tokens, credentials, certificates, or sensitive source values.
- Use managed identities where supported by the selected architecture.
- Apply least privilege.
- Separate read-only diagnostic actions from mutating remediation actions.
- Require explicit approval for destructive, high-impact, or customer-facing remediations unless the reference architecture documents a safer control.
- Document agent boundaries and prohibited actions.
- Validate and constrain all user-controlled configuration.
- Avoid logging secrets or sensitive workload data.
- Include threat considerations for prompt injection, unsafe tool invocation, excessive permissions, data leakage, and untrusted diagnostic content.
- Preserve an auditable record of agent actions where supported by the architecture.
- Add secret scanning and IaC security validation to CI when practical.

If the sources conflict with these principles, document the conflict and propose a safer design rather than silently reproducing it.

## Configuration Design

Define a versioned, machine-validatable configuration contract.

The configuration must distinguish:

- Global framework defaults
- Environment settings
- Workload-specific settings
- Tool and integration settings
- Observability settings
- Remediation permissions
- Approval policies
- Sensitive values that must be referenced externally rather than stored

Provide:

- A schema
- A minimal valid example
- A more complete reference example
- Validation behavior
- Backward-compatibility or migration guidance

## Testing and Quality Gates

Define and implement appropriate validation for the selected technologies.

At minimum, include checks for:

- Formatting
- Linting
- Documentation links
- Configuration schema validation
- IaC syntax or compilation
- Static security analysis
- Unit tests for reusable logic
- Deployment validation that does not require exposing credentials
- Example configuration validation
- Detection of committed secrets
- Consistency between documentation and implemented commands

Tests that require an Azure subscription must be clearly separated from local tests.

Do not claim that a live deployment passed unless it was actually executed successfully and evidence is available.

## Delivery Strategy

Break the work into thin, reviewable slices.

Use this initial sequencing unless the analysis supports a better sequence:

Slice 1:
- DevSquad initialization
- Preflight
- Envisioning
- Source inventory
- Initial requirements
- Gap and risk report

Slice 2:
- Minimum SRE Agent Contract
- Architecture proposal
- IaC evaluation matrix
- ADRs
- Repository structure proposal

Slice 3:
- Minimal configuration schema
- Reusable IaC foundation
- Minimal deployable example
- Local validation

Slice 4:
- Guided deployment experience, if approved
- CI quality gates
- Security validation
- Documentation

Slice 5:
- Reference workload example
- Integration validation
- Operations guidance
- Final traceability review

For medium-impact or high-impact decisions, stop at the relevant review checkpoint and present:

- Decision required
- Options
- Recommendation
- Trade-offs
- Risks
- Files that would be created or changed

Do not make irreversible architectural choices silently.

## Initial Response Required

Before modifying implementation files, respond with:

1. Workspace and source-access status
2. Summary of the target repository state
3. Initial understanding of the mission
4. Assumptions
5. Missing information or blockers
6. Proposed source-analysis approach
7. Proposed first thin slice
8. Expected artifacts from that slice
9. Decisions that will require human review

Then initialize the DevSquad project artifacts if needed and begin only the first approved, non-blocked slice.

## Definition of Done

The project is complete only when:

- The reusable core is clearly separated from workload and customer-specific extensions.
- The minimum SRE agent contract is documented and machine-validatable where applicable.
- The primary IaC technology is justified through an ADR and decision matrix.
- A minimal example can be configured and validated using documented commands.
- Security, identity, observability, approval controls, rollback, and cleanup are addressed.
- CI validates documentation, configuration, tests, and IaC.
- No secrets or customer-specific identifiers are present.
- Documentation is entirely in English.
- Architectural decisions are traceable.
- The implementation aligns with the inspected source evidence.
- Any deviations from the reference implementation are explicit and justified.
- Known limitations and unvalidated assumptions are documented.

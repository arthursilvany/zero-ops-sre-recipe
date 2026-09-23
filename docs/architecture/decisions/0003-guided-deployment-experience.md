# Guided Deployment Experience

**Status**: Proposed
**Date**: 2026-09-23
**Depends on**: [0001 — Upstream Template Relationship](0001-upstream-template-relationship.md),
[0002 — Infrastructure as Code](0002-infrastructure-as-code.md)

## Context

`prd.md` requires a guided deployment experience and explicitly forbids assuming its
technology. It lists candidates — an Azure deployment experience, a portal UI, a CLI
bootstrap, PowerShell, Bash, a GitHub Actions `workflow_dispatch`, a configuration
generator — and requires that the choice be justified, that the guided path never hide the
underlying deployment model, and that anything the wizard produces remain inspectable and
reproducible without it.

FR-10 to FR-23 extend this beyond parameter collection into **workload discovery and
selection**: the operator should be able to discover candidate workloads in scope, select
them, and have the selection emitted as a validated scope contract before any deployment
occurs.

Three findings from the source analysis constrain this decision.

**An interactive CLI wizard already exists upstream.** `New-Agent.ps1` presents a numbered
recipe picker (`Pick a recipe [1-N]`) and prompts for parameters, with secure-string
handling for secrets. `Add-Recipe.ps1` follows the same pattern. Critically, it already
implements the escape hatch `prd.md` demands: `--non-interactive` combined with repeated
`--set key=value` arguments produces the identical artifact without any prompting. The
`azure.yaml` preprovision hook drives exactly that non-interactive path.

**Neither reference source performs workload discovery.** Upstream requires the operator to
hand-supply `targetRGs` as a string. The reference customer suite defines scope statically
in a committed `config/scope-contracts/*.json` file. Discovery is net-new work in both
directions — this is the genuine gap.

**The reference suite already proves the output format.** It emits scope as JSON validated
against JSON Schema 2020-12 contracts, which is precisely the "inspectable and reproducible
artifact" `prd.md` requires the wizard to produce.

## Priorities and Requirements (ordered)

1. **The artifact must be the product, not the wizard.** The guided path must emit a
   committed, schema-validated file; deployment must consume that file and never the
   interactive session. Non-negotiable per `prd.md`.
2. **Full non-interactive parity.** Every interactive choice must have a scriptable
   equivalent, for CI, for repeat deployments and for air-gapped review workflows.
3. **Discovery must be read-only and least-privilege.** It runs before any deployment and
   before any role assignment, so it must work with the operator's existing read access and
   must not mutate anything. This aligns with the v1 read-only posture.
4. **The underlying deployment model must stay visible.** The operator must be able to see
   what will be deployed, and to run the same deployment without the wizard.
5. **Low adoption friction.** SC-03 measures manual steps from clone to validated
   deployment. Introducing a new runtime, a hosted service or a portal publishing pipeline
   works against this.
6. **Cross-platform.** Consultants and platform engineers run Windows, macOS and Linux.

## Options Considered

### Option 1: Extend the existing upstream CLI wizard, adding a discovery step

Keep `new-agent` as the entry point and insert a workload discovery and selection stage that
queries Azure read-only, presents candidates, and emits a schema-validated scope contract
consumed by the deployment.

- **Artifact is the product**: Meets fully. The scope contract is written to disk, validated
  against a JSON Schema, and committed. Deployment reads the file.
- **Non-interactive parity**: Meets fully, and inherits it — the `--non-interactive` plus
  `--set` mechanism already exists and is already exercised by `azure.yaml`.
- **Read-only discovery**: Meets fully. Azure Resource Graph queries require only reader
  access and mutate nothing.
- **Deployment model visible**: Meets fully. The emitted contract plus the what-if preview
  from ADR-0002 show exactly what will happen.
- **Adoption friction**: Meets fully. No new runtime; the prerequisites are already
  installed for the deployment itself.
- **Cross-platform**: Meets fully, given the existing Bash and PowerShell parity.
- **Cost**: Only the discovery stage and the scope-contract schema are new. The prompting,
  secret handling and non-interactive plumbing are inherited.

### Option 2: Portal-based experience via `createUiDefinition.json`

- **Artifact is the product**: **Fails.** A portal deployment collects parameters and
  deploys directly. Producing a committed, reviewable artifact is not the native flow, and
  reproducing a deployment means re-entering the form.
- **Non-interactive parity**: Fails. There is no scriptable equivalent of the form.
- **Deployment model visible**: Partially meets. This is precisely the "hides the underlying
  deployment model" risk `prd.md` warns about.
- **Adoption friction**: Adds a publishing and hosting concern. Upstream ships no
  `createUiDefinition.json`, so this is entirely net-new and must be maintained in lockstep
  with the pinned upstream templates.
- **Note**: ADR-0002 deliberately preserves this as a *future* option. Rejecting it as the
  v1 mechanism does not foreclose it.

### Option 3: GitHub Actions `workflow_dispatch`

- **Artifact is the product**: Partially meets. Inputs are captured in run logs rather than
  in a committed artifact, unless it is built to open a pull request — at which point it is
  Option 1 wrapped in CI.
- **Discovery**: Fails as a guided experience. `workflow_dispatch` inputs are static form
  fields; they cannot present dynamically discovered workloads for selection.
- **Adoption friction**: Requires GitHub, a configured OIDC federation and repository write
  access before the first deployment. Excludes Azure DevOps shops and local evaluation.
- **Still valuable**: as an *execution* surface for an already-committed scope contract.

### Option 4: Standalone application, web or terminal UI

- **Artifact is the product**: Could meet.
- **Adoption friction**: **Fails.** Introduces a new runtime, a distribution mechanism, a
  security review surface and a maintenance burden entirely disproportionate to a
  selection step, working directly against SC-03.
- Rejected as unjustified by any finding in the source analysis.

## Decision

**The guided deployment experience is a CLI wizard that extends the existing upstream
`new-agent` interactive pattern, adding a read-only workload discovery and selection stage
whose output is a schema-validated scope contract file.**

Concretely:

1. **Discovery** queries Azure read-only, via Azure Resource Graph, for candidate workloads
   within the subscriptions the operator can already see.
2. **Selection** presents candidates interactively, reusing the numbered-picker pattern
   already established by `New-Agent.ps1`.
3. **Emission** writes a scope contract as JSON and validates it against a JSON Schema
   2020-12 contract in this repository, adopting the reference suite's proven pattern.
4. **Deployment** consumes the committed scope contract. It never consumes an interactive
   session.

**Rationale.** This option is the only one that satisfies the two non-negotiable priorities
simultaneously. The artifact is genuinely the product, and non-interactive parity is
inherited rather than rebuilt. It is also the lowest-cost option by a wide margin: under
ADR-0001 the framework extends upstream, and upstream has already solved prompting, secret
handling and the `--set` escape hatch. The only new work is the part that is genuinely
missing from both sources — discovery, and the schema that makes its output trustworthy.

Rejecting the portal experience is a judgement about **v1 sequencing, not about value**. The
portal option conflicts with the reproducible-artifact requirement as a primary mechanism,
and ADR-0002 keeps it technically available for later as a thin front end that emits the
same scope contract.

### Consequences

- A scope contract JSON Schema must be authored in this repository. It becomes a first-class
  contract with the same status as the agent contract, and the wizard's output is invalid
  until it validates.
- Discovery requires reader access at the discovery scope. This must be stated as an
  explicit prerequisite, and the wizard must fail closed with an actionable message when the
  operator lacks it, rather than silently returning an empty candidate list.
- The breadth of discovery — single subscription versus multi-subscription or multi-tenant —
  remains open and is flagged as `[NEEDS CLARIFICATION]` in the spec. The schema must be
  designed so that widening breadth later is an additive change.
- Interactive selection is not usable in CI. Full `--set` parity is therefore a hard
  requirement of the implementation and must be covered by tests, not documentation alone.
- The wizard must never write secrets into the scope contract. Secure-string prompting
  already exists upstream and must be preserved; secret references belong in the deployment
  parameters, not in the committed artifact.
- Discovery results are a point-in-time snapshot. The scope contract must record when and
  against what it was generated, so that drift between selection and deployment is
  detectable — partially compensating for the drift-detection limitation accepted in
  ADR-0002.
- `workflow_dispatch` is retained as a possible *execution* surface for an already-committed
  scope contract. That is complementary and is not decided here.

## Implementation Notes

- Reuse, do not fork, the upstream prompting helpers. Consistent with ADR-0001.
- Keep discovery and selection in separate stages so that discovery output can be reviewed,
  diffed and fed back in without re-running queries.
- Mirror the reference suite's fail-closed posture: an unrecognized or unresolvable workload
  is excluded and reported, never silently included.
- Cover the wizard with negative tests — missing permissions, empty results, invalid
  selection, schema-invalid output — consistent with the negative-testing pattern adopted
  from the reference suite.

## References

- `prd.md` — section *Guided Deployment Experience*
- [ADR-0001 — Upstream Template Relationship](0001-upstream-template-relationship.md)
- [ADR-0002 — Infrastructure as Code](0002-infrastructure-as-code.md)
- `docs/architecture/source-analysis.md` — sections 3.5, 5, 7, 8
- `docs/features/sre-agent-recipe-framework/spec.md` — FR-10 to FR-23, FR-24 to FR-30,
  FR-51 to FR-59, SC-03
- `docs/envisioning/README.md` — adoption journey, phase 2
- Upstream prompting pattern: `sreagent-templates/bin/ps/New-Agent.ps1` and
  `sreagent-templates/azure.yaml` in <https://github.com/microsoft/sre-agent>

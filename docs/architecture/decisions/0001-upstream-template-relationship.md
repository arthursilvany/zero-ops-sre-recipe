# Upstream Template Relationship

**Status**: Accepted
**Date**: 2026-09-23
**Accepted**: 2026-09-23

## Context

`docs/architecture/source-analysis.md` established that the second reference source is not
merely a guide. `sreagent-templates/`, inside the repository cloned at `C:\dev\sre-agent`,
is already a working recipe framework. It provides:

- `recipes/`, including a `minimal` recipe with `agent.json`, `connectors.json`,
  `expected-config.json` and a README contract.
- `bin/` lifecycle scripts in Bash and PowerShell: `new-agent.sh` / `New-Agent.ps1`,
  `deploy.sh` with `--dry-run`, `verify-agent.sh` / `Verify-Agent.ps1`.
- Two deployment backends, `bicep/` and `terraform/`, plus `azure.yaml` for `azd`.
- `tests/` with dry-run and end-to-end tests.
- `.github/workflows/validate-templates.yml`, an executable definition of a valid recipe.
- `VERSION` and `CHANGELOG.md`.

Provenance was verified: the local clone carries a remote `upstream` pointing at
`https://github.com/microsoft/sre-agent.git`, its `LICENSE` is MIT with
`Copyright (c) Microsoft Corporation`, the local `sreagent-templates/VERSION` reads `1.0.0`
and the local head is dated 2026-09-01. This is the official Microsoft template kit, under
the same licence as this repository.

This overlaps directly with parts of the deliverable described in `prd.md`. The source
analysis recorded the resulting duplication risk as high impact and high likelihood, and
recorded this as the first open decision, ahead of the Infrastructure as Code decision —
because the upstream kit already ships both Bicep and Terraform backends, which materially
changes that evaluation.

Deciding this wrongly is expensive in both directions. Reimplementing deployment mechanics
would contradict the primary business goal of `prd.md`, which is to reduce duplicated
effort. Blindly depending on an upstream that has no formal schemas and a partially
specified least-privilege model would import the very gaps this framework exists to close.

The source analysis also established what each source uniquely contributes:

- The upstream kit contributes **deployment mechanics and a validation harness**, which the
  single-customer implementation lacks almost entirely (its whole Infrastructure as Code
  surface is two files assigning RBAC).
- The single-customer implementation contributes **governance, evidence and safety
  semantics**: a deny-by-default and fail-closed tool policy, seven JSON Schema 2020-12
  contracts, an evidence manifest with classification and hashing, a hash-verified query
  catalogue, and negative tests as a release gate. The upstream kit has **no formal JSON
  Schema at all** and its least-privilege model is only partially specified.

Neither source provides workload discovery or selection. That remains net-new regardless of
this decision.

## Priorities and Requirements (ordered)

1. **Do not duplicate existing capability** — `prd.md` states the primary business goal as
   reducing time, ambiguity and duplicated effort. Rebuilding generate, dry-run, deploy and
   verify mechanics that already exist under a compatible licence directly contradicts it.
2. **Preserve and strengthen the safety differentiator** — the reusable core's value is the
   deny-by-default posture and the chain of evidence (FR-51 to FR-59, NFR-01 to NFR-07,
   invariants). Any option that dilutes this defeats the purpose of the framework.
3. **Control over the security posture** — the framework must be able to enforce
   secure-by-default behaviour, including read-only guarantees, even where the upstream is
   silent or more permissive. `SECURITY.md` and CON-06 make this non-negotiable.
4. **Bounded maintenance and dependency risk** — the upstream is versioned (`VERSION`,
   `CHANGELOG.md`) but is a preview-era artifact; the minimal recipe pins
   `upgradeChannel: "Preview"` and a finite region list. The source analysis flagged guide
   content as likely to age. Consumers must not be broken by upstream drift.
5. **Zero core edits to onboard a workload** — the headline KPI from envisioning. Whatever
   the relationship, onboarding must not require editing either the recipe core or the
   upstream kit.
6. **Support for customer-specific extensions** — `prd.md` requires extension points that
   survive an upgrade of the core.
7. **Licence and visibility compatibility** — this repository is MIT with
   `Copyright (c) Microsoft Corporation` and is expected to become public. Any dependency
   must be compatible with that.

## Options Considered

### Option 1: Consume

Treat `microsoft/sre-agent`'s `sreagent-templates` as an external dependency. This
repository ships only the governance layer — contract schemas, tool policy, evidence model,
guided workload discovery, negative tests — and documents how to combine it with the
upstream kit, which the operator obtains separately at a pinned version.

**Evaluation against priorities**:

- **Do not duplicate**: Meets fully. Nothing in the deployment path is reimplemented.
- **Preserve the safety differentiator**: Meets. The governance layer is wholly owned here.
- **Control over the security posture**: **Partially meets.** The framework can validate and
  reject an unsafe configuration, but it cannot change upstream defaults. Where the upstream
  is permissive — broader role and action patterns, no schema validation — this repository
  can only detect, not prevent, at the source.
- **Bounded maintenance and dependency risk**: Partially meets. A pinned version bounds
  drift, but every upstream release requires re-validation, and consumers must acquire two
  repositories.
- **Zero core edits**: Meets.
- **Customer-specific extensions**: Meets, through this repository's own extension points.
- **Licence and visibility**: Meets. MIT to MIT, same copyright holder.

### Option 2: Extend

Adopt the upstream kit as the deployment layer and build the governance layer on top of it
in this repository, with a pinned and recorded upstream version. Security hardening that is
general-purpose — formal schemas, least-privilege role tightening, placeholder checks — is
contributed back upstream where it is in scope there; anything specific to the Zero Ops
governance model stays here. The guided workload discovery step emits configuration in the
shape the upstream kit already consumes, so the two compose without forking behaviour.

**Evaluation against priorities**:

- **Do not duplicate**: Meets fully. Deployment mechanics are reused, not rebuilt.
- **Preserve the safety differentiator**: Meets fully. The governance layer wraps the
  deployment layer, so the deny-by-default policy, evidence manifest and negative tests
  govern what the upstream kit is allowed to deploy and do.
- **Control over the security posture**: Meets. Gaps can be closed locally now and upstreamed
  over time, so the framework is never blocked waiting on an external maintainer.
- **Bounded maintenance and dependency risk**: Meets. A pinned version plus a documented
  upgrade procedure and a compatibility test bound the drift. Upstreaming general fixes
  reduces the long-term divergence that a permanent private fork would accumulate.
- **Zero core edits**: Meets. Onboarding edits configuration only; the upstream kit and the
  governance core are both untouched.
- **Customer-specific extensions**: Meets. Extension points sit in the governance layer and
  in recipe-level configuration.
- **Licence and visibility**: Meets. MIT to MIT, same copyright holder, so contributing back
  and going public are both unobstructed.

### Option 3: Replace

Implement generation, deployment, verification and the validation harness natively in this
repository, ignoring the upstream kit.

**Evaluation against priorities**:

- **Do not duplicate**: **Fails.** It rebuilds recipes, lifecycle scripts, two Infrastructure
  as Code backends, `azd` integration and a validation workflow that already exist under a
  compatible licence. This is the exact outcome `prd.md` exists to prevent.
- **Preserve the safety differentiator**: Meets, but at disproportionate cost — the
  differentiator does not depend on owning the deployment mechanics.
- **Control over the security posture**: Meets fully. This is the option's only real
  advantage.
- **Bounded maintenance and dependency risk**: **Fails.** It removes an external dependency
  by taking on permanent ownership of a far larger surface, including two Infrastructure as
  Code backends and cross-platform lifecycle scripts, with a maintaining core of fewer than
  ten engineers.
- **Zero core edits**: Meets.
- **Customer-specific extensions**: Meets.
- **Licence and visibility**: Meets.

## Decision

**Adopt Option 2, Extend.**

The ranked priorities decide this. Priority 1 eliminates Option 3 outright: rebuilding an
officially maintained, MIT-licensed, same-copyright template kit is duplicated effort of
precisely the kind `prd.md` was written to eliminate, and it would be taken on by a
maintaining core of fewer than ten engineers.

Between Options 1 and 2, priorities 3 and 4 decide. Both avoid duplication and both preserve
the governance layer, but Option 1 leaves this framework able only to *detect* an unsafe
upstream default, never to *prevent* it, and offers no path to close the gaps the source
analysis documented — no formal JSON Schema anywhere in the upstream kit, and a
least-privilege model that is only partially specified. Option 2 keeps the framework
unblocked: hardening can land here immediately and be contributed upstream on its own
timeline. Licence compatibility, MIT to MIT under the same copyright holder, makes that
contribution path real rather than theoretical.

This decision establishes the layering the rest of the architecture depends on:

- **Deployment layer** — upstream `sreagent-templates`, pinned. Generation, dry-run, deploy,
  verify, and the existing Infrastructure as Code backends.
- **Governance layer** — this repository. The Minimum SRE Agent Contract, configuration and
  evidence schemas, the deny-by-default tool policy, negative tests, and traceability.
- **Guided workload discovery** — this repository. Net-new; absent from both sources. It
  emits a scope contract and configuration in the shape the deployment layer consumes.

### Consequences

- The Infrastructure as Code decision is now **constrained rather than open**: the upstream
  kit already ships Bicep and Terraform backends, so that decision becomes which of the
  existing backends this framework treats as primary, not which technology to author from
  scratch. That evaluation belongs to its own ADR.
- The upstream version must be pinned, recorded, and covered by a compatibility test. The
  local clone reads `1.0.0` and may already trail upstream; the pinned version must be
  resolved against `microsoft/sre-agent` rather than the local fork.
- `agent.json` becomes the concrete binding format for the Azure SRE Agent runtime. The
  runtime-agnostic contract (CON-03) sits **above** it, and the binding is an emitted
  artifact, not the contract itself. This partially resolves the two-incompatible-formats
  conflict recorded in the source analysis.
- Upstream gaps become explicit backlog items here: no formal JSON Schema, partially
  specified least privilege, the unverified placeholder check in
  `validate-templates.yml`, and preview-era pins such as `upgradeChannel: "Preview"` and the
  finite region list.
- Nothing from the single-customer reference implementation enters this repository except
  through the generalization rules and the exclusion list in `source-analysis.md`
  section 5.4.

## Implementation Notes

- Pin the upstream by commit or tag and record it in a single, discoverable place so the
  upgrade procedure and the compatibility test both read the same value.
- Do not vendor a copy of the upstream kit into this repository without an explicit,
  documented reason. A recorded pin plus an acquisition step keeps provenance and licence
  attribution unambiguous.
- Treat every upstream assumption that the source analysis flagged as version-specific as
  something to pin and date, not to inherit silently.
- Exclude the upstream failure-injection lab scripts, per `source-analysis.md` section 5.4
  item 16. They intentionally damage environments and are demonstrations, not operational
  procedures.

## References

- `prd.md` — sections *Mission*, *Pattern Extraction*, *Infrastructure as Code Decision*
- `docs/architecture/source-analysis.md` — sections 3.2, 4, 7.2, 8
- `docs/features/sre-agent-recipe-framework/spec.md` — FR-31 to FR-43, FR-60 to FR-70,
  NFR-08 to NFR-14, CON-03, CON-08
- `docs/envisioning/README.md` — sections 2, 8, 9
- Upstream project: <https://github.com/microsoft/sre-agent>

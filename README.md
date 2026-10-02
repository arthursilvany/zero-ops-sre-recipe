# Zero Ops SRE Agent Recipe

A reusable recipe for building **read-only** SRE agents on Azure. One team configures the
recipe, then reuses it across customer workloads without editing the core. Behaviour lives
in contracts and configuration, so every claim the recipe makes can be checked offline,
by anyone, with no Azure login.

> **Status: early access, not yet deployable.** The offline contracts, the safety
> boundary and workload discovery are delivered. Provisioning and deployment (User Story
> 5) are in progress. This README is a preliminary entry point. Task T11.05 replaces its
> quickstart with one whose file and step counts are asserted against an executed run.

## Who this is for

| Reader | Start here |
|---|---|
| Analyst starting a new project from the recipe | [Use the recipe for a new project](#use-the-recipe-for-a-new-project) |
| Reviewer checking what the recipe guarantees | [What the recipe guarantees](#what-the-recipe-guarantees) |
| Contributor changing the framework itself | [CONTRIBUTING.md](CONTRIBUTING.md) |

## What the recipe guarantees

Each guarantee is enforced by an automated check that runs on every pull request, most of
them in the release gate (`tests/negative/`). None of them is a convention you are asked
to follow.

- **Read-only by construction.** Prohibited actions, the tool allow-list and the role
  assignments in compiled templates are all checked against published policy in
  [`core/policy/`](core/policy/). A role carrying write, delete or authorization
  permissions fails the gate.
- **A declared core and extension boundary.** Onboarding a workload is meant to be
  configuration only. `zeroops check-core` fails when a tracked file falls outside the
  categories declared in [`contracts/core-paths.json`](contracts/core-paths.json), or
  when a runtime-specific identifier leaks out of `core/binding/`. Proving zero core
  edits for a second workload is User Story 9.
- **No secrets and no customer identifiers in the repository.** A local hook and CI scan
  the full history. Examples use placeholders such as `<SUBSCRIPTION_ID>`.
- **Upstream is pinned, never copied.** The official Azure SRE Agent templates are pinned
  at an immutable commit digest and verified on fetch. The deployment composes them and
  does not re-author them ([ADR-0001](docs/architecture/decisions/0001-upstream-template-relationship.md),
  [`deploy/README.md`](deploy/README.md)).

## Prerequisites

| Need | Why |
|---|---|
| Python 3.11 or later | The floor is the strictest requirement in the pinned dependency closure |
| Git | Clone, and the core declaration check reads the tracked files |
| [gitleaks](https://github.com/gitleaks/gitleaks) | Only to commit; the local hook refuses to pass silently without it |
| Azure CLI and a subscription | Only for workload discovery (User Story 4) and, later, deployment |

The offline steps below need no Azure subscription, no Azure CLI and no login.

## First run, offline

Run from the repository root. On Linux and macOS replace `.\bin\zeroops.ps1` with
`./bin/zeroops`.

```powershell
git clone https://github.com/arthursilvany/zero-ops-sre-recipe.git
cd zero-ops-sre-recipe
python -m pip install --require-hashes --only-binary=:all: -r tools/requirements.lock
.\bin\zeroops.ps1 validate examples\minimal\
.\bin\zeroops.ps1 check-core
.\bin\zeroops.ps1 test --local
```

What each step proves:

| Step | Proves |
|---|---|
| `pip install` with both flags | Only the reviewed, hash-pinned closure reaches your machine; no build script runs |
| `validate examples\minimal\` | The smallest valid configuration passes every contract level |
| `check-core` | The repository still matches its declared core and extension boundary |
| `test --local` | The full offline suite passes with credentials stripped and sockets refused |

Every command, flag and exit code is documented in [`docs/commands.md`](docs/commands.md).

## Use the recipe for a new project

The recipe is consumed by **configuration**. Do not fork the core to adapt it to a
customer; anything a workload needs that the contracts cannot express is a gap to report.

1. **Start from an example.** Copy [`examples/minimal/`](examples/minimal/) for a single
   environment, or [`examples/two-environments/`](examples/two-environments/) for a
   production and non-production pair, into your own project repository.
2. **Replace the placeholders.** Keep real subscription, tenant and resource identifiers
   in your project repository or your pipeline, never in this one.
3. **Validate offline before anything touches Azure.**

   ```powershell
   .\bin\zeroops.ps1 validate <your-config-folder>\ --strict
   ```

   `--strict` turns Recommended-area warnings into failures. Use it in a readiness gate.
4. **Discover candidate workloads (optional, needs Azure read access).** Discovery runs
   the read-only queries in [`wizard/discovery/`](wizard/discovery/) and applies the
   published eligibility rules in [`wizard/eligibility/`](wizard/eligibility/). See
   [`docs/discovery-output.md`](docs/discovery-output.md) and
   [`docs/permissions.md`](docs/permissions.md).
5. **Emit the scope contract.** The guided step turns a selection into a scope contract,
   interactively or from a file for pipelines. See
   [`docs/guided-inputs.md`](docs/guided-inputs.md),
   [`docs/non-interactive.md`](docs/non-interactive.md) and
   [`docs/scope-contract.md`](docs/scope-contract.md).
6. **Deployment.** Not available yet. User Story 5 adds it. Until then, stop after step 5.

### What you edit and what you leave alone

| Path | Holds | Who edits it |
|---|---|---|
| `examples/` | Copyable starting configurations, placeholders only | You, in your copy |
| `extensions/` | The seam workloads plug into; planned, arrives with task T9.03 | You, through the extension contract |
| `contracts/` | JSON Schema contracts, vocabulary, core declaration | Framework only |
| `core/` | Runtime-agnostic policy and evidence model | Framework only |
| `wizard/` | Read-only discovery queries and eligibility rules | Framework only |
| `tools/`, `bin/` | The `zeroops` package and its entry points | Framework only |
| `deploy/` | Upstream pin and the composition over pinned modules | Framework only |
| `tests/` | Unit, validation, negative and Azure suites | Framework only |

A change you need in a "Framework only" path goes back to this repository as a pull
request, following [CONTRIBUTING.md](CONTRIBUTING.md). It must never be made in a copy.
A local core edit is how a recipe silently becomes many diverging products.

## How the work is organised

The framework is built with Spec-Driven Development: no code without a specification,
and no architectural choice without an ADR.

| Artifact | Location |
|---|---|
| Specification | [`docs/features/sre-agent-recipe-framework/spec.md`](docs/features/sre-agent-recipe-framework/spec.md) |
| Plan | [`docs/features/sre-agent-recipe-framework/plan.md`](docs/features/sre-agent-recipe-framework/plan.md) |
| Tasks, by user story | [`docs/features/sre-agent-recipe-framework/tasks.md`](docs/features/sre-agent-recipe-framework/tasks.md) |
| Architecture overview | [`docs/architecture/overview.md`](docs/architecture/overview.md) |
| Decisions | [`docs/architecture/decisions/`](docs/architecture/decisions/) |

### Delivery status

| User story | Scope | State |
|---|---|---|
| US-1 | Validate a configuration offline | Delivered |
| US-2 | Prove the read-only and safety boundary offline | Delivered |
| US-3 | Make the repository safe to publish and to execute | Delivered |
| US-4 | Discover workloads and emit a scope contract | Delivered |
| US-5 | Provision, deploy and validate a read-only agent | In progress |
| US-6 to US-11 | CI supply chain, security model, evidence, second workload, lifecycle, handover | Planned |

The tracked source of truth is the issue list of this repository.

## Security

Report vulnerabilities as described in [SECURITY.md](SECURITY.md). Never open a public
issue containing a secret, a tenant identifier or customer data.

## Licence

[MIT](LICENSE).

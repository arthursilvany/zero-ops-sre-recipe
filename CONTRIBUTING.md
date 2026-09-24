# Contributing

Thank you for contributing to the **Zero Ops SRE Agent Recipe**. This repository is a
reusable, production-oriented framework that other teams use to create and deploy SRE
agents across customer workloads. Contributions are therefore held to a framework
standard, not a prototype standard.

## Non-negotiable rules

1. **English only.** All repository content — documentation, source code, comments,
   configuration names, examples, tests, and user-facing text — must be written in
   English.
2. **No secrets, no customer data.** See [SECURITY.md](SECURITY.md). Use placeholders
   such as `<SUBSCRIPTION_ID>` and `<TENANT_ID>`.
3. **The reusable core stays generic.** Workload-specific and customer-specific content
   belongs in extension points, never in the core.
4. **No purposeless scaffolding.** Do not add empty folders or placeholder files without
   a defined purpose.

## The DevSquad SDD flow is mandatory

Code is never the first artifact. Every change must be traceable back to a specification
and, where architecture is affected, to an Architecture Decision Record.

```text
Envisioning → Specification → ADR → Plan → Tasks → Implementation → Review
```

| Phase | Artifact | Location |
|---|---|---|
| Envisioning | Vision, problem statement, scope and non-goals | `docs/envisioning/` |
| Specification | Feature specification | `docs/features/` |
| Architecture decision | ADR | `docs/architecture/decisions/` |
| Plan | Implementation plan | alongside the specification |
| Tasks | Task breakdown | alongside the plan |
| Implementation | Source, IaC, configuration, tests | `src/`, `infra/`, `config/`, `tests/` |

Rules:

- **Do not jump directly into implementation.** A pull request that adds code without a
  corresponding specification will be rejected.
- **Architectural decisions require an ADR** containing the options considered, the
  evaluation criteria, the recommendation, the trade-offs, and the risks. Irreversible
  choices must never be made silently.
- **Medium-impact and high-impact decisions stop at a review checkpoint** before
  implementation proceeds.
- **Deliver in thin, reviewable slices.** A slice should be independently reviewable and
  leave the repository in a valid state.
- Templates are provided under `docs/features/TEMPLATE.md`,
  `docs/envisioning/TEMPLATE.md`, and `docs/architecture/decisions/ADR-TEMPLATE.md`.
  Authoring conventions live in `.github/instructions/`.

## Local setup

Before your first commit, enable the local secret gate:

```sh
git config core.hooksPath tools/hooks
```

This requires [gitleaks](https://github.com/gitleaks/gitleaks) on your `PATH`. The hook
scans full history before a push leaves your machine and refuses to pass silently when
gitleaks is missing. See [SECURITY.md](SECURITY.md) for what it checks and what to do if
something slips through.

## Branching and commits

- Trunk-based development off `main`. Direct pushes to `main` are not permitted.
- Branch naming: `feature/<short-description>`, `fix/<short-description>`,
  `docs/<short-description>`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/),
  for example `feat(infra): add reusable managed identity module`.

## Pull requests

Every pull request must:

- Target `main` and pass all CI quality gates.
- Link to the specification, ADR, or work item it implements.
- Describe what changed, why, and which files were created or modified.
- Include or update tests and documentation for the change.
- Keep documentation and implemented commands consistent — if a command changes, the
  documentation that references it changes in the same pull request.

Tests that require a live Azure subscription must be clearly separated from tests that
run locally. **Never claim that a live deployment succeeded unless it was actually
executed and evidence is available.**

## Contributor License Agreement

This project is licensed under the MIT License with copyright held by Microsoft
Corporation. Most Microsoft-owned repositories require contributors to agree to a
Contributor License Agreement (CLA) declaring that you have the right to grant Microsoft
the rights to use your contribution. Visit <https://cla.opensource.microsoft.com> to
check your status. When you open a pull request, a CLA bot will automatically indicate
whether a CLA is required and annotate the pull request accordingly. You only need to do
this once across all repositories using the Microsoft CLA.

## Code of Conduct

This project has adopted the Microsoft Open Source Code of Conduct. See
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for details.

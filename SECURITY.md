<!-- BEGIN MICROSOFT SECURITY.MD V1.0.0 BLOCK -->

## Security

Microsoft takes the security of our software products and services seriously, which
includes all source code repositories in our GitHub organizations.

**Please do not report security vulnerabilities through public GitHub issues.**

For security reporting information, locations, contact information, and policies,
please review the latest guidance for Microsoft repositories at
[https://aka.ms/SECURITY.md](https://aka.ms/SECURITY.md).

<!-- END MICROSOFT SECURITY.MD BLOCK -->

---

## Security expectations for this repository

This repository is a **reusable recipe for building and deploying SRE agents**. It ships
Infrastructure as Code, agent instructions, and configuration contracts that other teams
deploy into their own Azure environments. A defect here can be inherited by every
downstream workload, so the rules below are enforced in addition to the reporting process
above.

### Never commit

- Secrets, tokens, credentials, connection strings, certificates, or private keys.
- Tenant IDs, subscription IDs, resource IDs, or private endpoints belonging to a real
  environment.
- Customer names, customer identifiers, or any personal data.
- Environment-specific values copied from a production deployment.

Use clearly named placeholders instead — for example `<SUBSCRIPTION_ID>`,
`<TENANT_ID>`, `<WORKLOAD_NAME>`. Sensitive values must be referenced externally
(for example via Azure Key Vault or a managed identity) rather than stored in this
repository.

### Secure-by-default design rules

- Prefer **managed identities** wherever the selected architecture supports them.
- Apply **least privilege** to every role assignment.
- Keep **read-only diagnostic actions separate from mutating remediation actions**.
- Require an **explicit human approval gate** for destructive, high-impact, or
  customer-facing remediations.
- Document agent boundaries and prohibited actions.
- Validate and constrain all user-controlled configuration.
- Never log secrets or sensitive workload data.
- Preserve an auditable record of agent actions where the architecture supports it.

### Threats that must be considered in design and review

Prompt injection, unsafe tool invocation, excessive permissions, data leakage, and
untrusted diagnostic content being treated as instructions.

If a reference implementation conflicts with these principles, document the conflict and
propose a safer design rather than reproducing the unsafe behaviour.

---

## How the rules above are enforced

Git history is append-only from the point of view of everyone who has already cloned or
forked a repository. Deleting a value in a later commit does not remove it; it only hides
it from the working tree. Every control below therefore targets **history**, not the
checked-out files.

| Control | Where | Blocks or reports | Covers |
|---|---|---|---|
| Full-history scan | [`.github/workflows/security-scan.yml`](.github/workflows/security-scan.yml) | Reports, after the push has landed | Every commit reachable from `HEAD` |
| Client-side pre-push scan | [`tools/hooks/pre-push`](tools/hooks/pre-push) | Blocks, before the push leaves the machine | Every commit reachable from `HEAD` |
| Platform push protection | GitHub | Blocks, at the remote | Credential patterns only |

Rules for all three live in a single file, [`.gitleaks.toml`](.gitleaks.toml), so the
local check and the CI check cannot drift apart.

**Platform push protection is currently unavailable on this repository.** It requires
GitHub Advanced Security on a private repository, and the API rejects the request with
`Secret scanning is not available for this repository`. The consequences, the substitute
control, and the trigger for re-enabling are recorded in
[ADR-0005](docs/architecture/decisions/0005-secret-scanning-controls.md). Enabling it is a
**precondition of making this repository public**, not a follow-up task.

### Enable the local check

```sh
git config core.hooksPath tools/hooks
```

This requires [gitleaks](https://github.com/gitleaks/gitleaks) on your `PATH`. The hook
refuses to pass silently when gitleaks is absent, because a check that quietly does
nothing is worse than no check: it produces confidence without evidence.

### Run the check by hand

```sh
# The real gate: every commit in history.
gitleaks detect --config .gitleaks.toml --redact

# The working tree only. Useful while editing, but it PASSES on a repository
# whose history is already poisoned. Never treat it as the gate.
gitleaks detect --config .gitleaks.toml --no-git --redact
```

---

## If a secret or identifier reaches this repository

Treat the value as compromised from the moment it is committed, even if the commit was
never pushed and even if the repository is private. The steps below are ordered
deliberately.

### 1. Revoke first, clean up second

Rotate or revoke the exposed credential **before** touching git history. History rewriting
takes time, can fail, and does not reach clones, forks, caches, or the GitHub API's view
of unreachable objects. Revocation is the only step that actually removes the attacker's
capability.

For an environment identifier rather than a credential — a tenant, subscription, or
resource identifier — there is nothing to revoke. Record the exposure, assess whether it
reveals customer identity, and continue to step 2.

### 2. Confirm the blast radius

```sh
# Which commits carry the value.
git log --all --oneline -S'<THE_VALUE>'

# Whether the commits ever left this machine.
git log --all --not --remotes --oneline
```

If nothing was pushed and the repository has no other clone, step 3 is sufficient. If it
was pushed, assume it is public and that step 1 was mandatory.

### 3. Rewrite the history

Use [`git filter-repo`](https://github.com/newren/git-filter-repo).

```sh
# Back up first. filter-repo rewrites every object id and is not reversible.
git clone --mirror . ../repo-backup.git

# Remove a value everywhere it appears, in every commit, on every branch.
printf 'literal:<THE_VALUE>==><REDACTED>\n' > /tmp/replacements.txt
git filter-repo --replace-text /tmp/replacements.txt

# Or remove an entire file that should never have existed.
git filter-repo --invert-paths --path path/to/leaked-file
```

`git filter-repo` intentionally removes the `origin` remote so a rewrite cannot be pushed
by reflex. Re-add it explicitly, then force-push every ref:

```sh
git remote add origin <REMOTE_URL>
git push --force --all origin
git push --force --tags origin
```

### 4. Verify, do not assume

```sh
# Expect no output.
git log --all --oneline -S'<THE_VALUE>'

# Expect a clean scan over the rewritten history.
gitleaks detect --config .gitleaks.toml --redact
```

### 5. Deal with what the rewrite did not reach

A force-push does not clean up:

- **Existing clones and forks.** Notify every holder; ask them to re-clone rather than
  pull, because a pull will merge the old objects back in.
- **Unreachable objects still served by GitHub.** Open a support request to have them
  garbage-collected. Until then the old commit is still retrievable by its SHA.
- **Pull requests, issues, code review comments, and CI logs**, which store their own
  copies of the diff. Each must be edited or deleted separately.
- **Caches and mirrors** outside GitHub.

### 6. Close the loop

Record the exposure, the remediation, and the follow-up in the pull request that restores
the branch. If the pattern was one the scanner did not catch, add a rule to
`.gitleaks.toml` in the same pull request — otherwise the identical mistake is still
possible tomorrow.

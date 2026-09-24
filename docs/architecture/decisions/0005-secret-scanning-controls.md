# Secret Scanning Controls Without GitHub Advanced Security

**Status**: Accepted
**Date**: 2026-09-24
**Accepted**: 2026-09-24
**Depends on**: [0001 — Upstream Template Relationship](0001-upstream-template-relationship.md)
**Implements**: SEC-006 (High, effective immediately), NFR-01, NFR-02, NFR-04, SC-05

## Context

User Story 3 requires the repository to be safe to publish before any further commit
lands. Its first acceptance criterion is explicit: platform secret scanning **and** push
protection enabled on the repository, verified by an API read.

That criterion cannot be satisfied as written. The repository is private and belongs to a
personal account, and GitHub secret scanning on a private repository requires GitHub
Advanced Security. The API rejects the request:

```text
PATCH /repos/<OWNER>/<REPO>
{"security_and_analysis":{"secret_scanning":{"status":"enabled"},
                          "secret_scanning_push_protection":{"status":"enabled"}}}

HTTP 422
{"message":"Secret scanning is not available for this repository."}
```

A read of the same repository returns `"security_and_analysis": null`, confirming the
feature is absent rather than merely disabled.

This matters more than a missing convenience. The two controls are not interchangeable:

- **Push protection blocks.** It rejects the push, so the value never reaches the remote
  and never enters history.
- **A CI workflow reports.** It runs *after* the push has landed. By the time it fails,
  the commit exists on the remote, is retrievable by SHA, and may already have been
  fetched.

Git history is irreversible in the sense that matters: a later deletion commit does not
remove a value from history, and a force-push does not reach existing clones, forks,
unreachable objects still served by GitHub, or the copies of the diff held by pull
requests and CI logs. Losing the *blocking* control is therefore a real reduction in
safety, not a paperwork gap.

Three options were available.

1. **Make the repository public now** to obtain free secret scanning and push protection.
   This inverts the dependency: publication is the event the gate exists to make safe, so
   publishing in order to get the gate exposes whatever the gate would have caught.
2. **Purchase GitHub Advanced Security.** Outside the authority of this repository, and
   CON-11 requires the recipe to be adoptable by any customer, including those without
   GHAS. A control that only exists on a paid tier cannot be the recipe's only answer.
3. **Restore the blocking property on the client**, and keep CI as the enforced
   after-the-fact gate.

## Decision

Adopt option 3, as a layered control set with a single shared rule file.

- **`.gitleaks.toml`** is the one rule set. It extends the default gitleaks pack for
  credential material and adds custom rules for the environment-identifier classes named
  in `SECURITY.md` that no generic scanner looks for: subscription paths, fully qualified
  resource identifiers, directory identifiers bound to a GUID, and environment-specific
  endpoint hostnames. Local and CI checks read the same file so they cannot drift.

- **`tools/hooks/pre-push`** restores the blocking property. It runs before the push
  leaves the machine and fails closed when gitleaks is absent, rather than passing
  silently. It is enabled with `git config core.hooksPath tools/hooks`.

- **`.github/workflows/security-scan.yml`** is the **gate of record**. It scans every
  commit reachable from `HEAD`, not the working tree, and it asserts the clone is not
  shallow before scanning, because `fetch-depth: 0` is a request rather than a guarantee
  and a shallow clone would weaken the scan while still reporting success.

- **Platform push protection is a precondition of making this repository public**, not a
  follow-up task. The publication checklist must include the API read that the original
  acceptance criterion demanded.

Two details are deliberate. Scans run with `--redact`, because a gate that prints the
secret it found into a CI log has republished it. Third-party components are pinned by
digest — `actions/checkout` by commit SHA rather than tag, and the gitleaks archive by
SHA-256 — consistent with ADR-0001: a tag is mutable and is therefore not an integrity
control.

## Consequences

**Accepted risks.**

- The hook is bypassable with `--no-verify` and only protects contributors who enabled
  it. It is defence in depth, not the gate of record. This is stated in the hook itself
  so that no reader mistakes it for enforcement.
- Between a push and the workflow's verdict there is a window in which a secret exists on
  the remote. This window is inherent to the after-the-fact model and is the precise
  reason platform push protection remains a publication precondition.
- Custom identifier rules are pattern-based. They catch the shapes named in
  `SECURITY.md`; they do not catch a customer name that looks like an ordinary English
  word. Closing that gap is SC-13's salted-digest mechanism, decided separately in S3-14
  and enforced by S4-17.

**Gained.**

- The control works on any repository, on any plan, in any customer tenant. Under CON-11
  that is a feature of the recipe and not only of this repository: a customer adopting
  the recipe without GHAS inherits a gate that functions.
- The gate is falsifiable, and was falsified before being accepted. A synthetic secret
  planted in a non-tip commit, with the working tree clean, causes the history scan to
  fail while a working-tree scan reports no leaks. That asymmetry is the defect being
  closed, and it is now demonstrated rather than asserted.

## Revisit when

- The repository becomes public, at which point secret scanning and push protection
  become available at no cost and **must** be enabled as part of publication.
- GitHub Advanced Security becomes available to the owning account.
- The SC-13 salted-digest vocabulary gate lands, which may absorb part of the custom rule
  set.

## Amendment, 2026-09-24: branch protection is blocked by the same root cause

Attempting to require pull requests and a passing security scan before merge to `main`
fails for the same reason:

```text
POST /repos/<OWNER>/<REPO>/rulesets
HTTP 403
{"message":"Upgrade to GitHub Pro or make this repository public to enable this feature."}
```

This is the second control blocked by "private repository on a free personal account",
and it compounds the first. Without branch protection there is no merge gate, so the
security scan cannot block anything at all: it runs after a direct push to `main` has
already landed, and nothing prevents that push.

The two findings therefore share one remedy. Making the repository public restores both
push protection and branch protection at no cost. That is not an argument for publishing
early — publication is still the event these gates exist to make safe, so it must follow
the completion of User Story 3, not precede it.

The consequence for sequencing is explicit: **complete the repository-safety work, then
publish, then enable both controls as part of publication.** Until then, `CONTRIBUTING.md`
forbids direct pushes to `main` by convention only, and convention is not enforcement.
That gap is stated here rather than hidden, because an unenforced rule that reads like an
enforced one is the more dangerous of the two.

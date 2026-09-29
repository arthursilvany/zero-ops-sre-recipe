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

## Amendment, 2026-09-29: the blocked controls are now enabled, and one of them does not block

The repository is public, which removes the root cause recorded above. Both controls that
were rejected are now enabled, and both were verified rather than assumed.

**Branch protection is enabled and enforced.** Five required status checks, linear
history, no force pushes. Enforcement needed a second call: with `enforce_admins` unset,
a push by an administrator succeeded while reporting `remote: Bypassed rule violations`,
so the protection applied to nobody in a single-maintainer repository. After
`POST /repos/<OWNER>/<REPO>/branches/main/protection/enforce_admins`, the same push was
rejected with `GH006 ... 5 of 5 required status checks are expected`. The procedure and
the two distinguishing refusal texts are in `docs/commands.md`.

**Secret scanning is enabled. Push protection is enabled and did not block.** An API read
returns `secret_scanning: enabled` and `secret_scanning_push_protection: enabled`. The
measurement:

| Probe | Local hook | Result at the remote | Alert raised |
|---|---|---|---|
| Random `ghp_`-shaped string | blocked the push | accepted with `--no-verify` | none |
| Synthetic provider-pattern credential | blocked the push | accepted with `--no-verify` | yes, `push_protection_bypassed: false` |
| Same, repeated minutes later | not exercised | accepted with `--no-verify` | yes |

The first probe raised no alert, so it was never recognised as a secret and proves
nothing: that pattern carries a checksum a random string cannot satisfy. It is recorded
because an unrecognised probe and a working control produce the same observation, and
only the alert count tells them apart.

The second and third probes were recognised. Detection fired and the push still landed.
The repeat rules out propagation delay, and `push_protection_bypassed: false` rules out
the push having been waved through as an allowed bypass. The blocking step did not run.
The cause is undetermined and is not asserted here.

Two further settings, `secret_scanning_non_provider_patterns` and
`secret_scanning_validity_checks`, were requested in the same call and in a call of their
own. Both returned `200` and both remained `disabled`.

Every probe used a synthetic value that was never valid, pushed to a throwaway branch
that was deleted, with both alerts resolved as `used_in_tests`.

### Consequence of this amendment

The decision above does not change. Option 3 stays: the pre-push hook and the
full-history workflow remain the gates of record, and the platform layer is a reporting
control layered on top rather than the blocking control the original acceptance criterion
assumed. That criterion asked for an API read, and an API read alone would have passed
here while the control did nothing.

This is the same failure this repository keeps finding, in a third place: a control that
reports itself configured and cannot distinguish that from being effective. Branch
protection did it, the negative-suite flag did it, and platform push protection does it
now. The general rule stands: read the setting, then make the control refuse something.

Under CON-11 this strengthens rather than weakens the recipe. A customer adopting it
inherits a gate that functions without GitHub Advanced Security, on any plan, and does
not inherit a dependency on a platform control whose blocking behaviour has to be
measured per repository.

**Not covered by the offline suite.** The state of these controls is a property of the
remote, not of the tree, so the negative suite cannot assert it without a network and a
credential. The check is a manual step in the operations guide rather than an automated
one, and that is a stated limitation.

### Revisit this amendment when

- Platform push protection is observed to block a recognised pattern on this repository,
  at which point the control table in `SECURITY.md` should say it blocks and the claim
  should carry the date it was measured.
- `secret_scanning_non_provider_patterns` or `secret_scanning_validity_checks` stops
  silently returning `200` while staying disabled.

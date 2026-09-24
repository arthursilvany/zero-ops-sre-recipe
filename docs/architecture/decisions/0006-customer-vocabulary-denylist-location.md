# Customer-Vocabulary Denylist Location

**Status**: Accepted
**Date**: 2026-09-24
**Accepted**: 2026-09-24
**Depends on**: [0005 — Secret Scanning Controls](0005-secret-scanning-controls.md)
**Implements**: SEC-014, SC-13, NFR-03
**Blocks**: S4-17 (the SC-13 enforcement gate)

## Context

SC-13 requires zero customer-specific content in the core, and NFR-03 requires that
requirement to be checked rather than trusted. Pattern-based rules already catch the
*shaped* identifiers — subscription paths, resource identifiers, directory identifiers
bound to a GUID, endpoint hostnames — and ADR-0005 put those in `.gitleaks.toml`.

They do not catch the residue that actually leaks a customer: a company name, a product
codename, an internal system name, a team name, a site name. Those look like ordinary
words. No generic scanner can recognise them, and no regular expression can distinguish a
customer codename from an English noun. Catching them requires knowing the specific
vocabulary to look for.

That leads directly to a contradiction, recorded as SEC-014 in the architectural security
review:

> **A denylist of customer vocabulary is itself customer vocabulary.**

Committing `denylist.txt` containing the very names that must never appear would publish
them, in plaintext, in the permanent history of a repository intended to become public.
The control would become the disclosure it exists to prevent — and worse than an absent
control, because it would concentrate the sensitive terms into a single conveniently
labelled file.

Four options were considered.

1. **Commit the plaintext list.** Self-defeating, as above.
2. **Commit nothing and rely on review.** Human review does not scale, is not
   reproducible, and cannot be a gate. NFR-03 requires a check.
3. **Commit the list encrypted.** Moves the problem to key distribution without solving
   it, and an encrypted blob in git history is decryptable forever by anyone who later
   obtains the key. Git history is not revocable.
4. **Commit only irreversible digests of the terms, and supply the plaintext at run
   time.**

## Decision

Adopt option 4.

- The repository stores **only salted SHA-256 digests** of the forbidden terms, in a
  committed digest file. A digest is one-way: it can answer "is this token forbidden?"
  without ever revealing what the forbidden tokens are.
- **The plaintext vocabulary and the salt live outside the repository.** They are supplied
  to the gate at run time, from the adopting organization's own secret store. Neither is
  ever committed, in any branch, in any form.
- The salt is **mandatory, not optional**. An unsalted digest of a short, guessable term
  such as a company name is trivially reversible by dictionary attack, which would make
  the digest file a disclosure with extra steps rather than a control.
- The gate **fails closed when the vocabulary is absent**, reporting that it could not
  run. A vocabulary gate that silently passes when unconfigured is worse than no gate: it
  reports success while checking nothing, and SC-13 would then be satisfied on false
  evidence.
- A **committed plaintext denylist fails a check.** The structural rule
  `zeroops-plaintext-denylist` in `.gitleaks.toml` already fails on any committed
  `denylist`, `deny-list`, `blocklist` or `forbidden-terms` file, so the self-defeating
  option is mechanically blocked rather than merely discouraged.

Tokenisation, normalisation and the digest file format are implementation concerns owned
by S4-17. This decision fixes only *where the vocabulary lives*, which is what T6.05 was
blocked on.

## Consequences

**Accepted limitations. These are real and must not be papered over.**

- Digest matching is **exact-token matching**. It catches a customer name; it does not
  catch a misspelling, an inflection, an abbreviation, or that name embedded inside a
  longer identifier unless tokenisation splits it out. This gate narrows the gap; it does
  not close it, and it must never be presented as proof that no customer content remains.
- The control is only as good as the supplied vocabulary. An organization that does not
  maintain its list gets a gate that passes because it was asked the wrong question.
- Because the salt is external, **digests are not portable between organizations**. Each
  adopting organization generates its own digest file. This is a consequence of making
  the digests irreversible and is accepted deliberately.

**Gained.**

- SC-13 becomes checkable without the check itself leaking anything, which is the
  contradiction SEC-014 identified.
- The mechanism works for any adopting customer under CON-11, because nothing about it
  depends on this repository's vocabulary, this repository's tenant, or a paid platform
  feature.
- The failure mode is loud. An unconfigured gate reports that it did not run, rather than
  reporting success.

## Revisit when

- S4-17 implements the gate and discovers a tokenisation requirement this decision did not
  anticipate.
- An adopting organization needs shared vocabulary across repositories, which would need a
  shared-salt scheme and its own threat analysis.

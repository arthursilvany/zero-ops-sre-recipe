# Upstream acquisition

This directory holds the pin for the upstream template layer that ADR-0001 composes
rather than forks.

## Acquiring upstream code is a trust-boundary crossing

ADR-0001 keeps `microsoft/sre-agent` composed and parameterized, never forked. The
practical consequence is that **upstream code executes on the operator workstation** —
the machine holding live Azure credentials during discovery and deployment, and therefore
the highest-privilege boundary in the system (CON-06).

That makes the fetch a trust decision rather than a download. Treat it the way you would
treat running any third-party script as your own user, because that is exactly what it is.

Two consequences follow, and both are enforced rather than advisory:

1. **The pin is a commit digest, never a tag.** A tag is a mutable pointer. Whoever owns
   the upstream repository can move it, so a tag-pinned dependency can change underneath a
   previously verified build while the pin still reads the same. A tag is a convenience,
   not an integrity control (SEC-004).
2. **The fetched tree is verified before anything in it runs.** A correct pin proves
   nothing about what actually arrived over the network.

## What the lock records

| Field | Meaning |
|---|---|
| `commit` | The 40-character lowercase commit digest. The authoritative pin. |
| `treeSha1` | Git object id of the pinned subtree. Independently verifiable with git, but only meaningful over a git transport. |
| `contentSha256` | Digest of the tree contents, computed by this repository. Transport-independent: it covers a git clone, a release tarball, or an archive export alike. |
| `declaredVersion` | What upstream calls this release. Informational only — it is not an integrity control and must never be used as one. |
| `securityReviewed` | Whether the pinned code has been reviewed, not merely identified. |

`contentSha256` attests to **what** was pinned, not that it is **safe**. Those are
different claims and the lock keeps them separate on purpose.

## Verify before executing

```sh
# Offline: is the pin itself a valid immutable reference?
python tools/upstream/verify_upstream.py --check-lock

# After fetching: does the tree that arrived match the pin?
python tools/upstream/verify_upstream.py --verify <FETCHED_TREE>
```

Both fail closed. A non-zero exit means **do not execute the upstream code** — not "warn
and continue". An unrecorded `contentSha256` is also a failure, because a digest that was
never set cannot attest to anything, and treating it as a pass would turn the absent
control into a silent one.

## Raising the pin is a security-reviewed change

Bumping `commit` is not a version bump. Between two upstream commits, code that runs with
the operator's credentials may have changed. The steps:

1. Fetch the new tree at the exact target commit.
2. Review the diff of what will execute: `bin/`, `bicep/`, and anything invoked by them.
   Read the change, do not skim the release notes; upstream is preview-era software and
   its notes are not a security attestation.
3. Record the new digest:

   ```sh
   python tools/upstream/verify_upstream.py --record <FETCHED_TREE>
   ```

4. Update `securityReviewed` and `provenance` in the same commit, and state in the pull
   request what was reviewed and by whom.
5. Run the compatibility tests. An upstream change that silently alters the composed
   parameters is a breakage even when every digest verifies correctly.

A pull request that raises the pin without steps 2 and 4 should be rejected, because it
converts a reviewed dependency into an unreviewed one while looking like routine
maintenance.

# Discovery

The guided setup reads a subscription to propose candidates. This directory holds the queries it issues, and nothing else. It decides no eligibility: the rules that decide are published in [`../eligibility/README.md`](../eligibility/README.md).

## What is read

Three queries, all in [`query-catalogue.json`](query-catalogue.json), all read-only, all issued through the command broker.

| Query | What it answers |
|---|---|
| `subscription-readability` | Can this identity see the named subscription at all? |
| `subscription-resources` | Which resources can it read there? |
| `resource-diagnostic-settings` | Which of those emit a signal that can be read without changing them? |

Each entry records the query text, a SHA-256 over that text, and the date it was reviewed. The hash is recomputed before any query is issued. A catalogue edited after review validates against its schema perfectly well; the hash is the only thing that notices, which is what "integrity-verified" has to mean to be worth stating.

Discovery refuses to run at all if any hash disagrees, rather than skipping the entry in question. A partial catalogue would produce a shorter candidate list, which is the failure this whole page is about.

## Scope is one subscription

v1 discovery targets exactly one subscription, named as a GUID. Widening it later is purely additive: a second subscription adds candidates and removes none, so nothing decided under the narrow scope has to be revisited.

## An empty answer and a withheld one are different answers

This is the part worth reading twice.

Resource Graph returns what the calling identity can see. It does not report what it withheld. An identity with no read access to the subscription gets the same reply as an identity looking at an empty subscription: no rows, no error, exit code zero. Anything that judged by the row count alone would report "no candidates" for a permissions problem, and the operator would go looking for resources that were there the whole time.

So readability is established first, by asking whether the subscription container itself is visible. If it is not, discovery reports an access-denied state naming the missing permission, and reports no candidate list at all.

The same holds for the two enumerating queries. If either is refused, the result carries a denial alongside whatever rows did come back, and **the rows cannot be read as if they were the whole answer**: `DiscoveryResult.rows` raises while a denial is present. A caller that genuinely wants the incomplete list calls `partial_rows()`, which says so at the call site. An attribute that quietly returned the shorter list would be exactly the silent scope reduction that is forbidden, dressed up as a convenience.

A denial is never a shorter list.

## Why these queries and not more

`wizard/discovery/` is a core path, so it ships no workload type in either direction. A default list of types to look for would be workload content in the core; a default list to skip would be the same content written backwards. Type eligibility arrives from an installed extension.

`resource-diagnostic-settings` names one Azure type, and that is a deliberate exception rather than an oversight. `microsoft.insights/diagnosticSettings` is the platform mechanism by which *any* resource emits diagnostics. Naming it admits no workload and excludes none. The exception is asserted by a test, so widening it is a visible act.

Tags are not projected. A tag is free text an operator controls, and is the likeliest place a secret-shaped value turns up. Projecting one would put it in the discovery output, and from there into any bug report made from that output. The controls that would make it safe are the field allow-list on the emitter and the negative test that a secret-shaped tag cannot reach a scope contract; until both exist, the field stays out.

## What happens to what is read

Discovery output holds real resource identifiers, real names and real resource-group names. It is ignored by git by default, it carries a warning as its first key, and it has a redaction mode for bug reports. See [`../../docs/discovery-output.md`](../../docs/discovery-output.md).

## What a fresh install returns

On a fresh install with no workload extension, every resource is read and none is a candidate, because no extension has said which types are eligible. That looks like a fault and is not one. The empty-result report explains which rule stopped the list, so the operator is told rather than left to infer.

## Permissions

The identity running discovery and the identity the deployed agent uses are two different permission sets, documented separately in [`../../docs/permissions.md`](../../docs/permissions.md). The denial messages here name the specific action that was missing, so the fix is a grant rather than an investigation.

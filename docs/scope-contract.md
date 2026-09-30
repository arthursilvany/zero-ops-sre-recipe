# The scope contract

The scope contract states what the agent may observe. Every downstream artifact binds to its `canonicalHash`, so it is the anchor of the evidence chain, and unlike the discovery output it goes into version control.

That is the whole difficulty. It is built from a subscription-wide inventory of real identifiers and real names, and the thing it is built from is deliberately never committed (see [`discovery-output.md`](discovery-output.md)). This page describes what is allowed to cross that line (SEC-007).

## One field per selection kind, named in advance

A scope entry has two fields, `kind` and `selector`. The kind is a selection mechanism, deliberately not a workload type, and the core ships no workload-type content of its own.

| Kind | Where the selector comes from |
|---|---|
| `resource` | the discovery row's `id` |
| `resourceGroup` | the discovery row's `resourceGroup` |
| `tag` | the operator, because discovery projects no tags |

Nothing else from a row reaches the contract, and no code path copies a row. Every entry is assembled from the kind and that single field.

The direction is the control. A list of fields to strip would let the next column added to the discovery projection travel into a committed file by default, and the failure would be silent, because a contract carrying an extra field still looks like a contract. Under an allow-list a new column is inert until somebody decides what it means, and the test that holds this reads the projection out of the query catalogue rather than from a list copied into a test.

`tag` is the exception that proves why the rest is safe. Discovery projects no tags at all, because a tag is operator-controlled free text and the likeliest place a credential ends up. A tag selector therefore cannot be derived from a row, and is the one selector this framework cannot trace back to a value Azure chose.

## Exactly the selection, in both directions

A selected candidate that the discovery result does not contain is refused. Without that, "contains exactly the selected candidates" would be satisfiable by a contract holding something that was never discovered.

Two rows that resolve to the same selector produce one entry. Selecting three resources that share a resource group, by resource group, selects that group once. That is the same selection written once, and the schema rejects the alternative.

Exclusions are declared, never implied by omission, so the exclusion list has no default. Passing an empty list is a statement. Leaving it out is not available.

## Two refusals the schema asks for and cannot make

`subscriptionRef` names an entry in the framework configuration rather than carrying a subscription identifier. Its pattern allows lowercase letters, digits and hyphens, beginning with a letter, which a subscription identifier beginning with a letter satisfies. JSON Schema cannot tell the two apart, so the emitter does, and a reference shaped like a directory identifier is refused.

`generatedAgainst` is an opaque marker for the state the selection was taken against. It is documented as not a resource identifier precisely because the file is committed, and a maximum length does not express that. A digest is a legitimate marker and is accepted; a resource path, an endpoint, an address or a directory identifier is not.

## A credential is refused, not redacted

No secret may be written into a scope contract. Redacting one would still leave a decision this framework is not entitled to make on the operator's behalf, so nothing is emitted at all: the contract is refused whole, and the operator fixes the input.

The scan looks for named credential material, which is an assignment whose left-hand side is a word that names a credential, a web token, a private key block, or a shared access signature. Its vocabulary of marker words is shared with the schema linter, so the names a schema may not use and the values a contract may not carry cannot drift apart.

It will not catch a high-entropy value that names itself nothing, and it does not claim to. The control that matters for that case is upstream: discovery does not read tags, so an unnamed secret in a tag never reaches a selection in the first place.

## Checking one after the fact

```text
python -m zeroops.scope_emitter scope-contract.json
```

This asks two independent questions. Whether the file still validates, which the ordinary validator answers. And whether the recorded digest is the digest of what is in the file, which nothing else asks: a contract edited after it was approved validates perfectly and no longer describes the approved scope.

The digest is SHA-256 over the canonical form of the document with the hash field removed first, lowercase hex, as ADR-0004 pins it. Self-exclusion is part of the definition, because a document carrying its own digest while it was computed could never reproduce it.

A hash detects drift and authenticates nothing. A modified contract with a recomputed hash is indistinguishable from an approved one. That is recorded as a known limitation, and signing becomes required the moment the framework is allowed to change anything.

## The file itself

It is written with sorted keys and a fixed newline, so the same selection produces the same bytes on Windows and on Linux. The digest is over the canonical form rather than over those bytes, which is what lets the file stay readable without making the hash depend on how it was laid out.

The filename matters. The validator takes the artifact kind from the part of the filename before the first dot, so a contract written under another name validates against nothing. Writing one under a name the validator cannot dispatch on is refused.

See also [`discovery-output.md`](discovery-output.md) and [`../wizard/discovery/README.md`](../wizard/discovery/README.md).

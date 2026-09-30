# Guided inputs

The guided step asks for seven values. This page says what each one is, what
will be accepted, and why several things it could have asked for are not
asked for at all.

To read the same explanations from the tool rather than from this page:

```bash
PYTHONPATH=tools python -m zeroops.prompts --explain
```

## What is collected

| Input | Feeds | What it decides |
| --- | --- | --- |
| `subscription-reference` | `/subscriptionRef` | Which entry in the framework configuration's `externalReferences` resolves to the subscription to observe. |
| `observation-start` | `/observationPeriod/start` | The earliest point in time the agent may look back to. |
| `observation-end` | `/observationPeriod/end` | The latest point in time the agent may look at. |
| `max-tool-calls` | `/executionLimits/maxToolCalls` | How much work one run can cause. |
| `max-wall-clock-seconds` | `/executionLimits/maxWallClockSeconds` | How long one run may take. |
| `max-result-set-rows` | `/executionLimits/maxResultSetRows` | How much of the environment one answer can carry back. |
| `per-query-timeout-seconds` | `/executionLimits/perQueryTimeoutSeconds` | How long one query may run before it is abandoned. |

Every row's second column is a JSON pointer into
[`contracts/schemas/scope-contract.schema.json`](../contracts/schemas/scope-contract.schema.json).
That is the whole of the mapping: an input exists because a field consumes it,
and a test asserts the pointer resolves. An input that fed nothing would fail
to resolve, and a required field that nobody filled would fail the
completeness check described below.

## What is not collected, and where it comes from instead

| Field | Supplied by |
| --- | --- |
| `schemaVersion` | Pinned by the schema, so asking would invite a wrong answer. |
| `inScope` | The discovery selection. |
| `outOfScope` | The discovery selection. |
| `generatedAt` | The clock at the moment the contract is emitted. |
| `generatedAgainst` | The marker for the discovery run the selection was taken against. |
| `canonicalHash` | Computed over the finished document, so it cannot be supplied. |

These two tables together account for the schema's `required` list exactly,
and a test asserts that in both directions. Adding a required property to the
contract therefore forces a decision about who supplies it, rather than
producing an input nobody asks for or a field nobody fills.

## What will be accepted

The accepted format is read from the schema at run time. It is not restated
here or in the module, because a restated constraint is a second copy of it,
and the copy is the one that goes stale: the schema tightens, the prompt keeps
accepting, and the rejection arrives later from the validator with less
context to act on.

Two refusals are applied before the schema is consulted, because the schema
would accept both.

A value carrying credential material is refused outright. A connection string
is a perfectly valid string, so nothing in the schema would stop one. Nothing
is collected in plain text that a secret could hide in.

A value shaped like a directory identifier is refused for
`subscription-reference`. The `externalReferenceName` pattern admits any
lowercase hyphenated string, and a subscription identifier beginning with a
letter is a lowercase hyphenated string. The reference exists to keep the
identifier out of a committed file, so the prompt enforces what the pattern
cannot.

## What a rejection says, and what it never says

A rejection names the input, why the value was not accepted, and the expected
format. It never repeats the value.

This is the one place where the most helpful possible message is the wrong
one. `'AccountKey=...' is not a valid reference name` is maximally actionable
and is also how a credential reaches a terminal scrollback, a screen
recording, and the issue somebody pastes it into. SEC-017 resolves it in
favour of the format: every fragment of a rejection is either schema content
or the text on this page, and the supplied value is not passed to the function
that builds the message at all.

The same applies to identifier-bearing fields, not only secret-bearing ones. A
rejected subscription identifier is as unwelcome in a log as a rejected key.

## When the value is still wrong

A wrong answer is explained and asked again, up to three times, after which
collection stops rather than asking forever.

End of input is not treated as a wrong answer. A loop that re-prompts when the
stream is exhausted spins forever the first time it runs with anything other
than a person on the other end, which is every automated run.

## Related

- [Scope contract](scope-contract.md), the artifact these inputs feed.
- [Non-interactive runs](non-interactive.md), which answers the same questions
  from a file and from `--set` instead of a prompt.
- [Discovery](../wizard/discovery/README.md), which supplies the selection the
  inputs do not cover.

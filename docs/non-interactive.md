# Non-interactive runs and `--set` parity

The guided step has two modes and one output. Interactive execution asks the
questions; non-interactive execution reads the answers from a file and from
arguments. With equivalent inputs both modes emit the same bytes.

Run `python -m zeroops.guided --explain` to print the settable inputs and the
fields a configuration must supply.

## The two commands

Interactive, asking for anything the configuration does not already answer:

```text
python -m zeroops.guided --config selection.json --out scope-contract.json
```

Non-interactive, driven entirely by a file:

```text
python -m zeroops.guided --non-interactive --config scope-contract.json --out scope-contract.json
```

A non-interactive run never prompts. When an answer is missing it stops and
names the input, rather than blocking on a terminal that is not there.

## Settable inputs

Every interactive prompt has one `--set` key, and the keys are computed from
the prompts. A prompt without a key is not expressible.

| `--set` key | Contract field |
|---|---|
| `subscription-reference` | `subscriptionRef` |
| `observation-start` | `observationPeriod/start` |
| `observation-end` | `observationPeriod/end` |
| `max-tool-calls` | `executionLimits/maxToolCalls` |
| `max-wall-clock-seconds` | `executionLimits/maxWallClockSeconds` |
| `max-result-set-rows` | `executionLimits/maxResultSetRows` |
| `per-query-timeout-seconds` | `executionLimits/perQueryTimeoutSeconds` |

Example:

```text
python -m zeroops.guided --non-interactive --config selection.json \
  --set subscription-reference=sub-one \
  --set max-tool-calls=10
```

A key set twice is refused. Which value won would depend on argument order,
and a run whose outcome depends on argument order is not reproducible.

## Supplied by the configuration

These are required contract fields that no prompt asks for. They come from the
discovery stage that produced the selection.

| Field | Where it comes from |
|---|---|
| `inScope` | the discovery selection |
| `outOfScope` | the discovery selection |
| `generatedAgainst` | the marker for the discovery run the selection was taken against |
| `generatedAt` | the moment the contract was emitted, reused when the configuration records one |

Two further fields are never supplied by anyone. `schemaVersion` is pinned by
the emitter, and `canonicalHash` is computed over the finished document.
Setting either in a configuration has no effect.

## The emitted contract is a configuration

A scope contract carries every value needed to rebuild itself, so a previously
emitted contract is a valid `--config` input and needs no `--set` arguments at
all. Re-running against it reproduces the same bytes, including the recorded
`generatedAt`.

This is what makes the committed artifact the product. The approved scope is
reproducible from the file alone, without the session that produced it.

## What "identical" means

Identical is defined by the serialization rules ADR-0004 pins:

| Rule | Value |
|---|---|
| Unicode normalisation | NFC, applied before canonicalisation |
| Canonicalisation | RFC 8785 |
| Line endings | LF |

Normalisation applies to the emitted document, not only to the digest. Without
that, a name containing an accent typed on a platform that produces decomposed
forms emits different bytes from the same name typed elsewhere, while both
files carry the same hash and both validate.

The clock is an input. A run against a configuration that records no
`generatedAt` is starting a new run rather than reproducing an earlier one, and
its output differs accordingly. That is the intended behaviour, not a parity
failure.

## Precedence

1. `--set`, the deliberate deviation
2. `--config`, the committed baseline
3. The prompt, in interactive mode only

## Rejections

Every value is checked by the same code regardless of where it came from, so a
configuration cannot accept what a prompt refuses. A rejection names the input
and the expected format and **never repeats the value**, because an argument
already reaches shell history and CI logs, and quoting it in the rejection
copies it into the build output as well.

An argument that is not written `key=value` is refused without being quoted at
all. There is no `=` to split on, so there is no part of it that is safely
only a key.

## Related

- [Guided inputs](guided-inputs.md), the questions themselves
- ADR-0003, the guided deployment experience
- ADR-0004, the serialization rules

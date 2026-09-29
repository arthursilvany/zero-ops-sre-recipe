# Discovery output

Guided setup writes what it found to a file before you choose anything from it. ADR-0003 wants that file reviewable and diffable on its own, separately from the selection made out of it, and it is the right call: a proposal you cannot read before accepting is not a proposal.

It is also the one artifact in this framework that holds a subscription-wide list of real resource identifiers, real resource names and real resource-group names. Three things follow from that, and they are the subject of this page (SEC-007).

## It is ignored by default

The default path is `.zeroops/discovery.json`, and `.gitignore` covers both `.zeroops/` and `*.discovery.json`.

An ignore rule protects a path something writes to. So the default is published by the code that writes it, and the test that asks git whether the default is ignored asks about that published value rather than about a path typed into a test. Change the default without changing the rule and the test fails.

Writing an unredacted document to a path git does not ignore is refused. The refusal happens before the file is opened, so a rejected document is never on disk. A caller that genuinely wants an unprotected path says so in the call:

```python
discovery_output.write(document, path=somewhere, acknowledge_unignored=True)
```

That is deliberately awkward. It leaves the decision in the source rather than in somebody's shell history.

Two cases read as unprotected: a path no rule covers, and a directory that is not a git repository at all. In the second case the protection cannot be confirmed, and an unconfirmed protection carries the same risk as a missing one.

## It says what it is, at the top

The first key in the file is `warning`, before the inventory, because a warning below a thousand rows is not a warning.

The header is stamped by the writer from what the document turned out to be, not from what the caller called it. Set it by hand and it is overwritten. This matters in one direction only: a file that claims to be redacted and is not is the file somebody attaches to a public issue without reading it.

## There is a redaction mode for bug reports

```text
python -m zeroops.discovery_output --redact .zeroops/discovery.json
```

This writes `.zeroops/discovery.redacted.json` next to the original and leaves the original untouched. Attach the redacted copy.

### What survives

Two fields keep their value: `type` and `location`. Both are chosen by Azure from a published set and name a category rather than an instance, so neither identifies anybody. Booleans survive for the same reason.

Every other string becomes a salted pseudonym of the form `redacted-<twelve hex characters>`.

The list is an allow-list, and the direction is the control. Under a denylist, the next field added to the query projection would travel into bug reports untouched, and nothing would say so. Under an allow-list a forgotten field is redacted rather than leaked, and the verifier can then decide structurally whether anything unredacted remains rather than guessing from shape. That distinction matters more than it sounds: a resource named after the team that owns it is an identifier and matches no pattern at all.

### What the pseudonyms preserve

Equal values produce equal tokens inside one file. Two resources in the same resource group still visibly share one, so a redacted inventory can still be reasoned about.

The salt is generated per run and never written down. Tokens in two files therefore cannot be lined up against each other, and a token cannot be walked back to a short name by trying candidates. Redacting the same file twice is refused for the same reason: the second pass would produce different tokens and lose the joins the first one preserved.

### What is checked before it is written

A document claiming to be redacted is verified, and nothing is written when the verification reports. Two independent checks run, because either one alone passes the case the other exists for:

| Check | Catches | Misses |
|---|---|---|
| Structural: every string is a pseudonym, a preserved field, or framework envelope text | A field added to the projection that redaction never learned about, whatever its value looks like | Nothing in its own terms, but it depends on the allow-list being honest about the fields it preserves |
| Shape: no string holds a value shaped like an identifier | A value that leaked through a preserved field, for instance a region column carrying something else | A name that looks like an ordinary word |

An example of what the shape check looks for, written here as placeholders because this page is tracked and the artifact it describes is not: an identifier such as `<SUBSCRIPTION_ID>`, an address like `00000000-0000-0000-0000-000000000000`, a resource path, an electronic mail address, or a long hexadecimal run.

## Denials travel with the output

A result with a withheld portion is exactly the one worth writing down, so the denials are in the same file as the rows, under `denials`, with `complete` set to false. A reader who sees the inventory sees what is missing from it in the same place.

Denials keep their values through redaction. They name a catalogued query identifier and an Azure action string, both authored by this framework, and neither says anything about the tenant.

See also [`permissions.md`](permissions.md) and [`../wizard/discovery/README.md`](../wizard/discovery/README.md).

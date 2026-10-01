# The read-only command broker

Every Azure invocation issued by the core and the wizard passes through one
function in `tools/zeroops/broker.py`. This page exists so the allow-list is
reviewable without reading Python, and so the reasons for each entry survive
the people who wrote them.

The broker is defence in depth. The read-only guarantee is the role
assignment enforced by Azure Resource Manager. A bug in the broker is a bug
in a second layer, not the failure of the first.

## Allowed verbs

A verb is the last word before the first option. In
`az role assignment list --scope /subscriptions/...` the verb is `list`.

| Verb | Why it is allowed |
|------|-------------------|
| `show` | Read one resource by identifier. No side effect. |
| `list` | Enumerate resources in a scope. No side effect. |
| `query` | Resource Graph read, the discovery mechanism ADR-0003 chose. |
| `version` | Record the CLI version in evidence. Touches no subscription. |
| `rest` | One GET to Azure Resource Manager, in the single shape described below. |

Anything else is refused, including verbs nobody has classified. The refusal
is decided by this list and never by a list of write verbs. A deny-list would
permit every verb nobody thought of, and that set is the one worth worrying
about.

There is a separate list of write verbs. It never decides anything. It exists
so a refusal can say that `delete` changes state rather than only that it is
unrecognised.

## What else the broker refuses

| Refused | Reason |
|---------|--------|
| A command given as a string | Splitting it would put another shell's quoting rules inside this process. |
| An empty token | Usually an interpolated value that did not exist. |
| A token containing `;`, `&`, <code>&#124;</code>, `` ` ``, `$(`, `>`, `<`, a newline or a NUL | No resource identifier contains one, and each is how a token stops being one token. Query values are the exception, below. |
| A program other than `az`, including an absolute path to it | A path is how a call site reaches a different binary while still looking brokered. |
| `--yes`, `-y`, `--force`, `--no-wait` | A confirmation flag exists because something is about to change. |

## Query values are payload, not structure

A Resource Graph query is built on <code>&#124;</code>. Under the rule above no query could ever be issued, and the one caller that most needs the choke point would have to reach past it. Loosening the rule for every token instead would be worse again, so the loosening is named and bounded.

`VALUE_BEARING_FLAGS` lists the flags whose following value is data rather than command structure. Today that is `--graph-query` and its short form `-q`, and both spellings are covered: the value in the next token, and the value joined with `=`.

A payload token is still refused if it contains a newline, a carriage return or a NUL. A line break can end an argument early in some argv encodings, and it splits in two the line of evidence that records the query. Catalogued queries are therefore written on a single line.

What makes this safe is not that the value is trusted. It is that the broker runs the list through `subprocess` with `shell=False`, so a payload token is one argument and no shell ever parses it. The structural rule stays in force for every token that decides what the command *is*.

The exemption is a registry rather than a heuristic. A heuristic that guessed which tokens were data would eventually guess that a structural one was. Following *some* flag is not enough; the flag has to be listed, with the reason beside it.

## `az rest` is admitted in one shape

`az rest` can write: its method is a parameter. Discovery needs it for one read that Resource Graph cannot answer, which is the list of actions the identity holds at the subscription. So it is allowed only as:

```text
az rest --method get --url /subscriptions/<id>/...
```

`REST_FLAGS` in `tools/zeroops/broker.py` is the complete list of flags that may follow the verb, each with its reason, and each may appear once.

| Refused | Reason |
|---------|--------|
| A missing `--method`, or any method other than `get` | Any other method can change state. An absent one leaves the choice to the CLI default, which a future CLI could change. |
| A `--url` that does not begin with a single `/` | The CLI prefixes a path with the current cloud's ARM endpoint. A full URL could send the caller's token elsewhere. |
| Any other flag, including `--body`, `--headers`, `--resource`, short forms and `--flag=value` spellings | Refused because they are absent from the list, not because each one was recognised. |

The URL is structure, not payload, so the metacharacter rule above applies to it in full.

## What the broker adds

`--output json` unless the caller named a format, because evidence is
compared across runs and platforms and the format cannot depend on a local
configuration file.

`--only-show-errors`, because upgrade notices and deprecation warnings land
on stderr, end up inside captured evidence, and read as failures.

## Adding a verb

1. Confirm the verb cannot change state. If the documentation is ambiguous,
   it changes state.
2. Add it to `READ_ONLY_VERBS` in `tools/zeroops/broker.py` with a reason
   that says something. A test asserts the reason is not a placeholder.
3. Add it to `EXPECTED_VERBS` in `tests/unit/test_broker.py`. The two lists
   are stated separately on purpose: deriving one from the other would make
   them agree no matter what either said.
4. Add the row to the table above.

## Bypassing the broker

Calling Azure from a declared core path without going through this module
fails the build. The check is part of `zeroops check-core`, which CI already
runs on both platforms, and it applies two rules.

**No core path may invoke anything.** Not the Azure CLI, not an SDK, not a
shell. The rule is about the capability to invoke rather than about
recognising Azure, because a list of ways to reach Azure is a list somebody
has to keep complete, and the day it is not is the day the check passes for
the wrong reason. `subprocess` in a core path is a finding whether or not the
command it runs looks like Azure.

**A brokered command may name only an allowed verb.** The broker refuses at
runtime, but a wizard that only fails when someone runs it has already
shipped. A command written as a literal list is readable in the source, so it
is read there too. A command assembled at runtime is not readable, and the
check says nothing about it rather than guessing; the first rule is what
covers that case, because a core path has no way to run what it assembled.

The binding layer is not exempt. It names the runtime, which is why it
exists, and that is not a licence to invoke it.

`tools/` is not scanned. It holds the broker, which is the one place allowed
to invoke, and scanning it would make the rule unsatisfiable.

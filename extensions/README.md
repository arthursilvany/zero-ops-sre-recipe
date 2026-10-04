# Consumer extension skills

Place consumer-authored Markdown skills in this directory or a subdirectory. The
`zeroops lint-skills` command inspects Markdown files under `extensions/` and skips
`README.md` files. It needs no Azure access, credentials or network connection.

Each skill should provide four non-empty guidance sections:

| Heading | Guidance |
|---|---|
| `When to use` | State the condition that makes the skill relevant. |
| `What to check` | Name the evidence or checks the agent should examine. |
| `When not to use` | Define the boundary where the skill does not apply. |
| `Common mistake` | Name a specific reasoning or operational mistake to avoid. |

The linter also accepts the heading alternatives `When this skill applies` or `When it
applies`, `Checks` or `What to inspect`, `When this does not apply` or `Out of scope`,
and `Mistake to avoid` or `Pitfall`.

The check is heuristic: it verifies that each guidance section has a heading and
non-placeholder text outside fenced code examples and HTML comments. It does not judge whether the advice
is correct or useful. Findings are warnings in v1 and do not fail the command; review the
skill before it reaches an agent. The check never prints skill content.

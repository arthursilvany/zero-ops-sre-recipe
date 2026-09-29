# Agent boundaries and prohibited actions

This page is for the person who operates a deployed agent. It states what the
agent may reach and what it must not do, in the same terms the tool policy
uses, so the two cannot drift apart without the build failing.

## This page is not the guarantee

The read-only guarantee is the RBAC grant Azure Resource Manager enforces on
the agent's identity. The tool policy in `core/policy/tool-policy.json` is
defence in depth, and this page describes that policy.

That distinction matters when you are deciding whether to trust the agent with
a subscription. If the RBAC grant is wrong, nothing on this page holds. Check
the grant first, and treat this page as a description of the second layer
rather than the first.

For the same reason, the policy is **declared, not runtime-verified**. The
framework cannot observe the runtime enforcing it. The post-deployment
tool-policy-posture check reports the limits the runtime actually holds and
fails on a mismatch, which is the only place the declaration meets reality.

## What the agent must not do

Every row here is a deny rule in the tool policy. Removing a rule without
removing its row, or the reverse, fails `zeroops check-core`.

| Policy category | What is prohibited | What to do instead |
|---|---|---|
| `write` | Changing any resource, configuration or tag. The agent observes and never mutates. | Apply the change yourself through your normal deployment path. The agent's finding names the resource and the observation; it is an input to your change, not the change. |
| `destructiveOperation` | Deleting, scaling, restarting, failing over or stopping anything. | Act on the finding through the runbook your team already uses for that operation, so the action is recorded where your on-call expects to find it. |
| `arbitraryExecution` | Running a command or a query composed at run time. Only a reviewed, catalogued query runs. | Add the query you need to the catalogue and have it reviewed. A query nobody read is a query nobody can vouch for after an incident. |
| `secretsAccess` | Reading a credential, key, connection string or certificate. | Reference the secret externally and let the agent identity resolve it. If a task appears to need the value itself, that task belongs outside the agent. |
| `selfApproval` | Approving its own proposal. One principal must not both propose and authorise. | Route the proposal to a second principal. The approval ledger records the separation, and an approval from the proposing identity is rejected rather than logged. |
| `externalPublication` | Sending a finding anywhere outside the environment it observed. | Read findings from inside the environment. Exporting one turns an observation about a customer estate into a disclosure, and that decision is yours to make deliberately. |
| `agentCreatedSchedule` | Creating recurring or deferred work of its own. | Schedule the run yourself. A schedule the agent authored would outlive the execution that was reviewed, and nothing would be reviewing the runs that followed. |

## What the agent may reach

Every row here is a capability class the tool policy allows. The policy
denies by default, so a capability absent from this table is one the agent
cannot use.

| Capability class | What it reaches | Where it stops |
|---|---|---|
| `readResourceMetadata` | Resource names, types, locations, tags and relationships. | It reads the inventory and cannot alter any part of it, including tags. |
| `readResourceConfiguration` | The settings a resource currently holds. | Configuration is read as declared. Values a provider marks as secret are not returned, and are denied separately under `secretsAccess`. |
| `readMetrics` | Platform and custom metric series. | Aggregated series only, bounded by the declared result-row limit. It does not emit metrics or create alert rules. |
| `readLogs` | Log records through catalogued queries. | Only queries in the catalogue run. Retrieved records are hashed into the evidence manifest rather than stored in it. |
| `readAlerts` | Alert instances and their state. | It reads alert state and does not acknowledge, close, suppress or create an alert. |
| `readCostData` | Cost and usage data for the scope it was granted. | Reporting only. It does not change budgets, reservations or commitments. |
| `runCataloguedQuery` | The reviewed queries shipped with the framework or added by your team. | The catalogue is the whole surface. Nothing composes a new query at run time, which is what `arbitraryExecution` denies. |

## Execution limits

These are ceilings, not the values your deployment necessarily holds. A
consumer policy may narrow any of them and may not widen one.

| Limit | Ceiling |
|---|---|
| Tool calls per execution | 200 |
| Wall clock per execution | 900 seconds |
| Rows per result set | 1000 |
| Timeout per query | 60 seconds |
| Retry attempts | 3 |

Enforcement of these limits belongs to the agent runtime. The framework
declares them and the posture check compares them against what the runtime
reports.

## If the agent did something on this list

Treat it as a security incident rather than a bug, and follow
[`SECURITY.md`](../SECURITY.md). A prohibited action that happened is evidence
that either the RBAC grant or the runtime's policy enforcement is not what
this page assumes, and both are larger problems than the action itself.

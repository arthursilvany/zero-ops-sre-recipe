# Lab Validation Record, 2026-10-03

This record documents a validation run of the recipe's assumptions against a live Azure SRE
Agent and a laboratory workload. The run exercised the runtime directly, because the
framework commands that will automate it (`verify`, the canary of T5.10 and the connector
probe of T5.09) are not implemented yet. Every value below was observed and recorded during
the run; names carry a `<suffix>` placeholder and no subscription, tenant or endpoint value is
included.

## Summary

| Item | Result |
|---|---|
| Healthy investigation (health01) | Completed, classified HEALTHY, 30 read-only CLI calls, sentinel on its own line |
| Fault investigation (fault01) | Root cause identified correctly, then stalled on an on-behalf-of authorization request |
| Workload restored | Yes, confirmed by configuration read-back, metrics and HTTP probes |
| Alert behaviour | `alert-http-5xx-sre-lab` fired and resolved; the agent concluded it had not fired |
| New failure classes exercised live | `awaitingApproval` observed; `connectorNotVisibleToAgent` symptoms observed |
| Changes outside the laboratory resource group | None |

## Environment

| Component | Resource | Notes |
|---|---|---|
| Resource group | `rg-sre-lab` | The only scope changed |
| Agent | `zero-ops-sre-recipe` (`Microsoft.App/agents`) | Mode `review`, access level `Low`, no connectors, empty `managedResources` |
| Agent identity | user-assigned identity of the agent | Holds Monitoring Contributor at resource group scope and no explicit reader role |
| API workload | `ca-grubify-<suffix>` (Container App) | Port 8080, revision `--0000002`, one replica |
| Frontend workload | `ca-grubify-fe-<suffix>` (Container App) | Port 80 |
| Telemetry | Log Analytics `law-<suffix>`, Application Insights `appi-<suffix>` | Not connected to the agent |
| Alert | `alert-http-5xx-sre-lab` | More than five 5xx requests in five minutes, evaluated every minute, severity 3 |
| Action group | `ag-sre-lab-sre-lab` | No receivers, so firing notifies nobody |

## Method

Each investigation used a temporary HTTP trigger on the agent data plane, created and deleted
by the run:

1. Create the trigger with the instruction in `agentPrompt` and `agentMode` set to `review`.
2. Read the trigger back and refuse to fire when the stored instruction is shorter than
   expected. An empty stored instruction was accepted by the runtime in the ADR-0007 lab.
3. Fire the trigger. The runtime answers `202 Accepted`, which is not treated as a result.
4. Resolve the run. The trigger read-back never exposed a thread identifier in either run, so
   the thread was found in the agent thread list by its title, `HTTP Trigger: <trigger name>`.
5. Poll the thread messages and require the sentinel as a line of its own in a message that
   is not the echoed instruction.
6. Delete the trigger in a `finally` block, whatever the outcome.

The data plane is reached with a token for the `https://azuresre.dev` audience. An Azure
Resource Manager token is refused with 401 on the fire call.

## Scenario 1: healthy investigation

| Field | Value |
|---|---|
| Objective | Confirm the agent can complete a read-only health investigation end to end |
| Prerequisites | Workload healthy; baseline probes recorded before the run |
| Code revision | `acc09c1` |
| Command | Temporary trigger `zo-health01`; the instruction asks for status, replicas, restarts, requests by status class, memory, console errors and alert state over 60 minutes |
| Affected resource | None changed; reads only |
| Expected result | A classified health report with the command behind each value, ending with the sentinel |
| Actual result | HEALTHY. Create 201, read-back 200 with the stored instruction intact, fire 202, delete 200. The thread completed in about four minutes |
| Telemetry | API requests 2xx: 2, 4xx: 3, 5xx: 0; frontend 2xx: 1. These match the baseline probes sent before the run exactly (two data endpoints, three unknown paths) |
| Agent finding | 30 Azure CLI calls, all reads (`containerapp replica list`, `monitor metrics list`, `monitor activity-log list`, `monitor metrics alert show`). It reported that a time-bounded console log query could not run because no Log Analytics tool was available |
| Recovery | Not applicable |

Two observations from this run:

- The agent performed one web search to do arithmetic. A read-only agent sending any value
  outside the tenant is a data path the tool policy should declare.
- The missing Log Analytics tool is the symptom FR-75 describes: the workspace exists, but the
  agent holds no connector to it, so log evidence is absent by construction.

## Scenario 2: bounded ingress fault

| Field | Value |
|---|---|
| Objective | Confirm the agent can explain a short, real outage from telemetry and the control plane |
| Prerequisites | API answered 200 immediately before the fault |
| Code revision | `acc09c1` |
| Fault | `az containerapp ingress update --target-port 8081` on the API app, which points ingress at a port nothing listens on. No new revision is created |
| Load | 12 requests, three seconds apart, against a data endpoint |
| Fault window | 13:07:48 to 13:09:39 UTC (about two minutes) |
| Restore | `az containerapp ingress update --target-port 8080` |
| Expected result | 503 for every request during the fault; 200 after restore; the alert fires |
| Actual result | 12 of 12 requests returned 503. After restore, 5 of 5 returned 200 |
| Telemetry | Requests metric recorded 12 responses in the 5xx class (1 at 13:09, 11 at 13:10). The alert fired at 13:12:29 UTC and later resolved |
| Agent finding | Temporary trigger `zo-fault01`, given only the symptom. From the Activity Log and configuration it found that `targetPort` changed from 8080 to 8081 at 13:08:57 UTC and back at 13:10:47 UTC, and that no revision or restart was involved. This is the correct root cause |
| Agent failure | Its eleventh call named the API app with a mistyped resource name. The runtime answered with an authorization request (`PendingAuthorization`) to act with the caller's identity, and the thread stopped there. The thread itself reported no wait reason. The request was not approved, because approving would lend a human identity to a read-only agent |
| Alert reasoning | Reasoning at 13:15, the agent concluded the alert had not fired. The alert instance started at 13:12:29, so the conclusion was wrong when it was drawn |
| Recovery | Port 8080, latest ready revision unchanged (`--0000002`), running status Running, restart count 0, no 5xx after restore, API and frontend both 200 |

## Findings mapped to requirements

| Finding | Requirement | Consequence for the recipe |
|---|---|---|
| A fire call answers 202 whether or not a run follows; the trigger never exposes its thread | FR-76 | The canary must resolve the run independently and fail when it cannot. Matching the sentinel anywhere in the thread is a false pass, because the first message echoes the instruction including the sentinel. The validation helper itself produced this false pass before it was corrected |
| A read on a resource the identity cannot see becomes an on-behalf-of request that waits with no wait reason | FR-77, `awaitingApproval` | Detection must read the tool call status (`PendingAuthorization`) in the messages, not the thread state. The class is not retryable: the same call produces the same request |
| No Log Analytics connector, so log evidence is impossible | FR-75, `connectorNotVisibleToAgent` | Provisioned telemetry is not usable telemetry; the probe must run through the agent |
| The agent identity holds Monitoring Contributor and no explicit reader role | ADR-0007, NEG-A | A write-capable role on a read-only agent. Changing it is a role assignment change reserved to the owner |
| The agent concluded the alert had not fired while the alert instance existed | FR-81 | Observed conclusions must cite evidence from the execution window; an absence claim needs the query that would have shown presence |
| The agent used web search for arithmetic | Tool policy, `externalPublication` | Any egress from a read-only investigation is a data path to declare and, by default, refuse |

## Reproducing the scenarios

Prerequisites: a laboratory resource group with the Grubify sample, an SRE Agent with access
to that resource group, a signed-in Azure CLI account holding the agent administrator role,
and PowerShell 7.

1. Record a baseline: request the frontend root and the API data endpoints, and read
   `RestartCount`, `Replicas` and `Requests` for the API app.
2. Run the healthy investigation through a temporary trigger following the method above.
3. Inject the fault with the target port change, send a bounded number of requests, and
   restore the port within a few minutes.
4. Wait two minutes for metric ingestion, then run the fault investigation with a prompt that
   states only the symptom and the window.
5. Confirm restoration with the configuration read-back, metrics and HTTP probes listed in the
   scenario record.

## Cleanup

| Item | State after the run |
|---|---|
| Temporary triggers `zo-health01`, `zo-fault01` | Deleted, 200 on delete |
| API ingress target port | Restored to 8080 |
| Agent threads | Retained in the agent as investigation history; the stalled fault thread holds an unapproved authorization request and should stay unapproved |
| Laboratory resources | Unchanged apart from the reverted ingress setting |

## Owner decision addendum, 2026-10-03

This addendum records decisions made after the validation above. It does not change the
original observations or treat them as new measurements.

| Decision | Owner disposition |
|---|---|
| Log Analytics connector | The owner reports that the connector was added to the SRE Agent. This is owner-reported configuration, not verified functional evidence. The agent must execute a successful query before connector usability is confirmed. |
| Agent identity permission | The owner accepts retaining the current elevated permission in this lab until project testing is complete. The observed assignment remains recorded above as Monitoring Contributor; no role change was measured or is implied by this decision. This temporary lab exception does not authorize an RBAC change. |
| Recipe security invariant | The recipe remains read-only. NEG-A and the read-only role allow-list remain unchanged. This exception is not evidence of least-privilege compliance. |
| Handoff schema | The owner accepts handoff schema version 1.1.0. |
| ADR-0007 | The owner confirmed reviewed and approved. Repository guidance still requires review by at least one other team member before the ADR can be marked Accepted. |

## Functional connector follow-up, 2026-10-03

Actual agent tool execution now proves Log Analytics query authorization for the laboratory
workspace. The aggregate returned no matching rows; this does not establish dataset
availability or ingestion health. The baseline and owner decisions above remain historical.

| Evidence | Observed result |
|---|---|
| Agent and scope | `zero-ops-sre-recipe`, restricted to `rg-sre-lab`, workspace `law-<suffix>` and API `ca-grubify-<suffix>` |
| Temporary trigger | One uniquely named trigger; create 201, read-back 200, stored prompt exactly matched all 1,878 characters, mode `review`, fire 202 at 16:02:48.6437363 UTC |
| Actual query tool | `system-mcp-monitor_monitor_workspace_log_query`, server `system-mcp-monitor`, status `Completed`, no tool error |
| Execution window | Started 16:03:14.6453363 UTC, completed 16:03:19.4007506 UTC |
| Target verification | Tool parameters contained `resource-group=rg-sre-lab`; subscription matched the explicit lab subscription and workspace matched `properties.customerId` from an ARM GET of the named workspace inside this group |
| Query parameters | `subscription=<subscription-id>`, `workspace=<workspace-id>`, `table=ContainerAppConsoleLogs_CL`, `hours=1`, `limit=1`; KQL itself restricts data to the last 30 minutes and the exact API name |
| Tool result | `{"status":200,"message":"Success","results":[{"Rows":"0","Latest":"null"}],"duration":0}` |
| Completion | Unique own-line sentinel in the final agent response at 16:03:32.8983972 UTC, excluding the instruction echo |
| Cleanup | Delete 200 and subsequent GET 404 for the same temporary trigger; no trigger remains |
| Frontend HTTP probe | Existing ingress root returned 200 at 16:05:39.4750757 UTC; resource running status `Running` |
| API HTTP probe | Existing ingress root returned 404 at 16:05:38.0968490 UTC; resource running status `Running`. Root is not established as a health route, so API health is not claimed |

The exact executed KQL below uses only the resource-name placeholder in this committed copy.
Local verification compared the actual command to the requested exact laboratory API name:

```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated >= ago(30m)
| where ContainerAppName_s == "ca-grubify-<suffix>"
| summarize Rows=count(), Latest=max(TimeGenerated)
```

### Evidence qualifications

- The prompt requested `ListConnectors` before the query. The run exposed one MCP execution,
  the successful workspace query; no separate agent `ListConnectors` execution was observed.
  A subsequent connector-list GET returned 200. Listing is not the basis for the pass.
- The session harness initially matched the literal `PendingAuthorization` in the echoed
  instruction and deleted the trigger early. Inspection of the actual structured execution
  status found no authorization request. The already-started run continued, completed the
  query and emitted its final sentinel. Deleting a trigger does not cancel an existing run.
  The local detector now examines status fields rather than searching instruction text.
- No second trigger, approval, caller-identity delegation, connector change, workload fault,
  web search, RBAC change or boundary change was performed. The inspected run contained only
  the query tool execution; all ARM reads targeted named resources inside `rg-sre-lab`.
- Sanitized session evidence records the actual tool parameters, result, timings, target
  equality checks, completion and cleanup. No raw console logs or credentials are persisted
  in the repository.
- Issue 167 meets its functional-access criterion and can close as completed. Issue 166
  remains the deferred elevated-role remediation; this query does not demonstrate least
  privilege. Issue 168 remains the independent-review blocker. ADR-0007 stays `Proposed`;
  handoff schema 1.1.0 remains approved.
- Live framework commands remain unimplemented. This bounded runtime validation does not
  constitute project completion or a full security review.

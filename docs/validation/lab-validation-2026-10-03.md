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

# Agent Role Assignments

**Status**: Proposed
**Date**: 2026-10-02
**Depends on**: [0001 Upstream Template Relationship](0001-upstream-template-relationship.md),
[0002 Infrastructure as Code](0002-infrastructure-as-code.md)
**Implements**: FR-33, SEC-001, SEC-003, CC-009
**Blocks**: T5.01 (Bicep composition), and through it T5.03, T5.05, T5.06, T5.07, T5.08

## Context

The recipe deploys a read-only agent. FR-33 requires every role definition in the
compiled deployment output to resolve to the read-only allow-list, and NEG-A (T5.04)
enforces that offline. The composition must also never re-author or patch upstream
(ADR-0001, ADR-0002), which T5.02 enforces by refusing any Bicep declaration of a
resource type the pinned upstream creates, `Microsoft.Authorization/roleAssignments`
included.

The pinned upstream (commit `53e7b66`, `sreagent-templates/bicep/`) grants the
following. Line numbers refer to that commit.

| Grant | Principal | Role | Gated by | Source |
|---|---|---|---|---|
| `targetRbac` | User-assigned identity | Reader, Log Analytics Reader, Contributor | `!skipRoleAssignments && empty(existingManagedIdentityId)`; Contributor additionally `accessLevel == 'High'` | `agent-core.bicep` line 101, `role-assignments-target.bicep` |
| `monitoringReader` | User-assigned identity | Monitoring Reader | `!skipRoleAssignments && empty(existingManagedIdentityId)` | `agent-core.bicep` line 112 |
| `targetRbacSystemMi` | Agent system-assigned identity | Reader, Log Analytics Reader, Contributor | **No gate.** Contributor only `accessLevel == 'High'` | `agent-core.bicep` lines 183 to 190 |
| `adminRole` | The deploying principal | SRE Agent Administrator | `!skipRoleAssignments` | `agent-core.bicep` line 194 |
| `uamiAdminRole` | User-assigned identity | SRE Agent Administrator | `!skipRoleAssignments` | `agent-core.bicep` line 206 |

`accessLevel` defaults to `Low` (`main.bicep` line 41). SRE Agent Administrator was
measured live: it carries write, delete and secret listing on the agent resource itself.

Compiling the real upstream `main.bicep` and auditing it with `zeroops audit-roles`
produces five findings: three for SRE Agent Administrator and two for Contributor.

Two facts make this a decision rather than a parameter choice:

1. **NEG-A ignores `condition`.** An offline audit cannot see deployment parameter
   values, so a conditional Contributor counts the same as an unconditional one. No
   parameter combination makes the compiled upstream output pass NEG-A as it stands.
2. **`skipRoleAssignments` does not reach `targetRbacSystemMi`.** Skipping removes the
   administrator grants and the user-assigned identity grants, and it also removes the
   read grants the recipe needs. The system identity's grants, including the conditional
   Contributor, stay.

## Priorities and Requirements (ordered)

1. **Agent principals hold read-only roles only.** This covers both the user-assigned
   identity and the system-assigned identity, at every scope the deployment touches.
   It is the product's central claim (FR-33, SEC-001). An agent that can modify itself or
   a workload is not the product.
2. **Upstream is composed, never re-authored or patched.** ADR-0001, ADR-0002 and
   CON-12. Patching would turn every pin bump into a merge and break the provenance the
   lock establishes.
3. **The read-only claim is verifiable offline and fails closed.** CC-009 requires a
   credential-free check before anything is deployed. A check that trusts a parameter it
   cannot see is not evidence.
4. **A pin bump stays cheap.** Upstream is preview-era software and will move. Each
   bump should mean re-measuring and re-running gates, not re-designing.
5. **A human can administer the agent after deployment.** Some principal needs SRE Agent
   Administrator to operate the agent. That principal must be a person or an operations
   group, never the agent's own identity.

## Options Considered

The conductor derived these options from the upstream evidence above. They need the
decision owner's confirmation, and owners may add options.

### Option 1: Compose upstream as-is and accept its grants as documented exceptions

Deploy `main.bicep` with `accessLevel = 'Low'`. Add SRE Agent Administrator and
Contributor to the allow-list as accepted exceptions, with reasons.

**Evaluation against priorities**:

- **Read-only principals**: Fails. `uamiAdminRole` gives the agent's own identity write
  and delete on itself and secret listing. Accepting Contributor relies on a parameter
  value that nothing offline confirms.
- **Compose, never re-author**: Meets.
- **Offline verifiability**: Fails. The allow-list would vouch for write-capable roles,
  which removes the meaning of NEG-A.
- **Cheap pin bump**: Meets.
- **Human administration**: Meets, through `adminRole`.

### Option 2: Make NEG-A condition-aware for literal bindings, and compose upstream with role assignments enabled

Extend NEG-A so a grant whose `condition` is **provably false** under literal parameter
values bound in the committed composition is excluded. Anything not provably false still
counts, so the audit still fails closed. Compose with `accessLevel = 'Low'` bound as a
literal.

**Evaluation against priorities**:

- **Read-only principals**: Partially meets. Both Contributor grants become provably
  false. `uamiAdminRole` stays, because its condition is true whenever role assignments
  are enabled, so the agent identity still administers itself.
- **Compose, never re-author**: Meets.
- **Offline verifiability**: Meets for what it excludes. It adds a small evaluator for
  `not`, `equals`, `and`, `or`, `empty` and parameter references across nested
  deployments. Anything outside that grammar stays a finding.
- **Cheap pin bump**: Meets while upstream keeps the same gating shape.
- **Human administration**: Meets, through `adminRole`.

### Option 3: Condition-aware NEG-A, skip upstream role assignments, author the read-only grants in the composition

As in Option 2, NEG-A becomes condition-aware. The composition binds
`skipRoleAssignments = true` and `accessLevel = 'Low'` as literals. It then declares only
Reader, Monitoring Reader and Log Analytics Reader for the user-assigned identity, on the
declared scopes, in `deploy/compose/`. `Microsoft.Authorization/roleAssignments` gets a
reviewed exception in the T5.02 anti-duplication check, limited to role definitions
present in the read-only allow-list. SRE Agent Administrator goes to a named human
principal or group through a documented post-deployment step that the recipe never
grants to an agent identity.

**Evaluation against priorities**:

- **Read-only principals**: Meets. Both administrator grants are provably false. The
  system identity's Contributor is provably false. The system identity keeps Reader and
  Log Analytics Reader, which are on the allow-list.
- **Compose, never re-author**: Partially meets. No upstream file is changed and no
  upstream resource is redeclared under its own name. However, three role assignments
  that upstream would otherwise create are authored here, which T5.02 has to allow as a
  narrow, reviewed exception.
- **Offline verifiability**: Meets. NEG-A and the narrowed T5.02 exception are both
  offline and fail closed.
- **Cheap pin bump**: Partially meets. A bump must confirm that upstream's gating still
  matches. If a future upstream ungates a grant, NEG-A catches it, so the risk is a
  failed gate rather than a silent escalation.
- **Human administration**: Meets, as an explicit and auditable step instead of an
  implicit grant to whoever ran the deployment.

### Option 4: Ask upstream for a gate, and block deployment until it ships

Propose an upstream change that gates `targetRbacSystemMi` and `uamiAdminRole` separately
from the deployer grant. Raise the pin when it merges. Deployment stays unavailable until
then.

**Evaluation against priorities**:

- **Read-only principals**: Meets once merged, and only together with condition-aware
  NEG-A, because the grants would remain conditional.
- **Compose, never re-author**: Meets fully.
- **Offline verifiability**: Same as Option 2 or 3.
- **Cheap pin bump**: Meets, and reduces local maintenance.
- **Human administration**: Depends on the shape upstream accepts.
- **Timeline**: Not under this repository's control. US-5 waits for it.

### Option 5: Patch or fork upstream

Edit the pinned modules to remove the grants.

**Evaluation against priorities**:

- **Read-only principals**: Meets.
- **Compose, never re-author**: Fails. This is what ADR-0001 rejects, and the content
  digest in the lock would no longer describe what runs.
- **Offline verifiability**: Meets for the patched copy, but the evidence describes code
  that is not the pinned upstream.
- **Cheap pin bump**: Fails. Every bump becomes a merge of local patches into new
  upstream code.
- **Human administration**: Depends on the patch.

## Decision

**Option 3**, chosen by the project owner on 2026-10-02, with Option 4 pursued in
parallel so that a future pin bump can retire the local role assignments. The status stays
Proposed until another team member reviews this record.

Option 3 is the only option that meets the first and third priorities, which are the
product claim and its evidence. It keeps the second priority except for a narrow
exception, scoped to roles already on the read-only allow-list. Options 1 and 2 leave the
agent identity able to modify itself. Option 4 alone leaves US-5 blocked indefinitely.

Before this ADR can move to Accepted, three facts must be measured in the lab rather than
assumed:

1. The agent operates for read-only investigation with no SRE Agent Administrator on
   its own user-assigned identity.
2. With `skipRoleAssignments = true`, the composition's three read grants are sufficient
   for the knowledge graph and the log connectors.
3. A human principal granted SRE Agent Administrator after deployment can administer the
   agent through the portal.

If the first fact fails, this ADR returns to the option list with that evidence, because
it changes what the first priority can achieve.

## Lab Evidence

Measured on 2026-10-02 in a lab subscription, against the pinned upstream deployed with
`skipRoleAssignments = true`, `accessLevel = Low`, `actionMode = Review` and the Log
Analytics connector enabled. The composition grants were applied by hand to reproduce
Option 3. Every lab resource was deleted afterwards.

| Fact | Result | Evidence |
|---|---|---|
| Post deploy roles | The user-assigned identity had no roles. The system identity still received Reader and Log Analytics Reader on the target resource group, outside the skip flag. | ARM role assignment listing |
| Negative control | With no roles on the user-assigned identity, the agent's read-only CLI call failed with subscription not found and the agent asked for on-behalf-of approval. The CLI therefore runs as the user-assigned identity. | Thread messages, `azCliExecution` status |
| First fact | Confirmed. With Reader and Log Analytics Reader on the target resource group and Monitoring Reader on the agent resource group, the agent completed resource reads and a Log Analytics query with no administrator role and no on-behalf-of approval. | Thread final message `step1=ok step2=ok` |
| Second fact | Confirmed for resource reads, knowledge graph search and CLI log queries. Log Analytics data access lagged the role grant: the query failed at about seven minutes and succeeded at about thirty two minutes. | Two threads, timed against the grant |
| Second fact, connector | Not confirmed. The upstream Log Analytics connector was provisioned with the system identity and was not listed by the agent's connector tools. The cause is unmeasured and no RBAC denial was observed. | `ListConnectors` returned an empty list |
| Third fact | Confirmed through the data plane API. A subscription Owner received 403 on agent data plane calls. About thirty five seconds after SRE Agent Administrator was granted on the agent resource, the same calls returned 200 and trigger creation returned 201. The portal UI was not exercised. | HTTP status codes before and after the grant |

Observations recorded for the runbook, unrelated to the decision itself:

- Firing an HTTP trigger returned 401 with an ARM audience token and 202 with a token for
  the agent data plane audience.
- The trigger body field is `agentPrompt`. A body using `prompt` is accepted, stores an
  empty prompt, and firing still returns 202. A 202 only means the run was queued, so a
  verification step must read the stored trigger and the resulting thread.

## Implementation Notes

If Option 3 is accepted, it implies the following changes:

- **NEG-A:** evaluate `condition` under literal bindings only. An unknown function, an
  unbound parameter or a non-literal binding keeps the grant as a finding. Mutation
  tests must show that an evaluator which assumes `false` is killed.
- **T5.02:** the exception admits `Microsoft.Authorization/roleAssignments` in
  `deploy/compose/` only. Every `roleDefinitionId` must be a literal from the read-only
  allow-list, and an unresolvable one fails. No other upstream type gains an exception.
- **T5.06** (`zeroops verify`) still checks effective permissions after deployment. The
  offline result does not replace that check (FR-33).
- **T5.01:** Monitoring Reader for the user-assigned identity goes on the agent resource
  group, matching the upstream scope. Reader and Log Analytics Reader go on each target
  resource group.
- **T5.06:** allow for Log Analytics data access propagation, measured above at more than
  seven minutes, before declaring a failed probe. Verification reads the stored trigger
  and the thread result instead of trusting the 202.
- **Follow up:** decide whether the composition creates the Log Analytics connector with
  the user-assigned identity, after measuring why the system identity connector is not
  visible to the agent tools.

## References

- [ADR-0001 Upstream Template Relationship](0001-upstream-template-relationship.md)
- [ADR-0002 Infrastructure as Code](0002-infrastructure-as-code.md)
- [`core/policy/README.md`](../../../core/policy/README.md), read-only role allow-list
- [`deploy/README.md`](../../../deploy/README.md), what may be authored here
- [Specification](../../features/sre-agent-recipe-framework/spec.md), FR-33 and CC-009
- [Tasks](../../features/sre-agent-recipe-framework/tasks.md), User Story 5

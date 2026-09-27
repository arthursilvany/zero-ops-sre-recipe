# Tool policy

`tool-policy.json` in this directory is the framework's own policy and the
ceiling every emitted policy is measured against.

## This layer is not the authority

The read-only guarantee is the RBAC grant that Azure Resource Manager
enforces. This policy is defence in depth. Nothing here is asserted to be
enforced, because the framework cannot observe the runtime enforcing it
(SEC-001, FR-51).

The policy is therefore **declared, not runtime-verified**. It stays that way
until the reconciliation gate has enumerated the capability set advertised by
a pinned runtime version and compared it against what this policy classifies.
The consolidated statement of that status belongs in the known-limitations
document (FR-74), which this file is an input to and not a substitute for.

The execution limits are **declared, not framework-enforced**. Enforcement
belongs to the agent runtime. They are verified by the post-deployment
tool-policy-posture check, which reports the limits the runtime actually
holds and fails on a mismatch, rather than by any local gate (FR-53).

## What the schema already guarantees

`contracts/schemas/tool-policy.schema.json` pins most of the model in a way no
instance can escape:

| Property | How it is pinned | What that rules out |
|---|---|---|
| `defaultDecision` | `const: "deny"` | A capability absent from the allow list arriving permitted |
| `conflictResolution` | `const: "denyWins"` | An allow rule overriding a deny rule |
| `onEvaluationFailure` | `const: "deny"` | Fail-open, which is inexpressible rather than discouraged |
| `denyRules` | `minItems: 7` with `uniqueItems` over a seven-member enumeration | Any of the seven FR-52 categories being dropped |
| `allowedCapabilityClasses` | Closed, read-shaped enumeration; required even when empty | A write-shaped class, and absence being read as a wildcard |

Because those are unfalsifiable by construction, no code re-checks them. A
check that cannot fail is a check that tells a reader nothing.

## What the schema cannot say

How large a limit may be. The schema requires the four limits FR-53 names and
constrains each to at least 1, which admits a policy declaring a million tool
calls and a day of wall clock. Those are the numbers the posture check
compares against the runtime, so a policy nobody could meet is a posture check
nobody can pass.

A consumer policy may **narrow** any limit and may not **widen** one. The
ceiling is inclusive, so the baseline is itself a legal policy.

| Limit | Ceiling |
|---|---|
| `executionLimits.maxToolCalls` | 200 |
| `executionLimits.maxWallClockSeconds` | 900 |
| `executionLimits.maxResultSetRows` | 1000 |
| `executionLimits.perQueryTimeoutSeconds` | 60 |
| `retryPolicy.maxAttempts` | 3 |

This is enforced as a semantic finding during `zeroops validate`, so a
consumer editing their own policy learns about it where they are working
rather than after a deployment.

## Raising a ceiling

Change the value here, and record why. A ceiling raised without a reason is a
ceiling that will be raised again.

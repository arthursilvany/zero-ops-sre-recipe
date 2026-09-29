# Permissions

Two permission sets, and they are not the same set (FR-11).

Conflating them is the common failure. A team grants one identity everything the setup needed and everything the agent will need, then runs the agent with it. The agent inherits a discovery-time grant it never uses, and the blast radius of the deployed thing is decided by what the wizard happened to require.

| | Discovery permission set | Agent permission set |
|---|---|---|
| Held by | The operator, or the pipeline identity, running guided setup | The managed identity of the deployed agent |
| Lifetime | The setup session | As long as the agent exists |
| Scope | One subscription, the one being set up | The scope written into the generated scope contract |
| Contains | Read actions only | Read actions only, in v1 |

Both are read-only in v1. That they are both read-only is not a reason to merge them: they differ in lifetime, in who holds them, and in scope, and any one of those differences is enough to keep them apart.

## Discovery permission set

What guided setup needs in order to propose candidates, and nothing more.

| Action | Why |
|---|---|
| `Microsoft.Resources/subscriptions/read` | Establish that the subscription is visible. Without it, a withheld subscription is indistinguishable from an empty one. |
| `Microsoft.ResourceGraph/resources/read` | Run the catalogued Resource Graph queries. |

Every action in this set ends in `/read`. That is a checkable property, and it is checked: a test asserts it, so an action that changes something cannot be added here without the addition being noticed.

The built-in role that covers both is **Reader**, at the subscription being set up. A narrower custom role containing exactly the two actions above works as well and is preferable where role creation is cheap.

This set is not needed after setup finishes. Nothing in the framework asks for it again.

## Agent permission set

What the deployed agent holds at run time.

The actions are not fixed here, because the scope is not fixed here: it is whatever the generated scope contract names, and that is a product of the workload extension in use and the choices made during setup. What is fixed is the shape:

- Read actions only. The v1 core issues no verb that changes state, and the broker refuses one.
- Assigned at the scope the contract names, not at the subscription by default. A subscription-wide grant for an agent scoped to part of it is a grant nobody asked for.
- Held by a managed identity, so there is no secret to rotate or to leak.

The read-only guarantee is the role assignment enforced by Azure Resource Manager. The broker is a second layer, and a bug in it is a bug in a second layer rather than the failure of the first. Granting this identity a write role would remove the guarantee no matter what the broker does.

## When a permission is missing

Discovery names the specific action it was refused, rather than reporting that something went wrong. A message that says "access denied" and stops turns a one-line grant into an investigation.

A refusal is reported as a denial and never as a shorter result. See [`../wizard/discovery/README.md`](../wizard/discovery/README.md).

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
| `*/read` at the subscription scope | Read every resource the step enumerates. Resource Graph returns only what the identity can read and does not say what it withheld, so anything narrower is a reduced answer that looks whole. Discovery checks this before enumerating and reports a denial when it is missing. |
| `Microsoft.Authorization/permissions/read` | Ask Azure Resource Manager which actions the identity holds at the subscription, which is how the row above is checked. Included in `*/read`. |
| `Microsoft.ResourceGraph/resources/read` | Run the catalogued Resource Graph queries. |

Every action in this set ends in `/read`. That is a checkable property, and it is checked: a test asserts it, so an action that changes something cannot be added here without the addition being noticed.

The built-in role that covers all three is **Reader**, at the subscription being set up. A role at a narrower scope, such as one resource group, is refused rather than accepted with a shorter list: Resource Graph shows such an identity the subscription and the resources it can see, and nothing in that answer says the rest exist. A custom role works only if it grants `*/read` with no `notActions` entry that could remove a read.

The Azure CLI resolves the subscription in the request against its own profile before calling ARM. An identity signed in with `--allow-no-subscriptions`, or signed in before the role grant propagated, may have a profile that does not list the subscription, and discovery then reports a denial even though Reader is in place. Sign in again once the grant is visible.

The check evaluates the actions and `notActions` ARM reports for the subscription. It does not evaluate deny assignments, so a read removed by one is not detected here.

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

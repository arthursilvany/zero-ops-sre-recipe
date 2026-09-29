# Binding layer

This is the only directory in the repository where a runtime-specific identifier may
appear (FR-04, CON-03, ADR-0001). Everything under `contracts/` and the rest of `core/`
describes capability classes; this directory says what one named runtime calls them.

The separation is enforced rather than intended. `zeroops check-core` fails if a core
path names any term in the `runtimeIdentifiers` list, and it also fails if this directory
names none of them, because a binding layer with no runtime specifics in it would mean
the identifiers had leaked somewhere else while the first check kept passing.

## What is here

| File | What it is |
|---|---|
| `azure-sre-agent.capability-mapping.json` | Capability classes mapped to the pinned runtime's tool identifiers, per `contracts/schemas/capability-mapping.schema.json`. |

## The mapping classifies nothing, on purpose

`entries` is an empty array and `verificationState` is `unverified`. Neither is a
placeholder waiting to be filled in by whoever reads this next. They are what was found.

The pinned runtime version is recorded in `deploy/upstream.lock`. At that exact commit,
the template layer's own agent definition carries an `access.accessLevel` setting and an
`actionMode` setting and no tool list of any kind. Its connector file names data sources,
not tools. Nothing in the pinned tree enumerates a capability identifier, which is the
concrete form of the unconfirmed-runtime-capability-identifiers limitation recorded under
FR-74.

Writing plausible tool names here would have produced a mapping that validates, reads as
complete, and asserts something nobody checked against the runtime. The framework already
refuses that shape elsewhere: a check that cannot distinguish its own absence from the
condition it looks for is the failure mode this repository keeps finding. An empty
mapping that says it is empty is the honest version of the same document.

## What the state means downstream

- `verificationState: "unverified"` is the declared-not-runtime-verified marker FR-51
  requires. The tool policy is defence in depth; the read-only guarantee comes from the
  RBAC grant that Azure Resource Manager enforces (SEC-001), so an unmapped capability
  class does not widen what the agent can reach.
- There is no `toolListPointer`, so the NEG-D explicit-tool-list check refuses every
  binding emitted for this runtime with `the capability mapping declares no
  toolListPointer`. That is the fail-closed state, not an exemption. Deployment work
  cannot quietly proceed past it.
- `reconciledAt` and `reconciledCapabilitySetHash` are absent, and the schema forbids
  them while the state is unverified, so a stale value cannot be mistaken for evidence of
  a gate that never ran.

## What would change this

The reconciliation gate (S4-12) enumerates the capability set the pinned runtime version
actually advertises and fails closed on any capability the tool policy neither allows nor
denies (NEG-C). When it runs against a real runtime it sets `verificationState` to
`reconciled`, which the schema then requires to carry both a timestamp and the digest of
the capability set that was seen, and to classify at least one capability. A reconciled
mapping with no entries would say the gate ran and saw nothing, which is what a gate that
never ran also looks like.

Raising the pin in `deploy/upstream.lock` invalidates the mapping: `runtimeVersion`
records the version this was produced against precisely because the identifiers a runtime
advertises can change between versions.

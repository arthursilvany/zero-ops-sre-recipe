# Eligibility rules

These are the rules that decide whether a discovered resource is a candidate
workload. They are published here because an operator who runs discovery and
gets nothing back is owed the reasoning, not just the outcome (FR-12).

## One source, two renderings

The rules live in
[`eligibility-rules.json`](eligibility-rules.json) and nowhere else. The block
below is generated from that file, and so is the report discovery prints when
it finds no candidate. A test regenerates the block and fails when it differs,
so the document and the report cannot drift apart while both continue to look
correct on their own.

Do not edit the block by hand. Change the JSON, then regenerate:

```text
PYTHONPATH=tools python -m zeroops.eligibility --write
```

Run it without `--write` to check for drift without changing anything.

## What these rules do not contain

No resource type appears here, in either direction. The core neither admits
nor excludes any workload type: a resource type becomes a candidate type
because an installed extension declares it so (ELI-004). A default list of
admitted types in this file would be workload content inside a core path, and
a default list of excluded types would be the same content written backwards
(FR-63, CC-022, CON-11).

The practical consequence is the one worth stating plainly: **on a fresh
installation with no extension installed, discovery correctly returns zero
candidates.** That is the designed behaviour and not a fault. The empty-result
report says so, and names the rule responsible.

## The rules

<!-- BEGIN GENERATED RULES -->
### ELI-001 Inside the supplied scope

The resource belongs to the single subscription the operator supplied. Nothing outside that subscription is considered, and discovery never widens the scope on its own.

Decided at the scope stage; you supplied this.

If this rule excluded everything: The subscription holds no resource discovery can see at all. Confirm the subscription identifier is the one intended, and that it is not an empty or newly created subscription.

### ELI-002 Readable with read-only permissions

The identity running discovery can read the resource. Discovery requests no permission beyond reading, and a portion of the scope it cannot read is reported as an explicit access-denied state naming the missing permission.

Decided at the permission stage; the platform answered this.

If this rule excluded everything: The identity can reach the subscription but cannot read inside it. Read the reported denials: they name the permission that was missing. An empty candidate list with denials present is a permissions problem and not an absence of workloads.

### ELI-003 Emits an observable signal

The resource exposes at least one signal that can be read without changing it. A resource that emits nothing observable cannot be investigated by a read-only agent, so listing it as a candidate would promise an investigation that could never happen.

Decided at the signal stage; the platform answered this.

If this rule excluded everything: Resources exist and are readable, but none of them emits a signal discovery could find. This usually means diagnostic collection was never configured. Configuring it is a prerequisite, not a workaround.

### ELI-004 Its type is declared eligible by an installed extension

A resource type becomes a candidate type because an installed workload extension declares it so. The framework core declares no resource type of its own, in either direction: it neither admits nor excludes any type, and shipping a default list here would make the core carry workload content it is required not to carry.

Decided at the extension stage; an installed extension declared this.

If this rule excluded everything: No extension is installed, or none of the installed extensions declares a type present in this scope. This is the expected result on a fresh installation. Install or write the extension for the workload being onboarded; no core file needs to change.

### ELI-005 Not excluded by the operator

The resource is not matched by an exclusion the operator supplied. Exclusions are applied last and always win, so a resource every other rule admitted can still be withheld deliberately.

Decided at the exclusion stage; you supplied this.

If this rule excluded everything: The exclusions supplied matched everything the earlier rules admitted. Re-read them: an exclusion written more broadly than intended removes candidates without reporting a denial, because withholding was the instruction.
<!-- END GENERATED RULES -->

## Reading an empty result

The rules print in the order above, which runs from the cheapest condition to
the most specific. Read top to bottom and stop at the first one that could
plausibly have excluded everything; that is the one worth investigating.

Each rule names who supplies the fact it tests, because the fix differs. A
rule decided by the operator is changed by supplying different input. A rule
decided by the platform is changed in Azure, and an empty result from
`ELI-002` in particular is a permissions problem rather than an absence of
workloads, which is why unreadable scope is reported as an explicit denial and
never silently dropped (FR-22). A rule decided by an extension is changed by
installing or writing one, with no core file edited.

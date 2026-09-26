"""Cross-artifact references, and where each one is resolved.

A directory is a configuration set. Each artifact in it validates on its own,
and a set whose members every validate can still be incoherent: a framework
configuration naming a tool policy that no file defines validates today,
because no per-artifact rule can reach another document. "Complete" then means
nothing, since nobody checks it.

This module is a total registry of every reference-shaped property in
``contracts/schemas/``. Every one is either resolved within its own document,
resolved across the set here, or explicitly recorded as produced at run time
and therefore absent from a configuration set. A property with no entry is a
property nobody decided about, and a test refuses that state rather than
letting the reference go unchecked.
"""

from collections import namedtuple

# Where a reference is resolved.
WITHIN_DOCUMENT = "withinDocument"
ACROSS_SET = "acrossSet"
RUNTIME_PRODUCED = "runtimeProduced"

RESOLUTIONS = (WITHIN_DOCUMENT, ACROSS_SET, RUNTIME_PRODUCED)

# A target is the place a name has to be defined for the use to resolve:
# the artifact kind that defines it, and the path within that artifact.
# "*" stands for every item of an array.
Target = namedtuple("Target", "kind path label")

EXTERNAL_REFERENCE = Target(
    "framework-config",
    ("externalReferences", "entries", "*", "name"),
    "an external reference",
)
ENVIRONMENT = Target(
    "framework-config", ("environments", "*", "name"), "an environment"
)
WORKLOAD = Target("framework-config", ("workloads", "*", "name"), "a workload")
TOOL_POLICY = Target("tool-policy", ("name",), "a tool policy")
QUERY_CATALOGUE = Target("query-catalogue", ("name",), "a query catalogue")
CATALOGUE_ENTRY = Target(
    "query-catalogue", ("entries", "*", "id"), "a catalogue entry"
)
WORKLOAD_EXTENSION = Target(
    "workload-extension", ("name",), "a workload extension"
)
CONNECTOR = Target("connector-config", ("name",), "a connector configuration")
SCOPE_DIGEST = Target(
    "scope-contract", ("canonicalHash",), "a scope contract by its canonical hash"
)

Reference = namedtuple(
    "Reference", "schema property resolution path target rationale"
)

# Every reference-shaped property in contracts/schemas/, without exception.
# Adding one to a schema without adding it here fails
# test_example_sets.TheRegistryCoversEveryReferenceProperty.
REFERENCES = (
    Reference(
        "framework-config",
        "subscriptionRef",
        WITHIN_DOCUMENT,
        None,
        None,
        "Names an entry in the same document's externalReferences. Already "
        "resolved by the framework-config semantic rule, which is why it is "
        "not resolved a second time here.",
    ),
    Reference(
        "framework-config",
        "endpointRef",
        WITHIN_DOCUMENT,
        None,
        None,
        "A connector entry's endpoint, named in the same document's "
        "externalReferences and resolved by the framework-config rule.",
    ),
    Reference(
        "framework-config",
        "credentialRef",
        WITHIN_DOCUMENT,
        None,
        None,
        "A connector entry's credential, named in the same document's "
        "externalReferences and resolved by the framework-config rule.",
    ),
    Reference(
        "framework-config",
        "workspaceRef",
        WITHIN_DOCUMENT,
        None,
        None,
        "The agent's own telemetry destination, named in the same document's "
        "externalReferences and resolved by the framework-config rule.",
    ),
    Reference(
        "framework-config",
        "approverGroupRef",
        WITHIN_DOCUMENT,
        None,
        None,
        "The approver group, named in the same document's externalReferences "
        "and resolved by the framework-config rule.",
    ),
    Reference(
        "framework-config",
        "toolPolicyRef",
        ACROSS_SET,
        ("toolIntegrations", "toolPolicyRef"),
        TOOL_POLICY,
        "The policy that applies. Unresolved, the configuration claims a "
        "read-only posture that no shipped document states.",
    ),
    Reference(
        "framework-config",
        "queryCatalogueRef",
        ACROSS_SET,
        ("observability", "queryCatalogueRef"),
        QUERY_CATALOGUE,
        "The catalogue the agent may run. Unresolved, the only queries that "
        "can run are ones nobody reviewed, because no catalogue was found.",
    ),
    Reference(
        "framework-config",
        "extensionRef",
        ACROSS_SET,
        ("workloads", "*", "extensionRef"),
        WORKLOAD_EXTENSION,
        "The workload extension a workload uses. The core declares the seam "
        "and ships no workload-type content of its own (FR-63).",
    ),
    Reference(
        "scope-contract",
        "subscriptionRef",
        ACROSS_SET,
        ("subscriptionRef",),
        EXTERNAL_REFERENCE,
        "The subscription the scope is taken against. Declared in the "
        "framework configuration, never carried here as a value.",
    ),
    Reference(
        "connector-config",
        "endpointRef",
        ACROSS_SET,
        ("endpointRef",),
        EXTERNAL_REFERENCE,
        "Where the connector points. An unresolved endpoint is a connector "
        "that cannot be configured from this set.",
    ),
    Reference(
        "connector-config",
        "credentialRef",
        ACROSS_SET,
        ("authentication", "credentialRef"),
        EXTERNAL_REFERENCE,
        "The identity the connector authenticates with, referenced and never "
        "inlined (SEC-013).",
    ),
    Reference(
        "agent-definition",
        "deploymentRef",
        ACROSS_SET,
        ("modelProvider", "deploymentRef"),
        EXTERNAL_REFERENCE,
        "The model deployment locator. A literal endpoint in a committed file "
        "would be a customer environment identifier (NFR-02).",
    ),
    Reference(
        "agent-definition",
        "targetScopeRef",
        ACROSS_SET,
        ("targetScopeRef",),
        SCOPE_DIGEST,
        "The canonical hash of the scope this agent was defined against. "
        "Resolving it is how scope drift is caught before deployment rather "
        "than after (FR-23).",
    ),
    Reference(
        "environment-binding",
        "environmentRef",
        ACROSS_SET,
        ("environmentRef",),
        ENVIRONMENT,
        "The environment this binding applies to, declared once in the "
        "framework configuration.",
    ),
    Reference(
        "environment-binding",
        "workloadRef",
        ACROSS_SET,
        ("workloadRef",),
        WORKLOAD,
        "The workload this binding binds. Its scope lives in the framework "
        "configuration and only there, which is what stops two environments "
        "from drifting apart (FR-36).",
    ),
    Reference(
        "environment-binding",
        "connectorRefs",
        ACROSS_SET,
        ("connectorRefs", "*"),
        CONNECTOR,
        "Connectors that apply in this environment, named and never restated.",
    ),
    Reference(
        "workload-extension",
        "connectorRefs",
        ACROSS_SET,
        ("connectorRefs", "*"),
        CONNECTOR,
        "Connectors this workload needs, named and never restated (SEC-013).",
    ),
    Reference(
        "workload-extension",
        "queryRef",
        ACROSS_SET,
        ("alertDefinitions", "*", "queryRef"),
        CATALOGUE_ENTRY,
        "The catalogue entry an alert reads from. An alert pointing at no "
        "entry would fire on a query that was never reviewed.",
    ),
    Reference(
        "evidence-manifest",
        "sourceRef",
        RUNTIME_PRODUCED,
        None,
        None,
        "Names the query execution an evidence entry came from. Produced "
        "during an execution, so it cannot appear in a configuration set and "
        "has nothing to resolve against here.",
    ),
    Reference(
        "evidence-manifest",
        "evidenceRefs",
        RUNTIME_PRODUCED,
        None,
        None,
        "Links one evidence entry to others within the same emitted manifest. "
        "Resolved inside the manifest at emission, not across a set.",
    ),
    Reference(
        "assessment-result",
        "evidenceRefs",
        RUNTIME_PRODUCED,
        None,
        None,
        "Resolves a conclusion to the evidence that supports it, inside the "
        "manifest emitted by the same execution.",
    ),
    Reference(
        "readiness-result",
        "evidenceRefs",
        RUNTIME_PRODUCED,
        None,
        None,
        "Resolves a readiness finding to its evidence, inside the manifest "
        "emitted by the same execution.",
    ),
)


def by_resolution(resolution):
    """Every reference resolved in one place."""
    if resolution not in RESOLUTIONS:
        raise ValueError("unknown resolution: %s" % resolution)
    return tuple(r for r in REFERENCES if r.resolution == resolution)


def for_schema(schema):
    return tuple(r for r in REFERENCES if r.schema == schema)


def collect(document, path):
    """Every (pointer, value) a path reaches. "*" spans an array.

    Returns pointer strings so a finding can name the exact property rather
    than the artifact, which is what makes a set-level error actionable.
    """
    found = []

    def walk(node, remaining, parts):
        if not remaining:
            if isinstance(node, str):
                found.append(("/" + "/".join(parts), node))
            return
        head, rest = remaining[0], remaining[1:]
        if head == "*":
            if isinstance(node, list):
                for index, item in enumerate(node):
                    walk(item, rest, parts + [str(index)])
            return
        if isinstance(node, dict) and head in node:
            walk(node[head], rest, parts + [head])

    walk(document, list(path), [])
    return found


def defined_names(documents, target):
    """Every name a target defines across the artifacts of one kind."""
    names = set()
    for document in documents.get(target.kind, ()):
        for _, value in collect(document, target.path):
            names.add(value)
    return names

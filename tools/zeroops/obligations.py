"""Recommended-area obligations, and the warnings that surface them.

The Minimum SRE Agent Contract classifies every candidate area as Required,
Recommended, Optional or Out of scope (FR-01). Required areas are enforced
structurally: the schemas make the non-compliant document unwritable. Recommended
areas cannot be enforced that way without breaking CON-11, because requiring them
would force a customer to author something bespoke before seeing a first result.

So they get a third tier. A Recommended area that is absent produces a warning,
never an error, and a warning never changes the exit code unless the caller asks
for that with --strict. The distinction matters: a tool that fails on advice is a
tool people learn to ignore, and a tool that stays silent about production gaps
is one that ships them.

The registry below is deliberately total. Every Recommended area in the contract
appears exactly once, and an area that cannot be observed in configuration says
so and says why, rather than being omitted. Omission and "checked, nothing to
report" look identical from the outside, and only one of them is honest. A test
parses the contract document and asserts this registry covers exactly the areas
classified Recommended there, so adding an area to the contract without deciding
its observability fails CI rather than passing quietly.
"""

CONTRACT_DOCUMENT = "docs/architecture/minimum-sre-agent-contract.md"

OBSERVABLE = "observable"
NOT_OBSERVABLE = "notObservableAtConfigurationTime"


class Warning(object):
    """One Recommended area that this artifact does not cover."""

    def __init__(self, area, pointer, message):
        self.area = area
        self.pointer = pointer or "/"
        self.message = message

    def render(self, artifact):
        return "%s#%s: contract area %d (Recommended): %s" % (
            artifact,
            self.pointer,
            self.area,
            self.message,
        )


def _missing(instance, *path):
    """True when the path is absent, empty, or not reachable."""
    node = instance
    for key in path:
        if not isinstance(node, dict):
            return True
        if key not in node:
            return True
        node = node[key]
    if node is None:
        return True
    if isinstance(node, (list, dict, str)) and len(node) == 0:
        return True
    return False


def _warn_agent_scenarios(instance):
    if _missing(instance, "skills"):
        return Warning(
            3,
            "/skills",
            "no scenario is declared, so the agent runs framework defaults only. "
            "Declaring scenarios is how a consumer narrows or extends them.",
        )
    return None


def _warn_self_observability(instance):
    if _missing(instance, "observability", "workspaceRef"):
        return Warning(
            9,
            "/observability/workspaceRef",
            "the agent's own telemetry has no destination. A first result does "
            "not depend on it; a production deployment does.",
        )
    return None


def _warn_execution_limits(instance):
    if _missing(instance, "toolIntegrations", "toolPolicyRef"):
        return Warning(
            17,
            "/toolIntegrations/toolPolicyRef",
            "no tool policy is bound, so retry and timeout behaviour falls back "
            "to conservative framework defaults rather than limits tuned to the "
            "data sources in use.",
        )
    return None


def _warn_connector_timeout(instance):
    if _missing(instance, "timeoutSeconds"):
        return Warning(
            17,
            "/timeoutSeconds",
            "this connector declares no timeout, so it inherits the framework "
            "default rather than a bound suited to its data source.",
        )
    return None


# area -> (observability, artifact kind or reason, rule)
RECOMMENDED_AREAS = {
    3: (
        OBSERVABLE,
        [("agent-definition", _warn_agent_scenarios)],
        "Supported operational scenarios",
    ),
    9: (
        OBSERVABLE,
        [("framework-config", _warn_self_observability)],
        "Observability of the agent itself",
    ),
    10: (
        NOT_OBSERVABLE,
        "Post-deployment verification belongs to area 20 and is Required. What "
        "remains here is continuing health checking, which is a property of the "
        "running deployment rather than of any configuration artifact, so no "
        "document can be inspected to decide whether it is in place.",
        "Health checks",
    ),
    17: (
        OBSERVABLE,
        [
            ("framework-config", _warn_execution_limits),
            ("connector-config", _warn_connector_timeout),
        ],
        "Retry and timeout behavior",
    ),
    21: (
        NOT_OBSERVABLE,
        "The quickstart is Required and is covered by area 25. Per-scenario "
        "runbooks are prose held outside the configuration set, so their presence "
        "is a documentation check rather than a validation one.",
        "Runbooks",
    ),
    23: (
        NOT_OBSERVABLE,
        "The contract states that ownership should be recordable, but no schema "
        "in contracts/schemas/ currently carries an ownership field. Recording "
        "that gap here is deliberate: inventing the field inside the validator "
        "would put the check ahead of the contract it is supposed to enforce.",
        "Operational ownership",
    ),
}


def warnings_for(kind, instance):
    """Return the Recommended-area warnings that apply to one artifact."""
    found = []
    if not isinstance(instance, dict):
        return found
    for area in sorted(RECOMMENDED_AREAS):
        observability, payload, _ = RECOMMENDED_AREAS[area]
        if observability != OBSERVABLE:
            continue
        for applies_to, rule in payload:
            if applies_to != kind:
                continue
            warning = rule(instance)
            if warning is not None:
                found.append(warning)
    return found


def observable_areas():
    return sorted(
        area
        for area, entry in RECOMMENDED_AREAS.items()
        if entry[0] == OBSERVABLE
    )


def unobservable_areas():
    return sorted(
        area
        for area, entry in RECOMMENDED_AREAS.items()
        if entry[0] == NOT_OBSERVABLE
    )

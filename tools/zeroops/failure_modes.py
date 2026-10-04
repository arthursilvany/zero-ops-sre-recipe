"""Every failure class the specification names, and the one execution state it produces.

FR-07 requires that each failure class map to a defined state value. That is only
checkable if the set of failure classes is closed, so this registry is total in both
directions: every bullet in the specification's *Failure Modes* section appears here
exactly once, and every terminal execution state other than `completed` is reachable
from at least one class. A state no class can produce would be a value the contract
defines and nothing can ever set, which is indistinguishable from a typo.

One bullet is deliberately not a failure class. The consistency model states which
operations are eventually consistent; it describes a property of the system rather than
an outcome an execution can reach. It is recorded here with that reason rather than
omitted, because an omission and a decision look identical from outside.

Two classes come from the *Edge Cases* section rather than *Failure Modes*. Both are
cited, and both exist because the terminal states they produce would otherwise be
unreachable: nothing in *Failure Modes* halts a run on its own limits, and nothing there
describes permission that was never granted as distinct from permission that has not yet
propagated. That distinction is the specification's own, and collapsing it would make a
settling deployment indistinguishable from a misconfigured one.

Retryability is recorded because a retry is only honest when repeating the request can
change the answer. Retrying a divergent configuration or an incompatible schema version
reproduces the same outcome while consuming the budget that a genuinely transient
failure would have needed.
"""

import collections
import os
import re

FailureClass = collections.namedtuple(
    "FailureClass",
    [
        "name",
        "source",
        "citation",
        "execution_state",
        "retryable",
        "rationale",
        "probable_cause",
        "recovery_action",
    ],
    defaults=(None, None),
)

# The classes FR-77 adds. Each was observed against a live runtime, which is why each
# also names a probable cause and a recovery action: an operator who meets one of them
# needs the first thing to check, not only the state it produced.
FR77_CLASSES = (
    "awaitingApproval",
    "connectorNotVisibleToAgent",
    "noToolUse",
    "deliveryFailed",
)

# The lead-in of each bullet in the specification's Failure Modes section, verbatim.
# Matched against the document, so a reworded bullet fails rather than drifts.
FAILURE_MODE_SECTION = "### Failure Modes"

SPEC_RELATIVE_PATH = os.path.join(
    "docs", "features", "sre-agent-recipe-framework", "spec.md"
)

# A class whose source bullet describes a property rather than an outcome carries this
# instead of a state. It is a value, not an absence, so that "no state" has to be
# written down.
NOT_AN_EXECUTION_OUTCOME = "notAnExecutionOutcome"

FAILURE_CLASSES = [
    FailureClass(
        name="discoveryProviderUnavailable",
        source="Discovery provider unavailable or throttled",
        citation="Failure Modes",
        execution_state="failed",
        retryable=True,
        rationale=(
            "The bullet requires failing closed rather than emitting a scope contract "
            "from a partial enumeration. A partial enumeration that was allowed to "
            "stand would understate the scope, and every later conclusion would be "
            "drawn against a smaller world than the real one while looking complete. "
            "Retryable because throttling and transient unavailability settle."
        ),
    ),
    FailureClass(
        name="deploymentPartiallyApplied",
        source="Deployment partially applies",
        citation="Failure Modes",
        execution_state="incomplete",
        retryable=True,
        rationale=(
            "Some resources exist and others do not. The work already done is real "
            "and inspectable, which is what separates this from a failure: the bullet "
            "requires the environment be left inspectable and a re-run converge. "
            "Calling it failed would imply nothing was applied."
        ),
    ),
    FailureClass(
        name="roleAssignmentNotYetEffective",
        source="Role assignment propagation delay",
        citation="Failure Modes",
        execution_state="incomplete",
        retryable=True,
        rationale=(
            "The bullet requires that validation distinguish not-yet-effective from "
            "not-granted. Mapping this to accessDenied would collapse exactly that "
            "distinction and turn a deployment that is still settling into one that "
            "looks misconfigured, which is the difference between waiting and "
            "re-running a deployment that was already correct."
        ),
    ),
    FailureClass(
        name="dataSourceUnreachable",
        source="Data source unreachable at execution time",
        citation="Failure Modes",
        execution_state="incomplete",
        retryable=True,
        rationale=(
            "The run continues and records an unobserved entry, so the evidence it did "
            "gather stands and the conclusions that depended on the missing source are "
            "downgraded. The entry-level counterpart is the unobservedReason value "
            "sourceUnreachable; this is the execution-level outcome when the run ends "
            "with at least one such gap."
        ),
    ),
    FailureClass(
        name="concurrentScopeConflict",
        source="Two operators deploy against overlapping scopes concurrently",
        citation="Failure Modes",
        execution_state="failed",
        retryable=False,
        rationale=(
            "Convergent concurrent deployments are required to be idempotent and are "
            "therefore not a failure at all. What reaches this class is the divergent "
            "case, which the bullet resolves in version control rather than at "
            "deployment time. Not retryable: repeating the same divergent request "
            "produces the same conflict, and a retry budget spent here is a budget "
            "not available to something transient."
        ),
    ),
    FailureClass(
        name="frameworkVersionIncompatible",
        source="A consumer pins an older framework version while the core advances",
        citation="Failure Modes",
        execution_state="failed",
        retryable=False,
        rationale=(
            "The designed behaviour is that a pinned consumer keeps operating, so this "
            "class is reached only when the declared schema version cannot be honoured "
            "at all. Failing closed is the point: proceeding would interpret an "
            "artifact under a version it does not conform to. Not retryable, because "
            "the same artifact and the same core produce the same answer."
        ),
    ),
    FailureClass(
        name="executionLimitReached",
        source="An execution limit is reached mid-run",
        citation="Edge Cases",
        execution_state="incomplete",
        retryable=False,
        rationale=(
            "The edge case requires the run halt, the partial result be recorded with "
            "an explicit incomplete state, and no value be extrapolated. Not retryable "
            "under unchanged limits, because the same limits reproduce the same halt; "
            "raising a limit is a configuration change and not a retry, and recording "
            "it as retryable would invite a loop that never converges."
        ),
    ),
    FailureClass(
        name="accessNotGranted",
        source="Permission was never granted, as distinct from not yet effective",
        citation="Failure Modes, derived distinction",
        execution_state="accessDenied",
        retryable=False,
        rationale=(
            "The other half of the distinction the role-assignment bullet requires. "
            "Being refused is a finding about the environment rather than a defect in "
            "the run, which is why accessDenied is a first-class state and not a kind "
            "of failure. Not retryable: a grant that does not exist does not appear by "
            "asking again."
        ),
    ),
    FailureClass(
        name="awaitingApproval",
        source="An execution waits on an approval a read-only agent should never need",
        citation="Functional Requirements, FR-77",
        execution_state="incomplete",
        retryable=False,
        rationale=(
            "A read-only agent has no write to approve, so a run that stops on an "
            "approval request has met a permission gap that the runtime surfaced as a "
            "request to act on someone's behalf. Treating it as a human decision would "
            "leave it waiting with nobody able to answer, which the lab observed as an "
            "unbounded wait. Incomplete because the evidence read before the request "
            "stands. Not retryable: the same missing role produces the same request."
        ),
        probable_cause=(
            "The agent identity lacks a read role on the scope it queried, so the "
            "runtime asked to use the caller's identity instead."
        ),
        recovery_action=(
            "Grant the missing read role named in the request to the agent identity "
            "through the deployment, wait for propagation, then start a new execution."
        ),
    ),
    FailureClass(
        name="connectorNotVisibleToAgent",
        source="A provisioned data-source connector the agent cannot list",
        citation="Functional Requirements, FR-77",
        execution_state="failed",
        retryable=False,
        rationale=(
            "Distinct from dataSourceUnreachable: the source itself answers, but the "
            "agent holds no binding to it, so every conclusion would be drawn without "
            "that source by construction rather than by accident. A provisioning state "
            "reported as succeeded is not evidence of use (FR-75). Not retryable, "
            "because the lab connector never appeared however long the probe waited, "
            "and recreating it is a configuration change rather than a retry."
        ),
        probable_cause=(
            "The connector resource exists but is not registered with the agent's own "
            "connector listing, or it was created with an identity the agent does not "
            "use."
        ),
        recovery_action=(
            "List the agent's connectors through the agent itself, compare with the "
            "declared data sources, and recreate the missing connector through the "
            "supported configuration path before running verification again."
        ),
    ),
    FailureClass(
        name="noToolUse",
        source="An execution that concluded without calling any tool",
        citation="Functional Requirements, FR-77",
        execution_state="failed",
        retryable=False,
        rationale=(
            "A conclusion reached without a single tool call observed nothing, so any "
            "finding it states is unsupported by evidence collected in the execution "
            "window (FR-81). The lab reached this state when a trigger stored an empty "
            "instruction and still answered accepted. Not retryable: repeating the "
            "same stored instruction reproduces the same empty run."
        ),
        probable_cause=(
            "The stored instruction is empty or does not name a target, or the agent "
            "has no tool able to reach the declared scope."
        ),
        recovery_action=(
            "Read back the stored instruction and confirm it is the expected text, then "
            "confirm the declared connectors are visible to the agent before firing a "
            "new execution."
        ),
    ),
    FailureClass(
        name="deliveryFailed",
        source="Findings produced but not delivered to their declared destination",
        citation="Functional Requirements, FR-77",
        execution_state="incomplete",
        retryable=True,
        rationale=(
            "The investigation finished and its evidence is valid; only the hand-off of "
            "the result failed. Calling the run failed would discard evidence that is "
            "already correct. Retryable because delivery depends on a destination that "
            "can recover, and redelivering the same findings does not repeat the "
            "investigation or its reads."
        ),
        probable_cause=(
            "The destination rejected or did not acknowledge the delivery, or the "
            "delivery path is denied by the tool policy."
        ),
        recovery_action=(
            "Check the destination and the externalPublication rule in the tool policy, "
            "then redeliver the recorded findings without starting a new investigation."
        ),
    ),
    FailureClass(
        name="consistencyModel",
        source="Consistency model",
        citation="Failure Modes",
        execution_state=NOT_AN_EXECUTION_OUTCOME,
        retryable=False,
        rationale=(
            "Records which operations are eventually consistent and states that "
            "contract validation is immediate. That is a property of the system, not "
            "an outcome a run can reach, so it maps to no execution state. Listed "
            "rather than skipped, because a bullet absent from this registry and a "
            "bullet deliberately excluded from it are otherwise the same thing."
        ),
    ),
]

# The states a failure class may produce. Deliberately excludes running, which is not
# terminal, and completed, which is the absence of a failure class.
TERMINAL_FAILURE_STATES = ("failed", "incomplete", "accessDenied")


def by_name(name):
    for failure_class in FAILURE_CLASSES:
        if failure_class.name == name:
            return failure_class
    return None


def mapped_classes():
    """The classes that produce an execution state."""
    return [
        failure_class
        for failure_class in FAILURE_CLASSES
        if failure_class.execution_state != NOT_AN_EXECUTION_OUTCOME
    ]


def unmapped_classes():
    """The bullets recorded as describing something other than an outcome."""
    return [
        failure_class
        for failure_class in FAILURE_CLASSES
        if failure_class.execution_state == NOT_AN_EXECUTION_OUTCOME
    ]


def state_for(name):
    """The single execution state a failure class produces, or None."""
    failure_class = by_name(name)
    if failure_class is None or failure_class.execution_state == NOT_AN_EXECUTION_OUTCOME:
        return None
    return failure_class.execution_state


def classes_for_state(state):
    return [
        failure_class.name
        for failure_class in mapped_classes()
        if failure_class.execution_state == state
    ]


def retryable(name):
    failure_class = by_name(name)
    return bool(failure_class and failure_class.retryable)


def parse_failure_mode_bullets(spec_text):
    """The bold lead-in of every bullet in the specification's Failure Modes section.

    Parsed rather than restated so that a bullet added to the specification and never
    classified here fails, which is the only way the registry stays total as the
    document changes.
    """
    start = spec_text.find(FAILURE_MODE_SECTION)
    if start == -1:
        return []
    remainder = spec_text[start + len(FAILURE_MODE_SECTION) :]
    end = remainder.find("\n## ")
    if end != -1:
        remainder = remainder[:end]
    return re.findall(r"^- \*\*(.+?)\*\*", remainder, flags=re.MULTILINE)

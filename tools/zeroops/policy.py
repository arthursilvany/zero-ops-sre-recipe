"""The framework's tool policy baseline, and the one rule the schema cannot express.

`contracts/schemas/tool-policy.schema.json` already pins most of what FR-51
and FR-52 require, and it pins it in a way no instance can escape:
`defaultDecision`, `conflictResolution` and `onEvaluationFailure` are `const`,
and `denyRules` combines `minItems: 7` with `uniqueItems` over a seven-member
enumeration, so all seven categories are present or the document is invalid.

Re-checking any of that here would be a check that cannot fail. What the
schema cannot say is *how large* a limit may be. It requires the four limits
FR-53 names and constrains each to at least 1, which admits a policy
declaring a million tool calls and a day of wall clock. Those are the numbers
the post-deployment posture check compares against what the runtime actually
holds, so a policy nobody could meet is a posture check nobody can pass.

So the baseline is a ceiling. A consumer may narrow any limit and may not
widen one. That is the whole of what this module adds, stated plainly because
a module that appeared to re-verify the enforcement model would suggest the
enforcement model was in doubt.

This layer is not the authority. The read-only guarantee is the RBAC grant
Azure Resource Manager enforces (SEC-001). The policy is defence in depth and
is declared, not runtime-verified, until the reconciliation gate has run
against a real runtime (FR-51, FR-74).
"""

import json
import os


BASELINE_PATH = "core/policy/tool-policy.json"

# Each limit and the direction that counts as widening. All four are
# "larger is wider"; the pairing is written out rather than assumed so that a
# limit whose sense is inverted cannot be added without someone deciding.
CEILINGS = (
    ("maxToolCalls", "tool calls"),
    ("maxWallClockSeconds", "seconds of wall clock"),
    ("maxResultSetRows", "result rows"),
    ("perQueryTimeoutSeconds", "seconds per query"),
)

RETRY_CEILING = ("maxAttempts", "retry attempts")


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def baseline_path(root=None):
    root = root or repo_root()
    return os.path.join(root, BASELINE_PATH.replace("/", os.sep))


def load_baseline(root=None):
    with open(baseline_path(root), "r", encoding="utf-8") as handle:
        return json.load(handle)


def ceiling_findings(instance, baseline=None):
    """Return [(pointer, message)] for every limit that exceeds the baseline.

    The baseline measured against itself returns nothing: a ceiling is
    inclusive, so the framework's own policy is a legal policy. A test asserts
    that, because a ceiling its own author could not satisfy would be a number
    picked without reference to anything.
    """
    if not isinstance(instance, dict):
        return []
    baseline = baseline if baseline is not None else load_baseline()
    findings = []

    limits = instance.get("executionLimits")
    ceiling = baseline.get("executionLimits", {})
    if isinstance(limits, dict):
        for key, unit in CEILINGS:
            findings.extend(
                _compare(limits.get(key), ceiling.get(key), "/executionLimits/" + key, unit)
            )

    retry = instance.get("retryPolicy")
    retry_ceiling = baseline.get("retryPolicy", {})
    if isinstance(retry, dict):
        key, unit = RETRY_CEILING
        findings.extend(
            _compare(retry.get(key), retry_ceiling.get(key), "/retryPolicy/" + key, unit)
        )

    return findings


def _compare(value, ceiling, pointer, unit):
    if not isinstance(value, int) or not isinstance(ceiling, int):
        # A missing or non-integer value is the schema's problem, and it has
        # already refused the document by the time anything reaches here.
        # Reporting it again would put two findings on one fault.
        return []
    if value <= ceiling:
        return []
    return [
        (
            pointer,
            "declares %d %s, above the %d the framework baseline permits "
            "(%s). A policy may narrow a limit and may not widen one: these "
            "are the numbers the post-deployment posture check compares "
            "against the runtime, and the framework does not vouch for a "
            "value it has never measured." % (value, unit, ceiling, BASELINE_PATH),
        )
    ]

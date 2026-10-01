"""Read-only Resource Graph discovery over one subscription (FR-10, FR-11, FR-22).

Three properties this module exists to hold, each of which fails quietly if
nobody builds for it.

## The scope is never reduced without saying so

Resource Graph returns what the calling identity can see. It does not report
what it withheld. An identity with no read access to the supplied subscription
gets the same answer as an identity looking at an empty subscription: zero
rows, exit code zero, no error. That is the failure FR-22 is about, and a
module that only inspected the exit code would report an empty candidate list
and be wrong in the one direction that matters.

So readability is established before enumeration, by asking Azure Resource
Manager which actions the identity holds at the subscription scope itself, and
requiring a read of everything there. Asking Resource Graph whether the
subscription container is visible is not enough: it returns that row to an
identity holding any role anywhere inside the subscription, so an identity
that can read one resource group passed the check and its ten resources were
reported as the whole answer (issue 144). A subscription the identity cannot
read in full is reported as an explicit access-denied state naming the
permission that was missing. The distinction it buys is the one an operator
cannot make from the outside: nothing here, or nothing you can see.

## A reduced result cannot be read as a whole one

`DiscoveryResult.rows` refuses when a denial is present, and
`partial_rows()` is the only way to reach them. A caller that wants the
incomplete answer has to write down that it is incomplete. The alternative is
an attribute that returns a shorter list, which is precisely the silent
reduction the requirement forbids, expressed as a convenience.

## Every invocation goes through the broker

Nothing here builds a command for anything other than `broker.plan`. The
broker decides; this module supplies tokens. A query is never interpolated
into a shell string, and the subscription identifier is checked against the
one shape it can legitimately have before it becomes a token.

## What this module does not do

It does not decide eligibility. The rules are published in
`wizard/eligibility/` and the stages beyond scope and permission are applied
later in the guided step. It names no workload type, because
`wizard/discovery/` is a core path (FR-63, CC-022, CON-11).
"""

import json
import os
import re

from . import broker, canonical, policy


CATALOGUE_PATH = "wizard/discovery/query-catalogue.json"

# The three reads the step issues, in the order it issues them. Readability
# first: the other two are meaningless until it is known whether an empty
# answer means empty or means withheld.
READABILITY_QUERY = "subscription-readability"
RESOURCES_QUERY = "subscription-resources"
DIAGNOSTIC_SETTINGS_QUERY = "resource-diagnostic-settings"

QUERY_ORDER = (READABILITY_QUERY, RESOURCES_QUERY, DIAGNOSTIC_SETTINGS_QUERY)

# Reads issued to Azure Resource Manager through `az rest` rather than to
# Resource Graph. Their catalogued text is an ARM request path, with
# SUBSCRIPTION_PLACEHOLDER where the checked identifier goes.
ARM_READS = (READABILITY_QUERY,)
SUBSCRIPTION_PLACEHOLDER = "{subscription}"

# Where each read's rows live in its JSON answer. Resource Graph wraps them in
# `data`; ARM list operations wrap them in `value`.
ENVELOPE_FOR = {
    READABILITY_QUERY: "value",
    RESOURCES_QUERY: "data",
    DIAGNOSTIC_SETTINGS_QUERY: "data",
}

# The actions that grant a read of every resource type. Resource Graph
# returns only the resources the identity can read, so anything narrower than
# one of these at the subscription scope is a reduced answer that looks whole.
READ_EVERYTHING = ("*", "*/read")

# An Azure subscription identifier is a GUID and nothing else. Checked before
# the value becomes a command token: the broker refuses shell metacharacters,
# but a value that is merely wrong rather than dangerous would otherwise reach
# Azure and come back as an error about a subscription nobody meant to name.
# Case-insensitive on input and lowercased on the way out, because Azure
# treats the two spellings as the same subscription and evidence compared
# across runs must not differ over which one an operator pasted.
SUBSCRIPTION_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# The permission each read needs, named so a denial tells an operator what to
# grant rather than that something went wrong. These are Azure action strings,
# not workload content.
PERMISSION_FOR = {
    READABILITY_QUERY: "*/read",
    RESOURCES_QUERY: "Microsoft.ResourceGraph/resources/read",
    DIAGNOSTIC_SETTINGS_QUERY: "Microsoft.ResourceGraph/resources/read",
}

# Substrings Azure uses when it refuses for want of permission, lowercased.
# Matched against the command's error output. This list decides only how a
# failure is *described*; a failure matching none of them is still a failure,
# reported as an error rather than reclassified as a denial. A list that
# decided whether to report at all would have to be complete, and no list of
# other people's error strings ever is.
AUTHORISATION_SIGNATURES = (
    "authorizationfailed",
    "does not have authorization to perform action",
    "forbidden",
    "insufficient privileges",
    "authorization_requestdenied",
)

# How a subscription the identity cannot see is reported, by the CLI before
# the request is sent and by ARM after it. Applied to the readability read
# only, whose sole target is the subscription the operator named, so "not
# found" there can only mean "not visible to this identity" or a mistyped
# identifier. Both are reported as a denial; the description says so.
NOT_VISIBLE_SIGNATURES = (
    re.compile(r"subscriptionnotfound"),
    re.compile(r"subscription '[^']*' (?:not found|could not be found)"),
)


class DiscoveryError(Exception):
    """Discovery could not be carried out at all.

    Distinct from a denial, which is a reportable state, and from an empty
    result, which is an answer. A caller that could not tell these apart would
    present a broken invocation as an empty subscription.
    """


class IncompleteDiscovery(Exception):
    """The whole result was requested while part of the scope was withheld."""


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def catalogue_path(root=None):
    return os.path.join(root or repo_root(), CATALOGUE_PATH.replace("/", os.sep))


def load_catalogue(root=None):
    with open(catalogue_path(root), "r", encoding="utf-8") as handle:
        return json.load(handle)


def entries_by_id(catalogue):
    return {entry["id"]: entry for entry in catalogue.get("entries", [])}


def entry(catalogue, identifier):
    found = entries_by_id(catalogue).get(identifier)
    if found is None:
        raise DiscoveryError(
            "the catalogue holds no query %r. Discovery runs catalogued "
            "queries only, so a query that is not there cannot be issued "
            "(the tool policy denies constructing one)." % identifier
        )
    return found


def integrity_findings(catalogue):
    """Recompute every query hash and report the ones that disagree.

    This is what 'integrity-verified' has to mean to be worth stating. A
    catalogue edited after review validates against its schema perfectly well;
    the hash is the only thing that notices.
    """
    findings = []
    for item in catalogue.get("entries", []):
        recomputed = canonical.text_digest(item["queryText"])
        if recomputed != item.get("queryHash"):
            findings.append(
                "%s: the recorded query hash does not match the query text. "
                "The entry was edited after it was reviewed, or the recorded "
                "hash was never correct. Recorded %s, recomputed %s."
                % (item["id"], item.get("queryHash"), recomputed)
            )
    return findings


def coverage_findings(catalogue):
    """Every query the step issues must be in the catalogue, and nothing in
    the catalogue may be a query the step never issues.

    Both directions. A missing entry stops discovery at run time, which is
    late. A catalogue entry nothing issues is a reviewed query with no caller,
    and the next person to add a caller inherits a review nobody repeated.
    """
    findings = []
    present = set(entries_by_id(catalogue))
    for identifier in QUERY_ORDER:
        if identifier not in present:
            findings.append(
                "%s is issued by discovery but is not in the catalogue, so the "
                "step would fail at the point of use." % identifier
            )
    for identifier in sorted(present - set(QUERY_ORDER)):
        findings.append(
            "%s is in the catalogue but discovery issues no such query, so it "
            "carries a review that covers no call site." % identifier
        )
    return findings


def check_subscription(subscription):
    if not isinstance(subscription, str) or not SUBSCRIPTION_PATTERN.match(
        subscription
    ):
        raise DiscoveryError(
            "%r is not a subscription identifier. v1 discovery targets exactly "
            "one subscription (CON-11), named as a GUID." % (subscription,)
        )
    return subscription.lower()


def row_limit():
    """The row cap, taken from the tool policy rather than chosen here.

    A second number would be a second policy, and the two would diverge with
    nothing comparing them.
    """
    return policy.load_baseline()["executionLimits"]["maxResultSetRows"]


def plan_query(catalogue, identifier, subscription, limit=None):
    """The argument list for one catalogued query, as the broker approves it.

    Pure, so the entire command surface of discovery is testable with no
    Azure, no credentials and no network.
    """
    item = entry(catalogue, identifier)
    subscription = check_subscription(subscription)
    if identifier in ARM_READS:
        path = item["queryText"]
        if path.count(SUBSCRIPTION_PLACEHOLDER) != 1:
            raise DiscoveryError(
                "%s is an ARM read whose catalogued path does not name %s "
                "exactly once, so it would not read the subscription the "
                "operator supplied." % (identifier, SUBSCRIPTION_PLACEHOLDER)
            )
        return broker.plan(
            [
                "az",
                "rest",
                "--method",
                "get",
                "--url",
                path.replace(SUBSCRIPTION_PLACEHOLDER, subscription),
            ]
        )
    limit = row_limit() if limit is None else limit
    return broker.plan(
        [
            "az",
            "graph",
            "query",
            "--graph-query",
            item["queryText"],
            "--subscriptions",
            subscription,
            "--first",
            str(limit),
        ]
    )


def denial_for(identifier, message):
    """Describe a failed read as a denial, or return None.

    Returning None for an unrecognised failure is the point: a failure that is
    not a denial must not be presented as one, because 'grant this permission'
    is advice that wastes an operator's time when the cause was something else.
    """
    lowered = (message or "").lower()
    for signature in AUTHORISATION_SIGNATURES:
        if signature in lowered:
            return Denial(identifier, PERMISSION_FOR[identifier])
    if identifier == READABILITY_QUERY:
        for pattern in NOT_VISIBLE_SIGNATURES:
            if pattern.search(lowered):
                return Denial(identifier, PERMISSION_FOR[identifier])
    return None


def grants_subscription_read(permissions):
    """Whether ARM's permission list for the subscription reads every resource.

    Each entry is one role's `actions` less its `notActions`, and the identity
    holds the union of the entries. So one entry granting a read of everything
    with no exclusion that could touch a read is enough, and an exclusion in
    one entry is not rescued by an action in another unless that other entry
    grants the whole read itself.
    """
    for grant in permissions:
        if not isinstance(grant, dict):
            continue
        actions = [str(a).lower() for a in grant.get("actions") or []]
        if not any(action in READ_EVERYTHING for action in actions):
            continue
        if any(_may_exclude_a_read(n) for n in grant.get("notActions") or []):
            continue
        return True
    return False


def _may_exclude_a_read(not_action):
    """Conservative: an exclusion is harmless only when its final segment is a
    literal operation other than `read`, such as `.../Delete` or `.../action`.

    Anything ending in a wildcard or in `read` could remove a read of some
    resource type, and deciding which types would need the full list of
    provider operations, which this module does not have and should not ship.
    """
    last = str(not_action).rsplit("/", 1)[-1].lower()
    return "*" in last or last == "read"


class Denial(object):
    """One withheld portion of the requested scope (FR-22)."""

    def __init__(self, query, permission):
        self.query = query
        self.permission = permission

    def describe(self):
        scope = ""
        if self.query == READABILITY_QUERY:
            scope = (
                " at the subscription scope (the built-in Reader role there "
                "grants it), or the subscription is not in this tenant, or "
                "the Azure CLI profile does not list it yet (sign in again "
                "after a recent role grant, without --allow-no-subscriptions)"
            )
        return (
            "%s: access was denied. The identity running discovery is missing "
            "%s%s. This is a permissions result and not an empty subscription; "
            "the scope has not been narrowed to match what could be read."
            % (self.query, self.permission, scope)
        )


class DiscoveryResult(object):
    """What discovery found, and what it was not allowed to look at.

    `rows` refuses while a denial is present. A caller wanting the partial
    answer calls `partial_rows`, which says so at the call site. An attribute
    that quietly returned the shorter list would be the silent scope reduction
    FR-22 forbids, dressed as a convenience.
    """

    def __init__(self, subscription, rows=None, denials=None):
        self.subscription = subscription
        self._rows = list(rows or [])
        self.denials = list(denials or [])

    @property
    def complete(self):
        return not self.denials

    @property
    def rows(self):
        if self.denials:
            raise IncompleteDiscovery(
                "part of the requested scope was withheld, so this is not the "
                "list of resources in the subscription. Read `denials` and "
                "report them, or call partial_rows() to state that an "
                "incomplete answer is what you want.\n%s" % self.describe_denials()
            )
        return list(self._rows)

    def partial_rows(self):
        return list(self._rows)

    def describe_denials(self):
        return "\n".join(denial.describe() for denial in self.denials)


def _decode(text, identifier):
    # A successful `az graph query --output json` always prints a document,
    # `{"data": []}` when nothing matched. Missing or blank output on success
    # is therefore a failure to read the answer, and returning [] for it is
    # how a 663-resource subscription was once reported as complete and empty
    # (issue 141).
    if text is None or not text.strip():
        raise DiscoveryError(
            "%s exited successfully but returned no readable output. An empty "
            "result is an empty JSON document, never no output, so this is "
            "reported as a failure rather than as zero rows." % identifier
        )
    try:
        parsed = json.loads(text)
    except ValueError:
        raise DiscoveryError(
            "%s returned output that is not JSON. The broker pins --output "
            "json, so this is a failure to reach Azure rather than a result."
            % identifier
        )
    if isinstance(parsed, dict):
        envelope = ENVELOPE_FOR.get(identifier, "data")
        if envelope not in parsed:
            raise DiscoveryError(
                "%s returned a JSON object with no %r member. Reading that as "
                "no rows would be the silent empty answer this module refuses."
                % (identifier, envelope)
            )
        parsed = parsed[envelope]
    if not isinstance(parsed, list):
        raise DiscoveryError(
            "%s returned a result that is not a list of rows." % identifier
        )
    return parsed


def run_query(catalogue, identifier, subscription, runner, limit=None):
    """Issue one catalogued query. Returns (rows, denial).

    Exactly one of the two is meaningful, and a failure that is neither raises.
    """
    planned = plan_query(catalogue, identifier, subscription, limit=limit)
    completed = runner(planned)
    if completed.returncode != 0:
        denial = denial_for(identifier, completed.stderr)
        if denial is not None:
            return [], denial
        raise DiscoveryError(
            "%s failed and the failure is not a denial: %s"
            % (identifier, (completed.stderr or "").strip() or "no error output")
        )
    return _decode(completed.stdout, identifier), None


def discover(subscription, runner=None, catalogue=None, root=None, limit=None):
    """Enumerate the readable resources in one subscription (FR-10, FR-22).

    Readability is settled first. Resource Graph answers an unreadable
    subscription and an empty one identically, so enumerating first and
    inspecting the row count afterwards cannot tell them apart, and would
    report the empty list in both cases.
    """
    subscription = check_subscription(subscription)
    catalogue = catalogue if catalogue is not None else load_catalogue(root)

    broken = integrity_findings(catalogue) + coverage_findings(catalogue)
    if broken:
        raise DiscoveryError(
            "the discovery catalogue cannot be trusted, so no query was "
            "issued:\n%s" % "\n".join(broken)
        )

    runner = runner or broker.default_runner

    permissions, denial = run_query(
        catalogue, READABILITY_QUERY, subscription, runner, limit=limit
    )
    if denial is not None or not grants_subscription_read(permissions):
        # A refused read, and a read that succeeds but shows the identity
        # holds less than a read of everything at this scope, are the same
        # result for the operator: what follows would not be the whole
        # subscription. Enumerating anyway would hand back the visible part
        # with nothing to say it was a part (issue 144).
        return DiscoveryResult(
            subscription,
            denials=[
                denial
                or Denial(READABILITY_QUERY, PERMISSION_FOR[READABILITY_QUERY])
            ],
        )

    rows, denial = run_query(
        catalogue, RESOURCES_QUERY, subscription, runner, limit=limit
    )
    denials = [denial] if denial is not None else []

    signals, denial = run_query(
        catalogue, DIAGNOSTIC_SETTINGS_QUERY, subscription, runner, limit=limit
    )
    if denial is not None:
        denials.append(denial)

    emitting = {_parent_of(item.get("id", "")) for item in signals}
    for row in rows:
        row["emitsSignal"] = row.get("id", "").lower() in emitting

    return DiscoveryResult(subscription, rows=rows, denials=denials)


def _parent_of(diagnostic_setting_id):
    """The resource a diagnostic setting is attached to.

    A setting identifier is the resource identifier followed by the provider
    path. Splitting on that path is how the parent is read without a second
    query for every resource.
    """
    lowered = (diagnostic_setting_id or "").lower()
    marker = "/providers/microsoft.insights/diagnosticsettings/"
    index = lowered.find(marker)
    return lowered[:index] if index != -1 else lowered

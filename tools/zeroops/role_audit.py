"""NEG-A: every role definition in the compiled deployment output is read-only.

This is the offline half of FR-33 and CC-009, and SEC-001's first layer. It
reads a compiled ARM template, the JSON that Bicep emits, and asserts that
every role definition identifier it can grant resolves to
`core/policy/role-allow-list.json`. It needs no credentials and opens no
connection, which is what makes it runnable in CI on every change and is the
reason ADR-0002 compiles to ARM rather than keeping state elsewhere.

What the audit refuses to do, and why:

- **It ignores `condition`.** A conditional role assignment is decided by a
  deployment-time value that an offline check cannot see. Treating a
  Contributor assignment as safe because its condition reads `High` and the
  default is `Low` would make the audit's verdict depend on a parameter file
  it never read. A role the template can grant is a role the audit judges.
- **It fails closed on anything it cannot resolve.** A role definition taken
  from a parameter, built with `format()`, or held in a linked template the
  audit cannot open is reported as unresolvable rather than skipped. Skipping
  would let the cheapest way past the audit be to move the identifier one
  indirection away from where it looks.
- **It rejects custom role definitions outright.** A custom role's actions are
  whatever the template says they are, and the allow-list admits identifiers
  of measured built-in roles only.

Beyond the role assignments, every string anywhere in the document that names
a role definition is checked as well, so an identifier passed into a nested
template as a value, or held in a variable or output, cannot sit outside the
audit's view.

This check judges the grants a template issues. It cannot see what a
consumer-supplied identity already holds elsewhere; that is NEG-B at preview
and `zeroops verify` after deployment (SEC-003).
"""

import json
import os
import re
import sys


ALLOW_LIST_PATH = "core/policy/role-allow-list.json"

EXIT_OK = 0
EXIT_REJECTED = 1
EXIT_USAGE = 2

ROLE_ASSIGNMENT_TYPE = "microsoft.authorization/roleassignments"
ROLE_DEFINITION_TYPE = "microsoft.authorization/roledefinitions"
DEPLOYMENT_TYPE = "microsoft.resources/deployments"
DEPLOYMENT_TEMPLATE_SCHEMA = "deploymenttemplate.json"

_GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

# Any mention of a role definition by identifier, in whatever form ARM spells
# it: a resource-id function argument or a literal path segment.
ROLE_REFERENCE = re.compile(
    r"roleDefinitions'?\s*(?:,\s*'|/)(" + _GUID + r")", re.IGNORECASE
)

# The forms a roleDefinitionId may take for the audit to resolve it. Anything
# else is unresolvable and fails.
_RESOURCE_ID_FORM = re.compile(
    r"^\[(?:subscription|tenant|managementGroup)?resourceId\("
    r"\s*'Microsoft\.Authorization/roleDefinitions'\s*,\s*(?P<arg>.+?)\s*\)\]$",
    re.IGNORECASE,
)
_LITERAL_PATH_FORM = re.compile(
    r"^(?:/subscriptions/[^/]+)?/providers/Microsoft\.Authorization/roleDefinitions/"
    r"(?P<guid>" + _GUID + r")$",
    re.IGNORECASE,
)
_QUOTED_GUID = re.compile(r"^'(?P<guid>" + _GUID + r")'$")
_VARIABLE_REFERENCE = re.compile(r"^variables\('(?P<name>[^']+)'\)$")
_BARE_GUID = re.compile(r"^" + _GUID + r"$")

# Shapes an accepted exception may never take. Each would admit writes broadly
# while reading as a single, narrow line.
_FORBIDDEN_ACCEPTANCE = (
    (re.compile(r"^\*$"), "a bare wildcard admits every operation"),
    (
        re.compile(r"^\*/(?!read$)", re.IGNORECASE),
        "a wildcard provider with a non-read verb admits that verb everywhere",
    ),
    (
        re.compile(r"^Microsoft\.Authorization/", re.IGNORECASE),
        "an authorization operation can grant the agent more than it has",
    ),
    (
        re.compile(r"/(write|delete)$", re.IGNORECASE),
        "a write or delete is the operation the allow-list exists to exclude",
    ),
)


class Finding(object):
    def __init__(self, pointer, message, role_definition_id=None):
        self.pointer = pointer or "/"
        self.message = message
        self.role_definition_id = role_definition_id

    def render(self, artifact):
        return "%s#%s: %s" % (artifact, self.pointer, self.message)

    def __repr__(self):
        return "Finding(%r, %r)" % (self.pointer, self.message)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_allow_list(path=None):
    path = path or os.path.join(repo_root(), ALLOW_LIST_PATH.replace("/", os.sep))
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def allowed_identifiers(allow_list):
    return {
        role["roleDefinitionId"].lower()
        for role in allow_list.get("roles", [])
        if isinstance(role, dict) and isinstance(role.get("roleDefinitionId"), str)
    }


def is_read(permission):
    return permission.lower().endswith("/read")


def allow_list_findings(allow_list):
    """What the schema cannot say about the allow-list.

    The schema can require that acceptances exist; it cannot require that they
    name exactly the non-read permissions the role was measured to hold.
    """
    findings = []
    seen = {}
    for index, role in enumerate(allow_list.get("roles") or []):
        if not isinstance(role, dict):
            continue
        base = "/roles/%d" % index
        identifier = str(role.get("roleDefinitionId", "")).lower()
        if identifier in seen:
            findings.append(
                Finding(
                    base + "/roleDefinitionId",
                    "role definition %s is listed twice, also at /roles/%d"
                    % (identifier, seen[identifier]),
                )
            )
        else:
            seen[identifier] = index

        for granted_key, accepted_key in (
            ("actions", "acceptedNonReadActions"),
            ("dataActions", "acceptedNonReadDataActions"),
        ):
            granted = [p for p in role.get(granted_key) or [] if isinstance(p, str)]
            accepted = [
                a for a in role.get(accepted_key) or [] if isinstance(a, dict)
            ]
            accepted_names = [a.get("permission") for a in accepted]

            for permission in granted:
                if not is_read(permission) and permission not in accepted_names:
                    findings.append(
                        Finding(
                            "%s/%s" % (base, granted_key),
                            "'%s' is not a read and is not listed in %s with a "
                            "reason" % (permission, accepted_key),
                        )
                    )

            for position, name in enumerate(accepted_names):
                pointer = "%s/%s/%d/permission" % (base, accepted_key, position)
                if name not in granted:
                    findings.append(
                        Finding(
                            pointer,
                            "'%s' is accepted but the role was not recorded "
                            "holding it in %s" % (name, granted_key),
                        )
                    )
                    continue
                for shape, why in _FORBIDDEN_ACCEPTANCE:
                    if isinstance(name, str) and shape.search(name):
                        findings.append(
                            Finding(
                                pointer,
                                "'%s' cannot be accepted on a read-only agent: %s"
                                % (name, why),
                            )
                        )
                        break
    return findings


def _pointer_escape(token):
    return str(token).replace("~", "~0").replace("/", "~1")


def _resolve_argument(argument, variables):
    argument = argument.strip()
    match = _QUOTED_GUID.match(argument)
    if match:
        return match.group("guid")
    match = _VARIABLE_REFERENCE.match(argument)
    if match:
        value = variables.get(match.group("name"))
        if isinstance(value, str) and _BARE_GUID.match(value):
            return value
    return None


def resolve_role_definition(value, variables):
    """The GUID a roleDefinitionId expression names, or None if unresolvable."""
    if not isinstance(value, str):
        return None
    text = value.strip()

    match = _LITERAL_PATH_FORM.match(text)
    if match:
        return match.group("guid").lower()

    match = _RESOURCE_ID_FORM.match(text)
    if match:
        guid = _resolve_argument(match.group("arg"), variables)
        return guid.lower() if guid else None

    match = re.match(r"^\[(?P<inner>variables\('[^']+'\))\]$", text)
    if match:
        resolved = variables.get(match.group("inner")[len("variables('"):-2])
        if isinstance(resolved, str) and resolved != text:
            return resolve_role_definition(resolved, variables)
    return None


def _resources_of(template):
    """(pointer suffix, resource) pairs for both ARM resource layouts.

    Bicep emits a list, or with languageVersion 2.0 an object keyed by
    symbolic name. Both are audited; recognising only one would let the other
    pass without being read.
    """
    resources = template.get("resources")
    if isinstance(resources, list):
        return [("/resources/%d" % i, r) for i, r in enumerate(resources)]
    if isinstance(resources, dict):
        return [
            ("/resources/%s" % _pointer_escape(name), r)
            for name, r in resources.items()
        ]
    return []


def _audit_template(template, pointer, allowed, findings, counters):
    variables = template.get("variables")
    if not isinstance(variables, dict):
        variables = {}

    for suffix, resource in _resources_of(template):
        if not isinstance(resource, dict):
            continue
        here = pointer + suffix
        kind = str(resource.get("type", "")).lower()
        properties = resource.get("properties")
        if not isinstance(properties, dict):
            properties = {}

        if kind.endswith(ROLE_ASSIGNMENT_TYPE):
            counters["assignments"] += 1
            raw = properties.get("roleDefinitionId")
            guid = resolve_role_definition(raw, variables)
            target = here + "/properties/roleDefinitionId"
            if guid is None:
                findings.append(
                    Finding(
                        target,
                        "role definition cannot be resolved offline: %s. Name a "
                        "built-in role by literal identifier, through "
                        "resourceId or a variable holding the identifier, so "
                        "the audit can see which role is granted"
                        % json.dumps(raw),
                    )
                )
            elif guid not in allowed:
                findings.append(
                    Finding(
                        target,
                        "role definition %s is not on the read-only allow-list "
                        "(%s)" % (guid, ALLOW_LIST_PATH),
                        guid,
                    )
                )

        elif kind.endswith(ROLE_DEFINITION_TYPE):
            findings.append(
                Finding(
                    here,
                    "a custom role definition is created here. The allow-list "
                    "admits measured built-in roles only, because a custom "
                    "role's permissions are whatever this template says",
                )
            )

        elif kind == DEPLOYMENT_TYPE:
            if isinstance(properties.get("template"), dict):
                _audit_template(
                    properties["template"],
                    here + "/properties/template",
                    allowed,
                    findings,
                    counters,
                )
            if "templateLink" in properties:
                findings.append(
                    Finding(
                        here + "/properties/templateLink",
                        "a linked template cannot be audited offline. Compile "
                        "the module inline so its role assignments are part of "
                        "the output being audited",
                    )
                )

        nested = resource.get("resources")
        if isinstance(nested, (list, dict)):
            _audit_template(
                {"resources": nested, "variables": variables},
                here,
                allowed,
                findings,
                counters,
            )


def _strings(node, pointer):
    if isinstance(node, str):
        yield pointer, node
    elif isinstance(node, dict):
        for key, value in node.items():
            child = pointer + "/" + _pointer_escape(key)
            for item in _strings(key, child):
                yield item
            for item in _strings(value, child):
                yield item
    elif isinstance(node, list):
        for index, value in enumerate(node):
            for item in _strings(value, "%s/%d" % (pointer, index)):
                yield item


def is_compiled_template(document):
    if not isinstance(document, dict):
        return False
    schema = str(document.get("$schema", "")).lower()
    return schema.endswith(DEPLOYMENT_TEMPLATE_SCHEMA + "#") or schema.endswith(
        DEPLOYMENT_TEMPLATE_SCHEMA
    )


def audit(document, allow_list=None):
    """Findings for one compiled ARM template, and how many grants were read.

    Returns (findings, assignment_count). An empty findings list with a
    count of zero is a template that grants nothing, which is a pass and is
    reported as such by the command rather than passed off as an audit of
    something.
    """
    allow_list = allow_list if allow_list is not None else load_allow_list()
    allowed = allowed_identifiers(allow_list)
    findings = []
    counters = {"assignments": 0}

    if not is_compiled_template(document):
        findings.append(
            Finding(
                "/$schema",
                "not a compiled ARM deployment template. Audit the output of "
                "the Bicep build, not a Bicep file or a parameter file; a "
                "document the audit does not recognise cannot pass it",
            )
        )
        return findings, 0

    _audit_template(document, "", allowed, findings, counters)

    reported = {(f.pointer, f.role_definition_id) for f in findings}
    for pointer, text in _strings(document, ""):
        for match in ROLE_REFERENCE.finditer(text):
            guid = match.group(1).lower()
            if guid in allowed:
                continue
            if (pointer, guid) in reported:
                continue
            findings.append(
                Finding(
                    pointer,
                    "role definition %s is referenced here and is not on the "
                    "read-only allow-list (%s)" % (guid, ALLOW_LIST_PATH),
                    guid,
                )
            )
            reported.add((pointer, guid))

    return findings, counters["assignments"]


def run(target, allow_list_path=None, out=None, err=None):
    out = out or sys.stdout
    err = err or sys.stderr
    try:
        with open(target, "r", encoding="utf-8-sig") as handle:
            document = json.load(handle)
    except (OSError, ValueError) as exc:
        err.write("error: cannot read compiled template %s: %s\n" % (target, exc))
        return EXIT_USAGE
    try:
        allow_list = load_allow_list(allow_list_path)
    except (OSError, ValueError) as exc:
        err.write("error: cannot read the role allow-list: %s\n" % exc)
        return EXIT_USAGE

    findings, assignments = audit(document, allow_list)
    if findings:
        err.write("Role audit rejected: %d finding(s).\n" % len(findings))
        for finding in findings:
            err.write("  %s\n" % finding.render(target))
        return EXIT_REJECTED

    out.write(
        "Role audit passed: %d role assignment(s), every role definition on the "
        "read-only allow-list.\n" % assignments
    )
    return EXIT_OK

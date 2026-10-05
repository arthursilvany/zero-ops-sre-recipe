"""Fail closed when the reviewed runtime dependency closure has known advisories."""

import http.client
import json
import re
import sys
import urllib.error
import urllib.request

from supply_chain import generate_lock

OSV_QUERY_URL = "https://api.osv.dev/v1/query"
REQUEST_TIMEOUT_SECONDS = 30
ADVISORY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class AuditError(Exception):
    """The dependency audit could not produce a trustworthy result."""


def runtime_packages(declaration):
    """Return the reviewed direct and transitive runtime dependency closure."""
    packages = declaration.get("packages") if isinstance(declaration, dict) else None
    if not isinstance(packages, list) or not packages:
        raise AuditError("the reviewed runtime dependency declaration is missing or empty")

    names = set()
    for package in packages:
        if not isinstance(package, dict):
            raise AuditError("a runtime dependency entry is not an object")
        name = package.get("name")
        version = package.get("version")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(version, str)
            or not version.strip()
            or package.get("role") not in ("direct", "transitive")
        ):
            raise AuditError("a runtime dependency entry lacks a valid name, version, or role")
        normalized_name = name.casefold()
        if normalized_name in names:
            raise AuditError("the runtime dependency declaration contains a duplicate package")
        names.add(normalized_name)
    return packages


def _query_vulnerabilities(package, open_url=None):
    request = urllib.request.Request(
        OSV_QUERY_URL,
        data=json.dumps(
            {
                "package": {"name": package["name"], "ecosystem": "PyPI"},
                "version": package["version"],
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    opener = open_url or urllib.request.urlopen
    try:
        with opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as exc:
        raise AuditError(
            "OSV query failed for %s==%s: %s" % (package["name"], package["version"], exc)
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise AuditError(
            "OSV returned an unreadable response for %s==%s"
            % (package["name"], package["version"])
        ) from exc

    if not isinstance(payload, dict):
        raise AuditError("OSV returned an invalid response for %s" % package["name"])
    if payload and "vulns" not in payload:
        raise AuditError("OSV returned an invalid response for %s" % package["name"])
    vulnerabilities = payload.get("vulns", [])
    if not isinstance(vulnerabilities, list):
        raise AuditError("OSV returned an invalid vulnerability list for %s" % package["name"])

    advisory_ids = []
    for vulnerability in vulnerabilities:
        advisory_id = vulnerability.get("id") if isinstance(vulnerability, dict) else None
        if not isinstance(advisory_id, str) or not ADVISORY_ID.fullmatch(advisory_id):
            raise AuditError("OSV returned a vulnerability without a valid advisory ID")
        advisory_ids.append(advisory_id)
    return advisory_ids


def audit(declaration, lock_file=None, open_url=None):
    """Verify the reviewed lock, then query OSV for every runtime package."""
    problems = generate_lock.verify_lock(declaration, lock_file=lock_file)
    if problems:
        raise AuditError("dependency lock verification failed: " + "; ".join(problems))

    findings = []
    for package in runtime_packages(declaration):
        for advisory_id in _query_vulnerabilities(package, open_url=open_url):
            findings.append((package["name"], package["version"], advisory_id))
    return findings


def main():
    try:
        declaration = generate_lock.load_declaration()
        packages = runtime_packages(declaration)
        findings = audit(declaration)
    except (AuditError, OSError, json.JSONDecodeError) as exc:
        print("Dependency vulnerability audit failed: %s" % exc, file=sys.stderr)
        return 1

    if findings:
        print("Known vulnerabilities found in reviewed runtime dependencies:", file=sys.stderr)
        for name, version, advisory_id in findings:
            print("  %s==%s: %s" % (name, version, advisory_id), file=sys.stderr)
        return 1

    print("OSV reported no known advisories for %d reviewed runtime dependencies." % len(packages))
    return 0


if __name__ == "__main__":
    sys.exit(main())

import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from supply_chain import audit_vulnerabilities

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOW = os.path.join(REPO_ROOT, ".github", "workflows", "dependency-audit.yml")
DECLARATION = os.path.join(REPO_ROOT, "tools", "supply-chain.json")
LOCK = os.path.join(REPO_ROOT, "tools", "requirements.lock")


def response(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def declaration():
    with open(DECLARATION, "r", encoding="utf-8") as handle:
        return json.load(handle)


class RuntimeDependencyAudit(unittest.TestCase):
    def test_every_declared_runtime_package_is_queried_at_its_pinned_version(self):
        packages = declaration()["packages"]
        opener = mock.Mock(side_effect=[response({}) for _ in packages])

        findings = audit_vulnerabilities.audit(
            declaration(), lock_file=LOCK, open_url=opener
        )

        self.assertEqual([], findings)
        self.assertEqual(len(packages), opener.call_count)
        requested = [
            json.loads(call.args[0].data.decode("utf-8"))
            for call in opener.call_args_list
        ]
        self.assertEqual(
            [
                {
                    "package": {"name": package["name"], "ecosystem": "PyPI"},
                    "version": package["version"],
                }
                for package in packages
            ],
            requested,
        )

    def test_a_known_advisory_is_reported_as_a_finding(self):
        packages = declaration()["packages"]
        responses = [response({"vulns": [{"id": "GHSA-abcd-1234-efgh"}]})]
        responses.extend(response({}) for _ in packages[1:])
        opener = mock.Mock(side_effect=responses)

        findings = audit_vulnerabilities.audit(
            declaration(), lock_file=LOCK, open_url=opener
        )

        self.assertEqual(
            [(packages[0]["name"], packages[0]["version"], "GHSA-abcd-1234-efgh")],
            findings,
        )

    def test_osv_unavailability_fails_closed(self):
        opener = mock.Mock(side_effect=urllib.error.URLError("offline"))

        with self.assertRaisesRegex(audit_vulnerabilities.AuditError, "OSV query failed"):
            audit_vulnerabilities.audit(
                declaration(), lock_file=LOCK, open_url=opener
            )

    def test_malformed_response_fails_closed(self):
        for payload in ({"vulns": "not-a-list"}, {"error": "unavailable"}):
            with self.subTest(payload=payload):
                opener = mock.Mock(return_value=response(payload))

                with self.assertRaises(audit_vulnerabilities.AuditError):
                    audit_vulnerabilities.audit(
                        declaration(), lock_file=LOCK, open_url=opener
                    )

    def test_invalid_lock_prevents_an_unverified_audit(self):
        opener = mock.Mock()
        missing_lock = os.path.join(os.path.dirname(LOCK), "missing-test.lock")

        with self.assertRaisesRegex(audit_vulnerabilities.AuditError, "lock verification"):
            audit_vulnerabilities.audit(
                declaration(), lock_file=missing_lock, open_url=opener
            )
        opener.assert_not_called()

    def test_undeclared_dependency_role_is_not_silently_audited_as_runtime(self):
        spec = declaration()
        spec["packages"][0]["role"] = "development"

        with self.assertRaisesRegex(
            audit_vulnerabilities.AuditError, "valid name, version, or role"
        ):
            audit_vulnerabilities.runtime_packages(spec)


class AuditCommandFailsClosed(unittest.TestCase):
    def test_known_advisory_returns_failure_status(self):
        package = declaration()["packages"][0]
        output = io.StringIO()
        with mock.patch.object(
            audit_vulnerabilities.generate_lock,
            "load_declaration",
            return_value=declaration(),
        ), mock.patch.object(
            audit_vulnerabilities,
            "audit",
            return_value=[(package["name"], package["version"], "GHSA-abcd-1234-efgh")],
        ):
            with unittest.mock.patch("sys.stderr", output):
                result = audit_vulnerabilities.main()

        self.assertEqual(1, result)
        self.assertIn("GHSA-abcd-1234-efgh", output.getvalue())

    def test_unavailable_advisory_data_returns_failure_status(self):
        output = io.StringIO()
        with mock.patch.object(
            audit_vulnerabilities.generate_lock,
            "load_declaration",
            return_value=declaration(),
        ), mock.patch.object(
            audit_vulnerabilities,
            "audit",
            side_effect=audit_vulnerabilities.AuditError("OSV unavailable"),
        ):
            with unittest.mock.patch("sys.stderr", output):
                result = audit_vulnerabilities.main()

        self.assertEqual(1, result)
        self.assertIn("OSV unavailable", output.getvalue())


class RuntimeAuditWorkflow(unittest.TestCase):
    def test_workflow_is_a_blocking_pull_request_and_scheduled_gate(self):
        with open(WORKFLOW, "r", encoding="utf-8") as handle:
            text = handle.read()

        self.assertIn("pull_request:", text)
        self.assertIn("branches: [main]", text)
        self.assertIn("schedule:", text)
        self.assertIn("python tools/supply_chain/audit_vulnerabilities.py", text)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertNotIn("continue-on-error", text)
        for line in text.splitlines():
            if line.strip().startswith("uses:"):
                self.assertRegex(line, r"@[0-9a-f]{40}(?:\s|$)")


if __name__ == "__main__":
    unittest.main()

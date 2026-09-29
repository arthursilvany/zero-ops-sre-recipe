"""The contract-only schemas, and the register that has to agree with them.

T1.08's done criterion is that every entry in the register resolves to exactly one
file. That is checked here in both directions: an entry with no file fails, and a
file with no entry fails too. Only the first direction is stated in the task, but a
schema nobody registered is the same drift in the opposite direction, and it is the
one that happens by accident.

Most of these cases feed a schema something it must refuse. A schema observed only
to accept is not known to constrain anything.
"""

import json
import os
import re
import unittest

import jsonschema

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA_DIR = os.path.join(REPO_ROOT, "contracts", "schemas")
REGISTER = os.path.join(REPO_ROOT, "contracts", "schema-register.md")

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64

CONTRACT_ONLY = [
    "tool-policy",
    "capability-mapping",
    "change-set",
    "approval-ledger",
    "evidence-manifest",
    "query-catalogue",
    "workload-extension",
    "handoff-record",
    "assessment-result",
    "readiness-result",
]

DENY_CATEGORIES = [
    "write",
    "destructiveOperation",
    "arbitraryExecution",
    "secretsAccess",
    "selfApproval",
    "externalPublication",
    "agentCreatedSchedule",
]


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def validator(name):
    return jsonschema.Draft202012Validator(
        read_json(os.path.join(SCHEMA_DIR, "%s.schema.json" % name))
    )


def valid(name):
    """A minimal instance each schema must accept."""
    return json.loads(json.dumps(FIXTURES[name]))


FIXTURES = {
    "tool-policy": {
        "schemaVersion": "1.0.0",
        "name": "read-only-baseline",
        "defaultDecision": "deny",
        "conflictResolution": "denyWins",
        "onEvaluationFailure": "deny",
        "allowedCapabilityClasses": ["readMetrics", "readLogs"],
        "denyRules": [
            {"category": c, "justification": "Denied in v1."} for c in DENY_CATEGORIES
        ],
        "executionLimits": {
            "maxToolCalls": 200,
            "maxWallClockSeconds": 900,
            "maxResultSetRows": 1000,
            "perQueryTimeoutSeconds": 30,
        },
        "retryPolicy": {
            "maxAttempts": 3,
            "backoff": "exponential",
            "initialDelaySeconds": 2,
        },
    },
    "capability-mapping": {
        "schemaVersion": "1.2.0",
        "runtimeName": "example-runtime",
        "runtimeVersion": "1.0.0",
        "verificationState": "unverified",
        "entries": [
            {"capabilityClass": "readMetrics", "runtimeToolNames": ["example.readMetrics"]}
        ],
    },
    "change-set": {
        "schemaVersion": "1.0.0",
        "name": "example-proposal",
        "scopeContractHash": HASH_A,
        "lifecycleState": "proposed",
        "preconditions": ["The scope contract still resolves."],
        "blastRadius": {
            "affectedScopeEntries": ["<RESOURCE_GROUP_NAME>"],
            "reversible": True,
            "summary": "One resource group.",
        },
        "rollbackPlan": {
            "steps": ["Restore the prior configuration."],
            "maximumRollbackSeconds": 600,
        },
        "verificationMethod": {
            "steps": ["Re-read the configuration."],
            "successCriterion": "The configuration matches the prior state.",
        },
        "proposedAt": "2026-01-08T00:00:00Z",
        "canonicalHash": HASH_B,
    },
    "approval-ledger": {
        "schemaVersion": "1.0.0",
        "name": "example-ledger",
        "agentPrincipalObjectId": "<AGENT_OBJECT_ID>",
        "entries": [
            {
                "sequence": 1,
                "approvedArtifactHash": HASH_A,
                "decision": "approved",
                "deciderPrincipalObjectId": "<DECIDER_OBJECT_ID>",
                "decidedAt": "2026-01-08T00:00:00Z",
            },
            {
                "sequence": 2,
                "previousEntryHash": HASH_C,
                "approvedArtifactHash": HASH_B,
                "decision": "rejected",
                "deciderPrincipalObjectId": "<DECIDER_OBJECT_ID>",
                "decidedAt": "2026-01-09T00:00:00Z",
                "justification": "Blast radius too wide.",
            },
        ],
    },
    "evidence-manifest": {
        "schemaVersion": "1.0.0",
        "executionId": "<EXECUTION_ID>",
        "scopeContractHash": HASH_A,
        "startedAt": "2026-01-08T00:00:00Z",
        "entries": [
            {
                "id": "metric-sample",
                "observationState": "observed",
                "provenanceClassification": "platformTelemetry",
                "collectedAt": "2026-01-08T00:00:00Z",
                "freshnessSeconds": 60,
                "dataClassification": "internal",
                "contentHash": HASH_B,
            },
            {
                "id": "denied-source",
                "observationState": "unobserved",
                "provenanceClassification": "directObservation",
                "collectedAt": "2026-01-08T00:00:00Z",
                "freshnessSeconds": 0,
                "dataClassification": "internal",
                "unobservedReason": "accessDenied",
            },
        ],
        "conclusions": [
            {
                "id": "supported",
                "statement": "Throughput stayed within its band.",
                "evidenceRefs": ["metric-sample"],
            },
            {
                "id": "unsupported",
                "statement": "Capacity headroom is probably adequate.",
                "classification": "inferred",
            },
        ],
    },
    "query-catalogue": {
        "schemaVersion": "1.0.0",
        "name": "default-catalogue",
        "entries": [
            {
                "id": "error-rate",
                "origin": "frameworkDefault",
                "capabilityClass": "readLogs",
                "queryText": "<CATALOGUED_QUERY>",
                "queryHash": HASH_A,
                "reviewedAt": "2026-01-08T00:00:00Z",
            }
        ],
    },
    "workload-extension": {
        "schemaVersion": "1.0.0",
        "name": "example-extension",
        "targetResources": [{"kind": "resourceGroup", "selector": "<RESOURCE_GROUP_NAME>"}],
        "queries": [
            {
                "id": "consumer-query",
                "origin": "consumerExtension",
                "capabilityClass": "readLogs",
                "queryText": "<CONSUMER_QUERY>",
                "queryHash": HASH_B,
            }
        ],
        "networkAccessMode": "privateEndpoint",
        "schedule": {"cadence": "daily"},
        "reportShaping": {"sections": ["summary", "findings"]},
    },
    "handoff-record": {
        "schemaVersion": "1.0.0",
        "executionId": "<EXECUTION_ID>",
        "idempotencyKey": "<IDEMPOTENCY_KEY>",
        "turn": 1,
        "maxTurns": 5,
        "attempt": 1,
        "maxAttempts": 3,
        "autonomyLevel": "readOnly",
        "executionState": "running",
    },
    "assessment-result": {
        "schemaVersion": "1.0.0",
        "executionId": "<EXECUTION_ID>",
        "scopeContractHash": HASH_A,
        "status": "degraded",
        "confidence": "medium",
        "findings": [
            {
                "id": "latency-drift",
                "statement": "Latency rose over the window.",
                "severity": "medium",
                "evidenceRefs": ["metric-sample"],
            }
        ],
        "producedAt": "2026-01-08T00:00:00Z",
    },
    "readiness-result": {
        "schemaVersion": "1.0.0",
        "executionId": "<EXECUTION_ID>",
        "scopeContractHash": HASH_A,
        "status": "readyWithFindings",
        "confidence": "high",
        "checks": [
            {
                "id": "diagnostics-reachable",
                "outcome": "passed",
                "statement": "The diagnostics workspace responded.",
            }
        ],
        "producedAt": "2026-01-08T00:00:00Z",
    },
}


class RegisterAndDirectoryAgree(unittest.TestCase):
    """FR-05: exactly one schema per artifact, at exactly one path."""

    def registered_filenames(self):
        with open(REGISTER, "r", encoding="utf-8") as handle:
            text = handle.read()
        # Only the register table names files; the prose names none.
        return re.findall(r"`([a-z0-9-]+\.schema\.json)`", text)

    def test_the_register_names_something(self):
        # Guards every assertion below. A regex that matches nothing would
        # satisfy them all while checking nothing.
        self.assertGreaterEqual(len(self.registered_filenames()), 10)

    def test_every_register_entry_resolves_to_exactly_one_file(self):
        present = os.listdir(SCHEMA_DIR)
        for name in self.registered_filenames():
            with self.subTest(schema=name):
                self.assertEqual(
                    1,
                    present.count(name),
                    "%s resolves to %d files" % (name, present.count(name)),
                )

    def test_every_schema_file_has_a_register_entry(self):
        # The direction the task does not state. A schema nobody registered is
        # the same drift, and it is the one that happens by accident.
        registered = set(self.registered_filenames())
        for name in sorted(os.listdir(SCHEMA_DIR)):
            if name.endswith(".schema.json"):
                with self.subTest(schema=name):
                    self.assertIn(name, registered)

    def test_no_schema_is_registered_twice(self):
        names = self.registered_filenames()
        self.assertEqual(sorted(set(names)), sorted(names))

    def test_every_contract_only_schema_exists(self):
        for name in CONTRACT_ONLY:
            with self.subTest(schema=name):
                self.assertTrue(
                    os.path.isfile(os.path.join(SCHEMA_DIR, "%s.schema.json" % name))
                )


class EverySchemaAcceptsItsFixture(unittest.TestCase):
    def test_each_fixture_validates(self):
        for name in CONTRACT_ONLY:
            with self.subTest(schema=name):
                validator(name).validate(valid(name))

    def test_an_unknown_property_is_rejected_everywhere(self):
        for name in CONTRACT_ONLY:
            document = valid(name)
            document["somethingNobodyDeclared"] = "x"
            with self.subTest(schema=name):
                with self.assertRaises(jsonschema.ValidationError):
                    validator(name).validate(document)

    def test_an_inline_secret_cannot_be_added_anywhere(self):
        for name in CONTRACT_ONLY:
            document = valid(name)
            document["clientSecret"] = "not-a-real-value"
            with self.subTest(schema=name):
                with self.assertRaises(jsonschema.ValidationError):
                    validator(name).validate(document)

    def test_a_missing_version_is_rejected_everywhere(self):
        for name in CONTRACT_ONLY:
            document = {k: v for k, v in valid(name).items() if k != "schemaVersion"}
            with self.subTest(schema=name):
                with self.assertRaises(jsonschema.ValidationError):
                    validator(name).validate(document)


class TheToolPolicyCannotFailOpen(unittest.TestCase):
    def reject(self, document):
        with self.assertRaises(jsonschema.ValidationError):
            validator("tool-policy").validate(document)

    def test_a_permissive_default_is_inexpressible(self):
        document = valid("tool-policy")
        document["defaultDecision"] = "allow"
        self.reject(document)

    def test_allow_winning_a_conflict_is_inexpressible(self):
        document = valid("tool-policy")
        document["conflictResolution"] = "allowWins"
        self.reject(document)

    def test_failing_open_on_evaluation_error_is_inexpressible(self):
        document = valid("tool-policy")
        document["onEvaluationFailure"] = "allow"
        self.reject(document)

    def test_dropping_any_one_deny_rule_is_rejected(self):
        # FR-52 names seven categories. minItems plus uniqueItems over a
        # seven-member enum is what forces all seven, so removing any one
        # must fail regardless of which one it is.
        for index in range(len(DENY_CATEGORIES)):
            document = valid("tool-policy")
            document["denyRules"] = [
                r for i, r in enumerate(document["denyRules"]) if i != index
            ]
            with self.subTest(dropped=DENY_CATEGORIES[index]):
                self.reject(document)

    def test_padding_with_duplicates_cannot_fake_the_seven(self):
        # Without uniqueItems, minItems alone would be satisfied by repeating
        # one category seven times.
        document = valid("tool-policy")
        document["denyRules"] = [
            {"category": "write", "justification": "Denied in v1."}
        ] * 7
        self.reject(document)

    def test_an_eighth_category_is_rejected(self):
        document = valid("tool-policy")
        document["denyRules"].append(
            {"category": "somethingNew", "justification": "x"}
        )
        self.reject(document)

    def test_an_unjustified_deny_rule_is_rejected(self):
        document = valid("tool-policy")
        document["denyRules"][0] = {"category": "write"}
        self.reject(document)

    def test_an_absent_allow_list_is_rejected(self):
        document = {k: v for k, v in valid("tool-policy").items()
                    if k != "allowedCapabilityClasses"}
        self.reject(document)

    def test_an_empty_allow_list_is_accepted_because_it_denies_everything(self):
        document = valid("tool-policy")
        document["allowedCapabilityClasses"] = []
        validator("tool-policy").validate(document)

    def test_an_unclassified_capability_cannot_be_allowed(self):
        document = valid("tool-policy")
        document["allowedCapabilityClasses"] = ["writeResourceConfiguration"]
        self.reject(document)

    def test_dropping_any_execution_limit_is_rejected(self):
        for key in (
            "maxToolCalls",
            "maxWallClockSeconds",
            "maxResultSetRows",
            "perQueryTimeoutSeconds",
        ):
            document = valid("tool-policy")
            del document["executionLimits"][key]
            with self.subTest(limit=key):
                self.reject(document)


class TheCapabilityMappingNamesNoRuntime(unittest.TestCase):
    def test_the_schema_contains_no_runtime_identifier(self):
        # contracts/ is a declared core path, and FR-04 confines runtime names
        # to the binding layer. The schema describes the shape of a mapping and
        # must contain no mapping of its own. check-core enforces this over the
        # whole repository; asserting it here keeps the reason attached to the
        # file it constrains.
        with open(
            os.path.join(SCHEMA_DIR, "capability-mapping.schema.json"), "r", encoding="utf-8"
        ) as handle:
            text = handle.read().lower()
        declaration = read_json(os.path.join(REPO_ROOT, "contracts", "core-paths.json"))
        for term in declaration["runtimeIdentifiers"]:
            with self.subTest(term=term["term"]):
                self.assertNotIn(term["term"].lower(), text)

    def test_an_unverified_mapping_cannot_claim_a_reconciliation(self):
        document = valid("capability-mapping")
        document["reconciledAt"] = "2026-01-08T00:00:00Z"
        with self.assertRaises(jsonschema.ValidationError):
            validator("capability-mapping").validate(document)

    def test_a_reconciled_mapping_must_say_when(self):
        document = valid("capability-mapping")
        document["verificationState"] = "reconciled"
        with self.assertRaises(jsonschema.ValidationError):
            validator("capability-mapping").validate(document)

    def test_a_reconciled_mapping_must_say_what_it_saw(self):
        """A timestamp says a gate ran. Without the digest nothing says what
        the runtime advertised, so a capability added between two runs of the
        same version leaves the document still stamped reconciled."""
        document = valid("capability-mapping")
        document["verificationState"] = "reconciled"
        document["reconciledAt"] = "2026-01-08T00:00:00Z"
        with self.assertRaises(jsonschema.ValidationError):
            validator("capability-mapping").validate(document)

    def test_an_unverified_mapping_cannot_claim_a_capability_set(self):
        document = valid("capability-mapping")
        document["reconciledCapabilitySetHash"] = "a" * 64
        with self.assertRaises(jsonschema.ValidationError):
            validator("capability-mapping").validate(document)

    def test_a_reconciled_mapping_cannot_classify_nothing(self):
        """An empty reconciled mapping says the gate ran and found no
        capability at all, which is what a gate that never ran looks like."""
        document = valid("capability-mapping")
        document["verificationState"] = "reconciled"
        document["reconciledAt"] = "2026-01-08T00:00:00Z"
        document["reconciledCapabilitySetHash"] = "a" * 64
        document["entries"] = []
        with self.assertRaises(jsonschema.ValidationError):
            validator("capability-mapping").validate(document)

    def test_an_unverified_mapping_may_classify_nothing(self):
        """The control for the case above, and the state the binding layer in
        this repository is actually in."""
        document = valid("capability-mapping")
        document["entries"] = []
        validator("capability-mapping").validate(document)

    def test_a_reconciled_mapping_with_a_timestamp_is_accepted(self):
        document = valid("capability-mapping")
        document["verificationState"] = "reconciled"
        document["reconciledAt"] = "2026-01-08T00:00:00Z"
        document["reconciledCapabilitySetHash"] = "a" * 64
        validator("capability-mapping").validate(document)

    def test_an_uppercase_capability_set_digest_is_rejected(self):
        document = valid("capability-mapping")
        document["verificationState"] = "reconciled"
        document["reconciledAt"] = "2026-01-08T00:00:00Z"
        document["reconciledCapabilitySetHash"] = "A" * 64
        with self.assertRaises(jsonschema.ValidationError):
            validator("capability-mapping").validate(document)

    def test_a_declared_tool_list_absence_needs_a_reason_and_a_version(self):
        document = valid("capability-mapping")
        document["toolListUnavailable"] = {"reason": "x" * 40}
        with self.assertRaises(jsonschema.ValidationError):
            validator("capability-mapping").validate(document)

    def test_a_one_word_reason_is_rejected(self):
        """A reason nobody had to write is the same as no reason."""
        document = valid("capability-mapping")
        document["toolListUnavailable"] = {
            "reason": "none",
            "observedInRuntimeVersion": "1.0.0",
        }
        with self.assertRaises(jsonschema.ValidationError):
            validator("capability-mapping").validate(document)

    def test_a_complete_declared_absence_is_accepted(self):
        document = valid("capability-mapping")
        document["toolListUnavailable"] = {
            "reason": "x" * 40,
            "observedInRuntimeVersion": "1.0.0",
        }
        validator("capability-mapping").validate(document)

    def test_an_unpinned_runtime_version_is_rejected(self):
        document = {k: v for k, v in valid("capability-mapping").items()
                    if k != "runtimeVersion"}
        with self.assertRaises(jsonschema.ValidationError):
            validator("capability-mapping").validate(document)

    def test_a_class_mapping_to_nothing_is_rejected(self):
        document = valid("capability-mapping")
        document["entries"][0]["runtimeToolNames"] = []
        with self.assertRaises(jsonschema.ValidationError):
            validator("capability-mapping").validate(document)


class TheChangeSetCannotClaimApplication(unittest.TestCase):
    def reject(self, document):
        with self.assertRaises(jsonschema.ValidationError):
            validator("change-set").validate(document)

    def test_no_executed_state_exists(self):
        # FR-06: the contract defines the artifact and provides no execution
        # path. An artifact that cannot represent having run is a stronger
        # statement than one that merely is not run.
        for state in ("executed", "applied", "running", "completed"):
            document = valid("change-set")
            document["lifecycleState"] = state
            with self.subTest(state=state):
                self.reject(document)

    def test_the_declared_lifecycle_states_are_exactly_the_four(self):
        schema = read_json(os.path.join(SCHEMA_DIR, "change-set.schema.json"))
        self.assertEqual(
            ["proposed", "approved", "rejected", "withdrawn"],
            schema["properties"]["lifecycleState"]["enum"],
        )

    def test_a_proposal_without_a_rollback_plan_is_rejected(self):
        document = {k: v for k, v in valid("change-set").items() if k != "rollbackPlan"}
        self.reject(document)

    def test_a_rollback_plan_without_a_time_bound_is_rejected(self):
        document = valid("change-set")
        del document["rollbackPlan"]["maximumRollbackSeconds"]
        self.reject(document)

    def test_a_proposal_with_no_preconditions_is_rejected(self):
        document = valid("change-set")
        document["preconditions"] = []
        self.reject(document)

    def test_a_proposal_without_a_verification_criterion_is_rejected(self):
        document = valid("change-set")
        del document["verificationMethod"]["successCriterion"]
        self.reject(document)

    def test_an_unstated_blast_radius_is_rejected(self):
        document = valid("change-set")
        document["blastRadius"] = {"summary": "unknown"}
        self.reject(document)

    def test_a_proposal_not_bound_to_a_scope_is_rejected(self):
        document = {k: v for k, v in valid("change-set").items()
                    if k != "scopeContractHash"}
        self.reject(document)


class TheApprovalLedgerResistsRenaming(unittest.TestCase):
    def reject(self, document):
        with self.assertRaises(jsonschema.ValidationError):
            validator("approval-ledger").validate(document)

    def test_a_display_name_cannot_be_recorded_as_the_decider(self):
        # SEC-016. A display name can be changed to match, so recording one
        # would let self-approval be defeated by renaming.
        document = valid("approval-ledger")
        document["entries"][0]["deciderPrincipalObjectId"] = "Alex Operator"
        self.reject(document)

    def test_the_agent_principal_must_be_recorded(self):
        # Without it the self-approval comparison needs a second document,
        # and a check that spans documents is a check that can be skipped.
        document = {k: v for k, v in valid("approval-ledger").items()
                    if k != "agentPrincipalObjectId"}
        self.reject(document)

    def test_the_first_entry_cannot_reference_a_predecessor(self):
        document = valid("approval-ledger")
        document["entries"][0]["previousEntryHash"] = HASH_C
        self.reject(document)

    def test_a_later_entry_must_reference_its_predecessor(self):
        # The chain is what makes append-only checkable rather than promised.
        document = valid("approval-ledger")
        del document["entries"][1]["previousEntryHash"]
        self.reject(document)

    def test_a_pending_decision_is_inexpressible(self):
        document = valid("approval-ledger")
        document["entries"][0]["decision"] = "pending"
        self.reject(document)

    def test_an_entry_approving_a_name_instead_of_a_hash_is_rejected(self):
        document = valid("approval-ledger")
        document["entries"][0]["approvedArtifactHash"] = "example-proposal"
        self.reject(document)

    def test_a_zero_sequence_is_rejected(self):
        document = valid("approval-ledger")
        document["entries"][0]["sequence"] = 0
        self.reject(document)

    def test_an_empty_ledger_is_accepted_because_it_states_a_fact(self):
        document = valid("approval-ledger")
        document["entries"] = []
        validator("approval-ledger").validate(document)


class TheEvidenceManifestHoldsNoContent(unittest.TestCase):
    def reject(self, document):
        with self.assertRaises(jsonschema.ValidationError):
            validator("evidence-manifest").validate(document)

    def test_no_entry_property_can_hold_retrieved_content(self):
        # NEG-F. This is what makes the injection and leakage mitigations
        # structural rather than scan-based.
        for name in ("content", "body", "raw", "payload", "logText", "responseBody"):
            document = valid("evidence-manifest")
            document["entries"][0][name] = "some retrieved text"
            with self.subTest(property=name):
                self.reject(document)

    def test_an_observed_entry_without_a_content_hash_is_rejected(self):
        document = valid("evidence-manifest")
        del document["entries"][0]["contentHash"]
        self.reject(document)

    def test_an_unobserved_entry_cannot_carry_a_content_hash(self):
        # Substituting a digest for something never seen is exactly the
        # defaulting the data model forbids: a zero hash validates, sorts and
        # compares like a real one.
        document = valid("evidence-manifest")
        document["entries"][1]["contentHash"] = "0" * 64
        self.reject(document)

    def test_an_unobserved_entry_must_say_why(self):
        document = valid("evidence-manifest")
        del document["entries"][1]["unobservedReason"]
        self.reject(document)

    def test_an_observed_entry_cannot_carry_an_unobserved_reason(self):
        document = valid("evidence-manifest")
        document["entries"][0]["unobservedReason"] = "timedOut"
        self.reject(document)

    def test_access_denied_is_a_first_class_reason(self):
        schema = read_json(os.path.join(SCHEMA_DIR, "evidence-manifest.schema.json"))
        reasons = schema["$defs"]["evidenceEntry"]["properties"]["unobservedReason"]["enum"]
        self.assertIn("accessDenied", reasons)

    def test_dropping_any_required_entry_attribute_is_rejected(self):
        for key in (
            "provenanceClassification",
            "collectedAt",
            "freshnessSeconds",
            "dataClassification",
            "observationState",
        ):
            document = valid("evidence-manifest")
            del document["entries"][0][key]
            with self.subTest(attribute=key):
                self.reject(document)

    def test_a_conclusion_citing_evidence_and_calling_itself_inferred_is_rejected(self):
        document = valid("evidence-manifest")
        document["conclusions"][0]["classification"] = "inferred"
        self.reject(document)

    def test_a_conclusion_with_neither_evidence_nor_classification_is_rejected(self):
        document = valid("evidence-manifest")
        del document["conclusions"][1]["classification"]
        self.reject(document)

    def test_a_conclusion_citing_an_empty_evidence_list_is_rejected(self):
        document = valid("evidence-manifest")
        document["conclusions"][0]["evidenceRefs"] = []
        self.reject(document)

    def test_an_incomplete_execution_simply_omits_its_end(self):
        # FR-07. The absence is the representation; a substituted end time
        # would make an unfinished run look finished.
        document = valid("evidence-manifest")
        self.assertNotIn("completedAt", document)
        validator("evidence-manifest").validate(document)


class TheQueryCatalogueStaysSeparable(unittest.TestCase):
    def test_an_entry_must_declare_its_origin(self):
        document = valid("query-catalogue")
        del document["entries"][0]["origin"]
        with self.assertRaises(jsonschema.ValidationError):
            validator("query-catalogue").validate(document)

    def test_an_entry_without_an_integrity_hash_is_rejected(self):
        document = valid("query-catalogue")
        del document["entries"][0]["queryHash"]
        with self.assertRaises(jsonschema.ValidationError):
            validator("query-catalogue").validate(document)

    def test_an_unreviewed_entry_is_rejected(self):
        document = valid("query-catalogue")
        del document["entries"][0]["reviewedAt"]
        with self.assertRaises(jsonschema.ValidationError):
            validator("query-catalogue").validate(document)

    def test_an_extension_cannot_pose_as_a_framework_default(self):
        # SC-13 separability. A workload extension pins origin, so a consumer
        # query cannot be labelled as shipped content.
        document = valid("workload-extension")
        document["queries"][0]["origin"] = "frameworkDefault"
        with self.assertRaises(jsonschema.ValidationError):
            validator("workload-extension").validate(document)


class TheWorkloadExtensionSuppliesInputsNotBehaviour(unittest.TestCase):
    def reject(self, document):
        with self.assertRaises(jsonschema.ValidationError):
            validator("workload-extension").validate(document)

    def test_an_extension_targeting_nothing_is_rejected(self):
        document = valid("workload-extension")
        document["targetResources"] = []
        self.reject(document)

    def test_an_extension_cannot_supply_a_command_or_a_script(self):
        # An extension point that accepted code would put consumer content on
        # the execution path, making the read-only boundary depend on what was
        # written rather than on what is possible.
        for name in ("script", "command", "hook", "exec", "payload"):
            document = valid("workload-extension")
            document[name] = "echo hello"
            with self.subTest(property=name):
                self.reject(document)

    def test_a_free_form_schedule_expression_is_inexpressible(self):
        # Agent-created schedules are one of the seven denied categories.
        document = valid("workload-extension")
        document["schedule"] = {"cadence": "*/5 * * * *"}
        self.reject(document)

    def test_an_unknown_report_section_is_rejected(self):
        document = valid("workload-extension")
        document["reportShaping"]["sections"] = ["arbitraryConsumerText"]
        self.reject(document)

    def test_an_override_that_overrides_nothing_is_rejected(self):
        document = valid("workload-extension")
        document["executionLimitOverrides"] = {}
        self.reject(document)

    def test_an_extension_cannot_widen_the_capability_set(self):
        document = valid("workload-extension")
        document["queries"][0]["capabilityClass"] = "writeConfiguration"
        self.reject(document)


class TheHandoffRecordPinsAutonomy(unittest.TestCase):
    def reject(self, document):
        with self.assertRaises(jsonschema.ValidationError):
            validator("handoff-record").validate(document)

    def test_a_write_capable_autonomy_level_is_inexpressible(self):
        for level in ("readWrite", "full", "autonomous"):
            document = valid("handoff-record")
            document["autonomyLevel"] = level
            with self.subTest(level=level):
                self.reject(document)

    def test_an_absent_idempotency_key_is_rejected(self):
        # Without it a retry reads as new work, which double-counts evidence
        # and can exceed a limit each half respected individually.
        document = {k: v for k, v in valid("handoff-record").items()
                    if k != "idempotencyKey"}
        self.reject(document)

    def test_a_zero_turn_is_rejected(self):
        document = valid("handoff-record")
        document["turn"] = 0
        self.reject(document)

    def test_incomplete_and_failed_are_distinct_states(self):
        schema = read_json(os.path.join(SCHEMA_DIR, "handoff-record.schema.json"))
        states = schema["properties"]["executionState"]["enum"]
        for expected in ("incomplete", "failed", "accessDenied"):
            self.assertIn(expected, states)

    def test_an_identifier_cannot_smuggle_a_resource_path(self):
        document = valid("handoff-record")
        document["executionId"] = "/subscriptions/x/resourceGroups/y"
        self.reject(document)


class TheResultsDeclareTheirStanding(unittest.TestCase):
    def test_a_finding_cannot_both_cite_evidence_and_call_itself_inferred(self):
        document = valid("assessment-result")
        document["findings"][0]["classification"] = "inferred"
        with self.assertRaises(jsonschema.ValidationError):
            validator("assessment-result").validate(document)

    def test_a_finding_with_neither_is_rejected(self):
        document = valid("assessment-result")
        del document["findings"][0]["evidenceRefs"]
        with self.assertRaises(jsonschema.ValidationError):
            validator("assessment-result").validate(document)

    def test_indeterminate_is_available_so_absence_is_not_reported_as_health(self):
        document = valid("assessment-result")
        document["status"] = "indeterminate"
        document["confidence"] = "indeterminate"
        validator("assessment-result").validate(document)

    def test_status_and_confidence_are_separate_properties(self):
        # Collapsing them would lose the difference between a degraded finding
        # held with low confidence and one held with high confidence.
        schema = read_json(os.path.join(SCHEMA_DIR, "assessment-result.schema.json"))
        self.assertIn("status", schema["required"])
        self.assertIn("confidence", schema["required"])

    def test_a_readiness_check_can_report_that_it_never_ran(self):
        # not-evaluated must be distinct from passed, or a check that never ran
        # counts towards readiness.
        document = valid("readiness-result")
        document["checks"][0]["outcome"] = "notEvaluated"
        validator("readiness-result").validate(document)

    def test_ready_with_findings_is_distinct_from_ready(self):
        schema = read_json(os.path.join(SCHEMA_DIR, "readiness-result.schema.json"))
        statuses = schema["$defs"]["readinessStatus"]["enum"]
        self.assertIn("ready", statuses)
        self.assertIn("readyWithFindings", statuses)

    def test_an_unknown_outcome_is_rejected(self):
        document = valid("readiness-result")
        document["checks"][0]["outcome"] = "probablyFine"
        with self.assertRaises(jsonschema.ValidationError):
            validator("readiness-result").validate(document)

    def test_a_result_not_bound_to_a_scope_is_rejected(self):
        for name in ("assessment-result", "readiness-result"):
            document = {k: v for k, v in valid(name).items() if k != "scopeContractHash"}
            with self.subTest(schema=name):
                with self.assertRaises(jsonschema.ValidationError):
                    validator(name).validate(document)


class DiagnosisIsNotProposal(unittest.TestCase):
    """FR-57, asserted structurally rather than by convention."""

    def test_a_change_set_is_not_a_valid_assessment_result(self):
        with self.assertRaises(jsonschema.ValidationError):
            validator("assessment-result").validate(valid("change-set"))

    def test_an_assessment_result_is_not_a_valid_change_set(self):
        with self.assertRaises(jsonschema.ValidationError):
            validator("change-set").validate(valid("assessment-result"))

    def test_an_assessment_result_cannot_carry_a_rollback_plan(self):
        # If it could, a diagnostic output would start to look like a proposal,
        # which is the confusion FR-57 exists to prevent.
        document = valid("assessment-result")
        document["rollbackPlan"] = {"steps": ["x"], "maximumRollbackSeconds": 1}
        with self.assertRaises(jsonschema.ValidationError):
            validator("assessment-result").validate(document)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryAssetTests(unittest.TestCase):
    def test_json_contracts_are_closed_and_parseable(self) -> None:
        schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
        self.assertEqual(len(schema_paths), 18)
        for path in schema_paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(document["type"], "object")
            self.assertFalse(document["additionalProperties"], path.name)

        values = json.loads(
            (ROOT / "deploy/helm/proof-harness/values.schema.json").read_text(encoding="utf-8")
        )
        digest = values["properties"]["image"]["properties"]["digest"]
        self.assertEqual(digest["pattern"], "^sha256:[0-9a-f]{64}$")
        self.assertEqual(values["properties"]["replicaCount"]["minimum"], 2)

    def test_postgres_migration_is_tenant_qualified_and_fail_closed(self) -> None:
        sql = (ROOT / "migrations/V001__proof_harness_core.sql").read_text(encoding="utf-8")
        self.assertGreaterEqual(sql.count("tenant_id uuid NOT NULL"), 20)
        self.assertGreaterEqual(sql.count("project_id uuid NOT NULL"), 20)
        self.assertGreaterEqual(sql.count("FORCE ROW LEVEL SECURITY"), 1)
        self.assertIn("proof_harness.current_tenant_id()", sql)
        self.assertIn("proof_harness.current_project_id()", sql)
        self.assertIn("tenant_project_isolation", sql)
        self.assertIn("assert_event_fence", sql)
        self.assertIn("reject_immutable_mutation", sql)
        self.assertIn("environment_authority_revocations", sql)
        self.assertIn("external_signature_revocations", sql)
        self.assertIn("attested_status", sql)
        self.assertIn("certification_authority", sql)
        self.assertIn("'AWAITING_REVIEW'", sql)
        self.assertIn("'TIMED_OUT'", sql)
        self.assertIn("baseline_digest text NOT NULL", sql)
        self.assertIn("completion_review_signature_required", sql)
        self.assertIn("effective_completion_reviews", sql)
        self.assertIn("external completion decision lacks a live bound signature receipt", sql)
        self.assertNotRegex(sql, re.compile(r"REPLACE_WITH|SET_ME|TODO|FIXME", re.IGNORECASE))
        self.assertNotIn("ON DELETE CASCADE", sql)

    def test_helm_defaults_require_exact_external_configuration(self) -> None:
        values = (ROOT / "deploy/helm/proof-harness/values.yaml").read_text(encoding="utf-8")
        deployment = (
            ROOT / "deploy/helm/proof-harness/templates/deployment.yaml"
        ).read_text(encoding="utf-8")
        network = (
            ROOT / "deploy/helm/proof-harness/templates/networkpolicy.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn('repository: ""', values)
        self.assertIn('digest: ""', values)
        self.assertIn('existingSecret: ""', values)
        self.assertIn("@{{ .Values.image.digest }}", deployment)
        self.assertIn("runAsNonRoot: true", deployment)
        self.assertIn("readOnlyRootFilesystem: true", deployment)
        self.assertIn("allowPrivilegeEscalation: false", deployment)
        self.assertIn("automountServiceAccountToken: false", deployment)
        self.assertIn("ingress: []", network)
        self.assertNotIn("0.0.0.0/0", network)

    def test_observability_catalog_excludes_sensitive_labels(self) -> None:
        catalog = (ROOT / "observability/metrics.yaml").read_text(encoding="utf-8")
        for forbidden in (
            "tenant_id",
            "project_id",
            "actor_id",
            "repository_url",
            "source_path",
            "evidence_id",
        ):
            self.assertIn(f"- {forbidden}", catalog)
            self.assertNotRegex(catalog, rf"labels:\s*\[[^\]]*\b{forbidden}\b")
        alerts = (ROOT / "observability/alerts.yaml").read_text(encoding="utf-8")
        self.assertIn("ProofHarnessStatusInflationAttempt", alerts)
        self.assertIn("ProofHarnessUnknownExternalOutcome", alerts)
        self.assertIn("ProofHarnessCriticalObligationBlocked", alerts)

    def test_openapi_never_grants_identity_from_transport_payload(self) -> None:
        spec = (ROOT / "openapi/proof-harness-v3.openapi.yaml").read_text(encoding="utf-8")
        self.assertIn("request bodies cannot grant authority", spec)
        self.assertIn("Idempotency-Key", spec)
        self.assertIn("oauth2", spec)
        self.assertIn("/v3/invocations:", spec)
        self.assertIn("READY_FOR_EXTERNAL_GATE", spec)
        self.assertNotIn("CERTIFIED_COMPLETE", spec)

    def test_public_contracts_require_the_full_revision_and_release_gate_set(self) -> None:
        invocation = json.loads(
            (ROOT / "schemas/invocation.schema.json").read_text(encoding="utf-8")
        )
        required_revisions = set(
            invocation["properties"]["revisionSet"]["required"]
        )
        self.assertEqual(
            required_revisions,
            {
                "revisionSetId",
                "source",
                "baseline",
                "requirements",
                "policy",
                "workflow",
                "modelRoute",
                "toolchain",
                "environment",
                "domainPack",
            },
        )
        revision_set = json.loads(
            (ROOT / "schemas/revision-set.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            set(revision_set["required"]),
            {
                "revisionSetId",
                "tenantId",
                "projectId",
                "goalId",
                "source",
                "baseline",
                "requirements",
                "policy",
                "workflow",
                "modelRoute",
                "toolchain",
                "environment",
                "domainPack",
                "createdAt",
            },
        )

        review = json.loads(
            (ROOT / "schemas/completion-review.schema.json").read_text(
                encoding="utf-8"
            )
        )
        gate_results = review["properties"]["gateResults"]
        self.assertEqual(
            set(gate_results["required"]),
            {"P05", "E0", "E1", "E2", "E3", "E4", "E5"},
        )
        self.assertFalse(gate_results["additionalProperties"])
        signature = review["properties"]["externalSignature"]
        self.assertTrue(
            {
                "receiptId",
                "tenantId",
                "projectId",
                "signerIdentity",
                "providerId",
                "verificationEvidenceId",
                "issuedAt",
                "expiresAt",
                "independent",
                "certificationAuthority",
                "attestedStatus",
            }.issubset(signature["required"])
        )
        self.assertEqual(signature["properties"]["independent"], {"const": True})

        certificate = json.loads(
            (ROOT / "schemas/completion-certificate.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            certificate["$defs"]["digest"]["pattern"],
            "^sha256:[0-9a-f]{64}$",
        )
        self.assertTrue(
            {
                "productionAssessment",
                "signatureReceiptId",
                "signatureReceiptSha256",
            }.issubset(certificate["required"])
        )
        certified_rule = certificate["allOf"][1]["then"]["properties"]
        self.assertEqual(certified_rule["productionAssessment"], {"const": True})
        self.assertEqual(certified_rule["gateResults"]["minItems"], 7)
        self.assertEqual(certified_rule["gateResults"]["maxItems"], 7)
        self.assertEqual(
            len(certified_rule["gateResults"]["allOf"]),
            7,
        )
        proof_statuses = certificate["properties"]["statusCounts"][
            "propertyNames"
        ]["enum"]
        self.assertNotIn("FAIL", proof_statuses)
        self.assertIn("REFUTED_WITH_COUNTEREXAMPLE", proof_statuses)

        passing_review = review["$defs"]["allPassingProductionGates"]
        self.assertEqual(
            set(passing_review["required"]),
            {"P05", "E0", "E1", "E2", "E3", "E4", "E5"},
        )
        self.assertTrue(
            all(
                definition == {"const": "PASS"}
                for definition in passing_review["properties"].values()
            )
        )

    def test_supply_chain_records_do_not_manufacture_release_evidence(self) -> None:
        sbom = json.loads((ROOT / "supply-chain/sbom.cdx.json").read_text(encoding="utf-8"))
        policy = json.loads(
            (ROOT / "supply-chain/release-policy.json").read_text(encoding="utf-8")
        )
        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        source = sbom["components"][0]
        properties = {item["name"]: item["value"] for item in source["properties"]}
        self.assertEqual(properties["ai.elmos.executed"], "false")
        self.assertEqual(
            properties["ai.elmos.selective-inert-data-materialized"], "true"
        )
        self.assertEqual(
            properties["ai.elmos.executable-content-materialized"], "false"
        )
        self.assertEqual(properties["ai.elmos.approved-license"], "ABSENT")
        self.assertEqual(properties["ai.elmos.signature"], "ABSENT")
        self.assertEqual(policy["local_maximum"], "READY_FOR_EXTERNAL_GATE")
        self.assertEqual(policy["release_authority"], "EXTERNAL_REQUIRED")
        self.assertTrue(
            all(value == "NOT_RUN" for value in policy["required_before_distribution"].values())
        )


if __name__ == "__main__":
    unittest.main()

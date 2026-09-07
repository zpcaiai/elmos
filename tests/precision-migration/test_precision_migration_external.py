from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.precision_migration.external import (
    ExternalProfileRegistry,
    _campaign_digest,
    _installed_identity,
    evaluate_external_campaign,
    scaffold,
)
from scripts.precision_migration.check_external_readiness import evaluate_preflight
from scripts.precision_migration.production_runtime import (
    OperationLedger,
    ProductionRuntimeError,
    TrustedAdapterRegistry,
    execute_operation,
)
from scripts.precision_migration.trust import (
    TrustStore,
    canonical_bytes,
    canonical_digest,
    verify_content_reference,
)


NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
ROLES = (
    "external-campaign-authorizer",
    "native-verifier",
    "independent-verifier",
    "customer-workload-verifier",
    "customer-workload-authorizer",
    "production-change-approver",
    "production-hsm-attestor",
    "production-controller",
    "rollback-controller",
    "external-certifier",
    "external-adapter-admin",
    "external-execution-authorizer",
)


class PrecisionMigrationExternalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="precision-external-tests-")
        cls.root = Path(cls.temporary.name)
        cls.keys: dict[str, Path] = {}
        keys = []
        for role in ROLES:
            private = cls.root / f"{role}.private.pem"
            public = cls.root / f"{role}.public.pem"
            subprocess.run(
                ["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(private)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)],
                check=True,
                capture_output=True,
            )
            cls.keys[role] = private
            keys.append(
                {
                    "key_id": f"external-test-{role}",
                    "roles": [role],
                    "public_key_path": public.name,
                    "not_before": "2025-01-01T00:00:00Z",
                    "not_after": "2030-01-01T00:00:00Z",
                    "revoked": False,
                }
            )
        cls.trust_path = cls.root / "external-trust-store.json"
        cls.trust_path.write_text(
            json.dumps({"schema_version": 1, "keys": keys, "revoked_record_ids": []}),
            encoding="utf-8",
        )
        cls.trust = TrustStore.load(cls.trust_path)
        cls.profiles = ExternalProfileRegistry.load()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def setUp(self) -> None:
        self.case_root = Path(tempfile.mkdtemp(prefix="case-", dir=self.root))

    def sign(self, role: str, payload: dict[str, object]) -> dict[str, object]:
        payload_path = self.case_root / f"payload-{role}-{payload['record_id']}.json"
        signature_path = self.case_root / f"signature-{role}-{payload['record_id']}.bin"
        payload_path.write_bytes(canonical_bytes(payload))
        subprocess.run(
            [
                "openssl", "pkeyutl", "-sign", "-inkey", str(self.keys[role]),
                "-rawin", "-in", str(payload_path), "-out", str(signature_path),
            ],
            check=True,
            capture_output=True,
        )
        return {
            "algorithm": "ed25519",
            "key_id": f"external-test-{role}",
            "payload": payload,
            "signature": base64.b64encode(signature_path.read_bytes()).decode("ascii"),
        }

    def content_ref(self, path: Path, media_type: str = "application/json") -> dict[str, object]:
        content = path.read_bytes()
        return {
            "uri": path.resolve().as_uri(),
            "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "media_type": media_type,
        }

    def write_json(self, name: str, payload: object) -> tuple[Path, dict[str, object]]:
        path = self.case_root / name
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return path, self.content_ref(path)

    def test_all_557_non_b16_skills_have_exact_external_profiles(self) -> None:
        self.assertEqual(557, len(self.profiles.by_skill))
        self.assertEqual(557, len({item["profile_digest"] for item in self.profiles.by_skill.values()}))
        self.assertTrue(all(len(item["required_stages"]) == 4 for item in self.profiles.by_skill.values()))
        self.assertFalse(any(item["handler_id"].startswith("batch29-route-executor-v1:") for item in self.profiles.by_skill.values()))

    def test_checked_in_external_state_is_honestly_not_run(self) -> None:
        result = scaffold()
        self.assertEqual("NOT_READY", result["decision"])
        self.assertEqual(0, result["verified_skill_count"])
        self.assertFalse(result["production_operation_authorized"])
        self.assertEqual("NOT_CERTIFIED", result["production_certification"])
        self.assertEqual({"NOT_RUN"}, set(result["stage_states"].values()))

    def corpus(self, partition: str, *, duplicate_from: dict[str, str] | None = None) -> tuple[dict[str, str], dict[str, object]]:
        cases: dict[str, str] = {}
        rows = []
        for skill, profile in sorted(self.profiles.by_skill.items()):
            case_digest = duplicate_from[skill] if duplicate_from else canonical_digest(
                {"partition": partition, "skill": skill, "profile_digest": profile["profile_digest"]}
            )
            cases[skill] = case_digest
            rows.append({"skill": skill, "profile_digest": profile["profile_digest"], "case_digest": case_digest})
        _, reference = self.write_json(
            f"corpus-{partition}.json",
            {
                "schema_version": 1,
                "namespace": "precision-migration-b01-44",
                "corpus_id": f"corpus-{partition}",
                "partition": partition,
                "cases": rows,
            },
        )
        return cases, reference

    def base_campaign(self) -> tuple[dict[str, object], dict[str, dict[str, str]]]:
        development, development_ref = self.corpus("development")
        holdout, holdout_ref = self.corpus("holdout")
        representative, representative_ref = self.corpus("representative")
        _, canary_ref = self.write_json(
            "canary-plan.json",
            {
                "schema_version": 1,
                "plan_id": "canary-plan-one",
                "environment": "production-equivalent-test-environment",
                "stages": [
                    {
                        "stage_id": "stage-one",
                        "traffic_percent": 1,
                        "minimum_observation_seconds": 60,
                        "required_sli": ["error-rate", "latency", "data-integrity"],
                        "rollback_on_failure": True,
                    },
                    {
                        "stage_id": "stage-two",
                        "traffic_percent": 5,
                        "minimum_observation_seconds": 300,
                        "required_sli": ["error-rate", "latency", "data-integrity"],
                        "rollback_on_failure": True,
                    },
                ],
                "canary_adapter_id": "canary-controller-one",
                "rollback_adapter_id": "rollback-controller-one",
                "approval_required": True,
            },
        )
        _, rollback_ref = self.write_json(
            "rollback-plan.json",
            {
                "schema_version": 1,
                "plan_id": "rollback-plan-one",
                "environment": "production-equivalent-test-environment",
                "target_digest": "sha256:" + "7" * 64,
                "rollback_adapter_id": "rollback-controller-one",
                "maximum_rto_seconds": 300,
                "verification_checks": ["source-capacity", "data-integrity", "route-restoration"],
                "data_reconciliation_required": True,
                "approval_required": True,
            },
        )
        campaign: dict[str, object] = {
            "schema_version": 1,
            "namespace": "precision-migration-b01-44",
            "campaign_id": "campaign-external-one",
            "profile_registry_digest": self.profiles.digest,
            "package_identity": _installed_identity(),
            "environment": "production-equivalent-test-environment",
            "tenant_id": "customer-tenant-one",
            "purpose": "authorized-migration-qualification",
            "corpora": {
                "development": development_ref,
                "holdout": holdout_ref,
                "representative": representative_ref,
            },
            "plans": {"canary": canary_ref, "rollback": rollback_ref},
            "stage_receipts": {},
        }
        return campaign, {"development": development, "holdout": holdout, "representative": representative}

    def campaign_digest(self, campaign: dict[str, object]) -> str:
        corpus_observations = {
            name: verify_content_reference(reference, (self.case_root.resolve(),))
            for name, reference in campaign["corpora"].items()
        }
        plan_observations = {
            name: verify_content_reference(reference, (self.case_root.resolve(),))
            for name, reference in campaign["plans"].items()
        }
        return _campaign_digest(campaign, self.profiles, corpus_observations, plan_observations)

    def add_campaign_authorization(self, campaign: dict[str, object], digest: str) -> None:
        campaign["campaign_authorization"] = self.sign(
            "external-campaign-authorizer",
            {
                "record_type": "PRECISION_EXTERNAL_CAMPAIGN_AUTHORIZATION",
                "record_id": "campaign-auth-one",
                "actor_id": "campaign-authorizer-actor",
                "campaign_id": campaign["campaign_id"],
                "campaign_digest": digest,
                "decision": "APPROVED",
                "issued_at": "2026-01-01T00:00:00Z",
                "expires_at": "2029-01-01T00:00:00Z",
            },
        )

    def add_stage(
        self,
        campaign: dict[str, object],
        cases: dict[str, dict[str, str]],
        stage: str,
        partition: str,
        role: str,
        digest: str,
        executor: str,
        verifier: str,
    ) -> None:
        bundle = self.case_root / f"bundle-{stage}.bin"
        bundle.write_bytes((stage + "\n").encode("utf-8"))
        results = []
        for skill, profile in sorted(self.profiles.by_skill.items()):
            row = {
                "skill": skill,
                "profile_digest": profile["profile_digest"],
                "case_digest": cases[partition][skill],
                "state": "PASSED",
                "exit_code": 0,
                "environment_digest": canonical_digest({"stage": stage, "environment": campaign["environment"]}),
                "executor": executor,
                "verifier": verifier,
                "replay_command": ["precision-external-runner", "--stage", stage, "--skill", skill],
            }
            results.append({**row, "result_digest": canonical_digest(row)})
        _, manifest_ref = self.write_json(
            f"results-{stage}.json",
            {
                "schema_version": 1,
                "namespace": "precision-migration-b01-44",
                "campaign_id": campaign["campaign_id"],
                "stage": stage,
                "evidence_bundle": self.content_ref(bundle, "application/octet-stream"),
                "results": results,
            },
        )
        corpus_ref = campaign["corpora"][partition]
        attestation = self.sign(
            role,
            {
                "record_type": "PRECISION_EXTERNAL_STAGE_ATTESTATION",
                "record_id": f"attestation-{stage}",
                "actor_id": verifier,
                "campaign_id": campaign["campaign_id"],
                "campaign_digest": digest,
                "stage": stage,
                "manifest_digest": manifest_ref["digest"],
                "corpus_digest": corpus_ref["digest"],
                "state": "PASSED",
                "executor": executor,
                "verifier": verifier,
                "issued_at": "2026-01-01T00:00:00Z",
                "expires_at": "2029-01-01T00:00:00Z",
            },
        )
        campaign["stage_receipts"][stage] = {"manifest": manifest_ref, "attestation": attestation}

    def complete_external_campaign(self) -> dict[str, object]:
        campaign, cases = self.base_campaign()
        digest = self.campaign_digest(campaign)
        self.add_campaign_authorization(campaign, digest)
        self.add_stage(campaign, cases, "native_source_execution", "development", "native-verifier", digest, "source-executor", "source-verifier")
        self.add_stage(campaign, cases, "native_target_execution", "development", "native-verifier", digest, "target-executor", "target-verifier")
        self.add_stage(campaign, cases, "independent_holdout", "holdout", "independent-verifier", digest, "holdout-executor", "holdout-verifier")
        self.add_stage(campaign, cases, "representative_customer_workload", "representative", "customer-workload-verifier", digest, "customer-executor", "customer-verifier")
        campaign["customer_authorization"] = self.sign(
            "customer-workload-authorizer",
            {
                "record_type": "PRECISION_CUSTOMER_WORKLOAD_AUTHORIZATION",
                "record_id": "customer-workload-auth-one",
                "actor_id": "customer-data-owner",
                "campaign_id": campaign["campaign_id"],
                "tenant_id": campaign["tenant_id"],
                "purpose": campaign["purpose"],
                "corpus_digest": campaign["corpora"]["representative"]["digest"],
                "decision": "APPROVED",
                "issued_at": "2026-01-01T00:00:00Z",
                "expires_at": "2029-01-01T00:00:00Z",
            },
        )
        return campaign

    def test_corpus_overlap_is_rejected_before_external_execution(self) -> None:
        campaign, _ = self.base_campaign()
        development_payload = json.loads(Path(campaign["corpora"]["development"]["uri"].removeprefix("file://")).read_text())
        _, overlapping = self.write_json(
            "corpus-overlap.json",
            {**development_payload, "corpus_id": "corpus-holdout-overlap", "partition": "holdout"},
        )
        campaign["corpora"]["holdout"] = overlapping
        result = evaluate_external_campaign(
            campaign,
            evidence_roots=[self.case_root],
            trust_store=self.trust,
            profile_registry=self.profiles,
            now=NOW,
        )
        self.assertEqual("REJECTED", result["decision"])
        self.assertTrue(any("overlap" in failure for failure in result["failures"]))

    def test_canary_plan_requires_monotonic_rollbackable_stages(self) -> None:
        campaign, _ = self.base_campaign()
        _, invalid = self.write_json(
            "invalid-canary-plan.json",
            {
                "schema_version": 1,
                "plan_id": "canary-plan-invalid",
                "environment": campaign["environment"],
                "stages": [
                    {
                        "stage_id": "stage-five",
                        "traffic_percent": 5,
                        "minimum_observation_seconds": 60,
                        "required_sli": ["error-rate"],
                        "rollback_on_failure": True,
                    },
                    {
                        "stage_id": "stage-one",
                        "traffic_percent": 1,
                        "minimum_observation_seconds": 60,
                        "required_sli": ["error-rate"],
                        "rollback_on_failure": False,
                    },
                ],
                "canary_adapter_id": "canary-controller-one",
                "rollback_adapter_id": "rollback-controller-one",
                "approval_required": True,
            },
        )
        campaign["plans"]["canary"] = invalid
        result = evaluate_external_campaign(
            campaign,
            evidence_roots=[self.case_root],
            trust_store=self.trust,
            profile_registry=self.profiles,
            now=NOW,
        )
        self.assertEqual("REJECTED", result["decision"])
        self.assertTrue(any("roll back" in failure or "increase strictly" in failure for failure in result["failures"]))

    def test_rollback_plan_must_match_canary_adapter_and_environment(self) -> None:
        campaign, _ = self.base_campaign()
        _, invalid = self.write_json(
            "invalid-rollback-plan.json",
            {
                "schema_version": 1,
                "plan_id": "rollback-plan-invalid",
                "environment": "wrong-production-environment",
                "target_digest": "sha256:" + "8" * 64,
                "rollback_adapter_id": "different-rollback-controller",
                "maximum_rto_seconds": 300,
                "verification_checks": ["data-integrity"],
                "data_reconciliation_required": True,
                "approval_required": True,
            },
        )
        campaign["plans"]["rollback"] = invalid
        result = evaluate_external_campaign(
            campaign,
            evidence_roots=[self.case_root],
            trust_store=self.trust,
            profile_registry=self.profiles,
            now=NOW,
        )
        self.assertEqual("REJECTED", result["decision"])
        self.assertTrue(any("rollback plan environment" in failure for failure in result["failures"]))

    def test_full_557_skill_evidence_reaches_external_verified_only(self) -> None:
        campaign = self.complete_external_campaign()
        result = evaluate_external_campaign(
            campaign,
            evidence_roots=[self.case_root],
            trust_store=self.trust,
            profile_registry=self.profiles,
            now=NOW,
        )
        self.assertEqual("EXTERNAL_VERIFIED", result["decision"])
        self.assertEqual(557, result["verified_skill_count"])
        self.assertFalse(result["production_operation_authorized"])
        self.assertEqual("NOT_CERTIFIED", result["production_certification"])

    def test_complete_independent_production_chain_can_verify_external_certificate(self) -> None:
        campaign = self.complete_external_campaign()
        preliminary = evaluate_external_campaign(
            campaign,
            evidence_roots=[self.case_root],
            trust_store=self.trust,
            profile_registry=self.profiles,
            now=NOW,
        )
        release_digest = preliminary["release_digest"]
        canary_digest = campaign["plans"]["canary"]["digest"]
        rollback_digest = campaign["plans"]["rollback"]["digest"]
        hsm_payload_path = self.case_root / "hsm-release-payload.json"
        hsm_payload_path.write_bytes(canonical_bytes({"campaign_id": campaign["campaign_id"], "release_digest": release_digest}))
        hsm_signature_path = self.case_root / "hsm-release-signature.bin"
        subprocess.run(
            [
                "openssl", "pkeyutl", "-sign", "-inkey", str(self.keys["production-hsm-attestor"]),
                "-rawin", "-in", str(hsm_payload_path), "-out", str(hsm_signature_path),
            ],
            check=True,
            capture_output=True,
        )
        hsm_public_path = self.case_root / "hsm-release-public.pem"
        hsm_public_path.write_bytes((self.root / "production-hsm-attestor.public.pem").read_bytes())
        canary_metrics_path, _ = self.write_json("canary-metrics.json", {"error_rate": 0.0, "latency_ms": 10})
        rollback_recovery_path, _ = self.write_json("rollback-recovery.json", {"rto_seconds": 30, "integrity": "PASS"})
        campaign["production_artifacts"] = {
            "hsm_payload": self.content_ref(hsm_payload_path),
            "hsm_signature": self.content_ref(hsm_signature_path, "application/octet-stream"),
            "hsm_public_key": self.content_ref(hsm_public_path, "application/x-pem-file"),
            "canary_metrics": self.content_ref(canary_metrics_path),
            "rollback_recovery": self.content_ref(rollback_recovery_path),
        }
        authorization_payload = {
            "record_type": "PRECISION_PRODUCTION_CHANGE_AUTHORIZATION",
            "record_id": "production-auth-one",
            "actor_id": "production-approver-actor",
            "campaign_id": campaign["campaign_id"],
            "release_digest": release_digest,
            "environment": campaign["environment"],
            "canary_plan_digest": canary_digest,
            "rollback_plan_digest": rollback_digest,
            "decision": "APPROVED",
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2029-01-01T00:00:00Z",
        }
        hsm_payload = {
            "record_type": "PRECISION_HSM_SIGNATURE_RECEIPT",
            "record_id": "hsm-receipt-one",
            "actor_id": "hsm-operator-actor",
            "campaign_id": campaign["campaign_id"],
            "release_digest": release_digest,
            "state": "PASSED",
            "provider": "test-production-hsm",
            "algorithm": "ed25519",
            "key_reference_digest": canonical_digest({"key": "production-key"}),
            "signed_payload_digest": campaign["production_artifacts"]["hsm_payload"]["digest"],
            "signature_digest": campaign["production_artifacts"]["hsm_signature"]["digest"],
            "public_key_digest": campaign["production_artifacts"]["hsm_public_key"]["digest"],
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2029-01-01T00:00:00Z",
        }
        canary_payload = {
            "record_type": "PRECISION_CANARY_EXECUTION_RECEIPT",
            "record_id": "canary-receipt-one",
            "actor_id": "canary-controller-actor",
            "campaign_id": campaign["campaign_id"],
            "release_digest": release_digest,
            "plan_digest": canary_digest,
            "state": "PASSED",
            "maximum_percent_observed": 10,
            "rollback_ready": True,
            "metrics_evidence_digest": campaign["production_artifacts"]["canary_metrics"]["digest"],
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2029-01-01T00:00:00Z",
        }
        rollback_payload = {
            "record_type": "PRECISION_ROLLBACK_VALIDATION_RECEIPT",
            "record_id": "rollback-receipt-one",
            "actor_id": "rollback-controller-actor",
            "campaign_id": campaign["campaign_id"],
            "release_digest": release_digest,
            "plan_digest": rollback_digest,
            "state": "PASSED",
            "mode": "AUTHORIZED_EXERCISE",
            "recovery_evidence_digest": campaign["production_artifacts"]["rollback_recovery"]["digest"],
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2029-01-01T00:00:00Z",
        }
        campaign["production_authorization"] = self.sign("production-change-approver", authorization_payload)
        campaign["hsm_receipt"] = self.sign("production-hsm-attestor", hsm_payload)
        campaign["canary_receipt"] = self.sign("production-controller", canary_payload)
        campaign["rollback_receipt"] = self.sign("rollback-controller", rollback_payload)
        certificate_payload = {
            "record_type": "PRECISION_EXTERNAL_CERTIFICATE",
            "record_id": "external-certificate-one",
            "certificate_id": "certificate-external-one",
            "actor_id": "independent-certifier-actor",
            "campaign_id": campaign["campaign_id"],
            "release_digest": release_digest,
            "profile_count": 557,
            "authorization_digest": canonical_digest(authorization_payload),
            "hsm_receipt_digest": canonical_digest(hsm_payload),
            "canary_receipt_digest": canonical_digest(canary_payload),
            "rollback_receipt_digest": canonical_digest(rollback_payload),
            "decision": "CERTIFIED",
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2029-01-01T00:00:00Z",
        }
        campaign["external_certificate"] = self.sign("external-certifier", certificate_payload)
        result = evaluate_external_campaign(
            campaign,
            evidence_roots=[self.case_root],
            trust_store=self.trust,
            profile_registry=self.profiles,
            now=NOW,
        )
        self.assertEqual("CERTIFIED", result["decision"])
        self.assertTrue(result["production_operation_authorized"])
        self.assertEqual("CERTIFIED", result["production_certification"])

    def signed_adapter_registry(self) -> tuple[TrustedAdapterRegistry, Path]:
        executable = Path("/usr/bin/printf").resolve(strict=True)
        payload = {
            "record_type": "PRECISION_EXTERNAL_ADAPTER_REGISTRY",
            "record_id": "adapter-registry-one",
            "actor_id": "adapter-admin-actor",
            "registry_id": "external-registry-one",
            "profile_registry_digest": self.profiles.digest,
            "adapters": [
                {
                    "adapter_id": "native-source-one",
                    "stage": "native_source_execution",
                    "executable": str(executable),
                    "executable_digest": "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest(),
                    "argv": ["%s", "{param:value}"],
                    "parameters": [{"name": "value", "type": "identifier", "required": True}],
                    "environment_allowlist": [],
                    "timeout_seconds": 10,
                    "effect_class": "read-only",
                    "compensation_adapter": None,
                }
            ],
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2029-01-01T00:00:00Z",
        }
        envelope = self.sign("external-adapter-admin", payload)
        path, _ = self.write_json("external-adapters.json", envelope)
        return TrustedAdapterRegistry.load(path, self.trust, self.profiles), path

    def signed_preflight_adapter_registry(self) -> Path:
        executable = Path("/usr/bin/printf").resolve(strict=True)
        executable_digest = "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest()

        def adapter(
            adapter_id: str,
            stage: str,
            *,
            effect: str = "read-only",
            compensation: str | None = None,
            environment: list[str] | None = None,
        ) -> dict[str, object]:
            return {
                "adapter_id": adapter_id,
                "stage": stage,
                "executable": str(executable),
                "executable_digest": executable_digest,
                "argv": [adapter_id],
                "parameters": [],
                "environment_allowlist": environment or [],
                "timeout_seconds": 10,
                "effect_class": effect,
                "compensation_adapter": compensation,
            }

        payload = {
            "record_type": "PRECISION_EXTERNAL_ADAPTER_REGISTRY",
            "record_id": "preflight-adapter-registry-one",
            "actor_id": "adapter-admin-actor",
            "registry_id": "preflight-registry-one",
            "profile_registry_digest": self.profiles.digest,
            "adapters": [
                adapter("native-source-one", "native_source_execution"),
                adapter("native-target-one", "native_target_execution"),
                adapter("holdout-one", "independent_holdout"),
                adapter("customer-one", "representative_customer_workload"),
                adapter(
                    "production-hsm-one",
                    "production_hsm",
                    effect="approval-required",
                    environment=["ELMOS_PRECISION_HSM_PIN"],
                ),
                adapter(
                    "canary-controller-one",
                    "authorized_canary",
                    effect="reversible",
                    compensation="rollback-controller-one",
                ),
                adapter(
                    "rollback-controller-one",
                    "verified_rollback",
                    effect="approval-required",
                ),
            ],
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2029-01-01T00:00:00Z",
        }
        path, _ = self.write_json(
            "preflight-external-adapters.json",
            self.sign("external-adapter-admin", payload),
        )
        return path

    def preflight_config(self) -> dict[str, str]:
        campaign, _ = self.base_campaign()
        registry_path = self.signed_preflight_adapter_registry()
        authorization = self.sign(
            "production-change-approver",
            {
                "record_type": "PRECISION_PRODUCTION_CHANGE_AUTHORIZATION",
                "record_id": "preflight-production-auth-one",
                "actor_id": "production-change-approver-actor",
                "campaign_id": campaign["campaign_id"],
                "release_digest": "sha256:" + "9" * 64,
                "environment": campaign["environment"],
                "decision": "APPROVED",
                "issued_at": "2026-01-01T00:00:00Z",
                "expires_at": "2029-01-01T00:00:00Z",
            },
        )
        authorization_path, _ = self.write_json("preflight-production-auth.json", authorization)

        def referenced_path(reference: dict[str, object]) -> str:
            return verify_content_reference(reference, (self.case_root.resolve(),))["resolved_path"]

        return {
            "environment": str(campaign["environment"]),
            "independent_verifier_trust_store": str(self.trust_path),
            "external_adapter_registry": str(registry_path),
            "evidence_roots": str(self.case_root),
            "hsm_provider": "pkcs11",
            "hsm_key_reference": "pkcs11:token=elmos-production;object=release-signing;type=private",
            "customer_workload_manifest": referenced_path(campaign["corpora"]["representative"]),
            "canary_plan": referenced_path(campaign["plans"]["canary"]),
            "rollback_plan": referenced_path(campaign["plans"]["rollback"]),
            "production_authorization": str(authorization_path),
        }

    def test_external_preflight_validates_code_owned_boundary_without_promoting_evidence(self) -> None:
        result = evaluate_preflight(
            self.preflight_config(),
            secret_names={"ELMOS_PRECISION_HSM_PIN"},
            now=NOW,
        )
        self.assertEqual("READY_FOR_AUTHORIZED_EXTERNAL_EXECUTION", result["status"])
        self.assertEqual(557, result["checks"]["representative_customer_workload"]["case_count"])
        self.assertEqual(7, len(result["checks"]["external_adapter_registry"]["stage_counts"]))
        self.assertFalse(result["external_operations_executed"])
        self.assertEqual("NOT_RUN", result["independent_holdout"])
        self.assertEqual("NOT_RUN", result["hsm_signing"])
        self.assertEqual("NOT_RUN", result["customer_workload"])
        self.assertEqual("NOT_RUN", result["canary"])
        self.assertEqual("NOT_RUN", result["rollback"])
        self.assertEqual("NOT_CERTIFIED", result["production_certification"])

    def test_external_preflight_fails_closed_without_hsm_secret_reference(self) -> None:
        result = evaluate_preflight(self.preflight_config(), secret_names=set(), now=NOW)
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("BLOCKED", result["checks"]["production_hsm"]["state"])
        self.assertTrue(any("HSM_PIN" in item for item in result["failures"]))
        self.assertFalse(result["external_operations_executed"])
        self.assertEqual("NOT_CERTIFIED", result["production_certification"])

    def test_external_preflight_invalid_plan_is_serializable_and_fail_closed(self) -> None:
        config = self.preflight_config()
        invalid_path, _ = self.write_json("preflight-invalid-canary.json", {"stages": [100]})
        config["canary_plan"] = str(invalid_path)
        result = evaluate_preflight(
            config,
            secret_names={"ELMOS_PRECISION_HSM_PIN"},
            now=NOW,
        )
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("BLOCKED", result["checks"]["canary_plan"]["state"])
        self.assertEqual("BLOCKED", result["checks"]["rollback_plan"]["state"])
        self.assertEqual("BLOCKED", result["checks"]["external_adapter_registry"]["state"])
        json.dumps(result, sort_keys=True)
        self.assertEqual("NOT_CERTIFIED", result["production_certification"])

    def operation_request(self, registry: TrustedAdapterRegistry, value: str) -> dict[str, object]:
        parameters = {"value": value}
        cases, corpus_reference = self.corpus("development")
        skill = sorted(self.profiles.by_skill)[0]
        profile_digest = self.profiles.by_skill[skill]["profile_digest"]
        qualification_binding = {
            "skill": skill,
            "profile_digest": profile_digest,
            "partition": "development",
            "case_digest": cases[skill],
            "corpus_digest": corpus_reference["digest"],
            "corpus_ref_index": 0,
        }
        identity = {
            "operation_id": "operation-one",
            "campaign_id": "campaign-one",
            "adapter_id": "native-source-one",
            "adapter_registry_digest": registry.digest,
            "stage": "native_source_execution",
            "parameters_digest": canonical_digest(parameters),
            "input_digests": [corpus_reference["digest"]],
            "qualification_binding": qualification_binding,
            "idempotency_key": "idempotency-one",
            "fencing_token": 1,
            "compensates_idempotency_key": None,
            "target_digest": canonical_digest({"adapter_id": "native-source-one", "parameters": parameters}),
        }
        request_digest = canonical_digest(identity)
        return {
            "schema_version": 1,
            "operation_id": "operation-one",
            "campaign_id": "campaign-one",
            "adapter_id": "native-source-one",
            "stage": "native_source_execution",
            "parameters": parameters,
            "input_refs": [corpus_reference],
            "qualification_binding": {
                "skill": skill,
                "profile_digest": profile_digest,
                "partition": "development",
                "case_digest": cases[skill],
                "corpus_ref_index": 0,
            },
            "idempotency_key": "idempotency-one",
            "fencing_token": 1,
            "compensates_idempotency_key": None,
            "authorization": self.sign(
                "external-execution-authorizer",
                {
                    "record_type": "PRECISION_EXTERNAL_OPERATION_AUTHORIZATION",
                    "record_id": "operation-auth-one",
                    "actor_id": "execution-authorizer-actor",
                    "operation_id": "operation-one",
                    "campaign_id": "campaign-one",
                    "request_digest": request_digest,
                    "decision": "APPROVED",
                    "issued_at": "2026-01-01T00:00:00Z",
                    "expires_at": "2029-01-01T00:00:00Z",
                },
            ),
        }

    def test_signed_digest_pinned_external_adapter_executes_and_is_idempotent(self) -> None:
        registry, _ = self.signed_adapter_registry()
        request = self.operation_request(registry, "safe-value")
        output = self.case_root / "operation-output"
        ledger = OperationLedger(self.case_root / "operation-ledger.sqlite3")
        first = execute_operation(
            request,
            registry=registry,
            trust_store=self.trust,
            evidence_roots=[self.case_root],
            ledger=ledger,
            output_dir=output,
        )
        second = execute_operation(
            request,
            registry=registry,
            trust_store=self.trust,
            evidence_roots=[self.case_root],
            ledger=ledger,
            output_dir=output,
        )
        self.assertEqual("SUCCEEDED", first["state"])
        self.assertEqual("safe-value", first["stdout"])
        self.assertFalse(first["stdout_truncated"])
        self.assertFalse(first["stderr_truncated"])
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(first["receipt_digest"], second["receipt_digest"])
        self.assertEqual(0o600, (self.case_root / "operation-ledger.sqlite3").stat().st_mode & 0o777)
        self.assertEqual(0o600, (output / "operation-one.json").stat().st_mode & 0o777)

    def test_operation_ledger_and_receipt_directory_reject_symlinks(self) -> None:
        real_ledger = self.case_root / "real-ledger.sqlite3"
        OperationLedger(real_ledger)
        linked_ledger = self.case_root / "linked-ledger.sqlite3"
        linked_ledger.symlink_to(real_ledger)
        with self.assertRaisesRegex(ProductionRuntimeError, "must not be a symlink"):
            OperationLedger(linked_ledger)

        registry, _ = self.signed_adapter_registry()
        request = self.operation_request(registry, "safe-value")
        real_output = self.case_root / "real-operation-output"
        real_output.mkdir()
        linked_output = self.case_root / "linked-operation-output"
        linked_output.symlink_to(real_output, target_is_directory=True)
        with self.assertRaisesRegex(ProductionRuntimeError, "output directory must not be a symlink"):
            execute_operation(
                request,
                registry=registry,
                trust_store=self.trust,
                evidence_roots=[self.case_root],
                ledger=OperationLedger(self.case_root / "symlink-output-ledger.sqlite3"),
                output_dir=linked_output,
            )

    def test_external_adapter_rejects_parameter_command_injection(self) -> None:
        registry, _ = self.signed_adapter_registry()
        request = self.operation_request(registry, "unsafe;touch")
        with self.assertRaisesRegex(ProductionRuntimeError, "safe identifier"):
            execute_operation(
                request,
                registry=registry,
                trust_store=self.trust,
                evidence_roots=[self.case_root],
                ledger=OperationLedger(self.case_root / "injection-ledger.sqlite3"),
                output_dir=self.case_root / "injection-output",
            )

    def test_qualification_operation_rejects_wrong_skill_case_binding(self) -> None:
        registry, _ = self.signed_adapter_registry()
        request = self.operation_request(registry, "safe-value")
        request["qualification_binding"]["case_digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ProductionRuntimeError, "case binding"):
            execute_operation(
                request,
                registry=registry,
                trust_store=self.trust,
                evidence_roots=[self.case_root],
                ledger=OperationLedger(self.case_root / "wrong-case-ledger.sqlite3"),
                output_dir=self.case_root / "wrong-case-output",
            )

    def signed_cutover_registry(self) -> TrustedAdapterRegistry:
        executable = Path("/usr/bin/printf").resolve(strict=True)
        executable_digest = "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest()
        payload = {
            "record_type": "PRECISION_EXTERNAL_ADAPTER_REGISTRY",
            "record_id": "cutover-registry-one",
            "actor_id": "adapter-admin-actor",
            "registry_id": "cutover-registry-one",
            "profile_registry_digest": self.profiles.digest,
            "adapters": [
                {
                    "adapter_id": "canary-controller-one",
                    "stage": "authorized_canary",
                    "executable": str(executable),
                    "executable_digest": executable_digest,
                    "argv": ["canary"],
                    "parameters": [],
                    "environment_allowlist": [],
                    "timeout_seconds": 10,
                    "effect_class": "reversible",
                    "compensation_adapter": "rollback-controller-one",
                },
                {
                    "adapter_id": "rollback-controller-one",
                    "stage": "verified_rollback",
                    "executable": str(executable),
                    "executable_digest": executable_digest,
                    "argv": ["rollback"],
                    "parameters": [],
                    "environment_allowlist": [],
                    "timeout_seconds": 10,
                    "effect_class": "approval-required",
                    "compensation_adapter": None,
                },
            ],
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2029-01-01T00:00:00Z",
        }
        envelope = self.sign("external-adapter-admin", payload)
        path, _ = self.write_json("cutover-adapters.json", envelope)
        return TrustedAdapterRegistry.load(path, self.trust, self.profiles)

    def signed_mutation_request(
        self,
        registry: TrustedAdapterRegistry,
        *,
        operation_id: str,
        adapter_id: str,
        stage: str,
        idempotency_key: str,
        fencing_token: int,
        compensates: str | None,
    ) -> dict[str, object]:
        identity = {
            "operation_id": operation_id,
            "campaign_id": "campaign-cutover",
            "adapter_id": adapter_id,
            "adapter_registry_digest": registry.digest,
            "stage": stage,
            "parameters_digest": canonical_digest({}),
            "input_digests": [],
            "qualification_binding": None,
            "idempotency_key": idempotency_key,
            "fencing_token": fencing_token,
            "compensates_idempotency_key": compensates,
            "target_digest": canonical_digest({"adapter_id": adapter_id, "parameters": {}}),
        }
        return {
            "schema_version": 1,
            "operation_id": operation_id,
            "campaign_id": "campaign-cutover",
            "adapter_id": adapter_id,
            "stage": stage,
            "parameters": {},
            "input_refs": [],
            "qualification_binding": None,
            "idempotency_key": idempotency_key,
            "fencing_token": fencing_token,
            "compensates_idempotency_key": compensates,
            "authorization": self.sign(
                "production-change-approver",
                {
                    "record_type": "PRECISION_EXTERNAL_OPERATION_AUTHORIZATION",
                    "record_id": f"authorization-{operation_id}",
                    "actor_id": "production-change-approver-actor",
                    "operation_id": operation_id,
                    "campaign_id": "campaign-cutover",
                    "request_digest": canonical_digest(identity),
                    "decision": "APPROVED",
                    "issued_at": "2026-01-01T00:00:00Z",
                    "expires_at": "2029-01-01T00:00:00Z",
                },
            ),
        }

    def test_authorized_canary_executes_only_with_registered_rollback(self) -> None:
        registry = self.signed_cutover_registry()
        ledger = OperationLedger(self.case_root / "cutover-ledger.sqlite3")
        output = self.case_root / "cutover-output"
        canary = self.signed_mutation_request(
            registry,
            operation_id="canary-operation",
            adapter_id="canary-controller-one",
            stage="authorized_canary",
            idempotency_key="canary-idempotency",
            fencing_token=1,
            compensates=None,
        )
        rollback = self.signed_mutation_request(
            registry,
            operation_id="rollback-operation",
            adapter_id="rollback-controller-one",
            stage="verified_rollback",
            idempotency_key="rollback-idempotency",
            fencing_token=2,
            compensates="canary-idempotency",
        )
        canary_result = execute_operation(
            canary,
            registry=registry,
            trust_store=self.trust,
            evidence_roots=[self.case_root],
            ledger=ledger,
            output_dir=output,
        )
        rollback_result = execute_operation(
            rollback,
            registry=registry,
            trust_store=self.trust,
            evidence_roots=[self.case_root],
            ledger=ledger,
            output_dir=output,
        )
        self.assertEqual("SUCCEEDED", canary_result["state"])
        self.assertEqual("SUCCEEDED", rollback_result["state"])
        self.assertEqual("COMPENSATED", ledger.original("canary-idempotency")["state"])


if __name__ == "__main__":
    unittest.main()

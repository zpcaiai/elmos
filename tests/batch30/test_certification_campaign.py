import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import tests.batch30.test_external_certification_intake as _intake_tests
from scripts.batch30.certification_campaign import (
    PRE_CERTIFICATION_EVIDENCE,
    REQUIRED_EVIDENCE,
    TECHNICAL_EVIDENCE,
    CampaignError,
    evaluate_certification_campaign,
    support_matrix_subject_digest,
)
from scripts.batch30.promote_framework_certification import (
    PromotionError,
    build_promotion_documents,
    promote,
)
from scripts.batch30.validate_external_certification_intake import (
    CUSTOMER_AUTHORIZATION_ROLE,
    EVIDENCE_ROLES,
)
from scripts.precision_migration.trust import canonical_digest


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "batch30"


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


class CertificationCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_class = _intake_tests.ExternalCertificationIntakeTests
        cls.fixture_class.setUpClass()
        cls.pack = cls.fixture_class.pack
        cls.source_commit = "1" * 40
        cls.source_snapshot_digest = "sha256:" + "2" * 64
        cls.version_tuple = {
            "source": {
                "framework": "spring-boot",
                "framework_version": "2.7.18",
                "java": "17.0.12",
                "maven": "3.9.11",
                "servlet_namespace": "javax.servlet",
                "servlet_api": "4.0",
                "container": "9.0.90",
            },
            "target": {
                "framework": "spring-boot",
                "framework_version": "3.5.3",
                "spring_framework_version": "6.2.8",
                "java": "21.0.11",
                "maven": "3.9.11",
                "servlet_namespace": "jakarta.servlet",
                "servlet_api": "6.1",
                "container": "10.1.42",
            },
        }
        cls.toolchain_digests = {
            "source-java": _sha256_bytes(b"source-java-release-manifest"),
            "source-maven": _sha256_bytes(b"maven-distribution"),
            "source-container": _sha256_bytes(b"source-container-distribution"),
            "target-java": _sha256_bytes(b"target-java-release-manifest"),
            "target-maven": _sha256_bytes(b"maven-distribution"),
            "target-container": _sha256_bytes(b"target-container-core"),
        }
        cls._prepare_campaign_pack()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture_class.tearDownClass()

    @classmethod
    def _write_json(cls, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def _prepare_campaign_pack(cls) -> None:
        manifest_path = cls.pack / "pack.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update(
            {
                "owner": "framework-team",
                "maintenance_owner": "framework-team",
                "review_date": "2026-12-01",
                "paths": {"certification": "certification"},
                "gates": {
                    "real_source_runtime": True,
                    "real_target_runtime": True,
                    "startup_required": True,
                    "holdout_required": True,
                    "representative_repository_required": True,
                    "critical_unknowns_allowed": 0,
                    "critical_security_regressions_allowed": 0,
                    "critical_transaction_regressions_allowed": 0,
                    "critical_data_regressions_allowed": 0,
                },
            }
        )
        cls._write_json(manifest_path, manifest)
        target_profile_path = cls.pack / "target-profile" / "profile.json"
        target_profile_value = json.loads(target_profile_path.read_text(encoding="utf-8"))
        target_profile_value.update(
            {
                "version": "1.0.0",
                "owner": "framework-team",
                "architecture_style": "executable-servlet-application",
                "providers": {"servlet": {"version": "6.1"}},
                "build": {"commands": ["mvn verify"], "toolchain_digests": ["sha256:test"]},
                "startup": {"command": "java -jar target.jar", "health_check": "/readyz"},
            }
        )
        cls._write_json(target_profile_path, target_profile_value)
        (cls.pack / "adapters").mkdir(exist_ok=True)
        cls._write_json(
            cls.pack / "source-fingerprint" / "manifest.json",
            {"schema_version": 1, "pack_key": "spring-boot-2-7-18-to-3-5-3"},
        )
        cls._write_json(
            cls.pack / "compatibility" / "manifest.json",
            {"schema_version": 1, "pack_key": "spring-boot-2-7-18-to-3-5-3"},
        )
        cls._write_json(
            cls.pack / "coexistence" / "manifest.json",
            {
                "schema_version": 1,
                "pack_key": "spring-boot-2-7-18-to-3-5-3",
                "enabled": False,
                "status": "NOT_RUN",
                "reason": "Coexistence is disabled until an application-specific compatibility contract is approved.",
                "components": [],
                "exit_criteria": [
                    "Retire the source runtime only after target parity, rollback, and customer acceptance pass."
                ],
            },
        )
        artifact = cls.pack / "certification" / "artifacts" / "target.jar"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"real-target-artifact-fixture\n")
        rules = cls.pack / "recipes" / "exact-rules.yml"
        rules.write_text("type: specs.openrewrite.org/v1beta/recipe\nname: exact\n", encoding="utf-8")
        recipe_manifest_path = cls.pack / "recipes" / "manifest.json"
        recipe_manifest = json.loads(recipe_manifest_path.read_text(encoding="utf-8"))
        recipe_manifest["recipe_config"] = "recipes/exact-rules.yml"
        cls._write_json(recipe_manifest_path, recipe_manifest)

        cls._write_json(
            cls.pack / "source-fingerprint" / "evidence.json",
            {
                "source_commit": cls.source_commit,
                "source_snapshot_sha256": cls.source_snapshot_digest.removeprefix("sha256:"),
            },
        )
        cls._write_json(
            cls.pack / "contracts" / "framework-contract-model.json",
            {
                "source_commit": cls.source_commit,
                "source_snapshot_sha256": cls.source_snapshot_digest.removeprefix("sha256:"),
            },
        )
        cls._write_json(
            cls.pack / "support-matrix.json",
            {
                "schema_version": 1,
                "pack_key": "spring-boot-2-7-18-to-3-5-3",
                "capabilities": [
                    {"id": "web", "status": "supported"},
                    {
                        "id": "transactions",
                        "status": "blocked",
                        "reason": "excluded from the exact certified scope",
                    },
                ],
            },
        )
        cls._write_json(
            cls.pack / "certification" / "evidence.json",
            {
                "schema_version": 1,
                "pack_key": "spring-boot-2-7-18-to-3-5-3",
                "evidence_class": "LOCAL_ENGINEERING",
                "runs": [],
                "metrics": {},
                "external_execution_status": "NOT_RUN",
            },
        )
        cls._write_json(
            cls.pack / "certification" / "certification.json",
            {
                "schema_version": 1,
                "pack_key": "spring-boot-2-7-18-to-3-5-3",
                "status": "limited",
                "certification_decision": "NOT_CERTIFIED",
                "gate_results": {},
                "metrics": {},
                "evidence_refs": [],
            },
        )
        for role in ("development", "holdout", "real-repository", "customer"):
            path = cls.pack / "corpus" / role
            path.mkdir(parents=True, exist_ok=True)
            (path / "README.md").write_text(role + "\n", encoding="utf-8")

        policy_path = cls.pack / "certification" / "qualification-policy.json"
        cls.recipe_binding = {
            "coordinate": "io.elmos:elmos-java-recipes:0.1.0-SNAPSHOT",
            "build_output_timestamp": "2026-08-28T00:00:00Z",
            "jar_sha256": "sha256:" + "a" * 64,
            "recipe_pom_sha256": "sha256:" + "b" * 64,
            "parent_pom_sha256": "sha256:" + "c" * 64,
            "files": [
                {
                    "path": "io/elmos/elmos-parent/0.1.0-SNAPSHOT/"
                    "elmos-parent-0.1.0-SNAPSHOT.pom",
                    "bytes": 101,
                    "sha256": "c" * 64,
                },
                {
                    "path": "io/elmos/elmos-java-recipes/0.1.0-SNAPSHOT/"
                    "elmos-java-recipes-0.1.0-SNAPSHOT.pom",
                    "bytes": 102,
                    "sha256": "b" * 64,
                },
                {
                    "path": "io/elmos/elmos-java-recipes/0.1.0-SNAPSHOT/"
                    "elmos-java-recipes-0.1.0-SNAPSHOT.jar",
                    "bytes": 103,
                    "sha256": "a" * 64,
                },
            ],
        }
        cls._write_json(
            policy_path,
            {
                "schema_version": 1,
                "source_commit": cls.source_commit,
                "target_artifact": {"sha256": _sha256_file(artifact)},
                "evidence_policy": {
                    "required_evidence_types": list(REQUIRED_EVIDENCE),
                    "external_evidence_status": "NOT_RUN",
                    "certification_status": "NOT_CERTIFIED",
                    "signature_algorithm": "Ed25519",
                },
                "toolchain_bindings": cls.toolchain_digests,
                "rewrite_recipe_artifact": cls.recipe_binding,
            },
        )
        exact_path = cls.pack / "certification" / "exact-tuple-binding.json"
        target_profile = cls.pack / "target-profile" / "profile.json"
        exact = {
            "schema_version": 1,
            "pack_key": "spring-boot-2-7-18-to-3-5-3",
            "source": {
                "commit": cls.source_commit,
                "snapshot_sha256": cls.source_snapshot_digest,
                **cls.version_tuple["source"],
                "packaging": "jar",
            },
            "target": {
                "artifact_sha256": _sha256_file(artifact),
                "artifact_bytes": artifact.stat().st_size,
                **cls.version_tuple["target"],
                "embedded_tomcat": cls.version_tuple["target"]["container"],
                "packaging": "executable-jar",
            },
            "toolchain": {"source_tomcat_version": cls.version_tuple["source"]["container"]},
            "transformation": {
                "target_profile_sha256": _sha256_file(target_profile),
                "custom_recipe_coordinate": cls.recipe_binding["coordinate"],
                "custom_recipe_build_output_timestamp":
                    cls.recipe_binding["build_output_timestamp"],
                "custom_recipe_artifact_sha256": cls.recipe_binding["jar_sha256"],
                "custom_recipe_pom_sha256": cls.recipe_binding["recipe_pom_sha256"],
                "custom_recipe_parent_pom_sha256":
                    cls.recipe_binding["parent_pom_sha256"],
            },
            "policy": {"sha256": _sha256_file(policy_path)},
            "status_boundary": {
                "external_evidence": "NOT_RUN",
                "production_certification": "NOT_CERTIFIED",
                "local_runner_may_certify": False,
            },
        }
        cls._write_json(exact_path, exact)
        phases = []
        phase_evidence = {
            "P0": [], "P1": [],
            "P2": ["source_build", "target_build", "source_startup", "target_startup"],
            "P3": ["behavioral_equivalence"], "P4": ["security"],
            "P5": ["performance"], "P6": ["operability", "sbom"],
            "P7": ["rollback"], "P8": ["customer_acceptance"],
            "P9": list(PRE_CERTIFICATION_EVIDENCE),
            "P10": ["external_certification"], "P11": [],
        }
        for index in range(12):
            phase = f"P{index}"
            phases.append(
                {
                    "id": phase,
                    "title": f"campaign phase {phase}",
                    "owner_role": f"owner-{phase.lower()}",
                    "required_evidence_types": phase_evidence[phase],
                    "pass_criteria": [f"{phase} exact criteria"],
                    "execution_status": "NOT_RUN" if index not in {0, 11} else (
                        "PASSED_LOCAL" if index == 0 else "PASSED_EXPERIMENTAL_NOT_CERTIFIED"
                    ),
                }
            )
        cls.campaign_path = cls.pack / "certification" / "p0-p11-campaign.json"
        campaign = {
            "schema_version": "elmos.batch30.certification-campaign.v1",
            "campaign_id": "test-p0-p11-campaign",
            "pack_key": "spring-boot-2-7-18-to-3-5-3",
            "tuple_binding": {
                "source_commit": cls.source_commit,
                "source_snapshot_digest": cls.source_snapshot_digest,
                "exact_tuple": {
                    "path": "certification/exact-tuple-binding.json",
                    "digest": _sha256_file(exact_path),
                },
                "target_artifact": {
                    "path": "certification/artifacts/target.jar",
                    "digest": _sha256_file(artifact),
                    "size_bytes": artifact.stat().st_size,
                },
                "target_profile": {
                    "path": "target-profile/profile.json",
                    "digest": _sha256_file(target_profile),
                },
                "policy": {
                    "path": "certification/qualification-policy.json",
                    "digest": _sha256_file(policy_path),
                },
                "version_tuple": cls.version_tuple,
            },
            "scope": {
                "exact_tuple_only": True,
                "certified_capability_ids": ["web"],
                "excluded_capability_ids": ["transactions"],
                "support_matrix_subject_digest": support_matrix_subject_digest(
                    json.loads((cls.pack / "support-matrix.json").read_text()),
                    ["web"],
                ),
            },
            "corpora": {
                "development": {"path": "corpus/development", "independent": False, "execution_status": "PASSED_LOCAL", "authoring_allowed": True},
                "holdout": {"path": "corpus/holdout", "independent": True, "execution_status": "NOT_RUN", "authoring_allowed": False},
                "representative": {"path": "corpus/real-repository", "independent": True, "execution_status": "NOT_RUN", "authoring_allowed": False},
                "customer": {"path": "corpus/customer", "independent": True, "execution_status": "NOT_RUN", "authoring_allowed": False},
            },
            "rule_freeze": {
                "rules": {"path": "recipes/exact-rules.yml", "digest": _sha256_file(rules)},
                "recipe_manifest_digest": _sha256_file(recipe_manifest_path),
                "frozen_at": "2026-01-01T00:00:00Z",
                "holdout_authoring_forbidden": True,
            },
            "phases": phases,
            "required_external_evidence_types": list(REQUIRED_EVIDENCE),
            "thresholds": {
                "source_fingerprint_coverage": 1.0,
                "framework_contract_coverage": 1.0,
                "build_green_rate": 1.0,
                "startup_pass_rate": 1.0,
                "p0_contract_pass_rate": 1.0,
                "source_map_coverage": 1.0,
                "route_coverage": 1.0,
                "critical_unknowns": 0,
                "silent_framework_drops": 0,
                "critical_security_regressions": 0,
                "critical_transaction_regressions": 0,
                "critical_data_regressions": 0,
                "duplicate_message_or_job_effects": 0,
                "test_integrity_violations": 0,
                "skipped_tests": 0,
                "flaky_tests": 0,
                "waivers": 0,
                "minimum_source_builds": 2,
                "minimum_target_builds": 2,
                "minimum_startup_attempts": 2,
                "minimum_security_scanners": 3,
                "minimum_performance_requests": 10000,
                "minimum_performance_soak_seconds": 3600,
                "performance_slo_p95_ms": 100.0,
                "performance_slo_throughput_rps": 400.0,
                "minimum_rollback_attempts": 3,
                "rollback_rto_objective_seconds": 60.0,
            },
            "status_boundary": {
                "external_evidence": "NOT_RUN",
                "production_certification": "NOT_CERTIFIED",
                "local_runner_may_certify": False,
                "promotion_requires_reverification": True,
            },
        }
        cls._write_json(cls.campaign_path, campaign)
        cls.campaign = campaign

    def setUp(self) -> None:
        self.fixture = self.fixture_class(methodName="test_valid_intake_is_review_ready_but_never_certifies_or_mutates_pack")
        self.fixture.setUp()

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def _toolchains(self) -> list[dict[str, str]]:
        tools = []
        for name, side, field in (
            ("source-java", "source", "java"),
            ("source-maven", "source", "maven"),
            ("source-container", "source", "container"),
            ("target-java", "target", "java"),
            ("target-maven", "target", "maven"),
            ("target-container", "target", "container"),
        ):
            tools.append(
                {
                    "name": name,
                    "version": self.version_tuple[side][field],
                    "digest": self.toolchain_digests[name],
                }
            )
        return tools

    def _environment(self) -> dict[str, object]:
        return {
            "environment_id": "authorized-isolated-environment",
            "isolation": "AUTHORIZED_ISOLATED",
            "source_commit": self.source_commit,
            "source_snapshot_digest": self.source_snapshot_digest,
            "target_artifact_digest": self.fixture.binding["artifact_digest"],
            "target_profile_digest": self.campaign["tuple_binding"]["target_profile"]["digest"],
            "policy_digest": self.campaign["tuple_binding"]["policy"]["digest"],
            "version_tuple": copy.deepcopy(self.version_tuple),
            "toolchains": self._toolchains(),
        }

    def _base_metrics(self, evidence_type: str) -> dict[str, object]:
        artifact = self.fixture.binding["artifact_digest"]
        if evidence_type == "source_build":
            return {"builds_total": 2, "builds_passed": 2, "tests_total": 10, "failures": 0, "errors": 0, "skipped": 0, "native": True, "exact_toolchain": True}
        if evidence_type == "target_build":
            return {"builds_total": 2, "builds_passed": 2, "tests_total": 12, "failures": 0, "errors": 0, "skipped": 0, "native": True, "exact_toolchain": True, "artifact_digest": artifact, "rootless": True, "privileged": False}
        if evidence_type in {"source_startup", "target_startup"}:
            metrics = {"startup_attempts": 2, "startup_passed": 2, "readiness_probes": 4, "readiness_passed": 4, "shutdown_attempts": 2, "shutdown_passed": 2, "startup_seconds": 1.5, "shutdown_seconds": 0.5, "native": True}
            if evidence_type == "target_startup":
                metrics.update({"rootless": True, "privileged": False, "effective_uid": 10001})
            return metrics
        if evidence_type == "behavioral_equivalence":
            return {
                "routes_total": 4, "routes_passed": 4, "p0_contracts_total": 8,
                "p0_contracts_passed": 8, "holdout_projects": 1,
                "representative_projects": 1, "customer_projects": 1,
                "route_coverage": 1.0, "source_fingerprint_coverage": 1.0,
                "framework_contract_coverage": 1.0, "source_map_coverage": 1.0,
                "critical_mismatch_count": 0, "silent_framework_drops": 0,
                "critical_transaction_regressions": 0, "critical_data_regressions": 0,
                "duplicate_message_or_job_effects": 0, "test_integrity_violations": 0,
                "rules_frozen_before_holdout": True,
                "rules_digest": self.campaign["rule_freeze"]["rules"]["digest"],
                "corpus_digests": {
                    role: _sha256_bytes(("corpus:" + role).encode())
                    for role in ("development", "holdout", "representative", "customer")
                },
                "project_outcome_evidence_digests": {
                    role: _sha256_bytes(("project-outcome:" + role).encode())
                    for role in ("holdout", "representative", "customer")
                },
            }
        if evidence_type == "security":
            return {"scanners": ["sast-1.0", "sca-1.0", "dast-1.0"], "critical_findings": 0, "high_findings": 0, "authentication_regressions": 0, "authorization_regressions": 0, "critical_dependency_vulnerabilities": 0, "critical_data_exposure_findings": 0}
        if evidence_type == "performance":
            return {"capacity_validated": True, "request_count": 10000, "error_count": 0, "p95_ms": 80.0, "slo_p95_ms": 100.0, "throughput_rps": 500.0, "slo_throughput_rps": 400.0, "soak_seconds": 3600}
        if evidence_type == "operability":
            return {"endpoints_verified": ["/livez", "/readyz", "/metrics", "/version"], "failed_probes": 0, "alert_failures": 0, "runbook_failures": 0, "trace_correlation_verified": True}
        if evidence_type == "sbom":
            return {"artifact_digest": artifact, "format": "CycloneDX-1.5", "component_count": 42, "unknown_licenses": 0, "critical_vulnerabilities": 0, "artifact_bound": True}
        if evidence_type == "rollback":
            return {"rehearsed": True, "attempts": 3, "passed": 3, "actual_rto_seconds": 40.0, "rto_objective_seconds": 60.0, "data_loss_records": 0, "orphan_effects": 0}
        if evidence_type == "customer_acceptance":
            return {"scenarios_total": 12, "scenarios_passed": 12, "accepted_artifact_digest": artifact, "accepted_execution_profile_digest": self.fixture.binding["execution_profile_digest"], "customer_owned_holdout": True, "unresolved_findings": 0}
        raise AssertionError(evidence_type)

    def _install_full_documents(
        self,
        *,
        route_coverage: float = 1.0,
        waivers: bool = False,
        startup_native: bool = True,
        toolchain_drift: bool = False,
        target_startup_before_build: bool = False,
    ) -> None:
        documents: dict[str, dict[str, object]] = {}
        timestamps = {
            name: f"2026-06-{index + 1:02d}T00:00:00Z"
            for index, name in enumerate(TECHNICAL_EVIDENCE)
        }
        timestamps.update({"independent_review": "2026-06-20T00:00:00Z", "customer_acceptance": "2026-06-21T00:00:00Z", "external_certification": "2026-06-30T00:00:00Z"})
        if target_startup_before_build:
            timestamps["target_startup"] = "2026-06-01T12:00:00Z"

        def write_document(evidence_type: str, metrics: dict[str, object]) -> None:
            raw_path = self.evidence_root / f"raw-{evidence_type}.log"
            raw_path.write_text(f"real raw evidence for {evidence_type}\n", encoding="utf-8")
            raw_references = [self.fixture.content_ref(raw_path, "text/plain")]
            if evidence_type == "behavioral_equivalence":
                for role in ("development", "holdout", "representative", "customer"):
                    corpus_path = self.evidence_root / f"corpus-{role}.tar.zst"
                    corpus_path.write_bytes(("corpus:" + role).encode())
                    reference = self.fixture.content_ref(
                        corpus_path,
                        "application/zstd",
                    )
                    metrics["corpus_digests"][role] = reference["digest"]
                    raw_references.append(reference)
                for role in ("holdout", "representative", "customer"):
                    project_path = self.evidence_root / f"project-outcome-{role}.json"
                    project_path.write_bytes(("project-outcome:" + role).encode())
                    reference = self.fixture.content_ref(project_path)
                    metrics["project_outcome_evidence_digests"][role] = reference["digest"]
                    raw_references.append(reference)
            environment = self._environment()
            if toolchain_drift and evidence_type == "security":
                environment["toolchains"][0]["digest"] = "sha256:" + "e" * 64
            document = {
                "schema_version": "elmos.batch30.external-evidence.v1",
                "evidence_type": evidence_type,
                "campaign_digest": _sha256_file(self.campaign_path),
                "binding_digest": self.fixture.binding_digest,
                "execution_id": f"execution-{evidence_type}",
                "executed_at": timestamps[evidence_type],
                "executor_actor_id": self.fixture.evidence_executors[evidence_type]["actor_id"],
                "executor_organization_id": self.fixture.evidence_executors[evidence_type]["organization_id"],
                "result": self.fixture.outcome_for(evidence_type),
                "environment": environment,
                "metrics": metrics,
                "raw_evidence": raw_references,
                "unknowns": [],
                "not_run": [],
                "waivers": ["forbidden-waiver"] if waivers and evidence_type == "security" else [],
                "test_integrity": {"skipped": 0, "flaky": 0, "weakened": 0, "synthetic": False},
            }
            documents[evidence_type] = document
            path = self.evidence_root / f"{evidence_type}.json"
            self.fixture.write_json(path, document)
            self.fixture.intake["evidence"][evidence_type]["content"] = self.fixture.content_ref(path)

        for evidence_type in TECHNICAL_EVIDENCE:
            metrics = self._base_metrics(evidence_type)
            if evidence_type == "behavioral_equivalence":
                metrics["route_coverage"] = route_coverage
            if evidence_type in {"source_startup", "target_startup"}:
                metrics["native"] = startup_native
            write_document(evidence_type, metrics)
        write_document("customer_acceptance", self._base_metrics("customer_acceptance"))
        write_document(
            "independent_review",
            {
                "organizationally_independent": True,
                "reviewed_evidence_types": list(TECHNICAL_EVIDENCE),
                "reviewed_content_digests": {
                    name: self.fixture.intake["evidence"][name]["content"]["digest"]
                    for name in TECHNICAL_EVIDENCE
                },
                "critical_findings": 0,
                "unresolved_findings": 0,
            },
        )
        write_document(
            "external_certification",
            {
                "decision": "CERTIFIED",
                "scope_bound": True,
                "certified_capability_ids": ["web"],
                "reviewed_evidence_types": list(PRE_CERTIFICATION_EVIDENCE),
                "reviewed_content_digests": {
                    name: self.fixture.intake["evidence"][name]["content"]["digest"]
                    for name in PRE_CERTIFICATION_EVIDENCE
                },
                "certificate_valid_until": "2027-01-01T00:00:00Z",
                "manual_hours": 24.0,
                "cost_per_verified_workload": 120.0,
            },
        )

        authorization_payload = self.fixture.intake["customer_authorization"]["payload"]
        authorization_payload["scope"]["evidence_content_digests"] = {
            name: self.fixture.intake["evidence"][name]["content"]["digest"]
            for name in REQUIRED_EVIDENCE
        }
        self.fixture.intake["customer_authorization"] = self.fixture.sign(
            CUSTOMER_AUTHORIZATION_ROLE, authorization_payload
        )
        authorization_digest = canonical_digest(authorization_payload)
        for evidence_type, role in EVIDENCE_ROLES.items():
            reference = self.fixture.intake["evidence"][evidence_type]["content"]
            payload = self.fixture.intake["evidence"][evidence_type]["attestation"]["payload"]
            payload["issued_at"] = "2026-07-01T00:00:00Z"
            payload["authorization_payload_digest"] = authorization_digest
            payload["content_digest"] = reference["digest"]
            payload["content_size_bytes"] = reference["size_bytes"]
            self.fixture.intake["evidence"][evidence_type]["attestation"] = self.fixture.sign(role, payload)
        self.intake_path = self.case / "intake.json"
        self.fixture.write_json(self.intake_path, self.fixture.intake)

    @property
    def evidence_root(self) -> Path:
        return self.fixture.evidence_root

    @property
    def case(self) -> Path:
        return self.fixture.case

    def evaluate(self) -> dict[str, object]:
        return evaluate_certification_campaign(
            pack_dir=self.pack,
            campaign_path=self.campaign_path,
            intake_path=self.intake_path,
            trust_store=self.fixture.trust_path,
            evidence_roots=[self.evidence_root],
            now=NOW,
        )

    def test_plan_is_complete_but_remains_not_run_and_not_certified(self) -> None:
        result = evaluate_certification_campaign(
            pack_dir=self.pack,
            campaign_path=self.campaign_path,
        )
        self.assertEqual("BLOCKED_EXTERNAL_EVIDENCE_REQUIRED", result["decision"])
        self.assertEqual("NOT_RUN", result["external_evidence_status"])
        self.assertEqual("NOT_CERTIFIED", result["production_certification"])
        self.assertEqual(list(REQUIRED_EVIDENCE), result["required_evidence_types"])

    def test_campaign_rejects_support_semantic_drift_outside_promotion_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="batch30-support-subject-") as temporary:
            pack = Path(temporary) / "framework-pack"
            shutil.copytree(self.pack, pack)
            support_path = pack / "support-matrix.json"
            support = json.loads(support_path.read_text(encoding="utf-8"))
            support["capabilities"][1]["reason"] = "tampered support semantics"
            self._write_json(support_path, support)
            with self.assertRaisesRegex(CampaignError, "support matrix certification subject drifted"):
                evaluate_certification_campaign(
                    pack_dir=pack,
                    campaign_path=pack / "certification" / "p0-p11-campaign.json",
                )

    def test_campaign_rejects_rebound_recipe_binary_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="batch30-recipe-binary-") as temporary:
            pack = Path(temporary) / "framework-pack"
            shutil.copytree(self.pack, pack)
            policy_path = pack / "certification" / "qualification-policy.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["rewrite_recipe_artifact"]["jar_sha256"] = "sha256:" + "d" * 64
            for item in policy["rewrite_recipe_artifact"]["files"]:
                if item["path"].endswith(".jar"):
                    item["sha256"] = "d" * 64
            self._write_json(policy_path, policy)

            exact_path = pack / "certification" / "exact-tuple-binding.json"
            exact = json.loads(exact_path.read_text(encoding="utf-8"))
            exact["policy"]["sha256"] = _sha256_file(policy_path)
            self._write_json(exact_path, exact)

            campaign_path = pack / "certification" / "p0-p11-campaign.json"
            campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
            campaign["tuple_binding"]["policy"]["digest"] = _sha256_file(policy_path)
            campaign["tuple_binding"]["exact_tuple"]["digest"] = _sha256_file(exact_path)
            self._write_json(campaign_path, campaign)
            with self.assertRaisesRegex(
                CampaignError, "exact tuple rewrite recipe binding drifted"
            ):
                evaluate_certification_campaign(
                    pack_dir=pack,
                    campaign_path=campaign_path,
                )

    def test_campaign_rejects_pack_content_reached_through_a_symlink_parent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="batch30-pack-symlink-") as temporary:
            pack = Path(temporary) / "framework-pack"
            shutil.copytree(self.pack, pack)
            recipes = pack / "recipes"
            real_recipes = pack / "real-recipes"
            recipes.rename(real_recipes)
            recipes.symlink_to(real_recipes.name, target_is_directory=True)
            with self.assertRaisesRegex(CampaignError, "must not traverse a symlink"):
                evaluate_certification_campaign(
                    pack_dir=pack,
                    campaign_path=pack / "certification" / "p0-p11-campaign.json",
                )

    def test_all_thirteen_real_signed_evidence_classes_reach_the_gate(self) -> None:
        self._install_full_documents()
        result = self.evaluate()
        self.assertEqual("READY_FOR_BATCH30_CERTIFICATION_GATE", result["decision"])
        self.assertEqual(list(REQUIRED_EVIDENCE), result["verified_evidence_types"])
        self.assertEqual({f"P{index}": "PASSED" for index in range(12)}, result["phase_results"])
        self.assertFalse(result["pack_status_mutated"])

    def test_promotion_documents_are_derived_only_from_reverified_results(self) -> None:
        self._install_full_documents()
        result = self.evaluate()
        documents = build_promotion_documents(self.pack, result)
        self.assertEqual("certified", documents["pack.json"]["status"])
        self.assertEqual(
            "CERTIFIED",
            documents["certification/certification.json"]["certification_decision"],
        )
        admission = documents["certification/external-admission.json"]
        self.assertFalse(admission["self_certifying"])
        self.assertTrue(admission["requires_live_external_reverification"])
        self.assertEqual(list(REQUIRED_EVIDENCE), admission["verified_evidence_types"])

    def test_certified_framework_gate_reverifies_the_complete_external_chain(self) -> None:
        self._install_full_documents()
        result = self.evaluate()
        with tempfile.TemporaryDirectory(prefix="batch30-certified-gate-") as temporary:
            promoted_pack = Path(temporary) / "framework-pack"
            shutil.copytree(self.pack, promoted_pack)
            documents = build_promotion_documents(promoted_pack, result)
            for relative, value in documents.items():
                path = promoted_pack / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            gate = Path(__file__).resolve().parents[2] / "scripts" / "batch30" / "run_framework_gate.py"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(gate),
                    str(promoted_pack),
                    "--campaign",
                    str(promoted_pack / "certification" / "p0-p11-campaign.json"),
                    "--external-intake",
                    str(self.intake_path),
                    "--trust-store",
                    str(self.fixture.trust_path),
                    "--evidence-root",
                    str(self.evidence_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertIn("status=certified decision=CERTIFIED", completed.stdout)

    def test_certified_framework_gate_rejects_tampered_admission_receipt(self) -> None:
        self._install_full_documents()
        result = self.evaluate()
        with tempfile.TemporaryDirectory(prefix="batch30-certified-admission-") as temporary:
            promoted_pack = Path(temporary) / "framework-pack"
            shutil.copytree(self.pack, promoted_pack)
            documents = build_promotion_documents(promoted_pack, result)
            documents["certification/external-admission.json"]["self_certifying"] = True
            for relative, value in documents.items():
                path = promoted_pack / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            gate = Path(__file__).resolve().parents[2] / "scripts" / "batch30" / "run_framework_gate.py"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(gate),
                    str(promoted_pack),
                    "--campaign",
                    str(promoted_pack / "certification" / "p0-p11-campaign.json"),
                    "--external-intake",
                    str(self.intake_path),
                    "--trust-store",
                    str(self.fixture.trust_path),
                    "--evidence-root",
                    str(self.evidence_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(2, completed.returncode, completed.stdout + completed.stderr)
            self.assertIn("admission receipt does not match", completed.stderr)

    def test_apply_promotion_is_atomic_and_post_gate_verified(self) -> None:
        self._install_full_documents()
        with tempfile.TemporaryDirectory(prefix="batch30-atomic-promotion-") as temporary:
            promoted_pack = Path(temporary) / "framework-pack"
            shutil.copytree(self.pack, promoted_pack)
            result = promote(
                pack_dir=promoted_pack,
                campaign_path=promoted_pack / "certification" / "p0-p11-campaign.json",
                intake_path=self.intake_path,
                trust_store=self.fixture.trust_path,
                evidence_roots=[self.evidence_root],
                apply=True,
            )
            self.assertEqual("CERTIFIED", result["decision"])
            self.assertEqual(
                "certified",
                json.loads((promoted_pack / "pack.json").read_text())["status"],
            )
            self.assertFalse((promoted_pack / ".batch30-certification-promotion.lock").exists())

    def test_failed_post_write_gate_restores_every_authoritative_byte(self) -> None:
        self._install_full_documents()
        with tempfile.TemporaryDirectory(prefix="batch30-promotion-rollback-") as temporary:
            promoted_pack = Path(temporary) / "framework-pack"
            shutil.copytree(self.pack, promoted_pack)
            tracked = [
                "pack.json",
                "support-matrix.json",
                "certification/evidence.json",
                "certification/certification.json",
            ]
            before = {name: (promoted_pack / name).read_bytes() for name in tracked}
            failed = subprocess.CompletedProcess([], 2, stdout="", stderr="forced gate failure")
            with patch(
                "scripts.batch30.promote_framework_certification._run_post_write_gate",
                return_value=failed,
            ):
                with self.assertRaisesRegex(PromotionError, "forced gate failure"):
                    promote(
                        pack_dir=promoted_pack,
                        campaign_path=promoted_pack / "certification" / "p0-p11-campaign.json",
                        intake_path=self.intake_path,
                        trust_store=self.fixture.trust_path,
                        evidence_roots=[self.evidence_root],
                        apply=True,
                    )
            self.assertEqual(before, {name: (promoted_pack / name).read_bytes() for name in tracked})
            self.assertFalse((promoted_pack / "certification/external-admission.json").exists())
            self.assertFalse((promoted_pack / ".batch30-certification-promotion.lock").exists())

    def test_re_signed_99_percent_claim_still_fails_the_100_percent_gate(self) -> None:
        self._install_full_documents(route_coverage=0.99)
        with self.assertRaisesRegex(CampaignError, "route_coverage must be 1.0"):
            self.evaluate()

    def test_signed_waiver_cannot_bypass_zero_tolerance(self) -> None:
        self._install_full_documents(waivers=True)
        with self.assertRaisesRegex(CampaignError, "unknown, not-run, or waived work"):
            self.evaluate()

    def test_raw_evidence_tamper_is_rejected(self) -> None:
        self._install_full_documents()
        raw = self.evidence_root / "raw-security.log"
        raw.write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(CampaignError, "content verification failed"):
            self.evaluate()

    def test_signed_non_native_startup_cannot_pass(self) -> None:
        self._install_full_documents(startup_native=False)
        with self.assertRaisesRegex(CampaignError, "native must be true"):
            self.evaluate()

    def test_signed_toolchain_identity_drift_across_evidence_is_rejected(self) -> None:
        self._install_full_documents(toolchain_drift=True)
        with self.assertRaisesRegex(CampaignError, "toolchains digest drifted"):
            self.evaluate()

    def test_signed_runtime_evidence_with_impossible_chronology_is_rejected(self) -> None:
        self._install_full_documents(target_startup_before_build=True)
        with self.assertRaisesRegex(CampaignError, "target startup predates target build"):
            self.evaluate()

    def test_signed_document_for_a_different_campaign_cannot_pass(self) -> None:
        self._install_full_documents()
        evidence_type = "security"
        path = self.evidence_root / f"{evidence_type}.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["campaign_digest"] = "sha256:" + "f" * 64
        self.fixture.write_json(path, document)
        reference = self.fixture.content_ref(path)
        self.fixture.intake["evidence"][evidence_type]["content"] = reference
        authorization_payload = self.fixture.intake["customer_authorization"]["payload"]
        authorization_payload["scope"]["evidence_content_digests"][evidence_type] = reference["digest"]
        self.fixture.intake["customer_authorization"] = self.fixture.sign(
            CUSTOMER_AUTHORIZATION_ROLE, authorization_payload
        )
        authorization_digest = canonical_digest(authorization_payload)
        for current_type, role in EVIDENCE_ROLES.items():
            current_reference = self.fixture.intake["evidence"][current_type]["content"]
            payload = self.fixture.intake["evidence"][current_type]["attestation"]["payload"]
            payload["authorization_payload_digest"] = authorization_digest
            if current_type == evidence_type:
                payload["content_digest"] = current_reference["digest"]
                payload["content_size_bytes"] = current_reference["size_bytes"]
            self.fixture.intake["evidence"][current_type]["attestation"] = self.fixture.sign(
                role, payload
            )
        self.fixture.write_json(self.intake_path, self.fixture.intake)
        with self.assertRaisesRegex(CampaignError, "campaign digest drifted"):
            self.evaluate()

    def test_holdout_corpus_bytes_are_content_verified(self) -> None:
        self._install_full_documents()
        corpus = self.evidence_root / "corpus-holdout.tar.zst"
        corpus.write_bytes(b"tampered holdout corpus\n")
        with self.assertRaisesRegex(CampaignError, "content verification failed"):
            self.evaluate()

    def test_machine_readable_schemas_track_the_exact_campaign_and_evidence_sets(self) -> None:
        from jsonschema import Draft202012Validator

        campaign_schema = json.loads((SCHEMA_ROOT / "certification-campaign.schema.json").read_text())
        evidence_schema = json.loads((SCHEMA_ROOT / "external-evidence-document.schema.json").read_text())
        Draft202012Validator.check_schema(campaign_schema)
        Draft202012Validator.check_schema(evidence_schema)
        Draft202012Validator(campaign_schema).validate(self.campaign)
        self.assertEqual(
            list(REQUIRED_EVIDENCE),
            campaign_schema["$defs"]["evidenceType"]["enum"],
        )
        self.assertEqual(
            list(REQUIRED_EVIDENCE),
            evidence_schema["$defs"]["evidenceType"]["enum"],
        )

    def test_all_thirteen_external_documents_validate_against_the_published_schema(self) -> None:
        from jsonschema import Draft202012Validator

        self._install_full_documents()
        schema = json.loads(
            (SCHEMA_ROOT / "external-evidence-document.schema.json").read_text()
        )
        validator = Draft202012Validator(schema)
        for evidence_type in REQUIRED_EVIDENCE:
            document = json.loads(
                (self.evidence_root / f"{evidence_type}.json").read_text()
            )
            validator.validate(document)

    def test_published_schema_rejects_under_threshold_performance_evidence(self) -> None:
        from jsonschema import Draft202012Validator

        self._install_full_documents()
        schema = json.loads(
            (SCHEMA_ROOT / "external-evidence-document.schema.json").read_text()
        )
        document = json.loads(
            (self.evidence_root / "performance.json").read_text()
        )
        document["metrics"]["request_count"] = 9_999
        errors = list(Draft202012Validator(schema).iter_errors(document))
        self.assertTrue(errors)
        self.assertTrue(
            any("less than the minimum" in error.message for error in errors),
            [error.message for error in errors],
        )

    def test_published_schema_rejects_cross_type_metric_fields(self) -> None:
        from jsonschema import Draft202012Validator

        self._install_full_documents()
        schema = json.loads(
            (SCHEMA_ROOT / "external-evidence-document.schema.json").read_text()
        )
        document = json.loads((self.evidence_root / "security.json").read_text())
        document["metrics"]["artifact_bound"] = True
        errors = list(Draft202012Validator(schema).iter_errors(document))
        self.assertTrue(errors)
        self.assertTrue(
            any("Additional properties are not allowed" in error.message for error in errors),
            [error.message for error in errors],
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

from elmos_legacy_web_modernization import (
    CATALOG,
    SKILL_REGISTRY,
    ModernizationService,
    dispatch,
    validate_skill_registry,
)
from elmos_legacy_web_modernization.snapshot import SnapshotError, capture_repository
from elmos_legacy_web_modernization.contracts import RuntimeRequest
from elmos_legacy_web_modernization.persistence import PersistenceError, StateStore
from elmos_legacy_web_modernization.runtime import RuntimeErrorContract
from elmos_legacy_web_modernization.external_evidence import (
    CLAIMS,
    EVIDENCE_ROLES,
    EVIDENCE_TYPES,
    ExternalEvidenceError,
    not_run_external_status,
    evaluate_external_intake,
)
from scripts.precision_migration.trust import canonical_bytes


def fixture_root() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    holder = tempfile.TemporaryDirectory()
    root = Path(holder.name).resolve()
    (root / "src/main/java/com/acme").mkdir(parents=True)
    (root / "WEB-INF/jsp").mkdir(parents=True)
    (root / "pom.xml").write_text(
        """<project>
          <artifactId>orders</artifactId><packaging>war</packaging>
          <dependencies>
            <dependency><groupId>org.apache.struts</groupId><artifactId>struts-core</artifactId><version>1.3.10</version></dependency>
            <dependency><groupId>javax.servlet</groupId><artifactId>javax.servlet-api</artifactId><version>4.0.1</version></dependency>
          </dependencies>
        </project>""",
        encoding="utf-8",
    )
    (root / "WEB-INF/struts-config.xml").write_text(
        """<struts-config><action-mappings>
          <action path="/orders/create" type="com.acme.CreateOrderAction">
            <forward name="success" path="/WEB-INF/jsp/success.jsp"/>
          </action>
        </action-mappings></struts-config>""",
        encoding="utf-8",
    )
    (root / "WEB-INF/jsp/success.jsp").write_text(
        '<%@ taglib prefix="bean" uri="http://struts.apache.org/tags-bean" %><bean:write name="order"/>',
        encoding="utf-8",
    )
    (root / "application-prod.properties").write_text(
        "db.password=do-not-persist-this-value\napi_token=do-not-persist-this-token\njavax.servlet.secret=do-not-persist-this-value\n",
        encoding="utf-8",
    )
    (root / "src/main/java/com/acme/CreateOrderAction.java").write_text(
        """package com.acme;
        class CreateOrderAction {
          void execute(javax.servlet.http.HttpServletRequest request) {
            request.getSession().setAttribute("currentOrder", order);
            request.getParameter("customerId");
            // Class.forName is intentionally an unresolved dynamic boundary.
            Class.forName("com.acme.Plugin");
          }
        }""",
        encoding="utf-8",
    )
    return holder, root


def request(root: Path, skill_id: str, *, authority_profile: str = "scan-readonly") -> dict:
    return {
        "request_id": "request-" + skill_id[:2],
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "job_id": "job-a",
        "skill_id": skill_id,
        "idempotency_key": "idempotency-" + skill_id,
        "inputs": {"repository_root": root.as_posix()},
        "policy": {"mode": "preserve-first", "equivalence": "strict"},
        "authority": {
            "environment_id": "env-local",
            "profile": authority_profile,
            "scopes": ["repository-read"],
            "fencing_token": 7,
        },
    }


class RuntimeTests(unittest.TestCase):
    def test_catalog_and_registry_are_exact_and_immutable_shape(self) -> None:
        validate_skill_registry()
        self.assertEqual(len(CATALOG.skills), 55)
        self.assertEqual(len(SKILL_REGISTRY), 55)
        self.assertEqual(len({binding.operation for binding in SKILL_REGISTRY.values()}), 55)
        self.assertEqual(len({binding.handler_id for binding in SKILL_REGISTRY.values()}), 55)
        self.assertEqual(tuple(SKILL_REGISTRY), CATALOG.skill_ids)

    def test_snapshot_records_symlink_without_following_it(self) -> None:
        holder, root = fixture_root()
        try:
            (root / "link").symlink_to(root / "pom.xml")
            snapshot = capture_repository(root)
            link = next(item for item in snapshot.files if item.path == "link")
            self.assertEqual(link.kind, "symlink")
            self.assertNotIn("artifactId", link.manifest())
        finally:
            holder.cleanup()

    def test_snapshot_rejects_symlinked_root(self) -> None:
        holder, root = fixture_root()
        alias = root.parent / (root.name + "-alias")
        try:
            alias.symlink_to(root, target_is_directory=True)
            with self.assertRaises(SnapshotError):
                capture_repository(alias)
        finally:
            alias.unlink(missing_ok=True)
            holder.cleanup()

    def test_semantic_ir_recovers_route_pipeline_binding_state_and_unknown(self) -> None:
        holder, root = fixture_root()
        try:
            result = dispatch(request(root, "31-legacy-web-semantic-ir"))
            self.assertEqual(result["state"], "LOCAL_EXECUTED")
            payload = result["artifacts"][0]["payload"]
            self.assertEqual(payload["endpoints"][0]["pathPattern"], "/orders/create")
            self.assertTrue(payload["pipelines"][0]["steps"])
            self.assertIn("currentOrder", {item["key"] for item in payload["stateObjects"]})
            self.assertTrue(payload["unknownRefs"])
            self.assertEqual(result["externalEvidence"], "NOT_RUN")
            self.assertEqual(result["certification"], "NOT_CERTIFIED")
        finally:
            holder.cleanup()

    def test_snapshot_digest_changes_when_a_file_changes(self) -> None:
        holder, root = fixture_root()
        try:
            first = dispatch(request(root, "02-reproducible-repository-snapshot"))
            first_digest = first["artifacts"][0]["payload"]["digest"]
            pom = root / "pom.xml"
            pom.write_text(pom.read_text(encoding="utf-8") + "\n<!-- changed -->\n", encoding="utf-8")
            second = dispatch(request(root, "02-reproducible-repository-snapshot"))
            self.assertNotEqual(first_digest, second["artifacts"][0]["payload"]["digest"])
        finally:
            holder.cleanup()

    def test_every_exact_handler_has_a_capability_specific_result(self) -> None:
        holder, root = fixture_root()
        try:
            for skill_id, binding in SKILL_REGISTRY.items():
                with self.subTest(skill=skill_id):
                    result = dispatch(request(root, skill_id))
                    self.assertEqual(result["handlerId"], binding.handler_id)
                    self.assertEqual(result["skillId"], skill_id)
                    self.assertIn(result["state"], {"LOCAL_EXECUTED", "PARTIAL_LOCAL_EXECUTED", "PLANNING_ONLY", "BLOCKED"})
                    self.assertFalse(result["sideEffects"])
                    self.assertEqual(result["externalEvidence"], "NOT_RUN")
                    self.assertEqual(result["certification"], "NOT_CERTIFIED")
                    self.assertEqual(len(result.get("artifacts", [])), 1)
        finally:
            holder.cleanup()

    def test_differential_oracle_is_strict_and_reports_critical_dimensions(self) -> None:
        holder, root = fixture_root()
        try:
            value = request(root, "62-differential-http-and-view-oracle")
            value["inputs"]["observations"] = {
                "legacy": {"route": {"path": "/orders/create"}, "security": {"decision": "allow"}},
                "target": {"route": {"path": "/orders/create"}, "security": {"decision": "deny"}},
            }
            result = dispatch(value)
            report = result["artifacts"][0]["payload"]
            self.assertEqual(report["gate"]["status"], "failed")
            self.assertEqual(report["summary"]["criticalMismatches"], 1)
            self.assertTrue(any(item["dimension"] == "security" for item in report["mismatches"]))
        finally:
            holder.cleanup()

    def test_generators_use_recovered_bindings_and_deny_unverified_security(self) -> None:
        holder, root = fixture_root()
        try:
            generated = dispatch(request(root, "51-struts1-to-springmvc-generator"))
            files = generated["artifacts"][0]["payload"]["files"]
            source = next(iter(files.values()))
            self.assertIn('@RequestParam(name = "customerId"', source)
            self.assertNotIn("_legacyRequest", source)
            self.assertIn("forward: /WEB-INF/jsp/success.jsp", source)

            security = dispatch(request(root, "55-spring-security-validation-transaction-generator"))
            security_source = next(iter(security["artifacts"][0]["payload"]["files"].values()))
            self.assertIn("anyRequest().denyAll()", security_source)
            self.assertIn("csrf(Customizer.withDefaults())", security_source)
        finally:
            holder.cleanup()

    def test_change_set_requires_transform_authority(self) -> None:
        holder, root = fixture_root()
        try:
            blocked = dispatch(request(root, "58-idempotent-change-set-commit"))
            self.assertEqual(blocked["state"], "BLOCKED")
            transform = dispatch(request(root, "58-idempotent-change-set-commit", authority_profile="transform"))
            self.assertEqual(transform["state"], "PLANNING_ONLY")
            self.assertFalse(transform["artifacts"][0]["payload"]["gitMutation"])
        finally:
            holder.cleanup()

    def test_service_persists_artifacts_and_replays_idempotently(self) -> None:
        holder, root = fixture_root()
        state_holder = tempfile.TemporaryDirectory()
        try:
            service = ModernizationService(Path(state_holder.name).resolve())
            value = request(root, "31-legacy-web-semantic-ir")
            first = service.execute(value)
            second = service.execute(value)
            self.assertEqual(first["idempotency"], "CREATED")
            self.assertEqual(second["idempotency"], "REPLAYED")
            self.assertTrue((Path(state_holder.name) / "control-plane.sqlite3").exists())
            self.assertTrue(list((Path(state_holder.name) / "artifacts").rglob("*.json")))
        finally:
            state_holder.cleanup()
            holder.cleanup()

    def test_service_records_run_state_and_change_set_with_lease_fence(self) -> None:
        holder, root = fixture_root()
        state_holder = tempfile.TemporaryDirectory()
        try:
            service = ModernizationService(Path(state_holder.name).resolve())
            result = service.execute(request(root, "58-idempotent-change-set-commit", authority_profile="transform"))
            self.assertEqual(result["state"], "PLANNING_ONLY")
            with sqlite3.connect(Path(state_holder.name).resolve() / "control-plane.sqlite3") as db:
                run_state = db.execute("SELECT state FROM modernization_run WHERE job_id = ?", ("job-a",)).fetchone()[0]
                change_set = db.execute("SELECT state, fencing_token FROM change_set WHERE job_id = ?", ("job-a",)).fetchone()
            self.assertEqual(run_state, "COMPLETED")
            self.assertEqual(change_set[0], "STAGED")
            self.assertGreater(change_set[1], 0)
        finally:
            state_holder.cleanup()
            holder.cleanup()

    def test_stale_fencing_token_cannot_commit_a_checkpoint(self) -> None:
        holder, root = fixture_root()
        state_holder = tempfile.TemporaryDirectory()
        try:
            store = StateStore(Path(state_holder.name).resolve() / "control.sqlite3")
            value = request(root, "02-reproducible-repository-snapshot")
            typed = RuntimeRequest.from_dict(value)
            lease_id, token = store.acquire_lease(typed)
            store.checkpoint(typed, state="safe-point", cursor={"offset": 1}, lease_id=lease_id, fencing_token=token)
            with self.assertRaises(PersistenceError):
                store.verify_lease(typed, lease_id=lease_id, fencing_token=token + 1)
            store.release_lease(typed, lease_id=lease_id, fencing_token=token)
        finally:
            state_holder.cleanup()
            holder.cleanup()

    def test_artifacts_redact_secrets_from_structured_inputs_and_source_rewrites(self) -> None:
        holder, root = fixture_root()
        try:
            value = request(root, "00-modernization-orchestrator")
            value["inputs"]["target"] = {"framework": "spring-boot", "client_secret": "never-store-this"}
            value["inputs"]["observations"] = {"authorization": "Bearer never-store-this-token"}
            result = dispatch(value)
            serialized = json.dumps(result, ensure_ascii=False)
            self.assertNotIn("never-store-this", serialized)
            self.assertIn("<redacted>", serialized)

            rewritten = dispatch(request(root, "54-jakarta-and-dependency-migration"))
            rewritten_text = json.dumps(rewritten, ensure_ascii=False)
            self.assertNotIn("do-not-persist-this-value", rewritten_text)
            self.assertNotIn("do-not-persist-this-token", rewritten_text)
        finally:
            holder.cleanup()

    def test_unknown_skill_and_unapproved_cutover_fail_closed(self) -> None:
        holder, root = fixture_root()
        try:
            unknown = request(root, "99-unknown-skill")
            with self.assertRaises(RuntimeErrorContract):
                dispatch(unknown)
            cutover = request(root, "73-production-cutover-rollback")
            cutover["authority"]["profile"] = "production-cutover"
            with self.assertRaises(ValueError):
                RuntimeRequest.from_dict(cutover)
            cutover["authority"]["approved"] = "false"
            with self.assertRaises(ValueError):
                RuntimeRequest.from_dict(cutover)
        finally:
            holder.cleanup()

    def test_run_readonly_covers_pinned_dag_without_external_claim(self) -> None:
        holder, root = fixture_root()
        state_holder = tempfile.TemporaryDirectory()
        try:
            service = ModernizationService(Path(state_holder.name).resolve())
            value = request(root, "00-modernization-orchestrator")
            result = service.run_readonly(value)
            self.assertEqual(result["skills"], 55)
            self.assertEqual(result["externalEvidence"], "NOT_RUN")
            self.assertEqual(result["certification"], "NOT_CERTIFIED")
            self.assertEqual(len(result["results"]), 55)
        finally:
            state_holder.cleanup()
            holder.cleanup()

    def test_external_evidence_boundary_is_explicit_and_fail_closed(self) -> None:
        status = not_run_external_status()
        self.assertEqual(status["evidence_status"], "NOT_RUN")
        self.assertEqual(status["externalEvidence"], "NOT_RUN")
        self.assertEqual(status["certification"], "NOT_CERTIFIED")
        self.assertEqual(len(status["required_evidence_types"]), 13)
        with self.assertRaises(ExternalEvidenceError):
            from elmos_legacy_web_modernization.external_evidence import evaluate_external_intake

            evaluate_external_intake(
                {"schema_version": 1, "namespace": "wrong"},
                expected_binding={},
                evidence_root=Path("/tmp"),
                trust_store=Path("/tmp/missing-trust-store.json"),
            )

    def test_certification_artifact_exposes_external_gate_requirements(self) -> None:
        holder, root = fixture_root()
        try:
            result = dispatch(request(root, "74-evidence-bundle-and-e0-e5-certification"))
            payload = result["artifacts"][0]["payload"]
            external_gate = next(item for item in payload["gates"] if item["id"] == "EXTERNAL_EVIDENCE")
            self.assertEqual(external_gate["evidenceStatus"], "NOT_RUN")
            self.assertEqual(external_gate["decision"], "BLOCKED_EXTERNAL_EVIDENCE_REQUIRED")
            self.assertEqual(external_gate["certification"], "NOT_CERTIFIED")
            self.assertIn("external_certification", external_gate["requiredEvidenceTypes"])
        finally:
            holder.cleanup()


class ExternalEvidenceTests(unittest.TestCase):
    """Exercise the real Ed25519/content-addressed admission path."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="legacy-web-external-tests-")
        cls.root = Path(cls.temporary.name)
        cls.keys: dict[str, Path] = {}
        records: list[dict[str, object]] = []
        for index, evidence_type in enumerate(EVIDENCE_TYPES):
            role = EVIDENCE_ROLES[evidence_type]
            private = cls.root / f"key-{index}.private.pem"
            public = cls.root / f"key-{index}.public.pem"
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
            cls.keys[evidence_type] = private
            records.append(
                {
                    "key_id": f"test-key-{index}",
                    "actor_id": f"test-signer-{index}",
                    "organization_id": {
                        "producer": "org-producer",
                        "rootless": "org-rootless",
                        "independent": "org-independent",
                        "customer": "org-customer",
                        "certification": "org-certification",
                    }[
                        {
                            "source_build": "producer",
                            "target_build": "rootless",
                            "source_startup": "producer",
                            "target_startup": "rootless",
                            "behavioral_equivalence": "rootless",
                            "security": "independent",
                            "performance": "independent",
                            "operability": "independent",
                            "sbom": "independent",
                            "rollback": "independent",
                            "independent_review": "independent",
                            "customer_acceptance": "customer",
                            "external_certification": "certification",
                        }[evidence_type]
                    ],
                    "roles": [role],
                    "public_key_path": public.name,
                    "not_before": "2025-01-01T00:00:00Z",
                    "not_after": "2030-01-01T00:00:00Z",
                    "revoked": False,
                }
            )
        cls.trust_store = cls.root / "trust-store.json"
        cls.trust_store.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "namespace": "elmos.legacy-web.external-certification",
                    "keys": records,
                    "revoked_record_ids": [],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        cls.binding = {
            "package": "elmos.java-legacy-web.repository-modernization",
            "package_version": "1.0.0",
            "archive_digest": CATALOG.archive_digest,
            "source_snapshot_digest": "sha256:" + "b" * 64,
            "target_artifact_digest": "sha256:" + "c" * 64,
            "target_profile_digest": "sha256:" + "d" * 64,
            "policy_snapshot_digest": "sha256:" + "e" * 64,
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def signed_envelope(self, evidence_type: str, payload: dict[str, object]) -> dict[str, object]:
        index = EVIDENCE_TYPES.index(evidence_type)
        payload_path = self.root / f"payload-{index}.json"
        signature_path = self.root / f"signature-{index}.bin"
        payload_path.write_bytes(canonical_bytes(payload))
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(self.keys[evidence_type]),
                "-rawin",
                "-in",
                str(payload_path),
                "-out",
                str(signature_path),
            ],
            check=True,
            capture_output=True,
        )
        return {
            "algorithm": "ed25519",
            "key_id": f"test-key-{index}",
            "payload": payload,
            "signature": base64.b64encode(signature_path.read_bytes()).decode("ascii"),
        }

    def valid_intake(self) -> dict[str, object]:
        organizations = {
            "producer": "org-producer",
            "customer": "org-customer",
            "rootless": "org-rootless",
            "independent": "org-independent",
            "certification": "org-certification",
        }
        intake_id = "intake-test-001"
        binding_digest = "sha256:" + hashlib.sha256(canonical_bytes(self.binding)).hexdigest()
        evidence: dict[str, object] = {}
        executors: dict[str, object] = {}
        for index, evidence_type in enumerate(EVIDENCE_TYPES):
            content_path = self.root / f"content-{index}.json"
            content_path.write_text(
                json.dumps({"evidence_type": evidence_type, "fixture": index}, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            raw = content_path.read_bytes()
            content = {
                "path": content_path.name,
                "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
                "media_type": "application/json",
            }
            executor = {
                "actor_id": f"test-executor-{index}",
                "organization_id": f"org-executor-{index}",
            }
            executors[evidence_type] = executor
            signer_org = {
                "source_build": "org-producer",
                "target_build": "org-rootless",
                "source_startup": "org-producer",
                "target_startup": "org-rootless",
                "behavioral_equivalence": "org-rootless",
                "security": "org-independent",
                "performance": "org-independent",
                "operability": "org-independent",
                "sbom": "org-independent",
                "rollback": "org-independent",
                "independent_review": "org-independent",
                "customer_acceptance": "org-customer",
                "external_certification": "org-certification",
            }[evidence_type]
            payload = {
                "record_id": f"record-{index}",
                "issued_at": "2026-01-01T00:00:00Z",
                "expires_at": "2029-01-01T00:00:00Z",
                "actor_id": f"test-signer-{index}",
                "organization_id": signer_org,
                "role": EVIDENCE_ROLES[evidence_type],
                "intake_id": intake_id,
                "binding_digest": binding_digest,
                "evidence_type": evidence_type,
                "content_digest": content["sha256"],
                "content_size_bytes": content["size_bytes"],
                "executor_actor_id": executor["actor_id"],
                "executor_organization_id": executor["organization_id"],
                "outcome": "CERTIFIED" if evidence_type == "external_certification" else "ACCEPTED" if evidence_type == "customer_acceptance" else "PASS",
                "evidence_class": "EXTERNAL_NON_SYNTHETIC",
                "synthetic": False,
                "unknowns": [],
                "not_run": [],
                "claims": CLAIMS[evidence_type],
            }
            evidence[evidence_type] = {
                "content": content,
                "attestation": self.signed_envelope(evidence_type, payload),
            }
        return {
            "schema_version": 1,
            "namespace": "elmos.legacy-web.external-certification",
            "intake_id": intake_id,
            "organizations": organizations,
            "binding": self.binding,
            "evidence_executors": executors,
            "evidence": evidence,
        }

    def test_valid_signed_intake_is_review_ready_but_not_certified(self) -> None:
        result = evaluate_external_intake(
            self.valid_intake(),
            expected_binding=self.binding,
            evidence_root=self.root,
            trust_store=self.trust_store,
            now=datetime(2026, 8, 27, tzinfo=timezone.utc),
        )
        self.assertEqual(result["evidence_status"], "VERIFIED_EXTERNAL_INTAKE")
        self.assertEqual(result["externalEvidence"], "VERIFIED_EXTERNAL_INTAKE")
        self.assertEqual(result["decision"], "READY_FOR_EXTERNAL_GATE_REVIEW")
        self.assertEqual(result["certification"], "NOT_CERTIFIED")
        self.assertFalse(result["certification_promoted"])
        self.assertEqual(len(result["verified_evidence_types"]), 13)

    def test_tampered_external_content_is_rejected(self) -> None:
        intake = self.valid_intake()
        first = intake["evidence"][EVIDENCE_TYPES[0]]
        assert isinstance(first, dict)
        path = self.root / first["content"]["path"]
        path.write_text("tampered\n", encoding="utf-8")
        with self.assertRaises(ExternalEvidenceError):
            evaluate_external_intake(
                intake,
                expected_binding=self.binding,
                evidence_root=self.root,
                trust_store=self.trust_store,
                now=datetime(2026, 8, 27, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()

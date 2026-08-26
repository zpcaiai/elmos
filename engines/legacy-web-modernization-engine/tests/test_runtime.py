from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()

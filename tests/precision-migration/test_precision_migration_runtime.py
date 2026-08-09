from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.precision_migration.adapters import AdapterRegistry, execute
from scripts.precision_migration.contracts import ContractRegistry
from scripts.precision_migration.exact import ExactImplementationRegistry
from scripts.precision_migration.generated_handlers import EXACT_HANDLERS
from scripts.precision_migration.generated_orchestrators import ORCHESTRATOR_HANDLERS
from scripts.precision_migration.jobs import JobError, JobStore
from scripts.precision_migration.native import EXTERNAL_NATIVE_ADAPTERS, NATIVE_ADAPTERS
from scripts.precision_migration.orchestration import OrchestratorRegistry
from scripts.precision_migration.run_gate import (
    EXTERNAL_CHECKS,
    LOCAL_CHECKS,
    evaluate_gate,
    gate_binding_digest,
)
from scripts.precision_migration.run_production_code_gate import build as build_production_code_gate
from scripts.precision_migration.runtime import (
    Registry,
    batch_plan,
    evaluate,
    write_bundle,
)
from scripts.precision_migration.trust import (
    TrustStore,
    canonical_bytes,
    request_binding_digest,
    verify_content_reference,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
ENVIRONMENT_DIGEST = "sha256:" + "b" * 64


class PrecisionMigrationRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = Registry.load()
        cls.adapter_registry = AdapterRegistry.load()
        cls.temporary = tempfile.TemporaryDirectory(prefix="precision-runtime-tests-")
        cls.root = Path(cls.temporary.name)
        cls.keys: dict[str, Path] = {}
        trust_keys = []
        for role in ("evidence-authorizer", "proof-verifier", "release-approver", "gate-evidence-authorizer", "certificate-signer"):
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
            trust_keys.append(
                {
                    "key_id": f"test-{role}",
                    "roles": [role],
                    "public_key_path": public.name,
                    "not_before": "2025-01-01T00:00:00Z",
                    "not_after": "2030-01-01T00:00:00Z",
                    "revoked": False,
                }
            )
        cls.trust_path = cls.root / "trust-store.json"
        cls.trust_path.write_text(
            json.dumps({"schema_version": 1, "keys": trust_keys, "revoked_record_ids": []}),
            encoding="utf-8",
        )
        cls.trust_store = TrustStore.load(cls.trust_path)
        cls.source = cls.root / "source.json"
        cls.source.write_text('{"source":"fixture"}\n', encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def sign(self, role: str, payload: dict[str, object]) -> dict[str, object]:
        payload_path = self.root / f"payload-{role}-{payload['record_id']}.json"
        signature_path = self.root / f"signature-{role}-{payload['record_id']}.bin"
        payload_path.write_bytes(canonical_bytes(payload))
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(self.keys[role]),
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
            "key_id": f"test-{role}",
            "payload": payload,
            "signature": base64.b64encode(signature_path.read_bytes()).decode("ascii"),
        }

    def content_ref(self, path: Path) -> dict[str, object]:
        content = path.read_bytes()
        return {
            "uri": path.resolve().as_uri(),
            "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "media_type": "application/json",
        }

    def asset(self) -> dict[str, object]:
        return {**self.content_ref(self.source), "sensitivity": "internal", "version": "fixture-v1"}

    def base_request(self, skill: str, mode: str = "assess") -> dict[str, object]:
        return {
            "request_id": f"test-{skill}-{mode}",
            "skill": skill,
            "mode": mode,
            "inputs": {"assets": [self.asset()], "parameters": {}},
            "policy": {
                "unresolved_differences": "block",
                "allow_test_weakening": False,
                "require_provenance": True,
                "risk_level": "medium",
                "request_actor": "requester-a",
            },
            "evidence": [],
            "semantic_losses": [],
            "approvals": [],
        }

    def passed(self, request: dict[str, object], kind: str) -> dict[str, object]:
        artifact = self.root / f"evidence-{request['request_id']}-{kind}.json"
        if not artifact.exists():
            artifact.write_text(json.dumps({"kind": kind, "result": "PASS"}) + "\n", encoding="utf-8")
        reference = self.content_ref(artifact)
        executor = f"executor-{kind}"
        verifier = f"verifier-{kind}"
        authorization = self.sign(
            "evidence-authorizer",
            {
                "record_type": "EVIDENCE_AUTHORIZATION",
                "record_id": f"auth-{request['request_id']}-{kind}",
                "request_id": request["request_id"],
                "skill": request["skill"],
                "evidence_kind": kind,
                "artifact_digest": reference["digest"],
                "executor": executor,
                "verifier": verifier,
                "request_digest": request_binding_digest(request),
                "issued_at": "2025-12-31T00:00:00Z",
                "expires_at": "2026-12-31T00:00:00Z",
            },
        )
        return {
            "kind": kind,
            "state": "PASS",
            "artifact_uri": reference["uri"],
            "digest": reference["digest"],
            "size_bytes": reference["size_bytes"],
            "media_type": reference["media_type"],
            "executor": executor,
            "verifier": verifier,
            "replay_command": f"python3 replay.py --kind {kind}",
            "environment_digest": ENVIRONMENT_DIGEST,
            "authorization": authorization,
        }

    def complete_request(self, skill: str, mode: str = "assess") -> dict[str, object]:
        kinds = {
            "assess": ["input-provenance", "assessment-schema"],
            "transform": ["input-provenance", "source-build", "target-build", "source-target-differential", "artifact-provenance"],
            "validate": ["input-provenance", "source-build", "target-build", "negative-tests", "source-target-differential", "artifact-provenance"],
            "repair": ["input-provenance", "failure-reproduction", "target-build", "regression-tests", "differential-replay", "artifact-provenance"],
            "certify": ["input-provenance", "source-build", "target-build", "negative-tests", "source-target-differential", "artifact-provenance", "independent-review"],
        }[mode]
        request = self.base_request(skill, mode)
        request["evidence"] = [self.passed(request, kind) for kind in kinds]
        return request

    def evaluate(self, request: dict[str, object]) -> dict[str, object]:
        return evaluate(
            request,
            self.registry,
            evidence_roots=[self.root],
            trust_store=self.trust_store,
            now=NOW,
        )

    def test_loaded_trust_store_snapshots_public_key_material(self) -> None:
        snapshot = self.root / "trust-snapshot"
        snapshot.mkdir()
        public = snapshot / "evidence-public.pem"
        public.write_bytes((self.root / "evidence-authorizer.public.pem").read_bytes())
        store_path = snapshot / "trust-store.json"
        store_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "keys": [{
                        "key_id": "test-evidence-authorizer",
                        "roles": ["evidence-authorizer"],
                        "public_key_path": public.name,
                        "not_before": "2025-01-01T00:00:00Z",
                        "not_after": "2030-01-01T00:00:00Z",
                        "revoked": False,
                    }],
                    "revoked_record_ids": [],
                }
            ),
            encoding="utf-8",
        )
        loaded = TrustStore.load(store_path)
        payload = {
            "record_type": "KEY_SNAPSHOT_TEST",
            "record_id": "key-snapshot-test",
            "issued_at": "2025-12-31T00:00:00Z",
            "expires_at": "2026-12-31T00:00:00Z",
        }
        envelope = self.sign("evidence-authorizer", payload)
        public.write_bytes((self.root / "proof-verifier.public.pem").read_bytes())
        verified = loaded.verify_envelope(
            envelope,
            required_role="evidence-authorizer",
            bindings={"record_type": "KEY_SNAPSHOT_TEST"},
            now=NOW,
        )
        self.assertEqual("key-snapshot-test", verified["record_id"])
        with self.assertRaisesRegex(ValueError, "signature verification failed"):
            TrustStore.load(store_path).verify_envelope(
                envelope,
                required_role="evidence-authorizer",
                bindings={"record_type": "KEY_SNAPSHOT_TEST"},
                now=NOW,
            )

    def test_trust_store_from_bytes_uses_the_supplied_json_snapshot(self) -> None:
        snapshot = self.root / "trust-json-snapshot"
        snapshot.mkdir()
        public = snapshot / "evidence-public.pem"
        public.write_bytes((self.root / "evidence-authorizer.public.pem").read_bytes())
        store_path = snapshot / "trust-store.json"
        store_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "keys": [{
                        "key_id": "snapshot-evidence-authorizer",
                        "roles": ["evidence-authorizer"],
                        "public_key_path": public.name,
                        "not_before": "2025-01-01T00:00:00Z",
                        "not_after": "2030-01-01T00:00:00Z",
                        "revoked": False,
                    }],
                    "revoked_record_ids": [],
                }
            ),
            encoding="utf-8",
        )
        original = store_path.read_bytes()
        expected = TrustStore.load(store_path)
        store_path.write_text("{invalid", encoding="utf-8")

        loaded = TrustStore.from_bytes(store_path, original)

        self.assertEqual(expected.digest, loaded.digest)
        self.assertEqual(set(expected.keys), set(loaded.keys))
        with self.assertRaises(json.JSONDecodeError):
            TrustStore.load(store_path)

    def test_trust_store_rejects_symlinked_public_key(self) -> None:
        snapshot = self.root / "trust-symlink"
        snapshot.mkdir()
        target = snapshot / "public.pem"
        target.write_bytes((self.root / "evidence-authorizer.public.pem").read_bytes())
        link = snapshot / "public-link.pem"
        link.symlink_to(target.name)
        store_path = snapshot / "trust-store.json"
        store_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "keys": [{
                        "key_id": "symlink-key",
                        "roles": ["evidence-authorizer"],
                        "public_key_path": link.name,
                        "not_before": "2025-01-01T00:00:00Z",
                        "not_after": "2030-01-01T00:00:00Z",
                        "revoked": False,
                    }],
                    "revoked_record_ids": [],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(OSError):
            TrustStore.load(store_path)

    def test_all_source_and_runtime_names_resolve_with_honest_maturity(self) -> None:
        self.assertEqual(632, len(self.registry.by_runtime_name))
        self.assertEqual(632, self.registry.manifest["workspace_skill_count"])
        self.assertEqual("ALL_RUNTIME_SKILLS", self.registry.manifest["workspace_installation"])
        maturities = {record["maturity"] for record in self.registry.by_runtime_name.values()}
        self.assertEqual({"LOCAL_EXECUTED"}, maturities)
        self.assertEqual(632, sum(record["maturity"] == "LOCAL_EXECUTED" for record in self.registry.by_runtime_name.values()))
        for runtime_name, record in self.registry.by_runtime_name.items():
            self.assertEqual(record, self.registry.resolve(runtime_name))
            self.assertEqual(record, self.registry.resolve(record["source_name"]))
            workspace_skill = ROOT / record["workspace_path"]
            self.assertTrue(workspace_skill.is_file())
            self.assertEqual(record["workspace_sha256"], hashlib.sha256(workspace_skill.read_bytes()).hexdigest())

    def test_plan_enforces_assessment_validation_and_release_stages(self) -> None:
        record = self.registry.resolve("java-to-python-direction-pack")
        batches = [item["batch"] for stage in batch_plan(self.registry, record)["stages"] for item in stage["batches"]]
        self.assertLess(batches.index(2), batches.index(16))
        self.assertLess(batches.index(16), batches.index(41))

    def test_all_child_skills_have_unique_digest_bound_executable_contracts(self) -> None:
        contracts = ContractRegistry.load()
        self.assertEqual(587, len(contracts.by_skill))
        self.assertEqual(587, len(contracts.by_handler))
        for skill, contract in contracts.by_skill.items():
            entry = self.adapter_registry.by_skill[skill]
            if entry["handler_id"].startswith("precision-skill-v1:"):
                self.assertEqual(contract["handler_id"], entry["handler_id"])
            self.assertTrue(contract["source_sha256"].startswith("sha256:"))
            self.assertTrue(contract["workflow"])
            self.assertTrue(contract["validation_gates"])

    def test_all_generic_skills_have_unique_exact_entrypoints(self) -> None:
        implementations = ExactImplementationRegistry.load()
        self.assertEqual(536, len(implementations.by_handler))
        self.assertEqual(536, len(EXACT_HANDLERS))
        self.assertEqual(
            536,
            len({profile["handler_entrypoint"] for profile in implementations.by_handler.values()}),
        )
        self.assertFalse(
            any(
                entry["handler_id"].startswith(("domain-skill-v2:", "exact-skill-v3:"))
                for entry in self.adapter_registry.by_skill.values()
            )
        )
        self.assertEqual(
            536,
            len({profile["implementation_digest"] for profile in implementations.by_handler.values()}),
        )
        for profile in implementations.by_handler.values():
            self.assertEqual("precision-exact-program-v1", profile["program_version"])
            self.assertEqual(
                ["verify-inputs", "execute-algorithm", "execute-native", "evaluate-gates", "emit-artifact"],
                [step["op"] for step in profile["program"]],
            )
            self.assertTrue(set(profile["native_tools"]) <= (set(NATIVE_ADAPTERS) | set(EXTERNAL_NATIVE_ADAPTERS)))

    def test_all_orchestrators_have_unique_executable_dags(self) -> None:
        orchestrators = OrchestratorRegistry.load()
        self.assertEqual(45, len(orchestrators.by_handler))
        self.assertEqual(45, len(ORCHESTRATOR_HANDLERS))
        self.assertEqual(
            45,
            len({profile["handler_entrypoint"] for profile in orchestrators.by_handler.values()}),
        )

    def test_production_code_gate_is_ready_only_for_external_gate(self) -> None:
        result = build_production_code_gate()
        self.assertEqual("PASSED", result["status"])
        self.assertEqual("READY_FOR_EXTERNAL_GATE", result["decision"])
        self.assertFalse(result["production_operation_authorized"])
        self.assertEqual("NOT_CERTIFIED", result["production_certification"])
        self.assertTrue(all(value == "NOT_RUN" for value in result["external_boundaries"].values()))

    def test_assessment_with_real_signed_evidence_is_verified(self) -> None:
        result = self.evaluate(self.complete_request("repository-modernization-assessment"))
        self.assertEqual("VERIFIED", result["status"])
        self.assertEqual("SHADOW_ONLY", result["release_gate"]["decision"])
        self.assertEqual(2, len(result["evidence"]))

    def test_nonexistent_evidence_is_rejected(self) -> None:
        request = self.complete_request("repository-modernization-assessment")
        request["evidence"][0]["artifact_uri"] = (self.root / "does-not-exist.json").as_uri()
        result = self.evaluate(request)
        self.assertEqual("FAILED", result["status"])
        self.assertIn("EVIDENCE_CONTENT_UNVERIFIED", {item["code"] for item in result["unresolved"]})

    def test_digest_mismatch_is_rejected(self) -> None:
        request = self.complete_request("repository-modernization-assessment")
        request["evidence"][0]["digest"] = "sha256:" + "0" * 64
        result = self.evaluate(request)
        self.assertEqual("FAILED", result["status"])

    def test_unsigned_authorization_is_rejected(self) -> None:
        request = self.complete_request("repository-modernization-assessment")
        request["evidence"][0]["authorization"]["signature"] = "ZmFrZQ=="
        result = self.evaluate(request)
        self.assertEqual("FAILED", result["status"])
        self.assertIn("EVIDENCE_AUTHORIZATION_INVALID", {item["code"] for item in result["unresolved"]})

    def test_expired_authorization_is_rejected(self) -> None:
        request = self.complete_request("repository-modernization-assessment")
        authorization = request["evidence"][0]["authorization"]
        payload = dict(authorization["payload"])
        payload["issued_at"] = "2025-01-01T00:00:00Z"
        payload["expires_at"] = "2025-12-31T00:00:00Z"
        request["evidence"][0]["authorization"] = self.sign("evidence-authorizer", payload)
        result = self.evaluate(request)
        self.assertEqual("FAILED", result["status"])
        self.assertIn("EVIDENCE_AUTHORIZATION_INVALID", {item["code"] for item in result["unresolved"]})

    def test_revoked_authorization_record_is_rejected(self) -> None:
        request = self.complete_request("repository-modernization-assessment")
        record_id = request["evidence"][0]["authorization"]["payload"]["record_id"]
        payload = json.loads(self.trust_path.read_text(encoding="utf-8"))
        payload["revoked_record_ids"] = [record_id]
        revoked_path = self.root / "revoked-trust-store.json"
        revoked_path.write_text(json.dumps(payload), encoding="utf-8")
        result = evaluate(
            request,
            self.registry,
            evidence_roots=[self.root],
            trust_store=TrustStore.load(revoked_path),
            now=NOW,
        )
        self.assertEqual("FAILED", result["status"])
        self.assertIn("EVIDENCE_AUTHORIZATION_INVALID", {item["code"] for item in result["unresolved"]})

    def test_wrong_signing_role_is_rejected(self) -> None:
        request = self.complete_request("repository-modernization-assessment")
        payload = request["evidence"][0]["authorization"]["payload"]
        request["evidence"][0]["authorization"] = self.sign("release-approver", payload)
        self.assertEqual("FAILED", self.evaluate(request)["status"])

    def test_path_escape_and_remote_scheme_are_rejected(self) -> None:
        approved = self.root / "approved"
        approved.mkdir(exist_ok=True)
        outside = self.root / "outside.json"
        outside.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "escapes approved"):
            verify_content_reference(self.content_ref(outside), (approved.resolve(),))
        remote = {**self.content_ref(outside), "uri": "https://example.invalid/evidence.json"}
        with self.assertRaisesRegex(ValueError, "unsupported artifact URI scheme"):
            verify_content_reference(remote, (self.root.resolve(),))

    def test_self_verified_evidence_fails(self) -> None:
        request = self.complete_request("repository-modernization-assessment")
        request["evidence"][0]["verifier"] = request["evidence"][0]["executor"]
        result = self.evaluate(request)
        self.assertEqual("FAILED", result["status"])

    def test_missing_transform_evidence_is_conditionally_verified(self) -> None:
        request = self.base_request("java-to-python-direction-pack", "transform")
        result = self.evaluate(request)
        self.assertEqual("CONDITIONALLY_VERIFIED", result["status"])
        self.assertEqual("BLOCK", result["release_gate"]["decision"])

    def test_exact_skill_with_complete_signed_evidence_is_verified(self) -> None:
        result = self.evaluate(self.complete_request("java-to-go-direction-pack", "transform"))
        self.assertEqual("VERIFIED", result["status"])

    def test_signed_scoped_approval_is_required_for_high_risk(self) -> None:
        request = self.complete_request("repository-modernization-assessment")
        request["policy"]["risk_level"] = "high"
        # Policy changes invalidate evidence authorizations, so regenerate them.
        request["evidence"] = [self.passed(request, kind) for kind in ("input-provenance", "assessment-schema")]
        self.assertEqual("REQUIRES_HUMAN_REVIEW", self.evaluate(request)["status"])
        request["approvals"] = [
            self.sign(
                "release-approver",
                {
                    "record_type": "HUMAN_APPROVAL",
                    "record_id": "approval-high-risk",
                    "request_id": request["request_id"],
                    "scope": self.registry.resolve(request["skill"])["name"],
                    "decision": "APPROVED",
                    "approver": "release-owner",
                    "request_digest": request_binding_digest(request),
                    "issued_at": "2025-12-31T00:00:00Z",
                    "expires_at": "2026-12-31T00:00:00Z",
                },
            )
        ]
        self.assertEqual("VERIFIED", self.evaluate(request)["status"])

    def test_approval_separation_of_duties_is_enforced(self) -> None:
        request = self.complete_request("repository-modernization-assessment")
        request["policy"]["risk_level"] = "high"
        request["evidence"] = [self.passed(request, kind) for kind in ("input-provenance", "assessment-schema")]
        colliding_actor = request["evidence"][0]["executor"]
        request["approvals"] = [
            self.sign(
                "release-approver",
                {
                    "record_type": "HUMAN_APPROVAL",
                    "record_id": "approval-sod-conflict",
                    "request_id": request["request_id"],
                    "scope": self.registry.resolve(request["skill"])["name"],
                    "decision": "APPROVED",
                    "approver": colliding_actor,
                    "request_digest": request_binding_digest(request),
                    "issued_at": "2025-12-31T00:00:00Z",
                    "expires_at": "2026-12-31T00:00:00Z",
                },
            )
        ]
        result = self.evaluate(request)
        self.assertEqual("FAILED", result["status"])
        self.assertIn("APPROVAL_SOD_VIOLATION", {item["code"] for item in result["unresolved"]})

    def test_requester_cannot_self_approve_high_risk_release(self) -> None:
        request = self.complete_request("repository-modernization-assessment")
        request["policy"]["risk_level"] = "high"
        request["evidence"] = [self.passed(request, kind) for kind in ("input-provenance", "assessment-schema")]
        request["approvals"] = [
            self.sign(
                "release-approver",
                {
                    "record_type": "HUMAN_APPROVAL",
                    "record_id": "approval-requester-conflict",
                    "request_id": request["request_id"],
                    "scope": self.registry.resolve(request["skill"])["name"],
                    "decision": "APPROVED",
                    "approver": request["policy"]["request_actor"],
                    "request_digest": request_binding_digest(request),
                    "issued_at": "2025-12-31T00:00:00Z",
                    "expires_at": "2026-12-31T00:00:00Z",
                },
            )
        ]
        result = self.evaluate(request)
        self.assertEqual("FAILED", result["status"])
        self.assertIn("APPROVAL_SOD_VIOLATION", {item["code"] for item in result["unresolved"]})

    def test_caller_boolean_cannot_claim_proof(self) -> None:
        request = self.complete_request("rule-proof-certificate", "validate")
        request["claimed_status"] = "PROVED"
        request["evidence"].append({"kind": "machine-proof", "state": "PASS", "trusted_kernel": True})
        result = self.evaluate(request)
        self.assertEqual("FAILED", result["status"])

    def test_signed_bounded_machine_proof_can_reach_proved(self) -> None:
        request = self.complete_request("rule-proof-certificate", "validate")
        request["claimed_status"] = "PROVED"
        # claimed_status is part of the request binding, so re-authorize every item.
        request["evidence"] = [
            self.passed(request, kind)
            for kind in ("input-provenance", "source-build", "target-build", "negative-tests", "source-target-differential", "artifact-provenance")
        ]
        proof = self.passed(request, "machine-proof")
        proof["proof_record"] = self.sign(
            "proof-verifier",
            {
                "record_type": "MACHINE_PROOF",
                "record_id": "proof-bounded-core",
                "request_id": request["request_id"],
                "skill": request["skill"],
                "artifact_digest": proof["digest"],
                "request_digest": request_binding_digest(request),
                "result": "PROVED",
                "proof_scope": "bounded-core",
                "solver": "lean",
                "solver_version": "4.19.0",
                "theory": "typed-pure-function-v1",
                "options": {"no_sorry": True},
                "bounds": {"module": "bounded-core"},
                "assumptions_digest": "sha256:" + "c" * 64,
                "input_digest": self.asset()["digest"],
                "issued_at": "2025-12-31T00:00:00Z",
                "expires_at": "2026-12-31T00:00:00Z",
            },
        )
        request["evidence"].append(proof)
        self.assertEqual("PROVED", self.evaluate(request)["status"])

    def test_result_bundle_preserves_verified_input_lineage(self) -> None:
        result = self.evaluate(self.complete_request("repository-modernization-assessment"))
        output = self.root / "bundle-input-lineage"
        output.mkdir(exist_ok=True)
        write_bundle(result, output)
        manifest = json.loads((output / "evidence-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(self.asset()["digest"], manifest["inputs"][0]["digest"])

    def test_repository_assessment_adapter_executes_read_only_inventory(self) -> None:
        request = self.base_request("repository-modernization-assessment")
        request["inputs"]["parameters"] = {"workspace_path": str(ROOT / "scripts" / "precision_migration")}
        output = self.root / "adapter-assessment"
        result = execute(
            request,
            output,
            evidence_roots=[ROOT, self.root],
            trust_store=self.trust_store,
            adapter_registry=self.adapter_registry,
            skill_registry=self.registry,
        )
        self.assertEqual("LOCAL_EXECUTED", result["execution_state"])
        report = json.loads((output / "repository-assessment.json").read_text(encoding="utf-8"))
        self.assertGreater(report["file_count"], 0)

    def test_exact_batch29_route_adapter_transforms_builds_and_replays_behavior(self) -> None:
        request = self.base_request("java-to-python-direction-pack", "validate")
        source = ROOT / "engines" / "polyglot-route-engine" / "fixtures" / "java" / "Pricing.java"
        cases = ROOT / "engines" / "polyglot-route-engine" / "fixtures" / "behavior-cases.json"
        request["inputs"] = {
            "assets": [
                {**self.content_ref(source), "sensitivity": "internal", "version": "fixture-v1"},
                {**self.content_ref(cases), "sensitivity": "internal", "version": "fixture-v1"},
            ],
            "parameters": {"function_name": "calculate", "source_asset_index": 0, "cases_asset_index": 1},
        }
        output = self.root / "adapter-route"
        result = execute(
            request,
            output,
            evidence_roots=[ROOT, self.root],
            adapter_registry=self.adapter_registry,
            skill_registry=self.registry,
        )
        self.assertEqual("LOCAL_EXECUTED", result["execution_state"])
        report = json.loads((output / "route-execution.json").read_text())
        self.assertEqual(0, report["engine_exit_code"])
        self.assertEqual(0, report["route_gate_exit_code"])
        self.assertTrue((output / "migration" / "migrated.py").is_file())

    def test_repository_content_cannot_select_a_command(self) -> None:
        request = self.base_request("business-rule-extractor", "validate")
        request["inputs"]["parameters"] = {"command": "touch should-not-exist"}
        output = self.root / "adapter-command-injection"
        result = execute(
            request,
            output,
            evidence_roots=[self.root],
            adapter_registry=self.adapter_registry,
            skill_registry=self.registry,
        )
        self.assertEqual("LOCAL_EXECUTED", result["execution_state"])
        artifact_name = ExactImplementationRegistry.load().by_skill["pm-b05-business-rule-extractor"]["artifact_name"]
        domain_result = json.loads((output / artifact_name).read_text())
        self.assertEqual("EXACT_CONTRACT_LOCAL", domain_result["execution_scope"])
        self.assertEqual("NOT_RUN", domain_result["native_readiness"]["execution"])
        self.assertFalse((ROOT / "should-not-exist").exists())

    def test_batch_orchestrator_executes_identity_bound_dag(self) -> None:
        request = self.base_request("batch-01-competition-positioning")
        request["inputs"]["parameters"] = {}
        output = self.root / "batch-orchestrator"
        result = execute(
            request,
            output,
            evidence_roots=[self.root],
            adapter_registry=self.adapter_registry,
            skill_registry=self.registry,
        )
        self.assertEqual("LOCAL_EXECUTED", result["execution_state"])
        dag = json.loads((output / "orchestrator-execution.json").read_text())
        self.assertEqual("RUNNABLE", dag["state"])
        self.assertEqual(6, len(dag["topological_order"]))
        self.assertEqual(1, len(dag["ready_nodes"]))
        self.assertEqual("NOT_RUN", dag["production_execution"])

    def test_all_orchestrators_preflight_every_allowlisted_child(self) -> None:
        orchestrators = OrchestratorRegistry.load()
        for index, (handler_id, profile) in enumerate(sorted(orchestrators.by_handler.items())):
            request = self.base_request(profile["skill"])
            request["inputs"] = {"assets": [], "parameters": {"orchestration_action": "preflight"}}
            output = self.root / "orchestrator-preflight" / f"{index:02d}"
            result = execute(
                request,
                output,
                evidence_roots=[self.root],
                adapter_registry=self.adapter_registry,
                skill_registry=self.registry,
            )
            self.assertEqual("LOCAL_EXECUTED", result["execution_state"], handler_id)
            report = json.loads((output / "orchestrator-execution.json").read_text())
            self.assertEqual(len(profile["nodes"]), len(report["preflight"]))
            self.assertTrue(all(item["state"] == "READY" for item in report["preflight"]))

    def test_batch_orchestrator_executes_children_and_derives_receipts(self) -> None:
        profile = OrchestratorRegistry.load().by_handler["orchestrator-dag-v2:batch-01-competition-positioning"]
        selected = profile["nodes"][:2]
        fixture = self.root / "orchestrator-decision.json"
        fixture.write_text(
            json.dumps(
                {
                    "candidates": [
                        {"id": "build", "metrics": {"quality": 0.9, "cost": 0.6}},
                        {"id": "buy", "metrics": {"quality": 0.7, "cost": 0.9}},
                    ],
                    "criteria": {"quality": 2, "cost": 1},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        node_requests = {}
        for node in selected:
            child = self.base_request(node, "assess")
            child["inputs"]["assets"] = [
                {**self.content_ref(fixture), "sensitivity": "internal", "version": "orchestrator-fixture-v1"}
            ]
            node_requests[node] = child
        request = self.base_request(profile["skill"])
        request["inputs"] = {
            "assets": [],
            "parameters": {
                "orchestration_action": "execute",
                "selected_nodes": selected,
                "node_requests": node_requests,
            },
        }
        output = self.root / "orchestrator-child-execution"
        result = execute(
            request,
            output,
            evidence_roots=[self.root],
            adapter_registry=self.adapter_registry,
            skill_registry=self.registry,
        )
        self.assertEqual("LOCAL_EXECUTED", result["execution_state"])
        report = json.loads((output / "orchestrator-execution.json").read_text())
        self.assertEqual("COMPLETE", report["state"])
        self.assertEqual(["SUCCEEDED", "SUCCEEDED"], [item["state"] for item in report["node_runs"]])
        self.assertTrue(all(item["result_digest"].startswith("sha256:") for item in report["node_runs"]))

    def test_batch_orchestrator_resumes_only_content_verified_child_receipts(self) -> None:
        profile = OrchestratorRegistry.load().by_handler["orchestrator-dag-v2:batch-01-competition-positioning"]
        selected = profile["nodes"][:1]
        fixture = self.root / "orchestrator-checkpoint-decision.json"
        fixture.write_text(
            json.dumps(
                {
                    "candidates": [{"id": "build", "metrics": {"quality": 0.9}}],
                    "criteria": {"quality": 1},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        child = self.base_request(selected[0], "assess")
        child["inputs"]["assets"] = [
            {**self.content_ref(fixture), "sensitivity": "internal", "version": "checkpoint-fixture-v1"}
        ]
        first = self.base_request(profile["skill"])
        first["inputs"] = {
            "assets": [],
            "parameters": {
                "orchestration_action": "execute",
                "selected_nodes": selected,
                "node_requests": {selected[0]: child},
            },
        }
        first_output = self.root / "orchestrator-checkpoint-first"
        first_result = execute(
            first,
            first_output,
            evidence_roots=[self.root],
            adapter_registry=self.adapter_registry,
            skill_registry=self.registry,
        )
        self.assertEqual("LOCAL_EXECUTED", first_result["execution_state"])
        checkpoint = first_output / "orchestrator-execution.json"
        resumed = self.base_request(profile["skill"])
        resumed["inputs"] = {
            "assets": [
                {**self.content_ref(checkpoint), "sensitivity": "internal", "version": "orchestrator-checkpoint-v1"}
            ],
            "parameters": {
                "orchestration_action": "execute",
                "selected_nodes": selected,
                "node_requests": {},
                "checkpoint_asset_index": 0,
            },
        }
        resumed_output = self.root / "orchestrator-checkpoint-resumed"
        resumed_result = execute(
            resumed,
            resumed_output,
            evidence_roots=[self.root],
            adapter_registry=self.adapter_registry,
            skill_registry=self.registry,
        )
        self.assertEqual("LOCAL_EXECUTED", resumed_result["execution_state"])
        report = json.loads((resumed_output / "orchestrator-execution.json").read_text())
        self.assertEqual("COMPLETE", report["state"])
        self.assertEqual("REUSED_CHECKPOINT", report["node_runs"][0]["state"])

    def test_exact_python_adapter_runs_allowlisted_native_compiler(self) -> None:
        source = self.root / "native-fixture.py"
        source.write_text("def add(left: int, right: int) -> int:\n    return left + right\n", encoding="utf-8")
        request = self.base_request("python-parser-adapter", "transform")
        request["inputs"] = {
            "assets": [{**self.content_ref(source), "sensitivity": "internal", "version": "native-fixture-v1"}],
            "parameters": {"execute_native": True, "native_assets": {"python3": 0}},
        }
        output = self.root / "native-python-adapter"
        result = execute(
            request,
            output,
            evidence_roots=[self.root],
            adapter_registry=self.adapter_registry,
            skill_registry=self.registry,
        )
        self.assertEqual("LOCAL_EXECUTED", result["execution_state"])
        artifact_name = ExactImplementationRegistry.load().by_skill["pm-b14-python-parser-adapter"]["artifact_name"]
        artifact = json.loads((output / artifact_name).read_text())
        self.assertEqual("PASSED", artifact["native_execution"]["state"])
        self.assertEqual("python3", artifact["native_execution"]["runs"][0]["tool"])

    def test_native_command_injection_is_not_an_allowed_parameter(self) -> None:
        source = self.root / "native-injection.py"
        source.write_text("VALUE = 1\n", encoding="utf-8")
        request = self.base_request("python-parser-adapter", "transform")
        request["inputs"] = {
            "assets": [{**self.content_ref(source), "sensitivity": "internal", "version": "native-fixture-v1"}],
            "parameters": {
                "execute_native": True,
                "native_assets": {"python3": 0},
                "native_command": ["touch", str(ROOT / "forbidden")],
            },
        }
        output = self.root / "native-command-injection"
        result = execute(
            request,
            output,
            evidence_roots=[self.root],
            adapter_registry=self.adapter_registry,
            skill_registry=self.registry,
        )
        self.assertEqual("LOCAL_EXECUTED", result["execution_state"])
        self.assertFalse((ROOT / "forbidden").exists())

    def test_database_native_adapter_fails_closed_into_typed_external_gate(self) -> None:
        implementations = ExactImplementationRegistry.load()
        profile = next(item for item in implementations.by_handler.values() if item["native_tools"] == ["sqlplus"])
        source = self.root / "native-oracle.sql"
        source.write_text("SELECT 1 FROM dual;\n", encoding="utf-8")
        request = self.base_request(profile["skill"], profile["supported_modes"][0])
        request["inputs"] = {
            "assets": [{**self.content_ref(source), "sensitivity": "internal", "version": "native-sql-v1"}],
            "parameters": {"execute_native": True, "native_assets": {"sqlplus": 0}},
        }
        output = self.root / "native-database-external-gate"
        result = execute(
            request,
            output,
            evidence_roots=[self.root],
            adapter_registry=self.adapter_registry,
            skill_registry=self.registry,
        )
        self.assertEqual("FAILED", result["execution_state"])
        artifact = json.loads((output / profile["artifact_name"]).read_text())
        run = artifact["native_execution"]["runs"][0]
        self.assertEqual("REQUIRES_EXTERNAL_GATE", run["state"])
        self.assertEqual("DISPOSABLE_DATABASE", run["gate"])

    def test_database_native_adapter_accepts_only_independently_signed_external_receipt(self) -> None:
        implementations = ExactImplementationRegistry.load()
        profile = next(item for item in implementations.by_handler.values() if item["native_tools"] == ["sqlplus"])
        source = self.root / "native-oracle-receipt.sql"
        source.write_text("SELECT 1 FROM dual;\n", encoding="utf-8")
        request = self.base_request(profile["skill"], profile["supported_modes"][0])
        request["inputs"] = {
            "assets": [{**self.content_ref(source), "sensitivity": "internal", "version": "native-sql-v1"}],
            "parameters": {"execute_native": True, "native_assets": {"sqlplus": 0}},
        }
        request["evidence"] = [self.passed(request, "native-tool:sqlplus")]
        output = self.root / "native-database-signed-receipt"
        result = execute(
            request,
            output,
            evidence_roots=[self.root],
            trust_store=self.trust_store,
            adapter_registry=self.adapter_registry,
            skill_registry=self.registry,
        )
        self.assertEqual("LOCAL_EXECUTED", result["execution_state"])
        artifact = json.loads((output / profile["artifact_name"]).read_text())
        run = artifact["native_execution"]["runs"][0]
        self.assertEqual("EXTERNAL_VERIFIED", run["state"])
        self.assertNotEqual(run["executor"], run["verifier"])

    def test_b41_capabilities_use_ten_independent_handlers(self) -> None:
        entries = [entry for entry in self.adapter_registry.by_skill.values() if entry.get("batch") == 41 and entry.get("kind") == "skill"]
        self.assertEqual(10, len(entries))
        self.assertEqual(10, len({entry["handler_id"] for entry in entries}))
        self.assertEqual(10, len({entry["handler_entrypoint"] for entry in entries}))

    def test_b41_ed25519_certificate_is_signed_and_immediately_verified(self) -> None:
        request = self.base_request("certificate-signing", "validate")
        request["inputs"]["parameters"] = {
            "signing_key_path": str(self.keys["certificate-signer"]),
            "key_id": "test-certificate-signer",
            "payload_asset_index": 0,
            "issued_at": "2025-12-31T00:00:00Z",
            "expires_at": "2026-12-31T00:00:00Z",
        }
        output = self.root / "b41-signing"
        result = execute(
            request,
            output,
            evidence_roots=[self.root],
            trust_store=self.trust_store,
            adapter_registry=self.adapter_registry,
            skill_registry=self.registry,
        )
        self.assertEqual("LOCAL_EXECUTED", result["execution_state"])
        certificate = json.loads((output / "signed-certificate.json").read_text())
        self.assertEqual("PASSED", certificate["verification"])
        self.assertEqual("NOT_RUN", certificate["hsm_execution"])

    def test_b41_pkcs11_hsm_backend_fails_closed_without_pin(self) -> None:
        request = self.base_request("certificate-signing", "validate")
        request["inputs"]["parameters"] = {
            "signing_backend": "pkcs11-openssl-ed25519",
            "hsm_provider": "pkcs11",
            "hsm_key_uri": "pkcs11:token=precision;object=release-key;type=private",
            "key_id": "hsm-release-key",
            "payload_asset_index": 0,
            "issued_at": "2025-12-31T00:00:00Z",
            "expires_at": "2026-12-31T00:00:00Z",
        }
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "ELMOS_PRECISION_HSM_PIN"):
            execute(
                request,
                self.root / "b41-hsm-missing-pin",
                evidence_roots=[self.root],
                trust_store=self.trust_store,
                adapter_registry=self.adapter_registry,
                skill_registry=self.registry,
            )

    def test_tenant_job_lifecycle_retry_and_audit_are_durable(self) -> None:
        store = JobStore(self.root / "jobs-lifecycle", max_active=2, max_jobs=10, max_bytes=10_000_000)
        request = self.base_request("repository-modernization-assessment")
        request["inputs"]["parameters"] = {"workspace_path": str(ROOT / "scripts" / "precision_migration")}
        submitted = store.submit(request, tenant_id="tenant-a", actor="actor-a")
        self.assertEqual("QUEUED", submitted["status"])
        stored_request = json.loads(
            (store.job_root("tenant-a", submitted["job_id"]) / "request.json").read_text(encoding="utf-8")
        )
        self.assertEqual("actor-a", stored_request["policy"]["request_actor"])
        self.assertEqual("requester-a", request["policy"]["request_actor"])
        completed = store.run(
            "tenant-a",
            submitted["job_id"],
            evidence_roots=[ROOT, self.root],
            trust_store=self.trust_store,
        )
        self.assertEqual("SUCCEEDED", completed["status"])
        retried = store.retry("tenant-a", "actor-a", submitted["job_id"])
        self.assertEqual(submitted["job_id"], retried["retry_of"])
        self.assertEqual("QUEUED", retried["status"])
        audit_lines = (store.tenant_root("tenant-a") / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertGreaterEqual(len(audit_lines), 4)
        previous = "sha256:" + "0" * 64
        for line in audit_lines:
            entry = json.loads(line)
            self.assertEqual(previous, entry["previous_hash"])
            previous = entry["entry_hash"]

    def test_job_tenant_isolation_quota_and_cooperative_cancel(self) -> None:
        store = JobStore(self.root / "jobs-isolation", max_active=1, max_jobs=10, max_bytes=10_000_000)
        request = self.base_request("java-to-go-direction-pack", "transform")
        submitted = store.submit(request, tenant_id="tenant-one", actor="actor-one")
        with self.assertRaisesRegex(JobError, "active-job quota"):
            store.submit(request, tenant_id="tenant-one", actor="actor-one")
        with self.assertRaisesRegex(JobError, "job not found"):
            store.read("tenant-two", submitted["job_id"])
        cancelling = store.cancel("tenant-one", "actor-one", submitted["job_id"])
        self.assertEqual("CANCEL_REQUESTED", cancelling["status"])
        cancelled = store.run(
            "tenant-one",
            submitted["job_id"],
            evidence_roots=[self.root],
            trust_store=self.trust_store,
        )
        self.assertEqual("CANCELLED", cancelled["status"])

    def test_job_cancel_wins_when_requested_before_worker_finalization(self) -> None:
        store = JobStore(self.root / "jobs-cancel-race", max_active=1, max_jobs=10, max_bytes=10_000_000)
        request = self.base_request("repository-modernization-assessment")
        submitted = store.submit(request, tenant_id="tenant-race", actor="actor-race")
        entered = threading.Event()
        release = threading.Event()
        outcome: dict[str, object] = {}

        def delayed_execute(*_args: object, **_kwargs: object) -> dict[str, object]:
            entered.set()
            self.assertTrue(release.wait(timeout=5))
            return {"execution_state": "LOCAL_EXECUTED", "artifacts": [], "exit_code": 0}

        def run_worker() -> None:
            outcome.update(
                store.run(
                    "tenant-race",
                    submitted["job_id"],
                    evidence_roots=[self.root],
                    trust_store=self.trust_store,
                )
            )

        with mock.patch("scripts.precision_migration.jobs.execute", side_effect=delayed_execute):
            worker = threading.Thread(target=run_worker, daemon=True)
            worker.start()
            self.assertTrue(entered.wait(timeout=5))
            cancelling = store.cancel("tenant-race", "actor-race", submitted["job_id"])
            self.assertEqual("CANCEL_REQUESTED", cancelling["status"])
            release.set()
            worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertEqual("CANCELLED", outcome["status"])
        self.assertTrue(outcome["cancel_requested"])

    def test_job_worker_spawn_failure_is_persisted_as_terminal(self) -> None:
        store = JobStore(self.root / "jobs-spawn-failure", max_active=1, max_jobs=10, max_bytes=10_000_000)
        request = self.base_request("repository-modernization-assessment")
        submitted = store.submit(request, tenant_id="tenant-spawn", actor="actor-spawn")
        with mock.patch("scripts.precision_migration.jobs.subprocess.Popen", side_effect=OSError("spawn denied")):
            with self.assertRaisesRegex(JobError, "worker start failed"):
                store.start_worker(submitted, evidence_roots=[self.root], trust_store=self.trust_store)
        failed = store.read("tenant-spawn", submitted["job_id"])
        self.assertEqual("FAILED", failed["status"])
        self.assertEqual("WORKER_START_FAILED", failed["result"]["error"])
        self.assertEqual(0, store.list("tenant-spawn")["quota"]["active"])

    def test_job_submission_rejects_weakened_or_unknown_request_fields(self) -> None:
        store = JobStore(self.root / "jobs-request-validation", max_active=2, max_jobs=10, max_bytes=10_000_000)
        weakened = self.base_request("repository-modernization-assessment")
        weakened["policy"]["allow_test_weakening"] = True
        with self.assertRaisesRegex(JobError, "allow_test_weakening"):
            store.submit(weakened, tenant_id="tenant-validation", actor="actor-validation")
        unknown = self.base_request("repository-modernization-assessment")
        unknown["command"] = "touch must-not-run"
        with self.assertRaisesRegex(JobError, "unsupported fields"):
            store.submit(unknown, tenant_id="tenant-validation", actor="actor-validation")
        self.assertEqual(0, store.list("tenant-validation")["quota"]["retained"])

    def test_job_audit_tampering_is_detected_before_append(self) -> None:
        store = JobStore(self.root / "jobs-audit-tamper", max_active=2, max_jobs=10, max_bytes=10_000_000)
        request = self.base_request("java-to-go-direction-pack", "transform")
        store.submit(request, tenant_id="tenant-audit", actor="actor-audit")
        audit_path = store.tenant_root("tenant-audit") / "audit.jsonl"
        entries = audit_path.read_text(encoding="utf-8").splitlines()
        tampered = json.loads(entries[0])
        tampered["actor"] = "attacker"
        audit_path.write_text(json.dumps(tampered, sort_keys=True) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(JobError, "entry hash mismatch"):
            store.audit("tenant-audit", {"event": "MUST_NOT_APPEND", "actor": "actor-audit"})
        with self.assertRaisesRegex(JobError, "entry hash mismatch"):
            store.list("tenant-audit")
        self.assertEqual(1, len(audit_path.read_text(encoding="utf-8").splitlines()))

    def test_job_storage_permissions_and_gc_are_recoverable(self) -> None:
        store = JobStore(self.root / "jobs-gc", max_active=2, max_jobs=10, max_bytes=10_000_000)
        request = self.base_request("repository-modernization-assessment")
        request["inputs"]["parameters"] = {"workspace_path": str(ROOT / "scripts" / "precision_migration")}
        submitted = store.submit(request, tenant_id="tenant-gc", actor="actor-gc")
        completed = store.run(
            "tenant-gc",
            submitted["job_id"],
            evidence_roots=[ROOT, self.root],
            trust_store=self.trust_store,
        )
        self.assertEqual("SUCCEEDED", completed["status"])
        tenant_root = store.tenant_root("tenant-gc")
        self.assertEqual(0o700, tenant_root.stat().st_mode & 0o777)
        self.assertEqual(0o600, (tenant_root / "audit.jsonl").stat().st_mode & 0o777)
        old = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
        os.utime(store.job_root("tenant-gc", submitted["job_id"]), (old, old))
        archived = store.gc("tenant-gc", "actor-gc", older_than_seconds=3600)
        self.assertEqual([submitted["job_id"]], archived["archived"])
        self.assertTrue(Path(archived["recoverable_root"]).is_dir())
        with self.assertRaisesRegex(JobError, "job not found"):
            store.read("tenant-gc", submitted["job_id"])

    def gate_request(self) -> dict[str, object]:
        installed = self.registry.manifest
        request: dict[str, object] = {
            "schema_version": 1,
            "package_identity": {
                "source_package_manifest_sha256": installed["source_package_manifest_sha256"],
                "source_tree_sha256": installed["source_tree_sha256"],
            },
            "local_checks": {name: {"state": "PASSED", "evidence_refs": []} for name in LOCAL_CHECKS},
            "external_checks": {name: {"state": "NOT_RUN", "evidence_refs": []} for name in EXTERNAL_CHECKS},
        }
        binding = gate_binding_digest(request)
        for name in LOCAL_CHECKS:
            artifact = self.root / f"gate-{name}.json"
            artifact.write_text(json.dumps({"check": name, "state": "PASSED"}) + "\n", encoding="utf-8")
            reference = self.content_ref(artifact)
            reference["authorization"] = self.sign(
                "gate-evidence-authorizer",
                {
                    "record_type": "GATE_EVIDENCE_AUTHORIZATION",
                    "record_id": f"gate-auth-{name}",
                    "gate_request_digest": binding,
                    "check_group": "local_checks",
                    "check_name": name,
                    "artifact_digest": reference["digest"],
                    "issued_at": "2025-12-31T00:00:00Z",
                    "expires_at": "2026-12-31T00:00:00Z",
                },
            )
            request["local_checks"][name]["evidence_refs"] = [reference]
        return request

    def test_repository_gate_requires_real_signed_evidence(self) -> None:
        result = evaluate_gate(
            self.gate_request(),
            installed=self.registry.manifest,
            evidence_roots=[self.root],
            trust_store=self.trust_store,
        )
        self.assertEqual("READY_FOR_EXTERNAL_GATE", result["decision"])
        self.assertTrue(result["local_ready"])
        self.assertFalse(result["external_checks_complete"])
        self.assertEqual("NOT_CERTIFIED", result["production_certification"])

    def test_repository_gate_rejects_nonexistent_evidence(self) -> None:
        request = self.gate_request()
        request["local_checks"][LOCAL_CHECKS[0]]["evidence_refs"][0]["uri"] = (self.root / "missing-gate.json").as_uri()
        result = evaluate_gate(
            request,
            installed=self.registry.manifest,
            evidence_roots=[self.root],
            trust_store=self.trust_store,
        )
        self.assertEqual("REJECTED", result["decision"])
        self.assertFalse(result["local_ready"])


if __name__ == "__main__":
    unittest.main()

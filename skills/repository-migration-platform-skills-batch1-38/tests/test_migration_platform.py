from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = PACKAGE_ROOT / "scripts" / "migration_platform.py"
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("migration_platform", RUNTIME_PATH)
assert SPEC and SPEC.loader
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)
import domain_executors
import domain_handlers
import production_closure
import trusted_adapters


class MigrationPlatformRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.workspace = self.root / "workspace"
        self.source.mkdir()
        (self.source / "pom.xml").write_text("<project/>\n", encoding="utf-8")
        (self.source / "Main.java").write_text("final class Main {}\n", encoding="utf-8")
        (self.source / "MainTest.java").write_text("final class MainTest {}\n", encoding="utf-8")
        (self.source / "openapi.yaml").write_text("openapi: 3.1.0\n", encoding="utf-8")
        self.actor_directory = self.root / "actors"
        self.actor_directory.mkdir()
        self.actor_keys: dict[str, Path] = {}
        actor_roles = {
            "executor-dev": ["executor"],
            "executor-holdout": ["holdout-executor"],
            "executor-production": ["production-executor"],
            "oracle-owner": ["oracle-owner"],
            "verifier-dev": ["verifier"],
            "verifier-holdout": ["holdout-verifier"],
            "verifier-production": ["production-verifier"],
            "adapter-admin": ["adapter-admin"],
            "approver": ["approver", "production-approver"],
            "data-owner": ["data-owner"],
            "holdout-custodian": ["holdout-custodian"],
            "transformation-author": ["transformation-author"],
            "operations-owner": ["operations-owner"],
            "independent-certifier": ["independent-certifier"],
            "external-trust-approver": ["external-trust-approver"],
        }
        organizations = {
            "executor-dev": ("development-org", "implementation-provider"),
            "executor-holdout": ("holdout-executor-org", "holdout-lab"),
            "executor-production": ("production-executor-org", "operations"),
            "oracle-owner": ("oracle-org", "oracle-authority"),
            "verifier-dev": ("development-verifier-org", "independent-verifier"),
            "verifier-holdout": ("holdout-verifier-org", "independent-verifier"),
            "verifier-production": ("production-verifier-org", "independent-verifier"),
            "adapter-admin": ("platform-admin-org", "operations"),
            "approver": ("customer-approval-org", "customer"),
            "data-owner": ("customer-data-org", "customer"),
            "holdout-custodian": ("holdout-custodian-org", "customer"),
            "transformation-author": ("implementation-author-org", "implementation-provider"),
            "operations-owner": ("production-operations-org", "operations"),
            "independent-certifier": ("local-assurance-org", "independent-verifier"),
            "external-trust-approver": ("customer-governance-org", "customer"),
        }
        actors = []
        for actor_id, roles in actor_roles.items():
            private_key = self.actor_directory / f"{actor_id}.private.pem"
            public_key = self.actor_directory / f"{actor_id}.public.pem"
            subprocess.run(
                ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
                check=True, capture_output=True,
            )
            self.actor_keys[actor_id] = private_key
            actors.append({
                "actor_id": actor_id,
                "key_id": f"key-{actor_id}",
                "roles": roles,
                "public_key_path": public_key.name,
                "not_before": "2020-01-01T00:00:00Z",
                "not_after": "2099-01-01T00:00:00Z",
                "revoked": False,
                "organization_id": organizations[actor_id][0],
                "authority_class": organizations[actor_id][1],
            })
        self.trust_store = self.actor_directory / "trust-store.json"
        self.trust_store.write_text(json.dumps({
            "schema_version": "2.0", "store_id": "workspace-test-actors", "purpose": "workspace-actors",
            "actors": actors,
            "revoked_record_ids": [],
        }), encoding="utf-8")
        os.environ["SOURCE_DATE_EPOCH"] = "1700000000"

    def tearDown(self) -> None:
        os.environ.pop("SOURCE_DATE_EPOCH", None)
        self.temporary.cleanup()

    def prepare(self, batch: int = 1) -> dict:
        return runtime.prepare_batch(
            batch, self.source, self.workspace, "migrate safely", actor_trust_store=self.trust_store,
        )

    def adapter_registry(self) -> Path:
        executable = Path("/bin/echo").resolve(strict=True)
        executable_bytes = trusted_adapters.read_regular(executable, trusted_adapters.MAX_FILE_BYTES, "fixture adapter")
        source_fingerprint = runtime.state_store(self.workspace).metadata()["source_fingerprint"]
        adapters = [{
            "adapter_id": "fixture-provider", "capability": "provider-probe",
            "executable": str(executable), "executable_sha256": trusted_adapters.digest_bytes(executable_bytes),
            "version": "fixture-1.0", "environment_allowlist": [],
            "operations": [{
                "name": "inspect", "argv": ["provider-probe"],
                "parameters": [{"name": "target", "flag": "--target", "type": "identifier", "required": True}],
                "timeout_seconds": 10, "effect_class": "read-only", "compensation_operation": None,
            }, {
                "name": "apply", "argv": ["provider-apply"],
                "parameters": [{"name": "target", "flag": "--target", "type": "identifier", "required": True}],
                "timeout_seconds": 10, "effect_class": "reversible", "compensation_operation": "undo",
            }, {
                "name": "undo", "argv": ["provider-undo"],
                "parameters": [{"name": "target", "flag": "--target", "type": "identifier", "required": True}],
                "timeout_seconds": 10, "effect_class": "approval-required", "compensation_operation": None,
            }],
        }]
        envelope = self.sign("adapter-admin", {
            "schema_version": "1.0", "registry_id": "fixture-registry",
            "source_fingerprint": source_fingerprint, "adapters": adapters,
        }, suffix="adapter-registry")
        path = self.root / "adapter-registry.json"
        path.write_text(json.dumps(envelope), encoding="utf-8")
        return path

    def sign(self, actor_id: str, bindings: dict, *, suffix: str) -> dict:
        payload = {
            "actor_id": actor_id,
            "record_id": f"record-{actor_id}-{suffix}",
            "issued_at": "2020-01-01T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
            **bindings,
        }
        payload_path = self.root / f"signed-payload-{actor_id}-{suffix}.json"
        signature_path = self.root / f"signed-payload-{actor_id}-{suffix}.sig"
        payload_path.write_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        subprocess.run(
            [
                "openssl", "pkeyutl", "-sign", "-inkey", str(self.actor_keys[actor_id]),
                "-rawin", "-in", str(payload_path), "-out", str(signature_path),
            ],
            check=True, capture_output=True,
        )
        return {
            "algorithm": "ed25519",
            "key_id": f"key-{actor_id}",
            "payload": payload,
            "signature": base64.urlsafe_b64encode(signature_path.read_bytes()).decode("ascii").rstrip("="),
        }

    def external_certification_authority(self, tenant_id: str) -> tuple[Path, Path, dict]:
        directory = self.root / "external-certification-authority"
        directory.mkdir(exist_ok=True)
        actor_id = "external-certifier"
        private_key = directory / f"{actor_id}.private.pem"
        public_key = directory / f"{actor_id}.public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)],
                       check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
                       check=True, capture_output=True)
        self.actor_keys[actor_id] = private_key
        store_path = directory / "trust-store.json"
        store_path.write_text(json.dumps({"schema_version": "2.0", "store_id": "external-ca-fixture",
            "purpose": "external-certification", "actors": [{"actor_id": actor_id,
                "key_id": f"key-{actor_id}", "roles": ["independent-certifier"],
                "public_key_path": public_key.name, "not_before": "2020-01-01T00:00:00Z",
                "not_after": "2099-01-01T00:00:00Z", "revoked": False,
                "organization_id": "external-certification-org", "authority_class": "certification-body"}],
            "revoked_record_ids": []}), encoding="utf-8")
        store = production_closure.ActorTrustStore.load(store_path)
        policy = {"schema_version": "1.0", "policy_id": "external-ca-policy", "tenant_id": tenant_id,
            "external_store_id": store.store_id, "external_store_sha256": store.digest,
            "authority_organization_id": "external-certification-org", "authority_class": "certification-body",
            "purposes": ["independent-certification"], "issued_at": "2020-01-01T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z", "revoked": False}
        policy_path = directory / "policy.json"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        approval = self.sign("external-trust-approver", {"policy_id": policy["policy_id"],
            "tenant_id": tenant_id, "policy_sha256": production_closure.canonical_digest(policy),
            "external_store_sha256": store.digest, "purpose": "independent-certification"},
            suffix="external-ca-policy")
        return store_path, policy_path, approval

    def provider_receipt(self, cutover: dict, target_state: str, operation: str, suffix: str,
                         *, provider: dict | None = None, effect_state: str = "SUCCEEDED") -> dict:
        native = self.root / f"native-provider-{suffix}.json"
        native.write_text(json.dumps({"state": effect_state, "operation": operation}), encoding="utf-8")
        native_ref = {"path": str(native), "sha256": production_closure.sha256_bytes(native.read_bytes()),
                      "bytes": native.stat().st_size}
        effective_provider = provider or cutover["provider"]
        wrapper = {
            "schema_version": "2.0" if effective_provider.get("profile_version") == "2.0" else "1.0",
            "receipt_id": f"receipt-{suffix}",
            "cutover_id": cutover["cutover_id"], "tenant_id": cutover["tenant_id"],
            "target_key": cutover["target_key"], "target_state": target_state,
            "provider": effective_provider, "operation": operation,
            "adapter_receipt": native_ref, "effect_state": effect_state,
            "request_sha256": production_closure.sha256_bytes(f"request-{suffix}".encode()),
            "issued_at": production_closure.now_text(),
        }
        if effective_provider.get("profile_version") == "2.0":
            control_bytes = {"identity": b"fixture-identity-binding", "least_privilege": b"fixture-least-privilege-policy",
                             "state_backend": b"fixture-state-backend", "rollback": b"fixture-rollback-plan"}
            controls = {}
            for name, content in control_bytes.items():
                control_path = self.root / f"provider-control-{name}-{suffix}.json"
                control_path.write_bytes(content)
                controls[name] = {"path": str(control_path),
                    "sha256": production_closure.sha256_bytes(content), "bytes": len(content)}
            wrapper.update({"control_evidence": controls,
                            "control_decisions": {name: "PASS" for name in control_bytes}})
        path = self.root / f"provider-wrapper-{suffix}.json"
        path.write_text(json.dumps(wrapper), encoding="utf-8")
        return {"path": str(path), "sha256": production_closure.sha256_bytes(path.read_bytes()),
                "bytes": path.stat().st_size}

    @staticmethod
    def exact_provider_profile(account: bytes) -> dict:
        return {"profile_version": "2.0", "provider_id": "fixture-cloud", "provider_api_version": "2026-01-01",
            "account_binding_sha256": production_closure.sha256_bytes(account), "account_model": "isolated-test-account",
            "region": "test-region-1", "adapter_id": "fixture-provider", "adapter_version": "1.0.0",
            "iac_tool": "fixture-iac", "iac_tool_version": "1.0.0",
            "state_backend_sha256": production_closure.sha256_bytes(b"fixture-state-backend"),
            "identity_binding_sha256": production_closure.sha256_bytes(b"fixture-identity-binding"),
            "least_privilege_policy_sha256": production_closure.sha256_bytes(b"fixture-least-privilege-policy"),
            "rollback_plan_sha256": production_closure.sha256_bytes(b"fixture-rollback-plan"),
            "precheck_operation": "inspect", "execute_operation": "apply",
            "verify_operation": "inspect", "rollback_operation": "undo"}

    @staticmethod
    def corpus_actors(corpus_role: str) -> tuple[str, str, str]:
        if corpus_role == "holdout":
            return "executor-holdout", "holdout-executor", "verifier-holdout"
        if corpus_role == "production":
            return "executor-production", "production-executor", "verifier-production"
        return "executor-dev", "executor", "verifier-dev"

    def envelope_file(
        self,
        batch: int,
        claim_type: str,
        claim_index: int,
        *,
        producer: str | None = None,
        role: str | None = None,
        environment: str = "clean-local-fixture",
        outcome: str = "PASS",
        subject: dict | None = None,
        suffix: str = "",
        corpus_role: str = "development",
        corpus_digest: str | None = None,
    ) -> Path:
        expected_producer, expected_role, _ = self.corpus_actors(corpus_role)
        producer = producer or expected_producer
        role = role or expected_role
        obligation = runtime.OracleRegistry.load().resolve(batch, claim_type, claim_index)
        if subject is None:
            subject_file = self.root / f"subject-{batch}-{claim_type}-{claim_index}-{corpus_role}-{suffix}.json"
            subject_file.write_text(json.dumps({
                "schema_version": "1.0",
                "oracle_id": obligation.oracle_id,
                "executor_id": obligation.executor_id,
                "batch": batch,
                "claim": {"type": claim_type, "index": claim_index, "sha256": obligation.claim_sha256},
                "corpus": {"role": corpus_role, "id": f"corpus-{corpus_role}",
                           "sha256": corpus_digest or runtime.sha256_bytes(f"corpus-{corpus_role}".encode()),
                           "independent": corpus_role in {"holdout", "representative", "production"}},
                "decision": outcome,
                "checks": [{
                    "name": f"claim-specific-{claim_type}-{claim_index}",
                    "outcome": outcome,
                    "detail": f"signed fixture {corpus_role} corpus result",
                }],
                "limitations": [],
            }, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            subject = runtime.ingest_artifact(self.workspace, subject_file)
        metadata = runtime.state_store(self.workspace).metadata()
        attestation_suffix = f"{batch}-{claim_type}-{claim_index}-{corpus_role}-{suffix or 'default'}"
        bindings = {
            "batch": batch,
            "claim_type": claim_type,
            "claim_index": claim_index,
            "claim_sha256": obligation.claim_sha256,
            "subject_sha256": subject["sha256"],
            "source_fingerprint": metadata["source_fingerprint"],
            "corpus_role": corpus_role,
            "outcome": outcome,
            "oracle_id": obligation.oracle_id,
        }
        payload = {
            "evidence_version": "1.0",
            "batch": batch,
            "claim": {"type": claim_type, "index": claim_index},
            "producer": {"id": producer, "role": role},
            "environment": {"id": environment, "digest": runtime.sha256_bytes(environment.encode())},
            "subject": {
                "type": "claim-oracle-result",
                "sha256": subject["sha256"],
                "uri": subject["uri"],
                "bytes": subject["bytes"],
            },
            "scope": {
                "source_fingerprint": metadata["source_fingerprint"],
                "target_objective": metadata["target_objective"],
                "assumptions": [],
            },
            "observations": [{"name": f"claim-{claim_type}-{claim_index}", "outcome": outcome, "oracle": obligation.oracle_id}],
            "replay": {
                "argv": ["fixture-replay", claim_type, str(claim_index)],
                "cwd": str(self.source),
                "command_digest": runtime.sha256_bytes(f"{batch}:{claim_type}:{claim_index}:{suffix}".encode()),
            },
            "assurance": {
                "oracle_id": obligation.oracle_id,
                "claim_sha256": obligation.claim_sha256,
                "corpus_role": corpus_role,
                "executor_attestation": self.sign(producer, {**bindings, "actor_id": producer}, suffix=f"executor-{attestation_suffix}"),
                "oracle_attestation": self.sign("oracle-owner", bindings, suffix=f"oracle-{attestation_suffix}"),
            },
        }
        path = self.root / f"envelope-{batch}-{claim_type}-{claim_index}-{corpus_role}-{suffix}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def record_claim(
        self,
        batch: int,
        claim_type: str,
        claim_index: int,
        *,
        producer: str | None = None,
        verifier: str | None = None,
        subject: dict | None = None,
        suffix: str = "",
        corpus_role: str = "development",
        corpus_digest: str | None = None,
    ) -> dict:
        expected_producer, producer_role, expected_verifier = self.corpus_actors(corpus_role)
        producer = producer or expected_producer
        verifier = verifier or expected_verifier
        evidence = runtime.record_evidence(
            self.workspace,
            batch,
            self.envelope_file(
                batch, claim_type, claim_index, producer=producer, role=producer_role,
                subject=subject, suffix=suffix, corpus_role=corpus_role, corpus_digest=corpus_digest,
            ),
            kind="artifact" if claim_type == "output" else ("test" if claim_type == "test" else "external"),
            claim_type=claim_type,
            claim_index=claim_index,
            producer_id=producer,
            producer_role=producer_role,
            environment="clean-local-fixture",
            outcome="PASS",
            external=claim_type == "external",
        )
        verifier_attestation = self.sign(verifier, {
            "actor_id": verifier,
            "batch": batch,
            "evidence_id": evidence["evidence_id"],
            "evidence_sha256": runtime.semantic_record_digest(evidence),
            "outcome": "PASS",
            "corpus_role": corpus_role,
        }, suffix=f"verifier-{batch}-{claim_type}-{claim_index}-{corpus_role}-{suffix or 'default'}")
        runtime.verify_evidence(
            self.workspace, batch, evidence["evidence_id"], verifier, "PASS", verifier_attestation,
        )
        return evidence

    def make_batch_one_ready(self) -> dict:
        self.prepare(1)
        profile = runtime.profile(1)
        for claim_type, claims in (("output", profile["required_outputs"]), ("test", profile["required_tests"])):
            for index, _ in enumerate(claims):
                obligation = runtime.OracleRegistry.load().resolve(1, claim_type, index)
                for corpus_role in obligation.required_corpora:
                    self.record_claim(1, claim_type, index, corpus_role=corpus_role)
        return runtime.evaluate_gate(self.workspace, 1)

    def domain_result_file(self, *, batch: int = 1, corpus_role: str = "development", independent: bool = False) -> Path:
        obligation = runtime.OracleRegistry.load().resolve(batch, "output", 0)
        policy = domain_handlers.POLICIES[batch]
        tools = []
        raw_evidence = []
        for capability in policy.capabilities:
            role = domain_handlers.evidence_role(policy, capability)
            raw_file = self.root / f"native-tool-{batch}-{capability}-{corpus_role}.log"
            raw_file.write_text(f"{policy.handler} executed {capability} against the exact fixture\n", encoding="utf-8")
            raw_bytes = raw_file.read_bytes()
            tools.append({
                "name": f"{policy.handler}-native-{capability}", "version": "1.0.0",
                "argv_sha256": runtime.sha256_bytes(f"{policy.operation}:{capability}".encode()),
                "exit_code": 0, "evidence_role": role,
            })
            raw_evidence.append({"path": str(raw_file), "sha256": runtime.sha256_bytes(raw_bytes), "bytes": len(raw_bytes), "role": role})
        assertions = [{
            "name": f"{obligation.oracle_id}:operation:{policy.operation}", "outcome": "PASS",
            "detail": f"{policy.operation} completed",
        }]
        assertions.extend({
            "name": f"{obligation.oracle_id}:capability:{capability}", "outcome": "PASS",
            "detail": f"{capability} produced byte-bound native evidence",
        } for capability in policy.capabilities)
        assertions.extend({
            "name": f"{obligation.oracle_id}:safety:{control}", "outcome": "PASS",
            "detail": f"{control} remained enforced",
        } for control in policy.safety_controls)
        payload = {
            "schema_version": "1.0",
            "batch": batch,
            "executor_id": obligation.executor_id,
            "claim": {"type": "output", "index": 0, "sha256": obligation.claim_sha256},
            "corpus": {
                "role": corpus_role,
                "id": f"corpus-{corpus_role}",
                "sha256": runtime.sha256_bytes(f"corpus-{corpus_role}".encode()),
                "independent": independent,
            },
            "source_fingerprint": runtime.state_store(self.workspace).metadata()["source_fingerprint"],
            "environment": {
                "id": f"environment-{corpus_role}",
                "kind": "holdout" if corpus_role == "holdout" else "clean",
                "digest": runtime.sha256_bytes(f"environment-{corpus_role}".encode()),
            },
            "domain_contract": domain_handlers.contract_for_batch(batch),
            "toolchain": tools,
            "assertions": assertions,
            "raw_evidence": raw_evidence,
            "decision": "PASS",
            "limitations": [],
        }
        result_file = self.root / f"domain-result-{batch}-{corpus_role}.json"
        result_file.write_text(json.dumps(payload), encoding="utf-8")
        return result_file

    def test_catalog_owns_all_batches_and_has_acyclic_dependencies(self) -> None:
        profiles = [runtime.profile(number) for number in range(1, 39)]
        self.assertEqual(list(range(1, 39)), [item["batch"] for item in profiles])
        visiting: set[int] = set()
        visited: set[int] = set()

        def visit(batch: int) -> None:
            self.assertNotIn(batch, visiting, f"dependency cycle reaches Batch {batch}")
            if batch in visited:
                return
            visiting.add(batch)
            for dependency in profiles[batch - 1]["dependencies"]:
                visit(dependency)
            visiting.remove(batch)
            visited.add(batch)

        for number in range(1, 39):
            visit(number)

    def test_all_38_domain_executors_are_exactly_registered(self) -> None:
        registry = domain_executors.ExecutorRegistry.load()
        self.assertEqual(list(range(1, 39)), sorted(registry.by_batch))
        self.assertEqual(38, len({entry["handler"] for entry in registry.by_batch.values()}))
        self.assertEqual(set(entry["handler"] for entry in registry.by_batch.values()), set(domain_handlers.HANDLERS))
        self.assertEqual(38, len({id(handler) for handler in domain_handlers.HANDLERS.values()}))

    def test_all_38_domain_handlers_execute_their_exact_contract(self) -> None:
        self.prepare(1)
        for batch in range(1, 39):
            with self.subTest(batch=batch):
                subject = domain_executors.execute(self.domain_result_file(batch=batch), (self.root.resolve(),))
                self.assertEqual(batch, subject["batch"])
                self.assertIn(f"domain-handler:{domain_handlers.POLICIES[batch].handler}", {item["name"] for item in subject["checks"]})

    def test_domain_handler_rejects_cross_batch_contract_substitution(self) -> None:
        self.prepare(1)
        result_file = self.domain_result_file(batch=1)
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        payload["domain_contract"] = domain_handlers.contract_for_batch(2)
        result_file.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(domain_executors.DomainExecutionError, "does not match handler"):
            domain_executors.execute(result_file, (self.root.resolve(),))

    def test_domain_handler_rejects_generic_success_tool(self) -> None:
        self.prepare(1)
        result_file = self.domain_result_file(batch=1)
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        payload["toolchain"][0]["name"] = "/usr/bin/true"
        result_file.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(domain_executors.DomainExecutionError, "generic/no-op"):
            domain_executors.execute(result_file, (self.root.resolve(),))

    def test_domain_executor_requires_real_bytes_and_independent_holdout(self) -> None:
        self.prepare(1)
        result = domain_executors.execute(self.domain_result_file(), (self.root.resolve(),))
        obligation = runtime.OracleRegistry.load().resolve(1, "output", 0)
        runtime.OracleRegistry.load().validate_subject(result, obligation, "development", "PASS")
        with self.assertRaisesRegex(domain_executors.DomainExecutionError, "independently owned"):
            domain_executors.execute(self.domain_result_file(corpus_role="holdout"), (self.root.resolve(),))
        holdout = domain_executors.execute(
            self.domain_result_file(corpus_role="holdout", independent=True), (self.root.resolve(),),
        )
        runtime.OracleRegistry.load().validate_subject(holdout, obligation, "holdout", "PASS")

    def test_holdout_corpus_digest_cannot_reuse_development_bytes(self) -> None:
        self.prepare(1)
        shared = runtime.sha256_bytes(b"same-corpus-bytes")
        self.record_claim(1, "output", 0, corpus_role="development", corpus_digest=shared, suffix="shared-development")
        self.record_claim(1, "output", 0, corpus_role="holdout", corpus_digest=shared, suffix="shared-holdout")
        _, findings, _ = runtime.verified_claims(self.workspace, 1)
        self.assertTrue(any("Holdout corpus digest is reused" in finding for finding in findings))

    def test_production_evidence_ingress_requires_production_roles_but_does_not_certify(self) -> None:
        self.prepare(2)
        evidence = self.record_claim(2, "external", 0, corpus_role="production")
        self.assertEqual("production-executor", evidence["producer_role"])
        claims, findings, external_seen = runtime.verified_claims(self.workspace, 2)
        self.assertTrue(claims[("external", 0)])
        self.assertTrue(external_seen)
        self.assertEqual([], findings)
        gate = runtime.evaluate_gate(self.workspace, 2)
        self.assertEqual("BLOCKED", gate["decision"])
        self.assertFalse(gate["certified"])

    def test_prepare_all_creates_38_bound_execution_plans_and_90_routes(self) -> None:
        reports = [self.prepare(number) for number in range(1, 39)]
        self.assertEqual("PARTIAL", reports[0]["status"])
        self.assertEqual("BLOCKED", reports[-1]["status"])
        for number in range(1, 39):
            plan = runtime.load_json(runtime.batch_dir(self.workspace, number) / "execution-plan.json")
            self.assertEqual(number, plan["batch"])
            self.assertEqual(runtime.state_store(self.workspace).metadata()["source_fingerprint"], plan["source_fingerprint"])
            self.assertFalse(plan["execution_policy"]["shell"])
            self.assertFalse(plan["execution_policy"]["external_claims_allowed"])
        routes = runtime.load_json(runtime.batch_dir(self.workspace, 4) / "observation.json")["directional_routes"]
        self.assertEqual(90, len(routes))
        self.assertEqual(90, len({item["route_id"] for item in routes}))

    def test_empty_evidence_fails_closed(self) -> None:
        self.prepare(1)
        result = runtime.evaluate_gate(self.workspace, 1)
        self.assertEqual("NOT_RUN", result["decision"])
        self.assertFalse(result["certified"])

    def test_generic_success_commands_and_unsigned_verifiers_cannot_satisfy_claims(self) -> None:
        self.prepare(1)
        profile = runtime.profile(1)
        for claim_type, claims in (("output", profile["required_outputs"]), ("test", profile["required_tests"])):
            for index, _ in enumerate(claims):
                evidence = runtime.run_command(
                    self.workspace, 1, f"generic-{claim_type}-{index}", ["/usr/bin/true"], ".",
                    f"generic-executor-{claim_type}-{index}", 30, claim_type=claim_type, claim_index=index,
                )
                runtime.verify_evidence(
                    self.workspace, 1, evidence["evidence_id"], f"arbitrary-verifier-{claim_type}-{index}", "PASS",
                )
        result = runtime.evaluate_gate(self.workspace, 1)
        self.assertEqual("BLOCKED", result["decision"])
        self.assertFalse(result["certified"])
        self.assertTrue(any("lacks authenticated Claim Oracle" in finding for finding in result["findings"]))

    def test_independently_verified_claims_reach_only_local_toolkit_pass(self) -> None:
        result = self.make_batch_one_ready()
        self.assertEqual("LOCAL_TOOLKIT_PASS", result["decision"])
        self.assertFalse(result["certified"])
        with self.assertRaisesRegex(runtime.RuntimeFailure, "disabled by the package-owned trust policy"):
            runtime.request_certificate(self.workspace, 1, "requester-c")

    def test_subject_must_exist_and_one_subject_cannot_satisfy_distinct_claims(self) -> None:
        self.prepare(1)
        missing = self.envelope_file(1, "output", 0)
        payload = json.loads(missing.read_text(encoding="utf-8"))
        payload["subject"]["sha256"] = "sha256:" + "f" * 64
        payload["subject"]["uri"] = "artifact://" + payload["subject"]["sha256"]
        missing.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(runtime.RuntimeFailure, "not present"):
            runtime.record_evidence(
                self.workspace, 1, missing, kind="artifact", claim_type="output", claim_index=0,
                producer_id="executor-dev", producer_role="executor", environment="clean-local-fixture", outcome="PASS", external=False,
            )

        first_envelope = runtime.load_json(self.envelope_file(1, "output", 0, suffix="source-claim"))
        cross_claim = self.envelope_file(1, "output", 1, subject=first_envelope["subject"], suffix="cross-claim")
        with self.assertRaisesRegex(runtime.RuntimeFailure, "bound to another Claim"):
            runtime.record_evidence(
                self.workspace, 1, cross_claim, kind="artifact", claim_type="output", claim_index=1,
                producer_id="executor-dev", producer_role="executor", environment="clean-local-fixture", outcome="PASS", external=False,
            )

    def test_self_verification_and_stale_or_tampered_evidence_are_rejected(self) -> None:
        self.prepare(1)
        envelope = self.envelope_file(1, "output", 0, producer="executor-dev")
        evidence = runtime.record_evidence(
            self.workspace, 1, envelope, kind="artifact", claim_type="output", claim_index=0,
            producer_id="executor-dev", producer_role="executor", environment="clean-local-fixture", outcome="PASS", external=False,
        )
        with self.assertRaisesRegex(runtime.RuntimeFailure, "cannot verify its own evidence"):
            runtime.verify_evidence(self.workspace, 1, evidence["evidence_id"], "executor-dev", "PASS")
        mirror = runtime.batch_dir(self.workspace, 1) / "evidence" / f"{evidence['evidence_id']}.json"
        tampered = json.loads(mirror.read_text(encoding="utf-8"))
        tampered["claim_index"] = 1
        mirror.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(runtime.RuntimeFailure, "differs from transactional state"):
            runtime.verify_evidence(self.workspace, 1, evidence["evidence_id"], "verifier-dev", "PASS")

    def test_tampered_content_addressed_object_is_rejected(self) -> None:
        self.prepare(1)
        evidence = runtime.record_evidence(
            self.workspace, 1, self.envelope_file(1, "output", 0), kind="artifact", claim_type="output", claim_index=0,
            producer_id="executor-dev", producer_role="executor", environment="clean-local-fixture", outcome="PASS", external=False,
        )
        object_path = self.workspace / evidence["object"]["object_path"]
        object_path.chmod(0o644)
        object_path.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(runtime.RuntimeFailure, "byte/digest verification"):
            runtime.verify_evidence(self.workspace, 1, evidence["evidence_id"], "verifier-dev", "PASS")

    def test_dependency_gate_unblocks_next_batch_only_after_local_readiness(self) -> None:
        self.prepare(2)
        self.assertEqual("BLOCKED", runtime.load_json(runtime.batch_dir(self.workspace, 2) / "completion-report.json")["status"])
        self.make_batch_one_ready()
        self.assertEqual("PARTIAL", self.prepare(2)["status"])

    def test_concurrent_idempotency_and_fencing_are_linearizable(self) -> None:
        self.prepare(17)

        def same_effect(_: int) -> dict:
            return runtime.plan_effect(self.workspace, 17, "same-key", "deploy", "sandbox", "actor-a", "approval-a", 1, True)

        with ThreadPoolExecutor(max_workers=16) as pool:
            records = list(pool.map(same_effect, range(64)))
        self.assertEqual(1, len({item["effect_id"] for item in records}))
        self.assertEqual(1, len(runtime.state_store(self.workspace).effects()))
        with self.assertRaisesRegex(runtime.RuntimeFailure, "binds a different effect"):
            runtime.plan_effect(self.workspace, 17, "same-key", "destroy", "sandbox", "actor-a", "approval-a", 2, True)
        with self.assertRaisesRegex(runtime.RuntimeFailure, "fencing token must be greater"):
            runtime.plan_effect(self.workspace, 17, "new-key", "deploy", "sandbox", "actor-a", "approval-a", 1, True)

    def test_signed_adapter_execution_is_digest_bound_and_idempotent(self) -> None:
        self.prepare(1)
        request = {
            "schema_version": "1.0", "batch": 1, "adapter_id": "fixture-provider", "operation": "inspect",
            "parameters": {"target": "fixture-target"}, "idempotency_key": "fixture-idempotency",
            "fencing_token": 1, "source_fingerprint": runtime.state_store(self.workspace).metadata()["source_fingerprint"],
            "approval": None, "compensates_idempotency_key": None,
        }
        request_path = self.root / "adapter-request.json"
        request_path.write_text(json.dumps(request), encoding="utf-8")
        first = trusted_adapters.execute(self.workspace, request_path, self.adapter_registry(), self.trust_store, (self.root.resolve(),))
        second = trusted_adapters.execute(self.workspace, request_path, self.adapter_registry(), self.trust_store, (self.root.resolve(),))
        self.assertEqual("SUCCEEDED", first["state"])
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(first["request_sha256"], second["request_sha256"])
        request["parameters"]["target"] = "different-target"
        request_path.write_text(json.dumps(request), encoding="utf-8")
        with self.assertRaisesRegex(trusted_adapters.AdapterError, "binds a different effect"):
            trusted_adapters.execute(self.workspace, request_path, self.adapter_registry(), self.trust_store, (self.root.resolve(),))

    def test_mutating_adapter_compensation_is_approved_and_atomic(self) -> None:
        self.prepare(1)
        source_fingerprint = runtime.state_store(self.workspace).metadata()["source_fingerprint"]
        registry_path = self.adapter_registry()
        trust = trusted_adapters.ActorTrustStore.load(self.trust_store)
        registry = trusted_adapters.Registry.load(registry_path, trust, source_fingerprint)

        def signed_request(operation: str, key: str, fencing: int, compensates: str | None) -> dict:
            parameters = {"target": "fixture-target"}
            effect = registry.adapters["fixture-provider"].operations[operation].effect_class
            identity = {
                "batch": 1, "skill": runtime.profile(1)["skill"], "domain_contract": domain_handlers.contract_for_batch(1),
                "adapter_id": "fixture-provider", "adapter_registry_sha256": registry.sha256, "operation": operation,
                "parameters_sha256": trusted_adapters.digest(parameters), "source_fingerprint": source_fingerprint,
                "effect_class": effect, "idempotency_key": key, "fencing_token": fencing,
                "compensates_idempotency_key": compensates,
            }
            request_sha256 = trusted_adapters.digest(identity)
            approval = self.sign("approver", {"request_sha256": request_sha256, "adapter_id": "fixture-provider",
                                               "operation": operation, "source_fingerprint": source_fingerprint,
                                               "effect_class": effect}, suffix=f"approval-{operation}")
            return {"schema_version": "1.0", "batch": 1, "adapter_id": "fixture-provider", "operation": operation,
                    "parameters": parameters, "idempotency_key": key, "fencing_token": fencing,
                    "source_fingerprint": source_fingerprint, "approval": approval,
                    "compensates_idempotency_key": compensates}

        request_path = self.root / "mutating-adapter-request.json"
        request_path.write_text(json.dumps(signed_request("apply", "apply-idempotency", 1, None)), encoding="utf-8")
        applied = trusted_adapters.execute(self.workspace, request_path, registry_path, self.trust_store, (self.root.resolve(),))
        self.assertEqual("SUCCEEDED", applied["state"])
        request_path.write_text(json.dumps(signed_request("undo", "undo-idempotency", 2, "apply-idempotency")), encoding="utf-8")
        undone = trusted_adapters.execute(self.workspace, request_path, registry_path, self.trust_store, (self.root.resolve(),))
        self.assertEqual("SUCCEEDED", undone["state"])
        effects = {item["idempotency_key"]: item for item in runtime.state_store(self.workspace).effects()}
        self.assertEqual("COMPENSATED", effects["apply-idempotency"]["state"])
        self.assertEqual(effects["undo-idempotency"]["effect_id"], effects["apply-idempotency"]["compensation_effect_id"])

    def test_effect_transition_rolls_back_on_event_failure(self) -> None:
        self.prepare(17)
        planned = runtime.plan_effect(self.workspace, 17, "transition-key", "deploy", "sandbox", "actor-a", "approval-a", 1, True)
        identity = {"batch": 17, "action": "deploy", "target": "sandbox", "actor_id": "actor-a",
                    "approval_id": "approval-a", "fencing_token": 1, "reversible": True}
        identity_sha256 = runtime.sha256_bytes(runtime.canonical_bytes({"idempotency_key": "transition-key", **identity}))
        store = runtime.state_store(self.workspace)
        with mock.patch.object(runtime.TransactionStore, "_append_event", side_effect=RuntimeError("injected effect crash")):
            with self.assertRaisesRegex(RuntimeError, "injected effect crash"):
                store.transition_effect("transition-key", identity_sha256, "PLANNED", "RUNNING",
                                        {"request_sha256": "sha256:" + "1" * 64}, runtime.utc_now())
        self.assertEqual("PLANNED", store.effects()[0]["state"])
        self.assertEqual(planned["effect_id"], store.effects()[0]["effect_id"])

    def test_production_closure_control_plane_runs_complete_engineering_flow(self) -> None:
        snapshot_file = self.root / "customer-snapshot.bin"
        snapshot_file.write_bytes(b"masked customer fixture")
        snapshot_manifest = {
            "schema_version": "1.0", "snapshot_id": "snapshot-001", "tenant_id": "tenant-001",
            "environment_class": "test", "classification": "synthetic", "purpose": "migration-validation",
            "read_only": True, "files": [{"path": str(snapshot_file),
                "sha256": production_closure.sha256_bytes(snapshot_file.read_bytes()), "bytes": snapshot_file.stat().st_size}],
        }
        snapshot_manifest_path = self.root / "snapshot-manifest.json"
        snapshot_manifest_path.write_text(json.dumps(snapshot_manifest), encoding="utf-8")
        snapshot_sha = production_closure.sha256_bytes(production_closure.canonical_bytes(snapshot_manifest))
        snapshot_auth = self.sign("data-owner", {"snapshot_id": "snapshot-001", "tenant_id": "tenant-001",
            "manifest_sha256": snapshot_sha, "environment_class": "test", "purpose": "migration-validation"},
            suffix="snapshot")
        snapshot = production_closure.register_snapshot(
            self.workspace, snapshot_manifest_path, snapshot_auth, self.trust_store, (self.root.resolve(),),
        )
        self.assertEqual("metadata-and-content-digests-only", snapshot["data_minimization"])
        self.assertNotIn(str(snapshot_file), json.dumps(snapshot))

        holdout_file = self.root / "customer-holdout.bin"
        holdout_file.write_bytes(b"sealed independent holdout")
        holdout_manifest = {
            "schema_version": "1.0", "holdout_id": "holdout-001", "tenant_id": "tenant-001",
            "environment_class": "test", "corpus": {"path": str(holdout_file),
                "sha256": production_closure.sha256_bytes(holdout_file.read_bytes()), "bytes": holdout_file.stat().st_size},
            "development_corpus_sha256": production_closure.sha256_bytes(b"development-corpus"),
            "transformation_author_ids": ["transformation-author"], "executor_ids": ["executor-holdout"],
            "verifier_ids": ["verifier-holdout"],
        }
        holdout_manifest_path = self.root / "holdout-manifest.json"
        holdout_manifest_path.write_text(json.dumps(holdout_manifest), encoding="utf-8")
        holdout_sha = production_closure.sha256_bytes(production_closure.canonical_bytes(holdout_manifest))
        holdout_auth = self.sign("holdout-custodian", {"holdout_id": "holdout-001", "tenant_id": "tenant-001",
            "manifest_sha256": holdout_sha, "corpus_sha256": holdout_manifest["corpus"]["sha256"],
            "environment_class": "test"}, suffix="holdout")
        holdout = production_closure.register_holdout(
            self.workspace, holdout_manifest_path, holdout_auth, self.trust_store, (self.root.resolve(),),
        )
        self.assertTrue(holdout["sealed"])

        holdout_execution = self.root / "holdout-execution.json"
        holdout_execution.write_text(json.dumps({"state": "SUCCEEDED"}), encoding="utf-8")
        holdout_claim = self.root / "holdout-claim.json"
        holdout_claim.write_text(json.dumps({"claim": "route-equivalence", "outcome": "PASS"}), encoding="utf-8")
        holdout_result = {"schema_version": "1.0", "result_id": "holdout-result-001",
            "holdout_id": "holdout-001", "tenant_id": "tenant-001",
            "target_release_sha256": production_closure.sha256_bytes(b"target-release"),
            "provider_account_sha256": production_closure.sha256_bytes(b"sandbox-account"),
            "execution_receipt": {"path": str(holdout_execution),
                "sha256": production_closure.sha256_bytes(holdout_execution.read_bytes()),
                "bytes": holdout_execution.stat().st_size},
            "decision": "PASS", "claim_results": [{"claim_id": "route-equivalence", "outcome": "PASS",
                "evidence": {"path": str(holdout_claim),
                    "sha256": production_closure.sha256_bytes(holdout_claim.read_bytes()),
                    "bytes": holdout_claim.stat().st_size}}],
            "started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:00:01Z"}
        holdout_result_path = self.root / "holdout-result.json"
        holdout_result_path.write_text(json.dumps(holdout_result), encoding="utf-8")
        bad_holdout_path = self.root / "holdout-result-mismatched.json"
        bad_holdout_path.write_text(json.dumps({**holdout_result, "decision": "FAIL"}), encoding="utf-8")
        with self.assertRaisesRegex(production_closure.ClosureError, "differs from claim outcomes"):
            production_closure.record_holdout_result(self.workspace, bad_holdout_path, {}, {}, self.trust_store,
                                                     (self.root.resolve(),))
        normalized_claims = [{"claim_id": "route-equivalence", "outcome": "PASS",
            "evidence": {"sha256": holdout_result["claim_results"][0]["evidence"]["sha256"],
                         "bytes": holdout_claim.stat().st_size}}]
        holdout_root = production_closure.canonical_digest({"holdout_corpus_sha256": holdout["corpus"]["sha256"],
            "execution_receipt_sha256": holdout_result["execution_receipt"]["sha256"],
            "claim_results": normalized_claims})
        result_sha = production_closure.sha256_bytes(production_closure.canonical_bytes(holdout_result))
        result_bindings = {"result_id": "holdout-result-001", "holdout_id": "holdout-001",
            "tenant_id": "tenant-001", "manifest_sha256": result_sha, "evidence_root": holdout_root,
            "target_release_sha256": holdout_result["target_release_sha256"],
            "provider_account_sha256": holdout_result["provider_account_sha256"], "decision": "PASS"}
        executor_auth = self.sign("executor-holdout", result_bindings, suffix="holdout-result-executor")
        verifier_auth = self.sign("verifier-holdout", {**result_bindings, "executor_id": "executor-holdout"},
                                  suffix="holdout-result-verifier")
        recorded_holdout = production_closure.record_holdout_result(self.workspace, holdout_result_path,
            executor_auth, verifier_auth, self.trust_store, (self.root.resolve(),))
        self.assertTrue(recorded_holdout["independent"])

        cutover_plan = {
            "schema_version": "1.0", "cutover_id": "cutover-001", "tenant_id": "tenant-001",
            "snapshot_id": "snapshot-001", "target_key": "sandbox-target",
            "target_release_sha256": production_closure.sha256_bytes(b"target-release"),
            "rollback_adapter_id": "fixture-provider", "rollback_operation": "undo",
            "preconditions": ["reconciliation-pass", "rollback-ready"],
        }
        cutover_path = self.root / "cutover-plan.json"
        cutover_path.write_text(json.dumps(cutover_plan), encoding="utf-8")
        plan_sha = production_closure.sha256_bytes(production_closure.canonical_bytes(cutover_plan))
        approval = self.sign("approver", {"cutover_id": "cutover-001", "tenant_id": "tenant-001",
            "plan_sha256": plan_sha, "snapshot_id": "snapshot-001", "target_key": "sandbox-target"},
            suffix="cutover-plan")
        production_closure.plan_cutover(
            self.workspace, cutover_path, approval, self.trust_store, (self.root.resolve(),),
        )

        states = [
            ("PLANNED", "PRECHECKED", "operations-owner"),
            ("PRECHECKED", "APPROVED", "approver"),
            ("APPROVED", "EXECUTING", "operations-owner"),
            ("EXECUTING", "VERIFYING", "verifier-production"),
            ("VERIFYING", "SUCCEEDED", "verifier-production"),
        ]
        for fencing, (source_state, target_state, actor_id) in enumerate(states, 1):
            receipt_path = self.root / f"receipt-{target_state}.json"
            receipt_path.write_text(json.dumps({"state": target_state, "fencing": fencing}), encoding="utf-8")
            receipt = {"path": str(receipt_path), "sha256": production_closure.sha256_bytes(receipt_path.read_bytes()),
                       "bytes": receipt_path.stat().st_size}
            attestation = self.sign(actor_id, {"cutover_id": "cutover-001", "tenant_id": "tenant-001",
                "expected_state": source_state, "target_state": target_state, "fencing_token": fencing,
                "receipt_sha256": receipt["sha256"]}, suffix=f"transition-{target_state}")
            cutover = production_closure.transition_cutover(
                self.workspace, "cutover-001", source_state, target_state, fencing, receipt, attestation,
                self.trust_store, (self.root.resolve(),),
            )
        self.assertEqual("SUCCEEDED", cutover["state"])

        production_closure.start_soak(
            self.workspace, "cutover-001", "soak-001", "test", "2026-01-01T00:00:00Z", 60, 40,
        )
        for sequence, observed_at in ((1, "2026-01-01T00:00:30Z"), (2, "2026-01-01T00:01:00Z")):
            metrics = {"requests": 100, "errors": 0, "critical_failures": 0, "availability": 1.0}
            metrics_sha = production_closure.canonical_digest(metrics)
            heartbeat = self.sign("operations-owner", {"run_id": "soak-001", "sequence": sequence,
                "observed_at": observed_at, "metrics_sha256": metrics_sha}, suffix=f"soak-{sequence}")
            production_closure.observe_soak(
                self.workspace, "soak-001", sequence, observed_at, metrics, heartbeat, self.trust_store,
            )
        running = production_closure.ClosureStore(self.workspace).row("soak_runs", "soak-001")
        evidence_root = production_closure.soak_evidence_root(running)
        finish = self.sign("verifier-production", {"run_id": "soak-001", "sequence": 3,
            "observed_at": "2026-01-01T00:01:01Z", "target_state": "PASSED", "evidence_root": evidence_root},
            suffix="soak-finish")
        soak = production_closure.finish_soak(
            self.workspace, "soak-001", 3, "2026-01-01T00:01:01Z", finish, self.trust_store,
        )
        self.assertEqual("PASSED", soak["state"])
        self.assertEqual("engineering-only", soak["evidence_class"])

        assessment = {
            "schema_version": "1.0", "assessment_id": "assessment-001", "tenant_id": "tenant-001",
            "scope": "fixture-only", "decision": "NOT_CERTIFIED", "evidence_root": soak["evidence_root"],
            "limitations": ["synthetic fixture"], "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
        }
        assessment_path = self.root / "assessment.json"
        assessment_path.write_text(json.dumps(assessment), encoding="utf-8")
        unbound = {**assessment, "assessment_id": "assessment-unbound",
                   "evidence_root": production_closure.sha256_bytes(b"unbound-evidence")}
        unbound_path = self.root / "assessment-unbound.json"
        unbound_path.write_text(json.dumps(unbound), encoding="utf-8")
        unbound_auth = self.sign("independent-certifier", {"assessment_id": "assessment-unbound",
            "tenant_id": "tenant-001", "report_sha256": production_closure.sha256_bytes(production_closure.canonical_bytes(unbound)),
            "evidence_root": unbound["evidence_root"], "decision": "NOT_CERTIFIED"}, suffix="assessment-unbound")
        with self.assertRaisesRegex(production_closure.ClosureError, "not a PASSED tenant soak"):
            production_closure.import_assessment(
                self.workspace, unbound_path, unbound_auth, self.trust_store, (self.root.resolve(),))
        report_sha = production_closure.sha256_bytes(production_closure.canonical_bytes(assessment))
        assessment_auth = self.sign("independent-certifier", {"assessment_id": "assessment-001",
            "tenant_id": "tenant-001", "report_sha256": report_sha, "evidence_root": soak["evidence_root"],
            "decision": "NOT_CERTIFIED"}, suffix="assessment")
        imported = production_closure.import_assessment(
            self.workspace, assessment_path, assessment_auth, self.trust_store, (self.root.resolve(),),
        )
        self.assertFalse(imported["certified"])
        ready = production_closure.readiness(self.workspace, "tenant-001")
        self.assertEqual("LOCAL_TOOLKIT_PASS", ready["decision"])
        self.assertEqual("NOT_CERTIFIED", ready["production_status"])
        self.assertEqual([], ready["findings"])
        self.assertEqual("soak-001", ready["selected_chain"]["run_id"])

        # A failed historical attempt must remain auditable without poisoning a
        # later complete evidence chain for the same tenant.
        historical_cutover = {"schema_version": "1.0", "cutover_id": "cutover-historical",
            "tenant_id": "tenant-001", "snapshot_id": "snapshot-001", "target_key": "old-target",
            "target_release_sha256": production_closure.sha256_bytes(b"old-release"),
            "state": "CANCELLED", "fencing_token": 1,
            "plan_sha256": production_closure.sha256_bytes(b"old-plan"),
            "approval": {"actor_id": "approver"}, "transitions": []}
        store = production_closure.ClosureStore(self.workspace)
        store.insert("cutovers", "cutover-historical",
            ("cutover-historical", "tenant-001", "old-target", "CANCELLED", 1,
             historical_cutover["plan_sha256"]), historical_cutover, "CUTOVER_CANCELLED")
        historical_soak = {"schema_version": "1.0", "run_id": "soak-historical",
            "cutover_id": "cutover-historical", "tenant_id": "tenant-001",
            "environment_class": "test", "state": "FAILED", "started_at": "2025-01-01T00:00:00Z",
            "required_seconds": 60, "max_gap_seconds": 40, "last_sequence": 0,
            "last_observed_at": "2025-01-01T00:01:00Z", "observations": [],
            "critical_failures": 1, "clock_mode": "system", "evidence_class": "engineering-only",
            "real_seven_day_elapsed": False}
        store.insert("soak_runs", "soak-historical",
            ("soak-historical", "cutover-historical", "test", "FAILED", 0,
             "2025-01-01T00:01:00Z"), historical_soak, "SOAK_FAILED")
        ready_with_history = production_closure.readiness(self.workspace, "tenant-001")
        self.assertEqual("LOCAL_TOOLKIT_PASS", ready_with_history["decision"])
        self.assertEqual("soak-001", ready_with_history["selected_chain"]["run_id"])
        self.assertEqual(2, ready_with_history["evaluated_chains"])
        self.assertEqual(1, ready_with_history["ignored_historical_chains"])
        self.assertEqual([], ready_with_history["findings"])

    def test_production_closure_rejects_holdout_reuse_and_short_production_soak(self) -> None:
        holdout_file = self.root / "reused.bin"
        holdout_file.write_bytes(b"same-corpus")
        corpus_sha = production_closure.sha256_bytes(holdout_file.read_bytes())
        manifest = {
            "schema_version": "1.0", "holdout_id": "holdout-reused", "tenant_id": "tenant-001",
            "environment_class": "test", "corpus": {"path": str(holdout_file), "sha256": corpus_sha,
                "bytes": holdout_file.stat().st_size}, "development_corpus_sha256": corpus_sha,
            "transformation_author_ids": ["transformation-author"], "executor_ids": ["executor-holdout"],
            "verifier_ids": ["verifier-holdout"],
        }
        path = self.root / "reused-manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(production_closure.ClosureError, "reuses development"):
            production_closure.register_holdout(self.workspace, path, {}, self.trust_store, (self.root.resolve(),))

        store = production_closure.ClosureStore(self.workspace)
        cutover = {"schema_version": "1.0", "cutover_id": "cutover-complete", "tenant_id": "tenant-001",
                   "target_key": "target", "state": "SUCCEEDED", "fencing_token": 1,
                   "plan_sha256": production_closure.sha256_bytes(b"plan"), "approval": {"actor_id": "approver"},
                   "transitions": []}
        store.insert("cutovers", "cutover-complete", ("cutover-complete", "tenant-001", "target", "SUCCEEDED", 1,
                     cutover["plan_sha256"]), cutover, "CUTOVER_SUCCEEDED")
        with self.assertRaisesRegex(production_closure.ClosureError, "at least seven days"):
            production_closure.start_soak(self.workspace, "cutover-complete", "short-production", "production",
                                          "2026-01-01T00:00:00Z", 60, 30)
        soak = {"schema_version": "1.0", "run_id": "stale-soak", "cutover_id": "cutover-complete",
                "tenant_id": "tenant-001", "environment_class": "test", "state": "RUNNING",
                "started_at": "2026-01-01T00:00:00Z", "required_seconds": 60, "max_gap_seconds": 40,
                "last_sequence": 1, "last_observed_at": "2026-01-01T00:00:30Z",
                "observations": [{"metrics_sha256": production_closure.canonical_digest({"ok": True})}],
                "critical_failures": 0}
        store.insert("soak_runs", "stale-soak", ("stale-soak", "cutover-complete", "test", "RUNNING", 1,
                     "2026-01-01T00:00:30Z"), soak, "SOAK_STARTED")
        with self.assertRaisesRegex(production_closure.ClosureError, "exceeds gap"):
            production_closure.finish_soak(self.workspace, "stale-soak", 2, "2026-01-01T00:01:20Z", {}, self.trust_store)
        self.assertIn("soak run has not reached PASSED", production_closure.readiness(self.workspace, "tenant-001")["findings"])

    def test_production_cutover_transition_is_linearizable_under_race(self) -> None:
        store = production_closure.ClosureStore(self.workspace)
        cutover = {"schema_version": "1.0", "cutover_id": "cutover-race", "tenant_id": "tenant-001",
                   "target_key": "target", "state": "PLANNED", "fencing_token": 0,
                   "plan_sha256": production_closure.sha256_bytes(b"race-plan"),
                   "approval": {"actor_id": "approver"}, "transitions": []}
        store.insert("cutovers", "cutover-race", ("cutover-race", "tenant-001", "target", "PLANNED", 0,
                     cutover["plan_sha256"]), cutover, "CUTOVER_PLANNED")
        receipt_path = self.root / "race-receipt.json"
        receipt_path.write_text("{}", encoding="utf-8")
        receipt = {"path": str(receipt_path), "sha256": production_closure.sha256_bytes(receipt_path.read_bytes()),
                   "bytes": receipt_path.stat().st_size}
        attestation = self.sign("operations-owner", {"cutover_id": "cutover-race", "tenant_id": "tenant-001",
            "expected_state": "PLANNED", "target_state": "PRECHECKED", "fencing_token": 1,
            "receipt_sha256": receipt["sha256"]}, suffix="cutover-race")

        def transition(_: int) -> str:
            try:
                production_closure.transition_cutover(self.workspace, "cutover-race", "PLANNED", "PRECHECKED", 1,
                    receipt, attestation, self.trust_store, (self.root.resolve(),))
                return "won"
            except production_closure.ClosureError:
                return "conflict"

        with ThreadPoolExecutor(max_workers=16) as pool:
            outcomes = list(pool.map(transition, range(32)))
        self.assertEqual(1, outcomes.count("won"))
        self.assertEqual(31, outcomes.count("conflict"))
        self.assertEqual("PRECHECKED", store.row("cutovers", "cutover-race")["state"])
        self.assertEqual([], store.verify_event_chain())

    def test_closure_event_chain_detects_current_record_and_metadata_tampering(self) -> None:
        store = production_closure.ClosureStore(self.workspace)
        record = {"schema_version": "1.0", "snapshot_id": "tamper-snapshot",
                  "tenant_id": "tenant-001", "environment_class": "test"}
        store.insert("snapshots", "tamper-snapshot", ("tamper-snapshot", "tenant-001", "test",
                     production_closure.sha256_bytes(b"tamper-manifest")), record, "SNAPSHOT_REGISTERED")
        connection = store.connect()
        try:
            changed = {**record, "environment_class": "production"}
            connection.execute("UPDATE snapshots SET record_json=? WHERE snapshot_id=?",
                               (production_closure.canonical_bytes(changed).decode(), "tamper-snapshot"))
        finally:
            connection.close()
        findings = store.verify_event_chain()
        self.assertTrue(any("current record differs from latest event" in item for item in findings))
        self.assertTrue(any("environment metadata mismatch" in item for item in findings))

    def test_production_holdout_binds_exact_claim_oracle_and_independent_roles(self) -> None:
        corpus = self.root / "production-holdout.bin"
        corpus.write_bytes(b"sealed-production-holdout")
        oracle_registry_sha = production_closure.sha256_bytes(b"oracle-registry-v1")
        mapping = [{"claim_id": "claim-route-equivalence", "oracle_id": "oracle-route-v1",
                    "oracle_version": "1.0.0"}]
        manifest = {"schema_version": "2.0", "holdout_id": "production-holdout-v2",
            "tenant_id": "tenant-001", "environment_class": "production",
            "corpus": {"path": str(corpus), "sha256": production_closure.sha256_bytes(corpus.read_bytes()),
                       "bytes": corpus.stat().st_size},
            "development_corpus_sha256": production_closure.sha256_bytes(b"development-corpus"),
            "transformation_author_ids": ["transformation-author"], "executor_ids": ["executor-holdout"],
            "verifier_ids": ["verifier-holdout"], "oracle_owner_ids": ["oracle-owner"],
            "oracle_registry_sha256": oracle_registry_sha, "claim_oracle_map": mapping,
            "development_partition_id": "development-partition", "holdout_partition_id": "holdout-partition"}
        manifest_path = self.root / "production-holdout-v2.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        manifest_sha = production_closure.sha256_bytes(production_closure.canonical_bytes(manifest))
        custodian = self.sign("holdout-custodian", {"holdout_id": "production-holdout-v2",
            "tenant_id": "tenant-001", "manifest_sha256": manifest_sha,
            "corpus_sha256": manifest["corpus"]["sha256"], "environment_class": "production",
            "oracle_registry_sha256": oracle_registry_sha,
            "claim_oracle_root": production_closure.canonical_digest(mapping),
            "development_partition_id": "development-partition", "holdout_partition_id": "holdout-partition"},
            suffix="production-holdout-v2")
        overlapping_payload = json.loads(self.trust_store.read_text(encoding="utf-8"))
        for actor in overlapping_payload["actors"]:
            if actor["actor_id"] == "verifier-holdout":
                actor["organization_id"] = "holdout-executor-org"
        overlapping_trust = self.trust_store.parent / "overlapping-production-trust-store.json"
        overlapping_trust.write_text(json.dumps(overlapping_payload), encoding="utf-8")
        with self.assertRaisesRegex(production_closure.ClosureError, "organizations overlap"):
            production_closure.register_holdout(
                self.workspace, manifest_path, custodian, overlapping_trust, (self.root.resolve(),))
        holdout = production_closure.register_holdout(
            self.workspace, manifest_path, custodian, self.trust_store, (self.root.resolve(),))
        execution = self.root / "production-holdout-execution.json"
        evidence = self.root / "production-holdout-claim.json"
        execution.write_text('{"state":"SUCCEEDED"}', encoding="utf-8")
        evidence.write_text('{"outcome":"PASS"}', encoding="utf-8")
        release = production_closure.sha256_bytes(b"release-v2")
        account = production_closure.sha256_bytes(b"account-v2")
        evidence_ref = {"path": str(evidence), "sha256": production_closure.sha256_bytes(evidence.read_bytes()),
                        "bytes": evidence.stat().st_size}
        oracle_bindings = {"result_id": "production-holdout-result-v2", "holdout_id": "production-holdout-v2",
            "tenant_id": "tenant-001", "claim_id": mapping[0]["claim_id"], "oracle_id": mapping[0]["oracle_id"],
            "oracle_version": mapping[0]["oracle_version"], "outcome": "PASS",
            "evidence_sha256": evidence_ref["sha256"], "target_release_sha256": release,
            "provider_account_sha256": account, "oracle_registry_sha256": oracle_registry_sha}
        oracle_attestation = self.sign("oracle-owner", oracle_bindings, suffix="production-holdout-oracle")
        result = {"schema_version": "2.0", "result_id": "production-holdout-result-v2",
            "holdout_id": "production-holdout-v2", "tenant_id": "tenant-001",
            "target_release_sha256": release, "provider_account_sha256": account,
            "execution_receipt": {"path": str(execution),
                "sha256": production_closure.sha256_bytes(execution.read_bytes()), "bytes": execution.stat().st_size},
            "decision": "PASS", "claim_results": [{**mapping[0], "outcome": "PASS", "evidence": evidence_ref,
                "oracle_attestation": oracle_attestation}],
            "started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:01:00Z"}
        result_path = self.root / "production-holdout-result-v2.json"
        result_path.write_text(json.dumps(result), encoding="utf-8")
        oracle_actor = production_closure.ActorTrustStore.load(self.trust_store).verify(
            oracle_attestation, "oracle-owner", oracle_bindings)
        normalized = [{"claim_id": mapping[0]["claim_id"], "outcome": "PASS",
                       "evidence": {"sha256": evidence_ref["sha256"], "bytes": evidence_ref["bytes"]},
                       "oracle_id": mapping[0]["oracle_id"], "oracle_version": mapping[0]["oracle_version"],
                       "oracle": oracle_actor}]
        root = production_closure.canonical_digest({"holdout_corpus_sha256": holdout["corpus"]["sha256"],
            "execution_receipt_sha256": result["execution_receipt"]["sha256"], "claim_results": normalized})
        bindings = {"result_id": result["result_id"], "holdout_id": result["holdout_id"],
            "tenant_id": result["tenant_id"],
            "manifest_sha256": production_closure.sha256_bytes(production_closure.canonical_bytes(result)),
            "evidence_root": root, "target_release_sha256": release,
            "provider_account_sha256": account, "decision": "PASS"}
        executor = self.sign("executor-holdout", bindings, suffix="production-holdout-executor")
        verifier = self.sign("verifier-holdout", {**bindings, "executor_id": "executor-holdout"},
                             suffix="production-holdout-verifier")
        recorded = production_closure.record_holdout_result(
            self.workspace, result_path, executor, verifier, self.trust_store, (self.root.resolve(),))
        self.assertTrue(recorded["oracle_bound"])
        self.assertEqual("oracle-owner", recorded["claim_results"][0]["oracle"]["actor_id"])

    def test_provider_receipt_is_bound_to_exact_account_region_adapter_and_operation(self) -> None:
        profile = self.exact_provider_profile(b"account-a")
        store = production_closure.ClosureStore(self.workspace)
        trust = production_closure.ActorTrustStore.load(self.trust_store)
        snapshot = {"schema_version": "1.0", "snapshot_id": "provider-snapshot", "tenant_id": "tenant-001",
                    "environment_class": "production", "authorization": {"actor_id": "data-owner",
                    "organization_id": "customer-data-org", "trust_store_sha256": trust.digest}}
        store.insert("snapshots", "provider-snapshot", ("provider-snapshot", "tenant-001", "production",
                     production_closure.sha256_bytes(b"provider-snapshot-manifest")), snapshot, "SNAPSHOT_REGISTERED")
        release = production_closure.sha256_bytes(b"release")
        holdout = {"schema_version": "2.0", "holdout_id": "provider-holdout",
            "tenant_id": "tenant-001", "environment_class": "production", "organization_bound": True,
            "actor_trust_store_sha256": trust.digest, "independence_organizations": {
                "transformation_authors": ["implementation-author-org"],
                "custodian": ["holdout-custodian-org"], "executors": ["holdout-executor-org"],
                "verifiers": ["holdout-verifier-org"], "oracle_owners": ["oracle-org"]}}
        store.insert("holdouts", "provider-holdout",
            ("provider-holdout", "tenant-001", production_closure.sha256_bytes(b"provider-holdout")),
            holdout, "HOLDOUT_SEALED")
        holdout_result = {"schema_version": "2.0", "result_id": "provider-holdout-result",
            "holdout_id": "provider-holdout", "tenant_id": "tenant-001", "decision": "PASS",
            "target_release_sha256": release, "provider_account_sha256": profile["account_binding_sha256"],
            "independent": True, "oracle_bound": True}
        store.insert("holdout_results", "provider-holdout-result",
            ("provider-holdout-result", "tenant-001", "provider-holdout", "PASS"),
            holdout_result, "HOLDOUT_RESULT_RECORDED")
        plan = {"schema_version": "2.0", "cutover_id": "provider-cutover", "tenant_id": "tenant-001",
            "snapshot_id": "provider-snapshot", "holdout_result_id": "provider-holdout-result",
            "target_key": "target", "target_release_sha256": release, "rollback_adapter_id": "fixture-provider",
            "rollback_operation": "undo", "preconditions": ["reconciled", "rollback-ready"], "provider": profile}
        plan_path = self.root / "provider-cutover-plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        approval = self.sign("approver", {"cutover_id": "provider-cutover", "tenant_id": "tenant-001",
            "plan_sha256": production_closure.sha256_bytes(production_closure.canonical_bytes(plan)),
            "snapshot_id": "provider-snapshot", "target_key": "target"}, suffix="provider-cutover-plan")
        cutover = production_closure.plan_cutover(self.workspace, plan_path, approval, self.trust_store,
                                                  (self.root.resolve(),))
        wrong_profile = {**profile, "region": "other-region-1"}
        wrong = self.provider_receipt(cutover, "PRECHECKED", "inspect", "wrong-region", provider=wrong_profile)
        wrong_auth = self.sign("operations-owner", {"cutover_id": "provider-cutover", "tenant_id": "tenant-001",
            "expected_state": "PLANNED", "target_state": "PRECHECKED", "fencing_token": 1,
            "receipt_sha256": wrong["sha256"]}, suffix="wrong-provider-receipt")
        with self.assertRaisesRegex(production_closure.ClosureError, "differs from the approved plan"):
            production_closure.transition_cutover(self.workspace, "provider-cutover", "PLANNED", "PRECHECKED", 1,
                wrong, wrong_auth, self.trust_store, (self.root.resolve(),))
        bad_control = self.provider_receipt(cutover, "PRECHECKED", "inspect", "bad-control")
        (self.root / "provider-control-least_privilege-bad-control.json").write_bytes(b"broadened-policy")
        bad_control_auth = self.sign("operations-owner", {"cutover_id": "provider-cutover",
            "tenant_id": "tenant-001", "expected_state": "PLANNED", "target_state": "PRECHECKED",
            "fencing_token": 1, "receipt_sha256": bad_control["sha256"]}, suffix="bad-provider-control")
        with self.assertRaisesRegex(production_closure.ClosureError, "byte/digest mismatch"):
            production_closure.transition_cutover(self.workspace, "provider-cutover", "PLANNED", "PRECHECKED", 1,
                bad_control, bad_control_auth, self.trust_store, (self.root.resolve(),))
        correct = self.provider_receipt(cutover, "PRECHECKED", "inspect", "correct-provider")
        correct_auth = self.sign("operations-owner", {"cutover_id": "provider-cutover", "tenant_id": "tenant-001",
            "expected_state": "PLANNED", "target_state": "PRECHECKED", "fencing_token": 1,
            "receipt_sha256": correct["sha256"]}, suffix="correct-provider-receipt")
        result = production_closure.transition_cutover(self.workspace, "provider-cutover", "PLANNED", "PRECHECKED", 1,
            correct, correct_auth, self.trust_store, (self.root.resolve(),))
        self.assertEqual("test-region-1", result["transitions"][0]["receipt"]["provider"]["region"])
        self.assertNotIn("path", result["transitions"][0]["receipt"])

    def test_production_soak_requires_realtime_seven_day_thresholded_independent_evidence(self) -> None:
        start = datetime.now(timezone.utc).replace(microsecond=0)
        profile = self.exact_provider_profile(b"account-b")
        trust = production_closure.ActorTrustStore.load(self.trust_store)
        cutover = {"schema_version": "2.0", "cutover_id": "soak-cutover", "tenant_id": "tenant-001",
                   "target_key": "target", "target_release_sha256": production_closure.sha256_bytes(b"release-b"),
                   "rollback_adapter_id": "fixture-provider", "rollback_operation": "undo",
                   "holdout_result_id": "production-holdout-result",
                   "environment_class": "production", "provider": profile, "state": "SUCCEEDED", "fencing_token": 5,
                   "plan_sha256": production_closure.sha256_bytes(b"soak-plan"),
                   "approval": {"actor_id": "approver", "organization_id": "customer-approval-org",
                                "trust_store_sha256": trust.digest},
                   "transitions": [{"to": "SUCCEEDED", "recorded_at": start.isoformat().replace("+00:00", "Z")} ]}
        store = production_closure.ClosureStore(self.workspace)
        holdout = {"schema_version": "2.0", "holdout_id": "production-holdout",
            "tenant_id": "tenant-001", "environment_class": "production", "organization_bound": True,
            "actor_trust_store_sha256": trust.digest, "independence_organizations": {
                "transformation_authors": ["implementation-author-org"],
                "custodian": ["holdout-custodian-org"], "executors": ["holdout-executor-org"],
                "verifiers": ["holdout-verifier-org"], "oracle_owners": ["oracle-org"]}}
        store.insert("holdouts", "production-holdout",
            ("production-holdout", "tenant-001", production_closure.sha256_bytes(b"production-holdout")),
            holdout, "HOLDOUT_SEALED")
        holdout_result = {"schema_version": "2.0", "result_id": "production-holdout-result",
            "holdout_id": "production-holdout", "tenant_id": "tenant-001", "decision": "PASS",
            "target_release_sha256": cutover["target_release_sha256"],
            "provider_account_sha256": profile["account_binding_sha256"],
            "independent": True, "oracle_bound": True}
        store.insert("holdout_results", "production-holdout-result",
            ("production-holdout-result", "tenant-001", "production-holdout", "PASS"),
            holdout_result, "HOLDOUT_RESULT_RECORDED")
        store.insert("cutovers", "soak-cutover", ("soak-cutover", "tenant-001", "target", "SUCCEEDED", 5,
                     cutover["plan_sha256"]), cutover, "CUTOVER_SUCCEEDED")
        clock = production_closure.ControlledTestClock(start + timedelta(seconds=1))
        with self.assertRaisesRegex(production_closure.ClosureError, "conservative telemetry policy"):
            production_closure.start_soak(self.workspace, "soak-cutover", "weak-soak", "production",
                (start + timedelta(seconds=1)).isoformat(), production_closure.PRODUCTION_MIN_SOAK_SECONDS,
                production_closure.PRODUCTION_MIN_SOAK_SECONDS, 0.99, 0.01, 1, clock=clock)
        telemetry_profile = {"schema_version": "1.0", "monitor_id": "fixture-monitor",
            "provider_account_sha256": profile["account_binding_sha256"],
            "metrics_source_sha256": production_closure.sha256_bytes(b"fixture-metrics-source"),
            "collection_interval_seconds": production_closure.PRODUCTION_MAX_GAP_SECONDS,
            "raw_evidence_required": True}
        production_closure.start_soak(self.workspace, "soak-cutover", "production-soak", "production",
            (start + timedelta(seconds=1)).isoformat(), production_closure.PRODUCTION_MIN_SOAK_SECONDS,
            production_closure.PRODUCTION_MAX_GAP_SECONDS, 0.999, 0.001, 28, clock=clock,
            telemetry_profile=telemetry_profile)
        for sequence in range(1, 29):
            observed = start + timedelta(seconds=1 + sequence * production_closure.PRODUCTION_MAX_GAP_SECONDS)
            observed_text = observed.isoformat().replace("+00:00", "Z")
            metrics = {"requests": 10_000, "errors": 1, "critical_failures": 0, "availability": 0.9999}
            telemetry = {"schema_version": "1.0", "monitor_id": "fixture-monitor",
                "run_id": "production-soak", "sequence": sequence, "observed_at": observed_text,
                "provider_account_sha256": profile["account_binding_sha256"],
                "metrics_source_sha256": telemetry_profile["metrics_source_sha256"],
                "source_event_id": f"fixture-event-{sequence}", "metrics": metrics}
            telemetry_path = self.root / f"telemetry-production-soak-{sequence}.json"
            telemetry_path.write_text(json.dumps(telemetry), encoding="utf-8")
            telemetry_ref = {"path": str(telemetry_path),
                "sha256": production_closure.sha256_bytes(telemetry_path.read_bytes()),
                "bytes": telemetry_path.stat().st_size}
            metrics_sha = production_closure.canonical_digest({"metrics": metrics,
                "telemetry_receipt_sha256": telemetry_ref["sha256"],
                "telemetry_profile_sha256": production_closure.canonical_digest(telemetry_profile)})
            heartbeat = self.sign("operations-owner", {"run_id": "production-soak", "sequence": sequence,
                "observed_at": observed_text, "metrics_sha256": metrics_sha},
                suffix=f"production-soak-{sequence}")
            clock.set(observed)
            if sequence == 1:
                with self.assertRaisesRegex(production_closure.ClosureError, "raw telemetry receipt"):
                    production_closure.observe_soak(self.workspace, "production-soak", sequence, observed_text,
                                                    metrics, heartbeat, self.trust_store, clock=clock)
            production_closure.observe_soak(self.workspace, "production-soak", sequence, observed_text,
                                            metrics, heartbeat, self.trust_store, clock=clock,
                                            telemetry_receipt=telemetry_ref, roots=(self.root.resolve(),))
        running = store.row("soak_runs", "production-soak")
        root = production_closure.soak_evidence_root(running)
        finished = start + timedelta(seconds=2 + production_closure.PRODUCTION_MIN_SOAK_SECONDS)
        finished_text = finished.isoformat().replace("+00:00", "Z")
        final = self.sign("verifier-production", {"run_id": "production-soak", "sequence": 29,
            "observed_at": finished_text, "target_state": "PASSED", "evidence_root": root},
            suffix="production-soak-final")
        clock.set(finished)
        result = production_closure.finish_soak(self.workspace, "production-soak", 29, finished_text,
                                                final, self.trust_store, clock=clock)
        self.assertEqual("PASSED", result["state"])
        self.assertEqual("engineering-only", result["evidence_class"])
        self.assertTrue(result["production_protocol_simulated"])
        self.assertFalse(result["real_seven_day_elapsed"])
        legacy_report = {"schema_version": "1.0", "assessment_id": "legacy-production-assessment",
            "tenant_id": "tenant-001", "scope": "synthetic-production-protocol-test", "decision": "CERTIFIED",
            "evidence_root": result["evidence_root"], "limitations": ["local synthetic clock"],
            "issued_at": start.isoformat().replace("+00:00", "Z"), "expires_at": "2099-01-01T00:00:00Z"}
        legacy_path = self.root / "legacy-production-assessment.json"
        legacy_path.write_text(json.dumps(legacy_report), encoding="utf-8")
        legacy_auth = self.sign("independent-certifier", {"assessment_id": "legacy-production-assessment",
            "tenant_id": "tenant-001", "report_sha256": production_closure.sha256_bytes(
                production_closure.canonical_bytes(legacy_report)), "evidence_root": result["evidence_root"],
            "decision": "CERTIFIED"}, suffix="legacy-production-assessment")
        with self.assertRaisesRegex(production_closure.ClosureError, "exact run, release, and provider account"):
            production_closure.import_assessment(self.workspace, legacy_path, legacy_auth, self.trust_store,
                                                 (self.root.resolve(),))
        exact_report = {**legacy_report, "schema_version": "2.0", "assessment_id": "exact-production-assessment",
            "run_id": "production-soak", "cutover_id": "soak-cutover",
            "target_release_sha256": cutover["target_release_sha256"],
            "provider_account_sha256": profile["account_binding_sha256"]}
        exact_path = self.root / "exact-production-assessment.json"
        exact_path.write_text(json.dumps(exact_report), encoding="utf-8")
        external_store, authority_policy, authority_approval = self.external_certification_authority("tenant-001")
        exact_auth = self.sign("external-certifier", {"assessment_id": "exact-production-assessment",
            "tenant_id": "tenant-001", "report_sha256": production_closure.sha256_bytes(
                production_closure.canonical_bytes(exact_report)), "evidence_root": result["evidence_root"],
            "decision": "CERTIFIED"}, suffix="exact-production-assessment")
        revoked_policy = json.loads(authority_policy.read_text(encoding="utf-8"))
        revoked_policy["revoked"] = True
        revoked_policy_path = authority_policy.parent / "revoked-policy.json"
        revoked_policy_path.write_text(json.dumps(revoked_policy), encoding="utf-8")
        with self.assertRaisesRegex(production_closure.ClosureError, "revocation state"):
            production_closure.import_assessment(self.workspace, exact_path, exact_auth, external_store,
                (self.root.resolve(),), authority_policy_path=revoked_policy_path,
                authority_approval=authority_approval, internal_trust_path=self.trust_store)
        imported = production_closure.import_assessment(self.workspace, exact_path, exact_auth, external_store,
            (self.root.resolve(),), authority_policy_path=authority_policy,
            authority_approval=authority_approval, internal_trust_path=self.trust_store)
        self.assertFalse(imported["certified"])
        self.assertTrue(imported["external_authority_authorized"])
        readiness = production_closure.readiness(self.workspace, "tenant-001")
        self.assertFalse(readiness["certified"])
        self.assertEqual("NOT_RUN", readiness["external_runtime_status"])

        expired_started = finished + timedelta(seconds=1)
        expired_started_text = expired_started.isoformat().replace("+00:00", "Z")
        clock.set(expired_started)
        production_closure.start_soak(self.workspace, "soak-cutover", "expired-production-soak", "production",
            expired_started_text, production_closure.PRODUCTION_MIN_SOAK_SECONDS,
            production_closure.PRODUCTION_MAX_GAP_SECONDS, 0.999, 0.001, 28, clock=clock,
            telemetry_profile=telemetry_profile)
        expired_at = expired_started + timedelta(seconds=production_closure.PRODUCTION_MAX_GAP_SECONDS + 1)
        expired_at_text = expired_at.isoformat().replace("+00:00", "Z")
        clock.set(expired_at)
        watchdog = production_closure.soak_status(self.workspace, "expired-production-soak", clock)
        self.assertTrue(watchdog["heartbeat_overdue"])
        timeout_payload = {"run_id": "expired-production-soak", "sequence": 1,
            "observed_at": expired_at_text, "target_state": "FAILED",
            "evidence_root": production_closure.soak_evidence_root(
                store.row("soak_runs", "expired-production-soak")),
            "heartbeat_deadline": watchdog["heartbeat_deadline"], "reason": "HEARTBEAT_TIMEOUT"}
        timeout_attestation = self.sign("verifier-production", timeout_payload, suffix="expired-soak")
        expired = production_closure.expire_soak(self.workspace, "expired-production-soak", expired_at_text,
                                                  timeout_attestation, self.trust_store, clock=clock)
        self.assertEqual("FAILED", expired["state"])
        self.assertEqual("HEARTBEAT_TIMEOUT", expired["terminal_reason"])
        revival_at = expired_at + timedelta(seconds=1)
        revival_text = revival_at.isoformat().replace("+00:00", "Z")
        clock.set(revival_at)
        revival = self.sign("verifier-production", {"run_id": "expired-production-soak", "sequence": 2,
            "observed_at": revival_text, "target_state": "FAILED",
            "evidence_root": production_closure.soak_evidence_root(expired)}, suffix="expired-soak-revival")
        with self.assertRaisesRegex(production_closure.ClosureError, "sequence/state conflict"):
            production_closure.finish_soak(self.workspace, "expired-production-soak", 2, revival_text,
                                           revival, self.trust_store, clock=clock)
    def test_24_concurrent_commands_have_no_evidence_crosstalk(self) -> None:
        self.prepare(1)

        def command(index: int) -> dict:
            return runtime.run_command(
                self.workspace, 1, f"command-{index}", [sys.executable, "-c", f"print('value-{index}')"], ".", f"executor-{index}", 30,
                claim_type="test", claim_index=0,
            )

        with ThreadPoolExecutor(max_workers=12) as pool:
            records = list(pool.map(command, range(24)))
        self.assertEqual(24, len({item["evidence_id"] for item in records}))
        names = set()
        for record in records:
            envelope_path = self.workspace / record["object"]["object_path"]
            envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
            names.add(envelope["observations"][0]["name"])
            execution_path = self.workspace / "objects" / "sha256" / envelope["subject"]["sha256"].split(":", 1)[1]
            execution = json.loads(execution_path.read_text(encoding="utf-8"))
            self.assertIn(execution["name"].replace("command", "value"), execution["stdout"])
        self.assertEqual({f"command-{index}" for index in range(24)}, names)
        self.assertEqual([], runtime.state_store(self.workspace).verify_event_chain())

    def test_transaction_rolls_back_after_injected_event_failure(self) -> None:
        self.prepare(1)
        envelope = self.envelope_file(1, "output", 0)
        with mock.patch.object(runtime.TransactionStore, "_append_event", side_effect=RuntimeError("injected crash")):
            with self.assertRaisesRegex(RuntimeError, "injected crash"):
                runtime.record_evidence(
                    self.workspace, 1, envelope, kind="artifact", claim_type="output", claim_index=0,
                    producer_id="executor-dev", producer_role="executor", environment="clean-local-fixture", outcome="PASS", external=False,
                )
        store = runtime.state_store(self.workspace)
        self.assertEqual([], store.evidence(1))
        self.assertEqual([], store.verify_event_chain())
        evidence = runtime.record_evidence(
            self.workspace, 1, envelope, kind="artifact", claim_type="output", claim_index=0,
            producer_id="executor-dev", producer_role="executor", environment="clean-local-fixture", outcome="PASS", external=False,
        )
        self.assertEqual(1, len(store.evidence(1)))
        self.assertTrue(evidence["evidence_id"].startswith("evidence-"))

    def test_committed_authority_repairs_a_missing_json_mirror(self) -> None:
        self.prepare(1)
        envelope = self.envelope_file(1, "output", 0)
        first = runtime.record_evidence(
            self.workspace, 1, envelope, kind="artifact", claim_type="output", claim_index=0,
            producer_id="executor-dev", producer_role="executor", environment="clean-local-fixture", outcome="PASS", external=False,
        )
        mirror = runtime.batch_dir(self.workspace, 1) / "evidence" / f"{first['evidence_id']}.json"
        mirror.unlink()
        self.assertEqual(1, len(runtime.state_store(self.workspace).evidence(1)))
        second = runtime.record_evidence(
            self.workspace, 1, envelope, kind="artifact", claim_type="output", claim_index=0,
            producer_id="executor-dev", producer_role="executor", environment="clean-local-fixture", outcome="PASS", external=False,
        )
        self.assertEqual(first["evidence_id"], second["evidence_id"])
        self.assertEqual(first, runtime.load_json(mirror))

    def test_command_rejects_source_drift_from_bound_snapshot(self) -> None:
        self.prepare(1)
        (self.source / "Main.java").write_text("final class Main { int changed; }\n", encoding="utf-8")
        with self.assertRaisesRegex(runtime.RuntimeFailure, "source has changed"):
            runtime.run_command(
                self.workspace, 1, "must-not-run", [sys.executable, "-c", "print('unexpected')"], ".", "executor-a", 30,
                claim_type="test", claim_index=0,
            )
        self.assertEqual([], runtime.state_store(self.workspace).evidence(1))

    def test_gate_snapshot_detects_input_change_but_not_its_own_write(self) -> None:
        self.prepare(1)
        first = runtime.evaluate_gate(self.workspace, 1)
        second = runtime.evaluate_gate(self.workspace, 1)
        self.assertEqual(first["evaluated_revision"], second["evaluated_revision"])
        stale = dict(second)
        self.record_claim(1, "output", 0)
        with self.assertRaisesRegex(runtime.StoreConflict, "input revision changed"):
            runtime.state_store(self.workspace).record_gate(stale)

    def test_cli_command_redacts_secret_in_execution_subject(self) -> None:
        self.prepare(1)
        completed = subprocess.run(
            [
                sys.executable, str(RUNTIME_PATH), "run-command", "--workspace", str(self.workspace), "--batch", "1",
                "--name", "redaction-fixture", "--argv-json", json.dumps([sys.executable, "-c", "print('token=supersecretvalue')", "--token", "anothersecretvalue"]),
                "--producer-id", "executor-a",
            ],
            check=False, capture_output=True, text=True, env={**os.environ, "SOURCE_DATE_EPOCH": "1700000000"},
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        record = json.loads(completed.stdout)
        envelope = json.loads((self.workspace / record["object"]["object_path"]).read_text(encoding="utf-8"))
        execution_path = self.workspace / "objects" / "sha256" / envelope["subject"]["sha256"].split(":", 1)[1]
        execution = json.loads(execution_path.read_text(encoding="utf-8"))
        self.assertIn("token=[REDACTED]", execution["stdout"])
        self.assertNotIn("supersecretvalue", execution["stdout"])
        self.assertNotIn("anothersecretvalue", json.dumps(execution))

    def test_execution_plan_runs_argv_only_and_rejects_policy_weakening(self) -> None:
        self.prepare(1)
        plan_path = runtime.batch_dir(self.workspace, 1) / "execution-plan.json"
        plan = runtime.load_json(plan_path)
        plan["steps"] = [{
            "step_id": "test-0", "name": "real-process", "claim_type": "test", "claim_index": 0,
            "argv": [sys.executable, "-c", "print('ok')"], "cwd": ".", "producer_id": "executor-a", "timeout_seconds": 30,
        }]
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        result = runtime.execute_plan(self.workspace, 1, plan_path)
        self.assertEqual("PASS", result["decision"])
        plan["execution_policy"]["shell"] = True
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaisesRegex(runtime.RuntimeFailure, "may not be weakened"):
            runtime.execute_plan(self.workspace, 1, plan_path)

    def test_certificate_import_is_disabled_without_package_trust_root(self) -> None:
        self.prepare(1)
        dummy = self.root / "dummy.json"
        dummy.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(runtime.RuntimeFailure, "disabled by the package-owned trust policy"):
            runtime.import_certificate(self.workspace, 1, dummy, dummy)

    def test_installed_runtime_is_relocatable(self) -> None:
        destination = self.root / "installed-skills"
        completed = subprocess.run(
            [str(PACKAGE_ROOT / "install.sh"), str(destination)], check=False, capture_output=True, text=True,
            env={**os.environ, "SOURCE_DATE_EPOCH": "1700000000"},
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        installed = destination / ".repository-migration-platform-runtime"
        self.assertTrue((installed / "transaction_store.py").is_file())
        self.assertTrue((installed / "actor_trust.py").is_file())
        self.assertTrue((installed / "oracle_registry.py").is_file())
        self.assertTrue((installed / "domain_executors.py").is_file())
        self.assertTrue((installed / "domain_handlers.py").is_file())
        self.assertTrue((installed / "oracle-registry.json").is_file())
        self.assertTrue((installed / "domain-executor-registry.json").is_file())
        self.assertTrue((installed / "trust-policy.json").is_file())
        catalog = subprocess.run(
            [sys.executable, str(installed / "migration_platform.py"), "catalog"], check=False, capture_output=True, text=True,
            env={**os.environ, "SOURCE_DATE_EPOCH": "1700000000"},
        )
        self.assertEqual(0, catalog.returncode, catalog.stdout + catalog.stderr)
        self.assertEqual(38, len(json.loads(catalog.stdout)["batches"]))


if __name__ == "__main__":
    unittest.main()

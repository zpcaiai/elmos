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
            })
        self.trust_store = self.actor_directory / "trust-store.json"
        self.trust_store.write_text(json.dumps({
            "schema_version": "1.0",
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
                "corpus_role": corpus_role,
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
    ) -> dict:
        expected_producer, producer_role, expected_verifier = self.corpus_actors(corpus_role)
        producer = producer or expected_producer
        verifier = verifier or expected_verifier
        evidence = runtime.record_evidence(
            self.workspace,
            batch,
            self.envelope_file(
                batch, claim_type, claim_index, producer=producer, role=producer_role,
                subject=subject, suffix=suffix, corpus_role=corpus_role,
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

    def domain_result_file(self, *, corpus_role: str = "development", independent: bool = False) -> Path:
        obligation = runtime.OracleRegistry.load().resolve(1, "output", 0)
        raw_file = self.root / f"native-tool-{corpus_role}.log"
        raw_file.write_text("native tool executed against the exact fixture\n", encoding="utf-8")
        raw_bytes = raw_file.read_bytes()
        payload = {
            "schema_version": "1.0",
            "batch": 1,
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
            "toolchain": [{
                "name": "fixture-native-inspector",
                "version": "1.0.0",
                "argv_sha256": runtime.sha256_bytes(b"package-owned-fixture-command"),
                "exit_code": 0,
                "evidence_role": "native-execution-log",
            }],
            "assertions": [{
                "name": "repository-snapshot-is-complete",
                "outcome": "PASS",
                "detail": "the native execution log is byte-bound to this result",
            }],
            "raw_evidence": [{
                "path": str(raw_file),
                "sha256": runtime.sha256_bytes(raw_bytes),
                "bytes": len(raw_bytes),
                "role": "native-execution-log",
            }],
            "decision": "PASS",
            "limitations": [],
        }
        result_file = self.root / f"domain-result-{corpus_role}.json"
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

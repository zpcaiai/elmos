from __future__ import annotations

import base64
import datetime as dt
import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from elmos_etgb.attestation import unsigned_payload
from elmos_etgb.canonical import canonical_json, digest_json
from elmos_etgb.campaign import merge_release_results
from elmos_etgb.evidence import EvidenceStore
from elmos_etgb.external_harness import ExternalExecutionContext, ExternalHarnessError, ExternalHarnessRouter
from elmos_etgb.orchestrator import build_plan
from elmos_etgb.planner import select_plan_shard, stable_shards, validate_plan
from elmos_etgb.runner import execute_case


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "skills/subskills/elmos-etgb-sota-skills-package-v1.1.0"


class ExternalHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        self.now = now
        self.private_key = Ed25519PrivateKey.generate()
        public_key = self.private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        trust_store = {
            "schema_version": "1.0",
            "keys": [
                {
                    "key_id": "harness-key-1",
                    "algorithm": "ed25519",
                    "status": "active",
                    "record_types": ["adapter-execution"],
                    "public_key": base64.urlsafe_b64encode(public_key).decode().rstrip("="),
                    "not_before": (now - dt.timedelta(hours=1)).isoformat(),
                    "not_after": (now + dt.timedelta(hours=2)).isoformat(),
                }
            ],
        }
        self.trust_store = trust_store
        (self.root / "trust.json").write_text(json.dumps(trust_store), encoding="utf-8")
        self.config = {
            "schema_version": "1.0",
            "trust_store": "trust.json",
            "policy": {
                "request_timeout_seconds": 30,
                "max_attempts": 3,
                "initial_backoff_ms": 0,
                "max_request_bytes": 1048576,
                "max_response_bytes": 1048576,
                "allow_loopback_http": False,
                "allow_environment_proxy": False,
            },
            "adapters": {
                "external-transformation-harness": {
                    "endpoint": "https://harness.example.test/v1/cases:execute",
                    "executor_id": "executor-1",
                    "auth_token_env": "ETGB_TEST_TOKEN",
                }
            },
        }
        (self.root / "harness.json").write_text(json.dumps(self.config), encoding="utf-8")
        self.context = ExternalExecutionContext(
            tenant_id="tenant-a",
            project_id="project-a",
            task_id="task-a",
            candidate_digest="sha256:" + "a" * 64,
            plan_digest="sha256:" + "b" * 64,
            environment_id="environment-a",
            authority_id="authority-a",
            owner_id="worker-a",
            fencing_token=7,
            checkpoint_digest="sha256:" + "c" * 64,
        )
        self.case = {
            "id": "EXTERNAL-001",
            "business_line": "cross-language",
            "priority": "P0",
            "level": "L3",
            "profiles": ["release"],
            "execution": {"adapter": "external-transformation-harness"},
        }

    def signed_response(self, request: dict[str, Any], *, request_digest: str | None = None) -> dict[str, Any]:
        payload = {
            "schema_version": "1.0",
            "adapter": request["adapter"],
            "request_digest": request_digest or request["request_digest"],
            "bindings": request["context"],
            "status": "passed",
            "oracle_results": [{"type": "semantic-equivalence", "critical": True, "passed": True}],
            "evidence": {
                "manifest_digest": "sha256:" + "d" * 64,
                "artifact_digests": ["sha256:" + "e" * 64],
                "environment_digest": "sha256:" + "1" * 64,
                "toolchain_digest": "sha256:" + "2" * 64,
                "raw_evidence_roles": ["build-log", "oracle-output"],
            },
            "cost": {"token_input": 10, "token_output": 2, "credit_usd": 0.01, "wall_clock_ms": 50},
            "silent_semantic_error": False,
            "failure_class": None,
            "retryable": False,
        }
        record = {
            "schema_version": "1.0",
            "record_type": "adapter-execution",
            "payload": payload,
            "issuer_id": "executor-1",
            "key_id": "harness-key-1",
            "algorithm": "ed25519",
            "issued_at": (self.now - dt.timedelta(minutes=1)).isoformat(),
            "expires_at": (self.now + dt.timedelta(hours=1)).isoformat(),
        }
        record["signature"] = base64.urlsafe_b64encode(self.private_key.sign(canonical_json(unsigned_payload(record)))).decode().rstrip("=")
        return record

    def test_signed_external_result_is_bound_and_persisted(self) -> None:
        def transport(_endpoint: Any, body: bytes, headers: Any, _policy: Any) -> dict[str, Any]:
            self.assertEqual(headers["Authorization"], "Bearer opaque-test-token")
            request = json.loads(body)
            self.assertEqual(request["context"]["tenant_id"], "tenant-a")
            self.assertEqual(request["context"]["candidate_digest"], self.context.candidate_digest)
            return self.signed_response(request)

        router = ExternalHarnessRouter.load(self.root / "harness.json", transport=transport, environ={"ETGB_TEST_TOKEN": "opaque-test-token"})
        store = EvidenceStore(self.root / "evidence")
        result = execute_case(self.case, PACKAGE, run_id="run-1", external_router=router, external_context=self.context, store=store)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["claim_state"], "success")
        self.assertTrue(result["evidence"]["external_harness"]["signature_valid"])
        self.assertEqual(result["cost"]["credit_usd"], 0.01)
        roles = {item["role"] for item in result["evidence"]["artifacts"]}
        self.assertIn("external-harness-signed-response", roles)

    def test_capability_preflight_requires_exact_credentials_without_exposing_them(self) -> None:
        required = {"external-transformation-harness"}
        ready = ExternalHarnessRouter.load(
            self.root / "harness.json",
            environ={"ETGB_TEST_TOKEN": "opaque-test-token"},
        ).capability_report(required)
        self.assertEqual(ready["status"], "READY_FOR_EXTERNAL_EXECUTION_CONFIG")
        self.assertEqual(ready["configured_executor_ids"], ["executor-1"])
        self.assertNotIn("opaque-test-token", json.dumps(ready))
        production = ExternalHarnessRouter.load(
            self.root / "harness.json",
            environ={"ETGB_TEST_TOKEN": "opaque-test-token"},
        ).capability_report(required, require_production_transport=True)
        self.assertEqual(production["status"], "BLOCKED")
        self.assertEqual(production["missing_ca_bundle_adapters"], ["external-transformation-harness"])
        self.assertEqual(production["missing_mtls_adapters"], ["external-transformation-harness"])

        blocked = ExternalHarnessRouter.load(
            self.root / "harness.json",
            environ={},
        ).capability_report(required)
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertEqual(blocked["missing_credential_adapters"], ["external-transformation-harness"])

    def test_v20_external_adapter_uses_the_same_signed_protocol(self) -> None:
        config = json.loads(json.dumps(self.config))
        endpoint = config["adapters"].pop("external-transformation-harness")
        config["adapters"]["external-identity-access-harness"] = endpoint
        path = self.root / "harness-v20.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        case = json.loads(json.dumps(self.case))
        case["execution"]["adapter"] = "external-identity-access-harness"

        def transport(_endpoint: Any, body: bytes, _headers: Any, _policy: Any) -> dict[str, Any]:
            return self.signed_response(json.loads(body))

        router = ExternalHarnessRouter.load(
            path,
            transport=transport,
            environ={"ETGB_TEST_TOKEN": "opaque-test-token"},
        )
        result = execute_case(case, PACKAGE, run_id="run-v20", external_router=router, external_context=self.context)
        self.assertEqual(result["status"], "passed")

    def test_signed_but_misbound_response_fails_closed(self) -> None:
        def transport(_endpoint: Any, body: bytes, _headers: Any, _policy: Any) -> dict[str, Any]:
            return self.signed_response(json.loads(body), request_digest="sha256:" + "f" * 64)

        router = ExternalHarnessRouter.load(self.root / "harness.json", transport=transport, environ={"ETGB_TEST_TOKEN": "opaque-test-token"})
        result = execute_case(self.case, PACKAGE, run_id="run-1", external_router=router, external_context=self.context)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["failure_class"], "evidence/integrity")
        self.assertFalse(result["evidence"]["integrity_valid"])
        self.assertNotEqual(result["claim_state"], "success")

    def test_transient_transport_retry_reuses_exact_request(self) -> None:
        calls: list[str] = []

        def transport(_endpoint: Any, body: bytes, _headers: Any, _policy: Any) -> dict[str, Any]:
            request = json.loads(body)
            calls.append(request["request_digest"])
            if len(calls) == 1:
                raise ExternalHarnessError("temporary", failure_class="environment/dependency", retryable=True)
            return self.signed_response(request)

        router = ExternalHarnessRouter.load(self.root / "harness.json", transport=transport, environ={"ETGB_TEST_TOKEN": "opaque-test-token"})
        result = execute_case(self.case, PACKAGE, run_id="run-1", external_router=router, external_context=self.context)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(set(calls)), 1)
        self.assertEqual(result["evidence"]["external_harness"]["attempts"], 2)

    def test_config_rejects_inline_secret_and_insecure_endpoint(self) -> None:
        bad = json.loads(json.dumps(self.config))
        bad["adapters"]["external-transformation-harness"]["token"] = "secret"
        (self.root / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
        with self.assertRaises(ValueError):
            ExternalHarnessRouter.load(self.root / "bad.json", environ={"ETGB_TEST_TOKEN": "token"})
        bad = json.loads(json.dumps(self.config))
        bad["adapters"]["external-transformation-harness"]["endpoint"] = "http://harness.example.test/run"
        (self.root / "bad-http.json").write_text(json.dumps(bad), encoding="utf-8")
        with self.assertRaises(ValueError):
            ExternalHarnessRouter.load(self.root / "bad-http.json", environ={"ETGB_TEST_TOKEN": "token"})

    def test_complete_release_plan_partitions_all_46664_cases_exactly(self) -> None:
        candidate_digest = "sha256:" + "a" * 64
        plan = build_plan(PACKAGE, profile="release", shard_count=64, candidate_digest=candidate_digest)
        self.assertEqual(len(plan["case_ids"]), 46664)
        self.assertEqual(validate_plan(plan), [])
        selected = set().union(*(set(shard["case_ids"]) for shard in plan["shards"]))
        self.assertEqual(selected, set(plan["case_ids"]))
        self.assertEqual(select_plan_shard(plan, plan["shards"][0]["shard_id"]), set(plan["shards"][0]["case_ids"]))
        tampered = json.loads(json.dumps(plan))
        tampered["shards"][0]["case_ids"].pop()
        self.assertTrue(validate_plan(tampered))

    def test_release_result_merge_reverifies_signed_outcome(self) -> None:
        plan = {
            "schema_version": "1.1",
            "profile": "release",
            "selection_policy": "test-exact-scope",
            "candidate_digest": self.context.candidate_digest,
            "case_ids": [self.case["id"]],
        }
        plan["scope_digest"] = "sha256:" + digest_json(plan)
        plan["shards"] = stable_shards(plan["case_ids"], 1, scope_digest=plan["scope_digest"], candidate_digest=plan["candidate_digest"])
        plan["plan_digest"] = "sha256:" + digest_json(plan)
        context = replace(self.context, plan_digest=plan["plan_digest"])

        def transport(_endpoint: Any, body: bytes, _headers: Any, _policy: Any) -> dict[str, Any]:
            return self.signed_response(json.loads(body))

        router = ExternalHarnessRouter.load(self.root / "harness.json", transport=transport, environ={"ETGB_TEST_TOKEN": "opaque-test-token"})
        result = execute_case(self.case, PACKAGE, run_id="run-merge", external_router=router, external_context=context)
        shard = self.root / "shard.jsonl"
        shard.write_text(json.dumps(result) + "\n", encoding="utf-8")
        package = self.root / "package"
        (package / "schemas").mkdir(parents=True)
        (package / "suites").mkdir()
        shutil.copyfile(PACKAGE / "schemas/run-result.schema.json", package / "schemas/run-result.schema.json")
        (package / "suites/suite.yaml").write_text("case_files:\n  - suites/cases.jsonl\n", encoding="utf-8")
        (package / "suites/cases.jsonl").write_text(json.dumps(self.case) + "\n", encoding="utf-8")
        merged, receipt = merge_release_results(package, plan, [shard], candidate_digest=self.context.candidate_digest, trust_store=self.trust_store)
        self.assertEqual(receipt["status"], "MERGED", receipt["errors"])
        self.assertEqual(len(merged), 1)
        tampered = json.loads(json.dumps(result))
        tampered["status"] = "failed"
        shard.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
        _, blocked = merge_release_results(package, plan, [shard], candidate_digest=self.context.candidate_digest, trust_store=self.trust_store)
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertTrue(any("signed external outcome mismatch" in error for error in blocked["errors"]))


if __name__ == "__main__":
    unittest.main()

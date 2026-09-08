from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from elmos_repository_orchestrator.cli import main
from elmos_repository_orchestrator.contracts import ContractError, sha256_payload
from elmos_repository_orchestrator.external_gate import (
    OPERATIONS,
    certificate_signing_bytes,
    evaluate_production_certification,
    external_preflight,
    validate_external_plan,
    validate_external_report,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = PACKAGE_ROOT / "config" / "ai-external-gate-plan.json"


def load_plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class ExternalGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="elmos-ai-gate-test-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def report(self, *, status: str = "PASS") -> dict:
        operations = {}
        plan = load_plan()
        for name in OPERATIONS:
            path = self.root / f"{name}.json"
            path.write_text(json.dumps({"operation": name, "observed": True}), encoding="utf-8")
            operations[name] = {
                "status": status,
                "evidence_role": plan["operations"][name]["evidence_role"],
                "executor_actor": f"executor-{name}",
                "verifier_actor": f"verifier-{name}",
                "authorization_id": f"authorization-{name}",
                "synthetic": False,
                "evidence": [{"path": path.name, "sha256": file_digest(path)}],
            }
        return {
            "schema_version": 1,
            "gate_id": plan["gate_id"],
            "repository_revision": "a" * 40,
            "artifact_digest": "sha256:" + "b" * 64,
            "environment": "production-cn-1",
            "producer_actor": plan["producer_actor"],
            "generated_at": "2026-09-08T08:00:00Z",
            "operations": operations,
            "production_certification": "NOT_CERTIFIED",
        }

    def test_checked_in_plan_is_valid_and_preflight_is_fail_closed(self) -> None:
        plan = validate_external_plan(load_plan())
        self.assertEqual(set(plan["operations"]), set(OPERATIONS))
        result = external_preflight(plan, environ={})
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(set(result["external_execution"].values()), {"NOT_RUN"})
        self.assertEqual(result["production_certification"], "NOT_CERTIFIED")
        self.assertIn("elasticsearch", result["blockers"])
        self.assertIn("trusted_public_key_sha256_not_pinned", result["blockers"]["independent_verification"])

    def test_preflight_only_becomes_ready_with_all_bindings_and_pinned_trust(self) -> None:
        plan = load_plan()
        plan["certification"]["trusted_public_key_sha256"] = "sha256:" + "1" * 64
        plan["certification"]["certifier_organization"] = "independent-assurance-lab"
        environment = {
            name: "configured"
            for operation in plan["operations"].values()
            for name in operation["required_env"]
        }
        result = external_preflight(plan, environ=environment)
        self.assertEqual(result["status"], "READY")
        self.assertEqual(set(result["external_execution"].values()), {"NOT_RUN"})

    def test_plan_rejects_inline_secrets_predeclared_results_and_self_certification(self) -> None:
        plan = load_plan()
        plan["api_key"] = "not-allowed"
        with self.assertRaisesRegex(ContractError, "environment variable"):
            validate_external_plan(plan)
        plan = load_plan()
        plan["operations"]["dify"]["status"] = "PASS"
        with self.assertRaisesRegex(ContractError, "must start as NOT_RUN"):
            validate_external_plan(plan)
        plan = load_plan()
        plan["certification"]["certifier_actor"] = plan["producer_actor"]
        with self.assertRaisesRegex(ContractError, "must differ"):
            validate_external_plan(plan)

    def test_report_rejects_self_verification_and_producer_certification(self) -> None:
        report = self.report()
        report["operations"]["dify"]["verifier_actor"] = report["operations"]["dify"]["executor_actor"]
        with self.assertRaisesRegex(ContractError, "must differ"):
            validate_external_report(load_plan(), report, evidence_root=self.root)
        report = self.report()
        report["production_certification"] = "CERTIFIED"
        with self.assertRaisesRegex(ContractError, "only state NOT_CERTIFIED"):
            validate_external_report(load_plan(), report, evidence_root=self.root)

    def test_report_rejects_tampered_and_symlink_evidence(self) -> None:
        report = self.report()
        (self.root / "dify.json").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "digest mismatch"):
            validate_external_report(load_plan(), report, evidence_root=self.root)

        report = self.report()
        target = self.root / "target.json"
        target.write_text("outside authority", encoding="utf-8")
        link = self.root / "dify-link.json"
        link.symlink_to(target)
        report["operations"]["dify"]["evidence"] = [{"path": link.name, "sha256": file_digest(target)}]
        with self.assertRaisesRegex(ContractError, "non-symlink"):
            validate_external_report(load_plan(), report, evidence_root=self.root)

    def test_non_pass_operation_blocks_without_requiring_a_certificate(self) -> None:
        report = self.report()
        report["operations"]["model_provider"]["status"] = "UNKNOWN"
        result = evaluate_production_certification(load_plan(), report, evidence_root=self.root)
        self.assertFalse(result["certified"])
        self.assertEqual(result["production_certification"], "NOT_CERTIFIED")
        self.assertIn("model_provider:UNKNOWN", result["reasons"])

    def test_all_pass_still_requires_an_independent_certificate(self) -> None:
        result = evaluate_production_certification(load_plan(), self.report(), evidence_root=self.root)
        self.assertFalse(result["certified"])
        self.assertEqual(result["reasons"], ["independent_certificate_missing"])

    def test_exact_fresh_trusted_signature_is_required_for_certification(self) -> None:
        private_key = self.root / "private.pem"
        public_key = self.root / "public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(private_key)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
            check=True,
            capture_output=True,
        )
        plan = load_plan()
        plan["certification"]["trusted_public_key_sha256"] = file_digest(public_key)
        plan["certification"]["certifier_organization"] = "independent-assurance-lab"
        report = self.report()
        _, evidence = validate_external_report(plan, report, evidence_root=self.root)
        now = datetime(2026, 9, 8, 8, 30, tzinfo=timezone.utc)
        certificate = {
            "schema_version": 1,
            "gate_id": plan["gate_id"],
            "decision": "CERTIFIED",
            "report_digest": sha256_payload(report),
            "evidence_set_digest": sha256_payload(evidence),
            "repository_revision": report["repository_revision"],
            "artifact_digest": report["artifact_digest"],
            "certifier_actor": plan["certification"]["certifier_actor"],
            "certifier_organization": plan["certification"]["certifier_organization"],
            "certified_at": "2026-09-08T08:29:00Z",
            "expires_at": "2026-09-09T08:29:00Z",
            "public_key_sha256": file_digest(public_key),
        }
        payload = self.root / "certificate-payload.json"
        signature = self.root / "certificate.sig"
        payload.write_bytes(certificate_signing_bytes(certificate))
        subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(private_key), "-out", str(signature), str(payload)],
            check=True,
            capture_output=True,
        )
        certificate["signature"] = base64.b64encode(signature.read_bytes()).decode("ascii")
        result = evaluate_production_certification(
            plan,
            report,
            evidence_root=self.root,
            certificate_value=certificate,
            public_key=public_key,
            now=now,
        )
        self.assertTrue(result["certified"])
        self.assertEqual(result["production_certification"], "CERTIFIED")

        stale = deepcopy(certificate)
        stale["certified_at"] = (now - timedelta(days=2)).isoformat()
        with self.assertRaisesRegex(ContractError, "stale"):
            evaluate_production_certification(
                plan,
                report,
                evidence_root=self.root,
                certificate_value=stale,
                public_key=public_key,
                now=now,
            )

    def test_cli_preflight_reports_blocked_without_contacting_providers(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["external-preflight", "--plan", str(PLAN_PATH)])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["production_certification"], "NOT_CERTIFIED")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            expected_code = main(["external-preflight", "--plan", str(PLAN_PATH), "--expect-blocked"])
        self.assertEqual(expected_code, 0)


if __name__ == "__main__":
    unittest.main()

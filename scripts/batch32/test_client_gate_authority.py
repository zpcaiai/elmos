from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).with_name("run_client_gate.py")
MODULE_SPEC = importlib.util.spec_from_file_location("run_client_gate", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError("unable to load run_client_gate.py")
run_client_gate = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(run_client_gate)


class ClientGateExternalAuthorityTest(unittest.TestCase):
    def test_repository_gate_reports_readiness_but_never_self_certifies(self) -> None:
        self.assertEqual(
            run_client_gate.decide_certification(
                requested_certified=True,
                failures=[],
                portable=False,
            ),
            "READY_FOR_EXTERNAL_GATE",
        )
        self.assertEqual(
            run_client_gate.decide_certification(
                requested_certified=True,
                failures=["missing evidence"],
                portable=False,
            ),
            "BLOCKED",
        )
        self.assertEqual(
            run_client_gate.decide_certification(
                requested_certified=True,
                failures=[],
                portable=True,
            ),
            "NOT_CERTIFIED",
        )

    def test_certification_authority_is_missing_without_an_external_root(self) -> None:
        failures: list[str] = []
        result = run_client_gate.validate_operator_external_authority(
            failures,
            pack=Path(__file__).resolve().parents[2],
            pack_key="pack-v1",
            evidence_path=Path(__file__),
            trust_root_path=None,
        )
        self.assertIsNone(result)
        self.assertEqual(
            failures,
            ["certified status requires --external-trust-root outside the repository"],
        )

    def test_external_root_binds_one_pack_and_exact_evidence_digest(self) -> None:
        now = datetime.now(UTC)
        with tempfile.TemporaryDirectory(prefix="b32-external-authority-") as root:
            directory = Path(root)
            evidence = directory / "evidence.json"
            evidence.write_text('{"result":"PASSED_EXTERNAL"}\n')
            authority = directory / "authority.json"
            authority.write_text(json.dumps({
                "schema_version": 1,
                "kind": "batch32-client-external-trust-root",
                "root_id": "independent-b32-verifier",
                "issued_at": (now - timedelta(minutes=1)).isoformat(),
                "expires_at": (now + timedelta(minutes=5)).isoformat(),
                "revoked": False,
                "pack_authorizations": [{
                    "pack_key": "pack-v1",
                    "evidence_sha256": run_client_gate.sha256_file(evidence),
                    "verifier_id": "independent-verifier-1",
                    "authorized_at": now.isoformat(),
                }],
            }))
            failures: list[str] = []
            digest = run_client_gate.validate_operator_external_authority(
                failures,
                pack=directory,
                pack_key="pack-v1",
                evidence_path=evidence,
                trust_root_path=authority,
            )
            self.assertEqual(failures, [])
            self.assertEqual(digest, run_client_gate.sha256_file(authority))

            evidence.write_text('{"result":"CHANGED"}\n')
            failures = []
            self.assertIsNone(run_client_gate.validate_operator_external_authority(
                failures,
                pack=directory,
                pack_key="pack-v1",
                evidence_path=evidence,
                trust_root_path=authority,
            ))
            self.assertIn("does not uniquely authorize", failures[0])


if __name__ == "__main__":
    unittest.main()

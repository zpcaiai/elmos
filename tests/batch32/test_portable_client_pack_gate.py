from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/batch32"))
import validate_frontend_formal_route_campaign as formal_v1  # noqa: E402
import validate_frontend_formal_route_campaign_v2 as formal_v2  # noqa: E402
import validate_portable_client_packs as portable  # noqa: E402
import run_client_gate as client_gate  # noqa: E402


class PortableClientPackGateTest(unittest.TestCase):
    def write_inventory(self, root: Path) -> None:
        for pack_name, mode in portable.EXPECTED_PACK_MODES.items():
            pack = root / pack_name
            pack.mkdir()
            manifest: dict[str, object] = {"pack_key": pack_name}
            if mode == "formal-v1":
                manifest["frontend_formal_route_campaign"] = "campaign.json"
            elif mode == "formal-v2":
                manifest["frontend_formal_route_campaign_v2"] = "campaign-v2.json"
            (pack / "pack.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_v1_portable_validation_never_executes_the_captured_solver(self) -> None:
        pack = ROOT / "client-packs/frontend-72-route-equivalence-v1"
        with mock.patch.object(
            formal_v1.subprocess,
            "run",
            side_effect=AssertionError("portable v1 attempted native execution"),
        ) as execute:
            result = formal_v1.validate_campaign(
                pack,
                execute_replay=False,
                portable_evidence_only=True,
            )

        self.assertEqual("valid", result["status"], result["errors"])
        execute.assert_not_called()

    def test_v2_portable_validation_never_executes_solver_or_node(self) -> None:
        pack = ROOT / "client-packs/frontend-72-route-equivalence-v2"
        with mock.patch.object(
            formal_v2.subprocess,
            "run",
            side_effect=AssertionError("portable v2 attempted native execution"),
        ) as execute:
            result = formal_v2.validate_campaign(
                pack,
                execute_replay=False,
                portable_evidence_only=True,
            )

        self.assertEqual("valid", result["status"], result["errors"])
        self.assertEqual("NOT_RUN", result["live_engine_verifier_status"])
        execute.assert_not_called()

    def test_formal_commands_use_portable_validators_and_disable_execution(self) -> None:
        pack = Path("/evidence/client-pack")
        v1, v1_command = portable.formal_command(
            pack, {"frontend_formal_route_campaign": "campaign.json"}
        )
        v2, v2_command = portable.formal_command(
            pack, {"frontend_formal_route_campaign_v2": "campaign-v2.json"}
        )

        self.assertEqual(1, v1)
        self.assertIn("validate_frontend_formal_route_campaign.py", v1_command[1])
        self.assertIn("--no-replay-execute", v1_command)
        self.assertIn("--portable-evidence-only", v1_command)
        self.assertEqual(2, v2)
        self.assertIn("validate_frontend_formal_route_campaign_v2.py", v2_command[1])
        self.assertIn("--no-replay-execute", v2_command)
        self.assertIn("--portable-evidence-only", v2_command)

    def test_v2_portable_gate_requires_live_replay_to_remain_not_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="batch32-portable-test-") as directory:
            pack = Path(directory) / "formal-v2"
            pack.mkdir()
            manifest = {
                "pack_key": "formal-v2",
                "frontend_formal_route_campaign_v2": "campaign.json",
            }
            with (
                mock.patch.object(
                    portable,
                    "formal_command",
                    return_value=(2, [sys.executable]),
                ),
                mock.patch.object(
                    portable,
                    "run_checked",
                    return_value={
                        "status": "valid",
                        "structural_status": "PASSED",
                        "certification_ready": False,
                        "live_engine_verifier_status": "PASSED",
                    },
                ),
            ):
                with self.assertRaisesRegex(
                    portable.PortableGateError,
                    "live engine verifier status must remain NOT_RUN",
                ):
                    portable.validate_formal(pack, manifest)

    def test_v2_portable_gate_emits_an_explicit_not_certified_boundary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="batch32-portable-test-") as directory:
            pack = Path(directory) / "formal-v2"
            pack.mkdir()
            manifest = {
                "pack_key": "formal-v2",
                "frontend_formal_route_campaign_v2": "campaign.json",
            }
            with (
                mock.patch.object(
                    portable,
                    "formal_command",
                    return_value=(2, [sys.executable]),
                ),
                mock.patch.object(
                    portable,
                    "run_checked",
                    return_value={
                        "status": "valid",
                        "structural_status": "PASSED",
                        "certification_ready": False,
                        "live_engine_verifier_status": "NOT_RUN",
                    },
                ),
            ):
                outcome = portable.validate_formal(pack, manifest)

        self.assertEqual("PASSED", outcome.structural_status)
        self.assertEqual("NOT_RUN", outcome.native_receipt_replay)
        self.assertEqual("NOT_CERTIFIED", outcome.certification_decision)

    def test_last_json_parser_ignores_human_readable_prefix(self) -> None:
        payload = {"status": "valid", "errors": []}
        self.assertEqual(
            payload,
            portable.parse_last_json(
                "validator progress\n" + json.dumps(payload) + "\n",
                "fixture",
            ),
        )

    def test_portable_client_gate_cannot_grant_certification(self) -> None:
        self.assertEqual(
            "NOT_CERTIFIED",
            client_gate.decide_certification(
                requested_certified=True, failures=[], portable=True
            ),
        )
        self.assertEqual(
            "CERTIFIED",
            client_gate.decide_certification(
                requested_certified=True, failures=[], portable=False
            ),
        )

    def test_inventory_fails_closed_when_a_required_pack_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="batch32-portable-test-") as directory:
            root = Path(directory)
            self.write_inventory(root)
            missing = next(iter(portable.EXPECTED_PACK_MODES))
            (root / missing / "pack.json").unlink()
            (root / missing).rmdir()
            with self.assertRaisesRegex(
                portable.PortableGateError, "client pack inventory mismatch"
            ):
                portable.validate_all(root)

    def test_formal_pack_cannot_downgrade_to_the_ordinary_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="batch32-portable-test-") as directory:
            root = Path(directory)
            self.write_inventory(root)
            pack = root / "frontend-72-route-equivalence-v2"
            (pack / "pack.json").write_text(
                json.dumps({"pack_key": pack.name}), encoding="utf-8"
            )
            with self.assertRaisesRegex(portable.PortableGateError, "mode mismatch"):
                portable.validate_all(root)

    def test_duplicate_pack_key_is_rejected_before_any_gate_runs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="batch32-portable-test-") as directory:
            root = Path(directory)
            self.write_inventory(root)
            names = list(portable.EXPECTED_PACK_MODES)
            duplicate = names[0]
            second = root / names[1] / "pack.json"
            second.write_text(json.dumps({"pack_key": duplicate}), encoding="utf-8")
            with self.assertRaisesRegex(portable.PortableGateError, "duplicate"):
                portable.validate_all(root)


if __name__ == "__main__":
    unittest.main()

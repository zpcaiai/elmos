from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.precision_migration.b42 import (
    CutoverError,
    execute_automatic_rollback,
    execute_canary_traffic_planner,
    execute_dual_write_validation,
    execute_live_event_replay,
    execute_migration_wave_planner,
    execute_post_cutover_monitoring,
    execute_production_shadow_run,
    execute_progressive_cutover,
    execute_side_effect_suppression,
    execute_strangler_routing,
)

Handler = Callable[..., dict[str, Any]]


class PrecisionMigrationB42Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="precision-b42-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def request(self, name: str, payload: dict[str, Any], *, tamper: bool = False) -> dict[str, Any]:
        path = self.root / f"{name}.json"
        content = json.dumps(payload, sort_keys=True).encode("utf-8") + b"\n"
        path.write_bytes(content)
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if tamper:
            digest = "sha256:" + "0" * 64
        return {
            "request_id": f"b42-{name}",
            "inputs": {
                "assets": [{
                    "uri": path.resolve().as_uri(),
                    "digest": digest,
                    "size_bytes": len(content),
                    "media_type": "application/json",
                    "sensitivity": "internal",
                    "version": "fixture-v1",
                }]
            },
        }

    def cases(self) -> dict[str, tuple[Handler, dict[str, Any]]]:
        return {
            "production-shadow-run": (execute_production_shadow_run, {
                "side_effects_suppressed": True,
                "source_observations": [{"id": "r1", "result": {"value": 1}}],
                "target_observations": [{"id": "r1", "result": {"value": 1}}],
            }),
            "live-event-replay": (execute_live_event_replay, {
                "events": [{"sequence": 1, "idempotency_key": "event-1"}, {"sequence": 2, "idempotency_key": "event-2"}],
            }),
            "side-effect-suppression": (execute_side_effect_suppression, {
                "effects": [{"id": "payment-1", "kind": "payment", "replacement": "intent-record"}],
            }),
            "dual-write-validation": (execute_dual_write_validation, {
                "source_records": [{"id": "row-1", "value": 1}],
                "target_records": [{"id": "row-1", "value": 1}],
            }),
            "canary-traffic-planner": (execute_canary_traffic_planner, {
                "maximum_percent": 8,
                "segments": [{"id": "tenant-low-risk", "risk": 1, "approved": True}],
            }),
            "progressive-cutover": (execute_progressive_cutover, {
                "stages": [{"id": "stage-1", "gate": "PASS", "rollback_ready": True}],
            }),
            "automatic-rollback": (execute_automatic_rollback, {
                "metrics": {"error_rate": 0.001}, "thresholds": {"error_rate": 0.01},
            }),
            "migration-wave-planner": (execute_migration_wave_planner, {
                "units": [{"id": "api", "depends_on": [], "risk": 1}, {"id": "web", "depends_on": ["api"], "risk": 2}],
            }),
            "strangler-routing": (execute_strangler_routing, {
                "routes": [{"capability": "catalog-read", "target": "new"}],
            }),
            "post-cutover-monitoring": (execute_post_cutover_monitoring, {
                "samples": [{"name": "error_rate", "value": 0.001, "lower": 0, "upper": 0.01}],
            }),
        }

    def test_all_ten_handlers_execute_bounded_algorithms(self) -> None:
        for name, (handler, payload) in self.cases().items():
            with self.subTest(name=name):
                output = self.root / f"out-{name}"
                output.mkdir()
                result = handler(
                    self.request(name, payload),
                    {"skill": f"pm-b42-{name}"},
                    output,
                    evidence_roots=(self.root.resolve(),),
                )
                self.assertEqual("LOCAL_EXECUTED", result["execution_state"])
                self.assertEqual(0, result["exit_code"])
                artifact = json.loads((output / result["artifacts"][0]["uri"].rsplit("/", 1)[-1]).read_text())
                self.assertFalse(artifact["production_side_effects_executed"])
                self.assertEqual("NOT_RUN", artifact["external_verification"])

    def test_all_ten_handlers_reject_tampered_input(self) -> None:
        for name, (handler, payload) in self.cases().items():
            with self.subTest(name=name):
                output = self.root / f"negative-{name}"
                output.mkdir()
                with self.assertRaises(CutoverError):
                    handler(
                        self.request(f"tampered-{name}", payload, tamper=True),
                        {"skill": f"pm-b42-{name}"},
                        output,
                        evidence_roots=(self.root.resolve(),),
                    )

    def test_rollback_breach_requires_authorized_controller(self) -> None:
        payload = {"metrics": {"error_rate": 0.1}, "thresholds": {"error_rate": 0.01}}
        output = self.root / "rollback"
        output.mkdir()
        result = execute_automatic_rollback(
            self.request("rollback-breach", payload),
            {"skill": "pm-b42-automatic-rollback"},
            output,
            evidence_roots=(self.root.resolve(),),
        )
        artifact = json.loads(Path(result["artifacts"][0]["uri"].removeprefix("file://")).read_text())
        self.assertEqual("ROLLBACK_REQUIRED", artifact["decision"]["state"])
        self.assertTrue(artifact["decision"]["requires_authorized_controller"])
        self.assertFalse(artifact["decision"]["rollback_executed"])


if __name__ == "__main__":
    unittest.main()

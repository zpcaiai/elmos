from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = REPOSITORY_ROOT / "engines" / "frontend-client-engine"
ENGINE_MODULE = ENGINE_ROOT / "dist" / "src" / "directional-route.js"
MATERIALIZER = Path(__file__).with_name("materialize_frt_route.mjs")
BATCH46_GATE = REPOSITORY_ROOT / "scripts" / "batch46" / "run_smoke_gate.py"


class FrtRouteSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="frt-route-smoke-"))
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.request = self.temp / "request.json"
        self.output = self.temp / "generated-target"

    def vue3_fixture(self) -> dict[str, str]:
        program = (
            "import { createDirectionalRouteFixture } from "
            f"{json.dumps(ENGINE_MODULE.as_uri())};"
            "process.stdout.write(JSON.stringify(createDirectionalRouteFixture('Vue 3')));"
        )
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", program],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        return json.loads(completed.stdout)

    def materialize(self) -> subprocess.CompletedProcess[str]:
        self.request.write_text(json.dumps({
            "source": "Vue 3",
            "target": "React",
            "files": self.vue3_fixture(),
        }), encoding="utf-8")
        return subprocess.run(
            ["node", str(MATERIALIZER), "--request", str(self.request), "--output", str(self.output)],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_materializer_attaches_portable_validated_smoke_pack(self) -> None:
        completed = self.materialize()
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        report = json.loads((self.output / "materialization-report.json").read_text())
        self.assertEqual("Vue 3 -> React", report["route"])
        self.assertEqual("ATTACHED_VALIDATED", report["smokePack"])
        self.assertEqual("NOT_RUN", report["runnableGate"])
        profile = json.loads((self.output / "smoke" / "profile.json").read_text())
        self.assertEqual(".", profile["project_root"])
        self.assertEqual([], profile["unknown"])
        self.assertTrue((self.output / "run-smoke.sh").is_file())
        self.assertTrue((self.output / "smoke" / "tools" / "run_smoke.py").is_file())

    def test_materialized_route_executes_and_only_gate_declares_runnable(self) -> None:
        completed = self.materialize()
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        # The engine's exact React runtime is a prepared local toolchain.  This
        # avoids a network install in the unit suite while still starting the
        # generated target, probing both routes and executing teardown.
        os.symlink(ENGINE_ROOT / "node_modules", self.output / "node_modules", target_is_directory=True)
        run = subprocess.run(
            [str(self.output / "run-smoke.sh"), "--entry", "script", "--ttl", "10", "--no-hold", "--no-install"],
            cwd=self.output,
            capture_output=True,
            text=True,
            timeout=60,
        )
        app_stderr = self.output / "smoke" / "runtime" / "logs" / "app.stderr.log"
        diagnostic = app_stderr.read_text(encoding="utf-8") if app_stderr.is_file() else ""
        self.assertEqual(0, run.returncode, run.stdout + run.stderr + diagnostic)
        result = json.loads((self.output / "smoke" / "runtime" / "result.json").read_text())
        self.assertEqual("PASS", result["overall"])
        self.assertTrue(result["lease"]["teardown_complete"])
        gate = subprocess.run(
            ["python3", str(BATCH46_GATE), str(self.output)],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, gate.returncode, gate.stdout + gate.stderr)
        decision = json.loads((self.output / "smoke" / "runtime" / "gate-result.json").read_text())
        self.assertEqual("runnable", decision["status"])

    def test_materializer_is_create_only_and_rejects_request_widening(self) -> None:
        completed = self.materialize()
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        repeated = subprocess.run(
            ["node", str(MATERIALIZER), "--request", str(self.request), "--output", str(self.output)],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(0, repeated.returncode)
        self.assertIn("FRT_ROUTE_OUTPUT_MUST_NOT_EXIST", repeated.stderr)

        widened = json.loads(self.request.read_text())
        widened["command"] = "echo unsafe"
        self.request.write_text(json.dumps(widened), encoding="utf-8")
        rejected = subprocess.run(
            ["node", str(MATERIALIZER), "--request", str(self.request), "--output", str(self.temp / "other")],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("FRT_ROUTE_REQUEST_FIELDS_INVALID", rejected.stderr)


if __name__ == "__main__":
    unittest.main()

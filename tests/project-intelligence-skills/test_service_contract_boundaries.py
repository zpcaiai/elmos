from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/project-intelligence-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_project_intelligence.artifacts import (  # noqa: E402
    ContentAddressedArtifactStore,
)
from elmos_project_intelligence.contracts import RunStatus  # noqa: E402
from elmos_project_intelligence.runtime import SkillRuntimeError  # noqa: E402
from elmos_project_intelligence.service import (  # noqa: E402
    ProjectIntelligenceService,
)
from elmos_project_intelligence.store import ProjectIntelligenceStore  # noqa: E402


def _rejected_request() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": "rejected-run",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "revision": "abc123",
        "inputs": {
            "revision": "abc123",
            "files": [
                {"path": "duplicate.py", "text": "first"},
                {"path": "duplicate.py", "text": "second"},
            ],
        },
    }


class ServiceContractBoundaryTests(unittest.TestCase):
    def test_dispatch_rejection_never_becomes_collected_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-pi-rejection-") as temporary:
            root = Path(temporary).resolve()
            store = ProjectIntelligenceStore(root / "state.sqlite3")
            artifacts = ContentAddressedArtifactStore(root / "artifacts")
            service = ProjectIntelligenceService(store, artifacts)
            try:
                with self.assertRaisesRegex(
                    SkillRuntimeError,
                    "request or capability contract rejected",
                ):
                    service.execute(
                        "elmos-project-fingerprinting",
                        _rejected_request(),
                        idempotency_key="rejected-idempotency",
                    )

                run = store.get_run("tenant-a", "project-a", "rejected-run")
                self.assertEqual(run.status, RunStatus.FAILED)
                self.assertEqual(
                    store.list_artifacts("tenant-a", "project-a", "rejected-run"),
                    (),
                )
                self.assertEqual(
                    store.list_evidence("tenant-a", "project-a", "rejected-run"),
                    (),
                )
                checkpoints = store.list_checkpoints(
                    "tenant-a",
                    "project-a",
                    "rejected-run",
                )
                self.assertEqual(len(checkpoints), 1)
                self.assertEqual(checkpoints[0].state["kind"], "service-failure")
                self.assertEqual(checkpoints[0].state["phase"], "handler-dispatch")
                objects = [
                    path for path in artifacts.objects.rglob("*") if path.is_file()
                ]
                self.assertEqual(objects, [])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()

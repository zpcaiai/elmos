from __future__ import annotations

from collections.abc import Mapping
import tempfile
import threading
from pathlib import Path
import unittest
from unittest.mock import patch

from elmos_project_intelligence.artifacts import (
    ArtifactStoreError,
    ContentAddressedArtifactStore,
)
from elmos_project_intelligence.contracts import RunStatus
from elmos_project_intelligence.runtime import (
    SkillRuntimeError,
    dispatch_skill as runtime_dispatch_skill,
)
from elmos_project_intelligence.service import ProjectIntelligenceService
from elmos_project_intelligence.store import (
    IdempotencyConflict,
    ProjectIntelligenceStore,
    RecordNotFound,
)


def request(
    *, tenant: str = "tenant-a", request_id: str = "run-1"
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": request_id,
        "tenant_id": tenant,
        "project_id": "project-a",
        "revision": "abc123",
        "actor_id": "actor-a",
        "purpose": "local-engineering-test",
        "inputs": {
            "files": [
                {"path": "src/app.py", "text": "class App:\n    pass\n"},
                {"path": "pyproject.toml", "text": "[project]\nname='app'\n"},
            ]
        },
    }


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="elmos-pi-service-")
        root = Path(self.temporary.name).resolve()
        self.store = ProjectIntelligenceStore(root / "state.sqlite3")
        self.artifacts = ContentAddressedArtifactStore(root / "artifacts")
        self.service = ProjectIntelligenceService(self.store, self.artifacts)

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def test_execution_persists_digest_bound_artifact_evidence_and_checkpoint(
        self,
    ) -> None:
        result = self.service.execute(
            "elmos-project-fingerprinting",
            request(),
            idempotency_key="idempotency-1",
        )
        self.assertEqual(result["state"], "LOCAL_EXECUTED")
        self.assertEqual(result["run_status"], "SUCCEEDED")
        self.assertEqual(result["evidence_state"], "COLLECTED")
        self.assertFalse(result["independent_verifier"])
        self.assertEqual(result["external_evidence"], "NOT_RUN")
        self.assertEqual(result["certification"], "NOT_CERTIFIED")
        self.assertTrue(self.artifacts.contains(result["artifact_digest"]))
        artifacts = self.store.list_artifacts("tenant-a", "project-a", "run-1")
        evidence = self.store.list_evidence("tenant-a", "project-a", "run-1")
        checkpoints = self.store.list_checkpoints("tenant-a", "project-a", "run-1")
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(evidence[0].state.value, "COLLECTED")
        self.assertIsNone(evidence[0].verifier)

    def test_exact_replay_returns_terminal_response_without_duplicate_records(
        self,
    ) -> None:
        first = self.service.execute(
            "elmos-project-fingerprinting", request(), idempotency_key="same"
        )
        second = self.service.execute(
            "elmos-project-fingerprinting", request(), idempotency_key="same"
        )
        self.assertEqual(first["result_digest"], second["result_digest"])
        self.assertEqual(second["idempotency"], "REPLAYED")
        self.assertEqual(
            len(self.store.list_artifacts("tenant-a", "project-a", "run-1")), 1
        )

    def test_overlapping_same_key_replay_is_in_progress_without_dispatch(self) -> None:
        entered_handler = threading.Event()
        release_handler = threading.Event()
        call_lock = threading.Lock()
        dispatch_calls = 0
        first_results: list[dict[str, object]] = []
        first_errors: list[BaseException] = []

        def blocking_dispatch(
            skill: str, request_value: Mapping[str, object]
        ) -> dict[str, object]:
            nonlocal dispatch_calls
            with call_lock:
                dispatch_calls += 1
                call_number = dispatch_calls
            if call_number == 1:
                entered_handler.set()
                if not release_handler.wait(timeout=5):
                    raise RuntimeError("test handler release timed out")
            return runtime_dispatch_skill(skill, request_value)

        def execute_first() -> None:
            try:
                first_results.append(
                    self.service.execute(
                        "elmos-project-fingerprinting",
                        request(),
                        idempotency_key="overlapping-key",
                    )
                )
            except BaseException as exc:
                first_errors.append(exc)

        with patch(
            "elmos_project_intelligence.service.dispatch_skill",
            side_effect=blocking_dispatch,
        ):
            worker = threading.Thread(target=execute_first, daemon=True)
            worker.start()
            try:
                self.assertTrue(entered_handler.wait(timeout=5))
                replay_one = self.service.execute(
                    "elmos-project-fingerprinting",
                    request(),
                    idempotency_key="overlapping-key",
                )
                replay_two = self.service.execute(
                    "elmos-project-fingerprinting",
                    request(),
                    idempotency_key="overlapping-key",
                )
                self.assertEqual(replay_one["state"], "IN_PROGRESS")
                self.assertEqual(replay_one["code"], "IDEMPOTENT_RUN_IN_PROGRESS")
                self.assertEqual(replay_one["idempotency"], "REPLAYED")
                self.assertEqual(replay_one["run_status"], "RUNNING")
                self.assertEqual(
                    replay_one["result_digest"], replay_two["result_digest"]
                )
                self.assertFalse(replay_one["external_effects_performed"])
                self.assertEqual(replay_one["external_evidence"], "NOT_RUN")
                self.assertEqual(replay_one["certification"], "NOT_CERTIFIED")
                self.assertEqual(dispatch_calls, 1)
            finally:
                release_handler.set()
                worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(first_errors, [])
        self.assertEqual(len(first_results), 1)
        self.assertEqual(first_results[0]["run_status"], "SUCCEEDED")
        self.assertEqual(dispatch_calls, 1)
        self.assertEqual(
            len(self.store.list_artifacts("tenant-a", "project-a", "run-1")), 1
        )
        self.assertEqual(
            len(self.store.list_evidence("tenant-a", "project-a", "run-1")), 1
        )
        self.assertEqual(
            len(self.store.list_checkpoints("tenant-a", "project-a", "run-1")),
            1,
        )

    def test_idempotency_conflict_and_cross_tenant_lookup_fail_closed(self) -> None:
        self.service.execute(
            "elmos-project-fingerprinting", request(), idempotency_key="same"
        )
        changed = request(request_id="run-2")
        changed["revision"] = "different"
        with self.assertRaises(IdempotencyConflict):
            self.service.execute(
                "elmos-project-fingerprinting", changed, idempotency_key="same"
            )
        with self.assertRaises(RecordNotFound):
            self.store.get_run("tenant-b", "project-a", "run-1")

    def test_unknown_skill_is_rejected_before_persistence(self) -> None:
        with self.assertRaises(SkillRuntimeError):
            self.service.execute("elmos-unknown", request(), idempotency_key="unknown")
        with self.assertRaises(RecordNotFound):
            self.store.get_run("tenant-a", "project-a", "run-1")

    def test_handler_exception_is_sanitized_terminal_and_replay_safe(self) -> None:
        secret = "provider-token=must-not-persist"
        with patch(
            "elmos_project_intelligence.service.dispatch_skill",
            side_effect=RuntimeError(secret),
        ):
            with self.assertRaisesRegex(RuntimeError, "must-not-persist"):
                self.service.execute(
                    "elmos-project-fingerprinting",
                    request(),
                    idempotency_key="handler-failure",
                )

        run = self.store.get_run("tenant-a", "project-a", "run-1")
        self.assertEqual(run.status, RunStatus.FAILED)
        self.assertIsInstance(run.response, Mapping)
        response = dict(run.response)
        self.assertEqual(response["state"], "BLOCKED")
        self.assertEqual(response["code"], "SERVICE_EXECUTION_FAILED")
        self.assertEqual(response["error"]["phase"], "handler-dispatch")
        self.assertEqual(response["error"]["type"], "RuntimeError")
        self.assertFalse(response["error"]["message_disclosed"])
        self.assertNotIn(secret, repr(response))
        self.assertEqual(response["external_evidence"], "NOT_RUN")
        self.assertEqual(response["certification"], "NOT_CERTIFIED")

        checkpoints = self.store.list_checkpoints("tenant-a", "project-a", "run-1")
        events = self.store.list_events("tenant-a", "project-a", "run-1")
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(checkpoints[0].state["kind"], "service-failure")
        self.assertNotIn(secret, repr(checkpoints))
        self.assertEqual(
            [event.event_type for event in events],
            [
                "run.created",
                "run.status-changed",
                "checkpoint.recorded",
                "run.status-changed",
            ],
        )
        before_event_count = len(events)
        before_checkpoint_count = len(checkpoints)

        replay = self.service.execute(
            "elmos-project-fingerprinting",
            request(),
            idempotency_key="handler-failure",
        )
        self.assertEqual(replay["idempotency"], "REPLAYED")
        self.assertEqual(replay["run_status"], "FAILED")
        self.assertEqual(
            replay["error"]["fingerprint"], response["error"]["fingerprint"]
        )
        self.assertEqual(
            len(self.store.list_events("tenant-a", "project-a", "run-1")),
            before_event_count,
        )
        self.assertEqual(
            len(self.store.list_checkpoints("tenant-a", "project-a", "run-1")),
            before_checkpoint_count,
        )

    def test_cas_failure_terminalizes_without_partial_database_evidence(self) -> None:
        secret = "artifact-path=/sensitive/location"
        with patch.object(
            self.artifacts,
            "put",
            side_effect=ArtifactStoreError(secret),
        ):
            with self.assertRaises(ArtifactStoreError):
                self.service.execute(
                    "elmos-project-fingerprinting",
                    request(),
                    idempotency_key="cas-failure",
                )

        run = self.store.get_run("tenant-a", "project-a", "run-1")
        self.assertEqual(run.status, RunStatus.FAILED)
        assert isinstance(run.response, Mapping)
        self.assertEqual(run.response["error"]["phase"], "artifact-write")
        self.assertNotIn(secret, repr(run.response))
        self.assertEqual(
            self.store.list_artifacts("tenant-a", "project-a", "run-1"), ()
        )
        self.assertEqual(self.store.list_evidence("tenant-a", "project-a", "run-1"), ())
        self.assertEqual(
            len(self.store.list_checkpoints("tenant-a", "project-a", "run-1")),
            1,
        )

        replay = self.service.execute(
            "elmos-project-fingerprinting",
            request(),
            idempotency_key="cas-failure",
        )
        self.assertEqual(replay["idempotency"], "REPLAYED")
        self.assertEqual(replay["run_status"], "FAILED")

    def test_store_artifact_failure_terminalizes_after_local_cas_write(self) -> None:
        secret = "sqlite-details=must-not-persist"
        with patch.object(
            self.store,
            "put_artifact",
            side_effect=RuntimeError(secret),
        ):
            with self.assertRaises(RuntimeError):
                self.service.execute(
                    "elmos-project-fingerprinting",
                    request(),
                    idempotency_key="store-failure",
                )

        run = self.store.get_run("tenant-a", "project-a", "run-1")
        self.assertEqual(run.status, RunStatus.FAILED)
        assert isinstance(run.response, Mapping)
        self.assertEqual(run.response["error"]["phase"], "artifact-record")
        self.assertNotIn(secret, repr(run.response))
        self.assertEqual(
            self.store.list_artifacts("tenant-a", "project-a", "run-1"), ()
        )
        self.assertEqual(self.store.list_evidence("tenant-a", "project-a", "run-1"), ())
        self.assertEqual(
            len(self.store.list_checkpoints("tenant-a", "project-a", "run-1")),
            1,
        )
        objects = [path for path in self.artifacts.objects.rglob("*") if path.is_file()]
        self.assertEqual(len(objects), 1)

    def test_checkpoint_persistence_failure_uses_failure_checkpoint_retry(self) -> None:
        original_append = self.store.append_checkpoint
        attempts = 0

        def fail_once(*args: object, **kwargs: object):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("checkpoint-secret=must-not-persist")
            return original_append(*args, **kwargs)

        with patch.object(self.store, "append_checkpoint", side_effect=fail_once):
            with self.assertRaises(RuntimeError):
                self.service.execute(
                    "elmos-project-fingerprinting",
                    request(),
                    idempotency_key="checkpoint-failure",
                )

        run = self.store.get_run("tenant-a", "project-a", "run-1")
        self.assertEqual(run.status, RunStatus.FAILED)
        assert isinstance(run.response, Mapping)
        self.assertTrue(run.response["failure_checkpoint_recorded"])
        self.assertEqual(run.response["error"]["phase"], "checkpoint-record")
        checkpoints = self.store.list_checkpoints("tenant-a", "project-a", "run-1")
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(checkpoints[0].state["kind"], "service-failure")
        self.assertNotIn("checkpoint-secret", repr(checkpoints))


if __name__ == "__main__":
    unittest.main()

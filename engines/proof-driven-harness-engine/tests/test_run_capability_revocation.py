from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
import threading
from typing import Any, Mapping, cast
import unittest

from elmos_proof_harness.canonical import canonical_json_bytes
from elmos_proof_harness.contracts import SecurityContext
from elmos_proof_harness.control_plane import DurableControlPlane
from elmos_proof_harness.delta_storage import (
    CapabilityLeaseRecord,
    CapabilityRevocationReason,
)
from elmos_proof_harness.runtime_assurance import RuntimeAssuranceControlPlane
from elmos_proof_harness.service import AuthPrincipal
from elmos_proof_harness.skills import SkillExecutionResult, SkillRuntime
from elmos_proof_harness.store import SQLiteStore


SOURCE = "sha256:" + "1" * 64
BASELINE = "sha256:" + "2" * 64
REQUIREMENTS = "sha256:" + "3" * 64
POLICY = "sha256:" + "4" * 64
TOOLCHAIN = "sha256:" + "5" * 64
ENVIRONMENT = "sha256:" + "6" * 64
DOMAIN = "sha256:" + "7" * 64
WORKFLOW = "sha256:" + "8" * 64
MODEL_ROUTE = "sha256:" + "9" * 64
AUTH_CONTEXT = "sha256:" + "a" * 64
AUTHORITY_REVISION = "sha256:" + "b" * 64


class _RecordingStore(SQLiteStore):
    """Real local workflow store with a narrow observable assurance boundary."""

    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        self._revocation_lock = threading.Lock()
        self._revocations: list[tuple[SecurityContext, CapabilityRevocationReason]] = []

    def revoke_run_capability_leases(
        self,
        context: SecurityContext,
        *,
        reason: CapabilityRevocationReason,
        now: datetime | None = None,
    ) -> tuple[CapabilityLeaseRecord, ...]:
        del now
        with self._revocation_lock:
            self._revocations.append((context, reason))
        return ()

    def revocations(
        self,
    ) -> tuple[tuple[SecurityContext, CapabilityRevocationReason], ...]:
        with self._revocation_lock:
            return tuple(self._revocations)

    def clear_revocations(self) -> None:
        with self._revocation_lock:
            self._revocations.clear()


class _RuntimeAssuranceProbe:
    """Only the run-level revocation port used by DurableControlPlane."""

    def __init__(self, store: _RecordingStore) -> None:
        self.store = store


class _ScriptedRuntime(SkillRuntime):
    """Deterministic in-process result source; all durability remains real."""

    def execute(
        self,
        skill_name: str,
        payload: Mapping[str, Any],
        *,
        context: Any = None,
    ) -> SkillExecutionResult:
        del context
        status = payload.get("testStatus")
        if not isinstance(status, str):
            raise ValueError("testStatus is required")
        return SkillExecutionResult(
            skill_name,
            status,
            {"observedStatus": status},
            reason="deterministic lifecycle fixture",
        )


class RunCapabilityRevocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = _RecordingStore(self.root / "state.db")
        self.runtime = _ScriptedRuntime(workspace_roots=(self.root,))
        assurance_probe = cast(
            RuntimeAssuranceControlPlane,
            _RuntimeAssuranceProbe(self.store),
        )
        self.control_plane = DurableControlPlane(
            self.store,
            self.runtime,
            runtime_assurance=assurance_probe,
        )
        self.principal = AuthPrincipal(
            tenant_id="tenant-revocation",
            project_id="project-revocation",
            actor_id="actor-revocation",
            authority=("proof-harness.invoke", "proof-harness.cancel"),
            authentication_context_digest=AUTH_CONTEXT,
            authority_id="authority-revocation",
            authority_revision=AUTHORITY_REVISION,
            environment_id="environment-revocation",
            environment_revision=ENVIRONMENT,
            execution_epoch=1,
            fencing_generation=1,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

    def tearDown(self) -> None:
        self.control_plane.shutdown()
        self.store.close()
        self.temporary.cleanup()

    def _request(
        self,
        status: str,
        suffix: str,
        *,
        limits: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "apiVersion": "elmos.ai/proof-harness/v3",
            "requestId": f"request-revocation-{suffix}",
            "skill": "elmos-goal-specification-kernel",
            "identity": {
                "tenantId": self.principal.tenant_id,
                "projectId": self.principal.project_id,
                "actorId": self.principal.actor_id,
                "authenticationContextDigest": (
                    self.principal.authentication_context_digest
                ),
            },
            "revisionSet": {
                "revisionSetId": f"revision-set-{suffix}",
                "source": SOURCE,
                "baseline": BASELINE,
                "requirements": REQUIREMENTS,
                "policy": POLICY,
                "toolchain": TOOLCHAIN,
                "environment": self.principal.environment_revision,
                "domainPack": DOMAIN,
                "workflow": WORKFLOW,
                "modelRoute": MODEL_ROUTE,
            },
            "authority": {
                "authorityId": self.principal.authority_id,
                "revision": self.principal.authority_revision,
                "environmentId": self.principal.environment_id,
                "executionEpoch": self.principal.execution_epoch,
                "fencingGeneration": self.principal.fencing_generation,
                "expiresAt": self.principal.expires_at.astimezone(UTC)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z"),
            },
            "idempotencyKey": f"revocation-{suffix}-0001",
            "input": {"testStatus": status},
        }
        if limits is not None:
            request["limits"] = dict(limits)
        return request

    def _run_to_terminal(
        self,
        request: Mapping[str, Any],
    ) -> tuple[str, str]:
        admitted = self.control_plane.invoke(
            self.principal,
            request,
            input_bytes=len(canonical_json_bytes(request)),
        )
        self.assertFalse(admitted.completed)
        self.assertTrue(self.control_plane.wait_for_run(admitted.run.run_id, 10.0))
        context = self.control_plane.register_scope(self.principal)
        snapshot = self.store.get_run(context, admitted.run.run_id)
        return admitted.run.run_id, str(snapshot.state)

    def _assert_last_revocation(
        self,
        run_id: str,
        reason: CapabilityRevocationReason,
    ) -> None:
        revocations = self.store.revocations()
        self.assertGreaterEqual(len(revocations), 1)
        context, observed = revocations[-1]
        self.assertEqual(context.run_id, run_id)
        self.assertEqual(observed, reason)

    def test_successful_completion_revokes_with_completed_reason(self) -> None:
        run_id, state = self._run_to_terminal(self._request("SUCCEEDED", "completed"))
        self.assertEqual(state, "COMPLETED")
        self._assert_last_revocation(
            run_id,
            CapabilityRevocationReason.COMPLETED,
        )

    def test_failure_and_partial_revoke_with_turn_aborted_reason(self) -> None:
        for status, expected_state in (("FAILED", "FAILED"), ("PARTIAL", "PARTIAL")):
            with self.subTest(status=status):
                self.store.clear_revocations()
                run_id, state = self._run_to_terminal(
                    self._request(status, status.lower())
                )
                self.assertEqual(state, expected_state)
                self._assert_last_revocation(
                    run_id,
                    CapabilityRevocationReason.TURN_ABORTED,
                )

    def test_wall_clock_timeout_revokes_with_timed_out_reason(self) -> None:
        run_id, state = self._run_to_terminal(
            self._request(
                "SUCCEEDED",
                "timed-out",
                limits={"wallClockSeconds": 0.000001, "maxOutputBytes": 4096},
            )
        )
        self.assertEqual(state, "TIMED_OUT")
        self._assert_last_revocation(
            run_id,
            CapabilityRevocationReason.TIMED_OUT,
        )

    def test_cancel_revokes_before_terminal_transition(self) -> None:
        self.control_plane.auto_start_workers = False
        request = self._request("SUCCEEDED", "cancelled")
        admitted = self.control_plane.invoke(
            self.principal,
            request,
            input_bytes=len(canonical_json_bytes(request)),
        )
        outcome = self.control_plane.cancel(
            self.principal,
            admitted.run.run_id,
            expected_version=admitted.run.sequence,
            reason="operator requested cancellation",
            idempotency_key="cancel-revocation-0001",
        )
        self.assertEqual(outcome.run["state"], "CANCELLED")
        self._assert_last_revocation(
            admitted.run.run_id,
            CapabilityRevocationReason.CANCELLED,
        )

    def test_terminal_worker_replay_compensates_missing_revocation(self) -> None:
        request = self._request("SUCCEEDED", "terminal-replay")
        admitted = self.control_plane.invoke(
            self.principal,
            request,
            input_bytes=len(canonical_json_bytes(request)),
        )
        self.assertTrue(self.control_plane.wait_for_run(admitted.run.run_id, 10.0))
        request_digest = admitted.result.get("requestDigest")
        self.assertIsInstance(request_digest, str)
        context = self.control_plane.register_scope(self.principal)
        receipt = self.store.get_control_plane_receipt(
            context,
            operation="invoke",
            idempotency_key=str(request["idempotencyKey"]),
            request_sha256=cast(str, request_digest),
        )
        if receipt is None:
            self.fail("completed invocation receipt is missing")
        self.store.clear_revocations()

        self.assertTrue(self.control_plane._process_receipt(receipt, None))

        self.assertEqual(len(self.store.revocations()), 1)
        self._assert_last_revocation(
            admitted.run.run_id,
            CapabilityRevocationReason.COMPLETED,
        )


if __name__ == "__main__":
    unittest.main()

"""Tests for v3.2 HTTP Endpoints on HarnessService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import unittest

from elmos_proof_harness.service import (
    AuthPrincipal,
    HarnessService,
)
from elmos_proof_harness.skills import SkillRuntime


_DIGEST = "sha256:" + "a" * 64


def _principal(authority: tuple[str, ...] = ("proof-harness.read", "proof-harness.invoke")) -> AuthPrincipal:
    return AuthPrincipal(
        tenant_id="tenant-1",
        project_id="project-1",
        actor_id="actor-1",
        authority=authority,
        authentication_context_digest=_DIGEST,
        authority_id="authority-1",
        authority_revision=_DIGEST,
        environment_id="environment-1",
        environment_revision=_DIGEST,
        execution_epoch=1,
        fencing_generation=1,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class ServiceV32EndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = SkillRuntime()
        self.token = "test-token-0123456789"
        self.service = HarnessService(
            self.runtime,
            auth_tokens={self.token: _principal()},
            runtime_mode="local-engineering",
        )
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def test_get_v32_skills_returns_all_20_skills(self) -> None:
        res = self.service.handle_request("GET", "/v3.2/skills", self.headers)
        self.assertEqual(res.status, 200)
        data = json.loads(res.body)
        self.assertEqual(data["registryVersion"], "3.2.0")
        self.assertEqual(len(data["skills"]), 20)
        skill_names = {s["name"] for s in data["skills"]}
        self.assertIn("durable-execution-ownership", skill_names)
        self.assertIn("effective-policy-authority", skill_names)
        self.assertIn("elmos-engineering-control-plane-v3.2", skill_names)

    def test_post_v32_skills_invoke(self) -> None:
        payload = json.dumps({
            "execution_id": "exec-101",
            "owner_id": "actor-101",
            "epoch": 1,
            "action": "quiesce",
        }).encode("utf-8")
        res = self.service.handle_request(
            "POST",
            "/v3.2/skills/durable-execution-ownership/invoke",
            self.headers,
            body=payload,
        )
        self.assertEqual(res.status, 200)
        data = json.loads(res.body)
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["ownership"]["state"], "QUIESCING")

    def test_post_v32_timeline(self) -> None:
        payload = json.dumps({
            "execution_id": "exec-timeline-01",
            "events": [{"type": "INIT", "payload": {"step": 1}}],
        }).encode("utf-8")
        res = self.service.handle_request(
            "POST",
            "/v3.2/timeline",
            self.headers,
            body=payload,
        )
        self.assertEqual(res.status, 200)
        data = json.loads(res.body)
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["event_count"], 1)

    def test_post_v32_artifacts(self) -> None:
        payload = json.dumps({
            "execution_id": "exec-artifact-01",
            "artifacts": [{"id": "art-1", "content": "hello world", "type": "report"}],
        }).encode("utf-8")
        res = self.service.handle_request(
            "POST",
            "/v3.2/artifacts",
            self.headers,
            body=payload,
        )
        self.assertEqual(res.status, 200)
        data = json.loads(res.body)
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(len(data["registered_artifacts"]), 1)

    def test_post_v32_ownership(self) -> None:
        payload = json.dumps({
            "execution_id": "exec-own-01",
            "owner_id": "worker-01",
            "epoch": 2,
            "action": "suspend",
        }).encode("utf-8")
        res = self.service.handle_request(
            "POST",
            "/v3.2/ownership",
            self.headers,
            body=payload,
        )
        self.assertEqual(res.status, 200)
        data = json.loads(res.body)
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["ownership"]["state"], "SUSPENDED")

    def test_post_v32_approvals(self) -> None:
        payload = json.dumps({
            "approval_id": "appr-1",
            "execution_plan_digest": "plan-digest-1",
            "action_kind": "EXEC_COMMAND",
            "decision": "ALLOW",
            "resource_digest": "res-digest-1",
            "valid_seconds": 120,
        }).encode("utf-8")
        res = self.service.handle_request(
            "POST",
            "/v3.2/approvals",
            self.headers,
            body=payload,
        )
        self.assertEqual(res.status, 200)
        data = json.loads(res.body)
        self.assertEqual(data["status"], "SUCCESS")
        self.assertTrue(data["is_valid_and_matched"])

    def test_post_v32_release_gate_evaluate(self) -> None:
        payload = json.dumps({
            "release_id": "rel-v32-test",
            "checks": [{"status": "PASS", "evidence_id": "ev-01"}],
            "exact_artifact_verified": True,
        }).encode("utf-8")
        res = self.service.handle_request(
            "POST",
            "/v3.2/release-gate/evaluate",
            self.headers,
            body=payload,
        )
        self.assertEqual(res.status, 200)
        data = json.loads(res.body)
        self.assertEqual(data["gate_decision"], "PASS")

    def test_get_v32_status_side_effect_free(self) -> None:
        res = self.service.handle_request(
            "GET",
            "/v3.2/status",
            self.headers,
        )
        self.assertEqual(res.status, 200)
        data = json.loads(res.body)
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["connect_calls"], 0)

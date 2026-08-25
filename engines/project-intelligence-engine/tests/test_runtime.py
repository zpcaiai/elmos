from __future__ import annotations

import hashlib
import unittest

from elmos_project_intelligence.runtime import (
    SKILL_REGISTRY,
    SkillRuntimeError,
    capability_manifest,
    dispatch_skill,
    validate_skill_registry,
)


def sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


BASE_FILES = [
    {
        "path": "README.md",
        "text": "# Refund Service\nHandles refund requests with evidence.\n",
    },
    {
        "path": "src/app.py",
        "text": (
            "from src.store import RefundStore\n"
            "class App:\n"
            "    def refund(self, order_id):\n"
            "        return RefundStore().save(order_id)\n"
        ),
    },
    {
        "path": "src/store.py",
        "text": (
            "class RefundStore:\n"
            "    table = 'refunds'\n"
            "    def save(self, order_id):\n"
            "        return order_id\n"
        ),
    },
    {
        "path": "src/api.py",
        "text": "@post('/refunds')\ndef create_refund():\n    publish('refund.created')\n",
    },
    {
        "path": "tests/test_app.py",
        "text": "def test_refund():\n    assert App().refund('o1') == 'o1'\n",
    },
    {"path": "pyproject.toml", "text": "[project]\nname='refund-service'\n"},
]


def base_inputs() -> dict[str, object]:
    files = [dict(item) for item in BASE_FILES]
    return {
        "files": files,
        "revision": "abc123",
        "requested_skills": [
            "elmos-repository-ingestion",
            "elmos-project-fingerprinting",
        ],
        "dependency_edges": [
            {
                "dependency": "elmos-reference-architecture",
                "skill": "elmos-repository-ingestion",
            },
            {
                "dependency": "elmos-repository-ingestion",
                "skill": "elmos-project-fingerprinting",
            },
        ],
        "requirements": [
            {
                "id": "REQ-1",
                "statement": "Refund is evidence-backed",
                "evidence_refs": ["ev-1"],
            }
        ],
        "claims": [
            {
                "id": "claim-1",
                "statement": "Refund endpoint exists",
                "evidence_refs": ["ev-1"],
            }
        ],
        "evidence": [
            {"id": "ev-1", "path": "src/api.py", "digest": sha(BASE_FILES[3]["text"])}
        ],
        "path": "src/app.py",
        "symbol": "App",
        "query": "refund endpoint",
        "changed_paths": ["src/store.py"],
        "declared_components": ["src", "tests"],
        "rules": [{"id": "RULE-1", "pattern": "TODO"}],
        "traces": [
            {"trace_id": "trace-1", "component": "src/app.py", "duration_ms": 5}
        ],
        "nodes": [
            {"id": "api", "name": "refund-api", "kind": "service"},
            {"id": "store", "name": "refund-store", "kind": "database"},
        ],
        "edges": [{"from": "api", "to": "store", "kind": "writes"}],
        "diagram_type": "component",
        "diagram_spec": {
            "nodes": [
                {"id": "api", "label": "Refund API", "kind": "service"},
                {"id": "store", "label": "Refund Store", "kind": "database"},
            ],
            "edges": [{"from": "api", "to": "store", "kind": "writes"}],
        },
        "patch": [{"node_id": "api", "label": "Refund HTTP API"}],
        "locked_node_ids": [],
        "artifacts": [
            {
                "artifact_id": "architecture",
                "digest": sha("architecture"),
                "media_type": "text/markdown",
            }
        ],
        "stage": "fingerprint",
        "stage_inputs": {"revision": "abc123"},
        "artifact_id": "architecture",
        "content": "v1",
        "proposed_content": "v1",
        "previous_version": 1,
        "human_locked": False,
        "title": "Project Intelligence artifacts",
        "actor_tenant_id": "tenant-a",
        "resource_tenant_id": "tenant-a",
        "roles": ["project-reader"],
        "required_roles": ["project-reader"],
        "connector": {"id": "local-mcp", "scopes": ["read:project"]},
        "max_shard_bytes": 256,
        "observations": [{"status": "SUCCEEDED"}, {"status": "SUCCEEDED"}],
        "success_rate_target": "0.99",
        "test_results": [{"id": "test-1", "required": True, "status": "PASSED"}],
        "mappings": [
            {
                "source_ref": "src/app.py:3",
                "target_ref": "target/app.py:3",
                "evidence_ref": "ev-1",
            }
        ],
        "workers": 2,
        "human_review_effort_seconds": 300,
        "topology": "self-hosted",
        "controls": [
            "immutable-image-digest",
            "secret-reference-only",
            "backup-restore-plan",
            "tenant-isolation",
            "rollback-plan",
        ],
        "gates": [{"id": "local", "required": True, "status": "PASSED"}],
        "independent_verifier": True,
        "edition": "enterprise",
        "requested_features": ["reader"],
        "entitled_features": ["reader"],
        "adapter": {
            "id": "fixture-dap",
            "capabilities": ["breakpoints", "stack", "variables"],
        },
        "requested_capabilities": ["breakpoints", "stack"],
        "ttl_seconds": 600,
        "debug_events": [
            {
                "event_id": "event-1",
                "sequence": 1,
                "kind": "stopped",
                "thread_id": "main",
                "frame": "refund",
                "trace_id": "trace-1",
                "timestamp": "2026-08-24T00:00:00Z",
                "secret": "must-not-leak",
            },
            {
                "event_id": "event-2",
                "sequence": 2,
                "kind": "continued",
                "thread_id": "main",
                "trace_id": "trace-1",
                "timestamp": "2026-08-24T00:00:01Z",
            },
        ],
        "frames": [
            {
                "frame_id": "frame-1",
                "function": "refund",
                "evidence_ref": "src/app.py:3",
            }
        ],
    }


def request(inputs: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": "request-1",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "revision": "abc123",
        "actor_id": "actor-a",
        "purpose": "local-engineering-qualification",
        "inputs": base_inputs() if inputs is None else inputs,
    }


class RuntimeRegistryTests(unittest.TestCase):
    def test_exact_fifty_unique_handlers_and_state_counts(self) -> None:
        validate_skill_registry()
        bindings = list(SKILL_REGISTRY.values())
        self.assertEqual(len(bindings), 50)
        self.assertEqual([item.ordinal for item in bindings], list(range(50)))
        self.assertEqual(len({item.handler_id for item in bindings}), 50)
        self.assertEqual(len({id(item.operation) for item in bindings}), 50)
        self.assertEqual(
            {
                state: sum(item.capability_state == state for item in bindings)
                for state in ("LOCAL", "PARTIAL", "PLAN")
            },
            {"LOCAL": 21, "PARTIAL": 24, "PLAN": 5},
        )
        with self.assertRaises(TypeError):
            SKILL_REGISTRY["elmos-unknown"] = bindings[0]  # type: ignore[index]

    def test_all_fifty_handlers_execute_capability_specific_contracts(self) -> None:
        expected_states = {
            "LOCAL": "LOCAL_EXECUTED",
            "PARTIAL": "PARTIAL_LOCAL_EXECUTED",
            "PLAN": "PLANNING_ONLY",
        }
        for binding in SKILL_REGISTRY.values():
            with self.subTest(skill=binding.skill):
                result = dispatch_skill(binding.skill, request())
                self.assertEqual(result["handler_id"], binding.handler_id)
                self.assertEqual(
                    result["state"], expected_states[binding.capability_state]
                )
                self.assertEqual(result["code"], binding.expected_success_code)
                self.assertNotEqual(result["code"], "LOCAL_OPERATION_COMPLETED")
                self.assertFalse(result["external_effects_performed"])
                self.assertEqual(result["external_evidence"], "NOT_RUN")
                self.assertEqual(result["certification"], "NOT_CERTIFIED")
                self.assertTrue(str(result["result_digest"]).startswith("sha256:"))

    def test_manifest_exposes_exact_code_and_test_bindings(self) -> None:
        manifest = capability_manifest()
        self.assertEqual(
            manifest["counts"], {"skills": 50, "local": 21, "partial": 24, "plan": 5}
        )
        self.assertEqual(
            [item["skill"] for item in manifest["capabilities"]],
            list(SKILL_REGISTRY),
        )
        self.assertTrue(all(item["code_path"] for item in manifest["capabilities"]))
        self.assertTrue(all(item["test_path"] for item in manifest["capabilities"]))

    def test_unknown_skill_and_request_authority_injection_fail_closed(self) -> None:
        with self.assertRaises(SkillRuntimeError):
            dispatch_skill("elmos-unknown", request())
        malformed = request()
        malformed["authorized_external_effects"] = ["push", "deploy"]
        result = dispatch_skill("elmos-project-fingerprinting", malformed)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertFalse(result["external_effects_performed"])

    def test_secret_findings_are_fingerprints_only(self) -> None:
        inputs = base_inputs()
        files = list(inputs["files"])
        literal = "super-secret-value"
        files.append({"path": "config/local.env", "text": f"API_KEY={literal}\n"})
        inputs["files"] = files
        result = dispatch_skill("elmos-security-threat-model", request(inputs))
        serialized = repr(result)
        self.assertNotIn(literal, serialized)
        self.assertTrue(result["outputs"]["threats"])
        self.assertTrue(
            all(
                item.get("secret_redacted", True)
                for item in result["outputs"]["threats"]
            )
        )

    def test_human_lock_and_release_certification_fail_closed(self) -> None:
        inputs = base_inputs()
        inputs.update(
            {"human_locked": True, "content": "human", "proposed_content": "agent"}
        )
        locked = dispatch_skill("elmos-artifact-versioning-human-lock", request(inputs))
        self.assertEqual(locked["state"], "BLOCKED")
        readiness = dispatch_skill("elmos-release-certification", request())
        self.assertEqual(readiness["outputs"]["decision"], "READY_FOR_EXTERNAL_GATE")
        self.assertFalse(readiness["outputs"]["certified"])
        self.assertFalse(readiness["outputs"]["release_authorized"])
        self.assertEqual(readiness["certification"], "NOT_CERTIFIED")


if __name__ == "__main__":
    unittest.main()

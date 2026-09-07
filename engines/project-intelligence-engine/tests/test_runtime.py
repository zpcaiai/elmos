from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

try:
    import jsonschema  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - dependency-free engine run
    jsonschema = None

from elmos_project_intelligence.canonical import canonical_digest
from elmos_project_intelligence.runtime import (
    SKILL_REGISTRY,
    SkillRuntimeError,
    capability_manifest,
    dispatch_skill,
    validate_skill_registry,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE_SCHEMA_ROOT = (
    REPOSITORY_ROOT / "skills/elmos-project-intelligence-skills-v1.1.0/schemas"
)


def sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


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
            "schema_version": 1,
            "diagram_id": sha("fixture-diagram"),
            "type": "component",
            "project_id": "project-a",
            "revision_id": "abc123",
            "nodes": [
                {"id": "api", "label": "Refund API", "kind": "service"},
                {"id": "store", "label": "Refund Store", "kind": "database"},
            ],
            "edges": [
                {
                    "id": "api-writes-store",
                    "source": "api",
                    "target": "store",
                    "kind": "writes",
                }
            ],
        },
        "patch": [{"node_id": "api", "label": "Refund HTTP API"}],
        "locked_node_ids": [],
        "artifacts": [
            {
                "artifact_id": "architecture",
                "digest": sha("architecture"),
                "media_type": "text/markdown",
                "content_text": "architecture",
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
        "as_of": "2026-08-24T00:00:00Z",
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
            "version": "0.1.0",
            "digest": sha("fixture-dap"),
            "capabilities": ["breakpoints", "stack", "variables"],
        },
        "runtime_profile": {
            "runtime_profile_id": "fixture-runtime",
            "image_digest": sha("fixture-runtime-image"),
            "toolchain": {"python": "3.12"},
        },
        "debug_target": {"kind": "test", "ref": "tests/test_app.py::test_refund"},
        "debug_mode": "guided",
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
            {"LOCAL": 19, "PARTIAL": 26, "PLAN": 5},
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
            manifest["counts"], {"skills": 50, "local": 19, "partial": 26, "plan": 5}
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

        secret = "sentinel-secret-path"
        duplicate_inputs = base_inputs()
        duplicate_inputs["files"] = [
            {"path": secret, "text": "first"},
            {"path": secret, "text": "second"},
        ]
        rejected = dispatch_skill(
            "elmos-project-fingerprinting", request(duplicate_inputs)
        )
        self.assertEqual(rejected["state"], "BLOCKED")
        self.assertNotIn(secret, repr(rejected))

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

    def test_diagram_projection_is_source_shaped_stable_and_evidence_bound(
        self,
    ) -> None:
        inputs = base_inputs()
        inputs["nodes"] = [
            {
                "name": "Refund API",
                "kind": "service",
                "evidence_refs": ["ev-1"],
            },
            {"id": "store", "name": "Refund Store", "kind": "database"},
        ]
        generated_api_id = canonical_digest(
            {
                "kind": "service",
                "label": "Refund API",
                "semantic": {},
                "evidence_refs": ["ev-1"],
            }
        )
        inputs["edges"] = [
            {
                "from": generated_api_id,
                "to": "store",
                "kind": "writes",
                "evidence_refs": ["ev-1"],
            }
        ]

        first = dispatch_skill("elmos-diagram-spec-engine", request(inputs))
        spec = first["outputs"]["diagram_spec"]
        self.assertEqual(spec["schema_version"], 1)
        self.assertEqual(spec["type"], "component")
        self.assertEqual(spec["project_id"], "project-a")
        self.assertEqual(spec["revision_id"], "abc123")
        self.assertEqual(
            first["outputs"]["digest"],
            canonical_digest(first["outputs"]["diagram_spec"]),
        )
        self.assertEqual(
            {node["id"] for node in spec["nodes"]}, {generated_api_id, "store"}
        )
        self.assertTrue(
            all(
                {"id", "source", "target", "kind"}.issubset(edge)
                and "from" not in edge
                and "to" not in edge
                for edge in spec["edges"]
            )
        )

        inputs["nodes"] = list(reversed(inputs["nodes"]))
        second = dispatch_skill("elmos-diagram-spec-engine", request(inputs))
        self.assertEqual(second["outputs"]["diagram_spec"], spec)
        self.assertEqual(second["outputs"]["digest"], first["outputs"]["digest"])

    def test_diagram_dangling_endpoints_evidence_and_legacy_renderer_fail_closed(
        self,
    ) -> None:
        dangling_edge = base_inputs()
        dangling_edge["edges"] = [{"from": "api", "to": "missing", "kind": "writes"}]
        rejected_edge = dispatch_skill(
            "elmos-diagram-spec-engine", request(dangling_edge)
        )
        self.assertEqual(rejected_edge["state"], "BLOCKED")

        dangling_evidence = base_inputs()
        dangling_evidence["nodes"] = [
            {
                "id": "api",
                "name": "Refund API",
                "kind": "service",
                "evidence_refs": ["missing-evidence"],
            }
        ]
        dangling_evidence["edges"] = []
        rejected_evidence = dispatch_skill(
            "elmos-diagram-spec-engine", request(dangling_evidence)
        )
        self.assertEqual(rejected_evidence["state"], "BLOCKED")

        legacy_renderer = base_inputs()
        legacy_spec = json.loads(json.dumps(legacy_renderer["diagram_spec"]))
        legacy_edge = legacy_spec["edges"][0]
        legacy_edge["from"] = legacy_edge.pop("source")
        legacy_edge["to"] = legacy_edge.pop("target")
        legacy_renderer["diagram_spec"] = legacy_spec
        rejected_legacy = dispatch_skill(
            "elmos-diagram-rendering", request(legacy_renderer)
        )
        self.assertEqual(rejected_legacy["state"], "BLOCKED")

        foreign_scope = base_inputs()
        foreign_scope["diagram_spec"] = json.loads(
            json.dumps(foreign_scope["diagram_spec"])
        )
        foreign_scope["diagram_spec"]["project_id"] = "project-b"
        rejected_foreign = dispatch_skill(
            "elmos-diagram-rendering", request(foreign_scope)
        )
        self.assertEqual(rejected_foreign["state"], "BLOCKED")

    def test_cache_key_binds_trusted_scope_schema_and_implementation(self) -> None:
        inputs = base_inputs()
        inputs["stage_inputs"] = {"payload": "same"}
        first = dispatch_skill("elmos-incremental-analysis-cache", request(inputs))
        first_outputs = first["outputs"]
        self.assertFalse(first_outputs["caller_reported_key_match"])
        self.assertEqual(first["state"], "PARTIAL_LOCAL_EXECUTED")
        self.assertEqual(first["code"], "ANALYSIS_CACHE_KEY_DERIVED")
        self.assertEqual(
            first["warnings"], ["caller-supplied-cache-key-not-content-verified"]
        )
        self.assertEqual(
            first["unavailable"],
            ["durable-scoped-cache-store", "cache-entry-content-verification"],
        )
        self.assertEqual(
            first_outputs["schema_version"],
            "elmos.project-intelligence.analysis-cache-key.v1",
        )
        self.assertEqual(
            first_outputs["implementation_version"],
            "elmos-project-intelligence-engine/1.1.0",
        )

        repeat_inputs = base_inputs()
        repeat_inputs["stage_inputs"] = {"payload": "same"}
        repeat_inputs["existing_cache_key"] = first_outputs["cache_key"]
        repeat = dispatch_skill(
            "elmos-incremental-analysis-cache", request(repeat_inputs)
        )
        self.assertTrue(repeat["outputs"]["caller_reported_key_match"])
        self.assertEqual(repeat["outputs"]["cache_key"], first_outputs["cache_key"])

        other_request = request(repeat_inputs)
        other_request["tenant_id"] = "tenant-b"
        other_tenant = dispatch_skill("elmos-incremental-analysis-cache", other_request)
        self.assertFalse(other_tenant["outputs"]["caller_reported_key_match"])
        self.assertNotEqual(
            other_tenant["outputs"]["cache_key"], first_outputs["cache_key"]
        )

        revision_inputs = base_inputs()
        revision_inputs["revision"] = "def456"
        revision_inputs["stage_inputs"] = {"payload": "same"}
        revision_inputs["existing_cache_key"] = first_outputs["cache_key"]
        revision_request = request(revision_inputs)
        revision_request["revision"] = "def456"
        other_revision = dispatch_skill(
            "elmos-incremental-analysis-cache", revision_request
        )
        self.assertFalse(other_revision["outputs"]["caller_reported_key_match"])
        self.assertNotEqual(
            other_revision["outputs"]["cache_key"], first_outputs["cache_key"]
        )

    def test_runtime_estimate_matches_nested_numeric_source_contract(self) -> None:
        result = dispatch_skill("elmos-runtime-cost-estimator", request())
        estimate = result["outputs"]
        self.assertEqual(estimate["project_revision_id"], "abc123")
        self.assertEqual(estimate["pipeline"], ["parse", "graph"])
        self.assertEqual(
            [stage["name"] for stage in estimate["stages"]], estimate["pipeline"]
        )
        self.assertIsInstance(
            estimate["system_wall_clock_eta"]["p50_seconds"], (int, float)
        )
        self.assertIsInstance(
            estimate["system_wall_clock_eta"]["p90_seconds"], (int, float)
        )
        self.assertGreaterEqual(
            estimate["system_wall_clock_eta"]["p90_seconds"],
            estimate["system_wall_clock_eta"]["p50_seconds"],
        )
        self.assertIn("p50_hours", estimate["human_review_effort"])
        self.assertIn("p90_hours", estimate["human_review_effort"])
        self.assertNotIn("human_review_effort_seconds", estimate)
        self.assertNotIn("system_wall_clock_eta_p50_seconds", estimate)

        for field_name, invalid in (
            ("human_review_effort_seconds", -1),
            ("workers", 0),
            ("workers", True),
            ("as_of", "not-a-date"),
        ):
            with self.subTest(field=field_name, invalid=invalid):
                inputs = base_inputs()
                inputs[field_name] = invalid
                rejected = dispatch_skill(
                    "elmos-runtime-cost-estimator", request(inputs)
                )
                self.assertEqual(rejected["state"], "BLOCKED")

    @unittest.skipIf(jsonschema is None, "jsonschema is needed for source parity")
    def test_diagram_and_estimate_outputs_validate_with_draft_2020_12(self) -> None:
        assert jsonschema is not None
        for skill, schema_name, output_key in (
            ("elmos-diagram-spec-engine", "diagram-spec.schema.json", "diagram_spec"),
            ("elmos-runtime-cost-estimator", "estimate.schema.json", None),
        ):
            with self.subTest(skill=skill):
                schema = json.loads((SOURCE_SCHEMA_ROOT / schema_name).read_text())
                jsonschema.Draft202012Validator.check_schema(schema)
                validator = jsonschema.Draft202012Validator(
                    schema,
                    format_checker=jsonschema.FormatChecker(),
                )
                result = dispatch_skill(skill, request())
                value = (
                    result["outputs"]
                    if output_key is None
                    else result["outputs"][output_key]
                )
                validator.validate(value)

    def test_mermaid_renderer_normalizes_injection_and_bounds_labels(self) -> None:
        inputs = base_inputs()
        injection = (
            'Refund API"]\n  attacker["injected"]\n'
            '%%{init: {"securityLevel": "loose"}}%%\n'
            'click n0 "https://example.invalid"\n<script>alert(1)</script>'
        )
        inputs["diagram_spec"] = {
            "schema_version": 1,
            "diagram_id": sha("injection-diagram"),
            "type": "component",
            "project_id": "project-a",
            "revision_id": "abc123",
            "nodes": [
                {"id": "api", "label": injection, "kind": "service"},
                {"id": "store", "label": "x" * 500, "kind": "database"},
            ],
            "edges": [
                {
                    "id": "api-store",
                    "source": "api",
                    "target": "store",
                    "kind": "relates",
                }
            ],
        }

        result = dispatch_skill("elmos-diagram-rendering", request(inputs))

        content = result["outputs"]["content"]
        self.assertEqual(result["code"], "SAFE_MERMAID_RENDERED")
        self.assertEqual(result["warnings"], ["diagram-labels-normalized"])
        self.assertEqual(len(content.splitlines()), 4)
        self.assertNotIn("%%", content)
        self.assertNotIn("<script", content)
        self.assertNotIn("https://", content)
        self.assertNotIn("attacker[", content)
        self.assertIn('n1["' + ("x" * 160) + '"]', content)

    def test_markdown_document_normalizes_untrusted_graph_text(self) -> None:
        inputs = base_inputs()
        inputs["nodes"] = [
            {
                "id": "api",
                "name": "refund`\n# injected\n<script>alert(1)</script>",
                "kind": "service] (https://example.invalid)",
            }
        ]
        inputs["edges"] = [
            {
                "from": "api\n## forged",
                "to": "store<script>",
                "kind": "writes`\n---",
            }
        ]

        result = dispatch_skill("elmos-architecture-documentation", request(inputs))

        content = result["outputs"]["content"]
        self.assertEqual(result["warnings"], ["markdown-fields-normalized"])
        self.assertNotIn("<script", content)
        self.assertNotIn("https://", content)
        self.assertNotIn("\n# injected", content)
        self.assertNotIn("\n## forged", content)
        self.assertNotIn("`", content)

    def test_report_bundle_requires_canonical_unique_content_digests(self) -> None:
        valid = dispatch_skill("elmos-project-report-bundle", request())
        self.assertTrue(valid["outputs"]["content_addressed"])
        self.assertTrue(valid["outputs"]["artifact_bytes_verified"])
        self.assertEqual(valid["outputs"]["artifacts"][0]["byte_count"], 12)
        self.assertEqual(
            valid["outputs"]["bundle_digest"],
            canonical_digest(valid["outputs"]["artifacts"]),
        )
        self.assertTrue(
            all(
                str(item["digest"]).startswith("sha256:")
                and str(item["digest"]) == str(item["digest"]).lower()
                for item in valid["outputs"]["artifacts"]
            )
        )

        malformed_inputs = base_inputs()
        malformed_inputs["artifacts"] = [
            {
                "artifact_id": "forged",
                "digest": "SHA256:" + ("A" * 64),
                "media_type": "application/json",
            }
        ]
        malformed = dispatch_skill(
            "elmos-project-report-bundle", request(malformed_inputs)
        )
        self.assertEqual(malformed["state"], "BLOCKED")
        self.assertEqual(malformed["code"], "REQUEST_OR_CAPABILITY_CONTRACT_REJECTED")

        duplicate_inputs = base_inputs()
        duplicate_inputs["artifacts"] = [
            {
                "artifact_id": "same",
                "digest": sha("one"),
                "content_text": "one",
            },
            {
                "artifact_id": "same",
                "digest": sha("two"),
                "content_text": "two",
            },
        ]
        duplicate = dispatch_skill(
            "elmos-project-report-bundle", request(duplicate_inputs)
        )
        self.assertEqual(duplicate["state"], "BLOCKED")

        binary_inputs = base_inputs()
        binary_inputs["artifacts"] = [
            {
                "artifact_id": "binary",
                "digest": sha_bytes(b"binary\x00"),
                "media_type": "application/octet-stream",
                "content_base64": "YmluYXJ5AA==",
            }
        ]
        binary = dispatch_skill("elmos-project-report-bundle", request(binary_inputs))
        self.assertEqual(binary["state"], "LOCAL_EXECUTED")
        self.assertEqual(binary["outputs"]["artifacts"][0]["byte_count"], 7)
        self.assertEqual(
            binary["outputs"]["artifacts"][0]["content_encoding"], "base64"
        )

        for artifact in (
            {
                "artifact_id": "mismatch",
                "digest": sha("different"),
                "content_text": "actual",
            },
            {"artifact_id": "missing", "digest": sha("")},
            {
                "artifact_id": "ambiguous",
                "digest": sha("same"),
                "content_text": "same",
                "content_base64": "c2FtZQ==",
            },
            {
                "artifact_id": "bad-base64",
                "digest": sha("bad"),
                "content_base64": "not base64!",
            },
        ):
            with self.subTest(artifact_id=artifact["artifact_id"]):
                invalid_inputs = base_inputs()
                invalid_inputs["artifacts"] = [artifact]
                invalid = dispatch_skill(
                    "elmos-project-report-bundle", request(invalid_inputs)
                )
                self.assertEqual(invalid["state"], "BLOCKED")

    def test_connector_and_debug_capabilities_default_deny_and_never_authorize(
        self,
    ) -> None:
        connector = dispatch_skill("elmos-integrations-mcp", request())
        self.assertEqual(connector["state"], "PLANNING_ONLY")
        self.assertFalse(connector["outputs"]["enforcement_authorized"])

        connector_inputs = base_inputs()
        connector_inputs["connector"] = {
            "id": "unsafe",
            "scopes": ["ADMIN", "write:*", "system:admin"],
        }
        rejected_connector = dispatch_skill(
            "elmos-integrations-mcp", request(connector_inputs)
        )
        self.assertEqual(rejected_connector["state"], "BLOCKED")
        self.assertEqual(rejected_connector["code"], "CONNECTOR_SCOPE_REJECTED")
        self.assertEqual(
            rejected_connector["outputs"]["forbidden_scopes"],
            ["ADMIN", "system:admin", "write:*"],
        )
        self.assertFalse(rejected_connector["outputs"]["enforcement_authorized"])

        debug = dispatch_skill("elmos-debug-adapter-gateway", request())
        self.assertEqual(debug["state"], "PARTIAL_LOCAL_EXECUTED")
        self.assertFalse(debug["outputs"]["enforcement_authorized"])

        debug_inputs = base_inputs()
        debug_inputs["adapter"] = {
            "id": "unsafe",
            "capabilities": ["breakpoints", "shell", "write-memory"],
        }
        debug_inputs["requested_capabilities"] = ["shell", "write-memory"]
        rejected_debug = dispatch_skill(
            "elmos-debug-adapter-gateway", request(debug_inputs)
        )
        self.assertEqual(rejected_debug["state"], "BLOCKED")
        self.assertEqual(rejected_debug["code"], "DEBUG_CAPABILITY_REJECTED")
        self.assertEqual(
            rejected_debug["outputs"]["forbidden"], ["shell", "write-memory"]
        )
        self.assertFalse(rejected_debug["outputs"]["enforcement_authorized"])

    def test_entitlements_are_caller_reported_and_non_authoritative(self) -> None:
        inputs = base_inputs()
        inputs["requested_features"] = ["reader", "admin-console"]
        inputs["entitled_features"] = ["reader", "admin-console"]

        result = dispatch_skill("elmos-commercial-packaging", request(inputs))

        outputs = result["outputs"]
        self.assertNotIn("allowed_features", outputs)
        self.assertEqual(
            outputs["caller_reported_allowed_features"],
            ["admin-console", "reader"],
        )
        self.assertEqual(
            outputs["caller_reported_entitled_features"],
            ["admin-console", "reader"],
        )
        self.assertFalse(outputs["enforcement_authorized"])
        self.assertFalse(outputs["billing_performed"])
        self.assertEqual(
            result["warnings"], ["caller-supplied-entitlements-unverified"]
        )

    def test_repository_shards_block_single_files_over_the_shard_limit(self) -> None:
        inputs = base_inputs()
        inputs["files"] = [{"path": "oversized.txt", "text": "x" * 33}]
        inputs["max_shard_bytes"] = 32

        rejected = dispatch_skill("elmos-large-repository-scaling", request(inputs))

        self.assertEqual(rejected["state"], "BLOCKED")
        self.assertEqual(rejected["code"], "SHARD_SIZE_LIMIT_EXCEEDED")
        self.assertEqual(rejected["outputs"]["oversized_paths"], ["oversized.txt"])
        self.assertEqual(rejected["outputs"]["shards"], [])
        self.assertFalse(rejected["outputs"]["distributed_execution"])

        planned = dispatch_skill("elmos-large-repository-scaling", request())
        self.assertEqual(planned["outputs"]["oversized_paths"], [])
        self.assertTrue(
            all(item["bytes"] <= 256 for item in planned["outputs"]["shards"])
        )

    def test_evidence_policy_and_release_claims_remain_unverified(self) -> None:
        evidence = dispatch_skill("elmos-evidence-provenance", request())
        self.assertEqual(
            evidence["outputs"]["bindings"][0]["confidence"],
            "REFERENCED_UNVERIFIED",
        )
        self.assertEqual(
            evidence["outputs"]["bindings"][0]["verification_state"], "NOT_RUN"
        )

        policy = dispatch_skill("elmos-collaboration-governance", request())
        self.assertEqual(policy["code"], "LOCAL_POLICY_SIMULATED")
        self.assertFalse(policy["outputs"]["enforcement_authorized"])
        self.assertTrue(policy["outputs"]["simulated_tenant_match"])

        release = dispatch_skill("elmos-release-certification", request())
        self.assertEqual(release["code"], "RELEASE_READINESS_PLANNED")
        self.assertEqual(release["outputs"]["decision"], "EXTERNAL_GATE_REQUIRED")
        self.assertFalse(release["outputs"]["certified"])
        self.assertFalse(release["outputs"]["release_authorized"])

    def test_static_navigation_and_lexical_qa_never_claim_confirmation(self) -> None:
        navigation = dispatch_skill("elmos-semantic-navigation", request())
        self.assertEqual(navigation["outputs"]["confidence"], "INFERRED")
        self.assertIn(
            "static-or-caller-supplied-symbols-unverified", navigation["warnings"]
        )

        supplied_inputs = base_inputs()
        supplied_inputs["symbols"] = [
            {"name": "Invented", "path": "src/none.py", "line": 1}
        ]
        supplied_inputs["symbol"] = "Invented"
        supplied = dispatch_skill("elmos-semantic-navigation", request(supplied_inputs))
        self.assertEqual(supplied["outputs"]["confidence"], "INFERRED")

        qa_inputs = base_inputs()
        qa_inputs["query"] = "refund endpoint"
        qa_inputs["files"] = [
            {
                "path": "README.md",
                "text": "The refund endpoint does not exist.\n",
            }
        ]
        qa = dispatch_skill("elmos-project-search-qa", request(qa_inputs))
        self.assertEqual(qa["outputs"]["confidence"], "LEXICAL_MATCH")
        self.assertNotEqual(qa["outputs"]["confidence"], "CONFIRMED")
        self.assertIn("lexical-match-is-not-semantic-confirmation", qa["warnings"])

    def test_debug_outputs_recursively_redact_and_enforce_hard_bounds(self) -> None:
        inputs = base_inputs()
        inputs["debug_events"] = [
            {
                "event_id": "event-sensitive",
                "sequence": 1,
                "kind": "stopped",
                "timestamp": "2026-08-24T00:00:00Z",
                "trace_id": "trace-sensitive",
                "Authorization": "Bearer bearer-secret-value",
                "context": {
                    "api_key": "nested-api-key-value",
                    "nested": {
                        "Password": "nested-password-value",
                        "message": "secret=inline-secret-value",
                        "release_authorized": True,
                    },
                },
                "log": (
                    "password=shrt42 "
                    "url=https://example.invalid/cb?access_token=x&safe=1 "
                    "Authorization: Basic z "
                    "X-API-Key: q "
                    "dsn=postgres://dbuser:p@db.invalid/app "
                    "Server=db;Password=r;User Id=app "
                    "secret=log-secret-value"
                ),
            }
        ]

        replay = dispatch_skill("elmos-debug-record-replay", request(inputs))
        correlation = dispatch_skill(
            "elmos-distributed-debug-correlation", request(inputs)
        )
        serialized = repr((replay, correlation))
        for secret in (
            "bearer-secret-value",
            "nested-api-key-value",
            "nested-password-value",
            "inline-secret-value",
            "log-secret-value",
            "shrt42",
            "access_token=x",
            "Basic z",
            "X-API-Key: q",
            "dbuser:p",
            "Password=r",
        ):
            self.assertNotIn(secret, serialized)
        self.assertGreater(
            replay["outputs"]["bundle"]["redaction"]["sensitive_fields_omitted"],
            0,
        )
        correlated_event = correlation["outputs"]["timelines"][0]["events"][0]
        self.assertEqual(
            set(correlated_event),
            {
                "event_id",
                "event_type",
                "occurred_at",
                "tenant_id",
                "project_id",
                "revision_id",
                "debug_session_id",
                "sequence",
                "redaction_profile",
                "payload",
            },
        )
        self.assertEqual(correlated_event["payload"]["trace_id"], "trace-sensitive")

        inputs["debug_events"] = [
            {"event_id": f"event-{index}", "sequence": index} for index in range(1_001)
        ]
        blocked = dispatch_skill("elmos-debug-record-replay", request(inputs))
        self.assertEqual(blocked["state"], "BLOCKED")
        self.assertEqual(blocked["code"], "REQUEST_OR_CAPABILITY_CONTRACT_REJECTED")

    def test_human_lock_and_release_certification_fail_closed(self) -> None:
        inputs = base_inputs()
        inputs.update(
            {"human_locked": True, "content": "human", "proposed_content": "agent"}
        )
        locked = dispatch_skill("elmos-artifact-versioning-human-lock", request(inputs))
        self.assertEqual(locked["state"], "BLOCKED")
        proposal = dispatch_skill("elmos-artifact-versioning-human-lock", request())
        self.assertEqual(proposal["state"], "PARTIAL_LOCAL_EXECUTED")
        self.assertEqual(proposal["code"], "ARTIFACT_VERSION_PROPOSAL_VALIDATED")
        self.assertFalse(proposal["outputs"]["authoritative_lock_verified"])
        self.assertFalse(proposal["outputs"]["version_persisted"])

        changed_inputs = base_inputs()
        changed_inputs.update(
            {
                "content": "v1",
                "proposed_content": "v2",
                "previous_version": 7,
                "human_locked": False,
            }
        )
        changed = dispatch_skill(
            "elmos-artifact-versioning-human-lock", request(changed_inputs)
        )
        self.assertEqual(changed["outputs"]["proposed_version"], 8)
        self.assertEqual(changed["outputs"]["content_digest"], canonical_digest("v2"))
        self.assertNotEqual(
            changed["outputs"]["content_digest"], canonical_digest("v1")
        )

        for invalid_previous_version in (-1, True):
            with self.subTest(previous_version=invalid_previous_version):
                invalid_inputs = base_inputs()
                invalid_inputs["previous_version"] = invalid_previous_version
                invalid = dispatch_skill(
                    "elmos-artifact-versioning-human-lock", request(invalid_inputs)
                )
                self.assertEqual(invalid["state"], "BLOCKED")
                self.assertEqual(
                    invalid["code"], "REQUEST_OR_CAPABILITY_CONTRACT_REJECTED"
                )
        readiness = dispatch_skill("elmos-release-certification", request())
        self.assertEqual(readiness["outputs"]["decision"], "EXTERNAL_GATE_REQUIRED")
        self.assertFalse(readiness["outputs"]["certified"])
        self.assertFalse(readiness["outputs"]["release_authorized"])
        self.assertEqual(readiness["certification"], "NOT_CERTIFIED")


if __name__ == "__main__":
    unittest.main()

"""Comprehensive behavioral and fail-closed security tests for the 10 frontier local semantic skills."""

from __future__ import annotations

from typing import Any
import unittest

from elmos_foundry.domain import TenantScope
from elmos_foundry.foundation_extensions import (
    FOUNDATION_EXTENSION_SKILLS,
    build_foundation_extension_handlers,
)
from elmos_foundry.graph_semantics import (
    GRAPH_SEMANTIC_SKILLS,
    build_graph_extension_handlers,
)
from elmos_foundry.ingestion_extensions import (
    INGESTION_EXTENSION_SKILLS,
    build_ingestion_extension_handlers,
)
from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.skills import load_compiled_catalog


class FrontierSemanticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = ExecutionKernel()
        self.scope = TenantScope(
            tenant_id="tenant-alpha",
            project_id="project-prime",
            actor_id="actor-test",
            environment_id="env-local",
            workspace_digest="sha256:" + "a" * 64,
            revision_set_id="sha256:" + "b" * 64,
            purpose="test-frontier-semantics",
            invocation_id="inv-001",
            lease_id="lease-001",
        )
        self.catalog = load_compiled_catalog()
        self.foundation_handlers = build_foundation_extension_handlers(self.catalog)
        self.ingestion_handlers = build_ingestion_extension_handlers(self.catalog)
        self.graph_handlers = build_graph_extension_handlers(self.catalog)

    def test_frontier_skill_sets_are_disjoint_and_complete(self) -> None:
        all_skills = FOUNDATION_EXTENSION_SKILLS | INGESTION_EXTENSION_SKILLS | GRAPH_SEMANTIC_SKILLS
        self.assertEqual(len(all_skills), 10)
        self.assertEqual(len(self.foundation_handlers), 2)
        self.assertEqual(len(self.ingestion_handlers), 4)
        self.assertEqual(len(self.graph_handlers), 4)

    # --- Pack 00 Foundation Extensions ---
    def test_contract_migration_manager_success(self) -> None:
        handler = self.foundation_handlers["contract-migration-manager"]
        payload = {
            "inputs": {
                "business requirement": {
                    "source_version": "1.0.0",
                    "target_version": "2.0.0",
                    "schema_changes": [{"kind": "add_field", "field": "email"}],
                },
                "architecture decision": {
                    "strategy": "expand-contract",
                    "rollback_strategy": "compensate-and-revert",
                },
                "policy profile": {
                    "tenant_id": self.scope.tenant_id,
                    "project_id": self.scope.project_id,
                    "compatibility_mode": "backward-compatible",
                },
                "runtime capability inventory": {"capabilities": ["schema.migrate"]},
            }
        }
        res = handler("contract-migration-manager", payload, self.scope, "inv-001")
        self.assertEqual(res["status"], "SUCCEEDED")
        self.assertIn("typed contract", res["outputs"])
        self.assertIn("compatibility declaration", res["outputs"])
        contract = res["outputs"]["typed contract"]
        self.assertEqual(contract["source_version"], "1.0.0")
        self.assertEqual(contract["target_version"], "2.0.0")
        self.assertTrue(contract["zero_downtime_supported"])

    def test_contract_migration_manager_same_version_fails(self) -> None:
        handler = self.foundation_handlers["contract-migration-manager"]
        payload = {
            "inputs": {
                "business requirement": {"source_version": "1.0.0", "target_version": "1.0.0"},
                "architecture decision": {"strategy": "expand-contract"},
                "policy profile": {},
                "runtime capability inventory": {},
            }
        }
        with self.assertRaises(ValueError):
            handler("contract-migration-manager", payload, self.scope, "inv-001")

    def test_contract_migration_manager_cross_tenant_fails(self) -> None:
        handler = self.foundation_handlers["contract-migration-manager"]
        payload = {
            "inputs": {
                "business requirement": {"source_version": "1.0.0", "target_version": "2.0.0"},
                "architecture decision": {"strategy": "expand-contract"},
                "policy profile": {"tenant_id": "other-tenant"},
                "runtime capability inventory": {},
            }
        }
        with self.assertRaises(ValueError):
            handler("contract-migration-manager", payload, self.scope, "inv-001")

    def test_extension_sdk_and_codegen_success(self) -> None:
        handler = self.foundation_handlers["extension-sdk-and-codegen"]
        payload = {
            "inputs": {
                "business requirement": {
                    "target_language": "typescript",
                    "package_name": "elmos-sdk-core",
                    "skills": ["artifact-identity-and-hashing", "typed-skill-contract"],
                },
                "architecture decision": {"generation_mode": "full-sdk"},
                "policy profile": {"tenant_id": self.scope.tenant_id},
                "runtime capability inventory": {},
            }
        }
        res = handler("extension-sdk-and-codegen", payload, self.scope, "inv-001")
        self.assertEqual(res["status"], "SUCCEEDED")
        contract = res["outputs"]["typed contract"]
        self.assertEqual(contract["target_language"], "typescript")
        self.assertEqual(contract["package_name"], "elmos-sdk-core")
        self.assertEqual(contract["skill_count"], 2)

    def test_extension_sdk_and_codegen_invalid_package_name(self) -> None:
        handler = self.foundation_handlers["extension-sdk-and-codegen"]
        payload = {
            "inputs": {
                "business requirement": {"package_name": "INVALID PACKAGE NAME!"},
                "architecture decision": {"generation_mode": "full-sdk"},
                "policy profile": {},
                "runtime capability inventory": {},
            }
        }
        with self.assertRaises(ValueError):
            handler("extension-sdk-and-codegen", payload, self.scope, "inv-001")

    # --- Pack 01 Ingestion Extensions ---
    def _base_ingestion_payload(self, doc_extra: dict[str, Any]) -> dict[str, Any]:
        document = {
            "tenant_id": self.scope.tenant_id,
            "project_id": self.scope.project_id,
            **doc_extra,
        }
        return {
            "inputs": {
                "repository": {"path": "src/module.py", "revision": "rev-1"},
                "document": document,
                "API schema": {"openapi": "3.1.0"},
                "database metadata": {"engine": "postgres"},
                "runtime trace": {"status": "PASS"},
                "ticket or incident": {"ticket_id": "TICK-100"},
            }
        }

    def test_archive_folder_ingestion_success(self) -> None:
        handler = self.ingestion_handlers["archive-and-folder-ingestion"]
        payload = self._base_ingestion_payload({
            "archive_type": "zip",
            "entries": [
                {"path": "package.json", "size_bytes": 256, "sha256": "1" * 64},
                {"path": "src/index.ts", "size_bytes": 1024, "sha256": "2" * 64},
            ],
        })
        res = handler("archive-and-folder-ingestion", payload, self.scope, "inv-001")
        self.assertEqual(res["status"], "SUCCEEDED")
        artifact = res["outputs"]["normalized artifact"]["normalized"]
        self.assertEqual(artifact["entry_count"], 2)
        self.assertEqual(artifact["total_size_bytes"], 1280)

    def test_archive_folder_ingestion_path_traversal_rejected(self) -> None:
        handler = self.ingestion_handlers["archive-and-folder-ingestion"]
        payload = self._base_ingestion_payload({
            "archive_type": "zip",
            "entries": [
                {"path": "../../etc/passwd", "size_bytes": 100, "sha256": "3" * 64},
            ],
        })
        with self.assertRaises(ValueError):
            handler("archive-and-folder-ingestion", payload, self.scope, "inv-001")

    def test_document_structure_ingestion_success(self) -> None:
        handler = self.ingestion_handlers["document-structure-ingestion"]
        payload = self._base_ingestion_payload({
            "headings": [
                {"title": "Chapter 1", "level": 1, "line": 1},
                {"title": "Section 1.1", "level": 2, "line": 10},
            ],
            "code_blocks": [
                {"language": "python", "code": "def hello(): pass"},
            ],
        })
        res = handler("document-structure-ingestion", payload, self.scope, "inv-001")
        self.assertEqual(res["status"], "SUCCEEDED")
        artifact = res["outputs"]["normalized artifact"]["normalized"]
        self.assertEqual(artifact["section_count"], 2)
        self.assertEqual(artifact["code_block_count"], 1)

    def test_ingestion_quarantine_gate_cleared(self) -> None:
        handler = self.ingestion_handlers["ingestion-quarantine-gate"]
        payload = self._base_ingestion_payload({
            "artifact_digest": "sha256:" + "4" * 64,
            "content_sample": "normal documentation text",
        })
        res = handler("ingestion-quarantine-gate", payload, self.scope, "inv-001")
        self.assertEqual(res["status"], "SUCCEEDED")
        artifact = res["outputs"]["normalized artifact"]["normalized"]
        self.assertEqual(artifact["quarantine_status"], "CLEARED")

    def test_ingestion_quarantine_gate_rejected_suspicious(self) -> None:
        handler = self.ingestion_handlers["ingestion-quarantine-gate"]
        payload = self._base_ingestion_payload({
            "artifact_digest": "sha256:" + "4" * 64,
            "content_sample": "eval(dangerous_code)",
        })
        res = handler("ingestion-quarantine-gate", payload, self.scope, "inv-001")
        self.assertEqual(res["status"], "SUCCEEDED")
        artifact = res["outputs"]["normalized artifact"]["normalized"]
        self.assertEqual(artifact["quarantine_status"], "QUARANTINED")
        self.assertEqual(artifact["admission_decision"], "DENIED")

    def test_ingestion_quarantine_gate_invalid_digest_rejected(self) -> None:
        handler = self.ingestion_handlers["ingestion-quarantine-gate"]
        payload = self._base_ingestion_payload({
            "artifact_digest": "not-valid-sha256",
            "content_sample": "clean documentation text",
        })
        with self.assertRaises(ValueError):
            handler("ingestion-quarantine-gate", payload, self.scope, "inv-001")

    def test_multimodal_artifact_ingestion_success(self) -> None:
        handler = self.ingestion_handlers["multimodal-artifact-ingestion"]
        payload = self._base_ingestion_payload({
            "mime_type": "image/jpeg",
            "byte_size": 2048,
            "content_digest": "sha256:" + "4" * 64,
            "modality": "image",
            "metadata": {"format": "jpeg"},
        })
        res = handler("multimodal-artifact-ingestion", payload, self.scope, "inv-001")
        self.assertEqual(res["status"], "SUCCEEDED")
        artifact = res["outputs"]["normalized artifact"]["normalized"]
        self.assertEqual(artifact["media_count"], 1)
        self.assertEqual(artifact["modality"], "image")

    # --- Pack 02 Semantic Graph Extensions ---
    def _base_graph_payload(self) -> dict[str, Any]:
        return {
            "inputs": {
                "normalized repository artifact": {
                    "tenant_id": self.scope.tenant_id,
                    "project_id": self.scope.project_id,
                    "modules": [
                        {
                            "name": "service",
                            "path": "src/service.py",
                            "symbols": [
                                {"name": "Service", "kind": "class", "line": 10},
                                {"name": "run", "kind": "function", "line": 20, "calls": ["step", "log"]},
                                {"name": "step", "kind": "function", "line": 30, "calls": ["log"]},
                                {"name": "log", "kind": "function", "line": 40},
                            ],
                            "ast_nodes": [
                                {
                                    "type": "FunctionDef",
                                    "name": "run",
                                    "blocks": ["b0", "b1", "b2"],
                                    "edges": [["b0", "b1"], ["b1", "b2"]],
                                }
                            ],
                            "diff": {
                                "modified_symbols": ["run"],
                                "lines_added": 5,
                                "lines_removed": 2,
                            },
                        }
                    ],
                },
                "build metadata": {"status": "SUCCESS"},
                "runtime trace": {"traces": []},
                "test result": {"passed": True},
            }
        }

    def test_symbol_and_reference_graph(self) -> None:
        handler = self.graph_handlers["symbol-and-reference-graph"]
        res = handler("symbol-and-reference-graph", self._base_graph_payload(), self.scope, "inv-001")
        self.assertEqual(res["status"], "SUCCEEDED")
        graph = res["outputs"]["semantic graph"]
        self.assertEqual(graph["symbol_count"], 4)
        self.assertIn("symbols", graph)

    def test_call_graph_construction(self) -> None:
        handler = self.graph_handlers["call-graph-construction"]
        res = handler("call-graph-construction", self._base_graph_payload(), self.scope, "inv-001")
        self.assertEqual(res["status"], "SUCCEEDED")
        graph = res["outputs"]["semantic graph"]
        self.assertGreater(graph["edge_count"], 0)
        self.assertFalse(graph["has_cycles"])

    def test_control_flow_graph(self) -> None:
        handler = self.graph_handlers["control-flow-graph"]
        res = handler("control-flow-graph", self._base_graph_payload(), self.scope, "inv-001")
        self.assertEqual(res["status"], "SUCCEEDED")
        graph = res["outputs"]["semantic graph"]
        self.assertEqual(graph["block_count"], 3)
        self.assertEqual(graph["cfg_edge_count"], 2)

    def test_semantic_diff_and_impact_analysis(self) -> None:
        handler = self.graph_handlers["semantic-diff-and-impact-analysis"]
        res = handler("semantic-diff-and-impact-analysis", self._base_graph_payload(), self.scope, "inv-001")
        self.assertEqual(res["status"], "SUCCEEDED")
        diff = res["outputs"]["semantic diff"]
        self.assertIn("run", diff["affected_symbols"])
        self.assertEqual(diff["blast_radius_score"], 0.5)


if __name__ == "__main__":
    unittest.main()

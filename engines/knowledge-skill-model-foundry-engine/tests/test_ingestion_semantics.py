"""Behavioral and negative tests for exact local Knowledge Fabric ingestion."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Any
import unittest

from elmos_foundry.domain import TenantScope
from elmos_foundry.ingestion_semantics import (
    INGESTION_SEMANTIC_SKILLS,
    build_ingestion_handlers,
)
from elmos_foundry.kernel import ExecutionKernel


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def fixture_inputs(skill: str, scope: TenantScope) -> dict[str, Any]:
    repository: dict[str, Any] = {
        "repository_id": "repository-local",
        "tenant_id": scope.tenant_id,
        "project_id": scope.project_id,
        "base_revision": _digest("1"),
        "target_revision": _digest("2"),
        "base_files": [
            {"path": "README.md", "content_digest": _digest("3"), "mode": "REGULAR"},
            {"path": "src/old.py", "content_digest": _digest("4"), "mode": "REGULAR"},
        ],
        "target_files": [
            {"path": "README.md", "content_digest": _digest("5"), "mode": "REGULAR"},
            {"path": "src/new.py", "content_digest": _digest("6"), "mode": "REGULAR"},
        ],
    }
    document: dict[str, Any] = {"source_id": "document-local"}
    api_schema: dict[str, Any] = {
        "format": "OPENAPI",
        "version": "3.1.0",
        "source_digest": _digest("7"),
        "operations": [
            {
                "id": "get-user",
                "kind": "HTTP",
                "method": "get",
                "path": "/users/{id}",
                "input_digest": _digest("8"),
                "output_digest": _digest("9"),
            },
            {
                "id": "create-user",
                "kind": "HTTP",
                "method": "post",
                "path": "/users",
                "input_digest": _digest("a"),
                "output_digest": _digest("b"),
            },
        ],
    }
    database: dict[str, Any] = {
        "engine": "postgresql",
        "engine_version": "17.2",
        "snapshot_digest": _digest("c"),
        "objects": [
            {
                "kind": "TABLE",
                "schema": "public",
                "name": "users",
                "definition_digest": _digest("d"),
                "dependencies": [],
            },
            {
                "kind": "VIEW",
                "schema": "public",
                "name": "active_users",
                "definition_digest": _digest("e"),
                "dependencies": ["public.users"],
            },
        ],
        "plans": [
            {
                "query_id": "active-user-query",
                "plan_digest": _digest("f"),
                "objects": ["public.active_users", "public.users"],
            }
        ],
    }
    runtime_trace: dict[str, Any] = {
        "format": "OTLP",
        "source_digest": _digest("0"),
        "spans": [
            {
                "span_id": "span-root",
                "parent_span_id": None,
                "service": "api-service",
                "operation": "GET /users/{id}",
                "start_ns": 10,
                "end_ns": 30,
                "code_entity": "src/api.py:get_user",
            },
            {
                "span_id": "span-db",
                "parent_span_id": "span-root",
                "service": "api-service",
                "operation": "SELECT users",
                "start_ns": 15,
                "end_ns": 25,
                "code_entity": "src/store.py:get_user",
            },
        ],
        "metrics": [{"name": "request-duration", "value": 20, "unit": "nanoseconds"}],
        "logs": [
            {
                "timestamp": "2026-09-07T00:00:20Z",
                "severity": "INFO",
                "message_digest": _digest("1"),
                "span_id": "span-root",
            }
        ],
    }
    ticket: dict[str, Any] = {"ticket_id": "ticket-local"}
    if skill == "source-freshness-and-expiry":
        document = {
            "source_id": "document-local",
            "version": "v2",
            "observed_at": "2026-09-01T00:00:00Z",
            "valid_from": "2026-09-01T00:00:00Z",
            "expires_at": "2026-10-01T00:00:00Z",
            "last_verified_at": "2026-09-06T00:00:00Z",
            "refresh_sla_seconds": 172_800,
            "applies_to_versions": ["v1", "v2"],
        }
        ticket = {"evaluated_at": "2026-09-07T00:00:00Z", "target_version": "v2"}
    elif skill == "license-and-rights-classification":
        document = {
            "source_id": "document-local",
            "content_digest": _digest("2"),
            "license_expression": "Apache-2.0",
            "contract_restrictions": [],
            "training_use": "ALLOW",
            "redistribution": "ALLOW",
            "attribution_required": True,
            "notice_digest": _digest("3"),
            "territories": ["*"],
            "purposes": ["*"],
        }
    return {
        "repository": repository,
        "document": document,
        "API schema": api_schema,
        "database metadata": database,
        "runtime trace": runtime_trace,
        "ticket or incident": ticket,
    }


class IngestionSemanticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = ExecutionKernel()
        self.scope = self.kernel.mint_context(
            tenant_id="tenant-ingestion",
            project_id="project-ingestion",
            actor_id="actor-ingestion",
            environment_id="environment-local",
            workspace_digest=_digest("a"),
            revision_set_id=_digest("b"),
            purpose="ingestion-tests",
            capabilities=("foundry.adapter.execute",),
            ttl_seconds=600,
            invocation_id="invocation-ingestion",
            lease_id="lease-ingestion",
        )
        self.handlers = build_ingestion_handlers(
            SimpleNamespace(
                content_sha256="a" * 64,
                discovery={"candidate_limit": 16, "activation_limit": 8},
                atomic_skills={name: {} for name in INGESTION_SEMANTIC_SKILLS},
                meta_skills={},
            )
        )

    def invoke(self, skill: str, inputs: dict[str, Any] | None = None) -> Any:
        return self.handlers[skill](
            skill,
            {"inputs": fixture_inputs(skill, self.scope) if inputs is None else inputs},
            self.scope,
            self.scope.invocation_id,
        )

    def test_exact_registry_and_declared_outputs(self) -> None:
        self.assertEqual(INGESTION_SEMANTIC_SKILLS, set(self.handlers))
        for skill in sorted(self.handlers):
            with self.subTest(skill=skill):
                result = self.invoke(skill)
                self.assertEqual("SUCCEEDED", result["status"])
                self.assertEqual(
                    {"normalized artifact", "source provenance", "rights classification", "freshness status"},
                    set(result["outputs"]),
                )
                self.assertEqual("NOT_RUN", result["external_evidence_status"])
                self.assertEqual("NOT_CERTIFIED", result["certification_status"])
                self.assertFalse(result["outputs"]["normalized artifact"]["external_effects_executed"])
                self.assertFalse(result["outputs"]["source provenance"]["caller_facts_verified"])

    def test_repository_delta_is_exact_and_deterministic(self) -> None:
        first = self.invoke("repository-incremental-ingestion")["outputs"]["normalized artifact"]
        values = fixture_inputs("repository-incremental-ingestion", self.scope)
        values["repository"]["base_files"].reverse()
        values["repository"]["target_files"].reverse()
        second = self.invoke("repository-incremental-ingestion", values)["outputs"]["normalized artifact"]
        self.assertEqual(first["normalized"], second["normalized"])
        delta = first["normalized"]
        self.assertEqual(["src/new.py"], [item["path"] for item in delta["added"]])
        self.assertEqual(["README.md"], [item["path"] for item in delta["modified"]])
        self.assertEqual(["src/old.py"], [item["path"] for item in delta["deleted"]])
        self.assertEqual("NOT_RUN", delta["native_repository_read_status"])

    def test_repository_rejects_scope_escape_and_unsafe_paths(self) -> None:
        for field, value, error in (
            ("tenant_id", "other-tenant", "tenant/project"),
            ("project_id", "other-project", "tenant/project"),
        ):
            inputs = fixture_inputs("repository-incremental-ingestion", self.scope)
            inputs["repository"][field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, error):
                    self.invoke("repository-incremental-ingestion", inputs)
        inputs = fixture_inputs("repository-incremental-ingestion", self.scope)
        inputs["repository"]["target_files"][0]["path"] = "../secret"
        with self.assertRaisesRegex(ValueError, "canonical relative"):
            self.invoke("repository-incremental-ingestion", inputs)

    def test_api_contract_normalizes_and_rejects_duplicate_operations(self) -> None:
        normalized = self.invoke("api-contract-ingestion")["outputs"]["normalized artifact"]["normalized"]
        self.assertEqual(["create-user", "get-user"], [row["id"] for row in normalized["operations"]])
        self.assertEqual(["POST", "GET"], [row["method"] for row in normalized["operations"]])
        self.assertEqual("NOT_RUN", normalized["native_parser_status"])
        inputs = fixture_inputs("api-contract-ingestion", self.scope)
        inputs["API schema"]["operations"].append(deepcopy(inputs["API schema"]["operations"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate operation"):
            self.invoke("api-contract-ingestion", inputs)

    def test_database_metadata_binds_dependencies_and_plans(self) -> None:
        normalized = self.invoke("database-metadata-ingestion")["outputs"]["normalized artifact"]["normalized"]
        self.assertEqual(["public.active_users", "public.users"], [row["id"] for row in normalized["objects"]])
        self.assertEqual("NOT_RUN", normalized["native_database_status"])
        inputs = fixture_inputs("database-metadata-ingestion", self.scope)
        inputs["database metadata"]["objects"][1]["dependencies"] = ["public.missing"]
        with self.assertRaisesRegex(ValueError, "unknown dependencies"):
            self.invoke("database-metadata-ingestion", inputs)
        inputs = fixture_inputs("database-metadata-ingestion", self.scope)
        inputs["database metadata"]["plans"][0]["objects"] = ["public.missing"]
        with self.assertRaisesRegex(ValueError, "unknown database objects"):
            self.invoke("database-metadata-ingestion", inputs)

    def test_runtime_trace_validates_graph_time_and_references(self) -> None:
        normalized = self.invoke("runtime-trace-ingestion")["outputs"]["normalized artifact"]["normalized"]
        self.assertEqual([10, 20], [span["duration_ns"] for span in normalized["spans"]])
        self.assertEqual("NOT_RUN", normalized["native_telemetry_read_status"])
        inputs = fixture_inputs("runtime-trace-ingestion", self.scope)
        inputs["runtime trace"]["spans"][0]["parent_span_id"] = "span-db"
        with self.assertRaisesRegex(ValueError, "cycle"):
            self.invoke("runtime-trace-ingestion", inputs)
        inputs = fixture_inputs("runtime-trace-ingestion", self.scope)
        inputs["runtime trace"]["logs"][0]["span_id"] = "span-missing"
        with self.assertRaisesRegex(ValueError, "unknown span"):
            self.invoke("runtime-trace-ingestion", inputs)

    def test_freshness_uses_supplied_evaluation_time(self) -> None:
        def status(evaluated_at: str, target: str = "v2") -> str:
            inputs = fixture_inputs("source-freshness-and-expiry", self.scope)
            inputs["ticket or incident"] = {
                "evaluated_at": evaluated_at,
                "target_version": target,
            }
            return str(self.invoke("source-freshness-and-expiry", inputs)["outputs"]["freshness status"]["status"])

        self.assertEqual("FRESH", status("2026-09-07T00:00:00Z"))
        self.assertEqual("REFRESH_DUE", status("2026-09-09T00:00:01Z"))
        self.assertEqual("EXPIRED", status("2026-10-01T00:00:00Z"))
        self.assertEqual("INAPPLICABLE", status("2026-09-07T00:00:00Z", "v3"))

    def test_rights_are_conservative_and_never_claim_legal_review(self) -> None:
        rights = self.invoke("license-and-rights-classification")["outputs"]["rights classification"]
        self.assertEqual("CALLER_DECLARED", rights["decision"])
        self.assertTrue(rights["training_allowed"])
        self.assertEqual("NOT_RUN", rights["legal_review_status"])
        inputs = fixture_inputs("license-and-rights-classification", self.scope)
        inputs["document"]["contract_restrictions"] = ["customer-only"]
        restricted = self.invoke("license-and-rights-classification", inputs)["outputs"]["rights classification"]
        self.assertEqual("REVIEW_REQUIRED", restricted["decision"])
        self.assertFalse(restricted["training_allowed"])
        inputs = fixture_inputs("license-and-rights-classification", self.scope)
        inputs["document"]["notice_digest"] = None
        with self.assertRaisesRegex(ValueError, "attribution requires"):
            self.invoke("license-and-rights-classification", inputs)

    def test_outer_input_contract_is_exact_and_nonempty(self) -> None:
        for skill in sorted(self.handlers):
            inputs = fixture_inputs(skill, self.scope)
            inputs["unexpected"] = {"value": True}
            with self.subTest(skill=skill, case="extra"):
                with self.assertRaisesRegex(ValueError, "keys are not exact"):
                    self.invoke(skill, inputs)
            inputs = fixture_inputs(skill, self.scope)
            inputs["document"] = {}
            with self.subTest(skill=skill, case="empty"):
                with self.assertRaisesRegex(ValueError, "non-empty"):
                    self.invoke(skill, inputs)


if __name__ == "__main__":
    unittest.main()

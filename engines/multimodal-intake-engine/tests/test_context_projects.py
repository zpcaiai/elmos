from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import math
import zipfile
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

from elmos_multimodal_intake.context import operate_project_memory
from elmos_multimodal_intake.projects import extract_archive_safely
from elmos_multimodal_intake.skill_runtime import dispatch_skill


def sha_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha_bytes(encoded)


def request(inputs: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "request_id": "request-context-projects",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "actor_id": "actor-a",
        "inputs": dict(inputs),
        **extra,
    }


def trusted_capability() -> dict[str, Any]:
    return {
        "provider": "provider-a",
        "model_id": "model-a",
        "model_version": "2026-08-20",
        "context_window_tokens": 100_000,
        "max_output_tokens": 10_000,
        "source": "signed-registry",
        "trust": "SIGNED_REGISTRY",
        "observed_at": 1_700_000_000,
        "expires_at": 2_000_000_000,
    }


def test_capability_snapshot_is_versioned_and_stale_snapshot_blocks() -> None:
    observation = trusted_capability()
    valid = dispatch_skill(
        "elmos-model-capability-discovery",
        request(
            {"observation": observation},
            capabilities={
                "model_capability_observation": observation,
                "model_capability_now": 1_800_000_000,
            },
        ),
    )
    assert valid["state"] == "SUCCEEDED"
    assert valid["outputs"]["snapshot"]["snapshot_digest"].startswith("sha256:")
    assert valid["outputs"]["snapshot"]["context_window_tokens"] != valid["outputs"]["snapshot"]["max_output_tokens"]

    stale = trusted_capability()
    stale["expires_at"] = 1_750_000_000
    blocked = dispatch_skill(
        "elmos-model-capability-discovery",
        request(
            {"observation": stale},
            capabilities={
                "model_capability_observation": stale,
                "model_capability_now": 1_800_000_000,
            },
        ),
    )
    assert blocked["state"] == "BLOCKED"
    assert blocked["code"] == "MODEL_CAPABILITY_STALE"

    self_attested = dispatch_skill(
        "elmos-model-capability-discovery",
        request({"observation": observation}),
    )
    assert self_attested["state"] == "BLOCKED"
    assert self_attested["code"] == "MODEL_CAPABILITY_UNTRUSTED"


def test_configured_capability_clock_cannot_freeze_host_expiry() -> None:
    observation = trusted_capability()
    with patch(
        "elmos_multimodal_intake.context.time.time",
        return_value=2_100_000_001,
    ):
        result = dispatch_skill(
            "elmos-model-capability-discovery",
            request(
                {"observation": observation},
                capabilities={
                    "model_capability_observation": observation,
                    "model_capability_now": 1_800_000_000,
                },
            ),
        )

    assert result["state"] == "BLOCKED"
    assert result["code"] == "MODEL_CAPABILITY_STALE"


def test_multimodal_accounting_is_nonzero_and_budget_uses_safe_upper_bounds() -> None:
    accounted = dispatch_skill(
        "elmos-multimodal-token-accounting",
        request(
            {
                "model_version": "model-a-v1",
                "items": [
                    {"item_id": "text", "modality": "text", "text": "hello world"},
                    {"item_id": "image", "modality": "image", "width": 1024, "height": 768},
                    {"item_id": "audio", "modality": "audio", "duration_seconds": 12.5},
                ],
            }
        ),
    )
    assert accounted["state"] == "SUCCEEDED"
    assert all(item["tokens"] > 0 for item in accounted["outputs"]["estimates"])

    observation = trusted_capability()
    discovered = dispatch_skill(
        "elmos-model-capability-discovery",
        request(
            {"observation": observation},
            capabilities={
                "model_capability_observation": observation,
                "model_capability_now": 1_800_000_000,
            },
        ),
    )
    snapshot = discovered["outputs"]["snapshot"]
    budget = dispatch_skill(
        "elmos-context-budget-manager",
        request(
            {
                "capability_snapshot": snapshot,
                "usage": {"document": accounted["outputs"]["safe_total_tokens"], "tool_schema": 300},
                "reserved_output_tokens": 10_000,
                "safety_headroom_tokens": 5_000,
            },
            capabilities={"model_capability_snapshot": snapshot},
        ),
    )
    assert budget["state"] == "SUCCEEDED"
    assert budget["outputs"]["input_used_tokens"] + budget["outputs"]["reserved_output_tokens"] + budget["outputs"]["safety_headroom_tokens"] <= budget["outputs"]["context_window_tokens"]

    expired_reuse = dispatch_skill(
        "elmos-context-budget-manager",
        request(
            {
                "capability_snapshot": snapshot,
                "usage": {"document": 1},
            },
            capabilities={
                "model_capability_snapshot": snapshot,
                "model_capability_now": 2_100_000_000,
            },
        ),
    )
    assert expired_reuse["state"] == "BLOCKED"
    assert expired_reuse["code"] == "CAPABILITY_UNKNOWN"

    invalid_duration = dispatch_skill(
        "elmos-multimodal-token-accounting",
        request({"items": [{"item_id": "bad", "modality": "audio", "duration_seconds": math.nan}]}),
    )
    assert invalid_duration["state"] == "BLOCKED"
    assert invalid_duration["code"] == "REQUEST_CONTRACT_REJECTED"

    invalid_usage = dispatch_skill(
        "elmos-context-budget-manager",
        request(
            {"capability_snapshot": snapshot, "usage": {"document": -1}},
            capabilities={"model_capability_snapshot": snapshot},
        ),
    )
    assert invalid_usage["state"] == "BLOCKED"
    assert invalid_usage["code"] == "DOMAIN_INPUT_REJECTED"


def test_verified_token_measurement_binds_content_source_model_and_tokenizer() -> None:
    item = {
        "item_id": "measured-text",
        "modality": "text",
        "text": "exact measured content",
        "source_digest": sha_bytes(b"exact measured content"),
        "measured_tokens": 7,
    }
    inputs = {
        "model_id": "model-a",
        "model_version": "2026-08-20",
        "tokenizer_id": "tokenizer-a",
        "tokenizer_version": "3.1.0",
        "items": [item],
    }
    binding = {
        "item_id": item["item_id"],
        "source_digest": item["source_digest"],
        "content_digest": sha_json(
            {key: value for key, value in item.items() if key != "measured_tokens"}
        ),
        "model_id": inputs["model_id"],
        "model_version": inputs["model_version"],
        "tokenizer_id": inputs["tokenizer_id"],
        "tokenizer_version": inputs["tokenizer_version"],
        "measured_tokens": item["measured_tokens"],
        "registry_version": "token-measurements-v1",
    }
    capabilities = {
        "verified_token_measurements": {
            "version": "token-measurements-v1",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "measurements": [{**binding, "measurement_digest": sha_json(binding)}],
        }
    }
    measured = dispatch_skill(
        "elmos-multimodal-token-accounting",
        request(inputs, capabilities=capabilities),
    )
    assert measured["state"] == "SUCCEEDED"
    assert measured["outputs"]["estimates"][0]["status"] == "MEASURED_VERIFIED"
    assert measured["outputs"]["estimates"][0]["measurement_binding_digest"] == sha_json(binding)

    for field, replacement in (
        ("model_version", "2026-08-21"),
        ("tokenizer_version", "3.1.1"),
    ):
        drifted_inputs = json.loads(json.dumps(inputs))
        drifted_inputs[field] = replacement
        drifted = dispatch_skill(
            "elmos-multimodal-token-accounting",
            request(drifted_inputs, capabilities=capabilities),
        )
        assert drifted["state"] == "BLOCKED"
        assert drifted["outputs"]["unbounded_item_ids"] == ["measured-text"]

    content_drift = json.loads(json.dumps(inputs))
    content_drift["items"][0]["text"] = "changed content with the same item id and count"
    changed = dispatch_skill(
        "elmos-multimodal-token-accounting",
        request(content_drift, capabilities=capabilities),
    )
    assert changed["state"] == "BLOCKED"
    assert changed["outputs"]["unbounded_item_ids"] == ["measured-text"]

    source_drift = json.loads(json.dumps(inputs))
    source_drift["items"][0]["source_digest"] = sha_bytes(b"different-source")
    changed_source = dispatch_skill(
        "elmos-multimodal-token-accounting",
        request(source_drift, capabilities=capabilities),
    )
    assert changed_source["state"] == "BLOCKED"
    assert changed_source["outputs"]["unbounded_item_ids"] == ["measured-text"]

    legacy_count_only = dispatch_skill(
        "elmos-multimodal-token-accounting",
        request(inputs, capabilities={"verified_token_measurements": {"measured-text": 7}}),
    )
    assert legacy_count_only["state"] == "BLOCKED"
    assert legacy_count_only["code"] == "DOMAIN_INPUT_REJECTED"


def test_capacity_parity_requires_trusted_snapshot_and_outer_policy() -> None:
    observation = trusted_capability()
    discovered = dispatch_skill(
        "elmos-model-capability-discovery",
        request(
            {"observation": observation},
            capabilities={
                "model_capability_observation": observation,
                "model_capability_now": 1_800_000_000,
            },
        ),
    )
    snapshot = discovered["outputs"]["snapshot"]
    injected = dispatch_skill(
        "elmos-codex-context-capacity-parity",
        request(
            {
                "capability_snapshot": snapshot,
                "parity_policy": {
                    "minimum_context_window_tokens": 1,
                    "minimum_output_tokens": 1,
                },
            },
            capabilities={"model_capability_snapshot": snapshot},
        ),
    )
    assert injected["state"] == "BLOCKED"
    assert injected["code"] == "PARITY_POLICY_UNTRUSTED"

    trusted = dispatch_skill(
        "elmos-codex-context-capacity-parity",
        request(
            {"capability_snapshot": snapshot},
            capabilities={"model_capability_snapshot": snapshot},
            policy={
                "context_parity": {
                    "minimum_context_window_tokens": 90_000,
                    "minimum_output_tokens": 8_000,
                    "version": "p1",
                }
            },
        ),
    )
    assert trusted["state"] == "SUCCEEDED"
    assert trusted["outputs"]["policy_version"] == "p1"


def test_context_packing_pins_p0_p1_and_is_deterministic() -> None:
    inputs = {
        "effective_input_budget": 100,
        "candidates": [
            {"item_id": "ordinary", "priority": "P3", "tokens": 70, "relevance": 1.0, "freshness": 1.0},
            {"item_id": "latest-request", "priority": "P0", "tokens": 30, "relevance": 0.2, "freshness": 1.0},
            {"item_id": "acceptance", "priority": "P1", "tokens": 30, "relevance": 0.2, "freshness": 1.0},
        ],
    }
    left = dispatch_skill("elmos-long-context-packing-and-ranking", request(inputs))
    right = dispatch_skill("elmos-long-context-packing-and-ranking", request(inputs))
    included = {item["item_id"] for item in left["outputs"]["included"]}
    assert included == {"latest-request", "acceptance"}
    assert left["outputs"]["plan_digest"] == right["outputs"]["plan_digest"]

    negative = dispatch_skill(
        "elmos-long-context-packing-and-ranking",
        request(
            {
                "effective_input_budget": 100,
                "candidates": [
                    {"item_id": "invalid", "priority": "P2", "tokens": 1, "relevance": -0.1}
                ],
            }
        ),
    )
    assert negative["state"] == "BLOCKED"
    assert negative["code"] == "DOMAIN_INPUT_REJECTED"


def test_pressure_hysteresis_and_missing_usage_fail_closed() -> None:
    held = dispatch_skill(
        "elmos-context-pressure-monitor",
        request(
            {
                "used_tokens": 76,
                "effective_input_budget": 100,
                "previous_state": "HIGH",
            }
        ),
    )
    assert held["outputs"]["pressure_state"] == "HIGH"
    missing = dispatch_skill("elmos-context-pressure-monitor", request({}))
    assert missing["state"] == "BLOCKED"
    assert missing["outputs"]["action"] == "BLOCK_NEW_LOADS"

    injected_policy = dispatch_skill(
        "elmos-context-pressure-monitor",
        request(
            {
                "used_tokens": 99,
                "effective_input_budget": 100,
                "thresholds": {"elevated": 0.999, "high": 0.9991, "critical": 0.9992},
            }
        ),
    )
    assert injected_policy["state"] == "BLOCKED"
    assert injected_policy["code"] == "CONTEXT_PRESSURE_POLICY_UNTRUSTED"

    nan_usage = dispatch_skill(
        "elmos-context-pressure-monitor",
        request({"used_tokens": math.nan, "effective_input_budget": 100}),
    )
    assert nan_usage["state"] == "BLOCKED"
    assert nan_usage["code"] == "REQUEST_CONTRACT_REJECTED"


def test_structured_compaction_is_atomic_and_checkpoint_round_trips() -> None:
    incomplete = dispatch_skill(
        "elmos-structured-context-compaction",
        request({"state": {"goal": "g"}}),
    )
    assert incomplete["state"] == "BLOCKED"
    assert incomplete["outputs"]["original_unchanged"] is True

    state = {
        "goal": "finish",
        "latest_user_request": "do it all",
        "constraints": ["no silent truncation"],
        "acceptance_criteria": ["all handlers mapped"],
        "todos": ["verify"],
        "facts": [{"type": "constraint", "value": "fail closed", "critical": True, "anchor": {"id": "a"}}],
        "modified_files": ["a.py"],
        "test_state": ["NOT_RUN"],
    }
    compacted = dispatch_skill("elmos-structured-context-compaction", request({"state": state}))
    checkpoint_result = dispatch_skill(
        "elmos-context-checkpoint-and-recovery",
        request(
            {
                "action": "create",
                "task_id": "task-a",
                "package_version": "v1",
                "payload": compacted["outputs"]["checkpoint"],
            },
            request_id="checkpoint-create",
        ),
    )
    checkpoint = checkpoint_result["outputs"]["checkpoint"]
    assert checkpoint["tenant_id"] == "tenant-a"
    assert checkpoint["project_id"] == "project-a"
    assert checkpoint["request_id"] == "checkpoint-create"
    assert checkpoint["payload_digest"].startswith("sha256:")

    restore_request_id = "checkpoint-restore"
    restore_binding = {
        "authorized": True,
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "source_request_id": "checkpoint-create",
        "restore_request_id": restore_request_id,
        "payload_digest": checkpoint["payload_digest"],
        "checkpoint_digest": checkpoint["checkpoint_digest"],
    }
    restored = dispatch_skill(
        "elmos-context-checkpoint-and-recovery",
        request(
            {
                "action": "restore",
                "checkpoint": checkpoint,
                "current_package_version": "v1",
            },
            request_id=restore_request_id,
            capabilities={"checkpoint_restore_binding": restore_binding},
        ),
    )
    assert restored["state"] == "SUCCEEDED"
    assert restored["outputs"]["effects_to_skip"] == []
    assert restored["outputs"]["source_request_id"] == "checkpoint-create"

    self_receipted = dispatch_skill(
        "elmos-context-checkpoint-and-recovery",
        request(
            {
                "action": "create",
                "task_id": "task-a",
                "package_version": "v1",
                "payload": compacted["outputs"]["checkpoint"],
                "effect_receipts": ["effect-1"],
            }
        ),
    )
    assert self_receipted["state"] == "BLOCKED"
    assert self_receipted["code"] == "CHECKPOINT_AUTHORITY_INPUT_UNTRUSTED"

    cross_scope = dispatch_skill(
        "elmos-context-checkpoint-and-recovery",
        request(
            {"action": "restore", "checkpoint": checkpoint, "current_package_version": "v1"},
            tenant_id="tenant-b",
            request_id="checkpoint-cross-scope",
            capabilities={"checkpoint_restore_binding": restore_binding},
        ),
    )
    assert cross_scope["state"] == "BLOCKED"
    assert cross_scope["code"] == "CHECKPOINT_SCOPE_DENIED"


def test_rehydration_checks_scope_version_hash_and_budget() -> None:
    content = "exact source"
    source = {
        "source_id": "source-1",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "package_version": "v1",
        "content": content,
        "content_digest": sha_bytes(content.encode()),
        "tokens": 10,
        "anchor": {"line_start": 1, "line_end": 1},
    }
    sources = [source]
    catalog_binding = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "package_version": "v1",
        "sources": sources,
        "max_tokens": 20,
    }
    catalog = {
        "verified": True,
        **catalog_binding,
        "catalog_digest": sha_json(catalog_binding),
    }
    loaded = dispatch_skill(
        "elmos-context-rehydration",
        request(
            {"source_ids": ["source-1"], "package_version": "v1", "remaining_budget_tokens": 20},
            capabilities={"rehydration_catalog": catalog},
        ),
    )
    assert loaded["state"] == "SUCCEEDED"
    assert loaded["outputs"]["loaded"][0]["content"] == content
    assert loaded["outputs"]["loaded"][0]["content_digest"] == source["content_digest"]

    tampered = dict(source)
    tampered["content"] = "changed"
    tampered_binding = {**catalog_binding, "sources": [tampered]}
    blocked = dispatch_skill(
        "elmos-context-rehydration",
        request(
            {"source_ids": ["source-1"], "package_version": "v1", "remaining_budget_tokens": 20},
            capabilities={
                "rehydration_catalog": {
                    "verified": True,
                    **tampered_binding,
                    "catalog_digest": sha_json(tampered_binding),
                }
            },
        ),
    )
    assert blocked["state"] == "BLOCKED"
    assert blocked["code"] == "REHYDRATION_HASH_MISMATCH"

    self_authorized = dispatch_skill(
        "elmos-context-rehydration",
        request(
            {
                "sources": sources,
                "source_ids": ["source-1"],
                "package_version": "v1",
                "remaining_budget_tokens": 20,
            }
        ),
    )
    assert self_authorized["state"] == "BLOCKED"
    assert self_authorized["code"] == "REHYDRATION_CATALOG_INPUT_UNTRUSTED"

    cross_scope = dispatch_skill(
        "elmos-context-rehydration",
        request(
            {"source_ids": ["source-1"], "package_version": "v1", "remaining_budget_tokens": 20},
            tenant_id="tenant-b",
            capabilities={"rehydration_catalog": catalog},
        ),
    )
    assert cross_scope["state"] == "BLOCKED"
    assert cross_scope["code"] == "REHYDRATION_CATALOG_UNAVAILABLE"


def test_project_memory_uses_trusted_scope_and_reports_unperformed_persistence() -> None:
    items = [
        {
            "memory_id": "memory-1",
            "key": "constraint",
            "value": "fail closed",
            "version": 1,
            "status": "CURRENT",
            "source_digest": sha_bytes(b"source"),
            "source_anchor": {"path": "README.md", "line": 1},
        }
    ]
    snapshot_binding = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "actor_id": "actor-a",
        "branch": "main",
        "allowed_operations": ["delete", "query", "write"],
        "items": items,
        "max_results": 20,
    }
    snapshot = {
        "verified": True,
        **snapshot_binding,
        "snapshot_digest": sha_json(snapshot_binding),
    }
    projected = operate_project_memory(
        request(
            {"operation": "query", "query": "fail", "branch": "main", "limit": 10},
            capabilities={"project_memory_snapshot": snapshot},
        )
    )
    assert projected["state"] == "PARTIAL"
    assert projected["code"] == "PROJECT_MEMORY_QUERY_PROJECTED"
    assert projected["outputs"]["persistent_read_performed"] is False
    assert projected["outputs"]["external_execution"] == "NOT_RUN"
    assert projected["outputs"]["scope"]["actor_id"] == "actor-a"

    planned = operate_project_memory(
        request(
            {
                "operation": "write",
                "branch": "main",
                "candidate": {
                    "key": "constraint",
                    "value": "preserve provenance",
                    "source_anchor": {"path": "README.md", "line": 1},
                    "source_digest": sha_bytes(b"readme"),
                },
            },
            capabilities={"project_memory_snapshot": snapshot},
        )
    )
    assert planned["state"] == "PARTIAL"
    assert planned["code"] == "PROJECT_MEMORY_WRITE_PLANNED"
    assert planned["outputs"]["persisted"] is False

    self_authorized = operate_project_memory(request({"operation": "query", "items": items}))
    assert self_authorized["state"] == "BLOCKED"
    assert self_authorized["code"] == "MEMORY_AUTHORITY_INPUT_UNTRUSTED"

    cross_actor = operate_project_memory(
        request(
            {"operation": "query", "branch": "main"},
            actor_id="actor-b",
            capabilities={"project_memory_snapshot": snapshot},
        )
    )
    assert cross_actor["state"] == "BLOCKED"
    assert cross_actor["code"] == "PROJECT_MEMORY_SNAPSHOT_UNAVAILABLE"


def test_repository_context_map_rejects_ambiguous_graph_identity_and_confidence() -> None:
    mapped = dispatch_skill(
        "elmos-repository-context-map",
        request(
            {
                "modules": [{"node_id": "api"}],
                "symbols": [{"symbol_id": "db"}],
                "edges": [{"source": "api", "target": "db", "kind": "calls", "confidence": 1.0}],
                "changed_node_ids": ["db"],
            }
        ),
    )
    assert mapped["state"] == "SUCCEEDED"
    assert mapped["outputs"]["impact_candidates"] == ["api", "db"]

    for invalid_inputs, expected_code in (
        (
            {"modules": [{"node_id": "same"}, {"node_id": "same"}], "edges": []},
            "DOMAIN_INPUT_REJECTED",
        ),
        (
            {
                "modules": [{"node_id": "a"}, {"node_id": "b"}],
                "edges": [{"source": "a", "target": "b", "confidence": math.nan}],
            },
            "REQUEST_CONTRACT_REJECTED",
        ),
        (
            {
                "modules": [{"node_id": "a"}],
                "edges": [{"source": "a", "target": "missing", "confidence": 1.0}],
            },
            "DOMAIN_INPUT_REJECTED",
        ),
    ):
        blocked = dispatch_skill("elmos-repository-context-map", request(invalid_inputs))
        assert blocked["state"] == "BLOCKED"
        assert blocked["code"] == expected_code


def test_integrity_detects_negation_numeric_permission_and_version_drift() -> None:
    before = [
        {"fact_id": "f1", "type": "permission", "value": 10, "negated": True, "permission": "deny", "version": 2, "source_digest": sha_bytes(b"a")}
    ]
    after = [
        {"fact_id": "f1", "type": "permission", "value": 10, "negated": False, "permission": "allow", "version": 1, "source_digest": sha_bytes(b"a")}
    ]
    report = dispatch_skill(
        "elmos-context-integrity-and-loss-detection",
        request({"before": before, "after": after}),
    )
    assert report["state"] == "BLOCKED"
    assert report["outputs"]["retention_ratio"] == 0.0
    assert report["outputs"]["action"] == "BLOCK_AND_REHYDRATE_OR_ROLLBACK"

    empty = dispatch_skill(
        "elmos-context-integrity-and-loss-detection",
        request({"before": [], "after": []}),
    )
    assert empty["state"] == "BLOCKED"
    assert empty["code"] == "CONTEXT_INTEGRITY_BASELINE_EMPTY"

    non_finite = dispatch_skill(
        "elmos-context-integrity-and-loss-detection",
        request(
            {
                "before": [{"fact_id": "f1", "value": math.nan}],
                "after": [{"fact_id": "f1", "value": math.nan}],
            }
        ),
    )
    assert non_finite["state"] == "BLOCKED"
    assert non_finite["code"] == "REQUEST_CONTRACT_REJECTED"


def manifest_entries() -> list[dict[str, Any]]:
    return [
        {"path": "src/main.py", "kind": "file", "size": 7, "content_digest": sha_bytes(b"print()")},
        {"path": "README.md", "kind": "file", "size": 4, "content_digest": sha_bytes(b"read")},
    ]


def test_folder_and_manifest_paths_are_safe_and_digests_are_order_independent() -> None:
    unsafe = dispatch_skill(
        "elmos-folder-tree-input",
        request({"entries": [{"path": "../escape", "kind": "file", "size": 1, "content_digest": sha_bytes(b"x")}], "roots": []}),
    )
    assert unsafe["state"] == "BLOCKED"
    assert unsafe["code"] == "DOMAIN_INPUT_REJECTED"

    first = dispatch_skill(
        "elmos-project-package-manifest",
        request({"package_id": "pkg", "package_version": "v1", "entries": manifest_entries(), "roots": []}),
    )
    second = dispatch_skill(
        "elmos-project-package-manifest",
        request({"package_id": "pkg", "package_version": "v1", "entries": list(reversed(manifest_entries())), "roots": []}),
    )
    assert first["outputs"]["manifest_digest"] == second["outputs"]["manifest_digest"]
    assert first["outputs"]["merkle_root"] == second["outputs"]["merkle_root"]

    duplicate = dispatch_skill(
        "elmos-folder-tree-input",
        request(
            {
                "entries": [
                    {"entry_id": "same", "path": "src/a.py", "kind": "file", "size": 1, "content_digest": sha_bytes(b"a")},
                    {"entry_id": "same", "path": "src/b.py", "kind": "file", "size": 1, "content_digest": sha_bytes(b"b")},
                ],
                "roots": [{"name": "source", "path": "src", "role": "SOURCE"}],
            }
        ),
    )
    assert duplicate["state"] == "BLOCKED"
    assert duplicate["code"] == "FOLDER_PATH_COLLISION"
    assert duplicate["outputs"]["collisions"][0]["type"] == "DUPLICATE_ENTRY_ID"

    non_mapping = dispatch_skill(
        "elmos-folder-tree-input",
        request({"entries": ["src/main.py"], "roots": []}),
    )
    assert non_mapping["state"] == "BLOCKED"
    assert non_mapping["code"] == "DOMAIN_INPUT_REJECTED"

    invalid_size = dispatch_skill(
        "elmos-project-package-manifest",
        request(
            {
                "package_id": "pkg",
                "package_version": "v1",
                "entries": [
                    {"path": "src/main.py", "kind": "file", "size": -1, "content_digest": sha_bytes(b"")}
                ],
                "roots": [],
            }
        ),
    )
    assert invalid_size["state"] == "BLOCKED"
    assert invalid_size["code"] == "DOMAIN_INPUT_REJECTED"

    bad_root = dispatch_skill(
        "elmos-project-package-manifest",
        request(
            {
                "package_id": "pkg",
                "package_version": "v1",
                "entries": manifest_entries(),
                "roots": [{"name": "source", "path": "/src", "role": "SOURCE"}],
            }
        ),
    )
    assert bad_root["state"] == "BLOCKED"
    assert bad_root["code"] == "DOMAIN_INPUT_REJECTED"


def test_folder_resume_uses_scope_bound_server_state_and_exact_inventory() -> None:
    expected = [{"path": "src/main.py", "content_digest": sha_bytes(b"print()"), "size": 7}]
    expected_digest = sha_json(expected)
    state_binding = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "upload_session_id": "upload-1",
        "expected_manifest_digest": expected_digest,
        "received_files": expected,
    }
    server_state = {
        "verified": True,
        **state_binding,
        "state_digest": sha_json(state_binding),
    }
    completed = dispatch_skill(
        "elmos-resumable-multi-file-folder-upload",
        request(
            {"upload_session_id": "upload-1", "expected_files": expected},
            capabilities={"folder_upload_state": server_state},
        ),
    )
    assert completed["state"] == "SUCCEEDED"
    assert completed["code"] == "FOLDER_UPLOAD_VERIFIED"
    assert completed["outputs"]["external_state_verified"] is True

    self_reported = dispatch_skill(
        "elmos-resumable-multi-file-folder-upload",
        request(
            {
                "upload_session_id": "upload-1",
                "expected_files": expected,
                "received_files": expected,
            }
        ),
    )
    assert self_reported["state"] == "BLOCKED"
    assert self_reported["code"] == "UPLOAD_STATE_INPUT_UNTRUSTED"

    rebound = dispatch_skill(
        "elmos-resumable-multi-file-folder-upload",
        request(
            {
                "upload_session_id": "upload-1",
                "expected_files": [
                    {"path": "src/other.py", "content_digest": sha_bytes(b"other"), "size": 5}
                ],
            },
            capabilities={"folder_upload_state": server_state},
        ),
    )
    assert rebound["state"] == "BLOCKED"
    assert rebound["code"] == "UPLOAD_EXPECTED_MANIFEST_MISMATCH"

    duplicate_expected = dispatch_skill(
        "elmos-resumable-multi-file-folder-upload",
        request(
            {
                "upload_session_id": "upload-1",
                "expected_files": [expected[0], dict(expected[0])],
            },
            capabilities={"folder_upload_state": server_state},
        ),
    )
    assert duplicate_expected["state"] == "BLOCKED"
    assert duplicate_expected["code"] == "DOMAIN_INPUT_REJECTED"


def test_archive_traversal_rejects_and_safe_zip_waits_for_malware_clearance() -> None:
    unsafe = dispatch_skill(
        "elmos-archive-bomb-and-path-traversal-defense",
        request({"entries": [{"path": "../escape", "uncompressed_size": 1, "compressed_size": 1}]}),
    )
    assert unsafe["state"] == "BLOCKED"
    assert unsafe["outputs"]["decision"] == "REJECT"
    assert unsafe["outputs"]["decision_scope"] == "DECLARED_LAYER_ONLY"
    assert unsafe["outputs"]["global_budget_state"] == "NOT_EVALUATED"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("src/main.py", "print('safe')")
    extracted = extract_archive_safely(
        request({"format": "zip", "archive_bytes_b64": base64.b64encode(buffer.getvalue()).decode()})
    )
    assert extracted["state"] == "PARTIAL"
    assert extracted["code"] == "ARCHIVE_MALWARE_CLEARANCE_REQUIRED"
    assert extracted["outputs"]["objects"] == []
    assert extracted["outputs"]["parser_execution"] == "NOT_RUN"
    assert extracted["outputs"]["host_files_created"] is False
    assert extracted["outputs"]["publication_state"] == "NOT_RUN"
    assert extracted["outputs"]["readable_cas_objects"] == []

    injected_policy = dispatch_skill(
        "elmos-archive-bomb-and-path-traversal-defense",
        request(
            {
                "entries": [{"path": "large.bin", "uncompressed_size": 1_000_000_000, "compressed_size": 1}],
                "policy": {"max_total_uncompressed_bytes": 2_000_000_000},
            }
        ),
    )
    assert injected_policy["state"] == "BLOCKED"
    assert injected_policy["code"] == "DOMAIN_INPUT_REJECTED"

    negative_size = dispatch_skill(
        "elmos-archive-bomb-and-path-traversal-defense",
        request({"entries": [{"path": "bad.bin", "uncompressed_size": -1, "compressed_size": 1}]}),
    )
    assert negative_size["state"] == "BLOCKED"
    assert negative_size["outputs"]["decision"] == "REJECT"

    input_limit_override = extract_archive_safely(
        request(
            {
                "format": "zip",
                "archive_bytes_b64": base64.b64encode(buffer.getvalue()).decode(),
                "max_archive_bytes": 1_000_000_000,
            }
        )
    )
    assert input_limit_override["state"] == "BLOCKED"
    assert input_limit_override["code"] == "DOMAIN_INPUT_REJECTED"

    many = io.BytesIO()
    with zipfile.ZipFile(many, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("one.txt", "1")
        archive.writestr("two.txt", "2")
    bounded_count = extract_archive_safely(
        request(
            {"format": "zip", "archive_bytes_b64": base64.b64encode(many.getvalue()).decode()},
            policy={"archive": {"max_entries": 1, "version": "tight-1"}},
        )
    )
    assert bounded_count["state"] == "PARTIAL"
    assert bounded_count["code"] == "ARCHIVE_MALWARE_CLEARANCE_REQUIRED"
    assert bounded_count["outputs"]["parser_execution"] == "NOT_RUN"

    compressed_bomb = io.BytesIO()
    with zipfile.ZipFile(compressed_bomb, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("repeated.txt", "A" * 200_000)
    ratio_blocked = extract_archive_safely(
        request(
            {
                "format": "zip",
                "archive_bytes_b64": base64.b64encode(compressed_bomb.getvalue()).decode(),
            }
        )
    )
    assert ratio_blocked["state"] == "PARTIAL"
    assert ratio_blocked["code"] == "ARCHIVE_MALWARE_CLEARANCE_REQUIRED"
    assert ratio_blocked["outputs"]["parser_execution"] == "NOT_RUN"

    gzip_stream_limit = extract_archive_safely(
        request(
            {
                "format": "gzip",
                "output_name": "payload.txt",
                "archive_bytes_b64": base64.b64encode(gzip.compress(b"0123456789abcdef")).decode(),
            },
            policy={"archive": {"max_entry_uncompressed_bytes": 8, "version": "tight-stream-1"}},
        )
    )
    assert gzip_stream_limit["state"] == "PARTIAL"
    assert gzip_stream_limit["code"] == "ARCHIVE_MALWARE_CLEARANCE_REQUIRED"
    assert gzip_stream_limit["outputs"]["parser_execution"] == "NOT_RUN"


def test_profile_classification_symbol_index_and_incremental_diff_are_explicit() -> None:
    entries = [
        {"path": "pyproject.toml"},
        {"path": "src/app.py"},
        {"path": "node_modules/pkg/index.js"},
        {"path": ".env"},
    ]
    profile = dispatch_skill(
        "elmos-project-root-language-framework-detection",
        request({"entries": entries}),
    )
    assert profile["outputs"]["languages"]["Python"] == 1
    assert profile["outputs"]["roots"][0]["evidence"] == ["pyproject.toml"]

    generic_package_marker = dispatch_skill(
        "elmos-project-root-language-framework-detection",
        request({"entries": [{"path": "package.json"}]}),
    )
    assert generic_package_marker["state"] == "PARTIAL"
    assert generic_package_marker["outputs"]["frameworks"] == []

    package_content = json.dumps({"dependencies": {"react": "19.0.0"}}, sort_keys=True)
    verified_react = dispatch_skill(
        "elmos-project-root-language-framework-detection",
        request(
            {
                "entries": [
                    {
                        "path": "package.json",
                        "content": package_content,
                        "content_digest": sha_bytes(package_content.encode()),
                    }
                ]
            }
        ),
    )
    assert [item["framework"] for item in verified_react["outputs"]["frameworks"]] == ["React"]

    security_states = {"src/app.py": "CLEAR", ".env": "QUARANTINED"}
    classified = dispatch_skill(
        "elmos-ignore-generated-vendored-file-classification",
        request(
            {
                "entries": [
                    {"path": "src/app.py"},
                    {"path": ".env"},
                ],
            },
            policy={
                "project_classification": {
                    "version": "classification-1",
                    "ignore_rules": [{"pattern": "!.env", "source": ".gitignore", "line": 1}],
                }
            },
            capabilities={
                "project_security_assessment": {
                    "verified": True,
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "states": security_states,
                    "assessment_digest": sha_json(security_states),
                }
            },
        ),
    )
    assert classified["state"] == "SUCCEEDED"
    env = next(item for item in classified["outputs"]["entries"] if item["path"] == ".env")
    assert env["classification"] == "QUARANTINED"
    assert env["reason"] == "SECURITY_POLICY_PRECEDENCE"

    source = "import os\nclass App:\n    def run(self):\n        return 1\n"
    indexed = dispatch_skill(
        "elmos-repository-map-and-symbol-indexing",
        request(
            {
                "files": [
                    {
                        "path": "src/app.py",
                        "content": source,
                        "content_digest": sha_bytes(source.encode()),
                        "source_version": "commit:abc123",
                        "anchor": {"repository_id": "repo-1", "commit": "abc123"},
                    }
                ]
            }
        ),
    )
    assert indexed["state"] == "SUCCEEDED"
    assert {item["name"] for item in indexed["outputs"]["symbols"]} == {"App", "run"}
    assert {item["source_version"] for item in indexed["outputs"]["symbols"]} == {"commit:abc123"}
    assert indexed["outputs"]["symbols"][0]["anchor"]["repository_id"] == "repo-1"
    assert indexed["outputs"]["source_inventory"][0]["content_digest"] == sha_bytes(source.encode())
    assert indexed["outputs"]["user_code_executed"] is False

    diff = dispatch_skill(
        "elmos-project-package-version-and-incremental-update",
        request(
            {
                "previous_entries": [{"path": "old.py", "content_digest": sha_bytes(b"same")}],
                "current_entries": [{"path": "new.py", "content_digest": sha_bytes(b"same")}],
            }
        ),
    )
    assert diff["outputs"]["rename_candidates"] == [
        {"from": "old.py", "to": "new.py", "confidence": 1.0, "basis": "IDENTICAL_CONTENT_DIGEST"}
    ]
    assert diff["outputs"]["reparse_paths"] == []


def test_classification_symbol_index_and_diff_fail_closed_on_untrusted_or_ambiguous_input() -> None:
    self_classified = dispatch_skill(
        "elmos-ignore-generated-vendored-file-classification",
        request({"entries": [{"path": "src/app.py", "security_state": "CLEAR"}]}),
    )
    assert self_classified["state"] == "BLOCKED"
    assert self_classified["code"] == "CLASSIFICATION_SECURITY_INPUT_UNTRUSTED"

    self_policy = dispatch_skill(
        "elmos-ignore-generated-vendored-file-classification",
        request(
            {
                "entries": [{"path": "src/app.py"}],
                "ignore_rules": [{"pattern": "src/**"}],
            }
        ),
    )
    assert self_policy["state"] == "BLOCKED"
    assert self_policy["code"] == "CLASSIFICATION_POLICY_INPUT_UNTRUSTED"

    portable_collision = dispatch_skill(
        "elmos-ignore-generated-vendored-file-classification",
        request({"entries": [{"path": "Src/App.py"}, {"path": "src/app.py"}]}),
    )
    assert portable_collision["state"] == "BLOCKED"
    assert portable_collision["code"] == "DOMAIN_INPUT_REJECTED"

    missing_provenance = dispatch_skill(
        "elmos-repository-map-and-symbol-indexing",
        request({"files": [{"path": "src/app.py", "content": "pass\n"}]}),
    )
    assert missing_provenance["state"] == "BLOCKED"
    assert missing_provenance["code"] == "DOMAIN_INPUT_REJECTED"

    duplicate_source = "class A:\n    pass\n"
    duplicate_sources = dispatch_skill(
        "elmos-repository-map-and-symbol-indexing",
        request(
            {
                "files": [
                    {
                        "path": "src/App.py",
                        "content": duplicate_source,
                        "content_digest": sha_bytes(duplicate_source.encode()),
                        "source_version": "v1",
                        "anchor": {"commit": "a"},
                    },
                    {
                        "path": "src/app.py",
                        "content": duplicate_source,
                        "content_digest": sha_bytes(duplicate_source.encode()),
                        "source_version": "v1",
                        "anchor": {"commit": "a"},
                    },
                ]
            }
        ),
    )
    assert duplicate_sources["state"] == "BLOCKED"
    assert duplicate_sources["code"] == "DOMAIN_INPUT_REJECTED"

    oversized_source = "x" * (2 * 1024 * 1024 + 1)
    over_limit = dispatch_skill(
        "elmos-repository-map-and-symbol-indexing",
        request(
            {
                "files": [
                    {
                        "path": "src/large.py",
                        "content": oversized_source,
                        "content_digest": sha_bytes(oversized_source.encode()),
                        "source_version": "v1",
                        "anchor": {"commit": "a"},
                    }
                ]
            }
        ),
    )
    assert over_limit["state"] == "BLOCKED"
    assert over_limit["code"] == "DOMAIN_INPUT_REJECTED"

    digest = sha_bytes(b"same")
    ambiguous_rename = dispatch_skill(
        "elmos-project-package-version-and-incremental-update",
        request(
            {
                "previous_entries": [
                    {"path": "old-a.py", "content_digest": digest},
                    {"path": "old-b.py", "content_digest": digest},
                ],
                "current_entries": [{"path": "new.py", "content_digest": digest}],
            }
        ),
    )
    assert ambiguous_rename["state"] == "PARTIAL"
    assert ambiguous_rename["code"] == "PACKAGE_RENAME_REVIEW_REQUIRED"
    assert ambiguous_rename["outputs"]["rename_candidates"] == []

    missing_digest = dispatch_skill(
        "elmos-project-package-version-and-incremental-update",
        request(
            {
                "previous_entries": [{"path": "old.py"}],
                "current_entries": [],
            }
        ),
    )
    assert missing_digest["state"] == "BLOCKED"
    assert missing_digest["code"] == "DOMAIN_INPUT_REJECTED"

    contradictory_size = dispatch_skill(
        "elmos-project-package-version-and-incremental-update",
        request(
            {
                "previous_entries": [{"path": "old.py", "content_digest": digest, "size": 4}],
                "current_entries": [{"path": "new.py", "content_digest": digest, "size": 5}],
            }
        ),
    )
    assert contradictory_size["state"] == "BLOCKED"
    assert contradictory_size["code"] == "DOMAIN_INPUT_REJECTED"


def test_package_review_is_paginated_and_untrusted_state_cannot_raise_readiness() -> None:
    result = dispatch_skill(
        "elmos-project-package-preview-and-review-ui",
        request(
            {
                "entries": [
                    {"path": "safe.txt", "state": "READY"},
                    {"path": "danger.bin", "state": "QUARANTINED"},
                ],
                "overrides": {"danger.bin": "READY"},
                "offset": 0,
                "limit": 1,
            }
        ),
    )
    assert result["state"] == "BLOCKED"
    assert result["outputs"]["virtualized"] is True
    assert result["outputs"]["total"] == 2
    assert result["outputs"]["rejected_overrides"][0]["code"] == "OVERRIDE_AUTHORIZATION_REQUIRED"
    assert result["outputs"]["readiness"] == "NOT_READY"
    assert result["outputs"]["entries"][0]["state"] == "PENDING"

    empty = dispatch_skill(
        "elmos-project-package-preview-and-review-ui",
        request({"entries": []}),
    )
    assert empty["state"] == "BLOCKED"
    assert empty["code"] == "PACKAGE_REVIEW_EMPTY"
    assert empty["outputs"]["readiness"] == "NOT_READY"

    untrusted_override = dispatch_skill(
        "elmos-project-package-preview-and-review-ui",
        request(
            {
                "entries": [{"path": "pending.txt", "state": "PENDING"}],
                "overrides": {"pending.txt": "READY"},
            }
        ),
    )
    assert untrusted_override["state"] == "BLOCKED"
    assert untrusted_override["outputs"]["rejected_overrides"][0]["code"] == "OVERRIDE_AUTHORIZATION_REQUIRED"
    assert untrusted_override["outputs"]["readiness"] == "NOT_READY"

    trusted_override = dispatch_skill(
        "elmos-project-package-preview-and-review-ui",
        request(
            {
                "entries": [{"path": "pending.txt", "state": "PENDING"}],
                "overrides": {"pending.txt": "READY"},
            },
            capabilities={
                "review_override_authorization": {
                    "verified": True,
                    "consent_granted": True,
                    "receipt_id": "review-receipt-1",
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "actor_id": "actor-a",
                    "allowed_overrides": {
                        "pending.txt": {"from": "PENDING", "to": "READY"}
                    },
                }
            },
        ),
    )
    assert trusted_override["state"] == "BLOCKED"
    assert trusted_override["outputs"]["readiness"] == "NOT_READY"
    assert trusted_override["outputs"]["rejected_overrides"][0]["code"] == "OVERRIDE_AUTHORIZATION_REQUIRED"

    input_consent = dispatch_skill(
        "elmos-project-package-preview-and-review-ui",
        request(
            {
                "entries": [{"path": "pending.txt", "state": "PENDING"}],
                "overrides": {"pending.txt": "READY"},
                "consent": True,
            }
        ),
    )
    assert input_consent["state"] == "BLOCKED"
    assert input_consent["code"] == "DOMAIN_INPUT_REJECTED"

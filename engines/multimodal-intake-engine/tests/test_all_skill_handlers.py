from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from elmos_multimodal_intake.skill_runtime import (
    SKILL_REGISTRY,
    SkillDispatcher,
    SkillRuntimeError,
)


TENANT_ID = "tenant-a"
PROJECT_ID = "project-a"
ACTOR_ID = "actor-a"

RESULT_ENVELOPE_KEYS = frozenset(
    {
        "schema_version",
        "skill",
        "handler_id",
        "request_id",
        "trace_id",
        "phase",
        "state",
        "code",
        "retryable",
        "outputs",
        "metrics",
        "implementation_state",
        "external_evidence",
        "certification",
    }
)


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _anchor(*, anchor_id: str = "anchor-1") -> dict[str, Any]:
    return {
        "anchor_id": anchor_id,
        "asset_id": "asset-1",
        "asset_digest": _sha256("source-asset"),
        "asset_version": 1,
        "locator": {"kind": "text_range", "start_line": 1, "end_line": 1},
    }


@dataclass(frozen=True)
class HandlerCase:
    ordinal: int
    skill: str
    handler_id: str
    phase: str
    expected_state: str
    expected_code: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    policy: Mapping[str, Any] = field(default_factory=dict)
    capabilities: Mapping[str, Any] = field(default_factory=dict)
    implementation_state: str = "CODE_IMPLEMENTED_LOCAL"
    idempotency_key: str | None = None


CASES = (
    HandlerCase(
        1,
        "elmos-multimodal-input-orchestrator",
        "execute_multimodal_input_orchestrator",
        "secure-intake",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        2,
        "elmos-secure-resumable-upload",
        "execute_secure_resumable_upload",
        "secure-intake",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        3,
        "elmos-file-type-detection-and-validation",
        "execute_file_type_detection_and_validation",
        "secure-intake",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        4,
        "elmos-malware-quarantine-and-sandbox",
        "execute_malware_quarantine_and_sandbox",
        "secure-intake",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        5,
        "elmos-audio-asr-and-diarization",
        "execute_audio_asr_and_diarization",
        "secure-intake",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        6,
        "elmos-image-ocr-and-preprocessing",
        "execute_image_ocr_and_preprocessing",
        "secure-intake",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        7,
        "elmos-visual-ui-understanding",
        "execute_visual_ui_understanding",
        "content",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        8,
        "elmos-diagram-and-architecture-understanding",
        "execute_diagram_and_architecture_understanding",
        "content",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        9,
        "elmos-pdf-layout-table-parser",
        "execute_pdf_layout_table_parser",
        "secure-intake",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        10,
        "elmos-word-document-parser",
        "execute_word_document_parser",
        "secure-intake",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        11,
        "elmos-markdown-text-log-parser",
        "execute_markdown_text_log_parser",
        "secure-intake",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        12,
        "elmos-unified-multimodal-content-ir",
        "execute_unified_multimodal_content_ir",
        "normalization",
        "PARTIAL",
        "CONTENT_IR_AUTHORITY_REQUIRED",
        {
            "document_id": "document-12",
            "blocks": [
                {
                    "id": "block-1",
                    "type": "paragraph",
                    "text": "Anchored content.",
                    "anchors": [_anchor()],
                }
            ],
        },
    ),
    HandlerCase(
        13,
        "elmos-source-anchor-and-provenance",
        "execute_source_anchor_and_provenance",
        "normalization",
        "PARTIAL",
        "PROVENANCE_AUTHORITY_REQUIRED",
        {
            "anchors": [_anchor()],
            "critical_item_ids": ["critical-1"],
            "derivations": [
                {
                    "derivation_id": "derivation-1",
                    "source_anchor_ids": ["anchor-1"],
                    "processor": "local-parser",
                    "processor_version": "1.0",
                    "output_digest": _sha256("derived-output"),
                    "critical_item_ids": ["critical-1"],
                }
            ],
        },
    ),
    HandlerCase(
        14,
        "elmos-multimodal-requirement-extraction",
        "execute_multimodal_requirement_extraction",
        "content",
        "SUCCEEDED",
        "REQUIREMENTS_EXTRACTED",
        {
            "sources": [
                {
                    "source_id": "source-14",
                    "anchor": _anchor(),
                    "text": (
                        "MUST preserve exact source anchors.\n"
                        "ACCEPTANCE: Every extracted requirement retains its anchor."
                    ),
                }
            ]
        },
    ),
    HandlerCase(
        15,
        "elmos-multi-asset-content-fusion",
        "execute_multi_asset_content_fusion",
        "content",
        "SUCCEEDED",
        "ASSETS_FUSED",
        {
            "assets": [
                {
                    "asset_id": "asset-15",
                    "content": "same-content",
                    "content_digest": _sha256("same-content"),
                    "role": "SOURCE",
                }
            ]
        },
    ),
    HandlerCase(
        16,
        "elmos-document-version-and-conflict-detection",
        "execute_document_version_and_conflict_detection",
        "content",
        "PARTIAL",
        "UNRESOLVED_CONFLICTS",
        {
            "claims": [
                {
                    "claim_id": "claim-1",
                    "subject": "retention-days",
                    "value": "30",
                    "version": 1,
                    "anchor": _anchor(anchor_id="anchor-16-a"),
                },
                {
                    "claim_id": "claim-2",
                    "subject": "retention-days",
                    "value": "90",
                    "version": 2,
                    "anchor": _anchor(anchor_id="anchor-16-b"),
                },
            ]
        },
    ),
    HandlerCase(
        17,
        "elmos-human-review-and-correction",
        "execute_human_review_and_correction",
        "review",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        {
            "content_id": "asset-17",
            "expected_version": 1,
            "value": "reviewed",
            "reason": "human review",
        },
        implementation_state="BRIDGE_REQUIRED",
        idempotency_key="idempotency-17",
    ),
    HandlerCase(
        18,
        "elmos-prompt-injection-defense",
        "execute_prompt_injection_defense",
        "governance",
        "BLOCKED",
        "TRUSTED_TOOL_POLICY_UNAVAILABLE",
        {"text": "Untrusted document text is data only."},
    ),
    HandlerCase(
        19,
        "elmos-provider-routing-and-fallback",
        "execute_provider_routing_and_fallback",
        "governance",
        "BLOCKED",
        "PROVIDER_ROUTING_POLICY_UNAVAILABLE",
    ),
    HandlerCase(
        20,
        "elmos-storage-index-and-retrieval",
        "execute_storage_index_and_retrieval",
        "indexing",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        {"query": "anchor", "package_version": "v1"},
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        21,
        "elmos-durable-processing-and-recovery",
        "execute_durable_processing_and_recovery",
        "governance",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        {"task_id": "task-21", "target_state": "RUNNING"},
        implementation_state="BRIDGE_REQUIRED",
        idempotency_key="idempotency-21",
    ),
    HandlerCase(
        22,
        "elmos-processing-cost-and-eta-estimation",
        "execute_processing_cost_and_eta_estimation",
        "evaluation",
        "BLOCKED",
        "TRUSTED_ESTIMATION_POLICY_REQUIRED",
        {"stages": []},
    ),
    HandlerCase(
        23,
        "elmos-multimodal-observability",
        "execute_multimodal_observability",
        "evaluation",
        "BLOCKED",
        "TRUSTED_OBSERVABILITY_POLICY_REQUIRED",
        {"events": []},
    ),
    HandlerCase(
        24,
        "elmos-multimodal-evaluation-framework",
        "execute_multimodal_evaluation_framework",
        "evaluation",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        {"operation": "evaluate"},
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        25,
        "elmos-multimodal-input-workbench-ui",
        "execute_multimodal_input_workbench_ui",
        "review",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        26,
        "elmos-ingestion-api-and-sdk",
        "execute_ingestion_api_and_sdk",
        "delivery",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        27,
        "elmos-data-retention-and-governance",
        "execute_data_retention_and_governance",
        "governance",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        {"action": "evaluate"},
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        28,
        "elmos-downstream-agent-integration",
        "execute_downstream_agent_integration",
        "delivery",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        29,
        "elmos-codex-context-capacity-parity",
        "execute_codex_context_capacity_parity",
        "context",
        "BLOCKED",
        "CAPABILITY_UNKNOWN",
    ),
    HandlerCase(
        30,
        "elmos-context-budget-manager",
        "execute_context_budget_manager",
        "context",
        "BLOCKED",
        "CAPABILITY_UNKNOWN",
        {"usage": {}},
    ),
    HandlerCase(
        31,
        "elmos-multimodal-token-accounting",
        "execute_multimodal_token_accounting",
        "context",
        "SUCCEEDED",
        "MULTIMODAL_TOKENS_ACCOUNTED",
        {"items": [{"item_id": "item-31", "modality": "text", "text": "safe text"}]},
    ),
    HandlerCase(
        32,
        "elmos-long-context-packing-and-ranking",
        "execute_long_context_packing_and_ranking",
        "context",
        "BLOCKED",
        "CONTEXT_BUDGET_MISSING",
        {"candidates": []},
    ),
    HandlerCase(
        33,
        "elmos-context-pressure-monitor",
        "execute_context_pressure_monitor",
        "context",
        "SUCCEEDED",
        "CONTEXT_PRESSURE_NORMAL",
        {"used_tokens": 10, "effective_input_budget": 100},
    ),
    HandlerCase(
        34,
        "elmos-structured-context-compaction",
        "execute_structured_context_compaction",
        "context",
        "SUCCEEDED",
        "STRUCTURED_CONTEXT_COMPACTED",
        {
            "state": {
                "goal": "Exercise the local compactor.",
                "latest_user_request": "Keep the exact request.",
                "constraints": ["No external calls."],
                "acceptance_criteria": ["All critical fields remain."],
                "todos": ["Continue locally."],
                "facts": [],
                "modified_files": [],
                "test_state": [],
            }
        },
    ),
    HandlerCase(
        35,
        "elmos-context-checkpoint-and-recovery",
        "execute_context_checkpoint_and_recovery",
        "context",
        "SUCCEEDED",
        "CONTEXT_CHECKPOINT_CREATED",
        {
            "action": "create",
            "task_id": "task-35",
            "package_version": "1.0.0",
            "payload": {"step": "safe-local-checkpoint"},
        },
    ),
    HandlerCase(
        36,
        "elmos-context-rehydration",
        "execute_context_rehydration",
        "context",
        "BLOCKED",
        "REHYDRATION_CATALOG_INPUT_UNTRUSTED",
        {
            "sources": [],
            "source_ids": ["missing-source"],
            "remaining_budget_tokens": 10,
            "package_version": "v1",
        },
    ),
    HandlerCase(
        37,
        "elmos-project-memory-and-retrieval",
        "execute_project_memory_and_retrieval",
        "context",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        {"operation": "query", "query": "anchor", "items": []},
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        38,
        "elmos-repository-context-map",
        "execute_repository_context_map",
        "indexing",
        "BLOCKED",
        "REPOSITORY_MAP_NODES_EMPTY",
        {"modules": [], "symbols": [], "edges": [], "changed_node_ids": []},
    ),
    HandlerCase(
        39,
        "elmos-model-capability-discovery",
        "execute_model_capability_discovery",
        "context",
        "BLOCKED",
        "MODEL_CAPABILITY_UNTRUSTED",
        {"observation": {}},
    ),
    HandlerCase(
        40,
        "elmos-context-integrity-and-loss-detection",
        "execute_context_integrity_and_loss_detection",
        "context",
        "SUCCEEDED",
        "CONTEXT_INTEGRITY_PASSED",
        {
            "before": [
                {
                    "fact_id": "fact-40",
                    "type": "constraint",
                    "value": "No external calls.",
                    "negated": False,
                    "version": 1,
                    "source_digest": _sha256("fact-40"),
                }
            ],
            "after": [
                {
                    "fact_id": "fact-40",
                    "type": "constraint",
                    "value": "No external calls.",
                    "negated": False,
                    "version": 1,
                    "source_digest": _sha256("fact-40"),
                }
            ],
        },
    ),
    HandlerCase(
        41,
        "elmos-folder-tree-input",
        "execute_folder_tree_input",
        "project-package",
        "SUCCEEDED",
        "FOLDER_MANIFEST_CREATED",
        {
            "entries": [
                {
                    "path": "src/main.py",
                    "kind": "file",
                    "size": 3,
                    "content_digest": _sha256("src"),
                }
            ],
            "roots": [],
        },
    ),
    HandlerCase(
        42,
        "elmos-resumable-multi-file-folder-upload",
        "execute_resumable_multi_file_folder_upload",
        "project-package",
        "BLOCKED",
        "UPLOAD_STATE_INPUT_UNTRUSTED",
        {
            "expected_files": [
                {"path": "src/main.py", "size": 3, "content_digest": _sha256("src")}
            ],
            "received_files": [
                {"path": "src/main.py", "size": 3, "content_digest": _sha256("src")}
            ],
        },
    ),
    HandlerCase(
        43,
        "elmos-project-package-manifest",
        "execute_project_package_manifest",
        "project-package",
        "SUCCEEDED",
        "PROJECT_MANIFEST_CREATED",
        {
            "package_id": "package-43",
            "package_version": "1.0.0",
            "entries": [
                {
                    "path": "src/main.py",
                    "kind": "file",
                    "size": 3,
                    "content_digest": _sha256("src"),
                }
            ],
            "roots": [],
        },
    ),
    HandlerCase(
        44,
        "elmos-secure-zip-tar-extraction",
        "execute_secure_zip_tar_extraction",
        "project-package",
        "BLOCKED",
        "BRIDGE_UNAVAILABLE",
        implementation_state="BRIDGE_REQUIRED",
    ),
    HandlerCase(
        45,
        "elmos-archive-bomb-and-path-traversal-defense",
        "execute_archive_bomb_and_path_traversal_defense",
        "secure-intake",
        "BLOCKED",
        "ARCHIVE_REJECT",
        {"entries": []},
    ),
    HandlerCase(
        46,
        "elmos-project-root-language-framework-detection",
        "execute_project_root_language_framework_detection",
        "project-package",
        "SUCCEEDED",
        "PROJECT_PROFILE_DETECTED",
        {"entries": [{"path": "pyproject.toml"}]},
    ),
    HandlerCase(
        47,
        "elmos-ignore-generated-vendored-file-classification",
        "execute_ignore_generated_vendored_file_classification",
        "project-package",
        "BLOCKED",
        "CLASSIFICATION_POLICY_INPUT_UNTRUSTED",
        {"entries": [{"path": "src/main.py", "security_state": "CLEAR"}], "ignore_rules": []},
    ),
    HandlerCase(
        48,
        "elmos-repository-map-and-symbol-indexing",
        "execute_repository_map_and_symbol_indexing",
        "indexing",
        "BLOCKED",
        "DOMAIN_INPUT_REJECTED",
        {"files": [{"path": "src/main.py", "content": "def main():\n    return 0\n"}]},
    ),
    HandlerCase(
        49,
        "elmos-project-package-version-and-incremental-update",
        "execute_project_package_version_and_incremental_update",
        "project-package",
        "SUCCEEDED",
        "PACKAGE_INCREMENTAL_UPDATE_PLANNED",
        {
            "previous_entries": [
                {"path": "src/main.py", "content_digest": _sha256("src")}
            ],
            "current_entries": [
                {"path": "src/main.py", "content_digest": _sha256("src")}
            ],
        },
    ),
    HandlerCase(
        50,
        "elmos-project-package-preview-and-review-ui",
        "execute_project_package_preview_and_review_ui",
        "review",
        "PARTIAL",
        "PACKAGE_REVIEW_TRUSTED_SNAPSHOT_REQUIRED",
        {
            "entries": [
                {
                    "path": "src/main.py",
                    "state": "READY",
                    "security_findings": [],
                }
            ]
        },
    ),
)


def _request(case: HandlerCase) -> dict[str, Any]:
    request: dict[str, Any] = {
        "schema_version": "1.0",
        "request_id": f"request-{case.ordinal:02d}",
        "trace_id": f"trace-{case.ordinal:02d}",
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_ID,
        "actor_id": ACTOR_ID,
        "inputs": copy.deepcopy(dict(case.inputs)),
        "policy": copy.deepcopy(dict(case.policy)),
        "capabilities": copy.deepcopy(dict(case.capabilities)),
    }
    if case.idempotency_key is not None:
        request["idempotency_key"] = case.idempotency_key
    return request


def test_case_table_is_an_exact_copy_of_the_50_handler_bindings() -> None:
    ordered_bindings = sorted(SKILL_REGISTRY.values(), key=lambda binding: binding.ordinal)
    expected_bindings = [
        (case.ordinal, case.skill, case.handler_id, case.phase) for case in CASES
    ]
    actual_bindings = [
        (binding.ordinal, binding.skill, binding.handler_id, binding.phase)
        for binding in ordered_bindings
    ]

    assert len(CASES) == 50
    assert expected_bindings == actual_bindings
    assert all(
        SKILL_REGISTRY[case.skill].handler.__name__ == case.handler_id for case in CASES
    )


@pytest.mark.parametrize(
    "case",
    CASES,
    ids=lambda case: f"{case.ordinal:02d}-{case.skill.removeprefix('elmos-')}",
)
def test_each_canonical_skill_dispatches_its_real_handler_with_a_fixed_envelope(
    case: HandlerCase,
) -> None:
    # An instance-scoped dispatcher with no registered bridges prevents ambient
    # global bridge state from invoking an external adapter in this test.
    result = SkillDispatcher().dispatch(case.skill, _request(case))

    assert set(result) == RESULT_ENVELOPE_KEYS
    assert result["schema_version"] == "1.0"
    assert result["skill"] == case.skill
    assert result["handler_id"] == case.handler_id
    assert result["request_id"] == f"request-{case.ordinal:02d}"
    assert result["trace_id"] == f"trace-{case.ordinal:02d}"
    assert result["phase"] == case.phase
    assert result["state"] == case.expected_state
    assert result["code"] == case.expected_code
    assert isinstance(result["retryable"], bool)
    assert isinstance(result["outputs"], dict)
    assert isinstance(result["metrics"], dict)
    assert result["implementation_state"] == case.implementation_state
    assert result["external_evidence"] == "NOT_RUN"
    assert result["certification"] == "NOT_CERTIFIED"


def test_unknown_skill_fails_closed_before_any_handler_or_bridge_can_run() -> None:
    with pytest.raises(SkillRuntimeError, match="unknown multimodal intake Skill"):
        SkillDispatcher().dispatch(
            "elmos-unknown-multimodal-skill",
            {
                "schema_version": "1.0",
                "request_id": "request-unknown",
                "trace_id": "trace-unknown",
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "actor_id": ACTOR_ID,
                "inputs": {},
            },
        )

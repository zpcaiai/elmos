#!/usr/bin/env python3
"""Fail-closed importer for the pinned multimodal-intake Skill package.

The archive is treated as untrusted data.  This module never imports or runs
anything from it.  Validation and handler discovery are performed with the
Python standard library and static AST inspection only.
"""

from __future__ import annotations

import argparse
import ast
import errno
import fcntl
import hashlib
import hmac
import io
import json
import math
import os
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
import zipfile
import zlib
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping, Sequence

try:
    from tooling.skill_creator_tools import format_display_name, yaml_quote
except ModuleNotFoundError:  # Direct execution places tooling/ on sys.path.
    from skill_creator_tools import format_display_name, yaml_quote


PACKAGE_NAME = "elmos-multimodal-intake-skills"
PACKAGE_VERSION = "1.0.0"
ARCHIVE_ROOT = f"{PACKAGE_NAME}-v{PACKAGE_VERSION}"
ARCHIVE_RELATIVE_PATH = Path("skills/subskills") / f"{ARCHIVE_ROOT}.zip"
ARCHIVE_SHA256 = "23f9f2cee63e2fb1a43f85df539942e92077db2c58ddd75a8a0854773eb1c90b"
EXPECTED_ARCHIVE_BYTES = 664_179
EXPECTED_ENTRY_COUNT = 346
EXPECTED_UNCOMPRESSED_BYTES = 1_117_974
EXPECTED_INTERNAL_CHECKSUMS = 345
EXPECTED_SKILL_COUNT = 50
EXPECTED_ACCEPTANCE_COUNT = 240
EXPECTED_DELIVERABLE_COUNT = 170
EXPECTED_GLOBAL_GATE_COUNT = 8
EXPECTED_DEPENDENCY_EDGES = 95
EXPECTED_ROOT_SKILLS = 8
EXPECTED_SCHEMA_COUNT = 9
EXPECTED_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
EXPECTED_SCHEMA_NAMES = (
    "archive-inspection.schema.json",
    "content-block.schema.json",
    "context-budget.schema.json",
    "input-package.schema.json",
    "processing-event.schema.json",
    "project-package-manifest.schema.json",
    "requirement-conflict.schema.json",
    "source-anchor.schema.json",
    "task-checkpoint.schema.json",
)
EXPECTED_OPERATION_REGISTRY_SCHEMA = "multimodal-operation-registry-v1"
EXPECTED_OPERATION_COUNT = 147
EXPECTED_OPERATION_REGISTRY_DIGEST = (
    "4eeeeb5d921048a8c3dad6964956cf6fa171f4b13c3ffa711584ce4c08443eaa"
)
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 512
MAX_ARCHIVE_ENTRY_BYTES = 64 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 100
MAX_ARCHIVE_PATH_BYTES = 1024
MAX_ARCHIVE_COMPONENT_BYTES = 255
MAX_MANAGED_JSON_BYTES = 8 * 1024 * 1024
MAX_RUNTIME_FILE_BYTES = 16 * 1024 * 1024
MAX_TRANSACTION_JOURNAL_BYTES = 1024 * 1024
TRANSACTION_PREFIX = ".multimodal-intake-transaction-"
TRANSACTION_JOURNAL_NAME = "journal-v1.json"
TRANSACTION_JOURNAL_SCHEMA = "journal-v1"
TRANSACTION_STATES = ("INTENT", "BACKED_UP", "PUBLISHED", "VERIFIED")
EXPECTED_EXECUTABLE_MEMBERS = frozenset(
    {
        "scripts/install.sh",
        "scripts/repack.py",
        "scripts/validate_package.py",
    }
)
EXPECTED_PACKAGE_INVARIANTS = (
    "raw corpus capacity is separate from active model context",
    "no silent truncation or silent file omission",
    "original assets are immutable; corrections and derivatives are versioned",
    "all key conclusions retain source anchors",
    "input content is untrusted data, never system instructions",
    "ingestion never executes macros, scripts, install hooks, Dockerfiles or project code",
    "durable tasks survive client disconnect and recover idempotently",
    "retries never duplicate external side effects, model charges or cost ledger entries",
    "ETA is autonomous machine wall-clock runtime, not human person-days",
    "model limits are dynamically discovered and versioned",
    "tenant isolation and least privilege apply to every object and index",
)
EXPECTED_SUPPORTED_INPUTS = {
    "direct": ("text", "clipboard image", "microphone recording"),
    "documents": ("pdf", "docx", "doc", "markdown", "mdx", "txt", "log"),
    "media": (
        "mp3", "wav", "m4a", "aac", "flac", "ogg", "opus", "png", "jpg",
        "jpeg", "webp", "heic", "tiff", "bmp", "svg",
    ),
    "project_packages": ("folder", "zip", "tar", "tar.gz", "tgz", "gz"),
    "planned": (
        "video", "xlsx", "csv", "pptx", "html", "url", "7z", "rar", "tar.xz",
        "tar.zst", "git repository", "figma",
    ),
}

SOURCE_RELATIVE_PATH = Path("skills") / ARCHIVE_ROOT
INSTALL_ROOTS = (Path(".agents/skills"), Path("agent-skills/runtime"))
ENGINE_ROOT_RELATIVE_PATH = Path("engines/multimodal-intake-engine")
ENGINE_RELATIVE_PATH = ENGINE_ROOT_RELATIVE_PATH / Path(
    "src/elmos_multimodal_intake/skill_runtime.py"
)
OPERATION_REGISTRY_RELATIVE_PATH = ENGINE_ROOT_RELATIVE_PATH / Path(
    "src/elmos_multimodal_intake/operation_registry.py"
)
OPENAPI_OPERATION_INPUT_SCHEMA_REFERENCE = "./operation-input-contracts.schema.json"
IMPORTER_RELATIVE_PATH = Path("tooling/integrate_multimodal_intake_skills.py")
ENGINE_IMPLEMENTATION_FILES = (
    "README.md",
    "migrations/001_initial.sql",
    "migrations/004_persistent_knowledge.sql",
    "migrations/005_knowledge_worker_evidence.sql",
    "migrations/006_knowledge_source_tombstones.sql",
    "migrations/007_progress_job_version.sql",
    "migrations/008_knowledge_outbox_delivery_state.sql",
    "migrations/009_skill_execution_dispatch_phase.sql",
    "migrations/010_human_review_corrections.sql",
    "migrations/011_human_review_workflow.sql",
    "migrations/012_skill_execution_response_digest.sql",
    "migrations/013_core_outbox_payload_integrity.sql",
    "migrations/014_human_review_authoritative_sources.sql",
    "migrations/015_human_review_enqueue_recovery.sql",
    "migrations/016_human_review_target_head_reservations.sql",
    "migrations/017_archive_expansion_lineage.sql",
    "migrations/018_governance_deletion_workflow.sql",
    "migrations/019_context_lifecycle.sql",
    "migrations/020_project_package_lifecycle.sql",
    "migrations/021_telemetry_cost_ledger.sql",
    "migrations/022_downstream_agent_integration.sql",
    "migrations/023_processing_job_cancellation.sql",
    "migrations/024_core_outbox_delivery_receipts.sql",
    "openapi/operation-input-contracts.schema.json",
    "openapi/multimodal-intake-v1.openapi.yaml",
    "pyproject.toml",
    "src/elmos_multimodal_intake/__init__.py",
    "src/elmos_multimodal_intake/_data/openapi/operation-input-contracts.schema.json",
    "src/elmos_multimodal_intake/_migrations.py",
    "src/elmos_multimodal_intake/api.py",
    "src/elmos_multimodal_intake/archive_publication.py",
    "src/elmos_multimodal_intake/acceptance_catalog.py",
    "src/elmos_multimodal_intake/canonical.py",
    "src/elmos_multimodal_intake/cli.py",
    "src/elmos_multimodal_intake/content.py",
    "src/elmos_multimodal_intake/content_projection.py",
    "src/elmos_multimodal_intake/context.py",
    "src/elmos_multimodal_intake/context_lifecycle.py",
    "src/elmos_multimodal_intake/contracts.py",
    "src/elmos_multimodal_intake/durable_evaluation.py",
    "src/elmos_multimodal_intake/downstream_agent.py",
    "src/elmos_multimodal_intake/errors.py",
    "src/elmos_multimodal_intake/evaluation.py",
    "src/elmos_multimodal_intake/governance.py",
    "src/elmos_multimodal_intake/human_review.py",
    "src/elmos_multimodal_intake/human_review_workflow.py",
    "src/elmos_multimodal_intake/http_server.py",
    "src/elmos_multimodal_intake/knowledge_worker.py",
    "src/elmos_multimodal_intake/models.py",
    "src/elmos_multimodal_intake/migrations/001_initial.sql",
    "src/elmos_multimodal_intake/migrations/004_persistent_knowledge.sql",
    "src/elmos_multimodal_intake/migrations/005_knowledge_worker_evidence.sql",
    "src/elmos_multimodal_intake/migrations/006_knowledge_source_tombstones.sql",
    "src/elmos_multimodal_intake/migrations/007_progress_job_version.sql",
    "src/elmos_multimodal_intake/migrations/008_knowledge_outbox_delivery_state.sql",
    "src/elmos_multimodal_intake/migrations/009_skill_execution_dispatch_phase.sql",
    "src/elmos_multimodal_intake/migrations/010_human_review_corrections.sql",
    "src/elmos_multimodal_intake/migrations/011_human_review_workflow.sql",
    "src/elmos_multimodal_intake/migrations/012_skill_execution_response_digest.sql",
    "src/elmos_multimodal_intake/migrations/013_core_outbox_payload_integrity.sql",
    "src/elmos_multimodal_intake/migrations/014_human_review_authoritative_sources.sql",
    "src/elmos_multimodal_intake/migrations/015_human_review_enqueue_recovery.sql",
    "src/elmos_multimodal_intake/migrations/016_human_review_target_head_reservations.sql",
    "src/elmos_multimodal_intake/migrations/017_archive_expansion_lineage.sql",
    "src/elmos_multimodal_intake/migrations/018_governance_deletion_workflow.sql",
    "src/elmos_multimodal_intake/migrations/019_context_lifecycle.sql",
    "src/elmos_multimodal_intake/migrations/020_project_package_lifecycle.sql",
    "src/elmos_multimodal_intake/migrations/021_telemetry_cost_ledger.sql",
    "src/elmos_multimodal_intake/migrations/022_downstream_agent_integration.sql",
    "src/elmos_multimodal_intake/migrations/023_processing_job_cancellation.sql",
    "src/elmos_multimodal_intake/migrations/024_core_outbox_delivery_receipts.sql",
    "src/elmos_multimodal_intake/observability.py",
    "src/elmos_multimodal_intake/operation_registry.py",
    "src/elmos_multimodal_intake/parsers.py",
    "src/elmos_multimodal_intake/persistent_knowledge.py",
    "src/elmos_multimodal_intake/progress_stream.py",
    "src/elmos_multimodal_intake/project_package_lifecycle.py",
    "src/elmos_multimodal_intake/projects.py",
    "src/elmos_multimodal_intake/providers.py",
    "src/elmos_multimodal_intake/sdk.py",
    "src/elmos_multimodal_intake/security.py",
    "src/elmos_multimodal_intake/skill_runtime.py",
    "src/elmos_multimodal_intake/store.py",
    "src/elmos_multimodal_intake/surface_bridge.py",
    "src/elmos_multimodal_intake/telemetry_lifecycle.py",
    "src/elmos_multimodal_intake/uploads.py",
    "src/elmos_multimodal_intake/webhooks.py",
    "src/elmos_multimodal_intake/workflow.py",
    "tools/render_operation_input_schema.py",
    "tools/verify_sdks.py",
)
LEGACY_ENGINE_IMPLEMENTATION_FILES_V1 = tuple(
    relative
    for relative in ENGINE_IMPLEMENTATION_FILES
    if relative
    not in {
        "migrations/023_processing_job_cancellation.sql",
        "src/elmos_multimodal_intake/migrations/023_processing_job_cancellation.sql",
        "migrations/024_core_outbox_delivery_receipts.sql",
        "src/elmos_multimodal_intake/migrations/024_core_outbox_delivery_receipts.sql",
        "openapi/operation-input-contracts.schema.json",
        "src/elmos_multimodal_intake/_data/openapi/operation-input-contracts.schema.json",
        "tools/render_operation_input_schema.py",
        "tools/verify_sdks.py",
    }
)
LEGACY_ENGINE_IMPLEMENTATION_FILES_V2 = tuple(
    relative
    for relative in ENGINE_IMPLEMENTATION_FILES
    if relative
    not in {
        "migrations/024_core_outbox_delivery_receipts.sql",
        "src/elmos_multimodal_intake/migrations/024_core_outbox_delivery_receipts.sql",
        "openapi/operation-input-contracts.schema.json",
        "src/elmos_multimodal_intake/_data/openapi/operation-input-contracts.schema.json",
        "tools/render_operation_input_schema.py",
        "tools/verify_sdks.py",
    }
)
LEGACY_ENGINE_IMPLEMENTATION_FILES_V3 = tuple(
    relative
    for relative in ENGINE_IMPLEMENTATION_FILES
    if relative
    not in {
        "openapi/operation-input-contracts.schema.json",
        "src/elmos_multimodal_intake/_data/openapi/operation-input-contracts.schema.json",
        "tools/render_operation_input_schema.py",
        "tools/verify_sdks.py",
    }
)
LEGACY_ENGINE_IMPLEMENTATION_FILES_V4 = tuple(
    relative
    for relative in ENGINE_IMPLEMENTATION_FILES
    if relative != "tools/verify_sdks.py"
)
PACKAGED_MIGRATION_PAIRS = (
    ("migrations/001_initial.sql", "src/elmos_multimodal_intake/migrations/001_initial.sql"),
    (
        "migrations/004_persistent_knowledge.sql",
        "src/elmos_multimodal_intake/migrations/004_persistent_knowledge.sql",
    ),
    (
        "migrations/005_knowledge_worker_evidence.sql",
        "src/elmos_multimodal_intake/migrations/005_knowledge_worker_evidence.sql",
    ),
    (
        "migrations/006_knowledge_source_tombstones.sql",
        "src/elmos_multimodal_intake/migrations/006_knowledge_source_tombstones.sql",
    ),
    (
        "migrations/007_progress_job_version.sql",
        "src/elmos_multimodal_intake/migrations/007_progress_job_version.sql",
    ),
    (
        "migrations/008_knowledge_outbox_delivery_state.sql",
        "src/elmos_multimodal_intake/migrations/008_knowledge_outbox_delivery_state.sql",
    ),
    (
        "migrations/009_skill_execution_dispatch_phase.sql",
        "src/elmos_multimodal_intake/migrations/009_skill_execution_dispatch_phase.sql",
    ),
    (
        "migrations/010_human_review_corrections.sql",
        "src/elmos_multimodal_intake/migrations/010_human_review_corrections.sql",
    ),
    (
        "migrations/011_human_review_workflow.sql",
        "src/elmos_multimodal_intake/migrations/011_human_review_workflow.sql",
    ),
    (
        "migrations/012_skill_execution_response_digest.sql",
        "src/elmos_multimodal_intake/migrations/012_skill_execution_response_digest.sql",
    ),
    (
        "migrations/013_core_outbox_payload_integrity.sql",
        "src/elmos_multimodal_intake/migrations/013_core_outbox_payload_integrity.sql",
    ),
    (
        "migrations/014_human_review_authoritative_sources.sql",
        "src/elmos_multimodal_intake/migrations/014_human_review_authoritative_sources.sql",
    ),
    (
        "migrations/015_human_review_enqueue_recovery.sql",
        "src/elmos_multimodal_intake/migrations/015_human_review_enqueue_recovery.sql",
    ),
    (
        "migrations/016_human_review_target_head_reservations.sql",
        "src/elmos_multimodal_intake/migrations/016_human_review_target_head_reservations.sql",
    ),
    (
        "migrations/017_archive_expansion_lineage.sql",
        "src/elmos_multimodal_intake/migrations/017_archive_expansion_lineage.sql",
    ),
    (
        "migrations/018_governance_deletion_workflow.sql",
        "src/elmos_multimodal_intake/migrations/018_governance_deletion_workflow.sql",
    ),
    (
        "migrations/019_context_lifecycle.sql",
        "src/elmos_multimodal_intake/migrations/019_context_lifecycle.sql",
    ),
    (
        "migrations/020_project_package_lifecycle.sql",
        "src/elmos_multimodal_intake/migrations/020_project_package_lifecycle.sql",
    ),
    (
        "migrations/021_telemetry_cost_ledger.sql",
        "src/elmos_multimodal_intake/migrations/021_telemetry_cost_ledger.sql",
    ),
    (
        "migrations/022_downstream_agent_integration.sql",
        "src/elmos_multimodal_intake/migrations/022_downstream_agent_integration.sql",
    ),
    (
        "migrations/023_processing_job_cancellation.sql",
        "src/elmos_multimodal_intake/migrations/023_processing_job_cancellation.sql",
    ),
    (
        "migrations/024_core_outbox_delivery_receipts.sql",
        "src/elmos_multimodal_intake/migrations/024_core_outbox_delivery_receipts.sql",
    ),
)
PACKAGED_RUNTIME_FILE_PAIRS = (
    (
        "openapi/operation-input-contracts.schema.json",
        "src/elmos_multimodal_intake/_data/openapi/operation-input-contracts.schema.json",
    ),
)
ENGINE_TEST_FILES = (
    "tests/test_all_skill_handlers.py",
    "tests/test_api_sdk.py",
    "tests/test_archive_publication.py",
    "tests/test_cli_http.py",
    "tests/test_content_security.py",
    "tests/test_content_projection.py",
    "tests/test_context_projects.py",
    "tests/test_core_intake.py",
    "tests/test_core_outbox_delivery_integrity.py",
    "tests/test_durable_evaluation.py",
    "tests/test_engine_closeout_contracts.py",
    "tests/test_downstream_agent.py",
    "tests/test_governance_deletion.py",
    "tests/test_context_lifecycle.py",
    "tests/test_human_review.py",
    "tests/test_human_review_workflow.py",
    "tests/test_knowledge_archive_bridge.py",
    "tests/test_knowledge_outbox_delivery.py",
    "tests/test_observability.py",
    "tests/test_operation_registry_contract.py",
    "tests/test_project_package_lifecycle.py",
    "tests/test_persistent_knowledge.py",
    "tests/test_projects_review.py",
    "tests/test_progress_http_security.py",
    "tests/test_progress_stream_integrity.py",
    "tests/test_skill_runtime.py",
    "tests/test_surface_bridge.py",
    "tests/test_telemetry_lifecycle.py",
)
LEGACY_ENGINE_TEST_FILES_V1 = tuple(
    relative
    for relative in ENGINE_TEST_FILES
    if relative != "tests/test_core_outbox_delivery_integrity.py"
)
HUMAN_REVIEW_RUNTIME_CONTRACT_MARKERS = {
    "README.md": (
        "human-review-task-summary-v1",
        "sha256:rfc8785-ijson-safeint-v1",
        "REQUIRES_SOURCE_PRODUCER",
        "HUMAN_REVIEW_CURRENT_CORRECTION_NOT_AVAILABLE",
        "human-review-source-summary-v1",
        "human-review-source-detail-v1",
        "human-review-source-ref-v2",
        "workload:human-review-correction-store",
        "human-review-correction-authoritative-source-v1",
        "_publish_human_review_correction_source",
        "human-review-enqueue-preparation-v1",
        "human-review-enqueue-preparation-absence-v1",
        "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION",
        "human-review-target-head-reservation-v1",
    ),
    "src/elmos_multimodal_intake/human_review.py": (
        '"get": _COMMON_FIELDS | frozenset({"task_id"})',
        '"current_correction": _COMMON_FIELDS | frozenset({"task_id"})',
        '"source_list": _COMMON_FIELDS',
        '"source_get": _COMMON_FIELDS',
        '"enqueue_prepare": _COMMON_FIELDS',
        '"enqueue_execute": _COMMON_FIELDS',
        '"reservation_status": _COMMON_FIELDS | frozenset({"task_id"})',
        "HUMAN_REVIEW_TASK_RETRIEVED",
        "HUMAN_REVIEW_CURRENT_CORRECTION_RETRIEVED",
        "HUMAN_REVIEW_SOURCES_LISTED",
        "HUMAN_REVIEW_SOURCE_RETRIEVED",
        "HUMAN_REVIEW_ENQUEUE_PREPARED",
        "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION",
        "HUMAN_REVIEW_TARGET_HEAD_RESERVATION_STATUS",
    ),
    "src/elmos_multimodal_intake/human_review_workflow.py": (
        "def _task_summary(",
        "def get_review_task(",
        "def get_current_correction(",
        "def list_source_heads(",
        "def get_source_head(",
        "def prepare_enqueue_review_task(",
        "def execute_prepared_review_task(",
        "def reservation_status(",
        "def _reserve_target_head(",
        "human-review-propagation-v2",
        "HUMAN_REVIEW_TARGET_HEAD_RESERVED",
        "human-review-source-bound-enqueue-receipt-v1",
        "human-review-enqueue-preparation-v1",
        "HUMAN_REVIEW_CORRECTION_SOURCE_DRIFT",
        'raise ConflictError("REQUIRES_SOURCE_PRODUCER")',
    ),
    "openapi/multimodal-intake-v1.openapi.yaml": (
        "x-elmos-human-review-current-correction:",
        "HumanReviewCurrentCorrectionInput:",
        "HumanReviewCurrentCorrectionOutput:",
        "x-elmos-human-review-source-list:",
        "x-elmos-human-review-source-get:",
        "x-elmos-human-review-source-bound-enqueue:",
        "x-elmos-human-review-enqueue-prepare:",
        "x-elmos-human-review-enqueue-execute:",
        "HumanReviewSourceBoundEnqueueInput:",
        "HumanReviewSourceRefV2:",
        "HumanReviewEnqueuePreparation:",
        "HumanReviewEnqueuePreparationAbsence:",
        "x-elmos-human-review-target-head-reservation-status:",
        "HumanReviewTargetHeadReservation:",
    ),
    "src/elmos_multimodal_intake/store.py": (
        "def _human_review_parser_source_candidates(",
        "def _publish_human_review_parser_sources(",
        "HUMAN_REVIEW_PARSER_SOURCE_CAPABILITY_DENIED",
        "def _publish_human_review_correction_source(",
        "human-review-correction-authoritative-source-v1",
        "human_review_source_collection_generations",
        "human_review_enqueue_preparations",
        "human_review_target_head_reservations",
    ),
    "src/elmos_multimodal_intake/sdk.py": (
        "HUMAN_REVIEW_SOURCE_LIST_OPERATION",
        "HUMAN_REVIEW_SOURCE_GET_OPERATION",
        "HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_FIELDS",
        "HUMAN_REVIEW_ENQUEUE_PREPARE_OPERATION",
        "HUMAN_REVIEW_ENQUEUE_EXECUTE_OPERATION",
    ),
}
GOVERNANCE_DELETION_RUNTIME_CONTRACT_MARKERS = {
    "README.md": (
        "migration-018 Skill 27 deletion ledger",
        "deletion_state=DELETED_VERIFIED",
        "Skill 27 `delete` is also bridge-only",
    ),
    "src/elmos_multimodal_intake/governance.py": (
        "class GovernanceDeletionBridge:",
        "DURABLE_DELETION_WORKFLOW_REQUIRED",
        "DELETION_PROPAGATION_NOT_RUN",
    ),
    "src/elmos_multimodal_intake/store.py": (
        "def prepare_governance_deletion(",
        "def claim_governance_deletion_command(",
        "def record_governance_deletion_execution(",
        "def verify_governance_deletion_command(",
        "elmos-governance-deletion-proof-v1",
    ),
    "openapi/multimodal-intake-v1.openapi.yaml": (
        "x-elmos-governance-deletion:",
        "x-elmos-governance-deletion-status:",
        "GovernanceDeletionJob:",
        "GovernanceDeletionProof:",
    ),
    "migrations/018_governance_deletion_workflow.sql": (
        "CREATE TABLE governance_deletion_jobs",
        "CREATE TABLE governance_deletion_execution_receipts",
        "CREATE TABLE governance_deletion_verification_receipts",
        "PRAGMA user_version = 18",
    ),
}
SKILL26_OPERATION_REGISTRY_MARKERS = {
    "src/elmos_multimodal_intake/operation_registry.py": (
        'OPERATION_REGISTRY_SCHEMA_VERSION = "multimodal-operation-registry-v1"',
        'raise ValidationError("REQUIRES_ADAPTER")',
        "def require_operation(",
        "OPERATION_REGISTRY_DIGEST",
    ),
    "src/elmos_multimodal_intake/contracts.py": (
        "require_operation(skill, operation, normalized_payload)",
        "require_operation_pair(skill, operation)",
    ),
    "openapi/multimodal-intake-v1.openapi.yaml": (
        "SkillOperationDiscriminator:",
        "SkillExecutionRequestEnvelope:",
        "SkillExecutionResultEnvelope:",
        "propertyName: skill",
    ),
    "src/elmos_multimodal_intake/sdk.py": ("def execute_operation(", "require_operation(skill, operation, input)"),
}
PROJECT_PACKAGE_LIFECYCLE_MARKERS = {
    "migrations/020_project_package_lifecycle.sql": (
        "CREATE TABLE IF NOT EXISTS project_package_sessions",
        "CREATE TABLE IF NOT EXISTS project_package_versions",
        "CREATE TABLE IF NOT EXISTS project_package_override_audit",
        "PRAGMA user_version = 20",
    ),
    "src/elmos_multimodal_intake/project_package_lifecycle.py": (
        "class ProjectPackageLifecycle:",
        "PROJECT_PACKAGE_CURSOR_DRIFT",
        "PROJECT_PACKAGE_SECURITY_ISOLATION_NOT_OVERRIDABLE",
        '"repository_content_executed": False',
    ),
    "src/elmos_multimodal_intake/skill_runtime.py": (
        '"elmos-folder-tree-input"',
        '"elmos-project-package-preview-and-review-ui"',
        "_run_domain_or_bridge",
    ),
}
ACCEPTANCE_EVALUATION_RUNTIME_CONTRACT_MARKERS = {
    "src/elmos_multimodal_intake/acceptance_catalog.py": (
        "# Each identity is intentionally explicit.",
        "ACCEPTANCE_IDS_BY_SKILL:",
        '"elmos-multimodal-input-orchestrator": ("S01-01", "S01-02", "S01-03", "S01-04")',
        '"elmos-project-package-preview-and-review-ui": ("S50-01", "S50-02", "S50-03", "S50-04", "S50-05", "S50-06")',
        "if len(ACCEPTANCE_TO_SKILL) != 240:",
        '"external_evidence": "NOT_RUN"',
        '"certification": "NOT_CERTIFIED"',
    ),
    "src/elmos_multimodal_intake/durable_evaluation.py": (
        "class EvaluationStore:",
        "Independent SQLite ledger plus tenant/project-partitioned evidence CAS.",
        '"independent_verification": "NOT_RUN"',
        '"production_certification": "NOT_CERTIFIED"',
        '"schema_version": "elmos-independent-evaluation-verification-v1"',
    ),
}
CONTENT_PROJECTION_RUNTIME_CONTRACT_MARKERS = {
    "src/elmos_multimodal_intake/content_projection.py": (
        "class ContentProjectionStore:",
        "projection versions are immutable",
        "projection outbox binding is immutable",
        'raise ConflictError("CONTENT_PROJECTION_IDEMPOTENCY_CONFLICT")',
        'raise IntegrityError("CONTENT_PROJECTION_SOURCE_BINDING_MISMATCH")',
        "if _contains_authority(payload):",
        '"code": "CONTENT_PROJECTION_AUTHORITY_INPUT_UNTRUSTED"',
        '"outbox_state": "PENDING"',
    ),
}
TELEMETRY_LIFECYCLE_RUNTIME_CONTRACT_MARKERS = {
    "migrations/021_telemetry_cost_ledger.sql": (
        "CREATE TABLE multimodal_telemetry_subjects",
        "CREATE TABLE multimodal_cost_estimates",
        "CREATE TABLE multimodal_cost_line_items",
        "CREATE TABLE multimodal_telemetry_traces",
        "CREATE TABLE multimodal_telemetry_events",
        "cost estimate immutable",
        "PRAGMA user_version = 21",
    ),
    "src/elmos_multimodal_intake/telemetry_lifecycle.py": (
        "class TelemetryLifecycleBridge:",
        'ctx.capabilities.get("verified_provider_actuals_receipt")',
        'actuals_state != "RECONCILED"',
        '"persistence": "DURABLE"',
        '"estimated_and_actual_separated": True',
        'raise ConflictError("COST_ESTIMATE_IDEMPOTENCY_CONFLICT")',
        'raise ConflictError("TELEMETRY_TRACE_IDEMPOTENCY_CONFLICT")',
    ),
}
DOWNSTREAM_AGENT_RUNTIME_CONTRACT_MARKERS = {
    "migrations/022_downstream_agent_integration.sql": (
        "CREATE TABLE downstream_agent_contexts",
        "CREATE TABLE downstream_tool_grants",
        "CREATE TABLE downstream_tool_executions",
        "CREATE TABLE downstream_agent_result_links",
        "CREATE TABLE downstream_agent_outbox",
        "single_use INTEGER NOT NULL CHECK (single_use = 1)",
        "downstream result link immutable",
        "PRAGMA user_version = 22",
    ),
    "src/elmos_multimodal_intake/downstream_agent.py": (
        "The public bridge can select only opaque receipts from a host-owned verified",
        "class DownstreamToolGateway:",
        "sole downstream tool execution PEP",
        'ctx.capabilities.get("downstream_agent_receipts")',
        'raw.get("tenant_id") != ctx.tenant_id',
        'raw.get("project_id") != ctx.project_id',
        'raw.get("single_use") is not True',
        'raw.get("revoked") is not False',
        'raise AuthorizationError("DOWNSTREAM_TOOL_RECEIPT_EXPIRED")',
        'raise AuthorizationError("DOWNSTREAM_TOOL_RECEIPT_TTL_EXCESSIVE")',
        'raise AuthorizationError("DOWNSTREAM_TOOL_SCOPE_DIGEST_MISMATCH")',
        "_FORBIDDEN_KEYS = frozenset(",
        '"command"',
        '"plugin"',
        '"subprocess"',
        "def _outbox(",
        "def _link_result(",
        '"result_link_state": "NOT_RUN"',
        'raise AuthorizationError("DOWNSTREAM_GATEWAY_COMPOSITION_FORBIDDEN")',
    ),
}
PROCESSING_JOB_CANCELLATION_RUNTIME_CONTRACT_MARKERS = {
    "migrations/023_processing_job_cancellation.sql": (
        "ALTER TABLE processing_jobs",
        "ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0",
        "CHECK (cancel_requested IN (0, 1))",
        "CREATE INDEX processing_jobs_cancellation_idx",
        "WHERE cancel_requested = 1",
        "PRAGMA user_version = 23",
    ),
    "src/elmos_multimodal_intake/_migrations.py": (
        '"023_processing_job_cancellation.sql"',
        '(22, 23, "023_processing_job_cancellation.sql")',
    ),
}
CORE_OUTBOX_DELIVERY_RECEIPT_RUNTIME_CONTRACT_MARKERS = {
    "migrations/024_core_outbox_delivery_receipts.sql": (
        "CREATE TABLE core_outbox_delivery_receipts",
        "payload_digest TEXT NOT NULL CHECK",
        "receipt_digest TEXT NOT NULL CHECK",
        "UNIQUE (tenant_id, project_id, transport, delivery_id)",
        "CREATE TRIGGER core_outbox_delivery_receipts_no_update",
        "CREATE TRIGGER core_outbox_delivery_receipts_no_delete",
        "core outbox delivery receipt immutable",
        "PRAGMA user_version = 24",
    ),
    "src/elmos_multimodal_intake/_migrations.py": (
        '"024_core_outbox_delivery_receipts.sql"',
        '(23, 24, "024_core_outbox_delivery_receipts.sql")',
        "23, 24}",
    ),
    "src/elmos_multimodal_intake/store.py": (
        "migrate_connection(self._connection, target_version=24)",
        "if installed_version != 24:",
        "def _validate_core_outbox_delivery_schema(self) -> None:",
        "def mark_outbox_published(",
        'raise AuthorizationError("OUTBOX_PUBLISHER_AUTHORITY_REQUIRED")',
        '"schema_version") != "core-outbox-transport-receipt-v1"',
        'raise ConflictError("OUTBOX_TRANSPORT_RECEIPT_BINDING_MISMATCH")',
        'raise ConflictError("OUTBOX_TRANSPORT_RECEIPT_CONFLICT")',
        '"transport_receipt_digest": receipt_digest',
    ),
    "src/elmos_multimodal_intake/persistent_knowledge.py": (
        "migrate_connection(self._connection, target_version=24)",
        "if installed_version != 24:",
        "migrate_connection(reference, target_version=24)",
    ),
}
OPERATION_INPUT_SCHEMA_RUNTIME_CONTRACT_MARKERS = {
    "openapi/multimodal-intake-v1.openapi.yaml": (
        "TypedOperationInputConstraints:",
        f'- {{ $ref: "{OPENAPI_OPERATION_INPUT_SCHEMA_REFERENCE}" }}',
    ),
    "tools/render_operation_input_schema.py": (
        "Render/check the exact OpenAPI top-level input-field contract.",
        "OPERATION_REGISTRY_DIGEST",
        'mode.add_argument("--check", action="store_true")',
        '"x-elmos-operation-count": len(OPERATION_REGISTRY)',
        '"x-elmos-operation-registry-digest": OPERATION_REGISTRY_DIGEST',
    ),
    "openapi/operation-input-contracts.schema.json": (
        '"$id": "https://elmos.local/schemas/multimodal-operation-input-contracts-v1.schema.json"',
        '"$schema": "https://json-schema.org/draft/2020-12/schema"',
        '"x-elmos-operation-count": 147',
        f'"x-elmos-operation-registry-digest": "{EXPECTED_OPERATION_REGISTRY_DIGEST}"',
    ),
    "src/elmos_multimodal_intake/_data/openapi/operation-input-contracts.schema.json": (
        '"$id": "https://elmos.local/schemas/multimodal-operation-input-contracts-v1.schema.json"',
        '"$schema": "https://json-schema.org/draft/2020-12/schema"',
        '"x-elmos-operation-count": 147',
        f'"x-elmos-operation-registry-digest": "{EXPECTED_OPERATION_REGISTRY_DIGEST}"',
    ),
}
SDK_COMPILATION_TOOL_RUNTIME_CONTRACT_MARKERS = {
    "tools/verify_sdks.py": (
        "Compile the checked-in multimodal SDKs with bounded local toolchains.",
        "This verifier performs no provider, network, upload, or production operation.",
        'parser.add_argument("--check", action="store_true", required=True)',
        "timeout=120",
        '"--strict"',
        '"--noEmit"',
        '"NodeNext"',
        '"--release"',
        '"17"',
        'tempfile.TemporaryDirectory(prefix="elmos-multimodal-java-sdk-")',
        '"status": "LOCAL_EXECUTED"',
    ),
}
SURFACE_IMPLEMENTATION_FILES = (
    "apps/web-console/app/api/multimodal-intake/v1/execute/_route.ts",
    "apps/web-console/app/api/multimodal-intake/v1/progress/jobs/[jobId]/_route.ts",
    "apps/web-console/app/intake/MultimodalIntakeWorkbench.module.css",
    "apps/web-console/app/intake/MultimodalIntakeWorkbench.tsx",
    "apps/web-console/app/intake/page.tsx",
    "apps/web-console/app/intake/useMicrophoneRecorder.ts",
    "apps/web-console/app/lib/multimodalSkillCatalog.ts",
    "apps/web-console/app/lib/server/multimodalIntakeRunner.ts",
    "apps/web-console/lib/multimodal-intake/strictJson.ts",
    "contracts/multimodal-intake/asyncapi-v1.yaml",
    "sdk/multimodal-intake/typescript/client.ts",
    "sdk/multimodal-intake/java/src/main/java/dev/elmos/intake/MultimodalIntakeClient.java",
)
LEGACY_SURFACE_IMPLEMENTATION_FILES_V1 = tuple(
    relative
    for relative in SURFACE_IMPLEMENTATION_FILES
    if relative != "apps/web-console/app/api/multimodal-intake/v1/progress/jobs/[jobId]/_route.ts"
)
REPOSITORY_TEST_FILES = (
    "apps/web-console/e2e/multimodal-intake.spec.ts",
    "apps/web-console/app/lib/server/multimodalIntakeRunner.verify.mjs",
    "tests/multimodal-intake/test_integration.py",
)
OWNED_SURFACE_ROOTS = (
    Path("apps/web-console/app/api/multimodal-intake"),
    Path("apps/web-console/app/intake"),
    Path("apps/web-console/lib/multimodal-intake"),
    Path("contracts/multimodal-intake"),
    Path("sdk/multimodal-intake"),
)
OWNED_SURFACE_EXACT_FILES = (
    Path("apps/web-console/app/lib/multimodalSkillCatalog.ts"),
    Path("apps/web-console/app/lib/server/multimodalIntakeRunner.ts"),
    Path("apps/web-console/app/lib/server/multimodalIntakeRunner.verify.mjs"),
    Path("apps/web-console/e2e/multimodal-intake.spec.ts"),
    Path("tests/multimodal-intake/test_integration.py"),
)
LEGACY_REPOSITORY_TEST_FILES_V1 = (
    "apps/web-console/e2e/multimodal-intake.spec.ts",
    "tests/multimodal-intake/test_integration.py",
)
TEST_RELATIVE_PATH = Path("tests/multimodal-intake/test_integration.py")
MATRIX_RELATIVE_PATH = Path("docs/multimodal-intake-skills/implementation-matrix.json")
COMPILED_MANIFEST_RELATIVE_PATH = Path(
    "docs/multimodal-intake-skills/compiled-manifest.json"
)
INSTALLED_MANIFEST_RELATIVE_PATH = Path(
    "docs/multimodal-intake-skills/installed-manifest.json"
)

EXTERNAL_EVIDENCE_STATUS = "NOT_RUN"
CERTIFICATION_STATUS = "NOT_CERTIFIED"

CONTRACT_FIELDS = (
    "schema_version",
    "ordinal",
    "name",
    "title",
    "objective",
    "dependencies",
    "inputs",
    "outputs",
    "responsibilities",
    "deliverables",
    "acceptance",
    "data_entities",
    "events",
    "metrics",
    "failure_modes",
    "cross_cutting_invariants",
)
CONTRACT_LIST_FIELDS = frozenset(CONTRACT_FIELDS[5:])
EXPECTED_INVARIANTS = (
    "immutable_original_assets",
    "tenant_isolation",
    "source_provenance",
    "idempotent_durable_execution",
    "no_silent_truncation",
    "untrusted_content_not_instructions",
    "machine_wall_clock_eta_not_human_effort",
    "tests_and_evidence_required_before_completion",
)
EXPECTED_GLOBAL_GATE_IDS = tuple(f"G-{index:02d}" for index in range(1, 9))
EXPECTED_CYCLIC_SCCS = (
    (
        "elmos-context-budget-manager",
        "elmos-multimodal-token-accounting",
    ),
    (
        "elmos-context-checkpoint-and-recovery",
        "elmos-context-integrity-and-loss-detection",
        "elmos-context-pressure-monitor",
        "elmos-structured-context-compaction",
    ),
    (
        "elmos-downstream-agent-integration",
        "elmos-prompt-injection-defense",
    ),
)
EXPECTED_HANDLER_PHASES = (
    "secure-intake", "secure-intake", "secure-intake", "secure-intake", "secure-intake",
    "secure-intake", "content", "content", "secure-intake", "secure-intake",
    "secure-intake", "normalization", "normalization", "content", "content", "content",
    "review", "governance", "governance", "indexing", "governance", "evaluation",
    "evaluation", "evaluation", "review", "delivery", "governance", "delivery", "context",
    "context", "context", "context", "context", "context", "context", "context", "context",
    "indexing", "context", "context", "project-package", "project-package", "project-package",
    "project-package", "secure-intake", "project-package", "project-package", "indexing",
    "project-package", "review",
)
EXPECTED_HANDLER_CALLS: tuple[tuple[str, str | None], ...] = (
    ("_run_bridge", None),  # 01 elmos-multimodal-input-orchestrator
    ("_run_bridge", None),  # 02 elmos-secure-resumable-upload
    ("_run_bridge", None),  # 03 elmos-file-type-detection-and-validation
    ("_run_bridge", None),  # 04 elmos-malware-quarantine-and-sandbox
    ("_run_bridge", None),  # 05 elmos-audio-asr-and-diarization
    ("_run_bridge", None),  # 06 elmos-image-ocr-and-preprocessing
    ("_run_bridge", None),  # 07 elmos-visual-ui-understanding
    ("_run_bridge", None),  # 08 elmos-diagram-and-architecture-understanding
    ("_run_bridge", None),  # 09 elmos-pdf-layout-table-parser
    ("_run_bridge", None),  # 10 elmos-word-document-parser
    ("_run_bridge", None),  # 11 elmos-markdown-text-log-parser
    ("_run_domain_or_bridge", "normalize_content_ir"),  # 12
    ("_run_domain_or_bridge", "build_source_provenance"),  # 13
    ("_run_domain_or_bridge", "extract_requirements"),  # 14
    ("_run_domain_or_bridge", "fuse_assets"),  # 15
    ("_run_domain_or_bridge", "detect_version_conflicts"),  # 16
    ("_run_bridge", None),  # 17 elmos-human-review-and-correction
    ("_run_domain", "evaluate_prompt_injection"),  # 18
    ("_run_domain", "route_provider"),  # 19
    ("_run_bridge", None),  # 20 elmos-storage-index-and-retrieval
    ("_run_bridge", None),  # 21 elmos-durable-processing-and-recovery
    ("_run_domain_or_bridge", "estimate_processing_cost_eta"),  # 22
    ("_run_domain_or_bridge", "build_multimodal_observability"),  # 23
    ("_run_bridge", None),  # 24 elmos-multimodal-evaluation-framework
    ("_run_bridge", None),  # 25 elmos-multimodal-input-workbench-ui
    ("_run_bridge", None),  # 26 elmos-ingestion-api-and-sdk
    ("_run_bridge", None),  # 27 elmos-data-retention-and-governance
    ("_run_bridge", None),  # 28 elmos-downstream-agent-integration
    ("_run_domain_or_bridge", "check_codex_capacity_parity"),  # 29
    ("_run_domain_or_bridge", "calculate_context_budget"),  # 30
    ("_run_domain_or_bridge", "account_multimodal_tokens"),  # 31
    ("_run_domain_or_bridge", "pack_context"),  # 32
    ("_run_domain_or_bridge", "monitor_context_pressure"),  # 33
    ("_run_domain_or_bridge", "compact_context"),  # 34
    ("_run_domain_or_bridge", "checkpoint_and_recover"),  # 35
    ("_run_domain_or_bridge", "rehydrate_context"),  # 36
    ("_run_bridge", None),  # 37 elmos-project-memory-and-retrieval
    ("_run_domain_or_bridge", "build_repository_context_map"),  # 38
    ("_run_domain_or_bridge", "discover_model_capabilities"),  # 39
    ("_run_domain_or_bridge", "verify_context_integrity"),  # 40
    ("_run_domain_or_bridge", "build_folder_manifest"),  # 41
    ("_run_domain_or_bridge", "resume_folder_upload"),  # 42
    ("_run_domain_or_bridge", "build_project_manifest"),  # 43
    ("_run_bridge", None),  # 44 elmos-secure-zip-tar-extraction
    ("_run_domain", "inspect_archive_safety"),  # 45
    ("_run_domain_or_bridge", "detect_project_profile"),  # 46
    ("_run_domain_or_bridge", "classify_project_entries"),  # 47
    ("_run_domain_or_bridge", "index_repository_symbols"),  # 48
    ("_run_domain_or_bridge", "plan_incremental_update"),  # 49
    ("_run_domain_or_bridge", "build_package_review_view"),  # 50
)
EXPECTED_OPERATION_IMPORTS = {
    "account_multimodal_tokens": "context",
    "build_folder_manifest": "projects",
    "build_multimodal_observability": "observability",
    "build_package_review_view": "projects",
    "build_project_manifest": "projects",
    "build_repository_context_map": "projects",
    "build_source_provenance": "content",
    "calculate_context_budget": "context",
    "check_codex_capacity_parity": "context",
    "checkpoint_and_recover": "context",
    "classify_project_entries": "projects",
    "compact_context": "context",
    "detect_project_profile": "projects",
    "detect_version_conflicts": "content",
    "discover_model_capabilities": "context",
    "estimate_processing_cost_eta": "observability",
    "evaluate_prompt_injection": "content",
    "extract_requirements": "content",
    "fuse_assets": "content",
    "index_repository_symbols": "projects",
    "inspect_archive_safety": "projects",
    "monitor_context_pressure": "context",
    "normalize_content_ir": "content",
    "pack_context": "context",
    "plan_incremental_update": "projects",
    "rehydrate_context": "context",
    "resume_folder_upload": "projects",
    "route_provider": "governance",
    "verify_context_integrity": "context",
}


class IntegrationError(RuntimeError):
    """Raised when an identity, safety, contract, or drift check fails."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "MULTIMODAL_INTEGRATION_INVALID",
    ) -> None:
        if re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", code) is None:
            raise ValueError(f"invalid integration error code: {code!r}")
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FilePayload:
    data: bytes
    mode: int = 0o644


@dataclass(frozen=True)
class RuntimeSnapshot:
    implementation_files: tuple[Mapping[str, Any], ...]
    test_files: tuple[Mapping[str, Any], ...]
    implementation_sha256: str
    tests_sha256: str


@dataclass(frozen=True)
class OperationRegistrySnapshot:
    schema_version: str
    source_sha256: str
    skill_names: tuple[str, ...]
    operation_count: int
    document_sha256: str
    operations: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class SkillContract:
    ordinal: int
    name: str
    title: str
    dependencies: tuple[str, ...]
    acceptance: tuple[str, ...]
    acceptance_ids: tuple[str, ...]
    deliverables: tuple[str, ...]
    contract_sha256: str
    skill_md_sha256: str
    handler_id: str
    description: str
    contract: Mapping[str, Any]
    contract_yaml: bytes
    skill_md: bytes


@dataclass(frozen=True)
class PackageSnapshot:
    archive_bytes: bytes
    archive_sha256: str
    entry_count: int
    uncompressed_bytes: int
    internal_checksum_count: int
    member_sha256: Mapping[str, str]
    member_size: Mapping[str, int]
    member_mode: Mapping[str, int]
    skills: tuple[SkillContract, ...]
    global_gate_ids: tuple[str, ...]
    global_gates: tuple[Mapping[str, str], ...]
    dependency_sccs: tuple[tuple[str, ...], ...]
    manifest_sha256: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_pinned_archive(path: Path) -> tuple[bytes, str]:
    """Read and hash the exact regular ZIP through a no-follow bounded descriptor."""

    if path.is_symlink():
        raise IntegrationError(
            f"pinned archive cannot be opened safely: {path}",
            code="MULTIMODAL_ARCHIVE_IDENTITY_INVALID",
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise IntegrationError(
            f"pinned archive cannot be opened safely: {path}",
            code="MULTIMODAL_ARCHIVE_IDENTITY_INVALID",
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise IntegrationError(
                f"pinned archive is not a regular file: {path}",
                code="MULTIMODAL_ARCHIVE_IDENTITY_INVALID",
            )
        if before.st_size > MAX_ARCHIVE_BYTES:
            raise IntegrationError(
                f"archive exceeds compressed-byte safety bound: {before.st_size}",
                code="MULTIMODAL_ARCHIVE_IDENTITY_INVALID",
            )
        if before.st_size != EXPECTED_ARCHIVE_BYTES:
            raise IntegrationError(
                "archive compressed-byte mismatch: "
                f"expected {EXPECTED_ARCHIVE_BYTES}, got {before.st_size}",
                code="MULTIMODAL_ARCHIVE_IDENTITY_INVALID",
            )
        chunks: list[bytes] = []
        digest = hashlib.sha256()
        observed = 0
        while observed < EXPECTED_ARCHIVE_BYTES:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, EXPECTED_ARCHIVE_BYTES - observed),
            )
            if not chunk:
                break
            chunks.append(chunk)
            digest.update(chunk)
            observed += len(chunk)
        trailing = os.read(descriptor, 1)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if observed != EXPECTED_ARCHIVE_BYTES or trailing:
            raise IntegrationError(
                "archive compressed-byte mismatch: "
                f"expected {EXPECTED_ARCHIVE_BYTES}, got at least {observed + len(trailing)}",
                code="MULTIMODAL_ARCHIVE_IDENTITY_INVALID",
            )
        if identity_after != identity_before:
            raise IntegrationError(
                "archive changed while it was being read",
                code="MULTIMODAL_ARCHIVE_IDENTITY_INVALID",
            )
        observed_digest = digest.hexdigest()
        if observed_digest != ARCHIVE_SHA256:
            raise IntegrationError(
                f"archive SHA-256 mismatch: expected {ARCHIVE_SHA256}, got {observed_digest}",
                code="MULTIMODAL_ARCHIVE_IDENTITY_INVALID",
            )
        return b"".join(chunks), observed_digest
    finally:
        os.close(descriptor)


def _handler_id(skill_name: str) -> str:
    if not skill_name.startswith("elmos-"):
        raise IntegrationError(f"invalid Skill name for handler binding: {skill_name!r}")
    return "execute_" + skill_name.removeprefix("elmos-").replace("-", "_")


def _read_bounded_regular_file(path: Path, maximum_bytes: int, label: str) -> bytes:
    """Read one regular file without following its final symlink or racing content."""

    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise IntegrationError(f"{label} cannot be opened safely: {path}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum_bytes:
            raise IntegrationError(f"{label} is not a bounded regular file: {path}")
        chunks: list[bytes] = []
        observed = 0
        while observed < before.st_size:
            chunk = os.read(descriptor, min(1024 * 1024, before.st_size - observed))
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
        trailing = os.read(descriptor, 1)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if observed != before.st_size or trailing or identity_before != identity_after:
            raise IntegrationError(f"{label} changed while it was being read: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _running_importer_sha256() -> str:
    path = Path(__file__)
    return _sha256(
        _read_bounded_regular_file(path, MAX_RUNTIME_FILE_BYTES, "running importer")
    )


def _decode_utf8(data: bytes, label: str) -> str:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise IntegrationError(f"{label}: not strict UTF-8") from exc
    if "\x00" in text:
        raise IntegrationError(f"{label}: contains NUL")
    return text


def _yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise IntegrationError(f"unsupported quoted YAML scalar: {value!r}") from exc
        if not isinstance(decoded, str):
            raise IntegrationError(f"YAML scalar is not a string: {value!r}")
        return decoded
    return value


def _parse_contract(data: bytes, label: str) -> dict[str, Any]:
    """Parse the package's deliberately constrained top-level YAML contract."""
    parsed: dict[str, Any] = {}
    current_list: str | None = None
    current_scalar: str | None = None
    key_pattern = re.compile(r"^([a-z][a-z0-9_]*):(.*)$")
    for line_number, raw_line in enumerate(_decode_utf8(data, label).splitlines(), 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        match = key_pattern.fullmatch(raw_line)
        if match:
            key, raw_value = match.groups()
            if key in parsed:
                raise IntegrationError(f"{label}:{line_number}: duplicate key {key!r}")
            value = raw_value.strip()
            if key in CONTRACT_LIST_FIELDS:
                if value == "[]":
                    parsed[key] = []
                    current_list = None
                    current_scalar = None
                elif value:
                    raise IntegrationError(
                        f"{label}:{line_number}: list field {key!r} must use block syntax"
                    )
                else:
                    parsed[key] = []
                    current_list = key
                    current_scalar = None
            else:
                if not value:
                    raise IntegrationError(f"{label}:{line_number}: empty scalar {key!r}")
                parsed[key] = _yaml_scalar(value)
                current_list = None
                current_scalar = key
            continue
        list_match = re.fullmatch(r"-\s+(.+)", raw_line)
        if list_match and current_list:
            parsed[current_list].append(_yaml_scalar(list_match.group(1)))
            continue
        folded_match = re.fullmatch(r" {2}(\S.*)", raw_line)
        if folded_match and current_list and parsed[current_list]:
            parsed[current_list][-1] += " " + _yaml_scalar(folded_match.group(1))
            continue
        if folded_match and current_scalar:
            parsed[current_scalar] += " " + _yaml_scalar(folded_match.group(1))
            continue
        raise IntegrationError(f"{label}:{line_number}: unsupported YAML structure")

    if tuple(parsed) != CONTRACT_FIELDS:
        raise IntegrationError(
            f"{label}: contract fields/order differ: expected {CONTRACT_FIELDS!r}, "
            f"got {tuple(parsed)!r}"
        )
    raw_ordinal = parsed["ordinal"]
    if not isinstance(raw_ordinal, str) or not re.fullmatch(r"[1-9][0-9]*", raw_ordinal):
        raise IntegrationError(f"{label}: ordinal is not a canonical positive integer")
    parsed["ordinal"] = int(raw_ordinal)
    return parsed


def _parse_frontmatter(data: bytes, label: str) -> dict[str, str]:
    text = _decode_utf8(data, label)
    if not text.startswith("---\n"):
        raise IntegrationError(f"{label}: missing YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise IntegrationError(f"{label}: unterminated YAML frontmatter")
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        match = re.fullmatch(r"([a-z][a-z0-9-]*):\s*(\S.*)", line)
        if match is None:
            raise IntegrationError(f"{label}: malformed frontmatter")
        normalized_key, value = match.groups()
        if normalized_key in result:
            raise IntegrationError(f"{label}: duplicate frontmatter key {normalized_key!r}")
        result[normalized_key] = _yaml_scalar(value)
    if not text[end + 5 :].strip():
        raise IntegrationError(f"{label}: Skill body is empty")
    return result


def _strict_json_bytes(data: bytes, label: str) -> Any:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise IntegrationError(f"{label}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise IntegrationError(f"{label}: non-finite JSON number {value!r}")

    try:
        document = json.loads(
            _decode_utf8(data, label),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        raise IntegrationError(f"{label}: invalid JSON") from exc
    remaining = 200_000
    stack: list[tuple[Any, int]] = [(document, 0)]
    while stack:
        value, depth = stack.pop()
        remaining -= 1
        if remaining < 0 or depth > 64:
            raise IntegrationError(f"{label}: JSON is too complex")
        if isinstance(value, str):
            try:
                value.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise IntegrationError(f"{label}: invalid JSON Unicode") from exc
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise IntegrationError(f"{label}: non-finite JSON number")
        elif isinstance(value, dict):
            for key, child in value.items():
                try:
                    key.encode("utf-8", errors="strict")
                except UnicodeEncodeError as exc:
                    raise IntegrationError(f"{label}: invalid JSON Unicode") from exc
                stack.append((child, depth + 1))
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)
    return document


def _resolve_local_json_pointer(document: Any, reference: str, label: str) -> None:
    """Require one canonical, document-local JSON Pointer to resolve."""

    if reference == "#":
        return
    if not reference.startswith("#/") or "%" in reference:
        raise IntegrationError(f"{label}: non-local or non-canonical $ref {reference!r}")
    current = document
    for raw_token in reference[2:].split("/"):
        if re.search(r"~(?![01])", raw_token):
            raise IntegrationError(f"{label}: invalid JSON Pointer escape in {reference!r}")
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                raise IntegrationError(f"{label}: unresolved local $ref {reference!r}")
            current = current[token]
        elif isinstance(current, list):
            if re.fullmatch(r"0|[1-9][0-9]*", token) is None:
                raise IntegrationError(f"{label}: invalid array pointer in {reference!r}")
            index = int(token)
            if index >= len(current):
                raise IntegrationError(f"{label}: unresolved local $ref {reference!r}")
            current = current[index]
        else:
            raise IntegrationError(f"{label}: unresolved local $ref {reference!r}")


def _validate_package_schemas(schema_members: Mapping[str, bytes]) -> tuple[str, ...]:
    """Strictly validate the fixed package Schema inventory and local references."""

    observed_names = set(schema_members)
    expected_names = set(EXPECTED_SCHEMA_NAMES)
    if observed_names != expected_names or len(schema_members) != EXPECTED_SCHEMA_COUNT:
        missing = sorted(expected_names - observed_names)
        extra = sorted(observed_names - expected_names)
        raise IntegrationError(
            f"package Schema inventory drift: missing={missing}, extra={extra}"
        )
    identifiers: list[str] = []
    for name in EXPECTED_SCHEMA_NAMES:
        label = f"schemas/{name}"
        document = _strict_json_bytes(schema_members[name], label)
        if not isinstance(document, Mapping):
            raise IntegrationError(f"{label}: Schema root must be an object")
        expected_identifier = f"https://elmos.local/schemas/{name}"
        if (
            document.get("$schema") != EXPECTED_SCHEMA_DRAFT
            or document.get("$id") != expected_identifier
            or document.get("type") != "object"
            or not isinstance(document.get("title"), str)
            or not document["title"].strip()
        ):
            raise IntegrationError(f"{label}: Schema identity or root contract drifted")
        identifiers.append(expected_identifier)
        stack: list[Any] = [document]
        while stack:
            value = stack.pop()
            if isinstance(value, Mapping):
                reference = value.get("$ref")
                if reference is not None:
                    if not isinstance(reference, str):
                        raise IntegrationError(f"{label}: $ref must be a string")
                    _resolve_local_json_pointer(document, reference, label)
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
    if len(identifiers) != len(set(identifiers)):
        raise IntegrationError("package Schema identifiers are not unique")
    return tuple(identifiers)


def _parse_acceptance_matrix(
    data: bytes,
) -> tuple[tuple[Mapping[str, str], ...], dict[str, dict[str, Any]]]:
    """Parse the complete fixed acceptance-matrix grammar and reject ignored text."""

    label = "evals/acceptance-matrix.yaml"
    lines = _decode_utf8(data, label).splitlines()
    if lines[:3] != [
        "schema_version: 1.0.0",
        f"package_version: {PACKAGE_VERSION}",
        "global_gates:",
    ]:
        raise IntegrationError(f"{label}: package header drifted")
    cursor = 3
    gates: list[Mapping[str, str]] = []
    while cursor < len(lines) and lines[cursor] != "skills:":
        id_match = re.fullmatch(r"- id: (G-\d{2})", lines[cursor])
        if id_match is None or cursor + 2 >= len(lines):
            raise IntegrationError(f"{label}:{cursor + 1}: malformed global gate")
        requirement_match = re.fullmatch(r"  requirement: (\S.*)", lines[cursor + 1])
        evidence_match = re.fullmatch(r"  evidence: (\S.*)", lines[cursor + 2])
        if requirement_match is None or evidence_match is None:
            raise IntegrationError(f"{label}:{cursor + 2}: incomplete global gate")
        gate = {
            "id": id_match.group(1),
            "requirement": _yaml_scalar(requirement_match.group(1)),
            "evidence": _yaml_scalar(evidence_match.group(1)),
        }
        if any(existing["id"] == gate["id"] for existing in gates):
            raise IntegrationError(f"{label}: duplicate global gate {gate['id']!r}")
        if not gate["requirement"] or not gate["evidence"]:
            raise IntegrationError(f"{label}: empty global gate semantics")
        gates.append(gate)
        cursor += 3
    if cursor >= len(lines) or lines[cursor] != "skills:":
        raise IntegrationError(f"{label}: missing skills section")
    cursor += 1

    skills: dict[str, dict[str, Any]] = {}
    while cursor < len(lines):
        ordinal_match = re.fullmatch(r"- ordinal: ([1-9][0-9]*)", lines[cursor])
        if ordinal_match is None or cursor + 3 >= len(lines):
            raise IntegrationError(f"{label}:{cursor + 1}: malformed Skill entry")
        name_match = re.fullmatch(r"  name: (\S.*)", lines[cursor + 1])
        title_match = re.fullmatch(r"  title: (\S.*)", lines[cursor + 2])
        if (
            name_match is None
            or title_match is None
            or lines[cursor + 3] != "  acceptance:"
        ):
            raise IntegrationError(f"{label}:{cursor + 2}: incomplete Skill identity")
        name = _yaml_scalar(name_match.group(1))
        title = _yaml_scalar(title_match.group(1))
        if name in skills:
            raise IntegrationError(f"{label}: duplicate Skill {name!r}")
        record: dict[str, Any] = {
            "ordinal": int(ordinal_match.group(1)),
            "name": name,
            "title": title,
            "acceptance": [],
            "deliverables": [],
        }
        cursor += 4
        acceptance_ids: set[str] = set()
        while cursor < len(lines) and lines[cursor] != "  required_deliverables:":
            acceptance_match = re.fullmatch(r"  - id: (S\d{2}-\d{2})", lines[cursor])
            if acceptance_match is None or cursor + 1 >= len(lines):
                raise IntegrationError(f"{label}:{cursor + 1}: malformed acceptance row")
            criterion_match = re.fullmatch(r"    criterion: (\S.*)", lines[cursor + 1])
            if criterion_match is None:
                raise IntegrationError(f"{label}:{cursor + 2}: missing acceptance criterion")
            acceptance_id = acceptance_match.group(1)
            if acceptance_id in acceptance_ids:
                raise IntegrationError(f"{label}: duplicate acceptance ID {acceptance_id!r}")
            acceptance_ids.add(acceptance_id)
            record["acceptance"].append(
                {
                    "id": acceptance_id,
                    "criterion": _yaml_scalar(criterion_match.group(1)),
                }
            )
            cursor += 2
        if not record["acceptance"] or cursor >= len(lines):
            raise IntegrationError(f"{label}: empty acceptance list for {name!r}")
        cursor += 1
        while cursor < len(lines) and not lines[cursor].startswith("- ordinal: "):
            deliverable_match = re.fullmatch(r"  - (\S.*)", lines[cursor])
            if deliverable_match is None:
                raise IntegrationError(f"{label}:{cursor + 1}: malformed deliverable")
            deliverable = _yaml_scalar(deliverable_match.group(1))
            if deliverable in record["deliverables"]:
                raise IntegrationError(f"{label}: duplicate deliverable for {name!r}")
            record["deliverables"].append(deliverable)
            cursor += 1
        if not title or not record["deliverables"]:
            raise IntegrationError(f"{label}: incomplete semantics for {name!r}")
        skills[name] = record
    return tuple(gates), skills


def _safe_archive_name(name: str) -> PurePosixPath:
    if not name or "\x00" in name or "\\" in name:
        raise IntegrationError(
            f"unsafe archive member name: {name!r}",
            code="MULTIMODAL_ARCHIVE_MEMBER_UNSAFE",
        )
    try:
        encoded_name = name.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise IntegrationError(
            f"invalid Unicode in archive member: {name!r}",
            code="MULTIMODAL_ARCHIVE_MEMBER_UNSAFE",
        ) from exc
    if len(encoded_name) > MAX_ARCHIVE_PATH_BYTES:
        raise IntegrationError(
            f"archive member path exceeds its byte bound: {name!r}",
            code="MULTIMODAL_ARCHIVE_MEMBER_UNSAFE",
        )
    if any(
        ord(character) == 127
        or unicodedata.category(character) in {"Cc", "Cs"}
        for character in name
    ):
        raise IntegrationError(
            f"control character in archive member: {name!r}",
            code="MULTIMODAL_ARCHIVE_MEMBER_UNSAFE",
        )
    path = PurePosixPath(name)
    if path.as_posix() != name or unicodedata.normalize("NFC", name) != name:
        raise IntegrationError(
            f"non-canonical archive member path: {name!r}",
            code="MULTIMODAL_ARCHIVE_MEMBER_UNSAFE",
        )
    if path.is_absolute() or not path.parts or path.parts[0] != ARCHIVE_ROOT:
        raise IntegrationError(
            f"archive member escapes expected root: {name!r}",
            code="MULTIMODAL_ARCHIVE_MEMBER_UNSAFE",
        )
    if any(part in {"", ".", ".."} for part in path.parts):
        raise IntegrationError(
            f"ambiguous archive member path: {name!r}",
            code="MULTIMODAL_ARCHIVE_MEMBER_UNSAFE",
        )
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        f"{prefix}{number}"
        for prefix in ("COM", "LPT")
        for number in range(1, 10)
    }
    for part in path.parts:
        if len(part.encode("utf-8")) > MAX_ARCHIVE_COMPONENT_BYTES:
            raise IntegrationError(
                f"archive member component exceeds its byte bound: {name!r}",
                code="MULTIMODAL_ARCHIVE_MEMBER_UNSAFE",
            )
        if ":" in part or part.endswith((" ", ".")):
            raise IntegrationError(
                f"drive-like archive member path: {name!r}",
                code="MULTIMODAL_ARCHIVE_MEMBER_UNSAFE",
            )
        if part.split(".", 1)[0].upper() in reserved:
            raise IntegrationError(
                f"reserved archive member path: {name!r}",
                code="MULTIMODAL_ARCHIVE_MEMBER_UNSAFE",
            )
    return path


def _validate_central_directory(
    archive: zipfile.ZipFile,
    *,
    expected_entries: int | None = EXPECTED_ENTRY_COUNT,
    expected_uncompressed_bytes: int | None = EXPECTED_UNCOMPRESSED_BYTES,
) -> tuple[zipfile.ZipInfo, ...]:
    infos = tuple(archive.infolist())
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise IntegrationError(
            f"archive member count exceeds its safety bound: {len(infos)}",
            code="MULTIMODAL_ARCHIVE_MEMBER_UNSAFE",
        )
    if expected_entries is not None and len(infos) != expected_entries:
        raise IntegrationError(
            f"archive entry count mismatch: expected {expected_entries}, got {len(infos)}"
        )
    names: set[str] = set()
    normalized_names: set[str] = set()
    total = 0
    total_compressed = 0
    for info in infos:
        path = _safe_archive_name(info.filename)
        if info.filename in names:
            raise IntegrationError(f"duplicate archive member: {info.filename!r}")
        names.add(info.filename)
        collision_key = unicodedata.normalize("NFKC", path.as_posix()).casefold()
        if collision_key in normalized_names:
            raise IntegrationError(
                f"case/Unicode archive path collision: {info.filename!r}",
                code="MULTIMODAL_ARCHIVE_MEMBER_UNSAFE",
            )
        normalized_names.add(collision_key)
        if info.flag_bits & (0x1 | 0x40):
            raise IntegrationError(
                f"encrypted archive entry: {info.filename!r}",
                code="MULTIMODAL_ARCHIVE_MEMBER_UNSAFE",
            )
        if info.is_dir():
            raise IntegrationError(f"unexpected directory entry: {info.filename!r}")
        if info.create_system != 3:
            raise IntegrationError(f"archive entry lacks pinned Unix mode: {info.filename!r}")
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(unix_mode)
        if file_type not in (0, stat.S_IFREG):
            raise IntegrationError(f"link or special archive entry: {info.filename!r}")
        relative_name = path.relative_to(ARCHIVE_ROOT).as_posix()
        expected_mode = 0o755 if relative_name in EXPECTED_EXECUTABLE_MEMBERS else 0o644
        observed_mode = stat.S_IMODE(unix_mode)
        if observed_mode != expected_mode:
            raise IntegrationError(
                f"archive mode mismatch for {info.filename!r}: "
                f"expected {expected_mode:o}, got {observed_mode:o}"
            )
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise IntegrationError(f"unsupported compression method: {info.filename!r}")
        if info.file_size < 0 or info.compress_size < 0:
            raise IntegrationError(f"negative archive size: {info.filename!r}")
        if type(info.CRC) is not int or not 0 <= info.CRC <= 0xFFFFFFFF:
            raise IntegrationError(
                f"archive entry has an invalid CRC: {info.filename!r}",
                code="MULTIMODAL_ARCHIVE_INTEGRITY_INVALID",
            )
        if info.file_size > MAX_ARCHIVE_ENTRY_BYTES:
            raise IntegrationError(f"archive entry exceeds byte bound: {info.filename!r}")
        if info.file_size and info.compress_size == 0:
            raise IntegrationError(f"archive entry has unbounded compression ratio: {info.filename!r}")
        if info.file_size / max(1, info.compress_size) > MAX_ARCHIVE_COMPRESSION_RATIO:
            raise IntegrationError(f"archive entry compression ratio is unsafe: {info.filename!r}")
        total += info.file_size
        total_compressed += info.compress_size
        if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise IntegrationError("archive exceeds total uncompressed-byte safety bound")
    if total and total / max(1, total_compressed) > MAX_ARCHIVE_COMPRESSION_RATIO:
        raise IntegrationError(
            "archive total compression ratio is unsafe",
            code="MULTIMODAL_ARCHIVE_MEMBER_UNSAFE",
        )
    if expected_uncompressed_bytes is not None and total != expected_uncompressed_bytes:
        raise IntegrationError(
            "archive uncompressed-byte mismatch: "
            f"expected {expected_uncompressed_bytes}, got {total}"
        )
    return infos


def _member_digest(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    crc32 = 0
    observed = 0
    try:
        with archive.open(info, "r") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                observed += len(chunk)
                if observed > info.file_size:
                    raise IntegrationError(
                        f"member expands beyond declared size: {info.filename!r}",
                        code="MULTIMODAL_ARCHIVE_INTEGRITY_INVALID",
                    )
                digest.update(chunk)
                crc32 = zlib.crc32(chunk, crc32)
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise IntegrationError(
            f"archive member CRC/read failure: {info.filename!r}",
            code="MULTIMODAL_ARCHIVE_INTEGRITY_INVALID",
        ) from exc
    if observed != info.file_size:
        raise IntegrationError(
            f"member byte count mismatch for {info.filename!r}: {observed} != {info.file_size}",
            code="MULTIMODAL_ARCHIVE_INTEGRITY_INVALID",
        )
    if crc32 & 0xFFFFFFFF != info.CRC:
        raise IntegrationError(
            f"archive member CRC mismatch: {info.filename!r}",
            code="MULTIMODAL_ARCHIVE_INTEGRITY_INVALID",
        )
    return digest.hexdigest()


def _verify_internal_checksums(
    archive: zipfile.ZipFile,
    infos: Sequence[zipfile.ZipInfo],
) -> tuple[dict[str, str], dict[str, int], dict[str, int]]:
    by_name = {info.filename: info for info in infos}
    checksum_member = f"{ARCHIVE_ROOT}/CHECKSUMS.sha256"
    if checksum_member not in by_name:
        raise IntegrationError("archive is missing CHECKSUMS.sha256")
    try:
        checksum_bytes = archive.read(checksum_member)
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise IntegrationError(
            "archive checksum member failed CRC/read validation",
            code="MULTIMODAL_ARCHIVE_INTEGRITY_INVALID",
        ) from exc
    checksum_text = _decode_utf8(checksum_bytes, checksum_member)
    rows: dict[str, str] = {}
    pattern = re.compile(r"^([0-9a-f]{64})  (.+)$")
    for line_number, line in enumerate(checksum_text.splitlines(), 1):
        match = pattern.fullmatch(line)
        if not match:
            raise IntegrationError(f"CHECKSUMS.sha256:{line_number}: malformed row")
        expected_digest, relative_name = match.groups()
        relative_path = PurePosixPath(relative_name)
        if relative_path.is_absolute() or any(
            part in {"", ".", ".."} for part in relative_path.parts
        ):
            raise IntegrationError(
                f"CHECKSUMS.sha256:{line_number}: unsafe relative path"
            )
        if relative_name in rows:
            raise IntegrationError(f"CHECKSUMS.sha256: duplicate row {relative_name!r}")
        rows[relative_name] = expected_digest
    if len(rows) != EXPECTED_INTERNAL_CHECKSUMS:
        raise IntegrationError(
            "internal checksum count mismatch: "
            f"expected {EXPECTED_INTERNAL_CHECKSUMS}, got {len(rows)}"
        )
    expected_names = {
        info.filename.removeprefix(f"{ARCHIVE_ROOT}/")
        for info in infos
        if info.filename != checksum_member
    }
    if set(rows) != expected_names:
        missing = sorted(expected_names - set(rows))
        extra = sorted(set(rows) - expected_names)
        raise IntegrationError(
            f"internal checksum coverage mismatch: missing={missing}, extra={extra}"
        )

    member_sha256: dict[str, str] = {}
    member_size: dict[str, int] = {}
    member_mode: dict[str, int] = {}
    for info in infos:
        relative_name = info.filename.removeprefix(f"{ARCHIVE_ROOT}/")
        observed_digest = _member_digest(archive, info)
        member_sha256[relative_name] = observed_digest
        member_size[relative_name] = info.file_size
        member_mode[relative_name] = stat.S_IMODE((info.external_attr >> 16) & 0xFFFF)
        if relative_name != "CHECKSUMS.sha256" and rows[relative_name] != observed_digest:
            raise IntegrationError(f"internal checksum mismatch: {relative_name}")
    return member_sha256, member_size, member_mode


def _members_below(
    archive: zipfile.ZipFile,
    infos: Sequence[zipfile.ZipInfo],
    prefix: str,
) -> dict[str, bytes]:
    normalized_prefix = f"{ARCHIVE_ROOT}/{prefix.rstrip('/')}/"
    return {
        info.filename.removeprefix(normalized_prefix): archive.read(info)
        for info in infos
        if info.filename.startswith(normalized_prefix)
    }


def _dependency_sccs(dependencies: Mapping[str, Sequence[str]]) -> tuple[tuple[str, ...], ...]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for dependency in dependencies[node]:
            if dependency not in indices:
                visit(dependency)
                lowlinks[node] = min(lowlinks[node], lowlinks[dependency])
            elif dependency in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[dependency])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        components.append(tuple(sorted(component)))

    for name in sorted(dependencies):
        if name not in indices:
            visit(name)
    cyclic = [
        component
        for component in components
        if len(component) > 1
        or (len(component) == 1 and component[0] in dependencies[component[0]])
    ]
    return tuple(sorted(cyclic))


def validate_archive(archive_path: Path) -> PackageSnapshot:
    archive_bytes, archive_digest = _read_pinned_archive(archive_path)
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes), "r")
    except zipfile.BadZipFile as exc:
        raise IntegrationError("pinned archive is not a valid ZIP") from exc

    with archive:
        infos = _validate_central_directory(archive)
        member_sha256, member_size, member_mode = _verify_internal_checksums(archive, infos)

        canonical = _members_below(archive, infos, "skills")
        codex_mirror = _members_below(archive, infos, ".agents/skills")
        claude_mirror = _members_below(archive, infos, ".claude/skills")
        if canonical != codex_mirror or canonical != claude_mirror:
            raise IntegrationError("canonical, Codex, and Claude Skill trees are not byte-identical")
        _validate_package_schemas(_members_below(archive, infos, "schemas"))

        skill_names = sorted({name.split("/", 1)[0] for name in canonical})
        if len(skill_names) != EXPECTED_SKILL_COUNT:
            raise IntegrationError(
                f"canonical Skill count mismatch: {len(skill_names)} != {EXPECTED_SKILL_COUNT}"
            )
        for name in skill_names:
            expected_files = {
                f"{name}/SKILL.md",
                f"{name}/references/contract.yaml",
            }
            observed_files = {path for path in canonical if path.startswith(f"{name}/")}
            if observed_files != expected_files:
                raise IntegrationError(
                    f"{name}: unexpected Skill payload files: {sorted(observed_files)}"
                )

        acceptance_member = f"{ARCHIVE_ROOT}/evals/acceptance-matrix.yaml"
        global_gates, acceptance_by_skill = _parse_acceptance_matrix(
            archive.read(acceptance_member)
        )
        global_gate_ids = tuple(gate["id"] for gate in global_gates)
        if global_gate_ids != EXPECTED_GLOBAL_GATE_IDS:
            raise IntegrationError(
                f"global gate IDs differ: {global_gate_ids!r} != {EXPECTED_GLOBAL_GATE_IDS!r}"
            )
        if len(global_gate_ids) != EXPECTED_GLOBAL_GATE_COUNT:
            raise IntegrationError("global gate count mismatch")

        manifest_member = f"{ARCHIVE_ROOT}/manifest.json"
        manifest_bytes = archive.read(manifest_member)
        manifest = _strict_json_bytes(manifest_bytes, manifest_member)
        if not isinstance(manifest, Mapping):
            raise IntegrationError("manifest.json root must be an object")
        if tuple(manifest) != (
            "schema_version",
            "package",
            "compatibility",
            "supported_inputs",
            "invariants",
            "skills",
        ):
            raise IntegrationError("manifest.json fields or ordering drifted")
        package = manifest.get("package")
        if not isinstance(package, Mapping) or tuple(package) != (
            "name", "version", "title", "description", "language", "generated_at", "license"
        ):
            raise IntegrationError("manifest package semantics drifted")
        if (
            package.get("name") != PACKAGE_NAME
            or package.get("version") != PACKAGE_VERSION
            or package.get("language") != "zh-CN"
            or package.get("generated_at") != "2026-08-19"
            or package.get("license")
            != "Proprietary project specification; adapt to your repository policy"
            or not isinstance(package.get("title"), str)
            or not package.get("title")
            or not isinstance(package.get("description"), str)
            or not package.get("description")
        ):
            raise IntegrationError("manifest package identity drifted")
        compatibility = manifest.get("compatibility")
        expected_compatibility = {
            "canonical_skill_root": "skills",
            "codex_repo_skill_root": ".agents/skills",
            "claude_code_repo_skill_root": ".claude/skills",
            "skill_contract": "SKILL.md with YAML frontmatter name and description",
            "context_baseline": {
                "as_of": "2026-08-19",
                "parity_target": "Codex",
                "context_window_tokens": 1_050_000,
                "max_output_tokens": 128_000,
                "hardcoded_in_business_logic": False,
                "source_of_truth": "model capability registry",
            },
        }
        if compatibility != expected_compatibility:
            raise IntegrationError("manifest compatibility semantics drifted")
        supported_inputs = manifest.get("supported_inputs")
        if not isinstance(supported_inputs, Mapping) or {
            key: tuple(value) if isinstance(value, list) else value
            for key, value in supported_inputs.items()
        } != EXPECTED_SUPPORTED_INPUTS:
            raise IntegrationError("manifest supported-input semantics drifted")
        if tuple(manifest.get("invariants") or ()) != EXPECTED_PACKAGE_INVARIANTS:
            raise IntegrationError("manifest package invariants drifted")
        manifest_skills = manifest.get("skills")
        if not isinstance(manifest_skills, list) or len(manifest_skills) != EXPECTED_SKILL_COUNT:
            raise IntegrationError("manifest.json does not contain exactly 50 Skills")
        manifest_by_name: dict[str, Mapping[str, Any]] = {}
        for item in manifest_skills:
            if not isinstance(item, Mapping) or tuple(item) != (
                "ordinal", "name", "title", "dependencies", "path"
            ):
                raise IntegrationError("manifest Skill record shape drifted")
            item_name = item.get("name")
            if not isinstance(item_name, str) or item_name in manifest_by_name:
                raise IntegrationError("manifest contains an invalid or duplicate Skill name")
            manifest_by_name[item_name] = item
        if set(manifest_by_name) != set(skill_names):
            raise IntegrationError("manifest Skill names differ from canonical directories")

        contracts: list[SkillContract] = []
        dependencies: dict[str, tuple[str, ...]] = {}
        ordinals: set[int] = set()
        total_acceptance = 0
        total_deliverables = 0
        for name in skill_names:
            if (
                len(name.encode("utf-8")) > 64
                or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is None
            ):
                raise IntegrationError(f"invalid Codex Skill name: {name!r}")
            skill_rel = f"skills/{name}/SKILL.md"
            contract_rel = f"skills/{name}/references/contract.yaml"
            skill_data = archive.read(f"{ARCHIVE_ROOT}/{skill_rel}")
            contract_data = archive.read(f"{ARCHIVE_ROOT}/{contract_rel}")
            frontmatter = _parse_frontmatter(skill_data, skill_rel)
            contract = _parse_contract(contract_data, contract_rel)
            if (
                set(frontmatter) != {"name", "description"}
                or frontmatter.get("name") != name
                or not frontmatter.get("description")
            ):
                raise IntegrationError(f"{name}: invalid Skill frontmatter")
            description = frontmatter["description"]
            if len(description) > 1024 or "<" in description or ">" in description:
                raise IntegrationError(f"{name}: frontmatter description violates Codex contract")
            if contract["schema_version"] != "1.0.0" or contract["name"] != name:
                raise IntegrationError(f"{name}: contract identity mismatch")
            for field in CONTRACT_FIELDS[3:5]:
                if not isinstance(contract[field], str) or not contract[field].strip():
                    raise IntegrationError(f"{name}: empty contract field {field!r}")
            for field in CONTRACT_LIST_FIELDS:
                values = contract[field]
                if (
                    not isinstance(values, list)
                    or any(not isinstance(value, str) or not value.strip() for value in values)
                    or len(values) != len(set(values))
                ):
                    raise IntegrationError(f"{name}: invalid contract list {field!r}")
            if tuple(contract["cross_cutting_invariants"]) != EXPECTED_INVARIANTS:
                raise IntegrationError(f"{name}: cross-cutting invariants drifted")
            ordinal = contract["ordinal"]
            if ordinal in ordinals:
                raise IntegrationError(f"duplicate Skill ordinal: {ordinal}")
            ordinals.add(ordinal)
            expected_acceptance = 4 if ordinal <= 30 else 6
            expected_deliverables = 3 if ordinal <= 30 else 4
            if len(contract["acceptance"]) != expected_acceptance:
                raise IntegrationError(f"{name}: acceptance count drifted")
            if len(contract["deliverables"]) != expected_deliverables:
                raise IntegrationError(f"{name}: deliverable count drifted")
            matrix_record = acceptance_by_skill.get(name)
            if (
                matrix_record is None
                or matrix_record["ordinal"] != ordinal
                or matrix_record["title"] != contract["title"]
            ):
                raise IntegrationError(f"{name}: acceptance matrix identity mismatch")
            acceptance_ids = tuple(item["id"] for item in matrix_record["acceptance"])
            expected_ids = tuple(
                f"S{ordinal:02d}-{index:02d}"
                for index in range(1, expected_acceptance + 1)
            )
            if acceptance_ids != expected_ids:
                raise IntegrationError(f"{name}: acceptance IDs drifted")
            matrix_criteria = tuple(item["criterion"] for item in matrix_record["acceptance"])
            if matrix_criteria != tuple(contract["acceptance"]):
                raise IntegrationError(f"{name}: acceptance criteria differ from contract")
            if tuple(matrix_record["deliverables"]) != tuple(contract["deliverables"]):
                raise IntegrationError(f"{name}: deliverables differ from contract")
            manifest_item = manifest_by_name[name]
            dependency_tuple = tuple(contract["dependencies"])
            if (
                manifest_item.get("ordinal") != ordinal
                or manifest_item.get("title") != contract["title"]
                or tuple(manifest_item.get("dependencies") or ()) != dependency_tuple
                or manifest_item.get("path") != f"skills/{name}/SKILL.md"
            ):
                raise IntegrationError(f"{name}: manifest and contract differ")
            total_acceptance += len(acceptance_ids)
            total_deliverables += len(contract["deliverables"])
            dependencies[name] = dependency_tuple
            contracts.append(
                SkillContract(
                    ordinal=ordinal,
                    name=name,
                    title=str(contract["title"]),
                    dependencies=dependency_tuple,
                    acceptance=matrix_criteria,
                    acceptance_ids=acceptance_ids,
                    deliverables=tuple(contract["deliverables"]),
                    contract_sha256=_sha256(contract_data),
                    skill_md_sha256=_sha256(skill_data),
                    handler_id=_handler_id(name),
                    description=description,
                    contract=contract,
                    contract_yaml=contract_data,
                    skill_md=skill_data,
                )
            )

        if ordinals != set(range(1, EXPECTED_SKILL_COUNT + 1)):
            raise IntegrationError("Skill ordinals are not exactly 1..50")
        if set(acceptance_by_skill) != set(skill_names):
            raise IntegrationError("acceptance matrix contains missing or extra Skills")
        if total_acceptance != EXPECTED_ACCEPTANCE_COUNT:
            raise IntegrationError(f"acceptance total mismatch: {total_acceptance}")
        if total_deliverables != EXPECTED_DELIVERABLE_COUNT:
            raise IntegrationError(f"deliverable total mismatch: {total_deliverables}")
        unknown_dependencies = {
            dependency
            for values in dependencies.values()
            for dependency in values
            if dependency not in dependencies
        }
        if unknown_dependencies:
            raise IntegrationError(f"unknown dependencies: {sorted(unknown_dependencies)}")
        edge_count = sum(len(values) for values in dependencies.values())
        if edge_count != EXPECTED_DEPENDENCY_EDGES:
            raise IntegrationError(f"dependency edge count mismatch: {edge_count}")
        roots = [name for name, values in dependencies.items() if not values]
        if len(roots) != EXPECTED_ROOT_SKILLS:
            raise IntegrationError(f"dependency root count mismatch: {len(roots)}")
        dependency_sccs = _dependency_sccs(dependencies)
        if dependency_sccs != tuple(sorted(EXPECTED_CYCLIC_SCCS)):
            raise IntegrationError(f"dependency SCCs drifted: {dependency_sccs!r}")

    return PackageSnapshot(
        archive_bytes=archive_bytes,
        archive_sha256=archive_digest,
        entry_count=len(infos),
        uncompressed_bytes=sum(info.file_size for info in infos),
        internal_checksum_count=EXPECTED_INTERNAL_CHECKSUMS,
        member_sha256=member_sha256,
        member_size=member_size,
        member_mode=member_mode,
        skills=tuple(sorted(contracts, key=lambda item: item.ordinal)),
        global_gate_ids=global_gate_ids,
        global_gates=global_gates,
        dependency_sccs=dependency_sccs,
        manifest_sha256=_sha256(manifest_bytes),
    )


def _resolve_below(repo_root: Path, relative: Path) -> Path:
    root = repo_root.resolve()
    if not root.is_dir():
        raise IntegrationError(f"repository root is not a directory: {root}")
    if relative.is_absolute() or any(part == ".." for part in relative.parts):
        raise IntegrationError(f"path escapes repository root: {relative}")
    candidate = root / relative
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if _lexists(cursor) and cursor.is_symlink():
            raise IntegrationError(f"managed path traverses a symlink: {cursor}")
    return candidate


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _assert_regular_tree(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise IntegrationError(f"expected a real directory: {root}")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise IntegrationError(f"symlink is not allowed in managed tree: {path}")
        if not path.is_dir() and not path.is_file():
            raise IntegrationError(f"special file is not allowed in managed tree: {path}")


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _update_tree_digest(
    digest: Any,
    kind: str,
    relative: str,
    mode: int,
    size: int = 0,
    content_sha256: str = "",
) -> None:
    record = f"{kind}\0{relative}\0{mode:04o}\0{size}\0{content_sha256}\n"
    digest.update(record.encode("utf-8"))


def _tree_digest(root: Path) -> str:
    _assert_regular_tree(root)
    digest = hashlib.sha256()
    _update_tree_digest(digest, "D", ".", _mode(root))
    paths = tuple(root.rglob("*"))
    for path in sorted(
        (value for value in paths if value.is_dir()),
        key=lambda value: value.relative_to(root).as_posix(),
    ):
        relative = path.relative_to(root).as_posix()
        _update_tree_digest(digest, "D", relative, _mode(path))
    for path in sorted(
        (value for value in paths if value.is_file()),
        key=lambda value: value.relative_to(root).as_posix(),
    ):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        _update_tree_digest(
            digest,
            "F",
            relative,
            stat.S_IMODE(metadata.st_mode),
            metadata.st_size,
            _digest_file(path),
        )
    return digest.hexdigest()


def _payload_directories(payloads: Mapping[str, FilePayload]) -> set[str]:
    directories: set[str] = set()
    for relative in payloads:
        parent = PurePosixPath(relative).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _payload_tree_digest(payloads: Mapping[str, FilePayload]) -> str:
    digest = hashlib.sha256()
    _update_tree_digest(digest, "D", ".", 0o755)
    for relative in sorted(_payload_directories(payloads)):
        _update_tree_digest(digest, "D", relative, 0o755)
    for relative in sorted(payloads):
        payload = payloads[relative]
        _update_tree_digest(
            digest,
            "F",
            relative,
            payload.mode,
            len(payload.data),
            _sha256(payload.data),
        )
    return digest.hexdigest()


def _assert_tree_matches(
    root: Path,
    payloads: Mapping[str, FilePayload],
    label: str,
) -> None:
    _assert_regular_tree(root)
    observed_files = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
    }
    observed_directories = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_dir()
    }
    expected_files = set(payloads)
    expected_directories = _payload_directories(payloads)
    if set(observed_files) != expected_files:
        missing = sorted(expected_files - set(observed_files))
        extra = sorted(set(observed_files) - expected_files)
        raise IntegrationError(f"{label} drift: missing={missing}, extra={extra}")
    if observed_directories != expected_directories:
        missing = sorted(expected_directories - observed_directories)
        extra = sorted(observed_directories - expected_directories)
        raise IntegrationError(f"{label} directory drift: missing={missing}, extra={extra}")
    if _mode(root) != 0o755:
        raise IntegrationError(f"{label} root mode drift: {_mode(root):o}")
    for relative in expected_directories:
        if _mode(root / relative) != 0o755:
            raise IntegrationError(f"{label} directory mode drift: {relative}")
    for relative, payload in payloads.items():
        path = observed_files[relative]
        metadata = path.lstat()
        if stat.S_IMODE(metadata.st_mode) != payload.mode:
            raise IntegrationError(f"{label} mode drift: {relative}")
        if metadata.st_size != len(payload.data) or _digest_file(path) != _sha256(payload.data):
            raise IntegrationError(f"{label} content drift: {relative}")
    if _tree_digest(root) != _payload_tree_digest(payloads):
        raise IntegrationError(f"{label} aggregate tree drift")


def _source_payloads(snapshot: PackageSnapshot) -> dict[str, FilePayload]:
    payloads: dict[str, FilePayload] = {}
    with zipfile.ZipFile(io.BytesIO(snapshot.archive_bytes), "r") as archive:
        infos = _validate_central_directory(archive)
        for info in infos:
            relative = PurePosixPath(info.filename).relative_to(ARCHIVE_ROOT).as_posix()
            data = archive.read(info)
            if len(data) != snapshot.member_size[relative] or _sha256(data) != snapshot.member_sha256[relative]:
                raise IntegrationError(f"archive payload changed after validation: {relative}")
            payloads[relative] = FilePayload(data=data, mode=snapshot.member_mode[relative])
    return payloads


def _assert_source_matches(snapshot: PackageSnapshot, source_root: Path) -> None:
    _assert_tree_matches(source_root, _source_payloads(snapshot), "immutable source")


def _write_payload_file(path: Path, payload: FilePayload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, payload.mode)
    try:
        os.fchmod(descriptor, payload.mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload.data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _write_payload_tree(root: Path, payloads: Mapping[str, FilePayload]) -> None:
    if root.exists() or root.is_symlink():
        raise IntegrationError(f"staging path already exists: {root}")
    root.mkdir(mode=0o755)
    os.chmod(root, 0o755)
    for relative in sorted(_payload_directories(payloads), key=lambda item: (item.count("/"), item)):
        directory = root / relative
        directory.mkdir(exist_ok=True, mode=0o755)
        os.chmod(directory, 0o755)
    for relative in sorted(payloads):
        _write_payload_file(root / relative, payloads[relative])
    _assert_tree_matches(root, payloads, f"staged tree {root.name}")


def _runtime_record(repo_root: Path, relative: str) -> Mapping[str, Any]:
    path = _resolve_below(repo_root, Path(relative))
    if path.is_symlink() or not path.is_file():
        raise IntegrationError(f"runtime inventory file is missing or unsafe: {relative}")
    data = _read_bounded_regular_file(path, MAX_RUNTIME_FILE_BYTES, "runtime inventory file")
    metadata = path.lstat()
    mode = stat.S_IMODE(metadata.st_mode)
    if metadata.st_size != len(data):
        raise IntegrationError(f"runtime inventory file changed after read: {relative}")
    if mode != 0o644:
        raise IntegrationError(f"runtime inventory mode drift for {relative}: {mode:o}")
    return {
        "path": relative,
        "bytes": len(data),
        "mode": f"{mode:04o}",
        "sha256": _sha256(data),
    }


def _validate_owned_surface_inventory(repo_root: Path) -> None:
    """Discover every owned multimodal surface and reject undeclared files."""

    repository = repo_root.resolve()
    observed: set[str] = set()
    for relative_root in OWNED_SURFACE_ROOTS:
        root = _resolve_below(repository, relative_root)
        _assert_regular_tree(root)
        observed.update(
            path.relative_to(repository).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        )
    for relative in OWNED_SURFACE_EXACT_FILES:
        path = _resolve_below(repository, relative)
        if path.is_symlink() or not path.is_file():
            raise IntegrationError(f"owned multimodal surface is missing or unsafe: {relative}")
        observed.add(relative.as_posix())
    expected = set(SURFACE_IMPLEMENTATION_FILES) | set(REPOSITORY_TEST_FILES)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise IntegrationError(
            f"owned multimodal surface inventory drift: missing={missing}, extra={extra}"
        )


def _runtime_snapshot(repo_root: Path) -> RuntimeSnapshot:
    engine_root = _resolve_below(repo_root, ENGINE_ROOT_RELATIVE_PATH)
    _assert_regular_tree(engine_root)
    observed: set[str] = set()
    unexpected_ephemeral: list[str] = []
    for path in engine_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(engine_root)
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            unexpected_ephemeral.append(relative.as_posix())
            continue
        observed.add(relative.as_posix())
    expected = set(ENGINE_IMPLEMENTATION_FILES) | set(ENGINE_TEST_FILES)
    if observed != expected or unexpected_ephemeral:
        missing = sorted(expected - observed)
        extra = sorted((observed - expected) | set(unexpected_ephemeral))
        raise IntegrationError(f"runtime file inventory drift: missing={missing}, extra={extra}")
    _validate_owned_surface_inventory(repo_root)
    for source_relative, packaged_relative in PACKAGED_MIGRATION_PAIRS:
        source = _read_bounded_regular_file(
            _resolve_below(engine_root, Path(source_relative)),
            MAX_RUNTIME_FILE_BYTES,
            "source migration",
        )
        packaged = _read_bounded_regular_file(
            _resolve_below(engine_root, Path(packaged_relative)),
            MAX_RUNTIME_FILE_BYTES,
            "packaged migration",
        )
        if not hmac.compare_digest(source, packaged):
            raise IntegrationError(
                f"packaged migration drift: {source_relative} != {packaged_relative}"
            )
    for source_relative, packaged_relative in PACKAGED_RUNTIME_FILE_PAIRS:
        source = _read_bounded_regular_file(
            _resolve_below(engine_root, Path(source_relative)),
            MAX_RUNTIME_FILE_BYTES,
            "source runtime mirror",
        )
        packaged = _read_bounded_regular_file(
            _resolve_below(engine_root, Path(packaged_relative)),
            MAX_RUNTIME_FILE_BYTES,
            "packaged runtime mirror",
        )
        if not hmac.compare_digest(source, packaged):
            raise IntegrationError(
                f"packaged runtime file drift: {source_relative} != {packaged_relative}"
            )
    _validate_openapi_operation_input_schema_reference(engine_root)
    for contract_name, marker_map in (
        ("human-review", HUMAN_REVIEW_RUNTIME_CONTRACT_MARKERS),
        ("governance-deletion", GOVERNANCE_DELETION_RUNTIME_CONTRACT_MARKERS),
        ("skill26-operation-registry", SKILL26_OPERATION_REGISTRY_MARKERS),
        ("project-package-lifecycle", PROJECT_PACKAGE_LIFECYCLE_MARKERS),
        ("acceptance-evaluation", ACCEPTANCE_EVALUATION_RUNTIME_CONTRACT_MARKERS),
        ("content-projection", CONTENT_PROJECTION_RUNTIME_CONTRACT_MARKERS),
        ("telemetry-lifecycle", TELEMETRY_LIFECYCLE_RUNTIME_CONTRACT_MARKERS),
        ("downstream-agent", DOWNSTREAM_AGENT_RUNTIME_CONTRACT_MARKERS),
        (
            "processing-job-cancellation",
            PROCESSING_JOB_CANCELLATION_RUNTIME_CONTRACT_MARKERS,
        ),
        (
            "core-outbox-delivery-receipt",
            CORE_OUTBOX_DELIVERY_RECEIPT_RUNTIME_CONTRACT_MARKERS,
        ),
        (
            "operation-input-schema",
            OPERATION_INPUT_SCHEMA_RUNTIME_CONTRACT_MARKERS,
        ),
        (
            "sdk-compilation-tool",
            SDK_COMPILATION_TOOL_RUNTIME_CONTRACT_MARKERS,
        ),
    ):
        for relative, markers in marker_map.items():
            text = _decode_utf8(
                _read_bounded_regular_file(
                    _resolve_below(engine_root, Path(relative)),
                    MAX_RUNTIME_FILE_BYTES,
                    f"{contract_name} runtime contract",
                ),
                f"{contract_name} runtime contract {relative}",
            )
            missing_markers = [marker for marker in markers if marker not in text]
            if missing_markers:
                raise IntegrationError(
                    f"{contract_name} runtime contract drift in {relative}: "
                    f"missing={missing_markers}"
                )
    engine_implementation = tuple(
        (ENGINE_ROOT_RELATIVE_PATH / relative).as_posix()
        for relative in ENGINE_IMPLEMENTATION_FILES
    )
    engine_tests = tuple(
        (ENGINE_ROOT_RELATIVE_PATH / relative).as_posix()
        for relative in ENGINE_TEST_FILES
    )
    implementation = tuple(
        _runtime_record(repo_root, relative)
        for relative in (*engine_implementation, *SURFACE_IMPLEMENTATION_FILES)
    )
    tests = tuple(
        _runtime_record(repo_root, relative)
        for relative in (*engine_tests, *REPOSITORY_TEST_FILES)
    )
    return RuntimeSnapshot(
        implementation_files=implementation,
        test_files=tests,
        implementation_sha256=_sha256(_json_bytes(list(implementation))),
        tests_sha256=_sha256(_json_bytes(list(tests))),
    )


def _assignment_target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Starred):
        return _assignment_target_names(target.value)
    if isinstance(target, (ast.Tuple, ast.List)):
        return {
            name
            for element in target.elts
            for name in _assignment_target_names(element)
        }
    return set()


def _attribute_root_name(node: ast.Attribute) -> str | None:
    value: ast.AST = node
    while isinstance(value, ast.Attribute):
        value = value.value
    return value.id if isinstance(value, ast.Name) else None


def _bound_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Assign):
        return {
            name
            for target in node.targets
            for name in _assignment_target_names(target)
        }
    if isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
        return _assignment_target_names(node.target)
    if isinstance(node, ast.Delete):
        return {
            name
            for target in node.targets
            for name in _assignment_target_names(target)
        }
    if isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
        return _assignment_target_names(node.target)
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return {
            name
            for item in node.items
            if item.optional_vars is not None
            for name in _assignment_target_names(item.optional_vars)
        }
    if isinstance(node, ast.ExceptHandler):
        return {node.name} if isinstance(node.name, str) else set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, ast.Import):
        return {alias.asname or alias.name.split(".", 1)[0] for alias in node.names}
    if isinstance(node, ast.ImportFrom):
        return {
            alias.asname or alias.name
            for alias in node.names
            if alias.name != "*"
        }
    if isinstance(node, ast.MatchAs):
        return {node.name} if node.name is not None else set()
    if isinstance(node, ast.MatchStar):
        return {node.name} if node.name is not None else set()
    if isinstance(node, ast.MatchMapping):
        return {node.rest} if node.rest is not None else set()
    type_alias = getattr(ast, "TypeAlias", None)
    if type_alias is not None and isinstance(node, type_alias):
        return _assignment_target_names(node.name)
    return set()


def _static_operation_value(
    node: ast.AST,
    environment: Mapping[str, Any],
    label: str,
) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in environment:
        return environment[node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(
            _static_operation_value(item, environment, label) for item in node.elts
        )
    if isinstance(node, ast.IfExp):
        branch = (
            node.body
            if _static_operation_condition(node.test, environment, label)
            else node.orelse
        )
        return _static_operation_value(branch, environment, label)
    raise IntegrationError(f"{label}: unsupported static operation expression")


def _static_operation_condition(
    node: ast.AST,
    environment: Mapping[str, Any],
    label: str,
) -> bool:
    if (
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], (ast.Eq, ast.NotEq))
        and len(node.comparators) == 1
    ):
        left = _static_operation_value(node.left, environment, label)
        right = _static_operation_value(node.comparators[0], environment, label)
        return left == right if isinstance(node.ops[0], ast.Eq) else left != right
    raise IntegrationError(f"{label}: unsupported static operation condition")


def _bind_static_operation_target(
    target: ast.AST,
    value: Any,
    environment: dict[str, Any],
    label: str,
) -> None:
    if isinstance(target, ast.Name):
        environment[target.id] = value
        return
    if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, tuple):
        if len(target.elts) != len(value):
            raise IntegrationError(f"{label}: operation comprehension unpacking drifted")
        for child, item in zip(target.elts, value, strict=True):
            _bind_static_operation_target(child, item, environment, label)
        return
    raise IntegrationError(f"{label}: unsupported operation comprehension target")


def _static_operation_environments(
    generators: Sequence[ast.comprehension],
    environment: Mapping[str, Any],
    label: str,
    index: int = 0,
) -> Iterator[dict[str, Any]]:
    if index == len(generators):
        yield dict(environment)
        return
    generator = generators[index]
    if generator.is_async:
        raise IntegrationError(f"{label}: async operation comprehension is forbidden")
    values = _static_operation_value(generator.iter, environment, label)
    if not isinstance(values, tuple):
        raise IntegrationError(f"{label}: operation comprehension input is not static")
    for value in values:
        child = dict(environment)
        _bind_static_operation_target(generator.target, value, child, label)
        if all(
            _static_operation_condition(condition, child, label)
            for condition in generator.ifs
        ):
            yield from _static_operation_environments(
                generators, child, label, index + 1
            )


def _static_operation_record(
    node: ast.AST,
    environment: Mapping[str, Any],
    label: str,
) -> Mapping[str, Any]:
    function_name = node.func.id if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) else None
    argument_count_valid = (
        function_name == "_single" and isinstance(node, ast.Call) and len(node.args) == 3
    ) or (
        function_name == "_spec"
        and isinstance(node, ast.Call)
        and 2 <= len(node.args) <= 4
    )
    if (
        not isinstance(node, ast.Call)
        or not isinstance(node.func, ast.Name)
        or node.func.id not in {"_spec", "_single"}
        or node.keywords
        or not argument_count_valid
    ):
        raise IntegrationError(f"{label}: operation record is not a static _spec/_single call")
    values = [
        _static_operation_value(argument, environment, label) for argument in node.args
    ]
    if any(not isinstance(value, str) for value in values):
        raise IntegrationError(f"{label}: operation record contains a non-string value")
    skill, operation = values[:2]
    fields = values[2] if len(values) >= 3 else ""
    required = values[3] if len(values) >= 4 else ""
    if (
        re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", skill) is None
        or re.fullmatch(r"[a-z][a-z0-9_]*", operation) is None
    ):
        raise IntegrationError(f"{label}: operation identity is not canonical")
    allowed_fields = fields.split()
    required_fields = required.split()
    field_pattern = re.compile(r"[a-z][a-z0-9_]*")
    if (
        len(allowed_fields) != len(set(allowed_fields))
        or len(required_fields) != len(set(required_fields))
        or any(field_pattern.fullmatch(field) is None for field in allowed_fields)
        or any(field_pattern.fullmatch(field) is None for field in required_fields)
        or set(required_fields) - set(allowed_fields)
    ):
        raise IntegrationError(f"{label}: operation field contract is invalid")
    return {
        "skill": skill,
        "operation": operation,
        "input_fields": sorted(allowed_fields),
        "required_input_fields": sorted(required_fields),
    }


def _expand_static_operation_records(
    node: ast.AST,
    environment: Mapping[str, Any],
    label: str,
) -> Iterator[Mapping[str, Any]]:
    if isinstance(node, ast.Call):
        yield _static_operation_record(node, environment, label)
        return
    if isinstance(node, ast.GeneratorExp):
        for child in _static_operation_environments(node.generators, environment, label):
            yield _static_operation_record(node.elt, child, label)
        return
    raise IntegrationError(f"{label}: unsupported operation registry expansion")


def _canonical_static_json_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256(encoded)


def _parse_operation_registry(
    path: Path,
    expected_skill_names: Sequence[str],
) -> OperationRegistrySnapshot:
    """Parse the trusted runtime registry without importing or executing it."""

    source = _read_bounded_regular_file(path, MAX_RUNTIME_FILE_BYTES, "operation registry")
    label = str(path)
    try:
        tree = ast.parse(_decode_utf8(source, label), filename=label)
    except SyntaxError as exc:
        raise IntegrationError(f"operation registry has invalid Python syntax: {path}") from exc

    schema_assignments: list[ast.AST] = []
    specs_assignments: list[ast.AST] = []
    digest_assignments: list[ast.AST] = []
    for node in tree.body:
        value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        names = {
            name
            for target in targets
            for name in _assignment_target_names(target)
        }
        if "OPERATION_REGISTRY_SCHEMA_VERSION" in names:
            schema_assignments.append(value)
        if "_SPECS" in names:
            specs_assignments.append(value)
        if "OPERATION_REGISTRY_DIGEST" in names:
            digest_assignments.append(value)
    if (
        len(schema_assignments) != 1
        or not isinstance(schema_assignments[0], ast.Constant)
        or schema_assignments[0].value != EXPECTED_OPERATION_REGISTRY_SCHEMA
    ):
        raise IntegrationError("operation registry schema binding drifted")
    if len(specs_assignments) != 1 or not isinstance(specs_assignments[0], ast.Tuple):
        raise IntegrationError("operation registry _SPECS must be one static tuple")
    if len(digest_assignments) != 1:
        raise IntegrationError("operation registry digest binding drifted")
    digest_call = digest_assignments[0]
    if not (
        isinstance(digest_call, ast.Call)
        and isinstance(digest_call.func, ast.Name)
        and digest_call.func.id == "canonical_digest"
        and len(digest_call.args) == 1
        and isinstance(digest_call.args[0], ast.Name)
        and digest_call.args[0].id == "OPERATION_REGISTRY_DOCUMENT"
        and not digest_call.keywords
    ):
        raise IntegrationError("operation registry digest is not canonically derived")

    records: list[Mapping[str, Any]] = []
    for element in specs_assignments[0].elts:
        if isinstance(element, ast.Starred):
            records.extend(_expand_static_operation_records(element.value, {}, label))
        else:
            record = _static_operation_record(element, {}, label)
            if not (
                isinstance(element, ast.Call)
                and isinstance(element.func, ast.Name)
                and element.func.id == "_spec"
            ):
                raise IntegrationError("unstarred operation record must use _spec")
            records.append(record)
    pairs = [(record["skill"], record["operation"]) for record in records]
    if len(pairs) != len(set(pairs)):
        raise IntegrationError("operation registry contains duplicate Skill/operation pairs")
    skill_names = tuple(sorted({record["skill"] for record in records}))
    expected_names = tuple(sorted(expected_skill_names))
    if skill_names != expected_names:
        missing = sorted(set(expected_names) - set(skill_names))
        extra = sorted(set(skill_names) - set(expected_names))
        raise IntegrationError(
            f"operation registry Skill coverage drift: missing={missing}, extra={extra}"
        )
    if len(records) != EXPECTED_OPERATION_COUNT:
        raise IntegrationError(
            f"operation registry count drift: {len(records)} != {EXPECTED_OPERATION_COUNT}"
        )
    sorted_records = tuple(
        sorted(records, key=lambda item: (item["skill"], item["operation"]))
    )
    document = {
        "schema_version": EXPECTED_OPERATION_REGISTRY_SCHEMA,
        "skill_count": len(skill_names),
        "operation_count": len(records),
        "operations": list(sorted_records),
    }
    document_sha256 = _canonical_static_json_digest(document)
    if document_sha256 != EXPECTED_OPERATION_REGISTRY_DIGEST:
        raise IntegrationError(
            "operation registry document digest drift: "
            f"{document_sha256} != {EXPECTED_OPERATION_REGISTRY_DIGEST}"
        )
    return OperationRegistrySnapshot(
        schema_version=EXPECTED_OPERATION_REGISTRY_SCHEMA,
        source_sha256=_sha256(source),
        skill_names=skill_names,
        operation_count=len(records),
        document_sha256=document_sha256,
        operations=sorted_records,
    )


def _validate_operation_input_schema(
    path: Path,
    operation_registry: OperationRegistrySnapshot,
) -> None:
    """Bind the checked-in conditional input Schema to every static operation."""

    document = _strict_json_bytes(
        _read_bounded_regular_file(
            path,
            MAX_RUNTIME_FILE_BYTES,
            "operation input Schema",
        ),
        "operation input Schema",
    )
    clauses: list[Mapping[str, Any]] = []
    for operation in operation_registry.operations:
        input_schema: dict[str, Any] = {
            "additionalProperties": False,
            "properties": {
                field: {} for field in operation["input_fields"]
            },
            "type": "object",
        }
        if operation["required_input_fields"]:
            input_schema["required"] = list(operation["required_input_fields"])
        clauses.append(
            {
                "if": {
                    "properties": {
                        "operation": {"const": operation["operation"]},
                        "skill": {"const": operation["skill"]},
                    },
                    "required": ["skill", "operation"],
                },
                "then": {
                    "properties": {"input": input_schema},
                    "required": ["input"],
                },
            }
        )
    expected = {
        "$id": (
            "https://elmos.local/schemas/"
            "multimodal-operation-input-contracts-v1.schema.json"
        ),
        "$schema": EXPECTED_SCHEMA_DRAFT,
        "allOf": clauses,
        "title": "ELMOS multimodal exact operation input fields",
        "type": "object",
        "x-elmos-operation-count": operation_registry.operation_count,
        "x-elmos-operation-registry-digest": operation_registry.document_sha256,
    }
    if document != expected:
        raise IntegrationError(
            "operation input Schema does not exactly match the static operation registry"
        )


def _validate_openapi_operation_input_schema_reference(engine_root: Path) -> None:
    """Require the public OpenAPI document to use one exact local Schema reference."""

    openapi_path = _resolve_below(
        engine_root,
        Path("openapi/multimodal-intake-v1.openapi.yaml"),
    )
    source = _decode_utf8(
        _read_bounded_regular_file(
            openapi_path,
            MAX_RUNTIME_FILE_BYTES,
            "multimodal OpenAPI document",
        ),
        "multimodal OpenAPI document",
    )
    external_references = re.findall(
        r'^\s*- \{ \$ref: "([^"#][^"]*)" \}$',
        source,
        re.MULTILINE,
    )
    if external_references != [OPENAPI_OPERATION_INPUT_SCHEMA_REFERENCE]:
        raise IntegrationError(
            "OpenAPI operation input Schema external reference inventory drifted"
        )
    referenced = _resolve_below(
        openapi_path.parent,
        Path(external_references[0]),
    )
    expected_path = _resolve_below(
        engine_root,
        Path("openapi/operation-input-contracts.schema.json"),
    )
    resolved = referenced.resolve(strict=True)
    if (
        referenced.is_symlink()
        or not referenced.is_file()
        or resolved != expected_path.resolve(strict=True)
        or resolved.parent != openapi_path.parent.resolve(strict=True)
    ):
        raise IntegrationError(
            "OpenAPI operation input Schema reference does not resolve inside its contract directory"
        )


def _parse_engine_registry(engine_path: Path, skills: Sequence[SkillContract]) -> tuple[str, dict[str, str]]:
    source = _read_bounded_regular_file(
        engine_path,
        MAX_RUNTIME_FILE_BYTES,
        "runtime engine",
    )
    try:
        tree = ast.parse(_decode_utf8(source, str(engine_path)), filename=str(engine_path))
    except SyntaxError as exc:
        raise IntegrationError(f"runtime engine has invalid Python syntax: {engine_path}") from exc

    expected_handlers = {skill.name: skill.handler_id for skill in skills}
    expected_ordinals = {skill.name: skill.ordinal for skill in skills}
    if (
        len(EXPECTED_HANDLER_PHASES) != len(skills)
        or len(EXPECTED_HANDLER_CALLS) != len(skills)
    ):
        raise IntegrationError(
            "expected handler phase/call contract is incomplete",
            code="MULTIMODAL_HANDLER_REGISTRY_INVALID",
        )
    expected_phases = {
        skill.name: EXPECTED_HANDLER_PHASES[skill.ordinal - 1]
        for skill in skills
    }
    expected_calls = {
        skill.name: EXPECTED_HANDLER_CALLS[skill.ordinal - 1]
        for skill in skills
    }
    expected_operation_names = {
        operation
        for _dispatcher, operation in expected_calls.values()
        if operation is not None
    }
    if expected_operation_names != set(EXPECTED_OPERATION_IMPORTS):
        raise IntegrationError(
            "expected handler operation imports are incomplete",
            code="MULTIMODAL_HANDLER_REGISTRY_INVALID",
        )

    function_nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    function_counts: dict[str, int] = {}
    for node in function_nodes:
        function_counts[node.name] = function_counts.get(node.name, 0) + 1
    duplicate_functions = sorted(name for name, count in function_counts.items() if count != 1)
    if duplicate_functions:
        raise IntegrationError(f"runtime engine has duplicate function definitions: {duplicate_functions}")
    functions = set(function_counts)

    dispatcher_names = {dispatcher for dispatcher, _operation in expected_calls.values()}
    dispatcher_nodes: dict[str, ast.FunctionDef] = {}
    for dispatcher in sorted(dispatcher_names):
        candidates = [node for node in function_nodes if node.name == dispatcher]
        if len(candidates) != 1 or not isinstance(candidates[0], ast.FunctionDef):
            raise IntegrationError(
                f"runtime dispatcher binding drift: {dispatcher}",
                code="MULTIMODAL_HANDLER_REGISTRY_INVALID",
            )
        dispatcher_nodes[dispatcher] = candidates[0]

    operation_import_nodes: dict[str, ast.ImportFrom] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        for alias in node.names:
            bound_name = alias.asname or alias.name
            expected_module = EXPECTED_OPERATION_IMPORTS.get(bound_name)
            if expected_module is None:
                continue
            if (
                bound_name in operation_import_nodes
                or node.level != 1
                or node.module != expected_module
                or alias.asname is not None
                or alias.name != bound_name
            ):
                raise IntegrationError(
                    f"runtime operation import drift: {bound_name}",
                    code="MULTIMODAL_HANDLER_REGISTRY_INVALID",
                )
            operation_import_nodes[bound_name] = node
    if set(operation_import_nodes) != expected_operation_names:
        missing = sorted(expected_operation_names - set(operation_import_nodes))
        raise IntegrationError(
            f"runtime operation imports are incomplete: {missing}",
            code="MULTIMODAL_HANDLER_REGISTRY_INVALID",
        )

    binding_classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HandlerBinding"
    ]
    if len(binding_classes) != 1:
        raise IntegrationError("runtime engine must define exactly one HandlerBinding")
    binding_class = binding_classes[0]
    exact_dataclass_decorator = (
        len(binding_class.decorator_list) == 1
        and isinstance(binding_class.decorator_list[0], ast.Call)
        and isinstance(binding_class.decorator_list[0].func, ast.Name)
        and binding_class.decorator_list[0].func.id == "dataclass"
        and not binding_class.decorator_list[0].args
        and len(binding_class.decorator_list[0].keywords) == 1
        and binding_class.decorator_list[0].keywords[0].arg == "frozen"
        and isinstance(binding_class.decorator_list[0].keywords[0].value, ast.Constant)
        and binding_class.decorator_list[0].keywords[0].value.value is True
    )
    expected_binding_fields = (
        ("ordinal", "int"),
        ("skill", "str"),
        ("handler_id", "str"),
        ("phase", "str"),
        ("handler", "SkillHandler"),
    )
    observed_binding_fields: list[tuple[str, str]] = []
    for field in binding_class.body:
        if (
            not isinstance(field, ast.AnnAssign)
            or not isinstance(field.target, ast.Name)
            or not isinstance(field.annotation, ast.Name)
            or field.value is not None
            or field.simple != 1
        ):
            raise IntegrationError("runtime HandlerBinding field structure drift")
        observed_binding_fields.append((field.target.id, field.annotation.id))
    if (
        binding_class.bases
        or binding_class.keywords
        or getattr(binding_class, "type_params", ())
        or not exact_dataclass_decorator
        or tuple(observed_binding_fields) != expected_binding_fields
    ):
        raise IntegrationError("runtime HandlerBinding structure drift")

    dataclass_imports: list[ast.ImportFrom] = []
    for node in tree.body:
        if (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == "dataclasses"
            and len(node.names) == 1
            and node.names[0].name == "dataclass"
            and node.names[0].asname is None
        ):
            dataclass_imports.append(node)
    if len(dataclass_imports) != 1:
        raise IntegrationError("runtime must import dataclass exactly from dataclasses")
    dataclass_import = dataclass_imports[0]

    entry_nodes = [node for node in function_nodes if node.name == "_entry"]
    if len(entry_nodes) != 1:
        raise IntegrationError("runtime engine must define exactly one static _entry helper")
    entry = entry_nodes[0]
    if (
        isinstance(entry, ast.AsyncFunctionDef)
        or entry.decorator_list
        or entry.args.posonlyargs
        or entry.args.vararg is not None
        or entry.args.kwonlyargs
        or entry.args.kwarg is not None
        or entry.args.defaults
        or entry.args.kw_defaults
        or [argument.arg for argument in entry.args.args] != ["ordinal", "skill", "phase", "handler"]
        or len(entry.body) != 1
        or not isinstance(entry.body[0], ast.Return)
        or not isinstance(entry.body[0].value, ast.Call)
    ):
        raise IntegrationError("runtime _entry helper shape drift")
    entry_call = entry.body[0].value
    expected_entry_arguments = (
        isinstance(entry_call.func, ast.Name)
        and entry_call.func.id == "HandlerBinding"
        and not entry_call.keywords
        and len(entry_call.args) == 5
        and isinstance(entry_call.args[0], ast.Name)
        and entry_call.args[0].id == "ordinal"
        and isinstance(entry_call.args[1], ast.Name)
        and entry_call.args[1].id == "skill"
        and isinstance(entry_call.args[2], ast.Call)
        and isinstance(entry_call.args[2].func, ast.Name)
        and entry_call.args[2].func.id == "getattr"
        and len(entry_call.args[2].args) == 2
        and not entry_call.args[2].keywords
        and isinstance(entry_call.args[2].args[0], ast.Name)
        and entry_call.args[2].args[0].id == "handler"
        and isinstance(entry_call.args[2].args[1], ast.Constant)
        and entry_call.args[2].args[1].value == "__name__"
        and isinstance(entry_call.args[3], ast.Name)
        and entry_call.args[3].id == "phase"
        and isinstance(entry_call.args[4], ast.Name)
        and entry_call.args[4].id == "handler"
    )
    if not expected_entry_arguments:
        raise IntegrationError("runtime _entry helper implementation drift")

    registry_node: ast.Dict | None = None
    registry_binding_node: ast.Assign | ast.AnnAssign | None = None
    registry_assignments = 0
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SKILL_REGISTRY"
            for target in node.targets
        ):
            registry_assignments += 1
            if not isinstance(node.value, ast.Dict):
                raise IntegrationError("SKILL_REGISTRY must be a static dict literal")
            registry_node = node.value
            registry_binding_node = node
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "SKILL_REGISTRY"
        ):
            registry_assignments += 1
            if not isinstance(node.value, ast.Dict):
                raise IntegrationError("SKILL_REGISTRY must be a static dict literal")
            registry_node = node.value
            registry_binding_node = node
    if registry_node is None or registry_binding_node is None or registry_assignments != 1:
        raise IntegrationError("runtime engine must define exactly one static SKILL_REGISTRY")

    registry: dict[str, str] = {}
    for key_node, value_node in zip(registry_node.keys, registry_node.values, strict=True):
        if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
            raise IntegrationError("SKILL_REGISTRY keys must be literal Skill names")
        if (
            not isinstance(value_node, ast.Call)
            or not isinstance(value_node.func, ast.Name)
            or value_node.func.id != "_entry"
            or value_node.keywords
            or len(value_node.args) != 4
        ):
            raise IntegrationError("SKILL_REGISTRY values must be exact static _entry calls")
        ordinal_node, skill_node, phase_node, handler_node = value_node.args
        if type(getattr(ordinal_node, "value", None)) is not int:
            raise IntegrationError("_entry ordinal must be a literal integer")
        if not isinstance(skill_node, ast.Constant) or not isinstance(skill_node.value, str):
            raise IntegrationError("_entry Skill must be a literal string")
        if not isinstance(phase_node, ast.Constant) or not isinstance(phase_node.value, str):
            raise IntegrationError("_entry phase must be a literal string")
        if not isinstance(handler_node, ast.Name):
            raise IntegrationError("_entry handler must be a function reference")
        key = key_node.value
        if (
            key not in expected_handlers
            or ordinal_node.value != expected_ordinals[key]
            or skill_node.value != key
            or phase_node.value != expected_phases[key]
            or handler_node.id != expected_handlers[key]
        ):
            raise IntegrationError(f"_entry identity, phase, or handler drift: {key}")
        handler = handler_node.id
        if key_node.value in registry:
            raise IntegrationError(f"duplicate SKILL_REGISTRY key: {key_node.value}")
        registry[key_node.value] = handler

    if len(set(registry.values())) != len(registry):
        raise IntegrationError("SKILL_REGISTRY callable bindings are not unique")
    expected = expected_handlers
    if registry != expected:
        missing = sorted(set(expected) - set(registry))
        extra = sorted(set(registry) - set(expected))
        wrong = sorted(
            name for name in set(expected) & set(registry) if expected[name] != registry[name]
        )
        raise IntegrationError(
            f"SKILL_REGISTRY drift: missing={missing}, extra={extra}, wrong={wrong}"
        )
    undefined = sorted(set(registry.values()) - functions)
    if undefined:
        raise IntegrationError(f"SKILL_REGISTRY handlers are not defined: {undefined}")
    registered_names = set(registry.values())
    handler_nodes = {
        node.name: node
        for node in function_nodes
        if node.name in registered_names
    }
    for handler_name in sorted(registered_names):
        node = handler_nodes[handler_name]
        if (
            not isinstance(node, ast.FunctionDef)
            or node.decorator_list
            or node.args.posonlyargs
            or [argument.arg for argument in node.args.args] != ["request"]
            or node.args.vararg is not None
            or node.args.kwonlyargs
            or node.args.kwarg is not None
            or node.args.defaults
            or node.args.kw_defaults
        ):
            raise IntegrationError(
                f"registered handler must be an undecorated synchronous request callable: {handler_name}"
            )
        skill_name = next(
            skill for skill, registered_handler in registry.items()
            if registered_handler == handler_name
        )
        dispatcher, operation = expected_calls[skill_name]
        if (
            len(node.body) != 1
            or not isinstance(node.body[0], ast.Return)
            or not isinstance(node.body[0].value, ast.Call)
        ):
            raise IntegrationError(
                f"registered handler body is not an exact static dispatch: {handler_name}",
                code="MULTIMODAL_HANDLER_REGISTRY_INVALID",
            )
        call = node.body[0].value
        exact_common = (
            isinstance(call.func, ast.Name)
            and call.func.id == dispatcher
            and not call.keywords
            and isinstance(call.args[0], ast.Constant)
            and call.args[0].value == skill_name
            and isinstance(call.args[-1], ast.Name)
            and call.args[-1].id == "request"
        ) if call.args else False
        exact_operation = (
            operation is None
            and len(call.args) == 2
            or operation is not None
            and len(call.args) == 3
            and isinstance(call.args[1], ast.Name)
            and call.args[1].id == operation
        )
        if not exact_common or not exact_operation:
            raise IntegrationError(
                f"registered handler call binding drift: {handler_name}",
                code="MULTIMODAL_HANDLER_REGISTRY_INVALID",
            )

    protected_names = registered_names | {
        "HandlerBinding",
        "SKILL_REGISTRY",
        "_entry",
        "dataclass",
        "getattr",
        "len",
    } | dispatcher_names | expected_operation_names
    allowed_bindings = {
        (id(binding_class), "HandlerBinding"),
        (id(dataclass_import), "dataclass"),
        (id(entry), "_entry"),
        (id(registry_binding_node), "SKILL_REGISTRY"),
    }
    allowed_bindings.update(
        (id(node), node.name)
        for node in handler_nodes.values()
    )
    allowed_bindings.update(
        (id(node), name)
        for name, node in dispatcher_nodes.items()
    )
    allowed_bindings.update(
        (id(node), name)
        for name, node in operation_import_nodes.items()
    )
    for node in ast.walk(tree):
        for name in _bound_names(node) & protected_names:
            if (id(node), name) not in allowed_bindings:
                raise IntegrationError(f"protected runtime name is rebound or shadowed: {name}")
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
            root_name = _attribute_root_name(node)
            if root_name in protected_names:
                raise IntegrationError(
                    f"protected runtime object is mutated through an attribute: {root_name}"
                )
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            raise IntegrationError("protected runtime names may not be populated by star import")
        if (
            isinstance(node, ast.Import)
            and any(alias.name == "builtins" for alias in node.names)
        ) or (
            isinstance(node, ast.ImportFrom)
            and node.module == "builtins"
        ) or (
            isinstance(node, ast.Name)
            and node.id == "__builtins__"
        ):
            raise IntegrationError("direct builtins namespace access is not allowed")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            shadowed = sorted(set(node.names) & protected_names)
            if shadowed:
                raise IntegrationError(f"protected runtime name has dynamic scope: {shadowed}")
        if isinstance(node, ast.Call):
            call_name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else None
            )
            if call_name in {
                "__delattr__",
                "__delitem__",
                "__setattr__",
                "__setitem__",
                "__import__",
                "compile",
                "delattr",
                "delitem",
                "eval",
                "exec",
                "globals",
                "locals",
                "setattr",
                "setitem",
                "vars",
            }:
                raise IntegrationError(f"dynamic namespace operation is not allowed: {call_name}")

    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    for node in ast.walk(tree):
        if not isinstance(node, ast.Name) or node.id != "SKILL_REGISTRY":
            continue
        if not isinstance(node.ctx, ast.Load):
            if parents.get(id(node)) is registry_binding_node:
                continue
            raise IntegrationError("SKILL_REGISTRY may only have its canonical binding")
        parent = parents.get(id(node))
        if isinstance(parent, ast.Attribute) and parent.value is node:
            call = parents.get(id(parent))
            if (
                parent.attr in {"get", "items", "values"}
                and isinstance(call, ast.Call)
                and call.func is parent
            ):
                continue
        if isinstance(parent, ast.Call) and parent.func is not node:
            if (
                isinstance(parent.func, ast.Name)
                and parent.func.id == "len"
                and parent.args == [node]
                and not parent.keywords
            ):
                continue
        raise IntegrationError("SKILL_REGISTRY reference may alias or mutate the registry")
    return _sha256(source), registry


def _expected_matrix(snapshot: PackageSnapshot) -> dict[str, Any]:
    engine = ENGINE_RELATIVE_PATH.as_posix()
    test = TEST_RELATIVE_PATH.as_posix()
    return {
        "schema_version": "1.0.0",
        "package": {"name": PACKAGE_NAME, "version": PACKAGE_VERSION},
        "source_archive": ARCHIVE_RELATIVE_PATH.as_posix(),
        "source_archive_sha256": ARCHIVE_SHA256,
        "engine_path": engine,
        "test_path": test,
        "handler_count": EXPECTED_SKILL_COUNT,
        "acceptance_count": EXPECTED_ACCEPTANCE_COUNT,
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification_status": CERTIFICATION_STATUS,
        "handlers": [
            {
                "ordinal": skill.ordinal,
                "skill": skill.name,
                "handler_id": skill.handler_id,
                "phase": EXPECTED_HANDLER_PHASES[skill.ordinal - 1],
                "acceptance_ids": list(skill.acceptance_ids),
                "code_path": f"{engine}::{skill.handler_id}",
                "test_path": test,
                "implementation_evidence": EXTERNAL_EVIDENCE_STATUS,
                "certification": CERTIFICATION_STATUS,
            }
            for skill in snapshot.skills
        ],
    }


def _load_json(path: Path, label: str) -> Any:
    return _strict_json_bytes(
        _read_bounded_regular_file(path, MAX_MANAGED_JSON_BYTES, label),
        label,
    )


def _validate_matrix(repo_root: Path, snapshot: PackageSnapshot) -> None:
    matrix_path = _resolve_below(repo_root, MATRIX_RELATIVE_PATH)
    if _load_json(matrix_path, "implementation matrix") != _expected_matrix(snapshot):
        raise IntegrationError("implementation-matrix.json does not match pinned contracts")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _render_installed_skill(
    snapshot: PackageSnapshot,
    skill: SkillContract,
    runtime: RuntimeSnapshot,
) -> bytes:
    source_path = (SOURCE_RELATIVE_PATH / "skills" / skill.name / "SKILL.md").as_posix()
    contract_path = (
        SOURCE_RELATIVE_PATH / "skills" / skill.name / "references/contract.yaml"
    ).as_posix()
    dependencies = ", ".join(f"`${name}`" for name in skill.dependencies) or "none"
    acceptance_ids = ", ".join(f"`{value}`" for value in skill.acceptance_ids)
    section = f"""

## Repository Integration Boundary

- Canonical Skill ordinal: `{skill.ordinal}`
- Immutable source: `{source_path}`
- Immutable contract: `{contract_path}`
- Source package: `{PACKAGE_NAME}@{PACKAGE_VERSION}`
- Source archive SHA-256: `{snapshot.archive_sha256}`
- Source SKILL.md SHA-256: `{skill.skill_md_sha256}`
- Source contract SHA-256: `{skill.contract_sha256}`
- Runtime handler: `{ENGINE_RELATIVE_PATH.as_posix()}::{skill.handler_id}`
- Runtime phase: `{EXPECTED_HANDLER_PHASES[skill.ordinal - 1]}`
- Runtime implementation aggregate SHA-256: `{runtime.implementation_sha256}`
- Runtime test aggregate SHA-256: `{runtime.tests_sha256}`
- Exact dependencies: {dependencies}
- Acceptance identities: {acceptance_ids}
- Generated contract: `compiled-contract.json`
- Codex interface: `agents/openai.yaml`
- External evidence: `{EXTERNAL_EVIDENCE_STATUS}`
- Certification: `{CERTIFICATION_STATUS}`

Package scripts remain untrusted input and are never executed by this importer.
Acceptance criteria are preserved as contracts; this installation does not claim
that they were executed or passed.
"""
    return (_decode_utf8(skill.skill_md, f"{skill.name}/SKILL.md").rstrip() + section).encode(
        "utf-8"
    )


def _render_openai_yaml(skill: SkillContract) -> bytes:
    short_description = "Run this ELMOS Skill with evidence controls"
    default_prompt = (
        f"Use ${skill.name} to execute this ELMOS Skill with fail-closed evidence."
    )
    if not 25 <= len(short_description) <= 64 or f"${skill.name}" not in default_prompt:
        raise IntegrationError(f"{skill.name}: invalid generated Codex interface")
    return (
        "\n".join(
            [
                "interface:",
                f"  display_name: {yaml_quote(format_display_name(skill.name))}",
                f"  short_description: {yaml_quote(short_description)}",
                f"  default_prompt: {yaml_quote(default_prompt)}",
                "policy:",
                "  allow_implicit_invocation: true",
                "",
            ]
        )
    ).encode("utf-8")


def _compiled_skill_contract(
    snapshot: PackageSnapshot,
    skill: SkillContract,
    runtime: RuntimeSnapshot,
    importer_sha256: str | None,
) -> Mapping[str, Any]:
    skill_member = f"skills/{skill.name}/SKILL.md"
    contract_member = f"skills/{skill.name}/references/contract.yaml"
    provenance: dict[str, Any] = {
        "compiler_path": IMPORTER_RELATIVE_PATH.as_posix(),
        "canonical_skill_member": skill_member,
        "canonical_contract_member": contract_member,
        "canonical_members": {
            skill_member: {
                "bytes": snapshot.member_size[skill_member],
                "mode": f"{snapshot.member_mode[skill_member]:04o}",
                "sha256": snapshot.member_sha256[skill_member],
            },
            contract_member: {
                "bytes": snapshot.member_size[contract_member],
                "mode": f"{snapshot.member_mode[contract_member]:04o}",
                "sha256": snapshot.member_sha256[contract_member],
            },
        },
        "mirrors_verified_byte_identical": [
            "skills",
            ".agents/skills",
            ".claude/skills",
        ],
        "archive_scripts_executed": False,
    }
    if importer_sha256 is not None:
        provenance["compiler_sha256"] = importer_sha256
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.multimodal-intake.compiled-skill-contract",
        "package": {"name": PACKAGE_NAME, "version": PACKAGE_VERSION},
        "source": {
            "archive_path": ARCHIVE_RELATIVE_PATH.as_posix(),
            "archive_sha256": snapshot.archive_sha256,
            "package_manifest_sha256": snapshot.manifest_sha256,
            "skill_md_sha256": skill.skill_md_sha256,
            "contract_sha256": skill.contract_sha256,
        },
        "provenance": provenance,
        "skill": {
            "ordinal": skill.ordinal,
            "name": skill.name,
            "title": skill.title,
            "description": skill.description,
        },
        "contract": skill.contract,
        "runtime": {
            "handler_id": skill.handler_id,
            "phase": EXPECTED_HANDLER_PHASES[skill.ordinal - 1],
            "engine_path": ENGINE_RELATIVE_PATH.as_posix(),
            "implementation_sha256": runtime.implementation_sha256,
            "tests_sha256": runtime.tests_sha256,
        },
        "acceptance": [
            {
                "id": acceptance_id,
                "criterion": criterion,
                "status": EXTERNAL_EVIDENCE_STATUS,
                "evidence": [],
            }
            for acceptance_id, criterion in zip(
                skill.acceptance_ids, skill.acceptance, strict=True
            )
        ],
        "acceptance_criteria_executed": False,
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification_status": CERTIFICATION_STATUS,
    }


def _expected_skill_payloads(
    snapshot: PackageSnapshot,
    runtime: RuntimeSnapshot,
    importer_sha256: str | None,
) -> dict[str, dict[str, FilePayload]]:
    return {
        skill.name: {
            "SKILL.md": FilePayload(_render_installed_skill(snapshot, skill, runtime)),
            "references/contract.yaml": FilePayload(skill.contract_yaml),
            "compiled-contract.json": FilePayload(
                _json_bytes(
                    _compiled_skill_contract(
                        snapshot, skill, runtime, importer_sha256
                    )
                )
            ),
            "agents/openai.yaml": FilePayload(_render_openai_yaml(skill)),
        }
        for skill in snapshot.skills
    }


def _compiled_manifest(
    snapshot: PackageSnapshot,
    engine_sha256: str,
    runtime: RuntimeSnapshot,
    skill_payloads: Mapping[str, Mapping[str, FilePayload]],
    importer_sha256: str | None,
    operation_registry: OperationRegistrySnapshot | None,
) -> dict[str, Any]:
    engine = ENGINE_RELATIVE_PATH.as_posix()
    engine_record = next(
        (item for item in runtime.implementation_files if item["path"] == engine),
        None,
    )
    if engine_record is None or engine_record["sha256"] != engine_sha256:
        raise IntegrationError("runtime changed while handler binding was validated")
    if (importer_sha256 is None) != (operation_registry is None):
        raise IntegrationError("compiled manifest generation identity is incomplete")
    document: dict[str, Any] = {
        "schema_version": "1.0.0",
        "kind": "elmos.multimodal-intake.compiled-manifest",
        "package": {"name": PACKAGE_NAME, "version": PACKAGE_VERSION},
        "archive": {
            "path": ARCHIVE_RELATIVE_PATH.as_posix(),
            "sha256": snapshot.archive_sha256,
            "compressed_bytes": EXPECTED_ARCHIVE_BYTES,
            "entries": snapshot.entry_count,
            "uncompressed_bytes": snapshot.uncompressed_bytes,
            "internal_checksums": snapshot.internal_checksum_count,
            "manifest_sha256": snapshot.manifest_sha256,
            "crc32_verified": True,
            "modes_verified": True,
            "case_and_unicode_collisions_rejected": True,
            "archive_scripts_executed": False,
        },
        "contracts": {
            "skills": len(snapshot.skills),
            "acceptance": sum(len(skill.acceptance_ids) for skill in snapshot.skills),
            "deliverables": sum(len(skill.deliverables) for skill in snapshot.skills),
            "global_gates": [
                {**gate, "status": EXTERNAL_EVIDENCE_STATUS, "evidence_files": []}
                for gate in snapshot.global_gates
            ],
            "dependency_edges": sum(len(skill.dependencies) for skill in snapshot.skills),
            "cyclic_sccs": [list(component) for component in snapshot.dependency_sccs],
        },
        "runtime": {
            "root": ".",
            "roots": [
                ENGINE_ROOT_RELATIVE_PATH.as_posix(),
                "apps/web-console",
                "tests/multimodal-intake",
            ],
            "implementation": {
                "file_count": len(runtime.implementation_files),
                "aggregate_sha256": runtime.implementation_sha256,
                "files": list(runtime.implementation_files),
            },
            "tests": {
                "file_count": len(runtime.test_files),
                "aggregate_sha256": runtime.tests_sha256,
                "files": list(runtime.test_files),
                "execution_status": EXTERNAL_EVIDENCE_STATUS,
            },
        },
        "engine": {
            "path": engine,
            "sha256": engine_sha256,
            "registry": "SKILL_REGISTRY",
            "handler_count": len(snapshot.skills),
        },
        "acceptance_criteria_executed": False,
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification_status": CERTIFICATION_STATUS,
        "skills": [
            {
                "ordinal": skill.ordinal,
                "name": skill.name,
                "title": skill.title,
                "handler_id": skill.handler_id,
                "phase": EXPECTED_HANDLER_PHASES[skill.ordinal - 1],
                "engine_path": engine,
                "engine_sha256": engine_sha256,
                "skill_md_sha256": skill.skill_md_sha256,
                "contract_sha256": skill.contract_sha256,
                "compiled_contract_sha256": _sha256(
                    skill_payloads[skill.name]["compiled-contract.json"].data
                ),
                "installed_tree_sha256": _payload_tree_digest(skill_payloads[skill.name]),
                "dependencies": list(skill.dependencies),
                "acceptance_ids": list(skill.acceptance_ids),
                "acceptance_status": EXTERNAL_EVIDENCE_STATUS,
                "deliverable_count": len(skill.deliverables),
                "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
                "certification_status": CERTIFICATION_STATUS,
            }
            for skill in snapshot.skills
        ],
    }
    if importer_sha256 is not None and operation_registry is not None:
        operation_record = next(
            (
                item
                for item in runtime.implementation_files
                if item["path"] == OPERATION_REGISTRY_RELATIVE_PATH.as_posix()
            ),
            None,
        )
        if (
            operation_record is None
            or operation_record["sha256"] != operation_registry.source_sha256
        ):
            raise IntegrationError("operation registry changed while it was validated")
        document["compiler"] = {
            "path": IMPORTER_RELATIVE_PATH.as_posix(),
            "sha256": importer_sha256,
        }
        document["operation_registry"] = {
            "path": OPERATION_REGISTRY_RELATIVE_PATH.as_posix(),
            "source_sha256": operation_registry.source_sha256,
            "schema_version": operation_registry.schema_version,
            "skill_count": len(operation_registry.skill_names),
            "skills": list(operation_registry.skill_names),
            "operation_count": operation_registry.operation_count,
            "document_sha256": operation_registry.document_sha256,
            "static_ast_validated": True,
        }
    return document


def _installed_manifest(
    snapshot: PackageSnapshot,
    runtime: RuntimeSnapshot,
    compiled_manifest_bytes: bytes,
    source_payloads: Mapping[str, FilePayload],
    skill_payloads: Mapping[str, Mapping[str, FilePayload]],
) -> dict[str, Any]:
    digests = {
        skill.name: _payload_tree_digest(skill_payloads[skill.name])
        for skill in snapshot.skills
    }
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.multimodal-intake.installed-manifest",
        "package": {"name": PACKAGE_NAME, "version": PACKAGE_VERSION},
        "archive_sha256": snapshot.archive_sha256,
        "compiled_manifest_sha256": _sha256(compiled_manifest_bytes),
        "source": {
            "path": SOURCE_RELATIVE_PATH.as_posix(),
            "file_count": len(source_payloads),
            "tree_sha256": _payload_tree_digest(source_payloads),
            "immutable_by_digest": True,
            "modes_pinned": True,
            "canonical_root": "skills",
            "mirror_roots_verified_byte_identical": [
                ".agents/skills",
                ".claude/skills",
            ],
            "archive_scripts_executed": False,
        },
        "runtime": {
            "root": ".",
            "roots": [
                ENGINE_ROOT_RELATIVE_PATH.as_posix(),
                "apps/web-console",
                "tests/multimodal-intake",
            ],
            "implementation_sha256": runtime.implementation_sha256,
            "tests_sha256": runtime.tests_sha256,
        },
        "installations": [
            {
                "root": relative_root.as_posix(),
                "skill_count": len(digests),
                "skill_tree_sha256": digests,
                "modes_pinned": True,
            }
            for relative_root in INSTALL_ROOTS
        ],
        "acceptance_criteria_executed": False,
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification_status": CERTIFICATION_STATUS,
    }


def _assert_file_payload(path: Path, payload: FilePayload, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise IntegrationError(f"missing or unsafe {label}: {path}")
    metadata = path.lstat()
    if stat.S_IMODE(metadata.st_mode) != payload.mode:
        raise IntegrationError(f"{label} mode drifted: {path}")
    if metadata.st_size != len(payload.data) or _digest_file(path) != _sha256(payload.data):
        raise IntegrationError(f"{label} content drifted: {path}")


@dataclass(frozen=True)
class _ManagedTarget:
    destination: Path
    kind: str
    payload: Any
    replace: bool
    original_fingerprint: str | None
    label: str


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


@contextmanager
def _repository_lock(repo_root: Path, *, exclusive: bool) -> Iterator[None]:
    """Hold a process-scoped lock on the repository directory without creating files."""

    root = repo_root.resolve()
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise IntegrationError(f"repository lock cannot be opened safely: {root}") from exc
    acquired = False
    try:
        metadata = os.fstat(descriptor)
        current = root.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_dev != current.st_dev
            or metadata.st_ino != current.st_ino
        ):
            raise IntegrationError(f"repository lock identity changed: {root}")
        operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}:
                owner = "writer" if exclusive else "integration operation"
                raise IntegrationError(
                    f"another multimodal-intake {owner} is active for {root}"
                ) from exc
            raise IntegrationError(f"repository lock failed for {root}") from exc
        acquired = True
        yield
    finally:
        try:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


@contextmanager
def _writer_lock(repo_root: Path) -> Iterator[None]:
    with _repository_lock(repo_root, exclusive=True):
        yield


@contextmanager
def _check_lock(repo_root: Path) -> Iterator[None]:
    with _repository_lock(repo_root, exclusive=False):
        yield


def _fsync_directory(path: Path) -> None:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise IntegrationError(f"directory cannot be opened for durable sync: {path}") from exc
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise IntegrationError(f"durable sync target is not a directory: {path}")
        os.fsync(descriptor)
    except OSError as exc:
        raise IntegrationError(f"directory durable sync failed: {path}") from exc
    finally:
        os.close(descriptor)


def _fsync_tree_directories(root: Path) -> None:
    directories = [path for path in root.rglob("*") if path.is_dir()]
    for directory in sorted(
        directories,
        key=lambda path: (-len(path.relative_to(root).parts), path.as_posix()),
    ):
        _fsync_directory(directory)
    _fsync_directory(root)


def _durable_replace(source: Path, destination: Path) -> None:
    source_parent = source.parent
    destination_parent = destination.parent
    os.replace(source, destination)
    _fsync_directory(destination_parent)
    if source_parent != destination_parent:
        _fsync_directory(source_parent)


def _path_fingerprint(path: Path) -> str:
    if path.is_symlink():
        raise IntegrationError(f"managed destination is a symlink: {path}")
    if path.is_dir():
        return f"D:{_tree_digest(path)}"
    if path.is_file():
        metadata = path.lstat()
        return (
            f"F:{stat.S_IMODE(metadata.st_mode):04o}:{metadata.st_size}:"
            f"{_digest_file(path)}"
        )
    raise IntegrationError(f"managed destination is not a regular file or directory: {path}")


def _payload_fingerprint(target: _ManagedTarget) -> str:
    if target.kind == "tree":
        if not isinstance(target.payload, Mapping):
            raise IntegrationError(f"managed tree payload is invalid: {target.label}")
        return f"D:{_payload_tree_digest(target.payload)}"
    if target.kind == "file":
        if not isinstance(target.payload, FilePayload):
            raise IntegrationError(f"managed file payload is invalid: {target.label}")
        payload = target.payload
        return f"F:{payload.mode:04o}:{len(payload.data)}:{_sha256(payload.data)}"
    raise IntegrationError(f"unknown managed target kind: {target.kind}")


def _fingerprint_kind(fingerprint: str) -> str | None:
    if re.fullmatch(r"D:[0-9a-f]{64}", fingerprint):
        return "tree"
    if re.fullmatch(r"F:[0-7]{4}:(?:0|[1-9][0-9]*):[0-9a-f]{64}", fingerprint):
        return "file"
    return None


def _fingerprint_if_present(path: Path) -> str | None:
    return _path_fingerprint(path) if _lexists(path) else None


def _repo_relative_destination(repo_root: Path, destination: Path) -> str:
    root = repo_root.resolve()
    try:
        relative = destination.relative_to(root)
    except ValueError as exc:
        raise IntegrationError(f"managed destination escapes repository root: {destination}") from exc
    if relative == Path("."):
        raise IntegrationError("repository root cannot be a managed destination")
    normalized = relative.as_posix()
    if _resolve_below(root, Path(normalized)) != destination:
        raise IntegrationError(f"managed destination is not canonical: {destination}")
    return normalized


def _allowed_managed_targets(snapshot: PackageSnapshot) -> dict[str, str]:
    allowed = {SOURCE_RELATIVE_PATH.as_posix(): "tree"}
    for install_root in INSTALL_ROOTS:
        for skill in snapshot.skills:
            allowed[(install_root / skill.name).as_posix()] = "tree"
    allowed[COMPILED_MANIFEST_RELATIVE_PATH.as_posix()] = "file"
    allowed[INSTALLED_MANIFEST_RELATIVE_PATH.as_posix()] = "file"
    return allowed


def _allowed_managed_parents(allowed_targets: Mapping[str, str]) -> set[str]:
    allowed: set[str] = set()
    for destination in allowed_targets:
        parent = PurePosixPath(destination).parent
        while parent != PurePosixPath("."):
            allowed.add(parent.as_posix())
            parent = parent.parent
    return allowed


def _planned_created_parents(
    repo_root: Path,
    targets: Sequence[_ManagedTarget],
) -> list[str]:
    planned: set[str] = set()
    root = repo_root.resolve()
    for target in targets:
        relative = PurePosixPath(_repo_relative_destination(root, target.destination)).parent
        while relative != PurePosixPath("."):
            path = _resolve_below(root, Path(relative.as_posix()))
            if not _lexists(path):
                planned.add(relative.as_posix())
            elif path.is_symlink() or not path.is_dir():
                raise IntegrationError(f"managed destination parent is unsafe: {path}")
            relative = relative.parent
    return sorted(planned, key=lambda value: (len(PurePosixPath(value).parts), value))


def _strict_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise IntegrationError(
            f"{label} fields differ: expected={sorted(expected)}, got={sorted(value)}"
        )


def _transaction_name_is_valid(name: str) -> bool:
    return re.fullmatch(
        rf"{re.escape(TRANSACTION_PREFIX)}[A-Za-z0-9_-]{{6,64}}",
        name,
    ) is not None


def _transaction_roots(repo_root: Path) -> tuple[Path, ...]:
    roots: list[Path] = []
    with os.scandir(repo_root) as entries:
        for entry in entries:
            if not entry.name.startswith(TRANSACTION_PREFIX):
                continue
            path = Path(entry.path)
            if (
                not _transaction_name_is_valid(entry.name)
                or entry.is_symlink()
                or not entry.is_dir(follow_symlinks=False)
            ):
                raise IntegrationError(
                    f"unsafe multimodal-intake transaction artifact preserved: {path}"
                )
            roots.append(path)
    return tuple(sorted(roots))


def _assert_no_stale_transactions(repo_root: Path) -> None:
    stale = _transaction_roots(repo_root)
    if stale:
        raise IntegrationError(
            "stale multimodal-intake transaction requires --write recovery: "
            + ", ".join(path.name for path in stale)
        )


def _journal_bytes(journal: Mapping[str, Any]) -> bytes:
    data = _json_bytes(journal)
    if len(data) > MAX_TRANSACTION_JOURNAL_BYTES:
        raise IntegrationError("transaction journal exceeds its byte bound")
    return data


def _write_journal_atomic(transaction_root: Path, journal: Mapping[str, Any]) -> None:
    if transaction_root.is_symlink() or not transaction_root.is_dir():
        raise IntegrationError(f"transaction root is unsafe: {transaction_root}")
    data = _journal_bytes(journal)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".journal-v1-",
        suffix=".tmp",
        dir=transaction_root,
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(data)
        written = 0
        while written < len(data):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise IntegrationError("transaction journal write made no progress")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    journal_path = transaction_root / TRANSACTION_JOURNAL_NAME
    if _lexists(journal_path):
        if journal_path.is_symlink() or not journal_path.is_file():
            raise IntegrationError(f"transaction journal is unsafe: {journal_path}")
        if stat.S_IMODE(journal_path.lstat().st_mode) != 0o600:
            raise IntegrationError(f"transaction journal mode drifted: {journal_path}")
    _durable_replace(temporary_path, journal_path)


def _validate_journal_document(
    document: Any,
    *,
    transaction_root: Path,
    archive_sha256: str,
    allowed_targets: Mapping[str, str],
) -> dict[str, Any]:
    label = f"transaction journal {transaction_root.name}"
    if not isinstance(document, dict):
        raise IntegrationError(f"{label} root must be an object")
    _strict_keys(
        document,
        {
            "archive_sha256",
            "created_parents",
            "package",
            "recovery_started",
            "schema_version",
            "targets",
            "transaction_id",
        },
        label,
    )
    if document["schema_version"] != TRANSACTION_JOURNAL_SCHEMA:
        raise IntegrationError(f"{label} schema is not {TRANSACTION_JOURNAL_SCHEMA}")
    if (
        not isinstance(document["transaction_id"], str)
        or document["transaction_id"] != transaction_root.name
        or not _transaction_name_is_valid(document["transaction_id"])
    ):
        raise IntegrationError(f"{label} transaction identity drifted")
    if document["archive_sha256"] != archive_sha256:
        raise IntegrationError(f"{label} archive identity drifted")
    package = document["package"]
    if not isinstance(package, dict):
        raise IntegrationError(f"{label} package identity must be an object")
    _strict_keys(package, {"name", "version"}, f"{label} package")
    if package != {"name": PACKAGE_NAME, "version": PACKAGE_VERSION}:
        raise IntegrationError(f"{label} package identity drifted")
    if not isinstance(document["recovery_started"], bool):
        raise IntegrationError(f"{label} recovery flag is not boolean")

    created_parents = document["created_parents"]
    allowed_parents = _allowed_managed_parents(allowed_targets)
    if (
        not isinstance(created_parents, list)
        or any(not isinstance(value, str) for value in created_parents)
        or len(created_parents) != len(set(created_parents))
        or any(value not in allowed_parents for value in created_parents)
        or created_parents
        != sorted(
            created_parents,
            key=lambda value: (len(PurePosixPath(value).parts), value),
        )
    ):
        raise IntegrationError(f"{label} created-parent allowlist drifted")

    targets = document["targets"]
    if not isinstance(targets, list) or not targets or len(targets) > len(allowed_targets):
        raise IntegrationError(f"{label} target inventory is invalid")
    seen_destinations: set[str] = set()
    state_ranks: list[int] = []
    for index, record in enumerate(targets):
        target_label = f"{label} target {index}"
        if not isinstance(record, dict):
            raise IntegrationError(f"{target_label} is not an object")
        _strict_keys(
            record,
            {
                "destination",
                "index",
                "kind",
                "original_fingerprint",
                "replace",
                "staged_fingerprint",
                "state",
            },
            target_label,
        )
        if type(record["index"]) is not int or record["index"] != index:
            raise IntegrationError(f"{target_label} index is not canonical")
        destination = record["destination"]
        if (
            not isinstance(destination, str)
            or destination in seen_destinations
            or destination not in allowed_targets
        ):
            raise IntegrationError(f"{target_label} destination is not allowlisted")
        seen_destinations.add(destination)
        kind = record["kind"]
        if (
            not isinstance(kind, str)
            or kind not in {"file", "tree"}
            or allowed_targets[destination] != kind
        ):
            raise IntegrationError(f"{target_label} kind drifted")
        if not isinstance(record["replace"], bool):
            raise IntegrationError(f"{target_label} replace flag is not boolean")
        staged_fingerprint = record["staged_fingerprint"]
        if (
            not isinstance(staged_fingerprint, str)
            or _fingerprint_kind(staged_fingerprint) != kind
        ):
            raise IntegrationError(f"{target_label} staged fingerprint is invalid")
        original_fingerprint = record["original_fingerprint"]
        if record["replace"]:
            if (
                not isinstance(original_fingerprint, str)
                or _fingerprint_kind(original_fingerprint) != kind
            ):
                raise IntegrationError(f"{target_label} original fingerprint is invalid")
        elif original_fingerprint is not None:
            raise IntegrationError(f"{target_label} unexpected original fingerprint")
        state = record["state"]
        if state not in TRANSACTION_STATES:
            raise IntegrationError(f"{target_label} state is invalid")
        state_ranks.append(TRANSACTION_STATES.index(state))

    if any(rank == 3 for rank in state_ranks):
        if any(rank != 3 for rank in state_ranks) or document["recovery_started"]:
            raise IntegrationError(f"{label} VERIFIED state is not transaction-wide")
    elif any(left < right for left, right in zip(state_ranks, state_ranks[1:])):
        raise IntegrationError(f"{label} target states are not a publish prefix")
    return document


def _load_journal_file(
    path: Path,
    *,
    transaction_root: Path,
    archive_sha256: str,
    allowed_targets: Mapping[str, str],
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise IntegrationError(f"transaction journal is missing or unsafe: {path}")
    if stat.S_IMODE(path.lstat().st_mode) != 0o600:
        raise IntegrationError(f"transaction journal mode drifted: {path}")
    document = _strict_json_bytes(
        _read_bounded_regular_file(path, MAX_TRANSACTION_JOURNAL_BYTES, "transaction journal"),
        "transaction journal",
    )
    return _validate_journal_document(
        document,
        transaction_root=transaction_root,
        archive_sha256=archive_sha256,
        allowed_targets=allowed_targets,
    )


def _validate_transaction_layout(
    transaction_root: Path,
    journal: Mapping[str, Any],
    *,
    archive_sha256: str,
    allowed_targets: Mapping[str, str],
) -> None:
    if (
        transaction_root.is_symlink()
        or not transaction_root.is_dir()
        or stat.S_IMODE(transaction_root.lstat().st_mode) != 0o700
    ):
        raise IntegrationError(f"transaction root mode/type drifted: {transaction_root}")
    staged_root = transaction_root / "staged"
    backup_root = transaction_root / "backups"
    for root in (staged_root, backup_root):
        if root.is_symlink() or not root.is_dir() or stat.S_IMODE(root.lstat().st_mode) != 0o755:
            raise IntegrationError(f"transaction directory mode/type drifted: {root}")

    expected_indices = {f"{index:03d}" for index in range(len(journal["targets"]))}
    for root in (staged_root, backup_root):
        with os.scandir(root) as entries:
            for entry in entries:
                if entry.name not in expected_indices or entry.is_symlink():
                    raise IntegrationError(
                        f"unexpected transaction artifact preserved: {Path(entry.path)}"
                    )

    allowed_top_level = {TRANSACTION_JOURNAL_NAME, "staged", "backups"}
    with os.scandir(transaction_root) as entries:
        for entry in entries:
            if entry.name in allowed_top_level:
                continue
            if re.fullmatch(r"\.journal-v1-[A-Za-z0-9_-]+\.tmp", entry.name) is None:
                raise IntegrationError(
                    f"unexpected transaction artifact preserved: {Path(entry.path)}"
                )
            temporary = _load_journal_file(
                Path(entry.path),
                transaction_root=transaction_root,
                archive_sha256=archive_sha256,
                allowed_targets=allowed_targets,
            )
            immutable_fields = (
                "archive_sha256",
                "created_parents",
                "package",
                "schema_version",
                "transaction_id",
            )
            if any(temporary[field] != journal[field] for field in immutable_fields):
                raise IntegrationError(f"temporary transaction journal identity drifted: {entry.path}")
            if len(temporary["targets"]) != len(journal["targets"]):
                raise IntegrationError(
                    f"temporary transaction journal target count drifted: {entry.path}"
                )
            for observed, canonical in zip(
                temporary["targets"], journal["targets"]
            ):
                immutable_target_fields = (
                    "destination",
                    "index",
                    "kind",
                    "original_fingerprint",
                    "replace",
                    "staged_fingerprint",
                )
                if any(observed[field] != canonical[field] for field in immutable_target_fields):
                    raise IntegrationError(
                        f"temporary transaction journal target drifted: {entry.path}"
                    )


def _load_transaction_journal(
    transaction_root: Path,
    *,
    archive_sha256: str,
    allowed_targets: Mapping[str, str],
) -> dict[str, Any]:
    if not _transaction_name_is_valid(transaction_root.name):
        raise IntegrationError(f"transaction name is invalid: {transaction_root}")
    journal = _load_journal_file(
        transaction_root / TRANSACTION_JOURNAL_NAME,
        transaction_root=transaction_root,
        archive_sha256=archive_sha256,
        allowed_targets=allowed_targets,
    )
    _validate_transaction_layout(
        transaction_root,
        journal,
        archive_sha256=archive_sha256,
        allowed_targets=allowed_targets,
    )
    return journal


def _new_journal(
    repo_root: Path,
    transaction_root: Path,
    targets: Sequence[_ManagedTarget],
    archive_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": TRANSACTION_JOURNAL_SCHEMA,
        "package": {"name": PACKAGE_NAME, "version": PACKAGE_VERSION},
        "archive_sha256": archive_sha256,
        "transaction_id": transaction_root.name,
        "recovery_started": False,
        "created_parents": _planned_created_parents(repo_root, targets),
        "targets": [
            {
                "index": index,
                "destination": _repo_relative_destination(repo_root, target.destination),
                "kind": target.kind,
                "replace": target.replace,
                "original_fingerprint": target.original_fingerprint,
                "staged_fingerprint": _payload_fingerprint(target),
                "state": "INTENT",
            }
            for index, target in enumerate(targets)
        ],
    }


def _initialize_transaction(
    repo_root: Path,
    targets: Sequence[_ManagedTarget],
    allowed_targets: Mapping[str, str],
    archive_sha256: str = ARCHIVE_SHA256,
) -> tuple[Path, dict[str, Any]]:
    root = repo_root.resolve()
    transaction_root = Path(tempfile.mkdtemp(prefix=TRANSACTION_PREFIX, dir=root))
    try:
        os.chmod(transaction_root, 0o700)
        _fsync_directory(root)
        staged_root = transaction_root / "staged"
        backup_root = transaction_root / "backups"
        staged_root.mkdir(mode=0o755)
        backup_root.mkdir(mode=0o755)
        _fsync_directory(staged_root)
        _fsync_directory(backup_root)
        _fsync_directory(transaction_root)
        journal = _new_journal(root, transaction_root, targets, archive_sha256)
        _validate_journal_document(
            journal,
            transaction_root=transaction_root,
            archive_sha256=archive_sha256,
            allowed_targets=allowed_targets,
        )
        _write_journal_atomic(transaction_root, journal)
        return transaction_root, journal
    except BaseException:
        shutil.rmtree(transaction_root)
        _fsync_directory(root)
        raise


def _advance_target_state(
    transaction_root: Path,
    journal: dict[str, Any],
    index: int,
    state: str,
) -> None:
    record = journal["targets"][index]
    current = record["state"]
    expected = {
        "BACKED_UP": "INTENT",
        "PUBLISHED": "BACKED_UP",
    }.get(state)
    if expected is None or current != expected or journal["recovery_started"]:
        raise IntegrationError(
            f"invalid transaction state transition for target {index}: {current} -> {state}"
        )
    record["state"] = state
    _write_journal_atomic(transaction_root, journal)


def _mark_transaction_verified(transaction_root: Path, journal: dict[str, Any]) -> None:
    if journal["recovery_started"] or any(
        target["state"] != "PUBLISHED" for target in journal["targets"]
    ):
        raise IntegrationError("transaction cannot be marked VERIFIED before every publish")
    for target in journal["targets"]:
        target["state"] = "VERIFIED"
    _write_journal_atomic(transaction_root, journal)


def _mark_recovery_started(transaction_root: Path, journal: dict[str, Any]) -> None:
    if journal["recovery_started"]:
        return
    if any(target["state"] == "VERIFIED" for target in journal["targets"]):
        raise IntegrationError("a VERIFIED transaction cannot enter rollback recovery")
    journal["recovery_started"] = True
    _write_journal_atomic(transaction_root, journal)


def _transaction_paths(
    repo_root: Path,
    transaction_root: Path,
    record: Mapping[str, Any],
) -> tuple[Path, Path, Path]:
    index = record["index"]
    destination = _resolve_below(repo_root, Path(record["destination"]))
    staged = transaction_root / "staged" / f"{index:03d}"
    backup = transaction_root / "backups" / f"{index:03d}"
    return destination, staged, backup


def _validate_unrecovered_distribution(
    repo_root: Path,
    transaction_root: Path,
    journal: Mapping[str, Any],
) -> None:
    staging_complete = any(
        target["state"] != "INTENT" for target in journal["targets"]
    )
    for record in journal["targets"]:
        destination, staged, backup = _transaction_paths(
            repo_root, transaction_root, record
        )
        destination_fp = _fingerprint_if_present(destination)
        staged_fp = _fingerprint_if_present(staged)
        backup_fp = _fingerprint_if_present(backup)
        expected_staged = record["staged_fingerprint"]
        expected_original = record["original_fingerprint"]
        if staged_fp not in {None, expected_staged}:
            raise IntegrationError(f"staged target changed outside recovery: {staged}")
        if backup_fp not in {None, expected_original}:
            raise IntegrationError(f"backup target changed outside recovery: {backup}")
        if staging_complete and record["state"] == "INTENT" and staged_fp != expected_staged:
            raise IntegrationError(f"staged publish suffix is incomplete: {staged}")

        state = record["state"]
        if record["replace"]:
            distributions = {
                "INTENT": {
                    (expected_original, None, None),
                    (expected_original, expected_staged, None),
                    (None, expected_staged, expected_original),
                },
                "BACKED_UP": {
                    (None, expected_staged, expected_original),
                    (expected_staged, None, expected_original),
                },
                "PUBLISHED": {(expected_staged, None, expected_original)},
            }
        else:
            distributions = {
                "INTENT": {(None, None, None), (None, expected_staged, None)},
                "BACKED_UP": {
                    (None, expected_staged, None),
                    (expected_staged, None, None),
                },
                "PUBLISHED": {(expected_staged, None, None)},
            }
        observed = (destination_fp, staged_fp, backup_fp)
        if observed not in distributions[state]:
            raise IntegrationError(
                f"transaction target changed outside recovery: {record['destination']}"
            )


def _validate_recovery_distribution(
    repo_root: Path,
    transaction_root: Path,
    journal: Mapping[str, Any],
) -> None:
    for record in journal["targets"]:
        destination, staged, backup = _transaction_paths(
            repo_root, transaction_root, record
        )
        destination_fp = _fingerprint_if_present(destination)
        staged_fp = _fingerprint_if_present(staged)
        backup_fp = _fingerprint_if_present(backup)
        expected_staged = record["staged_fingerprint"]
        expected_original = record["original_fingerprint"]
        if staged_fp not in {None, expected_staged}:
            raise IntegrationError(f"staged target changed during recovery: {staged}")
        if record["replace"]:
            if backup_fp not in {None, expected_original}:
                raise IntegrationError(f"backup target changed during recovery: {backup}")
            if backup_fp is None:
                if destination_fp != expected_original:
                    raise IntegrationError(
                        f"original target is not restored: {record['destination']}"
                    )
            elif destination_fp not in {None, expected_staged}:
                raise IntegrationError(
                    f"destination changed during recovery: {record['destination']}"
                )
            if destination_fp == expected_staged and staged_fp == expected_staged:
                raise IntegrationError(
                    f"staged target was duplicated outside recovery: {record['destination']}"
                )
        else:
            if backup_fp is not None or destination_fp not in {None, expected_staged}:
                raise IntegrationError(
                    f"new target changed during recovery: {record['destination']}"
                )
            if destination_fp == expected_staged and staged_fp == expected_staged:
                raise IntegrationError(
                    f"new staged target was duplicated outside recovery: {record['destination']}"
                )


def _validate_committed_distribution(
    repo_root: Path,
    transaction_root: Path,
    journal: Mapping[str, Any],
) -> None:
    for record in journal["targets"]:
        destination, staged, backup = _transaction_paths(
            repo_root, transaction_root, record
        )
        if _fingerprint_if_present(destination) != record["staged_fingerprint"]:
            raise IntegrationError(
                f"VERIFIED destination changed before cleanup: {record['destination']}"
            )
        if _lexists(staged):
            raise IntegrationError(f"VERIFIED staged target unexpectedly remains: {staged}")
        backup_fp = _fingerprint_if_present(backup)
        if record["replace"]:
            if backup_fp not in {None, record["original_fingerprint"]}:
                raise IntegrationError(f"VERIFIED backup changed before cleanup: {backup}")
        elif backup_fp is not None:
            raise IntegrationError(f"VERIFIED new target has an unexpected backup: {backup}")


def _remove_managed_path_durable(path: Path, expected_fingerprint: str) -> None:
    if not _lexists(path) or _path_fingerprint(path) != expected_fingerprint:
        raise IntegrationError(f"refusing to remove changed managed path: {path}")
    _remove_managed_path(path)
    _fsync_directory(path.parent)


def _validate_created_parent_layout(
    repo_root: Path,
    journal: Mapping[str, Any],
) -> None:
    created = set(journal["created_parents"])
    expected_children: dict[str, set[str]] = {relative: set() for relative in created}
    for descendant in (
        *journal["created_parents"],
        *(record["destination"] for record in journal["targets"]),
    ):
        path = PurePosixPath(descendant)
        parent = path.parent.as_posix()
        if parent in expected_children:
            expected_children[parent].add(path.name)
    for relative in journal["created_parents"]:
        path = _resolve_below(repo_root, Path(relative))
        if not _lexists(path):
            continue
        if (
            path.is_symlink()
            or not path.is_dir()
            or stat.S_IMODE(path.lstat().st_mode) != 0o755
        ):
            raise IntegrationError(f"created parent changed during recovery: {path}")
        with os.scandir(path) as entries:
            observed = {entry.name for entry in entries}
        unexpected = observed - expected_children[relative]
        if unexpected:
            raise IntegrationError(
                "created parent received third-party content; transaction preserved: "
                f"{path}: {sorted(unexpected)}"
            )


def _remove_created_parents(repo_root: Path, journal: Mapping[str, Any]) -> None:
    for relative in reversed(journal["created_parents"]):
        path = _resolve_below(repo_root, Path(relative))
        if not _lexists(path):
            continue
        if (
            path.is_symlink()
            or not path.is_dir()
            or stat.S_IMODE(path.lstat().st_mode) != 0o755
        ):
            raise IntegrationError(f"created parent changed during recovery: {path}")
        try:
            path.rmdir()
        except OSError as exc:
            if exc.errno in {errno.ENOTEMPTY, errno.EEXIST}:
                raise IntegrationError(
                    f"created parent received third-party content; transaction preserved: {path}"
                ) from exc
            raise
        _fsync_directory(path.parent)


def _cleanup_transaction(repo_root: Path, transaction_root: Path) -> None:
    root = repo_root.resolve()
    if (
        transaction_root.parent != root
        or not _transaction_name_is_valid(transaction_root.name)
        or transaction_root.is_symlink()
        or not transaction_root.is_dir()
        or stat.S_IMODE(transaction_root.lstat().st_mode) != 0o700
    ):
        raise IntegrationError(f"refusing unsafe transaction cleanup: {transaction_root}")
    # Deliberately do not use ignore_errors: a partial cleanup remains observable
    # and blocks --check / the next writer until it is safely reconciled.
    shutil.rmtree(transaction_root)
    _fsync_directory(root)


def _recover_transaction(
    repo_root: Path,
    transaction_root: Path,
    *,
    archive_sha256: str,
    allowed_targets: Mapping[str, str],
) -> None:
    journal = _load_transaction_journal(
        transaction_root,
        archive_sha256=archive_sha256,
        allowed_targets=allowed_targets,
    )
    if all(target["state"] == "VERIFIED" for target in journal["targets"]):
        _validate_committed_distribution(repo_root, transaction_root, journal)
        _validate_transaction_layout(
            transaction_root,
            journal,
            archive_sha256=archive_sha256,
            allowed_targets=allowed_targets,
        )
        _cleanup_transaction(repo_root, transaction_root)
        return

    if journal["recovery_started"]:
        _validate_recovery_distribution(repo_root, transaction_root, journal)
    else:
        _validate_unrecovered_distribution(repo_root, transaction_root, journal)
        _mark_recovery_started(transaction_root, journal)

    # Validate every path before the first destructive rollback action.  Each
    # individual action rechecks its own fingerprint to close the common race.
    _validate_recovery_distribution(repo_root, transaction_root, journal)
    _validate_created_parent_layout(repo_root, journal)
    for record in reversed(journal["targets"]):
        destination, _staged, backup = _transaction_paths(
            repo_root, transaction_root, record
        )
        destination_fp = _fingerprint_if_present(destination)
        backup_fp = _fingerprint_if_present(backup)
        if record["replace"] and backup_fp is not None:
            if backup_fp != record["original_fingerprint"]:
                raise IntegrationError(f"original backup changed during recovery: {backup}")
            if destination_fp is not None:
                _remove_managed_path_durable(
                    destination, record["staged_fingerprint"]
                )
            if _lexists(destination):
                raise IntegrationError(f"destination reappeared during recovery: {destination}")
            if _path_fingerprint(backup) != record["original_fingerprint"]:
                raise IntegrationError(f"original backup raced recovery: {backup}")
            _durable_replace(backup, destination)
        elif not record["replace"] and destination_fp is not None:
            _remove_managed_path_durable(destination, record["staged_fingerprint"])

    _validate_recovery_distribution(repo_root, transaction_root, journal)
    for record in journal["targets"]:
        destination, _staged, backup = _transaction_paths(
            repo_root, transaction_root, record
        )
        if record["replace"]:
            if (
                _fingerprint_if_present(destination) != record["original_fingerprint"]
                or _lexists(backup)
            ):
                raise IntegrationError(
                    f"original target was not durably restored: {record['destination']}"
                )
        elif _lexists(destination) or _lexists(backup):
            raise IntegrationError(
                f"new target was not durably removed: {record['destination']}"
            )
    _remove_created_parents(repo_root, journal)
    _validate_transaction_layout(
        transaction_root,
        journal,
        archive_sha256=archive_sha256,
        allowed_targets=allowed_targets,
    )
    _cleanup_transaction(repo_root, transaction_root)


def _recover_stale_transactions(
    repo_root: Path,
    *,
    archive_sha256: str,
    allowed_targets: Mapping[str, str],
) -> None:
    stale = _transaction_roots(repo_root)
    if len(stale) > 1:
        raise IntegrationError(
            "multiple stale multimodal-intake transactions are ambiguous and were preserved: "
            + ", ".join(path.name for path in stale)
        )
    for transaction_root in stale:
        try:
            _recover_transaction(
                repo_root,
                transaction_root,
                archive_sha256=archive_sha256,
                allowed_targets=allowed_targets,
            )
        except (IntegrationError, OSError) as exc:
            raise IntegrationError(
                "stale multimodal-intake transaction could not be safely recovered; "
                f"artifacts preserved at {transaction_root}: {exc}"
            ) from exc


def _legacy_skill_payloads(skill: SkillContract) -> Mapping[str, FilePayload]:
    return {
        "SKILL.md": FilePayload(skill.skill_md),
        "references/contract.yaml": FilePayload(skill.contract_yaml),
    }


def _installed_skill_is_legacy_source(
    destination: Path,
    skill: SkillContract,
) -> bool:
    try:
        _assert_tree_matches(
            destination,
            _legacy_skill_payloads(skill),
            f"legacy installed Skill {skill.name}",
        )
        return True
    except IntegrationError:
        return False


def _prepare_expectations(
    repo_root: Path,
    snapshot: PackageSnapshot,
) -> tuple[
    RuntimeSnapshot,
    str,
    str,
    OperationRegistrySnapshot,
    dict[str, FilePayload],
    dict[str, dict[str, FilePayload]],
    FilePayload,
    FilePayload,
]:
    runtime = _runtime_snapshot(repo_root)
    engine_path = _resolve_below(repo_root, ENGINE_RELATIVE_PATH)
    engine_sha256, _registry = _parse_engine_registry(engine_path, snapshot.skills)
    importer_sha256 = _running_importer_sha256()
    operation_registry = _parse_operation_registry(
        _resolve_below(repo_root, OPERATION_REGISTRY_RELATIVE_PATH),
        [skill.name for skill in snapshot.skills],
    )
    _validate_operation_input_schema(
        _resolve_below(
            repo_root,
            ENGINE_ROOT_RELATIVE_PATH
            / "openapi/operation-input-contracts.schema.json",
        ),
        operation_registry,
    )
    source_payloads = _source_payloads(snapshot)
    skill_payloads = _expected_skill_payloads(
        snapshot, runtime, importer_sha256
    )
    compiled_payload = FilePayload(
        _json_bytes(
            _compiled_manifest(
                snapshot,
                engine_sha256,
                runtime,
                skill_payloads,
                importer_sha256,
                operation_registry,
            )
        )
    )
    installed_payload = FilePayload(
        _json_bytes(
            _installed_manifest(
                snapshot,
                runtime,
                compiled_payload.data,
                source_payloads,
                skill_payloads,
            )
        )
    )
    return (
        runtime,
        engine_sha256,
        importer_sha256,
        operation_registry,
        source_payloads,
        skill_payloads,
        compiled_payload,
        installed_payload,
    )


def _verify_expected_integration(
    repo_root: Path,
    snapshot: PackageSnapshot,
    runtime: RuntimeSnapshot,
    engine_sha256: str,
    importer_sha256: str,
    operation_registry: OperationRegistrySnapshot,
    source_payloads: Mapping[str, FilePayload],
    skill_payloads: Mapping[str, Mapping[str, FilePayload]],
    compiled_payload: FilePayload,
    installed_payload: FilePayload,
) -> None:
    _validate_matrix(repo_root, snapshot)
    _assert_tree_matches(
        _resolve_below(repo_root, SOURCE_RELATIVE_PATH),
        source_payloads,
        "immutable source",
    )
    for install_root in INSTALL_ROOTS:
        for skill in snapshot.skills:
            _assert_tree_matches(
                _resolve_below(repo_root, install_root / skill.name),
                skill_payloads[skill.name],
                f"installed Skill {install_root.as_posix()}/{skill.name}",
            )
    if _runtime_snapshot(repo_root) != runtime:
        raise IntegrationError("runtime inventory changed during integration")
    if _running_importer_sha256() != importer_sha256:
        raise IntegrationError("running importer changed during integration")
    if _parse_operation_registry(
        _resolve_below(repo_root, OPERATION_REGISTRY_RELATIVE_PATH),
        [skill.name for skill in snapshot.skills],
    ) != operation_registry:
        raise IntegrationError("operation registry changed during integration")
    _validate_operation_input_schema(
        _resolve_below(
            repo_root,
            ENGINE_ROOT_RELATIVE_PATH
            / "openapi/operation-input-contracts.schema.json",
        ),
        operation_registry,
    )
    observed_engine_sha256, _registry = _parse_engine_registry(
        _resolve_below(repo_root, ENGINE_RELATIVE_PATH), snapshot.skills
    )
    if observed_engine_sha256 != engine_sha256:
        raise IntegrationError("runtime engine changed during integration")
    _assert_file_payload(
        _resolve_below(repo_root, COMPILED_MANIFEST_RELATIVE_PATH),
        compiled_payload,
        "compiled manifest",
    )
    _assert_file_payload(
        _resolve_below(repo_root, INSTALLED_MANIFEST_RELATIVE_PATH),
        installed_payload,
        "installed manifest",
    )


def _managed_manifest_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise IntegrationError(f"{label} is missing or unsafe: {path}")
    if stat.S_IMODE(path.lstat().st_mode) != 0o644:
        raise IntegrationError(f"{label} mode drifted: {path}")
    return _read_bounded_regular_file(path, MAX_MANAGED_JSON_BYTES, label)


def _historical_runtime_records(
    section: Any,
    *,
    label: str,
    allowed_path_sequences: Sequence[tuple[str, ...]],
    includes_execution_status: bool,
) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(section, dict):
        raise IntegrationError(f"{label} must be an object")
    expected_fields = {"aggregate_sha256", "file_count", "files"}
    if includes_execution_status:
        expected_fields.add("execution_status")
    _strict_keys(section, expected_fields, label)
    if includes_execution_status and section["execution_status"] != EXTERNAL_EVIDENCE_STATUS:
        raise IntegrationError(f"{label} execution status drifted")
    records = section["files"]
    if not isinstance(records, list):
        raise IntegrationError(f"{label} files must be a list")
    paths: list[str] = []
    for index, record in enumerate(records):
        record_label = f"{label} file {index}"
        if not isinstance(record, dict):
            raise IntegrationError(f"{record_label} must be an object")
        _strict_keys(record, {"bytes", "mode", "path", "sha256"}, record_label)
        path = record["path"]
        if not isinstance(path, str):
            raise IntegrationError(f"{record_label} path is invalid")
        paths.append(path)
        byte_count = record["bytes"]
        if (
            type(byte_count) is not int
            or byte_count < 0
            or byte_count > MAX_RUNTIME_FILE_BYTES
            or record["mode"] != "0644"
            or not isinstance(record["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None
        ):
            raise IntegrationError(f"{record_label} metadata is invalid")
    if tuple(paths) not in allowed_path_sequences:
        raise IntegrationError(f"{label} path inventory is not a recognized managed closure")
    if type(section["file_count"]) is not int or section["file_count"] != len(records):
        raise IntegrationError(f"{label} file count drifted")
    aggregate = section["aggregate_sha256"]
    if (
        not isinstance(aggregate, str)
        or re.fullmatch(r"[0-9a-f]{64}", aggregate) is None
        or aggregate != _sha256(_json_bytes(records))
    ):
        raise IntegrationError(f"{label} aggregate digest drifted")
    return tuple(records)


def _validate_managed_upgrade_group(
    repo_root: Path,
    snapshot: PackageSnapshot,
    source_payloads: Mapping[str, FilePayload],
    compiled_path: Path,
    installed_path: Path,
) -> dict[str, str]:
    """Prove an older generated group is intact before allowing all-at-once upgrade."""

    compiled_bytes = _managed_manifest_bytes(compiled_path, "old compiled manifest")
    installed_bytes = _managed_manifest_bytes(installed_path, "old installed manifest")
    compiled = _strict_json_bytes(compiled_bytes, "old compiled manifest")
    installed = _strict_json_bytes(installed_bytes, "old installed manifest")
    if not isinstance(compiled, dict) or not isinstance(installed, dict):
        raise IntegrationError("old generated manifests must be JSON objects")
    legacy_compiled_keys = {
        "acceptance_criteria_executed",
        "archive",
        "certification_status",
        "contracts",
        "engine",
        "external_evidence_status",
        "kind",
        "package",
        "runtime",
        "schema_version",
        "skills",
    }
    observed_compiled_keys = set(compiled)
    legacy_generation = observed_compiled_keys == legacy_compiled_keys
    if not legacy_generation:
        _strict_keys(
            compiled,
            legacy_compiled_keys | {"compiler", "operation_registry"},
            "old compiled manifest",
        )
    _strict_keys(
        installed,
        {
            "acceptance_criteria_executed",
            "archive_sha256",
            "certification_status",
            "compiled_manifest_sha256",
            "external_evidence_status",
            "installations",
            "kind",
            "package",
            "runtime",
            "schema_version",
            "source",
        },
        "old installed manifest",
    )
    package_identity = {"name": PACKAGE_NAME, "version": PACKAGE_VERSION}
    if (
        compiled["schema_version"] != "1.0.0"
        or compiled["kind"] != "elmos.multimodal-intake.compiled-manifest"
        or compiled["package"] != package_identity
        or installed["schema_version"] != "1.0.0"
        or installed["kind"] != "elmos.multimodal-intake.installed-manifest"
        or installed["package"] != package_identity
        or installed["archive_sha256"] != snapshot.archive_sha256
    ):
        raise IntegrationError("old generated manifest package identity drifted")
    expected_archive = {
        "path": ARCHIVE_RELATIVE_PATH.as_posix(),
        "sha256": snapshot.archive_sha256,
        "compressed_bytes": EXPECTED_ARCHIVE_BYTES,
        "entries": snapshot.entry_count,
        "uncompressed_bytes": snapshot.uncompressed_bytes,
        "internal_checksums": snapshot.internal_checksum_count,
        "manifest_sha256": snapshot.manifest_sha256,
        "crc32_verified": True,
        "modes_verified": True,
        "case_and_unicode_collisions_rejected": True,
        "archive_scripts_executed": False,
    }
    if compiled["archive"] != expected_archive:
        raise IntegrationError("old compiled manifest archive identity drifted")
    if installed["compiled_manifest_sha256"] != _sha256(compiled_bytes):
        raise IntegrationError("old generated manifests are not digest-bound to each other")

    runtime = compiled["runtime"]
    if not isinstance(runtime, dict):
        raise IntegrationError("old compiled runtime must be an object")
    _strict_keys(runtime, {"implementation", "root", "roots", "tests"}, "old runtime")
    expected_roots = [
        ENGINE_ROOT_RELATIVE_PATH.as_posix(),
        "apps/web-console",
        "tests/multimodal-intake",
    ]
    if runtime["root"] != "." or runtime["roots"] != expected_roots:
        raise IntegrationError("old compiled runtime roots drifted")
    implementation_path_sequences = tuple(
        tuple(
            (ENGINE_ROOT_RELATIVE_PATH / relative).as_posix()
            for relative in engine_files
        )
        + surface_files
        for engine_files in (
            LEGACY_ENGINE_IMPLEMENTATION_FILES_V1,
            LEGACY_ENGINE_IMPLEMENTATION_FILES_V2,
            LEGACY_ENGINE_IMPLEMENTATION_FILES_V3,
            LEGACY_ENGINE_IMPLEMENTATION_FILES_V4,
            ENGINE_IMPLEMENTATION_FILES,
        )
        for surface_files in (
            LEGACY_SURFACE_IMPLEMENTATION_FILES_V1,
            SURFACE_IMPLEMENTATION_FILES,
        )
    )
    recognized_test_path_sequences = tuple(
        tuple(
            (ENGINE_ROOT_RELATIVE_PATH / relative).as_posix()
            for relative in engine_test_files
        )
        + repository_test_files
        for engine_test_files in (
            LEGACY_ENGINE_TEST_FILES_V1,
            ENGINE_TEST_FILES,
        )
        for repository_test_files in (
            LEGACY_REPOSITORY_TEST_FILES_V1,
            REPOSITORY_TEST_FILES,
        )
    )
    implementation_records = _historical_runtime_records(
        runtime["implementation"],
        label="old runtime implementation",
        allowed_path_sequences=implementation_path_sequences,
        includes_execution_status=False,
    )
    test_records = _historical_runtime_records(
        runtime["tests"],
        label="old runtime tests",
        allowed_path_sequences=recognized_test_path_sequences,
        includes_execution_status=True,
    )
    engine = compiled["engine"]
    if not isinstance(engine, dict):
        raise IntegrationError("old compiled engine must be an object")
    _strict_keys(
        engine,
        {"handler_count", "path", "registry", "sha256"},
        "old compiled engine",
    )
    engine_sha256 = engine["sha256"]
    if (
        engine["path"] != ENGINE_RELATIVE_PATH.as_posix()
        or engine["registry"] != "SKILL_REGISTRY"
        or engine["handler_count"] != EXPECTED_SKILL_COUNT
        or not isinstance(engine_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", engine_sha256) is None
    ):
        raise IntegrationError("old compiled engine identity drifted")
    engine_record = next(
        (
            record
            for record in implementation_records
            if record["path"] == ENGINE_RELATIVE_PATH.as_posix()
        ),
        None,
    )
    if engine_record is None or engine_record["sha256"] != engine_sha256:
        raise IntegrationError("old compiled engine is not bound to its runtime inventory")

    old_importer_sha256: str | None = None
    old_operation_registry: OperationRegistrySnapshot | None = None
    if not legacy_generation:
        compiler = compiled["compiler"]
        if not isinstance(compiler, dict):
            raise IntegrationError("old compiled compiler must be an object")
        _strict_keys(compiler, {"path", "sha256"}, "old compiled compiler")
        compiler_sha256 = compiler["sha256"]
        if (
            compiler["path"] != IMPORTER_RELATIVE_PATH.as_posix()
            or not isinstance(compiler_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", compiler_sha256) is None
        ):
            raise IntegrationError("old compiled compiler identity drifted")

        registry = compiled["operation_registry"]
        if not isinstance(registry, dict):
            raise IntegrationError("old compiled operation registry must be an object")
        _strict_keys(
            registry,
            {
                "document_sha256",
                "operation_count",
                "path",
                "schema_version",
                "skill_count",
                "skills",
                "source_sha256",
                "static_ast_validated",
            },
            "old compiled operation registry",
        )
        expected_skill_names = tuple(sorted(skill.name for skill in snapshot.skills))
        registry_skill_names = registry["skills"]
        registry_source_sha256 = registry["source_sha256"]
        if (
            registry["path"] != OPERATION_REGISTRY_RELATIVE_PATH.as_posix()
            or registry["schema_version"] != EXPECTED_OPERATION_REGISTRY_SCHEMA
            or type(registry["skill_count"]) is not int
            or registry["skill_count"] != EXPECTED_SKILL_COUNT
            or not isinstance(registry_skill_names, list)
            or tuple(registry_skill_names) != expected_skill_names
            or type(registry["operation_count"]) is not int
            or registry["operation_count"] != EXPECTED_OPERATION_COUNT
            or registry["document_sha256"] != EXPECTED_OPERATION_REGISTRY_DIGEST
            or registry["static_ast_validated"] is not True
            or not isinstance(registry_source_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", registry_source_sha256) is None
        ):
            raise IntegrationError("old compiled operation registry identity drifted")
        operation_record = next(
            (
                record
                for record in implementation_records
                if record["path"] == OPERATION_REGISTRY_RELATIVE_PATH.as_posix()
            ),
            None,
        )
        if operation_record is None or operation_record["sha256"] != registry_source_sha256:
            raise IntegrationError(
                "old compiled operation registry is not bound to its runtime inventory"
            )
        old_importer_sha256 = compiler_sha256
        old_operation_registry = OperationRegistrySnapshot(
            schema_version=EXPECTED_OPERATION_REGISTRY_SCHEMA,
            source_sha256=registry_source_sha256,
            skill_names=expected_skill_names,
            operation_count=EXPECTED_OPERATION_COUNT,
            document_sha256=EXPECTED_OPERATION_REGISTRY_DIGEST,
            operations=(),
        )

    old_runtime = RuntimeSnapshot(
        implementation_files=implementation_records,
        test_files=test_records,
        implementation_sha256=runtime["implementation"]["aggregate_sha256"],
        tests_sha256=runtime["tests"]["aggregate_sha256"],
    )
    old_skill_payloads = _expected_skill_payloads(
        snapshot, old_runtime, old_importer_sha256
    )
    expected_compiled_bytes = _json_bytes(
        _compiled_manifest(
            snapshot,
            engine_sha256,
            old_runtime,
            old_skill_payloads,
            old_importer_sha256,
            old_operation_registry,
        )
    )
    if compiled_bytes != expected_compiled_bytes:
        raise IntegrationError("old compiled manifest is not an exact generated artifact")
    expected_installed_bytes = _json_bytes(
        _installed_manifest(
            snapshot,
            old_runtime,
            compiled_bytes,
            source_payloads,
            old_skill_payloads,
        )
    )
    if installed_bytes != expected_installed_bytes:
        raise IntegrationError("old installed manifest is not an exact generated artifact")

    original_fingerprints = {
        COMPILED_MANIFEST_RELATIVE_PATH.as_posix(): (
            f"F:0644:{len(compiled_bytes)}:{_sha256(compiled_bytes)}"
        ),
        INSTALLED_MANIFEST_RELATIVE_PATH.as_posix(): (
            f"F:0644:{len(installed_bytes)}:{_sha256(installed_bytes)}"
        ),
    }
    for install_root in INSTALL_ROOTS:
        for skill in snapshot.skills:
            _assert_tree_matches(
                _resolve_below(repo_root, install_root / skill.name),
                old_skill_payloads[skill.name],
                f"old managed Skill {install_root.as_posix()}/{skill.name}",
            )
            original_fingerprints[(install_root / skill.name).as_posix()] = (
                f"D:{_payload_tree_digest(old_skill_payloads[skill.name])}"
            )
    return original_fingerprints


def _preflight_targets(
    repo_root: Path,
    snapshot: PackageSnapshot,
    source_payloads: Mapping[str, FilePayload],
    skill_payloads: Mapping[str, Mapping[str, FilePayload]],
    compiled_payload: FilePayload,
    installed_payload: FilePayload,
) -> list[_ManagedTarget]:
    targets: list[_ManagedTarget] = []
    source_root = _resolve_below(repo_root, SOURCE_RELATIVE_PATH)
    if _lexists(source_root):
        _assert_tree_matches(source_root, source_payloads, "immutable source")
    else:
        targets.append(
            _ManagedTarget(source_root, "tree", source_payloads, False, None, "source")
        )

    compiled_path = _resolve_below(repo_root, COMPILED_MANIFEST_RELATIVE_PATH)
    installed_path = _resolve_below(repo_root, INSTALLED_MANIFEST_RELATIVE_PATH)
    compiled_exists = _lexists(compiled_path)
    installed_exists = _lexists(installed_path)
    if compiled_exists != installed_exists:
        raise IntegrationError(
            "refusing a partial or unowned generated-manifest pair",
            code="MULTIMODAL_MANAGED_DRIFT",
        )
    managed_upgrade_fingerprints: dict[str, str] | None = None
    manifests_current = False
    if compiled_exists:
        compiled_current = installed_current = False
        try:
            _assert_file_payload(compiled_path, compiled_payload, "compiled manifest")
            compiled_current = True
        except IntegrationError:
            pass
        try:
            _assert_file_payload(installed_path, installed_payload, "installed manifest")
            installed_current = True
        except IntegrationError:
            pass
        manifests_current = compiled_current and installed_current
        if not manifests_current:
            try:
                managed_upgrade_fingerprints = _validate_managed_upgrade_group(
                    repo_root,
                    snapshot,
                    source_payloads,
                    compiled_path,
                    installed_path,
                )
            except (IntegrationError, KeyError, TypeError, ValueError) as exc:
                raise IntegrationError(
                    "refusing to overwrite drifted generated manifests or managed Skills"
                ) from exc

    for install_root in INSTALL_ROOTS:
        for skill in snapshot.skills:
            destination = _resolve_below(repo_root, install_root / skill.name)
            expected = skill_payloads[skill.name]
            if not _lexists(destination):
                if managed_upgrade_fingerprints is not None:
                    raise IntegrationError(
                        f"managed Skill disappeared after upgrade validation: {destination}"
                    )
                targets.append(
                    _ManagedTarget(
                        destination, "tree", expected, False, None, f"installed Skill {skill.name}"
                    )
                )
                continue
            try:
                _assert_tree_matches(destination, expected, f"installed Skill {skill.name}")
                continue
            except IntegrationError:
                if (
                    manifests_current
                    or managed_upgrade_fingerprints is None
                    and not _installed_skill_is_legacy_source(destination, skill)
                ):
                    raise IntegrationError(
                        f"refusing to overwrite unowned or drifted installed Skill: {destination}",
                        code="MULTIMODAL_MANAGED_DRIFT",
                    )
            if managed_upgrade_fingerprints is not None:
                relative_destination = (install_root / skill.name).as_posix()
                original_fingerprint = managed_upgrade_fingerprints[relative_destination]
                if _path_fingerprint(destination) != original_fingerprint:
                    raise IntegrationError(
                        f"managed Skill changed after upgrade validation: {destination}"
                    )
            else:
                original_fingerprint = _path_fingerprint(destination)
            targets.append(
                _ManagedTarget(
                    destination,
                    "tree",
                    expected,
                    True,
                    original_fingerprint,
                    f"installed Skill {skill.name}",
                )
            )

    if not compiled_exists:
        targets.extend(
            [
                _ManagedTarget(
                    compiled_path, "file", compiled_payload, False, None, "compiled manifest"
                ),
                _ManagedTarget(
                    installed_path, "file", installed_payload, False, None, "installed manifest"
                ),
            ]
        )
    elif managed_upgrade_fingerprints is not None:
        compiled_original = managed_upgrade_fingerprints[
            COMPILED_MANIFEST_RELATIVE_PATH.as_posix()
        ]
        installed_original = managed_upgrade_fingerprints[
            INSTALLED_MANIFEST_RELATIVE_PATH.as_posix()
        ]
        if (
            _path_fingerprint(compiled_path) != compiled_original
            or _path_fingerprint(installed_path) != installed_original
        ):
            raise IntegrationError("generated manifests changed after upgrade validation")
        targets.extend(
            [
                _ManagedTarget(
                    compiled_path,
                    "file",
                    compiled_payload,
                    True,
                    compiled_original,
                    "compiled manifest",
                ),
                _ManagedTarget(
                    installed_path,
                    "file",
                    installed_payload,
                    True,
                    installed_original,
                    "installed manifest",
                ),
            ]
        )
    return targets


def _ensure_parent_directories(
    path: Path,
    repo_root: Path,
    planned_created_parents: set[str],
    created_by_transaction: set[str],
) -> None:
    missing: list[Path] = []
    cursor = path.parent
    while cursor != repo_root and not _lexists(cursor):
        missing.append(cursor)
        cursor = cursor.parent
    if cursor.is_symlink() or not cursor.is_dir():
        raise IntegrationError(f"managed destination parent is unsafe: {cursor}")
    for directory in reversed(missing):
        relative = directory.relative_to(repo_root).as_posix()
        if relative not in planned_created_parents:
            raise IntegrationError(
                f"unplanned managed destination parent disappeared: {directory}"
            )
        directory.mkdir(mode=0o755)
        os.chmod(directory, 0o755)
        _fsync_directory(directory)
        _fsync_directory(directory.parent)
        created_by_transaction.add(relative)

    cursor = path.parent
    while cursor != repo_root:
        relative = cursor.relative_to(repo_root).as_posix()
        if (
            relative in planned_created_parents
            and relative not in created_by_transaction
        ):
            raise IntegrationError(
                f"planned parent appeared outside this transaction: {cursor}"
            )
        if cursor.is_symlink() or not cursor.is_dir():
            raise IntegrationError(f"managed destination parent is unsafe: {cursor}")
        cursor = cursor.parent


def _remove_managed_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _apply_transaction(
    repo_root: Path,
    targets: Sequence[_ManagedTarget],
    verify: Callable[[], None],
    failure_injector: Callable[[str, int, Path], None] | None,
    *,
    archive_sha256: str = ARCHIVE_SHA256,
    allowed_targets: Mapping[str, str] | None = None,
) -> None:
    if not targets:
        verify()
        return
    root = repo_root.resolve()
    if allowed_targets is None:
        allowed_targets = {
            _repo_relative_destination(root, target.destination): target.kind
            for target in targets
        }
    transaction_root, journal = _initialize_transaction(
        root,
        targets,
        allowed_targets,
        archive_sha256,
    )
    staged_root = transaction_root / "staged"
    backup_root = transaction_root / "backups"
    staged: list[Path] = []
    planned_created_parents = set(journal["created_parents"])
    created_by_transaction: set[str] = set()
    try:
        if failure_injector is not None:
            failure_injector("after_intent", -1, transaction_root)
        for index, target in enumerate(targets):
            staged_path = staged_root / f"{index:03d}"
            if target.kind == "tree":
                _write_payload_tree(staged_path, target.payload)
                _fsync_tree_directories(staged_path)
            elif target.kind == "file":
                _write_payload_file(staged_path, target.payload)
                _assert_file_payload(staged_path, target.payload, f"staged {target.label}")
            else:
                raise IntegrationError(f"unknown managed target kind: {target.kind}")
            _fsync_directory(staged_path.parent)
            staged.append(staged_path)
            if _path_fingerprint(staged_path) != journal["targets"][index]["staged_fingerprint"]:
                raise IntegrationError(f"staged target fingerprint drifted: {target.label}")
            if failure_injector is not None:
                failure_injector("after_stage", index, target.destination)

        for index, (target, staged_path) in enumerate(zip(targets, staged, strict=True)):
            staged_fingerprint = journal["targets"][index]["staged_fingerprint"]
            if failure_injector is not None:
                failure_injector("before_commit", index, target.destination)
            _ensure_parent_directories(
                target.destination,
                root,
                planned_created_parents,
                created_by_transaction,
            )
            if target.replace:
                if (
                    not _lexists(target.destination)
                    or _path_fingerprint(target.destination) != target.original_fingerprint
                ):
                    raise IntegrationError(f"managed destination changed after preflight: {target.destination}")
                backup = backup_root / f"{index:03d}"
                _durable_replace(target.destination, backup)
                if failure_injector is not None:
                    failure_injector("after_backup", index, target.destination)
            else:
                if _lexists(target.destination):
                    raise IntegrationError(f"managed destination appeared after preflight: {target.destination}")
            _advance_target_state(transaction_root, journal, index, "BACKED_UP")
            if failure_injector is not None:
                failure_injector("after_backup_journal", index, target.destination)
            if _path_fingerprint(staged_path) != staged_fingerprint:
                raise IntegrationError(f"staged target changed before publish: {target.destination}")
            _durable_replace(staged_path, target.destination)
            if failure_injector is not None:
                failure_injector("after_publish", index, target.destination)
            _advance_target_state(transaction_root, journal, index, "PUBLISHED")
            if failure_injector is not None:
                failure_injector("after_commit", index, target.destination)
        verify()
        if failure_injector is not None:
            failure_injector("after_verify", len(targets) - 1, transaction_root)
        for index, target in enumerate(targets):
            if (
                _path_fingerprint(target.destination)
                != journal["targets"][index]["staged_fingerprint"]
            ):
                raise IntegrationError(
                    f"managed destination changed after verification: {target.destination}"
                )
        _mark_transaction_verified(transaction_root, journal)
        if failure_injector is not None:
            failure_injector("after_verified", len(targets) - 1, transaction_root)
    except BaseException as exc:
        try:
            _recover_transaction(
                root,
                transaction_root,
                archive_sha256=archive_sha256,
                allowed_targets=allowed_targets,
            )
        except (IntegrationError, OSError) as rollback_exc:
            raise IntegrationError(
                "integration failed and rollback was incomplete; "
                f"recovery artifacts preserved at {transaction_root}: {rollback_exc}"
            ) from exc
        raise
    _recover_transaction(
        root,
        transaction_root,
        archive_sha256=archive_sha256,
        allowed_targets=allowed_targets,
    )


def write_integration(
    repo_root: Path,
    archive_path: Path,
    *,
    _failure_injector: Callable[[str, int, Path], None] | None = None,
) -> PackageSnapshot:
    root = repo_root.resolve()
    with _writer_lock(root):
        snapshot = validate_archive(archive_path)
        _validate_matrix(root, snapshot)
        (
            runtime,
            engine_sha256,
            importer_sha256,
            operation_registry,
            source_payloads,
            skill_payloads,
            compiled_payload,
            installed_payload,
        ) = _prepare_expectations(root, snapshot)
        allowed_targets = _allowed_managed_targets(snapshot)
        _recover_stale_transactions(
            root,
            archive_sha256=snapshot.archive_sha256,
            allowed_targets=allowed_targets,
        )
        targets = _preflight_targets(
            root,
            snapshot,
            source_payloads,
            skill_payloads,
            compiled_payload,
            installed_payload,
        )
        _apply_transaction(
            root,
            targets,
            lambda: _verify_expected_integration(
                root,
                snapshot,
                runtime,
                engine_sha256,
                importer_sha256,
                operation_registry,
                source_payloads,
                skill_payloads,
                compiled_payload,
                installed_payload,
            ),
            _failure_injector,
            archive_sha256=snapshot.archive_sha256,
            allowed_targets=allowed_targets,
        )
        return snapshot


def check_integration(repo_root: Path, archive_path: Path) -> PackageSnapshot:
    root = repo_root.resolve()
    with _check_lock(root):
        _assert_no_stale_transactions(root)
        snapshot = validate_archive(archive_path)
        _validate_matrix(root, snapshot)
        (
            runtime,
            engine_sha256,
            importer_sha256,
            operation_registry,
            source_payloads,
            skill_payloads,
            compiled_payload,
            installed_payload,
        ) = _prepare_expectations(root, snapshot)
        _verify_expected_integration(
            root,
            snapshot,
            runtime,
            engine_sha256,
            importer_sha256,
            operation_registry,
            source_payloads,
            skill_payloads,
            compiled_payload,
            installed_payload,
        )
        return snapshot


def _summary(snapshot: PackageSnapshot, mode: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "package": f"{PACKAGE_NAME}@{PACKAGE_VERSION}",
        "archive_sha256": snapshot.archive_sha256,
        "compressed_bytes": EXPECTED_ARCHIVE_BYTES,
        "entries": snapshot.entry_count,
        "uncompressed_bytes": snapshot.uncompressed_bytes,
        "internal_checksums": snapshot.internal_checksum_count,
        "skills": len(snapshot.skills),
        "acceptance": sum(len(skill.acceptance_ids) for skill in snapshot.skills),
        "deliverables": sum(len(skill.deliverables) for skill in snapshot.skills),
        "global_gates": len(snapshot.global_gate_ids),
        "cyclic_sccs": [list(component) for component in snapshot.dependency_sccs],
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification_status": CERTIFICATION_STATUS,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="validate identity and drift only")
    mode.add_argument("--write", action="store_true", help="safely extract/install and write manifests")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to this script's repository)",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=None,
        help="pinned ZIP path (defaults below --repo-root)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    repo_root = arguments.repo_root.resolve()
    archive_path = (
        Path(os.path.abspath(os.fspath(arguments.archive)))
        if arguments.archive is not None
        else _resolve_below(repo_root, ARCHIVE_RELATIVE_PATH)
    )
    try:
        snapshot = (
            write_integration(repo_root, archive_path)
            if arguments.write
            else check_integration(repo_root, archive_path)
        )
    except IntegrationError as exc:
        print(f"ERROR[{exc.code}]: {exc}", file=sys.stderr)
        return 1
    except (OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR[MULTIMODAL_INTEGRATION_IO_ERROR]: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(_summary(snapshot, "write" if arguments.write else "check"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

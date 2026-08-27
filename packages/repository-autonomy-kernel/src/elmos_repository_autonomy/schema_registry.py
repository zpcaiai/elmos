"""Runtime registry for the 20 package resource schemas.

The upstream JSON schemas are intentionally permissive about resource payload
values, but the registry still enforces object shape, known fields and the
content digest of each validated value. It is the common boundary used by
handlers rather than a collection of unchecked dictionaries.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import ContractError
from .models import digest, require_mapping

SCHEMA_NAMES = (
    "acceptance-decision", "artifact", "capability-package", "checkpoint", "evidence",
    "execution-authority", "finding", "lease", "policy-decision", "repository-snapshot",
    "run-event", "run", "semantic-index", "semantic-ir", "spec-delta", "step",
    "task-spec", "tool-call", "tool-descriptor", "validation-result",
)

KNOWN_FIELDS: dict[str, frozenset[str]] = {
    "run": frozenset({"run_id", "tenant_id", "account_id", "task_spec_hash", "workflow_version", "repo_snapshot_sha", "state", "payload", "idempotency_key", "created_at", "updated_at"}),
    "step": frozenset({"run_id", "step_id", "step_type", "step_version", "state", "attempt_no", "input_artifact_hashes", "output_artifact_hashes", "error", "started_at", "finished_at", "wall_clock_ms"}),
    "run-event": frozenset({"run_id", "sequence_no", "event_id", "event_type", "payload", "occurred_at"}),
    "checkpoint": frozenset({"checkpoint_id", "run_id", "step_id", "state_snapshot", "side_effect_cursor", "content_hash", "created_at"}),
    "lease": frozenset({"lease_id", "resource_type", "resource_id", "owner_id", "fencing_token", "state", "acquired_at", "heartbeat_at", "expires_at", "released_at"}),
    "artifact": frozenset({"artifact_id", "tenant_id", "run_id", "kind", "content_hash", "storage_uri", "media_type", "size_bytes", "repo_snapshot_sha", "producer", "metadata", "created_at"}),
    "evidence": frozenset({"evidence_id", "tenant_id", "run_id", "claim", "evidence_type", "source", "confidence", "repo_snapshot_sha", "captured_at", "expires_at"}),
    "execution-authority": frozenset({"environment_id", "workspace_id", "permission_profile_id", "policy_snapshot_hash", "fencing_token", "allowed_tools", "network_scopes", "secret_scopes"}),
    "policy-decision": frozenset({"decision_id", "tenant_id", "run_id", "event_type", "decision", "reason", "policy_snapshot_hash", "evidence_ids", "decided_at"}),
    "tool-call": frozenset({"tool_call_id", "tenant_id", "run_id", "step_id", "tool_id", "tool_version", "state", "input_hash", "idempotency_key", "result", "error", "created_at"}),
    "tool-descriptor": frozenset({"tool_id", "version", "input_schema", "output_schema", "side_effects", "idempotency_required", "allowed_operations"}),
    "validation-result": frozenset({"validation_id", "tenant_id", "run_id", "validator_id", "validator_version", "status", "metrics", "started_at", "finished_at"}),
    "finding": frozenset({"finding_id", "tenant_id", "run_id", "category", "severity", "confidence", "description", "location", "evidence_ids", "reproducer", "status", "validated_by", "created_at"}),
    "acceptance-decision": frozenset({"acceptance_decision_id", "tenant_id", "run_id", "decision", "gate_results", "release_artifact_ids", "rollback_artifact_ids", "deployment_complete", "decided_by", "decided_at"}),
    "repository-snapshot": frozenset({"snapshot_id", "tenant_id", "repo_uri", "base_commit_sha", "content_hash", "profile", "captured_at"}),
    "semantic-index": frozenset({"index_id", "tenant_id", "snapshot_id", "version", "artifact_id", "quality", "created_at"}),
    "semantic-ir": frozenset({"version", "snapshot_sha", "task_spec_hash", "source_profile", "target_profile", "nodes", "unknown_semantics", "status"}),
    "task-spec": frozenset({"id", "version", "hash", "objective", "non_goals", "constraints", "deliverables", "acceptance_criteria", "risk", "repository_snapshot_sha", "requirements_hash", "immutable"}),
    "spec-delta": frozenset({"base_hash", "candidate_hash", "changed_fields", "affected_nodes", "cache_invalidation", "status"}),
    "capability-package": frozenset({"package_id", "name", "version", "content_hash", "manifest", "signature", "state", "created_at"}),
}


@dataclass(frozen=True, slots=True)
class SchemaValidation:
    schema: str
    valid: bool
    value_hash: str
    unknown_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "valid": self.valid, "value_hash": self.value_hash, "unknown_fields": list(self.unknown_fields)}


class SchemaRegistry:
    def __init__(self) -> None:
        self.schemas = frozenset(SCHEMA_NAMES)

    def validate(self, schema: str, value: Mapping[str, Any]) -> SchemaValidation:
        if schema not in self.schemas:
            raise ContractError("SCHEMA_MISMATCH", f"unknown schema: {schema}")
        mapping = require_mapping(value, schema)
        unknown = tuple(sorted(set(mapping) - KNOWN_FIELDS.get(schema, frozenset())))
        if unknown:
            raise ContractError("SCHEMA_MISMATCH", f"unknown fields for {schema}: {unknown}")
        return SchemaValidation(schema, True, digest(mapping), unknown)

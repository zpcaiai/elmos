"""Pinned v1.2 parity Schema and OpenAPI asset integration."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import jsonschema  # type: ignore[import-untyped]
import pytest

from elmos_build_cache import schemas
from elmos_build_cache.context_ledger import ContextEventType, ContextLedgerEvent
from elmos_build_cache.errors import SchemaInvalid
from elmos_build_cache.parity_api import _context_event_document

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_REFERENCES = (
    REPOSITORY_ROOT
    / "agent-skills/packages/elmos-build-cache-staging-codex-claude-parity/references"
)
REPOSITORY_SCHEMAS = ENGINE_ROOT / "schemas"
PACKAGED_DATA = ENGINE_ROOT / "src/elmos_build_cache/_data"

PARITY_SCHEMA_NAMES = (
    "cache-affinity-decision",
    "cache-outcome-event",
    "cache-parity-report",
    "cache-slo-policy",
    "context-checkpoint",
    "context-ledger-event",
    "environment-snapshot",
    "prompt-prefix-manifest",
    "provider-cache-profile",
)

DIGEST = "sha256:" + "a" * 64

VALID_DOCUMENTS: dict[str, dict[str, object]] = {
    "cache-affinity-decision": {
        "schema_version": "1.2.0",
        "decision_id": "decision-1",
        "affinity_key": DIGEST,
        "request_id": "request-1",
        "selected_target": "worker-1",
        "candidates": [{"target_id": "worker-1", "compatible": True, "score": 1.0}],
        "reason_codes": ["PREFIX_LOCAL"],
    },
    "cache-outcome-event": {
        "schema_version": "1.2.0",
        "event_id": "event-1",
        "request_id": "request-1",
        "layer": "ACTION",
        "outcome": "HIT",
        "reason_code": "EXACT_ACTION_RESULT",
        "eligible": True,
        "occurred_at": "2026-08-20T00:00:00Z",
    },
    "cache-parity-report": {
        "schema_version": "1.2.0",
        "report_id": "report-1",
        "subject": {
            "source_digest": DIGEST,
            "config_digest": DIGEST,
            "corpus_digest": DIGEST,
        },
        "thresholds": {},
        "metrics": {},
        "scenario_results": [{"scenario_id": "exact-rerun", "passed": True, "metrics": {}}],
        "mandatory_pass": True,
        "false_hits": 0,
    },
    "cache-slo-policy": {
        "schema_version": "1.2.0",
        "policy_id": "parity-default",
        "targets": {
            "stable_turn_cached_token_reuse_min": 0.9,
            "unexpected_full_prefix_miss_max": 0.02,
            "exact_rerun_weighted_reuse_min": 0.99,
            "small_edit_weighted_reuse_min": 0.9,
            "environment_snapshot_hit_min": 0.95,
            "restart_artifact_reuse_min": 0.999,
            "false_hits_max": 0,
        },
        "error_budgets": {},
        "rollback": {"automatic": True, "safe_baseline_id": "v1.1-safe"},
    },
    "context-checkpoint": {
        "schema_version": "1.2.0",
        "checkpoint_id": "checkpoint-1",
        "stream_id": "stream-1",
        "ledger_sequence": 1,
        "repository_snapshot_digest": DIGEST,
        "sections": {
            "task_contract": {},
            "repository_state": {},
            "decisions": [],
            "unresolved": [],
            "run_state": {},
            "validation": {},
        },
        "checkpoint_digest": DIGEST,
    },
    "context-ledger-event": {
        "schema_version": "1.2.0",
        "stream_id": "stream-1",
        "sequence": 1,
        "event_id": "event-1",
        "event_type": "SNAPSHOT_BOUND",
        "occurred_at": "2026-08-20T00:00:00Z",
        "payload_digest": DIGEST,
        "previous_event_digest": None,
        "event_digest": DIGEST,
    },
    "environment-snapshot": {
        "schema_version": "1.2.0",
        "snapshot_id": "snapshot-1",
        "snapshot_key": DIGEST,
        "platform": {"os": "linux", "arch": "arm64"},
        "layers": [{"layer_type": "BASE", "digest": DIGEST, "size_bytes": 1}],
        "trust_namespace": "tenant/project/toolchain",
        "status": "AVAILABLE",
    },
    "prompt-prefix-manifest": {
        "schema_version": "1.2.0",
        "manifest_id": "manifest-1",
        "provider_namespace": "openai/project-1",
        "compatibility_group": "provider-model-effort-tools-v1",
        "segments": [
            {
                "segment_id": "system-policy",
                "stability_class": "GLOBAL_STABLE",
                "digest": DIGEST,
                "byte_length": 1,
            }
        ],
        "stable_prefix_digest": DIGEST,
    },
    "provider-cache-profile": {
        "schema_version": "1.2.0",
        "profile_id": "openai-profile-1",
        "provider": "openai",
        "capabilities": {
            "exact_prefix": True,
            "usage_counters": True,
            "routing_key": True,
        },
    },
}


def _declared_components(text: str) -> set[tuple[str, str]]:
    """Component names declared under ``components:``, keyed by section.

    PyYAML is not a dependency of this engine, so the overlay is read with the
    same indentation-anchored scanning the rest of this module uses.
    """

    body = text.split("\ncomponents:\n", 1)[1].split("\npaths:\n", 1)[0]
    declared: set[tuple[str, str]] = set()
    section: str | None = None
    for line in body.splitlines():
        if re.fullmatch(r"  [A-Za-z][A-Za-z0-9_]*:", line):
            section = line.strip().rstrip(":")
        elif section is not None and re.fullmatch(r"    [A-Za-z][A-Za-z0-9_]*:", line):
            declared.add((section, line.strip().rstrip(":")))
    return declared


def test_schema_registry_is_the_closed_on_disk_inventory() -> None:
    on_disk = {
        path.name.removesuffix(".schema.json"): path.name
        for path in REPOSITORY_SCHEMAS.glob("*.schema.json")
    }
    assert schemas.SCHEMA_NAMES == dict(sorted(on_disk.items()))
    assert set(PARITY_SCHEMA_NAMES) <= set(schemas.SCHEMA_NAMES)


@pytest.mark.parametrize("name", PARITY_SCHEMA_NAMES)
def test_parity_schema_is_exact_packaged_and_meta_schema_valid(name: str) -> None:
    filename = f"{name}.schema.json"
    source = (PACKAGE_REFERENCES / "schemas" / filename).read_bytes()
    repository = (REPOSITORY_SCHEMAS / filename).read_bytes()
    packaged = (PACKAGED_DATA / "schemas" / filename).read_bytes()

    assert repository == packaged == source
    document = schemas.load_schema(name)
    jsonschema.Draft202012Validator.check_schema(document)


@pytest.mark.parametrize("name", PARITY_SCHEMA_NAMES)
def test_representative_parity_documents_validate_and_version_drift_fails(name: str) -> None:
    valid = VALID_DOCUMENTS[name]
    schemas.validate(name, valid)

    invalid = copy.deepcopy(valid)
    invalid["schema_version"] = "1.1.0"
    with pytest.raises(SchemaInvalid, match=f"{name} document is invalid"):
        schemas.validate(name, invalid)


def test_parity_openapi_production_overlay_is_exact_and_all_local_refs_resolve() -> None:
    filename = "cache-parity-control-plane.openapi.yaml"
    source = (PACKAGE_REFERENCES / "openapi" / filename).read_bytes()
    repository = ENGINE_ROOT / "openapi" / filename
    packaged = PACKAGED_DATA / "openapi" / filename
    overlay = repository.read_bytes()

    # The immutable source package is an input/reference, not the deployed API
    # authority.  Its draft reuses a completed ledger-event schema as an append
    # request and omits idempotency parameters from several mutations.  The
    # engine therefore owns a fail-closed production overlay while retaining a
    # pinned digest for the unmodified source document.
    assert hashlib.sha256(source).hexdigest() == (
        "eb9e0bcd65cb7094ae9b31fe6974176e71ef091ab9c7e0fd2881fc0e3bbf0462"
    )
    assert overlay == packaged.read_bytes()
    assert overlay != source

    overlay_text = overlay.decode("utf-8")
    assert "ContextAppendRequest:" in overlay_text
    assert "ContextLedgerEventResponse:" in overlay_text
    assert "schema: { $ref: '#/components/schemas/ContextAppendRequest' }" in overlay_text
    assert overlay_text.count(
        "schema: { $ref: '#/components/schemas/ContextLedgerEventResponse' }"
    ) == 2
    # One reference per mutating operation: compile, context append, affinity,
    # parity run, provider prompt preparation, provider cache usage.
    assert overlay_text.count("#/components/parameters/IdempotencyKey") == 6
    assert "provider_execution_performed: { type: boolean, const: false }" in overlay_text
    assert "certified: { type: boolean, const: false }" in overlay_text
    # The affinity transport speaks the runtime provider vocabulary.  The
    # immutable source package's provider-profile schema uses ``self_hosted``
    # for its own document type, but that spelling must not leak into this
    # request and become an input the runtime cannot parse.
    assert "enum: [openai, anthropic, self-hosted]" in overlay_text
    assert "enum: [openai, anthropic, self_hosted]" not in overlay_text
    assert "security:\n  - gatewayMutualTLS: []" in overlay_text
    assert "type: mutualTLS" in overlay_text

    reference_pattern = re.compile(r"\$ref:\s*[\"']?([^\"'\s}]+)")
    for document in (repository, packaged):
        text = document.read_text(encoding="utf-8")
        references = reference_pattern.findall(text)
        # Every ``#/components/<section>/<Name>`` pointer must name a component
        # this document actually declares; a dangling one would make the
        # published contract unusable to a generator even though the YAML parses.
        declared = _declared_components(text)
        document_references = [
            reference for reference in references if reference.startswith("#/components/")
        ]
        assert document_references
        for reference in document_references:
            _section, name = reference.removeprefix("#/components/").split("/", 1)
            assert (_section, name) in declared, reference
        for operation in ("prepareProviderPrompt", "recordProviderCacheUsage"):
            assert f"operationId: {operation}" in text
        local_references = [reference for reference in references if not reference.startswith("#")]
        assert local_references == ["../schemas/cache-affinity-decision.schema.json"]
        for reference in local_references:
            relative, _separator, _fragment = reference.partition("#")
            assert "://" not in relative
            target = (document.parent / relative).resolve(strict=True)
            assert target.parent == document.parent.parent / "schemas"
            jsonschema.Draft202012Validator.check_schema(
                json.loads(target.read_text(encoding="utf-8"))
            )


def test_context_append_runtime_responses_match_the_closed_openapi_component() -> None:
    overlay_text = (
        ENGINE_ROOT / "openapi/cache-parity-control-plane.openapi.yaml"
    ).read_text(encoding="utf-8")
    component = overlay_text.split("    ContextLedgerEventResponse:\n", 1)[1].split(
        "    ParityReportEnvelope:\n",
        1,
    )[0]
    required_section = component.split("      required:\n", 1)[1].split(
        "      properties:\n",
        1,
    )[0]
    properties_section = component.split("      properties:\n", 1)[1]
    event_type_section = properties_section.split("        event_type:\n", 1)[1].split(
        "        occurred_at:",
        1,
    )[0]

    required_fields = set(re.findall(r"^        - ([a-z][a-z0-9_]*)$", required_section, re.M))
    property_fields = set(
        re.findall(r"^        ([a-z][a-z0-9_]*):", properties_section, re.M)
    )
    documented_event_types = set(
        re.findall(r"^            - ([A-Z][A-Z_]*)$", event_type_section, re.M)
    )
    runtime_event_types = {event_type.value for event_type in ContextEventType}

    assert required_fields == property_fields
    assert documented_event_types == runtime_event_types
    assert "      additionalProperties: false\n" in component

    runtime_documents: dict[ContextEventType, dict[str, object]] = {}
    for sequence, event_type in enumerate(ContextEventType, start=1):
        event = ContextLedgerEvent(
            tenant_id="tenant-test",
            project_id="project-test",
            stream_id="stream-1",
            sequence=sequence,
            event_id=f"event-{sequence}",
            idempotency_key=f"idempotency-{sequence}",
            event_type=event_type,
            branch_lineage="main",
            repository_snapshot_digest=DIGEST,
            subject_ref=None,
            payload={},
            payload_digest=DIGEST,
            previous_event_digest=None,
            event_digest=DIGEST,
            supersedes_event_id=None,
            occurred_at=0.0,
        )
        document = _context_event_document(event)
        assert set(document) == required_fields
        assert document["event_type"] in documented_event_types
        runtime_documents[event_type] = document

    rollback = runtime_documents[ContextEventType.COMPACTION_ROLLBACK]
    assert rollback["event_type"] == "COMPACTION_ROLLBACK"
    with pytest.raises(SchemaInvalid, match="context-ledger-event document is invalid"):
        schemas.validate("context-ledger-event", rollback)


def test_provider_prompt_operations_document_the_runtime_vocabulary() -> None:
    """The two BC-15 operations must not drift from the runtime enums.

    A documented ``enum`` that the runtime does not accept turns a valid
    generated client into a 422, and one the runtime accepts but the document
    omits hides a live input from review. Both are caught by comparing the
    published lists against the enums themselves.
    """

    from elmos_build_cache.prompt_cache import (
        PromptProvider,
        PromptRequestClass,
        ProviderCacheMode,
        ProviderCacheReason,
    )

    text = (
        ENGINE_ROOT / "openapi/cache-parity-control-plane.openapi.yaml"
    ).read_text(encoding="utf-8")
    prepare = text.split("  /cache/provider-prompts/prepare:\n", 1)[1].split(
        "  /cache/provider-prompts/usage:\n", 1
    )[0]
    usage = text.split("  /cache/provider-prompts/usage:\n", 1)[1].split(
        "  /cache/context-ledgers/", 1
    )[0]

    assert "operationId: prepareProviderPrompt" in prepare
    assert "operationId: recordProviderCacheUsage" in usage
    assert prepare.count("#/components/parameters/IdempotencyKey") == 1
    assert usage.count("#/components/parameters/IdempotencyKey") == 1

    request_classes = set(
        re.findall(r"^                    - ([A-Z][A-Z_]*)$", prepare, re.M)
    )
    assert request_classes == {item.value for item in PromptRequestClass}
    documented_modes = set(
        re.findall(r"cache_mode:\n\s+enum: \[([^\]]+)\]", prepare)[0].split(", ")
    )
    assert documented_modes == {item.value for item in ProviderCacheMode}
    reason_codes = set(
        re.findall(r"^                    - ([A-Z][A-Z_]*)$", usage, re.M)
    )
    assert reason_codes == {item.value for item in ProviderCacheReason}
    providers = set(
        re.findall(r"provider: \{ type: string, enum: \[([^\]]+)\] \}", usage)[0].split(", ")
    )
    assert providers == {item.value for item in PromptProvider}

    view = text.split("    ProviderRequestView:\n", 1)[1].split(
        "    PreparedProviderPrompt:\n", 1
    )[0]
    # The published provider request view is the content-free projection: the
    # assembled payload is represented only by its digest.
    assert "payload_digest" in view
    assert "payload_retained: { type: boolean, const: false }" in view
    assert "\n        payload:" not in view

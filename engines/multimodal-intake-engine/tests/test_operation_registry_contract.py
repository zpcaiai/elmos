from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

from elmos_multimodal_intake.api import MultimodalIntakeApi
from elmos_multimodal_intake.errors import ValidationError
from elmos_multimodal_intake.operation_registry import (
    OPERATION_REGISTRY,
    OPERATION_REGISTRY_DIGEST,
    OPERATION_REGISTRY_DOCUMENT,
    REGISTERED_SKILLS,
    require_operation,
)
from elmos_multimodal_intake.skill_runtime import SKILL_REGISTRY


ROOT = Path(__file__).resolve().parents[3]
OPENAPI = ROOT / "engines/multimodal-intake-engine/openapi/multimodal-intake-v1.openapi.yaml"
TYPESCRIPT = ROOT / "sdk/multimodal-intake/typescript/client.ts"
JAVA = ROOT / "sdk/multimodal-intake/java/src/main/java/dev/elmos/intake/MultimodalIntakeClient.java"
OPERATION_INPUT_SCHEMA = (
    ROOT
    / "engines/multimodal-intake-engine/openapi/operation-input-contracts.schema.json"
)
PACKAGED_OPERATION_INPUT_SCHEMA = (
    ROOT
    / "engines/multimodal-intake-engine/src/elmos_multimodal_intake/_data/openapi/operation-input-contracts.schema.json"
)
OPENAPI_OPERATION_INPUT_SCHEMA_REF = "./operation-input-contracts.schema.json"


def _openapi_operation_input_schema(source: str) -> Path:
    external_refs = re.findall(
        r'^\s*- \{ \$ref: "([^"#][^"]*)" \}$', source, re.MULTILINE
    )
    assert external_refs == [OPENAPI_OPERATION_INPUT_SCHEMA_REF]
    candidate = OPENAPI.parent / external_refs[0]
    assert not candidate.is_symlink()
    resolved = candidate.resolve(strict=True)
    assert resolved == OPERATION_INPUT_SCHEMA.resolve(strict=True)
    assert resolved.parent == OPENAPI.parent.resolve(strict=True)
    assert resolved.is_file()
    return resolved


def _pairs_from_typescript(source: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for skill, operations in re.findall(
        r'^  "(elmos-[^"]+)": \[([^\]]+)\],?$', source, re.MULTILINE
    ):
        for operation in re.findall(r'"([a-z][a-z0-9_]*)"', operations):
            pairs.add((skill, operation))
    return pairs


def _pairs_from_java(source: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for skill, operations in re.findall(
        r'Map\.entry\("(elmos-[^"]+)", Set\.of\(([^)]*)\)\)', source
    ):
        for operation in re.findall(r'"([a-z][a-z0-9_]*)"', operations):
            pairs.add((skill, operation))
    return pairs


def _pairs_from_openapi(source: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    pattern = re.compile(
        r"^    [A-Za-z]+SkillExecutionRequest: \{ type: object, properties: "
        r"\{ skill: \{ const: (elmos-[a-z0-9-]+) \}, operation: \{ enum: \[([^]]+)\]",
        re.MULTILINE,
    )
    for skill, operations in pattern.findall(source):
        for operation in operations.split(","):
            pairs.add((skill, operation.strip()))
    return pairs


def _field_contracts_from_typescript(source: str) -> dict[tuple[str, str], tuple[set[str], set[str]]]:
    contracts: dict[tuple[str, str], tuple[set[str], set[str]]] = {}
    pattern = re.compile(
        r'^  "(elmos-[^"/]+)/([a-z][a-z0-9_]*)": \{ allowed: \[([^]]*)\], required: \[([^]]*)\] \},$',
        re.MULTILINE,
    )
    for skill, operation, allowed, required in pattern.findall(source):
        contracts[(skill, operation)] = (
            set(re.findall(r'"([a-z][a-z0-9_]*)"', allowed)),
            set(re.findall(r'"([a-z][a-z0-9_]*)"', required)),
        )
    return contracts


def _field_contracts_from_java(source: str) -> dict[tuple[str, str], tuple[set[str], set[str]]]:
    contracts: dict[tuple[str, str], tuple[set[str], set[str]]] = {}
    pattern = re.compile(
        r'Map\.entry\("(elmos-[^"/]+)/([a-z][a-z0-9_]*)", inputContract\("([^"]*)", "([^"]*)"\)\)'
    )
    for skill, operation, allowed, required in pattern.findall(source):
        contracts[(skill, operation)] = (set(allowed.split()), set(required.split()))
    return contracts


def test_operation_registry_is_exact_and_matches_all_public_contracts() -> None:
    expected = set(OPERATION_REGISTRY)
    assert len(REGISTERED_SKILLS) == 50
    assert len(expected) == 147
    assert REGISTERED_SKILLS == set(SKILL_REGISTRY)
    assert OPERATION_REGISTRY_DOCUMENT["skill_count"] == 50
    assert OPERATION_REGISTRY_DOCUMENT["operation_count"] == 147
    assert _pairs_from_typescript(TYPESCRIPT.read_text(encoding="utf-8")) == expected
    assert _pairs_from_java(JAVA.read_text(encoding="utf-8")) == expected
    assert _pairs_from_openapi(OPENAPI.read_text(encoding="utf-8")) == expected


def test_generated_openapi_input_field_schema_matches_every_registry_pair() -> None:
    raw = OPERATION_INPUT_SCHEMA.read_bytes()
    assert raw == PACKAGED_OPERATION_INPUT_SCHEMA.read_bytes()
    document = json.loads(raw)
    assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert document["x-elmos-operation-count"] == 147
    assert document["x-elmos-operation-registry-digest"] == OPERATION_REGISTRY_DIGEST
    observed: dict[tuple[str, str], tuple[set[str], set[str]]] = {}
    for clause in document["allOf"]:
        condition = clause["if"]
        output = clause["then"]
        assert condition["required"] == ["skill", "operation"]
        pair = (
            condition["properties"]["skill"]["const"],
            condition["properties"]["operation"]["const"],
        )
        assert output["required"] == ["input"]
        input_schema = output["properties"]["input"]
        assert input_schema["type"] == "object"
        assert input_schema["additionalProperties"] is False
        assert all(value == {} for value in input_schema["properties"].values())
        observed[pair] = (
            set(input_schema["properties"]),
            set(input_schema.get("required", [])),
        )
    expected = {
        pair: (set(spec.input_fields), set(spec.required_input_fields))
        for pair, spec in OPERATION_REGISTRY.items()
    }
    assert observed == expected


def test_openapi_resolves_the_exact_generated_operation_input_contract() -> None:
    resolved = _openapi_operation_input_schema(OPENAPI.read_text(encoding="utf-8"))
    document = json.loads(resolved.read_bytes())

    assert document["x-elmos-operation-count"] == len(OPERATION_REGISTRY) == 147
    assert document["x-elmos-operation-registry-digest"] == OPERATION_REGISTRY_DIGEST
    assert len(document["allOf"]) == 147


@pytest.mark.parametrize(
    "invalid_ref",
    [
        "../operation-input-contracts.schema.json",
        "./missing-operation-input-contracts.schema.json",
        "https://example.invalid/operation-input-contracts.schema.json",
        "#/components/schemas/TypedOperationInputConstraints",
    ],
)
def test_openapi_operation_input_contract_reference_fails_closed(
    invalid_ref: str,
) -> None:
    source = OPENAPI.read_text(encoding="utf-8").replace(
        OPENAPI_OPERATION_INPUT_SCHEMA_REF,
        invalid_ref,
        1,
    )

    with pytest.raises(AssertionError):
        _openapi_operation_input_schema(source)


def test_changed_input_field_contracts_do_not_drift_across_sdks() -> None:
    expected = {
        pair: (set(spec.input_fields), set(spec.required_input_fields))
        for pair, spec in OPERATION_REGISTRY.items()
        if pair[0] in {
            "elmos-multimodal-requirement-extraction",
            "elmos-multi-asset-content-fusion",
            "elmos-document-version-and-conflict-detection",
            "elmos-multimodal-evaluation-framework",
            "elmos-downstream-agent-integration",
            "elmos-codex-context-capacity-parity",
            "elmos-context-budget-manager",
            "elmos-multimodal-token-accounting",
            "elmos-long-context-packing-and-ranking",
            "elmos-context-pressure-monitor",
            "elmos-structured-context-compaction",
            "elmos-context-checkpoint-and-recovery",
            "elmos-context-rehydration",
            "elmos-repository-context-map",
            "elmos-model-capability-discovery",
            "elmos-context-integrity-and-loss-detection",
            "elmos-folder-tree-input",
            "elmos-resumable-multi-file-folder-upload",
            "elmos-project-package-manifest",
            "elmos-project-root-language-framework-detection",
            "elmos-ignore-generated-vendored-file-classification",
            "elmos-repository-map-and-symbol-indexing",
            "elmos-project-package-version-and-incremental-update",
            "elmos-project-package-preview-and-review-ui",
        }
    }
    assert _field_contracts_from_typescript(TYPESCRIPT.read_text(encoding="utf-8")) == expected
    assert _field_contracts_from_java(JAVA.read_text(encoding="utf-8")) == expected


def test_evaluation_and_confirmed_part_nested_shapes_are_strict() -> None:
    evaluation = {
        "subject": {
            "subject_id": "parser-a",
            "subject_kind": "parser",
            "artifact_digest": "sha256:" + "a" * 64,
            "implementation_version": "1.2.3",
            "configuration_digest": "sha256:" + "b" * 64,
        },
        "evidence": [{"case_id": "case-a", "media_type": "text/plain", "content_base64": "YQ=="}],
    }
    require_operation("elmos-multimodal-evaluation-framework", "evaluate", evaluation)
    with pytest.raises(ValidationError, match="OPERATION_INPUT_SHAPE_INVALID"):
        require_operation(
            "elmos-multimodal-evaluation-framework", "evaluate",
            {**evaluation, "subject": {**evaluation["subject"], "subject_kind": "unknown"}},
        )

    data = b"confirmed bytes"
    confirmed = {
        "session_id": "session-a", "path": "src/main.py", "part_number": 1,
        "byte_count": len(data),
        "part_digest": "sha256:" + hashlib.sha256(data).hexdigest(),
        "data_base64": base64.b64encode(data).decode("ascii"),
    }
    require_operation("elmos-resumable-multi-file-folder-upload", "confirm_part", confirmed)
    with pytest.raises(ValidationError, match="OPERATION_INPUT_SHAPE_INVALID"):
        require_operation(
            "elmos-resumable-multi-file-folder-upload", "confirm_part",
            {**confirmed, "byte_count": len(data) + 1},
        )


def test_removed_pure_operations_and_legacy_evaluation_inputs_require_adapter_or_fail() -> None:
    for pair in (
        ("elmos-folder-tree-input", "parse"),
        ("elmos-project-package-manifest", "build_manifest"),
        ("elmos-project-package-preview-and-review-ui", "build_preview"),
    ):
        with pytest.raises(ValidationError, match="REQUIRES_ADAPTER"):
            require_operation(*pair, {})
    with pytest.raises(ValidationError, match="OPERATION_INPUT_FIELDS_INVALID"):
        require_operation(
            "elmos-multimodal-evaluation-framework", "evaluate",
            {"cases": [], "metrics": [], "required_skills": []},
        )


def test_unknown_operation_and_unowned_input_fields_fail_closed() -> None:
    with pytest.raises(ValidationError, match="REQUIRES_ADAPTER"):
        require_operation("elmos-unified-multimodal-content-ir", "invented", {})
    with pytest.raises(ValidationError, match="OPERATION_INPUT_FIELDS_INVALID"):
        require_operation(
            "elmos-unified-multimodal-content-ir",
            "normalize",
            {"blocks": [], "unowned": True},
        )


def test_unknown_public_operation_returns_adapter_error_with_trace() -> None:
    document = {
        "schema_version": "1.0.0",
        "skill": "elmos-unified-multimodal-content-ir",
        "operation": "invented",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "actor_id": "actor-a",
        "idempotency_key": "registry-test-0001",
        "trace_id": "trace-registry",
        "input": {},
    }
    response = MultimodalIntakeApi(lambda _request: {}, lambda: []).execute(document)
    assert response.status_code == 422
    assert response.body["code"] == "REQUIRES_ADAPTER"
    assert response.body["trace_id"] == "trace-registry"


def test_openapi_request_and_result_share_one_discriminator() -> None:
    source = OPENAPI.read_text(encoding="utf-8")
    assert "SkillOperationDiscriminator:" in source
    assert source.count('$ref: "#/components/schemas/SkillOperationDiscriminator"') == 2
    assert source.count("propertyName: skill") >= 2
    assert "required: [schema_version, status, code, retryable, trace_id]" in source
    assert '$ref: "#/components/schemas/TypedOperationInputConstraints"' in source
    assert "required: [subject_id, subject_kind, artifact_digest, implementation_version, configuration_digest]" in source
    assert "required: [session_id, path, part_number, byte_count, part_digest, data_base64]" in source
    assert "Runtime and SDK validators decode data_base64" in source

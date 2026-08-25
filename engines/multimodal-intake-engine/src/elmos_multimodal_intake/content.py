"""Deterministic content, provenance, review, and retrieval operations.

All functions in this module treat supplied text and metadata as untrusted data.
They perform bounded, local transformations only and never execute input content.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .canonical import MAX_SAFE_JSON_INTEGER, normalize_relative_path
from .errors import ValidationError


_BLOCK_TYPES = frozenset(
    {
        "text",
        "heading",
        "paragraph",
        "list",
        "table",
        "table_cell",
        "code",
        "image",
        "audio_segment",
        "ui_element",
        "diagram_node",
        "diagram_edge",
        "requirement",
        "unknown",
    }
)
_REQUIREMENT = re.compile(
    r"^(?:REQ(?:UIREMENT)?[- :#]*\d*|MUST|SHALL|必须|应当|不得|需求[- :：#]*\d*)\s*[:：-]?\s*(.+)$",
    re.IGNORECASE,
)
_ACCEPTANCE = re.compile(r"^(?:AC|ACCEPTANCE|验收(?:标准)?)\s*[:：-]\s*(.+)$", re.IGNORECASE)
_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OVERRIDE_INSTRUCTIONS", re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions", re.I)),
    ("SYSTEM_IMPERSONATION", re.compile(r"(?:system|developer)\s*(?:message|instruction)\s*[:：]", re.I)),
    ("TOOL_ESCALATION", re.compile(r"(?:run|execute|调用|执行).{0,40}(?:shell|terminal|tool|命令)", re.I)),
    ("SECRET_EXFILTRATION", re.compile(r"(?:reveal|print|send|显示|泄露).{0,40}(?:secret|token|password|密钥)", re.I)),
)
_DETECTOR_RESULTS = frozenset({"ALLOW", "DENY", "NEEDS_REVIEW"})
_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_AUTHORITATIVE_ASSET_BINDING_CAPABILITY = object()


class ContentContractError(ValueError):
    """Raised when untrusted content violates an executable contract."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    data = value if isinstance(value, bytes) else _canonical(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def content_contract_json(value: Any) -> str:
    """Serialize a value with the established Content-domain canonical form."""

    return _canonical(value)


def content_contract_digest(value: Any) -> str:
    """Return the stable digest used by immutable Content-domain contracts.

    This intentionally preserves the existing Content canonicalization instead
    of adopting the runtime-wide RFC 8785 serializer.  Persistence bridges must
    call this function when they verify a digest emitted by this module.
    """

    data = value if isinstance(value, bytes) else content_contract_json(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _content_digest(value: Any) -> str:
    data = value if isinstance(value, bytes) else value.encode("utf-8") if isinstance(value, str) else _canonical(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _inputs(request: Mapping[str, Any]) -> Mapping[str, Any]:
    value = request.get("inputs")
    if not isinstance(value, Mapping):
        raise ContentContractError("inputs must be an object")
    return value


def _runtime_namespace(
    request: Mapping[str, Any], container: str, namespace: str
) -> Mapping[str, Any] | None:
    """Read policy/capability facts from the trusted runtime envelope only."""

    root = request.get(container)
    if not isinstance(root, Mapping):
        return None
    value = root.get(namespace)
    return value if isinstance(value, Mapping) else None


def _scope_matches(value: Mapping[str, Any], request: Mapping[str, Any]) -> bool:
    return (
        value.get("tenant_id") == request.get("tenant_id")
        and value.get("project_id") == request.get("project_id")
    )


def _trusted_prompt_detector_receipt(
    request: Mapping[str, Any],
    *,
    content_digest: str,
    policy_version: str,
) -> tuple[str, dict[str, Any] | None]:
    """Resolve one digest-bound detector receipt from the trusted runtime envelope.

    Repository/user content cannot install a detector or self-assert a verdict. The
    host must put the detector registry and its authorization receipts in the
    trusted ``capabilities`` namespace. A receipt is accepted only when every
    security-relevant field is bound by its canonical digest.
    """

    registry = _runtime_namespace(request, "capabilities", "prompt_injection_detector")
    if registry is None or not _scope_matches(registry, request):
        return "DETECTOR_REGISTRY_UNAVAILABLE", None
    detector_id = str(registry.get("detector_id", "")).strip()
    detector_version = str(registry.get("version", "")).strip()
    registry_version = str(registry.get("registry_version", "")).strip()
    if not detector_id or not detector_version or not registry_version:
        return "DETECTOR_REGISTRY_INVALID", None
    if registry.get("available") is not True:
        return "DETECTOR_UNAVAILABLE", None
    if registry.get("authorized") is not True:
        return "DETECTOR_NOT_AUTHORIZED", None
    raw_records = registry.get("evidence_records", [])
    if not isinstance(raw_records, Sequence) or isinstance(
        raw_records, (str, bytes, bytearray)
    ):
        return "DETECTOR_REGISTRY_INVALID", None
    if len(raw_records) > 10_000:
        return "DETECTOR_REGISTRY_INVALID", None

    matches: list[dict[str, Any]] = []
    invalid_matching_record = False
    for raw in raw_records:
        if not isinstance(raw, Mapping):
            continue
        if raw.get("content_digest") != content_digest:
            continue
        result = str(raw.get("result", "")).strip().upper()
        binding = {
            "receipt_id": str(raw.get("receipt_id", "")).strip(),
            "content_digest": content_digest,
            "detector_id": detector_id,
            "detector_version": detector_version,
            "registry_version": registry_version,
            "result": result,
            "policy_version": policy_version,
            "tenant_id": request.get("tenant_id"),
            "project_id": request.get("project_id"),
            "authorization_id": str(raw.get("authorization_id", "")).strip(),
            "authorized": True,
        }
        valid = (
            bool(binding["receipt_id"])
            and bool(binding["authorization_id"])
            and result in _DETECTOR_RESULTS
            and raw.get("detector_id") == detector_id
            and raw.get("detector_version") == detector_version
            and raw.get("registry_version") == registry_version
            and raw.get("policy_version") == policy_version
            and raw.get("tenant_id") == request.get("tenant_id")
            and raw.get("project_id") == request.get("project_id")
            and raw.get("authorized") is True
            and raw.get("receipt_digest") == _digest(binding)
        )
        if not valid:
            invalid_matching_record = True
            continue
        matches.append({**binding, "receipt_digest": raw["receipt_digest"]})

    if invalid_matching_record or len(matches) > 1:
        return "DETECTOR_RECEIPT_INVALID", None
    if not matches:
        return "DETECTOR_RECEIPT_NOT_FOUND", None
    return "OK", matches[0]


def _string_set(value: Any, field: str, *, maximum: int = 1_000) -> set[str]:
    items = _sequence(value, field, maximum=maximum)
    normalized: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, str) or not item.strip():
            raise ContentContractError(f"{field}[{index}] must be a non-blank string")
        normalized.add(item.strip())
    return normalized


def _sequence(value: Any, field: str, *, maximum: int = 100_000) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ContentContractError(f"{field} must be an array")
    if len(value) > maximum:
        raise ContentContractError(f"{field} exceeds the bounded item limit")
    return list(value)


def _text(value: Any, field: str, *, maximum: int = 1_000_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContentContractError(f"{field} must be a non-blank UTF-8 string")
    normalized = value.strip()
    try:
        encoded = normalized.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ContentContractError(f"{field} must be valid UTF-8 text") from exc
    if len(encoded) > maximum:
        raise ContentContractError(f"{field} exceeds the {maximum}-byte UTF-8 limit")
    return normalized


def _finite_float(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool):
        raise ContentContractError(f"{field} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ContentContractError(f"{field} must be a finite number") from exc
    if (
        not math.isfinite(result)
        or minimum is not None and result < minimum
        or maximum is not None and result > maximum
    ):
        raise ContentContractError(f"{field} is outside its allowed finite range")
    return result


def _optional_locator_text(value: Any, field: str, *, maximum: int = 512) -> str | None:
    if value is None:
        return None
    return _text(value, field, maximum=maximum)


def _locator_integer(
    value: Any,
    field: str,
    *,
    minimum: int,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or value > MAX_SAFE_JSON_INTEGER
    ):
        raise ContentContractError(f"{field} must be an integer greater than or equal to {minimum}")
    return value


def _bbox(value: Any, field: str) -> list[float]:
    raw = _sequence(value, field, maximum=4)
    if len(raw) != 4:
        raise ContentContractError(f"{field} must contain exactly four numbers")
    result = [
        _finite_float(item, field, minimum=0.0, maximum=float(MAX_SAFE_JSON_INTEGER))
        for item in raw
    ]
    if result[2] <= result[0] or result[3] <= result[1]:
        raise ContentContractError(f"{field} must have positive width and height")
    return result


def _relative_locator_path(value: Any, field: str) -> str:
    try:
        return normalize_relative_path(_text(value, field, maximum=1024))
    except ValidationError as exc:
        raise ContentContractError(f"{field} must be a safe relative path") from exc


def _strict_locator(value: Any, field: str) -> dict[str, Any]:
    """Validate exactly one typed locator variant from the SourceAnchor contract."""

    if not isinstance(value, Mapping):
        raise ContentContractError(f"{field} must be an object")
    kind = value.get("kind")
    if not isinstance(kind, str):
        raise ContentContractError(f"{field}.kind is required")
    variants: dict[str, tuple[set[str], set[str]]] = {
        "pdf_region": ({"kind", "page", "bbox"}, {"kind", "page", "bbox"}),
        "word_part": (
            {"kind", "part", "paragraph_id", "table_cell", "revision_id"},
            {"kind", "part"},
        ),
        "audio_time": ({"kind", "start_ms", "end_ms", "speaker"}, {"kind", "start_ms", "end_ms"}),
        "image_region": ({"kind", "bbox", "polygon"}, {"kind"}),
        "text_range": (
            {"kind", "start_line", "end_line", "start_byte", "end_byte", "encoding"},
            {"kind", "start_line", "end_line"},
        ),
        "code_range": (
            {
                "kind", "relative_path", "start_line", "end_line",
                "start_column", "end_column", "commit",
            },
            {"kind", "relative_path", "start_line", "end_line"},
        ),
        "code_symbol": (
            {"kind", "relative_path", "symbol_id", "commit"},
            {"kind", "relative_path", "symbol_id"},
        ),
        "table_region": ({"kind", "reference_id"}, {"kind", "reference_id"}),
        "diagram_element": ({"kind", "reference_id"}, {"kind", "reference_id"}),
        "tool_run": ({"kind", "reference_id"}, {"kind", "reference_id"}),
        "test_run": ({"kind", "reference_id"}, {"kind", "reference_id"}),
    }
    variant = variants.get(kind)
    if variant is None:
        raise ContentContractError(f"{field}.kind is unsupported")
    allowed, required = variant
    actual = set(value)
    if actual - allowed or required - actual:
        raise ContentContractError(f"{field} does not match the {kind} locator contract")

    result: dict[str, Any] = {"kind": kind}
    if kind == "pdf_region":
        result["page"] = _locator_integer(value["page"], f"{field}.page", minimum=1)
        result["bbox"] = _bbox(value["bbox"], f"{field}.bbox")
    elif kind == "word_part":
        result["part"] = _text(value["part"], f"{field}.part", maximum=512)
        for name in ("paragraph_id", "table_cell", "revision_id"):
            if name in value:
                result[name] = _optional_locator_text(value[name], f"{field}.{name}")
    elif kind == "audio_time":
        start = _locator_integer(value["start_ms"], f"{field}.start_ms", minimum=0)
        end = _locator_integer(value["end_ms"], f"{field}.end_ms", minimum=0)
        if end <= start:
            raise ContentContractError(f"{field} has an invalid time range")
        result.update({"start_ms": start, "end_ms": end})
        if "speaker" in value:
            result["speaker"] = _optional_locator_text(value["speaker"], f"{field}.speaker")
    elif kind == "image_region":
        if "bbox" not in value and "polygon" not in value:
            raise ContentContractError(f"{field} requires bbox or polygon")
        if "bbox" in value:
            result["bbox"] = _bbox(value["bbox"], f"{field}.bbox")
        if "polygon" in value:
            polygon = _sequence(value["polygon"], f"{field}.polygon", maximum=10_000)
            if len(polygon) < 3:
                raise ContentContractError(f"{field}.polygon requires at least three points")
            points: list[list[float]] = []
            for index, point in enumerate(polygon):
                raw_point = _sequence(point, f"{field}.polygon[{index}]", maximum=2)
                if len(raw_point) != 2:
                    raise ContentContractError(f"{field}.polygon[{index}] must contain two numbers")
                points.append([
                    _finite_float(
                        item,
                        f"{field}.polygon[{index}]",
                        minimum=0.0,
                        maximum=float(MAX_SAFE_JSON_INTEGER),
                    )
                    for item in raw_point
                ])
            if len({tuple(point) for point in points}) < 3:
                raise ContentContractError(f"{field}.polygon must contain three distinct points")
            result["polygon"] = points
    elif kind in {"text_range", "code_range"}:
        start_line = _locator_integer(value["start_line"], f"{field}.start_line", minimum=1)
        end_line = _locator_integer(value["end_line"], f"{field}.end_line", minimum=1)
        if end_line < start_line:
            raise ContentContractError(f"{field} has an invalid line range")
        result.update({"start_line": start_line, "end_line": end_line})
        if kind == "text_range":
            byte_fields = (value.get("start_byte"), value.get("end_byte"))
            if (byte_fields[0] is None) != (byte_fields[1] is None):
                raise ContentContractError(f"{field} byte range must be complete")
            if byte_fields[0] is not None:
                start_byte = _locator_integer(byte_fields[0], f"{field}.start_byte", minimum=0)
                end_byte = _locator_integer(byte_fields[1], f"{field}.end_byte", minimum=0)
                if end_byte < start_byte:
                    raise ContentContractError(f"{field} has an invalid byte range")
                result.update({"start_byte": start_byte, "end_byte": end_byte})
            if "encoding" in value:
                result["encoding"] = _optional_locator_text(value["encoding"], f"{field}.encoding", maximum=64)
        else:
            result["relative_path"] = _relative_locator_path(
                value["relative_path"], f"{field}.relative_path"
            )
            columns = (value.get("start_column"), value.get("end_column"))
            if (columns[0] is None) != (columns[1] is None):
                raise ContentContractError(f"{field} column range must be complete")
            if columns[0] is not None:
                start_column = _locator_integer(columns[0], f"{field}.start_column", minimum=0)
                end_column = _locator_integer(columns[1], f"{field}.end_column", minimum=0)
                if end_line == start_line and end_column < start_column:
                    raise ContentContractError(f"{field} has an invalid column range")
                result.update({"start_column": start_column, "end_column": end_column})
            if "commit" in value:
                result["commit"] = _optional_locator_text(value["commit"], f"{field}.commit", maximum=128)
    elif kind == "code_symbol":
        result["relative_path"] = _relative_locator_path(
            value["relative_path"], f"{field}.relative_path"
        )
        result["symbol_id"] = _text(value["symbol_id"], f"{field}.symbol_id", maximum=512)
        if "commit" in value:
            result["commit"] = _optional_locator_text(value["commit"], f"{field}.commit", maximum=128)
    else:
        result["reference_id"] = _text(value["reference_id"], f"{field}.reference_id", maximum=512)
    return result


def _anchor(anchor: Any, field: str = "anchor") -> dict[str, Any]:
    if not isinstance(anchor, Mapping):
        raise ContentContractError(f"{field} must be an object")
    asset_id = _text(anchor.get("asset_id"), f"{field}.asset_id", maximum=128)
    if _RESOURCE_ID.fullmatch(asset_id) is None:
        raise ContentContractError(f"{field}.asset_id must be a safe resource identifier")
    asset_digest = _text(anchor.get("asset_digest"), f"{field}.asset_digest", maximum=80)
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", asset_digest):
        raise ContentContractError(f"{field}.asset_digest must be sha256 content identity")
    locator = _strict_locator(anchor.get("locator"), f"{field}.locator")
    asset_version = anchor.get("asset_version", 1)
    if (
        not isinstance(asset_version, int)
        or isinstance(asset_version, bool)
        or asset_version < 1
        or asset_version > MAX_SAFE_JSON_INTEGER
    ):
        raise ContentContractError(
            f"{field}.asset_version must be a positive JSON-safe integer"
        )
    normalized: dict[str, Any] = {
        "asset_id": asset_id,
        "asset_digest": asset_digest,
        "asset_version": asset_version,
        "locator": dict(locator),
        "status": str(anchor.get("status", "VALID")),
    }
    if normalized["status"] not in {"VALID", "MIGRATED", "INVALID", "DELETED", "INACCESSIBLE"}:
        raise ContentContractError(f"{field}.status is invalid")
    anchor_id = (
        _text(anchor["anchor_id"], f"{field}.anchor_id", maximum=128)
        if "anchor_id" in anchor
        else "anchor_" + _digest(normalized)[7:31]
    )
    if _RESOURCE_ID.fullmatch(anchor_id) is None:
        raise ContentContractError(f"{field}.anchor_id must be a safe resource identifier")
    normalized["anchor_id"] = anchor_id
    return normalized


def _with_authoritative_asset_bindings(
    request: Mapping[str, Any],
    bindings: set[tuple[str, int, str]],
) -> dict[str, Any]:
    """Attach store-derived authority; JSON/public callers cannot forge the object capability."""

    result = dict(request)
    result["_authoritative_asset_binding_capability"] = _AUTHORITATIVE_ASSET_BINDING_CAPABILITY
    result["_authoritative_asset_bindings"] = frozenset(bindings)
    return result


def _anchor_is_authoritative(request: Mapping[str, Any], anchor: Mapping[str, Any]) -> bool:
    if request.get("_authoritative_asset_binding_capability") is not _AUTHORITATIVE_ASSET_BINDING_CAPABILITY:
        return False
    bindings = request.get("_authoritative_asset_bindings")
    if not isinstance(bindings, frozenset) or anchor.get("status") != "VALID":
        return False
    return (
        anchor.get("asset_id"),
        anchor.get("asset_version"),
        anchor.get("asset_digest"),
    ) in bindings


def normalize_content_ir(request: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize parser output into a versioned, format-neutral Content IR."""

    values = _inputs(request)
    blocks = _sequence(values.get("blocks", []), "inputs.blocks")
    source_schema_version = str(values.get("source_schema_version", "1.0.0"))
    if source_schema_version not in {"0.9.0", "1.0.0"}:
        return {
            "state": "BLOCKED",
            "code": "CONTENT_IR_SCHEMA_UNSUPPORTED",
            "outputs": {"source_schema_version": source_schema_version, "supported": ["0.9.0", "1.0.0"]},
        }
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    unknown_types: list[str] = []
    unanchored: list[str] = []
    unbound_anchor_ids: list[str] = []
    authoritative_anchor_count = 0
    known_block_fields = {
        "id", "type", "body", "text", "confidence", "anchors", "parent_id", "order", "extensions"
    }
    for index, raw in enumerate(blocks):
        if not isinstance(raw, Mapping):
            raise ContentContractError(f"inputs.blocks[{index}] must be an object")
        source_type = str(raw.get("type", "unknown")).lower()
        block_type = source_type
        if block_type not in _BLOCK_TYPES:
            block_type = "unknown"
            unknown_types.append(source_type)
        block_id = _text(raw.get("id") or f"block_{index + 1:06d}", "content block id", maximum=256)
        if block_id in seen:
            raise ContentContractError(f"duplicate content block id: {block_id}")
        seen.add(block_id)
        anchors = [
            _anchor(item, f"inputs.blocks[{index}].anchors")
            for item in _sequence(raw.get("anchors", []), "anchors")
        ]
        for item in anchors:
            if _anchor_is_authoritative(request, item):
                authoritative_anchor_count += 1
            else:
                unbound_anchor_ids.append(item["anchor_id"])
        body = raw.get("body", raw.get("text", ""))
        extensions = raw.get("extensions", {})
        if not isinstance(extensions, Mapping):
            raise ContentContractError("content block extensions must be an object")
        preserved_extensions = dict(extensions)
        source_fields = {str(key): value for key, value in raw.items() if key not in known_block_fields}
        if source_fields:
            preserved_extensions["source_fields"] = source_fields
        if block_type == "unknown":
            preserved_extensions["source_type"] = source_type
        _canonical(body)
        confidence = _finite_float(raw.get("confidence", 1.0), "content block confidence", minimum=0.0, maximum=1.0)
        parent_id = raw.get("parent_id")
        if parent_id is not None:
            parent_id = _text(parent_id, "content block parent_id", maximum=256)
        order = raw.get("order", index)
        if not isinstance(order, int) or isinstance(order, bool) or order < 0:
            raise ContentContractError("content block order must be a non-negative integer")
        if not anchors:
            unanchored.append(block_id)
        normalized.append(
            {
                "id": block_id,
                "type": block_type,
                "body": body,
                "confidence": confidence,
                "anchors": anchors,
                "parent_id": parent_id,
                "order": order,
                "extensions": preserved_extensions,
            }
        )
    normalized.sort(key=lambda item: (item["order"], item["id"]))
    for block in normalized:
        if block["parent_id"] is not None and block["parent_id"] not in seen:
            raise ContentContractError("content block parent_id references an unknown block")
        if block["parent_id"] == block["id"]:
            raise ContentContractError("content block cannot be its own parent")
    relations: list[dict[str, Any]] = []
    relation_ids: set[str] = set()
    for index, raw in enumerate(_sequence(values.get("relations", []), "inputs.relations")):
        if not isinstance(raw, Mapping):
            raise ContentContractError(f"inputs.relations[{index}] must be an object")
        relation_id = _text(raw.get("id") or f"relation_{index + 1:06d}", "relation id", maximum=256)
        if relation_id in relation_ids:
            raise ContentContractError("relation id must be unique")
        relation_ids.add(relation_id)
        source_id = _text(raw.get("source_id"), "relation source_id", maximum=256)
        target_id = _text(raw.get("target_id"), "relation target_id", maximum=256)
        if source_id not in seen or target_id not in seen:
            raise ContentContractError("relation endpoint references an unknown block")
        attributes = raw.get("attributes", {})
        if not isinstance(attributes, Mapping):
            raise ContentContractError("relation attributes must be an object")
        relations.append(
            {
                "id": relation_id,
                "type": _text(raw.get("type"), "relation type", maximum=128),
                "source_id": source_id,
                "target_id": target_id,
                "confidence": _finite_float(raw.get("confidence", 1.0), "relation confidence", minimum=0.0, maximum=1.0),
                "attributes": dict(attributes),
            }
        )
    migrations = [] if source_schema_version == "1.0.0" else [{"from": "0.9.0", "to": "1.0.0", "state": "APPLIED"}]
    document = {
        "schema_version": "1.0.0",
        "source_schema_version": source_schema_version,
        "document_id": str(values.get("document_id", "document_" + _digest(normalized)[7:31])),
        "blocks": normalized,
        "relations": relations,
        "migrations": migrations,
    }
    warnings = {
        "unknown_source_types": sorted(set(unknown_types)),
        "unanchored_block_ids": sorted(unanchored),
        "unbound_anchor_ids": sorted(set(unbound_anchor_ids)),
        "empty_document": not normalized,
    }
    anchor_count = sum(len(item["anchors"]) for item in normalized)
    authority_bound = anchor_count > 0 and not unbound_anchor_ids
    complete = (
        bool(normalized)
        and not unknown_types
        and not unanchored
        and not unbound_anchor_ids
    )
    authority_required = bool(normalized) and (not authority_bound or bool(unanchored))
    return {
        "state": "SUCCEEDED" if complete else "PARTIAL",
        "code": (
            "CONTENT_IR_NORMALIZED"
            if complete
            else "CONTENT_IR_AUTHORITY_REQUIRED"
            if authority_required
            else "CONTENT_IR_REVIEW_REQUIRED"
        ),
        "outputs": {
            **document,
            "validation": warnings,
            "authority_state": "BOUND" if authority_bound else "NEEDS_REVIEW",
            "ir_digest": _digest(document),
        },
        "metrics": {
            "block_count": len(normalized),
            "anchored_block_count": sum(bool(item["anchors"]) for item in normalized),
            "anchor_count": anchor_count,
            "authoritative_anchor_count": authoritative_anchor_count,
        },
    }


def build_source_provenance(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate anchors and construct a hash-linked derivation graph."""

    values = _inputs(request)
    anchors = [_anchor(item, f"inputs.anchors[{index}]") for index, item in enumerate(_sequence(values.get("anchors", []), "inputs.anchors"))]
    derivations = _sequence(values.get("derivations", []), "inputs.derivations")
    nodes: dict[str, dict[str, Any]] = {}
    for anchor in anchors:
        anchor_id = anchor["anchor_id"]
        if anchor_id in nodes:
            raise ContentContractError(f"duplicate source anchor id: {anchor_id}")
        nodes[anchor_id] = anchor
    critical = _string_set(values.get("critical_item_ids", []), "inputs.critical_item_ids")
    edges: list[dict[str, Any]] = []
    derivation_ids: set[str] = set()
    for index, raw in enumerate(derivations):
        if not isinstance(raw, Mapping):
            raise ContentContractError(f"inputs.derivations[{index}] must be an object")
        source_ids = [
            _text(
                item,
                f"inputs.derivations[{index}].source_anchor_ids[{source_index}]",
                maximum=128,
            )
            for source_index, item in enumerate(
                _sequence(
                    raw.get("source_anchor_ids", []),
                    f"inputs.derivations[{index}].source_anchor_ids",
                )
            )
        ]
        if not source_ids or len(source_ids) != len(set(source_ids)):
            raise ContentContractError(
                "every derivation requires unique, non-empty source_anchor_ids"
            )
        missing = sorted(set(source_ids) - nodes.keys())
        if missing:
            raise ContentContractError(f"derivation references unknown anchors: {missing}")
        output_digest = _text(raw.get("output_digest"), "output_digest", maximum=80)
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", output_digest):
            raise ContentContractError("output_digest must be sha256 content identity")
        critical_item_ids = _string_set(
            raw.get("critical_item_ids", []),
            f"inputs.derivations[{index}].critical_item_ids",
        )
        unknown_critical = sorted(critical_item_ids - critical)
        if unknown_critical:
            raise ContentContractError(
                f"derivation references undeclared critical items: {unknown_critical}"
            )
        derivation_id = (
            _text(
                raw["derivation_id"],
                f"inputs.derivations[{index}].derivation_id",
                maximum=128,
            )
            if "derivation_id" in raw
            else f"derivation_{index + 1:06d}"
        )
        if _RESOURCE_ID.fullmatch(derivation_id) is None:
            raise ContentContractError("derivation_id must be a safe resource identifier")
        if derivation_id in derivation_ids:
            raise ContentContractError("derivation_id must be unique")
        derivation_ids.add(derivation_id)
        payload = {
            "derivation_id": derivation_id,
            "source_anchor_ids": sorted(source_ids),
            "processor": _text(raw.get("processor"), "processor", maximum=256),
            "processor_version": _text(raw.get("processor_version"), "processor_version", maximum=128),
            "output_digest": output_digest,
            "critical_item_ids": sorted(critical_item_ids),
        }
        payload["lineage_digest"] = _digest(payload)
        edges.append(payload)
    covered = {item for edge in edges for item in edge["critical_item_ids"]}
    missing_critical = sorted(critical - covered)
    unbound_anchor_ids = sorted(
        anchor["anchor_id"]
        for anchor in anchors
        if not _anchor_is_authoritative(request, anchor)
    )
    if missing_critical:
        state = "BLOCKED"
        code = "CRITICAL_SOURCE_COVERAGE_INCOMPLETE"
    elif not anchors or unbound_anchor_ids:
        state = "PARTIAL"
        code = "PROVENANCE_AUTHORITY_REQUIRED"
    else:
        state = "SUCCEEDED"
        code = "PROVENANCE_COMPLETE"
    return {
        "state": state,
        "code": code,
        "outputs": {
            "anchors": anchors,
            "derivations": edges,
            "graph_digest": _digest({"anchors": anchors, "derivations": edges}),
            "critical_coverage": 1.0 if not critical else len(critical & covered) / len(critical),
            "missing_critical_item_ids": missing_critical,
            "unbound_anchor_ids": unbound_anchor_ids,
            "authority_state": "BOUND" if anchors and not unbound_anchor_ids else "NEEDS_REVIEW",
        },
        "metrics": {
            "anchor_count": len(anchors),
            "authoritative_anchor_count": len(anchors) - len(unbound_anchor_ids),
        },
    }


def extract_requirements(request: Mapping[str, Any]) -> dict[str, Any]:
    """Extract explicitly stated requirements without inventing missing semantics."""

    values = _inputs(request)
    sources = _sequence(values.get("sources", []), "inputs.sources")
    requirements: list[dict[str, Any]] = []
    open_questions: list[dict[str, str]] = []
    source_ids: set[str] = set()
    for source_index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise ContentContractError(f"inputs.sources[{source_index}] must be an object")
        source_id = _text(source.get("source_id"), "source_id", maximum=256)
        if source_id in source_ids:
            raise ContentContractError("source_id must be unique")
        source_ids.add(source_id)
        anchor = _anchor(source.get("anchor"), f"inputs.sources[{source_index}].anchor")
        text = _text(source.get("text"), "source.text")
        pending_acceptance: list[str] = []
        for line_number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped:
                continue
            acceptance = _ACCEPTANCE.match(stripped)
            if acceptance:
                criterion = acceptance.group(1).strip()
                if requirements and requirements[-1]["source_id"] == source_id:
                    requirements[-1]["acceptance_criteria"].append(criterion)
                else:
                    pending_acceptance.append(criterion)
                continue
            match = _REQUIREMENT.match(stripped)
            if match:
                statement = match.group(1).strip()
                requirement = {
                    "requirement_id": f"REQ-{len(requirements) + 1:04d}",
                    "statement": statement,
                    "source_id": source_id,
                    "source_anchor": anchor,
                    "source_line": line_number,
                    "inferred": False,
                    "acceptance_criteria": pending_acceptance,
                    "requirement_type": str(source.get("requirement_type", "UNCLASSIFIED")),
                    "priority": str(source.get("priority", "UNSPECIFIED")),
                    "role": source.get("role"),
                    "depends_on": sorted(
                        _string_set(source.get("depends_on", []), "source.depends_on")
                    ),
                    "confidence": _finite_float(source.get("confidence", 1.0), "source.confidence", minimum=0.0, maximum=1.0),
                    "status": "EXTRACTED",
                }
                requirements.append(requirement)
                pending_acceptance = []
        if pending_acceptance:
            open_questions.append(
                {"requirement_id": "UNBOUND", "question": f"Acceptance criteria in {source_id} have no requirement."}
            )
    for item in requirements:
        if not item["acceptance_criteria"]:
            open_questions.append(
                {"requirement_id": item["requirement_id"], "question": "Acceptance criterion is missing."}
            )
    return {
        "state": "SUCCEEDED" if requirements and not open_questions else "PARTIAL",
        "code": "REQUIREMENTS_EXTRACTED" if requirements and not open_questions else "REQUIREMENTS_REVIEW_REQUIRED",
        "outputs": {
            "requirements": requirements,
            "open_questions": open_questions,
            "requirement_digest": _digest(requirements),
            "review_actions": {"accept": "NOT_RUN", "reject": "NOT_RUN", "merge": "NOT_RUN", "split": "NOT_RUN"},
        },
        "metrics": {"requirement_count": len(requirements), "anchored_count": len(requirements)},
    }


def fuse_assets(request: Mapping[str, Any]) -> dict[str, Any]:
    """Deduplicate content by immutable identity while preserving every source."""

    assets = _sequence(_inputs(request).get("assets", []), "inputs.assets")
    identity_registry = _runtime_namespace(request, "capabilities", "asset_identity_registry")
    trusted_digests: dict[str, str] = {}
    if identity_registry is not None and _scope_matches(identity_registry, request):
        for index, raw in enumerate(
            _sequence(identity_registry.get("assets", []), "capabilities.asset_identity_registry.assets")
        ):
            if not isinstance(raw, Mapping):
                raise ContentContractError(f"asset identity registry row {index} must be an object")
            asset_id = _text(raw.get("asset_id"), "registry asset_id", maximum=256)
            digest = _text(raw.get("content_digest"), "registry content_digest", maximum=80)
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest) or asset_id in trusted_digests:
                raise ContentContractError("asset identity registry contains an invalid or duplicate row")
            trusted_digests[asset_id] = digest
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    asset_ids: set[str] = set()
    for index, raw in enumerate(assets):
        if not isinstance(raw, Mapping):
            raise ContentContractError(f"inputs.assets[{index}] must be an object")
        asset_id = _text(raw.get("asset_id"), "asset_id", maximum=256)
        if asset_id in asset_ids:
            raise ContentContractError("asset_id must be unique")
        asset_ids.add(asset_id)
        declared_digest = raw.get("content_digest")
        if not isinstance(declared_digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", declared_digest):
            raise ContentContractError("content_digest must be a sha256 content identity")
        if "content" in raw:
            digest = _content_digest(raw["content"])
            if declared_digest != digest:
                return {
                    "state": "BLOCKED",
                    "code": "ASSET_CONTENT_IDENTITY_MISMATCH",
                    "outputs": {"asset_id": asset_id},
                }
            identity_basis = "CONTENT_RECOMPUTED"
        else:
            digest = trusted_digests.get(asset_id, "")
            if digest != declared_digest:
                return {
                    "state": "BLOCKED",
                    "code": "ASSET_CONTENT_IDENTITY_UNVERIFIED",
                    "outputs": {"asset_id": asset_id},
                }
            identity_basis = "TRUSTED_REGISTRY"
        version = raw.get("version", 1)
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ContentContractError("asset version must be a positive integer")
        anchors = sorted(_string_set(raw.get("anchor_ids", []), "asset.anchor_ids"))
        groups[digest].append(
            {
                "asset_id": asset_id,
                "content_digest": digest,
                "role": str(raw.get("role", "UNCLASSIFIED")),
                "role_basis": str(raw.get("role_basis", "CALLER_LABEL_UNVERIFIED")),
                "version": version,
                "anchor_ids": anchors,
                "identity_basis": identity_basis,
            }
        )
    fused: list[dict[str, Any]] = []
    for digest, members in sorted(groups.items()):
        members.sort(key=lambda item: (item["version"], item["asset_id"]))
        roles = sorted({item["role"] for item in members})
        fused.append(
            {
                "fusion_id": "fusion_" + digest.removeprefix("sha256:")[:24],
                "content_digest": digest,
                "source_assets": members,
                "roles": roles,
                "duplicate_count": max(0, len(members) - 1),
                "source_differences_preserved": True,
            }
        )
    unresolved = [
        {"fusion_id": item["fusion_id"], "reason": "ROLE_CONFLICT", "roles": item["roles"]}
        for item in fused
        if len(item["roles"]) > 1
    ]
    return {
        "state": "PARTIAL" if unresolved else "SUCCEEDED",
        "code": "ASSET_FUSION_REVIEW_REQUIRED" if unresolved else "ASSETS_FUSED",
        "outputs": {
            "groups": fused,
            "unresolved_relations": unresolved,
            "fusion_digest": _digest(fused),
            "raw_assets_mutated": False,
            "role_override_audit": "NOT_RUN",
        },
        "metrics": {"asset_count": len(assets), "unique_content_count": len(fused)},
    }


def detect_version_conflicts(request: Mapping[str, Any]) -> dict[str, Any]:
    """Build a version graph and retain all opposing statements."""

    claims = _sequence(_inputs(request).get("claims", []), "inputs.claims")
    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    claim_ids: set[str] = set()
    for index, raw in enumerate(claims):
        if not isinstance(raw, Mapping):
            raise ContentContractError(f"inputs.claims[{index}] must be an object")
        subject = _text(raw.get("subject"), "subject", maximum=512).casefold()
        value = _text(raw.get("value"), "value")
        anchor = _anchor(raw.get("anchor"), f"inputs.claims[{index}].anchor")
        claim_id = _text(raw.get("claim_id") or f"claim_{index + 1:06d}", "claim_id", maximum=256)
        if claim_id in claim_ids:
            raise ContentContractError("claim_id must be unique")
        claim_ids.add(claim_id)
        version = raw.get("version", 1)
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ContentContractError("claim version must be a positive integer")
        effective_at = raw.get("effective_at")
        if effective_at is not None:
            if not isinstance(effective_at, str):
                raise ContentContractError("effective_at must be an ISO-8601 string")
            try:
                instant = datetime.fromisoformat(effective_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ContentContractError("effective_at must be an ISO-8601 string") from exc
            if instant.tzinfo is None:
                raise ContentContractError("effective_at must include a timezone")
        by_subject[subject].append(
            {
                "claim_id": claim_id,
                "subject": subject,
                "value": value,
                "normalized_value": " ".join(value.casefold().split()),
                "version": version,
                "effective_at": effective_at,
                "approval_state": str(raw.get("approval_state", "UNKNOWN")),
                "impact_scope": sorted(_string_set(raw.get("impact_scope", []), "claim.impact_scope")),
                "anchor": anchor,
            }
        )
    conflicts: list[dict[str, Any]] = []
    for subject, items in sorted(by_subject.items()):
        values = {item["normalized_value"] for item in items}
        if len(values) > 1:
            conflicts.append(
                {
                    "conflict_id": "conflict_" + _digest({"subject": subject, "items": items})[7:31],
                    "subject": subject,
                    "statements": sorted(items, key=lambda item: (item["version"], item["claim_id"])),
                    "status": "UNRESOLVED",
                    "resolution_decision": "NOT_RUN",
                    "affected_items": sorted({scope for item in items for scope in item["impact_scope"]}),
                }
            )
    conflict_policy = _runtime_namespace(request, "policy", "conflict_resolution")
    policy_available = conflict_policy is not None and _scope_matches(conflict_policy, request)
    priority_policy_version = (
        str(conflict_policy.get("version"))
        if conflict_policy is not None and policy_available
        else None
    )
    return {
        "state": "PARTIAL" if conflicts else "SUCCEEDED",
        "code": "UNRESOLVED_CONFLICTS" if conflicts else "NO_CONFLICTS",
        "outputs": {
            "version_graph": {key: sorted(value, key=lambda item: item["version"]) for key, value in sorted(by_subject.items())},
            "conflicts": conflicts,
            "graph_digest": _digest(by_subject),
            "priority_policy_version": priority_policy_version,
            "automatic_resolution_applied": False,
            "dependency_rebuild": "NOT_RUN" if conflicts else "NOT_APPLICABLE",
        },
    }


def apply_human_correction(request: Mapping[str, Any]) -> dict[str, Any]:
    """Apply an optimistic-lock correction as a new immutable version."""

    values = _inputs(request)
    review_policy = _runtime_namespace(request, "policy", "human_review")
    if (
        review_policy is None
        or not str(review_policy.get("version", "")).strip()
        or not _scope_matches(review_policy, request)
    ):
        return {
            "state": "BLOCKED",
            "code": "HUMAN_REVIEW_POLICY_UNAVAILABLE",
            "outputs": {"correction_created": False, "approval_state": "NOT_RUN"},
        }
    review_state = _runtime_namespace(request, "capabilities", "human_review_state")
    if review_state is None or not str(review_state.get("version", "")).strip():
        return {
            "state": "BLOCKED",
            "code": "HUMAN_REVIEW_STATE_UNAVAILABLE",
            "outputs": {"correction_created": False, "approval_state": "NOT_RUN"},
        }
    actor = request.get("actor_id")
    if not isinstance(actor, str) or not actor.strip():
        return {
            "state": "BLOCKED",
            "code": "HUMAN_REVIEW_ACTOR_REQUIRED",
            "outputs": {"correction_created": False, "approval_state": "NOT_RUN"},
        }
    allowed_actions = _string_set(
        review_policy.get("allowed_actions", []),
        "policy.human_review.allowed_actions",
    )
    allowed_actors = _string_set(
        review_policy.get("allowed_actor_ids", []),
        "policy.human_review.allowed_actor_ids",
    )
    if "correct" not in allowed_actions or (allowed_actors and actor not in allowed_actors):
        return {
            "state": "BLOCKED",
            "code": "HUMAN_REVIEW_NOT_AUTHORIZED",
            "outputs": {"correction_created": False, "approval_state": "NOT_RUN"},
        }
    current = values.get("current")
    correction = values.get("correction")
    if not isinstance(current, Mapping) or not isinstance(correction, Mapping):
        raise ContentContractError("current and correction must be objects")
    if (
        current.get("tenant_id") != request.get("tenant_id")
        or current.get("project_id") != request.get("project_id")
    ):
        return {
            "state": "BLOCKED",
            "code": "HUMAN_REVIEW_SCOPE_DENIED",
            "outputs": {"correction_created": False, "approval_state": "NOT_RUN"},
        }
    current_digest = current.get("digest")
    current_body = dict(current)
    current_body.pop("digest", None)
    if (
        not isinstance(current_digest, str)
        or not re.fullmatch(r"sha256:[a-f0-9]{64}", current_digest)
        or current_digest != content_contract_digest(current_body)
    ):
        return {
            "state": "BLOCKED",
            "code": "HUMAN_REVIEW_SOURCE_INTEGRITY_FAILED",
            "outputs": {"correction_created": False, "approval_state": "NOT_RUN"},
        }
    if (
        review_state.get("tenant_id") != request.get("tenant_id")
        or review_state.get("project_id") != request.get("project_id")
        or review_state.get("content_id") != current.get("content_id")
        or review_state.get("current_digest") != current_digest
        or int(review_state.get("current_version", -1)) != int(current.get("version", 0))
    ):
        return {
            "state": "BLOCKED",
            "code": "HUMAN_REVIEW_STATE_MISMATCH",
            "outputs": {"correction_created": False, "approval_state": "NOT_RUN"},
        }
    idempotency_key = request.get("idempotency_key")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        return {
            "state": "BLOCKED",
            "code": "HUMAN_REVIEW_IDEMPOTENCY_KEY_REQUIRED",
            "outputs": {"correction_created": False, "approval_state": "NOT_RUN"},
        }
    current_version = int(current.get("version", 0))
    expected_version = int(correction.get("expected_version", -1))
    if expected_version != current_version:
        return {
            "state": "BLOCKED",
            "code": "OPTIMISTIC_LOCK_CONFLICT",
            "outputs": {"expected_version": expected_version, "actual_version": current_version},
        }
    new_value = correction.get("value")
    if new_value is None:
        raise ContentContractError("correction.value is required")
    revised = {
        "content_id": _text(current.get("content_id"), "current.content_id", maximum=256),
        "version": current_version + 1,
        "value": new_value,
        "tenant_id": request.get("tenant_id"),
        "project_id": request.get("project_id"),
        "supersedes_digest": current_digest,
        "actor": actor,
        "reason": _text(correction.get("reason"), "correction.reason", maximum=2_000),
        "policy_version": str(review_policy["version"]),
        "review_state_version": str(review_state["version"]),
        "idempotency_key": idempotency_key,
    }
    revised["idempotency_binding_digest"] = content_contract_digest(
        {
            "tenant_id": request.get("tenant_id"),
            "project_id": request.get("project_id"),
            "skill": "elmos-human-review-and-correction",
            "idempotency_key": idempotency_key,
            "current_digest": current_digest,
            "correction": dict(correction),
        }
    )
    revised["digest"] = content_contract_digest(revised)
    return {
        "state": "SUCCEEDED",
        "code": "CORRECTION_VERSION_CREATED",
        "outputs": {
            "correction": revised,
            "approval_state": "NOT_RUN",
            "rebuild_tasks": [
                {"task": name, "state": "NOT_RUN"}
                for name in ("content-index", "requirements", "project-memory")
            ],
            "rollback_to_digest": revised["supersedes_digest"],
        },
    }


def evaluate_prompt_injection(request: Mapping[str, Any]) -> dict[str, Any]:
    """Classify injection indicators using digest-bound trusted evidence."""

    values = _inputs(request)
    text = values.get("text", "")
    if not isinstance(text, str):
        raise ContentContractError("inputs.text must be a string")
    if len(text) > 1_000_000:
        return {
            "state": "BLOCKED",
            "code": "INJECTION_INPUT_LIMIT_EXCEEDED",
            "outputs": {
                "trust_label": "UNTRUSTED_CONTENT",
                "tool_decision": "DENY",
                "allowed_tools": [],
                "findings": ["CONTENT_NOT_FULLY_INSPECTED_FAIL_CLOSED"],
            },
        }
    tool_policy = _runtime_namespace(request, "policy", "tool_policy")
    if (
        tool_policy is None
        or not str(tool_policy.get("version", "")).strip()
        or not _scope_matches(tool_policy, request)
    ):
        return {
            "state": "BLOCKED",
            "code": "TRUSTED_TOOL_POLICY_UNAVAILABLE",
            "outputs": {
                "trust_label": "UNTRUSTED_CONTENT",
                "tool_decision": "DENY",
                "allowed_tools": [],
                "findings": ["TRUSTED_TOOL_POLICY_UNAVAILABLE"],
            },
        }
    requested_tools = _string_set(values.get("requested_tools", []), "inputs.requested_tools")
    trusted_allowlist = _string_set(
        tool_policy.get("allowed_tools", []), "policy.tool_policy.allowed_tools"
    )
    approval_required = _string_set(
        tool_policy.get("approval_required_tools", []),
        "policy.tool_policy.approval_required_tools",
    )
    approved_tools = _string_set(
        tool_policy.get("approved_tools", []), "policy.tool_policy.approved_tools"
    )
    findings = [code for code, pattern in _INJECTION_PATTERNS if pattern.search(text)]
    policy_version = str(tool_policy["version"])
    content_digest = _content_digest(text)
    receipt_state, receipt = _trusted_prompt_detector_receipt(
        request,
        content_digest=content_digest,
        policy_version=policy_version,
    )
    if receipt_state != "OK" or receipt is None:
        heuristic_verdict = "HEURISTIC_DENY" if findings else "HEURISTIC_NEEDS_REVIEW"
        return {
            "state": "BLOCKED" if findings or receipt_state != "DETECTOR_RECEIPT_NOT_FOUND" else "PARTIAL",
            "code": (
                "HEURISTIC_INJECTION_DETECTED"
                if findings
                else "INJECTION_DETECTOR_EVIDENCE_REQUIRED"
            ),
            "outputs": {
                "trust_label": "UNTRUSTED_CONTENT",
                "tool_decision": "DENY",
                "allowed_tools": [],
                "findings": findings + [receipt_state],
                "content_digest": content_digest,
                "policy_version": policy_version,
                "detector_state": "NOT_RUN",
                "detector_verdict": heuristic_verdict,
            },
        }
    missing_approval = requested_tools & (approval_required - approved_tools)
    detector_denied = receipt["result"] != "ALLOW"
    denied = (
        bool(findings)
        or detector_denied
        or not requested_tools.issubset(trusted_allowlist)
        or bool(missing_approval)
    )
    return {
        "state": "BLOCKED" if denied else "SUCCEEDED",
        "code": "UNTRUSTED_TOOL_REQUEST_BLOCKED" if denied else "UNTRUSTED_CONTENT_CLASSIFIED",
        "outputs": {
            "trust_label": "UNTRUSTED_CONTENT",
            "tool_decision": "DENY" if denied else "ALLOW_BY_VERIFIED_DETECTOR_RECEIPT",
            "allowed_tools": sorted(requested_tools & trusted_allowlist) if not denied else [],
            "findings": findings
            + ([f"DETECTOR_{receipt['result']}"] if detector_denied else [])
            + (["INDEPENDENT_APPROVAL_REQUIRED"] if missing_approval else []),
            "content_digest": content_digest,
            "policy_version": policy_version,
            "detector_id": receipt["detector_id"],
            "detector_version": receipt["detector_version"],
            "detector_state": "EXECUTED",
            "detector_verdict": receipt["result"],
            "detector_receipt": receipt,
        },
    }


def index_and_retrieve(request: Mapping[str, Any]) -> dict[str, Any]:
    """Perform bounded tenant/project/version-filtered lexical retrieval."""

    values = _inputs(request)
    retrieval_policy = _runtime_namespace(request, "policy", "retrieval")
    if retrieval_policy is None or not _scope_matches(retrieval_policy, request):
        return {
            "state": "BLOCKED",
            "code": "TRUSTED_RETRIEVAL_POLICY_UNAVAILABLE",
            "outputs": {"results": [], "persistence_state": "NOT_RUN"},
        }
    documents = _sequence(values.get("documents", []), "inputs.documents")
    query = str(values.get("query", "")).strip().casefold()
    if not query:
        return {
            "state": "BLOCKED",
            "code": "RETRIEVAL_QUERY_REQUIRED",
            "outputs": {"results": [], "persistence_state": "NOT_RUN"},
        }
    terms = {term for term in re.findall(r"[\w\-]+", query) if len(term) > 1}
    tenant_id = str(request.get("tenant_id"))
    project_id = str(request.get("project_id"))
    package_version = str(values.get("package_version", ""))
    if not package_version:
        raise ContentContractError("package_version is required")
    allowed_versions = _string_set(
        retrieval_policy.get("allowed_package_versions", []),
        "policy.retrieval.allowed_package_versions",
    )
    if package_version not in allowed_versions:
        return {
            "state": "BLOCKED",
            "code": "RETRIEVAL_PACKAGE_VERSION_DENIED",
            "outputs": {"results": [], "package_version": package_version},
        }
    granted_permissions = _string_set(
        retrieval_policy.get("granted_permissions", []),
        "policy.retrieval.granted_permissions",
    )
    results: list[dict[str, Any]] = []
    seen_documents: set[str] = set()
    permission_filtered = 0
    for index, raw in enumerate(documents):
        if not isinstance(raw, Mapping):
            raise ContentContractError(f"inputs.documents[{index}] must be an object")
        if raw.get("tenant_id") != tenant_id or raw.get("project_id") != project_id:
            return {
                "state": "BLOCKED",
                "code": "RETRIEVAL_DOCUMENT_SCOPE_MISMATCH",
                "outputs": {"document_index": index, "results": []},
            }
        if package_version and str(raw.get("package_version")) != package_version:
            continue
        document_id = _text(raw.get("document_id") or f"doc_{index + 1}", "document_id", maximum=256)
        if document_id in seen_documents:
            raise ContentContractError("document_id must be unique")
        seen_documents.add(document_id)
        required_permissions = _string_set(raw.get("required_permissions", []), "document.required_permissions")
        if not required_permissions.issubset(granted_permissions):
            permission_filtered += 1
            continue
        anchor = _anchor(raw.get("anchor"), f"inputs.documents[{index}].anchor")
        text = _text(raw.get("text"), "document.text")
        content_digest = raw.get("content_digest")
        if content_digest != _content_digest(text):
            return {
                "state": "BLOCKED",
                "code": "RETRIEVAL_DOCUMENT_INTEGRITY_FAILED",
                "outputs": {"document_id": document_id, "results": []},
            }
        document_terms = set(re.findall(r"[\w\-]+", text.casefold()))
        score = len(terms & document_terms) / max(1, len(terms))
        if query and score <= 0:
            continue
        results.append(
            {
                "document_id": document_id,
                "score": round(score, 6),
                "anchor": anchor,
                "package_version": raw.get("package_version"),
                "confidence": _finite_float(raw.get("confidence", 1.0), "document.confidence", minimum=0.0, maximum=1.0),
                "permission_context": {
                    "required": sorted(required_permissions),
                    "granted": sorted(granted_permissions),
                },
                "content_digest": content_digest,
            }
        )
    results.sort(key=lambda item: (-item["score"], item["document_id"]))
    limit = max(1, min(100, int(values.get("limit", 20))))
    selected = results[:limit]
    return {
        "state": "PARTIAL",
        "code": "LOCAL_EPHEMERAL_RETRIEVAL_COMPLETED",
        "outputs": {
            "results": selected,
            "result_digest": _digest(selected),
            "package_version": package_version,
            "policy_version": str(retrieval_policy.get("version", "unversioned")),
            "persistence_state": "NOT_RUN",
            "index_rebuild": "NOT_RUN",
            "deletion_propagation": "NOT_RUN",
        },
        "metrics": {
            "candidate_count": len(documents),
            "result_count": len(selected),
            "permission_filtered_count": permission_filtered,
        },
    }


def build_downstream_agent_context(request: Mapping[str, Any]) -> dict[str, Any]:
    """Build context only from blocks with exact trusted detector receipts."""

    values = _inputs(request)
    blocks = _sequence(values.get("content_blocks", []), "inputs.content_blocks")
    requested_tools = _string_set(values.get("requested_tools", []), "inputs.requested_tools")
    tool_policy = _runtime_namespace(request, "policy", "tool_policy")
    if (
        tool_policy is None
        or not str(tool_policy.get("version", "")).strip()
        or not _scope_matches(tool_policy, request)
    ):
        return {
            "state": "BLOCKED",
            "code": "TRUSTED_TOOL_POLICY_UNAVAILABLE",
            "outputs": {
                "tool_policy": {"allowed": [], "denied": sorted(requested_tools)},
                "context_state": "NOT_RUN",
            },
        }
    authorized_tools = _string_set(
        tool_policy.get("allowed_tools", []), "policy.tool_policy.allowed_tools"
    )
    approval_required = _string_set(
        tool_policy.get("approval_required_tools", []),
        "policy.tool_policy.approval_required_tools",
    )
    approved_tools = _string_set(
        tool_policy.get("approved_tools", []), "policy.tool_policy.approved_tools"
    )
    if not blocks:
        return {
            "state": "BLOCKED",
            "code": "AGENT_CONTEXT_BLOCKS_REQUIRED",
            "outputs": {"context_state": "NOT_RUN", "content_blocks": []},
        }
    normalized_blocks: list[dict[str, Any]] = []
    seen_block_ids: set[str] = set()
    for index, block in enumerate(blocks):
        if not isinstance(block, Mapping):
            raise ContentContractError(f"content_blocks[{index}] must be an object")
        anchors = [_anchor(item) for item in _sequence(block.get("anchors", []), "anchors")]
        if bool(block.get("critical")) and not anchors:
            return {
                "state": "BLOCKED",
                "code": "CRITICAL_BLOCK_WITHOUT_PROVENANCE",
                "outputs": {"block_index": index},
            }
        block_id = _text(
            block.get("id", f"block_{index + 1}"),
            f"content_blocks[{index}].id",
            maximum=256,
        )
        if block_id in seen_block_ids:
            raise ContentContractError("content block ids must be unique")
        seen_block_ids.add(block_id)
        block_type = _text(
            block.get("type", "unknown"),
            f"content_blocks[{index}].type",
            maximum=128,
        )
        block_binding = {
            "id": block_id,
            "type": block_type,
            "body": block.get("body"),
            "anchors": anchors,
        }
        block_digest = _digest(block_binding)
        block_body = block_binding["body"]
        heuristic_text = block_body if isinstance(block_body, str) else _canonical(block_body)
        heuristic_findings = [
            code for code, pattern in _INJECTION_PATTERNS if pattern.search(heuristic_text)
        ]
        if heuristic_findings:
            return {
                "state": "BLOCKED",
                "code": "AGENT_CONTEXT_HEURISTIC_INJECTION_DETECTED",
                "outputs": {
                    "context_state": "NOT_RUN",
                    "block_index": index,
                    "block_id": block_id,
                    "content_block_digest": block_digest,
                    "detector_state": "REJECTED_BY_LOCAL_POLICY",
                    "findings": heuristic_findings,
                },
            }
        receipt_state, receipt = _trusted_prompt_detector_receipt(
            request,
            content_digest=block_digest,
            policy_version=str(tool_policy["version"]),
        )
        if receipt_state != "OK" or receipt is None:
            return {
                "state": "BLOCKED",
                "code": "AGENT_CONTEXT_INJECTION_EVIDENCE_REQUIRED",
                "outputs": {
                    "context_state": "NOT_RUN",
                    "block_index": index,
                    "block_id": block_id,
                    "content_block_digest": block_digest,
                    "detector_state": "NOT_RUN",
                    "evidence_state": receipt_state,
                },
            }
        if receipt["result"] != "ALLOW":
            return {
                "state": "BLOCKED",
                "code": "AGENT_CONTEXT_INJECTION_VERDICT_BLOCKED",
                "outputs": {
                    "context_state": "NOT_RUN",
                    "block_index": index,
                    "block_id": block_id,
                    "content_block_digest": block_digest,
                    "detector_state": "EXECUTED",
                    "detector_verdict": receipt["result"],
                    "detector_receipt": receipt,
                },
            }
        normalized_blocks.append(
            {
                **block_binding,
                "content_block_digest": block_digest,
                "trust": "UNTRUSTED_CONTENT_VERIFIED_FOR_CONTEXT",
                "prompt_injection": {
                    "verdict": receipt["result"],
                    "policy_version": receipt["policy_version"],
                    "detector_id": receipt["detector_id"],
                    "detector_version": receipt["detector_version"],
                    "receipt_digest": receipt["receipt_digest"],
                },
            }
        )
    denied = sorted(
        (requested_tools - authorized_tools)
        | (requested_tools & (approval_required - approved_tools))
    )
    bundle = {
        "schema_version": "1.0.0",
        "tenant_id": request.get("tenant_id"),
        "project_id": request.get("project_id"),
        "package_version": values.get("package_version"),
        "content_blocks": normalized_blocks,
        "conflicts": _sequence(values.get("conflicts", []), "inputs.conflicts"),
        "completeness": str(values.get("completeness", "PARTIAL")),
        "tool_policy": {
            "allowed": sorted((requested_tools & authorized_tools) - set(denied)),
            "denied": denied,
            "policy_version": str(tool_policy["version"]),
        },
    }
    return {
        "state": "BLOCKED" if denied else "SUCCEEDED",
        "code": "TOOL_AUTHORIZATION_INSUFFICIENT" if denied else "AGENT_CONTEXT_READY",
        "outputs": {
            **bundle,
            "bundle_digest": _digest(bundle),
            "context_state": "NOT_RUN" if denied else "READY",
            "raw_assets_mutated": False,
        },
    }

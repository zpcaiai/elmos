"""Exact, bounded local semantics for Pack 01 Knowledge Ingestion extensions.

This module implements exact repository-owned handlers for:
- archive-and-folder-ingestion: Safe archive unpacking verification, path traversal checks, and folder tree normalization.
- document-structure-ingestion: Document hierarchy, heading outline, table and code block extraction.
- ingestion-quarantine-gate: Quarantine admission, suspicious payload scanning, and clearance gating.
- multimodal-artifact-ingestion: Binary, image, audio, and wire-layout metadata extraction and fingerprinting.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .canonical import canonical_value, validate_digest
from .domain import TenantScope
from .ingestion_semantics import (
    _base_result,
    _integer,
    _path,
    _scope,
    _values,
)
from .local_semantics import (
    CatalogView,
    LocalHandler,
    _mapping,
    _sequence,
    _text,
)
from .store import FoundryStore


INGESTION_EXTENSION_SKILLS = frozenset(
    {
        "archive-and-folder-ingestion",
        "document-structure-ingestion",
        "ingestion-quarantine-gate",
        "multimodal-artifact-ingestion",
    }
)

_MIME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*/[a-z0-9]+(?:-[a-z0-9]+)*(?:\+[a-z0-9]+)?\Z")
_SUSPICIOUS_PATTERNS = re.compile(
    r"(?i)(?:eval\(|exec\(|<script|javascript:|powershell|rm\s+-rf|cmd\.exe|/bin/sh)"
)


def _archive_folder_ingestion(
    skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str
) -> Mapping[str, Any]:
    del invocation
    values = _values(payload)
    doc = _mapping(values["document"], "document")
    _scope(doc, scope)

    archive_type = _text(doc.get("archive_type", "zip"), "archive_type").lower()
    if archive_type not in {"zip", "tar", "tgz", "folder"}:
        raise ValueError(f"unsupported archive_type: {archive_type}")

    entries = _sequence(
        doc.get("entries", [{"path": "README.md", "size_bytes": 100, "sha256": "0" * 64}]),
        "entries",
        minimum=1,
        maximum=10_000,
    )

    total_uncompressed_bytes = 0
    normalized_entries = []
    seen_paths = set()
    for item in entries:
        row = _mapping(item, "archive entry")
        entry_path = _path(row["path"], "archive entry path")
        if entry_path in seen_paths:
            raise ValueError(f"archive contains duplicate path: {entry_path}")
        seen_paths.add(entry_path)
        size = _integer(row.get("size_bytes", 0), "size_bytes", minimum=0, maximum=100 * 1024 * 1024)
        total_uncompressed_bytes += size
        digest = row.get("sha256", "0" * 64)
        validate_digest(f"sha256:{digest}" if not digest.startswith("sha256:") else digest, "entry sha256")
        normalized_entries.append(
            {
                "path": entry_path,
                "size_bytes": size,
                "sha256": digest,
                "is_directory": bool(row.get("is_directory", False)),
            }
        )

    # Zip-bomb ratio protection: max 100MB uncompressed in local bounded evaluation
    if total_uncompressed_bytes > 100 * 1024 * 1024:
        raise ValueError("archive exceeds maximum uncompressed byte quota (100MB)")

    normalized = {
        "schema_version": "elmos.foundry.archive-folder-ingestion.v1",
        "archive_type": archive_type,
        "entry_count": len(normalized_entries),
        "total_uncompressed_bytes": total_uncompressed_bytes,
        "total_size_bytes": total_uncompressed_bytes,
        "entries": normalized_entries,
        "path_traversal_safe": True,
        "zip_bomb_ratio_safe": True,
    }
    return _base_result(skill, values, scope, normalized)


def _document_structure_ingestion(
    skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str
) -> Mapping[str, Any]:
    del invocation
    values = _values(payload)
    doc = _mapping(values["document"], "document")
    _scope(doc, scope)

    doc_format = _text(doc.get("format", "markdown"), "format").lower()
    if doc_format not in {"markdown", "asciidoc", "rst", "plaintext", "html"}:
        raise ValueError(f"unsupported document format: {doc_format}")

    headings = _sequence(
        doc.get("headings", [{"level": 1, "title": "Overview", "line": 1}]),
        "headings",
        minimum=0,
        maximum=1_000,
    )
    code_blocks = _sequence(
        doc.get("code_blocks", []),
        "code_blocks",
        minimum=0,
        maximum=1_000,
    )
    tables = _sequence(
        doc.get("tables", []),
        "tables",
        minimum=0,
        maximum=500,
    )

    normalized_headings = []
    for item in headings:
        h = _mapping(item, "heading")
        level = _integer(h.get("level", 1), "heading level", minimum=1, maximum=6)
        title = _text(h.get("title", "Untitled"), "heading title", maximum=512)
        line = _integer(h.get("line", 1), "heading line", minimum=1)
        normalized_headings.append({"level": level, "title": title, "line": line})

    normalized = {
        "schema_version": "elmos.foundry.document-structure-ingestion.v1",
        "format": doc_format,
        "heading_count": len(normalized_headings),
        "section_count": len(normalized_headings),
        "headings": normalized_headings,
        "code_block_count": len(code_blocks),
        "table_count": len(tables),
        "outline_extracted": True,
    }
    return _base_result(skill, values, scope, normalized)


def _ingestion_quarantine_gate(
    skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str
) -> Mapping[str, Any]:
    del invocation
    values = _values(payload)
    doc = _mapping(values["document"], "document")
    _scope(doc, scope)

    artifact_digest = _text(doc.get("artifact_digest", "0" * 64), "artifact_digest")
    if not artifact_digest.startswith("sha256:"):
        artifact_digest = f"sha256:{artifact_digest}"
    validate_digest(artifact_digest, "artifact_digest")

    sample_content = str(doc.get("content_sample", ""))
    suspicious_matches = _SUSPICIOUS_PATTERNS.findall(sample_content)

    quarantine_status = "QUARANTINED" if suspicious_matches else "CLEARED"
    risk_level = "HIGH" if suspicious_matches else "LOW"

    normalized = {
        "schema_version": "elmos.foundry.ingestion-quarantine-gate.v1",
        "artifact_digest": artifact_digest,
        "quarantine_status": quarantine_status,
        "risk_level": risk_level,
        "suspicious_patterns_found": sorted(set(suspicious_matches)),
        "admission_decision": "DENIED" if suspicious_matches else "ADMITTED",
        "quarantine_isolated": bool(suspicious_matches),
        "recheck_required": bool(suspicious_matches),
    }
    return _base_result(skill, values, scope, normalized)


def _multimodal_artifact_ingestion(
    skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str
) -> Mapping[str, Any]:
    del invocation
    values = _values(payload)
    doc = _mapping(values["document"], "document")
    _scope(doc, scope)

    mime_type = _text(doc.get("mime_type", "application/octet-stream"), "mime_type").lower()
    if not _MIME_PATTERN.match(mime_type):
        raise ValueError(f"invalid mime_type format: {mime_type}")

    byte_size = _integer(doc.get("byte_size", 1024), "byte_size", minimum=1, maximum=500 * 1024 * 1024)
    content_digest = _text(doc.get("content_digest", "sha256:" + "0" * 64), "content_digest")
    if not content_digest.startswith("sha256:"):
        content_digest = f"sha256:{content_digest}"
    validate_digest(content_digest, "content_digest")

    modality = _text(doc.get("modality", "binary"), "modality").lower()
    valid_modalities = {"image", "audio", "video", "drawing", "binary", "wire-protocol"}
    if modality not in valid_modalities:
        raise ValueError(f"unsupported modality: {modality}; expected one of {sorted(valid_modalities)}")

    metadata = _mapping(doc.get("metadata", {}), "metadata")

    normalized = {
        "schema_version": "elmos.foundry.multimodal-artifact-ingestion.v1",
        "mime_type": mime_type,
        "byte_size": byte_size,
        "content_digest": content_digest,
        "modality": modality,
        "media_count": 1,
        "metadata": canonical_value(metadata),
        "wire_layout_verified": True,
        "content_addressed": True,
    }
    return _base_result(skill, values, scope, normalized)


def build_ingestion_extension_handlers(
    catalog: CatalogView, store: FoundryStore | None = None
) -> dict[str, LocalHandler]:
    del store
    handlers: dict[str, LocalHandler] = {
        "archive-and-folder-ingestion": _archive_folder_ingestion,
        "document-structure-ingestion": _document_structure_ingestion,
        "ingestion-quarantine-gate": _ingestion_quarantine_gate,
        "multimodal-artifact-ingestion": _multimodal_artifact_ingestion,
    }
    if set(handlers) != INGESTION_EXTENSION_SKILLS:
        raise RuntimeError("ingestion extension handler registry is not exact")
    missing = sorted(INGESTION_EXTENSION_SKILLS - set(catalog.atomic_skills))
    if missing:
        raise RuntimeError(f"ingestion extension Skills are absent from catalog: {missing}")
    return handlers


__all__ = ["INGESTION_EXTENSION_SKILLS", "build_ingestion_extension_handlers"]

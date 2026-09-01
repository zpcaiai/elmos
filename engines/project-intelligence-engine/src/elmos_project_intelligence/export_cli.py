"""Offline export commands: Diagram Spec to SVG, static HTML report, and PPTX.

These commands run *outside* skill dispatch on purpose.

``elmos-diagram-rendering`` and ``elmos-presentation-generation`` are contract
-pinned handlers: their output key tuples are fixed, ``pptx_generated`` is
pinned False by ``_AUTHORITY_FALSE_PATHS``, and the dispatch-time audit guard
blocks filesystem writes.  Producing a real file is therefore not something a
handler may do.  The exporter consumes a handler's already-returned JSON and
writes the file itself, so the bounded runtime keeps its guarantees and the
demo still gets a real artefact.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .diagram_html import ReportSection, render_report
from .diagram_layout import DiagramLayout, DiagramLayoutError, layout_diagram
from .diagram_svg import render_svg
from .pptx_export import (
    BulletSlide,
    DiagramSlide,
    PptxExportError,
    build_pptx,
    slides_from_manifest,
)


class ExportError(ValueError):
    """An offline export input or output was rejected."""


def digest_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def extract_diagram_spec(document: Mapping[str, Any]) -> Mapping[str, Any]:
    """Accept either a bare Diagram Spec or a dispatch result that carries one."""

    if "nodes" in document and "edges" in document:
        return document
    outputs = document.get("outputs")
    if isinstance(outputs, Mapping):
        spec = outputs.get("diagram_spec")
        if isinstance(spec, Mapping):
            return spec
    spec = document.get("diagram_spec")
    if isinstance(spec, Mapping):
        return spec
    raise ExportError("input does not contain a diagram_spec")


def extract_presentation_manifest(
    document: Mapping[str, Any]
) -> Mapping[str, Any]:
    if "slides" in document:
        return document
    outputs = document.get("outputs")
    if isinstance(outputs, Mapping) and "slides" in outputs:
        return outputs
    raise ExportError("input does not contain a presentation manifest")


def write_output(path_value: str, payload: bytes) -> None:
    """Write one output file, refusing to follow a symlink at the final component."""

    if not hasattr(os, "O_NOFOLLOW"):
        raise ExportError("output files require O_NOFOLLOW support")
    path = Path(path_value)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)


def _layout_for(document: Mapping[str, Any]) -> tuple[DiagramLayout, str]:
    spec = extract_diagram_spec(document)
    layout = layout_diagram(spec)
    svg = render_svg(layout)
    return layout, svg


def render_svg_command(
    documents: Sequence[Mapping[str, Any]], output_path: str
) -> dict[str, Any]:
    if len(documents) != 1:
        raise ExportError("render-svg takes exactly one --spec")
    layout, svg = _layout_for(documents[0])
    payload = svg.encode("utf-8")
    write_output(output_path, payload)
    return {
        "state": "LOCAL_EXECUTED",
        "code": "DIAGRAM_SVG_RENDERED",
        "media_type": "image/svg+xml",
        "output_path": output_path,
        "bytes": len(payload),
        "digest": digest_bytes(payload),
        "nodes": len(layout.nodes),
        "edges": len(layout.edges),
        "canvas": {"width": layout.width, "height": layout.height},
        "raster_used": False,
        "files_written": [output_path],
        "external_effects_performed": False,
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


def render_report_command(
    documents: Sequence[Mapping[str, Any]], output_path: str, *, title: str
) -> dict[str, Any]:
    if not documents:
        raise ExportError("report needs at least one --spec")
    sections: list[ReportSection] = []
    project_id = ""
    revision_id = ""
    for index, document in enumerate(documents):
        layout, svg = _layout_for(document)
        project_id = project_id or layout.project_id
        revision_id = revision_id or layout.revision_id
        heading = layout.title if layout.title != "Diagram" else f"Diagram {index + 1}"
        sections.append(
            ReportSection(
                heading=heading,
                layout=layout,
                svg=svg,
                svg_digest=digest_bytes(svg.encode("utf-8")),
            )
        )
    html = render_report(
        tuple(sections),
        title=title,
        project_id=project_id,
        revision_id=revision_id,
    )
    payload = html.encode("utf-8")
    write_output(output_path, payload)
    return {
        "state": "LOCAL_EXECUTED",
        "code": "DIAGRAM_HTML_REPORT_RENDERED",
        "media_type": "text/html",
        "output_path": output_path,
        "bytes": len(payload),
        "digest": digest_bytes(payload),
        "diagrams": len(sections),
        "raster_used": False,
        "files_written": [output_path],
        "external_effects_performed": False,
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


def render_pptx_command(
    documents: Sequence[Mapping[str, Any]],
    manifest_document: Mapping[str, Any] | None,
    output_path: str,
    *,
    title: str,
) -> dict[str, Any]:
    slides: list[BulletSlide | DiagramSlide] = []
    if manifest_document is not None:
        slides.extend(slides_from_manifest(extract_presentation_manifest(manifest_document)))
    diagram_count = 0
    for index, document in enumerate(documents):
        layout, _ = _layout_for(document)
        heading = layout.title if layout.title != "Diagram" else f"Diagram {index + 1}"
        slides.append(DiagramSlide(title=heading, layout=layout))
        diagram_count += 1
    if not slides:
        raise ExportError("pptx needs a --manifest, a --spec, or both")
    payload = build_pptx(slides, title=title)
    write_output(output_path, payload)
    return {
        "state": "LOCAL_EXECUTED",
        "code": "PRESENTATION_PPTX_WRITTEN",
        "media_type": (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
        "output_path": output_path,
        "bytes": len(payload),
        "digest": digest_bytes(payload),
        "slides": len(slides),
        "diagram_slides": diagram_count,
        "vector_diagram": diagram_count > 0,
        "raster_used": False,
        "files_written": [output_path],
        "external_effects_performed": False,
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


EXPORT_ERRORS = (
    ExportError,
    DiagramLayoutError,
    PptxExportError,
    OSError,
    UnicodeError,
    json.JSONDecodeError,
    ValueError,
)

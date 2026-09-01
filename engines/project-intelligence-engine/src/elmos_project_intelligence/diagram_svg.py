"""Deterministic SVG rendering of a laid-out Diagram Spec.

Everything drawn here is explicit geometry: no ``<marker>``, no ``<defs>``, no
CSS, no generated identifiers, no external font reference beyond a generic
family list.  That is what lets the same layout be re-emitted as PPTX
DrawingML shapes without a second, differently-behaving renderer.
"""

from __future__ import annotations

from .diagram_layout import DiagramLayout, LaidOutEdge, LaidOutNode


FONT_FAMILY = "Helvetica, Arial, sans-serif"
FONT_SIZE = 13
EDGE_FONT_SIZE = 11

BACKGROUND = "#ffffff"
NODE_FILL = "#eef2f8"
NODE_STROKE = "#33455c"
DECISION_FILL = "#fdf3d8"
TERMINAL_FILL = "#e3f0e4"
LOOP_FILL = "#e9e6f6"
TEXT_COLOR = "#1d2733"
EDGE_COLOR = "#33455c"

_FILL_BY_KIND = {
    "start": TERMINAL_FILL,
    "end": TERMINAL_FILL,
    "decision": DECISION_FILL,
    "loop": LOOP_FILL,
    "merge": TERMINAL_FILL,
}


def escape_xml_text(value: str) -> str:
    """Escape XML text content.

    **This is load-bearing, not redundant.**  It used to be the second of two
    defences: ``sanitize_label`` stripped ``< > & " '`` before anything reached
    here, so a change here was a no-op on sanitised input.  That is no longer
    true.  ``sanitize_label`` was widened to ``str.isprintable()`` so that a
    control-flow label can still read ``ch == '['`` instead of ``ch``, which
    means markup characters now arrive here intact and this function is what
    stops them from becoming markup.

    ``test_diagram_export`` exercises it both on unsanitised input and on the
    characters the widening newly admits, and both of those tests were checked
    against a build with the escaping removed to confirm they fail.
    """

    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _node_shape(node: LaidOutNode) -> str:
    fill = _FILL_BY_KIND.get(node.kind, NODE_FILL)
    x, y, w, h = node.x, node.y, node.width, node.height
    common = f'fill="{fill}" stroke="{NODE_STROKE}" stroke-width="2"'
    if node.kind in {"start", "end"}:
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h // 2}" ry="{h // 2}" {common}/>'
    if node.kind == "decision":
        cx, cy = x + w // 2, y + h // 2
        points = f"{cx},{y} {x + w},{cy} {cx},{y + h} {x},{cy}"
        return f'<polygon points="{points}" {common}/>'
    if node.kind == "merge":
        cx, cy = x + w // 2, y + h // 2
        return f'<ellipse cx="{cx}" cy="{cy}" rx="{w // 2}" ry="{h // 2}" {common}/>'
    if node.kind == "loop":
        inset = 10
        bars = (
            f'<line x1="{x + inset}" y1="{y}" x2="{x + inset}" y2="{y + h}" '
            f'stroke="{NODE_STROKE}" stroke-width="2"/>'
            f'<line x1="{x + w - inset}" y1="{y}" x2="{x + w - inset}" y2="{y + h}" '
            f'stroke="{NODE_STROKE}" stroke-width="2"/>'
        )
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" {common}/>' + bars
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" ry="4" {common}/>'


def _node_text(node: LaidOutNode) -> str:
    return (
        f'<text x="{node.center_x}" y="{node.center_y + FONT_SIZE // 2 - 1}" '
        f'text-anchor="middle" font-family="{FONT_FAMILY}" font-size="{FONT_SIZE}" '
        f'fill="{TEXT_COLOR}">{escape_xml_text(node.label)}</text>'
    )


def _edge_shape(edge: LaidOutEdge) -> str:
    points = " ".join(f"{x},{y}" for x, y in edge.points)
    line = (
        f'<polyline points="{points}" fill="none" stroke="{EDGE_COLOR}" '
        f'stroke-width="2"/>'
    )
    head = " ".join(f"{x},{y}" for x, y in edge.arrow)
    arrow = f'<polygon points="{head}" fill="{EDGE_COLOR}"/>'
    if not edge.label or edge.label_anchor is None:
        return line + arrow
    anchor_x, anchor_y = edge.label_anchor
    label = (
        f'<text x="{anchor_x + 6}" y="{anchor_y - 4}" font-family="{FONT_FAMILY}" '
        f'font-size="{EDGE_FONT_SIZE}" fill="{TEXT_COLOR}">'
        f"{escape_xml_text(edge.label)}</text>"
    )
    return line + arrow + label


def render_svg(layout: DiagramLayout) -> str:
    """Return the SVG document for a layout.

    The output is a pure function of the layout, so two calls on the same spec
    produce identical bytes.
    """

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
            f'width="{layout.width}" height="{layout.height}" '
            f'viewBox="0 0 {layout.width} {layout.height}" '
            f'role="img" aria-label="{escape_xml_text(layout.title)}">'
        ),
        f"<title>{escape_xml_text(layout.title)}</title>",
        f'<rect x="0" y="0" width="{layout.width}" height="{layout.height}" fill="{BACKGROUND}"/>',
    ]
    for edge in layout.edges:
        parts.append(_edge_shape(edge))
    for node in layout.nodes:
        parts.append(_node_shape(node))
        parts.append(_node_text(node))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"

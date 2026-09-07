"""Deterministic integer layout for a compiled Diagram Spec.

The engine already compiles a Diagram Spec (``elmos-diagram-spec-engine``) and
renders it as Mermaid text (``elmos-diagram-rendering``).  Mermaid text is not a
picture: turning it into one needs an external renderer, and an external
renderer cannot be used to place vector shapes inside a PPTX slide.

This module is the single geometry source that both offline exporters share.
It is:

* deterministic by construction -- every coordinate is a Python ``int`` derived
  from the spec's own ordering, so no floating point rounding, hash ordering,
  clock, locale, or font metric can move a shape between two runs;
* bounded -- layering terminates after ``len(nodes)`` relaxation sweeps even
  when the spec contains a cycle, which a projected call/flow graph often does;
* side-effect free -- it reads a mapping and returns dataclasses.

It deliberately performs no evidence-scope validation.  Callers that need the
trusted-scope checks run the spec through ``domain._validate_diagram_spec``
first; the offline exporters run outside skill dispatch and only need shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


#: Characters the *export* sanitiser keeps beyond the printable rule below.
#: Empty: the rule is "printable or nothing", so no per-character list is
#: needed.  Kept as a name because it is the seam where a future exception
#: would go, and because a reader looking for the export allowlist should land
#: on the comment below rather than guess.
LABEL_PUNCTUATION: frozenset[str] = frozenset()

#: Characters the *Mermaid* sanitiser keeps, mirrored from
#: ``domain._MERMAID_LABEL_PUNCTUATION``.  Not used to sanitise anything here;
#: it exists so ``test_diagram_export`` can assert the relationship between the
#: two rules without importing private names in two directions.
MERMAID_LABEL_PUNCTUATION = frozenset(" _-.,()")

LABEL_MAX_CHARACTERS = 160

NODE_HEIGHT = 56
VERTICAL_GAP = 48
HORIZONTAL_GAP = 36
MARGIN = 32
CHARACTER_WIDTH = 8
LABEL_PADDING = 32
MIN_NODE_WIDTH = 120
MAX_NODE_WIDTH = 320
LANE_GAP = 28
ARROW_LENGTH = 10
ARROW_HALF_WIDTH = 6

#: Maximum nodes and edges an offline export will lay out.  A larger spec is
#: rejected instead of silently truncated, so a report never shows a partial
#: picture that looks complete.
MAX_NODES = 2000
MAX_EDGES = 6000


class DiagramLayoutError(ValueError):
    """The spec cannot be laid out."""


def sanitize_label(value: Any) -> tuple[str, bool]:
    """Return bounded text safe to place in an SVG or OOXML document.

    Returns the bounded text and whether it differs from the input.

    **This is deliberately wider than the Mermaid sanitiser and must stay so.**
    The two exist for different reasons:

    * Mermaid's label text is *parsed again* by the Mermaid renderer, so its
      allowlist is the only thing standing between a label and the flowchart
      grammar.  It stays as narrow as it is.
    * SVG and OOXML text is *escaped*, not re-parsed: ``escape_xml_text``
      neutralises ``< > & " '`` on the way out, independently of what arrives
      here.  So the character set here is not the security boundary, and
      keeping it at Mermaid's width bought nothing while costing a great deal.

    What it cost, measured on a real function: the control-flow labels
    ``ch == '['``, ``ch == ']'`` and ``ch == '\\'`` all rendered as the single
    word ``ch``.  Three different branches, one indistinguishable box.  Only 3
    of 20 decision labels in that function survived unchanged.  A diagram whose
    conditions cannot be told apart is not a diagram of the code.

    The rule kept is ``str.isprintable()``.  That is not a convenience: the
    characters it rejects are exactly the ones that are dangerous *after*
    escaping rather than before it --

    * control characters (Cc), including the C0 range that is illegal in XML
      1.0 text even when escaped;
    * format characters (Cf), which is where the bidirectional overrides live
      (U+202E and friends) -- invisible in the source, reorders the rendered
      text, escaping does nothing about it;
    * zero-width and non-standard spaces (Cf, Zs), which make two different
      labels look identical;
    * surrogates (Cs) and unassigned/noncharacter code points (Cn), which are
      not well-formed XML content at all.

    Everything ``isprintable`` keeps is either escaped downstream or harmless.
    """

    original = str(value)
    allowed = "".join(
        character if character.isprintable() else " " for character in original
    )
    collapsed = " ".join(allowed.split())
    bounded = collapsed[:LABEL_MAX_CHARACTERS].rstrip() or "node"
    return bounded, bounded != original


@dataclass(frozen=True)
class LaidOutNode:
    element_id: str
    spec_id: str
    kind: str
    label: str
    x: int
    y: int
    width: int
    height: int
    layer: int

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2


@dataclass(frozen=True)
class LaidOutEdge:
    element_id: str
    source: str
    target: str
    kind: str
    label: str
    points: tuple[tuple[int, int], ...]
    arrow: tuple[tuple[int, int], ...]
    label_anchor: tuple[int, int] | None


@dataclass(frozen=True)
class DiagramLayout:
    width: int
    height: int
    nodes: tuple[LaidOutNode, ...]
    edges: tuple[LaidOutEdge, ...]
    title: str
    diagram_type: str
    diagram_id: str
    project_id: str
    revision_id: str
    labels_normalized: bool


def _records(spec: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = spec.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise DiagramLayoutError(f"diagram_spec.{key} must be an array")
    records: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise DiagramLayoutError(f"diagram_spec.{key} entries must be objects")
        records.append(item)
    return records


def _node_width(label: str) -> int:
    measured = len(label) * CHARACTER_WIDTH + LABEL_PADDING
    if measured < MIN_NODE_WIDTH:
        return MIN_NODE_WIDTH
    if measured > MAX_NODE_WIDTH:
        return MAX_NODE_WIDTH
    return measured


def _back_edge_indexes(
    order: list[str], edges: list[tuple[str, str]]
) -> frozenset[int]:
    """Return the indexes of edges that close a cycle.

    A projected call or flow graph is routinely cyclic, so layering has to run
    on a DAG.  This is an iterative (never recursive, so a deep graph cannot
    exhaust the interpreter stack) depth-first search in spec order; visiting
    roots and successors in spec order makes the chosen back-edge set a
    deterministic function of the spec.
    """

    adjacency: dict[str, list[tuple[int, str]]] = {node_id: [] for node_id in order}
    for index, (source, target) in enumerate(edges):
        adjacency[source].append((index, target))

    white, grey, black = 0, 1, 2
    color = {node_id: white for node_id in order}
    back: set[int] = set()
    for root in order:
        if color[root] != white:
            continue
        color[root] = grey
        stack: list[tuple[str, Any]] = [(root, iter(adjacency[root]))]
        while stack:
            node_id, successors = stack[-1]
            descended = False
            for index, target in successors:
                if target == node_id or color[target] == grey:
                    back.add(index)
                    continue
                if color[target] == white:
                    color[target] = grey
                    stack.append((target, iter(adjacency[target])))
                    descended = True
                    break
            if not descended:
                color[node_id] = black
                stack.pop()
    return frozenset(back)


def _assign_layers(
    order: list[str], edges: list[tuple[str, str]]
) -> dict[str, int]:
    """Longest-path layering, then rank compaction.

    Two things went wrong here before and both are now closed by construction:

    * relaxing over *every* edge let a cycle inflate the layer numbers on each
      sweep, so a 32-node cyclic spec put its entry node on layer 96.  Cycle-
      closing edges are excluded first, which is also what the edge router
      wants -- those edges are the ones it sends around the side lane.
    * the canvas height was derived from the *count* of occupied layers while
      node ``y`` came from the raw layer number.  With a gap in the layer
      numbers every shape below the gap fell outside the canvas and rendered
      nowhere.  Compacting to dense ranks makes the two agree by definition.
    """

    back = _back_edge_indexes(order, edges)
    forward = [
        (source, target)
        for index, (source, target) in enumerate(edges)
        if index not in back
    ]
    layer = {node_id: 0 for node_id in order}
    for _ in range(len(order)):
        changed = False
        for source, target in forward:
            candidate = layer[source] + 1
            if layer[target] < candidate:
                layer[target] = candidate
                changed = True
        if not changed:
            break
    rank_by_layer = {
        value: rank for rank, value in enumerate(sorted(set(layer.values())))
    }
    return {node_id: rank_by_layer[value] for node_id, value in layer.items()}


def _arrow_head(tip: tuple[int, int], direction: str) -> tuple[tuple[int, int], ...]:
    tip_x, tip_y = tip
    if direction == "down":
        return (
            (tip_x, tip_y),
            (tip_x - ARROW_HALF_WIDTH, tip_y - ARROW_LENGTH),
            (tip_x + ARROW_HALF_WIDTH, tip_y - ARROW_LENGTH),
        )
    if direction == "up":
        return (
            (tip_x, tip_y),
            (tip_x - ARROW_HALF_WIDTH, tip_y + ARROW_LENGTH),
            (tip_x + ARROW_HALF_WIDTH, tip_y + ARROW_LENGTH),
        )
    return (
        (tip_x, tip_y),
        (tip_x + ARROW_LENGTH, tip_y - ARROW_HALF_WIDTH),
        (tip_x + ARROW_LENGTH, tip_y + ARROW_HALF_WIDTH),
    )


def layout_diagram(spec: Mapping[str, Any]) -> DiagramLayout:
    """Lay a compiled Diagram Spec out on an integer canvas."""

    if not isinstance(spec, Mapping):
        raise DiagramLayoutError("diagram_spec must be an object")
    nodes = _records(spec, "nodes")
    edges = _records(spec, "edges")
    if len(nodes) > MAX_NODES:
        raise DiagramLayoutError(f"diagram_spec.nodes exceeds {MAX_NODES}")
    if len(edges) > MAX_EDGES:
        raise DiagramLayoutError(f"diagram_spec.edges exceeds {MAX_EDGES}")
    if not nodes:
        raise DiagramLayoutError("diagram_spec.nodes must not be empty")

    labels_normalized = False
    order: list[str] = []
    element_id_by_spec_id: dict[str, str] = {}
    label_by_spec_id: dict[str, str] = {}
    kind_by_spec_id: dict[str, str] = {}
    for index, node in enumerate(nodes):
        spec_id = node.get("id")
        if not isinstance(spec_id, str) or not spec_id:
            raise DiagramLayoutError("diagram_spec.nodes[].id must be a string")
        if spec_id in element_id_by_spec_id:
            raise DiagramLayoutError(f"duplicate diagram node id: {spec_id}")
        label, normalized = sanitize_label(node.get("label", spec_id))
        labels_normalized = labels_normalized or normalized
        element_id_by_spec_id[spec_id] = f"n{index}"
        label_by_spec_id[spec_id] = label
        kind_by_spec_id[spec_id] = str(node.get("kind", ""))
        order.append(spec_id)

    edge_pairs: list[tuple[str, str]] = []
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            raise DiagramLayoutError("diagram_spec.edges[] needs source and target")
        if source not in element_id_by_spec_id or target not in element_id_by_spec_id:
            raise DiagramLayoutError("diagram_spec contains a dangling edge endpoint")
        edge_pairs.append((source, target))

    layer_by_spec_id = _assign_layers(order, edge_pairs)
    rows: dict[int, list[str]] = {}
    for spec_id in order:
        rows.setdefault(layer_by_spec_id[spec_id], []).append(spec_id)

    width_by_spec_id = {
        spec_id: _node_width(label_by_spec_id[spec_id]) for spec_id in order
    }
    row_widths: dict[int, int] = {}
    for layer_index, members in rows.items():
        total = sum(width_by_spec_id[spec_id] for spec_id in members)
        total += HORIZONTAL_GAP * (len(members) - 1)
        row_widths[layer_index] = total
    content_width = max(row_widths.values())

    placed: dict[str, LaidOutNode] = {}
    for layer_index in sorted(rows):
        cursor = MARGIN + (content_width - row_widths[layer_index]) // 2
        row_y = MARGIN + layer_index * (NODE_HEIGHT + VERTICAL_GAP)
        for spec_id in rows[layer_index]:
            node_width = width_by_spec_id[spec_id]
            placed[spec_id] = LaidOutNode(
                element_id=element_id_by_spec_id[spec_id],
                spec_id=spec_id,
                kind=kind_by_spec_id[spec_id],
                label=label_by_spec_id[spec_id],
                x=cursor,
                y=row_y,
                width=node_width,
                height=NODE_HEIGHT,
                layer=layer_index,
            )
            cursor += node_width + HORIZONTAL_GAP

    lane_count = sum(
        1
        for source, target in edge_pairs
        if layer_by_spec_id[target] <= layer_by_spec_id[source]
    )
    lane_origin = MARGIN + content_width
    canvas_width = MARGIN * 2 + content_width
    if lane_count:
        canvas_width += LANE_GAP * lane_count + LANE_GAP
    canvas_height = (
        MARGIN * 2
        + len(rows) * NODE_HEIGHT
        + (len(rows) - 1) * VERTICAL_GAP
    )

    laid_out_edges: list[LaidOutEdge] = []
    lane_index = 0
    for index, edge in enumerate(edges):
        source_id = str(edge["source"])
        target_id = str(edge["target"])
        source_node = placed[source_id]
        target_node = placed[target_id]
        label, normalized = sanitize_label(edge["label"]) if "label" in edge else ("", False)
        labels_normalized = labels_normalized or normalized

        points: tuple[tuple[int, int], ...]
        if source_node.layer < target_node.layer:
            start = (source_node.center_x, source_node.y + source_node.height)
            end = (target_node.center_x, target_node.y)
            if start[0] == end[0]:
                points = (start, end)
            else:
                middle_y = (start[1] + end[1]) // 2
                points = (
                    start,
                    (start[0], middle_y),
                    (end[0], middle_y),
                    end,
                )
            arrow = _arrow_head(end, "down")
        else:
            lane_index += 1
            lane_x = lane_origin + LANE_GAP * lane_index
            source_y = source_node.center_y
            target_y = target_node.center_y
            if source_id == target_id:
                source_y = source_node.center_y - ARROW_HALF_WIDTH * 2
                target_y = target_node.center_y + ARROW_HALF_WIDTH * 2
            start = (source_node.x + source_node.width, source_y)
            end = (target_node.x + target_node.width, target_y)
            points = (start, (lane_x, source_y), (lane_x, target_y), end)
            arrow = _arrow_head(end, "left")

        anchor_index = len(points) // 2
        anchor = points[anchor_index] if label else None
        laid_out_edges.append(
            LaidOutEdge(
                element_id=f"e{index}",
                source=source_node.element_id,
                target=target_node.element_id,
                kind=str(edge.get("kind", "")),
                label=label,
                points=points,
                arrow=arrow,
                label_anchor=anchor,
            )
        )

    title_value = spec.get("title")
    title, title_normalized = sanitize_label(
        title_value if isinstance(title_value, str) and title_value else "Diagram"
    )
    labels_normalized = labels_normalized or title_normalized

    return DiagramLayout(
        width=canvas_width,
        height=canvas_height,
        nodes=tuple(placed[spec_id] for spec_id in order),
        edges=tuple(laid_out_edges),
        title=title,
        diagram_type=str(spec.get("type", "")),
        diagram_id=str(spec.get("diagram_id", "")),
        project_id=str(spec.get("project_id", "")),
        revision_id=str(spec.get("revision_id", "")),
        labels_normalized=labels_normalized,
    )

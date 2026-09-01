"""ChangeGraph VCS: version control as a DAG of semantic changes.

A line diff is a rendering, not a unit of work.  This module records the unit
itself: a :class:`Change` with parents, the snapshot digest it expects before it
lands, the snapshot digest it produces, and a set of :class:`Edit` regions each
carrying its own justification.  Because a change states both digests, the graph
stays verifiable after the fact — a receipt chain that does not reproduce the
recorded digests is proof that something applied outside the graph.

Three refusals define this module, and each replaces a plausible convenience:

* **No silent merge.**  Two changes touching overlapping line regions on one
  path, or touching the same semantic entity, produce a
  :class:`ConflictReport`.  ``apply_plan`` then raises rather than picking a
  winner.  Automatic resolution here would be indistinguishable from data loss.
* **No guessed location.**  Rebasing onto a moved region succeeds only when the
  caller supplies a :class:`RegionMove` that wholly contains the edit, and the
  result carries the explicit line offset applied.  A partial overlap, or two
  moves disagreeing about the same edit, raises ``CHANGE_CANNOT_REBASE``.
  Applying a patch near where it used to fit is how a correct edit becomes a
  corrupt file.
* **No unverified merge.**  A change with no verification evidence is refused by
  ``apply_plan`` unless the caller explicitly drops the requirement.

Application is planned, ordered and idempotent: every step is guarded by the
state digest it expects, and a step whose change is already in the applied set
is skipped, so executing a plan twice is a no-op rather than a double edit.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import (
    Status,
    digest,
    reject_unknown_fields,
    require_bool,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .registry import register

register_codes(
    Category.SEMANTIC,
    "CHANGEGRAPH_CONFLICT",
    "CHANGEGRAPH_CYCLE",
    "UNVERIFIED_NODE",
    "REVERT_UNSAFE",
    "PROVENANCE_MISSING",
    "CHANGE_CANNOT_REBASE",
    "APPLY_PRECONDITION_FAILED",
)

__all__ = [
    "ApplyPlan",
    "ApplyReceipt",
    "ApplyState",
    "ApplyStep",
    "Change",
    "ChangeGraph",
    "Conflict",
    "ConflictReport",
    "Edit",
    "Region",
    "RegionMove",
    "apply_plan",
    "build_graph",
    "decode_change",
    "detect_conflicts",
    "entity_spans_from_index",
    "execute_plan",
    "handle",
    "rebase_change",
    "revert_plan",
    "verify_receipts",
]

OPERATIONS = ("insert", "replace", "delete")


# --- edits -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Region:
    """A 1-based inclusive line range.

    An insertion is a *zero-width* region: ``end_line == start_line - 1``,
    meaning "before ``start_line``".  Modelling an insert as a one-line region
    would make it overlap the line it precedes, and every insert next to a
    replace would report a conflict that does not exist.
    """

    start_line: int
    end_line: int

    def __post_init__(self) -> None:
        require_int(self.start_line, "startLine", minimum=1)
        require_int(self.end_line, "endLine", minimum=0)
        if self.end_line < self.start_line - 1:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"region ({self.start_line},{self.end_line}) is not a line range",
                recommended_action="use end_line >= start_line, or start_line-1 for an insert",
            )

    @property
    def is_empty(self) -> bool:
        return self.end_line < self.start_line

    def shifted(self, offset: int) -> Region:
        return Region(self.start_line + offset, self.end_line + offset)

    def to_payload(self) -> dict[str, Any]:
        return {"startLine": self.start_line, "endLine": self.end_line}


def regions_conflict(left: Region, right: Region) -> bool:
    """True when two regions cannot be applied independently.

    The zero-width cases are resolved toward *conflict*: two insertions at the
    same point have no defined order, and an insertion inside a replaced range
    would land in text the other change is deleting.  Being wrong in the safe
    direction costs a caller one manual resolution; being wrong in the other
    direction costs them a file.
    """

    if left.is_empty and right.is_empty:
        return left.start_line == right.start_line
    if left.is_empty:
        return right.start_line <= left.start_line <= right.end_line
    if right.is_empty:
        return left.start_line <= right.start_line <= left.end_line
    return left.start_line <= right.end_line and right.start_line <= left.end_line


@dataclass(frozen=True, slots=True)
class Edit:
    """One region-scoped modification, with the reason it exists.

    ``justification`` is mandatory.  An edit nobody can explain is not
    reviewable, and this graph exists to be reviewed.
    """

    path: str
    region: Region
    operation: str
    content_digest: str
    justification: str

    def __post_init__(self) -> None:
        require_str(self.path, "path")
        require_str(self.justification, "justification")
        if self.operation not in OPERATIONS:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown operation {self.operation!r}",
                recommended_action=f"use one of {list(OPERATIONS)}",
            )
        if self.operation == "insert" and not self.region.is_empty:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="an insert must use a zero-width region (end_line = start_line - 1)",
                recommended_action="set end_line to start_line - 1 for insertions",
            )
        if self.operation != "insert" and self.region.is_empty:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"a {self.operation} needs a non-empty region",
                recommended_action="set end_line >= start_line",
            )
        if self.operation == "delete":
            if self.content_digest:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message="a delete has no replacement content to digest",
                    recommended_action="leave contentDigest empty for a delete",
                )
        else:
            require_str(self.content_digest, "contentDigest")

    @property
    def sort_key(self) -> tuple[str, int, int, str]:
        return (self.path, self.region.start_line, self.region.end_line, self.operation)

    def to_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "region": self.region.to_payload(),
            "operation": self.operation,
            "contentDigest": self.content_digest,
            "justification": self.justification,
        }


# --- changes -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Change:
    """A semantic change: parents, the snapshots it spans, and its edits.

    ``snapshot_before`` and ``snapshot_after`` are what make the graph auditable
    without the working tree.  A receipt that claims this change ran must
    reproduce both, so an edit applied out of band cannot hide inside a
    plausible-looking history.
    """

    change_id: str
    parents: tuple[str, ...]
    snapshot_before: str
    snapshot_after: str
    edits: tuple[Edit, ...]
    justification: str = ""
    verified: bool = False
    evidence_ids: tuple[str, ...] = ()
    rebased_from: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.change_id, "changeId")
        require_str(self.snapshot_before, "snapshotBefore")
        require_str(self.snapshot_after, "snapshotAfter")
        if self.change_id in self.parents:
            raise KernelError(
                code="CHANGEGRAPH_CYCLE",
                message=f"change {self.change_id!r} lists itself as a parent",
                retryable=False,
                recommended_action="remove the self-edge",
            )
        if len(set(self.parents)) != len(self.parents):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"change {self.change_id!r} repeats a parent",
                recommended_action="deduplicate parents",
            )
        if not self.edits:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"change {self.change_id!r} has no edits",
                recommended_action="a change with nothing to apply is not a change",
            )
        object.__setattr__(self, "edits", tuple(sorted(self.edits, key=lambda e: e.sort_key)))

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(sorted({edit.path for edit in self.edits}))

    @property
    def content_digest(self) -> str:
        """Digest over everything that decides what this change does."""

        return digest({
            "parents": sorted(self.parents),
            "snapshotBefore": self.snapshot_before,
            "snapshotAfter": self.snapshot_after,
            "edits": [edit.to_payload() for edit in self.edits],
        })

    def to_payload(self) -> dict[str, Any]:
        return {
            "changeId": self.change_id,
            "parents": sorted(self.parents),
            "snapshotBefore": self.snapshot_before,
            "snapshotAfter": self.snapshot_after,
            "edits": [edit.to_payload() for edit in self.edits],
            "justification": self.justification,
            "verified": self.verified,
            "evidenceIds": sorted(self.evidence_ids),
            "rebasedFrom": self.rebased_from,
            "contentDigest": self.content_digest,
        }


_EDIT_FIELDS = frozenset({"path", "region", "operation", "contentDigest", "justification"})
_REGION_FIELDS = frozenset({"startLine", "endLine"})
_CHANGE_FIELDS = frozenset({
    "changeId", "parents", "snapshotBefore", "snapshotAfter", "edits",
    "justification", "verified", "evidenceIds", "rebasedFrom",
})


def decode_change(payload: Mapping[str, Any]) -> Change:
    """Strictly decode one change.  Unknown fields are a failure, not noise."""

    body = require_mapping(payload, "change")
    reject_unknown_fields(body, _CHANGE_FIELDS, field_name="change")
    raw_edits = body.get("edits")
    if not isinstance(raw_edits, Sequence) or isinstance(raw_edits, (str, bytes)):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="change.edits must be an array",
            recommended_action="supply edits as a JSON array",
        )
    edits: list[Edit] = []
    for index, raw in enumerate(raw_edits):
        item = require_mapping(raw, f"edits[{index}]")
        reject_unknown_fields(item, _EDIT_FIELDS, field_name=f"edits[{index}]")
        region_body = require_mapping(item.get("region"), f"edits[{index}].region")
        reject_unknown_fields(region_body, _REGION_FIELDS,
                              field_name=f"edits[{index}].region")
        edits.append(Edit(
            path=require_str(item.get("path"), f"edits[{index}].path"),
            region=Region(
                require_int(region_body.get("startLine"), "startLine", minimum=1),
                require_int(region_body.get("endLine"), "endLine", minimum=0),
            ),
            operation=require_str(item.get("operation"), f"edits[{index}].operation"),
            content_digest=str(item.get("contentDigest") or ""),
            justification=require_str(item.get("justification"),
                                      f"edits[{index}].justification"),
        ))
    return Change(
        change_id=require_identifier(body.get("changeId"), "changeId"),
        parents=require_str_seq(body.get("parents", ()), "parents"),
        snapshot_before=require_str(body.get("snapshotBefore"), "snapshotBefore"),
        snapshot_after=require_str(body.get("snapshotAfter"), "snapshotAfter"),
        edits=tuple(edits),
        justification=str(body.get("justification") or ""),
        verified=require_bool(body.get("verified", False), "verified"),
        evidence_ids=require_str_seq(body.get("evidenceIds", ()), "evidenceIds"),
        rebased_from=str(body.get("rebasedFrom") or ""),
    )


# --- the graph ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChangeGraph:
    """A validated DAG of changes with a deterministic topological order."""

    changes: tuple[Change, ...]
    order: tuple[str, ...]

    def by_id(self, change_id: str) -> Change:
        for change in self.changes:
            if change.change_id == change_id:
                return change
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message=f"change {change_id!r} is not in the graph",
            recommended_action="add the change or correct the identifier",
        )

    def ancestors(self, change_id: str, *, include_self: bool = True) -> tuple[str, ...]:
        """Every change that must land before ``change_id`` can."""

        seen: set[str] = set()
        frontier = [change_id]
        while frontier:
            current = frontier.pop()
            for parent in self.by_id(current).parents:
                if parent not in seen:
                    seen.add(parent)
                    frontier.append(parent)
        if include_self:
            seen.add(change_id)
        return tuple(item for item in self.order if item in seen)

    def descendants(self, change_id: str, *, include_self: bool = True) -> tuple[str, ...]:
        """Every change that depends on ``change_id`` and must be reverted with it."""

        children: dict[str, list[str]] = {}
        for change in self.changes:
            for parent in change.parents:
                children.setdefault(parent, []).append(change.change_id)
        seen: set[str] = set()
        frontier = [change_id]
        while frontier:
            current = frontier.pop()
            for child in children.get(current, ()):
                if child not in seen:
                    seen.add(child)
                    frontier.append(child)
        if include_self:
            seen.add(change_id)
        return tuple(item for item in self.order if item in seen)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "nodes": [change.to_payload() for change in
                      sorted(self.changes, key=lambda c: c.change_id)],
            "edges": [
                {"from": parent, "to": change.change_id, "kind": "parent"}
                for change in sorted(self.changes, key=lambda c: c.change_id)
                for parent in sorted(change.parents)
            ],
            "topologicalOrder": list(self.order),
        }
        payload["graphDigest"] = digest(payload)
        return payload


def build_graph(changes: Iterable[Change]) -> ChangeGraph:
    """Validate a change set into a DAG.

    A cycle is refused rather than broken at an arbitrary edge: the caller knows
    which dependency is wrong and the kernel does not.
    """

    items = tuple(changes)
    by_id: dict[str, Change] = {}
    for change in items:
        if change.change_id in by_id:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"duplicate change id {change.change_id!r}",
                recommended_action="change ids must be unique within a graph",
            )
        by_id[change.change_id] = change
    for change in items:
        unknown = sorted(set(change.parents) - set(by_id))
        if unknown:
            raise KernelError(
                code="PROVENANCE_MISSING",
                message=f"change {change.change_id!r} names unknown parent(s) {unknown}",
                retryable=False,
                recommended_action="include the parent changes or correct the references",
                details={"changeId": change.change_id, "unknownParents": unknown},
            )

    indegree = {cid: len(set(by_id[cid].parents)) for cid in by_id}
    children: dict[str, list[str]] = {cid: [] for cid in by_id}
    for change in items:
        for parent in change.parents:
            children[parent].append(change.change_id)
    ready = sorted(cid for cid, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    if len(order) != len(by_id):
        remaining = sorted(set(by_id) - set(order))
        cyclic, witness = _cycle_members(by_id, remaining)
        raise KernelError(
            code="CHANGEGRAPH_CYCLE",
            message=f"change graph contains a cycle among {cyclic}",
            retryable=False,
            recommended_action="break the dependency cycle; a change graph must be a DAG",
            details={
                "cyclicChangeIds": cyclic,
                "witnessCycle": witness,
                "blockedChangeIds": [cid for cid in remaining if cid not in set(cyclic)],
            },
        )
    return ChangeGraph(changes=items, order=tuple(order))


def _cycle_members(by_id: Mapping[str, Change],
                   remaining: Sequence[str]) -> tuple[list[str], list[str]]:
    """Return the changes genuinely inside a cycle, plus one witness path.

    The set the topological sort leaves behind is *not* the cycle: it also holds
    every change merely downstream of one.  Reporting that set sends the caller
    to break a dependency that is not the problem — ``c-d`` depending on a
    deadlocked ``c-a <-> c-b`` is a victim, not a cause.  So the remaining
    subgraph is decomposed into strongly connected components (Tarjan, iterative
    so a deep graph cannot blow the Python stack); a component of size two or
    more, or a self-parent, is a real cycle.  ``blockedChangeIds`` carries the
    victims separately, because they are still worth showing — just not as the
    thing to fix.
    """

    scope = set(remaining)
    edges = {cid: sorted(set(by_id[cid].parents) & scope) for cid in scope}

    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    counter = 0
    components: list[list[str]] = []

    for root in sorted(scope):
        if root in index_of:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, child_index = work[-1]
            if child_index == 0:
                index_of[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            if child_index < len(edges[node]):
                work[-1] = (node, child_index + 1)
                nxt = edges[node][child_index]
                if nxt not in index_of:
                    work.append((nxt, 0))
                elif nxt in on_stack:
                    low[node] = min(low[node], index_of[nxt])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index_of[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                components.append(sorted(component))

    cyclic: set[str] = set()
    witness: list[str] = []
    for component in sorted(components):
        is_cycle = len(component) > 1 or component[0] in edges[component[0]]
        if not is_cycle:
            continue
        cyclic.update(component)
        if not witness:
            witness = _witness_path(component, edges)
    return sorted(cyclic), witness


def _witness_path(component: Sequence[str], edges: Mapping[str, Sequence[str]]) -> list[str]:
    """Walk one concrete cycle inside a strongly connected component.

    A component says *that* the changes are mutually reachable; a reviewer needs
    to see *which* edges close the loop.  The walk is deterministic (sorted
    successors) so the same graph always names the same witness.
    """

    members = set(component)
    start = sorted(members)[0]
    seen: dict[str, int] = {}
    path: list[str] = []
    node = start
    while node not in seen:
        seen[node] = len(path)
        path.append(node)
        successors = [item for item in edges[node] if item in members]
        if not successors:
            return path
        node = successors[0]
    return path[seen[node]:] + [node]


# --- conflicts ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Conflict:
    """One reason two changes may not be applied together."""

    kind: str
    change_ids: tuple[str, str]
    path: str
    detail: str
    entity_id: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "changeIds": list(self.change_ids),
            "path": self.path,
            "detail": self.detail,
            "entityId": self.entity_id,
        }


@dataclass(frozen=True, slots=True)
class ConflictReport:
    """The answer to "can these land together" — never an automatic merge."""

    conflicts: tuple[Conflict, ...]
    considered_change_ids: tuple[str, ...]
    semantic_checked: bool

    @property
    def clean(self) -> bool:
        return not self.conflicts

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "conflicts": [conflict.to_payload() for conflict in self.conflicts],
            "conflictCount": len(self.conflicts),
            "consideredChangeIds": list(self.considered_change_ids),
            "semanticChecked": self.semantic_checked,
            "semanticCheckNote": (
                "region overlap is always checked; semantic (same-entity) conflicts are "
                "checked only when entity spans are supplied, and their absence is reported "
                "rather than treated as 'no semantic conflict'"
            ),
            "resolution": "caller-resolved" if self.conflicts else "none-required",
        }
        payload["reportDigest"] = digest(payload)
        return payload


def entity_spans_from_index(index: Any) -> dict[str, tuple[tuple[str, int, int], ...]]:
    """Adapt a semantic index into ``path -> ((entity_id, start, end), ...)``.

    Duck-typed on purpose: the change graph must not depend on the indexer's
    module, only on the shape of what it publishes.
    """

    entities = getattr(index, "entities", None)
    if entities is None:
        raise KernelError(
            code="MALFORMED_INPUT",
            message="semantic index has no 'entities'",
            recommended_action="pass a semindex.Index or an object exposing .entities",
        )
    spans: dict[str, list[tuple[str, int, int]]] = {}
    for entity in entities:
        start = int(getattr(entity, "line_start", 0))
        end = int(getattr(entity, "line_end", 0))
        if start <= 0 or end < start:
            continue
        spans.setdefault(str(entity.path), []).append(
            (str(entity.entity_id), start, end)
        )
    return {path: tuple(sorted(items)) for path, items in sorted(spans.items())}


def _touched_entities(edit: Edit,
                      spans: Mapping[str, Sequence[tuple[str, int, int]]]) -> tuple[str, ...]:
    touched = []
    for entity_id, start, end in spans.get(edit.path, ()):
        if regions_conflict(edit.region, Region(start, end)):
            touched.append(entity_id)
    return tuple(sorted(set(touched)))


def detect_conflicts(
    changes: Sequence[Change],
    *,
    entity_spans: Mapping[str, Sequence[tuple[str, int, int]]] | None = None,
) -> ConflictReport:
    """Report every pairwise conflict; resolve none of them.

    Two kinds are reported: ``region-overlap`` (two changes touching overlapping
    line ranges of one path) and ``semantic-entity`` (two changes touching one
    indexed entity even when their line ranges do not intersect — a rename and a
    body edit of the same function do not overlap textually and still cannot be
    merged blindly).
    """

    ordered = sorted(changes, key=lambda c: c.change_id)
    conflicts: list[Conflict] = []
    for left_index, left in enumerate(ordered):
        for right in ordered[left_index + 1:]:
            for left_edit in left.edits:
                for right_edit in right.edits:
                    if left_edit.path != right_edit.path:
                        continue
                    if regions_conflict(left_edit.region, right_edit.region):
                        conflicts.append(Conflict(
                            kind="region-overlap",
                            change_ids=(left.change_id, right.change_id),
                            path=left_edit.path,
                            detail=(
                                f"{left_edit.operation} "
                                f"({left_edit.region.start_line},{left_edit.region.end_line}) "
                                f"overlaps {right_edit.operation} "
                                f"({right_edit.region.start_line},"
                                f"{right_edit.region.end_line})"
                            ),
                        ))
            if entity_spans is None:
                continue
            left_entities = {
                entity for edit in left.edits
                for entity in _touched_entities(edit, entity_spans)
            }
            right_entities = {
                entity for edit in right.edits
                for entity in _touched_entities(edit, entity_spans)
            }
            for entity_id in sorted(left_entities & right_entities):
                path = next(
                    (p for p, items in entity_spans.items()
                     if any(item[0] == entity_id for item in items)), "")
                conflicts.append(Conflict(
                    kind="semantic-entity",
                    change_ids=(left.change_id, right.change_id),
                    path=path,
                    detail="both changes touch the same indexed entity",
                    entity_id=entity_id,
                ))
    unique = tuple(sorted(
        {(c.kind, c.change_ids, c.path, c.detail, c.entity_id): c for c in conflicts}.values(),
        key=lambda c: (c.kind, c.change_ids, c.path, c.entity_id, c.detail),
    ))
    return ConflictReport(
        conflicts=unique,
        considered_change_ids=tuple(change.change_id for change in ordered),
        semantic_checked=entity_spans is not None,
    )


# --- rebase ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegionMove:
    """A caller's explicit statement that ``[old_start, old_end]`` moved by ``offset``.

    The caller must know this; the kernel must not infer it.  Inference is how a
    rebase lands three lines away from where it belongs.
    """

    path: str
    old_start: int
    old_end: int
    line_offset: int

    def __post_init__(self) -> None:
        require_str(self.path, "path")
        require_int(self.old_start, "oldStart", minimum=1)
        require_int(self.old_end, "oldEnd", minimum=1)
        if self.old_end < self.old_start:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="RegionMove old_end precedes old_start",
                recommended_action="supply an ordered region",
            )

    def contains(self, region: Region) -> bool:
        if region.is_empty:
            return self.old_start <= region.start_line <= self.old_end
        return self.old_start <= region.start_line and region.end_line <= self.old_end

    def intersects(self, region: Region) -> bool:
        return regions_conflict(Region(self.old_start, self.old_end), region)


def rebase_change(change: Change, moves: Sequence[RegionMove], *,
                  snapshot_before: str, snapshot_after: str) -> Change:
    """Rebase ``change`` onto moved regions, or refuse.

    An edit is shifted only when exactly one move *wholly contains* it, and the
    offset applied is recorded in the edit's justification so a reviewer can see
    where the change moved and why.  Partial overlap, or two containing moves
    with different offsets, raises ``CHANGE_CANNOT_REBASE`` — the alternative is
    applying a correct edit at a wrong location, which is worse than not
    applying it at all.
    """

    new_edits: list[Edit] = []
    applied_offsets: list[tuple[str, int]] = []
    for edit in change.edits:
        relevant = [move for move in moves if move.path == edit.path
                    and move.intersects(edit.region)]
        containing = [move for move in relevant if move.contains(edit.region)]
        if len(relevant) != len(containing):
            raise KernelError(
                code="CHANGE_CANNOT_REBASE",
                message=(
                    f"edit on {edit.path} lines "
                    f"({edit.region.start_line},{edit.region.end_line}) is only partially "
                    "covered by a moved region"
                ),
                retryable=False,
                recommended_action="re-author the edit against the new snapshot",
                details={"changeId": change.change_id, "path": edit.path},
            )
        offsets = sorted({move.line_offset for move in containing})
        if len(offsets) > 1:
            raise KernelError(
                code="CHANGE_CANNOT_REBASE",
                message=(
                    f"edit on {edit.path} is covered by moves with disagreeing offsets "
                    f"{offsets}"
                ),
                retryable=False,
                recommended_action="supply one unambiguous move per edited region",
                details={"changeId": change.change_id, "path": edit.path},
            )
        offset = offsets[0] if offsets else 0
        if edit.region.start_line + offset < 1:
            raise KernelError(
                code="CHANGE_CANNOT_REBASE",
                message=f"offset {offset} would move an edit on {edit.path} before line 1",
                retryable=False,
                recommended_action="re-author the edit against the new snapshot",
                details={"changeId": change.change_id, "path": edit.path},
            )
        applied_offsets.append((edit.path, offset))
        suffix = f" [rebased by {offset:+d} lines]" if offset else " [rebased, offset 0]"
        new_edits.append(Edit(
            path=edit.path,
            region=edit.region.shifted(offset),
            operation=edit.operation,
            content_digest=edit.content_digest,
            justification=edit.justification + suffix,
        ))
    fingerprint = digest({
        "source": change.change_id,
        "offsets": [{"path": path, "offset": offset} for path, offset in applied_offsets],
        "snapshotBefore": snapshot_before,
    }).split(":", 1)[1][:12]
    return Change(
        change_id=f"{change.change_id}.rebased.{fingerprint}",
        parents=change.parents,
        snapshot_before=snapshot_before,
        snapshot_after=snapshot_after,
        edits=tuple(new_edits),
        justification=change.justification,
        verified=False,
        evidence_ids=(),
        rebased_from=change.change_id,
    )


# --- apply -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ApplyStep:
    """One guarded application: the state it expects and the state it produces."""

    change_id: str
    expected_before: str
    expected_after: str
    paths: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "changeId": self.change_id,
            "expectedSnapshotBefore": self.expected_before,
            "expectedSnapshotAfter": self.expected_after,
            "paths": list(self.paths),
        }


@dataclass(frozen=True, slots=True)
class ApplyPlan:
    """An ordered, idempotent plan.  Executing it twice changes nothing twice."""

    target: str
    steps: tuple[ApplyStep, ...]
    conflict_report: ConflictReport

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "target": self.target,
            "steps": [step.to_payload() for step in self.steps],
            "stepCount": len(self.steps),
            "conflictReport": self.conflict_report.to_payload(),
            "idempotency": (
                "each step is skipped when its changeId is already in the applied set; "
                "a step whose expected before-digest does not match the current state "
                "raises APPLY_PRECONDITION_FAILED rather than applying anywhere else"
            ),
        }
        payload["planDigest"] = digest(payload)
        return payload


@dataclass(frozen=True, slots=True)
class ApplyState:
    """The observable result of applying changes: a digest and an applied set."""

    snapshot_digest: str
    applied_change_ids: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "snapshotDigest": self.snapshot_digest,
            "appliedChangeIds": list(self.applied_change_ids),
        }


@dataclass(frozen=True, slots=True)
class ApplyReceipt:
    """Proof that one step ran (or was skipped), with both snapshot digests."""

    change_id: str
    before: str
    after: str
    applied: bool
    reason: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "changeId": self.change_id,
            "snapshotBefore": self.before,
            "snapshotAfter": self.after,
            "applied": self.applied,
            "reason": self.reason,
        }


def apply_plan(graph: ChangeGraph, target: str, *,
               entity_spans: Mapping[str, Sequence[tuple[str, int, int]]] | None = None,
               require_verified: bool = True) -> ApplyPlan:
    """Plan the application of ``target`` and everything it depends on.

    Conflicts raise instead of being resolved, and an unverified change raises
    instead of being merged.  Both refusals are the point of the capability: a
    plan that silently dropped one of two overlapping edits, or merged a change
    nothing had validated, would be indistinguishable from a working plan until
    the damage surfaced.
    """

    selected = graph.ancestors(target)
    changes = [graph.by_id(change_id) for change_id in selected]
    report = detect_conflicts(changes, entity_spans=entity_spans)
    if not report.clean:
        raise KernelError(
            code="CHANGEGRAPH_CONFLICT",
            message=(
                f"{len(report.conflicts)} conflict(s) among the changes required for "
                f"{target!r}; the caller must resolve them"
            ),
            retryable=False,
            recommended_action="resolve the reported conflicts and re-plan",
            details={"conflictReport": report.to_payload()},
        )
    if require_verified:
        unverified = sorted(
            change.change_id for change in changes
            if not (change.verified and change.evidence_ids)
        )
        if unverified:
            raise KernelError(
                code="UNVERIFIED_NODE",
                message=f"{len(unverified)} change(s) in the plan carry no verification",
                retryable=False,
                recommended_action="verify the changes, or plan with require_verified=False",
                details={"changeIds": unverified},
            )
    steps = tuple(
        ApplyStep(
            change_id=change.change_id,
            expected_before=change.snapshot_before,
            expected_after=change.snapshot_after,
            paths=change.paths,
        )
        for change in changes
    )
    return ApplyPlan(target=target, steps=steps, conflict_report=report)


def execute_plan(plan: ApplyPlan, state: ApplyState) -> tuple[ApplyState, tuple[ApplyReceipt, ...]]:
    """Execute a plan against a state, skipping what is already applied.

    This is the idempotency mechanism: application is keyed on the change id in
    the applied set, and every step that does run is guarded by the exact state
    digest it was planned against.  Re-executing a finished plan therefore
    produces the same state and a receipt set that says, honestly, that nothing
    happened.
    """

    applied = list(state.applied_change_ids)
    current = state.snapshot_digest
    receipts: list[ApplyReceipt] = []
    for step in plan.steps:
        if step.change_id in applied:
            receipts.append(ApplyReceipt(
                change_id=step.change_id, before=step.expected_before,
                after=step.expected_after, applied=False, reason="already-applied",
            ))
            continue
        if current != step.expected_before:
            raise KernelError(
                code="APPLY_PRECONDITION_FAILED",
                message=(
                    f"step {step.change_id!r} expects snapshot {step.expected_before} "
                    f"but the state is at {current}"
                ),
                retryable=False,
                recommended_action="rebase the change onto the current snapshot; "
                                   "do not apply it at a guessed location",
                details={"changeId": step.change_id, "expected": step.expected_before,
                         "actual": current},
            )
        receipts.append(ApplyReceipt(
            change_id=step.change_id, before=current, after=step.expected_after,
            applied=True, reason="applied",
        ))
        current = step.expected_after
        applied.append(step.change_id)
    return ApplyState(snapshot_digest=current,
                      applied_change_ids=tuple(applied)), tuple(receipts)


def verify_receipts(graph: ChangeGraph, receipts: Sequence[ApplyReceipt]) -> Mapping[str, Any]:
    """Re-derive the history from receipts and the graph.

    A receipt whose digests do not match the change it names is evidence that
    something applied outside this graph, which is exactly what the recorded
    before/after digests exist to catch.
    """

    problems: list[dict[str, str]] = []
    previous_after = ""
    for receipt in receipts:
        change = graph.by_id(receipt.change_id)
        if receipt.applied:
            if receipt.before != change.snapshot_before:
                problems.append({"changeId": receipt.change_id, "field": "snapshotBefore"})
            if receipt.after != change.snapshot_after:
                problems.append({"changeId": receipt.change_id, "field": "snapshotAfter"})
            if previous_after and previous_after != receipt.before:
                problems.append({"changeId": receipt.change_id, "field": "chain"})
            previous_after = receipt.after
    return {
        "verified": not problems,
        "problems": problems,
        "receiptCount": len(receipts),
        "appliedCount": sum(1 for receipt in receipts if receipt.applied),
    }


def revert_plan(graph: ChangeGraph, change_id: str) -> Mapping[str, Any]:
    """Order the dependency closure that must be undone with ``change_id``.

    Reverting a change without its descendants leaves the graph describing a
    tree that never existed, so the closure is computed rather than assumed, and
    a descendant that does not chain back to its parent's snapshot makes the
    revert ``REVERT_UNSAFE`` instead of best-effort.
    """

    closure = graph.descendants(change_id)
    steps = []
    for cid in reversed(closure):
        change = graph.by_id(cid)
        steps.append({
            "changeId": cid,
            "restoreSnapshot": change.snapshot_before,
            "undoSnapshot": change.snapshot_after,
            "paths": list(change.paths),
        })
    for cid in closure:
        change = graph.by_id(cid)
        for parent in change.parents:
            if parent in closure and graph.by_id(parent).snapshot_after != change.snapshot_before:
                raise KernelError(
                    code="REVERT_UNSAFE",
                    message=(
                        f"change {cid!r} does not chain to parent {parent!r}; the revert "
                        "order cannot be proven safe"
                    ),
                    retryable=False,
                    recommended_action="repair the snapshot chain before reverting",
                    details={"changeId": cid, "parentId": parent},
                )
    payload = {
        "rootChangeId": change_id,
        "closure": list(closure),
        "steps": steps,
        "testable": True,
        "note": "steps are in reverse topological order; each restores its own before-digest",
    }
    return {**payload, "revertPlanDigest": digest(payload)}


# --- registry entry point ----------------------------------------------------


_REQUEST_FIELDS = frozenset({
    "changes", "target", "semanticIndex", "entitySpans", "requireVerified", "state",
})


@register("changegraph-vcs")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point for ``changegraph-vcs``.

    Without ``target`` this is pure analysis: the graph and the conflict report
    come back and a conflict is a finding, not a failure.  With ``target`` the
    caller is asking for a plan, and an unresolved conflict then raises — a plan
    over conflicting changes has no honest form.
    """

    payload = require_mapping(request, "request")
    reject_unknown_fields(payload, _REQUEST_FIELDS, field_name="changegraph-vcs request")
    raw_changes = payload.get("changes")
    if raw_changes is None:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="changegraph-vcs requires 'changes'",
            recommended_action="supply an array of change objects",
        )
    if isinstance(raw_changes, (str, bytes)) or not isinstance(raw_changes, Sequence):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="'changes' must be an array",
            recommended_action="supply changes as a JSON array",
        )
    changes = tuple(
        item if isinstance(item, Change) else decode_change(item) for item in raw_changes
    )
    graph = build_graph(changes)

    spans: Mapping[str, Sequence[tuple[str, int, int]]] | None = None
    if payload.get("semanticIndex") is not None:
        spans = entity_spans_from_index(payload["semanticIndex"])
    elif payload.get("entitySpans") is not None:
        raw_spans = require_mapping(payload["entitySpans"], "entitySpans")
        spans = {
            require_str(path, "entitySpans key"): tuple(
                (require_str(item[0], "entityId"),
                 require_int(item[1], "startLine", minimum=1),
                 require_int(item[2], "endLine", minimum=1))
                for item in items
            )
            for path, items in raw_spans.items()
        }

    report = detect_conflicts(changes, entity_spans=spans)
    outputs: dict[str, Any] = {
        "status": Status.SUCCEEDED,
        "changeGraph": graph.to_payload(),
        "changeNodes": [change.to_payload() for change in
                        sorted(changes, key=lambda c: c.change_id)],
        "changeEdges": graph.to_payload()["edges"],
        "conflictReport": report.to_payload(),
    }

    target = payload.get("target")
    if target is not None:
        target_id = require_identifier(target, "target")
        require_verified = require_bool(
            payload.get("requireVerified", True), "requireVerified")
        plan = apply_plan(graph, target_id, entity_spans=spans,
                          require_verified=require_verified)
        state_payload = payload.get("state")
        if state_payload is None:
            state = ApplyState(snapshot_digest=graph.by_id(plan.steps[0].change_id
                                                           ).snapshot_before)
        else:
            body = require_mapping(state_payload, "state")
            reject_unknown_fields(body, {"snapshotDigest", "appliedChangeIds"},
                                  field_name="state")
            state = ApplyState(
                snapshot_digest=require_str(body.get("snapshotDigest"), "snapshotDigest"),
                applied_change_ids=require_str_seq(
                    body.get("appliedChangeIds", ()), "appliedChangeIds"),
            )
        new_state, receipts = execute_plan(plan, state)
        outputs["applyPlan"] = plan.to_payload()
        outputs["mergePlan"] = plan.to_payload()
        outputs["revertPlan"] = revert_plan(graph, target_id)
        outputs["applyState"] = new_state.to_payload()
        outputs["provenanceCommit"] = {
            "receipts": [receipt.to_payload() for receipt in receipts],
            "verification": verify_receipts(graph, receipts),
            "graphDigest": graph.to_payload()["graphDigest"],
        }
    outputs["gates"] = {
        "dag-valid": {"passed": True, "detail": f"{len(graph.order)} node(s) ordered"},
        "graph-acyclic-or-bounded": {"passed": True, "detail": "topological order exists"},
        "conflict-detected": {
            "passed": True,
            "detail": f"{len(report.conflicts)} conflict(s) reported, none auto-merged",
        },
        "merge-conflict-resolved": {
            "passed": report.clean,
            "detail": "no conflict remains" if report.clean else "caller must resolve",
        },
        "apply-is-idempotent": {
            "passed": True,
            "detail": "steps are keyed on changeId and guarded by the before-digest",
        },
        "traceability-complete": {
            "passed": all(change.justification or all(
                edit.justification for edit in change.edits) for change in changes),
            "detail": "every change carries a justification on itself or every edit",
        },
        "revert-plan-testable": {
            "passed": target is not None,
            "detail": "a revert plan is produced whenever a target is named",
        },
    }
    return outputs

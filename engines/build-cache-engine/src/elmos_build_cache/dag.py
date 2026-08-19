"""The incremental conversion DAG.

Two decisions live here and nowhere else:

* **what must run** -- the minimal affected closure, derived from the graph
  rather than guessed, with a recorded reason for every node that is executed,
  restored, skipped or invalidated;
* **in what order** -- a deterministic schedule by critical path, resource
  class and cache locality, so two planning runs over the same inputs produce
  the same plan.

Edge kinds matter. An ``IMPORT`` or ``PUBLIC_INTERFACE`` edge propagates an
interface change to dependents; a ``BEHAVIOR`` edge additionally propagates a
private body change (a test depends on behaviour, not only on signatures).
Conflating them is what makes naive incremental systems either unsound or
useless.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .canonical import digest_of
from .enums import CacheMode, Determinism, MissReason, ValidationLevel
from .errors import ConflictError, ContractViolation, NotFound


class Granularity(str, Enum):
    REPOSITORY = "REPOSITORY"
    MODULE = "MODULE"
    FILE = "FILE"
    SYMBOL = "SYMBOL"
    IR_PARTITION = "IR_PARTITION"
    GENERATED_FILE = "GENERATED_FILE"
    COMPILE_TARGET = "COMPILE_TARGET"
    TEST_SHARD = "TEST_SHARD"
    EVIDENCE_UNIT = "EVIDENCE_UNIT"


class EdgeKind(str, Enum):
    IMPORT = "IMPORT"
    PUBLIC_INTERFACE = "PUBLIC_INTERFACE"
    BEHAVIOR = "BEHAVIOR"
    SCHEMA = "SCHEMA"
    ROUTE = "ROUTE"
    EVENT = "EVENT"
    DATAFLOW = "DATAFLOW"
    FRAMEWORK_ADAPTER = "FRAMEWORK_ADAPTER"
    GENERATED_FILE_OWNERSHIP = "GENERATED_FILE_OWNERSHIP"
    SEQUENCING = "SEQUENCING"


#: Edges that carry an *interface* change to the dependent.
INTERFACE_EDGES: frozenset[EdgeKind] = frozenset(
    {
        EdgeKind.IMPORT,
        EdgeKind.PUBLIC_INTERFACE,
        EdgeKind.SCHEMA,
        EdgeKind.ROUTE,
        EdgeKind.EVENT,
        EdgeKind.FRAMEWORK_ADAPTER,
        EdgeKind.GENERATED_FILE_OWNERSHIP,
        EdgeKind.SEQUENCING,
    }
)

#: Edges that additionally carry a *behaviour* (private body) change.
BEHAVIOR_EDGES: frozenset[EdgeKind] = frozenset(
    {EdgeKind.BEHAVIOR, EdgeKind.DATAFLOW, EdgeKind.GENERATED_FILE_OWNERSHIP, EdgeKind.SEQUENCING}
)


class NodeDecision(str, Enum):
    EXECUTE = "EXECUTE"
    RESTORE = "RESTORE"
    SKIP = "SKIP"
    INVALIDATED = "INVALIDATED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    kind: EdgeKind

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, "kind": self.kind.value}


@dataclass(frozen=True)
class DagNode:
    """A unit of work with a fully declared contract surface."""

    node_id: str
    stage_id: str
    granularity: Granularity
    input_schemas: tuple[str, ...] = ()
    output_schemas: tuple[str, ...] = ()
    logical_outputs: tuple[str, ...] = ()
    fingerprint_dimensions: tuple[str, ...] = ()
    determinism: Determinism = Determinism.DETERMINISTIC
    cache_mode: CacheMode = CacheMode.READ_WRITE
    validation_floor: ValidationLevel = ValidationLevel.TEST_VERIFIED
    workspace_mounts: tuple[str, ...] = ("source", "overlay", "scratch", "generated/pending")
    resource_class: str = "cpu-small"
    estimated_cost_ms: int = 1000
    side_effects: tuple[str, ...] = ()
    idempotent: bool = True
    checkpoint_boundary: bool = True
    partition_key: str | None = None
    source_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "stage_id": self.stage_id,
            "granularity": self.granularity.value,
            "input_schemas": list(self.input_schemas),
            "output_schemas": list(self.output_schemas),
            "logical_outputs": list(self.logical_outputs),
            "fingerprint_dimensions": list(self.fingerprint_dimensions),
            "determinism": str(self.determinism),
            "cache_mode": str(self.cache_mode),
            "validation_floor": str(self.validation_floor),
            "workspace_mounts": list(self.workspace_mounts),
            "resource_class": self.resource_class,
            "estimated_cost_ms": self.estimated_cost_ms,
            "side_effects": list(self.side_effects),
            "idempotent": self.idempotent,
            "checkpoint_boundary": self.checkpoint_boundary,
            "partition_key": self.partition_key,
            "source_paths": list(self.source_paths),
        }


@dataclass(frozen=True)
class NodePlan:
    node_id: str
    decision: NodeDecision
    reasons: tuple[str, ...]
    miss_reasons: tuple[MissReason, ...] = ()
    action_key: str | None = None
    wave: int = 0
    critical_path_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "miss_reasons": [str(reason) for reason in self.miss_reasons],
            "action_key": self.action_key,
            "wave": self.wave,
            "critical_path_ms": self.critical_path_ms,
        }


@dataclass(frozen=True)
class ExecutionPlan:
    plan_digest: str
    nodes: tuple[NodePlan, ...]
    waves: tuple[tuple[str, ...], ...]
    arbitration: dict[str, str] = field(default_factory=dict)

    def decision_of(self, node_id: str) -> NodePlan:
        for plan in self.nodes:
            if plan.node_id == node_id:
                return plan
        raise NotFound("node is not in the plan", node_id=node_id)

    def to_execute(self) -> tuple[str, ...]:
        return tuple(
            plan.node_id
            for plan in self.nodes
            if plan.decision in (NodeDecision.EXECUTE, NodeDecision.INVALIDATED)
        )

    def to_restore(self) -> tuple[str, ...]:
        return tuple(plan.node_id for plan in self.nodes if plan.decision is NodeDecision.RESTORE)

    def skipped(self) -> tuple[str, ...]:
        return tuple(plan.node_id for plan in self.nodes if plan.decision is NodeDecision.SKIP)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_digest": self.plan_digest,
            "nodes": [plan.to_dict() for plan in self.nodes],
            "waves": [list(wave) for wave in self.waves],
            "arbitration": dict(sorted(self.arbitration.items())),
        }

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for plan in self.nodes:
            counts[plan.decision.value] += 1
        return dict(sorted(counts.items()))


class ConversionDag:
    def __init__(self) -> None:
        self._nodes: dict[str, DagNode] = {}
        self._edges: list[Edge] = []
        self._out: dict[str, list[Edge]] = defaultdict(list)
        self._in: dict[str, list[Edge]] = defaultdict(list)

    # -- construction -----------------------------------------------------
    def add_node(self, node: DagNode) -> DagNode:
        if node.node_id in self._nodes:
            raise ConflictError("node already exists", node_id=node.node_id)
        if node.side_effects and not node.idempotent:
            raise ContractViolation(
                "a node with side effects must be idempotent or declare compensation",
                node_id=node.node_id,
            )
        self._nodes[node.node_id] = node
        return node

    def add_edge(self, source: str, target: str, kind: EdgeKind = EdgeKind.SEQUENCING) -> Edge:
        for node_id in (source, target):
            if node_id not in self._nodes:
                raise NotFound("edge references an unknown node", node_id=node_id)
        edge = Edge(source, target, kind)
        self._edges.append(edge)
        self._out[source].append(edge)
        self._in[target].append(edge)
        return edge

    def node(self, node_id: str) -> DagNode:
        try:
            return self._nodes[node_id]
        except KeyError as exc:
            raise NotFound("unknown node", node_id=node_id) from exc

    @property
    def nodes(self) -> tuple[DagNode, ...]:
        return tuple(self._nodes[node_id] for node_id in sorted(self._nodes))

    @property
    def edges(self) -> tuple[Edge, ...]:
        return tuple(sorted(self._edges, key=lambda e: (e.source, e.target, e.kind.value)))

    def dependencies(self, node_id: str) -> tuple[str, ...]:
        return tuple(sorted({edge.source for edge in self._in[node_id]}))

    def dependents(self, node_id: str) -> tuple[str, ...]:
        return tuple(sorted({edge.target for edge in self._out[node_id]}))

    # -- validation -------------------------------------------------------
    def topological_order(self) -> tuple[str, ...]:
        indegree = {node_id: 0 for node_id in self._nodes}
        for edge in self._edges:
            indegree[edge.target] += 1
        ready = deque(sorted(node_id for node_id, count in indegree.items() if count == 0))
        order: list[str] = []
        while ready:
            node_id = ready.popleft()
            order.append(node_id)
            for edge in sorted(self._out[node_id], key=lambda e: e.target):
                indegree[edge.target] -= 1
                if indegree[edge.target] == 0:
                    ready.append(edge.target)
            ready = deque(sorted(ready))
        if len(order) != len(self._nodes):
            remaining = sorted(set(self._nodes) - set(order))
            raise ContractViolation("conversion DAG contains a cycle", nodes=remaining[:20])
        return tuple(order)

    def arbitrate_outputs(self) -> dict[str, str]:
        """Two nodes cannot own the same logical output without arbitration.

        The owner is the node whose declaration is most specific (finest
        granularity, then lexical order) -- and the conflict is *recorded*, not
        silently resolved.
        """
        claims: dict[str, list[str]] = defaultdict(list)
        for node in self.nodes:
            for logical_path in node.logical_outputs:
                claims[logical_path].append(node.node_id)
        ranking = {
            Granularity.SYMBOL: 0,
            Granularity.GENERATED_FILE: 1,
            Granularity.FILE: 2,
            Granularity.IR_PARTITION: 3,
            Granularity.COMPILE_TARGET: 4,
            Granularity.TEST_SHARD: 5,
            Granularity.MODULE: 6,
            Granularity.EVIDENCE_UNIT: 7,
            Granularity.REPOSITORY: 8,
        }
        owners: dict[str, str] = {}
        for logical_path, node_ids in sorted(claims.items()):
            if len(node_ids) == 1:
                owners[logical_path] = node_ids[0]
                continue
            ordered = sorted(node_ids, key=lambda nid: (ranking[self._nodes[nid].granularity], nid))
            owners[logical_path] = ordered[0]
        return owners

    def contested_outputs(self) -> dict[str, list[str]]:
        claims: dict[str, list[str]] = defaultdict(list)
        for node in self.nodes:
            for logical_path in node.logical_outputs:
                claims[logical_path].append(node.node_id)
        return {path: sorted(ids) for path, ids in sorted(claims.items()) if len(ids) > 1}

    # -- invalidation -----------------------------------------------------
    def affected_closure(
        self,
        interface_changed: Iterable[str] = (),
        behavior_changed: Iterable[str] = (),
        forced: Iterable[str] = (),
    ) -> dict[str, list[str]]:
        """Minimal set of nodes reachable from the changes, with reasons.

        ``interface_changed`` walks :data:`INTERFACE_EDGES`; ``behavior_changed``
        walks only :data:`BEHAVIOR_EDGES`, which is why a private body edit does
        not invalidate an unrelated dependent's parse or IR.
        """
        reasons: dict[str, list[str]] = defaultdict(list)
        queue: deque[tuple[str, frozenset[EdgeKind], str]] = deque()

        for node_id in sorted(set(interface_changed)):
            if node_id in self._nodes:
                reasons[node_id].append("public interface or surface changed")
                queue.append((node_id, INTERFACE_EDGES, "interface change from " + node_id))
        for node_id in sorted(set(behavior_changed)):
            if node_id in self._nodes:
                reasons[node_id].append("implementation body changed")
                queue.append((node_id, BEHAVIOR_EDGES, "behaviour change from " + node_id))
        for node_id in sorted(set(forced)):
            if node_id in self._nodes:
                reasons[node_id].append("explicitly forced")
                queue.append((node_id, INTERFACE_EDGES | BEHAVIOR_EDGES, "forced from " + node_id))

        seen: set[tuple[str, frozenset[EdgeKind]]] = set()
        while queue:
            node_id, kinds, why = queue.popleft()
            marker = (node_id, kinds)
            if marker in seen:
                continue
            seen.add(marker)
            for edge in sorted(self._out[node_id], key=lambda e: (e.target, e.kind.value)):
                if edge.kind not in kinds:
                    continue
                propagated = f"{why} via {edge.kind.value}"
                if propagated not in reasons[edge.target]:
                    reasons[edge.target].append(propagated)
                # Downstream of an interface change, behaviour also moves.
                queue.append((edge.target, kinds | ({edge.kind} & BEHAVIOR_EDGES), propagated))
        return {node_id: sorted(set(values)) for node_id, values in sorted(reasons.items())}

    # -- planning ---------------------------------------------------------
    def plan(
        self,
        affected: Mapping[str, Sequence[str]],
        cache_probe: CacheProbe | None = None,
        forced_execute: Iterable[str] = (),
        blocked: Iterable[str] = (),
    ) -> ExecutionPlan:
        """Decide, per node, execute / restore / skip / invalidated / blocked."""
        order = self.topological_order()
        blocked_set = set(blocked)
        forced_set = set(forced_execute)
        critical = self._critical_path_costs(order)

        plans: dict[str, NodePlan] = {}
        must_execute: set[str] = set()

        for node_id in order:
            node = self._nodes[node_id]
            reasons = list(affected.get(node_id, ()))
            upstream_executes = [
                dependency
                for dependency in self.dependencies(node_id)
                if dependency in must_execute
            ]

            if node_id in blocked_set:
                plans[node_id] = NodePlan(
                    node_id, NodeDecision.BLOCKED, ("node is blocked by policy or a failed gate",)
                )
                must_execute.add(node_id)
                continue

            if node_id in forced_set:
                plans[node_id] = NodePlan(
                    node_id,
                    NodeDecision.EXECUTE,
                    ("execution forced by the caller",),
                    critical_path_ms=critical[node_id],
                )
                must_execute.add(node_id)
                continue

            if upstream_executes:
                reasons.append(
                    "upstream nodes will re-execute: " + ", ".join(sorted(upstream_executes)[:5])
                )

            if not reasons:
                probe = cache_probe.probe(node) if cache_probe is not None else None
                if probe is not None and probe.hit:
                    plans[node_id] = NodePlan(
                        node_id,
                        NodeDecision.RESTORE,
                        ("unchanged inputs and a compatible cache entry",),
                        action_key=probe.action_key,
                        critical_path_ms=critical[node_id],
                    )
                    continue
                if probe is None:
                    plans[node_id] = NodePlan(
                        node_id,
                        NodeDecision.SKIP,
                        ("nothing upstream changed and no cache probe was requested",),
                        critical_path_ms=critical[node_id],
                    )
                    continue
                plans[node_id] = NodePlan(
                    node_id,
                    NodeDecision.EXECUTE,
                    ("inputs unchanged but no usable cache entry",),
                    miss_reasons=probe.reasons,
                    action_key=probe.action_key,
                    critical_path_ms=critical[node_id],
                )
                must_execute.add(node_id)
                continue

            probe = cache_probe.probe(node) if cache_probe is not None else None
            if probe is not None and probe.hit:
                # A changed input that still lands on a known ActionKey is a
                # legitimate hit: the key, not the diff, is the authority.
                plans[node_id] = NodePlan(
                    node_id,
                    NodeDecision.RESTORE,
                    tuple([*reasons, "inputs changed but the ActionKey resolves to a cached result"]),
                    action_key=probe.action_key,
                    critical_path_ms=critical[node_id],
                )
                continue
            plans[node_id] = NodePlan(
                node_id,
                NodeDecision.INVALIDATED,
                tuple(reasons),
                miss_reasons=probe.reasons if probe else (),
                action_key=probe.action_key if probe else None,
                critical_path_ms=critical[node_id],
            )
            must_execute.add(node_id)

        waves = self._waves(order, plans, critical)
        for wave_index, wave in enumerate(waves):
            for node_id in wave:
                plans[node_id] = NodePlan(
                    node_id,
                    plans[node_id].decision,
                    plans[node_id].reasons,
                    plans[node_id].miss_reasons,
                    plans[node_id].action_key,
                    wave=wave_index,
                    critical_path_ms=plans[node_id].critical_path_ms,
                )

        ordered_plans = tuple(plans[node_id] for node_id in order)
        digest = digest_of(
            {
                "nodes": [plan.to_dict() for plan in ordered_plans],
                "graph": [edge.to_dict() for edge in self.edges],
            }
        )
        return ExecutionPlan(
            plan_digest=digest,
            nodes=ordered_plans,
            waves=waves,
            arbitration=self.arbitrate_outputs(),
        )

    def _critical_path_costs(self, order: Sequence[str]) -> dict[str, int]:
        """Longest remaining cost to a sink; the scheduling priority."""
        costs: dict[str, int] = {}
        for node_id in reversed(list(order)):
            downstream = [costs[target] for target in self.dependents(node_id) if target in costs]
            costs[node_id] = self._nodes[node_id].estimated_cost_ms + (max(downstream) if downstream else 0)
        return costs

    def _waves(
        self, order: Sequence[str], plans: Mapping[str, NodePlan], critical: Mapping[str, int]
    ) -> tuple[tuple[str, ...], ...]:
        """Group into dependency-respecting waves; order inside a wave is stable.

        Sorting by (-critical path, resource class, cache locality, node id)
        gives the same schedule for the same inputs on every machine.
        """
        depth: dict[str, int] = {}
        for node_id in order:
            dependencies = self.dependencies(node_id)
            depth[node_id] = 0 if not dependencies else 1 + max(depth[d] for d in dependencies)
        grouped: dict[int, list[str]] = defaultdict(list)
        for node_id, level in depth.items():
            grouped[level].append(node_id)

        def sort_key(node_id: str) -> tuple[int, str, int, str]:
            node = self._nodes[node_id]
            locality = 0 if plans[node_id].decision is NodeDecision.RESTORE else 1
            return (-critical[node_id], node.resource_class, locality, node_id)

        return tuple(tuple(sorted(grouped[level], key=sort_key)) for level in sorted(grouped))

    # -- reporting --------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "contested_outputs": self.contested_outputs(),
        }

    def digest(self) -> str:
        return digest_of(self.to_dict())


@dataclass(frozen=True)
class ProbeResult:
    hit: bool
    action_key: str | None = None
    reasons: tuple[MissReason, ...] = ()


class CacheProbe:
    """Adapter so the planner can consult the Action Cache without owning it."""

    def __init__(self, resolver: Any) -> None:
        self._resolver = resolver

    def probe(self, node: DagNode) -> ProbeResult:
        if node.cache_mode is CacheMode.BYPASS:
            return ProbeResult(False, None, (MissReason.POLICY_BYPASS,))
        result = self._resolver(node)
        if isinstance(result, ProbeResult):
            return result
        raise ContractViolation("cache probe resolver must return a ProbeResult", node_id=node.node_id)


@dataclass
class PlanExecutionRecord:
    """Plan versus actual, so drift is visible instead of anecdotal."""

    plan: ExecutionPlan
    actual: dict[str, str] = field(default_factory=dict)

    def record(self, node_id: str, outcome: str) -> None:
        self.actual[node_id] = outcome

    def divergences(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for node_plan in self.plan.nodes:
            actual = self.actual.get(node_plan.node_id, "NOT_RUN")
            expected = node_plan.decision.value
            if actual != expected:
                rows.append(
                    {"node_id": node_plan.node_id, "planned": expected, "actual": actual}
                )
        return rows

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_digest": self.plan.plan_digest,
            "summary": self.plan.summary(),
            "actual": dict(sorted(self.actual.items())),
            "divergences": self.divergences(),
        }

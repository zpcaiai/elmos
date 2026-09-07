"""Skill 05 — the change closure.

Given seeds (the symbols an intent names) this module walks the semantic index
outwards along reference, call, import, inheritance, build, test, contract and
ownership edges until the closure stops growing, then reports:

* what will change and **why** — every member carries the edge chain that put
  it there, so "why is this file in my diff?" is answerable;
* which tests cover it, and which changed targets have **no** test;
* which public contracts and external consumers are reachable;
* the wave plan and shard plan, derived from the dependency structure rather
  than from file count;
* a risk assessment whose unknown-risk penalty *raises* risk rather than being
  averaged away.

The governing rule: **unknown is not no-impact.**  A dynamic reference, an
unparsed file or an unresolved edge widens the closure's uncertainty; it never
narrows the closure.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .buildgraph import BuildGraph
from .contracts import EntityKind, RelationshipType, RiskClass, match_path_glob, sha256_payload
from .discovery import RepositoryInventory
from .index import SemanticIndex
from .intent import CompiledIntent, Operation

#: Edge types that propagate impact *backwards* — if X changes, everything that
#: references X is affected.
_INBOUND_EDGES: frozenset[RelationshipType] = frozenset(
    {
        RelationshipType.REFERENCES,
        RelationshipType.CALLS,
        RelationshipType.IMPORTS,
        RelationshipType.INHERITS,
        RelationshipType.IMPLEMENTS,
        RelationshipType.OVERRIDES,
        RelationshipType.READS,
        RelationshipType.WRITES,
        RelationshipType.SERIALIZES,
        RelationshipType.PERSISTS,
        RelationshipType.SUBSCRIBES,
    }
)

#: Edge types that propagate *forwards* — changing X means its declarations,
#: build targets and tests come along.
_OUTBOUND_EDGES: frozenset[RelationshipType] = frozenset(
    {
        RelationshipType.DECLARES,
        RelationshipType.EXPORTS,
        RelationshipType.PUBLISHES,
    }
)

#: A symbol referenced by more than this many distinct entities is a hub: its
#: change is a repository-wide event regardless of the diff size.
HIGH_FAN_OUT_THRESHOLD = 25

MAX_CLOSURE_ENTITIES = 200_000


@dataclass(frozen=True, slots=True)
class ClosureMember:
    entity_id: str
    path: str
    qualified_name: str
    distance: int
    reason: str
    confidence: Decimal
    dynamic: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "entityId": self.entity_id,
            "path": self.path,
            "qualifiedName": self.qualified_name,
            "distance": self.distance,
            "reason": self.reason,
            "confidence": str(self.confidence),
            "dynamic": self.dynamic,
        }


@dataclass(frozen=True, slots=True)
class ChangeClosure:
    seeds: tuple[str, ...]
    members: tuple[ClosureMember, ...]
    truncated: bool = False

    @property
    def entity_ids(self) -> tuple[str, ...]:
        return tuple(member.entity_id for member in self.members)

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(sorted({member.path for member in self.members if member.path}))

    @property
    def dynamic_members(self) -> tuple[ClosureMember, ...]:
        return tuple(member for member in self.members if member.dynamic)

    @property
    def low_confidence_members(self) -> tuple[ClosureMember, ...]:
        return tuple(member for member in self.members if member.confidence < Decimal("0.7"))

    def reason_for(self, entity_id: str) -> str:
        for member in self.members:
            if member.entity_id == entity_id:
                return member.reason
        return ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "seeds": list(self.seeds),
            "size": len(self.members),
            "paths": list(self.paths),
            "truncated": self.truncated,
            "dynamicMembers": len(self.dynamic_members),
            "lowConfidenceMembers": len(self.low_confidence_members),
            "members": [member.to_payload() for member in self.members[:2000]],
        }


@dataclass(frozen=True, slots=True)
class TestSelection:
    targets: tuple[str, ...]
    test_targets: tuple[str, ...]
    test_paths: tuple[str, ...]
    uncovered_targets: tuple[str, ...]
    uncovered_paths: tuple[str, ...]

    @property
    def coverage(self) -> Decimal:
        total = len(self.targets)
        if total == 0:
            return Decimal("0")
        covered = total - len(self.uncovered_targets)
        return (Decimal(covered) / Decimal(total)).quantize(Decimal("0.0001"))

    def to_payload(self) -> dict[str, Any]:
        return {
            "changedTargets": list(self.targets),
            "testTargets": list(self.test_targets),
            "testPaths": list(self.test_paths),
            "uncoveredTargets": list(self.uncovered_targets),
            "uncoveredPaths": list(self.uncovered_paths),
            "coverage": str(self.coverage),
        }


@dataclass(frozen=True, slots=True)
class Shard:
    shard_id: str
    paths: tuple[str, ...]
    build_targets: tuple[str, ...] = ()
    owners: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "shardId": self.shard_id,
            "paths": list(self.paths),
            "buildTargets": list(self.build_targets),
            "owners": list(self.owners),
        }


@dataclass(frozen=True, slots=True)
class Wave:
    wave_id: str
    shards: tuple[Shard, ...]
    depends_on: tuple[str, ...] = ()
    rationale: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "waveId": self.wave_id,
            "dependsOn": list(self.depends_on),
            "rationale": self.rationale,
            "shards": [shard.to_payload() for shard in self.shards],
        }


@dataclass(frozen=True, slots=True)
class ConsumerRecord:
    contract: str
    path: str
    consumers: tuple[str, ...]
    external_visibility: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "path": self.path,
            "consumers": list(self.consumers),
            "externalVisibility": self.external_visibility,
        }


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    risk_class: RiskClass
    score: Decimal
    unknown_penalty: Decimal
    reasons: tuple[str, ...]
    hub_symbols: tuple[str, ...] = ()
    sensitive_areas: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "riskClass": self.risk_class.value,
            "score": str(self.score),
            "unknownPenalty": str(self.unknown_penalty),
            "reasons": list(self.reasons),
            "hubSymbols": list(self.hub_symbols),
            "sensitiveAreas": list(self.sensitive_areas),
        }


@dataclass(frozen=True, slots=True)
class ImpactReport:
    closure: ChangeClosure
    tests: TestSelection
    waves: tuple[Wave, ...]
    consumers: tuple[ConsumerRecord, ...]
    risk: RiskAssessment
    changed_files_estimate: int
    approval_points: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "changeClosure": self.closure.to_payload(),
            "testSelectionPlan": self.tests.to_payload(),
            "wavePlan": [wave.to_payload() for wave in self.waves],
            "consumerMatrix": [item.to_payload() for item in self.consumers],
            "riskAssessment": self.risk.to_payload(),
            "changedFilesEstimate": self.changed_files_estimate,
            "approvalPoints": list(self.approval_points),
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


# ---------------------------------------------------------------------------
# Closure
# ---------------------------------------------------------------------------


def compute_closure(
    index: SemanticIndex,
    seeds: Sequence[str],
    *,
    max_distance: int = 6,
    allowed_globs: Sequence[str] = (),
    max_entities: int = MAX_CLOSURE_ENTITIES,
) -> ChangeClosure:
    """Breadth-first closure over impact-propagating edges.

    Distance is capped, and hitting the cap is *reported* rather than treated
    as "the closure ended here": a truncated closure is an incomplete answer,
    and downstream risk maths must know that.
    """

    inbound: dict[str, list[tuple[str, RelationshipType, Decimal, bool]]] = defaultdict(list)
    outbound: dict[str, list[tuple[str, RelationshipType, Decimal, bool]]] = defaultdict(list)
    for relationship in index.relationships:
        if relationship.type in _INBOUND_EDGES:
            inbound[relationship.to_id].append(
                (relationship.from_id, relationship.type, relationship.confidence, relationship.dynamic)
            )
        if relationship.type in _OUTBOUND_EDGES:
            outbound[relationship.from_id].append(
                (relationship.to_id, relationship.type, relationship.confidence, relationship.dynamic)
            )

    by_id = {entity.id: entity for entity in index.entities}
    visited: dict[str, ClosureMember] = {}
    queue: deque[tuple[str, int, str, Decimal, bool]] = deque()
    for seed in dict.fromkeys(seeds):
        queue.append((seed, 0, "seed", Decimal("1"), False))
    truncated = False

    while queue:
        entity_id, distance, reason, confidence, dynamic = queue.popleft()
        if entity_id in visited:
            existing = visited[entity_id]
            if distance >= existing.distance:
                continue
        if len(visited) >= max_entities:
            truncated = True
            break
        entity = by_id.get(entity_id)
        path = entity.path if entity else ""
        if allowed_globs and path and not any(match_path_glob(path, glob) for glob in allowed_globs):
            # Out of scope: recorded so the caller sees that impact reached
            # beyond the permitted scope, but not expanded through.
            visited[entity_id] = ClosureMember(
                entity_id=entity_id,
                path=path,
                qualified_name=entity.qualified_name if entity else "",
                distance=distance,
                reason=f"{reason} (outside allowed scope; not expanded)",
                confidence=confidence,
                dynamic=dynamic,
            )
            continue
        visited[entity_id] = ClosureMember(
            entity_id=entity_id,
            path=path,
            qualified_name=entity.qualified_name if entity else "",
            distance=distance,
            reason=reason,
            confidence=confidence,
            dynamic=dynamic,
        )
        if distance >= max_distance:
            truncated = True
            continue
        for neighbour, edge, edge_confidence, edge_dynamic in (
            *inbound.get(entity_id, ()),
            *outbound.get(entity_id, ()),
        ):
            if neighbour in visited:
                continue
            queue.append(
                (
                    neighbour,
                    distance + 1,
                    f"{reason} -> {edge.value}",
                    min(confidence, edge_confidence),
                    dynamic or edge_dynamic,
                )
            )

    members = tuple(sorted(visited.values(), key=lambda item: (item.distance, item.path, item.entity_id)))
    return ChangeClosure(seeds=tuple(dict.fromkeys(seeds)), members=members, truncated=truncated)


def _hub_symbols(index: SemanticIndex, closure: ChangeClosure) -> tuple[str, ...]:
    counts: dict[str, int] = defaultdict(int)
    for relationship in index.relationships:
        counts[relationship.to_id] += 1
    inside = set(closure.entity_ids)
    hubs = [
        entity.qualified_name or entity.name
        for entity in index.entities
        if entity.id in inside and counts[entity.id] >= HIGH_FAN_OUT_THRESHOLD
    ]
    return tuple(sorted(set(hubs)))


def select_tests(closure: ChangeClosure, graph: BuildGraph, inventory: RepositoryInventory) -> TestSelection:
    """Map changed paths to test targets, and report what has none."""

    changed_paths = [path for path in closure.paths if path not in set(inventory.test_paths)]
    targets: set[str] = set()
    for path in changed_paths:
        targets.update(graph.targets_for(path))
    test_targets = graph.tests_for_paths(changed_paths)
    uncovered = sorted(target for target in targets if not graph.target_to_tests.get(target))
    covered_paths = {
        path
        for path in changed_paths
        if any(graph.target_to_tests.get(target) for target in graph.targets_for(path))
    }
    test_paths = sorted(
        {
            path
            for path in inventory.test_paths
            if any(target in test_targets for target in graph.targets_for(path))
        }
    )
    return TestSelection(
        targets=tuple(sorted(targets)),
        test_targets=test_targets,
        test_paths=tuple(test_paths),
        uncovered_targets=tuple(uncovered),
        uncovered_paths=tuple(sorted(set(changed_paths) - covered_paths)),
    )


def plan_waves(
    closure: ChangeClosure,
    graph: BuildGraph,
    inventory: RepositoryInventory,
    *,
    max_shard_paths: int = 200,
) -> tuple[Wave, ...]:
    """Group changed paths into ordered waves and bounded shards.

    Waves follow dependency depth (providers before consumers); shards inside a
    wave are cut along build-target and ownership boundaries so a shard failure
    maps to one owner and one build.
    """

    by_distance: dict[int, list[str]] = defaultdict(list)
    seen: set[str] = set()
    for member in closure.members:
        if not member.path or member.path in seen:
            continue
        seen.add(member.path)
        by_distance[member.distance].append(member.path)

    waves: list[Wave] = []
    previous: str | None = None
    for distance in sorted(by_distance):
        paths = sorted(by_distance[distance])
        grouped: dict[str, list[str]] = defaultdict(list)
        for path in paths:
            targets = graph.targets_for(path)
            key = targets[0] if targets else "unassigned"
            grouped[key].append(path)
        shards: list[Shard] = []
        for key in sorted(grouped):
            members = sorted(grouped[key])
            for offset in range(0, len(members), max_shard_paths):
                chunk = tuple(members[offset : offset + max_shard_paths])
                owners = sorted({owner for item in chunk for owner in inventory.owners_of(item)})
                shards.append(
                    Shard(
                        shard_id=f"w{distance}-{key.replace(':', '_')}-{offset // max_shard_paths}",
                        paths=chunk,
                        build_targets=(key,) if key != "unassigned" else (),
                        owners=tuple(owners),
                    )
                )
        wave = Wave(
            wave_id=f"wave-{distance}",
            shards=tuple(shards),
            depends_on=(previous,) if previous else (),
            rationale=f"dependency distance {distance} from the change seeds",
        )
        waves.append(wave)
        previous = wave.wave_id
    return tuple(waves)


def find_consumers(index: SemanticIndex, closure: ChangeClosure) -> tuple[ConsumerRecord, ...]:
    """Public contracts inside the closure, and who consumes them."""

    inside = set(closure.entity_ids)
    records: list[ConsumerRecord] = []
    for entity in index.entities:
        if entity.id not in inside:
            continue
        if entity.kind not in (EntityKind.API_CONTRACT, EntityKind.EVENT_CONTRACT):
            exported_symbol = entity.visibility in ("public", "exported") and entity.kind in (
                EntityKind.TYPE,
                EntityKind.FUNCTION,
                EntityKind.METHOD,
            )
            if not exported_symbol:
                continue
        consumers = sorted(
            {
                relationship.from_id
                for relationship in index.incoming(entity.id)
                if relationship.type
                in (RelationshipType.CALLS, RelationshipType.REFERENCES, RelationshipType.SUBSCRIBES)
            }
        )
        #: An exported symbol with no in-repository consumer is *more*
        #: dangerous, not less: its consumers are outside where we cannot see
        #: them.
        visibility = "in-repository" if consumers else "unknown-external"
        records.append(
            ConsumerRecord(
                contract=entity.qualified_name or entity.name,
                path=entity.path,
                consumers=tuple(consumers[:200]),
                external_visibility=visibility,
            )
        )
    return tuple(sorted(records, key=lambda item: (item.path, item.contract)))


def assess_risk(
    intent: CompiledIntent,
    index: SemanticIndex,
    closure: ChangeClosure,
    tests: TestSelection,
    inventory: RepositoryInventory,
    consumers: Sequence[ConsumerRecord],
) -> RiskAssessment:
    """Combine structural facts into a risk class, penalising uncertainty."""

    reasons: list[str] = []
    score = Decimal("0")

    size_factor = min(Decimal("0.25"), Decimal(len(closure.paths)) / Decimal(400))
    score += size_factor
    if len(closure.paths) > 50:
        reasons.append(f"{len(closure.paths)} file(s) in the change closure")

    hubs = _hub_symbols(index, closure)
    if hubs:
        score += Decimal("0.15")
        reasons.append(f"{len(hubs)} high fan-out symbol(s) in scope: " + ", ".join(hubs[:5]))

    touched_sensitive = sorted(
        {
            hit.area
            for hit in inventory.sensitive_areas
            if hit.path in set(closure.paths)
        }
    )
    if touched_sensitive:
        score += Decimal("0.25")
        reasons.append("sensitive areas touched: " + ", ".join(touched_sensitive))

    if tests.coverage < Decimal("0.8"):
        score += Decimal("0.2")
        reasons.append(f"only {tests.coverage} of changed targets have a linked test")
    if tests.uncovered_paths:
        reasons.append(f"{len(tests.uncovered_paths)} changed path(s) have no test at all")

    external = [item for item in consumers if item.external_visibility == "unknown-external"]
    if external:
        score += Decimal("0.15")
        reasons.append(f"{len(external)} public contract(s) have no visible consumer and may be used externally")

    unknown_penalty = index.coverage.unknown_risk_weight
    if closure.truncated:
        unknown_penalty = min(Decimal("1"), unknown_penalty + Decimal("0.2"))
        reasons.append("the change closure hit its traversal limit and is incomplete")
    if closure.dynamic_members:
        unknown_penalty = min(Decimal("1"), unknown_penalty + Decimal("0.1"))
        reasons.append(f"{len(closure.dynamic_members)} closure member(s) were reached only by a dynamic reference")
    score += unknown_penalty * Decimal("0.5")

    floor = intent.risk_floor
    if score >= Decimal("0.75"):
        derived = RiskClass.R4
    elif score >= Decimal("0.5"):
        derived = RiskClass.R3
    elif score >= Decimal("0.25"):
        derived = RiskClass.R2
    elif score > Decimal("0"):
        derived = RiskClass.R1
    else:
        derived = RiskClass.R0
    resolved = RiskClass.max_of([floor, derived])
    if resolved is not derived:
        reasons.append(f"risk floor from intent/constraints is {floor.value}")

    return RiskAssessment(
        risk_class=resolved,
        score=min(Decimal("1"), score).quantize(Decimal("0.0001")),
        unknown_penalty=unknown_penalty,
        reasons=tuple(reasons),
        hub_symbols=hubs,
        sensitive_areas=tuple(touched_sensitive),
    )


def analyse_impact(
    intent: CompiledIntent,
    index: SemanticIndex,
    graph: BuildGraph,
    inventory: RepositoryInventory,
    *,
    max_distance: int = 6,
) -> ImpactReport:
    """Full impact analysis for a compiled intent."""

    seeds: list[str] = []
    for goal in intent.goals:
        seeds.extend(goal.resolved_entities)
    if not seeds:
        #: No named target is not "no impact": fall back to the scope policy,
        #: which is the widest set the operator has authorised.
        seeds = [
            entity.id
            for entity in index.entities
            if entity.kind in (EntityKind.SOURCE_FILE,)
            and any(match_path_glob(entity.path, glob) for glob in intent.scope.allowed_paths)
        ]

    closure = compute_closure(
        index,
        seeds,
        max_distance=max_distance,
        allowed_globs=intent.scope.allowed_paths,
    )
    tests = select_tests(closure, graph, inventory)
    waves = plan_waves(closure, graph, inventory)
    consumers = find_consumers(index, closure)
    risk = assess_risk(intent, index, closure, tests, inventory, consumers)

    approvals: list[str] = []
    if risk.risk_class.rank >= RiskClass.R3.rank:
        approvals.append(f"risk class {risk.risk_class.value} requires approval before any mutating step")
    if tests.uncovered_paths:
        approvals.append("changed paths without test coverage require an explicit risk acceptance")
    for record in consumers:
        if record.external_visibility == "unknown-external":
            approvals.append(f"contract '{record.contract}' may have external consumers")
            break
    for conflict in intent.conflicts:
        approvals.append("constraint conflict: " + ", ".join(conflict.minimal_set))

    forbidden = [
        path
        for path in closure.paths
        if any(match_path_glob(path, glob) for glob in intent.scope.forbidden_paths)
    ]
    if forbidden:
        approvals.append(f"{len(forbidden)} path(s) in the closure are explicitly forbidden by scope policy")

    return ImpactReport(
        closure=closure,
        tests=tests,
        waves=waves,
        consumers=consumers,
        risk=risk,
        changed_files_estimate=len(closure.paths),
        approval_points=tuple(dict.fromkeys(approvals)),
    )


def operations_requiring_contract_work(intent: CompiledIntent) -> tuple[Operation, ...]:
    return tuple(
        operation
        for operation in intent.operations
        if operation
        in {
            Operation.CONTRACT_EVOLUTION,
            Operation.CHANGE_SIGNATURE,
            Operation.SPLIT_SERVICE,
            Operation.SCHEMA_EXPAND_CONTRACT,
        }
    )


__all__ = [
    "HIGH_FAN_OUT_THRESHOLD",
    "ChangeClosure",
    "ClosureMember",
    "ConsumerRecord",
    "ImpactReport",
    "RiskAssessment",
    "Shard",
    "TestSelection",
    "Wave",
    "analyse_impact",
    "assess_risk",
    "compute_closure",
    "find_consumers",
    "plan_waves",
    "select_tests",
]

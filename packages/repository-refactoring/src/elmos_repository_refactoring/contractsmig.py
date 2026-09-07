"""Skill 08 — cross-language contract evolution.

Plans the migration of a REST / gRPC / GraphQL / event / SDK contract across
producers and consumers that may live in different languages and repositories.

The shape of the plan is fixed by three facts that do not change with the
technology:

* **Additive first.**  The new shape is published alongside the old one; both
  work simultaneously.  Nothing is removed in the same wave that adds.
* **Order depends on who breaks.**  A producer-breaking change goes
  consumer-first (consumers learn to accept both, then the producer switches);
  a consumer-breaking change goes provider-first.  Choosing the wrong order is
  what turns a migration into an outage.
* **Removal needs evidence, not a calendar.**  The cleanup wave is gated on
  old-path usage reaching zero in telemetry, not on a date.

Generated clients are regenerated from the IDL rather than patched: a
hand-edited generated file is a change that the next codegen run silently
reverts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .apicompat import ApiDiff
from .contracts import (
    CompatibilityImpact,
    EntityKind,
    RelationshipType,
    RiskClass,
    match_path_glob,
    sha256_payload,
)
from .index import SemanticIndex
from .workspace import WorkspaceSnapshot, classify_path


class ContractKind(StrEnum):
    REST = "rest"
    GRPC = "grpc"
    GRAPHQL = "graphql"
    EVENT = "event"
    SDK = "sdk"
    CONFIG = "config"
    FILE_FORMAT = "file-format"


class MigrationOrder(StrEnum):
    PROVIDER_FIRST = "provider-before-consumer"
    CONSUMER_FIRST = "consumer-before-provider"
    SIMULTANEOUS = "simultaneous"


#: Which source-of-truth file shapes map to which contract kind.
SOURCE_OF_TRUTH: Mapping[ContractKind, tuple[str, ...]] = {
    ContractKind.REST: ("**/openapi.yaml", "**/openapi.yml", "**/openapi.json", "**/swagger.*"),
    ContractKind.GRPC: ("**/*.proto",),
    ContractKind.GRAPHQL: ("**/*.graphql", "**/*.gql"),
    ContractKind.EVENT: ("**/asyncapi.yaml", "**/asyncapi.yml", "**/*.avsc", "**/events/**/*.json"),
    ContractKind.CONFIG: ("**/*.schema.json",),
}

#: Paths that hold *generated* clients.  These are rebuilt, never patched.
GENERATED_CLIENT_MARKERS = (
    "**/generated/**",
    "**/gen/**",
    "**/*_pb2.py",
    "**/*_pb2_grpc.py",
    "**/*.pb.go",
    "**/*.generated.ts",
    "**/openapi-client/**",
)


@dataclass(frozen=True, slots=True)
class ContractSource:
    kind: ContractKind
    path: str
    digest: str

    def to_payload(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "path": self.path, "digest": self.digest}


@dataclass(frozen=True, slots=True)
class ConsumerEntry:
    identifier: str
    path: str
    role: str
    language: str
    generated: bool
    visible: bool = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "path": self.path,
            "role": self.role,
            "language": self.language,
            "generated": self.generated,
            "visible": self.visible,
        }


@dataclass(frozen=True, slots=True)
class ContractWave:
    wave_id: str
    title: str
    order: int
    actions: tuple[str, ...]
    gate: str
    depends_on: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "waveId": self.wave_id,
            "title": self.title,
            "order": self.order,
            "actions": list(self.actions),
            "gate": self.gate,
            "dependsOn": list(self.depends_on),
        }


@dataclass(frozen=True, slots=True)
class ContractMigrationPlan:
    sources: tuple[ContractSource, ...]
    consumers: tuple[ConsumerEntry, ...]
    order: MigrationOrder
    waves: tuple[ContractWave, ...]
    compatibility_adapters: tuple[Mapping[str, Any], ...]
    risk_class: RiskClass
    reasons: tuple[str, ...] = field(default_factory=tuple)
    blocked_reason: str = ""

    @property
    def invisible_consumers(self) -> tuple[ConsumerEntry, ...]:
        return tuple(item for item in self.consumers if not item.visible)

    @property
    def executable(self) -> bool:
        return not self.blocked_reason

    def to_payload(self) -> dict[str, Any]:
        return {
            "sources": [item.to_payload() for item in self.sources],
            "consumerMatrix": [item.to_payload() for item in self.consumers],
            "order": self.order.value,
            "waves": [item.to_payload() for item in self.waves],
            "compatibilityAdapters": [dict(item) for item in self.compatibility_adapters],
            "riskClass": self.risk_class.value,
            "invisibleConsumers": len(self.invisible_consumers),
            "reasons": list(self.reasons),
            "executable": self.executable,
            "blockedReason": self.blocked_reason,
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


def find_sources(snapshot: WorkspaceSnapshot) -> tuple[ContractSource, ...]:
    """Locate contract sources of truth in the snapshot."""

    found: list[ContractSource] = []
    for kind, patterns in SOURCE_OF_TRUTH.items():
        for path in snapshot.match(list(patterns)):
            record = snapshot.require(path)
            found.append(ContractSource(kind=kind, path=path, digest=record.content_digest))
    return tuple(sorted(found, key=lambda item: item.path))


def find_consumers(
    index: SemanticIndex,
    snapshot: WorkspaceSnapshot,
    sources: Sequence[ContractSource],
) -> tuple[ConsumerEntry, ...]:
    """Every producer, generated client, hand-written client and test in scope."""

    source_paths = {item.path for item in sources}
    contract_entities = [
        entity
        for entity in index.entities
        if entity.kind in (EntityKind.API_CONTRACT, EntityKind.EVENT_CONTRACT)
        and entity.path in source_paths
    ]
    entries: list[ConsumerEntry] = []
    seen: set[str] = set()
    for entity in contract_entities:
        referrers = [
            relationship
            for relationship in index.incoming(entity.id)
            if relationship.type
            in (RelationshipType.CALLS, RelationshipType.REFERENCES, RelationshipType.SUBSCRIBES)
        ]
        for relationship in referrers:
            if not relationship.path or relationship.path in seen:
                continue
            seen.add(relationship.path)
            labels = classify_path(relationship.path)
            entries.append(
                ConsumerEntry(
                    identifier=entity.qualified_name or entity.name,
                    path=relationship.path,
                    role="test" if "test" in labels else "consumer",
                    language=_language_of(index, relationship.path),
                    generated=any(
                        match_path_glob(relationship.path, glob) for glob in GENERATED_CLIENT_MARKERS
                    ),
                )
            )
        if not referrers:
            #: A published contract that nothing in this repository consumes is
            #: the *dangerous* case: its consumers are outside where we can see
            #: them, so its removal risk is higher, not lower.
            entries.append(
                ConsumerEntry(
                    identifier=entity.qualified_name or entity.name,
                    path=entity.path,
                    role="external",
                    language=entity.language,
                    generated=False,
                    visible=False,
                )
            )
    for path in snapshot.match(list(GENERATED_CLIENT_MARKERS)):
        if path in seen:
            continue
        seen.add(path)
        entries.append(
            ConsumerEntry(
                identifier=path,
                path=path,
                role="generated-client",
                language=_language_of(index, path),
                generated=True,
            )
        )
    return tuple(sorted(entries, key=lambda item: (item.role, item.path)))


def _language_of(index: SemanticIndex, path: str) -> str:
    for entity in index.in_path(path):
        if entity.language and entity.language != "unknown":
            return entity.language
    from .adapters import language_of

    return language_of(path)


def choose_order(diff: ApiDiff) -> tuple[MigrationOrder, str]:
    """Pick the wave order from what the change actually breaks."""

    if diff.wire_breaks:
        return (
            MigrationOrder.CONSUMER_FIRST,
            "a wire break must be absorbed by consumers before the producer emits the new shape",
        )
    if diff.source_breaks or diff.binary_breaks:
        return (
            MigrationOrder.PROVIDER_FIRST,
            "a source or binary break is compiled against, so the provider publishes the new surface first",
        )
    if diff.behavior_risks:
        return (
            MigrationOrder.PROVIDER_FIRST,
            "behaviour risk needs the provider deployed and observed before consumers rely on it",
        )
    return (MigrationOrder.SIMULTANEOUS, "the change is additive; no ordering constraint applies")


def plan_contract_migration(
    snapshot: WorkspaceSnapshot,
    index: SemanticIndex,
    diff: ApiDiff,
    *,
    compatibility_policy: str = "backward-compatible",
) -> ContractMigrationPlan:
    """Build the wave plan for one contract change."""

    sources = find_sources(snapshot)
    consumers = find_consumers(index, snapshot, sources)
    order, order_reason = choose_order(diff)
    reasons: list[str] = [order_reason]
    blocked = ""

    if not sources:
        blocked = "no contract source of truth was found; a contract migration needs an IDL to evolve"
    if diff.wire_breaks and compatibility_policy in ("strict", "backward-compatible"):
        blocked = blocked or (
            f"{diff.wire_breaks} wire break(s) under policy '{compatibility_policy}'; "
            "publish a new version instead of changing the existing wire shape"
        )

    invisible = [item for item in consumers if not item.visible]
    if invisible:
        reasons.append(
            f"{len(invisible)} contract(s) have no visible consumer; removal risk is raised, not lowered"
        )
    generated = [item for item in consumers if item.generated]
    if generated:
        reasons.append(
            f"{len(generated)} generated client path(s) will be regenerated from the IDL, not patched"
        )

    waves = _build_waves(order, diff, generated=bool(generated))
    adapters = _adapters_for(diff)
    risk = (
        RiskClass.R4
        if diff.wire_breaks
        else RiskClass.R3
        if diff.breaks
        else RiskClass.R2
        if diff.changes
        else RiskClass.R1
    )
    return ContractMigrationPlan(
        sources=sources,
        consumers=consumers,
        order=order,
        waves=waves,
        compatibility_adapters=adapters,
        risk_class=risk,
        reasons=tuple(reasons),
        blocked_reason=blocked,
    )


def _build_waves(order: MigrationOrder, diff: ApiDiff, *, generated: bool) -> tuple[ContractWave, ...]:
    waves: list[ContractWave] = [
        ContractWave(
            wave_id="wave-0-compatibility",
            title="Publish the new shape alongside the old",
            order=0,
            actions=(
                "add the new fields, methods or version to the source of truth",
                "keep every existing field, method and wire number unchanged",
                *(("regenerate all clients from the IDL",) if generated else ()),
                "add contract tests covering both shapes",
            ),
            gate="api-compatibility",
        )
    ]
    if order is MigrationOrder.CONSUMER_FIRST:
        waves.append(
            ContractWave(
                "wave-1-consumers",
                "Teach every consumer to accept both shapes",
                1,
                ("update consumers to read old-or-new", "deploy consumers", "verify with dual-shape fixtures"),
                "changed-target-tests",
                ("wave-0-compatibility",),
            )
        )
        waves.append(
            ContractWave(
                "wave-2-provider",
                "Switch the producer to the new shape",
                2,
                ("emit the new shape", "keep accepting the old shape on input"),
                "full-tests",
                ("wave-1-consumers",),
            )
        )
    elif order is MigrationOrder.PROVIDER_FIRST:
        waves.append(
            ContractWave(
                "wave-1-provider",
                "Deploy the provider with both surfaces",
                1,
                ("serve the new surface", "keep the old surface serving unchanged"),
                "api-compatibility",
                ("wave-0-compatibility",),
            )
        )
        waves.append(
            ContractWave(
                "wave-2-consumers",
                "Migrate consumers onto the new surface",
                2,
                ("update each consumer", "regenerate clients", "deploy per consumer"),
                "changed-target-tests",
                ("wave-1-provider",),
            )
        )
    else:
        waves.append(
            ContractWave(
                "wave-1-adopt",
                "Adopt the additive change",
                1,
                ("consumers may adopt at their own pace",),
                "changed-target-tests",
                ("wave-0-compatibility",),
            )
        )
    if diff.breaks:
        waves.append(
            ContractWave(
                "wave-3-cleanup",
                "Remove the old shape",
                3,
                (
                    "confirm old-path usage telemetry has read zero for a full release window",
                    "obtain approval bound to this exact API diff",
                    "remove the old fields, methods or version",
                    "regenerate clients and re-run contract tests",
                ),
                "old-path-usage-zero",
                (waves[-1].wave_id,),
            )
        )
    return tuple(waves)


def _adapters_for(diff: ApiDiff) -> tuple[Mapping[str, Any], ...]:
    outlines: list[Mapping[str, Any]] = []
    for change in diff.changes:
        if change.impact is CompatibilityImpact.ADDITIVE:
            continue
        outlines.append(
            {
                "identity": change.identity,
                "impact": change.impact.value,
                "adapter": _adapter_strategy(change.change),
                "removableAfter": "wave-3-cleanup",
            }
        )
    return tuple(outlines)


def _adapter_strategy(change: str) -> str:
    return {
        "removed": "keep a deprecated forwarding implementation that delegates to the new shape",
        "required-parameter-added": "default the new parameter at the boundary for old callers",
        "parameter-removed": "accept and ignore the removed parameter, logging its use",
        "wire-number-changed": "restore the original number; introduce the new field under a fresh number",
        "sync-async-changed": "expose a synchronous facade over the asynchronous implementation",
        "visibility-changed": "re-export the symbol from its previous location",
    }.get(change, "hand-written adapter plus a contract test that exercises both shapes")


def contract_diff_payload(diff: ApiDiff, plan: ContractMigrationPlan) -> dict[str, Any]:
    return {
        "contractMigrationPlan": plan.to_payload(),
        "compatibilityAdapters": [dict(item) for item in plan.compatibility_adapters],
        "consumerMatrix": [item.to_payload() for item in plan.consumers],
        "contractDiff": diff.to_payload(),
    }


__all__ = [
    "GENERATED_CLIENT_MARKERS",
    "SOURCE_OF_TRUTH",
    "ConsumerEntry",
    "ContractKind",
    "ContractMigrationPlan",
    "ContractSource",
    "ContractWave",
    "MigrationOrder",
    "choose_order",
    "contract_diff_payload",
    "find_consumers",
    "find_sources",
    "plan_contract_migration",
]

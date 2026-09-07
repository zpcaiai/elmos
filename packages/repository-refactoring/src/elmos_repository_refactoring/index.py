"""Skill 03 — the semantic index.

Assembles per-file extraction into one queryable, content-addressed graph of
entities and relationships that conforms to ``contracts/semantic-ir.schema.json``,
and reports honest coverage alongside it.

What "honest coverage" means here:

* ``resolution`` counts only references that were bound to a *known* entity.
  An import of a third-party package is resolved-as-external, not resolved.
* ``type_attribution`` counts only entities produced by a compiler-tier
  extractor, because a regex cannot attribute a type.
* ``unknown_risk_weight`` rises with unparsed files, dynamic-reference markers
  and unmapped build files.  It is the number a planner must consult before
  claiming an impact closure is complete.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .adapters import language_of
from .buildgraph import BuildGraph
from .contracts import (
    ContractError,
    EntityKind,
    RelationshipType,
    sha256_payload,
)
from .discovery import RepositoryInventory
from .extractors import ExtractionResult, SourceSpan, extract, supported
from .workspace import WorkspaceSnapshot, classify_path

IR_VERSION = "1.0.0"
API_VERSION = "elmos.dev/v1"
SNAPSHOT_KIND = "SemanticIndexSnapshot"

_ZERO = Decimal("0")
_ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class SemanticEntity:
    id: str
    kind: EntityKind
    language: str
    name: str
    repository_id: str
    path: str
    span: SourceSpan | None = None
    qualified_name: str = ""
    signature: str = ""
    visibility: str = "unknown"
    confidence: Decimal = _ONE
    content_digest: str = ""
    attributes: Mapping[str, Any] = field(default_factory=dict)
    provenance_adapter: str = "native"
    provenance_version: str = IR_VERSION

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind.value,
            "language": self.language,
            "name": self.name,
            "confidence": str(self.confidence),
            "provenance": {"adapter": self.provenance_adapter, "version": self.provenance_version},
        }
        if self.qualified_name:
            payload["qualifiedName"] = self.qualified_name
        if self.signature:
            payload["signature"] = self.signature
        if self.span is not None:
            payload["sourceRange"] = {
                "repositoryId": self.repository_id,
                "path": self.path,
                **self.span.to_payload(),
            }
        if self.visibility != "unknown":
            payload["visibility"] = self.visibility
        if self.attributes:
            payload["attributes"] = dict(sorted(self.attributes.items()))
        if self.content_digest:
            payload["contentDigest"] = self.content_digest
        return payload


@dataclass(frozen=True, slots=True)
class SemanticRelationship:
    id: str
    type: RelationshipType
    from_id: str
    to_id: str
    confidence: Decimal = _ONE
    repository_id: str = ""
    path: str = ""
    span: SourceSpan | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @property
    def dynamic(self) -> bool:
        return bool(self.attributes.get("dynamic", False))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.type.value,
            "from": self.from_id,
            "to": self.to_id,
            "confidence": str(self.confidence),
        }
        if self.span is not None and self.path:
            payload["sourceRange"] = {
                "repositoryId": self.repository_id,
                "path": self.path,
                **self.span.to_payload(),
            }
        if self.attributes:
            payload["attributes"] = dict(sorted(self.attributes.items()))
        return payload


@dataclass(frozen=True, slots=True)
class CoverageMetrics:
    resolution: Decimal
    type_attribution: Decimal
    build_graph: Decimal
    test_link: Decimal
    unknown_risk_weight: Decimal
    parsed_files: int = 0
    total_files: int = 0
    dynamic_files: int = 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "resolution": str(self.resolution),
            "typeAttribution": str(self.type_attribution),
            "buildGraph": str(self.build_graph),
            "testLink": str(self.test_link),
            "unknownRiskWeight": str(self.unknown_risk_weight),
            "parsedFiles": self.parsed_files,
            "totalFiles": self.total_files,
            "dynamicFiles": self.dynamic_files,
        }

    def meets(self, minimum: Mapping[str, Decimal]) -> tuple[str, ...]:
        """Names of coverage dimensions below their required minimum."""

        actual = {
            "resolution": self.resolution,
            "typeAttribution": self.type_attribution,
            "buildGraph": self.build_graph,
            "testLink": self.test_link,
        }
        return tuple(sorted(name for name, floor in minimum.items() if actual.get(name, _ZERO) < floor))


@dataclass(frozen=True, slots=True)
class UnknownRegion:
    path: str
    reason: str
    language: str = "unknown"
    detail: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {"path": self.path, "reason": self.reason, "language": self.language, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class SemanticIndex:
    snapshot_id: str
    repository_id: str
    revision: str
    tree_digest: str
    entities: tuple[SemanticEntity, ...]
    relationships: tuple[SemanticRelationship, ...]
    coverage: CoverageMetrics
    unknown_regions: tuple[UnknownRegion, ...] = ()
    adapter_digests: tuple[str, ...] = ()

    # -- indices ---------------------------------------------------------

    def __post_init__(self) -> None:
        ids = [entity.id for entity in self.entities]
        if len(set(ids)) != len(ids):
            raise ContractError("duplicate_entity", "semantic index contains duplicate entity ids")

    def entity(self, entity_id: str) -> SemanticEntity:
        for item in self.entities:
            if item.id == entity_id:
                return item
        raise ContractError("unknown_entity", f"semantic index has no entity '{entity_id}'")

    def by_qualified_name(self, qualified_name: str) -> tuple[SemanticEntity, ...]:
        return tuple(item for item in self.entities if item.qualified_name == qualified_name)

    def by_name(self, name: str) -> tuple[SemanticEntity, ...]:
        return tuple(item for item in self.entities if item.name == name)

    def in_path(self, path: str) -> tuple[SemanticEntity, ...]:
        return tuple(item for item in self.entities if item.path == path)

    def of_kind(self, kind: EntityKind) -> tuple[SemanticEntity, ...]:
        return tuple(item for item in self.entities if item.kind is kind)

    def incoming(self, entity_id: str) -> tuple[SemanticRelationship, ...]:
        return tuple(item for item in self.relationships if item.to_id == entity_id)

    def outgoing(self, entity_id: str) -> tuple[SemanticRelationship, ...]:
        return tuple(item for item in self.relationships if item.from_id == entity_id)

    def referrers(self, entity_id: str) -> tuple[str, ...]:
        """Entities that reference ``entity_id``, including dynamically."""

        return tuple(sorted({item.from_id for item in self.incoming(entity_id)}))

    def paths_touching(self, entity_ids: Iterable[str]) -> tuple[str, ...]:
        wanted = set(entity_ids)
        found: set[str] = set()
        for entity in self.entities:
            if entity.id in wanted and entity.path:
                found.add(entity.path)
        for relationship in self.relationships:
            if (relationship.to_id in wanted or relationship.from_id in wanted) and relationship.path:
                found.add(relationship.path)
        return tuple(sorted(found))

    @property
    def dynamic_relationships(self) -> tuple[SemanticRelationship, ...]:
        return tuple(item for item in self.relationships if item.dynamic)

    # -- serialisation ---------------------------------------------------

    def to_payload(self) -> dict[str, Any]:
        return {
            "apiVersion": API_VERSION,
            "kind": SNAPSHOT_KIND,
            "snapshotId": self.snapshot_id,
            "irVersion": IR_VERSION,
            "repositories": [
                {
                    "repositoryId": self.repository_id,
                    "revision": self.revision,
                    "treeDigest": self.tree_digest,
                    "adapterDigests": list(self.adapter_digests),
                }
            ],
            "entities": [entity.to_payload() for entity in self.entities],
            "relationships": [item.to_payload() for item in self.relationships],
            "coverage": self.coverage.to_payload(),
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())

    def unknown_region_report(self) -> dict[str, Any]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for region in self.unknown_regions:
            grouped[region.reason].append(region.path)
        return {
            "totalUnknownPaths": len(self.unknown_regions),
            "byReason": {reason: sorted(paths) for reason, paths in sorted(grouped.items())},
            "dynamicReferences": [
                {"from": item.from_id, "to": item.to_id, "path": item.path, "confidence": str(item.confidence)}
                for item in self.dynamic_relationships[:500]
            ],
            "unknownRiskWeight": str(self.coverage.unknown_risk_weight),
        }


# ---------------------------------------------------------------------------
# Contract entities (IDL, config, database)
# ---------------------------------------------------------------------------

_OPENAPI_PATH = re.compile(r"^\s{2}(/[^:\s]*):\s*$", re.MULTILINE)
_PROTO_MESSAGE = re.compile(r"^\s*(message|service|enum)\s+(\w+)", re.MULTILINE)
_PROTO_RPC = re.compile(r"^\s*rpc\s+(\w+)\s*\(", re.MULTILINE)
_GRAPHQL_TYPE = re.compile(r"^\s*(type|input|interface|enum|union|scalar)\s+(\w+)", re.MULTILINE)


def _contract_entities(path: str, text: str, repository_id: str) -> list[tuple[EntityKind, str, str, int]]:
    """(kind, name, qualified_name, line) for API/event contracts in a file."""

    found: list[tuple[EntityKind, str, str, int]] = []
    lowered = path.lower()
    if lowered.endswith(".proto"):
        for match in _PROTO_MESSAGE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            kind = EntityKind.EVENT_CONTRACT if match.group(1) == "message" else EntityKind.API_CONTRACT
            found.append((kind, match.group(2), f"{path}#{match.group(2)}", line))
        for match in _PROTO_RPC.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            found.append((EntityKind.API_CONTRACT, match.group(1), f"{path}#rpc:{match.group(1)}", line))
    elif lowered.endswith((".graphql", ".gql")):
        for match in _GRAPHQL_TYPE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            found.append((EntityKind.API_CONTRACT, match.group(2), f"{path}#{match.group(2)}", line))
    elif "openapi" in lowered or "swagger" in lowered:
        if lowered.endswith(".json"):
            try:
                document = json.loads(text)
            except json.JSONDecodeError:
                return found
            paths = document.get("paths") if isinstance(document, dict) else None
            if isinstance(paths, dict):
                for route, operations in paths.items():
                    if not isinstance(operations, dict):
                        continue
                    for method in operations:
                        if method.lower() in ("get", "put", "post", "delete", "patch", "head", "options"):
                            name = f"{method.upper()} {route}"
                            found.append((EntityKind.API_CONTRACT, name, f"{path}#{name}", 1))
        else:
            for match in _OPENAPI_PATH.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                found.append((EntityKind.API_CONTRACT, match.group(1), f"{path}#{match.group(1)}", line))
    return found


_CONFIG_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_.\-]*)\s*[:=]", re.MULTILINE)


def _config_keys(path: str, text: str, limit: int = 400) -> list[tuple[str, int]]:
    keys: list[tuple[str, int]] = []
    for match in _CONFIG_KEY.finditer(text):
        if len(keys) >= limit:
            break
        line = text.count("\n", 0, match.start()) + 1
        keys.append((match.group(1), line))
    return keys


# ---------------------------------------------------------------------------
# Index construction
# ---------------------------------------------------------------------------


def _entity_id(repository_id: str, kind: EntityKind, qualified_name: str, path: str, line: int) -> str:
    return sha256_payload(
        {"repo": repository_id, "kind": kind.value, "qname": qualified_name, "path": path, "line": line}
    )[:32]


def _index_contracts_and_config(
    path: str,
    text: str,
    language: str,
    labels: Sequence[str],
    repository_id: str,
    entities: list[SemanticEntity],
    by_qualified: dict[str, str],
    by_simple: dict[str, list[str]],
) -> None:
    """Index API/event contracts and configuration keys found in one file."""

    for kind, name, qualified, line in _contract_entities(path, text, repository_id):
        entity_id = _entity_id(repository_id, kind, qualified, path, line)
        entities.append(
            SemanticEntity(
                id=entity_id,
                kind=kind,
                language=language,
                name=name,
                repository_id=repository_id,
                path=path,
                span=SourceSpan(line, 0, line, 0),
                qualified_name=qualified,
                visibility="public",
                attributes={"contract": True},
                provenance_adapter="contract",
            )
        )
        by_qualified.setdefault(qualified, entity_id)
        by_simple[name].append(entity_id)

    if "configuration" not in labels:
        return
    for key, line in _config_keys(path, text):
        qualified = f"{path}#{key}"
        entity_id = _entity_id(repository_id, EntityKind.CONFIG_KEY, qualified, path, line)
        entities.append(
            SemanticEntity(
                id=entity_id,
                kind=EntityKind.CONFIG_KEY,
                language=language,
                name=key,
                repository_id=repository_id,
                path=path,
                span=SourceSpan(line, 0, line, len(key)),
                qualified_name=qualified,
                confidence=Decimal("0.7"),
                provenance_adapter="config",
            )
        )
        by_simple[key].append(entity_id)


def build_index(
    snapshot: WorkspaceSnapshot,
    inventory: RepositoryInventory,
    graph: BuildGraph,
    *,
    include_generated: bool = False,
    max_files: int = 100_000,
) -> SemanticIndex:
    """Index a snapshot into entities and relationships."""

    entities: list[SemanticEntity] = []
    relationships: list[SemanticRelationship] = []
    unknown: list[UnknownRegion] = []
    results: list[ExtractionResult] = []

    generated = set(inventory.generated_paths)
    vendored = set(inventory.vendored_paths)
    tests = set(inventory.test_paths)

    by_qualified: dict[str, str] = {}
    by_simple: dict[str, list[str]] = defaultdict(list)
    file_entity: dict[str, str] = {}

    considered = [record for record in snapshot if record.path not in vendored][:max_files]

    # -- pass 1: files and declarations ---------------------------------
    for record in considered:
        language = language_of(record.path)
        labels = classify_path(record.path)
        is_generated = record.path in generated
        kind = EntityKind.GENERATED_FILE if is_generated else EntityKind.SOURCE_FILE
        file_id = _entity_id(snapshot.repository_id, kind, record.path, record.path, 0)
        file_entity[record.path] = file_id
        entities.append(
            SemanticEntity(
                id=file_id,
                kind=kind,
                language=language,
                name=record.basename,
                repository_id=snapshot.repository_id,
                path=record.path,
                qualified_name=record.path,
                visibility="public",
                content_digest=record.content_digest,
                attributes={
                    "labels": list(labels),
                    "sizeBytes": record.size_bytes,
                    "buildTargets": list(graph.targets_for(record.path)),
                },
            )
        )

        if record.text is None:
            unknown.append(
                UnknownRegion(
                    path=record.path,
                    reason=record.unreadable_reason or "binary",
                    language=language,
                    detail="content unavailable: this file is not indexed and must not be treated as empty",
                )
            )
            continue
        if is_generated and not include_generated:
            unknown.append(
                UnknownRegion(
                    path=record.path,
                    reason="generated-excluded",
                    language=language,
                    detail="generated file skipped by policy; regenerate from its source of truth instead",
                )
            )
            continue
        # Contract and configuration extraction is independent of whether a
        # *code* extractor exists for the language: an OpenAPI document is a
        # contract whether or not anyone can parse YAML as a program.
        _index_contracts_and_config(
            record.path,
            record.text,
            language,
            labels,
            snapshot.repository_id,
            entities,
            by_qualified,
            by_simple,
        )

        if not supported(language):
            unknown.append(
                UnknownRegion(path=record.path, reason="no-extractor", language=language)
            )
            continue

        result = extract(record.path, record.text, language)
        results.append(result)
        if not result.parsed:
            unknown.append(
                UnknownRegion(
                    path=record.path,
                    reason="parse-failed",
                    language=language,
                    detail="; ".join(result.errors)[:400],
                )
            )
            continue

        for symbol in result.symbols:
            entity_id = _entity_id(
                snapshot.repository_id, symbol.kind, symbol.qualified_name, record.path, symbol.span.start_line
            )
            entities.append(
                SemanticEntity(
                    id=entity_id,
                    kind=EntityKind.TEST if record.path in tests and symbol.kind in (
                        EntityKind.FUNCTION,
                        EntityKind.METHOD,
                    ) else symbol.kind,
                    language=language,
                    name=symbol.name,
                    repository_id=snapshot.repository_id,
                    path=record.path,
                    span=symbol.span,
                    qualified_name=symbol.qualified_name,
                    signature=symbol.signature,
                    visibility=symbol.visibility,
                    confidence=symbol.confidence,
                    attributes=dict(symbol.attributes),
                    provenance_adapter=result.engine,
                )
            )
            by_qualified.setdefault(symbol.qualified_name, entity_id)
            by_simple[symbol.name].append(entity_id)
            relationships.append(
                SemanticRelationship(
                    id=f"{file_id}:declares:{entity_id}",
                    type=RelationshipType.DECLARES,
                    from_id=file_id,
                    to_id=entity_id,
                    repository_id=snapshot.repository_id,
                    path=record.path,
                    span=symbol.span,
                )
            )

    # -- pass 2: references ----------------------------------------------
    resolvable = 0
    resolved = 0
    for result in results:
        owning_file_id = file_entity.get(result.path)
        if owning_file_id is None:
            continue
        for index, reference in enumerate(result.references):
            resolvable += 1
            source_id: str = by_qualified.get(reference.from_symbol, owning_file_id)
            target_id: str | None = by_qualified.get(reference.name)
            confidence = reference.confidence
            attributes: dict[str, Any] = {}
            if reference.dynamic:
                attributes["dynamic"] = True
                attributes["detail"] = reference.detail
                attributes["dynamicScope"] = reference.dynamic_scope or "module"
            if target_id is None:
                candidates = by_simple.get(reference.name.rsplit(".", 1)[-1], [])
                if len(candidates) == 1:
                    target_id = candidates[0]
                    confidence = min(confidence, Decimal("0.7"))
                    attributes["resolvedBy"] = "unique-simple-name"
                elif candidates:
                    target_id = candidates[0]
                    confidence = min(confidence, Decimal("0.3"))
                    attributes["resolvedBy"] = "ambiguous-simple-name"
                    attributes["candidates"] = len(candidates)
            if target_id is None:
                # External or unresolved: recorded as an edge to a synthetic
                # external node so it stays visible instead of disappearing.
                external_id = f"external:{reference.name}"
                attributes["external"] = True
                relationships.append(
                    SemanticRelationship(
                        id=f"{result.path}:{index}",
                        type=reference.type,
                        from_id=source_id,
                        to_id=external_id,
                        confidence=min(confidence, Decimal("0.5")),
                        repository_id=snapshot.repository_id,
                        path=result.path,
                        span=reference.span,
                        attributes=attributes,
                    )
                )
                continue
            resolved += 1
            relationships.append(
                SemanticRelationship(
                    id=f"{result.path}:{index}",
                    type=reference.type,
                    from_id=source_id,
                    to_id=target_id,
                    confidence=confidence,
                    repository_id=snapshot.repository_id,
                    path=result.path,
                    span=reference.span,
                    attributes=attributes,
                )
            )

    # -- pass 3: build and test links ------------------------------------
    target_entities: dict[str, str] = {}
    for target in graph.targets:
        entity_id = _entity_id(
            snapshot.repository_id, EntityKind.BUILD_TARGET, target.target_id, target.definition_path, 0
        )
        target_entities[target.target_id] = entity_id
        entities.append(
            SemanticEntity(
                id=entity_id,
                kind=EntityKind.BUILD_TARGET,
                language=target.language,
                name=target.target_id,
                repository_id=snapshot.repository_id,
                path=target.definition_path,
                qualified_name=target.target_id,
                visibility="public",
                attributes={"buildSystem": target.build_system, "kind": target.kind},
                provenance_adapter="buildgraph",
            )
        )
    for path, target_ids in graph.file_to_targets.items():
        built_file_id = file_entity.get(path)
        if built_file_id is None:
            continue
        for built_target in target_ids:
            build_entity_id = target_entities.get(built_target)
            if build_entity_id is None:
                continue
            relationships.append(
                SemanticRelationship(
                    id=f"{build_entity_id}:builds:{built_file_id}",
                    type=RelationshipType.BUILDS,
                    from_id=build_entity_id,
                    to_id=built_file_id,
                    repository_id=snapshot.repository_id,
                    path=path,
                )
            )
    for tested_target, test_ids in graph.target_to_tests.items():
        tested_entity_id = target_entities.get(tested_target)
        for test_target in test_ids:
            test_entity_id = target_entities.get(test_target)
            if tested_entity_id and test_entity_id:
                relationships.append(
                    SemanticRelationship(
                        id=f"{test_entity_id}:tests:{tested_entity_id}",
                        type=RelationshipType.TESTS,
                        from_id=test_entity_id,
                        to_id=tested_entity_id,
                        repository_id=snapshot.repository_id,
                    )
                )
    for path, owners in inventory.ownership.items():
        owned_file_id = file_entity.get(path)
        if owned_file_id is None:
            continue
        for owner in owners:
            relationships.append(
                SemanticRelationship(
                    id=f"owner:{owner}:{owned_file_id}",
                    type=RelationshipType.OWNS,
                    from_id=f"owner:{owner}",
                    to_id=owned_file_id,
                    repository_id=snapshot.repository_id,
                    path=path,
                )
            )

    coverage = _coverage(
        results=results,
        considered=len(considered),
        resolvable=resolvable,
        resolved=resolved,
        graph=graph,
        unknown=unknown,
    )

    return SemanticIndex(
        snapshot_id=f"{snapshot.repository_id}@{snapshot.revision[:12]}",
        repository_id=snapshot.repository_id,
        revision=snapshot.revision,
        tree_digest=snapshot.tree_digest,
        entities=tuple(entities),
        relationships=tuple(relationships),
        coverage=coverage,
        unknown_regions=tuple(sorted(unknown, key=lambda item: item.path)),
        adapter_digests=(sha256_payload({"engine": "native", "irVersion": IR_VERSION}),),
    )


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return _ZERO
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))


def _coverage(
    *,
    results: Sequence[ExtractionResult],
    considered: int,
    resolvable: int,
    resolved: int,
    graph: BuildGraph,
    unknown: Sequence[UnknownRegion],
) -> CoverageMetrics:
    parsed = [item for item in results if item.parsed]
    compiler_tier = [item for item in parsed if item.engine == "compiler"]
    dynamic_files = [item for item in parsed if item.dynamic_markers]

    resolution = _ratio(resolved, resolvable)
    type_attribution = _ratio(len(compiler_tier), max(considered, 1))
    build_coverage = Decimal(str(round(graph.coverage, 4)))
    linked_targets = len(graph.target_to_tests)
    testable_targets = sum(1 for target in graph.targets if not target.is_test)
    test_link = _ratio(linked_targets, max(testable_targets, 1))

    #: Unknown risk is deliberately additive and capped at 1.  Each term is a
    #: distinct way the index can be wrong, and they compound rather than
    #: cancel: unparsed files hide symbols, dynamic references hide edges, and
    #: unmapped build files hide tests.
    unparsed_share = _ratio(len(unknown), max(considered, 1))
    dynamic_share = _ratio(len(dynamic_files), max(len(parsed), 1))
    unmapped_share = _ratio(len(graph.unmapped_files), max(considered, 1))
    syntactic_share = _ratio(len(parsed) - len(compiler_tier), max(len(parsed), 1))
    weight = (
        unparsed_share * Decimal("0.4")
        + dynamic_share * Decimal("0.3")
        + unmapped_share * Decimal("0.15")
        + syntactic_share * Decimal("0.15")
    )
    return CoverageMetrics(
        resolution=resolution,
        type_attribution=type_attribution,
        build_graph=build_coverage,
        test_link=test_link,
        unknown_risk_weight=min(_ONE, weight).quantize(Decimal("0.0001")),
        parsed_files=len(parsed),
        total_files=considered,
        dynamic_files=len(dynamic_files),
    )


def incremental_update(
    previous: SemanticIndex,
    snapshot: WorkspaceSnapshot,
    inventory: RepositoryInventory,
    graph: BuildGraph,
    changed_paths: Sequence[str],
) -> SemanticIndex:
    """Re-index only ``changed_paths``, keeping everything else intact.

    The result is compared against a full rebuild in the test-suite; the two
    must agree, because an incremental index that drifts from a full one is
    worse than no incremental index at all.
    """

    changed = set(changed_paths)
    if not changed:
        return previous
    subset = WorkspaceSnapshot(
        repository_id=snapshot.repository_id,
        revision=snapshot.revision,
        files={path: record for path, record in snapshot.files.items() if path in changed},
        excluded_paths=snapshot.excluded_paths,
        truncated=snapshot.truncated,
        filters_applied=snapshot.filters_applied,
    )
    fresh = build_index(subset, inventory, graph)
    kept_entities = tuple(entity for entity in previous.entities if entity.path not in changed)
    kept_ids = {entity.id for entity in kept_entities}
    kept_relationships = tuple(
        item
        for item in previous.relationships
        if item.path not in changed and (item.from_id in kept_ids or item.from_id.startswith(("external:", "owner:")))
    )
    merged_entities = {entity.id: entity for entity in (*kept_entities, *fresh.entities)}
    merged_relationships = {item.id: item for item in (*kept_relationships, *fresh.relationships)}
    return SemanticIndex(
        snapshot_id=f"{snapshot.repository_id}@{snapshot.revision[:12]}",
        repository_id=snapshot.repository_id,
        revision=snapshot.revision,
        tree_digest=snapshot.tree_digest,
        entities=tuple(sorted(merged_entities.values(), key=lambda item: item.id)),
        relationships=tuple(sorted(merged_relationships.values(), key=lambda item: item.id)),
        coverage=fresh.coverage,
        unknown_regions=tuple(
            sorted(
                {
                    region.path: region
                    for region in (
                        *(item for item in previous.unknown_regions if item.path not in changed),
                        *fresh.unknown_regions,
                    )
                }.values(),
                key=lambda item: item.path,
            )
        ),
        adapter_digests=previous.adapter_digests,
    )


__all__ = [
    "API_VERSION",
    "IR_VERSION",
    "CoverageMetrics",
    "SemanticEntity",
    "SemanticIndex",
    "SemanticRelationship",
    "UnknownRegion",
    "build_index",
    "incremental_update",
]

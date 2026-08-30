"""Bounded repository prewalk and provenance-bearing semantic indexes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path, PurePosixPath
import stat
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .adapters import AdapterRegistry, AdapterRequest, AdapterResult
from .canonical import digest_bytes, digest_object, freeze_json, require_sha256_digest
from .registry import resolve_operation


_LANGUAGES = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".dart": "dart",
    ".go": "go",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".php": "php",
    ".py": "python",
    ".rs": "rust",
    ".sql": "sql",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
}
_DEFAULT_EXCLUDED_DIRECTORIES = frozenset(
    {".git", ".hg", ".svn", "node_modules", "target", "dist", "build"}
)
_EDGE_INDEX_KINDS = frozenset({"reference", "call", "type", "dataflow"})


@dataclass(frozen=True, slots=True)
class OperationSpec:
    capability: str
    owner: str
    method: str
    output_contract: str
    external_adapter: bool = False

    def __post_init__(self) -> None:
        resolved = resolve_operation(self.capability)
        if resolved.operation.canonical_owner != self.owner:
            raise ValueError("operation binding owner differs from the canonical registry")
        if not self.method.strip() or not self.output_contract.strip():
            raise ValueError("operation binding method and output contract are required")


@dataclass(frozen=True, slots=True)
class PrewalkLimits:
    max_files: int = 20_000
    max_total_bytes: int = 512 * 1024 * 1024
    max_file_bytes: int = 8 * 1024 * 1024
    max_depth: int = 40
    max_entries: int = 100_000

    def __post_init__(self) -> None:
        values = (
            self.max_files,
            self.max_total_bytes,
            self.max_file_bytes,
            self.max_depth,
            self.max_entries,
        )
        if any(value <= 0 for value in values):
            raise ValueError("all prewalk limits must be positive")
        if self.max_file_bytes > self.max_total_bytes:
            raise ValueError("max_file_bytes cannot exceed max_total_bytes")


@dataclass(frozen=True, slots=True)
class RepositoryFile:
    path: str
    digest: str
    size: int
    mode: int
    modified_ns: int
    language: str | None

    def __post_init__(self) -> None:
        _validate_relative_path(self.path)
        require_sha256_digest(self.digest)
        if self.size < 0 or self.modified_ns < 0:
            raise ValueError("repository file metadata cannot be negative")


@dataclass(frozen=True, slots=True)
class PrewalkSkip:
    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class RepositoryPrewalk:
    root: str
    snapshot_digest: str
    files: tuple[RepositoryFile, ...]
    skipped: tuple[PrewalkSkip, ...]
    complete: bool
    entries_seen: int
    bytes_hashed: int

    def __post_init__(self) -> None:
        require_sha256_digest(self.snapshot_digest)
        if len({item.path for item in self.files}) != len(self.files):
            raise ValueError("repository prewalk contains duplicate paths")

    def file(self, path: str) -> RepositoryFile | None:
        normalized = _validate_relative_path(path)
        return next((item for item in self.files if item.path == normalized), None)


@dataclass(frozen=True, slots=True)
class Provenance:
    source: str
    source_id: str
    evidence_digest: str
    tool_version: str

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.source_id.strip() or not self.tool_version.strip():
            raise ValueError("semantic provenance fields are required")
        require_sha256_digest(self.evidence_digest)


@dataclass(frozen=True, slots=True)
class SemanticNode:
    node_id: str
    kind: str
    name: str
    path: str
    symbol_identity: str | None
    confidence: float
    unknown: bool
    provenance: tuple[Provenance, ...]
    unknown_reason: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_relative_path(self.path)
        _validate_semantic_claim(
            self.node_id,
            self.kind,
            self.confidence,
            self.unknown,
            self.unknown_reason,
            self.provenance,
        )
        frozen = freeze_json(dict(self.attributes))
        if not isinstance(frozen, Mapping):
            raise ValueError("semantic node attributes must be a JSON object")
        object.__setattr__(self, "attributes", frozen)


@dataclass(frozen=True, slots=True)
class SemanticEdge:
    edge_id: str
    source_node: str
    target_node: str | None
    kind: str
    path: str
    confidence: float
    unknown: bool
    provenance: tuple[Provenance, ...]
    unknown_reason: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_relative_path(self.path)
        _validate_semantic_claim(
            self.edge_id,
            self.kind,
            self.confidence,
            self.unknown,
            self.unknown_reason,
            self.provenance,
        )
        if not self.source_node.strip():
            raise ValueError("semantic edge source_node is required")
        if not self.unknown and not self.target_node:
            raise ValueError("known semantic edge requires target_node")
        frozen = freeze_json(dict(self.attributes))
        if not isinstance(frozen, Mapping):
            raise ValueError("semantic edge attributes must be a JSON object")
        object.__setattr__(self, "attributes", frozen)


@dataclass(frozen=True, slots=True)
class SemanticShard:
    path: str
    source_digest: str
    nodes: tuple[SemanticNode, ...]
    edges: tuple[SemanticEdge, ...]
    dependencies: tuple[str, ...]
    shard_digest: str

    def __post_init__(self) -> None:
        normalized = _validate_relative_path(self.path)
        require_sha256_digest(self.source_digest)
        require_sha256_digest(self.shard_digest)
        if any(node.path != normalized for node in self.nodes):
            raise ValueError("semantic node escapes its shard path")
        if any(edge.path != normalized for edge in self.edges):
            raise ValueError("semantic edge escapes its shard path")
        if len({node.node_id for node in self.nodes}) != len(self.nodes):
            raise ValueError("semantic node identities must be unique per shard")
        if len({edge.edge_id for edge in self.edges}) != len(self.edges):
            raise ValueError("semantic edge identities must be unique per shard")
        for dependency in self.dependencies:
            _validate_relative_path(dependency)
        expected = digest_object(
            {
                "path": normalized,
                "source_digest": self.source_digest,
                "nodes": tuple(_node_wire(item) for item in self.nodes),
                "edges": tuple(_edge_wire(item) for item in self.edges),
                "dependencies": tuple(sorted(self.dependencies)),
            },
            domain="semantic-shard",
        )
        if self.shard_digest != expected:
            raise ValueError("semantic shard digest does not match its canonical contents")

    @property
    def has_unknowns(self) -> bool:
        return any(item.unknown for item in self.nodes) or any(
            item.unknown for item in self.edges
        )


@dataclass(frozen=True, slots=True)
class RepositorySemanticGraph:
    snapshot_digest: str
    graph_digest: str
    shards: tuple[SemanticShard, ...]
    invalidated_paths: tuple[str, ...]
    reused_paths: tuple[str, ...]
    complete: bool

    def __post_init__(self) -> None:
        require_sha256_digest(self.snapshot_digest)
        require_sha256_digest(self.graph_digest)
        if len({item.path for item in self.shards}) != len(self.shards):
            raise ValueError("semantic graph contains duplicate shards")

    def edges(self, kind: str) -> tuple[SemanticEdge, ...]:
        return tuple(
            edge
            for shard in self.shards
            for edge in shard.edges
            if edge.kind == kind
        )

    def uncertainty(self) -> tuple[SemanticNode | SemanticEdge, ...]:
        claims: list[SemanticNode | SemanticEdge] = []
        for shard in self.shards:
            claims.extend(
                item
                for item in shard.nodes
                if item.unknown or item.confidence < 1.0
            )
            claims.extend(
                item
                for item in shard.edges
                if item.unknown or item.confidence < 1.0
            )
        return tuple(claims)


class SemanticDiffStatus(str, Enum):
    EQUIVALENT = "EQUIVALENT"
    DIFFERENT = "DIFFERENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class SemanticGraphDiff:
    status: SemanticDiffStatus
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]
    residual_uncertainty: tuple[str, ...]
    diff_digest: str


class SemanticGraphBuilder:
    """Build immutable shards and invalidate reverse dependencies."""

    def build(
        self,
        prewalk: RepositoryPrewalk,
        supplied_shards: Mapping[str, SemanticShard],
        *,
        previous: RepositorySemanticGraph | None = None,
    ) -> RepositorySemanticGraph:
        current = {item.path: item for item in prewalk.files}
        supplied = {_validate_relative_path(key): value for key, value in supplied_shards.items()}
        if set(supplied) - set(current):
            raise ValueError("supplied semantic shards include paths outside the prewalk")
        invalidated = self.plan_invalidation(prewalk, previous)
        old = {item.path: item for item in previous.shards} if previous else {}
        shards: list[SemanticShard] = []
        reused: list[str] = []
        for path, file_record in sorted(current.items()):
            candidate = supplied.get(path)
            if candidate is not None:
                if candidate.path != path or candidate.source_digest != file_record.digest:
                    raise ValueError("semantic shard is stale or bound to the wrong path")
                shards.append(candidate)
            elif path in old and path not in invalidated:
                shards.append(old[path])
                reused.append(path)
            else:
                shards.append(_unknown_shard(file_record))
        node_ids = [node.node_id for shard in shards for node in shard.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("semantic node identities must be repository-global")
        node_identity_set = set(node_ids)
        for shard in shards:
            for edge in shard.edges:
                if edge.source_node not in node_identity_set:
                    raise ValueError("semantic edge source is unresolved")
                if not edge.unknown and edge.target_node not in node_identity_set:
                    raise ValueError(
                        "known semantic edge target is unresolved; mark it unknown explicitly"
                    )
        complete = (
            prewalk.complete
            and len(shards) == len(current)
            and all(not item.has_unknowns for item in shards)
        )
        graph_digest = digest_object(
            {
                "snapshot_digest": prewalk.snapshot_digest,
                "shards": tuple(item.shard_digest for item in shards),
                "invalidated_paths": tuple(sorted(invalidated)),
                "complete": complete,
            },
            domain="semantic-graph",
        )
        return RepositorySemanticGraph(
            snapshot_digest=prewalk.snapshot_digest,
            graph_digest=graph_digest,
            shards=tuple(shards),
            invalidated_paths=tuple(sorted(invalidated)),
            reused_paths=tuple(sorted(reused)),
            complete=complete,
        )

    @staticmethod
    def plan_invalidation(
        prewalk: RepositoryPrewalk,
        previous: RepositorySemanticGraph | None,
    ) -> set[str]:
        current = {item.path: item.digest for item in prewalk.files}
        if previous is None:
            return set(current)
        old = {item.path: item.source_digest for item in previous.shards}
        changed = {
            path
            for path in set(current) | set(old)
            if current.get(path) != old.get(path)
        }
        reverse: dict[str, set[str]] = {}
        for shard in previous.shards:
            for dependency in shard.dependencies:
                reverse.setdefault(dependency, set()).add(shard.path)
        queue = list(changed)
        invalidated = set(changed)
        while queue:
            dependency = queue.pop()
            for dependent in reverse.get(dependency, ()):
                if dependent not in invalidated:
                    invalidated.add(dependent)
                    queue.append(dependent)
        return invalidated


def make_semantic_shard(
    file_record: RepositoryFile,
    *,
    nodes: Sequence[SemanticNode],
    edges: Sequence[SemanticEdge],
    dependencies: Sequence[str] = (),
) -> SemanticShard:
    normalized_dependencies = tuple(sorted({_validate_relative_path(item) for item in dependencies}))
    body = {
        "path": file_record.path,
        "source_digest": file_record.digest,
        "nodes": tuple(_node_wire(item) for item in nodes),
        "edges": tuple(_edge_wire(item) for item in edges),
        "dependencies": normalized_dependencies,
    }
    return SemanticShard(
        path=file_record.path,
        source_digest=file_record.digest,
        nodes=tuple(nodes),
        edges=tuple(edges),
        dependencies=normalized_dependencies,
        shard_digest=digest_object(body, domain="semantic-shard"),
    )


def prewalk_repository(
    root: str | os.PathLike[str],
    *,
    limits: PrewalkLimits | None = None,
    excluded_directories: frozenset[str] = _DEFAULT_EXCLUDED_DIRECTORIES,
) -> RepositoryPrewalk:
    """Hash a bounded repository tree without following symbolic links."""

    limits = limits or PrewalkLimits()
    root_path = Path(root).absolute()
    root_stat = root_path.lstat()
    if stat.S_ISLNK(root_stat.st_mode):
        raise ValueError("repository root cannot be a symbolic link")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ValueError("repository root must be a directory")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    root_fd = os.open(root_path, os.O_RDONLY | os.O_DIRECTORY | nofollow)
    files: list[RepositoryFile] = []
    skipped: list[PrewalkSkip] = []
    entries_seen = 0
    bytes_hashed = 0
    complete = True
    stop = False

    def scan(directory_fd: int, prefix: str, depth: int) -> None:
        nonlocal entries_seen, bytes_hashed, complete, stop
        if stop:
            return
        with os.scandir(directory_fd) as iterator:
            entries = sorted(iterator, key=lambda item: item.name)
        for entry in entries:
            if stop:
                return
            entries_seen += 1
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            normalized = _validate_relative_path(relative)
            if entries_seen > limits.max_entries:
                skipped.append(PrewalkSkip(normalized, "max_entries exceeded"))
                complete = False
                stop = True
                return
            try:
                if entry.is_symlink():
                    skipped.append(PrewalkSkip(normalized, "symbolic link not followed"))
                    complete = False
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in excluded_directories:
                        skipped.append(PrewalkSkip(normalized, "excluded directory"))
                        continue
                    if depth >= limits.max_depth:
                        skipped.append(PrewalkSkip(normalized, "max_depth exceeded"))
                        complete = False
                        continue
                    child_fd = os.open(
                        entry.name,
                        os.O_RDONLY | os.O_DIRECTORY | nofollow,
                        dir_fd=directory_fd,
                    )
                    try:
                        scan(child_fd, normalized, depth + 1)
                    finally:
                        os.close(child_fd)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    skipped.append(PrewalkSkip(normalized, "not a regular file"))
                    continue
                if len(files) >= limits.max_files:
                    skipped.append(PrewalkSkip(normalized, "max_files exceeded"))
                    complete = False
                    stop = True
                    return
                file_fd = os.open(entry.name, os.O_RDONLY | nofollow, dir_fd=directory_fd)
                try:
                    metadata = os.fstat(file_fd)
                    if not stat.S_ISREG(metadata.st_mode):
                        skipped.append(PrewalkSkip(normalized, "not a regular file"))
                        continue
                    if metadata.st_size > limits.max_file_bytes:
                        skipped.append(PrewalkSkip(normalized, "max_file_bytes exceeded"))
                        complete = False
                        continue
                    if bytes_hashed + metadata.st_size > limits.max_total_bytes:
                        skipped.append(PrewalkSkip(normalized, "max_total_bytes exceeded"))
                        complete = False
                        stop = True
                        return
                    content = _read_bounded_fd(file_fd, metadata.st_size)
                finally:
                    os.close(file_fd)
                bytes_hashed += len(content)
                files.append(
                    RepositoryFile(
                        path=normalized,
                        digest=digest_bytes(content),
                        size=len(content),
                        mode=stat.S_IMODE(metadata.st_mode),
                        modified_ns=metadata.st_mtime_ns,
                        language=_LANGUAGES.get(PurePosixPath(normalized).suffix.lower()),
                    )
                )
            except FileNotFoundError:
                skipped.append(PrewalkSkip(normalized, "entry changed during prewalk"))
                complete = False
            except OSError as exc:
                skipped.append(PrewalkSkip(normalized, f"entry unavailable: {exc.errno}"))
                complete = False

    try:
        scan(root_fd, "", 0)
    finally:
        os.close(root_fd)
    ordered_files = tuple(sorted(files, key=lambda item: item.path))
    snapshot_digest = digest_object(
        {
            "files": tuple(
                (item.path, item.digest, item.size, item.mode) for item in ordered_files
            ),
            "complete": complete,
            "skipped": tuple((item.path, item.reason) for item in skipped),
        },
        domain="repository-prewalk",
    )
    return RepositoryPrewalk(
        root=str(root_path),
        snapshot_digest=snapshot_digest,
        files=ordered_files,
        skipped=tuple(skipped),
        complete=complete,
        entries_seen=entries_seen,
        bytes_hashed=bytes_hashed,
    )


def read_repository_bytes(
    root: str | os.PathLike[str],
    relative_path: str,
    *,
    max_bytes: int = 8 * 1024 * 1024,
) -> bytes:
    """Read a regular file beneath root through no-follow directory handles."""

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    normalized = _validate_relative_path(relative_path)
    components = PurePosixPath(normalized).parts
    root_path = Path(root).absolute()
    if stat.S_ISLNK(root_path.lstat().st_mode):
        raise ValueError("repository root cannot be a symbolic link")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(root_path, os.O_RDONLY | os.O_DIRECTORY | nofollow)
    try:
        for component in components[:-1]:
            next_fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | nofollow,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(components[-1], os.O_RDONLY | nofollow, dir_fd=directory_fd)
        try:
            metadata = os.fstat(file_fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("repository path is not a regular file")
            if metadata.st_size > max_bytes:
                raise ValueError("repository file exceeds read limit")
            return _read_bounded_fd(file_fd, metadata.st_size)
        finally:
            os.close(file_fd)
    finally:
        os.close(directory_fd)


class SemanticRuntime:
    """Exact K1 operation router; unknown operations are rejected."""

    def __init__(self, adapters: AdapterRegistry | None = None) -> None:
        self.adapters = adapters or AdapterRegistry()
        self.builder = SemanticGraphBuilder()

    def execute(self, operation: str, **kwargs: Any) -> Any:
        spec = K1_OPERATION_SPECS.get(operation)
        if spec is None:
            raise KeyError(f"unknown K1 operation: {operation}")
        return getattr(self, spec.method)(**kwargs)

    def semantic_lsp_federation(
        self, request: AdapterRequest | None = None
    ) -> Mapping[str, Any] | AdapterResult:
        if request is None:
            return self.adapters.discovery("lsp")
        _require_protocol(request, "lsp")
        return self.adapters.invoke(request)

    def compiler_authority_router(self, request: AdapterRequest) -> AdapterResult:
        _require_protocol(request, "compiler")
        return self.adapters.invoke(request)

    def repository_semantic_graph(
        self,
        prewalk: RepositoryPrewalk,
        supplied_shards: Mapping[str, SemanticShard],
        previous: RepositorySemanticGraph | None = None,
    ) -> RepositorySemanticGraph:
        return self.builder.build(prewalk, supplied_shards, previous=previous)

    @staticmethod
    def semantic_reference_index(graph: RepositorySemanticGraph) -> tuple[SemanticEdge, ...]:
        return graph.edges("reference")

    @staticmethod
    def semantic_call_graph(graph: RepositorySemanticGraph) -> tuple[SemanticEdge, ...]:
        return graph.edges("call")

    @staticmethod
    def semantic_type_graph(graph: RepositorySemanticGraph) -> tuple[SemanticEdge, ...]:
        return graph.edges("type")

    @staticmethod
    def semantic_dataflow_index(graph: RepositorySemanticGraph) -> tuple[SemanticEdge, ...]:
        return graph.edges("dataflow")

    def framework_semantic_detector(self, request: AdapterRequest) -> AdapterResult:
        if request.protocol not in {"compiler", "lsp"}:
            raise ValueError("framework detection requires compiler or lsp protocol")
        return self.adapters.invoke(request)

    def ast_structural_query(self, request: AdapterRequest) -> AdapterResult:
        _require_protocol(request, "compiler")
        return self.adapters.invoke(request)

    @staticmethod
    def repository_prewalk_indexer(
        root: str | os.PathLike[str], limits: PrewalkLimits | None = None
    ) -> RepositoryPrewalk:
        return prewalk_repository(root, limits=limits)

    @staticmethod
    def cross_language_semantic_diff(
        source: RepositorySemanticGraph, target: RepositorySemanticGraph
    ) -> SemanticGraphDiff:
        return diff_semantic_graphs(source, target)

    @staticmethod
    def semantic_uncertainty_map(
        graph: RepositorySemanticGraph,
    ) -> tuple[SemanticNode | SemanticEdge, ...]:
        return graph.uncertainty()


def diff_semantic_graphs(
    source: RepositorySemanticGraph,
    target: RepositorySemanticGraph,
) -> SemanticGraphDiff:
    source_claims = _claim_index(source)
    target_claims = _claim_index(target)
    added = tuple(sorted(set(target_claims) - set(source_claims)))
    removed = tuple(sorted(set(source_claims) - set(target_claims)))
    changed = tuple(
        sorted(
            key
            for key in set(source_claims) & set(target_claims)
            if source_claims[key] != target_claims[key]
        )
    )
    residual = tuple(
        sorted(
            {
                item.node_id if isinstance(item, SemanticNode) else item.edge_id
                for item in (*source.uncertainty(), *target.uncertainty())
            }
        )
    )
    if not source.complete or not target.complete or residual:
        status = SemanticDiffStatus.INSUFFICIENT_EVIDENCE
    elif added or removed or changed:
        status = SemanticDiffStatus.DIFFERENT
    else:
        status = SemanticDiffStatus.EQUIVALENT
    digest = digest_object(
        {
            "source": source.graph_digest,
            "target": target.graph_digest,
            "status": status.value,
            "added": added,
            "removed": removed,
            "changed": changed,
            "residual_uncertainty": residual,
        },
        domain="semantic-diff",
    )
    return SemanticGraphDiff(status, added, removed, changed, residual, digest)


K1_OPERATION_SPECS: Mapping[str, OperationSpec] = MappingProxyType(
    {
        "semantic-lsp-federation": OperationSpec("semantic-lsp-federation", "K1", "semantic_lsp_federation", "AdapterResult", True),
        "compiler-authority-router": OperationSpec("compiler-authority-router", "K1", "compiler_authority_router", "AdapterResult", True),
        "repository-semantic-graph": OperationSpec("repository-semantic-graph", "K1", "repository_semantic_graph", "RepositorySemanticGraph"),
        "semantic-reference-index": OperationSpec("semantic-reference-index", "K1", "semantic_reference_index", "SemanticEdge[]"),
        "semantic-call-graph": OperationSpec("semantic-call-graph", "K1", "semantic_call_graph", "SemanticEdge[]"),
        "semantic-type-graph": OperationSpec("semantic-type-graph", "K1", "semantic_type_graph", "SemanticEdge[]"),
        "semantic-dataflow-index": OperationSpec("semantic-dataflow-index", "K1", "semantic_dataflow_index", "SemanticEdge[]"),
        "framework-semantic-detector": OperationSpec("framework-semantic-detector", "K1", "framework_semantic_detector", "AdapterResult", True),
        "ast-structural-query": OperationSpec("ast-structural-query", "K1", "ast_structural_query", "AdapterResult", True),
        "repository-prewalk-indexer": OperationSpec("repository-prewalk-indexer", "K1", "repository_prewalk_indexer", "RepositoryPrewalk"),
        "cross-language-semantic-diff": OperationSpec("cross-language-semantic-diff", "K1", "cross_language_semantic_diff", "SemanticGraphDiff"),
        "semantic-uncertainty-map": OperationSpec("semantic-uncertainty-map", "K1", "semantic_uncertainty_map", "SemanticClaim[]"),
    }
)


def _validate_relative_path(path: str) -> str:
    if not isinstance(path, str) or not path or "\x00" in path or "\\" in path:
        raise ValueError("repository path must be a non-empty POSIX relative path")
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("repository path traversal is forbidden")
    normalized = candidate.as_posix()
    if normalized != path:
        raise ValueError("repository path must already be normalized")
    return normalized


def _validate_semantic_claim(
    identity: str,
    kind: str,
    confidence: float,
    unknown: bool,
    unknown_reason: str | None,
    provenance: tuple[Provenance, ...],
) -> None:
    if not identity.strip() or not kind.strip():
        raise ValueError("semantic claim identity and kind are required")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("semantic confidence must be between zero and one")
    if not provenance:
        raise ValueError("semantic claims require provenance")
    if unknown and not unknown_reason:
        raise ValueError("unknown semantic claims require an explicit reason")
    if not unknown and unknown_reason is not None:
        raise ValueError("known semantic claims cannot have unknown_reason")


def _unknown_shard(file_record: RepositoryFile) -> SemanticShard:
    provenance = Provenance(
        source="repository-prewalk",
        source_id=file_record.path,
        evidence_digest=file_record.digest,
        tool_version="elmos-pdhi-prewalk-v1",
    )
    node = SemanticNode(
        node_id=f"file:{file_record.path}",
        kind="file",
        name=PurePosixPath(file_record.path).name,
        path=file_record.path,
        symbol_identity=None,
        confidence=0.0,
        unknown=True,
        provenance=(provenance,),
        unknown_reason="semantic adapter evidence unavailable",
        attributes={"language": file_record.language},
    )
    return make_semantic_shard(file_record, nodes=(node,), edges=())


def _node_wire(node: SemanticNode) -> Mapping[str, Any]:
    return {
        "node_id": node.node_id,
        "kind": node.kind,
        "name": node.name,
        "path": node.path,
        "symbol_identity": node.symbol_identity,
        "confidence": node.confidence,
        "unknown": node.unknown,
        "unknown_reason": node.unknown_reason,
        "provenance": tuple(_provenance_wire(item) for item in node.provenance),
        "attributes": dict(node.attributes),
    }


def _edge_wire(edge: SemanticEdge) -> Mapping[str, Any]:
    return {
        "edge_id": edge.edge_id,
        "source_node": edge.source_node,
        "target_node": edge.target_node,
        "kind": edge.kind,
        "path": edge.path,
        "confidence": edge.confidence,
        "unknown": edge.unknown,
        "unknown_reason": edge.unknown_reason,
        "provenance": tuple(_provenance_wire(item) for item in edge.provenance),
        "attributes": dict(edge.attributes),
    }


def _provenance_wire(provenance: Provenance) -> Mapping[str, str]:
    return {
        "source": provenance.source,
        "source_id": provenance.source_id,
        "evidence_digest": provenance.evidence_digest,
        "tool_version": provenance.tool_version,
    }


def _claim_index(graph: RepositorySemanticGraph) -> dict[str, str]:
    claims: dict[str, str] = {}
    for shard in graph.shards:
        for node in shard.nodes:
            claims[f"node:{node.node_id}"] = digest_object(
                _node_wire(node), domain="semantic-node"
            )
        for edge in shard.edges:
            claims[f"edge:{edge.edge_id}"] = digest_object(
                _edge_wire(edge), domain="semantic-edge"
            )
    return claims


def _read_bounded_fd(file_fd: int, expected_size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = expected_size
    while remaining:
        chunk = os.read(file_fd, min(remaining, 1024 * 1024))
        if not chunk:
            raise OSError("file changed while being read")
        chunks.append(chunk)
        remaining -= len(chunk)
    if os.read(file_fd, 1):
        raise OSError("file grew while being read")
    return b"".join(chunks)


def _require_protocol(request: AdapterRequest, expected: str) -> None:
    if request.protocol != expected:
        raise ValueError(f"operation requires {expected} adapter protocol")


if set(K1_OPERATION_SPECS) != {
    "semantic-lsp-federation",
    "compiler-authority-router",
    "repository-semantic-graph",
    "semantic-reference-index",
    "semantic-call-graph",
    "semantic-type-graph",
    "semantic-dataflow-index",
    "framework-semantic-detector",
    "ast-structural-query",
    "repository-prewalk-indexer",
    "cross-language-semantic-diff",
    "semantic-uncertainty-map",
}:
    raise RuntimeError("K1 operation bindings drifted from the source catalog")


__all__ = [
    "K1_OPERATION_SPECS",
    "OperationSpec",
    "PrewalkLimits",
    "PrewalkSkip",
    "Provenance",
    "RepositoryFile",
    "RepositoryPrewalk",
    "RepositorySemanticGraph",
    "SemanticDiffStatus",
    "SemanticEdge",
    "SemanticGraphBuilder",
    "SemanticGraphDiff",
    "SemanticNode",
    "SemanticRuntime",
    "SemanticShard",
    "diff_semantic_graphs",
    "make_semantic_shard",
    "prewalk_repository",
    "read_repository_bytes",
]

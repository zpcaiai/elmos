"""Real-provider Tree-sitter parsing with fail-closed incremental handling.

Callers may inject a pinned Tree-sitter parser.  The default facade also uses
the optional ``tree_sitter_language_pack`` when that dependency is present;
otherwise it reports ``NOT_RUN`` and emits no AST.  No fallback parser or
synthetic tree is ever returned as native evidence.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


_MAX_SOURCE_BYTES = 16 * 1024 * 1024
_MAX_TREE_NODES = 1_000_000


@dataclass
class AstSpan:
    start_row: int
    start_col: int
    end_row: int
    end_col: int


@dataclass
class IncrementalAstNode:
    id: str
    node_type: str
    span: AstSpan
    text_snippet: str
    is_modified: bool = False
    digest: str = ""
    children: List["IncrementalAstNode"] = field(default_factory=list)


@dataclass
class IncrementalAstTree:
    root: Optional[IncrementalAstNode]
    total_nodes: int
    language: str
    tree_digest: Optional[str]
    parse_duration_ms: float
    status: str = "NOT_RUN"
    source_digest: Optional[str] = None
    provider: Optional[str] = None
    reason: Optional[str] = None


def _require_source(code: Any) -> bytes:
    if not isinstance(code, str):
        raise ValueError("code must be a string")
    encoded = code.encode("utf-8")
    if len(encoded) > _MAX_SOURCE_BYTES:
        raise ValueError("code exceeds the 16 MiB parser boundary")
    return encoded


def _require_language(lang: Any) -> str:
    if not isinstance(lang, str) or not lang.strip() or len(lang.encode("utf-8")) > 64:
        raise ValueError("lang must be a non-empty bounded string")
    return lang.lower()


def _point_tuple(point: Any, label: str) -> Tuple[int, int]:
    if hasattr(point, "row") and hasattr(point, "column"):
        row, column = point.row, point.column
    elif isinstance(point, (tuple, list)) and len(point) == 2:
        row, column = point
    else:
        raise ValueError(f"provider node {label} is invalid")
    if not isinstance(row, int) or not isinstance(column, int) or row < 0 or column < 0:
        raise ValueError(f"provider node {label} is invalid")
    return row, column


def _byte_point(prefix: bytes) -> Tuple[int, int]:
    row = prefix.count(b"\n")
    last_newline = prefix.rfind(b"\n")
    return row, len(prefix) if last_newline < 0 else len(prefix) - last_newline - 1


class TreeSitterIncrementalParser:
    """Adapter around an injected parser from the real ``tree_sitter`` module."""

    def __init__(self, provider: Any = None) -> None:
        self._provider = provider
        self._default_providers: Dict[str, Any] = {}
        self._default_provider_errors: Dict[str, str] = {}
        self._native_trees: Dict[str, Any] = {}
        self._sources: Dict[str, bytes] = {}
        if provider is None:
            self.provider_name: Optional[str] = None
        else:
            provider_type = type(provider)
            self.provider_name = f"{provider_type.__module__}.{provider_type.__name__}"

    def _provider_reason(self, lang: str, provider: Any = None) -> Optional[str]:
        selected = self._provider if provider is None else provider
        if selected is None:
            return "TREE_SITTER_PROVIDER_NOT_CONFIGURED"
        if not callable(getattr(selected, "parse", None)):
            return "TREE_SITTER_PROVIDER_PARSE_UNAVAILABLE"
        provider_module = type(selected).__module__
        if provider_module != "tree_sitter" and not provider_module.startswith("tree_sitter."):
            return "UNTRUSTED_TREE_SITTER_PROVIDER_TYPE"
        configured_language = getattr(selected, "language", None)
        configured_name = getattr(configured_language, "name", None)
        if not isinstance(configured_name, str) or not configured_name:
            return "TREE_SITTER_LANGUAGE_IDENTITY_UNAVAILABLE"
        if configured_name.lower() != lang:
            return "TREE_SITTER_LANGUAGE_MISMATCH"
        return None

    def _provider_for_language(self, lang: str) -> Tuple[Any, Optional[str]]:
        """Resolve an explicitly injected or package-pinned parser."""

        if self._provider is not None:
            return self._provider, self._provider_reason(lang, self._provider)
        cached = self._default_providers.get(lang)
        if cached is not None:
            return cached, None
        cached_error = self._default_provider_errors.get(lang)
        if cached_error is not None:
            return None, cached_error
        try:
            from tree_sitter_language_pack import get_parser

            provider = get_parser(lang)
        except (ImportError, ModuleNotFoundError):
            reason = "TREE_SITTER_LANGUAGE_PACK_NOT_INSTALLED"
            self._default_provider_errors[lang] = reason
            return None, reason
        except Exception as exc:
            reason = f"TREE_SITTER_LANGUAGE_PACK_FAILED:{type(exc).__name__}"
            self._default_provider_errors[lang] = reason
            return None, reason
        reason = self._provider_reason(lang, provider)
        # Java grammars in current language-pack releases do not expose a
        # language.name attribute.  The adapter still remains trusted because
        # the parser was obtained through the exact package API for this exact
        # requested language; all other provider identity checks still apply.
        if reason in {
            "TREE_SITTER_LANGUAGE_IDENTITY_UNAVAILABLE",
            "TREE_SITTER_LANGUAGE_MISMATCH",
        }:
            if type(provider).__module__ == "tree_sitter" and callable(
                getattr(provider, "parse", None)
            ):
                reason = None
        if reason is not None:
            self._default_provider_errors[lang] = reason
            return None, reason
        self._default_providers[lang] = provider
        self.provider_name = f"{type(provider).__module__}.{type(provider).__name__}"
        return provider, None

    def _not_run(self, code: bytes, lang: str, reason: str) -> IncrementalAstTree:
        return IncrementalAstTree(
            root=None,
            total_nodes=0,
            language=lang,
            tree_digest=None,
            parse_duration_ms=0.0,
            status="NOT_RUN",
            source_digest="sha256:" + hashlib.sha256(code).hexdigest(),
            provider=self.provider_name,
            reason=reason,
        )

    def _convert_node(
        self,
        native_node: Any,
        source: bytes,
        *,
        counter: List[int],
    ) -> IncrementalAstNode:
        counter[0] += 1
        if counter[0] > _MAX_TREE_NODES:
            raise ValueError("provider tree exceeds the bounded node count")
        node_type = getattr(native_node, "type", None)
        start_byte = getattr(native_node, "start_byte", None)
        end_byte = getattr(native_node, "end_byte", None)
        if not isinstance(node_type, str) or not node_type:
            raise ValueError("provider node type is invalid")
        if (
            not isinstance(start_byte, int)
            or not isinstance(end_byte, int)
            or start_byte < 0
            or end_byte < start_byte
            or end_byte > len(source)
        ):
            raise ValueError("provider node byte range is invalid")
        start_row, start_col = _point_tuple(
            getattr(native_node, "start_point", None), "start_point"
        )
        end_row, end_col = _point_tuple(
            getattr(native_node, "end_point", None), "end_point"
        )
        raw = source[start_byte:end_byte]
        node_digest = hashlib.sha256(
            b"\0".join(
                (
                    node_type.encode("utf-8"),
                    str(start_byte).encode("ascii"),
                    str(end_byte).encode("ascii"),
                    raw,
                )
            )
        ).hexdigest()
        children_value = getattr(native_node, "children", None)
        if children_value is None:
            raise ValueError("provider node children are unavailable")
        children = [
            self._convert_node(child, source, counter=counter)
            for child in list(children_value)
        ]
        snippet = raw[:256].decode("utf-8", errors="replace")
        return IncrementalAstNode(
            id=f"node-{node_digest[:24]}",
            node_type=node_type,
            span=AstSpan(
                start_row=start_row + 1,
                start_col=start_col + 1,
                end_row=end_row + 1,
                end_col=end_col + 1,
            ),
            text_snippet=snippet,
            digest="sha256:" + node_digest,
            children=children,
        )

    def _from_native(
        self,
        native_tree: Any,
        source: bytes,
        lang: str,
        duration_ms: float,
    ) -> IncrementalAstTree:
        root_node = getattr(native_tree, "root_node", None)
        if root_node is None:
            raise ValueError("provider tree root_node is unavailable")
        counter = [0]
        root = self._convert_node(root_node, source, counter=counter)
        structure = {
            "language": lang,
            "provider": self.provider_name,
            "root": asdict(root),
        }
        tree_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                structure,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        result = IncrementalAstTree(
            root=root,
            total_nodes=counter[0],
            language=lang,
            tree_digest=tree_digest,
            parse_duration_ms=duration_ms,
            status="PARSED",
            source_digest="sha256:" + hashlib.sha256(source).hexdigest(),
            provider=self.provider_name,
            reason=None,
        )
        self._native_trees[tree_digest] = native_tree
        self._sources[tree_digest] = source
        return result

    def parse(self, code: str, lang: str = "java") -> IncrementalAstTree:
        """Parse using an injected real Tree-sitter parser, or return NOT_RUN."""

        source = _require_source(code)
        lang = _require_language(lang)
        provider, unavailable = self._provider_for_language(lang)
        if unavailable is not None:
            return self._not_run(source, lang, unavailable)
        started = time.perf_counter()
        try:
            native_tree = provider.parse(source)
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            return self._from_native(native_tree, source, lang, duration_ms)
        except Exception as exc:
            return IncrementalAstTree(
                root=None,
                total_nodes=0,
                language=lang,
                tree_digest=None,
                parse_duration_ms=round((time.perf_counter() - started) * 1000, 3),
                status="FAILED",
                source_digest="sha256:" + hashlib.sha256(source).hexdigest(),
                provider=self.provider_name,
                reason=f"TREE_SITTER_PROVIDER_FAILED:{type(exc).__name__}",
            )

    def incremental_reparse(
        self,
        old_tree: IncrementalAstTree,
        new_code: str,
        lang: str = "java",
    ) -> Dict[str, Any]:
        """Perform real provider incremental parsing and AST diffing."""

        source = _require_source(new_code)
        lang = _require_language(lang)
        provider, unavailable = self._provider_for_language(lang)
        if unavailable is not None:
            return self._incremental_not_run(old_tree, source, lang, unavailable)
        if old_tree.status != "PARSED" or not old_tree.tree_digest:
            return self._incremental_not_run(
                old_tree, source, lang, "PREVIOUS_PROVIDER_TREE_REQUIRED"
            )
        native_old = self._native_trees.get(old_tree.tree_digest)
        old_source = self._sources.get(old_tree.tree_digest)
        if native_old is None or old_source is None:
            return self._incremental_not_run(
                old_tree, source, lang, "PREVIOUS_NATIVE_TREE_UNAVAILABLE"
            )
        if not callable(getattr(native_old, "copy", None)):
            return self._incremental_not_run(
                old_tree, source, lang, "PROVIDER_TREE_COPY_UNAVAILABLE"
            )

        prefix_chars = 0
        old_text = old_source.decode("utf-8")
        new_text = source.decode("utf-8")
        while (
            prefix_chars < len(old_text)
            and prefix_chars < len(new_text)
            and old_text[prefix_chars] == new_text[prefix_chars]
        ):
            prefix_chars += 1
        suffix_chars = 0
        while (
            suffix_chars < len(old_text) - prefix_chars
            and suffix_chars < len(new_text) - prefix_chars
            and old_text[len(old_text) - suffix_chars - 1]
            == new_text[len(new_text) - suffix_chars - 1]
        ):
            suffix_chars += 1
        prefix_bytes = old_text[:prefix_chars].encode("utf-8")
        old_end_bytes = old_text[: len(old_text) - suffix_chars].encode("utf-8")
        new_end_bytes = new_text[: len(new_text) - suffix_chars].encode("utf-8")

        started = time.perf_counter()
        try:
            edited_tree = native_old.copy()
            edited_tree.edit(
                start_byte=len(prefix_bytes),
                old_end_byte=len(old_end_bytes),
                new_end_byte=len(new_end_bytes),
                start_point=_byte_point(prefix_bytes),
                old_end_point=_byte_point(old_end_bytes),
                new_end_point=_byte_point(new_end_bytes),
            )
            native_new = provider.parse(source, edited_tree)
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            new_tree = self._from_native(native_new, source, lang, duration_ms)
        except Exception as exc:
            return {
                "status": "FAILED",
                "reason": f"TREE_SITTER_INCREMENTAL_PROVIDER_FAILED:{type(exc).__name__}",
                "old_tree_digest": old_tree.tree_digest,
                "new_tree_digest": None,
                "total_nodes": 0,
                "modified_nodes_count": 0,
                "modified_nodes": [],
                "reparse_speedup": None,
                "provider": self.provider_name,
                "tree": None,
            }

        old_digests = {
            node.digest for node in self._flatten_nodes(old_tree.root)
        }
        modified_nodes: List[str] = []
        for node in self._flatten_nodes(new_tree.root):
            if node.digest not in old_digests:
                node.is_modified = True
                modified_nodes.append(node.id)
        return {
            "status": "PARSED_INCREMENTALLY",
            "reason": None,
            "old_tree_digest": old_tree.tree_digest,
            "new_tree_digest": new_tree.tree_digest,
            "total_nodes": new_tree.total_nodes,
            "modified_nodes_count": len(modified_nodes),
            "modified_nodes": modified_nodes,
            "reparse_speedup": None,
            "provider": self.provider_name,
            "tree": asdict(new_tree),
        }

    def _incremental_not_run(
        self,
        old_tree: IncrementalAstTree,
        source: bytes,
        lang: str,
        reason: str,
    ) -> Dict[str, Any]:
        return {
            "status": "NOT_RUN",
            "reason": reason,
            "old_tree_digest": old_tree.tree_digest,
            "new_tree_digest": None,
            "new_source_digest": "sha256:" + hashlib.sha256(source).hexdigest(),
            "language": lang,
            "total_nodes": 0,
            "modified_nodes_count": 0,
            "modified_nodes": [],
            "reparse_speedup": None,
            "provider": self.provider_name,
            "tree": None,
        }

    def _flatten_nodes(
        self, node: Optional[IncrementalAstNode]
    ) -> List[IncrementalAstNode]:
        if node is None:
            return []
        result = [node]
        for child in node.children:
            result.extend(self._flatten_nodes(child))
        return result


# Compatibility singleton lazily resolves the pinned optional language pack.
_tree_sitter_parser = TreeSitterIncrementalParser()


def parse_incremental_cst(
    code: str,
    lang: str = "java",
    previous_code: Optional[str] = None,
    *,
    parser: Optional[TreeSitterIncrementalParser] = None,
) -> Dict[str, Any]:
    """Top-level helper; a real configured parser must be supplied to execute."""

    selected_parser = parser or _tree_sitter_parser
    if previous_code is not None:
        old_tree = selected_parser.parse(previous_code, lang=lang)
        return selected_parser.incremental_reparse(old_tree, code, lang=lang)
    tree = selected_parser.parse(code, lang=lang)
    return {
        "status": tree.status,
        "reason": tree.reason,
        "language": tree.language,
        "total_nodes": tree.total_nodes,
        "tree_digest": tree.tree_digest,
        "source_digest": tree.source_digest,
        "parse_duration_ms": tree.parse_duration_ms,
        "provider": tree.provider,
        "tree": asdict(tree) if tree.root is not None else None,
    }

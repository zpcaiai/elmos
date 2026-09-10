"""Industrial Deep Call Graph Engine for Project Intelligence.

Constructs interprocedural call graphs across multiple languages (Python, JavaScript/TypeScript, Go).
Provides:
- Function/method definition cataloging with line ranges and parameters
- Call site extraction and callee resolution
- Recursion and cycle detection (Tarjan's strongly connected components)
- Path analysis (reachability, shortest call paths, blast radius)
- Unreachable/dead code identification
"""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Dict, List, Optional, Set, Tuple


@dataclass(frozen=True, slots=True)
class FunctionNode:
    qualified_name: str
    language: str
    file_path: str
    start_line: int
    end_line: int
    parameters: Tuple[str, ...]
    is_entrypoint: bool = False
    docstring: Optional[str] = None


@dataclass(frozen=True, slots=True)
class CallEdge:
    caller: str
    callee: str
    call_line: int
    file_path: str
    call_expression: str
    is_recursive: bool = False


@dataclass(frozen=True, slots=True)
class CallGraphSummary:
    total_functions: int
    total_calls: int
    cycles: Tuple[Tuple[str, ...], ...]
    entrypoints: Tuple[str, ...]
    dead_functions: Tuple[str, ...]
    graph_digest: str


class DeepCallGraphBuilder:
    """Builds and analyzes interprocedural call graphs."""

    def __init__(self) -> None:
        self.nodes: Dict[str, FunctionNode] = {}
        self.edges: List[CallEdge] = []
        self._adj: Dict[str, Set[str]] = defaultdict(set)
        self._rev_adj: Dict[str, Set[str]] = defaultdict(set)

    def add_source_file(self, file_path: str, source_code: str, language: Optional[str] = None) -> None:
        if language is None:
            if file_path.endswith(".py"):
                language = "python"
            elif file_path.endswith((".ts", ".tsx", ".js", ".jsx")):
                language = "javascript"
            elif file_path.endswith(".go"):
                language = "go"
            else:
                language = "generic"

        if language == "python":
            self._analyze_python(file_path, source_code)
        elif language in ("javascript", "typescript"):
            self._analyze_js_ts(file_path, source_code)
        elif language == "go":
            self._analyze_go(file_path, source_code)
        else:
            self._analyze_generic(file_path, source_code)

    def _analyze_python(self, file_path: str, source_code: str) -> None:
        try:
            tree = ast.parse(source_code, filename=file_path)
        except SyntaxError:
            return

        class FunctionVisitor(ast.NodeVisitor):
            def __init__(self, outer: DeepCallGraphBuilder) -> None:
                self.outer = outer
                self.current_scope: List[str] = []

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self._handle_func(node, is_async=False)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self._handle_func(node, is_async=True)

            def _handle_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> None:
                func_name = node.name
                scope_prefix = ".".join(self.current_scope)
                qname = f"{file_path}:{scope_prefix}.{func_name}" if scope_prefix else f"{file_path}:{func_name}"
                params = tuple(arg.arg for arg in node.args.args)
                is_entry = (
                    func_name.startswith("test_")
                    or func_name in ("main", "__main__", "handler", "entrypoint")
                    or any(
                        isinstance(d, ast.Name) and d.id in ("app", "router", "route", "entrypoint")
                        for d in node.decorator_list
                    )
                )
                docstring = ast.get_docstring(node)
                end_line = getattr(node, "end_lineno", node.lineno)

                f_node = FunctionNode(
                    qualified_name=qname,
                    language="python",
                    file_path=file_path,
                    start_line=node.lineno,
                    end_line=end_line,
                    parameters=params,
                    is_entrypoint=is_entry,
                    docstring=docstring,
                )
                self.outer.nodes[qname] = f_node

                prev_scope = list(self.current_scope)
                self.current_scope.append(func_name)

                # Extract calls inside this function
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and child is not node:
                        callee_name = self._resolve_call(child)
                        if callee_name:
                            callee_qname = f"{file_path}:{callee_name}"
                            edge = CallEdge(
                                caller=qname,
                                callee=callee_qname,
                                call_line=child.lineno,
                                file_path=file_path,
                                call_expression=ast.unparse(child.func) if hasattr(ast, "unparse") else callee_name,
                                is_recursive=(callee_name == func_name),
                            )
                            self.outer.edges.append(edge)
                            self.outer._adj[qname].add(callee_qname)
                            self.outer._rev_adj[callee_qname].add(qname)

                self.current_scope = prev_scope

            def _resolve_call(self, call_node: ast.Call) -> Optional[str]:
                if isinstance(call_node.func, ast.Name):
                    return call_node.func.id
                if isinstance(call_node.func, ast.Attribute):
                    return call_node.func.attr
                return None

        visitor = FunctionVisitor(self)
        visitor.visit(tree)

    def _analyze_js_ts(self, file_path: str, source_code: str) -> None:
        func_pat = re.compile(
            r"(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z0-9_$]+)\s*\(([^)]*)\)|"
            r"(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>|"
            r"([a-zA-Z0-9_$]+)\s*\(([^)]*)\)\s*\{"
        )
        lines = source_code.splitlines()
        for idx, line in enumerate(lines, 1):
            match = func_pat.search(line)
            if match:
                fname = match.group(1) or match.group(3) or match.group(5)
                raw_params = match.group(2) or match.group(4) or match.group(6) or ""
                if fname in ("if", "for", "while", "switch", "catch"):
                    continue
                params = tuple(p.strip().split(":")[0].strip() for p in raw_params.split(",") if p.strip())
                qname = f"{file_path}:{fname}"
                is_entry = fname in ("main", "handler", "default") or fname.startswith("test")
                self.nodes[qname] = FunctionNode(
                    qualified_name=qname,
                    language="javascript",
                    file_path=file_path,
                    start_line=idx,
                    end_line=idx,
                    parameters=params,
                    is_entrypoint=is_entry,
                )

        # Extract calls
        call_pat = re.compile(r"\b([a-zA-Z0-9_$]+)\s*\(")
        for idx, line in enumerate(lines, 1):
            for m in call_pat.finditer(line):
                callee = m.group(1)
                if callee in ("if", "for", "while", "switch", "catch", "function", "return"):
                    continue
                # Match to nearest caller
                caller_qname = self._find_enclosing_func(file_path, idx)
                if caller_qname:
                    callee_qname = f"{file_path}:{callee}"
                    edge = CallEdge(
                        caller=caller_qname,
                        callee=callee_qname,
                        call_line=idx,
                        file_path=file_path,
                        call_expression=f"{callee}()",
                        is_recursive=(callee_qname == caller_qname),
                    )
                    self.edges.append(edge)
                    self.adj_add(caller_qname, callee_qname)

    def _analyze_go(self, file_path: str, source_code: str) -> None:
        func_pat = re.compile(r"func\s+(?:\([^)]+\)\s+)?([a-zA-Z0-9_]+)\s*\(([^)]*)\)")
        lines = source_code.splitlines()
        for idx, line in enumerate(lines, 1):
            match = func_pat.search(line)
            if match:
                fname = match.group(1)
                raw_params = match.group(2)
                params = tuple(p.strip().split(" ")[0].strip() for p in raw_params.split(",") if p.strip())
                qname = f"{file_path}:{fname}"
                is_entry = fname in ("main", "init") or fname.startswith("Test") or fname.startswith("Benchmark")
                self.nodes[qname] = FunctionNode(
                    qualified_name=qname,
                    language="go",
                    file_path=file_path,
                    start_line=idx,
                    end_line=idx,
                    parameters=params,
                    is_entrypoint=is_entry,
                )

        call_pat = re.compile(r"\b([a-zA-Z0-9_]+)\s*\(")
        for idx, line in enumerate(lines, 1):
            for m in call_pat.finditer(line):
                callee = m.group(1)
                if callee in ("func", "if", "for", "switch", "select", "return", "go", "defer"):
                    continue
                caller_qname = self._find_enclosing_func(file_path, idx)
                if caller_qname:
                    callee_qname = f"{file_path}:{callee}"
                    edge = CallEdge(
                        caller=caller_qname,
                        callee=callee_qname,
                        call_line=idx,
                        file_path=file_path,
                        call_expression=f"{callee}()",
                        is_recursive=(callee_qname == caller_qname),
                    )
                    self.edges.append(edge)
                    self.adj_add(caller_qname, callee_qname)

    def _analyze_generic(self, file_path: str, source_code: str) -> None:
        pattern = re.compile(r"\bdef\s+([a-zA-Z0-9_]+)|\bfunction\s+([a-zA-Z0-9_]+)|\bfunc\s+([a-zA-Z0-9_]+)")
        for idx, line in enumerate(source_code.splitlines(), 1):
            match = pattern.search(line)
            if match:
                fname = match.group(1) or match.group(2) or match.group(3)
                qname = f"{file_path}:{fname}"
                self.nodes[qname] = FunctionNode(
                    qualified_name=qname,
                    language="generic",
                    file_path=file_path,
                    start_line=idx,
                    end_line=idx,
                    parameters=(),
                )

    def _find_enclosing_func(self, file_path: str, line_no: int) -> Optional[str]:
        candidates = [
            n for n in self.nodes.values()
            if n.file_path == file_path and n.start_line <= line_no <= (n.end_line or line_no)
        ]
        if candidates:
            candidates.sort(key=lambda n: n.start_line, reverse=True)
            return candidates[0].qualified_name
        return None

    def adj_add(self, caller: str, callee: str) -> None:
        self._adj[caller].add(callee)
        self._rev_adj[callee].add(caller)

    def find_cycles(self) -> List[List[str]]:
        """Find all strongly connected components with more than 1 node or self-loops using Tarjan's algorithm."""
        index = 0
        indices: Dict[str, int] = {}
        lowlink: Dict[str, int] = {}
        on_stack: Set[str] = set()
        stack: List[str] = []
        sccs: List[List[str]] = []

        all_nodes = set(self.nodes.keys()).union(self._adj.keys())

        def strongconnect(v: str) -> None:
            nonlocal index
            indices[v] = index
            lowlink[v] = index
            index += 1
            stack.append(v)
            on_stack.add(v)

            for w in self._adj.get(v, ()):
                if w not in indices:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], indices[w])

            if lowlink[v] == indices[v]:
                scc: List[str] = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == v:
                        break
                if len(scc) > 1 or (len(scc) == 1 and v in self._adj.get(v, ())):
                    sccs.append(scc)

        for node in all_nodes:
            if node not in indices:
                strongconnect(node)

        return sccs

    def get_reachable_nodes(self, start_node: str) -> Set[str]:
        """Compute all functions transitively reachable from a start node."""
        visited: Set[str] = set()
        queue: deque[str] = deque([start_node])
        while queue:
            curr = queue.popleft()
            if curr not in visited:
                visited.add(curr)
                for neighbor in self._adj.get(curr, ()):
                    if neighbor not in visited:
                        queue.append(neighbor)
        return visited

    def find_shortest_call_path(self, start_node: str, end_node: str) -> Optional[List[str]]:
        """Breadth-first search for the shortest invocation sequence."""
        if start_node == end_node:
            return [start_node]
        queue: deque[Tuple[str, List[str]]] = deque([(start_node, [start_node])])
        visited: Set[str] = {start_node}
        while queue:
            curr, path = queue.popleft()
            for neighbor in self._adj.get(curr, ()):
                if neighbor == end_node:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return None

    def find_dead_code(self) -> List[str]:
        """Functions with 0 callers that are not recognized entrypoints."""
        dead: List[str] = []
        for qname, node in self.nodes.items():
            if not node.is_entrypoint:
                callers = self._rev_adj.get(qname, set())
                # If only called by self (self-recursion) or no callers
                if not callers or callers == {qname}:
                    dead.append(qname)
        return sorted(dead)

    def summarize(self) -> CallGraphSummary:
        cycles = [tuple(sorted(c)) for c in self.find_cycles()]
        entrypoints = [k for k, v in self.nodes.items() if v.is_entrypoint]
        dead = self.find_dead_code()

        raw_fingerprint = {
            "functions": sorted(self.nodes.keys()),
            "edges": sorted([f"{e.caller}->{e.callee}@{e.call_line}" for e in self.edges]),
            "cycles": sorted(cycles),
        }
        digest = "sha256:" + hashlib.sha256(json.dumps(raw_fingerprint, sort_keys=True).encode("utf-8")).hexdigest()

        return CallGraphSummary(
            total_functions=len(self.nodes),
            total_calls=len(self.edges),
            cycles=tuple(cycles),
            entrypoints=tuple(sorted(entrypoints)),
            dead_functions=tuple(dead),
            graph_digest=digest,
        )


__all__ = [
    "CallEdge",
    "CallGraphSummary",
    "DeepCallGraphBuilder",
    "FunctionNode",
]

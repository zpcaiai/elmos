from __future__ import annotations

import ast
from hashlib import sha256
from pathlib import Path

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider, QualifiedNameProvider

from .domain import SemanticEdge, SemanticGraph, SemanticSymbol


class _CstCollector(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider, QualifiedNameProvider)

    def __init__(self, module_name: str) -> None:
        self.module_name = module_name
        self.symbols: list[SemanticSymbol] = []
        self.edges: list[SemanticEdge] = []
        self._scope: list[str] = []

    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        self._add_symbol(node, node.name.value, "CLASS")
        self._scope.append(node.name.value)

    def leave_ClassDef(self, original_node: cst.ClassDef) -> None:
        self._scope.pop()

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        kind = "ASYNC_FUNCTION" if node.asynchronous else "FUNCTION"
        self._add_symbol(node, node.name.value, kind)
        self._scope.append(node.name.value)

    def leave_FunctionDef(self, original_node: cst.FunctionDef) -> None:
        self._scope.pop()

    def visit_Import(self, node: cst.Import) -> None:
        for alias in node.names:
            self._add_edge(self._dotted(alias.name), "IMPORTS", node)

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        module = self._dotted(node.module) if node.module else ""
        self._add_edge(module or "RELATIVE_IMPORT", "IMPORTS", node)

    def visit_Call(self, node: cst.Call) -> None:
        target = self._expression(node.func)
        kind = "CALLS"
        if target in {"getattr", "setattr", "importlib.import_module", "__import__"}:
            kind = "CALLS_POTENTIALLY"
        self._add_edge(target or "UNRESOLVED_CALL", kind, node)

    def visit_Assign(self, node: cst.Assign) -> None:
        for target in node.targets:
            if isinstance(target.target, cst.Attribute):
                self._add_edge(self._expression(target.target), "MONKEY_PATCHES", node)

    def _add_symbol(self, node: cst.CSTNode, name: str, kind: str) -> None:
        position = self.get_metadata(PositionProvider, node)
        qualified = ".".join([self.module_name, *self._scope, name])
        symbol_id = sha256(f"{qualified}:{kind}:{position.start.line}".encode()).hexdigest()[:24]
        self.symbols.append(
            SemanticSymbol(
                symbol_id=symbol_id,
                module=self.module_name,
                qualified_name=qualified,
                kind=kind,
                line=position.start.line,
            )
        )

    def _add_edge(self, target: str, kind: str, node: cst.CSTNode) -> None:
        position = self.get_metadata(PositionProvider, node)
        source = ".".join([self.module_name, *self._scope])
        source_id = sha256(f"{source}:{position.start.line}".encode()).hexdigest()[:24]
        confidence = "LOW" if kind in {"CALLS_POTENTIALLY", "MONKEY_PATCHES"} else "HIGH"
        self.edges.append(SemanticEdge(source_id=source_id, target=target, kind=kind, confidence=confidence))

    @staticmethod
    def _dotted(node: cst.BaseExpression | None) -> str:
        if node is None:
            return ""
        if isinstance(node, cst.Name):
            return node.value
        if isinstance(node, cst.Attribute):
            prefix = _CstCollector._dotted(node.value)
            return f"{prefix}.{node.attr.value}" if prefix else node.attr.value
        return "DYNAMIC"

    @staticmethod
    def _expression(node: cst.BaseExpression) -> str:
        return _CstCollector._dotted(node)


class PythonSemanticGraphBuilder:
    def build(self, root: Path) -> SemanticGraph:
        symbols: list[SemanticSymbol] = []
        edges: list[SemanticEdge] = []
        parse_failures: list[str] = []
        generated: list[str] = []
        dynamic: set[str] = set()
        for path in sorted(root.rglob("*.py")):
            if path.is_symlink() or any(
                part in {".venv", "venv", "build", "dist", "__pycache__"} for part in path.parts
            ):
                continue
            relative = path.relative_to(root).as_posix()
            source = path.read_text(encoding="utf-8", errors="replace")
            if self._generated(source):
                generated.append(relative)
                continue
            try:
                ast.parse(source, filename=relative, feature_version=(3, 14))
            except SyntaxError as error:
                parse_failures.append(f"{relative}:{error.lineno}:{error.msg}")
                continue
            try:
                module = cst.parse_module(source)
                wrapper = MetadataWrapper(module)
                collector = _CstCollector(relative.removesuffix(".py").replace("/", "."))
                wrapper.visit(collector)
                symbols.extend(collector.symbols)
                edges.extend(collector.edges)
                if any(edge.kind in {"CALLS_POTENTIALLY", "MONKEY_PATCHES"} for edge in collector.edges):
                    dynamic.add(relative)
            except (cst.ParserSyntaxError, KeyError, TypeError) as error:
                parse_failures.append(f"{relative}:LIBCST:{type(error).__name__}")
        return SemanticGraph(
            cst_parser=f"LibCST {getattr(cst, '__version__', 'installed')}",
            ast_parser="CPython AST 3.14",
            symbols=sorted(symbols, key=lambda item: (item.module, item.line, item.qualified_name)),
            edges=sorted(edges, key=lambda item: (item.source_id, item.kind, item.target)),
            type_results=[
                {"tool": "MYPY", "status": "NOT_RUN_REQUIRES_SANDBOX"},
                {"tool": "PYRIGHT", "status": "NOT_RUN_REQUIRES_SANDBOX"},
            ],
            runtime_observations=[],
            dynamic_findings=[f"DYNAMIC_BEHAVIOR_REQUIRES_RUNTIME_TRACE:{item}" for item in sorted(dynamic)],
            parse_failures=parse_failures,
            generated_files=generated,
        )

    @staticmethod
    def _generated(source: str) -> bool:
        header = "\n".join(source.splitlines()[:5]).lower()
        return "generated" in header and ("do not edit" in header or "auto-generated" in header)

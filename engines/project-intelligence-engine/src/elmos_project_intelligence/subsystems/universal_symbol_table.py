"""Universal Hierarchical Lexical & AST Symbol Table for Multi-Language Analysis.

Provides:
- Hierarchical Lexical Scoping (Global -> Module -> Class -> Function -> Block)
- Lexical Shadowing & Resolution
- Definition & Reference Tracking (Read / Write occurrences)
- Full Python AST Symbol Extractor
- Exportable Cross-File Symbol Index with Merkle tree verification
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional, Set, Tuple


class SymbolKind(str, Enum):
    VARIABLE = "VARIABLE"
    CONSTANT = "CONSTANT"
    FUNCTION = "FUNCTION"
    METHOD = "METHOD"
    CLASS = "CLASS"
    INTERFACE = "INTERFACE"
    ENUM = "ENUM"
    TYPE_ALIAS = "TYPE_ALIAS"
    MODULE = "MODULE"
    IMPORT = "IMPORT"


class SymbolVisibility(str, Enum):
    PUBLIC = "PUBLIC"
    PROTECTED = "PROTECTED"
    PRIVATE = "PRIVATE"
    INTERNAL = "INTERNAL"


@dataclass
class SourceLocation:
    file_path: str
    start_line: int
    start_col: int
    end_line: int = 0
    end_col: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "start_col": self.start_col,
            "end_line": self.end_line,
            "end_col": self.end_col,
        }


@dataclass
class Symbol:
    symbol_id: str
    name: str
    kind: SymbolKind
    visibility: SymbolVisibility = SymbolVisibility.PUBLIC
    type_signature: Optional[str] = None
    location: Optional[SourceLocation] = None
    docstring: Optional[str] = None
    is_exported: bool = True
    read_references_count: int = 0
    write_references_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol_id": self.symbol_id,
            "name": self.name,
            "kind": self.kind.value,
            "visibility": self.visibility.value,
            "type_signature": self.type_signature,
            "location": self.location.to_dict() if self.location else None,
            "docstring": self.docstring,
            "is_exported": self.is_exported,
            "read_references_count": self.read_references_count,
            "write_references_count": self.write_references_count,
            "metadata": self.metadata,
        }


@dataclass
class Scope:
    scope_id: str
    name: str
    scope_type: str  # GLOBAL, MODULE, CLASS, FUNCTION, BLOCK
    parent_id: Optional[str] = None
    symbols: Dict[str, Symbol] = field(default_factory=dict)
    children: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope_id": self.scope_id,
            "name": self.name,
            "scope_type": self.scope_type,
            "parent_id": self.parent_id,
            "symbols": {k: v.to_dict() for k, v in self.symbols.items()},
            "children": self.children,
        }


class UniversalSymbolTable:
    """Manages hierarchical scopes and symbol resolution."""

    def __init__(self, workspace_root: str = "") -> None:
        self.workspace_root = workspace_root
        self.scopes: Dict[str, Scope] = {}
        self.current_scope_id: str = "scope_global"
        self._counter = 0

        # Initialize global scope
        global_scope = Scope(scope_id="scope_global", name="<global>", scope_type="GLOBAL")
        self.scopes["scope_global"] = global_scope

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{self._counter}"

    def enter_scope(self, name: str, scope_type: str) -> str:
        """Create or enter an existing child scope."""
        current = self.scopes[self.current_scope_id]
        for ch_id in current.children:
            if self.scopes[ch_id].name == name:
                self.current_scope_id = ch_id
                return ch_id

        scope_id = self._next_id("scope")
        new_scope = Scope(
            scope_id=scope_id,
            name=name,
            scope_type=scope_type,
            parent_id=self.current_scope_id,
        )
        self.scopes[self.current_scope_id].children.append(scope_id)
        self.scopes[scope_id] = new_scope
        self.current_scope_id = scope_id
        return scope_id

    def exit_scope(self) -> Optional[str]:
        """Exit current scope and return to parent scope."""
        current = self.scopes[self.current_scope_id]
        if current.parent_id:
            self.current_scope_id = current.parent_id
            return self.current_scope_id
        return None

    def define_symbol(
        self,
        name: str,
        kind: SymbolKind,
        visibility: SymbolVisibility = SymbolVisibility.PUBLIC,
        type_signature: Optional[str] = None,
        location: Optional[SourceLocation] = None,
        docstring: Optional[str] = None,
        is_exported: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Symbol:
        """Define a new symbol in the current scope."""
        symbol_id = self._next_id("sym")
        sym = Symbol(
            symbol_id=symbol_id,
            name=name,
            kind=kind,
            visibility=visibility,
            type_signature=type_signature,
            location=location,
            docstring=docstring,
            is_exported=is_exported,
            metadata=metadata or {},
        )
        self.scopes[self.current_scope_id].symbols[name] = sym
        return sym

    def lookup_symbol(self, name: str, current_scope_only: bool = False) -> Optional[Tuple[Symbol, str]]:
        """Look up a symbol by name, walking up parent scopes if not restricted to current."""
        curr_id: Optional[str] = self.current_scope_id
        while curr_id is not None:
            scope = self.scopes.get(curr_id)
            if scope and name in scope.symbols:
                return scope.symbols[name], curr_id
            if current_scope_only:
                break
            curr_id = scope.parent_id if scope else None
        return None

    def record_reference(self, name: str, is_write: bool = False) -> bool:
        """Record read or write access to a visible symbol."""
        res = self.lookup_symbol(name)
        if res:
            sym, _ = res
            if is_write:
                sym.write_references_count += 1
            else:
                sym.read_references_count += 1
            return True
        return False

    def extract_from_python_ast(self, filepath: str, source_code: str) -> None:
        """Extract symbols and scopes from Python source AST."""
        tree = ast.parse(source_code, filename=filepath)
        module_name = filepath.split("/")[-1].replace(".py", "")
        module_scope_id = self.enter_scope(module_name, "MODULE")

        class SymbolVisitor(ast.NodeVisitor):
            def __init__(self, table: UniversalSymbolTable, fpath: str) -> None:
                self.table = table
                self.fpath = fpath

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                vis = SymbolVisibility.PRIVATE if node.name.startswith("__") else SymbolVisibility.PUBLIC
                loc = SourceLocation(self.fpath, node.lineno, node.col_offset, node.end_lineno or 0, node.end_col_offset or 0)
                doc = ast.get_docstring(node)
                self.table.define_symbol(
                    name=node.name,
                    kind=SymbolKind.CLASS,
                    visibility=vis,
                    location=loc,
                    docstring=doc,
                    metadata={"bases": [ast.unparse(b) for b in node.bases]},
                )
                self.table.enter_scope(node.name, "CLASS")
                self.generic_visit(node)
                self.table.exit_scope()

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self._handle_func(node, is_async=False)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self._handle_func(node, is_async=True)

            def _handle_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> None:
                vis = SymbolVisibility.PRIVATE if node.name.startswith("__") else (
                    SymbolVisibility.PROTECTED if node.name.startswith("_") else SymbolVisibility.PUBLIC
                )
                loc = SourceLocation(self.fpath, node.lineno, node.col_offset, node.end_lineno or 0, node.end_col_offset or 0)
                doc = ast.get_docstring(node)
                ret_sig = ast.unparse(node.returns) if node.returns else "None"
                kind = SymbolKind.METHOD if self.table.scopes[self.table.current_scope_id].scope_type == "CLASS" else SymbolKind.FUNCTION

                self.table.define_symbol(
                    name=node.name,
                    kind=kind,
                    visibility=vis,
                    type_signature=f"-> {ret_sig}",
                    location=loc,
                    docstring=doc,
                    metadata={"is_async": is_async, "arg_count": len(node.args.args)},
                )
                self.table.enter_scope(node.name, "FUNCTION")

                # Define arguments as variables in function scope
                for arg in node.args.args:
                    arg_type = ast.unparse(arg.annotation) if arg.annotation else None
                    self.table.define_symbol(
                        name=arg.arg,
                        kind=SymbolKind.VARIABLE,
                        type_signature=arg_type,
                        location=SourceLocation(self.fpath, arg.lineno, arg.col_offset),
                    )

                self.generic_visit(node)
                self.table.exit_scope()

            def visit_Assign(self, node: ast.Assign) -> None:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        loc = SourceLocation(self.fpath, target.lineno, target.col_offset)
                        is_const = target.id.isupper()
                        kind = SymbolKind.CONSTANT if is_const else SymbolKind.VARIABLE
                        self.table.define_symbol(
                            name=target.id,
                            kind=kind,
                            location=loc,
                        )
                self.generic_visit(node)

            def visit_Import(self, node: ast.Import) -> None:
                for alias in node.names:
                    name = alias.asname or alias.name
                    loc = SourceLocation(self.fpath, node.lineno, node.col_offset)
                    self.table.define_symbol(
                        name=name,
                        kind=SymbolKind.IMPORT,
                        location=loc,
                        metadata={"source_module": alias.name},
                    )

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                mod = node.module or ""
                for alias in node.names:
                    name = alias.asname or alias.name
                    loc = SourceLocation(self.fpath, node.lineno, node.col_offset)
                    self.table.define_symbol(
                        name=name,
                        kind=SymbolKind.IMPORT,
                        location=loc,
                        metadata={"source_module": f"{mod}.{alias.name}"},
                    )

        visitor = SymbolVisitor(self, filepath)
        visitor.visit(tree)
        self.exit_scope()  # Exit MODULE scope

    def compute_merkle_digest(self) -> str:
        """Compute deterministic Merkle digest of the entire symbol table."""
        leaves: List[str] = []
        for scope_id in sorted(self.scopes.keys()):
            scope = self.scopes[scope_id]
            for sym_name in sorted(scope.symbols.keys()):
                sym = scope.symbols[sym_name]
                raw = f"{scope_id}:{sym.name}:{sym.kind.value}:{sym.visibility.value}:{sym.type_signature}"
                leaf_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                leaves.append(leaf_hash)

        if not leaves:
            return "sha256:" + hashlib.sha256(b"EMPTY_SYMBOL_TABLE").hexdigest()

        # Construct binary Merkle tree
        current_layer = leaves
        while len(current_layer) > 1:
            next_layer = []
            for i in range(0, len(current_layer), 2):
                left = current_layer[i]
                right = current_layer[i + 1] if i + 1 < len(current_layer) else left
                combined = hashlib.sha256((left + right).encode("utf-8")).hexdigest()
                next_layer.append(combined)
            current_layer = next_layer

        return "sha256:" + current_layer[0]

    def compute_ledger_merkle_root(self) -> str:
        """Compatibility alias for ledger Merkle root."""
        return self.compute_merkle_digest()

    def get_all_symbols(self) -> List[Symbol]:
        res: List[Symbol] = []
        for s in self.scopes.values():
            res.extend(s.symbols.values())
        return res

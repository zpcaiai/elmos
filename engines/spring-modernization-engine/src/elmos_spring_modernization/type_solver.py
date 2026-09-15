from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .java_ast import (
    JavaLexer,
    JavaASTParser,
    CompilationUnit,
    TypeDeclaration,
    MethodDeclaration,
    ImportDeclaration,
    TypeReference,
    SymbolResolutionContext,
)


@dataclass
class TypeSymbol:
    fqcn: str
    simple_name: str
    package_name: str
    kind: str = "class"  # class, interface, enum, record
    modifiers: List[str] = field(default_factory=list)
    super_class: Optional[str] = None
    interfaces: List[str] = field(default_factory=list)
    methods: Dict[str, List[str]] = field(default_factory=dict)  # method_name -> list of param types
    annotations: List[str] = field(default_factory=list)
    source_file: Optional[str] = None


class GlobalClasspathIndex:
    """
    Project-wide Classpath Symbol Index and Cross-Compilation-Unit Type Solver.
    Scans all Java sources across modules, builds an authoritative type hierarchy,
    and resolves same-package implicit symbols, wildcard imports, and inherited types.
    """

    # Built-in authoritative Spring, Jakarta, and JDK canonical symbols
    BUILTIN_ECOSYSTEM_SYMBOLS: Dict[str, TypeSymbol] = {
        "org.springframework.web.bind.annotation.RequestMapping": TypeSymbol(
            fqcn="org.springframework.web.bind.annotation.RequestMapping",
            simple_name="RequestMapping",
            package_name="org.springframework.web.bind.annotation",
            kind="interface"
        ),
        "org.springframework.web.bind.annotation.GetMapping": TypeSymbol(
            fqcn="org.springframework.web.bind.annotation.GetMapping",
            simple_name="GetMapping",
            package_name="org.springframework.web.bind.annotation",
            kind="interface"
        ),
        "org.springframework.web.bind.annotation.PostMapping": TypeSymbol(
            fqcn="org.springframework.web.bind.annotation.PostMapping",
            simple_name="PostMapping",
            package_name="org.springframework.web.bind.annotation",
            kind="interface"
        ),
        "org.springframework.web.bind.annotation.RestController": TypeSymbol(
            fqcn="org.springframework.web.bind.annotation.RestController",
            simple_name="RestController",
            package_name="org.springframework.web.bind.annotation",
            kind="interface"
        ),
        "org.springframework.stereotype.Service": TypeSymbol(
            fqcn="org.springframework.stereotype.Service",
            simple_name="Service",
            package_name="org.springframework.stereotype",
            kind="interface"
        ),
        "org.springframework.stereotype.Repository": TypeSymbol(
            fqcn="org.springframework.stereotype.Repository",
            simple_name="Repository",
            package_name="org.springframework.stereotype",
            kind="interface"
        ),
        "org.springframework.transaction.annotation.Transactional": TypeSymbol(
            fqcn="org.springframework.transaction.annotation.Transactional",
            simple_name="Transactional",
            package_name="org.springframework.transaction.annotation",
            kind="interface"
        ),
        "org.springframework.web.servlet.config.annotation.WebMvcConfigurer": TypeSymbol(
            fqcn="org.springframework.web.servlet.config.annotation.WebMvcConfigurer",
            simple_name="WebMvcConfigurer",
            package_name="org.springframework.web.servlet.config.annotation",
            kind="interface"
        ),
        "org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter": TypeSymbol(
            fqcn="org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter",
            simple_name="WebMvcConfigurerAdapter",
            package_name="org.springframework.web.servlet.config.annotation",
            kind="class"
        ),
        "jakarta.persistence.Entity": TypeSymbol(
            fqcn="jakarta.persistence.Entity",
            simple_name="Entity",
            package_name="jakarta.persistence",
            kind="interface"
        ),
        "jakarta.persistence.Table": TypeSymbol(
            fqcn="jakarta.persistence.Table",
            simple_name="Table",
            package_name="jakarta.persistence",
            kind="interface"
        ),
        "jakarta.persistence.Id": TypeSymbol(
            fqcn="jakarta.persistence.Id",
            simple_name="Id",
            package_name="jakarta.persistence",
            kind="interface"
        ),
    }

    def __init__(self):
        self.symbols_by_fqcn: Dict[str, TypeSymbol] = dict(self.BUILTIN_ECOSYSTEM_SYMBOLS)
        self.symbols_by_simple_name: Dict[str, List[TypeSymbol]] = {}
        self.packages: Dict[str, List[TypeSymbol]] = {}

        # Re-index builtins
        for sym in self.symbols_by_fqcn.values():
            self._register_symbol_index(sym)

    def _register_symbol_index(self, sym: TypeSymbol) -> None:
        self.symbols_by_fqcn[sym.fqcn] = sym

        if sym.simple_name not in self.symbols_by_simple_name:
            self.symbols_by_simple_name[sym.simple_name] = []
        if sym not in self.symbols_by_simple_name[sym.simple_name]:
            self.symbols_by_simple_name[sym.simple_name].append(sym)

        if sym.package_name not in self.packages:
            self.packages[sym.package_name] = []
        if sym not in self.packages[sym.package_name]:
            self.packages[sym.package_name].append(sym)

    def scan_directory(self, root_dir: str | Path) -> int:
        """
        Recursively scans a workspace directory for Java files and indexes all types.
        """
        root = Path(root_dir)
        scanned_count = 0

        for path in root.rglob("*.java"):
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                self.index_source_code(content, source_file=str(path))
                scanned_count += 1
            except Exception:
                continue

        return scanned_count

    def index_source_code(self, source_code: str, source_file: Optional[str] = None) -> List[TypeSymbol]:
        """
        Parses a single Java source file into AST and registers all top-level types.
        """
        lexer = JavaLexer(source_code)
        tokens = lexer.tokenize()
        parser = JavaASTParser(tokens, source=source_code)
        unit = parser.parse()

        pkg_name = unit.package_decl.name if unit.package_decl else ""
        registered: List[TypeSymbol] = []

        for type_decl in unit.type_declarations:
            fqcn = f"{pkg_name}.{type_decl.name}" if pkg_name else type_decl.name
            super_cls = type_decl.extends_types[0].name if type_decl.extends_types else None
            ifaces = [imp.name for imp in type_decl.implements_types]
            annos = [anno.name for anno in type_decl.annotations]

            methods_map: Dict[str, List[str]] = {}
            for m in type_decl.members:
                if isinstance(m, MethodDeclaration):
                    param_types = [p.type_name for p in m.parameters]
                    methods_map[m.name] = param_types

            sym = TypeSymbol(
                fqcn=fqcn,
                simple_name=type_decl.name,
                package_name=pkg_name,
                kind=type_decl.kind,
                modifiers=list(type_decl.modifiers),
                super_class=super_cls,
                interfaces=ifaces,
                methods=methods_map,
                annotations=annos,
                source_file=source_file
            )
            self._register_symbol_index(sym)
            registered.append(sym)

        return registered

    def resolve_type(
        self,
        symbol_name: str,
        current_package: str = "",
        imports: Sequence[ImportDeclaration] = ()
    ) -> Optional[TypeSymbol]:
        """
        Cross-compilation unit type resolution:
        1. Fully qualified names directly checked.
        2. Explicit imports.
        3. Same package implicit resolution.
        4. Wildcard imports.
        5. Global unique simple names.
        """
        # 1. Fully qualified name
        if "." in symbol_name and symbol_name in self.symbols_by_fqcn:
            return self.symbols_by_fqcn[symbol_name]

        # 2. Check explicit imports
        for imp in imports:
            if not imp.is_wildcard:
                if imp.name.endswith(f".{symbol_name}") or imp.name == symbol_name:
                    if imp.name in self.symbols_by_fqcn:
                        return self.symbols_by_fqcn[imp.name]

        # 3. Same package resolution (Implicit same-package classes in Java)
        if current_package:
            same_pkg_fqcn = f"{current_package}.{symbol_name}"
            if same_pkg_fqcn in self.symbols_by_fqcn:
                return self.symbols_by_fqcn[same_pkg_fqcn]

        # 4. Check wildcard imports
        for imp in imports:
            if imp.is_wildcard:
                wildcard_pkg = imp.name.rstrip(".*").rstrip("*").rstrip(".")
                candidate_fqcn = f"{wildcard_pkg}.{symbol_name}"
                if candidate_fqcn in self.symbols_by_fqcn:
                    return self.symbols_by_fqcn[candidate_fqcn]

        # 5. Global unique simple name fallback
        candidates = self.symbols_by_simple_name.get(symbol_name, [])
        if len(candidates) == 1:
            return candidates[0]

        return None

    def get_type_hierarchy(self, fqcn: str) -> List[str]:
        """
        Returns the transitive type hierarchy (superclasses and interfaces) for a type.
        """
        hierarchy: List[str] = [fqcn]
        visited: Set[str] = {fqcn}
        queue = [fqcn]

        while queue:
            curr_name = queue.pop(0)
            sym = self.symbols_by_fqcn.get(curr_name)
            if not sym:
                continue

            if sym.super_class:
                # Try resolve super class FQCN
                resolved_super = self.resolve_type(sym.super_class, sym.package_name)
                super_fqcn = resolved_super.fqcn if resolved_super else sym.super_class
                if super_fqcn not in visited:
                    visited.add(super_fqcn)
                    hierarchy.append(super_fqcn)
                    queue.append(super_fqcn)

            for iface in sym.interfaces:
                resolved_iface = self.resolve_type(iface, sym.package_name)
                iface_fqcn = resolved_iface.fqcn if resolved_iface else iface
                if iface_fqcn not in visited:
                    visited.add(iface_fqcn)
                    hierarchy.append(iface_fqcn)
                    queue.append(iface_fqcn)

        return hierarchy


class ClasspathTypeSolver:
    """
    High-level facade connecting the GlobalClasspathIndex to AST visitors and compilation units.
    """

    def __init__(self, index: Optional[GlobalClasspathIndex] = None):
        self.index = index or GlobalClasspathIndex()

    def resolve_ast_symbols(self, unit: CompilationUnit) -> None:
        """
        Traverses a CompilationUnit and enriches all TypeReference and AnnotationNode
        objects with resolved_type and symbol_attributes based on the global index.
        """
        curr_pkg = unit.package_decl.name if unit.package_decl else ""
        imports = unit.imports

        for type_decl in unit.type_declarations:
            # Resolve annotations
            for anno in type_decl.annotations:
                sym = self.index.resolve_type(anno.name, curr_pkg, imports)
                if sym:
                    anno.resolved_type = sym.fqcn

            # Resolve extends
            for ext in type_decl.extends_types:
                sym = self.index.resolve_type(ext.name, curr_pkg, imports)
                if sym:
                    ext.resolved_type = sym.fqcn

            # Resolve implements
            for imp in type_decl.implements_types:
                sym = self.index.resolve_type(imp.name, curr_pkg, imports)
                if sym:
                    imp.resolved_type = sym.fqcn

            # Resolve members
            for m in type_decl.members:
                if isinstance(m, MethodDeclaration):
                    for anno in m.annotations:
                        sym = self.index.resolve_type(anno.name, curr_pkg, imports)
                        if sym:
                            anno.resolved_type = sym.fqcn
                    for param in m.parameters:
                        sym = self.index.resolve_type(param.type_name, curr_pkg, imports)
                        if sym:
                            param.symbol_attributes["resolved_type"] = sym.fqcn

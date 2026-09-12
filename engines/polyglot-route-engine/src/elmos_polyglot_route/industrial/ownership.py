"""Ownership, RAII, ARC and GC lowering for the industrial subset."""

from __future__ import annotations

from copy import deepcopy

from elmos_polyglot_route.ast_compiler.ir import (
    DropStmt,
    MoveStmt,
    UniversalMethod,
    UniversalModule,
    UniversalType,
)
from elmos_polyglot_route.ast_compiler.ir.ownership import OwnershipAnalyzer, OwnershipKind
from elmos_polyglot_route.industrial.concurrency import normalize_language

GC_LANGUAGES = frozenset(
    {"java", "csharp", "python", "typescript", "go", "kotlin", "php", "react", "flutter"}
)
RAII_LANGUAGES = frozenset({"cpp", "vcpp6", "rust"})
ARC_LANGUAGES = frozenset({"objc", "swift"})
VENDOR_LANGUAGES = frozenset({"vb6"})


def memory_model(language: str) -> str:
    key = normalize_language(language)
    if key in RAII_LANGUAGES:
        return "raii-owned"
    if key in ARC_LANGUAGES:
        return "arc"
    if key in VENDOR_LANGUAGES:
        return "manual-ref"
    return "tracing-gc"


class OwnershipMemoryEngine:
    """Rewrites unique/shared/GC pointers and records move/drop obligations."""

    @classmethod
    def lower_module(
        cls,
        module: UniversalModule,
        source_language: str,
        target_language: str,
    ) -> UniversalModule:
        source = normalize_language(source_language)
        target = normalize_language(target_language)
        out = deepcopy(module)
        out.metadata = dict(out.metadata)
        out.metadata["memory_model"] = {
            "source": memory_model(source),
            "target": memory_model(target),
        }
        for klass in out.classes:
            for field in klass.fields:
                field.type_info = cls.lower_type(field.type_info, source, target)
            for method in klass.methods:
                cls._lower_method(method, source, target)
        for method in out.free_functions:
            cls._lower_method(method, source, target)
        return out

    @classmethod
    def _lower_method(cls, method: UniversalMethod, source: str, target: str) -> None:
        method.return_type = cls.lower_type(method.return_type, source, target)
        for param in method.params:
            param.type_info = cls.lower_type(param.type_info, source, target)
        analyzer = OwnershipAnalyzer(is_rust_mode=(target == "rust"))
        for param in method.params:
            kind = OwnershipKind.OWNED
            if param.type_info.pointer_kind == "shared":
                kind = OwnershipKind.ARC_MANAGED
            elif param.type_info.pointer_kind in {"raw"}:
                kind = OwnershipKind.RAW_PTR
            elif memory_model(target) == "tracing-gc":
                kind = OwnershipKind.GC_MANAGED
            analyzer.declare_variable(param.name, kind)
        for stmt in method.body:
            if isinstance(stmt, MoveStmt):
                analyzer.declare_variable(stmt.target, OwnershipKind.OWNED)
                analyzer.record_move(stmt.source, location=f"{method.name}:{stmt.source}")
            elif isinstance(stmt, DropStmt):
                analyzer.release_borrows(stmt.name)
        if target == "rust":
            violations = [v for v in analyzer.violations if v.violation_type != "USE_AFTER_MOVE"]
            # Move/drop in the industrial subset is explicit and legal. Alias errors fail closed.
            blocking = [v for v in analyzer.violations if v.violation_type in {"ALIASING_CONFLICT", "MULTIPLE_MUT_BORROW"}]
            if blocking:
                raise ValueError(
                    f"BLOCKED_OWNERSHIP:{blocking[0].violation_type}:{blocking[0].message}"
                )

    @classmethod
    def lower_type(cls, typ: UniversalType, source: str, target: str) -> UniversalType:
        src_model = memory_model(source)
        tgt_model = memory_model(target)
        if typ.kind != "pointer" and not typ.pointer_kind:
            if tgt_model == "raii-owned" and typ.kind == "custom" and src_model == "tracing-gc":
                return UniversalType.shared_ptr_of(typ) if target != "rust" else UniversalType(
                    kind="pointer",
                    name="Arc",
                    element_type=typ,
                    pointer_kind="shared",
                )
            return typ
        if tgt_model == "tracing-gc" and typ.element_type is not None:
            return typ.element_type
        if tgt_model == "arc" and typ.element_type is not None:
            return UniversalType.arc_strong(typ.element_type)
        return typ

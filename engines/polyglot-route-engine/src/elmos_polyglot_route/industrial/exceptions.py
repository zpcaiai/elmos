"""Exception / Result / (T, error) channel lowering."""

from __future__ import annotations

from copy import deepcopy

from elmos_polyglot_route.ast_compiler.ir import (
    CatchClause,
    ThrowStmt,
    TryCatchFinallyStmt,
    UniversalMethod,
    UniversalModule,
)
from elmos_polyglot_route.industrial.concurrency import normalize_language

ERROR_CHANNEL: dict[str, str] = {
    "java": "throw-Exception",
    "csharp": "throw-Exception",
    "python": "raise-Exception",
    "typescript": "throw-Error",
    "kotlin": "throw-Exception",
    "php": "throw-Exception",
    "cpp": "throw-runtime_error",
    "objc": "NSException",
    "swift": "throw-Error",
    "react": "throw-Error",
    "flutter": "throw-Exception",
    "vb6": "On Error / Err.Raise",
    "vcpp6": "throw-CException",
    "go": "(T, error)",
    "rust": "Result<T, E>",
}


class ExceptionErrorEngine:
    @classmethod
    def lower_module(cls, module: UniversalModule, target_language: str) -> UniversalModule:
        target = normalize_language(target_language)
        out = deepcopy(module)
        out.metadata = dict(out.metadata)
        out.metadata["error_channel"] = ERROR_CHANNEL[target]
        for klass in out.classes:
            for method in klass.methods:
                cls._lower_method(method, target)
        for method in out.free_functions:
            cls._lower_method(method, target)
        return out

    @classmethod
    def _lower_method(cls, method: UniversalMethod, target: str) -> None:
        for stmt in method.body:
            if isinstance(stmt, TryCatchFinallyStmt):
                method.has_exception_handling = True
                for catch in stmt.catch_clauses:
                    catch.exception_type = cls._catch_type(target, catch)
            if isinstance(stmt, ThrowStmt) and target in {"go", "rust"}:
                method.has_exception_handling = True

    @classmethod
    def _catch_type(cls, target: str, catch: CatchClause) -> str:
        if target == "python":
            return "Exception"
        if target == "typescript" or target == "react":
            return "Error"
        if target == "go":
            return "error"
        if target == "rust":
            return "Box<dyn std::error::Error>"
        if target == "vb6":
            return "Err"
        return "Exception"

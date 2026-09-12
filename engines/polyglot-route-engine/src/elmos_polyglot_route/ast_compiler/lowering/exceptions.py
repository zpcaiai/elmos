"""Exception unwinding & error handling lowering across 8 languages."""

from __future__ import annotations

from ..ir import CatchClause, RawSnippetStmt, ThrowStmt, TryCatchFinallyStmt, UniversalClass, UniversalMethod, UniversalModule


class ExceptionLowering:
    """Maps stack unwinding exceptions to Result/Error returns and vice versa."""

    @classmethod
    def lower_module(cls, module: UniversalModule, target_language: str) -> UniversalModule:
        target = target_language.lower().strip()
        for c in module.classes:
            for m in c.methods:
                cls.lower_method(m, target)
        return module

    @classmethod
    def lower_method(cls, m: UniversalMethod, target_language: str) -> None:
        # Standardize catch clauses
        for stmt in m.body:
            if isinstance(stmt, TryCatchFinallyStmt):
                for catch in stmt.catch_clauses:
                    if target_language in ('java', 'csharp', 'kotlin'):
                        catch.exception_type = 'Exception'
                    elif target_language == 'python':
                        catch.exception_type = 'Exception'
                    elif target_language == 'typescript':
                        catch.exception_type = 'any'
                    elif target_language == 'go':
                        catch.exception_type = 'error'
                    elif target_language == 'rust':
                        catch.exception_type = 'Box<dyn std::error::Error>'

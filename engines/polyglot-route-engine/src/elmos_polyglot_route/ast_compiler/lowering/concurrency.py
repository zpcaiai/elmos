"""Async & concurrency semantic lowering across 8 languages."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalMethod, UniversalModule, UniversalType


class ConcurrencyLowering:
    """Harmonizes async/await, Tasks, Promises, Futures, and goroutines."""

    @classmethod
    def lower_module(cls, module: UniversalModule, target_language: str) -> UniversalModule:
        target = target_language.lower().strip()
        for c in module.classes:
            for m in c.methods:
                cls.lower_method(m, target)
        for m in module.free_functions:
            cls.lower_method(m, target)
        return module

    @classmethod
    def lower_method(cls, m: UniversalMethod, target_language: str) -> None:
        if not m.is_async:
            return

        # Adapt return type wrapping based on target language
        orig_ret = m.return_type
        if target_language == 'java':
            # CompletableFuture<T>
            m.return_type = UniversalType.custom(f'CompletableFuture<{orig_ret.name}>')
        elif target_language == 'csharp':
            # Task<ActionResult<T>> for web or Task<T>
            if m.http_method:
                m.return_type = UniversalType.custom(f'Task<ActionResult<{orig_ret.name}>>')
            else:
                m.return_type = UniversalType.custom(f'Task<{orig_ret.name}>')
        elif target_language == 'typescript':
            # Promise<T>
            m.return_type = UniversalType.custom(f'Promise<{orig_ret.name}>')
        elif target_language == 'go':
            # (T, error)
            m.return_type = orig_ret
        elif target_language == 'rust':
            # Result<T, ...>
            m.return_type = UniversalType.custom(f'Result<{orig_ret.name}, Box<dyn std::error::Error>>')
        elif target_language == 'kotlin':
            # Coroutine suspend fun
            m.return_type = orig_ret
        elif target_language == 'python':
            # async def with raw return annotation
            m.return_type = orig_ret

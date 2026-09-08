"""Public source-analyzer dispatch without widening the native legacy module."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .dart_analyzer import analyze_flutter
from .flutter_repository import analyze_flutter_many, inventory_flutter_module
from .kotlin_repository import inventory_kotlin_module
from .models import Language, RouteError, SemanticIR
from .native import analyze as analyze_native
from .native import analyze_many as analyze_many_native
from .native import inventory_module as inventory_module_native
from .react_analyzer import analyze_react, inventory_react_module
from .toolchains import exact_toolchain


def analyze(
    source: Path,
    language: Language,
    function_name: str,
    *,
    emitted_target: bool = False,
) -> SemanticIR:
    """Dispatch exact source frontends, preserving React and Flutter boundaries."""

    if language == "react":
        return analyze_react(source, function_name, emitted_target=emitted_target)
    if language == "flutter":
        return analyze_flutter(
            source,
            function_name,
            exact_toolchain("flutter"),
            emitted_target=emitted_target,
        )
    return analyze_native(source, language, function_name, emitted_target=emitted_target)


def inventory_module(
    source: Path,
    language: Language,
    *,
    emitted_target: bool = False,
) -> dict[str, object]:
    """Dispatch compiler-backed module inventories for every source identity."""

    if language == "react":
        return inventory_react_module(source, emitted_target=emitted_target)
    if language == "flutter":
        return inventory_flutter_module(
            source,
            exact_toolchain("flutter"),
            emitted_target=emitted_target,
        )
    if language == "kotlin":
        return inventory_kotlin_module(source)
    if emitted_target:
        return inventory_module_native(source, language)
    return inventory_module_native(source, language)


def analyze_many(
    source: Path,
    language: Language,
    function_names: Sequence[str],
    *,
    emitted_target: bool = False,
) -> dict[str, SemanticIR | RouteError]:
    """Analyze repository candidates without bypassing framework adapters."""

    if language == "flutter":
        return analyze_flutter_many(
            source,
            function_names,
            emitted_target=emitted_target,
        )
    if language == "react":
        outcomes: dict[str, SemanticIR | RouteError] = {}
        for name in dict.fromkeys(function_names):
            try:
                outcomes[name] = analyze_react(
                    source,
                    name,
                    emitted_target=emitted_target,
                )
            except RouteError as error:
                outcomes[name] = error
        return outcomes
    return analyze_many_native(
        source,
        language,
        function_names,
        emitted_target=emitted_target,
    )


__all__ = ["analyze", "analyze_many", "inventory_module"]

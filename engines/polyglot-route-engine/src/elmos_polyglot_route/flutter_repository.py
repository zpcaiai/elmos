"""Repository-facing Flutter/Dart source adapter.

The active route identity is ``flutter`` even though the bounded source
surface is deliberately pure Dart.  Flutter UI, Widget, async, platform and
effect semantics remain outside this adapter and are rejected by the exact
AST frontend in :mod:`dart_analyzer`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .dart_analyzer import analyze_flutter, inventory_flutter
from .models import RouteError, SemanticIR
from .toolchains import ExactToolchain, exact_toolchain


def inventory_flutter_module(
    source: Path,
    toolchain: ExactToolchain,
    *,
    emitted_target: bool = False,
) -> dict[str, object]:
    """Inventory one Dart module with Flutter's exact bundled analyzer graph."""

    return inventory_flutter(source, toolchain, emitted_target=emitted_target)


def analyze_flutter_many(
    source: Path,
    function_names: Sequence[str],
    *,
    emitted_target: bool = False,
) -> dict[str, SemanticIR | RouteError]:
    """Analyze a bounded set of names without weakening per-name failures.

    The Dart helper currently accepts one selector per invocation.  Repository
    discovery is allowed to fall back to that exact per-function behavior; it
    must still return a result for every requested name, including a typed
    ``RouteError`` for a source-domain rejection.
    """

    toolchain = exact_toolchain("flutter")
    outcomes: dict[str, SemanticIR | RouteError] = {}
    for name in function_names:
        if name in outcomes:
            outcomes[name] = RouteError(f"DART_DUPLICATE_ANALYSIS_SELECTOR:{name}")
            continue
        try:
            outcomes[name] = analyze_flutter(
                source,
                name,
                toolchain,
                emitted_target=emitted_target,
            )
        except RouteError as error:
            outcomes[name] = error
    return outcomes


__all__ = ["analyze_flutter_many", "inventory_flutter_module"]

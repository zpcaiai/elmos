"""Authoritative directed route sets for the explicit nine-language matrix.

The original six-language matrix and exact-eight native profile retain their
identities for provenance.  The completion set contains every remaining pair,
so the union is the one explicit 9 x 8 matrix requested by product policy.
"""

from __future__ import annotations

from collections.abc import Iterable

CORE_LANGUAGES = ("java", "csharp", "go", "rust", "python", "typescript")
SPECIALIZED_LANGUAGES = ("cpp", "objc", "swift")
SUPPORTED_ROUTE_LANGUAGES = (*CORE_LANGUAGES, *SPECIALIZED_LANGUAGES)

COMPLETE_ROUTE_KEYS = tuple(
    f"{source}-to-{target}"
    for source in SUPPORTED_ROUTE_LANGUAGES
    for target in SUPPORTED_ROUTE_LANGUAGES
    if source != target
)

CORE_ROUTE_KEYS = tuple(
    f"{source}-to-{target}" for source in CORE_LANGUAGES for target in CORE_LANGUAGES if source != target
)

SPECIALIZED_ROUTE_KEYS = (
    "cpp-to-objc",
    "objc-to-cpp",
    "cpp-to-swift",
    "swift-to-cpp",
    "objc-to-swift",
    "swift-to-objc",
    "cpp-to-java",
    "java-to-cpp",
)

COMPLETION_ROUTE_KEYS = tuple(
    route_key for route_key in COMPLETE_ROUTE_KEYS if route_key not in {*CORE_ROUTE_KEYS, *SPECIALIZED_ROUTE_KEYS}
)

EXACT_ROUTE_SETS = {
    "legacy-complete-30": CORE_ROUTE_KEYS,
    "cpp-objc-swift-java-exact-8": SPECIALIZED_ROUTE_KEYS,
    "nine-language-completion-34": COMPLETION_ROUTE_KEYS,
    "nine-language-complete-72": COMPLETE_ROUTE_KEYS,
}
EVIDENCED_ROUTE_KEYS = COMPLETE_ROUTE_KEYS


def provenance_route_set(route_key: str) -> str:
    """Return the disjoint provenance set owning one complete-matrix route."""

    if route_key in CORE_ROUTE_KEYS:
        return "legacy-complete-30"
    if route_key in SPECIALIZED_ROUTE_KEYS:
        return "cpp-objc-swift-java-exact-8"
    if route_key in COMPLETION_ROUTE_KEYS:
        return "nine-language-completion-34"
    raise ValueError(f"UNDECLARED_DIRECTED_ROUTE:{route_key}")


def split_route_key(route_key: str) -> tuple[str, str]:
    """Return one exact evidenced direction, rejecting inferred routes."""

    if route_key not in EVIDENCED_ROUTE_KEYS:
        raise ValueError(f"UNDECLARED_DIRECTED_ROUTE:{route_key}")
    source, target = route_key.split("-to-", 1)
    return source, target


def validate_exact_route_keys(route_keys: Iterable[str]) -> tuple[str, ...]:
    """Validate a non-empty, duplicate-free subset of declared route keys."""

    values = tuple(route_keys)
    if not values:
        raise ValueError("EXACT_ROUTE_SET_EMPTY")
    if len(set(values)) != len(values):
        raise ValueError("EXACT_ROUTE_SET_DUPLICATED")
    for route_key in values:
        split_route_key(route_key)
    return values

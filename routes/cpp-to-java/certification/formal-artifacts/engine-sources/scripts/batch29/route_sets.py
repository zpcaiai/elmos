"""Authoritative directed route sets for Batch 29.

The original six-language matrix remains a complete 6 x 5 set.  C++,
Objective-C and Swift are deliberately introduced through an exact eight-route
specialized set; their presence must never imply the unsupported 9 x 8 matrix.
"""

from __future__ import annotations

from collections.abc import Iterable

CORE_LANGUAGES = ("java", "csharp", "go", "rust", "python", "typescript")
SPECIALIZED_LANGUAGES = ("cpp", "objc", "swift")
SUPPORTED_ROUTE_LANGUAGES = (*CORE_LANGUAGES, *SPECIALIZED_LANGUAGES)

CORE_ROUTE_KEYS = tuple(
    f"{source}-to-{target}"
    for source in CORE_LANGUAGES
    for target in CORE_LANGUAGES
    if source != target
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

EXACT_ROUTE_SETS = {
    "legacy-complete-30": CORE_ROUTE_KEYS,
    "cpp-objc-swift-java-exact-8": SPECIALIZED_ROUTE_KEYS,
}
EVIDENCED_ROUTE_KEYS = (*CORE_ROUTE_KEYS, *SPECIALIZED_ROUTE_KEYS)


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

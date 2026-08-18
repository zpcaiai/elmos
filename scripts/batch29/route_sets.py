"""Authoritative directed route sets for the explicit ten-language matrix.

The original six-language matrix, exact-eight native profile, and nine-language
completion retain their immutable identities for provenance.  JavaScript is a
separate Node.js/ESM language identity (not a TypeScript alias) and contributes
exactly eighteen new directed routes against the established nine languages.
"""

from __future__ import annotations

from collections.abc import Iterable

CORE_LANGUAGES = ("java", "csharp", "go", "rust", "python", "typescript")
SPECIALIZED_LANGUAGES = ("cpp", "objc", "swift")
NINE_LANGUAGE_MATRIX_LANGUAGES = (*CORE_LANGUAGES, *SPECIALIZED_LANGUAGES)
NODEJS_LANGUAGES = ("javascript",)
PHP_LANGUAGES = ("php",)
TEN_LANGUAGE_MATRIX_LANGUAGES = (*NINE_LANGUAGE_MATRIX_LANGUAGES, *NODEJS_LANGUAGES)
SUPPORTED_ROUTE_LANGUAGES = (*TEN_LANGUAGE_MATRIX_LANGUAGES, *PHP_LANGUAGES)

NINE_LANGUAGE_COMPLETE_ROUTE_KEYS = tuple(
    f"{source}-to-{target}"
    for source in NINE_LANGUAGE_MATRIX_LANGUAGES
    for target in NINE_LANGUAGE_MATRIX_LANGUAGES
    if source != target
)

#: The 90 the matrix had before php. Kept as its own name rather than recomputed
#: from SUPPORTED_ROUTE_LANGUAGES because "ten-language-complete-90" is a
#: recorded set name: letting it silently follow the language tuple would have
#: renamed the thing 90 routes' evidence was filed under.
TEN_LANGUAGE_COMPLETE_ROUTE_KEYS = tuple(
    f"{source}-to-{target}"
    for source in TEN_LANGUAGE_MATRIX_LANGUAGES
    for target in TEN_LANGUAGE_MATRIX_LANGUAGES
    if source != target
)

COMPLETE_ROUTE_KEYS = tuple(
    f"{source}-to-{target}"
    for source in SUPPORTED_ROUTE_LANGUAGES
    for target in SUPPORTED_ROUTE_LANGUAGES
    if source != target
)

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

COMPLETION_ROUTE_KEYS = tuple(
    route_key
    for route_key in NINE_LANGUAGE_COMPLETE_ROUTE_KEYS
    if route_key not in {*CORE_ROUTE_KEYS, *SPECIALIZED_ROUTE_KEYS}
)

#: Exactly the 18 directions javascript added to the nine-language matrix.
#: Derived from the ten-language set, not from COMPLETE_ROUTE_KEYS: computing it
#: against the eleven-language set would pull javascript-to-php and
#: php-to-javascript in here and silently grow an immutable Batch 29 provenance
#: partition from 18 to 20.
NODEJS_EXACT_ROUTE_KEYS = tuple(
    route_key
    for route_key in TEN_LANGUAGE_COMPLETE_ROUTE_KEYS
    if route_key not in NINE_LANGUAGE_COMPLETE_ROUTE_KEYS
)

#: The 20 directions php adds, which is every pair naming php -- including
#: javascript-to-php and php-to-javascript. Those two are Node directions by
#: runtime, but they are php directions by provenance: no evidence exists for
#: them, and filing them under the Node partition would attach them to a
#: campaign that never ran them.
PHP_EXACT_ROUTE_KEYS = tuple(
    route_key
    for route_key in COMPLETE_ROUTE_KEYS
    if route_key not in TEN_LANGUAGE_COMPLETE_ROUTE_KEYS
)

# These four provenance sets are the only authority partition for the complete
# ten-language matrix.  The 72-route and 90-route sets below are convenient
# unions, not additional owners.  Keeping the partition explicit prevents a
# newer campaign from silently reclassifying or overwriting the immutable
# legacy 30-route evidence.
ROUTE_PROVENANCE_PARTITIONS = {
    "legacy-complete-30": CORE_ROUTE_KEYS,
    "cpp-objc-swift-java-exact-8": SPECIALIZED_ROUTE_KEYS,
    "nine-language-completion-34": COMPLETION_ROUTE_KEYS,
    "javascript-node26-completion-18": NODEJS_EXACT_ROUTE_KEYS,
    "php-php85-completion-20": PHP_EXACT_ROUTE_KEYS,
}

_partition_members = tuple(
    route_key
    for route_keys in ROUTE_PROVENANCE_PARTITIONS.values()
    for route_key in route_keys
)
if len(_partition_members) != len(set(_partition_members)):
    raise RuntimeError("ROUTE_PROVENANCE_PARTITIONS_OVERLAP")
if set(_partition_members) != set(COMPLETE_ROUTE_KEYS):
    raise RuntimeError("ROUTE_PROVENANCE_PARTITIONS_INCOMPLETE")

MODULE_EQUIVALENCE_ROUTE_KEYS = (*SPECIALIZED_ROUTE_KEYS, *NODEJS_EXACT_ROUTE_KEYS)

NODEJS_NEGATIVE_COMMON_CASE_IDS = (
    "nodejs-ambiguous-jsdoc-type-unsupported",
    "nodejs-async-function-unsupported",
    "nodejs-coercive-equality-unsupported",
    "nodejs-commonjs-unsupported",
    "nodejs-dynamic-eval-unsupported",
    "nodejs-generator-function-unsupported",
    "nodejs-import-unsupported",
    "nodejs-missing-jsdoc-unsupported",
    "nodejs-number-arithmetic-unsupported",
    "nodejs-promise-timer-unsupported",
    "nodejs-this-prototype-unsupported",
    "nodejs-top-level-side-effect-unsupported",
    "nodejs-non-finite-case-unsupported",
    "undeclared-directed-route-fails-closed",
    "missing-symbol-fails-closed",
)

NODEJS_NEGATIVE_NON_TYPESCRIPT_CASE_IDS = (
    "nodejs-division-by-zero-unsupported",
    "nodejs-integer-overflow-unsupported",
    "nodejs-modulo-by-zero-unsupported",
    "nodejs-string-semantics-unsupported",
    "nodejs-unsafe-integer-case-unsupported",
    "nodejs-unsafe-integer-intermediate-boolean-unsupported",
    "nodejs-unsafe-integer-intermediate-integer-unsupported",
    "nodejs-unsafe-integer-intermediate-number-unsupported",
    "nodejs-unsafe-integer-result-unsupported",
)

EXACT_ROUTE_SETS = {
    **ROUTE_PROVENANCE_PARTITIONS,
    "nine-language-complete-72": NINE_LANGUAGE_COMPLETE_ROUTE_KEYS,
    "javascript-node26-completion-18": NODEJS_EXACT_ROUTE_KEYS,
    "ten-language-complete-90": TEN_LANGUAGE_COMPLETE_ROUTE_KEYS,
    "eleven-language-complete-110": COMPLETE_ROUTE_KEYS,
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
    if route_key in NODEJS_EXACT_ROUTE_KEYS:
        return "javascript-node26-completion-18"
    if route_key in PHP_EXACT_ROUTE_KEYS:
        return "php-php85-completion-20"
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


def nodejs_negative_case_ids(source: str, target: str) -> tuple[str, ...]:
    """Return the exact fail-closed corpus for one declared Node.js direction."""

    route_key = f"{source}-to-{target}"
    if route_key not in NODEJS_EXACT_ROUTE_KEYS:
        raise ValueError(f"NOT_A_NODEJS_DIRECTED_ROUTE:{route_key}")
    route_specific = (
        ("nodejs-typescript-integer-contract-unsupported",)
        if {source, target} == {"javascript", "typescript"}
        else NODEJS_NEGATIVE_NON_TYPESCRIPT_CASE_IDS
    )
    return tuple(sorted((*NODEJS_NEGATIVE_COMMON_CASE_IDS, *route_specific)))

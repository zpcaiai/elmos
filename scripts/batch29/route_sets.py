"""Authoritative directed route sets for the explicit thirteen-language matrix.

The original six-language matrix, exact-eight native profile, nine-language
completion, Node.js expansion and PHP completion retain their immutable
identities for provenance.  Kotlin, React and Flutter contribute exactly
sixty-six new directed routes against the ten languages that remain active.

JavaScript is deprecated: its twenty directions leave the *active* matrix but
stay declared, keep their packs under ``routes/``, and keep their provenance
partitions at their recorded sizes.  ``COMPLETE_ROUTE_KEYS`` is therefore the
active set (156) while ``ALL_DECLARED_ROUTE_KEYS`` is the set the provenance
partitions must exactly cover (176).
"""

from __future__ import annotations

from collections.abc import Iterable

CORE_LANGUAGES = ("java", "csharp", "go", "rust", "python", "typescript")
SPECIALIZED_LANGUAGES = ("cpp", "objc", "swift")
NINE_LANGUAGE_MATRIX_LANGUAGES = (*CORE_LANGUAGES, *SPECIALIZED_LANGUAGES)
NODEJS_LANGUAGES = ("javascript",)
PHP_LANGUAGES = ("php",)
TEN_LANGUAGE_MATRIX_LANGUAGES = (*NINE_LANGUAGE_MATRIX_LANGUAGES, *NODEJS_LANGUAGES)

#: The eleven-language matrix as it stood before javascript was deprecated.
#: Frozen under its own name for the same reason the nine- and ten-language
#: tuples are: "eleven-language-complete-110" is a recorded set name and 110
#: routes' evidence is filed under it.
ELEVEN_LANGUAGE_MATRIX_LANGUAGES = (*TEN_LANGUAGE_MATRIX_LANGUAGES, *PHP_LANGUAGES)

#: Kotlin, React and Flutter. Their exact local analyzers and bounded
#: repository inventory/build surfaces are executable; declaration still is
#: not independent-verification or certification evidence.
V3_LANGUAGES = ("kotlin", "react", "flutter")

#: Deprecated: still declared, no longer active.  Every javascript direction is
#: excluded from ``COMPLETE_ROUTE_KEYS`` and rejected by ``split_route_key``.
DEPRECATED_ROUTE_LANGUAGES = NODEJS_LANGUAGES

SUPPORTED_ROUTE_LANGUAGES = (
    *(
        language
        for language in ELEVEN_LANGUAGE_MATRIX_LANGUAGES
        if language not in DEPRECATED_ROUTE_LANGUAGES
    ),
    *V3_LANGUAGES,
)

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

#: The 110 the matrix had before javascript was deprecated and before kotlin,
#: react and flutter were added.  Frozen for the same reason as the 90.
ELEVEN_LANGUAGE_COMPLETE_ROUTE_KEYS = tuple(
    f"{source}-to-{target}"
    for source in ELEVEN_LANGUAGE_MATRIX_LANGUAGES
    for target in ELEVEN_LANGUAGE_MATRIX_LANGUAGES
    if source != target
)

#: The active matrix: 13 x 12 = 156.  Contains no javascript direction.
COMPLETE_ROUTE_KEYS = tuple(
    f"{source}-to-{target}"
    for source in SUPPORTED_ROUTE_LANGUAGES
    for target in SUPPORTED_ROUTE_LANGUAGES
    if source != target
)

#: The 20 javascript directions that left the active matrix.  They keep their
#: packs, their evidence and their partition names; they are simply no longer
#: executable through the official runner.
DEPRECATED_ROUTE_KEYS = tuple(
    route_key
    for route_key in ELEVEN_LANGUAGE_COMPLETE_ROUTE_KEYS
    if route_key not in set(COMPLETE_ROUTE_KEYS)
)

#: Active plus deprecated.  This -- not ``COMPLETE_ROUTE_KEYS`` -- is what the
#: provenance partitions must exactly cover, because a partition owns filed
#: evidence and evidence does not disappear when a language is deprecated.
ALL_DECLARED_ROUTE_KEYS = (*COMPLETE_ROUTE_KEYS, *DEPRECATED_ROUTE_KEYS)

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
#: Derived from the frozen eleven-language set, NOT from COMPLETE_ROUTE_KEYS.
#: Against the thirteen-language active set this comprehension would have
#: returned 86 keys (20 php + 66 kotlin/react/flutter) and silently grown a
#: recorded 20-route partition, exactly the failure the nodejs comment below
#: warns about.
PHP_EXACT_ROUTE_KEYS = tuple(
    route_key
    for route_key in ELEVEN_LANGUAGE_COMPLETE_ROUTE_KEYS
    if route_key not in TEN_LANGUAGE_COMPLETE_ROUTE_KEYS
)

#: The executable PHP completion selection excludes the two archived
#: javascript directions from the immutable 20-route provenance partition.
#: It is a runner selection, not a new evidence owner: every member remains
#: filed under ``php-php85-completion-20``.
PHP_ACTIVE_ROUTE_KEYS = tuple(
    route_key
    for route_key in PHP_EXACT_ROUTE_KEYS
    if route_key not in set(DEPRECATED_ROUTE_KEYS)
)

#: Exactly the 66 directions kotlin, react and flutter added to the eleven
#: language matrix.  Derived as active-minus-eleven, so every direction naming
#: a new language belongs here -- including the ones whose other end is
#: javascript-free but previously unrouted.
V3_EXACT_ROUTE_KEYS = tuple(
    route_key
    for route_key in COMPLETE_ROUTE_KEYS
    if route_key not in set(ELEVEN_LANGUAGE_COMPLETE_ROUTE_KEYS)
)

# These six provenance sets are the only authority partition for every declared
# direction, active or deprecated.  The 72-, 90- and 110-route sets below are
# convenient unions, not additional owners.  Keeping the partition explicit
# prevents a newer campaign from silently reclassifying or overwriting the
# immutable legacy 30-route evidence -- and prevents a deprecation from
# orphaning evidence that was filed under a still-recorded name.
ROUTE_PROVENANCE_PARTITIONS = {
    "legacy-complete-30": CORE_ROUTE_KEYS,
    "cpp-objc-swift-java-exact-8": SPECIALIZED_ROUTE_KEYS,
    "nine-language-completion-34": COMPLETION_ROUTE_KEYS,
    "javascript-node26-completion-18": NODEJS_EXACT_ROUTE_KEYS,
    "php-php85-completion-20": PHP_EXACT_ROUTE_KEYS,
    "kotlin-react-flutter-completion-66": V3_EXACT_ROUTE_KEYS,
}

#: The partitions that own an *active* direction.  A deprecated partition still
#: owns its evidence; it simply owns nothing the runner will execute.
DEPRECATED_ROUTE_PROVENANCE_SETS = ("javascript-node26-completion-18",)

_partition_members = tuple(
    route_key
    for route_keys in ROUTE_PROVENANCE_PARTITIONS.values()
    for route_key in route_keys
)
if len(_partition_members) != len(set(_partition_members)):
    raise RuntimeError("ROUTE_PROVENANCE_PARTITIONS_OVERLAP")
# Covers active *and* deprecated: see ALL_DECLARED_ROUTE_KEYS.  Comparing
# against COMPLETE_ROUTE_KEYS here would reject the retained javascript
# evidence and force it to be deleted to make the import succeed.
if set(_partition_members) != set(ALL_DECLARED_ROUTE_KEYS):
    raise RuntimeError("ROUTE_PROVENANCE_PARTITIONS_INCOMPLETE")
if set(DEPRECATED_ROUTE_KEYS) - set(NODEJS_EXACT_ROUTE_KEYS) - set(PHP_EXACT_ROUTE_KEYS):
    raise RuntimeError("DEPRECATED_ROUTE_KEYS_UNOWNED")

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
    # Repointed at the frozen tuple.  This entry used to be an alias for
    # COMPLETE_ROUTE_KEYS; leaving it that way would have renamed the active
    # 156 to "eleven-language-complete-110".
    "eleven-language-complete-110": ELEVEN_LANGUAGE_COMPLETE_ROUTE_KEYS,
    "thirteen-language-complete-156": COMPLETE_ROUTE_KEYS,
}

# CLI mutation surfaces intentionally do not expose historical sets, mixed
# active/deprecated sets, or the V3 research-only routes as executable.  The
# PHP 18 is an execution selection over the immutable PHP 20 provenance set.
EXECUTABLE_ROUTE_SETS = {
    "legacy-complete-30": CORE_ROUTE_KEYS,
    "cpp-objc-swift-java-exact-8": SPECIALIZED_ROUTE_KEYS,
    "nine-language-completion-34": COMPLETION_ROUTE_KEYS,
    "nine-language-complete-72": NINE_LANGUAGE_COMPLETE_ROUTE_KEYS,
    "php-php85-active-completion-18": PHP_ACTIVE_ROUTE_KEYS,
}

# Preparation may synchronize V3 research metadata, but it still cannot touch
# a deprecated direction.  The complete active 156 is therefore preparable
# while the frozen 90/110 and provenance PHP 20 are read-only.
PREPARABLE_ROUTE_SETS = {
    **EXECUTABLE_ROUTE_SETS,
    "kotlin-react-flutter-completion-66": V3_EXACT_ROUTE_KEYS,
    "thirteen-language-complete-156": COMPLETE_ROUTE_KEYS,
}

# Read-only verification accepts every immutable provenance/view set plus the
# PHP active execution selection.  It never mutates route evidence.
READ_ONLY_ROUTE_SETS = {
    **EXACT_ROUTE_SETS,
    "php-php85-active-completion-18": PHP_ACTIVE_ROUTE_KEYS,
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
    if route_key in V3_EXACT_ROUTE_KEYS:
        return "kotlin-react-flutter-completion-66"
    raise ValueError(f"UNDECLARED_DIRECTED_ROUTE:{route_key}")


def split_route_key(route_key: str) -> tuple[str, str]:
    """Return one exact evidenced direction, rejecting inferred routes.

    Deprecated directions fail closed here with their own error code rather
    than the generic one, so a caller that still names a javascript route gets
    told the route was retired instead of being told it never existed.
    """

    if route_key in DEPRECATED_ROUTE_KEYS:
        raise ValueError(f"DEPRECATED_DIRECTED_ROUTE:{route_key}")
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

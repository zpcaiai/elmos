"""Deterministic, proof-carrying identifier hygiene for the pure-function IR.

This module deliberately does not emit source text.  It owns the narrower
contract that the emitter, target harness and target re-lifter can consume in
a later integration step:

* every function and parameter binder receives one content-bound identity;
* target spellings are selected by a bounded, deterministic candidate policy;
* an :class:`IdentifierPlan` can be recomputed rather than trusted; and
* a raw target re-lift can be alpha-normalized only through the verified,
  typed, scope-aware bijection.

The current semantic IR has no locals, calls, fields, methods or types as
binders.  Those constructs are not guessed here.  Multi-function modules are
supported because every function and parameter has a scope-bound ordinal and
the whole-file closure consumes both raw target spellings and canonical names.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Any, Literal, cast

from . import types
from .models import Expression, Function, Language, RouteError, SemanticIR, Statement

SCHEMA_VERSION = "2.0.0"
PLAN_KIND = "elmos.typed-identifier-plan"
POLICY_ID = "typed-alpha-hygiene-v2"
UNIT_NAMESPACE_SCHEMA_VERSION = "1.0.0"
UNIT_NAMESPACE_KIND = "elmos.identifier-unit-namespace"
MAX_IDENTIFIER_CANDIDATES = 16
_IDENTIFIER_PATTERN = r"[A-Za-z_][A-Za-z0-9_]*"
_IDENTIFIER_RE = re.compile(rf"^{_IDENTIFIER_PATTERN}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

#: Locals are looked up in the rename map under a prefixed key so a binder and
#: a reference to it never collide.
_LOCAL_BINDER_PREFIX = "\x00local:"

BindingRole = Literal["function", "parameter", "local"]
CandidateStatus = Literal["REJECTED", "SELECTED"]
BindingDecision = Literal["PRESERVED", "ALPHA_RENAMED"]
UnitNamespaceScope = Literal[
    "standalone-semantic-ir",
    "standalone-artifact",
    "repository-work-unit",
]

_WORK_UNIT_ID_RE = re.compile(r"^WU-[0-9]{5}(?:-F[0-9]{3})?$")


def _words(value: str) -> frozenset[str]:
    return frozenset(value.split())


_JAVA_RESERVED = _words(
    """
    _ abstract assert boolean break byte case catch char class const continue
    default do double else enum extends final finally float for goto if
    implements import instanceof int interface long native new package private
    protected public return short static strictfp super switch synchronized
    this throw throws transient try void volatile while true false null var
    yield record sealed permits module open opens exports requires transitive to
    uses provides with when
    """
)

_PYTHON_RESERVED = _words(
    """
    False None True and as assert async await break case class continue def del
    elif else except finally for from global if import in is lambda match
    nonlocal not or pass raise return try type while with yield _
    """
)

_CSHARP_RESERVED = _words(
    """
    abstract as base bool break byte case catch char checked class const
    continue decimal default delegate do double else enum event explicit extern
    false finally fixed float for foreach goto if implicit in int interface
    internal is lock long namespace new null object operator out override params
    private protected public readonly ref return sbyte sealed short sizeof
    stackalloc static string struct switch this throw true try typeof uint ulong
    unchecked unsafe ushort using virtual void volatile while add alias and
    ascending args async await by descending dynamic equals file from get
    global group init into join let managed nameof nint not notnull nuint on or
    orderby partial record remove required scoped select set unmanaged value var
    when where with yield
    """
)

_ECMASCRIPT_RESERVED = _words(
    """
    await break case catch class const continue debugger default delete do else
    enum export extends false finally for function if import in instanceof new
    null return super switch this throw true try typeof var void while with
    yield implements interface let package private protected public static
    """
)

_TYPESCRIPT_RESERVED = _ECMASCRIPT_RESERVED | _words(
    """
    abstract any as asserts bigint boolean constructor declare get infer
    intrinsic is keyof module namespace never number object override readonly
    require set string symbol type undefined unique unknown
    """
)

_GO_RESERVED = _words(
    """
    break default func interface select case defer go map struct chan else goto
    package switch const fallthrough if range type continue for import return var
    """
)

_RUST_RESERVED = _words(
    """
    Self as async await become box break const continue crate do dyn else enum
    extern false final fn for gen if impl in let loop macro match mod move
    override priv pub ref return self static struct super trait true try type
    typeof unsafe unsized use virtual where while yield abstract
    """
)

_CPP_RESERVED = _words(
    """
    alignas alignof and and_eq asm atomic_cancel atomic_commit atomic_noexcept
    auto bitand bitor bool break case catch char char8_t char16_t char32_t class
    compl concept const consteval constexpr constinit const_cast continue
    contract_assert co_await co_return co_yield decltype default delete do
    double dynamic_cast else enum explicit export extern false float for friend
    goto if inline int long mutable namespace new noexcept not not_eq nullptr
    operator or or_eq private protected public reflexpr register reinterpret_cast
    requires return short signed sizeof static static_assert static_cast struct
    switch synchronized template this thread_local throw true try typedef
    typeid typename union unsigned using virtual void volatile wchar_t while xor
    xor_eq
    """
)

_OBJC_RESERVED = _words(
    """
    auto break case char const continue default do double else enum extern float
    for goto if inline int long register restrict return short signed sizeof
    static struct switch typedef union unsigned void volatile while _Alignas
    _Alignof _Atomic _Bool _Complex _Generic _Imaginary _Noreturn
    _Static_assert _Thread_local id Class SEL self super instancetype protocol
    selector encode synchronized autoreleasepool try catch finally throw
    """
)

_SWIFT_RESERVED = _words(
    """
    associatedtype borrowing break case catch class consuming continue
    convenience copy default defer deinit didSet distributed do dynamic else
    enum extension fallthrough false fileprivate final for func get guard if
    import indirect infix init inout internal is isolated lazy let macro
    mutating nil nonisolated nonmutating open operator optional override package
    postfix precedence prefix private protocol public repeat required rethrows
    return self Self sending set some static struct subscript super switch true
    try typealias unowned var weak where while willSet any as async await
    consume consuming discard each inout repeat throws
    """
)


#: PHP's keyword set is *case-insensitive* (`IF`, `If` and `if` are the same
#: token), and so is its function-name namespace. The exact-match `reserved`
#: check below is therefore not sufficient on its own; `_RESERVED_PATTERNS`
#: carries the case-folded form and is what actually enforces the rule. Both are
#: kept: the word list is the readable statement of intent, the pattern is the
#: enforcement. The list is PHP 8.4's reserved words plus the reserved
#: non-keyword type names and the magic constants, which cannot be used as a
#: function name either.
_PHP_RESERVED = _words(
    """
    abstract and array as break callable case catch class clone const continue
    declare default do echo else elseif empty enddeclare endfor endforeach endif
    endswitch endwhile enum extends final finally fn for foreach function global
    goto if implements include include_once instanceof insteadof interface isset
    list match namespace new or print private protected public readonly require
    require_once return static switch throw trait try unset use var while xor
    yield
    int float bool string void iterable object mixed never null false true self
    parent
    __CLASS__ __DIR__ __FILE__ __FUNCTION__ __LINE__ __METHOD__ __NAMESPACE__
    __TRAIT__ __PROPERTY__ __halt_compiler
    """
)


#: Pinned PHP dialect. This string is part of the identifier-policy digest, so
#: it must agree with the version `toolchains._php()` accepts -- changing the
#: pinned interpreter without changing this constant would let two different
#: dialects share one recorded policy digest.
_PHP_DIALECT = "php-8.5.9-strict-types"

#: Kotlin's hard keywords, plus the modifier and soft keywords that cannot
#: appear as a bare declaration name in the positions this engine emits.
#: Kotlin allows almost any of these when backtick-quoted; the engine never
#: emits backticks, so the plain-identifier set is the one that matters.
_KOTLIN_RESERVED = _words(
    """
    as break class continue do else false for fun if in interface is null object
    package return super this throw true try typealias typeof val var when while
    by catch constructor delegate dynamic field file finally get import init
    param property receiver set setparam value where
    abstract actual annotation companion const crossinline data enum expect
    external final infix inline inner internal lateinit noinline open operator
    out override private protected public reified sealed suspend tailrec vararg
    """
)

_KOTLIN_DIALECT = "kotlin-2.4.10-jvm"

_FORBIDDEN: dict[Language, frozenset[str]] = {
    "java": _words(
        """
        Migrated RouteHarness main Math Long Double Boolean String
        ArithmeticException elmosCheckedDiv elmosCheckedMod elmosNonZero
        """
    ),
    "python": _words(
        """
        migrated json math _ELMOS_INTEGER_MIN _ELMOS_INTEGER_MAX
        abs
        _elmos_in_range _elmos_checked_add _elmos_checked_sub
        _elmos_checked_mul _elmos_truncating_div _elmos_truncating_mod
        """
    ),
    "csharp": _words(
        """
        Migrated Program Main Math Console Convert Exception
        DivideByZeroException ElmosNonZero
        """
    ),
    "typescript": _words(
        """
        Math Number Object RangeError TypeError Error migrated actual0
        _elmosRequireSafeInteger _elmosRequireFiniteNumber _elmosRequireNonZero
        """
    ),
    "javascript": _words(
        """
        eval arguments Math Number Object RangeError TypeError Error migrated actual0
        _elmosHarnessSubject
        _elmosRequireSafeInteger _elmosRequireFiniteNumber
        _elmosRequireBoolean _elmosRequireString _elmosRequireNonZero
        """
    ),
    "go": _words(
        """
        main fmt base64 panic int64 float64 bool string error
        elmosIntegerMin elmosCheckedAdd elmosCheckedSub elmosCheckedMul
        elmosCheckedDiv elmosCheckedMod elmosNonZeroFloat64
        """
    ),
    "rust": _words(
        """
        main panic String i64 f64 bool elmos_non_zero_f64 actual_0
        """
    ),
    "cpp": _words(
        """
        main elmos_checked_add elmos_checked_sub elmos_checked_mul
        std
        elmos_checked_div elmos_checked_mod elmos_non_zero
        elmos_harness_fp64_bits elmos_harness_same_fp64
        elmos_harness_fp64 elmos_harness_hex_utf8 actual_0
        """
    ),
    "objc": _words(
        """
        main BOOL YES NO NSInteger NSUInteger int64_t uint64_t nil Nil
        printf memcpy isnan NSUTF8StringEncoding NSObject
        NSString NSException NSData NSMutableString
        ElmosCheckedAdd ElmosCheckedSub ElmosCheckedMul ElmosCheckedDiv
        ElmosCheckedMod ElmosNonZero ElmosHarnessFP64Bits
        ElmosHarnessSameFP64 ElmosHarnessFP64 ElmosHarnessHexUTF8 actual_0
        """
    ),
    "swift": _words(
        """
        main Foundation Int64 Double Bool String fatalError
        elmosNonZero elmosHarnessSameFP64 elmosHarnessFP64
        elmosHarnessHexUTF8 actual0
        """
    ),
    "php": _words(
        """
        migrated fmod intdiv is_int is_nan is_float pack bin2hex printf sprintf
        ArithmeticError DivisionByZeroError TypeError Error Throwable
        PHP_INT_MIN PHP_INT_MAX PHP_INT_SIZE NAN INF
        elmos_checked_add elmos_checked_sub elmos_checked_mul
        elmos_checked_div elmos_checked_mod elmos_non_zero_float
        elmos_harness_fp64 elmos_harness_hex_utf8 elmos_harness_subject actual_0
        """
    ),
    # `Math` and `elmosNonZero` were missing.  Kotlin's emitted file calls
    # `Math.addExact` and declares `private fun elmosNonZero`, both unqualified
    # and both in the same top-level namespace as the migrated functions -- a
    # source function named `elmosNonZero` would be a redeclaration error, and
    # `elmosNonZeroDouble` (which was listed) is a name the emitter never
    # writes.  Java's list, which does cover exactly what Java emits, is the
    # shape to match.  `elmosCheckedAdd`/`Sub`/`Mul` are likewise not emitted
    # today -- kotlin uses `Math.*Exact` for those three -- and are kept only
    # because reserving an unused elmos-prefixed name costs nothing.
    #
    # `maxOf`/`minOf` are the only `kotlin.*` top-level functions whose signature
    # a migrated function can match *exactly* over the canonical types --
    # `maxOf(Long, Long): Long`, `maxOf(Double, Double): Double`. Verified with
    # kotlinc 2.1.21: a file declaring `fun maxOf(a: Long, b: Long): Long`
    # compiles, and an unqualified `maxOf(7L, 2L)` elsewhere in the module then
    # resolves to the migrated function -- 3, not 7 -- with no diagnostic.
    # The rest of the default-imported surface (`run`, `let`, `repeat`,
    # `apply`, ...) takes a lambda, so overload resolution separates it from
    # anything this profile emits and renaming it would only cost readability.
    "kotlin": _words(
        """
        main Math Long Double Boolean String Int Float Short Byte Char Unit Nothing Any
        ArithmeticException Exception RuntimeException Throwable error require check
        elmosCheckedAdd elmosCheckedSub elmosCheckedMul elmosCheckedDiv elmosCheckedMod
        elmosNonZero elmosNonZeroDouble
        elmosHarnessSameFP64 elmosHarnessFP64 elmosHarnessHexUTF8
        actual0
        maxOf minOf
        """
    ),
}

_RESERVED: dict[Language, frozenset[str]] = {
    "java": _JAVA_RESERVED,
    "python": _PYTHON_RESERVED,
    "csharp": _CSHARP_RESERVED,
    "typescript": _TYPESCRIPT_RESERVED,
    "javascript": _ECMASCRIPT_RESERVED,
    "go": _GO_RESERVED,
    "rust": _RUST_RESERVED,
    "cpp": _CPP_RESERVED,
    "objc": _OBJC_RESERVED,
    "swift": _SWIFT_RESERVED,
    "php": _PHP_RESERVED,
    "kotlin": _KOTLIN_RESERVED,
}

_DIALECT: dict[Language, str] = {
    "java": "java-21.0.11",
    "python": "python-3.12.12",
    "csharp": "csharp-roslyn-5.6.0",
    "typescript": "typescript-5.9.2-node-26.0.0-esm-strict",
    "javascript": "javascript-node-26.0.0-es2022-esm-strict-jsdoc",
    "go": "go-1.25.0",
    "rust": "rust-1.89.0-edition-2021",
    "cpp": "cpp-20-apple-clang-21.0.0",
    "objc": "objective-c-c17-apple-clang-21.0.0",
    "swift": "swift-6.3.3",
    "php": _PHP_DIALECT,
    "kotlin": _KOTLIN_DIALECT,
}

_RESERVED_PATTERNS: dict[Language, tuple[str, ...]] = {
    "cpp": (r"^__", r"^_[A-Z]"),
    "objc": (r"^__", r"^_[A-Z]"),
    # The case-folded enforcement of _PHP_RESERVED, plus PHP's reserved
    # `__`-prefixed magic-method namespace.
    "php": (
        r"(?i)\A(?:" + "|".join(sorted(_PHP_RESERVED)) + r")\Z",
        r"^__",
    ),
}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _mapping_digest(value: Any) -> str:
    return _sha256(_canonical_json_bytes(value))


def _require_digest(value: str, label: str) -> None:
    if _DIGEST_RE.fullmatch(value) is None:
        raise RouteError(f"IDENTIFIER_PLAN_DIGEST_INVALID:{label}")


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    observed = set(value)
    if observed != expected:
        raise RouteError(f"IDENTIFIER_PLAN_KEYS_INVALID:{label}")


def _require_logical_path(value: str) -> None:
    if not value or "\\" in value:
        raise RouteError("IDENTIFIER_UNIT_NAMESPACE_LOGICAL_PATH_INVALID")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or value == "." or ".." in path.parts:
        raise RouteError("IDENTIFIER_UNIT_NAMESPACE_LOGICAL_PATH_INVALID")


@dataclass(frozen=True)
class IdentifierUnitNamespace:
    """One immutable namespace identity for generated external symbols.

    Content identity alone cannot distinguish two byte-identical repository
    work units that are linked into the same target library.  Repository
    contexts therefore bind the repository snapshot, work-unit identity,
    logical source path and exact source bytes.  Standalone contexts remain a
    separate, explicit scope so they cannot be replayed as repository proof.
    """

    scope: UnitNamespaceScope
    repository_snapshot_sha256: str | None
    work_unit_id: str | None
    source_logical_path: str
    source_sha256: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": UNIT_NAMESPACE_SCHEMA_VERSION,
            "kind": UNIT_NAMESPACE_KIND,
            "scope": self.scope,
            "repository_snapshot_sha256": self.repository_snapshot_sha256,
            "work_unit_id": self.work_unit_id,
            "source_logical_path": self.source_logical_path,
            "source_sha256": self.source_sha256,
        }

    @property
    def digest(self) -> str:
        return _mapping_digest(self.to_mapping())

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> IdentifierUnitNamespace:
        _require_exact_keys(
            value,
            {
                "schema_version",
                "kind",
                "scope",
                "repository_snapshot_sha256",
                "work_unit_id",
                "source_logical_path",
                "source_sha256",
            },
            "unit_namespace",
        )
        if value.get("schema_version") != UNIT_NAMESPACE_SCHEMA_VERSION or value.get("kind") != UNIT_NAMESPACE_KIND:
            raise RouteError("IDENTIFIER_UNIT_NAMESPACE_PROFILE_INVALID")
        scope = value.get("scope")
        repository_snapshot_sha256 = value.get("repository_snapshot_sha256")
        work_unit_id = value.get("work_unit_id")
        source_logical_path = value.get("source_logical_path")
        source_sha256 = value.get("source_sha256")
        if (
            scope
            not in {
                "standalone-semantic-ir",
                "standalone-artifact",
                "repository-work-unit",
            }
            or not isinstance(source_logical_path, str)
            or not isinstance(source_sha256, str)
        ):
            raise RouteError("IDENTIFIER_UNIT_NAMESPACE_INVALID")
        _require_logical_path(source_logical_path)
        _require_digest(source_sha256, "unit_namespace_source")
        if scope == "repository-work-unit":
            if (
                not isinstance(repository_snapshot_sha256, str)
                or not isinstance(work_unit_id, str)
                or _WORK_UNIT_ID_RE.fullmatch(work_unit_id) is None
            ):
                raise RouteError("IDENTIFIER_REPOSITORY_UNIT_NAMESPACE_INVALID")
            _require_digest(repository_snapshot_sha256, "unit_namespace_repository_snapshot")
        elif repository_snapshot_sha256 is not None or work_unit_id is not None:
            raise RouteError("IDENTIFIER_STANDALONE_UNIT_NAMESPACE_INVALID")
        return cls(
            scope=cast(UnitNamespaceScope, scope),
            repository_snapshot_sha256=repository_snapshot_sha256,
            work_unit_id=work_unit_id,
            source_logical_path=source_logical_path,
            source_sha256=source_sha256,
        )


def standalone_artifact_unit_namespace(
    source_logical_path: str,
    source_sha256: str,
) -> IdentifierUnitNamespace:
    """Build the explicit namespace for one detached standalone artifact."""

    return IdentifierUnitNamespace.from_mapping(
        {
            "schema_version": UNIT_NAMESPACE_SCHEMA_VERSION,
            "kind": UNIT_NAMESPACE_KIND,
            "scope": "standalone-artifact",
            "repository_snapshot_sha256": None,
            "work_unit_id": None,
            "source_logical_path": source_logical_path,
            "source_sha256": source_sha256,
        }
    )


def repository_work_unit_namespace(
    *,
    repository_snapshot_sha256: str,
    work_unit_id: str,
    source_logical_path: str,
    source_sha256: str,
) -> IdentifierUnitNamespace:
    """Build one repository-scoped, independently recomputable namespace."""

    return IdentifierUnitNamespace.from_mapping(
        {
            "schema_version": UNIT_NAMESPACE_SCHEMA_VERSION,
            "kind": UNIT_NAMESPACE_KIND,
            "scope": "repository-work-unit",
            "repository_snapshot_sha256": repository_snapshot_sha256,
            "work_unit_id": work_unit_id,
            "source_logical_path": source_logical_path,
            "source_sha256": source_sha256,
        }
    )


@dataclass(frozen=True)
class IdentifierPolicy:
    target_language: Language
    dialect: str
    reserved: frozenset[str]
    forbidden: frozenset[str]
    reserved_patterns: tuple[str, ...] = ()

    def to_mapping(self) -> dict[str, Any]:
        return {
            "policy_id": POLICY_ID,
            "target_language": self.target_language,
            "dialect": self.dialect,
            "identifier_pattern": _IDENTIFIER_PATTERN,
            "reserved": sorted(self.reserved),
            "forbidden": sorted(self.forbidden),
            "reserved_patterns": list(self.reserved_patterns),
            "candidate_scheme": "exact-then-unit-scoped-content-hash-ascii-v2",
            "candidate_limit": MAX_IDENTIFIER_CANDIDATES,
        }

    @property
    def digest(self) -> str:
        return _mapping_digest(self.to_mapping())


def policy_for_language(target_language: Language) -> IdentifierPolicy:
    try:
        return IdentifierPolicy(
            target_language=target_language,
            dialect=_DIALECT[target_language],
            reserved=_RESERVED[target_language],
            forbidden=_FORBIDDEN[target_language],
            reserved_patterns=_RESERVED_PATTERNS.get(target_language, ()),
        )
    except KeyError as error:
        raise RouteError(f"IDENTIFIER_POLICY_UNSUPPORTED:{target_language}") from error


@dataclass(frozen=True)
class IdentifierCandidate:
    index: int
    name: str
    status: CandidateStatus
    reasons: tuple[str, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "status": self.status,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> IdentifierCandidate:
        _require_exact_keys(value, {"index", "name", "status", "reasons"}, "candidate")
        index = value.get("index")
        name = value.get("name")
        status = value.get("status")
        reasons = value.get("reasons")
        if (
            type(index) is not int
            or not 0 <= index < MAX_IDENTIFIER_CANDIDATES
            or not isinstance(name, str)
            or not name
            or status not in {"REJECTED", "SELECTED"}
            or not isinstance(reasons, list)
            or any(not isinstance(reason, str) or not reason for reason in reasons)
        ):
            raise RouteError("IDENTIFIER_PLAN_CANDIDATE_INVALID")
        return cls(
            index=index,
            name=name,
            status=cast(CandidateStatus, status),
            reasons=tuple(cast(list[str], reasons)),
        )


@dataclass(frozen=True)
class IdentifierBinding:
    binding_id: str
    scope_id: str
    role: BindingRole
    ordinal: int
    source_name: str
    target_name: str
    canonical_type: str | None
    signature_sha256: str | None
    decision: BindingDecision
    selected_candidate_index: int
    candidates_examined: tuple[IdentifierCandidate, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "scope_id": self.scope_id,
            "role": self.role,
            "ordinal": self.ordinal,
            "source_name": self.source_name,
            "target_name": self.target_name,
            "canonical_type": self.canonical_type,
            "signature_sha256": self.signature_sha256,
            "decision": self.decision,
            "selected_candidate_index": self.selected_candidate_index,
            "candidates_examined": [candidate.to_mapping() for candidate in self.candidates_examined],
        }

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> IdentifierBinding:
        _require_exact_keys(
            value,
            {
                "binding_id",
                "scope_id",
                "role",
                "ordinal",
                "source_name",
                "target_name",
                "canonical_type",
                "signature_sha256",
                "decision",
                "selected_candidate_index",
                "candidates_examined",
            },
            "binding",
        )
        binding_id = value.get("binding_id")
        scope_id = value.get("scope_id")
        role = value.get("role")
        ordinal = value.get("ordinal")
        source_name = value.get("source_name")
        target_name = value.get("target_name")
        canonical_type = value.get("canonical_type")
        signature_sha256 = value.get("signature_sha256")
        decision = value.get("decision")
        selected = value.get("selected_candidate_index")
        candidates = value.get("candidates_examined")
        if not isinstance(binding_id, str) or not isinstance(scope_id, str):
            raise RouteError("IDENTIFIER_PLAN_BINDING_ID_INVALID")
        _require_digest(binding_id, "binding_id")
        _require_digest(scope_id, "scope_id")
        if (
            role not in {"function", "parameter", "local"}
            or type(ordinal) is not int
            or ordinal < 0
            or not isinstance(source_name, str)
            or not source_name
            or not isinstance(target_name, str)
            or not target_name
            or canonical_type is not None
            and canonical_type not in types.CANONICAL_TYPES
            or signature_sha256 is not None
            and (not isinstance(signature_sha256, str) or _DIGEST_RE.fullmatch(signature_sha256) is None)
            or decision not in {"PRESERVED", "ALPHA_RENAMED"}
            or type(selected) is not int
            or not isinstance(candidates, list)
            or not candidates
            or any(not isinstance(candidate, dict) for candidate in candidates)
        ):
            raise RouteError("IDENTIFIER_PLAN_BINDING_INVALID")
        parsed_candidates = tuple(
            IdentifierCandidate.from_mapping(cast(dict[str, Any], candidate)) for candidate in candidates
        )
        return cls(
            binding_id=binding_id,
            scope_id=scope_id,
            role=cast(BindingRole, role),
            ordinal=ordinal,
            source_name=source_name,
            target_name=target_name,
            canonical_type=cast(str | None, canonical_type),
            signature_sha256=signature_sha256,
            decision=cast(BindingDecision, decision),
            selected_candidate_index=selected,
            candidates_examined=parsed_candidates,
        )


@dataclass(frozen=True)
class IdentifierPlan:
    policy_id: str
    policy_sha256: str
    target_language: Language
    source_ir_sha256: str
    source_semantic_sha256: str
    unit_namespace: IdentifierUnitNamespace
    candidate_limit: int
    bindings: tuple[IdentifierBinding, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": PLAN_KIND,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "target_language": self.target_language,
            "source_ir_sha256": self.source_ir_sha256,
            "source_semantic_sha256": self.source_semantic_sha256,
            "unit_namespace": self.unit_namespace.to_mapping(),
            "unit_namespace_sha256": self.unit_namespace.digest,
            "candidate_limit": self.candidate_limit,
            "binding_count": len(self.bindings),
            "bindings": [binding.to_mapping() for binding in self.bindings],
        }

    @property
    def digest(self) -> str:
        return _mapping_digest(self.to_mapping())

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> IdentifierPlan:
        _require_exact_keys(
            value,
            {
                "schema_version",
                "kind",
                "policy_id",
                "policy_sha256",
                "target_language",
                "source_ir_sha256",
                "source_semantic_sha256",
                "unit_namespace",
                "unit_namespace_sha256",
                "candidate_limit",
                "binding_count",
                "bindings",
            },
            "plan",
        )
        if value.get("schema_version") != SCHEMA_VERSION or value.get("kind") != PLAN_KIND:
            raise RouteError("IDENTIFIER_PLAN_PROFILE_INVALID")
        target_language = value.get("target_language")
        if target_language not in _DIALECT:
            raise RouteError(f"IDENTIFIER_POLICY_UNSUPPORTED:{target_language}")
        policy_id = value.get("policy_id")
        policy_sha256 = value.get("policy_sha256")
        source_ir_sha256 = value.get("source_ir_sha256")
        source_semantic_sha256 = value.get("source_semantic_sha256")
        unit_namespace_value = value.get("unit_namespace")
        unit_namespace_sha256 = value.get("unit_namespace_sha256")
        candidate_limit = value.get("candidate_limit")
        binding_count = value.get("binding_count")
        bindings = value.get("bindings")
        if (
            policy_id != POLICY_ID
            or not isinstance(policy_sha256, str)
            or not isinstance(source_ir_sha256, str)
            or not isinstance(source_semantic_sha256, str)
            or not isinstance(unit_namespace_value, dict)
            or not isinstance(unit_namespace_sha256, str)
            or candidate_limit != MAX_IDENTIFIER_CANDIDATES
            or type(binding_count) is not int
            or not isinstance(bindings, list)
            or binding_count != len(bindings)
            or any(not isinstance(binding, dict) for binding in bindings)
        ):
            raise RouteError("IDENTIFIER_PLAN_INVALID")
        _require_digest(policy_sha256, "policy")
        _require_digest(source_ir_sha256, "source_ir")
        _require_digest(source_semantic_sha256, "source_semantic")
        _require_digest(unit_namespace_sha256, "unit_namespace")
        unit_namespace = IdentifierUnitNamespace.from_mapping(cast(dict[str, Any], unit_namespace_value))
        if unit_namespace_sha256 != unit_namespace.digest:
            raise RouteError("IDENTIFIER_UNIT_NAMESPACE_DIGEST_MISMATCH")
        return cls(
            policy_id=policy_id,
            policy_sha256=policy_sha256,
            target_language=cast(Language, target_language),
            source_ir_sha256=source_ir_sha256,
            source_semantic_sha256=source_semantic_sha256,
            unit_namespace=unit_namespace,
            candidate_limit=candidate_limit,
            bindings=tuple(IdentifierBinding.from_mapping(cast(dict[str, Any], binding)) for binding in bindings),
        )


def identifier_plan_bytes(plan: IdentifierPlan) -> bytes:
    """Return the one canonical persisted representation of a plan."""

    return _canonical_json_bytes(plan.to_mapping())


def _source_ir_digest(ir: SemanticIR) -> str:
    return _mapping_digest(ir.to_mapping())


def _source_semantic_digest(ir: SemanticIR) -> str:
    return _mapping_digest(ir.semantic_mapping())


def _standalone_semantic_ir_unit_namespace(ir: SemanticIR) -> IdentifierUnitNamespace:
    return IdentifierUnitNamespace.from_mapping(
        {
            "schema_version": UNIT_NAMESPACE_SCHEMA_VERSION,
            "kind": UNIT_NAMESPACE_KIND,
            "scope": "standalone-semantic-ir",
            "repository_snapshot_sha256": None,
            "work_unit_id": None,
            # Analyzer snapshots may expose an absolute temporary path and a
            # build-specific analyzer version.  Neither is a link namespace.
            # Standalone semantic calls therefore bind the logical basename
            # plus canonical semantic content; repository calls must supply
            # the stronger repository-work-unit context explicitly.
            "source_logical_path": PurePosixPath(ir.source_file).name,
            "source_sha256": _source_semantic_digest(ir),
        }
    )


def _binding_id(
    *,
    source_semantic_sha256: str,
    unit_namespace_sha256: str,
    scope_id: str,
    role: BindingRole,
    ordinal: int,
    source_name: str,
    canonical_type: str | None,
    signature_sha256: str | None,
) -> str:
    return _mapping_digest(
        {
            "source_semantic_sha256": source_semantic_sha256,
            "unit_namespace_sha256": unit_namespace_sha256,
            "scope_id": scope_id,
            "role": role,
            "ordinal": ordinal,
            "source_name": source_name,
            "canonical_type": canonical_type,
            "signature_sha256": signature_sha256,
        }
    )


def _generated_candidate_name(
    *,
    policy: IdentifierPolicy,
    binding_id: str,
    role: BindingRole,
    ordinal: int,
    candidate_index: int,
) -> str:
    digest = hashlib.sha256(
        _canonical_json_bytes(
            {
                "policy_id": POLICY_ID,
                "policy_sha256": policy.digest,
                "target_language": policy.target_language,
                "binding_id": binding_id,
                "role": role,
                "ordinal": ordinal,
                "candidate_index": candidate_index,
            }
        )
    ).hexdigest()[:16]
    if role == "function":
        return f"elmos_fn_{digest}"
    # `p` and `l` are kept apart so a generated name says which binder it came
    # from; a local and a parameter share one target scope and would otherwise
    # be indistinguishable in the emitted file.
    return f"elmos_{'p' if role == 'parameter' else 'l'}{ordinal:03d}_{digest}"


def _candidate_reasons(
    candidate: str,
    policy: IdentifierPolicy,
    occupied: dict[str, str],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if _IDENTIFIER_RE.fullmatch(candidate) is None:
        reasons.append("INVALID_TARGET_IDENTIFIER")
    if candidate in policy.reserved:
        reasons.append("TARGET_RESERVED")
    if candidate in policy.forbidden:
        reasons.append("POLICY_FORBIDDEN")
    reasons.extend(
        f"TARGET_RESERVED_PATTERN:{pattern}"
        for pattern in policy.reserved_patterns
        if re.search(pattern, candidate) is not None
    )
    if candidate in occupied:
        reasons.append(f"SCOPE_COLLISION:{occupied[candidate]}")
    return tuple(reasons)


def _allocate_binding(
    *,
    policy: IdentifierPolicy,
    source_semantic_sha256: str,
    unit_namespace_sha256: str,
    scope_id: str,
    role: BindingRole,
    ordinal: int,
    source_name: str,
    canonical_type: str | None,
    signature_sha256: str | None,
    occupied: dict[str, str],
) -> IdentifierBinding:
    binding_id = _binding_id(
        source_semantic_sha256=source_semantic_sha256,
        unit_namespace_sha256=unit_namespace_sha256,
        scope_id=scope_id,
        role=role,
        ordinal=ordinal,
        source_name=source_name,
        canonical_type=canonical_type,
        signature_sha256=signature_sha256,
    )
    examined: list[IdentifierCandidate] = []
    for candidate_index in range(MAX_IDENTIFIER_CANDIDATES):
        candidate = (
            source_name
            if candidate_index == 0
            else _generated_candidate_name(
                policy=policy,
                binding_id=binding_id,
                role=role,
                ordinal=ordinal,
                candidate_index=candidate_index,
            )
        )
        reasons = list(_candidate_reasons(candidate, policy, occupied))
        if role == "function" and policy.target_language == "php":
            # PHP resolves function names case-insensitively, so `Total` and
            # `total` are one symbol even though `$Total` and `$total` are two
            # distinct variables. Only the function role folds; folding the
            # parameter role too would rename identifiers PHP keeps distinct.
            folded = candidate.lower()
            collision = next(
                (owner for name, owner in occupied.items() if name != candidate and name.lower() == folded),
                None,
            )
            if collision is not None:
                reasons.append(f"TARGET_CASE_INSENSITIVE_SCOPE_COLLISION:{collision}")
        if candidate_index == 0:
            if role == "function" and policy.target_language in {"cpp", "objc"}:
                reasons.append("TARGET_OPEN_GLOBAL_SYMBOL_NAMESPACE")
            elif role == "parameter" and policy.target_language in {"cpp", "objc"}:
                reasons.append("TARGET_OPEN_PREPROCESSOR_IDENTIFIER_NAMESPACE")
            elif role == "function" and policy.target_language in {"java", "csharp", "swift"}:
                reasons.append("TARGET_RUNTIME_FUNCTION_NAMESPACE")
        reason_tuple = tuple(reasons)
        status: CandidateStatus = "REJECTED" if reason_tuple else "SELECTED"
        examined.append(
            IdentifierCandidate(
                index=candidate_index,
                name=candidate,
                status=status,
                reasons=reason_tuple,
            )
        )
        if reason_tuple:
            continue
        occupied[candidate] = binding_id
        return IdentifierBinding(
            binding_id=binding_id,
            scope_id=scope_id,
            role=role,
            ordinal=ordinal,
            source_name=source_name,
            target_name=candidate,
            canonical_type=canonical_type,
            signature_sha256=signature_sha256,
            decision="PRESERVED" if candidate_index == 0 else "ALPHA_RENAMED",
            selected_candidate_index=candidate_index,
            candidates_examined=tuple(examined),
        )
    raise RouteError(f"IDENTIFIER_CANDIDATE_EXHAUSTED:{role}:{binding_id}")


def plan_identifiers(
    ir: SemanticIR,
    target_language: Language,
    *,
    unit_namespace: IdentifierUnitNamespace | None = None,
) -> IdentifierPlan:
    """Create the exact bounded name plan for one immutable semantic IR."""

    if ir.diagnostics:
        raise RouteError("IDENTIFIER_SOURCE_DIAGNOSTICS_PRESENT")
    types.check(ir)
    policy = policy_for_language(target_language)
    source_ir_sha256 = _source_ir_digest(ir)
    source_semantic_sha256 = _source_semantic_digest(ir)
    selected_namespace = unit_namespace or _standalone_semantic_ir_unit_namespace(ir)
    # Frozen dataclasses can still be instantiated directly. Round-trip the
    # strict mapping before it participates in any binding identifier.
    selected_namespace = IdentifierUnitNamespace.from_mapping(selected_namespace.to_mapping())
    module_scope_id = _mapping_digest(
        {
            "kind": "elmos.identifier-module-scope",
            "source_semantic_sha256": source_semantic_sha256,
            "unit_namespace_sha256": selected_namespace.digest,
        }
    )
    source_function_names = [function.name for function in ir.functions]
    if len(set(source_function_names)) != len(source_function_names):
        raise RouteError("IDENTIFIER_SOURCE_FUNCTION_DUPLICATED")

    bindings: list[IdentifierBinding] = []
    function_bindings: list[IdentifierBinding] = []
    function_occupied: dict[str, str] = {}
    for ordinal, function in enumerate(ir.functions):
        signature_sha256 = _mapping_digest(function.signature_mapping())
        binding = _allocate_binding(
            policy=policy,
            source_semantic_sha256=source_semantic_sha256,
            unit_namespace_sha256=selected_namespace.digest,
            scope_id=module_scope_id,
            role="function",
            ordinal=ordinal,
            source_name=function.name,
            canonical_type=None,
            signature_sha256=signature_sha256,
            occupied=function_occupied,
        )
        function_bindings.append(binding)
        bindings.append(binding)

    for function, function_binding in zip(ir.functions, function_bindings, strict=True):
        # Parameters and locals share one `occupied` map because they share one
        # scope in the target: a local that took a parameter's target name
        # would shadow it in every brace language and be a redeclaration error
        # in several. Allocating them against the same map is what makes the
        # collision impossible rather than merely unlikely.
        parameter_occupied: dict[str, str] = {}
        for ordinal, parameter in enumerate(function.parameters):
            bindings.append(
                _allocate_binding(
                    policy=policy,
                    source_semantic_sha256=source_semantic_sha256,
                    unit_namespace_sha256=selected_namespace.digest,
                    scope_id=function_binding.binding_id,
                    role="parameter",
                    ordinal=ordinal,
                    source_name=parameter.name,
                    canonical_type=parameter.type,
                    signature_sha256=None,
                    occupied=parameter_occupied,
                )
            )
        for ordinal, local in enumerate(_local_bindings_in_order(function.body)):
            if local.name is None or local.declared_type is None:
                raise RouteError("IDENTIFIER_SOURCE_LOCAL_INVALID")
            bindings.append(
                _allocate_binding(
                    policy=policy,
                    source_semantic_sha256=source_semantic_sha256,
                    unit_namespace_sha256=selected_namespace.digest,
                    scope_id=function_binding.binding_id,
                    role="local",
                    ordinal=ordinal,
                    source_name=local.name,
                    canonical_type=local.declared_type,
                    signature_sha256=None,
                    occupied=parameter_occupied,
                )
            )

    return IdentifierPlan(
        policy_id=POLICY_ID,
        policy_sha256=policy.digest,
        target_language=target_language,
        source_ir_sha256=source_ir_sha256,
        source_semantic_sha256=source_semantic_sha256,
        unit_namespace=selected_namespace,
        candidate_limit=MAX_IDENTIFIER_CANDIDATES,
        bindings=tuple(bindings),
    )


def validate_identifier_plan(
    ir: SemanticIR,
    plan: IdentifierPlan,
    *,
    expected_unit_namespace: IdentifierUnitNamespace | None = None,
) -> None:
    """Recompute a plan; no recorded candidate or collision reason is trusted."""

    policy = policy_for_language(plan.target_language)
    if plan.policy_id != POLICY_ID or plan.policy_sha256 != policy.digest:
        raise RouteError("IDENTIFIER_PLAN_POLICY_MISMATCH")
    if plan.source_ir_sha256 != _source_ir_digest(ir) or plan.source_semantic_sha256 != _source_semantic_digest(ir):
        raise RouteError("IDENTIFIER_PLAN_SOURCE_BINDING_MISMATCH")
    if expected_unit_namespace is not None and plan.unit_namespace.to_mapping() != expected_unit_namespace.to_mapping():
        raise RouteError("IDENTIFIER_PLAN_UNIT_NAMESPACE_MISMATCH")
    expected = plan_identifiers(ir, plan.target_language, unit_namespace=plan.unit_namespace)
    if plan.to_mapping() != expected.to_mapping():
        raise RouteError("IDENTIFIER_PLAN_RECOMPUTATION_MISMATCH")


def _function_binding(plan: IdentifierPlan, function_ordinal: int, function: Function) -> IdentifierBinding:
    matches = [
        binding for binding in plan.bindings if binding.role == "function" and binding.ordinal == function_ordinal
    ]
    if len(matches) != 1:
        raise RouteError("IDENTIFIER_FUNCTION_BINDING_INCOMPLETE")
    binding = matches[0]
    if (
        binding.source_name != function.name
        or binding.canonical_type is not None
        or binding.signature_sha256 != _mapping_digest(function.signature_mapping())
    ):
        raise RouteError("IDENTIFIER_FUNCTION_BINDING_MISMATCH")
    return binding


def _parameter_bindings(
    plan: IdentifierPlan,
    function_binding: IdentifierBinding,
    function: Function,
) -> tuple[IdentifierBinding, ...]:
    matches = sorted(
        (
            binding
            for binding in plan.bindings
            if binding.role == "parameter" and binding.scope_id == function_binding.binding_id
        ),
        key=lambda binding: binding.ordinal,
    )
    if len(matches) != len(function.parameters):
        raise RouteError("IDENTIFIER_PARAMETER_BINDING_INCOMPLETE")
    for ordinal, (binding, parameter) in enumerate(zip(matches, function.parameters, strict=True)):
        if (
            binding.ordinal != ordinal
            or binding.source_name != parameter.name
            or binding.canonical_type != parameter.type
            or binding.signature_sha256 is not None
        ):
            raise RouteError("IDENTIFIER_PARAMETER_BINDING_MISMATCH")
    return tuple(matches)


def _local_bindings_in_order(statements: tuple[Statement, ...]) -> list[Statement]:
    """Every `let` in one function, in the order a reader meets them.

    Depth-first in statement order -- an `if`'s condition cannot bind, so a
    branch's bindings follow the branch. The order is what gives each local a
    stable ordinal, and therefore a stable generated name across runs.
    """
    found: list[Statement] = []
    for statement in statements:
        if statement.kind == "let":
            found.append(statement)
        elif statement.kind == "if":
            found.extend(_local_bindings_in_order(statement.then_body))
            found.extend(_local_bindings_in_order(statement.else_body))
    return found


def _rename_expression(expression: Expression, names: dict[str, str], role: str) -> Expression:
    if expression.kind == "name":
        source_name = str(expression.value)
        target_name = names.get(source_name)
        if target_name is None:
            raise RouteError(f"IDENTIFIER_{role}_REFERENCE_UNMAPPED:{source_name}")
        return replace(expression, value=target_name)
    if expression.kind == "literal":
        return expression
    if expression.kind == "binary" and expression.left is not None and expression.right is not None:
        return replace(
            expression,
            left=_rename_expression(expression.left, names, role),
            right=_rename_expression(expression.right, names, role),
        )
    raise RouteError(f"IDENTIFIER_{role}_EXPRESSION_UNSUPPORTED:{expression.kind}")


def _rename_statements(
    statements: tuple[Statement, ...],
    names: dict[str, str],
    role: str,
) -> tuple[Statement, ...]:
    result: list[Statement] = []
    for statement in statements:
        if statement.kind == "let" and statement.expression is not None and statement.name is not None:
            # The initializer is renamed under the names visible *before* this
            # binding; the binding becomes visible only afterwards.
            renamed = _rename_expression(statement.expression, names, role)
            target_name = names.get(_LOCAL_BINDER_PREFIX + statement.name)
            if target_name is None:
                raise RouteError(f"IDENTIFIER_{role}_LOCAL_UNMAPPED:{statement.name}")
            names[statement.name] = target_name
            result.append(replace(statement, name=target_name, expression=renamed))
            continue
        if statement.kind == "return" and statement.expression is not None:
            result.append(
                replace(
                    statement,
                    expression=_rename_expression(statement.expression, names, role),
                )
            )
        elif statement.kind == "if" and statement.condition is not None:
            result.append(
                replace(
                    statement,
                    condition=_rename_expression(statement.condition, names, role),
                    then_body=_rename_statements(statement.then_body, dict(names), role),
                    else_body=_rename_statements(statement.else_body, dict(names), role),
                )
            )
        else:
            raise RouteError(f"IDENTIFIER_{role}_STATEMENT_UNSUPPORTED:{statement.kind}")
    return tuple(result)


def _local_bindings(
    plan: IdentifierPlan,
    function_binding: IdentifierBinding,
    function: Function,
) -> tuple[IdentifierBinding, ...]:
    matches = sorted(
        (
            binding
            for binding in plan.bindings
            if binding.role == "local" and binding.scope_id == function_binding.binding_id
        ),
        key=lambda binding: binding.ordinal,
    )
    locals_in_order = _local_bindings_in_order(function.body)
    if len(matches) != len(locals_in_order):
        raise RouteError("IDENTIFIER_LOCAL_BINDING_INCOMPLETE")
    for ordinal, (binding, local) in enumerate(zip(matches, locals_in_order, strict=True)):
        if (
            binding.ordinal != ordinal
            or binding.source_name != local.name
            or binding.canonical_type != local.declared_type
            or binding.signature_sha256 is not None
        ):
            raise RouteError("IDENTIFIER_LOCAL_BINDING_MISMATCH")
    return tuple(matches)


def _target_function_view_validated(
    function: Function,
    function_ordinal: int,
    plan: IdentifierPlan,
) -> Function:
    function_binding = _function_binding(plan, function_ordinal, function)
    parameter_bindings = _parameter_bindings(plan, function_binding, function)
    local_bindings = _local_bindings(plan, function_binding, function)
    name_map = {
        parameter.name: binding.target_name
        for parameter, binding in zip(function.parameters, parameter_bindings, strict=True)
    }
    name_map.update(
        {
            _LOCAL_BINDER_PREFIX + str(local.name): binding.target_name
            for local, binding in zip(_local_bindings_in_order(function.body), local_bindings, strict=True)
        }
    )
    target = replace(
        function,
        name=function_binding.target_name,
        parameters=tuple(
            replace(parameter, name=binding.target_name)
            for parameter, binding in zip(function.parameters, parameter_bindings, strict=True)
        ),
        body=_rename_statements(function.body, name_map, "SOURCE"),
    )
    types.check_function(target)
    return target


def target_function_view(
    source_ir: SemanticIR,
    function: Function,
    plan: IdentifierPlan,
) -> Function:
    """Return a target-facing Function after recomputing the whole plan."""

    validate_identifier_plan(source_ir, plan)
    ordinals = [index for index, item in enumerate(source_ir.functions) if item == function]
    if len(ordinals) != 1:
        raise RouteError("IDENTIFIER_SOURCE_FUNCTION_NOT_UNIQUE")
    return _target_function_view_validated(function, ordinals[0], plan)


def target_ir_view(source_ir: SemanticIR, plan: IdentifierPlan) -> SemanticIR:
    """Return one emitter-facing IR while preserving source provenance."""

    validate_identifier_plan(source_ir, plan)
    return replace(
        source_ir,
        functions=tuple(
            _target_function_view_validated(function, ordinal, plan)
            for ordinal, function in enumerate(source_ir.functions)
        ),
    )


def alpha_normalize_target(
    source_ir: SemanticIR,
    raw_target_ir: SemanticIR,
    plan: IdentifierPlan,
) -> SemanticIR:
    """Verify the raw target binders and reverse only the recorded alpha map."""

    validate_identifier_plan(source_ir, plan)
    if raw_target_ir.source_language != plan.target_language:
        raise RouteError("IDENTIFIER_TARGET_LANGUAGE_MISMATCH")
    if raw_target_ir.diagnostics:
        raise RouteError("IDENTIFIER_TARGET_DIAGNOSTICS_PRESENT")
    expected_views = tuple(
        _target_function_view_validated(function, ordinal, plan) for ordinal, function in enumerate(source_ir.functions)
    )
    raw_index: dict[str, Function] = {}
    for function in raw_target_ir.functions:
        if function.name in raw_index:
            raise RouteError("IDENTIFIER_RAW_TARGET_FUNCTION_DUPLICATED")
        raw_index[function.name] = function
    expected_names = {function.name for function in expected_views}
    if set(raw_index) != expected_names:
        raise RouteError("IDENTIFIER_RAW_TARGET_FUNCTION_SET_MISMATCH")

    normalized_functions: list[Function] = []
    for source_function, expected_view in zip(source_ir.functions, expected_views, strict=True):
        raw_function = raw_index[expected_view.name]
        if raw_function.return_type != source_function.return_type:
            raise RouteError("IDENTIFIER_RAW_TARGET_RETURN_TYPE_MISMATCH")
        if len(raw_function.parameters) != len(source_function.parameters):
            raise RouteError("IDENTIFIER_RAW_TARGET_PARAMETER_COUNT_MISMATCH")
        reverse_names: dict[str, str] = {}
        normalized_parameters = []
        for source_parameter, expected_parameter, raw_parameter in zip(
            source_function.parameters,
            expected_view.parameters,
            raw_function.parameters,
            strict=True,
        ):
            if raw_parameter.name != expected_parameter.name or raw_parameter.type != source_parameter.type:
                raise RouteError("IDENTIFIER_RAW_TARGET_PARAMETER_BINDING_MISMATCH")
            if raw_parameter.name in reverse_names:
                raise RouteError("IDENTIFIER_RAW_TARGET_PARAMETER_DUPLICATED")
            reverse_names[raw_parameter.name] = source_parameter.name
            normalized_parameters.append(replace(raw_parameter, name=source_parameter.name))
        normalized = replace(
            raw_function,
            name=source_function.name,
            parameters=tuple(normalized_parameters),
            body=_rename_statements(raw_function.body, reverse_names, "TARGET"),
        )
        types.check_function(normalized)
        normalized_functions.append(normalized)
    return replace(raw_target_ir, functions=tuple(normalized_functions))

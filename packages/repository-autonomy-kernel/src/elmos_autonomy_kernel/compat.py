"""Contract compatibility: source-level API diff, wire-level tag diff, policy decision.

The engine owns one judgement — *is this change safe for someone who already depends on
the old contract* — and it makes that judgement with the variance rules the right way
round.  Narrowing a **parameter** type is breaking (an existing caller's argument may no
longer be accepted); widening one is not.  For a **return** type it is the mirror image:
narrowing is safe, widening is breaking (an existing caller's handling may not cover the
new values).  Getting this backwards produces an engine that confidently blesses breaking
changes, which is worse than having no engine.

The default posture is that a removal, or anything the type lattice cannot relate, is
BREAKING until proven otherwise.  "We could not classify it" and "it is fine" are
different answers and must not render identically.

The wire surface exists because a source-level diff is structurally blind to the failure
that actually corrupts production data: retiring field tag 4 and later handing tag 4 to a
different field.  Old encoders keep emitting the old meaning under that tag and new
decoders accept it.  ``WIRE_TAG_REUSE`` is the one classification no policy in this module
can waive.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .contracts import (
    Status,
    digest,
    reject_unknown_fields,
    require_bool,
    require_int,
    require_mapping,
    require_str,
)
from .errors import Category, KernelError, register_codes
from .registry import register

__all__ = [
    "ParamKind",
    "Visibility",
    "ChangeKind",
    "Severity",
    "ParamSpec",
    "Declaration",
    "ApiSurface",
    "WireField",
    "WireMessage",
    "WireSurface",
    "TypeLattice",
    "DEFAULT_LATTICE",
    "Change",
    "ApiDiff",
    "Policy",
    "POLICIES",
    "policy_for",
    "CompatibilityDecision",
    "DeprecationStep",
    "DeprecationPlan",
    "diff",
    "diff_wire",
    "merge_diffs",
    "decide",
    "deprecation_plan",
    "handle",
]

register_codes(
    Category.SEMANTIC,
    "COMPAT_DUPLICATE_DECLARATION",
    "COMPAT_MALFORMED_SURFACE",
    "COMPAT_UNKNOWN_POLICY",
    "COMPAT_UNKNOWN_PARAM_KIND",
    "COMPAT_DUPLICATE_WIRE_TAG",
    "WIRE_TAG_REUSE",
    # Codes named by skills/contract-compatibility-engine/SKILL.md.
    "BREAKING_CHANGE",
    "UNKNOWN_CONSUMER",
    "DATA_MIGRATION_UNSAFE",
    "CONTRACT_TEST_FAILED",
)


class ParamKind(StrEnum):
    """How a caller can pass an argument."""

    POSITIONAL = "positional"
    KEYWORD = "keyword"
    VARIADIC = "variadic"


class Visibility(StrEnum):
    """Whether a declaration is part of the promised contract."""

    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"


class Severity(StrEnum):
    """What a change does to an existing consumer.

    ``RISKY`` is not a softer ``BREAKING``; it is "this is safe only under an assumption
    we have not verified" (typically: that every consumer is known).  A policy decides
    whether an unverified assumption blocks, and the strict policy says it does.
    """

    BREAKING = "BREAKING"
    RISKY = "RISKY"
    COMPATIBLE = "COMPATIBLE"


class ChangeKind(StrEnum):
    """Every classification this engine can produce.

    ``UNCLASSIFIED`` is a real member rather than an internal fallback: an engine that
    cannot express "I do not know what this is" ends up expressing "it is fine".
    """

    ADDED = "ADDED"
    REMOVED = "REMOVED"
    KIND_CHANGED = "KIND_CHANGED"
    VISIBILITY_REDUCED = "VISIBILITY_REDUCED"
    VISIBILITY_INCREASED = "VISIBILITY_INCREASED"
    DEPRECATED = "DEPRECATED"
    UNDEPRECATED = "UNDEPRECATED"
    SINCE_VERSION_CHANGED = "SINCE_VERSION_CHANGED"
    PARAM_ADDED_REQUIRED = "PARAM_ADDED_REQUIRED"
    PARAM_ADDED_OPTIONAL = "PARAM_ADDED_OPTIONAL"
    PARAM_REMOVED = "PARAM_REMOVED"
    PARAM_RENAMED = "PARAM_RENAMED"
    PARAM_REORDERED = "PARAM_REORDERED"
    PARAM_KIND_CHANGED = "PARAM_KIND_CHANGED"
    PARAM_DEFAULT_ADDED = "PARAM_DEFAULT_ADDED"
    PARAM_DEFAULT_REMOVED = "PARAM_DEFAULT_REMOVED"
    PARAM_TYPE_NARROWED = "PARAM_TYPE_NARROWED"
    PARAM_TYPE_WIDENED = "PARAM_TYPE_WIDENED"
    PARAM_TYPE_UNRELATED = "PARAM_TYPE_UNRELATED"
    RETURN_TYPE_NARROWED = "RETURN_TYPE_NARROWED"
    RETURN_TYPE_WIDENED = "RETURN_TYPE_WIDENED"
    RETURN_TYPE_UNRELATED = "RETURN_TYPE_UNRELATED"
    WIRE_FIELD_ADDED_OPTIONAL = "WIRE_FIELD_ADDED_OPTIONAL"
    WIRE_FIELD_ADDED_REQUIRED = "WIRE_FIELD_ADDED_REQUIRED"
    WIRE_FIELD_REMOVED = "WIRE_FIELD_REMOVED"
    WIRE_FIELD_REMOVED_UNRESERVED = "WIRE_FIELD_REMOVED_UNRESERVED"
    WIRE_TAG_CHANGED = "WIRE_TAG_CHANGED"
    WIRE_TAG_REUSE = "WIRE_TAG_REUSE"
    WIRE_TYPE_INCOMPATIBLE = "WIRE_TYPE_INCOMPATIBLE"
    WIRE_TYPE_COMPATIBLE = "WIRE_TYPE_COMPATIBLE"
    WIRE_MESSAGE_ADDED = "WIRE_MESSAGE_ADDED"
    WIRE_MESSAGE_REMOVED = "WIRE_MESSAGE_REMOVED"
    UNCLASSIFIED = "UNCLASSIFIED"


#: Severity by kind.  Anything absent is BREAKING, which is the point of the lookup being
#: a ``.get`` with a BREAKING default rather than an exhaustive match.
_SEVERITY: Mapping[ChangeKind, Severity] = {
    ChangeKind.ADDED: Severity.COMPATIBLE,
    ChangeKind.PARAM_ADDED_OPTIONAL: Severity.COMPATIBLE,
    ChangeKind.PARAM_TYPE_WIDENED: Severity.COMPATIBLE,
    ChangeKind.PARAM_DEFAULT_ADDED: Severity.COMPATIBLE,
    ChangeKind.RETURN_TYPE_NARROWED: Severity.COMPATIBLE,
    ChangeKind.VISIBILITY_INCREASED: Severity.COMPATIBLE,
    ChangeKind.DEPRECATED: Severity.COMPATIBLE,
    ChangeKind.SINCE_VERSION_CHANGED: Severity.COMPATIBLE,
    ChangeKind.WIRE_FIELD_ADDED_OPTIONAL: Severity.COMPATIBLE,
    ChangeKind.WIRE_TYPE_COMPATIBLE: Severity.COMPATIBLE,
    ChangeKind.WIRE_MESSAGE_ADDED: Severity.COMPATIBLE,
    # Safe only if every consumer is known.
    ChangeKind.UNDEPRECATED: Severity.RISKY,
    ChangeKind.WIRE_FIELD_REMOVED: Severity.RISKY,
    ChangeKind.PARAM_KIND_CHANGED: Severity.RISKY,
}


# --- surfaces ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParamSpec:
    """One parameter of a declaration."""

    name: str
    type: str
    has_default: bool = False
    kind: ParamKind = ParamKind.POSITIONAL

    def to_payload(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.type, "hasDefault": self.has_default,
                "kind": str(self.kind)}


@dataclass(frozen=True, slots=True)
class Declaration:
    """One named element of an API surface."""

    name: str
    kind: str
    params: tuple[ParamSpec, ...] = ()
    return_type: str = "void"
    visibility: Visibility = Visibility.PUBLIC
    since_version: str = "0.0.0"
    deprecated: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind,
            "params": [param.to_payload() for param in self.params],
            "returnType": self.return_type, "visibility": str(self.visibility),
            "sinceVersion": self.since_version, "deprecated": self.deprecated,
        }

    @property
    def positional_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.params if p.kind is ParamKind.POSITIONAL)


@dataclass(frozen=True, slots=True)
class ApiSurface:
    """A set of uniquely named declarations.

    A duplicate name is refused rather than resolved by last-write-wins: the diff would
    otherwise silently compare against whichever copy happened to survive.
    """

    declarations: tuple[Declaration, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for declaration in self.declarations:
            if declaration.name in seen:
                raise KernelError(
                    code="COMPAT_DUPLICATE_DECLARATION",
                    message=f"declaration {declaration.name!r} appears twice in one surface",
                    recommended_action="deduplicate the surface before diffing",
                )
            seen.add(declaration.name)

    def by_name(self) -> dict[str, Declaration]:
        return {declaration.name: declaration for declaration in self.declarations}

    def to_payload(self) -> dict[str, Any]:
        return {"declarations": [d.to_payload() for d in sorted(self.declarations,
                                                                key=lambda d: d.name)]}

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class WireField:
    """A protobuf-ish field: identity on the wire is the tag, not the name."""

    name: str
    tag: int
    type: str
    required: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {"name": self.name, "tag": self.tag, "type": self.type,
                "required": self.required}


@dataclass(frozen=True, slots=True)
class WireMessage:
    """A message plus the tags it has retired.

    ``reserved_tags`` is what makes tag reuse detectable at all once the old field is gone
    from the schema: without it, "tag 4 used to mean something else" is information the
    diff simply does not have.
    """

    name: str
    fields: tuple[WireField, ...] = ()
    reserved_tags: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        seen: set[int] = set()
        for wire_field in self.fields:
            if wire_field.tag in seen:
                raise KernelError(
                    code="COMPAT_DUPLICATE_WIRE_TAG",
                    message=f"{self.name}: tag {wire_field.tag} is assigned twice",
                    recommended_action="assign each field a unique tag",
                )
            if wire_field.tag in self.reserved_tags:
                raise KernelError(
                    code="WIRE_TAG_REUSE",
                    message=f"{self.name}: tag {wire_field.tag} is both reserved and assigned",
                    recommended_action="pick an unreserved tag",
                )
            seen.add(wire_field.tag)

    def by_tag(self) -> dict[int, WireField]:
        return {wire_field.tag: wire_field for wire_field in self.fields}


@dataclass(frozen=True, slots=True)
class WireSurface:
    """A set of wire messages."""

    messages: tuple[WireMessage, ...] = ()

    def by_name(self) -> dict[str, WireMessage]:
        return {message.name: message for message in self.messages}


#: Wire-level type changes that keep the same encoding.  Anything outside this table is
#: incompatible; the table is an allow-list rather than a deny-list on purpose.
_WIRE_COMPATIBLE: frozenset[tuple[str, str]] = frozenset({
    ("int32", "int64"), ("uint32", "uint64"), ("sint32", "sint64"),
    ("int32", "uint32"), ("int64", "uint64"), ("bytes", "string"), ("string", "bytes"),
})


# --- types -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TypeLattice:
    """A declared subtype relation, plus a top (``any``) and a bottom (``never``).

    Two type names with no declared relation are *unrelated*, not equal and not
    incomparable-therefore-fine.  Unrelated is reported and treated as breaking.
    """

    edges: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    top: str = "any"
    bottom: str = "never"

    def is_subtype(self, sub: str, sup: str) -> bool:
        if sub == sup or sup == self.top or sub == self.bottom:
            return True
        seen: set[str] = set()
        stack = [sub]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            for parent in self.edges.get(current, ()):
                if parent == sup:
                    return True
                stack.append(parent)
        return False

    def relate(self, before: str, after: str) -> str:
        """``same`` / ``narrowed`` / ``widened`` / ``unrelated`` going before -> after."""

        if before == after:
            return "same"
        after_is_sub = self.is_subtype(after, before)
        before_is_sub = self.is_subtype(before, after)
        if after_is_sub and before_is_sub:
            return "same"
        if after_is_sub:
            return "narrowed"
        if before_is_sub:
            return "widened"
        return "unrelated"


DEFAULT_LATTICE = TypeLattice(edges={
    "bool": ("int",),
    "int": ("number",),
    "float": ("number",),
    "number": ("any",),
    "str": ("any",),
    "PositiveInt": ("int",),
    "NonEmptyStr": ("str",),
})


# --- diff --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Change:
    """One classified difference."""

    symbol: str
    kind: ChangeKind
    severity: Severity
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "kind": str(self.kind),
                "severity": str(self.severity), "detail": dict(self.detail)}


def _severity_for(kind: ChangeKind) -> Severity:
    return _SEVERITY.get(kind, Severity.BREAKING)


@dataclass(frozen=True, slots=True)
class ApiDiff:
    """The classified difference between two surfaces."""

    changes: tuple[Change, ...]

    @property
    def breaking(self) -> tuple[Change, ...]:
        return tuple(c for c in self.changes if c.severity is Severity.BREAKING)

    @property
    def risky(self) -> tuple[Change, ...]:
        return tuple(c for c in self.changes if c.severity is Severity.RISKY)

    def of_kind(self, kind: ChangeKind) -> tuple[Change, ...]:
        return tuple(c for c in self.changes if c.kind is kind)

    def to_payload(self) -> dict[str, Any]:
        return {"changes": [change.to_payload() for change in self.changes],
                "breakingCount": len(self.breaking), "riskyCount": len(self.risky),
                "totalCount": len(self.changes)}

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def merge_diffs(*diffs: ApiDiff) -> ApiDiff:
    """Combine diffs, preserving a deterministic order."""

    changes: list[Change] = []
    for one in diffs:
        changes.extend(one.changes)
    return ApiDiff(changes=_sorted(changes))


def _sorted(changes: Sequence[Change]) -> tuple[Change, ...]:
    return tuple(sorted(changes, key=lambda c: (c.symbol, str(c.kind),
                                                digest(dict(c.detail)))))


def _change(symbol: str, kind: ChangeKind, /, **detail: Any) -> Change:
    """Build a change.  ``symbol`` and ``kind`` are positional-only so that a detail
    key literally named ``kind`` (a declaration's own kind) cannot collide with them."""

    return Change(symbol=symbol, kind=kind, severity=_severity_for(kind), detail=detail)


def _diff_params(symbol: str, before: Declaration, after: Declaration,
                 lattice: TypeLattice) -> list[Change]:
    changes: list[Change] = []
    before_params = {param.name: param for param in before.params}
    after_params = {param.name: param for param in after.params}
    only_before = [name for name in before_params if name not in after_params]
    only_after = [name for name in after_params if name not in before_params]

    # Rename detection: same positional index, same type, one gone and one appeared.
    before_index = {param.name: index for index, param in enumerate(before.params)}
    after_index = {param.name: index for index, param in enumerate(after.params)}
    renamed: dict[str, str] = {}
    for old_name in sorted(only_before):
        for new_name in sorted(only_after):
            if new_name in renamed.values():
                continue
            if (before_index[old_name] == after_index[new_name]
                    and before_params[old_name].type == after_params[new_name].type):
                renamed[old_name] = new_name
                break
    for old_name, new_name in sorted(renamed.items()):
        changes.append(_change(f"{symbol}.{old_name}", ChangeKind.PARAM_RENAMED,
                               before=old_name, after=new_name,
                               position=before_index[old_name]))

    for name in sorted(only_before):
        if name in renamed:
            continue
        changes.append(_change(f"{symbol}.{name}", ChangeKind.PARAM_REMOVED,
                               type=before_params[name].type))
    for name in sorted(only_after):
        if name in renamed.values():
            continue
        param = after_params[name]
        kind = (ChangeKind.PARAM_ADDED_OPTIONAL if param.has_default
                else ChangeKind.PARAM_ADDED_REQUIRED)
        changes.append(_change(f"{symbol}.{name}", kind, type=param.type,
                               hasDefault=param.has_default))

    shared = [name for name in before_params if name in after_params]
    for name in sorted(shared):
        old = before_params[name]
        new = after_params[name]
        if old.kind is not new.kind:
            changes.append(_change(f"{symbol}.{name}", ChangeKind.PARAM_KIND_CHANGED,
                                   before=str(old.kind), after=str(new.kind)))
        if old.has_default and not new.has_default:
            changes.append(_change(f"{symbol}.{name}", ChangeKind.PARAM_DEFAULT_REMOVED))
        elif new.has_default and not old.has_default:
            changes.append(_change(f"{symbol}.{name}", ChangeKind.PARAM_DEFAULT_ADDED))
        relation = lattice.relate(old.type, new.type)
        if relation == "narrowed":
            # Contravariance: the callee now accepts less than a caller may send.
            changes.append(_change(f"{symbol}.{name}", ChangeKind.PARAM_TYPE_NARROWED,
                                   before=old.type, after=new.type, variance="contravariant"))
        elif relation == "widened":
            changes.append(_change(f"{symbol}.{name}", ChangeKind.PARAM_TYPE_WIDENED,
                                   before=old.type, after=new.type, variance="contravariant"))
        elif relation == "unrelated":
            changes.append(_change(f"{symbol}.{name}", ChangeKind.PARAM_TYPE_UNRELATED,
                                   before=old.type, after=new.type))

    # Reordering is only observable for positionally-passed parameters.
    kept_before = tuple(name for name in before.positional_names
                        if renamed.get(name, name) in after_params
                        and after_params[renamed.get(name, name)].kind is ParamKind.POSITIONAL)
    kept_after = tuple(renamed.get(name, name) for name in kept_before)
    actual_after = tuple(name for name in after.positional_names if name in set(kept_after))
    if kept_after != actual_after:
        changes.append(_change(symbol, ChangeKind.PARAM_REORDERED,
                               before=list(kept_after), after=list(actual_after)))
    return changes


def diff(before: ApiSurface, after: ApiSurface, *,
         lattice: TypeLattice = DEFAULT_LATTICE) -> ApiDiff:
    """Classify every difference between two source-level API surfaces."""

    before_map = before.by_name()
    after_map = after.by_name()
    changes: list[Change] = []

    for name in sorted(set(before_map) - set(after_map)):
        declaration = before_map[name]
        if declaration.visibility is Visibility.PUBLIC:
            changes.append(_change(name, ChangeKind.REMOVED, kind=declaration.kind,
                                   wasDeprecated=declaration.deprecated))
        else:
            changes.append(Change(symbol=name, kind=ChangeKind.REMOVED,
                                  severity=Severity.COMPATIBLE,
                                  detail={"kind": declaration.kind,
                                          "visibility": str(declaration.visibility),
                                          "note": "not part of the public contract"}))
    for name in sorted(set(after_map) - set(before_map)):
        declaration = after_map[name]
        changes.append(_change(name, ChangeKind.ADDED, kind=declaration.kind,
                               visibility=str(declaration.visibility)))

    for name in sorted(set(before_map) & set(after_map)):
        old = before_map[name]
        new = after_map[name]
        if old.kind != new.kind:
            changes.append(_change(name, ChangeKind.KIND_CHANGED,
                                   before=old.kind, after=new.kind))
        if old.visibility is not new.visibility:
            reduced = _VISIBILITY_RANK[new.visibility] < _VISIBILITY_RANK[old.visibility]
            changes.append(_change(
                name,
                ChangeKind.VISIBILITY_REDUCED if reduced else ChangeKind.VISIBILITY_INCREASED,
                before=str(old.visibility), after=str(new.visibility)))
        if old.deprecated != new.deprecated:
            changes.append(_change(
                name, ChangeKind.DEPRECATED if new.deprecated else ChangeKind.UNDEPRECATED))
        if old.since_version != new.since_version:
            changes.append(_change(name, ChangeKind.SINCE_VERSION_CHANGED,
                                   before=old.since_version, after=new.since_version))
        relation = lattice.relate(old.return_type, new.return_type)
        if relation == "narrowed":
            # Covariance: returning less than promised is safe for existing callers.
            changes.append(_change(name, ChangeKind.RETURN_TYPE_NARROWED,
                                   before=old.return_type, after=new.return_type,
                                   variance="covariant"))
        elif relation == "widened":
            changes.append(_change(name, ChangeKind.RETURN_TYPE_WIDENED,
                                   before=old.return_type, after=new.return_type,
                                   variance="covariant"))
        elif relation == "unrelated":
            changes.append(_change(name, ChangeKind.RETURN_TYPE_UNRELATED,
                                   before=old.return_type, after=new.return_type))
        changes.extend(_diff_params(name, old, new, lattice))

    return ApiDiff(changes=_sorted(changes))


_VISIBILITY_RANK: Mapping[Visibility, int] = {
    Visibility.PRIVATE: 0, Visibility.INTERNAL: 1, Visibility.PUBLIC: 2,
}


def diff_wire(before: WireSurface, after: WireSurface) -> ApiDiff:
    """Classify wire-level differences, tag identity first.

    A tag that meant one thing and now means another is ``WIRE_TAG_REUSE`` whether or not
    the old field is still present in the schema, and whether or not it was formally
    reserved.  That is the change no source-level diff can see and the one that corrupts
    already-persisted data.
    """

    before_map = before.by_name()
    after_map = after.by_name()
    changes: list[Change] = []

    for name in sorted(set(before_map) - set(after_map)):
        changes.append(_change(name, ChangeKind.WIRE_MESSAGE_REMOVED))
    for name in sorted(set(after_map) - set(before_map)):
        changes.append(_change(name, ChangeKind.WIRE_MESSAGE_ADDED))

    for name in sorted(set(before_map) & set(after_map)):
        old = before_map[name]
        new = after_map[name]
        old_tags = old.by_tag()
        new_tags = new.by_tag()
        retired = set(old.reserved_tags)

        for tag in sorted(set(old_tags) - set(new_tags)):
            old_field = old_tags[tag]
            still_named = any(f.name == old_field.name for f in new.fields)
            if still_named:
                moved = next(f for f in new.fields if f.name == old_field.name)
                changes.append(_change(f"{name}#{tag}", ChangeKind.WIRE_TAG_CHANGED,
                                       fieldName=old_field.name, before=tag, after=moved.tag))
                continue
            kind = (ChangeKind.WIRE_FIELD_REMOVED if tag in new.reserved_tags
                    else ChangeKind.WIRE_FIELD_REMOVED_UNRESERVED)
            changes.append(_change(f"{name}#{tag}", kind, fieldName=old_field.name,
                                   reserved=tag in new.reserved_tags))

        for tag in sorted(new_tags):
            new_field = new_tags[tag]
            old_field = old_tags.get(tag)
            if old_field is None:
                if tag in retired:
                    changes.append(_change(
                        f"{name}#{tag}", ChangeKind.WIRE_TAG_REUSE,
                        fieldName=new_field.name, tag=tag,
                        reason="tag was retired in the baseline and is now reassigned"))
                    continue
                kind = (ChangeKind.WIRE_FIELD_ADDED_REQUIRED if new_field.required
                        else ChangeKind.WIRE_FIELD_ADDED_OPTIONAL)
                changes.append(_change(f"{name}#{tag}", kind, fieldName=new_field.name))
                continue
            if old_field.name != new_field.name:
                changes.append(_change(
                    f"{name}#{tag}", ChangeKind.WIRE_TAG_REUSE,
                    before=old_field.name, after=new_field.name, tag=tag,
                    reason="tag now carries a different field"))
                continue
            if old_field.type != new_field.type:
                pair = (old_field.type, new_field.type)
                kind = (ChangeKind.WIRE_TYPE_COMPATIBLE if pair in _WIRE_COMPATIBLE
                        else ChangeKind.WIRE_TYPE_INCOMPATIBLE)
                changes.append(_change(f"{name}#{tag}", kind, fieldName=new_field.name,
                                       before=old_field.type, after=new_field.type))
            if new_field.required and not old_field.required:
                changes.append(_change(f"{name}#{tag}", ChangeKind.WIRE_FIELD_ADDED_REQUIRED,
                                       fieldName=new_field.name,
                                       reason="an optional field became required"))
    return ApiDiff(changes=_sorted(changes))


# --- policy ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Policy:
    """How much breakage a release is allowed to ship.

    ``consumers_known`` is not cosmetic: with an unknown consumer set, a RISKY change has
    no evidence behind it, so the strict and deprecate-first policies promote it to
    blocking.  This is invariant I3 of the SKILL — an unknown consumer raises risk.
    """

    policy_id: str
    mode: str
    consumers_known: bool = False
    min_notice_days: int = 90

    def __post_init__(self) -> None:
        if self.mode not in {"strict", "deprecate-first", "best-effort"}:
            raise KernelError(
                code="COMPAT_UNKNOWN_POLICY",
                message=f"unknown compatibility mode {self.mode!r}",
                recommended_action="use strict, deprecate-first or best-effort",
            )
        require_int(self.min_notice_days, "min_notice_days", minimum=0)


POLICIES: Mapping[str, Policy] = {
    "strict": Policy(policy_id="strict", mode="strict", min_notice_days=180),
    "deprecate-first": Policy(policy_id="deprecate-first", mode="deprecate-first",
                              min_notice_days=90),
    "best-effort": Policy(policy_id="best-effort", mode="best-effort", min_notice_days=30),
}

#: Classifications that no policy can waive.  Reusing a wire tag silently reinterprets
#: bytes that are already on disk and in flight; there is no consumer inventory and no
#: notice window that makes it safe.
UNWAIVABLE: frozenset[ChangeKind] = frozenset({ChangeKind.WIRE_TAG_REUSE})


def policy_for(name: str, *, consumers_known: bool = False) -> Policy:
    """Look up a named policy, failing closed on anything unknown or empty."""

    if not name:
        raise KernelError(
            code="COMPAT_UNKNOWN_POLICY",
            message="no compatibility policy supplied; an empty policy is a deny",
            recommended_action="name one of: " + ", ".join(sorted(POLICIES)),
        )
    base = POLICIES.get(name)
    if base is None:
        raise KernelError(
            code="COMPAT_UNKNOWN_POLICY",
            message=f"unknown compatibility policy {name!r}",
            recommended_action="name one of: " + ", ".join(sorted(POLICIES)),
            details={"supported": sorted(POLICIES)},
        )
    return Policy(policy_id=base.policy_id, mode=base.mode, consumers_known=consumers_known,
                  min_notice_days=base.min_notice_days)


@dataclass(frozen=True, slots=True)
class CompatibilityDecision:
    """The version bump the diff forces, plus what must be resolved first."""

    policy_id: str
    bump: str
    blocking: tuple[Change, ...]
    rationale: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        return not self.blocking

    def to_payload(self) -> dict[str, Any]:
        return {"policyId": self.policy_id, "bump": self.bump,
                "blocking": [change.to_payload() for change in self.blocking],
                "allowed": self.allowed, "rationale": list(self.rationale)}

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def decide(api_diff: ApiDiff, policy: Policy) -> CompatibilityDecision:
    """Apply ``policy`` to ``api_diff`` and return the bump plus the blocking list."""

    breaking = api_diff.breaking
    risky = api_diff.risky
    additions = [c for c in api_diff.changes
                 if c.kind in {ChangeKind.ADDED, ChangeKind.PARAM_ADDED_OPTIONAL,
                               ChangeKind.WIRE_FIELD_ADDED_OPTIONAL,
                               ChangeKind.WIRE_MESSAGE_ADDED}]

    bump = "MAJOR" if breaking else ("MINOR" if additions else "PATCH")
    rationale: list[str] = []
    blocking: list[Change] = []

    unwaivable = [c for c in api_diff.changes if c.kind in UNWAIVABLE]
    if unwaivable:
        rationale.append(
            f"{len(unwaivable)} change(s) reuse a retired wire tag; no policy can waive this"
        )
        blocking.extend(unwaivable)

    if policy.mode == "strict":
        blocking.extend(c for c in breaking if c not in blocking)
        blocking.extend(c for c in risky if c not in blocking)
        rationale.append("strict: every breaking change blocks, and every risky change "
                         "blocks as well")
    elif policy.mode == "deprecate-first":
        for change in breaking:
            if change in blocking:
                continue
            deprecated_first = bool(change.detail.get("wasDeprecated"))
            if change.kind is ChangeKind.REMOVED and deprecated_first:
                rationale.append(f"{change.symbol}: removal allowed, it shipped deprecated")
                continue
            blocking.append(change)
        if not policy.consumers_known:
            blocking.extend(c for c in risky if c not in blocking)
            rationale.append("deprecate-first: consumer inventory is unknown, so risky "
                             "changes block (UNKNOWN_CONSUMER)")
        else:
            rationale.append("deprecate-first: risky changes cleared against a known "
                             "consumer inventory")
    else:
        rationale.append("best-effort: breaking changes are reported and force a MAJOR "
                         "bump but do not block")

    if not breaking and not risky:
        rationale.append("no breaking or risky change detected")

    return CompatibilityDecision(policy_id=policy.policy_id, bump=bump,
                                 blocking=_sorted(blocking), rationale=tuple(rationale))


# --- deprecation plan --------------------------------------------------------

#: Minimum notice per classification, in whole days.  The engine never invents a shorter
#: window than the policy's, and never a zero window for a change that has consumers.
_NOTICE_DAYS: Mapping[ChangeKind, int] = {
    ChangeKind.REMOVED: 180,
    ChangeKind.VISIBILITY_REDUCED: 180,
    ChangeKind.KIND_CHANGED: 180,
    ChangeKind.PARAM_REMOVED: 90,
    ChangeKind.PARAM_RENAMED: 90,
    ChangeKind.PARAM_REORDERED: 90,
    ChangeKind.PARAM_ADDED_REQUIRED: 90,
    ChangeKind.PARAM_DEFAULT_REMOVED: 90,
    ChangeKind.PARAM_TYPE_NARROWED: 90,
    ChangeKind.PARAM_TYPE_UNRELATED: 90,
    ChangeKind.RETURN_TYPE_WIDENED: 60,
    ChangeKind.RETURN_TYPE_UNRELATED: 60,
    ChangeKind.WIRE_FIELD_REMOVED_UNRESERVED: 180,
    ChangeKind.WIRE_TAG_CHANGED: 180,
    ChangeKind.WIRE_TYPE_INCOMPATIBLE: 180,
    ChangeKind.WIRE_FIELD_ADDED_REQUIRED: 90,
}


@dataclass(frozen=True, slots=True)
class DeprecationStep:
    """One ordered, actionable step."""

    order: int
    symbol: str
    action: str
    min_notice_days: int
    rationale: str
    change_kind: ChangeKind

    def to_payload(self) -> dict[str, Any]:
        return {"order": self.order, "symbol": self.symbol, "action": self.action,
                "minNoticeDays": self.min_notice_days, "rationale": self.rationale,
                "changeKind": str(self.change_kind)}


@dataclass(frozen=True, slots=True)
class DeprecationPlan:
    """Forward steps plus the rollback that undoes them.

    Every ``ENFORCE`` step has a matching rollback step in reverse order; a migration plan
    without a stated way back is not a plan, it is a one-way door.
    """

    steps: tuple[DeprecationStep, ...]
    rollback: tuple[DeprecationStep, ...]
    total_notice_days: int

    def to_payload(self) -> dict[str, Any]:
        return {"steps": [step.to_payload() for step in self.steps],
                "rollback": [step.to_payload() for step in self.rollback],
                "totalNoticeDays": self.total_notice_days}

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def deprecation_plan(api_diff: ApiDiff, *,
                     policy: Policy | None = None) -> DeprecationPlan:
    """Emit ordered steps that take each breaking change through a notice window."""

    floor = policy.min_notice_days if policy is not None else 0
    steps: list[DeprecationStep] = []
    rollback: list[DeprecationStep] = []
    order = 0
    total = 0

    for change in api_diff.changes:
        if change.severity is not Severity.BREAKING:
            continue
        if change.kind in UNWAIVABLE:
            order += 1
            steps.append(DeprecationStep(
                order=order, symbol=change.symbol, action="FORBID", min_notice_days=0,
                rationale="a retired wire tag can never be reassigned; allocate a new tag "
                          "and keep the old one reserved forever",
                change_kind=change.kind))
            continue
        notice = max(_NOTICE_DAYS.get(change.kind, 90), floor)
        total = max(total, notice)
        order += 1
        steps.append(DeprecationStep(
            order=order, symbol=change.symbol, action="ANNOUNCE", min_notice_days=notice,
            rationale=f"mark {change.symbol} deprecated and publish the replacement",
            change_kind=change.kind))
        order += 1
        steps.append(DeprecationStep(
            order=order, symbol=change.symbol, action="DUAL_SUPPORT",
            min_notice_days=notice,
            rationale=f"ship an adapter so old and new callers of {change.symbol} both work",
            change_kind=change.kind))
        order += 1
        steps.append(DeprecationStep(
            order=order, symbol=change.symbol, action="ENFORCE", min_notice_days=notice,
            rationale=f"apply the breaking change to {change.symbol} after the notice window",
            change_kind=change.kind))
        rollback.append(DeprecationStep(
            order=order, symbol=change.symbol, action="ROLLBACK",
            min_notice_days=0,
            rationale=f"restore the pre-change contract for {change.symbol} and re-enable "
                      "the adapter",
            change_kind=change.kind))

    rollback.reverse()
    return DeprecationPlan(steps=tuple(steps),
                           rollback=tuple(
                               DeprecationStep(order=index + 1, symbol=step.symbol,
                                               action=step.action,
                                               min_notice_days=step.min_notice_days,
                                               rationale=step.rationale,
                                               change_kind=step.change_kind)
                               for index, step in enumerate(rollback)),
                           total_notice_days=total)


# --- decoding ----------------------------------------------------------------

_KNOWN_FIELDS = ("baselineSurface", "candidateSurface", "baselineWire", "candidateWire",
                 "policy", "consumerInventory")
_KNOWN_DECL_FIELDS = ("name", "kind", "params", "returnType", "visibility", "sinceVersion",
                      "deprecated")
_KNOWN_PARAM_FIELDS = ("name", "type", "hasDefault", "kind")
_KNOWN_WIRE_FIELDS = ("name", "tag", "type", "required")
_KNOWN_MESSAGE_FIELDS = ("name", "fields", "reservedTags")


def _decode_param(payload: Any, where: str) -> ParamSpec:
    mapping = require_mapping(payload, where)
    reject_unknown_fields(mapping, _KNOWN_PARAM_FIELDS, field_name=where)
    kind_text = mapping.get("kind", "positional")
    try:
        kind = ParamKind(kind_text)
    except ValueError as exc:
        raise KernelError(
            code="COMPAT_UNKNOWN_PARAM_KIND",
            message=f"{where}.kind={kind_text!r} is not a known parameter kind",
            recommended_action="use positional, keyword or variadic",
        ) from exc
    return ParamSpec(
        name=require_str(mapping.get("name"), f"{where}.name", max_length=256),
        type=require_str(mapping.get("type"), f"{where}.type", max_length=256),
        has_default=require_bool(mapping.get("hasDefault", False), f"{where}.hasDefault"),
        kind=kind,
    )


def _decode_declaration(payload: Any, where: str) -> Declaration:
    mapping = require_mapping(payload, where)
    reject_unknown_fields(mapping, _KNOWN_DECL_FIELDS, field_name=where)
    raw_params = mapping.get("params", [])
    if not isinstance(raw_params, Sequence) or isinstance(raw_params, (str, bytes)):
        raise KernelError(
            code="COMPAT_MALFORMED_SURFACE",
            message=f"{where}.params must be an array",
            recommended_action="supply params as a JSON array",
        )
    visibility_text = mapping.get("visibility", "public")
    try:
        visibility = Visibility(visibility_text)
    except ValueError as exc:
        raise KernelError(
            code="COMPAT_MALFORMED_SURFACE",
            message=f"{where}.visibility={visibility_text!r} is unknown",
            recommended_action="use public, internal or private",
        ) from exc
    return Declaration(
        name=require_str(mapping.get("name"), f"{where}.name", max_length=256),
        kind=require_str(mapping.get("kind", "function"), f"{where}.kind", max_length=64),
        params=tuple(_decode_param(item, f"{where}.params[{index}]")
                     for index, item in enumerate(raw_params)),
        return_type=require_str(mapping.get("returnType", "void"), f"{where}.returnType",
                                max_length=256),
        visibility=visibility,
        since_version=require_str(mapping.get("sinceVersion", "0.0.0"),
                                  f"{where}.sinceVersion", max_length=64),
        deprecated=require_bool(mapping.get("deprecated", False), f"{where}.deprecated"),
    )


def _decode_surface(payload: Any, where: str) -> ApiSurface:
    mapping = require_mapping(payload, where)
    reject_unknown_fields(mapping, ("declarations",), field_name=where)
    raw = mapping.get("declarations")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise KernelError(
            code="COMPAT_MALFORMED_SURFACE",
            message=f"{where}.declarations must be an array",
            recommended_action="supply declarations as a JSON array",
        )
    return ApiSurface(declarations=tuple(
        _decode_declaration(item, f"{where}.declarations[{index}]")
        for index, item in enumerate(raw)))


def _decode_wire(payload: Any, where: str) -> WireSurface:
    mapping = require_mapping(payload, where)
    reject_unknown_fields(mapping, ("messages",), field_name=where)
    raw = mapping.get("messages", [])
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise KernelError(
            code="COMPAT_MALFORMED_SURFACE",
            message=f"{where}.messages must be an array",
            recommended_action="supply messages as a JSON array",
        )
    messages: list[WireMessage] = []
    for index, item in enumerate(raw):
        entry = require_mapping(item, f"{where}.messages[{index}]")
        reject_unknown_fields(entry, _KNOWN_MESSAGE_FIELDS,
                              field_name=f"{where}.messages[{index}]")
        raw_fields = entry.get("fields", [])
        if not isinstance(raw_fields, Sequence) or isinstance(raw_fields, (str, bytes)):
            raise KernelError(
                code="COMPAT_MALFORMED_SURFACE",
                message=f"{where}.messages[{index}].fields must be an array",
                recommended_action="supply fields as a JSON array",
            )
        fields: list[WireField] = []
        for position, raw_field in enumerate(raw_fields):
            where_field = f"{where}.messages[{index}].fields[{position}]"
            entry_field = require_mapping(raw_field, where_field)
            reject_unknown_fields(entry_field, _KNOWN_WIRE_FIELDS, field_name=where_field)
            fields.append(WireField(
                name=require_str(entry_field.get("name"), f"{where_field}.name", max_length=256),
                tag=require_int(entry_field.get("tag"), f"{where_field}.tag", minimum=1),
                type=require_str(entry_field.get("type"), f"{where_field}.type", max_length=64),
                required=require_bool(entry_field.get("required", False),
                                      f"{where_field}.required"),
            ))
        reserved = entry.get("reservedTags", [])
        if not isinstance(reserved, Sequence) or isinstance(reserved, (str, bytes)):
            raise KernelError(
                code="COMPAT_MALFORMED_SURFACE",
                message=f"{where}.messages[{index}].reservedTags must be an array",
                recommended_action="supply reservedTags as a JSON array of integers",
            )
        messages.append(WireMessage(
            name=require_str(entry.get("name"), f"{where}.messages[{index}].name",
                             max_length=256),
            fields=tuple(fields),
            reserved_tags=tuple(require_int(tag, f"{where}.messages[{index}].reservedTags[{i}]",
                                            minimum=1)
                                for i, tag in enumerate(reserved)),
        ))
    return WireSurface(messages=tuple(messages))


@register("contract-compatibility-engine")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point: decode strictly, diff, decide, plan."""

    payload = require_mapping(request, "request")
    reject_unknown_fields(payload, _KNOWN_FIELDS,
                          field_name="contract-compatibility-engine request")

    before = _decode_surface(payload.get("baselineSurface", {"declarations": []}),
                             "baselineSurface")
    after = _decode_surface(payload.get("candidateSurface", {"declarations": []}),
                            "candidateSurface")
    source_diff = diff(before, after)

    wire_diff = ApiDiff(changes=())
    if "baselineWire" in payload or "candidateWire" in payload:
        wire_diff = diff_wire(_decode_wire(payload.get("baselineWire", {"messages": []}),
                                           "baselineWire"),
                              _decode_wire(payload.get("candidateWire", {"messages": []}),
                                           "candidateWire"))
    combined = merge_diffs(source_diff, wire_diff)

    inventory = payload.get("consumerInventory")
    consumers_known = False
    consumer_count: int | None = None
    if inventory is not None:
        entry = require_mapping(inventory, "consumerInventory")
        reject_unknown_fields(entry, ("consumers", "complete"), field_name="consumerInventory")
        consumers = entry.get("consumers", [])
        if not isinstance(consumers, Sequence) or isinstance(consumers, (str, bytes)):
            raise KernelError(
                code="COMPAT_MALFORMED_SURFACE",
                message="consumerInventory.consumers must be an array",
                recommended_action="supply consumers as a JSON array",
            )
        consumer_count = len(consumers)
        consumers_known = require_bool(entry.get("complete", False),
                                       "consumerInventory.complete")

    policy_name = require_str(payload.get("policy", ""), "policy", max_length=64) \
        if payload.get("policy") else ""
    policy = policy_for(policy_name, consumers_known=consumers_known)
    decision = decide(combined, policy)
    plan = deprecation_plan(combined, policy=policy)

    return {
        "status": Status.SUCCEEDED,
        "compatibilityReport": combined.to_payload(),
        "breakingChanges": [change.to_payload() for change in combined.breaking],
        "compatibilityDecision": decision.to_payload(),
        "migrationPlan": plan.to_payload(),
        "rollbackContract": {"steps": [step.to_payload() for step in plan.rollback],
                             "coversEnforceSteps": len(
                                 [s for s in plan.steps if s.action == "ENFORCE"])},
        "consumerInventory": {"count": consumer_count, "complete": consumers_known,
                              "measured": consumer_count is not None},
        "digest": digest({"diff": combined.to_payload(), "decision": decision.to_payload(),
                          "plan": plan.to_payload()}),
    }

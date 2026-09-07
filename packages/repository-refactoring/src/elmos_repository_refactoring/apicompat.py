"""Skill 20 — source, binary, wire and behaviour compatibility.

Extracts a normalised API surface from a semantic index and diffs two of them.
Each difference is classified into the *strongest* compatibility it breaks, and
the classification is deliberately pessimistic in the places where optimism is
expensive:

* Removing anything public is a break, even if nothing in this repository uses
  it — the consumers we cannot see are the ones that matter.
* Adding a parameter without a default is a source break, not an addition.
* Renaming a field in a wire contract is a **wire break**, never a rename:
  the old name disappears from the wire whatever the intent was.
* Changing a proto field number or an enum ordinal is a wire break even when
  the name is unchanged, because the wire carries the number.
* An "additive" change still has to prove its serialisation default: a new
  optional field that serialises differently in an old consumer is not
  additive.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .contracts import (
    CompatibilityImpact,
    EntityKind,
    RiskClass,
    sha256_payload,
)
from .index import SemanticIndex

#: Visibilities that make a symbol part of the published surface.
PUBLIC_VISIBILITIES = frozenset({"public", "exported"})

_SIGNATURE_PARAMS = re.compile(r"\(([^)]*)\)")
_PROTO_FIELD = re.compile(r"^\s*(?:repeated\s+|optional\s+|required\s+)?[\w.<>]+\s+(\w+)\s*=\s*(\d+)", re.MULTILINE)
_ENUM_MEMBER = re.compile(r"^\s*(\w+)\s*=\s*(\d+)\s*;", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class ApiMember:
    """One element of the published surface, normalised for comparison."""

    identity: str
    kind: str
    language: str
    path: str
    signature: str = ""
    visibility: str = "public"
    wire_number: int | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @property
    def parameters(self) -> tuple[str, ...]:
        match = _SIGNATURE_PARAMS.search(self.signature)
        if match is None:
            return ()
        body = match.group(1).strip()
        if not body:
            return ()
        return tuple(item.strip() for item in _split_top_level(body))

    @property
    def required_parameters(self) -> tuple[str, ...]:
        return tuple(item for item in self.parameters if "=" not in item and item not in ("self", "cls", "*", "/"))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "identity": self.identity,
            "kind": self.kind,
            "language": self.language,
            "path": self.path,
            "visibility": self.visibility,
        }
        if self.signature:
            payload["signature"] = self.signature
        if self.wire_number is not None:
            payload["wireNumber"] = self.wire_number
        if self.attributes:
            payload["attributes"] = dict(sorted(self.attributes.items()))
        return payload


def _split_top_level(body: str) -> list[str]:
    """Split a parameter list on commas that are not inside brackets."""

    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in body:
        if char in "[({<":
            depth += 1
        elif char in "])}>":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current))
    return [item for item in parts if item.strip()]


@dataclass(frozen=True, slots=True)
class ApiSurface:
    members: tuple[ApiMember, ...]
    revision: str = ""

    def by_identity(self) -> dict[str, ApiMember]:
        return {member.identity: member for member in self.members}

    @property
    def identities(self) -> frozenset[str]:
        return frozenset(member.identity for member in self.members)

    def to_payload(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "memberCount": len(self.members),
            "members": [member.to_payload() for member in self.members],
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


@dataclass(frozen=True, slots=True)
class ApiChange:
    identity: str
    change: str
    impact: CompatibilityImpact
    detail: str
    before: str = ""
    after: str = ""
    path: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "change": self.change,
            "impact": self.impact.value,
            "detail": self.detail,
            "before": self.before,
            "after": self.after,
            "path": self.path,
        }


@dataclass(frozen=True, slots=True)
class ApiDiff:
    changes: tuple[ApiChange, ...]
    before_digest: str = ""
    after_digest: str = ""

    def of(self, impact: CompatibilityImpact) -> tuple[ApiChange, ...]:
        return tuple(item for item in self.changes if item.impact is impact)

    @property
    def breaks(self) -> tuple[ApiChange, ...]:
        return tuple(item for item in self.changes if item.impact.is_break)

    @property
    def source_breaks(self) -> int:
        return len(self.of(CompatibilityImpact.SOURCE_BREAK))

    @property
    def binary_breaks(self) -> int:
        return len(self.of(CompatibilityImpact.BINARY_BREAK))

    @property
    def wire_breaks(self) -> int:
        return len(self.of(CompatibilityImpact.WIRE_BREAK))

    @property
    def behavior_risks(self) -> int:
        return len(self.of(CompatibilityImpact.BEHAVIOR_RISK))

    @property
    def additive_only(self) -> bool:
        return not self.breaks

    def to_payload(self) -> dict[str, Any]:
        return {
            "beforeDigest": self.before_digest,
            "afterDigest": self.after_digest,
            "additiveOnly": self.additive_only,
            "counts": {
                "additive": len(self.of(CompatibilityImpact.ADDITIVE)),
                "sourceBreak": self.source_breaks,
                "binaryBreak": self.binary_breaks,
                "wireBreak": self.wire_breaks,
                "behaviorRisk": self.behavior_risks,
            },
            "changes": [item.to_payload() for item in self.changes],
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


# ---------------------------------------------------------------------------
# Surface extraction
# ---------------------------------------------------------------------------

_SURFACE_KINDS = {
    EntityKind.TYPE,
    EntityKind.FUNCTION,
    EntityKind.METHOD,
    EntityKind.PROPERTY,
    EntityKind.FIELD,
    EntityKind.API_CONTRACT,
    EntityKind.EVENT_CONTRACT,
}


def extract_surface(index: SemanticIndex, *, include_internal: bool = False) -> ApiSurface:
    """The published surface of one revision."""

    members: list[ApiMember] = []
    for entity in index.entities:
        if entity.kind not in _SURFACE_KINDS:
            continue
        is_contract = entity.kind in (EntityKind.API_CONTRACT, EntityKind.EVENT_CONTRACT)
        if not is_contract and entity.visibility not in PUBLIC_VISIBILITIES and not include_internal:
            continue
        members.append(
            ApiMember(
                identity=entity.qualified_name or f"{entity.path}#{entity.name}",
                kind=entity.kind.value,
                language=entity.language,
                path=entity.path,
                signature=entity.signature,
                visibility=entity.visibility,
                attributes={
                    key: value
                    for key, value in entity.attributes.items()
                    if key in ("bases", "async", "arity", "annotated", "contract")
                },
            )
        )
    return ApiSurface(
        members=tuple(sorted(members, key=lambda item: item.identity)),
        revision=index.revision,
    )


def extract_wire_surface(files: Mapping[str, str]) -> ApiSurface:
    """Field numbers and enum ordinals — the parts the wire actually carries."""

    members: list[ApiMember] = []
    for path, text in sorted(files.items()):
        if not path.endswith(".proto"):
            continue
        #: Scoping matters: attributing every field to the *last* declaration
        #: in the file would make two messages with the same field name
        #: indistinguishable, and would compare the wrong numbers.
        container = ""
        container_kind = ""
        depth = 0
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("message ", "enum ")):
                container_kind = stripped.split(None, 1)[0]
                container = stripped.split()[1].rstrip("{").strip()
                depth = 0
            depth += line.count("{") - line.count("}")
            if depth <= 0 and not stripped.startswith(("message ", "enum ")):
                if stripped.startswith("}"):
                    container, container_kind = "", ""
                    continue
            if container_kind == "enum":
                match = _ENUM_MEMBER.match(stripped)
                if match:
                    members.append(
                        ApiMember(
                            identity=f"{path}#{container}.{match.group(1)}",
                            kind="wire-enum-member",
                            language="protobuf",
                            path=path,
                            wire_number=int(match.group(2)),
                            attributes={"container": container},
                        )
                    )
                continue
            match = _PROTO_FIELD.match(stripped)
            if match and container:
                members.append(
                    ApiMember(
                        identity=f"{path}#{container}.{match.group(1)}",
                        kind="wire-field",
                        language="protobuf",
                        path=path,
                        wire_number=int(match.group(2)),
                        attributes={"container": container},
                    )
                )
    return ApiSurface(members=tuple(sorted(members, key=lambda item: item.identity)))


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def diff_surfaces(before: ApiSurface, after: ApiSurface) -> ApiDiff:
    """Classify every difference by the strongest compatibility it breaks."""

    left = before.by_identity()
    right = after.by_identity()
    changes: list[ApiChange] = []
    renames = _detect_wire_renames(left, right)
    changes.extend(renames.values())
    renamed_before = set(renames)
    renamed_after = {change.after for change in renames.values()}

    for identity in sorted(set(left) - set(right) - renamed_before):
        member = left[identity]
        changes.append(
            ApiChange(
                identity=identity,
                change="removed",
                impact=_removal_impact(member),
                detail=(
                    f"public {member.kind} removed; consumers outside this repository cannot be enumerated, "
                    "so absence of in-repository usage is not evidence of safety"
                ),
                before=member.signature or member.kind,
                path=member.path,
            )
        )

    for identity in sorted(set(right) - set(left) - renamed_after):
        member = right[identity]
        impact = CompatibilityImpact.ADDITIVE
        detail = f"new public {member.kind}"
        if member.wire_number is not None:
            detail += f" with wire number {member.wire_number}"
        if member.kind in ("method", "property", "field") and member.attributes.get("abstract"):
            impact = CompatibilityImpact.SOURCE_BREAK
            detail = "new abstract member: every existing implementer must be updated"
        changes.append(
            ApiChange(
                identity=identity,
                change="added",
                impact=impact,
                detail=detail,
                after=member.signature or member.kind,
                path=member.path,
            )
        )

    for identity in sorted(set(left) & set(right)):
        changes.extend(_compare_member(left[identity], right[identity]))

    return ApiDiff(
        changes=tuple(changes),
        before_digest=before.digest,
        after_digest=after.digest,
    )


def _wire_slot(member: ApiMember) -> tuple[str, str, str, int] | None:
    """The coordinates the wire format actually keys on."""

    if member.wire_number is None:
        return None
    container = str(member.attributes.get("container", ""))
    if not container:
        return None
    return (member.path, container, member.kind, member.wire_number)


def _detect_wire_renames(
    left: Mapping[str, ApiMember],
    right: Mapping[str, ApiMember],
) -> dict[str, ApiChange]:
    """Pair a disappearance with an appearance that occupies the same wire slot.

    Protocol buffers key the binary encoding on the field number and type, not
    on the name. A field renamed while keeping its number is therefore *not* a
    wire break: already-serialised bytes still decode. It does break the JSON
    and text encodings, which carry names, and it breaks every generated client
    that compiled against the old accessor -- so it is reported once, as a
    source break, instead of twice as a removal plus an addition.

    A slot is only paired when it is unambiguous on both sides; ambiguity falls
    back to remove + add, which is the more conservative reading.
    """

    gone: dict[tuple[str, str, str, int], list[str]] = {}
    for identity in set(left) - set(right):
        slot = _wire_slot(left[identity])
        if slot is not None:
            gone.setdefault(slot, []).append(identity)
    fresh: dict[tuple[str, str, str, int], list[str]] = {}
    for identity in set(right) - set(left):
        slot = _wire_slot(right[identity])
        if slot is not None:
            fresh.setdefault(slot, []).append(identity)

    renames: dict[str, ApiChange] = {}
    for slot, before_ids in sorted(gone.items()):
        after_ids = fresh.get(slot, [])
        if len(before_ids) != 1 or len(after_ids) != 1:
            continue
        before_id, after_id = before_ids[0], after_ids[0]
        member = left[before_id]
        renames[before_id] = ApiChange(
            identity=before_id,
            change="wire-member-renamed",
            impact=CompatibilityImpact.SOURCE_BREAK,
            detail=(
                f"{member.kind} kept wire number {slot[3]} but changed name; the binary encoding still "
                "decodes, while the JSON and text encodings and every generated accessor do not"
            ),
            before=before_id,
            after=after_id,
            path=member.path,
        )
    return renames


def _removal_impact(member: ApiMember) -> CompatibilityImpact:
    if member.wire_number is not None or member.kind in ("api-contract", "event-contract", "wire-field"):
        return CompatibilityImpact.WIRE_BREAK
    if member.kind in ("type", "method", "field", "property"):
        return CompatibilityImpact.BINARY_BREAK
    return CompatibilityImpact.SOURCE_BREAK


def _compare_member(before: ApiMember, after: ApiMember) -> list[ApiChange]:
    changes: list[ApiChange] = []

    if before.wire_number != after.wire_number:
        changes.append(
            ApiChange(
                identity=before.identity,
                change="wire-number-changed",
                impact=CompatibilityImpact.WIRE_BREAK,
                detail=(
                    f"wire number changed {before.wire_number} -> {after.wire_number}; "
                    "the wire carries the number, not the name"
                ),
                before=str(before.wire_number),
                after=str(after.wire_number),
                path=after.path,
            )
        )

    if before.visibility != after.visibility:
        widened = after.visibility in PUBLIC_VISIBILITIES and before.visibility not in PUBLIC_VISIBILITIES
        changes.append(
            ApiChange(
                identity=before.identity,
                change="visibility-changed",
                impact=CompatibilityImpact.ADDITIVE if widened else CompatibilityImpact.SOURCE_BREAK,
                detail=f"visibility {before.visibility} -> {after.visibility}",
                before=before.visibility,
                after=after.visibility,
                path=after.path,
            )
        )

    if before.signature != after.signature and (before.signature or after.signature):
        changes.extend(_compare_signature(before, after))

    before_bases = before.attributes.get("bases")
    after_bases = after.attributes.get("bases")
    if before_bases != after_bases and (before_bases or after_bases):
        removed = set(before_bases or ()) - set(after_bases or ())
        changes.append(
            ApiChange(
                identity=before.identity,
                change="base-types-changed",
                impact=CompatibilityImpact.BINARY_BREAK
                if removed
                else CompatibilityImpact.BEHAVIOR_RISK,
                detail=f"base types {before_bases} -> {after_bases}",
                before=str(before_bases),
                after=str(after_bases),
                path=after.path,
            )
        )

    if bool(before.attributes.get("async")) != bool(after.attributes.get("async")):
        changes.append(
            ApiChange(
                identity=before.identity,
                change="sync-async-changed",
                impact=CompatibilityImpact.SOURCE_BREAK,
                detail="a function changed between sync and async; every call site must change",
                path=after.path,
            )
        )
    return changes


def _compare_signature(before: ApiMember, after: ApiMember) -> list[ApiChange]:
    before_params = before.parameters
    after_params = after.parameters
    before_names = [item.split(":")[0].split("=")[0].strip() for item in before_params]
    after_names = [item.split(":")[0].split("=")[0].strip() for item in after_params]

    removed = [item for item in before_names if item not in after_names and item not in ("*", "/")]
    added_required = [
        item
        for item in after.required_parameters
        if item.split(":")[0].split("=")[0].strip() not in before_names
    ]
    reordered = (
        [item for item in before_names if item in after_names]
        != [item for item in after_names if item in before_names]
    )

    changes: list[ApiChange] = []
    if removed:
        changes.append(
            ApiChange(
                identity=before.identity,
                change="parameter-removed",
                impact=CompatibilityImpact.SOURCE_BREAK,
                detail="parameter(s) removed: " + ", ".join(removed),
                before=before.signature,
                after=after.signature,
                path=after.path,
            )
        )
    if added_required:
        changes.append(
            ApiChange(
                identity=before.identity,
                change="required-parameter-added",
                impact=CompatibilityImpact.SOURCE_BREAK,
                detail=(
                    "required parameter(s) added: "
                    + ", ".join(added_required)
                    + "; an added parameter without a default is not an additive change"
                ),
                before=before.signature,
                after=after.signature,
                path=after.path,
            )
        )
    if reordered:
        changes.append(
            ApiChange(
                identity=before.identity,
                change="parameter-order-changed",
                impact=CompatibilityImpact.SOURCE_BREAK,
                detail="positional parameter order changed",
                before=before.signature,
                after=after.signature,
                path=after.path,
            )
        )
    if not changes:
        changes.append(
            ApiChange(
                identity=before.identity,
                change="signature-changed",
                impact=CompatibilityImpact.BEHAVIOR_RISK,
                detail=(
                    "signature text changed without a structural break (types, defaults or annotations); "
                    "verify the serialisation and default semantics"
                ),
                before=before.signature,
                after=after.signature,
                path=after.path,
            )
        )
    return changes


# ---------------------------------------------------------------------------
# Policy decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompatibilityDecision:
    allowed: bool
    policy: str
    violations: tuple[ApiChange, ...]
    required_measures: tuple[str, ...]
    risk_class: RiskClass

    def to_payload(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "policy": self.policy,
            "violations": [item.to_payload() for item in self.violations],
            "requiredMeasures": list(self.required_measures),
            "riskClass": self.risk_class.value,
        }


def decide(diff: ApiDiff, *, public_api_policy: str, binary_policy: str = "best-effort") -> CompatibilityDecision:
    """Apply the request's compatibility constraints to a diff."""

    violations: list[ApiChange] = []
    measures: list[str] = []

    if public_api_policy == "strict":
        violations.extend(
            item for item in diff.changes if item.impact is not CompatibilityImpact.ADDITIVE
        )
        violations.extend(
            item for item in diff.of(CompatibilityImpact.ADDITIVE) if item.change == "added"
        )
        if diff.of(CompatibilityImpact.ADDITIVE):
            measures.append(
                "strict source compatibility forbids surface additions as well as removals; "
                "publish additions in a new version instead"
            )
    elif public_api_policy == "backward-compatible":
        violations.extend(
            item
            for item in diff.changes
            if item.impact in (CompatibilityImpact.SOURCE_BREAK, CompatibilityImpact.WIRE_BREAK)
        )
    elif public_api_policy == "versioned-break":
        if diff.breaks:
            measures.append("a versioned break requires a new published version and a deprecation window")
    elif public_api_policy == "approved-break":
        if diff.breaks:
            measures.append("an approved break requires a signed approval bound to this exact API diff")

    if binary_policy == "strict":
        violations.extend(diff.of(CompatibilityImpact.BINARY_BREAK))

    for change in diff.of(CompatibilityImpact.ADDITIVE):
        if change.change == "added" and change.identity.endswith(("Request", "Response", "Event")):
            measures.append(
                f"new field on '{change.identity}': verify the default value an old consumer will deserialise"
            )
    if diff.behavior_risks:
        measures.append(
            f"{diff.behavior_risks} change(s) preserve the name but may change behaviour; "
            "name stability is not behaviour stability"
        )

    if diff.wire_breaks:
        risk = RiskClass.R4
    elif diff.binary_breaks or diff.source_breaks:
        risk = RiskClass.R3
    elif diff.behavior_risks:
        risk = RiskClass.R2
    elif diff.changes:
        risk = RiskClass.R1
    else:
        risk = RiskClass.R0

    unique = tuple(dict.fromkeys(violations))
    return CompatibilityDecision(
        allowed=not unique,
        policy=public_api_policy,
        violations=unique,
        required_measures=tuple(dict.fromkeys(measures)),
        risk_class=risk,
    )


@dataclass(frozen=True, slots=True)
class DeprecationStep:
    phase: str
    description: str
    gate: str

    def to_payload(self) -> dict[str, Any]:
        return {"phase": self.phase, "description": self.description, "gate": self.gate}


def deprecation_plan(diff: ApiDiff) -> tuple[DeprecationStep, ...]:
    """The expand-deprecate-contract lifecycle for the breaks in ``diff``."""

    if not diff.breaks:
        return ()
    removed = [item.identity for item in diff.breaks if item.change == "removed"]
    steps = [
        DeprecationStep(
            "expand",
            "add the replacement surface alongside the old one; both must work simultaneously",
            "api-compatibility",
        ),
        DeprecationStep(
            "annotate",
            "mark the old surface deprecated with a removal version and a migration pointer",
            "api-compatibility",
        ),
        DeprecationStep(
            "observe",
            "publish usage telemetry for the old surface until it reaches zero over a full release window",
            "old-path-usage-zero",
        ),
        DeprecationStep(
            "approve",
            "obtain sign-off bound to this exact API diff digest",
            "human-approval",
        ),
        DeprecationStep(
            "contract",
            "remove the old surface: " + (", ".join(removed[:20]) if removed else "the deprecated members"),
            "api-compatibility",
        ),
    ]
    return tuple(steps)


def adapter_patch_outline(diff: ApiDiff) -> tuple[dict[str, Any], ...]:
    """What a compatibility shim would have to provide for each break."""

    outlines: list[dict[str, Any]] = []
    for change in diff.breaks:
        if change.change == "removed":
            strategy = "re-export a deprecated forwarding stub"
        elif change.change == "required-parameter-added":
            strategy = "add an overload or a default so existing call sites keep compiling"
        elif change.change == "parameter-removed":
            strategy = "keep the parameter, ignore it, and mark it deprecated"
        elif change.change == "wire-number-changed":
            strategy = "restore the original wire number and add the new field under a fresh number"
        elif change.change == "sync-async-changed":
            strategy = "keep a synchronous wrapper delegating to the asynchronous implementation"
        else:
            strategy = "provide an explicit adapter and cover it with a contract test"
        outlines.append(
            {
                "identity": change.identity,
                "impact": change.impact.value,
                "strategy": strategy,
                "path": change.path,
            }
        )
    return tuple(outlines)


def consumer_matrix(index: SemanticIndex, surface: ApiSurface) -> tuple[dict[str, Any], ...]:
    """Who consumes each published member, and whether that set is knowable."""

    rows: list[dict[str, Any]] = []
    by_qualified: dict[str, str] = {}
    for entity in index.entities:
        if entity.qualified_name:
            by_qualified.setdefault(entity.qualified_name, entity.id)
    for member in surface.members:
        entity_id = by_qualified.get(member.identity)
        consumers = sorted({item.from_id for item in index.incoming(entity_id)}) if entity_id else []
        rows.append(
            {
                "identity": member.identity,
                "path": member.path,
                "inRepositoryConsumers": len(consumers),
                "externalVisibility": "unknown-external" if not consumers else "in-repository",
                "removalRisk": "high" if not consumers else "measurable",
            }
        )
    return tuple(rows)


def surface_from_files(files: Mapping[str, str], index: SemanticIndex) -> ApiSurface:
    """Combined language surface plus wire surface for one revision."""

    language = extract_surface(index)
    wire = extract_wire_surface(files)
    return ApiSurface(
        members=tuple(sorted((*language.members, *wire.members), key=lambda item: item.identity)),
        revision=index.revision,
    )


def summarise(diff: ApiDiff, decision: CompatibilityDecision) -> dict[str, Any]:
    return {
        "apiDiff": diff.to_payload(),
        "compatibilityDecision": decision.to_payload(),
        "deprecationPlan": [item.to_payload() for item in deprecation_plan(diff)],
        "adapterPatch": list(adapter_patch_outline(diff)),
    }


def changed_identities(diff: ApiDiff) -> Sequence[str]:
    return tuple(sorted({item.identity for item in diff.changes}))


__all__ = [
    "PUBLIC_VISIBILITIES",
    "ApiChange",
    "ApiDiff",
    "ApiMember",
    "ApiSurface",
    "CompatibilityDecision",
    "DeprecationStep",
    "adapter_patch_outline",
    "consumer_matrix",
    "decide",
    "deprecation_plan",
    "diff_surfaces",
    "extract_surface",
    "extract_wire_surface",
    "summarise",
    "surface_from_files",
]

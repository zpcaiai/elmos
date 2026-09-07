"""Exact, allowlisted PDHI v1 Skill and capability registries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from ._catalog import SOURCE_CAPABILITY_CATALOG, SOURCE_KERNEL_LABELS
from .canonical import digest_object
from .errors import (
    AmbiguousCapabilityError,
    RegistryError,
    UnknownCapabilityError,
    UnknownSkillError,
)


PACKAGE_NAME = "elmos-proof-driven-harness-intelligence"
PACKAGE_VERSION = "1.0.0"
ARCHIVE_ROOT = f"{PACKAGE_NAME}-v{PACKAGE_VERSION}"
ARCHIVE_SHA256 = "9dcf9a4ac6eafad4d24df12dfc4e31da2fb5c20bde840611d81c43fa9607910e"
EXTERNAL_EVIDENCE_STATUS = "NOT_RUN"
CERTIFICATION_STATUS = "NOT_CERTIFIED"


class ImplementationStatus(StrEnum):
    DECLARED = "DECLARED_RUNTIME_UNQUALIFIED"
    LOCAL = "LOCAL"
    PARTIAL = "PARTIAL"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


@dataclass(frozen=True, slots=True)
class SkillDescriptor:
    skill_id: str
    name: str
    source_owner: str
    priority: str
    source_member: str
    source_sha256: str
    version: str = PACKAGE_VERSION
    kind: str = "kernel"
    implementation_status: ImplementationStatus = ImplementationStatus.DECLARED
    external_evidence_status: str = EXTERNAL_EVIDENCE_STATUS
    certification_status: str = CERTIFICATION_STATUS

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "source_owner": self.source_owner,
            "priority": self.priority,
            "source_member": self.source_member,
            "source_sha256": self.source_sha256,
            "version": self.version,
            "kind": self.kind,
            "implementation_status": self.implementation_status.value,
            "external_evidence_status": self.external_evidence_status,
            "certification_status": self.certification_status,
        }


@dataclass(frozen=True, slots=True)
class CapabilityOccurrence:
    occurrence_id: str
    name: str
    owner: str
    source_label: str
    source_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "occurrence_id": self.occurrence_id,
            "name": self.name,
            "owner": self.owner,
            "source_label": self.source_label,
            "source_index": self.source_index,
        }


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """Canonical capability identity plus every source occurrence."""

    operation_id: str
    name: str
    canonical_owner: str
    occurrence_owners: tuple[str, ...]
    occurrence_ids: tuple[str, ...]
    source_ambiguous: bool
    implementation_status: ImplementationStatus = ImplementationStatus.DECLARED
    external_evidence_status: str = EXTERNAL_EVIDENCE_STATUS
    certification_status: str = CERTIFICATION_STATUS

    @property
    def owner(self) -> str:
        return self.canonical_owner

    @property
    def capability_id(self) -> str:
        return self.operation_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "name": self.name,
            "canonical_owner": self.canonical_owner,
            "occurrence_owners": list(self.occurrence_owners),
            "occurrence_ids": list(self.occurrence_ids),
            "source_ambiguous": self.source_ambiguous,
            "implementation_status": self.implementation_status.value,
            "external_evidence_status": self.external_evidence_status,
            "certification_status": self.certification_status,
        }


CapabilityDescriptor = OperationSpec


@dataclass(frozen=True, slots=True)
class CapabilityResolution:
    operation: OperationSpec
    selected_owner: str
    occurrence_id: str


@dataclass(frozen=True, slots=True)
class CrosswalkEntry:
    source_skill_id: str
    source_name: str
    v3_skill_ids: tuple[str, ...]
    relationship: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_skill_id": self.source_skill_id,
            "source_name": self.source_name,
            "v3_skill_ids": list(self.v3_skill_ids),
            "relationship": self.relationship,
            "note": self.note,
        }


_SKILLS = (
    SkillDescriptor(
        "PDHI-V1-000",
        "elmos-proof-driven-harness-intelligence",
        "ORCHESTRATOR",
        "P0",
        "SKILL.md",
        "sha256:e4c2fa1ce35620e320f99bc540d97fb4637b0c938fc7c1cbce287649a46cb3d6",
        kind="orchestrator",
    ),
    SkillDescriptor(
        "PDHI-V1-001",
        "elmos-harness-contracts",
        "K0",
        "P0",
        "00-contracts/SKILL.md",
        "sha256:7e4961743efaa01a1835749560542f385edbb54a7306a42b86d5d48c15c18921",
    ),
    SkillDescriptor(
        "PDHI-V1-002",
        "elmos-repository-semantic-intelligence",
        "K1",
        "P0",
        "10-semantic-intelligence/SKILL.md",
        "sha256:7a12b4416213bdb594254afaf8b20617eac6d0287099835184294c90756662bc",
    ),
    SkillDescriptor(
        "PDHI-V1-003",
        "elmos-transactional-semantic-transformation",
        "K2",
        "P0",
        "20-transactional-transformation/SKILL.md",
        "sha256:1d9049c5361ed497d001b346b190e2db5e61373ec98fe67d968f851fb39f33be",
    ),
    SkillDescriptor(
        "PDHI-V1-004",
        "elmos-runtime-equivalence-proof",
        "K3",
        "P0",
        "30-runtime-proof/SKILL.md",
        "sha256:3cbb654ce5542e9ad2f97f416bf0c1981b9630270da83a0a7149fe4aa9445bcc",
    ),
    SkillDescriptor(
        "PDHI-V1-005",
        "elmos-agentic-execution-runtime",
        "K4",
        "P0",
        "40-agentic-execution/SKILL.md",
        "sha256:544711137337211a6bf038039674498ece456da44681560b58d4cce7296d23ba",
    ),
    SkillDescriptor(
        "PDHI-V1-006",
        "elmos-independent-assurance",
        "K5",
        "P0",
        "50-independent-assurance/SKILL.md",
        "sha256:937002fc621a9a0c3c61dfbd2796d46b836f16e421973cee9bdf0c2b0915e214",
    ),
    SkillDescriptor(
        "PDHI-V1-007",
        "elmos-policy-invariant-engine",
        "K6",
        "P0",
        "60-policy-invariants/SKILL.md",
        "sha256:b2741abacd52f4ac1e5dd8382abe641713d4e3d0a1c4225ce1ac9ff276df08d5",
    ),
    SkillDescriptor(
        "PDHI-V1-008",
        "elmos-certified-skill-evolution",
        "K7",
        "P1",
        "70-skill-evolution/SKILL.md",
        "sha256:2584d5ac3f27c9364de4bbaad6aa34d19857f13a92875bee5dde52e31295be98",
    ),
    SkillDescriptor(
        "PDHI-V1-009",
        "elmos-harness-intelligence",
        "K8",
        "P0",
        "80-harness-intelligence/SKILL.md",
        "sha256:26a3b38e24c4855025416b515e5340eee29e7c31ceb2bb077457896cb977320c",
    ),
    SkillDescriptor(
        "PDHI-V1-010",
        "elmos-production-control-plane",
        "K9",
        "P0",
        "90-production-control-plane/SKILL.md",
        "sha256:3df01627e9e441813e62eda9ae56716f2861ef192d171d21d650dd881ed1cf74",
    ),
    SkillDescriptor(
        "PDHI-V1-011",
        "elmos-e0-e5-harness-certification",
        "K10",
        "P0",
        "95-certification/SKILL.md",
        "sha256:9030d4eea6bc2217cf8db666432be873f87698fb56d9fcc9cd1efd5a1c0d40fe",
    ),
)

SKILL_REGISTRY: Mapping[str, SkillDescriptor] = MappingProxyType(
    {skill.name: skill for skill in _SKILLS}
)
SKILL_BY_ID: Mapping[str, SkillDescriptor] = MappingProxyType(
    {skill.skill_id: skill for skill in _SKILLS}
)


_occurrences: list[CapabilityOccurrence] = []
for owner, names in SOURCE_CAPABILITY_CATALOG.items():
    for source_index, name in enumerate(names, 1):
        _occurrences.append(
            CapabilityOccurrence(
                occurrence_id=f"PDHI-OCC-{len(_occurrences) + 1:03d}",
                name=name,
                owner=owner,
                source_label=SOURCE_KERNEL_LABELS[owner],
                source_index=source_index,
            )
        )
CAPABILITY_OCCURRENCES = tuple(_occurrences)

_grouped: dict[str, list[CapabilityOccurrence]] = {}
for occurrence in CAPABILITY_OCCURRENCES:
    _grouped.setdefault(occurrence.name, []).append(occurrence)

_CANONICAL_DUPLICATE_OWNERS = {
    "phase-model-handoff": "K8",
    "steer-agent": "K9",
}

_operations: dict[str, OperationSpec] = {}
for index, (name, source_occurrences) in enumerate(_grouped.items(), 1):
    owners = tuple(item.owner for item in source_occurrences)
    canonical_owner = _CANONICAL_DUPLICATE_OWNERS.get(name, owners[0])
    _operations[name] = OperationSpec(
        operation_id=f"PDHI-OP-{index:03d}",
        name=name,
        canonical_owner=canonical_owner,
        occurrence_owners=owners,
        occurrence_ids=tuple(item.occurrence_id for item in source_occurrences),
        source_ambiguous=len(source_occurrences) > 1,
    )

CAPABILITY_REGISTRY: Mapping[str, OperationSpec] = MappingProxyType(_operations)
OPERATION_REGISTRY = CAPABILITY_REGISTRY


def resolve_skill(name_or_id: str) -> SkillDescriptor:
    skill = SKILL_REGISTRY.get(name_or_id) or SKILL_BY_ID.get(name_or_id)
    if skill is None:
        raise UnknownSkillError(
            "Skill is not in the PDHI v1 allowlist",
            code="UNKNOWN_SKILL",
            details={"skill": name_or_id},
        )
    return skill


def canonical_capability(name: str) -> OperationSpec:
    operation = CAPABILITY_REGISTRY.get(name)
    if operation is None:
        raise UnknownCapabilityError(
            "capability is not in the PDHI v1 allowlist",
            code="UNKNOWN_CAPABILITY",
            details={"capability": name},
        )
    return operation


def resolve_capability(
    name: str,
    *,
    owner: str | None = None,
) -> CapabilityResolution:
    operation = canonical_capability(name)
    if operation.source_ambiguous and owner is None:
        raise AmbiguousCapabilityError(
            "source capability name has multiple owners; explicit owner is required",
            code="AMBIGUOUS_CAPABILITY",
            details={
                "capability": name,
                "owners": operation.occurrence_owners,
                "canonical_owner": operation.canonical_owner,
            },
        )
    selected_owner = operation.canonical_owner if owner is None else owner
    if selected_owner not in operation.occurrence_owners:
        raise RegistryError(
            "owner does not declare this capability",
            code="CAPABILITY_OWNER_MISMATCH",
            details={
                "capability": name,
                "owner": selected_owner,
                "declared_owners": operation.occurrence_owners,
            },
        )
    occurrence_id = operation.occurrence_ids[
        operation.occurrence_owners.index(selected_owner)
    ]
    return CapabilityResolution(operation, selected_owner, occurrence_id)


resolve_operation = resolve_capability


_CROSSWALK_ROWS = (
    (
        "elmos-proof-driven-harness-intelligence",
        tuple(f"ELMOS-V3-{index:03d}" for index in range(1, 9)),
        "orchestrates-overlap",
        "The v1 orchestrator overlaps all eight v3 kernels; it is not a v3 runtime alias.",
    ),
    (
        "elmos-harness-contracts",
        tuple(f"ELMOS-V3-{index:03d}" for index in range(1, 9)),
        "cross-cutting-contract-overlap",
        "K0 contracts cross all v3 kernels and do not create a ninth v3 kernel.",
    ),
    (
        "elmos-repository-semantic-intelligence",
        ("ELMOS-V3-002", "ELMOS-V3-003"),
        "split-across-v3-kernels",
        "Source K1 spans v3 repository intelligence and semantic compiler boundaries.",
    ),
    (
        "elmos-transactional-semantic-transformation",
        ("ELMOS-V3-005",),
        "functional-overlap",
        "Source K2 overlaps v3 transformation but is not implementation equivalence.",
    ),
    (
        "elmos-runtime-equivalence-proof",
        ("ELMOS-V3-006", "ELMOS-V3-007"),
        "split-across-v3-kernels",
        "Source K3 requires both v3 proof verification and authorized runtime execution.",
    ),
    (
        "elmos-agentic-execution-runtime",
        ("ELMOS-V3-004", "ELMOS-V3-007"),
        "split-across-v3-kernels",
        "Source K4 combines reasoning and durable harness-runtime concerns.",
    ),
    (
        "elmos-independent-assurance",
        ("ELMOS-V3-006", "ELMOS-V3-008", "ELMOS-V3-014"),
        "cross-cutting-overlap",
        "Independent assurance spans proof, certification, and the v3 trust gate.",
    ),
    (
        "elmos-policy-invariant-engine",
        ("ELMOS-V3-001", "ELMOS-V3-007", "ELMOS-V3-008", "ELMOS-V3-014"),
        "cross-cutting-overlap",
        "Policy intent, enforcement and completion remain separate v3 authorities.",
    ),
    (
        "elmos-certified-skill-evolution",
        ("ELMOS-V3-015",),
        "governed-overlap",
        "Source K7 candidates remain governed and are not auto-promoted.",
    ),
    (
        "elmos-harness-intelligence",
        ("ELMOS-V3-004", "ELMOS-V3-007"),
        "split-across-v3-kernels",
        "Model/context routing and runtime authority remain separate in v3.",
    ),
    (
        "elmos-production-control-plane",
        ("ELMOS-V3-007", "ELMOS-V3-016"),
        "cross-cutting-overlap",
        "Execution control and commercial FinOps are separate v3 responsibilities.",
    ),
    (
        "elmos-e0-e5-harness-certification",
        ("ELMOS-V3-008", "ELMOS-V3-014"),
        "certification-overlap",
        "The source gate cannot manufacture v3 certification or trust evidence.",
    ),
)

SOURCE_V3_CROSSWALK: Mapping[str, CrosswalkEntry] = MappingProxyType(
    {
        name: CrosswalkEntry(
            source_skill_id=SKILL_REGISTRY[name].skill_id,
            source_name=name,
            v3_skill_ids=v3_ids,
            relationship=relationship,
            note=note,
        )
        for name, v3_ids, relationship, note in _CROSSWALK_ROWS
    }
)


def normalized_skill_registry() -> dict[str, Any]:
    payload = {
        "schema_version": "1.0.0",
        "package": f"{PACKAGE_NAME}@{PACKAGE_VERSION}",
        "archive_sha256": ARCHIVE_SHA256,
        "skill_count": len(SKILL_REGISTRY),
        "skills": [skill.to_dict() for skill in _SKILLS],
    }
    return {**payload, "registry_digest": digest_object(payload, domain="skill-registry")}


def normalized_capability_registry() -> dict[str, Any]:
    payload = {
        "schema_version": "1.0.0",
        "package": f"{PACKAGE_NAME}@{PACKAGE_VERSION}",
        "canonical_capability_count": len(CAPABILITY_REGISTRY),
        "source_occurrence_count": len(CAPABILITY_OCCURRENCES),
        "ambiguous_source_names": {
            name: {
                "owners": list(operation.occurrence_owners),
                "canonical_owner": operation.canonical_owner,
                "unqualified_resolution": "REJECT",
            }
            for name, operation in CAPABILITY_REGISTRY.items()
            if operation.source_ambiguous
        },
        "capabilities": [
            operation.to_dict() for operation in CAPABILITY_REGISTRY.values()
        ],
        "occurrences": [item.to_dict() for item in CAPABILITY_OCCURRENCES],
    }
    return {
        **payload,
        "registry_digest": digest_object(payload, domain="capability-registry"),
    }


def normalized_v3_crosswalk() -> dict[str, Any]:
    payload = {
        "schema_version": "1.0.0",
        "source_package": f"{PACKAGE_NAME}@{PACKAGE_VERSION}",
        "target_package": "elmos-proof-driven-agentic-harness-repository-semantic-compiler@3.0.0",
        "semantics": "overlap-only-not-runtime-alias",
        "entries": [entry.to_dict() for entry in SOURCE_V3_CROSSWALK.values()],
    }
    return {**payload, "crosswalk_digest": digest_object(payload, domain="v3-crosswalk")}


_ambiguous = {
    name: operation.occurrence_owners
    for name, operation in CAPABILITY_REGISTRY.items()
    if operation.source_ambiguous
}
if len(SKILL_REGISTRY) != 12 or len(SKILL_BY_ID) != 12:
    raise RuntimeError("PDHI v1 Skill registry must contain exactly 12 Skills")
if len(CAPABILITY_OCCURRENCES) != 262:
    raise RuntimeError("PDHI v1 source catalog must contain exactly 262 occurrences")
if len(CAPABILITY_REGISTRY) != 260:
    raise RuntimeError("PDHI v1 capability registry must contain exactly 260 names")
if _ambiguous != {
    "phase-model-handoff": ("K4", "K8"),
    "steer-agent": ("K4", "K9"),
}:
    raise RuntimeError("PDHI v1 duplicate capability identities drifted")
if set(SOURCE_V3_CROSSWALK) != set(SKILL_REGISTRY):
    raise RuntimeError("PDHI v1/v3 crosswalk must cover every source Skill exactly once")


__all__ = [
    "ARCHIVE_ROOT",
    "ARCHIVE_SHA256",
    "CAPABILITY_OCCURRENCES",
    "CAPABILITY_REGISTRY",
    "CERTIFICATION_STATUS",
    "CapabilityDescriptor",
    "CapabilityOccurrence",
    "CapabilityResolution",
    "CrosswalkEntry",
    "EXTERNAL_EVIDENCE_STATUS",
    "ImplementationStatus",
    "OPERATION_REGISTRY",
    "OperationSpec",
    "PACKAGE_NAME",
    "PACKAGE_VERSION",
    "SKILL_BY_ID",
    "SKILL_REGISTRY",
    "SOURCE_CAPABILITY_CATALOG",
    "SOURCE_V3_CROSSWALK",
    "SkillDescriptor",
    "canonical_capability",
    "normalized_capability_registry",
    "normalized_skill_registry",
    "normalized_v3_crosswalk",
    "resolve_capability",
    "resolve_operation",
    "resolve_skill",
]

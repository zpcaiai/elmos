"""Explicit JSON codecs for the five governed asset managers; no object loading."""

from __future__ import annotations

from dataclasses import fields
from typing import Any, Mapping, TypeVar

from .domain import (
    CertificationStatus,
    ConsentStatus,
    ContentDigest,
    DatasetItem,
    EvidenceState,
    ExperienceEpisode,
    GateLevel,
    KnowledgeObject,
    LifecycleState,
    ModelRelease,
)
from .domain import RightsClass
from .store import StoreIntegrityError

Asset = KnowledgeObject | ExperienceEpisode | DatasetItem | ModelRelease
T = TypeVar("T", KnowledgeObject, ExperienceEpisode, DatasetItem, ModelRelease)


def asset_payload(asset: Asset) -> dict[str, Any]:
    payload = {field.name: getattr(asset, field.name) for field in fields(asset)}
    if isinstance(asset, ModelRelease):
        payload["weights_digest"] = str(asset.weights_digest)
    return payload


def restore_asset(cls: type[T], payload: Mapping[str, Any]) -> T:
    if set(payload) != {field.name for field in fields(cls)}:
        raise StoreIntegrityError("stored asset shape differs from its exact domain contract")
    values = dict(payload)
    values["evidence_state"] = EvidenceState(values["evidence_state"])
    values["certification_status"] = CertificationStatus(values["certification_status"])
    if values["certification_status"] is not CertificationStatus.NOT_CERTIFIED:
        raise StoreIntegrityError("local asset cannot assert certification")
    expected_evidence = (
        EvidenceState.REJECTED
        if cls is DatasetItem and values["quarantine"] is True
        else EvidenceState.COLLECTED_SELF_ATTESTED
    )
    if values["evidence_state"] is not expected_evidence:
        raise StoreIntegrityError("stored asset evidence is outside its local implementation")
    if cls in (KnowledgeObject, DatasetItem):
        values["rights_class"] = RightsClass(values["rights_class"])
    if cls is KnowledgeObject:
        values["training_consent"] = ConsentStatus(values["training_consent"])
    elif cls is DatasetItem:
        values["consent_status"] = ConsentStatus(values["consent_status"])
        if values["consent_status"] is not ConsentStatus.ALLOW:
            raise StoreIntegrityError("stored dataset item lacks explicit ALLOW consent")
        if not isinstance(values["quarantine"], bool):
            raise StoreIntegrityError("stored dataset quarantine must be boolean")
        if values["quarantine"] and values["quality_score"] != 0:
            raise StoreIntegrityError("quarantined dataset item cannot retain a quality score")
    elif cls is ModelRelease:
        values["weights_digest"] = ContentDigest.parse(values["weights_digest"])
        values["gate_level"] = GateLevel(values["gate_level"])
        values["status"] = LifecycleState(values["status"])
        values["skill_set"] = tuple(values["skill_set"])
        if (values["gate_level"], values["status"]) not in {
            (GateLevel.E0_SYNTACTIC, LifecycleState.PLANNED),
            (GateLevel.E1_UNIT_EVAL, LifecycleState.VERIFYING),
        }:
            raise StoreIntegrityError("stored model gate and lifecycle exceed local implementation")
        if values["external_evidence_status"] != "NOT_RUN":
            raise StoreIntegrityError("local model metadata cannot assert external evidence")
    elif cls is ExperienceEpisode:
        values["trajectory"] = tuple(values["trajectory"])
    return cls(**values)

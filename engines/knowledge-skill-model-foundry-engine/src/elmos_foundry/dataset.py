"""Deterministic, consent-bound dataset preparation with explicit quarantine."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from dataclasses import replace
import hashlib
from threading import RLock
from types import MappingProxyType
from typing import Sequence

from .authorizations import AuthorizationVerifier, require_authorization
from .asset_store import asset_payload, restore_asset
from .canonical import canonical_digest, canonical_json
from .domain import (
    CertificationStatus,
    ConsentStatus,
    DatasetItem,
    EvidenceState,
    ExperienceEpisode,
    RightsClass,
    TenantScope,
)
from .kernel import ExecutionKernel
from .store import FoundryStore


def _ratio(value: Decimal | str | float, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{label} is not a decimal ratio") from exc
    if not result.is_finite() or result < 0 or result > 1:
        raise ValueError(f"{label} must be in [0, 1]")
    return result


class DatasetFoundry:
    """Prepare local dataset records; it does not train or publish a model."""

    def __init__(
        self,
        kernel: ExecutionKernel | None = None,
        *,
        data_use_verifier: AuthorizationVerifier | None = None,
        store: FoundryStore | None = None,
    ) -> None:
        self.kernel = kernel or ExecutionKernel()
        self._data_use_verifier = data_use_verifier
        self.store = store
        self._datasets: dict[tuple[str, str, str], list[DatasetItem]] = {}
        self._lock = RLock()

    def create_dataset_from_episodes(
        self,
        dataset_name: str,
        episodes: Sequence[ExperienceEpisode],
        train_ratio: Decimal | str | float = Decimal("0.8"),
        val_ratio: Decimal | str | float = Decimal("0.1"),
        holdout_ratio: Decimal | str | float = Decimal("0.1"),
        rights_class: RightsClass = RightsClass.INTERNAL,
        training_consent: ConsentStatus = ConsentStatus.DENY,
        tenant_scope: TenantScope | None = None,
        *,
        data_use_authorization_digest: str | None = None,
    ) -> str:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.dataset.create")
        if training_consent is not ConsentStatus.ALLOW:
            raise ValueError("dataset creation requires explicit ALLOW consent")
        if not dataset_name.strip() or len(dataset_name.encode("utf-8")) > 256:
            raise ValueError("dataset_name must be non-empty and bounded")
        if not episodes or len(episodes) > 100_000:
            raise ValueError("dataset requires 1..100000 episodes")
        ratios = (
            _ratio(train_ratio, "train_ratio"),
            _ratio(val_ratio, "val_ratio"),
            _ratio(holdout_ratio, "holdout_ratio"),
        )
        if sum(ratios, Decimal("0")) != Decimal("1"):
            raise ValueError("dataset split ratios must sum exactly to 1")
        if any(
            episode.tenant_id != scope.tenant_id or episode.project_id != scope.project_id
            for episode in episodes
        ):
            raise ValueError("cross-tenant or cross-project episodes fail closed")
        ordered = sorted(episodes, key=lambda item: item.episode_id)
        if len({episode.episode_id for episode in ordered}) != len(ordered):
            raise ValueError("dataset episodes must have unique identities")
        episode_digests = [
            canonical_digest(
                {
                    "episode_id": episode.episode_id,
                    "release_id": episode.release_id,
                    "task_type": episode.task_type,
                    "task_goal": episode.task_goal,
                    "trajectory": episode.trajectory,
                    "outcome": episode.outcome,
                    "reward_score": episode.reward_score,
                    "verifier_evidence": episode.verifier_evidence,
                }
            )
            for episode in ordered
        ]
        authorization = require_authorization(
            self._data_use_verifier,
            authorization_type="dataset-data-use",
            receipt_digest=data_use_authorization_digest,
            request={
                "dataset_name": dataset_name,
                "episode_digests": episode_digests,
                "ratios": [str(ratio) for ratio in ratios],
                "rights_class": rights_class.value,
                "training_consent": training_consent.value,
            },
            scope=scope,
        )
        dataset_identity = canonical_digest(
            {
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
                "dataset_name": dataset_name,
                "episodes": [episode.episode_id for episode in ordered],
                "ratios": [str(ratio) for ratio in ratios],
                "authorization": data_use_authorization_digest,
                "authorization_request": authorization.request_digest,
            }
        )
        dataset_id = "ds-" + dataset_identity.removeprefix("sha256:")[:32]
        items: list[DatasetItem] = []
        train_edge = ratios[0]
        val_edge = ratios[0] + ratios[1]
        for episode in ordered:
            value = Decimal(
                int(hashlib.sha256(episode.episode_id.encode("utf-8")).hexdigest(), 16)
            ) / Decimal(2**256)
            split = "train" if value < train_edge else "val" if value < val_edge else "holdout"
            item_identity = canonical_digest(
                {"dataset_id": dataset_id, "episode_id": episode.episode_id, "split": split}
            )
            items.append(
                DatasetItem(
                    item_id="di-" + item_identity.removeprefix("sha256:")[:32],
                    dataset_id=dataset_id,
                    tenant_id=scope.tenant_id,
                    project_id=scope.project_id,
                    split=split,
                    input_text=f"Goal: {episode.task_goal}\nTask Type: {episode.task_type}",
                    target_text=canonical_json(episode.outcome),
                    metadata=MappingProxyType(
                        {
                            "episode_id": episode.episode_id,
                            "reward": episode.reward_score,
                            "data_use_authorization_digest": data_use_authorization_digest,
                            "data_use_request_digest": authorization.request_digest,
                            "independent_corpus_status": "NOT_ESTABLISHED",
                        }
                    ),
                    rights_class=rights_class,
                    consent_status=training_consent,
                    quality_score=episode.reward_score,
                    quarantine=False,
                    evidence_state=EvidenceState.COLLECTED_SELF_ATTESTED,
                    certification_status=CertificationStatus.NOT_CERTIFIED,
                )
            )
        with self._lock:
            if self.store is not None:
                manifest = {
                    "tenant_id": scope.tenant_id,
                    "project_id": scope.project_id,
                    "dataset_id": dataset_id,
                    "dataset_name": dataset_name,
                    "item_count": len(items),
                    "request_digest": dataset_identity,
                    "data_use_authorization_digest": data_use_authorization_digest,
                    "data_use_request_digest": authorization.request_digest,
                }
                self.store._create_assets_after_verified_authorization(
                    scope,
                    (
                        ("dataset", dataset_id, "", dataset_identity, manifest),
                        *(
                            (
                                "dataset_item",
                                item.item_id,
                                dataset_id,
                                canonical_digest(asset_payload(item)),
                                asset_payload(item),
                            )
                            for item in items
                        ),
                    ),
                )
            else:
                # An exact retry must never remove a prior quarantine decision.
                self._datasets.setdefault((scope.tenant_id, scope.project_id, dataset_id), items)
        return dataset_id

    def get_dataset_items(
        self,
        dataset_id: str,
        split: str | None = None,
        tenant_scope: TenantScope | None = None,
        *,
        limit: int = 1000,
        after_id: str = "",
    ) -> Sequence[DatasetItem]:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.dataset.read")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("dataset query limit must be in [1, 1000]")
        if self.store is not None:
            filters: dict[str, str | bool] = {"quarantine": False}
            if split is not None:
                filters["split"] = split
            return tuple(
                restore_asset(DatasetItem, record.payload)
                for record in self.store.query_assets(
                    scope,
                    "dataset_item",
                    parent_id=dataset_id,
                    limit=limit,
                    after_id=after_id,
                    filters=filters,
                )
            )
        with self._lock:
            items = tuple(self._datasets.get((scope.tenant_id, scope.project_id, dataset_id), ()))
        return tuple(
            item
            for item in sorted(items, key=lambda item: item.item_id)
            if not item.quarantine
            and item.item_id > after_id
            and (split is None or item.split == split)
        )[:limit]

    def quarantine_item(self, item_id: str, tenant_scope: TenantScope | None = None) -> bool:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.dataset.quarantine")
        if self.store is not None:
            record = self.store.get_asset(scope, "dataset_item", item_id)
            if record is None:
                return False
            item = restore_asset(DatasetItem, record.payload)
            if item.quarantine:
                return True
            updated = replace(
                item, quality_score=0.0, quarantine=True, evidence_state=EvidenceState.REJECTED
            )
            self.store.update_asset(
                scope,
                "dataset_item",
                item_id,
                record.revision,
                asset_payload(updated),
                event_type="dataset.item.quarantined",
                event_payload={"dataset_id": item.dataset_id},
            )
            return True
        with self._lock:
            for key, items in self._datasets.items():
                if key[:2] != (scope.tenant_id, scope.project_id):
                    continue
                for index, item in enumerate(items):
                    if item.item_id != item_id:
                        continue
                    items[index] = DatasetItem(
                        item_id=item.item_id,
                        dataset_id=item.dataset_id,
                        tenant_id=item.tenant_id,
                        project_id=item.project_id,
                        split=item.split,
                        input_text=item.input_text,
                        target_text=item.target_text,
                        metadata=item.metadata,
                        rights_class=item.rights_class,
                        consent_status=item.consent_status,
                        quality_score=0.0,
                        quarantine=True,
                        evidence_state=EvidenceState.REJECTED,
                        certification_status=CertificationStatus.NOT_CERTIFIED,
                    )
                    return True
        return False


__all__ = ["DatasetFoundry"]

"""Dataset foundry, split calibration, consent filtering, and quarantine for Elmos Foundry.

Converts verified experience episodes into calibrated, permission-compliant training datasets.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
import uuid
from typing import Any, Mapping, Sequence

from .domain import (
    ConsentStatus,
    ContentDigest,
    DatasetItem,
    ExperienceEpisode,
    RightsClass,
    TenantScope,
)
from .kernel import ExecutionKernel


class DatasetFoundry:
    """Enterprise training dataset foundry and curator."""

    def __init__(self, kernel: ExecutionKernel | None = None) -> None:
        self.kernel = kernel or ExecutionKernel()
        self._datasets: dict[str, list[DatasetItem]] = {}  # dataset_id -> list of DatasetItem
        self._quarantined_items: set[str] = set()

    def create_dataset_from_episodes(
        self,
        dataset_name: str,
        episodes: Sequence[ExperienceEpisode],
        train_ratio: float = 0.8,
        val_ratio: float = 0.1,
        holdout_ratio: float = 0.1,
        rights_class: RightsClass = RightsClass.INTERNAL,
        training_consent: ConsentStatus = ConsentStatus.ALLOW,
        tenant_scope: TenantScope | None = None,
    ) -> str:
        scope = tenant_scope or self.kernel.current_tenant
        if training_consent != ConsentStatus.ALLOW:
            raise ValueError(f"Cannot create training dataset when consent is {training_consent}")

        dataset_id = f"ds-{uuid.uuid4().hex[:12]}"
        items: list[DatasetItem] = []

        for ep in episodes:
            if ep.tenant_id != scope.tenant_id:
                continue

            # Deterministic split allocation based on hash
            h_val = int(hashlib.md5(ep.episode_id.encode()).hexdigest(), 16) / float(1 << 128)
            if h_val < train_ratio:
                split = "train"
            elif h_val < (train_ratio + val_ratio):
                split = "val"
            else:
                split = "holdout"

            # Formulate instruction & target from trajectory
            prompt = f"Goal: {ep.task_goal}\nTask Type: {ep.task_type}"
            target = json.dumps(ep.outcome, sort_keys=True, ensure_ascii=False)

            item = DatasetItem(
                item_id=str(uuid.uuid4()),
                dataset_id=dataset_id,
                tenant_id=scope.tenant_id,
                split=split,
                input_text=prompt,
                target_text=target,
                metadata={"episode_id": ep.episode_id, "reward": ep.reward_score},
                rights_class=rights_class,
                consent_status=training_consent,
                quality_score=ep.reward_score,
                quarantine=False,
            )
            items.append(item)

        self._datasets[dataset_id] = items
        return dataset_id

    def get_dataset_items(
        self,
        dataset_id: str,
        split: str | None = None,
        tenant_scope: TenantScope | None = None,
    ) -> Sequence[DatasetItem]:
        scope = tenant_scope or self.kernel.current_tenant
        items = self._datasets.get(dataset_id, [])
        filtered = [
            i for i in items
            if i.tenant_id == scope.tenant_id
            and not i.quarantine
            and (split is None or i.split == split)
        ]
        return filtered

    def quarantine_item(self, item_id: str) -> None:
        self._quarantined_items.add(item_id)
        for items in self._datasets.values():
            for idx, item in enumerate(items):
                if item.item_id == item_id:
                    # Update quarantine flag
                    items[idx] = DatasetItem(
                        item_id=item.item_id,
                        dataset_id=item.dataset_id,
                        tenant_id=item.tenant_id,
                        split=item.split,
                        input_text=item.input_text,
                        target_text=item.target_text,
                        metadata=item.metadata,
                        rights_class=item.rights_class,
                        consent_status=item.consent_status,
                        quality_score=0.0,
                        quarantine=True,
                    )

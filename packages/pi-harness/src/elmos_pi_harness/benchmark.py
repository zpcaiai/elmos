"""Provider-neutral campaign and benchmark orchestration.

Adapters produce observations only.  ``validated_success`` can be populated
only by the separately supplied verifier, preventing a runner from declaring
its own benchmark pass.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .canonical import require_nonempty
from .persistence import DurableStore


class BenchmarkAdapter(Protocol):
    def discover(self) -> Mapping[str, Any]: ...
    def run(self, *, repository: str, revision: str, task_case: str, timeout_seconds: int) -> Mapping[str, Any]: ...


class BenchmarkVerifier(Protocol):
    def __call__(self, observation: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class CampaignDefinition:
    campaign_id: str
    name: str
    mode: str
    systems: tuple[str, ...]
    task_suite: str
    repositories: tuple[str, ...]
    repetitions: int
    required_evidence_level: str = "E3"

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CampaignDefinition:
        systems = tuple(require_nonempty(item, "systems[]", 256) for item in value.get("systems", []))
        repositories = tuple(require_nonempty(item, "repositories[]", 2048) for item in value.get("repositories", []))
        campaign_id = str(uuid.UUID(str(value.get("id", value.get("campaign_id", "")))))
        repetitions = int(value.get("repetitions", 0))
        if not systems or not repositories or repetitions < 1:
            raise ValueError("campaign requires systems, repositories and positive repetitions")
        if value.get("mode") not in {"matched-model", "native-product", "golden-route", "chaos"}:
            raise ValueError("unsupported campaign mode")
        if value.get("required_evidence_level", "E3") not in {"E3", "E4", "E5", "E6", "E7"}:
            raise ValueError("unsupported evidence level")
        return cls(campaign_id, require_nonempty(value.get("name"), "name", 256), str(value["mode"]), systems, require_nonempty(value.get("task_suite"), "task_suite", 512), repositories, repetitions, str(value.get("required_evidence_level", "E3")))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.campaign_id, "name": self.name, "mode": self.mode, "systems": list(self.systems), "task_suite": self.task_suite, "repositories": list(self.repositories), "repetitions": self.repetitions, "required_evidence_level": self.required_evidence_level}


class CampaignRunner:
    def __init__(self, store: DurableStore, adapters: Mapping[str, BenchmarkAdapter]) -> None:
        self.store = store
        self.adapters = dict(adapters)

    def run(self, tenant_id: str, campaign: CampaignDefinition, *, verifier: BenchmarkVerifier | None = None, timeout_seconds: int = 3600) -> dict[str, Any]:
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")
        missing = sorted(set(campaign.systems) - set(self.adapters))
        if missing:
            raise ValueError("missing benchmark adapters: " + ",".join(missing))
        self.store.create_campaign(tenant_id, campaign.campaign_id, campaign.name, campaign.mode, campaign.to_dict())
        runs: list[dict[str, Any]] = []
        for system in campaign.systems:
            profile = dict(self.adapters[system].discover())
            for repository in campaign.repositories:
                if not os.path.isdir(repository):
                    raise ValueError(f"repository is not a directory: {repository}")
                revision = str(profile.get("revision", "unknown"))
                for task_case in (campaign.task_suite,):
                    for repetition in range(1, campaign.repetitions + 1):
                        run_id = str(uuid.uuid4())
                        observation = dict(self.adapters[system].run(repository=repository, revision=revision, task_case=task_case, timeout_seconds=timeout_seconds))
                        verdict = dict(verifier(observation)) if verifier is not None else {"validated_success": None, "evidence_level": "NOT_RUN"}
                        evidence_level = verdict.get("evidence_level", "E3" if verifier else "NOT_RUN")
                        if evidence_level not in {"E3", "E4", "E5", "E6", "E7", "NOT_RUN"}:
                            raise ValueError("verifier returned an invalid evidence level")
                        result = {
                            "run_id": run_id, "system": system, "system_version": profile.get("version"),
                            "repo_revision": revision, "task_case": task_case, "repetition": repetition,
                            "validated_success": verdict.get("validated_success"),
                            "wall_clock_ms": int(observation.get("wall_clock_ms", 0)),
                            "evidence_level": evidence_level,
                            "observation": observation, "verdict": verdict,
                        }
                        self.store.record_benchmark_run(tenant_id, campaign.campaign_id, result)
                        runs.append(result)
        return {"campaign_id": campaign.campaign_id, "runs": runs, "validated_by": "external_verifier" if verifier else None}

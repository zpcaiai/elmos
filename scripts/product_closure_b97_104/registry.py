#!/usr/bin/env python3
"""Skill Registry for Batch 97-104 Product Closure.

Loads and indexes all 128 skills from docs/batch97-104/installed-manifest.json
and maps each batch to its canonical closure archetype.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from scripts.product_closure_b97_104.archetypes import (
    BaseClosureArchetype,
    get_closure_archetype,
)
from scripts.product_closure_b97_104.errors import SkillNotFoundError

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "docs/batch97-104/installed-manifest.json"

BATCH_TO_ARCHETYPE: dict[int, str] = {
    97: "estate-inventory-closure",
    98: "contract-certification-closure",
    99: "effect-messaging-closure",
    100: "sandbox-profile-closure",
    101: "route-discovery-closure",
    102: "verification-testing-closure",
    103: "independent-verifier-closure",
    104: "release-environment-closure",
}


@dataclass(frozen=True)
class ClosureSkill:
    batch: int
    source_id: str
    source_key: str
    source_name: str
    installed_name: str
    installed_path: str
    installed_sha256: str
    archetype_name: str

    def get_archetype_instance(self) -> BaseClosureArchetype:
        return get_closure_archetype(self.archetype_name)


class ProductClosureRegistry:
    """Registry indexing all 128 skills across Batches 97-104."""

    def __init__(self, manifest_file: Path = MANIFEST_PATH) -> None:
        self.manifest_file = manifest_file
        self._by_id: dict[str, ClosureSkill] = {}
        self._by_name: dict[str, ClosureSkill] = {}
        self._by_batch: dict[int, list[ClosureSkill]] = {}
        self._load()

    def _load(self) -> None:
        raw = json.loads(self.manifest_file.read_text(encoding="utf-8"))
        self.package_name = raw.get("package", "elmos-codex-skills-batch97-104-complete")
        self.batches = list(range(97, 105))

        for entry in raw.get("skills", []):
            batch = entry["batch"]
            archetype = BATCH_TO_ARCHETYPE.get(batch, "estate-inventory-closure")

            skill = ClosureSkill(
                batch=batch,
                source_id=entry["source_id"],
                source_key=entry["source_key"],
                source_name=entry["source_name"],
                installed_name=entry["installed_name"],
                installed_path=entry["installed_path"],
                installed_sha256=entry["installed_sha256"],
                archetype_name=archetype,
            )
            self._by_id[skill.source_id] = skill
            self._by_name[skill.installed_name] = skill
            self._by_batch.setdefault(batch, []).append(skill)

    def get_by_id(self, source_id: str) -> ClosureSkill:
        if source_id not in self._by_id:
            raise SkillNotFoundError(f"Closure skill with ID {source_id} not found")
        return self._by_id[source_id]

    def get_by_name(self, name: str) -> ClosureSkill:
        if name not in self._by_name:
            raise SkillNotFoundError(f"Closure skill with name {name} not found")
        return self._by_name[name]

    def get_batch(self, batch: int) -> list[ClosureSkill]:
        return list(self._by_batch.get(batch, []))

    def all_skills(self) -> list[ClosureSkill]:
        return list(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)


_GLOBAL_CLOSURE_REGISTRY: Optional[ProductClosureRegistry] = None


def get_closure_registry() -> ProductClosureRegistry:
    global _GLOBAL_CLOSURE_REGISTRY
    if _GLOBAL_CLOSURE_REGISTRY is None:
        _GLOBAL_CLOSURE_REGISTRY = ProductClosureRegistry()
    return _GLOBAL_CLOSURE_REGISTRY

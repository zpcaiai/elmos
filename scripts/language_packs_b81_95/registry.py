#!/usr/bin/env python3
"""Skill Registry for Batch 81-95 Language Packs.

Loads and indexes all 180 skills from docs/language-packs-batch81-95/installed-manifest.json
and binds each skill to its deterministic archetype.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from scripts.language_packs_b81_95.archetypes import (
    BaseArchetype,
    get_archetype,
)
from scripts.language_packs_b81_95.canonical import digest
from scripts.language_packs_b81_95.errors import SkillNotFoundError

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "docs/language-packs-batch81-95/installed-manifest.json"


@dataclass(frozen=True)
class LanguageSkill:
    """Metadata and archetype binding for one Language Pack skill."""

    batch: int
    source_id: str
    source_key: str
    source_name: str
    installed_name: str
    installed_path: str
    installed_sha256: str
    archetype_name: str

    def get_archetype_instance(self) -> BaseArchetype:
        return get_archetype(self.archetype_name)


ARCHETYPE_ORDER = [
    "discovery-inventory",
    "parser-semantic-model",
    "schema-data-compiler",
    "batch-workflow-modeler",
    "transaction-modernizer",
    "data-storage-adapter",
    "business-rule-recovery",
    "api-event-extractor",
    "target-generator",
    "parallel-run-verifier",
    "security-operations-mapper",
    "cutover-decommission-planner",
]


def classify_archetype(name: str, index_in_batch: int) -> str:
    """Determine archetype from skill naming tokens or position."""
    n = name.lower()
    if any(k in n for k in ["discovery", "inventory"]):
        return "discovery-inventory"
    if any(k in n for k in ["parser", "semantic-model", "equation-graph", "ast"]):
        return "parser-semantic-model"
    if any(k in n for k in ["schema", "dictionary", "memory-map", "compiler"]):
        return "schema-data-compiler"
    if any(k in n for k in ["workflow", "jcl", "scan-cycle", "job", "pipeline", "orchestrator"]):
        return "batch-workflow-modeler"
    if any(k in n for k in ["transaction", "cics", "concurrency", "coroutine", "interlock", "lifetime"]):
        return "transaction-modernizer"
    if any(k in n for k in ["adapter", "data-mapper", "storage", "custom-table", "db2i", "firedac", "mnesia"]):
        return "data-storage-adapter"
    if any(k in n for k in ["rule", "clean-core", "injection-safety", "retain-refactor", "stateflow"]):
        return "business-rule-recovery"
    if any(k in n for k in ["api", "contract", "extractor", "bapi", "rfc", "plumber", "liveview", "event", "bridge", "interop"]):
        return "api-event-extractor"
    if any(k in n for k in ["generator", "migrator", "modernizer", "rap", "embedded-code", "shiny"]):
        return "target-generator"
    if any(k in n for k in ["verifier", "regression", "validation", "equivalence", "diff", "test-harness", "testthat", "test-fuzz"]):
        return "parallel-run-verifier"
    if any(k in n for k in ["security", "mapper", "sharing", "fsl", "sandbox", "sil", "dimension"]):
        return "security-operations-mapper"
    if any(k in n for k in ["cutover", "certifier", "planner", "decommission", "reproducibility", "release-upgrade", "compatibility-checker"]):
        return "cutover-decommission-planner"

    # Fallback to positional slot
    return ARCHETYPE_ORDER[index_in_batch % len(ARCHETYPE_ORDER)]


class LanguagePackRegistry:
    """Registry indexing all 180 skills across Batches 81-95."""

    def __init__(self, manifest_file: Path = MANIFEST_PATH) -> None:
        self.manifest_file = manifest_file
        self._by_id: dict[str, LanguageSkill] = {}
        self._by_name: dict[str, LanguageSkill] = {}
        self._by_batch: dict[int, list[LanguageSkill]] = {}
        self._load()

    def _load(self) -> None:
        raw = json.loads(self.manifest_file.read_text(encoding="utf-8"))
        self.package_name = raw.get("package", "elmos-language-packs-batch81-95-complete")
        self.batches = raw.get("batches", list(range(81, 96)))

        batch_counters: dict[int, int] = {}
        for entry in raw.get("skills", []):
            batch = entry["batch"]
            idx = batch_counters.get(batch, 0)
            batch_counters[batch] = idx + 1

            archetype = classify_archetype(entry["installed_name"], idx)
            skill = LanguageSkill(
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

    def get_by_id(self, source_id: str) -> LanguageSkill:
        if source_id not in self._by_id:
            raise SkillNotFoundError(f"Skill with source ID {source_id} not found")
        return self._by_id[source_id]

    def get_by_name(self, name: str) -> LanguageSkill:
        if name not in self._by_name:
            raise SkillNotFoundError(f"Skill with name {name} not found")
        return self._by_name[name]

    def get_batch(self, batch: int) -> list[LanguageSkill]:
        return list(self._by_batch.get(batch, []))

    def all_skills(self) -> list[LanguageSkill]:
        return list(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)


_GLOBAL_REGISTRY: Optional[LanguagePackRegistry] = None


def get_registry() -> LanguagePackRegistry:
    """Cached singleton registry."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = LanguagePackRegistry()
    return _GLOBAL_REGISTRY

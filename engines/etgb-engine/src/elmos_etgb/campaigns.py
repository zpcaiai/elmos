"""Deterministic assurance campaign helpers."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

from .canonical import canonical_json, digest_json


def derive_seed(*parts: Any, master_seed: int = 17) -> int:
    material = canonical_json({"master_seed": master_seed, "parts": list(parts)})
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def deterministic_seeds(case_id: str, seeds: Iterable[int] = (17, 43, 101)) -> list[int]:
    return [derive_seed(case_id, seed, master_seed=seed) % 2_147_483_647 for seed in seeds]


@dataclass(frozen=True)
class CampaignResult:
    campaign_id: str
    technique: str
    seed: int
    generated: int
    passed: int
    failures: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "technique": self.technique,
            "seed": self.seed,
            "generated": self.generated,
            "passed": self.passed,
            "failed": self.generated - self.passed,
            "failures": list(self.failures),
        }


def property_campaign(case_id: str, *, seed: int, generator: Callable[[random.Random], Any], predicate: Callable[[Any], bool], count: int = 32) -> CampaignResult:
    rng = random.Random(derive_seed(case_id, seed, master_seed=seed))
    failures: list[dict[str, Any]] = []
    passed = 0
    for index in range(count):
        value = generator(rng)
        try:
            ok = bool(predicate(value))
        except Exception as exc:  # campaign evidence must retain oracle errors
            ok = False
            failures.append({"index": index, "input": value, "error": type(exc).__name__ + ": " + str(exc)})
        if ok:
            passed += 1
        elif len(failures) < 20 and not any(item.get("index") == index for item in failures):
            failures.append({"index": index, "input": value, "reason": "predicate-failed"})
    return CampaignResult(digest_json({"case_id": case_id, "seed": seed, "technique": "property-based"}), "property-based", seed, count, passed, tuple(failures))


def shrink(value: Any, predicate: Callable[[Any], bool]) -> Any:
    """Small deterministic reducer for list/string/dict counterexamples."""

    current = value
    changed = True
    while changed:
        changed = False
        candidates: list[Any] = []
        if isinstance(current, list) and len(current) > 1:
            midpoint = len(current) // 2
            candidates.extend([current[:midpoint], current[midpoint:]])
        elif isinstance(current, str) and len(current) > 1:
            candidates.extend([current[: len(current) // 2], current[1:]])
        elif isinstance(current, dict) and len(current) > 1:
            for key in sorted(current):
                candidates.append({item: value for item, value in current.items() if item != key})
        for candidate in candidates:
            if not predicate(candidate):
                current = candidate
                changed = True
                break
    return current


def metamorphic_relation(name: str, left: Any, right: Any, *, relation: Callable[[Any, Any], bool], precondition: Callable[[Any, Any], bool] | None = None) -> dict[str, Any]:
    applicable = precondition(left, right) if precondition else True
    passed = bool(relation(left, right)) if applicable else True
    return {"type": "metamorphic", "relation": name, "applicable": applicable, "passed": passed, "input_sha256": digest_json(left), "transformed_sha256": digest_json(right)}


def mutation_summary(mutants: Sequence[dict[str, Any]], outcomes: Sequence[bool]) -> dict[str, Any]:
    if len(mutants) != len(outcomes):
        raise ValueError("mutants and outcomes must have equal length")
    killed = sum(1 for outcome in outcomes if outcome)
    return {"total": len(mutants), "killed": killed, "surviving": len(mutants) - killed, "kill_rate": killed / len(mutants) if mutants else None, "surviving_ids": [mutant.get("id") for mutant, outcome in zip(mutants, outcomes) if not outcome]}

"""Typed transformation recipes with parser-owned application boundaries."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Recipe:
    recipe_id: str
    source_profile: str
    target_profile: str
    rule_ids: tuple[str, ...]
    reversible: bool = True


@dataclass(frozen=True)
class TransformationPlan:
    recipe_id: str
    source_digest: str
    operations: tuple[str, ...]
    status: str


class RecipeRegistry:
    def __init__(self) -> None:
        self._recipes: dict[str, Recipe] = {}

    def register(self, recipe: Recipe) -> None:
        if recipe.recipe_id in self._recipes:
            raise ValueError("recipe id already registered")
        if not recipe.rule_ids:
            raise ValueError("recipe must contain rules")
        self._recipes[recipe.recipe_id] = recipe

    def plan(self, recipe_id: str, source: bytes) -> TransformationPlan:
        recipe = self._recipes[recipe_id]
        return TransformationPlan(recipe.recipe_id, "sha256:" + hashlib.sha256(source).hexdigest(), recipe.rule_ids, "PLANNED")

    def apply(self, plan: TransformationPlan, source: bytes, parser_rewriter: Callable[[bytes, tuple[str, ...]], bytes]) -> tuple[bytes, dict[str, object]]:
        if "sha256:" + hashlib.sha256(source).hexdigest() != plan.source_digest:
            raise ValueError("source changed after transformation plan")
        target = parser_rewriter(source, plan.operations)
        return target, {"recipe_id": plan.recipe_id, "source_digest": plan.source_digest, "target_digest": "sha256:" + hashlib.sha256(target).hexdigest(), "status": "APPLIED_BY_PARSER_ADAPTER"}

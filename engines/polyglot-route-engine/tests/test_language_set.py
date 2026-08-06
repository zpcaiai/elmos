"""The engine's language set and the route packs' must agree, or say why not.

`SUPPORTED_LANGUAGES` lists nine languages and `routes/` holds thirty directed
pairs over six. Nothing used to reconcile those numbers, so the platform's
declared breadth depended on which file you read: seventy-two pairs from the
engine, thirty from the evidence. Three languages sat in between with an
emitter, an analyser and a passing test suite, but no route pack, no behaviour
corpus and no certification artefact.

That gap is not closed here -- closing it means giving cpp, objc and swift the
same evidence the other six carry. What is closed is the silence: the split is
declared in `models.py` and checked here, so adding a language without adding
its evidence fails rather than quietly widening the claim.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from elmos_polyglot_route.models import (
    ANALYZABLE_LANGUAGES,
    ENGINE_ONLY_LANGUAGES,
    ROUTED_LANGUAGES,
    SUPPORTED_LANGUAGES,
)

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ENGINE_ROOT.parents[1]
ROUTES = REPOSITORY_ROOT / "routes"


def test_the_split_is_a_partition_of_the_supported_set() -> None:
    assert set(ROUTED_LANGUAGES) | set(ENGINE_ONLY_LANGUAGES) == set(SUPPORTED_LANGUAGES)
    assert not set(ROUTED_LANGUAGES) & set(ENGINE_ONLY_LANGUAGES)
    # A language the engine cannot analyse could not be a route source.
    assert set(ROUTED_LANGUAGES) <= set(ANALYZABLE_LANGUAGES)


def test_the_routed_set_is_not_empty_and_engine_only_is_not_everything() -> None:
    # Guards against a future edit that "fixes" this file by declaring every
    # language engine-only, which would make every check below vacuous.
    assert len(ROUTED_LANGUAGES) >= 6
    assert len(ENGINE_ONLY_LANGUAGES) < len(SUPPORTED_LANGUAGES)


@pytest.mark.skipif(not ROUTES.is_dir(), reason="routes/ is not present in this checkout")
def test_every_routed_pair_has_a_pack_and_nothing_else_does() -> None:
    present = {path.name for path in ROUTES.iterdir() if path.is_dir()}
    expected = {
        f"{source}-to-{target}"
        for source in ROUTED_LANGUAGES
        for target in ROUTED_LANGUAGES
        if source != target
    }
    assert len(expected) == 30
    missing = sorted(expected - present)
    assert not missing, f"routed pairs with no pack: {missing}"
    unexpected = sorted(present - expected)
    assert not unexpected, f"packs for pairs the engine does not declare as routed: {unexpected}"


@pytest.mark.skipif(not ROUTES.is_dir(), reason="routes/ is not present in this checkout")
def test_no_engine_only_language_claims_route_evidence() -> None:
    names = {path.name for path in ROUTES.iterdir() if path.is_dir()}
    for language in ENGINE_ONLY_LANGUAGES:
        claimed = sorted(name for name in names if language in name.split("-to-"))
        assert not claimed, (
            f"{language} is declared engine-only but has route packs: {claimed}. "
            "Either move it to ROUTED_LANGUAGES with its evidence, or remove the packs."
        )


@pytest.mark.skipif(
    not (ROUTES / "inventory.json").is_file(), reason="routes/inventory.json is not present"
)
def test_the_inventory_declares_exactly_the_routed_languages() -> None:
    inventory = json.loads((ROUTES / "inventory.json").read_text(encoding="utf-8"))
    assert set(inventory["languages"]) == set(ROUTED_LANGUAGES)
    assert inventory["route_count"] == 30
    assert len(inventory["routes"]) == 30

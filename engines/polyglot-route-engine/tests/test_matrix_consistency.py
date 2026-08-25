"""Guard the seams *between* the matrix authorities, not any one of them.

The route matrix is declared twice on purpose:

* ``elmos_polyglot_route.models`` is the engine's authority.  It speaks in
  ordered language pairs and is what the runtime enforces.
* ``scripts/batch29/route_sets.py`` is the campaign authority.  It speaks in
  ``"<source>-to-<target>"`` route keys and is what the runners, gates and the
  generated ``routes/inventory.json`` are built from.

``tests/test_language_set.py`` already audits the engine authority thoroughly,
and deliberately derives its expectations by hand so that it is an independent
second opinion rather than an echo of ``route_sets``.  That independence leaves
three seams unguarded, and this module exists only for those:

1. **The two authorities are never compared to each other.**  They can drift --
   a language added to one and not the other, or a route key spelled
   differently -- and the whole suite stays green.
2. **``route_sets`` is never imported by the suite at all.**  Its import-time
   partition guards (``ROUTE_PROVENANCE_PARTITIONS_OVERLAP``,
   ``..._INCOMPLETE``, ``DEPRECATED_ROUTE_KEYS_UNOWNED``) therefore never run
   under pytest; a broken partition only surfaces when someone runs a script.
   Merely importing the module here re-arms those guards.
3. **``routes/inventory.json``'s provenance summary is never tied back to the
   partition it claims to summarise.**  ``test_language_set.py`` checks
   ``route_sets`` (the ten convenience unions); the six-way *owner* partition
   and the route-tier arithmetic are separate fields and go unchecked.

Nothing here re-asserts what ``test_language_set.py`` already asserts.  If a
check belongs to a single authority, it belongs in that file, not this one.

The provenance partition matters more than its size suggests: each partition
name is the *address* of filed evidence.  Several of its members are derived
expressions (``V3_EXACT_ROUTE_KEYS`` is active-minus-eleven,
``PHP_EXACT_ROUTE_KEYS`` is a difference against a named complete set), and a
derived expression repointed at the wrong base silently relabels evidence that
was filed under another name.  The shape assertions below are aimed at exactly
that failure mode.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route import toolchains
from elmos_polyglot_route.models import (
    DEPRECATED_DIRECTED_PAIRS,
    DEPRECATED_LANGUAGES,
    REPOSITORY_SURFACE_LANGUAGES,
    ROUTED_PAIRS,
    SUPPORTED_LANGUAGES,
)

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ENGINE_ROOT.parents[1]
ROUTE_SETS_PATH = REPOSITORY_ROOT / "scripts" / "batch29" / "route_sets.py"
INVENTORY_PATH = REPOSITORY_ROOT / "routes" / "inventory.json"

V3_LANGUAGES = frozenset({"kotlin", "react", "flutter"})

requires_route_sets = pytest.mark.skipif(
    not ROUTE_SETS_PATH.is_file(),
    reason="scripts/batch29/route_sets.py is not present in this checkout",
)
requires_inventory = pytest.mark.skipif(
    not INVENTORY_PATH.is_file(),
    reason="routes/inventory.json is not present in this checkout",
)


def _load_route_sets() -> Any:
    """Import the campaign authority by path.

    ``scripts/`` is not an installed package, so this mirrors how
    ``test_language_set.py`` loads ``tools/runtime_toolchain_receipt.py``.
    Executing the module is the point, not a side effect: ``route_sets`` raises
    at import time when its provenance partition overlaps, fails to cover every
    declared direction, or leaves a deprecated key unowned.
    """

    spec = importlib.util.spec_from_file_location(
        "elmos_batch29_route_sets_contract",
        ROUTE_SETS_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _route_key(pair: tuple[str, str]) -> str:
    source, target = pair
    return f"{source}-to-{target}"


def _ends(route_key: str) -> set[str]:
    return set(route_key.split("-to-"))


@requires_route_sets
def test_engine_and_campaign_authorities_declare_the_same_matrix() -> None:
    """models and route_sets must agree, in both languages and route keys."""

    route_sets = _load_route_sets()

    assert set(route_sets.SUPPORTED_ROUTE_LANGUAGES) == set(SUPPORTED_LANGUAGES)
    assert set(route_sets.DEPRECATED_ROUTE_LANGUAGES) == set(DEPRECATED_LANGUAGES)

    active_keys = {_route_key(pair) for pair in ROUTED_PAIRS}
    deprecated_keys = {_route_key(pair) for pair in DEPRECATED_DIRECTED_PAIRS}

    assert active_keys == set(route_sets.COMPLETE_ROUTE_KEYS)
    assert deprecated_keys == set(route_sets.DEPRECATED_ROUTE_KEYS)
    assert not active_keys & deprecated_keys
    assert set(route_sets.ALL_DECLARED_ROUTE_KEYS) == active_keys | deprecated_keys

    # Route keys are also filesystem names under routes/.  A pair the engine
    # can route but whose key the campaign spells differently would silently
    # look like a missing pack rather than a disagreement.
    assert len(route_sets.ALL_DECLARED_ROUTE_KEYS) == len(
        set(route_sets.ALL_DECLARED_ROUTE_KEYS)
    )


@requires_route_sets
def test_provenance_partition_is_a_partition_and_keeps_its_recorded_sizes() -> None:
    route_sets = _load_route_sets()
    partitions = route_sets.ROUTE_PROVENANCE_PARTITIONS

    members = [key for keys in partitions.values() for key in keys]
    assert len(members) == len(set(members)), "provenance partitions overlap"
    assert set(members) == set(route_sets.ALL_DECLARED_ROUTE_KEYS)

    # Every partition name ends in the number of directions it owns.  The name
    # is the address of filed evidence, so a size drift means either the
    # evidence moved or the name now lies about what it addresses.
    for name, keys in partitions.items():
        recorded = int(name.rsplit("-", 1)[-1])
        assert len(set(keys)) == recorded, f"{name} owns {len(set(keys))} directions"

    # Guards against a future edit that empties the table and makes the loop
    # above vacuously true.
    assert len(partitions) == 6
    assert sum(len(set(keys)) for keys in partitions.values()) == 176


@requires_route_sets
def test_derived_partitions_still_point_at_the_base_they_were_written_against() -> None:
    """The derived-expression trap, asserted as membership rather than size.

    ``PHP_EXACT_ROUTE_KEYS`` is a difference against the *eleven* language
    complete set.  Repointing it at the thirteen-language set would grow it
    from 20 to 86 and pull kotlin/react/flutter directions into a partition
    named for PHP evidence.  ``V3_EXACT_ROUTE_KEYS`` has the mirror failure.
    Sizes alone would not catch a rename that preserved the count.
    """

    route_sets = _load_route_sets()

    assert not any(V3_LANGUAGES & _ends(key) for key in route_sets.PHP_EXACT_ROUTE_KEYS)
    assert all("php" in _ends(key) for key in route_sets.PHP_EXACT_ROUTE_KEYS)

    assert all(V3_LANGUAGES & _ends(key) for key in route_sets.V3_EXACT_ROUTE_KEYS)

    assert all(
        "javascript" in _ends(key) for key in route_sets.NODEJS_EXACT_ROUTE_KEYS
    )
    # Every deprecated direction is owned, and only by the two partitions that
    # can own one: the javascript partition, plus the php partition for the two
    # php-to-javascript directions filed during the PHP campaign.
    assert set(route_sets.DEPRECATED_ROUTE_KEYS) <= (
        set(route_sets.NODEJS_EXACT_ROUTE_KEYS) | set(route_sets.PHP_EXACT_ROUTE_KEYS)
    )


@requires_route_sets
@requires_inventory
def test_inventory_provenance_summary_matches_the_partition_it_summarises() -> None:
    route_sets = _load_route_sets()
    partitions = route_sets.ROUTE_PROVENANCE_PARTITIONS
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))

    summary = inventory["route_provenance_partition"]
    assert set(summary["sets"]) == set(partitions)
    for name, keys in partitions.items():
        assert set(summary["sets"][name]) == set(keys), f"{name} drifted in inventory"

    assert summary["active_route_count"] == 156
    assert summary["deprecated_route_count"] == 20
    assert summary["route_count"] == 176

    # Each partition is also an execution authority; the two tables are written
    # separately and nothing else compares them.
    assert set(inventory["route_execution_authorities"]) == set(partitions)


@requires_inventory
def test_inventory_route_tiers_account_for_every_active_route() -> None:
    """Tier counts must sum to the route count, not merely look plausible.

    A route that falls out of every tier disappears from the strength story
    while still being listed, which reads as stronger evidence than exists.
    """

    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    tiers = (
        "certified_route_count",
        "limited_route_count",
        "experimental_route_count",
        "research_route_count",
        "blocked_route_count",
    )
    assert sum(inventory[tier] for tier in tiers) == inventory["route_count"]
    # The 66 kotlin/react/flutter directions are research, not limited.  If
    # this ever reads 0 the newest campaign was silently promoted.
    assert inventory["research_route_count"] == 66
    assert inventory["certified_route_count"] == 0


def test_every_repository_surface_language_has_a_registered_toolchain() -> None:
    """Registration, not availability.

    ``exact_toolchain`` raises ``EXACT_TOOLCHAIN_UNREGISTERED`` for a language
    with no selector at all, which is a matrix bug, and other RouteErrors for a
    machine that simply lacks the pinned install, which is not.  Reading the
    selector table rather than calling it keeps this check honest on any
    machine and free of toolchain work.
    """

    source = inspect.getsource(toolchains.exact_toolchain)
    registered = set(re.findall(r'"([a-z]+)"\s*:\s*_[a-z_]+\s*,', source))

    # Guards against a regex that silently stops matching and turns the
    # superset check below into a comparison against the empty set.
    assert len(registered) >= 10, f"selector table did not parse: {sorted(registered)}"
    missing = set(REPOSITORY_SURFACE_LANGUAGES) - registered
    assert not missing, f"languages with no exact toolchain selector: {sorted(missing)}"

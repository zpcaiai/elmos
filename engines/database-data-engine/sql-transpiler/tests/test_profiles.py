from __future__ import annotations

import pytest

from elmos_sql_transpiler.profiles import (
    capabilities,
    directed_route,
    exact_profiles,
    profile_by_id,
    route_matrix,
)


def test_seven_exact_profiles_produce_forty_two_directional_routes() -> None:
    profiles = exact_profiles()
    routes = route_matrix()

    assert len(profiles) == 7
    assert len(routes) == 42
    assert len({route.id for route in routes}) == 42
    assert all(route.source_profile != route.target_profile for route in routes)
    assert all(route.certification == "NOT_CERTIFIED" for route in routes)
    assert all(route.source_execution == "NOT_RUN" for route in routes)
    assert all(route.target_execution == "NOT_RUN" for route in routes)


def test_profiles_are_exact_and_capabilities_disclose_boundaries() -> None:
    forbidden = ("latest", "*", ".x", "current", "unspecified")
    for profile in exact_profiles():
        material = f"{profile.id} {profile.engine_version} {profile.driver}".lower()
        assert not any(token in material for token in forbidden)

    value = capabilities()
    assert value["directedRouteCount"] == 42
    assert value["syntaxSuccessGoal"] == 0.995
    assert value["p0CorrectnessRequired"] == 1.0
    assert value["silentDropTolerance"] == 0
    assert value["resultEquivalence"] == "NOT_RUN"
    assert value["certification"] == "NOT_CERTIFIED"
    capability_states = {item["id"]: item["state"] for item in value["capabilities"]}
    assert capability_states["stored-procedure-and-trigger"] == "CONDITIONAL"
    assert capability_states["optimizer-hints-and-plan-shape"] == "CONDITIONAL"
    assert capability_states["runtime-result-equivalence"] == "NOT_RUN"
    assert len(value["knownConditionalPairs"]) == 2
    # The two formerly-blocked pairs are typed rewrites now; the catalog must
    # not regress them back to BLOCKED nor launder them into silent aliases.
    pairs = {item["feature"]: item["state"] for item in value["knownConditionalPairs"]}
    assert pairs["GROUP_CONCAT_ORDER_BY"] == "TYPED_REWRITE"
    assert pairs["ORACLE_TRUNC_DATETIME_FORMAT"] == "TYPED_REWRITE_ALLOW_LIST"


def test_unknown_and_same_profile_routes_fail_closed() -> None:
    with pytest.raises(ValueError, match="unknown exact SQL profile"):
        profile_by_id("postgresql-latest")
    with pytest.raises(ValueError, match="must differ"):
        directed_route("postgresql-18.4", "postgresql-18.4")

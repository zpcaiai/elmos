from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, cast

from .adapters import target_adapter_capabilities
from .models import DialectProfile, DirectedRoute

_FORBIDDEN_VERSION_TOKENS = ("latest", "*", ".x", "current", "unspecified")


def _catalog() -> dict[str, Any]:
    path = files("elmos_sql_transpiler").joinpath("data/profiles-v1.json")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RuntimeError("SQL profile catalog must be an object")
    return loaded


def _profile(raw: dict[str, Any]) -> DialectProfile:
    profile = DialectProfile(
        id=str(raw["id"]),
        label=str(raw["label"]),
        engine=str(raw["engine"]),
        engine_version=str(raw["engineVersion"]),
        edition=str(raw["edition"]),
        dialect=str(raw["dialect"]),
        driver=str(raw["driver"]),
        charset=str(raw["charset"]),
        collation=str(raw["collation"]),
        timezone=str(raw["timezone"]),
        compatibility_mode=str(raw["compatibilityMode"]),
        support_state=str(raw["supportState"]),
        runtime_evidence=str(raw["runtimeEvidence"]),
    )
    exact_material = " ".join(
        (profile.id, profile.engine_version, profile.edition, profile.driver)
    ).lower()
    if any(token in exact_material for token in _FORBIDDEN_VERSION_TOKENS):
        raise RuntimeError(f"floating SQL profile is prohibited: {profile.id}")
    if profile.runtime_evidence != "NOT_RUN":
        raise RuntimeError("checked-in profile catalog cannot manufacture runtime evidence")
    return profile


def parser_pin() -> dict[str, Any]:
    """The exact parser build the checked-in profile catalog was verified
    against."""
    parser = _catalog()["parser"]
    if not isinstance(parser, dict) or "version" not in parser:
        raise RuntimeError("SQL profile catalog must pin an exact parser version")
    return parser


def exact_profiles() -> tuple[DialectProfile, ...]:
    profiles = tuple(_profile(raw) for raw in _catalog()["profiles"])
    ids = {profile.id for profile in profiles}
    if len(ids) != len(profiles):
        raise RuntimeError("duplicate SQL profile id")
    return profiles


def extension_by_id(profile_id: str) -> dict[str, Any] | None:
    for ext in _catalog().get("extensions", []):
        if isinstance(ext, dict) and ext.get("id") == profile_id:
            return cast(dict[str, Any], ext)
    return None


def profile_by_id(profile_id: str) -> DialectProfile:
    matches = [profile for profile in exact_profiles() if profile.id == profile_id]
    if len(matches) == 1:
        return matches[0]
    ext = extension_by_id(profile_id)
    if ext is not None:
        raise ValueError(
            f"SQL profile '{profile_id}' is an extension ({ext.get('state')}): "
            f"{ext.get('reason')}. "
            "Disguised alias transpilation is strictly prohibited by docs/batch31/QUALITY_GATES.md."
        )
    raise ValueError(f"unknown exact SQL profile: {profile_id}")


def directed_route(source_profile: str, target_profile: str) -> DirectedRoute:
    source = profile_by_id(source_profile)
    target = profile_by_id(target_profile)
    if source.id == target.id:
        raise ValueError("source and target SQL profiles must differ")
    state = (
        "LICENSED_RUNTIME_REQUIRED"
        if "LICENSED_RUNTIME_REQUIRED" in (source.support_state, target.support_state)
        else "SYNTAX_TRANSPILATION_EXPERIMENTAL"
    )
    return DirectedRoute(
        id=f"{source.id}--to--{target.id}",
        source_profile=source.id,
        target_profile=target.id,
        state=state,
    )


def route_matrix() -> tuple[DirectedRoute, ...]:
    profiles = exact_profiles()
    return tuple(
        directed_route(source.id, target.id)
        for source in profiles
        for target in profiles
        if source.id != target.id
    )


def capabilities() -> dict[str, Any]:
    from .commercial import commercial_summary

    catalog = _catalog()
    profiles = exact_profiles()
    routes = route_matrix()
    return {
        "schemaVersion": "1.0",
        "parser": catalog["parser"],
        "exactProfiles": [profile.to_dict() for profile in profiles],
        "directedRoutes": [route.to_dict() for route in routes],
        "directedRouteCount": len(routes),
        "capabilities": catalog["capabilities"],
        "knownConditionalPairs": catalog["knownConditionalPairs"],
        "extensions": catalog["extensions"],
        "targetAdapterProtocolVersion": "1.0",
        "targetAdapters": list(target_adapter_capabilities()),
        "commercialExtension": commercial_summary(),
        "syntaxSuccessGoal": 0.995,
        "p0CorrectnessRequired": 1.0,
        "silentDropTolerance": 0,
        "sourceExecution": "NOT_RUN",
        "targetExecution": "NOT_RUN",
        "resultEquivalence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }

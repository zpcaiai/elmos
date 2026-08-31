#!/usr/bin/env python3
"""Validate the exact 9-profile/72-route/12-block frontend v2 campaign.

The v2 contract deliberately keeps model/formal, browser, native-channel and
independent evidence separate.  A structurally valid bounded model proof can
therefore be useful while every runtime and certification readiness field
remains false.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import validate_frontend_formal_route_campaign as v1

try:
    import jsonschema
except ImportError:  # pragma: no cover - replay has a deterministic fallback
    jsonschema = None


BLOCK_IDS = (
    "route-navigation-deeplink-404",
    "component-template-view",
    "state-management",
    "action-event",
    "effect-lifecycle",
    "form-binding-validation",
    "api-network",
    "identity-permission",
    "rendering-hydration",
    "accessibility-focus",
    "i18n-theme-responsive",
    "native-platform",
)
BLOCK_SYMBOL_MAP = {
    "route-navigation-deeplink-404": "navigation",
    "component-template-view": "component_template",
    "state-management": "state_management",
    "action-event": "action_event",
    "effect-lifecycle": "effect_lifecycle",
    "form-binding-validation": "form_binding_validation",
    "api-network": "api_network",
    "identity-permission": "identity_permission",
    "rendering-hydration": "rendering_hydration",
    "accessibility-focus": "accessibility_focus",
    "i18n-theme-responsive": "i18n_theme_responsive",
    "native-platform": "native_platform",
}
BLOCK_ROOT_POINTERS = {
    "route-navigation-deeplink-404": "/navigation",
    "component-template-view": "/componentTemplate",
    "state-management": "/stateManagement",
    "action-event": "/actionEvent",
    "effect-lifecycle": "/effectLifecycle",
    "form-binding-validation": "/formBindingValidation",
    "api-network": "/apiNetwork",
    "identity-permission": "/identityPermission",
    "rendering-hydration": "/renderingHydration",
    "accessibility-focus": "/accessibilityFocus",
    "i18n-theme-responsive": "/i18nThemeResponsive",
    "native-platform": "/nativePlatform",
}
PROFILE_IDS = v1.PROFILE_IDS
RUNTIME_CHANNELS = ("browser", "android", "ios", "harmonyos")
REQUIRED_RUNTIME_CHANNELS = {
    "angular": ("browser",),
    "flutter": ("browser", "android", "ios"),
    "harmony-arkui": ("harmonyos",),
    "jquery": ("browser",),
    "react": ("browser",),
    "react-native": ("browser", "android", "ios"),
    "svelte": ("browser",),
    "vue2": ("browser",),
    "vue3": ("browser",),
}
EVIDENCE_STATES = {"PASSED", "FAILED", "NOT_RUN", "NOT_APPLICABLE"}
SELF_CONTAINED_REPLAY_TIMEOUT_SECONDS = 300
RUNTIME_ACTUAL_KEYS = {
    "route-navigation-deeplink-404": {
        "requestedPath", "selectedRouteId", "selectedPath", "resolution", "deepLink", "requiresAuth"
    },
    "component-template-view": {"componentId", "key", "title", "text", "visible"},
    "state-management": {"stateId", "before", "after", "saturated"},
    "action-event": {"event", "keyboardKey", "handled", "action"},
    "effect-lifecycle": {"lifecycle", "effect", "executions", "cleanup", "staleResponseIgnored"},
    "form-binding-validation": {"formId", "fieldId", "value", "submitted", "valid", "errorCode"},
    "api-network": {"operationId", "called", "method", "path", "outcome", "canceled", "staleIgnored", "cacheKey"},
    "identity-permission": {"role", "permission", "permissionGranted", "tenantMatch", "authorized", "serverAuthorityRequired"},
    "rendering-hydration": {"mode", "requested", "status", "duplicateEffects", "mismatchVisible"},
    "accessibility-focus": {"mainRole", "headingLevel", "formLabel", "errorRole", "liveRegion", "keyboardSubmit", "focusTarget"},
    "i18n-theme-responsive": {"requestedLocale", "locale", "requestedTheme", "theme", "viewportWidth", "columns"},
    "native-platform": {"boundary", "lifecycle", "attempted", "permission", "available", "outcome", "recovery"},
}
RUNTIME_ACTUAL_BOOL_FIELDS = {
    "deepLink", "requiresAuth", "visible", "saturated", "handled", "cleanup",
    "staleResponseIgnored", "submitted", "valid", "called", "canceled",
    "staleIgnored", "permissionGranted", "tenantMatch", "authorized",
    "serverAuthorityRequired", "duplicateEffects", "mismatchVisible",
    "keyboardSubmit", "attempted", "available",
}
RUNTIME_ACTUAL_INT_FIELDS = {
    "before", "after", "executions", "headingLevel", "viewportWidth", "columns"
}
RUNTIME_ACTUAL_NULLABLE_STRING_FIELDS = {
    "keyboardKey",
    "errorCode",
    "errorRole",
    "focusTarget",
}
RUNTIME_ACTUAL_EMPTY_STRING_FIELDS_BY_BLOCK = {
    "form-binding-validation": {"value"},
}
RUNTIME_ACTUAL_ENUMS_BY_BLOCK = {
    "route-navigation-deeplink-404": {
        "resolution": {
            "DECLARED",
            "FIRST_DECLARED_FALLBACK",
            "AUTH_DENIED_FALLBACK",
        },
    },
    "action-event": {
        "event": {
            "BOOT",
            "NAVIGATE",
            "AUTHENTICATE",
            "SUBMIT",
            "CANCEL",
            "HYDRATE",
            "DISPLAY_CHANGE",
            "NATIVE_DEEPLINK",
        },
        "action": {
            "BOOT",
            "NAVIGATE",
            "AUTHENTICATE",
            "SUBMIT_ACCEPTED",
            "BLOCK",
            "CANCEL",
            "HYDRATE",
            "DISPLAY_CHANGE",
            "NATIVE_DEEPLINK",
        },
    },
    "effect-lifecycle": {
        "lifecycle": {"MOUNT", "ACTIVE", "UNMOUNT"},
        "effect": {"LOAD_ON_MOUNT", "CANCEL_ON_UNMOUNT", "NONE"},
    },
    "api-network": {
        "method": {"POST"},
        "outcome": {"NOT_CALLED", "CANCELED", "SUCCESS", "ERROR", "PENDING"},
    },
    "identity-permission": {
        "role": {"ANONYMOUS", "MEMBER"},
    },
    "rendering-hydration": {
        "mode": {"HYDRATABLE_CSR"},
        "requested": {"MATCH", "MISMATCH", "NONE"},
        "status": {"MATCHED", "RENDER_ERROR", "NOT_ATTEMPTED"},
    },
    "native-platform": {
        "boundary": {"ADAPTER"},
        "lifecycle": {"FOREGROUND", "BACKGROUND"},
        "permission": {"GRANTED", "DENIED", "NOT_REQUESTED"},
        "outcome": {"NOT_ATTEMPTED", "OPENED", "NO_OP_REPORTED"},
        "recovery": {"NOT_REQUIRED", "FOREGROUND_RETRY"},
    },
}


def external_actual_value_valid_v2(block_id: str, actual: object) -> bool:
    if not isinstance(actual, dict):
        return False
    block_enums = RUNTIME_ACTUAL_ENUMS_BY_BLOCK.get(block_id, {})
    empty_string_fields = RUNTIME_ACTUAL_EMPTY_STRING_FIELDS_BY_BLOCK.get(
        block_id, set()
    )
    for field, value in actual.items():
        if field in block_enums:
            if value not in block_enums[field]:
                return False
        elif field in RUNTIME_ACTUAL_BOOL_FIELDS:
            if type(value) is not bool:
                return False
        elif field in RUNTIME_ACTUAL_INT_FIELDS:
            if type(value) is not int or value < 0:
                return False
        elif field in RUNTIME_ACTUAL_NULLABLE_STRING_FIELDS:
            if value is not None and (not isinstance(value, str) or not value):
                return False
        elif field in empty_string_fields:
            if not isinstance(value, str):
                return False
        elif not isinstance(value, str) or not value:
            return False
    return True


def external_authorization_time_valid_v2(
    *,
    trust_issued_at: datetime | None,
    trust_expires_at: datetime | None,
    issued_at: datetime | None,
    expires_at: datetime | None,
    now: datetime | None,
) -> bool:
    return (
        trust_issued_at is not None
        and trust_expires_at is not None
        and issued_at is not None
        and expires_at is not None
        and now is not None
        and trust_issued_at <= issued_at <= now < expires_at <= trust_expires_at
    )
BLOCK_OBSERVER_CONTRACT = "block-specific-runtime-observation-v1"
BLOCK_OBSERVER_SPECS = {
    block_id: {
        "observer_kind": observer_kind,
        "measurement_surface": measurement_surface,
        "trace_role": trace_role,
        "measurement_keys": measurement_keys,
        "supporting_trace_roles": supporting_trace_roles,
    }
    for block_id, (
        observer_kind,
        measurement_surface,
        trace_role,
        measurement_keys,
        supporting_trace_roles,
    ) in {
        "route-navigation-deeplink-404": ("ROUTER_DOM_URL_OBSERVER", "page.url+[data-elmos-active-route] attrs", "browser-route-dom-url-observer-trace", ("page_url", "active_route_attributes", "declared_routes"), ("browser-dom-snapshot", "browser-framework-event-trace")),
        "component-template-view": ("RENDERED_COMPONENT_DOM_OBSERVER", "active route heading/text/visibility attrs", "browser-rendered-component-observer-trace", ("heading", "text", "visibility", "attributes"), ("browser-dom-snapshot",)),
        "state-management": ("FRAMEWORK_STATE_TRANSITION_OBSERVER", "[data-elmos-state-measurement] before/after/saturated", "browser-framework-state-transition-observer-trace", ("state_measurement",), ("browser-framework-event-trace", "browser-dom-snapshot")),
        "action-event": ("NATIVE_EVENT_OUTCOME_OBSERVER", "captured click/keydown/submit + [data-elmos-action-outcome]", "browser-native-event-outcome-observer-trace", ("captured_events", "outcome_attributes"), ("browser-framework-event-trace",)),
        "effect-lifecycle": ("FRAMEWORK_LIFECYCLE_TRACE_OBSERVER", "ordered [data-elmos-lifecycle-event]", "browser-framework-lifecycle-observer-trace", ("ordered_events",), ("browser-framework-event-trace",)),
        "form-binding-validation": ("FORM_CONTROL_VALIDITY_OBSERVER", "control value+ValidityState+error DOM+focus", "browser-form-validity-observer-trace", ("control", "validity_state", "error_dom", "active_element"), ("browser-dom-snapshot", "browser-framework-event-trace", "browser-accessibility-axe-trace")),
        "api-network": ("BROWSER_NETWORK_OBSERVER", "Playwright request/response/requestfailed + app abort/stale marker", "browser-network-observer-trace", ("network_events", "application_markers"), ("browser-network-trace", "browser-framework-event-trace")),
        "identity-permission": ("AUTHORITY_ADAPTER_OBSERVER", "[data-elmos-auth-decision] only if real adapter trace", "browser-authority-adapter-observer-trace", ("adapter_events", "decision_attributes"), ("browser-framework-event-trace",)),
        "rendering-hydration": ("SSR_HYDRATION_OBSERVER", "server markup digest+hydration warnings/mutations/effect count", "browser-ssr-hydration-observer-trace", ("server_markup_digest", "hydration_warnings", "mutations", "effect_count", "hydration_state"), ("browser-dom-snapshot", "browser-framework-event-trace")),
        "accessibility-focus": ("ACCESSIBILITY_TREE_FOCUS_OBSERVER", "aria snapshot+axe+active element+keyboard", "browser-accessibility-tree-focus-observer-trace", ("aria_snapshot", "axe_results", "active_element", "keyboard_events", "accessibility_state"), ("browser-accessibility-axe-trace", "browser-framework-event-trace")),
        "i18n-theme-responsive": ("COMPUTED_LAYOUT_I18N_THEME_OBSERVER", "html lang+rendered translated text+computed theme tokens+measured layout", "browser-computed-layout-i18n-theme-observer-trace", ("html_lang", "translated_text", "computed_theme_tokens", "layout_measurement"), ("browser-dom-snapshot",)),
        "native-platform": ("NATIVE_ADAPTER_DEVICE_OBSERVER", "native semantics+lifecycle+permission+adapter trace", "native-adapter-device-observer-trace", ("semantics", "lifecycle", "permission", "adapter_events", "device_identity"), ()),
    }.items()
}
RUNTIME_DRIVER_CONTRACT_KEYS = {
    "schema_version", "kind", "framework_binding", "runtime_evidence_eligibility",
    "runtime_status", "independent_runtime_oracle", "customer_runtime_evidence",
    "certification", "required_runtime_channels", "observer_protocol", "actual_source",
    "self_reported_reducer_json_allowed", "legacy_runtime_observed_allowed",
    "declaration_payload_allowed_keys", "block_observer_contracts",
    "browser_required_not_run_blocks", "native_required_not_run_blocks",
    "native_route_without_real_device_channel_status", "root_selector", "ready_selector",
    "scenario_row_selector_template", "scenario_action_selector_template",
    "runtime_source_attribute", "runtime_source_value", "completion_attribute",
    "completion_value", "sequence_attribute", "query_selector",
    "block_selector_template", "network_intercept_path", "channel_projection_contract",
    "channel_projection_contract_digest", "native_adapter_evidence",
    "browser_or_device_evidence",
}
_RUNTIME_OBSERVER_HELPER: Any = None


def runtime_actual_from_block_measurement(
    *,
    block_id: str,
    value: object,
    label: str,
    scenario_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    global _RUNTIME_OBSERVER_HELPER
    if _RUNTIME_OBSERVER_HELPER is None:
        helper_path = (
            Path(__file__).resolve().parents[2]
            / "tooling/generate_frontend_formal_verification_pack.py"
        )
        namespace = runpy.run_path(
            str(helper_path), run_name="elmos_frontend_v2_runtime_observer_helper"
        )
        _RUNTIME_OBSERVER_HELPER = namespace.get(
            "runtime_actual_from_block_measurement_v2"
        )
    if not callable(_RUNTIME_OBSERVER_HELPER):
        raise ValueError("captured block observer derivation helper is unavailable")
    return _RUNTIME_OBSERVER_HELPER(
        block_id=block_id,
        value=value,
        label=label,
        scenario_input=scenario_input,
    )


def scenario_inputs_from_payload(
    payload: object, scenario_ids: list[str], errors: list[str]
) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        errors.append("scenario manifest payload is not an object")
        return {}
    rows = payload.get("scenarios")
    if (
        not isinstance(rows, list)
        or [
            row.get("scenarioId") if isinstance(row, dict) else None
            for row in rows
        ]
        != scenario_ids
    ):
        errors.append("scenario manifest input closure/order drift")
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"scenarioId", "input"}
            or not isinstance(row.get("input"), dict)
        ):
            errors.append("scenario manifest input row drift")
            return {}
        result[str(row["scenarioId"])] = dict(row["input"])
    return result


def validate_content_addressed_runtime_json(
    *,
    reference: dict[str, Any],
    path: Path,
    payload: dict[str, Any],
    label: str,
    errors: list[str],
) -> None:
    relative = PurePosixPath(str(reference.get("path")))
    try:
        content = path.read_bytes()
    except OSError as exc:
        errors.append(f"{label} content-addressed bytes unavailable: {exc}")
        return
    expected = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if (
        len(relative.parts) < 2
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or "\\" in str(reference.get("path"))
        or relative.as_posix() != str(reference.get("path"))
        or relative.suffix != ".json"
        or relative.stem
        != str(reference.get("sha256", "")).removeprefix("sha256:")
        or content != expected
    ):
        errors.append(f"{label} content-address/path/encoding drift")


def browser_block_status_contract(
    *, profile_id: str, driver: object, errors: list[str]
) -> dict[str, dict[str, Any]]:
    label = f"profile {profile_id} block observer contract"
    if not isinstance(driver, dict):
        errors.append(f"{label} is missing")
        return {}
    contracts = driver.get("block_observer_contracts")
    if not isinstance(contracts, dict) or set(contracts) != set(BLOCK_IDS):
        errors.append(f"{label} closure drift")
        return {}
    result: dict[str, dict[str, Any]] = {}
    not_run: list[str] = []
    for block_id in BLOCK_IDS:
        row = contracts.get(block_id)
        spec = BLOCK_OBSERVER_SPECS[block_id]
        if (
            not isinstance(row, dict)
            or set(row)
            != {
                "observer_kind",
                "measurement_surface",
                "browser_status",
                "browser_reason",
                "native_status",
                "native_reason",
            }
            or row.get("observer_kind") != spec["observer_kind"]
            or row.get("measurement_surface") != spec["measurement_surface"]
            or row.get("browser_status") not in {"PASSED", "NOT_RUN"}
            or not isinstance(row.get("browser_reason"), str)
            or not row["browser_reason"]
            or row.get("native_status") not in {"PASSED", "NOT_RUN"}
            or not isinstance(row.get("native_reason"), str)
            or not row["native_reason"]
        ):
            errors.append(f"{label} {block_id} drift")
            continue
        if row["browser_status"] == "NOT_RUN":
            not_run.append(block_id)
        result[block_id] = {
            "status": row["browser_status"],
            "reason": row["browser_reason"]
            if row["browser_status"] == "NOT_RUN"
            else None,
        }
    if driver.get("browser_required_not_run_blocks") != not_run:
        errors.append(f"{label} NOT_RUN list drift")
    native_not_run = [
        block_id
        for block_id in BLOCK_IDS
        if isinstance(contracts.get(block_id), dict)
        and contracts[block_id].get("native_status") == "NOT_RUN"
    ]
    if (
        native_not_run != ["api-network"]
        or not isinstance(contracts.get("api-network"), dict)
        or contracts["api-network"].get("native_reason")
        != "a single native adapter call does not prove timeout, retry, tenant cache, and unmount cancellation"
        or driver.get("native_required_not_run_blocks") != native_not_run
    ):
        errors.append(f"{label} native NOT_RUN ceiling drift")
    return result if set(result) == set(BLOCK_IDS) else {}


def native_block_status_ceiling(
    *, profile_id: str, driver: object, errors: list[str]
) -> dict[str, dict[str, Any]]:
    if not isinstance(driver, dict):
        return {}
    browser_block_status_contract(
        profile_id=profile_id, driver=driver, errors=errors
    )
    contracts = driver.get("block_observer_contracts")
    if not isinstance(contracts, dict) or set(contracts) != set(BLOCK_IDS):
        return {}
    return {
        block_id: {
            "status": contracts[block_id].get("native_status"),
            "reason": contracts[block_id].get("native_reason")
            if contracts[block_id].get("native_status") == "NOT_RUN"
            else None,
        }
        for block_id in BLOCK_IDS
    }


def validate_observed_block_statuses(
    *,
    profile_id: str,
    channel: str,
    observed: dict[str, dict[str, Any]],
    ceiling: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    label = f"toolchain v2 profile {profile_id} channel {channel}"
    if set(observed) != set(BLOCK_IDS) or set(ceiling) != set(BLOCK_IDS):
        errors.append(f"{label} block status/ceiling closure drift")
        return
    if channel == "browser":
        if observed != ceiling:
            errors.append(f"{label} exceeds or drifts from engine observer ceiling")
        return
    for block_id in BLOCK_IDS:
        row = observed[block_id]
        block_ceiling = ceiling[block_id]
        if (
            block_ceiling.get("status") == "NOT_RUN"
            and row != block_ceiling
        ) or (
            row.get("status") == "PASSED"
            and block_ceiling.get("status") != "PASSED"
        ):
            errors.append(
                f"{label} block {block_id} exceeds the engine native observer ceiling"
            )
FORMAL_PASS = {"PROVED", "PROVED_UNDER_ASSUMPTIONS"}
FORMAL_NONPASS = {"REFUTED", "NOT_PROVED", "UNKNOWN", "TIMEOUT", "NOT_RUN"}
MODEL_PRECEDENCE = {
    "DECLARATION_ECHO": 0,
    "TRANSITION": 1,
    "OBSERVABLE_EFFECT": 2,
}
RUNTIME_RESTRICTIVENESS = {
    "DECLARATION_ECHO": 0,
    "FRAMEWORK_OBSERVABLE": 1,
    "ADAPTER_SEAM_NOT_RUN": 2,
    "MODEL_ONLY_NOT_RUNTIME": 3,
}
EXPECTED_MODEL_INFLUENCE: dict[str, dict[str, str]] = {
    "route-navigation-deeplink-404": {
        "/navigation/fallback": "TRANSITION",
        "/navigation/routes": "TRANSITION",
        "/navigation/label": "DECLARATION_ECHO",
    },
    "component-template-view": {
        "/componentTemplate/keyedBy": "TRANSITION",
        "/componentTemplate/titleBinding": "TRANSITION",
        "/componentTemplate/textBinding": "TRANSITION",
        "/componentTemplate/componentId": "DECLARATION_ECHO",
        "/componentTemplate/templateKind": "DECLARATION_ECHO",
    },
    "state-management": {
        "/stateManagement/initial": "TRANSITION",
        "/stateManagement/minimum": "TRANSITION",
        "/stateManagement/maximum": "TRANSITION",
        "/stateManagement/transition": "TRANSITION",
        "/stateManagement/stateId": "DECLARATION_ECHO",
    },
    "action-event": {
        "/actionEvent/acceptedEvents": "TRANSITION",
        "/actionEvent/deniedAction": "TRANSITION",
        "/actionEvent/keyboardSubmit": "TRANSITION",
    },
    "effect-lifecycle": {
        "/effectLifecycle/mountEffect": "OBSERVABLE_EFFECT",
        "/effectLifecycle/cleanupEffect": "OBSERVABLE_EFFECT",
        "/effectLifecycle/maxExecutionsPerMount": "TRANSITION",
        "/effectLifecycle/staleResponsePolicy": "TRANSITION",
    },
    "form-binding-validation": {
        "/formBindingValidation/initialValue": "TRANSITION",
        "/formBindingValidation/required": "TRANSITION",
        "/formBindingValidation/minimumLength": "TRANSITION",
        "/formBindingValidation/validation": "TRANSITION",
        "/formBindingValidation/invalidCode": "TRANSITION",
        "/formBindingValidation/formId": "DECLARATION_ECHO",
        "/formBindingValidation/fieldId": "DECLARATION_ECHO",
    },
    "api-network": {
        "/apiNetwork/method": "OBSERVABLE_EFFECT",
        "/apiNetwork/path": "OBSERVABLE_EFFECT",
        "/apiNetwork/timeoutMs": "OBSERVABLE_EFFECT",
        "/apiNetwork/retry": "TRANSITION",
        "/apiNetwork/cacheScope": "TRANSITION",
        "/apiNetwork/cancelOnUnmount": "TRANSITION",
        "/apiNetwork/operationId": "DECLARATION_ECHO",
    },
    "identity-permission": {
        "/identityPermission/anonymousRole": "TRANSITION",
        "/identityPermission/authenticatedRole": "TRANSITION",
        "/identityPermission/requiredPermission": "TRANSITION",
        "/identityPermission/deniedBehavior": "TRANSITION",
        "/identityPermission/tenantIsolation": "TRANSITION",
        "/identityPermission/serverAuthorityRequired": "OBSERVABLE_EFFECT",
    },
    "rendering-hydration": {
        "/renderingHydration/mode": "DECLARATION_ECHO",
        "/renderingHydration/hydrationPolicy": "TRANSITION",
        "/renderingHydration/mismatchBehavior": "TRANSITION",
        "/renderingHydration/duplicateEffectsAllowed": "TRANSITION",
    },
    "accessibility-focus": {
        "/accessibilityFocus/mainRole": "OBSERVABLE_EFFECT",
        "/accessibilityFocus/headingLevel": "OBSERVABLE_EFFECT",
        "/accessibilityFocus/formLabel": "OBSERVABLE_EFFECT",
        "/accessibilityFocus/errorRole": "OBSERVABLE_EFFECT",
        "/accessibilityFocus/liveRegion": "OBSERVABLE_EFFECT",
        "/accessibilityFocus/invalidFocusTarget": "TRANSITION",
        "/accessibilityFocus/keyboardSubmit": "TRANSITION",
    },
    "i18n-theme-responsive": {
        "/i18nThemeResponsive/supportedLocales": "TRANSITION",
        "/i18nThemeResponsive/fallbackLocale": "TRANSITION",
        "/i18nThemeResponsive/themes": "TRANSITION",
        "/i18nThemeResponsive/defaultTheme": "TRANSITION",
        "/i18nThemeResponsive/compactBreakpoint": "TRANSITION",
        "/i18nThemeResponsive/compactColumns": "TRANSITION",
        "/i18nThemeResponsive/wideColumns": "TRANSITION",
    },
    "native-platform": {
        "/nativePlatform/boundary": "DECLARATION_ECHO",
        "/nativePlatform/capability": "TRANSITION",
        "/nativePlatform/lifecycleStates": "TRANSITION",
        "/nativePlatform/permission": "OBSERVABLE_EFFECT",
        "/nativePlatform/deniedBehavior": "TRANSITION",
        "/nativePlatform/recovery": "TRANSITION",
    },
}


def expected_runtime_influence(block_id: str) -> dict[str, str]:
    return {
        pointer: (
            "FRAMEWORK_OBSERVABLE"
            if block_id == "route-navigation-deeplink-404"
            and pointer == "/navigation/routes"
            else "DECLARATION_ECHO"
            if influence == "DECLARATION_ECHO"
            else "ADAPTER_SEAM_NOT_RUN"
            if influence == "OBSERVABLE_EFFECT"
            or block_id in {"api-network", "native-platform"}
            else "MODEL_ONLY_NOT_RUNTIME"
        )
        for pointer, influence in EXPECTED_MODEL_INFLUENCE[block_id].items()
    }


def canonical_runtime_projection(
    block_id: str, channel: str, canonical_observation: dict[str, Any]
) -> dict[str, Any] | None:
    required = RUNTIME_ACTUAL_KEYS.get(block_id)
    if required is None or not required.issubset(canonical_observation):
        return None
    value = {key: canonical_observation[key] for key in sorted(required)}
    if channel == "browser" and block_id == "native-platform":
        value.update(
            {"attempted": False, "available": False, "outcome": "NOT_ATTEMPTED"}
        )
    return value


def expected_runtime_projection_policy() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "kind": "frontend-runtime-canonical-projection-policy-v2",
        "proof_profile": "bounded-frontend-interaction-v1",
        "semantic_block_ids": list(BLOCK_IDS),
        "actual_keys": {
            block_id: sorted(RUNTIME_ACTUAL_KEYS[block_id]) for block_id in BLOCK_IDS
        },
        "default_projection": "SELECT_EXACT_ACTUAL_KEYS_FROM_CANONICAL_OBSERVATION",
        "channel_overrides": {
            "browser": {
                "native-platform": {
                    "attempted": False,
                    "available": False,
                    "outcome": "NOT_ATTEMPTED",
                }
            },
            "android": {},
            "ios": {},
            "harmonyos": {},
        },
        "comparison_relation": "EACH_ACTUAL_EQUALS_ITS_CHANNEL_CANONICAL_PROJECTION",
        "model_values_may_substitute_for_actual": False,
    }


def validate_runtime_driver_contract_v2(
    *,
    profile_id: str,
    profile_record: dict[str, Any],
    scenario_ids: list[str],
    errors: list[str],
) -> None:
    label = f"profile {profile_id} runtime driver contract"
    driver = profile_record.get("runtime_driver_contract")
    required_channels = list(REQUIRED_RUNTIME_CHANNELS[profile_id])
    if not isinstance(driver, dict):
        errors.append(f"{label} is missing")
        return
    if (
        profile_record.get("runtime_driver_contract_digest")
        != v1.canonical_digest(driver)
        or set(driver) != RUNTIME_DRIVER_CONTRACT_KEYS
        or driver.get("schema_version") != "1.0"
        or driver.get("kind")
        != (
            "bounded-interaction-native-semantics-driver-contract"
            if profile_id in {"flutter", "harmony-arkui"}
            else "bounded-interaction-framework-browser-driver-contract"
        )
        or not isinstance(driver.get("framework_binding"), str)
        or not driver["framework_binding"]
        or driver.get("runtime_evidence_eligibility")
        != "ELIGIBLE_LOCAL_ACTUAL_RUNTIME_EXECUTION"
        or driver.get("runtime_status") != "NOT_RUN"
        or driver.get("independent_runtime_oracle") != "NOT_RUN"
        or driver.get("customer_runtime_evidence") != "NOT_RUN"
        or driver.get("certification") != "NOT_CERTIFIED"
        or driver.get("required_runtime_channels") != required_channels
        or driver.get("observer_protocol") != "block-specific-runtime-observation-v1"
        or driver.get("actual_source") != "BLOCK_SPECIFIC_RUNTIME_OBSERVED"
        or driver.get("self_reported_reducer_json_allowed") is not False
        or driver.get("legacy_runtime_observed_allowed") is not False
        or driver.get("declaration_payload_allowed_keys")
        != [
            "schema_version",
            "kind",
            "block_id",
            "status",
            "observer_kind",
            "measurement_surface",
            "reason",
        ]
        or driver.get("runtime_source_value")
        != "BLOCK_SPECIFIC_RUNTIME_OBSERVED"
        or driver.get("native_adapter_evidence") != "NOT_RUN"
        or driver.get("browser_or_device_evidence") != "NOT_RUN"
        or driver.get("native_route_without_real_device_channel_status")
        != "NOT_RUN"
    ):
        errors.append(f"{label} eligibility/evidence boundary drift")
    browser_block_status_contract(
        profile_id=profile_id, driver=driver, errors=errors
    )
    projection = driver.get("channel_projection_contract")
    if not isinstance(projection, dict):
        errors.append(f"{label} channel projection is missing")
        return
    block_actual_keys = projection.get("block_actual_keys")
    if (
        set(projection)
        != {
            "schema_version",
            "kind",
            "projection",
            "model_digest",
            "block_actual_keys",
            "scenario_ids",
            "channels",
            "oracle_provenance",
            "arbitrary_customer_runtime",
        }
        or projection.get("schema_version") != "1.0"
        or projection.get("kind")
        != "bounded-interaction-channel-projection-contract"
        or projection.get("projection") != "STRICT_RUNTIME_OBSERVATION_V1"
        or projection.get("model_digest") != profile_record.get("relift_model_digest")
        or not isinstance(block_actual_keys, dict)
        or set(block_actual_keys) != set(BLOCK_IDS)
        or any(
            not isinstance(block_actual_keys.get(block_id), list)
            or set(block_actual_keys[block_id]) != RUNTIME_ACTUAL_KEYS[block_id]
            for block_id in BLOCK_IDS
        )
        or projection.get("scenario_ids") != scenario_ids
        or projection.get("oracle_provenance")
        != "SAME_PRODUCER_CHANNEL_PROJECTION_NOT_INDEPENDENT"
        or projection.get("arbitrary_customer_runtime") != "NOT_PROVED"
        or driver.get("channel_projection_contract_digest")
        != v1.canonical_digest(projection)
    ):
        errors.append(f"{label} projection identity/digest drift")
    channels = projection.get("channels")
    if not isinstance(channels, dict) or set(channels) != set(required_channels):
        errors.append(f"{label} required channel closure drift")
        return
    for channel in required_channels:
        channel_value = channels.get(channel)
        scenarios = channel_value.get("scenarios") if isinstance(channel_value, dict) else None
        if (
            not isinstance(channel_value, dict)
            or set(channel_value) != {"status", "native_execution_allowed", "scenarios"}
            or channel_value.get("status") != "NOT_RUN"
            or channel_value.get("native_execution_allowed") is (channel == "browser")
            or not isinstance(scenarios, list)
            or [row.get("scenario_id") for row in scenarios if isinstance(row, dict)]
            != scenario_ids
        ):
            errors.append(f"{label} {channel} projection closure drift")
            continue
        for scenario in scenarios:
            blocks = scenario.get("blocks")
            digests = scenario.get("block_digests")
            if (
                set(scenario) != {"scenario_id", "blocks", "block_digests"}
                or not isinstance(blocks, dict)
                or set(blocks) != set(BLOCK_IDS)
                or not isinstance(digests, dict)
                or set(digests) != set(BLOCK_IDS)
            ):
                errors.append(f"{label} {channel} scenario projection drift")
                continue
            for block_id in BLOCK_IDS:
                actual = blocks.get(block_id)
                if (
                    not isinstance(actual, dict)
                    or set(actual) != RUNTIME_ACTUAL_KEYS[block_id]
                    or digests.get(block_id) != v1.canonical_digest(actual)
                ):
                    errors.append(
                        f"{label} {channel}/{scenario.get('scenario_id')}/{block_id} projection drift"
                    )
                if (
                    channel == "browser"
                    and block_id == "native-platform"
                    and isinstance(actual, dict)
                    and (
                        actual.get("attempted") is not False
                        or actual.get("available") is not False
                        or actual.get("outcome") != "NOT_ATTEMPTED"
                    )
                ):
                    errors.append(
                        f"{label} {channel}/{scenario.get('scenario_id')} native projection drift"
                    )


def runtime_driver_projection_v2(
    profile_record: dict[str, Any],
    channel: str,
    scenario_id: str,
    block_id: str,
) -> dict[str, Any] | None:
    try:
        scenarios = profile_record["runtime_driver_contract"][
            "channel_projection_contract"
        ]["channels"][channel]["scenarios"]
    except (KeyError, TypeError):
        return None
    matches = [
        row for row in scenarios if isinstance(row, dict) and row.get("scenario_id") == scenario_id
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("blocks"), dict):
        return None
    value = matches[0]["blocks"].get(block_id)
    return value if isinstance(value, dict) else None


def runtime_scope_contract_v2(
    *,
    profile_id: str,
    channel: str,
    record: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    label = f"toolchain v2 runtime scope {profile_id}/{channel}"
    status = record.get("status")
    active_runtime = status == "PASSED" or (
        status == "NOT_RUN"
        and record.get("reason") == "BLOCK_SPECIFIC_RUNTIME_PARTIAL_CLOSURE"
    )
    required = channel in REQUIRED_RUNTIME_CHANNELS[profile_id]
    normalized_tools: list[dict[str, Any]] = []
    if active_runtime:
        runtime_tools = record.get("runtime_tools")
        if not isinstance(runtime_tools, list) or not runtime_tools:
            errors.append(f"{label} runtime tools are absent")
            runtime_tools = []
        for index, item in enumerate(runtime_tools):
            if not isinstance(item, dict) or set(item) != {
                "role",
                "path",
                "realpath",
                "sha256",
                "byte_count",
                "version",
                "package_closure_digest",
            }:
                errors.append(f"{label} runtime tool {index} key closure drift")
                continue
            for digest_name in ("sha256", "package_closure_digest"):
                value = item.get(digest_name)
                if (
                    not isinstance(value, str)
                    or len(value) != 71
                    or not value.startswith("sha256:")
                ):
                    errors.append(f"{label} runtime tool {index} digest drift")
            if (
                not isinstance(item.get("role"), str)
                or not item.get("role")
                or not isinstance(item.get("version"), str)
                or not item.get("version")
                or not isinstance(item.get("path"), str)
                or not Path(str(item.get("path"))).is_absolute()
                or not isinstance(item.get("realpath"), str)
                or not Path(str(item.get("realpath"))).is_absolute()
                or type(item.get("byte_count")) is not int
                or item.get("byte_count", 0) < 1
            ):
                errors.append(f"{label} runtime tool {index} host identity drift")
            normalized_tools.append(
                {
                    "role": item.get("role"),
                    "path": item.get("path"),
                    "realpath": item.get("realpath"),
                    "version": item.get("version"),
                    "sha256": item.get("sha256"),
                    "byte_count": item.get("byte_count"),
                    "package_closure_digest": item.get("package_closure_digest"),
                }
            )
        tool_roles = [item.get("role") for item in normalized_tools]
        if len(tool_roles) != len(set(tool_roles)):
            errors.append(f"{label} runtime tool role collision")

    browser_matrix: dict[str, Any] | None = None
    if channel == "browser" and active_runtime:
        discovery = record.get("tool_discovery")
        candidates = (
            [
                item
                for item in discovery
                if isinstance(item, dict) and item.get("kind") == "EXACT_BROWSER_MATRIX"
            ]
            if isinstance(discovery, list)
            else []
        )
        if len(candidates) != 1:
            errors.append(f"{label} exact browser matrix closure drift")
            matrix: dict[str, Any] = {}
        else:
            matrix = candidates[0]
        values = matrix.get("browser_matrix")
        if not isinstance(values, list):
            values = []
        tools_by_role = {
            str(item.get("role")): item for item in normalized_tools
        }
        if profile_id == "flutter":
            expected_keys = {
                "kind",
                "policy_id",
                "browser_matrix",
                "cross_browser",
                "capability_scope",
            }
            valid = (
                set(matrix) == expected_keys
                and matrix.get("policy_id") == "flutter-web-cft-chrome-drive-v1"
                and matrix.get("cross_browser") is False
                and matrix.get("capability_scope")
                == "flutter-web-chrome-drive-only"
                and len(values) == 1
                and isinstance(values[0], dict)
                and set(values[0])
                == {
                    "browser_id",
                    "engine",
                    "version",
                    "executable_sha256",
                    "driver_version",
                    "driver_sha256",
                }
                and values[0].get("browser_id") == "cft-chrome"
                and values[0].get("engine") == "chromium"
                and values[0].get("version") == "151.0.7922.77"
                and values[0].get("driver_version") == "151.0.7922.77"
                and values[0].get("executable_sha256")
                == tools_by_role.get("flutter-cft-chrome", {}).get("sha256")
                and values[0].get("driver_sha256")
                == tools_by_role.get("flutter-cft-chromedriver", {}).get("sha256")
            )
        else:
            expected_keys = {"kind", "policy_id", "browser_matrix", "cross_browser"}
            valid = (
                set(matrix) == expected_keys
                and matrix.get("policy_id") == "node-web-chromium-firefox-v1"
                and matrix.get("cross_browser") is True
                and len(values) == 2
                and all(
                    isinstance(value, dict)
                    and set(value)
                    == {"browser_id", "engine", "version", "executable_sha256"}
                    for value in values
                )
                and [
                    (value.get("browser_id"), value.get("engine")) for value in values
                ]
                == [("google-chrome", "chromium"), ("mozilla-firefox", "firefox")]
                and all(
                    value.get("executable_sha256")
                    == tools_by_role.get(
                        f"browser-{value.get('engine')}", {}
                    ).get("sha256")
                    for value in values
                )
            )
        tool_digests = {item.get("sha256") for item in normalized_tools}
        matrix_digests = {
            value.get("executable_sha256") for value in values if isinstance(value, dict)
        } | {
            value.get("driver_sha256")
            for value in values
            if isinstance(value, dict) and value.get("driver_sha256") is not None
        }
        if not valid or not matrix_digests or not matrix_digests.issubset(tool_digests):
            errors.append(f"{label} browser matrix policy/tool digest drift")
        browser_matrix = {
            key: matrix.get(key)
            for key in (
                "policy_id",
                "browser_matrix",
                "cross_browser",
                "capability_scope",
            )
            if key in matrix
        }
        browser_matrix["fingerprint"] = v1.canonical_digest(browser_matrix)

    return {
        "required": required,
        "status": status,
        "runner_kind": record.get("runner_kind") if active_runtime else None,
        "execution_policy_digest": (
            record.get("execution_policy_digest") if active_runtime else None
        ),
        "runtime_tools": normalized_tools,
        "browser_matrix": browser_matrix,
        "portable_replay": False,
        "portable_replay_status": "NOT_RUN",
    }


FORBIDDEN_INDEPENDENT_KINDS = {
    "ENGINE_AUTHORITATIVE_MODEL",
    "ENGINE_REFERENCE_REDUCER",
    "SOURCE_RELIFT_MODEL",
    "TARGET_RELIFT_MODEL",
    "GENERATED_SOURCE",
    "GENERATED_TARGET",
    "FORMAL_INPUT",
    "SOLVER_INPUT",
    "SOLVER_RESULT",
}
REQUIRED_IMPLEMENTATION_REPOSITORY_PATHS = frozenset(
    {
        "engines/frontend-client-engine/src/frontend-interaction-formal-equivalence.ts",
        "engines/frontend-client-engine/src/frontend-interaction-formal-cli.ts",
        "engines/frontend-client-engine/src/bounded-interaction-source.ts",
        "engines/frontend-client-engine/src/bounded-interaction-project.ts",
        "engines/frontend-client-engine/src/frontend-formal-equivalence.ts",
        "engines/frontend-client-engine/src/bounded-navigation-source.ts",
        "engines/frontend-client-engine/src/project-generation.ts",
        "engines/frontend-client-engine/src/project-profiles.ts",
        "engines/frontend-client-engine/src/project-templates.ts",
        "engines/frontend-client-engine/src/project-types.ts",
        "engines/frontend-client-engine/test/frontend-interaction-formal-equivalence.test.ts",
        "engines/frontend-client-engine/test/frontend-formal-equivalence.test.ts",
        "engines/frontend-client-engine/test/project-generation.test.ts",
        "engines/frontend-client-engine/dist/src/frontend-interaction-formal-cli.js",
        "engines/frontend-client-engine/dist/src/frontend-interaction-formal-equivalence.js",
        "engines/frontend-client-engine/dist/src/bounded-interaction-source.js",
        "engines/frontend-client-engine/dist/src/bounded-interaction-project.js",
        "engines/frontend-client-engine/dist/src/bounded-navigation-source.js",
        "engines/frontend-client-engine/dist/src/frontend-formal-equivalence.js",
        "engines/frontend-client-engine/dist/src/project-generation.js",
        "engines/frontend-client-engine/dist/src/project-profiles.js",
        "engines/frontend-client-engine/dist/src/project-templates.js",
        "engines/frontend-client-engine/dist/src/project-types.js",
        "engines/frontend-client-engine/package.json",
        "engines/frontend-client-engine/pnpm-lock.yaml",
        "engines/frontend-client-engine/tsconfig.json",
        "tooling/run_frontend_formal_toolchains.py",
        "tooling/frontend_formal_playwright_probe.cjs",
        "tooling/generate_frontend_formal_verification_pack.py",
        "apps/web-console/package.json",
        "apps/web-console/pnpm-lock.yaml",
        "scripts/batch32/run_client_gate.py",
        "scripts/batch32/validate_client_pack.py",
        "scripts/batch32/validate_frontend_formal_route_campaign_v2.py",
        "scripts/batch35/run_verification_gate.py",
        "scripts/batch35/validate_verification_pack.py",
        "scripts/batch35/validate_frontend_formal_route_campaign_v2.py",
        "schemas/batch32/client-pack.schema.json",
        "schemas/batch32/frontend-formal-route-campaign-v2.schema.json",
        "schemas/batch32/frontend-formal-route-evidence-v2.schema.json",
        "schemas/batch32/frontend-formal-external-evidence-v2.schema.json",
        "schemas/batch32/frontend-formal-external-trust-store-v2.schema.json",
        "schemas/batch32/frontend-formal-external-trust-root-v2.schema.json",
        "schemas/batch32/frontend-formal-external-route-block-execution-v2.schema.json",
        "schemas/batch32/frontend-formal-external-route-block-replay-v2.schema.json",
        "schemas/batch32/frontend-formal-external-runtime-observation-v2.schema.json",
        "schemas/batch32/frontend-formal-external-corpus-manifest-v2.schema.json",
        "schemas/batch32/frontend-formal-external-replay-verifier-result-v2.schema.json",
        "schemas/batch35/verification-pack.schema.json",
        "schemas/batch35/frontend-formal-route-campaign-v2.schema.json",
        "schemas/batch35/frontend-formal-route-evidence-v2.schema.json",
        "schemas/batch35/frontend-formal-external-evidence-v2.schema.json",
        "schemas/batch35/frontend-formal-external-trust-store-v2.schema.json",
        "schemas/batch35/frontend-formal-external-trust-root-v2.schema.json",
        "schemas/batch35/frontend-formal-external-route-block-execution-v2.schema.json",
        "schemas/batch35/frontend-formal-external-route-block-replay-v2.schema.json",
        "schemas/batch35/frontend-formal-external-runtime-observation-v2.schema.json",
        "schemas/batch35/frontend-formal-external-corpus-manifest-v2.schema.json",
        "schemas/batch35/frontend-formal-external-replay-verifier-result-v2.schema.json",
        "tests/batch32/test_frontend_formal_route_campaign_v2.py",
        "tests/batch35/test_frontend_formal_route_gate_v2.py",
        "tests/frontend_formal_toolchains/test_runner.py",
    }
)
REQUIRED_REPLAY_REPOSITORY_PATHS = frozenset(
    {
        "tooling/generate_frontend_formal_verification_pack.py",
        "scripts/batch32/validate_frontend_formal_route_campaign.py",
        "scripts/batch32/validate_frontend_formal_route_campaign_v2.py",
        "scripts/batch32/replay_frontend_formal_route_campaign_v2.py",
        "scripts/batch35/validate_frontend_formal_route_campaign_v2.py",
        "schemas/batch32/frontend-formal-route-campaign.schema.json",
        "schemas/batch32/frontend-formal-route-campaign-v2.schema.json",
        "schemas/batch32/frontend-formal-route-evidence-v2.schema.json",
        "schemas/batch32/frontend-formal-external-evidence-v2.schema.json",
        "schemas/batch32/frontend-formal-external-trust-store-v2.schema.json",
        "schemas/batch32/frontend-formal-external-trust-root-v2.schema.json",
        "schemas/batch32/frontend-formal-external-route-block-execution-v2.schema.json",
        "schemas/batch32/frontend-formal-external-route-block-replay-v2.schema.json",
        "schemas/batch32/frontend-formal-external-runtime-observation-v2.schema.json",
        "schemas/batch32/frontend-formal-external-corpus-manifest-v2.schema.json",
        "schemas/batch32/frontend-formal-external-replay-verifier-result-v2.schema.json",
        "schemas/batch35/frontend-formal-route-campaign-v2.schema.json",
        "schemas/batch35/frontend-formal-route-evidence-v2.schema.json",
        "schemas/batch35/frontend-formal-external-evidence-v2.schema.json",
        "schemas/batch35/frontend-formal-external-trust-store-v2.schema.json",
        "schemas/batch35/frontend-formal-external-trust-root-v2.schema.json",
        "schemas/batch35/frontend-formal-external-route-block-execution-v2.schema.json",
        "schemas/batch35/frontend-formal-external-route-block-replay-v2.schema.json",
        "schemas/batch35/frontend-formal-external-runtime-observation-v2.schema.json",
        "schemas/batch35/frontend-formal-external-corpus-manifest-v2.schema.json",
        "schemas/batch35/frontend-formal-external-replay-verifier-result-v2.schema.json",
    }
)
SOLVER_REPLAY_CACHE: dict[tuple[str, str], tuple[int, bytes, bytes]] = {}
MAIN_SOLVER_KEYS = frozenset(v1.ENGINE_SOLVER_RESULT_KEYS)
VACUITY_SOLVER_KEYS = MAIN_SOLVER_KEYS | {"precheck_status"}
BLOCK_RESULT_KEYS = frozenset(
    {
        "block_id",
        "obligation_symbol",
        "influence_classes",
        "model_influence_max",
        "runtime_influence_max",
        "canonical_block_digest",
        "source_block_digest",
        "target_block_digest",
        "behavior_block_digest",
        "chunk_block_digest",
        "formal_input_digest",
        "solver_input_digest",
        "solver_result_digest",
        "vacuity_input_digest",
        "vacuity_solver_result_digest",
        "mutation_campaign_digest",
        "semantic_status",
        "chunk_status",
        "model_behavior_status",
        "raw_solver_status",
        "formal_status",
        "assumption_precheck",
        "semantic_mutant_detected",
        "behavior_mutant_detected",
        "declaration_echo_excluded_from_behavior_denominator",
        "runtime_evidence_eligibility",
        "runtime_status",
        "oracle_provenance",
        "status",
    }
)
TOOLCHAIN_TOP_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "generated_at",
        "producer",
        "campaign",
        "engine_preverification",
        "implementation_closure",
        "semantic_block_ids",
        "scenario_manifest_digest",
        "scenario_policy",
        "mutation_replay",
        "policy",
        "profile_executions",
        "route_records",
        "summary",
        "evidence_identity",
        "replay",
    }
)
TOOLCHAIN_POLICY_KEYS = frozenset(
    {
        "no_network",
        "timeout_seconds",
        "network_timeout_seconds",
        "chrome_path",
        "firefox_path",
        "android_device_id",
        "ios_simulator_udid",
        "harmony_device_id",
        "harmony_sdk_root",
        "selected_profiles",
        "fail_on_unavailable",
        "profile_build_deduplication",
        "workspace_retention",
    }
)
TOOLCHAIN_PROFILE_KEYS = frozenset(
    {
        "execution_id",
        "producer",
        "profile_id",
        "project_digest",
        "status",
        "reason",
        "target_build",
        "tool_versions",
        "tool_discovery",
        "commands",
        "browser_journey",
        "required_runtime_channels",
        "runtime_model_oracle_findings",
        "runtime_observations",
        "artifacts",
        "boundaries",
        "replay_profile_args",
    }
)
TOOLCHAIN_CHANNEL_KEYS = frozenset(
    {
        "channel",
        "required",
        "status",
        "reason",
        "runner_kind",
        "tool_discovery",
        "execution_policy_digest",
        "runtime_tools",
        "build_execution",
        "startup_execution",
        "journey_execution",
        "scenario_manifest_digest",
        "scenario_count",
        "scenarios",
        "semantic_blocks",
        "raw_artifacts",
        "runtime_source_artifacts",
        "result_manifest",
        "model_values_used_as_actual",
    }
)
TOOLCHAIN_ROUTE_KEYS = frozenset(
    {
        "route_id",
        "source_profile",
        "target_profile",
        "source_project_digest",
        "target_project_digest",
        "source_execution_id",
        "target_execution_id",
        "source_toolchain_status",
        "target_toolchain_status",
        "source_browser_status",
        "target_browser_status",
        "status",
        "formal_route_status",
        "formal_evidence",
        "browser_evidence",
        "device_or_simulator_evidence",
        "source_required_runtime_channels",
        "target_required_runtime_channels",
        "runtime_blocks",
        "cross_channel_equivalence",
        "runtime_ready",
        "independent_runtime_verification",
        "holdout_evidence",
        "representative_customer_evidence",
        "certification",
    }
)
TOOLCHAIN_MUTATION_VARIANTS = (
    "SOURCE_ONLY",
    "TARGET_ONLY",
    "REFERENCE_ONLY",
)


def formal_proof_contract_v2(
    *,
    proof_status: object,
    unconditional_proof: object,
    assumptions: object,
    unsupported_semantics: object | None = None,
    label: str,
    errors: list[str],
) -> str:
    """Validate the exact cross-layer shape of a v2 formal proof claim."""

    if (
        not isinstance(assumptions, list)
        or any(not isinstance(item, str) or not item for item in assumptions)
        or len(assumptions) != len(set(assumptions))
    ):
        errors.append(f"{label} formal assumption contract drift")
        assumptions = []
    if unsupported_semantics is not None and (
        not isinstance(unsupported_semantics, list)
        or any(
            not isinstance(item, str) or not item for item in unsupported_semantics
        )
        or len(unsupported_semantics) != len(set(unsupported_semantics))
    ):
        errors.append(f"{label} formal unsupported-semantics contract drift")
        unsupported_semantics = []
    unsupported = unsupported_semantics or []
    if proof_status == "PROVED":
        if unconditional_proof is not True or assumptions or unsupported:
            errors.append(f"{label} unconditional formal claim is mixed")
        return "theorem"
    if proof_status == "PROVED_UNDER_ASSUMPTIONS":
        if unconditional_proof is not False or not assumptions:
            errors.append(f"{label} PUA formal claim is mixed")
        return "assumption"
    if unconditional_proof is not False:
        errors.append(f"{label} non-proof claims unconditional proof")
    return "none"


def validate_solver_artifact(
    *,
    label: str,
    route_id: str,
    result_id: str,
    smt_id: str,
    formal_input_digest: str,
    expected_outcome: str,
    expected_proof_status: str,
    expected_unconditional_proof: bool,
    assumptions: list[str],
    solver_binary_id: str,
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    execute_solver_replay: bool,
    errors: list[str],
    vacuity: bool = False,
) -> dict[str, Any]:
    result_path = artifact_files.get(result_id)
    smt_path = artifact_files.get(smt_id)
    binary_path = artifact_files.get(solver_binary_id)
    if result_path is None or smt_path is None or binary_path is None:
        errors.append(f"{label} raw solver closure is incomplete")
        return {}
    try:
        result = load_json(result_path)
    except Exception as exc:
        errors.append(f"{label} solver result is invalid: {exc}")
        return {}
    smt = smt_path.read_bytes()
    smt_digest = v1.digest_bytes(smt)
    expected_keys = VACUITY_SOLVER_KEYS if vacuity else MAIN_SOLVER_KEYS
    realpath = result.get("solver_binary_realpath")
    expected_stdout = "sat\n" if expected_outcome == "SAT" else "unsat\n"
    expected_proof = "REFUTED" if vacuity else expected_proof_status
    expected_unconditional = False if vacuity else expected_unconditional_proof
    formal_proof_contract_v2(
        proof_status=result.get("proof_status"),
        unconditional_proof=result.get("unconditional_proof"),
        assumptions=[] if vacuity else assumptions,
        label=f"{label} solver result",
        errors=errors,
    )
    if (
        set(result) != expected_keys
        or result.get("schema_version") != "1.0"
        or result.get("route_id") != route_id
        or result.get("formal_input_digest") != formal_input_digest
        or result.get("solver_input_digest") != smt_digest
        or result.get("smt2_digest") != smt_digest
        or result.get("identity_status") != "VERIFIED"
        or not isinstance(realpath, str)
        or not Path(realpath).is_absolute()
        or Path(realpath).name != "z3"
        or result.get("solver") != realpath
        or result.get("solver_binary_sha256") != v1.LOCKED_Z3_BINARY_SHA256
        or result.get("solver_version") != v1.LOCKED_Z3_VERSION
        or result.get("invocation") != [realpath, "-in"]
        or result.get("options") != v1.LOCKED_Z3_OPTIONS
        or result.get("environment") != v1.LOCKED_Z3_ENVIRONMENT
        or result.get("exit_code") != 0
        or result.get("stdout") != expected_stdout
        or result.get("stderr") != ""
        or result.get("outcome") != expected_outcome
        or result.get("proof_status") != expected_proof
        or result.get("unconditional_proof") is not expected_unconditional
        or (vacuity and result.get("precheck_status") != "PASSED")
        or artifacts.get(solver_binary_id, {}).get("sha256")
        != v1.LOCKED_Z3_BINARY_SHA256
    ):
        errors.append(f"{label} solver identity/result/linkage drift")
    replay_key = (v1.LOCKED_Z3_BINARY_SHA256, smt_digest)
    replay = SOLVER_REPLAY_CACHE.get(replay_key) if execute_solver_replay else None
    if execute_solver_replay and replay is None:
        try:
            completed = subprocess.run(
                [str(binary_path), "-in"],
                input=smt,
                capture_output=True,
                timeout=10,
                check=False,
            )
            replay = (completed.returncode, completed.stdout, completed.stderr)
            SOLVER_REPLAY_CACHE[replay_key] = replay
        except Exception as exc:
            errors.append(f"{label} locked solver replay failed: {exc}")
    if execute_solver_replay and replay is not None and replay != (
        result.get("exit_code"),
        expected_stdout.encode("utf-8"),
        b"",
    ):
        errors.append(f"{label} locked solver replay diverged")
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def exact_routes() -> set[str]:
    return {
        f"{source}--to--{target}"
        for source in PROFILE_IDS
        for target in PROFILE_IDS
        if source != target
    }


def is_captured_replay(path: Path) -> bool:
    parts = path.resolve().parts
    return any(
        parts[index : index + 2] == ("formal-campaign", "replay")
        for index in range(max(0, len(parts) - 1))
    )


def aggregate_status(values: list[str], *, applicable: bool = True) -> str:
    if not applicable:
        return "NOT_APPLICABLE"
    if not values or all(value == "NOT_RUN" for value in values):
        return "NOT_RUN"
    if "FAILED" in values:
        return "FAILED"
    if all(value in {"PASSED", "NOT_APPLICABLE"} for value in values):
        return "PASSED"
    return "PARTIAL"


def closed_status(values: list[str], *, applicable: bool = True) -> str:
    if not applicable:
        return "NOT_APPLICABLE"
    if "FAILED" in values:
        return "FAILED"
    if values and all(value in {"PASSED", "NOT_APPLICABLE"} for value in values):
        return "PASSED"
    return "NOT_RUN"


def unsupported_semantics_v2(
    *,
    arbitrary_customer_source: str,
    profile_channel_statuses: dict[str, dict[str, str]],
    independent_status: str,
) -> list[str]:
    unsupported: list[str] = []
    if arbitrary_customer_source != "PROVED":
        unsupported.append(
            f"arbitrary-customer-source-{arbitrary_customer_source}"
        )
    for channel in RUNTIME_CHANNELS:
        aggregate = aggregate_status(
            [
                profile_channel_statuses.get(profile_id, {}).get(
                    channel, "NOT_RUN"
                )
                for profile_id in PROFILE_IDS
                if channel in REQUIRED_RUNTIME_CHANNELS[profile_id]
            ]
        )
        if aggregate != "PASSED":
            unsupported.append(f"{channel}-runtime-{aggregate}")
    if independent_status != "PASSED":
        unsupported.append(
            f"independent-external-verification-{independent_status}"
        )
    return unsupported


def formal_readiness_v2(
    *,
    model_formal_ready: bool,
    route_results: list[dict[str, Any]],
    campaign: dict[str, Any],
) -> bool:
    """Only an assumption-free, fully closed proof matrix is formal-ready."""

    return (
        model_formal_ready
        and len(route_results) == 72
        and all(
            item.get("model_formal_status") == "PASSED"
            for item in route_results
        )
        and all(item.get("unconditional") is True for item in route_results)
        and not campaign.get("assumptions")
        and not campaign.get("unsupported_semantics")
        and campaign.get("unconditional_proof") is True
    )


def campaign_scope_value_v2(
    campaign: dict[str, Any],
    corpora: dict[str, Any],
    runtime_projection: dict[str, Any],
    scenario_sha256: object,
) -> dict[str, Any]:
    return {
        "campaign_key": campaign.get("campaign_key"),
        "version": campaign.get("version"),
        "proof_profile": campaign.get("proof_profile"),
        "semantic_block_ids": campaign.get("semantic_block_ids"),
        "block_symbol_map": campaign.get("block_symbol_map"),
        "scenario_manifest_sha256": scenario_sha256,
        "profiles": [
            {
                "profile": record.get("profile"),
                "profile_digest": record.get("profile_digest"),
                "project_digest": record.get("project_digest"),
                "required_runtime_channels": record.get("required_runtime_channels"),
                "runtime_driver_contract_digest": record.get(
                    "runtime_driver_contract_digest"
                ),
            }
            for record in campaign.get("profiles", [])
            if isinstance(record, dict)
        ],
        "routes": [
            {
                key: route.get(key)
                for key in (
                    "route_id",
                    "source_profile_digest",
                    "target_profile_digest",
                    "source_project_digest",
                    "target_project_digest",
                )
            }
            for route in campaign.get("routes", [])
            if isinstance(route, dict)
        ],
        "corpus_ids": {
            name: corpora.get(name, {}).get("id")
            for name in (
                "development",
                "negative",
                "holdout",
                "representative_workloads",
            )
        },
        "runtime_profile_channel_contracts": runtime_projection.get(
            "profile_channel_contracts"
        ),
    }


def expected_gap_inventory_v2(
    campaign: dict[str, Any], artifact_files: dict[str, Path]
) -> tuple[set[str], dict[str, str]]:
    rows: set[str] = set()
    independent_values: list[str] = []
    holdout_values: list[str] = []
    representative_values: list[str] = []
    route_values = [item for item in campaign.get("routes", []) if isinstance(item, dict)]
    for route in route_values:
        wrapper_path = artifact_files.get(str(route.get("route_evidence_artifact_id")))
        if wrapper_path is None:
            continue
        try:
            wrapper = load_json(wrapper_path)
        except Exception:
            continue
        blocks = {
            str(item.get("block_id")): item
            for item in wrapper.get("blocks", [])
            if isinstance(item, dict)
        }
        for block_id in BLOCK_IDS:
            block = blocks.get(block_id, {})
            runtime = block.get("runtime", {})
            channel_values: dict[str, list[str]] = {
                channel: [] for channel in RUNTIME_CHANNELS
            }
            for endpoint in ("source", "target"):
                endpoint_value = runtime.get(endpoint, {})
                channels = endpoint_value.get("channels", {})
                for channel in endpoint_value.get("required_runtime_channels", []):
                    if channel in channel_values and isinstance(channels, dict):
                        channel_values[channel].append(
                            str(channels.get(channel, {}).get("status"))
                        )
            cross_dimensions = runtime.get("cross_channel_equivalence", {}).get(
                "dimension_closure", {}
            )
            browser_cross = (
                str(cross_dimensions.get("browser", {}).get("status"))
                if isinstance(cross_dimensions, dict)
                and isinstance(cross_dimensions.get("browser"), dict)
                and cross_dimensions["browser"].get("applicable") is True
                else None
            )
            native_cross = (
                str(cross_dimensions.get("native", {}).get("status"))
                if isinstance(cross_dimensions, dict)
                and isinstance(cross_dimensions.get("native"), dict)
                and cross_dimensions["native"].get("applicable") is True
                else None
            )
            dimensions = [
                aggregate_status(
                    values
                    + (
                        [browser_cross]
                        if channel == "browser" and browser_cross is not None
                        else [native_cross]
                        if channel != "browser" and native_cross is not None
                        else []
                    ),
                    applicable=bool(values),
                )
                for channel, values in (
                    ("browser", channel_values["browser"]),
                    ("android", channel_values["android"]),
                    ("ios", channel_values["ios"]),
                    ("harmonyos", channel_values["harmonyos"]),
                )
            ]
            independent = block.get("independent", {})
            independent_status = str(independent.get("status"))
            independent_values.append(independent_status)
            holdout_values.append(str(independent.get("holdout_status")))
            representative_values.append(
                str(independent.get("representative_status"))
            )
            rows.add(
                f"| {route.get('route_id')} | {block_id} | PASSED | "
                f"{block.get('formal', {}).get('status')} | "
                + " | ".join(dimensions)
                + f" | {independent_status} | NOT_CERTIFIED |"
            )
    status_map = campaign.get("toolchain_evidence", {}).get(
        "profile_channel_statuses", {}
    )
    channel_aggregates = {
        channel: aggregate_status(
            [
                str(status_map.get(profile_id, {}).get(channel, "NOT_RUN"))
                for profile_id in PROFILE_IDS
                if channel in REQUIRED_RUNTIME_CHANNELS[profile_id]
            ]
        )
        for channel in RUNTIME_CHANNELS
    }
    browser_status = aggregate_status(
        [str(route.get("browser_status")) for route in route_values]
    )
    native_route_values = [
        str(route.get("native_status"))
        for route in route_values
        if route.get("native_status") != "NOT_APPLICABLE"
    ]
    native_status = aggregate_status(
        native_route_values, applicable=bool(native_route_values)
    )
    runtime_status = aggregate_status(
        [str(route.get("runtime_status")) for route in route_values]
    )
    dimensions = {
        "browser": browser_status,
        "native": native_status,
        "android": channel_aggregates["android"],
        "ios": channel_aggregates["ios"],
        "harmonyos": channel_aggregates["harmonyos"],
        "runtime": runtime_status,
        "independent": aggregate_status(independent_values),
        "holdout": aggregate_status(holdout_values),
        "representative": aggregate_status(representative_values),
    }
    return rows, dimensions


def schema_without_external_profile_ref(schema: dict[str, Any]) -> dict[str, Any]:
    """The replay evaluator is offline; profile identity is checked manually."""

    value = copy.deepcopy(schema)

    def walk(item: object) -> None:
        if isinstance(item, dict):
            reference = item.get("$ref")
            if isinstance(reference, str) and reference.startswith(
                "https://example.invalid/batch32/frontend-formal-route-campaign.schema.json"
            ):
                item.clear()
                item["type"] = "object"
                return
            for child in list(item.values()):
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return value


def validate_schema(
    value: object,
    schema: dict[str, Any],
    label: str,
    errors: list[str],
    *,
    external_profile_ref: bool = False,
) -> None:
    effective = (
        schema_without_external_profile_ref(schema) if external_profile_ref else schema
    )
    errors.extend(
        f"{label} schema violation: {message}"
        for message in v1.validate_schema_subset(value, effective, effective)
    )
    if jsonschema is not None:
        try:
            jsonschema.validate(value, effective)
        except Exception as exc:
            errors.append(f"{label} schema violation: {exc}")


def unique_index(
    values: object, key: str, label: str, errors: list[str]
) -> dict[str, dict[str, Any]]:
    return v1.unique_index(values, key, label, errors)


def validate_artifacts(
    pack: Path,
    campaign: dict[str, Any],
    errors: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Path]]:
    artifacts = unique_index(campaign.get("artifacts"), "id", "artifact", errors)
    files: dict[str, Path] = {}
    seen_paths: set[str] = set()
    artifact_root = campaign.get("artifact_root")
    for identifier, reference in artifacts.items():
        relative = reference.get("path")
        if not isinstance(relative, str) or not relative.startswith(
            f"{artifact_root}/"
        ):
            errors.append(f"artifact {identifier} is outside artifact_root")
            continue
        if relative in seen_paths:
            errors.append(f"duplicate artifact path: {relative}")
        seen_paths.add(relative)
        path = v1.safe_pack_file(pack, relative, f"artifact {identifier}", errors)
        if path is None:
            continue
        content = path.read_bytes()
        files[identifier] = path
        if not content:
            errors.append(f"artifact {identifier} is empty")
        if reference.get("sha256") != v1.digest_bytes(content):
            errors.append(f"artifact {identifier} sha256 mismatch")
        if reference.get("bytes") != len(content):
            errors.append(f"artifact {identifier} byte count mismatch")
    if isinstance(artifact_root, str):
        root = pack / artifact_root
        if root.is_symlink() or not root.is_dir():
            errors.append("artifact_root must be a real directory")
        else:
            actual_files: set[str] = set()
            for path in root.rglob("*"):
                relative = path.relative_to(pack).as_posix()
                if path.is_symlink():
                    errors.append(
                        f"symlink under artifact_root is forbidden: {relative}"
                    )
                    continue
                if path.is_file():
                    actual_files.add(relative)
            expected_files = seen_paths | {
                f"{artifact_root}/frontend-formal-route-campaign-v2.json"
            }
            extra_files = sorted(actual_files - expected_files)
            missing_files = sorted(expected_files - actual_files)
            if extra_files:
                errors.append(
                    f"unregistered files under artifact_root are forbidden: {extra_files}"
                )
            if missing_files:
                errors.append(
                    f"registered files missing under artifact_root: {missing_files}"
                )
    return artifacts, files


ENGINE_CAMPAIGN_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "proof_profile",
        "corpus_id",
        "semantic_block_ids",
        "block_symbol_map",
        "scenario_manifest",
        "mutation_campaign",
        "profile_count",
        "route_count",
        "block_count",
        "profiles",
        "routes",
        "counts",
        "block_counts",
        "source_liftings",
        "target_lowerings",
        "assumptions",
        "oracle_provenance",
        "arbitrary_customer_source",
        "unconditional_proof",
        "native_build_and_runtime",
        "independent_external_verification",
        "certification",
    }
)


def validate_engine_artifacts(
    *,
    campaign: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    used: set[str],
    errors: list[str],
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, str],
]:
    ids_value = campaign.get("engine_artifact_ids")
    if not isinstance(ids_value, list):
        errors.append("engine artifact id closure is missing")
        return {}, {}, {}
    engine_ids = [str(item) for item in ids_value]
    used.update(engine_ids)
    if len(engine_ids) != len(set(engine_ids)):
        errors.append("duplicate engine artifact ids")
    prefix = f"{campaign.get('artifact_root')}/artifacts/engine/"
    path_to_id: dict[str, str] = {}
    allowed_roles = {
        "engine-campaign-v2",
        "engine-scenario-artifact-v2",
        "scenario-manifest-v2",
        "engine-profile-artifact-v2",
        "engine-route-artifact-v2",
        "engine-mutation-artifact-v2",
        "engine-model-v2",
        "engine-behavior-v2",
        "engine-chunks-v2",
        "engine-formal-input-v2",
        "engine-smt-input-v2",
        "engine-solver-result-v2",
        "engine-vacuity-input-v2",
        "engine-vacuity-result-v2",
        "engine-block-results-v2",
        "engine-composition-v2",
        "engine-layered-result-v2",
    }
    for identifier in engine_ids:
        reference = artifacts.get(identifier, {})
        path = reference.get("path")
        role = reference.get("role")
        if (
            not isinstance(path, str)
            or not path.startswith(prefix)
            or role not in allowed_roles
        ):
            errors.append(f"engine artifact {identifier} path/role drift")
            continue
        relative = path[len(prefix) :]
        if relative in path_to_id:
            errors.append(f"duplicate engine relative artifact path: {relative}")
        path_to_id[relative] = identifier
    main_id = str(campaign.get("engine_campaign_artifact_id"))
    if main_id not in engine_ids:
        errors.append("engine campaign is outside engine artifact closure")
        return {}, {}, path_to_id
    main_path = artifact_files.get(main_id)
    if main_path is None:
        return {}, {}, path_to_id
    try:
        engine = load_json(main_path)
    except Exception as exc:
        errors.append(f"engine campaign is invalid: {exc}")
        return {}, {}, path_to_id
    if (
        set(engine) != ENGINE_CAMPAIGN_KEYS
        or engine.get("schema_version") != "1.0"
        or engine.get("kind") != "frontend-interaction-formal-route-campaign"
        or engine.get("proof_profile") != "bounded-frontend-interaction-v1"
        or engine.get("semantic_block_ids") != list(BLOCK_IDS)
        or engine.get("block_symbol_map") != BLOCK_SYMBOL_MAP
        or engine.get("profile_count") != 9
        or engine.get("route_count") != 72
        or engine.get("block_count") != 12
        or engine.get("native_build_and_runtime") != "NOT_RUN"
        or engine.get("independent_external_verification") != "NOT_RUN"
        or engine.get("certification") != "NOT_CERTIFIED"
    ):
        errors.append("engine campaign exact identity/boundary drift")
    engine_unconditional = engine.get("unconditional_proof")
    formal_proof_contract_v2(
        proof_status=(
            "PROVED" if engine_unconditional is True else "PROVED_UNDER_ASSUMPTIONS"
        ),
        unconditional_proof=engine_unconditional,
        assumptions=engine.get("assumptions"),
        label="engine campaign",
        errors=errors,
    )
    arbitrary_customer_source = engine.get("arbitrary_customer_source")
    if arbitrary_customer_source not in {"PROVED", "NOT_PROVED"} or (
        engine_unconditional is True and arbitrary_customer_source != "PROVED"
    ):
        errors.append("engine arbitrary-customer-source proof drift")

    expected_paths = {"frontend-interaction-formal-campaign.json"}
    scenario = engine.get("scenario_manifest", {})
    if isinstance(scenario, dict) and isinstance(scenario.get("source_path"), str):
        expected_paths.add(str(scenario["source_path"]))
    mutation_link = engine.get("mutation_campaign", {})
    if isinstance(mutation_link, dict) and isinstance(mutation_link.get("path"), str):
        expected_paths.add(str(mutation_link["path"]))

    engine_profiles = unique_index(
        engine.get("profiles"), "profile_id", "engine profile", errors
    )
    if set(engine_profiles) != set(PROFILE_IDS):
        errors.append("engine profile closure is not exact nine")
    for profile_id, profile in engine_profiles.items():
        for key in ("manifest_path", "source_fixture_path"):
            if isinstance(profile.get(key), str):
                expected_paths.add(str(profile[key]))
        manifest_id = path_to_id.get(str(profile.get("manifest_path")))
        manifest_path = artifact_files.get(str(manifest_id))
        if manifest_path is None:
            errors.append(f"engine profile manifest missing: {profile_id}")
            continue
        try:
            profile_manifest = load_json(manifest_path)
        except Exception as exc:
            errors.append(f"engine profile manifest invalid {profile_id}: {exc}")
            continue
        rows = profile_manifest.get("files")
        if not isinstance(rows, list):
            errors.append(f"engine profile file rows missing: {profile_id}")
            continue
        manifest_paths: set[str] = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                "path",
                "sha256",
                "byte_count",
            }:
                errors.append(f"engine profile file row drift: {profile_id}")
                continue
            relative = row.get("path")
            if not isinstance(relative, str) or relative in manifest_paths:
                errors.append(f"engine profile project path drift: {profile_id}")
                continue
            manifest_paths.add(relative)
            engine_relative = f"{profile.get('project_path')}/{relative}"
            expected_paths.add(engine_relative)
            identifier = path_to_id.get(engine_relative)
            reference = artifacts.get(str(identifier), {})
            if reference.get("sha256") != row.get("sha256") or reference.get(
                "bytes"
            ) != row.get("byte_count"):
                errors.append(
                    f"engine profile project file linkage drift: {profile_id}/{relative}"
                )
        manifest_without_digest = dict(profile_manifest)
        manifest_digest = manifest_without_digest.pop("manifest_digest", None)
        if (
            profile_manifest.get("file_count") != len(rows)
            or profile.get("manifest_digest") != manifest_digest
            or manifest_digest != v1.canonical_digest(manifest_without_digest)
        ):
            errors.append(f"engine profile manifest digest/count drift: {profile_id}")

    engine_routes = unique_index(
        engine.get("routes"), "route_id", "engine route", errors
    )
    if set(engine_routes) != exact_routes():
        errors.append("engine route closure is not exact 72")
    for route_id, route in engine_routes.items():
        route_root = f"routes/{route_id}"
        expected_paths.update(
            {
                f"{route_root}/source-model.json",
                f"{route_root}/target-model.json",
                f"{route_root}/behavior.json",
                f"{route_root}/chunks.json",
                f"{route_root}/formal-input.json",
                f"{route_root}/proof.smt2",
                f"{route_root}/solver-result.json",
                f"{route_root}/vacuity-precheck.smt2",
                f"{route_root}/vacuity-solver-result.json",
                f"{route_root}/block-results.json",
                f"{route_root}/composition.json",
                f"{route_root}/layered-result.json",
            }
        )
        declared_links = {
            "evidence_path": "evidence_digest",
            "formal_input_path": "formal_input_digest",
            "behavior_path": "behavior_digest",
            "chunks_path": "chunks_digest",
            "solver_input_path": "solver_input_digest",
            "solver_result_path": "solver_result_digest",
            "vacuity_input_path": "vacuity_input_digest",
            "vacuity_solver_result_path": "vacuity_solver_result_digest",
            "block_results_path": "block_results_digest",
            "composition_path": "composition_digest",
        }
        for path_key, digest_key in declared_links.items():
            relative = route.get(path_key)
            identifier = path_to_id.get(str(relative))
            if artifacts.get(str(identifier), {}).get("sha256") != route.get(
                digest_key
            ):
                errors.append(f"engine route {route_id} {path_key}/{digest_key} drift")
    mutation_id = path_to_id.get(str(mutation_link.get("path")))
    mutation_path = artifact_files.get(str(mutation_id))
    mutation_reference = artifacts.get(str(mutation_id), {})
    if (
        set(mutation_link) != {"path", "digest", "status"}
        or mutation_link.get("path") != "mutation-campaign.json"
        or mutation_link.get("status") != "PASSED"
        or mutation_reference.get("role") != "engine-mutation-artifact-v2"
        or mutation_link.get("digest") != mutation_reference.get("sha256")
    ):
        errors.append("engine mutation campaign declaration/digest drift")
    if mutation_path is not None:
        try:
            mutation = load_json(mutation_path)
            exact_object(
                mutation,
                {"schema_version", "kind", "proof_profile", "mutations", "status"},
                "engine mutation campaign",
                errors,
            )
            mutation_rows = mutation.get("mutations")
            if (
                mutation.get("schema_version") != "1.0"
                or mutation.get("kind")
                != "bounded-interaction-seeded-mutation-campaign"
                or mutation.get("proof_profile") != "bounded-frontend-interaction-v1"
                or mutation.get("status") != "PASSED"
                or not isinstance(mutation_rows, list)
                or [
                    row.get("block_id")
                    for row in mutation_rows
                    if isinstance(row, dict)
                ]
                != list(BLOCK_IDS)
            ):
                errors.append("engine mutation campaign identity/order drift")
                mutation_rows = []
            for row_index, row_value in enumerate(mutation_rows):
                row = exact_object(
                    row_value,
                    {
                        "block_id",
                        "obligation_symbol",
                        "pointer",
                        "scenario_id",
                        "counterexample_replay",
                        "variants",
                        "status",
                    },
                    f"engine mutation row {row_index}",
                    errors,
                )
                block_id = str(row.get("block_id"))
                variants = row.get("variants")
                if (
                    row.get("obligation_symbol")
                    != f"diff_{BLOCK_SYMBOL_MAP.get(block_id, '')}"
                    or row.get("status") != "REFUTED_AS_EXPECTED"
                    or not isinstance(row.get("pointer"), str)
                    or not isinstance(row.get("scenario_id"), str)
                    or not isinstance(row.get("counterexample_replay"), dict)
                    or not isinstance(variants, list)
                    or [
                        variant.get("variant")
                        for variant in variants
                        if isinstance(variant, dict)
                    ]
                    != list(TOOLCHAIN_MUTATION_VARIANTS)
                ):
                    errors.append(f"engine mutation row {block_id} closure drift")
                    continue
                for variant_index, variant_value in enumerate(variants):
                    variant = exact_object(
                        variant_value,
                        {
                            "variant",
                            "formal_input_path",
                            "formal_input_digest",
                            "smt2_path",
                            "smt2_digest",
                            "solver_result_path",
                            "solver_result_digest",
                            "solver_outcome",
                            "replay_status",
                        },
                        f"engine mutation {block_id} variant {variant_index}",
                        errors,
                    )
                    if (
                        variant.get("solver_outcome") != "SAT"
                        or variant.get("replay_status") != "PASSED"
                    ):
                        errors.append(
                            f"engine mutation {block_id} variant result drift"
                        )
                    for path_key, digest_key in (
                        ("formal_input_path", "formal_input_digest"),
                        ("smt2_path", "smt2_digest"),
                        ("solver_result_path", "solver_result_digest"),
                    ):
                        relative = variant.get(path_key)
                        if isinstance(relative, str):
                            expected_paths.add(relative)
                        identifier = path_to_id.get(str(relative))
                        if artifacts.get(str(identifier), {}).get(
                            "sha256"
                        ) != variant.get(digest_key):
                            errors.append(
                                f"engine mutation {block_id} {variant.get('variant')} "
                                f"{path_key}/{digest_key} drift"
                            )
        except Exception as exc:
            errors.append(f"engine mutation campaign invalid: {exc}")
    else:
        errors.append("engine mutation campaign artifact is missing")
    if set(path_to_id) != expected_paths:
        errors.append(
            "engine output artifact closure is not exact: "
            f"missing={sorted(expected_paths - set(path_to_id))} "
            f"extra={sorted(set(path_to_id) - expected_paths)}"
        )
    return engine, engine_routes, path_to_id


ENGINE_VERIFIER_RUNTIME_BASE_PATHS = frozenset(
    {
        "formal-campaign/engine-verifier/package.json",
        "formal-campaign/engine-verifier/src/frontend-interaction-formal-cli.js",
        "formal-campaign/engine-verifier/src/frontend-interaction-formal-equivalence.js",
        "formal-campaign/engine-verifier/src/bounded-interaction-source.js",
        "formal-campaign/engine-verifier/src/bounded-interaction-project.js",
        "formal-campaign/engine-verifier/src/bounded-navigation-source.js",
        "formal-campaign/engine-verifier/src/frontend-formal-equivalence.js",
        "formal-campaign/engine-verifier/src/project-generation.js",
        "formal-campaign/engine-verifier/src/project-profiles.js",
        "formal-campaign/engine-verifier/src/project-templates.js",
        "formal-campaign/engine-verifier/src/project-types.js",
        "formal-campaign/engine-verifier/node_modules/typescript/package.json",
        "formal-campaign/engine-verifier/node_modules/typescript/lib/typescript.js",
    }
)
ENGINE_VERIFIER_NODE_TYPES_PREFIX = (
    "formal-campaign/engine-verifier/node_modules/@types/node/"
)
LOCKED_ENGINE_VERIFIER_NODE_TYPES_TREE_FILE_COUNT = 67
LOCKED_ENGINE_VERIFIER_NODE_TYPES_TREE_SHA256 = (
    "sha256:b0c1c8b3aaa62dfb2f57156c9493db374c5ae99b6f9e27e3bc2344e8e5704fe3"
)
ENGINE_VERIFIER_REPOSITORY_MAP = {
    "formal-campaign/engine-verifier/package.json": (
        "engines/frontend-client-engine/package.json"
    ),
    **{
        f"formal-campaign/engine-verifier/src/{name}.js": (
            f"engines/frontend-client-engine/dist/src/{name}.js"
        )
        for name in (
            "frontend-interaction-formal-cli",
            "frontend-interaction-formal-equivalence",
            "bounded-interaction-source",
            "bounded-interaction-project",
            "bounded-navigation-source",
            "frontend-formal-equivalence",
            "project-generation",
            "project-profiles",
            "project-templates",
            "project-types",
        )
    },
}


def engine_verifier_node_types_tree(
    *,
    runtime_ids: list[str],
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    errors: list[str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for identifier in runtime_ids:
        reference = artifacts.get(identifier, {})
        runtime_path = str(reference.get("path"))
        if not runtime_path.startswith(ENGINE_VERIFIER_NODE_TYPES_PREFIX):
            continue
        relative = runtime_path.removeprefix(ENGINE_VERIFIER_NODE_TYPES_PREFIX)
        if (
            not relative
            or PurePosixPath(relative).as_posix() != relative
            or any(part in {"", ".", ".."} for part in PurePosixPath(relative).parts)
        ):
            errors.append(f"engine verifier Node types runtime path is unsafe: {runtime_path}")
            continue
        artifact_file = artifact_files.get(identifier)
        if (
            artifact_file is None
            or artifact_file.is_symlink()
            or not artifact_file.is_file()
        ):
            errors.append(f"engine verifier Node types runtime file is invalid: {runtime_path}")
            continue
        content = artifact_file.read_bytes()
        rows.append(
            {
                "path": relative,
                "sha256": v1.digest_bytes(content),
                "byte_count": len(content),
            }
        )
    rows.sort(key=lambda row: str(row["path"]))
    return {
        "file_count": len(rows),
        "digest": v1.canonical_digest(rows),
        "files": rows,
    }


def live_engine_verifier_node_types_tree(root: Path, errors: list[str]) -> dict[str, Any]:
    public_root = root / "node_modules/@types/node"
    expected_root = (
        root / "node_modules/.pnpm/@types+node@24.3.0/node_modules/@types/node"
    )
    expected_link = "../.pnpm/@types+node@24.3.0/node_modules/@types/node"
    try:
        if not public_root.is_symlink() or os.readlink(public_root) != expected_link:
            raise ValueError("public link drift")
        resolved_public = public_root.resolve(strict=True)
        resolved_expected = expected_root.resolve(strict=True)
        if resolved_public != resolved_expected:
            raise ValueError("public link target drift")
        current = root
        for part in expected_root.relative_to(root).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("pnpm root contains symlink")
        rows: list[dict[str, Any]] = []
        for path in sorted(resolved_expected.rglob("*"), key=lambda item: item.as_posix()):
            relative = path.relative_to(resolved_expected).as_posix()
            if path.is_symlink():
                raise ValueError(f"nested symlink: {relative}")
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError(f"non-regular entry: {relative}")
            content = path.read_bytes()
            rows.append(
                {
                    "path": relative,
                    "sha256": v1.digest_bytes(content),
                    "byte_count": len(content),
                }
            )
    except (OSError, RuntimeError, ValueError) as exc:
        errors.append(f"engine verifier live Node types tree invalid: {exc}")
        rows = []
    return {
        "file_count": len(rows),
        "digest": v1.canonical_digest(rows),
        "files": rows,
    }


def validate_engine_verifier_emit(
    *,
    node_realpath: Path,
    runtime_by_path: dict[str, str],
    implementation_by_repository_path: dict[str, str],
    artifact_files: dict[str, Path],
    errors: list[str],
) -> None:
    """Re-emit the frozen verifier JavaScript from the captured TypeScript.

    Direct validation additionally binds both sides to live repository bytes.
    The captured replay still performs this deterministic compiler-emitter
    comparison, so changing the verifier to a constant-success program cannot
    be hidden by only rehashing the packaged JavaScript.
    """

    typescript_path = artifact_files.get(
        str(
            runtime_by_path.get(
                "formal-campaign/engine-verifier/node_modules/typescript/lib/typescript.js"
            )
        )
    )
    pairs: list[dict[str, str]] = []
    for runtime_path, repository_path in ENGINE_VERIFIER_REPOSITORY_MAP.items():
        if not runtime_path.endswith(".js"):
            continue
        source_repository_path = repository_path.replace("/dist/src/", "/src/")
        source_repository_path = source_repository_path.removesuffix(".js") + ".ts"
        source_path = artifact_files.get(
            str(implementation_by_repository_path.get(source_repository_path))
        )
        output_path = artifact_files.get(str(runtime_by_path.get(runtime_path)))
        if source_path is None or output_path is None:
            errors.append(
                f"engine verifier compiler source/output closure missing: {runtime_path}"
            )
            continue
        pairs.append(
            {
                "source": str(source_path),
                "output": str(output_path),
                "file_name": f"src/{Path(source_repository_path).name}",
            }
        )
    if typescript_path is None or len(pairs) != 10:
        errors.append("engine verifier locked TypeScript emitter closure is incomplete")
        return
    script = """
const fs = require('fs');
const ts = require(process.argv[1]);
const pairs = JSON.parse(process.argv[2]);
const mismatches = [];
for (const pair of pairs) {
  const source = fs.readFileSync(pair.source, 'utf8');
  const emitted = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
      sourceMap: true,
    },
    fileName: pair.file_name,
  }).outputText;
  const expected = fs.readFileSync(pair.output, 'utf8');
  if (emitted !== expected) mismatches.push(pair.file_name);
}
process.stdout.write(JSON.stringify({mismatches}));
"""
    try:
        completed = subprocess.run(
            [
                str(node_realpath),
                "--input-type=commonjs",
                "-e",
                script,
                str(typescript_path),
                json.dumps(pairs, separators=(",", ":")),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        result = json.loads(completed.stdout)
        if completed.returncode != 0 or result != {"mismatches": []}:
            errors.append(
                "engine verifier compiled JavaScript does not match captured "
                f"TypeScript: returncode={completed.returncode} result={result} "
                f"stderr={completed.stderr.strip()}"
            )
    except Exception as exc:
        errors.append(f"engine verifier locked TypeScript emitter replay failed: {exc}")


def validate_engine_verifier(
    *,
    pack: Path,
    campaign: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    used: set[str],
    live_runtime_replay: bool,
    errors: list[str],
) -> None:
    declaration = campaign.get("engine_verifier")
    if not isinstance(declaration, dict):
        errors.append("engine verifier declaration is missing")
        return
    ids_value = declaration.get("runtime_artifact_ids")
    if not isinstance(ids_value, list):
        errors.append("engine verifier runtime artifact closure is missing")
        return
    runtime_ids = [str(item) for item in ids_value]
    node_id = str(declaration.get("node_identity_artifact_id"))
    used.update(runtime_ids)
    used.add(node_id)
    if declaration.get("entrypoint_artifact_id") not in runtime_ids:
        errors.append("engine verifier entrypoint is outside runtime closure")
    if v1.bundle_fingerprint(runtime_ids + [node_id], artifacts) != declaration.get(
        "fingerprint"
    ):
        errors.append("engine verifier runtime fingerprint drift")
    runtime_paths = {
        str(artifacts.get(identifier, {}).get("path")) for identifier in runtime_ids
    }
    node_types_tree = engine_verifier_node_types_tree(
        runtime_ids=runtime_ids,
        artifacts=artifacts,
        artifact_files=artifact_files,
        errors=errors,
    )
    expected_runtime_paths = ENGINE_VERIFIER_RUNTIME_BASE_PATHS | {
        ENGINE_VERIFIER_NODE_TYPES_PREFIX + str(row["path"])
        for row in node_types_tree["files"]
    }
    if (
        node_types_tree["file_count"]
        != LOCKED_ENGINE_VERIFIER_NODE_TYPES_TREE_FILE_COUNT
        or node_types_tree["digest"]
        != LOCKED_ENGINE_VERIFIER_NODE_TYPES_TREE_SHA256
    ):
        errors.append("engine verifier Node types tree identity drift")
    if runtime_paths != expected_runtime_paths:
        errors.append(
            "engine verifier runtime path closure is not exact: "
            f"missing={sorted(expected_runtime_paths - runtime_paths)} "
            f"extra={sorted(runtime_paths - expected_runtime_paths)}"
        )
    implementation = campaign.get("implementation", {})
    implementation_manifest_id = str(implementation.get("manifest_artifact_id"))
    implementation_manifest_path = artifact_files.get(implementation_manifest_id)
    implementation_by_repository_path: dict[str, str] = {}
    if implementation_manifest_path is not None:
        try:
            implementation_manifest = load_json(implementation_manifest_path)
            rows = implementation_manifest.get("files")
            if isinstance(rows, list):
                implementation_by_repository_path = {
                    str(row.get("repository_path")): str(row.get("artifact_id"))
                    for row in rows
                    if isinstance(row, dict)
                }
        except Exception as exc:
            errors.append(f"engine verifier implementation map invalid: {exc}")
    runtime_by_path = {
        str(artifacts.get(identifier, {}).get("path")): identifier
        for identifier in runtime_ids
    }
    for runtime_path, repository_path in ENGINE_VERIFIER_REPOSITORY_MAP.items():
        runtime_ref = artifacts.get(str(runtime_by_path.get(runtime_path)), {})
        implementation_ref = artifacts.get(
            str(implementation_by_repository_path.get(repository_path)), {}
        )
        if runtime_ref.get("sha256") != implementation_ref.get(
            "sha256"
        ) or runtime_ref.get("bytes") != implementation_ref.get("bytes"):
            errors.append(
                f"engine verifier runtime/live implementation mapping drift: {runtime_path}"
            )
    captured_replay = is_captured_replay(Path(__file__))
    for runtime_path, live_relative in (
        (
            "formal-campaign/engine-verifier/node_modules/typescript/package.json",
            "engines/frontend-client-engine/node_modules/typescript/package.json",
        ),
        (
            "formal-campaign/engine-verifier/node_modules/typescript/lib/typescript.js",
            "engines/frontend-client-engine/node_modules/typescript/lib/typescript.js",
        ),
    ):
        runtime_ref = artifacts.get(str(runtime_by_path.get(runtime_path)), {})
        if not captured_replay and live_runtime_replay:
            live = Path(__file__).resolve().parents[2] / live_relative
            if (
                not live.is_file()
                or live.is_symlink()
                or runtime_ref.get("sha256") != v1.digest_bytes(live.read_bytes())
                or runtime_ref.get("bytes") != len(live.read_bytes())
            ):
                errors.append(
                    f"engine verifier live TypeScript runtime drift: {runtime_path}"
                )
    if not captured_replay and live_runtime_replay:
        live_node_types_tree = live_engine_verifier_node_types_tree(
            Path(__file__).resolve().parents[2] / "engines/frontend-client-engine",
            errors,
        )
        if live_node_types_tree != node_types_tree:
            errors.append("engine verifier live Node types runtime drift")
    entry_id = str(declaration.get("entrypoint_artifact_id"))
    if artifacts.get(entry_id, {}).get("role") != "engine-verifier-entrypoint-v2":
        errors.append("engine verifier entrypoint role drift")
    for identifier in runtime_ids:
        if identifier == entry_id:
            continue
        if artifacts.get(identifier, {}).get("role") != "engine-verifier-runtime-v2":
            errors.append(f"engine verifier runtime role drift: {identifier}")

    package_ids = {
        artifacts.get(identifier, {}).get("path"): identifier
        for identifier in runtime_ids
    }
    for relative, expected in (
        (
            "formal-campaign/engine-verifier/package.json",
            ("@elmos/frontend-client-engine", "module"),
        ),
        (
            "formal-campaign/engine-verifier/node_modules/typescript/package.json",
            ("typescript", "5.9.2"),
        ),
        (
            "formal-campaign/engine-verifier/node_modules/@types/node/package.json",
            ("@types/node", "24.3.0"),
        ),
    ):
        path = artifact_files.get(str(package_ids.get(relative)))
        if path is None:
            continue
        try:
            package = load_json(path)
        except Exception as exc:
            errors.append(
                f"engine verifier package manifest invalid: {relative}: {exc}"
            )
            continue
        if relative.endswith("node_modules/typescript/package.json") or relative.endswith(
            "node_modules/@types/node/package.json"
        ):
            if (package.get("name"), package.get("version")) != expected:
                errors.append("engine verifier TypeScript runtime identity drift")
        elif package.get("name") != expected[0] or package.get("type") != expected[1]:
            errors.append("engine verifier package/module identity drift")

    node_ref = artifacts.get(node_id, {})
    node_file = artifact_files.get(node_id)
    if node_ref.get("role") != "node-environment-identity-v2" or node_file is None:
        errors.append("engine verifier Node identity artifact drift")
        return
    try:
        node = load_json(node_file)
    except Exception as exc:
        errors.append(f"engine verifier Node identity is invalid: {exc}")
        return
    node_metadata_invalid = (
        set(node)
        != {
            "schema_version",
            "kind",
            "realpath",
            "sha256",
            "bytes",
            "version",
            "platform",
            "arch",
            "portability",
        }
        or node.get("schema_version") != 2
        or node.get("kind") != "node-environment-identity-v2"
        or node.get("portability") != "PINNED_NODE_ENVIRONMENT_ASSUMPTION"
        or node.get("version") != "v26.0.0"
        or node.get("platform") != "darwin"
        or node.get("arch") != "arm64"
        or not isinstance(node.get("realpath"), str)
        or not Path(str(node.get("realpath"))).is_absolute()
        or not isinstance(node.get("bytes"), int)
        or isinstance(node.get("bytes"), bool)
        or int(node.get("bytes", 0)) <= 0
        or not isinstance(node.get("sha256"), str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", str(node.get("sha256"))) is None
    )
    node_realpath: Path | None = None
    if live_runtime_replay:
        node_command = shutil.which("node")
        node_realpath = Path(node_command).resolve() if node_command else None
        live_node_invalid = (
            node_realpath is None
            or node.get("realpath") != str(node_realpath)
            or not node_realpath.is_file()
            or node_realpath.is_symlink()
            or node.get("sha256") != v1.digest_bytes(node_realpath.read_bytes())
            or node.get("bytes") != len(node_realpath.read_bytes())
            or node.get("platform") != sys.platform
            or node.get("arch") != os.uname().machine
        )
    else:
        live_node_invalid = False
    if node_metadata_invalid or live_node_invalid:
        errors.append("engine verifier live Node identity/freshness drift")
        return
    if live_runtime_replay:
        assert node_realpath is not None
        validate_engine_verifier_emit(
            node_realpath=node_realpath,
            runtime_by_path=runtime_by_path,
            implementation_by_repository_path=implementation_by_repository_path,
            artifact_files=artifact_files,
            errors=errors,
        )
    solver_ids = [
        identifier
        for identifier, reference in artifacts.items()
        if reference.get("path") == "formal-campaign/environment/z3"
    ]
    if len(solver_ids) != 1:
        errors.append("engine verifier relocated solver closure is not exact")
        return
    solver_id = solver_ids[0]
    used.add(solver_id)
    solver_ref = artifacts[solver_id]
    solver_file = artifact_files.get(solver_id)
    if (
        solver_ref.get("role") != "solver-binary-environment"
        or solver_ref.get("sha256") != v1.LOCKED_Z3_BINARY_SHA256
        or solver_file is None
        or not solver_file.is_file()
        or solver_file.is_symlink()
        or not os.access(solver_file, os.X_OK)
    ):
        errors.append("engine verifier relocated solver identity drift")
        return
    expected_command = [
        "node",
        "formal-campaign/engine-verifier/src/frontend-interaction-formal-cli.js",
        "--proof-profile",
        "bounded-frontend-interaction-v1",
        "--verify",
        "formal-campaign/artifacts/engine",
        "--solver",
        "formal-campaign/environment/z3",
        "--json",
    ]
    if declaration.get("command") != expected_command:
        errors.append("engine verifier command is not canonical")
        return
    if declaration.get("status") != "PASSED":
        errors.append("frozen engine verifier captured status is not PASSED")
        return
    if not live_runtime_replay:
        return
    assert node_realpath is not None
    try:
        completed = subprocess.run(
            [str(node_realpath), *expected_command[1:]],
            cwd=pack,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        if (
            completed.returncode != 0
            or result
            != {
                "schema_version": "1.0",
                "kind": "frontend-interaction-formal-campaign-verification",
                "proof_profile": "bounded-frontend-interaction-v1",
                "valid": True,
                "errors": [],
            }
        ):
            errors.append(
                "frozen engine verifier replay failed: "
                f"returncode={completed.returncode} stderr={completed.stderr.strip()}"
            )
    except Exception as exc:
        errors.append(f"frozen engine verifier execution failed: {exc}")


def validate_bundle(
    *,
    name: str,
    bundle: object,
    required_paths: frozenset[str],
    manifest_role: str,
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    used: set[str],
    repo_root: Path,
    require_live: bool,
    errors: list[str],
) -> None:
    if not isinstance(bundle, dict):
        errors.append(f"{name} bundle is missing")
        return
    artifact_ids = bundle.get("artifact_ids")
    if not isinstance(artifact_ids, list):
        errors.append(f"{name} artifact ids are invalid")
        return
    ids = [str(item) for item in artifact_ids]
    used.update(ids)
    expected_fingerprint = v1.bundle_fingerprint(ids, artifacts)
    if expected_fingerprint != bundle.get("fingerprint"):
        errors.append(f"stale {name} fingerprint")
    manifest_id = str(bundle.get("manifest_artifact_id"))
    used.add(manifest_id)
    manifest_ref = artifacts.get(manifest_id, {})
    if manifest_ref.get("role") != manifest_role:
        errors.append(f"{name} manifest role mismatch")
        return
    manifest_path = artifact_files.get(manifest_id)
    if manifest_path is None:
        return
    try:
        manifest = load_json(manifest_path)
    except Exception as exc:
        errors.append(f"{name} manifest is invalid: {exc}")
        return
    if manifest.get("artifact_ids") != artifact_ids or manifest.get(
        "fingerprint"
    ) != bundle.get("fingerprint"):
        errors.append(f"{name} manifest/fingerprint linkage drift")
    rows = manifest.get("files")
    if not isinstance(rows, list):
        errors.append(f"{name} manifest files are missing")
        return
    repository_paths: set[str] = set()
    manifest_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {
            "repository_path",
            "captured_path",
            "artifact_id",
        }:
            errors.append(f"{name} manifest row {index} is invalid")
            continue
        repository_path = row.get("repository_path")
        captured_path = row.get("captured_path")
        artifact_id = row.get("artifact_id")
        if not isinstance(repository_path, str):
            errors.append(f"{name} repository path {index} is invalid")
            continue
        if repository_path in repository_paths:
            errors.append(f"{name} duplicate repository path: {repository_path}")
        repository_paths.add(repository_path)
        if not isinstance(artifact_id, str):
            errors.append(f"{name} artifact id {index} is invalid")
            continue
        manifest_ids.add(artifact_id)
        reference = artifacts.get(artifact_id, {})
        if artifact_id not in ids or reference.get("path") != captured_path:
            errors.append(f"{name} captured path drift: {repository_path}")
        if require_live:
            live = repo_root / repository_path
            if not live.is_file() or live.is_symlink():
                errors.append(f"{name} live source is unavailable: {repository_path}")
            else:
                content = live.read_bytes()
                if reference.get("sha256") != v1.digest_bytes(content) or reference.get(
                    "bytes"
                ) != len(content):
                    errors.append(
                        f"stale {name} live repository capture: {repository_path}"
                    )
    if repository_paths != required_paths:
        errors.append(
            f"{name} repository source closure is not exact: "
            f"missing={sorted(required_paths - repository_paths)} "
            f"extra={sorted(repository_paths - required_paths)}"
        )
    if manifest_ids != set(ids):
        errors.append(f"{name} manifest artifact closure drift")


def exact_object(
    value: object,
    expected_keys: frozenset[str] | set[str],
    label: str,
    errors: list[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{label} is not an object")
        return {}
    if set(value) != set(expected_keys):
        errors.append(
            f"{label} key closure drift: "
            f"missing={sorted(set(expected_keys) - set(value))} "
            f"extra={sorted(set(value) - set(expected_keys))}"
        )
    return value


def bundle_repository_files(
    bundle: object,
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
) -> dict[str, Path]:
    if not isinstance(bundle, dict):
        return {}
    manifest_path = artifact_files.get(str(bundle.get("manifest_artifact_id")))
    if manifest_path is None:
        return {}
    try:
        manifest = load_json(manifest_path)
    except Exception:
        return {}
    result: dict[str, Path] = {}
    for row in manifest.get("files", []):
        if not isinstance(row, dict):
            continue
        repository_path = row.get("repository_path")
        artifact_id = row.get("artifact_id")
        if isinstance(repository_path, str) and isinstance(artifact_id, str):
            path = artifact_files.get(artifact_id)
            if path is not None and artifact_id in artifacts:
                result[repository_path] = path
    return result


def validate_raw_solver_replay(
    value: object,
    *,
    expected_stdout: str,
    label: str,
    errors: list[str],
) -> None:
    replay = exact_object(
        value,
        {
            "argv",
            "cwd",
            "environment",
            "exit_code",
            "solver_binary_sha256",
            "solver_input_digest",
            "solver_version",
            "status",
            "stderr",
            "stdout",
        },
        label,
        errors,
    )
    argv = replay.get("argv")
    if (
        not isinstance(argv, list)
        or len(argv) != 2
        or argv[1] != "-in"
        or not isinstance(argv[0], str)
        or not Path(argv[0]).is_absolute()
        or replay.get("solver_binary_sha256")
        != "sha256:537a502af2f4013a8e887beebe525a0dae84918a61ff545991e36dfda07ed6d7"
        or replay.get("solver_version") != "Z3 version 4.16.0 - 64 bit"
        or replay.get("exit_code") != 0
        or replay.get("stdout") != expected_stdout
        or replay.get("stderr") != ""
        or replay.get("status") != "PASSED"
        or replay.get("environment") != {"LANG": "C", "LC_ALL": "C"}
        or not isinstance(replay.get("solver_input_digest"), str)
    ):
        errors.append(f"{label} locked Z3 replay drift")


def validate_runtime_execution_v2(
    value: object,
    *,
    phase: str,
    label: str,
    errors: list[str],
) -> str | None:
    if not isinstance(value, dict):
        errors.append(f"{label} is missing")
        return None
    expected_keys = {
        "schema_version",
        "kind",
        "execution_id",
        "phase",
        "tool",
        "argv",
        "cwd",
        "started_at",
        "duration_ms",
        "timeout_seconds",
        "exit_code",
        "signal",
        "status",
        "reason",
        "environment",
        "stdout",
        "stderr",
        "artifact_refs",
    }
    if set(value) != expected_keys:
        errors.append(f"{label} key closure drift")
    core = {key: item for key, item in value.items() if key != "execution_id"}
    if (
        value.get("schema_version") != "1.0"
        or value.get("kind") != "frontend-interaction-runtime-execution"
        or value.get("phase") != phase
        or value.get("status") != "PASSED"
        or value.get("exit_code") != 0
        or value.get("execution_id") != v1.canonical_digest(core)
        or not isinstance(value.get("artifact_refs"), list)
    ):
        errors.append(f"{label} identity/status drift")
    for stream_name in ("stdout", "stderr"):
        stream = value.get(stream_name)
        if not isinstance(stream, dict) or set(stream) != {
            "text",
            "byte_count",
            "sha256",
            "truncated",
        }:
            errors.append(f"{label} {stream_name} stream closure drift")
            continue
        text = stream.get("text")
        if not isinstance(text, str) or not isinstance(stream.get("byte_count"), int):
            errors.append(f"{label} {stream_name} stream identity drift")
            continue
        encoded = text.encode("utf-8")
        if stream.get("truncated") is False and (
            stream.get("byte_count") != len(encoded)
            or stream.get("sha256") != v1.digest_bytes(encoded)
        ):
            errors.append(f"{label} {stream_name} digest drift")
    return value.get("execution_id") if isinstance(value.get("execution_id"), str) else None


def validate_runtime_raw_proof_v2(
    *,
    profile_id: str,
    channel: str,
    profile_project_digest: object,
    profile_manifest_digest: object,
    engine_scenario_manifest_digest: str,
    record: dict[str, Any],
    scenario_ids: list[str],
    scenario_inputs: dict[str, dict[str, Any]],
    observations: dict[tuple[str, str], dict[str, Any]],
    block_statuses: dict[str, dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    declared_runtime_ids: set[str],
    errors: list[str],
) -> None:
    runner_kind = record.get("runner_kind")
    expected_discovery_kind = (
        "PLAYWRIGHT_RAW_RESULT"
        if runner_kind == "PLAYWRIGHT_BROWSER_INTERACTION"
        else "FLUTTER_DRIVE_RAW_RESULT"
        if runner_kind == "FLUTTER_DRIVE_SEMANTICS"
        else None
    )
    discovery = record.get("tool_discovery")
    rows = (
        [
            item
            for item in discovery
            if isinstance(item, dict)
            and item.get("kind") in {"PLAYWRIGHT_RAW_RESULT", "FLUTTER_DRIVE_RAW_RESULT"}
        ]
        if isinstance(discovery, list)
        else []
    )
    if expected_discovery_kind is None:
        if rows:
            errors.append(f"{profile_id}/{channel} unrecognized runner claims raw proof")
        return
    if (
        len(rows) != 1
        or rows[0].get("kind") != expected_discovery_kind
        or set(rows[0]) != {"kind", "path", "sha256", "byte_count"}
    ):
        errors.append(f"{profile_id}/{channel} raw proof discovery closure drift")
        return
    row = rows[0]
    packed_candidates = [
        identifier
        for identifier in declared_runtime_ids
        if artifacts.get(identifier, {}).get("role") == "runtime-raw-probe-v2"
        and str(artifacts.get(identifier, {}).get("path", "")).startswith(
            f"formal-campaign/toolchain/runtime-evidence/{profile_id}/{channel}/raw-probe/"
        )
    ]
    if len(packed_candidates) != 1:
        errors.append(f"{profile_id}/{channel} packed raw proof closure drift")
        return
    identifier = packed_candidates[0]
    reference = artifacts.get(identifier, {})
    path = artifact_files.get(identifier)
    expected_packed_path = (
        f"formal-campaign/toolchain/runtime-evidence/{profile_id}/{channel}/"
        f"raw-probe/{str(row.get('sha256', '')).removeprefix('sha256:')}.json"
    )
    if (
        path is None
        or reference.get("sha256") != row.get("sha256")
        or reference.get("bytes") != row.get("byte_count")
        or reference.get("path") != expected_packed_path
    ):
        errors.append(f"{profile_id}/{channel} packed raw proof bytes drift")
        return
    try:
        payload = load_json(path)
    except Exception as exc:
        errors.append(f"{profile_id}/{channel} packed raw proof is invalid: {exc}")
        return

    if expected_discovery_kind == "PLAYWRIGHT_RAW_RESULT":
        partial = any(
            row.get("status") == "NOT_RUN" for row in block_statuses.values()
        )
        expected_top_status = "NOT_RUN" if partial else "PASSED"
        expected_scenario_status = "PARTIAL" if partial else "PASSED"
        expected_reason = (
            "BLOCK_SPECIFIC_RUNTIME_PARTIAL_CLOSURE" if partial else None
        )
        expected_scenario_manifest_digest = v1.canonical_digest(
            [
                {"scenario_id": scenario_id, "input": scenario_inputs[scenario_id]}
                for scenario_id in scenario_ids
            ]
        )
        matrix_rows = (
            [
                item
                for item in discovery
                if isinstance(item, dict)
                and item.get("kind") == "EXACT_BROWSER_MATRIX"
            ]
            if isinstance(discovery, list)
            else []
        )
        matrix = (
            matrix_rows[0].get("browser_matrix") if len(matrix_rows) == 1 else None
        )
        runtime_tools = record.get("runtime_tools")
        tools_by_role = (
            {
                str(item.get("role")): item
                for item in runtime_tools
                if isinstance(item, dict) and isinstance(item.get("role"), str)
            }
            if isinstance(runtime_tools, list)
            else {}
        )
        if (
            set(payload)
            != {
                "schema_version",
                "kind",
                "profile_id",
                "project_digest",
                "proof_profile",
                "scenario_manifest_digest",
                "semantic_block_ids",
                "model_values_accepted_as_actual",
                "external_network",
                "status",
                "reason",
                "browser_runs",
            }
            or payload.get("schema_version") != "1.0"
            or payload.get("kind")
            != "frontend-interaction-playwright-probe-result"
            or payload.get("profile_id") != profile_id
            or payload.get("project_digest") != profile_project_digest
            or payload.get("proof_profile") != "bounded-frontend-interaction-v1"
            or payload.get("scenario_manifest_digest")
            != expected_scenario_manifest_digest
            or payload.get("semantic_block_ids") != list(BLOCK_IDS)
            or payload.get("model_values_accepted_as_actual") is not False
            or payload.get("external_network") != "BLOCKED"
            or payload.get("status") != expected_top_status
            or payload.get("reason") != expected_reason
            or not isinstance(matrix, list)
            or len(matrix) != 2
        ):
            errors.append(f"{profile_id}/{channel} Playwright raw proof identity drift")
            return
        browser_runs = payload.get("browser_runs")
        if (
            not isinstance(browser_runs, list)
            or [
                (item.get("browser_id"), item.get("engine"))
                if isinstance(item, dict)
                else None
                for item in browser_runs
            ]
            != [("google-chrome", "chromium"), ("mozilla-firefox", "firefox")]
        ):
            errors.append(f"{profile_id}/{channel} Playwright browser matrix drift")
            return
        for browser, matrix_row in zip(browser_runs, matrix):
            scenarios = browser.get("scenarios")
            engine = str(browser.get("engine"))
            browser_version = browser.get("browser_version")
            version_prefix = {
                "chromium": "Google Chrome for Testing ",
                "firefox": "Mozilla Firefox ",
            }.get(engine)
            expected_matrix_version = (
                f"{version_prefix}{browser_version}"
                if version_prefix is not None and isinstance(browser_version, str)
                else None
            )
            tool = tools_by_role.get(f"browser-{engine}")
            expected_executable = (
                {
                    "browser_id": matrix_row.get("browser_id"),
                    "engine": matrix_row.get("engine"),
                    "executable_path": tool.get("realpath"),
                    "executable_sha256": tool.get("sha256"),
                    "executable_byte_count": tool.get("byte_count"),
                }
                if isinstance(matrix_row, dict) and isinstance(tool, dict)
                else None
            )
            if (
                set(browser)
                != {
                    "browser_id", "engine", "executable", "browser_version",
                    "status", "reason", "scenario_count", "scenarios",
                }
                or browser.get("status") != expected_top_status
                or browser.get("reason") != expected_reason
                or browser.get("executable") != expected_executable
                or not isinstance(browser_version, str)
                or not browser_version
                or not isinstance(matrix_row, dict)
                or matrix_row.get("version") != expected_matrix_version
                or browser.get("scenario_count") != len(scenario_ids)
                or not isinstance(scenarios, list)
                or [
                    item.get("scenario_id") if isinstance(item, dict) else None
                    for item in scenarios
                ]
                != scenario_ids
            ):
                errors.append(f"{profile_id}/{channel} Playwright scenario closure drift")
                continue
            for scenario in scenarios:
                scenario_id = str(scenario.get("scenario_id"))
                blocks = scenario.get("block_observations")
                if (
                    set(scenario)
                    != {
                        "scenario_id", "status", "reason", "checks",
                        "runtime_metadata", "block_observations", "browser_events",
                        "network_events", "console_events", "page_errors",
                        "active_element", "aria_snapshot", "aria_error", "axe",
                        "axe_error", "raw_dom", "raw_dom_sha256", "capture_errors",
                    }
                    or scenario.get("status") != expected_scenario_status
                    or scenario.get("reason") != expected_reason
                    or not isinstance(blocks, dict)
                    or set(blocks) != set(BLOCK_IDS)
                    or not isinstance(scenario.get("raw_dom"), str)
                    or not scenario["raw_dom"]
                    or scenario.get("raw_dom_sha256")
                    != v1.digest_bytes(scenario["raw_dom"].encode("utf-8"))
                    or not isinstance(scenario.get("checks"), dict)
                    or not scenario["checks"]
                    or any(value is not True for value in scenario["checks"].values())
                    or not isinstance(scenario.get("browser_events"), list)
                    or not scenario["browser_events"]
                    or not isinstance(scenario.get("network_events"), list)
                    or not isinstance(scenario.get("console_events"), list)
                    or scenario.get("page_errors") != []
                    or scenario.get("capture_errors") != []
                    or not isinstance(scenario.get("aria_snapshot"), str)
                    or not scenario["aria_snapshot"]
                    or scenario.get("aria_error") is not None
                    or not isinstance(scenario.get("axe"), dict)
                    or scenario.get("axe_error") is not None
                    or not isinstance(scenario.get("runtime_metadata"), dict)
                    or set(scenario["runtime_metadata"])
                    != {"execution_state", "execution_sequence", "runtime_source"}
                    or scenario["runtime_metadata"].get("execution_state")
                    != ("PARTIAL" if partial else "COMPLETE")
                    or scenario["runtime_metadata"].get("runtime_source")
                    != "BLOCK_SPECIFIC_RUNTIME_OBSERVED"
                    or not isinstance(
                        scenario["runtime_metadata"].get("execution_sequence"), str
                    )
                    or not re.fullmatch(
                        r"[1-9][0-9]*",
                        scenario["runtime_metadata"]["execution_sequence"],
                    )
                ):
                    errors.append(
                        f"{profile_id}/{channel}/{scenario_id} Playwright actual trace incomplete"
                    )
                    continue
                for block_id in BLOCK_IDS:
                    block = blocks.get(block_id)
                    spec = BLOCK_OBSERVER_SPECS[block_id]
                    declared = block_statuses.get(block_id, {})
                    if (
                        not isinstance(block, dict)
                        or set(block)
                        != {
                            "status", "actual_source", "observer_kind",
                            "measurement_surface", "measurement", "measurement_digest",
                            "model_values_used_as_actual", "reason",
                        }
                        or block.get("status") != declared.get("status")
                        or block.get("observer_kind") != spec["observer_kind"]
                        or block.get("measurement_surface") != spec["measurement_surface"]
                        or block.get("model_values_used_as_actual") is not False
                    ):
                        errors.append(
                            f"{profile_id}/{channel}/{scenario_id}/{block_id} Playwright actual drift"
                        )
                        continue
                    if declared.get("status") == "NOT_RUN":
                        if (
                            block.get("actual_source") != "NOT_RUN"
                            or block.get("measurement") is not None
                            or block.get("measurement_digest") is not None
                            or block.get("reason") != declared.get("reason")
                            or (scenario_id, block_id) in observations
                        ):
                            errors.append(
                                f"{profile_id}/{channel}/{scenario_id}/{block_id} Playwright NOT_RUN drift"
                            )
                        continue
                    measurement = block.get("measurement")
                    try:
                        actual = runtime_actual_from_block_measurement(
                            block_id=block_id,
                            value=measurement,
                            label=f"raw:{profile_id}:{scenario_id}:{block_id}",
                            scenario_input=scenario_inputs.get(scenario_id),
                        )
                    except Exception as exc:
                        errors.append(
                            f"{profile_id}/{channel}/{scenario_id}/{block_id} Playwright measurement invalid: {exc}"
                        )
                        continue
                    if (
                        block.get("actual_source")
                        != "BLOCK_SPECIFIC_RUNTIME_OBSERVED"
                        or block.get("measurement_digest")
                        != v1.canonical_digest(measurement)
                        or block.get("reason") is not None
                        or actual
                        != observations.get((scenario_id, block_id), {}).get("actual")
                    ):
                        errors.append(
                            f"{profile_id}/{channel}/{scenario_id}/{block_id} Playwright actual drift"
                        )
        return

    top_keys = {
        "schema_version",
        "kind",
        "proof_profile",
        "profile_id",
        "channel",
        "project_digest",
        "profile_manifest_digest",
        "scenario_manifest_digest",
        "runtime_source",
        "model_or_precomputed_values_used",
        "scenarios",
        "summary",
    }
    journey = record.get("journey_execution")
    environment = journey.get("environment") if isinstance(journey, dict) else {}
    if (
        set(payload) != top_keys
        or payload.get("schema_version") != "1.0"
        or payload.get("kind")
        != "bounded-frontend-interaction-flutter-runtime-trace"
        or payload.get("proof_profile") != "bounded-frontend-interaction-v1"
        or payload.get("profile_id") != "flutter"
        or payload.get("channel") != channel
        or payload.get("project_digest") != profile_project_digest
        or payload.get("profile_manifest_digest") != profile_manifest_digest
        or payload.get("scenario_manifest_digest")
        != engine_scenario_manifest_digest
        or payload.get("runtime_source") != "FLUTTER_INTEGRATION_SEMANTICS"
        or payload.get("model_or_precomputed_values_used") is not False
        or not isinstance(environment, dict)
        or environment.get("ELMOS_FLUTTER_RUNTIME_CHANNEL") != channel
        or environment.get("ELMOS_FLUTTER_PROJECT_DIGEST")
        != payload.get("project_digest")
        or environment.get("ELMOS_FLUTTER_PROFILE_MANIFEST_DIGEST")
        != payload.get("profile_manifest_digest")
        or environment.get("ELMOS_FLUTTER_SCENARIO_MANIFEST_DIGEST")
        != payload.get("scenario_manifest_digest")
    ):
        errors.append(f"{profile_id}/{channel} Flutter raw proof identity/env drift")
        return
    scenarios = payload.get("scenarios")
    if (
        not isinstance(scenarios, list)
        or [
            item.get("scenario_id") if isinstance(item, dict) else None
            for item in scenarios
        ]
        != scenario_ids
    ):
        errors.append(f"{profile_id}/{channel} Flutter scenario closure drift")
        return
    prior_sequence = 0
    network_count = 0
    platform_count = 0
    native_attempt_count = 0
    scenario_keys = {
        "scenario_id",
        "execution_sequence",
        "execution_state",
        "runtime_source",
        "framework_events",
        "semantics_label",
        "focus",
        "network_adapter_events",
        "platform_adapter_events",
        "evidence_refs",
        "blocks",
    }
    for scenario in scenarios:
        scenario_id = str(scenario.get("scenario_id"))
        sequence = scenario.get("execution_sequence")
        network = scenario.get("network_adapter_events")
        platform = scenario.get("platform_adapter_events")
        blocks = scenario.get("blocks")
        evidence_refs = scenario.get("evidence_refs")
        if (
            set(scenario) != scenario_keys
            or type(sequence) is not int
            or sequence <= prior_sequence
            or scenario.get("execution_state") != "COMPLETE"
            or scenario.get("runtime_source") != "flutter-framework-events"
            or not isinstance(scenario.get("framework_events"), list)
            or not scenario["framework_events"]
            or not isinstance(scenario.get("semantics_label"), str)
            or not scenario["semantics_label"]
            or not isinstance(scenario.get("focus"), dict)
            or set(scenario["focus"]) != {"target", "query_has_focus"}
            or not isinstance(network, list)
            or not isinstance(platform, list)
            or not isinstance(evidence_refs, dict)
            or set(evidence_refs) != {"semantics", "network", "platform"}
            or evidence_refs.get("semantics") != "INLINE_INTEGRATION_BINDING"
            or not isinstance(blocks, dict)
            or set(blocks) != set(BLOCK_IDS)
        ):
            errors.append(f"{profile_id}/{channel}/{scenario_id} Flutter trace drift")
            continue
        prior_sequence = sequence
        network_count += len(network)
        platform_count += len(platform)
        if (evidence_refs.get("network") is None) != (not network) or (
            evidence_refs.get("platform") is None
        ) != (not platform):
            errors.append(f"{profile_id}/{channel}/{scenario_id} Flutter ref drift")
        for block_id in BLOCK_IDS:
            actual = blocks.get(block_id)
            if (
                not isinstance(actual, dict)
                or set(actual) != RUNTIME_ACTUAL_KEYS[block_id]
                or not external_actual_value_valid_v2(block_id, actual)
                or actual != observations.get((scenario_id, block_id), {}).get("actual")
            ):
                errors.append(
                    f"{profile_id}/{channel}/{scenario_id}/{block_id} Flutter actual drift"
                )
        if blocks.get("native-platform", {}).get("attempted") is True:
            native_attempt_count += 1
    if payload.get("summary") != {
        "scenario_count": len(scenario_ids),
        "block_count": len(BLOCK_IDS),
        "all_complete": True,
        "network_adapter_event_count": network_count,
        "platform_adapter_event_count": platform_count,
    } or network_count < 1:
        errors.append(f"{profile_id}/{channel} Flutter summary drift")
    if channel == "browser" and (platform_count != 0 or native_attempt_count != 0):
        errors.append(f"{profile_id}/{channel} Flutter browser/native projection drift")
    if channel in {"android", "ios"} and (
        platform_count < 1 or native_attempt_count < 1
    ):
        errors.append(f"{profile_id}/{channel} Flutter native adapter absent")


def validate_packed_runtime_channel_v2(
    *,
    profile_id: str,
    profile_project_digest: object,
    profile_manifest_digest: object,
    engine_scenario_manifest_digest: str,
    channel: str,
    record: dict[str, Any],
    scenario_ids: list[str],
    scenario_inputs: dict[str, dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    declared_runtime_ids: set[str],
    declared_browser_blocks: dict[str, dict[str, Any]],
    errors: list[str],
) -> dict[tuple[str, str], dict[str, Any]]:
    label = f"toolchain v2 profile {profile_id} channel {channel}"
    status = record.get("status")
    required = channel in REQUIRED_RUNTIME_CHANNELS[profile_id]
    partial_runtime = (
        required
        and channel == "browser"
        and status == "NOT_RUN"
        and record.get("reason") == "BLOCK_SPECIFIC_RUNTIME_PARTIAL_CLOSURE"
    )
    active_runtime = status == "PASSED" or partial_runtime
    expected_nonpass = "NOT_RUN" if required else "NOT_APPLICABLE"
    if (
        record.get("channel") != channel
        or record.get("required") is not required
        or status not in EVIDENCE_STATES
        or (required and status == "NOT_APPLICABLE")
        or (not required and status != "NOT_APPLICABLE")
        or record.get("model_values_used_as_actual") is not False
    ):
        errors.append(f"{label} status/applicability drift")
    blocks = record.get("semantic_blocks")
    # Runner JSON is emitted with sorted keys, so semantic closure is a set
    # property; scenario order remains independently manifest-bound.
    if not isinstance(blocks, dict) or set(blocks) != set(BLOCK_IDS):
        errors.append(f"{label} semantic block closure/order drift")
        blocks = {}
    if not active_runtime:
        if not required and status != expected_nonpass:
            errors.append(f"{label} nonapplicable status drift")
        if (
            record.get("scenario_count") != 0
            or record.get("scenarios") != []
            or record.get("raw_artifacts") != []
            or record.get("runtime_source_artifacts") != []
            or record.get("result_manifest") is not None
            or record.get("execution_policy_digest") is not None
            or record.get("runtime_tools") != []
        ):
            errors.append(f"{label} nonpassing channel exposes runtime PASS closure")
        for block_id in BLOCK_IDS:
            if blocks.get(block_id) != {
                "status": status,
                "observation_refs": [],
                "observation_digest": None,
            }:
                errors.append(f"{label} block {block_id} nonpass closure drift")
        return {}

    if (
        record.get("reason")
        != (
            "BLOCK_SPECIFIC_RUNTIME_PARTIAL_CLOSURE"
            if partial_runtime
            else None
        )
        or not isinstance(record.get("runner_kind"), str)
        or record.get("scenario_manifest_digest") != v1.canonical_digest(scenario_ids)
        or record.get("scenario_count") != len(scenario_ids)
    ):
        errors.append(f"{label} active identity/scenario manifest drift")

    passed_block_ids: list[str] = []
    not_run_block_ids: list[str] = []
    block_statuses: dict[str, dict[str, Any]] = {}
    for block_id in BLOCK_IDS:
        block = blocks.get(block_id)
        if not isinstance(block, dict) or set(block) != {
            "status",
            "reason",
            "observation_refs",
            "observation_digest",
        }:
            errors.append(f"{label} block {block_id} key closure drift")
            continue
        refs = block.get("observation_refs")
        block_status = block.get("status")
        if (
            block_status == "PASSED"
            and block.get("reason") is None
            and isinstance(refs, list)
            and len(refs) == len(scenario_ids)
            and block.get("observation_digest") == v1.canonical_digest(refs)
        ):
            passed_block_ids.append(block_id)
        elif (
            block_status == "NOT_RUN"
            and isinstance(block.get("reason"), str)
            and block["reason"]
            and refs == []
            and block.get("observation_digest") == v1.canonical_digest([])
        ):
            not_run_block_ids.append(block_id)
        else:
            errors.append(f"{label} block {block_id} active closure drift")
        block_statuses[block_id] = {
            "status": block_status,
            "reason": block.get("reason"),
        }
    if status == "PASSED" and not_run_block_ids:
        errors.append(f"{label} PASS contains NOT_RUN blocks")
    validate_observed_block_statuses(
        profile_id=profile_id,
        channel=channel,
        observed=block_statuses,
        ceiling=declared_browser_blocks,
        errors=errors,
    )
    if partial_runtime and (not passed_block_ids or not not_run_block_ids):
        errors.append(f"{label} partial closure does not contain both states")

    source_refs = record.get("runtime_source_artifacts")
    source_by_id: dict[str, dict[str, Any]] = {}
    derived_block_actuals: dict[str, dict[str, Any]] = {}
    discovery = record.get("tool_discovery")
    matrix_rows = (
        [
            row
            for row in discovery
            if isinstance(row, dict) and row.get("kind") == "EXACT_BROWSER_MATRIX"
        ]
        if isinstance(discovery, list)
        else []
    )
    expected_browser_ids = (
        [
            str(row.get("browser_id"))
            for row in matrix_rows[0].get("browser_matrix", [])
            if isinstance(row, dict)
        ]
        if channel == "browser"
        and len(matrix_rows) == 1
        and isinstance(matrix_rows[0].get("browser_matrix"), list)
        else []
    )
    if not isinstance(source_refs, list) or not source_refs:
        errors.append(f"{label} runtime source artifacts are missing")
        source_refs = []
    for index, reference in enumerate(source_refs):
        if not isinstance(reference, dict):
            errors.append(f"{label} trace {index} is invalid")
            continue
        artifact_id = str(reference.get("artifact_id"))
        is_block_trace = "block_id" in reference or "observer_kind" in reference
        expected_reference_keys = (
            {
                "artifact_id", "role", "profile_id", "channel", "scenario_id",
                "block_id", "observer_kind", "path", "sha256", "byte_count",
            }
            if is_block_trace
            else {
                "artifact_id", "role", "profile_id", "channel", "scenario_id",
                "path", "sha256", "byte_count",
            }
        )
        packed = artifacts.get(artifact_id, {})
        path = artifact_files.get(artifact_id)
        if (
            set(reference) != expected_reference_keys
            or
            artifact_id not in declared_runtime_ids
            or not str(packed.get("role", "")).startswith(
                "runtime-block-observer-trace-v2:"
                if is_block_trace
                else "runtime-trace-v2:"
            )
            or packed.get("sha256") != reference.get("sha256")
            or packed.get("bytes") != reference.get("byte_count")
            or packed.get("path")
            != (
                f"formal-campaign/toolchain/runtime-evidence/{profile_id}/{channel}/"
                f"{reference.get('path')}"
            )
            or path is None
        ):
            errors.append(f"{label} trace {artifact_id} packed binding drift")
            continue
        try:
            payload = load_json(path)
        except Exception as exc:
            errors.append(f"{label} trace {artifact_id} is invalid: {exc}")
            continue
        validate_content_addressed_runtime_json(
            reference=reference,
            path=path,
            payload=payload,
            label=f"{label} trace {artifact_id}",
            errors=errors,
        )
        common_identity_drift = (
            reference.get("artifact_id")
            != v1.canonical_digest(
                {key: item for key, item in reference.items() if key != "artifact_id"}
            )
            or payload.get("role") != reference.get("role")
            or payload.get("profile_id") != profile_id
            or payload.get("channel") != channel
            or payload.get("scenario_id") != reference.get("scenario_id")
        )
        if is_block_trace:
            block_id = str(reference.get("block_id"))
            spec = BLOCK_OBSERVER_SPECS.get(block_id, {})
            capture = payload.get("capture")
            browser_matrix = capture.get("browser_matrix") if isinstance(capture, dict) else None
            if (
                common_identity_drift
                or channel != "browser"
                or block_id not in passed_block_ids
                or reference.get("scenario_id") not in scenario_ids
                or set(payload)
                != {
                    "schema_version", "kind", "actual_source", "role", "profile_id",
                    "channel", "scenario_id", "block_id", "observer_kind", "capture",
                }
                or payload.get("schema_version") != "1.0"
                or payload.get("kind")
                != "frontend-interaction-block-observer-trace-artifact"
                or payload.get("actual_source")
                != "ALLOWLISTED_BLOCK_OBSERVER_CAPTURE"
                or payload.get("block_id") != block_id
                or payload.get("observer_kind") != spec.get("observer_kind")
                or reference.get("observer_kind") != spec.get("observer_kind")
                or payload.get("role") != spec.get("trace_role")
                or not isinstance(capture, dict)
                or set(capture)
                != {"observer_contract", "measurement_surface", "browser_matrix"}
                or capture.get("observer_contract")
                != "block-specific-runtime-observation-v1"
                or capture.get("measurement_surface") != spec.get("measurement_surface")
                or not isinstance(browser_matrix, list)
                or [
                    row.get("browser_id") if isinstance(row, dict) else None
                    for row in browser_matrix
                ]
                != expected_browser_ids
                or any(
                    not isinstance(row, dict)
                    or set(row) != {"browser_id", "measurement"}
                    for row in browser_matrix
                )
            ):
                errors.append(f"{label} block trace {artifact_id} content drift")
            else:
                try:
                    values = [
                        runtime_actual_from_block_measurement(
                            block_id=block_id,
                            value=row["measurement"],
                            label=f"{label}:{artifact_id}:{matrix_index}",
                            scenario_input=scenario_inputs.get(
                                str(reference.get("scenario_id"))
                            ),
                        )
                        for matrix_index, row in enumerate(browser_matrix)
                    ]
                except Exception as exc:
                    errors.append(f"{label} block trace {artifact_id} measurement invalid: {exc}")
                else:
                    if not values or any(value != values[0] for value in values[1:]):
                        errors.append(f"{label} block trace {artifact_id} matrix diverges")
                    else:
                        derived_block_actuals[artifact_id] = values[0]
        elif (
            common_identity_drift
            or set(payload)
            != {
                "schema_version", "kind", "actual_source", "role", "profile_id",
                "channel", "scenario_id", "capture",
            }
            or payload.get("schema_version") != "1.0"
            or payload.get("kind") != "frontend-interaction-runtime-trace-artifact"
            or payload.get("actual_source") != "ALLOWLISTED_RUNTIME_CAPTURE"
        ):
            errors.append(f"{label} trace {artifact_id} content identity drift")
        if artifact_id in source_by_id:
            errors.append(f"{label} source artifact {artifact_id} is reused")
        source_by_id[artifact_id] = reference

    raw_refs = record.get("raw_artifacts")
    observations: dict[tuple[str, str], dict[str, Any]] = {}
    observation_refs: dict[tuple[str, str], dict[str, Any]] = {}
    used_source_ids: set[str] = set()
    used_observer_ids: set[str] = set()
    if not isinstance(raw_refs, list) or len(raw_refs) != len(
        scenario_ids
    ) * len(passed_block_ids):
        errors.append(f"{label} runtime observation count drift")
        raw_refs = []
    for index, reference in enumerate(raw_refs):
        if not isinstance(reference, dict) or set(reference) != {
            "artifact_id", "role", "profile_id", "channel", "scenario_id",
            "block_id", "path", "sha256", "byte_count", "actual_digest",
        }:
            errors.append(f"{label} observation {index} is invalid")
            continue
        artifact_id = str(reference.get("artifact_id"))
        packed = artifacts.get(artifact_id, {})
        path = artifact_files.get(artifact_id)
        if (
            artifact_id not in declared_runtime_ids
            or packed.get("role") != "runtime-block-observation-v2"
            or packed.get("sha256") != reference.get("sha256")
            or packed.get("bytes") != reference.get("byte_count")
            or packed.get("path")
            != (
                f"formal-campaign/toolchain/runtime-evidence/{profile_id}/{channel}/"
                f"{reference.get('path')}"
            )
            or path is None
        ):
            errors.append(f"{label} observation {artifact_id} packed binding drift")
            continue
        try:
            payload = load_json(path)
        except Exception as exc:
            errors.append(f"{label} observation {artifact_id} invalid: {exc}")
            continue
        validate_content_addressed_runtime_json(
            reference=reference,
            path=path,
            payload=payload,
            label=f"{label} observation {artifact_id}",
            errors=errors,
        )
        scenario_id = str(reference.get("scenario_id"))
        block_id = str(reference.get("block_id"))
        actual = payload.get("actual")
        provenance = payload.get("provenance")
        key = (scenario_id, block_id)
        spec = BLOCK_OBSERVER_SPECS.get(block_id, {})
        observation_trace = (
            provenance.get("observation_trace_ref")
            if isinstance(provenance, dict)
            else None
        )
        supporting = (
            provenance.get("supporting_trace_refs")
            if isinstance(provenance, dict)
            else None
        )
        trace_id = (
            str(observation_trace.get("artifact_id"))
            if isinstance(observation_trace, dict)
            else ""
        )
        expected_support_roles = tuple(spec.get("supporting_trace_roles", ()))
        if (
            artifact_id
            != v1.canonical_digest(
                {key_name: item for key_name, item in reference.items() if key_name != "artifact_id"}
            )
            or payload.get("schema_version") != "1.0"
            or set(payload)
            != {
                "schema_version", "kind", "actual_source", "profile_id", "channel",
                "scenario_id", "block_id", "provenance", "actual",
            }
            or payload.get("kind") != "frontend-interaction-runtime-block-observation"
            or payload.get("actual_source") != "BLOCK_SPECIFIC_RUNTIME_OBSERVED"
            or payload.get("profile_id") != profile_id
            or payload.get("channel") != channel
            or payload.get("scenario_id") != scenario_id
            or payload.get("block_id") != block_id
            or scenario_id not in scenario_ids
            or block_id not in passed_block_ids
            or key in observations
            or not isinstance(actual, dict)
            or set(actual) != RUNTIME_ACTUAL_KEYS.get(block_id, set())
            or reference.get("actual_digest") != v1.canonical_digest(actual)
            or not isinstance(provenance, dict)
            or set(provenance)
            != {
                "runner_kind", "observer_contract", "observer_kind",
                "measurement_surface", "observation_trace_ref",
                "supporting_trace_refs", "model_values_used_as_actual",
            }
            or provenance.get("runner_kind") != record.get("runner_kind")
            or provenance.get("observer_contract")
            != "block-specific-runtime-observation-v1"
            or provenance.get("observer_kind") != spec.get("observer_kind")
            or provenance.get("measurement_surface") != spec.get("measurement_surface")
            or provenance.get("model_values_used_as_actual") is not False
            or not isinstance(observation_trace, dict)
            or set(observation_trace)
            != {
                "artifact_id", "role", "profile_id", "channel", "scenario_id",
                "block_id", "observer_kind", "path", "sha256", "byte_count",
            }
            or source_by_id.get(trace_id) != observation_trace
            or trace_id not in derived_block_actuals
            or observation_trace.get("role") != spec.get("trace_role")
            or observation_trace.get("profile_id") != profile_id
            or observation_trace.get("channel") != channel
            or observation_trace.get("scenario_id") != scenario_id
            or observation_trace.get("block_id") != block_id
            or observation_trace.get("observer_kind") != spec.get("observer_kind")
            or trace_id in used_observer_ids
            or not isinstance(supporting, list)
            or len(supporting) != len(expected_support_roles)
            or any(
                not isinstance(item, dict)
                or set(item)
                != {
                    "artifact_id", "role", "profile_id", "channel", "scenario_id",
                    "path", "sha256", "byte_count",
                }
                or item.get("role") != expected_role
                or source_by_id.get(str(item.get("artifact_id"))) != item
                for item, expected_role in zip(supporting, expected_support_roles)
            )
            or actual != derived_block_actuals.get(trace_id)
        ):
            errors.append(f"{label} observation {artifact_id} content/provenance drift")
        used_observer_ids.add(trace_id)
        used_source_ids.add(trace_id)
        if isinstance(supporting, list):
            used_source_ids.update(
                str(item.get("artifact_id"))
                for item in supporting
                if isinstance(item, dict)
            )
        observations[key] = {
            "artifact_id": artifact_id,
            "actual_digest": reference.get("actual_digest"),
            "actual": actual,
        }
        observation_refs[key] = reference
    expected_keys = {
        (scenario_id, block_id)
        for scenario_id in scenario_ids
        for block_id in passed_block_ids
    }
    if set(observations) != expected_keys:
        errors.append(f"{label} observation scenario/block closure drift")
    if len(used_observer_ids) != len(observations):
        errors.append(f"{label} block-specific observer trace reuse detected")
    diagnostic_ids = {
        artifact_id
        for artifact_id, reference in source_by_id.items()
        if reference.get("role") == "browser-network-trace"
    }
    diagnostic_required = (
        partial_runtime
        and block_statuses.get("api-network", {}).get("status") == "NOT_RUN"
    )
    diagnostic_complete = (
        len(diagnostic_ids) == len(scenario_ids)
        and {
            source_by_id[artifact_id].get("scenario_id")
            for artifact_id in diagnostic_ids
        }
        == set(scenario_ids)
    )
    expected_diagnostic_ids = diagnostic_ids if diagnostic_required else set()
    if (
        (diagnostic_required and not diagnostic_complete)
        or diagnostic_ids != expected_diagnostic_ids
        or used_source_ids | expected_diagnostic_ids != set(source_by_id)
        or used_source_ids & expected_diagnostic_ids
    ):
        errors.append(f"{label} runtime source artifact usage closure drift")

    scenarios = record.get("scenarios")
    if not isinstance(scenarios, list) or [
        item.get("scenario_id") for item in scenarios if isinstance(item, dict)
    ] != scenario_ids:
        errors.append(f"{label} scenario row closure/order drift")
        scenarios = []
    for scenario in scenarios:
        if not isinstance(scenario, dict) or set(scenario) != {
            "scenario_id", "status", "reason", "block_statuses",
            "block_observation_refs",
        }:
            errors.append(f"{label} scenario row key closure drift")
            continue
        scenario_id = str(scenario.get("scenario_id"))
        refs = scenario.get("block_observation_refs")
        scenario_statuses = scenario.get("block_statuses")
        if (
            scenario.get("status") != ("NOT_RUN" if not_run_block_ids else "PASSED")
            or scenario.get("reason")
            != (
                "BLOCK_SPECIFIC_RUNTIME_PARTIAL_CLOSURE"
                if not_run_block_ids
                else None
            )
            or scenario_statuses != block_statuses
            or not isinstance(refs, dict)
            or set(refs) != set(passed_block_ids)
            or any(
                refs.get(block_id) != observation_refs.get((scenario_id, block_id))
                for block_id in passed_block_ids
            )
        ):
            errors.append(f"{label} scenario {scenario_id} observation linkage drift")
    for block_id in BLOCK_IDS:
        expected_ids = [
            observations[(scenario_id, block_id)]["artifact_id"]
            for scenario_id in scenario_ids
            if (scenario_id, block_id) in observations
        ]
        if blocks.get(block_id, {}).get("observation_refs") != expected_ids:
            errors.append(f"{label} block {block_id} aggregate drift")

    build_id = validate_runtime_execution_v2(
        record.get("build_execution"), phase="BUILD", label=f"{label} BUILD", errors=errors
    )
    startup_id = validate_runtime_execution_v2(
        record.get("startup_execution"), phase="STARTUP", label=f"{label} STARTUP", errors=errors
    )
    journey_id = validate_runtime_execution_v2(
        record.get("journey_execution"), phase="JOURNEY", label=f"{label} JOURNEY", errors=errors
    )
    manifest_ref = record.get("result_manifest")
    if not isinstance(manifest_ref, dict) or set(manifest_ref) != {
        "artifact_id", "role", "profile_id", "channel", "path", "sha256",
        "byte_count", "manifest_digest",
    }:
        errors.append(f"{label} result manifest ref missing")
    else:
        manifest_id = str(manifest_ref.get("artifact_id"))
        packed = artifacts.get(manifest_id, {})
        path = artifact_files.get(manifest_id)
        if (
            manifest_id not in declared_runtime_ids
            or packed.get("role") != "runtime-result-manifest-v2"
            or packed.get("sha256") != manifest_ref.get("sha256")
            or packed.get("bytes") != manifest_ref.get("byte_count")
            or packed.get("path")
            != (
                f"formal-campaign/toolchain/runtime-evidence/{profile_id}/{channel}/"
                f"{manifest_ref.get('path')}"
            )
            or path is None
        ):
            errors.append(f"{label} result manifest packed binding drift")
        else:
            try:
                payload = load_json(path)
            except Exception as exc:
                errors.append(f"{label} result manifest invalid: {exc}")
            else:
                validate_content_addressed_runtime_json(
                    reference=manifest_ref,
                    path=path,
                    payload=payload,
                    label=f"{label} result manifest {manifest_id}",
                    errors=errors,
                )
                expected_manifest = {
                    "schema_version": "1.0",
                    "kind": "frontend-interaction-runtime-result-manifest",
                    "profile_id": profile_id,
                    "channel": channel,
                    "scenario_ids": scenario_ids,
                    "semantic_block_ids": list(BLOCK_IDS),
                    "runtime_source_artifact_ids": list(source_by_id),
                    "observation_artifact_ids": [
                        str(item.get("artifact_id")) for item in raw_refs if isinstance(item, dict)
                    ],
                    "runtime_tool_digests": [
                        item.get("sha256")
                        for item in record.get("runtime_tools", [])
                        if isinstance(item, dict)
                    ],
                    "prerequisite_execution_ids": [build_id, startup_id],
                    "runtime_source_artifact_count": len(source_by_id),
                    "observation_artifact_count": len(raw_refs),
                    "passed_block_ids": passed_block_ids,
                    "not_run_block_ids": not_run_block_ids,
                }
                if (
                    payload != expected_manifest
                    or manifest_ref.get("manifest_digest") != v1.canonical_digest(payload)
                    or manifest_id
                    != v1.canonical_digest(
                        {key: item for key, item in manifest_ref.items() if key != "artifact_id"}
                    )
                ):
                    errors.append(f"{label} result manifest content drift")
                journey = record.get("journey_execution", {})
                expected_journey_ids = [
                    *list(source_by_id),
                    *[str(item.get("artifact_id")) for item in raw_refs if isinstance(item, dict)],
                    manifest_id,
                ]
                if journey.get("artifact_refs") != expected_journey_ids:
                    errors.append(f"{label} journey artifact closure drift")

    policy_candidates: list[tuple[str, dict[str, Any]]] = []
    for identifier in declared_runtime_ids:
        if artifacts.get(identifier, {}).get("role") != "runtime-execution-policy-v2":
            continue
        path = artifact_files.get(identifier)
        if path is None:
            continue
        try:
            policy = load_json(path)
        except Exception:
            continue
        if policy.get("profile_id") == profile_id and policy.get("channel") == channel:
            policy_candidates.append((identifier, policy))
    if len(policy_candidates) != 1:
        errors.append(f"{label} execution policy packed closure drift")
    else:
        policy_id, policy = policy_candidates[0]
        policy_path = artifact_files.get(policy_id)
        policy_rows = [
            row
            for row in (
                record.get("tool_discovery")
                if isinstance(record.get("tool_discovery"), list)
                else []
            )
            if isinstance(row, dict)
            and row.get("kind") == "RUNTIME_EXECUTION_POLICY_ARTIFACT"
        ]
        policy_row = policy_rows[0] if len(policy_rows) == 1 else {}
        expected_phases = {
            phase: {
                "phase": execution.get("phase"),
                "tool": execution.get("tool"),
                "argv": execution.get("argv"),
                "cwd": execution.get("cwd"),
                "environment": execution.get("environment"),
            }
            for phase, execution in (
                ("BUILD", record.get("build_execution", {})),
                ("STARTUP", record.get("startup_execution", {})),
                ("JOURNEY", record.get("journey_execution", {})),
            )
        }
        if (
            set(policy_row)
            != {"kind", "path", "sha256", "byte_count", "policy_digest"}
            or policy_path is None
            or artifacts.get(policy_id, {}).get("sha256")
            != policy_row.get("sha256")
            or artifacts.get(policy_id, {}).get("bytes")
            != policy_row.get("byte_count")
            or artifacts.get(policy_id, {}).get("path")
            != (
                f"formal-campaign/toolchain/runtime-evidence/{profile_id}/{channel}/"
                f"{policy_row.get('path')}"
            )
        ):
            errors.append(f"{label} execution policy discovery/binding drift")
        elif policy_path is not None:
            validate_content_addressed_runtime_json(
                reference=policy_row,
                path=policy_path,
                payload=policy,
                label=f"{label} execution policy",
                errors=errors,
            )
        if (
            set(policy)
            != {
                "schema_version",
                "kind",
                "profile_id",
                "channel",
                "runner_kind",
                "phases",
                "runtime_tools",
            }
            or policy.get("schema_version") != "1.0"
            or policy.get("kind") != "frontend-interaction-runtime-execution-policy"
            or policy.get("profile_id") != profile_id
            or policy.get("channel") != channel
            or policy.get("runner_kind") != record.get("runner_kind")
            or record.get("execution_policy_digest") != v1.canonical_digest(policy)
            or policy_row.get("policy_digest") != v1.canonical_digest(policy)
            or policy.get("phases") != expected_phases
            or policy.get("runtime_tools") != record.get("runtime_tools")
        ):
            errors.append(f"{label} execution policy content drift")
    validate_runtime_raw_proof_v2(
        profile_id=profile_id,
        channel=channel,
        profile_project_digest=profile_project_digest,
        profile_manifest_digest=profile_manifest_digest,
        engine_scenario_manifest_digest=engine_scenario_manifest_digest,
        record=record,
        scenario_ids=scenario_ids,
        scenario_inputs=scenario_inputs,
        observations=observations,
        block_statuses=block_statuses,
        artifacts=artifacts,
        artifact_files=artifact_files,
        declared_runtime_ids=declared_runtime_ids,
        errors=errors,
    )
    del journey_id
    return observations


def validate_toolchain_evidence_v2(
    *,
    raw_path: Path | None,
    engine_campaign_path: Path | None,
    campaign: dict[str, Any],
    profile_records: dict[str, dict[str, Any]],
    scenario_ids: list[str],
    scenario_inputs: dict[str, dict[str, Any]],
    scenario_digest: str,
    implementation: object,
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    errors: list[str],
) -> None:
    """Reconstruct the final raw runner output instead of trusting its summary.

    Block-specific observations may preserve partial runtime evidence, but each
    PASS still requires every referenced DOM/event/a11y/network/device byte.
    Missing channel or block closure stays NOT_RUN rather than being promoted
    from a model, build, or producer summary.
    """

    if raw_path is None or engine_campaign_path is None:
        errors.append("toolchain v2 raw evidence closure is missing")
        return
    try:
        raw = load_json(raw_path)
        engine_payload = load_json(engine_campaign_path)
    except Exception as exc:
        errors.append(f"toolchain v2 raw evidence is invalid: {exc}")
        return
    declaration = exact_object(
        campaign.get("toolchain_evidence"),
        {
            "provided",
            "status",
            "artifact_id",
            "artifact_sha256",
            "artifact_bytes",
            "engine_campaign_sha256",
            "producer_fingerprint",
            "scenario_manifest_sha256",
            "profile_binding_count",
            "route_binding_count",
            "block_binding_count",
            "runtime_status",
            "runtime_artifact_ids",
            "runtime_artifact_count",
            "profile_channel_statuses",
            "boundaries",
        },
        "toolchain v2 campaign declaration",
        errors,
    )
    exact_object(raw, TOOLCHAIN_TOP_KEYS, "toolchain v2 raw evidence", errors)
    if (
        raw.get("schema_version") != "1.0"
        or raw.get("kind") != "frontend-interaction-toolchain-evidence"
        or raw.get("semantic_block_ids") != list(BLOCK_IDS)
        or raw.get("scenario_manifest_digest") != scenario_digest
    ):
        errors.append("toolchain v2 raw contract identity drift")

    captured = bundle_repository_files(implementation, artifacts, artifact_files)
    producer_file = captured.get("tooling/run_frontend_formal_toolchains.py")
    producer = exact_object(
        raw.get("producer"),
        {"path", "sha256", "byte_count"},
        "toolchain v2 producer",
        errors,
    )
    if producer_file is None:
        errors.append("toolchain v2 producer is absent from implementation closure")
    else:
        producer_bytes = producer_file.read_bytes()
        if producer.get("sha256") != v1.digest_bytes(producer_bytes) or producer.get(
            "byte_count"
        ) != len(producer_bytes):
            errors.append("toolchain v2 producer capture is stale or tampered")

    engine_bytes = engine_campaign_path.read_bytes()
    raw_campaign = exact_object(
        raw.get("campaign"),
        {
            "path",
            "sha256",
            "byte_count",
            "proof_profile",
            "profile_count",
            "route_count",
        },
        "toolchain v2 campaign binding",
        errors,
    )
    if (
        raw_campaign.get("sha256") != v1.digest_bytes(engine_bytes)
        or raw_campaign.get("byte_count") != len(engine_bytes)
        or raw_campaign.get("proof_profile") != "bounded-frontend-interaction-v1"
        or raw_campaign.get("profile_count") != 9
        or raw_campaign.get("route_count") != 72
    ):
        errors.append("toolchain v2 raw engine campaign binding drift")
    if (
        declaration.get("provided") is not True
        or declaration.get("engine_campaign_sha256") != v1.digest_bytes(engine_bytes)
        or declaration.get("producer_fingerprint") != producer.get("sha256")
    ):
        errors.append("toolchain v2 campaign declaration/raw binding drift")
    engine_routes = {
        str(item.get("route_id")): item
        for item in engine_payload.get("routes", [])
        if isinstance(item, dict)
    }
    if set(engine_routes) != exact_routes():
        errors.append("toolchain v2 raw engine route closure drift")

    engine_mutation_variants: dict[tuple[str, str], dict[str, Any]] = {}
    mutation_link = exact_object(
        engine_payload.get("mutation_campaign"),
        {"path", "digest", "status"},
        "toolchain v2 engine mutation link",
        errors,
    )
    mutation_relative = mutation_link.get("path")
    if not isinstance(mutation_relative, str) or not mutation_relative:
        errors.append("toolchain v2 engine mutation path is missing")
    else:
        engine_root = engine_campaign_path.parent.resolve()
        mutation_path = (engine_root / mutation_relative).resolve()
        try:
            mutation_path.relative_to(engine_root)
        except ValueError:
            errors.append("toolchain v2 engine mutation path escapes campaign root")
        else:
            try:
                if mutation_path.is_symlink() or not mutation_path.is_file():
                    raise ValueError("not a regular file")
                mutation_bytes = mutation_path.read_bytes()
                mutation_payload = json.loads(mutation_bytes)
            except Exception as exc:
                errors.append(
                    f"toolchain v2 engine mutation artifact is invalid: {exc}"
                )
            else:
                if (
                    mutation_link.get("digest") != v1.digest_bytes(mutation_bytes)
                    or mutation_link.get("status") != "PASSED"
                    or not isinstance(mutation_payload, dict)
                    or mutation_payload.get("status") != "PASSED"
                ):
                    errors.append("toolchain v2 engine mutation artifact binding drift")
                mutation_rows = mutation_payload.get("mutations", [])
                if not isinstance(mutation_rows, list) or len(mutation_rows) != 12:
                    errors.append(
                        "toolchain v2 engine mutation block closure is not exact 12"
                    )
                    mutation_rows = []
                for mutation_index, mutation_row in enumerate(mutation_rows):
                    if not isinstance(mutation_row, dict):
                        errors.append(
                            f"toolchain v2 engine mutation row {mutation_index} is invalid"
                        )
                        continue
                    block_id = mutation_row.get("block_id")
                    variants = mutation_row.get("variants")
                    if block_id not in BLOCK_IDS or not isinstance(variants, list):
                        errors.append(
                            f"toolchain v2 engine mutation row {mutation_index} identity drift"
                        )
                        continue
                    if len(variants) != len(TOOLCHAIN_MUTATION_VARIANTS):
                        errors.append(
                            f"toolchain v2 engine mutation row {mutation_index} variant closure drift"
                        )
                    for variant_value in variants:
                        if not isinstance(variant_value, dict):
                            errors.append(
                                f"toolchain v2 engine mutation row {mutation_index} variant is invalid"
                            )
                            continue
                        variant = variant_value.get("variant")
                        identity = (str(block_id), str(variant))
                        if (
                            variant not in TOOLCHAIN_MUTATION_VARIANTS
                            or identity in engine_mutation_variants
                        ):
                            errors.append(
                                f"toolchain v2 engine mutation row {mutation_index} variant identity drift"
                            )
                            continue
                        engine_mutation_variants[identity] = variant_value
                expected_engine_mutations = {
                    (block_id, variant)
                    for block_id in BLOCK_IDS
                    for variant in TOOLCHAIN_MUTATION_VARIANTS
                }
                if set(engine_mutation_variants) != expected_engine_mutations:
                    errors.append("toolchain v2 engine mutation variant closure drift")

    scenario_policy = exact_object(
        raw.get("scenario_policy"),
        {"version", "source_sha256", "source_byte_count", "scenario_ids"},
        "toolchain v2 scenario policy",
        errors,
    )
    if (
        scenario_policy.get("version") != "bounded-frontend-interaction-scenarios-v1"
        or scenario_policy.get("source_sha256") != scenario_digest
        or scenario_policy.get("scenario_ids") != scenario_ids
        or scenario_policy.get("source_byte_count")
        != artifacts.get(
            str(campaign.get("scenario_manifest", {}).get("artifact_id")), {}
        ).get("bytes")
    ):
        errors.append("toolchain v2 independently locked scenario policy drift")

    policy = exact_object(
        raw.get("policy"),
        TOOLCHAIN_POLICY_KEYS,
        "toolchain v2 execution policy",
        errors,
    )
    selected_profiles_value = policy.get("selected_profiles")
    selected_profile_ids = (
        set(selected_profiles_value)
        if isinstance(selected_profiles_value, list)
        and all(isinstance(item, str) for item in selected_profiles_value)
        else set()
    )
    selected_profiles_valid = (
        isinstance(selected_profiles_value, list)
        and bool(selected_profiles_value)
        and len(selected_profile_ids) == len(selected_profiles_value)
        and selected_profile_ids.issubset(PROFILE_IDS)
        and selected_profiles_value
        == [profile_id for profile_id in PROFILE_IDS if profile_id in selected_profile_ids]
    )
    if (
        not isinstance(policy.get("no_network"), bool)
        or not isinstance(policy.get("timeout_seconds"), int)
        or not 1 <= policy.get("timeout_seconds", 0) <= 3600
        or not isinstance(policy.get("network_timeout_seconds"), int)
        or not 0 <= policy.get("network_timeout_seconds", -1) <= 3600
        or not selected_profiles_valid
        or not isinstance(policy.get("fail_on_unavailable"), bool)
        or any(
            policy.get(key) is not None and not isinstance(policy.get(key), str)
            for key in (
                "chrome_path",
                "firefox_path",
                "android_device_id",
                "ios_simulator_udid",
                "harmony_device_id",
            )
        )
        or any(
            isinstance(policy.get(key), str)
            and not Path(str(policy.get(key))).is_absolute()
            for key in ("chrome_path", "firefox_path", "harmony_sdk_root")
        )
        or not isinstance(policy.get("harmony_sdk_root"), str)
        or not policy.get("harmony_sdk_root")
        or policy.get("profile_build_deduplication") != "project-content-digest"
        or policy.get("workspace_retention")
        != "PER_PROFILE_TEMPORARY_RECLAIMED_AFTER_EVIDENCE_CAPTURE"
    ):
        errors.append("toolchain v2 execution policy drift")

    closure = exact_object(
        raw.get("implementation_closure"),
        {
            "schema_version",
            "kind",
            "node_module_loading",
            "identities",
            "closure_digest",
        },
        "toolchain v2 browser implementation closure",
        errors,
    )
    identities = exact_object(
        closure.get("identities"),
        {
            "helper",
            "workspace_lock",
            "workspace_package",
            "playwright_package",
            "axe_package",
        },
        "toolchain v2 browser implementation identities",
        errors,
    )
    if (
        closure.get("schema_version") != "1.0"
        or closure.get("kind") != "frontend-interaction-browser-implementation-closure"
        or closure.get("node_module_loading") != "EXACT_ABSOLUTE_REPOSITORY_PATH"
        or closure.get("closure_digest") != v1.canonical_digest(identities)
    ):
        errors.append("toolchain v2 browser implementation fingerprint drift")
    captured_identity_paths = {
        "helper": "tooling/frontend_formal_playwright_probe.cjs",
        "workspace_lock": "apps/web-console/pnpm-lock.yaml",
        "workspace_package": "apps/web-console/package.json",
    }
    pinned_external_packages = {
        "playwright_package": (
            "sha256:9d8556509e073169efec663b7f71c13f17d7002b307d00d48bf88ee91c387f3e",
            754,
        ),
        "axe_package": (
            "sha256:c3e69bcde1800e1e748023ce6ed68018b1ce48714160441b7ffb7e1a6f2bd2a2",
            2217,
        ),
    }
    for name, identity_value in identities.items():
        identity = exact_object(
            identity_value,
            {"path", "realpath", "sha256", "byte_count"},
            f"toolchain v2 {name} identity",
            errors,
        )
        if (
            not isinstance(identity.get("path"), str)
            or not Path(str(identity.get("path"))).is_absolute()
            or not isinstance(identity.get("realpath"), str)
            or not Path(str(identity.get("realpath"))).is_absolute()
            or not isinstance(identity.get("sha256"), str)
            or not isinstance(identity.get("byte_count"), int)
            or identity.get("byte_count", 0) < 1
        ):
            errors.append(f"toolchain v2 {name} identity is malformed")
        repository_path = captured_identity_paths.get(name)
        if repository_path is not None:
            captured_file = captured.get(repository_path)
            if captured_file is None:
                errors.append(
                    f"toolchain v2 {name} is absent from implementation closure"
                )
            else:
                content = captured_file.read_bytes()
                if identity.get("sha256") != v1.digest_bytes(content) or identity.get(
                    "byte_count"
                ) != len(content):
                    errors.append(f"toolchain v2 {name} capture drift")
        pinned_external = pinned_external_packages.get(name)
        if (
            pinned_external is not None
            and (identity.get("sha256"), identity.get("byte_count")) != pinned_external
        ):
            errors.append(f"toolchain v2 {name} pinned package identity drift")

    preverification = raw.get("engine_preverification")
    if not isinstance(preverification, dict):
        errors.append("toolchain v2 engine preverification is missing")
    else:
        preverification_core = dict(preverification)
        evidence_digest = preverification_core.pop("evidence_digest", None)
        result = preverification.get("result")
        if (
            evidence_digest != v1.canonical_digest(preverification_core)
            or preverification.get("status") != "PASSED"
            or result
            != {
                "schema_version": "1.0",
                "kind": "frontend-interaction-formal-campaign-verification",
                "proof_profile": "bounded-frontend-interaction-v1",
                "valid": True,
                "errors": [],
            }
        ):
            errors.append("toolchain v2 engine preverification receipt drift")
        preverify_implementation = exact_object(
            preverification.get("implementation_identity"),
            {
                "schema_version",
                "kind",
                "node",
                "source_tree",
                "dist_tree",
                "node_types_tree",
                "files",
                "typescript_version",
                "node_types_version",
                "closure_digest",
            },
            "toolchain v2 engine preverification implementation",
            errors,
        )
        implementation_core = dict(preverify_implementation)
        implementation_digest = implementation_core.pop("closure_digest", None)
        if (
            preverify_implementation.get("schema_version") != "1.0"
            or preverify_implementation.get("kind")
            != "frontend-interaction-engine-implementation-identity"
            or preverify_implementation.get("typescript_version") != "5.9.2"
            or preverify_implementation.get("node_types_version") != "24.3.0"
            or implementation_digest != v1.canonical_digest(implementation_core)
        ):
            errors.append(
                "toolchain v2 engine preverification implementation fingerprint drift"
            )
        node_types_tree = exact_object(
            preverify_implementation.get("node_types_tree"),
            {"root", "file_count", "digest", "files"},
            "toolchain v2 engine preverification Node types tree",
            errors,
        )
        packed_node_types_tree = engine_verifier_node_types_tree(
            runtime_ids=[
                str(item)
                for item in campaign.get("engine_verifier", {}).get(
                    "runtime_artifact_ids", []
                )
            ],
            artifacts=artifacts,
            artifact_files=artifact_files,
            errors=errors,
        )
        if (
            node_types_tree.get("file_count")
            != LOCKED_ENGINE_VERIFIER_NODE_TYPES_TREE_FILE_COUNT
            or node_types_tree.get("digest")
            != LOCKED_ENGINE_VERIFIER_NODE_TYPES_TREE_SHA256
            or node_types_tree.get("files") != packed_node_types_tree.get("files")
            or node_types_tree.get("file_count")
            != packed_node_types_tree.get("file_count")
            or node_types_tree.get("digest") != packed_node_types_tree.get("digest")
            or not str(node_types_tree.get("root", "")).endswith(
                "/node_modules/.pnpm/@types+node@24.3.0/node_modules/@types/node"
            )
        ):
            errors.append(
                "toolchain v2 engine preverification Node types tree capture drift"
            )
        preverify_files = exact_object(
            preverify_implementation.get("files"),
            {
                "cli_source",
                "equivalence_source",
                "cli_dist",
                "equivalence_dist",
                "package",
                "tsconfig",
                "lock",
                "typescript_package",
                "node_types_package",
            },
            "toolchain v2 engine preverification files",
            errors,
        )
        implementation_file_map = {
            "cli_source": "engines/frontend-client-engine/src/frontend-interaction-formal-cli.ts",
            "equivalence_source": "engines/frontend-client-engine/src/frontend-interaction-formal-equivalence.ts",
            "cli_dist": "engines/frontend-client-engine/dist/src/frontend-interaction-formal-cli.js",
            "equivalence_dist": "engines/frontend-client-engine/dist/src/frontend-interaction-formal-equivalence.js",
            "package": "engines/frontend-client-engine/package.json",
            "tsconfig": "engines/frontend-client-engine/tsconfig.json",
            "lock": "engines/frontend-client-engine/pnpm-lock.yaml",
        }
        for name, repository_path in implementation_file_map.items():
            identity = exact_object(
                preverify_files.get(name),
                {"path", "realpath", "sha256", "byte_count"},
                f"toolchain v2 engine preverification {name}",
                errors,
            )
            captured_file = captured.get(repository_path)
            if captured_file is None:
                errors.append(
                    f"toolchain v2 engine preverification {name} capture is missing"
                )
            else:
                content = captured_file.read_bytes()
                if identity.get("sha256") != v1.digest_bytes(content) or identity.get(
                    "byte_count"
                ) != len(content):
                    errors.append(
                        f"toolchain v2 engine preverification {name} capture drift"
                    )
        typescript_file_ids = [
            identifier
            for identifier, reference in artifacts.items()
            if reference.get("path")
            == "formal-campaign/engine-verifier/node_modules/typescript/package.json"
        ]
        typescript_identity = exact_object(
            preverify_files.get("typescript_package"),
            {"path", "realpath", "sha256", "byte_count"},
            "toolchain v2 engine preverification TypeScript package",
            errors,
        )
        if len(typescript_file_ids) != 1:
            errors.append(
                "toolchain v2 engine preverification TypeScript capture is missing"
            )
        else:
            typescript_file = artifact_files.get(typescript_file_ids[0])
            if typescript_file is None:
                errors.append(
                    "toolchain v2 engine preverification TypeScript capture is missing"
                )
            else:
                content = typescript_file.read_bytes()
                if typescript_identity.get("sha256") != v1.digest_bytes(
                    content
                ) or typescript_identity.get("byte_count") != len(content):
                    errors.append(
                        "toolchain v2 engine preverification TypeScript capture drift"
                    )
        node_types_file_ids = [
            identifier
            for identifier, reference in artifacts.items()
            if reference.get("path")
            == "formal-campaign/engine-verifier/node_modules/@types/node/package.json"
        ]
        node_types_identity = exact_object(
            preverify_files.get("node_types_package"),
            {"path", "realpath", "sha256", "byte_count"},
            "toolchain v2 engine preverification Node types package",
            errors,
        )
        if len(node_types_file_ids) != 1:
            errors.append(
                "toolchain v2 engine preverification Node types capture is missing"
            )
        else:
            node_types_file = artifact_files.get(node_types_file_ids[0])
            if node_types_file is None:
                errors.append(
                    "toolchain v2 engine preverification Node types capture is missing"
                )
            else:
                content = node_types_file.read_bytes()
                if node_types_identity.get("sha256") != v1.digest_bytes(
                    content
                ) or node_types_identity.get("byte_count") != len(content):
                    errors.append(
                        "toolchain v2 engine preverification Node types capture drift"
                    )
        node_identity = exact_object(
            preverify_implementation.get("node"),
            {"path", "realpath", "sha256", "byte_count", "version"},
            "toolchain v2 engine preverification Node",
            errors,
        )
        packed_node_path = artifact_files.get(
            str(campaign.get("engine_verifier", {}).get("node_identity_artifact_id"))
        )
        if packed_node_path is None:
            errors.append("toolchain v2 packed Node identity is missing")
        else:
            try:
                packed_node = load_json(packed_node_path)
            except Exception as exc:
                errors.append(f"toolchain v2 packed Node identity is invalid: {exc}")
            else:
                if (
                    node_identity.get("sha256") != packed_node.get("sha256")
                    or node_identity.get("byte_count") != packed_node.get("bytes")
                    or node_identity.get("version") != packed_node.get("version")
                ):
                    errors.append(
                        "toolchain v2 engine preverification Node capture drift"
                    )

    mutations = raw.get("mutation_replay")
    expected_mutations = {
        (block_id, variant)
        for block_id in BLOCK_IDS
        for variant in TOOLCHAIN_MUTATION_VARIANTS
    }
    actual_mutations: set[tuple[object, object]] = set()
    if not isinstance(mutations, list) or len(mutations) != 36:
        errors.append("toolchain v2 mutation replay closure is not exact 36")
        mutations = []
    mutation_keys = {
        "block_id",
        "variant",
        "canonical_model_digest",
        "mutant_model_digest",
        "canonical_block_digest",
        "mutant_block_digest",
        "formal_input_digest",
        "solver_result_digest",
        "outcome",
        "proof_status",
        "runner_replay",
    }
    for index, mutation_value in enumerate(mutations):
        mutation = exact_object(
            mutation_value,
            mutation_keys,
            f"toolchain v2 mutation replay {index}",
            errors,
        )
        identity = (mutation.get("block_id"), mutation.get("variant"))
        if identity in actual_mutations:
            errors.append(f"toolchain v2 mutation replay {index} is duplicated")
        actual_mutations.add(identity)
        if (
            mutation.get("canonical_model_digest")
            == mutation.get("mutant_model_digest")
            or mutation.get("canonical_block_digest")
            == mutation.get("mutant_block_digest")
            or mutation.get("outcome") != "SAT"
            or mutation.get("proof_status") != "REFUTED"
        ):
            errors.append(f"toolchain v2 mutation replay {index} is vacuous")
        expected_variant = engine_mutation_variants.get(
            (str(mutation.get("block_id")), str(mutation.get("variant")))
        )
        replay_value = mutation.get("runner_replay")
        replay_solver_digest = (
            replay_value.get("solver_input_digest")
            if isinstance(replay_value, dict)
            else None
        )
        if (
            expected_variant is None
            or mutation.get("formal_input_digest")
            != expected_variant.get("formal_input_digest")
            or replay_solver_digest != expected_variant.get("smt2_digest")
            or mutation.get("solver_result_digest")
            != expected_variant.get("solver_result_digest")
        ):
            errors.append(
                f"toolchain v2 mutation replay {index} engine digest binding drift"
            )
        validate_raw_solver_replay(
            mutation.get("runner_replay"),
            expected_stdout="sat\n",
            label=f"toolchain v2 mutation replay {index}",
            errors=errors,
        )
    if actual_mutations != expected_mutations:
        errors.append("toolchain v2 mutation replay identity closure drift")

    declared_runtime_values = declaration.get("runtime_artifact_ids")
    declared_runtime_ids = (
        set(str(item) for item in declared_runtime_values)
        if isinstance(declared_runtime_values, list)
        else set()
    )
    if (
        not isinstance(declared_runtime_values, list)
        or len(declared_runtime_ids) != len(declared_runtime_values)
        or declaration.get("runtime_artifact_count") != len(declared_runtime_ids)
        or any(identifier not in artifacts for identifier in declared_runtime_ids)
    ):
        errors.append("toolchain v2 declared runtime artifact closure drift")

    profiles = raw.get("profile_executions")
    if not isinstance(profiles, list):
        errors.append("toolchain v2 profile executions are missing")
        profiles = []
    raw_profiles: dict[str, dict[str, Any]] = {}
    raw_runtime_observations: dict[
        tuple[str, str], dict[tuple[str, str], dict[str, Any]]
    ] = {}
    reconstructed_channel_statuses: dict[str, dict[str, str]] = {}
    reconstructed_channel_contracts: dict[str, dict[str, dict[str, Any]]] = {}
    if [item.get("profile_id") for item in profiles if isinstance(item, dict)] != list(
        PROFILE_IDS
    ):
        errors.append("toolchain v2 profile execution order/closure drift")
    for index, profile_value in enumerate(profiles):
        candidate_profile_id = (
            profile_value.get("profile_id")
            if isinstance(profile_value, dict)
            else None
        )
        profile_selected = candidate_profile_id in selected_profile_ids
        profile = exact_object(
            profile_value,
            (
                TOOLCHAIN_PROFILE_KEYS
                if profile_selected
                else TOOLCHAIN_PROFILE_KEYS - {"tool_discovery"}
            ),
            f"toolchain v2 profile execution {index}",
            errors,
        )
        profile_id = profile.get("profile_id")
        if profile_id not in PROFILE_IDS or profile_id in raw_profiles:
            errors.append(f"toolchain v2 profile execution {index} identity drift")
            continue
        profile_id = str(profile_id)
        raw_profiles[profile_id] = profile
        expected_profile = profile_records.get(profile_id, {})
        if profile_selected:
            expected_execution_id = v1.canonical_digest(
                {
                    key: value
                    for key, value in profile.items()
                    if key not in {"execution_id", "replay_profile_args"}
                }
            )
        else:
            expected_execution_id = v1.canonical_digest(
                {
                    "producer_digest": producer.get("sha256"),
                    "profile_id": profile_id,
                    "project_digest": profile.get("project_digest"),
                    "status": "NOT_RUN",
                }
            )
        if (
            profile.get("execution_id") != expected_execution_id
            or profile.get("producer") != producer
            or profile.get("project_digest") != expected_profile.get("project_digest")
            or profile.get("required_runtime_channels")
            != list(REQUIRED_RUNTIME_CHANNELS[profile_id])
            or profile.get("status") not in {"PASSED", "FAILED", "NOT_RUN"}
            or profile.get("target_build") not in {"PASSED", "FAILED", "NOT_RUN"}
        ):
            errors.append(f"toolchain v2 profile {profile_id} identity/status drift")
        browser_journey = exact_object(
            profile.get("browser_journey"),
            {"status", "reason", "browser_version", "server", "probes"},
            f"toolchain v2 profile {profile_id} browser journey",
            errors,
        )
        if browser_journey.get("status") not in {"PASSED", "FAILED", "NOT_RUN"}:
            errors.append(f"toolchain v2 profile {profile_id} browser status drift")
        boundaries = exact_object(
            profile.get("boundaries"),
            {
                "model_execution",
                "browser_journey",
                "device_or_simulator_journey",
                "holdout_journey",
                "representative_customer_journey",
                "independent_verification",
                "certification",
                "model_execution_counts_as_browser_or_device",
            },
            f"toolchain v2 profile {profile_id} boundaries",
            errors,
        )
        if (
            boundaries.get("model_execution") != "NOT_RUN"
            or boundaries.get("browser_journey") != browser_journey.get("status")
            or boundaries.get("device_or_simulator_journey") != "NOT_RUN"
            or boundaries.get("holdout_journey") != "NOT_RUN"
            or boundaries.get("representative_customer_journey") != "NOT_RUN"
            or boundaries.get("independent_verification") != "NOT_RUN"
            or boundaries.get("certification") != "NOT_CERTIFIED"
            or boundaries.get("model_execution_counts_as_browser_or_device") is not False
        ):
            errors.append(f"toolchain v2 profile {profile_id} evidence boundary drift")
        if not profile_selected and (
            profile.get("status") != "NOT_RUN"
            or profile.get("reason") != "PROFILE_NOT_SELECTED"
            or profile.get("target_build") != "NOT_RUN"
            or profile.get("tool_versions") != []
            or profile.get("commands") != []
            or profile.get("browser_journey")
            != {
                "status": "NOT_RUN",
                "reason": "PROFILE_NOT_SELECTED",
                "browser_version": None,
                "server": None,
                "probes": [],
            }
            or profile.get("artifacts")
            != {"dependency_lock": None, "build_output": None}
            or profile.get("replay_profile_args") != ["--profile", profile_id]
        ):
            errors.append(
                f"toolchain v2 profile {profile_id} unselected fail-closed contract drift"
            )
        findings = profile.get("runtime_model_oracle_findings")
        if not isinstance(findings, list):
            errors.append(f"toolchain v2 profile {profile_id} findings are invalid")
            findings = []
        project_files = {
            row.get("relative_path"): artifact_files.get(str(row.get("artifact_id")))
            for row in expected_profile.get("project_files", [])
            if isinstance(row, dict)
        }
        for finding_index, finding_value in enumerate(findings):
            finding = exact_object(
                finding_value,
                {"path", "line", "marker", "file_sha256", "byte_count"},
                f"toolchain v2 profile {profile_id} finding {finding_index}",
                errors,
            )
            source = project_files.get(finding.get("path"))
            if source is None:
                errors.append(f"toolchain v2 profile {profile_id} finding source is missing")
                continue
            content = source.read_bytes()
            lines = content.decode("utf-8", errors="replace").splitlines()
            line = finding.get("line")
            marker = finding.get("marker")
            if (
                finding.get("file_sha256") != v1.digest_bytes(content)
                or finding.get("byte_count") != len(content)
                or not isinstance(line, int)
                or line < 1
                or line > len(lines)
                or not isinstance(marker, str)
                or marker not in lines[line - 1]
            ):
                errors.append(f"toolchain v2 profile {profile_id} model-oracle finding drift")
        observations = profile.get("runtime_observations")
        if not isinstance(observations, dict) or set(observations) != set(RUNTIME_CHANNELS):
            errors.append(f"toolchain v2 profile {profile_id} runtime channel closure drift")
            observations = {}
        reconstructed_channel_statuses[profile_id] = {}
        reconstructed_channel_contracts[profile_id] = {}
        declared_browser_blocks = browser_block_status_contract(
            profile_id=profile_id,
            driver=expected_profile.get("runtime_driver_contract"),
            errors=errors,
        )
        declared_native_blocks = native_block_status_ceiling(
            profile_id=profile_id,
            driver=expected_profile.get("runtime_driver_contract"),
            errors=errors,
        )
        for channel in RUNTIME_CHANNELS:
            observation = exact_object(
                observations.get(channel),
                TOOLCHAIN_CHANNEL_KEYS,
                f"toolchain v2 profile {profile_id} channel {channel}",
                errors,
            )
            reconstructed_channel_statuses[profile_id][channel] = str(
                observation.get("status")
            )
            reconstructed_channel_contracts[profile_id][channel] = (
                runtime_scope_contract_v2(
                    profile_id=profile_id,
                    channel=channel,
                    record=observation,
                    errors=errors,
                )
            )
            if (
                observation.get("status") == "PASSED"
                or observation.get("reason")
                == "BLOCK_SPECIFIC_RUNTIME_PARTIAL_CLOSURE"
            ) and findings:
                errors.append(
                    f"toolchain v2 profile {profile_id} {channel} PASS consumed a precomputed model oracle"
                )
            raw_runtime_observations[(profile_id, channel)] = (
                validate_packed_runtime_channel_v2(
                    profile_id=profile_id,
                    profile_project_digest=profile.get("project_digest"),
                    profile_manifest_digest=expected_profile.get("manifest_digest"),
                    engine_scenario_manifest_digest=scenario_digest,
                    channel=channel,
                    record=observation,
                    scenario_ids=scenario_ids,
                    scenario_inputs=scenario_inputs,
                    artifacts=artifacts,
                    artifact_files=artifact_files,
                    declared_runtime_ids=declared_runtime_ids,
                    declared_browser_blocks=(
                        declared_browser_blocks
                        if channel == "browser"
                        else declared_native_blocks
                    ),
                    errors=errors,
                )
            )

    if set(raw_profiles) != set(PROFILE_IDS):
        errors.append("toolchain v2 raw profile closure is not exact nine")
    required_runtime_states = [
        reconstructed_channel_statuses.get(profile_id, {}).get(channel, "NOT_RUN")
        for profile_id in PROFILE_IDS
        for channel in REQUIRED_RUNTIME_CHANNELS[profile_id]
    ]
    expected_runtime_status = (
        "FAILED"
        if "FAILED" in required_runtime_states
        else "PASSED"
        if required_runtime_states and all(item == "PASSED" for item in required_runtime_states)
        else "NOT_RUN"
    )
    if (
        declaration.get("profile_channel_statuses") != reconstructed_channel_statuses
        or declaration.get("runtime_status") != expected_runtime_status
    ):
        errors.append("toolchain v2 declared runtime status reconstruction drift")
    runtime_projection = campaign.get("runtime_projection")
    if not isinstance(runtime_projection, dict) or (
        runtime_projection.get("profile_channel_contracts")
        != reconstructed_channel_contracts
        or runtime_projection.get("contract_fingerprint")
        != v1.canonical_digest(reconstructed_channel_contracts)
    ):
        errors.append("toolchain v2 runtime profile/channel scope binding drift")

    routes = raw.get("route_records")
    if not isinstance(routes, list):
        errors.append("toolchain v2 route records are missing")
        routes = []
    route_ids = [item.get("route_id") for item in routes if isinstance(item, dict)]
    if route_ids != sorted(exact_routes()):
        errors.append("toolchain v2 raw route order/closure is not exact 72")
    for index, route_value in enumerate(routes):
        route = exact_object(
            route_value,
            TOOLCHAIN_ROUTE_KEYS,
            f"toolchain v2 route {index}",
            errors,
        )
        route_id = str(route.get("route_id"))
        if "--to--" not in route_id:
            continue
        source_id, target_id = route_id.split("--to--", 1)
        source = raw_profiles.get(source_id, {})
        target = raw_profiles.get(target_id, {})
        expected_route_status = (
            "FAILED"
            if "FAILED" in {source.get("status"), target.get("status")}
            else "NOT_RUN"
            if "NOT_RUN" in {source.get("status"), target.get("status")}
            else "PASSED"
        )
        expected_browser_evidence = (
            "PASSED"
            if source.get("browser_journey", {}).get("status") == "PASSED"
            and target.get("browser_journey", {}).get("status") == "PASSED"
            else "NOT_RUN"
        )
        engine_route = engine_routes.get(route_id, {})
        engine_solver: dict[str, Any] = {}
        solver_relative = engine_route.get("solver_result_path")
        try:
            if not isinstance(solver_relative, str):
                raise ValueError("missing solver result path")
            engine_root = engine_campaign_path.parent.resolve()
            engine_solver_path = (engine_root / solver_relative).resolve(strict=True)
            engine_solver_path.relative_to(engine_root)
            if engine_solver_path.is_symlink() or not engine_solver_path.is_file():
                raise ValueError("solver result is not a regular file")
            engine_solver_bytes = engine_solver_path.read_bytes()
            engine_solver = json.loads(engine_solver_bytes)
            if (
                not isinstance(engine_solver, dict)
                or v1.digest_bytes(engine_solver_bytes)
                != engine_route.get("solver_result_digest")
            ):
                raise ValueError("solver result digest drift")
        except Exception as exc:
            errors.append(
                f"toolchain v2 route {route_id} engine solver linkage drift: {exc}"
            )
            engine_solver = {}
        expected_formal_status = engine_solver.get("proof_status")
        formal_proof_contract_v2(
            proof_status=expected_formal_status,
            unconditional_proof=engine_solver.get("unconditional_proof"),
            assumptions=engine_payload.get("assumptions"),
            label=f"toolchain v2 route {route_id} engine solver",
            errors=errors,
        )
        if (
            route.get("source_profile") != source_id
            or route.get("target_profile") != target_id
            or route.get("source_project_digest") != source.get("project_digest")
            or route.get("target_project_digest") != target.get("project_digest")
            or route.get("source_execution_id") != source.get("execution_id")
            or route.get("target_execution_id") != target.get("execution_id")
            or route.get("source_toolchain_status") != source.get("status")
            or route.get("target_toolchain_status") != target.get("status")
            or route.get("source_browser_status")
            != source.get("browser_journey", {}).get("status")
            or route.get("target_browser_status")
            != target.get("browser_journey", {}).get("status")
            or route.get("source_required_runtime_channels")
            != list(REQUIRED_RUNTIME_CHANNELS.get(source_id, ()))
            or route.get("target_required_runtime_channels")
            != list(REQUIRED_RUNTIME_CHANNELS.get(target_id, ()))
            or route.get("status") != expected_route_status
            or route.get("formal_route_status") != expected_formal_status
            or route.get("runtime_ready") is not False
            or route.get("browser_evidence") != expected_browser_evidence
            or route.get("device_or_simulator_evidence") != "NOT_RUN"
            or route.get("cross_channel_equivalence") != "NOT_RUN"
            or route.get("independent_runtime_verification") != "NOT_RUN"
            or route.get("holdout_evidence") != "NOT_RUN"
            or route.get("representative_customer_evidence") != "NOT_RUN"
            or route.get("certification") != "NOT_CERTIFIED"
        ):
            errors.append(f"toolchain v2 route {route_id} identity/status drift")
        formal = route.get("formal_evidence")
        if not isinstance(formal, dict):
            errors.append(f"toolchain v2 route {route_id} formal replay is missing")
        else:
            formal_solver = formal.get("formal_solver", {})
            vacuity_solver = formal.get("vacuity_solver", {})
            validate_raw_solver_replay(
                formal_solver.get("runner_replay"),
                expected_stdout="unsat\n",
                label=f"toolchain v2 route {route_id} formal",
                errors=errors,
            )
            validate_raw_solver_replay(
                vacuity_solver.get("runner_replay"),
                expected_stdout="sat\n",
                label=f"toolchain v2 route {route_id} vacuity",
                errors=errors,
            )
            expected_replay_digest = v1.canonical_digest(
                {
                    "formal": formal_solver.get("runner_replay"),
                    "vacuity": vacuity_solver.get("runner_replay"),
                }
            )
            if (
                formal.get("artifact_closure") != "PASSED"
                or formal.get("replay_digest") != expected_replay_digest
                or formal_solver.get("outcome") != "UNSAT"
                or formal_solver.get("proof_status") != expected_formal_status
                or formal_solver.get("result_digest")
                != engine_route.get("solver_result_digest")
                or formal_solver.get("runner_replay", {}).get("solver_input_digest")
                != engine_route.get("solver_input_digest")
                or vacuity_solver.get("outcome") != "SAT"
                or vacuity_solver.get("proof_status") != "REFUTED"
                or vacuity_solver.get("precheck_status") != "PASSED"
                or vacuity_solver.get("result_digest")
                != engine_route.get("vacuity_solver_result_digest")
                or vacuity_solver.get("runner_replay", {}).get("solver_input_digest")
                != engine_route.get("vacuity_input_digest")
            ):
                errors.append(f"toolchain v2 route {route_id} formal replay drift")
        runtime_blocks = route.get("runtime_blocks")
        if not isinstance(runtime_blocks, dict) or set(runtime_blocks) != set(
            BLOCK_IDS
        ):
            errors.append(f"toolchain v2 route {route_id} block closure drift")
            runtime_blocks = {}
        for block_id in BLOCK_IDS:
            block = exact_object(
                runtime_blocks.get(block_id),
                {"channels", "cross_channel_equivalence", "independent_status"},
                f"toolchain v2 route {route_id} block {block_id}",
                errors,
            )
            channels = block.get("channels")
            if not isinstance(channels, dict) or set(channels) != set(RUNTIME_CHANNELS):
                errors.append(
                    f"toolchain v2 route {route_id} block {block_id} channel closure drift"
                )
                channels = {}
            for channel in RUNTIME_CHANNELS:
                channel_row = exact_object(
                    channels.get(channel),
                    {
                        "source_status",
                        "source_observation_digest",
                        "target_status",
                        "target_observation_digest",
                        "equivalence_status",
                    },
                    f"toolchain v2 route {route_id} block {block_id} channel {channel}",
                    errors,
                )
                source_block = (
                    source.get("runtime_observations", {})
                    .get(channel, {})
                    .get("semantic_blocks", {})
                    .get(block_id, {})
                )
                target_block = (
                    target.get("runtime_observations", {})
                    .get(channel, {})
                    .get("semantic_blocks", {})
                    .get(block_id, {})
                )
                if "FAILED" in {
                    source_block.get("status"),
                    target_block.get("status"),
                }:
                    expected_equivalence = "FAILED"
                elif (
                    source_block.get("status") == "PASSED"
                    and target_block.get("status") == "PASSED"
                ):
                    expected_equivalence = (
                        "PASSED"
                        if source_block.get("observation_digest")
                        == target_block.get("observation_digest")
                        else "FAILED"
                    )
                elif (
                    source_block.get("status") == "NOT_APPLICABLE"
                    and target_block.get("status") == "NOT_APPLICABLE"
                ):
                    expected_equivalence = "NOT_APPLICABLE"
                else:
                    expected_equivalence = "NOT_RUN"
                if channel_row != {
                    "source_status": source_block.get("status"),
                    "source_observation_digest": source_block.get("observation_digest"),
                    "target_status": target_block.get("status"),
                    "target_observation_digest": target_block.get("observation_digest"),
                    "equivalence_status": expected_equivalence,
                }:
                    errors.append(
                        f"toolchain v2 route {route_id} block {block_id} "
                        f"channel {channel} observation binding drift"
                    )
            if (
                block.get("cross_channel_equivalence") != "NOT_RUN"
                or block.get("independent_status") != "NOT_RUN"
            ):
                errors.append(
                    f"toolchain v2 route {route_id} block {block_id} "
                    "runtime/independent masquerade"
                )

    profile_counts = {
        status: sum(item.get("status") == status for item in raw_profiles.values())
        for status in ("PASSED", "FAILED", "NOT_RUN")
    }
    expected_toolchain_status = (
        "FAILED"
        if profile_counts["FAILED"]
        else "PASSED"
        if profile_counts["PASSED"] == len(PROFILE_IDS)
        else "NOT_RUN"
        if profile_counts["NOT_RUN"] == len(PROFILE_IDS)
        else "PARTIAL"
    )
    if declaration.get("status") != expected_toolchain_status:
        errors.append("toolchain v2 declaration profile aggregate drift")
    route_counts = {
        status: sum(
            isinstance(item, dict) and item.get("status") == status for item in routes
        )
        for status in ("PASSED", "FAILED", "NOT_RUN")
    }
    expected_summary = {
        "profile_status_counts": profile_counts,
        "route_status_counts": route_counts,
        "browser_journeys_passed": sum(
            item.get("browser_journey", {}).get("status") == "PASSED"
            for item in raw_profiles.values()
        ),
        "device_or_simulator_journeys_passed": 0,
        "holdout_corpus": "NOT_RUN",
        "representative_customer_corpus": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }
    if raw.get("summary") != expected_summary:
        errors.append("toolchain v2 raw summary reconstruction drift")

    identity_payload = {
        "producer": producer,
        "implementation_closure": raw.get("implementation_closure"),
        "engine_preverification_digest": (
            preverification.get("evidence_digest")
            if isinstance(preverification, dict)
            else None
        ),
        "campaign_sha256": raw_campaign.get("sha256"),
        "proof_profile": raw_campaign.get("proof_profile"),
        "semantic_block_ids": raw.get("semantic_block_ids"),
        "scenario_manifest_digest": raw.get("scenario_manifest_digest"),
        "scenario_policy": raw.get("scenario_policy"),
        "mutation_replay_digest": v1.canonical_digest(raw.get("mutation_replay")),
        "policy": raw.get("policy"),
        "profile_execution_ids": [
            item.get("execution_id") for item in profiles if isinstance(item, dict)
        ],
        "route_execution_bindings": [
            {
                "route_id": item.get("route_id"),
                "source_execution_id": item.get("source_execution_id"),
                "target_execution_id": item.get("target_execution_id"),
                "status": item.get("status"),
                "formal_replay_digest": item.get("formal_evidence", {}).get(
                    "replay_digest"
                ),
            }
            for item in routes
            if isinstance(item, dict)
        ],
    }
    identity = exact_object(
        raw.get("evidence_identity"),
        {"algorithm", "identity_payload", "sha256", "scope"},
        "toolchain v2 evidence identity",
        errors,
    )
    if (
        identity.get("algorithm") != "sha256(canonical-json(identity_payload))"
        or identity.get("identity_payload") != identity_payload
        or identity.get("sha256") != v1.canonical_digest(identity_payload)
        or identity.get("scope")
        != "producer+engine-preverification+implementation+campaign+scenario+policy+profile-executions+route-bindings"
    ):
        errors.append("toolchain v2 evidence identity drift")
    raw_replay = raw.get("replay")
    replay_argv = raw_replay.get("argv") if isinstance(raw_replay, dict) else None
    if not isinstance(raw_replay, dict) or (
        raw_replay.get("producer") != producer
        or raw_replay.get("campaign_sha256") != raw_campaign.get("sha256")
        or raw_replay.get("campaign_byte_count") != raw_campaign.get("byte_count")
        or raw_replay.get("replay_execution") != "NOT_RUN"
        or raw_replay.get("portable_pack_replay") != "NOT_RUN"
        or raw_replay.get("scope") != "LOCAL_ABSOLUTE_PATH_REEXECUTION"
        or not isinstance(replay_argv, list)
        or len(replay_argv) < 3
        or replay_argv[1] != producer.get("path")
        or replay_argv[2] != raw_campaign.get("path")
        or (("--no-network" in replay_argv) is not (policy.get("no_network") is True))
        or raw_replay.get("environment")
        != {
            "inherits_only_per_command_allowlist": True,
            "network_allowed": policy.get("no_network") is not True,
        }
    ):
        errors.append("toolchain v2 replay producer/campaign binding drift")


def max_model_influence(value: object) -> str | None:
    if not isinstance(value, dict) or not value:
        return None
    values = list(value.values())
    if any(item not in MODEL_PRECEDENCE for item in values):
        return None
    return max(values, key=lambda item: MODEL_PRECEDENCE[str(item)])


def max_runtime_influence(model: object, runtime: object) -> str | None:
    if not isinstance(model, dict) or not isinstance(runtime, dict):
        return None
    if set(model) != set(runtime):
        return None
    values = [
        runtime[pointer] for pointer in model if model[pointer] != "DECLARATION_ECHO"
    ]
    if not values:
        return "DECLARATION_ECHO"
    if any(item not in RUNTIME_RESTRICTIVENESS for item in values):
        return None
    return max(values, key=lambda item: RUNTIME_RESTRICTIVENESS[str(item)])


def validate_oracle_graph(
    campaign: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    used: set[str],
    errors: list[str],
) -> bool:
    declaration = campaign.get("oracle_provenance", {})
    graph_id = str(declaration.get("graph_artifact_id"))
    used.add(graph_id)
    if artifacts.get(graph_id, {}).get("role") != "oracle-provenance-graph-v2":
        errors.append("oracle provenance graph role mismatch")
        return False
    path = artifact_files.get(graph_id)
    if path is None:
        return False
    try:
        graph = load_json(path)
    except Exception as exc:
        errors.append(f"oracle provenance graph is invalid: {exc}")
        return False
    implementation_fingerprint = campaign.get("implementation", {}).get("fingerprint")
    expected_nodes = [
        {
            "id": "canonical-model",
            "kind": "CANONICAL_ORACLE",
            "producer_fingerprint": implementation_fingerprint,
        },
        {
            "id": "formal-input",
            "kind": "FORMAL_INPUT",
            "producer_fingerprint": implementation_fingerprint,
        },
        {
            "id": "solver-input",
            "kind": "SOLVER_INPUT",
            "producer_fingerprint": implementation_fingerprint,
        },
        {
            "id": "solver-result",
            "kind": "SOLVER_RESULT",
            "producer_fingerprint": implementation_fingerprint,
        },
    ]
    expected_edges = [
        {"from": "canonical-model", "to": "formal-input", "relation": "DERIVES"},
        {"from": "formal-input", "to": "solver-input", "relation": "ENCODES"},
        {"from": "solver-input", "to": "solver-result", "relation": "SOLVED_BY"},
    ]
    external = campaign.get("external_evidence", {})
    if external.get("status") == "PASSED":
        intake_id = external.get("intake_artifact_id")
        expected_nodes.extend(
            [
                {
                    "id": "external-trust-root",
                    "kind": "TRUST_ROOT",
                    "producer_fingerprint": external.get("trust_root_fingerprint"),
                },
                {
                    "id": "external-replay-verifier",
                    "kind": "INDEPENDENT_REPLAY_VERIFIER",
                    "producer_fingerprint": external.get(
                        "replay_verifier_fingerprint"
                    ),
                },
                {
                    "id": "external-intake",
                    "kind": "EXTERNAL_INTAKE",
                    "producer_fingerprint": artifacts.get(str(intake_id), {}).get(
                        "sha256"
                    ),
                },
                {
                    "id": "external-runtime-oracle",
                    "kind": "INDEPENDENT_ORACLE",
                    "producer_fingerprint": v1.canonical_digest(
                        sorted(external.get("artifact_ids", []))
                    ),
                },
            ]
        )
        expected_edges.extend(
            [
                {
                    "from": "external-trust-root",
                    "to": "external-replay-verifier",
                    "relation": "AUTHORIZES",
                },
                {
                    "from": "external-intake",
                    "to": "external-runtime-oracle",
                    "relation": "EVIDENCES",
                },
                {
                    "from": "external-replay-verifier",
                    "to": "external-runtime-oracle",
                    "relation": "INDEPENDENTLY_REPLAYS",
                },
            ]
        )
    expected_graph = {
        "schema_version": 2,
        "kind": "frontend-oracle-provenance-graph-v2",
        "nodes": expected_nodes,
        "edges": expected_edges,
        "independent_oracle_status": (
            "PASSED" if external.get("status") == "PASSED" else "NOT_RUN"
        ),
    }
    if graph != expected_graph:
        errors.append("oracle provenance graph exact evidence/trust closure drift")
    nodes = unique_index(graph.get("nodes"), "id", "oracle node", errors)
    edges_value = graph.get("edges")
    if not isinstance(edges_value, list):
        errors.append("oracle provenance edges must be an array")
        return False
    adjacency: dict[str, set[str]] = {item: set() for item in nodes}
    reverse: dict[str, set[str]] = {item: set() for item in nodes}
    seen_edges: set[tuple[str, str, str]] = set()
    for index, edge in enumerate(edges_value):
        if not isinstance(edge, dict) or set(edge) != {"from", "to", "relation"}:
            errors.append(f"oracle edge {index} is invalid")
            continue
        source, target, relation = (
            edge.get("from"),
            edge.get("to"),
            edge.get("relation"),
        )
        if source not in nodes or target not in nodes or not isinstance(relation, str):
            errors.append(f"oracle edge {index} has unknown endpoints")
            continue
        key = (str(source), str(target), relation)
        if key in seen_edges:
            errors.append(f"duplicate oracle edge: {key}")
        seen_edges.add(key)
        adjacency[str(source)].add(str(target))
        reverse[str(target)].add(str(source))
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append("circular proof/oracle provenance is forbidden")
            return
        if node in visited:
            return
        visiting.add(node)
        for target in adjacency[node]:
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in nodes:
        visit(node)
    solver_results = {
        node for node, row in nodes.items() if row.get("kind") == "SOLVER_RESULT"
    }
    for solver_result in solver_results:
        for target in adjacency[solver_result]:
            if nodes[target].get("kind") in {
                "FORMAL_INPUT",
                "SOLVER_INPUT",
                "CANONICAL_ORACLE",
                "INDEPENDENT_ORACLE",
            }:
                errors.append(
                    "solver result is circularly reused as proof input/oracle"
                )
    independent_nodes = {
        node for node, row in nodes.items() if row.get("kind") == "INDEPENDENT_ORACLE"
    }
    independent_ok = bool(independent_nodes)
    for independent in independent_nodes:
        stack = list(reverse[independent])
        ancestors: set[str] = set()
        while stack:
            current = stack.pop()
            if current in ancestors:
                continue
            ancestors.add(current)
            stack.extend(reverse[current])
        if any(
            nodes[item].get("kind") in FORBIDDEN_INDEPENDENT_KINDS for item in ancestors
        ):
            errors.append(
                "independent oracle transitively depends on same-engine evidence"
            )
            independent_ok = False
        node = nodes[independent]
        if node.get("producer_fingerprint") in {
            campaign.get("implementation", {}).get("fingerprint"),
            campaign.get("toolchain_evidence", {}).get("producer_fingerprint"),
        }:
            errors.append("same-producer oracle cannot be independent")
            independent_ok = False
    declared_independent = declaration.get("independence") == "EXTERNALLY_INDEPENDENT"
    if declaration.get("same_producer") is True and declared_independent:
        errors.append("same-producer evidence masquerades as externally independent")
        independent_ok = False
    if declaration.get("status") == "PASSED" and (
        not declared_independent or not independent_ok
    ):
        errors.append("oracle independence PASS lacks an acyclic external provenance")
    return declaration.get("status") == "PASSED" and independent_ok


def parse_external_utc(value: object, label: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        errors.append(f"{label} is not an exact UTC timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        errors.append(f"{label} is not a valid timestamp")
        return None
    return parsed.astimezone(UTC)


def verify_external_ed25519(
    *,
    public_key_pem: object,
    signature_base64: object,
    payload: bytes,
    label: str,
    errors: list[str],
) -> bool:
    node = shutil.which("node")
    if node is None:
        errors.append(f"{label} cannot be verified because node is unavailable")
        return False
    if not isinstance(public_key_pem, str) or not isinstance(signature_base64, str):
        errors.append(f"{label} key/signature is malformed")
        return False
    try:
        signature = base64.b64decode(signature_base64, validate=True)
    except (binascii.Error, ValueError):
        errors.append(f"{label} signature is not canonical base64")
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="frontend-v2-external-verify-") as directory:
            root = Path(directory)
            public_path = root / "public.pem"
            payload_path = root / "payload.bin"
            signature_path = root / "signature.bin"
            public_path.write_text(public_key_pem, encoding="utf-8")
            payload_path.write_bytes(payload)
            signature_path.write_bytes(signature)
            completed = subprocess.run(
                [
                    node,
                    "-e",
                    (
                        "const fs=require('node:fs');"
                        "const crypto=require('node:crypto');"
                        "const [key,input,signature]=process.argv.slice(1);"
                        "let valid=false;"
                        "try { valid=crypto.verify(null,fs.readFileSync(input),"
                        "fs.readFileSync(key),fs.readFileSync(signature)); }"
                        "catch (error) { process.stderr.write(String(error));process.exit(2); }"
                        "process.exit(valid?0:1);"
                    ),
                    str(public_path),
                    str(payload_path),
                    str(signature_path),
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
    except Exception as exc:
        errors.append(f"{label} signature verification failed: {exc}")
        return False
    if completed.returncode != 0:
        errors.append(f"{label} signature is invalid")
        return False
    return True


def external_public_key_digest(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return v1.digest_bytes(value.encode("utf-8"))


def validate_external_trust_chain_v2(
    *,
    pack: Path,
    trust_root_path: Path | None,
    trust: dict[str, Any],
    declaration: dict[str, Any],
    replay_files: dict[str, Path],
    errors: list[str],
) -> dict[str, Any] | None:
    if trust_root_path is None:
        errors.append(
            "frontend v2 external evidence has no operator-configured trust root"
        )
        return None
    try:
        supplied_path = trust_root_path
        root_path = supplied_path.resolve(strict=True)
        if supplied_path.is_symlink() or not root_path.is_file():
            raise ValueError("regular non-symlink file required")
        try:
            root_path.relative_to(pack.resolve(strict=True))
        except ValueError:
            pass
        else:
            raise ValueError("trust root must remain outside the pack")
        trust_root = load_json(root_path)
    except Exception as exc:
        errors.append(f"frontend v2 external trust root is unavailable: {exc}")
        return None
    root_schema_path = replay_files.get(
        "schemas/batch32/frontend-formal-external-trust-root-v2.schema.json"
    )
    if root_schema_path is None:
        errors.append("frontend v2 external trust-root replay schema is missing")
    else:
        try:
            validate_schema(
                trust_root,
                load_json(root_schema_path),
                "frontend v2 external trust root",
                errors,
            )
        except Exception as exc:
            errors.append(f"frontend v2 external trust-root schema is invalid: {exc}")
    if declaration.get("trust_root_fingerprint") != v1.digest_bytes(
        root_path.read_bytes()
    ):
        errors.append("frontend v2 external trust-root fingerprint drift")
    now = datetime.now(UTC)
    try:
        if set(trust_root) != {
            "schema_version",
            "kind",
            "root_id",
            "policy_id",
            "valid_from",
            "valid_until",
            "revoked",
            "trust_store_signing_keys",
            "organization_key_allowlist",
            "revocations",
            "replay_verifier",
        }:
            raise ValueError("root key closure")
        root_from = parse_external_utc(
            trust_root.get("valid_from"), "external root valid_from", errors
        )
        root_until = parse_external_utc(
            trust_root.get("valid_until"), "external root valid_until", errors
        )
        if (
            trust_root.get("schema_version") != 2
            or trust_root.get("kind")
            != "frontend-formal-external-trust-root-v2"
            or trust_root.get("policy_id")
            != "frontend-independent-evidence-policy-v2"
            or declaration.get("trust_root_id") != trust_root.get("root_id")
            or trust_root.get("revoked") is not False
            or root_from is None
            or root_until is None
            or not root_from <= now < root_until
        ):
            raise ValueError("root identity/time/revocation")
        root_revocations = trust_root.get("revocations")
        if not isinstance(root_revocations, dict) or set(root_revocations) != {
            "key_ids",
            "organization_ids",
            "updated_at",
        }:
            raise ValueError("root revocation closure")
        root_revocation_time = parse_external_utc(
            root_revocations.get("updated_at"),
            "external root revocations updated_at",
            errors,
        )
        if root_revocation_time is None or root_revocation_time > now:
            raise ValueError("root revocation time")
        root_revoked_keys = set(root_revocations.get("key_ids", []))
        root_revoked_orgs = set(root_revocations.get("organization_ids", []))

        signer_rows = trust_root.get("trust_store_signing_keys")
        signer_by_id: dict[str, dict[str, Any]] = {}
        if not isinstance(signer_rows, list) or not signer_rows:
            raise ValueError("root signer missing")
        for row in signer_rows:
            if not isinstance(row, dict) or set(row) != {
                "key_id",
                "public_key_pem",
                "valid_from",
                "valid_until",
                "revoked",
            }:
                raise ValueError("root signer closure")
            key_id = str(row.get("key_id"))
            valid_from = parse_external_utc(
                row.get("valid_from"), f"root signer {key_id} valid_from", errors
            )
            valid_until = parse_external_utc(
                row.get("valid_until"), f"root signer {key_id} valid_until", errors
            )
            if (
                not key_id
                or key_id in signer_by_id
                or row.get("revoked") is not False
                or key_id in root_revoked_keys
                or valid_from is None
                or valid_until is None
                or not valid_from <= now < valid_until
                or external_public_key_digest(row.get("public_key_pem")) is None
            ):
                raise ValueError("root signer invalid")
            signer_by_id[key_id] = row

        allow_rows = trust_root.get("organization_key_allowlist")
        allowed: dict[tuple[str, str, str], str] = {}
        if not isinstance(allow_rows, list) or len(allow_rows) < 4:
            raise ValueError("organization/key allowlist missing")
        for row in allow_rows:
            if not isinstance(row, dict) or set(row) != {
                "organization_id",
                "key_id",
                "role",
                "public_key_sha256",
            }:
                raise ValueError("organization/key allowlist closure")
            key = (
                str(row.get("organization_id")),
                str(row.get("key_id")),
                str(row.get("role")),
            )
            if (
                not all(key)
                or key in allowed
                or key[2] not in {"AUTHORIZATION", "EXECUTOR", "VERIFIER", "CUSTOMER"}
                or key[0] in root_revoked_orgs
                or key[1] in root_revoked_keys
            ):
                raise ValueError("organization/key allowlist invalid")
            allowed[key] = str(row.get("public_key_sha256"))

        if set(trust) != {
            "schema_version",
            "kind",
            "trust_store_id",
            "root_id",
            "issued_at",
            "expires_at",
            "keys",
            "revocations",
            "root_authorization",
        }:
            raise ValueError("trust-store key closure")
        trust_issued = parse_external_utc(
            trust.get("issued_at"), "external trust issued_at", errors
        )
        trust_expires = parse_external_utc(
            trust.get("expires_at"), "external trust expires_at", errors
        )
        if (
            trust.get("schema_version") != 2
            or trust.get("kind") != "frontend-formal-external-trust-store-v2"
            or trust.get("root_id") != trust_root.get("root_id")
            or trust_issued is None
            or trust_expires is None
            or not root_from <= trust_issued <= now < trust_expires <= root_until
        ):
            raise ValueError("trust-store identity/time")
        trust_revocations = trust.get("revocations")
        if not isinstance(trust_revocations, dict) or set(trust_revocations) != {
            "key_ids",
            "organization_ids",
            "updated_at",
        }:
            raise ValueError("trust-store revocation closure")
        trust_revocation_time = parse_external_utc(
            trust_revocations.get("updated_at"),
            "external trust revocations updated_at",
            errors,
        )
        if trust_revocation_time is None or trust_revocation_time > now:
            raise ValueError("trust-store revocation time")
        revoked_keys = root_revoked_keys | set(trust_revocations.get("key_ids", []))
        revoked_orgs = root_revoked_orgs | set(
            trust_revocations.get("organization_ids", [])
        )

        authorization = trust.get("root_authorization")
        if not isinstance(authorization, dict) or set(authorization) != {
            "root_key_id",
            "algorithm",
            "signed_payload_sha256",
            "signature_base64",
        }:
            raise ValueError("trust-store root authorization missing")
        signer = signer_by_id.get(str(authorization.get("root_key_id")))
        unsigned_trust = dict(trust)
        unsigned_trust.pop("root_authorization", None)
        unsigned_bytes = v1.canonical_bytes(unsigned_trust)
        if (
            authorization.get("algorithm") != "ed25519"
            or authorization.get("signed_payload_sha256")
            != v1.digest_bytes(unsigned_bytes)
            or not isinstance(signer, dict)
            or not verify_external_ed25519(
                public_key_pem=signer.get("public_key_pem"),
                signature_base64=authorization.get("signature_base64"),
                payload=unsigned_bytes,
                label="frontend v2 external trust-store root authorization",
                errors=errors,
            )
        ):
            raise ValueError("trust-store root authorization invalid")

        trust_keys = trust.get("keys")
        key_by_id: dict[str, dict[str, Any]] = {}
        if not isinstance(trust_keys, list) or len(trust_keys) < 4:
            raise ValueError("evidence keys missing")
        for row in trust_keys:
            if not isinstance(row, dict) or set(row) != {
                "key_id",
                "organization_id",
                "roles",
                "public_key_pem",
                "valid_from",
                "valid_until",
                "revoked",
            }:
                raise ValueError("evidence key closure")
            key_id = str(row.get("key_id"))
            organization_id = str(row.get("organization_id"))
            roles = row.get("roles")
            valid_from = parse_external_utc(
                row.get("valid_from"), f"external key {key_id} valid_from", errors
            )
            valid_until = parse_external_utc(
                row.get("valid_until"), f"external key {key_id} valid_until", errors
            )
            public_digest = external_public_key_digest(row.get("public_key_pem"))
            if (
                not key_id
                or not organization_id
                or key_id in key_by_id
                or not isinstance(roles, list)
                or not roles
                or len(roles) != len(set(roles))
                or row.get("revoked") is not False
                or key_id in revoked_keys
                or organization_id in revoked_orgs
                or valid_from is None
                or valid_until is None
                or not valid_from <= trust_issued <= now < valid_until
                or public_digest is None
                or any(
                    allowed.get((organization_id, key_id, str(role)))
                    != public_digest
                    for role in roles
                )
            ):
                raise ValueError("evidence key not externally allowlisted")
            key_by_id[key_id] = row

        verifier = trust_root.get("replay_verifier")
        if not isinstance(verifier, dict) or set(verifier) != {
            "verifier_id",
            "path",
            "realpath",
            "sha256",
            "bytes",
            "version",
        }:
            raise ValueError("replay verifier identity closure")
        verifier_path = Path(str(verifier.get("path")))
        if (
            not verifier_path.is_absolute()
            or not verifier_path.is_file()
            or verifier_path.resolve(strict=True).as_posix() != verifier.get("realpath")
        ):
            raise ValueError("replay verifier path")
        verifier_bytes = verifier_path.read_bytes()
        if (
            verifier.get("sha256") != v1.digest_bytes(verifier_bytes)
            or verifier.get("bytes") != len(verifier_bytes)
            or declaration.get("replay_verifier_fingerprint")
            != v1.canonical_digest(verifier)
        ):
            raise ValueError("replay verifier bytes/fingerprint")
        version = subprocess.run(
            [str(verifier_path.resolve(strict=True)), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if version.returncode or version.stdout.strip() != verifier.get("version"):
            raise ValueError("replay verifier version")
    except Exception as exc:
        errors.append(f"frontend v2 external trust chain invalid: {exc}")
        return None
    return {
        "root_id": trust_root["root_id"],
        "key_by_id": key_by_id,
        "issued_at": trust_issued,
        "expires_at": trust_expires,
        "revoked_key_ids": revoked_keys,
        "revoked_organization_ids": revoked_orgs,
        "replay_verifier": verifier,
    }


def run_external_replay_verifier_v2(
    *,
    verifier: dict[str, Any],
    intake_path: Path,
    trust_store_path: Path,
    artifact_root: Path,
    scope_digest: str,
    execution_ids: set[str],
    replay_ids: set[str],
    raw_ids: set[str],
    errors: list[str],
) -> bool:
    try:
        completed = subprocess.run(
            [
                str(verifier["realpath"]),
                "--external-evidence",
                str(intake_path),
                "--external-trust-store",
                str(trust_store_path),
                "--artifact-root",
                str(artifact_root),
                "--scope-digest",
                scope_digest,
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        expected = {
            "schema_version": 2,
            "kind": "frontend-formal-external-replay-verifier-result-v2",
            "verifier_id": verifier["verifier_id"],
            "scope_digest": scope_digest,
            "intake_sha256": v1.digest_bytes(intake_path.read_bytes()),
            "trust_store_sha256": v1.digest_bytes(trust_store_path.read_bytes()),
            "verified_execution_artifact_ids": sorted(execution_ids),
            "verified_replay_artifact_ids": sorted(replay_ids),
            "verified_raw_artifact_ids": sorted(raw_ids),
            "verified_route_block_count": 72 * len(BLOCK_IDS),
            "status": "PASSED",
        }
        if completed.returncode or result != expected:
            raise ValueError("result closure/status drift")
    except Exception as exc:
        errors.append(f"frontend v2 external replay verifier failed: {exc}")
        return False
    return True


def external_actuals_v2(
    *,
    path: Path,
    scope_digest: str,
    route_id: str,
    block_id: str,
    profile_id: str,
    case_ids: set[str],
    schema_path: Path | None,
    errors: list[str],
) -> tuple[dict[str, dict[str, Any]], str] | None:
    try:
        payload = load_json(path)
        if schema_path is None:
            raise ValueError("schema missing")
        validate_schema(
            payload,
            load_json(schema_path),
            f"external observation {route_id}/{block_id}/{profile_id}",
            errors,
        )
        rows = payload.get("actuals")
        if (
            payload.get("scope_digest") != scope_digest
            or payload.get("route_id") != route_id
            or payload.get("block_id") != block_id
            or payload.get("profile_id") != profile_id
            or set(payload.get("corpus_case_ids", [])) != case_ids
            or payload.get("observer_protocol") != BLOCK_OBSERVER_CONTRACT
            or payload.get("model_values_used_as_actual") is not False
            or not isinstance(rows, list)
            or len(rows) != len(case_ids)
        ):
            raise ValueError("identity/closure drift")
        actuals: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"case_id", "actual"}:
                raise ValueError("row drift")
            case_id = str(row.get("case_id"))
            actual = row.get("actual")
            if (
                case_id not in case_ids
                or case_id in actuals
                or not isinstance(actual, dict)
                or set(actual) != RUNTIME_ACTUAL_KEYS[block_id]
                or not external_actual_value_valid_v2(block_id, actual)
            ):
                raise ValueError("actual drift")
            actuals[case_id] = actual
        if set(actuals) != case_ids:
            raise ValueError("case closure drift")
        normalized = [
            {"case_id": case_id, "actual": actuals[case_id]}
            for case_id in sorted(actuals)
        ]
        return actuals, v1.canonical_digest(normalized)
    except Exception as exc:
        errors.append(
            f"frontend v2 external observation {route_id}/{block_id}/{profile_id} invalid: {exc}"
        )
        return None


def validate_external_evidence_v2(
    *,
    pack: Path,
    campaign: dict[str, Any],
    scope_digest: str,
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    replay_files: dict[str, Path],
    trust_root_path: Path | None,
    used: set[str],
    errors: list[str],
) -> dict[str, Any]:
    """Accept only the exact absent declaration until positive validation is complete."""

    del pack, scope_digest, artifacts, artifact_files, replay_files, trust_root_path, used
    declaration = campaign.get("external_evidence")
    absent = {
        "provided": False,
        "status": "NOT_RUN",
        "intake_artifact_id": None,
        "trust_store_artifact_id": None,
        "trust_root_id": None,
        "trust_root_fingerprint": None,
        "trust_store_authorization_status": "NOT_RUN",
        "replay_verifier_fingerprint": None,
        "artifact_ids": [],
        "scope_digest": None,
        "authorization_status": "NOT_RUN",
        "signature_status": "NOT_RUN",
        "replay_status": "NOT_RUN",
        "independent_status": "NOT_RUN",
        "holdout_status": "NOT_RUN",
        "representative_status": "NOT_RUN",
        "customer_status": "NOT_RUN",
        "organization_ids": [],
    }
    if declaration == absent:
        return {"status": "NOT_RUN", "results": {}}
    errors.append(
        "frontend v2 external positive protocol is not implemented: "
        "V2_EXTERNAL_POSITIVE_PROTOCOL_NOT_IMPLEMENTED"
    )
    return {
        "status": "FAILED",
        "results": {},
        "reason": "V2_EXTERNAL_POSITIVE_PROTOCOL_NOT_IMPLEMENTED",
    }
def validate_channel_observation(
    *,
    route_id: str,
    block_id: str,
    endpoint: str,
    profile_id: str,
    value: object,
    expected_channel: str,
    scenario_ids: list[str],
    toolchain_artifact_id: str | None,
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    used: set[str],
    errors: list[str],
) -> str:
    label = f"route {route_id} block {block_id} {endpoint} {expected_channel}"
    if not isinstance(value, dict):
        errors.append(f"{label} observation is invalid")
        return "FAILED"
    if value.get("channel") != expected_channel:
        errors.append(f"{label} channel identity drift")
    required = expected_channel in REQUIRED_RUNTIME_CHANNELS[profile_id]
    if value.get("required") is not required:
        errors.append(f"{label} required applicability drift")
    status = value.get("status")
    if status not in EVIDENCE_STATES:
        errors.append(f"{label} status is invalid")
        return "FAILED"
    artifact_ids = value.get("observation_artifact_ids")
    if not isinstance(artifact_ids, list):
        errors.append(f"{label} observation artifact ids are invalid")
        artifact_ids = []
    actual_digests = value.get("observation_actual_digests")
    if not isinstance(actual_digests, list):
        errors.append(f"{label} observation actual digests are invalid")
        actual_digests = []
    used.update(str(item) for item in artifact_ids)
    closure_fields = {
        "result_manifest_artifact_id": value.get("result_manifest_artifact_id"),
        "runtime_source_artifact_ids": value.get("runtime_source_artifact_ids"),
        "execution_policy_artifact_id": value.get("execution_policy_artifact_id"),
        "raw_probe_artifact_ids": value.get("raw_probe_artifact_ids"),
        "build_execution_id": value.get("build_execution_id"),
        "startup_execution_id": value.get("startup_execution_id"),
        "journey_execution_id": value.get("journey_execution_id"),
    }
    empty_closure_fields = {
        "result_manifest_artifact_id": None,
        "runtime_source_artifact_ids": [],
        "execution_policy_artifact_id": None,
        "raw_probe_artifact_ids": [],
        "build_execution_id": None,
        "startup_execution_id": None,
        "journey_execution_id": None,
    }
    closure_present = closure_fields != empty_closure_fields
    closure_complete = (
        isinstance(closure_fields["result_manifest_artifact_id"], str)
        and isinstance(closure_fields["runtime_source_artifact_ids"], list)
        and bool(closure_fields["runtime_source_artifact_ids"])
        and isinstance(closure_fields["execution_policy_artifact_id"], str)
        and isinstance(closure_fields["raw_probe_artifact_ids"], list)
        and bool(closure_fields["raw_probe_artifact_ids"])
        and all(
            isinstance(closure_fields[name], str)
            for name in (
                "build_execution_id", "startup_execution_id", "journey_execution_id"
            )
        )
    )
    if required:
        if status == "NOT_APPLICABLE":
            errors.append(f"{label} required channel cannot be NOT_APPLICABLE")
        if status == "PASSED":
            if (
                value.get("actual_derived") is not True
                or value.get("model_values_used_as_actual") is not False
                or value.get("scenario_count") != len(scenario_ids)
                or len(artifact_ids) != len(scenario_ids)
                or len(actual_digests) != len(scenario_ids)
                or not artifact_ids
                or value.get("observation_digest") is None
                or not closure_complete
            ):
                errors.append(f"{label} runtime PASS lacks actual byte evidence")
        elif (
            value.get("actual_derived") is not False
            or artifact_ids
            or actual_digests
            or value.get("observation_digest") is not None
            or value.get("scenario_count") != 0
            or (closure_present and not closure_complete)
        ):
            errors.append(
                f"{label} nonpassing runtime must not expose PASS observation closure"
            )
    else:
        if (
            status != "NOT_APPLICABLE"
            or artifact_ids
            or actual_digests
            or value.get("observation_digest") is not None
            or value.get("scenario_count") != 0
            or value.get("actual_derived") is not False
            or closure_fields != empty_closure_fields
        ):
            errors.append(f"{label} non-required channel must be exact NOT_APPLICABLE")
    for artifact_id in artifact_ids:
        reference = artifacts.get(str(artifact_id), {})
        if reference.get("role") != "runtime-block-observation-v2":
            errors.append(f"{label} actual observation artifact role mismatch")
    if status == "PASSED" or (status == "NOT_RUN" and closure_present):
        observations: dict[str, dict[str, Any]] = {}
        closure_ids = [
            str(closure_fields["result_manifest_artifact_id"]),
            str(closure_fields["execution_policy_artifact_id"]),
            *[str(item) for item in closure_fields["runtime_source_artifact_ids"]],
            *[str(item) for item in closure_fields["raw_probe_artifact_ids"]],
        ]
        used.update(closure_ids)
        if artifacts.get(str(closure_fields["result_manifest_artifact_id"]), {}).get(
            "role"
        ) != "runtime-result-manifest-v2":
            errors.append(f"{label} result manifest role mismatch")
        if artifacts.get(str(closure_fields["execution_policy_artifact_id"]), {}).get(
            "role"
        ) != "runtime-execution-policy-v2":
            errors.append(f"{label} execution policy role mismatch")
        for identifier in closure_fields["runtime_source_artifact_ids"]:
            role = str(artifacts.get(str(identifier), {}).get("role", ""))
            if not (
                role.startswith("runtime-trace-v2:")
                or role.startswith("runtime-block-observer-trace-v2:")
            ):
                errors.append(f"{label} runtime trace role mismatch")
        for identifier in closure_fields["raw_probe_artifact_ids"]:
            if artifacts.get(str(identifier), {}).get("role") != "runtime-raw-probe-v2":
                errors.append(f"{label} raw probe role mismatch")
        if status != "PASSED":
            return str(status)
        for observation_index, artifact_id in enumerate(artifact_ids):
            path = artifact_files.get(str(artifact_id))
            if path is None:
                continue
            try:
                payload = load_json(path)
            except Exception as exc:
                errors.append(f"{label} actual observation is invalid: {exc}")
                continue
            if set(payload) != {
                "schema_version",
                "kind",
                "actual_source",
                "profile_id",
                "channel",
                "scenario_id",
                "block_id",
                "provenance",
                "actual",
            }:
                errors.append(f"{label} actual observation key closure drift")
            scenario_id = payload.get("scenario_id")
            actual = payload.get("actual")
            if (
                payload.get("schema_version") != "1.0"
                or payload.get("kind")
                != "frontend-interaction-runtime-block-observation"
                or payload.get("actual_source")
                != "BLOCK_SPECIFIC_RUNTIME_OBSERVED"
                or payload.get("profile_id") != profile_id
                or payload.get("channel") != expected_channel
                or payload.get("block_id") != block_id
                or scenario_id not in scenario_ids
                or scenario_id in observations
                or not isinstance(actual, dict)
                or set(actual) != RUNTIME_ACTUAL_KEYS[block_id]
                or (
                    actual_digests[observation_index]
                    if observation_index < len(actual_digests)
                    else None
                )
                != v1.canonical_digest(actual)
            ):
                errors.append(f"{label} actual observation identity/digest drift")
            if isinstance(scenario_id, str):
                observations[scenario_id] = {
                    "actual": actual,
                    "actual_digest": v1.canonical_digest(actual),
                }
        expected_observation_digest = v1.canonical_digest(
            [
                {
                    "scenario_id": scenario_id,
                    "actual_digest": observations.get(scenario_id, {}).get(
                        "actual_digest"
                    ),
                }
                for scenario_id in scenario_ids
            ]
        )
        if (
            set(observations) != set(scenario_ids)
            or value.get("observation_digest") != expected_observation_digest
        ):
            errors.append(f"{label} actual observation aggregate drift")
    return str(status)


def validate_route(
    *,
    pack: Path,
    route: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
    scenario_ids: list[str],
    scenario_digest: str,
    route_schema: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    engine_route: dict[str, Any],
    engine_path_ids: dict[str, str],
    engine_assumptions: list[str],
    engine_mutation_digest: str,
    implementation_fingerprint: str,
    replay_fingerprint: str,
    toolchain_artifact_id: str | None,
    toolchain_producer_fingerprint: str | None,
    external_capture: dict[str, Any],
    execute_solver_replay: bool,
    used: set[str],
    errors: list[str],
) -> dict[str, Any]:
    route_id = str(route.get("route_id"))
    source_id = str(route.get("source_profile_id"))
    target_id = str(route.get("target_profile_id"))
    expected_route_id = f"{source_id}--to--{target_id}"
    if source_id == target_id or route_id != expected_route_id:
        errors.append(f"route {route_id} is self-directed or noncanonical")
    if (
        engine_route.get("route_id") != route_id
        or engine_route.get("source_profile") != source_id
        or engine_route.get("target_profile") != target_id
        or engine_route.get("source_project_digest")
        != route.get("source_project_digest")
        or engine_route.get("target_project_digest")
        != route.get("target_project_digest")
    ):
        errors.append(f"route {route_id} engine route binding drift")
    source = profiles.get(source_id, {})
    target = profiles.get(target_id, {})
    for key, expected in (
        ("source_profile_digest", source.get("profile_digest")),
        ("target_profile_digest", target.get("profile_digest")),
        ("source_project_digest", source.get("project_digest")),
        ("target_project_digest", target.get("project_digest")),
    ):
        if route.get(key) != expected:
            errors.append(f"route {route_id} {key} drift")
    wrapper_id = str(route.get("route_evidence_artifact_id"))
    used.add(wrapper_id)
    wrapper_ref = artifacts.get(wrapper_id, {})
    if wrapper_ref.get("role") != "frontend-route-evidence-v2":
        errors.append(f"route {route_id} evidence role mismatch")
        return {}
    wrapper_path = artifact_files.get(wrapper_id)
    if wrapper_path is None:
        return {}
    try:
        wrapper = load_json(wrapper_path)
    except Exception as exc:
        errors.append(f"route {route_id} evidence is invalid: {exc}")
        return {}
    validate_schema(wrapper, route_schema, f"route {route_id}", errors)
    if (
        wrapper.get("route_id") != route_id
        or wrapper.get("source_profile_id") != source_id
        or wrapper.get("target_profile_id") != target_id
        or wrapper.get("source_profile_digest") != source.get("profile_digest")
        or wrapper.get("target_profile_digest") != target.get("profile_digest")
    ):
        errors.append(f"route {route_id} wrapper identity drift")
    if (
        wrapper.get("scenario_manifest_sha256") != scenario_digest
        or wrapper.get("scenario_ids") != scenario_ids
    ):
        errors.append(f"route {route_id} scenario manifest drift")
    if wrapper.get("implementation_fingerprint") != implementation_fingerprint:
        errors.append(f"route {route_id} implementation fingerprint drift")
    if wrapper.get("replay_fingerprint") != replay_fingerprint:
        errors.append(f"route {route_id} replay fingerprint drift")
    wrapper_refs = unique_index(
        wrapper.get("artifact_refs"), "id", f"route {route_id} artifact ref", errors
    )
    for identifier, reference in wrapper_refs.items():
        used.add(identifier)
        if artifacts.get(identifier) != reference:
            errors.append(f"route {route_id} artifact ref {identifier} drift")
    if set(route.get("artifact_ids", [])) != set(wrapper_refs) | {wrapper_id}:
        errors.append(f"route {route_id} artifact closure is not exact")
    route_artifact_ids = set(wrapper_refs)
    blocks = wrapper.get("blocks")
    if not isinstance(blocks, list):
        errors.append(f"route {route_id} block evidence is missing")
        return {}
    block_index = unique_index(blocks, "block_id", f"route {route_id} block", errors)
    if tuple(block_index) != BLOCK_IDS:
        errors.append(f"route {route_id} block closure/order is not exact 12/12")

    model_passes: list[bool] = []
    browser_states: list[str] = []
    native_states: list[str] = []
    runtime_states: list[str] = []
    independent_states: list[str] = []
    unconditional = True
    formal_statuses: list[str] = []
    for block_id in BLOCK_IDS:
        block = block_index.get(block_id)
        if not isinstance(block, dict):
            continue
        semantic = block.get("semantic", {})
        semantic_hashes: list[str] = []
        for name in ("canonical_ir", "source_relift_ir", "target_relift_ir"):
            span_ref = semantic.get(name)
            if (
                not isinstance(span_ref, dict)
                or span_ref.get("pointer") != BLOCK_ROOT_POINTERS[block_id]
            ):
                errors.append(f"route {route_id} block {block_id} {name} pointer drift")
            value = v1.validate_span_ref(
                span_ref,
                label=f"route {route_id} block {block_id} {name}",
                artifacts=artifacts,
                artifact_files=artifact_files,
                route_artifact_ids=route_artifact_ids,
                errors=errors,
            )
            if value is not None:
                semantic_hashes.append(value)
        for name, role in (
            ("source_code", "source-code"),
            ("target_code", "target-code"),
        ):
            v1.validate_code_span_ref(
                semantic.get(name),
                label=f"route {route_id} block {block_id} {name}",
                expected_role=role,
                artifacts=artifacts,
                artifact_files=artifact_files,
                route_artifact_ids=route_artifact_ids,
                errors=errors,
            )
        semantic_pass = semantic.get("status") == "PASSED"
        if semantic_pass and (
            len(semantic_hashes) != 3
            or len(set(semantic_hashes)) != 1
            or semantic.get("semantic_hash") != semantic_hashes[0]
        ):
            errors.append(f"route {route_id} block {block_id} semantic PASS drift")

        chunk = block.get("chunk", {})
        chunk_id = str(chunk.get("artifact_id"))
        used.add(chunk_id)
        if (
            chunk_id not in route_artifact_ids
            or artifacts.get(chunk_id, {}).get("role") != "chunk-map-v2"
        ):
            errors.append(f"route {route_id} block {block_id} chunk role/binding drift")
        chunk_pass = chunk.get("status") == "PASSED"
        chunk_path = artifact_files.get(chunk_id)
        expected_chunk_digest: str | None = None
        if chunk_path is not None:
            try:
                chunk_payload = load_json(chunk_path)
                if (
                    set(chunk_payload)
                    != {
                        "schema_version",
                        "kind",
                        "route_id",
                        "block_id",
                        "path_scheme",
                        "mappings",
                        "semantic_mappings",
                        "status",
                    }
                    or chunk_payload.get("schema_version") != 2
                    or chunk_payload.get("kind") != "frontend-chunk-map-v2"
                    or chunk_payload.get("route_id") != route_id
                    or chunk_payload.get("block_id") != block_id
                    or chunk_payload.get("path_scheme") != "rfc6901-json-pointer-v1"
                    or not isinstance(chunk_payload.get("mappings"), list)
                    or len(chunk_payload["mappings"]) != chunk.get("mapping_count")
                    or not isinstance(chunk_payload.get("semantic_mappings"), list)
                    or len(chunk_payload["semantic_mappings"])
                    != chunk.get("semantic_mapping_count")
                    or chunk_payload.get("status") != chunk.get("status")
                ):
                    errors.append(
                        f"route {route_id} block {block_id} chunk linkage drift"
                    )
                if isinstance(chunk_payload.get("mappings"), list):
                    expected_chunk_digest = v1.canonical_digest(
                        chunk_payload["mappings"]
                    )
                    raw_by_pointer: dict[str, dict[str, Any]] = {}
                    for index, mapping in enumerate(chunk_payload["mappings"]):
                        label = f"route {route_id} block {block_id} raw chunk {index}"
                        if not isinstance(mapping, dict) or set(mapping) != {
                            "pointer",
                            "pointer_standard",
                            "block_id",
                            "source",
                            "target",
                            "canonical_subtree_hash",
                            "source_subtree_hash",
                            "target_subtree_hash",
                            "equivalent",
                        }:
                            errors.append(f"{label} key closure drift")
                            continue
                        pointer = mapping.get("pointer")
                        if (
                            not isinstance(pointer, str)
                            or pointer in raw_by_pointer
                            or mapping.get("pointer_standard") != "RFC6901"
                            or mapping.get("block_id") != block_id
                        ):
                            errors.append(f"{label} pointer identity drift")
                            continue
                        try:
                            v1.pointer_tokens(pointer)
                        except Exception:
                            errors.append(f"{label} is not RFC6901")
                        raw_by_pointer[pointer] = mapping
                        subtree_hashes = [
                            mapping.get(name)
                            for name in (
                                "canonical_subtree_hash",
                                "source_subtree_hash",
                                "target_subtree_hash",
                            )
                        ]
                        if mapping.get("equivalent") is True and (
                            len(set(subtree_hashes)) != 1
                            or not isinstance(subtree_hashes[0], str)
                        ):
                            errors.append(f"{label} equivalent hash drift")
                else:
                    raw_by_pointer = {}
                semantic_mappings = unique_index(
                    chunk_payload.get("semantic_mappings"),
                    "pointer",
                    f"route {route_id} block {block_id} semantic chunk",
                    errors,
                )
                if set(semantic_mappings) != set(EXPECTED_MODEL_INFLUENCE[block_id]):
                    errors.append(
                        f"route {route_id} block {block_id} semantic pointer closure drift"
                    )
                for pointer, mapping in semantic_mappings.items():
                    if set(mapping) != {
                        "pointer",
                        "canonical_ir",
                        "source_relift_ir",
                        "target_relift_ir",
                        "source_code",
                        "target_code",
                        "semantic_hash",
                        "model_influence",
                        "runtime_influence",
                        "status",
                    }:
                        errors.append(
                            f"route {route_id} block {block_id} chunk {pointer} key closure drift"
                        )
                    pointer_hashes: list[str] = []
                    for name in (
                        "canonical_ir",
                        "source_relift_ir",
                        "target_relift_ir",
                    ):
                        span_ref = mapping.get(name)
                        if (
                            not isinstance(span_ref, dict)
                            or span_ref.get("pointer") != pointer
                        ):
                            errors.append(
                                f"route {route_id} block {block_id} chunk {pointer} {name} pointer drift"
                            )
                        value = v1.validate_span_ref(
                            span_ref,
                            label=(
                                f"route {route_id} block {block_id} chunk {pointer} {name}"
                            ),
                            artifacts=artifacts,
                            artifact_files=artifact_files,
                            route_artifact_ids=route_artifact_ids,
                            errors=errors,
                        )
                        if value is not None:
                            pointer_hashes.append(value)
                    for name, role in (
                        ("source_code", "source-code"),
                        ("target_code", "target-code"),
                    ):
                        v1.validate_code_span_ref(
                            mapping.get(name),
                            label=(
                                f"route {route_id} block {block_id} chunk {pointer} {name}"
                            ),
                            expected_role=role,
                            artifacts=artifacts,
                            artifact_files=artifact_files,
                            route_artifact_ids=route_artifact_ids,
                            errors=errors,
                        )
                    raw = raw_by_pointer.get(pointer, {})
                    code_link_ok = True
                    for endpoint, code_key in (
                        ("source", "source_code"),
                        ("target", "target_code"),
                    ):
                        raw_span = raw.get(endpoint, {})
                        code_span = mapping.get(code_key, {})
                        code_ref = (
                            artifacts.get(str(code_span.get("artifact_id")), {})
                            if isinstance(code_span, dict)
                            else {}
                        )
                        if (
                            not isinstance(raw_span, dict)
                            or not isinstance(code_span, dict)
                            or code_span.get("start") != raw_span.get("start_byte")
                            or code_span.get("end") != raw_span.get("end_byte")
                            or code_span.get("sha256") != raw_span.get("content_hash")
                            or raw_span.get("subtree_hash")
                            != raw.get("canonical_subtree_hash")
                            or not str(code_ref.get("path", "")).endswith(
                                "/" + str(raw_span.get("path"))
                            )
                        ):
                            code_link_ok = False
                    if (
                        mapping.get("model_influence")
                        != EXPECTED_MODEL_INFLUENCE[block_id].get(pointer)
                        or mapping.get("runtime_influence")
                        != expected_runtime_influence(block_id).get(pointer)
                        or mapping.get("status") != "PASSED"
                        or len(pointer_hashes) != 3
                        or len(set(pointer_hashes)) != 1
                        or mapping.get("semantic_hash") != pointer_hashes[0]
                        or raw.get("canonical_subtree_hash") != pointer_hashes[0]
                        or not code_link_ok
                    ):
                        errors.append(
                            f"route {route_id} block {block_id} chunk {pointer} semantic linkage drift"
                        )
                if chunk_pass and (
                    not raw_by_pointer
                    or not semantic_mappings
                    or any(
                        row.get("equivalent") is not True
                        for row in raw_by_pointer.values()
                    )
                ):
                    errors.append(
                        f"route {route_id} block {block_id} chunk PASS lacks exact mappings"
                    )
            except Exception as exc:
                errors.append(
                    f"route {route_id} block {block_id} chunk artifact invalid: {exc}"
                )

        behavior = block.get("model_behavior", {})
        behavior_id = str(behavior.get("artifact_id"))
        used.add(behavior_id)
        if (
            behavior_id not in route_artifact_ids
            or artifacts.get(behavior_id, {}).get("role") != "model-behavior-v2"
        ):
            errors.append(
                f"route {route_id} block {block_id} model behavior role/binding drift"
            )
        model_behavior_pass = behavior.get("status") == "PASSED"
        behavior_path = artifact_files.get(behavior_id)
        expected_behavior_digest: str | None = None
        canonical_runtime_cases: dict[str, dict[str, Any]] = {}
        if behavior_path is not None:
            try:
                payload = load_json(behavior_path)
                cases = payload.get("cases")
                case_index = unique_index(
                    cases,
                    "scenario_id",
                    f"route {route_id} block {block_id} model scenario",
                    errors,
                )
                passed = 0
                if list(case_index) != scenario_ids:
                    errors.append(
                        f"route {route_id} block {block_id} model scenario closure drift"
                    )
                for scenario_id, case in case_index.items():
                    if isinstance(case.get("canonical"), dict):
                        canonical_runtime_cases[scenario_id] = case["canonical"]
                    observations = [
                        case.get(name)
                        for name in ("canonical", "reference", "source", "target")
                    ]
                    if case.get("status") == "PASSED" and all(
                        item == observations[0] for item in observations[1:]
                    ):
                        passed += 1
                    elif case.get("status") == "PASSED":
                        errors.append(
                            f"route {route_id} block {block_id} scenario {scenario_id} model PASS drift"
                        )
                expected_behavior_digest = v1.canonical_digest(
                    [
                        {
                            "scenario_id": scenario_id,
                            "observation": case_index[scenario_id].get("canonical"),
                        }
                        for scenario_id in scenario_ids
                        if scenario_id in case_index
                    ]
                )
                if (
                    payload.get("route_id") != route_id
                    or payload.get("block_id") != block_id
                    or payload.get("runtime_kind") != "RELIFTED_MODEL_INTERPRETER"
                    or payload.get("independent") is not False
                    or behavior.get("scenario_count") != len(case_index)
                    or behavior.get("pass_count") != passed
                    or behavior.get("scenario_manifest_sha256") != scenario_digest
                ):
                    errors.append(
                        f"route {route_id} block {block_id} model behavior linkage drift"
                    )
                if model_behavior_pass and (
                    not case_index or passed != len(case_index)
                ):
                    errors.append(
                        f"route {route_id} block {block_id} zero/incomplete model behavior cannot PASS"
                    )
            except Exception as exc:
                errors.append(
                    f"route {route_id} block {block_id} model behavior invalid: {exc}"
                )

        formal = block.get("formal", {})
        formal_status = str(formal.get("status"))
        formal_statuses.append(formal_status)
        expected_symbol = f"diff_{BLOCK_SYMBOL_MAP[block_id]}"
        if formal.get("obligation_symbol") != expected_symbol:
            errors.append(f"route {route_id} block {block_id} obligation symbol drift")
        formal_ids = {
            key: str(formal.get(key))
            for key in (
                "formal_input_artifact_id",
                "smt_artifact_id",
                "solver_result_artifact_id",
                "solver_binary_artifact_id",
                "vacuity_input_artifact_id",
                "vacuity_result_artifact_id",
                "block_result_artifact_id",
                "composition_artifact_id",
                "layered_result_artifact_id",
            )
        }
        expected_engine_ids = {
            "formal_input_artifact_id": engine_path_ids.get(
                str(engine_route.get("formal_input_path"))
            ),
            "smt_artifact_id": engine_path_ids.get(
                str(engine_route.get("solver_input_path"))
            ),
            "solver_result_artifact_id": engine_path_ids.get(
                str(engine_route.get("solver_result_path"))
            ),
            "vacuity_input_artifact_id": engine_path_ids.get(
                str(engine_route.get("vacuity_input_path"))
            ),
            "vacuity_result_artifact_id": engine_path_ids.get(
                str(engine_route.get("vacuity_solver_result_path"))
            ),
            "block_result_artifact_id": engine_path_ids.get(
                str(engine_route.get("block_results_path"))
            ),
            "composition_artifact_id": engine_path_ids.get(
                str(engine_route.get("composition_path"))
            ),
            "layered_result_artifact_id": engine_path_ids.get(
                str(engine_route.get("evidence_path"))
            ),
        }
        if any(
            formal_ids[key] != identifier
            for key, identifier in expected_engine_ids.items()
        ):
            errors.append(
                f"route {route_id} block {block_id} formal artifacts are not the exact frozen engine outputs"
            )
        used.update(formal_ids.values())
        for key, identifier in formal_ids.items():
            if identifier not in route_artifact_ids or identifier not in artifacts:
                errors.append(
                    f"route {route_id} block {block_id} {key} is not route-bound"
                )
        digest_links = (
            ("formal_input_artifact_id", "formal_input_sha256"),
            ("smt_artifact_id", "solver_input_sha256"),
            ("solver_result_artifact_id", "solver_result_sha256"),
            ("solver_binary_artifact_id", "solver_binary_sha256"),
            ("vacuity_input_artifact_id", "vacuity_input_sha256"),
            ("vacuity_result_artifact_id", "vacuity_result_sha256"),
            ("block_result_artifact_id", "block_result_sha256"),
            ("composition_artifact_id", "composition_sha256"),
            ("layered_result_artifact_id", "layered_result_sha256"),
        )
        for id_key, digest_key in digest_links:
            if artifacts.get(formal_ids[id_key], {}).get("sha256") != formal.get(
                digest_key
            ):
                errors.append(
                    f"route {route_id} block {block_id} {digest_key} linkage drift"
                )
        expected_roles = {
            "formal_input_artifact_id": "engine-formal-input-v2",
            "smt_artifact_id": "engine-smt-input-v2",
            "solver_result_artifact_id": "engine-solver-result-v2",
            "solver_binary_artifact_id": "solver-binary-environment",
            "vacuity_input_artifact_id": "engine-vacuity-input-v2",
            "vacuity_result_artifact_id": "engine-vacuity-result-v2",
            "block_result_artifact_id": "engine-block-results-v2",
            "composition_artifact_id": "engine-composition-v2",
            "layered_result_artifact_id": "engine-layered-result-v2",
        }
        for id_key, expected_role in expected_roles.items():
            if artifacts.get(formal_ids[id_key], {}).get("role") != expected_role:
                errors.append(f"route {route_id} block {block_id} {id_key} role drift")
        if (
            artifacts.get(formal_ids["solver_binary_artifact_id"], {}).get("role")
            != "solver-binary-environment"
            or formal.get("solver_binary_sha256") != v1.LOCKED_Z3_BINARY_SHA256
            or formal.get("solver_binary_bytes")
            != artifacts.get(formal_ids["solver_binary_artifact_id"], {}).get("bytes")
        ):
            errors.append(f"route {route_id} block {block_id} solver binary drift")
        main_solver = validate_solver_artifact(
            label=f"route {route_id} block {block_id} main",
            route_id=route_id,
            result_id=formal_ids["solver_result_artifact_id"],
            smt_id=formal_ids["smt_artifact_id"],
            formal_input_digest=str(formal.get("formal_input_sha256")),
            expected_outcome="UNSAT",
            expected_proof_status=formal_status,
            expected_unconditional_proof=formal_status == "PROVED",
            assumptions=engine_assumptions,
            solver_binary_id=formal_ids["solver_binary_artifact_id"],
            artifacts=artifacts,
            artifact_files=artifact_files,
            execute_solver_replay=execute_solver_replay,
            errors=errors,
        )
        vacuity_solver = validate_solver_artifact(
            label=f"route {route_id} block {block_id} vacuity",
            route_id=route_id,
            result_id=formal_ids["vacuity_result_artifact_id"],
            smt_id=formal_ids["vacuity_input_artifact_id"],
            formal_input_digest=str(formal.get("formal_input_sha256")),
            expected_outcome="SAT",
            expected_proof_status="REFUTED",
            expected_unconditional_proof=False,
            assumptions=[],
            solver_binary_id=formal_ids["solver_binary_artifact_id"],
            artifacts=artifacts,
            artifact_files=artifact_files,
            execute_solver_replay=execute_solver_replay,
            errors=errors,
            vacuity=True,
        )
        for artifact_key, artifact_label in (
            ("composition_artifact_id", "composition"),
            ("layered_result_artifact_id", "layered result"),
        ):
            claim_path = artifact_files.get(formal_ids[artifact_key])
            if claim_path is None:
                continue
            try:
                claim = load_json(claim_path)
            except Exception as exc:
                errors.append(
                    f"route {route_id} block {block_id} {artifact_label} is invalid: {exc}"
                )
                continue
            if claim.get("status") != formal_status:
                errors.append(
                    f"route {route_id} block {block_id} {artifact_label} formal status drift"
                )
        block_result_path = artifact_files.get(formal_ids["block_result_artifact_id"])
        block_row: dict[str, Any] = {}
        if block_result_path is not None:
            try:
                block_payload = load_json(block_result_path)
                rows = unique_index(
                    block_payload.get("blocks"),
                    "block_id",
                    f"route {route_id} formal block result",
                    errors,
                )
                if tuple(rows) != BLOCK_IDS:
                    errors.append(
                        f"route {route_id} formal block-result closure is not 12/12"
                    )
                block_row = rows.get(block_id, {})
            except Exception as exc:
                errors.append(f"route {route_id} block results invalid: {exc}")
        influences = block_row.get("influence_classes", {})
        expected_model_matrix = EXPECTED_MODEL_INFLUENCE[block_id]
        expected_runtime_matrix = expected_runtime_influence(block_id)
        if (
            not isinstance(influences, dict)
            or influences.get("model") != expected_model_matrix
            or influences.get("runtime") != expected_runtime_matrix
        ):
            errors.append(
                f"route {route_id} block {block_id} producer-reported influence matrix drift"
            )
        model_max = max_model_influence(
            influences.get("model") if isinstance(influences, dict) else None
        )
        runtime_max = max_runtime_influence(
            influences.get("model") if isinstance(influences, dict) else None,
            influences.get("runtime") if isinstance(influences, dict) else None,
        )
        if formal.get("model_influence_max") != model_max:
            errors.append(
                f"route {route_id} block {block_id} model influence maximum drift"
            )
        if formal.get("runtime_influence_max") != runtime_max:
            errors.append(
                f"route {route_id} block {block_id} runtime influence maximum drift"
            )
        if block_row.get("model_influence_max") != max_model_influence(
            expected_model_matrix
        ) or block_row.get("runtime_influence_max") != max_runtime_influence(
            expected_model_matrix, expected_runtime_matrix
        ):
            errors.append(
                f"route {route_id} block {block_id} block-result influence aggregate drift"
            )
        if block_row:
            if set(block_row) != BLOCK_RESULT_KEYS:
                errors.append(
                    f"route {route_id} block {block_id} block-result key closure drift"
                )
            for key, expected in (
                ("block_id", block_id),
                ("obligation_symbol", expected_symbol),
                ("formal_input_digest", formal.get("formal_input_sha256")),
                ("solver_input_digest", formal.get("solver_input_sha256")),
                ("solver_result_digest", formal.get("solver_result_sha256")),
                ("vacuity_input_digest", formal.get("vacuity_input_sha256")),
                (
                    "vacuity_solver_result_digest",
                    formal.get("vacuity_result_sha256"),
                ),
                ("formal_status", formal_status),
                ("semantic_status", semantic.get("status")),
                ("chunk_status", chunk.get("status")),
                ("model_behavior_status", behavior.get("status")),
                ("raw_solver_status", main_solver.get("proof_status")),
                ("assumption_precheck", formal.get("assumption_precheck")),
                (
                    "declaration_echo_excluded_from_behavior_denominator",
                    True,
                ),
                ("runtime_evidence_eligibility", "INELIGIBLE_SAME_PRODUCER"),
                ("runtime_status", "NOT_RUN"),
                ("oracle_provenance", "NOT_INDEPENDENT_SINGLE_ENGINE"),
                ("status", formal_status),
                ("mutation_campaign_digest", engine_mutation_digest),
            ):
                if block_row.get(key) != expected:
                    errors.append(
                        f"route {route_id} block {block_id} block-result {key} drift"
                    )
            if len(semantic_hashes) == 3 and (
                block_row.get("canonical_block_digest") != semantic_hashes[0]
                or block_row.get("source_block_digest") != semantic_hashes[1]
                or block_row.get("target_block_digest") != semantic_hashes[2]
            ):
                errors.append(
                    f"route {route_id} block {block_id} semantic/block-result digest drift"
                )
            if block_row.get("behavior_block_digest") != expected_behavior_digest:
                errors.append(
                    f"route {route_id} block {block_id} behavior block digest drift"
                )
            if block_row.get("chunk_block_digest") != expected_chunk_digest:
                errors.append(
                    f"route {route_id} block {block_id} chunk block digest drift"
                )
        eligible_model = model_max in {"TRANSITION", "OBSERVABLE_EFFECT"}
        proof_pass = formal_status in FORMAL_PASS
        if proof_pass and (
            not semantic_pass
            or not chunk_pass
            or not model_behavior_pass
            or not eligible_model
            or formal.get("declaration_echo_excluded") is not True
            or formal.get("assumption_precheck") != "SAT_NON_VACUOUS_DOMAIN"
            or formal.get("replay_status") != "PASSED"
            or block_row.get("semantic_mutant_detected") is not True
            or block_row.get("behavior_mutant_detected") is not True
            or main_solver.get("outcome") != "UNSAT"
            or vacuity_solver.get("outcome") != "SAT"
        ):
            errors.append(
                f"route {route_id} block {block_id} proof lacks transition/effect, mutation, vacuity or replay closure"
            )
        expected_proof_strength = formal_proof_contract_v2(
            proof_status=formal_status,
            unconditional_proof=formal_status == "PROVED",
            assumptions=formal.get("assumptions"),
            unsupported_semantics=formal.get("unsupported_semantics"),
            label=f"route {route_id} block {block_id} wrapper",
            errors=errors,
        )
        if formal.get("proof_strength") != expected_proof_strength:
            errors.append(
                f"route {route_id} block {block_id} proof strength drift"
            )
        if formal.get("assumptions") != engine_assumptions:
            errors.append(
                f"route {route_id} block {block_id} proof assumption closure drift"
            )
        if formal_status != "PROVED":
            unconditional = False

        runtime = block.get("runtime", {})
        if runtime.get("toolchain_evidence_artifact_id") != toolchain_artifact_id:
            errors.append(
                f"route {route_id} block {block_id} toolchain artifact linkage drift"
            )
        endpoint_states: dict[str, dict[str, str]] = {}
        endpoint_actual_digests: dict[str, dict[str, dict[str, str]]] = {}
        for endpoint, profile_id in (("source", source_id), ("target", target_id)):
            endpoint_value = runtime.get(endpoint, {})
            if (
                not isinstance(endpoint_value, dict)
                or endpoint_value.get("profile_id") != profile_id
                or endpoint_value.get("required_runtime_channels")
                != list(REQUIRED_RUNTIME_CHANNELS[profile_id])
            ):
                errors.append(
                    f"route {route_id} block {block_id} {endpoint} runtime applicability drift"
                )
                endpoint_value = {}
            channels = endpoint_value.get("channels", {})
            endpoint_states[endpoint] = {}
            endpoint_actual_digests[endpoint] = {}
            for channel in RUNTIME_CHANNELS:
                channel_value = channels.get(channel) if isinstance(channels, dict) else None
                state = validate_channel_observation(
                    route_id=route_id,
                    block_id=block_id,
                    endpoint=endpoint,
                    profile_id=profile_id,
                    value=channel_value,
                    expected_channel=channel,
                    scenario_ids=scenario_ids,
                    toolchain_artifact_id=toolchain_artifact_id,
                    artifacts=artifacts,
                    artifact_files=artifact_files,
                    used=used,
                    errors=errors,
                )
                endpoint_states[endpoint][channel] = state
                digests = (
                    channel_value.get("observation_actual_digests")
                    if isinstance(channel_value, dict)
                    else None
                )
                endpoint_actual_digests[endpoint][channel] = (
                    {
                        scenario_id: str(digests[index])
                        for index, scenario_id in enumerate(scenario_ids)
                    }
                    if state == "PASSED"
                    and isinstance(digests, list)
                    and len(digests) == len(scenario_ids)
                    else {}
                )
                if (
                    channel == "browser"
                    and channel in REQUIRED_RUNTIME_CHANNELS[profile_id]
                ):
                    browser_states.append(state)
                if (
                    channel != "browser"
                    and channel in REQUIRED_RUNTIME_CHANNELS[profile_id]
                ):
                    native_states.append(state)
                if channel in REQUIRED_RUNTIME_CHANNELS[profile_id]:
                    runtime_states.append(state)
        cross = runtime.get("cross_channel_equivalence", {})
        cross_id = str(cross.get("artifact_id"))
        used.add(cross_id)
        required_pairs = len(REQUIRED_RUNTIME_CHANNELS[source_id]) * len(
            REQUIRED_RUNTIME_CHANNELS[target_id]
        )
        required_union = [
            channel
            for channel in RUNTIME_CHANNELS
            if channel
            in set(REQUIRED_RUNTIME_CHANNELS[source_id])
            | set(REQUIRED_RUNTIME_CHANNELS[target_id])
        ]
        expected_comparisons = required_pairs * len(scenario_ids)
        if (
            cross_id not in route_artifact_ids
            or artifacts.get(cross_id, {}).get("role") != "cross-channel-equivalence-v2"
            or cross.get("required_channel_union") != required_union
            or cross.get("required_pair_count") != required_pairs
            or cross.get("scenario_count") != len(scenario_ids)
            or cross.get("comparison_count") != expected_comparisons
            or artifacts.get(str(cross.get("projection_policy_artifact_id")), {}).get(
                "role"
            )
            != "runtime-canonical-projection-policy-v2"
        ):
            errors.append(
                f"route {route_id} block {block_id} cross-channel closure drift"
            )
        cross_path = artifact_files.get(cross_id)
        cross_pass_count = 0
        projection_id = str(cross.get("projection_policy_artifact_id"))
        used.add(projection_id)
        projection_path = artifact_files.get(projection_id)
        if projection_path is None:
            errors.append(
                f"route {route_id} block {block_id} runtime projection policy missing"
            )
        else:
            try:
                projection_policy = load_json(projection_path)
            except Exception as exc:
                errors.append(
                    f"route {route_id} block {block_id} runtime projection policy invalid: {exc}"
                )
            else:
                if (
                    projection_policy != expected_runtime_projection_policy()
                    or cross.get("projection_policy_fingerprint")
                    != v1.canonical_digest(projection_policy)
                ):
                    errors.append(
                        f"route {route_id} block {block_id} runtime projection policy drift"
                    )
        if cross_path is not None:
            try:
                cross_payload = load_json(cross_path)
                if set(cross_payload) != {
                    "schema_version",
                    "kind",
                    "route_id",
                    "block_id",
                    "required_channel_union",
                    "scenario_ids",
                    "comparisons",
                    "projection_policy_artifact_id",
                    "projection_policy_fingerprint",
                    "dimension_closure",
                    "status",
                }:
                    errors.append(
                        f"route {route_id} block {block_id} cross-channel key closure drift"
                    )
                comparisons = cross_payload.get("comparisons")
                expected_keys = {
                    (source_channel, target_channel, scenario_id)
                    for source_channel in REQUIRED_RUNTIME_CHANNELS[source_id]
                    for target_channel in REQUIRED_RUNTIME_CHANNELS[target_id]
                    for scenario_id in scenario_ids
                }
                actual_keys: set[tuple[str, str, str]] = set()
                if not isinstance(comparisons, list):
                    comparisons = []
                for index, comparison in enumerate(comparisons):
                    if not isinstance(comparison, dict) or set(comparison) != {
                        "source_channel",
                        "target_channel",
                        "scenario_id",
                        "source_observation_digest",
                        "target_observation_digest",
                        "source_canonical_projection_digest",
                        "target_canonical_projection_digest",
                        "relation",
                        "status",
                    }:
                        errors.append(
                            f"route {route_id} block {block_id} cross comparison {index} drift"
                        )
                        continue
                    key = (
                        str(comparison.get("source_channel")),
                        str(comparison.get("target_channel")),
                        str(comparison.get("scenario_id")),
                    )
                    if key in actual_keys:
                        errors.append(
                            f"route {route_id} block {block_id} duplicate cross comparison {key}"
                        )
                    actual_keys.add(key)
                    status = comparison.get("status")
                    actual_digests = [
                        comparison.get("source_observation_digest"),
                        comparison.get("target_observation_digest"),
                    ]
                    projection_digests = [
                        comparison.get("source_canonical_projection_digest"),
                        comparison.get("target_canonical_projection_digest"),
                    ]
                    source_projection = runtime_driver_projection_v2(
                        profiles.get(source_id, {}), key[0], key[2], block_id
                    )
                    target_projection = runtime_driver_projection_v2(
                        profiles.get(target_id, {}), key[1], key[2], block_id
                    )
                    expected_projection_digests = [
                        v1.canonical_digest(source_projection)
                        if source_projection is not None
                        else None,
                        v1.canonical_digest(target_projection)
                        if target_projection is not None
                        else None,
                    ]
                    expected_actual_digests = [
                        endpoint_actual_digests["source"]
                        .get(key[0], {})
                        .get(key[2]),
                        endpoint_actual_digests["target"]
                        .get(key[1], {})
                        .get(key[2]),
                    ]
                    if status == "PASSED":
                        if (
                            comparison.get("relation")
                            != "EACH_ACTUAL_EQUALS_ITS_CHANNEL_CANONICAL_PROJECTION"
                            or projection_digests != expected_projection_digests
                            or actual_digests != expected_actual_digests
                            or actual_digests != projection_digests
                            or any(not isinstance(item, str) for item in actual_digests)
                        ):
                            errors.append(
                                f"route {route_id} block {block_id} cross PASS digest drift"
                            )
                        else:
                            cross_pass_count += 1
                    elif status == "NOT_RUN":
                        if any(
                            item is not None
                            for item in [*actual_digests, *projection_digests]
                        ):
                            errors.append(
                                f"route {route_id} block {block_id} NOT_RUN cross comparison has observations"
                            )
                    elif status == "FAILED":
                        if (
                            projection_digests != expected_projection_digests
                            or actual_digests != expected_actual_digests
                            or any(
                                not isinstance(item, str)
                                for item in [*actual_digests, *projection_digests]
                            )
                        ):
                            errors.append(
                                f"route {route_id} block {block_id} FAILED cross comparison lacks observations"
                            )
                    else:
                        errors.append(
                            f"route {route_id} block {block_id} cross comparison status is invalid"
                        )
                comparison_statuses = [
                    item.get("status") for item in comparisons if isinstance(item, dict)
                ]
                derived_cross_status = (
                    "FAILED"
                    if "FAILED" in comparison_statuses
                    else "PASSED"
                    if comparison_statuses
                    and all(item == "PASSED" for item in comparison_statuses)
                    else "NOT_RUN"
                )
                dimension_rows = {
                    "browser": [
                        row
                        for row in comparisons
                        if isinstance(row, dict)
                        and row.get("source_channel") == "browser"
                        and row.get("target_channel") == "browser"
                    ],
                    "native": [
                        row
                        for row in comparisons
                        if isinstance(row, dict)
                        and row.get("source_channel") != "browser"
                        and row.get("target_channel") != "browser"
                    ],
                    "runtime": [row for row in comparisons if isinstance(row, dict)],
                }
                expected_dimension_closure = {
                    name: {
                        "applicable": bool(rows),
                        "comparison_count": len(rows),
                        "pass_count": sum(
                            row.get("status") == "PASSED" for row in rows
                        ),
                        "status": closed_status(
                            [str(row.get("status")) for row in rows],
                            applicable=bool(rows),
                        ),
                    }
                    for name, rows in dimension_rows.items()
                }
                if (
                    cross_payload.get("schema_version") != 2
                    or cross_payload.get("kind")
                    != "frontend-cross-channel-equivalence-v2"
                    or cross_payload.get("route_id") != route_id
                    or cross_payload.get("block_id") != block_id
                    or cross_payload.get("required_channel_union") != required_union
                    or cross_payload.get("scenario_ids") != scenario_ids
                    or cross_payload.get("projection_policy_artifact_id")
                    != projection_id
                    or cross_payload.get("projection_policy_fingerprint")
                    != cross.get("projection_policy_fingerprint")
                    or cross_payload.get("dimension_closure")
                    != expected_dimension_closure
                    or cross.get("dimension_closure") != expected_dimension_closure
                    or actual_keys != expected_keys
                    or cross_payload.get("status") != cross.get("status")
                    or cross.get("status") != derived_cross_status
                    or cross.get("pass_count") != cross_pass_count
                ):
                    errors.append(
                        f"route {route_id} block {block_id} cross-channel artifact drift"
                    )
            except Exception as exc:
                errors.append(
                    f"route {route_id} block {block_id} cross-channel artifact invalid: {exc}"
                )
        all_required_pass = all(
            endpoint_states[endpoint][channel] == "PASSED"
            for endpoint, profile_id in (("source", source_id), ("target", target_id))
            for channel in REQUIRED_RUNTIME_CHANNELS[profile_id]
        )
        cross_status = str(cross.get("status"))
        if cross_status == "PASSED" and (
            not all_required_pass
            or cross.get("pass_count") != expected_comparisons
            or cross_pass_count != expected_comparisons
        ):
            errors.append(
                f"route {route_id} block {block_id} runtime PASS exceeds influence/actual evidence"
            )
        dimensions = cross.get("dimension_closure", {})
        runtime_dimension = dimensions.get("runtime", {}) if isinstance(dimensions, dict) else {}
        browser_dimension = dimensions.get("browser", {}) if isinstance(dimensions, dict) else {}
        native_dimension = dimensions.get("native", {}) if isinstance(dimensions, dict) else {}
        runtime_states.append(str(runtime_dimension.get("status", cross_status)))
        if browser_dimension.get("applicable") is True:
            browser_states.append(str(browser_dimension.get("status")))
        if native_dimension.get("applicable") is True:
            native_states.append(str(native_dimension.get("status")))

        independent = block.get("independent", {})
        independent_status = str(independent.get("status"))
        independent_states.append(independent_status)
        independent_ids = independent.get("artifact_ids")
        if isinstance(independent_ids, list):
            used.update(str(item) for item in independent_ids)
        external_result = external_capture.get("results", {}).get((route_id, block_id))
        if isinstance(external_result, dict):
            expected_independent_ids = sorted(
                {
                    *external_result.get("execution_artifact_ids", []),
                    external_result.get("replay_artifact_id"),
                    external_capture.get("authorization_artifact_id"),
                }
            )
            expected_independent = {
                "status": external_result.get("status"),
                "same_producer": False,
                "producer_fingerprint": external_capture.get("producer_fingerprint"),
                "artifact_ids": expected_independent_ids,
                "holdout_status": "PASSED",
                "representative_status": "PASSED",
                "customer_status": "PASSED",
                "authorization_artifact_id": external_capture.get(
                    "authorization_artifact_id"
                ),
                "executor_organization_id": external_capture.get(
                    "executor_organization_id"
                ),
                "verifier_organization_id": external_capture.get(
                    "verifier_organization_id"
                ),
                "replay_status": "PASSED",
            }
            if (
                independent != expected_independent
                or independent.get("producer_fingerprint")
                in {implementation_fingerprint, toolchain_producer_fingerprint}
            ):
                errors.append(
                    f"route {route_id} block {block_id} external independent evidence binding drift"
                )
        else:
            expected_independent = {
                "status": "NOT_RUN",
                "same_producer": True,
                "producer_fingerprint": implementation_fingerprint,
                "artifact_ids": [],
                "holdout_status": "NOT_RUN",
                "representative_status": "NOT_RUN",
                "customer_status": "NOT_RUN",
                "authorization_artifact_id": None,
                "executor_organization_id": None,
                "verifier_organization_id": None,
                "replay_status": "NOT_RUN",
            }
            if independent != expected_independent:
                errors.append(
                    f"route {route_id} block {block_id} same-producer independent NOT_RUN boundary drift"
                )
        model_passes.append(
            semantic_pass and chunk_pass and model_behavior_pass and proof_pass
        )

    route_formal_statuses = set(formal_statuses)
    if (
        len(formal_statuses) != 12
        or len(route_formal_statuses) != 1
        or engine_route.get("status") not in route_formal_statuses
        or engine_route.get("layered_result") not in route_formal_statuses
    ):
        errors.append(f"route {route_id} engine/wrapper formal status drift")
    model_status = (
        "PASSED"
        if len(model_passes) == 12 and all(model_passes)
        else (
            "FAILED"
            if any(status == "REFUTED" for status in formal_statuses)
            else "PARTIAL"
        )
    )
    browser_status = closed_status(browser_states)
    native_status = closed_status(native_states, applicable=bool(native_states))
    runtime_status = closed_status(runtime_states)
    independent_status = aggregate_status(independent_states)
    for key, expected in (
        ("model_formal_status", model_status),
        ("browser_status", browser_status),
        ("native_status", native_status),
        ("runtime_status", runtime_status),
        ("independent_status", independent_status),
    ):
        if route.get(key) != expected:
            errors.append(f"route {route_id} {key} aggregate drift")
    return {
        "model_formal_status": model_status,
        "browser_status": browser_status,
        "native_status": native_status,
        "runtime_status": runtime_status,
        "independent_status": independent_status,
        "unconditional": unconditional,
    }


def validate_verification_governance_v2(
    *,
    pack: Path,
    manifest: dict[str, Any],
    campaign: dict[str, Any],
    errors: list[str],
) -> None:
    pack_key = manifest.get("pack_key")
    if pack_key != "frontend-72-route-formal-equivalence-v2":
        if manifest.get("frontend_governance_v2") is not None:
            errors.append("client v2 pack must not declare verification governance")
        return
    registry_path = pack / "oracle-registry.json"
    assurance_path = pack / "assurance/assurance-case.json"
    try:
        registry = load_json(registry_path)
        assurance = load_json(assurance_path)
    except Exception as exc:
        errors.append(f"frontend v2 verification governance is unavailable: {exc}")
        return
    campaign_relative = "formal-campaign/frontend-formal-route-campaign-v2.json"
    external_status = campaign.get("external_evidence", {}).get(
        "status", "NOT_RUN"
    )
    expected_registry = {
        "schema_version": 1,
        "pack_key": "frontend-72-route-formal-equivalence-v2",
        "oracles": [
            {
                "oracle_id": "oracle.canonical-model-v2",
                "type": "formal-spec",
                "owner": "frontend-formal-verification-team",
                "scope": ["claim.behavior"],
                "independence": "dependent",
                "trust_level": "supporting",
                "version": "2.0.0",
                "status": "PASSED",
                "evidence_refs": [
                    campaign_relative,
                    "formal-campaign/oracle/provenance-graph.json",
                ],
            },
            {
                "oracle_id": "oracle.bounded-z3-v2",
                "type": "solver",
                "owner": "frontend-formal-verification-team",
                "scope": ["claim.behavior"],
                "independence": "dependent",
                "trust_level": "supporting",
                "version": "4.16.0",
                "status": "PASSED",
                "evidence_refs": [campaign_relative],
            },
            {
                "oracle_id": "oracle.external-runtime-v2",
                "type": "reference-implementation",
                "owner": "external-independent-verifier",
                "scope": ["claim.behavior"],
                "independence": "independent",
                "trust_level": "strong",
                "version": "2.0.0",
                "status": external_status,
                "evidence_refs": (
                    [
                        campaign_relative,
                        "formal-campaign/oracle/provenance-graph.json",
                    ]
                    if external_status == "PASSED"
                    else []
                ),
            },
        ],
        "precedence_rules": [
            {
                "claim_type": "behavior",
                "ordered_oracles": [
                    "oracle.external-runtime-v2",
                    "oracle.canonical-model-v2",
                    "oracle.bounded-z3-v2",
                ],
            }
        ],
        "conflicts": [],
        "approvals": [],
    }
    expected_assurance = {
        "schema_version": 1,
        "case_key": "frontend-72-route-formal-equivalence-v2-assurance-v1",
        "version": 1,
        "owner": "frontend-formal-verification-team",
        "top_claim": (
            "The exact bounded frontend interaction scope has local model "
            "evidence; production correctness remains unsupported."
        ),
        "claims": [
            {
                "claim_id": "claim.behavior",
                "statement": "Critical migrated behavior remains correct.",
                "status": "unsupported",
                "evidence_refs": [campaign_relative],
                "assumptions": list(campaign.get("assumptions", [])),
                "limitations": [
                    "Independent runtime, holdout, representative and customer evidence is NOT_RUN."
                ],
            }
        ],
        "evidence": [],
        "residual_risks": [
            {
                "risk_id": "frontend-v2-external-evidence-not-run",
                "description": "External runtime and customer qualification is absent.",
                "severity": "critical",
                "mitigation": "Run the externally trusted intake and replay protocol.",
                "owner": "frontend-formal-verification-team",
                "status": "open",
            }
        ],
        "monitoring_obligations": [],
        "approvals": [],
    }
    if registry != expected_registry:
        errors.append("frontend v2 oracle registry exact closure drift")
    if assurance != expected_assurance:
        errors.append("frontend v2 assurance case exact fail-closed closure drift")
    expected_binding = {
        "oracle_registry_sha256": v1.digest_bytes(registry_path.read_bytes()),
        "assurance_case_sha256": v1.digest_bytes(assurance_path.read_bytes()),
        "status": "PASSED" if external_status == "PASSED" else "NOT_RUN",
    }
    if manifest.get("frontend_governance_v2") != expected_binding:
        errors.append("frontend v2 governance digest/status binding drift")


def validate_campaign(
    pack: Path,
    *,
    campaign_relative: str | None = None,
    schema_path: Path | None = None,
    route_schema_path: Path | None = None,
    execute_replay: bool = True,
    portable_evidence_only: bool = False,
    external_trust_root_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        pack = pack.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return readiness_failure(["pack is missing"])
    try:
        manifest = load_json(pack / "pack.json")
    except Exception as exc:
        return readiness_failure([f"cannot load pack manifest: {exc}"])
    declaration = campaign_relative or manifest.get("frontend_formal_route_campaign_v2")
    campaign_path = v1.safe_pack_file(
        pack, declaration, "pack frontend_formal_route_campaign_v2", errors
    )
    if campaign_path is None:
        return readiness_failure(errors)
    try:
        campaign = load_json(campaign_path)
    except Exception as exc:
        return readiness_failure([f"cannot load frontend v2 campaign: {exc}"])
    validator_path = Path(__file__).resolve()
    repo_root = validator_path.parents[2]
    captured_replay = is_captured_replay(validator_path)
    schema_path = schema_path or (
        repo_root / "schemas/batch32/frontend-formal-route-campaign-v2.schema.json"
    )
    route_schema_path = route_schema_path or (
        repo_root / "schemas/batch32/frontend-formal-route-evidence-v2.schema.json"
    )
    try:
        schema = load_json(schema_path)
        route_schema = load_json(route_schema_path)
        v1_schema = load_json(
            schema_path.parent / "frontend-formal-route-campaign.schema.json"
        )
    except Exception as exc:
        return readiness_failure([f"cannot load frontend v2 schemas: {exc}"])
    validate_schema(
        campaign,
        schema,
        "frontend v2 campaign",
        errors,
        external_profile_ref=True,
    )
    if (
        campaign.get("schema_version") != 2
        or campaign.get("semantic_block_ids") != list(BLOCK_IDS)
        or campaign.get("block_symbol_map") != BLOCK_SYMBOL_MAP
        or campaign.get("profile_count") != 9
        or campaign.get("route_count") != 72
        or campaign.get("block_count") != 12
        or campaign.get("route_block_count") != 864
    ):
        errors.append("frontend v2 contract identity drift")
    allowed_pack_keys = {
        "frontend-72-route-equivalence-v2",
        "frontend-72-route-formal-equivalence-v2",
    }
    pack_key = manifest.get("pack_key")
    if pack_key not in allowed_pack_keys:
        errors.append("frontend v2 pack_key is not exact")
    validate_verification_governance_v2(
        pack=pack,
        manifest=manifest,
        campaign=campaign,
        errors=errors,
    )
    campaign_digest = v1.digest_bytes(campaign_path.read_bytes())
    if manifest.get("frontend_formal_campaign_v2_digest") != campaign_digest:
        errors.append("pack frontend v2 campaign digest mismatch")
    artifacts, artifact_files = validate_artifacts(pack, campaign, errors)
    used: set[str] = set()
    engine, engine_routes, engine_path_ids = validate_engine_artifacts(
        campaign=campaign,
        artifacts=artifacts,
        artifact_files=artifact_files,
        used=used,
        errors=errors,
    )
    if campaign.get("assumptions") != engine.get("assumptions"):
        errors.append("frontend v2 campaign/engine assumption closure drift")
    validate_engine_verifier(
        pack=pack,
        campaign=campaign,
        artifacts=artifacts,
        artifact_files=artifact_files,
        used=used,
        live_runtime_replay=not portable_evidence_only,
        errors=errors,
    )
    engine_id = str(campaign.get("engine_campaign_artifact_id"))
    used.add(engine_id)
    if artifacts.get(engine_id, {}).get("role") != "engine-campaign-v2":
        errors.append("engine campaign artifact role mismatch")

    gap_id = str(campaign.get("gap_inventory_artifact_id"))
    used.add(gap_id)
    gap_ref = artifacts.get(gap_id, {})
    gap_file = artifact_files.get(gap_id)
    gap_text: str | None = None
    readable_gap = v1.safe_pack_file(
        pack,
        "certification/gap-inventory.md",
        "frontend v2 readable gap inventory",
        errors,
    )
    if gap_ref.get("role") != "frontend-gap-inventory-v2" or gap_file is None:
        errors.append("frontend v2 gap inventory artifact linkage drift")
    elif readable_gap is not None:
        content = gap_file.read_bytes()
        if readable_gap.read_bytes() != content:
            errors.append("frontend v2 readable gap inventory copy drift")
        text = content.decode("utf-8", errors="replace")
        gap_text = text
        expected_markers = {
            f"<!-- frontend-v2-gap-row route={route_id} block={block_id} -->"
            for route_id in exact_routes()
            for block_id in BLOCK_IDS
        }
        actual_markers = {
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("<!-- frontend-v2-gap-row route=")
        }
        if actual_markers != expected_markers:
            errors.append("frontend v2 readable gap inventory is not exact 864 rows")
        actual_rows = {
            line.strip()
            for line in text.splitlines()
            if any(line.startswith(f"| {route_id} |") for route_id in exact_routes())
        }
        if len(actual_rows) != 72 * len(BLOCK_IDS):
            errors.append("frontend v2 readable gap inventory status row count drift")
        for dimension in (
            "model",
            "formal",
            "browser",
            "android",
            "ios",
            "harmonyos",
            "runtime",
            "independent",
            "holdout",
            "representative",
        ):
            if f"| {dimension} |" not in text:
                errors.append(f"frontend v2 gap inventory omits {dimension} dimension")

    scenario = campaign.get("scenario_manifest", {})
    scenario_id = str(scenario.get("artifact_id"))
    used.add(scenario_id)
    scenario_ref = artifacts.get(scenario_id, {})
    scenario_ids = scenario.get("scenario_ids")
    if not isinstance(scenario_ids, list):
        scenario_ids = []
    if (
        scenario_ref.get("role") != "scenario-manifest-v2"
        or scenario_ref.get("sha256") != scenario.get("sha256")
        or scenario_ref.get("bytes") != scenario.get("bytes")
        or scenario.get("scenario_count") != len(scenario_ids)
        or len(set(scenario_ids)) != len(scenario_ids)
    ):
        errors.append("scenario manifest digest/count closure drift")
    scenario_file = artifact_files.get(scenario_id)
    scenario_inputs: dict[str, dict[str, Any]] = {}
    if scenario_file is not None:
        try:
            scenario_payload = load_json(scenario_file)
            payload_scenario_ids = scenario_payload.get("scenario_ids")
            if payload_scenario_ids is None and isinstance(
                scenario_payload.get("scenarios"), list
            ):
                payload_scenario_ids = [
                    row.get("scenarioId")
                    for row in scenario_payload["scenarios"]
                    if isinstance(row, dict)
                ]
            payload_scenario_count = scenario_payload.get(
                "scenario_count", len(payload_scenario_ids or [])
            )
            payload_input_schema = scenario_payload.get(
                "input_schema", scenario.get("input_schema")
            )
            if (
                payload_scenario_ids != scenario_ids
                or payload_scenario_count != len(scenario_ids)
                or payload_input_schema != scenario.get("input_schema")
            ):
                errors.append("scenario manifest payload drift")
            scenario_inputs = scenario_inputs_from_payload(
                scenario_payload, scenario_ids, errors
            )
        except Exception as exc:
            errors.append(f"scenario manifest is invalid: {exc}")

    expected_profiles = v1.expected_profiles(v1_schema)
    engine_profile_by_id = unique_index(
        engine.get("profiles"), "profile_id", "engine profile", errors
    )
    unique_index(campaign.get("profiles"), "profile_digest", "profile", errors)
    profile_by_id: dict[str, dict[str, Any]] = {}
    for record in campaign.get("profiles", []):
        if not isinstance(record, dict):
            continue
        profile = record.get("profile")
        if not isinstance(profile, dict):
            errors.append("profile identity is missing")
            continue
        profile_id = str(profile.get("id"))
        if profile_id in profile_by_id:
            errors.append(f"duplicate profile id: {profile_id}")
        profile_by_id[profile_id] = record
        if expected_profiles.get(profile_id) != profile:
            errors.append(f"profile tuple drift: {profile_id}")
        if record.get("profile_digest") != v1.canonical_digest(profile):
            errors.append(f"profile digest drift: {profile_id}")
        if record.get("required_runtime_channels") != list(
            REQUIRED_RUNTIME_CHANNELS.get(profile_id, ())
        ):
            errors.append(f"profile runtime channel applicability drift: {profile_id}")
        engine_profile = engine_profile_by_id.get(profile_id, {})
        engine_manifest_id = engine_path_ids.get(
            str(engine_profile.get("manifest_path"))
        )
        if (
            record.get("engine_profile_artifact_id") != engine_manifest_id
            or engine_profile.get("framework_version")
            != profile.get("framework_version")
            or engine_profile.get("platforms") != profile.get("platforms")
            or engine_profile.get("required_runtime_channels")
            != list(REQUIRED_RUNTIME_CHANNELS.get(profile_id, ()))
            or record.get("project_digest") != engine_profile.get("project_digest")
            or record.get("manifest_digest") != engine_profile.get("manifest_digest")
            or record.get("source_fixture_digest")
            != engine_profile.get("source_fixture_digest")
            or record.get("relift_model_digest")
            != engine_profile.get("relift_model_digest")
            or record.get("relift_block_digests")
            != engine_profile.get("relift_block_digests")
            or record.get("runtime_driver_contract")
            != engine_profile.get("runtime_driver_contract")
            or record.get("runtime_driver_contract_digest")
            != v1.canonical_digest(record.get("runtime_driver_contract"))
        ):
            errors.append(f"profile engine identity/relift closure drift: {profile_id}")
        validate_runtime_driver_contract_v2(
            profile_id=profile_id,
            profile_record=record,
            scenario_ids=scenario_ids,
            errors=errors,
        )
        artifact_ids = record.get("artifact_ids")
        if not isinstance(artifact_ids, list):
            errors.append(f"profile artifact ids invalid: {profile_id}")
            artifact_ids = []
        used.update(str(item) for item in artifact_ids)
        project_files = record.get("project_files")
        if not isinstance(project_files, list):
            errors.append(f"profile project files invalid: {profile_id}")
            continue
        project_map: dict[str, str] = {}
        seen_relative: set[str] = set()
        project_file_ids: set[str] = set()
        for row in project_files:
            if not isinstance(row, dict):
                errors.append(f"profile project file invalid: {profile_id}")
                continue
            relative = row.get("relative_path")
            artifact_id = str(row.get("artifact_id"))
            if not isinstance(relative, str) or relative in seen_relative:
                errors.append(f"profile project path duplicate/invalid: {profile_id}")
                continue
            seen_relative.add(relative)
            project_file_ids.add(artifact_id)
            path = artifact_files.get(artifact_id)
            if path is None:
                errors.append(
                    f"profile project artifact missing: {profile_id}/{relative}"
                )
                continue
            try:
                project_map[relative] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append(f"profile project artifact is not UTF-8: {profile_id}")
        if not project_file_ids.issubset(set(str(item) for item in artifact_ids)):
            errors.append(f"profile project artifact closure drift: {profile_id}")
        if record.get("project_digest") != v1.canonical_digest(project_map):
            errors.append(f"profile project digest drift: {profile_id}")
        expected_profile_artifacts = {
            identifier
            for relative, identifier in engine_path_ids.items()
            if relative.startswith(f"profiles/{profile_id}/project/")
            or relative
            in {
                str(engine_profile.get("manifest_path")),
                str(engine_profile.get("source_fixture_path")),
            }
        }
        if set(str(item) for item in artifact_ids) != expected_profile_artifacts:
            errors.append(f"profile artifact closure drift: {profile_id}")
    if set(profile_by_id) != set(PROFILE_IDS):
        errors.append("frontend v2 profile closure is not exact nine")

    implementation = campaign.get("implementation")
    replay = campaign.get("replay")
    validate_bundle(
        name="implementation",
        bundle=implementation,
        required_paths=REQUIRED_IMPLEMENTATION_REPOSITORY_PATHS,
        manifest_role="implementation-manifest-v2",
        artifacts=artifacts,
        artifact_files=artifact_files,
        used=used,
        repo_root=repo_root,
        require_live=not captured_replay and not portable_evidence_only,
        errors=errors,
    )
    validate_bundle(
        name="replay",
        bundle=replay,
        required_paths=REQUIRED_REPLAY_REPOSITORY_PATHS,
        manifest_role="replay-manifest-v2",
        artifacts=artifacts,
        artifact_files=artifact_files,
        used=used,
        repo_root=repo_root,
        require_live=not captured_replay and not portable_evidence_only,
        errors=errors,
    )

    toolchain = campaign.get("toolchain_evidence", {})
    runtime_projection = campaign.get("runtime_projection", {})
    projection_id = (
        str(runtime_projection.get("artifact_id"))
        if isinstance(runtime_projection, dict)
        else ""
    )
    used.add(projection_id)
    projection_path = artifact_files.get(projection_id)
    if (
        artifacts.get(projection_id, {}).get("role")
        != "runtime-canonical-projection-policy-v2"
        or projection_path is None
    ):
        errors.append("frontend v2 runtime projection declaration is missing")
    else:
        try:
            projection_payload = load_json(projection_path)
        except Exception as exc:
            errors.append(f"frontend v2 runtime projection is invalid: {exc}")
        else:
            if (
                projection_payload != expected_runtime_projection_policy()
                or runtime_projection.get("fingerprint")
                != v1.canonical_digest(projection_payload)
            ):
                errors.append("frontend v2 runtime projection declaration drift")
    toolchain_id_value = toolchain.get("artifact_id")
    toolchain_id = toolchain_id_value if isinstance(toolchain_id_value, str) else None
    if toolchain_id is not None:
        used.add(toolchain_id)
        reference = artifacts.get(toolchain_id, {})
        if (
            reference.get("role") != "toolchain-evidence-v2"
            or reference.get("sha256") != toolchain.get("artifact_sha256")
            or reference.get("bytes") != toolchain.get("artifact_bytes")
        ):
            errors.append("toolchain v2 artifact digest/bytes drift")
    if toolchain.get("scenario_manifest_sha256") != scenario.get("sha256"):
        errors.append("toolchain v2 scenario manifest binding drift")
    if (
        toolchain.get("profile_binding_count") != 9
        or toolchain.get("route_binding_count") != 72
        or toolchain.get("block_binding_count") != 864
        or toolchain.get("boundaries")
        != {
            "build_is_behavior": False,
            "model_is_runtime": False,
            "same_producer_is_independent": False,
            "certification": "NOT_CERTIFIED",
        }
    ):
        errors.append("toolchain v2 declared closure/boundaries drift")

    validate_toolchain_evidence_v2(
        raw_path=(
            artifact_files.get(toolchain_id) if toolchain_id is not None else None
        ),
        engine_campaign_path=artifact_files.get(engine_id),
        campaign=campaign,
        profile_records=profile_by_id,
        scenario_ids=scenario_ids,
        scenario_inputs=scenario_inputs,
        scenario_digest=str(scenario.get("sha256")),
        implementation=implementation,
        artifacts=artifacts,
        artifact_files=artifact_files,
        errors=errors,
    )

    corpora = campaign.get("corpora", {})
    corpus_sets: dict[str, set[str]] = {}
    for name in ("development", "negative", "holdout", "representative_workloads"):
        corpus = corpora.get(name, {}) if isinstance(corpora, dict) else {}
        manifest_id = str(corpus.get("manifest_artifact_id"))
        used.add(manifest_id)
        if artifacts.get(manifest_id, {}).get("role") != "corpus-manifest-v2":
            errors.append(f"{name} corpus manifest role mismatch")
        values = corpus.get("case_ids")
        corpus_sets[name] = set(values) if isinstance(values, list) else set()
        if corpus.get("status") == "PASSED" and not corpus_sets[name]:
            errors.append(f"{name} corpus cannot PASS with zero cases")
        manifest_path = artifact_files.get(manifest_id)
        if manifest_path is None:
            errors.append(f"{name} corpus manifest artifact is missing")
        else:
            try:
                manifest_value = load_json(manifest_path)
            except Exception as exc:
                errors.append(f"{name} corpus manifest is invalid: {exc}")
            else:
                expected_manifest = {
                    "schema_version": 2,
                    "kind": "frontend-formal-corpus-manifest-v2",
                    "corpus_kind": name,
                    "id": corpus.get("id"),
                    "status": corpus.get("status"),
                    "case_ids": values,
                    "independence_boundary": (
                        "LOCAL_ENGINE_CORPUS"
                        if name in {"development", "negative"}
                        else "EXTERNALLY_ATTESTED"
                        if corpus.get("status") == "PASSED"
                        else "INDEPENDENT_EXTERNAL_NOT_RUN"
                    ),
                }
                if manifest_value != expected_manifest:
                    errors.append(f"{name} corpus manifest linkage drift")
    names = list(corpus_sets)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            if corpus_sets[left] & corpus_sets[right]:
                errors.append(f"corpus overlap: {left}/{right}")

    preliminary_scope_digest = v1.canonical_digest(
        campaign_scope_value_v2(
            campaign,
            corpora if isinstance(corpora, dict) else {},
            runtime_projection if isinstance(runtime_projection, dict) else {},
            scenario.get("sha256"),
        )
    )
    replay_files = bundle_repository_files(replay, artifacts, artifact_files)
    external_capture = validate_external_evidence_v2(
        pack=pack,
        campaign=campaign,
        scope_digest=preliminary_scope_digest,
        artifacts=artifacts,
        artifact_files=artifact_files,
        replay_files=replay_files,
        trust_root_path=external_trust_root_path,
        used=used,
        errors=errors,
    )
    profile_channel_statuses = toolchain.get("profile_channel_statuses")
    if not isinstance(profile_channel_statuses, dict):
        profile_channel_statuses = {}
    external_declaration = campaign.get("external_evidence")
    external_independent_status = (
        str(external_declaration.get("independent_status"))
        if isinstance(external_declaration, dict)
        else "NOT_RUN"
    )
    expected_unsupported_semantics = unsupported_semantics_v2(
        arbitrary_customer_source=str(
            engine.get("arbitrary_customer_source", "NOT_PROVED")
        ),
        profile_channel_statuses=profile_channel_statuses,
        independent_status=external_independent_status,
    )
    if campaign.get("unsupported_semantics") != expected_unsupported_semantics:
        errors.append("frontend v2 unsupported-semantics derivation drift")
    independent_graph_ready = validate_oracle_graph(
        campaign, artifacts, artifact_files, used, errors
    )
    routes = unique_index(campaign.get("routes"), "route_id", "route", errors)
    if set(routes) != exact_routes():
        errors.append("frontend v2 route closure is not exact 72")
    route_results: list[dict[str, Any]] = []
    for route_id in sorted(routes):
        route_results.append(
            validate_route(
                pack=pack,
                route=routes[route_id],
                profiles=profile_by_id,
                scenario_ids=scenario_ids,
                scenario_digest=str(scenario.get("sha256")),
                route_schema=route_schema,
                artifacts=artifacts,
                artifact_files=artifact_files,
                engine_route=engine_routes.get(route_id, {}),
                engine_path_ids=engine_path_ids,
                engine_assumptions=(
                    engine.get("assumptions")
                    if isinstance(engine.get("assumptions"), list)
                    else []
                ),
                engine_mutation_digest=str(
                    engine.get("mutation_campaign", {}).get("digest")
                ),
                implementation_fingerprint=str(
                    campaign.get("implementation", {}).get("fingerprint")
                ),
                replay_fingerprint=str(campaign.get("replay", {}).get("fingerprint")),
                toolchain_artifact_id=toolchain_id,
                toolchain_producer_fingerprint=(
                    str(toolchain.get("producer_fingerprint"))
                    if toolchain.get("producer_fingerprint") is not None
                    else None
                ),
                external_capture=external_capture,
                execute_solver_replay=not portable_evidence_only,
                used=used,
                errors=errors,
            )
        )

    if gap_text is not None:
        expected_gap_rows, expected_gap_dimensions = expected_gap_inventory_v2(
            campaign, artifact_files
        )
        actual_gap_rows = {
            line.strip()
            for line in gap_text.splitlines()
            if any(line.startswith(f"| {route_id} |") for route_id in exact_routes())
        }
        if actual_gap_rows != expected_gap_rows:
            errors.append("frontend v2 readable gap inventory dynamic status rows drift")
        for dimension, status in expected_gap_dimensions.items():
            if f"| {dimension} | {status} |" not in gap_text:
                errors.append(
                    f"frontend v2 gap inventory {dimension} aggregate status drift"
                )

    scope_value = campaign_scope_value_v2(
        campaign,
        corpora if isinstance(corpora, dict) else {},
        runtime_projection if isinstance(runtime_projection, dict) else {},
        scenario.get("sha256"),
    )
    scope_digest = v1.canonical_digest(scope_value)
    expected_peer_binding = {
        "batch32_pack_key": "frontend-72-route-equivalence-v2",
        "batch35_pack_key": "frontend-72-route-formal-equivalence-v2",
        "scope_digest": scope_digest,
    }
    if campaign.get("peer_binding") != expected_peer_binding:
        errors.append("frontend v2 peer/scope binding drift")
    if manifest.get("frontend_formal_scope_v2_digest") != scope_digest:
        errors.append("pack frontend v2 scope digest drift")
    expected_peer_pack = (
        "frontend-72-route-formal-equivalence-v2"
        if pack_key == "frontend-72-route-equivalence-v2"
        else "frontend-72-route-equivalence-v2"
    )
    if manifest.get("frontend_formal_peer_v2") != {
        "pack_key": expected_peer_pack,
        "campaign_sha256": campaign_digest,
        "scope_digest": scope_digest,
    }:
        errors.append("pack frontend v2 peer binding drift")

    missing = sorted(used - set(artifacts))
    if missing:
        errors.append(f"referenced v2 artifacts are missing: {missing}")
    unused = sorted(set(artifacts) - used)
    if unused:
        errors.append(f"unused v2 artifact refs are forbidden: {unused}")

    model_formal_ready = len(route_results) == 72 and all(
        item.get("model_formal_status") == "PASSED" for item in route_results
    )
    browser_applicable = [
        item for item in route_results if item.get("browser_status") != "NOT_APPLICABLE"
    ]
    browser_ready = (
        len(route_results) == 72
        and bool(browser_applicable)
        and all(item.get("browser_status") == "PASSED" for item in browser_applicable)
        and all(
            item.get("browser_status") in {"PASSED", "NOT_APPLICABLE"}
            for item in route_results
        )
    )
    native_applicable = [
        item for item in route_results if item.get("native_status") != "NOT_APPLICABLE"
    ]
    native_ready = (
        len(route_results) == 72
        and bool(native_applicable)
        and all(item.get("native_status") == "PASSED" for item in native_applicable)
        and all(
            item.get("native_status") in {"PASSED", "NOT_APPLICABLE"}
            for item in route_results
        )
    )
    runtime_ready = len(route_results) == 72 and all(
        item.get("runtime_status") == "PASSED" for item in route_results
    )
    independent_ready = (
        independent_graph_ready
        and external_capture.get("status") == "PASSED"
        and len(route_results) == 72
        and all(item.get("independent_status") == "PASSED" for item in route_results)
        and corpora.get("holdout", {}).get("status") == "PASSED"
        and corpora.get("representative_workloads", {}).get("status") == "PASSED"
        and campaign.get("external_evidence", {}).get("customer_status") == "PASSED"
    )
    expected_unconditional_proof = (
        model_formal_ready
        and len(route_results) == 72
        and all(item.get("unconditional") is True for item in route_results)
        and not campaign.get("assumptions")
        and not campaign.get("unsupported_semantics")
    )
    if campaign.get("unconditional_proof") is not expected_unconditional_proof:
        errors.append("frontend v2 unconditional proof derivation drift")
    formal_ready = formal_readiness_v2(
        model_formal_ready=model_formal_ready,
        route_results=route_results,
        campaign=campaign,
    )
    certification_ready = (
        formal_ready
        and browser_ready
        and native_ready
        and runtime_ready
        and independent_ready
        and corpora.get("negative", {}).get("status") == "PASSED"
        and campaign.get("certification_status") == "CERTIFIED"
    )
    if expected_unconditional_proof and not formal_ready:
        errors.append("frontend v2 unconditional proof readiness drift")
    if manifest.get("status") == "certified" and not certification_ready:
        errors.append("certified v2 pack lacks five-dimensional readiness")
        for field, ready in (
            ("model_formal_ready", model_formal_ready),
            ("browser_ready", browser_ready),
            ("native_ready", native_ready),
            ("runtime_ready", runtime_ready),
            ("independent_ready", independent_ready),
            ("certification_ready", certification_ready),
        ):
            if not ready:
                errors.append(f"certified v2 pack {field} is not true")

    if execute_replay and not errors:
        expected_command = [
            "python3",
            "-B",
            "formal-campaign/replay/scripts/batch32/replay_frontend_formal_route_campaign_v2.py",
            ".",
            "--campaign",
            campaign_path.relative_to(pack).as_posix(),
            "--schema",
            "formal-campaign/replay/schemas/batch32/frontend-formal-route-campaign-v2.schema.json",
            "--route-schema",
            "formal-campaign/replay/schemas/batch32/frontend-formal-route-evidence-v2.schema.json",
            "--no-replay-execute",
            "--json",
        ]
        command = campaign.get("replay", {}).get("command")
        if command != expected_command:
            errors.append("v2 replay command is not canonical/self-contained")
        else:
            try:
                completed = subprocess.run(
                    command,
                    cwd=pack,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    capture_output=True,
                    text=True,
                    timeout=SELF_CONTAINED_REPLAY_TIMEOUT_SECONDS,
                    check=False,
                )
                replay_result = json.loads(completed.stdout.strip().splitlines()[-1])
                if completed.returncode or replay_result.get("status") != "valid":
                    errors.append("v2 self-contained replay validation failed")
            except Exception as exc:
                errors.append(f"v2 self-contained replay execution failed: {exc}")

    if errors:
        model_formal_ready = False
        formal_ready = False
        browser_ready = False
        native_ready = False
        runtime_ready = False
        independent_ready = False
        certification_ready = False
    return {
        "schema_version": 2,
        "status": "invalid" if errors else "valid",
        "campaign_key": campaign.get("campaign_key"),
        "profile_count": len(profile_by_id),
        "route_count": len(routes),
        "block_count": len(routes) * len(BLOCK_IDS),
        "scenario_count": len(scenario_ids),
        "structural_status": "FAILED" if errors else "PASSED",
        "local_equivalence_status": (
            "PROVED"
            if model_formal_ready
            and route_results
            and all(item.get("unconditional") is True for item in route_results)
            else "PROVED_UNDER_ASSUMPTIONS"
            if model_formal_ready
            else "INCOMPLETE"
        ),
        "bounded_proof_profile_ready": model_formal_ready,
        "formal_ready": formal_ready,
        "external_evidence_status": external_capture.get("status", "FAILED"),
        "proved_route_count": sum(
            item.get("model_formal_status") == "PASSED"
            and item.get("unconditional") is True
            for item in route_results
        )
        if not errors
        else 0,
        "proved_under_assumptions_route_count": (
            sum(
                item.get("model_formal_status") == "PASSED"
                and item.get("unconditional") is not True
                for item in route_results
            )
            if model_formal_ready
            else 0
        ),
        "native_route_count": sum(
            item.get("native_status") == "PASSED" for item in route_results
        ),
        "native_applicable_route_count": len(native_applicable),
        "native_passed_route_count": sum(
            item.get("native_status") == "PASSED" for item in route_results
        ),
        "model_formal_ready": model_formal_ready,
        "browser_ready": browser_ready,
        "native_ready": native_ready,
        "runtime_ready": runtime_ready,
        "independent_ready": independent_ready,
        "certification_ready": certification_ready and not portable_evidence_only,
        "live_engine_verifier_status": (
            "NOT_RUN" if portable_evidence_only else "PASSED"
        ),
        "scope_digest": scope_digest,
        "errors": errors,
    }


def readiness_failure(errors: list[str]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "status": "invalid",
        "structural_status": "FAILED",
        "local_equivalence_status": "INCOMPLETE",
        "bounded_proof_profile_ready": False,
        "formal_ready": False,
        "external_evidence_status": "NOT_RUN",
        "proved_route_count": 0,
        "proved_under_assumptions_route_count": 0,
        "native_route_count": 0,
        "native_applicable_route_count": 0,
        "native_passed_route_count": 0,
        "model_formal_ready": False,
        "browser_ready": False,
        "native_ready": False,
        "runtime_ready": False,
        "independent_ready": False,
        "certification_ready": False,
        "live_engine_verifier_status": "UNKNOWN",
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_dir")
    parser.add_argument("--campaign")
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--route-schema", type=Path)
    parser.add_argument(
        "--external-trust-root",
        type=Path,
        help="operator-configured trust anchor kept outside the evidence pack",
    )
    parser.add_argument("--no-replay-execute", action="store_true")
    parser.add_argument(
        "--portable-evidence-only",
        action="store_true",
        help=(
            "validate captured, digest-bound evidence without comparing live "
            "repository bytes or executing receipt-bound solver or Node replay; "
            "does not confer certification"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.portable_evidence_only and not args.no_replay_execute:
        parser.error("--portable-evidence-only requires --no-replay-execute")
    result = validate_campaign(
        Path(args.pack_dir),
        campaign_relative=args.campaign,
        schema_path=args.schema,
        route_schema_path=args.route_schema,
        execute_replay=not args.no_replay_execute,
        portable_evidence_only=args.portable_evidence_only,
        external_trust_root_path=(
            args.external_trust_root
            if args.external_trust_root is not None
            else Path(os.environ["ELMOS_FRONTEND_EXTERNAL_TRUST_ROOT"])
            if os.environ.get("ELMOS_FRONTEND_EXTERNAL_TRUST_ROOT")
            else None
        ),
    )
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif result.get("status") == "valid":
        print(
            "OK: frontend v2 formal route campaign "
            f"routes={result['route_count']} blocks={result['block_count']} "
            f"model_formal_ready={str(result['model_formal_ready']).lower()} "
            f"certification_ready={str(result['certification_ready']).lower()}"
        )
    else:
        print(
            "\n".join("ERROR: " + item for item in result.get("errors", [])),
            file=sys.stderr,
        )
    return 0 if result.get("status") == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())

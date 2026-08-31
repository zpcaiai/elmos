#!/usr/bin/env python3
"""Build the paired Batch 32/35 frontend formal aggregate packs atomically.

The frontend engine emits the bounded-navigation campaign.  This tool captures
that output, adds byte-addressed/canonical evidence and frozen replay tooling,
then validates both independent pack surfaces before publishing either one.
It never upgrades model evidence, proof under assumptions, or local execution
to native/external evidence or certification.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

CLIENT_KEY = "frontend-72-route-equivalence-v1"
VERIFICATION_KEY = "frontend-72-route-formal-equivalence-v1"
CAMPAIGN_KEY = "frontend-72-route-formal-equivalence-v1"
CLIENT_KEY_V2 = "frontend-72-route-equivalence-v2"
VERIFICATION_KEY_V2 = "frontend-72-route-formal-equivalence-v2"
CAMPAIGN_KEY_V2 = "frontend-72-route-formal-equivalence-v2"
PROFILE_IDS = (
    "angular",
    "flutter",
    "harmony-arkui",
    "jquery",
    "react",
    "react-native",
    "svelte",
    "vue2",
    "vue3",
)
SEMANTIC_BLOCKS = (
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
BLOCK_SYMBOL_MAP_V2 = {
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
BLOCK_ROOT_POINTERS_V2 = {
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
RUNTIME_CHANNELS_V2 = ("browser", "android", "ios", "harmonyos")
RUNTIME_CHANNEL_RECORD_KEYS_V2 = {
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
RUNTIME_RAW_PROOF_DISCOVERY_KINDS_V2 = {
    "PLAYWRIGHT_RAW_RESULT",
    "FLUTTER_DRIVE_RAW_RESULT",
}
REQUIRED_RUNTIME_CHANNELS_V2 = {
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
RUNTIME_ACTUAL_KEYS_V2 = {
    "route-navigation-deeplink-404": {
        "requestedPath",
        "selectedRouteId",
        "selectedPath",
        "resolution",
        "deepLink",
        "requiresAuth",
    },
    "component-template-view": {
        "componentId",
        "key",
        "title",
        "text",
        "visible",
    },
    "state-management": {"stateId", "before", "after", "saturated"},
    "action-event": {"event", "keyboardKey", "handled", "action"},
    "effect-lifecycle": {
        "lifecycle",
        "effect",
        "executions",
        "cleanup",
        "staleResponseIgnored",
    },
    "form-binding-validation": {
        "formId",
        "fieldId",
        "value",
        "submitted",
        "valid",
        "errorCode",
    },
    "api-network": {
        "operationId",
        "called",
        "method",
        "path",
        "outcome",
        "canceled",
        "staleIgnored",
        "cacheKey",
    },
    "identity-permission": {
        "role",
        "permission",
        "permissionGranted",
        "tenantMatch",
        "authorized",
        "serverAuthorityRequired",
    },
    "rendering-hydration": {
        "mode",
        "requested",
        "status",
        "duplicateEffects",
        "mismatchVisible",
    },
    "accessibility-focus": {
        "mainRole",
        "headingLevel",
        "formLabel",
        "errorRole",
        "liveRegion",
        "keyboardSubmit",
        "focusTarget",
    },
    "i18n-theme-responsive": {
        "requestedLocale",
        "locale",
        "requestedTheme",
        "theme",
        "viewportWidth",
        "columns",
    },
    "native-platform": {
        "boundary",
        "lifecycle",
        "attempted",
        "permission",
        "available",
        "outcome",
        "recovery",
    },
}
RUNTIME_ACTUAL_BOOL_FIELDS_V2 = {
    "deepLink", "requiresAuth", "visible", "saturated", "handled", "cleanup",
    "staleResponseIgnored", "submitted", "valid", "called", "canceled",
    "staleIgnored", "permissionGranted", "tenantMatch", "authorized",
    "serverAuthorityRequired", "duplicateEffects", "mismatchVisible",
    "keyboardSubmit", "attempted", "available",
}
RUNTIME_ACTUAL_INT_FIELDS_V2 = {
    "before", "after", "executions", "headingLevel", "viewportWidth", "columns"
}
RUNTIME_ACTUAL_NULLABLE_STRING_FIELDS_V2 = {
    "keyboardKey",
    "errorCode",
    "errorRole",
    "focusTarget",
}
RUNTIME_ACTUAL_EMPTY_STRING_FIELDS_BY_BLOCK_V2 = {
    "form-binding-validation": {"value"},
}
RUNTIME_ACTUAL_ENUMS_BY_BLOCK_V2 = {
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
    block_enums = RUNTIME_ACTUAL_ENUMS_BY_BLOCK_V2.get(block_id, {})
    empty_string_fields = RUNTIME_ACTUAL_EMPTY_STRING_FIELDS_BY_BLOCK_V2.get(
        block_id, set()
    )
    for field, value in actual.items():
        if field in block_enums:
            if value not in block_enums[field]:
                return False
        elif field in RUNTIME_ACTUAL_BOOL_FIELDS_V2:
            if type(value) is not bool:
                return False
        elif field in RUNTIME_ACTUAL_INT_FIELDS_V2:
            if type(value) is not int or value < 0:
                return False
        elif field in RUNTIME_ACTUAL_NULLABLE_STRING_FIELDS_V2:
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
BLOCK_OBSERVER_CONTRACT_V2 = "block-specific-runtime-observation-v1"
BLOCK_OBSERVER_SPECS_V2 = {
    "route-navigation-deeplink-404": {
        "observer_kind": "ROUTER_DOM_URL_OBSERVER",
        "measurement_surface": "page.url+[data-elmos-active-route] attrs",
        "trace_role": "browser-route-dom-url-observer-trace",
        "measurement_keys": (
            "page_url",
            "active_route_attributes",
            "declared_routes",
        ),
        "supporting_trace_roles": (
            "browser-dom-snapshot",
            "browser-framework-event-trace",
        ),
    },
    "component-template-view": {
        "observer_kind": "RENDERED_COMPONENT_DOM_OBSERVER",
        "measurement_surface": "active route heading/text/visibility attrs",
        "trace_role": "browser-rendered-component-observer-trace",
        "measurement_keys": ("heading", "text", "visibility", "attributes"),
        "supporting_trace_roles": ("browser-dom-snapshot",),
    },
    "state-management": {
        "observer_kind": "FRAMEWORK_STATE_TRANSITION_OBSERVER",
        "measurement_surface": "[data-elmos-state-measurement] before/after/saturated",
        "trace_role": "browser-framework-state-transition-observer-trace",
        "measurement_keys": ("state_measurement",),
        "supporting_trace_roles": (
            "browser-framework-event-trace",
            "browser-dom-snapshot",
        ),
    },
    "action-event": {
        "observer_kind": "NATIVE_EVENT_OUTCOME_OBSERVER",
        "measurement_surface": "captured click/keydown/submit + [data-elmos-action-outcome]",
        "trace_role": "browser-native-event-outcome-observer-trace",
        "measurement_keys": ("captured_events", "outcome_attributes"),
        "supporting_trace_roles": ("browser-framework-event-trace",),
    },
    "effect-lifecycle": {
        "observer_kind": "FRAMEWORK_LIFECYCLE_TRACE_OBSERVER",
        "measurement_surface": "ordered [data-elmos-lifecycle-event]",
        "trace_role": "browser-framework-lifecycle-observer-trace",
        "measurement_keys": ("ordered_events",),
        "supporting_trace_roles": ("browser-framework-event-trace",),
    },
    "form-binding-validation": {
        "observer_kind": "FORM_CONTROL_VALIDITY_OBSERVER",
        "measurement_surface": "control value+ValidityState+error DOM+focus",
        "trace_role": "browser-form-validity-observer-trace",
        "measurement_keys": ("control", "validity_state", "error_dom", "active_element"),
        "supporting_trace_roles": (
            "browser-dom-snapshot",
            "browser-framework-event-trace",
            "browser-accessibility-axe-trace",
        ),
    },
    "api-network": {
        "observer_kind": "BROWSER_NETWORK_OBSERVER",
        "measurement_surface": "Playwright request/response/requestfailed + app abort/stale marker",
        "trace_role": "browser-network-observer-trace",
        "measurement_keys": ("network_events", "application_markers"),
        "supporting_trace_roles": (
            "browser-network-trace",
            "browser-framework-event-trace",
        ),
    },
    "identity-permission": {
        "observer_kind": "AUTHORITY_ADAPTER_OBSERVER",
        "measurement_surface": "[data-elmos-auth-decision] only if real adapter trace",
        "trace_role": "browser-authority-adapter-observer-trace",
        "measurement_keys": ("adapter_events", "decision_attributes"),
        "supporting_trace_roles": ("browser-framework-event-trace",),
    },
    "rendering-hydration": {
        "observer_kind": "SSR_HYDRATION_OBSERVER",
        "measurement_surface": "server markup digest+hydration warnings/mutations/effect count",
        "trace_role": "browser-ssr-hydration-observer-trace",
        "measurement_keys": (
            "server_markup_digest",
            "hydration_warnings",
            "mutations",
            "effect_count",
            "hydration_state",
        ),
        "supporting_trace_roles": (
            "browser-dom-snapshot",
            "browser-framework-event-trace",
        ),
    },
    "accessibility-focus": {
        "observer_kind": "ACCESSIBILITY_TREE_FOCUS_OBSERVER",
        "measurement_surface": "aria snapshot+axe+active element+keyboard",
        "trace_role": "browser-accessibility-tree-focus-observer-trace",
        "measurement_keys": (
            "aria_snapshot",
            "axe_results",
            "active_element",
            "keyboard_events",
            "accessibility_state",
        ),
        "supporting_trace_roles": (
            "browser-accessibility-axe-trace",
            "browser-framework-event-trace",
        ),
    },
    "i18n-theme-responsive": {
        "observer_kind": "COMPUTED_LAYOUT_I18N_THEME_OBSERVER",
        "measurement_surface": "html lang+rendered translated text+computed theme tokens+measured layout",
        "trace_role": "browser-computed-layout-i18n-theme-observer-trace",
        "measurement_keys": (
            "html_lang",
            "translated_text",
            "computed_theme_tokens",
            "layout_measurement",
        ),
        "supporting_trace_roles": ("browser-dom-snapshot",),
    },
    "native-platform": {
        "observer_kind": "NATIVE_ADAPTER_DEVICE_OBSERVER",
        "measurement_surface": "native semantics+lifecycle+permission+adapter trace",
        "trace_role": "native-adapter-device-observer-trace",
        "measurement_keys": (
            "semantics",
            "lifecycle",
            "permission",
            "adapter_events",
            "device_identity",
        ),
        "supporting_trace_roles": (),
    },
}
RUNTIME_DRIVER_CONTRACT_KEYS_V2 = {
    "schema_version",
    "kind",
    "framework_binding",
    "runtime_evidence_eligibility",
    "runtime_status",
    "independent_runtime_oracle",
    "customer_runtime_evidence",
    "certification",
    "required_runtime_channels",
    "observer_protocol",
    "actual_source",
    "self_reported_reducer_json_allowed",
    "legacy_runtime_observed_allowed",
    "declaration_payload_allowed_keys",
    "block_observer_contracts",
    "browser_required_not_run_blocks",
    "native_required_not_run_blocks",
    "native_route_without_real_device_channel_status",
    "root_selector",
    "ready_selector",
    "scenario_row_selector_template",
    "scenario_action_selector_template",
    "runtime_source_attribute",
    "runtime_source_value",
    "completion_attribute",
    "completion_value",
    "sequence_attribute",
    "query_selector",
    "block_selector_template",
    "network_intercept_path",
    "channel_projection_contract",
    "channel_projection_contract_digest",
    "native_adapter_evidence",
    "browser_or_device_evidence",
}


def browser_block_status_contract_v2(
    *, profile_id: str, driver: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Read the content-bound engine ceiling for each browser block."""

    contracts = driver.get("block_observer_contracts")
    if not isinstance(contracts, dict) or set(contracts) != set(SEMANTIC_BLOCKS):
        raise RuntimeError(f"V2_BLOCK_OBSERVER_CONTRACT_CLOSURE:{profile_id}")
    result: dict[str, dict[str, Any]] = {}
    not_run: list[str] = []
    for block_id in SEMANTIC_BLOCKS:
        row = contracts.get(block_id)
        spec = BLOCK_OBSERVER_SPECS_V2[block_id]
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
            raise RuntimeError(
                f"V2_BLOCK_OBSERVER_CONTRACT_DRIFT:{profile_id}:{block_id}"
            )
        if row["browser_status"] == "NOT_RUN":
            not_run.append(block_id)
        result[block_id] = {
            "status": row["browser_status"],
            "reason": row["browser_reason"]
            if row["browser_status"] == "NOT_RUN"
            else None,
        }
    if driver.get("browser_required_not_run_blocks") != not_run:
        raise RuntimeError(f"V2_BLOCK_OBSERVER_NOT_RUN_DECLARATION_DRIFT:{profile_id}")
    native_not_run = [
        block_id
        for block_id in SEMANTIC_BLOCKS
        if contracts[block_id]["native_status"] == "NOT_RUN"
    ]
    if (
        native_not_run != ["api-network"]
        or contracts["api-network"]["native_reason"]
        != "a single native adapter call does not prove timeout, retry, tenant cache, and unmount cancellation"
        or driver.get("native_required_not_run_blocks") != native_not_run
    ):
        raise RuntimeError(
            f"V2_BLOCK_OBSERVER_NATIVE_NOT_RUN_DECLARATION_DRIFT:{profile_id}"
        )
    return result


def native_block_status_ceiling_v2(
    *, profile_id: str, driver: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    browser_block_status_contract_v2(profile_id=profile_id, driver=driver)
    contracts = driver["block_observer_contracts"]
    return {
        block_id: {
            "status": contracts[block_id]["native_status"],
            "reason": contracts[block_id]["native_reason"]
            if contracts[block_id]["native_status"] == "NOT_RUN"
            else None,
        }
        for block_id in SEMANTIC_BLOCKS
    }


def validate_observed_block_statuses_v2(
    *,
    profile_id: str,
    channel: str,
    observed: dict[str, dict[str, Any]],
    browser_ceiling: dict[str, dict[str, Any]],
    native_ceiling: dict[str, dict[str, Any]],
) -> None:
    """Enforce the engine-owned per-block observation ceiling.

    Browser execution must reproduce the exact engine declaration.  A native
    profile may further downgrade a block to ``NOT_RUN`` when a concrete device
    surface was not observed, but it may never promote a block whose native
    ceiling is ``NOT_RUN``.
    """

    if set(observed) != set(SEMANTIC_BLOCKS):
        raise RuntimeError(
            f"V2_RUNTIME_BLOCK_STATUS_CLOSURE_DRIFT:{profile_id}:{channel}"
        )
    for block_id in SEMANTIC_BLOCKS:
        row = observed.get(block_id)
        if (
            not isinstance(row, dict)
            or set(row) != {"status", "reason"}
            or row.get("status") not in {"PASSED", "NOT_RUN"}
            or (
                row.get("status") == "PASSED"
                and row.get("reason") is not None
            )
            or (
                row.get("status") == "NOT_RUN"
                and (
                    not isinstance(row.get("reason"), str)
                    or not row["reason"]
                )
            )
        ):
            raise RuntimeError(
                f"V2_RUNTIME_BLOCK_STATUS_INVALID:{profile_id}:{channel}:{block_id}"
            )
    if channel == "browser":
        if observed != browser_ceiling:
            raise RuntimeError(
                f"V2_RUNTIME_BROWSER_BLOCK_DECLARATION_DRIFT:{profile_id}:{channel}"
            )
        return
    for block_id, row in observed.items():
        ceiling = native_ceiling.get(block_id)
        if not isinstance(ceiling, dict):
            raise RuntimeError(
                f"V2_RUNTIME_NATIVE_BLOCK_CEILING_MISSING:{profile_id}:{channel}:{block_id}"
            )
        if ceiling.get("status") == "NOT_RUN" and row != ceiling:
            raise RuntimeError(
                f"V2_RUNTIME_NATIVE_BLOCK_CEILING_DRIFT:{profile_id}:{channel}:{block_id}"
            )
        if row["status"] == "PASSED" and ceiling.get("status") != "PASSED":
            raise RuntimeError(
                f"V2_RUNTIME_NATIVE_BLOCK_CEILING_DRIFT:{profile_id}:{channel}:{block_id}"
            )
CORPUS_KINDS = (
    "development",
    "negative",
    "holdout",
    "representative_workloads",
)
LOCKED_Z3_VERSION = "Z3 version 4.16.0 - 64 bit"
LOCKED_Z3_BINARY_SHA256 = (
    "sha256:537a502af2f4013a8e887beebe525a0dae84918a61ff545991e36dfda07ed6d7"
)
LOCKED_Z3_OPTIONS = {"args": ["-in"], "timeout_ms": 10000}
LOCKED_Z3_ENVIRONMENT = {
    "platform": "darwin",
    "arch": "arm64",
    "node_version": "v26.0.0",
}
V2_IMPLEMENTATION_PATHS = (
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
)
V2_REPLAY_PATHS = (
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
)
V2_ENGINE_VERIFIER_MODULES = (
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
LOCKED_V2_NODE_TYPES_TREE_FILE_COUNT = 67
LOCKED_V2_NODE_TYPES_TREE_SHA256 = (
    "sha256:b0c1c8b3aaa62dfb2f57156c9493db374c5ae99b6f9e27e3bc2344e8e5704fe3"
)
ENGINE_SOLVER_RESULT_KEYS = {
    "schema_version",
    "solver",
    "solver_binary_realpath",
    "solver_binary_sha256",
    "solver_version",
    "identity_status",
    "invocation",
    "options",
    "environment",
    "exit_code",
    "stdout",
    "stderr",
    "outcome",
    "proof_status",
    "unconditional_proof",
    "route_id",
    "formal_input_digest",
    "solver_input_digest",
    "smt2_digest",
}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_digest(value: object) -> str:
    return digest_bytes(canonical_bytes(value))


def formal_proof_contract_v2(
    *,
    proof_status: object,
    unconditional_proof: object,
    assumptions: object,
    unsupported_semantics: object | None = None,
    label: str,
) -> str:
    """Return the only allowed proof strength for an exact v2 proof claim."""

    if (
        not isinstance(assumptions, list)
        or any(not isinstance(item, str) or not item for item in assumptions)
        or len(assumptions) != len(set(assumptions))
    ):
        raise RuntimeError(f"V2_FORMAL_ASSUMPTION_CONTRACT_DRIFT:{label}")
    if unsupported_semantics is not None and (
        not isinstance(unsupported_semantics, list)
        or any(
            not isinstance(item, str) or not item for item in unsupported_semantics
        )
        or len(unsupported_semantics) != len(set(unsupported_semantics))
    ):
        raise RuntimeError(f"V2_FORMAL_UNSUPPORTED_CONTRACT_DRIFT:{label}")
    unsupported = unsupported_semantics or []
    if proof_status == "PROVED":
        if unconditional_proof is not True or assumptions or unsupported:
            raise RuntimeError(f"V2_FORMAL_UNCONDITIONAL_MIXED_CLAIM:{label}")
        return "theorem"
    if proof_status == "PROVED_UNDER_ASSUMPTIONS":
        if unconditional_proof is not False or not assumptions:
            raise RuntimeError(f"V2_FORMAL_PUA_MIXED_CLAIM:{label}")
        return "assumption"
    if unconditional_proof is not False:
        raise RuntimeError(f"V2_FORMAL_NONPROOF_UNCONDITIONAL_CLAIM:{label}")
    return "none"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def write_json(path: Path, value: object, *, canonical: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        canonical_bytes(value)
        if canonical
        else (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    path.write_bytes(content)


def safe_relative(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or "://" in value
        or any(part in {"", ".", ".."} for part in Path(value).parts)
        or PurePosixPath(value).as_posix() != value
    ):
        raise RuntimeError(f"UNSAFE_PATH:{label}:{value}")
    return value


def safe_source_file(root: Path, relative: object, label: str) -> Path:
    value = safe_relative(relative, label)
    current = root
    for part in Path(value).parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError(f"SYMLINK_FORBIDDEN:{label}:{value}")
    try:
        resolved = (root / value).resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise RuntimeError(f"MISSING_OR_ESCAPED:{label}:{value}") from exc
    if not resolved.is_file():
        raise RuntimeError(f"FILE_REQUIRED:{label}:{value}")
    return resolved


def locked_v2_node_types_sources(repo_root: Path) -> list[tuple[Path, str]]:
    """Return the exact regular-file closure of the locked pnpm Node types tree."""

    public_root = repo_root / "engines/frontend-client-engine/node_modules/@types/node"
    expected_root = (
        repo_root
        / "engines/frontend-client-engine/node_modules/.pnpm/"
        "@types+node@24.3.0/node_modules/@types/node"
    )
    expected_link = "../.pnpm/@types+node@24.3.0/node_modules/@types/node"
    if not public_root.is_symlink():
        raise RuntimeError("V2_NODE_TYPES_LINK_REQUIRED")
    try:
        link_value = os.readlink(public_root)
        resolved_public = public_root.resolve(strict=True)
        resolved_expected = expected_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RuntimeError("V2_NODE_TYPES_ROOT_UNAVAILABLE") from exc
    if link_value != expected_link or resolved_public != resolved_expected:
        raise RuntimeError("V2_NODE_TYPES_LINK_DRIFT")
    current = repo_root / "engines/frontend-client-engine"
    for part in expected_root.relative_to(current).parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError("V2_NODE_TYPES_PNPM_ROOT_SYMLINK_FORBIDDEN")
    rows: list[dict[str, object]] = []
    sources: list[tuple[Path, str]] = []
    for source in sorted(resolved_expected.rglob("*"), key=lambda item: item.as_posix()):
        relative = source.relative_to(resolved_expected).as_posix()
        if source.is_symlink():
            raise RuntimeError(f"V2_NODE_TYPES_NESTED_SYMLINK_FORBIDDEN:{relative}")
        if source.is_dir():
            continue
        if not source.is_file():
            raise RuntimeError(f"V2_NODE_TYPES_REGULAR_FILE_REQUIRED:{relative}")
        content = source.read_bytes()
        rows.append(
            {
                "path": relative,
                "sha256": digest_bytes(content),
                "byte_count": len(content),
            }
        )
        sources.append((source, relative))
    if (
        len(rows) != LOCKED_V2_NODE_TYPES_TREE_FILE_COUNT
        or canonical_digest(rows) != LOCKED_V2_NODE_TYPES_TREE_SHA256
    ):
        raise RuntimeError("V2_NODE_TYPES_TREE_IDENTITY_DRIFT")
    return sources


def pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def pointer_tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise RuntimeError(f"RFC6901_REQUIRED:{pointer}")
    return [
        part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")
    ]


def resolve_pointer(value: object, pointer: str) -> object:
    current = value
    for token in pointer_tokens(pointer):
        if isinstance(current, dict):
            current = current[token]
        elif isinstance(current, list):
            current = current[int(token)]
        else:
            raise RuntimeError(f"POINTER_SCALAR:{pointer}")
    return current


def canonical_pointer_span(
    value: object, tokens: list[str], offset: int = 0
) -> tuple[int, int]:
    if not tokens:
        encoded = canonical_bytes(value)
        return offset, offset + len(encoded)
    token, remaining = tokens[0], tokens[1:]
    if isinstance(value, dict):
        cursor = offset + 1
        for index, key in enumerate(sorted(value)):
            if index:
                cursor += 1
            cursor += len(canonical_bytes(key)) + 1
            child = value[key]
            if key == token:
                return canonical_pointer_span(child, remaining, cursor)
            cursor += len(canonical_bytes(child))
    elif isinstance(value, list) and token.isdigit():
        wanted = int(token)
        cursor = offset + 1
        for index, child in enumerate(value):
            if index:
                cursor += 1
            if index == wanted:
                return canonical_pointer_span(child, remaining, cursor)
            cursor += len(canonical_bytes(child))
    raise RuntimeError(f"POINTER_NOT_FOUND:{'/'.join(tokens)}")


def expected_routes() -> set[str]:
    return {
        f"{source}--to--{target}"
        for source in PROFILE_IDS
        for target in PROFILE_IDS
        if source != target
    }


def artifact_identifier(namespace: str, relative: str) -> str:
    suffix = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:20]
    return f"{namespace}-{suffix}"


class ArtifactCatalog:
    def __init__(self, pack_root: Path) -> None:
        self.pack_root = pack_root
        self.by_id: dict[str, dict[str, Any]] = {}
        self.by_path: dict[str, str] = {}

    def add(self, identifier: str, role: str, relative: str) -> str:
        if identifier in self.by_id:
            raise RuntimeError(f"DUPLICATE_ARTIFACT_ID:{identifier}")
        if relative in self.by_path:
            raise RuntimeError(f"DUPLICATE_ARTIFACT_PATH:{relative}")
        path = safe_source_file(self.pack_root, relative, f"artifact:{identifier}")
        content = path.read_bytes()
        if not content:
            raise RuntimeError(f"EMPTY_ARTIFACT:{relative}")
        reference = {
            "id": identifier,
            "role": role,
            "path": relative,
            "sha256": digest_bytes(content),
            "bytes": len(content),
        }
        self.by_id[identifier] = reference
        self.by_path[relative] = identifier
        return identifier

    def ref(self, identifier: str) -> dict[str, Any]:
        return self.by_id[identifier]

    def fingerprint(self, identifiers: list[str]) -> str:
        return canonical_digest([self.by_id[item] for item in sorted(identifiers)])


def exact_profiles(schema_path: Path) -> dict[str, dict[str, Any]]:
    schema = load_json(schema_path)
    choices = schema["$defs"]["exactProfile"]["oneOf"]
    result = {choice["const"]["id"]: choice["const"] for choice in choices}
    if tuple(sorted(result)) != PROFILE_IDS:
        raise RuntimeError("EXACT_PROFILE_SCHEMA_DRIFT")
    return result


def validate_engine_campaign(
    engine_root: Path,
    campaign: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if (
        campaign.get("schema_version") != "1.0"
        or campaign.get("kind") != "frontend-formal-route-campaign"
        or campaign.get("proof_profile") != "bounded-navigation-v1"
        or campaign.get("corpus_id") != "frontend-bounded-navigation-corpus-v1"
        or campaign.get("profile_count") != 9
        or campaign.get("route_count") != 72
        or campaign.get("unconditional_proof") is not False
        or campaign.get("certification") != "NOT_CERTIFIED"
    ):
        raise RuntimeError("ENGINE_CAMPAIGN_IDENTITY_DRIFT")
    profile_entries: dict[str, dict[str, Any]] = {}
    for entry in campaign.get("profiles", []):
        if not isinstance(entry, dict):
            raise RuntimeError("ENGINE_PROFILE_INVALID")
        profile_id = entry.get("profile_id")
        if profile_id in profile_entries:
            raise RuntimeError(f"ENGINE_PROFILE_DUPLICATE:{profile_id}")
        expected = profiles.get(str(profile_id))
        if (
            expected is None
            or entry.get("framework_version") != expected["framework_version"]
            or entry.get("platforms") != expected["platforms"]
            or entry.get("target_build") != "NOT_RUN"
        ):
            raise RuntimeError(f"ENGINE_PROFILE_TUPLE_DRIFT:{profile_id}")
        project_root = engine_root / safe_relative(
            entry.get("project_path"), "project_path"
        )
        if not project_root.is_dir() or project_root.is_symlink():
            raise RuntimeError(f"ENGINE_PROJECT_MISSING:{profile_id}")
        project_map: dict[str, str] = {}
        for path in sorted(project_root.rglob("*")):
            if path.is_symlink():
                raise RuntimeError(f"ENGINE_PROJECT_SYMLINK:{path}")
            if path.is_file():
                relative = path.relative_to(project_root).as_posix()
                project_map[relative] = path.read_text(encoding="utf-8")
        if canonical_digest(project_map) != entry.get("project_digest"):
            raise RuntimeError(f"ENGINE_PROJECT_DIGEST_DRIFT:{profile_id}")
        manifest_path = safe_source_file(
            engine_root, entry.get("manifest_path"), f"profile_manifest:{profile_id}"
        )
        manifest = load_json(manifest_path)
        unsigned_manifest = {
            key: value for key, value in manifest.items() if key != "manifest_digest"
        }
        if manifest.get("manifest_digest") != canonical_digest(
            unsigned_manifest
        ) or entry.get("manifest_digest") != manifest.get("manifest_digest"):
            raise RuntimeError(f"ENGINE_PROFILE_MANIFEST_DIGEST_DRIFT:{profile_id}")
        navigation_path = safe_relative(
            entry.get("navigation_source_path"), f"navigation_source:{profile_id}"
        )
        if not (project_root / navigation_path).is_file():
            raise RuntimeError(f"ENGINE_NAVIGATION_SOURCE_MISSING:{profile_id}")
        profile_entries[str(profile_id)] = entry
    if set(profile_entries) != set(PROFILE_IDS):
        raise RuntimeError("ENGINE_PROFILE_CLOSURE_DRIFT")

    route_entries: dict[str, dict[str, Any]] = {}
    for entry in campaign.get("routes", []):
        if not isinstance(entry, dict):
            raise RuntimeError("ENGINE_ROUTE_INVALID")
        route_id = entry.get("route_id")
        source = entry.get("source_profile")
        target = entry.get("target_profile")
        if route_id in route_entries:
            raise RuntimeError(f"ENGINE_ROUTE_DUPLICATE:{route_id}")
        if source == target or route_id != f"{source}--to--{target}":
            raise RuntimeError(f"ENGINE_ROUTE_IDENTITY_DRIFT:{route_id}")
        if entry.get("source_project_digest") != profile_entries[str(source)].get(
            "project_digest"
        ) or entry.get("target_project_digest") != profile_entries[str(target)].get(
            "project_digest"
        ):
            raise RuntimeError(f"ENGINE_ROUTE_PROJECT_DIGEST_DRIFT:{route_id}")
        route_root = engine_root / "routes" / str(route_id)
        for filename in (
            "formal-input.json",
            "proof.smt2",
            "solver-result.json",
            "source-model.json",
            "target-model.json",
            "behavior.json",
            "chunks.json",
            "composition.json",
            "layered-result.json",
        ):
            safe_source_file(
                route_root, filename, f"engine_route:{route_id}:{filename}"
            )
        solver_result = load_json(route_root / "solver-result.json")
        layered = load_json(route_root / "layered-result.json")
        links = layered.get("links")
        if not isinstance(links, dict):
            raise RuntimeError(f"ENGINE_ROUTE_LAYERED_LINKS_MISSING:{route_id}")
        if (
            entry.get("evidence_path") != f"routes/{route_id}/layered-result.json"
            or entry.get("formal_input_path") != f"routes/{route_id}/formal-input.json"
            or entry.get("solver_result_path")
            != f"routes/{route_id}/solver-result.json"
            or entry.get("formal_input_digest")
            != digest_bytes((route_root / "formal-input.json").read_bytes())
            or solver_result.get("formal_input_digest")
            != entry.get("formal_input_digest")
            or links.get("formal_input_path") != entry.get("formal_input_path")
            or links.get("formal_input_digest") != entry.get("formal_input_digest")
            or links.get("smt2_path") != f"routes/{route_id}/proof.smt2"
            or links.get("smt2_digest")
            != digest_bytes((route_root / "proof.smt2").read_bytes())
            or links.get("solver_result_path") != entry.get("solver_result_path")
            or links.get("solver_result_digest")
            != digest_bytes((route_root / "solver-result.json").read_bytes())
            or layered.get("route_id") != route_id
            or entry.get("status") != layered.get("status")
            or entry.get("layered_result") != layered.get("status")
            or layered.get("certification") != "NOT_CERTIFIED"
        ):
            raise RuntimeError(f"ENGINE_ROUTE_LINKAGE_DRIFT:{route_id}")
        route_entries[str(route_id)] = entry
    if set(route_entries) != expected_routes():
        raise RuntimeError("ENGINE_ROUTE_CLOSURE_DRIFT")
    return profile_entries, route_entries


def copy_engine_output(
    engine_root: Path,
    pack_root: Path,
    catalog: ArtifactCatalog,
) -> tuple[dict[str, str], str]:
    destination = pack_root / "formal-campaign" / "engine"
    shutil.copytree(engine_root, destination)
    raw_ids: dict[str, str] = {}
    for path in sorted(destination.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"ENGINE_COPY_SYMLINK:{path}")
        if not path.is_file():
            continue
        engine_relative = path.relative_to(destination).as_posix()
        pack_relative = path.relative_to(pack_root).as_posix()
        identifier = artifact_identifier("engine", engine_relative)
        if engine_relative == "frontend-formal-route-campaign.json":
            role = "engine-campaign"
        elif engine_relative.startswith("profiles/") and engine_relative.endswith(
            "/manifest.json"
        ):
            role = "engine-profile-manifest"
        elif engine_relative.startswith("profiles/"):
            role = "profile-project-file"
        elif engine_relative.startswith("routes/"):
            role = "engine-route-artifact"
        else:
            raise RuntimeError(f"UNEXPECTED_ENGINE_ARTIFACT:{engine_relative}")
        catalog.add(identifier, role, pack_relative)
        raw_ids[engine_relative] = identifier
    return raw_ids, raw_ids["frontend-formal-route-campaign.json"]


def capture_solver_binary(
    *,
    engine_root: Path,
    pack_root: Path,
    catalog: ArtifactCatalog,
    route_entries: dict[str, dict[str, Any]],
    relative_path: str = "formal-campaign/environment/z3-4.16.0.bin",
) -> dict[str, Any]:
    """Capture the exact verified Z3 producer binary once for all 72 routes."""

    solver_path: Path | None = None
    for route_id in sorted(route_entries):
        raw = load_json(engine_root / "routes" / route_id / "solver-result.json")
        realpath_value = raw.get("solver_binary_realpath")
        if (
            set(raw) != ENGINE_SOLVER_RESULT_KEYS
            or raw.get("schema_version") != "1.0"
            or raw.get("route_id") != route_id
            or raw.get("identity_status") != "VERIFIED"
            or not isinstance(realpath_value, str)
            or not Path(realpath_value).is_absolute()
            or Path(realpath_value).name != "z3"
            or raw.get("solver") != realpath_value
            or raw.get("solver_binary_sha256") != LOCKED_Z3_BINARY_SHA256
            or raw.get("solver_version") != LOCKED_Z3_VERSION
            or raw.get("invocation") != [realpath_value, "-in"]
            or raw.get("options") != LOCKED_Z3_OPTIONS
            or raw.get("environment") != LOCKED_Z3_ENVIRONMENT
        ):
            raise RuntimeError(f"ENGINE_SOLVER_IDENTITY_DRIFT:{route_id}")
        try:
            current = Path(realpath_value).resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise RuntimeError(f"ENGINE_SOLVER_BINARY_MISSING:{route_id}") from exc
        if (
            str(current) != realpath_value
            or not current.is_file()
            or current.is_symlink()
            or digest_bytes(current.read_bytes()) != LOCKED_Z3_BINARY_SHA256
        ):
            raise RuntimeError(f"ENGINE_SOLVER_BINARY_DRIFT:{route_id}")
        if solver_path is None:
            solver_path = current
        elif solver_path != current:
            raise RuntimeError("ENGINE_SOLVER_BINARY_NOT_UNIFORM")
    if solver_path is None:
        raise RuntimeError("ENGINE_SOLVER_BINARY_CLOSURE_EMPTY")
    relative = relative_path
    destination = pack_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(solver_path, destination)
    identifier = artifact_identifier("solver-binary", LOCKED_Z3_BINARY_SHA256)
    catalog.add(identifier, "solver-binary-environment", relative)
    reference = catalog.ref(identifier)
    if reference["sha256"] != LOCKED_Z3_BINARY_SHA256:
        raise RuntimeError("CAPTURED_SOLVER_BINARY_DIGEST_DRIFT")
    return {
        "artifact_id": identifier,
        "sha256": reference["sha256"],
        "bytes": reference["bytes"],
        "producer_realpath": str(solver_path),
        "version": LOCKED_Z3_VERSION,
        "options": LOCKED_Z3_OPTIONS,
        "environment": LOCKED_Z3_ENVIRONMENT,
    }


def install_bundle(
    *,
    repo_root: Path,
    pack_root: Path,
    catalog: ArtifactCatalog,
    name: str,
    sources: list[tuple[str, str, str]],
) -> dict[str, Any]:
    artifact_ids: list[str] = []
    files: list[dict[str, Any]] = []
    for repository_path, captured_name, role in sources:
        source = safe_source_file(repo_root, repository_path, f"{name}_source")
        relative = f"formal-campaign/{name}/{captured_name}"
        destination = pack_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        identifier = artifact_identifier(name, captured_name)
        catalog.add(identifier, role, relative)
        artifact_ids.append(identifier)
        files.append(
            {
                "repository_path": repository_path,
                "captured_path": relative,
                "artifact_id": identifier,
            }
        )
    artifact_ids.sort()
    fingerprint = catalog.fingerprint(artifact_ids)
    manifest_value = {
        "schema_version": 1,
        "kind": f"frontend-formal-{name}-bundle",
        "artifact_ids": artifact_ids,
        "fingerprint": fingerprint,
        "files": sorted(files, key=lambda item: item["repository_path"]),
    }
    manifest_relative = f"formal-campaign/{name}/manifest.json"
    write_json(pack_root / manifest_relative, manifest_value, canonical=True)
    manifest_id = artifact_identifier(name, "manifest.json")
    catalog.add(manifest_id, f"{name}-manifest", manifest_relative)
    return {
        "manifest_artifact_id": manifest_id,
        "artifact_ids": artifact_ids,
        "fingerprint": fingerprint,
    }


def install_bundle_v2(
    *,
    repo_root: Path,
    pack_root: Path,
    catalog: ArtifactCatalog,
    name: str,
    repository_paths: tuple[str, ...],
) -> dict[str, Any]:
    artifact_ids: list[str] = []
    rows: list[dict[str, str]] = []
    for repository_path in repository_paths:
        source = safe_source_file(repo_root, repository_path, f"v2_{name}_source")
        relative = f"formal-campaign/{name}/{repository_path}"
        destination = pack_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        identifier = artifact_identifier(f"v2-{name}", repository_path)
        catalog.add(identifier, f"{name}-source-v2", relative)
        artifact_ids.append(identifier)
        rows.append(
            {
                "repository_path": repository_path,
                "captured_path": relative,
                "artifact_id": identifier,
            }
        )
    artifact_ids.sort()
    fingerprint = catalog.fingerprint(artifact_ids)
    manifest = {
        "schema_version": 2,
        "kind": f"frontend-formal-{name}-bundle-v2",
        "artifact_ids": artifact_ids,
        "fingerprint": fingerprint,
        "files": sorted(rows, key=lambda row: row["repository_path"]),
    }
    relative = f"formal-campaign/{name}/manifest.json"
    write_json(pack_root / relative, manifest, canonical=True)
    manifest_id = artifact_identifier(f"v2-{name}", "manifest.json")
    catalog.add(manifest_id, f"{name}-manifest-v2", relative)
    return {
        "manifest_artifact_id": manifest_id,
        "artifact_ids": artifact_ids,
        "fingerprint": fingerprint,
    }


def add_corpora(pack_root: Path, catalog: ArtifactCatalog) -> dict[str, Any]:
    result: dict[str, Any] = {}
    behavior_cases = [f"bounded-navigation-case-{index}" for index in range(5)]
    for kind in CORPUS_KINDS:
        corpus_id = (
            "frontend-bounded-navigation-corpus-v1"
            if kind == "development"
            else f"frontend-bounded-navigation-{kind.replace('_', '-')}-not-run-v1"
        )
        status = "PASSED" if kind == "development" else "NOT_RUN"
        case_ids = behavior_cases if kind == "development" else []
        value = {
            "schema_version": 1,
            "kind": kind,
            "id": corpus_id,
            "status": status,
            "case_ids": case_ids,
            "authority": "local-model"
            if kind == "development"
            else "external-required",
        }
        relative = f"formal-campaign/corpora/{kind}.json"
        write_json(pack_root / relative, value, canonical=True)
        identifier = artifact_identifier("corpus", kind)
        catalog.add(identifier, "corpus-manifest", relative)
        result[kind] = {
            "id": corpus_id,
            "status": status,
            "manifest_artifact_id": identifier,
            "case_ids": case_ids,
        }
    return result


def verify_engine_campaign_v2(repo_root: Path, engine_root: Path) -> dict[str, Any]:
    main_path = safe_source_file(
        engine_root,
        "frontend-interaction-formal-campaign.json",
        "v2_engine_campaign",
    )
    campaign = load_json(main_path)
    if (
        campaign.get("schema_version") != "1.0"
        or campaign.get("kind") != "frontend-interaction-formal-route-campaign"
        or campaign.get("proof_profile") != "bounded-frontend-interaction-v1"
        or campaign.get("semantic_block_ids") != list(SEMANTIC_BLOCKS)
        or campaign.get("block_symbol_map") != BLOCK_SYMBOL_MAP_V2
        or campaign.get("profile_count") != 9
        or campaign.get("route_count") != 72
        or campaign.get("block_count") != 12
        or campaign.get("native_build_and_runtime") != "NOT_RUN"
        or campaign.get("independent_external_verification") != "NOT_RUN"
        or campaign.get("certification") != "NOT_CERTIFIED"
    ):
        raise RuntimeError("V2_ENGINE_CAMPAIGN_IDENTITY_DRIFT")
    engine_unconditional = campaign.get("unconditional_proof")
    engine_assumptions = campaign.get("assumptions")
    formal_proof_contract_v2(
        proof_status=(
            "PROVED" if engine_unconditional is True else "PROVED_UNDER_ASSUMPTIONS"
        ),
        unconditional_proof=engine_unconditional,
        assumptions=engine_assumptions,
        label="engine-campaign",
    )
    arbitrary_customer_source = campaign.get("arbitrary_customer_source")
    if arbitrary_customer_source not in {"PROVED", "NOT_PROVED"} or (
        engine_unconditional is True and arbitrary_customer_source != "PROVED"
    ):
        raise RuntimeError("V2_ENGINE_ARBITRARY_SOURCE_PROOF_DRIFT")
    verifier = safe_source_file(
        repo_root,
        "engines/frontend-client-engine/dist/src/frontend-interaction-formal-cli.js",
        "v2_engine_verifier",
    )
    route_rows = campaign.get("routes")
    if not isinstance(route_rows, list) or not route_rows:
        raise RuntimeError("V2_ENGINE_ROUTE_CLOSURE_DRIFT")
    first_route = route_rows[0]
    if not isinstance(first_route, dict):
        raise RuntimeError("V2_ENGINE_ROUTE_CLOSURE_DRIFT")
    solver_result_relative = first_route.get("solver_result_path")
    if not isinstance(solver_result_relative, str):
        raise RuntimeError("V2_ENGINE_SOLVER_RESULT_LINK_DRIFT")
    solver_result = load_json(
        safe_source_file(
            engine_root,
            solver_result_relative,
            "v2_engine_solver_result",
        )
    )
    solver_realpath = solver_result.get("solver_binary_realpath")
    if not isinstance(solver_realpath, str) or not Path(solver_realpath).is_absolute():
        raise RuntimeError("V2_ENGINE_SOLVER_IDENTITY_DRIFT")
    solver_path = Path(solver_realpath).resolve(strict=True)
    if (
        not solver_path.is_file()
        or solver_path.is_symlink()
        or digest_bytes(solver_path.read_bytes()) != LOCKED_Z3_BINARY_SHA256
    ):
        raise RuntimeError("V2_ENGINE_SOLVER_BINARY_DRIFT")
    node_command = shutil.which("node")
    if node_command is None:
        raise RuntimeError("V2_NODE_UNAVAILABLE")
    node_realpath = Path(node_command).resolve(strict=True)
    completed = subprocess.run(
        [
            str(node_realpath),
            str(verifier),
            "--proof-profile",
            "bounded-frontend-interaction-v1",
            "--verify",
            str(engine_root),
            "--solver",
            str(solver_path),
            "--json",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError("V2_ENGINE_VERIFIER_OUTPUT_INVALID") from exc
    expected = {
        "schema_version": "1.0",
        "kind": "frontend-interaction-formal-campaign-verification",
        "proof_profile": "bounded-frontend-interaction-v1",
        "valid": True,
        "errors": [],
    }
    if completed.returncode != 0 or result != expected:
        raise RuntimeError(
            "V2_ENGINE_VERIFIER_FAILED:\n" + completed.stdout + "\n" + completed.stderr
        )
    return campaign


def engine_artifact_role_v2(relative: str) -> str:
    if relative == "frontend-interaction-formal-campaign.json":
        return "engine-campaign-v2"
    if relative == "scenario-corpus.json":
        return "scenario-manifest-v2"
    if relative == "mutation-campaign.json" or relative.startswith("mutations/"):
        return "engine-mutation-artifact-v2"
    if relative.startswith(("profiles/", "generated-fixtures/")):
        return "engine-profile-artifact-v2"
    filename = Path(relative).name
    return {
        "source-model.json": "engine-model-v2",
        "target-model.json": "engine-model-v2",
        "behavior.json": "engine-behavior-v2",
        "chunks.json": "engine-chunks-v2",
        "formal-input.json": "engine-formal-input-v2",
        "proof.smt2": "engine-smt-input-v2",
        "solver-result.json": "engine-solver-result-v2",
        "vacuity-precheck.smt2": "engine-vacuity-input-v2",
        "vacuity-solver-result.json": "engine-vacuity-result-v2",
        "block-results.json": "engine-block-results-v2",
        "composition.json": "engine-composition-v2",
        "layered-result.json": "engine-layered-result-v2",
    }.get(filename, "engine-route-artifact-v2")


def copy_engine_output_v2(
    engine_root: Path,
    pack_root: Path,
    catalog: ArtifactCatalog,
) -> tuple[dict[str, str], str]:
    destination = pack_root / "formal-campaign" / "artifacts" / "engine"
    shutil.copytree(engine_root, destination)
    ids: dict[str, str] = {}
    for path in sorted(destination.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"V2_ENGINE_SYMLINK:{path}")
        if not path.is_file():
            continue
        engine_relative = path.relative_to(destination).as_posix()
        pack_relative = path.relative_to(pack_root).as_posix()
        identifier = artifact_identifier("v2-engine", engine_relative)
        catalog.add(identifier, engine_artifact_role_v2(engine_relative), pack_relative)
        ids[engine_relative] = identifier
    main = "frontend-interaction-formal-campaign.json"
    if main not in ids:
        raise RuntimeError("V2_ENGINE_MAIN_MISSING")
    return ids, ids[main]


def capture_engine_verifier_v2(
    *,
    repo_root: Path,
    pack_root: Path,
    catalog: ArtifactCatalog,
) -> dict[str, Any]:
    sources: list[tuple[Path, str, str]] = [
        (
            safe_source_file(
                repo_root,
                "engines/frontend-client-engine/package.json",
                "v2_verifier_package",
            ),
            "formal-campaign/engine-verifier/package.json",
            "engine-verifier-runtime-v2",
        )
    ]
    for name in V2_ENGINE_VERIFIER_MODULES:
        role = (
            "engine-verifier-entrypoint-v2"
            if name == "frontend-interaction-formal-cli"
            else "engine-verifier-runtime-v2"
        )
        sources.append(
            (
                safe_source_file(
                    repo_root,
                    f"engines/frontend-client-engine/dist/src/{name}.js",
                    f"v2_verifier_{name}",
                ),
                f"formal-campaign/engine-verifier/src/{name}.js",
                role,
            )
        )
    for source_relative, captured_relative in (
        (
            "engines/frontend-client-engine/node_modules/typescript/package.json",
            "formal-campaign/engine-verifier/node_modules/typescript/package.json",
        ),
        (
            "engines/frontend-client-engine/node_modules/typescript/lib/typescript.js",
            "formal-campaign/engine-verifier/node_modules/typescript/lib/typescript.js",
        ),
    ):
        source = (repo_root / source_relative).resolve(strict=True)
        try:
            source.relative_to(repo_root)
        except ValueError as exc:
            raise RuntimeError("V2_TYPESCRIPT_RUNTIME_ESCAPES_REPOSITORY") from exc
        if not source.is_file() or source.is_symlink():
            raise RuntimeError("V2_TYPESCRIPT_RUNTIME_FILE_REQUIRED")
        sources.append((source, captured_relative, "engine-verifier-runtime-v2"))
    for source, relative in locked_v2_node_types_sources(repo_root):
        sources.append(
            (
                source,
                f"formal-campaign/engine-verifier/node_modules/@types/node/{relative}",
                "engine-verifier-runtime-v2",
            )
        )
    runtime_ids: list[str] = []
    entrypoint_id: str | None = None
    for source, relative, role in sources:
        destination = pack_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        identifier = artifact_identifier("v2-engine-verifier", relative)
        catalog.add(identifier, role, relative)
        runtime_ids.append(identifier)
        if role == "engine-verifier-entrypoint-v2":
            entrypoint_id = identifier
    node_command = shutil.which("node")
    if node_command is None:
        raise RuntimeError("V2_NODE_UNAVAILABLE")
    node_realpath = Path(node_command).resolve(strict=True)
    completed = subprocess.run(
        [str(node_realpath), "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode != 0 or completed.stdout.strip() != "v26.0.0":
        raise RuntimeError("V2_NODE_VERSION_DRIFT")
    node_bytes = node_realpath.read_bytes()
    node_identity = {
        "schema_version": 2,
        "kind": "node-environment-identity-v2",
        "realpath": str(node_realpath),
        "sha256": digest_bytes(node_bytes),
        "bytes": len(node_bytes),
        "version": "v26.0.0",
        "platform": sys.platform,
        "arch": os.uname().machine,
        "portability": "PINNED_NODE_ENVIRONMENT_ASSUMPTION",
    }
    node_relative = "formal-campaign/engine-verifier/node-identity.json"
    write_json(pack_root / node_relative, node_identity, canonical=True)
    node_id = artifact_identifier("v2-engine-verifier", "node-identity.json")
    catalog.add(node_id, "node-environment-identity-v2", node_relative)
    if entrypoint_id is None:
        raise RuntimeError("V2_ENGINE_VERIFIER_ENTRYPOINT_MISSING")
    runtime_ids.sort()
    return {
        "entrypoint_artifact_id": entrypoint_id,
        "runtime_artifact_ids": runtime_ids,
        "node_identity_artifact_id": node_id,
        "fingerprint": catalog.fingerprint(runtime_ids + [node_id]),
        "command": [
            "node",
            "formal-campaign/engine-verifier/src/frontend-interaction-formal-cli.js",
            "--proof-profile",
            "bounded-frontend-interaction-v1",
            "--verify",
            "formal-campaign/artifacts/engine",
            "--solver",
            "formal-campaign/environment/z3",
            "--json",
        ],
        "status": "PASSED",
        "portability": "PINNED_NODE_ENVIRONMENT_ASSUMPTION",
    }


def add_corpora_v2(
    pack_root: Path,
    catalog: ArtifactCatalog,
    *,
    scenario_ids: list[str],
) -> dict[str, Any]:
    cases = {
        "development": scenario_ids,
        "negative": [f"mutation-{block_id}" for block_id in SEMANTIC_BLOCKS],
        "holdout": [],
        "representative_workloads": [],
    }
    statuses = {
        "development": "PASSED",
        "negative": "PASSED",
        "holdout": "NOT_RUN",
        "representative_workloads": "NOT_RUN",
    }
    result: dict[str, Any] = {}
    for name in CORPUS_KINDS:
        value = {
            "schema_version": 2,
            "kind": "frontend-formal-corpus-manifest-v2",
            "corpus_kind": name,
            "id": f"frontend-interaction-{name.replace('_', '-')}-v2",
            "status": statuses[name],
            "case_ids": cases[name],
            "independence_boundary": (
                "LOCAL_ENGINE_CORPUS"
                if name in {"development", "negative"}
                else "EXTERNALLY_ATTESTED"
                if statuses[name] == "PASSED"
                else "INDEPENDENT_EXTERNAL_NOT_RUN"
            ),
        }
        relative = f"formal-campaign/corpora/{name}.json"
        write_json(pack_root / relative, value, canonical=True)
        identifier = artifact_identifier("v2-corpus", name)
        catalog.add(identifier, "corpus-manifest-v2", relative)
        result[name] = {
            "id": value["id"],
            "status": value["status"],
            "manifest_artifact_id": identifier,
            "case_ids": value["case_ids"],
        }
    return result


def add_oracle_graph_v2(
    pack_root: Path,
    catalog: ArtifactCatalog,
    *,
    implementation_fingerprint: str,
    external_capture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    external_passed = (
        isinstance(external_capture, dict)
        and external_capture.get("status") == "PASSED"
    )
    graph = {
        "schema_version": 2,
        "kind": "frontend-oracle-provenance-graph-v2",
        "nodes": [
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
        ],
        "edges": [
            {
                "from": "canonical-model",
                "to": "formal-input",
                "relation": "DERIVES",
            },
            {
                "from": "formal-input",
                "to": "solver-input",
                "relation": "ENCODES",
            },
            {
                "from": "solver-input",
                "to": "solver-result",
                "relation": "SOLVED_BY",
            },
        ],
        "independent_oracle_status": "PASSED" if external_passed else "NOT_RUN",
    }
    if external_passed:
        graph["nodes"].extend(
            [
                {
                    "id": "external-trust-root",
                    "kind": "TRUST_ROOT",
                    "producer_fingerprint": external_capture[
                        "trust_root_fingerprint"
                    ],
                },
                {
                    "id": "external-replay-verifier",
                    "kind": "INDEPENDENT_REPLAY_VERIFIER",
                    "producer_fingerprint": external_capture[
                        "replay_verifier_fingerprint"
                    ],
                },
                {
                    "id": "external-intake",
                    "kind": "EXTERNAL_INTAKE",
                    "producer_fingerprint": external_capture[
                        "producer_fingerprint"
                    ],
                },
                {
                    "id": "external-runtime-oracle",
                    "kind": "INDEPENDENT_ORACLE",
                    "producer_fingerprint": external_capture[
                        "artifact_set_fingerprint"
                    ],
                },
            ]
        )
        graph["edges"].extend(
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
    relative = "formal-campaign/oracle/provenance-graph.json"
    write_json(pack_root / relative, graph, canonical=True)
    identifier = artifact_identifier("v2-oracle", "provenance-graph.json")
    catalog.add(identifier, "oracle-provenance-graph-v2", relative)
    return {
        "independence": (
            "EXTERNALLY_INDEPENDENT"
            if external_passed
            else "NOT_INDEPENDENT_SINGLE_ENGINE"
        ),
        "same_producer": not external_passed,
        "graph_artifact_id": identifier,
        "status": "PASSED" if external_passed else "NOT_RUN",
    }


def external_evidence_not_run_v2() -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {
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
        },
        {"results": {}},
    )


def _parse_utc_v2(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RuntimeError(f"V2_EXTERNAL_TIMESTAMP_INVALID:{label}")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise RuntimeError(f"V2_EXTERNAL_TIMESTAMP_INVALID:{label}") from exc
    if parsed.tzinfo is None:
        raise RuntimeError(f"V2_EXTERNAL_TIMESTAMP_INVALID:{label}")
    return parsed.astimezone(UTC)


def _verify_ed25519_v2(
    *, public_key_pem: str, signature_base64: str, payload: bytes, label: str
) -> None:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("V2_EXTERNAL_NODE_UNAVAILABLE")
    try:
        signature = base64.b64decode(signature_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError(f"V2_EXTERNAL_SIGNATURE_BASE64_INVALID:{label}") from exc
    with tempfile.TemporaryDirectory(prefix="frontend-v2-ed25519-") as directory:
        root = Path(directory)
        public_key = root / "public.pem"
        payload_path = root / "payload.bin"
        signature_path = root / "signature.bin"
        public_key.write_text(public_key_pem, encoding="utf-8")
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
                str(public_key),
                str(payload_path),
                str(signature_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    if completed.returncode != 0:
        raise RuntimeError(f"V2_EXTERNAL_SIGNATURE_INVALID:{label}")


def _external_public_key_digest_v2(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError("V2_EXTERNAL_PUBLIC_KEY_MISSING")
    return digest_bytes(value.encode("utf-8"))


def _validate_external_trust_chain_v2(
    *, trust_root: dict[str, Any], trust: dict[str, Any], now: datetime
) -> dict[str, Any]:
    root_keys = {
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
    }
    if set(trust_root) != root_keys:
        raise RuntimeError("V2_EXTERNAL_TRUST_ROOT_KEY_CLOSURE_DRIFT")
    root_valid_from = _parse_utc_v2(trust_root.get("valid_from"), "root.valid_from")
    root_valid_until = _parse_utc_v2(trust_root.get("valid_until"), "root.valid_until")
    if (
        trust_root.get("schema_version") != 2
        or trust_root.get("kind") != "frontend-formal-external-trust-root-v2"
        or trust_root.get("policy_id")
        != "frontend-independent-evidence-policy-v2"
        or not isinstance(trust_root.get("root_id"), str)
        or not trust_root["root_id"]
        or trust_root.get("revoked") is not False
        or not root_valid_from <= now < root_valid_until
    ):
        raise RuntimeError("V2_EXTERNAL_TRUST_ROOT_INVALID_EXPIRED_OR_REVOKED")
    root_revocations = trust_root.get("revocations")
    if not isinstance(root_revocations, dict) or set(root_revocations) != {
        "key_ids",
        "organization_ids",
        "updated_at",
    }:
        raise RuntimeError("V2_EXTERNAL_ROOT_REVOCATION_CLOSURE_DRIFT")
    root_revocation_time = _parse_utc_v2(
        root_revocations.get("updated_at"), "root.revocations.updated_at"
    )
    root_key_ids = root_revocations.get("key_ids")
    root_organization_ids = root_revocations.get("organization_ids")
    if (
        root_revocation_time > now
        or not isinstance(root_key_ids, list)
        or not all(isinstance(value, str) and value for value in root_key_ids)
        or len(root_key_ids) != len(set(root_key_ids))
        or not isinstance(root_organization_ids, list)
        or not all(
            isinstance(value, str) and value for value in root_organization_ids
        )
        or len(root_organization_ids) != len(set(root_organization_ids))
    ):
        raise RuntimeError("V2_EXTERNAL_ROOT_REVOCATION_LIST_INVALID")
    root_revoked_keys = set(root_key_ids)
    root_revoked_orgs = set(root_organization_ids)
    if not all(isinstance(value, str) and value for value in root_revoked_keys | root_revoked_orgs):
        raise RuntimeError("V2_EXTERNAL_ROOT_REVOCATION_ID_INVALID")

    signer_rows = trust_root.get("trust_store_signing_keys")
    if not isinstance(signer_rows, list) or not signer_rows:
        raise RuntimeError("V2_EXTERNAL_ROOT_SIGNER_MISSING")
    signer_by_id: dict[str, dict[str, Any]] = {}
    for row in signer_rows:
        if not isinstance(row, dict) or set(row) != {
            "key_id",
            "public_key_pem",
            "valid_from",
            "valid_until",
            "revoked",
        }:
            raise RuntimeError("V2_EXTERNAL_ROOT_SIGNER_DRIFT")
        key_id = str(row.get("key_id"))
        if not key_id or key_id in signer_by_id:
            raise RuntimeError("V2_EXTERNAL_ROOT_SIGNER_ID_COLLISION")
        valid_from = _parse_utc_v2(row.get("valid_from"), f"root.signer:{key_id}:from")
        valid_until = _parse_utc_v2(row.get("valid_until"), f"root.signer:{key_id}:until")
        if (
            row.get("revoked") is not False
            or key_id in root_revoked_keys
            or not valid_from <= now < valid_until
        ):
            raise RuntimeError(f"V2_EXTERNAL_ROOT_SIGNER_INVALID:{key_id}")
        _external_public_key_digest_v2(row.get("public_key_pem"))
        signer_by_id[key_id] = row

    allow_rows = trust_root.get("organization_key_allowlist")
    allowed: dict[tuple[str, str, str], str] = {}
    if not isinstance(allow_rows, list) or len(allow_rows) < 4:
        raise RuntimeError("V2_EXTERNAL_ORGANIZATION_KEY_ALLOWLIST_MISSING")
    for row in allow_rows:
        if not isinstance(row, dict) or set(row) != {
            "organization_id",
            "key_id",
            "role",
            "public_key_sha256",
        }:
            raise RuntimeError("V2_EXTERNAL_ORGANIZATION_KEY_ALLOWLIST_DRIFT")
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
            or not isinstance(row.get("public_key_sha256"), str)
            or len(row["public_key_sha256"]) != 71
            or not row["public_key_sha256"].startswith("sha256:")
        ):
            raise RuntimeError("V2_EXTERNAL_ORGANIZATION_KEY_ALLOWLIST_INVALID")
        allowed[key] = str(row["public_key_sha256"])

    trust_keys = {
        "schema_version",
        "kind",
        "trust_store_id",
        "root_id",
        "issued_at",
        "expires_at",
        "keys",
        "revocations",
        "root_authorization",
    }
    if set(trust) != trust_keys:
        raise RuntimeError("V2_EXTERNAL_TRUST_STORE_KEY_CLOSURE_DRIFT")
    issued_at = _parse_utc_v2(trust.get("issued_at"), "trust.issued_at")
    expires_at = _parse_utc_v2(trust.get("expires_at"), "trust.expires_at")
    if (
        trust.get("schema_version") != 2
        or trust.get("kind") != "frontend-formal-external-trust-store-v2"
        or trust.get("root_id") != trust_root.get("root_id")
        or not isinstance(trust.get("trust_store_id"), str)
        or not trust["trust_store_id"]
        or not root_valid_from <= issued_at <= now < expires_at <= root_valid_until
    ):
        raise RuntimeError("V2_EXTERNAL_TRUST_STORE_IDENTITY_OR_TIME_DRIFT")
    trust_revocations = trust.get("revocations")
    if not isinstance(trust_revocations, dict) or set(trust_revocations) != {
        "key_ids",
        "organization_ids",
        "updated_at",
    }:
        raise RuntimeError("V2_EXTERNAL_TRUST_REVOCATION_CLOSURE_DRIFT")
    trust_revocation_time = _parse_utc_v2(
        trust_revocations.get("updated_at"), "trust.revocations.updated_at"
    )
    if trust_revocation_time > now:
        raise RuntimeError("V2_EXTERNAL_TRUST_REVOCATION_TIME_INVALID")
    trust_key_ids = trust_revocations.get("key_ids")
    trust_organization_ids = trust_revocations.get("organization_ids")
    if (
        not isinstance(trust_key_ids, list)
        or not all(isinstance(value, str) and value for value in trust_key_ids)
        or len(trust_key_ids) != len(set(trust_key_ids))
        or not isinstance(trust_organization_ids, list)
        or not all(
            isinstance(value, str) and value for value in trust_organization_ids
        )
        or len(trust_organization_ids) != len(set(trust_organization_ids))
    ):
        raise RuntimeError("V2_EXTERNAL_TRUST_REVOCATION_LIST_INVALID")
    revoked_keys = root_revoked_keys | set(trust_key_ids)
    revoked_orgs = root_revoked_orgs | set(trust_organization_ids)

    authorization = trust.get("root_authorization")
    if not isinstance(authorization, dict) or set(authorization) != {
        "root_key_id",
        "algorithm",
        "signed_payload_sha256",
        "signature_base64",
    }:
        raise RuntimeError("V2_EXTERNAL_TRUST_ROOT_AUTHORIZATION_MISSING")
    signer = signer_by_id.get(str(authorization.get("root_key_id")))
    unsigned_trust = dict(trust)
    unsigned_trust.pop("root_authorization", None)
    unsigned_bytes = canonical_bytes(unsigned_trust)
    if (
        authorization.get("algorithm") != "ed25519"
        or authorization.get("signed_payload_sha256") != digest_bytes(unsigned_bytes)
        or not isinstance(signer, dict)
    ):
        raise RuntimeError("V2_EXTERNAL_TRUST_ROOT_AUTHORIZATION_DRIFT")
    _verify_ed25519_v2(
        public_key_pem=str(signer.get("public_key_pem")),
        signature_base64=str(authorization.get("signature_base64")),
        payload=unsigned_bytes,
        label="TRUST_STORE_ROOT_AUTHORIZATION",
    )

    keys = trust.get("keys")
    if not isinstance(keys, list) or len(keys) < 4:
        raise RuntimeError("V2_EXTERNAL_TRUST_KEYS_MISSING")
    key_by_id: dict[str, dict[str, Any]] = {}
    for row in keys:
        if not isinstance(row, dict) or set(row) != {
            "key_id",
            "organization_id",
            "roles",
            "public_key_pem",
            "valid_from",
            "valid_until",
            "revoked",
        }:
            raise RuntimeError("V2_EXTERNAL_TRUST_KEY_DRIFT")
        key_id = str(row.get("key_id"))
        organization_id = str(row.get("organization_id"))
        roles = row.get("roles")
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
        ):
            raise RuntimeError(f"V2_EXTERNAL_TRUST_KEY_INVALID:{key_id}")
        valid_from = _parse_utc_v2(row.get("valid_from"), f"trust.key:{key_id}:from")
        valid_until = _parse_utc_v2(row.get("valid_until"), f"trust.key:{key_id}:until")
        public_digest = _external_public_key_digest_v2(row.get("public_key_pem"))
        if not valid_from <= issued_at <= now < valid_until:
            raise RuntimeError(f"V2_EXTERNAL_TRUST_KEY_TIME_DRIFT:{key_id}")
        for role in roles:
            if allowed.get((organization_id, key_id, str(role))) != public_digest:
                raise RuntimeError(
                    f"V2_EXTERNAL_TRUST_KEY_NOT_EXTERNALLY_ALLOWLISTED:{organization_id}:{key_id}:{role}"
                )
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
        raise RuntimeError("V2_EXTERNAL_REPLAY_VERIFIER_IDENTITY_MISSING")
    verifier_path = Path(str(verifier.get("path")))
    if (
        not verifier_path.is_absolute()
        or not verifier_path.is_file()
        or verifier_path.resolve(strict=True).as_posix() != verifier.get("realpath")
    ):
        raise RuntimeError("V2_EXTERNAL_REPLAY_VERIFIER_PATH_DRIFT")
    verifier_bytes = verifier_path.read_bytes()
    if (
        verifier.get("sha256") != digest_bytes(verifier_bytes)
        or verifier.get("bytes") != len(verifier_bytes)
    ):
        raise RuntimeError("V2_EXTERNAL_REPLAY_VERIFIER_BYTES_DRIFT")
    version = subprocess.run(
        [str(verifier_path.resolve(strict=True)), "--version"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if version.returncode or version.stdout.strip() != verifier.get("version"):
        raise RuntimeError("V2_EXTERNAL_REPLAY_VERIFIER_VERSION_DRIFT")
    return {
        "root_id": trust_root["root_id"],
        "key_by_id": key_by_id,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "revoked_key_ids": revoked_keys,
        "revoked_organization_ids": revoked_orgs,
        "replay_verifier": verifier,
    }


def _run_external_replay_verifier_v2(
    *,
    verifier: dict[str, Any],
    intake_path: Path,
    trust_store_path: Path,
    artifact_root: Path,
    scope_digest: str,
    execution_ids: set[str],
    replay_ids: set[str],
    raw_ids: set[str],
) -> dict[str, Any]:
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
    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError("V2_EXTERNAL_REPLAY_VERIFIER_OUTPUT_INVALID") from exc
    expected = {
        "schema_version": 2,
        "kind": "frontend-formal-external-replay-verifier-result-v2",
        "verifier_id": verifier["verifier_id"],
        "scope_digest": scope_digest,
        "intake_sha256": digest_bytes(intake_path.read_bytes()),
        "trust_store_sha256": digest_bytes(trust_store_path.read_bytes()),
        "verified_execution_artifact_ids": sorted(execution_ids),
        "verified_replay_artifact_ids": sorted(replay_ids),
        "verified_raw_artifact_ids": sorted(raw_ids),
        "verified_route_block_count": 72 * len(SEMANTIC_BLOCKS),
        "status": "PASSED",
    }
    if completed.returncode or result != expected:
        raise RuntimeError("V2_EXTERNAL_REPLAY_VERIFIER_FAILED_OR_INCOMPLETE")
    return result
def _external_actuals_v2(
    *,
    path: Path,
    scope_digest: str,
    route_id: str,
    block_id: str,
    profile_id: str,
    case_ids: set[str],
) -> tuple[dict[str, dict[str, Any]], str]:
    """Load a typed runtime observation and return independently comparable actuals."""

    payload = load_json(path)
    expected_keys = {
        "schema_version",
        "kind",
        "scope_digest",
        "route_id",
        "block_id",
        "profile_id",
        "corpus_case_ids",
        "observer_protocol",
        "model_values_used_as_actual",
        "actuals",
    }
    rows = payload.get("actuals")
    if (
        set(payload) != expected_keys
        or payload.get("schema_version") != 2
        or payload.get("kind") != "frontend-formal-runtime-observation-v2"
        or payload.get("scope_digest") != scope_digest
        or payload.get("route_id") != route_id
        or payload.get("block_id") != block_id
        or payload.get("profile_id") != profile_id
        or set(payload.get("corpus_case_ids", [])) != case_ids
        or payload.get("observer_protocol")
        != "block-specific-runtime-observation-v1"
        or payload.get("model_values_used_as_actual") is not False
        or not isinstance(rows, list)
        or len(rows) != len(case_ids)
    ):
        raise RuntimeError("V2_EXTERNAL_RUNTIME_OBSERVATION_STRUCTURE_DRIFT")
    actuals: dict[str, dict[str, Any]] = {}
    required_actual_keys = RUNTIME_ACTUAL_KEYS_V2[block_id]
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"case_id", "actual"}:
            raise RuntimeError("V2_EXTERNAL_RUNTIME_OBSERVATION_ROW_DRIFT")
        case_id = str(row.get("case_id"))
        actual = row.get("actual")
        if (
            case_id not in case_ids
            or case_id in actuals
            or not isinstance(actual, dict)
            or set(actual) != required_actual_keys
            or not external_actual_value_valid_v2(block_id, actual)
        ):
            raise RuntimeError("V2_EXTERNAL_RUNTIME_OBSERVATION_ACTUAL_DRIFT")
        actuals[case_id] = actual
    if set(actuals) != case_ids:
        raise RuntimeError("V2_EXTERNAL_RUNTIME_OBSERVATION_CASE_CLOSURE_DRIFT")
    normalized = [
        {"case_id": case_id, "actual": actuals[case_id]}
        for case_id in sorted(actuals)
    ]
    return actuals, canonical_digest(normalized)
def add_external_evidence_v2(
    *,
    pack_root: Path,
    catalog: ArtifactCatalog,
    evidence_path: Path | None,
    trust_store_path: Path | None,
    trust_root_path: Path | None,
    scope_digest: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fail closed until the independent positive protocol is implemented end to end."""

    del pack_root, catalog, scope_digest
    if evidence_path is None and trust_store_path is None and trust_root_path is None:
        return external_evidence_not_run_v2()
    if evidence_path is None or trust_store_path is None or trust_root_path is None:
        raise RuntimeError(
            "V2_EXTERNAL_EVIDENCE_TRUST_STORE_AND_EXTERNAL_ROOT_REQUIRED"
        )
    raise RuntimeError("V2_EXTERNAL_POSITIVE_PROTOCOL_NOT_IMPLEMENTED")
def add_gap_inventory_v2(
    pack_root: Path,
    catalog: ArtifactCatalog,
    *,
    route_records: list[dict[str, Any]],
    runtime_capture: dict[str, Any],
) -> str:
    channel_values = {
        channel: [
            runtime_capture.get("profile_channel_statuses", {})
            .get(profile_id, {})
            .get(channel, "NOT_RUN")
            for profile_id in PROFILE_IDS
            if channel in REQUIRED_RUNTIME_CHANNELS_V2[profile_id]
        ]
        for channel in RUNTIME_CHANNELS_V2
    }
    channel_status = {
        channel: aggregate_evidence_status_v2(values)
        for channel, values in channel_values.items()
    }
    browser_status = aggregate_evidence_status_v2(
        [str(route["browser_status"]) for route in route_records]
    )
    native_status = aggregate_evidence_status_v2(
        [
            str(route["native_status"])
            for route in route_records
            if route["native_status"] != "NOT_APPLICABLE"
        ],
        applicable=any(
            route["native_status"] != "NOT_APPLICABLE" for route in route_records
        ),
    )
    runtime_status = aggregate_evidence_status_v2(
        [str(route["runtime_status"]) for route in route_records]
    )
    wrappers: dict[str, dict[str, Any]] = {}
    formal_values: list[str] = []
    independent_values: list[str] = []
    holdout_values: list[str] = []
    representative_values: list[str] = []
    for route in route_records:
        wrapper_path = pack_root / catalog.ref(route["route_evidence_artifact_id"])[
            "path"
        ]
        wrapper = load_json(wrapper_path)
        wrappers[str(route["route_id"])] = wrapper
        for block in wrapper.get("blocks", []):
            if not isinstance(block, dict) or not isinstance(block.get("independent"), dict):
                continue
            formal_values.append(str(block.get("formal", {}).get("status")))
            independent = block["independent"]
            independent_values.append(str(independent.get("status")))
            holdout_values.append(str(independent.get("holdout_status")))
            representative_values.append(str(independent.get("representative_status")))
    independent_status = aggregate_evidence_status_v2(independent_values)
    holdout_status = aggregate_evidence_status_v2(holdout_values)
    representative_status = aggregate_evidence_status_v2(representative_values)
    formal_status = (
        formal_values[0]
        if formal_values and all(item == formal_values[0] for item in formal_values)
        else "MIXED"
    )
    formal_reason = (
        "bounded Z3 encoding with an assumption-free proof claim"
        if formal_status == "PROVED"
        else "bounded Z3 encoding under explicit assumptions"
        if formal_status == "PROVED_UNDER_ASSUMPTIONS"
        else "formal block results are incomplete or inconsistent"
    )
    lines = [
        "# Frontend v2 formal-equivalence gap inventory",
        "",
        (
            "This inventory is exact for 9 profiles, 72 directed routes, 12 "
            "semantic blocks and 18 scenarios. Model/formal proof claims are kept "
            "separate from actual runtime and independent evidence."
        ),
        "",
        "| dimension | status | blocking reason |",
        "| --- | --- | --- |",
        "| model | PASSED | bounded same-engine relift model only |",
        f"| formal | {formal_status} | {formal_reason} |",
        f"| browser | {browser_status} | derived from applicable endpoint channels and route cross-channel closure |",
        (
            f"| native | {native_status} | derived from applicable native "
            "endpoints and native-to-native route closure only |"
        ),
        f"| android | {channel_status['android']} | derived from exact applicable Android profile channels |",
        f"| ios | {channel_status['ios']} | derived from exact applicable iOS profile channels |",
        f"| harmonyos | {channel_status['harmonyos']} | derived from the exact HarmonyOS profile channel |",
        (
            f"| runtime | {runtime_status} | all required endpoint observations "
            "plus channel-specific canonical projections |"
        ),
        (
            f"| independent | {independent_status} | derived from signed external "
            "route/block evidence; same producer never upgrades this dimension |"
        ),
        f"| holdout | {holdout_status} | derived from independently attested holdout corpus provenance |",
        (
            f"| representative | {representative_status} | derived from "
            "independently attested representative workload provenance |"
        ),
        "",
        "| route | block | model | formal | browser | android | ios | harmonyos | independent | certification |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for route in route_records:
        wrapper = wrappers[str(route["route_id"])]
        block_index = {
            str(item["block_id"]): item
            for item in wrapper.get("blocks", [])
            if isinstance(item, dict)
        }
        for block_id in SEMANTIC_BLOCKS:
            block = block_index[block_id]
            block_runtime = block["runtime"]
            browser_values: list[str] = []
            android_values: list[str] = []
            ios_values: list[str] = []
            harmony_values: list[str] = []
            for endpoint in ("source", "target"):
                endpoint_runtime = block_runtime[endpoint]
                for channel in endpoint_runtime["required_runtime_channels"]:
                    value = endpoint_runtime["channels"][channel]["status"]
                    {
                        "browser": browser_values,
                        "android": android_values,
                        "ios": ios_values,
                        "harmonyos": harmony_values,
                    }[channel].append(value)
            cross_dimensions = block_runtime["cross_channel_equivalence"][
                "dimension_closure"
            ]
            if browser_values and cross_dimensions["browser"]["applicable"]:
                browser_values.append(cross_dimensions["browser"]["status"])
            if cross_dimensions["native"]["applicable"]:
                if android_values:
                    android_values.append(cross_dimensions["native"]["status"])
                if ios_values:
                    ios_values.append(cross_dimensions["native"]["status"])
                if harmony_values:
                    harmony_values.append(cross_dimensions["native"]["status"])
            dimensions = [
                aggregate_evidence_status_v2(
                    browser_values, applicable=bool(browser_values)
                ),
                aggregate_evidence_status_v2(
                    android_values, applicable=bool(android_values)
                ),
                aggregate_evidence_status_v2(ios_values, applicable=bool(ios_values)),
                aggregate_evidence_status_v2(
                    harmony_values, applicable=bool(harmony_values)
                ),
            ]
            lines.append(
                f"<!-- frontend-v2-gap-row route={route['route_id']} block={block_id} -->"
            )
            lines.append(
                f"| {route['route_id']} | {block_id} | PASSED | {block['formal']['status']} | "
                + " | ".join(dimensions)
                + f" | {block['independent']['status']} | NOT_CERTIFIED |"
            )
    relative = "certification/gap-inventory.md"
    destination = pack_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    artifact_relative = "formal-campaign/certification/gap-inventory.md"
    artifact_path = pack_root / artifact_relative
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(destination, artifact_path)
    identifier = artifact_identifier("v2-gap", "gap-inventory.md")
    catalog.add(identifier, "frontend-gap-inventory-v2", artifact_relative)
    return identifier


def _runtime_evidence_file_v2(root: Path, relative: object, label: str) -> Path:
    value = safe_relative(relative, label)
    current = root
    for part in Path(value).parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError(f"V2_RUNTIME_SYMLINK_FORBIDDEN:{label}:{value}")
    try:
        resolved = (root / value).resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise RuntimeError(f"V2_RUNTIME_ARTIFACT_MISSING_OR_ESCAPED:{label}:{value}") from exc
    if not resolved.is_file():
        raise RuntimeError(f"V2_RUNTIME_ARTIFACT_FILE_REQUIRED:{label}:{value}")
    return resolved


def _copy_runtime_ref_v2(
    *,
    evidence_root: Path,
    pack_root: Path,
    catalog: ArtifactCatalog,
    profile_id: str,
    channel: str,
    reference: dict[str, Any],
    role: str,
) -> tuple[str, dict[str, Any]]:
    runner_id = reference.get("artifact_id")
    if not isinstance(runner_id, str) or runner_id != canonical_digest(
        {key: value for key, value in reference.items() if key != "artifact_id"}
    ):
        raise RuntimeError(
            f"V2_RUNTIME_ARTIFACT_ID_DRIFT:{profile_id}:{channel}:{runner_id}"
        )
    source = _runtime_evidence_file_v2(
        evidence_root,
        reference.get("path"),
        f"{profile_id}:{channel}:{runner_id}",
    )
    content = source.read_bytes()
    if (
        reference.get("sha256") != digest_bytes(content)
        or reference.get("byte_count") != len(content)
        or not content
    ):
        raise RuntimeError(
            f"V2_RUNTIME_ARTIFACT_BYTES_DRIFT:{profile_id}:{channel}:{runner_id}"
        )
    payload = load_json(source)
    relative_source = PurePosixPath(str(reference.get("path")))
    if (
        len(relative_source.parts) < 2
        or relative_source.suffix != ".json"
        or relative_source.stem
        != str(reference.get("sha256", "")).removeprefix("sha256:")
        or content
        != (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
    ):
        raise RuntimeError(
            f"V2_RUNTIME_CONTENT_ADDRESS_OR_ENCODING_DRIFT:{profile_id}:{channel}:{runner_id}"
        )
    relative = (
        f"formal-campaign/toolchain/runtime-evidence/{profile_id}/{channel}/"
        + safe_relative(reference["path"], f"runtime_ref:{runner_id}")
    )
    destination = pack_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    catalog.add(runner_id, role, relative)
    return runner_id, payload


def _exact_runtime_mapping_v2(
    value: object, keys: set[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise RuntimeError(f"V2_BLOCK_OBSERVER_MEASUREMENT_KEYS_DRIFT:{label}")
    return value


def _contains_model_shaped_runtime_value_v2(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower()
            in {"actual", "expected", "model", "projection", "observation", "blocks"}
            or _contains_model_shaped_runtime_value_v2(nested)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_contains_model_shaped_runtime_value_v2(item) for item in value)
    return False


def _runtime_observer_string_v2(
    value: object, label: str, *, nullable: bool = False
) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"V2_BLOCK_OBSERVER_STRING_INVALID:{label}")
    return value


def _runtime_observer_bool_v2(value: object, label: str) -> bool:
    if type(value) is bool:
        return value
    if value == "true":
        return True
    if value == "false":
        return False
    raise RuntimeError(f"V2_BLOCK_OBSERVER_BOOL_INVALID:{label}")


def _runtime_observer_int_v2(value: object, label: str) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"-?(?:0|[1-9][0-9]*)", value):
        return int(value)
    raise RuntimeError(f"V2_BLOCK_OBSERVER_INT_INVALID:{label}")


def _runtime_css_grid_track_count_v2(value: object, label: str) -> int:
    if not isinstance(value, str) or not value.strip() or value.strip() == "none":
        raise RuntimeError(f"V2_BLOCK_OBSERVER_GRID_TRACKS_INVALID:{label}")
    source = value.strip()
    repeated = re.fullmatch(r"repeat\(\s*([1-9][0-9]*)\s*,[\s\S]+\)", source)
    if repeated is not None:
        return int(repeated.group(1))
    depth = 0
    tracks: list[str] = []
    start = 0
    for index, character in enumerate(source):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                raise RuntimeError(
                    f"V2_BLOCK_OBSERVER_GRID_TRACKS_INVALID:{label}"
                )
        elif character.isspace() and depth == 0:
            if source[start:index].strip():
                tracks.append(source[start:index].strip())
            start = index + 1
    if depth != 0:
        raise RuntimeError(f"V2_BLOCK_OBSERVER_GRID_TRACKS_INVALID:{label}")
    if source[start:].strip():
        tracks.append(source[start:].strip())
    if not tracks:
        raise RuntimeError(f"V2_BLOCK_OBSERVER_GRID_TRACKS_INVALID:{label}")
    return len(tracks)


def runtime_actual_from_block_measurement_v2(
    *,
    block_id: str,
    value: object,
    label: str,
    scenario_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = BLOCK_OBSERVER_SPECS_V2[block_id]
    measured = _exact_runtime_mapping_v2(
        value, set(spec["measurement_keys"]), label
    )
    if _contains_model_shaped_runtime_value_v2(measured):
        raise RuntimeError(f"V2_BLOCK_OBSERVER_MODEL_SHAPED_PAYLOAD:{label}")
    exact = lambda nested, keys, suffix: _exact_runtime_mapping_v2(  # noqa: E731
        nested, set(keys), f"{label}.{suffix}"
    )
    string = lambda nested, suffix, nullable=False: _runtime_observer_string_v2(  # noqa: E731
        nested, f"{label}.{suffix}", nullable=nullable
    )
    boolean = lambda nested, suffix: _runtime_observer_bool_v2(  # noqa: E731
        nested, f"{label}.{suffix}"
    )
    integer = lambda nested, suffix: _runtime_observer_int_v2(  # noqa: E731
        nested, f"{label}.{suffix}"
    )
    if block_id == "route-navigation-deeplink-404":
        if not isinstance(measured["page_url"], str) or not re.match(
            r"^https?://", measured["page_url"]
        ):
            raise RuntimeError(f"V2_BLOCK_OBSERVER_URL_INVALID:{label}")
        attrs = exact(
            measured["active_route_attributes"],
            {
                "data-route-id",
                "data-route-path",
                "data-deep-link",
                "data-requires-auth",
            },
            "active_route_attributes",
        )
        selected_path = string(attrs["data-route-path"], "selected_path")
        if (urlsplit(measured["page_url"]).path or "/") != selected_path:
            raise RuntimeError(f"V2_BLOCK_OBSERVER_ROUTE_URL_MISMATCH:{label}")
        if not isinstance(scenario_input, dict):
            raise RuntimeError(f"V2_BLOCK_OBSERVER_SCENARIO_INPUT_MISSING:{label}")
        requested_path = scenario_input.get("routePath")
        if not isinstance(requested_path, str) or not requested_path.startswith("/"):
            raise RuntimeError(f"V2_BLOCK_OBSERVER_ROUTE_INPUT_INVALID:{label}")
        declared_value = measured["declared_routes"]
        if not isinstance(declared_value, list) or not declared_value:
            raise RuntimeError(f"V2_BLOCK_OBSERVER_DECLARED_ROUTES_EMPTY:{label}")
        declared_routes: list[dict[str, Any]] = []
        for index, row in enumerate(declared_value):
            route = exact(
                row,
                {"route_id", "route_path", "deep_link", "requires_auth"},
                f"declared_routes[{index}]",
            )
            if (
                not isinstance(route["route_id"], str)
                or not route["route_id"]
                or not isinstance(route["route_path"], str)
                or not route["route_path"].startswith("/")
                or type(route["deep_link"]) is not bool
                or type(route["requires_auth"]) is not bool
            ):
                raise RuntimeError(
                    f"V2_BLOCK_OBSERVER_DECLARED_ROUTE_INVALID:{label}:{index}"
                )
            declared_routes.append(route)
        if (
            len({route["route_id"] for route in declared_routes})
            != len(declared_routes)
            or len({route["route_path"] for route in declared_routes})
            != len(declared_routes)
        ):
            raise RuntimeError(f"V2_BLOCK_OBSERVER_DECLARED_ROUTE_DUPLICATE:{label}")
        selected_route_id = string(attrs["data-route-id"], "route_id")
        requested_route = next(
            (
                route
                for route in declared_routes
                if route["route_path"] == requested_path
            ),
            None,
        )
        first_route = declared_routes[0]
        if requested_route is None:
            resolution = "FIRST_DECLARED_FALLBACK"
            if (
                selected_path != first_route["route_path"]
                or selected_route_id != first_route["route_id"]
            ):
                raise RuntimeError(
                    f"V2_BLOCK_OBSERVER_ROUTE_FALLBACK_MISMATCH:{label}"
                )
        elif selected_path == requested_path:
            resolution = "DECLARED"
            if selected_route_id != requested_route["route_id"]:
                raise RuntimeError(f"V2_BLOCK_OBSERVER_ROUTE_ID_MISMATCH:{label}")
        else:
            exact_tenant = (
                isinstance(scenario_input.get("tenantId"), str)
                and scenario_input.get("tenantId")
                == scenario_input.get("resourceTenantId")
            )
            authorized = (
                not requested_route["requires_auth"]
                or (
                    scenario_input.get("authenticated") is True
                    and scenario_input.get("permissionGranted") is True
                    and exact_tenant
                )
            )
            if authorized:
                raise RuntimeError(
                    f"V2_BLOCK_OBSERVER_AUTHORIZED_ROUTE_FALLBACK:{label}"
                )
            resolution = "AUTH_DENIED_FALLBACK"
            if (
                selected_path != first_route["route_path"]
                or selected_route_id != first_route["route_id"]
            ):
                raise RuntimeError(
                    f"V2_BLOCK_OBSERVER_DENIED_ROUTE_FALLBACK_MISMATCH:{label}"
                )
        return {
            "requestedPath": requested_path,
            "selectedRouteId": selected_route_id,
            "selectedPath": selected_path,
            "resolution": resolution,
            "deepLink": boolean(attrs["data-deep-link"], "deep_link"),
            "requiresAuth": boolean(attrs["data-requires-auth"], "requires_auth"),
        }
    if block_id == "component-template-view":
        attrs = exact(
            measured["attributes"],
            {
                "id",
                "data-route-id",
                "data-elmos-active-component",
                "data-elmos-component-id",
                "data-elmos-component-key",
            },
            "attributes",
        )
        heading = string(measured["heading"], "heading")
        text_value = string(measured["text"], "text")
        if (
            attrs["id"] != "main"
            or attrs["data-elmos-active-component"] != "true"
            or attrs["data-route-id"] != attrs["data-elmos-component-key"]
            or not heading
            or not text_value
            or type(measured["visibility"]) is not bool
        ):
            raise RuntimeError(f"V2_BLOCK_OBSERVER_COMPONENT_SURFACE_INVALID:{label}")
        return {
            "componentId": string(attrs["data-elmos-component-id"], "component_id"),
            "key": string(attrs["data-elmos-component-key"], "component_key"),
            "title": heading,
            "text": text_value,
            "visible": boolean(measured["visibility"], "visibility"),
        }
    if block_id == "state-management":
        state = exact(
            measured["state_measurement"],
            {
                "data-elmos-state-id",
                "data-elmos-before",
                "data-elmos-after",
                "data-elmos-saturated",
            },
            "state_measurement",
        )
        return {
            "stateId": string(state["data-elmos-state-id"], "state_id"),
            "before": integer(state["data-elmos-before"], "before"),
            "after": integer(state["data-elmos-after"], "after"),
            "saturated": boolean(state["data-elmos-saturated"], "saturated"),
        }
    if block_id == "action-event":
        events = measured["captured_events"]
        outcome = exact(
            measured["outcome_attributes"],
            {
                "data-elmos-event-outcome",
                "data-elmos-keyboard-key",
                "data-elmos-handled",
                "data-elmos-action",
            },
            "outcome_attributes",
        )
        if (
            not isinstance(events, list)
            or not events
            or any(not isinstance(event, dict) for event in events)
            or not any(
                event.get("type") in {"click", "keydown", "submit"}
                for event in events
            )
        ):
            raise RuntimeError(f"V2_BLOCK_OBSERVER_NATIVE_EVENT_MISSING:{label}")
        return {
            "event": string(outcome["data-elmos-event-outcome"], "event"),
            "keyboardKey": string(outcome["data-elmos-keyboard-key"], "keyboard_key"),
            "handled": boolean(outcome["data-elmos-handled"], "handled"),
            "action": string(outcome["data-elmos-action"], "action"),
        }
    if block_id == "effect-lifecycle":
        events = measured["ordered_events"]
        if not isinstance(events, list) or not events:
            raise RuntimeError(f"V2_BLOCK_OBSERVER_LIFECYCLE_EMPTY:{label}")
        normalized = [
            exact(
                event,
                {"lifecycle", "effect", "executions", "cleanup", "stale_response_ignored"},
                f"ordered_events[{index}]",
            )
            for index, event in enumerate(events)
        ]
        event = normalized[-1]
        return {
            "lifecycle": string(event["lifecycle"], "lifecycle"),
            "effect": string(event["effect"], "effect"),
            "executions": integer(event["executions"], "executions"),
            "cleanup": boolean(event["cleanup"], "cleanup"),
            "staleResponseIgnored": boolean(
                event["stale_response_ignored"], "stale_response_ignored"
            ),
        }
    if block_id == "form-binding-validation":
        control = exact(measured["control"], {"form_id", "field_id", "value"}, "control")
        validity = exact(measured["validity_state"], {"submitted", "valid"}, "validity")
        error = exact(measured["error_dom"], {"error_code"}, "error_dom")
        exact(measured["active_element"], {"focus_target"}, "active_element")
        return {
            "formId": string(control["form_id"], "form_id"),
            "fieldId": string(control["field_id"], "field_id"),
            "value": string(control["value"], "value"),
            "submitted": boolean(validity["submitted"], "submitted"),
            "valid": boolean(validity["valid"], "valid"),
            "errorCode": string(error["error_code"], "error_code", True),
        }
    if block_id == "api-network":
        events = measured["network_events"]
        markers = exact(
            measured["application_markers"],
            {"operation_id", "called", "method", "path", "outcome", "canceled", "stale_ignored", "cache_key"},
            "application_markers",
        )
        if not isinstance(events, list):
            raise RuntimeError(f"V2_BLOCK_OBSERVER_NETWORK_EVENTS_INVALID:{label}")
        called = boolean(markers["called"], "called")
        canceled = boolean(markers["canceled"], "canceled")
        method = string(markers["method"], "method")
        path = string(markers["path"], "path")
        matching = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("kind") == "request"
            and event.get("method") == method
            and isinstance(event.get("url"), str)
            and re.sub(r"^https?://[^/]+", "", event["url"]).split("?", 1)[0] == path
        ]
        if called != bool(matching) or (
            canceled
            and not any(
                isinstance(event, dict)
                and event.get("kind") in {"requestfailed", "fixture-aborted"}
                for event in events
            )
        ):
            raise RuntimeError(f"V2_BLOCK_OBSERVER_NETWORK_CONTRADICTION:{label}")
        return {
            "operationId": string(markers["operation_id"], "operation_id"),
            "called": called,
            "method": method,
            "path": path,
            "outcome": string(markers["outcome"], "outcome"),
            "canceled": canceled,
            "staleIgnored": boolean(markers["stale_ignored"], "stale_ignored"),
            "cacheKey": string(markers["cache_key"], "cache_key"),
        }
    if block_id == "identity-permission":
        if not isinstance(measured["adapter_events"], list) or not measured["adapter_events"]:
            raise RuntimeError(f"V2_BLOCK_OBSERVER_AUTHORITY_ADAPTER_MISSING:{label}")
        decision = exact(
            measured["decision_attributes"],
            {"role", "permission", "permission_granted", "tenant_match", "authorized", "server_authority_required"},
            "decision_attributes",
        )
        return {
            "role": string(decision["role"], "role"),
            "permission": string(decision["permission"], "permission"),
            "permissionGranted": boolean(decision["permission_granted"], "permission_granted"),
            "tenantMatch": boolean(decision["tenant_match"], "tenant_match"),
            "authorized": boolean(decision["authorized"], "authorized"),
            "serverAuthorityRequired": boolean(decision["server_authority_required"], "server_authority_required"),
        }
    if block_id == "rendering-hydration":
        if (
            not isinstance(measured["server_markup_digest"], str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", measured["server_markup_digest"])
            or not isinstance(measured["hydration_warnings"], list)
            or not isinstance(measured["mutations"], list)
            or type(measured["effect_count"]) is not int
            or measured["effect_count"] < 0
        ):
            raise RuntimeError(f"V2_BLOCK_OBSERVER_HYDRATION_INVALID:{label}")
        state = exact(
            measured["hydration_state"],
            {"mode", "requested", "status", "duplicate_effects", "mismatch_visible"},
            "hydration_state",
        )
        return {
            "mode": string(state["mode"], "mode"),
            "requested": string(state["requested"], "requested"),
            "status": string(state["status"], "status"),
            "duplicateEffects": boolean(state["duplicate_effects"], "duplicate_effects"),
            "mismatchVisible": boolean(state["mismatch_visible"], "mismatch_visible"),
        }
    if block_id == "accessibility-focus":
        active_element = measured["active_element"]
        keyboard_events = measured["keyboard_events"]
        if (
            not isinstance(measured["aria_snapshot"], str)
            or not measured["aria_snapshot"].strip()
            or not isinstance(measured["axe_results"], dict)
            or not isinstance(measured["axe_results"].get("violations"), list)
            or any(
                isinstance(item, dict) and item.get("impact") in {"serious", "critical"}
                for item in measured["axe_results"]["violations"]
            )
            or not isinstance(active_element, dict)
            or set(active_element) != {"tag", "attributes"}
            or not isinstance(active_element.get("tag"), str)
            or not isinstance(active_element.get("attributes"), dict)
            or not isinstance(keyboard_events, list)
            or any(not isinstance(event, dict) for event in keyboard_events)
        ):
            raise RuntimeError(f"V2_BLOCK_OBSERVER_ACCESSIBILITY_INVALID:{label}")
        state = exact(
            measured["accessibility_state"],
            {
                "main_role",
                "heading_level",
                "form_label",
                "error_role",
                "live_region",
                "focus_target",
                "keyboard_submit",
            },
            "accessibility_state",
        )
        main_role = string(state["main_role"], "main_role")
        heading_level = integer(state["heading_level"], "heading_level")
        form_label = string(state["form_label"], "form_label")
        error_role = string(state["error_role"], "error_role", True)
        live_region = string(state["live_region"], "live_region")
        active_id = active_element["attributes"].get("id")
        focus_target = (
            "query"
            if active_id == "elmos-query"
            else "result"
            if active_id == "elmos-result"
            else None
        )
        keyboard_submit = any(
            event.get("type") == "keydown"
            and event.get("key") == "Enter"
            and isinstance(event.get("target"), dict)
            and isinstance(event["target"].get("attributes"), dict)
            and isinstance(
                event["target"]["attributes"].get("data-run-scenario"), str
            )
            for event in keyboard_events
        )
        if (
            main_role != "main"
            or heading_level not in range(1, 7)
            or not form_label
            or error_role not in {None, "alert"}
            or live_region not in {"off", "polite", "assertive"}
            or state["focus_target"] != focus_target
            or boolean(state["keyboard_submit"], "keyboard_submit")
            != keyboard_submit
            or "main" not in measured["aria_snapshot"].lower()
            or "heading" not in measured["aria_snapshot"].lower()
        ):
            raise RuntimeError(f"V2_BLOCK_OBSERVER_ACCESSIBILITY_CONTRADICTION:{label}")
        return {
            "mainRole": main_role,
            "headingLevel": heading_level,
            "formLabel": form_label,
            "errorRole": error_role,
            "liveRegion": live_region,
            "keyboardSubmit": keyboard_submit,
            "focusTarget": focus_target,
        }
    if block_id == "i18n-theme-responsive":
        translated = exact(measured["translated_text"], {"requested_locale", "text"}, "translated_text")
        theme = exact(measured["computed_theme_tokens"], {"requested_theme", "theme"}, "theme")
        layout = exact(
            measured["layout_measurement"],
            {
                "viewport_width",
                "columns",
                "computed_grid_template_columns",
                "bounding_box",
            },
            "layout",
        )
        bounding_box = exact(
            layout["bounding_box"], {"x", "y", "width", "height"}, "bounding_box"
        )
        requested_locale = string(translated["requested_locale"], "requested_locale")
        requested_theme = string(theme["requested_theme"], "requested_theme")
        viewport_width = integer(layout["viewport_width"], "viewport_width")
        columns = integer(layout["columns"], "columns")
        if (
            not isinstance(scenario_input, dict)
            or not isinstance(measured["html_lang"], str)
            or not measured["html_lang"]
            or requested_locale != scenario_input.get("locale")
            or requested_theme != scenario_input.get("theme")
            or viewport_width != scenario_input.get("viewportWidth")
            or not isinstance(translated["text"], str)
            or not translated["text"].strip()
            or any(
                type(item) not in {int, float} or not math.isfinite(item)
                for item in bounding_box.values()
            )
            or bounding_box["width"] <= 0
            or bounding_box["height"] <= 0
            or columns < 1
            or columns
            != _runtime_css_grid_track_count_v2(
                layout["computed_grid_template_columns"],
                f"{label}.computed_grid_template_columns",
            )
        ):
            raise RuntimeError(f"V2_BLOCK_OBSERVER_I18N_LAYOUT_INVALID:{label}")
        return {
            "requestedLocale": requested_locale,
            "locale": string(measured["html_lang"], "locale"),
            "requestedTheme": requested_theme,
            "theme": string(theme["theme"], "theme"),
            "viewportWidth": viewport_width,
            "columns": columns,
        }
    if block_id == "native-platform":
        semantics = exact(
            measured["semantics"],
            {"boundary", "attempted", "available", "outcome", "recovery"},
            "semantics",
        )
        if (
            not isinstance(measured["adapter_events"], list)
            or not measured["adapter_events"]
            or not isinstance(measured["device_identity"], dict)
            or not measured["device_identity"]
        ):
            raise RuntimeError(f"V2_BLOCK_OBSERVER_NATIVE_TRACE_MISSING:{label}")
        return {
            "boundary": string(semantics["boundary"], "boundary"),
            "lifecycle": string(measured["lifecycle"], "lifecycle"),
            "attempted": boolean(semantics["attempted"], "attempted"),
            "permission": string(measured["permission"], "permission"),
            "available": boolean(semantics["available"], "available"),
            "outcome": string(semantics["outcome"], "outcome"),
            "recovery": string(semantics["recovery"], "recovery"),
        }
    raise RuntimeError(f"V2_BLOCK_OBSERVER_UNKNOWN:{block_id}")


def load_scenario_inputs_v2(
    *,
    engine_root: Path,
    scenario_manifest: dict[str, Any],
    scenario_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Load the byte-bound scenario inputs used by runtime route projection."""

    source = safe_source_file(
        engine_root,
        scenario_manifest.get("source_path"),
        "v2_scenario_manifest_source",
    )
    content = source.read_bytes()
    if (
        scenario_manifest.get("source_sha256") != digest_bytes(content)
        or scenario_manifest.get("source_byte_count") != len(content)
    ):
        raise RuntimeError("V2_ENGINE_SCENARIO_SOURCE_BYTES_DRIFT")
    payload = load_json(source)
    if (
        set(payload)
        != {
            "schema_version",
            "kind",
            "proof_profile",
            "source_kind",
            "scenarios",
            "arbitrary_customer_source",
            "external_runtime_evidence",
        }
        or payload.get("schema_version") != "1.0"
        or payload.get("kind") != "bounded-frontend-interaction-scenario-corpus"
        or payload.get("proof_profile") != "bounded-frontend-interaction-v1"
        or payload.get("arbitrary_customer_source") != "NOT_PROVED"
        or payload.get("external_runtime_evidence") != "NOT_RUN"
    ):
        raise RuntimeError("V2_ENGINE_SCENARIO_SOURCE_IDENTITY_DRIFT")
    rows = payload.get("scenarios")
    if (
        not isinstance(rows, list)
        or [
            row.get("scenarioId") if isinstance(row, dict) else None
            for row in rows
        ]
        != scenario_ids
    ):
        raise RuntimeError("V2_ENGINE_SCENARIO_SOURCE_CLOSURE_DRIFT")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"scenarioId", "input"}
            or not isinstance(row.get("input"), dict)
        ):
            raise RuntimeError("V2_ENGINE_SCENARIO_SOURCE_ROW_DRIFT")
        result[str(row["scenarioId"])] = dict(row["input"])
    return result


def _runtime_scope_contract_v2(
    *,
    profile_id: str,
    channel: str,
    required: bool,
    record: dict[str, Any],
) -> dict[str, Any]:
    """Normalize the runner-owned capability matrix into the signed scope.

    Runtime status is intentionally retained: a later execution cannot inherit
    a browser/tool matrix (or its bytes) from an earlier campaign scope.
    """

    status = str(record.get("status"))
    active_runtime = status == "PASSED" or (
        status == "NOT_RUN"
        and record.get("reason") == "BLOCK_SPECIFIC_RUNTIME_PARTIAL_CLOSURE"
    )
    runtime_tools = record.get("runtime_tools")
    normalized_tools: list[dict[str, Any]] = []
    if active_runtime:
        if not isinstance(runtime_tools, list) or not runtime_tools:
            raise RuntimeError(
                f"V2_RUNTIME_SCOPE_TOOLS_MISSING:{profile_id}:{channel}"
            )
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
                raise RuntimeError(
                    f"V2_RUNTIME_SCOPE_TOOL_DRIFT:{profile_id}:{channel}:{index}"
                )
            if (
                not isinstance(item.get("role"), str)
                or not item["role"]
                or not isinstance(item.get("path"), str)
                or not Path(item["path"]).is_absolute()
                or not isinstance(item.get("realpath"), str)
                or not Path(item["realpath"]).is_absolute()
                or type(item.get("byte_count")) is not int
                or item["byte_count"] < 1
                or not isinstance(item.get("version"), str)
                or not item["version"]
                or not isinstance(item.get("sha256"), str)
                or len(item["sha256"]) != 71
                or not item["sha256"].startswith("sha256:")
                or not isinstance(item.get("package_closure_digest"), str)
                or len(item["package_closure_digest"]) != 71
                or not item["package_closure_digest"].startswith("sha256:")
            ):
                raise RuntimeError(
                    f"V2_RUNTIME_SCOPE_TOOL_IDENTITY_INVALID:{profile_id}:{channel}:{index}"
                )
            tool_path = Path(item["path"])
            try:
                tool_realpath = tool_path.resolve(strict=True)
                tool_bytes = tool_realpath.read_bytes()
            except (OSError, RuntimeError) as exc:
                raise RuntimeError(
                    f"V2_RUNTIME_SCOPE_TOOL_BYTES_UNAVAILABLE:{profile_id}:{channel}:{index}"
                ) from exc
            if (
                not tool_realpath.is_file()
                or not os.access(tool_realpath, os.X_OK)
                or tool_realpath.as_posix() != item["realpath"]
                or digest_bytes(tool_bytes) != item["sha256"]
                or len(tool_bytes) != item["byte_count"]
            ):
                raise RuntimeError(
                    f"V2_RUNTIME_SCOPE_TOOL_BYTES_DRIFT:{profile_id}:{channel}:{index}"
                )
            normalized_tools.append(
                {
                    "role": item["role"],
                    "path": item["path"],
                    "realpath": item["realpath"],
                    "version": item["version"],
                    "sha256": item["sha256"],
                    "byte_count": item["byte_count"],
                    "package_closure_digest": item["package_closure_digest"],
                }
            )
        tool_roles = [item["role"] for item in normalized_tools]
        if len(tool_roles) != len(set(tool_roles)):
            raise RuntimeError(
                f"V2_RUNTIME_SCOPE_TOOL_ROLE_COLLISION:{profile_id}:{channel}"
            )
    elif runtime_tools not in ([], None):
        # A non-PASS channel may report discovery diagnostics, but it cannot
        # publish runtime tool bytes as certification-capable execution scope.
        normalized_tools = []

    browser_matrix: dict[str, Any] | None = None
    if channel == "browser" and active_runtime:
        discovery = record.get("tool_discovery")
        rows = (
            [
                item
                for item in discovery
                if isinstance(item, dict) and item.get("kind") == "EXACT_BROWSER_MATRIX"
            ]
            if isinstance(discovery, list)
            else []
        )
        if len(rows) != 1:
            raise RuntimeError(f"V2_BROWSER_MATRIX_MISSING:{profile_id}")
        matrix = rows[0]
        values = matrix.get("browser_matrix")
        if not isinstance(values, list):
            raise RuntimeError(f"V2_BROWSER_MATRIX_INVALID:{profile_id}")
        tools_by_role = {item["role"]: item for item in normalized_tools}
        if profile_id == "flutter":
            if (
                set(matrix)
                != {
                    "kind",
                    "policy_id",
                    "browser_matrix",
                    "cross_browser",
                    "capability_scope",
                }
                or matrix.get("policy_id") != "flutter-web-cft-chrome-drive-v1"
                or matrix.get("cross_browser") is not False
                or matrix.get("capability_scope")
                != "flutter-web-chrome-drive-only"
                or len(values) != 1
                or not isinstance(values[0], dict)
                or set(values[0])
                != {
                    "browser_id",
                    "engine",
                    "version",
                    "executable_sha256",
                    "driver_version",
                    "driver_sha256",
                }
                or values[0].get("browser_id") != "cft-chrome"
                or values[0].get("engine") != "chromium"
                or values[0].get("version") != "151.0.7922.77"
                or values[0].get("driver_version") != "151.0.7922.77"
                or values[0].get("executable_sha256")
                != tools_by_role.get("flutter-cft-chrome", {}).get("sha256")
                or values[0].get("driver_sha256")
                != tools_by_role.get("flutter-cft-chromedriver", {}).get("sha256")
                or any(
                    not isinstance(values[0].get(key), str)
                    or len(values[0][key]) != 71
                    or not values[0][key].startswith("sha256:")
                    for key in ("executable_sha256", "driver_sha256")
                )
            ):
                raise RuntimeError(f"V2_FLUTTER_BROWSER_MATRIX_DRIFT:{profile_id}")
        else:
            if (
                set(matrix)
                != {
                    "kind",
                    "policy_id",
                    "browser_matrix",
                    "cross_browser",
                }
                or matrix.get("policy_id") != "node-web-chromium-firefox-v1"
                or matrix.get("cross_browser") is not True
                or len(values) != 2
                or any(
                    not isinstance(value, dict)
                    or set(value)
                    != {"browser_id", "engine", "version", "executable_sha256"}
                    or not isinstance(value.get("version"), str)
                    or not value["version"]
                    or not isinstance(value.get("executable_sha256"), str)
                    or len(value["executable_sha256"]) != 71
                    or not value["executable_sha256"].startswith("sha256:")
                    for value in values
                )
                or [
                    (value.get("browser_id"), value.get("engine")) for value in values
                ]
                != [("google-chrome", "chromium"), ("mozilla-firefox", "firefox")]
                or any(
                    value.get("executable_sha256")
                    != tools_by_role.get(
                        f"browser-{value.get('engine')}", {}
                    ).get("sha256")
                    for value in values
                )
            ):
                raise RuntimeError(f"V2_NODE_BROWSER_MATRIX_DRIFT:{profile_id}")
        digests = {
            tool["sha256"] for tool in normalized_tools if "sha256" in tool
        }
        matrix_digests = {
            value.get("executable_sha256") for value in values if isinstance(value, dict)
        } | {
            value.get("driver_sha256")
            for value in values
            if isinstance(value, dict) and value.get("driver_sha256") is not None
        }
        if (
            any(
                not isinstance(value, str) or not value.startswith("sha256:")
                for value in matrix_digests
            )
            or not matrix_digests.issubset(digests)
        ):
            raise RuntimeError(f"V2_BROWSER_MATRIX_TOOL_DIGEST_DRIFT:{profile_id}")
        browser_matrix = {
            key: matrix[key]
            for key in (
                "policy_id",
                "browser_matrix",
                "cross_browser",
                "capability_scope",
            )
            if key in matrix
        }
        browser_matrix["fingerprint"] = canonical_digest(browser_matrix)

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


def _validate_flutter_raw_proof_v2(
    *,
    payload: dict[str, Any],
    profile_execution: dict[str, Any],
    record: dict[str, Any],
    channel: str,
    scenario_ids: list[str],
    profile_manifest_digest: str,
    scenario_manifest_digest: str,
    observations: dict[tuple[str, str], dict[str, Any]],
) -> None:
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
    environment = journey.get("environment") if isinstance(journey, dict) else None
    if (
        set(payload) != top_keys
        or payload.get("schema_version") != "1.0"
        or payload.get("kind")
        != "bounded-frontend-interaction-flutter-runtime-trace"
        or payload.get("proof_profile") != "bounded-frontend-interaction-v1"
        or payload.get("profile_id") != "flutter"
        or payload.get("channel") != channel
        or payload.get("project_digest") != profile_execution.get("project_digest")
        or payload.get("profile_manifest_digest") != profile_manifest_digest
        or payload.get("scenario_manifest_digest") != scenario_manifest_digest
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
        raise RuntimeError(f"V2_FLUTTER_RAW_PROOF_IDENTITY_DRIFT:{channel}")
    for digest_name in ("profile_manifest_digest", "scenario_manifest_digest"):
        value = payload.get(digest_name)
        if (
            not isinstance(value, str)
            or len(value) != 71
            or not value.startswith("sha256:")
        ):
            raise RuntimeError(
                f"V2_FLUTTER_RAW_PROOF_DIGEST_INVALID:{channel}:{digest_name}"
            )
    scenarios = payload.get("scenarios")
    if (
        not isinstance(scenarios, list)
        or [
            row.get("scenario_id") if isinstance(row, dict) else None
            for row in scenarios
        ]
        != scenario_ids
    ):
        raise RuntimeError(f"V2_FLUTTER_RAW_PROOF_SCENARIO_CLOSURE:{channel}")
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
    for row in scenarios:
        scenario_id = str(row.get("scenario_id"))
        blocks = row.get("blocks")
        sequence = row.get("execution_sequence")
        network = row.get("network_adapter_events")
        platform = row.get("platform_adapter_events")
        focus = row.get("focus")
        evidence_refs = row.get("evidence_refs")
        if (
            set(row) != scenario_keys
            or type(sequence) is not int
            or sequence <= prior_sequence
            or row.get("execution_state") != "COMPLETE"
            or row.get("runtime_source") != "flutter-framework-events"
            or not isinstance(row.get("framework_events"), list)
            or not row["framework_events"]
            or not isinstance(row.get("semantics_label"), str)
            or not row["semantics_label"]
            or not isinstance(focus, dict)
            or set(focus) != {"target", "query_has_focus"}
            or not isinstance(network, list)
            or not isinstance(platform, list)
            or not isinstance(evidence_refs, dict)
            or set(evidence_refs) != {"semantics", "network", "platform"}
            or evidence_refs.get("semantics") != "INLINE_INTEGRATION_BINDING"
            or not isinstance(blocks, dict)
            or set(blocks) != set(SEMANTIC_BLOCKS)
        ):
            raise RuntimeError(
                f"V2_FLUTTER_RAW_PROOF_SCENARIO_DRIFT:{channel}:{scenario_id}"
            )
        prior_sequence = sequence
        network_count += len(network)
        platform_count += len(platform)
        if (evidence_refs.get("network") is None) != (len(network) == 0):
            raise RuntimeError(
                f"V2_FLUTTER_NETWORK_EVIDENCE_REF_DRIFT:{channel}:{scenario_id}"
            )
        if (evidence_refs.get("platform") is None) != (len(platform) == 0):
            raise RuntimeError(
                f"V2_FLUTTER_PLATFORM_EVIDENCE_REF_DRIFT:{channel}:{scenario_id}"
            )
        for block_id in SEMANTIC_BLOCKS:
            actual = blocks[block_id]
            observed = observations.get((scenario_id, block_id), {}).get("actual")
            if (
                not isinstance(actual, dict)
                or set(actual) != RUNTIME_ACTUAL_KEYS_V2[block_id]
                or actual != observed
            ):
                raise RuntimeError(
                    f"V2_FLUTTER_RAW_ACTUAL_DRIFT:{channel}:{scenario_id}:{block_id}"
                )
        native_actual = blocks["native-platform"]
        if native_actual.get("attempted") is True:
            native_attempt_count += 1
    summary = payload.get("summary")
    expected_summary = {
        "scenario_count": len(scenario_ids),
        "block_count": len(SEMANTIC_BLOCKS),
        "all_complete": True,
        "network_adapter_event_count": network_count,
        "platform_adapter_event_count": platform_count,
    }
    if summary != expected_summary or network_count < 1:
        raise RuntimeError(f"V2_FLUTTER_RAW_PROOF_SUMMARY_DRIFT:{channel}")
    if channel == "browser":
        if platform_count != 0 or native_attempt_count != 0:
            raise RuntimeError("V2_FLUTTER_BROWSER_NATIVE_PROJECTION_DRIFT")
    elif channel in {"android", "ios"} and (
        platform_count < 1 or native_attempt_count < 1
    ):
        raise RuntimeError(f"V2_FLUTTER_NATIVE_ADAPTER_NOT_OBSERVED:{channel}")


def _validate_playwright_raw_proof_v2(
    *,
    payload: dict[str, Any],
    profile_execution: dict[str, Any],
    record: dict[str, Any],
    scenario_ids: list[str],
    scenario_inputs: dict[str, dict[str, Any]],
    observations: dict[tuple[str, str], dict[str, Any]],
    block_statuses: dict[str, dict[str, Any]],
) -> None:
    partial = any(
        row.get("status") == "NOT_RUN" for row in block_statuses.values()
    )
    expected_top_status = "NOT_RUN" if partial else "PASSED"
    expected_scenario_status = "PARTIAL" if partial else "PASSED"
    expected_reason = (
        "BLOCK_SPECIFIC_RUNTIME_PARTIAL_CLOSURE" if partial else None
    )
    expected_scenario_manifest_digest = canonical_digest(
        [
            {"scenario_id": scenario_id, "input": scenario_inputs[scenario_id]}
            for scenario_id in scenario_ids
        ]
    )
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
    matrix = matrix_rows[0].get("browser_matrix") if len(matrix_rows) == 1 else None
    tools = record.get("runtime_tools")
    tools_by_role = {
        str(row.get("role")): row
        for row in tools
        if isinstance(row, dict) and isinstance(row.get("role"), str)
    } if isinstance(tools, list) else {}
    if not isinstance(matrix, list) or len(matrix) != 2:
        raise RuntimeError(
            f"V2_PLAYWRIGHT_RAW_BROWSER_SCOPE_MISSING:{profile_execution.get('profile_id')}"
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
        or payload.get("kind") != "frontend-interaction-playwright-probe-result"
        or payload.get("profile_id") != profile_execution.get("profile_id")
        or payload.get("project_digest") != profile_execution.get("project_digest")
        or payload.get("proof_profile") != "bounded-frontend-interaction-v1"
        or payload.get("scenario_manifest_digest")
        != expected_scenario_manifest_digest
        or payload.get("semantic_block_ids") != list(SEMANTIC_BLOCKS)
        or payload.get("model_values_accepted_as_actual") is not False
        or payload.get("external_network") != "BLOCKED"
        or payload.get("status") != expected_top_status
        or payload.get("reason") != expected_reason
    ):
        raise RuntimeError(
            f"V2_PLAYWRIGHT_RAW_PROOF_IDENTITY_DRIFT:{profile_execution.get('profile_id')}"
        )
    browser_runs = payload.get("browser_runs")
    if (
        not isinstance(browser_runs, list)
        or [
            (row.get("browser_id"), row.get("engine"))
            if isinstance(row, dict)
            else None
            for row in browser_runs
        ]
        != [("google-chrome", "chromium"), ("mozilla-firefox", "firefox")]
    ):
        raise RuntimeError(
            f"V2_PLAYWRIGHT_BROWSER_MATRIX_DRIFT:{profile_execution.get('profile_id')}"
        )
    for browser, matrix_row in zip(browser_runs, matrix, strict=True):
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
                "browser_id",
                "engine",
                "executable",
                "browser_version",
                "status",
                "reason",
                "scenario_count",
                "scenarios",
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
                row.get("scenario_id") if isinstance(row, dict) else None
                for row in scenarios
            ]
            != scenario_ids
        ):
            raise RuntimeError(
                f"V2_PLAYWRIGHT_SCENARIO_CLOSURE_DRIFT:{profile_execution.get('profile_id')}"
            )
        for row in scenarios:
            scenario_id = str(row.get("scenario_id"))
            blocks = row.get("block_observations")
            if (
                set(row)
                != {
                    "scenario_id",
                    "status",
                    "reason",
                    "checks",
                    "runtime_metadata",
                    "block_observations",
                    "browser_events",
                    "network_events",
                    "console_events",
                    "page_errors",
                    "active_element",
                    "aria_snapshot",
                    "aria_error",
                    "axe",
                    "axe_error",
                    "raw_dom",
                    "raw_dom_sha256",
                    "capture_errors",
                }
                or row.get("status") != expected_scenario_status
                or row.get("reason") != expected_reason
                or not isinstance(blocks, dict)
                or set(blocks) != set(SEMANTIC_BLOCKS)
                or not isinstance(row.get("raw_dom"), str)
                or not row["raw_dom"]
                or row.get("raw_dom_sha256")
                != digest_bytes(row["raw_dom"].encode("utf-8"))
                or not isinstance(row.get("checks"), dict)
                or not row["checks"]
                or any(value is not True for value in row["checks"].values())
                or not isinstance(row.get("browser_events"), list)
                or not row["browser_events"]
                or not isinstance(row.get("network_events"), list)
                or not isinstance(row.get("console_events"), list)
                or row.get("page_errors") != []
                or row.get("capture_errors") != []
                or not isinstance(row.get("aria_snapshot"), str)
                or not row["aria_snapshot"]
                or row.get("aria_error") is not None
                or not isinstance(row.get("axe"), dict)
                or row.get("axe_error") is not None
                or not isinstance(row.get("runtime_metadata"), dict)
                or set(row["runtime_metadata"])
                != {"execution_state", "execution_sequence", "runtime_source"}
                or row["runtime_metadata"].get("execution_state")
                != ("PARTIAL" if partial else "COMPLETE")
                or row["runtime_metadata"].get("runtime_source")
                != "BLOCK_SPECIFIC_RUNTIME_OBSERVED"
                or not isinstance(
                    row["runtime_metadata"].get("execution_sequence"), str
                )
                or not re.fullmatch(
                    r"[1-9][0-9]*",
                    row["runtime_metadata"]["execution_sequence"],
                )
            ):
                raise RuntimeError(
                    f"V2_PLAYWRIGHT_ACTUAL_TRACE_INCOMPLETE:{profile_execution.get('profile_id')}:{scenario_id}"
                )
            for block_id in SEMANTIC_BLOCKS:
                block = blocks[block_id]
                spec = BLOCK_OBSERVER_SPECS_V2[block_id]
                declared = block_statuses[block_id]
                if not isinstance(block, dict) or set(block) != {
                    "status",
                    "actual_source",
                    "observer_kind",
                    "measurement_surface",
                    "measurement",
                    "measurement_digest",
                    "model_values_used_as_actual",
                    "reason",
                }:
                    raise RuntimeError(
                        f"V2_PLAYWRIGHT_RAW_ACTUAL_DRIFT:{profile_execution.get('profile_id')}:{scenario_id}:{block_id}"
                    )
                common_valid = (
                    block.get("status") == declared["status"]
                    and block.get("observer_kind") == spec["observer_kind"]
                    and block.get("measurement_surface")
                    == spec["measurement_surface"]
                    and block.get("model_values_used_as_actual") is False
                )
                if declared["status"] == "NOT_RUN":
                    if (
                        not common_valid
                        or block.get("actual_source") != "NOT_RUN"
                        or block.get("measurement") is not None
                        or block.get("measurement_digest") is not None
                        or block.get("reason") != declared["reason"]
                        or (scenario_id, block_id) in observations
                    ):
                        raise RuntimeError(
                            f"V2_PLAYWRIGHT_RAW_NOT_RUN_DRIFT:{profile_execution.get('profile_id')}:{scenario_id}:{block_id}"
                        )
                    continue
                measurement = block.get("measurement")
                try:
                    actual = runtime_actual_from_block_measurement_v2(
                        block_id=block_id,
                        value=measurement,
                        label=f"raw:{profile_execution.get('profile_id')}:{scenario_id}:{block_id}",
                        scenario_input=scenario_inputs.get(scenario_id),
                    )
                except RuntimeError as exc:
                    raise RuntimeError(
                        f"V2_PLAYWRIGHT_RAW_MEASUREMENT_DRIFT:{profile_execution.get('profile_id')}:{scenario_id}:{block_id}"
                    ) from exc
                if (
                    not common_valid
                    or block.get("actual_source")
                    != "BLOCK_SPECIFIC_RUNTIME_OBSERVED"
                    or block.get("measurement_digest")
                    != canonical_digest(measurement)
                    or block.get("reason") is not None
                    or actual
                    != observations.get((scenario_id, block_id), {}).get("actual")
                ):
                    raise RuntimeError(
                        f"V2_PLAYWRIGHT_RAW_ACTUAL_DRIFT:{profile_execution.get('profile_id')}:{scenario_id}:{block_id}"
                    )


def pack_runtime_evidence_v2(
    *,
    pack_root: Path,
    catalog: ArtifactCatalog,
    raw: dict[str, Any],
    scenario_ids: list[str],
    scenario_inputs: dict[str, dict[str, Any]],
    runtime_driver_contracts: dict[str, dict[str, Any]],
    profile_manifest_digests: dict[str, str],
    scenario_manifest_digest: str,
) -> dict[str, Any]:
    """Capture every runner-owned runtime byte and reconstruct its exact closure."""

    executions = raw.get("profile_executions")
    if not isinstance(executions, list) or len(executions) != len(PROFILE_IDS):
        raise RuntimeError("V2_RUNTIME_PROFILE_EXECUTION_CLOSURE_DRIFT")
    profiles: dict[str, dict[str, Any]] = {}
    packed_ids: list[str] = []
    channel_statuses: dict[str, dict[str, str]] = {}
    channel_contracts: dict[str, dict[str, dict[str, Any]]] = {}
    for profile in executions:
        if not isinstance(profile, dict):
            raise RuntimeError("V2_RUNTIME_PROFILE_EXECUTION_INVALID")
        profile_id = str(profile.get("profile_id"))
        if profile_id not in PROFILE_IDS or profile_id in profiles:
            raise RuntimeError(f"V2_RUNTIME_PROFILE_IDENTITY_DRIFT:{profile_id}")
        driver_contract = runtime_driver_contracts.get(profile_id)
        if not isinstance(driver_contract, dict):
            raise RuntimeError(f"V2_RUNTIME_DRIVER_CONTRACT_MISSING:{profile_id}")
        declared_browser_blocks = browser_block_status_contract_v2(
            profile_id=profile_id,
            driver=driver_contract,
        )
        declared_native_blocks = native_block_status_ceiling_v2(
            profile_id=profile_id,
            driver=driver_contract,
        )
        observations = profile.get("runtime_observations")
        if not isinstance(observations, dict) or set(observations) != set(
            RUNTIME_CHANNELS_V2
        ):
            raise RuntimeError(f"V2_RUNTIME_CHANNEL_CLOSURE_DRIFT:{profile_id}")
        normalized_channels: dict[str, dict[str, Any]] = {}
        channel_statuses[profile_id] = {}
        channel_contracts[profile_id] = {}
        for channel in RUNTIME_CHANNELS_V2:
            record = observations[channel]
            if not isinstance(record, dict) or set(record) != RUNTIME_CHANNEL_RECORD_KEYS_V2:
                raise RuntimeError(f"V2_RUNTIME_CHANNEL_INVALID:{profile_id}:{channel}")
            required = channel in REQUIRED_RUNTIME_CHANNELS_V2[profile_id]
            status = record.get("status")
            if (
                record.get("channel") != channel
                or record.get("required") is not required
                or status not in {"PASSED", "FAILED", "NOT_RUN", "NOT_APPLICABLE"}
                or (required and status == "NOT_APPLICABLE")
                or (not required and status != "NOT_APPLICABLE")
                or record.get("model_values_used_as_actual") is not False
            ):
                raise RuntimeError(
                    f"V2_RUNTIME_CHANNEL_STATUS_OR_APPLICABILITY_DRIFT:{profile_id}:{channel}"
                )
            channel_statuses[profile_id][channel] = str(status)
            channel_contracts[profile_id][channel] = _runtime_scope_contract_v2(
                profile_id=profile_id,
                channel=channel,
                required=required,
                record=record,
            )
            empty = {
                "status": status,
                "reason": record.get("reason"),
                "runner_kind": record.get("runner_kind"),
                "observations": {},
                "block_statuses": {},
                "observation_artifact_ids": [],
                "runtime_source_artifact_ids": [],
                "result_manifest_artifact_id": None,
                "execution_policy_artifact_id": None,
                "raw_probe_artifact_ids": [],
                "build_execution_id": None,
                "startup_execution_id": None,
                "journey_execution_id": None,
                "artifact_ids": [],
            }
            partial_runtime = (
                required
                and status == "NOT_RUN"
                and record.get("reason") == "BLOCK_SPECIFIC_RUNTIME_PARTIAL_CLOSURE"
            )
            if status != "PASSED" and not partial_runtime:
                normalized_channels[channel] = empty
                continue
            if profile.get("runtime_model_oracle_findings"):
                raise RuntimeError(
                    f"V2_RUNTIME_MODEL_ORACLE_CONSUMED:{profile_id}:{channel}"
                )

            discovery = record.get("tool_discovery")
            if not isinstance(discovery, list):
                raise RuntimeError(
                    f"V2_RUNTIME_DISCOVERY_MISSING:{profile_id}:{channel}"
                )
            root_rows = [
                item
                for item in discovery
                if isinstance(item, dict) and item.get("kind") == "RUNTIME_EVIDENCE_ROOT"
            ]
            if len(root_rows) != 1 or not isinstance(root_rows[0].get("path"), str):
                raise RuntimeError(
                    f"V2_RUNTIME_EVIDENCE_ROOT_CLOSURE_DRIFT:{profile_id}:{channel}"
                )
            evidence_root_source = Path(root_rows[0]["path"])
            if evidence_root_source.is_symlink():
                raise RuntimeError(
                    f"V2_RUNTIME_EVIDENCE_ROOT_INVALID:{profile_id}:{channel}"
                )
            evidence_root = evidence_root_source.resolve(strict=True)
            if not evidence_root.is_dir():
                raise RuntimeError(
                    f"V2_RUNTIME_EVIDENCE_ROOT_INVALID:{profile_id}:{channel}"
                )

            semantic_blocks = record.get("semantic_blocks")
            if not isinstance(semantic_blocks, dict) or set(semantic_blocks) != set(
                SEMANTIC_BLOCKS
            ):
                raise RuntimeError(
                    f"V2_RUNTIME_SEMANTIC_BLOCK_CLOSURE_DRIFT:{profile_id}:{channel}"
                )
            passed_block_ids: list[str] = []
            not_run_block_ids: list[str] = []
            block_statuses: dict[str, dict[str, Any]] = {}
            for block_id in SEMANTIC_BLOCKS:
                block = semantic_blocks[block_id]
                if not isinstance(block, dict) or set(block) != {
                    "status",
                    "reason",
                    "observation_refs",
                    "observation_digest",
                }:
                    raise RuntimeError(
                        f"V2_RUNTIME_SEMANTIC_BLOCK_KEYS_DRIFT:{profile_id}:{channel}:{block_id}"
                    )
                block_status = block.get("status")
                refs = block.get("observation_refs")
                if (
                    block_status == "PASSED"
                    and block.get("reason") is None
                    and isinstance(refs, list)
                    and len(refs) == len(scenario_ids)
                    and block.get("observation_digest") == canonical_digest(refs)
                ):
                    passed_block_ids.append(block_id)
                elif (
                    block_status == "NOT_RUN"
                    and isinstance(block.get("reason"), str)
                    and block["reason"]
                    and refs == []
                    and block.get("observation_digest") == canonical_digest([])
                ):
                    not_run_block_ids.append(block_id)
                else:
                    raise RuntimeError(
                        f"V2_RUNTIME_SEMANTIC_BLOCK_STATUS_DRIFT:{profile_id}:{channel}:{block_id}"
                    )
                block_statuses[block_id] = {
                    "status": str(block_status),
                    "reason": block.get("reason"),
                }
            if status == "PASSED" and not_run_block_ids:
                raise RuntimeError(
                    f"V2_RUNTIME_CHANNEL_PASS_WITH_NOT_RUN_BLOCKS:{profile_id}:{channel}"
                )
            validate_observed_block_statuses_v2(
                profile_id=profile_id,
                channel=channel,
                observed=block_statuses,
                browser_ceiling=declared_browser_blocks,
                native_ceiling=declared_native_blocks,
            )
            if partial_runtime and (
                channel != "browser"
                or record.get("runner_kind") != "PLAYWRIGHT_BROWSER_INTERACTION"
                or not passed_block_ids
                or not not_run_block_ids
            ):
                raise RuntimeError(
                    f"V2_RUNTIME_PARTIAL_BLOCK_MATRIX_DRIFT:{profile_id}:{channel}"
                )

            source_payloads: dict[str, dict[str, Any]] = {}
            source_references: dict[str, dict[str, Any]] = {}
            derived_block_actuals: dict[str, list[dict[str, Any]]] = {}
            source_ids: list[str] = []
            matrix_rows = [
                item
                for item in discovery
                if isinstance(item, dict) and item.get("kind") == "EXACT_BROWSER_MATRIX"
            ]
            expected_browser_ids = (
                [
                    str(item.get("browser_id"))
                    for item in matrix_rows[0].get("browser_matrix", [])
                    if isinstance(item, dict)
                ]
                if len(matrix_rows) == 1
                and isinstance(matrix_rows[0].get("browser_matrix"), list)
                else []
            )
            source_refs = record.get("runtime_source_artifacts")
            if not isinstance(source_refs, list) or not source_refs:
                raise RuntimeError(
                    f"V2_RUNTIME_SOURCE_ARTIFACTS_MISSING:{profile_id}:{channel}"
                )
            for reference in source_refs:
                if not isinstance(reference, dict):
                    raise RuntimeError("V2_RUNTIME_SOURCE_REF_INVALID")
                role = str(reference.get("role"))
                is_block_trace = "block_id" in reference or "observer_kind" in reference
                expected_reference_keys = (
                    {
                        "artifact_id",
                        "role",
                        "profile_id",
                        "channel",
                        "scenario_id",
                        "block_id",
                        "observer_kind",
                        "path",
                        "sha256",
                        "byte_count",
                    }
                    if is_block_trace
                    else {
                        "artifact_id",
                        "role",
                        "profile_id",
                        "channel",
                        "scenario_id",
                        "path",
                        "sha256",
                        "byte_count",
                    }
                )
                if set(reference) != expected_reference_keys:
                    raise RuntimeError(
                        f"V2_RUNTIME_TRACE_REF_UNION_DRIFT:{profile_id}:{channel}:{role}"
                    )
                identifier, payload = _copy_runtime_ref_v2(
                    evidence_root=evidence_root,
                    pack_root=pack_root,
                    catalog=catalog,
                    profile_id=profile_id,
                    channel=channel,
                    reference=reference,
                    role=(
                        f"runtime-block-observer-trace-v2:{role}"
                        if is_block_trace
                        else f"runtime-trace-v2:{role}"
                    ),
                )
                if identifier in source_payloads:
                    raise RuntimeError(
                        f"V2_RUNTIME_SOURCE_ARTIFACT_REUSE:{profile_id}:{channel}:{identifier}"
                    )
                if is_block_trace:
                    block_id = str(reference.get("block_id"))
                    scenario_id = str(reference.get("scenario_id"))
                    spec = BLOCK_OBSERVER_SPECS_V2.get(block_id)
                    capture = payload.get("capture")
                    if (
                        channel != "browser"
                        or record.get("runner_kind") != "PLAYWRIGHT_BROWSER_INTERACTION"
                        or not isinstance(spec, dict)
                        or block_id not in passed_block_ids
                        or scenario_id not in scenario_ids
                        or set(payload)
                        != {
                            "schema_version",
                            "kind",
                            "actual_source",
                            "role",
                            "profile_id",
                            "channel",
                            "scenario_id",
                            "block_id",
                            "observer_kind",
                            "capture",
                        }
                        or payload.get("schema_version") != "1.0"
                        or payload.get("kind")
                        != "frontend-interaction-block-observer-trace-artifact"
                        or payload.get("actual_source")
                        != "ALLOWLISTED_BLOCK_OBSERVER_CAPTURE"
                        or payload.get("role") != spec.get("trace_role")
                        or payload.get("role") != role
                        or payload.get("profile_id") != profile_id
                        or payload.get("channel") != channel
                        or payload.get("scenario_id") != scenario_id
                        or payload.get("block_id") != block_id
                        or payload.get("observer_kind") != spec.get("observer_kind")
                        or reference.get("observer_kind") != spec.get("observer_kind")
                        or not isinstance(capture, dict)
                        or set(capture)
                        != {"observer_contract", "measurement_surface", "browser_matrix"}
                        or capture.get("observer_contract") != BLOCK_OBSERVER_CONTRACT_V2
                        or capture.get("measurement_surface")
                        != spec.get("measurement_surface")
                    ):
                        raise RuntimeError(
                            f"V2_RUNTIME_BLOCK_TRACE_PAYLOAD_DRIFT:{profile_id}:{channel}:{identifier}"
                        )
                    browser_matrix = capture.get("browser_matrix")
                    if (
                        not isinstance(browser_matrix, list)
                        or [
                            row.get("browser_id") if isinstance(row, dict) else None
                            for row in browser_matrix
                        ]
                        != expected_browser_ids
                        or not expected_browser_ids
                    ):
                        raise RuntimeError(
                            f"V2_RUNTIME_BLOCK_TRACE_MATRIX_DRIFT:{profile_id}:{channel}:{identifier}"
                        )
                    derived_values: list[dict[str, Any]] = []
                    for matrix_index, row in enumerate(browser_matrix):
                        if not isinstance(row, dict) or set(row) != {
                            "browser_id",
                            "measurement",
                        }:
                            raise RuntimeError(
                                f"V2_RUNTIME_BLOCK_TRACE_MATRIX_ROW_DRIFT:{identifier}:{matrix_index}"
                            )
                        derived_values.append(
                            runtime_actual_from_block_measurement_v2(
                                block_id=block_id,
                                value=row["measurement"],
                                label=f"{identifier}:{matrix_index}",
                                scenario_input=scenario_inputs.get(
                                    str(reference.get("scenario_id"))
                                ),
                            )
                        )
                    if any(value != derived_values[0] for value in derived_values[1:]):
                        raise RuntimeError(
                            f"V2_RUNTIME_BLOCK_TRACE_CROSS_BROWSER_DIVERGENCE:{identifier}"
                        )
                    derived_block_actuals[identifier] = derived_values
                elif (
                    set(payload)
                    != {
                        "schema_version",
                        "kind",
                        "actual_source",
                        "role",
                        "profile_id",
                        "channel",
                        "scenario_id",
                        "capture",
                    }
                    or payload.get("schema_version") != "1.0"
                    or payload.get("kind")
                    != "frontend-interaction-runtime-trace-artifact"
                    or payload.get("actual_source") != "ALLOWLISTED_RUNTIME_CAPTURE"
                    or payload.get("role") != role
                    or payload.get("profile_id") != profile_id
                    or payload.get("channel") != channel
                ):
                    raise RuntimeError(
                        f"V2_RUNTIME_TRACE_PAYLOAD_DRIFT:{profile_id}:{channel}:{identifier}"
                    )
                source_ids.append(identifier)
                source_payloads[identifier] = payload
                source_references[identifier] = reference
                packed_ids.append(identifier)

            observation_ids: list[str] = []
            observations_by_key: dict[tuple[str, str], dict[str, Any]] = {}
            observation_refs_by_key: dict[tuple[str, str], dict[str, Any]] = {}
            used_observer_trace_ids: set[str] = set()
            used_source_trace_ids: set[str] = set()
            raw_refs = record.get("raw_artifacts")
            if not isinstance(raw_refs, list) or len(raw_refs) != len(
                scenario_ids
            ) * len(passed_block_ids):
                raise RuntimeError(
                    f"V2_RUNTIME_OBSERVATION_COUNT_DRIFT:{profile_id}:{channel}"
                )
            for reference in raw_refs:
                if not isinstance(reference, dict) or set(reference) != {
                    "artifact_id",
                    "role",
                    "profile_id",
                    "channel",
                    "scenario_id",
                    "block_id",
                    "path",
                    "sha256",
                    "byte_count",
                    "actual_digest",
                }:
                    raise RuntimeError("V2_RUNTIME_OBSERVATION_REF_INVALID")
                identifier, payload = _copy_runtime_ref_v2(
                    evidence_root=evidence_root,
                    pack_root=pack_root,
                    catalog=catalog,
                    profile_id=profile_id,
                    channel=channel,
                    reference=reference,
                    role="runtime-block-observation-v2",
                )
                scenario_id = str(reference.get("scenario_id"))
                block_id = str(reference.get("block_id"))
                actual = payload.get("actual")
                provenance = payload.get("provenance")
                if (
                    set(payload)
                    != {
                        "schema_version",
                        "kind",
                        "actual_source",
                        "profile_id",
                        "channel",
                        "scenario_id",
                        "block_id",
                        "provenance",
                        "actual",
                    }
                    or payload.get("schema_version") != "1.0"
                    or payload.get("kind")
                    != "frontend-interaction-runtime-block-observation"
                    or payload.get("actual_source")
                    != "BLOCK_SPECIFIC_RUNTIME_OBSERVED"
                    or payload.get("profile_id") != profile_id
                    or payload.get("channel") != channel
                    or scenario_id not in scenario_ids
                    or block_id not in passed_block_ids
                    or not isinstance(actual, dict)
                    or set(actual) != RUNTIME_ACTUAL_KEYS_V2[block_id]
                    or reference.get("actual_digest") != canonical_digest(actual)
                    or not isinstance(provenance, dict)
                    or set(provenance)
                    != {
                        "runner_kind",
                        "observer_contract",
                        "observer_kind",
                        "measurement_surface",
                        "observation_trace_ref",
                        "supporting_trace_refs",
                        "model_values_used_as_actual",
                    }
                    or provenance.get("runner_kind") != record.get("runner_kind")
                    or provenance.get("observer_contract")
                    != BLOCK_OBSERVER_CONTRACT_V2
                    or provenance.get("observer_kind")
                    != BLOCK_OBSERVER_SPECS_V2.get(block_id, {}).get("observer_kind")
                    or provenance.get("measurement_surface")
                    != BLOCK_OBSERVER_SPECS_V2.get(block_id, {}).get(
                        "measurement_surface"
                    )
                    or provenance.get("model_values_used_as_actual") is not False
                    or (scenario_id, block_id) in observations_by_key
                ):
                    raise RuntimeError(
                        f"V2_RUNTIME_OBSERVATION_PAYLOAD_DRIFT:{profile_id}:{channel}:{identifier}"
                    )
                observation_trace = provenance["observation_trace_ref"]
                supporting = provenance["supporting_trace_refs"]
                spec = BLOCK_OBSERVER_SPECS_V2[block_id]
                trace_id = (
                    str(observation_trace.get("artifact_id"))
                    if isinstance(observation_trace, dict)
                    else ""
                )
                expected_support_roles = tuple(spec["supporting_trace_roles"])
                if (
                    not isinstance(observation_trace, dict)
                    or set(observation_trace)
                    != {
                        "artifact_id",
                        "role",
                        "profile_id",
                        "channel",
                        "scenario_id",
                        "block_id",
                        "observer_kind",
                        "path",
                        "sha256",
                        "byte_count",
                    }
                    or source_references.get(trace_id) != observation_trace
                    or trace_id not in derived_block_actuals
                    or observation_trace.get("role") != spec["trace_role"]
                    or observation_trace.get("block_id") != block_id
                    or observation_trace.get("profile_id") != profile_id
                    or observation_trace.get("channel") != channel
                    or observation_trace.get("scenario_id") != scenario_id
                    or observation_trace.get("observer_kind") != spec["observer_kind"]
                    or trace_id in used_observer_trace_ids
                    or not isinstance(supporting, list)
                    or len(supporting) != len(expected_support_roles)
                    or any(
                        not isinstance(item, dict)
                        or set(item)
                        != {
                            "artifact_id",
                            "role",
                            "profile_id",
                            "channel",
                            "scenario_id",
                            "path",
                            "sha256",
                            "byte_count",
                        }
                        or item.get("role") != expected_role
                        or source_references.get(str(item.get("artifact_id"))) != item
                        for item, expected_role in zip(
                            supporting, expected_support_roles, strict=True
                        )
                    )
                    or actual != derived_block_actuals[trace_id][0]
                ):
                    raise RuntimeError(
                        f"V2_RUNTIME_OBSERVATION_PROVENANCE_DRIFT:{profile_id}:{channel}:{identifier}"
                    )
                used_observer_trace_ids.add(trace_id)
                used_source_trace_ids.add(trace_id)
                used_source_trace_ids.update(
                    str(item["artifact_id"]) for item in supporting
                )
                observations_by_key[(scenario_id, block_id)] = {
                    "artifact_id": identifier,
                    "actual_digest": reference["actual_digest"],
                    "actual": actual,
                }
                observation_refs_by_key[(scenario_id, block_id)] = reference
                observation_ids.append(identifier)
                packed_ids.append(identifier)
            expected_keys = {
                (scenario_id, block_id)
                for scenario_id in scenario_ids
                for block_id in passed_block_ids
            }
            if set(observations_by_key) != expected_keys:
                raise RuntimeError(
                    f"V2_RUNTIME_OBSERVATION_CLOSURE_DRIFT:{profile_id}:{channel}"
                )
            diagnostic_source_ids = {
                identifier
                for identifier, reference in source_references.items()
                if reference.get("role") == "browser-network-trace"
            }
            diagnostic_required = (
                partial_runtime
                and block_statuses.get("api-network", {}).get("status") == "NOT_RUN"
            )
            diagnostic_complete = (
                len(diagnostic_source_ids) == len(scenario_ids)
                and {
                    source_references[identifier].get("scenario_id")
                    for identifier in diagnostic_source_ids
                }
                == set(scenario_ids)
            )
            expected_diagnostic_ids = diagnostic_source_ids if diagnostic_required else set()
            if (
                (diagnostic_required and not diagnostic_complete)
                or
                diagnostic_source_ids != expected_diagnostic_ids
                or used_source_trace_ids | expected_diagnostic_ids != set(source_ids)
                or used_source_trace_ids & expected_diagnostic_ids
            ):
                raise RuntimeError(
                    f"V2_RUNTIME_SOURCE_ARTIFACT_USAGE_DRIFT:{profile_id}:{channel}"
                )

            scenarios = record.get("scenarios")
            expected_channel_reason = (
                "BLOCK_SPECIFIC_RUNTIME_PARTIAL_CLOSURE"
                if not_run_block_ids
                else None
            )
            expected_scenario_status = "NOT_RUN" if not_run_block_ids else "PASSED"
            if (
                record.get("scenario_manifest_digest")
                != canonical_digest(scenario_ids)
                or record.get("scenario_count") != len(scenario_ids)
                or not isinstance(scenarios, list)
                or [
                    row.get("scenario_id") if isinstance(row, dict) else None
                    for row in scenarios
                ]
                != scenario_ids
            ):
                raise RuntimeError(
                    f"V2_RUNTIME_SCENARIO_CLOSURE_DRIFT:{profile_id}:{channel}"
                )
            for scenario in scenarios:
                scenario_id = str(scenario.get("scenario_id"))
                scenario_statuses = scenario.get("block_statuses")
                scenario_refs = scenario.get("block_observation_refs")
                if (
                    set(scenario)
                    != {
                        "scenario_id",
                        "status",
                        "reason",
                        "block_statuses",
                        "block_observation_refs",
                    }
                    or scenario.get("status") != expected_scenario_status
                    or scenario.get("reason") != expected_channel_reason
                    or not isinstance(scenario_statuses, dict)
                    or set(scenario_statuses) != set(SEMANTIC_BLOCKS)
                    or scenario_statuses != block_statuses
                    or not isinstance(scenario_refs, dict)
                    or set(scenario_refs) != set(passed_block_ids)
                    or any(
                        scenario_refs.get(block_id)
                        != observation_refs_by_key.get((scenario_id, block_id))
                        for block_id in passed_block_ids
                    )
                ):
                    raise RuntimeError(
                        f"V2_RUNTIME_SCENARIO_STATUS_OR_REF_DRIFT:{profile_id}:{channel}:{scenario_id}"
                    )
            for block_id in SEMANTIC_BLOCKS:
                expected_ids = [
                    observation_refs_by_key[(scenario_id, block_id)]["artifact_id"]
                    for scenario_id in scenario_ids
                    if (scenario_id, block_id) in observation_refs_by_key
                ]
                if semantic_blocks[block_id].get("observation_refs") != expected_ids:
                    raise RuntimeError(
                        f"V2_RUNTIME_SEMANTIC_BLOCK_REF_DRIFT:{profile_id}:{channel}:{block_id}"
                    )

            manifest_ref = record.get("result_manifest")
            if not isinstance(manifest_ref, dict) or set(manifest_ref) != {
                "artifact_id",
                "role",
                "profile_id",
                "channel",
                "path",
                "sha256",
                "byte_count",
                "manifest_digest",
            }:
                raise RuntimeError(
                    f"V2_RUNTIME_RESULT_MANIFEST_MISSING:{profile_id}:{channel}"
                )
            manifest_id, manifest_payload = _copy_runtime_ref_v2(
                evidence_root=evidence_root,
                pack_root=pack_root,
                catalog=catalog,
                profile_id=profile_id,
                channel=channel,
                reference=manifest_ref,
                role="runtime-result-manifest-v2",
            )
            packed_ids.append(manifest_id)
            expected_manifest = {
                "schema_version": "1.0",
                "kind": "frontend-interaction-runtime-result-manifest",
                "profile_id": profile_id,
                "channel": channel,
                "scenario_ids": scenario_ids,
                "semantic_block_ids": list(SEMANTIC_BLOCKS),
                "runtime_source_artifact_ids": source_ids,
                "observation_artifact_ids": observation_ids,
                "runtime_tool_digests": [
                    item["sha256"]
                    for item in record.get("runtime_tools", [])
                    if isinstance(item, dict)
                ],
                "prerequisite_execution_ids": [
                    record.get("build_execution", {}).get("execution_id"),
                    record.get("startup_execution", {}).get("execution_id"),
                ],
                "runtime_source_artifact_count": len(source_ids),
                "observation_artifact_count": len(observation_ids),
                "passed_block_ids": passed_block_ids,
                "not_run_block_ids": not_run_block_ids,
            }
            if (
                manifest_payload != expected_manifest
                or manifest_ref.get("manifest_digest")
                != canonical_digest(manifest_payload)
            ):
                raise RuntimeError(
                    f"V2_RUNTIME_RESULT_MANIFEST_DRIFT:{profile_id}:{channel}"
                )

            policy_rows = [
                item
                for item in discovery
                if isinstance(item, dict)
                and item.get("kind") == "RUNTIME_EXECUTION_POLICY_ARTIFACT"
            ]
            if len(policy_rows) != 1:
                raise RuntimeError(
                    f"V2_RUNTIME_POLICY_CLOSURE_DRIFT:{profile_id}:{channel}"
                )
            policy_row = policy_rows[0]
            policy_source = _runtime_evidence_file_v2(
                evidence_root,
                policy_row.get("path"),
                f"{profile_id}:{channel}:policy",
            )
            policy_bytes = policy_source.read_bytes()
            policy_payload = load_json(policy_source)
            policy_relative_source = PurePosixPath(str(policy_row.get("path")))
            expected_phase_policy = {
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
                policy_row.get("sha256") != digest_bytes(policy_bytes)
                or policy_row.get("byte_count") != len(policy_bytes)
                or len(policy_relative_source.parts) < 2
                or policy_relative_source.suffix != ".json"
                or policy_relative_source.stem
                != str(policy_row.get("sha256", "")).removeprefix("sha256:")
                or policy_bytes
                != (
                    json.dumps(
                        policy_payload,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
                or policy_row.get("policy_digest") != canonical_digest(policy_payload)
                or record.get("execution_policy_digest")
                != canonical_digest(policy_payload)
                or set(policy_payload)
                != {
                    "schema_version",
                    "kind",
                    "profile_id",
                    "channel",
                    "runner_kind",
                    "phases",
                    "runtime_tools",
                }
                or policy_payload.get("schema_version") != "1.0"
                or policy_payload.get("kind")
                != "frontend-interaction-runtime-execution-policy"
                or policy_payload.get("profile_id") != profile_id
                or policy_payload.get("channel") != channel
                or policy_payload.get("runner_kind") != record.get("runner_kind")
                or policy_payload.get("phases") != expected_phase_policy
                or policy_payload.get("runtime_tools") != record.get("runtime_tools")
            ):
                raise RuntimeError(
                    f"V2_RUNTIME_POLICY_DRIFT:{profile_id}:{channel}"
                )
            policy_relative = (
                f"formal-campaign/toolchain/runtime-evidence/{profile_id}/{channel}/"
                + safe_relative(policy_row["path"], "runtime_policy")
            )
            policy_destination = pack_root / policy_relative
            policy_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(policy_source, policy_destination)
            policy_id = artifact_identifier(
                f"v2-runtime-policy-{profile_id}-{channel}", policy_row["path"]
            )
            catalog.add(policy_id, "runtime-execution-policy-v2", policy_relative)
            packed_ids.append(policy_id)

            raw_probe_ids: list[str] = []
            raw_probe_payloads: list[tuple[str, dict[str, Any]]] = []
            for row in discovery:
                if (
                    not isinstance(row, dict)
                    or row.get("kind") not in RUNTIME_RAW_PROOF_DISCOVERY_KINDS_V2
                ):
                    continue
                expected_raw_keys = {"kind", "path", "sha256", "byte_count"}
                if row.get("kind") == "PLAYWRIGHT_RAW_RESULT":
                    # Failure diagnostics may add browser_statuses, but a PASS
                    # row is the exact byte reference below.
                    if set(row) != expected_raw_keys:
                        raise RuntimeError(
                            f"V2_PLAYWRIGHT_RAW_REF_DRIFT:{profile_id}:{channel}"
                        )
                elif set(row) != expected_raw_keys:
                    raise RuntimeError(
                        f"V2_FLUTTER_RAW_REF_DRIFT:{profile_id}:{channel}"
                    )
                raw_source = Path(str(row.get("path")))
                if raw_source.is_symlink():
                    raise RuntimeError(
                        f"V2_RUNTIME_RAW_PROBE_REGULAR_FILE_REQUIRED:{profile_id}:{channel}"
                    )
                raw_path = raw_source.resolve(strict=True)
                if not raw_path.is_file():
                    raise RuntimeError(
                        f"V2_RUNTIME_RAW_PROBE_REGULAR_FILE_REQUIRED:{profile_id}:{channel}"
                    )
                content = raw_path.read_bytes()
                if (
                    row.get("sha256") != digest_bytes(content)
                    or row.get("byte_count") != len(content)
                    or not raw_path.is_file()
                ):
                    raise RuntimeError(
                        f"V2_RUNTIME_RAW_PROBE_DRIFT:{profile_id}:{channel}"
                    )
                relative = (
                    f"formal-campaign/toolchain/runtime-evidence/{profile_id}/{channel}/"
                    f"raw-probe/{row['sha256'].removeprefix('sha256:')}.json"
                )
                destination = pack_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(raw_path, destination)
                identifier = artifact_identifier(
                    f"v2-runtime-raw-probe-{profile_id}-{channel}", row["sha256"]
                )
                catalog.add(identifier, "runtime-raw-probe-v2", relative)
                raw_probe_ids.append(identifier)
                raw_probe_payloads.append((str(row["kind"]), load_json(destination)))
                packed_ids.append(identifier)

            expected_raw_kind = (
                "FLUTTER_DRIVE_RAW_RESULT"
                if record.get("runner_kind") == "FLUTTER_DRIVE_SEMANTICS"
                else "PLAYWRIGHT_RAW_RESULT"
                if record.get("runner_kind") == "PLAYWRIGHT_BROWSER_INTERACTION"
                else None
            )
            if expected_raw_kind is not None:
                if len(raw_probe_payloads) != 1 or raw_probe_payloads[0][0] != expected_raw_kind:
                    raise RuntimeError(
                        f"V2_RUNTIME_RAW_PROOF_CLOSURE_DRIFT:{profile_id}:{channel}"
                    )
                if expected_raw_kind == "FLUTTER_DRIVE_RAW_RESULT":
                    _validate_flutter_raw_proof_v2(
                        payload=raw_probe_payloads[0][1],
                        profile_execution=profile,
                        record=record,
                        channel=channel,
                        scenario_ids=scenario_ids,
                        profile_manifest_digest=profile_manifest_digests[profile_id],
                        scenario_manifest_digest=scenario_manifest_digest,
                        observations=observations_by_key,
                    )
                else:
                    _validate_playwright_raw_proof_v2(
                        payload=raw_probe_payloads[0][1],
                        profile_execution=profile,
                        record=record,
                        scenario_ids=scenario_ids,
                        scenario_inputs=scenario_inputs,
                        observations=observations_by_key,
                        block_statuses=block_statuses,
                    )
            elif raw_probe_payloads:
                raise RuntimeError(
                    f"V2_RUNTIME_UNRECOGNIZED_RUNNER_RAW_PROOF:{profile_id}:{channel}"
                )

            for execution_name in (
                "build_execution",
                "startup_execution",
                "journey_execution",
            ):
                execution = record.get(execution_name)
                if not isinstance(execution, dict) or execution.get("status") != "PASSED":
                    raise RuntimeError(
                        f"V2_RUNTIME_EXECUTION_NOT_PASSED:{profile_id}:{channel}:{execution_name}"
                    )
            normalized_channels[channel] = {
                **empty,
                "observations": observations_by_key,
                "block_statuses": block_statuses,
                "observation_artifact_ids": observation_ids,
                "runtime_source_artifact_ids": source_ids,
                "result_manifest_artifact_id": manifest_id,
                "execution_policy_artifact_id": policy_id,
                "raw_probe_artifact_ids": raw_probe_ids,
                "build_execution_id": record["build_execution"]["execution_id"],
                "startup_execution_id": record["startup_execution"]["execution_id"],
                "journey_execution_id": record["journey_execution"]["execution_id"],
                "artifact_ids": [
                    *source_ids,
                    *observation_ids,
                    manifest_id,
                    policy_id,
                    *raw_probe_ids,
                ],
            }
        profiles[profile_id] = {"raw": profile, "channels": normalized_channels}
    if tuple(sorted(profiles)) != PROFILE_IDS:
        raise RuntimeError("V2_RUNTIME_PROFILE_CLOSURE_DRIFT")
    packed_unique = sorted(set(packed_ids))
    if len(packed_unique) != len(packed_ids):
        raise RuntimeError("V2_RUNTIME_ARTIFACT_REUSE_OR_COLLISION")
    required_states = [
        channel_statuses[profile_id][channel]
        for profile_id in PROFILE_IDS
        for channel in REQUIRED_RUNTIME_CHANNELS_V2[profile_id]
    ]
    runtime_status = (
        "FAILED"
        if "FAILED" in required_states
        else "PASSED"
        if required_states and all(item == "PASSED" for item in required_states)
        else "NOT_RUN"
    )
    return {
        "profiles": profiles,
        "artifact_ids": packed_unique,
        "profile_channel_statuses": channel_statuses,
        "profile_channel_contracts": channel_contracts,
        "runtime_status": runtime_status,
    }


def add_toolchain_evidence_v2(
    *,
    repo_root: Path,
    engine_root: Path,
    pack_root: Path,
    catalog: ArtifactCatalog,
    evidence_path: Path | None,
    scenario_digest: str,
    scenario_ids: list[str],
    scenario_inputs: dict[str, dict[str, Any]],
    runtime_driver_contracts: dict[str, dict[str, Any]],
    profile_manifest_digests: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    producer = safe_source_file(
        repo_root,
        "tooling/run_frontend_formal_toolchains.py",
        "v2_toolchain_producer",
    )
    producer_fingerprint = digest_bytes(producer.read_bytes())
    engine_digest = digest_bytes(
        (engine_root / "frontend-interaction-formal-campaign.json").read_bytes()
    )
    artifact_id: str | None = None
    artifact_sha256: str | None = None
    artifact_bytes: int | None = None
    raw: dict[str, Any] | None = None
    runtime_capture: dict[str, Any] = {
        "profiles": {},
        "artifact_ids": [],
        "profile_channel_statuses": {},
        "profile_channel_contracts": {},
        "runtime_status": "NOT_RUN",
    }
    status = "NOT_RUN"
    if evidence_path is not None:
        if evidence_path.is_symlink():
            raise RuntimeError("V2_TOOLCHAIN_EVIDENCE_REGULAR_FILE_REQUIRED")
        source = evidence_path.resolve(strict=True)
        if not source.is_file():
            raise RuntimeError("V2_TOOLCHAIN_EVIDENCE_REGULAR_FILE_REQUIRED")
        raw = load_json(source)
        campaign = raw.get("campaign")
        raw_producer = raw.get("producer")
        if (
            not isinstance(campaign, dict)
            or campaign.get("sha256") != engine_digest
            or campaign.get("proof_profile") != "bounded-frontend-interaction-v1"
            or campaign.get("profile_count") != 9
            or campaign.get("route_count") != 72
            or raw.get("semantic_block_ids") != list(SEMANTIC_BLOCKS)
            or raw.get("scenario_manifest_digest") != scenario_digest
            or not isinstance(raw_producer, dict)
            or raw_producer.get("sha256") != producer_fingerprint
            or raw_producer.get("byte_count") != len(producer.read_bytes())
        ):
            raise RuntimeError("V2_TOOLCHAIN_IDENTITY_OR_CAMPAIGN_DRIFT")
        executions = raw.get("profile_executions")
        records = raw.get("route_records")
        if not isinstance(executions, list) or len(executions) != 9:
            raise RuntimeError("V2_TOOLCHAIN_PROFILE_CLOSURE_DRIFT")
        if not isinstance(records, list) or len(records) != 72:
            raise RuntimeError("V2_TOOLCHAIN_ROUTE_CLOSURE_DRIFT")
        states = {row.get("status") for row in executions if isinstance(row, dict)}
        status = (
            "FAILED"
            if "FAILED" in states
            else "PASSED"
            if states == {"PASSED"}
            else "NOT_RUN"
            if states == {"NOT_RUN"}
            else "PARTIAL"
        )
        if raw.get("scenario_policy", {}).get("scenario_ids") != scenario_ids:
            raise RuntimeError("V2_TOOLCHAIN_SCENARIO_ID_CLOSURE_DRIFT")
        runtime_capture = pack_runtime_evidence_v2(
            pack_root=pack_root,
            catalog=catalog,
            raw=raw,
            scenario_ids=scenario_ids,
            scenario_inputs=scenario_inputs,
            runtime_driver_contracts=runtime_driver_contracts,
            profile_manifest_digests=profile_manifest_digests,
            scenario_manifest_digest=scenario_digest,
        )
        relative = (
            "formal-campaign/toolchain/frontend-formal-toolchain-evidence-v2.json"
        )
        destination = pack_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        artifact_id = artifact_identifier("v2-toolchain", source.name)
        catalog.add(artifact_id, "toolchain-evidence-v2", relative)
        reference = catalog.ref(artifact_id)
        artifact_sha256 = reference["sha256"]
        artifact_bytes = reference["bytes"]
    return (
        {
            "provided": evidence_path is not None,
            "status": status,
            "artifact_id": artifact_id,
            "artifact_sha256": artifact_sha256,
            "artifact_bytes": artifact_bytes,
            "engine_campaign_sha256": engine_digest,
            "producer_fingerprint": producer_fingerprint,
            "scenario_manifest_sha256": scenario_digest,
            "profile_binding_count": 9,
            "route_binding_count": 72,
            "block_binding_count": 864,
            "runtime_status": runtime_capture["runtime_status"],
            "runtime_artifact_ids": runtime_capture["artifact_ids"],
            "runtime_artifact_count": len(runtime_capture["artifact_ids"]),
            "profile_channel_statuses": runtime_capture[
                "profile_channel_statuses"
            ],
            "boundaries": {
                "build_is_behavior": False,
                "model_is_runtime": False,
                "same_producer_is_independent": False,
                "certification": "NOT_CERTIFIED",
            },
        },
        raw,
        runtime_capture,
    )


def validate_bounded_stream(value: object, label: str) -> None:
    if not isinstance(value, dict):
        raise RuntimeError(f"TOOLCHAIN_STREAM_INVALID:{label}")
    text = value.get("text")
    byte_count = value.get("byte_count")
    if not isinstance(text, str) or not isinstance(byte_count, int) or byte_count < 0:
        raise RuntimeError(f"TOOLCHAIN_STREAM_INVALID:{label}")
    encoded = text.encode("utf-8")
    if value.get("truncated") is False:
        if byte_count != len(encoded) or value.get("sha256") != digest_bytes(encoded):
            raise RuntimeError(f"TOOLCHAIN_STREAM_DIGEST_DRIFT:{label}")
    elif value.get("truncated") is not True or byte_count < len(encoded):
        raise RuntimeError(f"TOOLCHAIN_STREAM_TRUNCATION_DRIFT:{label}")


def validate_toolchain_command(value: object, label: str) -> None:
    if not isinstance(value, dict):
        raise RuntimeError(f"TOOLCHAIN_COMMAND_INVALID:{label}")
    status = value.get("status")
    exit_code = value.get("exit_code")
    if status not in {"PASSED", "FAILED", "NOT_RUN", "TIMEOUT", "TOOL_UNAVAILABLE"}:
        raise RuntimeError(f"TOOLCHAIN_COMMAND_STATUS_INVALID:{label}")
    if status == "PASSED" and exit_code != 0:
        raise RuntimeError(f"TOOLCHAIN_COMMAND_EXIT_DRIFT:{label}")
    if status == "FAILED" and (not isinstance(exit_code, int) or exit_code == 0):
        raise RuntimeError(f"TOOLCHAIN_COMMAND_EXIT_DRIFT:{label}")
    argv = value.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(item, str) and item for item in argv)
    ):
        raise RuntimeError(f"TOOLCHAIN_COMMAND_ARGV_INVALID:{label}")
    validate_bounded_stream(value.get("stdout"), f"{label}:stdout")
    validate_bounded_stream(value.get("stderr"), f"{label}:stderr")


def add_toolchain_evidence(
    *,
    repo_root: Path,
    engine_root: Path,
    pack_root: Path,
    catalog: ArtifactCatalog,
    profile_entries: dict[str, dict[str, Any]],
    route_entries: dict[str, dict[str, Any]],
    evidence_path: Path | None,
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    """Capture and strictly bind optional real build/browser evidence.

    Build success is retained as a separate fact.  A route receives native
    browser behavior only when both exact profile executions have complete,
    passing browser probe sets; no build-only or model-only result is promoted.
    """

    producer_path = safe_source_file(
        repo_root,
        "tooling/run_frontend_formal_toolchains.py",
        "toolchain_evidence_producer",
    )
    producer_fingerprint = digest_bytes(producer_path.read_bytes())
    raw_campaign_sha = digest_bytes(
        (engine_root / "frontend-formal-route-campaign.json").read_bytes()
    )
    if evidence_path is None:
        profile_bindings = [
            {
                "profile_id": profile_id,
                "project_digest": profile_entries[profile_id]["project_digest"],
                "execution_id": None,
                "toolchain_status": "NOT_RUN",
                "target_build_status": "NOT_RUN",
                "browser_status": "NOT_RUN",
                "browser_probe_count": 0,
                "browser_pass_count": 0,
            }
            for profile_id in PROFILE_IDS
        ]
        route_bindings = [
            {
                "route_id": route_id,
                "source_execution_id": None,
                "target_execution_id": None,
                "source_build_status": "NOT_RUN",
                "target_build_status": "NOT_RUN",
                "source_browser_status": "NOT_RUN",
                "target_browser_status": "NOT_RUN",
                "native_behavior_status": "NOT_RUN",
            }
            for route_id in sorted(route_entries)
        ]
        return (
            {
                "provided": False,
                "status": "NOT_RUN",
                "artifact_id": None,
                "artifact_sha256": None,
                "engine_campaign_sha256": None,
                "producer_fingerprint": producer_fingerprint,
                "profile_bindings": profile_bindings,
                "route_bindings": route_bindings,
                "boundaries": {
                    "build_is_behavior": False,
                    "model_is_native": False,
                    "device_or_simulator_status": "NOT_RUN",
                    "independent_verification": "NOT_RUN",
                    "certification": "NOT_CERTIFIED",
                },
            },
            {},
            {item["route_id"]: item for item in route_bindings},
        )

    if evidence_path.is_symlink():
        raise RuntimeError("TOOLCHAIN_EVIDENCE_REGULAR_FILE_REQUIRED")
    source = evidence_path.resolve(strict=True)
    if not source.is_file():
        raise RuntimeError("TOOLCHAIN_EVIDENCE_REGULAR_FILE_REQUIRED")
    raw = load_json(source)
    if (
        raw.get("schema_version") != "1.0"
        or raw.get("kind") != "frontend-formal-toolchain-evidence"
    ):
        raise RuntimeError("TOOLCHAIN_EVIDENCE_IDENTITY_DRIFT")
    producer = raw.get("producer")
    expected_producer = {
        "path": str(producer_path),
        "sha256": producer_fingerprint,
        "byte_count": len(producer_path.read_bytes()),
    }
    if (
        producer != expected_producer
        or raw.get("replay", {}).get("producer") != expected_producer
    ):
        raise RuntimeError("TOOLCHAIN_EVIDENCE_STALE_PRODUCER")
    campaign_binding = raw.get("campaign")
    if not isinstance(campaign_binding, dict) or (
        campaign_binding.get("sha256") != raw_campaign_sha
        or campaign_binding.get("proof_profile") != "bounded-navigation-v1"
        or campaign_binding.get("profile_count") != 9
        or campaign_binding.get("route_count") != 72
    ):
        raise RuntimeError("TOOLCHAIN_EVIDENCE_CAMPAIGN_DRIFT")
    summary = raw.get("summary")
    if not isinstance(summary, dict) or (
        summary.get("device_or_simulator_journeys_passed") != 0
        or summary.get("independent_verification") != "NOT_RUN"
        or summary.get("certification") != "NOT_CERTIFIED"
    ):
        raise RuntimeError("TOOLCHAIN_EVIDENCE_BOUNDARY_DRIFT")

    profile_executions: dict[str, dict[str, Any]] = {}
    for execution in raw.get("profile_executions", []):
        if not isinstance(execution, dict):
            raise RuntimeError("TOOLCHAIN_PROFILE_EXECUTION_INVALID")
        profile_id = execution.get("profile_id")
        if profile_id in profile_executions or profile_id not in profile_entries:
            raise RuntimeError(f"TOOLCHAIN_PROFILE_CLOSURE_DRIFT:{profile_id}")
        if execution.get("project_digest") != profile_entries[str(profile_id)].get(
            "project_digest"
        ):
            raise RuntimeError(f"TOOLCHAIN_PROFILE_PROJECT_DRIFT:{profile_id}")
        if execution.get("reason") == "PROFILE_NOT_SELECTED":
            identity_core = {
                "producer_digest": producer_fingerprint,
                "profile_id": profile_id,
                "project_digest": execution.get("project_digest"),
                "status": "NOT_RUN",
            }
        else:
            identity_core = {
                key: value
                for key, value in execution.items()
                if key not in {"execution_id", "replay_profile_args"}
            }
        if execution.get("execution_id") != canonical_digest(identity_core):
            raise RuntimeError(f"TOOLCHAIN_EXECUTION_ID_DRIFT:{profile_id}")
        if execution.get("producer") != expected_producer:
            raise RuntimeError(f"TOOLCHAIN_EXECUTION_STALE_PRODUCER:{profile_id}")
        status = execution.get("status")
        build_status = execution.get("target_build")
        if status not in {"PASSED", "FAILED", "NOT_RUN"} or build_status not in {
            "PASSED",
            "FAILED",
            "NOT_RUN",
        }:
            raise RuntimeError(f"TOOLCHAIN_PROFILE_STATUS_INVALID:{profile_id}")
        for index, command in enumerate(execution.get("tool_versions", [])):
            validate_toolchain_command(command, f"{profile_id}:version:{index}")
        for index, command in enumerate(execution.get("commands", [])):
            validate_toolchain_command(command, f"{profile_id}:command:{index}")
        browser = execution.get("browser_journey")
        if not isinstance(browser, dict) or browser.get("status") not in {
            "PASSED",
            "FAILED",
            "NOT_RUN",
        }:
            raise RuntimeError(f"TOOLCHAIN_BROWSER_RECORD_INVALID:{profile_id}")
        probes = browser.get("probes")
        if not isinstance(probes, list):
            raise RuntimeError(f"TOOLCHAIN_BROWSER_PROBES_INVALID:{profile_id}")
        for index, probe in enumerate(probes):
            if not isinstance(probe, dict):
                raise RuntimeError(
                    f"TOOLCHAIN_BROWSER_PROBE_INVALID:{profile_id}:{index}"
                )
            validate_toolchain_command(
                probe.get("command"), f"{profile_id}:browser:{index}"
            )
            command = probe["command"]
            observation = probe.get("observation")
            if probe.get("dom_sha256") != command.get("stdout", {}).get("sha256"):
                raise RuntimeError(
                    f"TOOLCHAIN_BROWSER_DOM_DIGEST_DRIFT:{profile_id}:{index}"
                )
            if probe.get("status") == "PASSED" and (
                command.get("status") != "PASSED"
                or not isinstance(observation, dict)
                or observation.get("matches_model") is not True
            ):
                raise RuntimeError(
                    f"TOOLCHAIN_BROWSER_PASS_INVALID:{profile_id}:{index}"
                )
        passed_probes = sum(probe.get("status") == "PASSED" for probe in probes)
        if browser.get("status") == "PASSED" and (
            build_status != "PASSED" or not probes or passed_probes != len(probes)
        ):
            raise RuntimeError(f"TOOLCHAIN_BROWSER_PASS_INCOMPLETE:{profile_id}")
        if profile_id == "harmony-arkui" and (
            browser.get("status") != "NOT_RUN" or probes
        ):
            raise RuntimeError("TOOLCHAIN_HARMONY_RUNTIME_MUST_REMAIN_NOT_RUN")
        profile_executions[str(profile_id)] = execution
    if set(profile_executions) != set(PROFILE_IDS):
        raise RuntimeError("TOOLCHAIN_PROFILE_CLOSURE_DRIFT")

    route_records: dict[str, dict[str, Any]] = {}
    for record in raw.get("route_records", []):
        if not isinstance(record, dict):
            raise RuntimeError("TOOLCHAIN_ROUTE_RECORD_INVALID")
        route_id = record.get("route_id")
        if route_id in route_records or route_id not in route_entries:
            raise RuntimeError(f"TOOLCHAIN_ROUTE_CLOSURE_DRIFT:{route_id}")
        route = route_entries[str(route_id)]
        source_execution = profile_executions[str(route["source_profile"])]
        target_execution = profile_executions[str(route["target_profile"])]
        for key, expected in (
            ("source_profile", route["source_profile"]),
            ("target_profile", route["target_profile"]),
            ("source_project_digest", route["source_project_digest"]),
            ("target_project_digest", route["target_project_digest"]),
            ("source_execution_id", source_execution["execution_id"]),
            ("target_execution_id", target_execution["execution_id"]),
            ("source_toolchain_status", source_execution["status"]),
            ("target_toolchain_status", target_execution["status"]),
            ("source_browser_status", source_execution["browser_journey"]["status"]),
            ("target_browser_status", target_execution["browser_journey"]["status"]),
        ):
            if record.get(key) != expected:
                raise RuntimeError(f"TOOLCHAIN_ROUTE_LINKAGE_DRIFT:{route_id}:{key}")
        native = (
            source_execution["target_build"] == "PASSED"
            and target_execution["target_build"] == "PASSED"
            and source_execution["browser_journey"]["status"] == "PASSED"
            and target_execution["browser_journey"]["status"] == "PASSED"
            and "harmony-arkui"
            not in {route["source_profile"], route["target_profile"]}
        )
        if record.get("browser_evidence") != ("PASSED" if native else "NOT_RUN"):
            raise RuntimeError(f"TOOLCHAIN_ROUTE_BROWSER_DRIFT:{route_id}")
        if (
            record.get("device_or_simulator_evidence") != "NOT_RUN"
            or record.get("holdout_evidence") != "NOT_RUN"
            or record.get("representative_customer_evidence") != "NOT_RUN"
            or record.get("certification") != "NOT_CERTIFIED"
        ):
            raise RuntimeError(f"TOOLCHAIN_ROUTE_BOUNDARY_DRIFT:{route_id}")
        route_records[str(route_id)] = record
    if set(route_records) != set(route_entries):
        raise RuntimeError("TOOLCHAIN_ROUTE_CLOSURE_DRIFT")
    if (
        raw.get("implementation_closure") is not None
        or raw.get("engine_preverification") is not None
        or raw.get("semantic_block_ids") != []
        or raw.get("scenario_manifest_digest") is not None
        or raw.get("scenario_policy") is not None
        or raw.get("mutation_replay") != []
    ):
        raise RuntimeError("TOOLCHAIN_EVIDENCE_IDENTITY_DRIFT")
    identity_core = {
        "producer": raw["producer"],
        "implementation_closure": None,
        "engine_preverification_digest": None,
        "campaign_sha256": raw_campaign_sha,
        "proof_profile": "bounded-navigation-v1",
        "semantic_block_ids": [],
        "scenario_manifest_digest": None,
        "scenario_policy": None,
        "mutation_replay_digest": canonical_digest([]),
        "policy": raw.get("policy"),
        "profile_execution_ids": [
            execution["execution_id"] for execution in profile_executions.values()
        ],
        "route_execution_bindings": [
            {
                "route_id": record["route_id"],
                "source_execution_id": record["source_execution_id"],
                "target_execution_id": record["target_execution_id"],
                "status": record["status"],
            }
            for record in route_records.values()
        ],
    }
    if raw.get("evidence_identity") != {
        "algorithm": "sha256(canonical-json(identity_payload))",
        "identity_payload": identity_core,
        "sha256": canonical_digest(identity_core),
        "scope": (
            "producer+engine-preverification+implementation+campaign+scenario+"
            "policy+profile-executions+route-bindings"
        ),
    }:
        raise RuntimeError("TOOLCHAIN_EVIDENCE_IDENTITY_DRIFT")

    relative = "formal-campaign/toolchain/frontend-formal-toolchain-evidence.json"
    destination = pack_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    artifact_id = artifact_identifier(
        "toolchain-evidence", "frontend-formal-toolchain-evidence.json"
    )
    catalog.add(artifact_id, "toolchain-evidence", relative)
    profile_bindings = [
        {
            "profile_id": profile_id,
            "project_digest": execution["project_digest"],
            "execution_id": execution["execution_id"],
            "toolchain_status": execution["status"],
            "target_build_status": execution["target_build"],
            "browser_status": execution["browser_journey"]["status"],
            "browser_probe_count": len(execution["browser_journey"]["probes"]),
            "browser_pass_count": sum(
                probe.get("status") == "PASSED"
                for probe in execution["browser_journey"]["probes"]
            ),
        }
        for profile_id, execution in sorted(profile_executions.items())
    ]
    route_bindings = []
    for route_id, record in sorted(route_records.items()):
        source = profile_executions[record["source_profile"]]
        target = profile_executions[record["target_profile"]]
        native = record["browser_evidence"] == "PASSED"
        route_bindings.append(
            {
                "route_id": route_id,
                "source_execution_id": source["execution_id"],
                "target_execution_id": target["execution_id"],
                "source_build_status": source["target_build"],
                "target_build_status": target["target_build"],
                "source_browser_status": source["browser_journey"]["status"],
                "target_browser_status": target["browser_journey"]["status"],
                "native_behavior_status": "PASSED" if native else "NOT_RUN",
            }
        )
    profile_states = {item["toolchain_status"] for item in profile_bindings}
    status = (
        "FAILED"
        if "FAILED" in profile_states
        else "PASSED"
        if profile_states == {"PASSED"}
        else "NOT_RUN"
        if profile_states == {"NOT_RUN"}
        else "PARTIAL"
    )
    reference = catalog.ref(artifact_id)
    return (
        {
            "provided": True,
            "status": status,
            "artifact_id": artifact_id,
            "artifact_sha256": reference["sha256"],
            "engine_campaign_sha256": raw_campaign_sha,
            "producer_fingerprint": producer_fingerprint,
            "profile_bindings": profile_bindings,
            "route_bindings": route_bindings,
            "boundaries": {
                "build_is_behavior": False,
                "model_is_native": False,
                "device_or_simulator_status": "NOT_RUN",
                "independent_verification": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            },
        },
        profile_executions,
        {item["route_id"]: item for item in route_bindings},
    )


def span_ref(artifact_id: str, document: object, pointer: str) -> dict[str, Any]:
    value = resolve_pointer(document, pointer)
    start, end = canonical_pointer_span(document, pointer_tokens(pointer))
    return {
        "artifact_id": artifact_id,
        "pointer": pointer,
        "span": {"start": start, "end": end},
        "sha256": canonical_digest(value),
    }


def code_span_ref(
    artifact_id: str,
    content: bytes,
    start: int,
    end: int,
    parser_node_kind: str,
) -> dict[str, Any]:
    if start < 0 or end <= start or end > len(content):
        raise RuntimeError(f"CODE_SPAN_OUT_OF_BOUNDS:{artifact_id}:{start}:{end}")
    return {
        "artifact_id": artifact_id,
        "start": start,
        "end": end,
        "sha256": digest_bytes(content[start:end]),
        "parser_node_kind": parser_node_kind,
    }


def observation_value(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "trace_id"}


def normalized_behavior(
    route_id: str,
    raw: dict[str, Any],
    canonical_oracle_id: str,
    independent_oracle_id: str,
    *,
    source_execution: dict[str, Any] | None,
    target_execution: dict[str, Any] | None,
    toolchain_artifact_id: str | None,
) -> dict[str, Any]:
    groups = [
        raw.get(name, {}).get("observations")
        for name in ("canonical", "independent", "source", "target")
    ]
    if any(not isinstance(group, list) for group in groups):
        raise RuntimeError(f"ENGINE_BEHAVIOR_GROUP_MISSING:{route_id}")
    canonical, independent, source, target = groups
    if not (len(canonical) == len(independent) == len(source) == len(target) == 5):
        raise RuntimeError(f"ENGINE_BEHAVIOR_CASE_CLOSURE_DRIFT:{route_id}")
    native = bool(
        toolchain_artifact_id
        and source_execution
        and target_execution
        and source_execution.get("target_build") == "PASSED"
        and target_execution.get("target_build") == "PASSED"
        and source_execution.get("browser_journey", {}).get("status") == "PASSED"
        and target_execution.get("browser_journey", {}).get("status") == "PASSED"
    )
    source_probes = (
        source_execution.get("browser_journey", {}).get("probes", [])
        if source_execution
        else []
    )
    target_probes = (
        target_execution.get("browser_journey", {}).get("probes", [])
        if target_execution
        else []
    )
    if native and (len(source_probes) != 5 or len(target_probes) != 5):
        raise RuntimeError(f"TOOLCHAIN_NATIVE_PROBE_CLOSURE_DRIFT:{route_id}")

    def trace(
        *,
        model_events: dict[str, Any],
        execution: dict[str, Any] | None,
        probes: list[dict[str, Any]],
        index: int,
    ) -> dict[str, Any]:
        if not native:
            return {
                "runtime_kind": "model",
                "native_execution": False,
                "events": model_events,
            }
        assert execution is not None
        probe = probes[index]
        normalized = probe.get("normalized_observation")
        expected_route = probe.get("expected_route")
        actual_event = (
            {
                "operation": normalized.get("operation"),
                "input_path": normalized.get("input_path"),
                "resolution": normalized.get("resolution"),
                "route": normalized.get("route"),
                "render": normalized.get("render"),
            }
            if isinstance(normalized, dict)
            else None
        )
        if (
            probe.get("status") != "PASSED"
            or probe.get("operation") != model_events.get("operation")
            or probe.get("input_path") != model_events.get("input_path")
            or probe.get("resolution") != model_events.get("resolution")
            or expected_route != model_events.get("route")
            or not isinstance(normalized, dict)
            or actual_event != model_events
        ):
            raise RuntimeError(f"TOOLCHAIN_NATIVE_OBSERVATION_DRIFT:{route_id}:{index}")
        return {
            "runtime_kind": "browser",
            "native_execution": True,
            "events": actual_event,
            "evidence": {
                "toolchain_evidence_artifact_id": toolchain_artifact_id,
                "execution_id": execution["execution_id"],
                "probe_name": probe.get("name"),
                "dom_sha256": probe.get("dom_sha256"),
                "normalized_observation_sha256": canonical_digest(normalized),
            },
        }

    cases: list[dict[str, Any]] = []
    for index, (
        canonical_item,
        independent_item,
        source_item,
        target_item,
    ) in enumerate(zip(canonical, independent, source, target, strict=True)):
        values = [
            observation_value(item)
            for item in (canonical_item, independent_item, source_item, target_item)
        ]
        status = "PASSED" if all(item == values[0] for item in values[1:]) else "FAILED"
        cases.append(
            {
                "case_id": f"bounded-navigation-case-{index}",
                "input": {
                    "operation": values[0].get("operation"),
                    "path": values[0].get("input_path"),
                },
                "canonical_expected": {
                    "oracle_kind": "canonical-spec",
                    "provenance_artifact_id": canonical_oracle_id,
                    "events": values[0],
                },
                "independent_expected": {
                    "oracle_kind": "independent-spec",
                    "provenance_artifact_id": independent_oracle_id,
                    "events": values[1],
                },
                "source_trace": trace(
                    model_events=values[0] if native else values[2],
                    execution=source_execution,
                    probes=source_probes,
                    index=index,
                ),
                "target_trace": trace(
                    model_events=values[0] if native else values[3],
                    execution=target_execution,
                    probes=target_probes,
                    index=index,
                ),
                "status": status,
            }
        )
    if raw.get("equivalent") is not True or any(
        case["status"] != "PASSED" for case in cases
    ):
        raise RuntimeError(f"ENGINE_BEHAVIOR_EQUIVALENCE_DRIFT:{route_id}")
    return {
        "schema_version": 1,
        "route_id": route_id,
        "runtime_kind": "browser" if native else "model",
        "cases": cases,
    }


def normalize_route(
    *,
    engine_root: Path,
    pack_root: Path,
    catalog: ArtifactCatalog,
    raw_ids: dict[str, str],
    route_id: str,
    route_entry: dict[str, Any],
    profile_entries: dict[str, dict[str, Any]],
    profile_records: dict[str, dict[str, Any]],
    implementation: dict[str, Any],
    replay: dict[str, Any],
    corpora: dict[str, Any],
    campaign_assumptions: list[str],
    toolchain_evidence: dict[str, Any],
    toolchain_profiles: dict[str, dict[str, Any]],
    toolchain_route: dict[str, Any],
    solver_binary: dict[str, Any],
) -> dict[str, Any]:
    source_id = str(route_entry["source_profile"])
    target_id = str(route_entry["target_profile"])
    raw_route_root = engine_root / "routes" / route_id
    raw_formal = load_json(raw_route_root / "formal-input.json")
    raw_solver = load_json(raw_route_root / "solver-result.json")
    raw_source_model = load_json(raw_route_root / "source-model.json")
    raw_target_model = load_json(raw_route_root / "target-model.json")
    raw_behavior = load_json(raw_route_root / "behavior.json")
    raw_chunks = load_json(raw_route_root / "chunks.json")
    raw_composition = load_json(raw_route_root / "composition.json")
    raw_layered = load_json(raw_route_root / "layered-result.json")
    canonical_model = raw_formal.get("canonical_model")
    source_model = raw_source_model.get("model")
    target_model = raw_target_model.get("model")
    if (
        not isinstance(canonical_model, dict)
        or canonical_model != source_model
        or canonical_model != target_model
    ):
        raise RuntimeError(f"ENGINE_SEMANTIC_MODEL_DRIFT:{route_id}")
    source_profile = profile_entries[source_id]
    target_profile = profile_entries[target_id]
    source_path = safe_source_file(
        engine_root / str(source_profile["project_path"]),
        source_profile["navigation_source_path"],
        f"source_code:{route_id}",
    )
    target_path = safe_source_file(
        engine_root / str(target_profile["project_path"]),
        target_profile["navigation_source_path"],
        f"target_code:{route_id}",
    )
    route_prefix = f"formal-campaign/routes/{route_id}"
    source_code_relative = f"{route_prefix}/source-code.bin"
    target_code_relative = f"{route_prefix}/target-code.bin"
    (pack_root / source_code_relative).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, pack_root / source_code_relative)
    shutil.copy2(target_path, pack_root / target_code_relative)
    source_code_id = artifact_identifier("source-code", route_id)
    target_code_id = artifact_identifier("target-code", route_id)
    catalog.add(source_code_id, "source-code", source_code_relative)
    catalog.add(target_code_id, "target-code", target_code_relative)
    source_code = source_path.read_bytes()
    target_code = target_path.read_bytes()

    raw_source_spans = raw_source_model.get("spans", {})
    raw_target_spans = raw_target_model.get("spans", {})
    if not isinstance(raw_source_spans, dict) or not isinstance(raw_target_spans, dict):
        raise RuntimeError(f"ENGINE_SPAN_MAP_MISSING:{route_id}")
    source_root_span = raw_source_spans.get("")
    target_root_span = raw_target_spans.get("")
    if not isinstance(source_root_span, dict) or not isinstance(target_root_span, dict):
        raise RuntimeError(f"ENGINE_ROOT_SPAN_MISSING:{route_id}")

    block_values: dict[str, Any] = {}
    block_statuses: dict[str, str] = {}
    source_block_code_refs: dict[str, dict[str, Any]] = {}
    target_block_code_refs: dict[str, dict[str, Any]] = {}
    for block in SEMANTIC_BLOCKS:
        if block == SEMANTIC_BLOCKS[0]:
            block_values[block] = canonical_model
            block_statuses[block] = "PASSED"
            source_start, source_end = (
                source_root_span["start_byte"],
                source_root_span["end_byte"],
            )
            target_start, target_end = (
                target_root_span["start_byte"],
                target_root_span["end_byte"],
            )
        else:
            block_values[block] = {"semantic_block": block, "status": "NOT_RUN"}
            block_statuses[block] = "NOT_RUN"
            source_start, source_end = 0, len(source_code)
            target_start, target_end = 0, len(target_code)
        source_block_code_refs[block] = code_span_ref(
            source_code_id,
            source_code,
            source_start,
            source_end,
            str(raw_source_model.get("parser")),
        )
        target_block_code_refs[block] = code_span_ref(
            target_code_id,
            target_code,
            target_start,
            target_end,
            str(raw_target_model.get("parser")),
        )

    chunk_values: dict[str, Any] = {}
    chunk_records: list[dict[str, Any]] = []
    source_chunk_code_refs: dict[str, dict[str, Any]] = {}
    target_chunk_code_refs: dict[str, dict[str, Any]] = {}
    chunks = raw_chunks.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise RuntimeError(f"ENGINE_CHUNKS_MISSING:{route_id}")
    for index, raw_chunk in enumerate(chunks):
        if not isinstance(raw_chunk, dict):
            raise RuntimeError(f"ENGINE_CHUNK_INVALID:{route_id}:{index}")
        pointer = str(raw_chunk.get("pointer"))
        canonical_value = resolve_pointer(canonical_model, pointer)
        source_value = resolve_pointer(source_model, pointer)
        target_value = resolve_pointer(target_model, pointer)
        identifier = f"navigation-{index:03d}"
        chunk_values[identifier] = canonical_value
        source_span = raw_chunk.get("source", {})
        target_span = raw_chunk.get("target", {})
        source_ref = code_span_ref(
            source_code_id,
            source_code,
            int(source_span.get("start_byte")),
            int(source_span.get("end_byte")),
            f"{raw_source_model.get('parser')}:{pointer}",
        )
        target_ref = code_span_ref(
            target_code_id,
            target_code,
            int(target_span.get("start_byte")),
            int(target_span.get("end_byte")),
            f"{raw_target_model.get('parser')}:{pointer}",
        )
        if source_ref["sha256"] != source_span.get("content_hash"):
            raise RuntimeError(
                f"ENGINE_SOURCE_CODE_SPAN_HASH_DRIFT:{route_id}:{pointer}"
            )
        if target_ref["sha256"] != target_span.get("content_hash"):
            raise RuntimeError(
                f"ENGINE_TARGET_CODE_SPAN_HASH_DRIFT:{route_id}:{pointer}"
            )
        semantic_hash = canonical_digest(canonical_value)
        status = (
            "PASSED"
            if raw_chunk.get("equivalent") is True
            and canonical_value == source_value == target_value
            and raw_chunk.get("canonical_subtree_hash") == semantic_hash
            and raw_chunk.get("source_subtree_hash") == semantic_hash
            and raw_chunk.get("target_subtree_hash") == semantic_hash
            else "FAILED"
        )
        source_chunk_code_refs[identifier] = source_ref
        target_chunk_code_refs[identifier] = target_ref
        chunk_records.append(
            {
                "chunk_id": identifier,
                "semantic_block": SEMANTIC_BLOCKS[0],
                "semantic_hash": semantic_hash,
                "status": status,
            }
        )
    for block in SEMANTIC_BLOCKS[1:]:
        identifier = f"not-run-{block}"
        chunk_values[identifier] = block_values[block]
        source_chunk_code_refs[identifier] = source_block_code_refs[block]
        target_chunk_code_refs[identifier] = target_block_code_refs[block]
        chunk_records.append(
            {
                "chunk_id": identifier,
                "semantic_block": block,
                "semantic_hash": canonical_digest(block_values[block]),
                "status": "NOT_RUN",
            }
        )

    source_document = {
        "blocks": block_values,
        "chunks": chunk_values,
        "code_spans": {
            key: value["sha256"] for key, value in source_block_code_refs.items()
        },
        "chunk_spans": {
            key: value["sha256"] for key, value in source_chunk_code_refs.items()
        },
    }
    target_document = {
        "blocks": block_values,
        "chunks": chunk_values,
        "code_spans": {
            key: value["sha256"] for key, value in target_block_code_refs.items()
        },
        "chunk_spans": {
            key: value["sha256"] for key, value in target_chunk_code_refs.items()
        },
    }
    canonical_document = {"blocks": block_values, "chunks": chunk_values}
    canonical_relative = f"{route_prefix}/canonical-ir.json"
    source_model_relative = f"{route_prefix}/source-relift-ir.json"
    target_model_relative = f"{route_prefix}/target-relift-ir.json"
    write_json(pack_root / canonical_relative, canonical_document, canonical=True)
    write_json(pack_root / source_model_relative, source_document, canonical=True)
    write_json(pack_root / target_model_relative, target_document, canonical=True)
    canonical_id = artifact_identifier("canonical-ir", route_id)
    source_model_id = artifact_identifier("source-relift-ir", route_id)
    target_model_id = artifact_identifier("target-relift-ir", route_id)
    catalog.add(canonical_id, "canonical-ir", canonical_relative)
    catalog.add(source_model_id, "source-relift-ir", source_model_relative)
    catalog.add(target_model_id, "target-relift-ir", target_model_relative)

    semantic_blocks: list[dict[str, Any]] = []
    for block in SEMANTIC_BLOCKS:
        pointer = f"/blocks/{pointer_escape(block)}"
        semantic_blocks.append(
            {
                "block_id": block,
                "canonical_ir": span_ref(canonical_id, canonical_document, pointer),
                "source_relift_ir": span_ref(source_model_id, source_document, pointer),
                "target_relift_ir": span_ref(target_model_id, target_document, pointer),
                "source_code": source_block_code_refs[block],
                "target_code": target_block_code_refs[block],
                "semantic_hash": canonical_digest(block_values[block]),
                "status": block_statuses[block],
            }
        )

    mappings: list[dict[str, Any]] = []
    for record in chunk_records:
        identifier = record["chunk_id"]
        pointer = f"/chunks/{pointer_escape(identifier)}"
        mappings.append(
            {
                **record,
                "canonical": span_ref(canonical_id, canonical_document, pointer),
                "source": span_ref(source_model_id, source_document, pointer),
                "target": span_ref(target_model_id, target_document, pointer),
                "source_code": source_chunk_code_refs[identifier],
                "target_code": target_chunk_code_refs[identifier],
            }
        )
    chunk_statuses = {item["status"] for item in mappings}
    chunk_status = (
        "FAILED"
        if "FAILED" in chunk_statuses
        else "NOT_RUN"
        if "NOT_RUN" in chunk_statuses
        else "PASSED"
    )
    chunk_value = {
        "schema_version": 1,
        "route_id": route_id,
        "path_scheme": "rfc6901-json-pointer-v1",
        "mappings": mappings,
        "status": chunk_status,
    }
    chunk_relative = f"{route_prefix}/chunk-map.json"
    write_json(pack_root / chunk_relative, chunk_value, canonical=True)
    chunk_id = artifact_identifier("chunk-map", route_id)
    catalog.add(chunk_id, "chunk-map", chunk_relative)

    raw_formal_id = raw_ids[f"routes/{route_id}/formal-input.json"]
    raw_behavior_id = raw_ids[f"routes/{route_id}/behavior.json"]
    canonical_oracle_value = {
        "schema_version": 1,
        "oracle_kind": "canonical-spec",
        "oracle_id": f"canonical:{route_id}",
        "derivation_fingerprint": canonical_digest(
            {"route_id": route_id, "derivation": "canonical-model"}
        ),
        "source_artifact_ids": [raw_formal_id],
    }
    independent_oracle_value = {
        "schema_version": 1,
        "oracle_kind": "independent-spec",
        "oracle_id": f"bounded-reference:{route_id}",
        "derivation_fingerprint": canonical_digest(
            {"route_id": route_id, "derivation": "separate-reference-interpreter"}
        ),
        "source_artifact_ids": [raw_behavior_id],
        "external_independence": "NOT_RUN",
    }
    canonical_oracle_relative = f"{route_prefix}/canonical-oracle.json"
    independent_oracle_relative = f"{route_prefix}/independent-oracle.json"
    write_json(
        pack_root / canonical_oracle_relative, canonical_oracle_value, canonical=True
    )
    write_json(
        pack_root / independent_oracle_relative,
        independent_oracle_value,
        canonical=True,
    )
    canonical_oracle_id = artifact_identifier("canonical-oracle", route_id)
    independent_oracle_id = artifact_identifier("independent-oracle", route_id)
    catalog.add(canonical_oracle_id, "canonical-oracle", canonical_oracle_relative)
    catalog.add(
        independent_oracle_id, "independent-oracle", independent_oracle_relative
    )
    behavior_value = normalized_behavior(
        route_id,
        raw_behavior,
        canonical_oracle_id,
        independent_oracle_id,
        source_execution=toolchain_profiles.get(source_id),
        target_execution=toolchain_profiles.get(target_id),
        toolchain_artifact_id=toolchain_evidence.get("artifact_id"),
    )
    behavior_relative = f"{route_prefix}/behavior-traces.json"
    write_json(pack_root / behavior_relative, behavior_value, canonical=True)
    behavior_id = artifact_identifier("behavior", route_id)
    catalog.add(behavior_id, "behavior-traces", behavior_relative)

    unsupported = list(SEMANTIC_BLOCKS[1:])
    composition_id = f"composition:{route_id}"
    formal_input_value = {
        "schema_version": 1,
        "kind": "frontend-formal-input-v1",
        "route_id": route_id,
        "source_profile_digest": profile_records[source_id]["profile_digest"],
        "target_profile_digest": profile_records[target_id]["profile_digest"],
        "source_project_digest": route_entry["source_project_digest"],
        "target_project_digest": route_entry["target_project_digest"],
        "source_model_sha256": catalog.ref(source_model_id)["sha256"],
        "target_model_sha256": catalog.ref(target_model_id)["sha256"],
        "chunk_sha256": catalog.ref(chunk_id)["sha256"],
        "behavior_sha256": catalog.ref(behavior_id)["sha256"],
        "corpus_id": corpora["development"]["id"],
        "implementation_fingerprint": implementation["fingerprint"],
        "replay_fingerprint": replay["fingerprint"],
        "composition_id": composition_id,
        "assumptions": campaign_assumptions,
        "unsupported_semantics": unsupported,
        "engine_formal_input_artifact_id": raw_formal_id,
        "engine_formal_input_digest": digest_bytes(
            (raw_route_root / "formal-input.json").read_bytes()
        ),
    }
    formal_input_relative = f"{route_prefix}/formal-input.json"
    write_json(pack_root / formal_input_relative, formal_input_value, canonical=True)
    formal_input_id = artifact_identifier("formal-input", route_id)
    catalog.add(formal_input_id, "formal-input", formal_input_relative)
    formal_input_sha = catalog.ref(formal_input_id)["sha256"]

    raw_smt = (raw_route_root / "proof.smt2").read_bytes()
    raw_smt_sha = digest_bytes(raw_smt)
    raw_formal_sha = digest_bytes((raw_route_root / "formal-input.json").read_bytes())
    raw_solver_result_id = raw_ids[f"routes/{route_id}/solver-result.json"]
    raw_solver_result_sha = catalog.ref(raw_solver_result_id)["sha256"]
    raw_layered_result_id = raw_ids[f"routes/{route_id}/layered-result.json"]
    raw_layered_result_sha = catalog.ref(raw_layered_result_id)["sha256"]
    solver_realpath = raw_solver.get("solver_binary_realpath")
    raw_layered_links = raw_layered.get("links")
    if (
        set(raw_solver) != ENGINE_SOLVER_RESULT_KEYS
        or raw_solver.get("identity_status") != "VERIFIED"
        or not isinstance(solver_realpath, str)
        or not Path(solver_realpath).is_absolute()
        or Path(solver_realpath).name != "z3"
        or raw_solver.get("solver") != solver_realpath
        or raw_solver.get("solver_binary_sha256") != LOCKED_Z3_BINARY_SHA256
        or raw_solver.get("solver_version") != LOCKED_Z3_VERSION
        or raw_solver.get("invocation") != [solver_realpath, "-in"]
        or raw_solver.get("options") != LOCKED_Z3_OPTIONS
        or raw_solver.get("environment") != LOCKED_Z3_ENVIRONMENT
        or solver_binary.get("sha256") != raw_solver.get("solver_binary_sha256")
        or solver_binary.get("producer_realpath") != solver_realpath
        or raw_solver.get("formal_input_digest") != raw_formal_sha
        or raw_solver.get("solver_input_digest") != raw_smt_sha
        or raw_solver.get("smt2_digest") != raw_smt_sha
        or not isinstance(raw_layered_links, dict)
        or raw_layered_links.get("solver_result_path")
        != f"routes/{route_id}/solver-result.json"
        or raw_layered_links.get("solver_result_digest") != raw_solver_result_sha
    ):
        raise RuntimeError(f"ENGINE_SOLVER_IDENTITY_OR_LINKAGE_DRIFT:{route_id}")
    smt_content = (
        f"; formal_input_sha256 {formal_input_sha}\n"
        f"; implementation_fingerprint {implementation['fingerprint']}\n"
        f"; replay_fingerprint {replay['fingerprint']}\n"
    ).encode() + raw_smt
    smt_relative = f"{route_prefix}/proof.smt2"
    (pack_root / smt_relative).write_bytes(smt_content)
    smt_id = artifact_identifier("solver-input", route_id)
    catalog.add(smt_id, "solver-input", smt_relative)
    smt_sha = catalog.ref(smt_id)["sha256"]

    raw_outcome = raw_solver.get("outcome")
    solver_status = (
        raw_outcome if raw_outcome in {"UNSAT", "SAT", "UNKNOWN"} else "ERROR"
    )
    if solver_status == "UNSAT" and (
        raw_solver.get("exit_code") != 0
        or raw_solver.get("stdout") != "unsat\n"
        or raw_solver.get("stderr") != ""
        or raw_solver.get("proof_status") != "PROVED_UNDER_ASSUMPTIONS"
        or raw_solver.get("unconditional_proof") is not False
    ):
        raise RuntimeError(f"ENGINE_FAKE_UNSAT_RESULT:{route_id}")
    if (
        raw_solver.get("proof_status") == "PROVED_UNDER_ASSUMPTIONS"
        and solver_status == "UNSAT"
    ):
        formal_status = "PROVED_UNDER_ASSUMPTIONS"
        proof_strength = "assumption"
    elif raw_solver.get("proof_status") == "REFUTED" and solver_status == "SAT":
        formal_status = "REFUTED"
        proof_strength = "none"
    elif solver_status == "UNKNOWN":
        formal_status = "UNKNOWN"
        proof_strength = "none"
    else:
        formal_status = "NOT_PROVED"
        proof_strength = "none"
    if (
        raw_layered.get("status") != formal_status
        or raw_composition.get("status") != formal_status
    ):
        raise RuntimeError(f"ENGINE_FORMAL_STATUS_DRIFT:{route_id}")
    solver_result_value = {
        "schema_version": 1,
        "route_id": route_id,
        "solver": raw_solver["solver"],
        "solver_binary_realpath": raw_solver["solver_binary_realpath"],
        "solver_binary_sha256": raw_solver["solver_binary_sha256"],
        "solver_binary_artifact_id": solver_binary["artifact_id"],
        "solver_binary_bytes": solver_binary["bytes"],
        "solver_version": raw_solver["solver_version"],
        "identity_status": raw_solver["identity_status"],
        "invocation": raw_solver["invocation"],
        "options": raw_solver["options"],
        "environment": raw_solver["environment"],
        "status": solver_status,
        "exit_code": raw_solver.get("exit_code"),
        "stdout": raw_solver.get("stdout"),
        "stderr": raw_solver.get("stderr"),
        "proof_status": raw_solver.get("proof_status"),
        "unconditional_proof": raw_solver.get("unconditional_proof"),
        "formal_input_sha256": formal_input_sha,
        "solver_input_sha256": smt_sha,
        "raw_formal_input_sha256": raw_formal_sha,
        "raw_solver_input_sha256": raw_smt_sha,
        "raw_solver_result_sha256": raw_solver_result_sha,
        "raw_layered_result_sha256": raw_layered_result_sha,
        "raw_layered_solver_result_sha256": raw_solver_result_sha,
        "implementation_fingerprint": implementation["fingerprint"],
        "replay_fingerprint": replay["fingerprint"],
        "raw_solver_input_artifact_id": raw_ids[f"routes/{route_id}/proof.smt2"],
        "raw_solver_result_artifact_id": raw_solver_result_id,
        "raw_layered_result_artifact_id": raw_layered_result_id,
        "normalized_smt_transform": "comments-prefix-only-v1",
    }
    solver_result_relative = f"{route_prefix}/solver-result.json"
    write_json(pack_root / solver_result_relative, solver_result_value, canonical=True)
    solver_result_id = artifact_identifier("solver-result", route_id)
    catalog.add(solver_result_id, "solver-result", solver_result_relative)

    raw_route_ids = sorted(
        identifier
        for relative, identifier in raw_ids.items()
        if relative.startswith(f"routes/{route_id}/")
    )
    route_artifact_ids = sorted(
        set(
            raw_route_ids
            + [
                source_code_id,
                target_code_id,
                canonical_id,
                source_model_id,
                target_model_id,
                chunk_id,
                canonical_oracle_id,
                independent_oracle_id,
                behavior_id,
                formal_input_id,
                smt_id,
                solver_result_id,
                solver_binary["artifact_id"],
            ]
        )
    )
    toolchain_artifact_id = toolchain_evidence.get("artifact_id")
    if isinstance(toolchain_artifact_id, str):
        route_artifact_ids.append(toolchain_artifact_id)
        route_artifact_ids.sort()
    native_behavior = toolchain_route.get("native_behavior_status") == "PASSED"
    semantic_status = "NOT_RUN"
    composition_status = (
        formal_status
        if formal_status in {"PROVED", "PROVED_UNDER_ASSUMPTIONS", "REFUTED"}
        else "NOT_PROVED"
    )
    wrapper = {
        "schema_version": 1,
        "route_id": route_id,
        "source_profile_id": source_id,
        "target_profile_id": target_id,
        "source_profile_digest": profile_records[source_id]["profile_digest"],
        "target_profile_digest": profile_records[target_id]["profile_digest"],
        "semantic_blocks": semantic_blocks,
        "chunk_equivalence": {
            "artifact_id": chunk_id,
            "path_scheme": "rfc6901-json-pointer-v1",
            "mappings": mappings,
            "status": chunk_status,
        },
        "behavior": {
            "artifact_id": behavior_id,
            "canonical_oracle_artifact_id": canonical_oracle_id,
            "independent_oracle_artifact_id": independent_oracle_id,
            "source_runtime_kind": "browser" if native_behavior else "model",
            "target_runtime_kind": "browser" if native_behavior else "model",
            "case_count": len(behavior_value["cases"]),
            "pass_count": len(behavior_value["cases"]),
            "status": "PASSED",
            "native_execution": native_behavior,
            "native_evidence_status": toolchain_route["native_behavior_status"],
            "toolchain_evidence_artifact_id": toolchain_artifact_id,
            "source_execution_id": toolchain_route["source_execution_id"],
            "target_execution_id": toolchain_route["target_execution_id"],
            "source_build_status": toolchain_route["source_build_status"],
            "target_build_status": toolchain_route["target_build_status"],
            "source_browser_status": toolchain_route["source_browser_status"],
            "target_browser_status": toolchain_route["target_browser_status"],
        },
        "formal": {
            "formal_input_artifact_id": formal_input_id,
            "smt_artifact_id": smt_id,
            "solver_result_artifact_id": solver_result_id,
            "formal_input_sha256": formal_input_sha,
            "solver_input_sha256": smt_sha,
            "solver_result_sha256": catalog.ref(solver_result_id)["sha256"],
            "raw_solver_input_sha256": raw_smt_sha,
            "raw_solver_result_sha256": raw_solver_result_sha,
            "solver_binary_artifact_id": solver_binary["artifact_id"],
            "solver_binary_sha256": solver_binary["sha256"],
            "solver_binary_bytes": solver_binary["bytes"],
            "raw_layered_result_artifact_id": raw_layered_result_id,
            "raw_layered_result_sha256": raw_layered_result_sha,
            "raw_layered_solver_result_sha256": raw_solver_result_sha,
            "status": formal_status,
            "proof_strength": proof_strength,
            "composition_id": composition_id,
            "composition_status": composition_status,
            "assumptions": campaign_assumptions,
            "unsupported_semantics": unsupported,
            "unconditional": False,
        },
        "implementation_fingerprint": implementation["fingerprint"],
        "replay_fingerprint": replay["fingerprint"],
        "corpus_ids": {kind: corpora[kind]["id"] for kind in CORPUS_KINDS},
        "artifact_refs": [catalog.ref(item) for item in route_artifact_ids],
        "certification": "NOT_CERTIFIED",
    }
    wrapper_relative = f"{route_prefix}/route-evidence.json"
    write_json(pack_root / wrapper_relative, wrapper, canonical=True)
    wrapper_id = artifact_identifier("route-evidence", route_id)
    catalog.add(wrapper_id, "frontend-route-evidence", wrapper_relative)
    route_artifact_ids.append(wrapper_id)
    return {
        "route_id": route_id,
        "source_profile_id": source_id,
        "target_profile_id": target_id,
        "source_profile_digest": profile_records[source_id]["profile_digest"],
        "target_profile_digest": profile_records[target_id]["profile_digest"],
        "source_project_digest": route_entry["source_project_digest"],
        "target_project_digest": route_entry["target_project_digest"],
        "route_evidence_artifact_id": wrapper_id,
        "artifact_ids": sorted(route_artifact_ids),
        "semantic_status": semantic_status,
        "chunk_status": chunk_status,
        "behavior_status": "PASSED",
        "formal_status": formal_status,
        "composition_status": composition_status,
        "runtime_evidence_status": "BROWSER_PASSED"
        if native_behavior
        else "MODEL_ONLY",
        "source_build_status": toolchain_route["source_build_status"],
        "target_build_status": toolchain_route["target_build_status"],
    }


def add_json_artifact_v2(
    *,
    pack_root: Path,
    catalog: ArtifactCatalog,
    identifier_namespace: str,
    role: str,
    relative: str,
    value: object,
) -> str:
    write_json(pack_root / relative, value, canonical=True)
    identifier = artifact_identifier(identifier_namespace, relative)
    catalog.add(identifier, role, relative)
    return identifier


def channel_observation_not_run_v2(profile_id: str, channel: str) -> dict[str, Any]:
    required = channel in REQUIRED_RUNTIME_CHANNELS_V2[profile_id]
    return {
        "channel": channel,
        "required": required,
        "status": "NOT_RUN" if required else "NOT_APPLICABLE",
        "reason": (
            "REQUIRED_RUNTIME_CHANNEL_NOT_RUN"
            if required
            else "PROFILE_CHANNEL_NOT_APPLICABLE"
        ),
        "actual_derived": False,
        "model_values_used_as_actual": False,
        "observation_artifact_ids": [],
        "observation_actual_digests": [],
        "observation_digest": None,
        "scenario_count": 0,
        "result_manifest_artifact_id": None,
        "runtime_source_artifact_ids": [],
        "execution_policy_artifact_id": None,
        "raw_probe_artifact_ids": [],
        "build_execution_id": None,
        "startup_execution_id": None,
        "journey_execution_id": None,
    }


def channel_observation_v2(
    *,
    profile_id: str,
    channel: str,
    block_id: str,
    scenario_ids: list[str],
    runtime_capture: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    profile_capture = runtime_capture.get("profiles", {}).get(profile_id, {})
    channel_capture = profile_capture.get("channels", {}).get(channel)
    if not isinstance(channel_capture, dict):
        return channel_observation_not_run_v2(profile_id, channel), {}, []
    status = channel_capture.get("status")
    required = channel in REQUIRED_RUNTIME_CHANNELS_V2[profile_id]
    block_status = channel_capture.get("block_statuses", {}).get(block_id)
    if not isinstance(block_status, dict):
        value = channel_observation_not_run_v2(profile_id, channel)
        value["status"] = status
        value["reason"] = channel_capture.get("reason")
        return value, {}, []
    closure_ids = list(channel_capture.get("artifact_ids", []))
    if block_status.get("status") != "PASSED":
        value = channel_observation_not_run_v2(profile_id, channel)
        value.update(
            {
                "status": block_status.get("status"),
                "reason": block_status.get("reason"),
                "result_manifest_artifact_id": channel_capture.get(
                    "result_manifest_artifact_id"
                ),
                "runtime_source_artifact_ids": channel_capture.get(
                    "runtime_source_artifact_ids", []
                ),
                "execution_policy_artifact_id": channel_capture.get(
                    "execution_policy_artifact_id"
                ),
                "raw_probe_artifact_ids": channel_capture.get(
                    "raw_probe_artifact_ids", []
                ),
                "build_execution_id": channel_capture.get("build_execution_id"),
                "startup_execution_id": channel_capture.get("startup_execution_id"),
                "journey_execution_id": channel_capture.get("journey_execution_id"),
            }
        )
        return value, {}, closure_ids
    observations: dict[str, dict[str, Any]] = {}
    for scenario_id in scenario_ids:
        observation = channel_capture.get("observations", {}).get(
            (scenario_id, block_id)
        )
        if not isinstance(observation, dict):
            raise RuntimeError(
                f"V2_RUNTIME_BLOCK_OBSERVATION_MISSING:{profile_id}:{channel}:{scenario_id}:{block_id}"
            )
        observations[scenario_id] = observation
    observation_ids = [
        observations[scenario_id]["artifact_id"] for scenario_id in scenario_ids
    ]
    observation_digest = canonical_digest(
        [
            {
                "scenario_id": scenario_id,
                "actual_digest": observations[scenario_id]["actual_digest"],
            }
            for scenario_id in scenario_ids
        ]
    )
    return (
        {
            "channel": channel,
            "required": required,
            "status": "PASSED",
            "reason": None,
            "actual_derived": True,
            "model_values_used_as_actual": False,
            "observation_artifact_ids": observation_ids,
            "observation_actual_digests": [
                observations[scenario_id]["actual_digest"]
                for scenario_id in scenario_ids
            ],
            "observation_digest": observation_digest,
            "scenario_count": len(scenario_ids),
            "result_manifest_artifact_id": channel_capture[
                "result_manifest_artifact_id"
            ],
            "runtime_source_artifact_ids": channel_capture[
                "runtime_source_artifact_ids"
            ],
            "execution_policy_artifact_id": channel_capture[
                "execution_policy_artifact_id"
            ],
            "raw_probe_artifact_ids": channel_capture["raw_probe_artifact_ids"],
            "build_execution_id": channel_capture["build_execution_id"],
            "startup_execution_id": channel_capture["startup_execution_id"],
            "journey_execution_id": channel_capture["journey_execution_id"],
        },
        observations,
        closure_ids,
    )


def add_runtime_projection_policy_v2(
    pack_root: Path, catalog: ArtifactCatalog
) -> dict[str, Any]:
    value = {
        "schema_version": 2,
        "kind": "frontend-runtime-canonical-projection-policy-v2",
        "proof_profile": "bounded-frontend-interaction-v1",
        "semantic_block_ids": list(SEMANTIC_BLOCKS),
        "actual_keys": {
            block_id: sorted(RUNTIME_ACTUAL_KEYS_V2[block_id])
            for block_id in SEMANTIC_BLOCKS
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
    relative = "formal-campaign/runtime/canonical-projection-policy.json"
    identifier = add_json_artifact_v2(
        pack_root=pack_root,
        catalog=catalog,
        identifier_namespace="v2-runtime-projection-policy",
        role="runtime-canonical-projection-policy-v2",
        relative=relative,
        value=value,
    )
    return {
        "artifact_id": identifier,
        "fingerprint": canonical_digest(value),
        "policy": value,
    }


def canonical_runtime_projection_v2(
    *, block_id: str, channel: str, canonical_observation: dict[str, Any]
) -> dict[str, Any]:
    missing = RUNTIME_ACTUAL_KEYS_V2[block_id] - set(canonical_observation)
    if missing:
        raise RuntimeError(
            f"V2_CANONICAL_RUNTIME_PROJECTION_KEYS_MISSING:{block_id}:{sorted(missing)}"
        )
    projected = {
        key: canonical_observation[key]
        for key in sorted(RUNTIME_ACTUAL_KEYS_V2[block_id])
    }
    if channel == "browser" and block_id == "native-platform":
        projected.update(
            {"attempted": False, "available": False, "outcome": "NOT_ATTEMPTED"}
        )
    return projected


def validate_runtime_driver_contract_v2(
    *, profile_id: str, profile: dict[str, Any], scenario_ids: list[str]
) -> None:
    driver = profile.get("runtime_driver_contract")
    required_channels = list(REQUIRED_RUNTIME_CHANNELS_V2[profile_id])
    if (
        not isinstance(driver, dict)
        or set(driver) != RUNTIME_DRIVER_CONTRACT_KEYS_V2
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
        or driver.get("observer_protocol") != BLOCK_OBSERVER_CONTRACT_V2
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
        raise RuntimeError(f"V2_RUNTIME_DRIVER_CONTRACT_DRIFT:{profile_id}")
    browser_block_status_contract_v2(profile_id=profile_id, driver=driver)
    projection = driver.get("channel_projection_contract")
    if (
        not isinstance(projection, dict)
        or set(projection)
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
        or projection.get("model_digest") != profile.get("relift_model_digest")
        or not isinstance(projection.get("block_actual_keys"), dict)
        or set(projection["block_actual_keys"]) != set(SEMANTIC_BLOCKS)
        or any(
            not isinstance(projection["block_actual_keys"].get(block_id), list)
            or set(projection["block_actual_keys"][block_id])
            != RUNTIME_ACTUAL_KEYS_V2[block_id]
            for block_id in SEMANTIC_BLOCKS
        )
        or projection.get("scenario_ids") != scenario_ids
        or projection.get("oracle_provenance")
        != "SAME_PRODUCER_CHANNEL_PROJECTION_NOT_INDEPENDENT"
        or projection.get("arbitrary_customer_runtime") != "NOT_PROVED"
        or driver.get("channel_projection_contract_digest")
        != canonical_digest(projection)
    ):
        raise RuntimeError(f"V2_RUNTIME_PROJECTION_CONTRACT_DRIFT:{profile_id}")
    channels = projection.get("channels")
    if not isinstance(channels, dict) or set(channels) != set(required_channels):
        raise RuntimeError(f"V2_RUNTIME_PROJECTION_CHANNEL_CLOSURE:{profile_id}")
    for channel in required_channels:
        channel_value = channels[channel]
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
            raise RuntimeError(
                f"V2_RUNTIME_PROJECTION_CHANNEL_DRIFT:{profile_id}:{channel}"
            )
        for scenario in scenarios:
            blocks = scenario.get("blocks")
            block_digests = scenario.get("block_digests")
            if (
                set(scenario) != {"scenario_id", "blocks", "block_digests"}
                or not isinstance(blocks, dict)
                or set(blocks) != set(SEMANTIC_BLOCKS)
                or not isinstance(block_digests, dict)
                or set(block_digests) != set(SEMANTIC_BLOCKS)
            ):
                raise RuntimeError(
                    f"V2_RUNTIME_PROJECTION_SCENARIO_DRIFT:{profile_id}:{channel}"
                )
            for block_id in SEMANTIC_BLOCKS:
                actual = blocks[block_id]
                if (
                    not isinstance(actual, dict)
                    or set(actual) != RUNTIME_ACTUAL_KEYS_V2[block_id]
                    or block_digests[block_id] != canonical_digest(actual)
                ):
                    raise RuntimeError(
                        f"V2_RUNTIME_PROJECTION_BLOCK_DRIFT:{profile_id}:{channel}:{scenario['scenario_id']}:{block_id}"
                    )
                if channel == "browser" and block_id == "native-platform" and (
                    actual.get("attempted") is not False
                    or actual.get("available") is not False
                    or actual.get("outcome") != "NOT_ATTEMPTED"
                ):
                    raise RuntimeError(
                        f"V2_RUNTIME_PROJECTION_BROWSER_NATIVE_DRIFT:{profile_id}:{scenario['scenario_id']}"
                    )


def runtime_driver_projection_v2(
    *,
    profile_record: dict[str, Any],
    channel: str,
    scenario_id: str,
    block_id: str,
) -> dict[str, Any]:
    scenarios = profile_record["runtime_driver_contract"][
        "channel_projection_contract"
    ]["channels"][channel]["scenarios"]
    matches = [row for row in scenarios if row.get("scenario_id") == scenario_id]
    if len(matches) != 1:
        raise RuntimeError(
            f"V2_RUNTIME_DRIVER_PROJECTION_LOOKUP_DRIFT:{channel}:{scenario_id}:{block_id}"
        )
    return dict(matches[0]["blocks"][block_id])


def aggregate_evidence_status_v2(
    values: list[str], *, applicable: bool = True
) -> str:
    if not applicable:
        return "NOT_APPLICABLE"
    if not values or all(item == "NOT_RUN" for item in values):
        return "NOT_RUN"
    if "FAILED" in values:
        return "FAILED"
    if all(item in {"PASSED", "NOT_APPLICABLE"} for item in values):
        return "PASSED"
    return "PARTIAL"


def closed_evidence_status_v2(
    values: list[str], *, applicable: bool = True
) -> str:
    """Fail a readiness dimension closed when any applicable closure is absent."""

    if not applicable:
        return "NOT_APPLICABLE"
    if "FAILED" in values:
        return "FAILED"
    if values and all(item in {"PASSED", "NOT_APPLICABLE"} for item in values):
        return "PASSED"
    return "NOT_RUN"


def unsupported_semantics_v2(
    *,
    arbitrary_customer_source: str,
    profile_channel_statuses: dict[str, dict[str, str]],
    independent_status: str,
) -> list[str]:
    """Derive campaign limitations only from validated closure dimensions."""

    unsupported: list[str] = []
    if arbitrary_customer_source != "PROVED":
        unsupported.append(
            f"arbitrary-customer-source-{arbitrary_customer_source}"
        )
    for channel in RUNTIME_CHANNELS_V2:
        aggregate = aggregate_evidence_status_v2(
            [
                profile_channel_statuses.get(profile_id, {}).get(
                    channel, "NOT_RUN"
                )
                for profile_id in PROFILE_IDS
                if channel in REQUIRED_RUNTIME_CHANNELS_V2[profile_id]
            ]
        )
        if aggregate != "PASSED":
            unsupported.append(f"{channel}-runtime-{aggregate}")
    if independent_status != "PASSED":
        unsupported.append(
            f"independent-external-verification-{independent_status}"
        )
    return unsupported


def aggregate_route_runtime_dimensions_v2(
    *,
    blocks: list[dict[str, Any]],
    source_profile_id: str,
    target_profile_id: str,
) -> dict[str, str]:
    """Aggregate browser, native, and all-channel runtime independently."""

    browser_states: list[str] = []
    native_states: list[str] = []
    runtime_states: list[str] = []
    native_applicable = any(
        channel != "browser"
        for profile_id in (source_profile_id, target_profile_id)
        for channel in REQUIRED_RUNTIME_CHANNELS_V2[profile_id]
    )
    for block in blocks:
        block_runtime = block["runtime"]
        for endpoint, profile_id in (
            ("source", source_profile_id),
            ("target", target_profile_id),
        ):
            for channel in REQUIRED_RUNTIME_CHANNELS_V2[profile_id]:
                state = str(block_runtime[endpoint]["channels"][channel]["status"])
                runtime_states.append(state)
                if channel == "browser":
                    browser_states.append(state)
                else:
                    native_states.append(state)
        dimensions = block_runtime["cross_channel_equivalence"]["dimension_closure"]
        runtime_states.append(str(dimensions["runtime"]["status"]))
        if dimensions["browser"]["applicable"]:
            browser_states.append(str(dimensions["browser"]["status"]))
        if dimensions["native"]["applicable"]:
            native_states.append(str(dimensions["native"]["status"]))
    return {
        "browser_status": closed_evidence_status_v2(
            browser_states, applicable=bool(browser_states)
        ),
        "native_status": closed_evidence_status_v2(
            native_states, applicable=native_applicable
        ),
        "runtime_status": closed_evidence_status_v2(runtime_states),
    }


def normalize_route_v2(
    *,
    engine_root: Path,
    pack_root: Path,
    catalog: ArtifactCatalog,
    raw_ids: dict[str, str],
    route: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
    profile_records: dict[str, dict[str, Any]],
    scenario_ids: list[str],
    scenario_digest: str,
    implementation: dict[str, Any],
    replay: dict[str, Any],
    corpora: dict[str, Any],
    assumptions: list[str],
    mutation_digest: str,
    toolchain_artifact_id: str | None,
    toolchain_producer_fingerprint: str,
    solver_binary: dict[str, Any],
    runtime_capture: dict[str, Any],
    runtime_projection: dict[str, Any],
    external_capture: dict[str, Any],
) -> dict[str, Any]:
    route_id = str(route["route_id"])
    source_id = str(route["source_profile"])
    target_id = str(route["target_profile"])
    route_root = engine_root / "routes" / route_id
    source_model = load_json(route_root / "source-model.json")
    target_model = load_json(route_root / "target-model.json")
    behavior = load_json(route_root / "behavior.json")
    chunks = load_json(route_root / "chunks.json")
    formal_input = load_json(route_root / "formal-input.json")
    raw_solver = load_json(route_root / "solver-result.json")
    block_results = load_json(route_root / "block-results.json")
    composition = load_json(route_root / "composition.json")
    layered_result = load_json(route_root / "layered-result.json")
    proof_status = raw_solver.get("proof_status")
    proof_strength = formal_proof_contract_v2(
        proof_status=proof_status,
        unconditional_proof=raw_solver.get("unconditional_proof"),
        assumptions=assumptions,
        label=f"route:{route_id}:solver",
    )
    if (
        set(raw_solver) != ENGINE_SOLVER_RESULT_KEYS
        or raw_solver.get("route_id") != route_id
        or raw_solver.get("outcome") != "UNSAT"
        or raw_solver.get("exit_code") != 0
        or raw_solver.get("stdout") != "unsat\n"
        or raw_solver.get("stderr") != ""
        or proof_status not in {"PROVED", "PROVED_UNDER_ASSUMPTIONS"}
        or route.get("status") != proof_status
        or route.get("layered_result") != proof_status
        or composition.get("status") != proof_status
        or layered_result.get("status") != proof_status
    ):
        raise RuntimeError(f"V2_ROUTE_FORMAL_CLAIM_DRIFT:{route_id}")
    canonical_model = formal_input["canonical_model"]
    if (
        source_model.get("model") != canonical_model
        or target_model.get("model") != canonical_model
        or source_model.get("model_digest") != canonical_digest(canonical_model)
        or target_model.get("model_digest") != canonical_digest(canonical_model)
    ):
        raise RuntimeError(f"V2_ROUTE_MODEL_DRIFT:{route_id}")

    normalized_ids: list[str] = []
    documents: dict[str, tuple[dict[str, Any], str]] = {}
    for name, document, role in (
        ("canonical-ir", canonical_model, "canonical-ir-v2"),
        ("source-relift-ir", source_model["model"], "source-relift-ir-v2"),
        ("target-relift-ir", target_model["model"], "target-relift-ir-v2"),
    ):
        relative = f"formal-campaign/routes/{route_id}/{name}.json"
        identifier = add_json_artifact_v2(
            pack_root=pack_root,
            catalog=catalog,
            identifier_namespace=f"v2-route-{route_id}",
            role=role,
            relative=relative,
            value=document,
        )
        normalized_ids.append(identifier)
        documents[name] = (document, identifier)

    code: dict[str, tuple[bytes, str]] = {}
    for endpoint, profile_id, model, role in (
        ("source", source_id, source_model, "source-code"),
        ("target", target_id, target_model, "target-code"),
    ):
        source_path = safe_source_file(
            engine_root / str(profiles[profile_id]["project_path"]),
            model.get("source_path"),
            f"v2_route_{route_id}_{endpoint}_code",
        )
        relative = f"formal-campaign/routes/{route_id}/{endpoint}-code/" + str(
            model["source_path"]
        )
        destination = pack_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        identifier = artifact_identifier(
            f"v2-route-{route_id}-{endpoint}-code", str(model["source_path"])
        )
        catalog.add(identifier, role, relative)
        normalized_ids.append(identifier)
        code[endpoint] = (destination.read_bytes(), identifier)

    observation_indexes: dict[str, dict[str, dict[str, Any]]] = {}
    for name in ("canonical", "reference", "source", "target"):
        rows = behavior.get(name, {}).get("observations")
        if not isinstance(rows, list):
            raise RuntimeError(f"V2_ROUTE_BEHAVIOR_MISSING:{route_id}:{name}")
        observation_indexes[name] = {
            str(row["scenarioId"]): row for row in rows if isinstance(row, dict)
        }
        if list(observation_indexes[name]) != scenario_ids:
            raise RuntimeError(f"V2_ROUTE_SCENARIO_ORDER_DRIFT:{route_id}:{name}")

    block_rows = {
        str(row["block_id"]): row
        for row in block_results.get("blocks", [])
        if isinstance(row, dict)
    }
    if tuple(block_rows) != SEMANTIC_BLOCKS:
        raise RuntimeError(f"V2_ROUTE_BLOCK_RESULTS_DRIFT:{route_id}")
    if any(
        row.get("raw_solver_status") != proof_status
        or row.get("formal_status") != proof_status
        or row.get("status") != proof_status
        for row in block_rows.values()
    ):
        raise RuntimeError(f"V2_ROUTE_BLOCK_FORMAL_CLAIM_DRIFT:{route_id}")
    block_assumptions = [] if proof_status == "PROVED" else assumptions
    block_unsupported = (
        []
        if proof_status == "PROVED"
        else ["compiler-framework-browser-device-runtime-soundness-NOT_PROVED"]
    )
    raw_chunks = chunks.get("chunks")
    if not isinstance(raw_chunks, list):
        raise RuntimeError(f"V2_ROUTE_CHUNKS_MISSING:{route_id}")
    raw_by_pointer = {
        str(row["pointer"]): row for row in raw_chunks if isinstance(row, dict)
    }
    blocks: list[dict[str, Any]] = []
    for block_id in SEMANTIC_BLOCKS:
        block_row = block_rows[block_id]
        pointer = BLOCK_ROOT_POINTERS_V2[block_id]
        root_chunk = raw_by_pointer.get(pointer)
        if not isinstance(root_chunk, dict):
            raise RuntimeError(f"V2_BLOCK_ROOT_CHUNK_MISSING:{route_id}:{block_id}")
        semantic_hash = str(block_row["canonical_block_digest"])
        semantic = {
            "canonical_ir": span_ref(
                documents["canonical-ir"][1], canonical_model, pointer
            ),
            "source_relift_ir": span_ref(
                documents["source-relift-ir"][1], source_model["model"], pointer
            ),
            "target_relift_ir": span_ref(
                documents["target-relift-ir"][1], target_model["model"], pointer
            ),
            "source_code": code_span_ref(
                code["source"][1],
                code["source"][0],
                int(root_chunk["source"]["start_byte"]),
                int(root_chunk["source"]["end_byte"]),
                str(source_model["parser"]),
            ),
            "target_code": code_span_ref(
                code["target"][1],
                code["target"][0],
                int(root_chunk["target"]["start_byte"]),
                int(root_chunk["target"]["end_byte"]),
                str(target_model["parser"]),
            ),
            "semantic_hash": semantic_hash,
            "status": "PASSED",
        }

        model_influences = block_row["influence_classes"]["model"]
        runtime_influences = block_row["influence_classes"]["runtime"]
        block_raw_chunks = [
            row for row in raw_chunks if row.get("block_id") == block_id
        ]
        semantic_mappings: list[dict[str, Any]] = []
        for semantic_pointer in model_influences:
            raw = raw_by_pointer.get(semantic_pointer)
            if not isinstance(raw, dict):
                raise RuntimeError(
                    f"V2_SEMANTIC_POINTER_CHUNK_MISSING:{route_id}:{block_id}:{semantic_pointer}"
                )
            semantic_mappings.append(
                {
                    "pointer": semantic_pointer,
                    "canonical_ir": span_ref(
                        documents["canonical-ir"][1], canonical_model, semantic_pointer
                    ),
                    "source_relift_ir": span_ref(
                        documents["source-relift-ir"][1],
                        source_model["model"],
                        semantic_pointer,
                    ),
                    "target_relift_ir": span_ref(
                        documents["target-relift-ir"][1],
                        target_model["model"],
                        semantic_pointer,
                    ),
                    "source_code": code_span_ref(
                        code["source"][1],
                        code["source"][0],
                        int(raw["source"]["start_byte"]),
                        int(raw["source"]["end_byte"]),
                        str(source_model["parser"]),
                    ),
                    "target_code": code_span_ref(
                        code["target"][1],
                        code["target"][0],
                        int(raw["target"]["start_byte"]),
                        int(raw["target"]["end_byte"]),
                        str(target_model["parser"]),
                    ),
                    "semantic_hash": raw["canonical_subtree_hash"],
                    "model_influence": model_influences[semantic_pointer],
                    "runtime_influence": runtime_influences[semantic_pointer],
                    "status": "PASSED",
                }
            )
        chunk_value = {
            "schema_version": 2,
            "kind": "frontend-chunk-map-v2",
            "route_id": route_id,
            "block_id": block_id,
            "path_scheme": "rfc6901-json-pointer-v1",
            "mappings": block_raw_chunks,
            "semantic_mappings": semantic_mappings,
            "status": "PASSED",
        }
        chunk_relative = (
            f"formal-campaign/routes/{route_id}/blocks/{block_id}/chunks.json"
        )
        chunk_id = add_json_artifact_v2(
            pack_root=pack_root,
            catalog=catalog,
            identifier_namespace=f"v2-route-{route_id}-{block_id}",
            role="chunk-map-v2",
            relative=chunk_relative,
            value=chunk_value,
        )
        normalized_ids.append(chunk_id)

        behavior_cases = [
            {
                "scenario_id": scenario_id,
                "canonical": observation_indexes["canonical"][scenario_id]["blocks"][
                    block_id
                ],
                "reference": observation_indexes["reference"][scenario_id]["blocks"][
                    block_id
                ],
                "source": observation_indexes["source"][scenario_id]["blocks"][
                    block_id
                ],
                "target": observation_indexes["target"][scenario_id]["blocks"][
                    block_id
                ],
                "status": "PASSED",
            }
            for scenario_id in scenario_ids
        ]
        behavior_value = {
            "schema_version": 2,
            "kind": "frontend-model-behavior-v2",
            "route_id": route_id,
            "block_id": block_id,
            "runtime_kind": "RELIFTED_MODEL_INTERPRETER",
            "independent": False,
            "cases": behavior_cases,
            "status": "PASSED",
        }
        behavior_relative = (
            f"formal-campaign/routes/{route_id}/blocks/{block_id}/model-behavior.json"
        )
        behavior_id = add_json_artifact_v2(
            pack_root=pack_root,
            catalog=catalog,
            identifier_namespace=f"v2-route-{route_id}-{block_id}",
            role="model-behavior-v2",
            relative=behavior_relative,
            value=behavior_value,
        )
        normalized_ids.append(behavior_id)

        source_required = REQUIRED_RUNTIME_CHANNELS_V2[source_id]
        target_required = REQUIRED_RUNTIME_CHANNELS_V2[target_id]
        required_union = [
            channel
            for channel in RUNTIME_CHANNELS_V2
            if channel in set(source_required) | set(target_required)
        ]
        endpoint_runtime: dict[str, dict[str, Any]] = {}
        endpoint_observations: dict[
            str, dict[str, dict[str, dict[str, Any]]]
        ] = {}
        runtime_closure_ids: list[str] = []
        for endpoint, profile_id in (("source", source_id), ("target", target_id)):
            channels: dict[str, Any] = {}
            endpoint_observations[endpoint] = {}
            for channel in RUNTIME_CHANNELS_V2:
                channel_value, actuals, closure_ids = channel_observation_v2(
                    profile_id=profile_id,
                    channel=channel,
                    block_id=block_id,
                    scenario_ids=scenario_ids,
                    runtime_capture=runtime_capture,
                )
                channels[channel] = channel_value
                endpoint_observations[endpoint][channel] = actuals
                runtime_closure_ids.extend(closure_ids)
            endpoint_runtime[endpoint] = {
                "profile_id": profile_id,
                "required_runtime_channels": list(
                    REQUIRED_RUNTIME_CHANNELS_V2[profile_id]
                ),
                "channels": channels,
            }
        normalized_ids.extend(runtime_closure_ids)
        normalized_ids.append(runtime_projection["artifact_id"])

        comparisons: list[dict[str, Any]] = []
        for source_channel in source_required:
            for target_channel in target_required:
                for scenario_id in scenario_ids:
                    source_actual = endpoint_observations["source"][source_channel].get(
                        scenario_id
                    )
                    target_actual = endpoint_observations["target"][target_channel].get(
                        scenario_id
                    )
                    if isinstance(source_actual, dict) and isinstance(
                        target_actual, dict
                    ):
                        source_projection = runtime_driver_projection_v2(
                            profile_record=profile_records[source_id],
                            channel=source_channel,
                            scenario_id=scenario_id,
                            block_id=block_id,
                        )
                        target_projection = runtime_driver_projection_v2(
                            profile_record=profile_records[target_id],
                            channel=target_channel,
                            scenario_id=scenario_id,
                            block_id=block_id,
                        )
                        source_projection_digest = canonical_digest(
                            source_projection
                        )
                        target_projection_digest = canonical_digest(
                            target_projection
                        )
                        source_actual_digest = source_actual["actual_digest"]
                        target_actual_digest = target_actual["actual_digest"]
                        comparison_status = (
                            "PASSED"
                            if source_actual_digest == source_projection_digest
                            and target_actual_digest == target_projection_digest
                            else "FAILED"
                        )
                    else:
                        source_actual_digest = None
                        target_actual_digest = None
                        source_projection_digest = None
                        target_projection_digest = None
                        comparison_status = "NOT_RUN"
                    comparisons.append(
                        {
                            "source_channel": source_channel,
                            "target_channel": target_channel,
                            "scenario_id": scenario_id,
                            "source_observation_digest": source_actual_digest,
                            "target_observation_digest": target_actual_digest,
                            "source_canonical_projection_digest": source_projection_digest,
                            "target_canonical_projection_digest": target_projection_digest,
                            "relation": "EACH_ACTUAL_EQUALS_ITS_CHANNEL_CANONICAL_PROJECTION",
                            "status": comparison_status,
                        }
                    )
        comparison_statuses = [row["status"] for row in comparisons]
        cross_status = (
            "FAILED"
            if "FAILED" in comparison_statuses
            else "PASSED"
            if comparison_statuses and all(item == "PASSED" for item in comparison_statuses)
            else "NOT_RUN"
        )
        cross_pass_count = sum(item == "PASSED" for item in comparison_statuses)
        dimension_rows = {
            "browser": [
                row
                for row in comparisons
                if row["source_channel"] == "browser"
                and row["target_channel"] == "browser"
            ],
            "native": [
                row
                for row in comparisons
                if row["source_channel"] != "browser"
                and row["target_channel"] != "browser"
            ],
            "runtime": comparisons,
        }
        dimension_closure = {
            name: {
                "applicable": bool(rows),
                "comparison_count": len(rows),
                "pass_count": sum(row["status"] == "PASSED" for row in rows),
                "status": closed_evidence_status_v2(
                    [str(row["status"]) for row in rows], applicable=bool(rows)
                ),
            }
            for name, rows in dimension_rows.items()
        }
        cross_value = {
            "schema_version": 2,
            "kind": "frontend-cross-channel-equivalence-v2",
            "route_id": route_id,
            "block_id": block_id,
            "required_channel_union": required_union,
            "scenario_ids": scenario_ids,
            "comparisons": comparisons,
            "projection_policy_artifact_id": runtime_projection["artifact_id"],
            "projection_policy_fingerprint": runtime_projection["fingerprint"],
            "dimension_closure": dimension_closure,
            "status": cross_status,
        }
        cross_relative = (
            f"formal-campaign/routes/{route_id}/blocks/{block_id}/cross-channel.json"
        )
        cross_id = add_json_artifact_v2(
            pack_root=pack_root,
            catalog=catalog,
            identifier_namespace=f"v2-route-{route_id}-{block_id}",
            role="cross-channel-equivalence-v2",
            relative=cross_relative,
            value=cross_value,
        )
        normalized_ids.append(cross_id)

        formal_ids = {
            "formal_input_artifact_id": raw_ids[str(route["formal_input_path"])],
            "smt_artifact_id": raw_ids[str(route["solver_input_path"])],
            "solver_result_artifact_id": raw_ids[str(route["solver_result_path"])],
            "solver_binary_artifact_id": solver_binary["artifact_id"],
            "vacuity_input_artifact_id": raw_ids[str(route["vacuity_input_path"])],
            "vacuity_result_artifact_id": raw_ids[
                str(route["vacuity_solver_result_path"])
            ],
            "block_result_artifact_id": raw_ids[str(route["block_results_path"])],
            "composition_artifact_id": raw_ids[str(route["composition_path"])],
            "layered_result_artifact_id": raw_ids[str(route["evidence_path"])],
        }
        normalized_ids.extend(formal_ids.values())
        formal = {
            "obligation_symbol": block_row["obligation_symbol"],
            **formal_ids,
            "solver_binary_sha256": solver_binary["sha256"],
            "solver_binary_bytes": solver_binary["bytes"],
            "formal_input_sha256": catalog.ref(formal_ids["formal_input_artifact_id"])[
                "sha256"
            ],
            "solver_input_sha256": catalog.ref(formal_ids["smt_artifact_id"])["sha256"],
            "solver_result_sha256": catalog.ref(
                formal_ids["solver_result_artifact_id"]
            )["sha256"],
            "vacuity_input_sha256": catalog.ref(
                formal_ids["vacuity_input_artifact_id"]
            )["sha256"],
            "vacuity_result_sha256": catalog.ref(
                formal_ids["vacuity_result_artifact_id"]
            )["sha256"],
            "block_result_sha256": catalog.ref(formal_ids["block_result_artifact_id"])[
                "sha256"
            ],
            "composition_sha256": catalog.ref(formal_ids["composition_artifact_id"])[
                "sha256"
            ],
            "layered_result_sha256": catalog.ref(
                formal_ids["layered_result_artifact_id"]
            )["sha256"],
            "model_influence_max": block_row["model_influence_max"],
            "runtime_influence_max": block_row["runtime_influence_max"],
            "declaration_echo_excluded": True,
            "assumption_precheck": block_row["assumption_precheck"],
            "status": block_row["formal_status"],
            "proof_strength": proof_strength,
            "assumptions": block_assumptions,
            "unsupported_semantics": block_unsupported,
            "replay_status": "PASSED",
            "oracle_independence": "NOT_INDEPENDENT_SINGLE_ENGINE",
        }
        runtime = {
            "toolchain_evidence_artifact_id": toolchain_artifact_id,
            **endpoint_runtime,
            "cross_channel_equivalence": {
                "artifact_id": cross_id,
                "required_channel_union": required_union,
                "required_pair_count": len(source_required) * len(target_required),
                "scenario_count": len(scenario_ids),
                "comparison_count": len(comparisons),
                "pass_count": cross_pass_count,
                "projection_policy_artifact_id": runtime_projection["artifact_id"],
                "projection_policy_fingerprint": runtime_projection["fingerprint"],
                "dimension_closure": dimension_closure,
                "status": cross_status,
            },
        }
        external_result = external_capture.get("results", {}).get(
            (route_id, block_id)
        )
        if isinstance(external_result, dict):
            independent_artifact_ids = sorted(
                {
                    *external_result.get("execution_artifact_ids", []),
                    external_result.get("replay_artifact_id"),
                    external_capture.get("authorization_artifact_id"),
                }
            )
            normalized_ids.extend(independent_artifact_ids)
            independent = {
                "status": external_result.get("status"),
                "same_producer": False,
                "producer_fingerprint": external_capture.get(
                    "producer_fingerprint"
                ),
                "artifact_ids": independent_artifact_ids,
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
        else:
            independent = {
                "status": "NOT_RUN",
                "same_producer": True,
                "producer_fingerprint": implementation["fingerprint"],
                "artifact_ids": [],
                "holdout_status": "NOT_RUN",
                "representative_status": "NOT_RUN",
                "customer_status": "NOT_RUN",
                "authorization_artifact_id": None,
                "executor_organization_id": None,
                "verifier_organization_id": None,
                "replay_status": "NOT_RUN",
            }
        blocks.append(
            {
                "block_id": block_id,
                "semantic": semantic,
                "chunk": {
                    "artifact_id": chunk_id,
                    "path_scheme": "rfc6901-json-pointer-v1",
                    "mapping_count": len(block_raw_chunks),
                    "semantic_mapping_count": len(semantic_mappings),
                    "status": "PASSED",
                },
                "model_behavior": {
                    "artifact_id": behavior_id,
                    "runtime_kind": "RELIFTED_MODEL_INTERPRETER",
                    "scenario_manifest_sha256": scenario_digest,
                    "scenario_count": len(scenario_ids),
                    "pass_count": len(scenario_ids),
                    "reference_oracle_kind": "SAME_ENGINE_REFERENCE_REDUCER",
                    "independent": False,
                    "status": "PASSED",
                },
                "formal": formal,
                "runtime": runtime,
                "independent": independent,
            }
        )

    normalized_ids.append(solver_binary["artifact_id"])
    route_artifact_ids = sorted(set(normalized_ids))
    wrapper = {
        "schema_version": 2,
        "route_id": route_id,
        "source_profile_id": source_id,
        "target_profile_id": target_id,
        "source_profile_digest": profile_records[source_id]["profile_digest"],
        "target_profile_digest": profile_records[target_id]["profile_digest"],
        "scenario_manifest_sha256": scenario_digest,
        "scenario_ids": scenario_ids,
        "blocks": blocks,
        "implementation_fingerprint": implementation["fingerprint"],
        "replay_fingerprint": replay["fingerprint"],
        "corpus_ids": {name: corpora[name]["id"] for name in CORPUS_KINDS},
        "artifact_refs": [catalog.ref(identifier) for identifier in route_artifact_ids],
        "certification": "NOT_CERTIFIED",
    }
    wrapper_relative = f"formal-campaign/routes/{route_id}/route-evidence.json"
    wrapper_id = add_json_artifact_v2(
        pack_root=pack_root,
        catalog=catalog,
        identifier_namespace=f"v2-route-{route_id}",
        role="frontend-route-evidence-v2",
        relative=wrapper_relative,
        value=wrapper,
    )
    dimension_statuses = aggregate_route_runtime_dimensions_v2(
        blocks=blocks,
        source_profile_id=source_id,
        target_profile_id=target_id,
    )
    del toolchain_producer_fingerprint, mutation_digest
    return {
        "route_id": route_id,
        "source_profile_id": source_id,
        "target_profile_id": target_id,
        "source_profile_digest": profile_records[source_id]["profile_digest"],
        "target_profile_digest": profile_records[target_id]["profile_digest"],
        "source_project_digest": route["source_project_digest"],
        "target_project_digest": route["target_project_digest"],
        "route_evidence_artifact_id": wrapper_id,
        "artifact_ids": sorted(route_artifact_ids + [wrapper_id]),
        "block_count": 12,
        "model_formal_status": "PASSED",
        "browser_status": dimension_statuses["browser_status"],
        "native_status": dimension_statuses["native_status"],
        "independent_status": aggregate_evidence_status_v2(
            [str(block["independent"]["status"]) for block in blocks]
        ),
        "runtime_status": dimension_statuses["runtime_status"],
    }


def build_common_campaign(
    repo_root: Path,
    engine_root: Path,
    common_root: Path,
    toolchain_evidence_path: Path | None = None,
) -> Path:
    campaign_schema = (
        repo_root / "schemas/batch32/frontend-formal-route-campaign.schema.json"
    )
    profiles = exact_profiles(campaign_schema)
    raw_campaign = load_json(engine_root / "frontend-formal-route-campaign.json")
    profile_entries, route_entries = validate_engine_campaign(
        engine_root, raw_campaign, profiles
    )
    formal_root = common_root / "formal-campaign"
    formal_root.mkdir(parents=True, exist_ok=True)
    catalog = ArtifactCatalog(common_root)
    raw_ids, raw_campaign_id = copy_engine_output(engine_root, common_root, catalog)
    solver_binary = capture_solver_binary(
        engine_root=engine_root,
        pack_root=common_root,
        catalog=catalog,
        route_entries=route_entries,
    )
    implementation = install_bundle(
        repo_root=repo_root,
        pack_root=common_root,
        catalog=catalog,
        name="implementation",
        sources=[
            (
                "engines/frontend-client-engine/src/frontend-formal-equivalence.ts",
                "frontend-formal-equivalence.ts",
                "implementation-source",
            ),
            (
                "engines/frontend-client-engine/src/frontend-formal-cli.ts",
                "frontend-formal-cli.ts",
                "implementation-source",
            ),
            (
                "engines/frontend-client-engine/src/bounded-navigation-source.ts",
                "bounded-navigation-source.ts",
                "implementation-source",
            ),
            (
                "engines/frontend-client-engine/src/project-generation.ts",
                "project-generation.ts",
                "implementation-source",
            ),
            (
                "engines/frontend-client-engine/src/project-profiles.ts",
                "project-profiles.ts",
                "implementation-source",
            ),
            (
                "engines/frontend-client-engine/src/project-templates.ts",
                "project-templates.ts",
                "implementation-source",
            ),
            (
                "engines/frontend-client-engine/src/project-types.ts",
                "project-types.ts",
                "implementation-source",
            ),
            (
                "engines/frontend-client-engine/test/frontend-formal-equivalence.test.ts",
                "frontend-formal-equivalence.test.ts",
                "implementation-test",
            ),
            (
                "engines/frontend-client-engine/package.json",
                "package.json",
                "implementation-lock",
            ),
            (
                "engines/frontend-client-engine/pnpm-lock.yaml",
                "pnpm-lock.yaml",
                "implementation-lock",
            ),
            (
                "engines/frontend-client-engine/tsconfig.json",
                "tsconfig.json",
                "implementation-config",
            ),
            (
                "tooling/run_frontend_formal_toolchains.py",
                "run_frontend_formal_toolchains.py",
                "implementation-source",
            ),
            (
                "tooling/generate_frontend_formal_verification_pack.py",
                "generate_frontend_formal_verification_pack.py",
                "implementation-source",
            ),
            (
                "scripts/batch32/run_client_gate.py",
                "run_client_gate.py",
                "implementation-gate",
            ),
            (
                "scripts/batch35/run_verification_gate.py",
                "run_verification_gate.py",
                "implementation-gate",
            ),
            (
                "scripts/batch35/validate_frontend_formal_route_campaign.py",
                "validate_batch35_frontend_formal_route_campaign.py",
                "implementation-validator",
            ),
        ],
    )
    replay = install_bundle(
        repo_root=repo_root,
        pack_root=common_root,
        catalog=catalog,
        name="replay",
        sources=[
            (
                "scripts/batch32/validate_frontend_formal_route_campaign.py",
                "validate_frontend_formal_route_campaign.py",
                "replay-tool",
            ),
            (
                "schemas/batch32/frontend-formal-route-campaign.schema.json",
                "schemas/batch32/frontend-formal-route-campaign.schema.json",
                "replay-schema",
            ),
            (
                "schemas/batch32/frontend-formal-route-evidence.schema.json",
                "schemas/batch32/frontend-formal-route-evidence.schema.json",
                "replay-schema",
            ),
        ],
    )
    replay["command"] = [
        "python3",
        "formal-campaign/replay/validate_frontend_formal_route_campaign.py",
        ".",
        "--campaign",
        "formal-campaign/frontend-formal-route-campaign.json",
        "--schema",
        "formal-campaign/replay/schemas/batch32/frontend-formal-route-campaign.schema.json",
        "--route-schema",
        "formal-campaign/replay/schemas/batch32/frontend-formal-route-evidence.schema.json",
        "--no-replay-execute",
        "--json",
    ]
    corpora = add_corpora(common_root, catalog)
    toolchain_evidence, toolchain_profiles, toolchain_routes = add_toolchain_evidence(
        repo_root=repo_root,
        engine_root=engine_root,
        pack_root=common_root,
        catalog=catalog,
        profile_entries=profile_entries,
        route_entries=route_entries,
        evidence_path=toolchain_evidence_path,
    )

    profile_records: dict[str, dict[str, Any]] = {}
    for profile_id in PROFILE_IDS:
        entry = profile_entries[profile_id]
        project_prefix = f"profiles/{profile_id}/project/"
        project_files: list[dict[str, str]] = []
        profile_artifact_ids: list[str] = []
        for relative, identifier in sorted(raw_ids.items()):
            if relative.startswith(project_prefix):
                project_files.append(
                    {
                        "relative_path": relative[len(project_prefix) :],
                        "artifact_id": identifier,
                    }
                )
                profile_artifact_ids.append(identifier)
            elif relative == f"profiles/{profile_id}/manifest.json":
                profile_artifact_ids.append(identifier)
        if not project_files:
            raise RuntimeError(f"PROFILE_PROJECT_ARTIFACTS_MISSING:{profile_id}")
        profile_records[profile_id] = {
            "profile": profiles[profile_id],
            "profile_digest": canonical_digest(profiles[profile_id]),
            "project_digest": entry["project_digest"],
            "project_files": project_files,
            "artifact_ids": sorted(profile_artifact_ids),
        }

    assumptions = list(raw_campaign.get("assumptions", []))
    if not assumptions:
        raise RuntimeError("ENGINE_ASSUMPTIONS_REQUIRED")
    routes = [
        normalize_route(
            engine_root=engine_root,
            pack_root=common_root,
            catalog=catalog,
            raw_ids=raw_ids,
            route_id=route_id,
            route_entry=route_entries[route_id],
            profile_entries=profile_entries,
            profile_records=profile_records,
            implementation=implementation,
            replay=replay,
            corpora=corpora,
            campaign_assumptions=assumptions,
            toolchain_evidence=toolchain_evidence,
            toolchain_profiles=toolchain_profiles,
            toolchain_route=toolchain_routes[route_id],
            solver_binary=solver_binary,
        )
        for route_id in sorted(route_entries)
    ]
    profile_list = [profile_records[item] for item in PROFILE_IDS]
    scope_value = {
        "campaign_key": CAMPAIGN_KEY,
        "version": "1.0.0",
        "proof_profile": "bounded-navigation-v1",
        "profiles": [
            {
                "profile": item["profile"],
                "profile_digest": item["profile_digest"],
                "project_digest": item["project_digest"],
            }
            for item in profile_list
        ],
        "semantic_blocks": list(SEMANTIC_BLOCKS),
        "routes": [
            {
                key: item[key]
                for key in (
                    "route_id",
                    "source_profile_digest",
                    "target_profile_digest",
                    "source_project_digest",
                    "target_project_digest",
                )
            }
            for item in routes
        ],
        "corpus_ids": {kind: corpora[kind]["id"] for kind in CORPUS_KINDS},
    }
    scope_digest = canonical_digest(scope_value)
    formal_statuses = {item["formal_status"] for item in routes}
    native_route_count = sum(
        item["runtime_evidence_status"] == "BROWSER_PASSED" for item in routes
    )
    campaign = {
        "schema_version": 1,
        "campaign_key": CAMPAIGN_KEY,
        "version": "1.0.0",
        "proof_profile": "bounded-navigation-v1",
        "campaign_status": "LOCAL_EXECUTED",
        "certification_status": "NOT_CERTIFIED",
        "artifact_root": "formal-campaign",
        "profile_count": 9,
        "route_count": 72,
        "profiles": profile_list,
        "semantic_blocks": list(SEMANTIC_BLOCKS),
        "routes": routes,
        "artifacts": sorted(catalog.by_id.values(), key=lambda item: item["id"]),
        "engine_campaign_artifact_id": raw_campaign_id,
        "implementation": implementation,
        "toolchain_evidence": toolchain_evidence,
        "replay": replay,
        "corpora": corpora,
        "independent_verification": {
            "status": "NOT_RUN",
            "verifier": None,
            "artifact_ids": [],
        },
        "assumptions": assumptions,
        "unsupported_semantics": list(SEMANTIC_BLOCKS[1:]),
        "unconditional_proof": formal_statuses == {"PROVED"},
        "peer_binding": {
            "batch32_pack_key": CLIENT_KEY,
            "batch35_pack_key": VERIFICATION_KEY,
            "scope_digest": scope_digest,
        },
        "limitations": [
            "The local campaign covers the bounded-navigation-v1 proof profile only.",
            "Eleven required frontend semantic blocks remain explicit NOT_RUN.",
            (
                f"Real browser evidence is complete for {native_route_count}/72 routes; "
                "all remaining routes retain model-only behavior."
                if native_route_count
                else "Source and target behavior traces are model interpreters, not browser or device execution."
            ),
            "Independent external verification, holdout, representative workloads, and certification remain NOT_RUN.",
        ],
    }
    campaign_path = formal_root / "frontend-formal-route-campaign.json"
    write_json(campaign_path, campaign, canonical=True)
    return campaign_path


def build_common_campaign_v2(
    repo_root: Path,
    engine_root: Path,
    common_root: Path,
    toolchain_evidence_path: Path | None,
    external_evidence_path: Path | None = None,
    external_trust_store_path: Path | None = None,
    external_trust_root_path: Path | None = None,
) -> Path:
    if any(
        path is not None
        for path in (
            external_evidence_path,
            external_trust_store_path,
            external_trust_root_path,
        )
    ):
        raise RuntimeError("V2_EXTERNAL_POSITIVE_PROTOCOL_NOT_IMPLEMENTED")
    engine = verify_engine_campaign_v2(repo_root, engine_root)
    exact = exact_profiles(
        repo_root / "schemas/batch32/frontend-formal-route-campaign.schema.json"
    )
    profiles = {
        str(row["profile_id"]): row
        for row in engine.get("profiles", [])
        if isinstance(row, dict)
    }
    routes = {
        str(row["route_id"]): row
        for row in engine.get("routes", [])
        if isinstance(row, dict)
    }
    if set(profiles) != set(PROFILE_IDS) or len(engine.get("profiles", [])) != 9:
        raise RuntimeError("V2_ENGINE_PROFILE_CLOSURE_DRIFT")
    if set(routes) != expected_routes() or len(engine.get("routes", [])) != 72:
        raise RuntimeError("V2_ENGINE_ROUTE_CLOSURE_DRIFT")
    for profile_id, profile in profiles.items():
        expected = exact[profile_id]
        if (
            profile.get("framework_version") != expected["framework_version"]
            or profile.get("platforms") != expected["platforms"]
            or profile.get("required_runtime_channels")
            != list(REQUIRED_RUNTIME_CHANNELS_V2[profile_id])
        ):
            raise RuntimeError(f"V2_ENGINE_PROFILE_TUPLE_DRIFT:{profile_id}")
    scenario = engine.get("scenario_manifest")
    if not isinstance(scenario, dict):
        raise RuntimeError("V2_ENGINE_SCENARIO_MANIFEST_MISSING")
    scenario_ids = scenario.get("scenario_ids")
    if (
        not isinstance(scenario_ids, list)
        or len(scenario_ids) != 18
        or len(set(scenario_ids)) != len(scenario_ids)
        or scenario.get("scenario_count") != len(scenario_ids)
    ):
        raise RuntimeError("V2_ENGINE_SCENARIO_CLOSURE_DRIFT")
    scenario_inputs = load_scenario_inputs_v2(
        engine_root=engine_root,
        scenario_manifest=scenario,
        scenario_ids=scenario_ids,
    )
    for profile_id in PROFILE_IDS:
        validate_runtime_driver_contract_v2(
            profile_id=profile_id,
            profile=profiles[profile_id],
            scenario_ids=scenario_ids,
        )

    catalog = ArtifactCatalog(common_root)
    raw_ids, raw_campaign_id = copy_engine_output_v2(engine_root, common_root, catalog)
    scenario_id = raw_ids[str(scenario["source_path"])]
    if catalog.ref(scenario_id)["sha256"] != scenario.get(
        "source_sha256"
    ) or catalog.ref(scenario_id)["bytes"] != scenario.get("source_byte_count"):
        raise RuntimeError("V2_ENGINE_SCENARIO_BYTES_DRIFT")
    implementation = install_bundle_v2(
        repo_root=repo_root,
        pack_root=common_root,
        catalog=catalog,
        name="implementation",
        repository_paths=V2_IMPLEMENTATION_PATHS,
    )
    replay = install_bundle_v2(
        repo_root=repo_root,
        pack_root=common_root,
        catalog=catalog,
        name="replay",
        repository_paths=V2_REPLAY_PATHS,
    )
    replay["command"] = [
        "python3",
        "-B",
        "formal-campaign/replay/scripts/batch32/replay_frontend_formal_route_campaign_v2.py",
        ".",
        "--campaign",
        "formal-campaign/frontend-formal-route-campaign-v2.json",
        "--schema",
        "formal-campaign/replay/schemas/batch32/frontend-formal-route-campaign-v2.schema.json",
        "--route-schema",
        "formal-campaign/replay/schemas/batch32/frontend-formal-route-evidence-v2.schema.json",
        "--no-replay-execute",
        "--json",
    ]
    engine_verifier = capture_engine_verifier_v2(
        repo_root=repo_root,
        pack_root=common_root,
        catalog=catalog,
    )
    solver_binary = capture_solver_binary(
        engine_root=engine_root,
        pack_root=common_root,
        catalog=catalog,
        route_entries=routes,
        relative_path="formal-campaign/environment/z3",
    )
    corpora = add_corpora_v2(
        common_root,
        catalog,
        scenario_ids=scenario_ids,
    )
    toolchain, raw_toolchain, runtime_capture = add_toolchain_evidence_v2(
        repo_root=repo_root,
        engine_root=engine_root,
        pack_root=common_root,
        catalog=catalog,
        evidence_path=toolchain_evidence_path,
        scenario_digest=str(scenario["source_sha256"]),
        scenario_ids=scenario_ids,
        scenario_inputs=scenario_inputs,
        runtime_driver_contracts={
            profile_id: profiles[profile_id]["runtime_driver_contract"]
            for profile_id in PROFILE_IDS
        },
        profile_manifest_digests={
            profile_id: str(profiles[profile_id]["manifest_digest"])
            for profile_id in PROFILE_IDS
        },
    )
    runtime_projection = add_runtime_projection_policy_v2(common_root, catalog)
    runtime_projection["profile_channel_contracts"] = runtime_capture[
        "profile_channel_contracts"
    ]
    runtime_projection["contract_fingerprint"] = canonical_digest(
        runtime_projection["profile_channel_contracts"]
    )

    profile_records: dict[str, dict[str, Any]] = {}
    for profile_id in PROFILE_IDS:
        profile = profiles[profile_id]
        project_prefix = f"profiles/{profile_id}/project/"
        artifact_ids = sorted(
            identifier
            for relative, identifier in raw_ids.items()
            if relative.startswith(project_prefix)
            or relative
            in {str(profile["manifest_path"]), str(profile["source_fixture_path"])}
        )
        project_files = [
            {
                "relative_path": relative[len(project_prefix) :],
                "artifact_id": identifier,
            }
            for relative, identifier in sorted(raw_ids.items())
            if relative.startswith(project_prefix)
        ]
        if not project_files:
            raise RuntimeError(f"V2_PROFILE_PROJECT_FILES_MISSING:{profile_id}")
        profile_records[profile_id] = {
            "profile": exact[profile_id],
            "profile_digest": canonical_digest(exact[profile_id]),
            "project_digest": profile["project_digest"],
            "engine_profile_artifact_id": raw_ids[str(profile["manifest_path"])],
            "manifest_digest": profile["manifest_digest"],
            "source_fixture_digest": profile["source_fixture_digest"],
            "relift_model_digest": profile["relift_model_digest"],
            "relift_block_digests": profile["relift_block_digests"],
            "runtime_driver_contract": profile["runtime_driver_contract"],
            "runtime_driver_contract_digest": canonical_digest(
                profile["runtime_driver_contract"]
            ),
            "required_runtime_channels": list(REQUIRED_RUNTIME_CHANNELS_V2[profile_id]),
            "project_files": project_files,
            "artifact_ids": artifact_ids,
        }
    assumptions = engine.get("assumptions")
    if not isinstance(assumptions, list):
        raise RuntimeError("V2_ENGINE_ASSUMPTIONS_INVALID")
    mutation = engine.get("mutation_campaign")
    if not isinstance(mutation, dict) or not isinstance(mutation.get("digest"), str):
        raise RuntimeError("V2_ENGINE_MUTATION_LINK_MISSING")
    preliminary_scope_value = {
        "campaign_key": CAMPAIGN_KEY_V2,
        "version": "2.0.0",
        "proof_profile": "bounded-frontend-interaction-v1",
        "semantic_block_ids": list(SEMANTIC_BLOCKS),
        "block_symbol_map": BLOCK_SYMBOL_MAP_V2,
        "scenario_manifest_sha256": scenario["source_sha256"],
        "profiles": [
            {
                "profile": profile_records[profile_id]["profile"],
                "profile_digest": profile_records[profile_id]["profile_digest"],
                "project_digest": profile_records[profile_id]["project_digest"],
                "required_runtime_channels": profile_records[profile_id][
                    "required_runtime_channels"
                ],
                "runtime_driver_contract_digest": profile_records[profile_id][
                    "runtime_driver_contract_digest"
                ],
            }
            for profile_id in PROFILE_IDS
        ],
        "routes": [
            {
                "route_id": route_id,
                "source_profile_digest": profile_records[
                    str(routes[route_id]["source_profile"])
                ]["profile_digest"],
                "target_profile_digest": profile_records[
                    str(routes[route_id]["target_profile"])
                ]["profile_digest"],
                "source_project_digest": routes[route_id]["source_project_digest"],
                "target_project_digest": routes[route_id]["target_project_digest"],
            }
            for route_id in sorted(routes)
        ],
        "corpus_ids": {name: corpora[name]["id"] for name in CORPUS_KINDS},
        "runtime_profile_channel_contracts": runtime_projection[
            "profile_channel_contracts"
        ],
    }
    preliminary_scope_digest = canonical_digest(preliminary_scope_value)
    external_evidence, external_capture = add_external_evidence_v2(
        pack_root=common_root,
        catalog=catalog,
        evidence_path=external_evidence_path,
        trust_store_path=external_trust_store_path,
        trust_root_path=external_trust_root_path,
        scope_digest=preliminary_scope_digest,
    )
    route_records = [
        normalize_route_v2(
            engine_root=engine_root,
            pack_root=common_root,
            catalog=catalog,
            raw_ids=raw_ids,
            route=routes[route_id],
            profiles=profiles,
            profile_records=profile_records,
            scenario_ids=scenario_ids,
            scenario_digest=str(scenario["source_sha256"]),
            implementation=implementation,
            replay=replay,
            corpora=corpora,
            assumptions=assumptions,
            mutation_digest=str(mutation["digest"]),
            toolchain_artifact_id=toolchain["artifact_id"],
            toolchain_producer_fingerprint=toolchain["producer_fingerprint"],
            solver_binary=solver_binary,
            runtime_capture=runtime_capture,
            runtime_projection=runtime_projection,
            external_capture=external_capture,
        )
        for route_id in sorted(routes)
    ]
    gap_id = add_gap_inventory_v2(
        common_root,
        catalog,
        route_records=route_records,
        runtime_capture=runtime_capture,
    )
    oracle = add_oracle_graph_v2(
        common_root,
        catalog,
        implementation_fingerprint=implementation["fingerprint"],
        external_capture=external_capture,
    )
    profile_list = [profile_records[profile_id] for profile_id in PROFILE_IDS]
    scope_value = {
        "campaign_key": CAMPAIGN_KEY_V2,
        "version": "2.0.0",
        "proof_profile": "bounded-frontend-interaction-v1",
        "semantic_block_ids": list(SEMANTIC_BLOCKS),
        "block_symbol_map": BLOCK_SYMBOL_MAP_V2,
        "scenario_manifest_sha256": scenario["source_sha256"],
        "profiles": [
            {
                "profile": row["profile"],
                "profile_digest": row["profile_digest"],
                "project_digest": row["project_digest"],
                "required_runtime_channels": row["required_runtime_channels"],
                "runtime_driver_contract_digest": row[
                    "runtime_driver_contract_digest"
                ],
            }
            for row in profile_list
        ],
        "routes": [
            {
                key: row[key]
                for key in (
                    "route_id",
                    "source_profile_digest",
                    "target_profile_digest",
                    "source_project_digest",
                    "target_project_digest",
                )
            }
            for row in route_records
        ],
        "corpus_ids": {name: corpora[name]["id"] for name in CORPUS_KINDS},
        "runtime_profile_channel_contracts": runtime_projection[
            "profile_channel_contracts"
        ],
    }
    scope_digest = canonical_digest(scope_value)
    if scope_digest != preliminary_scope_digest:
        raise RuntimeError("V2_EXTERNAL_SCOPE_PRECOMPUTATION_DRIFT")
    channel_statuses = runtime_capture["profile_channel_statuses"]
    arbitrary_customer_source = str(
        engine.get("arbitrary_customer_source", "NOT_PROVED")
    )
    unsupported_semantics = unsupported_semantics_v2(
        arbitrary_customer_source=arbitrary_customer_source,
        profile_channel_statuses=channel_statuses,
        independent_status=str(external_evidence["independent_status"]),
    )
    del raw_toolchain
    campaign = {
        "schema_version": 2,
        "kind": "frontend-formal-route-campaign-v2",
        "campaign_key": CAMPAIGN_KEY_V2,
        "version": "2.0.0",
        "proof_profile": "bounded-frontend-interaction-v1",
        "campaign_status": "LOCAL_EXECUTED",
        "certification_status": "NOT_CERTIFIED",
        "artifact_root": "formal-campaign",
        "profile_count": 9,
        "route_count": 72,
        "block_count": 12,
        "route_block_count": 864,
        "semantic_block_ids": list(SEMANTIC_BLOCKS),
        "block_symbol_map": BLOCK_SYMBOL_MAP_V2,
        "scenario_manifest": {
            "artifact_id": scenario_id,
            "sha256": catalog.ref(scenario_id)["sha256"],
            "bytes": catalog.ref(scenario_id)["bytes"],
            "scenario_ids": scenario_ids,
            "scenario_count": len(scenario_ids),
            "input_schema": scenario["input_schema"],
        },
        "profiles": profile_list,
        "routes": route_records,
        "artifacts": sorted(catalog.by_id.values(), key=lambda row: row["id"]),
        "engine_campaign_artifact_id": raw_campaign_id,
        "engine_artifact_ids": sorted(raw_ids.values()),
        "engine_verifier": engine_verifier,
        "gap_inventory_artifact_id": gap_id,
        "implementation": implementation,
        "toolchain_evidence": toolchain,
        "replay": replay,
        "corpora": corpora,
        "oracle_provenance": oracle,
        "runtime_projection": {
            "artifact_id": runtime_projection["artifact_id"],
            "fingerprint": runtime_projection["fingerprint"],
            "profile_channel_contracts": runtime_projection[
                "profile_channel_contracts"
            ],
            "contract_fingerprint": runtime_projection[
                "contract_fingerprint"
            ],
        },
        "external_evidence": external_evidence,
        "assumptions": assumptions,
        "unsupported_semantics": unsupported_semantics,
        "unconditional_proof": (
            engine.get("unconditional_proof") is True
            and not assumptions
            and not unsupported_semantics
            and all(
                row.get("model_formal_status") == "PASSED"
                for row in route_records
            )
        ),
        "peer_binding": {
            "batch32_pack_key": CLIENT_KEY_V2,
            "batch35_pack_key": VERIFICATION_KEY_V2,
            "scope_digest": scope_digest,
        },
        "limitations": [
            (
                "All 864 semantic blocks have bounded assumption-free solver "
                "claims; this remains bounded-profile evidence."
                if engine.get("unconditional_proof") is True
                else (
                    "All 864 semantic blocks have bounded same-engine model/formal "
                    "evidence under assumptions."
                )
            ),
            "No model output is counted as browser or native runtime evidence.",
            (
                "Runtime readiness is derived only from packed actual observations "
                "and exact channel-specific canonical projections."
            ),
            (
                "Independent, holdout, representative/customer and certification "
                "states are derived separately from strict external evidence."
            ),
        ],
    }
    campaign_path = (
        common_root / "formal-campaign/frontend-formal-route-campaign-v2.json"
    )
    write_json(campaign_path, campaign, canonical=True)
    return campaign_path


def client_tuple(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "stack": profile["id"],
        "versions": [profile["framework_version"]],
        "language": profile["language"],
        "language_versions": [profile["language_version"]],
        "runtime": profile["runtime"],
        "runtime_versions": [profile["runtime_version"]],
        "build_tool": f"{profile['build_tool']} {profile['build_tool_version']}",
        "package_manager": f"{profile['package_manager']} {profile['package_manager_version']}",
        "router": [profile["router"]],
        "renderer": [profile["rendering"]],
        "state": [profile["state"]],
        "forms": ["formal-campaign-NOT_RUN"],
        "styling": ["formal-campaign-NOT_RUN"],
        "design_system": ["formal-campaign-NOT_RUN"],
        "api_client": ["formal-campaign-NOT_RUN"],
        "identity": ["metadata-only-NOT_RUN"],
        "i18n": ["formal-campaign-NOT_RUN"],
        "test_tools": [profile["test_tool"]],
        "browsers": ["browser-execution-NOT_RUN"],
        "devices": [item for item in profile["platforms"] if item != "WEB"],
    }


def complete_client_pack(
    repo_root: Path,
    pack: Path,
    campaign_path: Path,
    scope_digest: str,
    profiles: dict[str, dict[str, Any]],
) -> None:
    campaign_relative = "formal-campaign/frontend-formal-route-campaign.json"
    campaign_sha = digest_bytes(campaign_path.read_bytes())
    manifest = load_json(pack / "pack.json")
    manifest.update(
        {
            "version": "1.0.0",
            "mode": "assessment",
            "status": "experimental",
            "owner": "frontend-client-platform-team",
            "maintenance_owner": "frontend-client-platform-team",
            "ux_owner": "frontend-experience-team",
            "accessibility_owner": "accessibility-team",
            "source": client_tuple(profiles["angular"]),
            "target": client_tuple(profiles["flutter"]),
            "scope": {
                "journeys": ["bounded-navigation-v1-model"],
                "routes": sorted(expected_routes()),
                "component_roots": ["exact-nine-profile-generated-projects"],
                "excluded": list(SEMANTIC_BLOCKS[1:])
                + ["browser-device-native-execution", "external-certification"],
            },
            "frontend_formal_route_campaign": campaign_relative,
            "frontend_formal_campaign_digest": campaign_sha,
            "frontend_formal_scope_digest": scope_digest,
            "frontend_formal_peer": {
                "pack_key": VERIFICATION_KEY,
                "campaign_sha256": campaign_sha,
                "scope_digest": scope_digest,
            },
        }
    )
    write_json(pack / "pack.json", manifest)
    support = load_json(pack / "support-matrix.json")
    for capability in support.get("capabilities", []):
        capability.update(
            {
                "status": "experimental",
                "owner": "frontend-client-platform-team",
                "evidence_refs": [campaign_relative],
                "reason": "Bounded local model/formal evidence only; certification remains NOT_CERTIFIED.",
            }
        )
    write_json(pack / "support-matrix.json", support)
    route_matrix = {
        "schema_version": 1,
        "pack_key": CLIENT_KEY,
        "tuples": [
            {
                "source_stack": route.split("--to--", 1)[0],
                "source_version": profiles[route.split("--to--", 1)[0]][
                    "framework_version"
                ],
                "target_stack": route.split("--to--", 1)[1],
                "target_version": profiles[route.split("--to--", 1)[1]][
                    "framework_version"
                ],
                "status": "experimental",
                "evidence_refs": [campaign_relative],
            }
            for route in sorted(expected_routes())
        ],
        "recertification_triggers": [
            "profile tuple drift",
            "implementation fingerprint drift",
            "replay fingerprint drift",
            "corpus or oracle drift",
        ],
    }
    write_json(pack / "route-matrix.json", route_matrix)
    fingerprint = load_json(pack / "source-fingerprint/fingerprint.json")
    fingerprint.update(
        {
            "snapshot_digest": scope_digest,
            "coverage": 1.0,
            "source_tuple": manifest["source"],
        }
    )
    write_json(pack / "source-fingerprint/fingerprint.json", fingerprint)
    ir = load_json(pack / "ui-ir/model.json")
    ir["source_snapshot_digest"] = scope_digest
    write_json(pack / "ui-ir/model.json", ir)
    target_profile = load_json(pack / "target-profile/profile.json")
    target_profile["owner"] = "frontend-client-platform-team"
    write_json(pack / "target-profile/profile.json", target_profile)
    acceptance = load_json(pack / "acceptance/acceptance-profile.json")
    acceptance["owner"] = "frontend-quality-team"
    write_json(pack / "acceptance/acceptance-profile.json", acceptance)
    target = load_json(pack / "target-profile/profile.json")
    flutter = profiles["flutter"]
    target.update(
        {
            "owner": "frontend-client-platform-team",
            "router": [flutter["router"]],
            "rendering_strategy": {"mode": flutter["rendering"]},
            "state_strategy": {"provider": flutter["state"]},
            "form_strategy": {"provider": "NOT_RUN"},
            "styling_strategy": {"mode": "NOT_RUN"},
            "design_system_strategy": {"mode": "NOT_RUN"},
            "api_client_strategy": {"provider": "NOT_RUN"},
            "auth_strategy": {"mode": "metadata-only-NOT_RUN"},
            "i18n_strategy": {"provider": "NOT_RUN"},
            "accessibility_profile": {"standard": "model-only-NOT_RUN"},
            "browser_matrix": ["browser-execution-NOT_RUN"],
            "device_profiles": ["ANDROID-NOT_RUN", "IOS-NOT_RUN"],
            "test_profiles": [flutter["test_tool"]],
            "provision": {"commands": ["NOT_RUN"]},
            "health_check": {"commands": ["NOT_RUN"]},
            "security": {"status": "NOT_RUN"},
            "lifecycle": {"policy": "recertify-on-profile-drift"},
        }
    )
    write_json(pack / "target-profile/profile.json", target)
    acceptance = load_json(pack / "acceptance/acceptance-profile.json")
    acceptance.update(
        {
            "owner": "frontend-quality-team",
            "browser_matrix": ["browser-execution-NOT_RUN"],
            "device_matrix": ["ANDROID-NOT_RUN", "IOS-NOT_RUN", "HARMONYOS-NOT_RUN"],
            "accessibility": {"standard": "NOT_RUN", "critical_violations": 0},
        }
    )
    write_json(pack / "acceptance/acceptance-profile.json", acceptance)
    evidence = load_json(pack / "certification/evidence.json")
    evidence["evidence_refs"] = [campaign_relative]
    write_json(pack / "certification/evidence.json", evidence)
    certification = load_json(pack / "certification/certification.json")
    certification.update(
        {
            "status": "experimental",
            "owner": "frontend-quality-team",
            "exact_tuple": {"source": manifest["source"], "target": manifest["target"]},
            "evidence_refs": [campaign_relative],
            "limitations": [
                "Bounded navigation model/formal evidence is not native runtime evidence.",
                "Certification remains NOT_CERTIFIED.",
            ],
        }
    )
    write_json(pack / "certification/certification.json", certification)


def complete_verification_pack(
    pack: Path,
    campaign_path: Path,
    scope_digest: str,
    implementation_fingerprint: str,
) -> None:
    campaign_relative = "formal-campaign/frontend-formal-route-campaign.json"
    campaign_sha = digest_bytes(campaign_path.read_bytes())
    manifest = load_json(pack / "pack.json")
    manifest.update(
        {
            "version": "1.0.0",
            "status": "experimental",
            "owner": "frontend-formal-verification-team",
            "maintenance_owner": "frontend-client-platform-team",
            "scope": {
                "migration_route": "all-directed-pairs-nine-exact-frontend-profiles",
                "source_artifact_digest": scope_digest,
                "target_artifact_digest": scope_digest,
                "workload_key": "bounded-navigation-v1",
                "risk_tier": "P0",
                "environment_digest": implementation_fingerprint,
            },
            "frontend_formal_route_campaign": campaign_relative,
            "frontend_formal_campaign_digest": campaign_sha,
            "frontend_formal_scope_digest": scope_digest,
            "frontend_formal_peer": {
                "pack_key": CLIENT_KEY,
                "campaign_sha256": campaign_sha,
                "scope_digest": scope_digest,
            },
        }
    )
    write_json(pack / "pack.json", manifest)
    certification = load_json(pack / "certification/certification.json")
    certification.update(
        {
            "status": "experimental",
            "owner": "frontend-formal-verification-team",
            "exact_scope": manifest["scope"],
            "evidence_refs": [campaign_relative],
            "limitations": [
                "The solver result is proof under assumptions for bounded-navigation-v1.",
                "Native, holdout, representative, independent external, and certification evidence remain NOT_RUN.",
            ],
        }
    )
    write_json(pack / "certification/certification.json", certification)
    evidence = load_json(pack / "certification/evidence.json")
    evidence["evidence_refs"] = [campaign_relative]
    write_json(pack / "certification/evidence.json", evidence)


def complete_client_pack_v2(
    pack: Path,
    campaign_path: Path,
    scope_digest: str,
    profiles: dict[str, dict[str, Any]],
) -> None:
    campaign_relative = "formal-campaign/frontend-formal-route-campaign-v2.json"
    campaign_sha = digest_bytes(campaign_path.read_bytes())
    campaign = load_json(campaign_path)
    runtime_status = campaign.get("toolchain_evidence", {}).get(
        "runtime_status", "NOT_RUN"
    )
    manifest = load_json(pack / "pack.json")
    manifest.update(
        {
            "version": "2.0.0",
            "mode": "assessment",
            "status": "experimental",
            "owner": "frontend-client-platform-team",
            "maintenance_owner": "frontend-client-platform-team",
            "ux_owner": "frontend-experience-team",
            "accessibility_owner": "accessibility-team",
            "source": client_tuple(profiles["angular"]),
            "target": client_tuple(profiles["flutter"]),
            "scope": {
                "journeys": ["bounded-frontend-interaction-v1-model"],
                "routes": sorted(expected_routes()),
                "component_roots": ["exact-nine-profile-generated-projects"],
                "excluded": [
                    "arbitrary-customer-source",
                    "independent-holdout",
                    "representative-customer-workloads",
                    "certification",
                ]
                + (["incomplete-actual-runtime-matrix"] if runtime_status != "PASSED" else []),
            },
            "frontend_formal_route_campaign_v2": campaign_relative,
            "frontend_formal_campaign_v2_digest": campaign_sha,
            "frontend_formal_scope_v2_digest": scope_digest,
            "frontend_formal_peer_v2": {
                "pack_key": VERIFICATION_KEY_V2,
                "campaign_sha256": campaign_sha,
                "scope_digest": scope_digest,
            },
        }
    )
    write_json(pack / "pack.json", manifest)
    support = load_json(pack / "support-matrix.json")
    for capability in support.get("capabilities", []):
        capability.update(
            {
                "status": "experimental",
                "owner": "frontend-client-platform-team",
                "evidence_refs": [campaign_relative],
                "reason": (
                    "Bounded proof remains under assumptions; runtime status is "
                    f"{runtime_status} and independent/customer certification evidence remains fail-closed."
                ),
            }
        )
    write_json(pack / "support-matrix.json", support)
    route_matrix = {
        "schema_version": 1,
        "pack_key": CLIENT_KEY_V2,
        "tuples": [
            {
                "source_stack": route_id.split("--to--", 1)[0],
                "source_version": profiles[route_id.split("--to--", 1)[0]][
                    "framework_version"
                ],
                "target_stack": route_id.split("--to--", 1)[1],
                "target_version": profiles[route_id.split("--to--", 1)[1]][
                    "framework_version"
                ],
                "status": "experimental",
                "evidence_refs": [campaign_relative],
            }
            for route_id in sorted(expected_routes())
        ],
        "recertification_triggers": [
            "engine or generator implementation drift",
            "scenario/block/profile/route closure drift",
            "toolchain producer or runtime evidence drift",
            "solver, replay, oracle or corpus drift",
        ],
    }
    write_json(pack / "route-matrix.json", route_matrix)
    fingerprint = load_json(pack / "source-fingerprint/fingerprint.json")
    fingerprint.update(
        {
            "snapshot_digest": scope_digest,
            "coverage": 1.0,
            "source_tuple": manifest["source"],
        }
    )
    write_json(pack / "source-fingerprint/fingerprint.json", fingerprint)
    ir = load_json(pack / "ui-ir/model.json")
    ir["source_snapshot_digest"] = scope_digest
    write_json(pack / "ui-ir/model.json", ir)
    target_profile = load_json(pack / "target-profile/profile.json")
    target_profile["owner"] = "frontend-client-platform-team"
    write_json(pack / "target-profile/profile.json", target_profile)
    acceptance_profile = load_json(pack / "acceptance/acceptance-profile.json")
    acceptance_profile["owner"] = "frontend-quality-team"
    write_json(pack / "acceptance/acceptance-profile.json", acceptance_profile)
    evidence = load_json(pack / "certification/evidence.json")
    evidence["evidence_refs"] = [campaign_relative, "certification/gap-inventory.md"]
    write_json(pack / "certification/evidence.json", evidence)
    certification = load_json(pack / "certification/certification.json")
    certification.update(
        {
            "status": "experimental",
            "owner": "frontend-quality-team",
            "exact_tuple": {"source": manifest["source"], "target": manifest["target"]},
            "evidence_refs": [
                campaign_relative,
                "certification/gap-inventory.md",
            ],
            "limitations": [
                "Model/formal, browser, native and independent readiness are separate.",
                f"Packed actual runtime aggregate is {runtime_status}; certification is NOT_CERTIFIED.",
            ],
        }
    )
    write_json(pack / "certification/certification.json", certification)


def complete_verification_pack_v2(
    pack: Path,
    campaign_path: Path,
    scope_digest: str,
    implementation_fingerprint: str,
) -> None:
    campaign_relative = "formal-campaign/frontend-formal-route-campaign-v2.json"
    campaign_sha = digest_bytes(campaign_path.read_bytes())
    campaign = load_json(campaign_path)
    runtime_status = campaign.get("toolchain_evidence", {}).get(
        "runtime_status", "NOT_RUN"
    )
    external_status = campaign.get("external_evidence", {}).get(
        "status", "NOT_RUN"
    )
    external_passed = external_status == "PASSED"
    external_limitation = (
        "Scoped independent runtime, holdout, representative and customer "
        "evidence passed the external trust protocol; unconditional proof, "
        "complete browser/native production coverage and certification remain open."
        if external_passed
        else "Independent runtime, holdout, representative and customer evidence is NOT_RUN."
    )
    external_risk = (
        {
            "risk_id": "frontend-v2-production-certification-incomplete",
            "description": (
                "Scoped external qualification does not establish unconditional "
                "proof, complete browser/native production coverage or certification."
            ),
            "severity": "critical",
            "mitigation": (
                "Close unconditional formal, required runtime, operational and "
                "certification gates."
            ),
            "owner": "frontend-formal-verification-team",
            "status": "open",
        }
        if external_passed
        else {
            "risk_id": "frontend-v2-external-evidence-not-run",
            "description": "External runtime and customer qualification is absent.",
            "severity": "critical",
            "mitigation": "Run the externally trusted intake and replay protocol.",
            "owner": "frontend-formal-verification-team",
            "status": "open",
        }
    )
    oracle_registry = {
        "schema_version": 1,
        "pack_key": VERIFICATION_KEY_V2,
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
    write_json(pack / "oracle-registry.json", oracle_registry)
    assurance = load_json(pack / "assurance/assurance-case.json")
    assurance.update(
        {
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
                    "limitations": [external_limitation],
                }
            ],
            "evidence": [],
            "residual_risks": [external_risk],
            "monitoring_obligations": [],
            "approvals": [],
        }
    )
    write_json(pack / "assurance/assurance-case.json", assurance)
    manifest = load_json(pack / "pack.json")
    manifest.update(
        {
            "version": "2.0.0",
            "status": "experimental",
            "owner": "frontend-formal-verification-team",
            "maintenance_owner": "frontend-client-platform-team",
            "scope": {
                "migration_route": "all-directed-pairs-nine-exact-frontend-profiles-12-blocks",
                "source_artifact_digest": scope_digest,
                "target_artifact_digest": scope_digest,
                "workload_key": "bounded-frontend-interaction-v1",
                "risk_tier": "P0",
                "environment_digest": implementation_fingerprint,
            },
            "frontend_formal_route_campaign_v2": campaign_relative,
            "frontend_formal_campaign_v2_digest": campaign_sha,
            "frontend_formal_scope_v2_digest": scope_digest,
            "frontend_formal_peer_v2": {
                "pack_key": CLIENT_KEY_V2,
                "campaign_sha256": campaign_sha,
                "scope_digest": scope_digest,
            },
            "frontend_governance_v2": {
                "oracle_registry_sha256": digest_bytes(
                    (pack / "oracle-registry.json").read_bytes()
                ),
                "assurance_case_sha256": digest_bytes(
                    (pack / "assurance/assurance-case.json").read_bytes()
                ),
                "status": "NOT_RUN" if external_status != "PASSED" else "PASSED",
            },
        }
    )
    write_json(pack / "pack.json", manifest)
    certification = load_json(pack / "certification/certification.json")
    certification.update(
        {
            "status": "experimental",
            "owner": "frontend-formal-verification-team",
            "exact_scope": manifest["scope"],
            "evidence_refs": [
                campaign_relative,
                "certification/gap-inventory.md",
            ],
            "limitations": [
                "All 864 blocks have bounded proof under assumptions from one engine.",
                f"Packed actual runtime aggregate is {runtime_status}.",
                (
                    "Independent holdout, representative/customer and certification "
                    "evidence remain NOT_RUN without strict external intake."
                ),
            ],
        }
    )
    write_json(pack / "certification/certification.json", certification)
    evidence = load_json(pack / "certification/evidence.json")
    evidence["evidence_refs"] = [campaign_relative, "certification/gap-inventory.md"]
    write_json(pack / "certification/evidence.json", evidence)


def run_checked(
    command: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> None:
    completed = subprocess.run(
        command, cwd=cwd, env=env, text=True, capture_output=True, check=False
    )
    if completed.returncode:
        raise RuntimeError(
            "COMMAND_FAILED:\n"
            + " ".join(command)
            + "\nSTDOUT:\n"
            + completed.stdout
            + "\nSTDERR:\n"
            + completed.stderr
        )


def build_packs(
    repo_root: Path,
    engine_root: Path,
    staging_root: Path,
    toolchain_evidence_path: Path | None = None,
) -> tuple[Path, Path]:
    common_root = staging_root / "common"
    common_root.mkdir(parents=True)
    common_campaign = build_common_campaign(
        repo_root,
        engine_root,
        common_root,
        toolchain_evidence_path=toolchain_evidence_path,
    )
    campaign = load_json(common_campaign)
    scope_digest = campaign["peer_binding"]["scope_digest"]
    implementation_fingerprint = campaign["implementation"]["fingerprint"]
    profiles = exact_profiles(
        repo_root / "schemas/batch32/frontend-formal-route-campaign.schema.json"
    )

    run_checked(
        [
            sys.executable,
            str(repo_root / "scripts/batch32/scaffold_client_pack.py"),
            "--source-stack",
            "angular",
            "--target-stack",
            "flutter",
            "--source-version",
            profiles["angular"]["framework_version"],
            "--target-version",
            profiles["flutter"]["framework_version"],
            "--source-language",
            profiles["angular"]["language"],
            "--target-language",
            profiles["flutter"]["language"],
            "--source-language-version",
            profiles["angular"]["language_version"],
            "--target-language-version",
            profiles["flutter"]["language_version"],
            "--source-runtime",
            profiles["angular"]["runtime"],
            "--target-runtime",
            profiles["flutter"]["runtime"],
            "--source-runtime-version",
            profiles["angular"]["runtime_version"],
            "--target-runtime-version",
            profiles["flutter"]["runtime_version"],
            "--source-build-tool",
            profiles["angular"]["build_tool"],
            "--target-build-tool",
            profiles["flutter"]["build_tool"],
            "--source-package-manager",
            profiles["angular"]["package_manager"],
            "--target-package-manager",
            profiles["flutter"]["package_manager"],
            "--pack-key",
            CLIENT_KEY,
            "--repo-root",
            str(staging_root),
        ],
        cwd=repo_root,
    )
    client_pack = staging_root / "client-packs" / CLIENT_KEY
    shutil.copytree(common_root / "formal-campaign", client_pack / "formal-campaign")
    complete_client_pack(
        repo_root,
        client_pack,
        client_pack / "formal-campaign/frontend-formal-route-campaign.json",
        scope_digest,
        profiles,
    )

    run_checked(
        [
            sys.executable,
            str(repo_root / "scripts/batch35/scaffold_verification_pack.py"),
            "--pack-key",
            VERIFICATION_KEY,
            "--migration-route",
            "all-directed-pairs-nine-exact-frontend-profiles",
            "--workload-key",
            "bounded-navigation-v1",
            "--source-digest",
            scope_digest,
            "--target-digest",
            scope_digest,
            "--environment-digest",
            implementation_fingerprint,
            "--repo-root",
            str(staging_root),
        ],
        cwd=repo_root,
    )
    verification_pack = staging_root / "verification-packs" / VERIFICATION_KEY
    shutil.copytree(
        common_root / "formal-campaign", verification_pack / "formal-campaign"
    )
    complete_verification_pack(
        verification_pack,
        verification_pack / "formal-campaign/frontend-formal-route-campaign.json",
        scope_digest,
        implementation_fingerprint,
    )

    commands = [
        [
            sys.executable,
            str(repo_root / "scripts/batch32/validate_client_pack.py"),
            str(client_pack),
        ],
        [
            sys.executable,
            str(
                repo_root / "scripts/batch32/validate_frontend_formal_route_campaign.py"
            ),
            str(client_pack),
        ],
        [
            sys.executable,
            str(repo_root / "scripts/batch32/run_client_gate.py"),
            str(client_pack),
        ],
        [
            sys.executable,
            str(repo_root / "scripts/batch35/validate_verification_pack.py"),
            str(verification_pack),
        ],
        [
            sys.executable,
            str(
                repo_root / "scripts/batch35/validate_frontend_formal_route_campaign.py"
            ),
            str(verification_pack),
        ],
        [
            sys.executable,
            str(repo_root / "scripts/batch35/run_verification_gate.py"),
            str(verification_pack),
        ],
    ]
    for command in commands:
        run_checked(command, cwd=repo_root)
    for pack in (client_pack, verification_pack):
        gate = load_json(pack / "certification/gate-result.json")
        structural_ok = (
            gate.get("structural_status") == "PASSED"
            or gate.get("structural_gate_status") in ("passed", "PASSED")
            or gate.get("status") in ("passed", "PASSED")
        )
        if (
            not structural_ok
            or gate.get("certification_decision") != "NOT_CERTIFIED"
        ):
            raise RuntimeError(f"GATE_BOUNDARY_DRIFT:{pack}")
    return client_pack, verification_pack


def build_packs_v2(
    repo_root: Path,
    engine_root: Path,
    staging_root: Path,
    toolchain_evidence_path: Path,
    external_evidence_path: Path | None = None,
    external_trust_store_path: Path | None = None,
    external_trust_root_path: Path | None = None,
) -> tuple[Path, Path]:
    if any(
        path is not None
        for path in (
            external_evidence_path,
            external_trust_store_path,
            external_trust_root_path,
        )
    ):
        raise RuntimeError("V2_EXTERNAL_POSITIVE_PROTOCOL_NOT_IMPLEMENTED")
    common_root = staging_root / "common-v2"
    common_root.mkdir(parents=True)
    common_campaign = build_common_campaign_v2(
        repo_root,
        engine_root,
        common_root,
        toolchain_evidence_path,
        external_evidence_path,
        external_trust_store_path,
        external_trust_root_path,
    )
    campaign = load_json(common_campaign)
    scope_digest = campaign["peer_binding"]["scope_digest"]
    implementation_fingerprint = campaign["implementation"]["fingerprint"]
    profiles = exact_profiles(
        repo_root / "schemas/batch32/frontend-formal-route-campaign.schema.json"
    )
    run_checked(
        [
            sys.executable,
            str(repo_root / "scripts/batch32/scaffold_client_pack.py"),
            "--source-stack",
            "angular",
            "--target-stack",
            "flutter",
            "--source-version",
            profiles["angular"]["framework_version"],
            "--target-version",
            profiles["flutter"]["framework_version"],
            "--source-language",
            profiles["angular"]["language"],
            "--target-language",
            profiles["flutter"]["language"],
            "--source-language-version",
            profiles["angular"]["language_version"],
            "--target-language-version",
            profiles["flutter"]["language_version"],
            "--source-runtime",
            profiles["angular"]["runtime"],
            "--target-runtime",
            profiles["flutter"]["runtime"],
            "--source-runtime-version",
            profiles["angular"]["runtime_version"],
            "--target-runtime-version",
            profiles["flutter"]["runtime_version"],
            "--source-build-tool",
            profiles["angular"]["build_tool"],
            "--target-build-tool",
            profiles["flutter"]["build_tool"],
            "--source-package-manager",
            profiles["angular"]["package_manager"],
            "--target-package-manager",
            profiles["flutter"]["package_manager"],
            "--pack-key",
            CLIENT_KEY_V2,
            "--repo-root",
            str(staging_root),
        ],
        cwd=repo_root,
    )
    client_pack = staging_root / "client-packs" / CLIENT_KEY_V2
    shutil.copytree(common_root / "formal-campaign", client_pack / "formal-campaign")
    shutil.copy2(
        common_root / "certification/gap-inventory.md",
        client_pack / "certification/gap-inventory.md",
    )
    complete_client_pack_v2(
        client_pack,
        client_pack / "formal-campaign/frontend-formal-route-campaign-v2.json",
        scope_digest,
        profiles,
    )

    run_checked(
        [
            sys.executable,
            str(repo_root / "scripts/batch35/scaffold_verification_pack.py"),
            "--pack-key",
            VERIFICATION_KEY_V2,
            "--migration-route",
            "all-directed-pairs-nine-exact-frontend-profiles-12-blocks",
            "--workload-key",
            "bounded-frontend-interaction-v1",
            "--source-digest",
            scope_digest,
            "--target-digest",
            scope_digest,
            "--environment-digest",
            implementation_fingerprint,
            "--repo-root",
            str(staging_root),
        ],
        cwd=repo_root,
    )
    verification_pack = staging_root / "verification-packs" / VERIFICATION_KEY_V2
    shutil.copytree(
        common_root / "formal-campaign",
        verification_pack / "formal-campaign",
    )
    shutil.copy2(
        common_root / "certification/gap-inventory.md",
        verification_pack / "certification/gap-inventory.md",
    )
    complete_verification_pack_v2(
        verification_pack,
        verification_pack / "formal-campaign/frontend-formal-route-campaign-v2.json",
        scope_digest,
        implementation_fingerprint,
    )
    commands = [
        [
            sys.executable,
            str(repo_root / "scripts/batch32/validate_client_pack.py"),
            str(client_pack),
        ],
        [
            sys.executable,
            str(
                repo_root
                / "scripts/batch32/validate_frontend_formal_route_campaign_v2.py"
            ),
            str(client_pack),
        ],
        [
            sys.executable,
            str(repo_root / "scripts/batch32/run_client_gate.py"),
            str(client_pack),
        ],
        [
            sys.executable,
            str(repo_root / "scripts/batch35/validate_verification_pack.py"),
            str(verification_pack),
        ],
        [
            sys.executable,
            str(
                repo_root
                / "scripts/batch35/validate_frontend_formal_route_campaign_v2.py"
            ),
            str(verification_pack),
        ],
        [
            sys.executable,
            str(repo_root / "scripts/batch35/run_verification_gate.py"),
            str(verification_pack),
        ],
    ]
    validation_env = dict(os.environ)
    if external_trust_root_path is not None:
        validation_env["ELMOS_FRONTEND_EXTERNAL_TRUST_ROOT"] = str(
            external_trust_root_path.resolve(strict=True)
        )
    for command in commands:
        run_checked(command, cwd=repo_root, env=validation_env)
    expected_formal_ready = (
        campaign.get("unconditional_proof") is True
        and not campaign.get("assumptions")
        and not campaign.get("unsupported_semantics")
    )
    client_gate = load_json(client_pack / "certification/gate-result.json")
    if (
        client_gate.get("structural_status") != "PASSED"
        or client_gate.get("model_formal_ready") is not True
        or client_gate.get("formal_ready") is not expected_formal_ready
        or client_gate.get("certification_ready") is not False
        or client_gate.get("certification_decision") != "NOT_CERTIFIED"
    ):
        raise RuntimeError(f"V2_GATE_BOUNDARY_DRIFT:{client_pack}")

    verification_gate = load_json(verification_pack / "certification/gate-result.json")
    verif_structural_ok = (
        verification_gate.get("structural_status") == "PASSED"
        or verification_gate.get("structural_gate_status") in ("passed", "PASSED")
        or verification_gate.get("status") in ("passed", "PASSED")
    )
    if (
        not verif_structural_ok
        or verification_gate.get("certification_decision") != "NOT_CERTIFIED"
    ):
        raise RuntimeError(f"V2_GATE_BOUNDARY_DRIFT:{verification_pack}")
    return client_pack, verification_pack


def publish_pair(
    pairs: list[tuple[Path, Path]], *, staging_root: Path, force: bool
) -> None:
    if not force:
        existing = [str(target) for _, target in pairs if target.exists()]
        if existing:
            raise RuntimeError(f"OUTPUT_EXISTS_USE_FORCE:{existing}")
    backup_root = staging_root / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backups: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for _, target in pairs:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                backup = backup_root / target.name
                os.replace(target, backup)
                backups.append((backup, target))
        for source, target in pairs:
            os.replace(source, target)
            published.append(target)
    except Exception:
        for target in reversed(published):
            if target.exists():
                os.replace(target, staging_root / f"failed-{target.name}")
        for backup, target in reversed(backups):
            if backup.exists():
                os.replace(backup, target)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--engine-cli")
    parser.add_argument("--engine-output", type=Path)
    parser.add_argument(
        "--contract-version",
        choices=("auto", "1", "2"),
        default="auto",
        help="preserve v1 by default; auto detects a supplied engine output",
    )
    parser.add_argument(
        "--external-evidence",
        type=Path,
        help="optional exact independently produced v2 evidence intake",
    )
    parser.add_argument(
        "--external-trust-store",
        type=Path,
        help="independent Ed25519 trust store required with --external-evidence",
    )
    parser.add_argument(
        "--external-trust-root",
        type=Path,
        help=(
            "operator-configured trust anchor kept outside the pack; required "
            "with independently supplied v2 evidence"
        ),
    )
    parser.add_argument(
        "--toolchain-evidence",
        type=Path,
        help=(
            "exact output of tooling/run_frontend_formal_toolchains.py; when "
            "omitted, the campaign records build/browser evidence as NOT_RUN"
        ),
    )
    parser.add_argument("--node", default="node")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    external_arguments = (
        args.external_evidence,
        args.external_trust_store,
        args.external_trust_root,
    )
    if any(path is not None for path in external_arguments) and not all(
        path is not None for path in external_arguments
    ):
        raise SystemExit(
            "--external-evidence, --external-trust-store and --external-trust-root "
            "must be supplied together"
        )
    if any(path is not None for path in external_arguments):
        raise RuntimeError("V2_EXTERNAL_POSITIVE_PROTOCOL_NOT_IMPLEMENTED")
    repo_root = Path(args.repo_root).resolve()
    if args.engine_output is not None:
        supplied_engine_root = args.engine_output.resolve(strict=True)
        detected_version = (
            "2"
            if (
                supplied_engine_root / "frontend-interaction-formal-campaign.json"
            ).is_file()
            else "1"
            if (supplied_engine_root / "frontend-formal-route-campaign.json").is_file()
            else None
        )
        if detected_version is None:
            raise SystemExit("engine output contains neither the v1 nor v2 campaign")
        if (
            args.contract_version != "auto"
            and args.contract_version != detected_version
        ):
            raise SystemExit("declared contract version does not match engine output")
        contract_version = detected_version
    else:
        supplied_engine_root = None
        contract_version = (
            "1" if args.contract_version == "auto" else args.contract_version
        )
    client_key = CLIENT_KEY_V2 if contract_version == "2" else CLIENT_KEY
    verification_key = (
        VERIFICATION_KEY_V2 if contract_version == "2" else VERIFICATION_KEY
    )
    client_target = repo_root / "client-packs" / client_key
    verification_target = repo_root / "verification-packs" / verification_key
    if not args.force and (client_target.exists() or verification_target.exists()):
        raise SystemExit("output exists; pass --force to refresh the paired packs")
    if contract_version == "2" and args.toolchain_evidence is None:
        raise SystemExit("v2 requires --toolchain-evidence with exact raw evidence")
    with tempfile.TemporaryDirectory(
        prefix=".frontend-formal-pack-stage-", dir=repo_root
    ) as directory:
        staging_root = Path(directory)
        if supplied_engine_root is None:
            engine_root = staging_root / "engine-output"
            default_cli = (
                "engines/frontend-client-engine/dist/src/frontend-interaction-formal-cli.js"
                if contract_version == "2"
                else "engines/frontend-client-engine/dist/src/frontend-formal-cli.js"
            )
            engine_cli = Path(args.engine_cli or default_cli)
            if not engine_cli.is_absolute():
                engine_cli = repo_root / engine_cli
            engine_command = [args.node, str(engine_cli)]
            if contract_version == "2":
                engine_command.extend(
                    ["--proof-profile", "bounded-frontend-interaction-v1"]
                )
            engine_command.extend(["--output", str(engine_root)])
            run_checked(engine_command, cwd=repo_root)
        else:
            engine_root = supplied_engine_root
        toolchain_path = args.toolchain_evidence
        if contract_version == "2":
            assert toolchain_path is not None
            client_pack, verification_pack = build_packs_v2(
                repo_root,
                engine_root,
                staging_root,
                toolchain_path,
                (
                    args.external_evidence
                    if args.external_evidence is not None
                    else None
                ),
                (
                    args.external_trust_store
                    if args.external_trust_store is not None
                    else None
                ),
                (
                    args.external_trust_root
                    if args.external_trust_root is not None
                    else None
                ),
            )
        else:
            client_pack, verification_pack = build_packs(
                repo_root,
                engine_root,
                staging_root,
                toolchain_evidence_path=toolchain_path,
            )
        publish_pair(
            [
                (client_pack, client_target),
                (verification_pack, verification_target),
            ],
            staging_root=staging_root,
            force=args.force,
        )
    print(client_target)
    print(verification_target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

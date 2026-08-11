#!/usr/bin/env python3
"""Execute exact frontend toolchains for a 9-profile/72-route campaign.

The frontend engine deliberately emits projects without dependency locks or
runtime evidence.  This runner consumes that immutable output, validates every
byte and route binding, copies each distinct project into an isolated temporary
workspace, and runs only the allowlisted commands for its exact profile.

Build/test evidence is not browser, device, independent, or certification
evidence.  Those boundaries remain explicit in the emitted result.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field as dataclass_field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

SCHEMA_VERSION = "1.0"
CAMPAIGN_KIND = "frontend-formal-route-campaign"
PROOF_PROFILE = "bounded-navigation-v1"
OUTPUT_KIND = "frontend-formal-toolchain-evidence"
INTERACTION_PROOF_PROFILE = "bounded-frontend-interaction-v1"
INTERACTION_CAMPAIGN_KIND = "frontend-interaction-formal-route-campaign"
INTERACTION_OUTPUT_KIND = "frontend-interaction-toolchain-evidence"
INTERACTION_BLOCK_IDS = (
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
INTERACTION_BLOCK_SYMBOLS = {
    "navigation": "route-navigation-deeplink-404",
    "component_template": "component-template-view",
    "state_management": "state-management",
    "action_event": "action-event",
    "effect_lifecycle": "effect-lifecycle",
    "form_binding_validation": "form-binding-validation",
    "api_network": "api-network",
    "identity_permission": "identity-permission",
    "rendering_hydration": "rendering-hydration",
    "accessibility_focus": "accessibility-focus",
    "i18n_theme_responsive": "i18n-theme-responsive",
    "native_platform": "native-platform",
}
LOCKED_INTERACTION_SCENARIO_POLICY_VERSION = "bounded-frontend-interaction-scenarios-v1"
LOCKED_INTERACTION_SCENARIO_SOURCE_SHA256 = (
    "sha256:52f60c2c8a65d2d0419be96e71357b90f3d2713e9895f5c532db923e76cfe619"
)
LOCKED_INTERACTION_SCENARIO_SOURCE_BYTE_COUNT = 13_234
LOCKED_INTERACTION_SCENARIO_IDS = (
    "BOOT_PUBLIC",
    "NAVIGATE_PROTECTED_ANONYMOUS_DENIED",
    "AUTHENTICATE_AND_NAVIGATE_PROTECTED",
    "FORM_INVALID_SUBMIT_FOCUS_ERROR",
    "FORM_VALID_SUBMIT_API_SUCCESS",
    "API_ERROR_CANCEL_STALE_RESPONSE",
    "HYDRATE_MATCH_SINGLE_EFFECT_CLEANUP",
    "LOCALE_THEME_VIEWPORT_CHANGE",
    "NATIVE_DEEPLINK_BACKGROUND_PERMISSION_DENIED_RECOVERY",
    "TENANT_ISOLATION_MISMATCH_DENIED",
    "API_NETWORK_ERROR",
    "HYDRATE_MISMATCH_ERROR",
    "NATIVE_FOREGROUND_PERMISSION_GRANTED_OPEN",
    "LOCALE_EN_US_WIDE_721",
    "UNSUPPORTED_THEME_FALLBACK",
    "BREAKPOINT_720_COMPACT",
    "NAVIGATE_HELP_PUBLIC",
    "KEYBOARD_ENTER_SUBMIT",
)
RUNTIME_CHANNELS = ("browser", "android", "ios", "harmonyos")
RUNTIME_STATUSES = {"PASSED", "FAILED", "NOT_RUN", "NOT_APPLICABLE"}
RUNTIME_ARTIFACT_REF_KEYS = {
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
}
RUNTIME_TRACE_ARTIFACT_REF_KEYS = {
    "artifact_id",
    "role",
    "profile_id",
    "channel",
    "scenario_id",
    "path",
    "sha256",
    "byte_count",
}
BLOCK_OBSERVER_TRACE_ARTIFACT_REF_KEYS = {
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
BLOCK_OBSERVER_CONTRACT = "block-specific-runtime-observation-v1"
BLOCK_SPECIFIC_RUNTIME_ACTUAL_SOURCE = "BLOCK_SPECIFIC_RUNTIME_OBSERVED"
BLOCK_SPECIFIC_RUNTIME_PARTIAL_REASON = (
    "BLOCK_SPECIFIC_RUNTIME_PARTIAL_CLOSURE"
)
WEB_BROWSER_MANDATORY_NOT_RUN_BLOCK_IDS = (
    "effect-lifecycle",
    "api-network",
    "identity-permission",
    "rendering-hydration",
    "native-platform",
)
NATIVE_MANDATORY_NOT_RUN_BLOCK_IDS = ("api-network",)
NATIVE_API_NOT_RUN_REASON = (
    "a single native adapter call does not prove timeout, retry, tenant cache, "
    "and unmount cancellation"
)
FORBIDDEN_RUNTIME_ACTUAL_SOURCES = {
    "SELF_REPORTED_REDUCER_JSON",
    "RUNTIME_OBSERVED",
}
BLOCK_OBSERVER_SPECS = {
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
        "measurement_surface": (
            "[data-elmos-state-measurement] before/after/saturated"
        ),
        "trace_role": "browser-framework-state-transition-observer-trace",
        "measurement_keys": ("state_measurement",),
        "supporting_trace_roles": (
            "browser-framework-event-trace",
            "browser-dom-snapshot",
        ),
    },
    "action-event": {
        "observer_kind": "NATIVE_EVENT_OUTCOME_OBSERVER",
        "measurement_surface": (
            "captured click/keydown/submit + [data-elmos-action-outcome]"
        ),
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
        "measurement_surface": (
            "control value+ValidityState+error DOM+focus"
        ),
        "trace_role": "browser-form-validity-observer-trace",
        "measurement_keys": (
            "control",
            "validity_state",
            "error_dom",
            "active_element",
        ),
        "supporting_trace_roles": (
            "browser-dom-snapshot",
            "browser-framework-event-trace",
            "browser-accessibility-axe-trace",
        ),
    },
    "api-network": {
        "observer_kind": "BROWSER_NETWORK_OBSERVER",
        "measurement_surface": (
            "Playwright request/response/requestfailed + app abort/stale marker"
        ),
        "trace_role": "browser-network-observer-trace",
        "measurement_keys": ("network_events", "application_markers"),
        "supporting_trace_roles": (
            "browser-network-trace",
            "browser-framework-event-trace",
        ),
    },
    "identity-permission": {
        "observer_kind": "AUTHORITY_ADAPTER_OBSERVER",
        "measurement_surface": (
            "[data-elmos-auth-decision] only if real adapter trace"
        ),
        "trace_role": "browser-authority-adapter-observer-trace",
        "measurement_keys": ("adapter_events", "decision_attributes"),
        "supporting_trace_roles": ("browser-framework-event-trace",),
    },
    "rendering-hydration": {
        "observer_kind": "SSR_HYDRATION_OBSERVER",
        "measurement_surface": (
            "server markup digest+hydration warnings/mutations/effect count"
        ),
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
        "measurement_surface": (
            "aria snapshot+axe+active element+keyboard"
        ),
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
        "measurement_surface": (
            "html lang+rendered translated text+computed theme tokens+measured layout"
        ),
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
        "measurement_surface": (
            "native semantics+lifecycle+permission+adapter trace"
        ),
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
RUNTIME_TRACE_ROLES = {
    "browser": {
        "browser-dom-snapshot",
        "browser-framework-event-trace",
        "browser-accessibility-axe-trace",
        "browser-network-trace",
        "flutter-framework-event-trace",
        "flutter-semantics-trace",
        "flutter-network-adapter-trace",
        "flutter-platform-adapter-trace",
        *(
            spec["trace_role"]
            for spec in BLOCK_OBSERVER_SPECS.values()
            if spec["trace_role"].startswith("browser-")
        ),
    },
    "android": {
        "native-framework-event-trace",
        "native-adapter-trace",
        "native-device-trace",
        "native-adapter-device-observer-trace",
    },
    "ios": {
        "native-framework-event-trace",
        "native-adapter-trace",
        "native-device-trace",
        "native-adapter-device-observer-trace",
    },
    "harmonyos": {
        "native-framework-event-trace",
        "native-adapter-trace",
        "native-device-trace",
        "native-adapter-device-observer-trace",
    },
}
RUNTIME_RESULT_MANIFEST_REF_KEYS = {
    "artifact_id",
    "role",
    "profile_id",
    "channel",
    "path",
    "sha256",
    "byte_count",
    "manifest_digest",
}
RUNTIME_EXECUTION_KEYS = {
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
RUNTIME_CHANNEL_RECORD_KEYS = {
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
INTERACTION_BLOCK_ACTUAL_KEYS = {
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
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
EXACT_VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+){2}(?:[-+][0-9A-Za-z.-]+)?$")
MAX_LOG_BYTES = 64 * 1024
RUNNER_PATH = Path(__file__).resolve()
REPOSITORY_ROOT = RUNNER_PATH.parents[1]
PLAYWRIGHT_HELPER_PATH = (
    REPOSITORY_ROOT / "tooling/frontend_formal_playwright_probe.cjs"
)
WEB_CONSOLE_ROOT = REPOSITORY_ROOT / "apps/web-console"
PLAYWRIGHT_PACKAGE_ROOT = WEB_CONSOLE_ROOT / "node_modules/@playwright/test"
AXE_PACKAGE_ROOT = WEB_CONSOLE_ROOT / "node_modules/@axe-core/playwright"
WEB_CONSOLE_LOCK_PATH = WEB_CONSOLE_ROOT / "pnpm-lock.yaml"
WEB_CONSOLE_PACKAGE_PATH = WEB_CONSOLE_ROOT / "package.json"
LOCKED_PLAYWRIGHT_VERSION = "1.61.1"
LOCKED_AXE_PLAYWRIGHT_VERSION = "4.12.1"
LOCKED_WEB_CONSOLE_LOCK_SHA256 = (
    "sha256:e5d920fe0af72e14fa3c07670812d3da26ac7b1e857f34d8a476ea02149bc543"
)
LOCKED_WEB_CONSOLE_PACKAGE_SHA256 = (
    "sha256:4b26148a0a06442137bf49f711ddacfc311d41a5be619dec5536489ac422cbee"
)
LOCKED_PLAYWRIGHT_PACKAGE_SHA256 = (
    "sha256:9d8556509e073169efec663b7f71c13f17d7002b307d00d48bf88ee91c387f3e"
)
LOCKED_AXE_PACKAGE_SHA256 = (
    "sha256:c3e69bcde1800e1e748023ce6ed68018b1ce48714160441b7ffb7e1a6f2bd2a2"
)
DEFAULT_CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEFAULT_FIREFOX_PATH = "/Applications/Firefox.app/Contents/MacOS/firefox"
LOCKED_FLUTTER_WEB_CFT_VERSION = "151.0.7922.77"
LOCKED_FLUTTER_WEB_CFT_ENDPOINT = (
    "https://googlechromelabs.github.io/chrome-for-testing/"
    "LATEST_RELEASE_151.0.7922"
)
LOCKED_FLUTTER_WEB_CFT_CHROME_URL = (
    "https://storage.googleapis.com/chrome-for-testing-public/151.0.7922.77/"
    "mac-arm64/chrome-mac-arm64.zip"
)
LOCKED_FLUTTER_WEB_CFT_DRIVER_URL = (
    "https://storage.googleapis.com/chrome-for-testing-public/151.0.7922.77/"
    "mac-arm64/chromedriver-mac-arm64.zip"
)
LOCKED_Z3_VERSION = "Z3 version 4.16.0 - 64 bit"
LOCKED_Z3_BINARY_SHA256 = (
    "sha256:537a502af2f4013a8e887beebe525a0dae84918a61ff545991e36dfda07ed6d7"
)
LOCKED_Z3_ARGS = ["-in"]
INTERACTION_ENGINE_ROOT = REPOSITORY_ROOT / "engines/frontend-client-engine"
INTERACTION_ENGINE_SOURCE_ROOT = INTERACTION_ENGINE_ROOT / "src"
INTERACTION_ENGINE_DIST_ROOT = INTERACTION_ENGINE_ROOT / "dist/src"
INTERACTION_ENGINE_CLI_SOURCE_PATH = (
    INTERACTION_ENGINE_SOURCE_ROOT / "frontend-interaction-formal-cli.ts"
)
INTERACTION_ENGINE_EQUIVALENCE_SOURCE_PATH = (
    INTERACTION_ENGINE_SOURCE_ROOT / "frontend-interaction-formal-equivalence.ts"
)
INTERACTION_ENGINE_CLI_DIST_PATH = (
    INTERACTION_ENGINE_DIST_ROOT / "frontend-interaction-formal-cli.js"
)
INTERACTION_ENGINE_EQUIVALENCE_DIST_PATH = (
    INTERACTION_ENGINE_DIST_ROOT / "frontend-interaction-formal-equivalence.js"
)
INTERACTION_ENGINE_PACKAGE_PATH = INTERACTION_ENGINE_ROOT / "package.json"
INTERACTION_ENGINE_TSCONFIG_PATH = INTERACTION_ENGINE_ROOT / "tsconfig.json"
INTERACTION_ENGINE_LOCK_PATH = INTERACTION_ENGINE_ROOT / "pnpm-lock.yaml"
INTERACTION_ENGINE_TYPESCRIPT_PACKAGE_PATH = (
    INTERACTION_ENGINE_ROOT / "node_modules/typescript/package.json"
)
LOCKED_INTERACTION_ENGINE_NODE_VERSION = "v26.0.0"
LOCKED_INTERACTION_ENGINE_NODE_SHA256 = (
    "sha256:73cc3e9b5d2b1753ea3395a5bf39787ef85f20f048a0f0744761860b81b8fbdb"
)
LOCKED_INTERACTION_ENGINE_SOURCE_TREE_FILE_COUNT = 42
LOCKED_INTERACTION_ENGINE_SOURCE_TREE_SHA256 = (
    "sha256:35a36e6e914a557238594c37128d075cb77508b3ce1578230b09c6b94f872b60"
)
LOCKED_INTERACTION_ENGINE_DIST_TREE_FILE_COUNT = 132
LOCKED_INTERACTION_ENGINE_DIST_TREE_SHA256 = (
    "sha256:fa169619fc4ffb75a12e0f1825fefe195e624aa9dac1958b898d5888107ecb62"
)
LOCKED_INTERACTION_ENGINE_FILE_SHA256 = {
    "cli_source": "sha256:695527da9f1470c4cdf17d9bd1e3f74502382a2945400ca82a770d97a6739c60",
    "equivalence_source": "sha256:a830b31a9cb25c231783a3e8a25a12484fe9f9a83e714711b204ad06043da67f",
    "cli_dist": "sha256:159603fa85be7e6525a34b362eb6e05432979e08729acebb79b42217927f10a8",
    "equivalence_dist": "sha256:a4f00762b0dcb256ae43758f97acc9e0951d577209cd54e5916ad3f7e5c9b8ab",
    "package": "sha256:3b34ae57b1dde2a766844fa3e376834905d0c3ef1be7b9d80dcab2ffcdd526b6",
    "tsconfig": "sha256:445643bccad04d5cb5aeae088bd9430b462b260e524412d4d19897484f73f273",
    "lock": "sha256:547799cf74324119abd2d0f601362384018bcb11e553fd63afc947570962604e",
    "typescript_package": "sha256:5a0bb7f286c4b3f1413a42c05f902311b161f70e5f52d9da10490443bfd595a3",
}
LOCKED_INTERACTION_ENGINE_TYPESCRIPT_VERSION = "5.9.2"
INTERACTION_ENGINE_VERIFY_TIMEOUT_SECONDS = 120
SOLVER_RESULT_KEYS = {
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

EXPECTED_PROFILES: dict[str, dict[str, Any]] = {
    "angular": {"framework_version": "22.0.8", "platforms": ["WEB"], "kind": "node"},
    "flutter": {
        "framework_version": "3.44.1",
        "platforms": ["ANDROID", "IOS", "WEB"],
        "kind": "flutter",
    },
    "harmony-arkui": {
        "framework_version": "6.0.0(20)",
        "platforms": ["HARMONYOS"],
        "kind": "harmony",
    },
    "jquery": {"framework_version": "4.0.0", "platforms": ["WEB"], "kind": "node"},
    "react": {"framework_version": "19.2.8", "platforms": ["WEB"], "kind": "node"},
    "react-native": {
        "framework_version": "0.86.0",
        "platforms": ["ANDROID", "IOS", "WEB"],
        "kind": "node",
    },
    "svelte": {"framework_version": "5.56.8", "platforms": ["WEB"], "kind": "node"},
    "vue2": {"framework_version": "2.7.16", "platforms": ["WEB"], "kind": "node"},
    "vue3": {"framework_version": "3.5.40", "platforms": ["WEB"], "kind": "node"},
}


def required_runtime_channels(profile_id: str) -> tuple[str, ...]:
    """Return the exact runtime channels required by the frozen target profile.

    Platform applicability is profile metadata, not a runner-selected waiver.
    Build, model, and Web export results never alter this requirement.
    """

    if profile_id not in EXPECTED_PROFILES:
        raise ValidationError(f"unknown runtime profile: {profile_id}")
    if profile_id in {"flutter", "react-native"}:
        return ("browser", "android", "ios")
    if profile_id == "harmony-arkui":
        return ("harmonyos",)
    return ("browser",)


def runtime_channel_applicable(profile_id: str, channel: str) -> bool:
    if channel not in RUNTIME_CHANNELS:
        raise ValidationError(f"unknown runtime channel: {channel}")
    return channel in required_runtime_channels(profile_id)


def unavailable_runtime_channel(
    profile_id: str,
    channel: str,
    reason: str,
    *,
    tool_discovery: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Create a fail-closed runtime record without inventing observations."""

    required = runtime_channel_applicable(profile_id, channel)
    status = "NOT_RUN" if required else "NOT_APPLICABLE"
    exact_reason = reason if required else "PROFILE_CHANNEL_NOT_APPLICABLE"
    return {
        "channel": channel,
        "required": required,
        "status": status,
        "reason": exact_reason,
        "runner_kind": None,
        "tool_discovery": [dict(item) for item in tool_discovery],
        "execution_policy_digest": None,
        "runtime_tools": [],
        "build_execution": None,
        "startup_execution": None,
        "journey_execution": None,
        "scenario_manifest_digest": None,
        "scenario_count": 0,
        "scenarios": [],
        "semantic_blocks": {
            block_id: {
                "status": status,
                "observation_refs": [],
                "observation_digest": None,
            }
            for block_id in INTERACTION_BLOCK_IDS
        },
        "raw_artifacts": [],
        "runtime_source_artifacts": [],
        "result_manifest": None,
        "model_values_used_as_actual": False,
    }


def unavailable_runtime_observations(
    profile: ProfileArtifact, reason: str
) -> dict[str, dict[str, Any]]:
    blocked_reason = (
        "PRECOMPUTED_MODEL_ORACLE_CONSUMED_BY_RUNTIME"
        if profile.runtime_model_oracle_findings
        else reason
    )
    return {
        channel: unavailable_runtime_channel(
            profile.profile_id,
            channel,
            blocked_reason,
            tool_discovery=profile.runtime_model_oracle_findings,
        )
        for channel in RUNTIME_CHANNELS
    }


def validate_runtime_stream(value: Any, name: str) -> dict[str, Any]:
    stream = require_exact_keys(
        value, {"text", "byte_count", "sha256", "truncated"}, name
    )
    if (
        not isinstance(stream["text"], str)
        or type(stream["byte_count"]) is not int
        or stream["byte_count"] < 0
        or type(stream["truncated"]) is not bool
    ):
        raise ValidationError(f"{name} fields are invalid")
    digest = require_sha256(stream["sha256"], f"{name}.sha256")
    if stream["truncated"]:
        raise ValidationError(f"{name} is truncated and cannot support runtime PASS")
    data = stream["text"].encode("utf-8")
    if stream["byte_count"] != len(data) or digest != sha256_bytes(data):
        raise ValidationError(f"{name} byte binding mismatch")
    return stream


def validate_runtime_execution(
    value: Any,
    name: str,
    phase: str,
    artifact_ids: set[str],
    expected_policy: Mapping[str, Any],
) -> dict[str, Any]:
    execution = require_exact_keys(value, RUNTIME_EXECUTION_KEYS, name)
    if (
        execution["schema_version"] != SCHEMA_VERSION
        or execution["kind"] != "frontend-interaction-runtime-execution"
        or execution["phase"] != phase
        or execution["status"] != "PASSED"
        or execution["exit_code"] != 0
        or execution["signal"] is not None
        or execution["reason"] is not None
    ):
        raise ValidationError(f"{name} did not bind a successful {phase} execution")
    tool = require_exact_keys(
        execution["tool"],
        {"path", "realpath", "sha256", "byte_count", "version"},
        f"{name}.tool",
    )
    if (
        not isinstance(tool["path"], str)
        or not isinstance(tool["realpath"], str)
        or not Path(tool["path"]).is_absolute()
        or not Path(tool["realpath"]).is_absolute()
        or type(tool["byte_count"]) is not int
        or tool["byte_count"] < 1
        or not isinstance(tool["version"], str)
        or not tool["version"]
    ):
        raise ValidationError(f"{name}.tool identity is invalid")
    tool_digest = require_sha256(tool["sha256"], f"{name}.tool.sha256")
    try:
        resolved_tool = Path(tool["path"]).resolve(strict=True)
        tool_bytes = resolved_tool.read_bytes()
    except (OSError, RuntimeError) as error:
        raise ValidationError(f"{name}.tool cannot be replay-bound: {error}") from error
    if (
        str(resolved_tool) != tool["realpath"]
        or len(tool_bytes) != tool["byte_count"]
        or sha256_bytes(tool_bytes) != tool_digest
        or not os.access(resolved_tool, os.X_OK)
    ):
        raise ValidationError(f"{name}.tool byte identity drift")
    argv = execution["argv"]
    try:
        argv_tool = Path(argv[0]).resolve(strict=True) if isinstance(argv, list) and argv else None
    except (OSError, RuntimeError):
        argv_tool = None
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(item, str) or not item for item in argv)
        or argv_tool != resolved_tool
        or not isinstance(execution["cwd"], str)
        or not Path(execution["cwd"]).is_absolute()
        or not isinstance(execution["started_at"], str)
        or type(execution["duration_ms"]) is not int
        or execution["duration_ms"] < 0
        or type(execution["timeout_seconds"]) is not int
        or execution["timeout_seconds"] < 1
    ):
        raise ValidationError(f"{name} argv/cwd/timing binding is invalid")
    policy = require_exact_keys(
        dict(expected_policy),
        {"phase", "tool", "argv", "cwd", "environment"},
        f"{name}.policy",
    )
    if policy["phase"] != phase:
        raise ValidationError(f"{name}.policy phase drift")
    if (
        tool != policy["tool"]
        or argv != policy["argv"]
        or execution["cwd"] != policy["cwd"]
    ):
        raise ValidationError(f"{name} execution policy binding mismatch")
    environment = require_exact_keys(
        execution["environment"],
        {
            "allowlisted_inherited_keys",
            "explicit",
            "network_allowed",
            "unlisted_environment_inherited",
        },
        f"{name}.environment",
    )
    if (
        not isinstance(environment["allowlisted_inherited_keys"], list)
        or not isinstance(environment["explicit"], dict)
        or type(environment["network_allowed"]) is not bool
        or environment["unlisted_environment_inherited"] is not False
    ):
        raise ValidationError(f"{name}.environment is invalid")
    if environment != policy["environment"]:
        raise ValidationError(f"{name}.environment policy drift")
    validate_runtime_stream(execution["stdout"], f"{name}.stdout")
    validate_runtime_stream(execution["stderr"], f"{name}.stderr")
    refs = execution["artifact_refs"]
    if (
        not isinstance(refs, list)
        or any(not isinstance(item, str) or item not in artifact_ids for item in refs)
        or len(refs) != len(set(refs))
    ):
        raise ValidationError(f"{name}.artifact_refs are invalid")
    without_id = dict(execution)
    without_id.pop("execution_id")
    if execution["execution_id"] != digest_json(without_id):
        raise ValidationError(f"{name}.execution_id mismatch")
    return execution


def validate_runtime_trace_artifact_ref(
    value: Any,
    *,
    evidence_root: Path,
    profile_id: str,
    channel: str,
    scenario_id: str,
    name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve one actual browser/device trace from immutable artifact bytes."""

    ref = require_exact_keys(value, RUNTIME_TRACE_ARTIFACT_REF_KEYS, name)
    role = ref["role"]
    if (
        not isinstance(ref["artifact_id"], str)
        or not ref["artifact_id"]
        or role not in RUNTIME_TRACE_ROLES[channel]
        or ref["profile_id"] != profile_id
        or ref["channel"] != channel
        or ref["scenario_id"] != scenario_id
        or type(ref["byte_count"]) is not int
        or ref["byte_count"] < 1
    ):
        raise ValidationError(f"{name} trace identity/role binding mismatch")
    digest = require_sha256(ref["sha256"], f"{name}.sha256")
    path = resolve_regular_file(evidence_root, ref["path"], f"{name}.path")
    data = path.read_bytes()
    if len(data) != ref["byte_count"] or sha256_bytes(data) != digest:
        raise ValidationError(f"{name} trace artifact byte binding mismatch")
    artifact = require_exact_keys(
        read_json(path, name),
        {
            "schema_version",
            "kind",
            "actual_source",
            "role",
            "profile_id",
            "channel",
            "scenario_id",
            "capture",
        },
        name,
    )
    if (
        artifact["schema_version"] != SCHEMA_VERSION
        or artifact["kind"] != "frontend-interaction-runtime-trace-artifact"
        or artifact["actual_source"] != "ALLOWLISTED_RUNTIME_CAPTURE"
        or artifact["role"] != role
        or artifact["profile_id"] != profile_id
        or artifact["channel"] != channel
        or artifact["scenario_id"] != scenario_id
    ):
        raise ValidationError(f"{name} trace actual-source identity binding mismatch")
    capture = artifact["capture"]
    if role == "browser-dom-snapshot":
        capture = require_exact_keys(
            capture, {"root_selector", "outer_html"}, f"{name}.capture"
        )
        if (
            capture["root_selector"] != "#elmos-interaction"
            or not isinstance(capture["outer_html"], str)
            or not capture["outer_html"].strip()
        ):
            raise ValidationError(f"{name} DOM capture is empty or unscoped")
    elif role in {
        "browser-framework-event-trace",
        "browser-network-trace",
        "flutter-framework-event-trace",
        "flutter-network-adapter-trace",
        "flutter-platform-adapter-trace",
        "native-framework-event-trace",
        "native-adapter-trace",
    }:
        capture = require_exact_keys(capture, {"events"}, f"{name}.capture")
        events = capture["events"]
        if (
            not isinstance(events, list)
            or not events
            or any(not isinstance(event, dict) or not event for event in events)
        ):
            raise ValidationError(f"{name} event trace is empty or invalid")
    elif role == "flutter-semantics-trace":
        capture = require_exact_keys(
            capture, {"semantics_label", "focus"}, f"{name}.capture"
        )
        focus = require_exact_keys(
            capture["focus"], {"target", "query_has_focus"}, f"{name}.capture.focus"
        )
        if (
            not isinstance(capture["semantics_label"], str)
            or not capture["semantics_label"].strip()
            or (
                focus["target"] is not None
                and not isinstance(focus["target"], str)
            )
            or type(focus["query_has_focus"]) is not bool
        ):
            raise ValidationError(f"{name} Flutter semantics/focus trace is invalid")
    elif role == "browser-accessibility-axe-trace":
        capture = require_exact_keys(
            capture,
            {
                "aria_snapshot",
                "active_element",
                "axe_results",
                "keyboard_events",
                "focus_events",
            },
            f"{name}.capture",
        )
        axe = capture["axe_results"]
        if (
            not isinstance(capture["aria_snapshot"], str)
            or not capture["aria_snapshot"].strip()
            or not isinstance(capture["active_element"], dict)
            or not capture["active_element"]
            or not isinstance(axe, dict)
            or not isinstance(axe.get("violations"), list)
            or not isinstance(capture["keyboard_events"], list)
            or not isinstance(capture["focus_events"], list)
            or not capture["focus_events"]
        ):
            raise ValidationError(f"{name} accessibility/focus capture is incomplete")
        if any(
            isinstance(violation, dict)
            and violation.get("impact") in {"serious", "critical"}
            for violation in axe["violations"]
        ):
            raise ValidationError(f"{name} contains serious accessibility violations")
    elif role == "native-device-trace":
        capture = require_exact_keys(
            capture, {"device_identity", "events"}, f"{name}.capture"
        )
        if (
            not isinstance(capture["device_identity"], dict)
            or not capture["device_identity"]
            or not isinstance(capture["events"], list)
            or not capture["events"]
        ):
            raise ValidationError(f"{name} device capture is incomplete")
    else:  # pragma: no cover - role allowlist above is exhaustive
        raise ValidationError(f"{name} trace role is unsupported")
    expected_id = digest_json(
        {
            "role": role,
            "profile_id": profile_id,
            "channel": channel,
            "scenario_id": scenario_id,
            "path": ref["path"],
            "sha256": digest,
            "byte_count": len(data),
        }
    )
    if ref["artifact_id"] != expected_id:
        raise ValidationError(f"{name} trace artifact_id binding mismatch")
    return ref, artifact


def _contains_forbidden_observer_payload_key(value: Any) -> bool:
    """Reject model/oracle-shaped data hidden inside a raw observer capture."""

    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in {
                "actual",
                "expected",
                "model",
                "projection",
                "observation",
                "blocks",
            } or _contains_forbidden_observer_payload_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_observer_payload_key(item) for item in value)
    return False


def validate_block_observer_measurement(
    value: Any, *, block_id: str, name: str
) -> dict[str, Any]:
    """Validate one browser measurement before it can support an actual value."""

    spec = BLOCK_OBSERVER_SPECS[block_id]
    measurement = require_exact_keys(
        value, set(spec["measurement_keys"]), name
    )
    if _contains_forbidden_observer_payload_key(measurement):
        raise ValidationError(f"{name} contains model/oracle-shaped payload")

    def require_nonempty_mapping(key: str) -> None:
        if not isinstance(measurement[key], dict) or not measurement[key]:
            raise ValidationError(f"{name}.{key} is empty or invalid")

    def require_nonempty_list(key: str) -> None:
        if not isinstance(measurement[key], list) or not measurement[key]:
            raise ValidationError(f"{name}.{key} is empty or invalid")

    if block_id == "route-navigation-deeplink-404":
        if (
            not isinstance(measurement["page_url"], str)
            or not re.match(r"^https?://", measurement["page_url"])
        ):
            raise ValidationError(f"{name}.page_url is invalid")
        require_exact_keys(
            measurement["active_route_attributes"],
            {
                "data-route-id",
                "data-route-path",
                "data-deep-link",
                "data-requires-auth",
            },
            f"{name}.active_route_attributes",
        )
        require_nonempty_list("declared_routes")
        for index, route in enumerate(measurement["declared_routes"]):
            require_exact_keys(
                route,
                {"route_id", "route_path", "deep_link", "requires_auth"},
                f"{name}.declared_routes[{index}]",
            )
    elif block_id == "component-template-view":
        for key in ("heading", "text"):
            if not isinstance(measurement[key], str) or not measurement[key]:
                raise ValidationError(f"{name}.{key} is empty or invalid")
        if type(measurement["visibility"]) is not bool:
            raise ValidationError(f"{name}.visibility is invalid")
        require_exact_keys(
            measurement["attributes"],
            {
                "id",
                "data-route-id",
                "data-elmos-active-component",
                "data-elmos-component-id",
                "data-elmos-component-key",
            },
            f"{name}.attributes",
        )
    elif block_id == "state-management":
        require_exact_keys(
            measurement["state_measurement"],
            {
                "data-elmos-state-id",
                "data-elmos-before",
                "data-elmos-after",
                "data-elmos-saturated",
            },
            f"{name}.state_measurement",
        )
    elif block_id == "action-event":
        require_nonempty_list("captured_events")
        require_exact_keys(
            measurement["outcome_attributes"],
            {
                "data-elmos-event-outcome",
                "data-elmos-keyboard-key",
                "data-elmos-handled",
                "data-elmos-action",
            },
            f"{name}.outcome_attributes",
        )
    elif block_id == "effect-lifecycle":
        require_nonempty_list("ordered_events")
        for index, event in enumerate(measurement["ordered_events"]):
            require_exact_keys(
                event,
                {
                    "lifecycle",
                    "effect",
                    "executions",
                    "cleanup",
                    "stale_response_ignored",
                },
                f"{name}.ordered_events[{index}]",
            )
    elif block_id == "form-binding-validation":
        require_exact_keys(
            measurement["control"],
            {"form_id", "field_id", "value"},
            f"{name}.control",
        )
        require_exact_keys(
            measurement["validity_state"],
            {"submitted", "valid"},
            f"{name}.validity_state",
        )
        require_exact_keys(
            measurement["error_dom"], {"error_code"}, f"{name}.error_dom"
        )
        require_exact_keys(
            measurement["active_element"],
            {"focus_target"},
            f"{name}.active_element",
        )
    elif block_id == "api-network":
        if not isinstance(measurement["network_events"], list):
            raise ValidationError(f"{name}.network_events is invalid")
        require_exact_keys(
            measurement["application_markers"],
            {
                "operation_id",
                "called",
                "method",
                "path",
                "outcome",
                "canceled",
                "stale_ignored",
                "cache_key",
            },
            f"{name}.application_markers",
        )
    elif block_id == "identity-permission":
        require_nonempty_list("adapter_events")
        require_exact_keys(
            measurement["decision_attributes"],
            {
                "role",
                "permission",
                "permission_granted",
                "tenant_match",
                "authorized",
                "server_authority_required",
            },
            f"{name}.decision_attributes",
        )
    elif block_id == "rendering-hydration":
        require_sha256(
            measurement["server_markup_digest"],
            f"{name}.server_markup_digest",
        )
        if (
            not isinstance(measurement["hydration_warnings"], list)
            or not isinstance(measurement["mutations"], list)
            or type(measurement["effect_count"]) is not int
            or measurement["effect_count"] < 0
        ):
            raise ValidationError(f"{name} hydration measurement is invalid")
        require_exact_keys(
            measurement["hydration_state"],
            {
                "mode",
                "requested",
                "status",
                "duplicate_effects",
                "mismatch_visible",
            },
            f"{name}.hydration_state",
        )
    elif block_id == "accessibility-focus":
        if (
            not isinstance(measurement["aria_snapshot"], str)
            or not measurement["aria_snapshot"].strip()
        ):
            raise ValidationError(f"{name}.aria_snapshot is invalid")
        require_nonempty_mapping("axe_results")
        require_nonempty_mapping("active_element")
        if not isinstance(measurement["keyboard_events"], list):
            raise ValidationError(f"{name}.keyboard_events is invalid")
        active_element = require_exact_keys(
            measurement["active_element"],
            {"tag", "attributes"},
            f"{name}.active_element",
        )
        if (
            not isinstance(active_element["tag"], str)
            or not isinstance(active_element["attributes"], dict)
        ):
            raise ValidationError(f"{name}.active_element is invalid")
        require_exact_keys(
            measurement["accessibility_state"],
            {
                "main_role",
                "heading_level",
                "form_label",
                "error_role",
                "live_region",
                "focus_target",
                "keyboard_submit",
            },
            f"{name}.accessibility_state",
        )
    elif block_id == "i18n-theme-responsive":
        if not isinstance(measurement["html_lang"], str) or not measurement[
            "html_lang"
        ]:
            raise ValidationError(f"{name}.html_lang is empty or invalid")
        require_exact_keys(
            measurement["translated_text"],
            {"requested_locale", "text"},
            f"{name}.translated_text",
        )
        require_exact_keys(
            measurement["computed_theme_tokens"],
            {"requested_theme", "theme"},
            f"{name}.computed_theme_tokens",
        )
        require_exact_keys(
            measurement["layout_measurement"],
            {
                "viewport_width",
                "columns",
                "computed_grid_template_columns",
                "bounding_box",
            },
            f"{name}.layout_measurement",
        )
        bounding_box = require_exact_keys(
            measurement["layout_measurement"]["bounding_box"],
            {"x", "y", "width", "height"},
            f"{name}.layout_measurement.bounding_box",
        )
        if any(
            type(value) not in {int, float} or not math.isfinite(value)
            for value in bounding_box.values()
        ) or bounding_box["width"] <= 0 or bounding_box["height"] <= 0:
            raise ValidationError(f"{name}.layout_measurement.bounding_box is invalid")
    elif block_id == "native-platform":
        require_exact_keys(
            measurement["semantics"],
            {"boundary", "attempted", "available", "outcome", "recovery"},
            f"{name}.semantics",
        )
        if (
            not isinstance(measurement["lifecycle"], str)
            or not measurement["lifecycle"]
            or not isinstance(measurement["permission"], str)
            or not measurement["permission"]
        ):
            raise ValidationError(f"{name} native state is invalid")
        require_nonempty_list("adapter_events")
        require_nonempty_mapping("device_identity")
    return measurement


def _observer_string(value: Any, name: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{name} is not a string")
    return value


def _observer_bool(value: Any, name: str) -> bool:
    if type(value) is bool:
        return value
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValidationError(f"{name} is not an exact boolean measurement")


def _observer_int(value: Any, name: str) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"-?(?:0|[1-9][0-9]*)", value):
        return int(value)
    raise ValidationError(f"{name} is not an exact integer measurement")


def _css_grid_track_count(value: Any, name: str) -> int:
    """Count a computed grid track list without trusting a consumer marker."""

    if not isinstance(value, str) or not value.strip() or value.strip() == "none":
        raise ValidationError(f"{name} is not a computed grid track list")
    source = value.strip()
    repeat = re.fullmatch(r"repeat\(\s*([1-9][0-9]*)\s*,[\s\S]+\)", source)
    if repeat is not None:
        return int(repeat.group(1))
    depth = 0
    tracks: list[str] = []
    start = 0
    for index, character in enumerate(source):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                raise ValidationError(f"{name} parentheses are unbalanced")
        elif character.isspace() and depth == 0:
            if source[start:index].strip():
                tracks.append(source[start:index].strip())
            start = index + 1
    if depth != 0:
        raise ValidationError(f"{name} parentheses are unbalanced")
    if source[start:].strip():
        tracks.append(source[start:].strip())
    if not tracks:
        raise ValidationError(f"{name} has no computed grid tracks")
    return len(tracks)


def derive_actual_from_block_measurement(
    block_id: str,
    measurement: Any,
    *,
    scenario_input: Mapping[str, Any] | None = None,
    name: str = "block observer measurement",
) -> dict[str, Any]:
    """Deterministically project allowlisted raw measurements into actual JSON.

    This is the sole runtime observation projector.  Neither generated consumer
    JSON nor a probe-supplied ``actual`` value is accepted as input.
    """

    measured = validate_block_observer_measurement(
        measurement, block_id=block_id, name=name
    )
    scenario_input = scenario_input or {}
    if block_id == "route-navigation-deeplink-404":
        attrs = measured["active_route_attributes"]
        selected_path = _observer_string(
            attrs["data-route-path"], f"{name}.selected_path"
        )
        assert isinstance(selected_path, str)
        page_path = urlsplit(measured["page_url"]).path or "/"
        if page_path != selected_path:
            raise ValidationError(f"{name} page URL/active route path mismatch")
        requested_path = scenario_input.get("routePath")
        if not isinstance(requested_path, str) or not requested_path.startswith("/"):
            raise ValidationError(f"{name} frozen scenario routePath is absent")
        declared_routes = measured["declared_routes"]
        if (
            any(
                not isinstance(route["route_id"], str)
                or not isinstance(route["route_path"], str)
                or type(route["deep_link"]) is not bool
                or type(route["requires_auth"]) is not bool
                for route in declared_routes
            )
            or len({route["route_id"] for route in declared_routes})
            != len(declared_routes)
            or len({route["route_path"] for route in declared_routes})
            != len(declared_routes)
        ):
            raise ValidationError(f"{name} declared route DOM is invalid or duplicate")
        requested_route = next(
            (
                route
                for route in declared_routes
                if route["route_path"] == requested_path
            ),
            None,
        )
        selected_route_id = _observer_string(
            attrs["data-route-id"], f"{name}.selected_route_id"
        )
        first_route = declared_routes[0]
        if requested_route is None:
            resolution = "FIRST_DECLARED_FALLBACK"
            if (
                selected_path != first_route["route_path"]
                or selected_route_id != first_route["route_id"]
            ):
                raise ValidationError(f"{name} undeclared route did not use first route")
        elif selected_path == requested_path:
            resolution = "DECLARED"
            if selected_route_id != requested_route["route_id"]:
                raise ValidationError(f"{name} selected route ID/path mismatch")
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
                raise ValidationError(
                    f"{name} authorized/public route remained on a static fallback"
                )
            resolution = "AUTH_DENIED_FALLBACK"
            if (
                selected_path != first_route["route_path"]
                or selected_route_id != first_route["route_id"]
            ):
                raise ValidationError(f"{name} denied route did not use first route")
        return {
            "requestedPath": requested_path,
            "selectedRouteId": selected_route_id,
            "selectedPath": selected_path,
            "resolution": resolution,
            "deepLink": _observer_bool(
                attrs["data-deep-link"], f"{name}.deep_link"
            ),
            "requiresAuth": _observer_bool(
                attrs["data-requires-auth"], f"{name}.requires_auth"
            ),
        }
    if block_id == "component-template-view":
        attrs = measured["attributes"]
        if (
            attrs["id"] != "main"
            or attrs["data-elmos-active-component"] != "true"
            or attrs["data-route-id"] != attrs["data-elmos-component-key"]
        ):
            raise ValidationError(f"{name} is not the contracted GeneratedPage main")
        return {
            "componentId": _observer_string(
                attrs["data-elmos-component-id"], f"{name}.component_id"
            ),
            "key": _observer_string(
                attrs["data-elmos-component-key"], f"{name}.component_key"
            ),
            "title": _observer_string(measured["heading"], f"{name}.heading"),
            "text": _observer_string(measured["text"], f"{name}.text"),
            "visible": _observer_bool(measured["visibility"], f"{name}.visibility"),
        }
    if block_id == "state-management":
        state = measured["state_measurement"]
        before = _observer_int(state["data-elmos-before"], f"{name}.before")
        after = _observer_int(state["data-elmos-after"], f"{name}.after")
        return {
            "stateId": _observer_string(
                state["data-elmos-state-id"], f"{name}.state_id"
            ),
            "before": before,
            "after": after,
            "saturated": _observer_bool(
                state["data-elmos-saturated"], f"{name}.saturated"
            ),
        }
    if block_id == "action-event":
        outcome = measured["outcome_attributes"]
        events = measured["captured_events"]
        if not any(event.get("type") in {"click", "keydown", "submit"} for event in events):
            raise ValidationError(f"{name} lacks a native browser action event")
        return {
            "event": _observer_string(
                outcome["data-elmos-event-outcome"], f"{name}.event"
            ),
            "keyboardKey": _observer_string(
                outcome["data-elmos-keyboard-key"], f"{name}.keyboard_key"
            ),
            "handled": _observer_bool(
                outcome["data-elmos-handled"], f"{name}.handled"
            ),
            "action": _observer_string(
                outcome["data-elmos-action"], f"{name}.action"
            ),
        }
    if block_id == "effect-lifecycle":
        event = measured["ordered_events"][-1]
        return {
            "lifecycle": _observer_string(event["lifecycle"], f"{name}.lifecycle"),
            "effect": _observer_string(event["effect"], f"{name}.effect"),
            "executions": _observer_int(event["executions"], f"{name}.executions"),
            "cleanup": _observer_bool(event["cleanup"], f"{name}.cleanup"),
            "staleResponseIgnored": _observer_bool(
                event["stale_response_ignored"],
                f"{name}.stale_response_ignored",
            ),
        }
    if block_id == "form-binding-validation":
        control = measured["control"]
        validity = measured["validity_state"]
        return {
            "formId": _observer_string(control["form_id"], f"{name}.form_id"),
            "fieldId": _observer_string(control["field_id"], f"{name}.field_id"),
            "value": _observer_string(control["value"], f"{name}.value"),
            "submitted": _observer_bool(
                validity["submitted"], f"{name}.submitted"
            ),
            "valid": _observer_bool(validity["valid"], f"{name}.valid"),
            "errorCode": _observer_string(
                measured["error_dom"]["error_code"],
                f"{name}.error_code",
                nullable=True,
            ),
        }
    if block_id == "api-network":
        markers = measured["application_markers"]
        called = _observer_bool(markers["called"], f"{name}.called")
        canceled = _observer_bool(markers["canceled"], f"{name}.canceled")
        method = _observer_string(markers["method"], f"{name}.method")
        path = _observer_string(markers["path"], f"{name}.path")
        assert isinstance(method, str) and isinstance(path, str)
        matching_requests = [
            event
            for event in measured["network_events"]
            if event.get("kind") == "request"
            and event.get("method") == method
            and isinstance(event.get("url"), str)
            and re.sub(r"^https?://[^/]+", "", event["url"]).split("?", 1)[0]
            == path
        ]
        if called and not matching_requests:
            raise ValidationError(f"{name} API called marker lacks network request")
        if not called and matching_requests:
            raise ValidationError(f"{name} API not-called marker conflicts with network")
        if canceled and not any(
            event.get("kind") in {"requestfailed", "fixture-aborted"}
            for event in measured["network_events"]
        ):
            raise ValidationError(f"{name} canceled marker lacks abort trace")
        return {
            "operationId": _observer_string(
                markers["operation_id"], f"{name}.operation_id"
            ),
            "called": called,
            "method": method,
            "path": path,
            "outcome": _observer_string(markers["outcome"], f"{name}.outcome"),
            "canceled": canceled,
            "staleIgnored": _observer_bool(
                markers["stale_ignored"], f"{name}.stale_ignored"
            ),
            "cacheKey": _observer_string(
                markers["cache_key"], f"{name}.cache_key"
            ),
        }
    if block_id == "identity-permission":
        decision = measured["decision_attributes"]
        if not measured["adapter_events"]:
            raise ValidationError(f"{name} authority decision lacks adapter trace")
        return {
            "role": _observer_string(decision["role"], f"{name}.role"),
            "permission": _observer_string(
                decision["permission"], f"{name}.permission"
            ),
            "permissionGranted": _observer_bool(
                decision["permission_granted"], f"{name}.permission_granted"
            ),
            "tenantMatch": _observer_bool(
                decision["tenant_match"], f"{name}.tenant_match"
            ),
            "authorized": _observer_bool(
                decision["authorized"], f"{name}.authorized"
            ),
            "serverAuthorityRequired": _observer_bool(
                decision["server_authority_required"],
                f"{name}.server_authority_required",
            ),
        }
    if block_id == "rendering-hydration":
        state = measured["hydration_state"]
        return {
            "mode": _observer_string(state["mode"], f"{name}.mode"),
            "requested": _observer_string(state["requested"], f"{name}.requested"),
            "status": _observer_string(state["status"], f"{name}.status"),
            "duplicateEffects": _observer_bool(
                state["duplicate_effects"], f"{name}.duplicate_effects"
            ),
            "mismatchVisible": _observer_bool(
                state["mismatch_visible"], f"{name}.mismatch_visible"
            ),
        }
    if block_id == "accessibility-focus":
        state = measured["accessibility_state"]
        axe = measured["axe_results"]
        if not isinstance(axe.get("violations"), list):
            raise ValidationError(f"{name}.axe_results.violations is invalid")
        if any(
            isinstance(item, dict)
            and item.get("impact") in {"serious", "critical"}
            for item in axe["violations"]
        ):
            raise ValidationError(f"{name} contains serious accessibility violations")
        main_role = _observer_string(state["main_role"], f"{name}.main_role")
        heading_level = _observer_int(
            state["heading_level"], f"{name}.heading_level"
        )
        form_label = _observer_string(state["form_label"], f"{name}.form_label")
        error_role = _observer_string(
            state["error_role"], f"{name}.error_role", nullable=True
        )
        live_region = _observer_string(
            state["live_region"], f"{name}.live_region"
        )
        if (
            main_role != "main"
            or heading_level not in range(1, 7)
            or not form_label
            or error_role not in {None, "alert"}
            or live_region not in {"off", "polite", "assertive"}
        ):
            raise ValidationError(f"{name} actual accessibility DOM is incomplete")
        active_attributes = measured["active_element"]["attributes"]
        active_id = active_attributes.get("id")
        focus_target = (
            "query"
            if active_id == "elmos-query"
            else "result"
            if active_id == "elmos-result"
            else None
        )
        if state["focus_target"] != focus_target:
            raise ValidationError(f"{name} focus target conflicts with activeElement")
        keyboard_submit = any(
            isinstance(event, dict)
            and event.get("type") == "keydown"
            and event.get("key") == "Enter"
            and isinstance(event.get("target"), dict)
            and isinstance(event["target"].get("attributes"), dict)
            and isinstance(
                event["target"]["attributes"].get("data-run-scenario"), str
            )
            for event in measured["keyboard_events"]
        )
        if _observer_bool(
            state["keyboard_submit"], f"{name}.keyboard_submit"
        ) != keyboard_submit:
            raise ValidationError(f"{name} keyboard submit conflicts with event trace")
        aria_snapshot = measured["aria_snapshot"].lower()
        if "main" not in aria_snapshot or "heading" not in aria_snapshot:
            raise ValidationError(
                f"{name} accessibility tree lacks the observed main/heading"
            )
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
        translated = measured["translated_text"]
        theme = measured["computed_theme_tokens"]
        layout = measured["layout_measurement"]
        requested_locale = _observer_string(
            translated["requested_locale"], f"{name}.requested_locale"
        )
        requested_theme = _observer_string(
            theme["requested_theme"], f"{name}.requested_theme"
        )
        if (
            requested_locale != scenario_input.get("locale")
            or requested_theme != scenario_input.get("theme")
        ):
            raise ValidationError(
                f"{name} requested locale/theme are not frozen scenario input"
            )
        if (
            not isinstance(translated["text"], str)
            or not translated["text"].strip()
        ):
            raise ValidationError(f"{name} rendered translated text is empty")
        viewport_width = _observer_int(
            layout["viewport_width"], f"{name}.viewport_width"
        )
        if viewport_width != scenario_input.get("viewportWidth"):
            raise ValidationError(
                f"{name} actual viewport is not the frozen scenario viewport"
            )
        columns = _observer_int(layout["columns"], f"{name}.columns")
        if columns < 1 or columns != _css_grid_track_count(
            layout["computed_grid_template_columns"],
            f"{name}.computed_grid_template_columns",
        ):
            raise ValidationError(f"{name} grid column measurement is inconsistent")
        return {
            "requestedLocale": requested_locale,
            "locale": _observer_string(measured["html_lang"], f"{name}.locale"),
            "requestedTheme": requested_theme,
            "theme": _observer_string(theme["theme"], f"{name}.theme"),
            "viewportWidth": viewport_width,
            "columns": columns,
        }
    if block_id == "native-platform":
        semantics = measured["semantics"]
        if not measured["adapter_events"] or not measured["device_identity"]:
            raise ValidationError(f"{name} native result lacks adapter/device trace")
        return {
            "boundary": _observer_string(semantics["boundary"], f"{name}.boundary"),
            "lifecycle": _observer_string(
                measured["lifecycle"], f"{name}.lifecycle"
            ),
            "attempted": _observer_bool(
                semantics["attempted"], f"{name}.attempted"
            ),
            "permission": _observer_string(
                measured["permission"], f"{name}.permission"
            ),
            "available": _observer_bool(
                semantics["available"], f"{name}.available"
            ),
            "outcome": _observer_string(semantics["outcome"], f"{name}.outcome"),
            "recovery": _observer_string(
                semantics["recovery"], f"{name}.recovery"
            ),
        }
    raise ValidationError(f"{name} unknown block observer: {block_id}")


def validate_block_observer_trace_artifact_ref(
    value: Any,
    *,
    evidence_root: Path,
    profile_id: str,
    channel: str,
    scenario_id: str,
    block_id: str,
    expected_browser_ids: Sequence[str],
    name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve one unique, block-bound raw observer trace."""

    spec = BLOCK_OBSERVER_SPECS[block_id]
    ref = require_exact_keys(value, BLOCK_OBSERVER_TRACE_ARTIFACT_REF_KEYS, name)
    if (
        not isinstance(ref["artifact_id"], str)
        or not ref["artifact_id"]
        or ref["role"] != spec["trace_role"]
        or ref["profile_id"] != profile_id
        or ref["channel"] != channel
        or ref["scenario_id"] != scenario_id
        or ref["block_id"] != block_id
        or ref["observer_kind"] != spec["observer_kind"]
        or type(ref["byte_count"]) is not int
        or ref["byte_count"] < 1
    ):
        raise ValidationError(f"{name} block observer identity/role binding mismatch")
    digest = require_sha256(ref["sha256"], f"{name}.sha256")
    path = resolve_regular_file(evidence_root, ref["path"], f"{name}.path")
    data = path.read_bytes()
    if len(data) != ref["byte_count"] or sha256_bytes(data) != digest:
        raise ValidationError(f"{name} block observer artifact byte binding mismatch")
    artifact = require_exact_keys(
        read_json(path, name),
        {
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
        },
        name,
    )
    if (
        artifact["schema_version"] != SCHEMA_VERSION
        or artifact["kind"]
        != "frontend-interaction-block-observer-trace-artifact"
        or artifact["actual_source"] != "ALLOWLISTED_BLOCK_OBSERVER_CAPTURE"
        or artifact["role"] != ref["role"]
        or artifact["profile_id"] != profile_id
        or artifact["channel"] != channel
        or artifact["scenario_id"] != scenario_id
        or artifact["block_id"] != block_id
        or artifact["observer_kind"] != spec["observer_kind"]
    ):
        raise ValidationError(f"{name} block observer trace identity drift")
    capture = require_exact_keys(
        artifact["capture"],
        {"observer_contract", "measurement_surface", "browser_matrix"},
        f"{name}.capture",
    )
    matrix = capture["browser_matrix"]
    if (
        capture["observer_contract"] != BLOCK_OBSERVER_CONTRACT
        or capture["measurement_surface"] != spec["measurement_surface"]
        or not isinstance(matrix, list)
        or [row.get("browser_id") for row in matrix if isinstance(row, dict)]
        != list(expected_browser_ids)
        or len(matrix) != len(expected_browser_ids)
        or len(expected_browser_ids) != len(set(expected_browser_ids))
    ):
        raise ValidationError(f"{name} block observer browser matrix drift")
    for index, row in enumerate(matrix):
        row = require_exact_keys(
            row,
            {"browser_id", "measurement"},
            f"{name}.capture.browser_matrix[{index}]",
        )
        validate_block_observer_measurement(
            row["measurement"],
            block_id=block_id,
            name=f"{name}.capture.browser_matrix[{index}].measurement",
        )
    expected_id = digest_json(
        {
            "role": ref["role"],
            "profile_id": profile_id,
            "channel": channel,
            "scenario_id": scenario_id,
            "block_id": block_id,
            "observer_kind": spec["observer_kind"],
            "path": ref["path"],
            "sha256": digest,
            "byte_count": len(data),
        }
    )
    if ref["artifact_id"] != expected_id:
        raise ValidationError(f"{name} block observer artifact_id binding mismatch")
    return ref, artifact


def validate_runtime_artifact_ref(
    value: Any,
    *,
    evidence_root: Path,
    profile_id: str,
    channel: str,
    scenario_id: str,
    block_id: str,
    runner_kind: str,
    source_artifacts: Mapping[str, tuple[dict[str, Any], dict[str, Any]]] | None = None,
    expected_browser_ids: Sequence[str] = (),
    scenario_input: Mapping[str, Any] | None = None,
    name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ref = require_exact_keys(value, RUNTIME_ARTIFACT_REF_KEYS, name)
    if (
        not isinstance(ref["artifact_id"], str)
        or not ref["artifact_id"]
        or ref["role"] != "runtime-block-observation"
        or ref["profile_id"] != profile_id
        or ref["channel"] != channel
        or ref["scenario_id"] != scenario_id
        or ref["block_id"] != block_id
        or type(ref["byte_count"]) is not int
        or ref["byte_count"] < 1
    ):
        raise ValidationError(f"{name} identity/role binding mismatch")
    artifact_digest = require_sha256(ref["sha256"], f"{name}.sha256")
    actual_digest = require_sha256(ref["actual_digest"], f"{name}.actual_digest")
    path = resolve_regular_file(evidence_root, ref["path"], f"{name}.path")
    data = path.read_bytes()
    if len(data) != ref["byte_count"] or sha256_bytes(data) != artifact_digest:
        raise ValidationError(f"{name} artifact byte binding mismatch")
    artifact = require_exact_keys(
        read_json(path, name),
        {
            "schema_version",
            "kind",
            "actual_source",
            "profile_id",
            "channel",
            "scenario_id",
            "block_id",
            "provenance",
            "actual",
        },
        name,
    )
    actual_source = artifact["actual_source"]
    if actual_source in FORBIDDEN_RUNTIME_ACTUAL_SOURCES:
        raise ValidationError(
            f"{name} forbidden self-reported/model-derived actual source: "
            f"{actual_source}"
        )
    if (
        artifact["schema_version"] != SCHEMA_VERSION
        or artifact["kind"] != "frontend-interaction-runtime-block-observation"
        or actual_source != BLOCK_SPECIFIC_RUNTIME_ACTUAL_SOURCE
        or artifact["profile_id"] != profile_id
        or artifact["channel"] != channel
        or artifact["scenario_id"] != scenario_id
        or artifact["block_id"] != block_id
    ):
        raise ValidationError(f"{name} actual-source identity binding mismatch")
    provenance = require_exact_keys(
        artifact["provenance"],
        {
            "runner_kind",
            "observer_contract",
            "observer_kind",
            "measurement_surface",
            "observation_trace_ref",
            "supporting_trace_refs",
            "model_values_used_as_actual",
        },
        f"{name}.provenance",
    )
    spec = BLOCK_OBSERVER_SPECS[block_id]
    if (
        provenance["runner_kind"] != runner_kind
        or provenance["observer_contract"] != BLOCK_OBSERVER_CONTRACT
        or provenance["observer_kind"] != spec["observer_kind"]
        or provenance["measurement_surface"] != spec["measurement_surface"]
        or provenance["model_values_used_as_actual"] is not False
    ):
        raise ValidationError(f"{name} runtime provenance is invalid")
    if source_artifacts is None:
        raise ValidationError(f"{name} runtime source artifact registry is absent")
    if channel != "browser" or runner_kind != "PLAYWRIGHT_BROWSER_INTERACTION":
        raise ValidationError(
            f"{name} block-specific native/Flutter observer is not implemented"
        )
    observation_trace_ref = require_exact_keys(
        provenance["observation_trace_ref"],
        BLOCK_OBSERVER_TRACE_ARTIFACT_REF_KEYS,
        f"{name}.provenance.observation_trace_ref",
    )
    registered_observer = source_artifacts.get(observation_trace_ref["artifact_id"])
    if (
        registered_observer is None
        or registered_observer[0] != observation_trace_ref
        or observation_trace_ref["role"] != spec["trace_role"]
        or observation_trace_ref["block_id"] != block_id
        or observation_trace_ref["observer_kind"] != spec["observer_kind"]
    ):
        raise ValidationError(f"{name} block observer trace registry/role mismatch")
    validate_block_observer_trace_artifact_ref(
        observation_trace_ref,
        evidence_root=evidence_root,
        profile_id=profile_id,
        channel=channel,
        scenario_id=scenario_id,
        block_id=block_id,
        expected_browser_ids=expected_browser_ids,
        name=f"{name}.provenance.observation_trace_ref",
    )
    observer_capture = registered_observer[1]["capture"]
    derived_actuals = [
        derive_actual_from_block_measurement(
            block_id,
            row["measurement"],
            scenario_input=scenario_input,
            name=(
                f"{name}.provenance.observation_trace_ref.capture."
                f"browser_matrix[{index}].measurement"
            ),
        )
        for index, row in enumerate(observer_capture["browser_matrix"])
    ]
    if not derived_actuals or any(
        value != derived_actuals[0] for value in derived_actuals[1:]
    ):
        raise ValidationError(f"{name} cross-browser derived actual values differ")
    supporting_trace_refs = provenance["supporting_trace_refs"]
    expected_support_roles = tuple(spec["supporting_trace_roles"])
    if (
        not isinstance(supporting_trace_refs, list)
        or len(supporting_trace_refs) != len(expected_support_roles)
        or len(
            {
                ref.get("artifact_id")
                for ref in supporting_trace_refs
                if isinstance(ref, dict)
            }
        )
        != len(supporting_trace_refs)
    ):
        raise ValidationError(f"{name} supporting trace closure is invalid")
    for index, (trace_ref, expected_role) in enumerate(
        zip(supporting_trace_refs, expected_support_roles)
    ):
        trace_ref = require_exact_keys(
            trace_ref,
            RUNTIME_TRACE_ARTIFACT_REF_KEYS,
            f"{name}.provenance.supporting_trace_refs[{index}]",
        )
        artifact_id = trace_ref["artifact_id"]
        registered = source_artifacts.get(artifact_id)
        if (
            registered is None
            or registered[0] != trace_ref
            or trace_ref["role"] != expected_role
        ):
            raise ValidationError(
                f"{name} supporting trace registry/role mismatch"
            )
        if (
            trace_ref["profile_id"] != profile_id
            or trace_ref["channel"] != channel
            or trace_ref["scenario_id"] != scenario_id
        ):
            raise ValidationError(f"{name} supporting trace endpoint mismatch")
    actual = require_exact_keys(
        artifact["actual"], INTERACTION_BLOCK_ACTUAL_KEYS[block_id], f"{name}.actual"
    )
    if actual != derived_actuals[0]:
        raise ValidationError(f"{name} actual is not derived from its raw measurement")
    if digest_json(actual) != actual_digest:
        raise ValidationError(f"{name} actual JSON digest mismatch")
    expected_artifact_id = digest_json(
        {
            "role": ref["role"],
            "profile_id": profile_id,
            "channel": channel,
            "scenario_id": scenario_id,
            "block_id": block_id,
            "path": ref["path"],
            "sha256": artifact_digest,
            "byte_count": len(data),
            "actual_digest": actual_digest,
        }
    )
    if ref["artifact_id"] != expected_artifact_id:
        raise ValidationError(f"{name} artifact_id binding mismatch")
    return ref, artifact


def validate_runtime_result_manifest(
    value: Any,
    *,
    evidence_root: Path,
    profile_id: str,
    channel: str,
    scenario_ids: Sequence[str],
    runtime_source_artifact_ids: Sequence[str],
    observation_artifact_ids: Sequence[str],
    runtime_tool_digests: Sequence[str],
    prerequisite_execution_ids: Sequence[str],
    passed_block_ids: Sequence[str],
    not_run_block_ids: Sequence[str],
) -> dict[str, Any]:
    ref = require_exact_keys(
        value,
        RUNTIME_RESULT_MANIFEST_REF_KEYS,
        f"{profile_id}.{channel}.result_manifest",
    )
    if (
        ref["role"] != "runtime-result-manifest"
        or ref["profile_id"] != profile_id
        or ref["channel"] != channel
        or type(ref["byte_count"]) is not int
        or ref["byte_count"] < 1
    ):
        raise ValidationError(f"{profile_id}.{channel} result manifest ref drift")
    path = resolve_regular_file(
        evidence_root, ref["path"], f"{profile_id}.{channel}.result_manifest.path"
    )
    data = path.read_bytes()
    sha = require_sha256(
        ref["sha256"], f"{profile_id}.{channel}.result_manifest.sha256"
    )
    if len(data) != ref["byte_count"] or sha256_bytes(data) != sha:
        raise ValidationError(f"{profile_id}.{channel} result manifest bytes drift")
    manifest = require_exact_keys(
        read_json(path, f"{profile_id}.{channel} result manifest"),
        {
            "schema_version",
            "kind",
            "profile_id",
            "channel",
            "scenario_ids",
            "semantic_block_ids",
            "runtime_source_artifact_ids",
            "runtime_source_artifact_count",
            "observation_artifact_ids",
            "observation_artifact_count",
            "passed_block_ids",
            "not_run_block_ids",
            "runtime_tool_digests",
            "prerequisite_execution_ids",
        },
        f"{profile_id}.{channel} result manifest",
    )
    if manifest != {
        "schema_version": SCHEMA_VERSION,
        "kind": "frontend-interaction-runtime-result-manifest",
        "profile_id": profile_id,
        "channel": channel,
        "scenario_ids": list(scenario_ids),
        "semantic_block_ids": list(INTERACTION_BLOCK_IDS),
        "runtime_source_artifact_ids": list(runtime_source_artifact_ids),
        "runtime_source_artifact_count": len(runtime_source_artifact_ids),
        "observation_artifact_ids": list(observation_artifact_ids),
        "observation_artifact_count": len(observation_artifact_ids),
        "passed_block_ids": list(passed_block_ids),
        "not_run_block_ids": list(not_run_block_ids),
        "runtime_tool_digests": list(runtime_tool_digests),
        "prerequisite_execution_ids": list(prerequisite_execution_ids),
    }:
        raise ValidationError(
            f"{profile_id}.{channel} result manifest binding mismatch"
        )
    manifest_digest = require_sha256(
        ref["manifest_digest"],
        f"{profile_id}.{channel}.result_manifest.manifest_digest",
    )
    if manifest_digest != digest_json(manifest):
        raise ValidationError(f"{profile_id}.{channel} result manifest digest drift")
    expected_id = digest_json(
        {
            "role": ref["role"],
            "profile_id": profile_id,
            "channel": channel,
            "path": ref["path"],
            "sha256": sha,
            "byte_count": len(data),
            "manifest_digest": manifest_digest,
        }
    )
    if ref["artifact_id"] != expected_id:
        raise ValidationError(f"{profile_id}.{channel} result manifest ID drift")
    return ref


def validate_runtime_tool(value: Any, name: str) -> dict[str, Any]:
    tool = require_exact_keys(
        value,
        {
            "role",
            "path",
            "realpath",
            "sha256",
            "byte_count",
            "version",
            "package_closure_digest",
        },
        name,
    )
    if (
        not isinstance(tool["role"], str)
        or not tool["role"]
        or not isinstance(tool["path"], str)
        or not Path(tool["path"]).is_absolute()
        or not isinstance(tool["realpath"], str)
        or not Path(tool["realpath"]).is_absolute()
        or type(tool["byte_count"]) is not int
        or tool["byte_count"] < 1
        or not isinstance(tool["version"], str)
        or not tool["version"]
    ):
        raise ValidationError(f"{name} identity is invalid")
    digest = require_sha256(tool["sha256"], f"{name}.sha256")
    require_sha256(tool["package_closure_digest"], f"{name}.package_closure_digest")
    try:
        path = Path(tool["path"]).resolve(strict=True)
        data = path.read_bytes()
    except (OSError, RuntimeError) as error:
        raise ValidationError(f"{name} is unavailable: {error}") from error
    if (
        str(path) != tool["realpath"]
        or len(data) != tool["byte_count"]
        or sha256_bytes(data) != digest
        or not os.access(path, os.X_OK)
    ):
        raise ValidationError(f"{name} byte identity drift")
    return tool


def validate_node_browser_matrix_discovery(
    value: Any, runtime_tools: Sequence[Mapping[str, Any]], name: str
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValidationError(f"{name} is absent")
    rows = [
        item
        for item in value
        if isinstance(item, dict) and item.get("kind") == "EXACT_BROWSER_MATRIX"
    ]
    if len(rows) != 1:
        raise ValidationError(f"{name} exact browser matrix closure drift")
    matrix = require_exact_keys(
        rows[0],
        {"kind", "policy_id", "browser_matrix", "cross_browser"},
        f"{name}.EXACT_BROWSER_MATRIX",
    )
    browser_rows = matrix["browser_matrix"]
    expected = (("google-chrome", "chromium"), ("mozilla-firefox", "firefox"))
    if (
        matrix["policy_id"] != "node-web-chromium-firefox-v1"
        or matrix["cross_browser"] is not True
        or not isinstance(browser_rows, list)
        or len(browser_rows) != len(expected)
    ):
        raise ValidationError(f"{name} exact browser matrix policy drift")
    tools_by_role = {tool.get("role"): tool for tool in runtime_tools}
    browser_ids: list[str] = []
    for index, ((expected_id, expected_engine), row) in enumerate(
        zip(expected, browser_rows)
    ):
        row = require_exact_keys(
            row,
            {
                "browser_id",
                "engine",
                "version",
                "executable_sha256",
            },
            f"{name}.EXACT_BROWSER_MATRIX.browser_matrix[{index}]",
        )
        if (
            row["browser_id"] != expected_id
            or row["engine"] != expected_engine
            or not isinstance(row["version"], str)
            or not row["version"]
            or tools_by_role.get(f"browser-{expected_engine}", {}).get("sha256")
            != require_sha256(
                row["executable_sha256"],
                f"{name}.EXACT_BROWSER_MATRIX.browser_matrix[{index}].sha256",
            )
        ):
            raise ValidationError(f"{name} exact browser matrix row drift")
        browser_ids.append(expected_id)
    return tuple(browser_ids)


def is_block_specific_runtime_partial(value: Mapping[str, Any]) -> bool:
    """Return whether a browser record carries a persisted partial closure."""

    return (
        value.get("status") == "NOT_RUN"
        and value.get("channel") == "browser"
        and value.get("runner_kind") == "PLAYWRIGHT_BROWSER_INTERACTION"
        and value.get("reason") == BLOCK_SPECIFIC_RUNTIME_PARTIAL_REASON
    )


def validate_runtime_channel_record(
    profile_id: str,
    channel: str,
    value: Mapping[str, Any],
    *,
    scenario_ids: Sequence[str],
    scenario_manifest: Sequence[Mapping[str, Any]] | None = None,
    runtime_model_oracle_findings: Sequence[Mapping[str, Any]] = (),
    evidence_root: Path | None = None,
    execution_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate actual-derived runtime closure for one exact channel.

    PASSED is intentionally expensive: the record must bind a real runner,
    build, startup, journey execution, every campaign scenario, every semantic
    block, and raw artifacts.  Static DOM or model output cannot satisfy it.
    """

    if channel not in RUNTIME_CHANNELS:
        raise ValidationError(f"unknown runtime channel: {channel}")
    record = require_exact_keys(
        dict(value),
        RUNTIME_CHANNEL_RECORD_KEYS,
        f"{profile_id}.{channel} runtime record",
    )
    status = record.get("status")
    if status not in RUNTIME_STATUSES:
        raise ValidationError(f"{profile_id}.{channel} runtime status is invalid")
    applicable = runtime_channel_applicable(profile_id, channel)
    if record.get("channel") != channel or record.get("required") is not applicable:
        raise ValidationError(f"{profile_id}.{channel} applicability binding mismatch")
    if applicable and status == "NOT_APPLICABLE":
        raise ValidationError(f"{profile_id}.{channel} cannot be NOT_APPLICABLE")
    if not applicable and status != "NOT_APPLICABLE":
        raise ValidationError(
            f"{profile_id}.{channel} must be derived as NOT_APPLICABLE"
        )
    if record.get("model_values_used_as_actual") is not False:
        raise ValidationError(
            f"{profile_id}.{channel} model output cannot be runtime actual"
        )
    partial_closure = is_block_specific_runtime_partial(record)
    if status != "PASSED" and not partial_closure:
        return record
    if status == "PASSED" and record.get("reason") is not None:
        raise ValidationError(f"{profile_id}.{channel} PASS cannot carry a reason")

    if runtime_model_oracle_findings:
        raise ValidationError(
            f"{profile_id}.{channel} precomputed model oracle consumption blocks runtime PASS"
        )

    if evidence_root is None:
        raise ValidationError(
            f"{profile_id}.{channel} runtime evidence root is required for validated closure"
        )
    evidence_root = evidence_root.resolve()
    if execution_policy is None:
        raise ValidationError(
            f"{profile_id}.{channel} runner-owned execution policy is required for validated closure"
        )
    policy = require_exact_keys(
        dict(execution_policy),
        {
            "schema_version",
            "kind",
            "profile_id",
            "channel",
            "runner_kind",
            "phases",
            "runtime_tools",
        },
        f"{profile_id}.{channel} execution policy",
    )
    if (
        policy["schema_version"] != SCHEMA_VERSION
        or policy["kind"] != "frontend-interaction-runtime-execution-policy"
        or policy["profile_id"] != profile_id
        or policy["channel"] != channel
        or policy["runner_kind"] != record["runner_kind"]
        or record["execution_policy_digest"] != digest_json(policy)
    ):
        raise ValidationError(f"{profile_id}.{channel} execution policy drift")
    phases = require_exact_keys(
        policy["phases"],
        {"BUILD", "STARTUP", "JOURNEY"},
        f"{profile_id}.{channel} execution policy phases",
    )
    runtime_tools = record["runtime_tools"]
    if not isinstance(runtime_tools, list) or not runtime_tools:
        raise ValidationError(f"{profile_id}.{channel} runtime tool closure is absent")
    validated_runtime_tools = [
        validate_runtime_tool(item, f"{profile_id}.{channel}.runtime_tools[{index}]")
        for index, item in enumerate(runtime_tools)
    ]
    if validated_runtime_tools != policy["runtime_tools"]:
        raise ValidationError(f"{profile_id}.{channel} runtime tool policy drift")
    expected_browser_ids: tuple[str, ...] = ()
    if record["runner_kind"] == "PLAYWRIGHT_BROWSER_INTERACTION":
        expected_browser_ids = validate_node_browser_matrix_discovery(
            record["tool_discovery"],
            validated_runtime_tools,
            f"{profile_id}.{channel}.tool_discovery",
        )

    if not scenario_ids or len(scenario_ids) != len(set(scenario_ids)):
        raise ValidationError("runtime scenario manifest is empty or duplicated")
    if scenario_manifest is None:
        raise ValidationError(
            f"{profile_id}.{channel} frozen scenario inputs are required for PASS"
        )
    if len(scenario_manifest) != len(scenario_ids):
        raise ValidationError(
            f"{profile_id}.{channel} frozen scenario input closure drift"
        )
    normalized_scenarios: list[Mapping[str, Any]] = []
    for index, scenario in enumerate(scenario_manifest):
        if (
            not isinstance(scenario, Mapping)
            or set(scenario) != {"scenario_id", "input"}
            or scenario.get("scenario_id") != scenario_ids[index]
            or not isinstance(scenario.get("input"), Mapping)
        ):
            raise ValidationError(
                f"{profile_id}.{channel} frozen scenario[{index}] binding drift"
            )
        normalized_scenarios.append(scenario)
    if len(normalized_scenarios) != len(scenario_ids):
        raise ValidationError(
            f"{profile_id}.{channel} frozen scenario input closure drift"
        )
    scenario_inputs = {
        scenario["scenario_id"]: scenario["input"]
        for scenario in normalized_scenarios
    }
    if not isinstance(record.get("runner_kind"), str) or not record["runner_kind"]:
        raise ValidationError(f"{profile_id}.{channel} runner identity is absent")
    manifest_digest = require_sha256(
        record.get("scenario_manifest_digest"),
        f"{profile_id}.{channel}.scenario_manifest_digest",
    )
    if manifest_digest != digest_json(list(scenario_ids)):
        raise ValidationError(f"{profile_id}.{channel} scenario manifest drift")
    scenarios = record.get("scenarios")
    if not isinstance(scenarios, list) or record.get("scenario_count") != len(
        scenario_ids
    ):
        raise ValidationError(f"{profile_id}.{channel} scenario closure is absent")
    observed_ids = [
        item.get("scenario_id") if isinstance(item, dict) else None
        for item in scenarios
    ]
    if observed_ids != list(scenario_ids):
        raise ValidationError(f"{profile_id}.{channel} scenario order/closure drift")
    artifacts = record.get("raw_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValidationError(f"{profile_id}.{channel} raw artifacts are absent")
    raw_by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(artifacts):
        ref = require_exact_keys(
            raw,
            RUNTIME_ARTIFACT_REF_KEYS,
            f"{profile_id}.{channel}.raw_artifacts[{index}]",
        )
        artifact_id = ref.get("artifact_id")
        if not isinstance(artifact_id, str) or artifact_id in raw_by_id:
            raise ValidationError(
                f"{profile_id}.{channel} raw artifact IDs are invalid or duplicate"
            )
        raw_by_id[artifact_id] = ref
    artifact_ids = set(raw_by_id)

    source_artifacts = record.get("runtime_source_artifacts")
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValidationError(
            f"{profile_id}.{channel} runtime source artifacts are absent"
        )
    source_by_id: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    scenario_id_set = set(scenario_ids)
    for index, source_ref in enumerate(source_artifacts):
        source_name = f"{profile_id}.{channel}.runtime_source_artifacts[{index}]"
        if not isinstance(source_ref, dict):
            raise ValidationError(f"{source_name} is invalid")
        source_scenario_id = source_ref.get("scenario_id")
        if source_scenario_id not in scenario_id_set:
            raise ValidationError(
                f"{profile_id}.{channel} runtime trace scenario is outside the manifest"
            )
        if set(source_ref) == RUNTIME_TRACE_ARTIFACT_REF_KEYS:
            validated_ref, trace = validate_runtime_trace_artifact_ref(
                source_ref,
                evidence_root=evidence_root,
                profile_id=profile_id,
                channel=channel,
                scenario_id=source_scenario_id,
                name=source_name,
            )
        elif set(source_ref) == BLOCK_OBSERVER_TRACE_ARTIFACT_REF_KEYS:
            source_block_id = source_ref.get("block_id")
            if source_block_id not in INTERACTION_BLOCK_IDS:
                raise ValidationError(f"{source_name}.block_id is invalid")
            validated_ref, trace = validate_block_observer_trace_artifact_ref(
                source_ref,
                evidence_root=evidence_root,
                profile_id=profile_id,
                channel=channel,
                scenario_id=source_scenario_id,
                block_id=source_block_id,
                expected_browser_ids=expected_browser_ids,
                name=source_name,
            )
        else:
            raise ValidationError(f"{source_name} fields are not exact")
        source_artifact_id = validated_ref["artifact_id"]
        if source_artifact_id in source_by_id:
            raise ValidationError(
                f"{profile_id}.{channel} runtime source artifact IDs are duplicated"
            )
        source_by_id[source_artifact_id] = (validated_ref, trace)
    source_artifact_ids = list(source_by_id)

    used_artifact_ids: list[str] = []
    used_source_artifact_ids: set[str] = set()
    used_block_observer_trace_ids: list[str] = []
    per_block_ids = {block_id: [] for block_id in INTERACTION_BLOCK_IDS}
    expected_observed_block_ids: tuple[str, ...] | None = None
    expected_not_run_block_ids: tuple[str, ...] | None = None
    expected_not_run_reasons: dict[str, str] = {}
    for scenario in scenarios:
        scenario = require_exact_keys(
            scenario,
            {
                "scenario_id",
                "status",
                "reason",
                "block_statuses",
                "block_observation_refs",
            },
            f"{profile_id}.{channel} scenario",
        )
        scenario_id = scenario["scenario_id"]
        if partial_closure:
            if (
                scenario["status"] != "NOT_RUN"
                or scenario["reason"] != BLOCK_SPECIFIC_RUNTIME_PARTIAL_REASON
            ):
                raise ValidationError(
                    f"{profile_id}.{channel}.{scenario_id} partial status drift"
                )
        elif scenario["status"] != "PASSED" or scenario["reason"] is not None:
            raise ValidationError(f"{profile_id}.{channel}.{scenario_id} did not pass")
        block_statuses = scenario["block_statuses"]
        if not isinstance(block_statuses, dict) or tuple(block_statuses) != (
            INTERACTION_BLOCK_IDS
        ):
            raise ValidationError(
                f"{profile_id}.{channel}.{scenario_id} block status closure drift"
            )
        for block_id, block_status in block_statuses.items():
            block_status = require_exact_keys(
                block_status,
                {"status", "reason"},
                f"{profile_id}.{channel}.{scenario_id}.{block_id}.status",
            )
            block_status_value = block_status["status"]
            if block_status_value not in {"PASSED", "NOT_RUN"} or (
                block_status_value == "PASSED"
                and block_status["reason"] is not None
            ) or (
                block_status_value == "NOT_RUN"
                and (
                    not isinstance(block_status["reason"], str)
                    or not block_status["reason"]
                )
            ) or (
                partial_closure
                and block_id in WEB_BROWSER_MANDATORY_NOT_RUN_BLOCK_IDS
                and block_status_value != "NOT_RUN"
            ):
                raise ValidationError(
                    f"{profile_id}.{channel}.{scenario_id}.{block_id} status drift"
                )
        observed_block_ids = tuple(
            block_id
            for block_id in INTERACTION_BLOCK_IDS
            if block_statuses[block_id]["status"] == "PASSED"
        )
        not_run_block_ids = tuple(
            block_id
            for block_id in INTERACTION_BLOCK_IDS
            if block_statuses[block_id]["status"] == "NOT_RUN"
        )
        if partial_closure and not not_run_block_ids:
            raise ValidationError(
                f"{profile_id}.{channel}.{scenario_id} partial closure has no NOT_RUN block"
            )
        if not partial_closure and not_run_block_ids:
            raise ValidationError(
                f"{profile_id}.{channel}.{scenario_id} PASS contains NOT_RUN blocks"
            )
        if expected_observed_block_ids is None:
            expected_observed_block_ids = observed_block_ids
            expected_not_run_block_ids = not_run_block_ids
            expected_not_run_reasons = {
                block_id: block_statuses[block_id]["reason"]
                for block_id in not_run_block_ids
            }
        elif (
            observed_block_ids != expected_observed_block_ids
            or not_run_block_ids != expected_not_run_block_ids
            or any(
                block_statuses[block_id]["reason"]
                != expected_not_run_reasons[block_id]
                for block_id in not_run_block_ids
            )
        ):
            raise ValidationError(
                f"{profile_id}.{channel}.{scenario_id} block capability contract drift"
            )
        observations = scenario["block_observation_refs"]
        if not isinstance(observations, dict) or tuple(observations) != (
            observed_block_ids
        ):
            raise ValidationError(
                f"{profile_id}.{channel}.{scenario_id} block closure drift"
            )
        for block_id, raw_ref in observations.items():
            ref, observation = validate_runtime_artifact_ref(
                raw_ref,
                evidence_root=evidence_root,
                profile_id=profile_id,
                channel=channel,
                scenario_id=scenario_id,
                block_id=block_id,
                runner_kind=record["runner_kind"],
                source_artifacts=source_by_id,
                expected_browser_ids=expected_browser_ids,
                scenario_input=scenario_inputs[scenario_id],
                name=f"{profile_id}.{channel}.{scenario_id}.{block_id}",
            )
            provenance = observation["provenance"]
            observation_trace_id = provenance["observation_trace_ref"]["artifact_id"]
            used_block_observer_trace_ids.append(observation_trace_id)
            used_source_artifact_ids.add(observation_trace_id)
            used_source_artifact_ids.update(
                trace_ref["artifact_id"]
                for trace_ref in provenance["supporting_trace_refs"]
            )
            artifact_id = ref["artifact_id"]
            if raw_by_id.get(artifact_id) != ref:
                raise ValidationError(
                    f"{profile_id}.{channel}.{scenario_id}.{block_id} raw artifact registry mismatch"
                )
            used_artifact_ids.append(artifact_id)
            per_block_ids[block_id].append(artifact_id)
    if len(used_artifact_ids) != len(set(used_artifact_ids)):
        raise ValidationError(f"{profile_id}.{channel} raw artifact reuse is forbidden")
    if len(used_block_observer_trace_ids) != len(
        set(used_block_observer_trace_ids)
    ):
        raise ValidationError(
            f"{profile_id}.{channel} block observer trace reuse is forbidden"
        )
    if set(used_artifact_ids) != artifact_ids:
        raise ValidationError(
            f"{profile_id}.{channel} raw artifacts are unused or unreferenced"
        )
    if expected_observed_block_ids is None or expected_not_run_block_ids is None:
        raise ValidationError(f"{profile_id}.{channel} block capability closure is absent")
    diagnostic_source_artifact_ids = {
        artifact_id
        for artifact_id, (ref, _artifact) in source_by_id.items()
        if partial_closure
        and "api-network" in expected_not_run_block_ids
        and ref["role"] == "browser-network-trace"
    }
    if partial_closure and "api-network" in expected_not_run_block_ids:
        diagnostic_scenarios = {
            source_by_id[artifact_id][0]["scenario_id"]
            for artifact_id in diagnostic_source_artifact_ids
        }
        if diagnostic_scenarios != set(scenario_ids) or len(
            diagnostic_source_artifact_ids
        ) != len(scenario_ids):
            raise ValidationError(
                f"{profile_id}.{channel} API network diagnostic closure drift"
            )
    if used_source_artifact_ids | diagnostic_source_artifact_ids != set(
        source_artifact_ids
    ):
        raise ValidationError(
            f"{profile_id}.{channel} runtime source artifacts are unused or unreferenced"
        )
    semantic_blocks = record.get("semantic_blocks")
    if not isinstance(semantic_blocks, dict) or tuple(semantic_blocks) != (
        INTERACTION_BLOCK_IDS
    ):
        raise ValidationError(f"{profile_id}.{channel} semantic block closure drift")
    for block_id, block in semantic_blocks.items():
        block = require_exact_keys(
            block,
            {"status", "reason", "observation_refs", "observation_digest"},
            f"{profile_id}.{channel}.{block_id} aggregate",
        )
        expected_status = (
            "PASSED" if block_id in expected_observed_block_ids else "NOT_RUN"
        )
        if block["status"] != expected_status or (
            expected_status == "PASSED" and block["reason"] is not None
        ) or (
            expected_status == "NOT_RUN"
            and (
                block["reason"] != expected_not_run_reasons.get(block_id)
                or not isinstance(block["reason"], str)
                or not block["reason"]
            )
        ):
            raise ValidationError(f"{profile_id}.{channel}.{block_id} status drift")
        refs = block["observation_refs"]
        if refs != per_block_ids[block_id]:
            raise ValidationError(
                f"{profile_id}.{channel}.{block_id} observation refs are incomplete"
            )
        aggregate_digest = require_sha256(
            block["observation_digest"],
            f"{profile_id}.{channel}.{block_id}.observation_digest",
        )
        if aggregate_digest != digest_json(refs):
            raise ValidationError(
                f"{profile_id}.{channel}.{block_id} observation digest mismatch"
            )
    build = validate_runtime_execution(
        record["build_execution"],
        f"{profile_id}.{channel}.build_execution",
        "BUILD",
        artifact_ids,
        phases["BUILD"],
    )
    startup = validate_runtime_execution(
        record["startup_execution"],
        f"{profile_id}.{channel}.startup_execution",
        "STARTUP",
        artifact_ids,
        phases["STARTUP"],
    )
    if build["artifact_refs"] or startup["artifact_refs"]:
        raise ValidationError(
            f"{profile_id}.{channel} prerequisite executions cannot claim journey artifacts"
        )
    runtime_tool_digests = [tool["sha256"] for tool in validated_runtime_tools]
    result_manifest = validate_runtime_result_manifest(
        record["result_manifest"],
        evidence_root=evidence_root,
        profile_id=profile_id,
        channel=channel,
        scenario_ids=scenario_ids,
        runtime_source_artifact_ids=source_artifact_ids,
        observation_artifact_ids=used_artifact_ids,
        runtime_tool_digests=runtime_tool_digests,
        prerequisite_execution_ids=[build["execution_id"], startup["execution_id"]],
        passed_block_ids=expected_observed_block_ids,
        not_run_block_ids=expected_not_run_block_ids,
    )
    all_artifact_ids = (
        artifact_ids | set(source_artifact_ids) | {result_manifest["artifact_id"]}
    )
    journey = validate_runtime_execution(
        record["journey_execution"],
        f"{profile_id}.{channel}.journey_execution",
        "JOURNEY",
        all_artifact_ids,
        phases["JOURNEY"],
    )
    expected_journey_refs = [
        *source_artifact_ids,
        *used_artifact_ids,
        result_manifest["artifact_id"],
    ]
    if journey["artifact_refs"] != expected_journey_refs:
        raise ValidationError(
            f"{profile_id}.{channel} journey execution artifact closure drift"
        )
    if (
        record["runner_kind"] == "PLAYWRIGHT_BROWSER_INTERACTION"
        and len(journey["argv"]) == 4
        and journey["argv"][1] == str(PLAYWRIGHT_HELPER_PATH.resolve())
    ):
        try:
            journey_summary = json.loads(journey["stdout"]["text"])
        except json.JSONDecodeError as error:
            raise ValidationError(
                f"{profile_id}.{channel} Playwright journey stdout is not JSON"
            ) from error
        journey_summary = require_exact_keys(
            journey_summary,
            {"output", "sha256", "byte_count", "status"},
            f"{profile_id}.{channel} Playwright journey stdout",
        )
        expected_journey_result_status = "NOT_RUN" if partial_closure else "PASSED"
        if (
            journey_summary["status"] != expected_journey_result_status
            or journey_summary["output"] != journey["argv"][-1]
            or type(journey_summary["byte_count"]) is not int
            or journey_summary["byte_count"] < 1
        ):
            raise ValidationError(
                f"{profile_id}.{channel} Playwright journey result binding drift"
            )
        raw_result_path = Path(journey_summary["output"])
        try:
            raw_result_path.resolve(strict=True).relative_to(evidence_root)
            raw_result_bytes = raw_result_path.read_bytes()
        except (OSError, RuntimeError, ValueError) as error:
            raise ValidationError(
                f"{profile_id}.{channel} Playwright raw result is unavailable"
            ) from error
        if (
            len(raw_result_bytes) != journey_summary["byte_count"]
            or sha256_bytes(raw_result_bytes)
            != require_sha256(
                journey_summary["sha256"],
                f"{profile_id}.{channel} Playwright journey raw sha256",
            )
        ):
            raise ValidationError(
                f"{profile_id}.{channel} Playwright raw result bytes drift"
            )
    elif record["runner_kind"] == "FLUTTER_DRIVE_SEMANTICS":
        if profile_id != "flutter" or channel != "browser":
            raise ValidationError("Flutter drive runner endpoint drift")
        discovery = record["tool_discovery"]
        if not isinstance(discovery, list):
            raise ValidationError("Flutter drive tool discovery is absent")
        raw_rows = [
            item
            for item in discovery
            if isinstance(item, dict)
            and item.get("kind") == "FLUTTER_DRIVE_RAW_RESULT"
        ]
        matrix_rows = [
            item
            for item in discovery
            if isinstance(item, dict) and item.get("kind") == "EXACT_BROWSER_MATRIX"
        ]
        if len(raw_rows) != 1 or len(matrix_rows) != 1:
            raise ValidationError("Flutter drive raw/matrix discovery closure drift")
        raw_row = require_exact_keys(
            raw_rows[0],
            {"kind", "path", "sha256", "byte_count"},
            "Flutter drive raw result discovery",
        )
        raw_path = Path(raw_row["path"])
        try:
            raw_path.resolve(strict=True).relative_to(evidence_root)
            raw_bytes = raw_path.read_bytes()
        except (OSError, RuntimeError, ValueError) as error:
            raise ValidationError("Flutter drive raw result is unavailable") from error
        if (
            type(raw_row["byte_count"]) is not int
            or raw_row["byte_count"] < 1
            or len(raw_bytes) != raw_row["byte_count"]
            or sha256_bytes(raw_bytes)
            != require_sha256(raw_row["sha256"], "Flutter drive raw result sha256")
        ):
            raise ValidationError("Flutter drive raw result bytes drift")
        matrix = require_exact_keys(
            matrix_rows[0],
            {
                "kind",
                "policy_id",
                "browser_matrix",
                "cross_browser",
                "capability_scope",
            },
            "Flutter exact browser matrix",
        )
        browser_matrix = matrix["browser_matrix"]
        if not isinstance(browser_matrix, list) or len(browser_matrix) != 1:
            raise ValidationError("Flutter exact browser matrix row closure drift")
        browser = require_exact_keys(
            browser_matrix[0],
            {
                "browser_id",
                "engine",
                "version",
                "executable_sha256",
                "driver_version",
                "driver_sha256",
            },
            "Flutter exact browser matrix row",
        )
        tools_by_role = {tool["role"]: tool for tool in validated_runtime_tools}
        if (
            matrix["policy_id"] != "flutter-web-cft-chrome-drive-v1"
            or matrix["cross_browser"] is not False
            or matrix["capability_scope"] != "flutter-web-chrome-drive-only"
            or browser["browser_id"] != "cft-chrome"
            or browser["engine"] != "chromium"
            or browser["version"] != LOCKED_FLUTTER_WEB_CFT_VERSION
            or browser["driver_version"] != LOCKED_FLUTTER_WEB_CFT_VERSION
            or tools_by_role.get("flutter-cft-chrome", {}).get("sha256")
            != browser["executable_sha256"]
            or tools_by_role.get("flutter-cft-chromedriver", {}).get("sha256")
            != browser["driver_sha256"]
        ):
            raise ValidationError("Flutter exact Chrome/driver matrix drift")
    else:
        expected_stdout = (
            canonical_json(
                {
                    "result_manifest_artifact_id": result_manifest["artifact_id"],
                    "result_manifest_sha256": result_manifest["sha256"],
                }
            )
            + "\n"
        )
        if journey["stdout"]["text"] != expected_stdout:
            raise ValidationError(
                f"{profile_id}.{channel} journey stdout/result manifest backlink drift"
            )
    return record


EXPECTED_NODE_PACKAGES: dict[str, dict[str, Any]] = {
    "angular": {
        "scripts": {
            "start": "ng serve",
            "build": "ng build",
            "test": "ng build --configuration development",
        },
        "dependencies": {
            "@angular/common": "22.0.8",
            "@angular/compiler": "22.0.8",
            "@angular/core": "22.0.8",
            "@angular/platform-browser": "22.0.8",
            "@angular/router": "22.0.8",
            "rxjs": "7.8.2",
            "tslib": "2.8.1",
            "zone.js": "0.16.2",
        },
        "devDependencies": {
            "@angular/build": "22.0.8",
            "@angular/cli": "22.0.8",
            "@angular/compiler-cli": "22.0.8",
            "typescript": "6.0.3",
        },
        "commands": [("test",), ("build",)],
    },
    "jquery": {
        "scripts": {
            "dev": "vite",
            "build": "tsc -b && vite build",
            "test": "vitest run",
        },
        "dependencies": {"jquery": "4.0.0"},
        "devDependencies": {
            "@types/jquery": "4.0.1",
            "typescript": "7.0.2",
            "vite": "8.1.5",
            "vitest": "4.1.10",
        },
        "commands": [("test",), ("build",)],
    },
    "react": {
        "scripts": {
            "dev": "vite",
            "build": "tsc -b && vite build",
            "test": "vitest run",
        },
        "dependencies": {
            "react": "19.2.8",
            "react-dom": "19.2.8",
            "react-router-dom": "7.18.1",
        },
        "devDependencies": {
            "@types/react": "19.2.17",
            "@types/react-dom": "19.2.3",
            "@vitejs/plugin-react": "6.0.4",
            "typescript": "7.0.2",
            "vite": "8.1.5",
            "vitest": "4.1.10",
        },
        "commands": [("test",), ("build",)],
    },
    "react-native": {
        "scripts": {
            "start": "expo start",
            "android": "expo run:android",
            "ios": "expo run:ios",
            "web": "expo start --web",
            "export:web": "expo export --platform web",
            "typecheck": "tsc --noEmit",
        },
        "dependencies": {
            "@expo/metro-runtime": "57.0.7",
            "@react-navigation/native": "7.3.14",
            "@react-navigation/native-stack": "7.18.6",
            "expo": "57.0.8",
            "expo-status-bar": "57.0.1",
            "react": "19.2.3",
            "react-dom": "19.2.3",
            "react-native": "0.86.0",
            "react-native-safe-area-context": "5.8.0",
            "react-native-screens": "4.26.2",
            "react-native-web": "0.21.2",
        },
        "devDependencies": {"@types/react": "19.2.2", "typescript": "6.0.3"},
        "commands": [("typecheck",), ("export:web",)],
    },
    "svelte": {
        "scripts": {
            "dev": "vite",
            "build": "svelte-check && vite build",
            "test": "vitest run",
        },
        "dependencies": {"svelte": "5.56.8"},
        "devDependencies": {
            "@sveltejs/vite-plugin-svelte": "7.2.0",
            "svelte-check": "4.4.5",
            "typescript": "6.0.3",
            "vite": "8.1.5",
            "vitest": "4.1.10",
        },
        "commands": [("test",), ("build",)],
    },
    "vue2": {
        "scripts": {"dev": "vite", "build": "vite build", "test": "vitest run"},
        "dependencies": {"vue": "2.7.16", "vue-router": "3.6.5"},
        "devDependencies": {
            "@vitejs/plugin-vue2": "2.3.4",
            "vite": "7.3.6",
            "vitest": "4.1.10",
        },
        "commands": [("test",), ("build",)],
    },
    "vue3": {
        "scripts": {
            "dev": "vite",
            "build": "vue-tsc --noEmit && vite build",
            "test": "vitest run",
        },
        "dependencies": {"pinia": "4.0.2", "vue": "3.5.40", "vue-router": "4.6.4"},
        "devDependencies": {
            "@vitejs/plugin-vue": "6.0.8",
            "typescript": "6.0.3",
            "vite": "8.1.5",
            "vitest": "4.1.10",
            "vue-tsc": "3.2.5",
        },
        "commands": [("test",), ("build",)],
    },
}

SAFE_INHERITED_ENV_KEYS = (
    "HOME",
    "LANG",
    "LC_ALL",
    "NODE_EXTRA_CA_CERTS",
    "PATH",
    "PUB_CACHE",
    "SSL_CERT_FILE",
    "TMPDIR",
)
NETWORK_ENV_KEYS = (
    "FLUTTER_STORAGE_BASE_URL",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "PUB_HOSTED_URL",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)
NPM_OFFLINE_MISS_MARKERS = (
    "ENOTCACHED",
    "@undefined",
    "cache miss",
    "offline mode",
    "request to https://registry.npmjs.org",
)


class ValidationError(RuntimeError):
    """Campaign or artifact integrity is invalid."""


def canonical_json(value: Any) -> str:
    """Match the engine's recursive JSON canonicalization for supported values."""

    if isinstance(value, list):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValidationError("canonical objects require string keys")
        return (
            "{"
            + ",".join(
                json.dumps(key, ensure_ascii=False, separators=(",", ":"))
                + ":"
                + canonical_json(value[key])
                for key in sorted(value)
            )
            + "}"
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise ValidationError("non-finite JSON numbers are forbidden")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def file_identity(path: Path, name: str) -> dict[str, Any]:
    try:
        resolved = path.resolve(strict=True)
        data = resolved.read_bytes()
    except (OSError, RuntimeError) as error:
        raise ValidationError(f"{name} is unavailable: {error}") from error
    if not resolved.is_file():
        raise ValidationError(f"{name} is not a regular file")
    return {
        "path": str(path.resolve()),
        "realpath": str(resolved),
        "sha256": sha256_bytes(data),
        "byte_count": len(data),
    }


def playwright_implementation_closure() -> dict[str, Any]:
    """Validate and bind the repository-owned browser probe implementation."""

    identities = {
        "helper": file_identity(PLAYWRIGHT_HELPER_PATH, "Playwright probe helper"),
        "workspace_lock": file_identity(
            WEB_CONSOLE_LOCK_PATH, "web-console dependency lock"
        ),
        "workspace_package": file_identity(
            WEB_CONSOLE_PACKAGE_PATH, "web-console package manifest"
        ),
        "playwright_package": file_identity(
            PLAYWRIGHT_PACKAGE_ROOT / "package.json", "Playwright package manifest"
        ),
        "axe_package": file_identity(
            AXE_PACKAGE_ROOT / "package.json", "Axe Playwright package manifest"
        ),
    }
    expected_digests = {
        "workspace_lock": LOCKED_WEB_CONSOLE_LOCK_SHA256,
        "workspace_package": LOCKED_WEB_CONSOLE_PACKAGE_SHA256,
        "playwright_package": LOCKED_PLAYWRIGHT_PACKAGE_SHA256,
        "axe_package": LOCKED_AXE_PACKAGE_SHA256,
    }
    for key, digest in expected_digests.items():
        if identities[key]["sha256"] != digest:
            raise ValidationError(f"{key} digest drift")
    playwright = read_json(
        PLAYWRIGHT_PACKAGE_ROOT / "package.json", "Playwright package manifest"
    )
    axe = read_json(AXE_PACKAGE_ROOT / "package.json", "Axe package manifest")
    if (
        playwright.get("name") != "@playwright/test"
        or playwright.get("version") != LOCKED_PLAYWRIGHT_VERSION
        or axe.get("name") != "@axe-core/playwright"
        or axe.get("version") != LOCKED_AXE_PLAYWRIGHT_VERSION
    ):
        raise ValidationError("Playwright/Axe package identity drift")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "frontend-interaction-browser-implementation-closure",
        "node_module_loading": "EXACT_ABSOLUTE_REPOSITORY_PATH",
        "identities": identities,
        "closure_digest": digest_json(identities),
    }


def require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise ValidationError(f"{name} must be a sha256 digest")
    return value


def require_exact_keys(value: Any, keys: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        found = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise ValidationError(f"{name} fields are not exact: {found}")
    return value


def safe_relative_path(value: Any, name: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValidationError(f"{name} is not a safe POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValidationError(f"{name} is not a safe POSIX relative path")
    if str(path) != value:
        raise ValidationError(f"{name} is not canonical")
    return path


def resolve_regular_file(root: Path, relative: Any, name: str) -> Path:
    rel = safe_relative_path(relative, name)
    root = root.resolve()
    candidate = root.joinpath(*rel.parts)
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValidationError(f"{name} traverses a symlink")
    if not candidate.is_file():
        raise ValidationError(f"{name} does not resolve to a regular file")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValidationError(f"{name} escapes the campaign root") from error
    return resolved


def resolve_directory(root: Path, relative: Any, name: str) -> Path:
    rel = safe_relative_path(relative, name)
    root = root.resolve()
    candidate = root.joinpath(*rel.parts)
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValidationError(f"{name} traverses a symlink")
    if not candidate.is_dir():
        raise ValidationError(f"{name} does not resolve to a directory")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValidationError(f"{name} escapes the campaign root") from error
    return resolved


def read_json(path: Path, name: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{name} is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{name} must contain a JSON object")
    return value


def project_file_map(project: Path) -> dict[str, str]:
    if project.is_symlink() or not project.is_dir():
        raise ValidationError("project root must be a real directory")
    result: dict[str, str] = {}
    for path in sorted(project.rglob("*")):
        relative = path.relative_to(project).as_posix()
        if path.is_symlink():
            raise ValidationError(f"project contains symlink: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValidationError(f"project contains non-regular entry: {relative}")
        try:
            result[relative] = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValidationError(f"project file is not UTF-8: {relative}") from error
    if not result:
        raise ValidationError("project contains no files")
    return result


RUNTIME_MODEL_ORACLE_MARKERS = (
    "ELMOS_INTERACTION_OBSERVATIONS",
    "elmosInteractionObservations",
    "elmosObserveInteraction(",
    "elmosReduceRuntime(",
    "elmosProjectRuntimeObservation(",
)


def detect_runtime_model_oracle_consumption(
    project: Path, interaction_source_path: str
) -> list[dict[str, Any]]:
    """Find generated consumers that substitute the reference model for runtime.

    The sole interaction contract may define the reference interpreter for
    formal/model evidence.  Browser and native consumers may import scenario
    *inputs*, but they must not read precomputed observations or call the model
    interpreter as their runtime implementation.
    """

    contract = safe_relative_path(
        interaction_source_path, "interaction_source_path"
    ).as_posix()
    findings: list[dict[str, Any]] = []
    for path in sorted(project.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(project).as_posix()
        if relative == contract or relative.startswith(
            ("node_modules/", "build/", "dist/")
        ):
            continue
        try:
            data = path.read_bytes()
            source = data.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for marker in RUNTIME_MODEL_ORACLE_MARKERS:
            offset = source.find(marker)
            if offset < 0:
                continue
            line = source.count("\n", 0, offset) + 1
            findings.append(
                {
                    "path": relative,
                    "file_sha256": sha256_bytes(data),
                    "byte_count": len(data),
                    "marker": marker,
                    "line": line,
                }
            )
    return findings


def tree_digest(root: Path) -> dict[str, Any] | None:
    if not root.is_dir():
        return None
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValidationError(
                f"build output contains symlink: {path.relative_to(root)}"
            )
        if path.is_file():
            data = path.read_bytes()
            rows.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256_bytes(data),
                    "byte_count": len(data),
                }
            )
    return {"file_count": len(rows), "digest": digest_json(rows), "files": rows}


@dataclass(frozen=True)
class ProfileArtifact:
    profile_id: str
    framework_version: str
    platforms: tuple[str, ...]
    project_path: Path
    project_digest: str
    navigation_source_path: str
    manifest_path: Path
    relift_model_digest: str
    relift_model: Mapping[str, Any]
    proof_profile: str = PROOF_PROFILE
    interaction_source_path: str | None = None
    scenario_manifest: tuple[dict[str, Any], ...] = ()
    scenario_manifest_digest: str | None = None
    relift_block_digests: Mapping[str, str] = dataclass_field(default_factory=dict)
    runtime_model_oracle_findings: tuple[dict[str, Any], ...] = ()
    runtime_driver_contract: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.proof_profile != INTERACTION_PROOF_PROFILE:
            return
        if not self.interaction_source_path:
            raise ValidationError(
                f"{self.profile_id} v2 interaction_source_path is required"
            )
        if not self.scenario_manifest or self.scenario_manifest_digest is None:
            raise ValidationError(f"{self.profile_id} v2 scenario manifest is required")
        if self.scenario_manifest_digest != digest_json(list(self.scenario_manifest)):
            raise ValidationError(
                f"{self.profile_id} v2 scenario manifest digest mismatch"
            )
        if tuple(self.relift_block_digests) != INTERACTION_BLOCK_IDS:
            raise ValidationError(
                f"{self.profile_id} v2 relift block digest closure is invalid"
            )
        if self.runtime_driver_contract is None:
            raise ValidationError(
                f"{self.profile_id} v2 runtime driver contract is required"
            )
        recomputed = tuple(
            detect_runtime_model_oracle_consumption(
                self.project_path, self.interaction_source_path
            )
        )
        if recomputed != self.runtime_model_oracle_findings:
            raise ValidationError(
                f"{self.profile_id} v2 runtime model-oracle scan binding mismatch"
            )


@dataclass(frozen=True)
class LoadedCampaign:
    path: Path
    root: Path
    digest: str
    byte_count: int
    profiles: Mapping[str, ProfileArtifact]
    routes: tuple[dict[str, Any], ...]
    proof_profile: str = PROOF_PROFILE
    semantic_block_ids: tuple[str, ...] = ()
    scenario_manifest: tuple[dict[str, Any], ...] = ()
    scenario_manifest_digest: str | None = None
    block_symbol_map: Mapping[str, str] = dataclass_field(default_factory=dict)
    mutation_replay: tuple[dict[str, Any], ...] = ()
    engine_verifier_evidence: Mapping[str, Any] | None = None


def validate_navigation_model(profile_id: str, value: Any) -> dict[str, Any]:
    model = require_exact_keys(
        value,
        {
            "schemaVersion",
            "profile",
            "projectTitle",
            "navigation",
            "render",
            "fallback",
            "routes",
        },
        f"{profile_id} bounded navigation model",
    )
    if (
        model["schemaVersion"] != "1.0"
        or model["profile"] != PROOF_PROFILE
        or not isinstance(model["projectTitle"], str)
        or not model["projectTitle"]
        or model["navigation"] != {"label": "主要导航"}
        or model["render"] != {"mainRole": "main", "headingLevel": 1}
        or model["fallback"] != {"strategy": "FIRST_DECLARED_ROUTE"}
    ):
        raise ValidationError(f"{profile_id} bounded navigation contract drift")
    routes = model["routes"]
    if not isinstance(routes, list) or len(routes) < 2:
        raise ValidationError(
            f"{profile_id} bounded navigation requires two representative routes"
        )
    route_keys = {"id", "path", "title", "text", "requiresAuth", "deepLink"}
    ids: set[str] = set()
    paths: set[str] = set()
    for index, route_value in enumerate(routes):
        route = require_exact_keys(
            route_value, route_keys, f"{profile_id} bounded route[{index}]"
        )
        for field in ("id", "path", "title", "text"):
            if not isinstance(route[field], str) or not route[field]:
                raise ValidationError(
                    f"{profile_id} bounded route[{index}].{field} is invalid"
                )
        if (
            not route["path"].startswith("/")
            or "?" in route["path"]
            or "#" in route["path"]
            or "\\" in route["path"]
        ):
            raise ValidationError(
                f"{profile_id} bounded route[{index}].path is invalid"
            )
        if (
            type(route["requiresAuth"]) is not bool
            or type(route["deepLink"]) is not bool
        ):
            raise ValidationError(
                f"{profile_id} bounded route[{index}] flags must be booleans"
            )
        if route["id"] in ids or route["path"] in paths:
            raise ValidationError(f"{profile_id} bounded routes are not unique")
        ids.add(route["id"])
        paths.add(route["path"])
    return model


INTERACTION_MODEL_BLOCK_FIELDS = {
    "route-navigation-deeplink-404": "navigation",
    "component-template-view": "componentTemplate",
    "state-management": "stateManagement",
    "action-event": "actionEvent",
    "effect-lifecycle": "effectLifecycle",
    "form-binding-validation": "formBindingValidation",
    "api-network": "apiNetwork",
    "identity-permission": "identityPermission",
    "rendering-hydration": "renderingHydration",
    "accessibility-focus": "accessibilityFocus",
    "i18n-theme-responsive": "i18nThemeResponsive",
    "native-platform": "nativePlatform",
}


def validate_interaction_model(profile_id: str, value: Any) -> dict[str, Any]:
    model = require_exact_keys(
        value,
        {
            "schemaVersion",
            "profile",
            "projectTitle",
            *INTERACTION_MODEL_BLOCK_FIELDS.values(),
        },
        f"{profile_id} bounded interaction model",
    )
    if (
        model["schemaVersion"] != SCHEMA_VERSION
        or model["profile"] != INTERACTION_PROOF_PROFILE
        or not isinstance(model["projectTitle"], str)
        or not model["projectTitle"]
    ):
        raise ValidationError(f"{profile_id} interaction model identity drift")
    navigation = require_exact_keys(
        model["navigation"],
        {"label", "fallback", "routes"},
        f"{profile_id}.navigation",
    )
    if (
        navigation["label"] != "主要导航"
        or navigation["fallback"] != "FIRST_DECLARED_ROUTE"
    ):
        raise ValidationError(f"{profile_id} interaction navigation drift")
    navigation_model = {
        "schemaVersion": SCHEMA_VERSION,
        "profile": PROOF_PROFILE,
        "projectTitle": model["projectTitle"],
        "navigation": {"label": navigation["label"]},
        "render": {
            "mainRole": model.get("accessibilityFocus", {}).get("mainRole"),
            "headingLevel": model.get("accessibilityFocus", {}).get("headingLevel"),
        },
        "fallback": {"strategy": navigation["fallback"]},
        "routes": navigation["routes"],
    }
    validate_navigation_model(profile_id, navigation_model)
    expected_blocks: dict[str, tuple[set[str], dict[str, Any]]] = {
        "componentTemplate": (
            {"componentId", "templateKind", "keyedBy", "titleBinding", "textBinding"},
            {
                "componentId": "interaction.shell",
                "templateKind": "ROUTE_DETAIL_WITH_INTERACTION_MATRIX",
                "keyedBy": "route.id",
                "titleBinding": "route.title",
                "textBinding": "route.text",
            },
        ),
        "stateManagement": (
            {"stateId", "initial", "minimum", "maximum", "transition"},
            {
                "stateId": "bounded.counter",
                "initial": 0,
                "minimum": 0,
                "maximum": 2,
                "transition": "SATURATING_INCREMENT",
            },
        ),
        "actionEvent": (
            {"acceptedEvents", "deniedAction", "keyboardSubmit"},
            {
                "acceptedEvents": [
                    "BOOT",
                    "NAVIGATE",
                    "AUTHENTICATE",
                    "SUBMIT",
                    "CANCEL",
                    "HYDRATE",
                    "DISPLAY_CHANGE",
                    "NATIVE_DEEPLINK",
                ],
                "deniedAction": "BLOCK",
                "keyboardSubmit": "Enter",
            },
        ),
        "effectLifecycle": (
            {
                "mountEffect",
                "cleanupEffect",
                "maxExecutionsPerMount",
                "staleResponsePolicy",
            },
            {
                "mountEffect": "LOAD_ON_MOUNT",
                "cleanupEffect": "CANCEL_ON_UNMOUNT",
                "maxExecutionsPerMount": 1,
                "staleResponsePolicy": "IGNORE_AFTER_CANCEL",
            },
        ),
        "formBindingValidation": (
            {
                "formId",
                "fieldId",
                "initialValue",
                "required",
                "minimumLength",
                "validation",
                "invalidCode",
            },
            {
                "formId": "search",
                "fieldId": "query",
                "initialValue": "",
                "required": True,
                "minimumLength": 2,
                "validation": "ON_SUBMIT",
                "invalidCode": "QUERY_TOO_SHORT",
            },
        ),
        "apiNetwork": (
            {
                "operationId",
                "method",
                "path",
                "timeoutMs",
                "retry",
                "cacheScope",
                "cancelOnUnmount",
            },
            {
                "operationId": "search",
                "method": "POST",
                "path": "/api/search",
                "timeoutMs": 1000,
                "retry": "NEVER",
                "cacheScope": "TENANT_QUERY",
                "cancelOnUnmount": True,
            },
        ),
        "identityPermission": (
            {
                "anonymousRole",
                "authenticatedRole",
                "requiredPermission",
                "deniedBehavior",
                "tenantIsolation",
                "serverAuthorityRequired",
            },
            {
                "anonymousRole": "ANONYMOUS",
                "authenticatedRole": "MEMBER",
                "requiredPermission": "search:execute",
                "deniedBehavior": "HIDE_AND_BLOCK",
                "tenantIsolation": "EXACT_TENANT_MATCH",
                "serverAuthorityRequired": True,
            },
        ),
        "renderingHydration": (
            {
                "mode",
                "hydrationPolicy",
                "mismatchBehavior",
                "duplicateEffectsAllowed",
            },
            {
                "mode": "HYDRATABLE_CSR",
                "hydrationPolicy": "REQUIRE_MATCH",
                "mismatchBehavior": "RENDER_ERROR",
                "duplicateEffectsAllowed": False,
            },
        ),
        "accessibilityFocus": (
            {
                "mainRole",
                "headingLevel",
                "formLabel",
                "errorRole",
                "liveRegion",
                "invalidFocusTarget",
                "keyboardSubmit",
            },
            {
                "mainRole": "main",
                "headingLevel": 1,
                "formLabel": "搜索",
                "errorRole": "alert",
                "liveRegion": "polite",
                "invalidFocusTarget": "query",
                "keyboardSubmit": "Enter",
            },
        ),
        "i18nThemeResponsive": (
            {
                "supportedLocales",
                "fallbackLocale",
                "themes",
                "defaultTheme",
                "compactBreakpoint",
                "compactColumns",
                "wideColumns",
            },
            {
                "supportedLocales": ["zh-CN", "en-US"],
                "fallbackLocale": "en-US",
                "themes": ["LIGHT", "DARK"],
                "defaultTheme": "LIGHT",
                "compactBreakpoint": 720,
                "compactColumns": 1,
                "wideColumns": 2,
            },
        ),
        "nativePlatform": (
            {
                "boundary",
                "capability",
                "lifecycleStates",
                "permission",
                "deniedBehavior",
                "recovery",
            },
            {
                "boundary": "ADAPTER",
                "capability": "OPEN_DEEP_LINK",
                "lifecycleStates": ["FOREGROUND", "BACKGROUND"],
                "permission": "DEEPLINK_OPEN",
                "deniedBehavior": "NO_OP_REPORTED",
                "recovery": "FOREGROUND_RETRY",
            },
        ),
    }
    for field, (keys, expected) in expected_blocks.items():
        actual = require_exact_keys(model[field], keys, f"{profile_id}.{field}")
        if actual != expected:
            raise ValidationError(f"{profile_id} interaction {field} drift")
    return model


INTERACTION_INPUT_KEYS = {
    "routePath",
    "event",
    "counterBefore",
    "incrementCount",
    "lifecycle",
    "query",
    "keyboardKey",
    "authenticated",
    "permissionGranted",
    "tenantId",
    "resourceTenantId",
    "networkResult",
    "hydration",
    "locale",
    "theme",
    "viewportWidth",
    "nativeLifecycle",
    "deepLinkPath",
    "nativePermission",
    "nativeAvailable",
}


def validate_scenario_manifest(value: Any, name: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{name} is empty")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        row = require_exact_keys(raw, {"scenarioId", "input"}, f"{name}[{index}]")
        scenario_id = row["scenarioId"]
        if not isinstance(scenario_id, str) or not scenario_id or scenario_id in seen:
            raise ValidationError(f"{name}[{index}].scenarioId is invalid or duplicate")
        input_value = require_exact_keys(
            row["input"], INTERACTION_INPUT_KEYS, f"{name}[{index}].input"
        )
        if (
            input_value["event"]
            not in {
                "BOOT",
                "NAVIGATE",
                "AUTHENTICATE",
                "SUBMIT",
                "CANCEL",
                "HYDRATE",
                "DISPLAY_CHANGE",
                "NATIVE_DEEPLINK",
            }
            or input_value["lifecycle"] not in {"MOUNT", "ACTIVE", "UNMOUNT"}
            or input_value["networkResult"] not in {"NONE", "SUCCESS", "ERROR", "STALE"}
            or input_value["hydration"] not in {"NONE", "MATCH", "MISMATCH"}
            or input_value["keyboardKey"] not in {"NONE", "Enter"}
            or input_value["nativeLifecycle"] not in {"FOREGROUND", "BACKGROUND"}
            or input_value["nativePermission"] not in {"GRANTED", "DENIED"}
        ):
            raise ValidationError(f"{name}[{index}] contains an invalid enum")
        for key in (
            "authenticated",
            "permissionGranted",
            "nativeAvailable",
        ):
            if type(input_value[key]) is not bool:
                raise ValidationError(f"{name}[{index}].input.{key} is not boolean")
        for key in ("counterBefore", "incrementCount", "viewportWidth"):
            if type(input_value[key]) is not int:
                raise ValidationError(f"{name}[{index}].input.{key} is not integer")
        seen.add(scenario_id)
        rows.append({"scenario_id": scenario_id, "input": dict(input_value)})
    return tuple(rows)


def validate_locked_interaction_scenario_policy(
    *, source_sha256: Any, source_byte_count: Any, scenario_ids: Any
) -> None:
    """Enforce the runner-owned, content-addressed 18-scenario policy.

    This policy is independent of campaign declarations.  Because the digest
    binds the complete pretty-JSON corpus bytes, any input mutation, deletion,
    or reordering requires an explicit runner policy/version update.
    """

    if (
        source_sha256 != LOCKED_INTERACTION_SCENARIO_SOURCE_SHA256
        or source_byte_count != LOCKED_INTERACTION_SCENARIO_SOURCE_BYTE_COUNT
        or scenario_ids != list(LOCKED_INTERACTION_SCENARIO_IDS)
    ):
        raise ValidationError(
            "scenario corpus violates the independent locked scenario policy"
        )


def relift_navigation_model(profile_id: str, source: str) -> dict[str, Any]:
    if profile_id == "flutter":
        marker = "const String elmosBoundedNavigationBase64 = "
        if source.count(marker) != 1:
            raise ValidationError(
                "flutter bounded model marker is missing or duplicated"
            )
        offset = source.index(marker) + len(marker)
        try:
            encoded, end = json.JSONDecoder().raw_decode(source, offset)
            if not isinstance(encoded, str) or not source[end:].lstrip().startswith(
                ";"
            ):
                raise ValueError("invalid Dart constant")
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
            value = json.loads(decoded)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValidationError(
                "flutter bounded model is not valid base64 JSON"
            ) from error
    else:
        marker = "export const ELMOS_BOUNDED_NAVIGATION = "
        if source.count(marker) != 1:
            raise ValidationError(
                f"{profile_id} bounded model marker is missing or duplicated"
            )
        offset = source.index(marker) + len(marker)
        try:
            value, end = json.JSONDecoder().raw_decode(source, offset)
        except json.JSONDecodeError as error:
            raise ValidationError(
                f"{profile_id} bounded model is not embedded canonical JSON"
            ) from error
        tail = source[end:].lstrip()
        if not (tail.startswith("as const;") or tail.startswith(";")):
            raise ValidationError(f"{profile_id} bounded model terminator is invalid")
    return validate_navigation_model(profile_id, value)


def _decode_embedded_json_string(source: str, marker: str, name: str) -> Any:
    if source.count(marker) != 1:
        raise ValidationError(f"{name} marker is missing or duplicated")
    offset = source.index(marker) + len(marker)
    try:
        encoded, end = json.JSONDecoder().raw_decode(source, offset)
        if not isinstance(encoded, str) or not source[end:].lstrip().startswith(";"):
            raise ValueError("invalid embedded string terminator")
        return json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
    except (
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise ValidationError(f"{name} is not valid base64 JSON") from error


def _decode_exported_json(source: str, marker: str, name: str) -> Any:
    if source.count(marker) != 1:
        raise ValidationError(f"{name} marker is missing or duplicated")
    offset = source.index(marker) + len(marker)
    try:
        value, end = json.JSONDecoder().raw_decode(source, offset)
    except json.JSONDecodeError as error:
        raise ValidationError(f"{name} is not embedded canonical JSON") from error
    tail = source[end:].lstrip()
    if not (tail.startswith("as const;") or tail.startswith(";")):
        raise ValidationError(f"{name} terminator is invalid")
    return value


def relift_interaction_contract(
    profile_id: str, source: str
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    if profile_id == "flutter":
        model = _decode_embedded_json_string(
            source,
            "const String elmosFrontendInteractionBase64 = ",
            "flutter interaction model",
        )
        scenarios = _decode_embedded_json_string(
            source,
            "const String elmosInteractionScenariosBase64 = ",
            "flutter interaction scenarios",
        )
    else:
        model = _decode_exported_json(
            source,
            "export const ELMOS_FRONTEND_INTERACTION = ",
            f"{profile_id} interaction model",
        )
        scenarios = _decode_exported_json(
            source,
            "export const ELMOS_INTERACTION_SCENARIOS = ",
            f"{profile_id} interaction scenarios",
        )
    return (
        validate_interaction_model(profile_id, model),
        validate_scenario_manifest(
            scenarios, f"{profile_id} embedded scenario manifest"
        ),
    )


RUNTIME_DRIVER_CONTRACT_KEYS = {
    "actual_source",
    "block_observer_contracts",
    "block_selector_template",
    "browser_or_device_evidence",
    "browser_required_not_run_blocks",
    "certification",
    "channel_projection_contract",
    "channel_projection_contract_digest",
    "completion_attribute",
    "completion_value",
    "customer_runtime_evidence",
    "declaration_payload_allowed_keys",
    "framework_binding",
    "independent_runtime_oracle",
    "kind",
    "legacy_runtime_observed_allowed",
    "native_adapter_evidence",
    "native_required_not_run_blocks",
    "native_route_without_real_device_channel_status",
    "network_intercept_path",
    "observer_protocol",
    "query_selector",
    "ready_selector",
    "required_runtime_channels",
    "root_selector",
    "runtime_evidence_eligibility",
    "runtime_source_attribute",
    "runtime_source_value",
    "runtime_status",
    "scenario_action_selector_template",
    "scenario_row_selector_template",
    "schema_version",
    "self_reported_reducer_json_allowed",
    "sequence_attribute",
}

RUNTIME_FRAMEWORK_BINDINGS = {
    "react": "REACT_HOOKS_COMPONENT",
    "vue2": "VUE2_OPTIONS_COMPONENT",
    "vue3": "VUE3_COMPOSITION_COMPONENT",
    "angular": "ANGULAR_SIGNAL_COMPONENT",
    "svelte": "SVELTE_COMPONENT_STATE",
    "jquery": "JQUERY_NAMESPACED_EVENTS_DATA",
    "react-native": "REACT_NATIVE_HOOKS_COMPONENT",
    "flutter": "FLUTTER_STATEFUL_WIDGET_INTEGRATION_SEMANTICS",
    "harmony-arkui": "ARKUI_STATE_COMPONENT_UITEST_SEMANTICS",
}


def validate_runtime_driver_contract(
    value: Any,
    profile_id: str,
    name: str,
    *,
    model_digest: str | None = None,
) -> dict[str, Any]:
    contract = require_exact_keys(value, RUNTIME_DRIVER_CONTRACT_KEYS, name)
    browser_dom = profile_id not in {"flutter", "harmony-arkui"}
    channels = required_runtime_channels(profile_id)
    if (
        contract["schema_version"] != SCHEMA_VERSION
        or contract["kind"]
        != (
            "bounded-interaction-framework-browser-driver-contract"
            if browser_dom
            else "bounded-interaction-native-semantics-driver-contract"
        )
        or contract["framework_binding"] != RUNTIME_FRAMEWORK_BINDINGS[profile_id]
        or contract["runtime_evidence_eligibility"]
        != "ELIGIBLE_LOCAL_ACTUAL_RUNTIME_EXECUTION"
        or contract["runtime_status"] != "NOT_RUN"
        or contract["independent_runtime_oracle"] != "NOT_RUN"
        or contract["customer_runtime_evidence"] != "NOT_RUN"
        or contract["certification"] != "NOT_CERTIFIED"
        or contract["required_runtime_channels"] != list(channels)
        or contract["observer_protocol"] != BLOCK_OBSERVER_CONTRACT
        or contract["actual_source"] != BLOCK_SPECIFIC_RUNTIME_ACTUAL_SOURCE
        or contract["self_reported_reducer_json_allowed"] is not False
        or contract["legacy_runtime_observed_allowed"] is not False
        or contract["declaration_payload_allowed_keys"]
        != [
            "schema_version",
            "kind",
            "block_id",
            "status",
            "observer_kind",
            "measurement_surface",
            "reason",
        ]
        or contract["native_route_without_real_device_channel_status"]
        != "NOT_RUN"
        or contract["native_adapter_evidence"] != "NOT_RUN"
        or contract["browser_or_device_evidence"] != "NOT_RUN"
    ):
        raise ValidationError(f"{name} proof boundary drift")

    observer_contracts = contract["block_observer_contracts"]
    if not isinstance(observer_contracts, dict) or tuple(observer_contracts) != (
        INTERACTION_BLOCK_IDS
    ):
        raise ValidationError(f"{name}.block_observer_contracts closure drift")
    browser_not_run: list[str] = []
    native_not_run: list[str] = []
    for block_id, raw in observer_contracts.items():
        row = require_exact_keys(
            raw,
            {
                "observer_kind",
                "measurement_surface",
                "browser_status",
                "browser_reason",
                "native_status",
                "native_reason",
            },
            f"{name}.block_observer_contracts.{block_id}",
        )
        spec = BLOCK_OBSERVER_SPECS[block_id]
        if (
            row["observer_kind"] != spec["observer_kind"]
            or row["measurement_surface"] != spec["measurement_surface"]
            or row["browser_status"] not in {"PASSED", "NOT_RUN"}
            or row["native_status"] not in {"PASSED", "NOT_RUN"}
            or not isinstance(row["browser_reason"], str)
            or not row["browser_reason"]
            or not isinstance(row["native_reason"], str)
            or not row["native_reason"]
        ):
            raise ValidationError(f"{name}.{block_id} observer ceiling drift")
        if row["browser_status"] == "NOT_RUN":
            browser_not_run.append(block_id)
        if row["native_status"] == "NOT_RUN":
            native_not_run.append(block_id)
    if (
        browser_not_run != list(WEB_BROWSER_MANDATORY_NOT_RUN_BLOCK_IDS)
        or contract["browser_required_not_run_blocks"] != browser_not_run
        or native_not_run != list(NATIVE_MANDATORY_NOT_RUN_BLOCK_IDS)
        or contract["native_required_not_run_blocks"] != native_not_run
        or observer_contracts["api-network"]["native_reason"]
        != NATIVE_API_NOT_RUN_REASON
    ):
        raise ValidationError(f"{name} browser/native observer ceiling drift")

    expected_surface = {
        "root_selector": (
            '#elmos-interaction[data-proof-profile="bounded-frontend-interaction-v1"]'
            '[data-observer-protocol="block-specific-runtime-observation-v1"]'
            if browser_dom
            else "NOT_APPLICABLE"
        ),
        "ready_selector": (
            '#elmos-interaction[data-elmos-ready="true"]'
            '[data-observer-protocol="block-specific-runtime-observation-v1"]'
            if browser_dom
            else "NOT_APPLICABLE"
        ),
        "scenario_row_selector_template": (
            '[data-scenario-id="${scenario_id}"]'
            if browser_dom
            else "NOT_APPLICABLE"
        ),
        "scenario_action_selector_template": (
            '[data-run-scenario="${scenario_id}"]'
            if browser_dom
            else "NOT_APPLICABLE"
        ),
        "runtime_source_attribute": (
            "data-runtime-source" if browser_dom else "SEMANTICS_LABEL"
        ),
        "runtime_source_value": BLOCK_SPECIFIC_RUNTIME_ACTUAL_SOURCE,
        "completion_attribute": (
            "data-execution-state" if browser_dom else "SEMANTICS_LABEL"
        ),
        "completion_value": (
            "PARTIAL" if browser_dom else "PARTIAL_OR_COMPLETE_FROM_BLOCK_STATUSES"
        ),
        "sequence_attribute": (
            "data-execution-sequence" if browser_dom else "SEMANTICS_LABEL"
        ),
        "query_selector": "#elmos-query" if browser_dom else "ValueKey(elmos-query)",
        "block_selector_template": (
            '[data-semantic-block="${block_id}"]'
            if browser_dom
            else "ValueKey(block:${scenario_id}:${block_id})"
        ),
        "network_intercept_path": (
            "/api/search" if "browser" in channels else "ADAPTER_TRACE"
        ),
    }
    if any(contract[key] != expected for key, expected in expected_surface.items()):
        raise ValidationError(f"{name} observer selector/surface drift")

    projection = require_exact_keys(
        contract["channel_projection_contract"],
        {
            "schema_version",
            "kind",
            "projection",
            "model_digest",
            "block_actual_keys",
            "scenario_ids",
            "channels",
            "oracle_provenance",
            "arbitrary_customer_runtime",
        },
        f"{name}.channel_projection_contract",
    )
    if (
        projection["schema_version"] != SCHEMA_VERSION
        or projection["kind"]
        != "bounded-interaction-channel-projection-contract"
        or projection["projection"] != "STRICT_RUNTIME_OBSERVATION_V1"
        or (
            model_digest is not None
            and projection["model_digest"] != require_sha256(model_digest, name)
        )
        or projection["scenario_ids"] != list(LOCKED_INTERACTION_SCENARIO_IDS)
        or projection["oracle_provenance"]
        != "SAME_PRODUCER_CHANNEL_PROJECTION_NOT_INDEPENDENT"
        or projection["arbitrary_customer_runtime"] != "NOT_PROVED"
    ):
        raise ValidationError(f"{name} channel projection identity drift")
    projection_model_digest = require_sha256(
        projection["model_digest"], f"{name}.channel_projection_contract.model_digest"
    )
    if model_digest is not None and projection_model_digest != model_digest:
        raise ValidationError(f"{name} channel projection model binding drift")
    block_actual_keys = projection["block_actual_keys"]
    if not isinstance(block_actual_keys, dict) or tuple(block_actual_keys) != (
        INTERACTION_BLOCK_IDS
    ):
        raise ValidationError(f"{name} channel projection block-key closure drift")
    for block_id, keys in block_actual_keys.items():
        if (
            not isinstance(keys, list)
            or len(keys) != len(set(keys))
            or set(keys) != INTERACTION_BLOCK_ACTUAL_KEYS[block_id]
        ):
            raise ValidationError(f"{name}.{block_id} projection actual keys drift")
    projected_channels = projection["channels"]
    if not isinstance(projected_channels, dict) or tuple(projected_channels) != channels:
        raise ValidationError(f"{name} channel projection closure drift")
    for channel, raw_channel in projected_channels.items():
        channel_row = require_exact_keys(
            raw_channel,
            {"status", "native_execution_allowed", "scenarios"},
            f"{name}.channel_projection_contract.channels.{channel}",
        )
        scenarios = channel_row["scenarios"]
        if (
            channel_row["status"] != "NOT_RUN"
            or channel_row["native_execution_allowed"] != (channel != "browser")
            or not isinstance(scenarios, list)
            or [row.get("scenario_id") for row in scenarios]
            != list(LOCKED_INTERACTION_SCENARIO_IDS)
        ):
            raise ValidationError(f"{name}.{channel} projection scenario closure drift")
        for index, raw_scenario in enumerate(scenarios):
            scenario = require_exact_keys(
                raw_scenario,
                {"scenario_id", "blocks", "block_digests"},
                f"{name}.{channel}.scenarios[{index}]",
            )
            blocks = scenario["blocks"]
            digests = scenario["block_digests"]
            if (
                not isinstance(blocks, dict)
                or tuple(blocks) != INTERACTION_BLOCK_IDS
                or not isinstance(digests, dict)
                or tuple(digests) != INTERACTION_BLOCK_IDS
            ):
                raise ValidationError(
                    f"{name}.{channel}.{scenario['scenario_id']} block closure drift"
                )
            for block_id, actual in blocks.items():
                require_exact_keys(
                    actual,
                    INTERACTION_BLOCK_ACTUAL_KEYS[block_id],
                    f"{name}.{channel}.{scenario['scenario_id']}.{block_id}",
                )
                if digests[block_id] != digest_json(actual):
                    raise ValidationError(
                        f"{name}.{channel}.{scenario['scenario_id']}.{block_id} digest drift"
                    )
    projection_digest = require_sha256(
        contract["channel_projection_contract_digest"],
        f"{name}.channel_projection_contract_digest",
    )
    if projection_digest != digest_json(projection):
        raise ValidationError(f"{name} channel projection digest drift")
    return contract


def load_scenario_corpus(
    root: Path, manifest: Mapping[str, Any]
) -> tuple[tuple[dict[str, Any], ...], str]:
    row = require_exact_keys(
        dict(manifest),
        {
            "schema_version",
            "kind",
            "source_kind",
            "source_path",
            "source_sha256",
            "source_byte_count",
            "scenario_ids",
            "scenario_count",
            "input_schema",
            "runtime_driver_contract",
        },
        "scenario_manifest",
    )
    validate_locked_interaction_scenario_policy(
        source_sha256=row["source_sha256"],
        source_byte_count=row["source_byte_count"],
        scenario_ids=row["scenario_ids"],
    )
    if (
        row["schema_version"] != SCHEMA_VERSION
        or row["kind"] != "bounded-interaction-scenario-manifest"
        or row["source_kind"] != "GENERATED_FIXTURE"
        or row["source_path"] != "scenario-corpus.json"
        or row["scenario_count"] != len(LOCKED_INTERACTION_SCENARIO_IDS)
        or row["input_schema"] != "InteractionInput@bounded-frontend-interaction-v1"
        or row["runtime_driver_contract"] != "profiles[].runtime_driver_contract"
    ):
        raise ValidationError(
            "scenario manifest violates the independent locked scenario policy"
        )
    source_path = resolve_regular_file(
        root, row["source_path"], "scenario_manifest.source_path"
    )
    data = source_path.read_bytes()
    source_digest = require_sha256(
        row["source_sha256"], "scenario_manifest.source_sha256"
    )
    if (
        len(data) != row["source_byte_count"]
        or sha256_bytes(data) != source_digest
        or source_digest != LOCKED_INTERACTION_SCENARIO_SOURCE_SHA256
    ):
        raise ValidationError("scenario corpus byte binding mismatch")
    corpus = require_exact_keys(
        read_json(source_path, "scenario corpus"),
        {
            "schema_version",
            "kind",
            "proof_profile",
            "source_kind",
            "scenarios",
            "arbitrary_customer_source",
            "external_runtime_evidence",
        },
        "scenario corpus",
    )
    if (
        corpus["schema_version"] != SCHEMA_VERSION
        or corpus["kind"] != "bounded-frontend-interaction-scenario-corpus"
        or corpus["proof_profile"] != INTERACTION_PROOF_PROFILE
        or corpus["source_kind"] != row["source_kind"]
        or corpus["arbitrary_customer_source"] != "NOT_PROVED"
        or corpus["external_runtime_evidence"] != "NOT_RUN"
    ):
        raise ValidationError("scenario corpus proof boundary is invalid")
    scenarios = validate_scenario_manifest(
        corpus["scenarios"], "scenario corpus scenarios"
    )
    scenario_ids = [item["scenario_id"] for item in scenarios]
    if (
        scenario_ids != list(LOCKED_INTERACTION_SCENARIO_IDS)
        or row["scenario_ids"] != scenario_ids
        or row["scenario_count"] != len(scenarios)
    ):
        raise ValidationError("scenario manifest/source scenario closure mismatch")
    return scenarios, source_digest


def validate_project_manifest(
    root: Path,
    profile_row: dict[str, Any],
    expected: dict[str, Any],
) -> ProfileArtifact:
    profile_id = profile_row["profile_id"]
    expected_project = f"profiles/{profile_id}/project"
    expected_manifest = f"profiles/{profile_id}/manifest.json"
    if (
        profile_row["project_path"] != expected_project
        or profile_row["manifest_path"] != expected_manifest
    ):
        raise ValidationError(f"{profile_id} profile paths are not canonical")
    if profile_row["framework_version"] != expected["framework_version"]:
        raise ValidationError(f"{profile_id} framework version drift")
    if profile_row["platforms"] != expected["platforms"]:
        raise ValidationError(f"{profile_id} platforms drift")
    if profile_row["target_build"] != "NOT_RUN":
        raise ValidationError(f"{profile_id} input target_build must remain NOT_RUN")

    project_digest = require_sha256(
        profile_row["project_digest"], f"{profile_id}.project_digest"
    )
    manifest_digest = require_sha256(
        profile_row["manifest_digest"], f"{profile_id}.manifest_digest"
    )
    relift_digest = require_sha256(
        profile_row["relift_model_digest"], f"{profile_id}.relift_model_digest"
    )
    project = resolve_directory(
        root, profile_row["project_path"], f"{profile_id}.project_path"
    )
    manifest_path = resolve_regular_file(
        root, profile_row["manifest_path"], f"{profile_id}.manifest_path"
    )
    manifest = require_exact_keys(
        read_json(manifest_path, f"{profile_id} manifest"),
        {
            "schema_version",
            "kind",
            "profile_id",
            "framework_version",
            "platforms",
            "project_path",
            "project_digest",
            "digest_scope",
            "file_count",
            "files",
            "manifest_digest",
        },
        f"{profile_id} manifest",
    )
    if (
        manifest["schema_version"] != SCHEMA_VERSION
        or manifest["kind"] != "frontend-formal-profile-project"
    ):
        raise ValidationError(f"{profile_id} manifest identity is invalid")
    for field in ("profile_id", "framework_version", "platforms", "project_digest"):
        if manifest[field] != profile_row[field]:
            raise ValidationError(f"{profile_id} manifest {field} binding mismatch")
    if manifest["project_path"] != "project":
        raise ValidationError(f"{profile_id} manifest project_path must be project")
    if (
        manifest["digest_scope"]
        != "sorted UTF-8 project files keyed by POSIX relative path"
    ):
        raise ValidationError(f"{profile_id} manifest digest_scope is invalid")
    without_digest = dict(manifest)
    without_digest.pop("manifest_digest")
    computed_manifest_digest = digest_json(without_digest)
    if (
        manifest["manifest_digest"] != computed_manifest_digest
        or manifest_digest != computed_manifest_digest
    ):
        raise ValidationError(f"{profile_id} manifest digest mismatch")

    files = project_file_map(project)
    computed_project_digest = digest_json(files)
    if (
        project_digest != computed_project_digest
        or manifest["project_digest"] != computed_project_digest
    ):
        raise ValidationError(f"{profile_id} project digest mismatch")
    expected_rows = []
    for path, content in files.items():
        data = content.encode("utf-8")
        expected_rows.append(
            {"path": path, "sha256": sha256_bytes(data), "byte_count": len(data)}
        )
    if manifest["files"] != expected_rows or manifest["file_count"] != len(
        expected_rows
    ):
        raise ValidationError(f"{profile_id} manifest file inventory mismatch")

    navigation_path = safe_relative_path(
        profile_row["navigation_source_path"], f"{profile_id}.navigation_source_path"
    )
    if str(navigation_path) not in files:
        raise ValidationError(
            f"{profile_id} navigation source is absent from the project"
        )
    relift_model = relift_navigation_model(profile_id, files[str(navigation_path)])
    if digest_json(relift_model) != relift_digest:
        raise ValidationError(f"{profile_id} relift model digest mismatch")
    validate_generated_project(profile_id, project, files, expected)
    return ProfileArtifact(
        profile_id=profile_id,
        framework_version=profile_row["framework_version"],
        platforms=tuple(profile_row["platforms"]),
        project_path=project,
        project_digest=project_digest,
        navigation_source_path=str(navigation_path),
        manifest_path=manifest_path,
        relift_model_digest=relift_digest,
        relift_model=relift_model,
    )


def validate_interaction_project_manifest(
    root: Path,
    profile_row: dict[str, Any],
    expected: dict[str, Any],
    scenario_manifest: tuple[dict[str, Any], ...],
) -> ProfileArtifact:
    profile_id = profile_row["profile_id"]
    expected_project = f"profiles/{profile_id}/project"
    expected_manifest = f"profiles/{profile_id}/manifest.json"
    if (
        profile_row["project_path"] != expected_project
        or profile_row["manifest_path"] != expected_manifest
        or profile_row["framework_version"] != expected["framework_version"]
        or profile_row["platforms"] != expected["platforms"]
        or profile_row["required_runtime_channels"]
        != list(required_runtime_channels(profile_id))
        or profile_row["target_build"] != "NOT_RUN"
        or profile_row["target_runtime"] != "NOT_RUN"
    ):
        raise ValidationError(f"{profile_id} interaction profile identity drift")
    project_digest = require_sha256(
        profile_row["project_digest"], f"{profile_id}.project_digest"
    )
    manifest_digest = require_sha256(
        profile_row["manifest_digest"], f"{profile_id}.manifest_digest"
    )
    relift_digest = require_sha256(
        profile_row["relift_model_digest"], f"{profile_id}.relift_model_digest"
    )
    project = resolve_directory(
        root, profile_row["project_path"], f"{profile_id}.project_path"
    )
    manifest_path = resolve_regular_file(
        root, profile_row["manifest_path"], f"{profile_id}.manifest_path"
    )
    manifest = require_exact_keys(
        read_json(manifest_path, f"{profile_id} interaction manifest"),
        {
            "schema_version",
            "kind",
            "proof_profile",
            "profile_id",
            "framework_version",
            "platforms",
            "required_runtime_channels",
            "project_path",
            "project_digest",
            "digest_scope",
            "file_count",
            "files",
            "source_kind",
            "source_fixture_path",
            "source_fixture_digest",
            "source_fixture_byte_count",
            "interaction_source_path",
            "navigation_compatibility_path",
            "relift_model_digest",
            "relift_block_digests",
            "runtime_driver_contract",
            "target_build",
            "target_runtime",
            "manifest_digest",
        },
        f"{profile_id} interaction manifest",
    )
    if (
        manifest["schema_version"] != SCHEMA_VERSION
        or manifest["kind"] != "frontend-interaction-formal-profile-project"
        or manifest["proof_profile"] != INTERACTION_PROOF_PROFILE
        or manifest["project_path"] != "project"
        or manifest["digest_scope"]
        != "sorted UTF-8 project files keyed by POSIX relative path"
    ):
        raise ValidationError(f"{profile_id} interaction manifest identity drift")
    bound_fields = {
        "profile_id",
        "framework_version",
        "platforms",
        "required_runtime_channels",
        "project_digest",
        "source_kind",
        "source_fixture_path",
        "source_fixture_digest",
        "source_fixture_byte_count",
        "interaction_source_path",
        "navigation_compatibility_path",
        "relift_model_digest",
        "relift_block_digests",
        "runtime_driver_contract",
        "target_build",
        "target_runtime",
    }
    for field in bound_fields:
        if manifest[field] != profile_row[field]:
            raise ValidationError(f"{profile_id} manifest {field} binding mismatch")
    without_digest = dict(manifest)
    without_digest.pop("manifest_digest")
    computed_manifest_digest = digest_json(without_digest)
    if (
        manifest["manifest_digest"] != computed_manifest_digest
        or manifest_digest != computed_manifest_digest
    ):
        raise ValidationError(f"{profile_id} interaction manifest digest mismatch")
    files = project_file_map(project)
    if project_digest != digest_json(files):
        raise ValidationError(f"{profile_id} interaction project digest mismatch")
    expected_rows = []
    for path, content in files.items():
        data = content.encode("utf-8")
        expected_rows.append(
            {"path": path, "sha256": sha256_bytes(data), "byte_count": len(data)}
        )
    if manifest["files"] != expected_rows or manifest["file_count"] != len(
        expected_rows
    ):
        raise ValidationError(f"{profile_id} interaction file inventory mismatch")
    source_fixture_path = (
        f"generated-fixtures/{profile_id}/typed-ui-interaction-ir.json"
    )
    if (
        profile_row["source_kind"] != "GENERATED_FIXTURE"
        or profile_row["source_fixture_path"] != source_fixture_path
        or type(profile_row["source_fixture_byte_count"]) is not int
        or profile_row["source_fixture_byte_count"] < 1
    ):
        raise ValidationError(f"{profile_id} source fixture provenance drift")
    source_fixture = resolve_regular_file(
        root, source_fixture_path, f"{profile_id}.source_fixture_path"
    )
    source_fixture_bytes = source_fixture.read_bytes()
    source_fixture_digest = require_sha256(
        profile_row["source_fixture_digest"], f"{profile_id}.source_fixture_digest"
    )
    if (
        len(source_fixture_bytes) != profile_row["source_fixture_byte_count"]
        or sha256_bytes(source_fixture_bytes) != source_fixture_digest
    ):
        raise ValidationError(f"{profile_id} source fixture byte binding drift")
    interaction_path = safe_relative_path(
        profile_row["interaction_source_path"],
        f"{profile_id}.interaction_source_path",
    ).as_posix()
    compatibility_path = safe_relative_path(
        profile_row["navigation_compatibility_path"],
        f"{profile_id}.navigation_compatibility_path",
    ).as_posix()
    if interaction_path not in files or compatibility_path not in files:
        raise ValidationError(f"{profile_id} interaction sources are absent")
    relift_model, embedded_scenarios = relift_interaction_contract(
        profile_id, files[interaction_path]
    )
    if embedded_scenarios != scenario_manifest:
        raise ValidationError(f"{profile_id} embedded scenario corpus drift")
    if digest_json(relift_model) != relift_digest:
        raise ValidationError(f"{profile_id} interaction relift model digest mismatch")
    block_digests = profile_row["relift_block_digests"]
    if not isinstance(block_digests, dict) or tuple(block_digests) != (
        INTERACTION_BLOCK_IDS
    ):
        raise ValidationError(f"{profile_id} relift block digest closure drift")
    computed_block_digests = {
        block_id: digest_json(relift_model[field])
        for block_id, field in INTERACTION_MODEL_BLOCK_FIELDS.items()
    }
    if block_digests != computed_block_digests:
        raise ValidationError(f"{profile_id} relift block digest binding drift")
    runtime_driver_contract = validate_runtime_driver_contract(
        profile_row["runtime_driver_contract"],
        profile_id,
        f"{profile_id}.runtime_driver_contract",
        model_digest=relift_digest,
    )
    kind = expected["kind"]
    if kind == "node":
        validate_node_project(profile_id, project)
    elif kind == "flutter":
        fvm = read_json(project / ".fvmrc", f"{profile_id} .fvmrc")
        if fvm != {"flutter": "3.44.1"}:
            raise ValidationError("flutter .fvmrc must pin 3.44.1")
    else:
        harmony = read_json(
            project / ".elmos-harmony-runner.json", f"{profile_id} harmony runner"
        )
        if harmony.get("sdk") != "6.0.0(20)" or harmony.get("apiLevel") != 20:
            raise ValidationError("Harmony runner profile is not exact")
    findings = tuple(detect_runtime_model_oracle_consumption(project, interaction_path))
    normalized_scenarios = tuple(dict(item) for item in scenario_manifest)
    return ProfileArtifact(
        profile_id=profile_id,
        framework_version=profile_row["framework_version"],
        platforms=tuple(profile_row["platforms"]),
        project_path=project,
        project_digest=project_digest,
        navigation_source_path=compatibility_path,
        manifest_path=manifest_path,
        relift_model_digest=relift_digest,
        relift_model=relift_model,
        proof_profile=INTERACTION_PROOF_PROFILE,
        interaction_source_path=interaction_path,
        scenario_manifest=normalized_scenarios,
        scenario_manifest_digest=digest_json(list(normalized_scenarios)),
        relift_block_digests=computed_block_digests,
        runtime_model_oracle_findings=findings,
        runtime_driver_contract=runtime_driver_contract,
    )


def validate_generated_project(
    profile_id: str,
    project: Path,
    files: Mapping[str, str],
    expected: Mapping[str, Any],
) -> None:
    migration_path = project / "elmos.ui-migration.json"
    if "elmos.ui-migration.json" not in files or not migration_path.is_file():
        raise ValidationError(f"{profile_id} is missing elmos.ui-migration.json")
    migration = read_json(migration_path, f"{profile_id} migration manifest")
    if migration.get("schemaVersion") != "1.0":
        raise ValidationError(f"{profile_id} migration schema is invalid")
    target = migration.get("targetProfile")
    if not isinstance(target, dict):
        raise ValidationError(f"{profile_id} target profile is absent")
    if (
        target.get("id") != profile_id
        or target.get("frameworkVersion") != expected["framework_version"]
        or target.get("platforms") != expected["platforms"]
    ):
        raise ValidationError(f"{profile_id} target profile binding drift")
    direction = migration.get("direction")
    if not isinstance(direction, dict) or direction.get("target") != profile_id:
        raise ValidationError(f"{profile_id} direction binding mismatch")
    if (
        migration.get("digestScope")
        != "all generated files except elmos.ui-migration.json"
    ):
        raise ValidationError(f"{profile_id} migration digest scope is invalid")
    generated_without_manifest = dict(files)
    generated_without_manifest.pop("elmos.ui-migration.json")
    if migration.get("contentDigest") != digest_json(generated_without_manifest):
        raise ValidationError(f"{profile_id} migration content digest mismatch")
    verification = migration.get("verification")
    if verification != {
        "dependencyLock": "NOT_RUN",
        "targetBuild": "NOT_RUN",
        "targetStartup": "NOT_RUN",
        "browserOrDeviceJourney": "NOT_RUN",
        "accessibility": "NOT_RUN",
        "visualParity": "NOT_RUN",
        "holdout": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }:
        raise ValidationError(f"{profile_id} input verification claims runtime success")

    kind = expected["kind"]
    if kind == "node":
        validate_node_project(profile_id, project)
    elif kind == "flutter":
        fvm = read_json(project / ".fvmrc", f"{profile_id} .fvmrc")
        if fvm != {"flutter": "3.44.1"}:
            raise ValidationError("flutter .fvmrc must pin 3.44.1")
    else:
        harmony = read_json(
            project / ".elmos-harmony-runner.json", f"{profile_id} harmony runner"
        )
        if harmony != {
            "schemaVersion": "1.0",
            "sdk": "6.0.0(20)",
            "apiLevel": 20,
            "runnerProfile": "harmonyos-6.0.0-api20",
            "signing": "NOT_RUN",
            "deviceEvidence": "NOT_RUN",
        }:
            raise ValidationError("Harmony runner profile is not exact")


def validate_node_project(profile_id: str, project: Path) -> None:
    package = read_json(project / "package.json", f"{profile_id} package.json")
    expected = EXPECTED_NODE_PACKAGES[profile_id]
    if package.get("engines") != {"node": "26.0.0"}:
        raise ValidationError(f"{profile_id} must pin Node 26.0.0")
    if package.get("packageManager") != "npm@11.12.1":
        raise ValidationError(f"{profile_id} must pin npm 11.12.1")
    for field in ("scripts", "dependencies", "devDependencies"):
        if package.get(field) != expected[field]:
            raise ValidationError(f"{profile_id} package {field} drift")
    for field in ("dependencies", "devDependencies"):
        if any(
            not EXACT_VERSION_PATTERN.fullmatch(value)
            for value in package[field].values()
        ):
            raise ValidationError(
                f"{profile_id} contains a non-exact dependency version"
            )
    if (project / ".nvmrc").read_text(encoding="utf-8") != "26.0.0\n":
        raise ValidationError(f"{profile_id} .nvmrc drift")
    expected_npmrc = "save-exact=true\npackage-lock=true\nengine-strict=true\nfund=false\naudit=true\n"
    if (project / ".npmrc").read_text(encoding="utf-8") != expected_npmrc:
        raise ValidationError(f"{profile_id} .npmrc drift")
    lock_path = project / "package-lock.json"
    if lock_path.is_file():
        validate_node_package_lock(profile_id, package, lock_path)


def validate_node_package_lock(
    profile_id: str, package: Mapping[str, Any], lock_path: Path
) -> dict[str, Any]:
    lock = read_json(lock_path, f"{profile_id} package-lock.json")
    packages = lock.get("packages")
    root = packages.get("") if isinstance(packages, dict) else None
    if (
        lock.get("lockfileVersion") != 3
        or not isinstance(lock.get("name"), str)
        or lock.get("name") != package.get("name")
        or not isinstance(packages, dict)
        or not isinstance(root, dict)
        or root.get("dependencies", {}) != package.get("dependencies", {})
        or root.get("devDependencies", {}) != package.get("devDependencies", {})
    ):
        raise ValidationError(f"{profile_id} package lock root binding drift")
    for relative, entry in packages.items():
        if not isinstance(relative, str) or not isinstance(entry, dict):
            raise ValidationError(f"{profile_id} package lock entry is invalid")
        if entry.get("resolved") is not None and not isinstance(
            entry.get("resolved"), str
        ):
            raise ValidationError(
                f"{profile_id} package lock resolved value is invalid"
            )
        if entry.get("integrity") is not None and not isinstance(
            entry.get("integrity"), str
        ):
            raise ValidationError(
                f"{profile_id} package lock integrity value is invalid"
            )
    return lock


def json_pointer_rows(value: Any, pointer: str = "") -> dict[str, Any]:
    rows = {pointer: value}
    if isinstance(value, dict):
        for key in sorted(value):
            escaped = key.replace("~", "~0").replace("/", "~1")
            rows.update(json_pointer_rows(value[key], f"{pointer}/{escaped}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.update(json_pointer_rows(item, f"{pointer}/{index}"))
    return rows


def expected_behavior_observations(model: Mapping[str, Any]) -> list[dict[str, Any]]:
    routes = model["routes"]
    render = {
        "navigationLabel": model["navigation"]["label"],
        "mainRole": model["render"]["mainRole"],
        "headingLevel": model["render"]["headingLevel"],
    }
    result = [
        {
            "operation": "INITIAL_RENDER",
            "input_path": None,
            "resolution": "FIRST_DECLARED_FALLBACK",
            "route": routes[0],
            "render": render,
        }
    ]
    result.extend(
        {
            "operation": "SELECT_DECLARED_PATH",
            "input_path": route["path"],
            "resolution": "DECLARED",
            "route": route,
            "render": render,
        }
        for route in routes
    )
    result.append(
        {
            "operation": "SELECT_UNKNOWN_PATH",
            "input_path": "/__elmos_unknown_route__",
            "resolution": "FIRST_DECLARED_FALLBACK",
            "route": routes[0],
            "render": render,
        }
    )
    return result


def behavior_observations(value: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or not isinstance(value.get("observations"), list):
        raise ValidationError(f"{name} observations are absent")
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(value["observations"]):
        if not isinstance(raw, dict) or not isinstance(raw.get("trace_id"), str):
            raise ValidationError(f"{name} observation[{index}] is invalid")
        result.append({key: item for key, item in raw.items() if key != "trace_id"})
    return result


def node_platform_name() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "win32":
        return "win32"
    return sys.platform


def node_arch_name() -> str:
    machine = platform.machine().lower()
    return {
        "aarch64": "arm64",
        "amd64": "x64",
        "arm64": "arm64",
        "x86_64": "x64",
    }.get(machine, machine)


def validate_solver_result(
    *,
    route_id: str,
    route_status: str,
    formal_input_digest: str,
    smt_path: Path,
    smt_digest: str,
    solver_path: Path,
    verified_binaries: dict[str, tuple[str, str]],
    expected_outcome: str | None = None,
    precheck: bool = False,
    extra_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and replay the immutable locked-Z3 result for one route."""

    expected_extra = dict(extra_fields or {})
    solver = require_exact_keys(
        read_json(solver_path, f"{route_id} solver result"),
        SOLVER_RESULT_KEYS
        | ({"precheck_status"} if precheck else set())
        | set(expected_extra),
        f"{route_id} solver result",
    )
    options = require_exact_keys(
        solver.get("options"), {"args", "timeout_ms"}, f"{route_id} solver options"
    )
    environment = require_exact_keys(
        solver.get("environment"),
        {"platform", "arch", "node_version"},
        f"{route_id} solver environment",
    )
    timeout_ms = options.get("timeout_ms")
    if (
        options.get("args") != LOCKED_Z3_ARGS
        or type(timeout_ms) is not int
        or timeout_ms <= 0
        or timeout_ms > 60_000
        or environment.get("platform") != node_platform_name()
        or environment.get("arch") != node_arch_name()
        or not isinstance(environment.get("node_version"), str)
        or not re.fullmatch(r"v[0-9]+(?:\.[0-9]+){2}", environment["node_version"])
    ):
        raise ValidationError(f"{route_id} solver options/environment drifted")
    if (
        solver.get("schema_version") != SCHEMA_VERSION
        or solver.get("route_id") != route_id
        or solver.get("formal_input_digest") != formal_input_digest
        or solver.get("solver_input_digest") != smt_digest
        or solver.get("smt2_digest") != smt_digest
        or solver.get("unconditional_proof") is not False
        or any(solver.get(key) != value for key, value in expected_extra.items())
    ):
        raise ValidationError(f"{route_id} solver result binding mismatch")

    identity_status = solver.get("identity_status")
    if identity_status == "REJECTED":
        if (
            route_status != "NOT_PROVED"
            or solver.get("proof_status") != "NOT_PROVED"
            or solver.get("outcome") not in {"MISSING", "ERROR"}
            or solver.get("exit_code") is not None
            or solver.get("stdout") != ""
            or not isinstance(solver.get("stderr"), str)
            or not solver["stderr"]
        ):
            raise ValidationError(
                f"{route_id} rejected solver identity cannot support proof evidence"
            )
        return solver
    if identity_status != "VERIFIED":
        raise ValidationError(f"{route_id} solver identity status is invalid")

    binary_value = solver.get("solver_binary_realpath")
    if not isinstance(binary_value, str) or not binary_value:
        raise ValidationError(f"{route_id} locked solver identity is absent")
    binary_path = Path(binary_value)
    try:
        resolved_binary = binary_path.resolve(strict=True)
    except OSError as error:
        raise ValidationError(
            f"{route_id} locked solver binary is unavailable"
        ) from error
    if (
        not binary_path.is_absolute()
        or resolved_binary != binary_path
        or not binary_path.is_file()
        or not os.access(binary_path, os.X_OK)
        or binary_path.name != "z3"
        or solver.get("solver") != binary_value
        or solver.get("solver_binary_sha256") != LOCKED_Z3_BINARY_SHA256
        or solver.get("solver_version") != LOCKED_Z3_VERSION
        or solver.get("invocation") != [binary_value, *LOCKED_Z3_ARGS]
    ):
        raise ValidationError(f"{route_id} locked solver identity drifted")

    cached_identity = verified_binaries.get(binary_value)
    if cached_identity is None:
        actual_digest = sha256_bytes(binary_path.read_bytes())
        if actual_digest != LOCKED_Z3_BINARY_SHA256:
            raise ValidationError(f"{route_id} locked solver binary digest drifted")
        try:
            version_result = subprocess.run(
                [binary_value, "-version"],
                check=False,
                cwd=binary_path.parent,
                env={"LANG": "C", "LC_ALL": "C"},
                input=b"",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=min(timeout_ms / 1000, 5),
                start_new_session=True,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValidationError(
                f"{route_id} locked solver version execution failed"
            ) from error
        expected_version_stdout = (LOCKED_Z3_VERSION + "\n").encode("utf-8")
        if (
            version_result.returncode != 0
            or version_result.stdout != expected_version_stdout
            or version_result.stderr != b""
        ):
            raise ValidationError(f"{route_id} locked solver version drifted")
        cached_identity = (actual_digest, LOCKED_Z3_VERSION)
        verified_binaries[binary_value] = cached_identity
    if cached_identity != (LOCKED_Z3_BINARY_SHA256, LOCKED_Z3_VERSION):
        raise ValidationError(f"{route_id} locked solver cached identity drifted")

    outcome = solver.get("outcome")
    expected_stdout = {
        "UNSAT": "unsat\n",
        "SAT": "sat\n",
        "UNKNOWN": "unknown\n",
    }.get(outcome)
    expected_proof_status = {
        "UNSAT": "PROVED_UNDER_ASSUMPTIONS",
        "SAT": "REFUTED",
        "UNKNOWN": "NOT_PROVED",
    }.get(outcome)
    if (
        expected_stdout is None
        or (expected_outcome is not None and outcome != expected_outcome)
        or (precheck and solver.get("precheck_status") != "PASSED")
        or solver.get("exit_code") != 0
        or solver.get("stdout") != expected_stdout
        or solver.get("stderr") != ""
        or solver.get("proof_status") != expected_proof_status
    ):
        raise ValidationError(f"{route_id} solver result binding mismatch")

    try:
        replay = subprocess.run(
            [binary_value, *LOCKED_Z3_ARGS],
            check=False,
            cwd=binary_path.parent,
            env={"LANG": "C", "LC_ALL": "C"},
            input=smt_path.read_bytes(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_ms / 1000,
            start_new_session=True,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValidationError(f"{route_id} locked solver replay failed") from error
    if (
        replay.returncode != solver["exit_code"]
        or replay.stdout != expected_stdout.encode("utf-8")
        or replay.stderr != b""
    ):
        raise ValidationError(f"{route_id} locked solver replay diverged")
    return {
        **solver,
        "runner_replay": {
            "status": "PASSED",
            "argv": [binary_value, *LOCKED_Z3_ARGS],
            "cwd": str(binary_path.parent),
            "environment": {"LANG": "C", "LC_ALL": "C"},
            "exit_code": replay.returncode,
            "stdout": replay.stdout.decode("utf-8"),
            "stderr": replay.stderr.decode("utf-8"),
            "solver_binary_sha256": LOCKED_Z3_BINARY_SHA256,
            "solver_version": LOCKED_Z3_VERSION,
            "solver_input_digest": smt_digest,
        },
    }


def validate_route_evidence(
    root: Path,
    row: Mapping[str, Any],
    profiles: Mapping[str, ProfileArtifact],
    formal_input: Mapping[str, Any],
    verified_binaries: dict[str, tuple[str, str]],
) -> None:
    route_id = row["route_id"]
    source = profiles[row["source_profile"]]
    target = profiles[row["target_profile"]]
    canonical_model = validate_navigation_model(
        route_id, formal_input.get("canonical_model")
    )
    canonical_digest = digest_json(canonical_model)
    if (
        formal_input.get("schema_version") != SCHEMA_VERSION
        or formal_input.get("kind") != "frontend-bounded-navigation-formal-input"
        or formal_input.get("proof_profile") != PROOF_PROFILE
        or formal_input.get("route_id") != route_id
        or formal_input.get("source_project_digest") != source.project_digest
        or formal_input.get("target_project_digest") != target.project_digest
        or formal_input.get("canonical_model_digest") != canonical_digest
        or formal_input.get("source_model_digest") != source.relift_model_digest
        or formal_input.get("target_model_digest") != target.relift_model_digest
    ):
        raise ValidationError(f"{route_id} formal input binding mismatch")
    tuple_value = formal_input.get("tuple")
    if tuple_value != {
        "source_profile": source.profile_id,
        "source_framework_version": source.framework_version,
        "target_profile": target.profile_id,
        "target_framework_version": target.framework_version,
    }:
        raise ValidationError(f"{route_id} formal tuple mismatch")
    for key in ("semantic_equal", "behavior_equal", "chunk_equal"):
        if type(formal_input.get(key)) is not bool:
            raise ValidationError(f"{route_id} formal {key} is not boolean")
    semantic_equal = (
        canonical_json(canonical_model)
        == canonical_json(source.relift_model)
        == canonical_json(target.relift_model)
    )
    if formal_input.get("semantic_equal") is not semantic_equal:
        raise ValidationError(f"{route_id} semantic equivalence binding mismatch")
    if formal_input.get("arbitrary_customer_source") != "NOT_PROVED":
        raise ValidationError(f"{route_id} arbitrary-source boundary is invalid")
    if formal_input.get("compiler_framework_runtime_soundness") != "ASSUMED_NOT_PROVED":
        raise ValidationError(f"{route_id} runtime soundness boundary is invalid")

    layered = read_json(
        resolve_regular_file(root, row["evidence_path"], f"{route_id}.evidence_path"),
        f"{route_id} layered result",
    )
    if (
        layered.get("schema_version") != SCHEMA_VERSION
        or layered.get("kind") != "frontend-bounded-navigation-layered-result"
        or layered.get("route_id") != route_id
        or layered.get("proof_profile") != PROOF_PROFILE
        or layered.get("status") != row["status"]
        or layered.get("unconditional_proof") is not False
        or layered.get("certification") != "NOT_CERTIFIED"
        or layered.get("assumptions") != formal_input.get("assumptions")
    ):
        raise ValidationError(f"{route_id} layered result binding mismatch")
    links = layered.get("links")
    if not isinstance(links, dict):
        raise ValidationError(f"{route_id} layered links are absent")
    expected_prefix = f"routes/{route_id}/"
    expected_paths = {
        "formal_input_path": row["formal_input_path"],
        "smt2_path": expected_prefix + "proof.smt2",
        "solver_result_path": row["solver_result_path"],
        "behavior_path": expected_prefix + "behavior.json",
        "chunks_path": expected_prefix + "chunks.json",
        "composition_path": expected_prefix + "composition.json",
    }
    if any(links.get(key) != value for key, value in expected_paths.items()):
        raise ValidationError(f"{route_id} layered artifact paths are not canonical")
    if links.get("formal_input_digest") != row["formal_input_digest"]:
        raise ValidationError(f"{route_id} layered formal digest mismatch")

    artifacts = {
        key: resolve_regular_file(root, value, f"{route_id}.{key}")
        for key, value in expected_paths.items()
    }
    smt_digest = sha256_bytes(artifacts["smt2_path"].read_bytes())
    if links.get("smt2_digest") != smt_digest:
        raise ValidationError(f"{route_id} SMT digest mismatch")
    behavior = read_json(artifacts["behavior_path"], f"{route_id} behavior")
    chunks = read_json(artifacts["chunks_path"], f"{route_id} chunks")
    composition = read_json(artifacts["composition_path"], f"{route_id} composition")
    for artifact_path_key, digest_key, value in (
        ("behavior_path", "behavior_digest", formal_input.get("behavior_digest")),
        ("chunks_path", "chunks_digest", formal_input.get("chunk_digest")),
        (
            "composition_path",
            "composition_digest",
            links.get("composition_digest"),
        ),
    ):
        computed = sha256_bytes(artifacts[artifact_path_key].read_bytes())
        if links.get(digest_key) != computed or value != computed:
            raise ValidationError(f"{route_id} {digest_key} mismatch")

    expected_behaviors = {
        "canonical": expected_behavior_observations(canonical_model),
        "independent": expected_behavior_observations(canonical_model),
        "source": expected_behavior_observations(source.relift_model),
        "target": expected_behavior_observations(target.relift_model),
    }
    actual_behaviors = {
        name: behavior_observations(behavior.get(name), f"{route_id} {name}")
        for name in expected_behaviors
    }
    if actual_behaviors != expected_behaviors:
        raise ValidationError(f"{route_id} behavior observations mismatch")
    behavior_equivalent = (
        len({canonical_json(value) for value in actual_behaviors.values()}) == 1
    )
    if (
        behavior.get("schema_version") != SCHEMA_VERSION
        or behavior.get("equivalent") is not behavior_equivalent
        or formal_input.get("behavior_equal") is not behavior_equivalent
        or behavior.get("native_browser_or_device_evidence") != "NOT_RUN"
        or not isinstance(behavior.get("domain"), dict)
        or behavior["domain"].get("framework_native_runtime") != "NOT_RUN"
    ):
        raise ValidationError(f"{route_id} behavior equivalence binding mismatch")

    chunk_rows = chunks.get("chunks")
    pointers = json_pointer_rows(canonical_model)
    if not isinstance(chunk_rows, list) or len(chunk_rows) != len(pointers):
        raise ValidationError(f"{route_id} chunk coverage is incomplete")
    source_bytes = source.project_path.joinpath(
        *PurePosixPath(source.navigation_source_path).parts
    ).read_bytes()
    target_bytes = target.project_path.joinpath(
        *PurePosixPath(target.navigation_source_path).parts
    ).read_bytes()
    seen_pointers: set[str] = set()
    all_equivalent = True
    for index, raw_chunk in enumerate(chunk_rows):
        if not isinstance(raw_chunk, dict):
            raise ValidationError(f"{route_id} chunk[{index}] is invalid")
        pointer = raw_chunk.get("pointer")
        if pointer not in pointers or pointer in seen_pointers:
            raise ValidationError(f"{route_id} chunk[{index}] pointer is invalid")
        seen_pointers.add(pointer)
        subtree_digest = digest_json(pointers[pointer])
        if (
            raw_chunk.get("pointer_standard") != "RFC6901"
            or raw_chunk.get("canonical_subtree_hash") != subtree_digest
        ):
            raise ValidationError(
                f"{route_id} chunk[{index}] canonical binding mismatch"
            )
        for side, profile, content in (
            ("source", source, source_bytes),
            ("target", target, target_bytes),
        ):
            span = raw_chunk.get(side)
            if (
                not isinstance(span, dict)
                or span.get("path") != profile.navigation_source_path
            ):
                raise ValidationError(f"{route_id} chunk[{index}] {side} path mismatch")
            start = span.get("start_byte")
            end = span.get("end_byte")
            if (
                type(start) is not int
                or type(end) is not int
                or start < 0
                or end <= start
                or end > len(content)
                or span.get("content_hash") != sha256_bytes(content[start:end])
                or span.get("subtree_hash") != subtree_digest
            ):
                raise ValidationError(f"{route_id} chunk[{index}] {side} span mismatch")
        equivalent = (
            raw_chunk.get("source_subtree_hash") == subtree_digest
            and raw_chunk.get("target_subtree_hash") == subtree_digest
            and raw_chunk.get("equivalent") is True
        )
        all_equivalent = all_equivalent and equivalent
    if seen_pointers != set(pointers):
        raise ValidationError(f"{route_id} chunk pointers are incomplete")
    if (
        chunks.get("schema_version") != SCHEMA_VERSION
        or chunks.get("route_id") != route_id
        or chunks.get("equivalent") is not all_equivalent
        or formal_input.get("chunk_equal") is not all_equivalent
    ):
        raise ValidationError(f"{route_id} chunk equivalence binding mismatch")

    equality = semantic_equal and behavior_equivalent and all_equivalent
    solver = validate_solver_result(
        route_id=route_id,
        route_status=row["status"],
        formal_input_digest=row["formal_input_digest"],
        smt_path=artifacts["smt2_path"],
        smt_digest=smt_digest,
        solver_path=artifacts["solver_result_path"],
        verified_binaries=verified_binaries,
    )
    expected_route_status = solver["proof_status"] if equality else "REFUTED"
    if row["status"] != expected_route_status:
        raise ValidationError(f"{route_id} proof status masks equivalence evidence")
    expected_composition = {
        "source_lifting": {
            "profile_id": source.profile_id,
            "project_digest": source.project_digest,
            "model_digest": source.relift_model_digest,
        },
        "target_lowering_relift": {
            "profile_id": target.profile_id,
            "project_digest": target.project_digest,
            "model_digest": target.relift_model_digest,
        },
    }
    if (
        composition.get("schema_version") != SCHEMA_VERSION
        or composition.get("route_id") != route_id
        or composition.get("source_lifting") != expected_composition["source_lifting"]
        or composition.get("target_lowering_relift")
        != expected_composition["target_lowering_relift"]
        or composition.get("canonical_model_digest") != canonical_digest
        or composition.get("semantic_equal") != formal_input.get("semantic_equal")
        or composition.get("chunk_equal") != formal_input.get("chunk_equal")
        or composition.get("behavior_equal") != formal_input.get("behavior_equal")
        or composition.get("solver_outcome") != solver.get("outcome")
        or composition.get("status") != row["status"]
    ):
        raise ValidationError(f"{route_id} composition binding mismatch")

    layers = layered.get("layers")
    if not isinstance(layers, dict):
        raise ValidationError(f"{route_id} layered statuses are absent")
    expected_layer_statuses = {
        "emitted_source_relift": "PASSED",
        "emitted_target_relift": "PASSED",
        "semantic": "PASSED" if semantic_equal else "FAILED",
        "chunk": "PASSED" if all_equivalent else "FAILED",
        "behavior": "PASSED" if behavior_equivalent else "FAILED",
        "smt_solver": solver["outcome"],
        "framework_native_build": "NOT_RUN",
        "framework_native_runtime": "NOT_RUN",
        "independent_external_verification": "NOT_RUN",
    }
    if any(layers.get(key) != value for key, value in expected_layer_statuses.items()):
        raise ValidationError(f"{route_id} layered runtime boundary mismatch")


def load_navigation_campaign(path: Path) -> LoadedCampaign:
    path = path.resolve()
    campaign = require_exact_keys(
        read_json(path, "frontend formal campaign"),
        {
            "schema_version",
            "kind",
            "proof_profile",
            "corpus_id",
            "profile_count",
            "route_count",
            "profiles",
            "source_liftings",
            "target_lowerings",
            "routes",
            "counts",
            "semantic_blocks",
            "assumptions",
            "arbitrary_customer_source",
            "unconditional_proof",
            "native_build_and_runtime",
            "independent_external_verification",
            "certification",
        },
        "frontend formal campaign",
    )
    if campaign.get("schema_version") != SCHEMA_VERSION:
        raise ValidationError("campaign schema_version is unsupported")
    if campaign["kind"] != CAMPAIGN_KIND:
        raise ValidationError("campaign kind is unsupported")
    if campaign.get("proof_profile") != PROOF_PROFILE:
        raise ValidationError("campaign proof_profile is unsupported")
    profiles_value = campaign.get("profiles")
    routes_value = campaign.get("routes")
    if not isinstance(profiles_value, list) or not isinstance(routes_value, list):
        raise ValidationError("campaign profiles and routes must be arrays")
    if len(profiles_value) != len(EXPECTED_PROFILES):
        raise ValidationError("campaign must contain exactly nine profiles")
    if (
        campaign["corpus_id"] != "frontend-bounded-navigation-corpus-v1"
        or campaign["profile_count"] != 9
        or campaign["route_count"] != 72
        or not isinstance(campaign["assumptions"], list)
        or not campaign["assumptions"]
        or campaign["arbitrary_customer_source"] != "NOT_PROVED"
        or campaign["unconditional_proof"] is not False
        or campaign["native_build_and_runtime"] != "NOT_RUN"
        or campaign["independent_external_verification"] != "NOT_RUN"
        or campaign["certification"] != "NOT_CERTIFIED"
    ):
        raise ValidationError("campaign proof boundary is invalid")
    root = path.parent
    profiles: dict[str, ProfileArtifact] = {}
    profile_keys = {
        "profile_id",
        "framework_version",
        "platforms",
        "project_path",
        "project_digest",
        "manifest_path",
        "manifest_digest",
        "navigation_source_path",
        "relift_model_digest",
        "target_build",
    }
    for index, value in enumerate(profiles_value):
        row = require_exact_keys(value, profile_keys, f"profiles[{index}]")
        profile_id = row.get("profile_id")
        if profile_id not in EXPECTED_PROFILES or profile_id in profiles:
            raise ValidationError(
                f"profiles[{index}] has an unknown or duplicate profile_id"
            )
        if not isinstance(row.get("platforms"), list):
            raise ValidationError(f"{profile_id} platforms must be an array")
        profiles[profile_id] = validate_project_manifest(
            root, row, EXPECTED_PROFILES[profile_id]
        )
    if set(profiles) != set(EXPECTED_PROFILES):
        raise ValidationError("campaign profile matrix is incomplete")
    expected_source_liftings = [
        {
            "profile_id": profile.profile_id,
            "project_digest": profile.project_digest,
            "relift_model_digest": profile.relift_model_digest,
            "status": "PASSED",
        }
        for profile in sorted(profiles.values(), key=lambda item: item.profile_id)
    ]
    expected_target_lowerings = [
        {
            "profile_id": profile.profile_id,
            "project_digest": profile.project_digest,
            "emitted_project": "PASSED",
            "relift": "PASSED",
        }
        for profile in sorted(profiles.values(), key=lambda item: item.profile_id)
    ]
    if campaign["source_liftings"] != expected_source_liftings:
        raise ValidationError("campaign source lifting bindings are invalid")
    if campaign["target_lowerings"] != expected_target_lowerings:
        raise ValidationError("campaign target lowering bindings are invalid")

    route_keys = {
        "route_id",
        "source_profile",
        "target_profile",
        "source_project_digest",
        "target_project_digest",
        "evidence_path",
        "formal_input_path",
        "formal_input_digest",
        "solver_result_path",
        "layered_result",
        "status",
    }
    allowed_statuses = {"PROVED_UNDER_ASSUMPTIONS", "REFUTED", "NOT_PROVED"}
    expected_pairs = {
        (source, target)
        for source in EXPECTED_PROFILES
        for target in EXPECTED_PROFILES
        if source != target
    }
    seen_pairs: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()
    routes: list[dict[str, Any]] = []
    verified_binaries: dict[str, tuple[str, str]] = {}
    for index, value in enumerate(routes_value):
        row = require_exact_keys(value, route_keys, f"routes[{index}]")
        route_id = row.get("route_id")
        source = row.get("source_profile")
        target = row.get("target_profile")
        if not isinstance(route_id, str) or not route_id or route_id in seen_ids:
            raise ValidationError(f"routes[{index}] route_id is invalid or duplicate")
        pair = (source, target)
        if pair not in expected_pairs or pair in seen_pairs:
            raise ValidationError(f"routes[{index}] pair is invalid or duplicate")
        if route_id != f"{source}--to--{target}":
            raise ValidationError(f"routes[{index}] route_id is not canonical")
        if row["source_project_digest"] != profiles[source].project_digest:
            raise ValidationError(f"{route_id} source project digest mismatch")
        if row["target_project_digest"] != profiles[target].project_digest:
            raise ValidationError(f"{route_id} target project digest mismatch")
        status = row.get("status")
        if status not in allowed_statuses or row.get("layered_result") != status:
            raise ValidationError(
                f"{route_id} has an invalid or inconsistent proof status"
            )
        expected_prefix = f"routes/{route_id}/"
        if row["evidence_path"] != expected_prefix + "layered-result.json":
            raise ValidationError(f"{route_id} evidence path is not canonical")
        for field in ("evidence_path", "formal_input_path", "solver_result_path"):
            if not str(row[field]).startswith(expected_prefix):
                raise ValidationError(
                    f"{route_id} {field} is outside its route directory"
                )
            resolve_regular_file(root, row[field], f"{route_id}.{field}")
        formal_input_path = resolve_regular_file(
            root, row["formal_input_path"], f"{route_id}.formal_input_path"
        )
        formal_digest = require_sha256(
            row["formal_input_digest"], f"{route_id}.formal_input_digest"
        )
        formal_input = read_json(formal_input_path, f"{route_id} formal input")
        if sha256_bytes(formal_input_path.read_bytes()) != formal_digest:
            raise ValidationError(f"{route_id} formal input digest mismatch")
        if formal_input.get("assumptions") != campaign["assumptions"]:
            raise ValidationError(f"{route_id} formal assumptions mismatch")
        validate_route_evidence(root, row, profiles, formal_input, verified_binaries)
        seen_ids.add(route_id)
        seen_pairs.add(pair)
        routes.append(dict(row))
    if seen_pairs != expected_pairs or len(routes) != 72:
        missing = sorted(expected_pairs - seen_pairs)
        raise ValidationError(f"campaign route matrix is incomplete: {missing}")
    counts = {
        status: sum(route["status"] == status for route in routes)
        for status in ("PROVED_UNDER_ASSUMPTIONS", "REFUTED", "NOT_PROVED")
    }
    if campaign["counts"] != counts:
        raise ValidationError("campaign proof status counts mismatch")
    semantic_blocks = campaign["semantic_blocks"]
    if (
        not isinstance(semantic_blocks, dict)
        or semantic_blocks.get("proved") != [PROOF_PROFILE]
        or semantic_blocks.get("externally_composable_not_run")
        != ["component-dialect-engine/certified-component-v1"]
        or not isinstance(semantic_blocks.get("unsupported_not_proved"), list)
        or not semantic_blocks["unsupported_not_proved"]
    ):
        raise ValidationError("campaign semantic block boundary is invalid")
    return LoadedCampaign(
        path=path,
        root=root.resolve(),
        digest=sha256_bytes(path.read_bytes()),
        byte_count=path.stat().st_size,
        profiles=profiles,
        routes=tuple(routes),
    )


INTERACTION_FORMAL_INPUT_KEYS = {
    "schema_version",
    "kind",
    "corpus_id",
    "proof_profile",
    "proof_scope",
    "route_id",
    "tuple",
    "source_project_digest",
    "target_project_digest",
    "canonical_model",
    "canonical_model_digest",
    "canonical_block_digests",
    "source_model_digest",
    "target_model_digest",
    "source_block_digests",
    "target_block_digests",
    "source_model_artifact_digest",
    "target_model_artifact_digest",
    "semantic_equal",
    "behavior_digest",
    "behavior_equal",
    "chunk_digest",
    "chunk_equal",
    "scenario_manifest_digest",
    "mutation_campaign_digest",
    "semantic_block_ids",
    "block_symbol_map",
    "influence_classes",
    "runtime_evidence_eligibility",
    "oracle_provenance",
    "arbitrary_customer_source",
    "compiler_framework_runtime_soundness",
    "assumptions",
}
INTERACTION_BLOCK_RESULT_KEYS = {
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
INTERACTION_LAYER_LINK_KEYS = {
    "source_model_path",
    "target_model_path",
    "behavior_path",
    "chunks_path",
    "formal_input_path",
    "smt2_path",
    "solver_result_path",
    "vacuity_input_path",
    "vacuity_solver_result_path",
    "block_results_path",
    "composition_path",
    "layered_result_path",
    "source_model_digest",
    "target_model_digest",
    "behavior_digest",
    "chunks_digest",
    "formal_input_digest",
    "smt2_digest",
    "solver_result_digest",
    "vacuity_input_digest",
    "vacuity_solver_result_digest",
    "block_results_digest",
    "composition_digest",
    "mutation_campaign_digest",
}


def read_bound_interaction_json(
    root: Path, path_value: Any, digest_value: Any, name: str
) -> tuple[Path, dict[str, Any]]:
    path = resolve_regular_file(root, path_value, name)
    digest = require_sha256(digest_value, f"{name}.digest")
    if sha256_bytes(path.read_bytes()) != digest:
        raise ValidationError(f"{name} byte digest mismatch")
    return path, read_json(path, name)


def validate_interaction_model_artifact(
    *,
    artifact: dict[str, Any],
    artifact_path: Path,
    profile: ProfileArtifact,
    expected_digest: str,
    name: str,
) -> None:
    require_exact_keys(
        artifact,
        {
            "schema_version",
            "proof_profile",
            "profile_id",
            "parser",
            "source_path",
            "source_hash",
            "model",
            "model_digest",
            "block_digests",
            "spans",
            "consumer_binding",
        },
        name,
    )
    source_path = profile.project_path.joinpath(
        *PurePosixPath(profile.interaction_source_path or "").parts
    )
    consumer_binding = artifact["consumer_binding"]
    if (
        artifact["schema_version"] != SCHEMA_VERSION
        or artifact["proof_profile"] != INTERACTION_PROOF_PROFILE
        or artifact["profile_id"] != profile.profile_id
        or not isinstance(artifact["parser"], str)
        or artifact["source_path"] != profile.interaction_source_path
        or artifact["source_hash"] != sha256_bytes(source_path.read_bytes())
        or artifact["model"] != profile.relift_model
        or artifact["model_digest"] != profile.relift_model_digest
        or artifact["block_digests"] != profile.relift_block_digests
        or not isinstance(artifact["spans"], dict)
        or not isinstance(consumer_binding, dict)
        or not consumer_binding
        or any(value is not True for value in consumer_binding.values())
        or sha256_bytes(artifact_path.read_bytes()) != expected_digest
    ):
        raise ValidationError(f"{name} re-lift artifact binding drift")


def validate_interaction_route_evidence(
    *,
    root: Path,
    row: Mapping[str, Any],
    profiles: Mapping[str, ProfileArtifact],
    assumptions: list[Any],
    scenario_digest: str,
    mutation_digest: str,
    verified_binaries: dict[str, tuple[str, str]],
) -> dict[str, Any]:
    route_id = str(row["route_id"])
    source = profiles[str(row["source_profile"])]
    target = profiles[str(row["target_profile"])]
    prefix = f"routes/{route_id}/"
    expected_paths = {
        "source_model_path": prefix + "source-model.json",
        "target_model_path": prefix + "target-model.json",
        "behavior_path": row["behavior_path"],
        "chunks_path": row["chunks_path"],
        "formal_input_path": row["formal_input_path"],
        "smt2_path": row["solver_input_path"],
        "solver_result_path": row["solver_result_path"],
        "vacuity_input_path": row["vacuity_input_path"],
        "vacuity_solver_result_path": row["vacuity_solver_result_path"],
        "block_results_path": row["block_results_path"],
        "composition_path": row["composition_path"],
        "layered_result_path": row["evidence_path"],
    }
    formal_path, formal = read_bound_interaction_json(
        root,
        row["formal_input_path"],
        row["formal_input_digest"],
        f"{route_id}.formal",
    )
    require_exact_keys(formal, INTERACTION_FORMAL_INPUT_KEYS, f"{route_id}.formal")
    canonical_model = validate_interaction_model(route_id, formal["canonical_model"])
    canonical_digest = digest_json(canonical_model)
    expected_block_map = {
        block_id: digest_json(canonical_model[field])
        for block_id, field in INTERACTION_MODEL_BLOCK_FIELDS.items()
    }
    expected_symbol_map = {
        block_id: symbol for symbol, block_id in INTERACTION_BLOCK_SYMBOLS.items()
    }
    influence_classes = formal["influence_classes"]
    if (
        formal["schema_version"] != SCHEMA_VERSION
        or formal["kind"] != "frontend-bounded-interaction-formal-input"
        or formal["corpus_id"] != "frontend-bounded-interaction-corpus-v1"
        or formal["proof_profile"] != INTERACTION_PROOF_PROFILE
        or formal["route_id"] != route_id
        or formal["tuple"]
        != {
            "source_profile": source.profile_id,
            "source_framework_version": source.framework_version,
            "target_profile": target.profile_id,
            "target_framework_version": target.framework_version,
        }
        or formal["source_project_digest"] != source.project_digest
        or formal["target_project_digest"] != target.project_digest
        or formal["canonical_model_digest"] != canonical_digest
        or formal["canonical_block_digests"] != expected_block_map
        or formal["source_model_digest"] != source.relift_model_digest
        or formal["target_model_digest"] != target.relift_model_digest
        or formal["source_block_digests"] != source.relift_block_digests
        or formal["target_block_digests"] != target.relift_block_digests
        or formal["semantic_equal"] is not True
        or formal["behavior_digest"] != row["behavior_digest"]
        or formal["behavior_equal"] is not True
        or formal["chunk_digest"] != row["chunks_digest"]
        or formal["chunk_equal"] is not True
        or formal["scenario_manifest_digest"] != scenario_digest
        or formal["mutation_campaign_digest"] != mutation_digest
        or formal["semantic_block_ids"] != list(INTERACTION_BLOCK_IDS)
        or formal["block_symbol_map"] != expected_symbol_map
        or not isinstance(influence_classes, dict)
        or set(influence_classes) != {"model", "runtime"}
        or any(
            not isinstance(influence_classes[kind], dict)
            or tuple(influence_classes[kind]) != INTERACTION_BLOCK_IDS
            for kind in ("model", "runtime")
        )
        or formal["runtime_evidence_eligibility"] != "INELIGIBLE_SAME_PRODUCER"
        or formal["oracle_provenance"]
        != {
            "independence": "NOT_INDEPENDENT_SINGLE_ENGINE",
            "formal_input_from_solver_result": False,
            "oracle_from_solver_result": False,
        }
        or formal["arbitrary_customer_source"] != "NOT_PROVED"
        or formal["compiler_framework_runtime_soundness"] != "ASSUMED_NOT_PROVED"
        or formal["assumptions"] != assumptions
    ):
        raise ValidationError(f"{route_id} formal evidence binding drift")

    layered_path, layered = read_bound_interaction_json(
        root, row["evidence_path"], row["evidence_digest"], f"{route_id}.layered"
    )
    require_exact_keys(
        layered,
        {
            "schema_version",
            "kind",
            "route_id",
            "proof_profile",
            "links",
            "layers",
            "oracle_provenance",
            "runtime_evidence_eligibility",
            "status",
            "unconditional_proof",
            "certification",
            "assumptions",
        },
        f"{route_id}.layered",
    )
    links = require_exact_keys(
        layered["links"], INTERACTION_LAYER_LINK_KEYS, f"{route_id}.layered.links"
    )
    source_model_path, source_model = read_bound_interaction_json(
        root,
        links["source_model_path"],
        links["source_model_digest"],
        f"{route_id}.source-model",
    )
    target_model_path, target_model = read_bound_interaction_json(
        root,
        links["target_model_path"],
        links["target_model_digest"],
        f"{route_id}.target-model",
    )
    validate_interaction_model_artifact(
        artifact=source_model,
        artifact_path=source_model_path,
        profile=source,
        expected_digest=formal["source_model_artifact_digest"],
        name=f"{route_id}.source-model",
    )
    validate_interaction_model_artifact(
        artifact=target_model,
        artifact_path=target_model_path,
        profile=target,
        expected_digest=formal["target_model_artifact_digest"],
        name=f"{route_id}.target-model",
    )
    expected_link_digests = {
        "behavior_digest": row["behavior_digest"],
        "chunks_digest": row["chunks_digest"],
        "formal_input_digest": row["formal_input_digest"],
        "smt2_digest": row["solver_input_digest"],
        "solver_result_digest": row["solver_result_digest"],
        "vacuity_input_digest": row["vacuity_input_digest"],
        "vacuity_solver_result_digest": row["vacuity_solver_result_digest"],
        "block_results_digest": row["block_results_digest"],
        "composition_digest": row["composition_digest"],
        "mutation_campaign_digest": mutation_digest,
    }
    if (
        any(links[key] != value for key, value in expected_paths.items())
        or any(links[key] != value for key, value in expected_link_digests.items())
        or layered["schema_version"] != SCHEMA_VERSION
        or layered["kind"] != "bounded-interaction-layered-result"
        or layered["route_id"] != route_id
        or layered["proof_profile"] != INTERACTION_PROOF_PROFILE
        or layered["oracle_provenance"] != "NOT_INDEPENDENT_SINGLE_ENGINE"
        or layered["runtime_evidence_eligibility"] != "INELIGIBLE_SAME_PRODUCER"
        or layered["status"] != row["status"]
        or layered["unconditional_proof"] is not False
        or layered["certification"] != "NOT_CERTIFIED"
        or layered["assumptions"] != assumptions
    ):
        raise ValidationError(f"{route_id} layered linkage drift")

    behavior_path, behavior = read_bound_interaction_json(
        root, row["behavior_path"], row["behavior_digest"], f"{route_id}.behavior"
    )
    del behavior_path
    require_exact_keys(
        behavior,
        {
            "schema_version",
            "kind",
            "domain",
            "canonical",
            "reference",
            "source",
            "target",
            "equivalent",
            "oracle_provenance",
            "runtime_evidence_eligibility",
        },
        f"{route_id}.behavior",
    )
    expected_runtime_kinds = {
        "canonical": "AUTHORITATIVE_MODEL_REDUCER",
        "reference": "SAME_ENGINE_SEPARATE_TABLE_REDUCER",
        "source": "RELIFTED_EMITTED_SOURCE_MODEL_REDUCER",
        "target": "RELIFTED_EMITTED_TARGET_MODEL_REDUCER",
    }
    observation_rows: list[Any] = []
    for side, runtime_kind in expected_runtime_kinds.items():
        side_value = require_exact_keys(
            behavior[side], {"runtime_kind", "observations"}, f"{route_id}.{side}"
        )
        observations = side_value["observations"]
        if (
            side_value["runtime_kind"] != runtime_kind
            or not isinstance(observations, list)
            or [item.get("scenarioId") for item in observations]
            != list(LOCKED_INTERACTION_SCENARIO_IDS)
            or any(
                not isinstance(item, dict)
                or not isinstance(item.get("blocks"), dict)
                or tuple(item["blocks"]) != INTERACTION_BLOCK_IDS
                for item in observations
            )
        ):
            raise ValidationError(f"{route_id}.{side} model observation closure drift")
        observation_rows.append(observations)
    if (
        behavior["schema_version"] != SCHEMA_VERSION
        or behavior["kind"] != "bounded-interaction-model-behavior"
        or behavior["domain"]
        != {
            "scenario_manifest_path": "scenario-corpus.json",
            "scenario_manifest_digest": scenario_digest,
            "scenario_count": len(LOCKED_INTERACTION_SCENARIO_IDS),
            "model_reducer": "BOUNDED_PURE_REDUCER",
            "browser_runtime": "NOT_RUN",
            "native_runtime": "NOT_RUN",
        }
        or len({canonical_json(value) for value in observation_rows}) != 1
        or behavior["equivalent"] is not True
        or behavior["oracle_provenance"]
        != {
            "independence": "NOT_INDEPENDENT_SINGLE_ENGINE",
            "solver_result_used_as_oracle": False,
            "runtime_observation_source": "NOT_RUN",
        }
        or behavior["runtime_evidence_eligibility"] != "INELIGIBLE_SAME_PRODUCER"
    ):
        raise ValidationError(f"{route_id} model behavior binding drift")

    chunks_path, chunks = read_bound_interaction_json(
        root, row["chunks_path"], row["chunks_digest"], f"{route_id}.chunks"
    )
    del chunks_path
    require_exact_keys(
        chunks,
        {"schema_version", "kind", "route_id", "chunks", "equivalent"},
        f"{route_id}.chunks",
    )
    pointers = json_pointer_rows(canonical_model)
    chunk_rows = chunks["chunks"]
    source_bytes = source.project_path.joinpath(
        *PurePosixPath(source.interaction_source_path or "").parts
    ).read_bytes()
    target_bytes = target.project_path.joinpath(
        *PurePosixPath(target.interaction_source_path or "").parts
    ).read_bytes()
    seen_pointers: set[str] = set()
    if not isinstance(chunk_rows, list) or len(chunk_rows) != len(pointers):
        raise ValidationError(f"{route_id} chunk closure drift")
    for index, raw_chunk in enumerate(chunk_rows):
        raw_chunk = require_exact_keys(
            raw_chunk,
            {
                "pointer",
                "pointer_standard",
                "block_id",
                "source",
                "target",
                "canonical_subtree_hash",
                "source_subtree_hash",
                "target_subtree_hash",
                "equivalent",
            },
            f"{route_id}.chunks[{index}]",
        )
        pointer = raw_chunk.get("pointer")
        if pointer not in pointers or pointer in seen_pointers:
            raise ValidationError(f"{route_id}.chunks[{index}] pointer drift")
        seen_pointers.add(pointer)
        subtree_digest = digest_json(pointers[pointer])
        if re.fullmatch(r"/navigation/routes/[0-9]+/(?:title|text)", str(pointer)):
            expected_block_id = "component-template-view"
        else:
            expected_block_id = next(
                (
                    block_id
                    for block_id, field in INTERACTION_MODEL_BLOCK_FIELDS.items()
                    if pointer == f"/{field}" or str(pointer).startswith(f"/{field}/")
                ),
                None,
            )
        if (
            raw_chunk.get("pointer_standard") != "RFC6901"
            or raw_chunk.get("block_id") != expected_block_id
            or raw_chunk.get("canonical_subtree_hash") != subtree_digest
            or raw_chunk.get("source_subtree_hash") != subtree_digest
            or raw_chunk.get("target_subtree_hash") != subtree_digest
            or raw_chunk.get("equivalent") is not True
        ):
            raise ValidationError(f"{route_id}.chunks[{index}] semantic drift")
        for side, profile, content in (
            ("source", source, source_bytes),
            ("target", target, target_bytes),
        ):
            span = require_exact_keys(
                raw_chunk.get(side),
                {"path", "start_byte", "end_byte", "content_hash", "subtree_hash"},
                f"{route_id}.chunks[{index}].{side}",
            )
            if span.get("path") != profile.interaction_source_path:
                raise ValidationError(f"{route_id}.chunks[{index}].{side} path drift")
            start = span.get("start_byte")
            end = span.get("end_byte")
            if (
                type(start) is not int
                or type(end) is not int
                or start < 0
                or end <= start
                or end > len(content)
                or span.get("content_hash") != sha256_bytes(content[start:end])
                or span.get("subtree_hash") != subtree_digest
            ):
                raise ValidationError(f"{route_id}.chunks[{index}].{side} span drift")
    if (
        seen_pointers != set(pointers)
        or chunks["schema_version"] != SCHEMA_VERSION
        or chunks["kind"] != "bounded-interaction-rfc6901-chunks"
        or chunks["route_id"] != route_id
        or chunks["equivalent"] is not True
    ):
        raise ValidationError(f"{route_id} chunk evidence binding drift")

    smt_path = resolve_regular_file(root, row["solver_input_path"], f"{route_id}.smt")
    vacuity_path = resolve_regular_file(
        root, row["vacuity_input_path"], f"{route_id}.vacuity"
    )
    solver = validate_solver_result(
        route_id=route_id,
        route_status=str(row["status"]),
        formal_input_digest=str(row["formal_input_digest"]),
        smt_path=smt_path,
        smt_digest=str(row["solver_input_digest"]),
        solver_path=resolve_regular_file(
            root, row["solver_result_path"], f"{route_id}.solver"
        ),
        verified_binaries=verified_binaries,
        expected_outcome="UNSAT",
    )
    vacuity_solver = validate_solver_result(
        route_id=route_id,
        route_status="REFUTED",
        formal_input_digest=str(row["formal_input_digest"]),
        smt_path=vacuity_path,
        smt_digest=str(row["vacuity_input_digest"]),
        solver_path=resolve_regular_file(
            root, row["vacuity_solver_result_path"], f"{route_id}.vacuity-solver"
        ),
        verified_binaries=verified_binaries,
        expected_outcome="SAT",
        precheck=True,
    )
    if solver["proof_status"] != row["status"] or vacuity_solver["outcome"] != "SAT":
        raise ValidationError(f"{route_id} solver/vacuity proof status drift")

    block_path, block_artifact = read_bound_interaction_json(
        root,
        row["block_results_path"],
        row["block_results_digest"],
        f"{route_id}.blocks",
    )
    del block_path
    require_exact_keys(
        block_artifact,
        {"schema_version", "kind", "route_id", "blocks"},
        f"{route_id}.blocks",
    )
    block_rows = block_artifact["blocks"]
    if (
        block_artifact["schema_version"] != SCHEMA_VERSION
        or block_artifact["kind"] != "bounded-interaction-block-results"
        or block_artifact["route_id"] != route_id
        or not isinstance(block_rows, list)
        or [item.get("block_id") for item in block_rows] != list(INTERACTION_BLOCK_IDS)
    ):
        raise ValidationError(f"{route_id} block result closure drift")
    for index, block in enumerate(block_rows):
        block = require_exact_keys(
            block, INTERACTION_BLOCK_RESULT_KEYS, f"{route_id}.blocks[{index}]"
        )
        block_id = block["block_id"]
        symbol = next(
            symbol
            for symbol, external_id in INTERACTION_BLOCK_SYMBOLS.items()
            if external_id == block_id
        )
        block_behavior_digest = digest_json(
            [
                {
                    "scenario_id": observation["scenarioId"],
                    "observation": observation["blocks"][block_id],
                }
                for observation in observation_rows[0]
            ]
        )
        block_chunk_digest = digest_json(
            [chunk for chunk in chunk_rows if chunk["block_id"] == block_id]
        )
        if (
            block["obligation_symbol"] != f"diff_{symbol}"
            or block["influence_classes"]
            != {
                "model": influence_classes["model"][block_id],
                "runtime": influence_classes["runtime"][block_id],
            }
            or block["canonical_block_digest"] != expected_block_map[block_id]
            or block["source_block_digest"] != source.relift_block_digests[block_id]
            or block["target_block_digest"] != target.relift_block_digests[block_id]
            or block["behavior_block_digest"] != block_behavior_digest
            or block["chunk_block_digest"] != block_chunk_digest
            or block["formal_input_digest"] != row["formal_input_digest"]
            or block["solver_input_digest"] != row["solver_input_digest"]
            or block["solver_result_digest"] != row["solver_result_digest"]
            or block["vacuity_input_digest"] != row["vacuity_input_digest"]
            or block["vacuity_solver_result_digest"]
            != row["vacuity_solver_result_digest"]
            or block["mutation_campaign_digest"] != mutation_digest
            or block["semantic_status"] != "PASSED"
            or block["chunk_status"] != "PASSED"
            or block["model_behavior_status"] != "PASSED"
            or block["raw_solver_status"] != row["status"]
            or block["formal_status"] != row["status"]
            or block["assumption_precheck"] != "SAT_NON_VACUOUS_DOMAIN"
            or block["semantic_mutant_detected"] is not True
            or block["behavior_mutant_detected"] is not True
            or block["declaration_echo_excluded_from_behavior_denominator"] is not True
            or block["runtime_evidence_eligibility"] != "INELIGIBLE_SAME_PRODUCER"
            or block["runtime_status"] != "NOT_RUN"
            or block["oracle_provenance"] != "NOT_INDEPENDENT_SINGLE_ENGINE"
            or block["status"] != row["status"]
        ):
            raise ValidationError(f"{route_id}.{block_id} proof linkage drift")

    composition_path, composition = read_bound_interaction_json(
        root,
        row["composition_path"],
        row["composition_digest"],
        f"{route_id}.composition",
    )
    del composition_path
    require_exact_keys(
        composition,
        {
            "schema_version",
            "kind",
            "route_id",
            "source_lifting",
            "target_lowering_relift",
            "canonical_model_digest",
            "semantic_equal",
            "chunk_equal",
            "model_behavior_equal",
            "solver_outcome",
            "vacuity_outcome",
            "cross_channel_equivalence",
            "oracle_provenance",
            "status",
        },
        f"{route_id}.composition",
    )
    required_channels = {
        *required_runtime_channels(source.profile_id),
        *required_runtime_channels(target.profile_id),
    }
    if (
        composition["schema_version"] != SCHEMA_VERSION
        or composition["kind"] != "bounded-interaction-route-composition"
        or composition["route_id"] != route_id
        or composition["source_lifting"]
        != {
            "profile_id": source.profile_id,
            "project_digest": source.project_digest,
            "model_digest": source.relift_model_digest,
        }
        or composition["target_lowering_relift"]
        != {
            "profile_id": target.profile_id,
            "project_digest": target.project_digest,
            "model_digest": target.relift_model_digest,
        }
        or composition["canonical_model_digest"] != canonical_digest
        or composition["semantic_equal"] is not True
        or composition["chunk_equal"] is not True
        or composition["model_behavior_equal"] is not True
        or composition["solver_outcome"] != "UNSAT"
        or composition["vacuity_outcome"] != "SAT"
        or not isinstance(composition["cross_channel_equivalence"], dict)
        or set(composition["cross_channel_equivalence"]) != required_channels
        or any(
            value != "NOT_RUN"
            for value in composition["cross_channel_equivalence"].values()
        )
        or composition["oracle_provenance"] != "NOT_INDEPENDENT_SINGLE_ENGINE"
        or composition["status"] != row["status"]
    ):
        raise ValidationError(f"{route_id} route composition drift")
    expected_layers = {
        "emitted_source_relift": "PASSED",
        "emitted_target_relift": "PASSED",
        "semantic": "PASSED",
        "chunk": "PASSED",
        "model_behavior": "PASSED",
        "assumption_vacuity_precheck": "SAT",
        "smt_solver": "UNSAT",
        "framework_native_build": "NOT_RUN",
        "framework_browser_or_device_runtime": "NOT_RUN",
        "independent_external_verification": "NOT_RUN",
    }
    if (
        layered["layers"] != expected_layers
        or formal_path
        != resolve_regular_file(
            root, links["formal_input_path"], f"{route_id}.formal-link"
        )
        or layered_path
        != resolve_regular_file(
            root, links["layered_result_path"], f"{route_id}.layered-link"
        )
    ):
        raise ValidationError(f"{route_id} layered proof stages drift")
    return {
        "artifact_closure": "PASSED",
        "formal_solver": {
            "result_digest": row["solver_result_digest"],
            "outcome": solver["outcome"],
            "proof_status": solver["proof_status"],
            "runner_replay": solver["runner_replay"],
        },
        "vacuity_solver": {
            "result_digest": row["vacuity_solver_result_digest"],
            "outcome": vacuity_solver["outcome"],
            "proof_status": vacuity_solver["proof_status"],
            "precheck_status": vacuity_solver["precheck_status"],
            "runner_replay": vacuity_solver["runner_replay"],
        },
        "replay_digest": digest_json(
            {
                "formal": solver["runner_replay"],
                "vacuity": vacuity_solver["runner_replay"],
            }
        ),
    }


def load_interaction_campaign(path: Path) -> LoadedCampaign:
    path = path.resolve()
    root = path.parent.resolve()
    engine_verifier_evidence = run_locked_interaction_engine_verifier(root)
    campaign = require_exact_keys(
        read_json(path, "frontend interaction formal campaign"),
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
        },
        "frontend interaction formal campaign",
    )
    if (
        campaign["schema_version"] != SCHEMA_VERSION
        or campaign["kind"] != INTERACTION_CAMPAIGN_KIND
        or campaign["proof_profile"] != INTERACTION_PROOF_PROFILE
        or campaign["corpus_id"] != "frontend-bounded-interaction-corpus-v1"
        or campaign["semantic_block_ids"] != list(INTERACTION_BLOCK_IDS)
        or campaign["block_symbol_map"]
        != {block_id: symbol for symbol, block_id in INTERACTION_BLOCK_SYMBOLS.items()}
        or campaign["profile_count"] != len(EXPECTED_PROFILES)
        or campaign["route_count"] != 72
        or campaign["block_count"] != len(INTERACTION_BLOCK_IDS)
        or not isinstance(campaign["assumptions"], list)
        or not campaign["assumptions"]
        or campaign["oracle_provenance"]
        != {
            "independence": "NOT_INDEPENDENT_SINGLE_ENGINE",
            "authoritative_spec": "SAME_ENGINE",
            "reference_reducer": "SAME_ENGINE_SEPARATE_IMPLEMENTATION",
            "solver_result_used_as_input_or_oracle": False,
        }
        or campaign["arbitrary_customer_source"] != "NOT_PROVED"
        or campaign["unconditional_proof"] is not False
        or campaign["native_build_and_runtime"] != "NOT_RUN"
        or campaign["independent_external_verification"] != "NOT_RUN"
        or campaign["certification"] != "NOT_CERTIFIED"
    ):
        raise ValidationError("interaction campaign identity/proof boundary drift")
    scenarios, scenario_source_digest = load_scenario_corpus(
        root, campaign["scenario_manifest"]
    )
    verified_binaries: dict[str, tuple[str, str]] = {}
    mutation_replays: list[dict[str, Any]] = []
    mutation_link = require_exact_keys(
        campaign["mutation_campaign"],
        {"path", "digest", "status"},
        "mutation_campaign",
    )
    if (
        mutation_link["path"] != "mutation-campaign.json"
        or mutation_link["status"] != "PASSED"
    ):
        raise ValidationError("mutation campaign link drift")
    mutation_path, mutation = read_bound_interaction_json(
        root,
        mutation_link["path"],
        mutation_link["digest"],
        "mutation campaign",
    )
    del mutation_path
    require_exact_keys(
        mutation,
        {"schema_version", "kind", "proof_profile", "mutations", "status"},
        "mutation campaign",
    )
    mutations = mutation["mutations"]
    if (
        mutation["schema_version"] != SCHEMA_VERSION
        or mutation["kind"] != "bounded-interaction-seeded-mutation-campaign"
        or mutation["proof_profile"] != INTERACTION_PROOF_PROFILE
        or mutation["status"] != "PASSED"
        or not isinstance(mutations, list)
        or [item.get("block_id") for item in mutations] != list(INTERACTION_BLOCK_IDS)
    ):
        raise ValidationError("mutation campaign closure drift")
    for mutation_index, mutation_row in enumerate(mutations):
        mutation_row = require_exact_keys(
            mutation_row,
            {
                "block_id",
                "obligation_symbol",
                "pointer",
                "scenario_id",
                "counterexample_replay",
                "variants",
                "status",
            },
            f"mutation[{mutation_index}]",
        )
        block_id = mutation_row.get("block_id")
        symbol = next(
            symbol
            for symbol, external_id in INTERACTION_BLOCK_SYMBOLS.items()
            if external_id == block_id
        )
        variants = mutation_row.get("variants")
        witness = mutation_row.get("counterexample_replay")
        if (
            mutation_row.get("obligation_symbol") != f"diff_{symbol}"
            or mutation_row.get("status") != "REFUTED_AS_EXPECTED"
            or not isinstance(variants, list)
            or [variant.get("variant") for variant in variants]
            != ["SOURCE_ONLY", "TARGET_ONLY", "REFERENCE_ONLY"]
            or not isinstance(mutation_row.get("pointer"), str)
            or not str(mutation_row["pointer"]).startswith("/")
            or mutation_row.get("scenario_id") not in LOCKED_INTERACTION_SCENARIO_IDS
            or not isinstance(witness, dict)
            or witness.get("block_id") != block_id
            or witness.get("pointer") != mutation_row.get("pointer")
            or witness.get("scenario_id") != mutation_row.get("scenario_id")
            or witness.get("semantic_mutant_detected") is not True
            or witness.get("behavior_mutant_detected") is not True
        ):
            raise ValidationError(f"mutation[{mutation_index}] proof row drift")
        for variant_index, variant in enumerate(variants):
            variant = require_exact_keys(
                variant,
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
                f"mutation[{mutation_index}].variants[{variant_index}]",
            )
            variant_name = str(variant["variant"])
            expected_prefix = (
                f"mutations/{block_id}/{variant_name.lower().replace('_', '-')}/"
            )
            if (
                variant.get("formal_input_path")
                != expected_prefix + "formal-input.json"
                or variant.get("smt2_path") != expected_prefix + "proof.smt2"
                or variant.get("solver_result_path")
                != expected_prefix + "solver-result.json"
                or variant.get("solver_outcome") != "SAT"
                or variant.get("replay_status") != "PASSED"
            ):
                raise ValidationError(
                    f"mutation[{mutation_index}].variants[{variant_index}] drift"
                )
            for path_key, digest_key in (
                ("formal_input_path", "formal_input_digest"),
                ("smt2_path", "smt2_digest"),
                ("solver_result_path", "solver_result_digest"),
            ):
                variant_path = resolve_regular_file(
                    root,
                    variant[path_key],
                    f"mutation[{mutation_index}].variants[{variant_index}].{path_key}",
                )
                if sha256_bytes(variant_path.read_bytes()) != require_sha256(
                    variant[digest_key],
                    f"mutation[{mutation_index}].variants[{variant_index}].{digest_key}",
                ):
                    raise ValidationError(
                        f"mutation[{mutation_index}].variants[{variant_index}] bytes drift"
                    )
            formal_path = resolve_regular_file(
                root,
                variant["formal_input_path"],
                f"mutation[{mutation_index}].variants[{variant_index}].formal",
            )
            formal = require_exact_keys(
                read_json(formal_path, "mutation formal input"),
                {
                    "schema_version",
                    "kind",
                    "proof_profile",
                    "block_id",
                    "obligation_symbol",
                    "variant",
                    "pointer",
                    "canonical_model_digest",
                    "canonical_block_digest",
                    "mutant_model_digest",
                    "mutant_block_digest",
                    "counterexample_replay",
                    "expected_solver_outcome",
                    "oracle_provenance",
                },
                f"mutation[{mutation_index}].variants[{variant_index}].formal",
            )
            if (
                formal["schema_version"] != SCHEMA_VERSION
                or formal["kind"] != "bounded-interaction-seeded-mutation-formal-input"
                or formal["proof_profile"] != INTERACTION_PROOF_PROFILE
                or formal["block_id"] != block_id
                or formal["obligation_symbol"] != f"diff_{symbol}"
                or formal["variant"] != variant_name
                or formal["pointer"] != mutation_row.get("pointer")
                or formal["counterexample_replay"]
                != mutation_row.get("counterexample_replay")
                or formal["expected_solver_outcome"] != "SAT"
                or formal["oracle_provenance"] != "NOT_INDEPENDENT_SINGLE_ENGINE"
            ):
                raise ValidationError(
                    f"mutation[{mutation_index}].variants[{variant_index}] formal drift"
                )
            require_sha256(
                formal["canonical_model_digest"],
                f"mutation[{mutation_index}].canonical_model_digest",
            )
            require_sha256(
                formal["canonical_block_digest"],
                f"mutation[{mutation_index}].canonical_block_digest",
            )
            require_sha256(
                formal["mutant_model_digest"],
                f"mutation[{mutation_index}].mutant_model_digest",
            )
            require_sha256(
                formal["mutant_block_digest"],
                f"mutation[{mutation_index}].mutant_block_digest",
            )
            if formal["canonical_block_digest"] == formal["mutant_block_digest"]:
                raise ValidationError(
                    f"mutation[{mutation_index}].variants[{variant_index}] block mutant is vacuous"
                )
            mutation_route_id = f"mutation:{block_id}:{variant_name}"
            mutation_solver = validate_solver_result(
                route_id=mutation_route_id,
                route_status="REFUTED",
                formal_input_digest=str(variant["formal_input_digest"]),
                smt_path=resolve_regular_file(
                    root,
                    variant["smt2_path"],
                    f"mutation[{mutation_index}].variants[{variant_index}].smt",
                ),
                smt_digest=str(variant["smt2_digest"]),
                solver_path=resolve_regular_file(
                    root,
                    variant["solver_result_path"],
                    f"mutation[{mutation_index}].variants[{variant_index}].solver",
                ),
                verified_binaries=verified_binaries,
                expected_outcome="SAT",
                extra_fields={
                    "mutation_formal_input_path": variant["formal_input_path"],
                    "mutation_solver_input_path": variant["smt2_path"],
                    "expected_outcome": "SAT",
                    "replay_status": "PASSED",
                },
            )
            mutation_replays.append(
                {
                    "block_id": block_id,
                    "variant": variant_name,
                    "formal_input_digest": variant["formal_input_digest"],
                    "canonical_model_digest": formal["canonical_model_digest"],
                    "canonical_block_digest": formal["canonical_block_digest"],
                    "mutant_model_digest": formal["mutant_model_digest"],
                    "mutant_block_digest": formal["mutant_block_digest"],
                    "solver_result_digest": variant["solver_result_digest"],
                    "outcome": mutation_solver["outcome"],
                    "proof_status": mutation_solver["proof_status"],
                    "runner_replay": mutation_solver["runner_replay"],
                }
            )
    profiles_value = campaign["profiles"]
    if not isinstance(profiles_value, list) or len(profiles_value) != len(
        EXPECTED_PROFILES
    ):
        raise ValidationError("interaction campaign profile matrix is incomplete")
    profile_keys = {
        "profile_id",
        "framework_version",
        "platforms",
        "required_runtime_channels",
        "project_path",
        "project_digest",
        "manifest_path",
        "manifest_digest",
        "source_kind",
        "source_fixture_path",
        "source_fixture_digest",
        "source_fixture_byte_count",
        "interaction_source_path",
        "navigation_compatibility_path",
        "relift_model_digest",
        "relift_block_digests",
        "runtime_driver_contract",
        "target_build",
        "target_runtime",
    }
    profiles: dict[str, ProfileArtifact] = {}
    for index, raw in enumerate(profiles_value):
        row = require_exact_keys(raw, profile_keys, f"profiles[{index}]")
        profile_id = row.get("profile_id")
        if profile_id not in EXPECTED_PROFILES or profile_id in profiles:
            raise ValidationError(
                f"profiles[{index}] has an unknown or duplicate profile_id"
            )
        profiles[profile_id] = validate_interaction_project_manifest(
            root, row, EXPECTED_PROFILES[profile_id], scenarios
        )
    if set(profiles) != set(EXPECTED_PROFILES):
        raise ValidationError("interaction campaign profile matrix is incomplete")
    model_digests = {profile.relift_model_digest for profile in profiles.values()}
    block_digest_rows = {
        canonical_json(profile.relift_block_digests) for profile in profiles.values()
    }
    if len(model_digests) != 1 or len(block_digest_rows) != 1:
        raise ValidationError("interaction profile relift equivalence drift")
    canonical_profile = profiles[sorted(profiles)[0]]
    for replay in mutation_replays:
        block_id = replay["block_id"]
        if (
            replay["canonical_model_digest"] != canonical_profile.relift_model_digest
            or replay["canonical_block_digest"]
            != canonical_profile.relift_block_digests[block_id]
        ):
            raise ValidationError(f"{block_id} mutation canonical binding drift")
    expected_source_liftings = [
        {
            "profile_id": profile.profile_id,
            "project_digest": profile.project_digest,
            "relift_model_digest": profile.relift_model_digest,
            "source_kind": "GENERATED_FIXTURE",
            "arbitrary_customer_source": "NOT_PROVED",
            "status": "PASSED",
        }
        for profile in sorted(profiles.values(), key=lambda item: item.profile_id)
    ]
    expected_target_lowerings = [
        {
            "profile_id": profile.profile_id,
            "project_digest": profile.project_digest,
            "emitted_project": "PASSED",
            "relift": "PASSED",
        }
        for profile in sorted(profiles.values(), key=lambda item: item.profile_id)
    ]
    if campaign["source_liftings"] != expected_source_liftings:
        raise ValidationError("interaction source lifting bindings drift")
    if campaign["target_lowerings"] != expected_target_lowerings:
        raise ValidationError("interaction target lowering bindings drift")

    route_keys = {
        "route_id",
        "source_profile",
        "target_profile",
        "source_project_digest",
        "target_project_digest",
        "evidence_path",
        "evidence_digest",
        "formal_input_path",
        "formal_input_digest",
        "behavior_path",
        "behavior_digest",
        "chunks_path",
        "chunks_digest",
        "solver_input_path",
        "solver_input_digest",
        "solver_result_path",
        "solver_result_digest",
        "vacuity_input_path",
        "vacuity_input_digest",
        "vacuity_solver_result_path",
        "vacuity_solver_result_digest",
        "block_results_path",
        "block_results_digest",
        "composition_path",
        "composition_digest",
        "layered_result",
        "status",
    }
    artifact_pairs = (
        ("evidence_path", "evidence_digest"),
        ("formal_input_path", "formal_input_digest"),
        ("behavior_path", "behavior_digest"),
        ("chunks_path", "chunks_digest"),
        ("solver_input_path", "solver_input_digest"),
        ("solver_result_path", "solver_result_digest"),
        ("vacuity_input_path", "vacuity_input_digest"),
        ("vacuity_solver_result_path", "vacuity_solver_result_digest"),
        ("block_results_path", "block_results_digest"),
        ("composition_path", "composition_digest"),
    )
    allowed_statuses = {"PROVED_UNDER_ASSUMPTIONS", "REFUTED", "NOT_PROVED"}
    expected_pairs = {
        (source, target)
        for source in EXPECTED_PROFILES
        for target in EXPECTED_PROFILES
        if source != target
    }
    seen_pairs: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()
    routes: list[dict[str, Any]] = []
    routes_value = campaign["routes"]
    if not isinstance(routes_value, list):
        raise ValidationError("interaction campaign routes must be an array")
    for index, raw in enumerate(routes_value):
        row = require_exact_keys(raw, route_keys, f"routes[{index}]")
        route_id = row.get("route_id")
        source = row.get("source_profile")
        target = row.get("target_profile")
        pair = (source, target)
        if (
            not isinstance(route_id, str)
            or route_id in seen_ids
            or route_id != f"{source}--to--{target}"
            or pair not in expected_pairs
            or pair in seen_pairs
        ):
            raise ValidationError(f"routes[{index}] identity/pair drift")
        if (
            row["source_project_digest"] != profiles[source].project_digest
            or row["target_project_digest"] != profiles[target].project_digest
            or row["status"] not in allowed_statuses
            or row["layered_result"] != row["status"]
        ):
            raise ValidationError(f"{route_id} route proof binding drift")
        prefix = f"routes/{route_id}/"
        expected_route_paths = {
            "evidence_path": "layered-result.json",
            "formal_input_path": "formal-input.json",
            "behavior_path": "behavior.json",
            "chunks_path": "chunks.json",
            "solver_input_path": "proof.smt2",
            "solver_result_path": "solver-result.json",
            "vacuity_input_path": "vacuity-precheck.smt2",
            "vacuity_solver_result_path": "vacuity-solver-result.json",
            "block_results_path": "block-results.json",
            "composition_path": "composition.json",
        }
        if any(
            row[path_key] != prefix + filename
            for path_key, filename in expected_route_paths.items()
        ):
            raise ValidationError(f"{route_id} canonical artifact path drift")
        for path_key, digest_key in artifact_pairs:
            if not str(row[path_key]).startswith(prefix):
                raise ValidationError(f"{route_id}.{path_key} escapes route directory")
            artifact = resolve_regular_file(
                root, row[path_key], f"{route_id}.{path_key}"
            )
            digest = require_sha256(row[digest_key], f"{route_id}.{digest_key}")
            if sha256_bytes(artifact.read_bytes()) != digest:
                raise ValidationError(f"{route_id}.{digest_key} byte mismatch")
        formal_input = read_json(
            resolve_regular_file(
                root, row["formal_input_path"], f"{route_id}.formal_input_path"
            ),
            f"{route_id} formal input",
        )
        if formal_input.get("assumptions") != campaign["assumptions"]:
            raise ValidationError(f"{route_id} formal assumptions drift")
        proof_replay = validate_interaction_route_evidence(
            root=root,
            row=row,
            profiles=profiles,
            assumptions=campaign["assumptions"],
            scenario_digest=scenario_source_digest,
            mutation_digest=str(mutation_link["digest"]),
            verified_binaries=verified_binaries,
        )
        seen_ids.add(route_id)
        seen_pairs.add(pair)
        routes.append({**row, "runner_proof_replay": proof_replay})
    if seen_pairs != expected_pairs or len(routes) != 72:
        raise ValidationError("interaction campaign route matrix is incomplete")
    counts = {
        status: sum(route["status"] == status for route in routes)
        for status in allowed_statuses
    }
    if campaign["counts"] != counts:
        raise ValidationError("interaction campaign status counts drift")
    expected_block_counts = {
        block_id: dict(counts) for block_id in INTERACTION_BLOCK_IDS
    }
    if campaign["block_counts"] != expected_block_counts:
        raise ValidationError("interaction campaign block counts are incomplete")
    return LoadedCampaign(
        path=path,
        root=root,
        digest=sha256_bytes(path.read_bytes()),
        byte_count=path.stat().st_size,
        profiles=profiles,
        routes=tuple(routes),
        proof_profile=INTERACTION_PROOF_PROFILE,
        semantic_block_ids=INTERACTION_BLOCK_IDS,
        scenario_manifest=scenarios,
        scenario_manifest_digest=scenario_source_digest,
        block_symbol_map=dict(campaign["block_symbol_map"]),
        mutation_replay=tuple(mutation_replays),
        engine_verifier_evidence=engine_verifier_evidence,
    )


def load_campaign(path: Path) -> LoadedCampaign:
    identity = read_json(path.resolve(), "frontend formal campaign identity")
    proof_profile = identity.get("proof_profile")
    if proof_profile == PROOF_PROFILE:
        return load_navigation_campaign(path)
    if proof_profile == INTERACTION_PROOF_PROFILE:
        return load_interaction_campaign(path)
    raise ValidationError("campaign proof_profile is unsupported")


def bounded_stream(value: bytes | None) -> dict[str, Any]:
    raw = value or b""
    return {
        "text": raw[:MAX_LOG_BYTES].decode("utf-8", errors="replace"),
        "byte_count": len(raw),
        "sha256": sha256_bytes(raw),
        "truncated": len(raw) > MAX_LOG_BYTES,
    }


def process_environment(
    no_network: bool, explicit: Mapping[str, str]
) -> tuple[dict[str, str], dict[str, Any]]:
    inherited_keys = list(SAFE_INHERITED_ENV_KEYS)
    if not no_network:
        inherited_keys.extend(NETWORK_ENV_KEYS)
    environment = {key: os.environ[key] for key in inherited_keys if key in os.environ}
    environment.update(explicit)
    evidence = {
        "allowlisted_inherited_keys": sorted(
            key for key in inherited_keys if key in os.environ
        ),
        "explicit": dict(sorted(explicit.items())),
        "network_allowed": not no_network,
        "unlisted_environment_inherited": False,
    }
    return environment, evidence


def run_command(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    no_network: bool,
    explicit_env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not argv:
        raise ValueError("argv must not be empty")
    command = argv[0]
    resolved = Path(command) if Path(command).is_absolute() else None
    if resolved is None:
        found = shutil.which(command)
        resolved = Path(found) if found else None
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    base = {
        "argv": [str(resolved) if resolved else command, *argv[1:]],
        "cwd": str(cwd.resolve()),
        "started_at": started_at,
        "timeout_seconds": timeout_seconds,
    }
    if resolved is None or not resolved.is_file() or not os.access(resolved, os.X_OK):
        return {
            **base,
            "duration_ms": 0,
            "exit_code": None,
            "signal": None,
            "status": "TOOL_UNAVAILABLE",
            "reason": "EXECUTABLE_NOT_FOUND",
            "environment": {
                "allowlisted_inherited_keys": [],
                "explicit": dict(explicit_env or {}),
                "network_allowed": not no_network,
                "unlisted_environment_inherited": False,
            },
            "stdout": bounded_stream(b""),
            "stderr": bounded_stream(b""),
        }
    environment, env_evidence = process_environment(no_network, explicit_env or {})
    started = time.monotonic()
    process = subprocess.Popen(
        [str(resolved), *argv[1:]],
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except KeyboardInterrupt:
        terminate_process_group(process)
        raise
    except subprocess.TimeoutExpired as error:
        timed_out = True
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
        stdout = (error.stdout or b"") + (stdout or b"")
        stderr = (error.stderr or b"") + (stderr or b"")
    duration_ms = round((time.monotonic() - started) * 1000)
    if timed_out:
        status = "TIMEOUT"
        reason = "COMMAND_TIMEOUT"
    else:
        status = "PASSED" if process.returncode == 0 else "FAILED"
        reason = None if status == "PASSED" else "NONZERO_EXIT"
    return {
        **base,
        "duration_ms": duration_ms,
        "exit_code": process.returncode,
        "signal": -process.returncode
        if process.returncode is not None and process.returncode < 0
        else None,
        "status": status,
        "reason": reason,
        "environment": env_evidence,
        "stdout": bounded_stream(stdout),
        "stderr": bounded_stream(stderr),
    }


def locked_interaction_engine_implementation_identity() -> dict[str, Any]:
    """Bind the exact frozen verifier source, build, dependency, and Node bytes."""

    source_tree = tree_digest(INTERACTION_ENGINE_SOURCE_ROOT)
    dist_tree = tree_digest(INTERACTION_ENGINE_DIST_ROOT)
    if source_tree is None or dist_tree is None:
        raise ValidationError(
            "frozen frontend interaction engine trees are unavailable"
        )
    if (
        source_tree["file_count"] != LOCKED_INTERACTION_ENGINE_SOURCE_TREE_FILE_COUNT
        or source_tree["digest"] != LOCKED_INTERACTION_ENGINE_SOURCE_TREE_SHA256
        or dist_tree["file_count"] != LOCKED_INTERACTION_ENGINE_DIST_TREE_FILE_COUNT
        or dist_tree["digest"] != LOCKED_INTERACTION_ENGINE_DIST_TREE_SHA256
    ):
        raise ValidationError("frozen frontend interaction engine tree identity drift")

    file_paths = {
        "cli_source": INTERACTION_ENGINE_CLI_SOURCE_PATH,
        "equivalence_source": INTERACTION_ENGINE_EQUIVALENCE_SOURCE_PATH,
        "cli_dist": INTERACTION_ENGINE_CLI_DIST_PATH,
        "equivalence_dist": INTERACTION_ENGINE_EQUIVALENCE_DIST_PATH,
        "package": INTERACTION_ENGINE_PACKAGE_PATH,
        "tsconfig": INTERACTION_ENGINE_TSCONFIG_PATH,
        "lock": INTERACTION_ENGINE_LOCK_PATH,
        "typescript_package": INTERACTION_ENGINE_TYPESCRIPT_PACKAGE_PATH,
    }
    files = {
        key: file_identity(path, f"frontend interaction engine {key}")
        for key, path in file_paths.items()
    }
    for key, expected_digest in LOCKED_INTERACTION_ENGINE_FILE_SHA256.items():
        if files[key]["sha256"] != expected_digest:
            raise ValidationError(f"frozen frontend interaction engine {key} drift")
    typescript_package = read_json(
        INTERACTION_ENGINE_TYPESCRIPT_PACKAGE_PATH,
        "frontend interaction engine TypeScript package",
    )
    if (
        typescript_package.get("name") != "typescript"
        or typescript_package.get("version")
        != LOCKED_INTERACTION_ENGINE_TYPESCRIPT_VERSION
    ):
        raise ValidationError("frozen frontend interaction engine TypeScript drift")

    node_path_value = shutil.which("node")
    if node_path_value is None:
        raise ValidationError("frozen frontend interaction engine Node is unavailable")
    node = file_identity(Path(node_path_value), "frontend interaction verifier Node")
    node["version"] = LOCKED_INTERACTION_ENGINE_NODE_VERSION
    if node["sha256"] != LOCKED_INTERACTION_ENGINE_NODE_SHA256:
        raise ValidationError("frozen frontend interaction verifier Node digest drift")

    identity = {
        "schema_version": SCHEMA_VERSION,
        "kind": "frontend-interaction-engine-implementation-identity",
        "node": node,
        "source_tree": {
            "root": str(INTERACTION_ENGINE_SOURCE_ROOT.resolve()),
            **source_tree,
        },
        "dist_tree": {
            "root": str(INTERACTION_ENGINE_DIST_ROOT.resolve()),
            **dist_tree,
        },
        "files": files,
        "typescript_version": LOCKED_INTERACTION_ENGINE_TYPESCRIPT_VERSION,
    }
    identity["closure_digest"] = digest_json(identity)
    return identity


def validate_interaction_engine_verifier_executions(
    *,
    version_execution: Mapping[str, Any],
    verification_execution: Mapping[str, Any],
    node_realpath: str,
    campaign_root: Path,
) -> dict[str, Any]:
    """Reject nonzero, contaminated, truncated, or fabricated verifier output."""

    command_keys = {
        "argv",
        "cwd",
        "started_at",
        "timeout_seconds",
        "duration_ms",
        "exit_code",
        "signal",
        "status",
        "reason",
        "environment",
        "stdout",
        "stderr",
    }
    version = require_exact_keys(
        dict(version_execution),
        command_keys,
        "interaction engine Node version execution",
    )
    verification = require_exact_keys(
        dict(verification_execution),
        command_keys,
        "interaction engine campaign verification execution",
    )
    explicit_environment = {"LANG": "C", "LC_ALL": "C", "NO_COLOR": "1"}
    expected_environment = process_environment(True, explicit_environment)[1]
    expected_version_argv = [node_realpath, "--version"]
    expected_verify_argv = [
        node_realpath,
        str(INTERACTION_ENGINE_CLI_DIST_PATH.resolve()),
        "--proof-profile",
        INTERACTION_PROOF_PROFILE,
        "--verify",
        str(campaign_root.resolve()),
        "--json",
    ]
    expected_cwd = str(INTERACTION_ENGINE_ROOT.resolve())
    for name, execution, argv, timeout_seconds in (
        ("Node version", version, expected_version_argv, 30),
        (
            "campaign verification",
            verification,
            expected_verify_argv,
            INTERACTION_ENGINE_VERIFY_TIMEOUT_SECONDS,
        ),
    ):
        if (
            execution["argv"] != argv
            or execution["cwd"] != expected_cwd
            or execution["timeout_seconds"] != timeout_seconds
            or execution["status"] != "PASSED"
            or execution["reason"] is not None
            or execution["exit_code"] != 0
            or execution["signal"] is not None
            or execution["environment"] != expected_environment
            or not isinstance(execution["started_at"], str)
            or type(execution["duration_ms"]) is not int
            or execution["duration_ms"] < 0
        ):
            raise ValidationError(f"frozen interaction engine {name} execution drift")
        validate_runtime_stream(
            execution["stdout"], f"interaction engine {name}.stdout"
        )
        validate_runtime_stream(
            execution["stderr"], f"interaction engine {name}.stderr"
        )
        if execution["stderr"]["text"] != "":
            raise ValidationError(
                f"frozen interaction engine {name} emitted unexpected stderr"
            )
    if version["stdout"]["text"] != LOCKED_INTERACTION_ENGINE_NODE_VERSION + "\n":
        raise ValidationError("frozen interaction engine Node version drift")

    try:
        result = json.loads(verification["stdout"]["text"])
    except json.JSONDecodeError as error:
        raise ValidationError(
            "frozen interaction engine verifier stdout is not strict JSON"
        ) from error
    result = require_exact_keys(
        result,
        {"schema_version", "kind", "proof_profile", "valid", "errors"},
        "frozen interaction engine verifier result",
    )
    expected_result = {
        "schema_version": SCHEMA_VERSION,
        "kind": "frontend-interaction-formal-campaign-verification",
        "proof_profile": INTERACTION_PROOF_PROFILE,
        "valid": True,
        "errors": [],
    }
    expected_stdout = (
        json.dumps(expected_result, ensure_ascii=False, separators=(",", ":")) + "\n"
    )
    if result != expected_result or verification["stdout"]["text"] != expected_stdout:
        raise ValidationError(
            "frozen interaction engine verifier rejected the campaign"
        )
    return result


def run_locked_interaction_engine_verifier(campaign_root: Path) -> dict[str, Any]:
    """Execute the frozen producer verifier before trusting any v2 campaign."""

    implementation = locked_interaction_engine_implementation_identity()
    node_realpath = implementation["node"]["realpath"]
    explicit_environment = {"LANG": "C", "LC_ALL": "C", "NO_COLOR": "1"}
    version_execution = run_command(
        [node_realpath, "--version"],
        cwd=INTERACTION_ENGINE_ROOT,
        timeout_seconds=30,
        no_network=True,
        explicit_env=explicit_environment,
    )
    verification_execution = run_command(
        [
            node_realpath,
            str(INTERACTION_ENGINE_CLI_DIST_PATH.resolve()),
            "--proof-profile",
            INTERACTION_PROOF_PROFILE,
            "--verify",
            str(campaign_root.resolve()),
            "--json",
        ],
        cwd=INTERACTION_ENGINE_ROOT,
        timeout_seconds=INTERACTION_ENGINE_VERIFY_TIMEOUT_SECONDS,
        no_network=True,
        explicit_env=explicit_environment,
    )
    result = validate_interaction_engine_verifier_executions(
        version_execution=version_execution,
        verification_execution=verification_execution,
        node_realpath=node_realpath,
        campaign_root=campaign_root,
    )
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "kind": "frontend-interaction-engine-campaign-preverification",
        "status": "PASSED",
        "implementation_identity": implementation,
        "version_execution": version_execution,
        "verification_execution": verification_execution,
        "result": result,
    }
    evidence["evidence_digest"] = digest_json(evidence)
    return evidence


def command_output(record: Mapping[str, Any]) -> str:
    return str(record["stdout"]["text"]).strip()


def skipped_command(argv: Sequence[str], cwd: Path, reason: str) -> dict[str, Any]:
    return {
        "argv": list(argv),
        "cwd": str(cwd.resolve()),
        "started_at": None,
        "duration_ms": 0,
        "timeout_seconds": None,
        "exit_code": None,
        "signal": None,
        "status": "NOT_RUN",
        "reason": reason,
        "environment": {
            "allowlisted_inherited_keys": [],
            "explicit": {},
            "network_allowed": False,
            "unlisted_environment_inherited": False,
        },
        "stdout": bounded_stream(b""),
        "stderr": bounded_stream(b""),
    }


@dataclass
class DomNode:
    tag: str
    attributes: dict[str, str]
    children: list[DomNode | str]


class DomTreeParser(HTMLParser):
    VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.roots: list[DomNode] = []
        self.stack: list[DomNode] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = DomNode(
            tag.lower(),
            {name.lower(): value or "" for name, value in attrs},
            [],
        )
        if self.stack:
            self.stack[-1].children.append(node)
        else:
            self.roots.append(node)
        if node.tag not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1].tag == tag.lower():
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        wanted = tag.lower()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == wanted:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if self.stack:
            self.stack[-1].children.append(data)


def walk_dom(nodes: Sequence[DomNode]) -> list[DomNode]:
    result: list[DomNode] = []
    pending = list(reversed(nodes))
    while pending:
        node = pending.pop()
        result.append(node)
        pending.extend(
            reversed([child for child in node.children if isinstance(child, DomNode)])
        )
    return result


def dom_text(node: DomNode) -> str:
    values: list[str] = []
    pending: list[DomNode | str] = list(reversed(node.children))
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            values.append(value)
        else:
            pending.extend(reversed(value.children))
    return " ".join("".join(values).split())


def dom_boolean(value: str | None) -> bool | None:
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def observe_dom(
    dom: str, model: Mapping[str, Any], expected: Mapping[str, Any]
) -> dict[str, Any]:
    parser = DomTreeParser()
    try:
        parser.feed(dom)
        parser.close()
    except Exception as error:  # HTMLParser can surface malformed entity errors.
        raise ValidationError(f"Chrome DOM is not parseable: {error}") from error
    nodes = walk_dom(parser.roots)
    headings = [node for node in nodes if node.tag == "h1"]
    paragraphs = [node for node in nodes if node.tag == "p"]
    navigations = [node for node in nodes if node.tag == "nav"]
    status_nodes = [node for node in nodes if node.attributes.get("role") == "status"]
    main_nodes = [
        node
        for node in nodes
        if node.tag == "main" or node.attributes.get("role") == "main"
    ]
    links = [node for node in nodes if node.tag == "a"]
    observed_links = [
        {
            "id": node.attributes.get("data-route-id"),
            "text": dom_text(node),
            "href": node.attributes.get("href"),
            "requiresAuth": dom_boolean(node.attributes.get("data-requires-auth")),
            "deepLink": dom_boolean(node.attributes.get("data-deep-link")),
        }
        for node in links
    ]
    expected_routes = model["routes"]
    expected_link_rows = [
        {
            "id": route["id"],
            "text": route["title"],
            "href": route["path"],
            "requiresAuth": route["requiresAuth"],
            "deepLink": route["deepLink"],
        }
        for route in expected_routes
    ]
    h1_text = dom_text(headings[0]) if headings else None
    navigation_label = (
        navigations[0].attributes.get("aria-label") if navigations else None
    )
    status_text = dom_text(status_nodes[0]) if status_nodes else None
    route_paragraphs = [
        dom_text(node) for node in paragraphs if node.attributes.get("role") != "status"
    ]
    route_text = route_paragraphs[0] if route_paragraphs else None
    main_attributes = main_nodes[0].attributes if main_nodes else {}
    main_role = "main" if main_nodes else None
    heading_level = 1 if headings else None
    observed_route = {
        "id": main_attributes.get("data-route-id"),
        "path": main_attributes.get("data-route-path"),
        "title": h1_text,
        "text": route_text,
        "requiresAuth": dom_boolean(main_attributes.get("data-requires-auth")),
        "deepLink": dom_boolean(main_attributes.get("data-deep-link")),
    }
    expected_text = " ".join(str(expected["text"]).split())
    comparisons = {
        "route_id": observed_route["id"] == expected["id"],
        "route_path": observed_route["path"] == expected["path"],
        "h1_title": h1_text == " ".join(str(expected["title"]).split()),
        "route_text": route_text == expected_text,
        "requires_auth": observed_route["requiresAuth"] is expected["requiresAuth"],
        "deep_link": observed_route["deepLink"] is expected["deepLink"],
        "navigation_label": navigation_label == model["navigation"]["label"],
        "main_role": main_role == model["render"]["mainRole"],
        "heading_level": heading_level == model["render"]["headingLevel"],
        "status_role_and_text": bool(status_text),
        "navigation_routes_and_flags": observed_links == expected_link_rows,
    }
    return {
        "route": observed_route,
        "h1_text": h1_text,
        "route_text": route_text,
        "navigation_label": navigation_label,
        "status_text": status_text,
        "main_role_present": bool(main_nodes),
        "main_role": main_role,
        "heading_level": heading_level,
        "links": observed_links,
        "comparisons": comparisons,
        "matches_model": all(comparisons.values()),
    }


def available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
        stream.bind(("127.0.0.1", 0))
        return int(stream.getsockname()[1])


def terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def execute_browser_journey(
    profile: ProfileArtifact,
    workspace: Path,
    policy: RunnerPolicy,
    server_argv_template: Sequence[str],
    server_env: Mapping[str, str],
) -> dict[str, Any]:
    version = run_command(
        [policy.chrome_path, "--version"],
        cwd=workspace,
        timeout_seconds=policy.timeout_seconds,
        no_network=policy.no_network,
        explicit_env={"CI": "1", "NO_COLOR": "1"},
    )
    if version["status"] == "TOOL_UNAVAILABLE":
        return {
            "status": "NOT_RUN",
            "reason": "GOOGLE_CHROME_UNAVAILABLE",
            "browser_version": version,
            "server": None,
            "probes": [],
        }
    if version["status"] != "PASSED":
        return {
            "status": "FAILED",
            "reason": "GOOGLE_CHROME_VERSION_COMMAND_FAILED",
            "browser_version": version,
            "server": None,
            "probes": [],
        }

    port = available_loopback_port()
    server_argv = [value.replace("{port}", str(port)) for value in server_argv_template]
    executable = (
        Path(server_argv[0])
        if Path(server_argv[0]).is_absolute()
        else Path(shutil.which(server_argv[0]) or "")
    )
    if not executable.is_file() or not os.access(executable, os.X_OK):
        return {
            "status": "NOT_RUN",
            "reason": "DEV_SERVER_TOOL_UNAVAILABLE",
            "browser_version": version,
            "server": skipped_command(server_argv, workspace, "EXECUTABLE_NOT_FOUND"),
            "probes": [],
        }
    environment, env_evidence = process_environment(policy.no_network, server_env)
    resolved_argv = [str(executable.resolve()), *server_argv[1:]]
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    started = time.monotonic()
    readiness_url = (
        f"http://127.0.0.1:{port}{profile.relift_model['routes'][0]['path']}"
    )
    attempts = 0
    last_error: str | None = None
    ready = False
    probes: list[dict[str, Any]] = []
    loopback_opener = build_opener(ProxyHandler({}))
    with (
        tempfile.TemporaryFile() as stdout_file,
        tempfile.TemporaryFile() as stderr_file,
    ):
        try:
            process = subprocess.Popen(
                resolved_argv,
                cwd=workspace,
                env=environment,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
        except OSError as error:
            return {
                "status": "FAILED",
                "reason": "DEV_SERVER_START_FAILED",
                "browser_version": version,
                "server": {
                    **skipped_command(resolved_argv, workspace, str(error)),
                    "status": "FAILED",
                },
                "probes": [],
            }
        deadline = time.monotonic() + min(policy.timeout_seconds, 60)
        try:
            while time.monotonic() < deadline:
                attempts += 1
                if process.poll() is not None:
                    last_error = f"server exited with {process.returncode}"
                    break
                try:
                    with loopback_opener.open(readiness_url, timeout=1) as response:
                        if 200 <= response.status < 400:
                            ready = True
                            break
                except (HTTPError, URLError, TimeoutError, OSError) as error:
                    last_error = f"{type(error).__name__}: {error}"
                time.sleep(0.1)
            if ready:
                user_data = workspace / ".elmos-chrome-profile"
                unknown_path = "/__elmos_unknown_route__"
                if any(
                    route["path"] == unknown_path
                    for route in profile.relift_model["routes"]
                ):
                    unknown_path = "/__elmos_unknown_route_2__"
                requested = [
                    (
                        "initial",
                        "INITIAL_RENDER",
                        None,
                        profile.relift_model["routes"][0]["path"],
                        "FIRST_DECLARED_FALLBACK",
                    ),
                    *(
                        (
                            f"declared-{index}",
                            "SELECT_DECLARED_PATH",
                            route["path"],
                            route["path"],
                            "DECLARED",
                        )
                        for index, route in enumerate(profile.relift_model["routes"])
                    ),
                    (
                        "unknown",
                        "SELECT_UNKNOWN_PATH",
                        unknown_path,
                        unknown_path,
                        "FIRST_DECLARED_FALLBACK",
                    ),
                ]
                for (
                    probe_name,
                    operation,
                    input_path,
                    requested_path,
                    resolution,
                ) in requested:
                    expected = next(
                        (
                            route
                            for route in profile.relift_model["routes"]
                            if route["path"] == requested_path
                        ),
                        profile.relift_model["routes"][0],
                    )
                    chrome_args = [
                        policy.chrome_path,
                        "--headless=new",
                        "--disable-background-networking",
                        "--disable-component-update",
                        "--disable-default-apps",
                        "--disable-extensions",
                        "--disable-sync",
                        "--metrics-recording-only",
                        "--no-first-run",
                        "--no-proxy-server",
                        f"--user-data-dir={user_data}",
                        "--virtual-time-budget=3000",
                        "--dump-dom",
                        *(
                            [
                                "--host-resolver-rules=MAP * 0.0.0.0, EXCLUDE localhost, EXCLUDE 127.0.0.1"
                            ]
                            if policy.no_network
                            else []
                        ),
                        f"http://127.0.0.1:{port}{requested_path}",
                    ]
                    command = run_command(
                        chrome_args,
                        cwd=workspace,
                        timeout_seconds=policy.timeout_seconds,
                        no_network=policy.no_network,
                        explicit_env={"CI": "1", "NO_COLOR": "1"},
                    )
                    observation = None
                    probe_status = "FAILED"
                    reason = None
                    if command["status"] != "PASSED":
                        reason = "CHROME_NAVIGATION_FAILED"
                    elif command["stdout"]["truncated"]:
                        reason = "CHROME_DOM_TRUNCATED"
                    else:
                        try:
                            observation = observe_dom(
                                command["stdout"]["text"],
                                profile.relift_model,
                                expected,
                            )
                            if observation["matches_model"]:
                                probe_status = "PASSED"
                            else:
                                reason = "DOM_MODEL_MISMATCH"
                        except ValidationError as error:
                            reason = str(error)
                    probes.append(
                        {
                            "name": probe_name,
                            "operation": operation,
                            "input_path": input_path,
                            "resolution": resolution,
                            "requested_path": requested_path,
                            "expected_route": dict(expected),
                            "command": command,
                            "dom_sha256": command["stdout"]["sha256"],
                            "observation": observation,
                            "normalized_observation": (
                                {
                                    "operation": operation,
                                    "input_path": input_path,
                                    "resolution": resolution,
                                    "route": observation["route"],
                                    "render": {
                                        "navigationLabel": observation[
                                            "navigation_label"
                                        ],
                                        "mainRole": observation["main_role"],
                                        "headingLevel": observation["heading_level"],
                                    },
                                    "status": {
                                        "role": "status"
                                        if observation["status_text"] is not None
                                        else None,
                                        "text": observation["status_text"],
                                    },
                                    "navigationLinks": observation["links"],
                                }
                                if observation is not None
                                else None
                            ),
                            "status": probe_status,
                            "reason": reason,
                        }
                    )
        finally:
            terminate_process_group(process)
        stdout_file.seek(0)
        stderr_file.seek(0)
        server_stdout = stdout_file.read()
        server_stderr = stderr_file.read()
        duration_ms = round((time.monotonic() - started) * 1000)
        server_record = {
            "argv": resolved_argv,
            "cwd": str(workspace.resolve()),
            "started_at": started_at,
            "duration_ms": duration_ms,
            "timeout_seconds": policy.timeout_seconds,
            "exit_code": process.returncode,
            "signal": (
                -process.returncode
                if process.returncode is not None and process.returncode < 0
                else None
            ),
            "status": "PASSED" if ready else "FAILED",
            "reason": "TERMINATED_AFTER_JOURNEY" if ready else "DEV_SERVER_NOT_READY",
            "environment": env_evidence,
            "readiness": {
                "url": readiness_url,
                "attempts": attempts,
                "status": "PASSED" if ready else "FAILED",
                "last_error": last_error,
            },
            "stdout": bounded_stream(server_stdout),
            "stderr": bounded_stream(server_stderr),
        }
    if not ready:
        return {
            "status": "FAILED",
            "reason": "DEV_SERVER_NOT_READY",
            "browser_version": version,
            "server": server_record,
            "probes": probes,
        }
    failed_probe = next(
        (probe for probe in probes if probe["status"] != "PASSED"), None
    )
    return {
        "status": "FAILED" if failed_probe else "PASSED",
        "reason": failed_probe["reason"] if failed_probe else None,
        "browser_version": version,
        "server": server_record,
        "probes": probes,
    }


def unsupported_browser_journey(reason: str) -> dict[str, Any]:
    return {
        "status": "NOT_RUN",
        "reason": reason,
        "browser_version": None,
        "server": None,
        "probes": [],
    }


def executable_candidate_rows(
    candidates: Sequence[tuple[str, Path]],
) -> tuple[list[dict[str, Any]], Path | None]:
    rows: list[dict[str, Any]] = []
    selected: Path | None = None
    seen: set[str] = set()
    for source, candidate in candidates:
        absolute = candidate.expanduser()
        key = str(absolute)
        if key in seen:
            continue
        seen.add(key)
        exists = absolute.is_file()
        executable = exists and os.access(absolute, os.X_OK)
        row: dict[str, Any] = {
            "source": source,
            "candidate_path": key,
            "exists": exists,
            "executable": executable,
            "selected": False,
            "realpath": None,
            "sha256": None,
            "byte_count": None,
        }
        if executable:
            resolved = absolute.resolve()
            data = resolved.read_bytes()
            row.update(
                {
                    "realpath": str(resolved),
                    "sha256": sha256_bytes(data),
                    "byte_count": len(data),
                }
            )
            if selected is None:
                selected = resolved
                row["selected"] = True
        rows.append(row)
    return rows, selected


def android_runtime_inventory(
    workspace: Path, policy: RunnerPolicy
) -> list[dict[str, Any]]:
    candidates: list[tuple[str, Path]] = []
    path_candidate = shutil.which("adb")
    if path_candidate:
        candidates.append(("PATH", Path(path_candidate)))
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(key)
        if value:
            candidates.append((key, Path(value) / "platform-tools/adb"))
    rows, selected = executable_candidate_rows(candidates)
    result: list[dict[str, Any]] = [
        {
            "kind": "ANDROID_PROJECT_INVENTORY",
            "android_directory": (workspace / "android").is_dir(),
            "integration_driver": (
                workspace / "integration_test/frontend_formal_interaction_test.dart"
            ).is_file()
            or (workspace / "e2e/frontend-formal-interaction.test.ts").is_file(),
            "requested_device_id": policy.android_device_id,
            "required_execution_plan": (
                [
                    [policy.flutter_path, "build", "apk", "--debug", "--no-pub"],
                    [
                        policy.flutter_path,
                        "test",
                        "integration_test/frontend_formal_interaction_test.dart",
                        "-d",
                        policy.android_device_id or "{ANDROID_DEVICE_ID}",
                        "--no-dds",
                        "--concurrency=1",
                    ],
                ]
                if workspace.joinpath("pubspec.yaml").is_file()
                else [
                    [
                        "npm",
                        "run",
                        "android",
                        "--",
                        "--device",
                        policy.android_device_id or "{ANDROID_DEVICE_ID}",
                    ],
                    [
                        "node",
                        "e2e/frontend-formal-native-probe.mjs",
                        "--platform",
                        "android",
                    ],
                ]
            ),
            "execution_status": "NOT_RUN",
        },
        {"kind": "ADB_CANDIDATES", "candidates": rows},
    ]
    if selected is not None:
        result.extend(
            [
                {
                    "kind": "ADB_VERSION",
                    "command": run_command(
                        [str(selected), "version"],
                        cwd=workspace,
                        timeout_seconds=min(policy.timeout_seconds, 30),
                        no_network=True,
                        explicit_env={"CI": "1", "NO_COLOR": "1"},
                    ),
                },
                {
                    "kind": "ADB_DEVICES",
                    "command": run_command(
                        [str(selected), "devices", "-l"],
                        cwd=workspace,
                        timeout_seconds=min(policy.timeout_seconds, 30),
                        no_network=True,
                        explicit_env={"CI": "1", "NO_COLOR": "1"},
                    ),
                },
            ]
        )
    return result


def ios_runtime_inventory(
    workspace: Path, policy: RunnerPolicy
) -> list[dict[str, Any]]:
    path_candidate = shutil.which("xcrun")
    rows, selected = executable_candidate_rows(
        [("PATH", Path(path_candidate))] if path_candidate else []
    )
    result: list[dict[str, Any]] = [
        {
            "kind": "IOS_PROJECT_INVENTORY",
            "ios_directory": (workspace / "ios").is_dir(),
            "integration_driver": (
                workspace / "integration_test/frontend_formal_interaction_test.dart"
            ).is_file()
            or (workspace / "e2e/frontend-formal-interaction.test.ts").is_file(),
            "requested_simulator_udid": policy.ios_simulator_udid,
            "required_execution_plan": (
                [
                    [
                        policy.flutter_path,
                        "build",
                        "ios",
                        "--simulator",
                        "--no-codesign",
                        "--no-pub",
                    ],
                    [
                        policy.flutter_path,
                        "test",
                        "integration_test/frontend_formal_interaction_test.dart",
                        "-d",
                        policy.ios_simulator_udid or "{IOS_SIMULATOR_UDID}",
                        "--no-dds",
                        "--concurrency=1",
                    ],
                ]
                if workspace.joinpath("pubspec.yaml").is_file()
                else [
                    [
                        "npm",
                        "run",
                        "ios",
                        "--",
                        "--device",
                        policy.ios_simulator_udid or "{IOS_SIMULATOR_UDID}",
                    ],
                    [
                        "node",
                        "e2e/frontend-formal-native-probe.mjs",
                        "--platform",
                        "ios",
                    ],
                ]
            ),
            "execution_status": "NOT_RUN",
        },
        {"kind": "XCRUN_CANDIDATES", "candidates": rows},
    ]
    if selected is not None:
        result.extend(
            [
                {
                    "kind": "XCODEBUILD_DISCOVERY",
                    "command": run_command(
                        [str(selected), "--find", "xcodebuild"],
                        cwd=workspace,
                        timeout_seconds=min(policy.timeout_seconds, 30),
                        no_network=True,
                        explicit_env={"CI": "1", "NO_COLOR": "1"},
                    ),
                },
                {
                    "kind": "IOS_SIMULATOR_INVENTORY",
                    "command": run_command(
                        [
                            str(selected),
                            "simctl",
                            "list",
                            "devices",
                            "available",
                            "--json",
                        ],
                        cwd=workspace,
                        timeout_seconds=min(policy.timeout_seconds, 30),
                        no_network=True,
                        explicit_env={"CI": "1", "NO_COLOR": "1"},
                    ),
                },
            ]
        )
    return result


def harmony_runtime_inventory(
    workspace: Path, policy: RunnerPolicy
) -> list[dict[str, Any]]:
    candidates: list[tuple[str, Path]] = []
    path_candidate = shutil.which("hdc")
    if path_candidate:
        candidates.append(("PATH", Path(path_candidate)))
    for application in ("DevEco-Studio.app", "DevEco Studio.app"):
        candidates.append(
            (
                "DEVECO_STANDARD_LOCATION",
                Path("/Applications")
                / application
                / "Contents/sdk/default/openharmony/toolchains/hdc",
            )
        )
    rows, selected = executable_candidate_rows(candidates)
    result: list[dict[str, Any]] = [
        {
            "kind": "HARMONY_PROJECT_INVENTORY",
            "entry_directory": (workspace / "entry").is_dir(),
            "integration_driver": (workspace / "entry/src/ohosTest").is_dir(),
            "requested_device_id": policy.harmony_device_id,
            "required_execution_plan": [
                [
                    policy.harmony_tool or "hvigorw",
                    "assembleHap",
                    "--mode",
                    "module",
                    "-p",
                    "module=entry@default",
                    "-p",
                    "buildMode=debug",
                    "--no-daemon",
                ],
                [
                    "hdc",
                    "-t",
                    policy.harmony_device_id or "{HARMONY_DEVICE_ID}",
                    "install",
                    "{EXACT_HAP_PATH}",
                ],
                [
                    "hdc",
                    "-t",
                    policy.harmony_device_id or "{HARMONY_DEVICE_ID}",
                    "shell",
                    "aa",
                    "start",
                    "-a",
                    "EntryAbility",
                    "-b",
                    "{BUNDLE_ID}",
                ],
                [
                    "hdc",
                    "-t",
                    policy.harmony_device_id or "{HARMONY_DEVICE_ID}",
                    "shell",
                    "aa",
                    "test",
                    "-b",
                    "{TEST_BUNDLE_ID}",
                ],
            ],
            "execution_status": "NOT_RUN",
        },
        {"kind": "HDC_CANDIDATES", "candidates": rows},
    ]
    if selected is not None:
        result.append(
            {
                "kind": "HDC_DEVICE_INVENTORY",
                "command": run_command(
                    [str(selected), "list", "targets", "-v"],
                    cwd=workspace,
                    timeout_seconds=min(policy.timeout_seconds, 30),
                    no_network=True,
                    explicit_env={"CI": "1", "NO_COLOR": "1"},
                ),
            }
        )
    return result


def browser_runtime_inventory(
    workspace: Path, policy: RunnerPolicy
) -> list[dict[str, Any]]:
    candidates, _selected = executable_candidate_rows(
        [
            ("CLI_CHROME_PATH", Path(policy.chrome_path)),
            ("CLI_FIREFOX_PATH", Path(policy.firefox_path)),
        ]
    )
    versions = []
    for browser_path in (policy.chrome_path, policy.firefox_path):
        versions.append(
            run_command(
                [browser_path, "--version"],
                cwd=workspace,
                timeout_seconds=min(policy.timeout_seconds, 30),
                no_network=True,
                explicit_env={"CI": "1", "NO_COLOR": "1"},
            )
        )
    return [
        {
            "kind": "PLAYWRIGHT_BROWSER_RUNTIME_INVENTORY",
            "implementation_closure": playwright_implementation_closure(),
            "browser_candidates": candidates,
            "version_commands": versions,
            "required_execution_plan": [
                [
                    str(Path(shutil.which("node") or "node").resolve()),
                    str(PLAYWRIGHT_HELPER_PATH),
                    "{CONTENT_ADDRESSED_CONFIG_PATH}",
                    "{CONTENT_ADDRESSED_RESULT_PATH}",
                ]
            ],
            "execution_status": "NOT_RUN",
        }
    ]


def interaction_runtime_inventory_observations(
    profile: ProfileArtifact,
    workspace: Path,
    policy: RunnerPolicy,
    reason: str,
) -> dict[str, dict[str, Any]]:
    inventories: dict[str, list[dict[str, Any]]] = {
        "browser": browser_runtime_inventory(workspace, policy)
        + [
            {
                "kind": "MODEL_ORACLE_SCAN",
                "findings": [
                    dict(item) for item in profile.runtime_model_oracle_findings
                ],
            }
        ],
        "android": android_runtime_inventory(workspace, policy)
        if "android" in required_runtime_channels(profile.profile_id)
        else [],
        "ios": ios_runtime_inventory(workspace, policy)
        if "ios" in required_runtime_channels(profile.profile_id)
        else [],
        "harmonyos": harmony_runtime_inventory(workspace, policy)
        if "harmonyos" in required_runtime_channels(profile.profile_id)
        else [],
    }
    blocked_reason = (
        "PRECOMPUTED_MODEL_ORACLE_CONSUMED_BY_RUNTIME"
        if profile.runtime_model_oracle_findings
        else reason
    )
    return {
        channel: unavailable_runtime_channel(
            profile.profile_id,
            channel,
            blocked_reason,
            tool_discovery=inventories[channel],
        )
        for channel in RUNTIME_CHANNELS
    }


@dataclass
class RunnerPolicy:
    no_network: bool
    timeout_seconds: int
    selected_profiles: frozenset[str]
    fail_on_unavailable: bool
    network_timeout_seconds: int = 0
    flutter_path: str = "/opt/homebrew/bin/flutter"
    flutter_chrome_path: str | None = None
    flutter_chromedriver_path: str | None = None
    flutter_cft_acquisition_record: Path | None = None
    chrome_path: str = DEFAULT_CHROME_PATH
    firefox_path: str = DEFAULT_FIREFOX_PATH
    harmony_tool: str | None = None
    android_device_id: str | None = None
    ios_simulator_udid: str | None = None
    harmony_device_id: str | None = None
    runtime_evidence_root: Path | None = None
    producer_path: str = str(RUNNER_PATH)
    producer_digest: str = dataclass_field(
        default_factory=lambda: sha256_bytes(RUNNER_PATH.read_bytes())
    )
    producer_byte_count: int = dataclass_field(
        default_factory=lambda: len(RUNNER_PATH.read_bytes())
    )

    def __post_init__(self) -> None:
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")
        if self.network_timeout_seconds == 0:
            self.network_timeout_seconds = min(45, self.timeout_seconds)
        if not 1 <= self.network_timeout_seconds <= self.timeout_seconds:
            raise ValueError("network_timeout_seconds must not exceed timeout_seconds")
        if self.runtime_evidence_root is not None:
            self.runtime_evidence_root = self.runtime_evidence_root.resolve()
        if self.flutter_cft_acquisition_record is not None:
            self.flutter_cft_acquisition_record = (
                self.flutter_cft_acquisition_record.resolve()
            )


def node_tool_versions(
    project: Path, policy: RunnerPolicy
) -> tuple[list[dict[str, Any]], str | None]:
    records = [
        run_command(
            ["node", "--version"],
            cwd=project,
            timeout_seconds=policy.timeout_seconds,
            no_network=policy.no_network,
            explicit_env={"CI": "1", "NO_COLOR": "1"},
        ),
        run_command(
            ["npm", "--version"],
            cwd=project,
            timeout_seconds=policy.timeout_seconds,
            no_network=policy.no_network,
            explicit_env={"CI": "1", "NO_COLOR": "1"},
        ),
    ]
    if any(record["status"] == "TOOL_UNAVAILABLE" for record in records):
        return records, "NODE_OR_NPM_TOOLCHAIN_UNAVAILABLE"
    if any(record["status"] != "PASSED" for record in records):
        return records, "TOOL_VERSION_COMMAND_FAILED"
    if (
        command_output(records[0]) != "v26.0.0"
        or command_output(records[1]) != "11.12.1"
    ):
        return records, "NODE_OR_NPM_VERSION_DRIFT"
    return records, None


def npm_offline_cache_miss(record: Mapping[str, Any]) -> bool:
    output = "\n".join(
        str(record[stream]["text"]) for stream in ("stdout", "stderr")
    ).lower()
    return any(marker.lower() in output for marker in NPM_OFFLINE_MISS_MARKERS)


def annotate_dependency_command(
    record: dict[str, Any], *, purpose: str, network_mode: str
) -> dict[str, Any]:
    record["purpose"] = purpose
    record["network_mode"] = network_mode
    return record


def runtime_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def write_content_addressed_runtime_json(
    evidence_root: Path,
    category: str,
    value: Mapping[str, Any],
) -> tuple[str, str, int]:
    """Persist immutable runtime JSON under a digest-derived safe path."""

    category_path = safe_relative_path(category, "runtime artifact category")
    data = runtime_json_bytes(value)
    digest = sha256_bytes(data)
    relative = PurePosixPath(*category_path.parts) / f"{digest.removeprefix('sha256:')}.json"
    root = evidence_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = root.joinpath(*relative.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValidationError("runtime artifact destination is a symlink")
    if destination.exists():
        if not destination.is_file() or destination.read_bytes() != data:
            raise ValidationError("content-addressed runtime artifact collision")
    else:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            try:
                destination.unlink()
            except OSError:
                pass
            raise
    return relative.as_posix(), digest, len(data)


def runtime_tool_identity(path: Path, version: str) -> dict[str, Any]:
    try:
        absolute = path.expanduser().absolute()
        resolved = absolute.resolve(strict=True)
        data = resolved.read_bytes()
    except (OSError, RuntimeError) as error:
        raise ValidationError(f"runtime executable is unavailable: {error}") from error
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ValidationError("runtime executable is not an executable regular file")
    return {
        "path": str(absolute),
        "realpath": str(resolved),
        "sha256": sha256_bytes(data),
        "byte_count": len(data),
        "version": version,
    }


def directory_inventory_with_symlinks(root: Path, name: str) -> dict[str, Any]:
    """Bind a runtime bundle without following or discarding its symlinks."""

    try:
        resolved_root = root.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValidationError(f"{name} is unavailable: {error}") from error
    if not resolved_root.is_dir():
        raise ValidationError(f"{name} is not a directory")
    rows: list[dict[str, Any]] = []
    for path in sorted(
        resolved_root.rglob("*"), key=lambda item: item.relative_to(resolved_root).as_posix()
    ):
        relative = path.relative_to(resolved_root).as_posix()
        if path.is_symlink():
            rows.append(
                {"path": relative, "type": "symlink", "target": os.readlink(path)}
            )
        elif path.is_file():
            data = path.read_bytes()
            rows.append(
                {
                    "path": relative,
                    "type": "file",
                    "sha256": sha256_bytes(data),
                    "byte_count": len(data),
                }
            )
    return {
        "root": str(resolved_root),
        "file_count": sum(row["type"] == "file" for row in rows),
        "symlink_count": sum(row["type"] == "symlink" for row in rows),
        "byte_count": sum(row.get("byte_count", 0) for row in rows),
        "inventory_digest": digest_json(rows),
    }


def validate_flutter_cft_acquisition_record(
    record_path: Path,
    *,
    chrome_path: Path,
    chromedriver_path: Path,
) -> dict[str, Any]:
    """Validate the official, matching Chrome-for-Testing acquisition closure."""

    record_bytes = record_path.resolve(strict=True).read_bytes()
    record = require_exact_keys(
        read_json(record_path, "Flutter CFT acquisition record"),
        {
            "schema_version",
            "kind",
            "platform",
            "requested_build",
            "resolved_version",
            "official_endpoint",
            "downloads",
            "executables",
            "chrome_app_bundle",
            "disk_kib",
            "network_mode",
            "evidence_digest",
        },
        "Flutter CFT acquisition record",
    )
    without_digest = dict(record)
    evidence_digest = require_sha256(
        without_digest.pop("evidence_digest"),
        "Flutter CFT acquisition evidence_digest",
    )
    endpoint = require_exact_keys(
        record["official_endpoint"],
        {"url", "response"},
        "Flutter CFT acquisition official_endpoint",
    )
    if (
        record["schema_version"] != SCHEMA_VERSION
        or record["kind"] != "official-chrome-for-testing-acquisition-evidence"
        or record["platform"] != "mac-arm64"
        or record["requested_build"] != "151.0.7922"
        or record["resolved_version"] != LOCKED_FLUTTER_WEB_CFT_VERSION
        or endpoint
        != {
            "url": LOCKED_FLUTTER_WEB_CFT_ENDPOINT,
            "response": LOCKED_FLUTTER_WEB_CFT_VERSION,
        }
        or evidence_digest != digest_json(without_digest)
    ):
        raise ValidationError("Flutter CFT acquisition identity drift")

    downloads = record["downloads"]
    expected_downloads = {
        "cft-chrome-archive": LOCKED_FLUTTER_WEB_CFT_CHROME_URL,
        "cft-chromedriver-archive": LOCKED_FLUTTER_WEB_CFT_DRIVER_URL,
    }
    if (
        not isinstance(downloads, list)
        or [item.get("role") for item in downloads]
        != list(expected_downloads)
    ):
        raise ValidationError("Flutter CFT archive closure drift")
    for index, item in enumerate(downloads):
        row = require_exact_keys(
            item,
            {"role", "url", "head", "path", "sha256", "byte_count"},
            f"Flutter CFT acquisition downloads[{index}]",
        )
        head = require_exact_keys(
            row["head"],
            {"status", "content_length", "etag", "last_modified", "x_goog_hash"},
            f"Flutter CFT acquisition downloads[{index}].head",
        )
        if (
            row["url"] != expected_downloads[row["role"]]
            or head["status"] != 200
            or head["content_length"] != row["byte_count"]
            or type(row["byte_count"]) is not int
            or row["byte_count"] < 1
            or not SHA256_PATTERN.fullmatch(str(row["sha256"]))
            or not isinstance(head["etag"], str)
            or not head["etag"]
            or not isinstance(head["last_modified"], str)
            or not head["last_modified"]
            or not isinstance(head["x_goog_hash"], list)
            or not head["x_goog_hash"]
        ):
            raise ValidationError("Flutter CFT archive byte binding drift")
        archive_path = Path(row["path"])
        if archive_path.exists():
            identity = file_identity(
                archive_path, f"Flutter CFT acquisition downloads[{index}].path"
            )
            if (
                row["sha256"] != identity["sha256"]
                or row["byte_count"] != identity["byte_count"]
            ):
                raise ValidationError("Flutter CFT retained archive bytes drift")

    executables = record["executables"]
    if (
        not isinstance(executables, list)
        or [item.get("role") for item in executables]
        != ["cft-chrome-launcher", "cft-chrome-framework", "cft-chromedriver"]
    ):
        raise ValidationError("Flutter CFT executable closure drift")
    executable_rows: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(executables):
        row = require_exact_keys(
            item,
            {"role", "version", "path", "sha256", "byte_count"},
            f"Flutter CFT acquisition executables[{index}]",
        )
        identity = file_identity(
            Path(row["path"]), f"Flutter CFT acquisition executables[{index}].path"
        )
        if (
            row["sha256"] != identity["sha256"]
            or row["byte_count"] != identity["byte_count"]
        ):
            raise ValidationError("Flutter CFT executable byte binding drift")
        executable_rows[row["role"]] = row
    chrome_realpath = chrome_path.resolve(strict=True)
    driver_realpath = chromedriver_path.resolve(strict=True)
    if (
        Path(executable_rows["cft-chrome-launcher"]["path"]).resolve(strict=True)
        != chrome_realpath
        or Path(executable_rows["cft-chromedriver"]["path"]).resolve(strict=True)
        != driver_realpath
        or executable_rows["cft-chrome-launcher"]["version"]
        != f"Google Chrome for Testing {LOCKED_FLUTTER_WEB_CFT_VERSION}"
        or not executable_rows["cft-chromedriver"]["version"].startswith(
            f"ChromeDriver {LOCKED_FLUTTER_WEB_CFT_VERSION} "
        )
        or executable_rows["cft-chrome-framework"]["version"]
        != LOCKED_FLUTTER_WEB_CFT_VERSION
    ):
        raise ValidationError("Flutter CFT Chrome/ChromeDriver version pair drift")

    app_bundle = require_exact_keys(
        record["chrome_app_bundle"],
        {"root", "file_count", "symlink_count", "byte_count", "inventory_digest"},
        "Flutter CFT acquisition chrome_app_bundle",
    )
    if chrome_realpath.parent.parent.parent != Path(app_bundle["root"]).resolve(
        strict=True
    ):
        raise ValidationError("Flutter CFT launcher/app bundle binding drift")
    actual_bundle = directory_inventory_with_symlinks(
        Path(app_bundle["root"]), "Flutter CFT Chrome app bundle"
    )
    if actual_bundle != app_bundle:
        raise ValidationError("Flutter CFT Chrome app bundle digest drift")
    return {
        "record": record,
        "record_path": str(record_path.resolve()),
        "record_sha256": sha256_bytes(record_bytes),
        "record_byte_count": len(record_bytes),
        "evidence_digest": evidence_digest,
        "app_bundle_digest": app_bundle["inventory_digest"],
        "chrome_row": executable_rows["cft-chrome-launcher"],
        "driver_row": executable_rows["cft-chromedriver"],
    }


def interaction_profile_manifest_digest(profile: ProfileArtifact) -> str:
    manifest = read_json(
        profile.manifest_path, f"{profile.profile_id} interaction profile manifest"
    )
    return require_sha256(
        manifest.get("manifest_digest"),
        f"{profile.profile_id} interaction profile manifest_digest",
    )


def validate_flutter_drive_raw_trace(
    profile: ProfileArtifact,
    raw_path: Path,
    *,
    profile_manifest_digest: str,
) -> dict[str, Any]:
    """Validate exact Flutter integration reportData before deriving artifacts."""

    raw = require_exact_keys(
        read_json(raw_path, "Flutter drive raw result"),
        {
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
        },
        "Flutter drive raw result",
    )
    if (
        raw["schema_version"] != SCHEMA_VERSION
        or raw["kind"] != "bounded-frontend-interaction-flutter-runtime-trace"
        or raw["proof_profile"] != INTERACTION_PROOF_PROFILE
        or raw["profile_id"] != "flutter"
        or raw["channel"] != "browser"
        or raw["project_digest"] != profile.project_digest
        or raw["profile_manifest_digest"] != profile_manifest_digest
        or raw["scenario_manifest_digest"] != profile.scenario_manifest_digest
        or raw["runtime_source"] != "FLUTTER_INTEGRATION_SEMANTICS"
        or raw["model_or_precomputed_values_used"] is not False
    ):
        raise ValidationError("Flutter drive raw result identity/provenance drift")

    expected_ids = [item["scenario_id"] for item in profile.scenario_manifest]
    scenarios = raw["scenarios"]
    if (
        expected_ids != list(LOCKED_INTERACTION_SCENARIO_IDS)
        or not isinstance(scenarios, list)
        or [item.get("scenario_id") for item in scenarios if isinstance(item, dict)]
        != expected_ids
        or len(scenarios) != len(expected_ids)
    ):
        raise ValidationError("Flutter drive scenario order/closure drift")
    prior_sequence = 0
    network_count = 0
    platform_count = 0
    normalized: list[dict[str, Any]] = []
    for index, value in enumerate(scenarios):
        scenario_id = expected_ids[index]
        row = require_exact_keys(
            value,
            {
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
            },
            f"Flutter drive scenario {scenario_id}",
        )
        sequence = row["execution_sequence"]
        expected_semantics = (
            f"scenario:{scenario_id}:COMPLETE:sequence:{sequence}"
        )
        if (
            row["scenario_id"] != scenario_id
            or type(sequence) is not int
            or sequence <= prior_sequence
            or row["execution_state"] != "COMPLETE"
            or row["runtime_source"] != "flutter-framework-events"
            or row["semantics_label"] != expected_semantics
        ):
            raise ValidationError(
                f"Flutter drive scenario {scenario_id} execution/semantics drift"
            )
        prior_sequence = sequence
        framework_events = row["framework_events"]
        expected_framework_events = [
            {"kind": "TAP", "target_key": f"action:{scenario_id}"}
        ]
        if framework_events != expected_framework_events:
            raise ValidationError(
                f"Flutter drive scenario {scenario_id} framework trace drift"
            )
        focus = require_exact_keys(
            row["focus"],
            {"target", "query_has_focus"},
            f"Flutter drive scenario {scenario_id}.focus",
        )
        if (
            (focus["target"] is not None and focus["target"] != "query")
            or type(focus["query_has_focus"]) is not bool
            or (focus["target"] == "query") is not focus["query_has_focus"]
            or (
                scenario_id == "FORM_INVALID_SUBMIT_FOCUS_ERROR"
                and focus != {"target": "query", "query_has_focus": True}
            )
        ):
            raise ValidationError(
                f"Flutter drive scenario {scenario_id} focus trace drift"
            )
        network_events = row["network_adapter_events"]
        if not isinstance(network_events, list):
            raise ValidationError(
                f"Flutter drive scenario {scenario_id} network trace is invalid"
            )
        for event_index, event in enumerate(network_events):
            event = require_exact_keys(
                event,
                {"method", "path", "query", "cancel", "outcome"},
                f"Flutter drive scenario {scenario_id}.network[{event_index}]",
            )
            if (
                event["method"] not in {"GET", "POST"}
                or not isinstance(event["path"], str)
                or not event["path"].startswith("/")
                or not isinstance(event["query"], str)
                or type(event["cancel"]) is not bool
                or event["outcome"] not in {"SUCCESS", "ERROR", "STALE"}
            ):
                raise ValidationError(
                    f"Flutter drive scenario {scenario_id} network event drift"
                )
        platform_events = row["platform_adapter_events"]
        if platform_events != []:
            raise ValidationError(
                f"Flutter drive browser scenario {scenario_id} invoked native adapter"
            )
        evidence_refs = require_exact_keys(
            row["evidence_refs"],
            {"semantics", "network", "platform"},
            f"Flutter drive scenario {scenario_id}.evidence_refs",
        )
        if evidence_refs != {
            "semantics": "INLINE_INTEGRATION_BINDING",
            "network": (
                "INLINE_API_ADAPTER_TRACE" if network_events else None
            ),
            "platform": None,
        }:
            raise ValidationError(
                f"Flutter drive scenario {scenario_id} inline evidence refs drift"
            )
        blocks = row["blocks"]
        if not isinstance(blocks, dict) or tuple(blocks) != INTERACTION_BLOCK_IDS:
            raise ValidationError(
                f"Flutter drive scenario {scenario_id} block closure drift"
            )
        normalized_blocks: dict[str, dict[str, Any]] = {}
        for block_id in INTERACTION_BLOCK_IDS:
            actual = require_exact_keys(
                blocks[block_id],
                INTERACTION_BLOCK_ACTUAL_KEYS[block_id],
                f"Flutter drive scenario {scenario_id}.{block_id}",
            )
            normalized_blocks[block_id] = actual
        api = normalized_blocks["api-network"]
        if bool(api["called"] or api["canceled"]) is not bool(network_events):
            raise ValidationError(
                f"Flutter drive scenario {scenario_id} API adapter trace mismatch"
            )
        native = normalized_blocks["native-platform"]
        if (
            native["attempted"] is not False
            or native["available"] is not False
            or native["outcome"] != "NOT_ATTEMPTED"
        ):
            raise ValidationError(
                f"Flutter drive scenario {scenario_id} browser native projection drift"
            )
        network_count += len(network_events)
        platform_count += len(platform_events)
        normalized.append({**row, "blocks": normalized_blocks})

    summary = require_exact_keys(
        raw["summary"],
        {
            "scenario_count",
            "block_count",
            "all_complete",
            "network_adapter_event_count",
            "platform_adapter_event_count",
        },
        "Flutter drive raw result summary",
    )
    if summary != {
        "scenario_count": len(expected_ids),
        "block_count": len(INTERACTION_BLOCK_IDS),
        "all_complete": True,
        "network_adapter_event_count": network_count,
        "platform_adapter_event_count": platform_count,
    } or network_count < 1:
        raise ValidationError("Flutter drive summary/count closure drift")
    return {"raw": raw, "scenarios": normalized, "summary": summary}


def runtime_execution_from_command(
    record: Mapping[str, Any],
    *,
    phase: str,
    tool: Mapping[str, Any],
    artifact_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Bind one actually executed subprocess to the runtime execution schema."""

    if record.get("status") != "PASSED" or record.get("exit_code") != 0:
        raise ValidationError(f"cannot promote unsuccessful {phase} subprocess")
    value = {
        "schema_version": SCHEMA_VERSION,
        "kind": "frontend-interaction-runtime-execution",
        "phase": phase,
        "tool": dict(tool),
        "argv": list(record["argv"]),
        "cwd": record["cwd"],
        "started_at": record["started_at"],
        "duration_ms": record["duration_ms"],
        "timeout_seconds": record["timeout_seconds"],
        "exit_code": record["exit_code"],
        "signal": record["signal"],
        "status": record["status"],
        "reason": record["reason"],
        "environment": dict(record["environment"]),
        "stdout": dict(record["stdout"]),
        "stderr": dict(record["stderr"]),
        "artifact_refs": list(artifact_refs),
    }
    value["execution_id"] = digest_json(value)
    return value


def runtime_phase_policy(execution: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "phase": execution["phase"],
        "tool": dict(execution["tool"]),
        "argv": list(execution["argv"]),
        "cwd": execution["cwd"],
        "environment": dict(execution["environment"]),
    }


def browser_trace_ref(
    evidence_root: Path,
    *,
    profile_id: str,
    scenario_id: str,
    role: str,
    capture: Mapping[str, Any],
) -> dict[str, Any]:
    value = {
        "schema_version": SCHEMA_VERSION,
        "kind": "frontend-interaction-runtime-trace-artifact",
        "actual_source": "ALLOWLISTED_RUNTIME_CAPTURE",
        "role": role,
        "profile_id": profile_id,
        "channel": "browser",
        "scenario_id": scenario_id,
        "capture": dict(capture),
    }
    relative, sha, byte_count = write_content_addressed_runtime_json(
        evidence_root,
        f"traces/{profile_id}/browser/{scenario_id}/{role}",
        value,
    )
    ref = {
        "role": role,
        "profile_id": profile_id,
        "channel": "browser",
        "scenario_id": scenario_id,
        "path": relative,
        "sha256": sha,
        "byte_count": byte_count,
    }
    ref["artifact_id"] = digest_json(ref)
    return ref


def browser_observation_ref(
    evidence_root: Path,
    *,
    profile_id: str,
    scenario_id: str,
    block_id: str,
    scenario_input: Mapping[str, Any],
    browser_measurements: Sequence[Mapping[str, Any]],
    trace_refs: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = BLOCK_OBSERVER_SPECS[block_id]
    browser_matrix: list[dict[str, Any]] = []
    derived_actuals: list[dict[str, Any]] = []
    for index, row in enumerate(browser_measurements):
        measurement_row = require_exact_keys(
            row,
            {"browser_id", "measurement"},
            f"{scenario_id}.{block_id}.browser_measurements[{index}]",
        )
        measurement = validate_block_observer_measurement(
            measurement_row["measurement"],
            block_id=block_id,
            name=f"{scenario_id}.{block_id}.{measurement_row['browser_id']}",
        )
        browser_matrix.append(
            {
                "browser_id": measurement_row["browser_id"],
                "measurement": measurement,
            }
        )
        derived_actuals.append(
            derive_actual_from_block_measurement(
                block_id,
                measurement,
                scenario_input=scenario_input,
                name=f"{scenario_id}.{block_id}.{measurement_row['browser_id']}",
            )
        )
    if not derived_actuals or any(
        actual != derived_actuals[0] for actual in derived_actuals[1:]
    ):
        raise ValidationError(
            f"{scenario_id}.{block_id} cross-browser derived actual values differ"
        )
    actual = derived_actuals[0]
    trace_value = {
        "schema_version": SCHEMA_VERSION,
        "kind": "frontend-interaction-block-observer-trace-artifact",
        "actual_source": "ALLOWLISTED_BLOCK_OBSERVER_CAPTURE",
        "role": spec["trace_role"],
        "profile_id": profile_id,
        "channel": "browser",
        "scenario_id": scenario_id,
        "block_id": block_id,
        "observer_kind": spec["observer_kind"],
        "capture": {
            "observer_contract": BLOCK_OBSERVER_CONTRACT,
            "measurement_surface": spec["measurement_surface"],
            "browser_matrix": browser_matrix,
        },
    }
    trace_relative, trace_sha, trace_byte_count = (
        write_content_addressed_runtime_json(
            evidence_root,
            (
                f"traces/{profile_id}/browser/{scenario_id}/"
                f"{spec['trace_role']}"
            ),
            trace_value,
        )
    )
    observation_trace_ref = {
        "role": spec["trace_role"],
        "profile_id": profile_id,
        "channel": "browser",
        "scenario_id": scenario_id,
        "block_id": block_id,
        "observer_kind": spec["observer_kind"],
        "path": trace_relative,
        "sha256": trace_sha,
        "byte_count": trace_byte_count,
    }
    observation_trace_ref["artifact_id"] = digest_json(observation_trace_ref)
    supporting_trace_refs = [
        dict(trace_refs[role]) for role in spec["supporting_trace_roles"]
    ]
    value = {
        "schema_version": SCHEMA_VERSION,
        "kind": "frontend-interaction-runtime-block-observation",
        "actual_source": BLOCK_SPECIFIC_RUNTIME_ACTUAL_SOURCE,
        "profile_id": profile_id,
        "channel": "browser",
        "scenario_id": scenario_id,
        "block_id": block_id,
        "provenance": {
            "runner_kind": "PLAYWRIGHT_BROWSER_INTERACTION",
            "observer_contract": BLOCK_OBSERVER_CONTRACT,
            "observer_kind": spec["observer_kind"],
            "measurement_surface": spec["measurement_surface"],
            "observation_trace_ref": observation_trace_ref,
            "supporting_trace_refs": supporting_trace_refs,
            "model_values_used_as_actual": False,
        },
        "actual": actual,
    }
    relative, sha, byte_count = write_content_addressed_runtime_json(
        evidence_root,
        f"observations/{profile_id}/browser/{scenario_id}/{block_id}",
        value,
    )
    ref = {
        "role": "runtime-block-observation",
        "profile_id": profile_id,
        "channel": "browser",
        "scenario_id": scenario_id,
        "block_id": block_id,
        "path": relative,
        "sha256": sha,
        "byte_count": byte_count,
        "actual_digest": digest_json(actual),
    }
    ref["artifact_id"] = digest_json(ref)
    return ref, observation_trace_ref


def flutter_browser_observation_ref(
    evidence_root: Path,
    *,
    scenario_id: str,
    block_id: str,
    actual: Mapping[str, Any],
    framework_trace_ref: Mapping[str, Any],
    semantics_trace_ref: Mapping[str, Any],
    network_trace_ref: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Fail closed until Flutter has the block-specific observer protocol.

    Flutter drive ``reportData`` is a useful raw diagnostic, but the current
    adapter does not independently derive each block actual from the same
    allowlisted measurement protocol used by the strict browser observer.  In
    particular, relabelling the driver-provided ``blocks`` object as a runtime
    observation would recreate the forbidden self-reporting path.  Keep this
    callable as an explicit guard for stale callers, but never write an
    observation artifact or reference from it.
    """

    del (
        evidence_root,
        scenario_id,
        block_id,
        actual,
        framework_trace_ref,
        semantics_trace_ref,
        network_trace_ref,
    )
    raise ValidationError(
        "Flutter block-specific runtime observer is not implemented; "
        "the browser channel must remain NOT_RUN"
    )


def validate_playwright_browser_run_identity(
    value: Mapping[str, Any],
    *,
    expected_browser_id: str,
    expected_engine: str,
    binary_version: str,
    executable_identity: Mapping[str, Any],
    name: str,
) -> dict[str, Any]:
    """Bind the probe browser row to the exact discovered executable bytes."""

    browser = require_exact_keys(
        dict(value),
        {
            "browser_id",
            "engine",
            "executable",
            "browser_version",
            "status",
            "reason",
            "scenario_count",
            "scenarios",
        },
        name,
    )
    executable = require_exact_keys(
        browser["executable"],
        {
            "browser_id",
            "engine",
            "executable_path",
            "executable_sha256",
            "executable_byte_count",
        },
        f"{name}.executable",
    )
    expected_version_prefix = {
        "chromium": "Google Chrome for Testing ",
        "firefox": "Mozilla Firefox ",
    }.get(expected_engine)
    if expected_version_prefix is None or not binary_version.startswith(
        expected_version_prefix
    ):
        raise ValidationError(f"{name} binary version brand drift")
    expected_browser_version = binary_version.removeprefix(expected_version_prefix)
    if (
        browser["browser_id"] != expected_browser_id
        or browser["engine"] != expected_engine
        or executable["browser_id"] != expected_browser_id
        or executable["engine"] != expected_engine
        or executable["executable_path"] != executable_identity.get("realpath")
        or executable["executable_sha256"] != executable_identity.get("sha256")
        or executable["executable_byte_count"]
        != executable_identity.get("byte_count")
        or browser["browser_version"] != expected_browser_version
    ):
        raise ValidationError(f"{name} executable/version identity drift")
    return browser


def execute_interaction_browser_runtime(
    profile: ProfileArtifact,
    workspace: Path,
    policy: RunnerPolicy,
    *,
    npm_path: str,
    npm_version: str,
    npm_environment: Mapping[str, str],
    build_command: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Run the strict two-browser interaction matrix and persist actual traces."""

    if policy.runtime_evidence_root is None:
        return (
            unavailable_runtime_channel(
                profile.profile_id,
                "browser",
                "RUNTIME_EVIDENCE_ROOT_NOT_CONFIGURED",
            ),
            None,
        )
    evidence_root = policy.runtime_evidence_root
    try:
        implementation = playwright_implementation_closure()
    except ValidationError as error:
        return (
            unavailable_runtime_channel(
                profile.profile_id,
                "browser",
                "PLAYWRIGHT_IMPLEMENTATION_CLOSURE_INVALID",
                tool_discovery=[{"kind": "PLAYWRIGHT_CLOSURE_ERROR", "error": str(error)}],
            ),
            None,
        )

    browser_rows: list[tuple[str, str, str, dict[str, Any]]] = []
    discovery: list[dict[str, Any]] = [
        {
            "kind": "PLAYWRIGHT_BROWSER_IMPLEMENTATION_CLOSURE",
            "implementation": implementation,
        }
    ]
    for browser_id, engine, executable_path in (
        ("google-chrome", "chromium", policy.chrome_path),
        ("mozilla-firefox", "firefox", policy.firefox_path),
    ):
        version_record = run_command(
            [executable_path, "--version"],
            cwd=workspace,
            timeout_seconds=min(policy.timeout_seconds, 30),
            no_network=True,
            explicit_env={"CI": "1", "NO_COLOR": "1"},
        )
        discovery.append(
            {
                "kind": "BROWSER_VERSION_EXECUTION",
                "browser_id": browser_id,
                "engine": engine,
                "execution": version_record,
            }
        )
        if version_record["status"] != "PASSED":
            return (
                unavailable_runtime_channel(
                    profile.profile_id,
                    "browser",
                    f"{browser_id.upper().replace('-', '_')}_UNAVAILABLE",
                    tool_discovery=discovery,
                ),
                None,
            )
        version = command_output(version_record)
        try:
            identity = runtime_tool_identity(Path(executable_path), version)
        except ValidationError as error:
            discovery.append(
                {
                    "kind": "BROWSER_IDENTITY_ERROR",
                    "browser_id": browser_id,
                    "error": str(error),
                }
            )
            return (
                unavailable_runtime_channel(
                    profile.profile_id,
                    "browser",
                    "BROWSER_EXECUTABLE_IDENTITY_INVALID",
                    tool_discovery=discovery,
                ),
                None,
            )
        browser_rows.append((browser_id, engine, version, identity))

    discovery.append(
        {
            "kind": "EXACT_BROWSER_MATRIX",
            "policy_id": "node-web-chromium-firefox-v1",
            "browser_matrix": [
                {
                    "browser_id": browser_id,
                    "engine": engine,
                    "version": version,
                    "executable_sha256": identity["sha256"],
                }
                for browser_id, engine, version, identity in browser_rows
            ],
            "cross_browser": True,
        }
    )

    port = available_loopback_port()
    if profile.profile_id == "angular":
        server_argv = [
            npm_path,
            "run",
            "start",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]
    else:
        server_argv = [
            npm_path,
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--strictPort",
        ]
    server_environment, server_environment_evidence = process_environment(
        True,
        {
            **npm_environment,
            "BROWSER": "none",
            "CI": "1",
            "NO_COLOR": "1",
        },
    )
    resolved_server_argv = [str(Path(npm_path).resolve()), *server_argv[1:]]
    readiness_url = f"http://127.0.0.1:{port}/"
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    server_started = time.monotonic()
    attempts = 0
    last_error: str | None = None
    ready = False
    probe_command: dict[str, Any] | None = None
    startup_check: dict[str, Any] | None = None
    raw_result_path: Path | None = None
    config_path: Path | None = None
    with (
        tempfile.TemporaryFile() as server_stdout_file,
        tempfile.TemporaryFile() as server_stderr_file,
    ):
        try:
            server = subprocess.Popen(
                resolved_server_argv,
                cwd=workspace,
                env=server_environment,
                stdout=server_stdout_file,
                stderr=server_stderr_file,
                start_new_session=True,
            )
        except OSError as error:
            discovery.append(
                {
                    "kind": "DEV_SERVER_START_ERROR",
                    "argv": resolved_server_argv,
                    "error": str(error),
                }
            )
            return (
                unavailable_runtime_channel(
                    profile.profile_id,
                    "browser",
                    "DEV_SERVER_START_FAILED",
                    tool_discovery=discovery,
                ),
                None,
            )
        try:
            opener = build_opener(ProxyHandler({}))
            deadline = time.monotonic() + min(policy.timeout_seconds, 60)
            while time.monotonic() < deadline:
                attempts += 1
                if server.poll() is not None:
                    last_error = f"server exited with {server.returncode}"
                    break
                try:
                    with opener.open(readiness_url, timeout=1) as response:
                        if 200 <= response.status < 400:
                            ready = True
                            break
                except (HTTPError, URLError, TimeoutError, OSError) as error:
                    last_error = f"{type(error).__name__}: {error}"
                time.sleep(0.1)
            if ready:
                startup_script = (
                    "import sys,urllib.request;"
                    "opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));"
                    "response=opener.open(sys.argv[1],timeout=5);"
                    "status=response.status;response.read(1);response.close();"
                    "print(status);raise SystemExit(0 if 200<=status<400 else 1)"
                )
                startup_check = run_command(
                    [str(Path(sys.executable).resolve()), "-c", startup_script, readiness_url],
                    cwd=workspace,
                    timeout_seconds=min(policy.timeout_seconds, 30),
                    no_network=True,
                    explicit_env={"CI": "1", "NO_COLOR": "1"},
                )
                if startup_check["status"] == "PASSED":
                    config = {
                        "schema_version": SCHEMA_VERSION,
                        "kind": "frontend-interaction-playwright-probe-config",
                        "profile_id": profile.profile_id,
                        "project_digest": profile.project_digest,
                        "proof_profile": INTERACTION_PROOF_PROFILE,
                        "base_url": readiness_url,
                        "scenario_manifest": [
                            {
                                "scenario_id": item["scenario_id"],
                                "input": dict(item["input"]),
                            }
                            for item in profile.scenario_manifest
                        ],
                        "semantic_block_ids": list(INTERACTION_BLOCK_IDS),
                        "block_observer_contracts": dict(
                            profile.runtime_driver_contract[
                                "block_observer_contracts"
                            ]
                        ),
                        "playwright_package_root": str(PLAYWRIGHT_PACKAGE_ROOT.resolve()),
                        "axe_package_root": str(AXE_PACKAGE_ROOT.resolve()),
                        "browsers": [
                            {
                                "browser_id": browser_id,
                                "engine": engine,
                                "executable_path": identity["realpath"],
                                "executable_sha256": identity["sha256"],
                                "executable_byte_count": identity["byte_count"],
                            }
                            for browser_id, engine, _version, identity in browser_rows
                        ],
                        "timeout_ms": min(policy.timeout_seconds, 60) * 1000,
                    }
                    config_relative, config_sha, _config_bytes = (
                        write_content_addressed_runtime_json(
                            evidence_root,
                            f"inputs/{profile.profile_id}/browser/playwright-config",
                            config,
                        )
                    )
                    config_path = evidence_root.joinpath(
                        *PurePosixPath(config_relative).parts
                    )
                    raw_result_path = evidence_root / (
                        f"raw/{profile.profile_id}/browser/"
                        f"playwright-result-{config_sha.removeprefix('sha256:')}.json"
                    )
                    raw_result_path.parent.mkdir(parents=True, exist_ok=True)
                    if raw_result_path.exists() or raw_result_path.is_symlink():
                        raise ValidationError("Playwright raw result path collision")
                    node_path = Path(shutil.which("node") or "")
                    if not node_path.is_file():
                        raise ValidationError("Node is unavailable for Playwright runtime")
                    probe_command = run_command(
                        [
                            str(node_path.resolve()),
                            str(PLAYWRIGHT_HELPER_PATH.resolve()),
                            str(config_path.resolve()),
                            str(raw_result_path.resolve()),
                        ],
                        cwd=workspace,
                        timeout_seconds=policy.timeout_seconds,
                        no_network=True,
                        explicit_env={"CI": "1", "NO_COLOR": "1"},
                    )
        except ValidationError as error:
            last_error = str(error)
        finally:
            terminate_process_group(server)
        server_stdout_file.seek(0)
        server_stderr_file.seek(0)
        server_record = {
            "kind": "DEV_SERVER_LIFECYCLE",
            "argv": resolved_server_argv,
            "cwd": str(workspace.resolve()),
            "started_at": started_at,
            "duration_ms": round((time.monotonic() - server_started) * 1000),
            "timeout_seconds": policy.timeout_seconds,
            "exit_code": server.returncode,
            "signal": (
                -server.returncode
                if server.returncode is not None and server.returncode < 0
                else None
            ),
            "readiness": {
                "url": readiness_url,
                "attempts": attempts,
                "status": "PASSED" if ready else "FAILED",
                "last_error": last_error,
            },
            "environment": server_environment_evidence,
            "stdout": bounded_stream(server_stdout_file.read()),
            "stderr": bounded_stream(server_stderr_file.read()),
        }
        discovery.append(server_record)

    if not ready:
        return (
            unavailable_runtime_channel(
                profile.profile_id,
                "browser",
                "DEV_SERVER_NOT_READY",
                tool_discovery=discovery,
            ),
            None,
        )
    if startup_check is None or startup_check["status"] != "PASSED":
        discovery.append(
            {"kind": "STARTUP_CHECK_EXECUTION", "execution": startup_check}
        )
        return (
            unavailable_runtime_channel(
                profile.profile_id,
                "browser",
                "DEV_SERVER_STARTUP_CHECK_FAILED",
                tool_discovery=discovery,
            ),
            None,
        )
    if (
        probe_command is None
        or probe_command["status"] != "PASSED"
        or raw_result_path is None
        or not raw_result_path.is_file()
    ):
        discovery.append(
            {"kind": "PLAYWRIGHT_PROBE_EXECUTION", "execution": probe_command}
        )
        if raw_result_path is not None and raw_result_path.is_file():
            raw_bytes = raw_result_path.read_bytes()
            try:
                raw_value = read_json(raw_result_path, "failed Playwright probe result")
                browser_statuses = [
                    {
                        "browser_id": row.get("browser_id"),
                        "status": row.get("status"),
                        "scenario_count": row.get("scenario_count"),
                        "passed_scenarios": sum(
                            scenario.get("status") == "PASSED"
                            for scenario in row.get("scenarios", [])
                            if isinstance(scenario, dict)
                        ),
                        "error": row.get("error"),
                    }
                    for row in raw_value.get("browser_runs", [])
                    if isinstance(row, dict)
                ]
            except ValidationError as error:
                browser_statuses = [{"parse_error": str(error)}]
            discovery.extend(
                [
                    {
                        "kind": "RUNTIME_EVIDENCE_ROOT",
                        "path": str(evidence_root),
                    },
                    {
                        "kind": "PLAYWRIGHT_RAW_RESULT",
                        "path": str(raw_result_path.resolve()),
                        "sha256": sha256_bytes(raw_bytes),
                        "byte_count": len(raw_bytes),
                        "browser_statuses": browser_statuses,
                    },
                ]
            )
        record = unavailable_runtime_channel(
            profile.profile_id,
            "browser",
            "PLAYWRIGHT_BROWSER_MATRIX_FAILED",
            tool_discovery=discovery,
        )
        record["build_execution"] = dict(build_command)
        record["startup_execution"] = startup_check
        record["journey_execution"] = probe_command
        return record, None

    try:
        probe = require_exact_keys(
            read_json(raw_result_path, "Playwright probe result"),
            {
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
            },
            "Playwright probe result",
        )
        if (
            probe["schema_version"] != SCHEMA_VERSION
            or probe["kind"] != "frontend-interaction-playwright-probe-result"
            or probe["profile_id"] != profile.profile_id
            or probe["project_digest"] != profile.project_digest
            or probe["proof_profile"] != INTERACTION_PROOF_PROFILE
            or probe["scenario_manifest_digest"]
            != digest_json(
                [
                    {
                        "scenario_id": item["scenario_id"],
                        "input": dict(item["input"]),
                    }
                    for item in profile.scenario_manifest
                ]
            )
            or probe["semantic_block_ids"] != list(INTERACTION_BLOCK_IDS)
            or probe["model_values_accepted_as_actual"] is not False
            or probe["external_network"] != "BLOCKED"
            or probe["status"] != "NOT_RUN"
            or probe["reason"] != BLOCK_SPECIFIC_RUNTIME_PARTIAL_REASON
        ):
            raise ValidationError("Playwright probe result identity/status drift")
        browser_runs = probe["browser_runs"]
        expected_browser_ids = [row[0] for row in browser_rows]
        if (
            not isinstance(browser_runs, list)
            or [row.get("browser_id") for row in browser_runs] != expected_browser_ids
        ):
            raise ValidationError("Playwright browser matrix is incomplete")
        for index, browser in enumerate(browser_runs):
            browser = validate_playwright_browser_run_identity(
                browser,
                expected_browser_id=browser_rows[index][0],
                expected_engine=browser_rows[index][1],
                binary_version=browser_rows[index][2],
                executable_identity=browser_rows[index][3],
                name=f"Playwright browser_runs[{index}]",
            )
            if (
                browser["status"] != "NOT_RUN"
                or browser["reason"] != BLOCK_SPECIFIC_RUNTIME_PARTIAL_REASON
            ):
                raise ValidationError("Playwright browser partial status drift")

        scenario_ids = [item["scenario_id"] for item in profile.scenario_manifest]
        by_browser: dict[str, dict[str, Mapping[str, Any]]] = {}
        for browser in browser_runs:
            scenarios = browser.get("scenarios")
            if (
                browser.get("scenario_count") != len(scenario_ids)
                or not isinstance(scenarios, list)
                or [row.get("scenario_id") for row in scenarios] != scenario_ids
            ):
                raise ValidationError("Playwright scenario closure/order drift")
            by_browser[browser["browser_id"]] = {
                row["scenario_id"]: row for row in scenarios
            }

        scenarios_output: list[dict[str, Any]] = []
        raw_artifacts: list[dict[str, Any]] = []
        source_artifacts: list[dict[str, Any]] = []
        per_block_ids = {block_id: [] for block_id in INTERACTION_BLOCK_IDS}
        declared_statuses: dict[str, str] | None = None
        declared_not_run_reasons: dict[str, str] = {}
        for scenario_id in scenario_ids:
            scenario_input = next(
                item["input"]
                for item in profile.scenario_manifest
                if item["scenario_id"] == scenario_id
            )
            browser_scenarios = [
                by_browser[browser_id][scenario_id]
                for browser_id in expected_browser_ids
            ]
            for browser_id, row in zip(expected_browser_ids, browser_scenarios):
                row = require_exact_keys(
                    row,
                    {
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
                    },
                    f"{scenario_id}.{browser_id} raw scenario",
                )
                raw_dom = row.get("raw_dom")
                checks = row.get("checks")
                runtime_metadata = require_exact_keys(
                    row["runtime_metadata"],
                    {"execution_state", "execution_sequence", "runtime_source"},
                    f"{scenario_id}.{browser_id}.runtime_metadata",
                )
                if (
                    row["status"] != "PARTIAL"
                    or row["reason"] != BLOCK_SPECIFIC_RUNTIME_PARTIAL_REASON
                    or runtime_metadata["execution_state"] != "PARTIAL"
                    or runtime_metadata["runtime_source"]
                    != BLOCK_SPECIFIC_RUNTIME_ACTUAL_SOURCE
                    or not isinstance(runtime_metadata["execution_sequence"], str)
                    or not re.fullmatch(
                        r"[1-9][0-9]*", runtime_metadata["execution_sequence"]
                    )
                    or not isinstance(raw_dom, str)
                    or not raw_dom.strip()
                    or row.get("raw_dom_sha256")
                    != sha256_bytes(raw_dom.encode("utf-8"))
                    or not isinstance(checks, dict)
                    or not checks
                    or any(value is not True for value in checks.values())
                    or not isinstance(row.get("browser_events"), list)
                    or not row["browser_events"]
                    or not isinstance(row.get("network_events"), list)
                    or not isinstance(row.get("aria_snapshot"), str)
                    or not row["aria_snapshot"].strip()
                    or not isinstance(row.get("axe"), dict)
                    or row["aria_error"] is not None
                    or row["axe_error"] is not None
                    or row["page_errors"] != []
                    or row["capture_errors"] != []
                ):
                    raise ValidationError(
                        f"{scenario_id}.{browser_id} actual trace closure is incomplete"
                    )
            primary = browser_scenarios[0]
            browser_dom_matrix = [
                {
                    "browser_id": browser_id,
                    "raw_dom": row.get("raw_dom"),
                    "raw_dom_sha256": row.get("raw_dom_sha256"),
                }
                for browser_id, row in zip(
                    expected_browser_ids, browser_scenarios
                )
            ]
            combined_events = [
                {"browser_id": browser_id, **dict(event)}
                for browser_id, row in zip(expected_browser_ids, browser_scenarios)
                for event in row.get("browser_events", [])
            ]
            combined_network = [
                {"browser_id": browser_id, **dict(event)}
                for browser_id, row in zip(expected_browser_ids, browser_scenarios)
                for event in row.get("network_events", [])
            ]
            keyboard_events = [
                dict(event) for event in combined_events if event.get("type") == "keydown"
            ]
            focus_events = [
                dict(event) for event in combined_events if event.get("type") == "focusin"
            ]
            axe_violations = [
                {"browser_id": browser_id, **dict(violation)}
                for browser_id, row in zip(expected_browser_ids, browser_scenarios)
                for violation in (row.get("axe") or {}).get("violations", [])
            ]
            trace_captures = {
                "browser-dom-snapshot": {
                    "root_selector": "#elmos-interaction",
                    "outer_html": canonical_json(browser_dom_matrix),
                },
                "browser-framework-event-trace": {"events": combined_events},
                "browser-accessibility-axe-trace": {
                    "aria_snapshot": "\n\n".join(
                        f"[{browser_id}]\n{row.get('aria_snapshot') or ''}"
                        for browser_id, row in zip(
                            expected_browser_ids, browser_scenarios
                        )
                    ),
                    "active_element": {
                        "browser_matrix": [
                            {
                                "browser_id": browser_id,
                                "value": row.get("active_element"),
                            }
                            for browser_id, row in zip(
                                expected_browser_ids, browser_scenarios
                            )
                        ]
                    },
                    "axe_results": {
                        "violations": axe_violations,
                        "browser_matrix": [
                            {
                                "browser_id": browser_id,
                                "value": row.get("axe"),
                            }
                            for browser_id, row in zip(
                                expected_browser_ids, browser_scenarios
                            )
                        ],
                    },
                    "keyboard_events": keyboard_events,
                    "focus_events": focus_events,
                },
                "browser-network-trace": {"events": combined_network},
            }
            trace_refs = {
                role: browser_trace_ref(
                    evidence_root,
                    profile_id=profile.profile_id,
                    scenario_id=scenario_id,
                    role=role,
                    capture=capture,
                )
                for role, capture in trace_captures.items()
            }
            source_artifacts.extend(trace_refs.values())
            block_refs: dict[str, dict[str, Any]] = {}
            block_statuses: dict[str, dict[str, Any]] = {}
            primary_blocks = primary.get("block_observations")
            if not isinstance(primary_blocks, dict) or tuple(primary_blocks) != (
                INTERACTION_BLOCK_IDS
            ):
                raise ValidationError(f"{scenario_id} semantic block closure drift")
            for block_id in INTERACTION_BLOCK_IDS:
                browser_block_rows = [
                    row.get("block_observations", {}).get(block_id)
                    for row in browser_scenarios
                ]
                if any(not isinstance(row, dict) for row in browser_block_rows):
                    raise ValidationError(f"{scenario_id}.{block_id} is absent")
                validated_rows = [
                    require_exact_keys(
                        raw_row,
                        {
                            "status",
                            "actual_source",
                            "observer_kind",
                            "measurement_surface",
                            "measurement",
                            "measurement_digest",
                            "model_values_used_as_actual",
                            "reason",
                        },
                        f"{scenario_id}.{block_id}.{browser_id}",
                    )
                    for browser_id, raw_row in zip(
                        expected_browser_ids, browser_block_rows
                    )
                ]
                spec = BLOCK_OBSERVER_SPECS[block_id]
                expected_contract = profile.runtime_driver_contract[
                    "block_observer_contracts"
                ][block_id]
                statuses = {row["status"] for row in validated_rows}
                reasons = {row["reason"] for row in validated_rows}
                if (
                    len(statuses) != 1
                    or statuses != {expected_contract["browser_status"]}
                    or reasons
                    != {
                        expected_contract["browser_reason"]
                        if expected_contract["browser_status"] == "NOT_RUN"
                        else None
                    }
                    or any(
                        row["observer_kind"] != spec["observer_kind"]
                        or row["measurement_surface"]
                        != spec["measurement_surface"]
                        or row["model_values_used_as_actual"] is not False
                        for row in validated_rows
                    )
                ):
                    raise ValidationError(
                        f"{scenario_id}.{block_id} browser declaration/provenance drift"
                    )
                block_status = statuses.pop()
                if block_status == "PASSED":
                    if (
                        block_id in WEB_BROWSER_MANDATORY_NOT_RUN_BLOCK_IDS
                        or any(
                            row["actual_source"]
                            != BLOCK_SPECIFIC_RUNTIME_ACTUAL_SOURCE
                            or row["reason"] is not None
                            or not isinstance(row["measurement"], dict)
                            or row["measurement_digest"]
                            != digest_json(row["measurement"])
                            for row in validated_rows
                        )
                    ):
                        raise ValidationError(
                            f"{scenario_id}.{block_id} invalid PASSED capture"
                        )
                    ref, block_trace_ref = browser_observation_ref(
                        evidence_root,
                        profile_id=profile.profile_id,
                        scenario_id=scenario_id,
                        block_id=block_id,
                        scenario_input=scenario_input,
                        browser_measurements=[
                            {
                                "browser_id": browser_id,
                                "measurement": row["measurement"],
                            }
                            for browser_id, row in zip(
                                expected_browser_ids, validated_rows
                            )
                        ],
                        trace_refs=trace_refs,
                    )
                    block_refs[block_id] = ref
                    raw_artifacts.append(ref)
                    source_artifacts.append(block_trace_ref)
                    per_block_ids[block_id].append(ref["artifact_id"])
                    block_statuses[block_id] = {"status": "PASSED", "reason": None}
                elif block_status == "NOT_RUN":
                    if (
                        len(reasons) != 1
                        or not isinstance(validated_rows[0]["reason"], str)
                        or not validated_rows[0]["reason"]
                        or any(
                            row["actual_source"] != "NOT_RUN"
                            or row["measurement"] is not None
                            or row["measurement_digest"] is not None
                            for row in validated_rows
                        )
                    ):
                        raise ValidationError(
                            f"{scenario_id}.{block_id} invalid NOT_RUN capture"
                        )
                    reason = validated_rows[0]["reason"]
                    block_statuses[block_id] = {
                        "status": "NOT_RUN",
                        "reason": reason,
                    }
                    prior_reason = declared_not_run_reasons.setdefault(
                        block_id, reason
                    )
                    if prior_reason != reason:
                        raise ValidationError(
                            f"{scenario_id}.{block_id} NOT_RUN reason drift"
                        )
                else:
                    raise ValidationError(
                        f"{scenario_id}.{block_id} raw status is invalid"
                    )
            scenario_declared_statuses = {
                block_id: block_statuses[block_id]["status"]
                for block_id in INTERACTION_BLOCK_IDS
            }
            if declared_statuses is None:
                declared_statuses = scenario_declared_statuses
            elif declared_statuses != scenario_declared_statuses:
                raise ValidationError(
                    f"{scenario_id} browser block capability status drift"
                )
            scenarios_output.append(
                {
                    "scenario_id": scenario_id,
                    "status": "NOT_RUN",
                    "reason": BLOCK_SPECIFIC_RUNTIME_PARTIAL_REASON,
                    "block_statuses": block_statuses,
                    "block_observation_refs": block_refs,
                }
            )

        if declared_statuses is None:
            raise ValidationError("Playwright block capability closure is absent")
        passed_block_ids = tuple(
            block_id
            for block_id in INTERACTION_BLOCK_IDS
            if declared_statuses[block_id] == "PASSED"
        )
        not_run_block_ids = tuple(
            block_id
            for block_id in INTERACTION_BLOCK_IDS
            if declared_statuses[block_id] == "NOT_RUN"
        )
        if not set(WEB_BROWSER_MANDATORY_NOT_RUN_BLOCK_IDS).issubset(not_run_block_ids):
            raise ValidationError("Playwright unsupported Web block was promoted")

        npm_tool = runtime_tool_identity(Path(npm_path), npm_version)
        python_tool = runtime_tool_identity(
            Path(sys.executable), platform.python_version()
        )
        node_version = command_output(
            run_command(
                ["node", "--version"],
                cwd=workspace,
                timeout_seconds=30,
                no_network=True,
                explicit_env={"CI": "1", "NO_COLOR": "1"},
            )
        )
        node_tool = runtime_tool_identity(Path(probe_command["argv"][0]), node_version)
        build_execution = runtime_execution_from_command(
            build_command, phase="BUILD", tool=npm_tool
        )
        startup_execution = runtime_execution_from_command(
            startup_check, phase="STARTUP", tool=python_tool
        )
        runtime_tools = [
            {
                "role": "playwright-driver-node",
                **node_tool,
                "package_closure_digest": implementation["closure_digest"],
            },
            *[
                {
                    "role": f"browser-{engine}",
                    **identity,
                    "package_closure_digest": implementation["closure_digest"],
                }
                for _browser_id, engine, _version, identity in browser_rows
            ],
        ]
        result_manifest_value = {
            "schema_version": SCHEMA_VERSION,
            "kind": "frontend-interaction-runtime-result-manifest",
            "profile_id": profile.profile_id,
            "channel": "browser",
            "scenario_ids": scenario_ids,
            "semantic_block_ids": list(INTERACTION_BLOCK_IDS),
            "runtime_source_artifact_ids": [
                item["artifact_id"] for item in source_artifacts
            ],
            "runtime_source_artifact_count": len(source_artifacts),
            "observation_artifact_ids": [
                item["artifact_id"] for item in raw_artifacts
            ],
            "observation_artifact_count": len(raw_artifacts),
            "passed_block_ids": list(passed_block_ids),
            "not_run_block_ids": list(not_run_block_ids),
            "runtime_tool_digests": [item["sha256"] for item in runtime_tools],
            "prerequisite_execution_ids": [
                build_execution["execution_id"],
                startup_execution["execution_id"],
            ],
        }
        manifest_relative, manifest_sha, manifest_bytes = (
            write_content_addressed_runtime_json(
                evidence_root,
                f"manifests/{profile.profile_id}/browser",
                result_manifest_value,
            )
        )
        result_manifest_ref = {
            "role": "runtime-result-manifest",
            "profile_id": profile.profile_id,
            "channel": "browser",
            "path": manifest_relative,
            "sha256": manifest_sha,
            "byte_count": manifest_bytes,
            "manifest_digest": digest_json(result_manifest_value),
        }
        result_manifest_ref["artifact_id"] = digest_json(result_manifest_ref)
        journey_refs = [
            *[item["artifact_id"] for item in source_artifacts],
            *[item["artifact_id"] for item in raw_artifacts],
            result_manifest_ref["artifact_id"],
        ]
        journey_execution = runtime_execution_from_command(
            probe_command,
            phase="JOURNEY",
            tool=node_tool,
            artifact_refs=journey_refs,
        )
        execution_policy = {
            "schema_version": SCHEMA_VERSION,
            "kind": "frontend-interaction-runtime-execution-policy",
            "profile_id": profile.profile_id,
            "channel": "browser",
            "runner_kind": "PLAYWRIGHT_BROWSER_INTERACTION",
            "phases": {
                "BUILD": runtime_phase_policy(build_execution),
                "STARTUP": runtime_phase_policy(startup_execution),
                "JOURNEY": runtime_phase_policy(journey_execution),
            },
            "runtime_tools": runtime_tools,
        }
        policy_relative, policy_sha, policy_bytes = (
            write_content_addressed_runtime_json(
                evidence_root,
                f"policies/{profile.profile_id}/browser",
                execution_policy,
            )
        )
        discovery.extend(
            [
                {
                    "kind": "RUNTIME_EVIDENCE_ROOT",
                    "path": str(evidence_root),
                },
                {
                    "kind": "PLAYWRIGHT_RAW_RESULT",
                    "path": str(raw_result_path.resolve()),
                    "sha256": sha256_bytes(raw_result_path.read_bytes()),
                    "byte_count": raw_result_path.stat().st_size,
                },
                {
                    "kind": "RUNTIME_EXECUTION_POLICY_ARTIFACT",
                    "path": policy_relative,
                    "sha256": policy_sha,
                    "byte_count": policy_bytes,
                    "policy_digest": digest_json(execution_policy),
                },
            ]
        )
        record = {
            "channel": "browser",
            "required": True,
            "status": "NOT_RUN",
            "reason": BLOCK_SPECIFIC_RUNTIME_PARTIAL_REASON,
            "runner_kind": "PLAYWRIGHT_BROWSER_INTERACTION",
            "tool_discovery": discovery,
            "execution_policy_digest": digest_json(execution_policy),
            "runtime_tools": runtime_tools,
            "build_execution": build_execution,
            "startup_execution": startup_execution,
            "journey_execution": journey_execution,
            "scenario_manifest_digest": digest_json(scenario_ids),
            "scenario_count": len(scenario_ids),
            "scenarios": scenarios_output,
            "semantic_blocks": {
                block_id: {
                    "status": declared_statuses[block_id],
                    "reason": (
                        None
                        if declared_statuses[block_id] == "PASSED"
                        else declared_not_run_reasons[block_id]
                    ),
                    "observation_refs": refs,
                    "observation_digest": digest_json(refs),
                }
                for block_id, refs in per_block_ids.items()
            },
            "raw_artifacts": raw_artifacts,
            "runtime_source_artifacts": source_artifacts,
            "result_manifest": result_manifest_ref,
            "model_values_used_as_actual": False,
        }
        return record, execution_policy
    except (KeyError, TypeError, ValidationError) as error:
        discovery.append(
            {"kind": "PLAYWRIGHT_RESULT_VALIDATION_ERROR", "error": str(error)}
        )
        record = unavailable_runtime_channel(
            profile.profile_id,
            "browser",
            "PLAYWRIGHT_ACTUAL_TRACE_CLOSURE_INVALID",
            tool_discovery=discovery,
        )
        record["build_execution"] = dict(build_command)
        record["startup_execution"] = startup_check
        record["journey_execution"] = probe_command
        return record, None


def execute_node_profile(
    profile: ProfileArtifact, workspace: Path, policy: RunnerPolicy
) -> dict[str, Any]:
    tool_versions, version_error = node_tool_versions(workspace, policy)
    commands: list[dict[str, Any]] = []
    if version_error:
        unavailable = version_error.endswith("UNAVAILABLE")
        runtime_observations = (
            interaction_runtime_inventory_observations(
                profile, workspace, policy, version_error
            )
            if profile.proof_profile == INTERACTION_PROOF_PROFILE
            else None
        )
        return profile_result(
            profile,
            "NOT_RUN" if unavailable else "FAILED",
            version_error,
            tool_versions,
            commands,
            workspace,
            policy,
            runtime_observations=runtime_observations,
        )
    npm = tool_versions[1]["argv"][0]
    empty_user_config = workspace / ".elmos-empty-npmrc"
    empty_user_config.write_text(
        "# isolated by ELMOS toolchain runner\n", encoding="utf-8"
    )
    package = read_json(workspace / "package.json", f"{profile.profile_id} package")
    npm_cache = Path(os.environ.get("npm_config_cache", Path.home() / ".npm"))
    base_npm_env = {
        "CI": "1",
        "NO_COLOR": "1",
        "npm_config_audit": "false",
        "npm_config_cache": str(npm_cache.resolve()),
        "npm_config_fetch_retries": "0",
        "npm_config_fetch_timeout": str(policy.network_timeout_seconds * 1000),
        "npm_config_fund": "false",
        "npm_config_ignore_scripts": "true",
        "npm_config_package_lock": "true",
        "npm_config_progress": "false",
        "npm_config_userconfig": str(empty_user_config),
    }
    offline_env = {**base_npm_env, "npm_config_offline": "true"}
    online_env = {**base_npm_env, "npm_config_prefer_offline": "true"}
    lock_path = workspace / "package-lock.json"
    if not lock_path.is_file():
        lock = annotate_dependency_command(
            run_command(
                [
                    npm,
                    "install",
                    "--package-lock-only",
                    "--ignore-scripts",
                    "--no-audit",
                    "--no-fund",
                    "--offline",
                ],
                cwd=workspace,
                timeout_seconds=policy.timeout_seconds,
                no_network=True,
                explicit_env=offline_env,
            ),
            purpose="GENERATE_EXACT_PACKAGE_LOCK",
            network_mode="OFFLINE_CACHE",
        )
        commands.append(lock)
        if lock["status"] != "PASSED" or not lock_path.is_file():
            if policy.no_network:
                unavailable = npm_offline_cache_miss(lock)
                return profile_result(
                    profile,
                    "NOT_RUN" if unavailable else "FAILED",
                    "OFFLINE_DEPENDENCY_LOCK_UNAVAILABLE"
                    if unavailable
                    else "PACKAGE_LOCK_FAILED",
                    tool_versions,
                    commands,
                    workspace,
                    policy,
                )
            lock = annotate_dependency_command(
                run_command(
                    [
                        npm,
                        "install",
                        "--package-lock-only",
                        "--ignore-scripts",
                        "--no-audit",
                        "--no-fund",
                    ],
                    cwd=workspace,
                    timeout_seconds=policy.network_timeout_seconds,
                    no_network=False,
                    explicit_env=online_env,
                ),
                purpose="GENERATE_EXACT_PACKAGE_LOCK",
                network_mode="BOUNDED_ONLINE_FALLBACK",
            )
            commands.append(lock)
            if lock["status"] != "PASSED" or not lock_path.is_file():
                return profile_result(
                    profile,
                    "FAILED",
                    "PACKAGE_LOCK_FAILED",
                    tool_versions,
                    commands,
                    workspace,
                    policy,
                )
    try:
        validate_node_package_lock(profile.profile_id, package, lock_path)
    except ValidationError:
        return profile_result(
            profile,
            "FAILED",
            "PACKAGE_LOCK_BINDING_INVALID",
            tool_versions,
            commands,
            workspace,
            policy,
        )

    ci = annotate_dependency_command(
        run_command(
            [
                npm,
                "ci",
                "--ignore-scripts",
                "--no-audit",
                "--no-fund",
                "--offline",
            ],
            cwd=workspace,
            timeout_seconds=policy.timeout_seconds,
            no_network=True,
            explicit_env=offline_env,
        ),
        purpose="INSTALL_EXACT_PACKAGE_LOCK",
        network_mode="OFFLINE_CACHE",
    )
    commands.append(ci)
    if ci["status"] != "PASSED":
        if policy.no_network:
            unavailable = npm_offline_cache_miss(ci)
            return profile_result(
                profile,
                "NOT_RUN" if unavailable else "FAILED",
                "OFFLINE_DEPENDENCIES_UNAVAILABLE" if unavailable else "NPM_CI_FAILED",
                tool_versions,
                commands,
                workspace,
                policy,
            )
        ci = annotate_dependency_command(
            run_command(
                [npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
                cwd=workspace,
                timeout_seconds=policy.network_timeout_seconds,
                no_network=False,
                explicit_env=online_env,
            ),
            purpose="INSTALL_EXACT_PACKAGE_LOCK",
            network_mode="BOUNDED_ONLINE_FALLBACK",
        )
        commands.append(ci)
        if ci["status"] != "PASSED":
            return profile_result(
                profile,
                "FAILED",
                "NPM_CI_FAILED",
                tool_versions,
                commands,
                workspace,
                policy,
            )
    npm_env = offline_env
    for command in EXPECTED_NODE_PACKAGES[profile.profile_id]["commands"]:
        record = run_command(
            [npm, "run", *command],
            cwd=workspace,
            timeout_seconds=policy.timeout_seconds,
            no_network=True,
            explicit_env=npm_env,
        )
        commands.append(record)
        if record["status"] != "PASSED":
            return profile_result(
                profile,
                "FAILED",
                f"NPM_{command[0].upper().replace('-', '_')}_FAILED",
                tool_versions,
                commands,
                workspace,
                policy,
                target_build_status=(
                    "FAILED" if command[0] in {"build", "export:web"} else "NOT_RUN"
                ),
            )
    if profile.proof_profile == INTERACTION_PROOF_PROFILE:
        if profile.runtime_model_oracle_findings:
            reason = "PRECOMPUTED_MODEL_ORACLE_CONSUMED_BY_RUNTIME"
            browser = unsupported_browser_journey(reason)
            runtime_observations = interaction_runtime_inventory_observations(
                profile, workspace, policy, reason
            )
            return profile_result(
                profile,
                "NOT_RUN",
                reason,
                tool_versions,
                commands,
                workspace,
                policy,
                browser_journey=browser,
                target_build_status="PASSED",
                runtime_observations=runtime_observations,
            )
        if profile.profile_id == "react-native":
            reason = "REACT_NATIVE_WEB_PLAYWRIGHT_ADAPTER_NOT_EXECUTED"
            browser = unsupported_browser_journey(reason)
            runtime_observations = interaction_runtime_inventory_observations(
                profile, workspace, policy, reason
            )
            return profile_result(
                profile,
                "NOT_RUN",
                reason,
                tool_versions,
                commands,
                workspace,
                policy,
                browser_journey=browser,
                target_build_status="PASSED",
                runtime_observations=runtime_observations,
            )
        build_command = next(
            (
                item
                for item in reversed(commands)
                if len(item.get("argv", [])) >= 3
                and item["argv"][1] == "run"
                and item["argv"][2] in {"build", "export:web"}
                and item.get("status") == "PASSED"
            ),
            None,
        )
        if build_command is None:
            reason = "PASSED_TARGET_BUILD_EXECUTION_NOT_BOUND"
            browser = unsupported_browser_journey(reason)
            runtime_observations = interaction_runtime_inventory_observations(
                profile, workspace, policy, reason
            )
            return profile_result(
                profile,
                "NOT_RUN",
                reason,
                tool_versions,
                commands,
                workspace,
                policy,
                browser_journey=browser,
                target_build_status="PASSED",
                runtime_observations=runtime_observations,
            )
        browser_record, execution_policy = execute_interaction_browser_runtime(
            profile,
            workspace,
            policy,
            npm_path=npm,
            npm_version=command_output(tool_versions[1]),
            npm_environment=npm_env,
            build_command=build_command,
        )
        reason = browser_record["reason"]
        runtime_observations = interaction_runtime_inventory_observations(
            profile, workspace, policy, reason or "PLAYWRIGHT_BROWSER_RUNTIME_PASSED"
        )
        runtime_observations["browser"] = browser_record
        browser = {
            "status": browser_record["status"],
            "reason": reason,
            "browser_version": [row["version"] for row in browser_record["runtime_tools"] if row["role"].startswith("browser-")]
            if browser_record["status"] == "PASSED"
            else None,
            "server": None,
            "probes": [],
        }
        return profile_result(
            profile,
            "PASSED" if browser_record["status"] == "PASSED" else "NOT_RUN",
            reason,
            tool_versions,
            commands,
            workspace,
            policy,
            browser_journey=browser,
            target_build_status="PASSED",
            runtime_observations=runtime_observations,
            runtime_validation_context=(
                {
                    "browser": (
                        policy.runtime_evidence_root,
                        execution_policy,
                    )
                }
                if (
                    browser_record["status"] == "PASSED"
                    or is_block_specific_runtime_partial(browser_record)
                )
                and policy.runtime_evidence_root is not None
                and execution_policy is not None
                else None
            ),
        )
    if profile.profile_id == "angular":
        server_argv = [
            npm,
            "run",
            "start",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            "{port}",
        ]
    elif profile.profile_id == "react-native":
        server_argv = [npm, "run", "web", "--", "--port", "{port}"]
    else:
        server_argv = [
            npm,
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            "{port}",
            "--strictPort",
        ]
    if profile.profile_id == "react-native":
        browser = unsupported_browser_journey("REACT_NATIVE_WEB_OBSERVER_UNSUPPORTED")
    else:
        browser = execute_browser_journey(
            profile,
            workspace,
            policy,
            server_argv,
            {
                **npm_env,
                "BROWSER": "none",
                "EXPO_NO_DOCTOR": "1",
            },
        )
    return profile_result(
        profile,
        browser["status"],
        browser["reason"],
        tool_versions,
        commands,
        workspace,
        policy,
        browser_journey=browser,
        target_build_status="PASSED",
    )


def execute_flutter_browser_runtime(
    profile: ProfileArtifact,
    workspace: Path,
    policy: RunnerPolicy,
    *,
    flutter_version: str,
    build_command: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Run Flutter's supported Chrome drive/semantics matrix fail-closed."""

    if policy.runtime_evidence_root is None:
        return (
            unavailable_runtime_channel(
                "flutter", "browser", "RUNTIME_EVIDENCE_ROOT_NOT_CONFIGURED"
            ),
            None,
        )
    evidence_root = policy.runtime_evidence_root
    free_bytes = shutil.disk_usage(workspace).free
    discovery: list[dict[str, Any]] = [
        {
            "kind": "DISK_CAPACITY_PREFLIGHT",
            "available_bytes": free_bytes,
            "minimum_bytes": 1024**3,
            "status": "PASSED" if free_bytes >= 1024**3 else "FAILED",
        }
    ]
    if free_bytes < 1024**3:
        return (
            unavailable_runtime_channel(
                "flutter",
                "browser",
                "FLUTTER_DRIVE_MINIMUM_DISK_CAPACITY_UNAVAILABLE",
                tool_discovery=discovery,
            ),
            None,
        )
    if (
        not policy.flutter_chrome_path
        or not policy.flutter_chromedriver_path
        or policy.flutter_cft_acquisition_record is None
    ):
        return (
            unavailable_runtime_channel(
                "flutter",
                "browser",
                "FLUTTER_CFT_EXACT_PAIR_NOT_CONFIGURED",
                tool_discovery=discovery,
            ),
            None,
        )
    chrome_path = Path(policy.flutter_chrome_path)
    driver_path = Path(policy.flutter_chromedriver_path)
    try:
        acquisition = validate_flutter_cft_acquisition_record(
            policy.flutter_cft_acquisition_record,
            chrome_path=chrome_path,
            chromedriver_path=driver_path,
        )
        chrome_version_execution = run_command(
            [str(chrome_path), "--version"],
            cwd=workspace,
            timeout_seconds=min(policy.timeout_seconds, 30),
            no_network=True,
            explicit_env={"CI": "1", "NO_COLOR": "1"},
        )
        driver_version_execution = run_command(
            [str(driver_path), "--version"],
            cwd=workspace,
            timeout_seconds=min(policy.timeout_seconds, 30),
            no_network=True,
            explicit_env={"CI": "1", "NO_COLOR": "1"},
        )
        discovery.extend(
            [
                {
                    "kind": "FLUTTER_CFT_CHROME_VERSION_EXECUTION",
                    "execution": chrome_version_execution,
                },
                {
                    "kind": "FLUTTER_CFT_DRIVER_VERSION_EXECUTION",
                    "execution": driver_version_execution,
                },
            ]
        )
        chrome_version = command_output(chrome_version_execution)
        driver_version = command_output(driver_version_execution)
        if (
            chrome_version_execution["status"] != "PASSED"
            or driver_version_execution["status"] != "PASSED"
            or chrome_version
            != f"Google Chrome for Testing {LOCKED_FLUTTER_WEB_CFT_VERSION}"
            or not driver_version.startswith(
                f"ChromeDriver {LOCKED_FLUTTER_WEB_CFT_VERSION} "
            )
        ):
            raise ValidationError("Flutter CFT exact version commands drifted")
        chrome_identity = runtime_tool_identity(chrome_path, chrome_version)
        driver_identity = runtime_tool_identity(driver_path, driver_version)
        flutter_identity = runtime_tool_identity(
            Path(policy.flutter_path), flutter_version
        )
        python_identity = runtime_tool_identity(
            Path(sys.executable), platform.python_version()
        )
        integration_identity = file_identity(
            workspace / "integration_test/elmos_bounded_interaction_test.dart",
            "Flutter integration test source",
        )
        driver_source_identity = file_identity(
            workspace / "test_driver/integration_test.dart",
            "Flutter integration driver source",
        )
        closure = {
            "runner_sha256": policy.producer_digest,
            "project_digest": profile.project_digest,
            "acquisition_evidence_digest": acquisition["evidence_digest"],
            "chrome_app_bundle_digest": acquisition["app_bundle_digest"],
            "integration_test_sha256": integration_identity["sha256"],
            "integration_driver_sha256": driver_source_identity["sha256"],
        }
        closure_digest = digest_json(closure)
        acquisition_relative, acquisition_sha, acquisition_bytes = (
            write_content_addressed_runtime_json(
                evidence_root,
                "inputs/flutter/browser/cft-acquisition",
                acquisition["record"],
            )
        )
        discovery.append(
            {
                "kind": "FLUTTER_CFT_ACQUISITION_EVIDENCE",
                "path": acquisition_relative,
                "sha256": acquisition_sha,
                "byte_count": acquisition_bytes,
                "evidence_digest": acquisition["evidence_digest"],
                "app_bundle_digest": acquisition["app_bundle_digest"],
            }
        )
        discovery.append(
            {
                "kind": "EXACT_BROWSER_MATRIX",
                "policy_id": "flutter-web-cft-chrome-drive-v1",
                "browser_matrix": [
                    {
                        "browser_id": "cft-chrome",
                        "engine": "chromium",
                        "version": LOCKED_FLUTTER_WEB_CFT_VERSION,
                        "executable_sha256": chrome_identity["sha256"],
                        "driver_version": LOCKED_FLUTTER_WEB_CFT_VERSION,
                        "driver_sha256": driver_identity["sha256"],
                    }
                ],
                "cross_browser": False,
                "capability_scope": "flutter-web-chrome-drive-only",
            }
        )
        profile_manifest_digest = interaction_profile_manifest_digest(profile)
        if profile.scenario_manifest_digest is None:
            raise ValidationError("Flutter scenario manifest digest is absent")
    except (OSError, RuntimeError, ValidationError) as error:
        discovery.append(
            {"kind": "FLUTTER_CFT_IDENTITY_ERROR", "error": str(error)}
        )
        return (
            unavailable_runtime_channel(
                "flutter",
                "browser",
                "FLUTTER_CFT_EXACT_PAIR_IDENTITY_INVALID",
                tool_discovery=discovery,
            ),
            None,
        )

    port = available_loopback_port()
    raw_config = {
        "schema_version": SCHEMA_VERSION,
        "kind": "flutter-drive-semantics-runtime-config",
        "profile_id": "flutter",
        "channel": "browser",
        "project_digest": profile.project_digest,
        "profile_manifest_digest": profile_manifest_digest,
        "scenario_manifest_digest": profile.scenario_manifest_digest,
        "scenario_ids": [item["scenario_id"] for item in profile.scenario_manifest],
        "semantic_block_ids": list(INTERACTION_BLOCK_IDS),
        "flutter_sha256": flutter_identity["sha256"],
        "chrome_sha256": chrome_identity["sha256"],
        "chromedriver_sha256": driver_identity["sha256"],
        "chromedriver_port": port,
        "runtime_implementation_closure": closure,
    }
    config_relative, config_sha, _config_bytes = write_content_addressed_runtime_json(
        evidence_root,
        "inputs/flutter/browser/drive-config",
        raw_config,
    )
    raw_path = evidence_root / (
        "raw/flutter/browser/"
        f"flutter-drive-{config_sha.removeprefix('sha256:')}.json"
    )
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_path.exists() or raw_path.is_symlink():
        return (
            unavailable_runtime_channel(
                "flutter",
                "browser",
                "FLUTTER_DRIVE_RAW_RESULT_PATH_COLLISION",
                tool_discovery=discovery,
            ),
            None,
        )
    driver_argv = [
        driver_identity["realpath"],
        f"--port={port}",
        "--allowed-ips=127.0.0.1",
        "--silent",
    ]
    driver_environment, driver_environment_evidence = process_environment(
        True, {"CI": "1", "NO_COLOR": "1"}
    )
    driver_started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    driver_started = time.monotonic()
    ready = False
    attempts = 0
    last_error: str | None = None
    startup_check: dict[str, Any] | None = None
    journey_command: dict[str, Any] | None = None
    driver_process: subprocess.Popen[bytes] | None = None
    with (
        tempfile.TemporaryFile() as driver_stdout,
        tempfile.TemporaryFile() as driver_stderr,
    ):
        try:
            driver_process = subprocess.Popen(
                driver_argv,
                cwd=workspace,
                env=driver_environment,
                stdout=driver_stdout,
                stderr=driver_stderr,
                start_new_session=True,
            )
            opener = build_opener(ProxyHandler({}))
            status_url = f"http://127.0.0.1:{port}/status"
            deadline = time.monotonic() + min(policy.timeout_seconds, 30)
            while time.monotonic() < deadline:
                attempts += 1
                if driver_process.poll() is not None:
                    last_error = f"chromedriver exited with {driver_process.returncode}"
                    break
                try:
                    with opener.open(status_url, timeout=1) as response:
                        status_value = json.loads(response.read().decode("utf-8"))
                    if (
                        200 <= response.status < 400
                        and status_value.get("value", {}).get("ready") is True
                    ):
                        ready = True
                        break
                except (
                    HTTPError,
                    URLError,
                    TimeoutError,
                    OSError,
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                ) as error:
                    last_error = f"{type(error).__name__}: {error}"
                time.sleep(0.1)
            if ready:
                startup_script = (
                    "import json,sys,urllib.request;"
                    "o=urllib.request.build_opener(urllib.request.ProxyHandler({}));"
                    "r=o.open(sys.argv[1],timeout=5);v=json.loads(r.read());"
                    "print(json.dumps(v,sort_keys=True,separators=(',',':')));"
                    "raise SystemExit(0 if v.get('value',{}).get('ready') is True else 1)"
                )
                startup_check = run_command(
                    [
                        str(Path(sys.executable).resolve()),
                        "-c",
                        startup_script,
                        status_url,
                    ],
                    cwd=workspace,
                    timeout_seconds=min(policy.timeout_seconds, 30),
                    no_network=True,
                    explicit_env={"CI": "1", "NO_COLOR": "1"},
                )
            if startup_check is not None and startup_check["status"] == "PASSED":
                before_drive_free = shutil.disk_usage(workspace).free
                discovery.append(
                    {
                        "kind": "FLUTTER_DRIVE_DISK_CAPACITY",
                        "available_bytes": before_drive_free,
                        "minimum_bytes": 1024**3,
                        "status": (
                            "PASSED" if before_drive_free >= 1024**3 else "FAILED"
                        ),
                    }
                )
                if before_drive_free < 1024**3:
                    last_error = "minimum disk capacity unavailable before drive"
                else:
                    drive_env = {
                        "CI": "1",
                        "FLUTTER_SUPPRESS_ANALYTICS": "true",
                        "NO_COLOR": "1",
                        "ELMOS_FLUTTER_TRACE_PATH": str(raw_path.resolve()),
                        "ELMOS_FLUTTER_RUNTIME_CHANNEL": "browser",
                        "ELMOS_FLUTTER_PROJECT_DIGEST": profile.project_digest,
                        "ELMOS_FLUTTER_PROFILE_MANIFEST_DIGEST": (
                            profile_manifest_digest
                        ),
                        "ELMOS_FLUTTER_SCENARIO_MANIFEST_DIGEST": (
                            profile.scenario_manifest_digest
                        ),
                    }
                    journey_command = run_command(
                        [
                            policy.flutter_path,
                            "drive",
                            "--driver=test_driver/integration_test.dart",
                            "--target=integration_test/elmos_bounded_interaction_test.dart",
                            "-d",
                            "chrome",
                            "--browser-name=chrome",
                            f"--chrome-binary={chrome_identity['realpath']}",
                            f"--driver-port={port}",
                            "--headless",
                            "--no-pub",
                            "--no-dds",
                            "--no-web-resources-cdn",
                            f"--timeout={policy.timeout_seconds}",
                        ],
                        cwd=workspace,
                        timeout_seconds=policy.timeout_seconds,
                        no_network=True,
                        explicit_env=drive_env,
                    )
        except (OSError, RuntimeError, ValidationError) as error:
            last_error = str(error)
        finally:
            if driver_process is not None:
                terminate_process_group(driver_process)
        driver_stdout.seek(0)
        driver_stderr.seek(0)
        driver_lifecycle = {
            "kind": "CHROMEDRIVER_LIFECYCLE",
            "argv": driver_argv,
            "cwd": str(workspace.resolve()),
            "started_at": driver_started_at,
            "duration_ms": round((time.monotonic() - driver_started) * 1000),
            "timeout_seconds": policy.timeout_seconds,
            "exit_code": (
                driver_process.returncode if driver_process is not None else None
            ),
            "signal": (
                -driver_process.returncode
                if driver_process is not None
                and driver_process.returncode is not None
                and driver_process.returncode < 0
                else None
            ),
            "readiness": {
                "url": f"http://127.0.0.1:{port}/status",
                "attempts": attempts,
                "status": "PASSED" if ready else "FAILED",
                "last_error": last_error,
            },
            "environment": driver_environment_evidence,
            "stdout": bounded_stream(driver_stdout.read()),
            "stderr": bounded_stream(driver_stderr.read()),
        }
        discovery.append(driver_lifecycle)

    if startup_check is None or startup_check["status"] != "PASSED":
        record = unavailable_runtime_channel(
            "flutter",
            "browser",
            "FLUTTER_CHROMEDRIVER_STARTUP_FAILED",
            tool_discovery=discovery,
        )
        record["build_execution"] = dict(build_command)
        record["startup_execution"] = startup_check
        return record, None
    raw_discovery: dict[str, Any] | None = None
    if raw_path.is_file():
        raw_bytes = raw_path.read_bytes()
        raw_discovery = {
            "kind": "FLUTTER_DRIVE_RAW_RESULT",
            "path": str(raw_path.resolve()),
            "sha256": sha256_bytes(raw_bytes),
            "byte_count": len(raw_bytes),
        }
        discovery.append(raw_discovery)
    if journey_command is None or journey_command["status"] != "PASSED" or raw_discovery is None:
        discovery.append(
            {"kind": "FLUTTER_DRIVE_EXECUTION", "execution": journey_command}
        )
        record = unavailable_runtime_channel(
            "flutter",
            "browser",
            "FLUTTER_DRIVE_SEMANTICS_EXECUTION_FAILED",
            tool_discovery=discovery,
        )
        record["build_execution"] = dict(build_command)
        record["startup_execution"] = startup_check
        record["journey_execution"] = journey_command
        return record, None

    try:
        validated = validate_flutter_drive_raw_trace(
            profile,
            raw_path,
            profile_manifest_digest=profile_manifest_digest,
        )
        discovery.append(
            {
                "kind": "FLUTTER_BLOCK_SPECIFIC_RUNTIME_OBSERVER_STATUS",
                "status": "NOT_RUN",
                "reason": "FLUTTER_BLOCK_SPECIFIC_RUNTIME_OBSERVER_NOT_IMPLEMENTED",
                "validated_raw_trace_sha256": raw_discovery["sha256"],
                "validated_scenario_count": len(validated["scenarios"]),
                "runtime_actuals_emitted": False,
                "runtime_observation_refs_emitted": False,
            }
        )
        record = unavailable_runtime_channel(
            "flutter",
            "browser",
            "FLUTTER_BLOCK_SPECIFIC_RUNTIME_OBSERVER_NOT_IMPLEMENTED",
            tool_discovery=discovery,
        )
        record["build_execution"] = dict(build_command)
        record["startup_execution"] = startup_check
        record["journey_execution"] = journey_command
        return record, None
    except (KeyError, OSError, TypeError, ValidationError) as error:
        discovery.append(
            {"kind": "FLUTTER_DRIVE_RESULT_VALIDATION_ERROR", "error": str(error)}
        )
        record = unavailable_runtime_channel(
            "flutter",
            "browser",
            "FLUTTER_DRIVE_ACTUAL_TRACE_CLOSURE_INVALID",
            tool_discovery=discovery,
        )
        record["build_execution"] = dict(build_command)
        record["startup_execution"] = startup_check
        record["journey_execution"] = journey_command
        return record, None


def execute_flutter_profile(
    profile: ProfileArtifact, workspace: Path, policy: RunnerPolicy
) -> dict[str, Any]:
    version = run_command(
        [policy.flutter_path, "--version", "--machine"],
        cwd=workspace,
        timeout_seconds=policy.timeout_seconds,
        no_network=policy.no_network,
        explicit_env={"CI": "1", "FLUTTER_SUPPRESS_ANALYTICS": "true", "NO_COLOR": "1"},
    )
    tool_versions = [version]
    if version["status"] == "TOOL_UNAVAILABLE":
        runtime_observations = (
            interaction_runtime_inventory_observations(
                profile, workspace, policy, "FLUTTER_TOOLCHAIN_UNAVAILABLE"
            )
            if profile.proof_profile == INTERACTION_PROOF_PROFILE
            else None
        )
        return profile_result(
            profile,
            "NOT_RUN",
            "FLUTTER_TOOLCHAIN_UNAVAILABLE",
            tool_versions,
            [],
            workspace,
            policy,
            runtime_observations=runtime_observations,
        )
    if version["status"] != "PASSED":
        return profile_result(
            profile,
            "FAILED",
            "FLUTTER_VERSION_COMMAND_FAILED",
            tool_versions,
            [],
            workspace,
            policy,
        )
    try:
        identity = json.loads(version["stdout"]["text"])
    except json.JSONDecodeError:
        identity = None
    resolved_flutter = Path(version["argv"][0]).resolve()
    if (
        not isinstance(identity, dict)
        or identity.get("frameworkVersion") != "3.44.1"
        or identity.get("dartSdkVersion") != "3.12.1"
        or not str(resolved_flutter).startswith("/opt/homebrew/")
    ):
        return profile_result(
            profile,
            "FAILED",
            "FLUTTER_OR_BUNDLED_DART_VERSION_DRIFT",
            tool_versions,
            [],
            workspace,
            policy,
        )
    flutter_env = {"CI": "1", "FLUTTER_SUPPRESS_ANALYTICS": "true", "NO_COLOR": "1"}
    commands: list[dict[str, Any]] = []
    pub = run_command(
        [
            policy.flutter_path,
            "pub",
            "get",
            *(["--offline"] if policy.no_network else []),
        ],
        cwd=workspace,
        timeout_seconds=policy.timeout_seconds,
        no_network=policy.no_network,
        explicit_env=flutter_env,
    )
    commands.append(pub)
    if pub["status"] != "PASSED":
        unavailable = policy.no_network
        return profile_result(
            profile,
            "NOT_RUN" if unavailable else "FAILED",
            "OFFLINE_FLUTTER_DEPENDENCIES_UNAVAILABLE"
            if unavailable
            else "FLUTTER_PUB_GET_FAILED",
            tool_versions,
            commands,
            workspace,
            policy,
        )
    for args, reason in (
        (["analyze", "--no-pub"], "FLUTTER_ANALYZE_FAILED"),
        (
            ["test", "--no-pub", "--no-dds", "--concurrency=1"],
            "FLUTTER_TEST_FAILED",
        ),
        (["build", "web", "--no-pub"], "FLUTTER_WEB_BUILD_FAILED"),
    ):
        record = run_command(
            [policy.flutter_path, *args],
            cwd=workspace,
            timeout_seconds=policy.timeout_seconds,
            no_network=policy.no_network,
            explicit_env=flutter_env,
        )
        commands.append(record)
        if record["status"] != "PASSED":
            return profile_result(
                profile,
                "FAILED",
                reason,
                tool_versions,
                commands,
                workspace,
                policy,
                target_build_status="FAILED" if args[0] == "build" else "NOT_RUN",
            )
    if profile.proof_profile == INTERACTION_PROOF_PROFILE:
        if profile.runtime_model_oracle_findings:
            reason = "PRECOMPUTED_MODEL_ORACLE_CONSUMED_BY_RUNTIME"
            return profile_result(
                profile,
                "NOT_RUN",
                reason,
                tool_versions,
                commands,
                workspace,
                policy,
                browser_journey=unsupported_browser_journey(reason),
                target_build_status="PASSED",
                runtime_observations=interaction_runtime_inventory_observations(
                    profile, workspace, policy, reason
                ),
            )
        browser_record, execution_policy = execute_flutter_browser_runtime(
            profile,
            workspace,
            policy,
            flutter_version=(
                f"{identity['frameworkVersion']} (Dart {identity['dartSdkVersion']})"
            ),
            build_command=commands[-1],
        )
        browser_reason = browser_record["reason"]
        reason = (
            "FLUTTER_ANDROID_IOS_DEVICE_RUNTIME_NOT_EXECUTED"
            if browser_record["status"] == "PASSED"
            else browser_reason
        )
        runtime_observations = interaction_runtime_inventory_observations(
            profile,
            workspace,
            policy,
            reason or "FLUTTER_RUNTIME_CHANNEL_NOT_EXECUTED",
        )
        runtime_observations["browser"] = browser_record
        browser_journey = {
            "status": browser_record["status"],
            "reason": browser_reason,
            "browser_version": (
                LOCKED_FLUTTER_WEB_CFT_VERSION
                if browser_record["status"] == "PASSED"
                else None
            ),
            "server": None,
            "probes": [],
        }
        return profile_result(
            profile,
            "NOT_RUN",
            reason,
            tool_versions,
            commands,
            workspace,
            policy,
            browser_journey=browser_journey,
            target_build_status="PASSED",
            runtime_observations=runtime_observations,
            runtime_validation_context=(
                {
                    "browser": (
                        policy.runtime_evidence_root,
                        execution_policy,
                    )
                }
                if (
                    browser_record["status"] == "PASSED"
                    or is_block_specific_runtime_partial(browser_record)
                )
                and policy.runtime_evidence_root is not None
                and execution_policy is not None
                else None
            ),
        )
    browser = unsupported_browser_journey("FLUTTER_WEB_SEMANTICS_OBSERVER_UNSUPPORTED")
    return profile_result(
        profile,
        browser["status"],
        browser["reason"],
        tool_versions,
        commands,
        workspace,
        policy,
        browser_journey=browser,
        target_build_status="PASSED",
    )


def execute_harmony_profile(
    profile: ProfileArtifact, workspace: Path, policy: RunnerPolicy
) -> dict[str, Any]:
    discovery, selected_tool = discover_hvigor_candidates(
        workspace, policy.harmony_tool
    )
    if selected_tool is None:
        unavailable = skipped_command(
            [policy.harmony_tool or "hvigorw", "--version"],
            workspace,
            "EXECUTABLE_NOT_FOUND",
        )
        runtime_observations = (
            interaction_runtime_inventory_observations(
                profile,
                workspace,
                policy,
                "DEVECO_HVIGOR_TOOLCHAIN_UNAVAILABLE",
            )
            if profile.proof_profile == INTERACTION_PROOF_PROFILE
            else None
        )
        return profile_result(
            profile,
            "NOT_RUN",
            "DEVECO_HVIGOR_TOOLCHAIN_UNAVAILABLE",
            [unavailable],
            [],
            workspace,
            policy,
            tool_discovery=discovery,
            runtime_observations=runtime_observations,
        )
    tool = selected_tool
    version = run_command(
        [tool, "--version"],
        cwd=workspace,
        timeout_seconds=policy.timeout_seconds,
        no_network=policy.no_network,
        explicit_env={"CI": "1", "NO_COLOR": "1"},
    )
    if version["status"] == "TOOL_UNAVAILABLE":
        return profile_result(
            profile,
            "NOT_RUN",
            "DEVECO_HVIGOR_TOOLCHAIN_UNAVAILABLE",
            [version],
            [],
            workspace,
            policy,
            tool_discovery=discovery,
        )
    if version["status"] != "PASSED":
        return profile_result(
            profile,
            "FAILED",
            "HVIGOR_VERSION_COMMAND_FAILED",
            [version],
            [],
            workspace,
            policy,
            tool_discovery=discovery,
        )
    version_text = f"{version['stdout']['text']}\n{version['stderr']['text']}"
    if not any(
        marker in version_text for marker in ("harmonyos-6.0.0-api20", "6.0.0(20)")
    ):
        return profile_result(
            profile,
            "FAILED",
            "HVIGOR_SDK_VERSION_DRIFT",
            [version],
            [],
            workspace,
            policy,
            tool_discovery=discovery,
        )
    commands: list[dict[str, Any]] = []
    for args, reason in (
        (["clean", "--no-daemon"], "HVIGOR_CLEAN_FAILED"),
        (
            [
                "assembleHap",
                "--mode",
                "module",
                "-p",
                "module=entry@default",
                "-p",
                "buildMode=debug",
                "--no-daemon",
            ],
            "HVIGOR_BUILD_FAILED",
        ),
    ):
        record = run_command(
            [tool, *args],
            cwd=workspace,
            timeout_seconds=policy.timeout_seconds,
            no_network=policy.no_network,
            explicit_env={"CI": "1", "NO_COLOR": "1"},
        )
        commands.append(record)
        if record["status"] != "PASSED":
            return profile_result(
                profile,
                "FAILED",
                reason,
                [version],
                commands,
                workspace,
                policy,
                tool_discovery=discovery,
                target_build_status=(
                    "FAILED" if args[0] == "assembleHap" else "NOT_RUN"
                ),
            )
    if profile.proof_profile == INTERACTION_PROOF_PROFILE:
        reason = (
            "PRECOMPUTED_MODEL_ORACLE_CONSUMED_BY_RUNTIME"
            if profile.runtime_model_oracle_findings
            else "HARMONYOS_DEVICE_INTERACTION_RUNTIME_NOT_EXECUTED"
        )
        return profile_result(
            profile,
            "NOT_RUN",
            reason,
            [version],
            commands,
            workspace,
            policy,
            tool_discovery=discovery,
            target_build_status="PASSED",
            runtime_observations=interaction_runtime_inventory_observations(
                profile, workspace, policy, reason
            ),
        )
    return profile_result(
        profile,
        "PASSED",
        None,
        [version],
        commands,
        workspace,
        policy,
        tool_discovery=discovery,
    )


def discover_hvigor_candidates(
    workspace: Path, configured: str | None
) -> tuple[list[dict[str, Any]], str | None]:
    raw_candidates: list[tuple[str, Path]] = []
    if configured:
        raw_candidates.append(("CLI_CONFIGURED", Path(configured)))
    raw_candidates.append(("PROJECT_WRAPPER", workspace / "hvigorw"))
    for command in ("hvigorw", "hvigor"):
        resolved = shutil.which(command)
        if resolved:
            raw_candidates.append(("PATH", Path(resolved)))
    for application in ("DevEco-Studio.app", "DevEco Studio.app"):
        raw_candidates.append(
            (
                "DEVECO_STANDARD_LOCATION",
                Path("/Applications")
                / application
                / "Contents/tools/hvigor/bin/hvigorw",
            )
        )
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    selected: str | None = None
    for source, candidate in raw_candidates:
        absolute = candidate if candidate.is_absolute() else workspace / candidate
        key = str(absolute)
        if key in seen:
            continue
        seen.add(key)
        exists = absolute.is_file()
        executable = exists and os.access(absolute, os.X_OK)
        row: dict[str, Any] = {
            "source": source,
            "candidate_path": key,
            "exists": exists,
            "executable": executable,
            "selected": False,
            "realpath": None,
            "sha256": None,
            "byte_count": None,
        }
        if exists:
            data = absolute.read_bytes()
            row.update(
                {
                    "realpath": str(absolute.resolve()),
                    "sha256": sha256_bytes(data),
                    "byte_count": len(data),
                }
            )
        if executable and selected is None:
            selected = str(absolute.resolve())
            row["selected"] = True
        rows.append(row)
    return rows, selected


def profile_result(
    profile: ProfileArtifact,
    status: str,
    reason: str | None,
    tool_versions: Sequence[dict[str, Any]],
    commands: Sequence[dict[str, Any]],
    workspace: Path,
    policy: RunnerPolicy,
    browser_journey: Mapping[str, Any] | None = None,
    target_build_status: str | None = None,
    tool_discovery: Sequence[dict[str, Any]] = (),
    runtime_observations: Mapping[str, Mapping[str, Any]] | None = None,
    runtime_validation_context: Mapping[
        str, tuple[Path, Mapping[str, Any]]
    ] | None = None,
) -> dict[str, Any]:
    lock_name = (
        "pubspec.lock" if profile.profile_id == "flutter" else "package-lock.json"
    )
    lock_path = workspace / lock_name
    lock_artifact = None
    if lock_path.is_file():
        data = lock_path.read_bytes()
        lock_artifact = {
            "path": lock_name,
            "sha256": sha256_bytes(data),
            "byte_count": len(data),
        }
    if profile.profile_id == "flutter":
        build_root = workspace / "build/web"
    elif profile.profile_id == "harmony-arkui":
        build_root = workspace / "entry/build"
    else:
        build_root = workspace / "dist"
    build = tree_digest(build_root)
    if browser_journey is None:
        browser_journey = {
            "status": "NOT_RUN",
            "reason": "TARGET_BUILD_NOT_PASSED",
            "browser_version": None,
            "server": None,
            "probes": [],
        }
    if target_build_status is None:
        target_build_status = "PASSED" if status == "PASSED" else "NOT_RUN"
    if runtime_observations is None:
        runtime_observations = (
            interaction_runtime_inventory_observations(
                profile,
                workspace,
                policy,
                reason or "INTERACTION_RUNTIME_NOT_EXECUTED",
            )
            if profile.proof_profile == INTERACTION_PROOF_PROFILE
            else unavailable_runtime_observations(
                profile, "LEGACY_NAVIGATION_RUNTIME_CHANNEL_NOT_EVALUATED"
            )
        )
    runtime_records: dict[str, dict[str, Any]] = {}
    scenario_ids = [item["scenario_id"] for item in profile.scenario_manifest]
    runtime_validation_context = runtime_validation_context or {}
    for channel in RUNTIME_CHANNELS:
        raw_record = runtime_observations.get(channel)
        if not isinstance(raw_record, Mapping):
            raise ValidationError(
                f"{profile.profile_id}.{channel} runtime evidence is absent"
            )
        context = runtime_validation_context.get(channel)
        runtime_records[channel] = validate_runtime_channel_record(
            profile.profile_id,
            channel,
            raw_record,
            scenario_ids=scenario_ids,
            scenario_manifest=profile.scenario_manifest,
            runtime_model_oracle_findings=profile.runtime_model_oracle_findings,
            evidence_root=context[0] if context is not None else None,
            execution_policy=context[1] if context is not None else None,
        )
    evidence_core = {
        "producer": {
            "path": policy.producer_path,
            "sha256": policy.producer_digest,
            "byte_count": policy.producer_byte_count,
        },
        "profile_id": profile.profile_id,
        "project_digest": profile.project_digest,
        "status": status,
        "reason": reason,
        "target_build": target_build_status,
        "tool_versions": list(tool_versions),
        "tool_discovery": list(tool_discovery),
        "commands": list(commands),
        "browser_journey": dict(browser_journey),
        "required_runtime_channels": list(
            required_runtime_channels(profile.profile_id)
        ),
        "runtime_model_oracle_findings": [
            dict(item) for item in profile.runtime_model_oracle_findings
        ],
        "runtime_observations": runtime_records,
        "artifacts": {"dependency_lock": lock_artifact, "build_output": build},
        "boundaries": {
            "model_execution": "NOT_RUN",
            "browser_journey": browser_journey["status"],
            "device_or_simulator_journey": "NOT_RUN",
            "holdout_journey": "NOT_RUN",
            "representative_customer_journey": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "model_execution_counts_as_browser_or_device": False,
        },
    }
    execution_id = digest_json(evidence_core)
    return {
        "execution_id": execution_id,
        **evidence_core,
        "replay_profile_args": [
            "--profile",
            profile.profile_id,
            *(["--no-network"] if policy.no_network else []),
            "--timeout-seconds",
            str(policy.timeout_seconds),
            "--network-timeout-seconds",
            str(policy.network_timeout_seconds),
            *(["--fail-on-unavailable"] if policy.fail_on_unavailable else []),
        ],
    }


def execute_campaign(campaign: LoadedCampaign, policy: RunnerPolicy) -> dict[str, Any]:
    producer_bytes = RUNNER_PATH.read_bytes()
    actual_producer_digest = sha256_bytes(producer_bytes)
    if (
        Path(policy.producer_path).resolve() != RUNNER_PATH
        or policy.producer_digest != actual_producer_digest
        or policy.producer_byte_count != len(producer_bytes)
    ):
        raise ValidationError("runner producer identity changed before execution")
    replayed_campaign = load_campaign(campaign.path)
    if replayed_campaign.digest != campaign.digest:
        raise ValidationError("campaign changed after validation")
    campaign = replayed_campaign
    implementation_closure = (
        playwright_implementation_closure()
        if campaign.proof_profile == INTERACTION_PROOF_PROFILE
        else None
    )
    profile_results: dict[str, dict[str, Any]] = {}
    digest_results: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(
        prefix="elmos-frontend-formal-toolchains-"
    ) as temporary:
        workspace_root = Path(temporary)
        for profile_id in sorted(campaign.profiles):
            profile = campaign.profiles[profile_id]
            if profile_id not in policy.selected_profiles:
                runtime_observations = unavailable_runtime_observations(
                    profile, "PROFILE_NOT_SELECTED"
                )
                result = {
                    "execution_id": digest_json(
                        {
                            "producer_digest": policy.producer_digest,
                            "profile_id": profile_id,
                            "project_digest": profile.project_digest,
                            "status": "NOT_RUN",
                        }
                    ),
                    "producer": {
                        "path": policy.producer_path,
                        "sha256": policy.producer_digest,
                        "byte_count": policy.producer_byte_count,
                    },
                    "profile_id": profile_id,
                    "project_digest": profile.project_digest,
                    "status": "NOT_RUN",
                    "reason": "PROFILE_NOT_SELECTED",
                    "target_build": "NOT_RUN",
                    "tool_versions": [],
                    "commands": [],
                    "browser_journey": {
                        "status": "NOT_RUN",
                        "reason": "PROFILE_NOT_SELECTED",
                        "browser_version": None,
                        "server": None,
                        "probes": [],
                    },
                    "required_runtime_channels": list(
                        required_runtime_channels(profile_id)
                    ),
                    "runtime_model_oracle_findings": [
                        dict(item) for item in profile.runtime_model_oracle_findings
                    ],
                    "runtime_observations": runtime_observations,
                    "artifacts": {"dependency_lock": None, "build_output": None},
                    "boundaries": {
                        "model_execution": "NOT_RUN",
                        "browser_journey": "NOT_RUN",
                        "device_or_simulator_journey": "NOT_RUN",
                        "holdout_journey": "NOT_RUN",
                        "representative_customer_journey": "NOT_RUN",
                        "independent_verification": "NOT_RUN",
                        "certification": "NOT_CERTIFIED",
                        "model_execution_counts_as_browser_or_device": False,
                    },
                    "replay_profile_args": ["--profile", profile_id],
                }
                profile_results[profile_id] = result
                continue
            existing = digest_results.get(profile.project_digest)
            if existing is not None:
                if existing["profile_id"] != profile_id:
                    raise ValidationError(
                        "one project digest is bound to multiple exact profiles"
                    )
                profile_results[profile_id] = existing
                continue
            # A profile workspace can contain gigabytes of dependencies.  Its
            # evidence is fully materialized into `result` before this exact
            # temporary directory is reclaimed; campaign/source files are never
            # deletion targets.
            with tempfile.TemporaryDirectory(
                prefix=f"{profile_id}-", dir=workspace_root
            ) as profile_temporary:
                workspace = Path(profile_temporary) / "project"
                shutil.copytree(profile.project_path, workspace, symlinks=False)
                kind = EXPECTED_PROFILES[profile_id]["kind"]
                if kind == "node":
                    result = execute_node_profile(profile, workspace, policy)
                elif kind == "flutter":
                    result = execute_flutter_profile(profile, workspace, policy)
                else:
                    result = execute_harmony_profile(profile, workspace, policy)
            digest_results[profile.project_digest] = result
            profile_results[profile_id] = result

    route_records = []
    for route in sorted(campaign.routes, key=lambda item: item["route_id"]):
        source = profile_results[route["source_profile"]]
        target = profile_results[route["target_profile"]]
        if "FAILED" in {source["status"], target["status"]}:
            status = "FAILED"
        elif "NOT_RUN" in {source["status"], target["status"]}:
            status = "NOT_RUN"
        else:
            status = "PASSED"
        record = {
            "route_id": route["route_id"],
            "source_profile": route["source_profile"],
            "target_profile": route["target_profile"],
            "source_project_digest": route["source_project_digest"],
            "target_project_digest": route["target_project_digest"],
            "source_execution_id": source["execution_id"],
            "target_execution_id": target["execution_id"],
            "source_toolchain_status": source["status"],
            "target_toolchain_status": target["status"],
            "source_browser_status": source["browser_journey"]["status"],
            "target_browser_status": target["browser_journey"]["status"],
            "status": status,
            "formal_route_status": route["status"],
            "browser_evidence": (
                "PASSED"
                if source["browser_journey"]["status"] == "PASSED"
                and target["browser_journey"]["status"] == "PASSED"
                else "NOT_RUN"
            ),
            "device_or_simulator_evidence": "NOT_RUN",
            "holdout_evidence": "NOT_RUN",
            "representative_customer_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
        if campaign.proof_profile == INTERACTION_PROOF_PROFILE:
            block_runtime: dict[str, Any] = {}
            for block_id in INTERACTION_BLOCK_IDS:
                channel_rows: dict[str, Any] = {}
                for channel in RUNTIME_CHANNELS:
                    source_channel = source["runtime_observations"][channel]
                    target_channel = target["runtime_observations"][channel]
                    source_block = source_channel["semantic_blocks"][block_id]
                    target_block = target_channel["semantic_blocks"][block_id]
                    if "FAILED" in {
                        source_block["status"],
                        target_block["status"],
                    }:
                        equivalence = "FAILED"
                    elif (
                        source_block["status"] == "PASSED"
                        and target_block["status"] == "PASSED"
                    ):
                        equivalence = (
                            "PASSED"
                            if source_block["observation_digest"]
                            == target_block["observation_digest"]
                            else "FAILED"
                        )
                    elif (
                        source_block["status"] == "NOT_APPLICABLE"
                        and target_block["status"] == "NOT_APPLICABLE"
                    ):
                        equivalence = "NOT_APPLICABLE"
                    else:
                        equivalence = "NOT_RUN"
                    channel_rows[channel] = {
                        "source_status": source_block["status"],
                        "source_observation_digest": source_block["observation_digest"],
                        "target_status": target_block["status"],
                        "target_observation_digest": target_block["observation_digest"],
                        "equivalence_status": equivalence,
                    }
                block_runtime[block_id] = {
                    "channels": channel_rows,
                    "cross_channel_equivalence": "NOT_RUN",
                    "independent_status": "NOT_RUN",
                }
            record.update(
                {
                    "formal_evidence": route["runner_proof_replay"],
                    "source_required_runtime_channels": source[
                        "required_runtime_channels"
                    ],
                    "target_required_runtime_channels": target[
                        "required_runtime_channels"
                    ],
                    "runtime_blocks": block_runtime,
                    "cross_channel_equivalence": "NOT_RUN",
                    "runtime_ready": False,
                    "independent_runtime_verification": "NOT_RUN",
                }
            )
        route_records.append(record)
    values = list(profile_results.values())
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "kind": (
            INTERACTION_OUTPUT_KIND
            if campaign.proof_profile == INTERACTION_PROOF_PROFILE
            else OUTPUT_KIND
        ),
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "producer": {
            "path": policy.producer_path,
            "sha256": policy.producer_digest,
            "byte_count": policy.producer_byte_count,
        },
        "campaign": {
            "path": str(campaign.path),
            "sha256": campaign.digest,
            "byte_count": campaign.byte_count,
            "proof_profile": campaign.proof_profile,
            "profile_count": len(campaign.profiles),
            "route_count": len(campaign.routes),
        },
        "engine_preverification": (
            dict(campaign.engine_verifier_evidence)
            if campaign.engine_verifier_evidence is not None
            else None
        ),
        "implementation_closure": implementation_closure,
        "semantic_block_ids": list(campaign.semantic_block_ids),
        "scenario_manifest_digest": campaign.scenario_manifest_digest,
        "scenario_policy": (
            {
                "version": LOCKED_INTERACTION_SCENARIO_POLICY_VERSION,
                "source_sha256": LOCKED_INTERACTION_SCENARIO_SOURCE_SHA256,
                "source_byte_count": LOCKED_INTERACTION_SCENARIO_SOURCE_BYTE_COUNT,
                "scenario_ids": list(LOCKED_INTERACTION_SCENARIO_IDS),
            }
            if campaign.proof_profile == INTERACTION_PROOF_PROFILE
            else None
        ),
        "mutation_replay": [dict(item) for item in campaign.mutation_replay],
        "policy": {
            "no_network": policy.no_network,
            "timeout_seconds": policy.timeout_seconds,
            "network_timeout_seconds": policy.network_timeout_seconds,
            "chrome_path": policy.chrome_path,
            "firefox_path": policy.firefox_path,
            "android_device_id": policy.android_device_id,
            "ios_simulator_udid": policy.ios_simulator_udid,
            "harmony_device_id": policy.harmony_device_id,
            "selected_profiles": sorted(policy.selected_profiles),
            "fail_on_unavailable": policy.fail_on_unavailable,
            "profile_build_deduplication": "project-content-digest",
            "workspace_retention": "PER_PROFILE_TEMPORARY_RECLAIMED_AFTER_EVIDENCE_CAPTURE",
        },
        "profile_executions": [profile_results[key] for key in sorted(profile_results)],
        "route_records": route_records,
        "summary": {
            "profile_status_counts": {
                state: sum(item["status"] == state for item in values)
                for state in ("PASSED", "FAILED", "NOT_RUN")
            },
            "route_status_counts": {
                state: sum(item["status"] == state for item in route_records)
                for state in ("PASSED", "FAILED", "NOT_RUN")
            },
            "browser_journeys_passed": sum(
                item["browser_journey"]["status"] == "PASSED" for item in values
            ),
            "device_or_simulator_journeys_passed": 0,
            "holdout_corpus": "NOT_RUN",
            "representative_customer_corpus": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
    }
    identity_core = {
        "producer": evidence["producer"],
        "implementation_closure": evidence["implementation_closure"],
        "engine_preverification_digest": (
            evidence["engine_preverification"]["evidence_digest"]
            if evidence["engine_preverification"] is not None
            else None
        ),
        "campaign_sha256": campaign.digest,
        "proof_profile": campaign.proof_profile,
        "semantic_block_ids": evidence["semantic_block_ids"],
        "scenario_manifest_digest": evidence["scenario_manifest_digest"],
        "scenario_policy": evidence["scenario_policy"],
        "mutation_replay_digest": digest_json(evidence["mutation_replay"]),
        "policy": evidence["policy"],
        "profile_execution_ids": [
            item["execution_id"] for item in evidence["profile_executions"]
        ],
        "route_execution_bindings": [
            {
                "route_id": item["route_id"],
                "source_execution_id": item["source_execution_id"],
                "target_execution_id": item["target_execution_id"],
                "status": item["status"],
                **(
                    {"formal_replay_digest": item["formal_evidence"]["replay_digest"]}
                    if "formal_evidence" in item
                    else {}
                ),
            }
            for item in evidence["route_records"]
        ],
    }
    evidence["evidence_identity"] = {
        "algorithm": "sha256(canonical-json(identity_payload))",
        "identity_payload": identity_core,
        "sha256": digest_json(identity_core),
        "scope": "producer+engine-preverification+implementation+campaign+scenario+policy+profile-executions+route-bindings",
    }
    validate_emitted_evidence(evidence, require_replay=False)
    return evidence


def validate_emitted_evidence(
    evidence: Mapping[str, Any], *, require_replay: bool
) -> None:
    """Independently reconstruct output summaries and all top-level identities."""

    producer = require_exact_keys(
        evidence.get("producer"),
        {"path", "sha256", "byte_count"},
        "emitted producer",
    )
    producer_path = Path(producer["path"])
    try:
        producer_bytes = producer_path.resolve(strict=True).read_bytes()
    except (OSError, RuntimeError) as error:
        raise ValidationError(
            f"emitted producer cannot be resolved: {error}"
        ) from error
    if (
        producer_path.resolve() != RUNNER_PATH
        or producer["sha256"] != sha256_bytes(producer_bytes)
        or producer["byte_count"] != len(producer_bytes)
    ):
        raise ValidationError("emitted producer identity mismatch")

    campaign = require_exact_keys(
        evidence.get("campaign"),
        {
            "path",
            "sha256",
            "byte_count",
            "proof_profile",
            "profile_count",
            "route_count",
        },
        "emitted campaign",
    )
    campaign_path = Path(campaign["path"])
    try:
        campaign_bytes = campaign_path.resolve(strict=True).read_bytes()
    except (OSError, RuntimeError) as error:
        raise ValidationError(
            f"emitted campaign cannot be resolved: {error}"
        ) from error
    if (
        campaign["sha256"] != sha256_bytes(campaign_bytes)
        or campaign["byte_count"] != len(campaign_bytes)
        or campaign["profile_count"] != len(EXPECTED_PROFILES)
        or campaign["route_count"] != 72
    ):
        raise ValidationError("emitted campaign identity/count mismatch")

    profiles = evidence.get("profile_executions")
    routes = evidence.get("route_records")
    if not isinstance(profiles, list) or not isinstance(routes, list):
        raise ValidationError("emitted profile/route records must be arrays")
    profile_by_id: dict[str, Mapping[str, Any]] = {}
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValidationError("emitted profile execution is not an object")
        profile_id = profile.get("profile_id")
        if profile_id not in EXPECTED_PROFILES or profile_id in profile_by_id:
            raise ValidationError("emitted profile execution identity is invalid")
        if profile.get("status") not in {"PASSED", "FAILED", "NOT_RUN"}:
            raise ValidationError(f"{profile_id} emitted profile status is invalid")
        profile_by_id[profile_id] = profile
    if set(profile_by_id) != set(EXPECTED_PROFILES):
        raise ValidationError("emitted profile matrix is incomplete")

    expected_pairs = {
        (source, target)
        for source in EXPECTED_PROFILES
        for target in EXPECTED_PROFILES
        if source != target
    }
    seen_pairs: set[tuple[str, str]] = set()
    seen_route_ids: set[str] = set()
    for route in routes:
        if not isinstance(route, dict):
            raise ValidationError("emitted route record is not an object")
        source_id = route.get("source_profile")
        target_id = route.get("target_profile")
        pair = (source_id, target_id)
        route_id = route.get("route_id")
        if (
            pair not in expected_pairs
            or pair in seen_pairs
            or route_id in seen_route_ids
            or route_id != f"{source_id}--to--{target_id}"
        ):
            raise ValidationError("emitted route matrix identity is invalid")
        source = profile_by_id[source_id]
        target = profile_by_id[target_id]
        expected_status = (
            "FAILED"
            if "FAILED" in {source["status"], target["status"]}
            else (
                "NOT_RUN"
                if "NOT_RUN" in {source["status"], target["status"]}
                else "PASSED"
            )
        )
        if (
            route.get("source_execution_id") != source.get("execution_id")
            or route.get("target_execution_id") != target.get("execution_id")
            or route.get("source_toolchain_status") != source.get("status")
            or route.get("target_toolchain_status") != target.get("status")
            or route.get("status") != expected_status
        ):
            raise ValidationError(
                f"{route_id} emitted execution/status binding mismatch"
            )
        if campaign["proof_profile"] == INTERACTION_PROOF_PROFILE:
            formal = route.get("formal_evidence")
            if (
                not isinstance(formal, dict)
                or formal.get("artifact_closure") != "PASSED"
                or formal.get("formal_solver", {})
                .get("runner_replay", {})
                .get("status")
                != "PASSED"
                or formal.get("vacuity_solver", {})
                .get("runner_replay", {})
                .get("status")
                != "PASSED"
                or require_sha256(
                    formal.get("replay_digest"), f"{route_id}.formal replay digest"
                )
                != digest_json(
                    {
                        "formal": formal["formal_solver"]["runner_replay"],
                        "vacuity": formal["vacuity_solver"]["runner_replay"],
                    }
                )
            ):
                raise ValidationError(
                    f"{route_id} emitted formal replay closure mismatch"
                )
        seen_pairs.add(pair)
        seen_route_ids.add(route_id)
    if seen_pairs != expected_pairs or len(routes) != 72:
        raise ValidationError("emitted route matrix is incomplete")

    profile_counts = {
        status: sum(profile["status"] == status for profile in profiles)
        for status in ("PASSED", "FAILED", "NOT_RUN")
    }
    route_counts = {
        status: sum(route["status"] == status for route in routes)
        for status in ("PASSED", "FAILED", "NOT_RUN")
    }
    expected_summary = {
        "profile_status_counts": profile_counts,
        "route_status_counts": route_counts,
        "browser_journeys_passed": sum(
            profile.get("browser_journey", {}).get("status") == "PASSED"
            for profile in profiles
        ),
        "device_or_simulator_journeys_passed": 0,
        "holdout_corpus": "NOT_RUN",
        "representative_customer_corpus": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }
    if evidence.get("summary") != expected_summary:
        raise ValidationError(
            "emitted summary does not match final profile/route records"
        )

    engine_preverification = evidence.get("engine_preverification")
    if campaign["proof_profile"] == INTERACTION_PROOF_PROFILE:
        if not isinstance(engine_preverification, dict):
            raise ValidationError(
                "emitted interaction engine preverification is absent"
            )
        preverification_core = dict(engine_preverification)
        preverification_digest = require_sha256(
            preverification_core.pop("evidence_digest", None),
            "emitted engine preverification digest",
        )
        if (
            preverification_digest != digest_json(preverification_core)
            or engine_preverification.get("status") != "PASSED"
            or engine_preverification.get("result", {}).get("valid") is not True
            or engine_preverification.get("result", {}).get("errors") != []
        ):
            raise ValidationError("emitted engine preverification closure mismatch")
        mutations = evidence.get("mutation_replay")
        if (
            not isinstance(mutations, list)
            or len(mutations) != len(INTERACTION_BLOCK_IDS) * 3
            or any(
                row.get("runner_replay", {}).get("status") != "PASSED"
                for row in mutations
                if isinstance(row, dict)
            )
            or any(not isinstance(row, dict) for row in mutations)
        ):
            raise ValidationError("emitted mutation replay closure mismatch")
    elif engine_preverification is not None:
        raise ValidationError(
            "navigation output cannot claim interaction preverification"
        )

    expected_identity_payload = {
        "producer": producer,
        "implementation_closure": evidence.get("implementation_closure"),
        "engine_preverification_digest": (
            engine_preverification["evidence_digest"]
            if engine_preverification is not None
            else None
        ),
        "campaign_sha256": campaign["sha256"],
        "proof_profile": campaign["proof_profile"],
        "semantic_block_ids": evidence.get("semantic_block_ids"),
        "scenario_manifest_digest": evidence.get("scenario_manifest_digest"),
        "scenario_policy": evidence.get("scenario_policy"),
        "mutation_replay_digest": digest_json(evidence.get("mutation_replay")),
        "policy": evidence.get("policy"),
        "profile_execution_ids": [profile["execution_id"] for profile in profiles],
        "route_execution_bindings": [
            {
                "route_id": route["route_id"],
                "source_execution_id": route["source_execution_id"],
                "target_execution_id": route["target_execution_id"],
                "status": route["status"],
                **(
                    {"formal_replay_digest": route["formal_evidence"]["replay_digest"]}
                    if "formal_evidence" in route
                    else {}
                ),
            }
            for route in routes
        ],
    }
    identity = require_exact_keys(
        evidence.get("evidence_identity"),
        {"algorithm", "identity_payload", "sha256", "scope"},
        "emitted evidence identity",
    )
    if (
        identity["algorithm"] != "sha256(canonical-json(identity_payload))"
        or identity["identity_payload"] != expected_identity_payload
        or identity["sha256"] != digest_json(expected_identity_payload)
        or identity["scope"]
        != "producer+engine-preverification+implementation+campaign+scenario+policy+profile-executions+route-bindings"
    ):
        raise ValidationError("emitted evidence identity mismatch")

    replay = evidence.get("replay")
    if require_replay:
        if not isinstance(replay, dict):
            raise ValidationError("emitted replay binding is absent")
        if (
            replay.get("producer") != producer
            or replay.get("campaign_sha256") != campaign["sha256"]
            or replay.get("campaign_byte_count") != campaign["byte_count"]
            or replay.get("replay_execution") != "NOT_RUN"
            or replay.get("portable_pack_replay") != "NOT_RUN"
            or not isinstance(replay.get("argv"), list)
            or len(replay["argv"]) < 3
            or replay["argv"][1] != str(RUNNER_PATH)
            or replay["argv"][2] != str(campaign_path.resolve())
        ):
            raise ValidationError("emitted replay producer/campaign binding mismatch")
    elif replay is not None:
        raise ValidationError("unexpected replay binding before final output assembly")


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> str:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return sha256_bytes(data)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("campaign", type=Path)
    value.add_argument("--output", type=Path)
    value.add_argument("--profile", action="append", choices=sorted(EXPECTED_PROFILES))
    value.add_argument("--no-network", action="store_true")
    value.add_argument("--timeout-seconds", type=int, default=900)
    value.add_argument("--network-timeout-seconds", type=int, default=0)
    value.add_argument("--fail-on-unavailable", action="store_true")
    value.add_argument(
        "--chrome-path",
        default=DEFAULT_CHROME_PATH,
    )
    value.add_argument("--firefox-path", default=DEFAULT_FIREFOX_PATH)
    value.add_argument("--flutter-chrome-path")
    value.add_argument("--flutter-chromedriver-path")
    value.add_argument("--flutter-cft-acquisition-record", type=Path)
    value.add_argument("--harmony-tool")
    value.add_argument("--android-device-id")
    value.add_argument("--ios-simulator-udid")
    value.add_argument("--harmony-device-id")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.timeout_seconds < 1 or arguments.timeout_seconds > 3600:
        parser().error("--timeout-seconds must be between 1 and 3600")
    if arguments.network_timeout_seconds and (
        arguments.network_timeout_seconds < 1
        or arguments.network_timeout_seconds > arguments.timeout_seconds
    ):
        parser().error(
            "--network-timeout-seconds must be between 1 and --timeout-seconds"
        )
    output = arguments.output or arguments.campaign.with_name(
        "frontend-formal-toolchain-evidence.json"
    )
    try:
        campaign = load_campaign(arguments.campaign)
        selected = frozenset(arguments.profile or EXPECTED_PROFILES)
        policy = RunnerPolicy(
            no_network=arguments.no_network,
            timeout_seconds=arguments.timeout_seconds,
            selected_profiles=selected,
            fail_on_unavailable=arguments.fail_on_unavailable,
            network_timeout_seconds=arguments.network_timeout_seconds,
            chrome_path=arguments.chrome_path,
            firefox_path=arguments.firefox_path,
            flutter_chrome_path=arguments.flutter_chrome_path,
            flutter_chromedriver_path=arguments.flutter_chromedriver_path,
            flutter_cft_acquisition_record=arguments.flutter_cft_acquisition_record,
            harmony_tool=arguments.harmony_tool,
            android_device_id=arguments.android_device_id,
            ios_simulator_udid=arguments.ios_simulator_udid,
            harmony_device_id=arguments.harmony_device_id,
            runtime_evidence_root=output.with_name(
                output.stem + "-runtime-evidence"
            ),
        )
        evidence = execute_campaign(campaign, policy)
        replay_argv = [
            str(Path(sys.executable).resolve()),
            str(RUNNER_PATH),
            str(campaign.path),
            "--output",
            str(output.resolve()),
            *(
                argument
                for profile_id in sorted(selected)
                for argument in ("--profile", profile_id)
            ),
            *(["--no-network"] if policy.no_network else []),
            "--timeout-seconds",
            str(policy.timeout_seconds),
            "--network-timeout-seconds",
            str(policy.network_timeout_seconds),
            "--chrome-path",
            policy.chrome_path,
            "--firefox-path",
            policy.firefox_path,
            *(
                ["--flutter-chrome-path", policy.flutter_chrome_path]
                if policy.flutter_chrome_path
                else []
            ),
            *(
                ["--flutter-chromedriver-path", policy.flutter_chromedriver_path]
                if policy.flutter_chromedriver_path
                else []
            ),
            *(
                [
                    "--flutter-cft-acquisition-record",
                    str(policy.flutter_cft_acquisition_record),
                ]
                if policy.flutter_cft_acquisition_record
                else []
            ),
            *(["--fail-on-unavailable"] if policy.fail_on_unavailable else []),
            *(["--harmony-tool", policy.harmony_tool] if policy.harmony_tool else []),
            *(
                ["--android-device-id", policy.android_device_id]
                if policy.android_device_id
                else []
            ),
            *(
                ["--ios-simulator-udid", policy.ios_simulator_udid]
                if policy.ios_simulator_udid
                else []
            ),
            *(
                ["--harmony-device-id", policy.harmony_device_id]
                if policy.harmony_device_id
                else []
            ),
        ]
        evidence["replay"] = {
            "argv": replay_argv,
            "cwd": str(REPOSITORY_ROOT),
            "campaign_sha256": campaign.digest,
            "campaign_byte_count": campaign.byte_count,
            "producer": {
                "path": policy.producer_path,
                "sha256": policy.producer_digest,
                "byte_count": policy.producer_byte_count,
            },
            "python_version": platform.python_version(),
            "expected_output_path": str(output.resolve()),
            "scope": "LOCAL_ABSOLUTE_PATH_REEXECUTION",
            "replay_execution": "NOT_RUN",
            "portable_pack_replay": "NOT_RUN",
            "environment": {
                "inherits_only_per_command_allowlist": True,
                "network_allowed": not policy.no_network,
            },
        }
        validate_emitted_evidence(evidence, require_replay=True)
        output_digest = atomic_write_json(output, evidence)
    except ValidationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    failed = evidence["summary"]["profile_status_counts"]["FAILED"]
    unavailable = sum(
        item["status"] == "NOT_RUN" and item["reason"] != "PROFILE_NOT_SELECTED"
        for item in evidence["profile_executions"]
    )
    print(
        json.dumps(
            {
                "output": str(output.resolve()),
                "sha256": output_digest,
                "profiles": evidence["summary"]["profile_status_counts"],
                "routes": evidence["summary"]["route_status_counts"],
                "certification": "NOT_CERTIFIED",
            },
            sort_keys=True,
        )
    )
    if failed or (policy.fail_on_unavailable and unavailable):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

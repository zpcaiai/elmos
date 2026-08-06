#!/usr/bin/env python3
"""Generate and preflight the fail-closed FRT external qualification plan.

This module prepares executable, content-addressed test cases for every external
qualification boundary.  It never upgrades external evidence, authorizes a
production operation, or executes repository-selected commands.  The only
subprocess used by preflight is the checked-in browser runtime probe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from external_campaign_parameters import CHECK_KEYS as CAMPAIGN_PARAMETER_CHECKS


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "client-packs" / "frt-g01-g30-platform"
PROFILE = PACK / "acceptance" / "external-evidence-profile.json"
QUALITY_MATRIX = PACK / "acceptance" / "quality-matrix.json"
INSTALLED_MANIFEST = ROOT / "docs" / "frt-g01-g30" / "installed-manifest.json"
DEFAULT_PLAN = PACK / "acceptance" / "external-qualification-plan.json"
DEFAULT_PREFLIGHT = PACK / "certification" / "external-qualification-preflight.json"
DEFAULT_LOCAL_EXECUTION = PACK / "certification" / "external-qualification-local-execution.json"
BROWSER_PROBE = ROOT / "scripts" / "frt" / "probe_browser_runtimes.mjs"
AT_TEMPLATE = PACK / "acceptance" / "assistive-technology-session.template.json"
DEVICE_CANDIDATE = PACK / "certification" / "local-device-inventory-candidate.json"
APPROVED_VISUAL_ROOT = PACK / "visual-baselines" / "approved"
HOLDOUT_ROOT = PACK / "corpus" / "holdout"
VISUAL_POLICY = PACK / "visual-baselines" / "policy.json"
BASELINE_MANIFEST = PACK / "baselines" / "manifest.json"
ROUTE_TOOLCHAIN_EVIDENCE = PACK / "certification" / "route-toolchain-evidence.json"

PLAN_ROOT_KEYS = {
    "schema_version",
    "plan_id",
    "pack_key",
    "profile_ref",
    "quality_matrix_ref",
    "package_manifest_sha256",
    "source_tree_sha256",
    "case_count",
    "cases",
    "boundaries",
}
CASE_KEYS = {
    "case_id",
    "title",
    "category",
    "external_check_id",
    "adapter_id",
    "execution_authority",
    "exact_target",
    "required_tools",
    "required_environment",
    "local_assertions",
    "required_evidence_roles",
    "required_metrics",
    "required_claims",
    "external_state",
    "production_operation_authorized",
    "certification",
}
PREFLIGHT_ROOT_KEYS = {
    "schema_version",
    "kind",
    "generated_at",
    "plan_sha256",
    "plan_file_ref",
    "case_count",
    "tools",
    "cases",
    "external_state_counts",
    "production_operation_authorized",
    "production_certification",
    "note",
}
PREFLIGHT_TOOL_KEYS = {
    "browser_runtimes",
    "arkui_hvigor",
    "approved_visual_baselines",
    "assistive_technology",
    "physical_devices",
    "customer_repositories",
    "independent_holdout",
    "external_runner",
    "production",
}
PREFLIGHT_CASE_KEYS = {
    "case_id",
    "adapter_id",
    "harness_state",
    "blockers",
    "external_state",
    "production_operation_authorized",
    "certification",
}
PREFLIGHT_TOOL_FIELD_KEYS = {
    "arkui_hvigor": {"available", "source"},
    "approved_visual_baselines": {"count", "approval_required"},
    "assistive_technology": {"template_present", "template_only", "session_executed"},
    "physical_devices": {"candidate_present", "candidate_count", "manual_acceptance_executed"},
    "customer_repositories": {"root_configured", "authorized_campaign_executed"},
    "independent_holdout": {"non_placeholder_file_count", "independence_attested"},
    "external_runner": {"configured"},
    "production": {"observation_authorized", "customer_acceptance_executed"},
}
BROWSER_RUNTIME_KEYS = {
    "name",
    "executable_present",
    "executable_sha256",
    "launch_attempted",
    "launch_available",
    "detected_version",
    "reason",
}
LOCAL_EXECUTION_ROOT_KEYS = {
    "schema_version",
    "kind",
    "generated_at",
    "plan_sha256",
    "preflight_sha256",
    "case_count",
    "cases",
    "code_contract_counts",
    "local_execution_counts",
    "external_state_counts",
    "production_operation_authorized",
    "production_certification",
    "note",
}
LOCAL_EXECUTION_CASE_KEYS = {
    "case_id",
    "adapter_id",
    "code_contract_state",
    "local_execution_state",
    "observations",
    "blockers",
    "external_state",
    "production_operation_authorized",
    "certification",
}
OBSERVATION_KEYS = {"observation_id", "state", "detail"}


CASE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "case_id": "FRT-EXT-001-FIREFOX-DESKTOP",
        "title": "Firefox desktop P0 browser journey",
        "category": "BROWSER",
        "external_check_id": "device_matrix",
        "adapter_id": "PLAYWRIGHT_FIREFOX_DESKTOP",
        "execution_authority": "LOCAL_EXACT_TOOLCHAIN",
        "exact_target": {"browser": "Firefox 151.0", "viewport": "1440x900", "locale": "zh-CN"},
        "required_tools": ["playwright@1.61.1", "firefox@151.0"],
        "required_environment": ["exact Playwright Firefox runtime"],
        "local_assertions": ["P0 journeys", "keyboard and focus", "Axe", "responsive overflow", "console and network"],
    },
    {
        "case_id": "FRT-EXT-002-WEBKIT-DESKTOP",
        "title": "WebKit desktop P0 browser journey",
        "category": "BROWSER",
        "external_check_id": "device_matrix",
        "adapter_id": "PLAYWRIGHT_WEBKIT_DESKTOP",
        "execution_authority": "LOCAL_EXACT_TOOLCHAIN",
        "exact_target": {"browser": "WebKit 26.5", "viewport": "1440x900", "locale": "zh-CN"},
        "required_tools": ["playwright@1.61.1", "webkit@26.5"],
        "required_environment": ["exact Playwright WebKit runtime"],
        "local_assertions": ["P0 journeys", "keyboard and focus", "Axe", "responsive overflow", "console and network"],
    },
    {
        "case_id": "FRT-EXT-003-WEBKIT-IPHONE15",
        "title": "WebKit iPhone 15 emulation P0 journey",
        "category": "BROWSER",
        "external_check_id": "device_matrix",
        "adapter_id": "PLAYWRIGHT_WEBKIT_IPHONE15",
        "execution_authority": "LOCAL_EXACT_TOOLCHAIN",
        "exact_target": {"browser": "WebKit 26.5", "device": "iPhone 15", "viewport": "393x852", "locale": "zh-CN"},
        "required_tools": ["playwright@1.61.1", "webkit@26.5"],
        "required_environment": ["exact Playwright WebKit runtime"],
        "local_assertions": ["touch viewport", "P0 journeys", "Axe", "responsive overflow", "console and network"],
    },
    {
        "case_id": "FRT-EXT-004-ARKUI-HVIGOR",
        "title": "ArkUI native hvigor target build",
        "category": "TOOLCHAIN",
        "external_check_id": "real_source_target_builds",
        "adapter_id": "ARKUI_HVIGOR_BUILD",
        "execution_authority": "LOCAL_EXACT_TOOLCHAIN",
        "exact_target": {"platform": "HarmonyOS ArkUI", "build": "hvigor assembleHap", "profile": "entry@default"},
        "required_tools": ["DevEco Studio", "hvigor or hvigorw"],
        "required_environment": ["ELMOS_HVIGORW or PATH hvigor", "exact HarmonyOS SDK"],
        "local_assertions": ["generated project integrity", "native build", "artifact digest", "typed gap preservation"],
    },
    {
        "case_id": "FRT-EXT-005-INDEPENDENT-VISUAL",
        "title": "Independent approved visual baseline comparison",
        "category": "VISUAL",
        "external_check_id": "device_matrix",
        "adapter_id": "INDEPENDENT_VISUAL_BASELINE",
        "execution_authority": "INDEPENDENT_HUMAN_AND_RUNNER",
        "exact_target": {"route": "/frontend", "update_mode": "NONE", "max_diff_pixels": 0, "pixel_threshold": 0},
        "required_tools": ["playwright@1.61.1", "approved immutable baseline store"],
        "required_environment": ["baseline approved before comparison", "independent visual reviewer"],
        "local_assertions": ["candidate stored outside approved root", "no masks", "no tolerance widening", "semantic checks paired"],
    },
    {
        "case_id": "FRT-EXT-006-MANUAL-ASSISTIVE-TECHNOLOGY",
        "title": "Independent manual assistive-technology sessions",
        "category": "ASSISTIVE_TECHNOLOGY",
        "external_check_id": "device_matrix",
        "adapter_id": "MANUAL_ASSISTIVE_TECHNOLOGY",
        "execution_authority": "INDEPENDENT_HUMAN",
        "exact_target": {"profiles": ["VoiceOver+Safari/WebKit", "NVDA+Firefox", "JAWS+Chrome"], "standard": "WCAG 2.2 AA"},
        "required_tools": ["exact OS", "exact assistive technology", "exact browser"],
        "required_environment": ["trained human operator", "signed session transcript"],
        "local_assertions": ["reading order", "labels and descriptions", "errors", "live announcements", "zoom", "reduced motion"],
    },
    {
        "case_id": "FRT-EXT-007-PHYSICAL-DEVICE-ACCEPTANCE",
        "title": "Physical-device manual P0 acceptance",
        "category": "PHYSICAL_DEVICE",
        "external_check_id": "device_matrix",
        "adapter_id": "PHYSICAL_DEVICE_ACCEPTANCE",
        "execution_authority": "INDEPENDENT_HUMAN_AND_RUNNER",
        "exact_target": {"matrix": "signed external device inventory", "journeys": "acceptance profile P0"},
        "required_tools": ["physical iOS or Android device", "authorized install and launch tooling"],
        "required_environment": ["privacy-minimized inventory", "manual P0 operator", "cleanup authority"],
        "local_assertions": ["physical reality", "install and launch", "P0 journeys", "privacy", "cleanup receipt"],
    },
    {
        "case_id": "FRT-EXT-008-REAL-CUSTOMER-REPOSITORIES",
        "title": "Real customer source and target repository campaign",
        "category": "CUSTOMER_REPOSITORY",
        "external_check_id": "real_source_target_builds",
        "adapter_id": "REAL_CUSTOMER_REPOSITORY_CAMPAIGN",
        "execution_authority": "AUTHORIZED_EXTERNAL_RUNNER",
        "exact_target": {"repositories": "exact commits", "routes": "exact declared tuples", "data_policy": "minimized"},
        "required_tools": ["authorized external runner", "real source and target toolchains"],
        "required_environment": ["customer authorization", "exact commit digests", "DLP-approved evidence root"],
        "local_assertions": ["source build", "target build", "target startup", "route equivalence", "cleanup receipt"],
    },
    {
        "case_id": "FRT-EXT-009-INDEPENDENT-HOLDOUT",
        "title": "Physically independent holdout campaign",
        "category": "HOLDOUT",
        "external_check_id": "independent_holdout",
        "adapter_id": "INDEPENDENT_HOLDOUT_CAMPAIGN",
        "execution_authority": "AUTHORIZED_EXTERNAL_RUNNER",
        "exact_target": {"corpus": "physically separate", "development_overlap": 0, "unexplained_differences": 0},
        "required_tools": ["authorized external runner", "independent corpus store"],
        "required_environment": ["corpus not used for implementation", "independent executor"],
        "local_assertions": ["corpus digest", "zero development overlap", "equivalence", "difference register", "cleanup receipt"],
    },
    {
        "case_id": "FRT-EXT-010-BOUNDED-FORMAL-PROOF",
        "title": "Bounded formal proof and counterexample replay",
        "category": "FORMAL_PROOF",
        "external_check_id": "formal_proof",
        "adapter_id": "BOUNDED_FORMAL_PROOF",
        "execution_authority": "AUTHORIZED_EXTERNAL_RUNNER",
        "exact_target": {"bounds": "explicit", "solver": "exact version and options", "counterexamples": "replayable"},
        "required_tools": ["qualified solver", "counterexample replay harness"],
        "required_environment": ["pinned solver inventory", "independent proof review"],
        "local_assertions": ["obligation completeness", "assumptions", "bounds", "proof artifact", "counterexample replay"],
    },
    {
        "case_id": "FRT-EXT-011-REPRESENTATIVE-PERFORMANCE",
        "title": "Representative performance and capacity campaign",
        "category": "PERFORMANCE",
        "external_check_id": "performance",
        "adapter_id": "REPRESENTATIVE_PERFORMANCE_CAMPAIGN",
        "execution_authority": "AUTHORIZED_EXTERNAL_RUNNER",
        "exact_target": {"samples_per_workload": 5, "budgets": "frozen before execution", "raw_samples": "preserved"},
        "required_tools": ["authorized performance runner", "resource telemetry"],
        "required_environment": ["representative workload", "controlled warmup", "frozen budgets"],
        "local_assertions": ["raw samples", "p95 and p99", "error rate", "throughput", "resource utilization"],
    },
    {
        "case_id": "FRT-EXT-012-AUTHORIZED-PENETRATION",
        "title": "Authorized penetration assessment and retest",
        "category": "PENETRATION",
        "external_check_id": "penetration_test",
        "adapter_id": "AUTHORIZED_PENETRATION_ASSESSMENT",
        "execution_authority": "AUTHORIZED_EXTERNAL_RUNNER_AND_HUMAN",
        "exact_target": {"scope": "written exact targets", "open_critical": 0, "open_high": 0, "unretested_findings": 0},
        "required_tools": ["approved security tools", "manual assessment workflow"],
        "required_environment": ["written authorization", "isolated or approved target", "retest authority"],
        "local_assertions": ["scope enforcement", "automated scan", "manual testing", "finding register", "retest"],
    },
    {
        "case_id": "FRT-EXT-013-CHAOS-DR",
        "title": "Authorized Chaos, backup, restore and DR drill",
        "category": "DISASTER_RECOVERY",
        "external_check_id": "chaos_dr",
        "adapter_id": "AUTHORIZED_CHAOS_DR_DRILL",
        "execution_authority": "AUTHORIZED_EXTERNAL_RUNNER",
        "exact_target": {"environment": "isolated authorized", "rpo": "at or below budget", "rto": "at or below budget"},
        "required_tools": ["fault-injection adapter", "backup and restore tooling", "reconciliation"],
        "required_environment": ["bounded blast radius", "rollback", "cleanup authority"],
        "local_assertions": ["fault injection", "backup manifest", "restore", "integrity reconciliation", "RTO and RPO"],
    },
    {
        "case_id": "FRT-EXT-014-PRODUCTION-OBSERVATION",
        "title": "Authorized production observation window",
        "category": "PRODUCTION_OBSERVATION",
        "external_check_id": "production_observation",
        "adapter_id": "AUTHORIZED_PRODUCTION_OBSERVATION",
        "execution_authority": "AUTHORIZED_PRODUCTION_OBSERVER",
        "exact_target": {"minimum_minutes": 60, "deployment": "exact artifact digest", "telemetry": "privacy minimized"},
        "required_tools": ["approved read-only observability connector", "alert reconciliation"],
        "required_environment": ["production access authorization", "exact deployment digest", "privacy review"],
        "local_assertions": ["SLO raw export", "alert delivery", "privacy redaction", "incident register", "deployment binding"],
    },
    {
        "case_id": "FRT-EXT-015-CUSTOMER-ACCEPTANCE",
        "title": "Independent customer acceptance decision",
        "category": "CUSTOMER_ACCEPTANCE",
        "external_check_id": "customer_acceptance",
        "adapter_id": "INDEPENDENT_CUSTOMER_ACCEPTANCE",
        "execution_authority": "INDEPENDENT_CUSTOMER_AND_REVIEWER",
        "exact_target": {"organizations": 2, "participants": 6, "p0_pass_rate": 1.0, "decision": "human authority only"},
        "required_tools": ["consent workflow", "privacy-minimized observation capture"],
        "required_environment": ["informed consent", "independent review", "accountable customer decision"],
        "local_assertions": ["participant roles", "journey scope", "task observation", "finding register", "customer decision"],
    },
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def repository_ref(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    relative = resolved.relative_to(ROOT.resolve()).as_posix()
    return {"path": relative, "sha256": sha256_file(resolved), "bytes": resolved.stat().st_size}


def build_plan() -> dict[str, Any]:
    profile = load_json(PROFILE)
    installed = load_json(INSTALLED_MANIFEST)
    checks = profile.get("checks", {})
    cases: list[dict[str, Any]] = []
    for definition in CASE_DEFINITIONS:
        check_id = definition["external_check_id"]
        spec = checks.get(check_id)
        if not isinstance(spec, dict):
            raise ValueError(f"external evidence profile is missing {check_id}")
        cases.append({
            **definition,
            "required_evidence_roles": spec["required_evidence_roles"],
            "required_metrics": spec["required_metrics"],
            "required_claims": spec["required_claims"],
            "external_state": "NOT_RUN",
            "production_operation_authorized": False,
            "certification": "NOT_CERTIFIED",
        })
    return {
        "schema_version": 1,
        "plan_id": "frt-g01-g30-external-qualification-v1",
        "pack_key": "frt-g01-g30-platform",
        "profile_ref": repository_ref(PROFILE),
        "quality_matrix_ref": repository_ref(QUALITY_MATRIX),
        "package_manifest_sha256": installed["source_package_manifest_sha256"],
        "source_tree_sha256": installed["source_tree_sha256"],
        "case_count": len(cases),
        "cases": cases,
        "boundaries": {
            "local_harness_is_external_evidence": False,
            "templates_are_evidence": False,
            "preflight_can_upgrade_external_state": False,
            "production_operation_authorized": False,
            "production_certification": "NOT_CERTIFIED",
        },
    }


def validate_plan(value: Any) -> list[str]:
    failures: list[str] = []
    expected = build_plan()
    if not isinstance(value, dict) or set(value) != PLAN_ROOT_KEYS:
        return ["external qualification plan root fields are not exact"]
    if value.get("case_count") != len(CASE_DEFINITIONS):
        failures.append("external qualification case count is not exact")
    cases = value.get("cases")
    if not isinstance(cases, list):
        return failures + ["external qualification cases must be an array"]
    actual_ids: list[str] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or set(case) != CASE_KEYS:
            failures.append(f"case[{index}] fields are not exact")
            continue
        actual_ids.append(str(case.get("case_id")))
        if case.get("external_state") != "NOT_RUN":
            failures.append(f"case[{index}] external state must remain NOT_RUN")
        if case.get("production_operation_authorized") is not False:
            failures.append(f"case[{index}] may not authorize a production operation")
        if case.get("certification") != "NOT_CERTIFIED":
            failures.append(f"case[{index}] may not claim certification")
        for field in ("required_tools", "required_environment", "local_assertions", "required_evidence_roles", "required_metrics", "required_claims"):
            if not isinstance(case.get(field), list) or not case[field]:
                failures.append(f"case[{index}].{field} must be non-empty")
    expected_ids = [case["case_id"] for case in CASE_DEFINITIONS]
    if actual_ids != expected_ids or len(set(actual_ids)) != len(expected_ids):
        failures.append("external qualification case IDs or ordering are not exact")
    expected_checks = set(load_json(PROFILE)["checks"])
    observed_checks = {case.get("external_check_id") for case in cases if isinstance(case, dict)}
    if observed_checks != expected_checks:
        failures.append("external qualification plan does not cover every external gate check")
    if canonical_bytes(value) != canonical_bytes(expected):
        failures.append("external qualification plan differs from generated source of truth")
    return failures


def browser_probe() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["node", str(BROWSER_PROBE), "--launch"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"state": "FAILED", "reason": type(error).__name__, "runtimes": {}}
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "state": "FAILED",
            "reason": "BROWSER_PROBE_OUTPUT_INVALID",
            "stdout_sha256": sha256_bytes(completed.stdout.encode("utf-8")),
            "stderr_sha256": sha256_bytes(completed.stderr.encode("utf-8")),
            "runtimes": {},
        }
    value["state"] = "PASSED" if completed.returncode == 0 else "FAILED"
    return value


def non_placeholder_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.name.lower() not in {"readme.md", ".gitkeep"} and path.stat().st_size > 0
    )


def tool_preflight() -> dict[str, Any]:
    hvigor_env = os.environ.get("ELMOS_HVIGORW", "").strip()
    hvigor_available = bool(hvigor_env and Path(hvigor_env).is_file()) or bool(
        shutil.which("hvigorw") or shutil.which("hvigor")
    )
    customer_root_value = os.environ.get("ELMOS_FRT_CUSTOMER_REPOSITORY_ROOT", "").strip()
    customer_root = Path(customer_root_value).resolve() if customer_root_value else None
    external_runner_value = os.environ.get("ELMOS_FRT_EXTERNAL_RUNNER", "").strip()
    external_runner = Path(external_runner_value).resolve() if external_runner_value else None
    device = load_json(DEVICE_CANDIDATE) if DEVICE_CANDIDATE.is_file() else {}
    at_template = load_json(AT_TEMPLATE) if AT_TEMPLATE.is_file() else {}
    return {
        "browser_runtimes": browser_probe(),
        "arkui_hvigor": {
            "available": hvigor_available,
            "source": "ELMOS_HVIGORW" if hvigor_env else ("PATH" if hvigor_available else "UNAVAILABLE"),
        },
        "approved_visual_baselines": {
            "count": len(non_placeholder_files(APPROVED_VISUAL_ROOT)),
            "approval_required": True,
        },
        "assistive_technology": {
            "template_present": AT_TEMPLATE.is_file(),
            "template_only": at_template.get("template_only") is True,
            "session_executed": False,
        },
        "physical_devices": {
            "candidate_present": DEVICE_CANDIDATE.is_file(),
            "candidate_count": device.get("physical_device_count", 0),
            "manual_acceptance_executed": False,
        },
        "customer_repositories": {
            "root_configured": bool(customer_root and customer_root.is_dir()),
            "authorized_campaign_executed": False,
        },
        "independent_holdout": {
            "non_placeholder_file_count": len(non_placeholder_files(HOLDOUT_ROOT)),
            "independence_attested": False,
        },
        "external_runner": {
            "configured": bool(
                external_runner
                and external_runner.is_file()
                and os.access(external_runner, os.X_OK)
            ),
        },
        "production": {
            "observation_authorized": False,
            "customer_acceptance_executed": False,
        },
    }


def case_blockers(case: dict[str, Any], tools: dict[str, Any]) -> list[str]:
    adapter = case["adapter_id"]
    blockers: list[str] = []
    browser_runtimes = tools["browser_runtimes"].get("runtimes", {})
    if adapter == "PLAYWRIGHT_FIREFOX_DESKTOP":
        runtime = browser_runtimes.get("firefox", {})
        if not runtime.get("launch_available"):
            blockers.append("EXACT_FIREFOX_RUNTIME_UNAVAILABLE")
        elif runtime.get("detected_version") != "151.0":
            blockers.append("EXACT_FIREFOX_VERSION_MISMATCH")
    if adapter in {"PLAYWRIGHT_WEBKIT_DESKTOP", "PLAYWRIGHT_WEBKIT_IPHONE15"}:
        runtime = browser_runtimes.get("webkit", {})
        if not runtime.get("launch_available"):
            blockers.append("EXACT_WEBKIT_RUNTIME_UNAVAILABLE")
        elif runtime.get("detected_version") != "26.5":
            blockers.append("EXACT_WEBKIT_VERSION_MISMATCH")
    if adapter == "ARKUI_HVIGOR_BUILD" and not tools["arkui_hvigor"]["available"]:
        blockers.append("DEVECO_HVIGOR_TOOLCHAIN_UNAVAILABLE")
    if adapter == "INDEPENDENT_VISUAL_BASELINE" and tools["approved_visual_baselines"]["count"] == 0:
        blockers.append("INDEPENDENT_APPROVED_BASELINE_MISSING")
    if adapter == "MANUAL_ASSISTIVE_TECHNOLOGY":
        blockers.append("MANUAL_ASSISTIVE_TECHNOLOGY_SESSION_REQUIRED")
    if adapter == "PHYSICAL_DEVICE_ACCEPTANCE":
        blockers.append("PHYSICAL_DEVICE_MANUAL_ACCEPTANCE_REQUIRED")
    if adapter == "REAL_CUSTOMER_REPOSITORY_CAMPAIGN" and not tools["customer_repositories"]["root_configured"]:
        blockers.append("AUTHORIZED_CUSTOMER_REPOSITORY_ROOT_UNCONFIGURED")
    if adapter == "INDEPENDENT_HOLDOUT_CAMPAIGN" and tools["independent_holdout"]["non_placeholder_file_count"] == 0:
        blockers.append("INDEPENDENT_HOLDOUT_CORPUS_UNAVAILABLE")
    if case["execution_authority"] not in {"LOCAL_EXACT_TOOLCHAIN"}:
        blockers.append("SIGNED_EXTERNAL_AUTHORIZATION_AND_INDEPENDENT_EXECUTION_REQUIRED")
    if adapter in {
        "REAL_CUSTOMER_REPOSITORY_CAMPAIGN",
        "INDEPENDENT_HOLDOUT_CAMPAIGN",
        "BOUNDED_FORMAL_PROOF",
        "REPRESENTATIVE_PERFORMANCE_CAMPAIGN",
        "AUTHORIZED_PENETRATION_ASSESSMENT",
        "AUTHORIZED_CHAOS_DR_DRILL",
        "AUTHORIZED_PRODUCTION_OBSERVATION",
        "INDEPENDENT_CUSTOMER_ACCEPTANCE",
    } and not tools["external_runner"]["configured"]:
        blockers.append("EXTERNAL_RUNNER_UNAVAILABLE")
    return sorted(set(blockers))


def observation(observation_id: str, state: str, detail: str) -> dict[str, str]:
    return {"observation_id": observation_id, "state": state, "detail": detail}


def browser_adapter_observations(
    case: dict[str, Any],
    tools: dict[str, Any],
) -> list[dict[str, str]]:
    runtime_name = "firefox" if "FIREFOX" in case["adapter_id"] else "webkit"
    expected_version = "151.0" if runtime_name == "firefox" else "26.5"
    runtime = tools["browser_runtimes"].get("runtimes", {}).get(runtime_name, {})
    launch_available = runtime.get("launch_available") is True
    version_matches = runtime.get("detected_version") == expected_version
    return [
        observation(
            "MANAGED_BROWSER_RUNTIME_LAUNCH",
            "PASSED" if launch_available else "BLOCKED",
            "exact managed runtime launched" if launch_available else "managed runtime is unavailable; no download attempted",
        ),
        observation(
            "MANAGED_BROWSER_VERSION_MATCH",
            "PASSED" if version_matches else "BLOCKED",
            f"required version {expected_version}" if version_matches else f"required version {expected_version} is not available",
        ),
        observation(
            "BROWSER_DOWNLOAD_BOUNDARY",
            "PASSED",
            "probe is launch-only and never downloads a browser",
        ),
    ]


def arkui_adapter_observations(
    _case: dict[str, Any],
    tools: dict[str, Any],
) -> list[dict[str, str]]:
    evidence_status = "NOT_RUN"
    if ROUTE_TOOLCHAIN_EVIDENCE.is_file():
        evidence = load_json(ROUTE_TOOLCHAIN_EVIDENCE)
        entries = [
            item for item in evidence.get("targetEvidence", [])
            if isinstance(item, dict) and item.get("target") == "ArkUI"
        ]
        if len(entries) == 1:
            evidence_status = str(entries[0].get("status", "NOT_RUN"))
    available = tools["arkui_hvigor"]["available"] is True
    return [
        observation(
            "HVIGOR_EXECUTABLE_PREFLIGHT",
            "PASSED" if available else "BLOCKED",
            "hvigor executable is configured" if available else "DevEco/hvigor is unavailable",
        ),
        observation(
            "ARKUI_NATIVE_BUILD_EVIDENCE",
            "PASSED" if evidence_status == "PASSED" else "BLOCKED",
            "real hvigor build passed" if evidence_status == "PASSED" else f"native build state is {evidence_status}",
        ),
    ]


def visual_adapter_observations(
    _case: dict[str, Any],
    tools: dict[str, Any],
) -> list[dict[str, str]]:
    policy = load_json(VISUAL_POLICY)
    baseline = load_json(BASELINE_MANIFEST)
    immutable = (
        policy.get("update_mode") == "NONE"
        and policy.get("max_diff_pixels") == 0
        and policy.get("pixel_threshold") == 0
        and policy.get("masks") == []
        and policy.get("tolerances_may_change_after_failure") is False
        and policy.get("approval_required_before_comparison") is True
        and baseline.get("automatic_updates") is False
        and baseline.get("candidate_and_approved_roots_are_distinct") is True
    )
    approved = tools["approved_visual_baselines"]["count"] > 0
    return [
        observation(
            "VISUAL_BASELINE_IMMUTABILITY_POLICY",
            "PASSED" if immutable else "BLOCKED",
            "baseline update, masks and tolerances remain fail-closed" if immutable else "visual policy is weakened",
        ),
        observation(
            "INDEPENDENT_APPROVED_BASELINE",
            "PASSED" if approved else "BLOCKED",
            "approved baseline exists" if approved else "independent approved baseline is absent",
        ),
    ]


def assistive_technology_adapter_observations(
    _case: dict[str, Any],
    tools: dict[str, Any],
) -> list[dict[str, str]]:
    template = load_json(AT_TEMPLATE)
    template_safe = (
        template.get("template_only") is True
        and template.get("decision") == "NOT_RUN"
        and all(value == "NOT_RUN" for value in template.get("observations", {}).values())
    )
    return [
        observation(
            "ASSISTIVE_TECHNOLOGY_SESSION_CONTRACT",
            "PASSED" if template_safe else "BLOCKED",
            "manual session template cannot claim evidence" if template_safe else "manual session template is unsafe",
        ),
        observation(
            "INDEPENDENT_MANUAL_SESSION",
            "BLOCKED",
            "trained independent operator and signed transcript are required",
        ),
    ]


def physical_device_adapter_observations(
    _case: dict[str, Any],
    tools: dict[str, Any],
) -> list[dict[str, str]]:
    candidate = load_json(DEVICE_CANDIDATE) if DEVICE_CANDIDATE.is_file() else {}
    privacy = candidate.get("privacy", {})
    minimized = (
        privacy.get("raw_identifiers_persisted") is False
        and privacy.get("raw_command_output_persisted") is False
        and privacy.get("device_names_persisted") is False
    )
    return [
        observation(
            "PHYSICAL_DEVICE_PRIVACY_MINIMIZATION",
            "PASSED" if minimized else "BLOCKED",
            "raw device identifiers and command output are not persisted" if minimized else "device candidate violates privacy policy",
        ),
        observation(
            "PHYSICAL_DEVICE_CANDIDATE",
            "PASSED" if tools["physical_devices"]["candidate_count"] > 0 else "BLOCKED",
            f"privacy-minimized candidate count {tools['physical_devices']['candidate_count']}",
        ),
        observation(
            "PHYSICAL_DEVICE_MANUAL_ACCEPTANCE",
            "BLOCKED",
            "install, launch, P0 journeys, visual and AT acceptance require an authorized human session",
        ),
    ]


def external_campaign_adapter_observations(
    case: dict[str, Any],
    _tools: dict[str, Any],
) -> list[dict[str, str]]:
    check_id = case["external_check_id"]
    registered = check_id in CAMPAIGN_PARAMETER_CHECKS
    return [
        observation(
            "TYPED_CAMPAIGN_PARAMETER_CONTRACT",
            "PASSED" if registered else "BLOCKED",
            f"exact typed parameters registered for {check_id}" if registered else f"missing typed parameters for {check_id}",
        ),
        observation(
            "EXTERNAL_EXECUTION_AUTHORITY",
            "BLOCKED",
            "signed authorization, allowlisted external Runner and independent evidence are required",
        ),
    ]


ADAPTER_HANDLERS = {
    "PLAYWRIGHT_FIREFOX_DESKTOP": browser_adapter_observations,
    "PLAYWRIGHT_WEBKIT_DESKTOP": browser_adapter_observations,
    "PLAYWRIGHT_WEBKIT_IPHONE15": browser_adapter_observations,
    "ARKUI_HVIGOR_BUILD": arkui_adapter_observations,
    "INDEPENDENT_VISUAL_BASELINE": visual_adapter_observations,
    "MANUAL_ASSISTIVE_TECHNOLOGY": assistive_technology_adapter_observations,
    "PHYSICAL_DEVICE_ACCEPTANCE": physical_device_adapter_observations,
    "REAL_CUSTOMER_REPOSITORY_CAMPAIGN": external_campaign_adapter_observations,
    "INDEPENDENT_HOLDOUT_CAMPAIGN": external_campaign_adapter_observations,
    "BOUNDED_FORMAL_PROOF": external_campaign_adapter_observations,
    "REPRESENTATIVE_PERFORMANCE_CAMPAIGN": external_campaign_adapter_observations,
    "AUTHORIZED_PENETRATION_ASSESSMENT": external_campaign_adapter_observations,
    "AUTHORIZED_CHAOS_DR_DRILL": external_campaign_adapter_observations,
    "AUTHORIZED_PRODUCTION_OBSERVATION": external_campaign_adapter_observations,
    "INDEPENDENT_CUSTOMER_ACCEPTANCE": external_campaign_adapter_observations,
}


def build_preflight(plan: dict[str, Any], plan_path: Path = DEFAULT_PLAN) -> dict[str, Any]:
    failures = validate_plan(plan)
    if failures:
        raise ValueError("; ".join(failures))
    tools = tool_preflight()
    cases = []
    for case in plan["cases"]:
        blockers = case_blockers(case, tools)
        cases.append({
            "case_id": case["case_id"],
            "adapter_id": case["adapter_id"],
            "harness_state": "READY_FOR_AUTHORIZED_EXECUTION" if not blockers else "BLOCKED_PRECONDITION",
            "blockers": blockers,
            "external_state": "NOT_RUN",
            "production_operation_authorized": False,
            "certification": "NOT_CERTIFIED",
        })
    return {
        "schema_version": 1,
        "kind": "FRT_EXTERNAL_QUALIFICATION_PREFLIGHT",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "plan_sha256": sha256_bytes(canonical_bytes(plan)),
        "plan_file_ref": repository_ref(plan_path),
        "case_count": len(cases),
        "tools": tools,
        "cases": cases,
        "external_state_counts": {"NOT_RUN": len(cases)},
        "production_operation_authorized": False,
        "production_certification": "NOT_CERTIFIED",
        "note": "Preflight and local harness results are engineering evidence only and cannot upgrade an external check.",
    }


def validate_preflight(
    value: Any,
    plan: dict[str, Any],
    plan_path: Path = DEFAULT_PLAN,
) -> list[str]:
    failures = validate_plan(plan)
    if failures:
        return [f"plan: {failure}" for failure in failures]
    if not isinstance(value, dict) or set(value) != PREFLIGHT_ROOT_KEYS:
        return ["external qualification preflight root fields are not exact"]
    if value.get("schema_version") != 1 or value.get("kind") != "FRT_EXTERNAL_QUALIFICATION_PREFLIGHT":
        failures.append("external qualification preflight identity is invalid")
    try:
        generated_at = datetime.fromisoformat(str(value.get("generated_at", "")).replace("Z", "+00:00"))
        if generated_at.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError:
        failures.append("external qualification preflight timestamp is invalid")
    if value.get("plan_sha256") != sha256_bytes(canonical_bytes(plan)):
        failures.append("external qualification preflight plan digest is stale")
    if value.get("plan_file_ref") != repository_ref(plan_path):
        failures.append("external qualification preflight plan file reference is stale")
    if value.get("case_count") != len(CASE_DEFINITIONS):
        failures.append("external qualification preflight case count is not exact")

    tools = value.get("tools")
    if not isinstance(tools, dict) or set(tools) != PREFLIGHT_TOOL_KEYS:
        failures.append("external qualification preflight tool inventory is not exact")
    else:
        for tool_name, exact_keys in PREFLIGHT_TOOL_FIELD_KEYS.items():
            tool = tools.get(tool_name)
            if not isinstance(tool, dict) or set(tool) != exact_keys:
                failures.append(f"{tool_name} preflight fields are not exact")
        browser = tools.get("browser_runtimes")
        if not isinstance(browser, dict):
            failures.append("browser runtime preflight must be an object")
        else:
            browser_state = browser.get("state")
            allowed_browser_keys = {
                "state",
                "reason",
                "runtimes",
                "stdout_sha256",
                "stderr_sha256",
                "schema_version",
                "kind",
                "playwright_version",
                "boundaries",
            }
            if set(browser) - allowed_browser_keys:
                failures.append("browser runtime preflight contains unexpected fields")
            browser_boundaries = browser.get("boundaries")
            if browser_state == "PASSED":
                if set(browser) != {
                    "schema_version",
                    "kind",
                    "playwright_version",
                    "runtimes",
                    "boundaries",
                    "state",
                }:
                    failures.append("successful browser runtime preflight fields are not exact")
                if (
                    browser.get("schema_version") != 1
                    or browser.get("kind") != "FRT_PLAYWRIGHT_RUNTIME_PREFLIGHT"
                    or browser.get("playwright_version") != "1.61.1"
                ):
                    failures.append("browser runtime preflight identity or version is invalid")
                runtimes = browser.get("runtimes")
                if not isinstance(runtimes, dict) or set(runtimes) != {"firefox", "webkit"}:
                    failures.append("browser runtime inventory is not exact")
                else:
                    for runtime_name, runtime in runtimes.items():
                        if not isinstance(runtime, dict) or frozenset(runtime) not in {
                            frozenset(BROWSER_RUNTIME_KEYS),
                            frozenset(BROWSER_RUNTIME_KEYS | {"launch_error_sha256"}),
                        }:
                            failures.append(f"{runtime_name} runtime fields are not exact")
                            continue
                        if runtime.get("name") != runtime_name:
                            failures.append(f"{runtime_name} runtime identity is invalid")
                        if runtime.get("executable_present") is False and (
                            runtime.get("executable_sha256") is not None
                            or runtime.get("launch_attempted") is not False
                            or runtime.get("launch_available") is not False
                        ):
                            failures.append(f"{runtime_name} missing executable state is inconsistent")
                        if runtime.get("launch_available") is True and (
                            runtime.get("executable_present") is not True
                            or runtime.get("launch_attempted") is not True
                            or not isinstance(runtime.get("detected_version"), str)
                            or runtime.get("reason") is not None
                        ):
                            failures.append(f"{runtime_name} launch state is inconsistent")
            elif browser_state != "FAILED":
                failures.append("browser runtime preflight state is invalid")
            if isinstance(browser_boundaries, dict) and (
                browser_boundaries.get("downloads_attempted") is not False
                or browser_boundaries.get("browser_journeys_executed") is not False
                or browser_boundaries.get("external_state") != "NOT_RUN"
                or browser_boundaries.get("certification") != "NOT_CERTIFIED"
            ):
                failures.append("browser preflight exceeded its local authority")
        if isinstance(tools.get("approved_visual_baselines"), dict) and tools["approved_visual_baselines"].get("approval_required") is not True:
            failures.append("independent visual baseline approval may not be bypassed")
        if isinstance(tools.get("assistive_technology"), dict) and tools["assistive_technology"].get("session_executed") is not False:
            failures.append("preflight may not claim a manual assistive-technology session")
        if isinstance(tools.get("physical_devices"), dict) and tools["physical_devices"].get("manual_acceptance_executed") is not False:
            failures.append("preflight may not claim physical-device manual acceptance")
        if isinstance(tools.get("customer_repositories"), dict) and tools["customer_repositories"].get("authorized_campaign_executed") is not False:
            failures.append("preflight may not claim a customer repository campaign")
        if isinstance(tools.get("independent_holdout"), dict) and tools["independent_holdout"].get("independence_attested") is not False:
            failures.append("preflight may not attest holdout independence")
        if isinstance(tools.get("production"), dict) and (
            tools["production"].get("observation_authorized") is not False
            or tools["production"].get("customer_acceptance_executed") is not False
        ):
            failures.append("preflight may not claim production or customer authority")

    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != len(CASE_DEFINITIONS):
        failures.append("external qualification preflight case inventory is incomplete")
    else:
        expected = [(case["case_id"], case["adapter_id"]) for case in plan["cases"]]
        observed: list[tuple[Any, Any]] = []
        for index, case in enumerate(cases):
            if not isinstance(case, dict) or set(case) != PREFLIGHT_CASE_KEYS:
                failures.append(f"preflight case[{index}] fields are not exact")
                continue
            observed.append((case.get("case_id"), case.get("adapter_id")))
            blockers = case.get("blockers")
            if not isinstance(blockers, list) or blockers != sorted(set(blockers)):
                failures.append(f"preflight case[{index}] blockers must be a sorted unique array")
            expected_harness_state = "BLOCKED_PRECONDITION" if blockers else "READY_FOR_AUTHORIZED_EXECUTION"
            if case.get("harness_state") != expected_harness_state:
                failures.append(f"preflight case[{index}] harness state does not match blockers")
            if case.get("external_state") != "NOT_RUN":
                failures.append(f"preflight case[{index}] external state must remain NOT_RUN")
            if case.get("production_operation_authorized") is not False:
                failures.append(f"preflight case[{index}] may not authorize a production operation")
            if case.get("certification") != "NOT_CERTIFIED":
                failures.append(f"preflight case[{index}] may not claim certification")
        if observed != expected:
            failures.append("external qualification preflight case identity or ordering is not exact")

    if value.get("external_state_counts") != {"NOT_RUN": len(CASE_DEFINITIONS)}:
        failures.append("external qualification preflight state count is invalid")
    if value.get("production_operation_authorized") is not False:
        failures.append("external qualification preflight may not authorize production operations")
    if value.get("production_certification") != "NOT_CERTIFIED":
        failures.append("external qualification preflight may not claim production certification")
    if not isinstance(value.get("note"), str) or not value["note"].strip():
        failures.append("external qualification preflight note is required")
    return failures


def count_states(values: list[str]) -> dict[str, int]:
    return {state: values.count(state) for state in sorted(set(values))}


def build_local_execution(
    plan: dict[str, Any],
    preflight: dict[str, Any],
    *,
    plan_path: Path = DEFAULT_PLAN,
    preflight_path: Path = DEFAULT_PREFLIGHT,
) -> dict[str, Any]:
    failures = validate_preflight(preflight, plan, plan_path)
    if failures:
        raise ValueError("; ".join(failures))
    planned_adapters = {case["adapter_id"] for case in plan["cases"]}
    if set(ADAPTER_HANDLERS) != planned_adapters:
        raise ValueError("local adapter registry does not exactly cover the qualification plan")
    preflight_by_id = {case["case_id"]: case for case in preflight["cases"]}
    tools = preflight["tools"]
    cases: list[dict[str, Any]] = []
    for case in plan["cases"]:
        blockers = preflight_by_id[case["case_id"]]["blockers"]
        observations = ADAPTER_HANDLERS[case["adapter_id"]](case, tools)
        if not observations:
            raise ValueError(f"adapter emitted no observations: {case['adapter_id']}")
        if case["execution_authority"] == "LOCAL_EXACT_TOOLCHAIN":
            local_state = "BLOCKED_TOOLCHAIN" if blockers else "READY_FOR_LOCAL_EXECUTION"
        else:
            local_state = "REQUIRES_EXTERNAL_AUTHORITY"
        cases.append({
            "case_id": case["case_id"],
            "adapter_id": case["adapter_id"],
            "code_contract_state": "PASSED_LOCAL_TOOLING",
            "local_execution_state": local_state,
            "observations": observations,
            "blockers": blockers,
            "external_state": "NOT_RUN",
            "production_operation_authorized": False,
            "certification": "NOT_CERTIFIED",
        })
    return {
        "schema_version": 1,
        "kind": "FRT_EXTERNAL_QUALIFICATION_LOCAL_EXECUTION",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "plan_sha256": sha256_bytes(canonical_bytes(plan)),
        "preflight_sha256": sha256_file(preflight_path),
        "case_count": len(cases),
        "cases": cases,
        "code_contract_counts": count_states([case["code_contract_state"] for case in cases]),
        "local_execution_counts": count_states([case["local_execution_state"] for case in cases]),
        "external_state_counts": {"NOT_RUN": len(cases)},
        "production_operation_authorized": False,
        "production_certification": "NOT_CERTIFIED",
        "note": "All adapters were exercised at code-contract level. Toolchain, human, customer, independent and production execution remains external evidence.",
    }


def validate_local_execution(
    value: Any,
    plan: dict[str, Any],
    preflight: dict[str, Any],
    *,
    plan_path: Path = DEFAULT_PLAN,
    preflight_path: Path = DEFAULT_PREFLIGHT,
) -> list[str]:
    failures = validate_preflight(preflight, plan, plan_path)
    if failures:
        return [f"preflight: {failure}" for failure in failures]
    planned_adapters = {case["adapter_id"] for case in plan["cases"]}
    if set(ADAPTER_HANDLERS) != planned_adapters:
        failures.append("local adapter registry does not exactly cover the qualification plan")
    if not isinstance(value, dict) or set(value) != LOCAL_EXECUTION_ROOT_KEYS:
        return ["local qualification execution root fields are not exact"]
    if value.get("schema_version") != 1 or value.get("kind") != "FRT_EXTERNAL_QUALIFICATION_LOCAL_EXECUTION":
        failures.append("local qualification execution identity is invalid")
    try:
        generated_at = datetime.fromisoformat(str(value.get("generated_at", "")).replace("Z", "+00:00"))
        if generated_at.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError:
        failures.append("local qualification execution timestamp is invalid")
    if value.get("plan_sha256") != sha256_bytes(canonical_bytes(plan)):
        failures.append("local qualification execution plan digest is stale")
    if value.get("preflight_sha256") != sha256_file(preflight_path):
        failures.append("local qualification execution preflight digest is stale")
    cases = value.get("cases")
    if value.get("case_count") != len(CASE_DEFINITIONS) or not isinstance(cases, list) or len(cases) != len(CASE_DEFINITIONS):
        failures.append("local qualification execution case inventory is incomplete")
        return failures
    expected_identity = [(case["case_id"], case["adapter_id"]) for case in plan["cases"]]
    observed_identity: list[tuple[Any, Any]] = []
    preflight_by_id = {case["case_id"]: case for case in preflight["cases"]}
    code_states: list[str] = []
    local_states: list[str] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or set(case) != LOCAL_EXECUTION_CASE_KEYS:
            failures.append(f"local execution case[{index}] fields are not exact")
            continue
        observed_identity.append((case.get("case_id"), case.get("adapter_id")))
        if case.get("code_contract_state") != "PASSED_LOCAL_TOOLING":
            failures.append(f"local execution case[{index}] code contract did not pass")
        code_states.append(str(case.get("code_contract_state")))
        plan_case = plan["cases"][index]
        expected_local_state = (
            "BLOCKED_TOOLCHAIN"
            if plan_case["execution_authority"] == "LOCAL_EXACT_TOOLCHAIN" and preflight_by_id[plan_case["case_id"]]["blockers"]
            else "READY_FOR_LOCAL_EXECUTION"
            if plan_case["execution_authority"] == "LOCAL_EXACT_TOOLCHAIN"
            else "REQUIRES_EXTERNAL_AUTHORITY"
        )
        if case.get("local_execution_state") != expected_local_state:
            failures.append(f"local execution case[{index}] state does not match authority and blockers")
        local_states.append(str(case.get("local_execution_state")))
        if case.get("blockers") != preflight_by_id[plan_case["case_id"]]["blockers"]:
            failures.append(f"local execution case[{index}] blockers differ from preflight")
        observations = case.get("observations")
        if not isinstance(observations, list) or not observations:
            failures.append(f"local execution case[{index}] observations are missing")
        else:
            expected_observations = ADAPTER_HANDLERS[plan_case["adapter_id"]](
                plan_case,
                preflight["tools"],
            )
            if observations != expected_observations:
                failures.append(
                    f"local execution case[{index}] observations differ from adapter output"
                )
            observation_ids = [
                item.get("observation_id")
                for item in observations
                if isinstance(item, dict)
            ]
            if len(observation_ids) != len(set(observation_ids)):
                failures.append(
                    f"local execution case[{index}] observation identities are not unique"
                )
            for observation_index, item in enumerate(observations):
                if not isinstance(item, dict) or set(item) != OBSERVATION_KEYS:
                    failures.append(f"local execution case[{index}] observation[{observation_index}] fields are not exact")
                    continue
                if item.get("state") not in {"PASSED", "BLOCKED", "NOT_APPLICABLE"}:
                    failures.append(f"local execution case[{index}] observation[{observation_index}] state is invalid")
                if not isinstance(item.get("detail"), str) or not item["detail"]:
                    failures.append(f"local execution case[{index}] observation[{observation_index}] detail is required")
        if case.get("external_state") != "NOT_RUN":
            failures.append(f"local execution case[{index}] external state must remain NOT_RUN")
        if case.get("production_operation_authorized") is not False:
            failures.append(f"local execution case[{index}] may not authorize production")
        if case.get("certification") != "NOT_CERTIFIED":
            failures.append(f"local execution case[{index}] may not claim certification")
    if observed_identity != expected_identity:
        failures.append("local qualification execution case identity or ordering is not exact")
    if value.get("code_contract_counts") != count_states(code_states):
        failures.append("local qualification execution code state counts are invalid")
    if value.get("local_execution_counts") != count_states(local_states):
        failures.append("local qualification execution local state counts are invalid")
    if value.get("external_state_counts") != {"NOT_RUN": len(CASE_DEFINITIONS)}:
        failures.append("local qualification execution external state count is invalid")
    if value.get("production_operation_authorized") is not False:
        failures.append("local qualification execution may not authorize production")
    if value.get("production_certification") != "NOT_CERTIFIED":
        failures.append("local qualification execution may not certify production")
    return failures


def generate_command(args: argparse.Namespace) -> int:
    plan = build_plan()
    write_json(args.output, plan)
    print(json.dumps({"output": str(args.output), "case_count": plan["case_count"], "sha256": sha256_file(args.output)}, indent=2))
    return 0


def check_command(args: argparse.Namespace) -> int:
    if not args.plan.is_file():
        print("external qualification plan is missing")
        return 2
    failures = validate_plan(load_json(args.plan))
    if failures:
        print("\n".join(f"REJECTED: {failure}" for failure in failures))
        return 2
    print(json.dumps({"plan": str(args.plan), "status": "PASSED", "case_count": len(CASE_DEFINITIONS)}, indent=2))
    return 0


def preflight_command(args: argparse.Namespace) -> int:
    plan = load_json(args.plan)
    result = build_preflight(plan, args.plan)
    write_json(args.output, result)
    print(json.dumps({
        "output": str(args.output),
        "case_count": result["case_count"],
        "external_state_counts": result["external_state_counts"],
        "production_certification": result["production_certification"],
    }, indent=2))
    return 0


def check_preflight_command(args: argparse.Namespace) -> int:
    if not args.plan.is_file() or not args.preflight.is_file():
        print("external qualification plan or preflight is missing")
        return 2
    plan = load_json(args.plan)
    failures = validate_preflight(load_json(args.preflight), plan, args.plan)
    if failures:
        print("\n".join(f"REJECTED: {failure}" for failure in failures))
        return 2
    print(json.dumps({
        "preflight": str(args.preflight),
        "status": "PASSED_LOCAL_TOOLING",
        "case_count": len(CASE_DEFINITIONS),
        "external_state_counts": {"NOT_RUN": len(CASE_DEFINITIONS)},
        "production_certification": "NOT_CERTIFIED",
    }, indent=2))
    return 0


def exercise_command(args: argparse.Namespace) -> int:
    plan = load_json(args.plan)
    preflight = load_json(args.preflight)
    result = build_local_execution(
        plan,
        preflight,
        plan_path=args.plan,
        preflight_path=args.preflight,
    )
    write_json(args.output, result)
    print(json.dumps({
        "output": str(args.output),
        "case_count": result["case_count"],
        "code_contract_counts": result["code_contract_counts"],
        "local_execution_counts": result["local_execution_counts"],
        "external_state_counts": result["external_state_counts"],
        "production_operation_authorized": result["production_operation_authorized"],
        "production_certification": result["production_certification"],
    }, indent=2))
    return 0


def check_execution_command(args: argparse.Namespace) -> int:
    if not args.plan.is_file() or not args.preflight.is_file() or not args.execution.is_file():
        print("external qualification plan, preflight or local execution report is missing")
        return 2
    plan = load_json(args.plan)
    preflight = load_json(args.preflight)
    failures = validate_local_execution(
        load_json(args.execution),
        plan,
        preflight,
        plan_path=args.plan,
        preflight_path=args.preflight,
    )
    if failures:
        print("\n".join(f"REJECTED: {failure}" for failure in failures))
        return 2
    print(json.dumps({
        "execution": str(args.execution),
        "status": "PASSED_LOCAL_TOOLING",
        "case_count": len(CASE_DEFINITIONS),
        "external_state_counts": {"NOT_RUN": len(CASE_DEFINITIONS)},
        "production_operation_authorized": False,
        "production_certification": "NOT_CERTIFIED",
    }, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("--output", type=Path, default=DEFAULT_PLAN)
    generate.set_defaults(func=generate_command)
    check = commands.add_parser("check")
    check.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    check.set_defaults(func=check_command)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    preflight.add_argument("--output", type=Path, default=DEFAULT_PREFLIGHT)
    preflight.set_defaults(func=preflight_command)
    check_preflight = commands.add_parser("check-preflight")
    check_preflight.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    check_preflight.add_argument("--preflight", type=Path, default=DEFAULT_PREFLIGHT)
    check_preflight.set_defaults(func=check_preflight_command)
    exercise = commands.add_parser("exercise")
    exercise.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    exercise.add_argument("--preflight", type=Path, default=DEFAULT_PREFLIGHT)
    exercise.add_argument("--output", type=Path, default=DEFAULT_LOCAL_EXECUTION)
    exercise.set_defaults(func=exercise_command)
    check_execution = commands.add_parser("check-execution")
    check_execution.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    check_execution.add_argument("--preflight", type=Path, default=DEFAULT_PREFLIGHT)
    check_execution.add_argument("--execution", type=Path, default=DEFAULT_LOCAL_EXECUTION)
    check_execution.set_defaults(func=check_execution_command)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

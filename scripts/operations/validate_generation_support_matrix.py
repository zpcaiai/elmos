#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SOURCE = ROOT / "engines" / "project-synthesis-engine" / "src"
sys.path.insert(0, str(ENGINE_SOURCE))

from elmos_project_synthesis import container_images  # noqa: E402
from elmos_project_synthesis.models import (  # noqa: E402
    SUPPORTED_LANGUAGES,
    SUPPORTED_PROFILE_TARGETS,
    TARGET_PROFILES,
)

# The same vocabulary the translation route matrix uses, so the two business
# lines describe the identical evidence ladder rather than inventing parallel
# spellings for the same three states.
LOCAL_STATUSES = {"PASSED_LOCAL", "NOT_RUN", "FAILED"}
VERIFICATION_STATUSES = {"PASSED", "NOT_RUN", "FAILED"}
CERTIFICATION_STATUSES = {"CERTIFIED", "NOT_CERTIFIED"}

# Evidence a target only earns by actually executing the production profile
# against a provisioned PostgreSQL instance.
PRODUCTION_EVIDENCE = "postgresql-integration"
DIGEST = re.compile(r"^[0-9a-f]{64}$")


class MatrixError(RuntimeError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise MatrixError(reason)


def load_rootless_runner() -> object:
    path = ROOT / "scripts" / "operations" / "rootless_project_runner.py"
    spec = importlib.util.spec_from_file_location("elmos_rootless_project_runner", path)
    require(spec is not None and spec.loader is not None, "ROOTLESS_RUNNER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def schema_languages() -> tuple[str, ...]:
    schema = json.loads(
        (ROOT / "contracts" / "project-synthesis-schema" / "synthesis-request-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    found: list[str] = []
    for name, definition in schema["$defs"].items():
        if not name.endswith("_target"):
            continue
        for item in definition.get("allOf", []):
            language = item.get("properties", {}).get("language", {}).get("const")
            if isinstance(language, str):
                found.append(language)
    return tuple(found)


def ui_profiles() -> dict[str, dict[str, str | int]]:
    catalog = (ROOT / "apps" / "web-console" / "app" / "lib" / "catalog.ts").read_text(
        encoding="utf-8"
    )
    profiles: dict[str, dict[str, str | int]] = {}
    pattern = re.compile(
        r'\{ id: "(?P<id>[^"]+)".*?port: (?P<port>\d+),.*?'
        r'verificationStatus: "NOT_RUN", maturity: "(?P<maturity>limited|experimental)"'
    )
    for line in catalog.splitlines():
        match = pattern.search(line)
        if match is not None:
            profiles[match.group("id")] = {
                "port": int(match.group("port")),
                "maturity": match.group("maturity"),
            }
    return profiles


def main() -> int:
    support = json.loads(
        (ROOT / "docs" / "project-synthesis" / "bundled-emitter-support.json").read_text(
            encoding="utf-8"
        )
    )
    profiles = support.get("profiles")
    require(isinstance(profiles, list), "SUPPORT_PROFILES_INVALID")
    matrix = {str(profile.get("language")): profile for profile in profiles if isinstance(profile, dict)}
    expected_languages = tuple(SUPPORTED_LANGUAGES)
    require(tuple(matrix) == expected_languages, "SUPPORT_LANGUAGE_ORDER_DRIFT")
    require(len(matrix) == 8, "SUPPORT_LANGUAGE_COUNT_DRIFT")
    # Order matters. The ladder is checked first and the resting-state pins
    # come after, so the ordering rules are reachable code that a negative
    # control can actually exercise. Pinning first would make every inversion
    # report the pin instead, leaving the ladder untested and, in practice,
    # dead -- which is how a guard rots without anyone noticing.
    local_status = support.get("local_execution_status", "NOT_RUN")
    independent_status = support.get("independent_verification_status", "NOT_RUN")
    external_status = support.get("external_evidence_status")
    require(local_status in LOCAL_STATUSES, "LOCAL_EXECUTION_STATUS_INVALID")
    require(independent_status in VERIFICATION_STATUSES, "INDEPENDENT_VERIFICATION_STATUS_INVALID")
    require(external_status in VERIFICATION_STATUSES, "EXTERNAL_EVIDENCE_STATUS_INVALID")
    require(support.get("certification_status") in CERTIFICATION_STATUSES, "CERTIFICATION_STATUS_INVALID")

    # Evidence may never run ahead of itself: independent verification
    # requires a local pass, and external certification requires an
    # independent pass.
    if independent_status == "PASSED":
        require(local_status == "PASSED_LOCAL", "GENERATION_EVIDENCE_INVERTED")
    if external_status == "PASSED":
        require(local_status == "PASSED_LOCAL", "GENERATION_EVIDENCE_INVERTED")
        require(
            independent_status == "PASSED",
            "GENERATION_CERTIFICATION_PRECEDES_VERIFICATION",
        )
    if support.get("certification_status") == "CERTIFIED":
        require(external_status == "PASSED", "GENERATION_CERTIFICATION_UNSUPPORTED")
        # A claim ceiling of "limited" and a certified line are contradictory;
        # whichever is wrong, the matrix must not publish both.
        require(support.get("claim_ceiling") != "limited", "GENERATION_CLAIM_CEILING_CONTRADICTS_CERTIFICATION")

    # Today's honest resting state. These pins are deliberate: the local gate
    # never issues certification, so relaxing them is a decision that needs a
    # real external process behind it, not a code edit.
    require(support.get("claim_ceiling") == "limited", "CLAIM_CEILING_MUST_BE_LIMITED")
    require(support.get("external_evidence_status") == "NOT_RUN", "EXTERNAL_EVIDENCE_MUST_BE_NOT_RUN")
    require(support.get("certification_status") == "NOT_CERTIFIED", "CERTIFICATION_MUST_BE_NOT_CERTIFIED")

    evidence_path = support.get("local_evidence")
    require(
        evidence_path == "docs/project-synthesis/local-production-profile-matrix.json",
        "LOCAL_EVIDENCE_PATH_DRIFT",
    )
    production_matrix = json.loads((ROOT / evidence_path).read_text(encoding="utf-8"))
    require(
        production_matrix.get("kind") == "elmos.local-production-profile-matrix",
        "LOCAL_EVIDENCE_KIND_INVALID",
    )
    require(production_matrix.get("status") == "PASSED", "LOCAL_EVIDENCE_NOT_PASSED")
    require(production_matrix.get("evidence_class") == "LOCAL_ENGINEERING", "LOCAL_EVIDENCE_CLASS_INVALID")
    require(production_matrix.get("case_count") == 16, "LOCAL_EVIDENCE_CASE_COUNT_INVALID")
    require(production_matrix.get("passed_count") == 16, "LOCAL_EVIDENCE_PASS_COUNT_INVALID")
    require(production_matrix.get("failures") == [], "LOCAL_EVIDENCE_FAILURES_PRESENT")
    require(production_matrix.get("production_delivery_status") == "NOT_RUN", "DELIVERY_EVIDENCE_OVERCLAIM")
    require(production_matrix.get("independent_verification_status") == "NOT_RUN", "INDEPENDENT_EVIDENCE_OVERCLAIM")
    require(production_matrix.get("external_certification_status") == "NOT_RUN", "EXTERNAL_EVIDENCE_OVERCLAIM")
    require(production_matrix.get("certification_status") == "NOT_CERTIFIED", "CERTIFICATION_EVIDENCE_OVERCLAIM")

    evidence_cases = production_matrix.get("cases")
    require(isinstance(evidence_cases, list) and len(evidence_cases) == 16, "LOCAL_EVIDENCE_CASES_INVALID")
    expected_pairs = {
        (language, auth_mode)
        for language in expected_languages
        for auth_mode in ("jwt", "oidc")
    }
    observed_pairs: set[tuple[str, str]] = set()
    for case in evidence_cases:
        require(isinstance(case, dict), "LOCAL_EVIDENCE_CASE_INVALID")
        language = case.get("language")
        auth_mode = case.get("auth_mode")
        require(isinstance(language, str) and isinstance(auth_mode, str), "LOCAL_EVIDENCE_CASE_ID_INVALID")
        pair = (language, auth_mode)
        require(pair not in observed_pairs, "LOCAL_EVIDENCE_CASE_DUPLICATE")
        observed_pairs.add(pair)
        require(case.get("status") == "PASSED", f"LOCAL_EVIDENCE_CASE_NOT_PASSED:{language}:{auth_mode}")
        require(case.get("cleanup_status") == "PASSED", f"LOCAL_EVIDENCE_CLEANUP_FAILED:{language}:{auth_mode}")
        require(case.get("exact_toolchain_match") is True, f"LOCAL_EVIDENCE_TOOLCHAIN_MISMATCH:{language}:{auth_mode}")
        for digest_field in (
            "request_sha256",
            "approved_payload_sha256",
            "generation_manifest_sha256",
        ):
            require(
                isinstance(case.get(digest_field), str)
                and DIGEST.fullmatch(case[digest_field]) is not None,
                f"LOCAL_EVIDENCE_DIGEST_INVALID:{language}:{auth_mode}:{digest_field}",
            )
        probes = case.get("startup_probes")
        require(
            isinstance(probes, list)
            and len(probes) == 1
            and isinstance(probes[0], dict)
            and probes[0].get("status") == "PASSED"
            and probes[0].get("integration_status") == "PASSED",
            f"LOCAL_EVIDENCE_PROBE_INVALID:{language}:{auth_mode}",
        )
    require(observed_pairs == expected_pairs, "LOCAL_EVIDENCE_CASE_MATRIX_INCOMPLETE")

    limited = set(expected_languages)
    for language, target in TARGET_PROFILES.items():
        declared = matrix[language]
        for field in ("framework", "runtime", "toolchain"):
            require(declared.get(field) == target[field], f"{language.upper()}_{field.upper()}_DRIFT")
        expected_maturity = "limited" if language in limited else "experimental"
        require(declared.get("maturity") == expected_maturity, f"{language.upper()}_MATURITY_DRIFT")
        evidence = declared.get("required_evidence")
        require(isinstance(evidence, list) and "startup-probe" in evidence, f"{language.upper()}_EVIDENCE_INCOMPLETE")
        # A target open for the PostgreSQL production profile must say so in
        # the published matrix, and a target that says so must actually be
        # open. Either half alone lets the shipped claim drift away from what
        # the engine will really accept.
        profile_open = language in SUPPORTED_PROFILE_TARGETS[("postgresql", "jwt")]
        require(
            profile_open == (PRODUCTION_EVIDENCE in evidence),
            f"{language.upper()}_PRODUCTION_EVIDENCE_DRIFT",
        )
        require(
            (language in SUPPORTED_PROFILE_TARGETS[("postgresql", "jwt")])
            == (language in SUPPORTED_PROFILE_TARGETS[("postgresql", "oidc")]),
            f"{language.upper()}_AUTH_MODE_ASYMMETRY",
        )

    require(schema_languages() == expected_languages, "REQUEST_SCHEMA_LANGUAGE_DRIFT")
    rootless = load_rootless_runner()
    require(tuple(rootless.LANGUAGE_DIRECTORIES) == expected_languages, "ROOTLESS_LANGUAGE_DRIFT")
    require(
        {language: TARGET_PROFILES[language]["port"] for language in expected_languages} == rootless.PORTS,
        "ROOTLESS_PORT_DRIFT",
    )
    require(
        rootless.HEALTH_PATHS == {language: "/health" for language in expected_languages},
        "ROOTLESS_HEALTH_DRIFT",
    )

    web = ui_profiles()
    require(tuple(web) == expected_languages, "WEB_LANGUAGE_DRIFT")
    for language in expected_languages:
        require(web[language]["port"] == TARGET_PROFILES[language]["port"], f"WEB_{language.upper()}_PORT_DRIFT")
        require(web[language]["maturity"] == matrix[language]["maturity"], f"WEB_{language.upper()}_MATURITY_DRIFT")

    image_values = [
        value
        for name, value in vars(container_images).items()
        if name.endswith("_IMAGE") and isinstance(value, str)
    ]
    require(len(image_values) == 12, "CONTAINER_IMAGE_INVENTORY_DRIFT")
    for image in image_values:
        require(
            re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", image) is not None,
            f"CONTAINER_IMAGE_NOT_IMMUTABLE:{image}",
        )
    require(container_images.POSTGRES_IMAGE == rootless.POSTGRES_IMAGE, "POSTGRES_IMAGE_DRIFT")

    skill = (ROOT / ".agents" / "skills" / "elmos-project-synthesis" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    require("built-in engine emits eight exact API starter profiles" in skill, "PROJECT_SKILL_SUPPORT_DRIFT")
    require("bundled-emitter-support.json" in skill, "PROJECT_SKILL_MATRIX_REFERENCE_MISSING")

    print(
        json.dumps(
            {
                "status": "PASSED",
                "profile_count": len(matrix),
                "limited": sorted(limited),
                "experimental": sorted(set(expected_languages) - limited),
                "external_evidence_status": support["external_evidence_status"],
                "certification_status": support["certification_status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MatrixError as error:
        print(json.dumps({"status": "FAILED", "reason": str(error)}, sort_keys=True))
        raise SystemExit(2) from error

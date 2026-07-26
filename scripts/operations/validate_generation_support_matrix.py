#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
ENGINE_SOURCE = ROOT / "engines" / "project-synthesis-engine" / "src"
sys.path.insert(0, str(ENGINE_SOURCE))

from elmos_project_synthesis import container_images  # noqa: E402
from elmos_project_synthesis.models import SUPPORTED_LANGUAGES, TARGET_PROFILES  # noqa: E402


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
    require(support.get("claim_ceiling") == "limited", "CLAIM_CEILING_MUST_BE_LIMITED")
    require(support.get("external_evidence_status") == "NOT_RUN", "EXTERNAL_EVIDENCE_MUST_BE_NOT_RUN")
    require(support.get("certification_status") == "NOT_CERTIFIED", "CERTIFICATION_MUST_BE_NOT_CERTIFIED")

    limited = {"java", "python", "csharp"}
    for language, target in TARGET_PROFILES.items():
        declared = matrix[language]
        for field in ("framework", "runtime", "toolchain"):
            require(declared.get(field) == target[field], f"{language.upper()}_{field.upper()}_DRIFT")
        expected_maturity = "limited" if language in limited else "experimental"
        require(declared.get("maturity") == expected_maturity, f"{language.upper()}_MATURITY_DRIFT")
        evidence = declared.get("required_evidence")
        require(isinstance(evidence, list) and "startup-probe" in evidence, f"{language.upper()}_EVIDENCE_INCOMPLETE")

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

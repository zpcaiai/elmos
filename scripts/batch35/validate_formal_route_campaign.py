#!/usr/bin/env python3
"""Validate a content-addressed aggregate formal campaign for all 30 routes.

The validator checks evidence integrity and proof-graph closure.  It deliberately
allows an honest experimental campaign to contain ``unknown``, ``unsupported``
or ``not-run`` obligations, but derives ``formal_ready=false`` from them.  Such
states can never be relabelled as a proved composition or certification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import jsonschema
except Exception:  # pragma: no cover - exercised through the CLI environment
    jsonschema = None


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts" / "batch29"))

from route_sets import (  # noqa: E402
    CORE_LANGUAGES,
    SPECIALIZED_ROUTE_KEYS,
    split_route_key,
)

LEGACY_LANGUAGES = frozenset(CORE_LANGUAGES)
SPECIALIZED_LANGUAGES = frozenset(
    language
    for route_key in SPECIALIZED_ROUTE_KEYS
    for language in split_route_key(route_key)
)
FORMAL_KINDS = frozenset({"source-lifting", "target-lowering"})
UNRESOLVED_STATUSES = frozenset(
    {"unknown", "timeout", "unsupported", "invalid", "not-run"}
)
PLACEHOLDERS = ("TODO", "NOT_CONFIGURED")
PACKED_REPLAY_SCOPE = "evidence-integrity-and-semantic-closure-only"
SPECIALIZED_INPUT_DOMAIN = "canonical-finite-no-error-input-domain"
PINNED_UV_PATH = Path("/opt/homebrew/Cellar/uv/0.11.16/bin/uv")
PINNED_UV_SHA256 = (
    "sha256:d4182a7bba32f331b2c5a74568cf1c88aa50f31fe643a2c56118c6610db0aff0"
)
PINNED_UV_BYTES = 46_541_136
PINNED_UV_VERSION = "uv 0.11.16 (Homebrew 2026-05-21 aarch64-apple-darwin)"
PACKED_REPLAY_VENV_NAME = ".elmos-packed-replay-venv"
PACKED_REPLAY_COMMAND = [
    "python3",
    "certification/replay/validate_packed_route.py",
    "--route",
    ".",
]
PACKED_REPLAY_COMMAND_V2 = [
    "uv",
    "--project",
    "certification/formal-artifacts/engine-sources/engines/polyglot-route-engine",
    "run",
    "--locked",
    "python",
    "certification/replay/validate_packed_route.py",
    "--route",
    ".",
]
PACKED_REPLAY_FILES = {
    "launcher": {
        "relative": "certification/replay/validate_packed_route.py",
        "source": "scripts/batch35/validate_packed_route.py",
        "role": "replay-tool",
    },
    "validator": {
        "relative": "certification/replay/scripts/batch29/validate_route.py",
        "source": "scripts/batch29/validate_route.py",
        "role": "replay-tool",
    },
    "schema": {
        "relative": (
            "certification/replay/schemas/batch29/"
            "formal-equivalence-evidence.schema.json"
        ),
        "source": "schemas/batch29/formal-equivalence-evidence.schema.json",
        "role": "replay-schema",
    },
}
PACKED_MODULE_REPLAY_FILES = {
    "module_schema": {
        "relative": (
            "certification/replay/schemas/batch29/"
            "module-equivalence-evidence.schema.json"
        ),
        "source": "schemas/batch29/module-equivalence-evidence.schema.json",
        "role": "replay-schema",
    },
    "module_case_schema": {
        "relative": (
            "certification/replay/schemas/batch29/"
            "module-case-manifest.schema.json"
        ),
        "source": "schemas/batch29/module-case-manifest.schema.json",
        "role": "replay-schema",
    },
}


def reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"), parse_constant=reject_non_finite_json
    )
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def pinned_uv_runtime(label: str, errors: list[str]) -> Path | None:
    """Resolve the exact uv binary authorized by this local replay profile."""

    ambient = shutil.which("uv")
    if ambient is None:
        errors.append(f"{label} pinned uv is unavailable")
        return None
    try:
        observed = Path(ambient).resolve(strict=True)
        expected = PINNED_UV_PATH.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        errors.append(f"{label} pinned uv origin cannot be resolved: {exc}")
        return None
    if observed != expected:
        errors.append(f"{label} pinned uv origin mismatch: {observed}")
        return None
    if observed.stat().st_size != PINNED_UV_BYTES:
        errors.append(f"{label} pinned uv byte count mismatch")
        return None
    content_digest = "sha256:" + hashlib.sha256(observed.read_bytes()).hexdigest()
    if content_digest != PINNED_UV_SHA256:
        errors.append(f"{label} pinned uv digest mismatch")
        return None
    clean_environment = {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": str(expected.parent) + os.pathsep + os.defpath,
        "UV_NO_CONFIG": "1",
    }
    try:
        version = subprocess.run(
            [str(expected), "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env=clean_environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"{label} pinned uv version failed: {exc}")
        return None
    if version.returncode != 0 or version.stdout.strip() != PINNED_UV_VERSION:
        errors.append(f"{label} pinned uv version mismatch")
        return None
    return expected


def packed_replay_environment(interpreter: Path, replay_root: Path) -> dict[str, str]:
    """Build an isolated environment for the content-addressed packed replay."""

    resolved_interpreter = interpreter.resolve(strict=True)
    resolved_root = replay_root.resolve(strict=True)
    project_environment = resolved_root / PACKED_REPLAY_VENV_NAME
    try:
        project_environment.resolve(strict=False).relative_to(resolved_root)
    except ValueError as exc:  # pragma: no cover - constant-name defense in depth
        raise ValueError("packed replay project environment escapes replay root") from exc
    if project_environment.exists() or project_environment.is_symlink():
        raise ValueError("packed replay project environment is not fresh")

    environment = {
        key: os.environ[key]
        for key in ("HOME", "TMPDIR", "TZ")
        if key in os.environ
    }
    environment["LANG"] = "C"
    environment["LC_ALL"] = "C"
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PATH"] = (
        str(resolved_interpreter.parent) + os.pathsep + os.defpath
    )
    environment["UV_NO_CONFIG"] = "1"
    environment["UV_PROJECT_ENVIRONMENT"] = str(project_environment)
    return environment


def is_placeholder(value: object) -> bool:
    return (
        not isinstance(value, str)
        or not value.strip()
        or any(token in value for token in PLACEHOLDERS)
    )


def load_batch29_formal_validator() -> Any:
    validator_path = (
        Path(__file__).resolve().parents[1] / "batch29" / "validate_route.py"
    )
    namespace = runpy.run_path(
        str(validator_path), run_name="elmos_batch29_validate_route_for_batch35"
    )
    validator = namespace.get("validate_formal_equivalence")
    if not callable(validator):
        raise RuntimeError("Batch 29 validate_formal_equivalence is unavailable")
    return validator


def load_batch29_packed_module_validator() -> Any:
    validator_path = (
        Path(__file__).resolve().parents[1] / "batch29" / "validate_route.py"
    )
    namespace = runpy.run_path(
        str(validator_path),
        run_name="elmos_batch29_validate_packed_module_for_batch35",
    )
    validator = namespace.get("validate_packed_module_equivalence")
    if not callable(validator):
        raise RuntimeError(
            "Batch 29 validate_packed_module_equivalence is unavailable"
        )
    return validator


def packed_replay_evidence_id(route_key: str, member: str) -> str:
    return f"route-replay-{member}-{route_key}"


def safe_pack_file(
    pack: Path, reference: object, label: str, errors: list[str]
) -> Path | None:
    if (
        not isinstance(reference, str)
        or not reference
        or "\\" in reference
        or "://" in reference
    ):
        errors.append(f"{label} must be a non-empty pack-relative POSIX path")
        return None
    relative = Path(reference)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        errors.append(f"{label} escapes or is not relative to the pack: {reference}")
        return None
    candidate = pack / relative
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError):
        errors.append(f"{label} does not exist: {reference}")
        return None
    try:
        resolved.relative_to(pack)
    except ValueError:
        errors.append(f"{label} escapes the pack: {reference}")
        return None
    if not resolved.is_file():
        errors.append(f"{label} is not a file: {reference}")
        return None
    return resolved


def validate_packed_route_replay(
    *,
    pack: Path,
    route_root: Path,
    route_key: str,
    wrapper: dict[str, Any],
    replay_evidence_ids: object,
    evidence_by_id: dict[str, dict[str, Any]],
    evidence_files: dict[str, Path],
    require_live_source_match: bool,
    errors: list[str],
) -> None:
    """Validate and execute the route-local evidence-only replay launcher."""

    if not isinstance(replay_evidence_ids, list):
        errors.append(f"route {route_key} packed_replay_evidence_ids must be an array")
        return
    replay_specifications = dict(PACKED_REPLAY_FILES)
    expected_command = PACKED_REPLAY_COMMAND
    if require_live_source_match:
        replay_specifications.update(PACKED_MODULE_REPLAY_FILES)
        expected_command = PACKED_REPLAY_COMMAND_V2
    expected_ids = {
        packed_replay_evidence_id(route_key, member)
        for member in replay_specifications
    }
    if set(replay_evidence_ids) != expected_ids or len(replay_evidence_ids) != len(
        replay_specifications
    ):
        errors.append(f"route {route_key} packed replay evidence set is not exact")

    artifact_refs = wrapper.get("artifact_refs")
    if not isinstance(artifact_refs, list):
        errors.append(f"route {route_key} formal artifact_refs must be an array")
        return
    wrapper_by_path: dict[str, dict[str, Any]] = {}
    for reference in artifact_refs:
        if not isinstance(reference, dict):
            continue
        relative = reference.get("path")
        if isinstance(relative, str):
            if relative in wrapper_by_path:
                errors.append(
                    f"route {route_key} duplicate formal artifact path: {relative}"
                )
            wrapper_by_path[relative] = reference

    repo_root = Path(__file__).resolve().parents[2]
    replay_files_valid = True
    for member, specification in replay_specifications.items():
        evidence_id = packed_replay_evidence_id(route_key, member)
        expected_pack_relative = (
            f"evidence/routes/{route_key}/{specification['relative']}"
        )
        evidence = evidence_by_id.get(evidence_id)
        evidence_path = evidence_files.get(evidence_id)
        if evidence is None:
            errors.append(
                f"route {route_key} packed replay {member} evidence is missing"
            )
            replay_files_valid = False
            continue
        if (
            evidence.get("path") != expected_pack_relative
            or evidence.get("role") != specification["role"]
        ):
            errors.append(
                f"route {route_key} packed replay {member} evidence path/role mismatch"
            )
            replay_files_valid = False
        if evidence_path is None:
            replay_files_valid = False
            continue
        if require_live_source_match:
            expected_source = repo_root / specification["source"]
            if not expected_source.is_file():
                errors.append(
                    f"route {route_key} packed replay {member} source is unavailable"
                )
                replay_files_valid = False
            elif evidence_path.read_bytes() != expected_source.read_bytes():
                errors.append(
                    f"route {route_key} packed replay {member} differs from frozen source"
                )
                replay_files_valid = False
        wrapper_reference = wrapper_by_path.get(specification["relative"])
        if (
            wrapper_reference is None
            or wrapper_reference.get("role") != specification["role"]
            or wrapper_reference.get("sha256") != evidence.get("sha256")
            or wrapper_reference.get("bytes") != evidence.get("bytes")
        ):
            errors.append(
                f"route {route_key} packed replay {member} is not wrapper-bound"
            )
            replay_files_valid = False

    replay = wrapper.get("formal_proof", {}).get("replay")
    if not isinstance(replay, dict):
        errors.append(f"route {route_key} packed replay record is missing")
        return
    if replay.get("command") != expected_command:
        errors.append(f"route {route_key} packed replay argv is not canonical")
        replay_files_valid = False
    if replay.get("cwd") != ".":
        errors.append(f"route {route_key} packed replay cwd is not canonical")
        replay_files_valid = False
    if replay.get("expected_exit_code") != 0:
        errors.append(f"route {route_key} packed replay expected exit is nonzero")
        replay_files_valid = False

    if expected_command[0] == "uv":
        pinned_uv = pinned_uv_runtime(f"route {route_key} packed replay", errors)
        interpreter = str(pinned_uv) if pinned_uv is not None else None
        if interpreter is None:
            replay_files_valid = False
    else:
        interpreter = shutil.which(expected_command[0])
        if interpreter is None or not Path(interpreter).is_file():
            errors.append(
                f"route {route_key} packed replay {expected_command[0]} is unavailable"
            )
            replay_files_valid = False
    launcher_token = (
        expected_command[1]
        if expected_command[0] == "python3"
        else expected_command[expected_command.index("python") + 1]
    )
    launcher = route_root / launcher_token
    try:
        launcher_resolved = launcher.resolve(strict=True)
        launcher_resolved.relative_to(route_root.resolve(strict=True))
    except (FileNotFoundError, OSError, ValueError):
        errors.append(
            f"route {route_key} packed replay launcher is dangling or escapes"
        )
        replay_files_valid = False
    route_argument = (
        route_root / expected_command[expected_command.index("--route") + 1]
    ).resolve(strict=False)
    if route_argument != route_root.resolve(strict=True):
        errors.append(f"route {route_key} packed replay --route binding drift")
        replay_files_valid = False

    if not replay_files_valid or interpreter is None:
        return
    try:
        if require_live_source_match:
            with tempfile.TemporaryDirectory(
                prefix=f"elmos-packed-route-{route_key}-"
            ) as temporary:
                replay_root = Path(temporary) / route_key
                shutil.copytree(route_root, replay_root)
                replay_environment = packed_replay_environment(
                    Path(interpreter), replay_root
                )
                execution_command = [
                    str(Path(interpreter).resolve(strict=True)),
                    *expected_command[1:],
                ]
                completed = subprocess.run(
                    execution_command,
                    cwd=replay_root,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=600,
                    env=replay_environment,
                )
                if completed.returncode != 0:
                    diagnostic = (
                        completed.stderr.strip().splitlines()[-1:]
                        or completed.stdout.strip().splitlines()[-1:]
                        or ["unknown packed replay error"]
                    )
                    raise ValueError(diagnostic[0])
                output_lines = completed.stdout.strip().splitlines()
                if not output_lines:
                    raise ValueError("packed replay emitted no JSON result")
                result = json.loads(
                    output_lines[-1], parse_constant=reject_non_finite_json
                )
        else:
            launcher_namespace = runpy.run_path(
                str(launcher_resolved),
                run_name=f"elmos_packed_replay_{route_key.replace('-', '_')}",
            )
            launcher_validator = launcher_namespace.get("validate_packed_route")
            if not callable(launcher_validator):
                raise ValueError("packed replay validate_packed_route is unavailable")
            result = launcher_validator(route_root)
    except Exception as exc:
        errors.append(f"route {route_key} packed replay exited nonzero: {exc}")
        return
    if (
        not isinstance(result, dict)
        or result.get("status") != "PASSED"
        or result.get("route_key") != route_key
        or result.get("scope") != PACKED_REPLAY_SCOPE
        or result.get("native_route_reexecution") != "NOT_RUN"
    ):
        errors.append(f"route {route_key} packed replay output overstates its scope")


def unique_index(
    items: list[dict[str, Any]], key: str, label: str, errors: list[str]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        value = item.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"{label}[{index}] has no {key}")
            continue
        if value in result:
            errors.append(f"duplicate {label} {key}: {value}")
            continue
        result[value] = item
    return result


def expected_routes(campaign: dict[str, Any], errors: list[str]) -> set[str]:
    """Derive the exact route set without inferring a 9 x 8 permutation."""

    if campaign.get("schema_version") == 1:
        if campaign.get("route_policy") is not None or campaign.get(
            "required_route_keys"
        ) is not None:
            errors.append("legacy campaign cannot redefine its exact route policy")
        return {
            f"{source}-to-{target}"
            for source in LEGACY_LANGUAGES
            for target in LEGACY_LANGUAGES
            if source != target
        }
    if campaign.get("schema_version") != 2:
        errors.append("unsupported formal route campaign schema_version")
        return set()
    if campaign.get("route_policy") != "exact-explicit-set":
        errors.append("schema v2 campaign must use exact-explicit-set policy")
    if campaign.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
        errors.append(
            "schema v2 campaign must use canonical-finite-no-error-input-domain"
        )
    declared = campaign.get("required_route_keys")
    if not isinstance(declared, list) or any(
        not isinstance(item, str) or not item for item in declared
    ):
        errors.append("schema v2 required_route_keys must be non-empty strings")
        return set()
    if len(declared) != len(set(declared)):
        errors.append("schema v2 required_route_keys must be unique")
    exact = set(SPECIALIZED_ROUTE_KEYS)
    if set(declared) != exact:
        errors.append(
            "schema v2 required_route_keys must be the exact cpp/objc/swift/java eight-route set"
        )
    return exact


def status_for_composition(obligations: list[dict[str, Any]]) -> str:
    statuses = {item.get("status") for item in obligations}
    if "invalid" in statuses:
        return "invalid"
    if statuses & {"disproved", "failed"}:
        return "disproved"
    if "timeout" in statuses:
        return "timeout"
    if "unknown" in statuses:
        return "unknown"
    if "unsupported" in statuses:
        return "unsupported"
    if "not-run" in statuses:
        return "not-run"
    formal = [item for item in obligations if item.get("kind") in FORMAL_KINDS]
    behavior = [item for item in obligations if item.get("kind") == "route-behavior"]
    if (
        formal
        and behavior
        and all(
            item.get("status") == "proved" and item.get("proof_strength") == "theorem"
            for item in formal
        )
        and all(item.get("status") == "passed" for item in behavior)
    ):
        return "proved"
    return "unknown"


def validate(pack_arg: Path) -> dict[str, Any]:
    errors: list[str] = []
    pack = pack_arg.resolve()
    try:
        pack_manifest = load_json(pack / "pack.json")
    except Exception as exc:
        return {
            "status": "invalid",
            "formal_ready": False,
            "errors": [f"cannot load pack.json: {exc}"],
        }

    declaration = pack_manifest.get("formal_route_campaign")
    campaign_path = safe_pack_file(
        pack, declaration, "pack formal_route_campaign", errors
    )
    if campaign_path is None:
        return {"status": "invalid", "formal_ready": False, "errors": errors}
    try:
        campaign = load_json(campaign_path)
    except Exception as exc:
        return {
            "status": "invalid",
            "formal_ready": False,
            "errors": [*errors, f"cannot load campaign: {exc}"],
        }

    if jsonschema is None:
        errors.append("jsonschema is required for strict formal campaign validation")
    else:
        schema_path = (
            Path(__file__).resolve().parents[2]
            / "schemas"
            / "batch35"
            / "formal-route-campaign.schema.json"
        )
        schema = load_json(schema_path)
        validator = jsonschema.validators.validator_for(schema)(schema)
        for issue in sorted(
            validator.iter_errors(campaign),
            key=lambda item: str(list(item.absolute_path)),
        ):
            location = ".".join(str(part) for part in issue.absolute_path) or "campaign"
            errors.append(f"schema {location}: {issue.message}")
    if errors:
        return {
            "status": "invalid",
            "campaign_key": campaign.get("campaign_key"),
            "formal_ready": False,
            "errors": errors,
        }

    expected_route_keys = expected_routes(campaign, errors)
    required_languages = set(campaign["required_languages"])
    expected_languages = (
        LEGACY_LANGUAGES
        if campaign.get("schema_version") == 1
        else SPECIALIZED_LANGUAGES
    )
    if required_languages != expected_languages:
        errors.append(
            f"required_languages must be exactly {sorted(expected_languages)}"
        )
    semantic_blocks = set(campaign["semantic_blocks"])
    if len(semantic_blocks) != len(campaign["semantic_blocks"]):
        errors.append("semantic_blocks must be unique")

    evidence_by_id = unique_index(
        campaign["evidence"], "evidence_id", "evidence", errors
    )
    evidence_paths: set[str] = set()
    evidence_files: dict[str, Path] = {}
    for evidence_id, evidence in evidence_by_id.items():
        reference = evidence.get("path")
        if isinstance(reference, str) and reference in evidence_paths:
            errors.append(f"duplicate evidence path: {reference}")
        elif isinstance(reference, str):
            evidence_paths.add(reference)
        path = safe_pack_file(pack, reference, f"evidence {evidence_id}", errors)
        if path is None:
            continue
        evidence_files[evidence_id] = path
        content = path.read_bytes()
        actual_digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if evidence.get("sha256") != actual_digest:
            errors.append(f"evidence {evidence_id} sha256 mismatch")
        if evidence.get("bytes") != len(content):
            errors.append(f"evidence {evidence_id} byte count mismatch")

    referenced_evidence: set[str] = set()

    def use_evidence(reference: object, label: str) -> None:
        if not isinstance(reference, str) or reference not in evidence_by_id:
            errors.append(f"{label} references unknown evidence: {reference}")
            return
        referenced_evidence.add(reference)

    def use_evidence_list(references: object, label: str) -> None:
        if not isinstance(references, list):
            errors.append(f"{label} evidence_ids must be an array")
            return
        for reference in references:
            use_evidence(reference, label)

    route_set = campaign["route_set"]
    use_evidence(route_set["manifest_evidence_id"], "route_set manifest")
    route_manifest_evidence = evidence_by_id.get(route_set["manifest_evidence_id"])
    if route_manifest_evidence and route_manifest_evidence.get("role") != "route-set":
        errors.append("route_set manifest evidence must have role route-set")
    route_manifest_path = evidence_files.get(route_set["manifest_evidence_id"])
    if route_manifest_path is not None:
        try:
            route_manifest = load_json(route_manifest_path)
        except Exception as exc:
            errors.append(f"route_set manifest is not valid JSON: {exc}")
        else:
            if route_manifest.get("semantic_profile") != campaign["semantic_profile"]:
                errors.append("route_set manifest semantic_profile mismatch")
            if route_manifest.get("routes") != route_set["routes"]:
                errors.append(
                    "route_set manifest routes do not match the campaign route set"
                )
    routes_by_key = unique_index(route_set["routes"], "route_key", "route", errors)
    actual_route_keys = set(routes_by_key)
    for route_key in sorted(expected_route_keys - actual_route_keys):
        errors.append(f"missing directed route: {route_key}")
    for route_key in sorted(actual_route_keys - expected_route_keys):
        errors.append(f"unexpected directed route: {route_key}")
    try:
        validate_batch29_formal_equivalence = load_batch29_formal_validator()
    except Exception as exc:
        errors.append(f"cannot load Batch 29 formal validator: {exc}")
        validate_batch29_formal_equivalence = None
    try:
        validate_batch29_module_equivalence = load_batch29_packed_module_validator()
    except Exception as exc:
        errors.append(f"cannot load Batch 29 module validator: {exc}")
        validate_batch29_module_equivalence = None
    route_formal_bindings: dict[str, list[str]] = {}
    route_module_bindings: dict[str, list[str]] = {}
    for route_key, route in routes_by_key.items():
        source = route.get("source_language")
        target = route.get("target_language")
        if (
            source not in required_languages
            or target not in required_languages
            or source == target
        ):
            errors.append(
                f"route {route_key} has invalid language tuple {source}->{target}"
            )
        elif route_key != f"{source}-to-{target}":
            errors.append(f"route {route_key} does not match {source}->{target}")
        if route.get("semantic_profile") != campaign["semantic_profile"]:
            errors.append(f"route {route_key} semantic_profile mismatch")
        route_evidence_ids = route.get("artifact_evidence_ids")
        use_evidence_list(route_evidence_ids, f"route {route_key}")
        replay_evidence_ids = route.get("packed_replay_evidence_ids")
        use_evidence_list(replay_evidence_ids, f"route {route_key} packed replay")
        formal_evidence_ids = [
            evidence_id
            for evidence_id in route_evidence_ids
            if evidence_id in evidence_by_id
            and evidence_by_id[evidence_id].get("role") == "route-formal-evidence"
        ]
        if len(formal_evidence_ids) != 1:
            errors.append(
                f"route {route_key} must bind exactly one route-formal-evidence"
            )
            continue
        formal_evidence_id = formal_evidence_ids[0]
        route_formal_bindings.setdefault(formal_evidence_id, []).append(route_key)
        expected_wrapper_relative = (
            f"evidence/routes/{route_key}/certification/formal-equivalence.json"
        )
        formal_evidence = evidence_by_id[formal_evidence_id]
        if formal_evidence.get("path") != expected_wrapper_relative:
            errors.append(
                f"route {route_key} route-formal-evidence path does not preserve route-relative hierarchy"
            )
        module_evidence_id = route.get("module_evidence_id")
        if campaign.get("schema_version") == 2:
            use_evidence(module_evidence_id, f"route {route_key} module")
            module_evidence = evidence_by_id.get(module_evidence_id)
            expected_module_relative = (
                f"evidence/routes/{route_key}/certification/module-equivalence.json"
            )
            if (
                module_evidence is None
                or module_evidence.get("role") != "route-module-evidence"
                or module_evidence.get("path") != expected_module_relative
            ):
                errors.append(
                    f"route {route_key} module evidence path/role mismatch"
                )
            elif isinstance(module_evidence_id, str):
                route_module_bindings.setdefault(module_evidence_id, []).append(
                    route_key
                )

        route_root_relative = f"evidence/routes/{route_key}"
        route_root = pack / route_root_relative
        route_manifest_path = safe_pack_file(
            pack,
            f"{route_root_relative}/route.json",
            f"route {route_key} copied route manifest",
            errors,
        )
        profile_path = safe_pack_file(
            pack,
            f"{route_root_relative}/lowering/profile.json",
            f"route {route_key} copied semantic profile",
            errors,
        )
        certification_path = safe_pack_file(
            pack,
            f"{route_root_relative}/certification/certification.json",
            f"route {route_key} copied certification wrapper",
            errors,
        )
        wrapper_path = evidence_files.get(formal_evidence_id)
        if wrapper_path is None:
            continue
        try:
            wrapper_path.relative_to(route_root.resolve(strict=True))
        except (FileNotFoundError, OSError, ValueError):
            errors.append(f"route {route_key} formal wrapper escapes its route bundle")
            continue
        if (
            route_manifest_path is None
            or profile_path is None
            or certification_path is None
        ):
            continue
        try:
            copied_manifest = load_json(route_manifest_path)
            copied_profile = load_json(profile_path)
            copied_certification = load_json(certification_path)
            copied_formal = load_json(wrapper_path)
        except Exception as exc:
            errors.append(f"route {route_key} copied route metadata is invalid: {exc}")
            continue
        if copied_manifest.get("route_key") != route_key:
            errors.append(f"route {route_key} copied route.json route_key mismatch")
        if copied_manifest.get("version") != route.get("route_version"):
            errors.append(f"route {route_key} copied route version mismatch")
        if copied_manifest.get("source", {}).get("language") != source:
            errors.append(f"route {route_key} copied source language mismatch")
        if copied_manifest.get("target", {}).get("language") != target:
            errors.append(f"route {route_key} copied target language mismatch")
        copied_semantic_profile = copied_manifest.get("profiles", {}).get(
            "semantic_profile"
        )
        if copied_semantic_profile != campaign["semantic_profile"]:
            errors.append(f"route {route_key} copied route semantic_profile mismatch")
        if copied_profile.get("profile") != campaign["semantic_profile"]:
            errors.append(f"route {route_key} copied profile identity mismatch")
        if copied_certification.get("route_key") != route_key:
            errors.append(f"route {route_key} copied certification route_key mismatch")
        if copied_certification.get("route_version") != route.get("route_version"):
            errors.append(f"route {route_key} copied certification version mismatch")
        expected_declared_scope = (
            campaign["semantic_profile"]
            if campaign.get("schema_version") == 1
            else f"{campaign['semantic_profile']}+typed-pure-module-v1"
        )
        if copied_certification.get("declared_scope") != expected_declared_scope:
            errors.append(f"route {route_key} copied certification scope mismatch")
        formal_reference = copied_certification.get("formal_equivalence")
        if (
            not isinstance(formal_reference, dict)
            or formal_reference.get("path") != "certification/formal-equivalence.json"
        ):
            errors.append(f"route {route_key} certification formal reference mismatch")
        if campaign.get("schema_version") == 2:
            module_reference = copied_certification.get("module_equivalence")
            if (
                not isinstance(module_reference, dict)
                or module_reference.get("path")
                != "certification/module-equivalence.json"
            ):
                errors.append(
                    f"route {route_key} certification module reference mismatch"
                )
        validate_packed_route_replay(
            pack=pack,
            route_root=route_root,
            route_key=route_key,
            wrapper=copied_formal,
            replay_evidence_ids=replay_evidence_ids,
            evidence_by_id=evidence_by_id,
            evidence_files=evidence_files,
            require_live_source_match=campaign.get("schema_version") == 2,
            errors=errors,
        )
        if validate_batch29_formal_equivalence is not None:
            try:
                validated_wrapper, batch29_errors = validate_batch29_formal_equivalence(
                    route_root, copied_manifest, copied_certification
                )
            except Exception as exc:
                errors.append(
                    f"route {route_key} Batch 29 formal validation crashed: {exc}"
                )
            else:
                if validated_wrapper is None:
                    errors.append(
                        f"route {route_key} Batch 29 formal validator returned no wrapper"
                    )
                errors.extend(
                    f"route {route_key} Batch 29 formal evidence: {error}"
                    for error in batch29_errors
                )
        if (
            campaign.get("schema_version") == 2
            and validate_batch29_module_equivalence is not None
        ):
            try:
                validated_module, module_errors = validate_batch29_module_equivalence(
                    route_root,
                    copied_manifest,
                    copied_certification,
                )
            except Exception as exc:
                errors.append(
                    f"route {route_key} Batch 29 module validation crashed: {exc}"
                )
            else:
                if validated_module is None:
                    errors.append(
                        f"route {route_key} Batch 29 module validator returned no report"
                    )
                errors.extend(
                    f"route {route_key} Batch 29 module evidence: {error}"
                    for error in module_errors
                )

    for evidence_id, evidence in evidence_by_id.items():
        if evidence.get("role") == "route-formal-evidence":
            bindings = route_formal_bindings.get(evidence_id, [])
            if len(bindings) != 1:
                errors.append(
                    f"route-formal-evidence {evidence_id} must bind exactly one route"
                )
        elif evidence.get("role") == "route-module-evidence":
            module_bindings = route_module_bindings.get(evidence_id, [])
            if len(module_bindings) != 1:
                errors.append(
                    f"route-module-evidence {evidence_id} must bind exactly one route"
                )

    try:
        profile = load_json(pack / "validation-profile.json")
    except Exception as exc:
        errors.append(f"cannot load validation-profile.json: {exc}")
        profile = {"claims": []}
    profile_claims = [
        item for item in profile.get("claims", []) if isinstance(item, dict)
    ]
    claims = unique_index(
        profile_claims, "claim_id", "validation profile claim", errors
    )
    properties: dict[str, dict[str, Any]] = {}
    property_dir = pack / "properties"
    property_schema = load_json(
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "batch35"
        / "property-spec.schema.json"
    )
    property_validator = jsonschema.validators.validator_for(property_schema)(
        property_schema
    )
    for property_path in (
        sorted(property_dir.rglob("*.json")) if property_dir.is_dir() else []
    ):
        try:
            item = load_json(property_path)
        except Exception as exc:
            errors.append(
                f"cannot load property spec {property_path.relative_to(pack)}: {exc}"
            )
            continue
        for issue in property_validator.iter_errors(item):
            errors.append(
                f"property spec {property_path.relative_to(pack)}: {issue.message}"
            )
        property_id = item.get("property_id")
        if not isinstance(property_id, str) or not property_id:
            errors.append(
                f"property spec {property_path.relative_to(pack)} has no property_id"
            )
        elif property_id in properties:
            errors.append(f"duplicate property_id: {property_id}")
        else:
            properties[property_id] = item

    obligations_by_id = unique_index(
        campaign["obligations"], "obligation_id", "obligation", errors
    )
    source_by_key: dict[tuple[str, str], str] = {}
    target_by_key: dict[tuple[str, str], str] = {}
    behavior_by_key: dict[tuple[str, str], str] = {}
    for obligation_id, obligation in obligations_by_id.items():
        kind = obligation.get("kind")
        block = obligation.get("semantic_block")
        status = obligation.get("status")
        strength = obligation.get("proof_strength")
        method = obligation.get("method")
        if block not in semantic_blocks:
            errors.append(
                f"obligation {obligation_id} has unknown semantic_block: {block}"
            )
        if obligation.get("required") is not True:
            errors.append(f"obligation {obligation_id} must be explicitly required")
        claim_id = obligation.get("claim_id")
        property_id = obligation.get("property_id")
        if claim_id not in claims:
            errors.append(
                f"obligation {obligation_id} references unknown claim: {claim_id}"
            )
        elif "formal-route-campaign" not in claims[claim_id].get(
            "required_techniques", []
        ):
            errors.append(
                f"obligation {obligation_id} claim {claim_id} does not require formal-route-campaign"
            )
        property_spec = properties.get(property_id)
        if property_spec is None:
            errors.append(
                f"obligation {obligation_id} references unknown property: {property_id}"
            )
        elif property_spec.get("claim_id") != claim_id:
            errors.append(
                f"obligation {obligation_id} property/claim association mismatch"
            )
        use_evidence_list(obligation.get("evidence_ids"), f"obligation {obligation_id}")

        assumption_ids: set[str] = set()
        assumptions = obligation.get("assumptions", [])
        for assumption in assumptions:
            assumption_id = assumption.get("assumption_id")
            if assumption_id in assumption_ids:
                errors.append(
                    f"obligation {obligation_id} has duplicate assumption {assumption_id}"
                )
            assumption_ids.add(assumption_id)
            if is_placeholder(assumption.get("statement")):
                errors.append(
                    f"obligation {obligation_id} has placeholder assumption {assumption_id}"
                )
            use_evidence_list(
                assumption.get("evidence_ids"), f"assumption {assumption_id}"
            )
            if assumption.get("status") == "discharged" and not assumption.get(
                "evidence_ids"
            ):
                errors.append(f"discharged assumption {assumption_id} has no evidence")
            if status == "proved" and assumption.get("status") in {
                "unverified",
                "rejected",
            }:
                errors.append(
                    f"proved obligation {obligation_id} has unresolved assumption {assumption_id}"
                )

        if kind == "source-lifting":
            language = obligation.get("source_language")
            key = (language, block)
            if language not in required_languages:
                errors.append(
                    f"source obligation {obligation_id} has invalid language: {language}"
                )
            if not assumptions:
                errors.append(
                    f"source obligation {obligation_id} must declare lifting assumptions"
                )
            if key in source_by_key:
                errors.append(
                    f"duplicate source lifting obligation for {language}/{block}"
                )
            source_by_key[key] = obligation_id
        elif kind == "target-lowering":
            language = obligation.get("target_language")
            key = (language, block)
            if language not in required_languages:
                errors.append(
                    f"target obligation {obligation_id} has invalid language: {language}"
                )
            if key in target_by_key:
                errors.append(
                    f"duplicate target lowering obligation for {language}/{block}"
                )
            target_by_key[key] = obligation_id
        elif kind == "route-behavior":
            route_key = obligation.get("route_key")
            key = (route_key, block)
            if route_key not in routes_by_key:
                errors.append(
                    f"behavior obligation {obligation_id} has unknown route: {route_key}"
                )
            if key in behavior_by_key:
                errors.append(f"duplicate behavior obligation for {route_key}/{block}")
            behavior_by_key[key] = obligation_id

        if kind in FORMAL_KINDS:
            if status == "passed":
                errors.append(
                    f"formal obligation {obligation_id} cannot use testing status passed"
                )
            if status == "proved":
                if strength != "theorem":
                    errors.append(
                        f"proved obligation {obligation_id} must have theorem strength"
                    )
                if method not in {"smt", "proof-certificate"}:
                    errors.append(
                        f"proved obligation {obligation_id} uses non-proof method {method}"
                    )
                if not obligation.get("evidence_ids"):
                    errors.append(f"proved obligation {obligation_id} has no evidence")
            if method == "language-standard-axiom" or strength == "axiom":
                if method != "language-standard-axiom" or strength != "axiom":
                    errors.append(
                        f"axiom obligation {obligation_id} has inconsistent method/strength"
                    )
                if status == "proved":
                    errors.append(
                        f"axiom obligation {obligation_id} cannot masquerade as proved"
                    )
                if not obligation.get("evidence_ids"):
                    errors.append(
                        f"axiom obligation {obligation_id} must retain citation evidence"
                    )
            if method == "bounded-model" or strength == "bounded":
                if method != "bounded-model" or strength != "bounded":
                    errors.append(
                        f"bounded obligation {obligation_id} has inconsistent method/strength"
                    )
                if status == "proved":
                    errors.append(
                        f"bounded obligation {obligation_id} cannot masquerade as a theorem"
                    )
            if method == "not-run" and status != "not-run":
                errors.append(f"not-run obligation {obligation_id} has status {status}")
            if status == "not-run" and method != "not-run":
                errors.append(
                    f"obligation {obligation_id} is not-run but method is {method}"
                )
        elif kind == "route-behavior":
            if status not in {"passed", "failed", "not-run"}:
                errors.append(
                    f"behavior obligation {obligation_id} has invalid status {status}"
                )
            if status == "passed" and (
                method != "differential-execution" or strength != "testing"
            ):
                errors.append(
                    f"passed behavior obligation {obligation_id} must be differential testing"
                )
            if status == "passed" and not obligation.get("evidence_ids"):
                errors.append(
                    f"passed behavior obligation {obligation_id} has no evidence"
                )

    for language in sorted(required_languages):
        for block in sorted(semantic_blocks):
            if (language, block) not in source_by_key:
                errors.append(
                    f"missing source lifting obligation for {language}/{block}"
                )
            if (language, block) not in target_by_key:
                errors.append(
                    f"missing target lowering obligation for {language}/{block}"
                )
    for route_key in sorted(expected_route_keys):
        for block in sorted(semantic_blocks):
            if (route_key, block) not in behavior_by_key:
                errors.append(f"missing behavior obligation for {route_key}/{block}")

    solver_runs_by_id = unique_index(
        campaign["solver_runs"], "run_id", "solver run", errors
    )
    for run_id, run in solver_runs_by_id.items():
        solver = run["solver"]
        if is_placeholder(solver.get("name")) or is_placeholder(solver.get("version")):
            errors.append(f"solver run {run_id} has placeholder solver identity")
        binary_evidence_id = solver.get("binary_evidence_id")
        use_evidence(binary_evidence_id, f"solver run {run_id} binary")
        binary_evidence = evidence_by_id.get(binary_evidence_id)
        if binary_evidence and binary_evidence.get("sha256") != solver.get(
            "binary_digest"
        ):
            errors.append(f"solver run {run_id} binary digest does not match evidence")
        if binary_evidence and binary_evidence.get("role") != "artifact":
            errors.append(
                f"solver run {run_id} binary evidence must have role artifact"
            )
        input_evidence_id = run.get("input_evidence_id")
        output_evidence_id = run.get("output_evidence_id")
        use_evidence(input_evidence_id, f"solver run {run_id} input")
        use_evidence(output_evidence_id, f"solver run {run_id} output")
        if (
            input_evidence_id in evidence_by_id
            and evidence_by_id[input_evidence_id].get("role") != "solver-input"
        ):
            errors.append(f"solver run {run_id} input evidence has the wrong role")
        if (
            output_evidence_id in evidence_by_id
            and evidence_by_id[output_evidence_id].get("role") != "solver-output"
        ):
            errors.append(f"solver run {run_id} output evidence has the wrong role")
        if run.get("proof_evidence_id") is not None:
            use_evidence(run.get("proof_evidence_id"), f"solver run {run_id} proof")
            proof_evidence = evidence_by_id.get(run.get("proof_evidence_id"))
            if proof_evidence and proof_evidence.get("role") != "proof-certificate":
                errors.append(f"solver run {run_id} proof evidence has the wrong role")
        if run.get("model_evidence_id") is not None:
            use_evidence(run.get("model_evidence_id"), f"solver run {run_id} model")
            model_evidence = evidence_by_id.get(run.get("model_evidence_id"))
            if model_evidence and model_evidence.get("role") != "countermodel":
                errors.append(f"solver run {run_id} model evidence has the wrong role")
        if run.get("result") == "sat" and not run.get("model_evidence_id"):
            errors.append(f"SAT solver run {run_id} has no countermodel evidence")
        for obligation_id in run.get("obligation_ids", []):
            obligation = obligations_by_id.get(obligation_id)
            if obligation is None:
                errors.append(
                    f"solver run {run_id} references unknown obligation {obligation_id}"
                )
            elif obligation.get("solver_run_id") != run_id:
                errors.append(
                    f"solver run {run_id} lacks reciprocal link from {obligation_id}"
                )

    result_for_status = {
        "proved": "unsat",
        "disproved": "sat",
        "unknown": "unknown",
        "timeout": "timeout",
        "unsupported": "unsupported",
        "invalid": "error",
        "not-run": "not-run",
    }
    for obligation_id, obligation in obligations_by_id.items():
        run_id = obligation.get("solver_run_id")
        method = obligation.get("method")
        status = obligation.get("status")
        if method in {"smt", "bounded-model"}:
            run = solver_runs_by_id.get(run_id)
            if run is None:
                errors.append(
                    f"solver-backed obligation {obligation_id} has no valid solver run"
                )
                continue
            if obligation_id not in run.get("obligation_ids", []):
                errors.append(
                    f"obligation {obligation_id} missing from solver run {run_id}"
                )
            expected_result = result_for_status.get(status)
            if method == "bounded-model" and status == "unknown":
                expected_result = "unsat"
            if expected_result is not None and run.get("result") != expected_result:
                errors.append(
                    f"obligation {obligation_id} status {status} conflicts with solver result {run.get('result')}"
                )
        elif run_id is not None:
            errors.append(
                f"non-solver obligation {obligation_id} unexpectedly references solver run {run_id}"
            )
        if method == "proof-certificate":
            roles = {
                evidence_by_id[item].get("role")
                for item in obligation.get("evidence_ids", [])
                if item in evidence_by_id
            }
            if "proof-certificate" not in roles:
                errors.append(
                    f"proof-certificate obligation {obligation_id} lacks certificate evidence"
                )

    replays_by_id = unique_index(campaign["replays"], "replay_id", "replay", errors)
    for replay_id, replay in replays_by_id.items():
        obligation_id = replay.get("obligation_id")
        obligation = obligations_by_id.get(obligation_id)
        if obligation is None:
            errors.append(
                f"replay {replay_id} references unknown obligation {obligation_id}"
            )
        elif obligation.get("replay_id") != replay_id:
            errors.append(
                f"replay {replay_id} lacks reciprocal link from {obligation_id}"
            )
        use_evidence(replay.get("manifest_evidence_id"), f"replay {replay_id} manifest")
        manifest_evidence = evidence_by_id.get(replay.get("manifest_evidence_id"))
        if manifest_evidence and manifest_evidence.get("role") != "replay-manifest":
            errors.append(f"replay {replay_id} manifest evidence has the wrong role")
        manifest_path = evidence_files.get(replay.get("manifest_evidence_id"))
        if manifest_path is not None:
            try:
                replay_manifest = load_json(manifest_path)
            except Exception as exc:
                errors.append(f"replay {replay_id} manifest is not valid JSON: {exc}")
            else:
                if replay_manifest.get("expected_fingerprint") != replay.get(
                    "expected_fingerprint"
                ):
                    errors.append(
                        f"replay {replay_id} expected fingerprint is not manifest-bound"
                    )
        use_evidence_list(replay.get("evidence_ids"), f"replay {replay_id}")
        replay_outputs = [
            evidence_by_id[item]
            for item in replay.get("evidence_ids", [])
            if item in evidence_by_id
            and evidence_by_id[item].get("role") == "replay-output"
        ]
        if len(replay_outputs) != 1:
            errors.append(
                f"replay {replay_id} must reference exactly one replay-output"
            )
        elif replay.get("observed_fingerprint") != replay_outputs[0].get("sha256"):
            errors.append(
                f"replay {replay_id} observed fingerprint is not output-bound"
            )
        if replay.get("status") == "passed" and replay.get(
            "expected_fingerprint"
        ) != replay.get("observed_fingerprint"):
            errors.append(f"replay {replay_id} fingerprint drift")
        if (
            replay.get("status") == "not-run"
            and replay.get("observed_fingerprint") is not None
        ):
            errors.append(f"not-run replay {replay_id} has an observed fingerprint")
    for obligation_id, obligation in obligations_by_id.items():
        replay_id = obligation.get("replay_id")
        if replay_id is not None:
            replay = replays_by_id.get(replay_id)
            if replay is None:
                errors.append(
                    f"obligation {obligation_id} references unknown replay {replay_id}"
                )
            elif replay.get("obligation_id") != obligation_id:
                errors.append(
                    f"obligation {obligation_id} replay points to another obligation"
                )
        if obligation.get("status") in {"disproved", "failed"}:
            replay = replays_by_id.get(replay_id)
            if replay is None or replay.get("status") != "passed":
                errors.append(
                    f"failed obligation {obligation_id} lacks a passing concrete replay"
                )

    compositions_by_id = unique_index(
        campaign["compositions"], "composition_id", "composition", errors
    )
    composition_by_route: dict[str, dict[str, Any]] = {}
    for composition_id, composition in compositions_by_id.items():
        route_key = composition.get("route_key")
        if route_key in composition_by_route:
            errors.append(f"duplicate composition for route {route_key}")
        composition_by_route[route_key] = composition
        route = routes_by_key.get(route_key)
        if route is None:
            errors.append(
                f"composition {composition_id} references unknown route {route_key}"
            )
        elif route.get("composition_id") != composition_id:
            errors.append(
                f"route {route_key} and composition {composition_id} are not reciprocal"
            )

    matrix_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for index, row in enumerate(campaign["obligation_matrix"]):
        key = (row.get("route_key"), row.get("semantic_block"))
        if key in matrix_by_key:
            errors.append(f"duplicate obligation_matrix row for {key[0]}/{key[1]}")
        matrix_by_key[key] = row
        route = routes_by_key.get(key[0])
        if route is None or key[1] not in semantic_blocks:
            errors.append(
                f"obligation_matrix[{index}] has unknown route/block {key[0]}/{key[1]}"
            )
            continue
        expected_source = source_by_key.get((route["source_language"], key[1]))
        expected_target = target_by_key.get((route["target_language"], key[1]))
        expected_behavior = behavior_by_key.get(key)
        expected_composition = route.get("composition_id")
        checks = {
            "source_lifting_obligation_id": expected_source,
            "target_lowering_obligation_id": expected_target,
            "behavior_obligation_id": expected_behavior,
            "composition_id": expected_composition,
        }
        for field, expected in checks.items():
            if row.get(field) != expected:
                errors.append(
                    f"obligation_matrix {key[0]}/{key[1]} {field} does not close"
                )

    for route_key in sorted(expected_route_keys):
        route = routes_by_key.get(route_key)
        composition = composition_by_route.get(route_key)
        if route is None or composition is None:
            if composition is None:
                errors.append(f"missing composition for route {route_key}")
            continue
        expected_source_ids: set[str] = set()
        expected_target_ids: set[str] = set()
        expected_behavior_ids: set[str] = set()
        for block in semantic_blocks:
            row = matrix_by_key.get((route_key, block))
            if row is None:
                errors.append(f"missing obligation_matrix row for {route_key}/{block}")
                continue
            expected_source_ids.add(row["source_lifting_obligation_id"])
            expected_target_ids.add(row["target_lowering_obligation_id"])
            expected_behavior_ids.add(row["behavior_obligation_id"])
        declared_sets = {
            "source_lifting_obligation_ids": expected_source_ids,
            "target_lowering_obligation_ids": expected_target_ids,
            "behavior_obligation_ids": expected_behavior_ids,
        }
        for field, expected in declared_sets.items():
            if set(composition.get(field, [])) != expected:
                errors.append(
                    f"composition {composition['composition_id']} {field} is not matrix-complete"
                )
        members = [
            obligations_by_id[item]
            for field in declared_sets
            for item in composition.get(field, [])
            if item in obligations_by_id
        ]
        derived_status = status_for_composition(members)
        if composition.get("status") != derived_status:
            errors.append(
                f"composition {composition['composition_id']} claims {composition.get('status')} but derives {derived_status}"
            )

    extra_matrix = set(matrix_by_key) - {
        (route_key, block)
        for route_key in expected_route_keys
        for block in semantic_blocks
    }
    for route_key, block in sorted(extra_matrix):
        errors.append(f"unexpected obligation_matrix row for {route_key}/{block}")

    independent = campaign["independent_verification"]
    independent_status = independent["status"]
    use_evidence_list(independent.get("evidence_ids"), "independent verification")
    verifier = independent.get("verifier")
    if independent_status == "NOT_RUN":
        if verifier not in (None, "") or independent.get("evidence_ids"):
            errors.append(
                "independent verification NOT_RUN cannot name a verifier or evidence"
            )
        if campaign.get("certification_status") != "NOT_CERTIFIED":
            errors.append("independent verification NOT_RUN cannot be certified")
    elif independent_status == "PASSED":
        if is_placeholder(verifier) or not independent.get("evidence_ids"):
            errors.append(
                "passed independent verification requires a verifier and evidence"
            )
        if verifier in {
            pack_manifest.get("owner"),
            pack_manifest.get("maintenance_owner"),
        }:
            errors.append(
                "independent verifier must differ from pack owner and maintenance owner"
            )
        review_records = []
        for evidence_id in independent.get("evidence_ids", []):
            evidence = evidence_by_id.get(evidence_id)
            if evidence and evidence.get("role") != "independent-review":
                errors.append(
                    f"independent verification evidence {evidence_id} has the wrong role"
                )
            review_path = evidence_files.get(evidence_id)
            if review_path is not None:
                try:
                    review_records.append(load_json(review_path))
                except Exception as exc:
                    errors.append(
                        f"independent verification evidence {evidence_id} is not valid JSON: {exc}"
                    )
        if not any(
            record.get("status") == "PASSED" and record.get("verifier") == verifier
            for record in review_records
        ):
            errors.append(
                "independent verification lacks a manifest bound to the named verifier"
            )

    composition_statuses = [item.get("status") for item in compositions_by_id.values()]
    formal_ready = (
        len(compositions_by_id) == len(expected_route_keys)
        and set(composition_by_route) == expected_route_keys
        and bool(composition_statuses)
        and all(status == "proved" for status in composition_statuses)
    )
    certification_ready = formal_ready and independent_status == "PASSED"
    if campaign.get("certification_status") == "CERTIFIED" and not certification_ready:
        errors.append(
            "campaign cannot be CERTIFIED without all proved compositions and independent verification"
        )
    try:
        certification = load_json(pack / "certification" / "certification.json")
    except Exception as exc:
        errors.append(f"cannot load certification/certification.json: {exc}")
        certification = {}
    if independent_status == "NOT_RUN" and (
        pack_manifest.get("status") == "certified"
        or certification.get("status") == "certified"
    ):
        errors.append(
            "pack cannot request certification while independent formal verification is NOT_RUN"
        )

    unreferenced = set(evidence_by_id) - referenced_evidence
    for evidence_id in sorted(unreferenced):
        errors.append(f"unreferenced evidence entry: {evidence_id}")

    unresolved = sorted(
        obligation_id
        for obligation_id, obligation in obligations_by_id.items()
        if obligation.get("required") is True
        and obligation.get("status") in UNRESOLVED_STATUSES
    )
    return {
        "status": "invalid" if errors else "valid",
        "campaign_key": campaign.get("campaign_key"),
        "formal_ready": formal_ready and not errors,
        "certification_ready": certification_ready and not errors,
        "independent_verification_status": independent_status,
        "route_count": len(routes_by_key),
        "semantic_block_count": len(semantic_blocks),
        "required_obligation_count": sum(
            1
            for obligation in obligations_by_id.values()
            if obligation.get("required") is True
        ),
        "unresolved_required_obligation_ids": unresolved,
        "composition_count": len(compositions_by_id),
        "proved_composition_count": sum(
            1 for status in composition_statuses if status == "proved"
        ),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    result = validate(args.pack)
    if args.as_json:
        print(json.dumps(result, sort_keys=True))
    elif result["status"] == "valid":
        print(
            "OK: formal route campaign "
            f"{result.get('campaign_key')} routes={result.get('route_count')} "
            f"formal_ready={str(result.get('formal_ready')).lower()}"
        )
    else:
        print(
            "\n".join(f"ERROR: {error}" for error in result["errors"]), file=sys.stderr
        )
    return 0 if result["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())

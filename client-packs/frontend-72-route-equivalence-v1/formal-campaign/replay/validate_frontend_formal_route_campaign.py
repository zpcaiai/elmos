#!/usr/bin/env python3
"""Strict validator for the exact nine-profile, 72-route frontend campaign.

This validator is deliberately independent from the six-language Batch 29/35
campaign.  It validates byte-addressed evidence, semantic/chunk pointers,
behavior-oracle independence, solver linkage, replay closure, and the exact
frontend project-profile matrix.  Honest model-only and proof-under-assumption
results are valid experimental evidence, but cannot become certification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import jsonschema
except Exception:  # pragma: no cover - reported fail-closed by the CLI
    jsonschema = None


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
CORPUS_KINDS = (
    "development",
    "negative",
    "holdout",
    "representative_workloads",
)
PROOF_PASSING = frozenset({"PROVED", "PROVED_UNDER_ASSUMPTIONS"})
NON_PROOF = frozenset(
    {"UNKNOWN", "TIMEOUT", "NOT_RUN", "AXIOM", "BOUNDED", "NOT_PROVED"}
)
SOLVER_TO_FORMAL = {
    "SAT": "REFUTED",
    "UNKNOWN": "UNKNOWN",
    "TIMEOUT": "TIMEOUT",
    "NOT_RUN": "NOT_RUN",
    "ERROR": "NOT_PROVED",
}
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
SOLVER_REPLAY_CACHE: dict[tuple[str, str], tuple[int, bytes, bytes]] = {}
REQUIRED_IMPLEMENTATION_REPOSITORY_PATHS = frozenset(
    {
        "engines/frontend-client-engine/src/frontend-formal-equivalence.ts",
        "engines/frontend-client-engine/src/frontend-formal-cli.ts",
        "engines/frontend-client-engine/src/bounded-navigation-source.ts",
        "engines/frontend-client-engine/src/project-generation.ts",
        "engines/frontend-client-engine/src/project-profiles.ts",
        "engines/frontend-client-engine/src/project-templates.ts",
        "engines/frontend-client-engine/src/project-types.ts",
        "engines/frontend-client-engine/test/frontend-formal-equivalence.test.ts",
        "engines/frontend-client-engine/package.json",
        "engines/frontend-client-engine/pnpm-lock.yaml",
        "engines/frontend-client-engine/tsconfig.json",
        "tooling/run_frontend_formal_toolchains.py",
        "tooling/generate_frontend_formal_verification_pack.py",
        "scripts/batch32/run_client_gate.py",
        "scripts/batch35/run_verification_gate.py",
        "scripts/batch35/validate_frontend_formal_route_campaign.py",
    }
)
REQUIRED_REPLAY_REPOSITORY_PATHS = frozenset(
    {
        "scripts/batch32/validate_frontend_formal_route_campaign.py",
        "schemas/batch32/frontend-formal-route-campaign.schema.json",
        "schemas/batch32/frontend-formal-route-evidence.schema.json",
    }
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


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


def safe_pack_file(
    pack: Path,
    reference: object,
    label: str,
    errors: list[str],
) -> Path | None:
    if (
        not isinstance(reference, str)
        or not reference
        or reference.startswith("/")
        or "\\" in reference
        or "://" in reference
    ):
        errors.append(f"{label} must be a non-empty pack-relative POSIX path")
        return None
    relative = Path(reference)
    if any(part in {"", ".", ".."} for part in relative.parts):
        errors.append(f"{label} escapes or is not relative to the pack: {reference}")
        return None
    candidate = pack / relative
    current = pack
    try:
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                errors.append(f"{label} must not traverse a symlink: {reference}")
                return None
        pack_resolved = pack.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(pack_resolved)
    except (FileNotFoundError, OSError, ValueError):
        errors.append(f"{label} is missing or escapes the pack: {reference}")
        return None
    if not resolved.is_file():
        errors.append(f"{label} is not a regular file: {reference}")
        return None
    return resolved


def json_pointer(value: object, pointer: str) -> object:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise ValueError("pointer is not RFC6901")
    current: object = value
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if "~" in raw.replace("~0", "").replace("~1", ""):
            raise ValueError("pointer contains an invalid escape")
        if isinstance(current, dict):
            if token not in current:
                raise ValueError(f"pointer token does not exist: {token}")
            current = current[token]
        elif isinstance(current, list):
            if token == "-" or not token.isdigit():
                raise ValueError(f"pointer array token is invalid: {token}")
            index = int(token)
            if index >= len(current):
                raise ValueError(f"pointer array index is out of range: {index}")
            current = current[index]
        else:
            raise ValueError(f"pointer traverses a scalar at: {token}")
    return current


def pointer_tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError("pointer is not RFC6901")
    result: list[str] = []
    for raw in pointer[1:].split("/"):
        if "~" in raw.replace("~0", "").replace("~1", ""):
            raise ValueError("pointer contains an invalid escape")
        result.append(raw.replace("~1", "/").replace("~0", "~"))
    return result


def canonical_pointer_span(
    value: object, tokens: list[str], offset: int = 0
) -> tuple[int, int]:
    """Return the exact byte span in ``canonical_bytes(value)`` for tokens."""

    if not tokens:
        encoded = canonical_bytes(value)
        return offset, offset + len(encoded)
    token, remaining = tokens[0], tokens[1:]
    if isinstance(value, dict):
        cursor = offset + 1
        for index, key in enumerate(sorted(value)):
            if index:
                cursor += 1
            encoded_key = canonical_bytes(key)
            cursor += len(encoded_key) + 1
            child = value[key]
            if key == token:
                return canonical_pointer_span(child, remaining, cursor)
            cursor += len(canonical_bytes(child))
        raise ValueError(f"pointer token does not exist: {token}")
    if isinstance(value, list):
        if not token.isdigit():
            raise ValueError(f"pointer array token is invalid: {token}")
        wanted = int(token)
        if wanted >= len(value):
            raise ValueError(f"pointer array index is out of range: {wanted}")
        cursor = offset + 1
        for index, child in enumerate(value):
            if index:
                cursor += 1
            if index == wanted:
                return canonical_pointer_span(child, remaining, cursor)
            cursor += len(canonical_bytes(child))
    raise ValueError(f"pointer traverses a scalar at: {token}")


def expected_profiles(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    definitions = schema.get("$defs", {})
    choices = definitions.get("exactProfile", {}).get("oneOf", [])
    result: dict[str, dict[str, Any]] = {}
    for choice in choices:
        profile = choice.get("const") if isinstance(choice, dict) else None
        if not isinstance(profile, dict) or not isinstance(profile.get("id"), str):
            raise ValueError("campaign schema exactProfile is malformed")
        result[profile["id"]] = profile
    if tuple(sorted(result)) != PROFILE_IDS:
        raise ValueError("campaign schema does not contain the exact nine profiles")
    return result


def exact_routes() -> set[str]:
    return {
        f"{source}--to--{target}"
        for source in PROFILE_IDS
        for target in PROFILE_IDS
        if source != target
    }


def unique_index(
    values: object,
    key: str,
    label: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(values, list):
        errors.append(f"{label} must be an array")
        return result
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        identifier = value.get(key)
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"{label}[{index}] has no {key}")
        elif identifier in result:
            errors.append(f"duplicate {label} {key}: {identifier}")
        else:
            result[identifier] = value
    return result


def schema_type_matches(value: object, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def validate_schema_subset(
    value: object,
    schema: dict[str, Any],
    root: dict[str, Any],
    *,
    path: str = "$",
) -> list[str]:
    """Evaluate the strict JSON-Schema subset used by the frozen campaign.

    Keeping this small evaluator with the replay closure avoids turning package
    integrity replay into a network/package-manager operation.  When the full
    ``jsonschema`` library is installed it is run as an additional check.
    """

    errors: list[str] = []
    reference = schema.get("$ref")
    if isinstance(reference, str):
        if not reference.startswith("#/"):
            return [f"{path}: non-local schema reference is forbidden"]
        target: object = root
        try:
            for token in reference[2:].split("/"):
                target = target[token.replace("~1", "/").replace("~0", "~")]  # type: ignore[index]
        except Exception:
            return [f"{path}: schema reference is unresolved: {reference}"]
        if not isinstance(target, dict):
            return [f"{path}: schema reference is not an object: {reference}"]
        errors.extend(validate_schema_subset(value, target, root, path=path))
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: value does not equal const")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value is not in enum")
    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not schema_type_matches(value, expected_type):
        errors.append(f"{path}: expected {expected_type}")
        return errors
    if isinstance(expected_type, list) and not any(
        schema_type_matches(value, item) for item in expected_type
    ):
        errors.append(f"{path}: type is not one of {expected_type}")
        return errors
    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if key not in value:
                    errors.append(f"{path}: missing required property {key}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    errors.extend(
                        validate_schema_subset(
                            value[key], child_schema, root, path=f"{path}/{key}"
                        )
                    )
            if schema.get("additionalProperties") is False:
                extras = sorted(set(value) - set(properties))
                for key in extras:
                    errors.append(f"{path}: additional property is forbidden: {key}")
    if isinstance(value, list):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if isinstance(minimum, int) and len(value) < minimum:
            errors.append(f"{path}: fewer than {minimum} items")
        if isinstance(maximum, int) and len(value) > maximum:
            errors.append(f"{path}: more than {maximum} items")
        if schema.get("uniqueItems") is True:
            encoded = [canonical_bytes(item) for item in value]
            if len(set(encoded)) != len(encoded):
                errors.append(f"{path}: items are not unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(
                    validate_schema_subset(
                        item, item_schema, root, path=f"{path}/{index}"
                    )
                )
    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if isinstance(minimum_length, int) and len(value) < minimum_length:
            errors.append(f"{path}: string is shorter than {minimum_length}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            errors.append(f"{path}: string does not match pattern")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum_value = schema.get("minimum")
        if isinstance(minimum_value, (int, float)) and value < minimum_value:
            errors.append(f"{path}: value is below minimum")
    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for index, branch in enumerate(all_of):
            if isinstance(branch, dict):
                errors.extend(
                    validate_schema_subset(
                        value, branch, root, path=f"{path}:allOf:{index}"
                    )
                )
    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        matches = 0
        for branch in one_of:
            if isinstance(branch, dict) and not validate_schema_subset(
                value, branch, root, path=path
            ):
                matches += 1
        if matches != 1:
            errors.append(f"{path}: oneOf matched {matches} branches")
    return errors


def bundle_fingerprint(
    artifact_ids: list[str], artifacts: dict[str, dict[str, Any]]
) -> str | None:
    if any(identifier not in artifacts for identifier in artifact_ids):
        return None
    payload = [artifacts[identifier] for identifier in sorted(artifact_ids)]
    return canonical_digest(payload)


def validate_toolchain_stream(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label} stream is invalid")
        return
    text = value.get("text")
    byte_count = value.get("byte_count")
    if not isinstance(text, str) or not isinstance(byte_count, int) or byte_count < 0:
        errors.append(f"{label} stream metadata is invalid")
        return
    encoded = text.encode("utf-8")
    if value.get("truncated") is False:
        if byte_count != len(encoded) or value.get("sha256") != digest_bytes(encoded):
            errors.append(f"{label} stream digest/bytes drift")
    elif value.get("truncated") is not True or byte_count < len(encoded):
        errors.append(f"{label} stream truncation metadata drift")


def validate_toolchain_command(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label} command is invalid")
        return
    status = value.get("status")
    exit_code = value.get("exit_code")
    if status not in {"PASSED", "FAILED", "NOT_RUN", "TIMEOUT", "TOOL_UNAVAILABLE"}:
        errors.append(f"{label} command status is invalid")
    if status == "PASSED" and exit_code != 0:
        errors.append(f"{label} passing command has nonzero exit")
    if status == "FAILED" and (not isinstance(exit_code, int) or exit_code == 0):
        errors.append(f"{label} failed command exit is inconsistent")
    argv = value.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(item, str) and item for item in argv)
    ):
        errors.append(f"{label} command argv is invalid")
    validate_toolchain_stream(value.get("stdout"), f"{label} stdout", errors)
    validate_toolchain_stream(value.get("stderr"), f"{label} stderr", errors)


def validate_toolchain_evidence(
    campaign: dict[str, Any],
    profile_index: dict[str, dict[str, Any]],
    route_index: dict[str, dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    used_artifact_ids: set[str],
    errors: list[str],
) -> dict[str, Any]:
    declaration = campaign.get("toolchain_evidence")
    if not isinstance(declaration, dict):
        errors.append("toolchain evidence declaration is missing")
        return {"profiles": {}, "routes": {}, "artifact_id": None}
    profile_bindings = unique_index(
        declaration.get("profile_bindings"),
        "profile_id",
        "toolchain profile binding",
        errors,
    )
    route_bindings = unique_index(
        declaration.get("route_bindings"),
        "route_id",
        "toolchain route binding",
        errors,
    )
    if set(profile_bindings) != set(PROFILE_IDS):
        errors.append("toolchain profile binding closure is not exact")
    if set(route_bindings) != exact_routes():
        errors.append("toolchain route binding closure is not exact")
    boundaries = declaration.get("boundaries")
    if boundaries != {
        "build_is_behavior": False,
        "model_is_native": False,
        "device_or_simulator_status": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }:
        errors.append("toolchain evidence boundaries drift")
    producer_candidates = [
        reference
        for identifier, reference in artifacts.items()
        if identifier in set(campaign.get("implementation", {}).get("artifact_ids", []))
        and reference.get("role") == "implementation-source"
        and str(reference.get("path", "")).endswith(
            "/run_frontend_formal_toolchains.py"
        )
    ]
    if len(producer_candidates) != 1 or declaration.get(
        "producer_fingerprint"
    ) != producer_candidates[0].get("sha256"):
        errors.append("toolchain evidence producer fingerprint drift")
    captured_producer = producer_candidates[0] if len(producer_candidates) == 1 else {}

    artifact_id = declaration.get("artifact_id")
    if declaration.get("provided") is False:
        if (
            declaration.get("status") != "NOT_RUN"
            or artifact_id is not None
            or declaration.get("artifact_sha256") is not None
            or declaration.get("engine_campaign_sha256") is not None
        ):
            errors.append("absent toolchain evidence must remain NOT_RUN")
        for profile_id, binding in profile_bindings.items():
            if (
                binding.get("project_digest")
                != profile_index.get(profile_id, {}).get("project_digest")
                or binding.get("execution_id") is not None
                or binding.get("toolchain_status") != "NOT_RUN"
                or binding.get("target_build_status") != "NOT_RUN"
                or binding.get("browser_status") != "NOT_RUN"
                or binding.get("browser_probe_count") != 0
                or binding.get("browser_pass_count") != 0
            ):
                errors.append(f"absent toolchain profile binding drift: {profile_id}")
        for route_id, binding in route_bindings.items():
            if any(
                binding.get(key) is not None
                for key in ("source_execution_id", "target_execution_id")
            ) or any(
                binding.get(key) != "NOT_RUN"
                for key in (
                    "source_build_status",
                    "target_build_status",
                    "source_browser_status",
                    "target_browser_status",
                    "native_behavior_status",
                )
            ):
                errors.append(f"absent toolchain route binding drift: {route_id}")
        return {
            "profiles": {},
            "routes": route_bindings,
            "artifact_id": None,
        }
    if declaration.get("provided") is not True:
        errors.append("toolchain evidence provided flag is invalid")
        return {"profiles": {}, "routes": route_bindings, "artifact_id": None}
    if artifacts.get(str(artifact_id), {}).get("role") != "toolchain-evidence":
        errors.append("toolchain evidence artifact role mismatch")
        return {"profiles": {}, "routes": route_bindings, "artifact_id": artifact_id}
    used_artifact_ids.add(str(artifact_id))
    raw_file = artifact_files.get(str(artifact_id))
    if raw_file is None:
        return {"profiles": {}, "routes": route_bindings, "artifact_id": artifact_id}
    artifact_ref = artifacts[str(artifact_id)]
    if declaration.get("artifact_sha256") != artifact_ref.get("sha256"):
        errors.append("toolchain evidence artifact digest drift")
    try:
        raw = load_json(raw_file)
    except Exception as exc:
        errors.append(f"toolchain evidence artifact is invalid: {exc}")
        return {"profiles": {}, "routes": route_bindings, "artifact_id": artifact_id}
    raw_producer = raw.get("producer")
    if (
        not isinstance(raw_producer, dict)
        or raw_producer.get("sha256") != captured_producer.get("sha256")
        or raw_producer.get("byte_count") != captured_producer.get("bytes")
        or not str(raw_producer.get("path", "")).endswith(
            "/tooling/run_frontend_formal_toolchains.py"
        )
        or raw.get("replay", {}).get("producer") != raw_producer
    ):
        errors.append("toolchain raw producer is stale or unbound")
    engine_id = str(campaign.get("engine_campaign_artifact_id"))
    engine_digest = artifacts.get(engine_id, {}).get("sha256")
    raw_campaign = raw.get("campaign")
    if (
        raw.get("schema_version") != "1.0"
        or raw.get("kind") != "frontend-formal-toolchain-evidence"
        or not isinstance(raw_campaign, dict)
        or raw_campaign.get("sha256") != engine_digest
        or declaration.get("engine_campaign_sha256") != engine_digest
        or raw_campaign.get("proof_profile") != "bounded-navigation-v1"
        or raw_campaign.get("profile_count") != 9
        or raw_campaign.get("route_count") != 72
    ):
        errors.append("toolchain evidence campaign binding drift")
    summary = raw.get("summary")
    if not isinstance(summary, dict) or (
        summary.get("device_or_simulator_journeys_passed") != 0
        or summary.get("independent_verification") != "NOT_RUN"
        or summary.get("certification") != "NOT_CERTIFIED"
    ):
        errors.append("toolchain evidence external boundary drift")

    executions = unique_index(
        raw.get("profile_executions"),
        "profile_id",
        "toolchain raw profile execution",
        errors,
    )
    if set(executions) != set(PROFILE_IDS):
        errors.append("toolchain raw profile closure is not exact")
    normalized_profiles: dict[str, dict[str, Any]] = {}
    for profile_id, execution in executions.items():
        if execution.get("reason") == "PROFILE_NOT_SELECTED":
            core = {
                "producer_digest": raw_producer.get("sha256")
                if isinstance(raw_producer, dict)
                else None,
                "profile_id": profile_id,
                "project_digest": execution.get("project_digest"),
                "status": "NOT_RUN",
            }
        else:
            core = {
                key: value
                for key, value in execution.items()
                if key not in {"execution_id", "replay_profile_args"}
            }
        browser = execution.get("browser_journey")
        probes = browser.get("probes", []) if isinstance(browser, dict) else []
        if execution.get("execution_id") != canonical_digest(core):
            errors.append(f"toolchain execution id drift: {profile_id}")
        if execution.get("producer") != raw_producer:
            errors.append(f"toolchain execution producer drift: {profile_id}")
        if execution.get("project_digest") != profile_index.get(profile_id, {}).get(
            "project_digest"
        ):
            errors.append(f"toolchain project digest drift: {profile_id}")
        if execution.get("status") not in {
            "PASSED",
            "FAILED",
            "NOT_RUN",
        } or execution.get("target_build") not in {"PASSED", "FAILED", "NOT_RUN"}:
            errors.append(f"toolchain profile status invalid: {profile_id}")
        if (
            not isinstance(browser, dict)
            or browser.get("status")
            not in {
                "PASSED",
                "FAILED",
                "NOT_RUN",
            }
            or not isinstance(probes, list)
        ):
            errors.append(f"toolchain browser record invalid: {profile_id}")
            probes = []
        for index, command in enumerate(execution.get("tool_versions", [])):
            validate_toolchain_command(
                command, f"toolchain {profile_id} version {index}", errors
            )
        for index, command in enumerate(execution.get("commands", [])):
            validate_toolchain_command(
                command, f"toolchain {profile_id} command {index}", errors
            )
        passed = 0
        for index, probe in enumerate(probes):
            if not isinstance(probe, dict):
                errors.append(f"toolchain {profile_id} probe {index} is invalid")
                continue
            validate_toolchain_command(
                probe.get("command"), f"toolchain {profile_id} probe {index}", errors
            )
            command = probe.get("command", {})
            observation = probe.get("observation")
            normalized = probe.get("normalized_observation")
            if probe.get("dom_sha256") != command.get("stdout", {}).get("sha256"):
                errors.append(f"toolchain {profile_id} probe {index} DOM digest drift")
            if probe.get("status") == "PASSED":
                passed += 1
                if (
                    command.get("status") != "PASSED"
                    or not isinstance(observation, dict)
                    or observation.get("matches_model") is not True
                    or not isinstance(normalized, dict)
                ):
                    errors.append(f"toolchain {profile_id} probe {index} fake PASS")
        if browser.get("status") == "PASSED" and (
            execution.get("target_build") != "PASSED"
            or not probes
            or passed != len(probes)
        ):
            errors.append(f"toolchain browser PASS incomplete: {profile_id}")
        if profile_id == "harmony-arkui" and (
            browser.get("status") != "NOT_RUN" or probes
        ):
            errors.append("Harmony native/browser evidence must remain NOT_RUN")
        normalized = {
            "profile_id": profile_id,
            "project_digest": execution.get("project_digest"),
            "execution_id": execution.get("execution_id"),
            "toolchain_status": execution.get("status"),
            "target_build_status": execution.get("target_build"),
            "browser_status": browser.get("status"),
            "browser_probe_count": len(probes),
            "browser_pass_count": passed,
        }
        normalized_profiles[profile_id] = normalized
        if profile_bindings.get(profile_id) != normalized:
            errors.append(f"toolchain normalized profile binding drift: {profile_id}")

    raw_routes = unique_index(
        raw.get("route_records"),
        "route_id",
        "toolchain raw route record",
        errors,
    )
    if set(raw_routes) != exact_routes():
        errors.append("toolchain raw route closure is not exact")
    normalized_routes: dict[str, dict[str, Any]] = {}
    for route_id, record in raw_routes.items():
        route = route_index.get(route_id, {})
        source = executions.get(str(route.get("source_profile_id")), {})
        target = executions.get(str(route.get("target_profile_id")), {})
        for key, expected in (
            ("source_profile", route.get("source_profile_id")),
            ("target_profile", route.get("target_profile_id")),
            ("source_project_digest", route.get("source_project_digest")),
            ("target_project_digest", route.get("target_project_digest")),
            ("source_execution_id", source.get("execution_id")),
            ("target_execution_id", target.get("execution_id")),
            ("source_toolchain_status", source.get("status")),
            ("target_toolchain_status", target.get("status")),
            ("source_browser_status", source.get("browser_journey", {}).get("status")),
            ("target_browser_status", target.get("browser_journey", {}).get("status")),
        ):
            if record.get(key) != expected:
                errors.append(f"toolchain route {route_id} {key} drift")
        native = (
            source.get("target_build") == "PASSED"
            and target.get("target_build") == "PASSED"
            and source.get("browser_journey", {}).get("status") == "PASSED"
            and target.get("browser_journey", {}).get("status") == "PASSED"
            and "harmony-arkui"
            not in {route.get("source_profile_id"), route.get("target_profile_id")}
        )
        if record.get("browser_evidence") != ("PASSED" if native else "NOT_RUN"):
            errors.append(f"toolchain route {route_id} browser evidence drift")
        if (
            record.get("device_or_simulator_evidence") != "NOT_RUN"
            or record.get("holdout_evidence") != "NOT_RUN"
            or record.get("representative_customer_evidence") != "NOT_RUN"
            or record.get("certification") != "NOT_CERTIFIED"
        ):
            errors.append(f"toolchain route {route_id} external boundary drift")
        normalized = {
            "route_id": route_id,
            "source_execution_id": source.get("execution_id"),
            "target_execution_id": target.get("execution_id"),
            "source_build_status": source.get("target_build"),
            "target_build_status": target.get("target_build"),
            "source_browser_status": source.get("browser_journey", {}).get("status"),
            "target_browser_status": target.get("browser_journey", {}).get("status"),
            "native_behavior_status": "PASSED" if native else "NOT_RUN",
        }
        normalized_routes[route_id] = normalized
        if route_bindings.get(route_id) != normalized:
            errors.append(f"toolchain normalized route binding drift: {route_id}")
    navigation_identity_boundary = (
        raw.get("implementation_closure") is None
        and raw.get("engine_preverification") is None
        and raw.get("semantic_block_ids") == []
        and raw.get("scenario_manifest_digest") is None
        and raw.get("scenario_policy") is None
        and raw.get("mutation_replay") == []
    )
    if not navigation_identity_boundary:
        errors.append("toolchain raw v1 identity boundary drift")
    identity_core = {
        "producer": raw_producer,
        "implementation_closure": None,
        "engine_preverification_digest": None,
        "campaign_sha256": engine_digest,
        "proof_profile": "bounded-navigation-v1",
        "semantic_block_ids": [],
        "scenario_manifest_digest": None,
        "scenario_policy": None,
        "mutation_replay_digest": canonical_digest([]),
        "policy": raw.get("policy"),
        "profile_execution_ids": [
            execution.get("execution_id") for execution in executions.values()
        ],
        "route_execution_bindings": [
            {
                "route_id": record.get("route_id"),
                "source_execution_id": record.get("source_execution_id"),
                "target_execution_id": record.get("target_execution_id"),
                "status": record.get("status"),
            }
            for record in raw_routes.values()
        ],
    }
    if raw.get("evidence_identity") != {
        "algorithm": "sha256(canonical-json(identity_payload))",
        "identity_payload": identity_core,
        "sha256": canonical_digest(identity_core),
        "scope": "producer+engine-preverification+implementation+campaign+scenario+policy+profile-executions+route-bindings",
    }:
        errors.append("toolchain raw evidence identity drift")
    states = {item.get("toolchain_status") for item in normalized_profiles.values()}
    expected_status = (
        "FAILED"
        if "FAILED" in states
        else "PASSED"
        if states == {"PASSED"}
        else "NOT_RUN"
        if states == {"NOT_RUN"}
        else "PARTIAL"
    )
    if declaration.get("status") != expected_status:
        errors.append("toolchain evidence aggregate status drift")
    return {
        "profiles": executions,
        "routes": normalized_routes,
        "artifact_id": artifact_id,
    }


def validate_span_ref(
    reference: object,
    *,
    label: str,
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    route_artifact_ids: set[str],
    errors: list[str],
) -> str | None:
    if not isinstance(reference, dict):
        errors.append(f"{label} must be an object")
        return None
    artifact_id = reference.get("artifact_id")
    if artifact_id not in route_artifact_ids:
        errors.append(f"{label} references an artifact outside the route closure")
        return None
    if artifact_id not in artifacts or artifact_id not in artifact_files:
        errors.append(f"{label} references an unknown artifact: {artifact_id}")
        return None
    path = artifact_files[artifact_id]
    try:
        content = path.read_bytes()
        document = json.loads(content.decode("utf-8"))
        pointer = str(reference.get("pointer", ""))
        pointed = json_pointer(document, pointer)
        expected_span = canonical_pointer_span(document, pointer_tokens(pointer))
    except Exception as exc:
        errors.append(f"{label} pointer is invalid: {exc}")
        return None
    span = reference.get("span")
    if not isinstance(span, dict):
        errors.append(f"{label} span is missing")
        return None
    start, end = span.get("start"), span.get("end")
    if content != canonical_bytes(document):
        errors.append(f"{label} artifact is not canonical JSON for exact spans")
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 0
        or end <= start
        or end > len(content)
    ):
        errors.append(f"{label} span is out of bounds")
        return None
    if (start, end) != expected_span:
        errors.append(f"{label} span does not match the RFC6901 canonical location")
    try:
        span_value = json.loads(content[start:end].decode("utf-8"))
    except Exception as exc:
        errors.append(f"{label} span is not a complete JSON value: {exc}")
        return None
    if span_value != pointed:
        errors.append(f"{label} span does not bind the RFC6901 value")
    actual_digest = canonical_digest(pointed)
    if reference.get("sha256") != actual_digest:
        errors.append(f"{label} pointer value digest mismatch")
    return actual_digest


def validate_code_span_ref(
    reference: object,
    *,
    label: str,
    expected_role: str,
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    route_artifact_ids: set[str],
    errors: list[str],
) -> str | None:
    if not isinstance(reference, dict):
        errors.append(f"{label} must be an object")
        return None
    artifact_id = reference.get("artifact_id")
    if artifact_id not in route_artifact_ids:
        errors.append(f"{label} references code outside the route closure")
        return None
    artifact = artifacts.get(str(artifact_id))
    path = artifact_files.get(str(artifact_id))
    if artifact is None or path is None:
        errors.append(f"{label} references unknown code artifact: {artifact_id}")
        return None
    if artifact.get("role") != expected_role:
        errors.append(f"{label} code artifact role mismatch")
    start, end = reference.get("start"), reference.get("end")
    content = path.read_bytes()
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 0
        or end <= start
        or end > len(content)
    ):
        errors.append(f"{label} code span is out of bounds")
        return None
    actual_digest = digest_bytes(content[start:end])
    if reference.get("sha256") != actual_digest:
        errors.append(f"{label} code span digest mismatch")
    if not isinstance(reference.get("parser_node_kind"), str) or not reference.get(
        "parser_node_kind"
    ):
        errors.append(f"{label} parser node kind is missing")
    return actual_digest


def validate_relift_code_binding(
    ir_reference: object,
    *,
    binding_group: str,
    binding_id: str,
    code_digest: str | None,
    label: str,
    artifact_files: dict[str, Path],
    errors: list[str],
) -> None:
    if code_digest is None or not isinstance(ir_reference, dict):
        return
    artifact_id = ir_reference.get("artifact_id")
    path = artifact_files.get(str(artifact_id))
    if path is None:
        return
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    bindings = document.get(binding_group) if isinstance(document, dict) else None
    if not isinstance(bindings, dict) or bindings.get(binding_id) != code_digest:
        errors.append(f"{label} relift IR is not bound to the code span")


def validate_behavior(
    route_id: str,
    wrapper: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    route_artifact_ids: set[str],
    toolchain_context: dict[str, Any],
    errors: list[str],
) -> None:
    behavior = wrapper.get("behavior", {})
    route_toolchain = toolchain_context.get("routes", {}).get(route_id, {})
    for key in (
        "source_execution_id",
        "target_execution_id",
        "source_build_status",
        "target_build_status",
        "source_browser_status",
        "target_browser_status",
    ):
        if behavior.get(key) != route_toolchain.get(key):
            errors.append(f"route {route_id} behavior toolchain {key} drift")
    if behavior.get("native_evidence_status") != route_toolchain.get(
        "native_behavior_status"
    ):
        errors.append(f"route {route_id} native behavior status drift")
    if behavior.get("toolchain_evidence_artifact_id") != toolchain_context.get(
        "artifact_id"
    ):
        errors.append(f"route {route_id} toolchain artifact binding drift")
    artifact_id = behavior.get("artifact_id")
    behavior_file = artifact_files.get(str(artifact_id))
    if artifact_id not in route_artifact_ids or behavior_file is None:
        errors.append(f"route {route_id} behavior artifact is not route-bound")
        return
    if artifacts.get(str(artifact_id), {}).get("role") != "behavior-traces":
        errors.append(f"route {route_id} behavior artifact role mismatch")
    try:
        payload = load_json(behavior_file)
    except Exception as exc:
        errors.append(f"route {route_id} behavior artifact is invalid: {exc}")
        return
    if payload.get("route_id") != route_id:
        errors.append(f"route {route_id} behavior artifact route binding drift")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        errors.append(f"route {route_id} behavior cases must be an array")
        return
    case_ids: set[str] = set()
    passed = 0
    source_execution = toolchain_context.get("profiles", {}).get(
        str(wrapper.get("source_profile_id")), {}
    )
    target_execution = toolchain_context.get("profiles", {}).get(
        str(wrapper.get("target_profile_id")), {}
    )
    source_probes = source_execution.get("browser_journey", {}).get("probes", [])
    target_probes = target_execution.get("browser_journey", {}).get("probes", [])
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"route {route_id} behavior case {index} is invalid")
            continue
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"route {route_id} behavior case {index} has no id")
        elif case_id in case_ids:
            errors.append(f"route {route_id} duplicate behavior case: {case_id}")
        else:
            case_ids.add(case_id)
        canonical = case.get("canonical_expected")
        independent = case.get("independent_expected")
        source_trace = case.get("source_trace")
        target_trace = case.get("target_trace")
        if not all(
            isinstance(item, dict) for item in (canonical, source_trace, target_trace)
        ):
            errors.append(f"route {route_id} behavior case {case_id} is incomplete")
            continue
        if canonical.get("oracle_kind") != "canonical-spec":
            errors.append(
                f"route {route_id} behavior case {case_id} lacks canonical oracle"
            )
        canonical_provenance = canonical.get("provenance_artifact_id")
        if canonical_provenance != behavior.get("canonical_oracle_artifact_id"):
            errors.append(f"route {route_id} canonical oracle provenance drift")
        if independent is not None:
            if not isinstance(independent, dict):
                errors.append(f"route {route_id} independent oracle record is invalid")
            else:
                independent_provenance = independent.get("provenance_artifact_id")
                if independent.get("oracle_kind") != "independent-spec":
                    errors.append(
                        f"route {route_id} independent oracle kind is invalid"
                    )
                if independent_provenance != behavior.get(
                    "independent_oracle_artifact_id"
                ):
                    errors.append(
                        f"route {route_id} independent oracle provenance drift"
                    )
                if (
                    canonical == independent
                    or canonical_provenance == independent_provenance
                ):
                    errors.append(
                        f"route {route_id} canonical oracle was copied as independent"
                    )
        for name, trace, expected_kind in (
            ("source", source_trace, behavior.get("source_runtime_kind")),
            ("target", target_trace, behavior.get("target_runtime_kind")),
        ):
            if trace.get("runtime_kind") != expected_kind:
                errors.append(f"route {route_id} {name} runtime kind drift")
            native = trace.get("native_execution")
            if expected_kind == "model" and native is not False:
                errors.append(f"route {route_id} model trace masquerades as native")
            if expected_kind in {"browser", "device"} and native is not True:
                errors.append(f"route {route_id} native trace lacks native execution")
            if expected_kind == "browser":
                probes = source_probes if name == "source" else target_probes
                evidence = trace.get("evidence")
                if not isinstance(evidence, dict):
                    errors.append(
                        f"route {route_id} {name} native trace lacks evidence"
                    )
                    continue
                matching = [
                    probe
                    for probe in probes
                    if isinstance(probe, dict)
                    and probe.get("name") == evidence.get("probe_name")
                ]
                if len(matching) != 1:
                    errors.append(f"route {route_id} {name} native probe binding drift")
                    continue
                probe = matching[0]
                normalized = probe.get("normalized_observation")
                if not isinstance(normalized, dict):
                    errors.append(
                        f"route {route_id} {name} native probe has no actual observation"
                    )
                    continue
                actual_event = {
                    "operation": normalized.get("operation"),
                    "input_path": normalized.get("input_path"),
                    "resolution": normalized.get("resolution"),
                    "route": normalized.get("route"),
                    "render": normalized.get("render"),
                }
                if (
                    probe.get("status") != "PASSED"
                    or evidence.get("toolchain_evidence_artifact_id")
                    != toolchain_context.get("artifact_id")
                    or evidence.get("execution_id")
                    != (
                        source_execution.get("execution_id")
                        if name == "source"
                        else target_execution.get("execution_id")
                    )
                    or evidence.get("dom_sha256") != probe.get("dom_sha256")
                    or evidence.get("normalized_observation_sha256")
                    != canonical_digest(normalized)
                    or trace.get("events") != actual_event
                    or actual_event != canonical.get("events")
                ):
                    errors.append(
                        f"route {route_id} {name} native trace is not actual-DOM-derived"
                    )
        expected_events = canonical.get("events")
        source_ok = source_trace.get("events") == expected_events
        target_ok = target_trace.get("events") == expected_events
        independent_ok = (
            isinstance(independent, dict)
            and independent.get("events") == expected_events
        )
        if (
            case.get("status") == "PASSED"
            and source_ok
            and target_ok
            and independent_ok
        ):
            passed += 1
        elif case.get("status") == "PASSED":
            errors.append(
                f"route {route_id} behavior case {case_id} PASS is inconsistent"
            )
    if behavior.get("case_count") != len(cases):
        errors.append(f"route {route_id} behavior case_count drift")
    if behavior.get("pass_count") != passed:
        errors.append(f"route {route_id} behavior pass_count drift")
    status = behavior.get("status")
    if status == "PASSED":
        if not cases:
            errors.append(f"route {route_id} zero-case behavior cannot PASS")
        if passed != len(cases):
            errors.append(f"route {route_id} behavior PASS has nonpassing cases")
        if behavior.get("independent_oracle_artifact_id") is None:
            errors.append(f"route {route_id} behavior PASS lacks an independent oracle")
    elif status == "NOT_RUN" and passed:
        errors.append(f"route {route_id} NOT_RUN behavior contains passing cases")
    source_kind = behavior.get("source_runtime_kind")
    target_kind = behavior.get("target_runtime_kind")
    native_execution = behavior.get("native_execution")
    if source_kind == "model" or target_kind == "model":
        if native_execution is not False:
            errors.append(f"route {route_id} model behavior masquerades as native")
    elif native_execution is not True:
        errors.append(
            f"route {route_id} browser/device behavior lacks native execution"
        )
    if (
        native_execution is True
        and route_toolchain.get("native_behavior_status") != "PASSED"
    ):
        errors.append(
            f"route {route_id} native behavior lacks two-sided passing probes"
        )


def validate_oracle_provenance(
    route_id: str,
    wrapper: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    errors: list[str],
) -> None:
    behavior = wrapper.get("behavior", {})
    canonical_id = behavior.get("canonical_oracle_artifact_id")
    independent_id = behavior.get("independent_oracle_artifact_id")
    canonical = artifacts.get(str(canonical_id))
    if canonical is None or canonical.get("role") != "canonical-oracle":
        errors.append(f"route {route_id} canonical oracle artifact is missing")
        return
    try:
        canonical_payload = load_json(artifact_files[str(canonical_id)])
    except Exception as exc:
        errors.append(f"route {route_id} canonical oracle is invalid: {exc}")
        return
    if canonical_payload.get("oracle_kind") != "canonical-spec":
        errors.append(f"route {route_id} canonical oracle manifest kind mismatch")
    if independent_id is None:
        return
    independent = artifacts.get(str(independent_id))
    if independent is None or independent.get("role") != "independent-oracle":
        errors.append(f"route {route_id} independent oracle artifact is missing")
        return
    try:
        independent_payload = load_json(artifact_files[str(independent_id)])
    except Exception as exc:
        errors.append(f"route {route_id} independent oracle is invalid: {exc}")
        return
    if independent_payload.get("oracle_kind") != "independent-spec":
        errors.append(f"route {route_id} independent oracle manifest kind mismatch")
    canonical_sources = set(canonical_payload.get("source_artifact_ids", []))
    independent_sources = set(independent_payload.get("source_artifact_ids", []))
    if not independent_sources:
        errors.append(f"route {route_id} independent oracle has no provenance sources")
    if canonical_sources & independent_sources:
        errors.append(
            f"route {route_id} canonical and independent oracle provenance overlaps"
        )
    if (
        canonical.get("sha256") == independent.get("sha256")
        or canonical_payload == independent_payload
        or canonical_payload.get("derivation_fingerprint")
        == independent_payload.get("derivation_fingerprint")
    ):
        errors.append(f"route {route_id} canonical oracle was copied as independent")


def validate_formal(
    route_id: str,
    wrapper: dict[str, Any],
    route: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    artifact_files: dict[str, Path],
    route_artifact_ids: set[str],
    corpora: dict[str, Any],
    implementation_fingerprint: str,
    replay_fingerprint: str,
    execute_solver_replay: bool,
    errors: list[str],
) -> None:
    formal = wrapper.get("formal", {})
    input_id = formal.get("formal_input_artifact_id")
    smt_id = formal.get("smt_artifact_id")
    result_id = formal.get("solver_result_artifact_id")
    solver_binary_id = formal.get("solver_binary_artifact_id")
    raw_layered_id = formal.get("raw_layered_result_artifact_id")
    for identifier, role, label in (
        (input_id, "formal-input", "formal input"),
        (smt_id, "solver-input", "SMT input"),
        (result_id, "solver-result", "solver result"),
        (solver_binary_id, "solver-binary-environment", "solver binary"),
        (raw_layered_id, "engine-route-artifact", "raw layered result"),
    ):
        if identifier not in route_artifact_ids or identifier not in artifacts:
            errors.append(f"route {route_id} {label} is not route-bound")
        elif artifacts[str(identifier)].get("role") != role:
            errors.append(f"route {route_id} {label} role mismatch")
    if any(
        identifier not in artifact_files
        for identifier in (
            input_id,
            smt_id,
            result_id,
            solver_binary_id,
            raw_layered_id,
        )
    ):
        return
    input_ref = artifacts[str(input_id)]
    smt_ref = artifacts[str(smt_id)]
    result_ref = artifacts[str(result_id)]
    solver_binary_ref = artifacts[str(solver_binary_id)]
    raw_layered_ref = artifacts[str(raw_layered_id)]
    if formal.get("formal_input_sha256") != input_ref.get("sha256"):
        errors.append(f"route {route_id} formal input digest linkage drift")
    if formal.get("solver_input_sha256") != smt_ref.get("sha256"):
        errors.append(f"route {route_id} solver input digest linkage drift")
    if formal.get("solver_result_sha256") != result_ref.get("sha256"):
        errors.append(f"route {route_id} solver result digest linkage drift")
    if (
        formal.get("solver_binary_sha256") != LOCKED_Z3_BINARY_SHA256
        or solver_binary_ref.get("sha256") != LOCKED_Z3_BINARY_SHA256
        or formal.get("solver_binary_bytes") != solver_binary_ref.get("bytes")
    ):
        errors.append(f"route {route_id} locked solver binary artifact drift")
    if formal.get("raw_layered_result_sha256") != raw_layered_ref.get("sha256"):
        errors.append(f"route {route_id} raw layered result digest linkage drift")
    try:
        formal_input = load_json(artifact_files[str(input_id)])
        solver_result = load_json(artifact_files[str(result_id)])
        smt_bytes = artifact_files[str(smt_id)].read_bytes()
        smt_content = smt_bytes.decode("utf-8")
    except Exception as exc:
        errors.append(f"route {route_id} formal artifacts are invalid: {exc}")
        return
    bindings = {
        "route_id": route_id,
        "source_profile_digest": route.get("source_profile_digest"),
        "target_profile_digest": route.get("target_profile_digest"),
        "source_project_digest": route.get("source_project_digest"),
        "target_project_digest": route.get("target_project_digest"),
        "implementation_fingerprint": implementation_fingerprint,
        "replay_fingerprint": replay_fingerprint,
        "composition_id": formal.get("composition_id"),
    }
    for key, expected in bindings.items():
        if formal_input.get(key) != expected:
            errors.append(f"route {route_id} formal input {key} linkage drift")
    if formal_input.get("assumptions") != formal.get("assumptions"):
        errors.append(f"route {route_id} formal assumptions drift")
    if formal_input.get("unsupported_semantics") != formal.get("unsupported_semantics"):
        errors.append(f"route {route_id} formal unsupported semantics drift")
    development_corpus = corpora.get("development", {}).get("id")
    if formal_input.get("corpus_id") != development_corpus:
        errors.append(f"route {route_id} formal corpus linkage drift")
    model_links = {
        "source_model_sha256": next(
            (
                artifacts[item].get("sha256")
                for item in route_artifact_ids
                if artifacts.get(item, {}).get("role") == "source-relift-ir"
            ),
            None,
        ),
        "target_model_sha256": next(
            (
                artifacts[item].get("sha256")
                for item in route_artifact_ids
                if artifacts.get(item, {}).get("role") == "target-relift-ir"
            ),
            None,
        ),
        "chunk_sha256": artifacts.get(
            str(wrapper.get("chunk_equivalence", {}).get("artifact_id")), {}
        ).get("sha256"),
        "behavior_sha256": artifacts.get(
            str(wrapper.get("behavior", {}).get("artifact_id")), {}
        ).get("sha256"),
    }
    for key, expected in model_links.items():
        if expected is None or formal_input.get(key) != expected:
            errors.append(f"route {route_id} formal input {key} linkage drift")
    input_digest = input_ref.get("sha256")
    if input_digest not in smt_content:
        errors.append(f"route {route_id} SMT input is not linked to formal input")
    for key, expected in (
        ("route_id", route_id),
        ("formal_input_sha256", input_digest),
        ("solver_input_sha256", smt_ref.get("sha256")),
        ("implementation_fingerprint", implementation_fingerprint),
        ("replay_fingerprint", replay_fingerprint),
    ):
        if solver_result.get(key) != expected:
            errors.append(f"route {route_id} solver result {key} linkage drift")
    raw_smt_id = solver_result.get("raw_solver_input_artifact_id")
    raw_result_id = solver_result.get("raw_solver_result_artifact_id")
    for raw_id, suffix, label in (
        (raw_smt_id, f"routes/{route_id}/proof.smt2", "raw SMT input"),
        (
            raw_result_id,
            f"routes/{route_id}/solver-result.json",
            "raw solver result",
        ),
        (
            raw_layered_id,
            f"routes/{route_id}/layered-result.json",
            "raw layered result",
        ),
    ):
        reference = artifacts.get(str(raw_id), {})
        if (
            raw_id not in route_artifact_ids
            or reference.get("role") != "engine-route-artifact"
            or not str(reference.get("path", "")).endswith(suffix)
        ):
            errors.append(f"route {route_id} {label} binding drift")
    raw_smt_file = artifact_files.get(str(raw_smt_id))
    raw_result_file = artifact_files.get(str(raw_result_id))
    raw_layered_file = artifact_files.get(str(raw_layered_id))
    raw_result: dict[str, Any] = {}
    raw_layered: dict[str, Any] = {}
    if raw_smt_file is None or raw_result_file is None or raw_layered_file is None:
        errors.append(f"route {route_id} raw solver closure is incomplete")
    else:
        raw_smt = raw_smt_file.read_bytes()
        try:
            raw_result = load_json(raw_result_file)
            raw_layered = load_json(raw_layered_file)
        except Exception as exc:
            errors.append(
                f"route {route_id} raw solver/layered result is invalid: {exc}"
            )
        raw_smt_sha = digest_bytes(raw_smt)
        raw_result_sha = digest_bytes(raw_result_file.read_bytes())
        raw_layered_sha = digest_bytes(raw_layered_file.read_bytes())
        if (
            formal.get("raw_solver_input_sha256") != raw_smt_sha
            or solver_result.get("raw_solver_input_sha256") != raw_smt_sha
            or formal.get("raw_solver_result_sha256") != raw_result_sha
            or solver_result.get("raw_solver_result_sha256") != raw_result_sha
            or formal.get("raw_layered_result_sha256") != raw_layered_sha
            or solver_result.get("raw_layered_result_sha256") != raw_layered_sha
            or formal.get("raw_layered_solver_result_sha256") != raw_result_sha
            or solver_result.get("raw_layered_solver_result_sha256") != raw_result_sha
        ):
            errors.append(f"route {route_id} raw solver artifact digest drift")
        raw_layered_links = raw_layered.get("links")
        if (
            raw_layered.get("route_id") != route_id
            or not isinstance(raw_layered_links, dict)
            or raw_layered_links.get("solver_result_path")
            != f"routes/{route_id}/solver-result.json"
            or raw_layered_links.get("solver_result_digest") != raw_result_sha
        ):
            errors.append(f"route {route_id} raw layered solver linkage drift")
        prefix = (
            f"; formal_input_sha256 {input_digest}\n"
            f"; implementation_fingerprint {implementation_fingerprint}\n"
            f"; replay_fingerprint {replay_fingerprint}\n"
        ).encode("utf-8")
        if solver_result.get("normalized_smt_transform") != "comments-prefix-only-v1":
            errors.append(f"route {route_id} normalized SMT transform is invalid")
        if smt_bytes != prefix + raw_smt:
            errors.append(
                f"route {route_id} normalized SMT is not exact comment-prefix replay"
            )
        raw_formal_id = formal_input.get("engine_formal_input_artifact_id")
        raw_formal_ref = artifacts.get(str(raw_formal_id), {})
        raw_formal_file = artifact_files.get(str(raw_formal_id))
        if (
            raw_formal_id not in route_artifact_ids
            or raw_formal_ref.get("role") != "engine-route-artifact"
            or not str(raw_formal_ref.get("path", "")).endswith(
                f"routes/{route_id}/formal-input.json"
            )
            or raw_formal_file is None
        ):
            errors.append(f"route {route_id} raw formal input binding drift")
        else:
            raw_formal_sha = digest_bytes(raw_formal_file.read_bytes())
            if (
                formal_input.get("engine_formal_input_digest") != raw_formal_sha
                or solver_result.get("raw_formal_input_sha256") != raw_formal_sha
                or raw_result.get("formal_input_digest") != raw_formal_sha
            ):
                errors.append(f"route {route_id} raw formal input digest drift")
        if (
            raw_result.get("solver_input_digest") != raw_smt_sha
            or raw_result.get("smt2_digest") != raw_smt_sha
        ):
            errors.append(f"route {route_id} raw solver input linkage drift")
        for key in (
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
            "proof_status",
            "unconditional_proof",
        ):
            if solver_result.get(key) != raw_result.get(key):
                errors.append(f"route {route_id} normalized/raw solver {key} drift")
        solver_environment = solver_result.get("environment")
        solver_realpath = solver_result.get("solver_binary_realpath")
        if (
            set(raw_result) != ENGINE_SOLVER_RESULT_KEYS
            or raw_result.get("schema_version") != "1.0"
            or raw_result.get("route_id") != route_id
            or solver_result.get("identity_status") != "VERIFIED"
            or not isinstance(solver_realpath, str)
            or not Path(solver_realpath).is_absolute()
            or Path(solver_realpath).name != "z3"
            or solver_result.get("solver") != solver_realpath
            or solver_result.get("solver_binary_sha256") != LOCKED_Z3_BINARY_SHA256
            or solver_result.get("solver_binary_artifact_id") != solver_binary_id
            or solver_result.get("solver_binary_bytes")
            != solver_binary_ref.get("bytes")
            or solver_result.get("raw_layered_result_artifact_id") != raw_layered_id
            or solver_result.get("solver_version") != LOCKED_Z3_VERSION
            or solver_result.get("invocation") != [solver_realpath, "-in"]
            or solver_result.get("options") != LOCKED_Z3_OPTIONS
            or solver_environment != LOCKED_Z3_ENVIRONMENT
        ):
            errors.append(
                f"route {route_id} solver identity/version/options/environment drift"
            )
        replay_key = (LOCKED_Z3_BINARY_SHA256, raw_smt_sha)
        replay_result = (
            SOLVER_REPLAY_CACHE.get(replay_key) if execute_solver_replay else None
        )
        if execute_solver_replay and replay_result is None:
            try:
                completed = subprocess.run(
                    [str(artifact_files[str(solver_binary_id)]), "-in"],
                    input=raw_smt,
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                replay_result = (
                    completed.returncode,
                    completed.stdout,
                    completed.stderr,
                )
                SOLVER_REPLAY_CACHE[replay_key] = replay_result
            except Exception as exc:
                errors.append(f"route {route_id} locked solver replay failed: {exc}")
        if execute_solver_replay and replay_result is not None and replay_result != (
            raw_result.get("exit_code"),
            str(raw_result.get("stdout", "")).encode("utf-8"),
            str(raw_result.get("stderr", "")).encode("utf-8"),
        ):
            errors.append(f"route {route_id} locked solver replay diverged")
    solver_status = solver_result.get("status")
    normalized_raw_status = (
        raw_result.get("outcome")
        if raw_result.get("outcome") in {"UNSAT", "SAT", "UNKNOWN"}
        else "ERROR"
    )
    if solver_status != normalized_raw_status:
        errors.append(f"route {route_id} normalized/raw solver status drift")
    formal_status = formal.get("status")
    proof_strength = formal.get("proof_strength")
    assumptions = formal.get("assumptions", [])
    unsupported = formal.get("unsupported_semantics", [])
    if solver_status == "UNSAT":
        if (
            solver_result.get("exit_code") != 0
            or solver_result.get("stdout") != "unsat\n"
            or solver_result.get("stderr") != ""
            or solver_result.get("proof_status") != "PROVED_UNDER_ASSUMPTIONS"
            or solver_result.get("unconditional_proof") is not False
            or raw_result.get("outcome") != "UNSAT"
        ):
            errors.append(
                f"route {route_id} fake or malformed UNSAT result cannot prove"
            )
        if proof_strength == "theorem" and not assumptions and not unsupported:
            expected_status = "PROVED"
        elif proof_strength == "assumption" and assumptions:
            expected_status = "PROVED_UNDER_ASSUMPTIONS"
        elif proof_strength == "bounded":
            expected_status = "BOUNDED"
        elif proof_strength == "axiom":
            expected_status = "AXIOM"
        else:
            expected_status = "NOT_PROVED"
    else:
        expected_status = SOLVER_TO_FORMAL.get(str(solver_status), "NOT_PROVED")
    if formal_status != expected_status:
        errors.append(f"route {route_id} solver/formal status drift")
    if route.get("formal_status") != formal_status:
        errors.append(f"route {route_id} campaign/formal status drift")
    if formal.get("composition_id") != f"composition:{route_id}":
        errors.append(f"route {route_id} composition id drift")
    composition = formal.get("composition_status")
    if formal_status in PROOF_PASSING:
        if composition != formal_status:
            errors.append(f"route {route_id} proof composition status drift")
    elif composition not in {"REFUTED", "NOT_PROVED"}:
        errors.append(f"route {route_id} unresolved proof masquerades as composition")
    if route.get("composition_status") != composition:
        errors.append(f"route {route_id} campaign composition status drift")
    if formal_status == "PROVED":
        if formal.get("unconditional") is not True or assumptions or unsupported:
            errors.append(
                f"route {route_id} unconditional proof has residual conditions"
            )
    else:
        if formal.get("unconditional") is not False:
            errors.append(
                f"route {route_id} conditional/unresolved proof is unconditional"
            )
    if formal_status == "PROVED_UNDER_ASSUMPTIONS" and not assumptions:
        errors.append(f"route {route_id} proof under assumptions has no assumptions")
    if formal_status in NON_PROOF and composition in PROOF_PASSING:
        errors.append(f"route {route_id} non-proof status masquerades as proved")


def validate_campaign(
    pack: Path,
    *,
    campaign_relative: str | None = None,
    schema_path: Path | None = None,
    route_schema_path: Path | None = None,
    execute_replay: bool = True,
    portable_evidence_only: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        pack = pack.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return {
            "status": "invalid",
            "formal_ready": False,
            "errors": ["pack is missing"],
        }
    manifest_path = pack / "pack.json"
    try:
        pack_manifest = load_json(manifest_path)
    except Exception as exc:
        return {
            "status": "invalid",
            "formal_ready": False,
            "errors": [f"cannot load pack manifest: {exc}"],
        }
    declaration = campaign_relative or pack_manifest.get(
        "frontend_formal_route_campaign"
    )
    campaign_path = safe_pack_file(
        pack, declaration, "pack frontend_formal_route_campaign", errors
    )
    if campaign_path is None:
        return {"status": "invalid", "formal_ready": False, "errors": errors}
    try:
        campaign = load_json(campaign_path)
    except Exception as exc:
        errors.append(f"cannot load frontend formal campaign: {exc}")
        return {"status": "invalid", "formal_ready": False, "errors": errors}

    repo_root = Path(__file__).resolve().parents[2]
    schema_path = schema_path or (
        repo_root / "schemas" / "batch32" / "frontend-formal-route-campaign.schema.json"
    )
    route_schema_path = route_schema_path or (
        repo_root / "schemas" / "batch32" / "frontend-formal-route-evidence.schema.json"
    )
    try:
        campaign_schema = load_json(schema_path)
        route_schema = load_json(route_schema_path)
    except Exception as exc:
        errors.append(f"cannot load frontend schemas: {exc}")
        return {"status": "invalid", "formal_ready": False, "errors": errors}
    errors.extend(
        f"frontend campaign schema violation: {message}"
        for message in validate_schema_subset(
            campaign, campaign_schema, campaign_schema
        )
    )
    if jsonschema is not None:
        try:
            jsonschema.validate(campaign, campaign_schema)
        except Exception as exc:
            errors.append(f"frontend campaign schema violation: {exc}")
    try:
        expected = expected_profiles(campaign_schema)
    except Exception as exc:
        errors.append(str(exc))
        expected = {}

    campaign_digest = digest_bytes(campaign_path.read_bytes())
    pack_key = pack_manifest.get("pack_key")
    allowed_pack_keys = {
        "frontend-72-route-equivalence-v1",
        "frontend-72-route-formal-equivalence-v1",
    }
    if pack_key not in allowed_pack_keys:
        errors.append("frontend campaign pack_key is not an exact aggregate owner")
    if pack_manifest.get("frontend_formal_campaign_digest") != campaign_digest:
        errors.append("pack frontend formal campaign digest mismatch")
    if pack_manifest.get("frontend_formal_scope_digest") != campaign.get(
        "peer_binding", {}
    ).get("scope_digest"):
        errors.append("pack frontend formal scope digest mismatch")
    peer = pack_manifest.get("frontend_formal_peer")
    if not isinstance(peer, dict):
        errors.append("pack frontend formal peer binding is missing")
    else:
        peer_key = (
            "frontend-72-route-formal-equivalence-v1"
            if pack_key == "frontend-72-route-equivalence-v1"
            else "frontend-72-route-equivalence-v1"
        )
        if peer.get("pack_key") != peer_key:
            errors.append("pack frontend formal peer pack_key mismatch")
        if peer.get("campaign_sha256") != campaign_digest:
            errors.append("pack frontend formal peer campaign digest mismatch")
        if peer.get("scope_digest") != campaign.get("peer_binding", {}).get(
            "scope_digest"
        ):
            errors.append("pack frontend formal peer scope digest mismatch")

    artifact_index = unique_index(campaign.get("artifacts"), "id", "artifact", errors)
    artifact_paths: dict[str, str] = {}
    artifact_files: dict[str, Path] = {}
    artifact_root = campaign.get("artifact_root")
    for identifier, reference in artifact_index.items():
        relative = reference.get("path")
        if relative in artifact_paths:
            errors.append(f"duplicate artifact path: {relative}")
        elif isinstance(relative, str):
            artifact_paths[relative] = identifier
        if not isinstance(relative, str) or not relative.startswith(
            f"{artifact_root}/"
        ):
            errors.append(f"artifact {identifier} is outside artifact_root")
            continue
        path = safe_pack_file(pack, relative, f"artifact {identifier}", errors)
        if path is None:
            continue
        artifact_files[identifier] = path
        content = path.read_bytes()
        if not content:
            errors.append(f"artifact {identifier} is empty")
        if reference.get("sha256") != digest_bytes(content):
            errors.append(f"artifact {identifier} sha256 mismatch")
        if reference.get("bytes") != len(content):
            errors.append(f"artifact {identifier} byte count mismatch")

    campaign_relative_path = campaign_path.relative_to(pack).as_posix()
    artifact_root_path = pack / str(artifact_root)
    declared_paths = set(artifact_paths)
    if artifact_root_path.is_dir():
        for current, directories, files in os.walk(
            artifact_root_path, followlinks=False
        ):
            current_path = Path(current)
            for name in tuple(directories):
                child = current_path / name
                if child.is_symlink():
                    errors.append(
                        f"artifact closure contains symlink directory: {child.relative_to(pack)}"
                    )
            for name in files:
                child = current_path / name
                relative = child.relative_to(pack).as_posix()
                if child.is_symlink():
                    errors.append(f"artifact closure contains symlink: {relative}")
                elif (
                    relative != campaign_relative_path
                    and relative not in declared_paths
                ):
                    errors.append(
                        f"undeclared artifact in campaign closure: {relative}"
                    )
    else:
        errors.append("frontend campaign artifact_root is missing")

    used_artifact_ids: set[str] = set()
    engine_campaign_id = campaign.get("engine_campaign_artifact_id")
    used_artifact_ids.add(str(engine_campaign_id))
    if artifact_index.get(str(engine_campaign_id), {}).get("role") != "engine-campaign":
        errors.append("engine campaign artifact role mismatch")

    profile_index: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(campaign.get("profiles", [])):
        if not isinstance(entry, dict) or not isinstance(entry.get("profile"), dict):
            continue
        profile = entry["profile"]
        profile_id = profile.get("id")
        if profile_id in profile_index:
            errors.append(f"duplicate frontend profile: {profile_id}")
            continue
        profile_index[str(profile_id)] = entry
        if expected.get(str(profile_id)) != profile:
            errors.append(f"frontend profile tuple drift: {profile_id}")
        expected_digest = canonical_digest(profile)
        if entry.get("profile_digest") != expected_digest:
            errors.append(f"frontend profile digest mismatch: {profile_id}")
        artifact_ids = entry.get("artifact_ids", [])
        project_files = entry.get("project_files", [])
        if not isinstance(artifact_ids, list) or not isinstance(project_files, list):
            continue
        used_artifact_ids.update(str(item) for item in artifact_ids)
        project_map: dict[str, str] = {}
        project_artifact_ids: set[str] = set()
        for file_entry in project_files:
            if not isinstance(file_entry, dict):
                continue
            relative_path = file_entry.get("relative_path")
            artifact_id = file_entry.get("artifact_id")
            if relative_path in project_map:
                errors.append(
                    f"profile {profile_id} duplicate project file: {relative_path}"
                )
                continue
            if artifact_id not in artifact_ids:
                errors.append(
                    f"profile {profile_id} project file is not artifact-bound"
                )
                continue
            file_path = artifact_files.get(str(artifact_id))
            if file_path is None:
                errors.append(
                    f"profile {profile_id} project artifact is missing: {artifact_id}"
                )
                continue
            try:
                project_map[str(relative_path)] = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append(
                    f"profile {profile_id} project file is not UTF-8: {relative_path}"
                )
            project_artifact_ids.add(str(artifact_id))
        if len(project_artifact_ids) != len(project_files):
            errors.append(
                f"profile {profile_id} project file artifact set is not exact"
            )
        if entry.get("project_digest") != canonical_digest(project_map):
            errors.append(f"profile {profile_id} project digest mismatch")
    if set(profile_index) != set(PROFILE_IDS):
        errors.append("frontend profile closure is not the exact nine profiles")

    semantic_blocks = campaign.get("semantic_blocks", [])
    route_index = unique_index(campaign.get("routes"), "route_id", "route", errors)
    if set(route_index) != exact_routes():
        missing = sorted(exact_routes() - set(route_index))
        extra = sorted(set(route_index) - exact_routes())
        errors.append(
            f"frontend route closure is not exact: missing={missing} extra={extra}"
        )

    implementation = campaign.get("implementation", {})
    replay = campaign.get("replay", {})
    implementation_ids = implementation.get("artifact_ids", [])
    replay_ids = replay.get("artifact_ids", [])
    if isinstance(implementation_ids, list):
        used_artifact_ids.update(str(item) for item in implementation_ids)
    if isinstance(replay_ids, list):
        used_artifact_ids.update(str(item) for item in replay_ids)
    used_artifact_ids.add(str(implementation.get("manifest_artifact_id")))
    used_artifact_ids.add(str(replay.get("manifest_artifact_id")))
    computed_implementation = bundle_fingerprint(
        [str(item) for item in implementation_ids]
        if isinstance(implementation_ids, list)
        else [],
        artifact_index,
    )
    computed_replay = bundle_fingerprint(
        [str(item) for item in replay_ids] if isinstance(replay_ids, list) else [],
        artifact_index,
    )
    if computed_implementation != implementation.get("fingerprint"):
        errors.append("stale implementation fingerprint")
    if computed_replay != replay.get("fingerprint"):
        errors.append("stale replay fingerprint")
    for bundle_name, bundle, expected_role in (
        ("implementation", implementation, "implementation-manifest"),
        ("replay", replay, "replay-manifest"),
    ):
        manifest_id = str(bundle.get("manifest_artifact_id"))
        if artifact_index.get(manifest_id, {}).get("role") != expected_role:
            errors.append(f"{bundle_name} manifest artifact role mismatch")
            continue
        manifest_file = artifact_files.get(manifest_id)
        if manifest_file is None:
            continue
        try:
            bundle_manifest = load_json(manifest_file)
        except Exception as exc:
            errors.append(f"{bundle_name} manifest is invalid: {exc}")
            continue
        if bundle_manifest.get("artifact_ids") != bundle.get("artifact_ids"):
            errors.append(f"{bundle_name} manifest artifact closure drift")
        if bundle_manifest.get("fingerprint") != bundle.get("fingerprint"):
            errors.append(f"{bundle_name} manifest fingerprint drift")
        manifest_files = bundle_manifest.get("files")
        if not isinstance(manifest_files, list):
            errors.append(f"{bundle_name} manifest files are missing")
            continue
        manifest_file_ids: set[str] = set()
        repository_paths: set[str] = set()
        for index, row in enumerate(manifest_files):
            if not isinstance(row, dict) or set(row) != {
                "repository_path",
                "captured_path",
                "artifact_id",
            }:
                errors.append(f"{bundle_name} manifest file {index} is invalid")
                continue
            repository_path = row.get("repository_path")
            captured_path = row.get("captured_path")
            artifact_id = str(row.get("artifact_id"))
            if repository_path in repository_paths:
                errors.append(
                    f"{bundle_name} duplicate repository path: {repository_path}"
                )
            repository_paths.add(str(repository_path))
            manifest_file_ids.add(artifact_id)
            reference = artifact_index.get(artifact_id, {})
            if (
                artifact_id not in bundle.get("artifact_ids", [])
                or reference.get("path") != captured_path
            ):
                errors.append(
                    f"{bundle_name} manifest captured path drift: {artifact_id}"
                )
            if not isinstance(repository_path, str):
                continue
            if not portable_evidence_only:
                live_path = repo_root / repository_path
                if live_path.is_file() and not live_path.is_symlink():
                    live_content = live_path.read_bytes()
                    if reference.get("sha256") != digest_bytes(
                        live_content
                    ) or reference.get("bytes") != len(live_content):
                        errors.append(
                            f"stale {bundle_name} live repository capture: {repository_path}"
                        )
        required_paths = (
            REQUIRED_IMPLEMENTATION_REPOSITORY_PATHS
            if bundle_name == "implementation"
            else REQUIRED_REPLAY_REPOSITORY_PATHS
        )
        if repository_paths != required_paths:
            errors.append(
                f"{bundle_name} repository source closure is not exact: "
                f"missing={sorted(required_paths - repository_paths)} "
                f"extra={sorted(repository_paths - required_paths)}"
            )
        if manifest_file_ids != set(bundle.get("artifact_ids", [])):
            errors.append(f"{bundle_name} manifest file closure drift")

    toolchain_context = validate_toolchain_evidence(
        campaign,
        profile_index,
        route_index,
        artifact_index,
        artifact_files,
        used_artifact_ids,
        errors,
    )

    corpora = campaign.get("corpora", {})
    corpus_case_sets: dict[str, set[str]] = {}
    corpus_ids: set[str] = set()
    for kind in CORPUS_KINDS:
        corpus = corpora.get(kind, {}) if isinstance(corpora, dict) else {}
        corpus_id = corpus.get("id")
        if corpus_id in corpus_ids:
            errors.append(f"duplicate corpus id: {corpus_id}")
        corpus_ids.add(str(corpus_id))
        case_ids = corpus.get("case_ids", [])
        corpus_case_sets[kind] = set(case_ids) if isinstance(case_ids, list) else set()
        if corpus.get("status") == "PASSED" and not case_ids:
            errors.append(f"{kind} corpus cannot PASS with zero cases")
        manifest_id = str(corpus.get("manifest_artifact_id"))
        used_artifact_ids.add(manifest_id)
        if artifact_index.get(manifest_id, {}).get("role") != "corpus-manifest":
            errors.append(f"{kind} corpus manifest role mismatch")
        manifest_file = artifact_files.get(manifest_id)
        if manifest_file is not None:
            try:
                corpus_manifest = load_json(manifest_file)
                if (
                    corpus_manifest.get("id") != corpus_id
                    or corpus_manifest.get("status") != corpus.get("status")
                    or corpus_manifest.get("case_ids") != case_ids
                ):
                    errors.append(f"{kind} corpus manifest linkage drift")
            except Exception as exc:
                errors.append(f"{kind} corpus manifest is invalid: {exc}")
    for index, left in enumerate(CORPUS_KINDS):
        for right in CORPUS_KINDS[index + 1 :]:
            overlap = sorted(corpus_case_sets[left] & corpus_case_sets[right])
            if overlap:
                errors.append(f"corpus overlap {left}/{right}: {overlap}")

    independent = campaign.get("independent_verification", {})
    independent_ids = independent.get("artifact_ids", [])
    if isinstance(independent_ids, list):
        used_artifact_ids.update(str(item) for item in independent_ids)
    if independent.get("status") == "PASSED":
        if not independent.get("verifier") or not independent_ids:
            errors.append("independent verification PASS lacks verifier/evidence")
        if independent.get("verifier") in {
            pack_manifest.get("owner"),
            pack_manifest.get("maintenance_owner"),
        }:
            errors.append("independent verifier is not independent from pack ownership")

    route_formal_statuses: list[str] = []
    native_routes = 0
    layer_failures = False
    for route_id, route in route_index.items():
        source = route.get("source_profile_id")
        target = route.get("target_profile_id")
        if source == target:
            errors.append(f"self route is forbidden: {route_id}")
        if route_id != f"{source}--to--{target}":
            errors.append(f"route identity drift: {route_id}")
        source_entry = profile_index.get(str(source), {})
        target_entry = profile_index.get(str(target), {})
        for key, expected_value in (
            ("source_profile_digest", source_entry.get("profile_digest")),
            ("target_profile_digest", target_entry.get("profile_digest")),
            ("source_project_digest", source_entry.get("project_digest")),
            ("target_project_digest", target_entry.get("project_digest")),
        ):
            if route.get(key) != expected_value:
                errors.append(f"route {route_id} {key} drift")
        route_artifact_ids = set(str(item) for item in route.get("artifact_ids", []))
        used_artifact_ids.update(route_artifact_ids)
        wrapper_id = str(route.get("route_evidence_artifact_id"))
        if wrapper_id not in route_artifact_ids:
            errors.append(f"route {route_id} evidence wrapper is not route-bound")
            continue
        if artifact_index.get(wrapper_id, {}).get("role") != "frontend-route-evidence":
            errors.append(f"route {route_id} evidence wrapper role mismatch")
            continue
        wrapper_file = artifact_files.get(wrapper_id)
        if wrapper_file is None:
            continue
        try:
            wrapper = load_json(wrapper_file)
            schema_errors = validate_schema_subset(wrapper, route_schema, route_schema)
            if schema_errors:
                errors.extend(
                    f"route {route_id} evidence schema violation: {message}"
                    for message in schema_errors
                )
                continue
            if jsonschema is not None:
                jsonschema.validate(wrapper, route_schema)
        except Exception as exc:
            errors.append(f"route {route_id} evidence schema violation: {exc}")
            continue
        for key, expected_value in (
            ("route_id", route_id),
            ("source_profile_id", source),
            ("target_profile_id", target),
            ("source_profile_digest", route.get("source_profile_digest")),
            ("target_profile_digest", route.get("target_profile_digest")),
            ("implementation_fingerprint", implementation.get("fingerprint")),
            ("replay_fingerprint", replay.get("fingerprint")),
        ):
            if wrapper.get(key) != expected_value:
                errors.append(f"route {route_id} wrapper {key} drift")
        expected_corpus_ids = {
            kind: corpora.get(kind, {}).get("id") for kind in CORPUS_KINDS
        }
        if wrapper.get("corpus_ids") != expected_corpus_ids:
            errors.append(f"route {route_id} corpus binding drift")
        wrapper_refs = wrapper.get("artifact_refs", [])
        wrapper_ref_index = unique_index(
            wrapper_refs, "id", f"route {route_id} ref", errors
        )
        expected_wrapper_ids = route_artifact_ids - {wrapper_id}
        if set(wrapper_ref_index) != expected_wrapper_ids:
            errors.append(f"route {route_id} wrapper artifact closure is not exact")
        for identifier, reference in wrapper_ref_index.items():
            if reference != artifact_index.get(identifier):
                errors.append(
                    f"route {route_id} wrapper artifact ref drift: {identifier}"
                )
        wrapper_blocks = unique_index(
            wrapper.get("semantic_blocks"),
            "block_id",
            f"route {route_id} semantic block",
            errors,
        )
        if set(wrapper_blocks) != set(semantic_blocks):
            errors.append(f"route {route_id} semantic block closure is not exact")
        for block_id, block in wrapper_blocks.items():
            hashes = []
            for name in ("canonical_ir", "source_relift_ir", "target_relift_ir"):
                value_hash = validate_span_ref(
                    block.get(name),
                    label=f"route {route_id} block {block_id} {name}",
                    artifacts=artifact_index,
                    artifact_files=artifact_files,
                    route_artifact_ids=route_artifact_ids,
                    errors=errors,
                )
                if value_hash is not None:
                    hashes.append(value_hash)
            source_code_digest = validate_code_span_ref(
                block.get("source_code"),
                label=f"route {route_id} block {block_id} source_code",
                expected_role="source-code",
                artifacts=artifact_index,
                artifact_files=artifact_files,
                route_artifact_ids=route_artifact_ids,
                errors=errors,
            )
            target_code_digest = validate_code_span_ref(
                block.get("target_code"),
                label=f"route {route_id} block {block_id} target_code",
                expected_role="target-code",
                artifacts=artifact_index,
                artifact_files=artifact_files,
                route_artifact_ids=route_artifact_ids,
                errors=errors,
            )
            validate_relift_code_binding(
                block.get("source_relift_ir"),
                binding_group="code_spans",
                binding_id=block_id,
                code_digest=source_code_digest,
                label=f"route {route_id} block {block_id} source",
                artifact_files=artifact_files,
                errors=errors,
            )
            validate_relift_code_binding(
                block.get("target_relift_ir"),
                binding_group="code_spans",
                binding_id=block_id,
                code_digest=target_code_digest,
                label=f"route {route_id} block {block_id} target",
                artifact_files=artifact_files,
                errors=errors,
            )
            if block.get("status") == "PASSED":
                if len(set(hashes)) != 1 or block.get("semantic_hash") not in set(
                    hashes
                ):
                    errors.append(
                        f"route {route_id} block {block_id} semantic PASS drift"
                    )
        chunks = wrapper.get("chunk_equivalence", {})
        chunk_id = chunks.get("artifact_id")
        if artifact_index.get(str(chunk_id), {}).get("role") != "chunk-map":
            errors.append(f"route {route_id} chunk artifact role mismatch")
        mappings = chunks.get("mappings", [])
        chunk_file = artifact_files.get(str(chunk_id))
        if chunk_file is not None:
            try:
                chunk_payload = load_json(chunk_file)
                if (
                    chunk_payload.get("route_id") != route_id
                    or chunk_payload.get("path_scheme") != "rfc6901-json-pointer-v1"
                    or chunk_payload.get("mappings") != mappings
                    or chunk_payload.get("status") != chunks.get("status")
                ):
                    errors.append(f"route {route_id} chunk artifact linkage drift")
            except Exception as exc:
                errors.append(f"route {route_id} chunk artifact is invalid: {exc}")
        mapped_blocks: set[str] = set()
        if isinstance(mappings, list):
            seen_chunks: set[str] = set()
            for mapping in mappings:
                if not isinstance(mapping, dict):
                    continue
                identifier = mapping.get("chunk_id")
                if identifier in seen_chunks:
                    errors.append(f"route {route_id} duplicate chunk id: {identifier}")
                seen_chunks.add(str(identifier))
                mapped_blocks.add(str(mapping.get("semantic_block")))
                hashes = []
                for name in ("canonical", "source", "target"):
                    value_hash = validate_span_ref(
                        mapping.get(name),
                        label=f"route {route_id} chunk {identifier} {name}",
                        artifacts=artifact_index,
                        artifact_files=artifact_files,
                        route_artifact_ids=route_artifact_ids,
                        errors=errors,
                    )
                    if value_hash is not None:
                        hashes.append(value_hash)
                source_code_digest = validate_code_span_ref(
                    mapping.get("source_code"),
                    label=f"route {route_id} chunk {identifier} source_code",
                    expected_role="source-code",
                    artifacts=artifact_index,
                    artifact_files=artifact_files,
                    route_artifact_ids=route_artifact_ids,
                    errors=errors,
                )
                target_code_digest = validate_code_span_ref(
                    mapping.get("target_code"),
                    label=f"route {route_id} chunk {identifier} target_code",
                    expected_role="target-code",
                    artifacts=artifact_index,
                    artifact_files=artifact_files,
                    route_artifact_ids=route_artifact_ids,
                    errors=errors,
                )
                validate_relift_code_binding(
                    mapping.get("source"),
                    binding_group="chunk_spans",
                    binding_id=str(identifier),
                    code_digest=source_code_digest,
                    label=f"route {route_id} chunk {identifier} source",
                    artifact_files=artifact_files,
                    errors=errors,
                )
                validate_relift_code_binding(
                    mapping.get("target"),
                    binding_group="chunk_spans",
                    binding_id=str(identifier),
                    code_digest=target_code_digest,
                    label=f"route {route_id} chunk {identifier} target",
                    artifact_files=artifact_files,
                    errors=errors,
                )
                if mapping.get("status") == "PASSED" and (
                    len(set(hashes)) != 1
                    or mapping.get("semantic_hash") not in set(hashes)
                ):
                    errors.append(f"route {route_id} chunk {identifier} PASS drift")
        if chunks.get("status") == "PASSED" and (
            not mappings or mapped_blocks != set(semantic_blocks)
        ):
            errors.append(f"route {route_id} chunk PASS lacks exact semantic coverage")
        mapping_statuses = {
            mapping.get("status") for mapping in mappings if isinstance(mapping, dict)
        }
        derived_chunk_status = (
            "FAILED"
            if "FAILED" in mapping_statuses
            else "NOT_RUN"
            if "NOT_RUN" in mapping_statuses
            else "PASSED"
            if mapping_statuses
            else "NOT_RUN"
        )
        if chunks.get("status") != derived_chunk_status:
            errors.append(f"route {route_id} chunk aggregate status drift")
        validate_oracle_provenance(
            route_id, wrapper, artifact_index, artifact_files, errors
        )
        validate_behavior(
            route_id,
            wrapper,
            artifact_index,
            artifact_files,
            route_artifact_ids,
            toolchain_context,
            errors,
        )
        validate_formal(
            route_id,
            wrapper,
            route,
            artifact_index,
            artifact_files,
            route_artifact_ids,
            corpora,
            str(implementation.get("fingerprint")),
            str(replay.get("fingerprint")),
            not portable_evidence_only,
            errors,
        )
        for route_key, wrapper_key in (
            ("semantic_status", "semantic_blocks"),
            ("chunk_status", "chunk_equivalence"),
            ("behavior_status", "behavior"),
        ):
            if wrapper_key == "semantic_blocks":
                statuses = {item.get("status") for item in wrapper.get(wrapper_key, [])}
                wrapper_status = (
                    "FAILED"
                    if "FAILED" in statuses
                    else "NOT_RUN"
                    if "NOT_RUN" in statuses
                    else "PASSED"
                )
            else:
                wrapper_status = wrapper.get(wrapper_key, {}).get("status")
            if route.get(route_key) != wrapper_status:
                errors.append(f"route {route_id} {route_key} drift")
            if wrapper_status == "FAILED":
                layer_failures = True
        runtime_kinds = {
            wrapper.get("behavior", {}).get("source_runtime_kind"),
            wrapper.get("behavior", {}).get("target_runtime_kind"),
        }
        expected_runtime_status = (
            "MODEL_ONLY"
            if "model" in runtime_kinds
            else "DEVICE_PASSED"
            if "device" in runtime_kinds
            else "BROWSER_PASSED"
        )
        if wrapper.get("behavior", {}).get("status") != "PASSED":
            expected_runtime_status = "NOT_RUN"
        route_toolchain = toolchain_context.get("routes", {}).get(route_id, {})
        for key in ("source_build_status", "target_build_status"):
            if route.get(key) != route_toolchain.get(key):
                errors.append(f"route {route_id} {key} toolchain drift")
        if (
            expected_runtime_status == "BROWSER_PASSED"
            and route_toolchain.get("native_behavior_status") != "PASSED"
        ):
            errors.append(
                f"route {route_id} browser PASS lacks toolchain probe closure"
            )
            expected_runtime_status = "NOT_RUN"
        if route.get("runtime_evidence_status") != expected_runtime_status:
            errors.append(f"route {route_id} runtime evidence status drift")
        if expected_runtime_status in {"BROWSER_PASSED", "DEVICE_PASSED"}:
            native_routes += 1
        route_formal_statuses.append(str(route.get("formal_status")))

    missing_artifacts = sorted(used_artifact_ids - set(artifact_index))
    if missing_artifacts:
        errors.append(f"referenced artifacts are missing: {missing_artifacts}")
    unused_artifacts = sorted(set(artifact_index) - used_artifact_ids)
    if unused_artifacts:
        errors.append(f"unused artifact refs are forbidden: {unused_artifacts}")

    scope_value = {
        "campaign_key": campaign.get("campaign_key"),
        "version": campaign.get("version"),
        "proof_profile": campaign.get("proof_profile"),
        "profiles": [
            {
                "profile": item.get("profile"),
                "profile_digest": item.get("profile_digest"),
                "project_digest": item.get("project_digest"),
            }
            for item in campaign.get("profiles", [])
            if isinstance(item, dict)
        ],
        "semantic_blocks": semantic_blocks,
        "routes": [
            {
                key: item.get(key)
                for key in (
                    "route_id",
                    "source_profile_digest",
                    "target_profile_digest",
                    "source_project_digest",
                    "target_project_digest",
                )
            }
            for item in campaign.get("routes", [])
            if isinstance(item, dict)
        ],
        "corpus_ids": {kind: corpora.get(kind, {}).get("id") for kind in CORPUS_KINDS},
    }
    scope_digest = canonical_digest(scope_value)
    if campaign.get("peer_binding", {}).get("scope_digest") != scope_digest:
        errors.append("frontend campaign scope digest mismatch")

    bounded_proof_profile_ready = (
        len(route_formal_statuses) == 72
        and all(status in PROOF_PASSING for status in route_formal_statuses)
        and campaign.get("campaign_status") == "LOCAL_EXECUTED"
    )
    all_layers_pass = all(
        route.get("semantic_status") == "PASSED"
        and route.get("chunk_status") == "PASSED"
        and route.get("behavior_status") == "PASSED"
        for route in route_index.values()
    )
    formal_ready = (
        bounded_proof_profile_ready
        and all_layers_pass
        and not campaign.get("unsupported_semantics")
    )
    all_unconditional = (
        bounded_proof_profile_ready
        and all(status == "PROVED" for status in route_formal_statuses)
        and not campaign.get("assumptions")
        and not campaign.get("unsupported_semantics")
    )
    if campaign.get("unconditional_proof") != all_unconditional:
        errors.append("campaign unconditional proof status drift")
    if layer_failures or any(
        status in {"REFUTED", "FAILED"} for status in route_formal_statuses
    ):
        local_equivalence_status = "FAILED"
    elif formal_ready:
        local_equivalence_status = (
            "PROVED" if all_unconditional else "PROVED_UNDER_ASSUMPTIONS"
        )
    elif bounded_proof_profile_ready:
        local_equivalence_status = "PARTIAL_PROVED_UNDER_ASSUMPTIONS"
    elif campaign.get("campaign_status") == "NOT_RUN":
        local_equivalence_status = "NOT_RUN"
    else:
        local_equivalence_status = "INCOMPLETE"
    independent_status = independent.get("status", "NOT_RUN")
    external_evidence_status = (
        "PASSED"
        if independent_status == "PASSED" and native_routes == 72
        else independent_status
        if independent_status in {"FAILED", "BLOCKED"}
        else "NOT_RUN"
    )
    required_corpora_pass = all(
        corpora.get(kind, {}).get("status") == "PASSED"
        for kind in ("negative", "holdout", "representative_workloads")
    )
    certification_ready = (
        all_unconditional
        and all_layers_pass
        and native_routes == 72
        and external_evidence_status == "PASSED"
        and required_corpora_pass
        and campaign.get("certification_status") == "CERTIFIED"
    )
    if pack_manifest.get("status") == "certified" and not certification_ready:
        errors.append("certified pack lacks frontend formal certification readiness")

    if execute_replay and not errors:
        command = replay.get("command")
        expected_command = [
            "python3",
            "formal-campaign/replay/validate_frontend_formal_route_campaign.py",
            ".",
            "--campaign",
            campaign_relative_path,
            "--schema",
            "formal-campaign/replay/schemas/batch32/frontend-formal-route-campaign.schema.json",
            "--route-schema",
            "formal-campaign/replay/schemas/batch32/frontend-formal-route-evidence.schema.json",
            "--no-replay-execute",
            "--json",
        ]
        if command != expected_command:
            errors.append("replay command is not canonical and self-contained")
        else:
            try:
                completed = subprocess.run(
                    command,
                    cwd=pack,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                replay_result = json.loads(completed.stdout.strip().splitlines()[-1])
                if completed.returncode or replay_result.get("status") != "valid":
                    errors.append("self-contained replay validation failed")
            except Exception as exc:
                errors.append(f"self-contained replay execution failed: {exc}")

    status = "invalid" if errors else "valid"
    return {
        "schema_version": 1,
        "status": status,
        "campaign_key": campaign.get("campaign_key"),
        "route_count": len(route_index),
        "profile_count": len(profile_index),
        "structural_status": "FAILED" if errors else "PASSED",
        "local_equivalence_status": local_equivalence_status,
        "bounded_proof_profile_ready": bounded_proof_profile_ready and not errors,
        "formal_ready": formal_ready and not errors,
        "external_evidence_status": external_evidence_status,
        "independent_verification_status": independent_status,
        "certification_ready": (
            certification_ready and not errors and not portable_evidence_only
        ),
        "proved_route_count": sum(
            status == "PROVED" for status in route_formal_statuses
        ),
        "proved_under_assumptions_route_count": sum(
            status == "PROVED_UNDER_ASSUMPTIONS" for status in route_formal_statuses
        ),
        "native_route_count": native_routes,
        "scope_digest": scope_digest,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_dir")
    parser.add_argument("--campaign")
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--route-schema", type=Path)
    parser.add_argument("--no-replay-execute", action="store_true")
    parser.add_argument(
        "--portable-evidence-only",
        action="store_true",
        help=(
            "validate captured, digest-bound evidence without comparing live "
            "repository bytes or executing the receipt-bound solver; does not "
            "confer certification"
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
    )
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif result["status"] == "valid":
        print(
            "OK: frontend formal route campaign "
            f"routes={result['route_count']} "
            f"local={result['local_equivalence_status']} "
            f"certification_ready={str(result['certification_ready']).lower()}"
        )
    else:
        print("\n".join("ERROR: " + item for item in result["errors"]), file=sys.stderr)
    return 0 if result["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())

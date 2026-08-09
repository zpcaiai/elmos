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
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


CLIENT_KEY = "frontend-72-route-equivalence-v1"
VERIFICATION_KEY = "frontend-72-route-formal-equivalence-v1"
CAMPAIGN_KEY = "frontend-72-route-formal-equivalence-v1"
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
    relative = "formal-campaign/environment/z3-4.16.0.bin"
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

    source = evidence_path.resolve(strict=True)
    if source.is_symlink() or not source.is_file():
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
    identity_core = {
        "producer": raw["producer"],
        "campaign_sha256": raw_campaign_sha,
        "policy": raw.get("policy"),
        "profile_execution_ids": [
            profile_executions[item]["execution_id"]
            for item in sorted(profile_executions)
        ],
        "route_execution_bindings": [
            {
                "route_id": item,
                "source_execution_id": route_records[item]["source_execution_id"],
                "target_execution_id": route_records[item]["target_execution_id"],
                "status": route_records[item]["status"],
            }
            for item in sorted(route_records)
        ],
    }
    if raw.get("evidence_identity") != {
        "sha256": canonical_digest(identity_core),
        "scope": "producer+campaign+policy+profile-executions+route-bindings",
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
    ).encode("utf-8") + raw_smt
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


def run_checked(command: list[str], *, cwd: Path) -> None:
    completed = subprocess.run(
        command, cwd=cwd, text=True, capture_output=True, check=False
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
        if (
            gate.get("structural_status") != "PASSED"
            or gate.get("certification_decision") != "NOT_CERTIFIED"
        ):
            raise RuntimeError(f"GATE_BOUNDARY_DRIFT:{pack}")
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
    parser.add_argument(
        "--engine-cli",
        default="engines/frontend-client-engine/dist/src/frontend-formal-cli.js",
    )
    parser.add_argument("--engine-output", type=Path)
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
    repo_root = Path(args.repo_root).resolve()
    client_target = repo_root / "client-packs" / CLIENT_KEY
    verification_target = repo_root / "verification-packs" / VERIFICATION_KEY
    if not args.force and (client_target.exists() or verification_target.exists()):
        raise SystemExit("output exists; pass --force to refresh the paired packs")

    with tempfile.TemporaryDirectory(
        prefix=".frontend-formal-pack-stage-", dir=repo_root
    ) as directory:
        staging_root = Path(directory)
        if args.engine_output is None:
            engine_root = staging_root / "engine-output"
            engine_cli = Path(args.engine_cli)
            if not engine_cli.is_absolute():
                engine_cli = repo_root / engine_cli
            run_checked(
                [args.node, str(engine_cli), "--output", str(engine_root)],
                cwd=repo_root,
            )
        else:
            engine_root = args.engine_output.resolve(strict=True)
        client_pack, verification_pack = build_packs(
            repo_root,
            engine_root,
            staging_root,
            toolchain_evidence_path=(
                args.toolchain_evidence.resolve(strict=True)
                if args.toolchain_evidence is not None
                else None
            ),
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

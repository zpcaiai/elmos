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
from urllib.request import ProxyHandler, build_opener

SCHEMA_VERSION = "1.0"
CAMPAIGN_KIND = "frontend-formal-route-campaign"
PROOF_PROFILE = "bounded-navigation-v1"
OUTPUT_KIND = "frontend-formal-toolchain-evidence"
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
EXACT_VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+){2}(?:[-+][0-9A-Za-z.-]+)?$")
MAX_LOG_BYTES = 64 * 1024
RUNNER_PATH = Path(__file__).resolve()
REPOSITORY_ROOT = RUNNER_PATH.parents[1]
LOCKED_Z3_VERSION = "Z3 version 4.16.0 - 64 bit"
LOCKED_Z3_BINARY_SHA256 = (
    "sha256:537a502af2f4013a8e887beebe525a0dae84918a61ff545991e36dfda07ed6d7"
)
LOCKED_Z3_ARGS = ["-in"]
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


@dataclass(frozen=True)
class LoadedCampaign:
    path: Path
    root: Path
    digest: str
    byte_count: int
    profiles: Mapping[str, ProfileArtifact]
    routes: tuple[dict[str, Any], ...]


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
) -> dict[str, Any]:
    """Validate and replay the immutable locked-Z3 result for one route."""

    solver = require_exact_keys(
        read_json(solver_path, f"{route_id} solver result"),
        SOLVER_RESULT_KEYS,
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
    return solver


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


def load_campaign(path: Path) -> LoadedCampaign:
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


@dataclass
class RunnerPolicy:
    no_network: bool
    timeout_seconds: int
    selected_profiles: frozenset[str]
    fail_on_unavailable: bool
    flutter_path: str = "/opt/homebrew/bin/flutter"
    chrome_path: str = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    harmony_tool: str | None = None
    producer_path: str = str(RUNNER_PATH)
    producer_digest: str = dataclass_field(
        default_factory=lambda: sha256_bytes(RUNNER_PATH.read_bytes())
    )
    producer_byte_count: int = dataclass_field(
        default_factory=lambda: len(RUNNER_PATH.read_bytes())
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


def execute_node_profile(
    profile: ProfileArtifact, workspace: Path, policy: RunnerPolicy
) -> dict[str, Any]:
    tool_versions, version_error = node_tool_versions(workspace, policy)
    commands: list[dict[str, Any]] = []
    if version_error:
        unavailable = version_error.endswith("UNAVAILABLE")
        return profile_result(
            profile,
            "NOT_RUN" if unavailable else "FAILED",
            version_error,
            tool_versions,
            commands,
            workspace,
            policy,
        )
    npm = tool_versions[1]["argv"][0]
    empty_user_config = workspace / ".elmos-empty-npmrc"
    empty_user_config.write_text(
        "# isolated by ELMOS toolchain runner\n", encoding="utf-8"
    )
    npm_env = {
        "CI": "1",
        "NO_COLOR": "1",
        "npm_config_audit": "false",
        "npm_config_fund": "false",
        "npm_config_ignore_scripts": "true",
        "npm_config_package_lock": "true",
        "npm_config_userconfig": str(empty_user_config),
        **({"npm_config_offline": "true"} if policy.no_network else {}),
    }
    offline = ["--offline"] if policy.no_network else []
    lock = run_command(
        [
            npm,
            "install",
            "--package-lock-only",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            *offline,
        ],
        cwd=workspace,
        timeout_seconds=policy.timeout_seconds,
        no_network=policy.no_network,
        explicit_env=npm_env,
    )
    commands.append(lock)
    if lock["status"] != "PASSED" or not (workspace / "package-lock.json").is_file():
        offline_unavailable = policy.no_network and any(
            marker in (lock[stream]["text"] or "")
            for stream in ("stdout", "stderr")
            for marker in ("ENOTCACHED", "offline mode", "cache miss")
        )
        return profile_result(
            profile,
            "NOT_RUN" if offline_unavailable else "FAILED",
            "OFFLINE_DEPENDENCY_LOCK_UNAVAILABLE"
            if offline_unavailable
            else "PACKAGE_LOCK_FAILED",
            tool_versions,
            commands,
            workspace,
            policy,
        )
    ci = run_command(
        [npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund", *offline],
        cwd=workspace,
        timeout_seconds=policy.timeout_seconds,
        no_network=policy.no_network,
        explicit_env=npm_env,
    )
    commands.append(ci)
    if ci["status"] != "PASSED":
        offline_unavailable = policy.no_network and any(
            marker in (ci[stream]["text"] or "")
            for stream in ("stdout", "stderr")
            for marker in ("ENOTCACHED", "offline mode", "cache miss")
        )
        return profile_result(
            profile,
            "NOT_RUN" if offline_unavailable else "FAILED",
            "OFFLINE_DEPENDENCIES_UNAVAILABLE"
            if offline_unavailable
            else "NPM_CI_FAILED",
            tool_versions,
            commands,
            workspace,
            policy,
        )
    for command in EXPECTED_NODE_PACKAGES[profile.profile_id]["commands"]:
        record = run_command(
            [npm, "run", *command],
            cwd=workspace,
            timeout_seconds=policy.timeout_seconds,
            no_network=policy.no_network,
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
        return profile_result(
            profile,
            "NOT_RUN",
            "FLUTTER_TOOLCHAIN_UNAVAILABLE",
            tool_versions,
            [],
            workspace,
            policy,
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
        (["test", "--no-pub"], "FLUTTER_TEST_FAILED"),
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
    configured = policy.harmony_tool
    project_wrapper = workspace / "hvigorw"
    tool = configured or (
        str(project_wrapper) if project_wrapper.is_file() else "hvigorw"
    )
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
                target_build_status=(
                    "FAILED" if args[0] == "assembleHap" else "NOT_RUN"
                ),
            )
    return profile_result(
        profile, "PASSED", None, [version], commands, workspace, policy
    )


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
        "commands": list(commands),
        "browser_journey": dict(browser_journey),
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
    profile_results: dict[str, dict[str, Any]] = {}
    digest_results: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(
        prefix="elmos-frontend-formal-toolchains-"
    ) as temporary:
        workspace_root = Path(temporary)
        for profile_id in sorted(campaign.profiles):
            profile = campaign.profiles[profile_id]
            if profile_id not in policy.selected_profiles:
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
        route_records.append(
            {
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
        )
    values = list(profile_results.values())
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "kind": OUTPUT_KIND,
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
            "proof_profile": PROOF_PROFILE,
            "profile_count": len(campaign.profiles),
            "route_count": len(campaign.routes),
        },
        "policy": {
            "no_network": policy.no_network,
            "timeout_seconds": policy.timeout_seconds,
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
        "campaign_sha256": campaign.digest,
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
            }
            for item in evidence["route_records"]
        ],
    }
    evidence["evidence_identity"] = {
        "sha256": digest_json(identity_core),
        "scope": "producer+campaign+policy+profile-executions+route-bindings",
    }
    return evidence


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
    value.add_argument("--fail-on-unavailable", action="store_true")
    value.add_argument(
        "--chrome-path",
        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    )
    value.add_argument("--harmony-tool")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.timeout_seconds < 1 or arguments.timeout_seconds > 3600:
        parser().error("--timeout-seconds must be between 1 and 3600")
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
            chrome_path=arguments.chrome_path,
            harmony_tool=arguments.harmony_tool,
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
            "--chrome-path",
            policy.chrome_path,
            *(["--fail-on-unavailable"] if policy.fail_on_unavailable else []),
            *(["--harmony-tool", policy.harmony_tool] if policy.harmony_tool else []),
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

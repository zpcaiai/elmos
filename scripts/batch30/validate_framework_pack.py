#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_PACK = [
    "schema_version",
    "pack_key",
    "version",
    "mode",
    "status",
    "owner",
    "maintenance_owner",
    "source",
    "target",
    "paths",
    "gates",
]
REQUIRED_DIRS = [
    "source-fingerprint",
    "contracts",
    "target-profile",
    "recipes",
    "adapters",
    "compatibility",
    "corpus/development",
    "corpus/holdout",
    "corpus/real-repository",
    "certification",
]
ALLOWED_PACK_STATUS = {"research", "experimental", "limited", "certified", "deprecated", "blocked"}
ALLOWED_CAP_STATUS = {"certified", "supported", "conditional", "experimental", "detected-only", "blocked"}
ALLOWED_MODES = {"migration", "upgrade", "modernization", "coexistence"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_BOUND_EVIDENCE_BYTES = 16 * 1024 * 1024
SUPPORTED_SEMANTIC_VALIDATORS = {"web", "configuration", "lifecycle"}
EXPECTED_FCM_IDS = {
    "web": {"web-json-contract"},
    "configuration": {"configuration-runtime-contract"},
    "lifecycle": {"health-lifecycle"},
}
EXPECTED_BINDING_ROLES = {
    "web": {"runtime-equivalence"},
    "configuration": {
        "runtime-equivalence",
        "source-configuration",
        "target-configuration",
    },
    "lifecycle": {"runtime-equivalence"},
}
RUNTIME_EVIDENCE_PATH = "certification/local-reference-evidence.json"
CONFIGURATION_BINDING_PATHS = {
    "source-configuration": (
        "corpus/development/source/src/main/resources/application.properties"
    ),
    "target-configuration": (
        "corpus/development/migrated/src/main/resources/application.properties"
    ),
}
CONFIGURATION_OBLIGATIONS = {
    "management health endpoint exposure remains enabled",
    "health details remain hidden",
    "graceful shutdown remains enabled",
}
EXPECTED_CONFIGURATION_BYTES = (
    b"management.endpoints.web.exposure.include=health\n"
    b"management.endpoint.health.show-details=never\n"
    b"server.shutdown=graceful\n"
)


@dataclass(frozen=True)
class EvidenceSnapshot:
    role: str
    path: str
    raw: bytes
    json_value: dict[str, Any] | None


def load(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        raise ValueError(f"{path}: {exc}") from exc


def side_errors(label: str, side: dict) -> list[str]:
    errors = []
    for key in ["framework", "framework_versions", "runtime", "runtime_versions"]:
        if not side.get(key):
            errors.append(f"{label} missing/non-empty key: {key}")
    for field in ["framework_versions", "runtime_versions"]:
        for version in side.get(field, []):
            if str(version).strip().lower() in {"latest", "*", "x"}:
                errors.append(f"{label} uses floating {field}: {version}")
    return errors


def _read_bound_pack_file(pack: Path, reference: object) -> tuple[bytes | None, str | None]:
    if not isinstance(reference, str) or not reference.strip():
        return None, "path must be a non-empty relative path"
    relative = Path(reference)
    if relative.is_absolute() or ".." in relative.parts:
        return None, "path must stay below the framework pack"
    try:
        root = pack.resolve(strict=True)
    except OSError:
        return None, "framework pack does not exist"
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return None, "path must not contain a symbolic link"
    try:
        resolved = current.resolve(strict=True)
    except OSError:
        return None, "path does not exist"
    if not resolved.is_relative_to(root):
        return None, "path escapes the framework pack"
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                return None, "path must reference a regular file"
            if metadata.st_size <= 0 or metadata.st_size > MAX_BOUND_EVIDENCE_BYTES:
                return None, "file must be non-empty and within the evidence size limit"
            chunks: list[bytes] = []
            remaining = metadata.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 1024 * 1024))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) != metadata.st_size:
                return None, "file changed or was truncated while being read"
            return raw, None
        finally:
            os.close(descriptor)
    except OSError as exc:
        return None, f"file cannot be read safely: {exc}"


def _load_evidence_bindings(
    errors: list[str],
    pack: Path,
    capability: dict[str, Any],
    status: str,
) -> dict[str, EvidenceSnapshot]:
    capability_id = capability.get("id")
    bindings = capability.get("evidence_bindings")
    if not isinstance(bindings, list) or not bindings:
        errors.append(f"{status} capability lacks content-addressed evidence bindings: {capability_id}")
        return {}
    snapshots: dict[str, EvidenceSnapshot] = {}
    bound_paths: list[str] = []
    for index, binding in enumerate(bindings):
        label = f"{status} capability evidence binding {capability_id}[{index}]"
        if not isinstance(binding, dict) or set(binding) != {"role", "path", "sha256", "bytes"}:
            errors.append(f"{label} must contain exactly role/path/sha256/bytes")
            continue
        role = binding.get("role")
        path = binding.get("path")
        digest = binding.get("sha256")
        size = binding.get("bytes")
        if not isinstance(role, str) or not role:
            errors.append(f"{label} role is invalid")
            continue
        if role in snapshots:
            errors.append(f"{status} capability has duplicate evidence role: {capability_id}: {role}")
            continue
        if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
            errors.append(f"{label} sha256 is invalid")
            continue
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            errors.append(f"{label} bytes must be a positive integer")
            continue
        raw, read_error = _read_bound_pack_file(pack, path)
        if read_error:
            errors.append(f"{label} {read_error}")
            continue
        assert raw is not None
        if len(raw) != size:
            errors.append(f"{label} bytes mismatch")
            continue
        if hashlib.sha256(raw).hexdigest() != digest:
            errors.append(f"{label} sha256 mismatch")
            continue
        json_value = None
        if role == "runtime-equivalence":
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"{label} must be UTF-8 JSON: {exc}")
                continue
            if not isinstance(parsed, dict):
                errors.append(f"{label} JSON must be an object")
                continue
            json_value = parsed
        snapshots[role] = EvidenceSnapshot(role, str(path), raw, json_value)
        bound_paths.append(str(path))
    evidence_refs = capability.get("evidence_refs")
    if not isinstance(evidence_refs, list) or sorted(evidence_refs) != sorted(bound_paths):
        errors.append(f"{status} capability evidence refs and bindings differ: {capability_id}")
    return snapshots


def _exact_version(side: dict[str, Any], field: str) -> str | None:
    values = side.get(field)
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str):
        return None
    return values[0]


def _validate_v2_tuple_bindings(
    errors: list[str],
    manifest: dict[str, Any],
    profile: dict[str, Any],
    fcm: dict[str, Any],
) -> None:
    source = manifest.get("source", {})
    target = manifest.get("target", {})
    source_version = _exact_version(source, "framework_versions")
    source_runtime_version = _exact_version(source, "runtime_versions")
    target_version = _exact_version(target, "framework_versions")
    target_runtime_version = _exact_version(target, "runtime_versions")
    if None in {source_version, source_runtime_version}:
        errors.append("v2 supported capability requires one exact source framework/runtime tuple")
    expected_fcm_tuple = {
        "framework": source.get("framework"),
        "version": source_version,
        "runtime": source.get("runtime"),
        "runtime_version": source_runtime_version,
    }
    if fcm.get("exact_tuple") != expected_fcm_tuple:
        errors.append("v2 FCM exact_tuple does not match the pack source tuple")
    if None in {target_version, target_runtime_version}:
        errors.append("v2 supported capability requires one exact target framework/runtime tuple")
    if (
        profile.get("framework") != target.get("framework")
        or profile.get("framework_versions") != [target_version]
        or profile.get("runtime") != target.get("runtime")
        or profile.get("runtime_versions") != [target_runtime_version]
    ):
        errors.append("v2 target profile does not match the pack target tuple")


def _validate_fcm_bindings(
    errors: list[str],
    capability: dict[str, Any],
    status: str,
    fcm_by_id: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    capability_id = capability.get("id")
    bound_ids = capability.get("fcm_capability_ids")
    if not isinstance(bound_ids, list) or not bound_ids:
        errors.append(f"{status} capability lacks FCM bindings: {capability_id}")
        return []
    resolved: list[dict[str, Any]] = []
    missing: list[object] = []
    for fcm_id in bound_ids:
        matches = fcm_by_id.get(fcm_id, []) if isinstance(fcm_id, str) else []
        if len(matches) != 1:
            missing.append(fcm_id)
            continue
        fcm_capability = matches[0]
        obligations = fcm_capability.get("obligations")
        traces = fcm_capability.get("source_traces")
        if (
            not isinstance(obligations, list)
            or not obligations
            or any(not isinstance(item, str) or not item.strip() for item in obligations)
        ):
            errors.append(f"bound FCM capability has no semantic obligations: {fcm_id}")
        if (
            not isinstance(traces, list)
            or not traces
            or any(not isinstance(item, str) or not item.strip() for item in traces)
        ):
            errors.append(f"bound FCM capability has no source traces: {fcm_id}")
        if fcm_capability.get("status") != "captured":
            errors.append(f"bound FCM capability status must be captured: {fcm_id}")
        resolved.append(fcm_capability)
    if missing:
        errors.append(
            f"{status} capability references unknown or duplicate FCM ids: {capability_id}: "
            + ", ".join(map(str, sorted(missing, key=str)))
        )
    return resolved


def _runtime_side_matches(
    errors: list[str],
    observed: Any,
    expected: dict[str, Any],
    label: str,
) -> dict[str, Any] | None:
    if not isinstance(observed, dict):
        errors.append(f"runtime evidence {label} side is missing")
        return None
    version = _exact_version(expected, "framework_versions")
    runtime_version = _exact_version(expected, "runtime_versions")
    if observed.get("framework") != expected.get("framework") or observed.get("version") != version:
        errors.append(f"runtime evidence {label} framework tuple mismatch")
    if expected.get("runtime") == "java":
        java = observed.get("java")
        if (
            not isinstance(java, str)
            or runtime_version is None
            or re.search(rf"\b{re.escape(runtime_version)}(?:\.|\b)", java) is None
        ):
            errors.append(f"runtime evidence {label} Java tuple mismatch")
    if observed.get("build") != "PASSED":
        errors.append(f"runtime evidence {label} build must be PASSED")
    runtime = observed.get("runtime")
    if not isinstance(runtime, dict) or not runtime:
        errors.append(f"runtime evidence {label} runtime record is missing")
        return None
    return runtime


def _validate_runtime_semantics(
    errors: list[str],
    capability_id: str,
    snapshot: EvidenceSnapshot | None,
    manifest: dict[str, Any],
) -> None:
    if snapshot is None or snapshot.json_value is None:
        errors.append(f"supported capability lacks runtime-equivalence evidence: {capability_id}")
        return
    if snapshot.path != RUNTIME_EVIDENCE_PATH:
        errors.append(f"runtime-equivalence evidence path is not exact: {capability_id}")
    evidence = snapshot.json_value
    if evidence.get("pack_key") != manifest.get("pack_key"):
        errors.append(f"runtime evidence pack_key mismatch: {capability_id}")
    if evidence.get("execution_status") != "PASSED_LOCAL":
        errors.append(f"runtime evidence execution_status must be PASSED_LOCAL: {capability_id}")
    source_runtime = _runtime_side_matches(errors, evidence.get("source"), manifest.get("source", {}), "source")
    target_runtime = _runtime_side_matches(errors, evidence.get("target"), manifest.get("target", {}), "target")
    if capability_id == "web":
        if evidence.get("behavioral_parity") is not True:
            errors.append("web runtime evidence behavioral_parity must be true")
        source_responses = source_runtime.get("responses") if source_runtime else None
        target_responses = target_runtime.get("responses") if target_runtime else None
        if not isinstance(source_responses, dict) or not source_responses:
            errors.append("web runtime evidence source responses must be non-empty")
        elif source_responses != target_responses:
            errors.append("web runtime evidence source/target responses differ")
    if capability_id == "lifecycle":
        for runtime, label in ((source_runtime, "source"), (target_runtime, "target")):
            if not isinstance(runtime, dict) or runtime.get("health", {}).get("status") != "UP":
                errors.append(f"lifecycle runtime evidence {label} health must be UP")


def _validate_configuration_semantics(
    errors: list[str],
    snapshots: dict[str, EvidenceSnapshot],
    fcm_capabilities: list[dict[str, Any]],
) -> None:
    obligations = {
        obligation
        for capability in fcm_capabilities
        for obligation in capability.get("obligations", [])
        if isinstance(obligation, str)
    }
    if obligations != CONFIGURATION_OBLIGATIONS:
        errors.append("configuration FCM obligations do not match the exact property contract")
    for role, expected_path in CONFIGURATION_BINDING_PATHS.items():
        snapshot = snapshots.get(role)
        if snapshot is None:
            errors.append(f"configuration capability lacks {role} evidence")
            continue
        if snapshot.path != expected_path:
            errors.append(f"configuration {role} evidence path is not exact")
        if snapshot.raw != EXPECTED_CONFIGURATION_BYTES:
            errors.append(f"configuration {role} content does not match the exact property contract")
    source = snapshots.get("source-configuration")
    target = snapshots.get("target-configuration")
    if source is not None and target is not None and source.raw != target.raw:
        errors.append("configuration source and target property bytes differ")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_dir")
    args = parser.parse_args()
    pack = Path(args.pack_dir)
    errors: list[str] = []
    if not pack.is_dir():
        errors.append(f"missing pack dir: {pack}")
    for rel in REQUIRED_DIRS:
        if not (pack / rel).exists():
            errors.append(f"missing: {pack / rel}")
    manifest = {}
    try:
        manifest = load(pack / "pack.json")
        for key in REQUIRED_PACK:
            if key not in manifest:
                errors.append(f"pack.json missing key: {key}")
        if manifest.get("status") not in ALLOWED_PACK_STATUS:
            errors.append("invalid pack status")
        if manifest.get("mode") not in ALLOWED_MODES:
            errors.append("invalid pack mode")
        if manifest.get("owner") in {"", "UNASSIGNED", None}:
            errors.append("pack owner is unassigned")
        if manifest.get("maintenance_owner") in {"", "UNASSIGNED", None}:
            errors.append("maintenance owner is unassigned")
        errors.extend(side_errors("source", manifest.get("source", {})))
        errors.extend(side_errors("target", manifest.get("target", {})))
    except Exception as exc:
        errors.append(str(exc))
    profile = {}
    try:
        profile = load(pack / "target-profile" / "profile.json")
        for key in [
            "profile_key",
            "version",
            "owner",
            "framework",
            "framework_versions",
            "runtime",
            "runtime_versions",
            "architecture_style",
            "providers",
            "build",
            "startup",
        ]:
            if not profile.get(key):
                errors.append(f"target profile missing/non-empty key: {key}")
        if profile.get("owner") in {"", "UNASSIGNED", None}:
            errors.append("target profile owner is unassigned")
    except Exception as exc:
        errors.append(str(exc))
    try:
        support = load(pack / "support-matrix.json")
        if support.get("pack_key") != manifest.get("pack_key"):
            errors.append("support matrix pack_key mismatch")
        support_schema_version = support.get("schema_version")
        if support_schema_version not in {1, 2}:
            errors.append("unsupported support matrix schema_version")
        fcm = {}
        if support_schema_version == 2:
            try:
                fcm = load(pack / "contracts" / "framework-contract-model.json")
            except Exception as exc:
                errors.append(str(exc))
        fcm_by_id: dict[str, list[dict[str, Any]]] = {}
        for fcm_capability in fcm.get("capabilities", []):
            if not isinstance(fcm_capability, dict) or not isinstance(fcm_capability.get("id"), str):
                continue
            fcm_by_id.setdefault(fcm_capability["id"], []).append(fcm_capability)
        claimed_capabilities = [
            capability
            for capability in support.get("capabilities", [])
            if isinstance(capability, dict)
            and capability.get("status") in {"certified", "supported"}
        ]
        if support_schema_version == 2 and claimed_capabilities:
            _validate_v2_tuple_bindings(errors, manifest, profile, fcm)
        ids = set()
        for capability in support.get("capabilities", []):
            cid = capability.get("id")
            if cid in ids:
                errors.append(f"duplicate capability id: {cid}")
            ids.add(cid)
            status = capability.get("status")
            if status not in ALLOWED_CAP_STATUS:
                errors.append(f"invalid capability status: {cid}")
            if status in {"certified", "supported"} and not capability.get("evidence_refs"):
                errors.append(f"{status} capability lacks evidence: {cid}")
            if support_schema_version == 2 and status in {"certified", "supported"}:
                bound_fcm_capabilities = _validate_fcm_bindings(
                    errors, capability, status, fcm_by_id
                )
                observed_fcm_ids = capability.get("fcm_capability_ids")
                if (
                    isinstance(observed_fcm_ids, list)
                    and all(isinstance(item, str) for item in observed_fcm_ids)
                    and set(observed_fcm_ids) != EXPECTED_FCM_IDS.get(cid, set())
                ):
                    errors.append(f"{status} capability FCM semantic binding mismatch: {cid}")
                if capability.get("target_profile_key") != profile.get("profile_key"):
                    errors.append(f"{status} capability target profile mismatch: {cid}")
                snapshots = _load_evidence_bindings(errors, pack, capability, status)
                if cid not in SUPPORTED_SEMANTIC_VALIDATORS:
                    errors.append(f"{status} capability lacks a semantic evidence validator: {cid}")
                else:
                    observed_roles = set(snapshots)
                    expected_roles = EXPECTED_BINDING_ROLES[cid]
                    if observed_roles != expected_roles:
                        errors.append(
                            f"{status} capability evidence roles mismatch: {cid}: "
                            f"expected={sorted(expected_roles)}, observed={sorted(observed_roles)}"
                        )
                    _validate_runtime_semantics(
                        errors,
                        cid,
                        snapshots.get("runtime-equivalence"),
                        manifest,
                    )
                    if cid == "configuration":
                        _validate_configuration_semantics(
                            errors, snapshots, bound_fcm_capabilities
                        )
            if status in {"conditional", "blocked"} and not capability.get("reason"):
                errors.append(f"conditional/blocked capability lacks reason: {cid}")
    except Exception as exc:
        errors.append(str(exc))
    for path in [
        pack / "version-matrix.json",
        pack / "source-fingerprint" / "manifest.json",
        pack / "source-fingerprint" / "evidence.json",
        pack / "compatibility" / "manifest.json",
        pack / "certification" / "evidence.json",
        pack / "certification" / "certification.json",
    ]:
        try:
            load(path)
        except Exception as exc:
            errors.append(str(exc))
    try:
        certification = load(pack / "certification" / "certification.json")
        if str(certification.get("status", "")).lower() != str(manifest.get("status", "")).lower():
            errors.append("pack and certification statuses must match")
    except Exception as exc:
        errors.append(str(exc))
    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
        return 1
    print(f"OK: {pack}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

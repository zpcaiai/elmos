#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

REQUIRED_ROUTE = [
    "schema_version",
    "route_key",
    "version",
    "status",
    "owner",
    "source",
    "target",
    "paths",
    "gates",
]
REQUIRED_DIRS = [
    "lowering",
    "mappings",
    "compat-runtime",
    "corpus/development",
    "corpus/holdout",
    "corpus/real-repository",
    "certification",
]
ALLOWED_ROUTE_STATUS = {
    "research",
    "experimental",
    "limited",
    "certified",
    "deprecated",
    "blocked",
}
ALLOWED_CAP_STATUS = {
    "certified",
    "supported",
    "conditional",
    "experimental",
    "detected-only",
    "blocked",
}
LAYER_STATUSES = {"PASSED", "FAILED", "UNKNOWN", "NOT_RUN"}
PROOF_STATUSES = {
    "PROVED",
    "PROVED_UNDER_ASSUMPTIONS",
    "AXIOM",
    "BOUNDED",
    "UNKNOWN",
    "TIMEOUT",
    "NOT_RUN",
    "COUNTEREXAMPLE",
}
CHUNK_STATUSES = {"MATCHED", "UNMATCHED", "AMBIGUOUS", "FAILED"}
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

FORMAL_REQUIRED_KEYS = {
    "schema_version",
    "route_key",
    "route_manifest_sha256",
    "semantic_profile",
    "semantic_profile_sha256",
    "artifact_sha256",
    "artifact_id",
    "environment_sha256",
    "environment_artifact_id",
    "artifact_refs",
    "semantic_ir",
    "semantic_chunks",
    "behavior_equivalence",
    "formal_proof",
}
SEMANTIC_IR_KEYS = {
    "status",
    "source_ir_artifact_id",
    "source_ir_sha256",
    "target_ir_artifact_id",
    "target_relift_ir_sha256",
    "unknown_or_dropped_nodes",
    "differences",
}
SEMANTIC_CHUNK_KEYS = {
    "status",
    "total",
    "matched",
    "unmatched",
    "ambiguous",
    "coverage",
    "evidence_artifact_ids",
    "chunks",
}
CHUNK_KEYS = {"chunk_id", "source_ref", "target_ref", "semantic_hash", "status"}
BEHAVIOR_KEYS = {
    "status",
    "total_cases",
    "passed_cases",
    "counterexamples",
    "evidence_artifact_ids",
    "source_runtime_artifact_ids",
    "target_runtime_artifact_ids",
    "canonical_oracle_passed",
    "source_runtime_passed",
    "target_runtime_passed",
}
COUNTEREXAMPLE_REQUIRED_KEYS = {"case_id", "reason"}
COUNTEREXAMPLE_ALLOWED_KEYS = COUNTEREXAMPLE_REQUIRED_KEYS | {"evidence_ref"}
FORMAL_PROOF_KEYS = {
    "status",
    "solver",
    "solver_version",
    "solver_options",
    "input_artifact_id",
    "input_digest",
    "result_artifact_ids",
    "assumptions",
    "obligations",
    "replay",
}
OBLIGATION_REQUIRED_KEYS = {
    "obligation_id",
    "status",
    "scope",
    "formal_input_artifact_id",
    "solver_input_artifact_id",
    "input_digest",
    "solver_result_artifact_id",
    "assumptions",
}
OBLIGATION_ALLOWED_KEYS = OBLIGATION_REQUIRED_KEYS | {"detail"}
REPLAY_KEYS = {
    "command",
    "cwd",
    "expected_result_artifact_id",
    "expected_result_sha256",
    "expected_exit_code",
}
ARTIFACT_REF_KEYS = {"artifact_id", "role", "path", "sha256", "bytes"}
ARTIFACT_ROLES = {
    "source-ir",
    "target-ir",
    "target-artifact",
    "environment",
    "chunk-map",
    "behavior-result",
    "formal-input",
    "solver-input",
    "solver-result",
    "proof-input-bundle",
    "formal-composition",
    "engine-source",
    "engine-source-manifest",
    "corpus-artifact",
    "replay-tool",
    "replay-schema",
}
ARTIFACT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{7,95}$")
FORMAL_INPUT_REQUIRED_KEYS = {
    "schema_version",
    "kind",
    "route",
    "claim_scope",
    "source_artifact",
    "target_artifact",
    "source_normalized_ir",
    "target_relift_normalized_ir",
    "implementation_identity",
    "analyzer_identity",
    "emitter_identity",
    "solver",
    "environment",
    "environment_assumptions",
    "unsupported_semantics",
}


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return value


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_sha256(value: object) -> str:
    encoded = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    return sha256_bytes(encoded)


def strict_evidence_requested(certification: dict[str, Any]) -> bool:
    evidence_format = certification.get("evidence_format")
    return (
        isinstance(evidence_format, int)
        and not isinstance(evidence_format, bool)
        and evidence_format >= 2
    ) or "formal_equivalence" in certification


def _is_int(value: object, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _require_exact_keys(
    failures: list[str],
    value: object,
    *,
    required: set[str],
    allowed: set[str] | None = None,
    label: str,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        failures.append(f"{label} must be an object")
        return None
    actual = set(value)
    missing = sorted(required - actual)
    extra = sorted(actual - (allowed or required))
    if missing:
        failures.append(f"{label} missing keys: {', '.join(missing)}")
    if extra:
        failures.append(f"{label} has unknown keys: {', '.join(extra)}")
    return value


def _require_nonempty_strings(
    failures: list[str], values: object, label: str
) -> list[str] | None:
    if not isinstance(values, list) or any(
        not isinstance(item, str) or not item for item in values
    ):
        failures.append(f"{label} must be an array of non-empty strings")
        return None
    return values


def _require_digest(failures: list[str], value: object, label: str) -> str | None:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        failures.append(f"{label} must be a canonical sha256 digest")
        return None
    return value


def _resolve_below(
    root: Path, relative: object, label: str, failures: list[str]
) -> Path | None:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        failures.append(f"{label} must be a non-empty route-relative path")
        return None
    root_resolved = root.resolve()
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        failures.append(f"{label} escapes the route directory: {relative}")
        return None
    return candidate


def _replay_execution_root(route: Path) -> Path:
    """Return the immutable root within which a replay command may resolve.

    Checked-in routes live below ``<repo>/routes`` and may invoke the pinned
    engine or runner from that repository.  Relocated evidence bundles keep
    their replay launcher below the route directory itself.
    """

    resolved = route.resolve()
    if resolved.parent.name == "routes":
        return resolved.parent.parent
    return resolved


def _resolve_replay_path(
    cwd: Path,
    token: str,
    execution_root: Path,
    label: str,
    failures: list[str],
) -> Path | None:
    if not token or Path(token).is_absolute() or "://" in token or "\\" in token:
        failures.append(f"{label} must be a relative POSIX path")
        return None
    candidate = (cwd / token).resolve(strict=False)
    try:
        candidate.relative_to(execution_root.resolve())
    except ValueError:
        failures.append(f"{label} escapes the replay execution root: {token}")
        return None
    if not candidate.is_file():
        failures.append(f"{label} does not exist: {token}")
        return None
    return candidate


def _resolve_replay_directory(
    cwd: Path,
    token: str,
    execution_root: Path,
    label: str,
    failures: list[str],
) -> Path | None:
    if not token or Path(token).is_absolute() or "://" in token or "\\" in token:
        failures.append(f"{label} must be a relative POSIX path")
        return None
    candidate = (cwd / token).resolve(strict=False)
    try:
        candidate.relative_to(execution_root.resolve())
    except ValueError:
        failures.append(f"{label} escapes the replay execution root: {token}")
        return None
    if not candidate.is_dir():
        failures.append(f"{label} does not exist: {token}")
        return None
    return candidate


def _validate_replay_command(
    *,
    route: Path,
    manifest: dict[str, Any],
    command: list[str],
    cwd: Path,
    records: dict[str, tuple[dict[str, Any], Path, str]],
    failures: list[str],
) -> None:
    """Validate that replay argv is executable, scoped, and byte-bound.

    The command is intentionally restricted to a Python launcher, optionally
    provisioned by ``uv run --locked``.  Repository evidence may invoke the
    exact route runner; a relocated pack may invoke its route-local integrity
    launcher.  In either case the executed Python file must be present in
    ``artifact_refs`` with the exact observed digest.
    """

    execution_root = _replay_execution_root(route)
    executable = command[0]
    script_index: int | None = None

    if executable == "uv":
        if shutil.which("uv") is None:
            failures.append("formal_proof.replay.command executable uv is unavailable")
        if len(command) < 8 or command[1] != "--directory":
            failures.append(
                "formal_proof.replay.command uv form must declare --directory"
            )
            return
        _resolve_replay_directory(
            cwd,
            command[2],
            execution_root,
            "formal_proof.replay.command uv directory",
            failures,
        )
        if command[3:6] != ["run", "--locked", "python"]:
            failures.append(
                "formal_proof.replay.command uv form must use run --locked python"
            )
        script_index = 6
    elif executable in {"python", "python3"}:
        if shutil.which(executable) is None:
            failures.append(
                f"formal_proof.replay.command executable {executable} is unavailable"
            )
        script_index = 1
    elif "/" in executable:
        interpreter = _resolve_replay_path(
            cwd,
            executable,
            execution_root,
            "formal_proof.replay.command interpreter",
            failures,
        )
        if interpreter is not None and (
            not interpreter.name.startswith("python")
            or not os.access(interpreter, os.X_OK)
        ):
            failures.append(
                "formal_proof.replay.command interpreter must be an executable Python binary"
            )
        script_index = 1
    else:
        failures.append(
            "formal_proof.replay.command must use python, python3, a relative Python binary, or uv"
        )
        return

    if script_index >= len(command):
        failures.append("formal_proof.replay.command is missing its Python script")
        return
    script = _resolve_replay_path(
        cwd,
        command[script_index],
        execution_root,
        "formal_proof.replay.command script",
        failures,
    )
    if script is None:
        return
    if script.suffix != ".py":
        failures.append("formal_proof.replay.command script must be a Python file")

    script_digest = sha256_file(script)
    try:
        route_relative = script.relative_to(route.resolve()).as_posix()
    except ValueError:
        root_relative = script.relative_to(execution_root.resolve()).as_posix()

        def path_matches(reference: str) -> bool:
            return reference == root_relative or reference.endswith("/" + root_relative)

    else:

        def path_matches(reference: str) -> bool:
            return reference == route_relative

    bindings = [
        record
        for record in records.values()
        if record[0].get("role") in {"engine-source", "replay-tool"}
        and record[2] == script_digest
        and isinstance(record[0].get("path"), str)
        and path_matches(record[0]["path"])
    ]
    if len(bindings) != 1:
        failures.append(
            "formal_proof.replay.command script must have exactly one matching engine-source or replay-tool artifact"
        )

    arguments = command[script_index + 1 :]
    parsed: dict[str, str] = {}
    index = 0
    while index < len(arguments):
        option = arguments[index]
        if option not in {"--repo-root", "--route"} or index + 1 >= len(arguments):
            failures.append(
                f"formal_proof.replay.command has unsupported argument: {option}"
            )
            return
        if option in parsed:
            failures.append(f"formal_proof.replay.command repeats argument: {option}")
            return
        parsed[option] = arguments[index + 1]
        index += 2

    route_argument = parsed.get("--route")
    if route_argument == ".":
        if cwd.resolve() != route.resolve():
            failures.append(
                "formal_proof.replay.command --route . requires the route directory as cwd"
            )
    elif route_argument != manifest.get("route_key"):
        failures.append(
            "formal_proof.replay.command --route must bind the exact route_key"
        )
    repository_argument = parsed.get("--repo-root")
    if repository_argument is not None:
        repository_root = (cwd / repository_argument).resolve(strict=False)
        if repository_root != execution_root.resolve() or not repository_root.is_dir():
            failures.append(
                "formal_proof.replay.command --repo-root must resolve to the replay execution root"
            )


def validate_artifact_ref(
    route: Path,
    reference: object,
    label: str,
    failures: list[str],
    *,
    require_identity: bool = True,
) -> tuple[Path, str] | None:
    value = _require_exact_keys(
        failures,
        reference,
        required=ARTIFACT_REF_KEYS if require_identity else {"path", "sha256", "bytes"},
        label=label,
    )
    if value is None:
        return None
    if require_identity:
        artifact_id = value.get("artifact_id")
        if (
            not isinstance(artifact_id, str)
            or ARTIFACT_ID_RE.fullmatch(artifact_id) is None
        ):
            failures.append(f"{label}.artifact_id is invalid")
        role = value.get("role")
        if role not in ARTIFACT_ROLES:
            failures.append(f"{label}.role is invalid")
    path = _resolve_below(route, value.get("path"), f"{label}.path", failures)
    digest = _require_digest(failures, value.get("sha256"), f"{label}.sha256")
    byte_count = value.get("bytes")
    if not _is_int(byte_count, minimum=1):
        failures.append(f"{label}.bytes must be a positive integer")
    if path is None or digest is None or not _is_int(byte_count, minimum=1):
        return None
    if not path.is_file():
        failures.append(f"{label} artifact is missing: {value.get('path')}")
        return None
    observed_bytes = path.stat().st_size
    if observed_bytes != byte_count:
        failures.append(
            f"{label} byte count mismatch: expected {byte_count}, observed {observed_bytes}"
        )
    observed_digest = sha256_file(path)
    if observed_digest != digest:
        failures.append(f"{label} digest mismatch: {value.get('path')}")
    return path, observed_digest


def _artifact_record(
    records: dict[str, tuple[dict[str, Any], Path, str]],
    artifact_id: object,
    *,
    expected_roles: set[str],
    label: str,
    failures: list[str],
) -> tuple[dict[str, Any], Path, str] | None:
    if not isinstance(artifact_id, str) or artifact_id not in records:
        failures.append(f"{label} references unknown artifact_id: {artifact_id}")
        return None
    record = records[artifact_id]
    role = record[0].get("role")
    if role not in expected_roles:
        failures.append(
            f"{label} artifact {artifact_id} has role {role}, expected one of {sorted(expected_roles)}"
        )
        return None
    return record


def _json_pointer_value(document: object, pointer: str) -> object:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must start with /")
    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                raise ValueError(f"invalid array index {token!r}")
            index = int(token)
            if index >= len(current):
                raise ValueError(f"array index out of range: {index}")
            current = current[index]
        elif isinstance(current, dict):
            if token not in current:
                raise ValueError(f"object key does not exist: {token!r}")
            current = current[token]
        else:
            raise ValueError(f"cannot traverse through {type(current).__name__}")
    return current


def _artifact_pointer(
    records: dict[str, tuple[dict[str, Any], Path, str]],
    reference: object,
    *,
    expected_role: str,
    label: str,
    failures: list[str],
) -> tuple[str, str, object, tuple[dict[str, Any], Path, str]] | None:
    if not isinstance(reference, str) or reference.count("#") != 1:
        failures.append(f"{label} must be <artifact_id>#<RFC6901 JSON pointer>")
        return None
    artifact_id, pointer = reference.split("#", 1)
    record = _artifact_record(
        records,
        artifact_id,
        expected_roles={expected_role},
        label=label,
        failures=failures,
    )
    if record is None:
        return None
    try:
        document = json.loads(record[1].read_text(encoding="utf-8"))
        value = _json_pointer_value(document, pointer)
    except Exception as exc:
        failures.append(f"{label} cannot resolve JSON pointer {pointer!r}: {exc}")
        return None
    return artifact_id, pointer, value, record


def _validate_formal_input_document(
    route: Path,
    record: tuple[dict[str, Any], Path, str],
    records: dict[str, tuple[dict[str, Any], Path, str]],
    manifest: dict[str, Any],
    proof: dict[str, Any],
    label: str,
    failures: list[str],
) -> dict[str, Any] | None:
    try:
        document = load(record[1])
    except Exception as exc:
        failures.append(f"{label} is invalid JSON: {exc}")
        return None
    missing = FORMAL_INPUT_REQUIRED_KEYS - set(document)
    if missing:
        failures.append(f"{label} missing keys: {', '.join(sorted(missing))}")
        return document
    if document.get("kind") != "elmos.formal-equivalence-input":
        failures.append(f"{label}.kind is invalid")
    route_scope = document.get("route")
    if not isinstance(route_scope, dict):
        failures.append(f"{label}.route must be an object")
    else:
        expected_route = {
            "source_language": manifest.get("source", {}).get("language"),
            "target_language": manifest.get("target", {}).get("language"),
            "profile": manifest.get("profiles", {}).get("semantic_profile"),
        }
        if route_scope != expected_route:
            failures.append(f"{label}.route does not match route.json")
    claim_scope = document.get("claim_scope")
    if not isinstance(claim_scope, dict):
        failures.append(f"{label}.claim_scope must be an object")
    else:
        if (
            claim_scope.get("relation")
            != "canonical-normalized-source-ir-to-target-relift-ir"
            or claim_scope.get("original_source_bytes_theorem") is not False
            or claim_scope.get("source_compiler_runtime_soundness") != "NOT_RUN"
            or claim_scope.get("target_compiler_runtime_soundness") != "NOT_RUN"
        ):
            failures.append(f"{label}.claim_scope overstates the proved relation")

    by_relative = {
        item[0].get("path"): item
        for item in records.values()
        if isinstance(item[0].get("path"), str)
    }
    formal_parent = record[1].parent

    def bound_sibling(
        reference: object, expected_role: str, child_label: str
    ) -> tuple[dict[str, Any], Path, str] | None:
        if not isinstance(reference, dict):
            failures.append(f"{label}.{child_label} reference must be an object")
            return None
        relative = reference.get("path")
        digest = reference.get("sha256")
        if not isinstance(relative, str) or not relative:
            failures.append(f"{label}.{child_label}.path is invalid")
            return None
        candidate = (formal_parent / relative).resolve(strict=False)
        try:
            route_relative = candidate.relative_to(route.resolve()).as_posix()
        except ValueError:
            failures.append(f"{label}.{child_label} escapes the route")
            return None
        child_record = by_relative.get(route_relative)
        if child_record is None:
            failures.append(
                f"{label}.{child_label} is not bound by artifact_refs: {route_relative}"
            )
            return None
        if child_record[0].get("role") != expected_role:
            failures.append(
                f"{label}.{child_label} has role {child_record[0].get('role')}, expected {expected_role}"
            )
        if digest != child_record[2]:
            failures.append(f"{label}.{child_label} digest mismatch")
        return child_record

    for field, role, expected_binding_role in (
        (
            "source_artifact",
            "corpus-artifact",
            "original-source-analyzer-input",
        ),
        ("target_artifact", "target-artifact", "emitted-target-analyzer-input"),
    ):
        binding = document.get(field)
        if not isinstance(binding, dict):
            failures.append(f"{label}.{field} must be an object")
            continue
        if binding.get("role") != expected_binding_role:
            failures.append(f"{label}.{field}.role is invalid")
        encoded = binding.get("content_base64")
        expected_digest = binding.get("sha256")
        expected_bytes = binding.get("byte_count")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, TypeError, ValueError):
            failures.append(f"{label}.{field}.content_base64 is invalid")
            decoded = b""
        if (
            not _is_int(expected_bytes, minimum=1)
            or len(decoded) != expected_bytes
            or sha256_bytes(decoded) != expected_digest
        ):
            failures.append(f"{label}.{field} embedded bytes do not match digest")
        child_record = bound_sibling(
            binding.get("content_reference"), role, f"{field}.content_reference"
        )
        if child_record is not None and child_record[1].read_bytes() != decoded:
            failures.append(f"{label}.{field} embedded/reference bytes differ")

    normalized_documents: dict[str, dict[str, Any]] = {}
    for field, role, expected_binding_role in (
        (
            "source_normalized_ir",
            "source-ir",
            "canonical-source-normalized-ir",
        ),
        (
            "target_relift_normalized_ir",
            "target-ir",
            "emitted-target-relift-normalized-ir",
        ),
    ):
        binding = document.get(field)
        if not isinstance(binding, dict):
            failures.append(f"{label}.{field} must be an object")
            continue
        if binding.get("role") != expected_binding_role:
            failures.append(f"{label}.{field}.role is invalid")
        child_record = bound_sibling(binding.get("artifact"), role, f"{field}.artifact")
        semantic_ir = binding.get("semantic_ir")
        formal_function = binding.get("formal_function")
        if not isinstance(semantic_ir, dict) or not isinstance(formal_function, dict):
            failures.append(f"{label}.{field} semantic IR/function is invalid")
            continue
        normalized_documents[field] = semantic_ir
        if child_record is not None:
            try:
                persisted_ir = load(child_record[1])
            except Exception as exc:
                failures.append(f"{label}.{field} persisted IR is invalid: {exc}")
            else:
                if persisted_ir != semantic_ir:
                    failures.append(f"{label}.{field} embedded/persisted IR differ")
        functions = semantic_ir.get("functions")
        if not isinstance(functions, list) or len(functions) != 1:
            failures.append(f"{label}.{field} must contain exactly one function")
        elif functions[0] != formal_function:
            failures.append(f"{label}.{field} formal_function drift")
        if binding.get("semantic_ir_sha256") != canonical_json_sha256(semantic_ir):
            failures.append(f"{label}.{field} semantic_ir_sha256 mismatch")
        if binding.get("formal_function_sha256") != canonical_json_sha256(
            formal_function
        ):
            failures.append(f"{label}.{field} formal_function_sha256 mismatch")
    if normalized_documents.get("source_normalized_ir", {}).get(
        "functions"
    ) != normalized_documents.get("target_relift_normalized_ir", {}).get("functions"):
        failures.append(f"{label} source/target normalized functions differ")

    analyzer_identity = document.get("analyzer_identity")
    if not isinstance(analyzer_identity, dict):
        failures.append(f"{label}.analyzer_identity must be an object")
    else:
        for identity_field, ir_field, expected_language, expected_mode in (
            (
                "source",
                "source_normalized_ir",
                manifest.get("source", {}).get("language"),
                None,
            ),
            (
                "target_relift",
                "target_relift_normalized_ir",
                manifest.get("target", {}).get("language"),
                "emitted-target",
            ),
        ):
            identity = analyzer_identity.get(identity_field)
            semantic_ir = normalized_documents.get(ir_field, {})
            if (
                not isinstance(identity, dict)
                or identity.get("name") != semantic_ir.get("analyzer")
                or identity.get("version") != semantic_ir.get("analyzer_version")
                or identity.get("language") != expected_language
                or (expected_mode is not None and identity.get("mode") != expected_mode)
            ):
                failures.append(
                    f"{label}.analyzer_identity.{identity_field} differs from bound IR"
                )
    emitter_identity = document.get("emitter_identity")
    if (
        not isinstance(emitter_identity, dict)
        or emitter_identity.get("target_language")
        != manifest.get("target", {}).get("language")
        or not isinstance(emitter_identity.get("normalization_rules"), list)
        or not isinstance(emitter_identity.get("helper_digests"), list)
    ):
        failures.append(f"{label}.emitter_identity is invalid")

    implementation = document.get("implementation_identity")
    if not isinstance(implementation, dict):
        failures.append(f"{label}.implementation_identity must be an object")
    else:
        expected_files = {
            "engine": "src/elmos_polyglot_route/engine.py",
            "equivalence_encoder": "src/elmos_polyglot_route/equivalence.py",
            "emitter": "src/elmos_polyglot_route/emitter.py",
        }
        engine_records = [
            item for item in records.values() if item[0].get("role") == "engine-source"
        ]
        for identity, expected_suffix in expected_files.items():
            value = implementation.get(identity)
            if not isinstance(value, dict) or value.get("path") != expected_suffix:
                failures.append(
                    f"{label}.implementation_identity.{identity} is invalid"
                )
                continue
            matches = [
                item
                for item in engine_records
                if str(item[0].get("path", "")).endswith(
                    f"engines/polyglot-route-engine/{expected_suffix}"
                )
            ]
            if len(matches) != 1:
                failures.append(
                    f"{label}.implementation_identity.{identity} has no unique captured source"
                )
            elif (
                value.get("sha256") != matches[0][2]
                or value.get("byte_count") != matches[0][1].stat().st_size
            ):
                failures.append(
                    f"{label}.implementation_identity.{identity} digest/bytes drift"
                )

    assumptions = document.get("environment_assumptions")
    if (
        not isinstance(assumptions, list)
        or not assumptions
        or any(not isinstance(item, str) or not item for item in assumptions)
    ):
        failures.append(f"{label}.environment_assumptions must be non-empty")
    unsupported = document.get("unsupported_semantics")
    if (
        not isinstance(unsupported, list)
        or not unsupported
        or any(not isinstance(item, str) or not item for item in unsupported)
    ):
        failures.append(f"{label}.unsupported_semantics must be non-empty")
    solver = document.get("solver")
    if not isinstance(solver, dict):
        failures.append(f"{label}.solver must be an object")
    else:
        if solver.get("name") != proof.get("solver") or solver.get(
            "version"
        ) != proof.get("solver_version"):
            failures.append(f"{label}.solver identity differs from formal_proof")
        options = proof.get("solver_options")
        if isinstance(options, dict):
            for key in ("timeout_ms", "random_seed"):
                if solver.get(key) != options.get(key):
                    failures.append(f"{label}.solver {key} differs from formal_proof")
    return document


def _validate_optional_json_schema(
    data: dict[str, Any], schema_name: str, failures: list[str], label: str
) -> None:
    """Use jsonschema when the invoking environment provides it.

    Direct semantic validation below remains authoritative because the route CI
    intentionally runs with the standard-library Python interpreter as well as
    through the Batch 29 Make target that installs jsonschema.
    """

    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        return
    schema = Path(__file__).resolve().parents[2] / "schemas" / "batch29" / schema_name
    try:
        jsonschema.Draft202012Validator(load(schema)).validate(data)
    except Exception as exc:
        failures.append(f"{label} schema validation failed: {exc}")


def validate_formal_equivalence(
    route: Path,
    manifest: dict[str, Any],
    certification: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate strict evidence format v2 without upgrading its proof claim.

    The return value is consumed by the route gate. Structural validation here
    proves only that referenced bytes and reported counts are internally
    consistent; the gate separately decides whether those states can pass.
    """

    failures: list[str] = []
    evidence_format = certification.get("evidence_format")
    if evidence_format is not None and not _is_int(evidence_format, minimum=1):
        failures.append("certification evidence_format must be a positive integer")
    if not strict_evidence_requested(certification):
        return None, failures

    reference = certification.get("formal_equivalence")
    resolved = validate_artifact_ref(
        route,
        reference,
        "formal_equivalence",
        failures,
        require_identity=False,
    )
    if resolved is None:
        return None, failures
    evidence_path, _ = resolved
    try:
        evidence = load(evidence_path)
    except Exception as exc:
        failures.append(str(exc))
        return None, failures

    _validate_optional_json_schema(
        evidence,
        "formal-equivalence-evidence.schema.json",
        failures,
        "formal equivalence evidence",
    )
    top = _require_exact_keys(
        failures,
        evidence,
        required=FORMAL_REQUIRED_KEYS,
        label="formal equivalence evidence",
    )
    if top is None:
        return evidence, failures
    if top.get("schema_version") != 2:
        failures.append("formal equivalence schema_version must be 2")
    if top.get("route_key") != manifest.get("route_key"):
        failures.append("formal equivalence route_key mismatch")
    profile = manifest.get("profiles", {}).get("semantic_profile")
    if top.get("semantic_profile") != profile:
        failures.append("formal equivalence semantic_profile mismatch")

    route_manifest_digest = _require_digest(
        failures, top.get("route_manifest_sha256"), "route_manifest_sha256"
    )
    if route_manifest_digest is not None and route_manifest_digest != sha256_file(
        route / "route.json"
    ):
        failures.append("route_manifest_sha256 does not bind route.json")
    profile_digest = _require_digest(
        failures, top.get("semantic_profile_sha256"), "semantic_profile_sha256"
    )
    profile_path = route / "lowering" / "profile.json"
    if not profile_path.is_file():
        failures.append("semantic profile artifact is missing")
    elif profile_digest is not None and profile_digest != sha256_file(profile_path):
        failures.append("semantic_profile_sha256 does not bind lowering/profile.json")
    artifact_digest = _require_digest(
        failures, top.get("artifact_sha256"), "artifact_sha256"
    )
    environment_digest = _require_digest(
        failures, top.get("environment_sha256"), "environment_sha256"
    )

    artifact_refs = top.get("artifact_refs")
    ref_digests: set[str] = set()
    ref_paths: set[str] = set()
    ref_records: dict[str, tuple[dict[str, Any], Path, str]] = {}
    if not isinstance(artifact_refs, list) or not artifact_refs:
        failures.append("artifact_refs must be a non-empty array")
    else:
        for index, item in enumerate(artifact_refs):
            verified = validate_artifact_ref(
                route, item, f"artifact_refs[{index}]", failures
            )
            if not isinstance(item, dict):
                continue
            relative = item.get("path")
            if isinstance(relative, str):
                if relative in ref_paths:
                    failures.append(
                        f"artifact_refs contains duplicate path: {relative}"
                    )
                ref_paths.add(relative)
            if verified is not None:
                ref_digests.add(verified[1])
                artifact_id = item.get("artifact_id")
                if isinstance(artifact_id, str):
                    if artifact_id in ref_records:
                        failures.append(
                            f"artifact_refs contains duplicate artifact_id: {artifact_id}"
                        )
                    else:
                        ref_records[artifact_id] = (item, verified[0], verified[1])

    top_artifact_records: dict[str, tuple[dict[str, Any], Path, str]] = {}
    for label, artifact_id, digest, roles in (
        (
            "artifact",
            top.get("artifact_id"),
            artifact_digest,
            {"target-artifact"},
        ),
        (
            "environment",
            top.get("environment_artifact_id"),
            environment_digest,
            {"environment"},
        ),
    ):
        record = _artifact_record(
            ref_records,
            artifact_id,
            expected_roles=roles,
            label=f"{label}_artifact_id",
            failures=failures,
        )
        if record is not None and digest is not None and record[2] != digest:
            failures.append(
                f"{label}_sha256 does not match {label}_artifact_id {artifact_id}"
            )
        if record is not None:
            top_artifact_records[label] = record

    environment_document: dict[str, Any] | None = None
    environment_record = top_artifact_records.get("environment")
    if environment_record is not None:
        try:
            environment_document = load(environment_record[1])
        except Exception as exc:
            failures.append(f"environment artifact is invalid JSON: {exc}")
        else:
            if environment_document.get("route_key") != manifest.get("route_key"):
                failures.append("environment artifact route_key mismatch")
            if environment_document.get("independent_verification") != "NOT_RUN":
                failures.append(
                    "environment independent_verification must remain NOT_RUN"
                )
            if environment_document.get("external_certification") != "NOT_RUN":
                failures.append(
                    "environment external_certification must remain NOT_RUN"
                )
            source_manifest = environment_document.get("engine_source_manifest")
            if not isinstance(source_manifest, dict):
                failures.append("environment engine_source_manifest is missing")
            else:
                manifest_relative = source_manifest.get("path")
                manifest_record = next(
                    (
                        item
                        for item in ref_records.values()
                        if item[0].get("path") == manifest_relative
                    ),
                    None,
                )
                if (
                    manifest_record is None
                    or manifest_record[0].get("role") != "engine-source-manifest"
                ):
                    failures.append(
                        "environment engine_source_manifest is not role-bound"
                    )
                elif (
                    source_manifest.get("sha256") != manifest_record[2]
                    or source_manifest.get("bytes") != manifest_record[1].stat().st_size
                ):
                    failures.append(
                        "environment engine_source_manifest digest/bytes mismatch"
                    )
                else:
                    try:
                        source_manifest_document = load(manifest_record[1])
                    except Exception as exc:
                        failures.append(
                            f"engine source manifest is invalid JSON: {exc}"
                        )
                    else:
                        files = source_manifest_document.get("files")
                        if not isinstance(files, list) or not files:
                            failures.append("engine source manifest files are empty")
                        else:
                            declared_sources: set[str] = set()
                            live_repository_root = _replay_execution_root(route)
                            validate_live_sources = (
                                (live_repository_root / "engines").is_dir()
                                and (
                                    live_repository_root / "scripts" / "batch29"
                                ).is_dir()
                                and (
                                    live_repository_root / "schemas" / "batch29"
                                ).is_dir()
                            )
                            for index, item in enumerate(files):
                                if not isinstance(item, dict):
                                    failures.append(
                                        f"engine source manifest files[{index}] is invalid"
                                    )
                                    continue
                                repository_path = item.get("repository_path")
                                if (
                                    not isinstance(repository_path, str)
                                    or not repository_path
                                    or Path(repository_path).is_absolute()
                                    or "\\" in repository_path
                                    or any(
                                        part in {"", ".", ".."}
                                        for part in Path(repository_path).parts
                                    )
                                ):
                                    failures.append(
                                        f"engine source manifest files[{index}].repository_path is invalid"
                                    )
                                    repository_path = None
                                captured_path = item.get("captured_path")
                                declared_sources.add(str(captured_path))
                                captured_record = next(
                                    (
                                        record
                                        for record in ref_records.values()
                                        if record[0].get("path") == captured_path
                                    ),
                                    None,
                                )
                                if (
                                    captured_record is None
                                    or captured_record[0].get("role") != "engine-source"
                                ):
                                    failures.append(
                                        f"engine source manifest files[{index}] is not role-bound"
                                    )
                                elif (
                                    item.get("sha256") != captured_record[2]
                                    or item.get("bytes")
                                    != captured_record[1].stat().st_size
                                ):
                                    failures.append(
                                        f"engine source manifest files[{index}] digest/bytes mismatch"
                                    )
                                if (
                                    validate_live_sources
                                    and repository_path is not None
                                ):
                                    live_path = (
                                        live_repository_root / repository_path
                                    ).resolve(strict=False)
                                    try:
                                        live_path.relative_to(live_repository_root)
                                    except ValueError:
                                        failures.append(
                                            f"engine source manifest files[{index}].repository_path escapes the repository"
                                        )
                                    else:
                                        if not live_path.is_file():
                                            failures.append(
                                                f"engine source manifest live file is missing: {repository_path}"
                                            )
                                        elif (
                                            item.get("sha256") != sha256_file(live_path)
                                            or item.get("bytes")
                                            != live_path.stat().st_size
                                        ):
                                            failures.append(
                                                f"engine source manifest live file drifted: {repository_path}"
                                            )
                            actual_sources = {
                                str(record[0].get("path"))
                                for record in ref_records.values()
                                if record[0].get("role") == "engine-source"
                            }
                            if declared_sources != actual_sources:
                                failures.append(
                                    "engine source manifest does not exactly cover engine-source artifacts"
                                )
                            if source_manifest_document.get("file_count") != len(files):
                                failures.append(
                                    "engine source manifest file_count mismatch"
                                )
                            lock_reference = environment_document.get(
                                "route_engine_lock"
                            )
                            if not isinstance(lock_reference, dict):
                                failures.append(
                                    "environment route_engine_lock is missing"
                                )
                            else:
                                lock_entries = [
                                    item
                                    for item in files
                                    if isinstance(item, dict)
                                    and item.get("repository_path")
                                    == lock_reference.get("path")
                                ]
                                if len(lock_entries) != 1 or lock_entries[0].get(
                                    "sha256"
                                ) != lock_reference.get("sha256"):
                                    failures.append(
                                        "environment route_engine_lock is not bound by engine source manifest"
                                    )

    semantic_ir = _require_exact_keys(
        failures,
        top.get("semantic_ir"),
        required=SEMANTIC_IR_KEYS,
        label="semantic_ir",
    )
    if semantic_ir is not None:
        if semantic_ir.get("status") not in LAYER_STATUSES:
            failures.append("semantic_ir.status is invalid")
        for id_field, digest_field, role in (
            ("source_ir_artifact_id", "source_ir_sha256", "source-ir"),
            ("target_ir_artifact_id", "target_relift_ir_sha256", "target-ir"),
        ):
            digest = _require_digest(
                failures, semantic_ir.get(digest_field), f"semantic_ir.{digest_field}"
            )
            record = _artifact_record(
                ref_records,
                semantic_ir.get(id_field),
                expected_roles={role},
                label=f"semantic_ir.{id_field}",
                failures=failures,
            )
            if record is not None and digest is not None and record[2] != digest:
                failures.append(f"semantic_ir.{digest_field} does not match {id_field}")
        if not _is_int(semantic_ir.get("unknown_or_dropped_nodes"), minimum=0):
            failures.append(
                "semantic_ir.unknown_or_dropped_nodes must be a non-negative integer"
            )
        _require_nonempty_strings(
            failures, semantic_ir.get("differences"), "semantic_ir.differences"
        )

    semantic_chunks = _require_exact_keys(
        failures,
        top.get("semantic_chunks"),
        required=SEMANTIC_CHUNK_KEYS,
        label="semantic_chunks",
    )
    if semantic_chunks is not None:
        if semantic_chunks.get("status") not in LAYER_STATUSES:
            failures.append("semantic_chunks.status is invalid")
        chunk_evidence_ids = semantic_chunks.get("evidence_artifact_ids")
        if not isinstance(chunk_evidence_ids, list) or not chunk_evidence_ids:
            failures.append(
                "semantic_chunks.evidence_artifact_ids must be a non-empty array"
            )
        else:
            for index, artifact_id in enumerate(chunk_evidence_ids):
                _artifact_record(
                    ref_records,
                    artifact_id,
                    expected_roles={"chunk-map"},
                    label=f"semantic_chunks.evidence_artifact_ids[{index}]",
                    failures=failures,
                )
        for field, minimum in (
            ("total", 1),
            ("matched", 0),
            ("unmatched", 0),
            ("ambiguous", 0),
        ):
            if not _is_int(semantic_chunks.get(field), minimum=minimum):
                failures.append(
                    f"semantic_chunks.{field} must be an integer >= {minimum}"
                )
        coverage = semantic_chunks.get("coverage")
        if not _is_number(coverage) or not 0 <= float(coverage) <= 1:
            failures.append("semantic_chunks.coverage must be between 0 and 1")
        chunks = semantic_chunks.get("chunks")
        ids: set[str] = set()
        observed = {"MATCHED": 0, "UNMATCHED": 0, "AMBIGUOUS": 0, "FAILED": 0}
        if not isinstance(chunks, list) or not chunks:
            failures.append("semantic_chunks.chunks must be a non-empty array")
        else:
            for index, item in enumerate(chunks):
                chunk = _require_exact_keys(
                    failures,
                    item,
                    required=CHUNK_KEYS,
                    label=f"semantic_chunks.chunks[{index}]",
                )
                if chunk is None:
                    continue
                chunk_id = chunk.get("chunk_id")
                if not isinstance(chunk_id, str) or not chunk_id:
                    failures.append(
                        f"semantic_chunks.chunks[{index}].chunk_id is invalid"
                    )
                elif chunk_id in ids:
                    failures.append(f"semantic chunk id is duplicated: {chunk_id}")
                else:
                    ids.add(chunk_id)
                semantic_hash = _require_digest(
                    failures,
                    chunk.get("semantic_hash"),
                    f"semantic_chunks.chunks[{index}].semantic_hash",
                )
                source_pointer = _artifact_pointer(
                    ref_records,
                    chunk.get("source_ref"),
                    expected_role="source-ir",
                    label=f"semantic_chunks.chunks[{index}].source_ref",
                    failures=failures,
                )
                target_pointer = _artifact_pointer(
                    ref_records,
                    chunk.get("target_ref"),
                    expected_role="target-ir",
                    label=f"semantic_chunks.chunks[{index}].target_ref",
                    failures=failures,
                )
                if source_pointer is not None and target_pointer is not None:
                    if source_pointer[1] != target_pointer[1]:
                        failures.append(
                            f"semantic_chunks.chunks[{index}] source/target JSON pointers differ"
                        )
                    for pointer_label, pointer in (
                        ("source", source_pointer),
                        ("target", target_pointer),
                    ):
                        observed_hash = canonical_json_sha256(pointer[2])
                        if semantic_hash is not None and observed_hash != semantic_hash:
                            failures.append(
                                f"semantic_chunks.chunks[{index}] {pointer_label} subtree hash mismatch"
                            )
                status = chunk.get("status")
                if status not in CHUNK_STATUSES:
                    failures.append(
                        f"semantic_chunks.chunks[{index}].status is invalid"
                    )
                else:
                    observed[status] += 1
            total = semantic_chunks.get("total")
            if _is_int(total, minimum=1) and total != len(chunks):
                failures.append("semantic_chunks.total does not equal chunks length")
            if (
                _is_int(semantic_chunks.get("matched"))
                and semantic_chunks.get("matched") != observed["MATCHED"]
            ):
                failures.append("semantic_chunks.matched does not match chunk statuses")
            if (
                _is_int(semantic_chunks.get("unmatched"))
                and semantic_chunks.get("unmatched") != observed["UNMATCHED"]
            ):
                failures.append(
                    "semantic_chunks.unmatched does not match chunk statuses"
                )
            if (
                _is_int(semantic_chunks.get("ambiguous"))
                and semantic_chunks.get("ambiguous") != observed["AMBIGUOUS"]
            ):
                failures.append(
                    "semantic_chunks.ambiguous does not match chunk statuses"
                )
            if _is_int(total, minimum=1) and _is_number(coverage):
                expected_coverage = observed["MATCHED"] / total
                if abs(float(coverage) - expected_coverage) > 1e-12:
                    failures.append(
                        "semantic_chunks.coverage does not equal matched / total"
                    )
        expected_chunk_rows: set[tuple[str, str, str, str, str]] = set()
        if isinstance(chunk_evidence_ids, list):
            for artifact_id in chunk_evidence_ids:
                chunk_record = ref_records.get(artifact_id)
                if chunk_record is None:
                    continue
                try:
                    chunk_document = load(chunk_record[1])
                except Exception as exc:
                    failures.append(
                        f"semantic chunk artifact {artifact_id} is invalid JSON: {exc}"
                    )
                    continue
                if chunk_document.get("status") != "PASSED":
                    failures.append(
                        f"semantic chunk artifact {artifact_id} did not pass"
                    )
                if chunk_document.get("path_scheme") != "rfc6901-json-pointer-v1":
                    failures.append(
                        f"semantic chunk artifact {artifact_id} does not use RFC6901 pointers"
                    )
                mappings = chunk_document.get("mappings")
                if not isinstance(mappings, list) or not mappings:
                    failures.append(
                        f"semantic chunk artifact {artifact_id} has no mappings"
                    )
                    continue
                parent = chunk_record[1].parent
                source_candidates = [
                    (candidate_id, record)
                    for candidate_id, record in ref_records.items()
                    if record[0].get("role") == "source-ir"
                    and record[1].parent == parent
                ]
                target_candidates = [
                    (candidate_id, record)
                    for candidate_id, record in ref_records.items()
                    if record[0].get("role") == "target-ir"
                    and record[1].parent == parent
                ]
                if len(source_candidates) != 1 or len(target_candidates) != 1:
                    failures.append(
                        f"semantic chunk artifact {artifact_id} must have one sibling source IR and target IR"
                    )
                    continue
                source_artifact_id = source_candidates[0][0]
                target_artifact_id = target_candidates[0][0]
                for mapping_index, mapping in enumerate(mappings):
                    if (
                        not isinstance(mapping, dict)
                        or mapping.get("status") != "EXACT"
                    ):
                        failures.append(
                            f"semantic chunk artifact {artifact_id} mapping {mapping_index} is not EXACT"
                        )
                        continue
                    pointer = mapping.get("semantic_path")
                    semantic_hash = mapping.get("semantic_hash")
                    source_chunk_id = mapping.get("source_chunk_id")
                    target_chunk_id = mapping.get("target_chunk_id")
                    source_artifact_pointer = mapping.get("source_artifact_pointer")
                    target_artifact_pointer = mapping.get("target_artifact_pointer")
                    if not all(
                        isinstance(item, str) and item
                        for item in (
                            pointer,
                            semantic_hash,
                            source_chunk_id,
                            target_chunk_id,
                            source_artifact_pointer,
                            target_artifact_pointer,
                        )
                    ):
                        failures.append(
                            f"semantic chunk artifact {artifact_id} mapping {mapping_index} is incomplete"
                        )
                        continue
                    for pointer_label, artifact_pointer, expected_roles in (
                        (
                            "source_artifact_pointer",
                            source_artifact_pointer,
                            {"corpus-artifact"},
                        ),
                        (
                            "target_artifact_pointer",
                            target_artifact_pointer,
                            {"target-artifact"},
                        ),
                    ):
                        if artifact_pointer.count("#") != 1:
                            failures.append(
                                f"semantic chunk artifact {artifact_id} mapping {mapping_index} {pointer_label} is invalid"
                            )
                            continue
                        artifact_digest, artifact_json_pointer = artifact_pointer.split(
                            "#", 1
                        )
                        if artifact_json_pointer != pointer:
                            failures.append(
                                f"semantic chunk artifact {artifact_id} mapping {mapping_index} {pointer_label} pointer drift"
                            )
                        matches = [
                            record
                            for record in ref_records.values()
                            if record[2] == artifact_digest
                            and record[0].get("role") in expected_roles
                            and (
                                pointer_label != "target_artifact_pointer"
                                or record[1].parent == parent
                            )
                        ]
                        if not matches:
                            failures.append(
                                f"semantic chunk artifact {artifact_id} mapping {mapping_index} {pointer_label} digest is not role-bound"
                            )
                    expected_source_chunk_id = sha256_bytes(
                        (
                            f"{source_artifact_pointer.split('#', 1)[0]}\0{pointer}\0{semantic_hash}"
                        ).encode("utf-8")
                    )
                    expected_target_chunk_id = sha256_bytes(
                        (
                            f"{target_artifact_pointer.split('#', 1)[0]}\0{pointer}\0{semantic_hash}"
                        ).encode("utf-8")
                    )
                    if source_chunk_id != expected_source_chunk_id:
                        failures.append(
                            f"semantic chunk artifact {artifact_id} mapping {mapping_index} source_chunk_id drift"
                        )
                    if target_chunk_id != expected_target_chunk_id:
                        failures.append(
                            f"semantic chunk artifact {artifact_id} mapping {mapping_index} target_chunk_id drift"
                        )
                    expected_chunk_rows.add(
                        (
                            f"{parent.name}:{source_chunk_id}",
                            f"{source_artifact_id}#{pointer}",
                            f"{target_artifact_id}#{pointer}",
                            semantic_hash,
                            "MATCHED",
                        )
                    )
                required = chunk_document.get("required_source_chunk_count")
                mapped = chunk_document.get("mapped_source_chunk_count")
                if required != len(mappings) or mapped != len(mappings):
                    failures.append(
                        f"semantic chunk artifact {artifact_id} count fields do not match mappings"
                    )
                if chunk_document.get("coverage") != 1.0:
                    failures.append(
                        f"semantic chunk artifact {artifact_id} coverage is not 1.0"
                    )
        if isinstance(chunks, list):
            actual_chunk_rows = {
                (
                    item.get("chunk_id"),
                    item.get("source_ref"),
                    item.get("target_ref"),
                    item.get("semantic_hash"),
                    item.get("status"),
                )
                for item in chunks
                if isinstance(item, dict)
            }
            if actual_chunk_rows != expected_chunk_rows:
                failures.append(
                    "semantic_chunks.chunks do not exactly match bound chunk-map artifacts"
                )

    behavior = _require_exact_keys(
        failures,
        top.get("behavior_equivalence"),
        required=BEHAVIOR_KEYS,
        label="behavior_equivalence",
    )
    if behavior is not None:
        if behavior.get("status") not in LAYER_STATUSES:
            failures.append("behavior_equivalence.status is invalid")
        behavior_artifact_ids = behavior.get("evidence_artifact_ids")
        observed_behavior_documents: list[dict[str, Any]] = []
        if not isinstance(behavior_artifact_ids, list) or not behavior_artifact_ids:
            failures.append(
                "behavior_equivalence.evidence_artifact_ids must be a non-empty array"
            )
        else:
            for index, artifact_id in enumerate(behavior_artifact_ids):
                record = _artifact_record(
                    ref_records,
                    artifact_id,
                    expected_roles={"behavior-result"},
                    label=f"behavior_equivalence.evidence_artifact_ids[{index}]",
                    failures=failures,
                )
                if record is None:
                    continue
                try:
                    document = load(record[1])
                except Exception as exc:
                    failures.append(
                        f"behavior artifact {artifact_id} is not valid JSON: {exc}"
                    )
                else:
                    observed_behavior_documents.append(document)
        for field in (
            "source_runtime_artifact_ids",
            "target_runtime_artifact_ids",
        ):
            runtime_ids = behavior.get(field)
            if not isinstance(runtime_ids, list) or not runtime_ids:
                failures.append(f"behavior_equivalence.{field} must be non-empty")
                continue
            for index, artifact_id in enumerate(runtime_ids):
                _artifact_record(
                    ref_records,
                    artifact_id,
                    expected_roles={"behavior-result"},
                    label=f"behavior_equivalence.{field}[{index}]",
                    failures=failures,
                )
                if (
                    isinstance(behavior_artifact_ids, list)
                    and artifact_id not in behavior_artifact_ids
                ):
                    failures.append(
                        f"behavior_equivalence.{field}[{index}] is absent from evidence_artifact_ids"
                    )
        total_cases = behavior.get("total_cases")
        passed_cases = behavior.get("passed_cases")
        if not _is_int(total_cases, minimum=1):
            failures.append(
                "behavior_equivalence.total_cases must be a positive integer"
            )
        if not _is_int(passed_cases, minimum=0):
            failures.append(
                "behavior_equivalence.passed_cases must be a non-negative integer"
            )
        elif _is_int(total_cases, minimum=1) and passed_cases > total_cases:
            failures.append("behavior_equivalence.passed_cases exceeds total_cases")
        for field in (
            "canonical_oracle_passed",
            "source_runtime_passed",
            "target_runtime_passed",
        ):
            if not isinstance(behavior.get(field), bool):
                failures.append(f"behavior_equivalence.{field} must be boolean")
        counterexamples = behavior.get("counterexamples")
        if not isinstance(counterexamples, list):
            failures.append("behavior_equivalence.counterexamples must be an array")
        else:
            case_ids: set[str] = set()
            for index, item in enumerate(counterexamples):
                counterexample = _require_exact_keys(
                    failures,
                    item,
                    required=COUNTEREXAMPLE_REQUIRED_KEYS,
                    allowed=COUNTEREXAMPLE_ALLOWED_KEYS,
                    label=f"behavior_equivalence.counterexamples[{index}]",
                )
                if counterexample is None:
                    continue
                case_id = counterexample.get("case_id")
                reason = counterexample.get("reason")
                if not isinstance(case_id, str) or not case_id:
                    failures.append(
                        f"behavior_equivalence.counterexamples[{index}].case_id is invalid"
                    )
                elif case_id in case_ids:
                    failures.append(
                        f"behavior counterexample id is duplicated: {case_id}"
                    )
                else:
                    case_ids.add(case_id)
                if not isinstance(reason, str) or not reason:
                    failures.append(
                        f"behavior_equivalence.counterexamples[{index}].reason is invalid"
                    )
                evidence_ref = counterexample.get("evidence_ref")
                if evidence_ref is not None and evidence_ref not in ref_paths:
                    failures.append(
                        f"behavior_equivalence.counterexamples[{index}].evidence_ref is not in artifact_refs"
                    )
            if _is_int(total_cases, minimum=1) and _is_int(passed_cases):
                if total_cases - passed_cases != len(counterexamples):
                    failures.append(
                        "behavior counterexample count must equal total_cases - passed_cases"
                    )
        if observed_behavior_documents:
            observed_counts: list[tuple[int, int]] = []
            for index, item in enumerate(observed_behavior_documents):
                case_count = item.get("case_count")
                pass_count = item.get("pass_count")
                if not _is_int(case_count, minimum=1) or not _is_int(
                    pass_count, minimum=0
                ):
                    failures.append(
                        f"behavior artifact {index} has invalid case/pass counts"
                    )
                    continue
                observed_counts.append((case_count, pass_count))
            observed_total = sum(item[0] for item in observed_counts)
            observed_passed = sum(item[1] for item in observed_counts)
            if observed_total != total_cases:
                failures.append(
                    "behavior_equivalence.total_cases does not match behavior artifacts"
                )
            if observed_passed != passed_cases:
                failures.append(
                    "behavior_equivalence.passed_cases does not match behavior artifacts"
                )
            observed_oracle = all(
                item.get("oracle_conflict_count") == 0
                for item in observed_behavior_documents
            )
            observed_source = all(
                item.get("source_runtime_passed") is True
                for item in observed_behavior_documents
            )
            observed_target = all(
                item.get("target_runtime_passed") is True
                for item in observed_behavior_documents
            )
            for field, observed in (
                ("canonical_oracle_passed", observed_oracle),
                ("source_runtime_passed", observed_source),
                ("target_runtime_passed", observed_target),
            ):
                if behavior.get(field) is not observed:
                    failures.append(
                        f"behavior_equivalence.{field} does not match behavior artifacts"
                    )

    formal_proof = _require_exact_keys(
        failures,
        top.get("formal_proof"),
        required=FORMAL_PROOF_KEYS,
        label="formal_proof",
    )
    if formal_proof is not None:
        status = formal_proof.get("status")
        if status not in PROOF_STATUSES:
            failures.append("formal_proof.status is invalid")
        for field in ("solver", "solver_version"):
            if not isinstance(formal_proof.get(field), str) or not formal_proof.get(
                field
            ):
                failures.append(f"formal_proof.{field} must be a non-empty string")
        if isinstance(environment_document, dict):
            environment_solver = environment_document.get("solver")
            if (
                not isinstance(environment_solver, dict)
                or environment_solver.get("name") != formal_proof.get("solver")
                or environment_solver.get("version")
                != formal_proof.get("solver_version")
            ):
                failures.append(
                    "formal_proof solver identity differs from environment artifact"
                )
        options = formal_proof.get("solver_options")
        if not isinstance(options, dict) or not options:
            failures.append("formal_proof.solver_options must be a non-empty object")
        elif any(
            not isinstance(value, str | int | float | bool)
            for value in options.values()
        ):
            failures.append("formal_proof.solver_options contains a non-scalar value")
        input_digest = _require_digest(
            failures, formal_proof.get("input_digest"), "formal_proof.input_digest"
        )
        proof_input_record = _artifact_record(
            ref_records,
            formal_proof.get("input_artifact_id"),
            expected_roles={"proof-input-bundle"},
            label="formal_proof.input_artifact_id",
            failures=failures,
        )
        if (
            proof_input_record is not None
            and input_digest is not None
            and proof_input_record[2] != input_digest
        ):
            failures.append(
                "formal_proof.input_digest does not match input_artifact_id"
            )
        result_artifact_ids = formal_proof.get("result_artifact_ids")
        if not isinstance(result_artifact_ids, list) or not result_artifact_ids:
            failures.append("formal_proof.result_artifact_ids must be non-empty")
        else:
            for index, artifact_id in enumerate(result_artifact_ids):
                _artifact_record(
                    ref_records,
                    artifact_id,
                    expected_roles={"solver-result"},
                    label=f"formal_proof.result_artifact_ids[{index}]",
                    failures=failures,
                )
        assumptions = _require_nonempty_strings(
            failures, formal_proof.get("assumptions"), "formal_proof.assumptions"
        )
        obligations = formal_proof.get("obligations")
        obligation_statuses: list[str] = []
        obligation_ids: set[str] = set()
        obligation_formal_input_ids: set[str] = set()
        obligation_solver_input_ids: set[str] = set()
        obligation_solver_result_ids: set[str] = set()
        obligation_assumption_union: set[str] = set()
        if not isinstance(obligations, list) or not obligations:
            failures.append("formal_proof.obligations must be a non-empty array")
        else:
            for index, item in enumerate(obligations):
                obligation = _require_exact_keys(
                    failures,
                    item,
                    required=OBLIGATION_REQUIRED_KEYS,
                    allowed=OBLIGATION_ALLOWED_KEYS,
                    label=f"formal_proof.obligations[{index}]",
                )
                if obligation is None:
                    continue
                obligation_id = obligation.get("obligation_id")
                if not isinstance(obligation_id, str) or not obligation_id:
                    failures.append(
                        f"formal_proof.obligations[{index}].obligation_id is invalid"
                    )
                elif obligation_id in obligation_ids:
                    failures.append(
                        f"formal proof obligation id is duplicated: {obligation_id}"
                    )
                else:
                    obligation_ids.add(obligation_id)
                obligation_status = obligation.get("status")
                if obligation_status not in PROOF_STATUSES:
                    failures.append(
                        f"formal_proof.obligations[{index}].status is invalid"
                    )
                else:
                    obligation_statuses.append(obligation_status)
                if not isinstance(obligation.get("scope"), str) or not obligation.get(
                    "scope"
                ):
                    failures.append(
                        f"formal_proof.obligations[{index}].scope is invalid"
                    )
                obligation_digest = _require_digest(
                    failures,
                    obligation.get("input_digest"),
                    f"formal_proof.obligations[{index}].input_digest",
                )
                formal_input_record = _artifact_record(
                    ref_records,
                    obligation.get("formal_input_artifact_id"),
                    expected_roles={"formal-input"},
                    label=f"formal_proof.obligations[{index}].formal_input_artifact_id",
                    failures=failures,
                )
                for field_name, destination in (
                    ("formal_input_artifact_id", obligation_formal_input_ids),
                    ("solver_input_artifact_id", obligation_solver_input_ids),
                    ("solver_result_artifact_id", obligation_solver_result_ids),
                ):
                    value = obligation.get(field_name)
                    if isinstance(value, str):
                        destination.add(value)
                solver_input_record = _artifact_record(
                    ref_records,
                    obligation.get("solver_input_artifact_id"),
                    expected_roles={"solver-input"},
                    label=f"formal_proof.obligations[{index}].solver_input_artifact_id",
                    failures=failures,
                )
                solver_result_record = _artifact_record(
                    ref_records,
                    obligation.get("solver_result_artifact_id"),
                    expected_roles={"solver-result"},
                    label=f"formal_proof.obligations[{index}].solver_result_artifact_id",
                    failures=failures,
                )
                formal_input_document = None
                if formal_input_record is not None:
                    formal_input_document = _validate_formal_input_document(
                        route,
                        formal_input_record,
                        ref_records,
                        manifest,
                        formal_proof,
                        f"formal_proof.obligations[{index}].formal_input",
                        failures,
                    )
                    environment_assumptions = (
                        formal_input_document.get("environment_assumptions")
                        if isinstance(formal_input_document, dict)
                        else None
                    )
                    obligation_assumptions = obligation.get("assumptions")
                    if (
                        isinstance(environment_assumptions, list)
                        and isinstance(obligation_assumptions, list)
                        and not set(environment_assumptions).issubset(
                            set(obligation_assumptions)
                        )
                    ):
                        failures.append(
                            f"formal_proof.obligations[{index}] omits formal-input assumptions"
                        )
                if (
                    solver_input_record is not None
                    and obligation_digest is not None
                    and solver_input_record[2] != obligation_digest
                ):
                    failures.append(
                        f"formal_proof.obligations[{index}].input_digest does not match solver_input_artifact_id"
                    )
                if (
                    isinstance(result_artifact_ids, list)
                    and obligation.get("solver_result_artifact_id")
                    not in result_artifact_ids
                ):
                    failures.append(
                        f"formal_proof.obligations[{index}] result is absent from formal_proof.result_artifact_ids"
                    )
                if formal_input_record is not None and solver_input_record is not None:
                    try:
                        solver_input_text = solver_input_record[1].read_text(
                            encoding="utf-8"
                        )
                    except Exception as exc:
                        failures.append(
                            f"formal_proof.obligations[{index}] solver input is unreadable: {exc}"
                        )
                    else:
                        if formal_input_record[2] not in solver_input_text:
                            failures.append(
                                f"formal_proof.obligations[{index}] SMT input does not bind formal input"
                            )
                if formal_input_record is not None and solver_result_record is not None:
                    try:
                        result_document = load(solver_result_record[1])
                    except Exception as exc:
                        failures.append(
                            f"formal_proof.obligations[{index}] solver result is invalid JSON: {exc}"
                        )
                    else:
                        formal_input_digest = formal_input_record[2]
                        declared_formal_input_digest = result_document.get(
                            "formal_input_digest"
                        )
                        if declared_formal_input_digest != formal_input_digest:
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result does not bind formal input"
                            )
                        if result_document.get("input_digest") != formal_input_digest:
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result input_digest differs from formal input"
                            )
                        formal_input_reference = result_document.get("formal_input")
                        expected_formal_input_path = formal_input_record[1].name
                        if (
                            not isinstance(formal_input_reference, dict)
                            or formal_input_reference.get("path")
                            != expected_formal_input_path
                            or formal_input_reference.get("sha256")
                            != formal_input_digest
                        ):
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result formal_input reference drift"
                            )
                        declared_solver_input_digest = result_document.get(
                            "solver_input_digest"
                        )
                        if (
                            solver_input_record is not None
                            and declared_solver_input_digest != solver_input_record[2]
                        ):
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result does not bind SMT input"
                            )
                        result_status = result_document.get("status")
                        if result_status != obligation_status:
                            failures.append(
                                f"formal_proof.obligations[{index}] status does not match solver result"
                            )
                _require_nonempty_strings(
                    failures,
                    obligation.get("assumptions"),
                    f"formal_proof.obligations[{index}].assumptions",
                )
                if isinstance(obligation.get("assumptions"), list):
                    obligation_assumption_union.update(obligation["assumptions"])

        if (
            isinstance(result_artifact_ids, list)
            and set(result_artifact_ids) != obligation_solver_result_ids
        ):
            failures.append(
                "formal_proof.result_artifact_ids do not exactly match obligations"
            )
        if (
            isinstance(assumptions, list)
            and set(assumptions) != obligation_assumption_union
        ):
            failures.append(
                "formal_proof.assumptions do not equal the obligation assumption union"
            )

        if proof_input_record is not None:
            try:
                proof_bundle = load(proof_input_record[1])
            except Exception as exc:
                failures.append(f"formal proof input bundle is invalid JSON: {exc}")
            else:
                if proof_bundle.get("route_key") != manifest.get("route_key"):
                    failures.append("formal proof input bundle route_key mismatch")
                if proof_bundle.get("same_input_required") is not True:
                    failures.append(
                        "formal proof input bundle must require same-input composition"
                    )
                runs = proof_bundle.get("runs")
                observed_bundle_ids: dict[str, set[str]] = {
                    "formal_input": set(),
                    "smt2": set(),
                    "result": set(),
                }
                if not isinstance(runs, list) or not runs:
                    failures.append("formal proof input bundle runs are empty")
                else:
                    corpora: set[str] = set()
                    by_relative = {
                        record[0].get("path"): (artifact_id, record)
                        for artifact_id, record in ref_records.items()
                    }
                    for run_index, run in enumerate(runs):
                        if not isinstance(run, dict):
                            failures.append(
                                f"formal proof input bundle runs[{run_index}] is invalid"
                            )
                            continue
                        corpus = run.get("corpus")
                        if not isinstance(corpus, str) or corpus in corpora:
                            failures.append(
                                f"formal proof input bundle runs[{run_index}] corpus is invalid/duplicate"
                            )
                        else:
                            corpora.add(corpus)
                        for field, roles in (
                            ("formal_input", {"formal-input"}),
                            ("smt2", {"solver-input"}),
                            ("result", {"solver-result"}),
                            ("composition", {"formal-composition"}),
                        ):
                            reference = run.get(field)
                            if not isinstance(reference, dict):
                                failures.append(
                                    f"formal proof input bundle runs[{run_index}].{field} is invalid"
                                )
                                continue
                            relative = reference.get("path")
                            bound = by_relative.get(relative)
                            if bound is None or bound[1][0].get("role") not in roles:
                                failures.append(
                                    f"formal proof input bundle runs[{run_index}].{field} is not role-bound"
                                )
                                continue
                            if (
                                reference.get("sha256") != bound[1][2]
                                or reference.get("bytes") != bound[1][1].stat().st_size
                            ):
                                failures.append(
                                    f"formal proof input bundle runs[{run_index}].{field} digest/bytes mismatch"
                                )
                            if field in observed_bundle_ids:
                                observed_bundle_ids[field].add(bound[0])
                    expected_bundle_ids = {
                        "formal_input": obligation_formal_input_ids,
                        "smt2": obligation_solver_input_ids,
                        "result": obligation_solver_result_ids,
                    }
                    for field, expected_ids in expected_bundle_ids.items():
                        if observed_bundle_ids[field] != expected_ids:
                            failures.append(
                                f"formal proof input bundle {field} set does not match obligations"
                            )

        if status == "PROVED":
            if any(item != "PROVED" for item in obligation_statuses):
                failures.append(
                    "formal_proof PROVED requires every obligation to be PROVED"
                )
            if assumptions:
                failures.append("formal_proof PROVED cannot carry assumptions")
            if isinstance(obligations, list) and any(
                item.get("assumptions")
                for item in obligations
                if isinstance(item, dict)
            ):
                failures.append("PROVED obligations cannot carry assumptions")
        elif status == "PROVED_UNDER_ASSUMPTIONS":
            if not assumptions:
                failures.append(
                    "PROVED_UNDER_ASSUMPTIONS requires explicit assumptions"
                )
            if any(
                item not in {"PROVED", "PROVED_UNDER_ASSUMPTIONS"}
                for item in obligation_statuses
            ):
                failures.append(
                    "PROVED_UNDER_ASSUMPTIONS cannot contain unresolved obligations"
                )
        elif status == "AXIOM" and not assumptions:
            failures.append("AXIOM evidence requires explicit assumptions")
        if status in PROOF_STATUSES and obligation_statuses:
            precedence = (
                "COUNTEREXAMPLE",
                "TIMEOUT",
                "UNKNOWN",
                "NOT_RUN",
                "BOUNDED",
                "AXIOM",
                "PROVED_UNDER_ASSUMPTIONS",
                "PROVED",
            )
            derived = next(item for item in precedence if item in obligation_statuses)
            if status != derived:
                failures.append(
                    f"formal_proof.status {status} does not match obligation aggregate {derived}"
                )

        replay = _require_exact_keys(
            failures,
            formal_proof.get("replay"),
            required=REPLAY_KEYS,
            label="formal_proof.replay",
        )
        if replay is not None:
            command = replay.get("command")
            if (
                not isinstance(command, list)
                or not command
                or any(not isinstance(item, str) or not item for item in command)
            ):
                failures.append(
                    "formal_proof.replay.command must be a non-empty argv array"
                )
            cwd = _resolve_below(
                route, replay.get("cwd"), "formal_proof.replay.cwd", failures
            )
            if cwd is not None and not cwd.is_dir():
                failures.append("formal_proof.replay.cwd is not an existing directory")
            if (
                cwd is not None
                and cwd.is_dir()
                and isinstance(command, list)
                and command
            ):
                _validate_replay_command(
                    route=route,
                    manifest=manifest,
                    command=command,
                    cwd=cwd,
                    records=ref_records,
                    failures=failures,
                )
            if replay.get("expected_exit_code") != 0:
                failures.append("formal_proof.replay.expected_exit_code must be zero")
            replay_result_digest = _require_digest(
                failures,
                replay.get("expected_result_sha256"),
                "formal_proof.replay.expected_result_sha256",
            )
            replay_result = _artifact_record(
                ref_records,
                replay.get("expected_result_artifact_id"),
                expected_roles={"solver-result"},
                label="formal_proof.replay.expected_result_artifact_id",
                failures=failures,
            )
            if (
                replay_result is not None
                and replay_result_digest is not None
                and replay_result[2] != replay_result_digest
            ):
                failures.append(
                    "formal_proof.replay expected result digest does not match artifact"
                )

    return evidence, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("route_dir")
    args = parser.parse_args()
    route = Path(args.route_dir)
    errors: list[str] = []
    manifest: dict[str, Any] = {}
    certification: dict[str, Any] = {}
    if not route.is_dir():
        errors.append(f"missing route dir: {route}")
    for directory in REQUIRED_DIRS:
        if not (route / directory).exists():
            errors.append(f"missing: {route / directory}")
    try:
        manifest = load(route / "route.json")
        for key in REQUIRED_ROUTE:
            if key not in manifest:
                errors.append(f"route.json missing key: {key}")
        if manifest.get("status") not in ALLOWED_ROUTE_STATUS:
            errors.append("invalid route status")
        if manifest.get("source", {}).get("language") == manifest.get("target", {}).get(
            "language"
        ):
            errors.append("source and target must differ")
        if not manifest.get("source", {}).get("versions"):
            errors.append("source versions are empty")
        if not manifest.get("target", {}).get("versions"):
            errors.append("target versions are empty")
        if manifest.get("owner") in {"", "UNASSIGNED", None}:
            errors.append("route owner is unassigned")
    except Exception as exc:
        errors.append(str(exc))
    try:
        support = load(route / "support-matrix.json")
        if support.get("route_key") != manifest.get("route_key"):
            errors.append("support matrix route_key mismatch")
        for capability in support.get("capabilities", []):
            if capability.get("status") not in ALLOWED_CAP_STATUS:
                errors.append(f"invalid capability status: {capability.get('id')}")
            evidence_refs = capability.get("evidence_refs")
            if (
                capability.get("status") in {"certified", "supported"}
                and not evidence_refs
            ):
                errors.append(
                    f"{capability.get('status')} capability lacks evidence: {capability.get('id')}"
                )
            if capability.get("status") in {
                "conditional",
                "blocked",
            } and not capability.get("reason"):
                errors.append(
                    f"conditional/blocked capability lacks reason: {capability.get('id')}"
                )
            if isinstance(evidence_refs, list):
                for index, reference in enumerate(evidence_refs):
                    path = _resolve_below(
                        route,
                        reference,
                        f"capability {capability.get('id')} evidence_refs[{index}]",
                        errors,
                    )
                    if path is not None and not path.is_file():
                        errors.append(
                            f"capability evidence is missing: {capability.get('id')}:{reference}"
                        )
    except Exception as exc:
        errors.append(str(exc))
    for file_path in [
        route / "compat-runtime" / "manifest.json",
        route / "certification" / "evidence.json",
        route / "certification" / "certification.json",
    ]:
        try:
            load(file_path)
        except Exception as exc:
            errors.append(str(exc))
    try:
        certification = load(route / "certification" / "certification.json")
        if (
            str(certification.get("status", "")).lower()
            != str(manifest.get("status", "")).lower()
        ):
            errors.append("route and certification statuses must match")
        _, strict_errors = validate_formal_equivalence(route, manifest, certification)
        errors.extend(strict_errors)
    except Exception as exc:
        errors.append(str(exc))
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"OK: {route}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

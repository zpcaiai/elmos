#!/usr/bin/env python3
"""Allowlisted Precision Migration adapter dispatcher.

The registry is generated from immutable Skill identities.  Repository content
can select neither a command nor an executable.  Handlers either perform a
bounded read-only operation, invoke one exact checked-in validator, or return a
typed REQUIRES_ADAPTER result.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.precision_migration.runtime import Registry, batch_plan, canonical_digest, evaluate
from scripts.precision_migration.trust import TrustStore, configured_roots


REGISTRY_PATH = ROOT / "docs" / "precision-migration-b01-44" / "adapter-registry.json"
MAX_SCAN_FILES = 50_000
MAX_CAPTURE_BYTES = 1024 * 1024
ALLOWED_REQUEST_KEYS = {
    "request_id", "skill", "mode", "inputs", "policy", "evidence",
    "semantic_losses", "approvals", "claimed_status",
}
ALLOWED_MODES = {"assess", "transform", "validate", "repair", "certify"}
ALLOWED_RISK = {"low", "medium", "high", "critical"}


class AdapterError(ValueError):
    pass


def validate_request_contract(request: Any) -> dict[str, Any]:
    """Validate the fail-closed request envelope without third-party runtime dependencies."""
    if not isinstance(request, dict):
        raise AdapterError("request root must be an object")
    missing = {"request_id", "skill", "mode", "inputs", "policy", "evidence"} - set(request)
    if missing:
        raise AdapterError(f"request lacks required fields: {sorted(missing)}")
    unknown = set(request) - ALLOWED_REQUEST_KEYS
    if unknown:
        raise AdapterError(f"request contains unsupported fields: {sorted(unknown)}")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 200:
        raise AdapterError("request_id must be a non-empty string of at most 200 characters")
    skill = request.get("skill")
    if not isinstance(skill, str) or not skill or len(skill) > 200:
        raise AdapterError("skill must be a non-empty string of at most 200 characters")
    if request.get("mode") not in ALLOWED_MODES:
        raise AdapterError("request mode is invalid")
    inputs = request.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) - {"assets", "parameters"}:
        raise AdapterError("inputs must contain only assets and parameters")
    if not isinstance(inputs.get("assets"), list):
        raise AdapterError("inputs.assets must be an array")
    if "parameters" in inputs and not isinstance(inputs.get("parameters"), dict):
        raise AdapterError("inputs.parameters must be an object")
    policy = request.get("policy")
    if not isinstance(policy, dict) or set(policy) - {
        "unresolved_differences", "allow_test_weakening", "require_provenance",
        "risk_level", "request_actor",
    }:
        raise AdapterError("policy contains unsupported fields")
    if policy.get("unresolved_differences") != "block":
        raise AdapterError("policy.unresolved_differences must be block")
    if policy.get("allow_test_weakening") is not False:
        raise AdapterError("policy.allow_test_weakening must be false")
    if policy.get("require_provenance") is not True:
        raise AdapterError("policy.require_provenance must be true")
    if policy.get("risk_level") not in ALLOWED_RISK:
        raise AdapterError("policy.risk_level is invalid")
    actor = policy.get("request_actor")
    if actor is not None and (not isinstance(actor, str) or not actor or len(actor) > 200):
        raise AdapterError("policy.request_actor is invalid")
    for field in ("evidence", "semantic_losses", "approvals"):
        if field in request and not isinstance(request.get(field), list):
            raise AdapterError(f"{field} must be an array")
    return request


def _confined(path: Path, roots: tuple[Path, ...]) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise AdapterError("adapter input escapes approved roots")
    return resolved


def _write_once(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        raise AdapterError(f"refusing to overwrite adapter artifact: {path}")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.write_bytes(encoded)
    return {
        "uri": path.resolve().as_uri(),
        "digest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
        "size_bytes": len(encoded),
        "media_type": "application/json",
    }


@dataclass(frozen=True)
class AdapterRegistry:
    payload: dict[str, Any]
    by_skill: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, path: Path = REGISTRY_PATH) -> "AdapterRegistry":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1 or payload.get("namespace") != "precision-migration-b01-44":
            raise AdapterError("adapter registry identity is invalid")
        entries = payload.get("entries")
        if not isinstance(entries, list) or len(entries) != 632:
            raise AdapterError("adapter registry must contain exactly 632 entries")
        by_skill: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("skill"), str):
                raise AdapterError("adapter registry contains an invalid entry")
            if entry["skill"] in by_skill:
                raise AdapterError(f"duplicate adapter identity: {entry['skill']}")
            by_skill[entry["skill"]] = entry
        return cls(payload=payload, by_skill=by_skill)

    def resolve(self, skill: str, skill_registry: Registry) -> dict[str, Any]:
        record = skill_registry.resolve(skill)
        entry = self.by_skill.get(str(record["name"]))
        if entry is None or entry.get("source_skill") != record.get("source_name"):
            raise AdapterError("adapter registry and installed Skill identity diverged")
        return entry

    def validate_handlers(self) -> list[str]:
        errors: list[str] = []
        for entry in self.by_skill.values():
            dotted = entry.get("handler_entrypoint")
            if not isinstance(dotted, str) or ":" not in dotted:
                errors.append(f"{entry['skill']}: invalid handler entrypoint")
                continue
            module_name, function_name = dotted.split(":", 1)
            try:
                function = getattr(importlib.import_module(module_name), function_name)
            except (ImportError, AttributeError) as exc:
                errors.append(f"{entry['skill']}: handler cannot be imported: {exc}")
                continue
            if not callable(function):
                errors.append(f"{entry['skill']}: handler is not callable")
            missing = [surface for surface in entry.get("repository_surfaces", []) if not (ROOT / surface).exists()]
            if missing != entry.get("missing_surfaces", []):
                errors.append(f"{entry['skill']}: repository surface status drifted")
            if entry.get("binding_state") == "DECLARED" and not entry.get("supported_modes"):
                errors.append(f"{entry['skill']}: declared handler has no supported mode")
        return errors


def explain_missing_adapter(
    request: dict[str, Any],
    entry: dict[str, Any],
    output_dir: Path,
    **_: Any,
) -> dict[str, Any]:
    artifact = _write_once(
        output_dir / "adapter-obligation.json",
        {
            "schema_version": 1,
            "skill": entry["skill"],
            "source_skill": entry["source_skill"],
            "handler_id": entry["handler_id"],
            "state": "REQUIRES_ADAPTER",
            "required_mode": request.get("mode"),
            "required_outputs": ["exact-domain-artifact", "native-execution-evidence", "independent-verification"],
            "reason": "No exact allowlisted domain handler exists for this Skill and mode.",
        },
    )
    return {"execution_state": "REQUIRES_ADAPTER", "artifacts": [artifact], "exit_code": 3}


def execute_orchestrator_plan(
    request: dict[str, Any],
    entry: dict[str, Any],
    output_dir: Path,
    *,
    skill_registry: Registry,
    **_: Any,
) -> dict[str, Any]:
    record = skill_registry.resolve(str(entry["skill"]))
    artifact = _write_once(output_dir / "migration-plan.json", batch_plan(skill_registry, record))
    return {"execution_state": "LOCAL_EXECUTED", "artifacts": [artifact], "exit_code": 0}


def execute_repository_assessment(
    request: dict[str, Any],
    entry: dict[str, Any],
    output_dir: Path,
    *,
    evidence_roots: tuple[Path, ...],
    **_: Any,
) -> dict[str, Any]:
    inputs = request.get("inputs") if isinstance(request.get("inputs"), dict) else {}
    parameters = inputs.get("parameters") if isinstance(inputs.get("parameters"), dict) else {}
    workspace_value = parameters.get("workspace_path")
    if not isinstance(workspace_value, str) or not workspace_value:
        raise AdapterError("repository assessment requires inputs.parameters.workspace_path")
    workspace = _confined(Path(workspace_value), evidence_roots)
    if not workspace.is_dir():
        raise AdapterError("repository assessment workspace_path must be a directory")
    extensions: dict[str, int] = {}
    manifests: list[str] = []
    total_files = 0
    total_bytes = 0
    truncated = False
    manifest_names = {
        "pom.xml", "build.gradle", "build.gradle.kts", "package.json", "pyproject.toml",
        "requirements.txt", "go.mod", "Cargo.toml", "Dockerfile", "compose.yaml",
    }
    for path in sorted(workspace.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        total_files += 1
        if total_files > MAX_SCAN_FILES:
            truncated = True
            break
        total_bytes += path.stat().st_size
        suffix = path.suffix.lower() or "[no-extension]"
        extensions[suffix] = extensions.get(suffix, 0) + 1
        if path.name in manifest_names:
            manifests.append(path.relative_to(workspace).as_posix())
    report = {
        "schema_version": 1,
        "skill": entry["skill"],
        "workspace": str(workspace),
        "file_count": min(total_files, MAX_SCAN_FILES),
        "byte_count": total_bytes,
        "extension_counts": dict(sorted(extensions.items(), key=lambda item: (-item[1], item[0]))),
        "detected_manifests": manifests,
        "scan_limit": MAX_SCAN_FILES,
        "truncated": truncated,
        "execution_boundary": "read-only inventory; build and runtime evidence remain NOT_RUN",
    }
    artifact = _write_once(output_dir / "repository-assessment.json", report)
    state = "INCONCLUSIVE" if truncated else "LOCAL_EXECUTED"
    return {"execution_state": state, "artifacts": [artifact], "exit_code": 0 if not truncated else 4}


def execute_batch29_route_validation(
    request: dict[str, Any],
    entry: dict[str, Any],
    output_dir: Path,
    **_: Any,
) -> dict[str, Any]:
    route_key = str(entry["source_skill"]).removesuffix("-direction-pack")
    route_dir = ROOT / "routes" / route_key
    if not (route_dir / "route.json").is_file():
        raise AdapterError(f"exact route pack is unavailable: {route_key}")
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "batch29" / "validate_route.py"), str(route_dir)],
        cwd=ROOT,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
        capture_output=True,
        timeout=int(entry.get("timeout_seconds", 120)),
    )
    if len(completed.stdout) + len(completed.stderr) > MAX_CAPTURE_BYTES:
        raise AdapterError("adapter validator output exceeded the capture budget")
    report = {
        "schema_version": 1,
        "skill": entry["skill"],
        "route_key": route_key,
        "command_identity": "scripts/batch29/validate_route.py",
        "exit_code": completed.returncode,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "stdout": completed.stdout.decode("utf-8", errors="replace"),
        "stderr": completed.stderr.decode("utf-8", errors="replace"),
        "execution_boundary": "route-pack validation only; native source/target execution remains separately evidenced",
    }
    artifact = _write_once(output_dir / "route-validation.json", report)
    return {
        "execution_state": "LOCAL_EXECUTED" if completed.returncode == 0 else "FAILED",
        "artifacts": [artifact],
        "exit_code": completed.returncode,
    }


def execute_evidence_gate(
    request: dict[str, Any],
    entry: dict[str, Any],
    output_dir: Path,
    *,
    skill_registry: Registry,
    evidence_roots: tuple[Path, ...],
    trust_store: TrustStore | None,
    **_: Any,
) -> dict[str, Any]:
    result = evaluate(
        request,
        skill_registry,
        evidence_roots=evidence_roots,
        trust_store=trust_store,
    )
    artifact = _write_once(output_dir / "evidence-evaluation.json", result)
    return {
        "execution_state": "LOCAL_EXECUTED" if result["status"] in {"VERIFIED", "PROVED"} else result["status"],
        "artifacts": [artifact],
        "exit_code": 0 if result["status"] in {"VERIFIED", "PROVED"} else 4,
    }


HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "contract-only-v1": explain_missing_adapter,
    "orchestrator-plan-v1": execute_orchestrator_plan,
    "repository-assessment-v1": execute_repository_assessment,
    "batch29-route-validator-v1": execute_batch29_route_validation,
    "precision-evidence-gate-v1": execute_evidence_gate,
}


def execute(
    request: dict[str, Any],
    output_dir: Path,
    *,
    evidence_roots: Iterable[Path] | None = None,
    trust_store: TrustStore | Path | None = None,
    adapter_registry: AdapterRegistry | None = None,
    skill_registry: Registry | None = None,
) -> dict[str, Any]:
    request = validate_request_contract(request)
    skill_registry = skill_registry or Registry.load()
    adapter_registry = adapter_registry or AdapterRegistry.load()
    entry = adapter_registry.resolve(str(request.get("skill", "")), skill_registry)
    mode = request.get("mode")
    supported = entry.get("supported_modes", [])
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    roots = configured_roots(evidence_roots)
    loaded_trust = TrustStore.load(trust_store) if isinstance(trust_store, Path) else trust_store
    handler = HANDLERS.get(str(entry.get("handler_id")))
    if handler is None or mode not in supported:
        handler = explain_missing_adapter
    started = time.monotonic()
    result = handler(
        request,
        entry,
        output_dir,
        skill_registry=skill_registry,
        evidence_roots=roots,
        trust_store=loaded_trust,
    )
    envelope_without_digest = {
        "schema_version": 1,
        "request_id": request.get("request_id"),
        "skill": entry["skill"],
        "handler_id": entry["handler_id"],
        "declared_maturity": entry["maturity"],
        "mode": mode,
        "execution_state": result["execution_state"],
        "artifacts": result["artifacts"],
        "duration_ms": round((time.monotonic() - started) * 1000),
        "production_certification": "NOT_CERTIFIED",
        "production_operation_authorized": False,
    }
    return {**envelope_without_digest, "result_digest": canonical_digest(envelope_without_digest), "exit_code": result["exit_code"]}


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate_parser = sub.add_parser("validate-registry")
    validate_parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    run_parser = sub.add_parser("execute")
    run_parser.add_argument("--request", type=Path, required=True)
    run_parser.add_argument("--output-dir", type=Path, required=True)
    run_parser.add_argument("--evidence-root", type=Path, action="append", default=[])
    run_parser.add_argument("--trust-store", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        registry = AdapterRegistry.load(args.registry if args.command == "validate-registry" else REGISTRY_PATH)
        if args.command == "validate-registry":
            errors = registry.validate_handlers()
            payload = {"status": "PASS" if not errors else "FAIL", "entries": len(registry.by_skill), "errors": errors}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if not errors else 2
        request = json.loads(args.request.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise AdapterError("request root must be an object")
        result = execute(
            request,
            args.output_dir,
            evidence_roots=args.evidence_root,
            trust_store=args.trust_store,
            adapter_registry=registry,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(result["exit_code"])
    except (AdapterError, OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

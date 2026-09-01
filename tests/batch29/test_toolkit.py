import argparse
import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "batch29"
MATRIX_VALIDATOR = (
    ROOT / "scripts" / "operations" / "validate_translation_route_matrix.py"
)
POLYGLOT_RUNNER = SCRIPTS / "run_polyglot_routes.py"
FRESH_ROUTE_RUNTIME = SCRIPTS / "fresh_route_runtime.py"
SPECIALIZED_PACK_GENERATOR = (
    ROOT / "tooling" / "generate_specialized_polyglot_formal_verification_pack.py"
)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def copy_fixture_tree_to_private_writable_root(
    source: Path,
    destination: Path,
    *,
    temporary_root: Path,
) -> Path:
    """Copy a frozen fixture into one confined, owner-writable test tree."""

    resolved_temporary_root = temporary_root.resolve(strict=True)
    resolved_parent = destination.parent.resolve(strict=True)
    try:
        resolved_parent.relative_to(resolved_temporary_root)
    except ValueError as exc:
        raise ValueError("fixture destination escapes private temporary root") from exc

    resolved_source = source.resolve(strict=True)
    source_entries = (resolved_source, *sorted(resolved_source.rglob("*")))
    for entry in source_entries:
        metadata = entry.lstat()
        if entry.is_symlink() or not (
            stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)
        ):
            raise ValueError("fixture source contains an unsupported entry")

    shutil.copytree(resolved_source, destination)
    resolved_destination = destination.resolve(strict=True)
    resolved_destination.relative_to(resolved_temporary_root)
    copied_entries = (
        resolved_destination,
        *sorted(resolved_destination.rglob("*")),
    )
    for entry in copied_entries:
        metadata = entry.lstat()
        if entry.is_symlink():
            raise ValueError("fixture copy contains a symbolic link")
        mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISDIR(metadata.st_mode):
            entry.chmod(mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        elif stat.S_ISREG(metadata.st_mode):
            entry.chmod(mode | stat.S_IRUSR | stat.S_IWUSR)
        else:
            raise ValueError("fixture copy contains an unsupported entry")
    return resolved_destination


def artifact_ref(route: Path, relative: str) -> dict[str, object]:
    path = route / relative
    return {"path": relative, "sha256": digest(path), "bytes": path.stat().st_size}


def strict_artifact_id(relative: str) -> str:
    return "artifact-" + hashlib.sha256(relative.encode("utf-8")).hexdigest()


def strict_artifact_ref(route: Path, relative: str, role: str) -> dict[str, object]:
    return {
        "artifact_id": strict_artifact_id(relative),
        "role": role,
        **artifact_ref(route, relative),
    }


def load_matrix_validator():
    spec = importlib.util.spec_from_file_location(
        "batch29_matrix_validator", MATRIX_VALIDATOR
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_polyglot_runner():
    spec = importlib.util.spec_from_file_location(
        "batch29_polyglot_runner", POLYGLOT_RUNNER
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_route_validator():
    spec = importlib.util.spec_from_file_location(
        "batch29_route_validator", SCRIPTS / "validate_route.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_route_gate():
    spec = importlib.util.spec_from_file_location(
        "batch29_route_gate", SCRIPTS / "run_route_gate.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    scripts_value = str(SCRIPTS)
    inserted = scripts_value not in sys.path
    if inserted:
        sys.path.insert(0, scripts_value)
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted:
            sys.path.remove(scripts_value)
    return module


def load_specialized_pack_generator():
    tooling = str(SPECIALIZED_PACK_GENERATOR.parent)
    inserted = tooling not in sys.path
    if inserted:
        sys.path.insert(0, tooling)
    try:
        spec = importlib.util.spec_from_file_location(
            "batch29_specialized_pack_generator",
            SPECIALIZED_PACK_GENERATOR,
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(tooling)


def load_fresh_route_runtime():
    spec = importlib.util.spec_from_file_location(
        "batch29_fresh_route_runtime", FRESH_ROUTE_RUNTIME
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def refresh_module_report_reference(route: Path, report: dict[str, object]) -> None:
    report_path = route / "certification" / "module-equivalence.json"
    write_json(report_path, report)
    certification_path = route / "certification" / "certification.json"
    certification = json.loads(certification_path.read_text())
    certification["module_equivalence"] = artifact_ref(
        route, "certification/module-equivalence.json"
    )
    write_json(certification_path, certification)


def module_artifact(report: dict[str, object], relative: str) -> dict[str, object]:
    return next(
        item
        for item in report["artifact_refs"]
        if isinstance(item, dict) and item.get("path") == relative
    )


def refresh_module_artifact(
    route: Path, report: dict[str, object], relative: str
) -> None:
    reference = module_artifact(report, relative)
    path = route / relative
    reference["sha256"] = digest(path)
    reference["bytes"] = path.stat().st_size


def refresh_module_semantic_bindings(route: Path, report: dict[str, object]) -> None:
    validator = load_route_validator()
    module_input = report["module_input"]
    for side in ("source", "target"):
        role = f"{side}-module-semantic-ir"
        reference = next(
            item for item in report["artifact_refs"] if item["role"] == role
        )
        relative = reference["path"]
        document = json.loads((route / relative).read_text())
        module_input[f"{side}_semantic_ir_sha256"] = validator.canonical_json_sha256(
            document
        )
        refresh_module_artifact(route, report, relative)
    module_input_relative = next(
        item["path"]
        for item in report["artifact_refs"]
        if item["role"] == "module-formal-input"
    )
    write_json(route / module_input_relative, module_input)
    refresh_module_artifact(route, report, module_input_relative)
    report["module_input_sha256"] = validator.canonical_json_sha256(module_input)


def install_fresh_cpp_java_module_evidence(route: Path) -> dict[str, object]:
    """Regenerate current module closure only inside a disposable route copy."""

    runner = load_polyglot_runner()
    module_ref, module_manifest_ref = runner.execute_module_route(
        route.parent,
        route,
        ROOT / "engines" / "polyglot-route-engine" / "fixtures",
        "cpp",
        "java",
        None,
    )
    certification_path = route / "certification" / "certification.json"
    certification = json.loads(certification_path.read_text())
    certification["module_equivalence"] = module_ref
    write_json(certification_path, certification)
    evidence_path = route / "certification" / "evidence.json"
    evidence = json.loads(evidence_path.read_text())
    evidence["module_equivalence"] = module_ref
    evidence["module_artifact_manifest"] = module_manifest_ref
    evidence["artifact_refs"] = [
        module_manifest_ref if item.get("path") == module_manifest_ref["path"] else item
        for item in evidence.get("artifact_refs", [])
    ]
    write_json(evidence_path, evidence)
    return json.loads((route / "certification" / "module-equivalence.json").read_text())


def install_strict_evidence(
    route: Path, proof_status: str = "PROVED_UNDER_ASSUMPTIONS"
) -> tuple[Path, Path]:
    artifacts = route / "certification" / "strict-artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    engine_source = ROOT / "engines" / "polyglot-route-engine" / "src"
    engine_source_value = str(engine_source)
    if engine_source_value not in sys.path:
        sys.path.insert(0, engine_source_value)
    from dataclasses import replace as dataclass_replace

    from elmos_polyglot_route.emitter import EmittedFile
    from elmos_polyglot_route.engine import _formal_input_payload
    from elmos_polyglot_route.identifier_hygiene import (
        alpha_normalize_target,
        identifier_plan_bytes,
        plan_identifiers,
        standalone_artifact_unit_namespace,
        target_ir_view,
    )
    from elmos_polyglot_route.models import SemanticIR

    source_runtime_path = artifacts / "source-runtime" / "source.py"
    source_runtime_path.parent.mkdir(parents=True)
    source_runtime_path.write_text(
        "def calculate(value: int) -> int:\n    return value\n"
    )
    target_artifact_path = artifacts / "target-artifact.txt"
    target_artifact_path.write_text(
        "export function calculate(value: number): number { return value; }\n"
    )
    source_ir = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "python",
            "source_file": "source.py",
            "analyzer": "fixture-python-analyzer",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "calculate",
                    "parameters": [{"name": "value", "type": "integer"}],
                    "return_type": "integer",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {"kind": "name", "value": "value"},
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )
    identifier_namespace = standalone_artifact_unit_namespace(
        "source.py", digest(source_runtime_path)
    )
    identifier_plan = plan_identifiers(
        source_ir,
        "typescript",
        unit_namespace=identifier_namespace,
    )
    raw_target_ir = dataclass_replace(
        target_ir_view(source_ir, identifier_plan),
        source_language="typescript",
        source_file="target-artifact.txt",
        analyzer="fixture-typescript-relifter",
        analyzer_version="1",
    )
    target_ir = alpha_normalize_target(source_ir, raw_target_ir, identifier_plan)
    source_ir_value = source_ir.to_mapping()
    raw_target_ir_value = raw_target_ir.to_mapping()
    target_ir_value = target_ir.to_mapping()
    (artifacts / "source-ir.json").write_bytes(
        (
            json.dumps(source_ir_value, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
    )
    (artifacts / "target-semantic-ir.raw.json").write_bytes(
        (
            json.dumps(raw_target_ir_value, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode()
    )
    (artifacts / "target-semantic-ir.normalized.json").write_bytes(
        (
            json.dumps(target_ir_value, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
    )
    (artifacts / "identifier-plan.json").write_bytes(
        identifier_plan_bytes(identifier_plan)
    )
    aggregate_ir_bytes = (
        json.dumps(
            {"functions": [source_ir.functions[0].semantic_mapping()]},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    aggregate_root = route / "certification" / "formal-artifacts"
    aggregate_root.mkdir(parents=True, exist_ok=True)
    (aggregate_root / "source-ir.aggregate.json").write_bytes(aggregate_ir_bytes)
    (aggregate_root / "target-ir.aggregate.json").write_bytes(aggregate_ir_bytes)
    semantic_hash = load_route_validator().canonical_json_sha256(
        source_ir.functions[0].semantic_mapping()
    )
    source_chunk_id = (
        "sha256:"
        + hashlib.sha256(
            f"{digest(source_runtime_path)}\0/functions/0\0{semantic_hash}".encode()
        ).hexdigest()
    )
    target_chunk_id = (
        "sha256:"
        + hashlib.sha256(
            f"{digest(target_artifact_path)}\0/functions/0\0{semantic_hash}".encode()
        ).hexdigest()
    )
    (artifacts / "environment.json").write_text('{"toolchain":"pinned"}\n')
    (artifacts / "chunk-map.json").write_text(
        json.dumps(
            {
                "status": "PASSED",
                "path_scheme": "rfc6901-json-pointer-v1",
                "required_source_chunk_count": 1,
                "mapped_source_chunk_count": 1,
                "mismatch_count": 0,
                "unexpected_target_chunk_count": 0,
                "coverage": 1.0,
                "mappings": [
                    {
                        "semantic_path": "/functions/0",
                        "semantic_hash": semantic_hash,
                        "source_artifact_pointer": (
                            f"{digest(source_runtime_path)}#/functions/0"
                        ),
                        "target_artifact_pointer": (
                            f"{digest(target_artifact_path)}#/functions/0"
                        ),
                        "source_chunk_id": source_chunk_id,
                        "target_chunk_id": target_chunk_id,
                        "status": "EXACT",
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n"
    )
    (artifacts / "behavior.json").write_text(
        json.dumps(
            {
                "case_count": 3,
                "pass_count": 3,
                "oracle_conflict_count": 0,
                "source_runtime_passed": True,
                "target_runtime_passed": True,
            },
            sort_keys=True,
        )
        + "\n"
    )
    runner = load_polyglot_runner()
    engine_source_manifest_path, captured_engine_sources = (
        runner._capture_engine_sources(ROOT, route)
    )
    engine_capture_root = (
        route / "certification" / "formal-artifacts" / "engine-sources"
    )
    captured_lock_path = (
        engine_capture_root / "engines" / "polyglot-route-engine" / "uv.lock"
    )
    manifest = json.loads((route / "route.json").read_text())
    (artifacts / "environment.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "route_key": manifest["route_key"],
                "authority": "local-engineering-validation",
                "independent_verification": "NOT_RUN",
                "external_certification": "NOT_RUN",
                "engine_source_manifest": {
                    "path": engine_source_manifest_path.relative_to(route).as_posix(),
                    "sha256": digest(engine_source_manifest_path),
                    "bytes": engine_source_manifest_path.stat().st_size,
                },
                "solver": {"name": "z3", "version": "4.15.3"},
                "route_engine_lock": {
                    "path": "engines/polyglot-route-engine/uv.lock",
                    "sha256": digest(captured_lock_path),
                },
            },
            sort_keys=True,
        )
        + "\n"
    )
    source_bytes = source_runtime_path.read_bytes()
    target_bytes = target_artifact_path.read_bytes()
    formal_input_value = _formal_input_payload(
        source_language="python",
        target_language="typescript",
        source_path="source.py",
        source_bytes=source_bytes,
        target_path="target-artifact.txt",
        target_bytes=target_bytes,
        source_ir=source_ir,
        raw_target_ir=raw_target_ir,
        target_ir=target_ir,
        source_ir_reference={
            "path": "source-ir.json",
            "sha256": digest(artifacts / "source-ir.json"),
        },
        raw_target_ir_reference={
            "path": "target-semantic-ir.raw.json",
            "sha256": digest(artifacts / "target-semantic-ir.raw.json"),
        },
        target_ir_reference={
            "path": "target-semantic-ir.normalized.json",
            "sha256": digest(artifacts / "target-semantic-ir.normalized.json"),
        },
        identifier_plan=identifier_plan,
        identifier_plan_reference={
            "path": "identifier-plan.json",
            "sha256": digest(artifacts / "identifier-plan.json"),
        },
        emitted=EmittedFile(
            relative_path="target-artifact.txt",
            content=target_bytes.decode("utf-8"),
        ),
    )
    assumptions = list(formal_input_value["environment_assumptions"])
    solver_identity = formal_input_value["solver"]
    environment_value = json.loads((artifacts / "environment.json").read_text())
    environment_value["solver"] = {
        "name": solver_identity["name"],
        "version": solver_identity["version"],
    }
    (artifacts / "environment.json").write_text(
        json.dumps(environment_value, sort_keys=True) + "\n"
    )
    (artifacts / "formal-input.json").write_text(
        json.dumps(formal_input_value, sort_keys=True, separators=(",", ":")) + "\n"
    )
    formal_input_digest = digest(artifacts / "formal-input.json")
    (artifacts / "proof-input.smt2").write_text(
        f"; formal_input_digest {formal_input_digest}\n(check-sat)\n"
    )
    solver_input_digest = digest(artifacts / "proof-input.smt2")
    (artifacts / "proof-result.json").write_text(
        json.dumps(
            {
                "status": proof_status,
                "input_digest": formal_input_digest,
                "formal_input_digest": formal_input_digest,
                "formal_input": {
                    "path": "formal-input.json",
                    "sha256": formal_input_digest,
                },
                "solver_input_digest": solver_input_digest,
            },
            sort_keys=True,
        )
        + "\n"
    )
    (artifacts / "proof-composition.json").write_text(
        '{"status":"PROVED_UNDER_ASSUMPTIONS"}\n'
    )
    (artifacts / "proof-input-bundle.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "route_key": manifest["route_key"],
                "property_id": "L0-DENOTATIONAL-EQUIVALENCE",
                "same_input_required": True,
                "runs": [
                    {
                        "corpus": "strict-artifacts",
                        "formal_input": artifact_ref(
                            route,
                            "certification/strict-artifacts/formal-input.json",
                        ),
                        "smt2": artifact_ref(
                            route,
                            "certification/strict-artifacts/proof-input.smt2",
                        ),
                        "result": artifact_ref(
                            route,
                            "certification/strict-artifacts/proof-result.json",
                        ),
                        "composition": artifact_ref(
                            route,
                            "certification/strict-artifacts/proof-composition.json",
                        ),
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n"
    )
    replay_tool = route / "tools" / "replay-proof.py"
    replay_tool.parent.mkdir(parents=True, exist_ok=True)
    replay_tool.write_text("raise SystemExit(0)\n")
    strict_paths = {
        "source": "certification/strict-artifacts/source-ir.json",
        "raw_target": "certification/strict-artifacts/target-semantic-ir.raw.json",
        "target": "certification/strict-artifacts/target-semantic-ir.normalized.json",
        "identifier_plan": "certification/strict-artifacts/identifier-plan.json",
        "source_aggregate": "certification/formal-artifacts/source-ir.aggregate.json",
        "target_aggregate": "certification/formal-artifacts/target-ir.aggregate.json",
        "artifact": "certification/strict-artifacts/target-artifact.txt",
        "environment": "certification/strict-artifacts/environment.json",
        "chunk": "certification/strict-artifacts/chunk-map.json",
        "behavior": "certification/strict-artifacts/behavior.json",
        "formal_input": "certification/strict-artifacts/formal-input.json",
        "solver_input": "certification/strict-artifacts/proof-input.smt2",
        "solver_result": "certification/strict-artifacts/proof-result.json",
        "proof_bundle": "certification/strict-artifacts/proof-input-bundle.json",
        "composition": "certification/strict-artifacts/proof-composition.json",
        "source_runtime": "certification/strict-artifacts/source-runtime/source.py",
        "engine_manifest": engine_source_manifest_path.relative_to(route).as_posix(),
        "replay_tool": "tools/replay-proof.py",
    }
    references = [
        strict_artifact_ref(route, strict_paths["source"], "source-ir"),
        strict_artifact_ref(route, strict_paths["raw_target"], "raw-target-ir"),
        strict_artifact_ref(route, strict_paths["target"], "normalized-target-ir"),
        strict_artifact_ref(route, strict_paths["identifier_plan"], "identifier-plan"),
        strict_artifact_ref(route, strict_paths["source_aggregate"], "source-ir"),
        strict_artifact_ref(route, strict_paths["target_aggregate"], "target-ir"),
        strict_artifact_ref(route, strict_paths["artifact"], "target-artifact"),
        strict_artifact_ref(route, strict_paths["environment"], "environment"),
        strict_artifact_ref(route, strict_paths["chunk"], "chunk-map"),
        strict_artifact_ref(route, strict_paths["behavior"], "behavior-result"),
        strict_artifact_ref(route, strict_paths["formal_input"], "formal-input"),
        strict_artifact_ref(route, strict_paths["solver_input"], "solver-input"),
        strict_artifact_ref(route, strict_paths["solver_result"], "solver-result"),
        strict_artifact_ref(route, strict_paths["proof_bundle"], "proof-input-bundle"),
        strict_artifact_ref(route, strict_paths["composition"], "formal-composition"),
        strict_artifact_ref(route, strict_paths["source_runtime"], "corpus-artifact"),
        strict_artifact_ref(
            route, strict_paths["engine_manifest"], "engine-source-manifest"
        ),
        strict_artifact_ref(route, strict_paths["replay_tool"], "replay-tool"),
    ]
    references.extend(
        strict_artifact_ref(
            route,
            captured_engine_source.relative_to(route).as_posix(),
            "engine-source",
        )
        for captured_engine_source in captured_engine_sources
    )
    source_ir = aggregate_root / "source-ir.aggregate.json"
    target_ir = aggregate_root / "target-ir.aggregate.json"
    proof_input = route / "certification" / "strict-artifacts" / "proof-input.smt2"
    source_id = strict_artifact_id(strict_paths["source_aggregate"])
    target_id = strict_artifact_id(strict_paths["target_aggregate"])
    chunk_source_id = strict_artifact_id(strict_paths["source"])
    chunk_target_id = strict_artifact_id(strict_paths["target"])
    result_id = strict_artifact_id(strict_paths["solver_result"])
    formal = {
        "schema_version": 2,
        "route_key": json.loads((route / "route.json").read_text())["route_key"],
        "route_manifest_sha256": digest(route / "route.json"),
        "semantic_profile": "typed-pure-function-v1",
        "semantic_profile_sha256": digest(route / "lowering" / "profile.json"),
        "artifact_sha256": digest(artifacts / "target-artifact.txt"),
        "artifact_id": strict_artifact_id(strict_paths["artifact"]),
        "environment_sha256": digest(artifacts / "environment.json"),
        "environment_artifact_id": strict_artifact_id(strict_paths["environment"]),
        "artifact_refs": references,
        "semantic_ir": {
            "status": "PASSED",
            "source_ir_artifact_id": source_id,
            "source_ir_sha256": digest(source_ir),
            "target_ir_artifact_id": target_id,
            "target_relift_ir_sha256": digest(target_ir),
            "unknown_or_dropped_nodes": 0,
            "differences": [],
        },
        "semantic_chunks": {
            "status": "PASSED",
            "total": 1,
            "matched": 1,
            "unmatched": 0,
            "ambiguous": 0,
            "coverage": 1.0,
            "evidence_artifact_ids": [strict_artifact_id(strict_paths["chunk"])],
            "chunks": [
                {
                    "chunk_id": f"strict-artifacts:{source_chunk_id}",
                    "source_ref": f"{chunk_source_id}#/functions/0",
                    "target_ref": f"{chunk_target_id}#/functions/0",
                    "semantic_hash": semantic_hash,
                    "status": "MATCHED",
                }
            ],
        },
        "behavior_equivalence": {
            "status": "PASSED",
            "total_cases": 3,
            "passed_cases": 3,
            "counterexamples": [],
            "evidence_artifact_ids": [strict_artifact_id(strict_paths["behavior"])],
            "source_runtime_artifact_ids": [
                strict_artifact_id(strict_paths["behavior"])
            ],
            "target_runtime_artifact_ids": [
                strict_artifact_id(strict_paths["behavior"])
            ],
            "canonical_oracle_passed": True,
            "source_runtime_passed": True,
            "target_runtime_passed": True,
        },
        "formal_proof": {
            "status": proof_status,
            "solver": solver_identity["name"],
            "solver_version": solver_identity["version"],
            "solver_options": {
                "timeout_ms": solver_identity["timeout_ms"],
                "random_seed": solver_identity["random_seed"],
            },
            "input_artifact_id": strict_artifact_id(strict_paths["proof_bundle"]),
            "input_digest": digest(artifacts / "proof-input-bundle.json"),
            "result_artifact_ids": [result_id],
            "assumptions": assumptions,
            "obligations": [
                {
                    "obligation_id": "route-composition",
                    "status": proof_status,
                    "scope": "typed-pure-function-v1",
                    "formal_input_artifact_id": strict_artifact_id(
                        strict_paths["formal_input"]
                    ),
                    "solver_input_artifact_id": strict_artifact_id(
                        strict_paths["solver_input"]
                    ),
                    "input_digest": digest(proof_input),
                    "solver_result_artifact_id": result_id,
                    "assumptions": assumptions,
                }
            ],
            "replay": {
                "command": [
                    "python3",
                    "tools/replay-proof.py",
                    "--route",
                    ".",
                ],
                "cwd": ".",
                "expected_result_artifact_id": result_id,
                "expected_result_sha256": digest(artifacts / "proof-result.json"),
                "expected_exit_code": 0,
            },
        },
    }
    formal_path = route / "certification" / "formal-equivalence.json"
    formal_path.write_text(json.dumps(formal, indent=2) + "\n")
    certification_path = route / "certification" / "certification.json"
    certification = json.loads(certification_path.read_text())
    certification["evidence_format"] = 2
    certification["formal_equivalence"] = artifact_ref(
        route, "certification/formal-equivalence.json"
    )
    certification_path.write_text(json.dumps(certification, indent=2) + "\n")
    return formal_path, certification_path


def refresh_formal_reference(
    route: Path, formal_path: Path, certification_path: Path
) -> None:
    certification = json.loads(certification_path.read_text())
    certification["formal_equivalence"] = artifact_ref(
        route, str(formal_path.relative_to(route))
    )
    certification_path.write_text(json.dumps(certification, indent=2) + "\n")


def portable_swift_analyzer_receipt(validator: object) -> dict[str, object]:
    """Build a valid receipt fixture from the currently pinned local inputs."""

    engine_source = ROOT / "engines" / "polyglot-route-engine" / "src"
    engine_source_value = str(engine_source)
    if engine_source_value not in sys.path:
        sys.path.insert(0, engine_source_value)
    package = ROOT / "engines" / "polyglot-route-engine" / "native" / "swift"
    sources = [
        package / "Package.swift",
        package / "Package.resolved",
        *sorted(
            (package / "Sources").rglob("*.swift"),
            key=lambda path: path.relative_to(package).as_posix(),
        ),
    ]
    files = [
        {
            "path": path.relative_to(package).as_posix(),
            "sha256": digest(path),
            "bytes": path.stat().st_size,
        }
        for path in sources
    ]
    tree = {
        "identity": validator.SWIFT_DEPENDENCY_IDENTITY,
        "version": validator.SWIFT_DEPENDENCY_VERSION,
        "revision": validator.SWIFT_DEPENDENCY_REVISION,
        "sha256": validator.SWIFT_DEPENDENCY_SHA256,
        "file_count": validator.SWIFT_DEPENDENCY_FILE_COUNT,
        "bytes": validator.SWIFT_DEPENDENCY_BYTES,
    }
    cache = {
        "cache_key": validator.SWIFT_DEPENDENCY_CACHE_KEY,
        "cache_schema": validator.SWIFT_DEPENDENCY_CACHE_SCHEMA,
        "object_store_policy": validator.SWIFT_DEPENDENCY_OBJECT_STORE_POLICY,
        "seed": validator.SWIFT_DEPENDENCY_SEED,
        **tree,
    }
    mirror = {
        "seed": validator.SWIFT_DEPENDENCY_SEED,
        "cache": cache,
        "git": {
            "path": validator.SWIFT_GIT_PATH,
            "sha256": validator.SWIFT_GIT_SHA256,
            "version": validator.SWIFT_GIT_VERSION,
        },
        **tree,
    }
    binary_root = Path("/private/tmp/elmos-swift-analyzer-fixture")
    binary = {
        "name": "ElmosSwiftAnalyzer",
        "path": str(binary_root / "ElmosSwiftAnalyzer"),
        "sha256": "sha256:" + "0" * 64,
        "bytes": 1,
        "mode": "0500",
        "uid": os.getuid(),
        "gid": os.getgid(),
        "nlink": 1,
        "device": 1,
        "inode": 2,
    }
    probe_root = binary_root / "network-probe-execution"
    probe_binary = {
        "name": validator.SWIFT_NETWORK_PROBE_BINARY_NAME,
        "path": str(probe_root / validator.SWIFT_NETWORK_PROBE_BINARY_NAME),
        "sha256": validator.SWIFT_NETWORK_PROBE_BINARY_SHA256,
        "bytes": validator.SWIFT_NETWORK_PROBE_BINARY_BYTES,
        "mode": "0500",
        "uid": os.getuid(),
        "gid": os.getgid(),
        "nlink": 1,
        "device": 1,
        "inode": 4,
    }
    receipt: dict[str, object] = {
        "schema_version": "1.0.0",
        "kind": "elmos.swift-analyzer-build-receipt",
        "source_inputs": {
            "sha256": validator._receipt_payload_sha256({"files": files}),
            "files": files,
        },
        "dependency": {**tree, "mirror": mirror},
        "toolchain": copy.deepcopy(validator.SWIFT_ANALYZER_TOOLCHAIN),
        "network_isolation": {
            "status": "PASSED",
            "scope": "swift-build-process-tree",
            "sandbox": copy.deepcopy(validator.SWIFT_NETWORK_SANDBOX),
            "verifier": copy.deepcopy(validator.SWIFT_NETWORK_VERIFIER),
            "policy": {
                "text": validator.SWIFT_NETWORK_POLICY_TEXT,
                "sha256": validator.SWIFT_NETWORK_POLICY_SHA256,
                "bytes": len(validator.SWIFT_NETWORK_POLICY_TEXT.encode("utf-8")),
            },
            "probe": {
                "result": "NETWORK_DENIED:1",
                "source": {
                    "text": validator.SWIFT_NETWORK_PROBE_SOURCE,
                    "sha256": validator.SWIFT_NETWORK_PROBE_SOURCE_SHA256,
                    "bytes": validator.SWIFT_NETWORK_PROBE_SOURCE_BYTES,
                },
                "build": {
                    "environment_policy": "sanitized-swift-build-deterministic-v1",
                    "argv": copy.deepcopy(validator.SWIFT_NETWORK_PROBE_BUILD_ARGV),
                    "environment": copy.deepcopy(
                        validator.SWIFT_NETWORK_PROBE_BUILD_ENVIRONMENT
                    ),
                    "compiler": copy.deepcopy(validator.SWIFT_NETWORK_PROBE_COMPILER),
                },
                "binary": probe_binary,
                "execution_seal": {
                    "policy": "private-nonwritable-execution-root-v1",
                    "root": str(probe_root),
                    "mode": "0500",
                    "uid": os.getuid(),
                    "gid": os.getgid(),
                    "device": 1,
                    "inode": 3,
                    "binary": copy.deepcopy(probe_binary),
                },
                "mach_o": {
                    "architecture": "arm64",
                    "file_type": "MH_EXECUTE",
                    "uuid": validator.SWIFT_NETWORK_PROBE_UUID,
                    "cdhash_full": validator.SWIFT_NETWORK_PROBE_CDHASH_FULL,
                    "linked_libraries": copy.deepcopy(
                        validator.SWIFT_NETWORK_PROBE_LINKED_LIBRARIES
                    ),
                },
            },
        },
        "build": copy.deepcopy(validator.SWIFT_ANALYZER_BUILD),
        "binary": binary,
        "execution_seal": {
            "policy": "private-nonwritable-execution-root-v1",
            "root": str(binary_root),
            "mode": "0500",
            "uid": os.getuid(),
            "gid": os.getgid(),
            "device": 1,
            "inode": 1,
            "binary": copy.deepcopy(binary),
        },
    }
    canonical = validator._rebuild_portable_swift_receipt_identity(receipt)
    receipt["canonical_identity"] = {
        "sha256": validator._receipt_payload_sha256(canonical),
        "receipt": canonical,
    }
    return receipt


class ToolkitTests(unittest.TestCase):
    def test_swift_build_closure_component_limit_covers_hosted_clang_and_fails_closed(self):
        validator = load_route_validator()
        maximum = validator.SWIFT_BUILD_CLOSURE_COMPONENT_MAXIMUM_BYTES
        self.assertEqual(maximum, 400_000_000)
        self.assertLessEqual(290_664_032, maximum)
        self.assertIn(
            "SWIFT_BUILD_CLOSURE_COMPONENT_MAXIMUM_BYTES",
            validator._stable_read_swift_closure_file.__code__.co_names,
        )

        with tempfile.TemporaryDirectory() as td:
            oversized = Path(td) / "oversized-clang"
            with oversized.open("wb") as stream:
                stream.truncate(maximum + 1)
            with self.assertRaisesRegex(
                ValueError,
                "Swift closure component exceeds maximum size",
            ):
                validator._stable_read_swift_closure_file(oversized)

            race_candidate = Path(td) / "lstat-open-race"
            race_candidate.touch()
            original_open = os.open
            nonblocking = getattr(os, "O_NONBLOCK", 0)
            self.assertNotEqual(nonblocking, 0)
            observed_flags: list[int] = []

            def replace_with_fifo(path: object, flags: int) -> int:
                observed_flags.append(flags)
                if not flags & nonblocking:
                    raise AssertionError("Swift closure open omitted O_NONBLOCK")
                self.assertEqual(Path(os.fspath(path)), race_candidate)
                race_candidate.unlink()
                os.mkfifo(race_candidate, 0o600)
                return original_open(path, flags)

            with (
                mock.patch.object(
                    validator.os,
                    "open",
                    side_effect=replace_with_fifo,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "Swift closure component exceeds maximum size",
                ),
            ):
                validator._stable_read_swift_closure_file(race_candidate)
            self.assertEqual(len(observed_flags), 1)
            self.assertTrue(observed_flags[0] & nonblocking)

    def test_swift_build_closure_tree_aggregate_limit_fails_closed(self):
        validator = load_route_validator()
        maximum = validator.SWIFT_BUILD_CLOSURE_TREE_MAXIMUM_BYTES
        self.assertEqual(maximum, 1_000_000_000)
        first = validator._checked_swift_tree_byte_total(
            0,
            maximum // 2,
            role="fixture",
        )
        self.assertEqual(
            validator._checked_swift_tree_byte_total(
                first,
                maximum - first,
                role="fixture",
            ),
            maximum,
        )
        with self.assertRaisesRegex(ValueError, "aggregate byte bound"):
            validator._checked_swift_tree_byte_total(
                maximum,
                1,
                role="fixture",
            )

    def test_swift_tree_regular_file_boundary_allows_zero_and_rejects_over_400m(self):
        validator = load_route_validator()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            empty = root / "empty"
            empty.touch()
            local_metadata = empty.lstat()
            hosted_metadata = os.stat_result(
                (
                    stat.S_IFREG | 0o444,
                    local_metadata.st_ino,
                    local_metadata.st_dev,
                    1,
                    0,
                    0,
                    0,
                    local_metadata.st_atime,
                    local_metadata.st_mtime,
                    local_metadata.st_ctime,
                )
            )
            root_owned_empty = mock.MagicMock(spec=Path)
            root_owned_empty.__fspath__.return_value = str(empty)
            root_owned_empty.lstat.return_value = hosted_metadata
            with mock.patch.object(
                validator.os,
                "fstat",
                return_value=hosted_metadata,
            ):
                content, metadata = validator._stable_read_swift_closure_file(
                    root_owned_empty
                )
            self.assertEqual(content, b"")
            self.assertEqual(metadata.st_size, 0)

            oversized = root / "oversized-tree-file"
            with oversized.open("wb") as stream:
                stream.truncate(
                    validator.SWIFT_BUILD_CLOSURE_COMPONENT_MAXIMUM_BYTES + 1
                )
            with self.assertRaisesRegex(
                ValueError,
                "Swift closure component exceeds maximum size",
            ):
                validator._stable_read_swift_closure_file(oversized)

    def test_swift_xcode_directory_chain_has_no_writable_applications_exception(self):
        validator = load_route_validator()
        names = validator._swift_closure_directory_chain.__code__.co_names
        constants = validator._swift_closure_directory_chain.__code__.co_consts
        self.assertNotIn("applications_exception", names)
        self.assertNotIn(0o775, constants)
        self.assertNotIn(80, constants)

    def test_skill_bundle(self):
        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "validate_skill_bundle.py"),
                str(ROOT / ".agents/skills"),
            ],
            check=True,
        )

    def test_scaffold_and_validate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "templates").mkdir()
            # point scaffolder at bundle templates through its fallback
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "scaffold_route.py"),
                    "--source",
                    "java",
                    "--target",
                    "csharp",
                    "--repo-root",
                    str(root),
                ],
                check=True,
            )
            route = root / "routes" / "java-to-csharp"
            data = json.loads((route / "route.json").read_text())
            data["owner"] = "test-owner"
            data["source"]["versions"] = ["21"]
            data["target"]["versions"] = ["13"]
            (route / "route.json").write_text(json.dumps(data, indent=2) + "\n")
            subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                check=True,
            )

    def test_route_scoring(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            inp = td / "in.json"
            out = td / "out.json"
            inp.write_text(
                json.dumps(
                    {
                        "weights": {"customer_demand": 1.0},
                        "candidates": [
                            {
                                "route_key": "java-to-csharp",
                                "customer_demand": 4,
                                "evidence_notes": ["customer"],
                            }
                        ],
                    }
                )
            )
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "score_routes.py"),
                    str(inp),
                    "--output",
                    str(out),
                ],
                check=True,
            )
            self.assertEqual(
                json.loads(out.read_text())["results"][0]["decision"], "approve"
            )

    def test_limited_route_gate_is_evidence_bound(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            install_strict_evidence(route)
            passed = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_route_gate.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            self.assertIn("status=limited decision=NOT_CERTIFIED", passed.stdout)
            self.assertRegex(passed.stdout, r"wall_seconds=\d+\.\d{3}")
            self.assertEqual(
                passed.stderr.count("Creating virtual environment at:"),
                1,
                passed.stdout + passed.stderr,
            )

            evidence_path = route / "certification" / "evidence.json"
            evidence = json.loads(evidence_path.read_text())
            evidence["execution_status"] = "NOT_RUN"
            evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
            blocked = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_route_gate.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("local execution evidence did not pass", blocked.stderr)

    def test_route_validator_rejects_manual_status_edit(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            manifest_path = route / "route.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["status"] = "certified"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertIn(
                "route and certification statuses must match", rejected.stderr
            )

    def test_strict_formal_equivalence_route_passes_only_with_bound_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            temporary_root = Path(td).resolve(strict=True)
            temporary_root.relative_to(Path(tempfile.gettempdir()).resolve(strict=True))
            route = copy_fixture_tree_to_private_writable_root(
                ROOT / "routes" / "python-to-typescript",
                temporary_root / "python-to-typescript",
                temporary_root=temporary_root,
            )
            install_strict_evidence(route)
            passed = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_route_gate.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            self.assertIn("status=limited decision=NOT_CERTIFIED", passed.stdout)

    def test_private_writable_fixture_copy_rejects_temp_escape(self):
        with (
            tempfile.TemporaryDirectory() as td,
            tempfile.TemporaryDirectory() as outside,
        ):
            temporary_root = Path(td).resolve(strict=True)
            escaped_destination = Path(outside).resolve(strict=True) / "route"
            with self.assertRaisesRegex(
                ValueError,
                "fixture destination escapes private temporary root",
            ):
                copy_fixture_tree_to_private_writable_root(
                    ROOT / "routes" / "python-to-typescript",
                    escaped_destination,
                    temporary_root=temporary_root,
                )

    def test_assumption_bound_proof_stays_limited_and_not_certified(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            install_strict_evidence(route, "PROVED_UNDER_ASSUMPTIONS")
            passed = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_route_gate.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            self.assertIn("decision=NOT_CERTIFIED", passed.stdout)

    def test_unresolved_or_axiom_formal_statuses_never_pass(self):
        non_passing = ("AXIOM", "BOUNDED", "UNKNOWN", "TIMEOUT", "NOT_RUN")
        for proof_status in non_passing:
            with (
                self.subTest(proof_status=proof_status),
                tempfile.TemporaryDirectory() as td,
            ):
                route = Path(td) / "python-to-typescript"
                shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
                install_strict_evidence(route, proof_status)
                blocked = subprocess.run(
                    [sys.executable, str(SCRIPTS / "run_route_gate.py"), str(route)],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(blocked.returncode, 2, blocked.stdout + blocked.stderr)
                self.assertIn(
                    f"formal proof status is non-passing: {proof_status}",
                    blocked.stderr,
                )

    def test_formal_counterexample_is_a_hard_failure(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            install_strict_evidence(route, "COUNTEREXAMPLE")
            blocked = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_route_gate.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(blocked.returncode, 2, blocked.stdout + blocked.stderr)
            self.assertIn("formal proof produced a counterexample", blocked.stderr)

    def test_strict_artifact_digest_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            install_strict_evidence(route)
            artifact = route / "certification" / "strict-artifacts" / "proof-input.smt2"
            artifact.write_text("(assert false)\n(check-sat)\n")
            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("digest mismatch", rejected.stderr)

    def test_strict_artifact_path_escape_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            formal_path, certification_path = install_strict_evidence(route)
            formal = json.loads(formal_path.read_text())
            formal["artifact_refs"][0]["path"] = "../outside.json"
            formal_path.write_text(json.dumps(formal, indent=2) + "\n")
            refresh_formal_reference(route, formal_path, certification_path)
            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("escapes the route directory", rejected.stderr)

    def test_strict_missing_layer_and_forged_chunk_counts_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            formal_path, certification_path = install_strict_evidence(route)
            formal = json.loads(formal_path.read_text())
            formal["semantic_chunks"]["total"] = 2
            formal_path.write_text(json.dumps(formal, indent=2) + "\n")
            refresh_formal_reference(route, formal_path, certification_path)
            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertIn(
                "semantic_chunks.total does not equal chunks length", rejected.stderr
            )

            formal = json.loads(formal_path.read_text())
            del formal["semantic_chunks"]
            formal_path.write_text(json.dumps(formal, indent=2) + "\n")
            refresh_formal_reference(route, formal_path, certification_path)
            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("missing keys: semantic_chunks", rejected.stderr)

    def test_strict_artifact_role_substitution_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            formal_path, certification_path = install_strict_evidence(route)
            formal = json.loads(formal_path.read_text())
            formal["semantic_ir"]["source_ir_artifact_id"] = formal[
                "behavior_equivalence"
            ]["evidence_artifact_ids"][0]
            formal_path.write_text(json.dumps(formal, indent=2) + "\n")
            refresh_formal_reference(route, formal_path, certification_path)
            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("expected one of ['source-ir']", rejected.stderr)

    def test_strict_chunk_pointer_and_subtree_hash_are_verified(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            formal_path, certification_path = install_strict_evidence(route)
            formal = json.loads(formal_path.read_text())
            formal["semantic_chunks"]["chunks"][0]["source_ref"] = (
                formal["semantic_ir"]["source_ir_artifact_id"] + "#/functions/99"
            )
            formal_path.write_text(json.dumps(formal, indent=2) + "\n")
            refresh_formal_reference(route, formal_path, certification_path)
            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("cannot resolve JSON pointer", rejected.stderr)

    def test_strict_behavior_claim_is_derived_from_bound_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            formal_path, certification_path = install_strict_evidence(route)
            behavior_path = (
                route / "certification" / "strict-artifacts" / "behavior.json"
            )
            behavior = json.loads(behavior_path.read_text())
            behavior["source_runtime_passed"] = False
            behavior_path.write_text(json.dumps(behavior, sort_keys=True) + "\n")
            formal = json.loads(formal_path.read_text())
            behavior_id = formal["behavior_equivalence"]["evidence_artifact_ids"][0]
            reference = next(
                item
                for item in formal["artifact_refs"]
                if item["artifact_id"] == behavior_id
            )
            reference["sha256"] = digest(behavior_path)
            reference["bytes"] = behavior_path.stat().st_size
            formal_path.write_text(json.dumps(formal, indent=2) + "\n")
            refresh_formal_reference(route, formal_path, certification_path)
            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertIn(
                "source_runtime_passed does not match behavior artifacts",
                rejected.stderr,
            )

    def test_strict_solver_result_must_bind_formal_and_smt_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            formal_path, certification_path = install_strict_evidence(route)
            result_path = (
                route / "certification" / "strict-artifacts" / "proof-result.json"
            )
            result = json.loads(result_path.read_text())
            result["formal_input_digest"] = "sha256:" + "0" * 64
            result_path.write_text(json.dumps(result, sort_keys=True) + "\n")
            formal = json.loads(formal_path.read_text())
            result_id = formal["formal_proof"]["result_artifact_ids"][0]
            reference = next(
                item
                for item in formal["artifact_refs"]
                if item["artifact_id"] == result_id
            )
            reference["sha256"] = digest(result_path)
            reference["bytes"] = result_path.stat().st_size
            formal["formal_proof"]["replay"]["expected_result_sha256"] = digest(
                result_path
            )
            formal_path.write_text(json.dumps(formal, indent=2) + "\n")
            refresh_formal_reference(route, formal_path, certification_path)
            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("solver result does not bind formal input", rejected.stderr)

    def test_strict_replay_rejects_a_dangling_script(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            formal_path, certification_path = install_strict_evidence(route)
            formal = json.loads(formal_path.read_text())
            formal["formal_proof"]["replay"]["command"][1] = "tools/missing.py"
            formal_path.write_text(json.dumps(formal, indent=2) + "\n")
            refresh_formal_reference(route, formal_path, certification_path)

            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(rejected.returncode, 1)
            self.assertIn("replay.command script does not exist", rejected.stderr)

    def test_strict_replay_rejects_an_unbound_existing_script(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            formal_path, certification_path = install_strict_evidence(route)
            unbound = route / "tools" / "unbound.py"
            unbound.write_text("raise SystemExit(0)\n")
            formal = json.loads(formal_path.read_text())
            formal["formal_proof"]["replay"]["command"][1] = "tools/unbound.py"
            formal_path.write_text(json.dumps(formal, indent=2) + "\n")
            refresh_formal_reference(route, formal_path, certification_path)

            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(rejected.returncode, 1)
            self.assertIn(
                "script must have exactly one matching engine-source or replay-tool artifact",
                rejected.stderr,
            )

    def test_strict_replay_rejects_the_wrong_route_binding(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            formal_path, certification_path = install_strict_evidence(route)
            formal = json.loads(formal_path.read_text())
            formal["formal_proof"]["replay"]["command"][-1] = "java-to-csharp"
            formal_path.write_text(json.dumps(formal, indent=2) + "\n")
            refresh_formal_reference(route, formal_path, certification_path)

            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(rejected.returncode, 1)
            self.assertIn("--route must bind the exact route_key", rejected.stderr)

    def test_uv_project_replay_is_route_local_and_artifact_bound(self):
        validator = load_route_validator()
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "cpp-to-java"
            project = route / "captured-engine"
            project.mkdir(parents=True)
            pyproject = project / "pyproject.toml"
            pyproject.write_text(
                "[project]\nname='fixture'\nversion='1.0.0'\n",
                encoding="utf-8",
            )
            lockfile = project / "uv.lock"
            lockfile.write_text("version = 1\n", encoding="utf-8")
            script = route / "certification" / "replay" / "validate.py"
            script.parent.mkdir(parents=True)
            script.write_text("raise SystemExit(0)\n", encoding="utf-8")
            failures: list[str] = []
            validator._validate_replay_command(
                route=route,
                manifest={"route_key": "cpp-to-java"},
                command=[
                    "uv",
                    "--project",
                    "captured-engine",
                    "run",
                    "--locked",
                    "python",
                    "certification/replay/validate.py",
                    "--route",
                    ".",
                ],
                cwd=route,
                records={
                    "pyproject": (
                        {
                            "role": "engine-source",
                            "path": "captured-engine/pyproject.toml",
                        },
                        pyproject,
                        digest(pyproject),
                    ),
                    "lockfile": (
                        {
                            "role": "engine-source",
                            "path": "captured-engine/uv.lock",
                        },
                        lockfile,
                        digest(lockfile),
                    ),
                    "replay-tool": (
                        {
                            "role": "replay-tool",
                            "path": "certification/replay/validate.py",
                        },
                        script,
                        digest(script),
                    ),
                },
                failures=failures,
            )
            self.assertEqual(failures, [])

    def test_uv_project_replay_rejects_project_path_escape(self):
        validator = load_route_validator()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            route = root / "cpp-to-java"
            route.mkdir()
            outside = root / "outside-engine"
            outside.mkdir()
            script = route / "validate.py"
            script.write_text("raise SystemExit(0)\n", encoding="utf-8")
            failures: list[str] = []
            validator._validate_replay_command(
                route=route,
                manifest={"route_key": "cpp-to-java"},
                command=[
                    "uv",
                    "--project",
                    "../outside-engine",
                    "run",
                    "--locked",
                    "python",
                    "validate.py",
                    "--route",
                    ".",
                ],
                cwd=route,
                records={
                    "replay-tool": (
                        {"role": "replay-tool", "path": "validate.py"},
                        script,
                        digest(script),
                    )
                },
                failures=failures,
            )
            self.assertTrue(
                any("uv project escapes" in failure for failure in failures),
                failures,
            )

    def test_strict_engine_source_manifest_rejects_live_repository_drift(self):
        with tempfile.TemporaryDirectory() as td:
            repository = Path(td)
            route = repository / "routes" / "python-to-typescript"
            route.parent.mkdir(parents=True)
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            install_strict_evidence(route)
            source_manifest_path = (
                route
                / "certification"
                / "formal-artifacts"
                / "engine-source-manifest.json"
            )
            source_manifest = json.loads(source_manifest_path.read_text())
            for item in source_manifest["files"]:
                captured = route / item["captured_path"]
                live = repository / item["repository_path"]
                live.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(captured, live)
            (repository / "scripts" / "batch29").mkdir(parents=True, exist_ok=True)
            (repository / "schemas" / "batch29").mkdir(parents=True, exist_ok=True)

            accepted = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)

            live_engine = (
                repository
                / "engines"
                / "polyglot-route-engine"
                / "src"
                / "elmos_polyglot_route"
                / "engine.py"
            )
            live_engine.write_text("# drifted engine fixture\n")
            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(rejected.returncode, 1)
            self.assertIn("engine source manifest live file drifted", rejected.stderr)

    def test_proof_runtime_rejects_pythonpath_shadow_package_in_fresh_process(self):
        with tempfile.TemporaryDirectory() as td:
            shadow = Path(td)
            package = shadow / "elmos_polyglot_route"
            package.mkdir()
            (package / "__init__.py").write_text("# hostile shadow package\n")
            for module in (
                "equivalence",
                "models",
                "engine",
                "emitter",
                "types",
                "canonical",
            ):
                (package / f"{module}.py").write_text(f"# hostile shadow {module}\n")
            program = f"""
import importlib.util
spec = importlib.util.spec_from_file_location('validator_under_attack', {str(SCRIPTS / "validate_route.py")!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
failures = []
assert module._engine_proof_api(failures, 'shadow regression') is None
print('\\n'.join(failures))
"""
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(shadow)
            attacked = subprocess.run(
                [sys.executable, "-c", program],
                text=True,
                capture_output=True,
                check=False,
                cwd=ROOT,
                env=environment,
            )
            self.assertEqual(attacked.returncode, 0, attacked.stdout + attacked.stderr)
            self.assertIn("engine module origin rejected", attacked.stdout)
            self.assertIn(str(shadow), attacked.stdout)

    def test_proof_runtime_rejects_path_shadow_z3_cli(self):
        with tempfile.TemporaryDirectory() as td:
            shadow = Path(td)
            fake_z3 = shadow / "z3"
            fake_z3.write_text("#!/bin/sh\necho 'Z3 version 4.16.0 - 64 bit'\n")
            fake_z3.chmod(0o755)
            program = f"""
import importlib.util
spec = importlib.util.spec_from_file_location('validator_under_attack', {str(SCRIPTS / "validate_route.py")!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
failures = []
assert module._runtime_provenance(failures, 'cli shadow regression') is None
print('\\n'.join(failures))
"""
            environment = os.environ.copy()
            environment["PATH"] = str(shadow) + os.pathsep + environment["PATH"]
            attacked = subprocess.run(
                [sys.executable, "-c", program],
                text=True,
                capture_output=True,
                check=False,
                cwd=ROOT,
                env=environment,
            )
            self.assertEqual(attacked.returncode, 0, attacked.stdout + attacked.stderr)
            self.assertIn("z3 CLI origin rejected", attacked.stdout)
            self.assertIn(str(fake_z3), attacked.stdout)

    def test_authoritative_route_runtime_ignores_existing_project_venv(self):
        runtime = load_fresh_route_runtime()
        with tempfile.TemporaryDirectory() as td:
            repository = Path(td) / "repository"
            script = repository / "scripts" / "batch29" / "entry.py"
            project = repository / "engines" / "polyglot-route-engine"
            script.parent.mkdir(parents=True)
            project.mkdir(parents=True)
            script.write_text("# fixture entry\n")
            (project / "pyproject.toml").write_text(
                "[project]\nname='fixture'\nversion='1'\n"
            )
            (project / "uv.lock").write_text("version = 1\n")
            hostile_z3 = project / ".venv" / "bin" / "z3"
            hostile_z3.parent.mkdir(parents=True)
            hostile_z3.write_text("hostile pre-existing solver\n")
            observed: dict[str, object] = {}

            def fake_run(command, **kwargs):
                environment = kwargs["env"]
                fresh_environment = Path(environment["UV_PROJECT_ENVIRONMENT"])
                observed.update(
                    {
                        "command": command,
                        "fresh_environment": fresh_environment,
                    }
                )
                self.assertNotEqual(fresh_environment, project / ".venv")
                self.assertTrue(fresh_environment.parent.is_dir())
                self.assertEqual(environment["UV_NO_CONFIG"], "1")
                for hostile_key in (
                    "PYTHONPATH",
                    "JAVA_TOOL_OPTIONS",
                    "CPATH",
                    "SDKROOT",
                    "SWIFT_EXEC",
                    "DYLD_INSERT_LIBRARIES",
                    "UV_PYTHON",
                    "UV_NO_SYNC",
                ):
                    self.assertNotIn(hostile_key, environment)
                self.assertIn("-c", command)
                self.assertIn(runtime.CHILD_PROGRAM, command)
                self.assertEqual(Path(command[-2]), script.resolve())
                self.assertEqual(command[-1], "--fixture")
                return subprocess.CompletedProcess(command, 0)

            hostile_environment = {
                "PYTHONPATH": "/tmp/shadow-python",
                "JAVA_TOOL_OPTIONS": "-javaagent:/tmp/shadow.jar",
                "CPATH": "/tmp/shadow-headers",
                "SDKROOT": "/tmp/shadow-sdk",
                "SWIFT_EXEC": "/tmp/shadow-swift",
                "DYLD_INSERT_LIBRARIES": "/tmp/shadow.dylib",
                "UV_PYTHON": "/tmp/shadow-python",
                "UV_NO_SYNC": "1",
            }
            with (
                mock.patch.dict(os.environ, hostile_environment, clear=False),
                mock.patch.object(
                    runtime, "_pinned_uv", return_value=Path("/trusted/pinned/uv")
                ),
                mock.patch.object(runtime.subprocess, "run", side_effect=fake_run),
            ):
                self.assertEqual(
                    runtime.run_in_fresh_locked_runtime(script, ["--fixture"]), 0
                )
            self.assertIn("fresh_environment", observed)
            self.assertEqual(hostile_z3.read_text(), "hostile pre-existing solver\n")

    def test_private_replay_snapshot_detects_origin_replacement(self):
        validator = load_route_validator()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            origin = root / "source.cpp"
            original = b"int64_t value(int64_t x) { return x; }\n"
            origin.write_bytes(original)
            snapshot_root = root / "private"
            snapshot_root.mkdir(mode=0o700)
            snapshot = validator._private_snapshot(
                snapshot_root,
                role="source",
                logical_name=origin.name,
                content=original,
            )
            origin.write_bytes(b"int64_t value(int64_t x) { return x - 1; }\n")
            failures: list[str] = []
            validator._validate_snapshot_stability(
                label="fixture",
                origin=origin,
                snapshot=snapshot,
                expected_bytes=original,
                expected_digest=validator.sha256_bytes(original),
                failures=failures,
            )
            self.assertEqual(snapshot.read_bytes(), original)
            self.assertIn("fixture bound origin changed during replay", failures)

    def test_fresh_route_subprocess_reaches_origin_bound_proof_api(self):
        environment = os.environ.copy()
        environment["UV_PROJECT_ENVIRONMENT"] = str(
            ROOT / "engines" / "polyglot-route-engine" / ".venv"
        )
        environment["ELMOS_BATCH29_FRESH_RUNTIME_RECEIPT"] = (
            "/tmp/forged-batch29-runtime-receipt"
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "validate_route.py"),
                "--runtime-proof-probe",
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, output)
        self.assertIn("OK: Batch29 fresh locked proof runtime", output)
        self.assertIn("elmos-batch29-fresh-route-runtime-", output)
        self.assertNotIn(
            str(ROOT / "engines" / "polyglot-route-engine" / ".venv"),
            output,
        )

    def test_fresh_route_subprocess_ignores_path_shadow_uv(self):
        with tempfile.TemporaryDirectory() as td:
            shadow = Path(td)
            fake_uv = shadow / "uv"
            fake_uv.write_text("#!/bin/sh\necho hostile-uv\n")
            fake_uv.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = str(shadow) + os.pathsep + environment["PATH"]
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_route.py"),
                    "--runtime-proof-probe",
                ],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
            output = completed.stdout + completed.stderr
            self.assertEqual(completed.returncode, 0, output)
            self.assertIn("OK: Batch29 fresh locked proof runtime", output)
            self.assertNotIn("hostile-uv", output)

    def test_specialized_module_rejects_self_consistent_false_smt(self):
        validator = load_route_validator()
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "cpp-to-java"
            shutil.copytree(ROOT / "routes" / "cpp-to-java", route)
            report_path = route / "certification" / "module-equivalence.json"
            report = json.loads(report_path.read_text())
            formal = report["functions"][0]["layers"]["formal"]
            smt_relative = formal["solver_input_path"]
            smt_path = route / smt_relative
            headers = [
                line
                for line in smt_path.read_text().splitlines()
                if line.startswith(";")
            ]
            smt_path.write_text(
                "\n".join(
                    headers
                    + ["(set-info :status unknown)", "(assert false)", "(check-sat)"]
                )
                + "\n"
            )
            refresh_module_artifact(route, report, smt_relative)
            solver_digest = digest(smt_path)
            result_relative = formal["formal_result_path"]
            result_path = route / result_relative
            result = json.loads(result_path.read_text())
            result["solver_input_digest"] = solver_digest
            result["solver_input"]["sha256"] = solver_digest
            write_json(result_path, result)
            refresh_module_artifact(route, report, result_relative)
            formal.update(result)
            formal["solver_input_sha256"] = solver_digest
            formal["formal_result_sha256"] = digest(result_path)
            refresh_module_report_reference(route, report)

            certification = json.loads(
                (route / "certification" / "certification.json").read_text()
            )
            _, failures = validator.validate_module_equivalence(
                route,
                json.loads((route / "route.json").read_text()),
                certification,
            )
            self.assertTrue(
                any("SMT assertion" in failure for failure in failures), failures
            )

    def test_specialized_module_rejects_formal_input_detached_from_module_ir(self):
        validator = load_route_validator()
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "cpp-to-java"
            shutil.copytree(ROOT / "routes" / "cpp-to-java", route)
            report = json.loads(
                (route / "certification" / "module-equivalence.json").read_text()
            )
            formal = report["functions"][0]["layers"]["formal"]
            input_relative = formal["formal_input_path"]
            input_path = route / input_relative
            formal_input = json.loads(input_path.read_text())
            old_input_digest = digest(input_path)
            formal_input["source_function"]["name"] = "detached_both"
            formal_input["source_function_sha256"] = validator.canonical_json_sha256(
                formal_input["source_function"]
            )
            write_json(input_path, formal_input)
            refresh_module_artifact(route, report, input_relative)
            new_input_digest = digest(input_path)

            smt_relative = formal["solver_input_path"]
            smt_path = route / smt_relative
            smt_path.write_text(
                smt_path.read_text().replace(old_input_digest, new_input_digest)
            )
            refresh_module_artifact(route, report, smt_relative)
            solver_digest = digest(smt_path)

            result_relative = formal["formal_result_path"]
            result_path = route / result_relative
            result = json.loads(result_path.read_text())
            result["formal_input_digest"] = new_input_digest
            result["formal_input"]["sha256"] = new_input_digest
            result["solver_input_digest"] = solver_digest
            result["solver_input"]["sha256"] = solver_digest
            write_json(result_path, result)
            refresh_module_artifact(route, report, result_relative)
            formal.update(result)
            formal["formal_input_sha256"] = new_input_digest
            formal["solver_input_sha256"] = solver_digest
            formal["formal_result_sha256"] = digest(result_path)
            refresh_module_report_reference(route, report)

            certification = json.loads(
                (route / "certification" / "certification.json").read_text()
            )
            _, failures = validator.validate_module_equivalence(
                route,
                json.loads((route / "route.json").read_text()),
                certification,
            )
            self.assertIn(
                "module function both formal source function is detached from source module IR",
                failures,
            )

    def test_specialized_module_rejects_in_bounds_chunk_span_topology_tamper(self):
        validator = load_route_validator()
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "cpp-to-java"
            shutil.copytree(ROOT / "routes" / "cpp-to-java", route)
            report = json.loads(
                (route / "certification" / "module-equivalence.json").read_text()
            )
            chunk = report["functions"][0]["layers"]["chunk"]
            by_path = {
                mapping["semantic_path"]: mapping for mapping in chunk["mappings"]
            }
            left = by_path["/functions/0/body/0/expression/left"]["source_span"]
            right = by_path["/functions/0/body/0/expression/right"]["source_span"]
            left["end_byte"] = right["start_byte"] + 1
            refresh_module_report_reference(route, report)

            certification = json.loads(
                (route / "certification" / "certification.json").read_text()
            )
            _, failures = validator.validate_module_equivalence(
                route,
                json.loads((route / "route.json").read_text()),
                certification,
            )
            self.assertTrue(
                any(
                    "does not bind semantic IR" in failure
                    or "sibling spans overlap" in failure
                    for failure in failures
                ),
                failures,
            )

    def test_specialized_module_rejects_supported_body_ir_detached_from_source_bytes(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "cpp-to-java"
            shutil.copytree(ROOT / "routes" / "cpp-to-java", route)
            report = install_fresh_cpp_java_module_evidence(route)
            for side in ("source", "target"):
                role = f"{side}-module-semantic-ir"
                relative = next(
                    item["path"]
                    for item in report["artifact_refs"]
                    if item["role"] == role
                )
                path = route / relative
                document = json.loads(path.read_text())
                function = next(
                    item
                    for item in document["functions"]
                    if item["name"] == "calculate"
                )
                expression = next(
                    statement["expression"]
                    for statement in function["body"]
                    if isinstance(statement, dict)
                    and isinstance(statement.get("expression"), dict)
                    and statement["expression"].get("operator") == "+"
                )
                self.assertEqual(expression["operator"], "+")
                expression["operator"] = "-"
                write_json(path, document)
            refresh_module_semantic_bindings(route, report)
            refresh_module_report_reference(route, report)

            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                timeout=300,
            )
            output = completed.stdout + completed.stderr
            self.assertNotEqual(completed.returncode, 0, output)
            self.assertIn(
                "source-module-semantic-ir differs from independent source analysis",
                output,
            )
            self.assertIn(
                "target-module-semantic-ir differs from independent target re-lift",
                output,
            )

    def test_specialized_function_rejects_uncovered_branch_ir_detached_from_source_bytes(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            route = (Path(td) / "cpp-to-java").resolve()
            shutil.copytree(ROOT / "routes" / "cpp-to-java", route)
            corpus = "development"
            corpus_root = route / "corpus" / corpus
            corpus_manifest = json.loads((corpus_root / "manifest.json").read_text())
            source_path = corpus_root / corpus_manifest["source_file"]
            cases_path = corpus_root / corpus_manifest["cases_file"]
            function_name = corpus_manifest["function_name"]
            artifact_root = route / "certification" / "artifacts" / corpus
            source_document = json.loads(
                (artifact_root / "source-semantic-ir.json").read_text()
            )
            function = source_document["functions"][0]
            first_statement_start = function["body"][0]["source_span"]["start_byte"]
            gap_start = function["parameters"][-1]["source_span"]["end_byte"] + 1
            self.assertGreaterEqual(first_statement_start - gap_start, 6)
            logical_file = function["source_span"]["file"]
            function["body"].insert(
                0,
                {
                    "kind": "if",
                    "condition": {
                        "kind": "binary",
                        "operator": "==",
                        "left": {
                            "kind": "name",
                            "value": function["parameters"][0]["name"],
                            "source_span": {
                                "file": logical_file,
                                "start_byte": gap_start,
                                "end_byte": gap_start + 1,
                            },
                        },
                        "right": {
                            "kind": "literal",
                            "value": 42,
                            "source_span": {
                                "file": logical_file,
                                "start_byte": gap_start + 2,
                                "end_byte": gap_start + 3,
                            },
                        },
                        "source_span": {
                            "file": logical_file,
                            "start_byte": gap_start,
                            "end_byte": gap_start + 3,
                        },
                    },
                    "then": [
                        {
                            "kind": "return",
                            "expression": {
                                "kind": "literal",
                                "value": 4242,
                                "source_span": {
                                    "file": logical_file,
                                    "start_byte": first_statement_start - 1,
                                    "end_byte": first_statement_start,
                                },
                            },
                            "source_span": {
                                "file": logical_file,
                                "start_byte": gap_start + 4,
                                "end_byte": first_statement_start,
                            },
                        }
                    ],
                    "else": [],
                    "source_span": {
                        "file": logical_file,
                        "start_byte": gap_start,
                        "end_byte": first_statement_start,
                    },
                },
            )

            # Simulate a malicious but internally consistent analyzer.  The
            # engine regenerates target bytes, relifted IR, chunk mappings,
            # formal input, SMT/result and layered evidence from the forged
            # source IR.  The bounded cases deliberately do not contain 42,
            # so native observations remain self-consistent as well.
            from elmos_polyglot_route import engine as route_engine
            from elmos_polyglot_route.models import SemanticIR

            forged_source_ir = SemanticIR.from_mapping(source_document)
            original_analyze = route_engine.analyze

            def forged_analyze(
                source: Path,
                language: str,
                requested_function: str,
                *,
                emitted_target: bool = False,
            ):
                if language == "cpp" and not emitted_target:
                    self.assertEqual(source.name, source_path.name)
                    self.assertEqual(requested_function, function_name)
                    return forged_source_ir
                return original_analyze(
                    source,
                    language,
                    requested_function,
                    emitted_target=emitted_target,
                )

            runner = load_polyglot_runner()
            with (
                tempfile.TemporaryDirectory() as generated_td,
                mock.patch.object(route_engine, "analyze", side_effect=forged_analyze),
            ):
                generated = Path(generated_td)
                report = route_engine.migrate(
                    source_path,
                    "cpp",
                    "java",
                    function_name,
                    cases_path,
                    generated,
                )
                report.update(
                    {
                        "corpus": corpus,
                        "executor": "local-toolchain",
                        "independent_verifier": "NOT_RUN",
                        "authorization": "local-engineering-validation",
                        "route_maturity": "LIMITED",
                        "certification_status": "NOT_CERTIFIED",
                    }
                )
                inputs = generated / "inputs"
                inputs.mkdir()
                shutil.copy2(source_path, inputs / source_path.name)
                shutil.copy2(cases_path, inputs / "cases.json")
                write_json(generated / "route-evidence.json", report)
                manifest_ref = runner.persist_artifact_directory(
                    route.parent,
                    route,
                    corpus,
                    generated,
                )
            report["artifact_root"] = f"certification/artifacts/{corpus}"
            report["artifact_manifest"] = manifest_ref
            write_json(
                route / "certification" / "local-development-evidence.json",
                report,
            )

            reports = {corpus: report}
            local_names = {
                "development": "local-development-evidence.json",
                "holdout": "local-holdout-evidence.json",
                "real-repository": "local-representative-evidence.json",
            }
            for current_corpus in ("holdout", "real-repository"):
                corpus_root = route / "corpus" / current_corpus
                current_manifest = json.loads(
                    (corpus_root / "manifest.json").read_text()
                )
                current_source = corpus_root / current_manifest["source_file"]
                current_cases = corpus_root / current_manifest["cases_file"]
                current_function = current_manifest["function_name"]
                with tempfile.TemporaryDirectory() as current_generated_td:
                    current_generated = Path(current_generated_td)
                    current_report = route_engine.migrate(
                        current_source,
                        "cpp",
                        "java",
                        current_function,
                        current_cases,
                        current_generated,
                    )
                    current_report.update(
                        {
                            "corpus": current_corpus,
                            "executor": "local-toolchain",
                            "independent_verifier": "NOT_RUN",
                            "authorization": "local-engineering-validation",
                            "route_maturity": "LIMITED",
                            "certification_status": "NOT_CERTIFIED",
                        }
                    )
                    current_inputs = current_generated / "inputs"
                    current_inputs.mkdir()
                    shutil.copy2(
                        current_source,
                        current_inputs / current_source.name,
                    )
                    shutil.copy2(current_cases, current_inputs / "cases.json")
                    write_json(
                        current_generated / "route-evidence.json",
                        current_report,
                    )
                    current_manifest_ref = runner.persist_artifact_directory(
                        route.parent,
                        route,
                        current_corpus,
                        current_generated,
                    )
                current_report["artifact_root"] = (
                    f"certification/artifacts/{current_corpus}"
                )
                current_report["artifact_manifest"] = current_manifest_ref
                write_json(
                    route / "certification" / local_names[current_corpus],
                    current_report,
                )
                reports[current_corpus] = current_report
            formal_ref = runner.build_formal_equivalence_evidence(
                ROOT,
                route,
                "cpp",
                "java",
                reports,
                None,
            )
            certification_path = route / "certification" / "certification.json"
            certification = json.loads(certification_path.read_text())
            certification["formal_equivalence"] = formal_ref
            write_json(certification_path, certification)
            evidence_path = route / "certification" / "evidence.json"
            evidence = json.loads(evidence_path.read_text())
            evidence["artifact_manifests"][corpus] = manifest_ref
            evidence["artifact_refs"] = [
                manifest_ref if item.get("path") == manifest_ref["path"] else item
                for item in evidence["artifact_refs"]
            ]
            evidence["formal_equivalence"] = formal_ref
            write_json(evidence_path, evidence)

            validator = load_route_validator()
            failures: list[str] = []
            validator._validate_specialized_native_runtime_replay(
                route,
                json.loads((route / "route.json").read_text()),
                failures,
            )
            self.assertIn(
                "specialized development independent native replay failed: "
                "identifier plan is detached from fresh source analysis",
                failures,
            )

    def test_specialized_swift_receipt_stable_projection_tamper_fails_closed(self):
        validator = load_route_validator()
        persisted = portable_swift_analyzer_receipt(validator)
        fresh = copy.deepcopy(persisted)
        persisted["build"]["environment_policy"] = "ambient-host-hooks"
        persisted_failures: list[str] = []
        validator._validate_swift_analyzer_receipt_document(
            persisted,
            label="persisted receipt",
            failures=persisted_failures,
        )
        self.assertTrue(
            any("build policy is invalid" in failure for failure in persisted_failures)
        )

        with tempfile.TemporaryDirectory() as td:
            receipt_path = Path(td) / "swift-analyzer-build-receipt.json"
            write_json(receipt_path, persisted)
            failures: list[str] = []
            api = (
                lambda _toolchain: ("/unused/ElmosSwiftAnalyzer", fresh),
                lambda: fresh,
                lambda _language: copy.deepcopy(validator.SWIFT_ANALYZER_TOOLCHAIN),
            )
            with (
                mock.patch.object(
                    validator,
                    "_engine_swift_analyzer_api",
                    return_value=api,
                ),
                mock.patch.object(
                    validator,
                    "_validate_swift_analyzer_receipt_document",
                    side_effect=lambda value, **_kwargs: value,
                ),
            ):
                validator._validate_swift_receipt_binding(
                    source_language="cpp",
                    target_language="swift",
                    records=[
                        (
                            {"path": validator.SWIFT_ANALYZER_RECEIPT_PATH},
                            receipt_path,
                            "swift-analyzer-build-receipt",
                        )
                    ],
                    label="formal Swift analyzer build receipt",
                    failures=failures,
                )
            self.assertIn(
                "formal Swift analyzer build receipt stable projection differs "
                "from independent scratch rebuild",
                failures,
            )

    def test_specialized_swift_receipt_standalone_v2_contract_is_fail_closed(self):
        validator = load_route_validator()
        runner = load_polyglot_runner()
        expected = {"verified-content-addressed-standalone-cache"}
        self.assertEqual(set(validator.SWIFT_ANALYZER_MIRROR_SEEDS), expected)
        self.assertEqual(validator.SWIFT_DEPENDENCY_SEED, next(iter(expected)))
        self.assertEqual(
            validator.SWIFT_DEPENDENCY_CACHE_SCHEMA,
            "swift-dependencies-standalone-v2",
        )
        self.assertEqual(
            validator.SWIFT_DEPENDENCY_OBJECT_STORE_POLICY,
            "standalone-no-alternates-no-hardlinks-v2",
        )
        self.assertTrue(
            validator.SWIFT_DEPENDENCY_CACHE_KEY.startswith(
                "swift-syntax-standalone-v2-600.0.1-"
            )
        )
        for name in (
            "SWIFT_DEPENDENCY_SEED",
            "SWIFT_DEPENDENCY_CACHE_SCHEMA",
            "SWIFT_DEPENDENCY_OBJECT_STORE_POLICY",
            "SWIFT_DEPENDENCY_CACHE_KEY",
            "SWIFT_DEPENDENCY_CACHE_KEYS",
        ):
            self.assertEqual(getattr(runner, name), getattr(validator, name))

        from jsonschema import Draft202012Validator

        schemas = [
            json.loads((ROOT / "schemas" / "batch29" / name).read_text())
            for name in (
                "formal-equivalence-evidence.schema.json",
                "module-equivalence-evidence.schema.json",
            )
        ]
        swift_definition_names = {
            name for name in schemas[0]["$defs"] if name.startswith("swift_")
        }
        self.assertEqual(len(swift_definition_names), 38)
        self.assertEqual(
            swift_definition_names,
            {name for name in schemas[1]["$defs"] if name.startswith("swift_")},
        )
        for definition_name in swift_definition_names:
            self.assertEqual(
                schemas[0]["$defs"][definition_name],
                schemas[1]["$defs"][definition_name],
            )
        cache_contracts = [
            schema["$defs"]["swift_dependency_cache_receipt"] for schema in schemas
        ]
        mirror_contracts = [
            schema["$defs"]["swift_dependency_mirror_receipt"] for schema in schemas
        ]
        self.assertEqual(cache_contracts[0], cache_contracts[1])
        self.assertEqual(mirror_contracts[0], mirror_contracts[1])
        receipt = portable_swift_analyzer_receipt(validator)
        for schema in schemas:
            receipt_contract = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$defs": schema["$defs"],
                "$ref": "#/$defs/swift_analyzer_build_receipt",
            }
            self.assertEqual(
                list(Draft202012Validator(receipt_contract).iter_errors(receipt)),
                [],
            )
        mirror = receipt["dependency"]["mirror"]
        cache = mirror["cache"]
        for contract in cache_contracts:
            self.assertEqual(
                set(contract["required"]), validator.SWIFT_DEPENDENCY_CACHE_KEYS
            )
            self.assertEqual(
                list(Draft202012Validator(contract).iter_errors(cache)),
                [],
            )
            for bad_seed in ("verified-package-checkout", "unknown"):
                forged = copy.deepcopy(cache)
                forged["seed"] = bad_seed
                self.assertNotEqual(
                    list(Draft202012Validator(contract).iter_errors(forged)),
                    [],
                )
            for field in ("object_store_policy",):
                missing = copy.deepcopy(cache)
                missing.pop(field)
                self.assertNotEqual(
                    list(Draft202012Validator(contract).iter_errors(missing)),
                    [],
                )
            forged_policy = copy.deepcopy(cache)
            forged_policy["object_store_policy"] = "borrowed-object-store"
            self.assertNotEqual(
                list(Draft202012Validator(contract).iter_errors(forged_policy)),
                [],
            )
            legacy = copy.deepcopy(cache)
            legacy.update(
                {
                    "cache_key": (
                        "swift-syntax-600.0.1-"
                        "0687f71944021d616d34d922343dcef086855920-"
                        "b78ec1b227a6cbe43ca239585f66907e50485b9119f96b5461bfc888f0e5f45d"
                    ),
                    "cache_schema": "swift-dependencies-v1",
                    "seed": "verified-content-addressed-cache",
                }
            )
            self.assertNotEqual(
                list(Draft202012Validator(contract).iter_errors(legacy)),
                [],
            )

    def test_specialized_swift_portable_cache_receipt_tamper_fails_closed(self):
        validator = load_route_validator()
        receipt = portable_swift_analyzer_receipt(validator)
        baseline_failures: list[str] = []
        validator._validate_swift_analyzer_receipt_document(
            receipt,
            label="portable receipt",
            failures=baseline_failures,
        )
        self.assertEqual(baseline_failures, [])
        projection = validator._swift_receipt_stable_projection(receipt)
        self.assertEqual(set(projection), {"sha256", "receipt"})
        self.assertEqual(
            projection["receipt"]["dependency"]["mirror"]["seed"],
            "verified-content-addressed-standalone-cache",
        )
        self.assertEqual(
            projection["receipt"]["dependency"]["mirror"]["cache"][
                "object_store_policy"
            ],
            "standalone-no-alternates-no-hardlinks-v2",
        )
        self.assertNotIn(
            "absolute_path",
            projection["receipt"]["dependency"]["mirror"]["cache"],
        )
        self.assertNotIn("path", projection["receipt"]["binary"])
        self.assertNotIn("root", projection["receipt"]["execution_seal"])
        self.assertNotIn("device", projection["receipt"]["binary"])
        self.assertNotIn("inode", projection["receipt"]["binary"])
        portable_closure = projection["receipt"]["toolchain"]["build_closure"]
        self.assertNotIn("path", portable_closure["components"][0])
        self.assertNotIn("resolved_path", portable_closure["components"][0])
        self.assertNotIn("uid", portable_closure["components"][0])
        self.assertNotIn("gid", portable_closure["components"][0])
        self.assertNotIn("root", portable_closure["trees"][0])
        self.assertEqual(portable_closure["compiler_runtime_soundness"], "NOT_RUN")
        self.assertEqual(portable_closure["certification"], "NOT_CERTIFIED")
        portable_probe_build = projection["receipt"]["network_isolation"]["probe"][
            "build"
        ]
        self.assertEqual(
            set(portable_probe_build),
            {"environment_policy", "argv", "environment", "compiler"},
        )
        self.assertEqual(
            portable_probe_build["environment"]["PATH"],
            "<swift-toolchain-bin>:<system-usr-bin>:<system-bin>:<system-usr-sbin>:<system-sbin>",
        )
        self.assertNotIn(
            "/Applications/", json.dumps(portable_probe_build["environment"])
        )
        self.assertNotIn("/private/", json.dumps(portable_probe_build["environment"]))
        host_drift = copy.deepcopy(receipt)
        host_drift["toolchain"]["swiftc"] = "/other/toolchain/swiftc"
        host_drift["toolchain"]["swift_driver"] = "/other/toolchain/swift"
        host_drift["toolchain"]["build_closure"]["components"][0]["path"] = (
            "/other/toolchain/swift"
        )
        host_drift["toolchain"]["build_closure"]["components"][0]["resolved_path"] = (
            "/other/toolchain/swift-frontend"
        )
        host_drift["toolchain"]["build_closure"]["components"][0]["uid"] = 502
        host_drift["toolchain"]["build_closure"]["components"][0]["gid"] = 21
        host_drift["toolchain"]["build_closure"]["trees"][0]["root"] = (
            "/other/toolchain/ManifestAPI"
        )
        host_drift["network_isolation"]["sandbox"]["path"] = (
            "/other/usr/bin/sandbox-exec"
        )
        host_drift["network_isolation"]["verifier"]["path"] = "/other/usr/bin/codesign"
        host_probe = host_drift["network_isolation"]["probe"]
        host_probe["build"]["compiler"].update(
            {
                "path": "/other/toolchain/clang",
                "resolved_path": "/other/toolchain/clang",
                "uid": 502,
                "gid": 21,
            }
        )
        host_probe["binary"].update(
            {
                "path": "/other/elmos-swift-analyzer-x/network-probe-execution/ElmosNetworkDenyProbe",
                "uid": 502,
                "gid": 21,
                "device": 9,
                "inode": 12,
            }
        )
        host_probe["execution_seal"].update(
            {
                "root": "/other/elmos-swift-analyzer-x/network-probe-execution",
                "uid": 502,
                "gid": 21,
                "device": 9,
                "inode": 11,
                "binary": copy.deepcopy(host_probe["binary"]),
            }
        )
        host_drift["binary"].update(
            {
                "path": "/other/elmos-swift-analyzer-x/ElmosSwiftAnalyzer",
                "uid": 502,
                "gid": 21,
                "device": 9,
                "inode": 10,
            }
        )
        host_drift["execution_seal"].update(
            {
                "root": "/other/elmos-swift-analyzer-x",
                "uid": 502,
                "gid": 21,
                "device": 9,
                "inode": 11,
                "binary": copy.deepcopy(host_drift["binary"]),
            }
        )
        host_drift["canonical_identity"] = {
            "sha256": "sha256:" + "f" * 64,
            "receipt": {"forged": "/host/path"},
        }
        self.assertEqual(
            validator._swift_receipt_stable_projection(host_drift),
            projection,
        )

        def refresh_canonical(value: dict[str, object]) -> None:
            canonical = validator._rebuild_portable_swift_receipt_identity(value)
            value["canonical_identity"] = {
                "sha256": validator._receipt_payload_sha256(canonical),
                "receipt": canonical,
            }

        def forge_self_consistent_mach_o(value: dict[str, object]) -> None:
            value["network_isolation"]["probe"]["mach_o"]["uuid"] = (  # type: ignore[index]
                "00000000-0000-0000-0000-000000000000"
            )
            refresh_canonical(value)

        def forge_self_consistent_host_path(value: dict[str, object]) -> None:
            source = value["network_isolation"]["probe"]["source"]  # type: ignore[index]
            text = "/tmp/host-probe.c"
            source.update(  # type: ignore[union-attr]
                {
                    "text": text,
                    "sha256": validator.sha256_bytes(text.encode("utf-8")),
                    "bytes": len(text.encode("utf-8")),
                }
            )
            refresh_canonical(value)

        mutations = (
            (
                "absolute_path extra",
                lambda value: value["dependency"]["mirror"]["cache"].update(
                    {"absolute_path": "/tmp/host-cache"}
                ),
                "cache keys are not exact",
            ),
            (
                "cache key",
                lambda value: value["dependency"]["mirror"]["cache"].update(
                    {"cache_key": "swift-syntax-forged"}
                ),
                "cache.cache_key is invalid",
            ),
            (
                "cache schema",
                lambda value: value["dependency"]["mirror"]["cache"].update(
                    {"cache_schema": "swift-dependencies-v2"}
                ),
                "cache.cache_schema is invalid",
            ),
            (
                "object store policy",
                lambda value: value["dependency"]["mirror"]["cache"].update(
                    {"object_store_policy": "borrowed-object-store"}
                ),
                "cache.object_store_policy is invalid",
            ),
            (
                "cache seed",
                lambda value: value["dependency"]["mirror"]["cache"].update(
                    {"seed": "verified-package-checkout"}
                ),
                "cache.seed is invalid",
            ),
            (
                "mirror revision",
                lambda value: value["dependency"]["mirror"].update(
                    {"revision": "0" * 40}
                ),
                "mirror identity is invalid",
            ),
            (
                "mirror tree",
                lambda value: value["dependency"]["mirror"].update(
                    {"sha256": "sha256:" + "0" * 64}
                ),
                "mirror.sha256 differs from dependency tree",
            ),
            (
                "git identity",
                lambda value: value["dependency"]["mirror"]["git"].update(
                    {"version": "git version forged"}
                ),
                "mirror.git identity is invalid",
            ),
            (
                "system git path",
                lambda value: value["dependency"]["mirror"]["git"].update(
                    {"path": "/usr/bin/git"}
                ),
                "mirror.git identity is invalid",
            ),
            (
                "system git digest",
                lambda value: value["dependency"]["mirror"]["git"].update(
                    {"sha256": "sha256:" + "4" * 64}
                ),
                "mirror.git identity is invalid",
            ),
            (
                "unknown mirror seed",
                lambda value: value["dependency"]["mirror"].update({"seed": "unknown"}),
                "mirror.seed is invalid",
            ),
            (
                "network policy",
                lambda value: value["network_isolation"]["policy"].update(
                    {"text": "(version 1)\n(allow default)\n"}
                ),
                "network_isolation policy/provenance is invalid",
            ),
            (
                "network probe",
                lambda value: value["network_isolation"]["probe"].update(
                    {"result": "NETWORK_DENIED:13"}
                ),
                "network_isolation.probe.binary identity is invalid",
            ),
            (
                "obsolete interpreter",
                lambda value: value["network_isolation"]["probe"].update(
                    {"interpreter": {"path": "/usr/bin/python3"}}
                ),
                "network_isolation.probe keys are not exact",
            ),
            (
                "obsolete framework",
                lambda value: value["network_isolation"]["probe"].update(
                    {"framework": {"path": "/tmp/Python3.framework"}}
                ),
                "network_isolation.probe keys are not exact",
            ),
            (
                "obsolete script digest",
                lambda value: value["network_isolation"]["probe"].update(
                    {"script_sha256": "sha256:" + "5" * 64}
                ),
                "network_isolation.probe keys are not exact",
            ),
            (
                "probe source text",
                lambda value: value["network_isolation"]["probe"]["source"].update(
                    {"text": "int main(void) { return 0; }\n"}
                ),
                "network_isolation.probe.source is invalid",
            ),
            (
                "probe source digest",
                lambda value: value["network_isolation"]["probe"]["source"].update(
                    {"sha256": "sha256:" + "6" * 64}
                ),
                "network_isolation.probe.source is invalid",
            ),
            (
                "probe source bytes",
                lambda value: value["network_isolation"]["probe"]["source"].update(
                    {"bytes": 922}
                ),
                "network_isolation.probe.source is invalid",
            ),
            (
                "probe source extra",
                lambda value: value["network_isolation"]["probe"]["source"].update(
                    {"language": "c"}
                ),
                "network_isolation.probe.source is invalid",
            ),
            (
                "probe build environment policy",
                lambda value: value["network_isolation"]["probe"]["build"].update(
                    {"environment_policy": "ambient"}
                ),
                "network_isolation.probe.build is invalid",
            ),
            (
                "probe build argv",
                lambda value: value["network_isolation"]["probe"]["build"][
                    "argv"
                ].append("-framework"),
                "network_isolation.probe.build is invalid",
            ),
            (
                "probe build environment missing",
                lambda value: value["network_isolation"]["probe"]["build"][
                    "environment"
                ].pop("PYTHONNOUSERSITE"),
                "network_isolation.probe.build is invalid",
            ),
            (
                "probe build environment extra",
                lambda value: value["network_isolation"]["probe"]["build"][
                    "environment"
                ].update({"SDKROOT": "/tmp/forged-sdk"}),
                "network_isolation.probe.build is invalid",
            ),
            (
                "probe build environment value",
                lambda value: value["network_isolation"]["probe"]["build"][
                    "environment"
                ].update({"TZ": "Asia/Shanghai"}),
                "network_isolation.probe.build is invalid",
            ),
            (
                "probe build environment path injection",
                lambda value: value["network_isolation"]["probe"]["build"][
                    "environment"
                ].update({"PATH": "/tmp/host-bin:/usr/bin"}),
                "network_isolation.probe.build is invalid",
            ),
            (
                "probe compiler role",
                lambda value: value["network_isolation"]["probe"]["build"][
                    "compiler"
                ].update({"role": "swift-driver"}),
                "network_isolation.probe.build is invalid",
            ),
            (
                "probe compiler path",
                lambda value: value["network_isolation"]["probe"]["build"][
                    "compiler"
                ].update({"path": "/tmp/forged-clang"}),
                "network_isolation.probe.build is invalid",
            ),
            (
                "probe compiler digest",
                lambda value: value["network_isolation"]["probe"]["build"][
                    "compiler"
                ].update({"sha256": "sha256:" + "7" * 64}),
                "network_isolation.probe.build is invalid",
            ),
            (
                "probe compiler extra",
                lambda value: value["network_isolation"]["probe"]["build"][
                    "compiler"
                ].update({"device": 1}),
                "network_isolation.probe.build is invalid",
            ),
            (
                "probe binary name",
                lambda value: value["network_isolation"]["probe"]["binary"].update(
                    {"name": "PythonNetworkProbe"}
                ),
                "network_isolation.probe.binary identity is invalid",
            ),
            (
                "probe binary path",
                lambda value: value["network_isolation"]["probe"]["binary"].update(
                    {"path": "/private/tmp/forged/../ElmosNetworkDenyProbe"}
                ),
                "network_isolation.probe.binary identity is invalid",
            ),
            (
                "probe binary digest",
                lambda value: value["network_isolation"]["probe"]["binary"].update(
                    {"sha256": "sha256:" + "8" * 64}
                ),
                "network_isolation.probe.binary identity is invalid",
            ),
            (
                "probe binary bytes",
                lambda value: value["network_isolation"]["probe"]["binary"].update(
                    {"bytes": 1}
                ),
                "network_isolation.probe.binary identity is invalid",
            ),
            (
                "probe binary mode",
                lambda value: value["network_isolation"]["probe"]["binary"].update(
                    {"mode": "0755"}
                ),
                "network_isolation.probe.binary identity is invalid",
            ),
            (
                "probe binary nlink",
                lambda value: value["network_isolation"]["probe"]["binary"].update(
                    {"nlink": 2}
                ),
                "network_isolation.probe.binary identity is invalid",
            ),
            (
                "probe binary device",
                lambda value: value["network_isolation"]["probe"]["binary"].update(
                    {"device": 0}
                ),
                "network_isolation.probe.binary identity is invalid",
            ),
            (
                "probe binary inode",
                lambda value: value["network_isolation"]["probe"]["binary"].update(
                    {"inode": 0}
                ),
                "network_isolation.probe.binary identity is invalid",
            ),
            (
                "probe binary extra",
                lambda value: value["network_isolation"]["probe"]["binary"].update(
                    {"interpreter": "/usr/bin/python3"}
                ),
                "network_isolation.probe.binary keys are not exact",
            ),
            (
                "probe seal policy",
                lambda value: value["network_isolation"]["probe"][
                    "execution_seal"
                ].update({"policy": "writable-root"}),
                "network_isolation.probe.execution_seal is invalid",
            ),
            (
                "probe seal root",
                lambda value: value["network_isolation"]["probe"][
                    "execution_seal"
                ].update({"root": "/private/tmp/forged/../network-probe-execution"}),
                "network_isolation.probe.execution_seal is invalid",
            ),
            (
                "probe seal binary",
                lambda value: value["network_isolation"]["probe"]["execution_seal"][
                    "binary"
                ].update({"inode": 99}),
                "network_isolation.probe.execution_seal is invalid",
            ),
            (
                "probe seal extra",
                lambda value: value["network_isolation"]["probe"][
                    "execution_seal"
                ].update({"owner": "forged"}),
                "network_isolation.probe.execution_seal keys are not exact",
            ),
            (
                "probe Mach-O UUID",
                lambda value: value["network_isolation"]["probe"]["mach_o"].update(
                    {"uuid": "00000000-0000-0000-0000-000000000000"}
                ),
                "network_isolation.probe.mach_o is invalid",
            ),
            (
                "probe Mach-O CDHash",
                lambda value: value["network_isolation"]["probe"]["mach_o"].update(
                    {"cdhash_full": "9" * 64}
                ),
                "network_isolation.probe.mach_o is invalid",
            ),
            (
                "probe Mach-O library",
                lambda value: value["network_isolation"]["probe"]["mach_o"].update(
                    {"linked_libraries": ["/tmp/libSystem.B.dylib"]}
                ),
                "network_isolation.probe.mach_o is invalid",
            ),
            (
                "probe Mach-O extra",
                lambda value: value["network_isolation"]["probe"]["mach_o"].update(
                    {"interpreter": "/usr/lib/dyld"}
                ),
                "network_isolation.probe.mach_o is invalid",
            ),
            (
                "self-consistent canonical Mach-O tamper",
                forge_self_consistent_mach_o,
                "network_isolation.probe.mach_o is invalid",
            ),
            (
                "self-consistent canonical host path",
                forge_self_consistent_host_path,
                "canonical_identity contains a host path",
            ),
            (
                "network verifier",
                lambda value: value["network_isolation"]["verifier"].update(
                    {"sha256": "sha256:" + "1" * 64}
                ),
                "network_isolation policy/provenance is invalid",
            ),
            (
                "build argv",
                lambda value: value["build"]["argv"].append("--allow-network"),
                "build policy is invalid",
            ),
            (
                "build extra",
                lambda value: value["build"].update({"scratch_root": "/tmp"}),
                "build keys are not exact",
            ),
            (
                "binary mode",
                lambda value: value["binary"].update({"mode": "0755"}),
                "binary identity/seal metadata is invalid",
            ),
            (
                "binary path injection",
                lambda value: value["binary"].update(
                    {
                        "path": (
                            "/private/tmp/elmos-swift-analyzer-fixture/../"
                            "forged/ElmosSwiftAnalyzer"
                        )
                    }
                ),
                "binary identity/seal metadata is invalid",
            ),
            (
                "binary extra key",
                lambda value: value["binary"].update({"owner": "forged"}),
                "binary keys are not exact",
            ),
            (
                "execution seal mode",
                lambda value: value["execution_seal"].update({"mode": "0700"}),
                "execution_seal identity is invalid",
            ),
            (
                "execution seal binary",
                lambda value: value["execution_seal"]["binary"].update({"inode": 99}),
                "execution_seal identity is invalid",
            ),
            (
                "canonical digest",
                lambda value: value["canonical_identity"].update(
                    {"sha256": "sha256:" + "2" * 64}
                ),
                "canonical_identity mismatch",
            ),
            (
                "canonical host path",
                lambda value: value["canonical_identity"]["receipt"]["binary"].update(
                    {"path": "/tmp/forged"}
                ),
                "canonical_identity mismatch",
            ),
            (
                "canonical extra key",
                lambda value: value["canonical_identity"].update(
                    {"scratch_root": "/tmp/forged"}
                ),
                "canonical_identity keys are not exact",
            ),
            (
                "toolchain version",
                lambda value: value["toolchain"].update(
                    {"version": "Apple Swift version forged"}
                ),
                "toolchain exact identity is invalid",
            ),
            (
                "toolchain path",
                lambda value: value["toolchain"].update(
                    {"swift_driver": "/tmp/forged-swift"}
                ),
                "toolchain exact identity is invalid",
            ),
            (
                "toolchain closure schema",
                lambda value: value["toolchain"]["build_closure"].update(
                    {"schema": "swiftpm-build-execution-closure-v2"}
                ),
                "toolchain exact identity is invalid",
            ),
            (
                "toolchain closure component digest",
                lambda value: value["toolchain"]["build_closure"]["components"][
                    4
                ].update({"sha256": "sha256:" + "3" * 64}),
                "toolchain exact identity is invalid",
            ),
            (
                "toolchain closure component path injection",
                lambda value: value["toolchain"]["build_closure"]["components"][
                    4
                ].update({"path": "/tmp/forged-swift-driver"}),
                "toolchain exact identity is invalid",
            ),
            (
                "toolchain closure component extra",
                lambda value: value["toolchain"]["build_closure"]["components"][
                    4
                ].update({"device": 1}),
                "toolchain exact identity is invalid",
            ),
            (
                "toolchain closure tree root",
                lambda value: value["toolchain"]["build_closure"]["trees"][0].update(
                    {"root": "/tmp/ManifestAPI"}
                ),
                "toolchain exact identity is invalid",
            ),
            (
                "toolchain closure certification",
                lambda value: value["toolchain"]["build_closure"].update(
                    {"certification": "CERTIFIED"}
                ),
                "toolchain exact identity is invalid",
            ),
            (
                "top-level extra",
                lambda value: value.update({"scratch_root": "/tmp/forged"}),
                "top-level keys are not exact",
            ),
        )
        for name, mutate, expected in mutations:
            with self.subTest(name=name):
                forged = copy.deepcopy(receipt)
                mutate(forged)
                failures: list[str] = []
                validator._validate_swift_analyzer_receipt_document(
                    forged,
                    label="portable receipt",
                    failures=failures,
                )
                self.assertTrue(
                    any(expected in failure for failure in failures),
                    failures,
                )

    def test_specialized_runner_validates_full_swift_receipt_before_write(self):
        from elmos_polyglot_route import native as swift_native

        validator = load_route_validator()
        runner = load_polyglot_runner()
        with tempfile.TemporaryDirectory(prefix="elmos-swift-analyzer-") as temporary:
            root = Path(temporary).resolve()
            binary_path = root / "ElmosSwiftAnalyzer"
            binary_path.write_bytes(b"portable-swift-analyzer-fixture")
            binary_path.chmod(0o500)
            binary_metadata = binary_path.lstat()
            probe_environment = validator._probe_validation_environment(root)
            network_isolation, network_identity = (
                swift_native._verified_swift_network_isolation(
                    root,
                    probe_environment,
                )
            )
            swift_native._require_current_swift_network_execution_identity(
                network_identity,
                root=root,
                environment=probe_environment,
            )
            root.chmod(0o500)
            root_metadata = root.lstat()
            try:
                receipt = portable_swift_analyzer_receipt(validator)
                receipt["network_isolation"] = network_isolation
                binary = {
                    "name": "ElmosSwiftAnalyzer",
                    "path": str(binary_path),
                    "sha256": digest(binary_path),
                    "bytes": binary_metadata.st_size,
                    "mode": "0500",
                    "uid": binary_metadata.st_uid,
                    "gid": binary_metadata.st_gid,
                    "nlink": binary_metadata.st_nlink,
                    "device": binary_metadata.st_dev,
                    "inode": binary_metadata.st_ino,
                }
                receipt["binary"] = binary
                receipt["execution_seal"] = {
                    "policy": "private-nonwritable-execution-root-v1",
                    "root": str(root),
                    "mode": "0500",
                    "uid": root_metadata.st_uid,
                    "gid": root_metadata.st_gid,
                    "device": root_metadata.st_dev,
                    "inode": root_metadata.st_ino,
                    "binary": copy.deepcopy(binary),
                }
                canonical = validator._rebuild_portable_swift_receipt_identity(receipt)
                receipt["canonical_identity"] = {
                    "sha256": validator._receipt_payload_sha256(canonical),
                    "receipt": canonical,
                }
                runner.validate_portable_swift_analyzer_receipt(receipt)

                forged = copy.deepcopy(receipt)
                forged["build"]["argv"].append("--allow-network")
                with self.assertRaisesRegex(
                    RuntimeError,
                    "SWIFT_ANALYZER_BUILD_RECEIPT_INVALID",
                ):
                    runner.validate_portable_swift_analyzer_receipt(forged)
            finally:
                root.chmod(0o700)

    def test_specialized_pack_generator_revalidates_complete_swift_receipt(self):
        validator = load_route_validator()
        generator = load_specialized_pack_generator()
        with tempfile.TemporaryDirectory() as temporary:
            route = Path(temporary) / "swift-to-cpp"
            receipt_path = (
                route
                / "certification"
                / "formal-artifacts"
                / "swift-analyzer-build-receipt.json"
            )
            receipt_path.parent.mkdir(parents=True)
            receipt = portable_swift_analyzer_receipt(validator)
            write_json(receipt_path, receipt)
            reference = {
                "path": (
                    "certification/formal-artifacts/swift-analyzer-build-receipt.json"
                ),
                "sha256": digest(receipt_path),
                "bytes": receipt_path.stat().st_size,
            }
            generator.validate_portable_swift_receipt(route, reference)

            receipt["observations"] = {"dependency_cache_absolute_path": "/tmp/forged"}
            write_json(receipt_path, receipt)
            with self.assertRaisesRegex(
                RuntimeError,
                "SWIFT_ANALYZER_RECEIPT_INVALID",
            ):
                generator.validate_portable_swift_receipt(route, reference)

    def test_specialized_module_rejects_forged_runtime_observation_closure(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "cpp-to-java"
            shutil.copytree(ROOT / "routes" / "cpp-to-java", route)
            report = install_fresh_cpp_java_module_evidence(route)
            symbol = "both"
            for side in ("source", "target"):
                validation_role = f"{side}-module-validation"
                validation_relative = next(
                    item["path"]
                    for item in report["artifact_refs"]
                    if item["role"] == validation_role
                )
                validation_path = route / validation_relative
                validation_document = json.loads(validation_path.read_text())
                forged = validation_document[symbol]["observations"][0]
                forged.update({"value": False, "raw": "false"})
                validation_document[symbol]["commands"][-1]["stdout"] = (
                    validation_document[symbol]["commands"][-1]["stdout"].replace(
                        "\t0\tbool\ttrue", "\t0\tbool\tfalse", 1
                    )
                )
                write_json(validation_path, validation_document)
                refresh_module_artifact(route, report, validation_relative)
                report[f"{side}_validation"] = validation_document

                observation_role = f"{side}-module-observations"
                observation_relative = next(
                    item["path"]
                    for item in report["artifact_refs"]
                    if item["role"] == observation_role
                )
                observation_path = route / observation_relative
                observation_document = json.loads(observation_path.read_text())
                observation_document[symbol][0].update({"value": False, "raw": "false"})
                write_json(observation_path, observation_document)
                refresh_module_artifact(route, report, observation_relative)

            function = next(
                item for item in report["functions"] if item["symbol"] == symbol
            )
            result = function["layers"]["behavior"]["results"][0]
            result["canonical"]["value"] = False
            result["independent_expected"] = False
            result["source_native"].update({"value": False, "raw": "false"})
            result["target_native"].update({"value": False, "raw": "false"})
            refresh_module_report_reference(route, report)

            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                timeout=300,
            )
            output = completed.stdout + completed.stderr
            self.assertNotEqual(completed.returncode, 0, output)
            self.assertIn(
                "source-module-validation differs from independent native replay",
                output,
            )
            self.assertIn(
                "target-module-validation differs from independent native replay",
                output,
            )
            self.assertIn(
                "source-module-observations differ from independent native replay",
                output,
            )
            self.assertIn(
                "target-module-observations differ from independent native replay",
                output,
            )

    def test_specialized_module_rejects_hidden_string_and_number_semantics(self):
        validator = load_route_validator()
        for scenario in ("string-equality", "number-arithmetic"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as td:
                route = Path(td) / "cpp-to-java"
                shutil.copytree(ROOT / "routes" / "cpp-to-java", route)
                report = json.loads(
                    (route / "certification" / "module-equivalence.json").read_text()
                )
                for side in ("source", "target"):
                    role = f"{side}-module-semantic-ir"
                    relative = next(
                        item["path"]
                        for item in report["artifact_refs"]
                        if item["role"] == role
                    )
                    path = route / relative
                    document = json.loads(path.read_text())
                    if scenario == "string-equality":
                        function = next(
                            item
                            for item in document["functions"]
                            if item["name"] == "both"
                        )
                        expression = function["body"][0]["expression"]
                        expression["operator"] = "=="
                        expression["left"]["kind"] = "literal"
                        expression["left"]["value"] = "canonically-hidden"
                        expression["right"]["kind"] = "literal"
                        expression["right"]["value"] = "canonically-hidden"
                    else:
                        function = next(
                            item
                            for item in document["functions"]
                            if item["name"] == "clampNumber"
                        )
                        expression = function["body"][0]["condition"]
                        expression["operator"] = "+"
                    write_json(path, document)
                refresh_module_semantic_bindings(route, report)
                refresh_module_report_reference(route, report)

                certification = json.loads(
                    (route / "certification" / "certification.json").read_text()
                )
                _, failures = validator.validate_module_equivalence(
                    route,
                    json.loads((route / "route.json").read_text()),
                    certification,
                )
                expected = (
                    "SPECIALIZED_STRING_SEMANTICS_UNSUPPORTED"
                    if scenario == "string-equality"
                    else "SPECIALIZED_NUMBER_ARITHMETIC_UNSUPPORTED"
                )
                self.assertTrue(
                    any(expected in failure for failure in failures), failures
                )

    def test_specialized_module_rejects_non_finite_json_case(self):
        validator = load_route_validator()
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "cpp-to-java"
            shutil.copytree(ROOT / "routes" / "cpp-to-java", route)
            report = json.loads(
                (route / "certification" / "module-equivalence.json").read_text()
            )
            case_relative = next(
                item["path"]
                for item in report["artifact_refs"]
                if item["role"] == "module-case-manifest"
            )
            case_path = route / case_relative
            case_path.write_text(case_path.read_text().replace("120", "NaN", 1))
            refresh_module_artifact(route, report, case_relative)
            report["module_input"]["corpus_sha256"] = digest(case_path)
            refresh_module_report_reference(route, report)

            certification = json.loads(
                (route / "certification" / "certification.json").read_text()
            )
            _, failures = validator.validate_module_equivalence(
                route,
                json.loads((route / "route.json").read_text()),
                certification,
            )
            self.assertTrue(
                any(
                    "non-finite JSON constant is forbidden: NaN" in failure
                    for failure in failures
                ),
                failures,
            )

    def test_route_inventory_is_exact_thirteen_language_complete_156(self):
        matrix = load_matrix_validator()
        inventory = json.loads((ROOT / "routes" / "inventory.json").read_text())
        routes = matrix.check_inventory_shape(inventory)
        self.assertEqual(len(routes), 156)
        self.assertEqual(
            {route["route_key"] for route in routes},
            set(matrix.EVIDENCED_ROUTE_KEYS),
        )
        self.assertEqual(inventory["pending_analyzer_languages"], [])
        self.assertEqual(inventory["pending_repository_languages"], [])
        self.assertNotIn("javascript", inventory["languages"])
        self.assertEqual(inventory["deprecated_languages"], ["javascript"])
        self.assertEqual(
            inventory["route_execution_authorities"],
            matrix.route_execution_authorities_document(),
        )
        matrix.check_route_packs(
            routes,
            str(inventory["semantic_profile"]),
            inventory["languages"],
        )

        missing = copy.deepcopy(inventory)
        removed = missing["routes"].pop()
        missing["route_count"] -= 1
        missing[f"{removed['status']}_route_count"] -= 1
        with self.assertRaisesRegex(matrix.MatrixError, "ROUTE_EXPLICIT_COUNT_DRIFT"):
            matrix.check_inventory_shape(missing)

        expanded = copy.deepcopy(inventory)
        expanded["routes"].append(
            {
                **copy.deepcopy(expanded["routes"][0]),
                "route_key": "duplicate-java-to-csharp",
            }
        )
        expanded["route_count"] += 1
        expanded[f"{expanded['routes'][0]['status']}_route_count"] += 1
        with self.assertRaisesRegex(matrix.MatrixError, "ROUTE_EXPLICIT_COUNT_DRIFT"):
            matrix.check_inventory_shape(expanded)

        self_directed = copy.deepcopy(inventory)
        self_directed["routes"][0]["target"] = self_directed["routes"][0]["source"]
        self_directed["routes"][0]["route_key"] = (
            f"{self_directed['routes'][0]['source']}-to-{self_directed['routes'][0]['source']}"
        )
        with self.assertRaisesRegex(matrix.MatrixError, "ROUTE_SELF_DIRECTED"):
            matrix.check_inventory_shape(self_directed)

        analyzer_regression = copy.deepcopy(inventory)
        analyzer_regression["pending_analyzer_languages"] = ["kotlin"]
        with self.assertRaisesRegex(
            matrix.MatrixError, "PENDING_ANALYZER_LANGUAGE_SET_DRIFT"
        ):
            matrix.check_inventory_shape(analyzer_regression)

        repository_regression = copy.deepcopy(inventory)
        repository_regression["pending_repository_languages"] = ["kotlin"]
        with self.assertRaisesRegex(
            matrix.MatrixError, "PENDING_REPOSITORY_LANGUAGE_SET_DRIFT"
        ):
            matrix.check_inventory_shape(repository_regression)

        dropped_deprecated_partition = copy.deepcopy(inventory)
        del dropped_deprecated_partition["route_provenance_partition"]["sets"][
            "javascript-node26-completion-18"
        ]
        with self.assertRaisesRegex(matrix.MatrixError, "ROUTE_PROVENANCE_SETS_DRIFT"):
            matrix.check_inventory_shape(dropped_deprecated_partition)

        authority_tampers = (
            (
                "javascript-node26-completion-18",
                "policy",
                "current-versioned-route-evidence",
            ),
            (
                "php-php85-completion-20",
                "policy",
                "current-versioned-route-evidence",
            ),
            (
                "php-php85-completion-20",
                "active_execution_selection",
                "php-all-20",
            ),
            (
                "kotlin-react-flutter-completion-66",
                "policy",
                "declared-ahead-of-analyzer",
            ),
            (
                "kotlin-react-flutter-completion-66",
                "native_reexecution_status",
                "PASSED_LOCAL",
            ),
            ("legacy-complete-30", "authority_sha256", "sha256:tampered"),
        )
        for authority, field, value in authority_tampers:
            tampered = copy.deepcopy(inventory)
            tampered["route_execution_authorities"][authority][field] = value
            with (
                self.subTest(authority=authority, field=field),
                self.assertRaisesRegex(
                    matrix.MatrixError, "ROUTE_EXECUTION_AUTHORITIES_DRIFT"
                ),
            ):
                matrix.check_inventory_shape(tampered)

        missing_authority = copy.deepcopy(inventory)
        del missing_authority["route_execution_authorities"][
            "kotlin-react-flutter-completion-66"
        ]
        with self.assertRaisesRegex(
            matrix.MatrixError, "ROUTE_EXECUTION_AUTHORITIES_DRIFT"
        ):
            matrix.check_inventory_shape(missing_authority)

        extra_authority = copy.deepcopy(inventory)
        extra_authority["route_execution_authorities"]["unowned-route-set"] = {
            "policy": "NOT_RUN"
        }
        with self.assertRaisesRegex(
            matrix.MatrixError, "ROUTE_EXECUTION_AUTHORITIES_DRIFT"
        ):
            matrix.check_inventory_shape(extra_authority)

        duplicated_digest_tamper = copy.deepcopy(inventory)
        duplicated_digest_tamper["route_sets"]["legacy-complete-30"][
            "execution_authority_sha256"
        ] = "sha256:tampered-duplicate"
        with self.assertRaisesRegex(
            matrix.MatrixError,
            "CORE_ROUTE_EXECUTION_AUTHORITY_DIGEST_DRIFT",
        ):
            matrix.check_inventory_shape(duplicated_digest_tamper)

    def test_route_matrix_document_covers_inventory_without_certification_overclaim(
        self,
    ):
        inventory = json.loads((ROOT / "routes" / "inventory.json").read_text())
        document = (ROOT / "docs" / "batch29" / "ROUTE_MATRIX.md").read_text()
        self.assertEqual(len(inventory["routes"]), 156)
        self.assertIn("156 directed routes across 13 active languages", document)
        for route_set in (
            "legacy-complete-30",
            "cpp-objc-swift-java-exact-8",
            "nine-language-completion-34",
            "nine-language-complete-72",
            "javascript-node26-completion-18",
            "ten-language-complete-90",
            "php-php85-completion-20",
            "eleven-language-complete-110",
            "kotlin-react-flutter-completion-66",
            "thirteen-language-complete-156",
        ):
            self.assertIn(f"`{route_set}`", document)
        self.assertIn("90 `limited`, 66 `research`, 0 `certified`", document)
        self.assertIn("`PASSED_LOCAL`", document)
        self.assertIn("`NOT_CERTIFIED`", document)
        self.assertIn("Independent verification: `NOT_RUN`", document)
        self.assertIn("External certification: `NOT_RUN`", document)

    def test_polyglot_runner_accepts_only_an_exact_directed_route(self):
        runner = load_polyglot_runner()
        self.assertEqual(runner.parse_route_key("cpp-to-java"), ("cpp", "java"))
        self.assertEqual(runner.parse_route_key("objc-to-go"), ("objc", "go"))
        self.assertEqual(runner.parse_route_key("java-to-php"), ("java", "php"))
        for invalid in (
            "python",
            "python-to-python",
            "Python-to-typescript",
            "java-to-javascript",
        ):
            with (
                self.subTest(invalid=invalid),
                self.assertRaises(argparse.ArgumentTypeError),
            ):
                runner.parse_route_key(invalid)

        for research_route in (
            "java-to-kotlin",
            "kotlin-to-react",
            "react-to-flutter",
            "flutter-to-kotlin",
        ):
            with (
                self.subTest(research_route=research_route),
                self.assertRaisesRegex(
                    argparse.ArgumentTypeError,
                    f"V3_ROUTE_RESEARCH_NOT_EXECUTABLE:{research_route}",
                ),
            ):
                runner.parse_route_key(research_route)

        with self.assertRaisesRegex(
            argparse.ArgumentTypeError,
            "LEGACY_ROUTE_IMMUTABLE_REEXECUTION_REQUIRES_NEW_PACK_VERSION:"
            "python-to-typescript",
        ):
            runner.parse_route_key("python-to-typescript")

        with (
            tempfile.TemporaryDirectory() as td,
            self.assertRaisesRegex(
                RuntimeError,
                "V3_ROUTE_RESEARCH_PACK_REQUIRES_CAMPAIGN:java-to-kotlin",
            ),
        ):
            runner.configure_route(Path(td), "java", "kotlin")

        self.assertEqual(len(runner.EXECUTABLE_MUTABLE_ROUTE_KEYS), 60)
        self.assertFalse(
            set(runner.EXECUTABLE_MUTABLE_ROUTE_KEYS)
            & set(runner.V3_EXACT_ROUTE_KEYS)
        )
        with self.assertRaisesRegex(
            RuntimeError,
            "V3_ROUTE_RESEARCH_PACK_REQUIRES_CAMPAIGN:java-to-kotlin",
        ):
            runner.preflight_route_set_execution(
                runner.PREPARABLE_ROUTE_SETS["thirteen-language-complete-156"]
            )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            route = root / "routes" / "java-to-kotlin"
            route.mkdir(parents=True)
            with self.assertRaisesRegex(
                RuntimeError,
                "V3_ROUTE_RESEARCH_PACK_REQUIRES_CAMPAIGN:java-to-kotlin",
            ):
                runner.execute_negative(
                    route,
                    root / "fixtures",
                    "java",
                    "kotlin",
                )
            with self.assertRaisesRegex(
                RuntimeError,
                "V3_ROUTE_RESEARCH_PACK_REQUIRES_CAMPAIGN:java-to-kotlin",
            ):
                runner.write_route_gate_documents(route, "java", "kotlin")
            self.assertEqual(list(route.iterdir()), [])

    def test_v3_direct_cli_rejects_before_any_side_effect(self):
        runner = load_polyglot_runner()
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td).resolve()
            sentinel = repo / "sentinel.bin"
            sentinel.write_bytes(b"unchanged\x00bytes")
            stderr = io.StringIO()
            with (
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "run_polyglot_routes.py",
                        "--repo-root",
                        str(repo),
                        "--route",
                        "java-to-kotlin",
                    ],
                ),
                mock.patch.object(sys, "stderr", stderr),
                mock.patch.object(runner, "execute_route") as execute_route,
                mock.patch.object(runner, "configure_route") as configure_route,
                mock.patch.object(
                    runner, "_transactional_write_bytes"
                ) as transactional_write,
                self.assertRaises(SystemExit) as raised,
            ):
                runner.main()
            self.assertEqual(raised.exception.code, 2)
            self.assertIn(
                "V3_ROUTE_RESEARCH_NOT_EXECUTABLE:java-to-kotlin",
                stderr.getvalue(),
            )
            execute_route.assert_not_called()
            configure_route.assert_not_called()
            transactional_write.assert_not_called()
            self.assertEqual(sentinel.read_bytes(), b"unchanged\x00bytes")

    def test_v3_route_sync_rejects_route_directory_symlink(self):
        runner = load_polyglot_runner()
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            external = Path(td) / "external" / "java-to-kotlin"
            (repo / "routes").mkdir(parents=True)
            external.mkdir(parents=True)
            (external / "route.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "route_key": "java-to-kotlin",
                        "version": "0.1.0",
                    }
                )
            )
            (repo / "routes" / "java-to-kotlin").symlink_to(
                external, target_is_directory=True
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "V3_ROUTE_PACK_MISSING_OR_UNSAFE:java-to-kotlin",
            ):
                runner.synchronize_v3_research_route_manifest(
                    repo, "java-to-kotlin"
                )

    def test_atomic_writer_rejects_hardlink_and_symlink_parent(self):
        runner = load_polyglot_runner()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            target = root / "target.json"
            alternate = root / "alternate.json"
            target.write_bytes(b"original\n")
            os.link(target, alternate)
            with self.assertRaisesRegex(RuntimeError, "ATOMIC_WRITE_TARGET_UNSAFE"):
                runner._atomic_write_bytes(target, b"replacement\n")
            self.assertEqual(target.read_bytes(), b"original\n")
            self.assertEqual(alternate.read_bytes(), b"original\n")

            external = root / "external"
            external.mkdir()
            unsafe_parent = root / "certification"
            unsafe_parent.symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "ATOMIC_WRITE_PARENT_UNSAFE"):
                runner._atomic_write_bytes(
                    unsafe_parent / "certification.json", b"blocked\n"
                )
            self.assertEqual(list(external.iterdir()), [])

    def test_stable_reader_rejects_intermediate_symlink_and_final_hardlink(self):
        runner = load_polyglot_runner()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            real = root / "real"
            real.mkdir()
            payload = real / "payload.bin"
            payload.write_bytes(b"immutable bytes\n")
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)

            with self.assertRaisesRegex(RuntimeError, "LEGACY_TEST_UNSAFE"):
                runner._stable_regular_file_bytes(
                    root,
                    alias / "payload.bin",
                    label="LEGACY_TEST",
                )

            hardlink = real / "payload-hardlink.bin"
            os.link(payload, hardlink)
            with self.assertRaisesRegex(RuntimeError, "LEGACY_TEST_UNSAFE"):
                runner._stable_regular_file_bytes(
                    root,
                    payload,
                    label="LEGACY_TEST",
                )

    def test_matrix_validator_rejects_linked_inventory_and_certification_dir(self):
        matrix = load_matrix_validator()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            routes = root / "routes"
            routes.mkdir()
            external_inventory = root / "external-inventory.json"
            external_inventory.write_text("{}\n")
            inventory = routes / "inventory.json"
            os.link(external_inventory, inventory)
            with (
                mock.patch.object(matrix, "ROOT", root),
                mock.patch.object(matrix, "INVENTORY", inventory),
                self.assertRaisesRegex(matrix.MatrixError, "ROUTE_INVENTORY_UNSAFE"),
            ):
                matrix.load_inventory()

            inventory.unlink()
            inventory.symlink_to(external_inventory)
            with (
                mock.patch.object(matrix, "ROOT", root),
                mock.patch.object(matrix, "INVENTORY", inventory),
                self.assertRaisesRegex(matrix.MatrixError, "ROUTE_INVENTORY_UNSAFE"),
            ):
                matrix.load_inventory()

            route = routes / "python-to-typescript"
            route.mkdir()
            external_certification = root / "external-certification"
            external_certification.mkdir()
            certification = route / "certification"
            certification.symlink_to(external_certification, target_is_directory=True)
            with self.assertRaisesRegex(
                matrix.MatrixError, "ROUTE_CERTIFICATION_DIRECTORY_UNSAFE"
            ):
                matrix.require_safe_directory(
                    routes,
                    certification,
                    "ROUTE_CERTIFICATION_DIRECTORY_UNSAFE",
                )

    def test_internal_route_mutation_boundaries_fail_closed_before_writes(self):
        runner = load_polyglot_runner()
        boundaries = {
            "formal": lambda repo, route, fixtures, source, target: (
                runner.build_formal_equivalence_evidence(
                    repo, route, source, target, {}, None
                )
            ),
            "scaffold": lambda repo, route, fixtures, source, target: (
                runner.write_not_run_route_scaffold(route, source, target)
            ),
            "corpus": lambda repo, route, fixtures, source, target: (
                runner.populate_corpus(route, fixtures, source)
            ),
            "module-corpus": lambda repo, route, fixtures, source, target: (
                runner.populate_module_corpus(route, fixtures, source)
            ),
            "module-execution": lambda repo, route, fixtures, source, target: (
                runner.execute_module_route(
                    repo, route, fixtures, source, target, None
                )
            ),
        }
        rejected = (
            (
                "java-to-kotlin",
                "java",
                "kotlin",
                "V3_ROUTE_RESEARCH_PACK_REQUIRES_CAMPAIGN",
            ),
            (
                "java-to-csharp",
                "java",
                "csharp",
                "LEGACY_ROUTE_IMMUTABLE_REEXECUTION_REQUIRES_NEW_PACK_VERSION",
            ),
            (
                "java-to-javascript",
                "java",
                "javascript",
                "INACTIVE_OR_UNDECLARED_ROUTE_EXECUTION",
            ),
        )
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td).resolve()
            fixtures = repo / "fixtures"
            for boundary_name, invoke in boundaries.items():
                for route_key, source, target, expected in rejected:
                    route = repo / boundary_name / route_key
                    route.mkdir(parents=True)
                    with self.subTest(boundary=boundary_name, route=route_key):
                        with self.assertRaisesRegex(RuntimeError, expected):
                            invoke(repo, route, fixtures, source, target)
                        self.assertEqual(list(route.iterdir()), [])

    def test_prepare_historical_set_rejects_before_any_side_effect(self):
        runner = load_polyglot_runner()
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td).resolve()
            sentinel = repo / "sentinel.bin"
            sentinel.write_bytes(b"unchanged\x00bytes")
            with (
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "run_polyglot_routes.py",
                        "--repo-root",
                        str(repo),
                        "--prepare-route-set",
                        "javascript-node26-completion-18",
                    ],
                ),
                mock.patch.object(runner, "legacy_campaign_authority") as legacy,
                mock.patch.object(
                    runner, "synchronize_v3_research_route_manifests"
                ) as synchronize,
                mock.patch.object(runner, "ensure_route_scaffold") as scaffold,
                mock.patch.object(runner, "configure_route") as configure,
                self.assertRaisesRegex(
                    RuntimeError,
                    "HISTORICAL_ROUTE_SET_READ_ONLY:javascript-node26-completion-18",
                ),
            ):
                runner.main()
            self.assertEqual(sentinel.read_bytes(), b"unchanged\x00bytes")
            legacy.assert_not_called()
            synchronize.assert_not_called()
            scaffold.assert_not_called()
            configure.assert_not_called()

    def test_prepare_preflights_every_mutable_route_directory_before_writes(self):
        runner = load_polyglot_runner()
        route_keys = runner.EXACT_ROUTE_SETS["cpp-objc-swift-java-exact-8"]
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td).resolve()
            routes = repo / "routes"
            routes.mkdir(parents=True)
            for route_key in route_keys[:-1]:
                (routes / route_key).mkdir()
            sentinel = routes / route_keys[0] / "sentinel.bin"
            sentinel.write_bytes(b"unchanged\n")
            external = repo / "external-route"
            external.mkdir()
            (routes / route_keys[-1]).symlink_to(external, target_is_directory=True)
            with (
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "run_polyglot_routes.py",
                        "--repo-root",
                        str(repo),
                        "--prepare-route-set",
                        "cpp-objc-swift-java-exact-8",
                    ],
                ),
                mock.patch.object(runner, "ensure_route_scaffold") as scaffold,
                mock.patch.object(runner, "configure_route") as configure,
                self.assertRaisesRegex(RuntimeError, "ROUTE_PREPARE_DIRECTORY_UNSAFE"),
            ):
                runner.main()
            self.assertEqual(sentinel.read_bytes(), b"unchanged\n")
            scaffold.assert_not_called()
            configure.assert_not_called()

    def test_write_inventory_failure_restores_v3_and_inventory_exact_bytes(self):
        runner = load_polyglot_runner()
        route_keys = ("java-to-kotlin", "kotlin-to-java")
        for failure_target in ("support-view", "inventory"):
            with (
                self.subTest(failure_target=failure_target),
                tempfile.TemporaryDirectory() as td,
            ):
                repo = Path(td).resolve()
                routes_root = repo / "routes"
                routes_root.mkdir(parents=True)
                existing_paths: list[Path] = []
                initially_missing_paths: list[Path] = []
                for index, route_key in enumerate(route_keys):
                    route = routes_root / route_key
                    certification = route / "certification"
                    route.mkdir(parents=True)
                    write_json(
                        route / "route.json",
                        {
                            "schema_version": 1,
                            "route_key": route_key,
                            "version": "0.1.0",
                            "original": index,
                        },
                    )
                    existing_paths.append(route / "route.json")
                    support_path = route / "support-matrix.json"
                    if index == 0:
                        support_path.write_bytes(b"original support exact bytes\x00\n")
                        certification.mkdir()
                        (certification / "evidence.json").write_bytes(
                            b"original evidence exact bytes\x00\n"
                        )
                        (certification / "certification.json").write_bytes(
                            b"original certification exact bytes\x00\n"
                        )
                        (certification / "support-matrix.md").write_bytes(
                            b"original support view exact bytes\x00\n"
                        )
                        existing_paths.extend(
                            (
                                support_path,
                                certification / "evidence.json",
                                certification / "certification.json",
                                certification / "support-matrix.md",
                            )
                        )
                    else:
                        initially_missing_paths.extend(
                            (
                                support_path,
                                certification / "evidence.json",
                                certification / "certification.json",
                                certification / "support-matrix.md",
                            )
                        )
                inventory_path = routes_root / "inventory.json"
                inventory_path.write_bytes(b"original inventory exact bytes\x00\n")
                existing_paths.append(inventory_path)
                originals = {path: path.read_bytes() for path in existing_paths}
                real_atomic_write = runner._atomic_write_bytes
                failed = False
                failing_path = (
                    routes_root
                    / route_keys[-1]
                    / "certification"
                    / "support-matrix.md"
                    if failure_target == "support-view"
                    else inventory_path
                )

                def fail_selected_write(path: Path, content: bytes) -> None:
                    nonlocal failed
                    if path == failing_path:
                        failed = True
                        raise OSError("injected transaction failure")
                    real_atomic_write(path, content)

                with (
                    mock.patch.object(runner, "V3_EXACT_ROUTE_KEYS", route_keys),
                    mock.patch.object(runner, "EVIDENCED_ROUTE_KEYS", route_keys),
                    mock.patch.object(
                        runner, "ALL_DECLARED_ROUTE_KEYS", route_keys
                    ),
                    mock.patch.object(
                        runner,
                        "legacy_campaign_authority",
                        return_value={"authority_sha256": "sha256:test"},
                    ),
                    mock.patch.object(
                        runner,
                        "provenance_route_set",
                        return_value="kotlin-react-flutter-completion-66",
                    ),
                    mock.patch.object(
                        runner,
                        "_atomic_write_bytes",
                        side_effect=fail_selected_write,
                    ),
                    self.assertRaisesRegex(
                        OSError, "injected transaction failure"
                    ),
                ):
                    runner.write_inventory(repo)
                self.assertTrue(failed)
                self.assertEqual(
                    {path: path.read_bytes() for path in existing_paths},
                    originals,
                )
                self.assertTrue(
                    all(not path.exists() for path in initially_missing_paths)
                )
                self.assertFalse(
                    (routes_root / route_keys[-1] / "certification").exists()
                )
                self.assertEqual(list(routes_root.rglob("*.tmp")), [])

    def test_support_matrix_markdown_escapes_content_and_rejects_invalid_status(self):
        runner = load_polyglot_runner()
        document = {
            "schema_version": 1,
            "route_key": "java-to-kotlin",
            "capabilities": [
                {
                    "id": "unsafe](https://example.invalid)",
                    "status": "experimental",
                    "strategy": "literal `code` fence",
                    "reason": "**not emphasis** | not a table",
                    "evidence_refs": ["artifact`close"],
                }
            ],
        }
        source_bytes = runner._json_bytes(document)
        rendered = runner.support_matrix_markdown_bytes(
            "java-to-kotlin",
            source_bytes,
            document,
        ).decode("utf-8")

        self.assertIn(r"unsafe\]\(https://example.invalid\)", rendered)
        self.assertIn(r"\*\*not emphasis\*\* \| not a table", rendered)
        self.assertIn("``literal `code` fence``", rendered)
        self.assertIn("``artifact`close``", rendered)

        invalid_status = copy.deepcopy(document)
        invalid_status["capabilities"][0]["status"] = "invented"
        with self.assertRaisesRegex(
            ValueError,
            "SUPPORT_MATRIX_CAPABILITY_INVALID:java-to-kotlin",
        ):
            runner.support_matrix_markdown_bytes(
                "java-to-kotlin",
                runner._json_bytes(invalid_status),
                invalid_status,
            )

        unevidenced_certified = copy.deepcopy(document)
        unevidenced_certified["capabilities"][0]["status"] = "certified"
        unevidenced_certified["capabilities"][0]["evidence_refs"] = []
        with self.assertRaisesRegex(
            ValueError,
            "SUPPORT_MATRIX_CAPABILITY_INVALID:java-to-kotlin",
        ):
            runner.support_matrix_markdown_bytes(
                "java-to-kotlin",
                runner._json_bytes(unevidenced_certified),
                unevidenced_certified,
            )

    def test_v3_first_materialization_creates_exact_non_vacuous_not_run_contract(
        self,
    ):
        from jsonschema import Draft202012Validator

        runner = load_polyglot_runner()
        matrix = load_matrix_validator()
        with tempfile.TemporaryDirectory() as td:
            repo = (Path(td) / "repo").resolve()
            route = repo / "routes" / "java-to-kotlin"
            certification_root = route / "certification"
            route.mkdir(parents=True)
            write_json(
                route / "route.json",
                {
                    "schema_version": 1,
                    "route_key": "java-to-kotlin",
                    "version": "0.1.0",
                },
            )
            self.assertFalse(certification_root.exists())

            runner.synchronize_v3_research_route_manifest(repo, "java-to-kotlin")
            manifest = json.loads((route / "route.json").read_text())
            support_path = route / "support-matrix.json"
            support_bytes = support_path.read_bytes()
            support = json.loads(support_bytes)
            support_view_path = certification_root / "support-matrix.md"
            support_view = support_view_path.read_bytes()
            evidence = json.loads(
                (certification_root / "evidence.json").read_text()
            )
            certification = json.loads(
                (certification_root / "certification.json").read_text()
            )

            self.assertEqual(
                evidence,
                runner.v3_research_evidence_document("java-to-kotlin"),
            )
            self.assertEqual(
                certification,
                runner.v3_research_certification_document("java-to-kotlin"),
            )
            self.assertEqual(
                support,
                runner.v3_research_support_document("java-to-kotlin"),
            )
            self.assertEqual(
                support_view,
                runner.support_matrix_markdown_bytes(
                    "java-to-kotlin",
                    support_bytes,
                    support,
                ),
            )
            self.assertEqual(
                certification["gate_results"],
                {
                    "local_execution": "NOT_RUN",
                    "external_execution": "NOT_RUN",
                    "independent_verification": "NOT_RUN",
                },
            )
            self.assertTrue(certification["gate_results"])
            self.assertTrue(
                all(value is None for value in evidence["metrics"].values())
            )
            matrix.check_v3_research_route_documents(
                "java-to-kotlin", manifest, support, certification, evidence
            )
            runner.verify_route_set_read_only(
                repo,
                "single-v3-research-route",
                ("java-to-kotlin",),
            )
            support_view_path.write_bytes(support_view + b"tampered\n")
            with self.assertRaisesRegex(
                RuntimeError,
                "ROUTE_SUPPORT_MATRIX_VIEW_DRIFT:java-to-kotlin",
            ):
                runner.verify_route_set_read_only(
                    repo,
                    "single-v3-research-route",
                    ("java-to-kotlin",),
                )
            support_view_path.write_bytes(support_view)

            manifest_schema = json.loads(
                (
                    ROOT
                    / "schemas"
                    / "batch29"
                    / "route-manifest.schema.json"
                ).read_text()
            )
            certification_schema = json.loads(
                (
                    ROOT
                    / "schemas"
                    / "batch29"
                    / "route-certification.schema.json"
                ).read_text()
            )
            support_schema = json.loads(
                (
                    ROOT
                    / "schemas"
                    / "batch29"
                    / "support-matrix.schema.json"
                ).read_text()
            )
            Draft202012Validator.check_schema(manifest_schema)
            Draft202012Validator.check_schema(certification_schema)
            Draft202012Validator.check_schema(support_schema)
            manifest_validator = Draft202012Validator(manifest_schema)
            certification_validator = Draft202012Validator(certification_schema)
            support_validator = Draft202012Validator(support_schema)
            self.assertEqual(list(manifest_validator.iter_errors(manifest)), [])
            self.assertEqual(
                list(certification_validator.iter_errors(certification)), []
            )
            self.assertEqual(list(support_validator.iter_errors(support)), [])

            support_tampers = []
            empty_support = copy.deepcopy(support)
            empty_support["capabilities"] = []
            support_tampers.append(("empty", empty_support))
            promoted_support = copy.deepcopy(support)
            promoted_support["capabilities"][0]["status"] = "supported"
            support_tampers.append(("promoted", promoted_support))
            unexplained_support = copy.deepcopy(support)
            unexplained_support["capabilities"][0]["reason"] = ""
            support_tampers.append(("empty-reason", unexplained_support))
            evidenced_support = copy.deepcopy(support)
            evidenced_support["capabilities"][0]["evidence_refs"] = [
                "certification/forged.json"
            ]
            support_tampers.append(("forged-evidence", evidenced_support))
            reordered_support = copy.deepcopy(support)
            reordered_support["capabilities"] = list(
                reversed(reordered_support["capabilities"])
            )
            support_tampers.append(("reordered", reordered_support))
            for label, tampered_support in support_tampers:
                with (
                    self.subTest(support_tamper=label),
                    self.assertRaisesRegex(
                        matrix.MatrixError,
                        "V3_ROUTE_SUPPORT_DRIFT:java-to-kotlin",
                    ),
                ):
                    matrix.check_v3_research_route_documents(
                        "java-to-kotlin",
                        manifest,
                        tampered_support,
                        certification,
                        evidence,
                    )

            empty_versions = copy.deepcopy(manifest)
            empty_versions["source"]["versions"] = []
            self.assertTrue(list(manifest_validator.iter_errors(empty_versions)))
            blank_version = copy.deepcopy(manifest)
            blank_version["target"]["versions"] = ["   "]
            self.assertTrue(list(manifest_validator.iter_errors(blank_version)))
            blank_route_version = copy.deepcopy(certification)
            blank_route_version["route_version"] = "   "
            self.assertTrue(
                list(certification_validator.iter_errors(blank_route_version))
            )
            forged_decision = copy.deepcopy(certification)
            forged_decision["certification_decision"] = "CERTIFIED"
            self.assertTrue(
                list(certification_validator.iter_errors(forged_decision))
            )

            vacuous_gate = copy.deepcopy(certification)
            vacuous_gate["gate_results"] = {}
            self.assertTrue(
                list(certification_validator.iter_errors(vacuous_gate))
            )
            with self.assertRaisesRegex(
                matrix.MatrixError,
                "V3_ROUTE_CERTIFICATION_OVERCLAIM:java-to-kotlin",
            ):
                matrix.check_v3_research_route_documents(
                    "java-to-kotlin",
                    manifest,
                    support,
                    vacuous_gate,
                    evidence,
                )

            missing_execution = copy.deepcopy(evidence)
            del missing_execution["execution_status"]
            with self.assertRaisesRegex(
                matrix.MatrixError,
                "V3_ROUTE_RAW_EVIDENCE_OVERCLAIM:java-to-kotlin",
            ):
                matrix.check_v3_research_route_documents(
                    "java-to-kotlin",
                    manifest,
                    support,
                    certification,
                    missing_execution,
                )

    def test_local_route_status_requires_current_engine_source_bytes(self):
        runner = load_polyglot_runner()
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td).resolve()
            route = repo / "routes" / "python-to-typescript"
            live = repo / "engine.py"
            captured = (
                route
                / "certification"
                / "formal-artifacts"
                / "engine-sources"
                / "engine.py"
            )
            manifest = (
                route
                / "certification"
                / "formal-artifacts"
                / "engine-source-manifest.json"
            )
            captured.parent.mkdir(parents=True)
            payload = b"original engine bytes\n"
            live.write_bytes(payload)
            captured.write_bytes(payload)
            write_json(
                manifest,
                {
                    "schema_version": 1,
                    "kind": "polyglot-route-engine-source-bundle",
                    "file_count": 1,
                    "files": [
                        {
                            "repository_path": "engine.py",
                            "captured_path": (
                                "certification/formal-artifacts/engine-sources/engine.py"
                            ),
                            "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
                            "bytes": len(payload),
                        }
                    ],
                },
            )

            self.assertEqual(
                runner.current_engine_source_binding(repo, route),
                (False, "ENGINE_SOURCE_MANIFEST_INVALID"),
            )

    def test_single_route_mode_executes_and_gates_only_the_selected_route(self):
        runner = load_polyglot_runner()
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(runner, "execute_route") as execute,
            mock.patch.object(runner, "run_route_checks", return_value=0) as checks,
            mock.patch.object(
                sys,
                "argv",
                [
                    "run_polyglot_routes.py",
                    "--repo-root",
                    td,
                    "--route",
                    "python-to-cpp",
                ],
            ),
        ):
            self.assertEqual(runner.main(), 0)
        execute.assert_called_once()
        self.assertEqual(execute.call_args.args[2:], ("python", "cpp"))
        checks.assert_called_once_with(
            Path(td).resolve(),
            Path(td).resolve() / "routes" / "python-to-cpp",
        )

    def test_persisted_artifact_manifest_is_complete_and_non_destructive(self):
        runner = load_polyglot_runner()
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td).resolve()
            route = repo / "routes" / "python-to-typescript"
            destination = route / "certification" / "artifacts" / "development"
            destination.mkdir(parents=True)
            user_file = destination / "user-note.txt"
            user_file.write_text("preserve me\n")
            generated = repo / "generated"
            (generated / "nested").mkdir(parents=True)
            (generated / "migrated.ts").write_text("export function f() { return 1 }\n")
            (generated / "semantic-ir.json").write_text('{"schema_version":"1.0.0"}\n')
            (generated / "nested" / "future-engine-output.bin").write_bytes(b"future")
            (generated / "bin").mkdir()
            (generated / "bin" / "RouteHarness.dll").write_bytes(b"binary")
            (generated / "route_harness").write_bytes(b"native")

            reference = runner.persist_artifact_directory(
                repo, route, "development", generated
            )

            self.assertTrue(
                user_file.is_file(), "managed refresh deleted an unrelated file"
            )
            manifest_path = route / str(reference["path"])
            self.assertEqual(reference["sha256"], digest(manifest_path))
            self.assertEqual(reference["bytes"], manifest_path.stat().st_size)
            manifest = json.loads(manifest_path.read_text())
            listed = {item["path"] for item in manifest["files"]}
            self.assertEqual(
                listed,
                {
                    "migrated.ts",
                    "semantic-ir.json",
                },
            )
            self.assertNotIn("user-note.txt", listed)
            self.assertFalse(
                (destination / "nested" / "future-engine-output.bin").exists()
            )
            self.assertFalse((destination / "bin" / "RouteHarness.dll").exists())
            self.assertFalse((destination / "route_harness").exists())
            self.assertIn("bin/**", manifest["excluded_rebuildable_patterns"])
            self.assertEqual(
                set(manifest["excluded_files"]),
                {
                    "bin/RouteHarness.dll",
                    "nested/future-engine-output.bin",
                    "route_harness",
                },
            )

    def test_execute_route_persists_every_engine_output_and_binds_manifests(self):
        runner = load_polyglot_runner()
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td).resolve()
            route = repo / "routes" / "python-to-cpp"
            shutil.copytree(ROOT / "routes" / "python-to-cpp", route)
            fixtures = repo / "engines" / "polyglot-route-engine" / "fixtures"
            fixtures_by_corpus = {
                "development": (
                    fixtures / "python" / "pricing.py",
                    fixtures / "behavior-cases.json",
                ),
                "holdout": (
                    fixtures / "holdout" / "python" / "clamp.py",
                    fixtures / "holdout" / "cases.json",
                ),
                "real-repository": (
                    fixtures / "representative" / "python" / "difference.py",
                    fixtures / "representative" / "cases.json",
                ),
            }
            for source, cases in fixtures_by_corpus.values():
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(
                    "def fixture(a: int, b: int) -> int:\n    return a + b\n"
                )
                cases.parent.mkdir(parents=True, exist_ok=True)
                cases.write_text('[{"args":[1,2],"expected":3}]\n')

            def fake_migrate(
                source, source_language, target_language, function_name, cases, output
            ):
                output.mkdir(parents=True, exist_ok=True)
                (output / "migrated.cpp").write_text("int migrated() { return 3; }\n")
                (output / "route_harness.cpp").write_text("// harness\n")
                (output / "semantic-ir.json").write_text('{"schema_version":"1.0.0"}\n')
                (output / "engine-new-output").mkdir()
                (output / "engine-new-output" / "trace.log").write_text("complete\n")
                return {
                    "schema_version": "1.0.0",
                    "status": "PASSED",
                    "route": f"{source_language}-to-{target_language}",
                    "scope": "typed-pure-function-v1",
                    "source_map_coverage": 1.0,
                    "behavior_case_count": 1,
                    "behavior_pass_rate": 1.0,
                    "critical_unknown_semantics": 0,
                    "validation": {"status": "PASSED", "commands": []},
                }

            def fake_negative(route_path, fixtures_path, source, target):
                relative = "certification/local-negative-evidence.json"
                (route_path / "certification").mkdir(parents=True, exist_ok=True)
                (route_path / relative).write_text(
                    json.dumps(
                        {
                            "status": "PASSED",
                            "expected_result": "BLOCKED",
                            "test_integrity": "PRESERVED",
                        }
                    )
                    + "\n"
                )
                return relative

            def fake_formal(
                repo_path,
                route_path,
                source,
                target,
                reports,
                swift_analyzer_receipt_path,
            ):
                del repo_path, source, target, swift_analyzer_receipt_path
                self.assertEqual(set(reports), set(runner.CORPORA))
                formal = route_path / "certification" / "formal-equivalence.json"
                formal.write_text('{"schema_version":2}\n')
                return runner.artifact_ref(route_path, formal)

            with (
                mock.patch.object(runner, "migrate", side_effect=fake_migrate),
                mock.patch.object(
                    runner, "execute_negative", side_effect=fake_negative
                ),
                mock.patch.object(
                    runner,
                    "build_formal_equivalence_evidence",
                    side_effect=fake_formal,
                ),
            ):
                runner.execute_route(repo, fixtures, "python", "cpp")

            aggregate = json.loads(
                (route / "certification" / "evidence.json").read_text()
            )
            self.assertEqual(
                aggregate["formal_equivalence"]["path"],
                "certification/formal-equivalence.json",
            )
            self.assertEqual(set(aggregate["artifact_manifests"]), set(runner.CORPORA))
            self.assertEqual(len(aggregate["artifact_refs"]), 3)
            certification = json.loads(
                (route / "certification" / "certification.json").read_text()
            )
            self.assertEqual(certification["evidence_format"], 2)
            self.assertEqual(
                certification["formal_equivalence"], aggregate["formal_equivalence"]
            )
            for corpus, reference in aggregate["artifact_manifests"].items():
                manifest_path = route / reference["path"]
                self.assertEqual(reference["sha256"], digest(manifest_path))
                self.assertEqual(reference["bytes"], manifest_path.stat().st_size)
                manifest = json.loads(manifest_path.read_text())
                listed = {item["path"] for item in manifest["files"]}
                self.assertTrue(
                    {
                        "migrated.cpp",
                        "route_harness.cpp",
                        "semantic-ir.json",
                        "route-evidence.json",
                        "engine-new-output/trace.log",
                        "inputs/cases.json",
                    }
                    <= listed
                )
                local_name = {
                    "development": "local-development-evidence.json",
                    "holdout": "local-holdout-evidence.json",
                    "real-repository": "local-representative-evidence.json",
                }[corpus]
                local = json.loads((route / "certification" / local_name).read_text())
                self.assertEqual(local["artifact_manifest"], reference)

    def test_route_checks_do_not_duplicate_the_gate_validator_replay(self):
        runner = load_polyglot_runner()
        route = ROOT / "routes" / "cpp-to-java"
        completed = subprocess.CompletedProcess([], 0)
        with mock.patch.object(
            runner.subprocess, "run", return_value=completed
        ) as invoked:
            self.assertEqual(runner.run_route_checks(ROOT, route), 0)
        invoked.assert_called_once_with(
            [
                sys.executable,
                str(ROOT / "scripts" / "batch29" / "run_route_gate.py"),
                str(route),
            ],
            cwd=ROOT,
            check=False,
        )

    def test_specialized_negative_replay_rejects_positive_source_with_self_consistent_ref(
        self,
    ):
        runner = load_polyglot_runner()
        gate = load_route_gate()
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "cpp-to-objc"
            shutil.copytree(ROOT / "routes" / "cpp-to-objc", route)
            reference = runner.execute_specialized_negative(
                route,
                ROOT / "engines" / "polyglot-route-engine" / "fixtures",
                "cpp",
                "objc",
            )
            aggregate = {"negative_runs": [reference]}
            failures: list[str] = []
            gate.validate_negative_refs(failures, route, aggregate)
            self.assertEqual(failures, [])

            negative_path = route / reference
            negative = json.loads(negative_path.read_text())
            string_case = next(
                item
                for item in negative["cases"]
                if item["case_id"] == "specialized-string-semantics-unsupported"
            )
            source_ref = next(
                item for item in string_case["input_refs"] if item["role"] == "source"
            )
            development_manifest = json.loads(
                (route / "corpus" / "development" / "manifest.json").read_text()
            )
            positive_source = (
                route / "corpus" / "development" / development_manifest["source_file"]
            )
            bound_negative_source = route / source_ref["path"]
            shutil.copyfile(positive_source, bound_negative_source)
            source_ref.update(
                {
                    "sha256": digest(bound_negative_source),
                    "bytes": bound_negative_source.stat().st_size,
                }
            )
            string_case["native_analysis"] = "SELF_REPORTED_ONLY"
            write_json(negative_path, negative)

            tampered_failures: list[str] = []
            gate.validate_negative_refs(
                tampered_failures,
                route,
                aggregate,
            )
            self.assertTrue(
                any(
                    "fresh RouteError reason is not exact" in failure
                    or "unexpectedly passed fresh replay" in failure
                    for failure in tampered_failures
                ),
                tampered_failures,
            )
            self.assertTrue(
                any(
                    "observed_reason differs from fresh replay" in failure
                    or "unexpectedly passed fresh replay" in failure
                    for failure in tampered_failures
                ),
                tampered_failures,
            )
            self.assertTrue(
                any(
                    "did not preserve fail-closed status" in failure
                    for failure in tampered_failures
                ),
                tampered_failures,
            )

    def test_negative_replay_writes_reachable_gate_report_and_readme(self):
        runner = load_polyglot_runner()
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td).resolve()
            route = repo / "routes" / "python-to-typescript"
            (route / "certification").mkdir(parents=True)
            fixtures = repo / "fixtures"
            source = fixtures / "python" / "pricing.py"
            cases = fixtures / "behavior-cases.json"
            source.parent.mkdir(parents=True)
            source.write_text(
                "def calculate(a: int, b: int) -> int:\n    return a + b\n"
            )
            cases.write_text('[{"args":[1,2],"expected":3}]\n')
            with mock.patch.object(
                runner,
                "migrate",
                side_effect=runner.RouteError("FUNCTION_NOT_FOUND"),
            ):
                reference = runner.execute_negative(
                    route, fixtures, "python", "typescript"
                )
            self.assertEqual(reference, "certification/local-negative-evidence.json")
            self.assertTrue((route / "certification" / "gate-report.md").is_file())
            self.assertTrue((route / "README.md").is_file())
            self.assertIn(
                "NOT_RUN", (route / "certification" / "gate-report.md").read_text()
            )


if __name__ == "__main__":
    unittest.main()

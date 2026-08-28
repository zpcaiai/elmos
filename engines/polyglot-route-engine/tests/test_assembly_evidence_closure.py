"""Focused adversarial tests for repository child-evidence assembly closure."""

from __future__ import annotations

import copy
import hashlib
import json
from functools import cache
from pathlib import Path
from typing import Any, cast

import pytest

from elmos_polyglot_route import assembly as assembly_module
from elmos_polyglot_route.assembly import (
    assemble_project as _assemble_project,
)
from elmos_polyglot_route.assembly import (
    verify_archived_assembly_closure,
)
from elmos_polyglot_route.equivalence import behavior_equivalence
from elmos_polyglot_route.identifier_hygiene import (
    identifier_plan_bytes,
    plan_identifiers,
    repository_work_unit_namespace,
    standalone_artifact_unit_namespace,
    target_function_view,
)
from elmos_polyglot_route.models import (
    Language,
    RouteError,
    SemanticIR,
    repository_language_lifecycle,
)
from elmos_polyglot_route.toolchains import exact_toolchain


def assemble_project(
    report: dict[str, Any],
    batch_output: Path,
    destination: Path,
) -> dict[str, Any]:
    """Authorize archived JavaScript only inside explicit historical fixtures."""

    return _assemble_project(
        report,
        batch_output,
        destination,
        allow_deprecated_replay=(report.get("source_language") == "javascript"),
    )


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


@cache
def _current_toolchain_version(language: Language) -> str:
    return exact_toolchain(language).version


def _fixture(
    tmp_path: Path,
    *,
    source_language: Language = "python",
    source_path: str = "src/identity.py",
    javascript_descriptor: bool = False,
) -> tuple[dict[str, Any], Path]:
    unit_id = "WU-00001"
    target_language: Language = "typescript" if source_language != "typescript" else "python"
    source_name = Path(source_path).name
    source_content = b"fixture-source-bytes\n"
    source_sha256 = _digest(source_content)
    source_sha256_raw = source_sha256.removeprefix("sha256:")
    source_ir = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": source_language,
            "source_file": source_name,
            "analyzer": "focused-fixture-analyzer",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "identity",
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
    namespace = repository_work_unit_namespace(
        repository_snapshot_sha256="sha256:" + "a" * 64,
        work_unit_id=unit_id,
        source_logical_path=source_path,
        source_sha256=source_sha256,
    )
    plan = plan_identifiers(source_ir, target_language, unit_namespace=namespace)
    target_function = target_function_view(source_ir, source_ir.functions[0], plan)
    target_name = "migrated.ts" if target_language == "typescript" else "migrated.py"
    target_content = (
        f"export function {target_function.name}(value: bigint): bigint {{ return value; }}\n"
        if target_language == "typescript"
        else f"def {target_function.name}(value: int) -> int:\n    return value\n"
    ).encode()
    observation = {
        "case_id": 0,
        "status": "RETURNED",
        "value": 7,
        "encoding": "json",
        "raw": '{"case_id":0,"value":7}',
    }
    behavior = {
        "schema_version": "1.0.0",
        "kind": "elmos.behavior-equivalence",
        "status": "PASSED",
        "case_count": 1,
        "pass_count": 1,
        "source_runtime_pass_count": 1,
        "target_runtime_pass_count": 1,
        "source_runtime_passed": True,
        "target_runtime_passed": True,
        "oracle_conflict_count": 0,
        "counterexample_count": 0,
        "results": [
            {
                "case_id": 0,
                "arguments_sha256": _digest(_canonical([7])),
                "canonical": {"status": "RETURNED", "value": 7, "error": None},
                "source_native": observation,
                "target_native": observation,
                "independent_expected": 7,
                "status": "PASSED",
            }
        ],
        "counterexamples": [],
    }
    behavior_bytes = json.dumps(behavior, indent=2, sort_keys=True).encode() + b"\n"
    source_record: dict[str, Any] = {
        "path": source_name,
        "sha256": source_sha256,
        "language": source_language,
        "function_name": "identity",
    }
    source_validation: dict[str, Any] = {
        "status": "PASSED",
        "case_count": 1,
        "observations": [observation],
    }
    descriptor_bytes: bytes | None = None
    descriptor: dict[str, Any] | None = None
    if javascript_descriptor:
        descriptor_bytes = b'{"type":"module"}\n'
        descriptor = {
            "logical_path": "../package.json" if "/" in source_path else "package.json",
            "snapshot_path": "source/package.json",
            "artifact_path": "source-javascript-esm-package.json",
            "sha256": _digest(descriptor_bytes),
            "bytes": len(descriptor_bytes),
            "type": "module",
        }
        source_record["javascript_esm_descriptor"] = descriptor
        source_validation["javascript_esm_descriptor"] = {
            key: descriptor[key] for key in ("logical_path", "sha256", "bytes", "type")
        }
        source_validation["javascript_esm_descriptor_observation"] = {
            "observed_origin_path": "/private/snapshot/source/package.json"
        }
    evidence: dict[str, Any] = {
        "schema_version": "1.0.0",
        "status": "PASSED_LOCAL_UNCERTIFIED",
        "repository_execution_mode": True,
        "behavior_case_count": 1,
        "behavior_pass_rate": 1.0,
        "source": source_record,
        "target": {
            "path": target_name,
            "sha256": _digest(target_content),
            "language": target_language,
            "function_name": target_function.name,
        },
        "identifier_hygiene": {
            "status": "PASSED",
            "plan_path": "identifier-plan.json",
            "plan_sha256": plan.digest,
            "source_function_name": "identity",
            "target_function_name": target_function.name,
            "unit_namespace": namespace.to_mapping(),
            "unit_namespace_sha256": namespace.digest,
        },
        "source_validation": source_validation,
        "validation": {"status": "PASSED", "case_count": 1, "observations": [observation]},
        "behavior_equivalence": {
            "status": "PASSED",
            "case_count": 1,
            "pass_count": 1,
            "source_runtime_passed": True,
            "target_runtime_passed": True,
            "oracle_conflict_count": 0,
            "artifact_path": "behavior-equivalence.json",
            "artifact_sha256": _digest(behavior_bytes),
        },
    }
    if descriptor is not None:
        evidence["javascript_esm_descriptor"] = descriptor
        evidence["javascript_esm_descriptor_observation"] = {
            "observed_origin_path": "/private/snapshot/source/package.json"
        }
    evidence_bytes = json.dumps(evidence, indent=2, sort_keys=True).encode() + b"\n"
    unit_directory = tmp_path / "batch" / "units" / unit_id
    unit_directory.mkdir(parents=True)
    (unit_directory / target_name).write_bytes(target_content)
    (unit_directory / "source-semantic-ir.json").write_text(
        json.dumps(source_ir.to_mapping(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (unit_directory / "identifier-plan.json").write_bytes(identifier_plan_bytes(plan))
    (unit_directory / "behavior-equivalence.json").write_bytes(behavior_bytes)
    (unit_directory / "route-evidence.json").write_bytes(evidence_bytes)
    if descriptor_bytes is not None:
        (unit_directory / "source-javascript-esm-package.json").write_bytes(descriptor_bytes)
    unit = {
        "id": unit_id,
        "source_path": source_path,
        "status": "PASSED",
        "function_name": "identity",
        "target_function_name": target_function.name,
        "identifier_plan_path": "identifier-plan.json",
        "identifier_plan_sha256": plan.digest,
        "target_path": target_name,
        "target_sha256": _digest(target_content),
        "evidence_path": f"units/{unit_id}/route-evidence.json",
        "evidence_sha256": _digest(evidence_bytes),
        "behavior_case_count": 1,
        "checkpoint_identity": {
            "snapshot_sha256": "a" * 64,
            "source_path": source_path,
            "source_sha256": source_sha256_raw,
            "function_name": "identity",
            "verdict": "READY",
            "identifier_unit_namespace": namespace.to_mapping(),
            "identifier_unit_namespace_sha256": namespace.digest,
        },
        "identifier_unit_namespace": namespace.to_mapping(),
        "identifier_unit_namespace_sha256": namespace.digest,
    }
    report = {
        "schema_version": "1.0.0",
        "kind": "elmos.repository-batch-report",
        "language_lifecycle": repository_language_lifecycle(
            source_language,
            target_language,
        ),
        "status": "COMPLETE",
        "repository_ref": "local:focused-child-evidence",
        "snapshot_sha256": "a" * 64,
        "route_id": f"{source_language}-to-{target_language}",
        "source_language": source_language,
        "target_language": target_language,
        "work_unit_count": 1,
        "selected_count": 1,
        "attempted_count": 1,
        "unattempted_count": 0,
        "status_counts": {"PASSED": 1},
        "units": [unit],
    }
    return report, tmp_path / "batch"


def _rewrite_route_evidence(
    report: dict[str, Any],
    batch: Path,
    transform: Any,
) -> dict[str, Any]:
    path = batch / "units" / "WU-00001" / "route-evidence.json"
    raw_payload = json.loads(path.read_bytes())
    if not isinstance(raw_payload, dict):
        raise AssertionError("focused fixture route evidence must be an object")
    payload: dict[str, Any] = raw_payload
    transform(payload)
    content = json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n"
    path.write_bytes(content)
    report["units"][0]["evidence_sha256"] = _digest(content)
    return payload


def _rewrite_identifier_namespace(
    report: dict[str, Any],
    batch: Path,
    namespace: Any,
) -> None:
    unit = report["units"][0]
    unit_directory = batch / "units" / unit["id"]
    source_ir = SemanticIR.from_mapping(json.loads((unit_directory / "source-semantic-ir.json").read_bytes()))
    plan = plan_identifiers(source_ir, cast(Language, report["target_language"]), unit_namespace=namespace)
    plan_bytes = identifier_plan_bytes(plan)
    (unit_directory / "identifier-plan.json").write_bytes(plan_bytes)
    unit.update(
        {
            "identifier_plan_sha256": plan.digest,
            "identifier_unit_namespace": namespace.to_mapping(),
            "identifier_unit_namespace_sha256": namespace.digest,
        }
    )
    unit["checkpoint_identity"].update(
        {
            "identifier_unit_namespace": namespace.to_mapping(),
            "identifier_unit_namespace_sha256": namespace.digest,
        }
    )

    def rewrite(evidence: dict[str, Any]) -> None:
        evidence["identifier_hygiene"].update(
            {
                "plan_sha256": plan.digest,
                "unit_namespace": namespace.to_mapping(),
                "unit_namespace_sha256": namespace.digest,
            }
        )

    _rewrite_route_evidence(report, batch, rewrite)


def _archive_view(
    manifest: dict[str, Any],
    assembled: Path,
    batch: Path,
) -> tuple[bytes, dict[str, bytes]]:
    archived_manifest = copy.deepcopy(manifest)
    archived_manifest["build_verification_status"] = "PASSED"
    archived_manifest["build_verification"] = {
        "toolchain_language": manifest["target_language"],
        "toolchain_version": _current_toolchain_version(
            cast(Language, manifest["target_language"])
        ),
        "commands": [{"command": ["fixture-build"], "stdout": "", "stderr": ""}],
    }
    manifest_bytes = json.dumps(archived_manifest, indent=2, sort_keys=True).encode() + b"\n"
    contents = {
        f"assembled/{path.relative_to(assembled).as_posix()}": path.read_bytes()
        for path in assembled.rglob("*")
        if path.is_file()
    }
    contents["assembled/assembly-manifest.json"] = manifest_bytes
    contents.update(
        {
            f"batch/{path.relative_to(batch).as_posix()}": path.read_bytes()
            for path in batch.rglob("*")
            if path.is_file()
        }
    )
    return manifest_bytes, contents


def test_assembly_copies_and_binds_verified_behavior_evidence(tmp_path: Path) -> None:
    report, batch = _fixture(tmp_path)

    manifest = assemble_project(report, batch, tmp_path / "assembled")

    assert manifest["verified_evidence_artifact_count"] == 5
    assert [record["role"] for record in manifest["verified_evidence_artifacts"]] == [
        "route-evidence",
        "behavior-equivalence",
        "source-semantic-ir",
        "identifier-plan",
        "emitted-target",
    ]
    for record in manifest["verified_evidence_artifacts"]:
        copied = tmp_path / "assembled" / record["assembled_path"]
        source = batch / record["source_path"]
        assert copied.read_bytes() == source.read_bytes()
        assert len(copied.read_bytes()) == record["bytes"]
        assert _digest(copied.read_bytes()) == record["sha256"]


def test_kotlin_assembly_binds_nested_source_validation_toolchain(tmp_path: Path) -> None:
    report, batch = _fixture(
        tmp_path,
        source_language="kotlin",
        source_path="src/identity.kt",
    )
    expected_toolchain = assembly_module._exact_toolchain_identity(
        exact_toolchain("kotlin")
    )
    _rewrite_route_evidence(
        report,
        batch,
        lambda evidence: evidence["source_validation"].update(
            {"toolchain": expected_toolchain}
        ),
    )

    manifest = assemble_project(report, batch, tmp_path / "assembled")

    assert manifest["included_unit_count"] == 1
    assert manifest["source_language"] == "kotlin"


def test_assembly_accepts_typed_number_evidence_from_json_integer_oracle() -> None:
    function = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "typescript",
            "source_file": "identity.ts",
            "analyzer": "focused-fixture-analyzer",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "identity",
                    "parameters": [{"name": "value", "type": "number"}],
                    "return_type": "number",
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
    ).functions[0]
    observation = {
        "case_id": 0,
        "status": "RETURNED",
        "value": 5.0,
        "encoding": "json",
        "raw": '{"case_id":0,"value":5.0}',
    }
    behavior = behavior_equivalence(
        function,
        [{"args": [5.0], "expected": 5}],
        [observation],
        [observation],
    )
    behavior_bytes = json.dumps(behavior, indent=2, sort_keys=True).encode() + b"\n"
    evidence = {
        "behavior_case_count": 1,
        "source": {},
        "source_validation": {"observations": [observation]},
        "validation": {"observations": [observation]},
        "behavior_equivalence": {
            "status": "PASSED",
            "case_count": 1,
            "pass_count": 1,
            "source_runtime_passed": True,
            "target_runtime_passed": True,
            "oracle_conflict_count": 0,
            "artifact_path": "behavior-equivalence.json",
            "artifact_sha256": _digest(behavior_bytes),
        },
    }

    assembly_module._validate_behavior_and_descriptor_closure(
        evidence,
        behavior_bytes,
        None,
        unit_id="WU-00001",
        source_language="typescript",
        source_path="src/identity.ts",
    )

    assert type(behavior["results"][0]["independent_expected"]) is float


@pytest.mark.parametrize("mutation", ["standalone-scope", "wrong-work-unit"])
def test_assembly_independently_recomputes_repository_unit_namespace(
    tmp_path: Path,
    mutation: str,
) -> None:
    report, batch = _fixture(tmp_path)
    source_sha256 = "sha256:" + report["units"][0]["checkpoint_identity"]["source_sha256"]
    if mutation == "standalone-scope":
        namespace = standalone_artifact_unit_namespace("src/identity.py", source_sha256)
    else:
        namespace = repository_work_unit_namespace(
            repository_snapshot_sha256="sha256:" + "a" * 64,
            work_unit_id="WU-00002",
            source_logical_path="src/identity.py",
            source_sha256=source_sha256,
        )
    _rewrite_identifier_namespace(report, batch, namespace)

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_IDENTIFIER_NAMESPACE_INVALID"):
        assemble_project(report, batch, tmp_path / "assembled")


def test_assembly_rejects_missing_behavior_artifact(tmp_path: Path) -> None:
    report, batch = _fixture(tmp_path)
    (batch / "units" / "WU-00001" / "behavior-equivalence.json").unlink()

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_BEHAVIOR_EVIDENCE_MISSING"):
        assemble_project(report, batch, tmp_path / "assembled")


def test_assembly_rejects_behavior_artifact_tamper(tmp_path: Path) -> None:
    report, batch = _fixture(tmp_path)
    behavior = batch / "units" / "WU-00001" / "behavior-equivalence.json"
    behavior.write_bytes(behavior.read_bytes() + b" ")

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_BEHAVIOR_EVIDENCE_INVALID"):
        assemble_project(report, batch, tmp_path / "assembled")


def test_assembly_rejects_self_consistent_behavior_pointer_rewrite_with_cross_observation_drift(
    tmp_path: Path,
) -> None:
    report, batch = _fixture(tmp_path)
    behavior_path = batch / "units" / "WU-00001" / "behavior-equivalence.json"
    behavior = json.loads(behavior_path.read_bytes())
    behavior["results"][0]["source_native"]["raw"] = '{"case_id":0,"value":8}'
    behavior_bytes = json.dumps(behavior, indent=2, sort_keys=True).encode() + b"\n"
    behavior_path.write_bytes(behavior_bytes)
    _rewrite_route_evidence(
        report,
        batch,
        lambda evidence: evidence["behavior_equivalence"].update(
            {"artifact_sha256": _digest(behavior_bytes)}
        ),
    )

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_BEHAVIOR_EVIDENCE_INVALID"):
        assemble_project(report, batch, tmp_path / "assembled")


def test_assembly_rejects_raw_observation_that_disagrees_with_typed_value(tmp_path: Path) -> None:
    report, batch = _fixture(tmp_path)
    behavior_path = batch / "units" / "WU-00001" / "behavior-equivalence.json"
    behavior = json.loads(behavior_path.read_bytes())
    result = behavior["results"][0]
    result["canonical"]["value"] = 8
    result["independent_expected"] = 8
    result["source_native"]["value"] = 8
    result["target_native"]["value"] = 8
    behavior_bytes = json.dumps(behavior, indent=2, sort_keys=True).encode() + b"\n"
    behavior_path.write_bytes(behavior_bytes)

    def rewrite(evidence: dict[str, Any]) -> None:
        evidence["source_validation"]["observations"][0]["value"] = 8
        evidence["validation"]["observations"][0]["value"] = 8
        evidence["behavior_equivalence"]["artifact_sha256"] = _digest(behavior_bytes)

    _rewrite_route_evidence(report, batch, rewrite)

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_BEHAVIOR_EVIDENCE_INVALID"):
        assemble_project(report, batch, tmp_path / "assembled")


def test_assembly_rejects_symlinked_behavior_artifact(tmp_path: Path) -> None:
    report, batch = _fixture(tmp_path)
    behavior = batch / "units" / "WU-00001" / "behavior-equivalence.json"
    external = tmp_path / "external-behavior.json"
    behavior.replace(external)
    behavior.symlink_to(external)

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_BEHAVIOR_EVIDENCE_MISSING"):
        assemble_project(report, batch, tmp_path / "assembled")


def test_plain_js_descriptor_is_independently_bound_into_assembly(tmp_path: Path) -> None:
    report, batch = _fixture(
        tmp_path,
        source_language="javascript",
        source_path="src/identity.js",
        javascript_descriptor=True,
    )

    manifest = assemble_project(report, batch, tmp_path / "assembled")

    assert manifest["verified_evidence_artifact_count"] == 6
    assert manifest["verified_evidence_artifacts"][-1]["role"] == "source-javascript-esm-descriptor"


def test_default_assembly_api_rejects_deprecated_replay_aggregation(
    tmp_path: Path,
) -> None:
    report, batch = _fixture(
        tmp_path,
        source_language="javascript",
        source_path="src/identity.js",
        javascript_descriptor=True,
    )

    with pytest.raises(
        RouteError,
        match="^ASSEMBLY_DEPRECATED_REPLAY_EXPLICIT_AUTHORITY_REQUIRED$",
    ):
        assembly_module.assemble_project(
            report,
            batch,
            tmp_path / "default-assembled",
        )


@pytest.mark.parametrize(
    ("source_path", "javascript_descriptor"),
    [("src/identity.JS", True), ("src/identity.MJS", False)],
)
def test_javascript_source_suffix_classification_is_case_insensitive(
    tmp_path: Path,
    source_path: str,
    javascript_descriptor: bool,
) -> None:
    report, batch = _fixture(
        tmp_path,
        source_language="javascript",
        source_path=source_path,
        javascript_descriptor=javascript_descriptor,
    )

    manifest = assemble_project(report, batch, tmp_path / "assembled")

    roles = {record["role"] for record in manifest["verified_evidence_artifacts"]}
    assert ("source-javascript-esm-descriptor" in roles) is javascript_descriptor


def test_plain_js_descriptor_rejects_cross_stage_origin_observation(tmp_path: Path) -> None:
    report, batch = _fixture(
        tmp_path,
        source_language="javascript",
        source_path="src/identity.js",
        javascript_descriptor=True,
    )

    def rewrite(evidence: dict[str, Any]) -> None:
        evidence["source_validation"]["javascript_esm_descriptor_observation"] = {
            "observed_origin_path": "/different/private-stage/package.json"
        }

    _rewrite_route_evidence(report, batch, rewrite)

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_JAVASCRIPT_ESM_DESCRIPTOR_INVALID"):
        assemble_project(report, batch, tmp_path / "assembled")


@pytest.mark.parametrize("mutation", ["missing", "tamper"])
def test_assembly_rejects_missing_or_tampered_plain_js_descriptor(
    tmp_path: Path,
    mutation: str,
) -> None:
    report, batch = _fixture(
        tmp_path,
        source_language="javascript",
        source_path="src/identity.js",
        javascript_descriptor=True,
    )
    descriptor = batch / "units" / "WU-00001" / "source-javascript-esm-package.json"
    if mutation == "missing":
        descriptor.unlink()
        error = "ASSEMBLY_UNIT_JAVASCRIPT_ESM_DESCRIPTOR_MISSING"
    else:
        descriptor.write_text('{"type":"commonjs"}\n', encoding="utf-8")
        error = "ASSEMBLY_UNIT_JAVASCRIPT_ESM_DESCRIPTOR_INVALID"

    with pytest.raises(RouteError, match=error):
        assemble_project(report, batch, tmp_path / "assembled")


def test_assembly_rejects_self_consistent_descriptor_rewrite_to_commonjs(tmp_path: Path) -> None:
    report, batch = _fixture(
        tmp_path,
        source_language="javascript",
        source_path="src/identity.js",
        javascript_descriptor=True,
    )
    descriptor_path = batch / "units" / "WU-00001" / "source-javascript-esm-package.json"
    descriptor_bytes = b'{"type":"commonjs"}\n'
    descriptor_path.write_bytes(descriptor_bytes)

    def rewrite(evidence: dict[str, Any]) -> None:
        descriptor = evidence["javascript_esm_descriptor"]
        descriptor.update({"sha256": _digest(descriptor_bytes), "bytes": len(descriptor_bytes)})
        evidence["source"]["javascript_esm_descriptor"] = descriptor
        evidence["source_validation"]["javascript_esm_descriptor"].update(
            {"sha256": _digest(descriptor_bytes), "bytes": len(descriptor_bytes)}
        )

    _rewrite_route_evidence(report, batch, rewrite)

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_JAVASCRIPT_ESM_DESCRIPTOR_INVALID"):
        assemble_project(report, batch, tmp_path / "assembled")


def test_non_js_source_rejects_unreferenced_descriptor_artifact(tmp_path: Path) -> None:
    report, batch = _fixture(tmp_path)
    (batch / "units" / "WU-00001" / "source-javascript-esm-package.json").write_text(
        '{"type":"module"}\n',
        encoding="utf-8",
    )

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_JAVASCRIPT_ESM_DESCRIPTOR_UNEXPECTED"):
        assemble_project(report, batch, tmp_path / "assembled")


def test_archived_non_js_source_rejects_unbound_descriptor_artifact(tmp_path: Path) -> None:
    report, batch = _fixture(tmp_path)
    assembled = tmp_path / "assembled"
    manifest = assemble_project(report, batch, assembled)
    manifest_bytes, contents = _archive_view(manifest, assembled, batch)
    contents["batch/units/WU-00001/source-javascript-esm-package.json"] = b'{"type":"module"}\n'

    with pytest.raises(RouteError, match="ASSEMBLY_ARCHIVE_SOURCE_EVIDENCE_ARTIFACT_SET_MISMATCH"):
        verify_archived_assembly_closure(
            manifest_bytes,
            cast(Language, manifest["target_language"]),
            contents,
            contents.__getitem__,
        )


@pytest.mark.parametrize("mutation", ["missing", "tamper"])
def test_live_assembly_closure_rejects_missing_or_tampered_copied_behavior_artifact(
    tmp_path: Path,
    mutation: str,
) -> None:
    report, batch = _fixture(tmp_path)
    assembled = tmp_path / "assembled"
    manifest = assemble_project(report, batch, assembled)
    copied = assembled / "evidence" / "WU-00001" / "behavior-equivalence.json"
    if mutation == "missing":
        copied.unlink()
        error = "ASSEMBLY_EVIDENCE_ARTIFACT_MISSING_OR_UNSAFE"
    else:
        copied.write_bytes(copied.read_bytes() + b" ")
        error = "ASSEMBLY_EVIDENCE_ARTIFACT_DRIFTED"

    with pytest.raises(RouteError, match=error):
        assembly_module._validate_assembly_manifest(
            manifest,
            cast(Language, manifest["target_language"]),
            assembled,
            require_build_passed=False,
        )


def test_archived_assembly_accepts_exact_original_and_copied_evidence(tmp_path: Path) -> None:
    report, batch = _fixture(tmp_path)
    assembled = tmp_path / "assembled"
    manifest = assemble_project(report, batch, assembled)
    manifest_bytes, contents = _archive_view(manifest, assembled, batch)

    verified = verify_archived_assembly_closure(
        manifest_bytes,
        cast(Language, manifest["target_language"]),
        contents,
        contents.__getitem__,
    )

    assert verified["verified_evidence_artifact_count"] == 5


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("function_name", "forgedSourceFunction"),
        ("target_function_name", "forgedTargetFunction"),
        ("identifier_plan_sha256", "sha256:" + "b" * 64),
        ("target_sha256", "sha256:" + "c" * 64),
    ],
)
def test_archived_assembly_cross_binds_included_unit_identity_to_evidence(
    tmp_path: Path,
    field: str,
    replacement: str,
) -> None:
    report, batch = _fixture(tmp_path)
    assembled = tmp_path / "assembled"
    manifest = assemble_project(report, batch, assembled)
    manifest["included_units"][0][field] = replacement
    manifest_bytes, contents = _archive_view(manifest, assembled, batch)

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_IDENTIFIER"):
        verify_archived_assembly_closure(
            manifest_bytes,
            cast(Language, manifest["target_language"]),
            contents,
            contents.__getitem__,
        )


@pytest.mark.parametrize(
    "relative",
    ["source-semantic-ir.json", "identifier-plan.json", "migrated.ts"],
)
@pytest.mark.parametrize("copy", ["assembled", "batch"])
def test_archived_assembly_rejects_identifier_or_emitted_target_artifact_tamper(
    tmp_path: Path,
    relative: str,
    copy: str,
) -> None:
    report, batch = _fixture(tmp_path)
    assembled = tmp_path / "assembled"
    manifest = assemble_project(report, batch, assembled)
    manifest_bytes, contents = _archive_view(manifest, assembled, batch)
    if copy == "assembled":
        path = f"assembled/evidence/WU-00001/{relative}"
    else:
        path = f"batch/units/WU-00001/{relative}"
    contents[path] += b" "

    with pytest.raises(RouteError, match="ASSEMBLY_ARCHIVE_EVIDENCE_ARTIFACT_DRIFTED"):
        verify_archived_assembly_closure(
            manifest_bytes,
            cast(Language, manifest["target_language"]),
            contents,
            contents.__getitem__,
        )


@pytest.mark.parametrize("scope_mutation", ["standalone-scope", "wrong-work-unit"])
@pytest.mark.parametrize("closure", ["live", "archive"])
def test_live_and_archived_manifest_recompute_identifier_unit_namespace(
    tmp_path: Path,
    scope_mutation: str,
    closure: str,
) -> None:
    report, batch = _fixture(tmp_path)
    assembled = tmp_path / "assembled"
    manifest = assemble_project(report, batch, assembled)
    included = manifest["included_units"][0]
    source_sha256 = "sha256:" + included["source_sha256"]
    if scope_mutation == "standalone-scope":
        namespace = standalone_artifact_unit_namespace(included["source_path"], source_sha256)
    else:
        namespace = repository_work_unit_namespace(
            repository_snapshot_sha256="sha256:" + manifest["snapshot_sha256"],
            work_unit_id="WU-00002",
            source_logical_path=included["source_path"],
            source_sha256=source_sha256,
        )
    included["identifier_unit_namespace"] = namespace.to_mapping()
    included["identifier_unit_namespace_sha256"] = namespace.digest

    with pytest.raises(RouteError, match="ASSEMBLY_MANIFEST_INCLUDED_UNIT_INVALID"):
        if closure == "live":
            assembly_module._validate_assembly_manifest(
                manifest,
                cast(Language, manifest["target_language"]),
                assembled,
                require_build_passed=False,
            )
        else:
            manifest_bytes, contents = _archive_view(manifest, assembled, batch)
            verify_archived_assembly_closure(
                manifest_bytes,
                cast(Language, manifest["target_language"]),
                contents,
                contents.__getitem__,
            )


@pytest.mark.parametrize("mutation", ["missing", "tamper"])
def test_archived_assembly_rejects_missing_or_tampered_original_behavior_artifact(
    tmp_path: Path,
    mutation: str,
) -> None:
    report, batch = _fixture(tmp_path)
    assembled = tmp_path / "assembled"
    manifest = assemble_project(report, batch, assembled)
    manifest_bytes, contents = _archive_view(manifest, assembled, batch)
    original = "batch/units/WU-00001/behavior-equivalence.json"
    if mutation == "missing":
        contents.pop(original)
        error = "ASSEMBLY_ARCHIVE_EVIDENCE_ARTIFACT_MISSING"
    else:
        contents[original] += b" "
        error = "ASSEMBLY_ARCHIVE_EVIDENCE_ARTIFACT_DRIFTED"

    with pytest.raises(RouteError, match=error):
        verify_archived_assembly_closure(
            manifest_bytes,
            cast(Language, manifest["target_language"]),
            contents,
            contents.__getitem__,
        )


@pytest.mark.parametrize("mutation", ["missing", "tamper"])
def test_archived_plain_js_assembly_rejects_missing_or_tampered_original_descriptor(
    tmp_path: Path,
    mutation: str,
) -> None:
    report, batch = _fixture(
        tmp_path,
        source_language="javascript",
        source_path="src/identity.js",
        javascript_descriptor=True,
    )
    assembled = tmp_path / "assembled"
    manifest = assemble_project(report, batch, assembled)
    manifest_bytes, contents = _archive_view(manifest, assembled, batch)
    original = "batch/units/WU-00001/source-javascript-esm-package.json"
    if mutation == "missing":
        contents.pop(original)
        error = "ASSEMBLY_ARCHIVE_EVIDENCE_ARTIFACT_MISSING"
    else:
        contents[original] = b'{"type":"commonjs"}\n'
        error = "ASSEMBLY_ARCHIVE_EVIDENCE_ARTIFACT_DRIFTED"

    with pytest.raises(RouteError, match=error):
        verify_archived_assembly_closure(
            manifest_bytes,
            cast(Language, manifest["target_language"]),
            contents,
            contents.__getitem__,
        )

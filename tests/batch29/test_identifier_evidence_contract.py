from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route.engine import migrate_module

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts/batch29/validate_route.py"
MODULE_FIXTURES = ROOT / "engines/polyglot-route-engine/fixtures/module"


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "batch29_identifier_evidence_validator", VALIDATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _role_records(
    output: Path, report: dict[str, Any]
) -> dict[str, list[tuple[dict[str, Any], Path, str]]]:
    validator = _load_validator()
    records: dict[str, list[tuple[dict[str, Any], Path, str]]] = {}
    for reference in report["artifact_refs"]:
        path = output / reference["path"]
        observed = validator.sha256_file(path)
        assert observed == reference["sha256"]
        assert path.stat().st_size == reference["bytes"]
        records.setdefault(reference["role"], []).append((reference, path, observed))
    return records


def _document(
    records: dict[str, list[tuple[dict[str, Any], Path, str]]], role: str
) -> dict[str, Any]:
    assert len(records[role]) == 1
    return _load(records[role][0][1])


def _validate_identifier_and_whole_file_replay(
    output: Path,
    report: dict[str, Any],
    *,
    source_language: str,
    target_language: str,
    replay_native_behavior: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    validator = _load_validator()
    records = _role_records(output, report)
    source_semantic = _document(records, "source-module-semantic-ir")
    target_semantic = _document(records, "target-module-semantic-ir")
    closure = _document(records, "whole-file-module-closure")
    module_manifest = _document(records, "module-case-manifest")
    manifest = {
        "source": {"language": source_language},
        "target": {"language": target_language},
    }
    failures: list[str] = []
    javascript_descriptor_record = validator._validate_module_javascript_esm_descriptor(
        manifest=manifest,
        evidence=report,
        module_input=report["module_input"],
        role_records=records,
        source_artifact_record=records["original-source-module-artifact"][0],
        failures=failures,
    )
    identifier_closure = validator._validate_module_identifier_closure(
        manifest=manifest,
        evidence=report,
        module_input=report["module_input"],
        closure_document=closure,
        role_records=records,
        source_semantic_document=source_semantic,
        target_semantic_document=target_semantic,
        source_inventory_document=_document(records, "source-module-inventory"),
        target_inventory_document=_document(records, "target-module-inventory"),
        minimum_functions=3,
        failures=failures,
    )
    validator._validate_module_whole_file_closure(
        manifest=manifest,
        module_manifest=module_manifest,
        module_input=report["module_input"],
        source_semantic_document=source_semantic,
        target_semantic_document=target_semantic,
        identifier_closure=identifier_closure,
        source_inventory_document=_document(records, "source-module-inventory"),
        target_inventory_document=_document(records, "target-module-inventory"),
        closure_document=closure,
        source_validation_document=_document(records, "source-module-validation"),
        target_validation_document=_document(records, "target-module-validation"),
        source_observation_document=_document(records, "source-module-observations"),
        target_observation_document=_document(records, "target-module-observations"),
        source_artifact_record=records["original-source-module-artifact"][0],
        target_artifact_record=records["emitted-target-module-artifact"][0],
        source_inventory_record=records["source-module-inventory"][0],
        target_inventory_record=records["target-module-inventory"][0],
        closure_record=records["whole-file-module-closure"][0],
        javascript_descriptor_record=javascript_descriptor_record,
        role_records=records,
        route_swift_receipt=None,
        replay_native_behavior=replay_native_behavior,
        failures=failures,
    )
    return identifier_closure, failures


@pytest.fixture(scope="module")
def cpp_to_objc_module(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("identifier-cpp-objc") / "output"
    report = migrate_module(
        MODULE_FIXTURES / "cpp/equivalence_module.cpp",
        "cpp",
        "objc",
        MODULE_FIXTURES / "cases.json",
        output,
    )
    assert report["status"] == "PASSED"
    return output


@pytest.fixture(scope="module")
def typescript_to_javascript_identifier_module(
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    root = tmp_path_factory.mktemp("identifier-typescript-javascript")
    source = root / "identifier_module.ts"
    source.write_text(
        "export function Object(value: number): number { return value; }\n\n"
        "export function Number(value: number): number { return value; }\n\n"
        "export function actual1(value: boolean): boolean { return value; }\n",
        encoding="utf-8",
    )
    manifest = root / "cases.json"
    _write_json(
        manifest,
        {
            "schema_version": "1.0.0",
            "profile": "typed-pure-module-v1",
            "composition": {
                "call_graph": [],
                "global_state": "none",
                "effects": "none",
                "exceptions": "domain-guards-fail-closed-before-execution",
                "input_domain": "nodejs-es2022-esm-safe-integer-finite-v1",
            },
            "functions": [
                {
                    "symbol": "Object",
                    "signature": {
                        "parameters": [{"name": "value", "type": "number"}],
                        "return_type": "number",
                    },
                    "cases": [{"args": [1.0], "expected": 1.0}],
                },
                {
                    "symbol": "Number",
                    "signature": {
                        "parameters": [{"name": "value", "type": "number"}],
                        "return_type": "number",
                    },
                    "cases": [{"args": [-0.0], "expected": -0.0}],
                },
                {
                    "symbol": "actual1",
                    "signature": {
                        "parameters": [{"name": "value", "type": "boolean"}],
                        "return_type": "boolean",
                    },
                    "cases": [{"args": [True], "expected": True}],
                },
            ],
        },
    )
    output = root / "output"
    report = migrate_module(
        source,
        "typescript",
        "javascript",
        manifest,
        output,
    )
    assert report["status"] == "PASSED"
    return output


@pytest.fixture(scope="module")
def javascript_js_to_typescript_module(
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    root = tmp_path_factory.mktemp("identifier-javascript-js-typescript")
    source = root / "identifier_module.js"
    source.write_text(
        "/** @param {number} value @returns {number} */\n"
        "export function echoNumber(value) { return value; }\n\n"
        "/** @param {boolean} value @returns {boolean} */\n"
        "export function echoBoolean(value) { return value; }\n\n"
        "/** @param {string} value @returns {string} */\n"
        "export function echoString(value) { return value; }\n",
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        '{"name":"identifier-esm-fixture","private":true,"type":"module"}\n',
        encoding="utf-8",
    )
    manifest = root / "cases.json"
    _write_json(
        manifest,
        {
            "schema_version": "1.0.0",
            "profile": "typed-pure-module-v1",
            "composition": {
                "call_graph": [],
                "global_state": "none",
                "effects": "none",
                "exceptions": "domain-guards-fail-closed-before-execution",
                "input_domain": "nodejs-es2022-esm-safe-integer-finite-v1",
            },
            "functions": [
                {
                    "symbol": "echoNumber",
                    "signature": {
                        "parameters": [{"name": "value", "type": "number"}],
                        "return_type": "number",
                    },
                    "cases": [{"args": [-0.0], "expected": -0.0}],
                },
                {
                    "symbol": "echoBoolean",
                    "signature": {
                        "parameters": [{"name": "value", "type": "boolean"}],
                        "return_type": "boolean",
                    },
                    "cases": [{"args": [True], "expected": True}],
                },
                {
                    "symbol": "echoString",
                    "signature": {
                        "parameters": [{"name": "value", "type": "string"}],
                        "return_type": "string",
                    },
                    "cases": [{"args": ["Node.js"], "expected": "Node.js"}],
                },
            ],
        },
    )
    output = root / "output"
    report = migrate_module(
        source,
        "javascript",
        "typescript",
        manifest,
        output,
    )
    assert report["status"] == "PASSED"
    return output


def test_cpp_to_objc_all_renamed_identifier_plan_replays_exactly(
    cpp_to_objc_module: Path,
) -> None:
    report = _load(cpp_to_objc_module / "typed-pure-module-equivalence.json")
    closure, failures = _validate_identifier_and_whole_file_replay(
        cpp_to_objc_module,
        report,
        source_language="cpp",
        target_language="objc",
    )
    assert failures == []
    assert closure
    assert report["identifier_hygiene"]["renamed"] is True
    assert all(
        mapping["raw_symbol"] != mapping["canonical_symbol"]
        for mapping in report["identifier_hygiene"]["functions"]
    )


def test_javascript_object_number_identifier_plan_replays_exactly(
    typescript_to_javascript_identifier_module: Path,
) -> None:
    report = _load(
        typescript_to_javascript_identifier_module
        / "typed-pure-module-equivalence.json"
    )
    closure, failures = _validate_identifier_and_whole_file_replay(
        typescript_to_javascript_identifier_module,
        report,
        source_language="typescript",
        target_language="javascript",
    )
    assert failures == []
    assert closure
    mappings = {
        mapping["canonical_symbol"]: mapping["raw_symbol"]
        for mapping in report["identifier_hygiene"]["functions"]
    }
    assert mappings["Object"] != "Object"
    assert mappings["Number"] != "Number"


def test_javascript_js_esm_descriptor_replays_with_private_package_snapshot(
    javascript_js_to_typescript_module: Path,
) -> None:
    report = _load(
        javascript_js_to_typescript_module / "typed-pure-module-equivalence.json"
    )
    closure, failures = _validate_identifier_and_whole_file_replay(
        javascript_js_to_typescript_module,
        report,
        source_language="javascript",
        target_language="typescript",
        replay_native_behavior=True,
    )
    assert closure
    assert failures == []
    descriptor = report["javascript_esm_descriptor"]
    assert descriptor == report["module_input"]["javascript_esm_descriptor"]
    assert descriptor["snapshot_path"] == "source/package.json"
    assert descriptor["artifact_path"] == "source-module-artifact/package.json"


def test_javascript_js_esm_descriptor_rejects_self_consistent_package_tamper(
    javascript_js_to_typescript_module: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    shutil.copytree(javascript_js_to_typescript_module, output)
    report = _load(output / "typed-pure-module-equivalence.json")
    validator = _load_validator()
    records = _role_records(output, report)
    reference, descriptor_path, _digest = records["source-javascript-esm-descriptor"][0]
    descriptor_path.write_text('{"type":"commonjs"}\n', encoding="utf-8")
    reference["sha256"] = validator.sha256_file(descriptor_path)
    reference["bytes"] = descriptor_path.stat().st_size
    for descriptor in (
        report["javascript_esm_descriptor"],
        report["module_input"]["javascript_esm_descriptor"],
    ):
        descriptor["sha256"] = reference["sha256"]
        descriptor["bytes"] = reference["bytes"]
    failures: list[str] = []
    records = _role_records(output, report)
    validated = validator._validate_module_javascript_esm_descriptor(
        manifest={
            "source": {"language": "javascript"},
            "target": {"language": "typescript"},
        },
        evidence=report,
        module_input=report["module_input"],
        role_records=records,
        source_artifact_record=records["original-source-module-artifact"][0],
        failures=failures,
    )
    assert validated is not None
    assert "module JavaScript ESM descriptor package type is not module" in failures


def test_javascript_mjs_forbids_descriptor_fields(tmp_path: Path) -> None:
    package = tmp_path / "package.json"
    package.write_text('{"type":"module"}\n', encoding="utf-8")
    validator = _load_validator()
    digest = validator.sha256_file(package)
    descriptor = {
        "logical_path": "package.json",
        "snapshot_path": "source/package.json",
        "artifact_path": "source-module-artifact/package.json",
        "sha256": digest,
        "bytes": package.stat().st_size,
        "type": "module",
    }
    failures: list[str] = []
    validated = validator._validate_module_javascript_esm_descriptor(
        manifest={
            "source": {"language": "javascript"},
            "target": {"language": "typescript"},
        },
        evidence={
            "javascript_esm_descriptor": descriptor,
            "javascript_esm_descriptor_observation": {
                "observed_origin_path": str(package)
            },
        },
        module_input={
            "source_logical_file": "equivalence_module.mjs",
            "javascript_esm_descriptor": descriptor,
        },
        role_records={
            "source-javascript-esm-descriptor": [
                (
                    {
                        "role": "source-javascript-esm-descriptor",
                        "path": "source-module-artifact/package.json",
                        "sha256": digest,
                        "bytes": package.stat().st_size,
                    },
                    package,
                    digest,
                )
            ]
        },
        source_artifact_record=None,
        failures=failures,
    )
    assert validated is None
    assert failures == [
        "JavaScript ESM descriptor fields are forbidden for this module source",
        "source-javascript-esm-descriptor is forbidden for this module source",
    ]


def test_javascript_js_descriptor_equivalence_ignores_absolute_observation_path(
    tmp_path: Path,
) -> None:
    validator = _load_validator()
    source = tmp_path / "source.js"
    source.write_text(
        "/** @param {number} value @returns {number} */\n"
        "export function identity(value) { return value; }\n",
        encoding="utf-8",
    )
    package = tmp_path / "package.json"
    package.write_text('{"type":"module"}\n', encoding="utf-8")
    package_digest = validator.sha256_file(package)
    source_digest = validator.sha256_file(source)
    descriptor = {
        "logical_path": "package.json",
        "snapshot_path": "source/package.json",
        "artifact_path": "source-module-artifact/package.json",
        "sha256": package_digest,
        "bytes": package.stat().st_size,
        "type": "module",
    }
    descriptor_record = (
        {
            "role": "source-javascript-esm-descriptor",
            "path": "source-module-artifact/package.json",
            "sha256": package_digest,
            "bytes": package.stat().st_size,
        },
        package,
        package_digest,
    )
    source_record = (
        {
            "role": "original-source-module-artifact",
            "path": "source-module-artifact/source.js",
            "sha256": source_digest,
            "bytes": source.stat().st_size,
        },
        source,
        source_digest,
    )
    for observed_origin in (
        tmp_path / "host-a/package.json",
        tmp_path / "unrelated-host-b/package.json",
    ):
        failures: list[str] = []
        validated = validator._validate_module_javascript_esm_descriptor(
            manifest={
                "source": {"language": "javascript"},
                "target": {"language": "typescript"},
            },
            evidence={
                "javascript_esm_descriptor": descriptor,
                "javascript_esm_descriptor_observation": {
                    "observed_origin_path": str(observed_origin.resolve())
                },
            },
            module_input={
                "source_logical_file": "source.js",
                "javascript_esm_descriptor": descriptor,
            },
            role_records={
                "source-javascript-esm-descriptor": [descriptor_record],
            },
            source_artifact_record=source_record,
            failures=failures,
        )
        assert validated == descriptor_record
        assert failures == []


@pytest.mark.parametrize("tamper", ["plan", "raw-target-ir"])
def test_module_identifier_closure_rejects_self_consistent_tamper(
    cpp_to_objc_module: Path,
    tmp_path: Path,
    tamper: str,
) -> None:
    output = tmp_path / "output"
    shutil.copytree(cpp_to_objc_module, output)
    report = _load(output / "typed-pure-module-equivalence.json")
    validator = _load_validator()
    records = _role_records(output, report)
    role = "identifier-plan" if tamper == "plan" else "raw-target-ir"
    reference, path, _ = records[role][0]
    payload = _load(path)
    if tamper == "plan":
        payload["bindings"][0]["target_name"] = "forged_identifier"
        path.write_bytes(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        hygiene_field = "plan"
    else:
        payload["functions"][0]["name"] = "forged_identifier"
        _write_json(path, payload)
        hygiene_field = "raw_target_ir"
    reference["sha256"] = validator.sha256_file(path)
    reference["bytes"] = path.stat().st_size
    for hygiene in (
        report["identifier_hygiene"],
        report["module_input"]["identifier_hygiene"],
    ):
        hygiene[hygiene_field] = {
            "role": role,
            "path": path.name,
            "sha256": reference["sha256"],
            "bytes": reference["bytes"],
        }
    if tamper == "plan":
        report["whole_file_closure"]["identifier_hygiene"]["plan_sha256"] = reference[
            "sha256"
        ]

    records = _role_records(output, report)
    failures: list[str] = []
    closure = validator._validate_module_identifier_closure(
        manifest={"target": {"language": "objc"}},
        evidence=report,
        module_input=report["module_input"],
        closure_document=report["whole_file_closure"],
        role_records=records,
        source_semantic_document=_document(records, "source-module-semantic-ir"),
        target_semantic_document=_document(records, "target-module-semantic-ir"),
        source_inventory_document=_document(records, "source-module-inventory"),
        target_inventory_document=_document(records, "target-module-inventory"),
        minimum_functions=3,
        failures=failures,
    )
    assert closure == {}
    assert any(
        "module identifier closure is invalid" in failure for failure in failures
    )

from __future__ import annotations

import copy
import importlib.util
import shutil
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts" / "batch29" / "validate_route.py"


@pytest.fixture(scope="module")
def validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "batch29_engine_source_module_binding_validator",
        VALIDATOR_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runtime_provenance(validator: Any) -> dict[str, Any]:
    failures: list[str] = []
    provenance = validator._runtime_provenance(
        failures,
        "focused engine source binding test",
    )
    assert provenance is not None, failures
    assert failures == []
    return provenance


def _current_capture(
    validator: Any,
    route: Path,
    *,
    artifact_directory: str = "formal-artifacts",
) -> tuple[
    str,
    dict[str, Any],
    dict[str, tuple[dict[str, Any], Path, str]],
]:
    artifact_root = f"certification/{artifact_directory}"
    manifest_relative = f"{artifact_root}/engine-source-manifest.json"
    entries: list[dict[str, Any]] = []
    records: dict[str, tuple[dict[str, Any], Path, str]] = {}
    for index, repository_path in enumerate(
        sorted(validator.ENGINE_SOURCE_REQUIRED_ASSETS)
    ):
        source = ROOT / repository_path
        assert source.is_file(), repository_path
        captured_relative = f"{artifact_root}/engine-sources/{repository_path}"
        captured = route / captured_relative
        captured.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, captured)
        digest = validator.sha256_file(captured)
        byte_count = captured.stat().st_size
        entry = {
            "repository_path": repository_path,
            "captured_path": captured_relative,
            "sha256": digest,
            "bytes": byte_count,
        }
        reference = {
            "artifact_id": f"engine-source-binding-{index:02d}",
            "role": "engine-source",
            "path": captured_relative,
            "sha256": digest,
            "bytes": byte_count,
        }
        entries.append(entry)
        records[str(reference["artifact_id"])] = (
            reference,
            captured.resolve(strict=True),
            digest,
        )
    return manifest_relative, {"files": entries}, records


def _failures(
    validator: Any,
    route: Path,
    manifest_relative: str,
    manifest: dict[str, Any],
    records: dict[str, tuple[dict[str, Any], Path, str]],
    runtime_provenance: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    validator._validate_required_engine_source_bindings(
        route=route,
        manifest_relative=manifest_relative,
        source_manifest=manifest,
        ref_records=records,
        runtime_provenance=runtime_provenance,
        failures=failures,
    )
    return failures


@pytest.mark.parametrize("artifact_directory", ["formal-artifacts", "strict-artifacts"])
def test_current_engine_capture_binds_all_required_assets_and_runtime_modules(
    tmp_path: Path,
    validator: Any,
    runtime_provenance: dict[str, Any],
    artifact_directory: str,
) -> None:
    route = tmp_path / "cpp-to-java"
    manifest_relative, manifest, records = _current_capture(
        validator,
        route,
        artifact_directory=artifact_directory,
    )

    assert len(validator.ENGINE_RUNTIME_MODULES) == 13
    assert len(validator.ENGINE_SOURCE_REQUIRED_ASSETS) == 16
    assert _failures(
        validator,
        route,
        manifest_relative,
        manifest,
        records,
        runtime_provenance,
    ) == []


@pytest.mark.parametrize(
    "repository_path",
    [
        (
            "engines/polyglot-route-engine/src/"
            "elmos_polyglot_route/validation.py"
        ),
        "engines/polyglot-route-engine/uv.lock",
        "scripts/batch29/run_polyglot_routes.py",
        "scripts/batch29/validate_route.py",
    ],
)
def test_self_consistent_required_asset_removal_fails_closed(
    tmp_path: Path,
    validator: Any,
    runtime_provenance: dict[str, Any],
    repository_path: str,
) -> None:
    route = tmp_path / "cpp-to-java"
    manifest_relative, manifest, records = _current_capture(validator, route)
    captured_path = (
        "certification/formal-artifacts/engine-sources/" + repository_path
    )
    manifest["files"] = [
        item
        for item in manifest["files"]
        if item["repository_path"] != repository_path
    ]
    records = {
        artifact_id: record
        for artifact_id, record in records.items()
        if record[0]["path"] != captured_path
    }

    failures = _failures(
        validator,
        route,
        manifest_relative,
        manifest,
        records,
        runtime_provenance,
    )

    assert any(
        "must contain exactly one required asset" in failure
        and repository_path in failure
        for failure in failures
    ), failures


def test_self_consistent_required_asset_path_swap_fails_closed(
    tmp_path: Path,
    validator: Any,
    runtime_provenance: dict[str, Any],
) -> None:
    route = tmp_path / "cpp-to-java"
    manifest_relative, manifest, records = _current_capture(validator, route)
    paths = (
        "engines/polyglot-route-engine/src/elmos_polyglot_route/engine.py",
        "engines/polyglot-route-engine/src/elmos_polyglot_route/validation.py",
    )
    entries = {
        item["repository_path"]: item
        for item in manifest["files"]
        if item["repository_path"] in paths
    }
    first_path = entries[paths[0]]["captured_path"]
    second_path = entries[paths[1]]["captured_path"]
    entries[paths[0]]["captured_path"] = second_path
    entries[paths[1]]["captured_path"] = first_path
    first_record = next(record for record in records.values() if record[0]["path"] == first_path)
    second_record = next(record for record in records.values() if record[0]["path"] == second_path)
    first_record[0]["path"] = second_path
    second_record[0]["path"] = first_path

    failures = _failures(
        validator,
        route,
        manifest_relative,
        manifest,
        records,
        runtime_provenance,
    )

    assert sum("captured_path is not canonical" in failure for failure in failures) == 2
    assert any("ref path mismatch" in failure for failure in failures), failures


def test_self_consistent_required_asset_digest_swap_fails_closed(
    tmp_path: Path,
    validator: Any,
    runtime_provenance: dict[str, Any],
) -> None:
    route = tmp_path / "cpp-to-java"
    manifest_relative, manifest, records = _current_capture(validator, route)
    paths = (
        "engines/polyglot-route-engine/src/elmos_polyglot_route/engine.py",
        "engines/polyglot-route-engine/src/elmos_polyglot_route/validation.py",
    )
    entries = {
        item["repository_path"]: item
        for item in manifest["files"]
        if item["repository_path"] in paths
    }
    first_digest = entries[paths[0]]["sha256"]
    second_digest = entries[paths[1]]["sha256"]
    entries[paths[0]]["sha256"] = second_digest
    entries[paths[1]]["sha256"] = first_digest
    for record in records.values():
        if record[0]["path"].endswith(paths[0]):
            record[0]["sha256"] = second_digest
        elif record[0]["path"].endswith(paths[1]):
            record[0]["sha256"] = first_digest

    failures = _failures(
        validator,
        route,
        manifest_relative,
        manifest,
        records,
        runtime_provenance,
    )

    assert sum("digest is not cross-bound" in failure for failure in failures) >= 2
    assert any("runtime module digest is not cross-bound" in failure for failure in failures)


def test_runtime_provenance_module_path_swap_fails_closed(
    tmp_path: Path,
    validator: Any,
    runtime_provenance: dict[str, Any],
) -> None:
    route = tmp_path / "cpp-to-java"
    manifest_relative, manifest, records = _current_capture(validator, route)
    provenance = copy.deepcopy(runtime_provenance)
    modules = provenance["engine_modules"]
    first = "elmos_polyglot_route.engine"
    second = "elmos_polyglot_route.validation"
    modules[first]["path"], modules[second]["path"] = (
        modules[second]["path"],
        modules[first]["path"],
    )

    failures = _failures(
        validator,
        route,
        manifest_relative,
        manifest,
        records,
        provenance,
    )

    assert sum("runtime module path is not cross-bound" in failure for failure in failures) == 2

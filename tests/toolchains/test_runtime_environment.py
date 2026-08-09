from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "toolchains" / "runtime_environment.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("elmos_runtime_environment", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("runtime_environment module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runtime_environment = _load_module()


SYNTHESIS_LANGUAGE_RUNTIMES = {
    "java": "java-21",
    "python": "python-3.12.12",
    "csharp": "dotnet-sdk-10.0.301",
    "typescript": "node-26.0.0",
    "go": "go-1.25.0",
    "kotlin": "kotlin-2.2.20",
    "php": "php-8.4.12",
    "rust": "rust-1.89.0",
}

ROUTE_LANGUAGE_RUNTIMES = {
    "java": "java-21",
    "python": "python-3.12.12",
    "csharp": "dotnet-sdk-10.0.301",
    "typescript": "node-26.0.0",
    "go": "go-1.25.0",
    "rust": "rust-1.89.0",
    "cpp": "apple-clang-21",
    "objc": "objective-c-apple",
    "swift": "swift-6.3.3",
}

B66_80_BINDINGS = {
    "66": {"node-26.0.0", "pnpm-10.12.4"},
    "67": {"go-1.25.0"},
    "68": {"java-21", "kotlin-2.2.20"},
    "69": {"php-8.4.12"},
    "70": {"apple-clang-21", "cmake-ninja"},
    "71": {"rust-1.89.0"},
    "72": {"flutter-3.44.1"},
    "73": {"swift-6.3.3"},
    "74": {"posix-shells", "powershell"},
    "75": {"postgresql-17.5"},
    "76": {"cmake-ninja"},
    "77": {"container-cli"},
    "78": {"iac-kubernetes-cli"},
    "79": {"ci-provider-runtimes"},
    "80": {
        "java-21",
        "python-3.12.12",
        "dotnet-sdk-10.0.301",
        "node-26.0.0",
        "go-1.25.0",
        "rust-1.89.0",
    },
}

B81_95_BINDINGS = {
    "81": {"mainframe-runtime"},
    "82": {"sap-abap-runtime"},
    "83": {"database-procedural-runtimes"},
    "84": {"plc-runtime"},
    "85": {"matlab-simulink-runtime"},
    "86": {"modelica-fmi-runtime"},
    "87": {"vb-office-runtime"},
    "88": {"ibmi-rpg-runtime"},
    "89": {"r-runtime"},
    "90": {"sas-runtime"},
    "91": {"salesforce-runtime"},
    "92": {"objective-c-apple", "swift-6.3.3"},
    "93": {"delphi-runtime"},
    "94": {"beam-runtime"},
    "95": {"lua-openresty-runtime"},
}


def _runtime_index(manifest: dict) -> dict[str, dict]:
    return {runtime["id"]: runtime for runtime in manifest["runtimes"]}


def _profile_runtime_ids(manifest: dict, profile: str) -> set[str]:
    selected = manifest["profiles"][profile]
    return set(selected["required"]) | set(selected["optional"])


def _write_executable(directory: Path, name: str, output: str) -> Path:
    target = directory / name
    target.write_text(f"#!/bin/sh\nprintf '%s\\n' {json.dumps(output)}\n", encoding="utf-8")
    target.chmod(0o755)
    return target


def _doctor_runtime(result: dict, runtime_id: str) -> dict:
    return next(item for item in result["runtimes"] if item["id"] == runtime_id)


def test_module_constants_and_default_manifest_are_repository_scoped() -> None:
    assert runtime_environment.ROOT == ROOT
    assert runtime_environment.MANIFEST_PATH == ROOT / "toolchains" / "runtime-manifest.json"

    manifest = runtime_environment.load_manifest()

    assert manifest["manifest_id"] == "elmos-language-runtime-matrix-v1"
    assert runtime_environment.validate_manifest(manifest) == []


def test_load_manifest_accepts_an_explicit_path(tmp_path: Path) -> None:
    payload = {"schema_version": "test", "profiles": {}, "runtimes": []}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert runtime_environment.load_manifest(path) == payload


def test_manifest_has_only_the_governed_top_level_profiles() -> None:
    manifest = runtime_environment.load_manifest()

    assert set(manifest["profiles"]) == {
        "core",
        "synthesis",
        "routes-macos",
        "b66-80",
        "spring-legacy",
        "frontend-native",
        "language-packs",
        "all",
    }


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("synthesis", SYNTHESIS_LANGUAGE_RUNTIMES),
        ("routes-macos", ROUTE_LANGUAGE_RUNTIMES),
    ],
)
def test_language_profiles_have_exact_emitter_and_route_coverage(
    profile: str,
    expected: dict[str, str],
) -> None:
    manifest = runtime_environment.load_manifest()
    runtimes = _runtime_index(manifest)
    selected_ids = _profile_runtime_ids(manifest, profile)
    expected_languages = set(expected)

    assert set(expected.values()) <= selected_ids
    assert {
        runtime_id
        for runtime_id in selected_ids
        if set(runtimes[runtime_id]["languages"]) & expected_languages
    } == set(expected.values())
    for language, runtime_id in expected.items():
        assert language in runtimes[runtime_id]["languages"]


def test_batch_bindings_cover_every_batch_exactly_and_reference_known_runtimes() -> None:
    manifest = runtime_environment.load_manifest()
    runtime_ids = set(_runtime_index(manifest))

    observed_66_80 = {
        batch: set(runtime_ids_for_batch)
        for batch, runtime_ids_for_batch in manifest["batch_bindings"]["b66-80"].items()
    }
    observed_81_95 = {
        batch: set(runtime_ids_for_batch)
        for batch, runtime_ids_for_batch in manifest["batch_bindings"]["b81-95"].items()
    }

    assert observed_66_80 == B66_80_BINDINGS
    assert observed_81_95 == B81_95_BINDINGS
    assert set().union(*observed_66_80.values(), *observed_81_95.values()) <= runtime_ids
    assert set().union(*observed_81_95.values()) == _profile_runtime_ids(
        manifest, "language-packs"
    )


def test_validation_reports_duplicate_unknown_regex_and_batch_gaps() -> None:
    manifest = runtime_environment.load_manifest()
    broken = copy.deepcopy(manifest)
    broken["runtimes"].append(copy.deepcopy(broken["runtimes"][0]))
    broken["profiles"]["core"]["required"].append("missing-runtime")
    broken["runtimes"][0]["probes"][0]["pattern"] = "("
    del broken["batch_bindings"]["b66-80"]["80"]

    errors = runtime_environment.validate_manifest(broken)
    combined = "\n".join(errors).lower()

    assert errors
    assert "duplicate" in combined
    assert "missing-runtime" in combined
    assert "pattern" in combined or "regex" in combined
    assert "80" in combined


def test_doctor_accepts_an_exact_managed_probe_and_rejects_version_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = runtime_environment.load_manifest()
    manifest["profiles"]["fixture"] = {
        "description": "single deterministic test runtime",
        "required": ["node-26.0.0"],
        "optional": [],
    }
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    node = _write_executable(bin_dir, "node", "v26.0.0")
    monkeypatch.setitem(
        runtime_environment.PROBE_COMMANDS,
        "node",
        runtime_environment.ProbeCommand("node", ("--version",), ("node",)),
    )
    environ = {
        "PATH": str(bin_dir),
        "ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT": str(tmp_path / "toolchains"),
    }

    ready = runtime_environment.doctor(
        manifest,
        "fixture",
        platform_key="darwin-arm64",
        environ=environ,
    )

    assert ready["status"] == "READY"
    assert ready["claim_ceiling"] == "TOOLCHAIN_READY"
    assert _doctor_runtime(ready, "node-26.0.0")["status"] == "READY"

    node.write_text("#!/bin/sh\nprintf '%s\\n' 'v25.0.0'\n", encoding="utf-8")
    node.chmod(0o755)
    drifted = runtime_environment.doctor(
        manifest,
        "fixture",
        platform_key="darwin-arm64",
        environ=environ,
    )

    assert drifted["status"] == "BLOCKED"
    assert drifted["claim_ceiling"] == "NOT_RUN"
    assert _doctor_runtime(drifted, "node-26.0.0")["status"] == "VERSION_MISMATCH"


def test_doctor_never_promotes_vendor_or_external_runtimes(
    tmp_path: Path,
) -> None:
    manifest = runtime_environment.load_manifest()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(bin_dir, "cobc", "cobc 3.2.0")
    _write_executable(bin_dir, "sf", "@salesforce/cli/2.100.0 darwin-arm64 node-v26")
    _write_executable(bin_dir, "salesforce", "@salesforce/cli/2.100.0")
    result = runtime_environment.doctor(
        manifest,
        "language-packs",
        platform_key="darwin-arm64",
        environ={"PATH": str(bin_dir)},
    )
    runtimes = _runtime_index(manifest)
    external_ids = {
        runtime_id
        for runtime_id in _profile_runtime_ids(manifest, "language-packs")
        if runtimes[runtime_id]["install_policy"] in {"external-service", "vendor-external"}
    }

    assert external_ids
    for runtime_id in external_ids:
        observed = _doctor_runtime(result, runtime_id)
        assert observed["status"] not in {"READY", "TOOLCHAIN_READY"}
        if "any" in runtimes[runtime_id]["platforms"] or "darwin-arm64" in runtimes[runtime_id][
            "platforms"
        ]:
            assert observed["status"] == "NOT_RUN"
        else:
            assert observed["status"] == "NOT_APPLICABLE"
    assert _doctor_runtime(result, "mainframe-runtime")["observed_available"] is True
    assert _doctor_runtime(result, "mainframe-runtime")["status"] == "NOT_RUN"


def test_render_env_is_deterministic_and_preserves_the_callers_path(tmp_path: Path) -> None:
    manifest = runtime_environment.load_manifest()
    toolchain_root = tmp_path / "isolated-toolchains"
    environ = {
        "PATH": os.pathsep.join([str(tmp_path / "existing-a"), str(tmp_path / "existing-b")]),
        "ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT": str(toolchain_root),
    }

    first = runtime_environment.render_env(
        manifest,
        "synthesis",
        environ=environ,
    )
    second = runtime_environment.render_env(
        manifest,
        "synthesis",
        environ=environ,
    )

    assert first == second
    assert "export ELMOS_RUNTIME_PROFILE=" in first
    assert "export ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT=" in first
    assert str(toolchain_root) in first
    assert '"$PATH"' in first
    assert environ["PATH"] not in first
    assert "curl " not in first
    assert "brew " not in first


def test_main_validates_the_default_manifest(capsys: pytest.CaptureFixture[str]) -> None:
    assert runtime_environment.main(["validate"]) == 0
    output = capsys.readouterr()
    assert "VALID" in output.out.upper()

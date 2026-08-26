from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

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
    "php": "php-route-8.5.9",
    "kotlin": "kotlin-route-2.2.20",
    "react": "react-19.2.7",
    "flutter": "flutter-3.44.1",
}

B66_80_BINDINGS = {
    "66": {"node-26.0.0", "pnpm-10.12.4", "typescript-5.9.2"},
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


def _route_receipt_bound(receipt: dict) -> dict:
    return {
        key: receipt[key]
        for key in (
            "toolchain_contract_sha256",
            "active_languages",
            "deprecated_languages",
            "toolchains",
            "react_runtime_receipt",
            "flutter_build_toolchain_receipt",
        )
    }


def _rebind_route_receipt(receipt: dict) -> None:
    receipt["receipt_sha256"] = runtime_environment._route_receipt_digest(
        _route_receipt_bound(receipt)
    )


def _valid_route_receipt(monkeypatch: pytest.MonkeyPatch) -> dict:
    dependency_profile_sha256 = "1" * 64
    probe_source = "probe"
    runtime_payload = {
        "schema_version": "1.0.0",
        "kind": "elmos.react-runtime-import-receipt",
        "status": "PASSED",
        "toolchain_language": "react",
        "toolchain_version": (
            "React 19.2.7 / React DOM 19.2.7 / TypeScript 5.9.2 / Node 26.0.0"
        ),
        "dependency_profile_sha256": dependency_profile_sha256,
        "probe_source_sha256": hashlib.sha256(probe_source.encode("utf-8")).hexdigest(),
        "versions": {"react": "19.2.7", "react-dom": "19.2.7"},
        "command": [
            "/exact/react",
            "--input-type=module",
            "--eval",
            probe_source,
            "/exact/react/index.js",
            "/exact/react-dom/index.js",
        ],
        "stdout": '{"react":"19.2.7","react-dom":"19.2.7"}\n',
        "stderr": "",
        "browser_execution_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    runtime_receipt = {
        **runtime_payload,
        "receipt_sha256": runtime_environment._route_receipt_digest(runtime_payload),
    }
    toolchains = [
        {
            "language": language,
            "version": runtime_environment.EXACT_TOOLCHAIN_VERSIONS[language],
            "executable": f"/exact/{language}",
            "auxiliary": None,
            "profile": (
                [f"react-dependency-profile-sha256={dependency_profile_sha256}"]
                if language == "react"
                else [f"fixture-profile={language}"]
            ),
            "executable_sha256": "3" * 64,
            "auxiliary_sha256": None,
        }
        for language in runtime_environment.ROUTE_RECEIPT_ACTIVE_LANGUAGES
    ]
    flutter_toolchain = next(
        item for item in toolchains if item["language"] == "flutter"
    )
    dart_sdk = {
        "root": "/exact/flutter-sdk",
        "sha256": "4" * 64,
        "record_count": 3,
        "file_count": 2,
        "directory_count": 1,
        "bytes": 1234,
    }
    closure = {"schema": "v1", "trees": {"dart_sdk": dart_sdk}}
    closure_sha256 = runtime_environment._route_receipt_digest(closure)
    flutter_toolchain["auxiliary"] = "/exact/flutter-sdk/bin/dart"
    flutter_toolchain["profile"] = [
        "flutter-build-closure-schema=v1",
        f"flutter-build-closure-sha256={closure_sha256}",
        f"flutter-dart-sdk-tree-sha256={dart_sdk['sha256']}",
        "repository-build=pure-dart-import-free",
        "flutter-ui-semantics=UNSUPPORTED",
    ]
    flutter_receipt = {
        "schema_version": 1,
        "kind": "elmos.flutter-dart-build-toolchain-receipt",
        "language": "flutter",
        "version": flutter_toolchain["version"],
        "closure_sha256": closure_sha256,
        "profile_sha256": runtime_environment._route_receipt_digest(
            flutter_toolchain["profile"]
        ),
        "trees": {"dart_sdk": dart_sdk},
    }
    record_sha256 = {
        str(item["language"]): runtime_environment.exact_toolchain_record_sha256(
            item
        )
        for item in toolchains
    }
    contract_document = {
        "receipt_schema_version": (
            runtime_environment.EXACT_TOOLCHAIN_RECEIPT_SCHEMA_VERSION
        ),
        "active_languages": list(
            runtime_environment.ROUTE_RECEIPT_ACTIVE_LANGUAGES
        ),
        "deprecated_languages": list(
            runtime_environment.EXACT_TOOLCHAIN_DEPRECATED_LANGUAGES
        ),
        "versions": {
            language: runtime_environment.EXACT_TOOLCHAIN_VERSIONS[language]
            for language in runtime_environment.ROUTE_RECEIPT_ACTIVE_LANGUAGES
        },
        "record_sha256": record_sha256,
    }
    contract_sha256 = runtime_environment._route_receipt_digest(
        contract_document
    )
    monkeypatch.setattr(
        runtime_environment,
        "EXACT_TOOLCHAIN_RECORD_SHA256",
        record_sha256,
    )
    monkeypatch.setattr(
        runtime_environment,
        "EXACT_TOOLCHAIN_CONTRACT_SHA256",
        contract_sha256,
    )
    monkeypatch.setattr(
        runtime_environment,
        "exact_toolchain_contract_sha256",
        lambda: contract_sha256,
    )
    bound = {
        "toolchain_contract_sha256": contract_sha256,
        "active_languages": list(runtime_environment.ROUTE_RECEIPT_ACTIVE_LANGUAGES),
        "deprecated_languages": list(
            runtime_environment.EXACT_TOOLCHAIN_DEPRECATED_LANGUAGES
        ),
        "toolchains": toolchains,
        "react_runtime_receipt": runtime_receipt,
        "flutter_build_toolchain_receipt": flutter_receipt,
    }
    return {
        "schema_version": runtime_environment.EXACT_TOOLCHAIN_RECEIPT_SCHEMA_VERSION,
        "kind": "elmos.polyglot-route-exact-toolchain-receipt",
        "status": "READY",
        "claim_ceiling": "TOOLCHAIN_READY",
        "route_execution_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        **bound,
        "receipt_sha256": runtime_environment._route_receipt_digest(bound),
    }


def test_module_constants_and_default_manifest_are_repository_scoped() -> None:
    assert runtime_environment.ROOT == ROOT
    assert runtime_environment.MANIFEST_PATH == ROOT / "toolchains" / "runtime-manifest.json"

    manifest = runtime_environment.load_manifest()

    assert manifest["manifest_id"] == "elmos-language-runtime-matrix-v1"
    assert runtime_environment.validate_manifest(manifest) == []


def test_exact_toolchain_contract_authority_is_complete_and_self_consistent() -> None:
    active = runtime_environment.ROUTE_RECEIPT_ACTIVE_LANGUAGES

    assert runtime_environment.EXACT_TOOLCHAIN_RECEIPT_SCHEMA_VERSION == "1.1.0"
    assert tuple(runtime_environment.EXACT_TOOLCHAIN_VERSIONS) == active
    assert tuple(runtime_environment.EXACT_TOOLCHAIN_RECORD_SHA256) == active
    assert runtime_environment.EXACT_TOOLCHAIN_DEPRECATED_LANGUAGES == (
        "javascript",
    )
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", digest)
        for digest in runtime_environment.EXACT_TOOLCHAIN_RECORD_SHA256.values()
    )
    assert re.fullmatch(
        r"[0-9a-f]{64}",
        runtime_environment.EXACT_TOOLCHAIN_CONTRACT_SHA256,
    )
    assert (
        runtime_environment.exact_toolchain_contract_sha256()
        == runtime_environment.EXACT_TOOLCHAIN_CONTRACT_SHA256
    )


def test_erlang_probe_finds_an_unlinked_homebrew_runtime() -> None:
    assert "/opt/homebrew/opt/erlang/bin/erl" in (
        runtime_environment.PROBE_COMMANDS["erl"].candidate_templates
    )


def test_kotlin_probe_binds_the_route_jdk_and_allows_launcher_startup() -> None:
    probe = runtime_environment.PROBE_COMMANDS["kotlinc"]

    assert dict(probe.environment) == {
        "JAVACMD": (
            "/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/"
            "openjdk.jdk/Contents/Home/bin/java"
        )
    }
    assert probe.timeout_seconds == 45.0


def test_load_manifest_accepts_an_explicit_path(tmp_path: Path) -> None:
    payload = {"schema_version": "test", "profiles": {}, "runtimes": []}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert runtime_environment.load_manifest(path) == payload


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        (
            '{"schema_version":"1.0.0","schema_version":"2.0.0"}',
            "RUNTIME_MANIFEST_DUPLICATE_KEY:schema_version",
        ),
        ('{"value":NaN}', "RUNTIME_MANIFEST_NONFINITE_NUMBER:NaN"),
        ('{"value":Infinity}', "RUNTIME_MANIFEST_NONFINITE_NUMBER:Infinity"),
        ('{"value":-Infinity}', "RUNTIME_MANIFEST_NONFINITE_NUMBER:-Infinity"),
    ],
)
def test_load_manifest_rejects_duplicate_keys_and_nonfinite_numbers(
    tmp_path: Path,
    payload: str,
    expected_error: str,
) -> None:
    path = tmp_path / "invalid-manifest.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match=expected_error):
        runtime_environment.load_manifest(path)


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

    if profile == "routes-macos":
        assert "javascript" not in expected_languages
        assert "javascript" not in runtime_environment.ROUTE_LANGUAGES


def test_exact_route_host_runtimes_are_darwin_arm64_only() -> None:
    manifest = runtime_environment.load_manifest()
    runtimes = _runtime_index(manifest)
    exact_runtime_ids = {
        "kotlin-route-2.2.20",
        "php-route-8.5.9",
        "flutter-3.44.1",
    }

    assert runtime_environment.DARWIN_ARM64_EXACT_RUNTIME_IDS == exact_runtime_ids
    for runtime_id in exact_runtime_ids:
        assert runtimes[runtime_id]["platforms"] == ["darwin-arm64"]

        broken = copy.deepcopy(manifest)
        _runtime_index(broken)[runtime_id]["platforms"].append("linux-arm64")
        errors = runtime_environment.validate_manifest(broken)

        assert any(
            error
            == f"runtime {runtime_id} platforms must be exactly darwin-arm64"
            for error in errors
        )


def test_route_profile_wrong_platform_runs_no_probes_or_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = runtime_environment.load_manifest()

    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("wrong-platform route profile must not inspect the host")

    monkeypatch.setattr(runtime_environment, "_toolchain_root", unexpected)
    monkeypatch.setattr(runtime_environment, "_runtime_result", unexpected)
    monkeypatch.setattr(runtime_environment, "_run_route_exact_receipt", unexpected)

    report = runtime_environment.doctor(
        manifest,
        "routes-macos",
        platform_key="linux-arm64",
        environ={"PATH": "/ambient/path"},
    )

    assert report["status"] == "NOT_APPLICABLE"
    assert report["claim_ceiling"] == "NOT_RUN"
    assert report["platform"] == "linux-arm64"
    assert report["runtimes"] == []
    assert report["profile_checks"] == []


def test_host_bound_route_probes_use_engine_absolute_paths(tmp_path: Path) -> None:
    php_path = "/opt/homebrew/Cellar/php/8.5.9/bin/php"
    flutter_dart_path = "/opt/homebrew/share/flutter/bin/cache/dart-sdk/bin/dart"
    ambient_bin = tmp_path / "ambient-bin"
    ambient_bin.mkdir()
    for executable in ("php", "dart"):
        candidate = ambient_bin / executable
        candidate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        candidate.chmod(0o755)

    for probe_id in ("php-route", "php-route-modules"):
        probe = runtime_environment.PROBE_COMMANDS[probe_id]
        assert probe.path_names == ()
        assert probe.candidate_templates == (php_path,)
        assert probe.executable_env is None
        assert probe.search_path is False
        assert ambient_bin / "php" not in runtime_environment._candidate_executables(
            probe,
            toolchain_root=tmp_path / "toolchains",
            environ={"PATH": str(ambient_bin)},
        )

    flutter_probe = runtime_environment.PROBE_COMMANDS["dart-flutter"]
    assert flutter_probe.path_names == ()
    assert flutter_probe.candidate_templates == (flutter_dart_path,)
    assert flutter_probe.executable_env is None
    assert flutter_probe.search_path is False
    assert ambient_bin / "dart" not in runtime_environment._candidate_executables(
        flutter_probe,
        toolchain_root=tmp_path / "toolchains",
        environ={"PATH": str(ambient_bin)},
    )


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
    assert set().union(*observed_66_80.values()) == _profile_runtime_ids(manifest, "b66-80")


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


def test_validation_rejects_batch_profile_coverage_drift() -> None:
    manifest = runtime_environment.load_manifest()
    broken = copy.deepcopy(manifest)
    broken["profiles"]["b66-80"]["optional"].remove("dotnet-sdk-10.0.301")
    broken["profiles"]["language-packs"]["optional"].append("node-26.0.0")

    errors = runtime_environment.validate_manifest(broken)

    assert any("profile b66-80 must equal batch_bindings.b66-80" in error for error in errors)
    assert any(
        "profile language-packs must equal batch_bindings.b81-95" in error for error in errors
    )


def test_validation_rejects_claim_boundary_promotion() -> None:
    manifest = runtime_environment.load_manifest()
    broken = copy.deepcopy(manifest)
    broken["claim_boundary"]["certification_status"] = "CERTIFIED"
    broken["claim_boundary"]["unexpected"] = "field"

    errors = runtime_environment.validate_manifest(broken)

    assert any(
        "claim_boundary.certification_status must be NOT_CERTIFIED" in error
        for error in errors
    )
    assert any("claim_boundary keys mismatch" in error for error in errors)


def test_validation_rejects_exact_active_profile_runtime_drift() -> None:
    manifest = runtime_environment.load_manifest()

    route_missing_compiler = copy.deepcopy(manifest)
    route_missing_compiler["profiles"]["routes-macos"]["required"].remove(
        "typescript-5.9.2"
    )
    route_errors = runtime_environment.validate_manifest(route_missing_compiler)
    assert any(
        "profile routes-macos required runtime ids mismatch" in error
        and "typescript-5.9.2" in error
        for error in route_errors
    )

    synthesis_wrong_php = copy.deepcopy(manifest)
    synthesis_required = synthesis_wrong_php["profiles"]["synthesis"]["required"]
    synthesis_required.remove("php-8.4.12")
    synthesis_required.append("php-route-8.5.9")
    synthesis_errors = runtime_environment.validate_manifest(synthesis_wrong_php)
    assert any(
        "profile synthesis required runtime ids mismatch" in error
        and "php-8.4.12" in error
        and "php-route-8.5.9" in error
        for error in synthesis_errors
    )

    route_optional = copy.deepcopy(manifest)
    route_required = route_optional["profiles"]["routes-macos"]["required"]
    route_required.remove("react-19.2.7")
    route_optional["profiles"]["routes-macos"]["optional"].append("react-19.2.7")
    optional_errors = runtime_environment.validate_manifest(route_optional)
    assert any(
        "profile routes-macos optional runtimes must be empty" in error
        for error in optional_errors
    )


def test_doctor_accepts_an_exact_managed_probe_and_rejects_version_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = runtime_environment.load_manifest()
    manifest["profiles"]["fixture"] = {
        "description": "single deterministic test runtime",
        "platforms": ["darwin-arm64"],
        "required": ["node-26.0.0"],
        "optional": [],
    }
    monkeypatch.setattr(
        runtime_environment,
        "REQUIRED_PROFILES",
        runtime_environment.REQUIRED_PROFILES | {"fixture"},
    )
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


def test_route_receipt_validator_rejects_language_and_claim_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _valid_route_receipt(monkeypatch)
    assert runtime_environment._validate_route_receipt(receipt) == receipt

    language_drift = copy.deepcopy(receipt)
    language_drift["active_languages"][-1] = "javascript"
    with pytest.raises(ValueError, match="ROUTE_EXACT_RECEIPT_CONTRACT_INVALID"):
        runtime_environment._validate_route_receipt(language_drift)

    certification_drift = copy.deepcopy(receipt)
    certification_drift["react_runtime_receipt"]["certification_status"] = "CERTIFIED"
    with pytest.raises(ValueError, match="ROUTE_EXACT_RECEIPT_REACT_RUNTIME_INVALID"):
        runtime_environment._validate_route_receipt(certification_drift)

    self_consistent_stdout_drift = copy.deepcopy(receipt)
    inner = self_consistent_stdout_drift["react_runtime_receipt"]
    inner["stdout"] = '{"react":"0.0.0","react-dom":"19.2.7"}\n'
    inner["receipt_sha256"] = runtime_environment._route_receipt_digest(
        {key: value for key, value in inner.items() if key != "receipt_sha256"}
    )
    _rebind_route_receipt(self_consistent_stdout_drift)
    with pytest.raises(ValueError, match="ROUTE_EXACT_RECEIPT_REACT_RUNTIME_INVALID"):
        runtime_environment._validate_route_receipt(self_consistent_stdout_drift)

    flutter_drift = copy.deepcopy(receipt)
    flutter_drift["flutter_build_toolchain_receipt"]["trees"]["dart_sdk"][
        "sha256"
    ] = "0" * 64
    with pytest.raises(ValueError, match="ROUTE_EXACT_RECEIPT_FLUTTER_BUILD_INVALID"):
        runtime_environment._validate_route_receipt(flutter_drift)


@pytest.mark.parametrize(
    "language",
    runtime_environment.ROUTE_RECEIPT_ACTIVE_LANGUAGES,
)
def test_route_receipt_rejects_each_exact_toolchain_version_drift(
    monkeypatch: pytest.MonkeyPatch,
    language: str,
) -> None:
    receipt = _valid_route_receipt(monkeypatch)
    toolchain = next(
        item for item in receipt["toolchains"] if item["language"] == language
    )
    toolchain["version"] = f"exact-{language}"
    _rebind_route_receipt(receipt)

    with pytest.raises(
        ValueError,
        match=f"ROUTE_EXACT_RECEIPT_TOOLCHAIN_VERSION_INVALID:{language}",
    ):
        runtime_environment._validate_route_receipt(receipt)


@pytest.mark.parametrize(
    "language",
    runtime_environment.ROUTE_RECEIPT_ACTIVE_LANGUAGES,
)
def test_route_receipt_rejects_each_exact_toolchain_profile_drift(
    monkeypatch: pytest.MonkeyPatch,
    language: str,
) -> None:
    receipt = _valid_route_receipt(monkeypatch)
    toolchain = next(
        item for item in receipt["toolchains"] if item["language"] == language
    )
    toolchain["profile"].append("unexpected-profile-drift=true")
    _rebind_route_receipt(receipt)

    with pytest.raises(
        ValueError,
        match=f"ROUTE_EXACT_RECEIPT_TOOLCHAIN_RECORD_INVALID:{language}",
    ):
        runtime_environment._validate_route_receipt(receipt)


@pytest.mark.parametrize(
    "language",
    runtime_environment.ROUTE_RECEIPT_ACTIVE_LANGUAGES,
)
def test_route_receipt_rejects_each_full_record_drift(
    monkeypatch: pytest.MonkeyPatch,
    language: str,
) -> None:
    receipt = _valid_route_receipt(monkeypatch)
    toolchain = next(
        item for item in receipt["toolchains"] if item["language"] == language
    )
    toolchain["executable"] = f"{toolchain['executable']}.drift"
    _rebind_route_receipt(receipt)

    with pytest.raises(
        ValueError,
        match=f"ROUTE_EXACT_RECEIPT_TOOLCHAIN_RECORD_INVALID:{language}",
    ):
        runtime_environment._validate_route_receipt(receipt)


def test_route_receipt_rejects_self_consistent_contract_field_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _valid_route_receipt(monkeypatch)
    receipt["toolchain_contract_sha256"] = "0" * 64
    _rebind_route_receipt(receipt)

    with pytest.raises(ValueError, match="ROUTE_EXACT_RECEIPT_CONTRACT_INVALID"):
        runtime_environment._validate_route_receipt(receipt)


def test_route_receipt_rejects_contract_authority_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _valid_route_receipt(monkeypatch)
    monkeypatch.setattr(
        runtime_environment,
        "exact_toolchain_contract_sha256",
        lambda: "0" * 64,
    )

    with pytest.raises(ValueError, match="ROUTE_EXACT_RECEIPT_AUTHORITY_INVALID"):
        runtime_environment._validate_route_receipt(receipt)


@pytest.mark.parametrize("profile", ["routes-macos", "all"])
def test_route_profiles_require_the_engine_exact_receipt(
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
) -> None:
    manifest = runtime_environment.load_manifest()

    def ready_runtime(runtime: dict, *, required: bool, **_kwargs: object) -> dict:
        return {
            "id": runtime["id"],
            "display_name": runtime["display_name"],
            "languages": runtime["languages"],
            "version": runtime["version"],
            "required": required,
            "install_policy": runtime["install_policy"],
            "notes": runtime.get("notes"),
            "status": "READY",
            "blocking_reason": None,
            "probes": [],
        }

    monkeypatch.setattr(runtime_environment, "_runtime_result", ready_runtime)
    monkeypatch.setattr(
        runtime_environment,
        "_run_route_exact_receipt",
        lambda *_args, **_kwargs: {
            "kind": "route-engine-exact-toolchain-receipt",
            "status": "BLOCKED",
            "claim_ceiling": "NOT_RUN",
            "blocking_reason": "fixture",
        },
    )
    blocked = runtime_environment.doctor(
        manifest,
        profile,
        platform_key="darwin-arm64",
        environ={},
    )
    assert blocked["status"] == "BLOCKED"
    assert blocked["claim_ceiling"] == "NOT_RUN"

    monkeypatch.setattr(
        runtime_environment,
        "_run_route_exact_receipt",
        lambda *_args, **_kwargs: {
            "kind": "route-engine-exact-toolchain-receipt",
            "status": "READY",
            "claim_ceiling": "TOOLCHAIN_READY",
        },
    )
    ready = runtime_environment.doctor(
        manifest,
        profile,
        platform_key="darwin-arm64",
        environ={},
    )
    assert ready["status"] == "READY"
    assert ready["claim_ceiling"] == "TOOLCHAIN_READY"


def test_doctor_never_promotes_vendor_or_external_runtimes(
    tmp_path: Path,
) -> None:
    manifest = runtime_environment.load_manifest()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(bin_dir, "cobc", "cobc 3.2.0")
    _write_executable(bin_dir, "sf", "@salesforce/cli/2.100.0 darwin-arm64 node-v26")
    _write_executable(bin_dir, "salesforce", "@salesforce/cli/2.100.0")
    _write_executable(bin_dir, "gleam", "gleam 1.18.1")
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


def test_route_env_does_not_shadow_absolute_php_route_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = runtime_environment.load_manifest()
    toolchain_root = tmp_path / "isolated-toolchains"
    kotlin_bin = toolchain_root / "kotlin" / "2.2.20" / "bin"
    route_php_bin = toolchain_root / "php" / "8.5.9" / "bin"
    kotlin_bin.mkdir(parents=True)
    route_php_bin.mkdir(parents=True)
    monkeypatch.setattr(runtime_environment, "_platform_key", lambda: "darwin-arm64")
    monkeypatch.setattr(runtime_environment, "_java_home", lambda *_: None)
    monkeypatch.setattr(runtime_environment, "_selected_python", lambda *_: None)

    rendered = runtime_environment.render_env(
        manifest,
        "routes-macos",
        environ={
            "PATH": "",
            "ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT": str(toolchain_root),
        },
    )

    assert str(kotlin_bin) in rendered
    assert str(route_php_bin) not in rendered
    assert "/opt/homebrew/Cellar/php/8.5.9/bin" not in rendered


def test_route_env_rejects_the_wrong_host_platform_before_host_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = runtime_environment.load_manifest()
    monkeypatch.setattr(runtime_environment, "_platform_key", lambda: "linux-arm64")

    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("wrong-platform env rendering must not inspect the host")

    monkeypatch.setattr(runtime_environment, "_toolchain_root", unexpected)

    with pytest.raises(
        ValueError,
        match="RUNTIME_PROFILE_PLATFORM_NOT_APPLICABLE:routes-macos:linux-arm64",
    ):
        runtime_environment.render_env(manifest, "routes-macos", environ={"PATH": ""})


@pytest.mark.parametrize("dry_run", [True, False])
def test_route_install_rejects_the_wrong_host_platform_before_any_action(
    monkeypatch: pytest.MonkeyPatch,
    dry_run: bool,
) -> None:
    manifest = runtime_environment.load_manifest()
    monkeypatch.setattr(runtime_environment, "_platform_key", lambda: "linux-arm64")

    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("wrong-platform install must not inspect or mutate the host")

    monkeypatch.setattr(runtime_environment, "_toolchain_root", unexpected)
    monkeypatch.setattr(runtime_environment, "_install_steps", unexpected)

    code, report = runtime_environment._run_install(
        manifest,
        "routes-macos",
        dry_run=dry_run,
        environ={"PATH": "/ambient/path"},
    )

    assert code == 2
    assert report == {
        "status": "NOT_APPLICABLE",
        "claim_ceiling": "NOT_RUN",
        "profile": "routes-macos",
        "platform": "linux-arm64",
        "allowed_platforms": ["darwin-arm64"],
        "blocking_reason": (
            "RUNTIME_PROFILE_PLATFORM_NOT_APPLICABLE:routes-macos:linux-arm64"
        ),
    }


def test_cli_doctor_rejects_a_platform_override_that_mismatches_the_host(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(runtime_environment, "_platform_key", lambda: "linux-arm64")

    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("mismatched CLI platform must not run doctor")

    monkeypatch.setattr(runtime_environment, "doctor", unexpected)

    code = runtime_environment.main(
        ["doctor", "--profile", "routes-macos", "--platform", "darwin-arm64", "--json"]
    )
    output = capsys.readouterr()

    assert code == 2
    assert output.out == ""
    assert (
        "RUNTIME_PLATFORM_OVERRIDE_MISMATCH:"
        "requested=darwin-arm64:actual=linux-arm64"
    ) in output.err


def test_main_validates_the_default_manifest(capsys: pytest.CaptureFixture[str]) -> None:
    assert runtime_environment.main(["validate"]) == 0
    output = capsys.readouterr()
    assert "VALID" in output.out.upper()


def test_toolchain_root_authorities_must_agree(tmp_path: Path) -> None:
    manifest = runtime_environment.load_manifest()
    with pytest.raises(ValueError, match="RUNTIME_TOOLCHAIN_ROOT_CONFLICT"):
        runtime_environment._toolchain_root(
            manifest,
            {
                "ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT": str(tmp_path / "synthesis"),
                "ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT": str(tmp_path / "routes"),
            },
        )


def test_runtime_manifest_schema_matches_fail_closed_structural_rules() -> None:
    manifest = runtime_environment.load_manifest()
    schema = json.loads(
        (ROOT / "schemas" / "toolchains" / "runtime-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    assert list(validator.iter_errors(manifest)) == []
    assert runtime_environment.validate_manifest(manifest) == []

    invalid_documents = []
    missing_schema = copy.deepcopy(manifest)
    missing_schema.pop("$schema")
    invalid_documents.append(missing_schema)
    extra_profile = copy.deepcopy(manifest)
    extra_profile["profiles"]["future"] = copy.deepcopy(extra_profile["profiles"]["core"])
    invalid_documents.append(extra_profile)
    empty_batch = copy.deepcopy(manifest)
    empty_batch["batch_bindings"]["b66-80"]["66"] = []
    invalid_documents.append(empty_batch)

    for document in invalid_documents:
        assert list(validator.iter_errors(document))
        assert runtime_environment.validate_manifest(document)

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route import native
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.toolchains import (
    ExactToolchain,
    exact_toolchain,
)

ENGINE_ROOT = Path(__file__).resolve().parents[1]
RUST_PACKAGE = ENGINE_ROOT / "native/rust"
EXPECTED_REGISTRY_PACKAGES = {
    "itoa-1.0.18": "8f42a60cbdf9a97f5d2305f08a87dc4e09308d1276d28c869c684d7777685682",
    "memchr-2.8.3": "cf8baf1c55e62ffcace7a9f06f4bd9cd3f0c4beb022d3b367256b91b87513d98",
    "proc-macro2-1.0.107": "985e7ec9bb745e6ce6535b544d84d6cd6f7ad8bd711c398938ae983b91a766d9",
    "quote-1.0.47": "1fbf4db142a473a8d80c26bbf18454ed458bf8d26c8219c331daecfdbd079001",
    "ryu-1.0.23": "9774ba4a74de5f7b1c1451ed6cd5285a32eddb5cccb8cc655a4e50009e06477f",
    "serde-1.0.219": "5f0e2c6ed6606019b4e29e69dbaba95b11854410e5347d525002456dbbb786b6",
    "serde_derive-1.0.219": "5b0276cf7f2c73365f7157c8123c21cd9a50fbbd844757af28ca1f5925fc2a00",
    "serde_json-1.0.143": "d401abef1d108fbd9cbaebc3e46611f4b1021f714a0597a71f41ee463f5f4a5a",
    "syn-2.0.119": "872831b642d1a07999a962a351ed35b955ea2cfc8f3862091e2a240a84f17297",
    "unicode-ident-1.0.24": "e6e4313cd5fcd3dad5cafa179702e2b244f760991f45397d14d4ebf38247da75",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def rust_toolchain() -> ExactToolchain:
    toolchain = exact_toolchain("rust")
    assert toolchain.auxiliary is not None
    return toolchain


def _tree_receipt(root: Path) -> dict[str, object]:
    if not root.exists():
        return {"exists": False}

    def metadata(path: Path) -> dict[str, object]:
        observed = path.lstat()
        record: dict[str, object] = {
            "mode": f"{stat.S_IMODE(observed.st_mode):04o}",
            "uid": observed.st_uid,
            "gid": observed.st_gid,
            "nlink": observed.st_nlink,
            "bytes": observed.st_size,
            "mtime_ns": observed.st_mtime_ns,
            "ctime_ns": observed.st_ctime_ns,
        }
        if stat.S_ISREG(observed.st_mode):
            record["kind"] = "file"
            record["sha256"] = _sha256(path)
        elif stat.S_ISDIR(observed.st_mode):
            record["kind"] = "directory"
        elif stat.S_ISLNK(observed.st_mode):
            record["kind"] = "symlink"
            record["target"] = path.readlink().as_posix()
        else:
            record["kind"] = "special"
        return record

    return {
        "exists": True,
        "root": metadata(root),
        "entries": {
            path.relative_to(root).as_posix(): metadata(path)
            for path in sorted(root.rglob("*"))
        },
    }


def _write_sample(source: Path) -> None:
    source.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    source.write_text(
        "pub fn total(value: i64) -> i64 { value }\n",
        encoding="utf-8",
    )


def test_rust_vendor_exactly_closes_locked_registry_inputs() -> None:
    configuration = tomllib.loads(
        (RUST_PACKAGE / ".cargo/config.toml").read_text(encoding="utf-8")
    )
    assert configuration == {
        "net": {"offline": True},
        "source": {
            "crates-io": {"replace-with": "vendored-sources"},
            "vendored-sources": {"directory": "vendor"},
        },
    }

    lock = tomllib.loads((RUST_PACKAGE / "Cargo.lock").read_text(encoding="utf-8"))
    locked_registry = {
        f"{package['name']}-{package['version']}": package["checksum"]
        for package in lock["package"]
        if package.get("source") == "registry+https://github.com/rust-lang/crates.io-index"
    }
    assert locked_registry == EXPECTED_REGISTRY_PACKAGES

    vendor = RUST_PACKAGE / "vendor"
    vendor_directories = {
        path.name for path in vendor.iterdir() if path.is_dir() and not path.is_symlink()
    }
    assert vendor_directories == set(EXPECTED_REGISTRY_PACKAGES)
    assert not [path for path in vendor.rglob("*") if path.is_symlink()]

    for directory_name, package_checksum in EXPECTED_REGISTRY_PACKAGES.items():
        crate = vendor / directory_name
        checksum_path = crate / ".cargo-checksum.json"
        checksum = json.loads(checksum_path.read_text(encoding="utf-8"))
        assert set(checksum) == {"files", "package"}
        assert checksum["package"] == package_checksum
        expected_files = checksum["files"]
        observed_files = {
            path.relative_to(crate).as_posix()
            for path in crate.rglob("*")
            if path.is_file() and path != checksum_path
        }
        assert set(expected_files) == observed_files
        assert {
            relative: _sha256(crate / relative)
            for relative in sorted(observed_files)
        } == expected_files


def test_rust_inventory_builds_with_sanitized_empty_home_and_vendor(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.rs"
    _write_sample(source)
    live_target = RUST_PACKAGE / "target"
    target_before = _tree_receipt(live_target)

    inventory = native.inventory_module(source, "rust")

    target_after = _tree_receipt(live_target)
    assert inventory["source_language"] == "rust"
    assert inventory["enumeration_status"] == "PASSED"
    assert [subject["name"] for subject in inventory["subjects"]] == ["total"]
    assert target_after == target_before


@pytest.mark.parametrize("returncode", [0, 17])
def test_native_run_cleans_private_cargo_environment_on_success_and_failure(
    rust_toolchain: ExactToolchain,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
) -> None:
    assert rust_toolchain.auxiliary is not None
    source = tmp_path / "sample.rs"
    _write_sample(source)
    observed_roots: list[Path] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        home = Path(environment["HOME"])
        temporary = Path(environment["TMPDIR"])
        cargo_home = Path(environment["CARGO_HOME"])
        cargo_target = Path(environment["CARGO_TARGET_DIR"])
        root = home.parent
        assert {path.parent for path in (home, temporary, cargo_home, cargo_target)} == {root}
        assert environment["CARGO_NET_OFFLINE"] == "true"
        assert all(path.is_dir() for path in (home, temporary, cargo_home, cargo_target))
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o700 for path in (home, temporary, cargo_home, cargo_target))
        assert not any(cargo_target.iterdir())
        assert cargo_target != RUST_PACKAGE / "target"
        observed_roots.append(root)
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout="{}\n" if returncode == 0 else "",
            stderr="forced cargo failure" if returncode else "",
        )

    monkeypatch.setattr(native.subprocess, "run", fake_run)
    command = [
        rust_toolchain.auxiliary,
        "run",
        "--quiet",
        "--offline",
        "--locked",
        "--manifest-path",
        str(RUST_PACKAGE / "Cargo.toml"),
        "--",
        str(source),
        "--inventory",
    ]
    if returncode:
        with pytest.raises(RouteError, match="forced cargo failure"):
            native._run(
                command,
                cwd=RUST_PACKAGE,
                timeout=900,
                isolated_cargo=True,
            )
    else:
        assert native._run(
            command,
            cwd=RUST_PACKAGE,
            timeout=900,
            isolated_cargo=True,
        ) == {}
    assert len(observed_roots) == 1
    assert not observed_roots[0].exists()


def test_rust_inventory_and_analyze_dispatchers_require_isolated_cargo(
    rust_toolchain: ExactToolchain,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sample.rs"
    _write_sample(source)
    calls: list[tuple[list[str], Path, int, bool, Path | None]] = []

    def stop_after_dispatch(
        command: list[str],
        *,
        cwd: Path,
        timeout: int = 120,
        isolated_cargo: bool = False,
        cargo_package: Path | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        calls.append((command, cwd, timeout, isolated_cargo, cargo_package))
        raise RouteError("TEST_RUST_DISPATCH_REACHED")

    monkeypatch.setattr(native, "exact_toolchain", lambda _language: rust_toolchain)
    monkeypatch.setattr(native, "_run", stop_after_dispatch)
    with pytest.raises(RouteError, match="TEST_RUST_DISPATCH_REACHED"):
        native.inventory_module(source, "rust")
    with pytest.raises(RouteError, match="TEST_RUST_DISPATCH_REACHED"):
        native.analyze(source, "rust", "total")

    assert len(calls) == 2
    for command, cwd, timeout, isolated_cargo, cargo_package in calls:
        assert command[1:6] == [
            "run",
            "--quiet",
            "--offline",
            "--locked",
            "--manifest-path",
        ]
        assert command[6] == str(RUST_PACKAGE / "Cargo.toml")
        assert cwd == RUST_PACKAGE
        assert timeout == 900
        assert isolated_cargo is True
        assert cargo_package == RUST_PACKAGE


@pytest.mark.parametrize("mutation", ["missing", "tampered"])
def test_rust_inventory_fails_closed_when_vendor_is_incomplete_or_modified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    isolated_engine = tmp_path / "engine"
    isolated = isolated_engine / "native/rust"
    shutil.copytree(
        RUST_PACKAGE,
        isolated,
        ignore=shutil.ignore_patterns("target"),
    )
    syn = isolated / "vendor/syn-2.0.119"
    if mutation == "missing":
        shutil.rmtree(syn)
    else:
        source = syn / "src/lib.rs"
        source.write_bytes(source.read_bytes() + b"\n// tampered\n")

    sample = tmp_path / "run/sample.rs"
    _write_sample(sample)
    monkeypatch.setattr(native, "ENGINE_ROOT", isolated_engine)
    with pytest.raises(RouteError) as raised:
        native.inventory_module(sample, "rust")
    assert not (isolated / "target").exists()
    if mutation == "tampered":
        assert "checksum" in str(raised.value).lower()
    else:
        assert "searched package name: `syn`" in str(raised.value)

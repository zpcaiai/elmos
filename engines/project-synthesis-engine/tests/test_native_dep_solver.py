from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from elmos_project_synthesis import native_dep_solver_bridge as bridge
from elmos_project_synthesis.native_dep_solver_bridge import native_solve_dependencies


class _FakeFunction:
    def __init__(self, result: object = None) -> None:
        self.argtypes: list[object] | None = None
        self.restype: object = None
        self.result = result
        self.calls: list[tuple[object, ...]] = []

    def __call__(self, *args: object) -> object:
        self.calls.append(args)
        return self.result


class _FakeLibrary:
    def __init__(self) -> None:
        self.elmos_solve_dependencies = _FakeFunction()
        self.elmos_free_string = _FakeFunction()


def test_native_dep_solver_resolution() -> None:
    roots = [
        {"package": "flask", "constraints": "^3.0.0"},
        {"package": "werkzeug", "constraints": ">=3.0.0"},
    ]
    available = {
        "flask": [
            {"version": "3.0.2", "dependencies": [{"package": "werkzeug", "constraints": "^3.0.0"}]},
            {"version": "2.3.3", "dependencies": []},
        ],
        "werkzeug": [
            {"version": "3.0.1", "dependencies": []},
            {"version": "2.3.7", "dependencies": []},
        ],
    }

    result = native_solve_dependencies(roots, available)
    assert result is not None
    assert result["status"] == "SOLVED"
    assert result["solution"]["flask"] == "3.0.2"
    assert result["solution"]["werkzeug"] == "3.0.1"


def test_native_dep_solver_conflict() -> None:
    roots = [
        {"package": "pkg-a", "constraints": "*"},
        {"package": "pkg-b", "constraints": "*"},
    ]
    available = {
        "pkg-a": [
            {"version": "1.0.0", "dependencies": [{"package": "common", "constraints": "^1.0.0"}]}
        ],
        "pkg-b": [
            {"version": "1.0.0", "dependencies": [{"package": "common", "constraints": "^2.0.0"}]}
        ],
        "common": [
            {"version": "1.0.0", "dependencies": []},
            {"version": "2.0.0", "dependencies": []},
        ],
    }

    result = native_solve_dependencies(roots, available)
    assert result is not None
    assert result["status"] == "CONFLICT"


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("darwin", "libelmos_native.dylib"),
        ("linux", "libelmos_native.so"),
        ("linux-musl", "libelmos_native.so"),
        ("win32", "elmos_native.dll"),
        ("freebsd14", None),
    ],
)
def test_native_library_filename_is_platform_exact(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    expected: str | None,
) -> None:
    monkeypatch.setattr(bridge.sys, "platform", platform)
    assert bridge._library_filename() == expected


def test_native_library_load_retries_after_artifact_appears(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "libelmos_native.so"
    artifact.write_bytes(b"test-placeholder")
    candidates = iter([None, artifact])
    fake_library = _FakeLibrary()
    loaded_paths: list[str] = []

    monkeypatch.setattr(bridge, "_LIB", None)
    monkeypatch.setattr(bridge, "_LIB_PATH", None)
    monkeypatch.setattr(bridge, "_find_library", lambda: next(candidates))

    def fake_cdll(path: str) -> Any:
        loaded_paths.append(path)
        return fake_library

    monkeypatch.setattr(bridge.ctypes, "CDLL", fake_cdll)

    assert bridge._get_lib() is None
    assert bridge._get_lib() is fake_library
    assert loaded_paths == [str(artifact.resolve())]


def test_native_library_explicit_binding_is_absolute_regular_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ELMOS_NATIVE_LIB", "relative/libelmos_native.so")
    assert bridge._find_library() is None

    directory = tmp_path / "native-directory"
    directory.mkdir()
    monkeypatch.setenv("ELMOS_NATIVE_LIB", str(directory))
    assert bridge._find_library() is None

    artifact = tmp_path / "libelmos_native.so"
    artifact.write_bytes(b"test-placeholder")
    monkeypatch.setenv("ELMOS_NATIVE_LIB", str(artifact))
    assert bridge._find_library() is None


def test_native_library_rejects_symlink_and_home_expansion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "libelmos_native.so"
    artifact.write_bytes(b"test-placeholder")
    link = tmp_path / "linked-native.so"
    link.symlink_to(artifact)

    monkeypatch.setenv("ELMOS_NATIVE_LIB", str(link))
    assert bridge._find_library() is None
    monkeypatch.setenv("ELMOS_NATIVE_LIB", "~/libelmos_native.so")
    assert bridge._find_library() is None


def test_native_library_accepts_only_owned_repository_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "target" / "release" / "libelmos_native.so"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"test-placeholder")
    monkeypatch.setattr(bridge, "_repository_candidates", lambda: (artifact,))
    monkeypatch.setenv("ELMOS_NATIVE_LIB", str(artifact))

    assert bridge._find_library() == artifact.resolve()

    artifact.chmod(0o777)
    assert bridge._find_library() is None


def test_native_solver_frees_invalid_native_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_library = _FakeLibrary()
    fake_library.elmos_solve_dependencies.result = 1234
    monkeypatch.setattr(bridge, "_get_lib", lambda: fake_library)
    monkeypatch.setattr(bridge.ctypes, "string_at", lambda _ptr: b"{")

    result = native_solve_dependencies([], {})

    assert result is None
    assert fake_library.elmos_free_string.calls == [(1234,)]

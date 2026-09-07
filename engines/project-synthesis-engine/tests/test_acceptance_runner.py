from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _load_runner() -> ModuleType:
    script = Path(__file__).parents[1] / "scripts" / "run_acceptance.py"
    spec = importlib.util.spec_from_file_location("project_synthesis_acceptance_runner", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runner() -> ModuleType:
    return _load_runner()


def _passed_evidence(language: str, port: int) -> dict[str, Any]:
    return {
        "status": "PASSED",
        "environment": {"exact_toolchain_match": {language: True}},
        "results": [
            {
                "language": language,
                "kind": "toolchain",
                "command": [language, "--version"],
                "status": "PASSED",
                "exit_code": 0,
                "output": "exact",
            },
            {
                "language": language,
                "kind": "startup-probe",
                "command": [language, "serve"],
                "status": "PASSED",
                "exit_code": 0,
                "output": "",
                "port": port,
                "response": {"status": "UP"},
            },
        ],
    }


def test_acceptance_validates_complete_graph_then_runs_isolated_targets(
    runner: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    directories = iter(
        [
            tmp_path / "elmos-project-synthesis-complete-1",
            tmp_path / "elmos-project-synthesis-java-1",
            tmp_path / "elmos-project-synthesis-rust-1",
        ]
    )
    workspace_languages: dict[Path, tuple[str, ...]] = {}

    def fake_temporary(*, suffix: str) -> Path:
        directory = next(directories)
        directory.mkdir()
        events.append(f"temporary:{suffix}")
        return directory

    def fake_request(languages: tuple[str, ...]) -> dict[str, Any]:
        return {"languages": languages}

    def fake_generate(request: dict[str, Any], workspace: Path) -> dict[str, Any]:
        languages = tuple(request["languages"])
        workspace.mkdir()
        workspace_languages[workspace] = languages
        events.append(f"generate:{','.join(languages)}")
        return {"file_count": 73 if len(languages) == 2 else 41}

    def fake_validate(workspace: Path) -> None:
        assert workspace_languages[workspace] == ("java", "rust")
        events.append("validate:java,rust")

    def fake_verify(workspace: Path, *, use_ephemeral_runtime_ports: bool) -> dict[str, Any]:
        assert use_ephemeral_runtime_ports is True
        language = workspace_languages[workspace][0]
        events.append(f"verify:{language}")
        return _passed_evidence(language, 41_000 + len(events))

    def fake_cleanup(directory: Path) -> str | None:
        events.append(f"cleanup:{directory.name.split('-')[-2]}")
        shutil.rmtree(directory)
        return None

    monkeypatch.setattr(runner, "_new_temporary_directory", fake_temporary)
    monkeypatch.setattr(runner, "_approved_request", fake_request)
    monkeypatch.setattr(runner, "generate_workspace", fake_generate)
    monkeypatch.setattr(runner, "validate_workspace_graphs", fake_validate)
    monkeypatch.setattr(runner, "verify_workspace", fake_verify)
    monkeypatch.setattr(runner, "_cleanup", fake_cleanup)

    result = runner.run_acceptance(("java", "rust"), require_all_toolchains=True)

    assert events == [
        "temporary:complete",
        "generate:java,rust",
        "validate:java,rust",
        "cleanup:complete",
        "temporary:java",
        "generate:java",
        "verify:java",
        "cleanup:java",
        "temporary:rust",
        "generate:rust",
        "verify:rust",
        "cleanup:rust",
    ]
    assert result["status"] == "PASSED"
    assert result["workspace_graph_status"] == "PASSED"
    assert result["execution_strategy"] == "sequential-isolated-workspaces"
    assert result["generated_file_count"] == 73
    assert result["build_and_analysis_count"] == 2
    assert result["cleanup_status"] == "PASSED"
    assert result["language_matrix"] == {
        "java": {"status": "PASSED", "exact_toolchain": True, "startup_probe": "PASSED"},
        "rust": {"status": "PASSED", "exact_toolchain": True, "startup_probe": "PASSED"},
    }


def test_complete_graph_failure_blocks_all_native_verification(
    runner: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary = tmp_path / "elmos-project-synthesis-complete-1"
    verified: list[Path] = []

    def fake_temporary(*, suffix: str) -> Path:
        assert suffix == "complete"
        temporary.mkdir()
        return temporary

    def fake_generate(_request: dict[str, Any], workspace: Path) -> dict[str, Any]:
        workspace.mkdir()
        return {"file_count": 70}

    def fake_validate(_workspace: Path) -> None:
        raise RuntimeError("GRAPH_DIGEST_MISMATCH")

    def fake_verify(workspace: Path, *, use_ephemeral_runtime_ports: bool) -> dict[str, Any]:
        verified.append(workspace)
        return {}

    monkeypatch.setattr(runner, "_new_temporary_directory", fake_temporary)
    monkeypatch.setattr(runner, "_approved_request", lambda languages: {"languages": languages})
    monkeypatch.setattr(runner, "generate_workspace", fake_generate)
    monkeypatch.setattr(runner, "validate_workspace_graphs", fake_validate)
    monkeypatch.setattr(runner, "verify_workspace", fake_verify)
    monkeypatch.setattr(runner, "_cleanup", lambda directory: (shutil.rmtree(directory), None)[1])

    result = runner.run_acceptance(("java", "rust"), require_all_toolchains=False)

    assert verified == []
    assert result["status"] == "FAILED"
    assert result["workspace_graph_status"] == "FAILED"
    assert result["cleanup_status"] == "PASSED"
    assert result["language_matrix"]["java"]["status"] == "NOT_RUN"
    assert result["language_matrix"]["rust"]["status"] == "NOT_RUN"
    assert result["failures"][0]["kind"] == "generation-graph-validation"


def test_cleanup_failure_stops_following_target_and_fails_closed(
    runner: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directories = iter(
        [
            tmp_path / "elmos-project-synthesis-complete-1",
            tmp_path / "elmos-project-synthesis-java-1",
        ]
    )
    workspace_languages: dict[Path, tuple[str, ...]] = {}
    verified: list[str] = []

    def fake_temporary(*, suffix: str) -> Path:
        directory = next(directories)
        directory.mkdir()
        return directory

    def fake_generate(request: dict[str, Any], workspace: Path) -> dict[str, Any]:
        workspace.mkdir()
        workspace_languages[workspace] = tuple(request["languages"])
        return {"file_count": 70}

    def fake_verify(workspace: Path, *, use_ephemeral_runtime_ports: bool) -> dict[str, Any]:
        language = workspace_languages[workspace][0]
        verified.append(language)
        return _passed_evidence(language, 41_001)

    cleanup_calls = 0

    def fake_cleanup(directory: Path) -> str | None:
        nonlocal cleanup_calls
        cleanup_calls += 1
        if cleanup_calls == 2:
            return "OSError:28"
        shutil.rmtree(directory)
        return None

    monkeypatch.setattr(runner, "_new_temporary_directory", fake_temporary)
    monkeypatch.setattr(runner, "_approved_request", lambda languages: {"languages": languages})
    monkeypatch.setattr(runner, "generate_workspace", fake_generate)
    monkeypatch.setattr(runner, "validate_workspace_graphs", lambda workspace: None)
    monkeypatch.setattr(runner, "verify_workspace", fake_verify)
    monkeypatch.setattr(runner, "_cleanup", fake_cleanup)

    result = runner.run_acceptance(("java", "rust"), require_all_toolchains=True)

    assert verified == ["java"]
    assert result["status"] == "FAILED"
    assert result["cleanup_status"] == "FAILED"
    assert result["cleanup_error"] == "OSError:28"
    assert result["language_matrix"]["java"]["status"] == "FAILED"
    assert result["language_matrix"]["rust"]["status"] == "NOT_RUN"
    assert runner._exit_code(result, require_all_toolchains=True) == 1


def test_require_all_toolchains_retains_partial_exit_code(runner: ModuleType) -> None:
    partial = {"status": "PARTIAL"}
    assert runner._exit_code(partial, require_all_toolchains=True) == 2
    assert runner._exit_code(partial, require_all_toolchains=False) == 0
    assert runner._exit_code({"status": "PASSED"}, require_all_toolchains=True) == 0

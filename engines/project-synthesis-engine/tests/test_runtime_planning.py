from __future__ import annotations

import json
from pathlib import Path

import pytest

from elmos_project_synthesis import verification


def test_runtime_plan_preserves_target_when_exact_toolchain_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "requirements").mkdir(parents=True)
    (workspace / "typescript").mkdir()
    (workspace / "requirements" / "project-blueprint.json").write_text(
        json.dumps(
            {
                "applications": [
                    {
                        "language": "typescript",
                        "port": 3001,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(verification, "_runtime_tool", lambda *_args, **_kwargs: None)

    plans = verification.runtime_commands(workspace)

    assert plans == [
        {
            "language": "typescript",
            "cwd": str((workspace / "typescript").resolve()),
            "command": ["pnpm", "start"],
            "environment": {"PORT": "3001", "HOST": "127.0.0.1"},
            "port": 3001,
            "execution_status": "NOT_RUN",
            "blocking_reason": "EXACT_TOOLCHAIN_NOT_AVAILABLE:typescript:pnpm",
        }
    ]


def test_runtime_plan_acceptance_port_override_is_explicit_and_validated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "requirements").mkdir(parents=True)
    (workspace / "typescript").mkdir()
    (workspace / "requirements" / "project-blueprint.json").write_text(
        json.dumps({"applications": [{"language": "typescript", "port": 3001}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(verification, "_runtime_tool", lambda *_args, **_kwargs: "pnpm")

    plan = verification.runtime_commands(
        workspace,
        port_overrides={"typescript": 43123},
    )[0]

    assert plan["port"] == 43123
    assert plan["environment"]["PORT"] == "43123"
    with pytest.raises(ValueError, match="RUNTIME_PORT_OVERRIDE_INVALID"):
        verification.runtime_commands(workspace, port_overrides={"typescript": 80})
    with pytest.raises(ValueError, match="RUNTIME_PORT_OVERRIDE_LANGUAGE_UNKNOWN"):
        verification.runtime_commands(workspace, port_overrides={"rust": 43124})

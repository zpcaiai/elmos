from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"


def _jobs() -> dict[str, Any]:
    document = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    return document["jobs"]


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


def test_project_synthesis_ci_builds_and_binds_locked_native_library() -> None:
    job = _jobs()["project-synthesis"]
    python_step = _step(job, "Set up Python 3.12.12")
    rust_step = _step(job, "Set up Rust 1.89.0")
    build_step = _step(job, "Build locked native dependency solver")
    verify_step = _step(job, "Verify Project Synthesis")

    assert job["env"]["UV_PYTHON_DOWNLOADS"] == "never"
    assert python_step["with"]["python-version"] == "3.12.12"
    assert rust_step["uses"] == (
        "dtolnay/rust-toolchain@451ce45ce31d200b52705aadd15ce75018b006de"
    )
    assert rust_step["with"]["toolchain"] == "1.89.0"
    assert "working-directory" not in build_step
    assert build_step["env"]["CARGO_NET_OFFLINE"] == "true"
    assert 'rustc 1.89.0 (29483883e 2025-08-04)' in build_step["run"]
    assert 'cargo 1.89.0 (c24e10642 2025-06-23)' in build_step["run"]
    assert "cargo build --locked --release --lib" in build_step["run"]
    assert "--manifest-path native/rust-core/Cargo.toml" in build_step["run"]
    assert verify_step["env"]["ELMOS_NATIVE_LIB"].endswith(
        "/native/rust-core/target/release/libelmos_native.so"
    )
    assert "uv sync --locked" in verify_step["run"]
    assert "uv run --locked pytest" in verify_step["run"]

    step_names = [step["name"] for step in job["steps"]]
    assert step_names.index("Build locked native dependency solver") < step_names.index(
        "Verify Project Synthesis"
    )


@pytest.mark.parametrize("job_id", ["web-console", "web-console-generation"])
def test_web_ci_installs_both_exact_python_runtimes(job_id: str) -> None:
    job = _jobs()[job_id]
    python_312 = _step(job, "Set up Python 3.12.12")
    python_314 = _step(job, "Set up exact ChinaDB preflight runtime")
    probe = _step(job, "Verify exact ChinaDB preflight runtime")

    assert job["env"]["UV_PYTHON_DOWNLOADS"] == "never"
    assert python_312["with"]["python-version"] == "3.12.12"
    assert python_314["with"]["python-version"] == "3.14.6"
    assert 'test "$(python3.12 --version)" = "Python 3.12.12"' in probe["run"]
    assert "uv --directory engines/database-data-engine/sql-transpiler run --locked" in probe["run"]
    assert probe["run"].count('= "3.14.6"') == 2

    sql_python_pin = (
        ROOT / "engines" / "database-data-engine" / "sql-transpiler" / ".python-version"
    ).read_text(encoding="utf-8")
    assert sql_python_pin.strip() == "3.14.6"

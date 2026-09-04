from __future__ import annotations

from elmos_project_synthesis.native_dep_solver_bridge import native_solve_dependencies


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

"""React typed-pure whole-repository source and target closure."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from elmos_polyglot_route import pipeline as pipeline_module
from elmos_polyglot_route.batch import run_batch
from elmos_polyglot_route.discovery import Verdict, discover_repository
from elmos_polyglot_route.models import REPOSITORY_SURFACE_LANGUAGES, RouteError
from elmos_polyglot_route.pipeline import run_repository_pipeline
from elmos_polyglot_route.project_graph import ProjectGraphError, build_project_graph
from elmos_polyglot_route.repository import plan_repository
from elmos_polyglot_route.toolchains import ExactToolchain, exact_toolchain, sanitized_subprocess_env


def _write_cases(cases: Path) -> None:
    cases.mkdir()
    values = (
        [{"args": [2, 3], "expected": 5}, {"args": [-4, 1], "expected": -3}],
        [{"args": [3, 4], "expected": 12}, {"args": [-2, 5], "expected": -10}],
    )
    for index, value in enumerate(values, start=1):
        (cases / f"WU-{index:05d}.json").write_text(
            json.dumps(value, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _write_react_project(repository: Path) -> None:
    repository.mkdir()
    (repository / "package.json").write_text(
        json.dumps(
            {
                "private": True,
                "type": "module",
                "dependencies": {
                    "react": "19.2.7",
                    "react-dom": "19.2.7",
                },
                "devDependencies": {
                    "@types/react": "19.1.10",
                    "@types/react-dom": "19.1.7",
                    "typescript": "5.9.2",
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (repository / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2022",
                    "module": "NodeNext",
                    "moduleResolution": "NodeNext",
                    "strict": True,
                    "jsx": "react-jsx",
                    "noEmit": True,
                    "types": [],
                },
                "include": ["**/*.ts", "**/*.tsx"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _run_node(
    toolchain: ExactToolchain,
    working_directory: Path,
    script: Path,
    scratch: Path,
) -> subprocess.CompletedProcess[str]:
    home = scratch / "home"
    temporary = scratch / "tmp"
    home.mkdir(parents=True)
    temporary.mkdir()
    return subprocess.run(
        [toolchain.executable, str(script)],
        cwd=working_directory,
        env=sanitized_subprocess_env(
            home=home,
            temp_dir=temporary,
            executable_dirs=(Path(toolchain.executable).resolve().parent,),
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _assert_node_passed(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == 0, (
        f"stdout={completed.stdout[-2_000:]!r}\n"
        f"stderr={completed.stderr[-2_000:]!r}"
    )


def _compiled_module(assembled_path: str) -> Path:
    source = Path(assembled_path)
    return source.relative_to("src").with_suffix(".js")


def _refresh_receipt_digest(receipt: dict[str, object]) -> None:
    payload = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def test_react_repository_inventory_requires_exact_project_and_rejects_ui(
    tmp_path: Path,
) -> None:
    assert "react" in REPOSITORY_SURFACE_LANGUAGES
    repository = tmp_path / "repository"
    _write_react_project(repository)
    (repository / "pure.tsx").write_text(
        "export function add(left: number, right: number): number {\n"
        "  return left + right;\n"
        "}\n",
        encoding="utf-8",
    )

    plan = plan_repository(repository, "local:react-inventory", "react", "typescript")
    assert plan["source_file_count"] == 1
    assert plan["language_counts"]["react"] == 1
    assert plan["react_project_descriptor"]["profile"] == (
        "react-19.2.7-typescript-5.9.2-node-26.0.0-typed-pure-v1"
    )
    discovery = discover_repository(plan, repository)
    assert discovery["ready_count"] == 1
    assert discovery["react_project_source_paths"] == ["pure.tsx"]
    assert discovery["react_project_verification"]["status"] == "PASSED"
    assert discovery["react_project_verification"]["toolchain"]["language"] == "react"

    (repository / "pure.tsx").write_text(
        "export function Counter(value: number): number {\n"
        "  return value;\n"
        "}\n",
        encoding="utf-8",
    )
    rejected_plan = plan_repository(
        repository,
        "local:react-component-rejected",
        "react",
        "typescript",
    )
    rejected = discover_repository(rejected_plan, repository)
    assert rejected["ready_count"] == 0
    assert rejected["results"][0]["verdict"] == Verdict.UNSUPPORTED
    assert rejected["results"][0]["blocker_code"] == (
        "NATIVE_MODULE_DECLARATION_CONVERSION_UNCOVERED"
    )

    package = json.loads((repository / "package.json").read_text(encoding="utf-8"))
    package["dependencies"]["react"] = "^19.2.7"
    (repository / "package.json").write_text(
        json.dumps(package, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RouteError, match=r"^REACT_PACKAGE_VERSION_MISMATCH:react$"):
        plan_repository(repository, "local:react-version-drift", "react", "typescript")


@pytest.mark.parametrize(
    "mutation",
    ["extra-dependency", "swapped-section", "scripts", "workspaces", "private-false"],
)
def test_react_repository_rejects_unmigrated_package_semantics(
    tmp_path: Path,
    mutation: str,
) -> None:
    repository = tmp_path / "repository"
    _write_react_project(repository)
    (repository / "pure.tsx").write_text(
        "export function pure(value: number): number { return value; }\n",
        encoding="utf-8",
    )
    package_path = repository / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    if mutation == "extra-dependency":
        package["dependencies"]["left-pad"] = "1.3.0"
    elif mutation == "swapped-section":
        package["devDependencies"]["react"] = package["dependencies"].pop("react")
    elif mutation == "scripts":
        package["scripts"] = {"prepare": "node untrusted.mjs"}
    elif mutation == "workspaces":
        package["workspaces"] = ["packages/*"]
    else:
        package["private"] = False
    package_path.write_text(
        json.dumps(package, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RouteError, match=r"^REACT_PACKAGE_"):
        plan_repository(repository, f"local:react-{mutation}", "react", "typescript")


@pytest.mark.parametrize(
    "tamper",
    ["profile", "executable", "digest", "command", "extra-field"],
)
def test_react_project_graph_rejects_self_consistent_verification_tamper(
    tmp_path: Path,
    tamper: str,
) -> None:
    repository = tmp_path / "repository"
    _write_react_project(repository)
    (repository / "pure.tsx").write_text(
        "export function pure(value: number): number { return value; }\n",
        encoding="utf-8",
    )
    reference = f"local:react-receipt-{tamper}"
    plan = plan_repository(repository, reference, "react", "typescript")
    discovery = discover_repository(plan, repository)
    assert build_project_graph(repository, reference, discovery)["repository_complete"] is True

    changed = copy.deepcopy(discovery)
    receipt = changed["react_project_verification"]
    if tamper == "profile":
        receipt["toolchain"]["profile"].append("fabricated=true")
    elif tamper == "executable":
        receipt["toolchain"]["executable"] = "/tmp/fabricated-node"
    elif tamper == "digest":
        receipt["toolchain"]["executable_sha256"] = "0" * 64
    elif tamper == "command":
        receipt["command"] = ["node", "--version"]
    else:
        receipt["fabricated"] = True
    _refresh_receipt_digest(receipt)

    with pytest.raises(ProjectGraphError, match=r"^REACT_"):
        build_project_graph(repository, reference, changed)

    cases = tmp_path / "tampered-cases"
    cases.mkdir()
    batch_output = tmp_path / "tampered-batch"
    with pytest.raises(RouteError, match=r"^REACT_"):
        run_batch(changed, repository, cases, batch_output)
    assert not batch_output.exists()


def test_react_pipeline_detects_repository_drift_during_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    _write_react_project(repository)
    (repository / "pure.tsx").write_text(
        "export function pure(value: number): number { return value; }\n",
        encoding="utf-8",
    )
    late_resource = repository / "late-resource.json"
    late_resource.write_text('{"must": "remain-bound"}\n', encoding="utf-8")
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "WU-00001.json").write_text(
        json.dumps([{"args": [7], "expected": 7}]) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "output"
    original_discover = pipeline_module.discover_repository

    def discover_then_remove(plan: dict[str, object], root: Path) -> dict[str, object]:
        result = original_discover(plan, root)
        late_resource.unlink()
        return result

    monkeypatch.setattr(pipeline_module, "discover_repository", discover_then_remove)
    with pytest.raises(RouteError, match=r"^PROJECT_GRAPH_CHANGED_DURING_PIPELINE$"):
        run_repository_pipeline(
            repository,
            "local:react-discovery-drift",
            "react",
            "typescript",
            cases,
            output,
        )
    for claim in (
        "repository-route-report.json",
        "repository-artifact.zip",
        "assembled",
        "assembled.staging",
    ):
        assert not (output / claim).exists()


def test_react_source_repository_closes_to_typescript_and_runs_with_node(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    _write_react_project(repository)
    (repository / "add.tsx").write_text(
        "export function add(left: number, right: number): number {\n"
        "  return left + right;\n"
        "}\n",
        encoding="utf-8",
    )
    (repository / "multiply.ts").write_text(
        "export function multiply(left: number, right: number): number {\n"
        "  return left * right;\n"
        "}\n",
        encoding="utf-8",
    )
    cases = tmp_path / "cases"
    _write_cases(cases)
    output = tmp_path / "output"

    report = run_repository_pipeline(
        repository,
        "local:react-source-to-typescript",
        "react",
        "typescript",
        cases,
        output,
    )

    assert report["status"] == "COMPLETE"
    assert report["repository_complete"] is True
    assert report["repository_execution_status"] == "PASSED_LOCAL"
    assert report["work_unit_count"] == 2
    assert report["included_unit_count"] == 2
    assert report["build_verification"]["status"] == "PASSED"
    assert report["build_verification"]["toolchain"]["language"] == "typescript"
    assert report["certification_status"] == "NOT_CERTIFIED"

    assembled = output / "assembled"
    manifest = json.loads((assembled / "assembly-manifest.json").read_text(encoding="utf-8"))
    imports: list[str] = []
    checks: list[str] = []
    expected = {"add.tsx": ("2, 3", "5"), "multiply.ts": ("3, 4", "12")}
    for index, unit in enumerate(manifest["included_units"]):
        module_name = f"unit{index}"
        compiled = _compiled_module(str(unit["assembled_path"]))
        arguments, value = expected[str(unit["source_path"])]
        imports.append(f'import * as {module_name} from "./dist/{compiled.as_posix()}";')
        checks.append(
            f"if ({module_name}.{unit['target_function_name']}({arguments}) !== {value}) "
            "throw new Error('react-source-target-runtime-mismatch');"
        )
    runner = assembled / "react-source-target-runner.mjs"
    runner.write_text(
        "\n".join([*imports, *checks, 'console.log("REACT_SOURCE_TO_TYPESCRIPT_OK");'])
        + "\n",
        encoding="utf-8",
    )
    completed = _run_node(
        exact_toolchain("typescript"),
        assembled,
        runner,
        tmp_path / "source-target-node-scratch",
    )
    _assert_node_passed(completed)
    assert completed.stdout.strip() == "REACT_SOURCE_TO_TYPESCRIPT_OK"


def test_react_target_repository_assembles_compiles_and_runs_with_node(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "add.ts").write_text(
        "export function add(left: number, right: number): number {\n"
        "  return left + right;\n"
        "}\n",
        encoding="utf-8",
    )
    (repository / "multiply.ts").write_text(
        "export function multiply(left: number, right: number): number {\n"
        "  return left * right;\n"
        "}\n",
        encoding="utf-8",
    )
    cases = tmp_path / "cases"
    _write_cases(cases)
    output = tmp_path / "output"

    report = run_repository_pipeline(
        repository,
        "local:typescript-source-to-react",
        "typescript",
        "react",
        cases,
        output,
    )

    assert report["status"] == "COMPLETE"
    assert report["repository_complete"] is True
    assert report["repository_execution_status"] == "PASSED_LOCAL"
    assert report["work_unit_count"] == 2
    assert report["included_unit_count"] == 2
    assert report["build_verification"]["status"] == "PASSED"
    assert report["build_verification"]["toolchain"]["language"] == "react"
    assert report["build_verification"]["toolchain"]["version"] == (
        "React 19.2.7 / React DOM 19.2.7 / TypeScript 5.9.2 / Node 26.0.0"
    )
    assert report["certification_status"] == "NOT_CERTIFIED"

    assembled = output / "assembled"
    manifest = json.loads((assembled / "assembly-manifest.json").read_text(encoding="utf-8"))
    assert manifest["build_files"] == ["package.json", "tsconfig.json"]
    assert manifest["build_verification_status"] == "PASSED"
    assert manifest["build_verification"]["react_runtime_receipt"]["status"] == "PASSED"
    assert manifest["build_verification"]["react_runtime_receipt"]["versions"] == {
        "react": "19.2.7",
        "react-dom": "19.2.7",
    }
    assert manifest["included_unit_count"] == 2
    assert all(str(unit["assembled_path"]).endswith(".tsx") for unit in manifest["included_units"])
    assert all(
        (assembled / "dist" / _compiled_module(str(unit["assembled_path"]))).is_file()
        for unit in manifest["included_units"]
    )

    imports: list[str] = []
    checks: list[str] = []
    expected = {"add.ts": ("2, 3", "5"), "multiply.ts": ("3, 4", "12")}
    for index, unit in enumerate(manifest["included_units"]):
        module_name = f"unit{index}"
        compiled = _compiled_module(str(unit["assembled_path"]))
        arguments, value = expected[str(unit["source_path"])]
        imports.append(f'import * as {module_name} from "./dist/{compiled.as_posix()}";')
        checks.append(
            f"if ({module_name}.{unit['target_function_name']}({arguments}) !== {value}) "
            "throw new Error('react-target-runtime-mismatch');"
        )
    runner = assembled / "react-target-runner.mjs"
    runner.write_text(
        "\n".join([*imports, *checks, 'console.log("TYPESCRIPT_TO_REACT_OK");'])
        + "\n",
        encoding="utf-8",
    )
    completed = _run_node(
        exact_toolchain("react"),
        assembled,
        runner,
        tmp_path / "target-node-scratch",
    )
    _assert_node_passed(completed)
    assert completed.stdout.strip() == "TYPESCRIPT_TO_REACT_OK"

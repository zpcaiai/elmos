from __future__ import annotations

import json
from pathlib import Path

import pytest

from elmos_python.codemod import LibCstModernizer
from elmos_python.contracts import (
    ErrorCode,
    ExecuteStepRequest,
    ExecutionBudget,
    ExecutorType,
    JobRequest,
    JobStatus,
    StepDefinition,
)
from elmos_python.discovery import SafePythonDiscovery
from elmos_python.engine import PythonEngine
from elmos_python.environment import EnvironmentReproducer
from elmos_python.legacy import LegacyPythonAnalyzer
from elmos_python.ml import MachineLearningModernizationAdvisor
from elmos_python.packaging import PackagingModernizationAdvisor
from elmos_python.pipeline import PipelineAndNotebookAnalyzer
from elmos_python.planning import CompatibilityRegistry, PythonMigrationPlanner
from elmos_python.runners import PythonRunnerRouter
from elmos_python.semantic import PythonSemanticGraphBuilder
from elmos_python.validation import (
    DatasetSnapshotter,
    MetricTolerance,
    ModelBehaviorValidator,
    NumericalDataValidator,
    PythonValidationJudge,
)
from elmos_python.web import DjangoModernizationAdvisor, FlaskModernizationAdvisor

REGISTRY = Path(__file__).parents[1] / "compatibility-registry" / "python-compatibility-v1.json"


def write(root: Path, name: str, content: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def request(
    workspace: str = ".",
    key: str = "key",
    snapshot: str = "snapshot",
    profile: str = "BALANCED_RECOMMENDED",
    **options: object,
) -> JobRequest:
    return JobRequest(
        organization_id="org-a",
        repository_snapshot_ref=snapshot,
        workspace_ref=workspace,
        profile=profile,
        correlation_id="correlation",
        idempotency_key=key,
        options=options,
    )


def test_capabilities_declare_third_engine_and_five_runner_types(tmp_path: Path) -> None:
    capabilities = PythonEngine(tmp_path).capabilities()
    assert capabilities.engine == "ELMOS_PYTHON"
    assert capabilities.source_versions[0] == "2.7"
    assert "3.15" not in capabilities.supported_target_versions
    assert set(capabilities.runner_profiles) == {
        "PYTHON_LEGACY_LINUX",
        "PYTHON_MODERN_CPU",
        "PYTHON_MODERN_GPU",
        "PYTHON_WINDOWS",
        "PYTHON_NOTEBOOK",
    }


def test_discovery_keeps_declared_test_and_deployment_python_separate(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", '[project]\nname="demo"\nversion="1"\nrequires-python=">=3.8"\n')
    write(tmp_path, "Dockerfile", "FROM python:3.9.21-slim\n")
    write(tmp_path, ".github/workflows/test.yml", "python-version: '3.11'\n")
    inventory = SafePythonDiscovery().discover(tmp_path, ".")
    evidence = {(item.kind, item.value) for item in inventory.python_versions}
    assert ("DECLARED_PYTHON", ">=3.8") in evidence
    assert ("DEPLOYMENT_PYTHON", "3.9.21") in evidence
    assert ("TEST_PYTHON", "3.11") in evidence
    assert "PYTHON_VERSION_CONFLICT" in inventory.findings


def test_unpinned_requirements_is_not_reproducible(tmp_path: Path) -> None:
    write(tmp_path, "requirements.txt", "Django>=2\nrequests\n")
    write(tmp_path, "app.py", "import django\n")
    inventory = SafePythonDiscovery().discover(tmp_path, ".")
    snapshot = EnvironmentReproducer().analyze(tmp_path, inventory)
    assert "UNPINNED_DEPENDENCIES" in inventory.findings
    assert snapshot.reproducibility_status.value == "UNREPRODUCIBLE"


def test_private_index_credentials_are_redacted(tmp_path: Path) -> None:
    write(tmp_path, "requirements.txt", "--extra-index-url https://user:secret@packages.example/simple\ndemo==1.0\n")
    write(tmp_path, "app.py", "pass\n")
    inventory = SafePythonDiscovery().discover(tmp_path, ".")
    assert all("secret" not in value and "user@" not in value for value in inventory.index_sources)
    assert inventory.index_sources == ["https://packages.example/simple"]


def test_notebook_out_of_order_execution_is_visible(tmp_path: Path) -> None:
    notebook = {
        "cells": [
            {"cell_type": "code", "execution_count": 2, "source": ["x = 1"]},
            {"cell_type": "code", "execution_count": 1, "source": ["print(x)"]},
        ]
    }
    write(tmp_path, "analysis.ipynb", json.dumps(notebook))
    write(tmp_path, "requirements.txt", "jupyter==1.1.1\n")
    inventory = SafePythonDiscovery().discover(tmp_path, ".")
    profile = PipelineAndNotebookAnalyzer().analyze(tmp_path)
    assert "NOTEBOOK_HIDDEN_STATE" in inventory.findings
    assert "NOTEBOOK_HIDDEN_STATE" in profile["findings"]


def test_semantic_graph_uses_cst_and_ast_and_marks_dynamic_calls(tmp_path: Path) -> None:
    write(
        tmp_path,
        "app.py",
        "import importlib\nclass A:\n    def run(self):\n        return importlib.import_module('plugin')\n",
    )
    graph = PythonSemanticGraphBuilder().build(tmp_path)
    assert any(symbol.qualified_name.endswith("A.run") for symbol in graph.symbols)
    assert any(edge.kind == "CALLS_POTENTIALLY" for edge in graph.edges)
    assert graph.ast_parser == "CPython AST 3.14"
    assert graph.runtime_observations == []


def test_libcst_codemod_preserves_comment_and_reaches_fixpoint() -> None:
    source = "# business invariant\nfor item in xrange(3):\n    print(data.iteritems())\n"
    result = LibCstModernizer().modernize_old_python_apis(source)
    assert result.comments_preserved and result.idempotent and result.changed
    assert "xrange" not in result.transformed_source
    assert "# business invariant" in result.transformed_source


def test_planner_keeps_web_data_and_ml_acceptance_paths_distinct(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", '[project]\nname="all"\nversion="1"\n')
    write(tmp_path, "web.py", "import django\n")
    write(tmp_path, "dag.py", "from airflow import DAG\n")
    write(tmp_path, "model.py", "import torch\n")
    inventory = SafePythonDiscovery().discover(tmp_path, ".")
    plan = PythonMigrationPlanner(CompatibilityRegistry(REGISTRY)).plan(inventory, "FUNCTIONALLY_REPRODUCIBLE")
    assert {profile.path.value for profile in plan.profiles} == {"WEB", "DATA_PIPELINE", "AI_ML"}
    assert all(profile.python_version != "3.15" for profile in plan.profiles)
    assert {"HTTP_CONTRACT", "DATA_CONTRACT", "MODEL_ARTIFACT"}.issubset(plan.acceptance_gates)


def test_monorepo_classification_is_scoped_to_each_project_root(tmp_path: Path) -> None:
    write(tmp_path, "packages/web/pyproject.toml", '[project]\nname="web"\nversion="1"\n')
    write(tmp_path, "packages/web/app.py", "from django.http import HttpResponse\n")
    write(tmp_path, "packages/model/pyproject.toml", '[project]\nname="model"\nversion="1"\n')
    write(tmp_path, "packages/model/train.py", "import torch\n")
    inventory = SafePythonDiscovery().discover(tmp_path, ".")
    paths_by_root = {project.relative_path: {path.value for path in project.paths} for project in inventory.projects}
    assert paths_by_root == {"packages/model": {"AI_ML"}, "packages/web": {"WEB"}}


def test_runner_router_isolates_python2_and_enforces_gpu_windows_and_notebook_capabilities() -> None:
    router = PythonRunnerRouter()
    assert router.route("2.7").runner_profile == "PYTHON_LEGACY_LINUX"
    assert router.route("2.7", "WINDOWS").status == "BLOCKED"
    assert "LEGACY_PYTHON_RUNNER_REQUIRED" in router.route("2.7", "WINDOWS").blockers
    assert router.route("3.13", requires_gpu=True).runner_profile == "PYTHON_MODERN_GPU"
    assert "GPU_RUNNER_REQUIRED" in router.route("3.14", requires_gpu=True).blockers
    assert router.route("3.14", "WINDOWS").runner_profile == "PYTHON_WINDOWS"
    assert router.route("3.14", notebook=True).runner_profile == "PYTHON_NOTEBOOK"


def test_python2_analysis_keeps_bytes_text_and_compatibility_exit_explicit(tmp_path: Path) -> None:
    write(
        tmp_path,
        "legacy.py",
        "from __future__ import unicode_literals\n"
        "import six\n"
        "print 'legacy'\n"
        "payload = str(request.data)\n"
        "open('blob', 'wb').write(payload)\n"
        "ratio = count / total\n",
    )
    profile = LegacyPythonAnalyzer().assess(tmp_path)
    assert profile["twoToThreeRole"] == "CANDIDATE_DIFF_ONLY_NOT_PRODUCTION_CORE"
    assert {"PY2_BYTES_TEXT_AMBIGUOUS", "PY2_INTEGER_DIVISION_RISK"}.issubset(profile["findings"])
    assert {item["boundary"] for item in profile["stringBoundaries"]} == {"FILE", "HTTP"}
    assert all(item["exitPlanRequired"] for item in profile["compatibilityLayers"])


def test_packaging_analysis_blocks_numpy2_native_abi_without_target_wheel(tmp_path: Path) -> None:
    write(
        tmp_path, "setup.py", "from setuptools import setup, Extension\nsetup(ext_modules=[Extension('x', ['x.c'])])\n"
    )
    write(tmp_path, "x.c", "#include <numpy/arrayobject.h>\nvoid f(){PyArray_API;}\n")
    profile = PackagingModernizationAdvisor().assess(tmp_path, target_python="3.14", target_numpy_major=2)
    assert {"LEGACY_SETUP_EXECUTION", "NATIVE_EXTENSION_REBUILD", "NUMPY_ABI_BREAK", "NO_TARGET_WHEEL"}.issubset(
        profile["findings"]
    )
    assert {item["os"] for item in profile["wheelMatrix"]} == {"LINUX", "WINDOWS", "MACOS"}
    assert profile["sourceBuildPolicy"]["network"] == "DENY_BY_DEFAULT"


def test_hashed_lock_is_dependency_reproducible(tmp_path: Path) -> None:
    write(tmp_path, "requirements.txt", "demo==1.0 --hash=sha256:" + "a" * 64 + "\n")
    write(tmp_path, "pylock.toml", 'lock-version="1.0"\n')
    write(tmp_path, "app.py", "pass\n")
    inventory = SafePythonDiscovery().discover(tmp_path, ".")
    snapshot = EnvironmentReproducer().analyze(tmp_path, inventory)
    assert snapshot.reproducibility_status.value == "DEPENDENCY_REPRODUCIBLE"


def test_django_plan_is_incremental_and_does_not_force_asgi(tmp_path: Path) -> None:
    write(tmp_path, "settings.py", "MIDDLEWARE_CLASSES = []\n")
    write(tmp_path, "urls.py", "url(r'^x$', view)\n")
    decision = DjangoModernizationAdvisor().assess(tmp_path, "2.2", "6.0")
    assert decision["stages"] == [
        "DJANGO_2.LATEST_PATCH",
        "DJANGO_3.LATEST_PATCH",
        "DJANGO_4.LATEST_PATCH",
        "DJANGO_5.LATEST_PATCH",
        "DJANGO_6.LATEST_PATCH",
    ]
    assert decision["wsgiToAsgi"] == "NOT_FORCED"
    assert "DJANGO_URL_BREAKING" in decision["findings"]


def test_django_unsupported_third_party_app_is_a_hard_blocker(tmp_path: Path) -> None:
    write(tmp_path, "settings.py", "INSTALLED_APPS = ['django_legacy_plugin']\n")
    decision = DjangoModernizationAdvisor().assess(
        tmp_path, "2.2", "6.0", {"django_legacy_plugin": False, "django_rest_framework": True}
    )
    assert "DJANGO_THIRD_PARTY_APP_BLOCKER" in decision["findings"]
    assert decision["blockers"] == ["DJANGO_PLUGIN_UNSUPPORTED:django_legacy_plugin"]


def test_flask_context_risk_does_not_trigger_automatic_framework_replacement(tmp_path: Path) -> None:
    write(
        tmp_path,
        "app.py",
        "from flask import Flask, current_app\n"
        "app = Flask(__name__)\n"
        "def background_thread(): return current_app.name\n",
    )
    decision = FlaskModernizationAdvisor().assess(tmp_path, requires_asgi=True)
    assert "FLASK_CONTEXT_LIFETIME_RISK" in decision["findings"]
    assert decision["automaticFrameworkReplacement"] is False


def test_pipeline_side_effect_requires_shadow_or_stub(tmp_path: Path) -> None:
    write(tmp_path, "tasks.py", "@app.task\ndef bill():\n    requests.post('https://billing')\n")
    profile = PipelineAndNotebookAnalyzer().analyze(tmp_path)
    assert profile["nodes"] == ["tasks.py"]
    assert "PIPELINE_SIDE_EFFECT_REQUIRES_SHADOW" in profile["findings"]


def test_model_artifacts_are_hashed_but_never_loaded_during_scan(tmp_path: Path) -> None:
    artifact = write(tmp_path, "model.joblib", "this is deliberately not a valid pickle")
    profile = MachineLearningModernizationAdvisor().inventory(tmp_path)
    assert artifact.exists()
    assert profile["artifacts"][0]["loadedDuringScan"] is False
    assert profile["artifacts"][0]["loadPolicy"] == "ISOLATED_NO_NETWORK_NO_SECRET"
    assert "MODEL_ARTIFACT_ENVIRONMENT_LOCKED" in profile["findings"]


def test_tensorflow1_is_planned_as_staged_candidate_not_declared_migrated(tmp_path: Path) -> None:
    write(tmp_path, "train.py", "import tensorflow as tf\nx = tf.placeholder(tf.float32)\nwith tf.Session(): pass\n")
    profile = MachineLearningModernizationAdvisor().inventory(tmp_path)
    assert "TENSORFLOW_1_STAGED_MIGRATION_REQUIRED" in profile["findings"]
    assert profile["tensorflowMigrationStages"][1] == "TF_UPGRADE_V2_CANDIDATE_ONLY"


def test_numerical_validation_detects_dtype_change_even_when_shape_matches() -> None:
    decision = NumericalDataValidator().compare(
        [1.0, 2.0], [1.0, 2.0], MetricTolerance("prediction", 0.0, 0.0), [True], "ORDER_STRICT", "float32", "float64"
    )
    assert decision["status"] == "REGRESSION"
    assert "DTYPE_CHANGED" in decision["failures"]


def test_numerical_validation_requires_declared_randomness_when_path_is_stochastic() -> None:
    missing = NumericalDataValidator().compare(
        [1.0],
        [1.0],
        MetricTolerance("prediction", 0.0, 0.0),
        [True],
        "ORDER_STRICT",
        "float32",
        "float32",
        randomness_required=True,
    )
    controlled = NumericalDataValidator().compare(
        [1.0],
        [1.0],
        MetricTolerance("prediction", 0.0, 0.0),
        [True],
        "ORDER_STRICT",
        "float32",
        "float32",
        randomness_required=True,
        random_seeds={"PYTHONHASHSEED": 7, "numpy": 7, "framework": 7},
    )
    assert "RANDOMNESS_CONTROL_MISSING" in missing["failures"]
    assert controlled["status"] == "NUMERICALLY_EQUIVALENT"


def test_dataset_snapshot_exposes_dtype_null_order_and_primary_key_behavior() -> None:
    snapshot = DatasetSnapshotter().snapshot(
        [{"id": 1, "name": "a"}, {"id": 1, "name": None}], primary_key="id", ordering="ORDER_BY_KEY"
    )
    assert snapshot["shape"] == [2, 2]
    assert snapshot["ordering"] == "ORDER_BY_KEY"
    assert snapshot["primaryKeyUnique"] is False
    assert next(item for item in snapshot["schema"] if item["name"] == "name")["nullCount"] == 1


def test_model_validation_separates_artifact_inference_training_and_test_identity() -> None:
    decision = ModelBehaviorValidator().decide("PASS", "PASS", "PASS", True, 900, 280)
    assert decision["decision"] == "FAIL"
    assert "TEST_INVENTORY_REGRESSION" in decision["blockers"]


def test_model_validation_fails_incomplete_load_matrix_signature_and_hardware_separation() -> None:
    decision = ModelBehaviorValidator().decide(
        "PASS",
        "PASS",
        "PASS",
        True,
        10,
        10,
        load_matrix_complete=False,
        signature_compatible=False,
        hardware_difference_separated=False,
    )
    assert decision["decision"] == "FAIL"
    assert {"MODEL_LOAD_MATRIX_INCOMPLETE", "MODEL_SIGNATURE_REGRESSION", "HARDWARE_VARIATION_NOT_SEPARATED"}.issubset(
        decision["blockers"]
    )


@pytest.mark.parametrize(
    ("path", "passing_options", "required"),
    [
        (
            "WEB",
            {"httpContractPassed": True, "sessionAuthPassed": True, "databaseBehaviorPassed": True},
            "httpContractPassed",
        ),
        (
            "DATA_PIPELINE",
            {"dataContractPassed": True, "numericalPassed": True, "scheduleRetryPassed": True},
            "dataContractPassed",
        ),
        (
            "AI_ML",
            {
                "artifactPassed": True,
                "inferencePassed": True,
                "trainingEvidencePassed": True,
                "ownerThresholdsApproved": True,
            },
            "artifactPassed",
        ),
    ],
)
def test_path_specific_validation_has_distinct_evidence(
    path: str, passing_options: dict[str, bool], required: str
) -> None:
    options: dict[str, object] = {
        "baselineTests": 10,
        "migratedTests": 10,
        "environmentReproduced": True,
        **passing_options,
    }
    decision = PythonValidationJudge().judge(path, options)
    assert decision["decision"] == "PASS"
    assert required in decision["requiredEvidence"]


def test_engine_jobs_are_tenant_scoped_and_idempotency_binds_inputs(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write(workspace, "pyproject.toml", '[project]\nname="demo"\nversion="1"\nrequires-python=">=3.14"\n')
    write(workspace, "app.py", "pass\n")
    engine = PythonEngine(tmp_path, REGISTRY)
    first = engine.scan(request("workspace", "same"))
    repeated = engine.scan(request("workspace", "same"))
    conflict = engine.scan(request("workspace", "same", snapshot="other"))
    assert first.job_id == repeated.job_id
    assert conflict.error and conflict.error.error_code == ErrorCode.POLICY_BLOCKED
    assert engine.get_job("org-b", first.job_id).status == JobStatus.FAILED
    assert engine.cancel("org-a", first.job_id).error is not None


def test_execute_step_applies_bounded_idempotent_libcst_change(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = write(workspace, "legacy.py", "# keep\nfor i in xrange(2):\n    pass\n")
    engine = PythonEngine(tmp_path, REGISTRY)
    response = engine.execute_step(
        ExecuteStepRequest(
            organization_id="org-a",
            migration_run_id="run",
            migration_plan_version=1,
            step_definition=StepDefinition(
                step_id="step", executor_type=ExecutorType.LIBCST, configuration={"relativePath": "legacy.py"}
            ),
            workspace_ref="workspace",
            source_commit="abc",
            execution_budget=ExecutionBudget(
                timeout_seconds=30, cpu_seconds=10, max_bytes_written=10_000, max_agent_credits=0
            ),
            correlation_id="correlation",
            idempotency_key="execute",
        )
    )
    assert response.status == JobStatus.SUCCEEDED
    assert "range(2)" in target.read_text(encoding="utf-8")
    assert response.result["transformation"]["idempotent"] is True

    changed_budget = ExecuteStepRequest(
        organization_id="org-a",
        migration_run_id="run",
        migration_plan_version=1,
        step_definition=StepDefinition(
            step_id="step", executor_type=ExecutorType.LIBCST, configuration={"relativePath": "legacy.py"}
        ),
        workspace_ref="workspace",
        source_commit="abc",
        execution_budget=ExecutionBudget(
            timeout_seconds=60, cpu_seconds=10, max_bytes_written=10_000, max_agent_credits=0
        ),
        correlation_id="correlation",
        idempotency_key="execute",
    )
    conflict = engine.execute_step(changed_budget)
    assert conflict.status == JobStatus.FAILED
    assert conflict.error and "different immutable inputs" in conflict.error.message


def test_engine_rejects_workspace_escape(tmp_path: Path) -> None:
    engine = PythonEngine(tmp_path, REGISTRY)
    scan_response = engine.scan(request("..", "escape-scan"))
    plan_response = engine.plan(request("..", "escape-plan"))
    assert scan_response.error and scan_response.error.error_code == ErrorCode.POLICY_BLOCKED
    assert plan_response.error and plan_response.error.error_code == ErrorCode.POLICY_BLOCKED


def test_engine_validation_never_turns_missing_evidence_into_pass(tmp_path: Path) -> None:
    engine = PythonEngine(tmp_path, REGISTRY)
    response = engine.validate(request(".", "validate", profile="AI_ML", baselineTests=10, migratedTests=10))
    assert response.status == JobStatus.FAILED
    assert response.error and response.error.error_code == ErrorCode.VALIDATION_FAILED

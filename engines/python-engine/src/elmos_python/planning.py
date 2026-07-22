from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from .domain import MigrationPlan, MigrationStep, ProjectInventory, ProjectPath, TargetProfile


class CompatibilityRegistry:
    def __init__(self, registry_path: Path) -> None:
        self.data = json.loads(registry_path.read_text(encoding="utf-8"))

    @property
    def snapshot_id(self) -> str:
        return str(self.data["snapshotId"])

    def target_for(
        self, path: ProjectPath, frameworks: list[str], gpu: bool
    ) -> tuple[str, dict[str, str], str, list[str]]:
        target = self.data["profiles"][path.value]
        python_version = target["python"]
        constraints: list[str] = []
        if gpu:
            python_version = self.data["profiles"]["AI_ML_GPU"]["python"]
            constraints.append("GPU_WHEEL_AND_DRIVER_MATRIX")
        framework_targets = {name: target["frameworks"][name] for name in frameworks if name in target["frameworks"]}
        runner = "PYTHON_MODERN_GPU" if gpu else "PYTHON_MODERN_CPU"
        return python_version, framework_targets, runner, constraints


class PythonMigrationPlanner:
    def __init__(self, registry: CompatibilityRegistry) -> None:
        self.registry = registry

    def plan(
        self, inventory: ProjectInventory, environment_status: str, profile_type: str = "BALANCED_RECOMMENDED"
    ) -> MigrationPlan:
        profiles: list[TargetProfile] = []
        steps: list[MigrationStep] = []
        blockers: set[str] = set()
        risks: set[str] = set(inventory.findings)
        project_paths: dict[ProjectPath, list[str]] = {}
        for project in inventory.projects:
            for path in project.paths:
                project_paths.setdefault(path, []).append(project.project_id)
        if not project_paths:
            blockers.add("PYTHON_PROJECT_NOT_FOUND")

        for path, project_ids in sorted(project_paths.items(), key=lambda item: item[0].value):
            effective_path = path
            gpu = effective_path == ProjectPath.AI_ML and any(
                item in inventory.system_dependencies for item in ("cuda", "cudnn")
            )
            python_version, framework_targets, runner, constraints = self.registry.target_for(
                effective_path, inventory.frameworks, gpu
            )
            if python_version.startswith("3.15"):
                blockers.add("PRE_RELEASE_PYTHON_TARGET_FORBIDDEN")
            profiles.append(
                TargetProfile(
                    profile_type=profile_type,
                    path=path,
                    python_version=python_version,
                    packaging="PYPROJECT_UV",
                    framework_targets=framework_targets,
                    platform="LINUX_CONTAINER",
                    runner_profile=runner,
                    compatibility_snapshot=self.registry.snapshot_id,
                    constraints=constraints,
                )
            )
            steps.extend(self._steps(path, project_ids, inventory.frameworks, gpu))

        if environment_status == "UNREPRODUCIBLE":
            blockers.add("PYTHON_ENVIRONMENT_UNREPRODUCIBLE")
        if "NOTEBOOK_HIDDEN_STATE" in inventory.findings:
            blockers.add("NOTEBOOK_HIDDEN_STATE")
        gates = ["ENVIRONMENT_REPRODUCTION", "TEST_IDENTITY", "TYPE_STATE_NOT_REGRESSED"]
        if ProjectPath.WEB in project_paths:
            gates.extend(["HTTP_CONTRACT", "SESSION_AUTH", "DATABASE_BEHAVIOR"])
        if ProjectPath.DATA_PIPELINE in project_paths:
            gates.extend(["DATA_CONTRACT", "SCHEDULE_RETRY_BACKFILL", "NUMERICAL_BEHAVIOR"])
        if ProjectPath.AI_ML in project_paths:
            gates.extend(["MODEL_ARTIFACT", "INFERENCE_METRICS", "TRAINING_EVIDENCE", "HARDWARE_COMPATIBILITY"])
        canonical = json.dumps(
            [item.model_dump(mode="json") for item in profiles], sort_keys=True, separators=(",", ":")
        )
        return MigrationPlan(
            plan_id="python-plan-" + sha256(canonical.encode()).hexdigest()[:20],
            profiles=profiles,
            steps=self._dedupe_steps(steps),
            blockers=sorted(blockers),
            risks=sorted(risks),
            acceptance_gates=sorted(set(gates)),
        )

    @staticmethod
    def _steps(path: ProjectPath, project_ids: list[str], frameworks: list[str], gpu: bool) -> list[MigrationStep]:
        common = [
            ("restore", "RESTORE_ENVIRONMENT", "UV", [], ["OFFLINE_REPRODUCTION"]),
            ("baseline", "FREEZE_BASELINE", "PYTEST", ["restore"], ["TEST_IDENTITY"]),
            ("packaging", "MODERNIZE_PACKAGING", "LIBCST", ["baseline"], ["LOCK_REPRODUCIBLE", "IMPORT_SMOKE"]),
            (
                "interpreter",
                "UPGRADE_INTERPRETER",
                "PYTHON_AST",
                ["packaging"],
                ["SYNTAX", "BYTES_TEXT", "GOLDEN_BEHAVIOR"],
            ),
        ]
        specific: list[tuple[str, str, str, list[str], list[str]]] = []
        if path == ProjectPath.WEB:
            if "DJANGO" in frameworks:
                specific.append(
                    (
                        "django",
                        "MIGRATE_DJANGO",
                        "LIBCST",
                        ["interpreter"],
                        ["DJANGO_SYSTEM_CHECK", "HTTP_CONTRACT", "AUTH_SESSION", "MIGRATION_DIFF"],
                    )
                )
            if "FLASK" in frameworks:
                specific.append(
                    (
                        "flask",
                        "MIGRATE_FLASK",
                        "LIBCST",
                        ["interpreter"],
                        ["HTTP_CONTRACT", "CONTEXT_LIFETIME", "SESSION_CONTRACT"],
                    )
                )
        elif path == ProjectPath.DATA_PIPELINE:
            specific.extend(
                [
                    (
                        "pipeline",
                        "MIGRATE_DATA_PIPELINE",
                        "LIBCST",
                        ["interpreter"],
                        ["CLEAN_KERNEL", "DATA_CONTRACT", "RETRY_BACKFILL"],
                    ),
                    (
                        "numerics",
                        "VALIDATE_NUMERICS",
                        "DATA_VALIDATOR",
                        ["pipeline"],
                        ["DTYPE", "TOLERANCE", "BUSINESS_INVARIANT"],
                    ),
                ]
            )
        elif path == ProjectPath.AI_ML:
            specific.extend(
                [
                    (
                        "model",
                        "MIGRATE_MODEL",
                        "MODEL_VALIDATOR",
                        ["interpreter"],
                        ["ARTIFACT_LOAD_MATRIX", "FEATURE_SIGNATURE"],
                    ),
                    (
                        "model-validate",
                        "VALIDATE_MODEL",
                        "MODEL_VALIDATOR",
                        ["model"],
                        ["INFERENCE", "TRAINING", "PERFORMANCE"],
                    ),
                ]
            )
        if gpu:
            specific.append(
                (
                    "gpu",
                    "VALIDATE_GPU_STACK",
                    "MODEL_VALIDATOR",
                    [specific[-1][0] if specific else "interpreter"],
                    ["DRIVER_CUDA_CUDNN_WHEEL_MATRIX"],
                )
            )
        result = []
        for key, step_type, executor, depends, validations in [*common, *specific]:
            result.append(
                MigrationStep(
                    step_id=f"{key}-{'-'.join(sorted(project_ids))}",
                    step_type=step_type,
                    project_ids=sorted(project_ids),
                    executor_policy={"executor": executor, "network": "DENY", "secrets": "NONE"},
                    depends_on=[f"{dependency}-{'-'.join(sorted(project_ids))}" for dependency in depends],
                    validations=validations,
                )
            )
        return result

    @staticmethod
    def _dedupe_steps(steps: list[MigrationStep]) -> list[MigrationStep]:
        return list({step.step_id: step for step in steps}.values())

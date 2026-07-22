from __future__ import annotations

import json
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any

from .codemod import LibCstModernizer
from .contracts import (
    Capabilities,
    EngineError,
    ErrorCode,
    ExecuteStepRequest,
    ExecutorType,
    JobRequest,
    JobResponse,
    JobStatus,
)
from .discovery import SafePythonDiscovery
from .environment import EnvironmentReproducer
from .evidence import UnifiedPythonEvidenceMapper
from .legacy import LegacyPythonAnalyzer
from .ml import MachineLearningModernizationAdvisor
from .packaging import PackagingModernizationAdvisor
from .pipeline import PipelineAndNotebookAnalyzer
from .planning import CompatibilityRegistry, PythonMigrationPlanner
from .runners import PythonRunnerRouter
from .semantic import PythonSemanticGraphBuilder
from .validation import PythonValidationJudge
from .web import DjangoModernizationAdvisor, FlaskModernizationAdvisor


class PythonEngine:
    def __init__(self, approved_workspace_root: Path, compatibility_registry: Path | None = None) -> None:
        self.approved_workspace_root = approved_workspace_root.resolve()
        registry = (
            compatibility_registry
            or Path(__file__).resolve().parents[2] / "compatibility-registry" / "python-compatibility-v1.json"
        )
        self.discovery = SafePythonDiscovery()
        self.environment = EnvironmentReproducer()
        self.semantic = PythonSemanticGraphBuilder()
        self.planner = PythonMigrationPlanner(CompatibilityRegistry(registry))
        self.codemod = LibCstModernizer()
        self.pipeline = PipelineAndNotebookAnalyzer()
        self.ml = MachineLearningModernizationAdvisor()
        self.legacy = LegacyPythonAnalyzer()
        self.packaging = PackagingModernizationAdvisor()
        self.runners = PythonRunnerRouter()
        self.django = DjangoModernizationAdvisor()
        self.flask = FlaskModernizationAdvisor()
        self.judge = PythonValidationJudge()
        self.evidence = UnifiedPythonEvidenceMapper()
        self._jobs: dict[str, tuple[str, str, JobResponse]] = {}
        self._idempotency: dict[tuple[str, str, str], tuple[str, JobResponse]] = {}
        self._lock = RLock()

    @staticmethod
    def capabilities() -> Capabilities:
        return Capabilities(
            source_versions=["2.7", "3.5", "3.6", "3.7", "3.8", "3.9", "3.10", "3.11", "3.12", "3.13", "3.14"],
            supported_target_versions=["3.10", "3.11", "3.12", "3.13", "3.14"],
            project_models=[
                "PYPROJECT",
                "SETUP_PY",
                "SETUP_CFG",
                "REQUIREMENTS",
                "POETRY",
                "PIPENV",
                "CONDA",
                "UV",
                "BAZEL",
                "NOTEBOOK",
            ],
            frameworks=["DJANGO", "FLASK", "AIRFLOW", "CELERY", "SPARK", "TENSORFLOW", "PYTORCH", "SCIKIT_LEARN"],
            runner_profiles=[
                "PYTHON_LEGACY_LINUX",
                "PYTHON_MODERN_CPU",
                "PYTHON_MODERN_GPU",
                "PYTHON_WINDOWS",
                "PYTHON_NOTEBOOK",
            ],
            validation_capabilities=[
                "ENVIRONMENT",
                "SYNTAX",
                "TYPE_STATE",
                "TEST_IDENTITY",
                "HTTP",
                "DATA",
                "NUMERICAL",
                "MODEL_ARTIFACT",
                "INFERENCE",
                "TRAINING",
                "PERFORMANCE",
            ],
            sandbox_requirements={
                "network": "DENY_BY_DEFAULT",
                "controlPlaneSecrets": "FORBIDDEN",
                "customerCodeInControlPlane": False,
            },
        )

    def scan(self, request: JobRequest) -> JobResponse:
        input_hash = self._hash(
            request.repository_snapshot_ref, request.workspace_ref, request.profile, request.options
        )
        return self._idempotent(
            request.organization_id, "scan", request.idempotency_key, input_hash, lambda: self._scan(request)
        )

    def plan(self, request: JobRequest) -> JobResponse:
        input_hash = self._hash(
            request.repository_snapshot_ref, request.workspace_ref, request.profile, request.options
        )
        return self._idempotent(
            request.organization_id, "plan", request.idempotency_key, input_hash, lambda: self._plan(request)
        )

    def execute_step(self, request: ExecuteStepRequest) -> JobResponse:
        input_hash = self._hash(
            request.migration_run_id,
            request.migration_plan_version,
            request.step_definition.model_dump(mode="json"),
            request.workspace_ref,
            request.source_commit,
            request.execution_budget.model_dump(mode="json"),
            request.policy,
        )
        return self._idempotent(
            request.organization_id, "execute", request.idempotency_key, input_hash, lambda: self._execute(request)
        )

    def validate(self, request: JobRequest) -> JobResponse:
        input_hash = self._hash(
            request.repository_snapshot_ref, request.workspace_ref, request.profile, request.options
        )
        return self._idempotent(
            request.organization_id, "validate", request.idempotency_key, input_hash, lambda: self._validate(request)
        )

    def get_job(self, organization_id: str, job_id: str) -> JobResponse:
        with self._lock:
            stored = self._jobs.get(job_id)
            if stored is None or stored[0] != organization_id:
                return self._failure(
                    job_id,
                    ErrorCode.POLICY_BLOCKED,
                    "Job is not visible in this organization.",
                    "Use the owning organization context.",
                )
            return stored[2]

    def cancel(self, organization_id: str, job_id: str) -> JobResponse:
        with self._lock:
            stored = self._jobs.get(job_id)
            if stored is None or stored[0] != organization_id:
                return self._failure(
                    job_id,
                    ErrorCode.POLICY_BLOCKED,
                    "Job is not visible in this organization.",
                    "Use the owning organization context.",
                )
            if stored[2].status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
                return self._failure(
                    job_id,
                    ErrorCode.POLICY_BLOCKED,
                    "Terminal job state cannot be rewritten by cancellation.",
                    "Inspect the immutable terminal result.",
                )
            cancelled = JobResponse(job_id=job_id, status=JobStatus.CANCELLED)
            self._jobs[job_id] = (organization_id, stored[1], cancelled)
            return cancelled

    def _scan(self, request: JobRequest) -> JobResponse:
        job_id = self._job_id(request.organization_id, "scan", request.idempotency_key)
        try:
            root = self._workspace(request.workspace_ref)
            inventory = self.discovery.discover(root, request.workspace_ref)
            if not inventory.projects:
                return self._failure(
                    job_id,
                    ErrorCode.PYTHON_PROJECT_NOT_FOUND,
                    "No Python project root was found.",
                    "Provide a Python manifest or source root.",
                )
            environment = self.environment.analyze(root, inventory)
            graph = self.semantic.build(root)
            pipeline = self.pipeline.analyze(root)
            ml = self.ml.inventory(root)
            legacy = self.legacy.assess(root)
            packaging = self.packaging.assess(
                root,
                target_python=str(request.options.get("targetPython", "3.14")),
                target_numpy_major=int(request.options.get("targetNumpyMajor", 2)),
                cuda=str(request.options["cuda"]) if "cuda" in request.options else None,
            )
            runner = self.runners.route(
                str(request.options.get("pythonVersion", "3.14")),
                str(request.options.get("operatingSystem", "LINUX")),
                requires_gpu=bool(request.options.get("requiresGpu", False)),
                notebook=bool(request.options.get("notebookRunner", False)),
            )
            django_compatibility = request.options.get("djangoThirdPartyCompatibility", {})
            if not isinstance(django_compatibility, dict):
                raise ValueError("DJANGO_THIRD_PARTY_COMPATIBILITY_MUST_BE_AN_OBJECT")
            web = {
                "django": self.django.assess(
                    root,
                    request.options.get("djangoCurrent"),
                    request.options.get("djangoTarget"),
                    {str(name): bool(value) for name, value in django_compatibility.items()},
                )
                if "DJANGO" in inventory.frameworks
                else None,
                "flask": self.flask.assess(root, bool(request.options.get("requiresAsgi", False)))
                if "FLASK" in inventory.frameworks
                else None,
            }
            artifacts = {
                "inventory": inventory,
                "environment": environment,
                "semanticGraph": graph,
                "pipelineProfile": pipeline,
                "machineLearningProfile": ml,
                "legacyPythonProfile": legacy,
                "packagingProfile": packaging,
                "runnerRoutingDecision": runner.as_dict(),
                "webProfiles": web,
            }
            evidence_refs = []
            extensions = []
            for artifact_type, artifact in artifacts.items():
                extension = self.evidence.map(
                    request.organization_id,
                    request.repository_snapshot_ref,
                    artifact_type.upper(),
                    artifact,
                    "INCONCLUSIVE",
                )
                evidence_refs.append("sha256:" + extension.content_hash)
                extensions.append(extension)
            return JobResponse(
                job_id=job_id,
                status=JobStatus.SUCCEEDED,
                evidence_refs=evidence_refs,
                result={**artifacts, "evidenceExtensions": extensions},
            )
        except ValueError as error:
            return self._failure(
                job_id, ErrorCode.POLICY_BLOCKED, str(error), "Use a workspace below the approved root."
            )
        except Exception as error:  # noqa: BLE001 - normalized at the engine boundary
            return self._failure(
                job_id,
                ErrorCode.INTERNAL_ENGINE_ERROR,
                f"Static scan failed: {type(error).__name__}",
                "Inspect sanitized engine evidence.",
            )

    def _plan(self, request: JobRequest) -> JobResponse:
        job_id = self._job_id(request.organization_id, "plan", request.idempotency_key)
        try:
            root = self._workspace(request.workspace_ref)
            inventory = self.discovery.discover(root, request.workspace_ref)
            environment = self.environment.analyze(root, inventory)
            plan = self.planner.plan(inventory, environment.reproducibility_status.value, request.profile)
            status = "FAILED" if plan.blockers else "INCONCLUSIVE"
            extension = self.evidence.map(
                request.organization_id, request.repository_snapshot_ref, "PYTHON_MIGRATION_PLAN", plan, status
            )
            return JobResponse(
                job_id=job_id,
                status=JobStatus.SUCCEEDED,
                evidence_refs=["sha256:" + extension.content_hash],
                result={"plan": plan, "evidenceExtension": extension},
            )
        except ValueError as error:
            return self._failure(
                job_id, ErrorCode.POLICY_BLOCKED, str(error), "Use a workspace below the approved root."
            )
        except Exception as error:  # noqa: BLE001
            return self._failure(
                job_id,
                ErrorCode.INTERNAL_ENGINE_ERROR,
                f"Planning failed: {type(error).__name__}",
                "Inspect sanitized planning evidence.",
            )

    def _execute(self, request: ExecuteStepRequest) -> JobResponse:
        job_id = self._job_id(request.organization_id, "execute", request.idempotency_key)
        if request.step_definition.executor_type != ExecutorType.LIBCST:
            code = (
                ErrorCode.GPU_RUNNER_REQUIRED
                if request.step_definition.executor_type == ExecutorType.MODEL_VALIDATOR
                else ErrorCode.POLICY_BLOCKED
            )
            return self._failure(
                job_id,
                code,
                "This step requires a leased capability-matched Runner; no in-process fallback is permitted.",
                "Route through the shared ELMOS Runner lease.",
            )
        try:
            root = self._workspace(request.workspace_ref)
            relative = str(request.step_definition.configuration.get("relativePath", ""))
            path = (root / relative).resolve(strict=True)
            if (root != path and root not in path.parents) or path.is_symlink() or path.suffix != ".py":
                raise ValueError("CODEMOD_PATH_OUTSIDE_APPROVED_WORKSPACE")
            source = path.read_text(encoding="utf-8")
            result = self.codemod.modernize_old_python_apis(source)
            encoded = result.transformed_source.encode()
            if len(encoded) > request.execution_budget.max_bytes_written:
                raise ValueError("CODEMOD_WRITE_BUDGET_EXCEEDED")
            if result.changed:
                path.write_text(result.transformed_source, encoding="utf-8")
            status = "PASSED" if result.idempotent and result.comments_preserved else "FAILED"
            extension = self.evidence.map(
                request.organization_id, request.source_commit, "PYTHON_CODEMOD", result, status
            )
            return JobResponse(
                job_id=job_id,
                status=JobStatus.SUCCEEDED if status == "PASSED" else JobStatus.FAILED,
                evidence_refs=["sha256:" + extension.content_hash],
                result={"transformation": result.__dict__, "evidenceExtension": extension},
            )
        except (OSError, UnicodeError, ValueError) as error:
            return self._failure(
                job_id, ErrorCode.POLICY_BLOCKED, str(error), "Submit an approved Python source path and budget."
            )
        except Exception as error:  # noqa: BLE001
            return self._failure(
                job_id,
                ErrorCode.PYTHON_CST_PARSE_FAILED,
                f"LibCST transformation failed: {type(error).__name__}",
                "Route unsupported Python 2 grammar through the Legacy Parser adapter.",
            )

    def _validate(self, request: JobRequest) -> JobResponse:
        job_id = self._job_id(request.organization_id, "validate", request.idempotency_key)
        decision = self.judge.judge(request.profile, request.options)
        extension = self.evidence.map(
            request.organization_id,
            request.repository_snapshot_ref,
            "PYTHON_VALIDATION_DECISION",
            decision,
            decision["decision"],
        )
        status = JobStatus.SUCCEEDED if decision["decision"] == "PASS" else JobStatus.FAILED
        error = (
            None
            if status == JobStatus.SUCCEEDED
            else EngineError(
                error_code=ErrorCode.VALIDATION_FAILED,
                message="Python path-specific validation did not pass.",
                evidence_refs=["sha256:" + extension.content_hash],
                suggested_action="Provide every required Web, Data, or AI/ML evidence item.",
            )
        )
        return JobResponse(
            job_id=job_id,
            status=status,
            evidence_refs=["sha256:" + extension.content_hash],
            result={"decision": decision, "evidenceExtension": extension},
            error=error,
        )

    def _idempotent(
        self,
        organization_id: str,
        operation: str,
        idempotency_key: str,
        input_hash: str,
        action: Callable[[], JobResponse],
    ) -> JobResponse:
        scope = (organization_id, operation, idempotency_key)
        with self._lock:
            existing = self._idempotency.get(scope)
            if existing:
                if existing[0] != input_hash:
                    return self._failure(
                        existing[1].job_id,
                        ErrorCode.POLICY_BLOCKED,
                        "Idempotency key was already bound to different immutable inputs.",
                        "Use the original inputs or a new idempotency key.",
                    )
                return existing[1]
            response = action()
            self._idempotency[scope] = (input_hash, response)
            self._jobs[response.job_id] = (organization_id, input_hash, response)
            return response

    def _workspace(self, workspace_ref: str) -> Path:
        candidate = (self.approved_workspace_root / workspace_ref).resolve(strict=True)
        if candidate != self.approved_workspace_root and self.approved_workspace_root not in candidate.parents:
            raise ValueError("WORKSPACE_PATH_ESCAPES_APPROVED_ROOT")
        if not candidate.is_dir() or candidate.is_symlink():
            raise ValueError("WORKSPACE_MUST_BE_A_REAL_DIRECTORY")
        return candidate

    @staticmethod
    def _hash(*values: Any) -> str:
        canonical = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)
        return sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _job_id(organization_id: str, operation: str, key: str) -> str:
        return "python-" + sha256(f"{organization_id}:{operation}:{key}".encode()).hexdigest()[:32]

    @staticmethod
    def _failure(job_id: str, code: ErrorCode, message: str, action: str) -> JobResponse:
        return JobResponse(
            job_id=job_id,
            status=JobStatus.FAILED,
            error=EngineError(error_code=code, message=message, suggested_action=action),
        )

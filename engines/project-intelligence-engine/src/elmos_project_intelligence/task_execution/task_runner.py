"""Fail-closed execution ledger for the 500 source backlog tasks.

The source backlog is a requirements inventory. A task becomes locally
executed only when its exact Project Intelligence handler runs through the
durable service. Local execution never proves product acceptance, external
runtime behavior, or certification.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..canonical import canonical_digest, canonical_value
from ..runtime import SKILL_REGISTRY, RuntimeRequest
from ..service import ProjectIntelligenceService


def _parse_catalog(text: str, collection: str) -> dict[str, Any]:
    """Parse the small source YAML subset without executing package code."""
    root: dict[str, Any] = {collection: []}
    items: list[dict[str, Any]] = root[collection]
    current: dict[str, Any] | None = None
    current_list: list[str] | None = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw.startswith("- id:"):
            current = {"id": raw.split(":", 1)[1].strip()}
            items.append(current)
            current_list = None
        elif current is not None and raw.startswith("  - "):
            if current_list is None:
                raise ValueError("catalog list item has no list field")
            current_list.append(stripped[2:].strip())
        elif current is not None and raw.startswith("  ") and ":" in stripped:
            key, raw_value = stripped.split(":", 1)
            value = raw_value.strip()
            if not value:
                current_list = []
                current[key] = current_list
            elif value == "[]":
                current[key] = []
                current_list = None
            else:
                current[key] = value
                current_list = None
        elif not raw.startswith(" ") and ":" in raw:
            key, raw_value = raw.split(":", 1)
            value = raw_value.strip()
            if key == collection and not value:
                root[key] = items
            else:
                root[key] = int(value) if value.isdigit() else value
    return root


@dataclass(frozen=True, slots=True)
class TaskExecutionReceipt:
    task_id: str
    skill: str
    batch: str
    source_status: str
    execution_state: str
    handler_state: str | None
    handler_code: str | None
    result_digest: str | None
    artifact_digest: str | None
    evidence_state: str
    acceptance_state: str
    external_evidence_status: str
    independent_evidence_status: str
    certification_status: str
    blockers: tuple[str, ...]
    receipt_digest: str


class ProjectIntelligenceTaskRunner:
    """Bind each source task to its exact handler without manufacturing success."""

    DEFAULT_TASKS_PATH = (
        Path(__file__).resolve().parents[5]
        / "skills/elmos-project-intelligence-skills-v1.1.0/backlog/tasks.yaml"
    )

    def __init__(
        self,
        tasks_path: Path | str | None = None,
        *,
        service: ProjectIntelligenceService | None = None,
    ) -> None:
        self.tasks_path = Path(tasks_path) if tasks_path else self.DEFAULT_TASKS_PATH
        self.service = service
        self.tasks: dict[str, dict[str, Any]] = {}
        self.skill_tasks: dict[str, list[dict[str, Any]]] = {}
        self.batch_tasks: dict[str, list[dict[str, Any]]] = {}
        self._load_tasks()

    def _load_tasks(self) -> None:
        if not self.tasks_path.is_file() or self.tasks_path.is_symlink():
            raise FileNotFoundError(f"task catalog is unavailable: {self.tasks_path}")
        data = _parse_catalog(self.tasks_path.read_text(encoding="utf-8"), "tasks")
        rows = data.get("tasks")
        if data.get("task_count") != 500 or not isinstance(rows, list) or len(rows) != 500:
            raise ValueError("task catalog must contain exactly 500 declared tasks")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("task catalog row must be an object")
            task_id, skill = row.get("id"), row.get("skill")
            if not isinstance(task_id, str) or task_id in self.tasks:
                raise ValueError("task identifiers must be unique strings")
            if not isinstance(skill, str) or skill not in SKILL_REGISTRY:
                raise ValueError(f"task references an unknown exact Skill: {task_id}")
            if row.get("status") != "todo":
                raise ValueError("source task status must remain todo")
            dependencies = row.get("depends_on", [])
            if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
                raise ValueError("task dependencies must be an identifier list")
            self.tasks[task_id] = row
            self.skill_tasks.setdefault(skill, []).append(row)
            self.batch_tasks.setdefault(str(row.get("batch", "")), []).append(row)
        if set(self.skill_tasks) != set(SKILL_REGISTRY) or any(
            len(rows) != 10 for rows in self.skill_tasks.values()
        ):
            raise ValueError("task catalog must bind ten tasks to every exact Skill")
        for task_id, row in self.tasks.items():
            for dependency in row.get("depends_on", []):
                if (
                    dependency not in self.tasks
                    and dependency not in SKILL_REGISTRY
                ) or dependency == task_id:
                    raise ValueError(f"task dependency is unresolved: {task_id}")

    @staticmethod
    def _receipt(
        row: Mapping[str, Any],
        *,
        execution_state: str,
        handler_state: str | None = None,
        handler_code: str | None = None,
        result_digest: str | None = None,
        artifact_digest: str | None = None,
        evidence_state: str = "NOT_RUN",
        blockers: tuple[str, ...] = (),
    ) -> TaskExecutionReceipt:
        document = {
            "task_id": str(row["id"]),
            "skill": str(row["skill"]),
            "batch": str(row.get("batch", "")),
            "source_status": str(row["status"]),
            "execution_state": execution_state,
            "handler_state": handler_state,
            "handler_code": handler_code,
            "result_digest": result_digest,
            "artifact_digest": artifact_digest,
            "evidence_state": evidence_state,
            "acceptance_state": "NOT_RUN",
            "external_evidence_status": "NOT_RUN",
            "independent_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
            "blockers": list(blockers),
        }
        return TaskExecutionReceipt(
            task_id=document["task_id"],
            skill=document["skill"],
            batch=document["batch"],
            source_status=document["source_status"],
            execution_state=execution_state,
            handler_state=handler_state,
            handler_code=handler_code,
            result_digest=result_digest,
            artifact_digest=artifact_digest,
            evidence_state=evidence_state,
            acceptance_state="NOT_RUN",
            external_evidence_status="NOT_RUN",
            independent_evidence_status="NOT_RUN",
            certification_status="NOT_CERTIFIED",
            blockers=blockers,
            receipt_digest=canonical_digest(canonical_value(document)),
        )

    def prepare_task(self, task_id: str) -> TaskExecutionReceipt:
        row = self.tasks.get(task_id)
        if row is None:
            raise KeyError(f"unknown task: {task_id}")
        return self._receipt(
            row,
            execution_state="NOT_RUN",
            blockers=("EXACT_RUNTIME_REQUEST_REQUIRED", "ACCEPTANCE_EVIDENCE_REQUIRED"),
        )

    def execute_task(
        self,
        task_id: str,
        request: Mapping[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
        dependency_receipts: Mapping[str, TaskExecutionReceipt] | None = None,
        dependency_skills_executed: tuple[str, ...] = (),
    ) -> TaskExecutionReceipt:
        row = self.tasks.get(task_id)
        if row is None:
            raise KeyError(f"unknown task: {task_id}")
        if request is None:
            return self.prepare_task(task_id)
        if self.service is None:
            return self._receipt(row, execution_state="BLOCKED", blockers=("TRUSTED_LOCAL_SERVICE_REQUIRED",))
        if not idempotency_key:
            raise ValueError("idempotency_key is required for task execution")
        RuntimeRequest.parse(request)
        supplied = dependency_receipts or {}
        missing = [
            dependency
            for dependency in row.get("depends_on", [])
            if (
                dependency in self.tasks
                and (
                    dependency not in supplied
                    or supplied[dependency].execution_state != "LOCAL_EXECUTED"
                )
            )
            or (
                dependency in SKILL_REGISTRY
                and dependency not in dependency_skills_executed
            )
        ]
        if missing:
            return self._receipt(
                row,
                execution_state="BLOCKED",
                blockers=tuple(f"DEPENDENCY_NOT_EXECUTED:{item}" for item in missing),
            )
        result = self.service.execute(str(row["skill"]), request, idempotency_key=idempotency_key)
        state = "BLOCKED" if result["state"] == "BLOCKED" else "LOCAL_EXECUTED"
        blockers = (
            (f"HANDLER_BLOCKED:{result['code']}",)
            if state == "BLOCKED"
            else ("PRODUCT_ACCEPTANCE_NOT_RUN",)
        )
        return self._receipt(
            row,
            execution_state=state,
            handler_state=result["state"],
            handler_code=result["code"],
            result_digest=result.get("result_digest"),
            artifact_digest=result.get("artifact_digest"),
            evidence_state=str(result.get("evidence_state", "NOT_RUN")),
            blockers=blockers,
        )

    def prepare_all_tasks(self) -> dict[str, TaskExecutionReceipt]:
        return {task_id: self.prepare_task(task_id) for task_id in self.tasks}

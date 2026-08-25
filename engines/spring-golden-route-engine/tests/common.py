from __future__ import annotations

from pathlib import Path

from elmos_spring_golden_route.runtime import REQUEST_SCHEMA_VERSION

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SHA1_A = "1" * 40
SHA1_B = "2" * 40


def request_for(
    skill_name: str,
    *,
    operation: str = "plan",
    tenant_id: str = "tenant-a",
    project_id: str = "project-a",
    run_id: str = "run-a",
    task_id: str = "task-a",
    actor_id: str = "actor-a",
    idempotency_key: str = "idem-a",
    objective: str = "Produce a bounded migration blueprint",
) -> dict[str, object]:
    input_value: dict[str, object]
    if operation == "describe":
        input_value = {}
    elif operation == "plan":
        input_value = {
            "objective": objective,
            "source": {"framework": "spring-boot", "version": "2.7.18", "commit": SHA1_A},
            "target": {"framework": "spring-boot", "version": "3.3.4", "commit": SHA1_B},
            "constraints": ["No production access"],
            "requested_outputs": [],
        }
    else:
        input_value = {}
    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "operation": operation,
        "skill_name": skill_name,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "run_id": run_id,
        "task_id": task_id,
        "actor_id": actor_id,
        "idempotency_key": idempotency_key,
        "input": input_value,
    }


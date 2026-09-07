from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .staging import Workspace


def plan_workspace_recovery(workspace: Workspace) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for staged in workspace.list_records():
        if staged.status == "RESERVED":
            action = "RELEASE_OR_REASSIGN"
        elif staged.status == "WRITING":
            action = "QUARANTINE_OR_DELETE_PARTIAL"
        elif staged.status == "SEALED":
            action = "VERIFY_AND_PROMOTE"
        elif staged.status == "CAS_PROMOTED":
            action = "INCLUDE_IN_TREE_IF_REQUIRED"
        elif staged.status == "TREE_INCLUDED":
            action = "RECONSTRUCT_AND_VALIDATE_TREE"
        elif staged.status == "PUBLISHED":
            action = "VERIFY_PUBLISHED_POINTER"
        elif staged.status in {"ABORTED", "QUARANTINED"}:
            action = "RETAIN_OR_GC_BY_POLICY"
        else:
            action = "QUARANTINE_UNKNOWN_STATE"
        plan.append({"staged_file": asdict(staged), "recovery_action": action})
    return plan

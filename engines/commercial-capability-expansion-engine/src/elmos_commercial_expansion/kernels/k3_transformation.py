"""K3: Transformation Kernel for Elmos Commercial Capability Expansion."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional

from ..models import TaskContext


class TransformationKernel:
    """Routes code edits across deterministic engines, compiler APIs, and neurosymbolic generation."""

    def __init__(self):
        self.explainability_ledger: List[Dict[str, Any]] = []
        self.rollback_maps: Dict[str, Dict[str, str]] = {}

    def route_rewrite_strategy(self, file_path: str, change_intent: str) -> Dict[str, Any]:
        """Chooses the most deterministic rewrite engine available for the requested change."""
        intent_lower = change_intent.lower()

        if any(k in intent_lower for k in ["rename", "import", "package", "namespace", "method signature"]):
            engine = "AST_COMPILER_API"
            deterministic = True
        elif any(k in intent_lower for k in ["security fix", "cve", "sanitize", "vulnerability"]):
            engine = "SEMGREP_RULE_ENGINE"
            deterministic = True
        elif any(k in intent_lower for k in ["format", "pattern", "replace pattern", "structural"]):
            engine = "STRUCTURAL_AST_GREP"
            deterministic = True
        elif any(k in intent_lower for k in ["spring modern", "upgrade boot", "jakarta"]):
            engine = "OPENREWRITE_RECIPE_ENGINE"
            deterministic = True
        else:
            engine = "NEUROSYMBOLIC_LLM_ASSISTED"
            deterministic = False

        return {
            "target_file": file_path,
            "selected_engine": engine,
            "is_deterministic": deterministic,
            "requires_human_approval": not deterministic,
        }

    def record_transformation_edit(
        self,
        task_id: str,
        file_path: str,
        before_content: str,
        after_content: str,
        rule_applied: str,
        engine_used: str,
        rationale: str,
    ) -> Dict[str, Any]:
        """Appends edit to immutable explainability ledger and builds rollback mapping."""
        before_digest = hashlib.sha256(before_content.encode("utf-8")).hexdigest()
        after_digest = hashlib.sha256(after_content.encode("utf-8")).hexdigest()
        edit_id = f"edit-{int(time.time()*1000)}-{after_digest[:8]}"

        entry = {
            "edit_id": edit_id,
            "task_id": task_id,
            "file_path": file_path,
            "before_sha256": before_digest,
            "after_sha256": after_digest,
            "rule_applied": rule_applied,
            "engine_used": engine_used,
            "rationale": rationale,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.explainability_ledger.append(entry)

        if task_id not in self.rollback_maps:
            self.rollback_maps[task_id] = {}
        # Stores reverse mapping for atomic rollback
        self.rollback_maps[task_id][file_path] = before_content

        return entry

    def get_rollback_snapshot(self, task_id: str) -> Dict[str, str]:
        """Retrieves original pre-transformation state for rollback."""
        return self.rollback_maps.get(task_id, {})

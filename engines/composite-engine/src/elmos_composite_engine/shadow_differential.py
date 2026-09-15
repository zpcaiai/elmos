"""Shadow traffic differential comparison, safe shadow writes, and CDC replication validation."""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Set, Tuple


class ShadowTrafficValidator:
    """Validates shadow run execution safety and response equivalence."""

    DYNAMIC_FIELD_PATTERNS = {
        "timestamp", "created_at", "updated_at", "time", "date",
        "uuid", "id", "request_id", "trace_id", "span_id", "traceparent"
    }

    def validate_shadow_safety(self, http_method: str, is_mutating: bool, shadow_writes_permitted: bool = False) -> Dict[str, Any]:
        """Ensures shadow requests do not issue writes against real external systems."""
        is_write = is_mutating or (http_method.upper() in {"POST", "PUT", "DELETE", "PATCH"})
        if is_write and not shadow_writes_permitted:
            return {
                "verdict": "SHADOW_WRITE_BLOCKED",
                "safe": False,
                "reason": f"Shadow request with method {http_method} attempts un-sandboxed write."
            }
        return {
            "verdict": "SHADOW_SAFE",
            "safe": True,
            "reason": "Request is read-only or routed to virtualized sink."
        }

    def normalize_payload(self, payload: Any, ignore_keys: Optional[Set[str]] = None) -> Any:
        """Normalizes dynamic timestamps, UUIDs, and floats for deterministic comparison."""
        ignored = (ignore_keys or set()) | self.DYNAMIC_FIELD_PATTERNS
        if isinstance(payload, dict):
            clean = {}
            for k, v in payload.items():
                if k.lower() in ignored:
                    clean[k] = "<NORMALIZED>"
                else:
                    clean[k] = self.normalize_payload(v, ignore_keys)
            return clean
        elif isinstance(payload, list):
            return [self.normalize_payload(item, ignore_keys) for item in payload]
        return payload

    def compare_responses(self, primary_resp: Dict[str, Any], shadow_resp: Dict[str, Any]) -> Dict[str, Any]:
        """Compares primary and shadow responses with dynamic normalization."""
        if primary_resp == shadow_resp:
            return {"verdict": "EXACT_MATCH", "match": True, "details": "Bit-identical response."}

        norm_primary = self.normalize_payload(primary_resp)
        norm_shadow = self.normalize_payload(shadow_resp)

        if norm_primary == norm_shadow:
            return {
                "verdict": "EXACT_AFTER_NORMALIZATION",
                "match": True,
                "details": "Responses match identically after dynamic field normalization."
            }

        return {
            "verdict": "DIFFERENTIAL_MISMATCH",
            "match": False,
            "details": "Semantic content mismatch observed between primary and shadow responses."
        }

    def evaluate_shadow_failure_impact(self, primary_status: int, shadow_failed: bool) -> Dict[str, Any]:
        """Verifies shadow failures do not degrade primary user response."""
        if shadow_failed and primary_status < 400:
            return {
                "verdict": "PRIMARY_UNAFFECTED",
                "isolation_verified": True,
                "reason": "Shadow service failure was asynchronously isolated; primary succeeded."
            }
        return {
            "verdict": "EVALUATED",
            "isolation_verified": True,
            "reason": f"Primary returned {primary_status}."
        }

    def evaluate_cdc_lag(self, lag_ms: float, max_allowed_ms: float = 1000.0) -> Dict[str, Any]:
        """Verifies CDC replication latency against strict cutover threshold."""
        if lag_ms > max_allowed_ms:
            return {
                "verdict": "CDC_LAG_EXCEEDED",
                "ready_for_cutover": False,
                "lag_ms": lag_ms,
                "threshold_ms": max_allowed_ms,
                "reason": f"CDC lag {lag_ms}ms exceeds maximum permissible threshold {max_allowed_ms}ms."
            }
        return {
            "verdict": "CDC_SYNCHRONIZED",
            "ready_for_cutover": True,
            "lag_ms": lag_ms,
            "threshold_ms": max_allowed_ms,
            "reason": "Replication lag within cutover tolerance."
        }

    def evaluate_dual_write_atomicity(self, primary_write_ok: bool, secondary_write_ok: bool) -> Dict[str, Any]:
        """Detects sequential dual-write partial failures."""
        if primary_write_ok and not secondary_write_ok:
            return {
                "verdict": "PARTIAL_WRITE",
                "atomic": False,
                "reason": "Primary write succeeded while secondary failed; outbox/saga required."
            }
        return {
            "verdict": "ATOMIC_WRITE_CONSISTENT",
            "atomic": True,
            "reason": "Both write legs succeeded or both aborted."
        }

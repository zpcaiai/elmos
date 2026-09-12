"""Diagnostic Root Cause Recommendation Engine - Batch 41 Skill 1404.

Analyzes execution and migration failure signatures, matches knowledge base patterns,
generates ranked root cause hypotheses, and recommends actionable remediations.
"""

from datetime import datetime, timezone
import re
from typing import Dict, List, Optional, Any, Tuple
import uuid

from .types import (
    DiagnosticSeverity,
    RemediationEffort,
    RootCauseHypothesis,
    DiagnosticReport,
)


class DiagnosticRootCauseRecommendationEngine:
    """Diagnoses failure signatures and recommends prioritized root causes and repairs."""

    def __init__(self) -> None:
        self._patterns: List[Dict[str, Any]] = []
        self._reports: Dict[str, DiagnosticReport] = {}
        self._initialize_default_patterns()

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _initialize_default_patterns(self) -> None:
        """Seed known migration failure diagnostic patterns."""
        self.register_pattern(
            pattern_regex=r"(?i)connection (refused|timed out|reset by peer)",
            cause_name="Database/Network Connectivity Interruption",
            recommended_action="Verify database endpoint availability, security group ingress, and connection pooling parameters.",
            effort=RemediationEffort.IMMEDIATE_RETRY,
            auto_fix=True,
            base_confidence=0.92,
        )
        self.register_pattern(
            pattern_regex=r"(?i)(table|column|relation) [\"']?(\w+)[\"']? does not exist",
            cause_name="Schema Definition Missing or Drift",
            recommended_action="Apply pending DDL migration scripts and check database catalog synchronization.",
            effort=RemediationEffort.CONFIG_UPDATE,
            auto_fix=True,
            base_confidence=0.95,
        )
        self.register_pattern(
            pattern_regex=r"(?i)(unique constraint|duplicate key|integrity constraint) .* violated",
            cause_name="Data Uniqueness Collision",
            recommended_action="Inspect source-to-target key mappings and check sequence or auto-increment offset.",
            effort=RemediationEffort.AUTOMATIC_PATCH,
            auto_fix=True,
            base_confidence=0.88,
        )
        self.register_pattern(
            pattern_regex=r"(?i)(syntax error|parse error) at or near",
            cause_name="SQL Dialect Transpilation Incompatibility",
            recommended_action="Update dialect AST transpiler rules to handle target database parser constructs.",
            effort=RemediationEffort.MANUAL_REFACTOR,
            auto_fix=False,
            base_confidence=0.85,
        )
        self.register_pattern(
            pattern_regex=r"(?i)(out of memory|java\.lang\.OutOfMemoryError|killed by oom)",
            cause_name="Resource Exhaustion (OOM)",
            recommended_action="Scale batch chunk size downwards or increase pod memory allocation limits.",
            effort=RemediationEffort.CONFIG_UPDATE,
            auto_fix=False,
            base_confidence=0.90,
        )

    def register_pattern(
        self,
        pattern_regex: str,
        cause_name: str,
        recommended_action: str,
        effort: RemediationEffort,
        auto_fix: bool = False,
        base_confidence: float = 0.8,
    ) -> str:
        """Register a diagnostic pattern with associated root cause and remediation."""
        pattern_id = f"pat-{uuid.uuid4().hex[:8]}"
        self._patterns.append({
            "pattern_id": pattern_id,
            "regex": re.compile(pattern_regex),
            "cause_name": cause_name,
            "recommended_action": recommended_action,
            "effort": effort,
            "auto_fix": auto_fix,
            "confidence": min(1.0, max(0.1, base_confidence)),
            "match_count": 0,
            "confirmed_count": 0,
        })
        return pattern_id

    def diagnose_error(
        self,
        run_id: str,
        error_message: str,
        stack_trace: str = "",
    ) -> DiagnosticReport:
        """Analyze failure strings and return a structured diagnostic report."""
        if not run_id:
            raise ValueError("run_id must not be empty")
        if not error_message:
            raise ValueError("error_message must not be empty")

        full_text = f"{error_message}\n{stack_trace}"
        matched_hypotheses: List[RootCauseHypothesis] = []

        for p in self._patterns:
            match = p["regex"].search(full_text)
            if match:
                p["match_count"] += 1
                hyp = RootCauseHypothesis(
                    hypothesis_id=f"hyp-{uuid.uuid4().hex[:8]}",
                    cause_name=p["cause_name"],
                    confidence_score=p["confidence"],
                    matching_error_pattern=p["regex"].pattern,
                    recommended_action=p["recommended_action"],
                    effort=p["effort"],
                    automated_fix_available=p["auto_fix"],
                )
                matched_hypotheses.append(hyp)

        # Sort hypotheses by confidence descending
        matched_hypotheses.sort(key=lambda h: h.confidence_score, reverse=True)

        primary = matched_hypotheses[0] if matched_hypotheses else RootCauseHypothesis(
            hypothesis_id=f"hyp-{uuid.uuid4().hex[:8]}",
            cause_name="Unknown Uncategorized Anomaly",
            confidence_score=0.2,
            matching_error_pattern="none",
            recommended_action="Conduct manual log inspection and review system telemetry.",
            effort=RemediationEffort.MANUAL_REFACTOR,
            automated_fix_available=False,
        )
        secondaries = matched_hypotheses[1:] if len(matched_hypotheses) > 1 else []

        report_id = f"diag-{uuid.uuid4().hex[:12]}"
        report = DiagnosticReport(
            report_id=report_id,
            run_id=run_id,
            error_signature=error_message[:200],
            primary_root_cause=primary,
            secondary_hypotheses=secondaries,
            generated_at=self._now_iso(),
        )
        self._reports[report_id] = report
        return report

    def add_user_feedback(self, report_id: str, is_accurate: bool) -> bool:
        """Provide validation feedback to adjust pattern confidence weights."""
        if report_id not in self._reports:
            raise ValueError(f"Diagnostic report {report_id} not found")

        report = self._reports[report_id]
        if not report.primary_root_cause:
            return False

        target_pattern = report.primary_root_cause.matching_error_pattern
        for p in self._patterns:
            if p["regex"].pattern == target_pattern:
                if is_accurate:
                    p["confirmed_count"] += 1
                    p["confidence"] = min(0.99, p["confidence"] + 0.02)
                else:
                    p["confidence"] = max(0.2, p["confidence"] - 0.05)
                return True
        return False

    def get_report(self, report_id: str) -> Optional[DiagnosticReport]:
        """Retrieve diagnostic report by ID."""
        return self._reports.get(report_id)

    def list_reports(self, run_id: Optional[str] = None) -> List[DiagnosticReport]:
        """List diagnostic reports optionally filtered by run ID."""
        if run_id is not None:
            return [r for r in self._reports.values() if r.run_id == run_id]
        return list(self._reports.values())

    def get_diagnostic_insights(self) -> Dict[str, Any]:
        """Generate high-level diagnostic intelligence statistics."""
        total = len(self._reports)
        auto_fix_ready = sum(
            1 for r in self._reports.values()
            if r.primary_root_cause and r.primary_root_cause.automated_fix_available
        )
        total_conf = sum(
            r.primary_root_cause.confidence_score
            for r in self._reports.values()
            if r.primary_root_cause
        )

        cause_counts: Dict[str, int] = {}
        for r in self._reports.values():
            if r.primary_root_cause:
                c = r.primary_root_cause.cause_name
                cause_counts[c] = cause_counts.get(c, 0) + 1

        return {
            "total_diagnosed_reports": total,
            "auto_fixable_count": auto_fix_ready,
            "auto_fix_rate_pct": round((auto_fix_ready / total * 100.0), 2) if total > 0 else 0.0,
            "avg_confidence_score": round(total_conf / total, 3) if total > 0 else 0.0,
            "top_root_causes": cause_counts,
            "active_pattern_rules": len(self._patterns),
        }

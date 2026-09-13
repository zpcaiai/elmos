"""Supply Chain Compliance Factory Engine (Batch 40 - Skill 1397).

Orchestrates multi-standard supply chain compliance evaluation across SLSA Level 3,
NIST SP 800-218 (SSDF), CIS Benchmarks, OpenSSF Scorecard, and SOC2 Type 2.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    ComplianceEvaluationReport,
    ComplianceStandard,
    PolicyEnforcementMode,
    SupplyChainComplianceRule,
)


SEVERITY_ORDER = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


class SupplyChainComplianceFactoryEngine:
    """Industrial engine for software supply chain compliance validation (B40)."""

    def __init__(self):
        self._rules: Dict[str, SupplyChainComplianceRule] = {}
        self._reports: Dict[str, ComplianceEvaluationReport] = {}
        self._audit_log: List[Dict[str, Any]] = []
        self._seed_default_rules()

    def _seed_default_rules(self) -> None:
        """Initialize standard baseline rules for each supported compliance standard."""
        default_rules = [
            SupplyChainComplianceRule(
                rule_id="rule-slsa-provenance",
                standard=ComplianceStandard.SLSA_LEVEL_3,
                name="SLSA Provenance Attestation Required",
                description="Must possess non-forgeable build provenance attestation",
                enforcement_mode=PolicyEnforcementMode.BLOCK,
                required_attestations=["slsa_provenance", "in_toto_statement"],
                max_cve_severity="medium",
                enabled=True,
            ),
            SupplyChainComplianceRule(
                rule_id="rule-slsa-hermetic",
                standard=ComplianceStandard.SLSA_LEVEL_3,
                name="Hermetic Isolated Builder Required",
                description="Artifacts must be built in an isolated hermetic environment",
                enforcement_mode=PolicyEnforcementMode.BLOCK,
                required_attestations=["hermetic_build_receipt"],
                max_cve_severity="medium",
                enabled=True,
            ),
            SupplyChainComplianceRule(
                rule_id="rule-nist-sbom",
                standard=ComplianceStandard.NIST_SP_800_218,
                name="CycloneDX/SPDX SBOM Component Attestation",
                description="NIST SSDF requires full SBOM transparency for dependencies",
                enforcement_mode=PolicyEnforcementMode.BLOCK,
                required_attestations=["sbom_cyclonedx"],
                max_cve_severity="high",
                enabled=True,
            ),
            SupplyChainComplianceRule(
                rule_id="rule-openssf-signed",
                standard=ComplianceStandard.OPENSSF_SCORECARD,
                name="Cryptographic Signature Verification",
                description="Release artifacts must have valid cryptographic signatures",
                enforcement_mode=PolicyEnforcementMode.BLOCK,
                required_attestations=["cosign_signature"],
                max_cve_severity="low",
                enabled=True,
            ),
            SupplyChainComplianceRule(
                rule_id="rule-soc2-audit",
                standard=ComplianceStandard.SOC2_TYPE2,
                name="Immutable Audit Trail Attestation",
                description="All promotion steps must maintain tamper-evident audit receipts",
                enforcement_mode=PolicyEnforcementMode.WARN,
                required_attestations=["merkle_audit_receipt"],
                max_cve_severity="critical",
                enabled=True,
            ),
        ]
        for rule in default_rules:
            self._rules[rule.rule_id] = rule

    def register_rule(self, rule: SupplyChainComplianceRule) -> str:
        """Register a new or custom supply chain compliance rule."""
        self._rules[rule.rule_id] = rule
        self._record_audit("rule_registered", rule.rule_id, {"standard": rule.standard.value})
        return rule.rule_id

    def get_rules(
        self,
        standard: Optional[ComplianceStandard] = None,
        enabled_only: bool = True,
    ) -> List[SupplyChainComplianceRule]:
        """Query rules optionally filtered by compliance standard."""
        res = list(self._rules.values())
        if standard:
            res = [r for r in res if r.standard == standard]
        if enabled_only:
            res = [r for r in res if r.enabled]
        return res

    def evaluate_artifact(
        self,
        artifact_id: str,
        standard: ComplianceStandard,
        present_attestations: List[str],
        max_detected_cve: str = "none",
    ) -> ComplianceEvaluationReport:
        """Evaluate an artifact's attestations and vulnerability posture against standard rules."""
        rules = self.get_rules(standard=standard, enabled_only=True)
        report_id = f"rpt-{uuid.uuid4().hex[:8]}"

        if not rules:
            report = ComplianceEvaluationReport(
                report_id=report_id,
                artifact_id=artifact_id,
                target_standard=standard,
                passed=True,
                score_pct=100.0,
                satisfied_rules=[],
                violated_rules=[],
                remediations=[],
                evaluated_at=datetime.now(timezone.utc).isoformat(),
            )
            self._reports[report_id] = report
            return report

        satisfied: List[str] = []
        violated: List[str] = []
        remediations: List[str] = []
        has_blocking_violation = False

        artifact_cve_level = SEVERITY_ORDER.get(max_detected_cve.lower(), 0)

        for rule in rules:
            rule_failed = False
            # Check attestations
            missing_attestations = [att for att in rule.required_attestations if att not in present_attestations]
            if missing_attestations:
                rule_failed = True
                remediations.append(
                    f"Generate missing attestations for rule '{rule.name}': {', '.join(missing_attestations)}"
                )

            # Check CVE severity threshold
            max_allowed = SEVERITY_ORDER.get(rule.max_cve_severity.lower(), 2)
            if artifact_cve_level > max_allowed:
                rule_failed = True
                remediations.append(
                    f"Remediate CVEs in artifact: detected severity '{max_detected_cve}' exceeds max allowed '{rule.max_cve_severity}' for rule '{rule.name}'"
                )

            if rule_failed:
                violated.append(rule.rule_id)
                if rule.enforcement_mode in (PolicyEnforcementMode.BLOCK, PolicyEnforcementMode.STRICT):
                    has_blocking_violation = True
            else:
                satisfied.append(rule.rule_id)

        score_pct = round((len(satisfied) / len(rules)) * 100.0, 2)
        passed = not has_blocking_violation

        report = ComplianceEvaluationReport(
            report_id=report_id,
            artifact_id=artifact_id,
            target_standard=standard,
            passed=passed,
            score_pct=score_pct,
            satisfied_rules=satisfied,
            violated_rules=violated,
            remediations=remediations,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

        self._reports[report_id] = report
        self._record_audit("artifact_evaluated", artifact_id, {
            "standard": standard.value,
            "passed": passed,
            "score_pct": score_pct,
        })
        return report

    def get_report(self, report_id: str) -> Optional[ComplianceEvaluationReport]:
        """Fetch an evaluation report."""
        return self._reports.get(report_id)

    def get_compliance_dashboard(self) -> Dict[str, Any]:
        """Generate overview of compliance status across evaluated artifacts."""
        total_evals = len(self._reports)
        passed_evals = sum(1 for r in self._reports.values() if r.passed)
        avg_score = (
            sum(r.score_pct for r in self._reports.values()) / total_evals
            if total_evals > 0 else 100.0
        )

        by_standard: Dict[str, Dict[str, Any]] = {}
        for r in self._reports.values():
            s_name = r.target_standard.value
            entry = by_standard.setdefault(s_name, {"total": 0, "passed": 0})
            entry["total"] += 1
            if r.passed:
                entry["passed"] += 1

        return {
            "total_evaluations": total_evals,
            "passed_evaluations": passed_evals,
            "overall_pass_rate_pct": round((passed_evals / total_evals) * 100.0, 2) if total_evals > 0 else 100.0,
            "average_score_pct": round(avg_score, 2),
            "by_standard": by_standard,
            "total_configured_rules": len(self._rules),
        }

    def _record_audit(self, action: str, target: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)

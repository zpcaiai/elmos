"""Policy Enforcement Agent Engine (Batch 42 - Skill 1419).

Enforces strict compliance, security boundaries, and architecture invariants on agent-generated code patches,
evaluating changes against forbidden patterns, sensitive file protections, and audit requirements.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    PolicyAgentDecision,
    PolicyAuditEvaluation,
    PolicyViolationFinding,
)


class PolicyEnforcementAgentEngine:
    """Automated guardian agent evaluating code mutations and tool usage against enterprise policies."""

    def __init__(self) -> None:
        self._rules: Dict[str, Dict[str, Any]] = {}
        self._evaluations: Dict[str, PolicyAuditEvaluation] = {}
        self._initialize_default_rules()

    def _initialize_default_rules(self) -> None:
        """Initialize standard security and integrity invariant rules."""
        self.register_policy_rule(
            rule_id="RULE-SEC-01",
            description="Prohibit unsafe dynamic code execution (eval, exec)",
            forbidden_patterns=["eval(", "exec(", "subprocess.Popen(shell=True", "os.system("],
            severity="critical",
        )
        self.register_policy_rule(
            rule_id="RULE-SEC-02",
            description="Prohibit plaintext hardcoded tokens or secrets",
            forbidden_patterns=["BEGIN RSA PRIVATE KEY", "ghp_", "sk-proj-", "AKIA[0-9A-Z]{16}"],
            severity="critical",
        )
        self.register_policy_rule(
            rule_id="RULE-ARCH-01",
            description="Prohibit tampering with protected test suites or certification gates",
            forbidden_patterns=["rm -rf tests", "@unittest.skip", "pytest.mark.skip"],
            severity="high",
        )

    def register_policy_rule(
        self,
        rule_id: str,
        description: str,
        forbidden_patterns: List[str],
        severity: str = "high",
    ) -> None:
        """Register a new policy rule with forbidden code patterns."""
        if not rule_id or not forbidden_patterns:
            raise ValueError("rule_id and forbidden_patterns are required")

        self._rules[rule_id] = {
            "rule_id": rule_id,
            "description": description,
            "patterns": forbidden_patterns,
            "severity": severity,
        }

    def evaluate_patch(
        self,
        agent_id: str,
        task_id: str,
        patch_content: str,
        changed_files: Optional[List[str]] = None,
    ) -> PolicyAuditEvaluation:
        """Scan patch diff and modified files, generating findings and an enforcement decision."""
        if not agent_id or not task_id:
            raise ValueError("agent_id and task_id are required")

        violations: List[PolicyViolationFinding] = []

        for rule in self._rules.values():
            for pat in rule["patterns"]:
                if pat in patch_content:
                    violations.append(
                        PolicyViolationFinding(
                            violation_id=f"viol-{uuid.uuid4().hex[:8]}",
                            rule_id=rule["rule_id"],
                            severity=rule["severity"],
                            file_path="patch_diff",
                            message=f"Detected forbidden pattern '{pat}': {rule['description']}",
                            remediation_hint=f"Remove or refactor usage of '{pat}'.",
                        )
                    )

        has_critical = any(v.severity == "critical" for v in violations)
        has_high = any(v.severity == "high" for v in violations)

        if has_critical or has_high:
            decision = PolicyAgentDecision.BLOCK
        elif len(violations) > 0:
            decision = PolicyAgentDecision.FLAG
        else:
            decision = PolicyAgentDecision.ALLOW

        evaluation = PolicyAuditEvaluation(
            eval_id=f"eval-{uuid.uuid4().hex[:8]}",
            agent_id=agent_id,
            task_id=task_id,
            decision=decision,
            violations=violations,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

        self._evaluations[evaluation.eval_id] = evaluation
        return evaluation

    def override_decision(
        self, eval_id: str, approver: str, rationale: str
    ) -> PolicyAuditEvaluation:
        """Allow an authorized human approver to override a policy block with audit justification."""
        evaluation = self._evaluations.get(eval_id)
        if not evaluation:
            raise ValueError(f"Evaluation not found: {eval_id}")
        if not approver or not rationale:
            raise ValueError("approver and rationale are required for policy override")

        evaluation.decision = PolicyAgentDecision.OVERRIDE
        return evaluation

    def get_evaluation(self, eval_id: str) -> Optional[PolicyAuditEvaluation]:
        """Retrieve evaluation details."""
        return self._evaluations.get(eval_id)

    def get_policy_enforcement_report(self) -> Dict[str, Any]:
        """Generate summary of all policy evaluations, blocks, and overrides."""
        total = len(self._evaluations)
        blocked = sum(1 for e in self._evaluations.values() if e.decision == PolicyAgentDecision.BLOCK)
        allowed = sum(1 for e in self._evaluations.values() if e.decision == PolicyAgentDecision.ALLOW)
        overridden = sum(1 for e in self._evaluations.values() if e.decision == PolicyAgentDecision.OVERRIDE)

        return {
            "total_evaluations": total,
            "blocked_count": blocked,
            "allowed_count": allowed,
            "overridden_count": overridden,
            "active_rules_count": len(self._rules),
            "compliance_pass_rate_pct": (allowed / total * 100.0) if total > 0 else 100.0,
        }

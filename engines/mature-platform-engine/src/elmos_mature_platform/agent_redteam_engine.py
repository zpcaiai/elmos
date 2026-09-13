"""Agent Red Team & Governance Engine."""

import time
import json
import logging
from typing import Any, Callable, Dict, List, Optional
from collections import Counter

from elmos_mature_platform.types import (
    AgentAutonomyLevel,
    AgentTestCategory,
    AgentTestVerdict,
    RedTeamScenario,
    RedTeamResult,
    AgentShadowResult,
    AgentConsensusResult,
    SeverityLevel
)

class AgentRedTeamEngine:
    def __init__(self):
        self.scenarios: Dict[str, RedTeamScenario] = {}
        self.results: List[RedTeamResult] = []

    def register_scenario(self, scenario: RedTeamScenario) -> None:
        """Register an attack scenario."""
        self.scenarios[scenario.scenario_id] = scenario

    def execute_redteam_scenario(self, scenario_id: str, agent_response_fn: Callable) -> RedTeamResult:
        """Run scenario against agent defense function."""
        if scenario_id not in self.scenarios:
            raise ValueError(f"Scenario {scenario_id} not registered")
        
        scenario = self.scenarios[scenario_id]
        
        start_time = time.time()
        try:
            # We assume agent_response_fn takes the payload and scenario category
            response = agent_response_fn(scenario.attack_payload, scenario.category)
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Simplified verdict logic: the agent function returns whether it defended successfully
            # In a real system, the response would be analyzed, but for the scope of this implementation, 
            # we'll expect the agent function to return a dict containing boolean flags or verdict.
            
            is_defended = response.get("defended", False)
            verdict = AgentTestVerdict.DEFENDED if is_defended else AgentTestVerdict.VULNERABLE
            
            result = RedTeamResult(
                scenario_id=scenario_id,
                verdict=verdict,
                defense_triggered=is_defended,
                attack_blocked=is_defended,
                response_contained=is_defended,
                details=response.get("details", ""),
                elapsed_ms=elapsed_ms
            )
            self.results.append(result)
            return result
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            result = RedTeamResult(
                scenario_id=scenario_id,
                verdict=AgentTestVerdict.INCONCLUSIVE,
                defense_triggered=False,
                attack_blocked=False,
                response_contained=False,
                details=f"Error executing scenario: {str(e)}",
                elapsed_ms=elapsed_ms
            )
            self.results.append(result)
            return result

    def check_prompt_injection(self, input_text: str) -> Dict[str, Any]:
        """Detect injection patterns (ignore previous, system prompt override, etc.)."""
        lower_input = input_text.lower()
        injection_patterns = [
            "ignore previous instructions",
            "ignore previous",
            "system: override",
            "system:",
            "disregard previous",
            "forget everything"
        ]
        
        for pattern in injection_patterns:
            if pattern in lower_input:
                return {
                    "defended": True,
                    "details": f"Prompt injection detected: matched pattern '{pattern}'"
                }
                
        return {
            "defended": False,
            "details": "No prompt injection detected."
        }

    def check_tool_abuse(self, tool_name: str, tool_args: Dict[str, Any], allowed_tools: List[str], tool_budgets: Dict[str, int]) -> Dict[str, Any]:
        """Verify tool is allowed and within budget."""
        if tool_name not in allowed_tools:
            return {
                "defended": True,
                "details": f"Tool abuse blocked: '{tool_name}' is not in allowed tools."
            }
            
        if tool_name in tool_budgets:
            budget = tool_budgets[tool_name]
            cost = tool_args.get("cost", 1)  # Default cost is 1 if not specified
            if cost > budget:
                return {
                    "defended": True,
                    "details": f"Tool abuse blocked: budget exhaustion for '{tool_name}'. Cost {cost} exceeds budget {budget}."
                }
                
        return {
            "defended": False,
            "details": "Tool usage allowed."
        }

    def check_privilege_escalation(self, requested_role: str, current_role: str, role_hierarchy: Dict[str, int]) -> Dict[str, Any]:
        """Detect unauthorized role elevation."""
        if current_role not in role_hierarchy:
            return {"defended": True, "details": "Current role unrecognized."}
        if requested_role not in role_hierarchy:
            return {"defended": True, "details": "Requested role unrecognized."}
            
        current_level = role_hierarchy[current_role]
        requested_level = role_hierarchy[requested_role]
        
        if requested_level > current_level:
            return {
                "defended": True,
                "details": f"Privilege escalation blocked: {current_role} cannot escalate to {requested_role}."
            }
            
        return {
            "defended": False,
            "details": "Role elevation check passed."
        }

    def check_data_exfiltration(self, output_text: str, sensitive_patterns: List[str]) -> Dict[str, Any]:
        """Scan output for leaked secrets/PII."""
        for pattern in sensitive_patterns:
            if pattern in output_text:
                return {
                    "defended": True,
                    "details": f"Data exfiltration blocked: matched sensitive pattern '{pattern}'."
                }
                
        return {
            "defended": False,
            "details": "No data exfiltration detected."
        }

    def check_runaway_loop(self, iteration_count: int, max_iterations: int, elapsed_seconds: float, max_seconds: float) -> Dict[str, Any]:
        """Detect infinite loops/economic DoS."""
        if iteration_count > max_iterations:
            return {
                "defended": True,
                "details": f"Runaway loop blocked: {iteration_count} iterations exceeds max {max_iterations}."
            }
        
        if elapsed_seconds > max_seconds:
            return {
                "defended": True,
                "details": f"Runaway loop blocked: {elapsed_seconds}s exceeds max {max_seconds}s."
            }
            
        return {
            "defended": False,
            "details": "Within loop constraints."
        }

    def execute_shadow_comparison(self, agent_id: str, input_data: Dict[str, Any], prod_fn: Callable, shadow_fn: Callable) -> AgentShadowResult:
        """Compare production vs shadow agent outputs."""
        prod_output = prod_fn(input_data)
        shadow_output = shadow_fn(input_data)
        
        divergent_fields = []
        
        # Simple top-level dict comparison
        all_keys = set(prod_output.keys()).union(set(shadow_output.keys()))
        for key in all_keys:
            if prod_output.get(key) != shadow_output.get(key):
                divergent_fields.append(key)
                
        divergence_score = len(divergent_fields) / len(all_keys) if all_keys else 0.0
        
        safe_to_promote = divergence_score == 0.0
        
        return AgentShadowResult(
            shadow_id=f"shadow_{agent_id}_{int(time.time())}",
            agent_id=agent_id,
            production_output=prod_output,
            shadow_output=shadow_output,
            divergence_score=divergence_score,
            divergent_fields=divergent_fields,
            safe_to_promote=safe_to_promote
        )

    def execute_consensus(self, decision_id: str, agent_votes: Dict[str, str], quorum: float) -> AgentConsensusResult:
        """Multi-agent consensus with quorum requirement."""
        if not agent_votes:
            return AgentConsensusResult(
                decision_id=decision_id,
                agent_votes=agent_votes,
                consensus_reached=False,
                requires_human_arbitration=True
            )
            
        vote_counts = Counter(agent_votes.values())
        total_votes = len(agent_votes)
        
        winning_decision, max_votes = vote_counts.most_common(1)[0]
        agreement_ratio = max_votes / total_votes
        
        consensus_reached = agreement_ratio >= quorum
        
        return AgentConsensusResult(
            decision_id=decision_id,
            agent_votes=agent_votes,
            consensus_reached=consensus_reached,
            winning_decision=winning_decision if consensus_reached else "",
            agreement_ratio=agreement_ratio,
            requires_human_arbitration=not consensus_reached
        )

    def get_redteam_report(self) -> Dict[str, Any]:
        """Summary: total scenarios, defended, vulnerable, partial."""
        total = len(self.scenarios)
        defended = sum(1 for r in self.results if r.verdict == AgentTestVerdict.DEFENDED)
        vulnerable = sum(1 for r in self.results if r.verdict == AgentTestVerdict.VULNERABLE)
        partial = sum(1 for r in self.results if r.verdict == AgentTestVerdict.PARTIAL)
        inconclusive = sum(1 for r in self.results if r.verdict == AgentTestVerdict.INCONCLUSIVE)
        
        return {
            "total_scenarios": total,
            "executed_scenarios": len(self.results),
            "defended": defended,
            "vulnerable": vulnerable,
            "partial": partial,
            "inconclusive": inconclusive
        }

    def get_vulnerability_summary(self) -> List[Dict[str, Any]]:
        """All VULNERABLE results with details."""
        vulnerabilities = []
        for r in self.results:
            if r.verdict == AgentTestVerdict.VULNERABLE:
                vulnerabilities.append({
                    "scenario_id": r.scenario_id,
                    "details": r.details,
                    "elapsed_ms": r.elapsed_ms
                })
        return vulnerabilities

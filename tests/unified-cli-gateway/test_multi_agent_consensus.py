"""Unit & integration tests for Multi-Agent Consensus & Red-Team Arbitrator."""

from __future__ import annotations

import io
import json
import sys
import unittest

from elmos_autonomous_qa.multi_agent_consensus import (
    AgentProfile,
    AgentProposal,
    MultiAgentConsensusArbitrator,
    get_consensus_arbitrator,
    run_multi_agent_consensus,
)
from elmos_cli.dispatcher import main


class MultiAgentConsensusTests(unittest.TestCase):
    """Test multi-agent candidate generation, voting, and formal arbitration."""

    def setUp(self) -> None:
        self.arbitrator = get_consensus_arbitrator()

    def test_candidate_generation(self) -> None:
        proposals = self.arbitrator.generate_candidate_proposals(
            task_name="LedgerTransaction",
            source_code="public class LedgerTransaction { public double amount; }",
            target_lang="csharp",
        )
        self.assertEqual(len(proposals), 3)
        profiles = [p.profile for p in proposals]
        self.assertIn(AgentProfile.SAFETY_FIRST, profiles)
        self.assertIn(AgentProfile.PERFORMANCE_OPTIMIZED, profiles)
        self.assertIn(AgentProfile.LEGACY_CONSERVATIVE, profiles)

    def test_arbitrate_with_unanimous_safety_bounds(self) -> None:
        res = self.arbitrator.arbitrate(
            task_name="LedgerTransaction",
            source_code="public class LedgerTransaction { public double amount; }",
            formal_formula="amount >= 0 ==> amount_target >= 0",
        )
        self.assertIn("proposals_evaluated", res)
        self.assertEqual(len(res["proposals_evaluated"]), 3)
        self.assertGreaterEqual(res["average_confidence"], 0.90)
        self.assertIn("winning_proposal", res)
        self.assertEqual(res["winning_proposal"]["profile"], "SAFETY_FIRST")
        self.assertEqual(res["formal_solver_decision"]["verdict"], "PROVED_UNANIMOUS_UNDER_SAFETY_BOUNDS")
        self.assertEqual(len(res["merkle_receipt"]), 64)

    def test_cli_qa_consensus_command(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = main([
                "qa",
                "consensus",
                "--task-name", "PaymentLedger",
                "--code", "public class PaymentLedger { public double total; }",
                "--json",
            ])
            self.assertEqual(code, 0)
            data = json.loads(sys.stdout.getvalue())
            self.assertEqual(data["task_name"], "PaymentLedger")
            self.assertIn("merkle_receipt", data)
            self.assertIn("winning_proposal", data)
        finally:
            sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()

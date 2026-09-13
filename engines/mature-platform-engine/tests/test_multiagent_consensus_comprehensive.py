import unittest
from datetime import datetime

from elmos_mature_platform.types import (
    ConsensusAgent,
    ConsensusProposal,
    AgentVote,
    ConsensusStrategy,
    VoteValue,
    ProposalStatus,
)
from elmos_mature_platform.multiagent_consensus_engine import MultiagentConsensusEngine

class TestMultiagentConsensusEngine(unittest.TestCase):
    def setUp(self):
        self.engine = MultiagentConsensusEngine()
        self.agent1 = ConsensusAgent(agent_id="a1", name="Agent 1", weight=2.0)
        self.agent2 = ConsensusAgent(agent_id="a2", name="Agent 2", weight=1.0)
        self.agent3 = ConsensusAgent(agent_id="a3", name="Agent 3", weight=1.0)
        self.engine.register_agent(self.agent1)
        self.engine.register_agent(self.agent2)
        self.engine.register_agent(self.agent3)

    def test_register_agent(self):
        self.assertIn("a1", self.engine.agents)
        
    def test_register_agent_invalid_trust(self):
        with self.assertRaises(ValueError):
            self.engine.register_agent(ConsensusAgent("a4", "A4", trust_score=1.5))

    def test_create_proposal(self):
        prop = ConsensusProposal(
            proposal_id="p1", topic="T", description="D", 
            strategy=ConsensusStrategy.MAJORITY, proposer_id="a1"
        )
        self.engine.create_proposal(prop)
        self.assertIn("p1", self.engine.proposals)

    def test_create_proposal_duplicate(self):
        prop = ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1")
        self.engine.create_proposal(prop)
        with self.assertRaises(ValueError):
            self.engine.create_proposal(prop)
            
    def test_create_proposal_invalid_proposer(self):
        prop = ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "unknown")
        with self.assertRaises(ValueError):
            self.engine.create_proposal(prop)
            
    def test_create_proposal_arbiter_missing_arbiter(self):
        prop = ConsensusProposal("p1", "T", "D", ConsensusStrategy.ARBITER, "a1")
        with self.assertRaises(ValueError):
            self.engine.create_proposal(prop)

    def test_cast_vote(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1"))
        vote = AgentVote("v1", "p1", "a1", VoteValue.APPROVE)
        self.engine.cast_vote(vote)
        self.assertEqual(len(self.engine.get_votes("p1")), 1)

    def test_cast_vote_invalid_proposal(self):
        vote = AgentVote("v1", "unknown", "a1", VoteValue.APPROVE)
        with self.assertRaises(ValueError):
            self.engine.cast_vote(vote)
            
    def test_cast_vote_closed_proposal(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1"))
        self.engine.proposals["p1"].status = ProposalStatus.APPROVED
        vote = AgentVote("v1", "p1", "a1", VoteValue.APPROVE)
        with self.assertRaises(ValueError):
            self.engine.cast_vote(vote)
            
    def test_cast_vote_invalid_agent(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1"))
        vote = AgentVote("v1", "p1", "unknown", VoteValue.APPROVE)
        with self.assertRaises(ValueError):
            self.engine.cast_vote(vote)
            
    def test_cast_vote_duplicate(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1"))
        vote = AgentVote("v1", "p1", "a1", VoteValue.APPROVE)
        self.engine.cast_vote(vote)
        with self.assertRaises(ValueError):
            self.engine.cast_vote(AgentVote("v2", "p1", "a1", VoteValue.REJECT))

    def test_resolve_majority_approve(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1"))
        self.engine.cast_vote(AgentVote("v1", "p1", "a1", VoteValue.APPROVE))
        self.engine.cast_vote(AgentVote("v2", "p1", "a2", VoteValue.APPROVE))
        self.engine.cast_vote(AgentVote("v3", "p1", "a3", VoteValue.REJECT))
        result = self.engine.resolve_proposal("p1")
        self.assertEqual(result.outcome, VoteValue.APPROVE)
        self.assertEqual(self.engine.proposals["p1"].status, ProposalStatus.APPROVED)

    def test_resolve_majority_reject(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1"))
        self.engine.cast_vote(AgentVote("v1", "p1", "a1", VoteValue.REJECT))
        self.engine.cast_vote(AgentVote("v2", "p1", "a2", VoteValue.REJECT))
        result = self.engine.resolve_proposal("p1")
        self.assertEqual(result.outcome, VoteValue.REJECT)
        
    def test_resolve_unanimous_approve(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.UNANIMOUS, "a1"))
        self.engine.cast_vote(AgentVote("v1", "p1", "a1", VoteValue.APPROVE))
        self.engine.cast_vote(AgentVote("v2", "p1", "a2", VoteValue.APPROVE))
        result = self.engine.resolve_proposal("p1")
        self.assertEqual(result.outcome, VoteValue.APPROVE)

    def test_resolve_unanimous_reject(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.UNANIMOUS, "a1"))
        self.engine.cast_vote(AgentVote("v1", "p1", "a1", VoteValue.APPROVE))
        self.engine.cast_vote(AgentVote("v2", "p1", "a2", VoteValue.REJECT))
        result = self.engine.resolve_proposal("p1")
        self.assertEqual(result.outcome, VoteValue.REJECT)

    def test_resolve_weighted_approve(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.WEIGHTED, "a1"))
        self.engine.cast_vote(AgentVote("v1", "p1", "a1", VoteValue.APPROVE)) # weight 2
        self.engine.cast_vote(AgentVote("v2", "p1", "a2", VoteValue.REJECT))  # weight 1
        self.engine.cast_vote(AgentVote("v3", "p1", "a3", VoteValue.REJECT))  # weight 1
        # Sums: approve=2, reject=2 => not strictly greater
        result = self.engine.resolve_proposal("p1")
        self.assertEqual(result.outcome, VoteValue.REJECT)

    def test_resolve_weighted_approve_clear(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.WEIGHTED, "a1"))
        self.engine.agents["a1"].weight = 3.0
        self.engine.cast_vote(AgentVote("v1", "p1", "a1", VoteValue.APPROVE))
        self.engine.cast_vote(AgentVote("v2", "p1", "a2", VoteValue.REJECT))
        self.engine.cast_vote(AgentVote("v3", "p1", "a3", VoteValue.REJECT))
        result = self.engine.resolve_proposal("p1")
        self.assertEqual(result.outcome, VoteValue.APPROVE)

    def test_resolve_quorum_met(self):
        prop = ConsensusProposal("p1", "T", "D", ConsensusStrategy.QUORUM, "a1", quorum_threshold=0.6)
        self.engine.create_proposal(prop)
        self.engine.cast_vote(AgentVote("v1", "p1", "a1", VoteValue.APPROVE))
        self.engine.cast_vote(AgentVote("v2", "p1", "a2", VoteValue.APPROVE))
        # 2 out of 3 = 0.66 > 0.6
        result = self.engine.resolve_proposal("p1")
        self.assertEqual(result.outcome, VoteValue.APPROVE)

    def test_resolve_quorum_not_met(self):
        prop = ConsensusProposal("p1", "T", "D", ConsensusStrategy.QUORUM, "a1", quorum_threshold=0.6)
        self.engine.create_proposal(prop)
        self.engine.cast_vote(AgentVote("v1", "p1", "a1", VoteValue.APPROVE))
        # 1 out of 3 = 0.33 < 0.6
        result = self.engine.resolve_proposal("p1")
        self.assertEqual(result.outcome, VoteValue.REJECT)

    def test_resolve_invalid_proposal(self):
        with self.assertRaises(ValueError):
            self.engine.resolve_proposal("unknown")
            
    def test_resolve_already_resolved(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1"))
        self.engine.proposals["p1"].status = ProposalStatus.APPROVED
        with self.assertRaises(ValueError):
            self.engine.resolve_proposal("p1")

    def test_arbitrate(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.ARBITER, "a1", arbiter_id="a2"))
        result = self.engine.arbitrate("p1", "a2", VoteValue.APPROVE, "reason")
        self.assertEqual(result.outcome, VoteValue.APPROVE)
        self.assertEqual(self.engine.proposals["p1"].status, ProposalStatus.ARBITRATED)

    def test_arbitrate_wrong_strategy(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1"))
        with self.assertRaises(ValueError):
            self.engine.arbitrate("p1", "a2", VoteValue.APPROVE, "reason")

    def test_resolve_arbiter_strategy(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.ARBITER, "a1", arbiter_id="a2"))
        with self.assertRaises(ValueError):
            self.engine.resolve_proposal("p1")
            
    def test_arbitrate_wrong_arbiter(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.ARBITER, "a1", arbiter_id="a2"))
        with self.assertRaises(PermissionError):
            self.engine.arbitrate("p1", "a3", VoteValue.APPROVE, "reason")

    def test_get_proposal(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1"))
        prop = self.engine.get_proposal("p1")
        self.assertEqual(prop.proposal_id, "p1")
        
    def test_get_proposal_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_proposal("unknown")

    def test_get_votes(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1"))
        self.engine.cast_vote(AgentVote("v1", "p1", "a1", VoteValue.APPROVE))
        votes = self.engine.get_votes("p1")
        self.assertEqual(len(votes), 1)

    def test_get_votes_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_votes("unknown")

    def test_update_trust_scores(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1"))
        self.engine.cast_vote(AgentVote("v1", "p1", "a1", VoteValue.APPROVE))
        self.engine.cast_vote(AgentVote("v2", "p1", "a2", VoteValue.REJECT))
        self.engine.update_trust_scores("p1", VoteValue.APPROVE)
        self.assertEqual(self.engine.agents["a1"].trust_score, 1.0) # Cap at 1.0
        self.assertLess(self.engine.agents["a2"].trust_score, 1.0)
        
    def test_update_trust_scores_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.update_trust_scores("unknown", VoteValue.APPROVE)

    def test_get_agent_stats(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1"))
        self.engine.cast_vote(AgentVote("v1", "p1", "a1", VoteValue.APPROVE))
        self.engine.update_trust_scores("p1", VoteValue.APPROVE)
        stats = self.engine.get_agent_stats("a1")
        self.assertEqual(stats["vote_count"], 1)
        self.assertEqual(stats["correct_predictions"], 1)
        self.assertEqual(stats["accuracy"], 1.0)
        
    def test_get_agent_stats_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_agent_stats("unknown")

    def test_expire_proposals(self):
        prop = ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1", deadline="2020-01-01")
        self.engine.create_proposal(prop)
        expired = self.engine.expire_proposals("2021-01-01")
        self.assertIn("p1", expired)
        self.assertEqual(self.engine.proposals["p1"].status, ProposalStatus.EXPIRED)

    def test_get_consensus_report(self):
        self.engine.create_proposal(ConsensusProposal("p1", "T", "D", ConsensusStrategy.MAJORITY, "a1"))
        report = self.engine.get_consensus_report()
        self.assertEqual(report["total_proposals"], 1)
        self.assertEqual(report["total_agents"], 3)
        self.assertEqual(report["proposals_by_status"]["open"], 1)
        self.assertGreater(report["average_trust_score"], 0.0)

if __name__ == "__main__":
    unittest.main()

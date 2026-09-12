from typing import List, Dict, Optional
from datetime import datetime
from .types import (
    ConsensusAgent,
    ConsensusProposal,
    AgentVote,
    ConsensusResult,
    ConsensusStrategy,
    VoteValue,
    ProposalStatus,
)

class MultiagentConsensusEngine:
    def __init__(self):
        self.agents: Dict[str, ConsensusAgent] = {}
        self.proposals: Dict[str, ConsensusProposal] = {}
        self.votes: Dict[str, List[AgentVote]] = {}
    
    def register_agent(self, agent: ConsensusAgent) -> None:
        """Register a voting agent."""
        if agent.trust_score < 0.0 or agent.trust_score > 1.0:
            raise ValueError("Trust score must be between 0 and 1.")
        self.agents[agent.agent_id] = agent

    def create_proposal(self, proposal: ConsensusProposal) -> str:
        """Create a proposal for voting."""
        if proposal.proposal_id in self.proposals:
            raise ValueError(f"Proposal {proposal.proposal_id} already exists.")
        if proposal.proposer_id not in self.agents:
            raise ValueError(f"Proposer {proposal.proposer_id} is not a registered agent.")
        if proposal.strategy == ConsensusStrategy.ARBITER and not proposal.arbiter_id:
            raise ValueError("Arbiter ID required for ARBITER strategy.")
            
        self.proposals[proposal.proposal_id] = proposal
        self.votes[proposal.proposal_id] = []
        return proposal.proposal_id

    def cast_vote(self, vote: AgentVote) -> AgentVote:
        """Cast a vote (no double-voting)."""
        if vote.proposal_id not in self.proposals:
            raise ValueError(f"Proposal {vote.proposal_id} not found.")
        
        proposal = self.proposals[vote.proposal_id]
        if proposal.status != ProposalStatus.OPEN:
            raise ValueError(f"Proposal {vote.proposal_id} is not open for voting.")
            
        if vote.agent_id not in self.agents:
            raise ValueError(f"Agent {vote.agent_id} is not registered.")
            
        existing_votes = self.votes[vote.proposal_id]
        for v in existing_votes:
            if v.agent_id == vote.agent_id:
                raise ValueError(f"Agent {vote.agent_id} has already voted on proposal {vote.proposal_id}.")
                
        self.votes[vote.proposal_id].append(vote)
        
        agent = self.agents[vote.agent_id]
        agent.vote_count += 1
        return vote

    def resolve_proposal(self, proposal_id: str) -> ConsensusResult:
        """Resolve using configured strategy."""
        if proposal_id not in self.proposals:
            raise ValueError(f"Proposal {proposal_id} not found.")
            
        proposal = self.proposals[proposal_id]
        if proposal.status not in (ProposalStatus.OPEN, ProposalStatus.EXPIRED):
            raise ValueError(f"Proposal {proposal_id} is already resolved.")
            
        votes = self.votes[proposal_id]
        
        approve_count = sum(1 for v in votes if v.value == VoteValue.APPROVE)
        reject_count = sum(1 for v in votes if v.value == VoteValue.REJECT)
        abstain_count = sum(1 for v in votes if v.value == VoteValue.ABSTAIN)
        
        weighted_approve = 0.0
        weighted_reject = 0.0
        
        for v in votes:
            agent = self.agents[v.agent_id]
            if v.value == VoteValue.APPROVE:
                weighted_approve += agent.weight
            elif v.value == VoteValue.REJECT:
                weighted_reject += agent.weight
                
        outcome = VoteValue.REJECT
        
        if proposal.strategy == ConsensusStrategy.MAJORITY:
            if approve_count > (approve_count + reject_count) / 2 if (approve_count + reject_count) > 0 else 0:
                outcome = VoteValue.APPROVE
        elif proposal.strategy == ConsensusStrategy.UNANIMOUS:
            if approve_count > 0 and reject_count == 0:
                outcome = VoteValue.APPROVE
        elif proposal.strategy == ConsensusStrategy.WEIGHTED:
            if weighted_approve > weighted_reject:
                outcome = VoteValue.APPROVE
        elif proposal.strategy == ConsensusStrategy.QUORUM:
            total_agents = len(self.agents)
            participation = len(votes) / total_agents if total_agents > 0 else 0
            if participation >= proposal.quorum_threshold:
                if approve_count > (approve_count + reject_count) / 2 if (approve_count + reject_count) > 0 else 0:
                    outcome = VoteValue.APPROVE
            else:
                outcome = VoteValue.REJECT
        elif proposal.strategy == ConsensusStrategy.ARBITER:
            raise ValueError("Use arbitrate() to resolve ARBITER proposals.")
            
        proposal.status = ProposalStatus.APPROVED if outcome == VoteValue.APPROVE else ProposalStatus.REJECTED
        
        return ConsensusResult(
            proposal_id=proposal_id,
            outcome=outcome,
            approve_count=approve_count,
            reject_count=reject_count,
            abstain_count=abstain_count,
            weighted_approve=weighted_approve,
            weighted_reject=weighted_reject,
            strategy_used=proposal.strategy
        )

    def arbitrate(self, proposal_id: str, arbiter_id: str, decision: VoteValue, reasoning: str) -> ConsensusResult:
        """Arbiter breaks tie."""
        if proposal_id not in self.proposals:
            raise ValueError(f"Proposal {proposal_id} not found.")
            
        proposal = self.proposals[proposal_id]
        if proposal.strategy != ConsensusStrategy.ARBITER:
            raise ValueError(f"Proposal {proposal_id} strategy is not ARBITER.")
            
        if arbiter_id != proposal.arbiter_id:
            raise PermissionError(f"Agent {arbiter_id} is not the designated arbiter.")
            
        proposal.status = ProposalStatus.ARBITRATED
        
        votes = self.votes[proposal_id]
        approve_count = sum(1 for v in votes if v.value == VoteValue.APPROVE)
        reject_count = sum(1 for v in votes if v.value == VoteValue.REJECT)
        abstain_count = sum(1 for v in votes if v.value == VoteValue.ABSTAIN)
        
        return ConsensusResult(
            proposal_id=proposal_id,
            outcome=decision,
            approve_count=approve_count,
            reject_count=reject_count,
            abstain_count=abstain_count,
            weighted_approve=0.0,
            weighted_reject=0.0,
            strategy_used=ConsensusStrategy.ARBITER,
            decided_by=arbiter_id
        )

    def get_proposal(self, proposal_id: str) -> ConsensusProposal:
        """Get proposal details."""
        if proposal_id not in self.proposals:
            raise ValueError(f"Proposal {proposal_id} not found.")
        return self.proposals[proposal_id]

    def get_votes(self, proposal_id: str) -> List[AgentVote]:
        """All votes for proposal."""
        if proposal_id not in self.votes:
            raise ValueError(f"Proposal {proposal_id} not found.")
        return list(self.votes[proposal_id])

    def update_trust_scores(self, proposal_id: str, ground_truth: VoteValue) -> None:
        """Update trust based on whether agents voted correctly."""
        if proposal_id not in self.votes:
            raise ValueError(f"Proposal {proposal_id} not found.")
            
        votes = self.votes[proposal_id]
        for vote in votes:
            if vote.value == VoteValue.ABSTAIN:
                continue
                
            agent = self.agents[vote.agent_id]
            if vote.value == ground_truth:
                agent.correct_predictions += 1
                agent.trust_score = min(1.0, agent.trust_score + 0.1)
            else:
                agent.trust_score = max(0.0, agent.trust_score - 0.05)

    def get_agent_stats(self, agent_id: str) -> Dict:
        """Vote count, accuracy, trust score."""
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not found.")
            
        agent = self.agents[agent_id]
        accuracy = (agent.correct_predictions / agent.vote_count) if agent.vote_count > 0 else 0.0
        
        return {
            "vote_count": agent.vote_count,
            "correct_predictions": agent.correct_predictions,
            "accuracy": accuracy,
            "trust_score": agent.trust_score
        }

    def expire_proposals(self, current_time: str) -> List[str]:
        """Expire overdue proposals."""
        expired = []
        for pid, proposal in self.proposals.items():
            if proposal.status == ProposalStatus.OPEN and proposal.deadline:
                if current_time > proposal.deadline:
                    proposal.status = ProposalStatus.EXPIRED
                    expired.append(pid)
        return expired

    def get_consensus_report(self) -> Dict:
        """Summary: proposals by status, agent participation, avg trust."""
        status_counts = {status.value: 0 for status in ProposalStatus}
        for p in self.proposals.values():
            status_counts[p.status.value] += 1
            
        total_trust = sum(a.trust_score for a in self.agents.values())
        avg_trust = total_trust / len(self.agents) if self.agents else 0.0
        
        return {
            "total_proposals": len(self.proposals),
            "proposals_by_status": status_counts,
            "total_agents": len(self.agents),
            "average_trust_score": avg_trust
        }

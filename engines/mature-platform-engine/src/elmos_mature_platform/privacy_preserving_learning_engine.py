from typing import Dict, List, Optional
import datetime
from .types import (
    PrivacyBudget,
    FederatedParticipant,
    FederatedRound,
    FederatedRoundStatus,
    PrivacyMechanism
)

class PrivacyPreservingLearningEngine:
    def __init__(self):
        self.budgets: Dict[str, PrivacyBudget] = {}
        self.participants: Dict[str, FederatedParticipant] = {}
        self.rounds: Dict[str, FederatedRound] = {}
        self.round_contributions: Dict[str, Dict[str, int]] = {} # round_id -> {participant_id -> data_size}

    def create_budget(self, budget: PrivacyBudget) -> str:
        """Create a privacy budget for a tenant."""
        self.budgets[budget.tenant_id] = budget
        return budget.budget_id

    def check_budget(self, tenant_id: str, epsilon_cost: float) -> bool:
        """Check if a tenant can afford the epsilon cost and has queries remaining."""
        if tenant_id not in self.budgets:
            raise PermissionError(f"No budget found for tenant {tenant_id}")
        budget = self.budgets[tenant_id]
        if budget.queries_used >= budget.queries_allowed:
            return False
        return (budget.epsilon_used + epsilon_cost) <= budget.epsilon_total

    def consume_budget(self, tenant_id: str, epsilon_cost: float) -> PrivacyBudget:
        """Consume epsilon cost and increment queries used."""
        if not self.check_budget(tenant_id, epsilon_cost):
            raise ValueError(f"Insufficient budget for tenant {tenant_id}")
        budget = self.budgets[tenant_id]
        budget.epsilon_used += epsilon_cost
        budget.queries_used += 1
        return budget

    def register_participant(self, participant: FederatedParticipant) -> str:
        """Register a federated learning participant."""
        self.participants[participant.participant_id] = participant
        return participant.participant_id

    def create_round(self, round_data: FederatedRound) -> str:
        """Create a new federated round."""
        self.rounds[round_data.round_id] = round_data
        self.round_contributions[round_data.round_id] = {}
        return round_data.round_id

    def start_round(self, round_id: str) -> FederatedRound:
        """Start a federated round if enough active participants exist."""
        if round_id not in self.rounds:
            raise KeyError(f"Round {round_id} not found")
        
        round_obj = self.rounds[round_id]
        if round_obj.status != FederatedRoundStatus.INITIALIZED:
            raise ValueError(f"Round {round_id} cannot be started from status {round_obj.status}")

        active_participants = []
        for p_id in round_obj.participants:
            if p_id in self.participants and self.participants[p_id].active:
                active_participants.append(p_id)

        if len(active_participants) < round_obj.min_participants:
            raise ValueError(f"Not enough active participants to start round {round_id}")

        round_obj.status = FederatedRoundStatus.TRAINING
        round_obj.started_at = datetime.datetime.utcnow().isoformat()
        return round_obj

    def submit_contribution(self, round_id: str, participant_id: str, data_size: int) -> FederatedParticipant:
        """Submit a contribution for a specific round."""
        if round_id not in self.rounds:
            raise KeyError(f"Round {round_id} not found")
        if participant_id not in self.participants:
            raise KeyError(f"Participant {participant_id} not found")
            
        round_obj = self.rounds[round_id]
        if round_obj.status != FederatedRoundStatus.TRAINING:
            raise ValueError(f"Round {round_id} is not in TRAINING state")
        if participant_id not in round_obj.participants:
            raise ValueError(f"Participant {participant_id} not part of round {round_id}")
        if not self.participants[participant_id].active:
            raise ValueError(f"Participant {participant_id} is not active")

        # Record contribution data size
        self.round_contributions[round_id][participant_id] = data_size
        
        participant = self.participants[participant_id]
        participant.last_contribution_at = datetime.datetime.utcnow().isoformat()
        participant.contribution_count += 1
        
        return participant

    def aggregate_round(self, round_id: str) -> FederatedRound:
        """Aggregate round contributions."""
        if round_id not in self.rounds:
            raise KeyError(f"Round {round_id} not found")
            
        round_obj = self.rounds[round_id]
        if round_obj.status != FederatedRoundStatus.TRAINING:
            raise ValueError(f"Round {round_id} must be in TRAINING state to aggregate")
            
        contributions = self.round_contributions[round_id]
        if not contributions:
            raise ValueError(f"No contributions received for round {round_id}")
            
        total_data = sum(contributions.values())
        if total_data == 0:
            raise ValueError("Total data size is zero, cannot compute weights")
            
        round_obj.aggregation_weights = {
            p_id: size / total_data for p_id, size in contributions.items()
        }
        
        # Deduct budget for all participating tenants
        for p_id in contributions.keys():
            tenant_id = self.participants[p_id].tenant_id
            try:
                self.consume_budget(tenant_id, round_obj.epsilon_spent)
            except ValueError:
                # In a real system, might fail the round or exclude the tenant
                # For this engine, we require they have budget to aggregate
                raise ValueError(f"Participant {p_id} (tenant {tenant_id}) ran out of budget during aggregation")

        round_obj.status = FederatedRoundStatus.AGGREGATING
        round_obj.model_version_out = round_obj.model_version_in + 1
        return round_obj

    def complete_round(self, round_id: str) -> FederatedRound:
        """Finalize the federated round."""
        if round_id not in self.rounds:
            raise KeyError(f"Round {round_id} not found")
            
        round_obj = self.rounds[round_id]
        if round_obj.status != FederatedRoundStatus.AGGREGATING:
            raise ValueError(f"Round {round_id} must be in AGGREGATING state to complete")
            
        round_obj.status = FederatedRoundStatus.COMPLETED
        round_obj.completed_at = datetime.datetime.utcnow().isoformat()
        
        # Update model version for participants that contributed
        for p_id in self.round_contributions[round_id].keys():
            self.participants[p_id].model_version = round_obj.model_version_out
            
        return round_obj

    def drop_participant(self, round_id: str, participant_id: str) -> FederatedParticipant:
        """Mark a participant as dropped out for a round."""
        if participant_id not in self.participants:
            raise KeyError(f"Participant {participant_id} not found")
        participant = self.participants[participant_id]
        participant.dropped_rounds += 1
        return participant

    def get_privacy_report(self, tenant_id: str) -> Dict:
        """Return a report of privacy budget usage for a tenant."""
        if tenant_id not in self.budgets:
            raise PermissionError(f"No budget found for tenant {tenant_id}")
        budget = self.budgets[tenant_id]
        
        return {
            "tenant_id": tenant_id,
            "budget_id": budget.budget_id,
            "epsilon_total": budget.epsilon_total,
            "epsilon_used": budget.epsilon_used,
            "epsilon_remaining": budget.epsilon_total - budget.epsilon_used,
            "queries_allowed": budget.queries_allowed,
            "queries_used": budget.queries_used,
            "queries_remaining": budget.queries_allowed - budget.queries_used,
            "mechanism": budget.mechanism.value
        }

    def get_federation_report(self) -> Dict:
        """Return a global federation summary report."""
        total_rounds = len(self.rounds)
        completed_rounds = sum(1 for r in self.rounds.values() if r.status == FederatedRoundStatus.COMPLETED)
        total_participants = len(self.participants)
        active_participants = sum(1 for p in self.participants.values() if p.active)
        
        total_contributions = sum(p.contribution_count for p in self.participants.values())
        total_dropped = sum(p.dropped_rounds for p in self.participants.values())
        
        participation_rate = 0.0
        if total_contributions + total_dropped > 0:
            participation_rate = total_contributions / (total_contributions + total_dropped)
            
        max_model_version = max([r.model_version_out for r in self.rounds.values()] + [0])
            
        return {
            "total_rounds": total_rounds,
            "completed_rounds": completed_rounds,
            "total_participants": total_participants,
            "active_participants": active_participants,
            "avg_participation_rate": participation_rate,
            "highest_model_version": max_model_version
        }

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from elmos_mature_platform.types import (
    StoredArtifact,
    RetentionRule,
    ArtifactTier,
    RetentionPolicyAction
)

class ArtifactRetentionEconomicsEngine:
    """
    Engine for managing artifact retention lifecycle and analyzing storage economics.
    """
    
    TIER_PRICING = {
        ArtifactTier.HOT: 0.023,
        ArtifactTier.WARM: 0.0125,
        ArtifactTier.COLD: 0.004,
        ArtifactTier.ARCHIVE: 0.001,
        ArtifactTier.DELETED: 0.0,
    }

    def __init__(self):
        self.artifacts: Dict[str, StoredArtifact] = {}
        self.rules: Dict[str, RetentionRule] = {}
        self._mock_now: Optional[datetime] = None

    def _now(self) -> datetime:
        if self._mock_now:
            return self._mock_now
        return datetime.utcnow()
        
    def _now_iso(self) -> str:
        return self._now().isoformat() + "Z"
    
    def register_artifact(self, artifact: StoredArtifact) -> str:
        """
        Registers a new artifact with the engine.
        Calculates initial cost per GB month based on tier.
        """
        if not artifact.created_at:
            artifact.created_at = self._now_iso()
        if not artifact.last_accessed:
            artifact.last_accessed = artifact.created_at
        
        artifact.cost_per_gb_month = self.TIER_PRICING.get(artifact.tier, 0.023)
        self.artifacts[artifact.artifact_id] = artifact
        return artifact.artifact_id
        
    def record_access(self, artifact_id: str) -> StoredArtifact:
        """
        Records an access event on an artifact, incrementing its access count.
        """
        if artifact_id not in self.artifacts:
            raise ValueError(f"Artifact {artifact_id} not found.")
        artifact = self.artifacts[artifact_id]
        artifact.access_count += 1
        artifact.last_accessed = self._now_iso()
        return artifact
        
    def set_legal_hold(self, artifact_id: str, hold: bool) -> StoredArtifact:
        """
        Toggles legal hold on an artifact. Artifacts on legal hold cannot be deleted.
        """
        if artifact_id not in self.artifacts:
            raise ValueError(f"Artifact {artifact_id} not found.")
        self.artifacts[artifact_id].legal_hold = hold
        return self.artifacts[artifact_id]
        
    def create_rule(self, rule: RetentionRule) -> str:
        """
        Creates a new retention rule to be evaluated against artifacts.
        """
        self.rules[rule.rule_id] = rule
        return rule.rule_id
        
    def evaluate_retention(self, artifact_id: str) -> Dict:
        """
        Evaluates all retention rules for a specific artifact and recommends an action.
        """
        if artifact_id not in self.artifacts:
            raise ValueError(f"Artifact {artifact_id} not found.")
        
        artifact = self.artifacts[artifact_id]
        if artifact.legal_hold:
            return {"action": RetentionPolicyAction.KEEP.value, "reason": "legal_hold", "rule_id": None}
            
        try:
            created_dt = datetime.fromisoformat(artifact.created_at.replace('Z', '+00:00')).replace(tzinfo=None)
            age_days = (self._now() - created_dt).days
        except Exception:
            age_days = 0
            
        for rule_id, rule in self.rules.items():
            # Check if rule applies based on tags
            tag_match = True
            for k, v in rule.applies_to_tags.items():
                if artifact.tags.get(k) != v:
                    tag_match = False
                    break
                    
            if not tag_match:
                continue
                
            # Rule applies, check conditions
            if age_days >= rule.max_age_days and artifact.access_count <= rule.min_access_count:
                return {
                    "action": rule.action.value,
                    "target_tier": rule.target_tier.value if rule.action == RetentionPolicyAction.TIER_DOWN else None,
                    "reason": "rule_matched",
                    "rule_id": rule.rule_id
                }
                
        return {"action": RetentionPolicyAction.KEEP.value, "reason": "no_rule_matched", "rule_id": None}
        
    def apply_tier_change(self, artifact_id: str, new_tier: ArtifactTier) -> StoredArtifact:
        """
        Applies a storage tier change to an artifact and updates its cost profile.
        """
        if artifact_id not in self.artifacts:
            raise ValueError(f"Artifact {artifact_id} not found.")
            
        artifact = self.artifacts[artifact_id]
        if artifact.legal_hold and new_tier == ArtifactTier.DELETED:
            raise PermissionError("Cannot delete an artifact under legal hold.")
            
        artifact.tier = new_tier
        artifact.cost_per_gb_month = self.TIER_PRICING.get(new_tier, 0.023)
        return artifact
        
    def calculate_storage_cost(self, artifact_id: str, months: int = 1) -> float:
        """
        Calculates storage cost for an artifact over a given number of months.
        """
        if artifact_id not in self.artifacts:
            raise ValueError(f"Artifact {artifact_id} not found.")
            
        artifact = self.artifacts[artifact_id]
        size_gb = artifact.size_bytes / (1024 ** 3)
        return size_gb * artifact.cost_per_gb_month * months
        
    def get_total_cost(self, months: int = 1) -> float:
        """
        Calculates total storage cost across all artifacts.
        """
        return sum(self.calculate_storage_cost(aid, months) for aid in self.artifacts)
        
    def get_cost_by_tier(self) -> Dict[str, float]:
        """
        Returns monthly cost breakdown by storage tier.
        """
        breakdown = {t.value: 0.0 for t in ArtifactTier}
        for artifact in self.artifacts.values():
            size_gb = artifact.size_bytes / (1024 ** 3)
            breakdown[artifact.tier.value] += size_gb * artifact.cost_per_gb_month
        return breakdown
        
    def get_savings_opportunity(self) -> Dict:
        """
        Analyzes artifacts eligible for tier-down or deletion and calculates potential savings.
        """
        savings = 0.0
        eligible = []
        for aid, artifact in self.artifacts.items():
            eval_res = self.evaluate_retention(aid)
            action = eval_res.get("action")
            if action in [RetentionPolicyAction.TIER_DOWN.value, RetentionPolicyAction.DELETE.value]:
                size_gb = artifact.size_bytes / (1024 ** 3)
                current_cost = size_gb * artifact.cost_per_gb_month
                
                if action == RetentionPolicyAction.DELETE.value:
                    new_cost = 0.0
                else:
                    target_tier = ArtifactTier(eval_res["target_tier"])
                    new_cost = size_gb * self.TIER_PRICING.get(target_tier, artifact.cost_per_gb_month)
                    
                if new_cost < current_cost:
                    potential_saving = current_cost - new_cost
                    savings += potential_saving
                    eligible.append({
                        "artifact_id": aid,
                        "action": action,
                        "potential_savings": potential_saving
                    })
                    
        return {
            "eligible_artifacts": eligible,
            "total_potential_savings": savings
        }
        
    def get_retention_report(self) -> Dict:
        """
        Generates a comprehensive retention and economics report.
        """
        tier_counts = {t.value: 0 for t in ArtifactTier}
        tier_sizes = {t.value: 0 for t in ArtifactTier}
        legal_holds = 0
        access_dist = {"0": 0, "1-10": 0, "11-100": 0, ">100": 0}
        
        for artifact in self.artifacts.values():
            t_val = artifact.tier.value
            tier_counts[t_val] += 1
            tier_sizes[t_val] += artifact.size_bytes
            
            if artifact.legal_hold:
                legal_holds += 1
                
            ac = artifact.access_count
            if ac == 0:
                access_dist["0"] += 1
            elif 1 <= ac <= 10:
                access_dist["1-10"] += 1
            elif 11 <= ac <= 100:
                access_dist["11-100"] += 1
            else:
                access_dist[">100"] += 1
                
        return {
            "by_tier": {
                "counts": tier_counts,
                "sizes_bytes": tier_sizes,
                "costs_monthly": self.get_cost_by_tier()
            },
            "legal_holds": legal_holds,
            "access_frequency": access_dist,
            "total_artifacts": len(self.artifacts),
            "total_size_bytes": sum(tier_sizes.values())
        }

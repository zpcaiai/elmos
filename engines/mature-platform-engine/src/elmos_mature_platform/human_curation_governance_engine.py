from typing import List, Dict, Optional
from datetime import datetime, timezone
import json

from elmos_mature_platform.types import (
    CurationItem,
    CurationPolicy,
    CurationAction,
    ContentCategory
)

class HumanCurationGovernanceEngine:
    def __init__(self):
        self._items: Dict[str, CurationItem] = {}
        self._policies: Dict[ContentCategory, CurationPolicy] = {}

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def submit_item(self, item: CurationItem) -> str:
        """Submit an item for curation."""
        if not (0.0 <= item.quality_score <= 1.0):
            raise ValueError("Quality score must be between 0.0 and 1.0")
        
        if not item.created_at:
            item.created_at = self._now_iso()
            
        self._items[item.item_id] = item
        return item.item_id

    def set_policy(self, policy: CurationPolicy) -> str:
        """Set a curation policy for a specific content category."""
        self._policies[policy.category] = policy
        return policy.policy_id

    def auto_curate(self, item_id: str) -> CurationItem:
        """Attempt to auto-approve an item based on policy and quality score."""
        if item_id not in self._items:
            raise KeyError(f"Item {item_id} not found")
            
        item = self._items[item_id]
        
        if item.action in [CurationAction.APPROVE, CurationAction.REJECT]:
            raise ValueError("Cannot curate already-approved/rejected item")
            
        if item.conflicts_with:
            raise ValueError("Conflict items cannot be approved until resolved")
            
        policy = self._policies.get(item.category)
        if not policy:
            raise ValueError(f"No policy defined for category {item.category}")
            
        if policy.require_human_review:
            raise ValueError("Policy requires human review")
            
        if item.quality_score >= policy.auto_approve_threshold:
            item.action = CurationAction.APPROVE
            item.curator = "system_auto"
            item.curated_at = self._now_iso()
            item.review_notes = "Auto-approved by policy threshold"
            return item
        else:
            raise ValueError("Quality score below auto-approve threshold")

    def curate(self, item_id: str, curator: str, action: CurationAction, notes: str) -> CurationItem:
        """Human curation action on an item."""
        if item_id not in self._items:
            raise KeyError(f"Item {item_id} not found")
            
        item = self._items[item_id]
        
        if item.action in [CurationAction.APPROVE, CurationAction.REJECT]:
            raise ValueError("Cannot curate already-approved/rejected item (must reset first)")
            
        if action == CurationAction.APPROVE and item.conflicts_with:
            raise ValueError("Conflict items cannot be approved until resolved")
            
        item.action = action
        item.curator = curator
        item.curated_at = self._now_iso()
        item.review_notes = notes
        
        return item

    def flag_conflict(self, item_id: str, conflicting_id: str) -> CurationItem:
        """Flag a conflict between items."""
        if item_id not in self._items:
            raise KeyError(f"Item {item_id} not found")
        if conflicting_id not in self._items:
            raise KeyError(f"Conflicting item {conflicting_id} not found")
            
        item = self._items[item_id]
        if conflicting_id not in item.conflicts_with:
            item.conflicts_with.append(conflicting_id)
            
        item.action = CurationAction.FLAG
        
        return item

    def resolve_conflict(self, item_id: str, resolution: str) -> CurationItem:
        """Resolve conflicts for an item."""
        if item_id not in self._items:
            raise KeyError(f"Item {item_id} not found")
            
        item = self._items[item_id]
        item.conflicts_with = []
        item.action = CurationAction.DEFER
        item.review_notes = f"Conflict resolved: {resolution}"
        
        return item

    def get_pending_items(self, category: str = "") -> List[CurationItem]:
        """Get items awaiting curation."""
        pending = []
        for item in self._items.values():
            if item.action not in [CurationAction.APPROVE, CurationAction.REJECT]:
                if not category or item.category.value == category or item.category == category:
                    pending.append(item)
        return pending

    def get_quality_distribution(self) -> Dict:
        """Get quality score histogram by category."""
        dist = {}
        for cat in ContentCategory:
            dist[cat.value] = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
            
        for item in self._items.values():
            cat = item.category.value if isinstance(item.category, ContentCategory) else item.category
            if cat not in dist:
                continue
                
            q = item.quality_score
            if q <= 0.2:
                dist[cat]["0.0-0.2"] += 1
            elif q <= 0.4:
                dist[cat]["0.2-0.4"] += 1
            elif q <= 0.6:
                dist[cat]["0.4-0.6"] += 1
            elif q <= 0.8:
                dist[cat]["0.6-0.8"] += 1
            else:
                dist[cat]["0.8-1.0"] += 1
                
        return dist

    def get_curator_stats(self) -> Dict:
        """Get per-curator statistics."""
        stats = {}
        for item in self._items.values():
            if not item.curator or item.curator == "system_auto":
                continue
                
            c = item.curator
            if c not in stats:
                stats[c] = {"reviewed": 0, "approved": 0, "rejected": 0, "ratio": 0.0}
                
            stats[c]["reviewed"] += 1
            if item.action == CurationAction.APPROVE:
                stats[c]["approved"] += 1
            elif item.action == CurationAction.REJECT:
                stats[c]["rejected"] += 1
                
        for c in stats:
            total = stats[c]["approved"] + stats[c]["rejected"]
            if total > 0:
                stats[c]["ratio"] = stats[c]["approved"] / total
                
        return stats

    def get_stale_items(self, max_age_days: int) -> List[CurationItem]:
        """Get uncurated items older than the max age threshold."""
        stale = []
        now = datetime.now(timezone.utc)
        
        for item in self._items.values():
            if item.action in [CurationAction.APPROVE, CurationAction.REJECT]:
                continue
                
            try:
                created = datetime.fromisoformat(item.created_at.replace("Z", "+00:00"))
            except ValueError:
                continue
                
            days_old = (now - created).days
            if days_old > max_age_days:
                stale.append(item)
                
        return stale

    def get_governance_report(self) -> Dict:
        """Get comprehensive governance report."""
        report = {
            "by_category": {},
            "by_action": {a.value: 0 for a in CurationAction},
            "auto_vs_human": {"auto": 0, "human": 0},
            "conflicts": 0,
            "total_items": len(self._items)
        }
        
        for cat in ContentCategory:
            report["by_category"][cat.value] = 0
            
        for item in self._items.values():
            cat = item.category.value if isinstance(item.category, ContentCategory) else item.category
            report["by_category"][cat] = report["by_category"].get(cat, 0) + 1
            
            action_val = item.action.value if isinstance(item.action, CurationAction) else item.action
            report["by_action"][action_val] = report["by_action"].get(action_val, 0) + 1
            
            if item.curator == "system_auto":
                report["auto_vs_human"]["auto"] += 1
            elif item.curator:
                report["auto_vs_human"]["human"] += 1
                
            if item.conflicts_with or item.action == CurationAction.FLAG:
                report["conflicts"] += 1
                
        return report

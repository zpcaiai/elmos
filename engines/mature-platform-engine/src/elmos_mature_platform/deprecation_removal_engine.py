from typing import Dict, List, Optional
from datetime import datetime, timedelta
from .types import DeprecatedItem, DeprecationPolicy, DeprecationPhase

class DeprecationRemovalEngine:
    def __init__(self):
        self.policies: Dict[str, DeprecationPolicy] = {}
        self.items: Dict[str, DeprecatedItem] = {}

    def _get_current_date(self) -> str:
        return datetime.utcnow().date().isoformat()

    def create_policy(self, policy: DeprecationPolicy):
        """Creates a new deprecation policy."""
        self.policies[policy.policy_id] = policy

    def announce_deprecation(self, item: DeprecatedItem) -> str:
        """Announce an item for future deprecation."""
        if item.item_id in self.items:
            raise ValueError(f"Item {item.item_id} already exists.")
        
        item.phase = DeprecationPhase.ANNOUNCED
        if not item.announced_at:
            item.announced_at = self._get_current_date()
            
        self.items[item.item_id] = item
        return item.item_id

    def deprecate_item(self, item_id: str) -> DeprecatedItem:
        """Move an ANNOUNCED item to DEPRECATED."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Item {item_id} not found.")
            
        if item.phase != DeprecationPhase.ANNOUNCED:
            raise ValueError(f"Item must be ANNOUNCED to be DEPRECATED, current: {item.phase}")
            
        item.phase = DeprecationPhase.DEPRECATED
        item.deprecated_at = self._get_current_date()
        return item

    def schedule_sunset(self, item_id: str, sunset_date: str) -> DeprecatedItem:
        """Set the sunset date for a DEPRECATED item, moving it to SUNSET phase."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Item {item_id} not found.")
            
        if item.phase != DeprecationPhase.DEPRECATED:
            raise ValueError(f"Item must be DEPRECATED to schedule SUNSET, current: {item.phase}")
            
        item.sunset_at = sunset_date
        item.phase = DeprecationPhase.SUNSET
        return item

    def remove_item(self, item_id: str, policy_id: str) -> DeprecatedItem:
        """Remove an item, validating against the given policy."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Item {item_id} not found.")
            
        if item.phase != DeprecationPhase.SUNSET:
            raise ValueError(f"Item must be in SUNSET phase to be REMOVED, current: {item.phase}")
            
        validation = self.validate_removal(item_id, policy_id)
        if not validation["ready"]:
            reasons = ", ".join(validation["reasons"])
            raise ValueError(f"Item {item_id} not ready for removal: {reasons}")
            
        item.phase = DeprecationPhase.REMOVED
        item.removed_at = self._get_current_date()
        return item

    def record_usage(self, item_id: str, consumer: str):
        """Record consumer usage of a deprecated item."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Item {item_id} not found.")
            
        item.usage_count += 1
        if consumer not in item.affected_consumers:
            item.affected_consumers.append(consumer)

    def get_active_consumers(self, item_id: str) -> List[str]:
        """List active consumers of a deprecated item."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Item {item_id} not found.")
        return item.affected_consumers

    def get_items_by_phase(self, phase: DeprecationPhase) -> List[DeprecatedItem]:
        """Filter items by their current phase."""
        return [item for item in self.items.values() if item.phase == phase]

    def get_overdue_items(self, current_date: str) -> List[DeprecatedItem]:
        """Get items that are past their sunset date but not yet removed."""
        overdue = []
        for item in self.items.values():
            if item.phase == DeprecationPhase.SUNSET and item.sunset_at:
                if item.sunset_at < current_date:
                    overdue.append(item)
        return overdue

    def validate_removal(self, item_id: str, policy_id: str) -> Dict:
        """Check removal readiness against a policy."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Item {item_id} not found.")
            
        policy = self.policies.get(policy_id)
        if not policy:
            raise ValueError(f"Policy {policy_id} not found.")
            
        reasons = []
        
        if policy.require_replacement and not item.replacement:
            reasons.append("Replacement is required but not provided.")
            
        if policy.require_migration_guide and not item.migration_guide_url:
            reasons.append("Migration guide is required but not provided.")
            
        if policy.block_removal_with_active_consumers and item.affected_consumers:
            reasons.append(f"Has {len(item.affected_consumers)} active consumers.")
            
        if item.announced_at:
            try:
                announced = datetime.strptime(item.announced_at, "%Y-%m-%d").date()
                current = datetime.utcnow().date()
                days_since_notice = (current - announced).days
                if days_since_notice < policy.min_notice_days:
                    reasons.append(f"Minimum notice period of {policy.min_notice_days} days not met (current: {days_since_notice}).")
            except ValueError:
                pass
                
        return {
            "ready": len(reasons) == 0,
            "reasons": reasons
        }

    def get_deprecation_report(self) -> Dict:
        """Get a summary report of deprecations."""
        report = {
            "by_phase": {
                DeprecationPhase.ANNOUNCED.value: 0,
                DeprecationPhase.DEPRECATED.value: 0,
                DeprecationPhase.SUNSET.value: 0,
                DeprecationPhase.REMOVED.value: 0,
            },
            "total_items": len(self.items),
            "overdue_count": len(self.get_overdue_items(self._get_current_date())),
            "most_impactful": []
        }
        
        impactful = sorted(
            [i for i in self.items.values() if i.phase != DeprecationPhase.REMOVED],
            key=lambda x: len(x.affected_consumers), 
            reverse=True
        )
        report["most_impactful"] = [
            {"item_id": i.item_id, "consumers": len(i.affected_consumers)}
            for i in impactful[:5]
        ]
        
        for item in self.items.values():
            report["by_phase"][item.phase.value] += 1
            
        return report

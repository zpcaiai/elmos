import time
import uuid
import hashlib
from typing import List, Dict, Optional
from datetime import datetime, timezone
from elmos_mature_platform.types import (
    ProgressiveFlag,
    ProgressiveFlagStatus,
    FlagRolloutStrategy,
    RolloutStep,
)

class FeatureFlagProgressiveEnableEngine:
    """Engine for progressively rolling out feature flags."""

    def __init__(self):
        self._flags: Dict[str, ProgressiveFlag] = {}
        self._rollout_steps: Dict[str, List[RolloutStep]] = {}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_flag(self, flag: ProgressiveFlag) -> str:
        """Create a new progressive flag."""
        if flag.flag_id in self._flags:
            raise ValueError(f"Flag {flag.flag_id} already exists.")
        
        flag.created_at = self._now()
        flag.last_updated = flag.created_at
        flag.status = ProgressiveFlagStatus.DISABLED
        flag.rollout_history.append(f"Created as {flag.status.value}")
        
        self._flags[flag.flag_id] = flag
        self._rollout_steps[flag.flag_id] = []
        return flag.flag_id

    def enable_canary(self, flag_id: str, users: List[str]) -> ProgressiveFlag:
        """Enable the flag for a specific set of users (CANARY)."""
        if flag_id not in self._flags:
            raise KeyError(f"Flag {flag_id} not found.")
            
        flag = self._flags[flag_id]
        if flag.status in [ProgressiveFlagStatus.ROLLED_BACK]:
            raise ValueError("Cannot enable a rolled back flag without reset.")
            
        flag.status = ProgressiveFlagStatus.CANARY
        flag.strategy = FlagRolloutStrategy.USER_LIST
        flag.target_users = users.copy()
        flag.last_updated = self._now()
        flag.rollout_history.append(f"Status changed to {flag.status.value} for {len(users)} canary users.")
        
        return flag

    def start_rollout(self, flag_id: str, initial_percentage: float) -> ProgressiveFlag:
        """Start a percentage-based rollout."""
        if not (0.0 <= initial_percentage <= 100.0):
            raise ValueError("Percentage must be between 0 and 100.")
            
        if flag_id not in self._flags:
            raise KeyError(f"Flag {flag_id} not found.")
            
        flag = self._flags[flag_id]
        if flag.status in [ProgressiveFlagStatus.PAUSED, ProgressiveFlagStatus.ROLLED_BACK]:
            raise ValueError(f"Cannot start rollout for flag in status {flag.status.value}.")
            
        flag.status = ProgressiveFlagStatus.ROLLING
        flag.strategy = FlagRolloutStrategy.PERCENTAGE
        flag.percentage = initial_percentage
        flag.last_updated = self._now()
        flag.rollout_history.append(f"Rollout started at {initial_percentage}%.")
        
        step = RolloutStep(
            step_id=str(uuid.uuid4()),
            flag_id=flag_id,
            from_percentage=0.0,
            to_percentage=initial_percentage,
            executed_at=self._now(),
            success=True,
            error_rate_at_execution=flag.current_error_rate,
        )
        self._rollout_steps[flag_id].append(step)
        
        return flag

    def increase_rollout(self, flag_id: str, new_percentage: float) -> RolloutStep:
        """Increase the percentage of a rollout."""
        if not (0.0 <= new_percentage <= 100.0):
            raise ValueError("Percentage must be between 0 and 100.")
            
        if flag_id not in self._flags:
            raise KeyError(f"Flag {flag_id} not found.")
            
        flag = self._flags[flag_id]
        if flag.status != ProgressiveFlagStatus.ROLLING:
            raise ValueError(f"Cannot increase rollout for flag in status {flag.status.value}.")
            
        if new_percentage <= flag.percentage:
            raise ValueError(f"New percentage {new_percentage} must be > current {flag.percentage}.")
            
        old_percentage = flag.percentage
        flag.percentage = new_percentage
        flag.last_updated = self._now()
        flag.rollout_history.append(f"Rollout increased to {new_percentage}%.")
        
        if new_percentage == 100.0:
            self.fully_enable(flag_id)
            
        step = RolloutStep(
            step_id=str(uuid.uuid4()),
            flag_id=flag_id,
            from_percentage=old_percentage,
            to_percentage=new_percentage,
            executed_at=self._now(),
            success=True,
            error_rate_at_execution=flag.current_error_rate,
        )
        self._rollout_steps[flag_id].append(step)
        
        return step

    def fully_enable(self, flag_id: str) -> ProgressiveFlag:
        """Set the flag to 100% and fully enabled."""
        if flag_id not in self._flags:
            raise KeyError(f"Flag {flag_id} not found.")
            
        flag = self._flags[flag_id]
        if flag.status == ProgressiveFlagStatus.ROLLED_BACK:
            raise ValueError("Cannot fully enable a rolled back flag.")
            
        flag.status = ProgressiveFlagStatus.FULLY_ENABLED
        flag.strategy = FlagRolloutStrategy.ALL
        flag.percentage = 100.0
        flag.last_updated = self._now()
        flag.rollout_history.append(f"Flag fully enabled.")
        
        return flag

    def pause_rollout(self, flag_id: str) -> ProgressiveFlag:
        """Pause the current rollout."""
        if flag_id not in self._flags:
            raise KeyError(f"Flag {flag_id} not found.")
            
        flag = self._flags[flag_id]
        if flag.status != ProgressiveFlagStatus.ROLLING:
            raise ValueError(f"Cannot pause flag not in ROLLING state, current: {flag.status.value}")
            
        flag.status = ProgressiveFlagStatus.PAUSED
        flag.last_updated = self._now()
        flag.rollout_history.append(f"Rollout paused at {flag.percentage}%.")
        
        return flag

    def rollback(self, flag_id: str) -> ProgressiveFlag:
        """Rollback the flag to 0%."""
        if flag_id not in self._flags:
            raise KeyError(f"Flag {flag_id} not found.")
            
        flag = self._flags[flag_id]
        flag.status = ProgressiveFlagStatus.ROLLED_BACK
        flag.percentage = 0.0
        flag.last_updated = self._now()
        flag.rollout_history.append("Flag rolled back to 0%.")
        
        return flag

    def auto_rollback_check(self, flag_id: str, current_error_rate: float) -> bool:
        """Check the error rate and rollback if it exceeds the threshold."""
        if flag_id not in self._flags:
            raise KeyError(f"Flag {flag_id} not found.")
            
        flag = self._flags[flag_id]
        flag.current_error_rate = current_error_rate
        
        if flag.status in [ProgressiveFlagStatus.ROLLING, ProgressiveFlagStatus.CANARY, ProgressiveFlagStatus.FULLY_ENABLED]:
            if current_error_rate > flag.error_rate_threshold:
                self.rollback(flag_id)
                flag.rollout_history.append(f"Auto-rollback triggered by error rate {current_error_rate} > {flag.error_rate_threshold}.")
                return True
                
        return False

    def is_enabled_for_user(self, flag_id: str, user_id: str, region: str = "", tenant: str = "") -> bool:
        """Check if the flag is enabled for the given user/context."""
        if flag_id not in self._flags:
            return False
            
        flag = self._flags[flag_id]
        
        if flag.status == ProgressiveFlagStatus.DISABLED or flag.status == ProgressiveFlagStatus.ROLLED_BACK or flag.status == ProgressiveFlagStatus.PAUSED:
            return False
            
        if flag.status == ProgressiveFlagStatus.FULLY_ENABLED or flag.strategy == FlagRolloutStrategy.ALL:
            return True
            
        if flag.strategy == FlagRolloutStrategy.USER_LIST:
            return user_id in flag.target_users
            
        if flag.strategy == FlagRolloutStrategy.PERCENTAGE:
            # Deterministic bucket assignment using hash
            hash_input = f"{flag_id}:{user_id}".encode('utf-8')
            hash_val = int(hashlib.md5(hash_input).hexdigest()[:8], 16)
            user_percentage = (hash_val % 10000) / 100.0  # 0.00 to 99.99
            
            return user_percentage < flag.percentage
            
        return False

    def get_rollout_history(self, flag_id: str) -> List[RolloutStep]:
        """Get the rollout steps history for a flag."""
        if flag_id not in self._rollout_steps:
            raise KeyError(f"Flag {flag_id} not found.")
        return self._rollout_steps[flag_id]

    def get_active_rollouts(self) -> List[ProgressiveFlag]:
        """Get flags currently in CANARY or ROLLING status."""
        active = []
        for flag in self._flags.values():
            if flag.status in [ProgressiveFlagStatus.CANARY, ProgressiveFlagStatus.ROLLING]:
                active.append(flag)
        return active

    def get_flag_report(self) -> Dict:
        """Generate a report of flag statuses and metrics."""
        status_counts = {status.value: 0 for status in ProgressiveFlagStatus}
        total_rolling_percentage = 0.0
        rolling_count = 0
        
        for flag in self._flags.values():
            status_counts[flag.status.value] += 1
            if flag.status == ProgressiveFlagStatus.ROLLING:
                total_rolling_percentage += flag.percentage
                rolling_count += 1
                
        avg_rollout_percentage = (total_rolling_percentage / rolling_count) if rolling_count > 0 else 0.0
        
        total_flags = len(self._flags)
        rolled_back_count = status_counts[ProgressiveFlagStatus.ROLLED_BACK.value]
        rollback_rate = (rolled_back_count / total_flags * 100.0) if total_flags > 0 else 0.0
        
        return {
            "total_flags": total_flags,
            "status_counts": status_counts,
            "avg_rollout_percentage": avg_rollout_percentage,
            "rollback_rate_percentage": rollback_rate
        }

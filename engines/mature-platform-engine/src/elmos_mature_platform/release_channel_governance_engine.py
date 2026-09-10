from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
import uuid

from elmos_mature_platform.types import (
    ChannelStability,
    PromotionVerdict,
    ReleaseCandidate,
    ChannelPolicy,
    PromotionRecord
)

class ReleaseChannelGovernanceEngine:
    """
    Engine for managing Batch 43 product lifecycle release channels.
    Validates RC promotions through nightly -> alpha -> beta -> rc -> stable -> lts.
    """

    CHANNEL_ORDER = [
        ChannelStability.NIGHTLY,
        ChannelStability.ALPHA,
        ChannelStability.BETA,
        ChannelStability.RC,
        ChannelStability.STABLE,
        ChannelStability.LTS
    ]

    def __init__(self):
        self.policies: Dict[ChannelStability, ChannelPolicy] = {}
        self.candidates: Dict[str, ReleaseCandidate] = {}
        self.promotions: List[PromotionRecord] = []
        
        # Initialize default policies
        for ch in self.CHANNEL_ORDER:
            self.policies[ch] = ChannelPolicy(channel=ch)

    def set_channel_policy(self, policy: ChannelPolicy) -> None:
        """Configure policy per channel."""
        self.policies[policy.channel] = policy

    def create_release_candidate(self, rc: ReleaseCandidate) -> ReleaseCandidate:
        """Create a new release candidate, typically in NIGHTLY."""
        self.candidates[rc.rc_id] = rc
        return rc

    def _get_channel_index(self, channel: ChannelStability) -> int:
        return self.CHANNEL_ORDER.index(channel)

    def evaluate_promotion(self, rc_id: str, to_channel: ChannelStability, actor: str) -> PromotionRecord:
        """Evaluate RC against target channel policy."""
        rc = self.candidates.get(rc_id)
        if not rc:
            raise ValueError(f"RC {rc_id} not found")

        current_idx = self._get_channel_index(rc.channel)
        target_idx = self._get_channel_index(to_channel)

        if target_idx != current_idx + 1:
            return PromotionRecord(
                promotion_id=str(uuid.uuid4()),
                rc_id=rc_id,
                from_channel=rc.channel,
                to_channel=to_channel,
                verdict=PromotionVerdict.BLOCKED,
                reason=f"Cannot promote from {rc.channel} to {to_channel}. Must promote to {self.CHANNEL_ORDER[current_idx + 1] if current_idx + 1 < len(self.CHANNEL_ORDER) else 'None'}.",
                actor=actor,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        policy = self.policies.get(to_channel)
        if not policy:
            return PromotionRecord(
                promotion_id=str(uuid.uuid4()),
                rc_id=rc_id,
                from_channel=rc.channel,
                to_channel=to_channel,
                verdict=PromotionVerdict.BLOCKED,
                reason=f"No policy defined for channel {to_channel}.",
                actor=actor,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        # Evaluate against policy
        if rc.test_pass_rate < policy.min_test_pass_rate:
            return PromotionRecord(
                promotion_id=str(uuid.uuid4()),
                rc_id=rc_id,
                from_channel=rc.channel,
                to_channel=to_channel,
                verdict=PromotionVerdict.BLOCKED,
                reason=f"Test pass rate {rc.test_pass_rate} below minimum {policy.min_test_pass_rate}.",
                actor=actor,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        if policy.require_security_scan and not rc.security_scan_clean:
            return PromotionRecord(
                promotion_id=str(uuid.uuid4()),
                rc_id=rc_id,
                from_channel=rc.channel,
                to_channel=to_channel,
                verdict=PromotionVerdict.BLOCKED,
                reason="Security scan not clean but required by policy.",
                actor=actor,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        if policy.require_zero_breaking_changes and rc.breaking_changes:
            return PromotionRecord(
                promotion_id=str(uuid.uuid4()),
                rc_id=rc_id,
                from_channel=rc.channel,
                to_channel=to_channel,
                verdict=PromotionVerdict.BLOCKED,
                reason="Breaking changes found but policy requires zero.",
                actor=actor,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            
        if policy.min_soak_hours > 0:
            if not self.check_soak_time(rc_id, datetime.now(timezone.utc).isoformat(), policy.min_soak_hours):
                return PromotionRecord(
                    promotion_id=str(uuid.uuid4()),
                    rc_id=rc_id,
                    from_channel=rc.channel,
                    to_channel=to_channel,
                    verdict=PromotionVerdict.BLOCKED,
                    reason=f"Minimum soak time of {policy.min_soak_hours} hours not met.",
                    actor=actor,
                    timestamp=datetime.now(timezone.utc).isoformat()
                )

        # Also, breaking changes block stable/lts promotion according to invariants if we enforce them strictly,
        # but let's assume the policy reflects this. Or we hardcode invariant.
        if to_channel in [ChannelStability.STABLE, ChannelStability.LTS] and rc.breaking_changes:
             return PromotionRecord(
                promotion_id=str(uuid.uuid4()),
                rc_id=rc_id,
                from_channel=rc.channel,
                to_channel=to_channel,
                verdict=PromotionVerdict.BLOCKED,
                reason="Breaking changes block promotion to stable/lts.",
                actor=actor,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        return PromotionRecord(
            promotion_id=str(uuid.uuid4()),
            rc_id=rc_id,
            from_channel=rc.channel,
            to_channel=to_channel,
            verdict=PromotionVerdict.APPROVED,
            reason="All policy checks passed.",
            actor=actor,
            timestamp=datetime.now(timezone.utc).isoformat()
        )

    def promote(self, rc_id: str, to_channel: ChannelStability, actor: str) -> PromotionRecord:
        """Execute promotion if evaluation passes."""
        record = self.evaluate_promotion(rc_id, to_channel, actor)
        self.promotions.append(record)
        
        if record.verdict == PromotionVerdict.APPROVED:
            rc = self.candidates[rc_id]
            rc.channel = to_channel
            rc.promoted_at = record.timestamp
            rc.promoted_to = to_channel.value
            
        return record

    def rollback(self, rc_id: str, actor: str, reason: str) -> PromotionRecord:
        """Rollback to previous version within the window."""
        rc = self.candidates.get(rc_id)
        if not rc:
            raise ValueError(f"RC {rc_id} not found")
            
        policy = self.policies.get(rc.channel)
        
        if not rc.promoted_at:
             raise ValueError("RC was not promoted, cannot rollback")
        
        try:
            promoted_time = datetime.fromisoformat(rc.promoted_at)
        except ValueError:
            promoted_time = datetime.now(timezone.utc)
            
        if policy and policy.max_rollback_window_hours > 0:
            window_end = promoted_time + timedelta(hours=policy.max_rollback_window_hours)
            if datetime.now(timezone.utc) > window_end:
                 raise ValueError("Rollback window expired")
                 
        record = PromotionRecord(
            promotion_id=str(uuid.uuid4()),
            rc_id=rc_id,
            from_channel=rc.channel,
            to_channel=rc.channel, # Rolling back doesn't strictly change its "to_channel" in a simple flow, but marks it rolled back
            verdict=PromotionVerdict.ROLLED_BACK,
            reason=reason,
            actor=actor,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        self.promotions.append(record)
        
        # Lower its channel back to previous if needed, or just mark it
        current_idx = self._get_channel_index(rc.channel)
        if current_idx > 0:
            rc.channel = self.CHANNEL_ORDER[current_idx - 1]
            
        return record

    def get_channel_head(self, channel: ChannelStability) -> Optional[ReleaseCandidate]:
        """Latest RC in each channel."""
        channel_rcs = [rc for rc in self.candidates.values() if rc.channel == channel]
        if not channel_rcs:
            return None
        # Sort by creation/promotion time to get the latest
        return max(channel_rcs, key=lambda x: x.created_at or "")

    def get_promotion_history(self, rc_id: Optional[str] = None) -> List[PromotionRecord]:
        """Full promotion audit trail."""
        if rc_id:
            return [p for p in self.promotions if p.rc_id == rc_id]
        return list(self.promotions)

    def get_channel_report(self) -> Dict:
        """RCs per channel, latest versions, pending promotions."""
        report = {
            "channels": {},
            "total_rcs": len(self.candidates),
            "total_promotions": len(self.promotions)
        }
        for ch in self.CHANNEL_ORDER:
            head = self.get_channel_head(ch)
            report["channels"][ch.value] = {
                "head_version": head.version if head else None,
                "head_rc_id": head.rc_id if head else None,
                "rc_count": len([rc for rc in self.candidates.values() if rc.channel == ch])
            }
        return report

    def check_soak_time(self, rc_id: str, current_time: str, min_soak_hours: int = 0) -> bool:
        """Has RC met minimum soak time?"""
        rc = self.candidates.get(rc_id)
        if not rc:
            return False
            
        try:
            start_time = datetime.fromisoformat(rc.promoted_at) if rc.promoted_at else datetime.fromisoformat(rc.created_at)
            curr = datetime.fromisoformat(current_time)
        except ValueError:
            return False
            
        soak_duration = curr - start_time
        if min_soak_hours == 0:
            policy = self.policies.get(rc.channel)
            if policy:
                min_soak_hours = policy.min_soak_hours
                
        return soak_duration.total_seconds() >= min_soak_hours * 3600

    def detect_version_gaps(self) -> List[Dict]:
        """Find channels where head version has skipped intermediate channels."""
        # e.g., if Beta has v2.0 but Alpha only has v1.0, that's a gap.
        gaps = []
        for i in range(1, len(self.CHANNEL_ORDER)):
            ch = self.CHANNEL_ORDER[i]
            prev_ch = self.CHANNEL_ORDER[i - 1]
            head = self.get_channel_head(ch)
            prev_head = self.get_channel_head(prev_ch)
            
            if head and prev_head:
                # Assuming semver string comparison works for simple check
                # Actually, if the higher channel has a newer version than the lower channel,
                # it means the lower channel might have skipped it or rolled back.
                # Since promotion goes from lower to higher, the lower channel should generally 
                # be >= higher channel.
                pass 
                
        # Actually gap detection is: A version exists in STABLE, but wasn't promoted through RC
        for rc in self.candidates.values():
            if rc.channel == ChannelStability.STABLE:
                # Check history to see if it went through all previous channels
                history = self.get_promotion_history(rc.rc_id)
                channels_visited = {p.to_channel for p in history if p.verdict == PromotionVerdict.APPROVED}
                channels_visited.add(ChannelStability.NIGHTLY) # Starts here usually
                
                expected_channels = {
                    ChannelStability.NIGHTLY,
                    ChannelStability.ALPHA,
                    ChannelStability.BETA,
                    ChannelStability.RC,
                    ChannelStability.STABLE
                }
                
                missing = expected_channels - channels_visited
                if missing:
                    gaps.append({
                        "rc_id": rc.rc_id,
                        "version": rc.version,
                        "current_channel": rc.channel.value,
                        "missing_channels": [m.value for m in missing]
                    })
        return gaps

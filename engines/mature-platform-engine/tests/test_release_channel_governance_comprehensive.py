import unittest
from datetime import datetime, timezone, timedelta
import uuid

from elmos_mature_platform.types import (
    ChannelStability,
    PromotionVerdict,
    ReleaseCandidate,
    ChannelPolicy
)
from elmos_mature_platform.release_channel_governance_engine import ReleaseChannelGovernanceEngine

class TestReleaseChannelGovernanceEngine(unittest.TestCase):
    
    def setUp(self):
        self.engine = ReleaseChannelGovernanceEngine()
        
    def _create_rc(self, rc_id="rc-1", version="1.0.0", channel=ChannelStability.NIGHTLY):
        rc = ReleaseCandidate(
            rc_id=rc_id,
            version=version,
            channel=channel,
            artifact_digest="sha256:dummy",
            created_at=datetime.now(timezone.utc).isoformat(),
            test_pass_rate=100.0,
            security_scan_clean=True
        )
        return self.engine.create_release_candidate(rc)
        
    # 1-5: Basic creation and policy setting
    def test_set_policy(self):
        policy = ChannelPolicy(channel=ChannelStability.ALPHA, min_test_pass_rate=90.0)
        self.engine.set_channel_policy(policy)
        self.assertEqual(self.engine.policies[ChannelStability.ALPHA].min_test_pass_rate, 90.0)
        
    def test_create_rc(self):
        rc = self._create_rc()
        self.assertEqual(len(self.engine.candidates), 1)
        self.assertEqual(rc.channel, ChannelStability.NIGHTLY)
        
    def test_initial_policies_exist(self):
        for ch in self.engine.CHANNEL_ORDER:
            self.assertIn(ch, self.engine.policies)
            
    def test_get_channel_head_empty(self):
        head = self.engine.get_channel_head(ChannelStability.NIGHTLY)
        self.assertIsNone(head)
        
    def test_get_channel_head_exists(self):
        rc = self._create_rc()
        head = self.engine.get_channel_head(ChannelStability.NIGHTLY)
        self.assertEqual(head.rc_id, rc.rc_id)
        
    # 6-12: Promotion evaluation and order
    def test_eval_promote_valid_next(self):
        rc = self._create_rc()
        rec = self.engine.evaluate_promotion(rc.rc_id, ChannelStability.ALPHA, "actor")
        self.assertEqual(rec.verdict, PromotionVerdict.APPROVED)
        
    def test_eval_promote_skip_channel(self):
        rc = self._create_rc()
        rec = self.engine.evaluate_promotion(rc.rc_id, ChannelStability.BETA, "actor")
        self.assertEqual(rec.verdict, PromotionVerdict.BLOCKED)
        self.assertIn("Cannot promote from", rec.reason)
        
    def test_promote_valid_next(self):
        rc = self._create_rc()
        rec = self.engine.promote(rc.rc_id, ChannelStability.ALPHA, "actor")
        self.assertEqual(rec.verdict, PromotionVerdict.APPROVED)
        self.assertEqual(rc.channel, ChannelStability.ALPHA)
        
    def test_promote_skip_channel(self):
        rc = self._create_rc()
        rec = self.engine.promote(rc.rc_id, ChannelStability.BETA, "actor")
        self.assertEqual(rec.verdict, PromotionVerdict.BLOCKED)
        self.assertEqual(rc.channel, ChannelStability.NIGHTLY)
        
    def test_promote_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.promote("missing", ChannelStability.ALPHA, "actor")
            
    def test_promote_all_the_way(self):
        rc = self._create_rc()
        self.engine.promote(rc.rc_id, ChannelStability.ALPHA, "actor")
        self.engine.promote(rc.rc_id, ChannelStability.BETA, "actor")
        self.engine.promote(rc.rc_id, ChannelStability.RC, "actor")
        self.engine.promote(rc.rc_id, ChannelStability.STABLE, "actor")
        rec = self.engine.promote(rc.rc_id, ChannelStability.LTS, "actor")
        self.assertEqual(rec.verdict, PromotionVerdict.APPROVED)
        self.assertEqual(rc.channel, ChannelStability.LTS)
        
    def test_promote_backwards(self):
        rc = self._create_rc(channel=ChannelStability.ALPHA)
        rec = self.engine.promote(rc.rc_id, ChannelStability.NIGHTLY, "actor")
        self.assertEqual(rec.verdict, PromotionVerdict.BLOCKED)
        
    # 13-18: Policy validations
    def test_policy_test_pass_rate(self):
        rc = self._create_rc()
        rc.test_pass_rate = 90.0
        policy = ChannelPolicy(channel=ChannelStability.ALPHA, min_test_pass_rate=95.0)
        self.engine.set_channel_policy(policy)
        rec = self.engine.promote(rc.rc_id, ChannelStability.ALPHA, "actor")
        self.assertEqual(rec.verdict, PromotionVerdict.BLOCKED)
        
    def test_policy_security_scan(self):
        rc = self._create_rc()
        rc.security_scan_clean = False
        policy = ChannelPolicy(channel=ChannelStability.ALPHA, require_security_scan=True)
        self.engine.set_channel_policy(policy)
        rec = self.engine.promote(rc.rc_id, ChannelStability.ALPHA, "actor")
        self.assertEqual(rec.verdict, PromotionVerdict.BLOCKED)
        
    def test_policy_breaking_changes_zero(self):
        rc = self._create_rc()
        rc.breaking_changes = ["api_v1_removed"]
        policy = ChannelPolicy(channel=ChannelStability.ALPHA, require_zero_breaking_changes=True)
        self.engine.set_channel_policy(policy)
        rec = self.engine.promote(rc.rc_id, ChannelStability.ALPHA, "actor")
        self.assertEqual(rec.verdict, PromotionVerdict.BLOCKED)
        
    def test_breaking_changes_block_stable(self):
        rc = self._create_rc(channel=ChannelStability.RC)
        rc.breaking_changes = ["api_v1_removed"]
        rec = self.engine.promote(rc.rc_id, ChannelStability.STABLE, "actor")
        self.assertEqual(rec.verdict, PromotionVerdict.BLOCKED)
        
    def test_breaking_changes_block_lts(self):
        rc = self._create_rc(channel=ChannelStability.STABLE)
        rc.breaking_changes = ["api_v1_removed"]
        rec = self.engine.promote(rc.rc_id, ChannelStability.LTS, "actor")
        self.assertEqual(rec.verdict, PromotionVerdict.BLOCKED)
        
    def test_policy_soak_time_blocked(self):
        rc = self._create_rc()
        rc.created_at = datetime.now(timezone.utc).isoformat()
        policy = ChannelPolicy(channel=ChannelStability.ALPHA, min_soak_hours=24)
        self.engine.set_channel_policy(policy)
        rec = self.engine.promote(rc.rc_id, ChannelStability.ALPHA, "actor")
        self.assertEqual(rec.verdict, PromotionVerdict.BLOCKED)
        
    def test_policy_soak_time_passed(self):
        rc = self._create_rc()
        past = datetime.now(timezone.utc) - timedelta(hours=25)
        rc.created_at = past.isoformat()
        policy = ChannelPolicy(channel=ChannelStability.ALPHA, min_soak_hours=24)
        self.engine.set_channel_policy(policy)
        rec = self.engine.promote(rc.rc_id, ChannelStability.ALPHA, "actor")
        self.assertEqual(rec.verdict, PromotionVerdict.APPROVED)
        
    # 19-23: Rollbacks
    def test_rollback_not_promoted(self):
        rc = self._create_rc()
        with self.assertRaises(ValueError):
            self.engine.rollback(rc.rc_id, "actor", "bug")
            
    def test_rollback_success(self):
        rc = self._create_rc()
        self.engine.promote(rc.rc_id, ChannelStability.ALPHA, "actor")
        rec = self.engine.rollback(rc.rc_id, "actor", "bug")
        self.assertEqual(rec.verdict, PromotionVerdict.ROLLED_BACK)
        self.assertEqual(rc.channel, ChannelStability.NIGHTLY)
        
    def test_rollback_expired_window(self):
        rc = self._create_rc()
        self.engine.promote(rc.rc_id, ChannelStability.ALPHA, "actor")
        past = datetime.now(timezone.utc) - timedelta(hours=73)
        rc.promoted_at = past.isoformat()
        policy = ChannelPolicy(channel=ChannelStability.ALPHA, max_rollback_window_hours=72)
        self.engine.set_channel_policy(policy)
        with self.assertRaises(ValueError):
            self.engine.rollback(rc.rc_id, "actor", "bug")
            
    def test_rollback_no_window_limit(self):
        rc = self._create_rc()
        self.engine.promote(rc.rc_id, ChannelStability.ALPHA, "actor")
        past = datetime.now(timezone.utc) - timedelta(hours=100)
        rc.promoted_at = past.isoformat()
        policy = ChannelPolicy(channel=ChannelStability.ALPHA, max_rollback_window_hours=0)
        self.engine.set_channel_policy(policy)
        rec = self.engine.rollback(rc.rc_id, "actor", "bug")
        self.assertEqual(rec.verdict, PromotionVerdict.ROLLED_BACK)
        
    # 24-28: Histories and reporting
    def test_get_promotion_history_empty(self):
        self.assertEqual(len(self.engine.get_promotion_history()), 0)
        
    def test_get_promotion_history_filled(self):
        rc = self._create_rc()
        self.engine.promote(rc.rc_id, ChannelStability.ALPHA, "actor")
        self.assertEqual(len(self.engine.get_promotion_history(rc.rc_id)), 1)
        self.assertEqual(len(self.engine.get_promotion_history()), 1)
        
    def test_channel_report(self):
        rc = self._create_rc()
        report = self.engine.get_channel_report()
        self.assertEqual(report["total_rcs"], 1)
        self.assertEqual(report["channels"][ChannelStability.NIGHTLY]["head_rc_id"], rc.rc_id)
        
    def test_detect_version_gaps_none(self):
        rc = self._create_rc()
        self.engine.promote(rc.rc_id, ChannelStability.ALPHA, "actor")
        self.engine.promote(rc.rc_id, ChannelStability.BETA, "actor")
        self.engine.promote(rc.rc_id, ChannelStability.RC, "actor")
        self.engine.promote(rc.rc_id, ChannelStability.STABLE, "actor")
        gaps = self.engine.detect_version_gaps()
        self.assertEqual(len(gaps), 0)
        
    def test_detect_version_gaps_found(self):
        rc = self._create_rc(channel=ChannelStability.STABLE)
        gaps = self.engine.detect_version_gaps()
        self.assertEqual(len(gaps), 1)
        self.assertIn(ChannelStability.ALPHA.value, gaps[0]["missing_channels"])
        
    # 29-32: Edge cases
    def test_check_soak_time_no_rc(self):
        self.assertFalse(self.engine.check_soak_time("missing", datetime.now(timezone.utc).isoformat()))
        
    def test_eval_promote_breaking_changes_not_stable(self):
        rc = self._create_rc()
        rc.breaking_changes = ["api_v1"]
        rec = self.engine.promote(rc.rc_id, ChannelStability.ALPHA, "actor")
        self.assertEqual(rec.verdict, PromotionVerdict.APPROVED)
        
    def test_get_channel_head_multiple(self):
        rc1 = self._create_rc("rc-1")
        rc1.created_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        rc2 = self._create_rc("rc-2")
        head = self.engine.get_channel_head(ChannelStability.NIGHTLY)
        self.assertEqual(head.rc_id, rc2.rc_id)
        
    def test_rollback_to_nightly_stays_nightly(self):
        # wait, if current is nightly, rollback raises error or stays?
        rc = self._create_rc()
        rc.promoted_at = datetime.now(timezone.utc).isoformat()
        # manual mark to test bounds
        rc.channel = ChannelStability.NIGHTLY
        rec = self.engine.rollback(rc.rc_id, "actor", "bug")
        self.assertEqual(rc.channel, ChannelStability.NIGHTLY)
        
if __name__ == '__main__':
    unittest.main()

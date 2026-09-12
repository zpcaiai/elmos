"""Comprehensive tests for RunnerUpdateSupplyChainEngine (Batch 40 - Skill 1385)."""

import hashlib
import unittest

from elmos_mature_platform.runner_update_supply_chain_engine import (
    RunnerUpdateSupplyChainEngine,
)
from elmos_mature_platform.types import (
    RunnerChannel,
    RunnerUpdateStatus,
)


class TestRunnerUpdateSupplyChainComprehensive(unittest.TestCase):
    """Test suite verifying runner binary signing, staged rollouts, and node fleet management."""

    def setUp(self):
        self.engine = RunnerUpdateSupplyChainEngine()
        self.dummy_digest = hashlib.sha256(b"runner_binary_v2.4.0").hexdigest()

    def test_create_release_package(self):
        """Verify registering candidate release in DRAFT state."""
        pkg = self.engine.create_release_package(
            version="2.4.0",
            channel=RunnerChannel.STABLE,
            binary_digest_sha256=self.dummy_digest,
            minimum_agent_version="1.5.0",
        )
        self.assertTrue(pkg.release_id.startswith("rel-sta-"))
        self.assertEqual(pkg.version, "2.4.0")
        self.assertEqual(pkg.channel, RunnerChannel.STABLE)
        self.assertEqual(pkg.status, RunnerUpdateStatus.DRAFT)
        self.assertEqual(pkg.binary_digest_sha256, self.dummy_digest)

    def test_invalid_digest_and_duplicate_release_errors(self):
        """Verify digest length validation and duplicate release detection."""
        with self.assertRaises(ValueError):
            self.engine.create_release_package("1.0.0", RunnerChannel.STABLE, "short_hash")

        self.engine.create_release_package("2.4.1", RunnerChannel.STABLE, self.dummy_digest)
        with self.assertRaises(ValueError):
            self.engine.create_release_package("2.4.1", RunnerChannel.STABLE, self.dummy_digest)

    def test_sign_stage_deploy_lifecycle(self):
        """Verify strict progression: DRAFT -> SIGNED -> STAGED -> DEPLOYED."""
        pkg = self.engine.create_release_package("2.5.0", RunnerChannel.CANARY, self.dummy_digest)

        # Cannot stage before signing
        with self.assertRaises(ValueError):
            self.engine.stage_release(pkg.release_id)

        # Sign release
        signed = self.engine.sign_release(pkg.release_id, signing_key="test-key")
        self.assertEqual(signed.status, RunnerUpdateStatus.SIGNED)
        self.assertTrue(len(signed.signature) > 0)
        self.assertTrue(signed.cosign_attestation_ref.startswith("rekor://"))

        # Stage release
        staged = self.engine.stage_release(pkg.release_id)
        self.assertEqual(staged.status, RunnerUpdateStatus.STAGED)

        # Deploy release
        deployed = self.engine.deploy_release(pkg.release_id)
        self.assertEqual(deployed.status, RunnerUpdateStatus.DEPLOYED)

    def test_revoke_release(self):
        """Verify emergency revocation of release with reason."""
        pkg = self.engine.create_release_package("2.6.0-rc1", RunnerChannel.CANARY, self.dummy_digest)
        revoked = self.engine.revoke_release(pkg.release_id, revocation_reason="CVE-2026-9999 sandbox bypass")
        self.assertEqual(revoked.status, RunnerUpdateStatus.REVOKED)
        self.assertIn("CVE-2026-9999", revoked.revocation_reason)

    def test_fleet_node_update_lifecycle_and_rollout_progress(self):
        """Verify triggering and completing node updates across fleet nodes."""
        # Setup deployed release
        pkg = self.engine.create_release_package("3.0.0", RunnerChannel.STABLE, self.dummy_digest)
        self.engine.sign_release(pkg.release_id)
        self.engine.stage_release(pkg.release_id)
        self.engine.deploy_release(pkg.release_id)

        # Register 2 nodes
        n1 = self.engine.register_fleet_node("node-01", current_version="2.0.0")
        n2 = self.engine.register_fleet_node("node-02", current_version="2.0.0")

        # Initial progress 0%
        prog0 = self.engine.get_fleet_rollout_progress("3.0.0")
        self.assertEqual(prog0["rollout_percentage"], 0.0)

        # Trigger update on node-01
        self.engine.trigger_node_update(n1.node_id, pkg.release_id)
        self.assertTrue(n1.update_in_progress)

        # Complete update on node-01 successfully
        self.engine.complete_node_update(n1.node_id, success=True)
        self.assertFalse(n1.update_in_progress)
        self.assertEqual(n1.current_version, "3.0.0")

        # Progress now 50%
        prog1 = self.engine.get_fleet_rollout_progress("3.0.0")
        self.assertEqual(prog1["rollout_percentage"], 50.0)
        self.assertEqual(prog1["upgraded_nodes"], 1)

        # Node-02 fails update
        self.engine.trigger_node_update(n2.node_id, pkg.release_id)
        self.engine.complete_node_update(n2.node_id, success=False)
        self.assertTrue(n2.update_failed)
        self.assertEqual(n2.current_version, "2.0.0")


if __name__ == "__main__":
    unittest.main()

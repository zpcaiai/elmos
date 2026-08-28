import unittest
from reference_kernel.elmos_ai_factory.capability import FeatureRequirement, TargetProfile, negotiate

class CapabilityTests(unittest.TestCase):
    def profile(self, features, version="1.0.0", digest="sha256:" + "a"*64):
        return TargetProfile("target", features, version, digest)

    def test_supported_target(self):
        r = negotiate([FeatureRequirement("durable")], [self.profile({"durable":"supported"})])
        self.assertEqual("SUPPORTED", r.overall)
        self.assertEqual("SUPPORTED", r.targets[0].overall)

    def test_external_policy_is_bounded(self):
        r = negotiate([FeatureRequirement("approval")], [self.profile({"approval":"external-policy"})])
        self.assertEqual("BOUNDED", r.overall)
        self.assertIn("policy-enforcement:approval", r.targets[0].decisions[0].obligations)

    def test_critical_unsupported_blocks(self):
        r = negotiate([FeatureRequirement("durable")], [self.profile({"durable":"unsupported"})])
        self.assertEqual("BLOCKED", r.overall)

    def test_missing_release_pin_blocks(self):
        r = negotiate([FeatureRequirement("durable")], [self.profile({"durable":"supported"}, version="", digest="")])
        self.assertEqual("BLOCKED", r.overall)
        self.assertTrue(r.blocked_reasons)

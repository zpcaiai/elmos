import unittest
from datetime import datetime, timedelta, timezone
from elmos_mature_platform.types import (
    OfflineBundle,
    BundleArtifact,
    BundleArtifactType,
    OfflineBundleStatus as BundleStatus
)
from elmos_mature_platform.offline_signed_bundle_engine import OfflineSignedBundleEngine

class TestOfflineSignedBundleEngine(unittest.TestCase):
    def setUp(self):
        self.engine = OfflineSignedBundleEngine()
        
    def test_create_bundle(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        bid = self.engine.create_bundle(bundle)
        self.assertEqual(bid, "b1")
        self.assertEqual(self.engine.bundles["b1"].status, BundleStatus.DRAFT)
        
    def test_add_artifact(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        art = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.CONTAINER_IMAGE, name="img", version="1", size_bytes=100)
        res = self.engine.add_artifact("b1", art)
        self.assertIn("a1", res.artifacts)
        self.assertEqual(res.total_size_bytes, 100)
        
    def test_add_artifact_fails_not_found(self):
        art = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.BINARY, name="bin", version="1")
        with self.assertRaises(ValueError):
            self.engine.add_artifact("nonexistent", art)
            
    def test_add_artifact_fails_wrong_status(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        self.engine.bundles["b1"].status = BundleStatus.BUILDING
        art = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.BINARY, name="bin", version="1")
        with self.assertRaises(ValueError):
            self.engine.add_artifact("b1", art)
            
    def test_set_install_order(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        art1 = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.BINARY, name="bin", version="1")
        art2 = BundleArtifact(artifact_id="a2", artifact_type=BundleArtifactType.BINARY, name="bin", version="1")
        self.engine.add_artifact("b1", art1)
        self.engine.add_artifact("b1", art2)
        res = self.engine.set_install_order("b1", ["a2", "a1"])
        self.assertEqual(res.install_order, ["a2", "a1"])
        
    def test_set_install_order_missing_artifact(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        with self.assertRaises(ValueError):
            self.engine.set_install_order("b1", ["missing"])
            
    def test_build_bundle(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        art = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.BINARY, name="bin", version="1", size_bytes=50)
        self.engine.add_artifact("b1", art)
        res = self.engine.build_bundle("b1")
        self.assertEqual(res.status, BundleStatus.BUILDING)
        self.assertEqual(res.total_size_bytes, 50)
        
    def test_build_bundle_no_artifacts(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        with self.assertRaises(ValueError):
            self.engine.build_bundle("b1")
            
    def test_sign_bundle(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        art = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.BINARY, name="bin", version="1", size_bytes=50)
        self.engine.add_artifact("b1", art)
        self.engine.build_bundle("b1")
        res = self.engine.sign_bundle("b1", "signer-1")
        self.assertEqual(res.status, BundleStatus.SIGNED)
        self.assertIsNotNone(res.bundle_signature)
        
    def test_sign_bundle_wrong_status(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        with self.assertRaises(ValueError):
            self.engine.sign_bundle("b1", "signer-1")
            
    def test_verify_bundle_signature_valid(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        art = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.BINARY, name="bin", version="1", size_bytes=50, sha256_digest="abc")
        self.engine.add_artifact("b1", art)
        self.engine.build_bundle("b1")
        self.engine.sign_bundle("b1", "signer-1")
        res = self.engine.verify_bundle_signature("b1")
        self.assertTrue(res["valid"])
        
    def test_verify_bundle_signature_missing_digest(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        art = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.BINARY, name="bin", version="1", size_bytes=50)
        self.engine.add_artifact("b1", art)
        self.engine.build_bundle("b1")
        self.engine.sign_bundle("b1", "signer-1")
        res = self.engine.verify_bundle_signature("b1")
        self.assertFalse(res["valid"])
        
    def test_verify_bundle_signature_expired(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        art = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.BINARY, name="bin", version="1", size_bytes=50, sha256_digest="abc")
        self.engine.add_artifact("b1", art)
        self.engine.build_bundle("b1")
        self.engine.sign_bundle("b1", "signer-1", expiry_days=-1)
        res = self.engine.verify_bundle_signature("b1")
        self.assertFalse(res["valid"])
        
    def test_distribute_bundle(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        art = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.BINARY, name="bin", version="1", size_bytes=50, sha256_digest="abc")
        self.engine.add_artifact("b1", art)
        self.engine.build_bundle("b1")
        self.engine.sign_bundle("b1", "signer-1")
        res = self.engine.distribute_bundle("b1", "prod")
        self.assertEqual(res.status, BundleStatus.DISTRIBUTING)
        self.assertIn("prod", res.target_environments)
        
    def test_distribute_bundle_wrong_status(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        with self.assertRaises(ValueError):
            self.engine.distribute_bundle("b1", "prod")
            
    def test_install_bundle(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        art = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.BINARY, name="bin", version="1", size_bytes=50, sha256_digest="abc")
        self.engine.add_artifact("b1", art)
        self.engine.set_install_order("b1", ["a1"])
        self.engine.build_bundle("b1")
        self.engine.sign_bundle("b1", "signer-1")
        self.engine.distribute_bundle("b1", "prod")
        res = self.engine.install_bundle("b1", "prod")
        self.assertEqual(res["status"], "installed")
        self.assertEqual(self.engine.bundles["b1"].status, BundleStatus.INSTALLED)
        
    def test_install_bundle_revoked(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        self.engine.bundles["b1"].status = BundleStatus.REVOKED
        with self.assertRaises(ValueError):
            self.engine.install_bundle("b1", "prod")
            
    def test_install_bundle_no_install_order(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        art = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.BINARY, name="bin", version="1", size_bytes=50, sha256_digest="abc")
        self.engine.add_artifact("b1", art)
        self.engine.build_bundle("b1")
        self.engine.sign_bundle("b1", "signer-1")
        with self.assertRaises(ValueError):
            self.engine.install_bundle("b1", "prod")
            
    def test_revoke_bundle(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        res = self.engine.revoke_bundle("b1", "compromised")
        self.assertEqual(res.status, BundleStatus.REVOKED)
        
    def test_get_bundle_manifest(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        art = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.BINARY, name="bin", version="1", size_bytes=50, sha256_digest="abc")
        self.engine.add_artifact("b1", art)
        self.engine.set_install_order("b1", ["a1"])
        self.engine.build_bundle("b1")
        self.engine.sign_bundle("b1", "signer-1")
        manifest = self.engine.get_bundle_manifest("b1")
        self.assertEqual(manifest["bundle"]["bundle_id"], "b1")
        self.assertEqual(len(manifest["artifacts"]), 1)
        self.assertEqual(manifest["install_order"], ["a1"])
        
    def test_get_bundle_report(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        art = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.BINARY, name="bin", version="1", size_bytes=50, sha256_digest="abc")
        self.engine.add_artifact("b1", art)
        self.engine.build_bundle("b1")
        self.engine.sign_bundle("b1", "signer-1")
        
        bundle2 = OfflineBundle(bundle_id="b2", name="v2.0", target_version="2.0.0")
        self.engine.create_bundle(bundle2)
        
        report = self.engine.get_bundle_report()
        self.assertEqual(report["total_bundles"], 2)
        self.assertEqual(report["signed_bundles"], 1)
        self.assertEqual(report["unsigned_bundles"], 1)
        
    def test_verify_bundle_signature_wrong_status(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        res = self.engine.verify_bundle_signature("b1")
        self.assertFalse(res["valid"])
        
    def test_verify_bundle_signature_missing_sig(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        self.engine.bundles["b1"].status = BundleStatus.SIGNED
        res = self.engine.verify_bundle_signature("b1")
        self.assertFalse(res["valid"])
        
    def test_verify_bundle_signature_mismatch(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        art = BundleArtifact(artifact_id="a1", artifact_type=BundleArtifactType.BINARY, name="bin", version="1", size_bytes=50, sha256_digest="abc")
        self.engine.add_artifact("b1", art)
        self.engine.build_bundle("b1")
        self.engine.sign_bundle("b1", "signer-1")
        self.engine.bundles["b1"].bundle_signature = "bad"
        res = self.engine.verify_bundle_signature("b1")
        self.assertFalse(res["valid"])
        
    def test_build_bundle_wrong_status(self):
        bundle = OfflineBundle(bundle_id="b1", name="v1.0", target_version="1.0.0")
        self.engine.create_bundle(bundle)
        self.engine.bundles["b1"].status = BundleStatus.SIGNED
        with self.assertRaises(ValueError):
            self.engine.build_bundle("b1")

    def test_set_install_order_wrong_bundle(self):
        with self.assertRaises(ValueError):
            self.engine.set_install_order("b1", ["a1"])

    def test_build_bundle_wrong_bundle(self):
        with self.assertRaises(ValueError):
            self.engine.build_bundle("b1")

    def test_sign_bundle_wrong_bundle(self):
        with self.assertRaises(ValueError):
            self.engine.sign_bundle("b1", "signer-1")

    def test_distribute_bundle_wrong_bundle(self):
        with self.assertRaises(ValueError):
            self.engine.distribute_bundle("b1", "prod")

    def test_install_bundle_wrong_bundle(self):
        with self.assertRaises(ValueError):
            self.engine.install_bundle("b1", "prod")
            
    def test_verify_bundle_signature_wrong_bundle(self):
        with self.assertRaises(ValueError):
            self.engine.verify_bundle_signature("b1")
            
    def test_revoke_bundle_wrong_bundle(self):
        with self.assertRaises(ValueError):
            self.engine.revoke_bundle("b1", "reason")

    def test_get_bundle_manifest_wrong_bundle(self):
        with self.assertRaises(ValueError):
            self.engine.get_bundle_manifest("b1")

if __name__ == "__main__":
    unittest.main()

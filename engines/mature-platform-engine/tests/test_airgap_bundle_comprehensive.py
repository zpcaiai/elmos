import unittest
from datetime import datetime, timedelta
from elmos_mature_platform.types import (
    AirgapBundle,
    BundleComponent,
    BundleComponentType,
    BundleStatus
)
from elmos_mature_platform.airgap_bundle_engine import AirgapBundleEngine

class TestAirgapBundleComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = AirgapBundleEngine()

    def test_create_bundle_success(self):
        bundle = AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise")
        bundle_id = self.engine.create_bundle(bundle)
        self.assertEqual(bundle_id, "b1")
        listed = self.engine.list_bundles()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].status, BundleStatus.BUILDING)
        self.assertNotEqual(listed[0].created_at, "")

    def test_create_bundle_duplicate(self):
        bundle1 = AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise")
        self.engine.create_bundle(bundle1)
        bundle2 = AirgapBundle(bundle_id="b1", target_version="1.1.0", target_edition="enterprise")
        with self.assertRaises(ValueError):
            self.engine.create_bundle(bundle2)

    def test_add_component_success(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            size_bytes=100,
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        bundles = self.engine.list_bundles()
        self.assertEqual(len(bundles[0].components), 1)

    def test_add_component_invalid_bundle(self):
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0"
        )
        with self.assertRaises(ValueError):
            self.engine.add_component("invalid", comp)

    def test_add_component_wrong_status(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        self.engine.finalize_bundle("b1")
        comp2 = BundleComponent(
            component_id="c2",
            component_type=BundleComponentType.BINARY,
            name="cli",
            version="1.0.0",
            checksum_sha256="def"
        )
        with self.assertRaises(ValueError):
            self.engine.add_component("b1", comp2)

    def test_finalize_bundle_success(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        comp1 = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            size_bytes=100,
            checksum_sha256="abc"
        )
        comp2 = BundleComponent(
            component_id="c2",
            component_type=BundleComponentType.BINARY,
            name="cli",
            version="1.0.0",
            size_bytes=200,
            checksum_sha256="def"
        )
        self.engine.add_component("b1", comp1)
        self.engine.add_component("b1", comp2)
        bundle = self.engine.finalize_bundle("b1")
        self.assertEqual(bundle.status, BundleStatus.READY)
        self.assertEqual(bundle.total_size_bytes, 300)
        self.assertTrue(bool(bundle.manifest_digest))

    def test_finalize_bundle_missing_checksum(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            size_bytes=100
        )
        self.engine.add_component("b1", comp)
        with self.assertRaises(ValueError):
            self.engine.finalize_bundle("b1")

    def test_finalize_bundle_wrong_status(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        self.engine.finalize_bundle("b1")
        with self.assertRaises(ValueError):
            self.engine.finalize_bundle("b1")

    def test_sign_bundle_success(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        self.engine.finalize_bundle("b1")
        bundle = self.engine.sign_bundle("b1", "key-123")
        self.assertEqual(bundle.status, BundleStatus.SIGNED)
        self.assertEqual(bundle.signing_key_id, "key-123")

    def test_sign_bundle_not_ready(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        with self.assertRaises(ValueError):
            self.engine.sign_bundle("b1", "key-123")

    def test_verify_bundle_success(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        self.engine.finalize_bundle("b1")
        self.engine.sign_bundle("b1", "key-123")
        ver = self.engine.verify_bundle("b1")
        self.assertTrue(ver.overall_valid)

    def test_verify_bundle_building(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        ver = self.engine.verify_bundle("b1")
        self.assertFalse(ver.overall_valid)
        self.assertIn("Bundle is still BUILDING", ver.errors[0])

    def test_verify_bundle_expired(self):
        past = (datetime.utcnow() - timedelta(days=1)).isoformat()
        bundle = AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise", expiry_date=past)
        self.engine.create_bundle(bundle)
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        self.engine.finalize_bundle("b1")
        self.engine.sign_bundle("b1", "key-123")
        ver = self.engine.verify_bundle("b1")
        self.assertFalse(ver.overall_valid)
        self.assertFalse(ver.not_expired)

    def test_verify_bundle_no_components(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        # Hack to finalize a bundle without components for test
        b = self.engine._bundles["b1"]
        b.status = BundleStatus.READY
        b.manifest_digest = "foo"
        self.engine.sign_bundle("b1", "key-123")
        ver = self.engine.verify_bundle("b1")
        self.assertFalse(ver.overall_valid)
        self.assertFalse(ver.all_components_present)

    def test_verify_bundle_revoked(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        self.engine.finalize_bundle("b1")
        self.engine.sign_bundle("b1", "key-123")
        self.engine.revoke_bundle("b1", "compromised")
        ver = self.engine.verify_bundle("b1")
        self.assertFalse(ver.overall_valid)

    def test_deploy_bundle_success(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        self.engine.finalize_bundle("b1")
        self.engine.sign_bundle("b1", "key-123")
        bundle = self.engine.deploy_bundle("b1")
        self.assertEqual(bundle.status, BundleStatus.DEPLOYED)
        self.assertTrue(bool(bundle.deployed_at))

    def test_deploy_bundle_not_signed(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        self.engine.finalize_bundle("b1")
        with self.assertRaises(ValueError):
            self.engine.deploy_bundle("b1")

    def test_deploy_bundle_revoked(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        self.engine.finalize_bundle("b1")
        self.engine.sign_bundle("b1", "key-123")
        self.engine.revoke_bundle("b1", "reason")
        with self.assertRaises(ValueError):
            self.engine.deploy_bundle("b1")

    def test_deploy_invalid_bundle(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        self.engine.finalize_bundle("b1")
        self.engine.sign_bundle("b1", "key-123")
        # Tamper manifest
        self.engine._bundles["b1"].manifest_digest = "tampered"
        with self.assertRaises(ValueError):
            self.engine.deploy_bundle("b1")

    def test_revoke_bundle_success(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        self.engine.revoke_bundle("b1", "compromised")
        self.assertEqual(self.engine._bundles["b1"].status, BundleStatus.REVOKED)

    def test_revoke_deployed_bundle(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        self.engine.finalize_bundle("b1")
        self.engine.sign_bundle("b1", "key-123")
        self.engine.deploy_bundle("b1")
        with self.assertRaises(ValueError):
            self.engine.revoke_bundle("b1", "compromised")

    def test_check_upgrade_path(self):
        bundle = AirgapBundle(bundle_id="b1", target_version="2.0.0", target_edition="enterprise", upgrade_from_version="1.0.0")
        self.engine.create_bundle(bundle)
        self.assertTrue(self.engine.check_upgrade_path("1.0.0", "2.0.0"))
        self.assertFalse(self.engine.check_upgrade_path("1.0.0", "3.0.0"))

    def test_list_bundles(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        self.engine.create_bundle(AirgapBundle(bundle_id="b2", target_version="1.0.0", target_edition="enterprise"))
        
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        self.engine.finalize_bundle("b1")
        
        self.assertEqual(len(self.engine.list_bundles()), 2)
        self.assertEqual(len(self.engine.list_bundles(BundleStatus.READY)), 1)
        self.assertEqual(len(self.engine.list_bundles(BundleStatus.BUILDING)), 1)

    def test_get_bundle_report(self):
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise"))
        self.engine.create_bundle(AirgapBundle(bundle_id="b2", target_version="1.0.0", target_edition="enterprise"))
        
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc",
            size_bytes=500
        )
        self.engine.add_component("b1", comp)
        self.engine.finalize_bundle("b1")
        self.engine.sign_bundle("b1", "key-1")
        
        report = self.engine.get_bundle_report()
        self.assertEqual(report["total_bundles"], 2)
        self.assertEqual(report["total_size_bytes"], 500)
        self.assertEqual(report["signed_count"], 1)
        self.assertEqual(report["by_status"][BundleStatus.READY.value], 0)
        self.assertEqual(report["by_status"][BundleStatus.SIGNED.value], 1)
        self.assertEqual(report["by_status"][BundleStatus.BUILDING.value], 1)

    def test_expire_bundles(self):
        past = (datetime.utcnow() - timedelta(days=1)).isoformat()
        future = (datetime.utcnow() + timedelta(days=1)).isoformat()
        current = datetime.utcnow().isoformat()
        
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise", expiry_date=past))
        self.engine.create_bundle(AirgapBundle(bundle_id="b2", target_version="1.0.0", target_edition="enterprise", expiry_date=future))
        
        expired = self.engine.expire_bundles(current)
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0], "b1")
        
        self.assertEqual(self.engine._bundles["b1"].status, BundleStatus.EXPIRED)
        self.assertEqual(self.engine._bundles["b2"].status, BundleStatus.BUILDING)

    def test_expire_bundles_invalid_date(self):
        with self.assertRaises(ValueError):
            self.engine.expire_bundles("invalid-date")

    def test_expire_bundles_ignores_deployed(self):
        future = (datetime.utcnow() + timedelta(days=1)).isoformat()
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise", expiry_date=future))
        
        comp = BundleComponent(
            component_id="c1",
            component_type=BundleComponentType.CONTAINER_IMAGE,
            name="app-image",
            version="1.0.0",
            checksum_sha256="abc"
        )
        self.engine.add_component("b1", comp)
        self.engine.finalize_bundle("b1")
        self.engine.sign_bundle("b1", "key-1")
        self.engine.deploy_bundle("b1")
        
        # Now artificially set it to the past to test if expire_bundles ignores it
        past = (datetime.utcnow() - timedelta(days=1)).isoformat()
        self.engine._bundles["b1"].expiry_date = past
        
        expired = self.engine.expire_bundles(datetime.utcnow().isoformat())
        self.assertEqual(len(expired), 0)
        self.assertEqual(self.engine._bundles["b1"].status, BundleStatus.DEPLOYED)

    def test_expire_bundles_ignores_revoked(self):
        past = (datetime.utcnow() - timedelta(days=1)).isoformat()
        self.engine.create_bundle(AirgapBundle(bundle_id="b1", target_version="1.0.0", target_edition="enterprise", expiry_date=past))
        self.engine.revoke_bundle("b1", "reason")
        
        expired = self.engine.expire_bundles(datetime.utcnow().isoformat())
        self.assertEqual(len(expired), 0)
        self.assertEqual(self.engine._bundles["b1"].status, BundleStatus.REVOKED)

if __name__ == '__main__':
    unittest.main()

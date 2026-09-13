import unittest
import uuid
from typing import Dict, List, Optional
from elmos_mature_platform.knowledge_marketplace_engine import KnowledgeMarketplaceEngine
from elmos_mature_platform.types import (
    KnowledgeAsset,
    KnowledgeAssetType,
    AssetQualityTier,
    SharingScope,
    AssetReview,
    AssetUsageRecord
)

class TestKnowledgeMarketplaceComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = KnowledgeMarketplaceEngine()
        self.tenant_a = "tenant_a"
        self.tenant_b = "tenant_b"

    def create_dummy_asset(self, asset_id: str, owner: str, scope: SharingScope = SharingScope.PRIVATE) -> KnowledgeAsset:
        return KnowledgeAsset(
            asset_id=asset_id,
            name=f"Asset {asset_id}",
            asset_type=KnowledgeAssetType.PATTERN,
            sharing_scope=scope,
            owner_tenant_id=owner,
            tags=["test", "dummy"]
        )

    def test_01_publish_asset_success(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        result = self.engine.publish_asset(asset)
        self.assertEqual(result.asset_id, "a1")

    def test_02_publish_asset_duplicate(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        self.engine.publish_asset(asset)
        with self.assertRaises(ValueError):
            self.engine.publish_asset(asset)

    def test_03_get_asset_success(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        self.engine.publish_asset(asset)
        result = self.engine.get_asset("a1")
        self.assertEqual(result.asset_id, "a1")

    def test_04_get_asset_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_asset("missing")

    def test_05_search_assets_by_name(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        asset.name = "UniqueName123"
        self.engine.publish_asset(asset)
        results = self.engine.search_assets("uniquename")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].asset_id, "a1")

    def test_06_search_assets_by_tag(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        asset.tags = ["specialtag"]
        self.engine.publish_asset(asset)
        results = self.engine.search_assets("special")
        self.assertEqual(len(results), 1)

    def test_07_search_assets_by_description(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        asset.description = "This is a wonderful asset"
        self.engine.publish_asset(asset)
        results = self.engine.search_assets("wonderful")
        self.assertEqual(len(results), 1)

    def test_08_search_assets_with_type_filter(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        asset.asset_type = KnowledgeAssetType.RECIPE
        self.engine.publish_asset(asset)
        results = self.engine.search_assets("asset", asset_type=KnowledgeAssetType.RECIPE)
        self.assertEqual(len(results), 1)
        results2 = self.engine.search_assets("asset", asset_type=KnowledgeAssetType.PATTERN)
        self.assertEqual(len(results2), 0)

    def test_09_search_assets_with_scope_filter(self):
        asset = self.create_dummy_asset("a1", self.tenant_a, SharingScope.PUBLIC)
        self.engine.publish_asset(asset)
        results = self.engine.search_assets("asset", scope=SharingScope.PUBLIC)
        self.assertEqual(len(results), 1)
        results2 = self.engine.search_assets("asset", scope=SharingScope.PRIVATE)
        self.assertEqual(len(results2), 0)

    def test_10_review_asset_success(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        self.engine.publish_asset(asset)
        review = AssetReview("r1", "a1", self.tenant_b, 4.0, "Good")
        self.engine.review_asset(review)
        a = self.engine.get_asset("a1")
        self.assertEqual(a.rating, 4.0)
        self.assertEqual(a.rating_count, 1)

    def test_11_review_asset_multiple(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        self.engine.publish_asset(asset)
        self.engine.review_asset(AssetReview("r1", "a1", self.tenant_b, 4.0, "Good"))
        self.engine.review_asset(AssetReview("r2", "a1", "tenant_c", 2.0, "Bad"))
        a = self.engine.get_asset("a1")
        self.assertEqual(a.rating, 3.0)
        self.assertEqual(a.rating_count, 2)

    def test_12_review_asset_self_review(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        self.engine.publish_asset(asset)
        review = AssetReview("r1", "a1", self.tenant_a, 5.0, "Perfect")
        with self.assertRaises(ValueError):
            self.engine.review_asset(review)

    def test_13_review_asset_invalid_rating(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        self.engine.publish_asset(asset)
        review = AssetReview("r1", "a1", self.tenant_b, 6.0, "Too good")
        with self.assertRaises(ValueError):
            self.engine.review_asset(review)

    def test_14_review_asset_not_found(self):
        review = AssetReview("r1", "missing", self.tenant_b, 4.0, "Good")
        with self.assertRaises(ValueError):
            self.engine.review_asset(review)

    def test_15_promote_quality_success(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        self.engine.publish_asset(asset)
        self.engine.promote_quality("a1", AssetQualityTier.REVIEWED, self.tenant_b)
        a = self.engine.get_asset("a1")
        self.assertEqual(a.quality_tier, AssetQualityTier.REVIEWED)

    def test_16_promote_quality_skip_tier(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        self.engine.publish_asset(asset)
        self.engine.promote_quality("a1", AssetQualityTier.CERTIFIED, self.tenant_b)
        a = self.engine.get_asset("a1")
        self.assertEqual(a.quality_tier, AssetQualityTier.CERTIFIED)

    def test_17_promote_quality_demote_fails(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        asset.quality_tier = AssetQualityTier.CERTIFIED
        self.engine.publish_asset(asset)
        with self.assertRaises(ValueError):
            self.engine.promote_quality("a1", AssetQualityTier.REVIEWED, self.tenant_b)

    def test_18_promote_quality_deprecated_fails(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        asset.quality_tier = AssetQualityTier.DEPRECATED
        self.engine.publish_asset(asset)
        with self.assertRaises(ValueError):
            self.engine.promote_quality("a1", AssetQualityTier.CERTIFIED, self.tenant_b)

    def test_19_promote_quality_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.promote_quality("missing", AssetQualityTier.REVIEWED, self.tenant_b)

    def test_20_deprecate_asset(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        self.engine.publish_asset(asset)
        self.engine.deprecate_asset("a1", "obsolete")
        a = self.engine.get_asset("a1")
        self.assertEqual(a.quality_tier, AssetQualityTier.DEPRECATED)

    def test_21_deprecate_asset_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.deprecate_asset("missing", "obsolete")

    def test_22_record_usage_success(self):
        asset = self.create_dummy_asset("a1", self.tenant_a)
        self.engine.publish_asset(asset)
        self.engine.record_usage(AssetUsageRecord("a1", self.tenant_b, "2023-01-01"))
        a = self.engine.get_asset("a1")
        self.assertEqual(a.usage_count, 1)

    def test_23_record_usage_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.record_usage(AssetUsageRecord("missing", self.tenant_b, "2023-01-01"))

    def test_24_get_popular_assets(self):
        for i in range(5):
            asset = self.create_dummy_asset(f"a{i}", self.tenant_a)
            self.engine.publish_asset(asset)
            for _ in range(i):
                self.engine.record_usage(AssetUsageRecord(f"a{i}", self.tenant_b, "2023-01-01"))
        
        popular = self.engine.get_popular_assets(3)
        self.assertEqual(len(popular), 3)
        self.assertEqual(popular[0].asset_id, "a4")
        self.assertEqual(popular[1].asset_id, "a3")
        self.assertEqual(popular[2].asset_id, "a2")

    def test_25_get_tenant_assets(self):
        self.engine.publish_asset(self.create_dummy_asset("a1", self.tenant_a))
        self.engine.publish_asset(self.create_dummy_asset("a2", self.tenant_a))
        self.engine.publish_asset(self.create_dummy_asset("b1", self.tenant_b))
        
        assets_a = self.engine.get_tenant_assets(self.tenant_a)
        self.assertEqual(len(assets_a), 2)
        assets_b = self.engine.get_tenant_assets(self.tenant_b)
        self.assertEqual(len(assets_b), 1)

    def test_26_check_access_public(self):
        asset = self.create_dummy_asset("a1", self.tenant_a, SharingScope.PUBLIC)
        self.engine.publish_asset(asset)
        self.assertTrue(self.engine.check_access("a1", self.tenant_b))

    def test_27_check_access_private_owner(self):
        asset = self.create_dummy_asset("a1", self.tenant_a, SharingScope.PRIVATE)
        self.engine.publish_asset(asset)
        self.assertTrue(self.engine.check_access("a1", self.tenant_a))

    def test_28_check_access_private_other(self):
        asset = self.create_dummy_asset("a1", self.tenant_a, SharingScope.PRIVATE)
        self.engine.publish_asset(asset)
        self.assertFalse(self.engine.check_access("a1", self.tenant_b))

    def test_29_check_access_not_found(self):
        self.assertFalse(self.engine.check_access("missing", self.tenant_a))

    def test_30_get_marketplace_report(self):
        self.engine.publish_asset(self.create_dummy_asset("a1", self.tenant_a))
        self.engine.publish_asset(self.create_dummy_asset("a2", self.tenant_a))
        report = self.engine.get_marketplace_report()
        self.assertEqual(report["total_assets"], 2)
        self.assertIn("by_type", report)
        self.assertIn("by_tier", report)
        self.assertIn("top_rated", report)
        self.assertIn("most_used", report)

    def test_31_clone_asset_success(self):
        asset = self.create_dummy_asset("a1", self.tenant_a, SharingScope.PUBLIC)
        self.engine.publish_asset(asset)
        cloned = self.engine.clone_asset("a1", self.tenant_b)
        self.assertTrue(cloned.asset_id.startswith("clone-"))
        self.assertEqual(cloned.owner_tenant_id, self.tenant_b)
        self.assertEqual(cloned.sharing_scope, SharingScope.PRIVATE)

    def test_32_clone_asset_no_access(self):
        asset = self.create_dummy_asset("a1", self.tenant_a, SharingScope.PRIVATE)
        self.engine.publish_asset(asset)
        with self.assertRaises(PermissionError):
            self.engine.clone_asset("a1", self.tenant_b)

if __name__ == '__main__':
    unittest.main()

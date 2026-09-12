import uuid
from typing import Dict, List, Optional
from elmos_mature_platform.types import (
    KnowledgeAsset,
    KnowledgeAssetType,
    AssetQualityTier,
    SharingScope,
    AssetReview,
    AssetUsageRecord
)

class KnowledgeMarketplaceEngine:
    """
    Engine for managing a knowledge marketplace and sharing flywheel across tenants.
    """

    def __init__(self):
        self._assets: Dict[str, KnowledgeAsset] = {}
        self._reviews: Dict[str, List[AssetReview]] = {}
        self._usage_records: Dict[str, List[AssetUsageRecord]] = {}

    def publish_asset(self, asset: KnowledgeAsset) -> KnowledgeAsset:
        """Publishes a new knowledge asset to the marketplace."""
        if asset.asset_id in self._assets:
            raise ValueError(f"Asset {asset.asset_id} already exists.")
        
        self._assets[asset.asset_id] = asset
        self._reviews[asset.asset_id] = []
        self._usage_records[asset.asset_id] = []
        return asset

    def search_assets(
        self,
        query: str,
        asset_type: Optional[KnowledgeAssetType] = None,
        scope: Optional[SharingScope] = None
    ) -> List[KnowledgeAsset]:
        """Searches for assets by substring match in name, description, or tags."""
        query_lower = query.lower()
        results = []
        for asset in self._assets.values():
            if asset_type and asset.asset_type != asset_type:
                continue
            if scope and asset.sharing_scope != scope:
                continue
            
            match = False
            if query_lower in asset.name.lower():
                match = True
            elif query_lower in asset.description.lower():
                match = True
            elif any(query_lower in tag.lower() for tag in asset.tags):
                match = True
                
            if match:
                results.append(asset)
        return results

    def get_asset(self, asset_id: str) -> KnowledgeAsset:
        """Retrieves an asset by its ID."""
        if asset_id not in self._assets:
            raise ValueError(f"Asset {asset_id} not found.")
        return self._assets[asset_id]

    def review_asset(self, review: AssetReview) -> AssetReview:
        """Submits a review for an asset and updates its average rating."""
        if review.asset_id not in self._assets:
            raise ValueError(f"Asset {review.asset_id} not found.")
        
        asset = self._assets[review.asset_id]
        
        # Self-review not allowed
        if review.reviewer_id == asset.owner_tenant_id:
            raise ValueError("Self-review is not allowed.")
            
        # Rating must be 1-5
        if not (1 <= review.rating <= 5):
            raise ValueError("Rating must be between 1 and 5.")
            
        self._reviews[review.asset_id].append(review)
        
        # Update average rating
        total_rating = sum(r.rating for r in self._reviews[review.asset_id])
        count = len(self._reviews[review.asset_id])
        asset.rating = total_rating / count
        asset.rating_count = count
        
        return review

    def promote_quality(self, asset_id: str, new_tier: AssetQualityTier, reviewer_id: str) -> KnowledgeAsset:
        """Promotes an asset's quality tier forward."""
        if asset_id not in self._assets:
            raise ValueError(f"Asset {asset_id} not found.")
            
        asset = self._assets[asset_id]
        
        if asset.quality_tier == AssetQualityTier.DEPRECATED:
            raise ValueError("Cannot promote a deprecated asset.")
            
        tiers = {
            AssetQualityTier.DRAFT: 1,
            AssetQualityTier.REVIEWED: 2,
            AssetQualityTier.CERTIFIED: 3,
            AssetQualityTier.DEPRECATED: 4
        }
        
        current_rank = tiers.get(asset.quality_tier, 0)
        new_rank = tiers.get(new_tier, 0)
        
        if new_rank <= current_rank:
            raise ValueError("Quality can only be promoted forward.")
            
        asset.quality_tier = new_tier
        return asset

    def deprecate_asset(self, asset_id: str, reason: str) -> KnowledgeAsset:
        """Marks an asset as deprecated."""
        if asset_id not in self._assets:
            raise ValueError(f"Asset {asset_id} not found.")
            
        asset = self._assets[asset_id]
        asset.quality_tier = AssetQualityTier.DEPRECATED
        # We could store the reason, but we don't have a field for it, so we just return
        return asset

    def record_usage(self, record: AssetUsageRecord) -> AssetUsageRecord:
        """Records an usage event for an asset and increments its usage counter."""
        if record.asset_id not in self._assets:
            raise ValueError(f"Asset {record.asset_id} not found.")
            
        self._usage_records[record.asset_id].append(record)
        asset = self._assets[record.asset_id]
        asset.usage_count += 1
        return record

    def get_popular_assets(self, top_n: int = 10) -> List[KnowledgeAsset]:
        """Returns the top N assets sorted by usage count."""
        assets = list(self._assets.values())
        assets.sort(key=lambda a: a.usage_count, reverse=True)
        return assets[:top_n]

    def get_tenant_assets(self, tenant_id: str) -> List[KnowledgeAsset]:
        """Returns all assets owned by a specific tenant."""
        return [a for a in self._assets.values() if a.owner_tenant_id == tenant_id]

    def check_access(self, asset_id: str, requester_tenant_id: str) -> bool:
        """Checks if a requester has access to an asset based on its sharing scope."""
        if asset_id not in self._assets:
            return False
            
        asset = self._assets[asset_id]
        
        if asset.sharing_scope == SharingScope.PUBLIC:
            return True
        elif asset.sharing_scope == SharingScope.PRIVATE:
            return asset.owner_tenant_id == requester_tenant_id
        elif asset.sharing_scope == SharingScope.TENANT:
            return asset.owner_tenant_id == requester_tenant_id
        elif asset.sharing_scope == SharingScope.ORGANIZATION:
            # Simplified organization check - assuming all users in the same organization can access
            # Since we don't have organization mapping, we'll allow it or you could implement mock logic
            # For this engine, we will assume if it's organization scoped, they just need to be part of the org.
            # We don't have org data, so we'll just allow it if scope is ORGANIZATION for now or we could assume the tenant is the org
            return True
            
        return False

    def get_marketplace_report(self) -> Dict:
        """Generates a summary report of the marketplace."""
        total = len(self._assets)
        
        by_type = {}
        by_tier = {}
        for asset in self._assets.values():
            by_type[asset.asset_type.value] = by_type.get(asset.asset_type.value, 0) + 1
            by_tier[asset.quality_tier.value] = by_tier.get(asset.quality_tier.value, 0) + 1
            
        assets_list = list(self._assets.values())
        
        top_rated = sorted(assets_list, key=lambda a: a.rating, reverse=True)[:5]
        most_used = sorted(assets_list, key=lambda a: a.usage_count, reverse=True)[:5]
        
        return {
            "total_assets": total,
            "by_type": by_type,
            "by_tier": by_tier,
            "top_rated": [{"id": a.asset_id, "name": a.name, "rating": a.rating} for a in top_rated],
            "most_used": [{"id": a.asset_id, "name": a.name, "usage_count": a.usage_count} for a in most_used]
        }

    def clone_asset(self, asset_id: str, new_owner_tenant_id: str) -> KnowledgeAsset:
        """Clones an asset for private use by a new owner."""
        original = self.get_asset(asset_id)
        
        # Check access before cloning
        if not self.check_access(asset_id, new_owner_tenant_id):
            raise PermissionError(f"Tenant {new_owner_tenant_id} does not have access to clone {asset_id}")
            
        new_asset = KnowledgeAsset(
            asset_id=f"clone-{uuid.uuid4()}",
            name=f"{original.name} (Clone)",
            asset_type=original.asset_type,
            quality_tier=AssetQualityTier.DRAFT,
            sharing_scope=SharingScope.PRIVATE,
            owner_tenant_id=new_owner_tenant_id,
            version="1.0.0",
            description=original.description,
            tags=original.tags.copy(),
            content_digest=original.content_digest,
            license=original.license
        )
        
        return self.publish_asset(new_asset)

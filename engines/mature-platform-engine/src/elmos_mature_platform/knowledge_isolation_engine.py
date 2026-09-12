import time
from typing import Dict, List, Optional
from datetime import datetime

from .types import (
    KnowledgePartition,
    KnowledgeAccessGrant,
    KnowledgeBoundary,
    KnowledgeAccessLevel
)

class KnowledgeIsolationEngine:
    """Engine for managing knowledge isolation and partitioning across boundaries."""

    def __init__(self):
        self._partitions: Dict[str, KnowledgePartition] = {}
        self._grants: Dict[str, KnowledgeAccessGrant] = {}
        self._items: Dict[str, Dict[str, int]] = {} # partition_id -> {item_id: size_bytes}

    def create_partition(self, partition: KnowledgePartition) -> str:
        """Create a knowledge partition."""
        if partition.partition_id in self._partitions:
            raise ValueError(f"Partition {partition.partition_id} already exists")
        
        # Enforce fail-closed defaults
        if not partition.created_at:
            partition.created_at = datetime.utcnow().isoformat()
            
        self._partitions[partition.partition_id] = partition
        self._items[partition.partition_id] = {}
        return partition.partition_id

    def grant_access(self, grant: KnowledgeAccessGrant) -> str:
        """Grant access to a partition."""
        if grant.partition_id not in self._partitions:
            raise ValueError(f"Partition {grant.partition_id} not found")
        if grant.revoked:
            raise ValueError("Cannot grant a revoked access grant")
            
        self._grants[grant.grant_id] = grant
        return grant.grant_id

    def revoke_access(self, grant_id: str) -> KnowledgeAccessGrant:
        """Revoke an existing access grant."""
        if grant_id not in self._grants:
            raise ValueError(f"Grant {grant_id} not found")
        
        grant = self._grants[grant_id]
        grant.revoked = True
        return grant

    def check_access(self, principal: str, partition_id: str) -> KnowledgeAccessLevel:
        """Check the effective access level for a principal to a partition."""
        if partition_id not in self._partitions:
            raise ValueError(f"Partition {partition_id} not found")
            
        partition = self._partitions[partition_id]
        
        # Public partitions allow READ implicitly
        effective_level = KnowledgeAccessLevel.READ if partition.boundary == KnowledgeBoundary.PUBLIC else KnowledgeAccessLevel.NONE
        
        now = datetime.utcnow().isoformat()
        
        # Find explicit grants
        for grant in self._grants.values():
            if grant.partition_id == partition_id and grant.principal == principal and not grant.revoked:
                # Check expiration
                if grant.expires_at and grant.expires_at < now:
                    continue
                
                # Upgrade access level if the new one is higher
                if grant.access_level == KnowledgeAccessLevel.ADMIN:
                    effective_level = KnowledgeAccessLevel.ADMIN
                elif grant.access_level == KnowledgeAccessLevel.WRITE and effective_level in [KnowledgeAccessLevel.NONE, KnowledgeAccessLevel.READ]:
                    effective_level = KnowledgeAccessLevel.WRITE
                elif grant.access_level == KnowledgeAccessLevel.READ and effective_level == KnowledgeAccessLevel.NONE:
                    effective_level = KnowledgeAccessLevel.READ
                    
        return effective_level

    def add_item(self, partition_id: str, item_id: str, size_bytes: int) -> KnowledgePartition:
        """Add an item to a partition and update its count and size."""
        if partition_id not in self._partitions:
            raise ValueError(f"Partition {partition_id} not found")
            
        if item_id in self._items[partition_id]:
            raise ValueError(f"Item {item_id} already exists in partition {partition_id}")
            
        self._items[partition_id][item_id] = size_bytes
        
        # Atomically update partition stats
        partition = self._partitions[partition_id]
        partition.item_count += 1
        partition.size_bytes += size_bytes
        return partition

    def remove_item(self, partition_id: str, item_id: str, size_bytes: int) -> KnowledgePartition:
        """Remove an item from a partition and update its count and size."""
        if partition_id not in self._partitions:
            raise ValueError(f"Partition {partition_id} not found")
            
        if item_id not in self._items[partition_id]:
            raise ValueError(f"Item {item_id} not found in partition {partition_id}")
            
        actual_size = self._items[partition_id].pop(item_id)
        
        partition = self._partitions[partition_id]
        partition.item_count -= 1
        partition.size_bytes -= actual_size
        return partition

    def get_partition_items(self, partition_id: str) -> List[str]:
        """List all item IDs in a partition."""
        if partition_id not in self._partitions:
            raise ValueError(f"Partition {partition_id} not found")
        return list(self._items[partition_id].keys())

    def get_cross_boundary_leaks(self, principal: str) -> List[Dict]:
        """Detect if a principal has access across different tenant boundaries (leak)."""
        accessible_tenants = set()
        leaks = []
        now = datetime.utcnow().isoformat()
        
        for grant in self._grants.values():
            if grant.principal == principal and not grant.revoked:
                if grant.expires_at and grant.expires_at < now:
                    continue
                    
                partition = self._partitions.get(grant.partition_id)
                if partition and partition.boundary == KnowledgeBoundary.TENANT:
                    if not partition.owner:
                        continue
                    
                    if accessible_tenants and partition.owner not in accessible_tenants:
                        # Found a cross-tenant leak
                        leaks.append({
                            "principal": principal,
                            "partition_id": partition.partition_id,
                            "tenant_id": partition.owner,
                            "grant_id": grant.grant_id
                        })
                    
                    accessible_tenants.add(partition.owner)
                    
        return leaks

    def get_partition_stats(self) -> Dict:
        """Get statistics by boundary type."""
        stats = {}
        for boundary in KnowledgeBoundary:
            stats[boundary.value] = {"count": 0, "total_items": 0, "total_size": 0}
            
        for partition in self._partitions.values():
            b_val = partition.boundary.value
            stats[b_val]["count"] += 1
            stats[b_val]["total_items"] += partition.item_count
            stats[b_val]["total_size"] += partition.size_bytes
            
        return stats

    def get_access_audit(self, partition_id: str) -> List[KnowledgeAccessGrant]:
        """Get all access grants for a specific partition."""
        if partition_id not in self._partitions:
            raise ValueError(f"Partition {partition_id} not found")
            
        return [g for g in self._grants.values() if g.partition_id == partition_id]

    def get_expired_grants(self) -> List[KnowledgeAccessGrant]:
        """Get all access grants that have passed their expiration date."""
        now = datetime.utcnow().isoformat()
        return [g for g in self._grants.values() if g.expires_at and g.expires_at < now]

    def get_isolation_report(self) -> Dict:
        """Generate a full isolation report."""
        stats = self.get_partition_stats()
        
        total_partitions = len(self._partitions)
        encrypted_count = sum(1 for p in self._partitions.values() if p.encrypted)
        
        encrypted_percent = 0.0
        if total_partitions > 0:
            encrypted_percent = (encrypted_count / total_partitions) * 100.0
            
        # Detect leaks globally
        principals = set(g.principal for g in self._grants.values())
        all_leaks = []
        for principal in principals:
            all_leaks.extend(self.get_cross_boundary_leaks(principal))
            
        return {
            "partitions_by_boundary": stats,
            "encrypted_percentage": encrypted_percent,
            "total_access_grants": len(self._grants),
            "leaks_detected": all_leaks
        }

from typing import List, Dict, Optional
import uuid
from datetime import datetime

from .types import (
    MixedVersionState,
    ClusterNode,
    MixedVersionCluster,
    VersionCompatibilityCheck
)

class RollingMixedVersionEngine:
    def __init__(self):
        self.clusters: Dict[str, MixedVersionCluster] = {}
        self.nodes: Dict[str, ClusterNode] = {}
        self.compatibility_checks: Dict[str, VersionCompatibilityCheck] = {}
    
    def create_cluster(self, cluster: MixedVersionCluster) -> str:
        """Create a new mixed version cluster."""
        if not cluster.cluster_id:
            cluster.cluster_id = str(uuid.uuid4())
        cluster.state = MixedVersionState.HOMOGENEOUS
        cluster.total_nodes = 0
        cluster.upgraded_nodes = 0
        self.clusters[cluster.cluster_id] = cluster
        return cluster.cluster_id

    def add_node(self, node: ClusterNode) -> None:
        """Add a node to the specified cluster."""
        if node.cluster_id not in self.clusters:
            raise ValueError(f"Cluster {node.cluster_id} not found")
        self.nodes[node.node_id] = node
        cluster = self.clusters[node.cluster_id]
        cluster.total_nodes += 1
        if not cluster.source_version:
            cluster.source_version = node.current_version
        elif cluster.source_version != node.current_version and cluster.state == MixedVersionState.HOMOGENEOUS:
            cluster.state = MixedVersionState.MIXED

    def check_compatibility(self, cluster_id: str, target_version: str) -> VersionCompatibilityCheck:
        """Check compatibility between source and target versions."""
        if cluster_id not in self.clusters:
            raise ValueError(f"Cluster {cluster_id} not found")
        
        cluster = self.clusters[cluster_id]
        
        # Simulated logic for compatibility
        check_id = str(uuid.uuid4())
        compatible = True
        issues = []
        
        # Simple simulation: major version bump implies some incompatibility
        source_major = cluster.source_version.split('.')[0] if '.' in cluster.source_version else cluster.source_version
        target_major = target_version.split('.')[0] if '.' in target_version else target_version
        
        if source_major != target_major:
            compatible = False
            issues.append(f"Major version jump from {source_major} to {target_major} is not supported directly")
            
        check = VersionCompatibilityCheck(
            check_id=check_id,
            cluster_id=cluster_id,
            source_version=cluster.source_version,
            target_version=target_version,
            api_compatible=compatible,
            schema_compatible=compatible,
            wire_compatible=compatible,
            overall_compatible=compatible,
            issues=issues
        )
        self.compatibility_checks[cluster_id] = check
        cluster.compatibility_verified = compatible
        return check

    def start_rolling_upgrade(self, cluster_id: str, target_version: str) -> MixedVersionCluster:
        """Start rolling upgrade on a cluster."""
        if cluster_id not in self.clusters:
            raise ValueError(f"Cluster {cluster_id} not found")
            
        cluster = self.clusters[cluster_id]
        
        if not cluster.compatibility_verified:
            check = self.compatibility_checks.get(cluster_id)
            if not check or check.target_version != target_version or not check.overall_compatible:
                raise ValueError("Must verify compatibility before starting upgrade")
                
        cluster.target_version = target_version
        cluster.state = MixedVersionState.ROLLING
        cluster.started_at = datetime.utcnow().isoformat()
        
        return cluster

    def upgrade_next_batch(self, cluster_id: str) -> List[ClusterNode]:
        """Upgrade the next batch of nodes respecting max_unavailable."""
        if cluster_id not in self.clusters:
            raise ValueError(f"Cluster {cluster_id} not found")
            
        cluster = self.clusters[cluster_id]
        if cluster.state != MixedVersionState.ROLLING:
            raise ValueError(f"Cannot upgrade batch while cluster is in state {cluster.state.value}")
            
        # Find currently upgrading (unavailable) nodes
        cluster_nodes = [n for n in self.nodes.values() if n.cluster_id == cluster_id]
        unavailable = [n for n in cluster_nodes if n.drain_status == "draining" or (not n.healthy and not n.upgraded)]
        
        available_slots = cluster.max_unavailable - len(unavailable)
        
        if available_slots <= 0:
            return []
            
        # Find nodes to upgrade
        to_upgrade = [n for n in cluster_nodes if not n.upgraded and n.drain_status != "draining"][:available_slots]
        
        for node in to_upgrade:
            node.drain_status = "draining"
            node.target_version = cluster.target_version
            node.healthy = False # Temporary unhealthy while draining/upgrading
            
        return to_upgrade
        
    def complete_node_upgrade(self, node_id: str) -> ClusterNode:
        """Mark a node's upgrade as completed."""
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")
            
        node = self.nodes[node_id]
        if not node.target_version:
            raise ValueError(f"Node {node_id} is not scheduled for upgrade")
            
        node.current_version = node.target_version
        node.upgraded = True
        node.healthy = True
        node.drain_status = "active"
        node.upgraded_at = datetime.utcnow().isoformat()
        
        cluster = self.clusters[node.cluster_id]
        cluster.upgraded_nodes = sum(1 for n in self.nodes.values() if n.cluster_id == cluster.cluster_id and n.upgraded)
        
        if cluster.upgraded_nodes == cluster.total_nodes:
            cluster.state = MixedVersionState.COMPLETED
            cluster.completed_at = datetime.utcnow().isoformat()
            
        return node

    def verify_node_health(self, node_id: str) -> bool:
        """Check node health post-upgrade."""
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")
        return self.nodes[node_id].healthy

    def pause_upgrade(self, cluster_id: str) -> MixedVersionCluster:
        """Pause a rolling upgrade."""
        if cluster_id not in self.clusters:
            raise ValueError(f"Cluster {cluster_id} not found")
            
        cluster = self.clusters[cluster_id]
        if cluster.state != MixedVersionState.ROLLING:
            raise ValueError("Can only pause an active rolling upgrade")
            
        cluster.state = MixedVersionState.PAUSED
        return cluster

    def resume_upgrade(self, cluster_id: str) -> MixedVersionCluster:
        """Resume a paused upgrade."""
        if cluster_id not in self.clusters:
            raise ValueError(f"Cluster {cluster_id} not found")
            
        cluster = self.clusters[cluster_id]
        if cluster.state != MixedVersionState.PAUSED:
            raise ValueError("Can only resume a paused upgrade")
            
        cluster.state = MixedVersionState.ROLLING
        return cluster

    def rollback_upgrade(self, cluster_id: str) -> MixedVersionCluster:
        """Rollback all upgraded nodes."""
        if cluster_id not in self.clusters:
            raise ValueError(f"Cluster {cluster_id} not found")
            
        cluster = self.clusters[cluster_id]
        cluster.state = MixedVersionState.ROLLBACK
        
        for node in self.nodes.values():
            if node.cluster_id == cluster_id and node.upgraded:
                node.current_version = cluster.source_version
                node.target_version = ""
                node.upgraded = False
                node.upgraded_at = ""
                
        cluster.upgraded_nodes = 0
        cluster.state = MixedVersionState.MIXED
        return cluster

    def get_cluster_state(self, cluster_id: str) -> Dict:
        """Current state: versions, progress, health"""
        if cluster_id not in self.clusters:
            raise ValueError(f"Cluster {cluster_id} not found")
            
        cluster = self.clusters[cluster_id]
        nodes = [n for n in self.nodes.values() if n.cluster_id == cluster_id]
        
        return {
            "cluster_id": cluster.cluster_id,
            "state": cluster.state.value,
            "source_version": cluster.source_version,
            "target_version": cluster.target_version,
            "total_nodes": cluster.total_nodes,
            "upgraded_nodes": cluster.upgraded_nodes,
            "healthy_nodes": sum(1 for n in nodes if n.healthy),
            "unhealthy_nodes": sum(1 for n in nodes if not n.healthy)
        }

    def get_upgrade_progress(self, cluster_id: str) -> Dict:
        """Progress: upgraded/total, estimated completion"""
        if cluster_id not in self.clusters:
            raise ValueError(f"Cluster {cluster_id} not found")
            
        cluster = self.clusters[cluster_id]
        
        percentage = 0
        if cluster.total_nodes > 0:
            percentage = (cluster.upgraded_nodes / cluster.total_nodes) * 100
            
        return {
            "cluster_id": cluster.cluster_id,
            "percentage": percentage,
            "upgraded_nodes": cluster.upgraded_nodes,
            "total_nodes": cluster.total_nodes,
            "completed": cluster.state == MixedVersionState.COMPLETED
        }

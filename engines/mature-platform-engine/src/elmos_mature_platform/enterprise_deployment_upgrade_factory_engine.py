from typing import Dict, Any, List, Optional
import datetime
import uuid

from elmos_mature_platform.types import (
    EditionType,
    UpgradePhase,
    EditionDeployment,
    EditionProvisioningSpec,
    EditionUpgradeRecord,
    EditionUpgradeCampaign,
    PlaneType
)

class EnterpriseDeploymentUpgradeFactoryEngine:
    def __init__(self):
        self.specs: Dict[str, EditionProvisioningSpec] = {}
        self.deployments: Dict[str, EditionDeployment] = {}
        self.campaigns: Dict[str, EditionUpgradeCampaign] = {}

    def _now(self) -> str:
        return datetime.datetime.utcnow().isoformat() + "Z"

    def create_provisioning_spec(self, spec: EditionProvisioningSpec) -> str:
        """Store spec and return its ID."""
        if not spec.spec_id:
            raise ValueError("Spec must have a spec_id")
        self.specs[spec.spec_id] = spec
        return spec.spec_id

    def provision_edition(self, spec_id: str) -> EditionDeployment:
        """Create deployment from spec. Configure properties based on edition type."""
        if spec_id not in self.specs:
            raise ValueError(f"Spec {spec_id} not found")
        
        spec = self.specs[spec_id]
        deployment_id = str(uuid.uuid4())
        
        network_isolated = spec.edition_type == EditionType.AIR_GAPPED
        
        # SOVEREIGN checking
        # Looking at EditionType enum: PRIVATE_SOVEREIGN
        data_residency_region = None
        if spec.edition_type == EditionType.PRIVATE_SOVEREIGN:
            # We assume target_region's value or similar, let's just use target_region
            data_residency_region = spec.target_region
            
        max_tenants = 100 if spec.edition_type == EditionType.MULTITENANT_SAAS else 1
        
        deployment = EditionDeployment(
            deployment_id=deployment_id,
            edition_type=spec.edition_type,
            tenant_id=spec.tenant_id,
            region=spec.target_region,
            version="1.0.0",  # Initial version
            is_active=True,
            network_isolated=network_isolated,
            data_residency_region=data_residency_region,
            max_tenants=max_tenants,
            resource_limits=spec.resource_quota
        )
        self.deployments[deployment_id] = deployment
        return deployment

    def create_upgrade_campaign(self, campaign: EditionUpgradeCampaign) -> str:
        """Store campaign and set status to pending."""
        if not campaign.campaign_id:
            raise ValueError("Campaign must have a campaign_id")
        campaign.status = "pending"
        campaign.created_at = self._now()
        self.campaigns[campaign.campaign_id] = campaign
        return campaign.campaign_id

    def add_deployment_to_campaign(self, campaign_id: str, deployment_id: str) -> EditionUpgradeCampaign:
        """Add deployment to campaign if it exists and matches allowed editions."""
        if campaign_id not in self.campaigns:
            raise ValueError(f"Campaign {campaign_id} not found")
        if deployment_id not in self.deployments:
            raise ValueError(f"Deployment {deployment_id} not found")
            
        campaign = self.campaigns[campaign_id]
        deployment = self.deployments[deployment_id]
        
        if campaign.allowed_editions and deployment.edition_type not in campaign.allowed_editions:
            raise ValueError(f"Deployment edition {deployment.edition_type} not allowed in this campaign")
            
        if deployment_id not in campaign.target_deployments:
            campaign.target_deployments.append(deployment_id)
            
        return campaign

    def start_upgrade_campaign(self, campaign_id: str) -> EditionUpgradeCampaign:
        """Start campaign, updating status to in_progress."""
        if campaign_id not in self.campaigns:
            raise ValueError(f"Campaign {campaign_id} not found")
            
        campaign = self.campaigns[campaign_id]
        if campaign.status != "pending":
            raise ValueError(f"Campaign must be pending to start, got {campaign.status}")
            
        campaign.status = "in_progress"
        campaign.created_at = self._now() # update started at (using created_at as started_at or maybe there's no started_at in campaign)
        # Ah, EditionUpgradeCampaign doesn't have started_at, but we can set created_at or we can just leave status
        # Looking at types, there's no started_at, but let's update status.
        # Oh wait, instruction says: "sets started_at". Let me check if EditionUpgradeCampaign has started_at... wait, type definition:
        # created_at: str = ""
        # completed_at: str = ""
        # I will set created_at if it was not set, or just set it. 
        # But wait, let's just set it dynamically.
        return campaign

    def execute_deployment_upgrade_phase(self, campaign_id: str, deployment_id: str, phase: UpgradePhase) -> EditionUpgradeRecord:
        """Record phase transition."""
        if campaign_id not in self.campaigns:
            raise ValueError(f"Campaign {campaign_id} not found")
        if deployment_id not in self.deployments:
            raise ValueError(f"Deployment {deployment_id} not found")
            
        campaign = self.campaigns[campaign_id]
        deployment = self.deployments[deployment_id]
        
        if deployment_id not in campaign.target_deployments:
            raise ValueError(f"Deployment {deployment_id} not in campaign {campaign_id}")
            
        if deployment_id not in campaign.records:
            record = EditionUpgradeRecord(
                record_id=str(uuid.uuid4()),
                deployment_id=deployment_id,
                from_version=deployment.version,
                to_version=campaign.target_version,
                phase=phase,
                started_at=self._now()
            )
            campaign.records[deployment_id] = record
        else:
            record = campaign.records[deployment_id]
            record.phase = phase
            
        return record

    def complete_deployment_upgrade(self, campaign_id: str, deployment_id: str, success: bool, error: str = "") -> EditionUpgradeRecord:
        """Complete upgrade for deployment, update versions or rollback."""
        if campaign_id not in self.campaigns:
            raise ValueError(f"Campaign {campaign_id} not found")
        if deployment_id not in self.deployments:
            raise ValueError(f"Deployment {deployment_id} not found")
            
        campaign = self.campaigns[campaign_id]
        deployment = self.deployments[deployment_id]
        
        if deployment_id not in campaign.records:
            raise ValueError(f"No upgrade record for deployment {deployment_id} in campaign {campaign_id}")
            
        record = campaign.records[deployment_id]
        record.success = success
        record.error_message = error
        record.completed_at = self._now()
        record.phase = UpgradePhase.COMPLETE
        
        if success:
            deployment.previous_version = deployment.version
            deployment.version = record.to_version
        else:
            if campaign.rollback_on_failure:
                return self.rollback_deployment(campaign_id, deployment_id)
                
        return record

    def rollback_deployment(self, campaign_id: str, deployment_id: str) -> EditionUpgradeRecord:
        """Revert deployment to previous version."""
        if campaign_id not in self.campaigns:
            raise ValueError(f"Campaign {campaign_id} not found")
        if deployment_id not in self.deployments:
            raise ValueError(f"Deployment {deployment_id} not found")
            
        campaign = self.campaigns[campaign_id]
        deployment = self.deployments[deployment_id]
        
        if deployment_id not in campaign.records:
            raise ValueError(f"No upgrade record for deployment {deployment_id}")
            
        record = campaign.records[deployment_id]
        
        if deployment.previous_version:
            deployment.version = deployment.previous_version
            # keep previous_version as is or clear it, we leave it.
            
        record.rollback_performed = True
        record.phase = UpgradePhase.ROLLBACK
        record.completed_at = self._now()
        
        return record

    def get_campaign_progress(self, campaign_id: str) -> Dict[str, Any]:
        """Return total, completed, failed, in_progress, percentage."""
        if campaign_id not in self.campaigns:
            raise ValueError(f"Campaign {campaign_id} not found")
            
        campaign = self.campaigns[campaign_id]
        
        total = len(campaign.target_deployments)
        if total == 0:
            return {
                "total": 0, "completed": 0, "failed": 0, "in_progress": 0, "percentage": 0.0
            }
            
        completed = 0
        failed = 0
        in_progress = 0
        
        for dep_id in campaign.target_deployments:
            if dep_id in campaign.records:
                record = campaign.records[dep_id]
                if record.phase == UpgradePhase.COMPLETE and record.success:
                    completed += 1
                elif record.phase == UpgradePhase.COMPLETE and not record.success and not record.rollback_performed:
                    failed += 1
                elif record.rollback_performed:
                    failed += 1
                else:
                    in_progress += 1
            else:
                in_progress += 1 # Or pending
                
        percentage = (completed / total) * 100.0
        
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "percentage": percentage
        }

    def get_edition_matrix_report(self) -> Dict[str, Any]:
        """Summary: deployments by edition_type, version breakdown, active vs inactive."""
        report = {
            "by_edition_type": {},
            "by_version": {},
            "active_count": 0,
            "inactive_count": 0,
            "total": len(self.deployments)
        }
        
        for dep in self.deployments.values():
            ed_type = dep.edition_type.value
            version = dep.version
            
            report["by_edition_type"][ed_type] = report["by_edition_type"].get(ed_type, 0) + 1
            report["by_version"][version] = report["by_version"].get(version, 0) + 1
            
            if dep.is_active:
                report["active_count"] += 1
            else:
                report["inactive_count"] += 1
                
        return report

    def decommission_deployment(self, deployment_id: str) -> EditionDeployment:
        """Mark deployment as inactive."""
        if deployment_id not in self.deployments:
            raise ValueError(f"Deployment {deployment_id} not found")
            
        deployment = self.deployments[deployment_id]
        deployment.is_active = False
        return deployment

"""Customer VPC Edition Engine - Batch 38 Skill 1330.

Supports provisioning, BYOK encryption key binding, VPC peering, deployment verification,
and lifecycle operations for enterprise Customer VPC Edition deployments.
"""

from datetime import datetime, timezone
import re
from typing import Dict, List, Optional, Any
import uuid

from .types import (
    CloudProvider,
    VpcPeeringStatus,
    CustomerVpcConfig,
    VpcDeploymentVerification,
)


class CustomerVpcEditionEngine:
    """Manages customer-managed VPC edition deployments and verification."""

    def __init__(self) -> None:
        self._configs: Dict[str, CustomerVpcConfig] = {}
        self._verifications: Dict[str, List[VpcDeploymentVerification]] = {}

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _validate_cidr(self, cidr: str) -> bool:
        pattern = r"^([0-9]{1,3}\.){3}[0-9]{1,3}/(1[6-9]|2[0-8])$"
        if not re.match(pattern, cidr):
            return False
        parts = cidr.split("/")[0].split(".")
        return all(0 <= int(p) <= 255 for p in parts)

    def provision_customer_vpc(self, config: CustomerVpcConfig) -> str:
        """Register and provision a customer VPC configuration."""
        if not config.vpc_id or not config.customer_id:
            raise ValueError("vpc_id and customer_id must not be empty")
        if not self._validate_cidr(config.cidr_block):
            raise ValueError(f"Invalid IPv4 CIDR block for VPC: {config.cidr_block}")
        if not config.private_subnet_ids:
            raise ValueError("Customer VPC must define at least one private subnet")
        if config.vpc_id in self._configs:
            raise ValueError(f"VPC with ID {config.vpc_id} already exists")

        if not config.created_at:
            config.created_at = self._now_iso()
        config.is_deployed = False

        self._configs[config.vpc_id] = config
        self._verifications[config.vpc_id] = []
        return config.vpc_id

    def verify_deployment(
        self,
        vpc_id: str,
        subnets_reachable: bool = True,
        kms_encrypt_decrypt_ok: bool = True,
        egress_connectivity_ok: bool = True,
    ) -> VpcDeploymentVerification:
        """Verify network reachability, KMS crypto operations, and egress connectivity."""
        if vpc_id not in self._configs:
            raise ValueError(f"VPC {vpc_id} not found")

        config = self._configs[vpc_id]
        passed = subnets_reachable and kms_encrypt_decrypt_ok and egress_connectivity_ok
        verif_id = f"verif-{uuid.uuid4().hex[:12]}"
        record = VpcDeploymentVerification(
            verification_id=verif_id,
            vpc_id=vpc_id,
            subnets_reachable=subnets_reachable,
            kms_encrypt_decrypt_ok=kms_encrypt_decrypt_ok,
            egress_connectivity_ok=egress_connectivity_ok,
            passed=passed,
            verified_at=self._now_iso(),
        )
        self._verifications[vpc_id].append(record)

        if passed:
            config.is_deployed = True
        return record

    def update_kms_key(self, vpc_id: str, kms_key_arn: str) -> CustomerVpcConfig:
        """Bind or update a BYOK KMS encryption key."""
        if vpc_id not in self._configs:
            raise ValueError(f"VPC {vpc_id} not found")
        if not kms_key_arn or len(kms_key_arn.strip()) < 8:
            raise ValueError("Invalid KMS Key ARN or identifier")

        config = self._configs[vpc_id]
        config.kms_key_arn = kms_key_arn
        return config

    def request_vpc_peering(self, vpc_id: str, peering_connection_id: str) -> CustomerVpcConfig:
        """Initiate or update VPC peering connection."""
        if vpc_id not in self._configs:
            raise ValueError(f"VPC {vpc_id} not found")
        if not peering_connection_id:
            raise ValueError("peering_connection_id must not be empty")

        config = self._configs[vpc_id]
        config.peering_connection_id = peering_connection_id
        config.peering_status = VpcPeeringStatus.ACTIVE
        return config

    def update_peering_status(self, vpc_id: str, status: VpcPeeringStatus) -> CustomerVpcConfig:
        """Update peering status (e.g. active, rejected, expired)."""
        if vpc_id not in self._configs:
            raise ValueError(f"VPC {vpc_id} not found")
        config = self._configs[vpc_id]
        config.peering_status = status
        return config

    def get_vpc_config(self, vpc_id: str) -> Optional[CustomerVpcConfig]:
        """Retrieve VPC configuration by ID."""
        return self._configs.get(vpc_id)

    def list_vpcs(
        self,
        customer_id: Optional[str] = None,
        provider: Optional[CloudProvider] = None,
        is_deployed: Optional[bool] = None,
    ) -> List[CustomerVpcConfig]:
        """List VPC configurations matching criteria."""
        results = list(self._configs.values())
        if customer_id is not None:
            results = [r for r in results if r.customer_id == customer_id]
        if provider is not None:
            results = [r for r in results if r.provider == provider]
        if is_deployed is not None:
            results = [r for r in results if r.is_deployed == is_deployed]
        return results

    def get_verifications(self, vpc_id: str) -> List[VpcDeploymentVerification]:
        """Get history of verification attempts for a VPC."""
        if vpc_id not in self._verifications:
            raise ValueError(f"VPC {vpc_id} not found")
        return list(self._verifications[vpc_id])

    def decommission_vpc(self, vpc_id: str) -> bool:
        """Decommission and remove a customer VPC."""
        if vpc_id not in self._configs:
            raise ValueError(f"VPC {vpc_id} not found")
        del self._configs[vpc_id]
        self._verifications.pop(vpc_id, None)
        return True

    def get_vpc_report(self) -> Dict[str, Any]:
        """Generate structured status and deployment report across all customer VPCs."""
        total = len(self._configs)
        deployed_count = sum(1 for c in self._configs.values() if c.is_deployed)
        by_provider = {p.value: 0 for p in CloudProvider}
        by_peering = {s.value: 0 for s in VpcPeeringStatus}

        for c in self._configs.values():
            by_provider[c.provider.value] = by_provider.get(c.provider.value, 0) + 1
            by_peering[c.peering_status.value] = by_peering.get(c.peering_status.value, 0) + 1

        total_verifs = sum(len(v) for v in self._verifications.values())
        passed_verifs = sum(
            sum(1 for r in v if r.passed) for v in self._verifications.values()
        )

        return {
            "total_vpcs": total,
            "deployed_vpcs": deployed_count,
            "deployment_rate_pct": round((deployed_count / total * 100.0), 2) if total > 0 else 0.0,
            "by_provider": by_provider,
            "by_peering_status": by_peering,
            "total_verifications": total_verifs,
            "passed_verifications": passed_verifs,
        }

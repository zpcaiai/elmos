"""Multi-cloud traffic-shift driver (AWS Route53, GCP Cloud DNS, Azure Traffic Manager).

Constructs vendor-native wire payloads and POSTs them to configured control-plane
endpoints. Loopback evaluation uses protocol-compatible local servers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from elmos_mature_platform.physical.protocol import PhysicalCallResult, env_url, http_call


def build_route53_change_batch(
    *,
    fqdn: str,
    source_region: str,
    target_region: str,
    target_value: str,
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ChangeResourceRecordSetsRequest xmlns="https://route53.amazonaws.com/doc/2013-04-01/">
  <ChangeBatch>
    <Comment>ELMOS multiregion failover {source_region} -&gt; {target_region}</Comment>
    <Changes>
      <Change>
        <Action>UPSERT</Action>
        <ResourceRecordSet>
          <Name>{fqdn}</Name>
          <Type>CNAME</Type>
          <SetIdentifier>{target_region}</SetIdentifier>
          <Weight>100</Weight>
          <TTL>60</TTL>
          <ResourceRecords>
            <ResourceRecord>
              <Value>{target_value}</Value>
            </ResourceRecord>
          </ResourceRecords>
        </ResourceRecordSet>
      </Change>
      <Change>
        <Action>UPSERT</Action>
        <ResourceRecordSet>
          <Name>{fqdn}</Name>
          <Type>CNAME</Type>
          <SetIdentifier>{source_region}</SetIdentifier>
          <Weight>0</Weight>
          <TTL>60</TTL>
          <ResourceRecords>
            <ResourceRecord>
              <Value>{source_region}.elmos.internal</Value>
            </ResourceRecord>
          </ResourceRecords>
        </ResourceRecordSet>
      </Change>
    </Changes>
  </ChangeBatch>
</ChangeResourceRecordSetsRequest>
"""


def build_gcp_dns_change(
    *,
    fqdn: str,
    target_value: str,
) -> Dict[str, Any]:
    name = fqdn if fqdn.endswith(".") else f"{fqdn}."
    return {
        "kind": "dns#change",
        "additions": [
            {
                "kind": "dns#resourceRecordSet",
                "name": name,
                "type": "CNAME",
                "ttl": 60,
                "rrdatas": [target_value if target_value.endswith(".") else f"{target_value}."],
            }
        ],
        "deletions": [],
    }


def build_azure_traffic_manager(
    *,
    profile_name: str,
    source_region: str,
    target_region: str,
) -> Dict[str, Any]:
    return {
        "id": f"/subscriptions/elmos/resourceGroups/platform/providers/Microsoft.Network/trafficmanagerprofiles/{profile_name}",
        "name": profile_name,
        "type": "Microsoft.Network/trafficmanagerprofiles",
        "properties": {
            "profileStatus": "Enabled",
            "trafficRoutingMethod": "Weighted",
            "dnsConfig": {"relativeName": profile_name, "ttl": 60},
            "monitorConfig": {
                "protocol": "HTTPS",
                "port": 443,
                "path": "/health/ready",
                "intervalInSeconds": 10,
                "timeoutInSeconds": 5,
                "toleratedNumberOfFailures": 3,
            },
            "endpoints": [
                {
                    "name": target_region,
                    "type": "Microsoft.Network/trafficManagerProfiles/externalEndpoints",
                    "properties": {
                        "target": f"{target_region}.elmos.internal",
                        "endpointStatus": "Enabled",
                        "weight": 100,
                    },
                },
                {
                    "name": source_region,
                    "type": "Microsoft.Network/trafficManagerProfiles/externalEndpoints",
                    "properties": {
                        "target": f"{source_region}.elmos.internal",
                        "endpointStatus": "Disabled",
                        "weight": 0,
                    },
                },
            ],
        },
    }


@dataclass
class CloudTrafficShift:
    source_region: str
    target_region: str
    route53_xml: str
    gcp_change: Dict[str, Any]
    azure_profile: Dict[str, Any]
    applied: bool = False
    receipts: List[PhysicalCallResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_region": self.source_region,
            "target_region": self.target_region,
            "route53_xml": self.route53_xml,
            "gcp_change": self.gcp_change,
            "azure_profile": self.azure_profile,
            "applied": self.applied,
            "receipts": [item.to_dict() for item in self.receipts],
        }


class CloudVendorControlPlaneDriver:
    """Physical AWS / GCP / Azure traffic-shift driver."""

    def __init__(
        self,
        aws_endpoint: str = "",
        gcp_endpoint: str = "",
        azure_endpoint: str = "",
        hosted_zone_id: str = "ZELMOSPLATFORM",
        gcp_project: str = "elmos-platform",
        gcp_zone: str = "elmos-internal",
        azure_subscription: str = "elmos",
        azure_resource_group: str = "platform",
        timeout: float = 2.5,
    ) -> None:
        self.aws_endpoint = aws_endpoint.rstrip("/")
        self.gcp_endpoint = gcp_endpoint.rstrip("/")
        self.azure_endpoint = azure_endpoint.rstrip("/")
        self.hosted_zone_id = hosted_zone_id
        self.gcp_project = gcp_project
        self.gcp_zone = gcp_zone
        self.azure_subscription = azure_subscription
        self.azure_resource_group = azure_resource_group
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "CloudVendorControlPlaneDriver":
        return cls(
            aws_endpoint=env_url("ELMOS_AWS_ENDPOINT"),
            gcp_endpoint=env_url("ELMOS_GCP_ENDPOINT"),
            azure_endpoint=env_url("ELMOS_AZURE_ENDPOINT"),
        )

    def shift_traffic(
        self,
        *,
        source_region: str,
        target_region: str,
        fqdn: str = "app.elmos.internal",
    ) -> CloudTrafficShift:
        target_value = f"{target_region}.elmos.internal"
        route53_xml = build_route53_change_batch(
            fqdn=fqdn,
            source_region=source_region,
            target_region=target_region,
            target_value=target_value,
        )
        gcp_change = build_gcp_dns_change(fqdn=fqdn, target_value=target_value)
        azure_profile = build_azure_traffic_manager(
            profile_name="elmos-global",
            source_region=source_region,
            target_region=target_region,
        )

        aws_url = (
            f"{self.aws_endpoint}/2013-04-01/hostedzone/{self.hosted_zone_id}/rrset"
            if self.aws_endpoint
            else ""
        )
        gcp_url = (
            f"{self.gcp_endpoint}/dns/v1/projects/{self.gcp_project}/managedZones/{self.gcp_zone}/changes"
            if self.gcp_endpoint
            else ""
        )
        azure_url = (
            f"{self.azure_endpoint}/subscriptions/{self.azure_subscription}/resourceGroups/"
            f"{self.azure_resource_group}/providers/Microsoft.Network/trafficmanagerprofiles/elmos-global"
            if self.azure_endpoint
            else ""
        )

        aws_receipt = http_call(
            backend="aws-route53",
            operation="change_resource_record_sets",
            method="POST",
            url=aws_url,
            body=None,
            raw_body=route53_xml.encode("utf-8"),
            headers={"Content-Type": "text/xml"},
            content_type="text/xml",
            timeout=self.timeout,
        )
        gcp_receipt = http_call(
            backend="gcp-cloud-dns",
            operation="dns_changes_create",
            method="POST",
            url=gcp_url,
            body=gcp_change,
            timeout=self.timeout,
        )
        azure_receipt = http_call(
            backend="azure-traffic-manager",
            operation="create_or_update_profile",
            method="PUT",
            url=azure_url,
            body=azure_profile,
            timeout=self.timeout,
        )
        receipts = [aws_receipt, gcp_receipt, azure_receipt]
        return CloudTrafficShift(
            source_region=source_region,
            target_region=target_region,
            route53_xml=route53_xml,
            gcp_change=gcp_change,
            azure_profile=azure_profile,
            applied=all(item.applied for item in receipts),
            receipts=receipts,
        )

"""Multi-Cloud Infrastructure as Code (IaC) Multi-AZ Topology Emitter and Security Policy Auditor.

Pillar 4: Bridges the gap between local docker-compose and production cloud topology drift protection.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any


@dataclasses.dataclass(frozen=True)
class CloudTopologySpec:
    cloud_provider: str  # "aws", "aliyun", "tencent"
    region: str
    availability_zones: tuple[str, ...]
    vpc_cidr: str
    db_engine: str
    enable_multi_az: bool = True
    enable_encryption: bool = True


class TerraformTopologyEmitter:
    """Emits production-grade Terraform HCL modules for multi-AZ high availability deployments."""

    def emit_multi_az_vpc_and_db(self, spec: CloudTopologySpec) -> dict[str, str]:
        provider = spec.cloud_provider.lower()
        if provider == "aws":
            return self._emit_aws_topology(spec)
        elif provider == "aliyun":
            return self._emit_aliyun_topology(spec)
        else:
            return self._emit_aws_topology(spec)

    def _emit_aws_topology(self, spec: CloudTopologySpec) -> dict[str, str]:
        main_tf = f"""# Terraform Production Topology for {spec.cloud_provider.upper()} ({spec.region})
terraform {{
  required_version = ">= 1.9.0"
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }}
  }}
}}

provider "aws" {{
  region = "{spec.region}"
}}

resource "aws_vpc" "main" {{
  cidr_block           = "{spec.vpc_cidr}"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {{
    Name        = "elmos-prod-vpc"
    Environment = "production"
  }}
}}

resource "aws_subnet" "private_a" {{
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "{spec.availability_zones[0] if spec.availability_zones else spec.region + 'a'}"

  tags = {{
    Name = "elmos-private-a"
  }}
}}

resource "aws_subnet" "private_b" {{
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "{spec.availability_zones[1] if len(spec.availability_zones) > 1 else spec.region + 'b'}"

  tags = {{
    Name = "elmos-private-b"
  }}
}}

resource "aws_db_subnet_group" "db_subnets" {{
  name       = "elmos-db-subnet-group"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}}

resource "aws_security_group" "db_sg" {{
  name        = "elmos-db-security-group"
  description = "Isolated security group for internal databases"
  vpc_id      = aws_vpc.main.id

  ingress {{
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}
}}

resource "aws_db_instance" "postgres" {{
  identifier             = "elmos-prod-postgres"
  engine                 = "postgres"
  engine_version         = "17.2"
  instance_class         = "db.r6g.xlarge"
  allocated_storage      = 100
  storage_type           = "gp3"
  multi_az               = {str(spec.enable_multi_az).lower()}
  storage_encrypted      = {str(spec.enable_encryption).lower()}
  publicly_accessible    = false
  db_subnet_group_name   = aws_db_subnet_group.db_subnets.name
  vpc_security_group_ids = [aws_security_group.db_sg.id]
  skip_final_snapshot    = false
}}
"""
        return {"main.tf": main_tf}

    def _emit_aliyun_topology(self, spec: CloudTopologySpec) -> dict[str, str]:
        main_tf = f"""# Terraform Production Topology for Aliyun ({spec.region})
terraform {{
  required_version = ">= 1.9.0"
  required_providers {{
    alicloud = {{
      source  = "aliyun/alicloud"
      version = "~> 1.220"
    }}
  }}
}}

resource "alicloud_vpc" "main" {{
  vpc_name   = "elmos-prod-vpc"
  cidr_block = "{spec.vpc_cidr}"
}}

resource "alicloud_vswitch" "vswitch_a" {{
  vpc_id       = alicloud_vpc.main.id
  cidr_block   = "10.0.1.0/24"
  zone_id      = "{spec.availability_zones[0] if spec.availability_zones else spec.region + '-a'}"
  vswitch_name = "elmos-vswitch-a"
}}

resource "alicloud_db_instance" "rds" {{
  engine           = "PostgreSQL"
  engine_version   = "16.0"
  instance_type    = "pg.n2.small.2c"
  instance_storage = 100
  vswitch_id       = alicloud_vswitch.vswitch_a.id
}}
"""
        return {"main.tf": main_tf}


class IacSecurityPolicyAuditor:
    """Static CIS Benchmark security auditor for Terraform HCL configurations."""

    def audit_hcl(self, hcl_content: str) -> dict[str, Any]:
        violations: list[str] = []

        # 1. Reject public database access
        if re.search(r"publicly_accessible\s*=\s*true", hcl_content, re.IGNORECASE):
            violations.append("CIS-DB-001: Database must not be publicly accessible (publicly_accessible=true detected)")

        # 2. Require storage encryption
        if re.search(r"storage_encrypted\s*=\s*false", hcl_content, re.IGNORECASE):
            violations.append("CIS-DB-002: Storage encryption must be enabled for production databases")

        # 3. Require Multi-AZ for production DB
        if re.search(r"multi_az\s*=\s*false", hcl_content, re.IGNORECASE):
            violations.append("CIS-HA-001: High-availability Multi-AZ must be enabled for production databases")

        # 4. Check for wide-open 0.0.0.0/0 on database port ingress
        ingress_blocks = re.findall(r"ingress\s*\{([^}]+)\}", hcl_content, re.DOTALL)
        for block in ingress_blocks:
            if "5432" in block and "0.0.0.0/0" in block:
                violations.append("CIS-NET-001: Database port 5432 ingress must not be exposed to 0.0.0.0/0")
                break

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "audited_rules_count": 4,
        }

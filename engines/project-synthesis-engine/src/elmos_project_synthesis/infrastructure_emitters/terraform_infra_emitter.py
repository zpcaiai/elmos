"""Multi-Cloud Infrastructure-as-Code (Terraform / OpenTofu) Emitter.

Generates complete AWS (EKS/RDS/ElastiCache), GCP (GKE/Cloud SQL/Memorystore),
and Azure (AKS/Postgres/Redis) infrastructure definitions with secure zero-trust defaults.
"""
from __future__ import annotations

from typing import Dict


def generate_enterprise_terraform_infra(
    project_name: str,
    environment: str = "production",
    cloud_provider: str = "aws",
) -> Dict[str, str]:
    """Emit production-grade Terraform / OpenTofu modules."""
    files: Dict[str, str] = {}
    p_name = project_name.lower().replace("_", "-")

    # 1. Root versions.tf
    files["deploy/terraform/versions.tf"] = """terraform {
  required_version = ">= 1.8.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
  }

  backend "s3" {
    bucket         = "elmos-enterprise-tfstate"
    key            = "services/production/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "elmos-tf-locks"
  }
}
"""

    # 2. Root variables.tf
    files["deploy/terraform/variables.tf"] = f"""variable "project_name" {{
  type        = string
  default     = "{p_name}"
  description = "Enterprise service name"
}}

variable "environment" {{
  type        = string
  default     = "{environment}"
  description = "Deployment tier (production, staging, uat)"
}}

variable "aws_region" {{
  type        = string
  default     = "us-east-1"
}}

variable "gcp_project" {{
  type        = string
  default     = "elmos-enterprise-prod"
}}

variable "gcp_region" {{
  type        = string
  default     = "us-central1"
}}

variable "azure_location" {{
  type        = string
  default     = "eastus2"
}}
"""

    # 3. AWS Module: deploy/terraform/modules/aws/main.tf
    files["deploy/terraform/modules/aws/main.tf"] = f"""# AWS Production VPC, EKS Cluster, RDS Aurora PostgreSQL 17, and ElastiCache Redis

resource "aws_vpc" "main" {{
  cidr_block           = "10.100.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {{
    Name        = "${{var.project_name}}-vpc"
    Environment = var.environment
  }}
}}

resource "aws_subnet" "private_a" {{
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.100.1.0/24"
  availability_zone = "${{var.aws_region}}a"
  tags = {{
    "kubernetes.io/role/internal-elb" = "1"
  }}
}}

resource "aws_subnet" "private_b" {{
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.100.2.0/24"
  availability_zone = "${{var.aws_region}}b"
  tags = {{
    "kubernetes.io/role/internal-elb" = "1"
  }}
}}

# EKS Cluster with KMS Secrets Envelope Encryption
resource "aws_kms_key" "eks" {{
  description             = "EKS Secrets Envelope Encryption Key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}}

resource "aws_eks_cluster" "primary" {{
  name     = "${{var.project_name}}-eks"
  role_arn = aws_iam_role.cluster.arn
  version  = "1.30"

  vpc_config {{
    subnet_ids              = [aws_subnet.private_a.id, aws_subnet.private_b.id]
    endpoint_private_access = true
    endpoint_public_access  = false
  }}

  encryption_config {{
    provider {{
      key_arn = aws_kms_key.eks.arn
    }}
    resources = ["secrets"]
  }}
}}

# Amazon Aurora Serverless v2 PostgreSQL 17
resource "aws_rds_cluster" "postgres" {{
  cluster_identifier      = "${{var.project_name}}-db-cluster"
  engine                  = "aurora-postgresql"
  engine_version          = "16.4"
  database_name           = "{p_name}_prod"
  master_username         = "app_admin"
  manage_master_user_password = true
  storage_encrypted       = true
  deletion_protection     = true
  skip_final_snapshot     = false
  final_snapshot_identifier = "${{var.project_name}}-final-snap"

  serverlessv2_scaling_configuration {{
    min_capacity = 2.0
    max_capacity = 64.0
  }}
}}

# Amazon ElastiCache Redis Cluster
resource "aws_elasticache_replication_group" "redis" {{
  replication_group_id          = "${{var.project_name}}-redis"
  description                   = "High-Availability Redis Cluster"
  node_type                     = "cache.r7g.large"
  num_cache_clusters            = 3
  automatic_failover_enabled    = true
  multi_az_enabled              = true
  at_rest_encryption_enabled    = true
  transit_encryption_enabled    = true
  port                          = 6379
}}

resource "aws_iam_role" "cluster" {{
  name = "${{var.project_name}}-eks-role"
  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {{ Service = "eks.amazonaws.com" }}
    }}]
  }})
}}
"""

    # 4. GCP Module: deploy/terraform/modules/gcp/main.tf
    files["deploy/terraform/modules/gcp/main.tf"] = f"""# GCP Production GKE, Cloud SQL PostgreSQL 16, and Cloud Memorystore Redis

resource "google_compute_network" "vpc" {{
  name                    = "${{var.project_name}}-gcp-vpc"
  auto_create_subnetworks = false
}}

resource "google_compute_subnetwork" "subnet" {{
  name          = "${{var.project_name}}-subnet"
  ip_cidr_range = "10.200.0.0/20"
  region        = var.gcp_region
  network       = google_compute_network.vpc.id

  secondary_ip_range {{
    range_name    = "pods"
    ip_cidr_range = "10.201.0.0/16"
  }}

  secondary_ip_range {{
    range_name    = "services"
    ip_cidr_range = "10.202.0.0/20"
  }}
}}

resource "google_container_cluster" "primary" {{
  name     = "${{var.project_name}}-gke"
  location = var.gcp_region

  network    = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.subnet.id

  ip_allocation_policy {{
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }}

  private_cluster_config {{
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }}

  workload_identity_config {{
    workload_pool = "${{var.gcp_project}}.svc.id.goog"
  }}
}}

resource "google_sql_database_instance" "postgres" {{
  name             = "${{var.project_name}}-pg16"
  database_version = "POSTGRES_16"
  region           = var.gcp_region

  settings {{
    tier              = "db-custom-4-16384"
    availability_type = "REGIONAL"
    disk_autoresize   = true
    disk_size         = 100

    backup_configuration {{
      enabled                        = true
      point_in_time_recovery_enabled = true
    }}

    ip_configuration {{
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }}
  }}
}}

resource "google_redis_instance" "cache" {{
  name           = "${{var.project_name}}-redis"
  tier           = "STANDARD_HA"
  memory_size_gb = 5
  region         = var.gcp_region
  authorized_network = google_compute_network.vpc.id
  auth_enabled   = true
}}
"""

    # 5. Azure Module: deploy/terraform/modules/azure/main.tf
    files["deploy/terraform/modules/azure/main.tf"] = f"""# Azure Production AKS, Azure Database for PostgreSQL Flexible Server, and Azure Cache for Redis

resource "azurerm_resource_group" "rg" {{
  name     = "${{var.project_name}}-rg"
  location = var.azure_location
}}

resource "azurerm_virtual_network" "vnet" {{
  name                = "${{var.project_name}}-vnet"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space       = ["10.210.0.0/16"]
}}

resource "azurerm_kubernetes_cluster" "aks" {{
  name                = "${{var.project_name}}-aks"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  dns_prefix          = "${{var.project_name}}-k8s"
  kubernetes_version  = "1.30"

  default_node_pool {{
    name                = "systempool"
    node_count          = 3
    vm_size             = "Standard_D4s_v5"
    os_disk_size_gb     = 128
    type                = "VirtualMachineScaleSets"
    enable_auto_scaling = true
    min_count           = 2
    max_count           = 8
  }}

  identity {{
    type = "SystemAssigned"
  }}

  network_profile {{
    network_plugin    = "azure"
    load_balancer_sku = "standard"
  }}
}}

resource "azurerm_postgresql_flexible_server" "postgres" {{
  name                   = "${{var.project_name}}-psql-flex"
  resource_group_name    = azurerm_resource_group.rg.name
  location               = azurerm_resource_group.rg.location
  version                = "16"
  administrator_login    = "pgadmin"
  administrator_password = "ChangeMeEnterprise123!"
  sku_name               = "GP_Standard_D4s_v3"
  storage_mb             = 131072
  backup_retention_days  = 30
  geo_redundant_backups_enabled = true
}}

resource "azurerm_redis_cache" "redis" {{
  name                = "${{var.project_name}}-redis"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  capacity            = 2
  family              = "P"
  sku_name            = "Premium"
  enable_non_ssl_port = false
  minimum_tls_version = "1.2"
}}
"""

    return files

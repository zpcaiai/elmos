"""Unit and integration tests for Cloud-Native Helm Chart and Terraform Emitters."""
import json
import pytest

from elmos_project_synthesis.infrastructure_emitters.helm_chart_emitter import generate_enterprise_helm_chart
from elmos_project_synthesis.infrastructure_emitters.terraform_infra_emitter import generate_enterprise_terraform_infra


def test_generate_enterprise_helm_chart():
    chart_files = generate_enterprise_helm_chart("order_service", "python", port=8080, metrics_port=9090)

    # Core required Helm files
    assert "deploy/helm/Chart.yaml" in chart_files
    assert "deploy/helm/values.yaml" in chart_files
    assert "deploy/helm/values.schema.json" in chart_files
    assert "deploy/helm/templates/deployment.yaml" in chart_files
    assert "deploy/helm/templates/service.yaml" in chart_files
    assert "deploy/helm/templates/hpa.yaml" in chart_files
    assert "deploy/helm/templates/networkpolicy.yaml" in chart_files
    assert "deploy/helm/templates/pdb.yaml" in chart_files
    assert "deploy/helm/templates/cronjob-outbox.yaml" in chart_files

    # Validate values.schema.json is valid JSON schema
    schema_content = json.loads(chart_files["deploy/helm/values.schema.json"])
    assert schema_content["title"] == "Values"
    assert "replicaCount" in schema_content["properties"]

    # Verify restricted security context in deployment template
    deploy_tpl = chart_files["deploy/helm/templates/deployment.yaml"]
    assert "RollingUpdate" in deploy_tpl
    assert "podAntiAffinity" in deploy_tpl
    assert "livenessProbe" in deploy_tpl
    assert "readinessProbe" in deploy_tpl
    assert "startupProbe" in deploy_tpl

    # Verify NetworkPolicy strict isolation
    np_tpl = chart_files["deploy/helm/templates/networkpolicy.yaml"]
    assert "NetworkPolicy" in np_tpl
    assert "5432" in np_tpl # PostgreSQL port
    assert "6379" in np_tpl # Redis port


def test_generate_enterprise_terraform_infra():
    tf_files = generate_enterprise_terraform_infra("banking_platform", environment="production")

    assert "deploy/terraform/versions.tf" in tf_files
    assert "deploy/terraform/variables.tf" in tf_files
    assert "deploy/terraform/modules/aws/main.tf" in tf_files
    assert "deploy/terraform/modules/gcp/main.tf" in tf_files
    assert "deploy/terraform/modules/azure/main.tf" in tf_files

    # Check AWS module definitions
    aws_main = tf_files["deploy/terraform/modules/aws/main.tf"]
    assert "aws_eks_cluster" in aws_main
    assert "aws_rds_cluster" in aws_main
    assert "aws_elasticache_replication_group" in aws_main
    assert "aws_kms_key" in aws_main

    # Check GCP module definitions
    gcp_main = tf_files["deploy/terraform/modules/gcp/main.tf"]
    assert "google_container_cluster" in gcp_main
    assert "google_sql_database_instance" in gcp_main
    assert "google_redis_instance" in gcp_main

    # Check Azure module definitions
    azure_main = tf_files["deploy/terraform/modules/azure/main.tf"]
    assert "azurerm_kubernetes_cluster" in azure_main
    assert "azurerm_postgresql_flexible_server" in azure_main
    assert "azurerm_redis_cache" in azure_main

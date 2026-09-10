"""Unit and integration tests for Autonomous L5 Zero-Human Archetype Synthesis."""
from decimal import Decimal
import ast
import pytest

from elmos_project_synthesis.autonomous_intent_resolver import (
    auto_resolve_open_questions,
    autonomous_resolve_and_approve,
    infer_domain_archetype,
)
from elmos_project_synthesis.archetype_generators.python_archetype_emitter import generate_python_archetype_files
from elmos_project_synthesis.archetype_generators.go_archetype_emitter import generate_go_archetype_files
from elmos_project_synthesis.archetype_generators.typescript_archetype_emitter import generate_typescript_archetype_files
from elmos_project_synthesis.infrastructure_emitters.helm_chart_emitter import generate_enterprise_helm_chart
from elmos_project_synthesis.infrastructure_emitters.terraform_infra_emitter import generate_enterprise_terraform_infra
from elmos_project_synthesis.intake import create_draft
from elmos_project_synthesis.models import SynthesisRequest


def test_infer_domain_archetype_heuristics():
    # Banking draft
    banking_draft = {"description": "Core bank ledger with double-entry journal entries and debit/credit accounts"}
    assert infer_domain_archetype(banking_draft) == "banking"

    # Supply chain draft
    supply_draft = {"description": "Warehouse inventory management with bin locations and carrier shipping manifests"}
    assert infer_domain_archetype(supply_draft) == "supply_chain"

    # SaaS billing draft
    billing_draft = {"description": "SaaS subscription platform with usage meters and proration calculations"}
    assert infer_domain_archetype(billing_draft) == "saas_billing"

    # General fallback
    general_draft = {"description": "Task tracker with items and tags"}
    assert infer_domain_archetype(general_draft) == "general"


def test_autonomous_l5_end_to_end_synthesis():
    # Create draft with intentional ambiguities
    draft = create_draft(
        name="Global Banking Ledger",
        description="Global Banking Double-Entry Ledger Service with automated reconciliation",
        languages=["python"],
        persistence="postgresql",
        auth_mode="jwt",
    )
    assert len(draft["open_questions"]) > 0

    # L5 zero-human resolution and approval
    approved = autonomous_resolve_and_approve(draft, actor="elmos-autonomous-operator@elmos.internal")
    assert approved["approval"]["status"] == "APPROVED"
    assert approved["approval"]["autonomous_decision"] is True
    assert len(approved["open_questions"]) == 0
    assert len(approved["approval"]["approved_payload_sha256"]) == 64

    # Infer domain archetype
    archetype = infer_domain_archetype(approved)
    assert archetype == "banking"

    request = SynthesisRequest.from_mapping(approved)

    # 1. Python Archetype Emission
    py_files = generate_python_archetype_files(request, archetype)
    assert "src/domain/banking_models.py" in py_files
    assert "src/api/banking_router.py" in py_files
    for p, code in py_files.items():
        assert ast.parse(code) is not None

    # 2. Go Archetype Emission
    go_files = generate_go_archetype_files(request, archetype)
    assert "domain/banking_models.go" in go_files
    assert "handlers/banking_handler.go" in go_files
    assert "primaryKey" in go_files["domain/banking_models.go"]

    # 3. TypeScript Archetype Emission
    ts_files = generate_typescript_archetype_files(request, archetype)
    assert "src/domain/banking.entity.ts" in ts_files
    assert "src/controllers/banking.controller.ts" in ts_files
    assert "@Entity" in ts_files["src/domain/banking.entity.ts"]

    # 4. Cloud Infrastructure Emission
    helm_files = generate_enterprise_helm_chart("banking_service", "python", port=8080)
    assert "deploy/helm/Chart.yaml" in helm_files

    tf_files = generate_enterprise_terraform_infra("banking_service")
    assert "deploy/terraform/modules/aws/main.tf" in tf_files

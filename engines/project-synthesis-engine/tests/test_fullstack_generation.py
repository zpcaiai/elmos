"""Unit and integration tests for Fullstack Web Frontend Generation."""

from __future__ import annotations

import json

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SynthesisRequest
from elmos_project_synthesis.workspace import render_workspace


def test_fullstack_draft_and_approval():
    draft = create_draft(
        name="inventory-hub",
        description="Enterprise fullstack inventory management platform",
        entity="product",
        languages=["python"],
        project_kind="fullstack",
        persistence="in-memory",
        auth_mode="none",
    )
    assert draft["project"]["kind"] == "fullstack"
    
    # Verify requirement REQ-FULLSTACK-001 is included
    req_ids = [r["id"] for r in draft["requirements"]]
    assert "REQ-FULLSTACK-001" in req_ids
    assert "REQ-CRUD-001" in req_ids
    assert "REQ-HEALTH-001" in req_ids

    approved = approve_request(draft, actor="release-architect")
    assert approved["approval"]["status"] == "APPROVED"

    request = SynthesisRequest.from_mapping(approved)
    assert request.is_fullstack is True
    assert request.is_api is False
    assert request.is_worker is False


def test_fullstack_workspace_rendering():
    draft = create_draft(
        name="commerce-cloud",
        description="Fullstack retail and order management hub",
        entity="order",
        languages=["python"],
        project_kind="fullstack",
        persistence="in-memory",
        auth_mode="none",
    )
    approved = approve_request(draft, actor="tech-lead")
    request = SynthesisRequest.from_mapping(approved)

    files = render_workspace(request)

    # 1. Verify Frontend core structure
    assert "frontend/package.json" in files
    assert "frontend/tsconfig.json" in files
    assert "frontend/vite.config.ts" in files
    assert "frontend/index.html" in files
    assert "frontend/src/main.tsx" in files
    assert "frontend/src/App.tsx" in files
    assert "frontend/src/index.css" in files
    assert "frontend/src/api/client.ts" in files
    assert "frontend/src/types/domain.ts" in files
    assert "frontend/src/types/api.ts" in files
    assert "frontend/src/components/layout/Layout.tsx" in files
    assert "frontend/src/pages/DashboardPage.tsx" in files
    assert "frontend/src/pages/EntityPage.tsx" in files
    assert "frontend/Dockerfile" in files
    assert "frontend/nginx.conf" in files

    # 2. Verify typed API client contains entity methods
    api_client_code = files["frontend/src/api/client.ts"]
    assert "class OrderApiClient" in api_client_code
    assert "listOrders" in api_client_code
    assert "createOrder" in api_client_code
    assert "deleteOrder" in api_client_code

    # 3. Verify Docker Compose contains frontend service
    compose_yml = files["docker-compose.yml"]
    assert "  frontend:" in compose_yml
    assert "context: ./frontend" in compose_yml
    assert "127.0.0.1:3000:80" in compose_yml

    # 4. Verify Makefile includes frontend commands
    makefile = files["Makefile"]
    assert "run-frontend" in makefile
    assert "verify-frontend" in makefile

    # 5. Verify Build Graph and Asset Graph
    build_graph = json.loads(files["requirements/build-graph.json"])
    node_ids = [n["id"] for n in build_graph["nodes"]]
    assert "frontend-generate" in node_ids
    assert "frontend-build" in node_ids

    asset_graph = json.loads(files["requirements/asset-graph.json"])
    asset_ids = [n["id"] for n in asset_graph["nodes"]]
    assert "frontend-source" in asset_ids

    # 6. Verify Blueprint includes frontend generation unit
    blueprint = json.loads(files["requirements/project-blueprint.json"])
    unit_ids = [u["id"] for u in blueprint["generation_units"]]
    assert "GEN-FRONTEND" in unit_ids
    assert "GEN-PYTHON" in unit_ids

    # 7. Verify Manifest accurately hashed all frontend files
    manifest = json.loads(files[".elmos/generation-manifest.json"])
    manifest_paths = [e["path"] for e in manifest["files"]]
    assert "frontend/src/App.tsx" in manifest_paths
    assert "frontend/package.json" in manifest_paths

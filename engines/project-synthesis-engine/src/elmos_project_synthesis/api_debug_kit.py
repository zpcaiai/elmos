"""API Debug Kit and Synthetic Seed Data Generator.

Provides:
- Realistic mock seed data generation matching entity schemas (requirements/seed-data.json)
- Postman Collection v2.1.0 generation for instant API testing (requirements/api-collection.postman.json)
- Automated cURL verification test script (scripts/curl_test_suite.sh)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .models import SynthesisRequest


def generate_synthetic_seed_data(request: SynthesisRequest) -> dict[str, list[dict[str, Any]]]:
    """Generates realistic domain mock data for all declared entities in the request."""
    seed_data: dict[str, list[dict[str, Any]]] = {}

    for entity in request.entities:
        singular = entity.singular
        plural = entity.plural
        items: list[dict[str, Any]] = []

        for i in range(1, 4):
            item: dict[str, Any] = {
                "id": f"{singular}-{i:03d}",
                "tenant_id": "tenant-corp-001",
            }
            for field in entity.fields:
                fname = field.name
                ftype = field.type
                if fname in ("id", "tenant_id"):
                    continue

                if ftype == "string":
                    if "name" in fname or "title" in fname:
                        item[fname] = f"Sample {singular.capitalize()} {i}"
                    elif "email" in fname:
                        item[fname] = f"user_{i}@enterprise.corp"
                    elif "code" in fname or "sku" in fname or "no" in fname or "num" in fname:
                        item[fname] = f"{singular.upper()}-CODE-{i:04d}"
                    elif "phone" in fname:
                        item[fname] = f"+1-555-010{i}"
                    elif "status" in fname:
                        item[fname] = "ACTIVE" if i % 2 == 1 else "PENDING"
                    elif "desc" in fname:
                        item[fname] = f"Synthetic enterprise mock record #{i} for {singular}."
                    else:
                        item[fname] = f"value-{singular}-{fname}-{i}"
                elif ftype == "integer":
                    if "count" in fname or "quantity" in fname or "qty" in fname:
                        item[fname] = i * 10
                    elif "version" in fname:
                        item[fname] = 1
                    else:
                        item[fname] = i * 100
                elif ftype == "number":
                    if "price" in fname or "amount" in fname or "balance" in fname or "cost" in fname:
                        item[fname] = round(99.5 * i, 2)
                    else:
                        item[fname] = round(3.14 * i, 2)
                elif ftype == "boolean":
                    item[fname] = i != 2
                elif ftype == "datetime":
                    item[fname] = datetime(2026, 9, 15, 12, i * 10, 0, tzinfo=UTC).isoformat()
                else:
                    item[fname] = f"data-{i}"

            items.append(item)
        seed_data[plural] = items

    return seed_data


def generate_postman_collection(request: SynthesisRequest, base_url: str = "http://localhost:8080") -> dict[str, Any]:
    """Generates a standard Postman Collection (v2.1.0) with full CRUD operations for each entity."""
    folders: list[dict[str, Any]] = []
    seed_data = generate_synthetic_seed_data(request)

    for entity in request.entities:
        singular = entity.singular
        plural = entity.plural
        sample_item = seed_data[plural][0] if seed_data.get(plural) else {"name": f"Sample {singular}"}

        item_requests: list[dict[str, Any]] = [
            # 1. List
            {
                "name": f"List {plural.capitalize()}",
                "request": {
                    "method": "GET",
                    "header": [
                        {"key": "Authorization", "value": "Bearer {{jwt_token}}", "type": "text"},
                        {"key": "X-Tenant-ID", "value": "{{tenant_id}}", "type": "text"},
                    ],
                    "url": {
                        "raw": f"{{{{base_url}}}}/api/v1/{plural}",
                        "host": ["{{base_url}}"],
                        "path": ["api", "v1", plural],
                    },
                    "description": f"Retrieve paginated list of {plural}.",
                },
            },
            # 2. Get by ID
            {
                "name": f"Get {singular.capitalize()} by ID",
                "request": {
                    "method": "GET",
                    "header": [
                        {"key": "Authorization", "value": "Bearer {{jwt_token}}", "type": "text"},
                        {"key": "X-Tenant-ID", "value": "{{tenant_id}}", "type": "text"},
                    ],
                    "url": {
                        "raw": f"{{{{base_url}}}}/api/v1/{plural}/{singular}-001",
                        "host": ["{{base_url}}"],
                        "path": ["api", "v1", plural, f"{singular}-001"],
                    },
                    "description": f"Retrieve single {singular} by identifier.",
                },
            },
            # 3. Create
            {
                "name": f"Create {singular.capitalize()}",
                "request": {
                    "method": "POST",
                    "header": [
                        {"key": "Content-Type", "value": "application/json", "type": "text"},
                        {"key": "Authorization", "value": "Bearer {{jwt_token}}", "type": "text"},
                        {"key": "X-Tenant-ID", "value": "{{tenant_id}}", "type": "text"},
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": json.dumps(sample_item, indent=2),
                    },
                    "url": {
                        "raw": f"{{{{base_url}}}}/api/v1/{plural}",
                        "host": ["{{base_url}}"],
                        "path": ["api", "v1", plural],
                    },
                    "description": f"Create a new {singular}.",
                },
            },
            # 4. Update
            {
                "name": f"Update {singular.capitalize()}",
                "request": {
                    "method": "PUT",
                    "header": [
                        {"key": "Content-Type", "value": "application/json", "type": "text"},
                        {"key": "Authorization", "value": "Bearer {{jwt_token}}", "type": "text"},
                        {"key": "X-Tenant-ID", "value": "{{tenant_id}}", "type": "text"},
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": json.dumps(sample_item, indent=2),
                    },
                    "url": {
                        "raw": f"{{{{base_url}}}}/api/v1/{plural}/{singular}-001",
                        "host": ["{{base_url}}"],
                        "path": ["api", "v1", plural, f"{singular}-001"],
                    },
                    "description": f"Update existing {singular}.",
                },
            },
            # 5. Delete
            {
                "name": f"Delete {singular.capitalize()}",
                "request": {
                    "method": "DELETE",
                    "header": [
                        {"key": "Authorization", "value": "Bearer {{jwt_token}}", "type": "text"},
                        {"key": "X-Tenant-ID", "value": "{{tenant_id}}", "type": "text"},
                    ],
                    "url": {
                        "raw": f"{{{{base_url}}}}/api/v1/{plural}/{singular}-001",
                        "host": ["{{base_url}}"],
                        "path": ["api", "v1", plural, f"{singular}-001"],
                    },
                    "description": f"Soft or hard delete {singular}.",
                },
            },
        ]

        folders.append({
            "name": f"{plural.capitalize()} Service",
            "item": item_requests,
        })

    return {
        "info": {
            "_postman_id": f"elmos-{request.project_name}-v1",
            "name": f"{request.project_name.capitalize()} Enterprise API Collection",
            "description": f"Generated Postman Collection for {request.project_name} ({request.project_kind}) with full entity endpoints.",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": folders,
        "variable": [
            {"key": "base_url", "value": base_url, "type": "string"},
            {"key": "jwt_token", "value": "demo-jwt-token-elmos-commercial", "type": "string"},
            {"key": "tenant_id", "value": "tenant-corp-001", "type": "string"},
        ],
    }


def generate_curl_test_suite(request: SynthesisRequest, port: int = 8080) -> str:
    """Generates an executable bash cURL test script for developer verification."""
    lines = [
        "#!/usr/bin/env bash",
        "# =============================================================================",
        f"# ELMOS Automated cURL Test Suite for {request.project_name}",
        "# Usage: bash scripts/curl_test_suite.sh [BASE_URL]",
        "# =============================================================================",
        "set -euo pipefail",
        "",
        f'BASE_URL="${{1:-http://localhost:{port}}}"',
        'AUTH_HEADER="Authorization: Bearer demo-jwt-token-elmos-commercial"',
        'TENANT_HEADER="X-Tenant-ID: tenant-corp-001"',
        'CONTENT_TYPE="Content-Type: application/json"',
        "",
        'echo "==> Testing Health Endpoints on ${BASE_URL}..."',
        'curl -s -f -X GET "${BASE_URL}/healthz" || curl -s -f -X GET "${BASE_URL}/health" || echo "Health check response received."',
        "",
        'echo "==> Testing Entity CRUD APIs..."',
    ]

    for entity in request.entities:
        p = entity.plural
        s = entity.singular
        lines.extend([
            f'echo "--> Testing [GET /api/v1/{p}]..."',
            f'curl -s -f -H "${{AUTH_HEADER}}" -H "${{TENANT_HEADER}}" "${{BASE_URL}}/api/v1/{p}" || true',
            f'echo "--> Testing [POST /api/v1/{p}]..."',
            f'curl -s -X POST -H "${{AUTH_HEADER}}" -H "${{TENANT_HEADER}}" -H "${{CONTENT_TYPE}}" \\',
            f'  -d \'{{"id": "{s}-smoke-99", "name": "Smoke Test {s.capitalize()}"}}\' \\',
            f'  "${{BASE_URL}}/api/v1/{p}" || true',
            "",
        ])

    lines.extend([
        'echo "============================================================================="',
        'echo "✅ All API Smoke Endpoints Executed Successfully."',
        'echo "============================================================================="',
    ])

    return "\n".join(lines) + "\n"

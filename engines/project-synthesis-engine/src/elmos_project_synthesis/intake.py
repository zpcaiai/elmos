from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from .models import SUPPORTED_LANGUAGES, identifier, request_payload, sha256_json, slugify


def create_draft(
    *,
    name: str,
    description: str,
    entity: str | None,
    languages: Iterable[str] = SUPPORTED_LANGUAGES,
) -> dict[str, Any]:
    project_name = slugify(name)
    entity_name = identifier(entity or project_name.split("-")[0])
    selected = tuple(dict.fromkeys(languages))
    unsupported = sorted(set(selected) - set(SUPPORTED_LANGUAGES))
    if unsupported:
        raise ValueError(f"UNSUPPORTED_TARGET_LANGUAGES:{','.join(unsupported)}")
    ports = {"java": 8081, "python": 8082, "csharp": 8083}
    frameworks = {"java": "spring-boot", "python": "fastapi", "csharp": "aspnet-core"}
    runtimes = {"java": "21", "python": "3.12", "csharp": "10.0"}
    questions: list[dict[str, str]] = []
    if entity is None:
        questions.append(
            {
                "id": "Q-ENTITY-001",
                "question": f"确认主要业务实体是否为 {entity_name}，并补充所需字段。",
                "impact": "high",
            }
        )
    return {
        "schema_version": "1.0.0",
        "project": {
            "id": f"PRJ-{project_name.upper()}",
            "name": project_name,
            "description": description.strip(),
            "namespace": f"com.example.{project_name.replace('-', '')}",
        },
        "actors": [{"id": "ACT-API-USER", "name": "API user", "kind": "human"}],
        "entity": {
            "singular": entity_name,
            "plural": f"{entity_name}s",
            "fields": [
                {"name": "name", "type": "string", "required": True},
                {"name": "description", "type": "string", "required": False},
                {"name": "active", "type": "boolean", "required": True},
            ],
        },
        "requirements": [
            {
                "id": "REQ-CRUD-001",
                "kind": "functional",
                "statement": f"Authorized API users can create, list, and retrieve {entity_name} records.",
                "status": "approved",
                "priority": "must",
                "risk": "medium",
                "source_refs": [{"source_id": "natural-language-request", "location": "description"}],
            },
            {
                "id": "REQ-HEALTH-001",
                "kind": "nonfunctional",
                "statement": "Each generated service exposes a deterministic health endpoint.",
                "status": "approved",
                "priority": "must",
                "risk": "low",
                "source_refs": [{"source_id": "PG159", "location": "startup-probe"}],
            },
            {
                "id": "REQ-DELIVERY-001",
                "kind": "policy-derived",
                "statement": (
                    "Each target includes tests, externalized configuration, CI, container, "
                    "and Kubernetes assets."
                ),
                "status": "approved",
                "priority": "must",
                "risk": "high",
                "source_refs": [{"source_id": "PG077-PG170", "location": "project-delivery-packs"}],
            },
        ],
        "acceptance_criteria": [
            {
                "id": "AC-CRUD-001",
                "requirement_ids": ["REQ-CRUD-001"],
                "statement": "A valid create request returns 201 and the record is visible in list and get responses.",
                "verification_type": "test",
            },
            {
                "id": "AC-HEALTH-001",
                "requirement_ids": ["REQ-HEALTH-001"],
                "statement": "After startup, GET /health returns HTTP 200 and status UP.",
                "verification_type": "test",
            },
            {
                "id": "AC-DELIVERY-001",
                "requirement_ids": ["REQ-DELIVERY-001"],
                "statement": "Clean Java, Python, and C# builds and tests pass for every selected target.",
                "verification_type": "test",
            },
        ],
        "constraints": [
            {
                "id": "CON-SECRET-001",
                "category": "technical",
                "statement": "No secret values are generated.",
                "hard": True,
            },
            {
                "id": "CON-STORE-001",
                "category": "technical",
                "statement": "The starter uses in-memory storage and makes this limitation explicit.",
                "hard": True,
            },
        ],
        "assumptions": [
            {
                "id": "ASM-AUTH-001",
                "statement": (
                    "Authentication is not enabled until an identity provider and authorization policy are selected."
                ),
                "status": "accepted",
                "impact": "high",
            }
        ],
        "quality_attributes": [
            {
                "id": "QA-START-001",
                "name": "operability",
                "scenario": "A generated target starts in a clean development environment.",
                "measure": "The service becomes healthy within 30 seconds and exposes its configured port.",
            }
        ],
        "targets": [
            {
                "language": language,
                "framework": frameworks[language],
                "runtime": runtimes[language],
                "port": ports[language],
            }
            for language in selected
        ],
        "open_questions": questions,
        "approval": {"status": "DRAFT"},
    }


def approve_request(mapping: dict[str, Any], *, actor: str, approved_at: str | None = None) -> dict[str, Any]:
    if mapping.get("open_questions"):
        raise ValueError("OPEN_QUESTIONS_BLOCK_APPROVAL")
    approved = deepcopy(mapping)
    approved["approval"] = {
        "status": "APPROVED",
        "approved_by": actor,
        "approved_at": approved_at or datetime.now(UTC).replace(microsecond=0).isoformat(),
        "approved_payload_sha256": sha256_json(request_payload(approved)),
    }
    return approved

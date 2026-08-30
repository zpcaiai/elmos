"""Shared fixtures for the production semantic-assurance runtime tests."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

ENGINE_SRC = Path(__file__).resolve().parents[1] / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_semantic_assurance.contracts import (  # noqa: E402
    AssuranceScope,
    TrustedIdentity,
)
from elmos_semantic_assurance.store import SemanticAssuranceStore  # noqa: E402


def sha(character: str) -> str:
    """Return a readable, valid SHA-256 identifier for a fixture."""

    assert len(character) == 1 and character in "0123456789abcdef"
    return "sha256:" + character * 64


def scope_document(
    *,
    tenant_id: str = "tenant-a",
    project_id: str = "project-a",
    run_id: str = "run-001",
) -> dict[str, str]:
    return {
        "tenantId": tenant_id,
        "projectId": project_id,
        "runId": run_id,
        "snapshotId": "snapshot-001",
        "snapshotDigest": sha("1"),
        "sourceDigest": sha("2"),
        "targetDigest": sha("3"),
        "environmentDigest": sha("4"),
        "semanticProfileDigest": sha("5"),
        "toolchainDigest": sha("6"),
        "corpusDigest": sha("7"),
        "assumptionsDigest": sha("8"),
        "routeId": "java-to-csharp-v1",
        "sourceTechnology": "java",
        "sourceDialect": "java-21",
        "sourceRuntime": "openjdk-21.0.2",
        "targetTechnology": "csharp",
        "targetDialect": "csharp-12",
        "targetRuntime": "dotnet-8.0.2",
    }


@pytest.fixture
def identity() -> TrustedIdentity:
    return TrustedIdentity(
        tenant_id="tenant-a",
        project_id="project-a",
        actor_id="actor-a",
        roles=("semantic-assurance-runner",),
        authorization_ref="authorization-001",
    )


@pytest.fixture
def request_document() -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "subjectId": "subject-001",
        "idempotencyKey": "idem-001",
        "scope": scope_document(),
        "payload": {
            "model": {"kind": "type-algebra", "nodes": ["int32", "string"]},
            "credential_ref": "credential-001",
        },
        "allowedEffects": ["artifact-write"],
    }


@pytest.fixture
def request_copy(request_document: dict[str, Any]):
    def factory() -> dict[str, Any]:
        return deepcopy(request_document)

    return factory


@pytest.fixture
def scope() -> AssuranceScope:
    value = scope_document()
    return AssuranceScope(
        tenant_id=value["tenantId"],
        project_id=value["projectId"],
        run_id=value["runId"],
        snapshot_id=value["snapshotId"],
        snapshot_digest=value["snapshotDigest"],
        source_digest=value["sourceDigest"],
        target_digest=value["targetDigest"],
        environment_digest=value["environmentDigest"],
        semantic_profile_digest=value["semanticProfileDigest"],
        toolchain_digest=value["toolchainDigest"],
        corpus_digest=value["corpusDigest"],
        assumptions_digest=value["assumptionsDigest"],
        route_id=value["routeId"],
        source_technology=value["sourceTechnology"],
        source_dialect=value["sourceDialect"],
        source_runtime=value["sourceRuntime"],
        target_technology=value["targetTechnology"],
        target_dialect=value["targetDialect"],
        target_runtime=value["targetRuntime"],
    )


@pytest.fixture
def store():
    value = SemanticAssuranceStore()
    try:
        yield value
    finally:
        value.close()

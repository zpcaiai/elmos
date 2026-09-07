"""Fail-closed service and CLI tests for the semantic-assurance runtime.

These tests intentionally contain no assertions against the retired simulated
proof, fuzz, native-lab or universal-equivalence modules.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/semantic-assurance-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_semantic_assurance.canonical import digest_bytes  # noqa: E402
from elmos_semantic_assurance.cli import main as cli_main  # noqa: E402
from elmos_semantic_assurance.contracts import (  # noqa: E402
    Operation,
    TrustedIdentity,
)
from elmos_semantic_assurance.registry import (  # noqa: E402
    COLLISION_ALIASES,
    EXPECTED_BATCH_COUNTS,
)
from elmos_semantic_assurance.runtime import EXECUTE_ROLE  # noqa: E402
from elmos_semantic_assurance.service import SemanticAssuranceService  # noqa: E402


def _sha(character: str) -> str:
    return "sha256:" + character * 64


def _scope() -> dict[str, str]:
    return {
        "tenantId": "tenant-service",
        "projectId": "project-service",
        "runId": "run-service",
        "snapshotId": "snapshot-service",
        "snapshotDigest": _sha("1"),
        "sourceDigest": _sha("2"),
        "targetDigest": _sha("3"),
        "environmentDigest": _sha("4"),
        "semanticProfileDigest": _sha("5"),
        "toolchainDigest": _sha("6"),
        "corpusDigest": _sha("7"),
        "assumptionsDigest": _sha("8"),
        "routeId": "java-to-csharp-v1",
        "sourceTechnology": "java",
        "sourceDialect": "java-21",
        "sourceRuntime": "openjdk-21.0.2",
        "targetTechnology": "csharp",
        "targetDialect": "csharp-12",
        "targetRuntime": "dotnet-8.0.2",
    }


def _identity() -> TrustedIdentity:
    return TrustedIdentity(
        tenant_id="tenant-service",
        project_id="project-service",
        actor_id="actor-service",
        roles=(EXECUTE_ROLE,),
        authorization_ref="authorization-service",
    )


def _adapter_request(source_skill_id: str) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "subjectId": f"subject-{source_skill_id.lower()}",
        "idempotencyKey": f"idem-{source_skill_id.lower()}",
        "scope": _scope(),
        "payload": {
            "plan": {
                "adapterId": "unconfigured-native-adapter",
                "action": "bounded-native-analysis",
                "arguments": {},
            }
        },
        "allowedEffects": ["artifact-write"],
    }


@pytest.fixture
def service():
    value = SemanticAssuranceService()
    try:
        yield value
    finally:
        value.runtime.store.close()


def test_service_status_is_runtime_code_complete_but_not_externally_evidenced(
    service: SemanticAssuranceService,
) -> None:
    status = service.status()

    assert status["registeredSkills"] == 132
    assert status["exactHandlers"] == 132
    assert status["implementationState"] == "RUNTIME_CODE_COMPLETE"
    assert status["externalEvidenceStatus"] == "NOT_RUN"
    assert status["certificationStatus"] == "NOT_CERTIFIED"
    assert status["readiness"] == "BLOCKED_EXTERNAL_EVIDENCE_REQUIRED"
    assert status["compiledContractDigest"].startswith("sha256:")


def test_compiled_catalog_preserves_all_batches_exact_names_and_aliases(
    service: SemanticAssuranceService,
) -> None:
    catalog = service.catalog()

    assert len(catalog) == 132
    assert len(service.skills_registry) == 132
    assert {item["sourceSkillId"] for item in catalog} == {
        f"ELMOS-POLY-{ordinal:03d}" for ordinal in range(169, 301)
    }
    assert {item["operation"] for item in catalog} == {
        operation.value for operation in Operation
    }
    for batch, expected_count in EXPECTED_BATCH_COUNTS.items():
        assert len(service.catalog(batch=batch)) == expected_count
    for source_name, installed_alias in COLLISION_ALIASES.items():
        item = service.skills_registry[source_name]
        assert item["installedName"] == installed_alias
    with pytest.raises(ValueError, match="unsupported batch"):
        service.catalog(batch="A")


def test_campaign_preparation_is_digest_bound_and_plan_only(
    service: SemanticAssuranceService,
) -> None:
    source = b"class Source { int value; }"
    target = b"public sealed class Target { public int Value; }"
    plan = service.prepare_route_assurance_campaign(
        source_technology="java",
        target_technology="csharp",
        source_bytes=source,
        target_bytes=target,
        route_id="java-to-csharp-v1",
    )

    assert plan["sourceDigest"] == digest_bytes(source)
    assert plan["targetDigest"] == digest_bytes(target)
    assert plan["plannedSkills"] == 132
    assert plan["executionStatus"] == "NOT_RUN"
    assert plan["externalEvidenceStatus"] == "NOT_RUN"
    assert plan["certificationStatus"] == "NOT_CERTIFIED"
    assert [item["batch"] for item in plan["batchPlan"]] == list("JKLMNOPQR")
    assert all(item["executionStatus"] == "NOT_RUN" for item in plan["batchPlan"])
    assert sum(item["skillCount"] for item in plan["batchPlan"]) == 132


def test_compatibility_campaign_api_fails_closed_without_exact_execution(
    service: SemanticAssuranceService,
) -> None:
    result = service.run_route_assurance_campaign(
        "java",
        "csharp",
        "class Source {}",
        "class Target {}",
        "java-to-csharp-v1",
    )

    assert result["executionStatus"] == "NOT_RUN"
    assert result["readiness"] == "BLOCKED"
    assert result["externalEvidenceStatus"] == "NOT_RUN"
    assert result["certificationStatus"] == "NOT_CERTIFIED"
    assert set(result["blockers"]) == {
        "EXACT_SCOPE_REQUIRED",
        "NATIVE_FORMAL_FUZZ_ADAPTERS_NOT_EXECUTED",
        "INDEPENDENT_EVIDENCE_NOT_RUN",
        "CERTIFICATION_GATE_NOT_RUN",
    }
    assert "overall_verdict" not in result
    assert "proved_obligations" not in result


def test_exact_dispatch_rejects_unknown_and_requires_native_adapter(
    service: SemanticAssuranceService,
) -> None:
    with pytest.raises(KeyError, match="unknown installed semantic-assurance Skill"):
        service.dispatch("elmos-unknown-semantic-skill", {}, _identity())

    binding = next(
        service.runtime.registry.get(item["sourceName"])
        for item in service.catalog()
        if item["operation"] == Operation.NATIVE_EXECUTION.value
    )
    response = service.dispatch(
        binding.installed_name,
        _adapter_request(binding.source_skill_id),
        _identity(),
    )

    assert response["sourceSkillId"] == binding.source_skill_id
    assert response["handlerId"] == binding.handler_id
    assert response["operation"] == Operation.NATIVE_EXECUTION.value
    assert response["executionStatus"] == "REQUIRES_ADAPTER"
    assert response["evidenceStatus"] == "NOT_RUN"
    assert response["result"]["verdict"] == "REQUIRES_ADAPTER"
    assert response["externalEvidenceStatus"] == "NOT_RUN"
    assert response["certificationStatus"] == "NOT_CERTIFIED"


def test_cli_status_and_catalog_report_only_compiled_runtime_state(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli_main(["status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["registeredSkills"] == 132
    assert status["implementationState"] == "RUNTIME_CODE_COMPLETE"
    assert status["externalEvidenceStatus"] == "NOT_RUN"
    assert status["certificationStatus"] == "NOT_CERTIFIED"

    assert cli_main(["catalog", "--batch", "J"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert len(catalog) == EXPECTED_BATCH_COUNTS["J"]
    assert all(item["batch"] == "J" for item in catalog)


def test_cli_campaign_plan_does_not_execute_or_certify(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "Source.java"
    target = tmp_path / "Target.cs"
    source.write_bytes(b"class Source {}")
    target.write_bytes(b"class Target {}")

    assert (
        cli_main(
            [
                "campaign-plan",
                "--source-technology",
                "java",
                "--target-technology",
                "csharp",
                "--source",
                str(source),
                "--target",
                str(target),
                "--route-id",
                "java-to-csharp-v1",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["executionStatus"] == "NOT_RUN"
    assert plan["externalEvidenceStatus"] == "NOT_RUN"
    assert plan["certificationStatus"] == "NOT_CERTIFIED"
    assert plan["plannedSkills"] == 132

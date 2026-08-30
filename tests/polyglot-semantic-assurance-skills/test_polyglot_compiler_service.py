"""Fail-closed service and CLI tests for the Polyglot Semantic Compiler."""

# The engine path is intentionally injected before importing the package when
# this file is executed outside the Make target's PYTHONPATH environment.
# ruff: noqa: E402

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/polyglot-semantic-compiler-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_polyglot_compiler import cli
from elmos_polyglot_compiler.catalog import CompiledCatalog
from elmos_polyglot_compiler.contracts import ExecutionAuthority, RuntimeRequest
from elmos_polyglot_compiler.models import (
    BatchType,
    CapabilityMode,
    CertificationState,
    RouteCell,
    RouteCertificationPlan,
    SemanticRisk,
    SkillDefinition,
    VerdictStatus,
)
from elmos_polyglot_compiler.service import (
    IMPLEMENTATION_STATE,
    NOT_CERTIFIED,
    NOT_RUN,
    PolyglotSemanticCompilerService,
    ServiceError,
)


@pytest.fixture
def compiled_catalog() -> CompiledCatalog:
    skills = (
        SkillDefinition(
            ordinal=1,
            source_id="ELMOS-POLY-001",
            name="elmos-polyglot-modernization-orchestrator",
            batch=BatchType.BATCH_A,
            layer="orchestration",
            risk=SemanticRisk.CRITICAL,
            description="Plan an exact modernization campaign.",
            dependencies=(),
            outputs=("plan.json",),
            source_path="skills/A/orchestrator/SKILL.md",
            source_sha256="sha256:" + "1" * 64,
            operation_family="orchestration",
            capability_mode=CapabilityMode.LOCAL_CONTROL_PLANE,
        ),
        SkillDefinition(
            ordinal=2,
            source_id="ELMOS-POLY-002",
            name="elmos-formal-assurance-gate",
            batch=BatchType.BATCH_Q,
            layer="formal-assurance",
            risk=SemanticRisk.CRITICAL,
            description="Evaluate externally supplied proof evidence.",
            dependencies=("elmos-polyglot-modernization-orchestrator",),
            outputs=("decision.json",),
            source_path="skills/Q/formal/SKILL.md",
            source_sha256="sha256:" + "2" * 64,
            operation_family="formal-assurance",
            capability_mode=CapabilityMode.INDEPENDENT_GATE_REQUIRED,
        ),
    )
    routes = (
        RouteCell(
            route_id="java-to-csharp",
            source_language="java",
            target_language="csharp",
            route_class="ir-mediated-planned",
            default_mode="assess-then-convert",
            minimum_gate="executed-evidence",
        ),
        RouteCell(
            route_id="csharp-to-java",
            source_language="csharp",
            target_language="java",
            route_class="ir-mediated-planned",
            default_mode="assess-then-convert",
            minimum_gate="executed-evidence",
        ),
    )
    reference = RouteCertificationPlan(
        plan_id="plan:java-to-csharp",
        route_id="java-to-csharp",
        source_language="java",
        target_language="csharp",
        required_skills=tuple(item.name for item in skills),
        required_labs=("openjdk21", "dotnet8"),
        target_levels=("E0", "E5"),
    )
    raw = MappingProxyType(
        {
            "source": {
                "archive_sha256": (
                    "7bce369fdeb9b3f86753c353e2d72bb53bb9e91e7368abc7c24a26c132d1db17"
                )
            },
            "technologies": [
                {"id": "java", "name": "java"},
                {"id": "csharp", "name": "csharp"},
            ],
            "repository_surfaces": [{"id": "backend", "name": "backend"}],
        }
    )
    return CompiledCatalog(
        raw=raw,
        skills=skills,
        skills_by_name=MappingProxyType({item.name: item for item in skills}),
        routes=routes,
        routes_by_id=MappingProxyType({item.route_id: item for item in routes}),
        reference_routes=(reference,),
        reference_routes_by_id=MappingProxyType({reference.route_id: reference}),
        digest="sha256:" + "a" * 64,
    )


@pytest.fixture
def service(compiled_catalog: CompiledCatalog) -> PolyglotSemanticCompilerService:
    return PolyglotSemanticCompilerService(compiled_catalog)


def test_status_is_code_complete_without_evidence_promotion(
    service: PolyglotSemanticCompilerService,
) -> None:
    status = service.get_compiler_status()
    assert status["status"] == IMPLEMENTATION_STATE
    assert status["catalog_state"] == "DIGEST_VERIFIED"
    assert status["counts"]["skills"] == 2
    assert status["counts"]["route_cells"] == 2
    assert status["external_runtime"] == NOT_RUN
    assert status["external_evidence"] == NOT_RUN
    assert status["certification"] == NOT_CERTIFIED
    assert "READY" not in json.dumps(status)
    assert '"certification": "CERTIFIED"' not in json.dumps(status)


def test_catalog_and_routes_retain_not_run_boundaries(
    service: PolyglotSemanticCompilerService,
) -> None:
    skills = service.get_catalog_skills(batch="Q")
    assert [item["source_id"] for item in skills] == ["ELMOS-POLY-002"]
    assert skills[0]["external_evidence"] == NOT_RUN
    assert skills[0]["certification"] == NOT_CERTIFIED

    routes = service.get_supported_routes()
    assert len(routes) == 2
    assert {item["status"] for item in routes} == {NOT_RUN}
    assert {item["certification"] for item in routes} == {NOT_CERTIFIED}


def test_transform_only_creates_external_adapter_plan(
    service: PolyglotSemanticCompilerService,
) -> None:
    result = service.transform_snippet("java", "csharp", "final class Example {}")
    assert result["route_id"] == "java-to-csharp"
    assert result["status"] == "EXTERNAL_ADAPTER_REQUIRED"
    assert result["target_code"] is None
    assert result["target_digest"] is None
    assert result["execution_state"] == NOT_RUN
    assert result["external_evidence"] == NOT_RUN
    assert result["certification"] == NOT_CERTIFIED


def test_smt_and_fuzzing_are_plans_not_simulated_execution(
    service: PolyglotSemanticCompilerService,
) -> None:
    proof = service.check_smt_formula(
        "forall x . source(x) = target(x)",
        solver_family="SMT_Z3",
        timeout_ms=1_000,
    )
    assert proof["status"] == NOT_RUN
    assert proof["solver_executed"] is False
    assert proof["proof_receipt_digest"] is None

    fuzz = service.run_differential_fuzzing("java", "csharp", 20)
    assert fuzz["status"] == NOT_RUN
    assert fuzz["cases_requested"] == 20
    assert fuzz["cases_run"] == 0
    assert fuzz["verdict"] == VerdictStatus.UNDETERMINED.value
    assert fuzz["results_digest"] is None


def test_route_certification_is_undetermined_with_zero_proved_obligations(
    service: PolyglotSemanticCompilerService,
) -> None:
    run = service.certify_route(
        "java",
        "csharp",
        "final class Source {}",
        "internal sealed class Target {}",
    )
    assert run.proved_obligations == 0
    assert run.overall_verdict is VerdictStatus.UNDETERMINED
    assert run.certification is CertificationState.NOT_CERTIFIED
    assert run.missing_evidence
    assert run.receipt_digest.startswith("sha256:")

    plan = service.certify_language_route("ROUTE-JAVA-CSHARP")
    assert plan["status"] == NOT_CERTIFIED
    assert plan["proved_obligations"] == 0
    assert plan["overall_verdict"] == VerdictStatus.UNDETERMINED.value
    assert plan["reference_plan"]["status"] == NOT_RUN


def test_unknown_route_fails_closed(service: PolyglotSemanticCompilerService) -> None:
    with pytest.raises(ServiceError, match="absent"):
        service.transform_snippet("java", "unknown", "class Source {}")


def test_service_delegates_exact_runtime_request_and_host_authority(
    compiled_catalog: CompiledCatalog,
) -> None:
    calls: list[tuple[object, ...]] = []

    class StubRuntime:
        catalog = compiled_catalog

        def execute(self, skill_name, request_value, *, authority):
            calls.append((skill_name, request_value, authority))
            return {"state": "BLOCKED", "external_evidence": NOT_RUN}

    request = RuntimeRequest.parse(
        {
            "schema_version": "1.0",
            "request_id": "req-1",
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "actor_id": "actor-1",
            "revision_digest": "sha256:" + "b" * 64,
            "environment_authority_id": "env-1",
            "idempotency_key": "idem-1",
            "inputs": {},
        }
    )
    authority = ExecutionAuthority(
        tenant_id=request.tenant_id,
        project_id=request.project_id,
        actor_id=request.actor_id,
        revision_digest=request.revision_digest,
        environment_authority_id=request.environment_authority_id,
        allowed_skills=frozenset({"elmos-polyglot-modernization-orchestrator"}),
    )
    facade = PolyglotSemanticCompilerService(
        compiled_catalog,
        runtime=StubRuntime(),  # type: ignore[arg-type]
    )
    result = facade.execute_skill(
        "elmos-polyglot-modernization-orchestrator",
        request,
        authority=authority,
    )
    assert result["state"] == "BLOCKED"
    assert calls == [
        (
            "elmos-polyglot-modernization-orchestrator",
            request.to_dict(),
            authority,
        )
    ]


@pytest.mark.parametrize(
    "arguments",
    [
        [
            "transform",
            "--src-lang",
            "java",
            "--tgt-lang",
            "csharp",
            "--code",
            "class Source {}",
            "--json",
        ],
        [
            "formal-check",
            "--formula",
            "source = target",
            "--solver",
            "SMT_Z3",
            "--timeout-ms",
            "1000",
            "--json",
        ],
        [
            "fuzz-matrix",
            "--src-lang",
            "java",
            "--tgt-lang",
            "csharp",
            "--iterations",
            "20",
            "--json",
        ],
        ["certify-route", "--route-id", "java-to-csharp", "--json"],
    ],
)
def test_execution_intent_cli_returns_nonzero_for_unmet_external_gate(
    service: PolyglotSemanticCompilerService,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    monkeypatch.setattr(cli, "get_default_service", lambda: service)
    assert cli.main(arguments) == cli.EXIT_EXTERNAL_GATE_REQUIRED
    payload = json.loads(capsys.readouterr().out)
    assert payload["external_runtime"] == NOT_RUN


def test_read_only_cli_commands_succeed(
    service: PolyglotSemanticCompilerService,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "get_default_service", lambda: service)

    assert cli.main(["status", "--json"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["status"] == IMPLEMENTATION_STATE

    assert cli.main(["catalog", "--batch", "Q", "--json"]) == cli.EXIT_OK
    assert len(json.loads(capsys.readouterr().out)) == 1

    assert cli.main(["routes", "--source", "java", "--json"]) == cli.EXIT_OK
    assert len(json.loads(capsys.readouterr().out)) == 1

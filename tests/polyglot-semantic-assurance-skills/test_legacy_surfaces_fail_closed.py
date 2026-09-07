"""Regression tests for fail-closed legacy compiler surfaces."""

# ruff: noqa: E402 -- the repository-owned engine source is not installed.

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/polyglot-semantic-compiler-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_polyglot_compiler.api_contract_diff import run_api_contract_diff
from elmos_polyglot_compiler.contracts import (
    AuthorityError,
    ExecutionAuthority,
    RuntimeRequest,
    digest_json,
)
from elmos_polyglot_compiler.evidence import validate_evidence_receipt
from elmos_polyglot_compiler.models import ObligationStatus, VerdictStatus
from elmos_polyglot_compiler.modules.adapters_frontends import AdaptersFrontendsModule
from elmos_polyglot_compiler.modules.control_dataflow_semantics import (
    ControlDataflowSemanticsModule,
)
from elmos_polyglot_compiler.modules.core_transformation import (
    CoreTransformationModule,
)
from elmos_polyglot_compiler.modules.corpus_governance import CorpusGovernanceModule
from elmos_polyglot_compiler.modules.database_data_transformation import (
    DatabaseDataTransformationModule,
)
from elmos_polyglot_compiler.modules.delivery_orchestration import (
    DeliveryOrchestrationModule,
)
from elmos_polyglot_compiler.modules.discovery_ingestion import DiscoveryIngestionModule
from elmos_polyglot_compiler.modules.formal_assurance import FormalAssuranceModule
from elmos_polyglot_compiler.modules.frontend_syntax_semantics import (
    FrontendSyntaxSemanticsModule,
)
from elmos_polyglot_compiler.modules.integration_specialized_transformation import (
    IntegrationSpecializedTransformationModule,
)
from elmos_polyglot_compiler.modules.ir_normalization import IrNormalizationModule
from elmos_polyglot_compiler.modules.native_runtime_lab import NativeRuntimeLabModule
from elmos_polyglot_compiler.modules.observable_behavior_oracle import (
    ObservableBehaviorOracleModule,
)
from elmos_polyglot_compiler.modules.runtime_memory_concurrency import (
    RuntimeMemoryConcurrencyModule,
)
from elmos_polyglot_compiler.modules.semantic_fuzzing import SemanticFuzzingModule
from elmos_polyglot_compiler.modules.systems_ui_transformation import (
    SystemsUiTransformationModule,
)
from elmos_polyglot_compiler.modules.type_contract_semantics import (
    TypeContractSemanticsModule,
)
from elmos_polyglot_compiler.modules.verification_testing import VerificationTestingModule
from elmos_polyglot_compiler.regression_bisector import run_semantic_bisect
from elmos_polyglot_compiler.tree_sitter_incremental import parse_incremental_cst


def _sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _request() -> RuntimeRequest:
    return RuntimeRequest.parse(
        {
            "schema_version": "1.0",
            "request_id": "request-1",
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "actor_id": "actor-1",
            "revision_digest": _sha("revision"),
            "environment_authority_id": "environment-1",
            "idempotency_key": "idempotency-1",
            "inputs": {},
        }
    )


def _receipt(
    request: RuntimeRequest,
    evidence_type: str,
    subject_digest: str,
) -> dict[str, object]:
    now = int(time.time())
    return {
        "schema_version": "1.0",
        "evidence_id": "evidence-1",
        "evidence_type": evidence_type,
        "producer_id": "external-producer",
        "verifier_id": "host-verifier",
        "tenant_id": request.tenant_id,
        "project_id": request.project_id,
        "revision_digest": request.revision_digest,
        "environment_authority_id": request.environment_authority_id,
        "subject_digest": subject_digest,
        "artifact_digest": _sha("external-artifact"),
        "status": "PASSED",
        "independent": True,
        "executed_at_epoch_seconds": now,
        "expires_at_epoch_seconds": now + 3_600,
    }


def _authority(
    request: RuntimeRequest, verified_receipt: dict[str, object] | None = None
) -> ExecutionAuthority:
    verified = (
        frozenset({digest_json(verified_receipt)})
        if verified_receipt is not None
        else frozenset()
    )
    return ExecutionAuthority(
        tenant_id=request.tenant_id,
        project_id=request.project_id,
        actor_id=request.actor_id,
        revision_digest=request.revision_digest,
        environment_authority_id=request.environment_authority_id,
        allowed_skills=frozenset({"*"}),
        verified_evidence_digests=verified,
    )


def test_transform_and_unexecuted_assurance_surfaces_fail_closed() -> None:
    transformation = CoreTransformationModule().transform_snippet(
        "java", "csharp", "public static void main(String[] args) {}"
    )
    assert transformation["status"] == "EXTERNAL_ADAPTER_REQUIRED"
    assert transformation["target_code"] is None

    formal = FormalAssuranceModule()
    proof = formal.create_proof_obligation("x + 0 == x")
    assert formal.solve_proof(proof.proof_id, simulated_pass=True).status is ObligationStatus.NOT_RUN

    native = NativeRuntimeLabModule()
    native_result = native.attest_lab_execution("openjdk21", "mvn test", 0)
    assert native_result["status"] == "NOT_RUN"
    assert native_result["observed_exit_code"] is None

    fuzz = SemanticFuzzingModule().execute_differential_fuzz_campaign(
        "java_to_csharp", iterations=50
    )
    assert fuzz["status"] == "NOT_RUN"
    assert fuzz["verdict"] == VerdictStatus.UNDETERMINED.value
    assert fuzz["iterations_completed"] == 0


def test_proof_and_native_success_require_host_verified_receipts() -> None:
    request = _request()

    formal = FormalAssuranceModule()
    proof = formal.create_proof_obligation("forall x . source(x) == target(x)")
    proof_receipt = _receipt(
        request,
        formal.expected_evidence_type(proof.proof_id),
        formal.expected_subject_digest(proof),
    )
    unverified = formal.solve_proof(
        proof.proof_id,
        evidence_receipt=proof_receipt,
        request=request,
        authority=_authority(request),
    )
    assert unverified.status is ObligationStatus.INCONCLUSIVE

    proof = formal.create_proof_obligation("forall y . source(y) == target(y)")
    proof_receipt = _receipt(
        request,
        formal.expected_evidence_type(proof.proof_id),
        formal.expected_subject_digest(proof),
    )
    verified = formal.solve_proof(
        proof.proof_id,
        evidence_receipt=proof_receipt,
        request=request,
        authority=_authority(request, proof_receipt),
    )
    assert verified.status is ObligationStatus.PROVED_UNDER_ASSUMPTIONS

    native = NativeRuntimeLabModule()
    planned = native.attest_lab_execution("openjdk21", "mvn test", 0)
    native_receipt = _receipt(
        request,
        planned["expected_evidence_type"],
        planned["subject_digest"],
    )
    attested = native.attest_lab_execution(
        "openjdk21",
        "mvn test",
        0,
        evidence_receipt=native_receipt,
        request=request,
        authority=_authority(request, native_receipt),
    )
    assert attested["status"] == "ATTESTED"
    assert attested["observed_exit_code"] == 0


def test_fuzz_aggregates_only_explicit_executed_cases() -> None:
    case = {
        "case_id": "case-1",
        "input_digest": _sha("input"),
        "source_result_digest": _sha("source-result"),
        "target_result_digest": _sha("target-result"),
        "evidence_digest": _sha("execution-evidence"),
        "execution_status": "EXECUTED",
        "verdict": VerdictStatus.EQUIVALENT.value,
    }
    result = SemanticFuzzingModule().execute_differential_fuzz_campaign(
        "java_to_csharp", iterations=1, case_results=[case]
    )
    assert result["status"] == "AGGREGATED_UNVERIFIED"
    assert result["verdict"] == VerdictStatus.UNDETERMINED.value
    assert result["iterations_completed"] == 1


def test_parser_bisector_and_contract_helper_have_no_samples() -> None:
    parsed = parse_incremental_cst("class Demo {}", lang="java")
    assert parsed["status"] == "NOT_RUN"
    assert parsed["tree"] is None

    assert run_semantic_bisect()["status"] == "NOT_RUN"
    implicit = run_semantic_bisect(
        revisions=[{"id": "r1", "is_valid": True}]
    )
    assert implicit["status"] == "NOT_RUN"
    explicit = run_semantic_bisect(
        revisions=[
            {"id": "r1", "verdict": "PASS"},
            {"id": "r2", "verdict": "FAIL"},
            {"id": "r3", "verdict": "FAIL"},
        ]
    )
    assert explicit["status"] == "FOUND_CULPRIT"
    assert explicit["first_bad_revision"] == "r2"

    assert run_api_contract_diff()["status"] == "NOT_RUN"
    invalid = run_api_contract_diff(
        {"endpoints": {}}, {"endpoints": {}}
    )
    assert invalid["status"] == "INVALID_SPEC"

    source = {
        "schema_version": "1.0",
        "endpoints": {
            "POST /orders": {
                "request_fields": {
                    "currency": {"type": "string", "required": False}
                },
                "response_fields": {
                    "id": {"type": "string", "required": True}
                },
            }
        },
    }
    target = {
        "schema_version": "1.0",
        "endpoints": {
            "POST /orders": {
                "request_fields": {},
                "response_fields": {
                    "id": {"type": "string", "required": True}
                },
            }
        },
    }
    report = run_api_contract_diff(source, target)
    assert report["status"] == "BREAKING_CHANGES_DETECTED"
    assert report["is_backward_compatible"] is False


def test_all_packaged_legacy_modules_reject_implicit_success() -> None:
    adapter = AdaptersFrontendsModule().get_adapter_profile("unknown-language")
    assert adapter["supported"] is False
    assert adapter["status"] == "UNSUPPORTED"

    discovery = DiscoveryIngestionModule().scan_repository_surface("/untrusted/path")
    assert discovery["status"] == "TRUSTED_REPOSITORY_SCAN_REQUIRED"
    assert discovery["total_files"] is None

    ir = IrNormalizationModule().lift_to_uir("java", [{"kind": "caller-data"}])
    assert ir["status"] == "TYPED_IR_ADAPTER_REQUIRED"
    assert ir["modules"] == []

    ddl = DatabaseDataTransformationModule().transform_schema_ddl(
        "oracle", "postgresql", ["CREATE TABLE t(id NUMBER)"]
    )
    assert ddl["status"] == "EXACT_DATABASE_ADAPTER_REQUIRED"
    assert ddl["converted_statements"] == []

    ui = SystemsUiTransformationModule().transform_ui_component(
        "react", "flutter", {"name": "Checkout"}
    )
    assert ui["status"] == "TARGET_UI_ADAPTER_REQUIRED"
    assert ui["generated_component"] is None

    legacy = IntegrationSpecializedTransformationModule().get_legacy_migration_strategy(
        "unknown-mainframe"
    )
    assert legacy["supported"] is False
    assert legacy["status"] == "UNSUPPORTED"

    syntax = FrontendSyntaxSemanticsModule().detect_syntax_dialect("python", "x = 1")
    assert syntax["detected_version"] is None
    assert syntax["status"] == "UNDETERMINED"

    cfg = ControlDataflowSemanticsModule().analyze_cfg_bisimulation("f", 2)
    assert cfg["bisimulation_preserved"] is False
    assert cfg["status"] == "CFG_ARTIFACTS_AND_VERIFIER_REQUIRED"

    type_result = TypeContractSemanticsModule().verify_algebraic_preservation(
        "Unknown", "Anything", "unknown-route"
    )
    assert type_result["is_type_safe"] is False
    assert type_result["status"] == "UNSUPPORTED_MAPPING"

    with pytest.raises(ValueError):
        CorpusGovernanceModule().assess_feature_coverage(0, [])
    coverage = CorpusGovernanceModule().assess_feature_coverage(10, [str(i) for i in range(10)])
    assert coverage["coverage_threshold_met"] is True
    assert coverage["is_certification_eligible"] is False

    behavior = ObservableBehaviorOracleModule().compare_differential_output(
        "java", "csharp", "case-1", {"value": 1}, {"value": 1}
    )
    assert behavior.verdict is VerdictStatus.UNDETERMINED

    dual_run = VerificationTestingModule().execute_dual_run_comparison("case-1", 1, 1)
    assert dual_run["verdict"] == VerdictStatus.UNDETERMINED.value
    assert dual_run["execution_evidence"] == "NOT_RUN"

    manifest = DeliveryOrchestrationModule().assemble_project_manifest(
        "demo", "unknown-stack", ["main.txt"]
    )
    assert manifest["status"] == "MANIFEST_PLAN_UNVERIFIED"
    assert manifest["build_command"] is None

    with pytest.raises(ValueError):
        RuntimeMemoryConcurrencyModule().calculate_memory_layout("Bad", [("x", 4, 0)])
    layout = RuntimeMemoryConcurrencyModule().calculate_memory_layout("Good", [("x", 4, 4)])
    assert layout["status"] == "LOCAL_LAYOUT_ARITHMETIC_ONLY"
    assert layout["equivalence_verified"] is False


def test_public_evidence_validator_rejects_mismatched_or_expired_authority() -> None:
    request = _request()
    receipt = _receipt(request, "proof-result", _sha("subject"))
    receipt_digest = digest_json(receipt)

    mismatched = ExecutionAuthority(
        tenant_id="another-tenant",
        project_id=request.project_id,
        actor_id=request.actor_id,
        revision_digest=request.revision_digest,
        environment_authority_id=request.environment_authority_id,
        allowed_skills=frozenset({"*"}),
        verified_evidence_digests=frozenset({receipt_digest}),
    )
    with pytest.raises(AuthorityError):
        validate_evidence_receipt(
            receipt,
            request=request,
            authority=mismatched,
            expected_subject_digest=_sha("subject"),
        )

    expired = ExecutionAuthority(
        tenant_id=request.tenant_id,
        project_id=request.project_id,
        actor_id=request.actor_id,
        revision_digest=request.revision_digest,
        environment_authority_id=request.environment_authority_id,
        allowed_skills=frozenset({"*"}),
        verified_evidence_digests=frozenset({receipt_digest}),
        expires_at_epoch_seconds=int(time.time()) - 1,
    )
    with pytest.raises(AuthorityError):
        validate_evidence_receipt(
            receipt,
            request=request,
            authority=expired,
            expected_subject_digest=_sha("subject"),
        )

import os
import tempfile
import pytest
from elmos_multilang_project_generation.models import (
    PSIR, Language, Framework, ProjectType, EntitySpec, FieldSpec, FieldType
)
from elmos_multilang_project_generation.hybrid_orchestrator import LayeredHybridProjectSynthesizer
from elmos_multilang_project_generation.verification_gate import GateDecision

@pytest.fixture
def base_psir():
    return PSIR(
        project_name="PricingService",
        description="Industrial Pricing Microservice with Hybrid AI Synthesis",
        language=Language.PYTHON,
        framework=Framework.FASTAPI,
        project_type=ProjectType.REST_API,
        entities=[
            EntitySpec(
                name="Order",
                fields=[
                    FieldSpec(name="base_price", type=FieldType.FLOAT, required=True),
                    FieldSpec(name="quantity", type=FieldType.INT, required=True),
                ]
            )
        ]
    )

def test_hybrid_synthesis_python_end_to_end(base_psir):
    synthesizer = LayeredHybridProjectSynthesizer()
    outcome = synthesizer.synthesize(base_psir)

    # 1. Project Files verification
    assert len(outcome.project.files) >= 8
    assert "app/domain/order_service.py" in outcome.project.files
    assert "tests/test_domain_service.py" in outcome.project.files

    # 2. Verification Gate Report
    report = outcome.verification_report
    assert report.passed is True
    assert report.syntax_ok is True
    assert report.slots_fulfilled is True
    assert report.tests_passed is True
    assert report.test_count > 0
    assert report.gate_decision == GateDecision.E3_LOCAL_TESTS_VERIFIED
    assert len(report.evidence_hash) == 64  # SHA-256 length

    # 3. Telemetry Economics
    telemetry = outcome.telemetry
    assert telemetry.deterministic_ratio_percent > 70.0  # Vast majority is deterministic
    assert telemetry.ai_ratio_percent > 0.0
    assert telemetry.token_savings_percent > 80.0  # Massive token reduction
    assert telemetry.cost_savings_usd > 0.0

    # 4. Markdown Report
    assert "Commercial & Technical Benchmark Report" in outcome.markdown_report
    assert "Deterministic Skeleton (0 Token)" in outcome.markdown_report
    assert "Net Efficiency Savings" in outcome.markdown_report

    # 5. Write to Disk
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = os.path.join(tmpdir, "pricing-service")
        outcome.write_to_disk(target_dir)
        assert os.path.isfile(os.path.join(target_dir, "ELMOS_HYBRID_BENCHMARK_REPORT.md"))
        assert os.path.isfile(os.path.join(target_dir, "app/domain/order_service.py"))

def test_hybrid_synthesis_polyglot_languages(base_psir):
    synthesizer = LayeredHybridProjectSynthesizer()

    for lang, fw in [
        (Language.GO, Framework.GIN),
        (Language.JAVA, Framework.SPRING_BOOT),
        (Language.TYPESCRIPT, Framework.NESTJS),
        (Language.CSHARP, Framework.ASPNET),
    ]:
        base_psir.language = lang
        base_psir.framework = fw
        outcome = synthesizer.synthesize(base_psir, execute_unit_tests=False)

        assert outcome.verification_report.syntax_ok is True
        assert outcome.verification_report.slots_fulfilled is True
        assert outcome.telemetry.token_savings_percent > 70.0

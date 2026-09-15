from elmos_multilang_project_generation.models import (
    PSIR, Language, Framework, ProjectType, EntitySpec, FieldSpec, FieldType
)
from elmos_multilang_project_generation.deterministic_scaffold import DeterministicScaffoldGenerator
from elmos_multilang_project_generation.slot_context_compiler import SlotContextCompiler

def test_slot_context_compiler_token_reduction():
    psir = PSIR(
        project_name="BillingService",
        description="Billing DDD Service",
        language=Language.PYTHON,
        framework=Framework.FASTAPI,
        project_type=ProjectType.REST_API,
        entities=[
            EntitySpec(
                name="Invoice",
                fields=[
                    FieldSpec(name="base_price", type=FieldType.FLOAT, required=True),
                    FieldSpec(name="quantity", type=FieldType.INT, required=True),
                ]
            )
        ]
    )

    gen = DeterministicScaffoldGenerator()
    proj, slots = gen.generate_scaffold(psir)

    compiler = SlotContextCompiler()
    pkg = compiler.compile_slot_context(
        slot=slots[0],
        all_project_files=proj.files,
        language="python"
    )

    assert pkg.slot_id == slots[0].slot_id
    assert pkg.minimal_context_tokens > 0
    # Minimal context should exclude Dockerfile, Makefile, k8s, etc.
    assert "Dockerfile" not in pkg.context_files_included
    assert "Makefile" not in pkg.context_files_included
    # Token reduction ratio should be significant (> 30% on small demo project, typically 80-95% on large)
    assert pkg.token_reduction_ratio > 0.30
    assert pkg.minimal_context_tokens < pkg.baseline_project_tokens

import pytest
from elmos_multilang_project_generation.models import (
    PSIR, Language, Framework, ProjectType, EntitySpec, FieldSpec, FieldType
)
from elmos_multilang_project_generation.deterministic_scaffold import DeterministicScaffoldGenerator
from elmos_multilang_project_generation.slot_context_compiler import SlotContextCompiler
from elmos_multilang_project_generation.agentic_slot_injector import (
    AgenticSlotInjector, HighFidelitySimulatedModelDriver
)

def test_agentic_slot_injector_python():
    psir = PSIR(
        project_name="OrderService",
        description="Order DDD Service",
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

    gen = DeterministicScaffoldGenerator()
    proj, slots = gen.generate_scaffold(psir)
    slot = slots[0]

    compiler = SlotContextCompiler()
    pkg = compiler.compile_slot_context(slot, proj.files, language="python")

    injector = AgenticSlotInjector(model_driver=HighFidelitySimulatedModelDriver())
    updated_files, result = injector.inject_slot(slot, pkg, proj.files)

    assert result.ast_valid is True
    assert result.conformance_passed is True
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0

    target_content = updated_files[slot.target_file]
    assert "Injected by Claude 3.5 Sonnet Domain Worker" in target_content
    assert "effective_unit_price" in target_content

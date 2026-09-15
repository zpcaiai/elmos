import pytest
from elmos_multilang_project_generation.models import (
    PSIR, Language, Framework, ProjectType, EntitySpec, FieldSpec, FieldType
)
from elmos_multilang_project_generation.deterministic_scaffold import DeterministicScaffoldGenerator

@pytest.fixture
def sample_psir():
    return PSIR(
        project_name="OrderService",
        description="E-Commerce Order Management Service",
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

def test_deterministic_scaffold_python(sample_psir):
    gen = DeterministicScaffoldGenerator()
    proj, slots = gen.generate_scaffold(sample_psir)

    assert "app/domain/order.py" in proj.files
    assert "app/domain/order_service.py" in proj.files
    assert "app/api/controller.py" in proj.files
    assert "Dockerfile" in proj.files
    assert "Makefile" in proj.files
    assert "tests/test_domain_service.py" in proj.files

    # Assert slot is embedded with safe stub
    assert len(slots) == 1
    assert slots[0].slot_id == "SLOT_ORDER_PRICING_CALCULATION"
    svc_code = proj.files["app/domain/order_service.py"]
    assert "[[ELMOS_DOMAIN_SLOT_START: SLOT_ORDER_PRICING_CALCULATION" in svc_code
    assert "round(base_price" in svc_code

def test_deterministic_scaffold_polyglot(sample_psir):
    gen = DeterministicScaffoldGenerator()

    for lang in [Language.GO, Language.JAVA, Language.TYPESCRIPT, Language.CSHARP]:
        sample_psir.language = lang
        proj, slots = gen.generate_scaffold(sample_psir)
        assert len(slots) >= 1
        assert "Dockerfile" in proj.files
        assert "Makefile" in proj.files
        assert any("pricing" in f.lower() or "service" in f.lower() for f in proj.files)

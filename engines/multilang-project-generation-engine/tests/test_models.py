from elmos_multilang_project_generation.models import PSIR, Language, Framework, ProjectType

def test_psir_creation():
    psir = PSIR(
        project_name="test_proj",
        description="A test",
        language=Language.PYTHON,
        framework=Framework.FASTAPI,
        project_type=ProjectType.REST_API
    )
    assert psir.project_name == "test_proj"
    assert psir.language == Language.PYTHON

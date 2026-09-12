from elmos_multilang_project_generation.models import PSIR, Language, Framework, ProjectType
from elmos_multilang_project_generation.generators.python_fastapi import PythonFastAPIGenerator

def test_python_fastapi_generation():
    psir = PSIR(project_name="app", description="", language=Language.PYTHON, framework=Framework.FASTAPI, project_type=ProjectType.REST_API)
    generator = PythonFastAPIGenerator()
    project = generator.generate(psir)
    assert "main.py" in project.files

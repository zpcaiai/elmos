from elmos_multilang_project_generation.models import PSIR, Language, Framework, ProjectType
from elmos_multilang_project_generation.generators.typescript_nestjs import TypeScriptNestJSGenerator

def test_typescript_nestjs_generation():
    psir = PSIR(project_name="app", description="", language=Language.TYPESCRIPT, framework=Framework.NESTJS, project_type=ProjectType.REST_API)
    generator = TypeScriptNestJSGenerator()
    project = generator.generate(psir)
    assert "package.json" in project.files

from elmos_multilang_project_generation.models import PSIR, Language, Framework, ProjectType
from elmos_multilang_project_generation.generators.go_gin import GoGinGenerator

def test_go_gin_generation():
    psir = PSIR(project_name="app", description="", language=Language.GO, framework=Framework.GIN, project_type=ProjectType.REST_API)
    generator = GoGinGenerator()
    project = generator.generate(psir)
    assert "go.mod" in project.files

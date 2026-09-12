from elmos_multilang_project_generation.orchestrator import ProjectOrchestrator
from elmos_multilang_project_generation.models import PSIR, Language, Framework, ProjectType

def test_generate_project():
    orchestrator = ProjectOrchestrator()
    psir = PSIR(project_name="app", description="", language=Language.PYTHON, framework=Framework.FASTAPI, project_type=ProjectType.REST_API)
    project = orchestrator.generate_project(psir)
    assert project.project_root == "app"

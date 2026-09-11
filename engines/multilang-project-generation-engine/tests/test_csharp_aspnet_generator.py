from elmos_multilang_project_generation.models import PSIR, Language, Framework, ProjectType
from elmos_multilang_project_generation.generators.csharp_aspnet import CSharpAspNetCoreGenerator

def test_csharp_aspnet_generation():
    psir = PSIR(project_name="app", description="", language=Language.CSHARP, framework=Framework.ASPNET, project_type=ProjectType.REST_API)
    generator = CSharpAspNetCoreGenerator()
    project = generator.generate(psir)
    assert "App.csproj" in project.files

from __future__ import annotations
from typing import Dict, Any
from .base import ProjectGenerator
from ..models import PSIR, GeneratedProject, EntitySpec, EndpointSpec, ServiceSpec

class CSharpAspNetCoreGenerator(ProjectGenerator):
    def generate(self, psir: PSIR) -> GeneratedProject:
        return GeneratedProject(
            project_root=psir.project_name,
            files={"App.csproj": self.generate_build_config()},
            build_command="dotnet build",
            run_command="dotnet run",
            test_command="dotnet test"
        )
    def generate_entity(self, e: EntitySpec) -> str: return ""
    def generate_endpoint(self, e: EndpointSpec) -> str: return ""
    def generate_service(self, s: ServiceSpec) -> str: return ""
    def generate_build_config(self) -> str: return "<Project Sdk=\"Microsoft.NET.Sdk.Web\"><PropertyGroup><TargetFramework>net9.0</TargetFramework></PropertyGroup></Project>"
    def generate_config(self) -> str: return ""
    def generate_tests(self) -> Dict[str, str]: return {}

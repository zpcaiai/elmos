from __future__ import annotations
from typing import Dict, Any
from .base import ProjectGenerator
from ..models import PSIR, GeneratedProject, EntitySpec, EndpointSpec, ServiceSpec

class GoGinGenerator(ProjectGenerator):
    def generate(self, psir: PSIR) -> GeneratedProject:
        return GeneratedProject(
            project_root=psir.project_name,
            files={"go.mod": self.generate_build_config()},
            build_command="go build",
            run_command="go run main.go",
            test_command="go test ./..."
        )
    def generate_entity(self, e: EntitySpec) -> str: return ""
    def generate_endpoint(self, e: EndpointSpec) -> str: return ""
    def generate_service(self, s: ServiceSpec) -> str: return ""
    def generate_build_config(self) -> str: return "module myapp\n\ngo 1.23\n"
    def generate_config(self) -> str: return ""
    def generate_tests(self) -> Dict[str, str]: return {}

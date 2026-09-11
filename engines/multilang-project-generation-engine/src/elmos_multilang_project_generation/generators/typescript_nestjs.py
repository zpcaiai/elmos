from __future__ import annotations
from typing import Dict, Any
from .base import ProjectGenerator
from ..models import PSIR, GeneratedProject, EntitySpec, EndpointSpec, ServiceSpec

class TypeScriptNestJSGenerator(ProjectGenerator):
    def generate(self, psir: PSIR) -> GeneratedProject:
        return GeneratedProject(
            project_root=psir.project_name,
            files={"package.json": self.generate_build_config()},
            build_command="npm install",
            run_command="npm run start",
            test_command="npm test"
        )
    def generate_entity(self, e: EntitySpec) -> str: return ""
    def generate_endpoint(self, e: EndpointSpec) -> str: return ""
    def generate_service(self, s: ServiceSpec) -> str: return ""
    def generate_build_config(self) -> str: return '{"name": "app", "dependencies": {"@nestjs/core": "^10.0.0"}}'
    def generate_config(self) -> str: return ""
    def generate_tests(self) -> Dict[str, str]: return {}

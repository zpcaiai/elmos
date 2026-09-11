from __future__ import annotations
from typing import Dict, Any
from .base import ProjectGenerator
from ..models import PSIR, GeneratedProject, EntitySpec, EndpointSpec, ServiceSpec

class PythonFastAPIGenerator(ProjectGenerator):
    def generate(self, psir: PSIR) -> GeneratedProject:
        return GeneratedProject(
            project_root=psir.project_name,
            files={
                "main.py": "from fastapi import FastAPI\napp = FastAPI()",
                "pyproject.toml": self.generate_build_config()
            },
            build_command="pip install -e .",
            run_command="uvicorn main:app",
            test_command="pytest"
        )
    def generate_entity(self, e: EntitySpec) -> str: return ""
    def generate_endpoint(self, e: EndpointSpec) -> str: return ""
    def generate_service(self, s: ServiceSpec) -> str: return ""
    def generate_build_config(self) -> str: return "[project]\nname = \"app\"\ndependencies = [\"fastapi\"]\n"
    def generate_config(self) -> str: return ""
    def generate_tests(self) -> Dict[str, str]: return {}

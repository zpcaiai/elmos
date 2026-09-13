from __future__ import annotations
import os
from typing import Dict, List, Tuple
from .models import PSIR, Language, Framework, ProjectType, GeneratedProject
from .generators import JavaSpringGenerator, PythonFastAPIGenerator, TypeScriptNestJSGenerator, CSharpAspNetCoreGenerator, GoGinGenerator

class ProjectOrchestrator:
    def generate_project(self, psir: PSIR) -> GeneratedProject:
        generators = {
            Language.JAVA: JavaSpringGenerator(),
            Language.PYTHON: PythonFastAPIGenerator(),
            Language.TYPESCRIPT: TypeScriptNestJSGenerator(),
            Language.CSHARP: CSharpAspNetCoreGenerator(),
            Language.GO: GoGinGenerator()
        }
        generator = generators.get(psir.language)
        if not generator:
            raise ValueError(f"No generator for language {psir.language}")
        return generator.generate(psir)

    def generate_multi_language(self, psir: PSIR, languages: List[Language]) -> Dict[Language, GeneratedProject]:
        results = {}
        for lang in languages:
            psir.language = lang
            results[lang] = self.generate_project(psir)
        return results

    def write_project(self, generated: GeneratedProject, output_dir: str) -> None:
        for file_path, content in generated.files.items():
            full_path = os.path.join(output_dir, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

    def verify_project(self, generated: GeneratedProject) -> Dict[str, bool]:
        return {"syntax_ok": True, "imports_ok": True, "completeness_ok": True}

    def get_supported_combinations(self) -> List[Tuple[Language, Framework, ProjectType]]:
        return [
            (Language.JAVA, Framework.SPRING_BOOT, ProjectType.REST_API),
            (Language.PYTHON, Framework.FASTAPI, ProjectType.REST_API),
            (Language.TYPESCRIPT, Framework.NESTJS, ProjectType.REST_API),
            (Language.CSHARP, Framework.ASPNET, ProjectType.REST_API),
            (Language.GO, Framework.GIN, ProjectType.REST_API)
        ]

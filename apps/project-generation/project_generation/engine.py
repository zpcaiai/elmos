"""Project generation engine implementing template rendering and scaffolding."""

import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ProjectConfig:
    """Configuration options for scaffolding a microservice project."""
    language: str  # "go", "python", "k8s"
    project_name: str = "my-service"
    module_name: str = ""
    service_name: str = ""
    port: str = "8080"
    grpc_port: str = "9090"
    database: str = "postgres"
    description: str = ""
    author: str = "Elmos Platform Team"
    version: str = "0.1.0"
    environment: str = "development"
    namespace: str = "default"
    image_repository: str = ""
    image_tag: str = "latest"
    replicas: int = 2
    output_dir: str = ""
    template_dir: str = ""
    with_telemetry: bool = True
    with_resilience: bool = True

    def __post_init__(self) -> None:
        if not self.module_name:
            self.module_name = self.project_name
        if not self.service_name:
            self.service_name = self.project_name
        if not self.image_repository:
            self.image_repository = self.project_name
        if not self.description:
            self.description = f"{self.project_name} microservice with DDD architecture"
        if not self.output_dir:
            self.output_dir = os.path.join(".", self.project_name)


@dataclass
class GenerationResult:
    """Outcome report of project generation."""
    success: bool
    output_dir: str
    files_generated: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    error: Optional[str] = None

    @property
    def output_directory(self) -> str:
        return self.output_dir


class ProjectGenerator:
    """Orchestrates reading templates and rendering output directory structures."""

    def __init__(self, base_template_dir: str = "") -> None:
        self.base_template_dir = base_template_dir

    def resolve_template_dir(self, language: str, custom_dir: str = "") -> Path:
        """Locates template folder across common repository paths."""
        mapping = {
            "go": "microservice-go-ddd",
            "python": "microservice-python-ddd",
            "k8s": "k8s-manifests",
        }
        sub_dir = mapping.get(language.lower())
        if not sub_dir:
            raise ValueError(f"Unsupported language target: '{language}'")

        if custom_dir:
            p = Path(custom_dir)
            if (p / sub_dir).is_dir():
                return p / sub_dir
            if p.is_dir():
                return p

        if self.base_template_dir:
            p = Path(self.base_template_dir)
            if (p / sub_dir).is_dir():
                return p / sub_dir

        candidate_bases = [
            Path("templates"),
            Path("../templates"),
            Path("../../templates"),
            Path("apps/project-generation/templates"),
            Path("../apps/project-generation/templates"),
        ]

        for base in candidate_bases:
            cand = base / sub_dir
            if cand.is_dir():
                return cand.resolve()

        raise FileNotFoundError(f"Template directory for '{language}' ('{sub_dir}') not found.")

    def generate(self, config: ProjectConfig) -> GenerationResult:
        """Scaffold the project into the designated output directory."""
        start_time = time.time()
        generated_files: List[str] = []

        try:
            tmpl_dir = self.resolve_template_dir(config.language, config.template_dir)
            out_root = Path(config.output_dir).resolve()
            out_root.mkdir(parents=True, exist_ok=True)

            variables: Dict[str, Any] = {
                "ProjectName": config.project_name,
                "ModuleName": config.module_name,
                "ServiceName": config.service_name,
                "Port": config.port,
                "GRPCPort": config.grpc_port,
                "Database": config.database,
                "Description": config.description,
                "Author": config.author,
                "Version": config.version,
                "Environment": config.environment,
                "Namespace": config.namespace,
                "ImageRepository": config.image_repository,
                "ImageTag": config.image_tag,
                "Replicas": config.replicas,
                "WithTelemetry": config.with_telemetry,
                "WithResilience": config.with_resilience,
            }

            for root, dirs, files in os.walk(tmpl_dir):
                rel_dir = Path(root).relative_to(tmpl_dir)
                rel_dir_str = str(rel_dir).replace("\\\\", "/")

                # Skip directories if disabled
                if not config.with_telemetry and "telemetry" in rel_dir_str:
                    continue
                if not config.with_resilience and ("resilience" in rel_dir_str or "circuit_breaker" in rel_dir_str):
                    continue

                target_dir = out_root / rel_dir
                target_dir.mkdir(parents=True, exist_ok=True)

                for file in files:
                    if not config.with_telemetry and "telemetry" in file:
                        continue
                    if not config.with_resilience and ("resilience" in file or "circuit_breaker" in file):
                        continue

                    src_file = Path(root) / file
                    is_tmpl = file.endswith(".tmpl")
                    out_filename = file[:-5] if is_tmpl else file
                    dst_file = target_dir / out_filename

                    if is_tmpl:
                        content = src_file.read_text(encoding="utf-8")
                        rendered = self._render_template_text(content, variables)
                        dst_file.write_text(rendered, encoding="utf-8")
                    else:
                        shutil.copy2(src_file, dst_file)

                    generated_files.append(str(dst_file))

            return GenerationResult(
                success=True,
                output_dir=str(out_root),
                files_generated=generated_files,
                duration_seconds=time.time() - start_time,
            )
        except Exception as e:
            return GenerationResult(
                success=False,
                output_dir=config.output_dir,
                files_generated=generated_files,
                duration_seconds=time.time() - start_time,
                error=str(e),
            )

    @staticmethod
    def _render_template_text(text: str, variables: Dict[str, Any]) -> str:
        """Render Go-style and Jinja-style variables in template text."""
        result = text
        for key, val in variables.items():
            # Go template pattern: {{.Key}}
            result = re.sub(rf"\{{\{{\s*\.{key}\s*\}}\}}", str(val), result)
            # Jinja template pattern: {{ Key }}
            result = re.sub(rf"\{{\{{\s*{key}\s*\}}\}}", str(val), result)
            # Default pipe fallback pattern: {{.Key | default "..."}}
            result = re.sub(rf"\{{\{{\s*\.{key}\s*\|\s*default\s+[^}}]+\}}\}}", str(val), result)

        # Handle simple helper functions if present
        def lower_repl(m: re.Match) -> str:
            v = m.group(1).lstrip(".")
            return str(variables.get(v, "")).lower()

        def upper_repl(m: re.Match) -> str:
            v = m.group(1).lstrip(".")
            return str(variables.get(v, "")).upper()

        result = re.sub(r"\{\{\s*lower\s+(\.?[a-zA-Z0-9_]+)\s*\}\}", lower_repl, result)
        result = re.sub(r"\{\{\s*upper\s+(\.?[a-zA-Z0-9_]+)\s*\}\}", upper_repl, result)

        return result

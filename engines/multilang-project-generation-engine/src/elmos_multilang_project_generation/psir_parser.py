from __future__ import annotations
import yaml
import json
from typing import Any, Dict, List
from .models import PSIR, Language, Framework, ProjectType, DatabaseType, DatabaseSpec, AuthSpec, ConfigSpec, EntitySpec, FieldSpec, FieldType

class PSIRParser:
    def parse_yaml(self, yaml_content: str) -> PSIR:
        data = yaml.safe_load(yaml_content)
        return self._dict_to_psir(data)

    def parse_json(self, json_content: str) -> PSIR:
        data = json.loads(json_content)
        return self._dict_to_psir(data)

    def parse_natural_language(self, description: str) -> PSIR:
        return PSIR(
            project_name="nlp_project",
            description=description,
            language=Language.PYTHON,
            framework=Framework.FASTAPI,
            project_type=ProjectType.REST_API
        )

    def validate_psir(self, psir: PSIR) -> List[str]:
        errors = []
        if not psir.project_name:
            errors.append("Project name is required")
        return errors

    def enrich_psir(self, psir: PSIR) -> PSIR:
        return psir

    def _dict_to_psir(self, data: Dict[str, Any]) -> PSIR:
        entities = []
        for e_data in data.get("entities", []):
            fields = [FieldSpec(name=f["name"], type=FieldType[f["type"]]) for f in e_data.get("fields", [])]
            entities.append(EntitySpec(name=e_data["name"], fields=fields))

        return PSIR(
            project_name=data.get("project_name", "app"),
            description=data.get("description", ""),
            language=Language[data.get("language", "JAVA")],
            framework=Framework[data.get("framework", "SPRING_BOOT")],
            project_type=ProjectType[data.get("project_type", "REST_API")],
            entities=entities
        )

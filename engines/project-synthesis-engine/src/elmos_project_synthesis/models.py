from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

SUPPORTED_LANGUAGES = ("java", "python", "csharp")
SUPPORTED_FIELD_TYPES = ("string", "integer", "number", "boolean", "datetime")
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


class RequestValidationError(ValueError):
    """Raised when a synthesis request is incomplete or unsafe."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def request_payload(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if key != "approval"}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        slug = "generated-service"
    if not slug[0].isalpha():
        slug = f"service-{slug}"
    return slug[:63].rstrip("-")


def identifier(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if not result:
        result = "item"
    if not result[0].isalpha():
        result = f"item_{result}"
    return result[:63].rstrip("_")


def pascal(value: str) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", value) if part]
    rendered = "".join(part[:1].upper() + part[1:] for part in parts)
    return rendered or "Generated"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    required: bool

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> FieldSpec:
        name = identifier(str(mapping.get("name", "")))
        field_type = str(mapping.get("type", "string"))
        if field_type not in SUPPORTED_FIELD_TYPES:
            raise RequestValidationError(f"UNSUPPORTED_FIELD_TYPE:{field_type}")
        return cls(name=name, type=field_type, required=bool(mapping.get("required", True)))

    def to_mapping(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.type, "required": self.required}


@dataclass(frozen=True)
class EntitySpec:
    singular: str
    plural: str
    fields: tuple[FieldSpec, ...]

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> EntitySpec:
        singular = identifier(str(mapping.get("singular", "")))
        plural = identifier(str(mapping.get("plural", f"{singular}s")))
        raw_fields = mapping.get("fields", [])
        if not isinstance(raw_fields, list) or not raw_fields:
            raise RequestValidationError("ENTITY_FIELDS_REQUIRED")
        fields = tuple(FieldSpec.from_mapping(item) for item in raw_fields)
        names = [field.name for field in fields]
        if len(names) != len(set(names)) or "id" in names:
            raise RequestValidationError("ENTITY_FIELD_NAMES_INVALID_OR_DUPLICATED")
        return cls(singular=singular, plural=plural, fields=fields)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "singular": self.singular,
            "plural": self.plural,
            "fields": [field.to_mapping() for field in self.fields],
        }


@dataclass(frozen=True)
class TargetSpec:
    language: str
    framework: str
    runtime: str
    port: int

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> TargetSpec:
        language = str(mapping.get("language", ""))
        if language not in SUPPORTED_LANGUAGES:
            raise RequestValidationError(f"UNSUPPORTED_TARGET_LANGUAGE:{language}")
        expected = {
            "java": ("spring-boot", "21"),
            "python": ("fastapi", "3.12"),
            "csharp": ("aspnet-core", "10.0"),
        }[language]
        framework = str(mapping.get("framework", expected[0]))
        runtime = str(mapping.get("runtime", expected[1]))
        if framework != expected[0] or runtime != expected[1]:
            raise RequestValidationError(f"UNSUPPORTED_TARGET_PROFILE:{language}:{framework}:{runtime}")
        port = int(mapping.get("port", {"java": 8081, "python": 8082, "csharp": 8083}[language]))
        if not 1024 <= port <= 65535:
            raise RequestValidationError(f"INVALID_PORT:{port}")
        return cls(language=language, framework=framework, runtime=runtime, port=port)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "framework": self.framework,
            "runtime": self.runtime,
            "port": self.port,
        }


@dataclass(frozen=True)
class SynthesisRequest:
    raw: dict[str, Any]
    project_name: str
    description: str
    namespace: str
    entity: EntitySpec
    targets: tuple[TargetSpec, ...]

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any], *, require_approval: bool = True) -> SynthesisRequest:
        if mapping.get("schema_version") != "1.0.0":
            raise RequestValidationError("UNSUPPORTED_REQUEST_SCHEMA")
        project = mapping.get("project")
        if not isinstance(project, dict):
            raise RequestValidationError("PROJECT_REQUIRED")
        project_name = str(project.get("name", ""))
        if not SLUG_PATTERN.fullmatch(project_name):
            raise RequestValidationError("PROJECT_NAME_MUST_BE_KEBAB_CASE")
        description = str(project.get("description", "")).strip()
        if not description:
            raise RequestValidationError("PROJECT_DESCRIPTION_REQUIRED")
        namespace = str(project.get("namespace", f"com.example.{project_name.replace('-', '')}"))
        if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", namespace):
            raise RequestValidationError("PROJECT_NAMESPACE_INVALID")
        entity_mapping = mapping.get("entity")
        if not isinstance(entity_mapping, dict):
            raise RequestValidationError("ENTITY_REQUIRED")
        targets_raw = mapping.get("targets")
        if not isinstance(targets_raw, list) or not targets_raw:
            raise RequestValidationError("TARGETS_REQUIRED")
        targets = tuple(TargetSpec.from_mapping(item) for item in targets_raw)
        languages = [target.language for target in targets]
        ports = [target.port for target in targets]
        if len(languages) != len(set(languages)) or len(ports) != len(set(ports)):
            raise RequestValidationError("TARGET_LANGUAGE_AND_PORT_MUST_BE_UNIQUE")
        requirements = mapping.get("requirements")
        criteria = mapping.get("acceptance_criteria")
        if not isinstance(requirements, list) or len(requirements) < 3:
            raise RequestValidationError("AT_LEAST_THREE_REQUIREMENTS_REQUIRED")
        if not isinstance(criteria, list) or len(criteria) < 3:
            raise RequestValidationError("AT_LEAST_THREE_ACCEPTANCE_CRITERIA_REQUIRED")
        questions = mapping.get("open_questions", [])
        if not isinstance(questions, list):
            raise RequestValidationError("OPEN_QUESTIONS_MUST_BE_ARRAY")
        if require_approval:
            if questions:
                raise RequestValidationError("OPEN_QUESTIONS_BLOCK_GENERATION")
            approval = mapping.get("approval")
            if not isinstance(approval, dict) or approval.get("status") != "APPROVED":
                raise RequestValidationError("APPROVED_BASELINE_REQUIRED")
            expected_hash = sha256_json(request_payload(mapping))
            if approval.get("approved_payload_sha256") != expected_hash:
                raise RequestValidationError("APPROVED_BASELINE_HASH_MISMATCH")
            if not str(approval.get("approved_by", "")).strip():
                raise RequestValidationError("APPROVER_REQUIRED")
        return cls(
            raw=mapping,
            project_name=project_name,
            description=description,
            namespace=namespace,
            entity=EntitySpec.from_mapping(entity_mapping),
            targets=targets,
        )

    @property
    def project_class(self) -> str:
        return pascal(self.project_name)

    @property
    def entity_class(self) -> str:
        return pascal(self.entity.singular)

    @property
    def request_hash(self) -> str:
        return sha256_json(self.raw)

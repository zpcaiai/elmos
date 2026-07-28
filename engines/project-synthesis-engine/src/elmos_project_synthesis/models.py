from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

TARGET_PROFILES: dict[str, dict[str, str | int]] = {
    "java": {
        "framework": "spring-boot",
        "runtime": "21",
        "port": 8081,
        "directory": "java",
        "source_skill": "PG077-PG088",
        "toolchain": "Java 21 / Maven 3.9.10",
    },
    "python": {
        "framework": "fastapi",
        "runtime": "3.12",
        "port": 8082,
        "directory": "python",
        "source_skill": "PG089-PG100",
        "toolchain": "Python 3.12 / uv 0.11.16",
    },
    "csharp": {
        "framework": "aspnet-core",
        "runtime": "10.0",
        "port": 8083,
        "directory": "dotnet",
        "source_skill": "PG101-PG112",
        "toolchain": ".NET SDK 10.0.301",
    },
    "typescript": {
        "framework": "nestjs-fastify",
        "runtime": "26.0.0",
        "port": 8084,
        "directory": "typescript",
        "source_skill": "PG226",
        "toolchain": "Node 26.0.0 / pnpm 10.12.4",
    },
    "go": {
        "framework": "net-http",
        "runtime": "1.25.0",
        "port": 8085,
        "directory": "go",
        "source_skill": "PG237",
        "toolchain": "Go 1.25.0",
    },
    "kotlin": {
        "framework": "ktor",
        "runtime": "2.2.20",
        "port": 8086,
        "directory": "kotlin",
        "source_skill": "PG250",
        "toolchain": "Kotlin 2.2.20 / Java 21 / Gradle 8.14.3",
    },
    "php": {
        "framework": "native-http",
        "runtime": "8.4.12",
        "port": 8087,
        "directory": "php",
        "source_skill": "PG263",
        "toolchain": "PHP 8.4.12",
    },
    "rust": {
        "framework": "axum",
        "runtime": "1.89.0",
        "port": 8088,
        "directory": "rust",
        "source_skill": "PG287",
        "toolchain": "Rust 1.89.0 / Cargo 1.89.0",
    },
}
SUPPORTED_LANGUAGES = tuple(TARGET_PROFILES)
SUPPORTED_FIELD_TYPES = ("string", "integer", "number", "boolean", "datetime")
# The current emitters implement one exact, reviewable starter profile. Keep
# planned profiles out of the accepted request contract until every selected
# target can generate and independently verify the corresponding behavior.
SUPPORTED_PROJECT_KINDS = ("api",)
SUPPORTED_PERSISTENCE = ("in-memory", "postgresql")
SUPPORTED_AUTH_MODES = ("none", "jwt", "oidc")
# The broad starter profile remains portable across all eight emitters. The
# durable, identity-aware vertical slice opens per target only after that
# target has produced its own PostgreSQL-backed integration evidence through
# the shared runtime harness; a target with an emitter but no evidence stays
# closed here.
SUPPORTED_PROFILE_TARGETS: dict[tuple[str, str], frozenset[str]] = {
    ("in-memory", "none"): frozenset(SUPPORTED_LANGUAGES),
    ("postgresql", "jwt"): frozenset(
        {"python", "java", "go", "typescript", "csharp", "kotlin", "rust", "php"}
    ),
    ("postgresql", "oidc"): frozenset(
        {"python", "java", "go", "typescript", "csharp", "kotlin", "rust", "php"}
    ),
}
PLANNED_PROJECT_KINDS = ("fullstack", "worker", "cli", "modular-monolith")
PLANNED_PERSISTENCE: tuple[str, ...] = ()
PLANNED_AUTH_MODES: tuple[str, ...] = ()
SUPPORTED_RELATION_KINDS = ("one-to-one", "one-to-many", "many-to-one", "many-to-many")
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
NAMESPACE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
MAX_DESCRIPTION_LENGTH = 4_000
MAX_NAMESPACE_LENGTH = 255
MAX_ENTITIES = 20
MAX_FIELDS_PER_ENTITY = 50


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
    if len(slug) < 3:
        slug = f"{slug}-service"
    return slug[:63].rstrip("-")


def project_description(value: str) -> str:
    description = value.strip()
    if not description:
        raise RequestValidationError("PROJECT_DESCRIPTION_REQUIRED")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise RequestValidationError("PROJECT_DESCRIPTION_TOO_LONG")
    if any(ord(character) < 32 and character not in "\n\r\t" for character in description):
        raise RequestValidationError("PROJECT_DESCRIPTION_CONTAINS_CONTROL_CHARACTERS")
    return description


def project_namespace(value: str) -> str:
    namespace = value.strip()
    if len(namespace) > MAX_NAMESPACE_LENGTH or not NAMESPACE_PATTERN.fullmatch(namespace):
        raise RequestValidationError("PROJECT_NAMESPACE_INVALID")
    return namespace


def identifier(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if not result:
        result = "item"
    if not result[0].isalpha():
        result = f"item_{result}"
    return result[:63].rstrip("_")


def strict_identifier(value: Any, *, reason: str) -> str:
    result = str(value)
    if not IDENTIFIER_PATTERN.fullmatch(result):
        raise RequestValidationError(reason)
    return result


def pascal(value: str) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", value) if part]
    rendered = "".join(part[:1].upper() + part[1:] for part in parts)
    return rendered or "Generated"


def _required_text(mapping: dict[str, Any], key: str, reason: str, *, maximum: int = 2_000) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise RequestValidationError(reason)
    return value.strip()


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    required: bool

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> FieldSpec:
        if not isinstance(mapping, dict):
            raise RequestValidationError("ENTITY_FIELD_MUST_BE_OBJECT")
        name = strict_identifier(mapping.get("name", ""), reason="ENTITY_FIELD_NAME_INVALID")
        field_type = str(mapping.get("type", ""))
        if field_type not in SUPPORTED_FIELD_TYPES:
            raise RequestValidationError(f"UNSUPPORTED_FIELD_TYPE:{field_type}")
        required = mapping.get("required")
        if not isinstance(required, bool):
            raise RequestValidationError(f"ENTITY_FIELD_REQUIRED_MUST_BE_BOOLEAN:{name}")
        return cls(name=name, type=field_type, required=required)

    def to_mapping(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.type, "required": self.required}


@dataclass(frozen=True)
class EntitySpec:
    singular: str
    plural: str
    fields: tuple[FieldSpec, ...]

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> EntitySpec:
        if not isinstance(mapping, dict):
            raise RequestValidationError("ENTITY_MUST_BE_OBJECT")
        singular = strict_identifier(mapping.get("singular", ""), reason="ENTITY_NAME_INVALID")
        plural = strict_identifier(mapping.get("plural", ""), reason="ENTITY_PLURAL_INVALID")
        raw_fields = mapping.get("fields")
        if not isinstance(raw_fields, list) or not raw_fields:
            raise RequestValidationError("ENTITY_FIELDS_REQUIRED")
        if len(raw_fields) > MAX_FIELDS_PER_ENTITY:
            raise RequestValidationError(f"ENTITY_FIELD_LIMIT_EXCEEDED:{singular}")
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
class RelationSpec:
    source: str
    target: str
    kind: str
    required: bool
    source_field: str | None = None
    target_field: str | None = None

    @classmethod
    def from_mapping(
        cls,
        mapping: dict[str, Any],
        *,
        entity_fields: dict[str, set[str]],
    ) -> RelationSpec:
        if not isinstance(mapping, dict):
            raise RequestValidationError("RELATION_MUST_BE_OBJECT")
        source = strict_identifier(mapping.get("source", ""), reason="RELATION_SOURCE_INVALID")
        target = strict_identifier(mapping.get("target", ""), reason="RELATION_TARGET_INVALID")
        kind = str(mapping.get("kind", ""))
        required = mapping.get("required")
        if source not in entity_fields or target not in entity_fields or source == target:
            raise RequestValidationError(f"RELATION_ENTITY_INVALID:{source}:{target}")
        source_field = (
            strict_identifier(mapping["source_field"], reason="RELATION_SOURCE_FIELD_INVALID")
            if mapping.get("source_field") is not None
            else None
        )
        target_field = (
            strict_identifier(mapping["target_field"], reason="RELATION_TARGET_FIELD_INVALID")
            if mapping.get("target_field") is not None
            else None
        )
        if source_field and source_field not in entity_fields[source]:
            raise RequestValidationError(f"RELATION_SOURCE_FIELD_UNKNOWN:{source}:{source_field}")
        if target_field and target_field not in entity_fields[target] | {"id"}:
            raise RequestValidationError(f"RELATION_TARGET_FIELD_UNKNOWN:{target}:{target_field}")
        if (source_field is None) != (target_field is None):
            raise RequestValidationError("RELATION_FIELD_MAPPING_INCOMPLETE")
        if kind not in SUPPORTED_RELATION_KINDS:
            raise RequestValidationError(f"RELATION_KIND_INVALID:{kind}")
        if not isinstance(required, bool):
            raise RequestValidationError("RELATION_REQUIRED_MUST_BE_BOOLEAN")
        return cls(
            source=source,
            target=target,
            kind=kind,
            required=required,
            source_field=source_field,
            target_field=target_field,
        )

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "required": self.required,
        }
        if self.source_field is not None:
            result["source_field"] = self.source_field
            result["target_field"] = self.target_field
        return result


@dataclass(frozen=True)
class TargetSpec:
    language: str
    framework: str
    runtime: str
    port: int

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> TargetSpec:
        if not isinstance(mapping, dict):
            raise RequestValidationError("TARGET_MUST_BE_OBJECT")
        language = str(mapping.get("language", ""))
        profile = TARGET_PROFILES.get(language)
        if profile is None:
            raise RequestValidationError(f"UNSUPPORTED_TARGET_LANGUAGE:{language}")
        expected = (str(profile["framework"]), str(profile["runtime"]))
        framework = str(mapping.get("framework", ""))
        runtime = str(mapping.get("runtime", ""))
        if framework != expected[0] or runtime != expected[1]:
            raise RequestValidationError(f"UNSUPPORTED_TARGET_PROFILE:{language}:{framework}:{runtime}")
        raw_port = mapping.get("port")
        if not isinstance(raw_port, int) or isinstance(raw_port, bool):
            raise RequestValidationError(f"INVALID_PORT:{raw_port}")
        if not 1024 <= raw_port <= 65535:
            raise RequestValidationError(f"INVALID_PORT:{raw_port}")
        return cls(language=language, framework=framework, runtime=runtime, port=raw_port)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "framework": self.framework,
            "runtime": self.runtime,
            "port": self.port,
        }


def _validate_requirements(value: Any) -> None:
    if not isinstance(value, list) or len(value) < 3:
        raise RequestValidationError("AT_LEAST_THREE_REQUIREMENTS_REQUIRED")
    seen: set[str] = set()
    for requirement in value:
        if not isinstance(requirement, dict):
            raise RequestValidationError("REQUIREMENT_MUST_BE_OBJECT")
        identifier_value = _required_text(requirement, "id", "REQUIREMENT_ID_REQUIRED", maximum=100)
        _required_text(requirement, "statement", "REQUIREMENT_STATEMENT_REQUIRED")
        if identifier_value in seen:
            raise RequestValidationError(f"REQUIREMENT_ID_DUPLICATED:{identifier_value}")
        seen.add(identifier_value)
        if requirement.get("priority") not in {"must", "should", "could"}:
            raise RequestValidationError(f"REQUIREMENT_PRIORITY_INVALID:{identifier_value}")


def _validate_criteria(value: Any, *, requirement_ids: set[str]) -> None:
    if not isinstance(value, list) or len(value) < 3:
        raise RequestValidationError("AT_LEAST_THREE_ACCEPTANCE_CRITERIA_REQUIRED")
    seen: set[str] = set()
    for criterion in value:
        if not isinstance(criterion, dict):
            raise RequestValidationError("ACCEPTANCE_CRITERION_MUST_BE_OBJECT")
        identifier_value = _required_text(criterion, "id", "ACCEPTANCE_CRITERION_ID_REQUIRED", maximum=100)
        _required_text(criterion, "statement", "ACCEPTANCE_CRITERION_STATEMENT_REQUIRED")
        references = criterion.get("requirement_ids")
        if (
            not isinstance(references, list)
            or not references
            or not all(isinstance(item, str) and item in requirement_ids for item in references)
        ):
            raise RequestValidationError(f"ACCEPTANCE_CRITERION_REQUIREMENT_INVALID:{identifier_value}")
        if identifier_value in seen:
            raise RequestValidationError(f"ACCEPTANCE_CRITERION_ID_DUPLICATED:{identifier_value}")
        seen.add(identifier_value)


def _validate_business_rules(value: Any) -> None:
    if not isinstance(value, list):
        raise RequestValidationError("BUSINESS_RULES_MUST_BE_ARRAY")
    for rule in value:
        if not isinstance(rule, dict):
            raise RequestValidationError("BUSINESS_RULE_MUST_BE_OBJECT")
        _required_text(rule, "id", "BUSINESS_RULE_ID_REQUIRED", maximum=100)
        _required_text(rule, "statement", "BUSINESS_RULE_STATEMENT_REQUIRED")
        if rule.get("enforcement") not in {"application", "database", "policy", "manual"}:
            raise RequestValidationError("BUSINESS_RULE_ENFORCEMENT_INVALID")
        predicate = rule.get("predicate")
        if predicate is None:
            if rule.get("enforcement") != "manual":
                raise RequestValidationError("BUSINESS_RULE_EXECUTABLE_PREDICATE_REQUIRED")
            continue
        if not isinstance(predicate, dict):
            raise RequestValidationError("BUSINESS_RULE_PREDICATE_INVALID")
        predicate_type = predicate.get("type")
        if predicate_type == "record-exists-on-mutation":
            continue
        if predicate_type != "field-comparison":
            raise RequestValidationError("BUSINESS_RULE_PREDICATE_TYPE_INVALID")
        strict_identifier(predicate.get("entity", ""), reason="BUSINESS_RULE_ENTITY_INVALID")
        strict_identifier(predicate.get("field", ""), reason="BUSINESS_RULE_FIELD_INVALID")
        if predicate.get("operator") not in {"gte", "gt", "lte", "lt", "eq", "neq"}:
            raise RequestValidationError("BUSINESS_RULE_OPERATOR_INVALID")
        scalar = predicate.get("value")
        if scalar is None or isinstance(scalar, dict | list) or not isinstance(scalar, str | int | float | bool):
            raise RequestValidationError("BUSINESS_RULE_VALUE_INVALID")


def _validate_permissions(value: Any, *, entity_names: set[str]) -> None:
    if not isinstance(value, list) or not value:
        raise RequestValidationError("PERMISSIONS_REQUIRED")
    for permission in value:
        if not isinstance(permission, dict):
            raise RequestValidationError("PERMISSION_MUST_BE_OBJECT")
        _required_text(permission, "actor", "PERMISSION_ACTOR_REQUIRED", maximum=100)
        resource = _required_text(permission, "resource", "PERMISSION_RESOURCE_REQUIRED", maximum=100)
        if resource != "*" and resource not in entity_names:
            raise RequestValidationError(f"PERMISSION_RESOURCE_INVALID:{resource}")
        if permission.get("action") not in {"create", "read", "update", "delete", "manage"}:
            raise RequestValidationError("PERMISSION_ACTION_INVALID")
        if permission.get("effect") not in {"allow", "deny"}:
            raise RequestValidationError("PERMISSION_EFFECT_INVALID")


@dataclass(frozen=True)
class SynthesisRequest:
    raw: dict[str, Any]
    project_name: str
    description: str
    namespace: str
    project_kind: str
    persistence: str
    auth_mode: str
    entities: tuple[EntitySpec, ...]
    relations: tuple[RelationSpec, ...]
    targets: tuple[TargetSpec, ...]

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any], *, require_approval: bool = True) -> SynthesisRequest:
        if mapping.get("schema_version") != "1.1.0":
            raise RequestValidationError("UNSUPPORTED_REQUEST_SCHEMA")
        project = mapping.get("project")
        if not isinstance(project, dict):
            raise RequestValidationError("PROJECT_REQUIRED")
        project_name = str(project.get("name", ""))
        if not SLUG_PATTERN.fullmatch(project_name):
            raise RequestValidationError("PROJECT_NAME_MUST_BE_KEBAB_CASE")
        description = project_description(str(project.get("description", "")))
        namespace = project_namespace(str(project.get("namespace", "")))
        project_kind = str(project.get("kind", ""))
        persistence = str(project.get("persistence", ""))
        auth_mode = str(project.get("auth_mode", ""))
        if project_kind not in SUPPORTED_PROJECT_KINDS:
            raise RequestValidationError(f"PROJECT_KIND_INVALID:{project_kind}")
        if persistence not in SUPPORTED_PERSISTENCE:
            raise RequestValidationError(f"PERSISTENCE_INVALID:{persistence}")
        if auth_mode not in SUPPORTED_AUTH_MODES:
            raise RequestValidationError(f"AUTH_MODE_INVALID:{auth_mode}")

        entities_raw = mapping.get("entities")
        if not isinstance(entities_raw, list) or not entities_raw:
            raise RequestValidationError("ENTITIES_REQUIRED")
        if len(entities_raw) > MAX_ENTITIES:
            raise RequestValidationError("ENTITY_LIMIT_EXCEEDED")
        entities = tuple(EntitySpec.from_mapping(item) for item in entities_raw)
        entity_names = {entity.singular for entity in entities}
        if len(entity_names) != len(entities):
            raise RequestValidationError("ENTITY_NAMES_DUPLICATED")
        entity_fields = {entity.singular: {field.name for field in entity.fields} for entity in entities}
        relations_raw = mapping.get("relations", [])
        if not isinstance(relations_raw, list):
            raise RequestValidationError("RELATIONS_MUST_BE_ARRAY")
        relations = tuple(RelationSpec.from_mapping(item, entity_fields=entity_fields) for item in relations_raw)
        if persistence == "postgresql" and require_approval:
            if any(
                relation.kind != "many-to-one" or relation.source_field is None or relation.target_field != "id"
                for relation in relations
            ):
                raise RequestValidationError("PRODUCTION_RELATION_PROFILE_UNSUPPORTED")
            adjacency: dict[str, set[str]] = {name: set() for name in entity_names}
            for relation in relations:
                adjacency[relation.source].add(relation.target)
            visiting: set[str] = set()
            visited: set[str] = set()

            def relation_cycle(node: str) -> bool:
                if node in visiting:
                    return True
                if node in visited:
                    return False
                visiting.add(node)
                cyclic = any(relation_cycle(target) for target in adjacency[node])
                visiting.remove(node)
                visited.add(node)
                return cyclic

            if any(relation_cycle(name) for name in sorted(adjacency)):
                raise RequestValidationError("PRODUCTION_RELATION_CYCLE")

        targets_raw = mapping.get("targets")
        if not isinstance(targets_raw, list) or not targets_raw:
            raise RequestValidationError("TARGETS_REQUIRED")
        targets = tuple(TargetSpec.from_mapping(item) for item in targets_raw)
        languages = [target.language for target in targets]
        ports = [target.port for target in targets]
        if len(languages) != len(set(languages)) or len(ports) != len(set(ports)):
            raise RequestValidationError("TARGET_LANGUAGE_AND_PORT_MUST_BE_UNIQUE")
        allowed_targets = SUPPORTED_PROFILE_TARGETS.get((persistence, auth_mode))
        if allowed_targets is None:
            raise RequestValidationError(f"PROFILE_COMBINATION_UNSUPPORTED:{persistence}:{auth_mode}")
        unsupported_profile_targets = sorted(set(languages) - allowed_targets)
        if unsupported_profile_targets:
            raise RequestValidationError(
                "PROFILE_TARGET_COMBINATION_UNSUPPORTED:"
                f"{persistence}:{auth_mode}:{','.join(unsupported_profile_targets)}"
            )

        requirements = mapping.get("requirements")
        _validate_requirements(requirements)
        assert isinstance(requirements, list)
        requirement_ids = {str(item["id"]) for item in requirements}
        _validate_criteria(mapping.get("acceptance_criteria"), requirement_ids=requirement_ids)
        _validate_business_rules(mapping.get("business_rules"))
        _validate_permissions(mapping.get("permissions"), entity_names=entity_names)

        questions = mapping.get("open_questions")
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
            project_kind=project_kind,
            persistence=persistence,
            auth_mode=auth_mode,
            entities=entities,
            relations=relations,
            targets=targets,
        )

    @property
    def entity(self) -> EntitySpec:
        return self.entities[0]

    @property
    def project_class(self) -> str:
        return pascal(self.project_name)

    @property
    def entity_class(self) -> str:
        return pascal(self.entity.singular)

    @property
    def request_hash(self) -> str:
        return sha256_json(self.raw)

    @property
    def requires_database(self) -> bool:
        return self.persistence == "postgresql"

    @property
    def requires_authentication(self) -> bool:
        return self.auth_mode in {"jwt", "oidc"}

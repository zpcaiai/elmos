from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from .models import (
    SUPPORTED_AUTH_MODES,
    SUPPORTED_LANGUAGES,
    SUPPORTED_PERSISTENCE,
    SUPPORTED_PROFILE_TARGETS,
    SUPPORTED_PROJECT_KINDS,
    TARGET_PROFILES,
    SynthesisRequest,
    identifier,
    project_description,
    project_namespace,
    request_payload,
    sha256_json,
    slugify,
)

_DOMAIN_ENTITY_ALIASES = {
    "订单": "order",
    "用户": "user",
    "客户": "customer",
    "商品": "product",
    "产品": "product",
    "库存": "inventory",
    "工单": "work_order",
    "任务": "task",
    "项目": "project",
    "发票": "invoice",
    "支付": "payment",
    "设备": "device",
    "告警": "alert",
}
_ENTITY_MARKER = re.compile(
    r"(?:entities?|实体|对象|数据模型)\s*[:：]\s*([A-Za-z][A-Za-z0-9_\-\s,，、]{0,300})",
    re.IGNORECASE,
)
_FIELD_MARKER = re.compile(
    r"([A-Za-z][A-Za-z0-9_-]*)\s*(?:fields?|字段)\s*[:：]\s*([^;\n。]+)",
    re.IGNORECASE,
)
_RELATION_MARKER = re.compile(
    r"(?P<source>[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]+)"
    r"(?:\.(?P<source_field>[A-Za-z][A-Za-z0-9_-]*))?\s*"
    r"(?:->|belongs\s+to|属于)\s*"
    r"(?P<target>[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]+)"
    r"(?:\.(?P<target_field>[A-Za-z][A-Za-z0-9_-]*))?",
    re.IGNORECASE,
)
_RELATION_SECTION = re.compile(r"(?:relations?|关系)\s*[:：]", re.IGNORECASE)
_RULE_MARKER = re.compile(
    r"(?:business\s+rules?|业务规则|规则)\s*[:：]\s*([^;\n。]+)",
    re.IGNORECASE,
)
_PERMISSION_MARKER = re.compile(
    r"(?:permissions?|权限)\s*[:：]\s*([^;\n。]+)",
    re.IGNORECASE,
)
_PERMISSION_SPEC = re.compile(
    r"(?P<actor>[A-Za-z][A-Za-z0-9_-]*)\s*:\s*"
    r"(?:(?P<effect>allow|deny|允许|拒绝)\s*:\s*)?"
    r"(?P<actions>[A-Za-z\u4e00-\u9fff/,，、]+)\s*:\s*"
    r"(?P<resource>[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]+|\*)",
    re.IGNORECASE,
)


def _default_fields() -> list[dict[str, Any]]:
    return [
        {"name": "name", "type": "string", "required": True},
        {"name": "description", "type": "string", "required": False},
        {"name": "active", "type": "boolean", "required": True},
    ]


def _normalize_field_type(value: str) -> str:
    aliases = {
        "str": "string",
        "text": "string",
        "int": "integer",
        "long": "integer",
        "float": "number",
        "double": "number",
        "decimal": "number",
        "bool": "boolean",
        "date": "datetime",
        "timestamp": "datetime",
    }
    normalized = value.strip().lower().rstrip("!?")
    return aliases.get(normalized, normalized)


def _pluralize(value: str) -> str:
    if value.endswith("y") and len(value) > 1 and value[-2] not in "aeiou":
        return f"{value[:-1]}ies"
    if value.endswith(("s", "x", "z", "ch", "sh")):
        return f"{value}es"
    return f"{value}s"


def _entity_reference(value: str) -> str:
    translated = _DOMAIN_ENTITY_ALIASES.get(value.strip(), value)
    return identifier(translated)


def _parse_field_marker(description: str, entity_name: str) -> list[dict[str, Any]] | None:
    for match in _FIELD_MARKER.finditer(description):
        if identifier(match.group(1)) != entity_name:
            continue
        fields: list[dict[str, Any]] = []
        for raw_field in re.split(r"[,，、]", match.group(2)):
            parts = [part.strip() for part in raw_field.split(":")]
            if not parts or not parts[0]:
                continue
            raw_name = parts[0]
            required = (
                raw_name.endswith("!")
                or (len(parts) > 1 and parts[1].endswith("!"))
                or any(part.lower() in {"required", "必填"} for part in parts[2:])
            )
            field_name = identifier(raw_name.rstrip("!?"))
            field_type = _normalize_field_type(parts[1] if len(parts) > 1 else "string")
            fields.append({"name": field_name, "type": field_type, "required": required})
        if fields:
            return fields
    return None


def infer_entities(description: str, explicit_entity: str | None = None) -> list[dict[str, Any]]:
    names: list[str] = []
    if explicit_entity:
        names.append(identifier(explicit_entity))
    marker = _ENTITY_MARKER.search(description)
    if marker:
        names.extend(identifier(value) for value in re.split(r"[,，、\s]+", marker.group(1)) if value.strip())
    else:
        for source, target in _DOMAIN_ENTITY_ALIASES.items():
            if source in description:
                names.append(target)
    unique_names = list(dict.fromkeys(names))[:20]
    return [
        {
            "singular": name,
            "plural": _pluralize(name),
            "fields": _parse_field_marker(description, name) or _default_fields(),
        }
        for name in unique_names
    ]


def infer_relations(
    description: str,
    entity_fields: Mapping[str, set[str]],
) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    for match in _RELATION_MARKER.finditer(description):
        source = _entity_reference(match.group("source"))
        target = _entity_reference(match.group("target"))
        source_field = identifier(match.group("source_field")) if match.group("source_field") else None
        target_field = identifier(match.group("target_field")) if match.group("target_field") else None
        if source not in entity_fields or target not in entity_fields or source == target:
            continue
        if source_field and source_field not in entity_fields[source]:
            continue
        if target_field and target_field not in entity_fields[target] | {"id"}:
            continue
        relation: dict[str, Any] = {
            "source": source,
            "target": target,
            "kind": "many-to-one",
            "required": True,
        }
        if source_field:
            relation["source_field"] = source_field
        if target_field:
            relation["target_field"] = target_field
        relations.append(relation)
    return relations


def _rule_predicate(
    statement: str,
    entity_fields: Mapping[str, set[str]],
) -> dict[str, Any] | None:
    comparison = re.fullmatch(
        r"\s*(?P<entity>[A-Za-z][A-Za-z0-9_-]*)\."
        r"(?P<field>[A-Za-z][A-Za-z0-9_-]*)\s*"
        r"(?:(?:must\s+be\s+)?(?P<word>non-negative|positive)|"
        r"(?P<operator>>=|>|<=|<|==|!=)\s*(?P<value>-?\d+(?:\.\d+)?))\s*",
        statement,
        re.IGNORECASE,
    )
    if comparison is None:
        comparison = re.fullmatch(
            r"\s*(?P<entity>[A-Za-z][A-Za-z0-9_-]*)\."
            r"(?P<field>[A-Za-z][A-Za-z0-9_-]*)\s*"
            r"(?P<word>必须非负|必须为正)\s*",
            statement,
        )
    if comparison is None:
        return None
    entity_name = identifier(comparison.group("entity"))
    field_name = identifier(comparison.group("field"))
    if entity_name not in entity_fields or field_name not in entity_fields[entity_name]:
        return None
    word = comparison.groupdict().get("word")
    operator = comparison.groupdict().get("operator")
    value = comparison.groupdict().get("value")
    normalized_operator = {
        "non-negative": "gte",
        "必须非负": "gte",
        "positive": "gt",
        "必须为正": "gt",
        ">=": "gte",
        ">": "gt",
        "<=": "lte",
        "<": "lt",
        "==": "eq",
        "!=": "neq",
    }[(word or operator or "").lower()]
    number: int | float = 0 if word else float(value or "0")
    if isinstance(number, float) and number.is_integer():
        number = int(number)
    return {
        "type": "field-comparison",
        "entity": entity_name,
        "field": field_name,
        "operator": normalized_operator,
        "value": number,
    }


def infer_business_rules(
    description: str,
    entity_fields: Mapping[str, set[str]],
) -> list[dict[str, Any]]:
    statements = [match.group(1).strip() for match in _RULE_MARKER.finditer(description) if match.group(1).strip()][:50]
    rules: list[dict[str, Any]] = []
    for index, statement in enumerate(dict.fromkeys(statements), 1):
        predicate = _rule_predicate(statement, entity_fields)
        rules.append(
            {
                "id": f"BR-{index:03d}",
                "statement": statement,
                "enforcement": "application" if predicate else "manual",
                **({"predicate": predicate} if predicate else {}),
            }
        )
    return rules


def infer_permissions(
    description: str,
    *,
    entity_names: set[str],
) -> list[dict[str, Any]]:
    action_aliases = {
        "create": ("create",),
        "read": ("read",),
        "update": ("update",),
        "delete": ("delete",),
        "manage": ("manage",),
        "crud": ("create", "read", "update", "delete"),
        "创建": ("create",),
        "读取": ("read",),
        "查询": ("read",),
        "更新": ("update",),
        "删除": ("delete",),
        "管理": ("manage",),
    }
    effect_aliases = {"允许": "allow", "拒绝": "deny"}
    permissions: list[dict[str, Any]] = []
    for marker in _PERMISSION_MARKER.finditer(description):
        match = _PERMISSION_SPEC.fullmatch(marker.group(1).strip())
        if match is None:
            continue
        resource = _entity_reference(match.group("resource"))
        if resource != "*" and resource not in entity_names:
            continue
        effect_value = (match.group("effect") or "allow").lower()
        effect = effect_aliases.get(effect_value, effect_value)
        actions: list[str] = []
        for raw_action in re.split(r"[/,，、]", match.group("actions")):
            actions.extend(action_aliases.get(raw_action.strip().lower(), ()))
        for action in dict.fromkeys(actions):
            permissions.append(
                {
                    "actor": identifier(match.group("actor")),
                    "action": action,
                    "resource": resource,
                    "effect": effect,
                }
            )
    return permissions[:200]


def _normalize_entities(
    raw_entities: Iterable[Mapping[str, Any]] | None,
    *,
    description: str,
    entity: str | None,
) -> list[dict[str, Any]]:
    if raw_entities is None:
        return infer_entities(description, entity)
    normalized: list[dict[str, Any]] = []
    for raw in raw_entities:
        singular = identifier(str(raw.get("singular", "")))
        plural = identifier(str(raw.get("plural", _pluralize(singular))))
        fields_raw = raw.get("fields", _default_fields())
        if not isinstance(fields_raw, list):
            raise ValueError(f"ENTITY_FIELDS_REQUIRED:{singular}")
        fields = [
            {
                "name": identifier(str(field.get("name", ""))),
                "type": _normalize_field_type(str(field.get("type", "string"))),
                "required": field.get("required", True),
            }
            for field in fields_raw
            if isinstance(field, Mapping)
        ]
        normalized.append({"singular": singular, "plural": plural, "fields": fields})
    return normalized


def _target_mapping(language: str) -> dict[str, Any]:
    profile = TARGET_PROFILES[language]
    return {
        "language": language,
        "framework": profile["framework"],
        "runtime": profile["runtime"],
        "port": profile["port"],
    }


def create_draft(
    *,
    name: str,
    description: str,
    entity: str | None = None,
    entities: Iterable[Mapping[str, Any]] | None = None,
    relations: Iterable[Mapping[str, Any]] = (),
    business_rules: Iterable[str | Mapping[str, Any]] = (),
    permissions: Iterable[Mapping[str, Any]] = (),
    namespace: str | None = None,
    languages: Iterable[str] = SUPPORTED_LANGUAGES,
    project_kind: str = "api",
    persistence: str = "in-memory",
    auth_mode: str = "none",
    requirement_sources: Iterable[Mapping[str, Any]] = (),
    source_bundle_sha256: str | None = None,
) -> dict[str, Any]:
    project_name = slugify(name)
    normalized_description = project_description(description)
    normalized_namespace = project_namespace(namespace or f"com.example.{project_name.replace('-', '')}")
    normalized_sources = [dict(source) for source in requirement_sources]
    if project_kind not in SUPPORTED_PROJECT_KINDS:
        raise ValueError(f"PROJECT_KIND_INVALID:{project_kind}")
    if persistence not in SUPPORTED_PERSISTENCE:
        raise ValueError(f"PERSISTENCE_INVALID:{persistence}")
    if auth_mode not in SUPPORTED_AUTH_MODES:
        raise ValueError(f"AUTH_MODE_INVALID:{auth_mode}")

    selected = tuple(dict.fromkeys(languages))
    if not selected:
        raise ValueError("TARGETS_REQUIRED")
    unsupported = sorted(set(selected) - set(SUPPORTED_LANGUAGES))
    if unsupported:
        raise ValueError(f"UNSUPPORTED_TARGET_LANGUAGES:{','.join(unsupported)}")
    allowed_targets = SUPPORTED_PROFILE_TARGETS.get((persistence, auth_mode))
    if allowed_targets is None:
        raise ValueError(f"PROFILE_COMBINATION_UNSUPPORTED:{persistence}:{auth_mode}")
    unsupported_profile_targets = sorted(set(selected) - allowed_targets)
    if unsupported_profile_targets:
        raise ValueError(
            f"PROFILE_TARGET_COMBINATION_UNSUPPORTED:{persistence}:{auth_mode}:{','.join(unsupported_profile_targets)}"
        )

    normalized_entities = _normalize_entities(entities, description=normalized_description, entity=entity)
    questions: list[dict[str, str]] = []
    if not normalized_entities:
        fallback = identifier(project_name.split("-")[0])
        normalized_entities = [{"singular": fallback, "plural": _pluralize(fallback), "fields": _default_fields()}]
        questions.append(
            {
                "id": "Q-ENTITY-001",
                "question": f"未能从描述中可靠识别业务实体。请确认 {fallback} 并补充字段。",
                "impact": "high",
            }
        )
    entity_names = {str(item["singular"]) for item in normalized_entities}
    entity_fields = {
        str(item["singular"]): {
            str(field["name"]) for field in item["fields"] if isinstance(field, Mapping) and "name" in field
        }
        for item in normalized_entities
    }

    normalized_relations = [dict(item) for item in relations]
    if not normalized_relations:
        relation_matches = list(_RELATION_MARKER.finditer(normalized_description))
        normalized_relations = infer_relations(normalized_description, entity_fields)
        if _RELATION_SECTION.search(normalized_description) and len(normalized_relations) != len(relation_matches):
            questions.append(
                {
                    "id": "Q-RELATION-001",
                    "question": (
                        "检测到关系声明，但未能绑定到已识别实体。请使用 source.field -> target.field 格式确认。"
                    ),
                    "impact": "high",
                }
            )
    if persistence == "postgresql":
        unsupported_relations = [
            relation
            for relation in normalized_relations
            if relation.get("kind") != "many-to-one"
            or not relation.get("source_field")
            or relation.get("target_field") != "id"
        ]
        adjacency: dict[str, set[str]] = {name: set() for name in entity_names}
        for relation in normalized_relations:
            source = str(relation.get("source", ""))
            target = str(relation.get("target", ""))
            if source in adjacency and target in adjacency:
                adjacency[source].add(target)
        visiting: set[str] = set()
        visited: set[str] = set()

        def has_cycle(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            cyclic = any(has_cycle(target) for target in adjacency[node])
            visiting.remove(node)
            visited.add(node)
            return cyclic

        relation_cycle = any(has_cycle(name) for name in sorted(adjacency))
        if unsupported_relations or relation_cycle:
            questions.append(
                {
                    "id": "Q-RELATION-PRODUCTION-001",
                    "question": (
                        "PostgreSQL 生产配置仅接受无环的显式 many-to-one 外键，格式必须是 source.field -> target.id。"
                    ),
                    "impact": "high",
                }
            )

    normalized_rules: list[dict[str, Any]] = []
    for index, raw_rule in enumerate(business_rules, 1):
        if isinstance(raw_rule, str):
            predicate = _rule_predicate(raw_rule.strip(), entity_fields)
            normalized_rules.append(
                {
                    "id": f"BR-{index:03d}",
                    "statement": raw_rule.strip(),
                    "enforcement": "application" if predicate else "manual",
                    **({"predicate": predicate} if predicate else {}),
                }
            )
        else:
            normalized_rules.append(dict(raw_rule))
    if not normalized_rules:
        normalized_rules = infer_business_rules(normalized_description, entity_fields)
    if not normalized_rules:
        normalized_rules.append(
            {
                "id": "BR-001",
                "statement": "Records are updated or deleted only when the requested identifier exists.",
                "enforcement": "application",
                "predicate": {"type": "record-exists-on-mutation"},
            }
        )
    if (persistence == "postgresql" or auth_mode in {"jwt", "oidc"}) and any(
        rule.get("enforcement") == "manual" for rule in normalized_rules
    ):
        questions.append(
            {
                "id": "Q-RULE-001",
                "question": (
                    "生产配置包含无法编译的业务规则。请改为 entity.field >= value、"
                    "entity.field must be non-negative 等可执行表达式。"
                ),
                "impact": "high",
            }
        )

    normalized_permissions = [dict(item) for item in permissions]
    if not normalized_permissions:
        normalized_permissions = infer_permissions(
            normalized_description,
            entity_names=entity_names,
        )
        if _PERMISSION_MARKER.search(normalized_description) and not normalized_permissions:
            questions.append(
                {
                    "id": "Q-PERMISSION-001",
                    "question": (
                        "检测到权限声明但无法安全解析。请使用 权限: actor:create/read/update/delete:resource 格式确认。"
                    ),
                    "impact": "high",
                }
            )
    permission_policy_declared = bool(normalized_permissions)
    if not normalized_permissions:
        normalized_permissions = [
            {
                "actor": "api_user",
                "action": action,
                "resource": entity_name,
                "effect": "deny",
            }
            for entity_name in sorted(entity_names)
            for action in ("create", "read", "update", "delete")
        ]
    if auth_mode in {"jwt", "oidc"} and not permission_policy_declared:
        questions.append(
            {
                "id": "Q-PERMISSION-PRODUCTION-001",
                "question": (
                    "JWT/OIDC 生产配置必须显式声明 Actor、资源、动作与 allow/deny；"
                    "当前已按默认拒绝生成，但在批准前必须确认授权矩阵。"
                ),
                "impact": "high",
            }
        )

    requirements: list[dict[str, Any]] = []
    criteria: list[dict[str, Any]] = []
    imported_source_refs = (
        [{"source_id": str(source["id"]), "location": "imported-requirements"} for source in normalized_sources]
        if normalized_sources
        else [{"source_id": "natural-language-request", "location": "description"}]
    )
    for index, entity_spec in enumerate(normalized_entities, 1):
        singular = str(entity_spec["singular"])
        requirement_id = f"REQ-CRUD-{index:03d}"
        requirements.append(
            {
                "id": requirement_id,
                "kind": "functional",
                "statement": (
                    f"Authorized API users can create, list, retrieve, update, and delete {singular} records."
                ),
                "status": "approved",
                "priority": "must",
                "risk": "medium",
                "source_refs": imported_source_refs,
            }
        )
        criteria.append(
            {
                "id": f"AC-CRUD-{index:03d}",
                "requirement_ids": [requirement_id],
                "statement": (
                    f"Create, list, get, update, and delete operations for {singular} "
                    "return deterministic HTTP results."
                ),
                "verification_type": "test",
            }
        )
    requirements.extend(
        [
            {
                "id": "REQ-HEALTH-001",
                "kind": "nonfunctional",
                "statement": "Each generated service exposes a deterministic health endpoint.",
                "status": "approved",
                "priority": "must",
                "risk": "low",
                "source_refs": [{"source_id": "PG159", "location": "startup-probe"}],
            },
            {
                "id": "REQ-DELIVERY-001",
                "kind": "policy-derived",
                "statement": (
                    "Every selected target includes tests, externalized configuration, CI, container, "
                    "API contracts, traceability, and a reproducible verification command."
                ),
                "status": "approved",
                "priority": "must",
                "risk": "high",
                "source_refs": [{"source_id": "PG077-PG417", "location": "project-delivery-packs"}],
            },
        ]
    )
    criteria.extend(
        [
            {
                "id": "AC-HEALTH-001",
                "requirement_ids": ["REQ-HEALTH-001"],
                "statement": "After startup, GET /health returns HTTP 200 and status UP.",
                "verification_type": "test",
            },
            {
                "id": "AC-DELIVERY-001",
                "requirement_ids": ["REQ-DELIVERY-001"],
                "statement": "Each selected target completes its declared clean build, test, and startup checks.",
                "verification_type": "test",
            },
        ]
    )

    draft: dict[str, Any] = {
        "schema_version": "1.1.0",
        "project": {
            "id": f"PRJ-{project_name.upper()}",
            "name": project_name,
            "description": normalized_description,
            "namespace": normalized_namespace,
            "kind": project_kind,
            "persistence": persistence,
            "auth_mode": auth_mode,
        },
        "actors": [{"id": "api_user", "name": "API user", "kind": "human"}],
        "entities": normalized_entities,
        "relations": normalized_relations,
        "business_rules": normalized_rules,
        "permissions": normalized_permissions,
        "requirements": requirements,
        "acceptance_criteria": criteria,
        "constraints": [
            {
                "id": "CON-SECRET-001",
                "category": "technical",
                "statement": "No secret values are generated.",
                "hard": True,
            },
            {
                "id": "CON-STORE-001",
                "category": "technical",
                "statement": (
                    f"The selected persistence profile is {persistence}; schema migration, rollback, "
                    "restore, and runtime evidence must be produced by its exact provider workflow."
                ),
                "hard": True,
            },
        ],
        "assumptions": [
            {
                "id": "ASM-AUTH-001",
                "statement": (
                    f"Authentication profile is {auth_mode}; issuer, audience, signing material, "
                    "scope policy, and provider reachability are runtime configuration obligations."
                ),
                "status": "accepted",
                "impact": "high",
            }
        ],
        "quality_attributes": [
            {
                "id": "QA-START-001",
                "name": "operability",
                "scenario": "A generated target starts in a clean development environment.",
                "measure": "The service becomes healthy within 30 seconds and exposes its configured port.",
            }
        ],
        "targets": [_target_mapping(language) for language in selected],
        "open_questions": questions,
        "approval": {"status": "DRAFT"},
    }
    if normalized_sources:
        draft["requirement_sources"] = normalized_sources
        draft["source_bundle_sha256"] = source_bundle_sha256
    SynthesisRequest.from_mapping(draft, require_approval=False)
    return draft


def approve_request(mapping: dict[str, Any], *, actor: str, approved_at: str | None = None) -> dict[str, Any]:
    SynthesisRequest.from_mapping(mapping, require_approval=False)
    if mapping.get("open_questions"):
        raise ValueError("OPEN_QUESTIONS_BLOCK_APPROVAL")
    approver = actor.strip()
    if not approver or len(approver) > 200 or any(ord(character) < 32 for character in approver):
        raise ValueError("APPROVER_INVALID")
    timestamp = approved_at or datetime.now(UTC).replace(microsecond=0).isoformat()
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise ValueError("APPROVED_AT_INVALID") from error
    if parsed_timestamp.tzinfo is None:
        raise ValueError("APPROVED_AT_TIMEZONE_REQUIRED")
    approved = deepcopy(mapping)
    approved["approval"] = {
        "status": "APPROVED",
        "approved_by": approver,
        "approved_at": parsed_timestamp.astimezone(UTC).replace(microsecond=0).isoformat(),
        "approved_payload_sha256": sha256_json(request_payload(approved)),
    }
    SynthesisRequest.from_mapping(approved)
    return approved

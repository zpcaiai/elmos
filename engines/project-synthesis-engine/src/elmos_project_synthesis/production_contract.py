"""The language-neutral contract every production target must satisfy.

The Python production profile grew organically, so its HTTP surface, SQL, env
var names and integration scenario were all expressed inline. Adding six more
languages that way would mean six more independent definitions of the same
contract, and the first divergence between them would be invisible.

This module states the contract once. A language target consumes these
descriptors and only supplies syntax, so "does Go enforce tenant isolation the
same way Java does" becomes a property of shared data rather than a matter of
reading two emitters side by side.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import EntitySpec, FieldSpec, SynthesisRequest

# Every production target reads its secrets and endpoints from the same
# environment. The local runtime harness sets exactly these names, so a target
# that invents its own will fail integration rather than silently diverge.
ENV_DATABASE_URL_FILE = "ELMOS_DATABASE_URL_FILE"
ENV_AUTH_ISSUER = "ELMOS_AUTH_ISSUER"
ENV_AUTH_AUDIENCE = "ELMOS_AUTH_AUDIENCE"
ENV_JWT_SECRET_FILE = "ELMOS_JWT_HMAC_SECRET_FILE"  # noqa: S105 - env var name, not a secret
ENV_OIDC_JWKS_FILE = "ELMOS_OIDC_JWKS_FILE"
ENV_OIDC_PRIVATE_KEY_FILE = "ELMOS_OIDC_PRIVATE_KEY_FILE"
ENV_RUNTIME_STATE_DIR = "ELMOS_RUNTIME_STATE_DIR"

TENANT_CLAIM = "tenant_id"
TENANT_SETTING = "app.tenant_id"
LOCAL_ISSUER = "https://identity.local.invalid/"
LOCAL_AUDIENCE = "generated-api"
LOCAL_KEY_ID = "elmos-local-integration"
DATABASE_ROLE = "app_runtime"
DATABASE_NAME = "app_db"

AuthMode = Literal["jwt", "oidc"]


@dataclass(frozen=True)
class EntitySql:
    """The exact statements a target must issue for one entity.

    Identifiers come from the strict entity and field validators, never from
    request text, so these strings are safe to embed. Values are always bound
    as parameters -- the placeholder style is the only thing a language may
    change.
    """

    entity: str
    plural: str
    columns: tuple[str, ...]
    list_sql: str
    get_sql: str
    upsert_sql: str
    delete_sql: str

    @property
    def column_count(self) -> int:
        return len(self.columns)


def _quoted(columns: tuple[str, ...]) -> str:
    return ", ".join(f'"{column}"' for column in columns)


def entity_sql(entity: EntitySpec, *, placeholder: str = "?") -> EntitySql:
    """Build the four statements for an entity in a placeholder style.

    ``placeholder`` is a format string receiving the 1-based parameter index so
    both positional (``?``) and ordinal (``$1``, ``%s``) dialects are covered.
    """
    columns = tuple(field.name for field in entity.fields)
    quoted = _quoted(columns)
    table = f'"app"."{entity.plural}"'

    def mark(index: int) -> str:
        return placeholder.format(index) if "{" in placeholder else placeholder

    insert_values = ", ".join(mark(index) for index in range(3, 3 + len(columns)))
    assignments = ", ".join(f'"{column}" = EXCLUDED."{column}"' for column in columns)
    # noqa: S608 below - every identifier here is produced by the strict entity
    # and field validators, and every value is bound as a parameter.
    return EntitySql(
        entity=entity.singular,
        plural=entity.plural,
        columns=columns,
        list_sql=f'SELECT "id", {quoted} FROM {table} ORDER BY "id"',  # noqa: S608
        get_sql=f'SELECT "id", {quoted} FROM {table} WHERE "id" = {mark(1)}',  # noqa: S608
        upsert_sql=(
            f'INSERT INTO {table} ("tenant_id", "id", {quoted}) '  # noqa: S608
            f"VALUES ({mark(1)}, {mark(2)}, {insert_values}) "
            f'ON CONFLICT ("tenant_id", "id") DO UPDATE SET {assignments} '
            f'RETURNING "id", {quoted}'
        ),
        delete_sql=f'DELETE FROM {table} WHERE "id" = {mark(1)}',  # noqa: S608
    )


def all_entity_sql(request: SynthesisRequest, *, placeholder: str = "?") -> list[EntitySql]:
    return [entity_sql(entity, placeholder=placeholder) for entity in request.entities]


def uuid_relation_fields(request: SynthesisRequest) -> set[tuple[str, str]]:
    """(entity, field) pairs the migration declares as uuid foreign keys."""

    return {
        (relation.source, relation.source_field)
        for relation in request.canonical_relations
        if relation.source_field is not None and relation.target_field == "id"
    }


def relation_parents(request: SynthesisRequest, entity_name: str) -> list[tuple[str, str]]:
    """(source_field, parent entity) pairs required before inserting entity_name."""

    return [
        (relation.source_field, relation.target)
        for relation in request.canonical_relations
        if relation.source == entity_name
        and relation.source_field is not None
        and relation.target_field == "id"
    ]


def fixture_chain(request: SynthesisRequest, entity_name: str) -> list[str]:
    """Parent entities that must exist before entity_name, parents-first."""

    ordered: list[str] = []
    visiting: set[str] = set()

    def walk(name: str) -> None:
        if name in visiting:
            raise ValueError(f"PRODUCTION_RELATION_CYCLE:{name}")
        visiting.add(name)
        for _field, parent in relation_parents(request, name):
            if parent not in ordered:
                walk(parent)
                ordered.append(parent)
        visiting.discard(name)

    walk(entity_name)
    return ordered


@dataclass(frozen=True)
class RouteSpec:
    method: str
    path: str
    authenticated: bool
    description: str


def routes(entity: EntitySpec) -> list[RouteSpec]:
    """The uniform CRUD surface every production target exposes."""
    return [
        RouteSpec("GET", f"/{entity.plural}", True, f"List {entity.plural} for the caller's tenant"),
        RouteSpec("GET", f"/{entity.plural}/{{id}}", True, f"Read one {entity.singular}"),
        RouteSpec("PUT", f"/{entity.plural}/{{id}}", True, f"Create or replace one {entity.singular}"),
        RouteSpec("DELETE", f"/{entity.plural}/{{id}}", True, f"Delete one {entity.singular}"),
    ]


HEALTH_ROUTE = RouteSpec("GET", "/health", False, "Unauthenticated liveness and readiness probe")


@dataclass(frozen=True)
class IntegrationStep:
    """One assertion the DB-backed integration test must make.

    Every language runs the same scenario against the same provisioned
    database. A target that cannot satisfy a step fails integration instead of
    quietly implementing a weaker check.
    """

    id: str
    description: str


INTEGRATION_SCENARIO: tuple[IntegrationStep, ...] = (
    IntegrationStep("health-unauthenticated", "GET /health succeeds without a bearer token"),
    IntegrationStep("missing-token-rejected", "A request without a bearer token is rejected with 401"),
    IntegrationStep("bad-signature-rejected", "A token signed with the wrong key is rejected with 401"),
    IntegrationStep("wrong-audience-rejected", "A token for another audience is rejected with 401"),
    IntegrationStep("wrong-issuer-rejected", "A token from another issuer is rejected with 401"),
    IntegrationStep("missing-tenant-claim-rejected", "A token without the tenant claim is rejected with 401"),
    IntegrationStep("upsert-and-read", "PUT then GET returns the persisted record for the caller's tenant"),
    IntegrationStep("list-scoped-to-tenant", "GET list returns only the caller tenant's rows"),
    IntegrationStep("cross-tenant-read-blocked", "Another tenant's token cannot read the record"),
    IntegrationStep("delete-removes-record", "DELETE removes the record and a later GET returns 404"),
)


def http_status_contract() -> dict[str, int]:
    return {
        "ok": 200,
        "created_or_replaced": 200,
        "deleted": 204,
        "unauthorized": 401,
        "not_found": 404,
        "unprocessable": 422,
    }


def openapi_field_type(field: FieldSpec) -> str:
    return {
        "string": "string",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
        "datetime": "string",
    }[field.type]


def production_contract(request: SynthesisRequest) -> dict[str, object]:
    """A machine-readable statement of what the production profile guarantees."""
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.production-profile-contract",
        "persistence": request.persistence,
        "auth_mode": request.auth_mode,
        "tenant_claim": TENANT_CLAIM,
        "tenant_setting": TENANT_SETTING,
        "database_role": DATABASE_ROLE,
        "isolation": "postgresql-row-level-security-forced",
        "environment": {
            "database_url_file": ENV_DATABASE_URL_FILE,
            "auth_issuer": ENV_AUTH_ISSUER,
            "auth_audience": ENV_AUTH_AUDIENCE,
            "jwt_secret_file": ENV_JWT_SECRET_FILE,
            "oidc_jwks_file": ENV_OIDC_JWKS_FILE,
        },
        "routes": [
            {"method": route.method, "path": route.path, "authenticated": route.authenticated}
            for entity in request.entities
            for route in routes(entity)
        ]
        + [{"method": HEALTH_ROUTE.method, "path": HEALTH_ROUTE.path, "authenticated": False}],
        "http_status": http_status_contract(),
        "integration_scenario": [
            {"id": step.id, "description": step.description} for step in INTEGRATION_SCENARIO
        ],
        "external_evidence_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }

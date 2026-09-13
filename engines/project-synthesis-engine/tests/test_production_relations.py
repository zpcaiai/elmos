"""The relational-v2 production profile lowers all four relation kinds.

Previously `many-to-one` only. Looking at what a relation actually becomes -- a
foreign-key column on one side referencing the other side's `id` -- two of the
remaining three turn out to be the same construct rather than new machinery:

  one-to-one   the identical foreign key plus UNIQUE on (tenant_id, fk).
               "At most one source row per target row" constrains the same
               column; it is not a different shape.
  one-to-many  the same relation declared from the other end. `A one-to-many B`
               and `B many-to-one A` describe one foreign key.

`many-to-many` is lowered into a deterministic association entity with two
tenant-scoped foreign keys, pair uniqueness, cascade cleanup and the same CRUD
surface every selected language already generates for explicit entities.

Declared `kind` is preserved so the ER diagram still shows what the author
wrote; generation reads `canonical_relations` so the emitters keep one path.

The production acceptance matrix executes the generated migrations and CRUD
journeys against the exact PostgreSQL profile; unit tests here additionally
pin the lowering and fail-closed boundaries without making an external or
certification claim.
"""

from __future__ import annotations

from typing import Any

import pytest

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import (
    RequestValidationError,
    SynthesisRequest,
    association_entity_mapping,
)
from elmos_project_synthesis.production_profile import _schema_sql
from elmos_project_synthesis.workspace import render_workspace

_ENTITIES: tuple[dict[str, Any], ...] = (
    {
        "singular": "customer",
        "plural": "customers",
        "fields": [{"name": "name", "type": "string", "required": True}],
    },
    {
        "singular": "order",
        "plural": "orders",
        "fields": [
            {"name": "customer_id", "type": "string", "required": True},
            {"name": "total", "type": "number", "required": True},
        ],
    },
)
_PERMISSIONS = tuple(
    {"actor": "api_user", "action": action, "resource": entity["singular"], "effect": "allow"}
    for entity in _ENTITIES
    for action in ("create", "read", "update", "delete")
)

MANY_TO_ONE = {
    "source": "order",
    "target": "customer",
    "source_field": "customer_id",
    "target_field": "id",
    "kind": "many-to-one",
    "required": True,
}
ONE_TO_ONE = {**MANY_TO_ONE, "kind": "one-to-one"}
# Declared from the other end: the foreign key lives on the many side.
ONE_TO_MANY = {
    "source": "customer",
    "target": "order",
    "source_field": "id",
    "target_field": "customer_id",
    "kind": "one-to-many",
    "required": True,
}
MANY_TO_MANY = {
    "source": "customer",
    "target": "order",
    "kind": "many-to-many",
    "required": True,
}


def _request(relation: dict[str, Any], *, persistence: str = "postgresql") -> SynthesisRequest:
    association_permissions = (
        tuple(
            {
                "actor": "api_user",
                "action": action,
                "resource": "customer_order_link",
                "effect": "allow",
            }
            for action in ("create", "read", "update", "delete")
        )
        if relation["kind"] == "many-to-many"
        else ()
    )
    draft = create_draft(
        name=f"relprobe-{relation['kind']}",
        description="Relation kind probe.",
        entities=_ENTITIES,
        relations=(relation,),
        languages=("java",),
        persistence=persistence,
        auth_mode="jwt" if persistence == "postgresql" else "none",
        permissions=(*_PERMISSIONS, *association_permissions),
        generation_profile=(
            "relational-v2"
            if relation["kind"] == "many-to-many" and persistence != "in-memory"
            else "starter-v1"
        ),
    )
    return SynthesisRequest.from_mapping(
        approve_request(draft, actor="test:relations", approved_at="2026-08-25T00:00:00+00:00"),
        require_approval=True,
    )


def _constraints(request: SynthesisRequest) -> list[str]:
    return [line.strip() for line in _schema_sql(request).splitlines() if line.strip()]


@pytest.mark.parametrize(
    ("label", "relation"),
    [("many-to-one", MANY_TO_ONE), ("one-to-one", ONE_TO_ONE), ("one-to-many", ONE_TO_MANY)],
)
def test_all_three_accepted_kinds_produce_the_same_foreign_key(label: str, relation: dict[str, Any]) -> None:
    """The key is on `orders` and points at `customers.id` in every case --
    including the one declared from the customer end."""

    lines = _constraints(_request(relation))
    assert 'ALTER TABLE "app"."orders" ADD CONSTRAINT "fk_order_customer_id_customer"' in lines
    assert 'FOREIGN KEY ("tenant_id", "customer_id")' in lines
    assert 'REFERENCES "app"."customers" ("tenant_id", "id")' in lines


def test_one_to_one_adds_the_uniqueness_that_makes_it_one_to_one() -> None:
    lines = _constraints(_request(ONE_TO_ONE))
    assert 'ALTER TABLE "app"."orders" ADD CONSTRAINT "uq_order_customer_id"' in lines
    assert 'UNIQUE ("tenant_id", "customer_id");' in lines


@pytest.mark.parametrize(("label", "relation"), [("many-to-one", MANY_TO_ONE), ("one-to-many", ONE_TO_MANY)])
def test_the_other_kinds_add_no_uniqueness(label: str, relation: dict[str, Any]) -> None:
    assert not [line for line in _constraints(_request(relation)) if '"uq_' in line]


def test_many_to_many_lowers_to_a_tenant_scoped_association_entity() -> None:
    request = _request(MANY_TO_MANY)
    assert request.generation_profile == "relational-v2"
    assert request.entities[-1].singular == "customer_order_link"
    assert [field.name for field in request.entities[-1].fields] == ["customer_id", "order_id"]
    assert [(relation.source, relation.target) for relation in request.canonical_relations] == [
        ("customer_order_link", "customer"),
        ("customer_order_link", "order"),
    ]
    schema = _schema_sql(request)
    assert 'CONSTRAINT "uq_customer_order_link_pair" UNIQUE ("tenant_id", "customer_id", "order_id")' in schema
    assert schema.count("ON UPDATE CASCADE ON DELETE CASCADE;") == 2


def test_many_to_many_long_names_keep_distinct_bounded_singular_and_plural() -> None:
    mapping = association_entity_mapping(
        "customer_with_a_long_domain_specific_name_that_reaches_identifier_limit",
        "order_archive_with_a_long_domain_specific_name_reaching_limit",
    )
    assert len(mapping["singular"]) <= 63
    assert len(mapping["plural"]) <= 63
    assert mapping["singular"] != mapping["plural"]
    field_names = [field["name"] for field in mapping["fields"]]
    assert all(len(name) <= 63 for name in field_names)
    assert len(set(field_names)) == 2


def test_many_to_many_requires_relational_v2_and_explicit_association_permissions() -> None:
    blocked = create_draft(
        name="relprobe-many-to-many-blocked",
        description="Many to many profile gate.",
        entities=_ENTITIES,
        relations=(MANY_TO_MANY,),
        languages=("java",),
        persistence="postgresql",
        auth_mode="jwt",
        permissions=_PERMISSIONS,
    )
    assert {question["id"] for question in blocked["open_questions"]} >= {
        "Q-RELATION-PRODUCTION-001"
    }
    with pytest.raises(ValueError, match="OPEN_QUESTIONS_BLOCK_APPROVAL"):
        approve_request(blocked, actor="test:relations")

    permission_blocked = create_draft(
        name="relprobe-many-to-many-permission",
        description="Many to many permission gate.",
        entities=_ENTITIES,
        relations=(MANY_TO_MANY,),
        languages=("java",),
        persistence="postgresql",
        auth_mode="jwt",
        generation_profile="relational-v2",
        permissions=_PERMISSIONS,
    )
    assert "Q-RELATION-PERMISSION-001" in {
        question["id"] for question in permission_blocked["open_questions"]
    }

    explicit_association_blocked = create_draft(
        name="relprobe-many-to-many-explicit-association-permission",
        description="Explicit association entities have the same permission gate.",
        entities=(*_ENTITIES, association_entity_mapping("customer", "order")),
        relations=(MANY_TO_MANY,),
        languages=("java",),
        persistence="postgresql",
        auth_mode="jwt",
        generation_profile="relational-v2",
        permissions=_PERMISSIONS,
    )
    assert "Q-RELATION-PERMISSION-001" in {
        question["id"] for question in explicit_association_blocked["open_questions"]
    }


def test_many_to_many_association_is_emitted_for_all_eight_targets() -> None:
    permissions = (
        *_PERMISSIONS,
        *(
            {
                "actor": "api_user",
                "action": action,
                "resource": "customer_order_link",
                "effect": "allow",
            }
            for action in ("create", "read", "update", "delete")
        ),
    )
    draft = create_draft(
        name="relprobe-many-to-many-all",
        description="Many to many eight-language lowering.",
        entities=_ENTITIES,
        relations=(MANY_TO_MANY,),
        persistence="postgresql",
        auth_mode="jwt",
        generation_profile="relational-v2",
        permissions=permissions,
    )
    request = SynthesisRequest.from_mapping(
        approve_request(draft, actor="test:relations", approved_at="2026-08-25T00:00:00+00:00")
    )
    files = render_workspace(request)
    for directory in ("java", "python", "dotnet", "typescript", "go", "kotlin", "php", "rust"):
        openapi = files[f"{directory}/openapi.yaml"]
        assert "/api/v1/customer_order_links" in openapi


def test_the_declared_kind_survives_for_documentation() -> None:
    """Generation canonicalises; the ER diagram must still say what was written."""

    request = _request(ONE_TO_MANY)
    assert request.relations[0].kind == "one-to-many"
    assert request.relations[0].source == "customer"
    canonical = request.canonical_relations[0]
    assert canonical.source == "order"
    assert canonical.source_field == "customer_id"
    assert canonical.target_field == "id"


def test_canonicalisation_is_identity_for_the_kinds_declared_from_the_key_side() -> None:
    for relation in (MANY_TO_ONE, ONE_TO_ONE):
        request = _request(relation)
        assert request.canonical_relations[0] == request.relations[0]


def test_a_cycle_written_partly_as_one_to_many_is_still_caught() -> None:
    """Cycles are a property of the foreign keys, so they are checked in the
    canonical orientation -- otherwise the inverse spelling would slip past."""

    draft = create_draft(
        name="relprobe-cycle",
        description="Relation cycle probe.",
        entities=_ENTITIES,
        relations=(
            MANY_TO_ONE,
            {
                "source": "order",
                "target": "customer",
                "source_field": "id",
                "target_field": "name",
                "kind": "one-to-many",
                "required": True,
            },
        ),
        languages=("java",),
        persistence="postgresql",
        auth_mode="jwt",
        permissions=_PERMISSIONS,
    )
    with pytest.raises(ValueError):
        approve_request(draft, actor="test:relations", approved_at="2026-08-25T00:00:00+00:00")


def test_one_to_many_still_requires_a_real_target_field() -> None:
    """`source.id -> target.id` is two primary keys pointed at each other."""

    broken = {**ONE_TO_MANY, "target_field": "id"}
    with pytest.raises(ValueError):
        _request(broken)


def test_the_in_memory_profile_still_accepts_every_kind() -> None:
    """The widening is about the PostgreSQL production profile. The broad
    starter profile was never restricted and must stay unrestricted."""

    for relation in (MANY_TO_ONE, ONE_TO_ONE, ONE_TO_MANY, MANY_TO_MANY):
        request = _request(relation, persistence="in-memory")
        assert request.relations[0].kind == relation["kind"]


def test_a_source_field_that_does_not_exist_is_still_rejected() -> None:
    broken = {**MANY_TO_ONE, "source_field": "nonexistent"}
    with pytest.raises((RequestValidationError, ValueError)):
        _request(broken)

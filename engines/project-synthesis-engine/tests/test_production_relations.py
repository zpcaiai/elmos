"""The PostgreSQL production profile takes three of the four relation kinds.

Previously `many-to-one` only. Looking at what a relation actually becomes -- a
foreign-key column on one side referencing the other side's `id` -- two of the
remaining three turn out to be the same construct rather than new machinery:

  one-to-one   the identical foreign key plus UNIQUE on (tenant_id, fk).
               "At most one source row per target row" constrains the same
               column; it is not a different shape.
  one-to-many  the same relation declared from the other end. `A one-to-many B`
               and `B many-to-one A` describe one foreign key.

`many-to-many` stays out, and it is the one that really is feature work: a join
table owned by no entity, its own composite primary key, two foreign keys, and
association endpoints.

Declared `kind` is preserved so the ER diagram still shows what the author
wrote; generation reads `canonical_relations` so the emitters keep one path.

The behaviour is executed, not just rendered: see
`.ai/measurement-2026-08-21/relation-execution-evidence.json`, where each
migration runs on a real PostgreSQL 16.15 and a second child row for the same
parent is accepted for many-to-one / one-to-many and refused with a
UniqueViolation for one-to-one.
"""

from __future__ import annotations

from typing import Any

import pytest

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import RequestValidationError, SynthesisRequest
from elmos_project_synthesis.production_profile import _schema_sql

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
    "source": "order", "target": "customer",
    "source_field": "customer_id", "target_field": "id",
    "kind": "many-to-one", "required": True,
}
ONE_TO_ONE = {**MANY_TO_ONE, "kind": "one-to-one"}
# Declared from the other end: the foreign key lives on the many side.
ONE_TO_MANY = {
    "source": "customer", "target": "order",
    "source_field": "id", "target_field": "customer_id",
    "kind": "one-to-many", "required": True,
}
MANY_TO_MANY = {**MANY_TO_ONE, "kind": "many-to-many"}


def _request(relation: dict[str, Any], *, persistence: str = "postgresql") -> SynthesisRequest:
    draft = create_draft(
        name=f"relprobe-{relation['kind']}",
        description="Relation kind probe.",
        entities=_ENTITIES,
        relations=(relation,),
        languages=("java",),
        persistence=persistence,
        auth_mode="jwt" if persistence == "postgresql" else "none",
        permissions=_PERMISSIONS,
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
def test_all_three_accepted_kinds_produce_the_same_foreign_key(
    label: str, relation: dict[str, Any]
) -> None:
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


def test_many_to_many_is_still_refused_because_it_needs_a_join_table() -> None:
    with pytest.raises(ValueError) as raised:
        _request(MANY_TO_MANY)
    # Intake raises it as an unresolved question; either gate refusing is correct,
    # what matters is that it never reaches generation.
    assert "OPEN_QUESTIONS_BLOCK_APPROVAL" in str(raised.value)


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
                "source": "order", "target": "customer",
                "source_field": "id", "target_field": "name",
                "kind": "one-to-many", "required": True,
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

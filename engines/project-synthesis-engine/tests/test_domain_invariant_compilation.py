from __future__ import annotations

import pytest

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import RequestValidationError, SynthesisRequest
from elmos_project_synthesis.production_profile import _schema_sql


def _request(persistence: str) -> SynthesisRequest:
    draft = create_draft(
        name=f"invoice-{persistence}",
        description="Invoice validity boundaries.",
        entities=(
            {
                "singular": "invoice",
                "plural": "invoices",
                "fields": [
                    {"name": "subtotal", "type": "number", "required": True},
                    {"name": "total", "type": "number", "required": True},
                    {"name": "status", "type": "string", "required": True},
                ],
            },
        ),
        business_rules=(
            {
                "id": "BR-TOTAL-001",
                "statement": "Invoice total cannot be less than subtotal.",
                "enforcement": "database",
                "predicate": {
                    "type": "field-reference-comparison",
                    "entity": "invoice",
                    "left_field": "total",
                    "operator": "gte",
                    "right_field": "subtotal",
                },
            },
        ),
        languages=("python",),
        persistence=persistence,
        auth_mode="jwt",
        permissions=tuple(
            {
                "actor": "billing_admin",
                "action": action,
                "resource": "invoice",
                "effect": "allow",
            }
            for action in ("create", "read", "update", "delete")
        ),
    )
    return SynthesisRequest.from_mapping(approve_request(draft, actor="test:invariants"))


@pytest.mark.parametrize("persistence", ["postgresql", "sqlite", "mysql"])
def test_cross_field_invariant_compiles_to_native_database_check(persistence: str) -> None:
    schema = _schema_sql(_request(persistence))
    if persistence == "mysql":
        assert "CONSTRAINT `br-total-001_check` CHECK (`total` >= `subtotal`)" in schema
    else:
        assert 'CONSTRAINT "br-total-001_check" CHECK ("total" >= "subtotal")' in schema


@pytest.mark.parametrize(
    ("predicate", "reason"),
    [
        (
            {
                "type": "field-reference-comparison",
                "entity": "invoice",
                "left_field": "missing",
                "operator": "gte",
                "right_field": "subtotal",
            },
            "BUSINESS_RULE_FIELD_UNKNOWN",
        ),
        (
            {
                "type": "field-reference-comparison",
                "entity": "invoice",
                "left_field": "status",
                "operator": "gte",
                "right_field": "subtotal",
            },
            "BUSINESS_RULE_FIELD_TYPE_MISMATCH",
        ),
    ],
)
def test_invalid_cross_field_invariant_fails_before_generation(
    predicate: dict[str, object], reason: str
) -> None:
    with pytest.raises(RequestValidationError, match=reason):
        SynthesisRequest.from_mapping(
            {
                **_request("postgresql").raw,
                "approval": {"status": "DRAFT"},
                "business_rules": [
                    {
                        "id": "BR-INVALID-001",
                        "statement": "Invalid typed rule.",
                        "enforcement": "database",
                        "predicate": predicate,
                    }
                ],
            },
            require_approval=False,
        )

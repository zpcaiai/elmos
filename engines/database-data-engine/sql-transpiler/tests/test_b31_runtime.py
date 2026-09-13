"""Test suite for all 22 Batch 31 Database and Data Platform skills."""

from __future__ import annotations

import pytest

from elmos_sql_transpiler.b31_skill_runtime import (
    B31_HANDLERS,
    B31_SKILL_SPECS,
    B31_SKILLS_BY_ID,
    execute_b31_skill,
)

_SCOPE = {"tenantId": "tenant-b31", "projectId": "project-b31", "actorId": "actor-b31"}


def test_b31_specs_count() -> None:
    assert len(B31_SKILL_SPECS) == 22
    assert len(B31_HANDLERS) == 22
    assert len(B31_SKILLS_BY_ID) == 22


@pytest.mark.parametrize("spec", B31_SKILL_SPECS, ids=lambda s: s.skill_id)
def test_each_b31_skill_executes_successfully(spec) -> None:
    payload = {
        "scope": dict(_SCOPE),
        "table": "orders",
        "sql": "SELECT id, amount FROM orders WHERE status = 'ACTIVE'",
        "ddl": "CREATE TABLE orders (id BIGINT PRIMARY KEY, amount NUMERIC(12,2))",
        "sourceDialect": "postgresql",
        "targetDialect": "dm8",
        "model": {"tables": ["orders"], "queries": ["select_orders"]},
    }
    result = execute_b31_skill(spec.skill_id, payload)

    assert result["schemaVersion"] == "1.0"
    assert result["skillId"] == spec.skill_id
    assert result["alias"] == f"b31-{spec.skill_id}"
    assert result["handlerId"] == spec.handler_id
    assert result["state"] == "LOCAL_COMPLETED"
    assert result["localCodeStatus"] == "CODE_IMPLEMENTED"
    assert result["verification"]["localHandler"] == "PASSED"
    assert "artifactDigest" in result
    assert "resultDigest" in result
    assert len(result["checks"]) > 0
    assert result["checks"][0]["status"] == "PASSED"


def test_b31_alias_dispatch() -> None:
    payload = {"scope": dict(_SCOPE)}
    res = execute_b31_skill("b31-canonical-database-ir", payload)
    assert res["skillId"] == "canonical-database-ir"
    assert res["verification"]["localHandler"] == "PASSED"


def test_b31_invalid_scope_rejection() -> None:
    with pytest.raises(ValueError, match="scope"):
        execute_b31_skill("canonical-database-ir", {})

    with pytest.raises(ValueError, match="scope"):
        execute_b31_skill("canonical-database-ir", {"scope": {"tenantId": "invalid space"}})


def test_b31_unknown_skill_rejection() -> None:
    with pytest.raises(ValueError, match="Unknown Batch 31 skill"):
        execute_b31_skill("unknown-database-skill", {"scope": dict(_SCOPE)})

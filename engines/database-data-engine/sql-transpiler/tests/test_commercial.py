from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import elmos_sql_transpiler.commercial as commercial
from elmos_sql_transpiler.cli import main
from elmos_sql_transpiler.commercial import assess_commercial, commercial_capabilities
from elmos_sql_transpiler.models import CommercialAssessRequest, ParameterContract
from elmos_sql_transpiler.profiles import capabilities, exact_profiles

_SNAPSHOT_DIGEST = str(commercial_capabilities()["capabilitySnapshotDigest"])


def _request(**changes: object) -> CommercialAssessRequest:
    values: dict[str, object] = {
        "schema_version": "1.0",
        "query_id": "commercial-preflight",
        "source_profile": "oracle-26ai-ee",
        "target_id": "dm8",
        "target_version": "8.1.3.140",
        "target_edition": "enterprise",
        "compatibility_mode": "oracle-compatible-explicit",
        "target_driver": "dm-jdbc-8.1.3.140",
        "target_charset": "UTF-8",
        "target_collation": "BINARY",
        "target_time_zone": "Asia/Shanghai",
        "capability_snapshot_digest": _SNAPSHOT_DIGEST,
        "sql": "SELECT id FROM orders WHERE tenant_id = :tenant_id ORDER BY id",
        "parameters": (
            ParameterContract(
                name="tenant_id",
                logical_type="unicode-text",
                nullable=False,
            ),
        ),
    }
    values.update(changes)
    return CommercialAssessRequest(**values)  # type: ignore[arg-type]


def test_registry_has_thirteen_independent_targets_and_seventy_eight_routes() -> None:
    value = commercial_capabilities()

    assert value["schemaVersion"] == "1.0"
    assert value["package"] == "chinadb-commercial-migration-skills"
    assert value["version"] == "1.0.0"
    assert value["targetCount"] == len(value["targets"]) == 13
    assert value["plannedRouteCount"] == len(value["plannedRoutes"]) == 78
    assert {item["id"] for item in value["excludedTargets"]} == {
        "polardb",
        "polardb-x",
        "tdsql",
    }
    assert not {"polardb", "polardb-x", "tdsql"}.intersection(
        item["id"] for item in value["targets"]
    )
    assert all(item["implementationStatus"] == "LOCAL_ADAPTER" for item in value["targets"])
    assert all(item["state"] == "LOCAL_ADAPTER" for item in value["plannedRoutes"])
    assert all(item["externalExecution"] == "NOT_RUN" for item in value["plannedRoutes"])
    assert all(item["certification"] == "NOT_CERTIFIED" for item in value["plannedRoutes"])
    assert value["implementationStatus"] == "LOCAL_ADAPTER"
    assert value["externalExecution"] == "NOT_RUN"
    assert value["certification"] == "NOT_CERTIFIED"
    assert value["boundaries"]["verifiedTargetRenderers"] == 13
    assert value["boundaries"]["targetSqlMayBeEmitted"] is True


def test_commercial_registry_does_not_add_or_alias_exact_profiles() -> None:
    before = {profile.id: (profile.engine, profile.dialect) for profile in exact_profiles()}
    commercial_capabilities()
    after = {profile.id: (profile.engine, profile.dialect) for profile in exact_profiles()}

    assert after == before
    assert len(after) == 7
    assert not set(after).intersection(item["id"] for item in commercial_capabilities()["targets"])


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["targets"][0].update({"id": "replacement-db"}),
        lambda value: value["plannedRoutes"][0].update({"sourceFamily": "Invented Source"}),
        lambda value: value["plannedRoutes"][0].update({"targetId": "goldendb"}),
    ],
)
def test_registry_rejects_substituted_target_and_route_identities(
    monkeypatch: pytest.MonkeyPatch,
    mutation: Callable[[dict[str, Any]], object],
) -> None:
    value: dict[str, Any] = json.loads(commercial._catalog_text())
    mutation(value)
    monkeypatch.setattr(commercial, "_catalog_text", lambda: json.dumps(value))

    with pytest.raises(RuntimeError, match="exact 13|exact 6 by 13"):
        commercial_capabilities()


def test_main_capabilities_disclose_commercial_extension_summary() -> None:
    value = capabilities()
    summary = value["commercialExtension"]

    assert summary["targetCount"] == 13
    assert summary["plannedRouteCount"] == 78
    assert summary["implementationStatus"] == "LOCAL_ADAPTER"
    assert summary["externalExecution"] == "NOT_RUN"
    assert summary["certification"] == "NOT_CERTIFIED"
    assert len(value["targetAdapters"]) == 7


def test_exact_preflight_emits_local_target_sql_under_explicit_mode() -> None:
    result = assess_commercial(_request())
    rendered = result.to_dict()

    assert result.state == "LOCAL_EMITTED"
    assert result.target_sql is not None
    assert "SELECT" in result.target_sql.upper()
    assert result.source_parse == "PASSED"
    assert result.target_adapter == "PASSED"
    assert result.target_emit == "PASSED"
    assert result.target_reparse == "PASSED"
    assert result.statements[0].kind == "SELECT"
    assert result.statements[0].source_ast
    assert "ORDERING_SEMANTICS" in result.statements[0].obligations
    assert {item.code for item in result.blockers} >= {
        "TARGET_CAPABILITY_SNAPSHOT_NOT_EXTERNALLY_VERIFIED",
    }
    assert all(item.severity != "ERROR" for item in result.blockers)
    assert "PARAMETER_BINDING_CONTRACT" in result.statements[0].obligations
    assert rendered["target"]["version"] == "8.1.3.140"
    assert rendered["target"]["edition"] == "enterprise"
    assert rendered["target"]["compatibilityMode"] == "oracle-compatible-explicit"
    assert rendered["target"]["driver"] == "dm-jdbc-8.1.3.140"
    assert rendered["target"]["charset"] == "UTF-8"
    assert rendered["target"]["collation"] == "BINARY"
    assert rendered["target"]["timeZone"] == "Asia/Shanghai"
    assert rendered["target"]["adapterId"] == "chinadb.dm8.target-adapter.v1"
    assert rendered["target"]["implementationStatus"] == "LOCAL_ADAPTER"
    assert rendered["verification"]["targetAdapter"] == "PASSED"
    assert rendered["verification"]["targetEmit"] == "PASSED"
    assert rendered["verification"]["targetReparse"] == "PASSED"
    assert rendered["verification"]["externalExecution"] == "NOT_RUN"
    assert rendered["certification"] == "NOT_CERTIFIED"


@pytest.mark.parametrize(
    "target_id",
    [
        "dm8",
        "kingbasees",
        "opengauss",
        "tidb",
        "gbase-8s",
        "gbase-8c",
        "gbase-8a",
        "highgo-hgdb",
        "oceanbase-oracle",
        "oceanbase-mysql",
        "gaussdb-oracle",
        "gaussdb-m",
        "goldendb",
    ],
)
def test_every_chinadb_target_emits_under_a_mapped_compatibility_mode(target_id: str) -> None:
    modes = {
        "dm8": "oracle-compatible-explicit",
        "kingbasees": "pg-compatible-explicit",
        "opengauss": "pg-compatible-explicit",
        "tidb": "mysql-compatible-explicit",
        "gbase-8s": "oracle-compatible-explicit",
        "gbase-8c": "pg-compatible-explicit",
        "gbase-8a": "mysql-compatible-explicit",
        "highgo-hgdb": "pg-compatible-explicit",
        "oceanbase-oracle": "oracle-compatible-explicit",
        "oceanbase-mysql": "mysql-compatible-explicit",
        "gaussdb-oracle": "oracle-compatible-explicit",
        "gaussdb-m": "mysql-compatible-explicit",
        "goldendb": "mysql-compatible-explicit",
    }
    result = assess_commercial(_request(target_id=target_id, compatibility_mode=modes[target_id]))
    assert result.state == "LOCAL_EMITTED", result.blockers
    assert result.target_sql is not None
    assert result.certification == "NOT_CERTIFIED"


def test_unmapped_compatibility_mode_stays_blocked() -> None:
    result = assess_commercial(_request(compatibility_mode="native-unspecified-explicit"))
    assert result.state == "BLOCKED"
    assert result.target_sql is None
    assert "COMPATIBILITY_MODE_NOT_MAPPED" in {item.code for item in result.blockers}


def test_source_tokenization_failure_returns_typed_blocked_result() -> None:
    result = assess_commercial(_request(sql="SELECT 'unterminated", parameters=()))

    assert result.state == "BLOCKED"
    assert result.source_parse == "FAILED"
    assert result.statements == ()
    assert result.target_sql is None
    assert [blocker.code for blocker in result.blockers] == ["SOURCE_PARSE_FAILED"]
    assert result.certification == "NOT_CERTIFIED"


@pytest.mark.parametrize("target_id", ["polardb", "polardb-x", "tdsql"])
def test_explicitly_excluded_targets_fail_closed(target_id: str) -> None:
    with pytest.raises(ValueError, match="explicitly excluded"):
        assess_commercial(_request(target_id=target_id))


def test_unknown_target_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown ChinaDB commercial target"):
        assess_commercial(_request(target_id="imaginary-db"))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("target_version", "latest", "exact targetVersion"),
        ("compatibility_mode", "unknown", "compatibilityMode must be a concrete"),
        ("target_driver", "latest", "targetDriver must be a concrete"),
        ("capability_snapshot_digest", "sha256:not-a-digest", "canonical sha256"),
        (
            "capability_snapshot_digest",
            "sha256:" + "0" * 64,
            "must match the current commercial planning registry",
        ),
    ],
)
def test_incomplete_target_tuple_fails_closed(field: str, value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        assess_commercial(_request(**{field: value}))


def test_exact_source_outside_planned_families_remains_blocked() -> None:
    result = assess_commercial(_request(source_profile="sqlite-3.53.3", sql="SELECT 1"))

    assert result.source_parse == "PASSED"
    assert result.target_sql is None
    assert result.route_id == "sqlite-3-53-3--to--dm8"
    assert "COMMERCIAL_ROUTE_NOT_PLANNED" in {item.code for item in result.blockers}


@pytest.mark.parametrize(
    ("parameters", "expected_blocker"),
    [
        ((), "PARAMETER_CONTRACT_MISSING"),
        (
            (ParameterContract(name="other", logical_type="text", nullable=False),),
            "PARAMETER_CONTRACT_NAME_MISMATCH",
        ),
        (
            (
                ParameterContract(name="tenant_id", logical_type="text", nullable=False),
                ParameterContract(name="extra", logical_type="text", nullable=False),
            ),
            "PARAMETER_CONTRACT_ARITY_MISMATCH",
        ),
    ],
)
def test_parameter_contract_drift_is_explicitly_blocked(
    parameters: tuple[ParameterContract, ...], expected_blocker: str
) -> None:
    result = assess_commercial(_request(parameters=parameters))

    assert expected_blocker in {item.code for item in result.blockers}
    assert result.target_sql is None


def test_cli_commercial_assessment_is_create_only_and_returns_blocked(
    tmp_path: Path,
) -> None:
    request = tmp_path / "request.json"
    output = tmp_path / "assessment.json"
    request.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "queryId": "cli-commercial-assessment",
                "sourceProfile": "oracle-26ai-ee",
                "targetId": "dm8",
                "targetVersion": "8.1.3.140",
                "targetEdition": "enterprise",
                "compatibilityMode": "oracle-compatible-explicit",
                "targetDriver": "dm-jdbc-8.1.3.140",
                "targetCharset": "UTF-8",
                "targetCollation": "BINARY",
                "targetTimeZone": "Asia/Shanghai",
                "capabilitySnapshotDigest": _SNAPSHOT_DIGEST,
                "sql": "SELECT 1 FROM dual",
                "parameters": [],
            }
        ),
        encoding="utf-8",
    )

    assert main(["commercial-assess", str(request), "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["state"] == "LOCAL_EMITTED"
    assert main(["commercial-assess", str(request), "--output", str(output)]) == 2


def test_cli_commercial_capabilities_is_create_only(tmp_path: Path) -> None:
    output = tmp_path / "capabilities.json"

    assert main(["commercial-capabilities", "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["plannedRouteCount"] == 78
    assert main(["commercial-capabilities", "--output", str(output)]) == 2


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("parameters"),
        lambda value: value.pop("targetDriver"),
        lambda value: value.update({"unexpected": "field"}),
        lambda value: value.update({"targetVersion": 813140}),
        lambda value: value.update({"parameters": {}}),
        lambda value: value.update(
            {"parameters": [{"name": "tenant", "logicalType": "text", "nullable": "false"}]}
        ),
    ],
)
def test_cli_rejects_missing_unknown_and_coerced_request_fields(
    tmp_path: Path,
    mutation: Callable[[dict[str, object]], object],
) -> None:
    request_value: dict[str, object] = {
        "schemaVersion": "1.0",
        "queryId": "strict-request",
        "sourceProfile": "oracle-26ai-ee",
        "targetId": "dm8",
        "targetVersion": "8.1.3.140",
        "targetEdition": "enterprise",
        "compatibilityMode": "oracle-compatible-explicit",
        "targetDriver": "dm-jdbc-8.1.3.140",
        "targetCharset": "UTF-8",
        "targetCollation": "BINARY",
        "targetTimeZone": "Asia/Shanghai",
        "capabilitySnapshotDigest": _SNAPSHOT_DIGEST,
        "sql": "SELECT 1 FROM dual",
        "parameters": [],
    }
    mutation(request_value)
    request = tmp_path / "request.json"
    output = tmp_path / "assessment.json"
    request.write_text(json.dumps(request_value), encoding="utf-8")

    assert main(["commercial-assess", str(request), "--output", str(output)]) == 2
    assert not output.exists()

"""ChinaDB target accounting tests.

These tests protect the distinction between complete migration accounting and
verified automatic conversion.  A target identity may be present in the
commercial planning registry while its renderer and real execution evidence
are still unavailable.
"""

from __future__ import annotations

import json
from pathlib import Path

from elmos_sql_dialect.chinadb import (
    CHINADB_EXCLUDED_TARGET_IDS,
    CHINADB_PLANNED_ROUTE_COUNT,
    CHINADB_TARGETS,
    chinadb_capabilities,
)
from elmos_sql_dialect.cli import main
from elmos_sql_dialect.models import Dialect
from elmos_sql_dialect.scan import scan_repository


def _repo(tmp_path: Path, text: str) -> Path:
    root = tmp_path / "schema"
    root.mkdir()
    (root / "V1.sql").write_text(text, encoding="utf-8")
    return root


def test_chinadb_registry_has_the_exact_domestic_target_set() -> None:
    capabilities = chinadb_capabilities()
    assert capabilities["targetCount"] == 13
    assert capabilities["plannedRouteCount"] == 78
    assert CHINADB_PLANNED_ROUTE_COUNT == 78
    assert [target.id for target in CHINADB_TARGETS] == [
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
    ]
    assert set(capabilities["excludedTargetIds"]) == set(CHINADB_EXCLUDED_TARGET_IDS)
    assert capabilities["implementationStatus"] == "LOCAL_ADAPTER"
    assert capabilities["externalExecution"] == "NOT_RUN"
    assert capabilities["certification"] == "NOT_CERTIFIED"
    assert capabilities["targetSqlEmission"] == "LOCAL_ONLY_UNDER_EXPLICIT_COMPATIBILITY_MODE"
    for target in capabilities["targets"]:
        assert target["implementationStatus"] == "LOCAL_ADAPTER"
        assert target["externalExecution"] == "NOT_RUN"
        assert target["certification"] == "NOT_CERTIFIED"


def test_every_sql_unit_gets_a_disposition_for_every_chinadb_target(tmp_path: Path) -> None:
    report = scan_repository(
        _repo(
            tmp_path,
            "CREATE TABLE person (id INTEGER PRIMARY KEY);\n"
            "ALTER TABLE person ALTER COLUMN id SET NOT NULL;\n",
        ),
        Dialect.POSTGRES,
    )
    china = report.chinadb_coverage
    assert china["sourceUnits"] == 2
    assert china["routeUnits"] == 2 * len(CHINADB_TARGETS)
    assert china["routeDispositionCovered"] == china["routeUnits"]
    assert china["routeDispositionUnknown"] == 0
    assert china["routeDispositionCoverage"] == 1.0
    assert china["automaticTargetEmissions"] == 0
    assert china["dispositionCounts"]["TARGET_ADAPTER_REVIEW_REQUIRED"] == 1
    assert china["dispositionCounts"]["MANUAL_MIGRATION_REQUIRED"] == 1
    assert len(china["targets"]) == len(CHINADB_TARGETS)
    for target in china["targets"]:
        assert target["routeDispositionCoverage"] == 1.0
        assert target["routeDispositionUnknown"] == 0
        assert target["automaticTargetEmissions"] == 0
        assert target["externalExecution"] == "NOT_RUN"
        assert target["certification"] == "NOT_CERTIFIED"


def test_source_format_review_is_not_counted_as_domestic_auto_conversion(tmp_path: Path) -> None:
    report = scan_repository(_repo(tmp_path, "CREATE TABLE ((("), Dialect.POSTGRES)
    china = report.chinadb_coverage
    assert china["routeDispositionCoverage"] == 1.0
    assert china["automaticTargetEmissions"] == 0
    assert china["dispositionCounts"]["SOURCE_FORMAT_REVIEW"] == 1
    assert china["dispositionCounts"]["TARGET_ADAPTER_REVIEW_REQUIRED"] == 0


def test_cli_exposes_the_same_domestic_registry(tmp_path: Path, capsys) -> None:
    output = tmp_path / "capabilities.json"
    assert main(["chinadb-capabilities", "--output", str(output)]) == 0
    capsys.readouterr()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["targetCount"] == 13
    assert payload["plannedRouteCount"] == 78
    assert payload["externalExecution"] == "NOT_RUN"
    assert payload["certification"] == "NOT_CERTIFIED"
    assert payload["implementationStatus"] == "LOCAL_ADAPTER"
    assert payload["targetSqlEmission"] == "LOCAL_ONLY_UNDER_EXPLICIT_COMPATIBILITY_MODE"


_SIMPLE_POSTGRES_TABLE = "CREATE TABLE person (id INTEGER PRIMARY KEY, name VARCHAR(64) NOT NULL);"


def test_explicit_compatibility_mode_emits_local_ddl_without_claiming_execution() -> None:
    from elmos_sql_dialect.chinadb import translate_chinadb_ddl
    from elmos_sql_dialect.models import RouteError

    report = translate_chinadb_ddl(
        _SIMPLE_POSTGRES_TABLE,
        "postgres",
        "dm8",
        "oracle-compatible-explicit",
    )
    assert report["status"] == "PASSED"
    assert report["state"] == "LOCAL_EMITTED"
    assert report["mappedDialect"] == "oracle"
    assert report["chinadbTargetId"] == "dm8"
    assert report["compatibilityMode"] == "oracle-compatible-explicit"
    assert report["implementationStatus"] == "LOCAL_ADAPTER"
    assert report["externalExecution"] == "NOT_RUN"
    assert report["certification"] == "NOT_CERTIFIED"
    assert report["emitted"]
    assert "PERSON" in report["emitted"].upper() or "person" in report["emitted"].lower()

    blocked = translate_chinadb_ddl(
        _SIMPLE_POSTGRES_TABLE,
        "postgres",
        "dm8",
        "pg-compatible-explicit",
    )
    assert blocked["status"] == "BLOCKED"
    assert blocked["reasonCode"] == "COMPATIBILITY_MODE_NOT_MAPPED"
    assert blocked["emitted"] is None
    assert blocked["externalExecution"] == "NOT_RUN"

    try:
        translate_chinadb_ddl(_SIMPLE_POSTGRES_TABLE, "postgres", "dm8", "")
        raise AssertionError("empty compatibility mode must fail closed")
    except RouteError as exc:
        assert "CHINADB_COMPATIBILITY_MODE_REQUIRED" in str(exc)


def test_cli_chinadb_translate_writes_local_emitted_sql(tmp_path: Path, capsys) -> None:
    source = tmp_path / "person.sql"
    source.write_text(_SIMPLE_POSTGRES_TABLE, encoding="utf-8")
    output = tmp_path / "out"
    assert (
        main(
            [
                "translate",
                "--source-file",
                str(source),
                "--source-dialect",
                "postgres",
                "--chinadb-target",
                "tidb",
                "--compatibility-mode",
                "mysql-compatible-explicit",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    capsys.readouterr()
    report = json.loads((output / "translation-report.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASSED"
    assert report["state"] == "LOCAL_EMITTED"
    assert report["mappedDialect"] == "mysql"
    assert report["externalExecution"] == "NOT_RUN"
    assert (output / "emitted.sql").read_text(encoding="utf-8").strip()

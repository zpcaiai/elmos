from __future__ import annotations

import json
import re
from hashlib import sha256
from importlib.resources import files
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError, TokenError

from .adapters import target_adapter_by_id
from .models import (
    CommercialAssessmentResult,
    CommercialAssessRequest,
    CommercialBlocker,
    CommercialStatement,
    EvidenceState,
)
from .profiles import profile_by_id
from .transpiler import _obligations, _parameter_nodes, _require_pinned_parser

_MAX_SQL_BYTES = 256 * 1024
_MAX_PARAMETERS = 256
_MAX_STATEMENTS = 256
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXACT_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+~-]*$")
_EXACT_CONTEXT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:/~-]*$")
_EXPECTED_TARGET_COUNT = 13
_EXPECTED_ROUTE_COUNT = 78
_EXPECTED_EXCLUSIONS = frozenset({"polardb", "polardb-x", "tdsql"})
_EXPECTED_TARGET_IDS = frozenset(
    {
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
    }
)
_EXPECTED_SOURCE_SLUGS = {
    "Oracle": "oracle",
    "SQL Server": "sql-server",
    "PostgreSQL": "postgresql",
    "MySQL/MariaDB": "mysql-mariadb",
    "DB2 LUW": "db2-luw",
    "Sybase ASE": "sybase-ase",
}
_SOURCE_FAMILY_BY_PROFILE = {
    "postgresql-17.5": "PostgreSQL",
    "postgresql-18.4": "PostgreSQL",
    "mysql-8.4.10-lts": "MySQL/MariaDB",
    "sqlserver-2022-cu26": "SQL Server",
    "oracle-26ai-ee": "Oracle",
}


def _digest_text(value: str) -> str:
    return f"sha256:{sha256(value.encode('utf-8')).hexdigest()}"


def _catalog_text() -> str:
    return files("elmos_sql_transpiler").joinpath(
        "data/chinadb-commercial-v1.json"
    ).read_text(encoding="utf-8")


def _object_list(value: object, *, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RuntimeError(f"commercial registry {name} must be an array")
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise RuntimeError(f"commercial registry {name} items must be objects")
        result.append({str(key): child for key, child in item.items()})
    return result


def _catalog() -> dict[str, Any]:
    loaded: object = json.loads(_catalog_text())
    if not isinstance(loaded, dict):
        raise RuntimeError("ChinaDB commercial registry must be an object")
    catalog = {str(key): value for key, value in loaded.items()}
    if (
        catalog.get("schemaVersion") != "1.0"
        or catalog.get("package") != "chinadb-commercial-migration-skills"
        or catalog.get("version") != "1.0.0"
    ):
        raise RuntimeError("ChinaDB commercial registry identity is invalid")
    if (
        catalog.get("implementationStatus") != "SPEC_ONLY"
        or catalog.get("externalExecution") != "NOT_RUN"
        or catalog.get("certification") != "NOT_CERTIFIED"
    ):
        raise RuntimeError("commercial registry cannot manufacture implementation evidence")

    targets = _object_list(catalog.get("targets"), name="targets")
    routes = _object_list(catalog.get("plannedRoutes"), name="plannedRoutes")
    exclusions = _object_list(catalog.get("excludedTargets"), name="excludedTargets")
    target_ids = [str(target.get("id")) for target in targets]
    route_ids = [str(route.get("id")) for route in routes]
    exclusion_ids = {str(target.get("id")) for target in exclusions}
    if (
        len(targets) != _EXPECTED_TARGET_COUNT
        or len(set(target_ids)) != len(target_ids)
        or set(target_ids) != _EXPECTED_TARGET_IDS
    ):
        raise RuntimeError("commercial registry must contain the exact 13 target identities")
    if len(routes) != _EXPECTED_ROUTE_COUNT or len(set(route_ids)) != len(route_ids):
        raise RuntimeError("commercial registry must contain 78 unique planned routes")
    if exclusion_ids != _EXPECTED_EXCLUSIONS:
        raise RuntimeError("commercial registry exclusions have drifted")
    if _EXPECTED_EXCLUSIONS.intersection(target_ids):
        raise RuntimeError("an excluded database appears in the commercial target registry")

    for target in targets:
        if (
            target.get("implementationStatus") != "SPEC_ONLY"
            or target.get("externalExecution") != "NOT_RUN"
            or target.get("certification") != "NOT_CERTIFIED"
        ):
            raise RuntimeError("commercial target state must remain fail-closed")
        expected_adapter_id = f"chinadb.{target['id']}.target-adapter.v1"
        if target.get("adapterId") != expected_adapter_id:
            raise RuntimeError("commercial target must declare its independent adapter id")
    expected_route_tuples = {
        (f"{source_slug}--to--{target_id}", source_family, target_id)
        for source_family, source_slug in _EXPECTED_SOURCE_SLUGS.items()
        for target_id in _EXPECTED_TARGET_IDS
    }
    observed_route_tuples = {
        (str(route.get("id")), str(route.get("sourceFamily")), str(route.get("targetId")))
        for route in routes
    }
    if observed_route_tuples != expected_route_tuples:
        raise RuntimeError("commercial registry must contain the exact 6 by 13 route matrix")
    for route in routes:
        if (
            route.get("state") != "SPEC_ONLY"
            or route.get("externalExecution") != "NOT_RUN"
            or route.get("certification") != "NOT_CERTIFIED"
            or route.get("priority") not in {"T1", "T2", "ANALYTICAL"}
        ):
            raise RuntimeError("commercial planned route state must remain fail-closed")
    return catalog


def commercial_capabilities() -> dict[str, Any]:
    catalog = _catalog()
    copied: object = json.loads(json.dumps(catalog, ensure_ascii=False))
    if not isinstance(copied, dict):
        raise RuntimeError("commercial capability registry copy failed")
    result = {str(key): value for key, value in copied.items()}
    result["capabilitySnapshotDigest"] = _digest_text(_catalog_text())
    result["targetCount"] = _EXPECTED_TARGET_COUNT
    result["plannedRouteCount"] = _EXPECTED_ROUTE_COUNT
    result["boundaries"] = {
        "exactCommercialTargetProfilesRegistered": False,
        "verifiedTargetRenderers": 0,
        "productionDatabaseAccess": False,
        "targetSqlMayBeEmitted": False,
        "claim": (
            "Static commercial planning registry and source-side typed preflight only; "
            "no ChinaDB target renderer, target execution, equivalence, or certification evidence."
        ),
    }
    return result


def commercial_summary() -> dict[str, Any]:
    value = commercial_capabilities()
    exclusions = _object_list(value["excludedTargets"], name="excludedTargets")
    return {
        "schemaVersion": value["schemaVersion"],
        "package": value["package"],
        "version": value["version"],
        "targetCount": value["targetCount"],
        "plannedRouteCount": value["plannedRouteCount"],
        "excludedTargetIds": [str(item["id"]) for item in exclusions],
        "implementationStatus": value["implementationStatus"],
        "externalExecution": value["externalExecution"],
        "certification": value["certification"],
        "capabilitySnapshotDigest": value["capabilitySnapshotDigest"],
    }


def _target(target_id: str) -> dict[str, Any]:
    catalog = _catalog()
    exclusions = _object_list(catalog["excludedTargets"], name="excludedTargets")
    if target_id in {str(item["id"]) for item in exclusions}:
        raise ValueError(f"ChinaDB commercial target is explicitly excluded: {target_id}")
    targets = _object_list(catalog["targets"], name="targets")
    matches = [target for target in targets if target.get("id") == target_id]
    if len(matches) != 1:
        raise ValueError(f"unknown ChinaDB commercial target id: {target_id}")
    return matches[0]


def _is_floating(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        not normalized
        or normalized in {"latest", "current", "unknown", "unspecified", "*", "x"}
        or normalized.endswith(".*")
        or normalized.endswith(".x")
    )


def _require_exact_context(name: str, value: str) -> None:
    if (
        _is_floating(value)
        or len(value) > 128
        or _EXACT_CONTEXT_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(
            f"{name} must be a concrete non-floating token of at most 128 characters"
        )


def _validate_request(request: CommercialAssessRequest) -> dict[str, Any]:
    string_values = (
        request.schema_version,
        request.query_id,
        request.source_profile,
        request.target_id,
        request.target_version,
        request.target_edition,
        request.compatibility_mode,
        request.target_driver,
        request.target_charset,
        request.target_collation,
        request.target_time_zone,
        request.capability_snapshot_digest,
        request.sql,
    )
    if any(not isinstance(value, str) for value in string_values):
        raise TypeError("commercial assessment scalar fields must be strings")
    if request.schema_version != "1.0":
        raise ValueError("commercial assessment schemaVersion must be 1.0")
    if not request.query_id or len(request.query_id) > 160:
        raise ValueError("query id is required and must be at most 160 characters")
    source = profile_by_id(request.source_profile)
    target = _target(request.target_id)
    if _is_floating(request.target_version):
        raise ValueError("an exact targetVersion is required; floating versions are prohibited")
    if (
        len(request.target_version) > 128
        or _EXACT_VERSION_PATTERN.fullmatch(request.target_version) is None
    ):
        raise ValueError("targetVersion must be a concrete version token of at most 128 characters")
    for name, value in (
        ("targetEdition", request.target_edition),
        ("compatibilityMode", request.compatibility_mode),
        ("targetDriver", request.target_driver),
        ("targetCharset", request.target_charset),
        ("targetCollation", request.target_collation),
        ("targetTimeZone", request.target_time_zone),
    ):
        _require_exact_context(name, value)
    if not _DIGEST_PATTERN.fullmatch(request.capability_snapshot_digest):
        raise ValueError("capabilitySnapshotDigest must be a canonical sha256 digest")
    current_snapshot = str(commercial_capabilities()["capabilitySnapshotDigest"])
    if request.capability_snapshot_digest != current_snapshot:
        raise ValueError(
            "capabilitySnapshotDigest must match the current commercial planning registry"
        )
    if not request.sql.strip():
        raise ValueError("SQL input is required")
    if len(request.sql.encode("utf-8")) > _MAX_SQL_BYTES:
        raise ValueError("SQL input exceeds the 256 KiB UTF-8 safety limit")
    if "\x00" in request.sql:
        raise ValueError("SQL input contains a prohibited NUL byte")
    names = [parameter.name for parameter in request.parameters]
    if len(request.parameters) > _MAX_PARAMETERS:
        raise ValueError("parameter contract exceeds the 256 item limit")
    if any(
        not isinstance(parameter.name, str)
        or not isinstance(parameter.logical_type, str)
        or not isinstance(parameter.nullable, bool)
        for parameter in request.parameters
    ):
        raise TypeError("parameter contract fields have invalid types")
    if len(names) != len(set(names)):
        raise ValueError("parameter contract names must be unique")
    if any(not parameter.name or not parameter.logical_type for parameter in request.parameters):
        raise ValueError("parameter contract names and logical types must be non-empty")
    if any(
        len(parameter.name) > 128 or len(parameter.logical_type) > 128
        for parameter in request.parameters
    ):
        raise ValueError(
            "parameter contract names and logical types must be at most 128 characters"
        )
    if source.dialect == "":
        raise RuntimeError("exact source profile has no parser dialect")
    return target


def _route_id(source_profile: str, target_id: str) -> tuple[str, bool]:
    source_family = _SOURCE_FAMILY_BY_PROFILE.get(source_profile)
    if source_family is None:
        source_slug = re.sub(r"[^a-z0-9-]+", "-", source_profile.lower()).strip("-")
        return f"{source_slug}--to--{target_id}", False
    routes = _object_list(_catalog()["plannedRoutes"], name="plannedRoutes")
    matches = [
        route
        for route in routes
        if route.get("sourceFamily") == source_family and route.get("targetId") == target_id
    ]
    if len(matches) != 1:
        raise RuntimeError("commercial planned route registry is incomplete")
    return str(matches[0]["id"]), True


def _result(
    request: CommercialAssessRequest,
    target: dict[str, Any],
    *,
    route_id: str,
    statements: tuple[CommercialStatement, ...],
    blockers: tuple[CommercialBlocker, ...],
    source_parse: EvidenceState,
) -> CommercialAssessmentResult:
    return CommercialAssessmentResult(
        schema_version="1.0",
        query_id=request.query_id,
        source_profile=request.source_profile,
        target={
            "id": target["id"],
            "label": target["label"],
            "version": request.target_version,
            "edition": request.target_edition,
            "compatibilityMode": request.compatibility_mode,
            "driver": request.target_driver,
            "charset": request.target_charset,
            "collation": request.target_collation,
            "timeZone": request.target_time_zone,
            "adapterId": target["adapterId"],
            "implementationStatus": target["implementationStatus"],
        },
        route_id=route_id,
        state="BLOCKED",
        source_digest=_digest_text(request.sql),
        capability_snapshot_digest=request.capability_snapshot_digest,
        statements=statements,
        blockers=blockers,
        source_parse=source_parse,
    )


def assess_commercial(
    request: CommercialAssessRequest,
    *,
    max_statements: int = _MAX_STATEMENTS,
) -> CommercialAssessmentResult:
    """Parse an exact source profile and fail closed before ChinaDB emission.

    The request binds a concrete target tuple and the current static planning
    registry digest. No target adapter is registered by this specification-only
    extension, so even a fully formed request cannot produce target SQL.
    """

    if max_statements < 1 or max_statements > _MAX_STATEMENTS:
        raise ValueError("commercial assessment statement limit is invalid")
    _require_pinned_parser()
    target = _validate_request(request)
    source = profile_by_id(request.source_profile)
    route_id, route_planned = _route_id(request.source_profile, request.target_id)
    try:
        parsed = sqlglot.parse(
            request.sql,
            read=source.dialect,
            error_level=ErrorLevel.RAISE,
        )
    except (ParseError, TokenError):
        return _result(
            request,
            target,
            route_id=route_id,
            statements=(),
            blockers=(
                CommercialBlocker(
                    code="SOURCE_PARSE_FAILED",
                    severity="ERROR",
                    statement_index=None,
                    message="The exact source profile parser rejected the SQL.",
                ),
            ),
            source_parse="FAILED",
        )
    except Exception as error:  # noqa: BLE001 - deliberate fail-closed backstop
        # Same discipline as transpiler.transpile: anything the pinned parser
        # raises that is not a declared parse rejection is a DEFECT, and it gets
        # its own code so it can never be counted as a source-side boundary.
        # Only the exception type is recorded -- a message could carry fragments
        # of the customer's SQL.
        return _result(
            request,
            target,
            route_id=route_id,
            statements=(),
            blockers=(
                CommercialBlocker(
                    code="SOURCE_PARSE_FAULTED",
                    severity="ERROR",
                    statement_index=None,
                    message=(
                        f"The exact source profile parser raised an unexpected "
                        f"{type(error).__name__} and was failed closed. This is a defect, "
                        "not a declared boundary; please report it."
                    ),
                ),
            ),
            source_parse="FAILED",
        )

    source_statements = [statement for statement in parsed if isinstance(statement, exp.Expression)]
    if not source_statements or len(source_statements) != len(parsed):
        return _result(
            request,
            target,
            route_id=route_id,
            statements=(),
            blockers=(
                CommercialBlocker(
                    code="SOURCE_EMPTY_OR_INCOMPLETE_AST",
                    severity="ERROR",
                    statement_index=None,
                    message="The source parser did not produce a complete typed statement set.",
                ),
            ),
            source_parse="FAILED",
        )
    if len(source_statements) > max_statements:
        return _result(
            request,
            target,
            route_id=route_id,
            statements=(),
            blockers=(
                CommercialBlocker(
                    code="SOURCE_STATEMENT_LIMIT_EXCEEDED",
                    severity="ERROR",
                    statement_index=None,
                    message="The source exceeds the configured statement safety limit.",
                ),
            ),
            source_parse="FAILED",
        )

    statements: list[CommercialStatement] = []
    blockers: list[CommercialBlocker] = []
    observed_parameter_tokens: list[str] = []
    first_opaque_statement: int | None = None
    for index, statement in enumerate(source_statements):
        obligations = set(_obligations(statement))
        if not obligations:
            obligations.add("TARGET_SEMANTICS_REVIEW_REQUIRED")
        if isinstance(statement, exp.Command):
            obligations.add("OPAQUE_COMMAND_SEMANTICS")
            if first_opaque_statement is None:
                first_opaque_statement = index
        parameter_tokens = _parameter_nodes(statement, source.dialect)
        observed_parameter_tokens.extend(parameter_tokens)
        if parameter_tokens:
            obligations.add("PARAMETER_BINDING_CONTRACT")
        statements.append(
            CommercialStatement(
                index=index,
                kind=statement.key.upper(),
                source_ast=statement.dump(),
                obligations=tuple(sorted(obligations)),
            )
        )

    if first_opaque_statement is not None:
        blockers.append(
            CommercialBlocker(
                code="OPAQUE_SOURCE_COMMAND",
                severity="ERROR",
                statement_index=first_opaque_statement,
                message="Opaque source commands cannot enter a commercial conversion route.",
            )
        )

    if source.dialect in {"oracle", "tsql", "postgres"}:
        observed_bindings = set(observed_parameter_tokens)
    else:
        observed_bindings = {
            f"#{index}" for index, _ in enumerate(observed_parameter_tokens, start=1)
        }
    if request.parameters and not observed_bindings:
        blockers.append(
            CommercialBlocker(
                code="PARAMETER_CONTRACT_NOT_OBSERVED",
                severity="ERROR",
                statement_index=None,
                message="A parameter contract was supplied but no typed parameter node was parsed.",
            )
        )
    elif not request.parameters and observed_bindings:
        blockers.append(
            CommercialBlocker(
                code="PARAMETER_CONTRACT_MISSING",
                severity="ERROR",
                statement_index=None,
                message="Typed parameter nodes were parsed but no parameter contract was supplied.",
            )
        )
    elif len(request.parameters) != len(observed_bindings):
        blockers.append(
            CommercialBlocker(
                code="PARAMETER_CONTRACT_ARITY_MISMATCH",
                severity="ERROR",
                statement_index=None,
                message="The parameter contract arity does not match the typed source bindings.",
            )
        )
    elif source.dialect in {"oracle", "tsql"}:
        observed_names = {token.lstrip(":@") for token in observed_bindings}
        contract_names = {parameter.name for parameter in request.parameters}
        if observed_names != contract_names:
            blockers.append(
                CommercialBlocker(
                    code="PARAMETER_CONTRACT_NAME_MISMATCH",
                    severity="ERROR",
                    statement_index=None,
                    message=(
                        "The named parameter contract does not match the typed source bindings."
                    ),
                )
            )
    if not route_planned:
        blockers.append(
            CommercialBlocker(
                code="COMMERCIAL_ROUTE_NOT_PLANNED",
                severity="ERROR",
                statement_index=None,
                message=(
                    "The exact source profile is not represented by a planned "
                    "commercial source family."
                ),
            )
        )
    blockers.append(
        CommercialBlocker(
            code="TARGET_CAPABILITY_SNAPSHOT_NOT_EXTERNALLY_VERIFIED",
            severity="ERROR",
            statement_index=None,
            message=(
                "The request matches the static commercial planning registry, but no "
                "independently collected target capability snapshot was supplied or executed."
            ),
        )
    )
    adapter = target_adapter_by_id(str(target["adapterId"]))
    if adapter is None:
        blockers.append(
            CommercialBlocker(
                code="VERIFIED_TARGET_RENDERER_UNAVAILABLE",
                severity="ERROR",
                statement_index=None,
                message=(
                    "No verified renderer implements the independent commercial target adapter; "
                    "target SQL emission is prohibited."
                ),
            )
        )
    else:
        blockers.append(
            CommercialBlocker(
                code="COMMERCIAL_TARGET_PROFILE_SPEC_ONLY",
                severity="ERROR",
                statement_index=None,
                message=(
                    "An adapter identity exists, but this target has no registered exact profile "
                    "or external evidence and remains specification-only."
                ),
            )
        )
    return _result(
        request,
        target,
        route_id=route_id,
        statements=tuple(statements),
        blockers=tuple(blockers),
        source_parse="PASSED",
    )

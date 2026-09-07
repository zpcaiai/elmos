from __future__ import annotations

import json
from dataclasses import dataclass
from typing import NoReturn

from .models import CommercialAssessRequest, ParameterContract

_REQUIRED_FIELDS = frozenset(
    {
        "schemaVersion",
        "queryId",
        "sourceProfile",
        "targetId",
        "targetVersion",
        "targetEdition",
        "compatibilityMode",
        "targetDriver",
        "targetCharset",
        "targetCollation",
        "targetTimeZone",
        "capabilitySnapshotDigest",
        "sql",
        "parameters",
    }
)
_PARAMETER_FIELDS = frozenset({"name", "logicalType", "nullable"})


@dataclass(frozen=True)
class CommercialRequestLimits:
    max_envelope_bytes: int
    max_sql_bytes: int
    max_parameters: int

    def __post_init__(self) -> None:
        if (
            self.max_envelope_bytes < 2
            or self.max_sql_bytes < 1
            or self.max_parameters < 0
        ):
            raise ValueError("commercial request limits must be positive")


CLI_REQUEST_LIMITS = CommercialRequestLimits(
    max_envelope_bytes=1_310_720,
    max_sql_bytes=256 * 1024,
    max_parameters=256,
)


class CommercialRequestError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _reject_non_finite(_: str) -> NoReturn:
    raise CommercialRequestError(
        "COMMERCIAL_REQUEST_NON_FINITE_JSON",
        "commercial assessment request contains a non-finite JSON number",
    )


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CommercialRequestError(
                "COMMERCIAL_REQUEST_DUPLICATE_FIELD",
                "commercial assessment request contains a duplicate JSON field",
            )
        result[key] = value
    return result


def _decode_json(payload: bytes, limits: CommercialRequestLimits) -> object:
    if not payload:
        raise CommercialRequestError(
            "COMMERCIAL_REQUEST_EMPTY",
            "commercial assessment request must not be empty",
        )
    if len(payload) > limits.max_envelope_bytes:
        raise CommercialRequestError(
            "COMMERCIAL_REQUEST_ENVELOPE_TOO_LARGE",
            "commercial assessment request exceeds the configured envelope limit",
        )
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise CommercialRequestError(
            "COMMERCIAL_REQUEST_UTF8_REQUIRED",
            "commercial assessment request must be valid UTF-8",
        ) from error
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_non_finite,
        )
    except CommercialRequestError:
        raise
    except (json.JSONDecodeError, RecursionError) as error:
        raise CommercialRequestError(
            "COMMERCIAL_REQUEST_JSON_INVALID",
            "commercial assessment request must be valid bounded JSON",
        ) from error


def parse_commercial_request_json(
    payload: bytes,
    *,
    limits: CommercialRequestLimits = CLI_REQUEST_LIMITS,
) -> CommercialAssessRequest:
    raw = _decode_json(payload, limits)
    if not isinstance(raw, dict):
        raise CommercialRequestError(
            "COMMERCIAL_REQUEST_OBJECT_REQUIRED",
            "commercial assessment request must be a JSON object",
        )

    fields = set(raw)
    missing = _REQUIRED_FIELDS - fields
    unknown = fields - _REQUIRED_FIELDS
    if missing:
        raise CommercialRequestError(
            "COMMERCIAL_REQUEST_FIELDS_MISSING",
            "commercial assessment request has missing required fields",
        )
    if unknown:
        raise CommercialRequestError(
            "COMMERCIAL_REQUEST_FIELDS_UNKNOWN",
            "commercial assessment request has unknown fields",
        )

    string_fields = _REQUIRED_FIELDS - {"parameters"}
    if any(type(raw[field]) is not str for field in string_fields):
        raise CommercialRequestError(
            "COMMERCIAL_REQUEST_STRING_REQUIRED",
            "commercial assessment request scalar fields must be strings",
        )

    sql = raw["sql"]
    if not isinstance(sql, str):
        raise AssertionError("strict string validation did not narrow SQL")
    try:
        sql_bytes = sql.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise CommercialRequestError(
            "COMMERCIAL_REQUEST_UTF8_REQUIRED",
            "commercial assessment SQL must contain valid Unicode text",
        ) from error
    if len(sql_bytes) > limits.max_sql_bytes:
        raise CommercialRequestError(
            "COMMERCIAL_REQUEST_SQL_TOO_LARGE",
            "commercial assessment SQL exceeds the configured UTF-8 byte limit",
        )

    parameter_values = raw["parameters"]
    if type(parameter_values) is not list:
        raise CommercialRequestError(
            "COMMERCIAL_REQUEST_PARAMETERS_ARRAY_REQUIRED",
            "commercial assessment parameters must be an array",
        )
    if len(parameter_values) > limits.max_parameters:
        raise CommercialRequestError(
            "COMMERCIAL_REQUEST_PARAMETERS_TOO_LARGE",
            "commercial assessment parameter count exceeds the configured limit",
        )

    parameters: list[ParameterContract] = []
    for item in parameter_values:
        if type(item) is not dict:
            raise CommercialRequestError(
                "COMMERCIAL_REQUEST_PARAMETER_OBJECT_REQUIRED",
                "commercial assessment parameters must be objects",
            )
        if set(item) != _PARAMETER_FIELDS:
            raise CommercialRequestError(
                "COMMERCIAL_REQUEST_PARAMETER_FIELDS_INVALID",
                "commercial assessment parameter fields are incomplete or unknown",
            )
        if type(item["name"]) is not str or type(item["logicalType"]) is not str:
            raise CommercialRequestError(
                "COMMERCIAL_REQUEST_PARAMETER_STRING_REQUIRED",
                "commercial assessment parameter names and logical types must be strings",
            )
        if type(item["nullable"]) is not bool:
            raise CommercialRequestError(
                "COMMERCIAL_REQUEST_PARAMETER_BOOLEAN_REQUIRED",
                "commercial assessment parameter nullable values must be booleans",
            )
        parameters.append(
            ParameterContract(
                name=item["name"],
                logical_type=item["logicalType"],
                nullable=item["nullable"],
            )
        )

    return CommercialAssessRequest(
        schema_version=raw["schemaVersion"],
        query_id=raw["queryId"],
        source_profile=raw["sourceProfile"],
        target_id=raw["targetId"],
        target_version=raw["targetVersion"],
        target_edition=raw["targetEdition"],
        compatibility_mode=raw["compatibilityMode"],
        target_driver=raw["targetDriver"],
        target_charset=raw["targetCharset"],
        target_collation=raw["targetCollation"],
        target_time_zone=raw["targetTimeZone"],
        capability_snapshot_digest=raw["capabilitySnapshotDigest"],
        sql=sql,
        parameters=tuple(parameters),
    )

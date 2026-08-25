"""Tenant-scoped durable Skill24 evaluation and raw evidence persistence.

Only evaluator identities in :data:`LOCAL_EVALUATORS` are executable.  Dataset
and rubric documents come from the trusted host context and are bound by exact
digests; repository or uploaded content can never select a command, module, or
callable.  Caller-supplied status, score, byte count, and evidence metadata are
ignored by design: this module derives them from the stored bytes.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import os
import re
import sqlite3
import stat
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from .acceptance_catalog import (
    ACCEPTANCE_CATALOG_DIGEST,
    ACCEPTANCE_TO_SKILL,
    external_acceptance_status,
)
from .canonical import (
    canonical_digest,
    canonical_json,
    normalize_sha256,
    require_actor_id,
    require_idempotency_key,
    require_resource_id,
    sha256_bytes,
    utc_now,
)
from .errors import AuthorizationError, ConflictError, IntegrityError, NotFoundError, ValidationError
from .skill_runtime import RuntimeContext


EVALUATION_SKILL: Final = "elmos-multimodal-evaluation-framework"
_CATEGORIES: Final = frozenset({"positive", "boundary", "failure", "security"})
_EXECUTION_SCOPES: Final = frozenset({"LOCAL", "EXTERNAL"})
_FIXTURE_ROLES: Final = frozenset(
    {"development", "negative", "holdout", "representative-workload"}
)
_MAX_CASES: Final = 2_000
_MAX_ARTIFACT_BYTES: Final = 1024 * 1024
_MAX_TOTAL_ARTIFACT_BYTES: Final = 8 * 1024 * 1024
_MAX_BASE64_BYTES: Final = ((_MAX_ARTIFACT_BYTES + 2) // 3) * 4
_SAFE_MEDIA_TYPE: Final = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+\-/]{0,126}$")
_RUN_TERMINAL: Final = frozenset({"EVALUATED", "VERIFIED"})
_EVALUATION_SCHEMA_COLUMNS: Final[Mapping[str, frozenset[str]]] = {
    "evaluation_manifests": frozenset(
        {
            "tenant_id", "project_id", "dataset_id", "dataset_version", "dataset_digest",
            "rubric_id", "rubric_version", "rubric_digest", "profile_version",
            "authorization_id", "dataset_json", "rubric_json", "created_at",
        }
    ),
    "evaluation_artifacts": frozenset(
        {
            "tenant_id", "project_id", "artifact_digest", "byte_count", "media_type",
            "storage_key", "created_at",
        }
    ),
    "evaluation_runs": frozenset(
        {
            "tenant_id", "project_id", "run_id", "idempotency_key", "request_digest",
            "dataset_id", "dataset_version", "dataset_digest", "rubric_id", "rubric_version",
            "rubric_digest", "subject_json", "subject_digest", "executor_id", "state",
            "decision", "report_json", "report_digest", "created_at", "completed_at",
        }
    ),
    "evaluation_results": frozenset(
        {
            "tenant_id", "project_id", "run_id", "case_id", "acceptance_id", "skill",
            "category", "execution_scope", "evaluator_id", "case_digest", "artifact_digest",
            "artifact_byte_count", "status", "code", "result_json", "result_digest",
        }
    ),
    "evaluation_verifications": frozenset(
        {
            "tenant_id", "project_id", "run_id", "verifier_id", "idempotency_key",
            "request_digest", "verification_json", "verification_digest", "verified_at",
        }
    ),
}


def _sequence(value: Any, field: str, *, maximum: int = _MAX_CASES) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValidationError("EVALUATION_SCHEMA_INVALID", f"{field} must be an array")
    if len(value) > maximum:
        raise ValidationError("EVALUATION_LIMIT_EXCEEDED", f"{field} exceeds its item limit")
    return list(value)


def _bounded_string(value: Any, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValidationError("EVALUATION_SCHEMA_INVALID", f"{field} must be an exact non-blank string")
    if len(value.encode("utf-8")) > maximum:
        raise ValidationError("EVALUATION_LIMIT_EXCEEDED", f"{field} exceeds its byte limit")
    return value


def _canonical_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("EVALUATION_SCHEMA_INVALID", f"{field} must be an object")
    normalized = json.loads(canonical_json(value))
    if not isinstance(normalized, dict):
        raise ValidationError("EVALUATION_SCHEMA_INVALID", f"{field} must be an object")
    return normalized


def _normalized_digest(value: Any, field: str) -> str:
    try:
        return normalize_sha256(_bounded_string(value, field, maximum=71))
    except ValidationError as error:
        raise ValidationError("EVALUATION_DIGEST_INVALID", f"{field} must be SHA-256") from error


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValidationError("EVALUATION_SCHEMA_INVALID", f"{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValidationError("EVALUATION_SCHEMA_INVALID", f"{field} must be a finite number") from error
    if not math.isfinite(number):
        raise ValidationError("EVALUATION_SCHEMA_INVALID", f"{field} must be a finite number")
    return number


def _strict_json_bytes(raw: bytes) -> Any:
    def duplicate_safe(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def non_finite(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=duplicate_safe,
        parse_constant=non_finite,
    )


def _result(status: str, code: str, observation: Any, expected: Any) -> dict[str, Any]:
    return {
        "status": status,
        "code": code,
        "observation_digest": canonical_digest(observation),
        "expected_digest": canonical_digest(expected),
    }


def _evaluate_bytes_digest(raw: bytes, config: Mapping[str, Any]) -> dict[str, Any]:
    if set(config) != {"expected_sha256"}:
        raise ValidationError("EVALUATION_RUBRIC_INVALID")
    expected = _normalized_digest(config.get("expected_sha256"), "expected_sha256")
    observed = sha256_bytes(raw)
    return _result(
        "PASS" if observed == expected else "FAIL",
        "BYTES_DIGEST_MATCH" if observed == expected else "BYTES_DIGEST_MISMATCH",
        {"sha256": observed, "byte_count": len(raw)},
        {"sha256": expected},
    )


def _evaluate_canonical_json(raw: bytes, config: Mapping[str, Any]) -> dict[str, Any]:
    if set(config) != {"expected"}:
        raise ValidationError("EVALUATION_RUBRIC_INVALID")
    expected = config["expected"]
    try:
        observed = _strict_json_bytes(raw)
        observed_canonical = json.loads(canonical_json(observed))
        expected_canonical = json.loads(canonical_json(expected))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, ValidationError):
        return _result("FAIL", "CANONICAL_JSON_INVALID", {"valid_json": False}, expected)
    equal = observed_canonical == expected_canonical
    return _result(
        "PASS" if equal else "FAIL",
        "CANONICAL_JSON_MATCH" if equal else "CANONICAL_JSON_MISMATCH",
        observed_canonical,
        expected_canonical,
    )


def _evaluate_utf8_text(raw: bytes, config: Mapping[str, Any]) -> dict[str, Any]:
    if set(config) != {"expected"} or not isinstance(config.get("expected"), str):
        raise ValidationError("EVALUATION_RUBRIC_INVALID")
    try:
        observed = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _result("FAIL", "UTF8_TEXT_INVALID", {"valid_utf8": False}, config["expected"])
    equal = observed == config["expected"]
    return _result(
        "PASS" if equal else "FAIL",
        "UTF8_TEXT_MATCH" if equal else "UTF8_TEXT_MISMATCH",
        observed,
        config["expected"],
    )


def _evaluate_forbidden_text(raw: bytes, config: Mapping[str, Any]) -> dict[str, Any]:
    if set(config) != {"forbidden", "case_sensitive"} or not isinstance(
        config.get("case_sensitive"), bool
    ):
        raise ValidationError("EVALUATION_RUBRIC_INVALID")
    forbidden = _sequence(config.get("forbidden"), "forbidden", maximum=100)
    terms = [_bounded_string(item, "forbidden[]", maximum=256) for item in forbidden]
    if not terms:
        raise ValidationError("EVALUATION_RUBRIC_INVALID")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _result("FAIL", "UTF8_TEXT_INVALID", {"valid_utf8": False}, {"forbidden_count": len(terms)})
    candidate = text if config["case_sensitive"] else text.casefold()
    normalized_terms = terms if config["case_sensitive"] else [term.casefold() for term in terms]
    matches = [index for index, term in enumerate(normalized_terms) if term in candidate]
    return _result(
        "FAIL" if matches else "PASS",
        "FORBIDDEN_TEXT_PRESENT" if matches else "FORBIDDEN_TEXT_ABSENT",
        {"matched_term_indexes": matches, "text_sha256": sha256_bytes(raw)},
        {"matched_term_indexes": []},
    )


def _evaluate_numeric_threshold(raw: bytes, config: Mapping[str, Any]) -> dict[str, Any]:
    if set(config) != {"direction", "threshold"}:
        raise ValidationError("EVALUATION_RUBRIC_INVALID")
    direction = config.get("direction")
    if direction not in {"at_least", "at_most"}:
        raise ValidationError("EVALUATION_RUBRIC_INVALID")
    threshold = _finite_number(config.get("threshold"), "threshold")
    try:
        parsed = _strict_json_bytes(raw)
        observed = _finite_number(parsed, "observation")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, ValidationError):
        return _result("FAIL", "NUMERIC_OBSERVATION_INVALID", {"valid_number": False}, config)
    passed = observed >= threshold if direction == "at_least" else observed <= threshold
    return _result(
        "PASS" if passed else "FAIL",
        "NUMERIC_THRESHOLD_MET" if passed else "NUMERIC_THRESHOLD_MISSED",
        {"value": observed},
        {"direction": direction, "threshold": threshold},
    )


Evaluator = Callable[[bytes, Mapping[str, Any]], dict[str, Any]]
LOCAL_EVALUATORS: Final[Mapping[str, Evaluator]] = {
    "bytes-digest-equals.v1": _evaluate_bytes_digest,
    "canonical-json-equals.v1": _evaluate_canonical_json,
    "utf8-text-equals.v1": _evaluate_utf8_text,
    "utf8-forbidden-substrings.v1": _evaluate_forbidden_text,
    "numeric-threshold.v1": _evaluate_numeric_threshold,
}


def _validate_dataset(document: Mapping[str, Any]) -> dict[str, Any]:
    dataset = _canonical_object(document, "capabilities.evaluation_catalog.dataset")
    required = {
        "schema_version", "dataset_id", "dataset_version", "privacy", "cases"
    }
    if set(dataset) != required or dataset.get("schema_version") != "1.0":
        raise ValidationError("EVALUATION_DATASET_INVALID")
    dataset_id = require_resource_id(dataset["dataset_id"], "dataset_id")
    dataset_version = require_resource_id(dataset["dataset_version"], "dataset_version")
    privacy = _canonical_object(dataset["privacy"], "dataset.privacy")
    if set(privacy) != {
        "classification", "contains_production_data", "production_data_authorization_id"
    }:
        raise ValidationError("EVALUATION_DATASET_PRIVACY_INVALID")
    classification = privacy.get("classification")
    contains_production = privacy.get("contains_production_data")
    authorization_id = privacy.get("production_data_authorization_id")
    if classification not in {"SYNTHETIC", "PUBLIC", "AUTHORIZED_PRODUCTION"} or not isinstance(
        contains_production, bool
    ):
        raise ValidationError("EVALUATION_DATASET_PRIVACY_INVALID")
    if contains_production:
        if classification != "AUTHORIZED_PRODUCTION":
            raise AuthorizationError("EVALUATION_PRODUCTION_DATA_UNAUTHORIZED")
        _bounded_string(authorization_id, "production_data_authorization_id")
    elif authorization_id is not None:
        raise ValidationError("EVALUATION_DATASET_PRIVACY_INVALID")
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(_sequence(dataset["cases"], "dataset.cases")):
        case = _canonical_object(raw, f"dataset.cases[{index}]")
        if set(case) != {
            "case_id", "acceptance_id", "skill", "category", "execution_scope",
            "evaluator_id", "evaluator_config", "fixture_role",
        }:
            raise ValidationError("EVALUATION_CASE_INVALID")
        case_id = require_resource_id(case["case_id"], "case_id")
        if case_id in seen:
            raise ValidationError("EVALUATION_CASE_DUPLICATE")
        seen.add(case_id)
        acceptance_id = _bounded_string(case["acceptance_id"], "acceptance_id", maximum=16)
        skill = _bounded_string(case["skill"], "skill")
        if ACCEPTANCE_TO_SKILL.get(acceptance_id) != skill:
            raise ValidationError("EVALUATION_ACCEPTANCE_OWNERSHIP_INVALID")
        category = _bounded_string(case["category"], "category", maximum=32).lower()
        execution_scope = _bounded_string(
            case["execution_scope"], "execution_scope", maximum=16
        ).upper()
        if category not in _CATEGORIES or execution_scope not in _EXECUTION_SCOPES:
            raise ValidationError("EVALUATION_CASE_INVALID")
        fixture_role = _bounded_string(case["fixture_role"], "fixture_role", maximum=32)
        if fixture_role not in _FIXTURE_ROLES:
            raise ValidationError("EVALUATION_FIXTURE_ROLE_INVALID")
        evaluator_id = case["evaluator_id"]
        evaluator_config = _canonical_object(case["evaluator_config"], "evaluator_config")
        if execution_scope == "LOCAL":
            if evaluator_id not in LOCAL_EVALUATORS:
                raise ValidationError("EVALUATION_EVALUATOR_NOT_ALLOWLISTED")
            # Validate configuration without trusting an observation.  A
            # deliberately impossible empty probe may return FAIL, but malformed
            # configuration raises before the dataset can be persisted.
            LOCAL_EVALUATORS[evaluator_id](b"", evaluator_config)
        elif evaluator_id is not None or evaluator_config:
            raise ValidationError("EVALUATION_EXTERNAL_CASE_MUST_NOT_NAME_EXECUTOR")
        cases.append(
            {
                **case,
                "case_id": case_id,
                "category": category,
                "execution_scope": execution_scope,
                "fixture_role": fixture_role,
                "case_digest": canonical_digest(case),
            }
        )
    if not cases:
        raise ValidationError("EVALUATION_DATASET_EMPTY")
    return {
        **dataset,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "cases": sorted(cases, key=lambda item: item["case_id"]),
    }


def _validate_rubric(document: Mapping[str, Any]) -> dict[str, Any]:
    rubric = _canonical_object(document, "capabilities.evaluation_catalog.rubric")
    if set(rubric) != {
        "schema_version", "rubric_id", "rubric_version", "allowed_evaluator_ids",
        "required_categories", "regression",
    } or rubric.get("schema_version") != "1.0":
        raise ValidationError("EVALUATION_RUBRIC_INVALID")
    rubric_id = require_resource_id(rubric["rubric_id"], "rubric_id")
    rubric_version = require_resource_id(rubric["rubric_version"], "rubric_version")
    raw_allowed = [
        _bounded_string(item, "allowed_evaluator_ids[]")
        for item in _sequence(rubric["allowed_evaluator_ids"], "allowed_evaluator_ids", maximum=32)
    ]
    allowed = set(raw_allowed)
    if len(allowed) != len(raw_allowed):
        raise ValidationError("EVALUATION_RUBRIC_INVALID")
    if not allowed or not allowed <= set(LOCAL_EVALUATORS):
        raise ValidationError("EVALUATION_EVALUATOR_NOT_ALLOWLISTED")
    categories = {
        _bounded_string(item, "required_categories[]", maximum=32).lower()
        for item in _sequence(rubric["required_categories"], "required_categories", maximum=4)
    }
    if categories != _CATEGORIES:
        raise ValidationError("EVALUATION_REQUIRED_CATEGORIES_INCOMPLETE")
    regression = _canonical_object(rubric["regression"], "rubric.regression")
    if set(regression) != {"baseline_pass_rate", "tolerance", "on_regression"}:
        raise ValidationError("EVALUATION_RUBRIC_INVALID")
    baseline = _finite_number(regression["baseline_pass_rate"], "baseline_pass_rate")
    tolerance = _finite_number(regression["tolerance"], "tolerance")
    if not 0 <= baseline <= 1 or not 0 <= tolerance <= 1 or regression["on_regression"] not in {
        "BLOCK_RELEASE", "REQUIRE_APPROVAL"
    }:
        raise ValidationError("EVALUATION_RUBRIC_INVALID")
    return {
        **rubric,
        "rubric_id": rubric_id,
        "rubric_version": rubric_version,
        "allowed_evaluator_ids": sorted(allowed),
        "required_categories": sorted(categories),
        "regression": {
            "baseline_pass_rate": baseline,
            "tolerance": tolerance,
            "on_regression": regression["on_regression"],
        },
    }


def _dataset_digest(dataset: Mapping[str, Any]) -> str:
    """Digest the source manifest fields, excluding runtime-derived case digests."""

    return canonical_digest(
        {
            **dataset,
            "cases": [
                {key: value for key, value in case.items() if key != "case_digest"}
                for case in dataset["cases"]
            ],
        }
    )


def _trusted_catalog(ctx: RuntimeContext) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    policy = ctx.policy.get("evaluation") if isinstance(ctx.policy, Mapping) else None
    catalog = ctx.capabilities.get("evaluation_catalog") if isinstance(ctx.capabilities, Mapping) else None
    if not isinstance(policy, Mapping) or not isinstance(catalog, Mapping):
        raise AuthorizationError("EVALUATION_TRUST_CONTEXT_UNAVAILABLE")
    if policy.get("tenant_id") != ctx.tenant_id or policy.get("project_id") != ctx.project_id:
        raise AuthorizationError("EVALUATION_POLICY_SCOPE_MISMATCH")
    if catalog.get("tenant_id") != ctx.tenant_id or catalog.get("project_id") != ctx.project_id:
        raise AuthorizationError("EVALUATION_CATALOG_SCOPE_MISMATCH")
    if catalog.get("authorized") is not True:
        raise AuthorizationError("EVALUATION_CATALOG_UNAUTHORIZED")
    authorization_id = _bounded_string(catalog.get("authorization_id"), "authorization_id")
    profile_version = require_resource_id(policy.get("profile_version"), "profile_version")
    raw_dataset = catalog.get("dataset")
    raw_rubric = catalog.get("rubric")
    if not isinstance(raw_dataset, Mapping) or not isinstance(raw_rubric, Mapping):
        raise ValidationError("EVALUATION_CATALOG_CONTRACT_INVALID")
    dataset = _validate_dataset(raw_dataset)
    rubric = _validate_rubric(raw_rubric)
    dataset_digest = _dataset_digest(dataset)
    rubric_digest = canonical_digest(rubric)
    if _normalized_digest(catalog.get("dataset_digest"), "catalog.dataset_digest") != dataset_digest:
        raise IntegrityError("EVALUATION_DATASET_DIGEST_MISMATCH")
    if _normalized_digest(catalog.get("rubric_digest"), "catalog.rubric_digest") != rubric_digest:
        raise IntegrityError("EVALUATION_RUBRIC_DIGEST_MISMATCH")
    raw_required_skills = [
        _bounded_string(item, "policy.required_skills[]")
        for item in _sequence(policy.get("required_skills"), "policy.required_skills", maximum=50)
    ]
    required_skills = set(raw_required_skills)
    if len(required_skills) != len(raw_required_skills):
        raise ValidationError("EVALUATION_REQUIRED_SCOPE_INVALID")
    if not required_skills or not required_skills <= set(ACCEPTANCE_TO_SKILL.values()):
        raise ValidationError("EVALUATION_REQUIRED_SCOPE_INVALID")
    if _normalized_digest(policy.get("dataset_digest"), "policy.dataset_digest") != dataset_digest:
        raise IntegrityError("EVALUATION_POLICY_DATASET_DRIFT")
    if _normalized_digest(policy.get("rubric_digest"), "policy.rubric_digest") != rubric_digest:
        raise IntegrityError("EVALUATION_POLICY_RUBRIC_DRIFT")
    if _normalized_digest(
        policy.get("acceptance_catalog_digest"), "policy.acceptance_catalog_digest"
    ) != ACCEPTANCE_CATALOG_DIGEST:
        raise IntegrityError("EVALUATION_ACCEPTANCE_CATALOG_DRIFT")
    if policy.get("dataset_id") != dataset["dataset_id"] or policy.get(
        "dataset_version"
    ) != dataset["dataset_version"]:
        raise IntegrityError("EVALUATION_POLICY_DATASET_DRIFT")
    if policy.get("rubric_id") != rubric["rubric_id"] or policy.get(
        "rubric_version"
    ) != rubric["rubric_version"]:
        raise IntegrityError("EVALUATION_POLICY_RUBRIC_DRIFT")
    evaluator_ids = {
        case["evaluator_id"] for case in dataset["cases"] if case["execution_scope"] == "LOCAL"
    }
    if not evaluator_ids <= set(rubric["allowed_evaluator_ids"]):
        raise AuthorizationError("EVALUATION_EVALUATOR_NOT_AUTHORIZED_BY_RUBRIC")
    raw_verifier_actor_ids = [
        require_actor_id(item)
        for item in _sequence(
            catalog.get("independent_verifier_actor_ids", []),
            "independent_verifier_actor_ids",
            maximum=100,
        )
    ]
    verifier_actor_ids = set(raw_verifier_actor_ids)
    if len(verifier_actor_ids) != len(raw_verifier_actor_ids):
        raise ValidationError("EVALUATION_VERIFIER_REGISTRY_INVALID")
    trusted = {
        "authorization_id": authorization_id,
        "profile_version": profile_version,
        "required_skills": sorted(required_skills),
        "verifier_actor_ids": sorted(verifier_actor_ids),
        "dataset_digest": dataset_digest,
        "rubric_digest": rubric_digest,
    }
    return dataset, rubric, trusted


class EvaluationStore:
    """Independent SQLite ledger plus tenant/project-partitioned evidence CAS."""

    def __init__(self, database: str | Path, evidence_root: str | Path) -> None:
        self.database = self._secure_database(Path(database).expanduser())
        self.evidence_root = self._secure_directory(Path(evidence_root).expanduser())
        with self._connect() as connection:
            schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if schema_version not in {0, 1}:
                raise IntegrityError("EVALUATION_SCHEMA_VERSION_UNSUPPORTED")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS evaluation_manifests (
                  tenant_id TEXT NOT NULL,
                  project_id TEXT NOT NULL,
                  dataset_id TEXT NOT NULL,
                  dataset_version TEXT NOT NULL,
                  dataset_digest TEXT NOT NULL,
                  rubric_id TEXT NOT NULL,
                  rubric_version TEXT NOT NULL,
                  rubric_digest TEXT NOT NULL,
                  profile_version TEXT NOT NULL,
                  authorization_id TEXT NOT NULL,
                  dataset_json TEXT NOT NULL,
                  rubric_json TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  PRIMARY KEY (
                    tenant_id, project_id, dataset_id, dataset_version,
                    rubric_id, rubric_version
                  )
                ) WITHOUT ROWID;
                CREATE TABLE IF NOT EXISTS evaluation_artifacts (
                  tenant_id TEXT NOT NULL,
                  project_id TEXT NOT NULL,
                  artifact_digest TEXT NOT NULL,
                  byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
                  media_type TEXT NOT NULL,
                  storage_key TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  PRIMARY KEY (tenant_id, project_id, artifact_digest)
                ) WITHOUT ROWID;
                CREATE TABLE IF NOT EXISTS evaluation_runs (
                  tenant_id TEXT NOT NULL,
                  project_id TEXT NOT NULL,
                  run_id TEXT NOT NULL,
                  idempotency_key TEXT NOT NULL,
                  request_digest TEXT NOT NULL,
                  dataset_id TEXT NOT NULL,
                  dataset_version TEXT NOT NULL,
                  dataset_digest TEXT NOT NULL,
                  rubric_id TEXT NOT NULL,
                  rubric_version TEXT NOT NULL,
                  rubric_digest TEXT NOT NULL,
                  subject_json TEXT NOT NULL,
                  subject_digest TEXT NOT NULL,
                  executor_id TEXT NOT NULL,
                  state TEXT NOT NULL,
                  decision TEXT NOT NULL,
                  report_json TEXT,
                  report_digest TEXT,
                  created_at TEXT NOT NULL,
                  completed_at TEXT,
                  PRIMARY KEY (tenant_id, project_id, run_id),
                  UNIQUE (tenant_id, project_id, idempotency_key)
                ) WITHOUT ROWID;
                CREATE TABLE IF NOT EXISTS evaluation_results (
                  tenant_id TEXT NOT NULL,
                  project_id TEXT NOT NULL,
                  run_id TEXT NOT NULL,
                  case_id TEXT NOT NULL,
                  acceptance_id TEXT NOT NULL,
                  skill TEXT NOT NULL,
                  category TEXT NOT NULL,
                  execution_scope TEXT NOT NULL,
                  evaluator_id TEXT,
                  case_digest TEXT NOT NULL,
                  artifact_digest TEXT,
                  artifact_byte_count INTEGER,
                  status TEXT NOT NULL,
                  code TEXT NOT NULL,
                  result_json TEXT NOT NULL,
                  result_digest TEXT NOT NULL,
                  PRIMARY KEY (tenant_id, project_id, run_id, case_id)
                ) WITHOUT ROWID;
                CREATE TABLE IF NOT EXISTS evaluation_verifications (
                  tenant_id TEXT NOT NULL,
                  project_id TEXT NOT NULL,
                  run_id TEXT NOT NULL,
                  verifier_id TEXT NOT NULL,
                  idempotency_key TEXT NOT NULL,
                  request_digest TEXT NOT NULL,
                  verification_json TEXT NOT NULL,
                  verification_digest TEXT NOT NULL,
                  verified_at TEXT NOT NULL,
                  PRIMARY KEY (tenant_id, project_id, run_id),
                  UNIQUE (tenant_id, project_id, idempotency_key)
                ) WITHOUT ROWID;
                CREATE INDEX IF NOT EXISTS evaluation_runs_subject_idx ON evaluation_runs(
                  tenant_id, project_id, dataset_id, dataset_version, subject_digest, state
                );
                PRAGMA user_version=1;
                """
            )
            for table, expected_columns in _EVALUATION_SCHEMA_COLUMNS.items():
                actual_columns = frozenset(
                    str(row[1])
                    for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
                )
                if actual_columns != expected_columns:
                    raise IntegrityError("EVALUATION_SCHEMA_DRIFT")

    @staticmethod
    def _secure_directory(path: Path) -> Path:
        if not path.is_absolute() or path == Path(path.anchor):
            raise ValidationError("EVALUATION_STORAGE_PATH_INVALID")
        existed = path.exists() or path.is_symlink()
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not existed:
            path.chmod(0o700)
        metadata = path.stat()
        wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
        if path.is_symlink() or not path.is_dir() or wrong_owner or metadata.st_mode & 0o077:
            raise ValidationError("EVALUATION_STORAGE_PERMISSIONS_INVALID")
        return path

    @classmethod
    def _secure_database(cls, path: Path) -> Path:
        cls._secure_directory(path.parent)
        if not path.is_absolute() or path == Path(path.anchor) or path.is_symlink():
            raise ValidationError("EVALUATION_DATABASE_INVALID")
        if not path.exists():
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(path, flags, 0o600)
            except OSError as error:
                raise ValidationError("EVALUATION_DATABASE_INVALID") from error
            os.close(descriptor)
        metadata = path.stat()
        wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
        if not stat.S_ISREG(metadata.st_mode) or wrong_owner or metadata.st_mode & 0o077:
            raise ValidationError("EVALUATION_DATABASE_PERMISSIONS_INVALID")
        return path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def persist_manifest(
        self,
        ctx: RuntimeContext,
        dataset: Mapping[str, Any],
        rubric: Mapping[str, Any],
        trusted: Mapping[str, Any],
    ) -> None:
        record = (
            ctx.tenant_id, ctx.project_id, dataset["dataset_id"], dataset["dataset_version"],
            trusted["dataset_digest"], rubric["rubric_id"], rubric["rubric_version"],
            trusted["rubric_digest"], trusted["profile_version"], trusted["authorization_id"],
            canonical_json(dataset), canonical_json(rubric), utc_now(),
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT dataset_digest,rubric_id,rubric_version,rubric_digest,profile_version,
                          authorization_id,dataset_json,rubric_json
                   FROM evaluation_manifests
                   WHERE tenant_id=? AND project_id=? AND dataset_id=? AND dataset_version=?
                     AND rubric_id=? AND rubric_version=?""",
                (record[0], record[1], record[2], record[3], record[5], record[6]),
            ).fetchone()
            expected = record[4:12]
            if existing is not None:
                observed = tuple(existing[key] for key in existing.keys())
                if observed != expected:
                    connection.rollback()
                    raise ConflictError("EVALUATION_IMMUTABLE_MANIFEST_CONFLICT")
                connection.commit()
                return
            connection.execute(
                """INSERT INTO evaluation_manifests(
                     tenant_id,project_id,dataset_id,dataset_version,dataset_digest,
                     rubric_id,rubric_version,rubric_digest,profile_version,authorization_id,
                     dataset_json,rubric_json,created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                record,
            )
            connection.commit()

    def _scope_token(self, ctx: RuntimeContext) -> str:
        return hashlib.sha256(f"{ctx.tenant_id}\0{ctx.project_id}".encode()).hexdigest()

    def _artifact_path(self, ctx: RuntimeContext, digest: str) -> tuple[Path, str]:
        scope = self._scope_token(ctx)
        storage_key = f"{scope[:2]}/{scope}/{digest[:2]}/{digest}"
        path = self.evidence_root.joinpath(*storage_key.split("/"))
        if self.evidence_root not in path.parents:
            raise IntegrityError("EVALUATION_ARTIFACT_PATH_ESCAPE")
        return path, storage_key

    @staticmethod
    def _read_bounded_artifact_file(path: Path) -> bytes:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise IntegrityError("EVALUATION_ARTIFACT_STORAGE_INVALID") from error
        try:
            metadata = os.fstat(descriptor)
            wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or wrong_owner
                or metadata.st_mode & 0o077
                or metadata.st_size > _MAX_ARTIFACT_BYTES
            ):
                raise IntegrityError("EVALUATION_ARTIFACT_STORAGE_INVALID")
            chunks: list[bytes] = []
            remaining = metadata.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    raise IntegrityError("EVALUATION_ARTIFACT_INTEGRITY_FAILED")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise IntegrityError("EVALUATION_ARTIFACT_INTEGRITY_FAILED")
            raw = b"".join(chunks)
            if len(raw) != metadata.st_size:
                raise IntegrityError("EVALUATION_ARTIFACT_INTEGRITY_FAILED")
            return raw
        finally:
            os.close(descriptor)

    def put_artifact(self, ctx: RuntimeContext, raw: bytes, media_type: str) -> dict[str, Any]:
        if len(raw) > _MAX_ARTIFACT_BYTES:
            raise ValidationError("EVALUATION_ARTIFACT_TOO_LARGE")
        if not _SAFE_MEDIA_TYPE.fullmatch(media_type):
            raise ValidationError("EVALUATION_MEDIA_TYPE_INVALID")
        digest = sha256_bytes(raw)
        path, storage_key = self._artifact_path(ctx, digest)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.exists() or path.is_symlink():
            if path.is_symlink() or not path.is_file():
                raise IntegrityError("EVALUATION_ARTIFACT_STORAGE_INVALID")
            existing = self._read_bounded_artifact_file(path)
            if len(existing) != len(raw) or sha256_bytes(existing) != digest or existing != raw:
                raise IntegrityError("EVALUATION_ARTIFACT_COLLISION")
        else:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags, 0o600)
            try:
                offset = 0
                while offset < len(raw):
                    written = os.write(descriptor, raw[offset:])
                    if written <= 0:
                        raise OSError("short artifact write")
                    offset += written
                os.fsync(descriptor)
            except BaseException:
                os.close(descriptor)
                try:
                    path.unlink()
                except OSError:
                    pass
                raise
            else:
                os.close(descriptor)
        with self._connect() as connection:
            existing = connection.execute(
                """SELECT byte_count,media_type,storage_key FROM evaluation_artifacts
                   WHERE tenant_id=? AND project_id=? AND artifact_digest=?""",
                (ctx.tenant_id, ctx.project_id, digest),
            ).fetchone()
            if existing is not None and (
                int(existing["byte_count"]), existing["media_type"], existing["storage_key"]
            ) != (len(raw), media_type, storage_key):
                raise ConflictError("EVALUATION_ARTIFACT_METADATA_CONFLICT")
            connection.execute(
                """INSERT OR IGNORE INTO evaluation_artifacts(
                     tenant_id,project_id,artifact_digest,byte_count,media_type,storage_key,created_at
                   ) VALUES (?,?,?,?,?,?,?)""",
                (ctx.tenant_id, ctx.project_id, digest, len(raw), media_type, storage_key, utc_now()),
            )
        return {"artifact_digest": digest, "byte_count": len(raw), "media_type": media_type}

    def read_artifact(self, ctx: RuntimeContext, digest: str) -> tuple[bytes, dict[str, Any]]:
        normalized = _normalized_digest(digest, "artifact_digest")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT byte_count,media_type,storage_key FROM evaluation_artifacts
                   WHERE tenant_id=? AND project_id=? AND artifact_digest=?""",
                (ctx.tenant_id, ctx.project_id, normalized),
            ).fetchone()
        if row is None:
            raise NotFoundError("EVALUATION_ARTIFACT_NOT_FOUND")
        expected_path, expected_key = self._artifact_path(ctx, normalized)
        if row["storage_key"] != expected_key or expected_path.is_symlink() or not expected_path.is_file():
            raise IntegrityError("EVALUATION_ARTIFACT_STORAGE_INVALID")
        raw = self._read_bounded_artifact_file(expected_path)
        if len(raw) != int(row["byte_count"]) or sha256_bytes(raw) != normalized:
            raise IntegrityError("EVALUATION_ARTIFACT_INTEGRITY_FAILED")
        return raw, {
            "artifact_digest": normalized,
            "byte_count": len(raw),
            "media_type": row["media_type"],
        }

    def begin_run(
        self,
        ctx: RuntimeContext,
        *,
        request_digest: str,
        dataset: Mapping[str, Any],
        rubric: Mapping[str, Any],
        trusted: Mapping[str, Any],
        subject: Mapping[str, Any],
    ) -> tuple[str, str, dict[str, Any] | None]:
        idempotency_key = require_idempotency_key(ctx.idempotency_key or "")
        run_id = "eval-" + hashlib.sha256(
            f"{ctx.tenant_id}\0{ctx.project_id}\0{idempotency_key}".encode()
        ).hexdigest()[:32]
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM evaluation_runs
                   WHERE tenant_id=? AND project_id=? AND idempotency_key=?""",
                (ctx.tenant_id, ctx.project_id, idempotency_key),
            ).fetchone()
            if row is not None:
                if row["request_digest"] != request_digest:
                    connection.rollback()
                    raise ConflictError("EVALUATION_IDEMPOTENCY_CONFLICT")
                report = json.loads(row["report_json"]) if row["report_json"] else None
                connection.commit()
                return ("REPLAY" if row["state"] in _RUN_TERMINAL else "RECOVER", run_id, report)
            connection.execute(
                """INSERT INTO evaluation_runs(
                     tenant_id,project_id,run_id,idempotency_key,request_digest,dataset_id,
                     dataset_version,dataset_digest,rubric_id,rubric_version,rubric_digest,
                     subject_json,subject_digest,executor_id,state,decision,created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ctx.tenant_id, ctx.project_id, run_id, idempotency_key, request_digest,
                    dataset["dataset_id"], dataset["dataset_version"], trusted["dataset_digest"],
                    rubric["rubric_id"], rubric["rubric_version"], trusted["rubric_digest"],
                    canonical_json(subject), canonical_digest(subject), ctx.actor_id,
                    "RUNNING", "NOT_RUN", utc_now(),
                ),
            )
            connection.commit()
        return "CLAIMED", run_id, None

    def complete_run(
        self,
        ctx: RuntimeContext,
        *,
        run_id: str,
        request_digest: str,
        results: Sequence[Mapping[str, Any]],
        report: Mapping[str, Any],
    ) -> None:
        report_json = canonical_json(report)
        report_without_digest = {key: value for key, value in report.items() if key != "report_digest"}
        report_digest = canonical_digest(report_without_digest)
        if report.get("report_digest") != report_digest:
            raise IntegrityError("EVALUATION_REPORT_DIGEST_INVALID")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT request_digest,state,report_digest FROM evaluation_runs
                   WHERE tenant_id=? AND project_id=? AND run_id=?""",
                (ctx.tenant_id, ctx.project_id, run_id),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise NotFoundError("EVALUATION_RUN_NOT_FOUND")
            if row["request_digest"] != request_digest:
                connection.rollback()
                raise ConflictError("EVALUATION_RUN_BINDING_CONFLICT")
            if row["state"] in _RUN_TERMINAL:
                if row["report_digest"] != report_digest:
                    connection.rollback()
                    raise IntegrityError("EVALUATION_REPLAY_RESULT_DRIFT")
                connection.commit()
                return
            for result in results:
                result_json = canonical_json(result["evaluator_result"])
                connection.execute(
                    """INSERT INTO evaluation_results(
                         tenant_id,project_id,run_id,case_id,acceptance_id,skill,category,
                         execution_scope,evaluator_id,case_digest,artifact_digest,
                         artifact_byte_count,status,code,result_json,result_digest
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ctx.tenant_id, ctx.project_id, run_id, result["case_id"],
                        result["acceptance_id"], result["skill"], result["category"],
                        result["execution_scope"], result.get("evaluator_id"),
                        result["case_digest"], result.get("artifact_digest"),
                        result.get("artifact_byte_count"), result["status"], result["code"],
                        result_json, canonical_digest(result["evaluator_result"]),
                    ),
                )
            connection.execute(
                """UPDATE evaluation_runs SET state='EVALUATED',decision=?,report_json=?,
                     report_digest=?,completed_at=?
                   WHERE tenant_id=? AND project_id=? AND run_id=? AND state='RUNNING'""",
                (
                    report["decision"], report_json, report_digest, utc_now(),
                    ctx.tenant_id, ctx.project_id, run_id,
                ),
            )
            connection.commit()

    def load_run(self, ctx: RuntimeContext, run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        run_id = require_resource_id(run_id, "run_id")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM evaluation_runs
                   WHERE tenant_id=? AND project_id=? AND run_id=?""",
                (ctx.tenant_id, ctx.project_id, run_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("EVALUATION_RUN_NOT_FOUND")
            result_rows = connection.execute(
                """SELECT * FROM evaluation_results
                   WHERE tenant_id=? AND project_id=? AND run_id=? ORDER BY case_id""",
                (ctx.tenant_id, ctx.project_id, run_id),
            ).fetchall()
        return dict(row), [dict(item) for item in result_rows]

    def manifest_for_run(
        self,
        ctx: RuntimeContext,
        run: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT dataset_json,rubric_json,dataset_digest,rubric_digest
                   FROM evaluation_manifests
                   WHERE tenant_id=? AND project_id=? AND dataset_id=? AND dataset_version=?
                     AND rubric_id=? AND rubric_version=?""",
                (
                    ctx.tenant_id, ctx.project_id, run["dataset_id"], run["dataset_version"],
                    run["rubric_id"], run["rubric_version"],
                ),
            ).fetchone()
        if row is None:
            raise IntegrityError("EVALUATION_MANIFEST_MISSING")
        if row["dataset_digest"] != run["dataset_digest"] or row["rubric_digest"] != run["rubric_digest"]:
            raise IntegrityError("EVALUATION_MANIFEST_DRIFT")
        return json.loads(row["dataset_json"]), json.loads(row["rubric_json"])

    def record_verification(
        self,
        ctx: RuntimeContext,
        *,
        run: Mapping[str, Any],
        verification: Mapping[str, Any],
        request_digest: str,
    ) -> tuple[dict[str, Any], bool]:
        idempotency_key = require_idempotency_key(ctx.idempotency_key or "")
        document = dict(verification)
        document["verification_digest"] = canonical_digest(document)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT verifier_id,idempotency_key,request_digest,verification_json,
                          verification_digest
                   FROM evaluation_verifications
                   WHERE tenant_id=? AND project_id=? AND run_id=?""",
                (ctx.tenant_id, ctx.project_id, run["run_id"]),
            ).fetchone()
            if existing is not None:
                if (
                    existing["idempotency_key"] != idempotency_key
                    or existing["request_digest"] != request_digest
                ):
                    connection.rollback()
                    raise ConflictError("EVALUATION_VERIFICATION_ALREADY_RECORDED")
                stored = json.loads(existing["verification_json"])
                if existing["verification_digest"] != canonical_digest(
                    {key: value for key, value in stored.items() if key != "verification_digest"}
                ):
                    connection.rollback()
                    raise IntegrityError("EVALUATION_VERIFICATION_INTEGRITY_FAILED")
                connection.commit()
                return stored, True
            connection.execute(
                """INSERT INTO evaluation_verifications(
                     tenant_id,project_id,run_id,verifier_id,idempotency_key,request_digest,
                     verification_json,verification_digest,verified_at
                   ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    ctx.tenant_id, ctx.project_id, run["run_id"], ctx.actor_id,
                    idempotency_key, request_digest, canonical_json(document),
                    document["verification_digest"], document["verified_at"],
                ),
            )
            connection.execute(
                """UPDATE evaluation_runs SET state='VERIFIED'
                   WHERE tenant_id=? AND project_id=? AND run_id=? AND state='EVALUATED'""",
                (ctx.tenant_id, ctx.project_id, run["run_id"]),
            )
            connection.commit()
        return document, False


def _subject(value: Any) -> dict[str, Any]:
    document = _canonical_object(value, "inputs.subject")
    if set(document) != {
        "subject_id", "subject_kind", "artifact_digest", "implementation_version",
        "configuration_digest",
    }:
        raise ValidationError("EVALUATION_SUBJECT_INVALID")
    document["subject_id"] = require_resource_id(document["subject_id"], "subject_id")
    document["subject_kind"] = _bounded_string(document["subject_kind"], "subject_kind", maximum=64)
    if document["subject_kind"] not in {"parser", "provider", "model", "runtime", "configuration"}:
        raise ValidationError("EVALUATION_SUBJECT_INVALID")
    document["artifact_digest"] = _normalized_digest(document["artifact_digest"], "artifact_digest")
    document["configuration_digest"] = _normalized_digest(
        document["configuration_digest"], "configuration_digest"
    )
    document["implementation_version"] = require_resource_id(
        document["implementation_version"], "implementation_version"
    )
    return document


def _decode_evidence(value: Any) -> dict[str, tuple[bytes, str]]:
    evidence: dict[str, tuple[bytes, str]] = {}
    total = 0
    for index, raw in enumerate(_sequence(value, "inputs.evidence")):
        item = _canonical_object(raw, f"inputs.evidence[{index}]")
        # Caller-asserted status, scores, digests, byte counts and verifier
        # metadata are deliberately forbidden rather than merely ignored.
        if set(item) != {"case_id", "media_type", "content_base64"}:
            raise ValidationError("EVALUATION_CALLER_EVIDENCE_METADATA_FORBIDDEN")
        case_id = require_resource_id(item["case_id"], "case_id")
        if case_id in evidence:
            raise ValidationError("EVALUATION_EVIDENCE_DUPLICATE")
        encoded = item["content_base64"]
        if (
            not isinstance(encoded, str)
            or encoded != encoded.strip()
            or len(encoded.encode("ascii", errors="ignore")) != len(encoded)
            or len(encoded) > _MAX_BASE64_BYTES
        ):
            raise ValidationError("EVALUATION_EVIDENCE_BASE64_INVALID")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValidationError("EVALUATION_EVIDENCE_BASE64_INVALID") from error
        if len(content) > _MAX_ARTIFACT_BYTES:
            raise ValidationError("EVALUATION_ARTIFACT_TOO_LARGE")
        total += len(content)
        if total > _MAX_TOTAL_ARTIFACT_BYTES:
            raise ValidationError("EVALUATION_EVIDENCE_TOTAL_TOO_LARGE")
        media_type = _bounded_string(item["media_type"], "media_type", maximum=127).lower()
        if not _SAFE_MEDIA_TYPE.fullmatch(media_type):
            raise ValidationError("EVALUATION_MEDIA_TYPE_INVALID")
        evidence[case_id] = (content, media_type)
    return evidence


def _coverage(
    cases: Sequence[Mapping[str, Any]], required_skills: Sequence[str], statuses: Mapping[str, str]
) -> dict[str, list[str]]:
    observed: dict[str, set[str]] = {skill: set() for skill in required_skills}
    for case in cases:
        if case["skill"] in observed and statuses.get(case["case_id"]) == "PASS":
            observed[case["skill"]].add(case["category"])
    return {
        skill: sorted(_CATEGORIES - observed[skill])
        for skill in sorted(observed)
        if _CATEGORIES - observed[skill]
    }


def _evaluate_cases(
    store: EvaluationStore,
    ctx: RuntimeContext,
    dataset: Mapping[str, Any],
    evidence: Mapping[str, tuple[bytes, str]],
) -> list[dict[str, Any]]:
    known = {case["case_id"] for case in dataset["cases"]}
    unknown = sorted(set(evidence) - known)
    if unknown:
        raise ValidationError("EVALUATION_EVIDENCE_CASE_UNKNOWN", details={"count": len(unknown)})
    results: list[dict[str, Any]] = []
    for case in dataset["cases"]:
        base = {
            "case_id": case["case_id"],
            "acceptance_id": case["acceptance_id"],
            "skill": case["skill"],
            "category": case["category"],
            "execution_scope": case["execution_scope"],
            "evaluator_id": case["evaluator_id"],
            "case_digest": case["case_digest"],
        }
        if case["execution_scope"] == "EXTERNAL":
            if case["case_id"] in evidence:
                raise ValidationError("EVALUATION_EXTERNAL_EVIDENCE_IMPORT_UNAVAILABLE")
            results.append(
                {
                    **base,
                    "status": "NOT_RUN",
                    "code": "EXTERNAL_EVIDENCE_NOT_RUN",
                    "evaluator_result": {
                        "status": "NOT_RUN",
                        "code": "EXTERNAL_EVIDENCE_NOT_RUN",
                        "external_evidence": "NOT_RUN",
                    },
                }
            )
            continue
        raw_evidence = evidence.get(case["case_id"])
        if raw_evidence is None:
            results.append(
                {
                    **base,
                    "status": "NOT_RUN",
                    "code": "LOCAL_EVIDENCE_MISSING",
                    "evaluator_result": {
                        "status": "NOT_RUN",
                        "code": "LOCAL_EVIDENCE_MISSING",
                    },
                }
            )
            continue
        raw, media_type = raw_evidence
        artifact = store.put_artifact(ctx, raw, media_type)
        evaluator = LOCAL_EVALUATORS.get(case["evaluator_id"])
        if evaluator is None:
            raise IntegrityError("EVALUATION_EVALUATOR_REGISTRY_DRIFT")
        evaluated = evaluator(raw, case["evaluator_config"])
        evaluator_result = {
            "schema_version": "elmos-local-evaluator-result-v1",
            "case_id": case["case_id"],
            "case_digest": case["case_digest"],
            "evaluator_id": case["evaluator_id"],
            "artifact_digest": artifact["artifact_digest"],
            "artifact_byte_count": artifact["byte_count"],
            **evaluated,
        }
        results.append(
            {
                **base,
                "artifact_digest": artifact["artifact_digest"],
                "artifact_byte_count": artifact["byte_count"],
                "status": evaluated["status"],
                "code": evaluated["code"],
                "evaluator_result": evaluator_result,
            }
        )
    return results


def _run_report(
    *,
    run_id: str,
    dataset: Mapping[str, Any],
    rubric: Mapping[str, Any],
    trusted: Mapping[str, Any],
    subject: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    statuses = {result["case_id"]: result["status"] for result in results}
    local = [result for result in results if result["execution_scope"] == "LOCAL"]
    local_passed = sum(result["status"] == "PASS" for result in local)
    local_failed = sum(result["status"] == "FAIL" for result in local)
    local_not_run = sum(result["status"] != "PASS" and result["status"] != "FAIL" for result in local)
    external_not_run = sum(result["execution_scope"] == "EXTERNAL" for result in results)
    pass_rate = local_passed / len(local) if local else 0.0
    baseline = rubric["regression"]["baseline_pass_rate"]
    tolerance = rubric["regression"]["tolerance"]
    regressed = pass_rate < baseline - tolerance
    missing_coverage = _coverage(dataset["cases"], trusted["required_skills"], statuses)
    if local_failed or regressed:
        decision = (
            "BLOCK_RELEASE"
            if rubric["regression"]["on_regression"] == "BLOCK_RELEASE"
            else "REQUIRE_APPROVAL"
        )
        state = "BLOCKED"
        code = "MULTIMODAL_EVALUATION_REGRESSION"
    elif local_not_run or missing_coverage or external_not_run:
        decision = "NOT_RUN"
        state = "PARTIAL"
        code = "MULTIMODAL_EVALUATION_INCOMPLETE"
    else:
        decision = "AWAITING_INDEPENDENT_VERIFICATION"
        state = "PARTIAL"
        code = "MULTIMODAL_EVALUATION_AWAITING_VERIFICATION"
    report = {
        "schema_version": "elmos-durable-evaluation-report-v1",
        "run_id": run_id,
        "state": state,
        "code": code,
        "decision": decision,
        "dataset": {
            "dataset_id": dataset["dataset_id"],
            "dataset_version": dataset["dataset_version"],
            "dataset_digest": trusted["dataset_digest"],
            "privacy": dataset["privacy"],
        },
        "rubric": {
            "rubric_id": rubric["rubric_id"],
            "rubric_version": rubric["rubric_version"],
            "rubric_digest": trusted["rubric_digest"],
            "profile_version": trusted["profile_version"],
        },
        "subject": dict(subject),
        "subject_digest": canonical_digest(subject),
        "case_counts": {
            "total": len(results),
            "local": len(local),
            "local_passed": local_passed,
            "local_failed": local_failed,
            "local_not_run": local_not_run,
            "external_not_run": external_not_run,
        },
        "local_pass_rate": pass_rate,
        "regression": {
            "baseline_pass_rate": baseline,
            "tolerance": tolerance,
            "regressed": regressed,
            "action": rubric["regression"]["on_regression"],
        },
        "missing_coverage": missing_coverage,
        "cases": [
            {
                "case_id": result["case_id"],
                "acceptance_id": result["acceptance_id"],
                "skill": result["skill"],
                "category": result["category"],
                "execution_scope": result["execution_scope"],
                "status": result["status"],
                "code": result["code"],
                "evaluator_id": result.get("evaluator_id"),
                "artifact_digest": result.get("artifact_digest"),
                "artifact_byte_count": result.get("artifact_byte_count"),
                "result_digest": canonical_digest(result["evaluator_result"]),
            }
            for result in results
        ],
        "acceptance_catalog": {
            "digest": ACCEPTANCE_CATALOG_DIGEST,
            "count": len(ACCEPTANCE_TO_SKILL),
            "external_evidence": "NOT_RUN",
        },
        "independent_verification": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
    }
    report["report_digest"] = canonical_digest(report)
    return report


class EvaluationSkillBridge:
    """Skill24 bridge over an isolated durable evidence store."""

    def __init__(self, store: EvaluationStore) -> None:
        self._store = store

    @staticmethod
    def _envelope(state: str, code: str, outputs: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "state": state,
            "code": code,
            "outputs": dict(outputs),
            "metrics": {},
            "retryable": False,
        }

    def handle(
        self,
        skill_name: str,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if skill_name != EVALUATION_SKILL:
            raise ValidationError("EVALUATION_SKILL_INVALID")
        dataset, rubric, trusted = _trusted_catalog(ctx)
        self._store.persist_manifest(ctx, dataset, rubric, trusted)
        operation = _bounded_string(payload.get("operation"), "operation", maximum=32).lower()
        if operation == "evaluate":
            return self._evaluate(ctx, payload, dataset, rubric, trusted)
        if operation == "verify":
            return self._verify(ctx, payload, dataset, rubric, trusted)
        if operation == "get_run":
            return self._get_run(ctx, payload)
        if operation == "catalog":
            return self._envelope(
                "PARTIAL",
                "EVALUATION_EXTERNAL_ACCEPTANCE_NOT_RUN",
                {
                    "acceptance_catalog_digest": ACCEPTANCE_CATALOG_DIGEST,
                    "acceptance_count": len(ACCEPTANCE_TO_SKILL),
                    "acceptance": external_acceptance_status(),
                    "external_evidence": "NOT_RUN",
                    "production_certification": "NOT_CERTIFIED",
                },
            )
        raise ValidationError("EVALUATION_OPERATION_UNSUPPORTED")

    def _evaluate(
        self,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
        dataset: Mapping[str, Any],
        rubric: Mapping[str, Any],
        trusted: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        subject = _subject(payload.get("subject"))
        evidence = _decode_evidence(payload.get("evidence", []))
        case_scopes = {case["case_id"]: case["execution_scope"] for case in dataset["cases"]}
        if set(evidence) - set(case_scopes):
            raise ValidationError(
                "EVALUATION_EVIDENCE_CASE_UNKNOWN",
                details={"count": len(set(evidence) - set(case_scopes))},
            )
        if any(case_scopes[case_id] == "EXTERNAL" for case_id in evidence):
            raise ValidationError("EVALUATION_EXTERNAL_EVIDENCE_IMPORT_UNAVAILABLE")
        evidence_identity = [
            {
                "case_id": case_id,
                "media_type": media_type,
                "byte_count": len(raw),
                "sha256": sha256_bytes(raw),
            }
            for case_id, (raw, media_type) in sorted(evidence.items())
        ]
        request_identity = {
            "schema_version": "elmos-durable-evaluation-request-v1",
            "tenant_id": ctx.tenant_id,
            "project_id": ctx.project_id,
            "dataset_digest": trusted["dataset_digest"],
            "rubric_digest": trusted["rubric_digest"],
            "profile_version": trusted["profile_version"],
            "subject": subject,
            "evidence": evidence_identity,
        }
        request_digest = canonical_digest(request_identity)
        claim, run_id, stored = self._store.begin_run(
            ctx,
            request_digest=request_digest,
            dataset=dataset,
            rubric=rubric,
            trusted=trusted,
            subject=subject,
        )
        if claim == "REPLAY" and stored is not None:
            replayed = dict(stored)
            replayed["idempotent_replay"] = True
            replayed["stored_report_digest"] = stored.get("report_digest")
            return self._envelope(stored["state"], "EVALUATION_RUN_REPLAYED", replayed)
        results = _evaluate_cases(self._store, ctx, dataset, evidence)
        report = _run_report(
            run_id=run_id,
            dataset=dataset,
            rubric=rubric,
            trusted=trusted,
            subject=subject,
            results=results,
        )
        self._store.complete_run(
            ctx,
            run_id=run_id,
            request_digest=request_digest,
            results=results,
            report=report,
        )
        return self._envelope(report["state"], report["code"], report)

    def _verify(
        self,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
        trusted_dataset: Mapping[str, Any],
        trusted_rubric: Mapping[str, Any],
        trusted: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if ctx.actor_id not in trusted["verifier_actor_ids"]:
            raise AuthorizationError("EVALUATION_VERIFIER_NOT_AUTHORIZED")
        run_id = require_resource_id(payload.get("run_id"), "run_id")
        run, stored_results = self._store.load_run(ctx, run_id)
        if run["state"] not in _RUN_TERMINAL:
            raise ConflictError("EVALUATION_RUN_NOT_READY_FOR_VERIFICATION")
        if run["executor_id"] == ctx.actor_id:
            raise AuthorizationError("EVALUATION_SELF_VERIFICATION_FORBIDDEN")
        if not isinstance(run.get("report_json"), str) or not isinstance(
            run.get("report_digest"), str
        ):
            raise IntegrityError("EVALUATION_REPORT_MISSING")
        try:
            report = _strict_json_bytes(run["report_json"].encode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise IntegrityError("EVALUATION_REPORT_INTEGRITY_FAILED") from None
        if (
            not isinstance(report, Mapping)
            or canonical_json(report) != run["report_json"]
            or report.get("report_digest") != run["report_digest"]
            or canonical_digest(
                {key: value for key, value in report.items() if key != "report_digest"}
            )
            != run["report_digest"]
        ):
            raise IntegrityError("EVALUATION_REPORT_INTEGRITY_FAILED")
        dataset, rubric = self._store.manifest_for_run(ctx, run)
        if (
            _dataset_digest(dataset) != trusted["dataset_digest"]
            or canonical_digest(rubric) != trusted["rubric_digest"]
        ):
            raise IntegrityError("EVALUATION_TRUSTED_MANIFEST_DRIFT")
        if _dataset_digest(trusted_dataset) != trusted["dataset_digest"] or canonical_digest(
            trusted_rubric
        ) != trusted["rubric_digest"]:
            raise IntegrityError("EVALUATION_TRUSTED_MANIFEST_DRIFT")
        case_by_id = {case["case_id"]: case for case in dataset["cases"]}
        if {stored["case_id"] for stored in stored_results} != set(case_by_id):
            raise IntegrityError("EVALUATION_RESULT_SET_INCOMPLETE")
        verified_case_digests: list[str] = []
        statuses: dict[str, str] = {}
        for stored in stored_results:
            case = case_by_id.get(stored["case_id"])
            if case is None or any(
                stored[field] != case[field]
                for field in (
                    "acceptance_id", "skill", "category", "execution_scope",
                    "evaluator_id", "case_digest",
                )
            ):
                raise IntegrityError("EVALUATION_CASE_MANIFEST_DRIFT")
            try:
                stored_result = _strict_json_bytes(stored["result_json"].encode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                raise IntegrityError("EVALUATION_RESULT_INTEGRITY_FAILED") from None
            if (
                not isinstance(stored_result, Mapping)
                or canonical_json(stored_result) != stored["result_json"]
                or canonical_digest(stored_result) != stored["result_digest"]
                or stored_result.get("status") != stored["status"]
                or stored_result.get("code") != stored["code"]
            ):
                raise IntegrityError("EVALUATION_RESULT_INTEGRITY_FAILED")
            if stored["execution_scope"] == "EXTERNAL":
                if stored["status"] != "NOT_RUN" or stored["artifact_digest"] is not None:
                    raise IntegrityError("EVALUATION_EXTERNAL_EVIDENCE_FABRICATED")
                statuses[stored["case_id"]] = "NOT_RUN"
                verified_case_digests.append(stored["result_digest"])
                continue
            if stored["artifact_digest"] is None:
                if stored["status"] != "NOT_RUN":
                    raise IntegrityError("EVALUATION_RESULT_ARTIFACT_MISSING")
                statuses[stored["case_id"]] = "NOT_RUN"
                verified_case_digests.append(stored["result_digest"])
                continue
            raw, artifact = self._store.read_artifact(ctx, stored["artifact_digest"])
            if artifact["byte_count"] != stored["artifact_byte_count"]:
                raise IntegrityError("EVALUATION_ARTIFACT_BYTE_COUNT_DRIFT")
            evaluator = LOCAL_EVALUATORS.get(case["evaluator_id"])
            if evaluator is None:
                raise IntegrityError("EVALUATION_EVALUATOR_REGISTRY_DRIFT")
            rerun = {
                "schema_version": "elmos-local-evaluator-result-v1",
                "case_id": case["case_id"],
                "case_digest": case["case_digest"],
                "evaluator_id": case["evaluator_id"],
                "artifact_digest": artifact["artifact_digest"],
                "artifact_byte_count": artifact["byte_count"],
                **evaluator(raw, case["evaluator_config"]),
            }
            if canonical_digest(rerun) != stored["result_digest"]:
                raise IntegrityError("EVALUATION_REPLAY_RESULT_DRIFT")
            statuses[stored["case_id"]] = rerun["status"]
            verified_case_digests.append(stored["result_digest"])
        local_statuses = [
            statuses[case["case_id"]]
            for case in dataset["cases"]
            if case["execution_scope"] == "LOCAL"
        ]
        external_not_run = any(
            case["execution_scope"] == "EXTERNAL" for case in dataset["cases"]
        )
        missing_coverage = _coverage(dataset["cases"], trusted["required_skills"], statuses)
        regression = bool(report["regression"]["regressed"])
        if "FAIL" in local_statuses or regression:
            decision = report["regression"]["action"]
            state, code = "BLOCKED", "MULTIMODAL_EVALUATION_VERIFIED_REGRESSION"
        elif "NOT_RUN" in local_statuses or external_not_run or missing_coverage:
            decision, state, code = "NOT_RUN", "PARTIAL", "MULTIMODAL_EVALUATION_VERIFIED_INCOMPLETE"
        else:
            decision = "LOCAL_ENGINEERING_PASSED"
            state, code = "SUCCEEDED", "MULTIMODAL_EVALUATION_VERIFIED_LOCAL"
        verification = {
            "schema_version": "elmos-independent-evaluation-verification-v1",
            "run_id": run_id,
            "run_report_digest": run["report_digest"],
            "dataset_digest": run["dataset_digest"],
            "rubric_digest": run["rubric_digest"],
            "profile_version": trusted["profile_version"],
            "authorization_id": trusted["authorization_id"],
            "acceptance_catalog_digest": ACCEPTANCE_CATALOG_DIGEST,
            "executor_id": run["executor_id"],
            "verifier_id": ctx.actor_id,
            "case_result_set_digest": canonical_digest(sorted(verified_case_digests)),
            "decision": decision,
            "state": state,
            "code": code,
            "missing_coverage": missing_coverage,
            "external_evidence": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
            "verified_at": utc_now(),
        }
        request_digest = canonical_digest(
            {
                "schema_version": "elmos-independent-evaluation-verification-request-v1",
                "tenant_id": ctx.tenant_id,
                "project_id": ctx.project_id,
                "run_id": run_id,
                "run_report_digest": run["report_digest"],
                "verifier_id": ctx.actor_id,
            }
        )
        persisted, replayed = self._store.record_verification(
            ctx,
            run=run,
            verification=verification,
            request_digest=request_digest,
        )
        if replayed:
            persisted = dict(persisted)
            persisted["idempotent_replay"] = True
            code = "EVALUATION_VERIFICATION_REPLAYED"
        return self._envelope(persisted["state"], code, persisted)

    def _get_run(self, ctx: RuntimeContext, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        run_id = require_resource_id(payload.get("run_id"), "run_id")
        run, results = self._store.load_run(ctx, run_id)
        if run["report_json"]:
            try:
                report = _strict_json_bytes(run["report_json"].encode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                raise IntegrityError("EVALUATION_REPORT_INTEGRITY_FAILED") from None
            if (
                not isinstance(report, dict)
                or canonical_json(report) != run["report_json"]
                or report.get("report_digest") != run["report_digest"]
                or canonical_digest(
                    {key: value for key, value in report.items() if key != "report_digest"}
                )
                != run["report_digest"]
            ):
                raise IntegrityError("EVALUATION_REPORT_INTEGRITY_FAILED")
        else:
            report = {
                "run_id": run_id,
                "state": run["state"],
                "decision": run["decision"],
            }
        report["durable_result_count"] = len(results)
        report["production_certification"] = "NOT_CERTIFIED"
        state = report.get("state", "PARTIAL")
        return self._envelope(state, "EVALUATION_RUN_LOADED", report)

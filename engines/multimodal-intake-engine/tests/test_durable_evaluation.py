from __future__ import annotations

import base64
import sqlite3
from pathlib import Path

import pytest

from elmos_multimodal_intake.acceptance_catalog import (
    ACCEPTANCE_CATALOG_DIGEST,
    ACCEPTANCE_IDS_BY_SKILL,
    ACCEPTANCE_TO_SKILL,
    external_acceptance_status,
)
from elmos_multimodal_intake.canonical import canonical_digest, sha256_bytes
from elmos_multimodal_intake.durable_evaluation import (
    EVALUATION_SKILL,
    EvaluationSkillBridge,
    EvaluationStore,
)
from elmos_multimodal_intake.errors import (
    AuthorizationError,
    ConflictError,
    IntegrityError,
    NotFoundError,
    ValidationError,
)
from elmos_multimodal_intake.skill_runtime import RuntimeContext


def _case(
    case_id: str,
    acceptance_id: str,
    category: str,
    evaluator_id: str | None,
    evaluator_config: dict[str, object],
    *,
    execution_scope: str = "LOCAL",
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "acceptance_id": acceptance_id,
        "skill": "elmos-multimodal-evaluation-framework",
        "category": category,
        "execution_scope": execution_scope,
        "evaluator_id": evaluator_id,
        "evaluator_config": evaluator_config,
        "fixture_role": "development",
    }


def _dataset(*, external: bool = False, evaluator_id: str = "bytes-digest-equals.v1") -> dict[str, object]:
    cases = [
        _case(
            "eval-positive",
            "S24-01",
            "positive",
            evaluator_id,
            {"expected_sha256": sha256_bytes(b"positive")},
        ),
        _case(
            "eval-boundary",
            "S24-02",
            "boundary",
            "canonical-json-equals.v1",
            {"expected": {"limit": 1}},
        ),
        _case(
            "eval-failure",
            "S24-03",
            "failure",
            "utf8-text-equals.v1",
            {"expected": "failure"},
        ),
        _case(
            "eval-security",
            "S24-04",
            "security",
            "utf8-forbidden-substrings.v1",
            {"forbidden": ["SECRET"], "case_sensitive": True},
        ),
    ]
    if external:
        cases.append(
            _case(
                "eval-external",
                "S24-02",
                "boundary",
                None,
                {},
                execution_scope="EXTERNAL",
            )
        )
    return {
        "schema_version": "1.0",
        "dataset_id": "multimodal-local",
        "dataset_version": "v1",
        "privacy": {
            "classification": "SYNTHETIC",
            "contains_production_data": False,
            "production_data_authorization_id": None,
        },
        "cases": cases,
    }


def _rubric(*, baseline: float = 1.0) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "rubric_id": "multimodal-local-rubric",
        "rubric_version": "v1",
        "allowed_evaluator_ids": [
            "bytes-digest-equals.v1",
            "canonical-json-equals.v1",
            "numeric-threshold.v1",
            "utf8-forbidden-substrings.v1",
            "utf8-text-equals.v1",
        ],
        "required_categories": ["boundary", "failure", "positive", "security"],
        "regression": {
            "baseline_pass_rate": baseline,
            "tolerance": 0.0,
            "on_regression": "BLOCK_RELEASE",
        },
    }


def _context(
    *,
    actor_id: str = "executor-a",
    idempotency_key: str = "evaluate-once",
    tenant_id: str = "tenant-a",
    project_id: str = "project-a",
    dataset: dict[str, object] | None = None,
    rubric: dict[str, object] | None = None,
) -> RuntimeContext:
    dataset = dataset or _dataset()
    rubric = rubric or _rubric()
    dataset_for_digest = {
        **dataset,
        "cases": sorted(dataset["cases"], key=lambda case: case["case_id"]),
    }
    dataset_digest = canonical_digest(dataset_for_digest)
    rubric_digest = canonical_digest(rubric)
    return RuntimeContext(
        tenant_id=tenant_id,
        project_id=project_id,
        actor_id=actor_id,
        request_id="request-a",
        trace_id="trace-a",
        idempotency_key=idempotency_key,
        policy={
            "evaluation": {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "profile_version": "profile-v1",
                "required_skills": ["elmos-multimodal-evaluation-framework"],
                "dataset_id": dataset["dataset_id"],
                "dataset_version": dataset["dataset_version"],
                "dataset_digest": dataset_digest,
                "rubric_id": rubric["rubric_id"],
                "rubric_version": rubric["rubric_version"],
                "rubric_digest": rubric_digest,
                "acceptance_catalog_digest": ACCEPTANCE_CATALOG_DIGEST,
            }
        },
        capabilities={
            "evaluation_catalog": {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "authorized": True,
                "authorization_id": "dataset-authorization-v1",
                "dataset": dataset,
                "dataset_digest": dataset_digest,
                "rubric": rubric,
                "rubric_digest": rubric_digest,
                "independent_verifier_actor_ids": ["executor-a", "verifier-b"],
            }
        },
    )


def _evidence(**overrides: bytes) -> list[dict[str, str]]:
    values = {
        "eval-positive": b"positive",
        "eval-boundary": b'{"limit":1}',
        "eval-failure": b"failure",
        "eval-security": b"safe output",
        **overrides,
    }
    return [
        {
            "case_id": case_id,
            "media_type": "application/json" if case_id == "eval-boundary" else "text/plain",
            "content_base64": base64.b64encode(raw).decode("ascii"),
        }
        for case_id, raw in sorted(values.items())
    ]


def _subject() -> dict[str, str]:
    return {
        "subject_id": "parser-a",
        "subject_kind": "parser",
        "artifact_digest": sha256_bytes(b"parser-artifact"),
        "implementation_version": "v1",
        "configuration_digest": sha256_bytes(b"parser-configuration"),
    }


def _bridge(tmp_path: Path) -> tuple[EvaluationSkillBridge, EvaluationStore]:
    store = EvaluationStore(tmp_path / "evaluation.sqlite3", tmp_path / "evidence")
    return EvaluationSkillBridge(store), store


def test_acceptance_catalog_explicitly_owns_all_240_source_ids() -> None:
    assert len(ACCEPTANCE_IDS_BY_SKILL) == 50
    assert len(ACCEPTANCE_TO_SKILL) == 240
    assert len(set(ACCEPTANCE_TO_SKILL)) == 240
    assert sum(len(ids) for ids in ACCEPTANCE_IDS_BY_SKILL.values()) == 240
    status = external_acceptance_status()
    assert len(status) == 240
    assert {item["external_evidence"] for item in status} == {"NOT_RUN"}
    assert {item["certification"] for item in status} == {"NOT_CERTIFIED"}


def test_evaluator_derives_status_from_bytes_and_replays_idempotently(tmp_path: Path) -> None:
    bridge, _store = _bridge(tmp_path)
    context = _context()
    payload = {"operation": "evaluate", "subject": _subject(), "evidence": _evidence()}

    evaluated = bridge.handle(EVALUATION_SKILL, context, payload)
    assert evaluated["state"] == "PARTIAL"
    assert evaluated["code"] == "MULTIMODAL_EVALUATION_AWAITING_VERIFICATION"
    assert evaluated["outputs"]["decision"] == "AWAITING_INDEPENDENT_VERIFICATION"
    assert evaluated["outputs"]["case_counts"] == {
        "total": 4,
        "local": 4,
        "local_passed": 4,
        "local_failed": 0,
        "local_not_run": 0,
        "external_not_run": 0,
    }
    for case in evaluated["outputs"]["cases"]:
        assert case["artifact_byte_count"] > 0
        assert len(case["artifact_digest"]) == 64

    replayed = bridge.handle(EVALUATION_SKILL, context, payload)
    assert replayed["code"] == "EVALUATION_RUN_REPLAYED"
    assert replayed["outputs"]["idempotent_replay"] is True
    assert replayed["outputs"]["stored_report_digest"] == evaluated["outputs"]["report_digest"]

    with pytest.raises(ConflictError, match="EVALUATION_IDEMPOTENCY_CONFLICT"):
        bridge.handle(
            EVALUATION_SKILL,
            context,
            {
                "operation": "evaluate",
                "subject": _subject(),
                "evidence": _evidence(**{"eval-positive": b"changed"}),
            },
        )


def test_caller_status_digest_byte_count_and_verifier_claims_are_forbidden(tmp_path: Path) -> None:
    bridge, _store = _bridge(tmp_path)
    evidence = _evidence()
    evidence[0]["status"] = "PASS"
    evidence[0]["artifact_digest"] = sha256_bytes(b"invented")
    evidence[0]["byte_count"] = "1"
    evidence[0]["verifier_id"] = "caller"
    with pytest.raises(ValidationError, match="EVALUATION_CALLER_EVIDENCE_METADATA_FORBIDDEN"):
        bridge.handle(
            EVALUATION_SKILL,
            _context(),
            {"operation": "evaluate", "subject": _subject(), "evidence": evidence},
        )


def test_independent_verifier_replays_raw_bytes_and_self_verification_fails(tmp_path: Path) -> None:
    bridge, _store = _bridge(tmp_path)
    evaluated = bridge.handle(
        EVALUATION_SKILL,
        _context(),
        {"operation": "evaluate", "subject": _subject(), "evidence": _evidence()},
    )
    run_id = evaluated["outputs"]["run_id"]

    with pytest.raises(AuthorizationError, match="EVALUATION_SELF_VERIFICATION_FORBIDDEN"):
        bridge.handle(
            EVALUATION_SKILL,
            _context(idempotency_key="self-verify"),
            {"operation": "verify", "run_id": run_id},
        )

    verified = bridge.handle(
        EVALUATION_SKILL,
        _context(actor_id="verifier-b", idempotency_key="verify-once"),
        {"operation": "verify", "run_id": run_id},
    )
    assert verified["state"] == "SUCCEEDED"
    assert verified["outputs"]["decision"] == "LOCAL_ENGINEERING_PASSED"
    assert verified["outputs"]["executor_id"] == "executor-a"
    assert verified["outputs"]["verifier_id"] == "verifier-b"
    assert verified["outputs"]["external_evidence"] == "NOT_RUN"
    assert verified["outputs"]["production_certification"] == "NOT_CERTIFIED"

    replayed = bridge.handle(
        EVALUATION_SKILL,
        _context(actor_id="verifier-b", idempotency_key="verify-once"),
        {"operation": "verify", "run_id": run_id},
    )
    assert replayed["code"] == "EVALUATION_VERIFICATION_REPLAYED"
    assert replayed["outputs"]["idempotent_replay"] is True


def test_verifier_detects_raw_artifact_byte_tampering(tmp_path: Path) -> None:
    bridge, store = _bridge(tmp_path)
    evaluated = bridge.handle(
        EVALUATION_SKILL,
        _context(),
        {"operation": "evaluate", "subject": _subject(), "evidence": _evidence()},
    )
    digest = evaluated["outputs"]["cases"][0]["artifact_digest"]
    artifact_path, _ = store._artifact_path(_context(), digest)
    artifact_path.write_bytes(b"tampered")
    with pytest.raises(IntegrityError, match="EVALUATION_ARTIFACT_INTEGRITY_FAILED"):
        bridge.handle(
            EVALUATION_SKILL,
            _context(actor_id="verifier-b", idempotency_key="verify-tampered"),
            {"operation": "verify", "run_id": evaluated["outputs"]["run_id"]},
        )


def test_external_case_never_runs_or_accepts_local_bytes(tmp_path: Path) -> None:
    dataset = _dataset(external=True)
    bridge, _store = _bridge(tmp_path)
    evaluated = bridge.handle(
        EVALUATION_SKILL,
        _context(dataset=dataset),
        {"operation": "evaluate", "subject": _subject(), "evidence": _evidence()},
    )
    external = next(case for case in evaluated["outputs"]["cases"] if case["case_id"] == "eval-external")
    assert external["status"] == "NOT_RUN"
    assert external["code"] == "EXTERNAL_EVIDENCE_NOT_RUN"
    assert external["artifact_digest"] is None

    with pytest.raises(ValidationError, match="EVALUATION_EXTERNAL_EVIDENCE_IMPORT_UNAVAILABLE"):
        bridge.handle(
            EVALUATION_SKILL,
            _context(dataset=dataset, idempotency_key="external-bytes"),
            {
                "operation": "evaluate",
                "subject": _subject(),
                "evidence": _evidence(**{"eval-external": b"caller says external passed"}),
            },
        )


def test_failed_real_observation_blocks_release_and_is_durable(tmp_path: Path) -> None:
    bridge, store = _bridge(tmp_path)
    blocked = bridge.handle(
        EVALUATION_SKILL,
        _context(),
        {
            "operation": "evaluate",
            "subject": _subject(),
            "evidence": _evidence(**{"eval-security": b"SECRET leaked"}),
        },
    )
    assert blocked["state"] == "BLOCKED"
    assert blocked["outputs"]["decision"] == "BLOCK_RELEASE"
    assert blocked["outputs"]["regression"]["regressed"] is True
    with sqlite3.connect(store.database) as connection:
        run = connection.execute("SELECT state,decision,report_digest FROM evaluation_runs").fetchone()
        results = connection.execute(
            "SELECT status,artifact_digest,artifact_byte_count,result_digest FROM evaluation_results"
        ).fetchall()
    assert run is not None and run[0:2] == ("EVALUATED", "BLOCK_RELEASE")
    assert len(run[2]) == 64
    assert len(results) == 4
    assert any(result[0] == "FAIL" for result in results)
    assert all(result[1] and result[2] > 0 and len(result[3]) == 64 for result in results)


def test_unallowlisted_evaluator_and_unauthorized_production_dataset_fail_closed(tmp_path: Path) -> None:
    bridge, _store = _bridge(tmp_path)
    arbitrary = _dataset(evaluator_id="subprocess:repository-command")
    with pytest.raises(ValidationError, match="EVALUATION_EVALUATOR_NOT_ALLOWLISTED"):
        bridge.handle(
            EVALUATION_SKILL,
            _context(dataset=arbitrary),
            {"operation": "evaluate", "subject": _subject(), "evidence": _evidence()},
        )

    production = _dataset()
    production["privacy"] = {
        "classification": "SYNTHETIC",
        "contains_production_data": True,
        "production_data_authorization_id": None,
    }
    with pytest.raises(AuthorizationError, match="EVALUATION_PRODUCTION_DATA_UNAUTHORIZED"):
        bridge.handle(
            EVALUATION_SKILL,
            _context(dataset=production, idempotency_key="production-data"),
            {"operation": "evaluate", "subject": _subject(), "evidence": _evidence()},
        )


def test_scope_and_manifest_digest_drift_fail_closed(tmp_path: Path) -> None:
    bridge, _store = _bridge(tmp_path)
    evaluated = bridge.handle(
        EVALUATION_SKILL,
        _context(),
        {"operation": "evaluate", "subject": _subject(), "evidence": _evidence()},
    )
    with pytest.raises(NotFoundError, match="EVALUATION_RUN_NOT_FOUND"):
        bridge.handle(
            EVALUATION_SKILL,
            _context(
                tenant_id="tenant-b",
                project_id="project-b",
                idempotency_key="other-scope-read",
            ),
            {"operation": "get_run", "run_id": evaluated["outputs"]["run_id"]},
        )

    drifted = _context(idempotency_key="drifted-policy")
    drifted.policy["evaluation"]["dataset_digest"] = sha256_bytes(b"different-dataset")
    with pytest.raises(IntegrityError, match="EVALUATION_POLICY_DATASET_DRIFT"):
        bridge.handle(
            EVALUATION_SKILL,
            drifted,
            {"operation": "evaluate", "subject": _subject(), "evidence": _evidence()},
        )

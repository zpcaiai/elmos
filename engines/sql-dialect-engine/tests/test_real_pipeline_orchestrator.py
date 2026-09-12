"""End-to-End Test for the 10 Real Migration Business Steps Pipeline.

Validates:
1. Full sequential physical execution of all 10 business steps against PostgreSQL 16
2. Non-Self-Certification gate enforcement
3. Serialization of tamper-evident dossier receipt
"""

import json
from pathlib import Path

import pytest

try:
    import psycopg2
    _HAS_PSYCOPG2 = True
except ImportError:
    psycopg2 = None
    _HAS_PSYCOPG2 = False

from elmos_sql_dialect.real_pipeline_orchestrator import RealMigrationPipelineOrchestrator


def is_pg_available() -> bool:
    if not _HAS_PSYCOPG2:
        return False
    try:
        conn = psycopg2.connect(dbname="postgres", user="stephen", host="localhost", port=5432)
        conn.close()
        return True
    except Exception:
        return False


def get_pg_connection():
    return psycopg2.connect(dbname="postgres", user="stephen", host="localhost", port=5432)


def is_opengauss_available() -> bool:
    if not _HAS_PSYCOPG2:
        return False
    try:
        conn = psycopg2.connect(
            dbname="omm",
            user="gaussdb",
            password="Enmotech@123",
            host="localhost",
            port=54321,
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


def get_opengauss_connection():
    return psycopg2.connect(
        dbname="omm",
        user="gaussdb",
        password="Enmotech@123",
        host="localhost",
        port=54321,
        connect_timeout=5,
    )


@pytest.mark.skipif(not is_pg_available(), reason="PostgreSQL 16 not running locally")
def test_end_to_end_real_10_phase_migration_pipeline():
    tgt_factory = get_opengauss_connection if is_opengauss_available() else None

    orchestrator = RealMigrationPipelineOrchestrator(
        connection_factory=get_pg_connection,
        target_connection_factory=tgt_factory,
        use_rust_cdc=True,
    )

    dossier = orchestrator.execute_all_10_phases(target_schema_prefix="elmos_e2e")

    assert dossier.all_phases_passed is True
    assert len(dossier.phases) == 10

    # Ensure all 10 phases passed
    for p in dossier.phases:
        assert p.status == "PASSED_LOCAL_EXECUTED", f"Phase {p.phase_id} {p.name} did not pass: {p.status}"
        assert len(p.evidence_digest) == 64, f"Phase {p.phase_id} missing SHA-256 digest"

    # Verify heterogeneous execution details
    p5 = next(p for p in dossier.phases if p.phase_id == 5)
    assert p5.details["rows_pumped"] == 1000
    if tgt_factory:
        assert "openGauss" in p5.details["target_type"]

    p7 = next(p for p in dossier.phases if p.phase_id == 7)
    assert p7.details["mismatched_chunks"] == 1
    assert 150 in p7.details["pinpointed_mismatched_pks"] or "150" in p7.details["pinpointed_mismatched_pks"]

    # Ensure gate decision strictly adheres to non-self-certification
    assert dossier.gate_decision == "LOCAL_EXECUTED_SELF_ATTESTED"

    # Persist the live execution receipt dossier into the database pack certification folder
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    cert_dir = repo_root / "database-packs" / "postgresql-to-opengauss" / "certification"
    if cert_dir.exists():
        dossier_file = cert_dir / "live-pipeline-execution-dossier.json"
        dossier_file.write_text(json.dumps(dossier.to_dict(), indent=2), encoding="utf-8")
        assert dossier_file.exists()

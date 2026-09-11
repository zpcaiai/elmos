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


@pytest.mark.skipif(not is_pg_available(), reason="PostgreSQL 16 not running locally")
def test_end_to_end_real_10_phase_migration_pipeline():
    orchestrator = RealMigrationPipelineOrchestrator(connection_factory=get_pg_connection)

    dossier = orchestrator.execute_all_10_phases(target_schema_prefix="elmos_e2e")

    assert dossier.all_phases_passed is True
    assert len(dossier.phases) == 10

    # Ensure all 10 phases passed
    for p in dossier.phases:
        assert p.status == "PASSED_LOCAL_EXECUTED", f"Phase {p.phase_id} {p.name} did not pass: {p.status}"
        assert len(p.evidence_digest) == 64, f"Phase {p.phase_id} missing SHA-256 digest"

    # Ensure gate decision strictly adheres to non-self-certification
    assert dossier.gate_decision == "LOCAL_EXECUTED_SELF_ATTESTED"

    # Persist the live execution receipt dossier into the database pack certification folder
    cert_dir = Path(__file__).resolve().parent.parent.parent.parent / "database-packs" / "postgresql-to-opengauss" / "certification"
    if cert_dir.exists():
        dossier_file = cert_dir / "live-pipeline-execution-dossier.json"
        dossier_file.write_text(json.dumps(dossier.to_dict(), indent=2), encoding="utf-8")
        assert dossier_file.exists()

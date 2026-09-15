"""Real industrial integration tests against live local tools:

1. Real Z3 binary (/opt/homebrew/bin/z3) solving real SMT-LIB2 formulas
2. Real PostgreSQL server (localhost:5432) with live connection pooling and advisory locks
3. Real POSIX subprocess sandbox with physical process limits
"""

from __future__ import annotations

import concurrent.futures
import os
import shutil
import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
import pytest

from elmos_proof_harness.adapter_drivers import AdapterStatus, Z3Driver
from elmos_proof_harness.connection_pool import PostgresConnectionPool
from elmos_proof_harness.formal_verifier import (
    FormalVerificationEngine,
    ObligationKind,
    ProofObligation,
    VerificationVerdict,
)
from elmos_proof_harness.migration_manager import MigrationManager
from elmos_proof_harness.sandbox import DisposableSandboxRunner, SandboxLimits


# ==============================================================================
# 1. REAL Z3 SMT SOLVER INTEGRATION (NO MOCKS)
# ==============================================================================


def test_real_z3_solver_available() -> None:
    driver = Z3Driver()
    binary_path = shutil.which("z3")
    print(f"\n[PHYSICAL Z3] Discovered binary at: {binary_path}")
    assert driver.is_available() is True, "Z3 binary should be found in system PATH"


def test_real_z3_solver_unsat_valid_theorem() -> None:
    """Modus Ponens in SMT-LIB2: (p and (p => q)) => q.

    Negating this goal and asserting it should yield UNSAT (meaning theorem holds).
    """
    driver = Z3Driver()
    # Negated goal of Modus Ponens
    formula = (
        "(declare-const p Bool)\n"
        "(declare-const q Bool)\n"
        "(assert (and p (=> p q)))\n"
        "(assert (not q))\n"
        "(check-sat)\n"
    )
    res = driver.execute({"smt2_formula": formula})
    print(f"\n[PHYSICAL Z3 PROOF] Tool: {res.tool_version}, ExitCode: {res.exit_code}, Verdict: {res.parsed_output.get('verdict')}, Duration: {res.elapsed_ms}ms")
    assert res.status == AdapterStatus.SUCCEEDED
    assert res.exit_code == 0
    assert "unsat" in res.stdout
    assert res.parsed_output["verdict"] == "UNSAT"
    assert res.tool_version is not None
    assert "Z3" in res.tool_version
    assert res.elapsed_ms > 0  # Real OS process took measurable time


def test_real_z3_solver_sat_counterexample() -> None:
    """Assert x > 0 and x < 10 and x % 3 == 0.

    Real Z3 should find SAT and return a real model (e.g. x = 3, 6, or 9).
    """
    driver = Z3Driver()
    formula = (
        "(set-option :produce-models true)\n"
        "(declare-const x Int)\n"
        "(assert (> x 0))\n"
        "(assert (< x 10))\n"
        "(assert (= (mod x 3) 0))\n"
        "(check-sat)\n"
        "(get-model)\n"
    )
    res = driver.execute({"smt2_formula": formula})
    print(f"\n[PHYSICAL Z3 SAT] Raw Output:\n{res.stdout.strip()}")
    assert res.status == AdapterStatus.SUCCEEDED
    assert res.exit_code == 0
    assert "sat" in res.stdout
    assert res.parsed_output["verdict"] == "SAT"


def test_real_formal_verifier_closed_loop() -> None:
    """Run FormalVerificationEngine against the REAL Z3 binary to produce a real counterexample and test."""
    engine = FormalVerificationEngine()
    obligation = ProofObligation(
        obligation_id="real-obl-array-index",
        kind=ObligationKind.BOUNDS_CHECK,
        symbol="SafeBuffer::read",
        preconditions=(),
        postconditions=("index >= 0", "index < 100"),
        # Negate bounds: index < 0 or index >= 100
        negated_goal_smt2=(
            "(declare-const index Int)\n"
            "(assert (or (< index 0) (>= index 100)))\n"
            "(assert (= index -42))\n"
        ),
    )

    cert = engine.verify_obligation(obligation, solver_name="z3")
    print(f"\n[FORMAL VERIFIER SYNTHESIS] Refuted with model: {cert.counterexample.assignments if cert.counterexample else None}")
    print(f"[GENERATED REGRESSION TEST CODE]:\n{cert.generated_test_code}")
    assert cert.verdict == VerificationVerdict.REFUTED
    assert cert.solver == "z3"
    assert cert.counterexample is not None
    assert cert.counterexample.assignments.get("index") == -42
    assert cert.generated_test_code is not None
    assert "test_formal_counterexample_real_obl_array_index" in cert.generated_test_code
    assert "inputs = {'index': -42}" in cert.generated_test_code


# ==============================================================================
# 2. REAL POSTGRESQL INTEGRATION (LIVE DB ON LOCALHOST:5432)
# ==============================================================================

REAL_PG_DSN = os.environ.get(
    "ELMOS_POSTGRES_TEST_DSN",
    f"postgresql://{os.environ.get('USER', 'stephen')}@localhost:5432/postgres",
)


def _check_real_pg_available() -> bool:
    try:
        with psycopg.connect(REAL_PG_DSN, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
    except Exception:
        return False


@pytest.mark.skipif(not _check_real_pg_available(), reason="Local PostgreSQL server not reachable")
def test_real_postgres_connection_pool_concurrency() -> None:
    """Test real PostgresConnectionPool under real concurrent load against live database."""
    def connect() -> psycopg.Connection[dict[str, object]]:
        return psycopg.connect(REAL_PG_DSN, row_factory=dict_row, autocommit=False)

    pool = PostgresConnectionPool(connect, min_size=2, max_size=6, timeout_seconds=5.0)

    def worker_task(thread_id: int) -> dict[str, object]:
        with pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_backend_pid() AS pid, %s::int AS thread_id, current_database() AS db, version() AS version",
                    (thread_id,),
                )
                res = cur.fetchone()
                time.sleep(0.05)  # hold connection briefly
                return dict(res) if res else {}

    # Run 10 concurrent tasks across 6-connection pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(worker_task, i) for i in range(10)]
        results = [f.result() for f in futures]

    assert len(results) == 10
    pids = {r["pid"] for r in results}
    version_str = results[0]["version"] if results else "unknown"
    print(f"\n[PHYSICAL POSTGRES POOL] Server: {version_str}")
    print(f"[PHYSICAL POSTGRES POOL] Distinct OS Backend PIDs served: {sorted(pids)}")
    assert len(pids) >= 2, f"Should have pooled across multiple real PG backends, got: {pids}"

    metrics = pool.metrics()
    assert metrics.total_connections <= 6
    assert metrics.active_connections == 0
    pool.close()


@pytest.mark.skipif(not _check_real_pg_available(), reason="Local PostgreSQL server not reachable")
def test_real_postgres_advisory_lock_and_migrations(tmp_path: Path) -> None:
    """Test MigrationManager applying real migrations with pg_advisory_lock on live PostgreSQL."""
    # Create a clean temporary schema for isolation
    test_schema = f"test_harness_mgt_{int(time.time())}"
    with psycopg.connect(REAL_PG_DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA {test_schema}")

    try:
        # Create 2 real SQL migration files
        migrations_dir = tmp_path / "sql_migrations"
        migrations_dir.mkdir()

        v1 = migrations_dir / "V001__init_accounts.sql"
        v1.write_text(
            f"CREATE TABLE {test_schema}.accounts (id SERIAL PRIMARY KEY, name TEXT NOT NULL, balance NUMERIC(12,2));",
            encoding="utf-8",
        )

        v2 = migrations_dir / "V002__add_audit_log.sql"
        v2.write_text(
            f"CREATE TABLE {test_schema}.audit_log (id SERIAL PRIMARY KEY, action TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW());",
            encoding="utf-8",
        )

        manager = MigrationManager(REAL_PG_DSN, migrations_dir=migrations_dir, schema=test_schema)
        applied = manager.apply_pending()
        assert len(applied) == 2
        assert applied[0]["version"] == "001"
        assert applied[1]["version"] == "002"

        # Verify tables were physically created in PostgreSQL
        with psycopg.connect(REAL_PG_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = %s ORDER BY table_name",
                    (test_schema,),
                )
                tables = [r[0] for r in cur.fetchall()]
                print(f"\n[PHYSICAL POSTGRES MIGRATION] Tables physically created in schema '{test_schema}': {tables}")
                assert "accounts" in tables
                assert "audit_log" in tables
                assert "harness_schema_history" in tables

    finally:
        # Clean up temporary test schema
        with psycopg.connect(REAL_PG_DSN, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP SCHEMA IF EXISTS {test_schema} CASCADE")
        print(f"[PHYSICAL POSTGRES CLEANUP] Dropped schema '{test_schema}' successfully.")


# ==============================================================================
# 3. REAL PHYSICAL PROCESS SANDBOX (REAL OS SUBPROCESSES & RLIMITS)
# ==============================================================================


def test_real_sandbox_rlimit_cpu_enforcement() -> None:
    """Run an infinite CPU-bound loop inside DisposableSandboxRunner with 1s CPU limit.

    The OS kernel must send SIGXCPU/SIGKILL to physically terminate the rogue process.
    """
    runner = DisposableSandboxRunner(SandboxLimits(max_cpu_seconds=1))
    # Infinite CPU busy loop
    res = runner.run(["python3", "-c", "while True: pass"], timeout_seconds=4.0)
    print(f"\n[PHYSICAL OS SANDBOX] CPU Rogue Task: exit_code={res.exit_code}, timed_out={res.timed_out}, duration={res.duration_ms}ms, stderr={res.stderr.strip()}")
    # The process must be terminated by timeout or signal
    assert res.timed_out is True or res.exit_code != 0
    assert res.duration_ms >= 800  # Took around ~1 second of actual CPU before termination

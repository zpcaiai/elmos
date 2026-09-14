"""Production SRE resilience, RISK-SYNTHESIS-001 deployment guardrail, and real SQLite backup/restore verification tests."""

from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SynthesisRequest
from elmos_project_synthesis.verification import verify_production_security_guardrail
from elmos_project_synthesis.workspace import generate_workspace


def test_risk_synthesis_001_guardrail_blocks_insecure_starter(tmp_path: Path):
    """RISK-SYNTHESIS-001: Generated starters intentionally use in-memory storage

    and omit identity until an approved production profile is selected.
    Any attempt to deploy or certify an in-memory/unauthenticated starter in production MUST fail-closed.
    """
    starter_ws = tmp_path / "starter_ws"
    starter_ws.mkdir(parents=True)

    # 1. In-memory storage in production context fails closed
    with pytest.raises(RuntimeError, match="SECURITY_GATE_FAILED: INSECURE_STARTER_IN_PRODUCTION.*INSECURE_STORAGE"):
        verify_production_security_guardrail(
            starter_ws,
            {
                "target_environment": "production",
                "storage": "memory",
                "authentication": "jwt",
            },
        )

    # 2. Omitted identity in production context fails closed
    with pytest.raises(RuntimeError, match="SECURITY_GATE_FAILED: INSECURE_STARTER_IN_PRODUCTION.*OMITTED_IDENTITY"):
        verify_production_security_guardrail(
            starter_ws,
            {
                "target_environment": "production",
                "storage": "postgresql",
                "authentication": "none",
            },
        )

    # 3. Missing production operational artifacts fails closed
    with pytest.raises(RuntimeError, match="SECURITY_GATE_FAILED: INSECURE_STARTER_IN_PRODUCTION.*OPERATIONS"):
        verify_production_security_guardrail(
            starter_ws,
            {
                "target_environment": "production",
                "storage": "postgresql",
                "authentication": "oidc",
            },
        )

    # 4. Non-fail-closed mode returns structured violation report
    report = verify_production_security_guardrail(
        starter_ws,
        {
            "target_environment": "production",
            "storage": "memory",
            "authentication": "none",
        },
        fail_closed=False,
    )
    assert report["status"] == "FAILED"
    assert report["gate"] == "RISK-SYNTHESIS-001"
    assert report["is_production_context"] is True
    assert any("INSECURE_STORAGE" in v for v in report["violations"])
    assert any("OMITTED_IDENTITY" in v for v in report["violations"])


def allow_crud(*resources: str) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "actor": "api_user",
            "action": action,
            "resource": resource,
            "effect": "allow",
        }
        for resource in resources
        for action in ("create", "read", "update", "delete")
    )


def _make_sqlite_request(name: str) -> SynthesisRequest:
    draft = create_draft(
        name=name,
        description="SQLite production service",
        entities=(
            {
                "singular": "account",
                "plural": "accounts",
                "fields": [
                    {"name": "holder", "type": "string", "required": True},
                    {"name": "balance", "type": "number", "required": True},
                ],
            },
        ),
        languages=("python",),
        persistence="sqlite",
        auth_mode="jwt",
        permissions=tuple({**permission, "actor": "store-admin"} for permission in allow_crud("account")),
    )
    approved = approve_request(draft, actor="user:stephen-architect")
    return SynthesisRequest.from_mapping(approved)


def test_production_profile_passes_security_guardrail(tmp_path: Path):
    """An approved production profile with durable storage, OIDC auth, and operational contracts passes the gate."""
    workspace = tmp_path / "prod_project"
    req = _make_sqlite_request("banking-core")
    generate_workspace(req.raw, workspace)

    # Verify that all required operational and security contracts exist in the generated workspace
    assert (workspace / "security" / "policy-contract.json").is_file()
    assert (workspace / "security" / "secret-contract.json").is_file()
    assert (workspace / "operations" / "runbook.md").is_file()
    assert (workspace / "operations" / "backup.sh").is_file()
    assert (workspace / "operations" / "restore.sh").is_file()

    # Gate must pass
    result = verify_production_security_guardrail(
        workspace,
        {
            "target_environment": "production",
            "storage": "sqlite",
            "authentication": "jwt",
            "profile": "production",
        },
        fail_closed=True,
    )
    assert result["status"] == "PASSED"
    assert result["violations"] == []


def test_sqlite_backup_and_restore_real_process_execution(tmp_path: Path):
    """Executes the generated operations/backup.sh and operations/restore.sh shell scripts

    against a real SQLite database process, verifying atomic snapshot, sha256 checksumming,
    disaster recovery, and row-level data fidelity.
    """
    workspace = tmp_path / "sqlite_sre_ws"
    req = _make_sqlite_request("vault-service")
    generate_workspace(req.raw, workspace)

    backup_script = workspace / "operations" / "backup.sh"
    restore_script = workspace / "operations" / "restore.sh"
    assert backup_script.is_file()
    assert restore_script.is_file()

    # Ensure scripts are executable
    backup_script.chmod(0o755)
    restore_script.chmod(0o755)

    # Create real SQLite database and populate with test data
    live_db = tmp_path / "live_vault.db"
    conn = sqlite3.connect(str(live_db))
    conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, holder TEXT, balance REAL);")
    conn.execute("INSERT INTO accounts (id, holder, balance) VALUES (1, 'Alice Corp', 1500000.50);")
    conn.execute("INSERT INTO accounts (id, holder, balance) VALUES (2, 'Bob Logistics', 450000.25);")
    conn.commit()
    conn.close()

    # Write database URL file
    db_url_file = tmp_path / "db_url.txt"
    db_url_file.write_text(f"sqlite://{live_db}", encoding="utf-8")

    # Run backup.sh
    backup_output = tmp_path / "backups" / "vault_backup_20260914.db"
    backup_output.parent.mkdir(parents=True, exist_ok=True)

    backup_env = {
        **os.environ,
        "ELMOS_DATABASE_URL_FILE": str(db_url_file),
        "ELMOS_BACKUP_OUTPUT": str(backup_output),
    }

    res_backup = subprocess.run(["/bin/sh", str(backup_script)], env=backup_env, capture_output=True, text=True)
    assert res_backup.returncode == 0, f"backup.sh failed: {res_backup.stderr}"
    assert backup_output.is_file()
    checksum_file = Path(f"{backup_output}.sha256")
    assert checksum_file.is_file()

    # Verify sha256 checksum file content format
    checksum_content = checksum_file.read_text(encoding="utf-8").strip()
    assert len(checksum_content.split()[0]) == 64  # SHA256 hex length

    # Simulate disaster: live DB deleted / corrupted
    live_db.unlink()
    assert not live_db.exists()

    # Run restore.sh into a target restored database
    restored_db = tmp_path / "restored_vault.db"
    restore_url_file = tmp_path / "restore_db_url.txt"
    restore_url_file.write_text(f"sqlite://{restored_db}", encoding="utf-8")

    restore_env = {
        **os.environ,
        "ELMOS_RESTORE_DATABASE_URL_FILE": str(restore_url_file),
        "ELMOS_BACKUP_INPUT": str(backup_output),
    }

    res_restore = subprocess.run(["/bin/sh", str(restore_script)], env=restore_env, capture_output=True, text=True)
    assert res_restore.returncode == 0, f"restore.sh failed: {res_restore.stderr}"
    assert restored_db.is_file()

    # Verify data integrity in restored database
    r_conn = sqlite3.connect(str(restored_db))
    rows = r_conn.execute("SELECT id, holder, balance FROM accounts ORDER BY id").fetchall()
    r_conn.close()

    assert len(rows) == 2
    assert rows[0] == (1, "Alice Corp", 1500000.50)
    assert rows[1] == (2, "Bob Logistics", 450000.25)


def test_backup_restore_checksum_tamper_detection(tmp_path: Path):
    """Tampering with backup bytes causes restore.sh to fail-closed via sha256sum verification."""
    workspace = tmp_path / "tamper_ws"
    req = _make_sqlite_request("tamper-test")
    generate_workspace(req.raw, workspace)

    backup_script = workspace / "operations" / "backup.sh"
    restore_script = workspace / "operations" / "restore.sh"

    # Create dummy database
    db = tmp_path / "tamper.db"
    c = sqlite3.connect(str(db))
    c.executescript("CREATE TABLE t (x INT); INSERT INTO t VALUES (42);")
    c.commit()
    c.close()

    db_url_file = tmp_path / "db_url.txt"
    db_url_file.write_text(f"sqlite://{db}", encoding="utf-8")

    backup_output = tmp_path / "tamper_backup.db"
    res_backup = subprocess.run(
        ["/bin/sh", str(backup_script)],
        env={**os.environ, "ELMOS_DATABASE_URL_FILE": str(db_url_file), "ELMOS_BACKUP_OUTPUT": str(backup_output)},
        capture_output=True,
    )
    assert res_backup.returncode == 0

    # Tamper with the backup file (append bytes)
    with open(backup_output, "ab") as f:
        f.write(b"CORRUPTED_TAMPER_BYTES")

    restored_db = tmp_path / "target_tamper.db"
    restore_url_file = tmp_path / "restore_url.txt"
    restore_url_file.write_text(f"sqlite://{restored_db}", encoding="utf-8")

    # Restore MUST fail
    res_restore = subprocess.run(
        ["/bin/sh", str(restore_script)],
        env={
            **os.environ,
            "ELMOS_RESTORE_DATABASE_URL_FILE": str(restore_url_file),
            "ELMOS_BACKUP_INPUT": str(backup_output),
        },
        capture_output=True,
        text=True,
    )
    assert res_restore.returncode != 0
    assert not restored_db.exists(), "Target database must not be modified when checksum validation fails"


def test_automated_sre_rollback_on_failed_migration(tmp_path: Path):
    """Simulates production SRE continuous delivery pipeline:

    Pre-migration snapshot -> Migration failure -> Automated rollback restoration.
    """
    db_file = tmp_path / "sre_prod.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE inventory (sku TEXT PRIMARY KEY, qty INTEGER);")
    conn.execute("INSERT INTO inventory VALUES ('SKU-100', 500);")
    conn.commit()
    conn.close()

    # Pre-migration snapshot
    snapshot_file = tmp_path / "pre_migration_snapshot.db"
    conn = sqlite3.connect(str(db_file))
    bck = sqlite3.connect(str(snapshot_file))
    conn.backup(bck)
    bck.close()
    conn.close()

    # Simulate risky migration that fails halfway (e.g. invalid constraint)
    m_conn = sqlite3.connect(str(db_file))
    try:
        m_conn.execute("INSERT INTO inventory VALUES ('SKU-200', 100);")
        # Fatal error: syntax error or check violation
        m_conn.execute("ALTER TABLE inventory ADD COLUMN price CHECK(price > 0);")
        m_conn.execute("INSERT INTO inventory (sku, qty, price) VALUES ('SKU-BAD', -50, -10);")
        m_conn.commit()
    except Exception:
        m_conn.rollback()
        # SRE Automated Rollback: Restore from pre-migration snapshot
        bck = sqlite3.connect(str(snapshot_file))
        bck.backup(m_conn)
        bck.close()
    finally:
        m_conn.close()

    # Verify inventory is completely consistent with pre-migration state
    v_conn = sqlite3.connect(str(db_file))
    rows = v_conn.execute("SELECT sku, qty FROM inventory").fetchall()
    v_conn.close()

    assert len(rows) == 1
    assert rows[0] == ("SKU-100", 500)

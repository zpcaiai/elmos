"""Unit tests for compliance_audit_toolkit.py."""

import json
from pathlib import Path
import pytest
from elmos_mature_platform.compliance_audit_toolkit import (
    ComplianceAuditToolkit,
    ComplianceAuditDossier,
    ComplianceMetrics,
)


def test_compliance_audit_scanning(tmp_path):
    # Setup test workspace
    (tmp_path / "pom.xml").write_text("<project></project>", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("[lock]", encoding="utf-8")
    cert_dir = tmp_path / "certification"
    cert_dir.mkdir()
    (cert_dir / "KEY_REVOCATION_NOTICE.md").write_text("# Revocation Notice", encoding="utf-8")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "USER_ACTIVITY_OBSERVABILITY.md").write_text("# Observability", encoding="utf-8")

    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "V1__init.sql").write_text("ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;", encoding="utf-8")

    toolkit = ComplianceAuditToolkit(repo_root=tmp_path)
    dossier = toolkit.evaluate_compliance()

    assert isinstance(dossier, ComplianceAuditDossier)
    assert dossier.metrics.total_controls_evaluated == 6
    assert dossier.metrics.controls_passed >= 4
    assert dossier.metrics.compliance_score_pct >= 60.0
    assert dossier.metrics.hardcoded_private_keys_count == 0
    assert dossier.metrics.append_only_audit_verified is True
    assert dossier.third_party_attestation_status == "NOT_RUN"

    # Export test
    export_file = tmp_path / "audit-dossier.json"
    toolkit.export_json(dossier, export_file)
    assert export_file.exists()
    exported_data = json.loads(export_file.read_text(encoding="utf-8"))
    assert exported_data["governance"]["third_party_attestation_status"] == "NOT_RUN"
    assert len(exported_data["evaluations"]) == 6

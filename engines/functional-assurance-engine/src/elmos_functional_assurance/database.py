"""Database Persistence for Certification Records and WORM Merkle Ledger."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping

from .domain import CertificateRecord, CertificateStatus, ConformityDecision, AssuranceLevel, ProductAssuranceLevel, SectorType


class CertificationDatabase:
    """Persistent ledger for certificates, Merkle trees, and audit trails."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self.connection = sqlite3.connect(self.db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS certificates (
                    certificate_id TEXT PRIMARY KEY,
                    subject_candidate_digest TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    assurance_level TEXT NOT NULL,
                    product_level TEXT NOT NULL,
                    sector TEXT,
                    decision TEXT NOT NULL,
                    status TEXT NOT NULL,
                    scope_description TEXT NOT NULL,
                    merkle_root_digest TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    evaluator_id TEXT NOT NULL,
                    independent_reviewer_id TEXT NOT NULL,
                    hsm_key_id TEXT NOT NULL,
                    signature_receipt TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS worm_merkle_leaves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    certificate_id TEXT NOT NULL,
                    leaf_index INTEGER NOT NULL,
                    data_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    prev_leaf_hash TEXT NOT NULL,
                    FOREIGN KEY(certificate_id) REFERENCES certificates(certificate_id)
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_certificate(self, cert: CertificateRecord) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO certificates (
                    certificate_id, subject_candidate_digest, tenant_id, project_id,
                    assurance_level, product_level, sector, decision, status,
                    scope_description, merkle_root_digest, issued_at, expires_at,
                    evaluator_id, independent_reviewer_id, hsm_key_id, signature_receipt,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cert.certificate_id,
                    cert.subject_candidate_digest,
                    cert.tenant_id,
                    cert.project_id,
                    cert.assurance_level.value,
                    cert.product_level.value,
                    cert.sector.value if cert.sector else None,
                    cert.decision.value,
                    cert.status.value,
                    cert.scope_description,
                    cert.merkle_root_digest,
                    cert.issued_at,
                    cert.expires_at,
                    cert.evaluator_id,
                    cert.independent_reviewer_id,
                    cert.hsm_key_id,
                    cert.signature_receipt,
                    json.dumps(cert.metadata),
                ),
            )

    def get_certificate(self, certificate_id: str) -> CertificateRecord | None:
        cursor = self.connection.execute(
            """
            SELECT certificate_id, subject_candidate_digest, tenant_id, project_id,
                   assurance_level, product_level, sector, decision, status,
                   scope_description, merkle_root_digest, issued_at, expires_at,
                   evaluator_id, independent_reviewer_id, hsm_key_id, signature_receipt,
                   metadata_json
            FROM certificates WHERE certificate_id = ?
            """,
            (certificate_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return CertificateRecord(
            certificate_id=row[0],
            subject_candidate_digest=row[1],
            tenant_id=row[2],
            project_id=row[3],
            assurance_level=AssuranceLevel(row[4]),
            product_level=ProductAssuranceLevel(row[5]),
            sector=SectorType(row[6]) if row[6] else None,
            decision=ConformityDecision(row[7]),
            status=CertificateStatus(row[8]),
            scope_description=row[9],
            merkle_root_digest=row[10],
            issued_at=row[11],
            expires_at=row[12],
            evaluator_id=row[13],
            independent_reviewer_id=row[14],
            hsm_key_id=row[15],
            signature_receipt=row[16],
            metadata=json.loads(row[17]),
        )

    def close(self) -> None:
        self.connection.close()

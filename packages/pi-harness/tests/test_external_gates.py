from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from elmos_pi_harness.canonical import digest_bytes
from elmos_pi_harness.cli import main as cli_main
from elmos_pi_harness.external_gates import (
    GATE_IDS,
    ExternalGateLedger,
    GateExecution,
    QualificationTrustStore,
    ReleaseCandidate,
)
from elmos_pi_harness.independent_verifier import (
    EvidenceStatement,
    IndependentVerifierSigner,
    TrustedVerifier,
)
from elmos_pi_harness.models import ConflictError, PolicyDeniedError
from elmos_pi_harness.production import ExactTarget


NOW = datetime(2026, 8, 28, 5, 0, tzinfo=timezone.utc)
STARTED = "2026-08-28T04:00:00Z"
COMPLETED = "2026-08-28T04:05:00Z"
ISSUED = "2026-08-28T04:10:00Z"
EXPIRES = "2026-08-29T04:10:00Z"


def uid() -> str:
    return str(uuid.uuid4())


class FakeEd25519:
    @staticmethod
    def sign_with_private_key(private_key: bytes, payload: bytes) -> bytes:
        return hashlib.sha256(private_key + payload).digest()

    @staticmethod
    def verify(public_key: bytes, signature: bytes, payload: bytes) -> None:
        if signature != hashlib.sha256(public_key + payload).digest():
            raise ValueError("invalid signature")


class LedgerFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.release = ReleaseCandidate(
            release_id=uid(),
            source_git_sha="a" * 40,
            package_version="5.1.0",
            source_archive_digest="sha256:" + "b" * 64,
            artifact_digests={"wheel": "sha256:" + "c" * 64},
            implementation_trust_domain="engineering.example",
            created_at="2026-08-28T03:00:00Z",
            frozen_by="release-manager@example",
            limitations=("external systems are independently administered",),
        )
        self.ledger = ExternalGateLedger.initialize(root / "ledger", self.release)
        self.raw = root / "raw-evidence.log"
        self.raw.write_bytes(b"external native output\n")
        self.raw_digest = digest_bytes(self.raw.read_bytes())
        self.backend = FakeEd25519()
        self.independent_signer = IndependentVerifierSigner(
            verifier_id="independent-verifier",
            trust_domain="audit.example",
            key_id="audit-key",
            private_key=b"i" * 32,
            backend=self.backend,
        )
        self.acceptance_signer = IndependentVerifierSigner(
            verifier_id="acceptance-authority",
            trust_domain="acceptance.example",
            key_id="acceptance-key",
            private_key=b"a" * 32,
            backend=self.backend,
        )
        self.customer_signer = IndependentVerifierSigner(
            verifier_id="customer-authority",
            trust_domain="customer.example",
            key_id="customer-key",
            private_key=b"c" * 32,
            backend=self.backend,
        )
        self.release_signer = IndependentVerifierSigner(
            verifier_id="release-authority",
            trust_domain="release.example",
            key_id="release-key",
            private_key=b"r" * 32,
            backend=self.backend,
        )
        verification_scopes = {f"external_gate:{gate}" for gate in GATE_IDS}
        acceptance_scopes = {
            f"external_gate_acceptance:{gate}"
            for gate in GATE_IDS
            if gate not in {"P1-G07", "P0-G08"}
        }
        trusted = (
            TrustedVerifier(
                "independent-verifier",
                "audit.example",
                "audit-key",
                b"i" * 32,
                "2026-08-27T00:00:00Z",
                "2026-09-30T00:00:00Z",
                allowed_scopes=frozenset(verification_scopes),
            ),
            TrustedVerifier(
                "acceptance-authority",
                "acceptance.example",
                "acceptance-key",
                b"a" * 32,
                "2026-08-27T00:00:00Z",
                "2026-09-30T00:00:00Z",
                allowed_scopes=frozenset(acceptance_scopes),
            ),
            TrustedVerifier(
                "customer-authority",
                "customer.example",
                "customer-key",
                b"c" * 32,
                "2026-08-27T00:00:00Z",
                "2026-09-30T00:00:00Z",
                allowed_scopes=frozenset({"external_gate_acceptance:P1-G07"}),
            ),
            TrustedVerifier(
                "release-authority",
                "release.example",
                "release-key",
                b"r" * 32,
                "2026-08-27T00:00:00Z",
                "2026-09-30T00:00:00Z",
                allowed_scopes=frozenset({"external_gate_acceptance:P0-G08"}),
            ),
        )
        self.trust = QualificationTrustStore(
            trusted,
            {
                ("independent-verifier", "audit-key"): frozenset(
                    {"independent_verifier"}
                ),
                ("acceptance-authority", "acceptance-key"): frozenset(
                    {"acceptance_authority"}
                ),
                ("customer-authority", "customer-key"): frozenset(
                    {"customer_authority"}
                ),
                ("release-authority", "release-key"): frozenset({"release_authority"}),
            },
            backend=self.backend,
        )

    def execution(
        self,
        gap_id: str = "P0-G01",
        *,
        result_id: str | None = None,
        status: str = "EXECUTED",
        evidence_digest: str | None = None,
    ) -> GateExecution:
        return GateExecution(
            result_id=result_id or uid(),
            gap_id=gap_id,
            release_digest=self.release.release_digest,
            target=ExactTarget(
                "external-provider",
                "external-service",
                "1.0.0",
                "ap-southeast-1",
                "account-123",
                "staging",
            ),
            authorization_id=f"AUTH-{gap_id}",
            executor_id="external-runner",
            producer_trust_domain="engineering.example",
            environment_digest="sha256:" + "d" * 64,
            started_at=STARTED,
            completed_at=COMPLETED,
            raw_evidence_digests=(evidence_digest or self.raw_digest,),
            replay_reference=f"runbook://pi-harness/{gap_id}",
            status=status,
            certified=False,
            limitations=(),
        )

    def verification_receipt(self, execution: GateExecution, verdict: str = "VERIFIED"):
        statement = EvidenceStatement(
            statement_id=uid(),
            scope=f"external_gate:{execution.gap_id}",
            producer_id=execution.executor_id,
            producer_trust_domain=execution.producer_trust_domain,
            subject_digest=execution.result_digest,
            environment_digest=execution.environment_digest,
            raw_evidence_digests=execution.raw_evidence_digests,
            authorization_id=execution.authorization_id,
            executor_id=execution.executor_id,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            result="PASS",
        )
        return self.independent_signer.sign(
            statement,
            receipt_id=uid(),
            verdict=verdict,
            issued_at=ISSUED,
            expires_at=EXPIRES,
        )

    def acceptance_receipt(
        self,
        gap_id: str,
        verified_event_digest: str,
        *,
        signer: IndependentVerifierSigner | None = None,
    ):
        selected = signer or self.acceptance_signer
        statement = EvidenceStatement(
            statement_id=uid(),
            scope=f"external_gate_acceptance:{gap_id}",
            producer_id="independent-verifier",
            producer_trust_domain="audit.example",
            subject_digest=verified_event_digest,
            environment_digest="sha256:" + "d" * 64,
            raw_evidence_digests=(verified_event_digest,),
            authorization_id=f"ACCEPT-{gap_id}",
            executor_id="independent-verifier",
            started_at=ISSUED,
            completed_at=ISSUED,
            result="PASS",
        )
        return selected.sign(
            statement,
            receipt_id=uid(),
            verdict="VERIFIED",
            issued_at=ISSUED,
            expires_at=EXPIRES,
        )


class ExternalGateLedgerTests(unittest.TestCase):
    def fixture(self, temporary: str) -> LedgerFixture:
        return LedgerFixture(Path(temporary).resolve())

    def test_execution_verification_acceptance_are_distinct_and_never_certify(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-ledger-") as temporary:
            fixture = self.fixture(temporary)
            execution = fixture.execution()
            recorded = fixture.ledger.record_execution(execution, [fixture.raw])
            self.assertEqual(recorded["status"], "EXECUTED")
            self.assertFalse(recorded["certified"])

            verified = fixture.ledger.verify_execution(
                fixture.verification_receipt(execution), fixture.trust, now=NOW
            )
            self.assertEqual(verified["status"], "INDEPENDENTLY_VERIFIED")
            unsigned_status = fixture.ledger.status()
            self.assertEqual(unsigned_status["receipt_revalidation"], "NOT_RUN")
            self.assertEqual(unsigned_status["qualification_decision"], "BLOCKED")

            accepted = fixture.ledger.accept_gate(
                fixture.acceptance_receipt("P0-G01", verified["event_digest"]),
                fixture.trust,
                now=NOW,
            )
            self.assertEqual(accepted["status"], "ACCEPTED")
            status = fixture.ledger.status(trust_store=fixture.trust, now=NOW)
            row = next(item for item in status["gaps"] if item["gap_id"] == "P0-G01")
            self.assertEqual(row["external_evidence"], "ACCEPTED")
            self.assertEqual(status["receipt_revalidation"], "PASS")
            self.assertEqual(status["certification"], "NOT_CERTIFIED")
            self.assertFalse(status["certified"])

    def test_event_and_evidence_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-ledger-") as temporary:
            fixture = self.fixture(temporary)
            execution = fixture.execution()
            recorded = fixture.ledger.record_execution(execution, [fixture.raw])
            object_path = Path(recorded["objects"][0]["object"])
            object_path.write_bytes(b"tampered")
            with self.assertRaises(PolicyDeniedError):
                fixture.ledger.status()

        with tempfile.TemporaryDirectory(prefix="pi-ledger-") as temporary:
            fixture = self.fixture(temporary)
            fixture.ledger.record_execution(fixture.execution(), [fixture.raw])
            event_path = next((fixture.root / "ledger" / "events").iterdir())
            raw = event_path.read_bytes()
            event_path.write_bytes(raw.replace(b'"EXECUTED"', b'"UNKNOWN"'))
            with self.assertRaises(PolicyDeniedError):
                fixture.ledger.status()

    def test_wrong_release_digest_symlink_and_mismatched_evidence_are_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-ledger-") as temporary:
            fixture = self.fixture(temporary)
            wrong = fixture.execution(evidence_digest="sha256:" + "f" * 64)
            with self.assertRaises(PolicyDeniedError):
                fixture.ledger.record_execution(wrong, [fixture.raw])
            self.assertEqual(fixture.ledger.status()["event_count"], 0)
            self.assertEqual(
                list((fixture.root / "ledger" / "objects" / "sha256").iterdir()), []
            )

            symlink = fixture.root / "raw-link.log"
            os.symlink(fixture.raw, symlink)
            with self.assertRaises(PolicyDeniedError):
                fixture.ledger.record_execution(fixture.execution(), [symlink])

            execution = fixture.execution()
            object.__setattr__(execution, "release_digest", "sha256:" + "e" * 64)
            with self.assertRaises(PolicyDeniedError):
                fixture.ledger.record_execution(execution, [fixture.raw])

    def test_execution_and_receipt_time_ordering_and_role_scopes_fail_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-ledger-") as temporary:
            fixture = self.fixture(temporary)
            predates_release = replace(
                fixture.execution(),
                started_at="2026-08-28T02:59:00Z",
                completed_at="2026-08-28T03:01:00Z",
            )
            with self.assertRaises(PolicyDeniedError):
                fixture.ledger.record_execution(
                    predates_release, [fixture.raw], now=NOW
                )

            future = replace(
                fixture.execution(),
                started_at=(NOW + timedelta(minutes=9)).isoformat(),
                completed_at=(NOW + timedelta(minutes=10)).isoformat(),
            )
            with self.assertRaises(PolicyDeniedError):
                fixture.ledger.record_execution(future, [fixture.raw], now=NOW)

            execution = fixture.execution()
            statement = EvidenceStatement(
                statement_id=uid(),
                scope="external_gate:P0-G01",
                producer_id=execution.executor_id,
                producer_trust_domain=execution.producer_trust_domain,
                subject_digest=execution.result_digest,
                environment_digest=execution.environment_digest,
                raw_evidence_digests=execution.raw_evidence_digests,
                authorization_id=execution.authorization_id,
                executor_id=execution.executor_id,
                started_at=execution.started_at,
                completed_at=execution.completed_at,
                result="PASS",
            )
            with self.assertRaises(ValueError):
                fixture.independent_signer.sign(
                    statement,
                    receipt_id=uid(),
                    verdict="VERIFIED",
                    issued_at=STARTED,
                    expires_at=EXPIRES,
                )

            mixed_scope = TrustedVerifier(
                "mixed-verifier",
                "mixed.example",
                "mixed-key",
                b"m" * 32,
                "2026-08-27T00:00:00Z",
                "2026-09-30T00:00:00Z",
                allowed_scopes=frozenset(
                    {
                        "external_gate:P0-G01",
                        "external_gate_acceptance:P0-G01",
                    }
                ),
            )
            with self.assertRaises(ValueError):
                QualificationTrustStore(
                    (mixed_scope,),
                    {
                        ("mixed-verifier", "mixed-key"): frozenset(
                            {"independent_verifier"}
                        )
                    },
                    backend=fixture.backend,
                )

    def test_replay_is_idempotent_but_id_reuse_with_different_content_conflicts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-ledger-") as temporary:
            fixture = self.fixture(temporary)
            result_id = uid()
            execution = fixture.execution(result_id=result_id)
            first = fixture.ledger.record_execution(execution, [fixture.raw])
            second = fixture.ledger.record_execution(execution, [fixture.raw])
            self.assertFalse(first["replayed"])
            self.assertTrue(second["replayed"])
            changed = fixture.execution(result_id=result_id, status="FAILED")
            with self.assertRaises(ConflictError):
                fixture.ledger.record_execution(changed, [fixture.raw])

            receipt = fixture.verification_receipt(execution)
            first_verification = fixture.ledger.verify_execution(
                receipt, fixture.trust, now=NOW
            )
            replay = fixture.ledger.verify_execution(receipt, fixture.trust, now=NOW)
            self.assertFalse(first_verification["replayed"])
            self.assertTrue(replay["replayed"])

    def test_rejected_or_inconclusive_receipt_never_passes(self) -> None:
        for verdict, expected in (("REJECTED", "FAILED"), ("INCONCLUSIVE", "UNKNOWN")):
            with (
                self.subTest(verdict=verdict),
                tempfile.TemporaryDirectory(prefix="pi-ledger-") as temporary,
            ):
                fixture = self.fixture(temporary)
                execution = fixture.execution()
                fixture.ledger.record_execution(execution, [fixture.raw])
                result = fixture.ledger.verify_execution(
                    fixture.verification_receipt(execution, verdict),
                    fixture.trust,
                    now=NOW,
                )
                self.assertEqual(result["status"], expected)
                status = fixture.ledger.status(trust_store=fixture.trust, now=NOW)
                self.assertEqual(status["qualification_decision"], "BLOCKED")
                self.assertFalse(status["certified"])

    def test_live_revalidation_blocks_expired_or_revoked_verifier_keys(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-ledger-") as temporary:
            fixture = self.fixture(temporary)
            execution = fixture.execution()
            fixture.ledger.record_execution(execution, [fixture.raw])
            fixture.ledger.verify_execution(
                fixture.verification_receipt(execution), fixture.trust, now=NOW
            )

            expired = fixture.ledger.status(
                trust_store=fixture.trust,
                now=datetime(2026, 10, 1, tzinfo=timezone.utc),
            )
            self.assertEqual(expired["receipt_revalidation"], "FAILED")
            self.assertEqual(expired["qualification_decision"], "BLOCKED")

            revoked_verifiers = (
                replace(fixture.trust.verifiers[0], revoked=True),
                *fixture.trust.verifiers[1:],
            )
            revoked_trust = QualificationTrustStore(
                revoked_verifiers,
                fixture.trust.roles,
                backend=fixture.backend,
            )
            revoked = fixture.ledger.status(trust_store=revoked_trust, now=NOW)
            self.assertEqual(revoked["receipt_revalidation"], "FAILED")
            self.assertEqual(revoked["qualification_decision"], "BLOCKED")

    def test_customer_and_release_gates_require_exact_authority_roles(self) -> None:
        cases = (
            ("P1-G07", "customer_signer"),
            ("P0-G08", "release_signer"),
        )
        for gap_id, signer_name in cases:
            with (
                self.subTest(gap_id=gap_id),
                tempfile.TemporaryDirectory(prefix="pi-ledger-") as temporary,
            ):
                fixture = self.fixture(temporary)
                execution = fixture.execution(gap_id)
                fixture.ledger.record_execution(execution, [fixture.raw])
                verified = fixture.ledger.verify_execution(
                    fixture.verification_receipt(execution), fixture.trust, now=NOW
                )
                wrong = fixture.acceptance_receipt(gap_id, verified["event_digest"])
                with self.assertRaises(PolicyDeniedError):
                    fixture.ledger.accept_gate(wrong, fixture.trust, now=NOW)
                signer = getattr(fixture, signer_name)
                accepted = fixture.ledger.accept_gate(
                    fixture.acceptance_receipt(
                        gap_id, verified["event_digest"], signer=signer
                    ),
                    fixture.trust,
                    now=NOW,
                )
                self.assertEqual(accepted["status"], "ACCEPTED")

    def test_all_eight_gates_reach_only_ready_for_human_decision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-ledger-") as temporary:
            fixture = self.fixture(temporary)
            for gap_id in GATE_IDS:
                execution = fixture.execution(gap_id)
                fixture.ledger.record_execution(execution, [fixture.raw])
                verified = fixture.ledger.verify_execution(
                    fixture.verification_receipt(execution), fixture.trust, now=NOW
                )
                if gap_id in {"P1-G07", "P0-G08"}:
                    signer = (
                        fixture.customer_signer
                        if gap_id == "P1-G07"
                        else fixture.release_signer
                    )
                    fixture.ledger.accept_gate(
                        fixture.acceptance_receipt(
                            gap_id, verified["event_digest"], signer=signer
                        ),
                        fixture.trust,
                        now=NOW,
                    )
            status = fixture.ledger.status(trust_store=fixture.trust, now=NOW)
            self.assertEqual(
                status["qualification_decision"], "READY_FOR_HUMAN_DECISION"
            )
            self.assertEqual(status["certification"], "NOT_CERTIFIED")
            self.assertFalse(status["certified"])
            self.assertEqual(
                status["blockers"],
                ["external_production_certification_authority_required"],
            )

    def test_operator_cli_initializes_records_and_audits_absolute_inputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-ledger-") as temporary:
            fixture_root = Path(temporary).resolve()
            fixture = LedgerFixture.__new__(LedgerFixture)
            fixture.root = fixture_root
            fixture.release = ReleaseCandidate(
                release_id=uid(),
                source_git_sha="a" * 40,
                package_version="5.1.0",
                source_archive_digest="sha256:" + "b" * 64,
                artifact_digests={"wheel": "sha256:" + "c" * 64},
                implementation_trust_domain="engineering.example",
                created_at="2026-08-28T03:00:00Z",
                frozen_by="release-manager@example",
            )
            release_path = fixture_root / "release-input.json"
            release_path.write_text(
                json.dumps(fixture.release.to_dict()), encoding="utf-8"
            )
            ledger_path = fixture_root / "cli-ledger"
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(io.StringIO()):
                code = cli_main(
                    [
                        "qualification-init",
                        "--ledger-root",
                        str(ledger_path),
                        "--release-manifest",
                        str(release_path),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "INITIALIZED")

            raw_path = fixture_root / "cli-raw.log"
            raw_path.write_bytes(b"external CLI evidence\n")
            execution = GateExecution(
                result_id=uid(),
                gap_id="P0-G01",
                release_digest=fixture.release.release_digest,
                target=ExactTarget(
                    "provider", "postgresql", "17.5", "region", "account", "staging"
                ),
                authorization_id="AUTH-CLI",
                executor_id="external-runner",
                producer_trust_domain="engineering.example",
                environment_digest="sha256:" + "d" * 64,
                started_at=STARTED,
                completed_at=COMPLETED,
                raw_evidence_digests=(digest_bytes(raw_path.read_bytes()),),
                replay_reference="runbook://pi-harness/P0-G01",
                status="EXECUTED",
            )
            result_path = fixture_root / "result-input.json"
            result_path.write_text(json.dumps(execution.to_dict()), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(io.StringIO()):
                code = cli_main(
                    [
                        "qualification-record",
                        "--ledger-root",
                        str(ledger_path),
                        "--result",
                        str(result_path),
                        "--raw-evidence",
                        str(raw_path),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "EXECUTED")

            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(io.StringIO()):
                code = cli_main(
                    ["qualification-status", "--ledger-root", str(ledger_path)]
                )
            status = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(status["gaps"][0]["external_evidence"], "EXECUTED")
            self.assertEqual(status["certification"], "NOT_CERTIFIED")
            self.assertFalse(status["certified"])


if __name__ == "__main__":
    unittest.main()

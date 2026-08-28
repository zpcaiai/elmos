"""Conservative local readiness and externally signed certification.

Local code can emit at most ``READY_FOR_EXTERNAL_GATE``.  Promotion to an
external state requires (1) an already-ready immutable local assessment, (2) a
tenant/project/payload-bound receipt from an independent asymmetric signer and
(3) successful verification through a preconfigured external trust provider.
The receipt's boolean fields are never treated as signature verification.
"""

from __future__ import annotations

import base64
import hmac
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterable, Mapping, Protocol

from .canonical import canonical_json_bytes, digest_object, require_sha256_digest
from .contracts import (
    CertificationStatus,
    CompletionCertificate,
    GateDecision,
    GateResult,
    RevisionSet,
    SecurityContext,
    utc_now,
)
from .errors import CertificationError, IntegrityError, NotFoundError, ValidationError
from .evidence import EvidenceService
from .proof_graph import ProofObligationGraph
from .storage import StorageReadiness


_ASYMMETRIC_ALGORITHMS = frozenset({"Ed25519", "ECDSA-P256-SHA256", "RSA-PSS-SHA256", "X509-REMOTE"})


@dataclass(frozen=True, slots=True)
class ExternalSignatureReceipt:
    receipt_id: str
    tenant_id: str
    project_id: str
    payload_sha256: str
    signer_identity: str
    key_id: str
    provider_id: str
    algorithm: str
    signature_base64: str
    verification_evidence_id: str
    issued_at: datetime
    expires_at: datetime
    independent: bool
    certification_authority: bool = False
    attested_status: CertificationStatus = CertificationStatus.EXTERNALLY_VERIFIED

    def __post_init__(self) -> None:
        if not all(
            (
                self.receipt_id,
                self.tenant_id,
                self.project_id,
                self.signer_identity,
                self.key_id,
                self.provider_id,
                self.verification_evidence_id,
            )
        ):
            raise ValidationError("external signature receipt bindings are incomplete")
        require_sha256_digest(self.payload_sha256, field="payload_sha256")
        if self.algorithm not in _ASYMMETRIC_ALGORITHMS:
            raise ValidationError("external signature algorithm is not approved")
        if self.attested_status not in {CertificationStatus.EXTERNALLY_VERIFIED, CertificationStatus.CERTIFIED}:
            raise ValidationError("external receipt attested status is invalid")
        if self.attested_status is CertificationStatus.CERTIFIED and not self.certification_authority:
            raise ValidationError("certified receipt requires certification authority scope")
        if (
            self.issued_at.tzinfo is None
            or self.issued_at.utcoffset() is None
            or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
            or self.issued_at >= self.expires_at
        ):
            raise ValidationError("external signature receipt validity is invalid")
        try:
            signature = base64.b64decode(self.signature_base64, validate=True)
        except Exception as exc:
            raise ValidationError("external signature is not valid base64") from exc
        if len(signature) < 32:
            raise ValidationError("external signature is implausibly short")

    def signature_bytes(self) -> bytes:
        return base64.b64decode(self.signature_base64, validate=True)

    def signed_payload(self, *, certificate_id: str) -> bytes:
        """Return all security-relevant claims covered by the signature."""

        return canonical_json_bytes(
            {
                "receipt_id": self.receipt_id,
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "payload_sha256": self.payload_sha256,
                "certificate_id": certificate_id,
                "signer_identity": self.signer_identity,
                "key_id": self.key_id,
                "provider_id": self.provider_id,
                "algorithm": self.algorithm,
                "verification_evidence_id": self.verification_evidence_id,
                "issued_at": self.issued_at,
                "expires_at": self.expires_at,
                "independent": self.independent,
                "certification_authority": self.certification_authority,
                "attested_status": self.attested_status,
            }
        )


class TrustedExternalSignatureVerifier(Protocol):
    """Adapter backed by a configured PKI/KMS/transparency trust service."""

    provider_id: str
    trust_anchor_sha256: str
    external: bool
    asymmetric: bool

    def verify(
        self,
        payload: bytes,
        signature: bytes,
        *,
        algorithm: str,
        key_id: str,
        signer_identity: str,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class TrustedVerifierRegistration:
    """Application-configured trust binding, never supplied per request."""

    provider_id: str
    trust_anchor_sha256: str
    allowed_key_ids: frozenset[str]
    allowed_signer_identities: frozenset[str]
    verifier: TrustedExternalSignatureVerifier

    def __post_init__(self) -> None:
        if not self.provider_id or not self.allowed_key_ids or not self.allowed_signer_identities:
            raise ValidationError("trusted verifier registration is incomplete")
        require_sha256_digest(self.trust_anchor_sha256, field="trust_anchor_sha256")
        if (
            not getattr(self.verifier, "external", False)
            or not getattr(self.verifier, "asymmetric", False)
            or getattr(self.verifier, "provider_id", None) != self.provider_id
            or getattr(self.verifier, "trust_anchor_sha256", None) != self.trust_anchor_sha256
        ):
            raise ValidationError("verifier adapter does not match its trusted registration")


class CertificationRepository(Protocol):
    """Durable trust bridge used by production certification.

    The repository is deliberately separate from the ordinary runtime Store:
    its PostgreSQL connection must use a least-privileged independent certifier
    role.  Local assessments, their exact canonical payload bytes, and external
    decisions are committed transactionally.  A missing repository is valid
    only for bounded local engineering and can never manufacture durable trust.
    """

    def readiness(self) -> StorageReadiness: ...

    def save_local(
        self,
        context: SecurityContext,
        certificate: CompletionCertificate,
        *,
        payload_bytes: bytes,
        revision_set_bytes: bytes,
        proof_graph_bytes: bytes,
    ) -> CompletionCertificate: ...

    def load_local(
        self,
        context: SecurityContext,
        payload_digest: str,
    ) -> CompletionCertificate | None: ...

    def save_external(
        self,
        context: SecurityContext,
        local: CompletionCertificate,
        receipt: ExternalSignatureReceipt,
        certificate: CompletionCertificate,
        *,
        signed_payload_bytes: bytes,
        trust_anchor_sha256: str,
    ) -> CompletionCertificate: ...

    def load_effective(
        self,
        context: SecurityContext,
        payload_digest: str,
        *,
        now: datetime | None = None,
    ) -> CompletionCertificate | None: ...

    def revoke_external(
        self,
        context: SecurityContext,
        receipt_id: str,
        *,
        reason: str,
        revocation_id: str | None = None,
        now: datetime | None = None,
    ) -> str: ...


class CertificationService:
    REQUIRED_LOCAL_GATES = frozenset({"E0", "E1", "E2", "E3", "E4"})
    REQUIRED_PRODUCTION_GATES = frozenset(
        {"P05", "E0", "E1", "E2", "E3", "E4", "E5"}
    )

    def __init__(
        self,
        evidence: EvidenceService,
        *,
        trusted_verifiers: Iterable[TrustedVerifierRegistration] = (),
        repository: CertificationRepository | None = None,
    ) -> None:
        self._evidence = evidence
        registrations = tuple(trusted_verifiers)
        self._trusted_verifiers = {item.provider_id: item for item in registrations}
        if len(self._trusted_verifiers) != len(registrations):
            raise ValidationError("trusted verifier provider ids must be unique")
        self._issued_local: dict[str, CompletionCertificate] = {}
        self._repository = repository
        self._lock = threading.RLock()

    def evaluate_local(
        self,
        context: SecurityContext,
        *,
        goal_id: str,
        revision_set: RevisionSet,
        graph: ProofObligationGraph,
        gates: Iterable[GateResult],
        evidence_ids: Iterable[str],
        certified_envelope: Mapping[str, object],
        independent_verifier_identity: str,
        production: bool = False,
        run_id: str | None = None,
        unsettled_side_effects: int = 0,
        now: datetime | None = None,
    ) -> CompletionCertificate:
        current_time = now or utc_now()
        bound_run_id = run_id or context.run_id
        if production and bound_run_id is None:
            raise ValidationError(
                "production assessment requires an exact run id",
                code="CERTIFICATION_RUN_REQUIRED",
            )
        if self._repository is not None and bound_run_id is None:
            raise CertificationError(
                "durable certification requires an exact run id",
                code="CERTIFICATION_RUN_REQUIRED",
            )
        blockers: list[str] = []
        failures: list[str] = []
        if (revision_set.tenant_id, revision_set.project_id, revision_set.goal_id) != (
            context.tenant_id,
            context.project_id,
            goal_id,
        ):
            blockers.append("revision set is not bound to the authenticated scope")
        if (graph.tenant_id, graph.project_id, graph.goal_id) != (context.tenant_id, context.project_id, goal_id):
            blockers.append("proof graph is not bound to the authenticated scope")
        if not revision_set.is_complete():
            blockers.append("revision set is incomplete")
        if not independent_verifier_identity or independent_verifier_identity == context.actor_id:
            blockers.append("an independent verifier identity is required")
        if graph.refutations():
            failures.append("refuted proof obligations exist")
        if not graph.all_critical_closed():
            blockers.append("critical proof obligations remain unclosed")
        if unsettled_side_effects != 0:
            blockers.append("external side effects are not reconciled")
        gate_items = tuple(gates)
        gate_map = {item.gate: item for item in gate_items}
        if len(gate_map) != len(gate_items):
            blockers.append("gate ids are duplicated")
        required = set(
            self.REQUIRED_PRODUCTION_GATES
            if production
            else self.REQUIRED_LOCAL_GATES
        )
        supplied_gate_names = set(gate_map)
        if supplied_gate_names != required:
            unexpected = sorted(supplied_gate_names - required)
            if unexpected:
                blockers.append(f"unexpected gates are present: {','.join(unexpected)}")
        for gate in sorted(required):
            result = gate_map.get(gate)
            if result is None:
                blockers.append(f"gate {gate} is NOT_RUN")
            elif result.decision is GateDecision.FAIL:
                failures.append(f"gate {gate} failed")
            elif result.decision is not GateDecision.PASS:
                blockers.append(f"gate {gate} is {result.decision.value}")
        envelope = dict(certified_envelope)
        if set(envelope) != {"name", "version", "scope", "assumptions"}:
            blockers.append("certified envelope fields do not match the exact contract")
        elif (
            not isinstance(envelope["name"], str)
            or not envelope["name"]
            or not isinstance(envelope["version"], str)
            or not envelope["version"]
            or not isinstance(envelope["scope"], (list, tuple))
            or not envelope["scope"]
            or any(
                not isinstance(item, str) or not item
                for item in envelope["scope"]
            )
            or len(set(envelope["scope"])) != len(envelope["scope"])
            or not isinstance(envelope["assumptions"], (list, tuple))
            or any(
                not isinstance(item, str) or not item
                for item in envelope["assumptions"]
            )
            or len(set(envelope["assumptions"]))
            != len(envelope["assumptions"])
        ):
            blockers.append("certified envelope is incomplete")
        selected_evidence_ids = tuple(evidence_ids)
        required_gate_evidence = {
            evidence_id
            for gate_name in required
            for result in (gate_map.get(gate_name),)
            if result is not None and result.decision is GateDecision.PASS
            for evidence_id in result.evidence_ids
        }
        if not required_gate_evidence.issubset(set(selected_evidence_ids)):
            blockers.append("passing gate evidence is not included in the sealed bundle")
        graph_evidence_ids = set(graph.evidence_ids)
        if not graph_evidence_ids.issubset(set(selected_evidence_ids)):
            blockers.append("proof graph evidence is not included in the sealed bundle")
        try:
            records = self._evidence.fresh_records(context, selected_evidence_ids, now=current_time)
            bundle = self._evidence.seal(context, selected_evidence_ids, now=current_time)
            evidence_root = bundle.root_sha256
            if not any(
                record.actor_id == independent_verifier_identity
                and record.producer.independent
                and record.producer.source in {"VERIFIER", "CERTIFIER"}
                for record in records
            ):
                blockers.append("independent verifier identity is not bound to fresh verifier evidence")
        except (IntegrityError, NotFoundError, ValidationError) as exc:
            blockers.append(f"evidence bundle is invalid: {exc.code}")
            # Stable non-empty sentinel allows a structured blocked result while
            # making the missing evidence explicit in payload and status.
            evidence_root = digest_object(
                {"tenant_id": context.tenant_id, "project_id": context.project_id, "state": "INVALID_EVIDENCE"},
                domain="blocked-evidence-root",
            )
        status = (
            CertificationStatus.FAILED_ASSURANCE
            if failures
            else CertificationStatus.BLOCKED
            if blockers
            else CertificationStatus.READY_FOR_EXTERNAL_GATE
        )
        revision_set_revisions = revision_set.revisions()
        revision_set_state = {
            "revision_set_id": revision_set.revision_set_id,
            "tenant_id": revision_set.tenant_id,
            "project_id": revision_set.project_id,
            "goal_id": revision_set.goal_id,
            "revisions": revision_set_revisions,
        }
        revision_set_digest = digest_object(
            revision_set_state,
            domain="certification-revision-set",
        )
        proof_graph_state = {
            "graph_id": graph.graph_id,
            "tenant_id": graph.tenant_id,
            "project_id": graph.project_id,
            "goal_id": graph.goal_id,
            "obligations": graph.obligations,
            "edges": graph.edges,
            "decisions": graph.decisions,
            "evidence_ids": graph.evidence_ids,
            "status_counts": graph.status_counts(),
        }
        proof_graph_digest = digest_object(
            proof_graph_state,
            domain="proof-obligation-graph-state",
        )
        unsigned_payload = self._local_payload(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            goal_id=goal_id,
            run_id=bound_run_id,
            revision_set_id=revision_set.revision_set_id,
            revision_set_digest=revision_set_digest,
            revision_set_revisions=revision_set_revisions,
            proof_graph_digest=proof_graph_digest,
            certified_envelope=envelope,
            gate_results=gate_items,
            status_counts=graph.status_counts(),
            evidence_ids=selected_evidence_ids,
            evidence_root=evidence_root,
            status=status,
            independent_verifier_identity=independent_verifier_identity,
            issued_at=current_time,
            unresolved_risks=tuple(failures + blockers),
            production_assessment=production,
        )
        payload_digest = digest_object(unsigned_payload, domain="local-certification-assessment")
        certificate = CompletionCertificate(
            certificate_id=f"certificate-{uuid.uuid4()}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            goal_id=goal_id,
            revision_set_id=revision_set.revision_set_id,
            certified_envelope=envelope,
            gate_results=gate_items,
            status_counts=graph.status_counts(),
            evidence_root=evidence_root,
            signer_identity=independent_verifier_identity,
            signer_key_id=None,
            signer_independent=independent_verifier_identity != context.actor_id,
            issued_at=current_time,
            status=status,
            payload_digest=payload_digest,
            run_id=bound_run_id,
            revision_set_digest=revision_set_digest,
            revision_set_revisions=revision_set_revisions,
            proof_graph_digest=proof_graph_digest,
            evidence_ids=selected_evidence_ids,
            production_assessment=production,
            unresolved_risks=tuple(failures + blockers),
        )
        if self._repository is not None:
            certificate = self._repository.save_local(
                context,
                certificate,
                payload_bytes=canonical_json_bytes(unsigned_payload),
                revision_set_bytes=canonical_json_bytes(revision_set_state),
                proof_graph_bytes=canonical_json_bytes(proof_graph_state),
            )
        with self._lock:
            self._issued_local[payload_digest] = certificate
        return certificate

    def finalize_external(
        self,
        context: SecurityContext,
        local: CompletionCertificate,
        receipt: ExternalSignatureReceipt,
        *,
        requested_status: CertificationStatus = CertificationStatus.EXTERNALLY_VERIFIED,
        now: datetime | None = None,
    ) -> CompletionCertificate:
        current_time = now or utc_now()
        if requested_status not in {CertificationStatus.EXTERNALLY_VERIFIED, CertificationStatus.CERTIFIED}:
            raise CertificationError("requested external status is invalid")
        if receipt.attested_status is not requested_status:
            raise CertificationError("requested status is not signed by the receipt", code="STATUS_ATTESTATION_MISMATCH")
        if local.status is not CertificationStatus.READY_FOR_EXTERNAL_GATE:
            raise CertificationError("only a ready local assessment can be promoted", code="LOCAL_GATE_NOT_READY")
        if (local.tenant_id, local.project_id) != (context.tenant_id, context.project_id):
            raise CertificationError("local assessment scope mismatch", code="CERTIFICATE_SCOPE_MISMATCH")
        expected_local_digest = digest_object(
            self._local_payload(
                tenant_id=local.tenant_id,
                project_id=local.project_id,
                goal_id=local.goal_id,
                run_id=local.run_id,
                revision_set_id=local.revision_set_id,
                revision_set_digest=local.revision_set_digest,
                revision_set_revisions=local.revision_set_revisions,
                proof_graph_digest=local.proof_graph_digest,
                certified_envelope=local.certified_envelope,
                gate_results=local.gate_results,
                status_counts=local.status_counts,
                evidence_ids=local.evidence_ids,
                evidence_root=local.evidence_root,
                status=local.status,
                independent_verifier_identity=local.signer_identity or "",
                issued_at=local.issued_at,
                unresolved_risks=local.unresolved_risks,
                production_assessment=local.production_assessment,
            ),
            domain="local-certification-assessment",
        )
        if not hmac.compare_digest(expected_local_digest, local.payload_digest):
            raise CertificationError("local assessment payload was altered", code="LOCAL_ASSESSMENT_TAMPERED")
        with self._lock:
            issued = self._issued_local.get(local.payload_digest)
        if issued is None and self._repository is not None:
            issued = self._repository.load_local(context, local.payload_digest)
        if issued != local:
            raise CertificationError("local assessment was not issued by this gate", code="LOCAL_ASSESSMENT_UNTRUSTED")
        if local.unresolved_risks or not local.signer_independent:
            raise CertificationError("local assessment contains unresolved risk or lacks independent review")
        if (
            requested_status is CertificationStatus.CERTIFIED
            and not local.production_assessment
        ):
            raise CertificationError(
                "certification requires a production assessment with P05 and E5",
                code="PRODUCTION_ASSESSMENT_REQUIRED",
            )
        if (receipt.tenant_id, receipt.project_id, receipt.payload_sha256) != (
            local.tenant_id,
            local.project_id,
            local.payload_digest,
        ):
            raise CertificationError("signature receipt does not bind the local assessment", code="SIGNATURE_BINDING_MISMATCH")
        if not receipt.independent or receipt.signer_identity in {context.actor_id, local.signer_identity}:
            raise CertificationError("external signer is not independent", code="SIGNER_NOT_INDEPENDENT")
        if not (receipt.issued_at <= current_time < receipt.expires_at):
            raise CertificationError("external signature receipt is expired", code="SIGNATURE_RECEIPT_EXPIRED")
        if requested_status is CertificationStatus.CERTIFIED and not receipt.certification_authority:
            raise CertificationError("receipt is not issued by a certification authority", code="CERTIFICATION_AUTHORITY_REQUIRED")
        registration = self._trusted_verifiers.get(receipt.provider_id)
        if registration is None:
            raise CertificationError("trusted external asymmetric verifier is unavailable", code="EXTERNAL_VERIFIER_REQUIRED")
        if receipt.key_id not in registration.allowed_key_ids or receipt.signer_identity not in registration.allowed_signer_identities:
            raise CertificationError("external signer or key is not trusted", code="EXTERNAL_SIGNER_NOT_TRUSTED")
        signed_payload = receipt.signed_payload(certificate_id=local.certificate_id)
        try:
            valid = registration.verifier.verify(
                signed_payload,
                receipt.signature_bytes(),
                algorithm=receipt.algorithm,
                key_id=receipt.key_id,
                signer_identity=receipt.signer_identity,
            )
        except Exception as exc:
            raise CertificationError("external signature verification failed closed", code="SIGNATURE_VERIFIER_FAILED") from exc
        if valid is not True:
            raise CertificationError("external signature is invalid", code="SIGNATURE_INVALID")
        # Verification evidence must itself be fresh, byte-bound and scoped.
        verification_record, verification_bytes = self._evidence.read_verified(
            context, receipt.verification_evidence_id, now=current_time
        )
        if verification_bytes != canonical_json_bytes(receipt):
            raise CertificationError("signature receipt bytes do not match verification evidence")
        if (
            not verification_record.producer.independent
            or verification_record.producer.source != "CERTIFIER"
            or verification_record.producer.tool_name != receipt.provider_id
            or verification_record.evidence_class != "external-signature"
            or verification_record.subject_revision != local.payload_digest
        ):
            raise CertificationError("signature verification evidence is not independently bound")
        receipt_sha256 = digest_object(receipt, domain="external-signature-receipt")
        certificate = replace(
            local,
            signer_identity=receipt.signer_identity,
            signer_key_id=receipt.key_id,
            signer_independent=True,
            issued_at=current_time,
            status=requested_status,
            signature_receipt_id=receipt.receipt_id,
            signature_receipt_sha256=receipt_sha256,
        )
        if self._repository is not None:
            certificate = self._repository.save_external(
                context,
                local,
                receipt,
                certificate,
                signed_payload_bytes=signed_payload,
                trust_anchor_sha256=registration.trust_anchor_sha256,
            )
        return certificate

    @staticmethod
    def _local_payload(
        *,
        tenant_id: str,
        project_id: str,
        goal_id: str,
        run_id: str | None,
        revision_set_id: str,
        revision_set_digest: str,
        revision_set_revisions: Mapping[str, str],
        proof_graph_digest: str,
        certified_envelope: Mapping[str, object],
        gate_results: Iterable[GateResult],
        status_counts: Mapping[str, int],
        evidence_ids: Iterable[str],
        evidence_root: str,
        status: CertificationStatus,
        independent_verifier_identity: str,
        issued_at: datetime,
        unresolved_risks: tuple[str, ...],
        production_assessment: bool,
    ) -> dict[str, object]:
        return {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "goal_id": goal_id,
            "run_id": run_id,
            "revision_set_id": revision_set_id,
            "revision_set_digest": revision_set_digest,
            "revision_set_revisions": dict(revision_set_revisions),
            "proof_graph_digest": proof_graph_digest,
            "certified_envelope": dict(certified_envelope),
            "gate_results": tuple(gate_results),
            "status_counts": dict(status_counts),
            "evidence_ids": tuple(evidence_ids),
            "evidence_root": evidence_root,
            "local_status": status,
            "independent_verifier_identity": independent_verifier_identity,
            "issued_at": issued_at,
            "unresolved_risks": unresolved_risks,
            "production_assessment": production_assessment,
        }

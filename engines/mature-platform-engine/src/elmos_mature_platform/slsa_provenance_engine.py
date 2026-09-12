import hashlib
import hmac
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from elmos_mature_platform.physical.sigstore_cosign import SigstoreCosignDriver
from elmos_mature_platform.types import (
    InTotoStatement,
    ProvenanceAttestationStatus,
    SlsaLevel,
    SlsaVerificationResult,
)

SLSA_LEVEL_ORDER = {
    SlsaLevel.LEVEL_0: 0,
    SlsaLevel.LEVEL_1: 1,
    SlsaLevel.LEVEL_2: 2,
    SlsaLevel.LEVEL_3: 3,
    SlsaLevel.LEVEL_4: 4,
}


class SlsaProvenanceEngine:
    """Engine for managing SLSA Provenance and build attestations."""

    def __init__(self, sigstore_driver: Optional[SigstoreCosignDriver] = None) -> None:
        """Initialize the SlsaProvenanceEngine."""
        self._statements: Dict[str, InTotoStatement] = {}
        self._trusted_builders: Dict[str, SlsaLevel] = {}
        self._sigstore = sigstore_driver or SigstoreCosignDriver.from_env()
        self._physical_receipts: List[Dict[str, Any]] = []

    def generate_statement(self, statement: InTotoStatement) -> str:
        """Store a statement and mark it as GENERATED."""
        if not statement.statement_id:
            statement.statement_id = str(uuid.uuid4())
        
        statement.status = ProvenanceAttestationStatus.GENERATED
        statement.created_at = datetime.now(timezone.utc).isoformat()
        
        self._statements[statement.statement_id] = statement
        return statement.statement_id

    def sign_statement(self, statement_id: str, signer_key_id: str, secret_key: str) -> InTotoStatement:
        """Generate signature for the statement and update its status to SIGNED."""
        if statement_id not in self._statements:
            raise ValueError(f"Statement ID {statement_id} not found")

        statement = self._statements[statement_id]
        
        # SHA-256 HMAC of subject_name + subject_sha256 + builder_id + secret_key
        msg = f"{statement.subject_name}{statement.subject_sha256}{statement.builder_id}{secret_key}".encode("utf-8")
        signature = hmac.new(secret_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        
        statement.signature = signature
        statement.signer_key_id = signer_key_id
        statement.status = ProvenanceAttestationStatus.SIGNED
        attestation = self._sigstore.attest_artifact(
            artifact_digest=statement.subject_sha256,
            subject_name=statement.subject_name or statement.statement_id,
            builder_id=statement.builder_id,
            key_id=signer_key_id,
            signature_base64=signature,
            materialize_keys=False,
        )
        self._physical_receipts.append(attestation.to_dict())
        statement.parameters.setdefault("sigstore", attestation.to_dict())
        if attestation.rekor_uuid:
            statement.parameters["rekor_uuid"] = attestation.rekor_uuid
        
        return statement

    def verify_provenance(self, statement_id: str, current_artifact_sha256: str, target_slsa_level: SlsaLevel) -> SlsaVerificationResult:
        """Verify the provenance statement."""
        if statement_id not in self._statements:
            raise ValueError(f"Statement ID {statement_id} not found")

        statement = self._statements[statement_id]
        verification_id = str(uuid.uuid4())
        verified_at = datetime.now(timezone.utc).isoformat()
        
        result = SlsaVerificationResult(
            verification_id=verification_id,
            statement_id=statement_id,
            target_slsa_level=target_slsa_level,
            achieved_slsa_level=statement.slsa_level,
            passed=False,
            tamper_detected=False,
            verified_at=verified_at,
            violations=[],
            verification_details={}
        )

        # Digest mismatch
        if current_artifact_sha256 != statement.subject_sha256:
            result.tamper_detected = True
            result.violations.append("Digest mismatch")
            return result
        
        # Signature check
        if statement.status not in (ProvenanceAttestationStatus.SIGNED, ProvenanceAttestationStatus.VERIFIED):
            result.violations.append("Statement not signed")
        elif not statement.signature:
            result.violations.append("Missing signature")
            
        # SLSA level check
        if SLSA_LEVEL_ORDER[statement.slsa_level] < SLSA_LEVEL_ORDER[target_slsa_level]:
            result.violations.append(f"SLSA level {statement.slsa_level} does not meet target {target_slsa_level}")

        if not result.violations:
            result.passed = True
            statement.status = ProvenanceAttestationStatus.VERIFIED
            statement.verified_at = verified_at
        
        return result

    def detect_tamper(self, statement_id: str, current_artifact_sha256: str) -> bool:
        """Return True if digest mismatch."""
        if statement_id not in self._statements:
            raise ValueError(f"Statement ID {statement_id} not found")
        statement = self._statements[statement_id]
        return current_artifact_sha256 != statement.subject_sha256

    def register_trusted_builder(self, builder_id: str, max_supported_level: SlsaLevel) -> None:
        """Register a trusted builder."""
        self._trusted_builders[builder_id] = max_supported_level

    def evaluate_builder_policy(self, builder_id: str, required_level: SlsaLevel) -> Dict[str, Any]:
        """Check if builder is registered and supports required_level."""
        if builder_id not in self._trusted_builders:
            return {
                "compliant": False,
                "reason": "Builder not registered"
            }
        
        supported_level = self._trusted_builders[builder_id]
        if SLSA_LEVEL_ORDER[supported_level] >= SLSA_LEVEL_ORDER[required_level]:
            return {
                "compliant": True,
                "reason": "Builder supports required level"
            }
        
        return {
            "compliant": False,
            "reason": f"Builder level {supported_level} lower than required {required_level}"
        }

    def get_artifact_provenance_chain(self, subject_name: str) -> List[InTotoStatement]:
        """All statements for subject."""
        return [
            stmt for stmt in self._statements.values()
            if stmt.subject_name == subject_name
        ]

    def get_compliance_report(self) -> Dict[str, Any]:
        """Statements by level, status breakdown, tamper count, trusted builders count."""
        by_level = {level.value: 0 for level in SlsaLevel}
        by_status = {status.value: 0 for status in ProvenanceAttestationStatus}
        
        tamper_count = 0
        for stmt in self._statements.values():
            by_level[stmt.slsa_level.value] = by_level.get(stmt.slsa_level.value, 0) + 1
            by_status[stmt.status.value] = by_status.get(stmt.status.value, 0) + 1
            if stmt.status == ProvenanceAttestationStatus.TAMPERED:
                tamper_count += 1
                
        return {
            "statements_by_level": by_level,
            "statements_by_status": by_status,
            "tamper_count": tamper_count,
            "trusted_builders_count": len(self._trusted_builders)
        }

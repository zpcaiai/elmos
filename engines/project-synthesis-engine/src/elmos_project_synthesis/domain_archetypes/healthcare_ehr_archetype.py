"""Healthcare EHR (Electronic Health Record) Domain Archetype.

Provides HIPAA/GxP compliant clinical domain aggregates:
- PatientRecordAggregate: Encrypted patient demographics, consent status, medical MRN.
- EncounterAggregate: Clinical encounter state machine (SCHEDULED -> IN_PROGRESS -> COMPLETED -> SIGNED_OFF).
- MedicalAuditTrail: Immutable HIPAA access trail recording actor, purpose_of_use, and patient_id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class EncounterStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    SIGNED_OFF = "SIGNED_OFF"
    CANCELLED = "CANCELLED"


class ConsentStatus(str, Enum):
    GRANTED = "GRANTED"
    REVOKED = "REVOKED"
    EMERGENCY_ONLY = "EMERGENCY_ONLY"


class HealthcareDomainError(Exception):
    """Base domain error for healthcare operations."""


class HipaaConsentViolationError(HealthcareDomainError):
    """Raised when record is accessed without active patient consent."""


class InvalidEncounterTransitionError(HealthcareDomainError):
    """Raised when encounter status transition violates clinical workflows."""


@dataclass
class MedicalAuditRecord:
    audit_id: str
    tenant_id: str
    patient_id: str
    actor_id: str
    action: str
    purpose_of_use: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PatientRecordAggregate:
    patient_id: str
    tenant_id: str
    medical_record_number: str
    full_name: str
    birth_date: str
    encrypted_phi_payload: str
    consent_status: ConsentStatus = ConsentStatus.GRANTED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def revoke_consent(self) -> None:
        self.consent_status = ConsentStatus.REVOKED

    def grant_consent(self) -> None:
        self.consent_status = ConsentStatus.GRANTED

    def check_access_authorized(self, purpose_of_use: str) -> None:
        if self.consent_status == ConsentStatus.REVOKED and purpose_of_use != "EMERGENCY_TREATMENT":
            raise HipaaConsentViolationError(f"Access to patient {self.patient_id} denied: consent revoked.")


@dataclass
class EncounterAggregate:
    encounter_id: str
    tenant_id: str
    patient_id: str
    practitioner_id: str
    chief_complaint: str
    status: EncounterStatus = EncounterStatus.SCHEDULED
    diagnosis_codes: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def begin_encounter(self) -> None:
        if self.status != EncounterStatus.SCHEDULED:
            raise InvalidEncounterTransitionError(f"Cannot begin encounter in state {self.status}")
        self.status = EncounterStatus.IN_PROGRESS

    def complete_clinical_notes(self, icd10_codes: list[str]) -> None:
        if self.status != EncounterStatus.IN_PROGRESS:
            raise InvalidEncounterTransitionError(f"Cannot complete notes in state {self.status}")
        self.diagnosis_codes.extend(icd10_codes)
        self.status = EncounterStatus.COMPLETED
        self.completed_at = datetime.now(UTC)

    def sign_off(self, signing_physician_id: str) -> None:
        if self.status != EncounterStatus.COMPLETED:
            raise InvalidEncounterTransitionError(f"Cannot sign off encounter in state {self.status}")
        if not self.diagnosis_codes:
            raise HealthcareDomainError("Cannot sign off encounter without clinical diagnosis codes.")
        self.status = EncounterStatus.SIGNED_OFF

"""Tests for Enterprise Commercial Capabilities:
- Synthetic Seed Data Generator
- Postman Collection v2.1.0 and cURL Test Suite
- Healthcare EHR (HIPAA/GxP) Domain Archetype
- Industrial IoT & Smart Manufacturing Domain Archetype
- Enterprise License & Code Compliance Scanner
- End-to-end Workspace Integration
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from elmos_project_synthesis.api_debug_kit import (
    generate_curl_test_suite,
    generate_postman_collection,
    generate_synthetic_seed_data,
)
from elmos_project_synthesis.compliance_scanner import generate_compliance_audit
from elmos_project_synthesis.domain_archetypes import (
    AlertSeverity,
    AlertStatus,
    ConsentStatus,
    DeviceAggregate,
    DeviceOfflineError,
    DeviceStatus,
    EncounterAggregate,
    EncounterStatus,
    HipaaConsentViolationError,
    InvalidEncounterTransitionError,
    PatientRecordAggregate,
    TelemetrySample,
)
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SynthesisRequest
from elmos_project_synthesis.workspace import render_workspace


def _sample_request_mapping() -> dict[str, Any]:
    draft = create_draft(
        name="enterprise-nexus",
        description="Enterprise commercial platform with full lifecycle assurance",
        entities=[
            {
                "singular": "order",
                "plural": "orders",
                "fields": [
                    {"name": "customer_id", "type": "string"},
                    {"name": "order_number", "type": "string"},
                    {"name": "total_amount", "type": "number"},
                    {"name": "item_count", "type": "integer"},
                    {"name": "is_paid", "type": "boolean"},
                    {"name": "created_at", "type": "datetime"},
                ],
            },
            {
                "singular": "customer",
                "plural": "customers",
                "fields": [
                    {"name": "customer_name", "type": "string"},
                    {"name": "customer_email", "type": "string"},
                    {"name": "contact_phone", "type": "string"},
                ],
            },
        ],
        relations=[
            {
                "source": "order",
                "target": "customer",
                "kind": "many-to-one",
                "required": False,
                "source_field": "customer_id",
                "target_field": "id",
            }
        ],
        business_rules=["order.total_amount must be non-negative"],
        permissions=[
            {"actor": "admin", "resource": "order", "action": "manage", "effect": "allow"},
            {"actor": "admin", "resource": "customer", "action": "manage", "effect": "allow"},
        ],
        languages=["python"],
        project_kind="api",
        persistence="postgresql",
        auth_mode="jwt",
    )
    draft["open_questions"] = []
    return approve_request(draft, actor="sec-team")


def test_synthetic_seed_data_generation() -> None:
    request = SynthesisRequest.from_mapping(_sample_request_mapping())
    seed_data = generate_synthetic_seed_data(request)

    assert "orders" in seed_data
    assert "customers" in seed_data
    assert len(seed_data["orders"]) == 3
    assert len(seed_data["customers"]) == 3

    order = seed_data["orders"][0]
    assert order["tenant_id"] == "tenant-corp-001"
    assert order["order_number"].startswith("ORDER-CODE-")
    assert isinstance(order["total_amount"], float)
    assert isinstance(order["item_count"], int)
    assert isinstance(order["is_paid"], bool)

    customer = seed_data["customers"][0]
    assert "@enterprise.corp" in customer["customer_email"]
    assert customer["contact_phone"].startswith("+1-555-")


def test_postman_collection_generation() -> None:
    request = SynthesisRequest.from_mapping(_sample_request_mapping())
    collection = generate_postman_collection(request)

    assert "Enterprise API Collection" in collection["info"]["name"]
    assert collection["info"]["schema"] == "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"

    folders = {item["name"]: item for item in collection["item"]}
    assert "Orders Service" in folders
    assert "Customers Service" in folders

    order_requests = {req["name"]: req for req in folders["Orders Service"]["item"]}
    assert "List Orders" in order_requests
    assert "Get Order by ID" in order_requests
    assert "Create Order" in order_requests
    assert "Update Order" in order_requests
    assert "Delete Order" in order_requests

    create_req = order_requests["Create Order"]["request"]
    assert create_req["method"] == "POST"
    assert json.loads(create_req["body"]["raw"])["tenant_id"] == "tenant-corp-001"


def test_curl_test_suite_generation() -> None:
    request = SynthesisRequest.from_mapping(_sample_request_mapping())
    script = generate_curl_test_suite(request)

    assert "#!/usr/bin/env bash" in script
    assert "set -euo pipefail" in script
    assert 'BASE_URL="${1:-http://localhost:8080}"' in script
    assert "health" in script
    assert "orders" in script
    assert "customers" in script
    assert "All API Smoke Endpoints Executed Successfully" in script


def test_healthcare_ehr_domain_archetype() -> None:
    # 1. Patient Record & Consent
    patient = PatientRecordAggregate(
        patient_id="PAT-001",
        tenant_id="HOSPITAL-NORTH",
        medical_record_number="MRN-88231",
        full_name="Jane Doe",
        birth_date="1985-04-12",
        encrypted_phi_payload="ENCRYPTED_AES256_DATA",
    )
    assert patient.consent_status == ConsentStatus.GRANTED

    # Successful access authorization check
    patient.check_access_authorized(purpose_of_use="TREATMENT")

    # Revoke consent and assert access violation
    patient.revoke_consent()
    assert patient.consent_status == ConsentStatus.REVOKED
    with pytest.raises(HipaaConsentViolationError):
        patient.check_access_authorized(purpose_of_use="TREATMENT")

    # Emergency access bypasses regular revocation
    patient.check_access_authorized(purpose_of_use="EMERGENCY_TREATMENT")

    # 2. Clinical Encounter State Machine
    encounter = EncounterAggregate(
        encounter_id="ENC-501",
        tenant_id="HOSPITAL-NORTH",
        patient_id="PAT-001",
        practitioner_id="DR-SMITH",
        chief_complaint="Chest pain and shortness of breath",
    )
    assert encounter.status == EncounterStatus.SCHEDULED

    encounter.begin_encounter()
    assert encounter.status == EncounterStatus.IN_PROGRESS

    # Cannot sign off before completing notes
    with pytest.raises(InvalidEncounterTransitionError):
        encounter.sign_off("DR-SMITH")

    encounter.complete_clinical_notes(["R07.9", "R06.02"])
    assert encounter.status == EncounterStatus.COMPLETED

    encounter.sign_off("DR-SMITH")
    assert encounter.status == EncounterStatus.SIGNED_OFF


def test_iot_telemetry_domain_archetype() -> None:
    # 1. Device Lifecycle State Machine
    device = DeviceAggregate(
        device_id="DEV-TURBINE-09",
        tenant_id="PLANT-SHANGHAI",
        serial_number="SN-998821",
        model="TURBINE-X",
        firmware_version="v2.4.1",
    )
    assert device.status == DeviceStatus.OFFLINE

    sample = TelemetrySample("vibration_hz", 45.2, "Hz")

    # Offline device rejects telemetry
    with pytest.raises(DeviceOfflineError):
        device.record_telemetry(sample)

    device.connect()
    assert device.status == DeviceStatus.CONNECTED

    device.start_streaming()
    assert device.status == DeviceStatus.STREAMING

    # 2. Ingestion & Threshold Alert Triggering
    high_temp_sample = TelemetrySample("temperature_celsius", 125.0, "C")
    alert = device.record_telemetry(high_temp_sample, threshold=100.0)
    assert alert is not None
    assert alert.status == AlertStatus.TRIGGERED
    assert alert.severity == AlertSeverity.WARNING
    assert alert.triggered_value == 125.0
    assert device.status == DeviceStatus.DEGRADED

    # Alert workflow
    alert.acknowledge("OPERATOR-CHEN")
    assert alert.status == AlertStatus.ACKNOWLEDGED
    alert.resolve()
    assert alert.status == AlertStatus.RESOLVED


def test_compliance_scanner() -> None:
    request = SynthesisRequest.from_mapping(_sample_request_mapping())
    mock_files = {
        "src/app.py": "def main(): print('Hello World')\n",
        "README.md": "# Project Nexus\nLicensed under Apache-2.0\n",
    }

    audit = generate_compliance_audit(request, mock_files)
    assert audit["kind"] == "elmos.commercial-compliance-audit"
    assert audit["commercial_readiness"]["status"] == "COMPLIANT_FOR_COMMERCIAL_DELIVERY"
    assert audit["ip_provenance"]["copyleft_free"] is True
    assert len(audit["ip_provenance"]["viral_copyleft_violations"]) == 0
    assert audit["security_posture"]["hardcoded_secrets_detected"] is False
    assert audit["artifact_integrity"]["tracked_file_count"] == 2
    assert len(audit["artifact_integrity"]["workspace_merkle_sha256"]) == 64

    # Viral copyleft detection
    tainted_files = {
        "src/tainted.py": "# Released under the GNU General Public License v3\nimport os\n",
    }
    tainted_audit = generate_compliance_audit(request, tainted_files)
    assert tainted_audit["commercial_readiness"]["status"] == "NON_COMPLIANT"
    assert tainted_audit["ip_provenance"]["copyleft_free"] is False
    assert "src/tainted.py" in tainted_audit["ip_provenance"]["viral_copyleft_violations"]


def test_workspace_render_with_commercial_assets() -> None:
    request = SynthesisRequest.from_mapping(_sample_request_mapping())
    files = render_workspace(request)

    # Verify Debug Kit and Mock Data assets
    assert "requirements/seed-data.json" in files
    assert "requirements/api-collection.postman.json" in files
    assert "scripts/curl_test_suite.sh" in files

    # Verify Compliance Audit
    assert ".elmos/compliance-audit.json" in files

    seed_data = json.loads(files["requirements/seed-data.json"])
    assert "orders" in seed_data

    postman = json.loads(files["requirements/api-collection.postman.json"])
    assert "Enterprise API Collection" in postman["info"]["name"]

    compliance = json.loads(files[".elmos/compliance-audit.json"])
    assert compliance["commercial_readiness"]["status"] == "COMPLIANT_FOR_COMMERCIAL_DELIVERY"

    # Verify manifest references
    manifest = json.loads(files[".elmos/generation-manifest.json"])
    manifest_paths = {entry["path"] for entry in manifest["files"]}
    assert "requirements/seed-data.json" in manifest_paths
    assert "requirements/api-collection.postman.json" in manifest_paths
    assert "scripts/curl_test_suite.sh" in manifest_paths
    assert ".elmos/compliance-audit.json" in manifest_paths

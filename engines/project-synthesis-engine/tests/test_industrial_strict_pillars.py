"""Comprehensive unit and integration tests for the 5 Industrial Strict Pillars.

Pillars Tested:
1. Chaos Engineering, Distributed Saga Compensation & Soak Leak Auditing
2. Hardware-in-the-Loop Modbus TCP & Healthcare HL7/FHIR with 21 CFR Part 11 Audit
3. Financial Payment Gateway Sandbox, T+1 Reconciliation & Digital Tax Invoices
4. Multi-Cloud IaC Multi-AZ Topology Emitter & CIS Security Auditor
5. Third-Party Independent Audit Bundle & E4/E5 Fail-Closed Gate
"""

from __future__ import annotations

import decimal
import hashlib
import struct
from typing import Any

import pytest

from elmos_project_synthesis.chaos_resilience import (
    ChaosFaultInjector,
    ChaosFaultType,
    ChaosRule,
    DistributedSagaRecoverySimulator,
    SoakResourceLeakAuditor,
)
from elmos_project_synthesis.financial_settlement_sandbox import (
    DigitalTaxInvoiceEngine,
    MerchantPaymentGatewaySandbox,
    PaymentNotification,
    ReconciliationEngine,
    TransactionRecord,
)
from elmos_project_synthesis.hardware_in_the_loop import (
    Hl7FhirValidator,
    ModbusExceptionCode,
    ModbusTcpEmulator,
)
from elmos_project_synthesis.multicloud_iac_validator import (
    CloudTopologySpec,
    IacSecurityPolicyAuditor,
    TerraformTopologyEmitter,
)
from elmos_project_synthesis.third_party_audit_gate import (
    AuditorProofBundle,
    E4E5CertificationGate,
    ExternalAuditorAttestation,
)


def test_chaos_fault_injection_and_saga_compensation() -> None:
    injector = ChaosFaultInjector(seed=123)
    injector.add_rule(ChaosRule(
        fault_type=ChaosFaultType.CONNECTION_REFUSED,
        probability=1.0,
        target_endpoint_pattern="payment-service",
    ))

    with pytest.raises(ConnectionRefusedError, match="Chaos injected"):
        injector.execute_with_chaos("http://internal/payment-service/charge", lambda: "charged")

    # Distributed Saga with compensation
    saga = DistributedSagaRecoverySimulator()
    journal = []

    def step1_fwd() -> str:
        journal.append("order_created")
        return "order_123"

    def step1_comp() -> None:
        journal.append("order_cancelled")

    def step2_fwd() -> None:
        raise RuntimeError("Inventory reservation failed: Out of stock")

    def step2_comp() -> None:
        journal.append("inventory_released")

    saga.register_step("OrderCreation", step1_fwd, step1_comp)
    saga.register_step("InventoryReserve", step2_fwd, step2_comp)

    result = saga.execute()
    assert result["success"] is False
    assert "Inventory reservation failed" in str(result["failure_reason"])
    assert "order_created" in journal
    assert "order_cancelled" in journal
    assert "COMPENSATION_TRIGGERED" in result["journal"]


def test_soak_leak_auditor_detection() -> None:
    auditor = SoakResourceLeakAuditor()
    auditor.record_snapshot(open_handles=10, active_connections=2, memory_bytes=1000)
    auditor.record_snapshot(open_handles=15, active_connections=4, memory_bytes=2000)
    auditor.record_snapshot(open_handles=25, active_connections=8, memory_bytes=5000)

    analysis = auditor.analyze_leak_trend()
    assert analysis["leak_detected"] is True
    assert analysis["verdict"] == "LEAK_DETECTED"
    assert analysis["open_handles_delta"] == 15
    assert analysis["active_connections_delta"] == 6


def test_modbus_tcp_emulator_read_write() -> None:
    emulator = ModbusTcpEmulator(unit_id=1)

    # Write Single Register 0x06 to address 10 with value 1234
    tx_id = 1001
    write_pdu = struct.pack(">HH", 10, 1234)
    write_req = struct.pack(">HHHBB", tx_id, 0, 6, 1, 0x06) + write_pdu
    write_resp = emulator.process_request(write_req)

    # Response should echo write
    assert len(write_resp) == 12
    resp_tx, _, _, _, resp_fc, resp_addr, resp_val = struct.unpack(">HHHBBHH", write_resp)
    assert resp_tx == tx_id
    assert resp_fc == 0x06
    assert resp_addr == 10
    assert resp_val == 1234
    assert emulator.holding_registers[10] == 1234

    # Read Holding Registers 0x03 starting at address 10 for 1 count
    read_pdu = struct.pack(">HH", 10, 1)
    read_req = struct.pack(">HHHBB", 1002, 0, 6, 1, 0x03) + read_pdu
    read_resp = emulator.process_request(read_req)
    assert len(read_resp) == 11
    _, _, _, _, resp_fc, byte_count, read_val = struct.unpack(">HHHBBBH", read_resp)
    assert resp_fc == 0x03
    assert byte_count == 2
    assert read_val == 1234

    # Test error response on invalid register
    err_pdu = struct.pack(">HH", 200, 1)  # out of range (>100)
    err_req = struct.pack(">HHHBB", 1003, 0, 6, 1, 0x03) + err_pdu
    err_resp = emulator.process_request(err_req)
    _, _, _, _, err_fc, err_code = struct.unpack(">HHHBBB", err_resp)
    assert err_fc == 0x83  # 0x03 | 0x80
    assert err_code == ModbusExceptionCode.ILLEGAL_DATA_ADDRESS


def test_hl7_v2_and_fhir_r4_with_cfr21_audit() -> None:
    validator = Hl7FhirValidator()

    # 1. HL7 v2 parsing
    hl7_msg = (
        "MSH|^~\\&|HOSPITAL_A|FACILITY_1|ELMOS_EHR|FACILITY_2|20260916000000||ADT^A01|MSG0001|P|2.5\n"
        "PID|1||PAT001^^^MRN||DOE^JOHN^^^^||19800101|M\n"
    )
    parsed_hl7 = validator.parse_hl7_v2_message(hl7_msg)
    assert parsed_hl7["message_type"] == "ADT^A01"
    assert parsed_hl7["message_control_id"] == "MSG0001"
    assert "PID" in parsed_hl7["segments"]

    # 2. FHIR R4 validation
    valid_fhir = {
        "resourceType": "Patient",
        "id": "pat-001",
        "name": [{"use": "official", "family": "Doe", "given": ["John"]}],
        "gender": "male",
        "birthDate": "1980-01-01",
    }
    val_res = validator.validate_fhir_r4_patient(valid_fhir)
    assert val_res["valid"] is True
    assert len(val_res["errors"]) == 0

    # 3. 21 CFR Part 11 Hash-Chained Audit Trail
    e1 = validator.record_audit("nurse_jane", "PATIENT_VIEW", {"patient_id": "pat-001"})
    e2 = validator.record_audit("dr_smith", "VITAL_UPDATE", {"bp": "120/80"})
    assert e2.prev_hash == e1.entry_hash
    assert validator.verify_audit_chain() is True

    # Tamper test
    validator.audit_log[0].details["patient_id"] = "tampered-id"
    assert validator.verify_audit_chain() is False


def test_merchant_payment_gateway_and_reconciliation() -> None:
    gateway = MerchantPaymentGatewaySandbox(secret_key="top-secret-key-2026")

    payload: dict[str, Any] = {
        "channel": "wechat_pay",
        "out_trade_no": "ORD-2026-9901",
        "channel_trade_no": "WX-99887766",
        "amount_cents": 50000,
        "currency": "CNY",
        "timestamp": "2026-09-16T00:00:00Z",
    }
    sig = gateway.sign_payload(payload)

    notification = PaymentNotification(
        channel=str(payload["channel"]),
        out_trade_no=str(payload["out_trade_no"]),
        channel_trade_no=str(payload["channel_trade_no"]),
        amount_cents=int(payload["amount_cents"]),
        currency=str(payload["currency"]),
        timestamp=str(payload["timestamp"]),
        signature=sig,
    )

    settle_res = gateway.verify_and_settle(notification)
    assert settle_res["success"] is True
    assert settle_res["status"] == "SETTLED_COMMITTED"

    # Test idempotency on duplicate notification
    dup_res = gateway.verify_and_settle(notification)
    assert dup_res["success"] is True
    assert dup_res["status"] == "DUPLICATE_IDEMPOTENT_IGNORE"

    # Test Reconciliation Engine
    recon = ReconciliationEngine()
    internal = [
        TransactionRecord("ORD-001", decimal.Decimal("100.00")),
        TransactionRecord("ORD-002", decimal.Decimal("200.00")),
        TransactionRecord("ORD-003", decimal.Decimal("300.00")),
    ]
    channel = [
        TransactionRecord("ORD-001", decimal.Decimal("100.00")),
        TransactionRecord("ORD-002", decimal.Decimal("199.00")),  # amount mismatch
        TransactionRecord("ORD-004", decimal.Decimal("50.00")),   # missing in internal
    ]
    diff = recon.reconcile(internal, channel)
    assert diff["balanced"] is False
    assert diff["matched_count"] == 1
    assert len(diff["amount_mismatches"]) == 1
    assert diff["amount_mismatches"][0]["difference"] == "1.00"
    assert len(diff["missing_in_internal"]) == 1
    assert len(diff["missing_in_channel"]) == 1


def test_digital_tax_invoice_lifecycle() -> None:
    engine = DigitalTaxInvoiceEngine()

    invoice = engine.issue_invoice(
        invoice_number="26102000000012345678",
        buyer_tax_id="91110108MA00000001",
        seller_tax_id="91310000MA00000002",
        total_amount=decimal.Decimal("10000.00"),
        tax_rate=decimal.Decimal("0.13"),
    )
    assert invoice.tax_amount == decimal.Decimal("1300.00")
    assert invoice.status == "ISSUED"

    # Red-letter negative invoice reversal
    neg_inv = engine.reverse_with_negative_invoice(
        negative_invoice_number="26102000000099999999",
        original_invoice_number=invoice.invoice_number,
    )
    assert neg_inv.total_amount == decimal.Decimal("-10000.00")
    assert neg_inv.tax_amount == decimal.Decimal("-1300.00")
    assert neg_inv.is_negative_reversal is True
    assert engine.issued_invoices[invoice.invoice_number].status == "REVERSED"


def test_terraform_topology_emitter_and_cis_security_audit() -> None:
    emitter = TerraformTopologyEmitter()
    auditor = IacSecurityPolicyAuditor()

    spec = CloudTopologySpec(
        cloud_provider="aws",
        region="ap-northeast-1",
        availability_zones=("ap-northeast-1a", "ap-northeast-1c"),
        vpc_cidr="10.0.0.0/16",
        db_engine="postgres",
        enable_multi_az=True,
        enable_encryption=True,
    )
    hcl_files = emitter.emit_multi_az_vpc_and_db(spec)
    assert "main.tf" in hcl_files
    hcl = hcl_files["main.tf"]

    # Security check on compliant HCL
    audit_res = auditor.audit_hcl(hcl)
    assert audit_res["passed"] is True
    assert len(audit_res["violations"]) == 0

    # Insecure HCL test
    insecure_hcl = hcl.replace("publicly_accessible    = false", "publicly_accessible = true")
    insecure_audit = auditor.audit_hcl(insecure_hcl)
    assert insecure_audit["passed"] is False
    assert any("CIS-DB-001" in v for v in insecure_audit["violations"])


def test_e4_e5_fail_closed_certification_gate() -> None:
    gate = E4E5CertificationGate()

    merkle_hash = hashlib.sha256(b"workspace-merkle-root").hexdigest()
    bundle = AuditorProofBundle(
        project_name="banking-core-settlement",
        merkle_root_sha256=merkle_hash,
        sbom_sha256=hashlib.sha256(b"sbom-cyclonedx").hexdigest(),
        compliance_audit_sha256=hashlib.sha256(b"compliance-clean").hexdigest(),
        local_test_count=352,
        local_test_failures=0,
        target_level="E5",
        representative_workload_run=True,
        external_attestation=None,  # No external auditor signature!
    )

    # Must fail closed per EXECUTION INTEGRITY CONTRACT
    decision = gate.evaluate_gate(bundle)
    assert decision["production_certified"] is False
    assert decision["gate_status"] == "READY_FOR_EXTERNAL_GATE"
    assert "E5_REQUIRES_INDEPENDENT_EXTERNAL_AUDITOR_ATTESTATION" in decision["blocking_reasons"]

    # Self-attestation attempt must be explicitly banned
    self_attestation = ExternalAuditorAttestation(
        auditor_id="self-attested-builder",
        audit_firm_name="Internal Automated Agent",
        accreditation_number="SELF-001",
        issued_at="2026-09-16T00:00:00Z",
        target_workload_sha256=merkle_hash,
        signature_algorithm="RSA-SHA256",
        digital_signature="dummy-signature",
    )
    bundle_with_self = AuditorProofBundle(
        project_name="banking-core-settlement",
        merkle_root_sha256=merkle_hash,
        sbom_sha256=bundle.sbom_sha256,
        compliance_audit_sha256=bundle.compliance_audit_sha256,
        local_test_count=352,
        local_test_failures=0,
        target_level="E5",
        representative_workload_run=True,
        external_attestation=self_attestation,
    )
    decision_self = gate.evaluate_gate(bundle_with_self)
    assert decision_self["production_certified"] is False
    assert "E5_PROHIBITS_INTERNAL_OR_SELF_AUDIT_ATTESTATION" in decision_self["blocking_reasons"]

    # Valid independent third-party auditor attestation
    independent_attestation = ExternalAuditorAttestation(
        auditor_id="tuv-sud-audit-agent-8848",
        audit_firm_name="TUV SUD Global Assurance GmbH",
        accreditation_number="DAkkS-MLPS-9901",
        issued_at="2026-09-16T00:00:00Z",
        target_workload_sha256=merkle_hash,
        signature_algorithm="ECDSA-P256-SHA256",
        digital_signature="valid-external-pki-signature",
    )
    bundle_valid = AuditorProofBundle(
        project_name="banking-core-settlement",
        merkle_root_sha256=merkle_hash,
        sbom_sha256=bundle.sbom_sha256,
        compliance_audit_sha256=bundle.compliance_audit_sha256,
        local_test_count=352,
        local_test_failures=0,
        target_level="E5",
        representative_workload_run=True,
        external_attestation=independent_attestation,
    )
    decision_valid = gate.evaluate_gate(bundle_valid)
    assert decision_valid["production_certified"] is True
    assert decision_valid["gate_status"] == "CERTIFIED_E5"
    assert decision_valid["evidence_status"] == "INDEPENDENT_THIRD_PARTY_VERIFIED"

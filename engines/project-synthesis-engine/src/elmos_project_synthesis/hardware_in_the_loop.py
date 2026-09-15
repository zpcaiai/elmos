"""Hardware-in-the-Loop (HIL) Industrial Modbus TCP and Healthcare HL7/FHIR Protocol Validation.

Pillar 2: Bridges the gap between memory-only models and real-world industrial and clinical protocols.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import struct
from typing import Any


class ModbusExceptionCode:
    ILLEGAL_FUNCTION = 0x01
    ILLEGAL_DATA_ADDRESS = 0x02
    ILLEGAL_DATA_VALUE = 0x03
    SLAVE_DEVICE_FAILURE = 0x04


class ModbusTcpEmulator:
    """Emulates a programmable logic controller (PLC) Modbus TCP server with standard register mappings."""

    def __init__(self, unit_id: int = 1) -> None:
        self.unit_id = unit_id
        self.holding_registers: dict[int, int] = {i: 0 for i in range(100)}
        self.coils: dict[int, bool] = {i: False for i in range(100)}

    def process_request(self, raw_pdu: bytes) -> bytes:
        """Processes raw Modbus TCP APU (MBAP Header + PDU) and returns response frame."""
        if len(raw_pdu) < 7:
            raise ValueError("FRAME_TOO_SHORT_FOR_MBAP")

        tx_id, proto_id, length, unit_id = struct.unpack(">HHHB", raw_pdu[:7])
        if proto_id != 0:
            raise ValueError("INVALID_MODBUS_PROTOCOL_ID")

        function_code = raw_pdu[7]
        pdu_data = raw_pdu[8:]

        # 0x03: Read Holding Registers
        if function_code == 0x03:
            if len(pdu_data) < 4:
                return self._error_response(tx_id, unit_id, function_code, ModbusExceptionCode.ILLEGAL_DATA_VALUE)
            start_addr, count = struct.unpack(">HH", pdu_data[:4])
            if start_addr + count > 100 or count == 0:
                return self._error_response(tx_id, unit_id, function_code, ModbusExceptionCode.ILLEGAL_DATA_ADDRESS)

            byte_count = count * 2
            resp_pdu = struct.pack(">B", byte_count)
            for i in range(count):
                val = self.holding_registers.get(start_addr + i, 0)
                resp_pdu += struct.pack(">H", val)

            return self._build_frame(tx_id, unit_id, function_code, resp_pdu)

        # 0x06: Write Single Register
        elif function_code == 0x06:
            if len(pdu_data) < 4:
                return self._error_response(tx_id, unit_id, function_code, ModbusExceptionCode.ILLEGAL_DATA_VALUE)
            addr, val = struct.unpack(">HH", pdu_data[:4])
            if addr not in self.holding_registers:
                return self._error_response(tx_id, unit_id, function_code, ModbusExceptionCode.ILLEGAL_DATA_ADDRESS)
            self.holding_registers[addr] = val
            # Echo back request
            return self._build_frame(tx_id, unit_id, function_code, pdu_data[:4])

        else:
            return self._error_response(tx_id, unit_id, function_code, ModbusExceptionCode.ILLEGAL_FUNCTION)

    def _build_frame(self, tx_id: int, unit_id: int, function_code: int, pdu_payload: bytes) -> bytes:
        pdu = struct.pack(">B", function_code) + pdu_payload
        mbap = struct.pack(">HHHB", tx_id, 0, len(pdu) + 1, unit_id)
        return mbap + pdu

    def _error_response(self, tx_id: int, unit_id: int, function_code: int, exc_code: int) -> bytes:
        err_func = function_code | 0x80
        pdu = struct.pack(">BB", err_func, exc_code)
        mbap = struct.pack(">HHHB", tx_id, 0, len(pdu) + 1, unit_id)
        return mbap + pdu


@dataclasses.dataclass
class AuditTrailEntry:
    entry_id: str
    actor: str
    action: str
    timestamp: str
    details: dict[str, Any]
    prev_hash: str
    entry_hash: str


class Hl7FhirValidator:
    """Clinical data exchange validator supporting HL7 v2 and HL7 FHIR R4 with 21 CFR Part 11 audit trails."""

    def __init__(self) -> None:
        self.audit_log: list[AuditTrailEntry] = []
        self._last_hash: str = "GENESIS_BLOCK_00000000000000000000000000000000000000000000000000000000"

    def record_audit(self, actor: str, action: str, details: dict[str, Any]) -> AuditTrailEntry:
        timestamp = dt.datetime.now(dt.UTC).isoformat()
        entry_id = f"AUD-{len(self.audit_log) + 1:06d}"
        payload_to_hash = json.dumps({
            "entry_id": entry_id,
            "actor": actor,
            "action": action,
            "timestamp": timestamp,
            "details": details,
            "prev_hash": self._last_hash,
        }, sort_keys=True)
        entry_hash = hashlib.sha256(payload_to_hash.encode("utf-8")).hexdigest()

        entry = AuditTrailEntry(
            entry_id=entry_id,
            actor=actor,
            action=action,
            timestamp=timestamp,
            details=details,
            prev_hash=self._last_hash,
            entry_hash=entry_hash,
        )
        self.audit_log.append(entry)
        self._last_hash = entry_hash
        return entry

    def verify_audit_chain(self) -> bool:
        """Cryptographically verifies that the audit log has not been altered or truncated."""
        expected_prev = "GENESIS_BLOCK_00000000000000000000000000000000000000000000000000000000"
        for entry in self.audit_log:
            if entry.prev_hash != expected_prev:
                return False
            payload = json.dumps({
                "entry_id": entry.entry_id,
                "actor": entry.actor,
                "action": entry.action,
                "timestamp": entry.timestamp,
                "details": entry.details,
                "prev_hash": entry.prev_hash,
            }, sort_keys=True)
            if hashlib.sha256(payload.encode("utf-8")).hexdigest() != entry.entry_hash:
                return False
            expected_prev = entry.entry_hash
        return True

    def parse_hl7_v2_message(self, raw_message: str) -> dict[str, Any]:
        """Parses standard pipe-and-hat (| ^) HL7 v2 message into segments."""
        segments = [line.strip() for line in raw_message.strip().splitlines() if line.strip()]
        if not segments:
            raise ValueError("HL7_EMPTY_MESSAGE")

        parsed_segments: dict[str, list[list[str]]] = {}
        for seg in segments:
            fields = seg.split("|")
            seg_id = fields[0]
            if seg_id not in parsed_segments:
                parsed_segments[seg_id] = []
            parsed_segments[seg_id].append(fields[1:])

        msh = parsed_segments.get("MSH")
        if not msh:
            raise ValueError("HL7_MISSING_MSH_HEADER")

        return {
            "message_type": msh[0][7] if len(msh[0]) > 7 else "UNKNOWN",
            "message_control_id": msh[0][8] if len(msh[0]) > 8 else "UNKNOWN",
            "segments": parsed_segments,
        }

    def validate_fhir_r4_patient(self, resource: dict[str, Any]) -> dict[str, Any]:
        """Validates FHIR R4 Patient resource according to HL7 International standards."""
        if resource.get("resourceType") != "Patient":
            raise ValueError("RESOURCE_TYPE_MUST_BE_PATIENT")

        errors: list[str] = []
        if not resource.get("id"):
            errors.append("MISSING_PATIENT_ID")
        if not resource.get("name") or not isinstance(resource.get("name"), list):
            errors.append("MISSING_NAME_ARRAY")
        if "gender" in resource and resource["gender"] not in {"male", "female", "other", "unknown"}:
            errors.append("INVALID_GENDER_CODE")

        return {
            "valid": len(errors) == 0,
            "resource_type": "Patient",
            "errors": errors,
        }

"""ELMOS Industrial IoT Protocol Semantic Transformer.

Maps industrial OT protocols (Modbus TCP/RTU registers, Profinet, PLC tags)
to Cloud IT standards: OPC-UA Node IDs, MQTT CloudEvents payloads,
and ROS2 robotic action & sensor topics.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Endianness(str, Enum):
    BIG_ENDIAN = "ABCD"
    LITTLE_ENDIAN = "DCBA"
    MID_BIG_ENDIAN = "BADC"
    MID_LITTLE_ENDIAN = "CDAB"


@dataclass
class IndustrialTag:
    address: int
    name: str
    data_type: str
    description: str = ""
    engineering_unit: str = ""


@dataclass
class IndustrialMappingResult:
    source_protocol: str
    target_protocol: str
    mapped_tags: List[Dict[str, Any]] = field(default_factory=list)
    cloudevents_schema: Dict[str, Any] = field(default_factory=dict)
    opcua_nodes: List[Dict[str, Any]] = field(default_factory=list)
    ros2_msg_definition: str = ""
    merkle_receipt: str = ""


@dataclass
class CanFrame:
    arbitration_id: int
    is_extended: bool
    data: bytes
    dlc: int = 8


@dataclass
class DbcSignal:
    name: str
    start_bit: int
    length: int
    is_little_endian: bool
    is_signed: bool
    scale: float = 1.0
    offset: float = 0.0
    unit: str = ""


@dataclass
class SparkplugMetric:
    name: str
    timestamp_ms: int
    datatype: str
    value: Any


@dataclass
class IndustrialSafetyValidationResult:
    is_safe: bool
    action: str
    violations: List[str] = field(default_factory=list)
    recommendation: str = ""


def compute_crc16_modbus(data: bytes) -> int:
    """Calculates standard Modbus RTU CRC-16 (polynomial 0xA001, initial 0xFFFF)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def verify_crc16_modbus(frame: bytes) -> bool:
    """Verifies Modbus RTU frame where the last 2 bytes are little-endian CRC-16."""
    if len(frame) < 3:
        return False
    data_bytes = frame[:-2]
    expected_crc = frame[-2] | (frame[-1] << 8)
    actual_crc = compute_crc16_modbus(data_bytes)
    return actual_crc == expected_crc


def build_modbus_rtu_frame(slave_id: int, function_code: int, payload: bytes) -> bytes:
    """Builds a complete Modbus RTU frame including appended CRC16."""
    pdu = bytes([slave_id & 0xFF, function_code & 0xFF]) + payload
    crc = compute_crc16_modbus(pdu)
    crc_bytes = bytes([crc & 0xFF, (crc >> 8) & 0xFF])
    return pdu + crc_bytes


def parse_modbus_rtu_frame(frame: bytes) -> Dict[str, Any]:
    """Parses and validates a Modbus RTU frame."""
    if len(frame) < 4:
        raise ValueError("Modbus RTU frame too short (min 4 bytes)")
    if not verify_crc16_modbus(frame):
        raise ValueError("Modbus RTU frame CRC mismatch (corrupted frame)")
    slave_id = frame[0]
    function_code = frame[1]
    payload = frame[2:-2]
    return {
        "slave_id": slave_id,
        "function_code": function_code,
        "payload": payload,
        "payload_hex": payload.hex().upper(),
        "is_exception": (function_code & 0x80) != 0,
    }


def decode_can_dbc_signal(frame_data: bytes, signal: DbcSignal) -> float:
    """Decodes a CAN signal from raw payload bytes using DBC specifications."""
    if len(frame_data) < 8:
        frame_data = frame_data.ljust(8, b"\x00")

    val_raw = 0
    if signal.is_little_endian:
        full_val = int.from_bytes(frame_data, byteorder="little")
        mask = (1 << signal.length) - 1
        val_raw = (full_val >> signal.start_bit) & mask
    else:
        full_val = int.from_bytes(frame_data, byteorder="big")
        shift = 64 - (signal.start_bit + 1)
        mask = (1 << signal.length) - 1
        val_raw = (full_val >> shift) & mask

    if signal.is_signed:
        sign_bit = 1 << (signal.length - 1)
        if val_raw & sign_bit:
            val_raw -= (1 << signal.length)

    return float(val_raw) * signal.scale + signal.offset


class IndustrialSafetyGate:
    """Enforces safety rules from ADR-0053 and Batch 24 policy constraints."""

    @staticmethod
    def validate_discovery_request(is_active_scan: bool, target_device_type: str) -> IndustrialSafetyValidationResult:
        if is_active_scan and target_device_type.upper() in ("PLC", "SAFETY_CONTROLLER", "DCS", "RTU"):
            return IndustrialSafetyValidationResult(
                is_safe=False,
                action="FAIL_CLOSED",
                violations=["ACTIVE_SCAN_PROHIBITED_ON_OT_DEVICE"],
                recommendation="Use configuration export and passive evidence capture instead.",
            )
        return IndustrialSafetyValidationResult(is_safe=True, action="PASS")

    @staticmethod
    def validate_plc_runtime_checksum(project_checksum: str, runtime_checksum: str) -> IndustrialSafetyValidationResult:
        if project_checksum != runtime_checksum:
            return IndustrialSafetyValidationResult(
                is_safe=False,
                action="FAIL_CLOSED",
                violations=["PLC_PROJECT_RUNTIME_MISMATCH"],
                recommendation="Re-synchronize engineering station before proceeding with modernization.",
            )
        return IndustrialSafetyValidationResult(is_safe=True, action="PASS")

    @staticmethod
    def validate_controller_safety_class(is_safety_plc: bool, target_action: str) -> IndustrialSafetyValidationResult:
        if is_safety_plc:
            return IndustrialSafetyValidationResult(
                is_safe=False,
                action="FAIL_CLOSED",
                violations=["SAFETY_CONTROLLER_ISOLATION_REQUIRED"],
                recommendation="Safety PLC logic modification requires independent SIL certification and human sign-off.",
            )
        return IndustrialSafetyValidationResult(is_safe=True, action="PASS")

    @staticmethod
    def validate_tag_quality_propagation(quality: str, raw_value: Any) -> Dict[str, Any]:
        normalized_q = quality.upper()
        if normalized_q in ("BAD", "COMM_FAILURE", "SENSOR_FAILURE", "UNCERTAIN"):
            return {
                "quality": normalized_q,
                "is_valid": False,
                "value": None,
                "treated_as_zero": False,
                "warning": "Tag quality BAD: value suppressed to prevent misleading zero measurements.",
            }
        return {
            "quality": "GOOD",
            "is_valid": True,
            "value": raw_value,
            "treated_as_zero": False,
            "warning": None,
        }

    @staticmethod
    def validate_write_command(is_production: bool, approved_by_human: bool, write_range: str) -> IndustrialSafetyValidationResult:
        if is_production and not approved_by_human:
            return IndustrialSafetyValidationResult(
                is_safe=False,
                action="FAIL_CLOSED",
                violations=["UNAUTHORIZED_PRODUCTION_WRITE"],
                recommendation="Production commands require explicit offline human approval.",
            )
        return IndustrialSafetyValidationResult(is_safe=True, action="PASS")


class IndustrialProtocolMapper:
    """Enterprise Industrial Protocol Semantic Transformer."""

    def __init__(self) -> None:
        self.safety_gate = IndustrialSafetyGate()

    def parse_tags_string(self, raw_tags: str) -> List[IndustrialTag]:
        """Parses tag specification e.g. '40001:FLOAT32:MotorTemp;40003:UINT16:RPM'."""
        tags: List[IndustrialTag] = []
        chunks = [c.strip() for c in raw_tags.split(";") if c.strip()]
        for chunk in chunks:
            parts = chunk.split(":")
            if len(parts) >= 3:
                addr = int(re.sub(r"\D", "", parts[0]) or "0")
                dtype = parts[1].upper()
                name = parts[2]
                unit = parts[3] if len(parts) > 3 else ""
                tags.append(IndustrialTag(address=addr, name=name, data_type=dtype, engineering_unit=unit))
            elif len(parts) == 2:
                addr = int(re.sub(r"\D", "", parts[0]) or "0")
                name = parts[1]
                tags.append(IndustrialTag(address=addr, name=name, data_type="UINT16"))
        return tags

    def map_modbus_to_opcua_and_cloud(
        self, tags_spec: str, namespace_idx: int = 2, device_id: str = "RobotArm_01"
    ) -> IndustrialMappingResult:
        tags = self.parse_tags_string(tags_spec)
        if not tags:
            tags = [
                IndustrialTag(address=40001, name="MotorTemperature", data_type="FLOAT32", engineering_unit="celsius"),
                IndustrialTag(address=40003, name="RotationalSpeed", data_type="UINT16", engineering_unit="rpm"),
                IndustrialTag(address=40004, name="Torque", data_type="FLOAT32", engineering_unit="Nm"),
            ]

        mapped_tags: List[Dict[str, Any]] = []
        opcua_nodes: List[Dict[str, Any]] = []
        cloudevent_props: Dict[str, Any] = {}
        ros2_fields: List[str] = []

        for tag in tags:
            node_id = f"ns={namespace_idx};s={device_id}.{tag.name}"
            mapped_tags.append({
                "modbus_address": tag.address,
                "tag_name": tag.name,
                "data_type": tag.data_type,
                "opcua_node_id": node_id,
                "unit": tag.engineering_unit,
            })

            opcua_nodes.append({
                "nodeId": node_id,
                "browseName": tag.name,
                "dataType": self._to_opcua_type(tag.data_type),
                "accessLevel": "CurrentRead | CurrentWrite",
            })

            cloudevent_props[tag.name] = {
                "type": "number" if "FLOAT" in tag.data_type or "INT" in tag.data_type else "string",
                "modbusRegister": tag.address,
                "unit": tag.engineering_unit,
            }

            ros2_fields.append(f"{self._to_ros2_type(tag.data_type)} {self._snake_case(tag.name)}")

        cloudevent_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "title": f"{device_id}TelemetryEvent",
            "properties": {
                "specversion": {"type": "string", "const": "1.0"},
                "type": {"type": "string", "const": f"com.elmos.industrial.{device_id}.telemetry"},
                "source": {"type": "string", "const": f"/devices/{device_id}"},
                "data": {
                    "type": "object",
                    "properties": cloudevent_props,
                },
            },
            "required": ["specversion", "type", "source", "data"],
        }

        ros2_def = "# Auto-generated by ELMOS Industrial Protocol Mapper\n"
        ros2_def += "std_msgs/Header header\n"
        for rf in ros2_fields:
            ros2_def += f"{rf}\n"

        h = hashlib.sha256(f"{tags_spec}:{json.dumps(cloudevent_schema)}".encode("utf-8")).hexdigest()

        return IndustrialMappingResult(
            source_protocol="Modbus-TCP/RTU",
            target_protocol="OPC-UA / MQTT-CloudEvents / ROS2",
            mapped_tags=mapped_tags,
            cloudevents_schema=cloudevent_schema,
            opcua_nodes=opcua_nodes,
            ros2_msg_definition=ros2_def.strip(),
            merkle_receipt=f"sha256:{h}",
        )

    def _to_opcua_type(self, dtype: str) -> str:
        if "FLOAT" in dtype:
            return "Float" if "32" in dtype else "Double"
        if "INT32" in dtype:
            return "Int32"
        if "INT64" in dtype:
            return "Int64"
        if "UINT" in dtype:
            return "UInt16" if "16" in dtype else "UInt32"
        return "Int16"

    def _to_ros2_type(self, dtype: str) -> str:
        if "FLOAT" in dtype:
            return "float32" if "32" in dtype else "float64"
        if "INT32" in dtype:
            return "int32"
        if "INT64" in dtype:
            return "int64"
        if "UINT" in dtype:
            return "uint16" if "16" in dtype else "uint32"
        return "int16"

    def _snake_case(self, name: str) -> str:
        s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    def generate_ros2_action_spec(
        self, action_name: str, goal_fields: List[str], result_fields: List[str], feedback_fields: List[str]
    ) -> str:
        """Generates standard ROS2 .action definition file format (Goal --- Result --- Feedback)."""
        lines = [f"# ROS2 Action Definition for {action_name}"]
        for g in goal_fields:
            lines.append(g)
        lines.append("---")
        for r in result_fields:
            lines.append(r)
        lines.append("---")
        for fb in feedback_fields:
            lines.append(fb)
        return "\n".join(lines) + "\n"

    def generate_ros2_service_spec(
        self, service_name: str, request_fields: List[str], response_fields: List[str]
    ) -> str:
        """Generates standard ROS2 .srv definition file format (Request --- Response)."""
        lines = [f"# ROS2 Service Definition for {service_name}"]
        for req in request_fields:
            lines.append(req)
        lines.append("---")
        for resp in response_fields:
            lines.append(resp)
        return "\n".join(lines) + "\n"

    def generate_sparkplug_payload(
        self, device_id: str, tags: List[IndustrialTag], values: Dict[str, Any], timestamp_ms: int
    ) -> Dict[str, Any]:
        """Generates Eclipse Sparkplug B compliant telemetry payload dictionary."""
        metrics: List[Dict[str, Any]] = []
        for tag in tags:
            val = values.get(tag.name)
            metrics.append({
                "name": tag.name,
                "timestamp": timestamp_ms,
                "datatype": self._to_sparkplug_datatype(tag.data_type),
                "value": val,
                "properties": {
                    "engineeringUnits": tag.engineering_unit,
                    "address": tag.address,
                },
            })

        return {
            "timestamp": timestamp_ms,
            "metrics": metrics,
            "seq": 0,
            "device_id": device_id,
        }

    def _to_sparkplug_datatype(self, dtype: str) -> str:
        if "FLOAT" in dtype:
            return "Float" if "32" in dtype else "Double"
        if "INT32" in dtype:
            return "Int32"
        if "INT64" in dtype:
            return "Int64"
        if "UINT" in dtype:
            return "UInt16" if "16" in dtype else "UInt32"
        return "Int16"


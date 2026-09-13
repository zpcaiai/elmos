"""Comprehensive test suite for ELMOS Industrial Protocol Mapper and Safety Gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elmos_industrial_engine.protocol_mapper import (
    CanFrame,
    DbcSignal,
    IndustrialProtocolMapper,
    IndustrialSafetyGate,
    IndustrialTag,
    build_modbus_rtu_frame,
    compute_crc16_modbus,
    decode_can_dbc_signal,
    parse_modbus_rtu_frame,
    verify_crc16_modbus,
)


class TestIndustrialProtocolMapper(unittest.TestCase):
    """Tests for protocol mapper, translations, and frame generation."""

    def setUp(self) -> None:
        self.mapper = IndustrialProtocolMapper()

    def test_parse_tags_string_complete(self) -> None:
        raw = "40001:FLOAT32:MotorTemp:celsius;40003:UINT16:RPM:rpm;40004:INT32:TotalCount"
        tags = self.mapper.parse_tags_string(raw)
        self.assertEqual(len(tags), 3)
        self.assertEqual(tags[0].address, 40001)
        self.assertEqual(tags[0].name, "MotorTemp")
        self.assertEqual(tags[0].data_type, "FLOAT32")
        self.assertEqual(tags[0].engineering_unit, "celsius")

        self.assertEqual(tags[1].address, 40003)
        self.assertEqual(tags[1].name, "RPM")
        self.assertEqual(tags[1].data_type, "UINT16")
        self.assertEqual(tags[1].engineering_unit, "rpm")

        self.assertEqual(tags[2].address, 40004)
        self.assertEqual(tags[2].name, "TotalCount")
        self.assertEqual(tags[2].data_type, "INT32")
        self.assertEqual(tags[2].engineering_unit, "")

    def test_parse_tags_string_default_uint16(self) -> None:
        raw = "40010:ValveState"
        tags = self.mapper.parse_tags_string(raw)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0].address, 40010)
        self.assertEqual(tags[0].name, "ValveState")
        self.assertEqual(tags[0].data_type, "UINT16")

    def test_parse_tags_string_empty_returns_empty(self) -> None:
        self.assertEqual(self.mapper.parse_tags_string(""), [])
        self.assertEqual(self.mapper.parse_tags_string("   ; ;  "), [])

    def test_map_modbus_to_opcua_and_cloud_defaults(self) -> None:
        res = self.mapper.map_modbus_to_opcua_and_cloud("", namespace_idx=2, device_id="Robot_A")
        self.assertEqual(res.source_protocol, "Modbus-TCP/RTU")
        self.assertIn("OPC-UA", res.target_protocol)
        self.assertEqual(len(res.mapped_tags), 3)
        self.assertEqual(len(res.opcua_nodes), 3)
        self.assertTrue(res.merkle_receipt.startswith("sha256:"))

    def test_opcua_nodes_structure(self) -> None:
        res = self.mapper.map_modbus_to_opcua_and_cloud("40001:FLOAT32:Temperature:degC", namespace_idx=3, device_id="Furnace01")
        self.assertEqual(len(res.opcua_nodes), 1)
        node = res.opcua_nodes[0]
        self.assertEqual(node["nodeId"], "ns=3;s=Furnace01.Temperature")
        self.assertEqual(node["browseName"], "Temperature")
        self.assertEqual(node["dataType"], "Float")
        self.assertEqual(node["accessLevel"], "CurrentRead | CurrentWrite")

    def test_cloudevents_schema_structure(self) -> None:
        res = self.mapper.map_modbus_to_opcua_and_cloud("40001:FLOAT32:Torque:Nm", device_id="Drive01")
        schema = res.cloudevents_schema
        self.assertEqual(schema["$schema"], "http://json-schema.org/draft-07/schema#")
        self.assertEqual(schema["title"], "Drive01TelemetryEvent")
        self.assertIn("specversion", schema["required"])
        self.assertIn("data", schema["required"])
        self.assertEqual(schema["properties"]["source"]["const"], "/devices/Drive01")
        self.assertIn("Torque", schema["properties"]["data"]["properties"])

    def test_ros2_msg_definition_snake_case(self) -> None:
        res = self.mapper.map_modbus_to_opcua_and_cloud("40001:FLOAT32:MotorTemperature;40003:UINT16:RotationalSpeed")
        msg = res.ros2_msg_definition
        self.assertIn("std_msgs/Header header", msg)
        self.assertIn("float32 motor_temperature", msg)
        self.assertIn("uint16 rotational_speed", msg)

    def test_generate_ros2_action_spec(self) -> None:
        action_spec = self.mapper.generate_ros2_action_spec(
            action_name="MoveJoint",
            goal_fields=["float64 target_angle", "float64 max_velocity"],
            result_fields=["bool success", "string message"],
            feedback_fields=["float64 current_angle", "float64 progress_pct"],
        )
        sections = action_spec.strip().split("---")
        self.assertEqual(len(sections), 3)
        self.assertIn("target_angle", sections[0])
        self.assertIn("success", sections[1])
        self.assertIn("current_angle", sections[2])

    def test_generate_ros2_service_spec(self) -> None:
        service_spec = self.mapper.generate_ros2_service_spec(
            service_name="CalibrateSensor",
            request_fields=["string sensor_id", "uint32 calibration_mode"],
            response_fields=["bool is_calibrated", "float64 offset"],
        )
        sections = service_spec.strip().split("---")
        self.assertEqual(len(sections), 2)
        self.assertIn("sensor_id", sections[0])
        self.assertIn("is_calibrated", sections[1])

    def test_generate_sparkplug_payload(self) -> None:
        tags = [
            IndustrialTag(address=40001, name="MotorTemp", data_type="FLOAT32", engineering_unit="degC"),
            IndustrialTag(address=40003, name="RPM", data_type="UINT16", engineering_unit="rpm"),
        ]
        values = {"MotorTemp": 62.5, "RPM": 1450}
        payload = self.mapper.generate_sparkplug_payload("EdgeNode01", tags, values, 1700000000000)
        self.assertEqual(payload["device_id"], "EdgeNode01")
        self.assertEqual(payload["timestamp"], 1700000000000)
        self.assertEqual(len(payload["metrics"]), 2)
        self.assertEqual(payload["metrics"][0]["name"], "MotorTemp")
        self.assertEqual(payload["metrics"][0]["value"], 62.5)
        self.assertEqual(payload["metrics"][0]["datatype"], "Float")
        self.assertEqual(payload["metrics"][0]["properties"]["engineeringUnits"], "degC")


class TestModbusRtuCrc(unittest.TestCase):
    """Tests for Modbus RTU CRC16 and frame building/parsing."""

    def test_compute_crc16_modbus_known_vector(self) -> None:
        # Standard Modbus poll request: 01 03 00 00 00 0A
        # CRC is 0xC5CD -> Low byte 0xC5, High byte 0xCD
        data = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x0A])
        crc = compute_crc16_modbus(data)
        self.assertEqual(crc, 0xCDC5)  # Or little-endian bytes: 0xC5, 0xCD

    def test_verify_crc16_modbus_valid_frame(self) -> None:
        frame = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x0A, 0xC5, 0xCD])
        self.assertTrue(verify_crc16_modbus(frame))

    def test_verify_crc16_modbus_corrupted_frame(self) -> None:
        frame = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x0A, 0xFF, 0xFF])
        self.assertFalse(verify_crc16_modbus(frame))

    def test_build_and_parse_modbus_rtu_frame(self) -> None:
        payload = bytes([0x00, 0x01, 0x00, 0x02])
        frame = build_modbus_rtu_frame(slave_id=1, function_code=3, payload=payload)
        self.assertTrue(verify_crc16_modbus(frame))

        parsed = parse_modbus_rtu_frame(frame)
        self.assertEqual(parsed["slave_id"], 1)
        self.assertEqual(parsed["function_code"], 3)
        self.assertEqual(parsed["payload"], payload)
        self.assertFalse(parsed["is_exception"])

    def test_parse_modbus_rtu_frame_exception_code(self) -> None:
        # Function code with MSB set (e.g. 0x83 = Read exception)
        err_payload = bytes([0x02])  # Illegal data address
        frame = build_modbus_rtu_frame(slave_id=1, function_code=0x83, payload=err_payload)
        parsed = parse_modbus_rtu_frame(frame)
        self.assertTrue(parsed["is_exception"])
        self.assertEqual(parsed["function_code"], 0x83)

    def test_parse_modbus_rtu_frame_raises_on_invalid(self) -> None:
        with self.assertRaises(ValueError):
            parse_modbus_rtu_frame(b"\x01\x02")  # Too short

        with self.assertRaises(ValueError):
            parse_modbus_rtu_frame(b"\x01\x03\x00\x00\x00\x00")  # Corrupted CRC


class TestCanDbcDecoding(unittest.TestCase):
    """Tests for CAN bus frame and DBC signal decoding."""

    def test_decode_can_little_endian_unsigned(self) -> None:
        # 16-bit unsigned speed at start_bit 0, scale 0.1, offset 0.0
        signal = DbcSignal(
            name="VehicleSpeed",
            start_bit=0,
            length=16,
            is_little_endian=True,
            is_signed=False,
            scale=0.1,
            offset=0.0,
            unit="km/h",
        )
        # 1000 in little endian = E8 03
        data = bytes([0xE8, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        speed = decode_can_dbc_signal(data, signal)
        # 1000 * 0.1 = 100.0 km/h
        self.assertAlmostEqual(speed, 100.0, places=4)

    def test_decode_can_little_endian_signed_negative(self) -> None:
        # 8-bit signed temperature at start_bit 16, scale 1.0, offset -40.0
        signal = DbcSignal(
            name="CoolantTemp",
            start_bit=16,
            length=8,
            is_little_endian=True,
            is_signed=True,
            scale=1.0,
            offset=-40.0,
            unit="degC",
        )
        # raw value 60 -> 60 * 1.0 - 40.0 = 20.0
        data = bytes([0x00, 0x00, 60, 0x00, 0x00, 0x00, 0x00, 0x00])
        temp = decode_can_dbc_signal(data, signal)
        self.assertAlmostEqual(temp, 20.0, places=4)


class TestIndustrialSafetyGate(unittest.TestCase):
    """Tests safety invariants from ADR-0053 and Batch 24 requirements."""

    def setUp(self) -> None:
        self.gate = IndustrialSafetyGate()

    def test_active_scan_prohibited_on_plc(self) -> None:
        res = self.gate.validate_discovery_request(is_active_scan=True, target_device_type="PLC")
        self.assertFalse(res.is_safe)
        self.assertEqual(res.action, "FAIL_CLOSED")
        self.assertIn("ACTIVE_SCAN_PROHIBITED_ON_OT_DEVICE", res.violations)

    def test_passive_scan_allowed(self) -> None:
        res = self.gate.validate_discovery_request(is_active_scan=False, target_device_type="PLC")
        self.assertTrue(res.is_safe)
        self.assertEqual(res.action, "PASS")

    def test_plc_runtime_checksum_mismatch(self) -> None:
        res = self.gate.validate_plc_runtime_checksum("hash_abc_123", "hash_xyz_789")
        self.assertFalse(res.is_safe)
        self.assertEqual(res.action, "FAIL_CLOSED")
        self.assertIn("PLC_PROJECT_RUNTIME_MISMATCH", res.violations)

    def test_plc_runtime_checksum_match(self) -> None:
        res = self.gate.validate_plc_runtime_checksum("hash_abc_123", "hash_abc_123")
        self.assertTrue(res.is_safe)
        self.assertEqual(res.action, "PASS")

    def test_safety_plc_isolation(self) -> None:
        res = self.gate.validate_controller_safety_class(is_safety_plc=True, target_action="containerize")
        self.assertFalse(res.is_safe)
        self.assertEqual(res.action, "FAIL_CLOSED")
        self.assertIn("SAFETY_CONTROLLER_ISOLATION_REQUIRED", res.violations)

    def test_bad_quality_tag_suppresses_zero_measurement(self) -> None:
        res = self.gate.validate_tag_quality_propagation(quality="BAD", raw_value=0)
        self.assertFalse(res["is_valid"])
        self.assertIsNone(res["value"])
        self.assertFalse(res["treated_as_zero"])

    def test_good_quality_tag_allows_value(self) -> None:
        res = self.gate.validate_tag_quality_propagation(quality="GOOD", raw_value=42.5)
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["value"], 42.5)
        self.assertFalse(res["treated_as_zero"])

    def test_unauthorized_production_write_fails_closed(self) -> None:
        res = self.gate.validate_write_command(is_production=True, approved_by_human=False, write_range="40001-40010")
        self.assertFalse(res.is_safe)
        self.assertEqual(res.action, "FAIL_CLOSED")
        self.assertIn("UNAUTHORIZED_PRODUCTION_WRITE", res.violations)

    def test_authorized_production_write_passes(self) -> None:
        res = self.gate.validate_write_command(is_production=True, approved_by_human=True, write_range="40001-40010")
        self.assertTrue(res.is_safe)
        self.assertEqual(res.action, "PASS")


if __name__ == "__main__":
    unittest.main()


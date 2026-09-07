"""Tests for Industrial IoT & Edge Protocol Semantic Transformer."""

import unittest
from elmos_industrial_engine.protocol_mapper import IndustrialProtocolMapper


class TestIndustrialProtocolMapper(unittest.TestCase):
    def setUp(self):
        self.mapper = IndustrialProtocolMapper()

    def test_map_modbus_to_opcua_and_cloud(self):
        spec = "40001:FLOAT32:MotorTemperature:celsius;40003:UINT16:RPM:rpm"
        res = self.mapper.map_modbus_to_opcua_and_cloud(spec, device_id="Kuka_Robot_Arm_01")
        self.assertEqual(res.source_protocol, "Modbus-TCP/RTU")
        self.assertEqual(res.target_protocol, "OPC-UA / MQTT-CloudEvents / ROS2")
        self.assertEqual(len(res.mapped_tags), 2)
        self.assertEqual(res.mapped_tags[0]["tag_name"], "MotorTemperature")
        self.assertEqual(res.mapped_tags[0]["data_type"], "FLOAT32")

        # OPC UA nodes
        self.assertEqual(len(res.opcua_nodes), 2)
        self.assertIn("ns=2;s=Kuka_Robot_Arm_01.MotorTemperature", res.opcua_nodes[0]["nodeId"])

        # CloudEvents schema
        self.assertIn("data", res.cloudevents_schema["properties"])
        self.assertEqual(res.cloudevents_schema["properties"]["source"]["const"], "/devices/Kuka_Robot_Arm_01")

        # ROS2 msg definition
        self.assertIn("float32 motor_temperature", res.ros2_msg_definition)
        self.assertIn("uint16 rpm", res.ros2_msg_definition)
        self.assertTrue(res.merkle_receipt.startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()

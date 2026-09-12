import struct
import sys
import unittest
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elmos_industrial_engine.native_industrial_bridge import (
    decode_modbus_registers,
    swap_bytes_32,
)


class TestNativeIndustrial(unittest.TestCase):
    """Validates native and fallback industrial byte-swapping and register decoding."""

    def test_swap_bytes_abcd_big_endian(self) -> None:
        # 12.34f32 in big endian hex is 414570A4
        res = swap_bytes_32("414570A4", "ABCD")
        self.assertEqual(res["hex"], "414570A4")
        self.assertAlmostEqual(res["float32"], 12.34, places=4)

    def test_swap_bytes_dcba_little_endian(self) -> None:
        # 12.34 in DCBA little-endian bytes: A4704541
        res = swap_bytes_32("A4704541", "DCBA")
        self.assertEqual(res["hex"], "414570A4")
        self.assertAlmostEqual(res["float32"], 12.34, places=4)

    def test_swap_bytes_cdab_mid_little_endian(self) -> None:
        # 12.34 in CDAB (word-swapped) bytes: 70A44145
        res = swap_bytes_32("70A44145", "CDAB")
        self.assertEqual(res["hex"], "414570A4")
        self.assertAlmostEqual(res["float32"], 12.34, places=4)

    def test_swap_bytes_badc_mid_big_endian(self) -> None:
        # 12.34 in BADC (byte-swapped) bytes: 4541A470
        res = swap_bytes_32("4541A470", "BADC")
        self.assertEqual(res["hex"], "414570A4")
        self.assertAlmostEqual(res["float32"], 12.34, places=4)

    def test_swap_bytes_int32_decoding(self) -> None:
        # Integer 12345678 in big-endian hex is 00BC614E
        res = swap_bytes_32("00BC614E", "ABCD")
        self.assertEqual(res["int32"], 12345678)

        # Little endian: 4E61BC00
        res_le = swap_bytes_32("4E61BC00", "DCBA")
        self.assertEqual(res_le["int32"], 12345678)

    def test_swap_bytes_negative_int32(self) -> None:
        # Integer -500 in 32-bit two's complement: FFFFFE0C
        res = swap_bytes_32("FFFFFE0C", "ABCD")
        self.assertEqual(res["int32"], -500)

    def test_decode_modbus_registers_float32(self) -> None:
        # 50.5f32 in big endian is 0x424A 0x0000
        registers = [0x424A, 0x0000]
        mappings = [
            {
                "register_address": 40001,
                "tag_name": "MotorTemp",
                "data_type": "FLOAT32",
                "endianness": "ABCD",
                "scale": 1.0,
                "offset": 0.0,
            }
        ]
        decoded = decode_modbus_registers(registers, 40001, mappings)
        self.assertEqual(len(decoded), 1)
        self.assertEqual(decoded[0]["tag_name"], "MotorTemp")
        self.assertAlmostEqual(decoded[0]["engineering_value"], 50.5, places=4)
        self.assertEqual(decoded[0]["quality"], "GOOD")

    def test_decode_modbus_registers_uint16_with_scale_and_offset(self) -> None:
        registers = [1500]
        mappings = [
            {
                "register_address": 40003,
                "tag_name": "Speed",
                "data_type": "UINT16",
                "endianness": "ABCD",
                "scale": 0.1,
                "offset": 10.0,
            }
        ]
        decoded = decode_modbus_registers(registers, 40003, mappings)
        self.assertEqual(len(decoded), 1)
        self.assertEqual(decoded[0]["tag_name"], "Speed")
        # 1500 * 0.1 + 10 = 160.0
        self.assertAlmostEqual(decoded[0]["engineering_value"], 160.0, places=4)

    def test_decode_modbus_registers_mixed_block(self) -> None:
        # Reg 40001-40002: Float 50.5 (0x424A, 0x0000)
        # Reg 40003: Speed (1200)
        # Reg 40004: Pressure (300)
        registers = [0x424A, 0x0000, 1200, 300]
        mappings = [
            {
                "register_address": 40001,
                "tag_name": "Temp",
                "data_type": "FLOAT32",
                "scale": 1.0,
                "offset": 0.0,
            },
            {
                "register_address": 40003,
                "tag_name": "RPM",
                "data_type": "UINT16",
                "scale": 1.0,
                "offset": 0.0,
            },
            {
                "register_address": 40004,
                "tag_name": "Pressure",
                "data_type": "UINT16",
                "scale": 0.01,
                "offset": 0.0,
            },
        ]
        decoded = decode_modbus_registers(registers, 40001, mappings)
        self.assertEqual(len(decoded), 3)
        self.assertAlmostEqual(decoded[0]["engineering_value"], 50.5, places=4)
        self.assertAlmostEqual(decoded[1]["engineering_value"], 1200.0, places=4)
        self.assertAlmostEqual(decoded[2]["engineering_value"], 3.0, places=4)

    def test_decode_modbus_registers_out_of_bounds(self) -> None:
        registers = [100]
        # Mapping requests 40005, which is outside registers length
        mappings = [
            {
                "register_address": 40005,
                "tag_name": "MissingTag",
                "data_type": "UINT16",
            }
        ]
        decoded = decode_modbus_registers(registers, 40001, mappings)
        # Should handle gracefully without crashing (empty or quality BAD)
        if decoded:
            self.assertIn("BAD", decoded[0].get("quality", "BAD"))

    def test_decode_modbus_registers_empty_inputs(self) -> None:
        self.assertEqual(decode_modbus_registers([], 40001, []), [])


if __name__ == "__main__":
    unittest.main()


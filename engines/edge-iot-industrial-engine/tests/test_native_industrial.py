import struct
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elmos_industrial_engine.native_industrial_bridge import (
    swap_bytes_32,
    decode_modbus_registers,
)


def test_swap_bytes_and_float_endianness():
    # 12.34f32 in big endian hex is 414570A4
    orig_f = 12.34
    orig_hex = "414570A4"

    # ABCD (Big Endian)
    res_abcd = swap_bytes_32(orig_hex, "ABCD")
    assert res_abcd["hex"] == "414570A4"
    assert abs(res_abcd["float32"] - orig_f) < 1e-4

    # DCBA (Little Endian bytes: A4704541)
    res_dcba = swap_bytes_32("A4704541", "DCBA")
    assert res_dcba["hex"] == "414570A4"
    assert abs(res_dcba["float32"] - orig_f) < 1e-4


def test_decode_modbus_registers():
    # 50.5f32 in big endian is 424A 0000
    registers = [0x424A, 0x0000, 1500]
    mappings = [
        {
            "register_address": 40001,
            "tag_name": "MotorTemp",
            "data_type": "FLOAT32",
            "endianness": "ABCD",
            "scale": 1.0,
            "offset": 0.0,
        },
        {
            "register_address": 40003,
            "tag_name": "Speed",
            "data_type": "UINT16",
            "endianness": "ABCD",
            "scale": 0.1,
            "offset": 10.0,
        },
    ]

    decoded = decode_modbus_registers(registers, 40001, mappings)
    assert len(decoded) == 2
    assert decoded[0]["tag_name"] == "MotorTemp"
    assert abs(decoded[0]["engineering_value"] - 50.5) < 1e-4

    assert decoded[1]["tag_name"] == "Speed"
    # 1500 * 0.1 + 10 = 160.0
    assert abs(decoded[1]["engineering_value"] - 160.0) < 1e-4

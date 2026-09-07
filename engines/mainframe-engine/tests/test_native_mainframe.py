import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elmos_mainframe_bridge import ebcdic_to_ascii, comp3_decode, comp3_encode


def test_ebcdic_to_ascii_native():
    # EBCDIC bytes for "HELLO" (0xC8, 0xC5, 0xD3, 0xD3, 0xD6)
    ebcdic = bytes([0xC8, 0xC5, 0xD3, 0xD3, 0xD6])
    ascii_res = ebcdic_to_ascii(ebcdic)
    assert ascii_res == "HELLO"


def test_comp3_decode_and_encode_native():
    # Positive packed decimal: +123.45 -> 0x12 0x34 0x5C
    decoded = comp3_decode("12345C", scale=2)
    assert decoded == "123.45"

    encoded = comp3_encode("123.45", scale=2, total_bytes=3)
    assert encoded == "12345C"

    # Negative packed decimal: -6789 -> 0x06 0x78 0x9D
    decoded_neg = comp3_decode("06789D", scale=0)
    assert decoded_neg == "-6789"

    encoded_neg = comp3_encode("-6789", scale=0, total_bytes=3)
    assert encoded_neg == "06789D"

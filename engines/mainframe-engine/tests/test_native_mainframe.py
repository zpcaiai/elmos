import unittest
import sys
from pathlib import Path
from unittest.mock import patch

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elmos_mainframe_bridge import (
    ebcdic_to_ascii,
    ascii_to_ebcdic,
    comp3_decode,
    comp3_encode,
    parse_comp3_field,
    format_comp3_field,
)


class TestMainframeNativeBridge(unittest.TestCase):
    """Comprehensive test suite for Mainframe EBCDIC and COMP-3 transcoding."""

    def test_ebcdic_to_ascii_basic(self):
        # EBCDIC bytes for "HELLO" (0xC8, 0xC5, 0xD3, 0xD3, 0xD6)
        ebcdic = bytes([0xC8, 0xC5, 0xD3, 0xD3, 0xD6])
        self.assertEqual(ebcdic_to_ascii(ebcdic), "HELLO")

    def test_ebcdic_to_ascii_numbers(self):
        # EBCDIC digits 0-9: 0xF0 - 0xF9
        ebcdic_digits = bytes(range(0xF0, 0xFA))
        self.assertEqual(ebcdic_to_ascii(ebcdic_digits), "0123456789")

    def test_ebcdic_to_ascii_empty(self):
        self.assertEqual(ebcdic_to_ascii(b""), "")

    def test_ascii_to_ebcdic_roundtrip(self):
        original = "BATCH19_COBOL_MAINFRAME_DATA_2026"
        ebcdic = ascii_to_ebcdic(original)
        self.assertIsInstance(ebcdic, bytes)
        decoded = ebcdic_to_ascii(ebcdic)
        self.assertEqual(decoded, original)

    def test_comp3_decode_positive_scaled(self):
        # Positive packed decimal: +123.45 -> 0x12 0x34 0x5C
        decoded = comp3_decode("12345C", scale=2)
        self.assertEqual(decoded, "123.45")

    def test_comp3_decode_positive_alt_sign_f(self):
        # 0xF is also a valid positive sign in IBM packed decimal
        decoded = comp3_decode("12345F", scale=2)
        self.assertEqual(decoded, "123.45")

    def test_comp3_decode_negative_d(self):
        # Negative packed decimal with 0xD sign: -6789 -> 0x06 0x78 0x9D
        decoded = comp3_decode("06789D", scale=0)
        self.assertEqual(decoded, "-6789")

    def test_comp3_decode_negative_alt_sign_b(self):
        # 0xB is an alternate negative sign
        decoded = comp3_decode("06789B", scale=0)
        self.assertEqual(decoded, "-6789")

    def test_comp3_decode_zero(self):
        self.assertEqual(comp3_decode("0C", scale=0), "0")
        self.assertEqual(comp3_decode("00000C", scale=2), "0.00")

    def test_comp3_decode_single_byte(self):
        self.assertEqual(comp3_decode("5C", scale=0), "5")
        self.assertEqual(comp3_decode("5D", scale=0), "-5")

    def test_comp3_encode_positive(self):
        encoded = comp3_encode("123.45", scale=2, total_bytes=3)
        self.assertEqual(encoded, "12345C")

    def test_comp3_encode_negative(self):
        encoded = comp3_encode("-6789", scale=0, total_bytes=3)
        self.assertEqual(encoded, "06789D")

    def test_comp3_encode_zero(self):
        encoded = comp3_encode("0", scale=0, total_bytes=2)
        self.assertEqual(encoded, "000C")

    def test_comp3_encode_padding(self):
        # 42 with total_bytes=4 (7 digits capacity) -> 0000042C
        encoded = comp3_encode("42", scale=0, total_bytes=4)
        self.assertEqual(encoded, "0000042C")

    def test_comp3_encode_fraction_padding(self):
        # "1.2" with scale=3 -> "1.200", total_bytes=3 (5 digits capacity) -> 01200C
        encoded = comp3_encode("1.2", scale=3, total_bytes=3)
        self.assertEqual(encoded, "01200C")

    def test_comp3_encode_overflow_raises(self):
        # "999999" (6 digits) in 2 bytes (capacity 3 digits) must raise ValueError
        with self.assertRaises(ValueError):
            comp3_encode("999999", scale=0, total_bytes=2)

    def test_comp3_roundtrip(self):
        test_values = [
            ("100.50", 2, 4),
            ("-450.75", 2, 4),
            ("999999", 0, 4),
            ("-1", 0, 2),
            ("0.05", 2, 2),
        ]
        for val, scale, total_bytes in test_values:
            encoded = comp3_encode(val, scale=scale, total_bytes=total_bytes)
            decoded = comp3_decode(encoded, scale=scale)
            self.assertEqual(decoded, val)

    def test_parse_comp3_field(self):
        # Simulated record buffer: 4 bytes header, 3 bytes COMP-3 ("12345C"), 2 bytes trailer
        buffer = b"HEAD\x12\x34\x5cOK"
        field_val = parse_comp3_field(buffer, offset=4, length=3, scale=2)
        self.assertEqual(field_val, "123.45")

    def test_format_comp3_field(self):
        data_bytes = format_comp3_field("123.45", scale=2, length=3)
        self.assertEqual(data_bytes, bytes([0x12, 0x34, 0x5C]))

    def test_field_roundtrip(self):
        num = "-8899.12"
        raw = format_comp3_field(num, scale=2, length=5)
        parsed = parse_comp3_field(raw, offset=0, length=5, scale=2)
        self.assertEqual(parsed, num)

    @patch("elmos_mainframe_bridge._get_native_lib", return_value=None)
    def test_fallback_ebcdic(self, mock_lib):
        ebcdic = bytes([0xC8, 0xC5, 0xD3, 0xD3, 0xD6])
        self.assertEqual(ebcdic_to_ascii(ebcdic), "HELLO")

    @patch("elmos_mainframe_bridge._get_native_lib", return_value=None)
    def test_fallback_comp3_decode(self, mock_lib):
        self.assertEqual(comp3_decode("12345C", scale=2), "123.45")
        self.assertEqual(comp3_decode("06789D", scale=0), "-6789")

    @patch("elmos_mainframe_bridge._get_native_lib", return_value=None)
    def test_fallback_comp3_encode(self, mock_lib):
        self.assertEqual(comp3_encode("123.45", scale=2, total_bytes=3), "12345C")
        self.assertEqual(comp3_encode("-6789", scale=0, total_bytes=3), "06789D")

    def test_native_vs_fallback_parity(self):
        """Verify that native core and Python fallback produce 100% bit-identical results."""
        samples = ["123.45", "-6789", "0", "999.99", "-0.01"]
        for s in samples:
            scale = 2 if "." in s else 0
            total_bytes = 4
            # Run with native (if available)
            native_enc = comp3_encode(s, scale=scale, total_bytes=total_bytes)
            native_dec = comp3_decode(native_enc, scale=scale)

            # Run with fallback
            with patch("elmos_mainframe_bridge._get_native_lib", return_value=None):
                fallback_enc = comp3_encode(s, scale=scale, total_bytes=total_bytes)
                fallback_dec = comp3_decode(fallback_enc, scale=scale)

            self.assertEqual(native_enc, fallback_enc)
            self.assertEqual(native_dec, fallback_dec)


if __name__ == "__main__":
    unittest.main()

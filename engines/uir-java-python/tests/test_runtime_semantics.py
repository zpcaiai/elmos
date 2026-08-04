"""Tests for the Java-semantics runtime.

Each test names the Python behaviour it is protecting against.  A test that only
asserted "idiv(7, 2) == 3" would pass just as happily against Python's ``//``;
the cases here are chosen so that the naive implementation fails.
"""

import importlib.util
import math
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "j2p_runtime", Path(__file__).resolve().parents[1] / "runtime" / "j2p_runtime.py"
)
rt = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rt)


class IntegerWrappingTest(unittest.TestCase):
    def test_int_addition_wraps_at_32_bits(self):
        # Python would return 2147483648.
        self.assertEqual(rt.jint(rt.INT_MAX + 1), rt.INT_MIN)

    def test_int_multiplication_wraps(self):
        self.assertEqual(rt.jint(65536 * 65536), 0)

    def test_long_wraps_at_64_bits(self):
        self.assertEqual(rt.jlong(rt.LONG_MAX + 1), rt.LONG_MIN)

    def test_byte_and_short_narrow(self):
        self.assertEqual(rt.jbyte(200), -56)
        self.assertEqual(rt.jshort(40000), -25536)

    def test_char_is_unsigned(self):
        self.assertEqual(rt.jchar(-1), 65535)


class DivisionTest(unittest.TestCase):
    def test_negative_division_truncates_toward_zero(self):
        # Python's -7 // 2 is -4.
        self.assertEqual(rt.idiv("int", -7, 2), -3)
        self.assertEqual(rt.idiv("int", 7, -2), -3)

    def test_remainder_takes_the_sign_of_the_dividend(self):
        # Python's -7 % 2 is 1.
        self.assertEqual(rt.irem("int", -7, 2), -1)
        self.assertEqual(rt.irem("int", 7, -2), 1)

    def test_integer_division_by_zero_raises_the_java_exception(self):
        with self.assertRaises(rt.ArithmeticExceptionJ) as ctx:
            rt.idiv("int", 1, 0)
        self.assertEqual(ctx.exception.message, "/ by zero")

    def test_min_value_divided_by_minus_one_overflows(self):
        self.assertEqual(rt.idiv("int", rt.INT_MIN, -1), rt.INT_MIN)

    def test_floating_division_by_zero_does_not_raise(self):
        self.assertEqual(rt.ddiv(1.0, 0.0), math.inf)
        self.assertTrue(math.isnan(rt.ddiv(0.0, 0.0)))


class ShiftTest(unittest.TestCase):
    def test_int_shift_distance_is_masked_to_five_bits(self):
        # Java's 1 << 32 is 1, not 4294967296.
        self.assertEqual(rt.shl("int", 1, 32), 1)

    def test_long_shift_distance_is_masked_to_six_bits(self):
        self.assertEqual(rt.shl("long", 1, 64), 1)

    def test_unsigned_shift_fills_with_zeros(self):
        self.assertEqual(rt.ushr("int", -1, 28), 15)

    def test_signed_shift_keeps_the_sign(self):
        self.assertEqual(rt.shr("int", -1, 28), -1)


class NarrowingTest(unittest.TestCase):
    def test_cast_of_nan_to_int_is_zero(self):
        # Python's int(nan) raises ValueError.
        self.assertEqual(rt.d2i(math.nan), 0)

    def test_cast_out_of_range_saturates(self):
        self.assertEqual(rt.d2i(1e30), rt.INT_MAX)
        self.assertEqual(rt.d2i(-1e30), rt.INT_MIN)

    def test_cast_truncates_toward_zero(self):
        self.assertEqual(rt.d2i(-2.9), -2)


class AbsTest(unittest.TestCase):
    def test_abs_of_min_value_is_min_value(self):
        # Python's abs would return 2147483648, a value Java can never show.
        self.assertEqual(rt.iabs("int", rt.INT_MIN), rt.INT_MIN)

    def test_generic_abs_refuses_integers(self):
        with self.assertRaises(rt.IllegalStateExceptionJ):
            rt.Math.abs(3)


class DoubleToStringTest(unittest.TestCase):
    def test_whole_numbers_keep_a_decimal_point(self):
        self.assertEqual(rt.jdouble_to_string(1.0), "1.0")

    def test_scientific_threshold_matches_java_not_python(self):
        # Python's repr(1e7) is '10000000.0'.
        self.assertEqual(rt.jdouble_to_string(1e7), "1.0E7")
        self.assertEqual(rt.jdouble_to_string(9999999.0), "9999999.0")

    def test_small_numbers_switch_at_one_thousandth(self):
        self.assertEqual(rt.jdouble_to_string(0.001), "0.001")
        self.assertEqual(rt.jdouble_to_string(0.0001), "1.0E-4")

    def test_special_values_use_java_spelling(self):
        self.assertEqual(rt.jdouble_to_string(math.nan), "NaN")
        self.assertEqual(rt.jdouble_to_string(math.inf), "Infinity")
        self.assertEqual(rt.jdouble_to_string(-math.inf), "-Infinity")
        self.assertEqual(rt.jdouble_to_string(-0.0), "-0.0")

    def test_shortest_round_trip_digits_are_preserved(self):
        self.assertEqual(rt.jdouble_to_string(0.1 + 0.2), "0.30000000000000004")


class StringConversionTest(unittest.TestCase):
    def test_null_becomes_the_word_null(self):
        self.assertEqual(rt.jstr(None), "null")

    def test_booleans_are_lowercase(self):
        self.assertEqual(rt.jstr(True), "true")
        self.assertEqual(rt.jstr(False), "false")

    def test_char_concatenates_as_a_character(self):
        self.assertEqual(rt.concat("", rt.JChar(97)), "a")

    def test_char_used_numerically_is_a_number(self):
        self.assertEqual(rt.num(rt.JChar(97)) + 1, 98)


class ArrayTest(unittest.TestCase):
    def test_new_array_is_zero_filled(self):
        self.assertEqual(list(rt.new_array("int", 3)), [0, 0, 0])
        self.assertEqual(list(rt.new_array("boolean", 2)), [False, False])

    def test_negative_index_is_out_of_bounds_not_a_tail_index(self):
        # Python would happily return the last element for arr[-1].
        arr = rt.array_of("int", [1, 2, 3])
        with self.assertRaises(rt.ArrayIndexOutOfBoundsExceptionJ):
            arr.get(-1)

    def test_index_past_the_end_raises(self):
        arr = rt.array_of("int", [1])
        with self.assertRaises(rt.ArrayIndexOutOfBoundsExceptionJ):
            arr.get(1)

    def test_negative_size_raises(self):
        with self.assertRaises(rt.NegativeArraySizeExceptionJ):
            rt.new_array("int", -1)


class StringApiTest(unittest.TestCase):
    def test_char_at_out_of_range_raises_the_java_exception(self):
        with self.assertRaises(rt.StringIndexOutOfBoundsExceptionJ):
            rt.JString.charAt("ab", 5)

    def test_substring_validates_its_range(self):
        with self.assertRaises(rt.StringIndexOutOfBoundsExceptionJ):
            rt.JString.substring("abc", 2, 1)

    def test_parse_int_rejects_surrounding_space(self):
        with self.assertRaises(rt.NumberFormatExceptionJ):
            rt.Integer.parseInt(" 1")

    def test_parse_int_rejects_values_outside_int_range(self):
        with self.assertRaises(rt.NumberFormatExceptionJ):
            rt.Integer.parseInt("2147483648")

    def test_trim_strips_only_control_and_space(self):
        self.assertEqual(rt.JString.trim(" x "), " x")


class ThrowableTest(unittest.TestCase):
    def test_every_mapped_name_is_a_java_throwable(self):
        for name, cls in rt.EXCEPTION_BY_SIMPLE_NAME.items():
            self.assertTrue(issubclass(cls, rt.JavaThrowable), name)
            self.assertTrue(cls.java_name.startswith("java.lang."), name)

    def test_unmapped_name_is_refused_rather_than_invented(self):
        with self.assertRaises(KeyError):
            rt.throwable_class("SomeVendorException")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

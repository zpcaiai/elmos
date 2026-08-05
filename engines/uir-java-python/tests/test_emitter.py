"""Emitter tests: the generated Python must route Java semantics through the runtime.

These assert on the *shape* of the generated source, which is normally a brittle
thing to test.  It is the right thing to test here: the whole claim of the
emitter is "this operation goes through the runtime helper", and a test that only
ran the result would pass against an emitter that got it right by luck on the
sampled inputs.  The differential tests cover behaviour; these cover intent.
"""

import unittest

from j2p.emit.python import EmitError, PythonEmitter, emit_python
from j2p.frontend.java import parse_java


def emit(body: str, header: str = "public class T {", footer: str = "}") -> str:
    module = parse_java(f"{header}\n{body}\n{footer}".encode("utf-8"), "T.java")
    return emit_python(module)


class ArithmeticRoutingTest(unittest.TestCase):
    def test_int_addition_is_wrapped(self):
        self.assertIn("rt.jint(a + b)", emit("static int f(int a, int b) { return a + b; }"))

    def test_long_addition_uses_the_64_bit_wrapper(self):
        self.assertIn(
            "rt.jlong(a + b)", emit("static long f(long a, long b) { return a + b; }")
        )

    def test_int_division_uses_the_truncating_helper(self):
        code = emit("static int f(int a, int b) { return a / b; }")
        self.assertIn("rt.idiv('int', a, b)", code)
        self.assertNotIn("a / b", code)
        self.assertNotIn("a // b", code)

    def test_int_remainder_uses_the_sign_preserving_helper(self):
        self.assertIn(
            "rt.irem('int', a, b)", emit("static int f(int a, int b) { return a % b; }")
        )

    def test_double_division_uses_the_non_throwing_helper(self):
        self.assertIn(
            "rt.ddiv(a, b)", emit("static double f(double a, double b) { return a / b; }")
        )

    def test_shifts_use_masked_helpers(self):
        code = emit(
            "static int f(int a, int b) { return (a << b) + (a >> b) + (a >>> b); }"
        )
        self.assertIn("rt.shl('int'", code)
        self.assertIn("rt.shr('int'", code)
        self.assertIn("rt.ushr('int'", code)

    def test_unary_minus_is_wrapped_so_min_value_negates_to_itself(self):
        self.assertIn("rt.jint(-a)", emit("static int f(int a) { return -a; }"))

    def test_integral_math_abs_uses_the_wrapping_helper(self):
        self.assertIn(
            "rt.iabs('int', a)", emit("static int f(int a) { return Math.abs(a); }")
        )


class ConversionTest(unittest.TestCase):
    def test_cast_from_double_to_int_saturates(self):
        self.assertIn("rt.d2i(", emit("static int f(double d) { return (int) d; }"))

    def test_cast_to_byte_narrows(self):
        self.assertIn("rt.jbyte(", emit("static int f(int a) { return (byte) a; }"))

    def test_compound_assignment_casts_back_to_the_target_type(self):
        # `int i; i += 2.5;` stays an int in Java.
        code = emit("static int f(int a) { a += 2.5; return a; }")
        self.assertIn("rt.d2i(", code)

    def test_increment_wraps(self):
        self.assertIn("rt.jint(a + 1)", emit("static int f(int a) { a++; return a; }"))

    def test_string_concat_goes_through_java_conversion(self):
        self.assertIn(
            "rt.concat(", emit('static String f(int a) { return "x" + a; }')
        )


class StructureTest(unittest.TestCase):
    def test_static_method_is_emitted_as_a_staticmethod(self):
        code = emit("static int f() { return 1; }")
        self.assertIn("@staticmethod", code)

    def test_for_loop_runs_its_update_on_continue(self):
        # Emitted as while+try/finally precisely so `continue` cannot skip i++.
        code = emit(
            "static int f(int n) { int t = 0; for (int i = 0; i < n; i++) "
            "{ if (i == 1) { continue; } t += i; } return t; }"
        )
        self.assertIn("finally:", code)

    def test_record_accessor_and_field_do_not_collide(self):
        code = emit_python(parse_java(b"record P(int x) {}", "P.java"))
        self.assertIn("self._x = x", code)
        self.assertIn("def x(self):", code)

    def test_generated_source_is_syntactically_valid_python(self):
        code = emit(
            "static int f(int a) { int t = 0; while (a > 0) { t += a; a--; } return t; }"
        )
        compile(code, "T.py", "exec")

    def test_source_map_points_back_at_java_lines(self):
        module = parse_java(
            b"public class T {\n  static int f() {\n    return 1;\n  }\n}", "T.java"
        )
        emitter = PythonEmitter(module)
        emitter.emit()
        entries = emitter.source_map_entries()
        self.assertTrue(entries)
        self.assertTrue(all(e.java_file == "T.java" for e in entries))
        self.assertTrue(any(e.java_line == 3 for e in entries))


class LambdaTest(unittest.TestCase):
    def test_captured_local_is_bound_by_value(self):
        # `n=n` is what makes this correct.  A plain closure would read `n` at
        # call time, and every lambda made in a loop would see the last value.
        code = emit(
            "static void f(int n) { java.util.function.Supplier<Integer> s"
            " = () -> n + 1; }"
        )
        self.assertIn("lambda n=n:", code)

    def test_lambda_parameters_are_not_captured(self):
        code = emit(
            "static void f() { java.util.function.Function<Integer,Integer> g"
            " = x -> x + 1; }"
        )
        self.assertIn("lambda x:", code)
        self.assertNotIn("x=x", code)

    def test_block_lambda_becomes_a_hoisted_def(self):
        code = emit(
            "static void f(int n) { Runnable r = () -> { int t = n; }; }"
        )
        self.assertIn("def _lambda_1(n=n):", code)
        self.assertIn("r = _lambda_1", code)
        compile(code, "T.py", "exec")

    def test_sam_call_becomes_a_call(self):
        code = emit(
            "static int f(java.util.function.Function<Integer,Integer> g)"
            " { return g.apply(1); }"
        )
        self.assertIn("return g(1)", code)

    def test_bound_method_reference_evaluates_its_receiver_once(self):
        code = emit_python(
            parse_java(
                b"class T { int m(int a) { return a; } void f() { Object b = this::m; } }",
                "T.java",
            )
        )
        self.assertIn("_t=self", code)

    def test_arithmetic_inside_a_lambda_still_wraps(self):
        code = emit(
            "static void f() { java.util.function.Function<Integer,Integer> g"
            " = x -> x * 2; }"
        )
        self.assertIn("rt.jint(", code)

    def test_pure_abstract_interface_becomes_an_empty_class(self):
        code = emit_python(parse_java(b"interface I { int m(int a); }", "I.java"))
        self.assertIn("class I:", code)
        compile(code, "I.py", "exec")


class RecordConstructorTest(unittest.TestCase):
    def test_compact_body_runs_before_the_fields_are_assigned(self):
        code = emit_python(
            parse_java(b"record P(int x) { P { x = x + 1; } }", "P.java")
        )
        body = code[code.index("def __init__"):]
        self.assertLess(body.index("x = rt.jint(x + 1)"), body.index("self._x = x"))

    def test_canonical_constructor_assigns_the_fields_itself(self):
        code = emit_python(
            parse_java(b"record P(int x) { P(int x) { this.x = x + 1; } }", "P.java")
        )
        self.assertIn("self._x = rt.jint(x + 1)", code)
        # No second, unconditional assignment appended after the body.
        # The trailing space matters: `self._x ==` in __eq__ is not a store.
        self.assertEqual(code.count("self._x = "), 1)

    def test_record_with_no_components_still_runs_its_compact_body(self):
        code = emit_python(
            parse_java(b"record P() { P { int t = 1; } }", "P.java")
        )
        self.assertIn("t = 1", code)
        compile(code, "P.py", "exec")

    def test_record_with_both_constructor_forms_is_refused(self):
        with self.assertRaises(EmitError):
            emit_python(
                parse_java(
                    b"record P(int x) { P { } P(int x) { this.x = x; } }", "P.java"
                )
            )


class SwitchExpressionTest(unittest.TestCase):
    def test_subject_is_evaluated_once_into_a_temporary(self):
        # Inlining the subject would re-evaluate it per comparison; Java
        # evaluates it exactly once.
        code = emit(
            "static int g(int n) { return n; }\n"
            "static int f(int n) { return switch (g(n)) { case 0 -> 1; "
            "default -> 2; }; }"
        )
        self.assertEqual(code.count("T.g(n)"), 1)
        self.assertIn("_switch_value_1 =", code)

    def test_multiple_labels_become_one_test(self):
        code = emit(
            "static int f(int n) { return switch (n) { case 0, 1 -> 5; "
            "default -> 6; }; }"
        )
        self.assertIn("== 0 or", code)

    def test_switch_expression_in_a_loop_condition_is_refused(self):
        # The subject would be hoisted above the loop and evaluated once.
        with self.assertRaises(EmitError) as ctx:
            emit(
                "static void f(int n) { while ((switch (n) { case 0 -> 1; "
                "default -> 2; }) > 0) { n--; } }"
            )
        self.assertIn("evaluated more than once", str(ctx.exception))

    def test_arrow_switch_statement_emits_without_fallthrough(self):
        code = emit(
            "static int f(int n) { int t = 0; switch (n) { case 0 -> t = 1; "
            "default -> t = 2; } return t; }"
        )
        compile(code, "T.py", "exec")
        self.assertIn("_switch_subject", code)


class UntranslatableTest(unittest.TestCase):
    def test_class_literal_is_refused_with_a_reason(self):
        with self.assertRaises(EmitError) as ctx:
            emit("static Object f() { return T.class; }")
        self.assertIn("reflection", str(ctx.exception))

    def test_unresolved_method_reference_without_a_runtime_equivalent_is_refused(self):
        with self.assertRaises(EmitError) as ctx:
            emit("static Object f() { return Instant::parse; }")
        self.assertIn("outside", str(ctx.exception))

    def test_unresolved_method_reference_with_a_runtime_equivalent_is_emitted(self):
        code = emit("static Object f() { return String::trim; }")
        self.assertIn("rt.JString.trim", code)

    def test_this_delegation_is_refused(self):
        with self.assertRaises(EmitError) as ctx:
            emit_python(
                parse_java(b"class T { T(int a) {} T() { this(1); } }", "T.java")
            )
        self.assertIn("not supported", str(ctx.exception))

    def test_bare_super_call_is_a_no_op(self):
        code = emit_python(
            parse_java(b"class T { T() { super(); } }", "T.java")
        )
        compile(code, "T.py", "exec")


class ReferenceEqualityTest(unittest.TestCase):
    def test_comparing_two_strings_with_double_equals_is_refused(self):
        # Java compares references there; Python would compare values and
        # silently turn a false into a true.
        with self.assertRaises(EmitError) as ctx:
            emit("static boolean f(String a, String b) { return a == b; }")
        self.assertIn("compares identity", str(ctx.exception))

    def test_comparing_two_boxed_integers_is_refused(self):
        with self.assertRaises(EmitError):
            emit("static boolean f(Integer a, Integer b) { return a == b; }")

    def test_comparing_against_null_uses_identity(self):
        code = emit("static boolean f(String a) { return a != null; }")
        self.assertIn("is not None", code)

    def test_primitive_comparison_is_unaffected(self):
        code = emit("static boolean f(int a, int b) { return a == b; }")
        self.assertIn("(a == b)", code)

    def test_unboxing_makes_mixed_comparison_a_value_comparison(self):
        code = emit("static boolean f(Integer a, int b) { return a == b; }")
        self.assertIn("(a == b)", code)


class EmitRefusalTest(unittest.TestCase):
    def _refuses(self, body: str, needle: str):
        with self.assertRaises(EmitError) as ctx:
            emit(body)
        self.assertIn(needle, str(ctx.exception))

    def test_switch_fallthrough_is_refused(self):
        self._refuses(
            "static int f(int a) { switch (a) { case 1: case 2: return 3; "
            "default: return 4; } }",
            "falls through",
        )

    def test_assignment_in_expression_position_is_refused(self):
        self._refuses(
            "static int f(int a) { int b; return (b = a) + b; }",
            "assignment used as a value",
        )

    def test_increment_in_expression_position_is_refused(self):
        self._refuses(
            "static int f(int a) { int[] xs = new int[3]; return xs[a++]; }",
            "used as a value",
        )

    def test_multidimensional_array_is_refused(self):
        self._refuses(
            "static void f() { int[][] g = new int[2][2]; }", "one-dimensional"
        )

    def test_tostring_on_a_plain_class_is_refused(self):
        with self.assertRaises(EmitError) as ctx:
            emit_python(
                parse_java(
                    b"class T { static String f(T t) { return t.toString(); } }",
                    "T.java",
                )
            )
        self.assertIn("identity hash", str(ctx.exception))

    def test_split_with_a_regex_separator_is_refused(self):
        # Java's split takes a regex, and Java's dialect is not Python's, so
        # only a literal separator can be translated with the same meaning.
        with self.assertRaises(EmitError) as ctx:
            emit(r'static String[] f(String s) { return s.split("\\s+"); }')
        self.assertIn("regex syntax", str(ctx.exception))

    def test_split_with_a_non_literal_separator_is_refused(self):
        with self.assertRaises(EmitError):
            emit("static String[] f(String s, String sep) { return s.split(sep); }")

    def test_split_with_a_literal_separator_is_emitted(self):
        code = emit('static String[] f(String s) { return s.split(","); }')
        self.assertIn("rt.JString.split", code)

    def test_unsupported_string_method_is_refused(self):
        self._refuses(
            'static String f(String s) { return s.replaceAll("a", "b"); }',
            "not supported",
        )

    def test_default_method_on_a_functional_interface_is_refused(self):
        self._refuses(
            "static Object f(java.util.function.Function<Integer,Integer> g)"
            " { return g.andThen(g); }",
            "not the single abstract method",
        )

    def test_interface_with_a_default_method_is_refused(self):
        with self.assertRaises(EmitError) as ctx:
            emit_python(
                parse_java(b"interface I { default int m() { return 1; } }", "I.java")
            )
        self.assertIn("default/static methods", str(ctx.exception))

    def test_unknown_static_call_is_refused(self):
        self._refuses(
            "static long f() { return System.currentTimeMillis(); }", "not supported"
        )

    def test_refusal_carries_a_source_location(self):
        with self.assertRaises(EmitError) as ctx:
            emit("static void f() { int[][] g = new int[2][2]; }")
        self.assertEqual(ctx.exception.origin.file, "T.java")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

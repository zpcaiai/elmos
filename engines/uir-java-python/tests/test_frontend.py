"""Front-end tests: what it lowers, and what it refuses to lower.

The refusal tests matter as much as the success tests.  A front end that quietly
accepted a lambda and produced IR without it would make every downstream
guarantee false, so each unsupported construct has a test asserting it raises.
"""

import unittest

from j2p import uir
from j2p.frontend.java import ParseError, UnsupportedConstruct, parse_java


def parse(body: str, header: str = "public class T {", footer: str = "}"):
    return parse_java(f"{header}\n{body}\n{footer}".encode("utf-8"), "T.java")


class LoweringTest(unittest.TestCase):
    def test_class_and_method_are_lowered(self):
        module = parse("static int f(int a) { return a; }")
        self.assertEqual(module.types[0].name, "T")
        self.assertEqual(module.types[0].methods[0].name, "f")
        self.assertEqual(module.types[0].methods[0].return_type, uir.T_INT)

    def test_package_and_imports_are_kept(self):
        module = parse_java(
            b"package a.b;\nimport java.util.List;\nclass T {}", "T.java"
        )
        self.assertEqual(module.package, "a.b")
        self.assertEqual(module.imports, ("java.util.List",))

    def test_long_literal_suffix_is_typed_as_long(self):
        module = parse("static long f() { return 3L; }")
        ret = module.types[0].methods[0].body.body[0]
        self.assertEqual(ret.value.type, uir.T_LONG)

    def test_hex_literal_wraps_into_signed_range(self):
        module = parse("static int f() { return 0xFFFFFFFF; }")
        ret = module.types[0].methods[0].body.body[0]
        self.assertEqual(ret.value.value, -1)

    def test_string_plus_int_becomes_string_concat_not_addition(self):
        module = parse('static String f(int a) { return "x" + a; }')
        ret = module.types[0].methods[0].body.body[0]
        self.assertIsInstance(ret.value, uir.StringConcat)

    def test_int_plus_int_stays_arithmetic(self):
        module = parse("static int f(int a) { return a + a; }")
        ret = module.types[0].methods[0].body.body[0]
        self.assertIsInstance(ret.value, uir.Binary)
        self.assertEqual(ret.value.type, uir.T_INT)

    def test_binary_promotion_widens_to_long(self):
        module = parse("static long f(int a, long b) { return a + b; }")
        ret = module.types[0].methods[0].body.body[0]
        self.assertEqual(ret.value.type, uir.T_LONG)

    def test_shift_result_type_comes_from_the_left_operand_only(self):
        # Asserted on the Binary node itself, not on the enclosing Return: the
        # return statement inserts a coercion to the declared return type, and
        # that cast would mask a wrong operand type underneath it.
        def shift_type(source: str):
            module = parse(source)
            binaries = [n for n in uir.walk(module) if isinstance(n, uir.Binary)]
            self.assertEqual(len(binaries), 1)
            return binaries[0].type

        self.assertEqual(
            shift_type("static long f(long a, int b) { return a << b; }"), uir.T_LONG
        )
        # int << long is an *int* shift.  Promoting it to long would both widen
        # the result and change the shift-distance mask from 5 bits to 6.
        self.assertEqual(
            shift_type("static int f(int a, long b) { return a << b; }"), uir.T_INT
        )

    def test_assignment_to_a_wider_type_inserts_a_cast(self):
        module = parse("static double f(int a) { double d = a; return d; }")
        local = module.types[0].methods[0].body.body[0]
        self.assertIsInstance(local.init, uir.Cast)
        self.assertEqual(local.init.target, uir.T_DOUBLE)

    def test_parameter_shadows_a_field_of_the_same_name(self):
        module = parse_java(
            b"class T { int value; T(int value) { this.value = value; } }", "T.java"
        )
        ctor = module.types[0].methods[0]
        assign = ctor.body.body[0].expr
        self.assertIsInstance(assign.target, uir.FieldAccess)
        # The right-hand side must be the parameter, not the field.
        self.assertIsInstance(assign.value, uir.Name)
        self.assertEqual(assign.value.ident, "value")

    def test_unqualified_field_read_resolves_to_this(self):
        module = parse_java(b"class T { int v; int f() { return v; } }", "T.java")
        ret = module.types[0].methods[0].body.body[0]
        self.assertIsInstance(ret.value, uir.FieldAccess)
        self.assertIsInstance(ret.value.target, uir.This)

    def test_unqualified_static_field_read_resolves_to_the_owner(self):
        module = parse_java(
            b"class T { static int v; static int f() { return v; } }", "T.java"
        )
        ret = module.types[0].methods[0].body.body[0]
        self.assertIsInstance(ret.value, uir.StaticFieldAccess)
        self.assertEqual(ret.value.owner, "T")

    def test_record_components_are_captured(self):
        module = parse_java(b"record P(int x, int y) {}", "P.java")
        self.assertEqual(module.types[0].kind, "record")
        self.assertEqual([c.name for c in module.types[0].record_components], ["x", "y"])

    def test_nested_static_class_is_flattened_to_module_level(self):
        module = parse("static class Inner { static int f() { return 1; } }")
        self.assertEqual([t.name for t in module.types], ["T", "Inner"])
        self.assertEqual(module.types[1].enclosing, "T")

    def test_enum_constants_are_ordered(self):
        module = parse_java(b"enum E { A, B, C }", "E.java")
        self.assertEqual(module.types[0].enum_constants, ("A", "B", "C"))

    def test_text_block_indentation_follows_the_closing_delimiter(self):
        source = 'class T { static String f() { return """\n    a\n      b\n    """; } }'
        module = parse_java(source.encode("utf-8"), "T.java")
        ret = module.types[0].methods[0].body.body[0]
        self.assertEqual(ret.value.value, "a\n  b\n")

    def test_escapes_are_decoded(self):
        module = parse(r'static String f() { return "a\tbA\n"; }')
        ret = module.types[0].methods[0].body.body[0]
        self.assertEqual(ret.value.value, "a\tbA\n")


class RefusalTest(unittest.TestCase):
    def _refuses(self, body: str, needle: str):
        with self.assertRaises(UnsupportedConstruct) as ctx:
            parse(body)
        self.assertIn(needle, str(ctx.exception))

    def test_lambda_is_refused(self):
        self._refuses(
            "static Object f() { return (Runnable) () -> {}; }", "lambda_expression"
        )

    def test_method_reference_is_refused(self):
        self._refuses(
            "static Object f() { return T::f; }", "method_reference"
        )

    def test_varargs_is_refused(self):
        self._refuses("static int f(int... xs) { return 1; }", "varargs")

    def test_generic_method_is_refused(self):
        self._refuses("static <A> A f(A a) { return a; }", "generic method")

    def test_non_static_inner_class_is_refused(self):
        self._refuses("class Inner { }", "non-static inner class")

    def test_float_literal_is_refused(self):
        self._refuses("static double f() { return 1.5f; }", "float literal")

    def test_try_with_resources_is_refused(self):
        self._refuses(
            "static void f() throws Exception { try (AutoCloseable c = null) { } }",
            "try_with_resources",
        )

    def test_labelled_statement_is_refused(self):
        # Rejecting the label itself is stronger than rejecting `break outer`:
        # it also catches `continue outer`, which is the harder of the two.
        self._refuses(
            "static void f() { outer: while (true) { break outer; } }",
            "labeled_statement",
        )

    def test_static_initializer_is_refused(self):
        self._refuses("static { }", "static initializer")

    def test_unparseable_source_is_a_parse_error_not_a_partial_tree(self):
        with self.assertRaises(ParseError):
            parse_java(b"class T { this is not java }", "T.java")

    def test_refusal_carries_a_source_location(self):
        with self.assertRaises(UnsupportedConstruct) as ctx:
            parse("static int f(int... xs) { return 1; }")
        self.assertEqual(ctx.exception.origin.file, "T.java")
        self.assertGreaterEqual(ctx.exception.origin.line, 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

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


class LambdaLoweringTest(unittest.TestCase):
    def test_expression_lambda_is_lowered(self):
        module = parse(
            "static int f(java.util.function.Function<Integer,Integer> g)"
            " { g = x -> x + 1; return g.apply(1); }"
        )
        lambdas = [n for n in uir.walk(module) if isinstance(n, uir.Lambda)]
        self.assertEqual(len(lambdas), 1)
        self.assertIsNotNone(lambdas[0].body_expr)
        self.assertIsNone(lambdas[0].body_block)

    def test_block_lambda_is_lowered(self):
        module = parse(
            "static void f() { Runnable r = () -> { int a = 1; }; }"
        )
        lam = next(n for n in uir.walk(module) if isinstance(n, uir.Lambda))
        self.assertIsNotNone(lam.body_block)

    def test_parameter_type_comes_from_the_target_interface(self):
        module = parse(
            "static void f() { java.util.function.Function<Integer,Integer> g"
            " = x -> x + 1; }"
        )
        lam = next(n for n in uir.walk(module) if isinstance(n, uir.Lambda))
        self.assertEqual(lam.params[0].type, uir.ClassType("Integer"))

    def test_lambda_argument_learns_its_type_from_the_callee_signature(self):
        module = parse(
            "static int use(java.util.function.Function<Integer,Integer> g)"
            " { return g.apply(1); }\n"
            "static int f() { return use(x -> x + 1); }"
        )
        lam = next(n for n in uir.walk(module) if isinstance(n, uir.Lambda))
        self.assertEqual(lam.params[0].type, uir.ClassType("Integer"))

    def test_return_inside_a_lambda_does_not_take_the_methods_return_type(self):
        # The enclosing method returns void; a `return` in the lambda must not
        # be coerced to void.
        module = parse(
            "static void f() { java.util.function.Function<Integer,Integer> g"
            " = x -> { return x + 1; }; }"
        )
        lam = next(n for n in uir.walk(module) if isinstance(n, uir.Lambda))
        ret = lam.body_block.body[0]
        self.assertNotEqual(ret.value.type, uir.T_VOID)

    def test_bound_and_static_method_references_are_distinguished(self):
        module = parse_java(
            b"class T { int m(int a) { return a; } static int s(int a) { return a; }"
            b" void f() { Object b = this::m; Object c = T::s; } }",
            "T.java",
        )
        refs = [n for n in uir.walk(module) if isinstance(n, uir.MethodRef)]
        self.assertEqual([r.ref_kind for r in refs], ["bound", "static"])

    def test_wildcard_type_argument_is_recorded_as_unknown(self):
        module = parse("static void f(java.util.List<? extends Number> xs) { }")
        param = module.types[0].methods[0].params[0]
        self.assertIsInstance(param.type.args[0], uir.UnknownType)


class RecordAndSwitchLoweringTest(unittest.TestCase):
    def test_compact_constructor_parameters_are_the_components(self):
        module = parse_java(b"record P(int x) { P { x = x + 1; } }", "P.java")
        compact = module.types[0].compact_constructor
        self.assertIsNotNone(compact)
        self.assertEqual([p.name for p in compact.params], ["x"])

    def test_compact_constructor_body_assigns_the_parameter_not_the_field(self):
        # `x = x + 1` inside a compact constructor rebinds the *parameter*.
        # Resolving it to the field would make the validation a no-op that
        # writes the unvalidated value.
        module = parse_java(b"record P(int x) { P { x = x + 1; } }", "P.java")
        assign = module.types[0].compact_constructor.body.body[0].expr
        self.assertIsInstance(assign.target, uir.Name)
        self.assertEqual(assign.target.ident, "x")

    def test_canonical_constructor_is_kept_as_a_constructor(self):
        module = parse_java(
            b"record P(int x) { P(int x) { this.x = x; } }", "P.java"
        )
        self.assertIsNone(module.types[0].compact_constructor)
        self.assertTrue(any(m.is_constructor for m in module.types[0].methods))

    def test_arrow_switch_rule_is_terminated(self):
        module = parse(
            "static int f(int n) { int t = 0; switch (n) { case 0 -> t = 1; "
            "default -> t = 2; } return t; }"
        )
        switch = next(n for n in uir.walk(module) if isinstance(n, uir.Switch))
        # Every arrow case must end in something terminal, because an arrow
        # rule cannot fall through.
        for case in switch.cases:
            self.assertIsInstance(
                case.body[-1], (uir.Break, uir.Return, uir.Throw)
            )

    def test_switch_expression_is_an_expression_node(self):
        module = parse(
            "static int f(int n) { return switch (n) { case 0 -> 1; "
            "default -> 2; }; }"
        )
        found = [n for n in uir.walk(module) if isinstance(n, uir.SwitchExpr)]
        self.assertEqual(len(found), 1)
        self.assertEqual(len(found[0].cases), 2)

    def test_yield_form_switch_expression_is_lowered(self):
        module = parse(
            'static String f(int n) { return switch (n) { case 1: yield "a"; '
            'default: yield "b"; }; }'
        )
        found = next(n for n in uir.walk(module) if isinstance(n, uir.SwitchExpr))
        self.assertEqual(len(found.cases), 2)

    def test_method_reference_to_an_outside_type_is_recorded_as_unresolved(self):
        module = parse("static Object f() { return String::trim; }")
        ref = next(n for n in uir.walk(module) if isinstance(n, uir.MethodRef))
        self.assertEqual(ref.ref_kind, "unresolved")
        self.assertEqual((ref.owner, ref.name), ("String", "trim"))

    def test_class_literal_is_represented(self):
        module = parse("static Object f() { return T.class; }")
        lit = next(n for n in uir.walk(module) if isinstance(n, uir.ClassLiteral))
        self.assertEqual(lit.name, "T")

    def test_explicit_constructor_invocation_is_represented(self):
        module = parse_java(
            b"class T { T(int a) {} T() { this(1); } }", "T.java"
        )
        call = next(n for n in uir.walk(module) if isinstance(n, uir.ConstructorCall))
        self.assertEqual(call.kind, "this")
        self.assertEqual(len(call.args), 1)


class ErasureAndResourceLoweringTest(unittest.TestCase):
    def test_generic_method_type_variable_erases_to_unknown(self):
        # Java erases generics at run time, so a type variable carries nothing
        # Python lacks.  Recording it as UnknownType keeps that visible.
        module = parse("static <A> A f(A a) { return a; }")
        method = module.types[0].methods[0]
        self.assertIsInstance(method.return_type, uir.UnknownType)
        self.assertIn("type-variable:A", method.return_type.reason)

    def test_type_variable_leaves_scope_after_the_method(self):
        module = parse(
            "static <A> A f(A a) { return a; }\n"
            "static A g(A a) { return a; }"
        )
        # `A` outside the generic method is an ordinary (unknown) class name,
        # not the erased type variable.
        second = module.types[0].methods[1]
        self.assertIsInstance(second.return_type, uir.ClassType)

    def test_generic_class_declaration_is_erased(self):
        module = parse_java(b"class Box<T> { T value; }", "Box.java")
        self.assertIsInstance(module.types[0].fields[0].type, uir.UnknownType)

    def test_varargs_parameter_is_an_array(self):
        module = parse("static int f(int... xs) { return xs.length; }")
        param = module.types[0].methods[0].params[0]
        self.assertTrue(param.is_varargs)
        self.assertIsInstance(param.type, uir.ArrayType)

    def test_try_with_resources_records_its_resources_in_order(self):
        module = parse(
            "static void f() { try (R a = null; R b = null) { } finally { } }"
        )
        node = next(n for n in uir.walk(module) if isinstance(n, uir.Try))
        self.assertEqual([r.name for r in node.resources], ["a", "b"])

    def test_comments_inside_an_argument_list_are_dropped(self):
        module = parse("static int f() { return g(1 /* here */, 2); }\n"
                       "static int g(int a, int b) { return a; }")
        call = next(n for n in uir.walk(module) if isinstance(n, uir.Call))
        self.assertEqual(len(call.args), 2)

    def test_text_block_line_continuation_joins_lines(self):
        source = 'class T { static String f() { return """\n    a\\\n    b\n    """; } }'
        module = parse_java(source.encode("utf-8"), "T.java")
        ret = module.types[0].methods[0].body.body[0]
        self.assertEqual(ret.value.value, "ab\n")

    def test_throwing_switch_rule_is_an_expression_node(self):
        module = parse(
            "static int f(int n) { return switch (n) { case 0 -> 1; "
            "default -> throw new IllegalStateException(\"no\"); }; }"
        )
        found = [n for n in uir.walk(module) if isinstance(n, uir.ThrowExpr)]
        self.assertEqual(len(found), 1)


class RefusalTest(unittest.TestCase):
    def _refuses(self, body: str, needle: str):
        with self.assertRaises(UnsupportedConstruct) as ctx:
            parse(body)
        self.assertIn(needle, str(ctx.exception))

    def test_non_static_inner_class_is_refused(self):
        self._refuses("class Inner { }", "non-static inner class")

    def test_float_literal_is_refused(self):
        self._refuses("static double f() { return 1.5f; }", "float literal")

    def test_try_with_resources_over_an_existing_variable_is_refused(self):
        self._refuses(
            "static void f(AutoCloseable c) throws Exception { try (c) { } }",
            "existing variable",
        )

    def test_labelled_statement_is_refused(self):
        # Rejecting the label itself is stronger than rejecting `break outer`:
        # it also catches `continue outer`, which is the harder of the two.
        self._refuses(
            "static void f() { outer: while (true) { break outer; } }",
            "labeled_statement",
        )

    def test_switch_expression_without_a_default_is_refused(self):
        self._refuses(
            "static int f(int n) { return switch (n) { case 0 -> 1; case 1 -> 2; }; }",
            "without a default",
        )

    def test_switch_expression_case_with_statements_is_refused(self):
        self._refuses(
            "static int f(int n) { return switch (n) { case 0 -> { int t = 1; "
            "yield t; } default -> 2; }; }",
            "switch rule with a statement body",
        )

    def test_static_initializer_is_refused(self):
        self._refuses("static { }", "static initializer")

    def test_unparseable_source_is_a_parse_error_not_a_partial_tree(self):
        with self.assertRaises(ParseError):
            parse_java(b"class T { this is not java }", "T.java")

    def test_refusal_carries_a_source_location(self):
        with self.assertRaises(UnsupportedConstruct) as ctx:
            parse("static void f() { outer: while (true) { break outer; } }")
        self.assertEqual(ctx.exception.origin.file, "T.java")
        self.assertGreaterEqual(ctx.exception.origin.line, 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

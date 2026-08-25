"""Whole-program symbol resolution.

Every test here asserts something that is *impossible* to get right one file at
a time, which is the whole reason the index exists.  The refusal tests matter as
much as the success ones: an index makes more calls resolvable, and a resolvable
call that is emitted wrongly is worse than one that was refused.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from j2p.emit.python import EmitError, PythonEmitter  # noqa: E402
from j2p.frontend.java import parse_java_file  # noqa: E402
from j2p.program import scan_files, scan_tree  # noqa: E402
from j2p.uir import ClassType, PrimitiveType  # noqa: E402

CORPUS_PROGRAM = Path(__file__).resolve().parents[1] / "corpus" / "program"


class _Tree:
    """A throwaway directory of Java sources, scanned into an index."""

    def __init__(self, files: dict[str, str]) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="j2p-prog-test-")
        self.root = Path(self._tmp.name)
        for name, text in files.items():
            (self.root / name).write_text(text, encoding="utf-8")
        self.index = scan_files(sorted(self.root.glob("*.java")))

    def module(self, name: str):
        return parse_java_file(self.root / name, index=self.index)

    def emit(self, name: str) -> str:
        return PythonEmitter(self.module(name), index=self.index).emit()

    def close(self) -> None:
        self._tmp.cleanup()


class IndexTest(unittest.TestCase):
    def test_nested_type_is_qualified_through_its_enclosing_type(self):
        tree = _Tree({
            "Outer.java": "package p; class Outer { static class Inner { int v() { return 1; } } }",
            "Inner.java": "package p; class Inner { int w() { return 2; } }",
        })
        self.addCleanup(tree.close)
        # Flattening the nested name to `p.Inner` would let it displace the
        # top-level class of the same name -- and which one won would depend on
        # directory iteration order.
        self.assertIn("p.Outer.Inner", tree.index.types)
        self.assertIn("p.Inner", tree.index.types)
        self.assertEqual(tree.index.types["p.Inner"].source_file.split("/")[-1], "Inner.java")

    def test_nested_type_resolves_by_the_way_it_is_written(self):
        tree = _Tree({
            "Outer.java": "package p; class Outer { static class Inner { int v() { return 1; } } }",
        })
        self.addCleanup(tree.close)
        found = tree.index.resolve("Outer.Inner", "p", ())
        self.assertIsNotNone(found)
        self.assertEqual(found.qualified_name, "p.Outer.Inner")

    def test_a_duplicate_qualified_name_is_reported_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            (root / "b").mkdir()
            (root / "a" / "Dup.java").write_text("package p; class Dup { }")
            (root / "b" / "Dup.java").write_text("package p; class Dup { }")
            index = scan_tree(root)
        self.assertEqual(len(index.collisions), 1)
        self.assertEqual(index.collisions[0][0], "p.Dup")

    def test_an_explicit_import_beats_a_same_package_type(self):
        tree = _Tree({
            "Here.java": "package p; class Target { }",
            "There.java": "package q; class Target { }",
        })
        self.addCleanup(tree.close)
        found = tree.index.resolve("Target", "p", ("q.Target",))
        self.assertEqual(found.qualified_name, "q.Target")

    def test_an_ambiguous_simple_name_resolves_to_nothing(self):
        tree = _Tree({
            "Here.java": "package p; class Target { }",
            "There.java": "package q; class Target { }",
        })
        self.addCleanup(tree.close)
        self.assertIsNone(tree.index.resolve("Target", None, ()))

    def test_a_signature_the_front_end_cannot_lower_still_records_the_method(self):
        # If one exotic parameter type erased the whole signature, every
        # *caller* would become unresolvable too.
        tree = _Tree({
            "Odd.java": "class Odd { static int f(int[][] m) { return 1; } }",
        })
        self.addCleanup(tree.close)
        info = tree.index.resolve("Odd", None, ())
        self.assertIsNotNone(info.method("f"))
        self.assertEqual(info.method("f").return_type, PrimitiveType("int"))


class CrossFileTypingTest(unittest.TestCase):
    def test_a_call_into_another_file_has_a_type(self):
        tree = _Tree({
            "Helper.java": "class Helper { static int twice(int v) { return v * 2; } }",
            "Main.java": "class Main { static void main(String[] a) { int x = Helper.twice(2); } }",
        })
        self.addCleanup(tree.close)
        module = tree.module("Main.java")
        body = module.types[0].methods[0].body.body
        self.assertEqual(body[0].type, PrimitiveType("int"))

    def test_the_same_call_has_no_type_without_the_index(self):
        # The measurement this whole change was chosen from: this is the state
        # 94% of the failing files were in.
        tree = _Tree({
            "Helper.java": "class Helper { static int twice(int v) { return v * 2; } }",
            "Main.java": "class Main { static void main(String[] a) { int x = Helper.twice(2); } }",
        })
        self.addCleanup(tree.close)
        module = parse_java_file(tree.root / "Main.java")
        with self.assertRaises(EmitError):
            PythonEmitter(module).emit()


class CrossFileEmissionTest(unittest.TestCase):
    def _tree(self) -> _Tree:
        return _Tree({
            "Helper.java": (
                "class Helper {\n"
                "  static final int BASE = 7;\n"
                "  private final int f;\n"
                "  Helper(int f) { this.f = f; }\n"
                "  static int twice(int v) { return v * 2; }\n"
                "  static int total(int... vs) { int s = 0; for (int v : vs) { s += v; } return s; }\n"
                "  int scale(int v) { return v * f; }\n"
                "}\n"
            ),
            "Main.java": (
                "class Main {\n"
                "  static int run(int v) { return Helper.twice(v); }\n"
                "}\n"
            ),
        })

    def test_a_cross_file_class_is_imported_as_a_module_not_a_name(self):
        tree = self._tree()
        self.addCleanup(tree.close)
        code = tree.emit("Main.java")
        # `from Helper import Helper` breaks the moment two classes call each
        # other, which Java allows freely: the second module to start importing
        # finds the first only partly initialised.
        self.assertIn("import Helper as _m_Helper", code)
        self.assertNotIn("from Helper import", code)
        self.assertIn("_m_Helper.Helper.twice", code)

    def test_a_type_declared_in_this_file_is_not_imported_from_itself(self):
        tree = _Tree({
            "Solo.java": "class Solo { static int f() { return 1; } static int g() { return Solo.f(); } }",
        })
        self.addCleanup(tree.close)
        code = tree.emit("Solo.java")
        self.assertNotIn("import Solo", code)

    def test_a_static_field_in_another_file_resolves(self):
        tree = _Tree({
            "Helper.java": "class Helper { static final int BASE = 7; }",
            "Main.java": "class Main { static int f() { return Helper.BASE; } }",
        })
        self.addCleanup(tree.close)
        self.assertIn("_m_Helper.Helper.BASE", tree.emit("Main.java"))

    def test_a_field_that_is_not_static_over_there_is_refused_here(self):
        tree = _Tree({
            "Helper.java": "class Helper { int base = 7; }",
            "Main.java": "class Main { static int f() { return Helper.base; } }",
        })
        self.addCleanup(tree.close)
        with self.assertRaisesRegex(EmitError, "not a static field"):
            tree.emit("Main.java")

    def test_a_method_that_does_not_exist_over_there_is_refused(self):
        tree = _Tree({
            "Helper.java": "class Helper { static int twice(int v) { return v * 2; } }",
            "Main.java": "class Main { static int f() { return Helper.thrice(1); } }",
        })
        self.addCleanup(tree.close)
        with self.assertRaisesRegex(EmitError, "not declared in the scanned program"):
            tree.emit("Main.java")

    def test_same_arity_overloads_in_another_file_are_refused(self):
        tree = _Tree({
            "Helper.java": (
                "class Helper {\n"
                "  static int f(int v) { return v; }\n"
                "  static int f(String v) { return 0; }\n"
                "}\n"
            ),
            "Main.java": "class Main { static int g() { return Helper.f(1); } }",
        })
        self.addCleanup(tree.close)
        with self.assertRaisesRegex(EmitError, "2 overloads taking 1 arguments"):
            tree.emit("Main.java")

    def test_arity_distinct_overloads_in_another_file_resolve(self):
        # Argument count is present at run time, so this choice is exact.
        tree = _Tree({
            "Helper.java": (
                "class Helper {\n"
                "  static int f(int v) { return v; }\n"
                "  static int f(int v, int w) { return v + w; }\n"
                "}\n"
            ),
            "Main.java": "class Main { static int g() { return Helper.f(1, 2); } }",
        })
        self.addCleanup(tree.close)
        self.assertIn("_m_Helper.Helper.f(1, 2)", tree.emit("Main.java"))

    def test_an_overload_with_no_matching_arity_is_refused(self):
        tree = _Tree({
            "Helper.java": (
                "class Helper {\n"
                "  static int f(int v) { return v; }\n"
                "  static int f(int v, int w) { return v + w; }\n"
                "}\n"
            ),
            "Main.java": "class Main { static int g() { return Helper.f(1, 2, 3); } }",
        })
        self.addCleanup(tree.close)
        with self.assertRaisesRegex(EmitError, "no overload taking 3"):
            tree.emit("Main.java")

    def test_an_instance_method_called_statically_is_refused(self):
        tree = _Tree({
            "Helper.java": "class Helper { int f(int v) { return v; } }",
            "Main.java": "class Main { static int g() { return Helper.f(1); } }",
        })
        self.addCleanup(tree.close)
        with self.assertRaisesRegex(EmitError, "instance method"):
            tree.emit("Main.java")

    def test_varargs_are_packed_against_the_other_files_signature(self):
        tree = _Tree({
            "Helper.java": (
                "class Helper { static int total(int... vs) { int s = 0;"
                " for (int v : vs) { s += v; } return s; } }"
            ),
            "Main.java": "class Main { static int g() { return Helper.total(1, 2, 3); } }",
        })
        self.addCleanup(tree.close)
        # Passing 1, 2, 3 straight through would give the callee three
        # parameters where it declares one.
        self.assertIn("array_of('int', [1, 2, 3])", tree.emit("Main.java"))

    def test_constructing_another_files_class_checks_the_arity(self):
        tree = _Tree({
            "Helper.java": "class Helper { Helper(int a, int b) { } }",
            "Main.java": "class Main { static void g() { Helper h = new Helper(1); } }",
        })
        self.addCleanup(tree.close)
        with self.assertRaisesRegex(EmitError, "passes 1 arguments"):
            tree.emit("Main.java")

    def test_same_arity_constructors_in_another_file_are_refused(self):
        # Java picks between these by the static type of the argument, which is
        # not there at run time.
        tree = _Tree({
            "Helper.java": "class Helper { Helper(int a) { } Helper(String a) { } }",
            "Main.java": "class Main { static void g() { Helper h = new Helper(1); } }",
        })
        self.addCleanup(tree.close)
        with self.assertRaisesRegex(EmitError, "could reach 2 constructors"):
            tree.emit("Main.java")

    def test_arity_distinct_constructors_in_another_file_are_allowed(self):
        # Argument *count* is present at run time, so this choice is exact.
        tree = _Tree({
            "Helper.java": "class Helper { Helper(int a) { } Helper(int a, int b) { } }",
            "Main.java": "class Main { static void g() { Helper h = new Helper(1, 2); } }",
        })
        self.addCleanup(tree.close)
        self.assertIn("_m_Helper.Helper(1, 2)", tree.emit("Main.java"))

    def test_new_on_an_abstract_class_in_another_file_is_refused(self):
        tree = _Tree({
            "Base.java": "abstract class Base { abstract int f(); }",
            "Main.java": "class Main { static void g() { Base b = new Base(); } }",
        })
        self.addCleanup(tree.close)
        with self.assertRaisesRegex(EmitError, "anonymous subclass"):
            tree.emit("Main.java")

    def test_a_record_in_another_file_is_constructed_by_component_count(self):
        tree = _Tree({
            "Pair.java": "record Pair(int a, int b) { }",
            "Main.java": "class Main { static void g() { Pair p = new Pair(1); } }",
        })
        self.addCleanup(tree.close)
        with self.assertRaisesRegex(EmitError, "2 components"):
            tree.emit("Main.java")

    def test_a_lambda_implements_an_interface_from_another_file(self):
        tree = _Tree({
            "Adjust.java": "interface Adjust { int apply(int v); }",
            "Main.java": (
                "class Main { static int g() { Adjust a = v -> v + 1;"
                " return a.apply(2); } }"
            ),
        })
        self.addCleanup(tree.close)
        code = tree.emit("Main.java")
        self.assertIn("lambda", code)
        # The SAM call is the call: dispatching by name would look for a method
        # on a Python function object.
        self.assertIn("a(2)", code)

    def test_a_method_inherited_from_a_superclass_in_another_file_resolves(self):
        tree = _Tree({
            "Base.java": "class Base { int shared(int v) { return v; } }",
            "Child.java": "class Child extends Base { }",
            "Main.java": (
                "class Main { static int g(Child c) { return c.shared(1); } }"
            ),
        })
        self.addCleanup(tree.close)
        self.assertIn("c.shared(1)", tree.emit("Main.java"))

    def test_toString_on_a_plain_class_from_another_file_is_refused(self):
        tree = _Tree({
            "Plain.java": "class Plain { int v = 1; }",
            "Main.java": (
                "class Main { static String g(Plain p) { return p.toString(); } }"
            ),
        })
        self.addCleanup(tree.close)
        with self.assertRaisesRegex(EmitError, "identity hash"):
            tree.emit("Main.java")


class EnumRepresentationTest(unittest.TestCase):
    def test_a_constant_is_a_named_singleton_not_its_ordinal(self):
        tree = _Tree({"Op.java": "enum Op { ADD, SUB }"})
        self.addCleanup(tree.close)
        code = tree.emit("Op.java")
        # As an ordinal, `System.out.println(Op.ADD)` printed `0`; Java prints
        # `ADD`.
        self.assertIn("ADD = rt.JEnum('Op', 'ADD', 0)", code)
        self.assertIn("SUB = rt.JEnum('Op', 'SUB', 1)", code)

    def test_two_constants_compare_by_identity(self):
        tree = _Tree({
            "Op.java": "enum Op { ADD, SUB }",
            "Main.java": (
                "class Main { static boolean g(Op o) { return o == Op.ADD; } }"
            ),
        })
        self.addCleanup(tree.close)
        code = tree.emit("Main.java")
        self.assertIn(" is ", code)
        self.assertNotIn(" == ", code)

    def test_name_and_ordinal_are_distinct_observations(self):
        tree = _Tree({
            "Op.java": "enum Op { ADD, SUB }",
            "Main.java": (
                "class Main { static String g(Op o) { return o.name() + o.ordinal(); } }"
            ),
        })
        self.addCleanup(tree.close)
        code = tree.emit("Main.java")
        self.assertIn("o.name()", code)
        self.assertIn("o.ordinal()", code)


class NamespaceClashTest(unittest.TestCase):
    def test_a_field_and_a_method_of_the_same_name_are_refused(self):
        # Found by the multi-file differential, not by inspection: `self.factor
        # = factor` in __init__ overwrote the method, and the call failed with a
        # TypeError nowhere near the declaration.
        tree = _Tree({
            "Rate.java": (
                "class Rate { private final int factor; Rate(int f) { this.factor = f; }"
                " int factor() { return factor; } }"
            ),
        })
        self.addCleanup(tree.close)
        with self.assertRaisesRegex(EmitError, "separate namespaces"):
            tree.emit("Rate.java")

    def test_a_record_component_and_its_accessor_are_not_a_clash(self):
        tree = _Tree({"Pair.java": "record Pair(int a, int b) { }"})
        self.addCleanup(tree.close)
        self.assertIn("def a(self):", tree.emit("Pair.java"))


class OverloadedConstructorTest(unittest.TestCase):
    """Java selects by static argument types; Python has argument count.

    Where the two coincide -- arities all different -- the choice is exact and
    is emitted.  Where they do not, it is refused.
    """

    def test_arity_distinct_constructors_dispatch_on_argument_count(self):
        tree = _Tree({
            "C.java": (
                "class C { int v; C() { this.v = 1; } C(int a) { this.v = a; }"
                " C(int a, int b) { this.v = a + b; } }"
            ),
        })
        self.addCleanup(tree.close)
        code = tree.emit("C.java")
        self.assertIn("def __init__(self, *_args):", code)
        self.assertIn("if len(_args) == 0:", code)
        self.assertIn("if len(_args) == 1:", code)
        self.assertIn("if len(_args) == 2:", code)

    def test_a_field_initialiser_runs_before_every_constructor_body(self):
        tree = _Tree({
            "C.java": (
                'class C { String label = "none"; C() { } C(int a) { this.label = "one"; } }'
            ),
        })
        self.addCleanup(tree.close)
        code = tree.emit("C.java")
        prologue = code.index("self.label = 'none'")
        dispatch = code.index("if len(_args) == 0:")
        # Java runs field initialisers before the selected constructor body, so
        # emitting them inside one branch would leave the others unset.
        self.assertLess(prologue, dispatch)

    def test_two_constructors_of_the_same_arity_are_refused(self):
        tree = _Tree({
            "C.java": "class C { C(int a) { } C(String a) { } }",
        })
        self.addCleanup(tree.close)
        with self.assertRaisesRegex(EmitError, "static types of the arguments"):
            tree.emit("C.java")

    def test_an_overloaded_varargs_constructor_is_refused(self):
        tree = _Tree({
            "C.java": "class C { C(int a) { } C(int a, int... rest) { } }",
        })
        self.addCleanup(tree.close)
        with self.assertRaisesRegex(EmitError, "arity is not fixed"):
            tree.emit("C.java")


class MultiDimensionalArrayTest(unittest.TestCase):
    def test_a_two_dimensional_array_type_is_refused_not_flattened(self):
        # tree-sitter puts both bracket pairs in one `dimensions` node, so the
        # obvious recursion produced `int[]` for `int[][]` -- a wrong type, which
        # is worse than a refusal because every index of it is then mistyped.
        from j2p.frontend.java import UnsupportedConstruct, parse_java

        with self.assertRaisesRegex(UnsupportedConstruct, "multi-dimensional"):
            parse_java(b"class T { static int f(int[][] m) { return 1; } }", "T.java")


class EnclosingStaticCallTest(unittest.TestCase):
    """A nested type may call the enclosing class's statics unqualified.

    The emitter flattens nested types into separate top-level Python classes, so
    the qualification Java left implicit has to be put back.  This was the
    largest single remaining blocker in the survey.
    """

    def test_a_nested_type_may_call_an_enclosing_static(self):
        tree = _Tree({
            "R.java": (
                "public class R {\n"
                "  public record Inner(String id) {\n"
                "    public Inner { require(id, \"id\"); }\n"
                "  }\n"
                "  static void require(String v, String n) {\n"
                "    if (v == null) throw new IllegalArgumentException(n);\n"
                "  }\n"
                "}\n"
            ),
        })
        self.addCleanup(tree.close)
        self.assertIn("R.require(id, 'id')", tree.emit("R.java"))

    def test_an_ambiguous_unqualified_static_is_refused(self):
        # Java resolves this by lexical nesting; the flattened IR no longer
        # carries that, so guessing would be a coin flip.
        tree = _Tree({
            "A.java": (
                "public class A {\n"
                "  static class One { static void helper() { } }\n"
                "  static class Two { static void helper() { } }\n"
                "  static class Three { static void go() { helper(); } }\n"
                "}\n"
            ),
        })
        self.addCleanup(tree.close)
        with self.assertRaisesRegex(EmitError, "lexical nesting"):
            tree.emit("A.java")


class FileScopeTest(unittest.TestCase):
    """A file's own declarations win over anything else in the program."""

    def test_a_files_own_nested_enum_beats_an_ambiguous_global_name(self):
        # Three files declare a nested `Decision`.  Resolving globally makes the
        # name ambiguous and therefore unresolvable *inside the file that
        # declares it*, which is where it is least ambiguous of all.
        files = {
            f"Holder{n}.java": (
                f"package p{n};\n"
                f"public class Holder{n} {{\n"
                "  public enum Decision { PASS, FAIL }\n"
                "  static boolean ok(Decision d) { return d == Decision.PASS; }\n"
                "}\n"
            )
            for n in (1, 2, 3)
        }
        tree = _Tree(files)
        self.addCleanup(tree.close)
        for n in (1, 2, 3):
            with self.subTest(n=n):
                # `==` on two enums is identity, which the singletons reproduce.
                self.assertIn(" is ", tree.emit(f"Holder{n}.java"))

    def test_the_global_table_is_still_used_for_types_from_elsewhere(self):
        tree = _Tree({
            "Helper.java": "class Helper { static int twice(int v) { return v * 2; } }",
            "Main.java": "class Main { static int g() { return Helper.twice(1); } }",
        })
        self.addCleanup(tree.close)
        self.assertIn("_m_Helper.Helper.twice", tree.emit("Main.java"))


class VarInferenceTest(unittest.TestCase):
    """`var` is not a type; it is whatever the initialiser is."""

    def test_var_takes_the_initialisers_type(self):
        tree = _Tree({
            "V.java": (
                "class V { static int f(String s) { var t = s.trim();"
                " return t.length(); } }"
            ),
        })
        self.addCleanup(tree.close)
        # Without inference `t` is a class named "var" and `t.length()` has an
        # unresolvable receiver -- which is how it showed up all over the survey.
        self.assertIn("rt.JString.length(t)", tree.emit("V.java"))

    def test_var_in_a_for_each_takes_the_element_type(self):
        tree = _Tree({
            "V.java": (
                "import java.util.List;\n"
                "class V { static void f(List<String> l) {"
                " for (var w : l) { w.trim(); } } }"
            ),
        })
        self.addCleanup(tree.close)
        self.assertIn("rt.JString.trim(w)", tree.emit("V.java"))

    def test_a_factory_call_carries_its_element_type(self):
        tree = _Tree({
            "V.java": (
                "import java.util.List;\n"
                "class V { static void f() { var l = List.of(\"a\");"
                " for (var w : l) { w.trim(); } } }"
            ),
        })
        self.addCleanup(tree.close)
        self.assertIn("rt.JString.trim(w)", tree.emit("V.java"))

    def test_a_factory_with_mixed_element_types_stays_unknown(self):
        # Java infers List<Object> here; claiming String would give the emitter
        # a type the elements do not all have.
        tree = _Tree({
            "V.java": (
                "import java.util.List;\n"
                "class V { static void f() { var l = List.of(\"a\", 1);"
                " for (var w : l) { w.trim(); } } }"
            ),
        })
        self.addCleanup(tree.close)
        with self.assertRaises(EmitError):
            tree.emit("V.java")


class SurveyHonestyTest(unittest.TestCase):
    def test_a_class_level_refusal_marks_the_measurement_as_truncated(self):
        # The class is refused before any body is walked, so the four blockers
        # inside the method are never seen.  Reporting "1 blocker" here is what
        # made the previous projection promise 137 files and deliver 28.
        from j2p.emit.python import survey_report

        tree = _Tree({
            "C.java": (
                "class C { int v; C(int a) { } C(String a) { }"
                " void m() { Object x = C.class; } }"
            ),
        })
        self.addCleanup(tree.close)
        result = survey_report(tree.module("C.java"), index=tree.index)
        self.assertTrue(result.truncated)
        self.assertEqual(result.truncated_types, ["C"])

    def test_a_body_level_refusal_is_a_complete_measurement(self):
        from j2p.emit.python import survey_report

        tree = _Tree({
            "C.java": "class C { void m() { Object x = C.class; } }",
        })
        self.addCleanup(tree.close)
        result = survey_report(tree.module("C.java"), index=tree.index)
        self.assertFalse(result.truncated)
        self.assertTrue(result.blockers)


class CorpusProgramTest(unittest.TestCase):
    def test_every_file_of_the_cross_file_corpus_translates(self):
        sources = sorted(CORPUS_PROGRAM.glob("*.java"))
        self.assertGreaterEqual(len(sources), 5)
        index = scan_files(sources)
        self.assertEqual(index.unscanned, [])
        for source in sources:
            with self.subTest(source=source.name):
                module = parse_java_file(source, index=index)
                PythonEmitter(module, index=index).emit()

    def test_the_entry_point_is_refused_without_the_index(self):
        module = parse_java_file(CORPUS_PROGRAM / "Ledger.java")
        with self.assertRaises(EmitError):
            PythonEmitter(module).emit()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

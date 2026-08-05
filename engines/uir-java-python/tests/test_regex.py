"""`String.matches`, and the parts of the two regex dialects that disagree.

Java's regex and Python's look identical and are not. The translation covers a
verified subset and refuses the rest by name; these tests pin down both halves.
The three silent differences — `.`, the ASCII-only predefined classes, and
whole-string anchoring — each get a test that fails if the rewrite is removed.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

import j2p_runtime as rt  # noqa: E402
from j2p.emit.python import EmitError, emit_python  # noqa: E402
from j2p.emit.regex import JAVA_DOT, UnsupportedRegex, translate  # noqa: E402
from j2p.frontend.java import parse_java  # noqa: E402


def emit(body: str) -> str:
    source = f"public class T {{\n{body}\n}}".encode("utf-8")
    return emit_python(parse_java(source, "T.java"))


class TranslationTest(unittest.TestCase):
    def test_dot_becomes_javas_line_terminator_class(self):
        # Java's `.` excludes \n \r     ; Python's excludes only
        # \n, so leaving it alone makes the translation match strings the
        # original rejected.
        self.assertEqual(translate("a.c"), f"a{JAVA_DOT}c")

    def test_a_dot_inside_a_character_class_is_a_literal(self):
        self.assertEqual(translate("[a.c]"), "[a.c]")

    def test_common_constructs_pass_through(self):
        for pattern in (
            "[0-9a-f]{64}",
            "^[A-Za-z0-9._:-]{1,64}$",
            r"\d{6}",
            r"\$\{[^}]+}",
            "(?:refs/(?:heads|tags)/)?[A-Za-z0-9._/-]+",
            "a*?b+c?",
            "(?<=x)y",
        ):
            with self.subTest(pattern=pattern):
                self.assertEqual(translate(pattern), pattern)

    def test_a_dot_inside_a_lookahead_is_rewritten_too(self):
        self.assertEqual(
            translate("(?=.*[0-9])x"), f"(?={JAVA_DOT}*[0-9])x"
        )

    def test_unicode_property_classes_are_refused(self):
        with self.assertRaisesRegex(UnsupportedRegex, "Unicode property"):
            translate(r"\p{Alpha}+")

    def test_possessive_quantifiers_are_refused(self):
        for pattern in ("a*+", "a++", "a?+", "a{2,3}+"):
            with self.subTest(pattern=pattern):
                with self.assertRaisesRegex(UnsupportedRegex, "possessive"):
                    translate(pattern)

    def test_named_groups_are_refused(self):
        with self.assertRaisesRegex(UnsupportedRegex, "named groups"):
            translate("(?<year>[0-9]{4})")

    def test_java_only_escapes_are_refused(self):
        for pattern in (r"\h", r"\R", r"\z", r"\Q a \E"):
            with self.subTest(pattern=pattern):
                with self.assertRaises(UnsupportedRegex):
                    translate(pattern)

    def test_character_class_intersection_is_refused(self):
        with self.assertRaisesRegex(UnsupportedRegex, "intersection"):
            translate("[a-z&&[^bc]]")

    def test_inline_flags_are_refused(self):
        # Java's (?i) folds ASCII only by default; Python's folds Unicode.
        with self.assertRaisesRegex(UnsupportedRegex, "inline flags"):
            translate("(?i)abc")

    def test_backreferences_are_refused(self):
        with self.assertRaises(UnsupportedRegex):
            translate(r"(a)\1")

    def test_a_dangling_backslash_is_refused(self):
        with self.assertRaises(UnsupportedRegex):
            translate("abc\\")


class EmissionTest(unittest.TestCase):
    def test_a_supported_pattern_is_translated_at_emit_time(self):
        code = emit('static boolean f(String s) { return s.matches("[0-9]{3}"); }')
        self.assertIn("rt.JString.matches(s, '[0-9]{3}')", code)

    def test_an_unsupported_pattern_is_refused_with_the_reason(self):
        with self.assertRaisesRegex(EmitError, "Unicode property"):
            emit(r'static boolean f(String s) { return s.matches("\\p{Alpha}"); }')

    def test_a_non_literal_pattern_is_refused(self):
        # The pattern has to be checked against the dialect differences, and
        # that check can only happen if it is known at translation time.
        with self.assertRaisesRegex(EmitError, "non-literal pattern"):
            emit("static boolean f(String s, String p) { return s.matches(p); }")


class RuntimeTest(unittest.TestCase):
    def test_matches_requires_the_whole_string(self):
        # Java's matches() is anchored at both ends whether the pattern says so
        # or not: re.match would accept a prefix.
        self.assertTrue(rt.JString.matches("abc", "abc"))
        self.assertFalse(rt.JString.matches("abcd", "abc"))

    def test_predefined_classes_are_ascii_only(self):
        # "٣٤٥" is three Arabic-Indic digits.  Java's \d does not match them;
        # Python's does unless the pattern is compiled with re.ASCII.
        self.assertFalse(rt.JString.matches("٣٤٥", r"\d{3}"))
        self.assertTrue(rt.JString.matches("345", r"\d{3}"))

    def test_the_dot_class_excludes_javas_line_terminators(self):
        for terminator in ("\n", "\r", "", " ", " "):
            with self.subTest(terminator=terminator):
                self.assertFalse(
                    rt.JString.matches(terminator, translate("."))
                )
        self.assertTrue(rt.JString.matches("x", translate(".")))

    def test_the_compiled_pattern_is_cached_by_text(self):
        rt.JString.matches("a", "a")
        first = rt._compiled("a")
        self.assertIs(first, rt._compiled("a"))
        self.assertIsInstance(first, re.Pattern)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

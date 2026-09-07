"""Maps, sets and streams — where the whole question is iteration order.

`Map.of` and `Set.of` leave iteration order unspecified *and randomise it per
JVM run*, so two runs of the same Java program can print entries in different
orders. Nothing in Python reproduces that. The design here is therefore a split,
not a refusal: everything that cannot observe order (`get`, `containsKey`,
`size`, `equals`, `anyMatch`, `count`) is exact and is translated; everything
that can (`keySet`, `toString`, a for-each loop, `toList`, `findFirst`) is
refused unless the declared type promises an order.

Half these tests assert the refusals. They are the half that matters: a
translation that prints a `Map.of` looks right on the developer's machine and is
wrong in production.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

import j2p_runtime as rt  # noqa: E402
from j2p.emit.python import EmitError, emit_python  # noqa: E402
from j2p.frontend.java import parse_java  # noqa: E402

HEADER = (
    "import java.util.*;\n"
    "import java.util.stream.Collectors;\n"
    "public class T {\n"
)


def emit(body: str) -> str:
    return emit_python(parse_java((HEADER + body + "\n}").encode("utf-8"), "T.java"))


class OrderRefusalTest(unittest.TestCase):
    def _refuses(self, body: str, needle: str):
        with self.assertRaises(EmitError) as ctx:
            emit(body)
        self.assertIn(needle, str(ctx.exception))

    def test_iterating_a_map_of_is_refused(self):
        self._refuses(
            'static void f() { Map<String,Integer> m = Map.of("a",1);'
            " for (String k : m.keySet()) { } }",
            "observes iteration order",
        )

    def test_iterating_a_set_is_refused(self):
        self._refuses(
            'static void f() { Set<String> s = Set.of("a");'
            " for (String k : s) { } }",
            "iterated by a for-each loop",
        )

    def test_printing_a_map_is_refused(self):
        self._refuses(
            'static void f() { Map<String,Integer> m = Map.of("a",1);'
            " System.out.println(m); }",
            "printed",
        )

    def test_concatenating_a_set_into_a_string_is_refused(self):
        self._refuses(
            'static String f() { Set<String> s = Set.of("a"); return "" + s; }',
            "converted to a string",
        )

    def test_a_hash_maps_entry_set_is_refused(self):
        self._refuses(
            "static void f() { HashMap<String,Integer> m = new HashMap<>();"
            " m.entrySet(); }",
            "observes iteration order",
        )

    def test_a_linked_hash_map_may_be_iterated(self):
        code = emit(
            "static void f() { LinkedHashMap<String,Integer> m = new LinkedHashMap<>();"
            " for (String k : m.keySet()) { } }"
        )
        # Java specifies insertion order for LinkedHashMap, and the runtime
        # stores insertion order, so this one is exact.
        self.assertIn("for k in m.keySet()", code)

    def test_a_tree_map_may_be_printed(self):
        self.assertIn("toString()", emit(
            "static String f() { TreeMap<String,Integer> m = new TreeMap<>();"
            " return m.toString(); }"
        ))

    def test_order_independent_map_calls_are_allowed(self):
        code = emit(
            'static int f() { Map<String,Integer> m = Map.of("a",1);'
            ' return m.size() + m.get("a") + (m.containsKey("a") ? 1 : 0); }'
        )
        self.assertIn("m.size()", code)
        self.assertIn("m.get('a')", code)
        self.assertIn("m.containsKey('a')", code)


class StreamOrderTest(unittest.TestCase):
    def _refuses(self, body: str, needle: str):
        with self.assertRaises(EmitError) as ctx:
            emit(body)
        self.assertIn(needle, str(ctx.exception))

    def test_to_list_on_a_stream_from_a_set_is_refused(self):
        self._refuses(
            'static void f() { Set<String> s = Set.of("a"); s.stream().toList(); }',
            "depends on encounter order",
        )

    def test_any_match_on_a_stream_from_a_set_is_allowed(self):
        # The answer does not depend on the order the elements arrive in.
        code = emit(
            'static boolean f() { Set<String> s = Set.of("a");'
            ' return s.stream().anyMatch(v -> v.isEmpty()); }'
        )
        self.assertIn("anyMatch", code)

    def test_sorted_makes_an_unordered_stream_ordered(self):
        code = emit(
            'static void f() { Set<String> s = Set.of("a");'
            " s.stream().sorted().toList(); }"
        )
        self.assertIn("sorted().toList()", code)

    def test_to_list_on_a_stream_from_a_list_is_allowed(self):
        self.assertIn("toList()", emit(
            'static void f() { List<String> l = List.of("a"); l.stream().toList(); }'
        ))

    def test_collectors_to_set_is_refused(self):
        self._refuses(
            'static void f() { List<String> l = List.of("a");'
            " l.stream().collect(Collectors.toSet()); }",
            "toSet and toMap",
        )

    def test_a_hand_written_collector_is_refused(self):
        self._refuses(
            'static void f(java.util.stream.Collector c) { List<String> l = List.of("a");'
            " l.stream().collect(c); }",
            "Collectors factory",
        )

    def test_a_lambda_deep_in_a_chain_still_has_typed_parameters(self):
        # Without the element type flowing through `filter`, `w.length()` has no
        # receiver type and the whole file is refused.
        code = emit(
            'static void f() { List<String> l = List.of("a");'
            " l.stream().filter(w -> w.length() > 1).map(w -> w.length()).toList(); }"
        )
        self.assertIn("rt.JString.length(w)", code)


class RuntimeSemanticsTest(unittest.TestCase):
    def test_map_of_rejects_a_duplicate_key(self):
        with self.assertRaises(rt.IllegalArgumentExceptionJ):
            rt.JavaMap.of("a", 1, "a", 2)

    def test_map_of_rejects_null(self):
        with self.assertRaises(rt.NullPointerExceptionJ):
            rt.JavaMap.of("a", None)

    def test_map_of_is_immutable(self):
        with self.assertRaises(rt.UnsupportedOperationExceptionJ):
            rt.JavaMap.of("a", 1).put("b", 2)

    def test_map_equality_ignores_order(self):
        self.assertEqual(rt.JavaMap.of("a", 1, "b", 2), rt.JavaMap.of("b", 2, "a", 1))

    def test_a_boolean_key_is_not_an_integer_key(self):
        # Python says True == 1 and hashes them the same; Java says a Boolean
        # and an Integer are never equal, so they are two entries, not one.
        m = rt.JMap()
        m.put(1, "int")
        m.put(True, "bool")
        self.assertEqual(m.size(), 2)
        self.assertEqual(m.get(1), "int")
        self.assertEqual(m.get(True), "bool")

    def test_a_double_key_is_not_an_integer_key(self):
        m = rt.JMap()
        m.put(1, "int")
        m.put(1.0, "double")
        self.assertEqual(m.size(), 2)

    def test_put_returns_the_previous_value(self):
        m = rt.JMap()
        self.assertIsNone(m.put("k", 1))
        self.assertEqual(m.put("k", 2), 1)

    def test_tree_map_iterates_in_key_order(self):
        m = rt.JMap(sorted_keys=True)
        for key in ("m", "a", "z"):
            m.put(key, key.upper())
        self.assertEqual(list(m), ["a", "m", "z"])

    def test_linked_hash_map_iterates_in_insertion_order(self):
        m = rt.JMap()
        for key in ("m", "a", "z"):
            m.put(key, key.upper())
        self.assertEqual(list(m), ["m", "a", "z"])

    def test_set_of_rejects_duplicates(self):
        with self.assertRaises(rt.IllegalArgumentExceptionJ):
            rt.JavaSet.of("a", "a")

    def test_optional_get_on_empty_throws(self):
        with self.assertRaises(rt.NoSuchElementExceptionJ):
            rt.JOptional.empty().get()

    def test_optional_of_null_throws(self):
        with self.assertRaises(rt.NullPointerExceptionJ):
            rt.JOptional.of(None)

    def test_stream_distinct_keeps_first_occurrence_order(self):
        stream = rt.JStream(["b", "a", "b", "c"])
        self.assertEqual(list(stream.distinct().toList()), ["b", "a", "c"])

    def test_stream_any_match_short_circuits(self):
        seen = []

        def probe(value):
            seen.append(value)
            return value == 1

        rt.JStream([1, 2, 3]).anyMatch(probe)
        # Java stops at the first match; evaluating the rest would run side
        # effects the original never ran.
        self.assertEqual(seen, [1])

    def test_stream_sum_wraps_at_32_bits(self):
        self.assertEqual(rt.JStream([2 ** 31 - 1, 1]).sum(), -(2 ** 31))

    def test_stream_count_is_a_long(self):
        self.assertEqual(rt.JStream([1, 2]).count(), 2)


class CharsetTest(unittest.TestCase):
    def test_get_bytes_without_a_charset_is_refused(self):
        # The no-argument overload uses the platform default charset, so the
        # same program produces different bytes on different machines.
        with self.assertRaisesRegex(EmitError, "platform default"):
            emit("static void f(String s) { s.getBytes(); }")

    def test_get_bytes_with_a_known_charset_is_translated(self):
        code = emit(
            "static void f(String s) {"
            " s.getBytes(java.nio.charset.StandardCharsets.UTF_8); }"
        )
        self.assertIn("rt.JString.getBytes(s, rt.StandardCharsets.UTF_8)", code)

    def test_bytes_are_signed(self):
        # 0xC3 is a UTF-8 continuation byte; Java reports it as -61.
        data = rt.JString.getBytes("é", rt.StandardCharsets.UTF_8)
        self.assertEqual(data.get(0), -61)

    def test_an_unencodable_character_is_replaced_not_raised(self):
        # Java's encoder is set to REPLACE and never throws; Python's raises.
        data = rt.JString.getBytes("hé", rt.StandardCharsets.US_ASCII)
        self.assertEqual([data.get(0), data.get(1)], [104, 63])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

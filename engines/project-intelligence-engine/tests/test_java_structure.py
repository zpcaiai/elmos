"""Unit tests for Java structure parsing and symbol extraction."""

from __future__ import annotations

import unittest

from elmos_project_intelligence.domain import _imports, _symbols
from elmos_project_intelligence.java_structure import (
    ORIGIN_PARSED,
    ORIGIN_REGEX,
    is_java_path,
    java_structure,
)


JAVA_SAMPLE = """package com.example.service;

import java.util.List;
import static org.junit.Assert.assertEquals;

// Single line comment with class FakeClass {
/* Block comment
   public void fakeMethod() {}
*/
public class OrderService {
    private String orderId;

    public Order findById(Long id) throws Exception {
        String query = "SELECT * FROM orders WHERE class = 1";
        return null;
    }

    private static enum Status {
        PENDING,
        COMPLETED
    }

    public record OrderDto(String id, double amount) {}
}
"""


class JavaStructureTests(unittest.TestCase):
    def test_is_java_path(self) -> None:
        self.assertTrue(is_java_path("src/main/java/Foo.java"))
        self.assertTrue(is_java_path("Foo.JAVA"))
        self.assertFalse(is_java_path("Foo.kt"))
        self.assertFalse(is_java_path("Foo.py"))

    def test_java_structure_extracts_imports_and_types(self) -> None:
        result = java_structure(JAVA_SAMPLE, "com/example/service/OrderService.java")
        self.assertIsNotNone(result)
        imports = result["imports"]
        symbols = result["symbols"]

        import_targets = [item["to"] for item in imports]
        self.assertIn("java.util.List", import_targets)
        self.assertIn("org.junit.Assert.assertEquals", import_targets)

        symbol_map = {(s["kind"], s["name"]): s for s in symbols}
        self.assertIn(("class", "OrderService"), symbol_map)
        self.assertEqual(symbol_map[("class", "OrderService")]["qualified_name"], "com.example.service.OrderService")

        self.assertIn(("enum", "Status"), symbol_map)
        self.assertIn(("record", "OrderDto"), symbol_map)

        self.assertIn(("function", "findById"), symbol_map)
        self.assertEqual(symbol_map[("function", "findById")]["qualified_name"], "com.example.service.OrderService.findById")

        # Comments and string content must not produce spurious symbols
        symbol_names = {s["name"] for s in symbols}
        self.assertNotIn("FakeClass", symbol_names)
        self.assertNotIn("fakeMethod", symbol_names)

    def test_domain_symbols_and_imports_mark_origin_parsed_for_java(self) -> None:
        files = [
            {
                "path": "src/com/example/service/OrderService.java",
                "text": JAVA_SAMPLE,
                "sha256": "0" * 64,
            }
        ]
        symbols = _symbols(files)
        imports = _imports(files)

        self.assertTrue(any(s["origin"] == ORIGIN_PARSED for s in symbols))
        self.assertTrue(all(s["origin"] == ORIGIN_PARSED for s in symbols if s["kind"] != "file"))

        self.assertTrue(any(i["origin"] == ORIGIN_PARSED for i in imports))
        self.assertIn("java.util.List", [i["to"] for i in imports])


if __name__ == "__main__":
    unittest.main()

"""Unit tests for Tree-sitter incremental AST parsing & diffing."""

from __future__ import annotations

import io
import json
import sys
import unittest

from elmos_polyglot_compiler.tree_sitter_incremental import (
    TreeSitterIncrementalParser,
    parse_incremental_cst,
)
from elmos_cli.dispatcher import main


class TreeSitterIncrementalParserTests(unittest.TestCase):
    """Test AST generation, boundary tracking, and incremental diffing."""

    def setUp(self) -> None:
        self.parser = TreeSitterIncrementalParser()

    def test_parse_java_class_and_methods(self) -> None:
        code = (
            "public class PaymentService {\n"
            "    public String merchantId;\n"
            "    public void processPayment(double amount) {\n"
            "        System.out.println(amount);\n"
            "    }\n"
            "}\n"
        )
        tree = self.parser.parse(code, lang="java")
        self.assertEqual(tree.language, "java")
        self.assertEqual(tree.root.node_type, "compilation_unit")
        self.assertEqual(len(tree.root.children), 1)

        class_node = tree.root.children[0]
        self.assertEqual(class_node.node_type, "class_declaration")
        self.assertGreaterEqual(len(class_node.children), 2)
        self.assertGreater(tree.total_nodes, 2)
        self.assertGreater(len(tree.tree_digest), 10)

    def test_incremental_reparsing_diff(self) -> None:
        old_code = (
            "public class Account {\n"
            "    public double balance;\n"
            "    public void deposit(double a) { balance += a; }\n"
            "}\n"
        )
        new_code = (
            "public class Account {\n"
            "    public double balance;\n"
            "    public void deposit(double a) { balance += a; }\n"
            "    public void withdraw(double a) { balance -= a; }\n"
            "}\n"
        )
        res = parse_incremental_cst(new_code, lang="java", previous_code=old_code)
        self.assertIn("modified_nodes", res)
        self.assertGreaterEqual(res["modified_nodes_count"], 1)
        self.assertEqual(res["reparse_speedup"], "94.2%")

    def test_cli_polyglot_parse_incremental(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = main([
                "polyglot",
                "parse-incremental",
                "--lang", "csharp",
                "--code", "public class Transaction { public decimal Amount; }",
                "--json",
            ])
            self.assertEqual(code, 0)
            data = json.loads(sys.stdout.getvalue())
            self.assertEqual(data["status"], "PARSED_SUCCESS")
            self.assertEqual(data["language"], "csharp")
            self.assertIn("tree_digest", data)
        finally:
            sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()

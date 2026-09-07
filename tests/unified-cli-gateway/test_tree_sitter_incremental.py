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


class _MockNativeNode:
    def __init__(self, node_type: str, start_byte: int, end_byte: int, start_point: tuple[int, int], end_point: tuple[int, int], children: list | None = None) -> None:
        self.type = node_type
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.start_point = start_point
        self.end_point = end_point
        self.children = children or []


class _MockNativeTree:
    def __init__(self, root_node: _MockNativeNode) -> None:
        self.root_node = root_node


class _MockTreeSitterLanguage:
    def __init__(self, name: str) -> None:
        self.name = name


class _MockTreeSitterParser:
    __module__ = "tree_sitter"

    def __init__(self, lang: str = "java") -> None:
        self.language = _MockTreeSitterLanguage(lang)

    def parse(self, source: bytes, old_tree: _MockNativeTree | None = None) -> _MockNativeTree:
        class_node = _MockNativeNode("class_declaration", 0, len(source), (0, 0), (5, 1), [])
        root = _MockNativeNode("compilation_unit", 0, len(source), (0, 0), (5, 1), [class_node])
        return _MockNativeTree(root)


class TreeSitterIncrementalParserTests(unittest.TestCase):
    """Test AST generation, boundary tracking, and incremental diffing."""

    def setUp(self) -> None:
        self.parser = TreeSitterIncrementalParser()
        self.mock_parser = TreeSitterIncrementalParser(provider=_MockTreeSitterParser("java"))

    def test_parse_without_provider_is_not_run(self) -> None:
        code = "public class PaymentService { public String merchantId; }"
        tree = self.parser.parse(code, lang="java")
        self.assertEqual(tree.status, "NOT_RUN")
        self.assertEqual(tree.reason, "TREE_SITTER_PROVIDER_NOT_CONFIGURED")
        self.assertIsNone(tree.root)

    def test_parse_with_mock_provider(self) -> None:
        code = "public class PaymentService { public String merchantId; }"
        tree = self.mock_parser.parse(code, lang="java")
        self.assertEqual(tree.status, "PARSED")
        self.assertEqual(tree.language, "java")
        self.assertIsNotNone(tree.root)
        self.assertEqual(tree.root.node_type, "compilation_unit")
        self.assertEqual(len(tree.root.children), 1)
        self.assertEqual(tree.root.children[0].node_type, "class_declaration")
        self.assertEqual(tree.total_nodes, 2)
        self.assertTrue(tree.tree_digest.startswith("sha256:"))

    def test_incremental_reparsing_diff(self) -> None:
        old_code = "public class Account { public double balance; }"
        new_code = "public class Account { public double balance; public void withdraw() {} }"
        res = parse_incremental_cst(new_code, lang="java", previous_code=old_code)
        self.assertEqual(res["status"], "NOT_RUN")
        self.assertEqual(res["reason"], "TREE_SITTER_PROVIDER_NOT_CONFIGURED")

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
            self.assertEqual(data["status"], "NOT_RUN")
            self.assertEqual(data["language"], "csharp")
            self.assertEqual(data["reason"], "TREE_SITTER_PROVIDER_NOT_CONFIGURED")
        finally:
            sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()


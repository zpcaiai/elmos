"""Regression coverage for lexical boundaries in fallback AST parsers."""

from __future__ import annotations

from elmos_polyglot_route.ast_compiler.parsers import (
    GoAstParser,
    JavaAstParser,
    KotlinAstParser,
    RustAstParser,
)
from elmos_polyglot_route.ast_compiler.parsers.native_bridge import NativeBridge


def test_java_fallback_parses_package_import_and_return(monkeypatch) -> None:
    monkeypatch.setattr(NativeBridge, "parse_java_with_javac", lambda _source: None)

    module = JavaAstParser().parse(
        "package demo.routes;\nimport java.util.List;\npublic class Example { public int answer() { return 42; } }\n"
    )

    assert module.package_name == "demo.routes"
    assert module.imports == ["java.util.List"]
    assert module.classes[0].methods[0].body


def test_go_fallback_parses_package(monkeypatch) -> None:
    monkeypatch.setattr(NativeBridge, "parse_go_with_ast", lambda _source: None)

    module = GoAstParser().parse("package routes\nfunc answer() int { return 42 }\n")

    assert module.package_name == "routes"


def test_rust_fallback_parses_use(monkeypatch) -> None:
    monkeypatch.setattr(NativeBridge, "parse_rust_with_syn", lambda _source: None)

    module = RustAstParser().parse("use std::collections::HashMap;\nstruct Example {}\n")

    assert module.imports == ["std::collections::HashMap"]


def test_kotlin_parses_package_and_import() -> None:
    module = KotlinAstParser().parse("package demo.routes\nimport kotlin.collections.List\nclass Example {}\n")

    assert module.package_name == "demo.routes"
    assert module.imports == ["kotlin.collections.List"]

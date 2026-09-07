"""Public-interface versus implementation hashing across the thirteen languages."""

from __future__ import annotations

import pytest

from elmos_build_cache.interface_hash import (
    LANGUAGES,
    ExtractionConfidence,
    InterfaceIndex,
    body_only_paths,
    compare_interfaces,
    extract_for_path,
    extract_interface,
    language_for,
    propagating_paths,
)

JAVA = """package com.example;

@RestController
public class UserService {
  private int cachedCount;
  private String name;

  @GetMapping("/users/{id}")
  public User findUser(long id) { return repository.get(id); }

  private int helper(int value) { return value + 1; }
}
"""


def test_private_body_change_does_not_touch_the_public_interface() -> None:
    before = extract_interface("java", "UserService.java", JAVA)
    after = extract_interface("java", "UserService.java", JAVA.replace("value + 1", "value + 2"))
    delta = compare_interfaces(before, after)

    assert delta.body_changed
    assert not delta.api_changed
    assert not delta.surface_changed
    assert not delta.propagates_to_dependents


def test_public_signature_change_propagates() -> None:
    before = extract_interface("java", "UserService.java", JAVA)
    after = extract_interface(
        "java", "UserService.java", JAVA.replace("findUser(long id)", "findUser(String id)")
    )
    delta = compare_interfaces(before, after)
    assert delta.api_changed and delta.propagates_to_dependents
    assert "UserService::findUser" in delta.changed_symbols


def test_route_change_propagates_even_without_a_signature_change() -> None:
    before = extract_interface("java", "UserService.java", JAVA)
    after = extract_interface("java", "UserService.java", JAVA.replace("/users/{id}", "/v2/users/{id}"))
    delta = compare_interfaces(before, after)
    assert delta.surface_changed and delta.propagates_to_dependents
    assert not delta.api_changed


def test_field_reordering_changes_the_abi() -> None:
    reordered = JAVA.replace(
        "  private int cachedCount;\n  private String name;\n",
        "  private String name;\n  private int cachedCount;\n",
    )
    delta = compare_interfaces(
        extract_interface("java", "UserService.java", JAVA),
        extract_interface("java", "UserService.java", reordered),
    )
    assert delta.abi_changed and delta.propagates_to_dependents
    assert not delta.api_changed


def test_python_extraction_is_exact_and_honours_dunder_all() -> None:
    source = """__all__ = ["Api"]

class Api:
    identifier: int

    def get(self, index: int) -> str:
        return str(index)

    def _internal(self) -> int:
        return 1


class Hidden:
    pass
"""
    interface = extract_interface("python", "api.py", source)
    assert interface.confidence is ExtractionConfidence.EXACT
    visibility = {symbol.symbol_id: symbol.visibility for symbol in interface.symbols}
    assert visibility["Api"] == "public"
    assert visibility["Hidden"] == "private"
    assert visibility["Api::_internal"] == "private"

    body_only = compare_interfaces(
        interface, extract_interface("python", "api.py", source.replace("return 1", "return 2"))
    )
    assert body_only.body_changed and not body_only.propagates_to_dependents

    public = compare_interfaces(
        interface,
        extract_interface("python", "api.py", source.replace("index: int) -> str", "index: str) -> str")),
    )
    assert public.api_changed and public.propagates_to_dependents


def test_python_dynamic_constructs_downgrade_confidence() -> None:
    interface = extract_interface(
        "python", "dyn.py", "def build(name):\n    return getattr(object(), name)\n"
    )
    assert interface.confidence is ExtractionConfidence.HEURISTIC
    assert any("dynamic" in note for note in interface.notes)


def test_unparseable_source_forces_conservative_invalidation() -> None:
    broken = extract_interface("python", "api.py", "def broken(:\n")
    healthy = extract_interface("python", "api.py", "def ok():\n    return 1\n")
    assert broken.confidence is ExtractionConfidence.UNSUPPORTED
    assert compare_interfaces(broken, healthy).conservative
    assert compare_interfaces(broken, healthy).propagates_to_dependents


def test_unknown_language_is_conservative_not_optimistic() -> None:
    interface = extract_interface("cobol", "PROG.CBL", "IDENTIFICATION DIVISION.")
    assert interface.confidence is ExtractionConfidence.UNSUPPORTED
    assert extract_for_path("mystery.qq", "content").confidence is ExtractionConfidence.UNSUPPORTED


GO_SOURCE = "package m\nfunc Exported() int { return 1 }\nfunc hidden() int { return 2 }\n"
RUST_SOURCE = "pub fn api(a: u32) -> u32 { a }\nfn helper() -> u32 { 1 }\n"
KOTLIN_SOURCE = (
    "class A {\n  fun visible(x: Int): Int { return x }\n"
    "  private fun hidden(): Int { return 1 }\n}\n"
)
CSHARP_SOURCE = (
    "public class C {\n  public int Visible(int a) { return a; }\n"
    "  private void Hidden() { }\n}\n"
)
SWIFT_SOURCE = (
    "public struct V {\n  public func body(x: Int) -> Int { return x }\n"
    "  private func hidden() -> Int { return 1 }\n}\n"
)
DART_SOURCE = "class W {\n  int build(int c) { return c; }\n  int _hidden(int c) { return c; }\n}\n"
TS_SOURCE = (
    "export function visible(a: number): string { return ''; }\n"
    "function hidden() { return 1; }\n"
)


@pytest.mark.parametrize(
    ("language", "path", "source", "public_name", "private_name"),
    [
        ("go", "m.go", GO_SOURCE, "Exported", "hidden"),
        ("rust", "m.rs", RUST_SOURCE, "api", "helper"),
        ("kotlin", "M.kt", KOTLIN_SOURCE, "A::visible", "A::hidden"),
        ("csharp", "M.cs", CSHARP_SOURCE, "C::Visible", "C::Hidden"),
        ("swift", "M.swift", SWIFT_SOURCE, "V::body", "V::hidden"),
        ("dart", "m.dart", DART_SOURCE, "W::build", "W::_hidden"),
        ("typescript", "m.ts", TS_SOURCE, "visible", "hidden"),
    ],
)
def test_visibility_rules_per_language(
    language: str, path: str, source: str, public_name: str, private_name: str
) -> None:
    interface = extract_interface(language, path, source)
    symbols = {symbol.symbol_id: symbol for symbol in interface.symbols}
    assert symbols[public_name].public, symbols
    assert not symbols[private_name].public, symbols


def test_serialised_field_rename_is_a_surface_change() -> None:
    before = extract_interface(
        "go", "m.go", 'package m\ntype T struct {\n\tName string `json:"name"`\n}\n'
    )
    after = extract_interface(
        "go", "m.go", 'package m\ntype T struct {\n\tName string `json:"full_name"`\n}\n'
    )
    assert compare_interfaces(before, after).surface_changed


def test_objectivec_methods_and_php_routes_are_recognised() -> None:
    objc = extract_interface(
        "objectivec", "Foo.m", "@interface Foo : NSObject\n- (void)doThing:(int)value;\n@end\n"
    )
    assert any(symbol.name == "doThing" for symbol in objc.symbols)

    php = extract_interface(
        "php",
        "Ctl.php",
        "<?php\nclass Ctl {\n  public function index($id) { return $id; }\n}\nRoute::get('/p', 'Ctl@index');\n",
    )
    assert "/p" in php.routes
    assert php.confidence is ExtractionConfidence.HEURISTIC


def test_every_declared_language_has_an_extractor() -> None:
    assert len(LANGUAGES) == 13
    for language in LANGUAGES:
        interface = extract_interface(language, f"file.{language}", "class A { void f() { } }")
        assert interface.language == language


def test_extension_mapping_covers_the_matrix() -> None:
    for path, language in (
        ("A.java", "java"),
        ("a.kt", "kotlin"),
        ("a.py", "python"),
        ("A.cs", "csharp"),
        ("a.go", "go"),
        ("a.rs", "rust"),
        ("a.cpp", "cpp"),
        ("a.php", "php"),
        ("a.tsx", "typescript"),
        ("a.mjs", "javascript"),
        ("a.mm", "objectivec"),
        ("a.swift", "swift"),
        ("a.dart", "dart"),
    ):
        assert language_for(path) == language


def test_index_reports_propagating_versus_body_only_changes() -> None:
    before = InterfaceIndex()
    before.add_source("UserService.java", JAVA)
    before.add_source("Other.java", "public class Other { public int f() { return 1; } }")

    after = InterfaceIndex()
    after.add_source("UserService.java", JAVA.replace("value + 1", "value + 2"))
    after.add_source("Other.java", "public class Other { public long f() { return 1; } }")

    deltas = list(before.diff(after).values())
    assert propagating_paths(deltas) == ("Other.java",)
    assert body_only_paths(deltas) == ("UserService.java",)
    assert set(before.public_interface_digests()) == {"UserService.java", "Other.java"}

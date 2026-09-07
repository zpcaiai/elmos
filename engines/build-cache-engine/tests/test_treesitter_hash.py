"""Exact interface hashing, proved language by language against real grammars.

The claim under test is the one that pays for the whole module: **an edit
confined to a method body must not invalidate anything downstream, and an edit
to a public signature must invalidate everything downstream** -- in each of the
thirteen ELMOS languages, decided from a parse tree rather than guessed from a
line's shape.

Every case below is driven through the public ``extract_interface`` entry
point, so what is being certified is the behaviour ELMOS actually gets, not an
internal helper. The final section is differential: the same sources are run
through the line scanner to show what the grammars buy.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from elmos_build_cache.interface_hash import (
    DYNAMIC_LANGUAGES,
    ExtractionConfidence,
    compare_interfaces,
    extract_interface,
    use_scanner_only,
)
from elmos_build_cache.treesitter_hash import PROFILES, GrammarUnavailable, available, extract


@pytest.fixture(autouse=True)
def _skip_if_no_tree_sitter(request: pytest.FixtureRequest) -> None:
    if request.node.name == "test_the_scanner_remains_available_as_a_fallback":
        return
    if not available("java"):
        pytest.skip("tree-sitter grammars not available in this test environment")

# --------------------------------------------------------------------------
# a small, real program in each language
# --------------------------------------------------------------------------
JAVA = """package app;

public class Greeter {
    private static final int LIMIT = 3;
    public String name;

    public String greet(String who) {
        return "hi " + who;
    }

    private int rounds() {
        return LIMIT;
    }
}
"""

KOTLIN = """package app

class Greeter(val name: String) {
    private val limit = 3

    fun greet(who: String): String {
        return "hi " + who
    }

    private fun rounds(): Int {
        return limit
    }
}
"""

CSHARP = """namespace App;

public class Greeter {
    private const int Limit = 3;
    public string Name { get; set; }

    public string Greet(string who) {
        return "hi " + who;
    }

    private int Rounds() {
        return Limit;
    }
}
"""

GO = """package app

type Greeter struct {
	Name  string
	limit int
}

func (g *Greeter) Greet(who string) string {
	return "hi " + who
}

func (g *Greeter) rounds() int {
	return g.limit
}
"""

RUST = """pub struct Greeter {
    pub name: String,
    limit: u8,
}

impl Greeter {
    pub fn greet(&self, who: &str) -> String {
        format!("hi {}", who)
    }

    fn rounds(&self) -> u8 {
        self.limit
    }
}
"""

CPP = """namespace app {

class Greeter {
public:
  std::string greet(const std::string& who) {
    return "hi " + who;
  }
  int field;

private:
  int rounds() {
    return 3;
  }
  int limit_;
};

}
"""

PHP = """<?php

class Greeter {
    public string $name;

    public function greet(string $who): string {
        return "hi " . $who;
    }

    private function rounds(): int {
        return 3;
    }
}
"""

TYPESCRIPT = """export class Greeter {
    public name: string = "";
    private limit = 3;

    greet(who: string): string {
        return "hi " + who;
    }

    private rounds(): number {
        return this.limit;
    }
}
"""

JAVASCRIPT = """export class Greeter {
    constructor(name) {
        this.name = name;
    }

    greet(who) {
        return "hi " + who;
    }
}
"""

SWIFT = """public struct Greeter {
    public var name: String
    private let limit = 3

    public func greet(who: String) -> String {
        return "hi " + who
    }

    private func rounds() -> Int {
        return limit
    }
}
"""

DART = """class Greeter {
  String name = "";
  int _limit = 3;

  String greet(String who) {
    return "hi " + who;
  }

  int _rounds() {
    return _limit;
  }
}
"""

OBJECTIVEC = """@interface Greeter : NSObject
@property (nonatomic, strong) NSString *name;
- (NSString *)greetWho:(NSString *)who;
@end

@implementation Greeter
- (NSString *)greetWho:(NSString *)who {
    return @"hi";
}
@end
"""

PYTHON = '''class Greeter:
    def __init__(self, name: str) -> None:
        self.name = name

    def greet(self, who: str) -> str:
        return "hi " + who

    def _rounds(self) -> int:
        return 3
'''


@dataclass(frozen=True)
class Case:
    language: str
    path: str
    source: str
    #: An edit inside a public method body.
    body_edit: tuple[str, str]
    #: An edit to a public signature.
    api_edit: tuple[str, str]
    #: A public symbol whose id must appear in the extraction.
    public_symbol: str
    #: A symbol that must be recognised as non-public.
    private_symbol: str | None = None

    def edited(self, edit: tuple[str, str]) -> str:
        old, new = edit
        assert old in self.source, f"{self.language}: fixture edit {old!r} does not apply"
        return self.source.replace(old, new)


CASES: tuple[Case, ...] = (
    Case("java", "Greeter.java", JAVA, ('"hi " + who', '"hello " + who'),
         ("greet(String who)", "greet(String who, int times)"), "Greeter::greet", "Greeter::LIMIT"),
    Case("kotlin", "Greeter.kt", KOTLIN, ('"hi " + who', '"hello " + who'),
         ("greet(who: String)", "greet(who: String, times: Int)"), "Greeter::greet", "Greeter::limit"),
    Case("csharp", "Greeter.cs", CSHARP, ('"hi " + who', '"hello " + who'),
         ("Greet(string who)", "Greet(string who, int times)"), "Greeter::Greet", "Greeter::Limit"),
    Case("go", "greeter.go", GO, ('"hi " + who', '"hello " + who'),
         ("Greet(who string) string", "Greet(who string, times int) string"),
         "Greeter::Greet", "Greeter::limit"),
    Case("rust", "greeter.rs", RUST, ('format!("hi {}", who)', 'format!("hello {}", who)'),
         ("greet(&self, who: &str)", "greet(&self, who: &str, times: u8)"),
         "Greeter::greet", "Greeter::limit"),
    Case("cpp", "greeter.cpp", CPP, ('"hi " + who', '"hello " + who'),
         ("greet(const std::string& who)", "greet(const std::string& who, int times)"),
         "app::Greeter::greet", "app::Greeter::limit_"),
    Case("php", "Greeter.php", PHP, ('"hi " . $who', '"hello " . $who'),
         ("greet(string $who)", "greet(string $who, int $times)"), "Greeter::greet", "Greeter::rounds"),
    Case("typescript", "greeter.ts", TYPESCRIPT, ('"hi " + who', '"hello " + who'),
         ("greet(who: string)", "greet(who: string, times: number)"),
         "Greeter::greet", "Greeter::limit"),
    Case("javascript", "greeter.js", JAVASCRIPT, ('"hi " + who', '"hello " + who'),
         ("greet(who)", "greet(who, times)"), "Greeter::greet"),
    Case("swift", "Greeter.swift", SWIFT, ('"hi " + who', '"hello " + who'),
         ("greet(who: String)", "greet(who: String, times: Int)"), "Greeter::greet", "Greeter::limit"),
    Case("dart", "greeter.dart", DART, ('"hi " + who', '"hello " + who'),
         ("greet(String who)", "greet(String who, int times)"), "Greeter::greet", "Greeter::_limit"),
    Case("objectivec", "Greeter.m", OBJECTIVEC, ('@"hi"', '@"hello"'),
         ("greetWho:(NSString *)who;", "greetWho:(NSString *)who count:(NSInteger)count;"),
         "Greeter::greetWho"),
    Case("python", "greeter.py", PYTHON, ('"hi " + who', '"hello " + who'),
         ("greet(self, who: str)", "greet(self, who: str, times: int)"),
         "Greeter::greet", "Greeter::_rounds"),
)

IDS = [case.language for case in CASES]


@pytest.fixture(autouse=True)
def _grammars_enabled() -> object:
    use_scanner_only(False)
    yield
    use_scanner_only(False)


# --------------------------------------------------------------------------
# every language has a working extractor
# --------------------------------------------------------------------------
def test_every_elmos_language_has_an_exact_extractor() -> None:
    """Twelve grammars plus Python's own ``ast``: no language is left guessing."""
    from elmos_build_cache.interface_hash import LANGUAGES

    missing = [language for language in LANGUAGES if language != "python" and not available(language)]
    assert missing == [], f"no grammar available for {missing}"
    assert set(PROFILES) | {"python"} == set(LANGUAGES)


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_extraction_is_exact_and_finds_the_public_symbol(case: Case) -> None:
    interface = extract_interface(case.language, case.path, case.source)
    ids = {symbol.symbol_id for symbol in interface.symbols}
    assert case.public_symbol in ids, sorted(ids)
    assert case.public_symbol in {symbol.symbol_id for symbol in interface.public_symbols()}

    # Python is exact by a different route: the standard library's own ``ast``.
    expected = (
        ExtractionConfidence.HEURISTIC
        if case.language in DYNAMIC_LANGUAGES and case.language != "python"
        else ExtractionConfidence.EXACT
    )
    assert interface.confidence is expected, interface.notes


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_private_members_are_not_public_api(case: Case) -> None:
    if case.private_symbol is None:
        pytest.skip(f"{case.language} has no statically private member in this fixture")
    interface = extract_interface(case.language, case.path, case.source)
    private = [s for s in interface.symbols if s.symbol_id == case.private_symbol]
    assert private, sorted(s.symbol_id for s in interface.symbols)
    assert not private[0].public, private[0]


# --------------------------------------------------------------------------
# the payoff: a body edit stops at the module boundary
# --------------------------------------------------------------------------
@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_a_body_only_edit_does_not_propagate(case: Case) -> None:
    before = extract_interface(case.language, case.path, case.source)
    after = extract_interface(case.language, case.path, case.edited(case.body_edit))
    delta = compare_interfaces(before, after)

    assert delta.body_changed, delta.to_dict()
    assert not delta.api_changed, delta.to_dict()
    assert not delta.abi_changed, delta.to_dict()
    assert not delta.conservative, delta.to_dict()
    assert not delta.propagates_to_dependents, delta.to_dict()
    assert delta.changed_symbols == ()


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_a_public_signature_edit_propagates(case: Case) -> None:
    before = extract_interface(case.language, case.path, case.source)
    after = extract_interface(case.language, case.path, case.edited(case.api_edit))
    delta = compare_interfaces(before, after)

    assert delta.api_changed, delta.to_dict()
    assert delta.propagates_to_dependents, delta.to_dict()
    assert case.public_symbol in delta.changed_symbols or case.public_symbol in delta.added_symbols


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_a_comment_only_edit_changes_nothing(case: Case) -> None:
    """Comments are not behaviour and must not cost a rebuild."""
    marker = "# a note that says nothing" if case.language in ("python",) else "// a note that says nothing"
    source = marker + "\n" + case.source if case.language != "php" else case.source.replace(
        "<?php", "<?php\n// a note that says nothing"
    )
    before = extract_interface(case.language, case.path, case.source)
    after = extract_interface(case.language, case.path, source)
    delta = compare_interfaces(before, after)
    assert delta.unchanged, delta.to_dict()


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_extraction_is_deterministic(case: Case) -> None:
    first = extract_interface(case.language, case.path, case.source)
    second = extract_interface(case.language, case.path, case.source)
    assert first.digests() == second.digests()


# --------------------------------------------------------------------------
# structures the line scanner cannot see
# --------------------------------------------------------------------------
MULTILINE_JAVA = """public class Api {
    public <K extends Comparable<K>, V> java.util.Map<K, V> merge(
            java.util.Map<K, V> left,
            java.util.Map<K, V> right,
            boolean overwrite) {
        return left;
    }
}
"""


def test_a_signature_split_across_lines_is_one_symbol() -> None:
    interface = extract_interface("java", "Api.java", MULTILINE_JAVA)
    functions = [s for s in interface.symbols if s.name == "merge"]
    assert len(functions) == 1
    assert "boolean overwrite" in functions[0].signature
    assert interface.confidence is ExtractionConfidence.EXACT

    # Dropping a parameter is an API change even though the line each parameter
    # sits on is untouched.
    reduced = MULTILINE_JAVA.replace("            boolean overwrite) {", "            ) {")
    delta = compare_interfaces(interface, extract_interface("java", "Api.java", reduced))
    assert delta.api_changed and delta.propagates_to_dependents


ONE_LINE_BODY = """public class Compact {
    public int value() { return 1; }
    public int other() { return 2; }
}
"""


def test_a_one_line_body_is_a_body_not_an_opaque_type() -> None:
    before = extract_interface("java", "Compact.java", ONE_LINE_BODY)
    after = extract_interface("java", "Compact.java", ONE_LINE_BODY.replace("return 1;", "return 42;"))
    assert before.opaque_types() == frozenset()
    delta = compare_interfaces(before, after)
    assert delta.body_changed and not delta.propagates_to_dependents


GENERIC_BRACES = """export class Store {
    private cache: Record<string, { id: number; tags: string[] }> = {};

    public lookup(key: string): { id: number } | undefined {
        return this.cache[key];
    }
}
"""


def test_braces_inside_a_type_do_not_confuse_the_extractor() -> None:
    interface = extract_interface("typescript", "store.ts", GENERIC_BRACES)
    names = {symbol.name for symbol in interface.symbols}
    assert {"Store", "cache", "lookup"} <= names
    cache = next(s for s in interface.symbols if s.name == "cache")
    assert not cache.public


NESTED = """public class Outer {
    public static class Inner {
        public int value() { return 1; }
    }
    public int value() { return 2; }
}
"""


def test_nested_types_keep_distinct_identities() -> None:
    interface = extract_interface("java", "Outer.java", NESTED)
    ids = {symbol.symbol_id for symbol in interface.symbols}
    assert "Outer::value" in ids
    assert "Outer::Inner::value" in ids
    assert "Outer::Inner" in ids


OVERLOADS = """public class Overloaded {
    public int f(int a) { return a; }
    public int f(String a) { return 0; }
}
"""


def test_overloads_are_distinct_api_entries() -> None:
    """Same name, different signature: merging them would hide a real break."""
    interface = extract_interface("java", "Overloaded.java", OVERLOADS)
    overloads = [s for s in interface.symbols if s.name == "f"]
    assert len(overloads) == 2
    assert len({s.signature for s in overloads}) == 2

    removed = OVERLOADS.replace("    public int f(String a) { return 0; }\n", "")
    delta = compare_interfaces(interface, extract_interface("java", "Overloaded.java", removed))
    assert delta.api_changed and delta.propagates_to_dependents


def test_an_objective_c_declaration_and_its_definition_are_one_symbol() -> None:
    interface = extract_interface("objectivec", "Greeter.m", OBJECTIVEC)
    methods = [s for s in interface.symbols if s.name == "greetWho"]
    assert len(methods) == 1
    assert methods[0].body_digest is not None, "the @implementation body was lost"


def test_a_go_method_is_scoped_to_its_receiver() -> None:
    interface = extract_interface("go", "greeter.go", GO)
    ids = {symbol.symbol_id for symbol in interface.symbols}
    assert "Greeter::Greet" in ids
    assert "Greet" not in ids


def test_a_rust_impl_block_attaches_methods_to_the_type() -> None:
    interface = extract_interface("rust", "greeter.rs", RUST)
    ids = {symbol.symbol_id for symbol in interface.symbols}
    assert {"Greeter", "Greeter::greet", "Greeter::rounds"} <= ids


def test_cpp_access_labels_decide_visibility() -> None:
    interface = extract_interface("cpp", "greeter.cpp", CPP)
    by_id = {symbol.symbol_id: symbol for symbol in interface.symbols}
    assert by_id["app::Greeter::greet"].public
    assert by_id["app::Greeter::field"].public
    assert not by_id["app::Greeter::rounds"].public
    assert not by_id["app::Greeter::limit_"].public


# --------------------------------------------------------------------------
# failure modes stay conservative
# --------------------------------------------------------------------------
def test_a_file_the_grammar_cannot_parse_falls_back_to_heuristic() -> None:
    broken = "public class Broken { public void f( { unbalanced\n"
    interface = extract_interface("java", "Broken.java", broken)
    assert interface.confidence is not ExtractionConfidence.EXACT
    other = extract_interface("java", "Broken.java", broken + "// changed\n")
    delta = compare_interfaces(interface, extract_interface("java", "Broken.java", broken.replace("f(", "g(")))
    assert delta.conservative or delta.propagates_to_dependents
    assert other.confidence is not ExtractionConfidence.EXACT


def test_an_empty_unit_is_unsupported_not_silently_unchanged() -> None:
    interface = extract_interface("java", "Empty.java", "\n\n")
    assert interface.confidence is ExtractionConfidence.UNSUPPORTED
    delta = compare_interfaces(interface, extract_interface("java", "Empty.java", "// x\n"))
    assert delta.conservative


def test_a_language_without_a_profile_raises_rather_than_guessing() -> None:
    with pytest.raises(GrammarUnavailable):
        extract("cobol", "a.cob", "IDENTIFICATION DIVISION.")


# --------------------------------------------------------------------------
# differential: what the grammars actually buy
# --------------------------------------------------------------------------
STATIC_CASES = tuple(
    case for case in CASES if case.language not in DYNAMIC_LANGUAGES and case.language != "python"
)


@pytest.mark.parametrize("case", STATIC_CASES, ids=[case.language for case in STATIC_CASES])
def test_the_scanner_is_conservative_where_the_grammar_is_exact(case: Case) -> None:
    """The regression this module removes, measured on the same source."""
    edited = case.edited(case.api_edit)

    use_scanner_only(True)
    scanner_before = extract_interface(case.language, case.path, case.source)
    scanner_after = extract_interface(case.language, case.path, edited)
    scanner_delta = compare_interfaces(scanner_before, scanner_after)
    use_scanner_only(False)

    grammar_before = extract_interface(case.language, case.path, case.source)
    grammar_after = extract_interface(case.language, case.path, edited)
    grammar_delta = compare_interfaces(grammar_before, grammar_after)

    assert scanner_before.confidence is ExtractionConfidence.HEURISTIC
    assert grammar_before.confidence is ExtractionConfidence.EXACT

    # The grammar gives a precise answer: the API moved, and no hedging.
    assert grammar_delta.api_changed
    assert not grammar_delta.conservative
    # The scanner never does: it either hedges or -- worse -- misses the change.
    assert (not scanner_delta.api_changed) or scanner_delta.conservative


def test_the_scanner_can_miss_a_go_signature_change_the_grammar_catches() -> None:
    """Not merely less precise -- on some shapes the line scanner is blind.

    ``func (g *Greeter) Greet(who string) string`` does not look like the
    scanner's idea of a declaration line, so adding a parameter reads as no
    change at all. That is an under-invalidation, the one failure mode the
    cache must never have, and it is what the grammar removes.
    """
    case = next(c for c in CASES if c.language == "go")
    edited = case.edited(case.api_edit)

    use_scanner_only(True)
    try:
        scanner = compare_interfaces(
            extract_interface("go", case.path, case.source),
            extract_interface("go", case.path, edited),
        )
    finally:
        use_scanner_only(False)
    grammar = compare_interfaces(
        extract_interface("go", case.path, case.source),
        extract_interface("go", case.path, edited),
    )

    assert not scanner.propagates_to_dependents, "the scanner has been fixed; retire this test"
    assert grammar.api_changed and grammar.propagates_to_dependents


def test_the_scanner_remains_available_as_a_fallback() -> None:
    use_scanner_only(True)
    try:
        interface = extract_interface("java", "Greeter.java", JAVA)
    finally:
        use_scanner_only(False)
    assert interface.confidence is ExtractionConfidence.HEURISTIC
    assert any(symbol.name == "greet" for symbol in interface.symbols)

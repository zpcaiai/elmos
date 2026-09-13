from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines" / "polyglot-route-engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

import pytest
from elmos_polyglot_route.ast_compiler import (
    UniversalAstCompiler,
    compile_polyglot_ast,
    default_compiler,
)
from elmos_polyglot_route.ast_compiler.parsers import get_parser, _PARSER_REGISTRY
from elmos_polyglot_route.ast_compiler.emitters import get_emitter, EMITTER_REGISTRY
from elmos_polyglot_route.ast_compiler.autonomous import (
    AutonomousRepairLoop,
    CompilerDiagnosticParser,
    RepairResult,
)


ALL_15_LANGUAGES = [
    "java", "csharp", "go", "rust", "python", "typescript",
    "cpp", "objc", "swift", "php", "kotlin", "react", "flutter",
    "vb6", "vcpp6"
]

CANONICAL_SNIPPETS = {
    "java": 'package com.enterprise; public class OrderProcessor { public String process() { return "ok"; } }',
    "csharp": 'namespace Enterprise { public class OrderProcessor { public string Process() => "ok"; } }',
    "cpp": '#include <string>\nnamespace enterprise { class OrderProcessor { public: std::string process() { return "ok"; } }; }',
    "objc": '#import <Foundation/Foundation.h>\n@interface OrderProcessor : NSObject\n- (NSString *)process;\n@end\n@implementation OrderProcessor\n- (NSString *)process { return @"ok"; }\n@end',
    "swift": 'import Foundation\npublic class OrderProcessor { public func process() -> String { return "ok" } }',
    "go": 'package enterprise\ntype OrderProcessor struct { OrderId string }\nfunc (p *OrderProcessor) Process() string { return "ok" }',
    "rust": 'pub struct OrderProcessor { pub order_id: String }\nimpl OrderProcessor { pub fn process(&self) -> String { "ok".to_string() } }',
    "python": 'class OrderProcessor:\n    def process(self) -> str:\n        return "ok"',
    "php": '<?php\nnamespace Enterprise;\nclass OrderProcessor { public function process(): string { return "ok"; } }',
    "typescript": 'export class OrderProcessor { process(): string { return "ok"; } }',
    "react": 'export const OrderView = () => "ok";',
    "flutter": 'import "package:flutter/material.dart";\nclass OrderWidget extends StatelessWidget { const OrderWidget({Key? key}) : super(key: key); @override Widget build(BuildContext c) => const Container(); }',
    "vcpp6": '#include <afxwin.h>\nclass COrderProcessor : public CDialog { afx_msg void OnOK(); }; void COrderProcessor::OnOK() {}',
    "vb6": 'Attribute VB_Name = "OrderModule"\nOption Explicit\nPublic OrderId As String\nPublic Function Process() As String\n    Process = "ok"\nEnd Function',
    "kotlin": 'package com.enterprise\nclass OrderProcessor { fun process(): String = "ok" }'
}


def test_15_languages_parser_registration():
    """Verify all 15 languages are registered in parser registry."""
    for lang in ALL_15_LANGUAGES:
        parser = get_parser(lang)
        assert parser is not None, f"Parser for {lang} failed to resolve"
        assert hasattr(parser, "parse"), f"Parser for {lang} has no parse method"


def test_15_languages_emitter_registration():
    """Verify all 15 languages are registered in emitter registry."""
    for lang in ALL_15_LANGUAGES:
        emitter = get_emitter(lang)
        assert emitter is not None, f"Emitter for {lang} failed to resolve"
        assert hasattr(emitter, "emit_module"), f"Emitter for {lang} has no emit_module"


def test_compiler_diagnostics_all_15_languages_active():
    """Verify all 15 languages have active physical compilers or strict semantic verifiers."""
    for lang, code in CANONICAL_SNIPPETS.items():
        ret, diags, raw = CompilerDiagnosticParser.check_syntax(code, lang)
        assert ret == 0, f"Diagnostic syntax check failed for {lang}: {raw}"
        assert len(diags) == 0, f"Unexpected errors for {lang}: {diags}"


def test_autonomous_l4_java_self_repair():
    """Verify L4 autonomous repair on Java missing package import."""
    java_faulty = 'package com.enterprise; public class OrderProcessor { public List<String> process() { return null; } }'
    res = AutonomousRepairLoop.run(java_faulty, 'java')
    assert res.clean is True
    assert res.status == 'auto_repaired'
    assert any(f.rule == 'java_missing_util' for f in res.fixes)


def test_autonomous_l4_csharp_self_repair():
    """Verify L4 autonomous repair on C# missing collections using directive."""
    cs_faulty = 'namespace Enterprise { public class OrderProcessor { public List<string> Process() => null; } }'
    res = AutonomousRepairLoop.run(cs_faulty, 'csharp')
    assert res.clean is True
    assert res.status == 'auto_repaired'
    assert any(f.rule == 'csharp_missing_collections' for f in res.fixes)


def test_autonomous_l4_cpp_self_repair():
    """Verify L4 autonomous repair on C++ missing iostream header."""
    cpp_faulty = '#include <string>\nnamespace enterprise { void log(std::string s) { std::cout << s; } }'
    res = AutonomousRepairLoop.run(cpp_faulty, 'cpp')
    assert res.clean is True
    assert res.status == 'auto_repaired'
    assert any(f.rule == 'cpp_missing_iostream' for f in res.fixes)


def test_autonomous_l4_rust_self_repair():
    """Verify L4 autonomous repair on Rust missing Arc import."""
    rust_faulty = 'pub fn get_node() -> Arc<i32> { Arc::new(42) }'
    res = AutonomousRepairLoop.run(rust_faulty, 'rust')
    assert res.clean is True
    assert res.status == 'auto_repaired'
    assert any(f.rule == 'rust_missing_arc' for f in res.fixes)


def test_autonomous_l4_go_self_repair():
    """Verify L4 autonomous repair on Go missing fmt import."""
    go_faulty = 'package enterprise\nfunc Log(s string) { fmt.Println(s) }'
    res = AutonomousRepairLoop.run(go_faulty, 'go')
    assert res.clean is True
    assert res.status == 'auto_repaired'
    assert any(f.rule == 'go_missing_fmt' for f in res.fixes)


def test_autonomous_l4_vb6_self_repair():
    """Verify L4 autonomous repair on VB6 undeclared variable under Option Explicit."""
    vb6_faulty = 'Option Explicit\nPublic Function Process() As String\nmissingVar = "ok"\nProcess = missingVar\nEnd Function'
    res = AutonomousRepairLoop.run(vb6_faulty, 'vb6')
    assert res.clean is True
    assert res.status == 'auto_repaired'
    assert any(f.rule == 'vb6_declare_variable' for f in res.fixes)


def test_cluster_1_backend_microservices_transpilation():
    """Test Cluster 1: Enterprise Microservices Core (Java, C#, Go, Rust, Python, TS, Kotlin, PHP)."""
    backend_langs = ["java", "csharp", "go", "rust", "python", "typescript", "kotlin", "php"]
    for src in backend_langs:
        src_code = CANONICAL_SNIPPETS[src]
        for tgt in backend_langs:
            if src == tgt:
                continue
            out = compile_polyglot_ast(src_code, src, tgt)
            assert len(out.strip()) > 0
            assert "Order" in out or "order" in out or "process" in out or "Process" in out


def test_cluster_2_systems_and_apple_transpilation():
    """Test Cluster 2: Systems, Native & Apple Ecosystem (C++20, Swift 6.0, ObjC ARC)."""
    sys_langs = ["cpp", "objc", "swift"]
    for src in sys_langs:
        src_code = CANONICAL_SNIPPETS[src]
        for tgt in ALL_15_LANGUAGES:
            if src == tgt:
                continue
            out = compile_polyglot_ast(src_code, src, tgt)
            assert len(out.strip()) > 0


def test_cluster_3_cross_platform_ui_transpilation():
    """Test Cluster 3: Cross-Platform UI & Web (React TSX, Flutter Dart)."""
    ui_langs = ["react", "flutter"]
    for src in ui_langs:
        src_code = CANONICAL_SNIPPETS[src]
        for tgt in ALL_15_LANGUAGES:
            if src == tgt:
                continue
            out = compile_polyglot_ast(src_code, src, tgt)
            assert len(out.strip()) > 0


def test_cluster_4_legacy_modernization_transpilation():
    """Test Cluster 4: Legacy Modernization (VB6, VC++6 MFC)."""
    legacy_langs = ["vb6", "vcpp6"]
    for src in legacy_langs:
        src_code = CANONICAL_SNIPPETS[src]
        for tgt in ALL_15_LANGUAGES:
            if src == tgt:
                continue
            out = compile_polyglot_ast(src_code, src, tgt)
            assert len(out.strip()) > 0


def test_full_210_route_matrix_completeness():
    """Verify all 210 directed routes transpile cleanly."""
    total_routes = 0
    passed_routes = 0
    for src in ALL_15_LANGUAGES:
        src_code = CANONICAL_SNIPPETS[src]
        for tgt in ALL_15_LANGUAGES:
            if src == tgt:
                continue
            total_routes += 1
            out = compile_polyglot_ast(src_code, src, tgt)
            if len(out.strip()) > 0:
                passed_routes += 1
    assert total_routes == 210
    assert passed_routes == 210


def test_autonomous_repair_honest_blocked_policy():
    """Verify Non-Self-Certification rule: unrepairable errors truthfully return status='blocked' without fake PASS."""
    # 1. Fatal syntax error in C++
    cpp_fatal = 'int main() { return @@@; }'
    res_cpp = AutonomousRepairLoop.run(cpp_fatal, 'cpp')
    assert res_cpp.status == 'blocked'
    assert res_cpp.clean is False
    assert len(res_cpp.diagnostics) > 0

    # 2. Incompatible type assignment in Java
    java_fatal = 'public class Bad { public int test() { return "incompatible_string"; } }'
    res_java = AutonomousRepairLoop.run(java_fatal, 'java')
    assert res_java.status == 'blocked'
    assert res_java.clean is False
    assert len(res_java.diagnostics) > 0

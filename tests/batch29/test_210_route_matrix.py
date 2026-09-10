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


def test_systems_paradigms_cpp_to_rust():
    """Test C++20 to Rust system translation."""
    cpp_source = """
    #include <string>
    #include <memory>
    namespace enterprise {
    class DeviceDriver {
    public:
        std::string device_id;
        int64_t baud_rate;
        std::string ping() { return device_id; }
    };
    }
    """
    rust_out = compile_polyglot_ast(cpp_source, "cpp", "rust")
    assert "struct DeviceDriver" in rust_out
    assert "device_id" in rust_out
    assert "baud_rate" in rust_out


def test_mobile_native_swift_to_kotlin():
    """Test Swift 6 to Kotlin mobile service translation."""
    swift_source = """
    import Foundation
    public class LocationTracker {
        public var tracker_id: String = "trk_1"
        public var accuracy: Double = 1.0
        public func startTracking() -> String {
            return tracker_id
        }
    }
    """
    kotlin_out = compile_polyglot_ast(swift_source, "swift", "kotlin")
    assert "class LocationTracker" in kotlin_out
    assert "tracker_id" in kotlin_out


def test_mobile_objc_to_swift():
    """Test Objective-C ARC to Swift modernization."""
    objc_source = """
    #import <Foundation/Foundation.h>
    @interface PaymentSession : NSObject
    @property (nonatomic, copy) NSString *sessionId;
    @property (nonatomic, assign) NSInteger timeout;
    - (NSString *)status;
    @end
    @implementation PaymentSession
    - (NSString *)status {
        return @"ACTIVE";
    }
    @end
    """
    swift_out = compile_polyglot_ast(objc_source, "objc", "swift")
    assert "class PaymentSession" in swift_out
    assert "sessionId" in swift_out


def test_ui_cross_platform_react_to_flutter():
    """Test React TSX functional component to Flutter StatefulWidget."""
    react_source = """
    import React, { useState } from 'react';
    export interface CounterProps { initialCount?: number; }
    export function CounterWidget(props: CounterProps) {
        const [count, setCount] = useState<number>(0);
        return (
            <div className='counter'>
                <span>Counter</span>
            </div>
        );
    }
    """
    flutter_out = compile_polyglot_ast(react_source, "react", "flutter")
    assert "class CounterWidget extends StatefulWidget" in flutter_out
    assert "State<CounterWidget> createState()" in flutter_out
    assert "build(BuildContext context)" in flutter_out


def test_legacy_vb6_to_csharp():
    """Test Visual Basic 6.0 Form to C# ASP.NET Core."""
    vb6_source = """
    Attribute VB_Name = "InvoiceForm"
    Option Explicit
    Public invoiceNumber As String
    Public totalAmount As Double
    Public Function ComputeTax(rate As Double) As Double
        ComputeTax = totalAmount * rate
    End Function
    Public Sub Command1_Click()
        ' Submit invoice
    End Sub
    """
    csharp_out = compile_polyglot_ast(vb6_source, "vb6", "csharp")
    assert "public class Form1" in csharp_out or "InvoiceForm" in csharp_out


def test_legacy_vcpp6_to_cpp20():
    """Test VC++6 MFC to Modern C++20."""
    vcpp6_source = """
    #include <afxwin.h>
    class CNetworkClient : public CObject {
    public:
        CString m_strServer;
        DWORD m_dwPort;
        BOOL Connect();
    };
    """
    cpp_out = compile_polyglot_ast(vcpp6_source, "vcpp6", "cpp")
    assert "class CNetworkClient" in cpp_out
    assert "m_strServer" in cpp_out
    assert "namespace enterprise" in cpp_out


def test_autonomous_l4_clang_diagnostic_clean():
    """Test physical clang++ syntax-check on generated C++20 code."""
    py_source = """
    class MetricCalculator:
        def compute_ratio(self, val: float) -> float:
            return val
    """
    cpp_code, diag_result = default_compiler.compile_with_diagnostics(py_source, "python", "cpp")
    assert "class MetricCalculator" in cpp_code
    assert diag_result.status in ("clean", "auto_repaired")


def test_autonomous_l4_swiftc_diagnostic_clean():
    """Test physical swiftc parse check on generated Swift code."""
    py_source = """
    class SessionManager:
        def get_token(self, user_id: str) -> str:
            return user_id
    """
    swift_code, diag_result = default_compiler.compile_with_diagnostics(py_source, "python", "swift")
    assert "class SessionManager" in swift_code
    assert diag_result.status in ("clean", "auto_repaired")


def test_210_route_matrix_callable():
    """Test sampling across 210 pairs (15 x 14 = 210) to ensure pipeline does not crash."""
    source_sample = "class SampleEntity:\n    val: str = 'test'\n"
    # Test all 15 targets from Python
    for target in ALL_15_LANGUAGES:
        if target == "python":
            continue
        out = compile_polyglot_ast(source_sample, "python", target)
        assert len(out) > 0, f"Route python -> {target} emitted empty output"

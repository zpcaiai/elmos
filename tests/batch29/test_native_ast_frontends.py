"""Comprehensive test suite for genuine native compiler AST frontends.

Validates that real host toolchains (Clang, TypeScript Compiler API, SwiftSyntax,
Rust syn, Go go/ast, Python ast, OpenJDK javac, .NET Roslyn) are actively bridged
without text-level regex hacks.
"""

from __future__ import annotations

import pytest
from elmos_polyglot_route.ast_compiler.parsers.native_bridge import NativeBridge
from elmos_polyglot_route.ast_compiler.parsers.typescript_parser import TypeScriptAstParser
from elmos_polyglot_route.ast_compiler.parsers.swift_parser import SwiftAstParser
from elmos_polyglot_route.ast_compiler.parsers.python_parser import PythonAstParser
from elmos_polyglot_route.ast_compiler.parsers.cpp_parser import CppAstParser
from elmos_polyglot_route.ast_compiler.parsers.rust_parser import RustAstParser
from elmos_polyglot_route.ast_compiler.parsers.go_parser import GoAstParser
from elmos_polyglot_route.ast_compiler.parsers.java_parser import JavaAstParser
from elmos_polyglot_route.ast_compiler.parsers.csharp_parser import CSharpAstParser
from elmos_polyglot_route.ast_compiler.ir import IfElseStmt, ReturnStmt, BinaryExpr, VarDeclStmt


def test_native_clang_cpp_ast_extraction():
    """Test Apple Clang -Xclang -ast-dump=json extraction on C++ source."""
    cpp_source = """
    #include <cstdint>
    class AssetAccount {
    public:
        int64_t account_id;
        double balance;
        int64_t get_id() { return account_id; }
        double deposit(double amount) {
            balance = balance + amount;
            return balance;
        }
    };
    """
    mod = NativeBridge.parse_cpp_with_clang(cpp_source)
    assert mod is not None, "Clang bridge failed to parse C++ AST"
    assert len(mod.classes) >= 1
    cls = next(c for c in mod.classes if c.name == "AssetAccount")
    assert len(cls.fields) >= 2
    f_names = [f.name for f in cls.fields]
    assert "account_id" in f_names
    assert "balance" in f_names


def test_native_typescript_compiler_api_ast_extraction():
    """Test official TypeScript Compiler API 5.9.2 extraction on TS source."""
    ts_source = """
    export interface OrderItem {
        id: string;
        price: number;
        quantity: number;
    }

    export function calculateTotal(subtotal: number, taxRate: number): number {
        if (subtotal < 0) {
            return 0;
        }
        return subtotal * (1 + taxRate);
    }
    """
    parser = TypeScriptAstParser()
    mod = parser.parse(ts_source)
    assert mod is not None, "TypeScript parser failed"
    assert any(c.name == "OrderItem" for c in mod.classes)
    order_item = next(c for c in mod.classes if c.name == "OrderItem")
    assert order_item.is_struct
    assert len(order_item.fields) >= 3

    # Check function body statements
    calc_fn = None
    for c in mod.classes:
        for m in c.methods:
            if m.name == "calculateTotal":
                calc_fn = m
                break
    if not calc_fn:
        for fn in mod.free_functions:
            if fn.name == "calculateTotal":
                calc_fn = fn
                break
    assert calc_fn is not None, "calculateTotal function not found"
    assert len(calc_fn.params) == 2
    assert len(calc_fn.body) >= 2
    assert any(isinstance(s, IfElseStmt) for s in calc_fn.body)
    assert any(isinstance(s, ReturnStmt) for s in calc_fn.body)


def test_native_swift_syntax_ast_extraction():
    """Test Apple SwiftSyntax 600.0.1 analyzer extraction on Swift source."""
    swift_source = """
    func difference(_ left: Int64, _ right: Int64) -> Int64 {
        if left < right {
            return 0
        }
        return left - right
    }
    """
    parser = SwiftAstParser()
    mod = parser.parse(swift_source)
    assert mod is not None, "Swift parser failed"
    diff_fn = None
    for c in mod.classes:
        for m in c.methods:
            if m.name == "difference":
                diff_fn = m
                break
    if not diff_fn:
        for fn in mod.free_functions:
            if fn.name == "difference":
                diff_fn = fn
                break
    assert diff_fn is not None, "difference function not found in Swift module"
    assert len(diff_fn.params) == 2
    assert len(diff_fn.body) >= 2
    assert any(isinstance(s, IfElseStmt) for s in diff_fn.body)


def test_native_rust_syn_ast_extraction():
    """Test Rust syn AST analyzer extraction on Rust source."""
    rust_source = """
    pub fn calculate_profit(revenue: i64, cost: i64) -> i64 {
        revenue - cost
    }
    """
    mod = NativeBridge.parse_rust_with_syn(rust_source)
    assert mod is not None, "Rust syn bridge failed"
    assert len(mod.free_functions) >= 1
    fn = mod.free_functions[0]
    assert fn.name == "calculate_profit"
    assert len(fn.params) == 2


def test_native_go_ast_extraction():
    """Test Go official go/ast analyzer extraction on Go source."""
    go_source = """
    package ledger

    type LedgerAccount struct {
        Id int64
        Name string
    }

    func (a *LedgerAccount) Balance() int64 {
        return 1000
    }
    """
    mod = NativeBridge.parse_go_with_ast(go_source)
    assert mod is not None, "Go go/ast bridge failed"
    assert len(mod.classes) >= 1 or len(mod.free_functions) >= 1


def test_native_python_ast_extraction():
    """Test Python standard library AST parser extraction on Python source."""
    py_source = """
    from dataclasses import dataclass

    @dataclass
    class InventoryItem:
        sku: str
        stock: int

    class InventoryService:
        def check_stock(self, item: InventoryItem, required: int) -> bool:
            if item.stock >= required:
                return True
            return False
    """
    parser = PythonAstParser()
    mod = parser.parse(py_source)
    assert mod is not None
    assert len(mod.classes) >= 2
    service_cls = next(c for c in mod.classes if c.name == "InventoryService")
    assert len(service_cls.methods) >= 1
    check_m = service_cls.methods[0]
    assert check_m.name == "check_stock"
    assert len(check_m.body) >= 2


def test_native_java_javac_ast_extraction():
    """Test Java OpenJDK javac Tree API extraction on Java source."""
    java_source = """
    package com.enterprise.banking;

    public class BankAccount {
        private String accountNumber;
        private double balance;

        public double getBalance() {
            return this.balance;
        }
    }
    """
    mod = NativeBridge.parse_java_with_javac(java_source)
    assert mod is not None, "Java javac bridge failed"
    assert len(mod.classes) >= 1
    cls = mod.classes[0]
    assert cls.name == "BankAccount"


def test_native_csharp_roslyn_ast_extraction():
    """Test C# Roslyn EmittedAnalyzer DLL extraction on C# source."""
    csharp_source = """
    namespace Banking {
        public class SavingsAccount {
            public long CalculateInterest(long balance) {
                return balance;
            }
        }
    }
    """
    mod = NativeBridge.parse_csharp_with_roslyn(csharp_source)
    assert mod is not None, "C# Roslyn bridge failed"
    assert len(mod.classes) >= 1
    cls = mod.classes[0]
    assert len(cls.methods) >= 1
    assert cls.methods[0].name == "CalculateInterest"

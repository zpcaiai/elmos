"""Tests for Enterprise Standard Library, Concurrency, and Collections Semantic Shims."""

from __future__ import annotations

import pytest

from elmos_polyglot_route.ast_compiler.ir import (
    BinaryExpr,
    BinaryOperator,
    ConstructExpr,
    ExprStmt,
    FieldAccessExpr,
    IdentifierExpr,
    LiteralExpr,
    MethodCallExpr,
    UniversalClass,
    UniversalExpr,
    UniversalField,
    UniversalMethod,
    UniversalParam,
    UniversalStmt,
    UniversalType,
)
from elmos_polyglot_route.ast_compiler.lowering import EnterpriseShimsLowering


def test_concurrent_map_type_and_method_lowering():
    """Verify concurrent map type translation and method lowering."""
    m_type = UniversalType.custom("ConcurrentMap")
    m_type.key_type = UniversalType.string_type()
    m_type.value_type = UniversalType.int64()

    # Types
    java_t = EnterpriseShimsLowering.lower_concurrent_map_type(m_type, "java")
    assert "ConcurrentHashMap<string, i64>" in java_t.name

    cs_t = EnterpriseShimsLowering.lower_concurrent_map_type(m_type, "csharp")
    assert "ConcurrentDictionary<string, i64>" in cs_t.name

    rust_t = EnterpriseShimsLowering.lower_concurrent_map_type(m_type, "rust")
    assert "Arc<DashMap<string, i64>>" in rust_t.name

    go_t = EnterpriseShimsLowering.lower_concurrent_map_type(m_type, "go")
    assert go_t.name == "sync.Map"

    # Calls
    map_var = IdentifierExpr("cache")
    k = LiteralExpr("user_1", "string")
    v = LiteralExpr(42, "int")

    # Go get/put
    go_get = EnterpriseShimsLowering.lower_concurrent_map_call(map_var, "get", [k], "go")
    assert isinstance(go_get, MethodCallExpr) and go_get.method_name == "Load"

    go_put = EnterpriseShimsLowering.lower_concurrent_map_call(map_var, "put", [k, v], "go")
    assert isinstance(go_put, MethodCallExpr) and go_put.method_name == "Store"

    # C# get/put
    cs_get = EnterpriseShimsLowering.lower_concurrent_map_call(map_var, "get", [k], "csharp")
    assert cs_get.method_name == "TryGetValue"

    cs_put_if_absent = EnterpriseShimsLowering.lower_concurrent_map_call(map_var, "putIfAbsent", [k, v], "csharp")
    assert cs_put_if_absent.method_name == "GetOrAdd"

    # Rust putIfAbsent
    rust_entry = EnterpriseShimsLowering.lower_concurrent_map_call(map_var, "computeIfAbsent", [k, v], "rust")
    assert rust_entry.method_name == "or_insert"
    assert rust_entry.target.method_name == "entry"


def test_atomic_variables_and_cas_lowering():
    """Verify lock-free atomic operations lowering across Go, Rust, C#."""
    counter = IdentifierExpr("activeUsers")

    # Rust
    rs_inc = EnterpriseShimsLowering.lower_atomic_call(counter, "incrementAndGet", [], "rust")
    assert rs_inc.method_name == "fetch_add"
    assert any("Ordering::SeqCst" in getattr(arg, "name", "") for arg in rs_inc.args)

    rs_cas = EnterpriseShimsLowering.lower_atomic_call(
        counter, "compareAndSet", [LiteralExpr(10, "int"), LiteralExpr(20, "int")], "rust"
    )
    assert rs_cas.method_name == "compare_exchange"

    # Go
    go_inc = EnterpriseShimsLowering.lower_atomic_call(counter, "incrementAndGet", [], "go")
    assert go_inc.method_name == "Add"
    assert go_inc.args[0].value == 1

    go_cas = EnterpriseShimsLowering.lower_atomic_call(
        counter, "compareAndSet", [LiteralExpr(10, "int"), LiteralExpr(20, "int")], "go"
    )
    assert go_cas.method_name == "CompareAndSwap"

    # C#
    cs_inc = EnterpriseShimsLowering.lower_atomic_call(counter, "incrementAndGet", [], "csharp")
    assert cs_inc.target.name == "Interlocked"
    assert cs_inc.method_name == "Increment"


def test_channel_pipeline_lowering():
    """Verify typed channel pipelines across Go, Rust, C#, Java."""
    ch_var = IdentifierExpr("jobQueue")
    item = LiteralExpr("job_42", "string")

    # Go: ch.Send(item)
    go_send = EnterpriseShimsLowering.lower_channel_send(ch_var, item, "go")
    assert isinstance(go_send, ExprStmt)
    assert isinstance(go_send.expr, MethodCallExpr)
    assert go_send.expr.target.name == "jobQueue"
    assert go_send.expr.method_name == "Send"

    # Rust: ch.send(item).await
    rs_send = EnterpriseShimsLowering.lower_channel_send(ch_var, item, "rust")
    assert isinstance(rs_send, ExprStmt)
    assert rs_send.expr.method_name == "await"
    assert rs_send.expr.target.method_name == "send"

    # Java: ch.put(item)
    java_send = EnterpriseShimsLowering.lower_channel_send(ch_var, item, "java")
    assert isinstance(java_send, ExprStmt)
    assert java_send.expr.method_name == "put"


def test_async_all_of_composition():
    """Verify async composition (CompletableFuture.allOf, Task.WhenAll, tokio, asyncio)."""
    f1 = IdentifierExpr("taskA")
    f2 = IdentifierExpr("taskB")

    java_all = EnterpriseShimsLowering.lower_async_all_of([f1, f2], "java")
    assert java_all.target.name == "CompletableFuture"
    assert java_all.method_name == "allOf"

    cs_all = EnterpriseShimsLowering.lower_async_all_of([f1, f2], "csharp")
    assert cs_all.target.name == "Task"
    assert cs_all.method_name == "WhenAll"

    rs_all = EnterpriseShimsLowering.lower_async_all_of([f1, f2], "rust")
    assert rs_all.target.name == "tokio"
    assert rs_all.method_name == "try_join"

    py_all = EnterpriseShimsLowering.lower_async_all_of([f1, f2], "python")
    assert py_all.target.name == "asyncio"
    assert py_all.method_name == "gather"


def test_stream_pipeline_lowering():
    """Verify stream filter -> map -> collect lowering across C# LINQ, Rust Iterator, Java Stream."""
    coll = IdentifierExpr("orders")
    pred = IdentifierExpr("is_valid")
    mapper = IdentifierExpr("extract_price")
    ops = [("filter", pred), ("map", mapper)]

    # C# LINQ: orders.Where(pred).Select(mapper).ToList()
    cs_linq = EnterpriseShimsLowering.lower_stream_pipeline(coll, ops, "csharp")
    assert cs_linq.method_name == "ToList"
    assert cs_linq.target.method_name == "Select"
    assert cs_linq.target.target.method_name == "Where"

    # Rust Iterator: orders.into_iter().filter(pred).map(mapper).collect()
    rs_iter = EnterpriseShimsLowering.lower_stream_pipeline(coll, ops, "rust")
    assert rs_iter.method_name == "collect"
    assert rs_iter.target.method_name == "map"
    assert rs_iter.target.target.method_name == "filter"
    assert rs_iter.target.target.target.method_name == "into_iter"

    # Java Stream: orders.stream().filter(pred).map(mapper).collect(Collectors.toList())
    java_stream = EnterpriseShimsLowering.lower_stream_pipeline(coll, ops, "java")
    assert java_stream.method_name == "collect"
    assert java_stream.target.method_name == "map"
    assert java_stream.target.target.method_name == "filter"
    assert java_stream.target.target.target.method_name == "stream"

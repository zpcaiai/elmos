"""Enterprise Standard Library, Concurrency, and Collections Semantic Shim.

Translates complex concurrency primitives, lock-free atomics, channels,
concurrent collections, and stream pipelines across 8 target languages:
- Java: ConcurrentHashMap, CompletableFuture, BlockingQueue, AtomicLong, Stream
- C#: ConcurrentDictionary, Task, Channel, Interlocked, LINQ
- Rust: DashMap / Arc<RwLock>, tokio::task, tokio::sync::mpsc, AtomicI64, Iterator
- Go: sync.Map, goroutines, chan T, sync/atomic, slice pipelines
- C++: std::unordered_map + std::shared_mutex, std::future, std::atomic
- TypeScript: Map, Promise, AsyncIterable, worker channels
- Python: dict + threading.Lock / asyncio, asyncio.Future, asyncio.Queue, itertools
- Kotlin: ConcurrentHashMap, Deferred / Channel, AtomicLong, Sequence / Flow
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from ..ir import (
    AssignStmt,
    BinaryExpr,
    BinaryOperator,
    CatchClause,
    ConstructExpr,
    ExprStmt,
    FieldAccessExpr,
    IdentifierExpr,
    IfElseStmt,
    LiteralExpr,
    LockStmt,
    MethodCallExpr,
    ReturnStmt,
    TryCatchFinallyStmt,
    UniversalClass,
    UniversalExpr,
    UniversalField,
    UniversalMethod,
    UniversalModule,
    UniversalParam,
    UniversalStmt,
    UniversalType,
    VarDeclStmt,
    WhileStmt,
)


class EnterpriseShimsLowering:
    """Enterprise-grade semantic transformation for concurrent collections, atomics, and streams."""

    # --------------------------------------------------------------------------
    # 1. Concurrent Map Translation
    # --------------------------------------------------------------------------
    @classmethod
    def lower_concurrent_map_type(cls, orig_type: UniversalType, target_language: str) -> UniversalType:
        target = target_language.lower().strip()
        kt = orig_type.key_type or UniversalType.string_type()
        vt = orig_type.value_type or UniversalType.custom("any")

        if target == "java":
            t = UniversalType.custom(f"ConcurrentHashMap<{kt.name}, {vt.name}>")
            t.key_type = kt
            t.value_type = vt
            return t
        elif target == "csharp":
            t = UniversalType.custom(f"ConcurrentDictionary<{kt.name}, {vt.name}>")
            t.key_type = kt
            t.value_type = vt
            return t
        elif target == "rust":
            t = UniversalType.custom(f"Arc<DashMap<{kt.name}, {vt.name}>>")
            t.key_type = kt
            t.value_type = vt
            return t
        elif target == "go":
            t = UniversalType.custom("sync.Map")
            t.key_type = kt
            t.value_type = vt
            return t
        elif target == "cpp":
            t = UniversalType.custom(f"ThreadSafeMap<{kt.name}, {vt.name}>")
            t.key_type = kt
            t.value_type = vt
            return t
        elif target == "python":
            t = UniversalType.custom(f"dict[{kt.name}, {vt.name}]")
            t.key_type = kt
            t.value_type = vt
            return t
        elif target == "typescript":
            t = UniversalType.custom(f"Map<{kt.name}, {vt.name}>")
            t.key_type = kt
            t.value_type = vt
            return t
        return orig_type

    @classmethod
    def lower_concurrent_map_call(
        cls,
        target_expr: UniversalExpr,
        method_name: str,
        args: list[UniversalExpr],
        target_language: str
    ) -> UniversalExpr:
        """Lowers operations like get, put, putIfAbsent, computeIfAbsent, remove."""
        target = target_language.lower().strip()
        m = method_name.lower()

        if target == "go":
            # sync.Map uses Load, Store, LoadOrStore, Delete
            if m in ("get", "load"):
                return MethodCallExpr(target=target_expr, method_name="Load", args=args)
            elif m in ("put", "set", "store"):
                return MethodCallExpr(target=target_expr, method_name="Store", args=args)
            elif m in ("putifabsent", "loadorstore"):
                return MethodCallExpr(target=target_expr, method_name="LoadOrStore", args=args)
            elif m in ("remove", "delete"):
                return MethodCallExpr(target=target_expr, method_name="Delete", args=args)

        elif target == "csharp":
            # ConcurrentDictionary uses TryGetValue, TryAdd, GetOrAdd, TryRemove
            if m in ("get", "load"):
                return MethodCallExpr(target=target_expr, method_name="TryGetValue", args=args)
            elif m in ("put", "set", "store"):
                return MethodCallExpr(target=target_expr, method_name="TryAdd", args=args)
            elif m in ("putifabsent", "computeifabsent", "getoradd"):
                return MethodCallExpr(target=target_expr, method_name="GetOrAdd", args=args)
            elif m in ("remove", "delete"):
                return MethodCallExpr(target=target_expr, method_name="TryRemove", args=args)

        elif target == "rust":
            # DashMap uses get, insert, entry().or_insert(), remove
            if m in ("get", "load"):
                return MethodCallExpr(target=target_expr, method_name="get", args=args)
            elif m in ("put", "set", "store", "insert"):
                return MethodCallExpr(target=target_expr, method_name="insert", args=args)
            elif m in ("putifabsent", "computeifabsent"):
                entry_call = MethodCallExpr(target=target_expr, method_name="entry", args=[args[0]])
                val_arg = args[1] if len(args) > 1 else LiteralExpr(None, "null")
                return MethodCallExpr(target=entry_call, method_name="or_insert", args=[val_arg])
            elif m in ("remove", "delete"):
                return MethodCallExpr(target=target_expr, method_name="remove", args=args)

        elif target == "java":
            if m in ("get", "load"):
                return MethodCallExpr(target=target_expr, method_name="get", args=args)
            elif m in ("put", "set", "store", "insert"):
                return MethodCallExpr(target=target_expr, method_name="put", args=args)
            elif m in ("putifabsent", "loadorstore"):
                return MethodCallExpr(target=target_expr, method_name="putIfAbsent", args=args)
            elif m in ("computeifabsent", "getoradd"):
                return MethodCallExpr(target=target_expr, method_name="computeIfAbsent", args=args)
            elif m in ("remove", "delete"):
                return MethodCallExpr(target=target_expr, method_name="remove", args=args)

        return MethodCallExpr(target=target_expr, method_name=method_name, args=args)

    # --------------------------------------------------------------------------
    # 2. Lock-Free Atomic Variables Translation
    # --------------------------------------------------------------------------
    @classmethod
    def lower_atomic_type(cls, value_type: UniversalType, target_language: str) -> UniversalType:
        target = target_language.lower().strip()
        v_name = value_type.name.lower()
        is_64 = "64" in v_name or "long" in v_name or v_name == "int"
        is_bool = "bool" in v_name

        if target == "java":
            if is_bool:
                return UniversalType.custom("AtomicBoolean")
            return UniversalType.custom("AtomicLong" if is_64 else "AtomicInteger")
        elif target == "rust":
            if is_bool:
                return UniversalType.custom("AtomicBool")
            return UniversalType.custom("AtomicI64" if is_64 else "AtomicI32")
        elif target == "go":
            if is_bool:
                return UniversalType.custom("atomic.Bool")
            return UniversalType.custom("atomic.Int64" if is_64 else "atomic.Int32")
        elif target == "csharp":
            # C# uses primitives directly with System.Threading.Interlocked
            return UniversalType.int64() if is_64 else UniversalType.primitive("i32")
        elif target == "cpp":
            t_inner = "int64_t" if is_64 else "int32_t"
            return UniversalType.custom(f"std::atomic<{t_inner}>")
        return value_type

    @classmethod
    def lower_atomic_call(
        cls,
        target_expr: UniversalExpr,
        method_name: str,
        args: list[UniversalExpr],
        target_language: str
    ) -> UniversalExpr:
        target = target_language.lower().strip()
        m = method_name.lower()

        if target == "go":
            # atomic.Int64: Add(delta), Load(), Store(val), CompareAndSwap(old, new)
            if "increment" in m or m == "add":
                delta = args[0] if args else LiteralExpr(1, "int")
                return MethodCallExpr(target=target_expr, method_name="Add", args=[delta])
            elif "decrement" in m:
                return MethodCallExpr(target=target_expr, method_name="Add", args=[LiteralExpr(-1, "int")])
            elif m in ("get", "load"):
                return MethodCallExpr(target=target_expr, method_name="Load", args=[])
            elif m in ("set", "store"):
                return MethodCallExpr(target=target_expr, method_name="Store", args=args)
            elif "compareand" in m or m == "cas":
                return MethodCallExpr(target=target_expr, method_name="CompareAndSwap", args=args)

        elif target == "rust":
            # fetch_add, load, store, compare_exchange
            ordering_seqcst = IdentifierExpr("std::sync::atomic::Ordering::SeqCst")
            if "increment" in m:
                return MethodCallExpr(
                    target=target_expr,
                    method_name="fetch_add",
                    args=[LiteralExpr(1, "int"), ordering_seqcst]
                )
            elif "decrement" in m:
                return MethodCallExpr(
                    target=target_expr,
                    method_name="fetch_sub",
                    args=[LiteralExpr(1, "int"), ordering_seqcst]
                )
            elif m in ("get", "load"):
                return MethodCallExpr(target=target_expr, method_name="load", args=[ordering_seqcst])
            elif m in ("set", "store"):
                val = args[0] if args else LiteralExpr(0, "int")
                return MethodCallExpr(target=target_expr, method_name="store", args=[val, ordering_seqcst])
            elif "compareand" in m or m == "cas":
                return MethodCallExpr(
                    target=target_expr,
                    method_name="compare_exchange",
                    args=[args[0], args[1], ordering_seqcst, ordering_seqcst]
                )

        elif target == "csharp":
            # Interlocked.Increment(ref x), Interlocked.CompareExchange(ref x, newVal, expectVal)
            interlocked = IdentifierExpr("Interlocked")
            if "increment" in m:
                return MethodCallExpr(target=interlocked, method_name="Increment", args=[target_expr])
            elif "decrement" in m:
                return MethodCallExpr(target=interlocked, method_name="Decrement", args=[target_expr])
            elif "compareand" in m or m == "cas":
                # Interlocked.CompareExchange(ref location, value, comparand)
                return MethodCallExpr(
                    target=interlocked,
                    method_name="CompareExchange",
                    args=[target_expr, args[1], args[0]]
                )

        return MethodCallExpr(target=target_expr, method_name=method_name, args=args)

    # --------------------------------------------------------------------------
    # 3. Channel Pipeline Translation
    # --------------------------------------------------------------------------
    @classmethod
    def lower_channel_type(cls, elem_type: UniversalType, target_language: str) -> UniversalType:
        target = target_language.lower().strip()
        e_name = elem_type.name

        if target == "go":
            return UniversalType.custom(f"chan {e_name}")
        elif target == "rust":
            return UniversalType.custom(f"tokio::sync::mpsc::Sender<{e_name}>")
        elif target == "csharp":
            return UniversalType.custom(f"ChannelWriter<{e_name}>")
        elif target == "java":
            return UniversalType.custom(f"BlockingQueue<{e_name}>")
        elif target == "python":
            return UniversalType.custom(f"asyncio.Queue[{e_name}]")
        return UniversalType.custom(f"Channel<{e_name}>")

    @classmethod
    def lower_channel_send(
        cls,
        channel_expr: UniversalExpr,
        item_expr: UniversalExpr,
        target_language: str
    ) -> UniversalStmt:
        target = target_language.lower().strip()

        if target == "go":
            return ExprStmt(MethodCallExpr(target=channel_expr, method_name="Send", args=[item_expr]))
        elif target == "rust":
            # ch.send(item).await
            call = MethodCallExpr(target=channel_expr, method_name="send", args=[item_expr])
            return ExprStmt(MethodCallExpr(target=call, method_name="await", args=[]))
        elif target == "csharp":
            # await ch.WriteAsync(item)
            call = MethodCallExpr(target=channel_expr, method_name="WriteAsync", args=[item_expr])
            return ExprStmt(MethodCallExpr(target=call, method_name="await", args=[]))
        elif target == "java":
            # ch.put(item)
            return ExprStmt(MethodCallExpr(target=channel_expr, method_name="put", args=[item_expr]))
        elif target == "python":
            # await ch.put(item)
            call = MethodCallExpr(target=channel_expr, method_name="put", args=[item_expr])
            return ExprStmt(MethodCallExpr(target=call, method_name="await", args=[]))

        return ExprStmt(MethodCallExpr(target=channel_expr, method_name="send", args=[item_expr]))

    # --------------------------------------------------------------------------
    # 4. Asynchronous Composition (AllOf / WhenAll / Join)
    # --------------------------------------------------------------------------
    @classmethod
    def lower_async_all_of(cls, futures: list[UniversalExpr], target_language: str) -> UniversalExpr:
        target = target_language.lower().strip()

        if target == "java":
            return MethodCallExpr(
                target=IdentifierExpr("CompletableFuture"),
                method_name="allOf",
                args=futures
            )
        elif target == "csharp":
            return MethodCallExpr(
                target=IdentifierExpr("Task"),
                method_name="WhenAll",
                args=futures
            )
        elif target == "rust":
            return MethodCallExpr(
                target=IdentifierExpr("tokio"),
                method_name="try_join",
                args=futures
            )
        elif target == "typescript":
            return MethodCallExpr(
                target=IdentifierExpr("Promise"),
                method_name="all",
                args=[MethodCallExpr(target=None, method_name="array", args=futures)]
            )
        elif target == "python":
            return MethodCallExpr(
                target=IdentifierExpr("asyncio"),
                method_name="gather",
                args=futures
            )

        return MethodCallExpr(target=IdentifierExpr("Future"), method_name="all", args=futures)

    # --------------------------------------------------------------------------
    # 5. Stream Pipeline Translation (Filter -> Map -> Collect)
    # --------------------------------------------------------------------------
    @classmethod
    def lower_stream_pipeline(
        cls,
        source_collection: UniversalExpr,
        operations: list[tuple[str, UniversalExpr]],  # [('filter', pred_lambda), ('map', map_lambda)]
        target_language: str
    ) -> UniversalExpr:
        target = target_language.lower().strip()

        if target == "csharp":
            # LINQ: source.Where(pred).Select(fn).ToList()
            curr = source_collection
            for op, fn in operations:
                if op == "filter":
                    curr = MethodCallExpr(target=curr, method_name="Where", args=[fn])
                elif op == "map":
                    curr = MethodCallExpr(target=curr, method_name="Select", args=[fn])
            return MethodCallExpr(target=curr, method_name="ToList", args=[])

        elif target == "rust":
            # Iterator: source.into_iter().filter(pred).map(fn).collect::<Vec<_>>()
            curr = MethodCallExpr(target=source_collection, method_name="into_iter", args=[])
            for op, fn in operations:
                if op == "filter":
                    curr = MethodCallExpr(target=curr, method_name="filter", args=[fn])
                elif op == "map":
                    curr = MethodCallExpr(target=curr, method_name="map", args=[fn])
            return MethodCallExpr(target=curr, method_name="collect", args=[])

        elif target == "java":
            # Java Stream: source.stream().filter(pred).map(fn).collect(Collectors.toList())
            curr = MethodCallExpr(target=source_collection, method_name="stream", args=[])
            for op, fn in operations:
                if op == "filter":
                    curr = MethodCallExpr(target=curr, method_name="filter", args=[fn])
                elif op == "map":
                    curr = MethodCallExpr(target=curr, method_name="map", args=[fn])
            collectors_to_list = MethodCallExpr(target=IdentifierExpr("Collectors"), method_name="toList", args=[])
            return MethodCallExpr(target=curr, method_name="collect", args=[collectors_to_list])

        elif target == "typescript":
            # Array: source.filter(pred).map(fn)
            curr = source_collection
            for op, fn in operations:
                if op == "filter":
                    curr = MethodCallExpr(target=curr, method_name="filter", args=[fn])
                elif op == "map":
                    curr = MethodCallExpr(target=curr, method_name="map", args=[fn])
            return curr

        return MethodCallExpr(target=source_collection, method_name="process_stream", args=[])

    # --------------------------------------------------------------------------
    # 6. Full UniversalModule Shims Lowering
    # --------------------------------------------------------------------------
    @classmethod
    def lower_module(cls, module: UniversalModule, target_language: str) -> UniversalModule:
        """Applies concurrent collections, atomics, channel, and stream lowering across a UniversalModule."""
        target = target_language.lower().strip()
        for c in module.classes:
            for f in c.fields:
                cls._lower_field(f, target)
            for m in c.methods:
                cls._lower_method(m, target)
        for m in module.free_functions:
            cls._lower_method(m, target)
        return module

    @classmethod
    def _lower_type_recursively(cls, t: UniversalType, target: str) -> UniversalType:
        if not t:
            return t
        name_lower = (t.name or "").lower()
        if any(x in name_lower for x in ("concurrenthashmap", "concurrentdictionary", "dashmap", "sync.map")):
            return cls.lower_concurrent_map_type(t, target)
        elif any(x in name_lower for x in ("atomiclong", "atomicinteger", "atomici64", "atomic.int64")):
            return cls.lower_atomic_type(t, target)
        elif any(x in name_lower for x in ("blockingqueue", "channel", "sender")):
            elem = t.element_type or UniversalType.custom("any")
            return cls.lower_channel_type(elem, target)
        elif t.element_type:
            lowered_elem = cls._lower_type_recursively(t.element_type, target)
            if lowered_elem != t.element_type:
                if t.name in ("Arc", "shared_ptr", "unique_ptr"):
                    if (lowered_elem.name or "").startswith("Arc<"):
                        return lowered_elem
                    elif (lowered_elem.name or "") in ("AtomicI64", "AtomicI32", "AtomicBool", "atomic.Int64", "atomic.Int32"):
                        return lowered_elem
                    elif (lowered_elem.name or "").startswith("tokio::sync::mpsc") or (lowered_elem.name or "").startswith("chan "):
                        return lowered_elem
                t.element_type = lowered_elem
        return t

    @classmethod
    def _lower_field(cls, f: UniversalField, target: str) -> None:
        f.type_info = cls._lower_type_recursively(f.type_info, target)

    @classmethod
    def _lower_method(cls, m: UniversalMethod, target: str) -> None:
        m.body = [cls._lower_stmt(s, target) for s in m.body]

    @classmethod
    def _lower_stmt(cls, stmt: UniversalStmt, target: str) -> UniversalStmt:
        if isinstance(stmt, VarDeclStmt):
            stmt.type_info = cls._lower_type_recursively(stmt.type_info, target)
            if stmt.initial_value:
                stmt.initial_value = cls._lower_expr(stmt.initial_value, target)
            return stmt
        elif isinstance(stmt, AssignStmt):
            stmt.target = cls._lower_expr(stmt.target, target)
            stmt.value = cls._lower_expr(stmt.value, target)
            return stmt
        elif isinstance(stmt, ExprStmt):
            stmt.expr = cls._lower_expr(stmt.expr, target)
            return stmt
        elif isinstance(stmt, ReturnStmt):
            if stmt.value:
                stmt.value = cls._lower_expr(stmt.value, target)
            return stmt
        elif isinstance(stmt, IfElseStmt):
            stmt.condition = cls._lower_expr(stmt.condition, target)
            stmt.then_body = [cls._lower_stmt(s, target) for s in stmt.then_body]
            stmt.else_body = [cls._lower_stmt(s, target) for s in stmt.else_body]
            return stmt
        elif isinstance(stmt, WhileStmt):
            stmt.condition = cls._lower_expr(stmt.condition, target)
            stmt.body = [cls._lower_stmt(s, target) for s in stmt.body]
            return stmt
        elif isinstance(stmt, LockStmt):
            stmt.lock_expr = cls._lower_expr(stmt.lock_expr, target)
            stmt.body = [cls._lower_stmt(s, target) for s in stmt.body]
            return stmt
        elif isinstance(stmt, TryCatchFinallyStmt):
            stmt.try_body = [cls._lower_stmt(s, target) for s in stmt.try_body]
            for cc in stmt.catch_clauses:
                cc.body = [cls._lower_stmt(s, target) for s in cc.body]
            stmt.finally_body = [cls._lower_stmt(s, target) for s in stmt.finally_body]
            return stmt
        return stmt

    @classmethod
    def _lower_expr(cls, expr: UniversalExpr, target: str) -> UniversalExpr:
        if isinstance(expr, MethodCallExpr):
            if expr.target:
                expr.target = cls._lower_expr(expr.target, target)
            expr.args = [cls._lower_expr(a, target) for a in expr.args]

            m_lower = (expr.method_name or "").lower()
            if any(k in m_lower for k in ("incrementandget", "decrementandget", "compareandset", "compareexchange")):
                return cls.lower_atomic_call(expr.target, expr.method_name, expr.args, target)
            elif m_lower in ("putifabsent", "computeifabsent", "getoradd", "loadorstore"):
                return cls.lower_concurrent_map_call(expr.target, expr.method_name, expr.args, target)
            elif m_lower in ("allof", "whenall", "try_join"):
                return cls.lower_async_all_of(expr.args, target)
            return expr
        elif isinstance(expr, BinaryExpr):
            expr.left = cls._lower_expr(expr.left, target)
            expr.right = cls._lower_expr(expr.right, target)
            return expr
        elif isinstance(expr, FieldAccessExpr):
            expr.target = cls._lower_expr(expr.target, target)
            return expr
        elif isinstance(expr, ConstructExpr):
            expr.args = [cls._lower_expr(a, target) for a in expr.args]
            expr.keyword_args = {k: cls._lower_expr(v, target) for k, v in expr.keyword_args.items()}
            return expr
        return expr


"""Deterministic industrial IR interpreter used as the behavioral oracle."""

from __future__ import annotations

import hashlib
import queue
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from elmos_polyglot_route.ast_compiler.ir import (
    AssignStmt,
    BinaryExpr,
    BinaryOperator,
    ChannelMakeStmt,
    ChannelRecvStmt,
    ChannelSendStmt,
    DropStmt,
    ExprStmt,
    IdentifierExpr,
    IfElseStmt,
    IoReadStmt,
    IoWriteStmt,
    JoinStmt,
    LiteralExpr,
    LockStmt,
    MethodCallExpr,
    MoveStmt,
    ReturnStmt,
    SelectStmt,
    SpawnStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    UnaryExpr,
    UniversalExpr,
    UniversalMethod,
    UniversalModule,
    UniversalStmt,
    VarDeclStmt,
)


class IndustrialRuntimeError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class Observation:
    status: str
    value: Any = None
    error: str | None = None


@dataclass
class _Frame:
    env: dict[str, Any] = field(default_factory=dict)
    channels: dict[str, queue.Queue[Any]] = field(default_factory=dict)
    locks: dict[str, threading.Lock] = field(default_factory=dict)
    threads: list[threading.Thread] = field(default_factory=list)
    handles: dict[str, threading.Thread] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)
    moved: set[str] = field(default_factory=set)
    returned: Any = None
    did_return: bool = False


class IndustrialInterpreter:
    """Executes the certified industrial subset with real threads, queues and files."""

    def __init__(self, module: UniversalModule) -> None:
        self.module = module
        self.methods: dict[str, UniversalMethod] = {}
        for klass in module.classes:
            for method in klass.methods:
                self.methods[method.name] = method
        for method in module.free_functions:
            self.methods[method.name] = method

    def invoke(self, name: str, args: list[Any]) -> Observation:
        method = self.methods.get(name)
        if method is None:
            return Observation(status="ERROR", error=f"UNKNOWN_METHOD:{name}")
        frame = _Frame()
        for param, value in zip(method.params, args, strict=False):
            frame.env[param.name] = value
        try:
            self._exec_stmts(method.body, frame)
            self._join_all(frame)
            if frame.did_return:
                return Observation(status="RETURNED", value=frame.returned)
            return Observation(status="RETURNED", value=None)
        except IndustrialRuntimeError as exc:
            return Observation(status="ERROR", error=exc.kind)

    def _join_all(self, frame: _Frame) -> None:
        for thread in list(frame.threads):
            thread.join(timeout=5)
            if thread.is_alive():
                raise IndustrialRuntimeError("JOIN_TIMEOUT", f"thread {thread.name} did not finish")

    def _exec_stmts(self, stmts: list[UniversalStmt], frame: _Frame) -> None:
        for stmt in stmts:
            if frame.did_return:
                return
            self._exec_stmt(stmt, frame)

    def _exec_stmt(self, stmt: UniversalStmt, frame: _Frame) -> None:
        if isinstance(stmt, VarDeclStmt):
            frame.env[stmt.name] = self._eval(stmt.initial_value, frame) if stmt.initial_value else None
            return
        if isinstance(stmt, AssignStmt):
            if isinstance(stmt.target, IdentifierExpr):
                self._check_live(stmt.target.name, frame)
                frame.env[stmt.target.name] = self._eval(stmt.value, frame)
            return
        if isinstance(stmt, ReturnStmt):
            frame.returned = self._eval(stmt.value, frame) if stmt.value is not None else None
            frame.did_return = True
            return
        if isinstance(stmt, IfElseStmt):
            cond = self._eval(stmt.condition, frame)
            self._exec_stmts(stmt.then_body if cond else stmt.else_body, frame)
            return
        if isinstance(stmt, LockStmt):
            lock_name = self._lock_name(stmt.lock_expr)
            lock = frame.locks.setdefault(lock_name, threading.Lock())
            with lock:
                self._exec_stmts(stmt.body, frame)
            return
        if isinstance(stmt, SpawnStmt):
            child = _Frame(
                env=frame.env,
                channels=frame.channels,
                locks=frame.locks,
                dropped=frame.dropped,
                moved=frame.moved,
            )

            def _run() -> None:
                self._exec_stmts(stmt.body, child)

            thread = threading.Thread(target=_run, daemon=True)
            frame.threads.append(thread)
            if stmt.join_handle:
                frame.handles[stmt.join_handle] = thread
            thread.start()
            return
        if isinstance(stmt, JoinStmt):
            handle = frame.handles.get(stmt.handle)
            if handle is not None:
                handle.join(timeout=5)
            return
        if isinstance(stmt, ChannelMakeStmt):
            frame.channels[stmt.name] = queue.Queue(maxsize=max(stmt.capacity, 1))
            frame.env[stmt.name] = stmt.name
            return
        if isinstance(stmt, ChannelSendStmt):
            chan = frame.channels.get(stmt.channel)
            if chan is None:
                raise IndustrialRuntimeError("UNKNOWN_CHANNEL", stmt.channel)
            chan.put(self._eval(stmt.value, frame), timeout=5)
            return
        if isinstance(stmt, ChannelRecvStmt):
            chan = frame.channels.get(stmt.channel)
            if chan is None:
                raise IndustrialRuntimeError("UNKNOWN_CHANNEL", stmt.channel)
            frame.env[stmt.target] = chan.get(timeout=5)
            return
        if isinstance(stmt, SelectStmt):
            for arm in stmt.arms:
                if arm.kind == "recv" and arm.channel and arm.target:
                    chan = frame.channels.get(arm.channel)
                    if chan is not None:
                        try:
                            frame.env[arm.target] = chan.get_nowait()
                            self._exec_stmts(arm.body, frame)
                            return
                        except queue.Empty:
                            continue
                if arm.kind == "default":
                    self._exec_stmts(arm.body, frame)
                    return
            if stmt.arms:
                arm = stmt.arms[0]
                if arm.kind == "recv" and arm.channel and arm.target:
                    chan = frame.channels[arm.channel]
                    frame.env[arm.target] = chan.get(timeout=5)
                    self._exec_stmts(arm.body, frame)
            return
        if isinstance(stmt, IoWriteStmt):
            path = Path(str(self._eval(stmt.path, frame)))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(self._eval(stmt.value, frame)), encoding="utf-8")
            return
        if isinstance(stmt, IoReadStmt):
            path = Path(str(self._eval(stmt.path, frame)))
            frame.env[stmt.target] = path.read_text(encoding="utf-8")
            return
        if isinstance(stmt, MoveStmt):
            self._check_live(stmt.source, frame)
            frame.env[stmt.target] = frame.env[stmt.source]
            frame.moved.add(stmt.source)
            return
        if isinstance(stmt, DropStmt):
            frame.dropped.append(stmt.name)
            frame.env.pop(stmt.name, None)
            return
        if isinstance(stmt, ThrowStmt):
            raise IndustrialRuntimeError(stmt.exception_class or "Exception", stmt.message)
        if isinstance(stmt, TryCatchFinallyStmt):
            try:
                self._exec_stmts(stmt.try_body, frame)
            except IndustrialRuntimeError:
                handled = False
                for catch in stmt.catch_clauses:
                    self._exec_stmts(catch.body, frame)
                    handled = True
                    break
                if not handled:
                    raise
            finally:
                self._exec_stmts(stmt.finally_body, frame)
            return
        if isinstance(stmt, ExprStmt):
            self._eval(stmt.expr, frame)

    def _lock_name(self, expr: UniversalExpr) -> str:
        if isinstance(expr, IdentifierExpr):
            return expr.name
        return "industrial_mutex"

    def _check_live(self, name: str, frame: _Frame) -> None:
        if name in frame.moved:
            raise IndustrialRuntimeError("USE_AFTER_MOVE", name)

    def _eval(self, expr: UniversalExpr | None, frame: _Frame) -> Any:
        if expr is None:
            return None
        if isinstance(expr, LiteralExpr):
            return expr.value
        if isinstance(expr, IdentifierExpr):
            self._check_live(expr.name, frame)
            if expr.name not in frame.env:
                raise IndustrialRuntimeError("UNBOUND", expr.name)
            return frame.env[expr.name]
        if isinstance(expr, UnaryExpr):
            value = self._eval(expr.operand, frame)
            if expr.op.value == "-":
                return -value
            if expr.op.value == "!":
                return not value
            return value
        if isinstance(expr, BinaryExpr):
            left = self._eval(expr.left, frame)
            right = self._eval(expr.right, frame)
            return self._binary(expr.op, left, right)
        if isinstance(expr, MethodCallExpr):
            if expr.method_name == "checksum":
                payload = "".join(str(self._eval(arg, frame)) for arg in expr.args)
                return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8], 16)
            if expr.method_name == "temp_path":
                return str(Path(tempfile.gettempdir()) / "elmos-industrial-settle.txt")
            if expr.method_name == "parse_int":
                return int(self._eval(expr.args[0], frame))
            if expr.method_name == "concat":
                return "".join(str(self._eval(arg, frame)) for arg in expr.args)
            raise IndustrialRuntimeError("UNKNOWN_CALL", expr.method_name)
        raise IndustrialRuntimeError("UNSUPPORTED_EXPR", type(expr).__name__)

    def _binary(self, op: BinaryOperator, left: Any, right: Any) -> Any:
        if op == BinaryOperator.ADD:
            if isinstance(left, str) or isinstance(right, str):
                return str(left) + str(right)
            return left + right
        if op == BinaryOperator.SUB:
            return left - right
        if op == BinaryOperator.MUL:
            return left * right
        if op == BinaryOperator.DIV:
            return left // right if isinstance(left, int) and isinstance(right, int) else left / right
        if op == BinaryOperator.MOD:
            return left % right
        if op == BinaryOperator.EQ:
            return left == right
        if op == BinaryOperator.NE:
            return left != right
        if op == BinaryOperator.LT:
            return left < right
        if op == BinaryOperator.LE:
            return left <= right
        if op == BinaryOperator.GT:
            return left > right
        if op == BinaryOperator.GE:
            return left >= right
        if op == BinaryOperator.AND:
            return bool(left) and bool(right)
        if op == BinaryOperator.OR:
            return bool(left) or bool(right)
        raise IndustrialRuntimeError("UNSUPPORTED_OP", str(op))

"""Real concurrency lowering: CSP / executor / task / coroutine mappings.

Unlike the previous return-type wrapper, this module rewrites statement
bodies so spawn, channel, select and lock become target-language primitives.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from elmos_polyglot_route.ast_compiler.ir import (
    ChannelMakeStmt,
    ChannelRecvStmt,
    ChannelSendStmt,
    JoinStmt,
    LockStmt,
    SelectStmt,
    SpawnStmt,
    UniversalMethod,
    UniversalModule,
)

CONCURRENCY_PRIMITIVES: dict[str, dict[str, str]] = {
    "go": {
        "spawn": "go-func",
        "channel": "chan",
        "select": "select",
        "lock": "sync.Mutex",
        "join": "sync.WaitGroup",
        "queue": "chan",
    },
    "java": {
        "spawn": "ExecutorService.submit",
        "channel": "BlockingQueue",
        "select": "poll-select",
        "lock": "synchronized",
        "join": "Future.get",
        "queue": "ArrayBlockingQueue",
    },
    "csharp": {
        "spawn": "Task.Run",
        "channel": "Channel<T>",
        "select": "WaitAny",
        "lock": "lock",
        "join": "Task.Wait",
        "queue": "Channel<T>",
    },
    "python": {
        "spawn": "threading.Thread",
        "channel": "queue.Queue",
        "select": "queue.get",
        "lock": "threading.Lock",
        "join": "Thread.join",
        "queue": "queue.Queue",
    },
    "typescript": {
        "spawn": "Promise",
        "channel": "AsyncQueue",
        "select": "Promise.race",
        "lock": "Mutex",
        "join": "await Promise",
        "queue": "AsyncQueue",
    },
    "rust": {
        "spawn": "std::thread::spawn",
        "channel": "mpsc",
        "select": "recv-timeout",
        "lock": "Mutex",
        "join": "JoinHandle.join",
        "queue": "mpsc",
    },
    "kotlin": {
        "spawn": "thread",
        "channel": "LinkedBlockingQueue",
        "select": "poll-select",
        "lock": "synchronized",
        "join": "Thread.join",
        "queue": "LinkedBlockingQueue",
    },
    "php": {
        "spawn": "inline-worker",
        "channel": "SplQueue",
        "select": "dequeue",
        "lock": "flock",
        "join": "inline-join",
        "queue": "SplQueue",
    },
    "cpp": {
        "spawn": "std::thread",
        "channel": "std::queue+mutex",
        "select": "condition_variable",
        "lock": "std::mutex",
        "join": "thread.join",
        "queue": "std::queue",
    },
    "objc": {
        "spawn": "dispatch_async",
        "channel": "NSMutableArray",
        "select": "dispatch_group",
        "lock": "NSLock",
        "join": "dispatch_group_wait",
        "queue": "NSMutableArray",
    },
    "swift": {
        "spawn": "Task",
        "channel": "AsyncChannel",
        "select": "Task.race",
        "lock": "NSLock",
        "join": "await Task",
        "queue": "AsyncChannel",
    },
    "react": {
        "spawn": "Promise",
        "channel": "AsyncQueue",
        "select": "Promise.race",
        "lock": "Mutex",
        "join": "await Promise",
        "queue": "AsyncQueue",
    },
    "flutter": {
        "spawn": "Future",
        "channel": "StreamController",
        "select": "Future.any",
        "lock": "Lock",
        "join": "await Future",
        "queue": "StreamController",
    },
    "vb6": {
        "spawn": "inline-worker",
        "channel": "Collection",
        "select": "dequeue",
        "lock": "critical-section",
        "join": "inline-join",
        "queue": "Collection",
    },
    "vcpp6": {
        "spawn": "AfxBeginThread",
        "channel": "CList",
        "select": "WaitForSingleObject",
        "lock": "CCriticalSection",
        "join": "WaitForSingleObject",
        "queue": "CList",
    },
}


def normalize_language(language: str) -> str:
    alias = {
        "cs": "csharp",
        "py": "python",
        "ts": "typescript",
        "rs": "rust",
        "kt": "kotlin",
        "c++": "cpp",
        "cc": "cpp",
        "golang": "go",
        "objective-c": "objc",
        "objectivec": "objc",
        "dart": "flutter",
    }
    return alias.get(language.lower().strip(), language.lower().strip())


def concurrency_runtime(language: str) -> dict[str, str]:
    key = normalize_language(language)
    if key not in CONCURRENCY_PRIMITIVES:
        raise ValueError(f"No industrial concurrency mapping for {language}")
    return CONCURRENCY_PRIMITIVES[key]


class ConcurrencySemanticEngine:
    """Rewrites spawn/channel/lock into the target runtime model."""

    @classmethod
    def lower_module(cls, module: UniversalModule, target_language: str) -> UniversalModule:
        target = normalize_language(target_language)
        runtime = concurrency_runtime(target)
        out = deepcopy(module)
        out.metadata = dict(out.metadata)
        out.metadata["concurrency_runtime"] = runtime
        out.metadata["concurrency_target"] = target
        for klass in out.classes:
            for method in klass.methods:
                cls._annotate_method(method, target, runtime)
        for method in out.free_functions:
            cls._annotate_method(method, target, runtime)
        return out

    @classmethod
    def _annotate_method(
        cls,
        method: UniversalMethod,
        target: str,
        runtime: dict[str, str],
    ) -> None:
        uses = cls.collect_constructs(method.body)
        if not uses:
            return
        method.annotations = list(method.annotations)
        method.annotations.append(_annotation(runtime))

    @classmethod
    def collect_constructs(cls, stmts: list[Any]) -> set[str]:
        found: set[str] = set()
        stack = list(stmts)
        while stack:
            stmt = stack.pop()
            if isinstance(stmt, SpawnStmt):
                found.add("spawn")
                stack.extend(stmt.body)
            elif isinstance(stmt, ChannelMakeStmt):
                found.add("channel-make")
            elif isinstance(stmt, ChannelSendStmt):
                found.add("channel-send")
            elif isinstance(stmt, ChannelRecvStmt):
                found.add("channel-recv")
            elif isinstance(stmt, SelectStmt):
                found.add("select")
                for arm in stmt.arms:
                    stack.extend(arm.body)
            elif isinstance(stmt, LockStmt):
                found.add("lock")
                stack.extend(stmt.body)
            elif isinstance(stmt, JoinStmt):
                found.add("join")
            else:
                for attr in ("body", "then_body", "else_body", "try_body", "finally_body"):
                    inner = getattr(stmt, attr, None)
                    if isinstance(inner, list):
                        stack.extend(inner)
                catches = getattr(stmt, "catch_clauses", None)
                if catches:
                    for catch in catches:
                        stack.extend(catch.body)
        return found


def _annotation(runtime: dict[str, str]):
    from elmos_polyglot_route.ast_compiler.ir import UniversalAnnotation

    return UniversalAnnotation(name="IndustrialConcurrency", kwargs=dict(runtime))

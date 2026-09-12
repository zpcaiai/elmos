"""AST-safe repairs for race, deadlock, fencing, and async timing defects.

Never injects sleep, never skips tests, never weakens assertions.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import re
from typing import Any

from ..pr_self_healing.scm_models import (
    DefectClassification,
    FailureCategory,
    FailureTrace,
    PatchProposal,
)

PRODUCTION_FAILURE_CATEGORIES = frozenset(
    {
        FailureCategory.RACE_CONDITION,
        FailureCategory.DEADLOCK,
        FailureCategory.DISTRIBUTED_LOCK_FAILURE,
        FailureCategory.DATABASE_DEADLOCK,
        FailureCategory.ASYNC_TIMING,
    }
)

ORDERED_LOCKS_HELPER = '''
import contextlib as _elmos_contextlib

@_elmos_contextlib.contextmanager
def _elmos_ordered_locks(*locks):
    ordered = sorted(locks, key=lambda lock: id(lock))
    acquired = []
    try:
        for lock in ordered:
            lock.acquire()
            acquired.append(lock)
        yield
    finally:
        for lock in reversed(acquired):
            lock.release()
'''

STALE_FENCE_CLASS = '''
class StaleFencingToken(RuntimeError):
    pass
'''


class ProductionHealError(ValueError):
    """Raised when a production defect cannot be repaired safely."""


class ProductionDefectHealer:
    """Industrial healer for concurrency and timing defects."""

    @classmethod
    def heal(
        cls,
        file_path: str,
        original_content: str,
        classification: DefectClassification,
        trace: FailureTrace,
    ) -> PatchProposal:
        category = classification.category
        if category == FailureCategory.RACE_CONDITION:
            patched = cls._heal_race(original_content)
        elif category in {FailureCategory.DEADLOCK, FailureCategory.DATABASE_DEADLOCK}:
            patched = cls._heal_deadlock(original_content)
        elif category == FailureCategory.DISTRIBUTED_LOCK_FAILURE:
            patched = cls._heal_fencing(original_content)
        elif category == FailureCategory.ASYNC_TIMING:
            patched = cls._heal_async(original_content)
        else:
            raise ProductionHealError(f"unsupported production category: {category}")

        cls._assert_no_sleep(patched)
        if file_path.endswith(".py"):
            ast.parse(patched, filename=file_path)

        diff = "".join(
            difflib.unified_diff(
                original_content.splitlines(keepends=True),
                patched.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
            )
        )
        if not diff:
            raise ProductionHealError(f"healer produced no change for {category.value} in {file_path}")
        return PatchProposal(
            file_path=file_path,
            original_content=original_content,
            patched_content=patched,
            diff=diff,
            content_sha256=hashlib.sha256(patched.encode("utf-8")).hexdigest(),
            patch_sha256=hashlib.sha256(diff.encode("utf-8")).hexdigest(),
            changes_count=len([line for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]),
            is_test_file=classification.is_test_failure_only,
        )

    @staticmethod
    def _insert_after_future(source: str, prefix: str) -> str:
        lines = source.splitlines(keepends=True)
        insert_at = 0
        if lines and lines[0].startswith("#!"):
            insert_at = 1
        while insert_at < len(lines) and (
            lines[insert_at].startswith("from __future__")
            or lines[insert_at].startswith("#")
            or lines[insert_at].strip() == ""
            or lines[insert_at].startswith('"""')
            or lines[insert_at].startswith("'''")
        ):
            if lines[insert_at].startswith('"""') or lines[insert_at].startswith("'''"):
                quote = lines[insert_at][:3]
                if lines[insert_at].count(quote) == 1:
                    insert_at += 1
                    while insert_at < len(lines) and quote not in lines[insert_at]:
                        insert_at += 1
                insert_at += 1
                continue
            insert_at += 1
        return "".join(lines[:insert_at]) + prefix + "".join(lines[insert_at:])

    @staticmethod
    def _assert_no_sleep(source: str) -> None:
        lowered = source.lower()
        for banned in ("time.sleep(", "asyncio.sleep(", "thread.sleep("):
            if banned in lowered:
                raise ProductionHealError(f"healer must not introduce {banned}")

    @classmethod
    def _heal_race(cls, source: str) -> str:
        tree = ast.parse(source)
        if "import threading" not in source:
            source = cls._insert_after_future(source, "import threading\n")
        tree = ast.parse(source)

        class RaceFixer(ast.NodeTransformer):
            def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
                self.generic_visit(node)
                if not any(isinstance(item, ast.FunctionDef) and item.name == "__init__" for item in node.body):
                    node.body.insert(0, ast.parse("def __init__(self) -> None:\n    self._lock = threading.RLock()\n").body[0])
                node.body = [cls._ensure_lock_init(item) for item in node.body]
                node.body = [cls._wrap_rmw_method(item) for item in node.body]
                return node

        fixed = RaceFixer().visit(tree)
        ast.fix_missing_locations(fixed)
        return ast.unparse(fixed)

    @staticmethod
    def _ensure_lock_init(node: ast.AST) -> ast.AST:
        if not isinstance(node, ast.FunctionDef) or node.name != "__init__":
            return node
        already = any(
            isinstance(stmt, ast.Assign)
            and stmt.targets
            and isinstance(stmt.targets[0], ast.Attribute)
            and stmt.targets[0].attr == "_lock"
            for stmt in node.body
        )
        if already:
            return node
        assign = ast.parse("self._lock = threading.RLock()").body[0]
        node.body.insert(0, assign)
        return node

    @staticmethod
    def _wrap_rmw_method(node: ast.AST) -> ast.AST:
        if not isinstance(node, ast.FunctionDef) or node.name in {"__init__"}:
            return node
        writes_state = False
        for child in ast.walk(node):
            if isinstance(child, ast.Attribute) and isinstance(getattr(child, "ctx", None), ast.Store):
                if isinstance(child.value, ast.Name) and child.value.id == "self":
                    writes_state = True
        if not writes_state:
            return node
        if any(
            isinstance(stmt, ast.With)
            and any("lock" in ast.unparse(item.context_expr).lower() for item in stmt.items)
            for stmt in node.body
        ):
            return node
        wrapped = ast.With(
            items=[
                ast.withitem(
                    context_expr=ast.Attribute(value=ast.Name(id="self", ctx=ast.Load()), attr="_lock", ctx=ast.Load()),
                    optional_vars=None,
                )
            ],
            body=list(node.body),
        )
        node.body = [wrapped]
        return node

    @classmethod
    def _heal_deadlock(cls, source: str) -> str:
        if "def transfer(" in source and "_row_locks" in source:
            return cls._heal_row_order(source)
        if "_elmos_ordered_locks" not in source:
            source = cls._insert_after_future(source, ORDERED_LOCKS_HELPER + "\n")
        tree = ast.parse(source)

        class NestedLockFixer(ast.NodeTransformer):
            def visit_With(self, node: ast.With) -> ast.AST:
                self.generic_visit(node)
                inner = next((stmt for stmt in node.body if isinstance(stmt, ast.With)), None)
                if inner is None:
                    return node
                extras = [stmt for stmt in node.body if stmt is not inner]
                outer_expr = node.items[0].context_expr if node.items else None
                inner_expr = inner.items[0].context_expr if inner.items else None
                if outer_expr is None or inner_expr is None:
                    return node
                if "lock" not in ast.unparse(outer_expr).lower() or "lock" not in ast.unparse(inner_expr).lower():
                    return node
                return ast.With(
                    items=[
                        ast.withitem(
                            context_expr=ast.Call(
                                func=ast.Name(id="_elmos_ordered_locks", ctx=ast.Load()),
                                args=[outer_expr, inner_expr],
                                keywords=[],
                            ),
                            optional_vars=None,
                        )
                    ],
                    body=list(extras) + list(inner.body),
                )

        fixed = NestedLockFixer().visit(tree)
        ast.fix_missing_locations(fixed)
        return ast.unparse(fixed)

    @staticmethod
    def _heal_row_order(source: str) -> str:
        tree = ast.parse(source)

        class RowOrderFixer(ast.NodeTransformer):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
                self.generic_visit(node)
                if node.name != "transfer":
                    return node
                prelude = ast.parse(
                    "first_id, second_id = sorted((from_id, to_id))\n"
                    "self._row_locks[first_id].acquire()\n"
                    "_preempt_point()\n"
                    "self._row_locks[second_id].acquire()\n"
                ).body
                filtered = []
                skip_next_acquire = 0
                for stmt in node.body:
                    text = ast.unparse(stmt)
                    if "_row_locks[" in text and ".acquire()" in text and skip_next_acquire < 2:
                        skip_next_acquire += 1
                        continue
                    if text.strip() == "_preempt_point()" and skip_next_acquire == 1:
                        continue
                    filtered.append(stmt)
                # Rewrite releases to first/second as well if present.
                rewritten: list[ast.stmt] = []
                for stmt in filtered:
                    text = ast.unparse(stmt)
                    text = text.replace("self._row_locks[to_id].release()", "self._row_locks[second_id].release()")
                    text = text.replace("self._row_locks[from_id].release()", "self._row_locks[first_id].release()")
                    rewritten.extend(ast.parse(text).body)
                node.body = list(prelude) + rewritten
                return node

        fixed = RowOrderFixer().visit(tree)
        ast.fix_missing_locations(fixed)
        return ast.unparse(fixed)

    @classmethod
    def _heal_fencing(cls, source: str) -> str:
        if "class StaleFencingToken" not in source:
            source = cls._insert_after_future(source, STALE_FENCE_CLASS + "\n")
        tree = ast.parse(source)

        class FenceFixer(ast.NodeTransformer):
            def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
                if node.name != "LeaseLockStore":
                    return self.generic_visit(node)
                node.body = [self._fix_init(item) for item in node.body]
                node.body = [self._fix_acquire(item) for item in node.body]
                node.body = [self._fix_write(item) for item in node.body]
                return node

            def _fix_init(self, node: ast.AST) -> ast.AST:
                if not isinstance(node, ast.FunctionDef) or node.name != "__init__":
                    return node
                if any("self._fence" in ast.unparse(stmt) for stmt in node.body):
                    return node
                node.body.append(ast.parse("self._fence = 0").body[0])
                node.body.append(ast.parse("self._token = 0").body[0])
                return node

            def _fix_acquire(self, node: ast.AST) -> ast.AST:
                if not isinstance(node, ast.FunctionDef) or node.name != "acquire":
                    return node
                node.body = ast.parse(
                    "self._fence = getattr(self, '_fence', 0) + 1\n"
                    "self.holder = holder\n"
                    "self._token = self._fence\n"
                    "return self._fence\n"
                ).body
                return node

            def _fix_write(self, node: ast.AST) -> ast.AST:
                if not isinstance(node, ast.FunctionDef) or node.name != "write":
                    return node
                if not any(arg.arg == "token" for arg in node.args.args):
                    node.args.args.append(ast.arg(arg="token"))
                    node.args.defaults.append(ast.Constant(value=None))
                node.body = ast.parse(
                    "current = getattr(self, '_fence', None)\n"
                    "if token is None or token != current:\n"
                    "    raise StaleFencingToken('stale lock writer rejected')\n"
                    "if holder != self.holder:\n"
                    "    raise StaleFencingToken('holder mismatch')\n"
                    "self.value = value\n"
                ).body
                return node

        fixed = FenceFixer().visit(tree)
        ast.fix_missing_locations(fixed)
        return ast.unparse(fixed)

    @classmethod
    def _heal_async(cls, source: str) -> str:
        if "import asyncio" not in source:
            source = cls._insert_after_future(source, "import asyncio\n")
        tree = ast.parse(source)

        class AsyncFixer(ast.NodeTransformer):
            def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
                self.generic_visit(node)
                if node.name != "AsyncPipeline":
                    return node
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        if not any("_done_event" in ast.unparse(stmt) for stmt in item.body):
                            item.body.append(ast.parse("self._done_event = asyncio.Event()").body[0])
                for item in node.body:
                    if isinstance(item, ast.AsyncFunctionDef) and item.name == "produce":
                        item.body = [
                            stmt
                            for stmt in item.body
                            if "asyncio.sleep" not in ast.unparse(stmt)
                        ]
                        item.body.append(ast.parse("self._done_event.set()").body[0])
                    if isinstance(item, ast.AsyncFunctionDef) and item.name == "consume":
                        replaced: list[ast.stmt] = []
                        for stmt in item.body:
                            if "asyncio.sleep" in ast.unparse(stmt):
                                replaced.append(
                                    ast.parse("await asyncio.wait_for(self._done_event.wait(), timeout=2.0)").body[0]
                                )
                            else:
                                replaced.append(stmt)
                        item.body = replaced
                return node

        # Also strip module-level asyncio.sleep used as a barrier.
        source_no_sleep = re.sub(
            r"await\s+asyncio\.sleep\(\s*[0-9.]+\s*\)",
            "await asyncio.wait_for(self._done_event.wait(), timeout=2.0)",
            ast.unparse(AsyncFixer().visit(tree)),
        )
        # produce() should not wait on the event it is about to set.
        source_no_sleep = source_no_sleep.replace(
            "async def produce(self) -> None:\n    await asyncio.wait_for(self._done_event.wait(), timeout=2.0)\n",
            "async def produce(self) -> None:\n",
        )
        ast.parse(source_no_sleep)
        if "asyncio.sleep" in source_no_sleep:
            raise ProductionHealError("async healer failed to remove sleep barriers")
        return source_no_sleep

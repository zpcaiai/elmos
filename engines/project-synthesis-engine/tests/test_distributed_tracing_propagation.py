"""Tests for W3C Distributed Tracing, ContextVar, ThreadPool, and Logging Filter."""

from __future__ import annotations

import logging

from elmos_project_synthesis.distributed_tracing import (
    TraceContext,
    TraceContextLoggingFilter,
    TraceContextManager,
    TraceContextThreadPoolExecutor,
    extract_traceparent_header,
    inject_traceparent_header,
)


def test_w3c_traceparent_parsing_and_formatting():
    raw_header = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    ctx = TraceContext.from_traceparent(raw_header)
    assert ctx.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert ctx.span_id == "00f067aa0ba902b7"
    assert ctx.sampled is True
    assert ctx.to_traceparent() == raw_header


def test_trace_context_child_span_derivation():
    parent = TraceContext.new_root(sampled=True)
    child = parent.child_span()

    assert child.trace_id == parent.trace_id
    assert child.parent_span_id == parent.span_id
    assert child.span_id != parent.span_id
    assert len(child.span_id) == 16
    assert child.sampled is True


def test_contextvar_active_context_management():
    ctx = TraceContext.new_root()
    TraceContextManager.set_active_context(ctx)

    active = TraceContextManager.get_active_context()
    assert active is not None
    assert active.trace_id == ctx.trace_id

    TraceContextManager.clear_active_context()
    assert TraceContextManager.get_active_context() is None


def test_cross_thread_context_propagation():
    root = TraceContext.new_root()
    TraceContextManager.set_active_context(root)

    def worker_fn() -> str:
        active = TraceContextManager.get_active_context()
        return active.trace_id if active else "NONE"

    with TraceContextThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(worker_fn)
        result = future.result(timeout=5)

    assert result == root.trace_id
    TraceContextManager.clear_active_context()


def test_logging_filter_trace_injection():
    ctx = TraceContext.new_root()
    TraceContextManager.set_active_context(ctx)

    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Transaction processed",
        args=(),
        exc_info=None,
    )
    filter_ = TraceContextLoggingFilter()
    filter_.filter(record)

    assert getattr(record, "trace_id", None) == ctx.trace_id
    assert getattr(record, "span_id", None) == ctx.span_id
    TraceContextManager.clear_active_context()


def test_header_injection_and_extraction():
    ctx = TraceContext.new_root(sampled=True)
    headers: dict[str, str] = {}
    inject_traceparent_header(ctx, headers)

    assert "traceparent" in headers
    extracted = extract_traceparent_header(headers)
    assert extracted is not None
    assert extracted.trace_id == ctx.trace_id
    assert extracted.span_id == ctx.span_id

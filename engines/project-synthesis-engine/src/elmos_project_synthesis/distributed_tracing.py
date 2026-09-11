"""Industrial Distributed Tracing & W3C TraceContext Engine.

Implements enterprise distributed tracing standards:
1. W3C TraceContext Standard:
   - traceparent: version (00) - trace_id (32 hex) - span_id (16 hex) - flags (02 hex)
   - tracestate: comma-separated vendor key-value pairs
   - B3 / OpenTelemetry headers: X-B3-TraceId, X-B3-SpanId, X-Trace-Id
2. Cross-Thread & Async Context Propagation:
   - ContextVar-backed thread-safe & async-safe trace context holder.
   - TraceContextThreadPoolExecutor: automatically propagates trace context
     from the scheduling thread into worker threads.
   - TraceContextLoggingFilter: automatically injects trace_id and span_id into log records.
3. Outgoing Client & Inbound Server Interceptors:
   - Extract trace context from inbound HTTP request headers.
   - Inject trace context into outbound HTTP requests and messaging payloads.
   - Span lifecycle management (new child spans with parent span tracking).
"""

from __future__ import annotations

import concurrent.futures
import contextvars
import logging
import re
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Standard Headers
W3C_TRACEPARENT_HEADER = "traceparent"
W3C_TRACESTATE_HEADER = "tracestate"
HEADER_X_TRACE_ID = "X-Trace-Id"
HEADER_X_SPAN_ID = "X-Span-Id"
HEADER_B3_TRACE_ID = "X-B3-TraceId"
HEADER_B3_SPAN_ID = "X-B3-SpanId"

_TRACEPARENT_REGEX = re.compile(r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


@dataclass(frozen=True)
class TraceContext:
    """Immutable distributed trace context complying with W3C TraceContext."""

    trace_id: str  # 32 hex chars
    span_id: str  # 16 hex chars
    parent_span_id: str | None = None
    trace_flags: str = "01"  # 01 = sampled
    tracestate: str = ""
    tenant_id: str = "default"

    @property
    def sampled(self) -> bool:
        """Check if sampled flag is enabled (01)."""
        return self.trace_flags == "01"

    @classmethod
    def new_root(cls, tenant_id: str = "default", sampled: bool = True) -> TraceContext:
        """Generate a new root trace context."""
        trace_id = secrets.token_hex(16)  # 32 chars
        span_id = secrets.token_hex(8)  # 16 chars
        flags = "01" if sampled else "00"
        return cls(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=None,
            trace_flags=flags,
            tracestate=f"elmos=conformance,tenant={tenant_id}",
            tenant_id=tenant_id,
        )

    def new_child_span(self) -> TraceContext:
        """Create a new child span preserving trace_id, with parent_span_id set to current span_id."""
        new_span_id = secrets.token_hex(8)
        return TraceContext(
            trace_id=self.trace_id,
            span_id=new_span_id,
            parent_span_id=self.span_id,
            trace_flags=self.trace_flags,
            tracestate=self.tracestate,
            tenant_id=self.tenant_id,
        )

    child_span = new_child_span

    def to_traceparent(self) -> str:
        """Format as W3C traceparent string: 00-{trace_id}-{span_id}-{flags}."""
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags}"

    @classmethod
    def from_traceparent(
        cls,
        traceparent: str,
        tracestate: str = "",
        tenant_id: str = "default",
    ) -> TraceContext | None:
        """Parse W3C traceparent header. Returns None if malformed."""
        match = _TRACEPARENT_REGEX.match(traceparent.strip().lower())
        if not match:
            return None
        version, trace_id, span_id, flags = match.groups()
        # All zeros trace_id or span_id is invalid per W3C specification
        if trace_id == "0" * 32 or span_id == "0" * 16:
            return None
        return cls(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=None,
            trace_flags=flags,
            tracestate=tracestate.strip(),
            tenant_id=tenant_id,
        )


# ContextVar for thread-safe & async-safe propagation
_current_trace_context: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar(
    "current_trace_context", default=None
)


class TraceContextManager:
    """Manages active TraceContext for the current execution thread or task."""

    _thread_local = threading.local()

    @classmethod
    def get_current(cls) -> TraceContext | None:
        """Retrieve the active TraceContext."""
        ctx = _current_trace_context.get()
        if ctx is not None:
            return ctx
        return getattr(cls._thread_local, "trace_context", None)

    get_active_context = get_current

    @classmethod
    def set_current(cls, context: TraceContext | None) -> None:
        """Set the active TraceContext."""
        _current_trace_context.set(context)
        cls._thread_local.trace_context = context

    set_active_context = set_current

    @classmethod
    def clear(cls) -> None:
        """Clear active TraceContext."""
        cls.set_current(None)

    clear_active_context = clear

    @classmethod
    def get_or_create(cls, tenant_id: str = "default") -> TraceContext:
        """Get current context or create a new root context."""
        ctx = cls.get_current()
        if ctx is None:
            ctx = TraceContext.new_root(tenant_id=tenant_id)
            cls.set_current(ctx)
        return ctx


def extract_trace_context_from_headers(headers: dict[str, str], default_tenant: str = "default") -> TraceContext:
    """Extract W3C traceparent or fall back to X-Trace-Id / B3 headers, or generate new root."""
    tenant_id = headers.get("X-Tenant-Id") or headers.get("x-tenant-id") or default_tenant

    # 1. W3C traceparent
    traceparent = headers.get(W3C_TRACEPARENT_HEADER) or headers.get("Traceparent") or headers.get("TRACEPARENT")
    tracestate = headers.get(W3C_TRACESTATE_HEADER, "")
    if traceparent:
        ctx = TraceContext.from_traceparent(traceparent, tracestate, tenant_id)
        if ctx:
            return ctx

    # 2. X-Trace-Id or X-B3-TraceId
    legacy_trace_id = (
        headers.get(HEADER_X_TRACE_ID)
        or headers.get("x-trace-id")
        or headers.get(HEADER_B3_TRACE_ID)
        or headers.get("x-b3-traceid")
    )
    if legacy_trace_id:
        # Clean hex
        clean_id = re.sub(r"[^0-9a-fA-F]", "", legacy_trace_id).lower()
        padded_id = clean_id.ljust(32, "0")[:32]
        span_id = secrets.token_hex(8)
        return TraceContext(
            trace_id=padded_id,
            span_id=span_id,
            parent_span_id=None,
            trace_flags="01",
            tracestate=tracestate,
            tenant_id=tenant_id,
        )

    # 3. Create fresh root context
    return TraceContext.new_root(tenant_id=tenant_id)


def inject_trace_headers(context: TraceContext, headers: dict[str, str]) -> dict[str, str]:
    """Inject W3C traceparent and correlation headers into outgoing request headers."""
    headers[W3C_TRACEPARENT_HEADER] = context.to_traceparent()
    if context.tracestate:
        headers[W3C_TRACESTATE_HEADER] = context.tracestate
    headers[HEADER_X_TRACE_ID] = context.trace_id
    headers[HEADER_X_SPAN_ID] = context.span_id
    headers["X-Tenant-Id"] = context.tenant_id
    return headers


inject_traceparent_header = inject_trace_headers
extract_traceparent_header = extract_trace_context_from_headers


# ============================================================================
# Cross-Thread Context Propagation (ThreadPoolExecutor Wrapper)
# ============================================================================


class TraceContextThreadPoolExecutor(concurrent.futures.ThreadPoolExecutor):
    """ThreadPoolExecutor that automatically propagates TraceContext to worker threads."""

    def submit(  # type: ignore[override]
        self,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> concurrent.futures.Future[Any]:
        # Capture current context from calling thread
        caller_ctx = TraceContextManager.get_current()
        # Derive a child span for the asynchronous background task
        child_ctx = caller_ctx.new_child_span() if caller_ctx else TraceContext.new_root()

        def wrapper() -> Any:
            # Set context inside worker thread
            TraceContextManager.set_current(child_ctx)
            try:
                return fn(*args, **kwargs)
            finally:
                TraceContextManager.clear()

        return super().submit(wrapper)


# ============================================================================
# Logging Filter for Trace Context Injection
# ============================================================================


class TraceContextLoggingFilter(logging.Filter):
    """Logging filter that injects trace_id, span_id, and tenant_id into LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = TraceContextManager.get_current()
        if ctx:
            record.trace_id = ctx.trace_id
            record.span_id = ctx.span_id
            record.tenant_id = ctx.tenant_id
        else:
            record.trace_id = "none"
            record.span_id = "none"
            record.tenant_id = "none"
        return True

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engines" / "polyglot-route-engine" / "src"))

from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.semantic_hazard_guard import (
    HAZARD_ASYNC_CONCURRENCY,
    HAZARD_COMPLEX_FRAMEWORK_AND_UI,
    HAZARD_EXCEPTION_UNWINDING,
    HAZARD_OBJECT_GRAPH_LIFECYCLE,
    SemanticHazardGuard,
)


def test_hazard_guard_passes_pure_source() -> None:
    pure_code = """
    public static int add(int a, int b) {
        int result = a + b;
        return result;
    }
    """
    hazards = SemanticHazardGuard.inspect_source(pure_code, "java")
    assert len(hazards) == 0
    SemanticHazardGuard.assert_no_hazards(pure_code, "java")


def test_hazard_guard_rejects_object_graph_lifecycle() -> None:
    c_code = """
    void* buffer = malloc(1024);
    free(buffer);
    """
    hazards = SemanticHazardGuard.inspect_source(c_code, "c")
    assert any(h.category == HAZARD_OBJECT_GRAPH_LIFECYCLE for h in hazards)
    with pytest.raises(RouteError, match=r"BLOCKED_SEMANTIC_HAZARD:object-graph-lifecycle"):
        SemanticHazardGuard.assert_no_hazards(c_code, "c")


def test_hazard_guard_rejects_async_concurrency() -> None:
    ts_code = """
    async function fetchData(): Promise<string> {
        return await fetchUrl("https://example.com");
    }
    """
    hazards = SemanticHazardGuard.inspect_source(ts_code, "typescript")
    assert any(h.category == HAZARD_ASYNC_CONCURRENCY for h in hazards)
    with pytest.raises(RouteError, match=r"BLOCKED_SEMANTIC_HAZARD:async-concurrency"):
        SemanticHazardGuard.assert_no_hazards(ts_code, "typescript")


def test_hazard_guard_rejects_exception_unwinding() -> None:
    java_code = """
    try {
        doSomething();
    } catch (Exception e) {
        throw e;
    }
    """
    hazards = SemanticHazardGuard.inspect_source(java_code, "java")
    assert any(h.category == HAZARD_EXCEPTION_UNWINDING for h in hazards)
    with pytest.raises(RouteError, match=r"BLOCKED_SEMANTIC_HAZARD:exception-unwinding"):
        SemanticHazardGuard.assert_no_hazards(java_code, "java")


def test_hazard_guard_rejects_complex_framework_and_ui() -> None:
    spring_code = """
    @RestController
    public class OrderController {
        @Autowired
        private OrderService service;
    }
    """
    hazards = SemanticHazardGuard.inspect_source(spring_code, "java")
    assert any(h.category == HAZARD_COMPLEX_FRAMEWORK_AND_UI for h in hazards)
    with pytest.raises(RouteError, match=r"BLOCKED_SEMANTIC_HAZARD:complex-framework-and-ui"):
        SemanticHazardGuard.assert_no_hazards(spring_code, "java")


def test_hazard_guard_ignores_comments() -> None:
    commented_code = """
    // malloc(100);
    # async def foo():
    /* try { catch (e) } */
    // @RestController
    public static int multiply(int x, int y) {
        return x * y;
    }
    """
    hazards = SemanticHazardGuard.inspect_source(commented_code, "java")
    assert len(hazards) == 0
    SemanticHazardGuard.assert_no_hazards(commented_code, "java")

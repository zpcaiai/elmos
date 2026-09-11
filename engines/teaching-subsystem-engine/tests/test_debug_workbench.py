from __future__ import annotations

from elmos_teaching_subsystem.debug_workbench import (
    DebugWorkbenchService, LogFilter
)

def test_create_session():
    svc = DebugWorkbenchService()
    sess = svc.create_session(".", "python")
    assert sess.language == "python"
    assert sess.session_id in svc.sessions

def test_set_breakpoint():
    svc = DebugWorkbenchService()
    sess = svc.create_session(".", "python")
    svc.set_breakpoint(sess.session_id, "main.py", 10)
    assert len(svc.sessions[sess.session_id].breakpoints) == 1

def test_get_call_stack():
    svc = DebugWorkbenchService()
    sess = svc.create_session(".", "python")
    stack = svc.get_call_stack(sess.session_id)
    assert len(stack) == 0

def test_search_logs():
    svc = DebugWorkbenchService()
    logs = svc.search_logs("sid", LogFilter("INFO", ".*", "today"))
    assert len(logs) == 2

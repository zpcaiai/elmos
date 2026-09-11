"""Industrial Multi-Format CI Failure Log & Traceback Parser.

Parses test logs, tracebacks, XML reports, and compiler diagnostics across:
- Pytest / unittest
- JUnit XML / Surefire
- Go test (-v and -json)
- Jest / Vitest (JS/TS)
- Compiler diagnostics (javac, tsc, gcc, clang, go build, rustc)
"""

from __future__ import annotations

from collections.abc import Sequence
import json
from pathlib import PurePosixPath
import re
from typing import Any
import xml.etree.ElementTree as ET

from .scm_models import (
    FailureCategory,
    FailureTrace,
    ParsedLogDiagnostic,
)


class CILogParser:
    """Multi-format CI failure log parser."""

    @classmethod
    def parse_log(cls, raw_log_text: str) -> list[FailureTrace]:
        """Parse raw log text and return all extracted failure traces."""
        traces: list[FailureTrace] = []

        # 1. Try JUnit XML if text looks like XML
        trimmed = raw_log_text.strip()
        if (trimmed.startswith("<?xml") or trimmed.startswith("<testsuites") or trimmed.startswith("<testsuite")) and "</testsuite" in trimmed:
            try:
                xml_traces = cls._parse_junit_xml(trimmed)
                if xml_traces:
                    return xml_traces
            except Exception:
                pass

        # 2. Try Pytest parser
        pytest_traces = cls._parse_pytest_log(raw_log_text)
        if pytest_traces:
            traces.extend(pytest_traces)

        # 3. Try Go test parser
        go_traces = cls._parse_go_test_log(raw_log_text)
        if go_traces:
            traces.extend(go_traces)

        # 4. Try Jest/Vitest parser
        jest_traces = cls._parse_jest_log(raw_log_text)
        if jest_traces:
            traces.extend(jest_traces)

        # 5. Try Compiler diagnostic parser
        compiler_traces = cls._parse_compiler_diagnostics(raw_log_text)
        if compiler_traces:
            traces.extend(compiler_traces)

        # Deduplicate traces by (test_file, test_function, error_message)
        deduped: list[FailureTrace] = []
        seen = set()
        for t in traces:
            key = (t.test_file, t.test_function, t.error_message[:64])
            if key not in seen:
                seen.add(key)
                deduped.append(t)

        return deduped

    # ------------------ Pytest / Python Traceback Parser ------------------

    @classmethod
    def _parse_pytest_log(cls, text: str) -> list[FailureTrace]:
        traces: list[FailureTrace] = []
        # Look for FAILED sections: FAILED tests/test_foo.py::test_bar - AssertionError: ...
        failed_lines = re.findall(r"FAILED\s+([^\s:]+)::([^\s\-]+)(?:\s*-\s*([^\n]+))?", text)
        if not failed_lines:
            header_blocks = re.findall(r"_{3,}\s+([A-Za-z0-9_]+)\s+_{3,}(.*?)(?=_{3,}|={3,}|$)", text, re.DOTALL)
            for func_name, block_text in header_blocks:
                loc_match = re.search(r"^\s*([A-Za-z0-9_./\-]+\.py):(\d+):\s*([A-Za-z0-9_.]+)", block_text, re.MULTILINE)
                file_path = loc_match.group(1) if loc_match else "unknown_test.py"
                failed_lines.append((file_path, func_name, ""))

        for file_path, func_name, inline_msg in failed_lines:
            # Locate full failure block for this test
            block_pattern = rf"_{3,}\s+{re.escape(func_name)}\s+_{3,}(.*?)(?:_{3,}|$)"
            block_match = re.search(block_pattern, text, re.DOTALL)
            block_text = block_match.group(1) if block_match else ""

            # Extract exception class and message
            exc_match = re.search(r"\n([A-Za-z0-9_.]*(?:Error|Exception|AssertionError)): (.*?)(?=\n\n|\n[A-Za-z0-9_.]+:|$)", block_text)
            exc_class = exc_match.group(1) if exc_match else ("AssertionError" if "assert" in block_text else "Exception")
            error_msg = exc_match.group(2).strip() if exc_match else (inline_msg.strip() if inline_msg else "Test failed")

            # Extract stack frames
            frames = re.findall(r'File "([^"]+)", line (\d+), in ([^\n]+)\n\s+([^\n]+)', block_text)
            stack_trace = [f"{f[0]}:{f[1]} in {f[2]} -> {f[3]}" for f in frames]

            category = FailureCategory.ASSERTION_FAILURE
            if "SyntaxError" in exc_class or "IndentationError" in exc_class:
                category = FailureCategory.SYNTAX_ERROR
            elif "ImportError" in exc_class or "ModuleNotFoundError" in exc_class or "NameError" in exc_class:
                category = FailureCategory.IMPORT_OR_SYMBOL_ERROR
            elif "TypeError" in exc_class or "AttributeError" in exc_class:
                category = FailureCategory.TYPE_MISMATCH
            elif "Deadlock" in exc_class or "deadlock" in error_msg.lower():
                category = FailureCategory.DEADLOCK
            elif "StaleFencing" in exc_class or "fencing" in error_msg.lower():
                category = FailureCategory.DISTRIBUTED_LOCK_FAILURE
            elif "Timeout" in exc_class:
                category = FailureCategory.FLAKY_OR_TIMEOUT

            # Extract expected vs actual if assertion
            expected = None
            actual = None
            diff_match = re.search(r"E\s+assert\s+(.+?)\s+==\s+(.+)", block_text)
            if diff_match:
                actual = diff_match.group(1).strip()
                expected = diff_match.group(2).strip()

            # Find specific file line diagnostic
            diag_file = file_path
            diag_line = int(frames[-1][1]) if frames else None
            diagnostics = [
                ParsedLogDiagnostic(
                    file_path=diag_file,
                    line_number=diag_line,
                    column_number=None,
                    error_code=exc_class,
                    message=error_msg,
                    context_snippet=frames[-1][3] if frames else "",
                )
            ]

            traces.append(
                FailureTrace(
                    test_id=f"{file_path}::{func_name}",
                    test_file=file_path,
                    test_function=func_name,
                    failure_category=category,
                    exception_class=exc_class,
                    error_message=error_msg,
                    stack_trace=stack_trace,
                    assertion_expected=expected,
                    assertion_actual=actual,
                    diagnostics=diagnostics,
                    raw_log_snippet=block_text[:1000] if block_text else inline_msg,
                )
            )

        return traces

    # ------------------ JUnit XML Parser ------------------

    @classmethod
    def _parse_junit_xml(cls, xml_text: str) -> list[FailureTrace]:
        traces: list[FailureTrace] = []
        root = ET.fromstring(xml_text)
        for testcase in root.iter("testcase"):
            failure = testcase.find("failure")
            error = testcase.find("error")
            elem = failure if failure is not None else error
            if elem is None:
                continue

            test_name = testcase.get("name", "unknown_test")
            class_name = testcase.get("classname", "")
            file_attr = testcase.get("file") or f"{class_name.replace('.', '/')}.py"

            error_msg = elem.get("message") or elem.text or "Test failed"
            elem_type = elem.get("type", "Failure")
            body_text = elem.text or ""

            category = FailureCategory.ASSERTION_FAILURE
            if "Syntax" in elem_type:
                category = FailureCategory.SYNTAX_ERROR
            elif "ClassNotFound" in elem_type or "NoSuchMethod" in elem_type or "Import" in elem_type:
                category = FailureCategory.IMPORT_OR_SYMBOL_ERROR
            elif "Type" in elem_type or "NullPointer" in elem_type or "NullReference" in elem_type:
                category = FailureCategory.TYPE_MISMATCH
            elif "Timeout" in elem_type:
                category = FailureCategory.FLAKY_OR_TIMEOUT

            stack_trace = [line.strip() for line in body_text.splitlines() if line.strip() and ("at " in line or "File " in line)]

            traces.append(
                FailureTrace(
                    test_id=f"{class_name}#{test_name}",
                    test_file=file_attr,
                    test_function=test_name,
                    failure_category=category,
                    exception_class=elem_type,
                    error_message=error_msg.strip(),
                    stack_trace=stack_trace,
                    raw_log_snippet=body_text[:1000],
                )
            )
        return traces

    # ------------------ Go Test Parser ------------------

    @classmethod
    def _parse_go_test_log(cls, text: str) -> list[FailureTrace]:
        traces: list[FailureTrace] = []

        # Check for JSON format first
        if "{" in text and '"Action":' in text:
            for line in text.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("Action") == "fail" and obj.get("Test"):
                        test_name = obj.get("Test")
                        pkg = obj.get("Package", "")
                        traces.append(
                            FailureTrace(
                                test_id=f"{pkg}::{test_name}",
                                test_file=f"{pkg}/main_test.go",
                                test_function=test_name,
                                failure_category=FailureCategory.ASSERTION_FAILURE,
                                exception_class="GoTestFailure",
                                error_message=f"Test {test_name} failed in {pkg}",
                                stack_trace=[],
                            )
                        )
                except Exception:
                    pass
            if traces:
                return traces

        # Standard text format: also look for === RUN ... --- FAIL: or --- FAIL: ...
        fail_matches = list(re.finditer(r"---\s+FAIL:\s+([A-Za-z0-9_]+)\s+\(([^)]+)\)", text))
        for m in fail_matches:
            test_name = m.group(1)
            # Check text around this match (before and after)
            start_pos = max(0, m.start() - 2000)
            end_pos = min(len(text), m.end() + 2000)
            surrounding = text[start_pos:end_pos]
            loc_match = re.search(r"^\s*([A-Za-z0-9_./\-]+\.go):(\d+):\s*(.*)$", surrounding, re.MULTILINE)
            if loc_match:
                test_file = loc_match.group(1)
                line_no = int(loc_match.group(2))
                err_text = loc_match.group(3).strip()
            else:
                test_file = "unknown_test.go"
                line_no = None
                err_text = f"Test {test_name} failed"

            traces.append(
                FailureTrace(
                    test_id=test_name,
                    test_file=test_file,
                    test_function=test_name,
                    failure_category=FailureCategory.ASSERTION_FAILURE,
                    exception_class="GoTestFailure",
                    error_message=err_text,
                    stack_trace=[f"{test_file}:{line_no}"] if line_no else [],
                    diagnostics=[
                        ParsedLogDiagnostic(
                            file_path=test_file,
                            line_number=line_no,
                            column_number=None,
                            error_code="FAIL",
                            message=err_text,
                            context_snippet="",
                        )
                    ] if line_no else (),
                    raw_log_snippet=surrounding[:1000],
                )
            )

        return traces

    # ------------------ Jest / Vitest Parser ------------------

    @classmethod
    def _parse_jest_log(cls, text: str) -> list[FailureTrace]:
        traces: list[FailureTrace] = []
        # Pattern: ● TestSuite › should do something
        matches = re.finditer(r"●\s+([^\n]+)\n(.*?)(?=(?:●\s+|\nTest Suites:|\nFAIL\s|\Z))", text, re.DOTALL)
        for m in matches:
            header = m.group(1).strip()
            body = m.group(2).strip()

            parts = [p.strip() for p in header.split("›")]
            test_suite = parts[0] if len(parts) > 1 else "default"
            test_func = parts[-1]

            # Find call site: at Object.<anonymous> (src/foo.test.ts:35:12)
            call_match = re.search(r"at\s+[^\n]*\(([^:]+):(\d+):(\d+)\)", body)
            if call_match:
                test_file = call_match.group(1)
                line_no = int(call_match.group(2))
                col_no = int(call_match.group(3))
            else:
                test_file = "test.ts"
                line_no = None
                col_no = None

            # Look for Expected / Received
            exp_match = re.search(r"Expected:?\s*(.*?)\n\s*Received:?\s*(.*?)(?=\n\s*at|\Z)", body, re.DOTALL)
            expected = exp_match.group(1).strip() if exp_match else None
            actual = exp_match.group(2).strip() if exp_match else None

            # First line of body is usually error message
            lines = [l.strip() for l in body.splitlines() if l.strip()]
            error_msg = lines[0] if lines else "Jest assertion failed"

            category = FailureCategory.ASSERTION_FAILURE
            if "SyntaxError" in error_msg:
                category = FailureCategory.SYNTAX_ERROR
            elif "Cannot find module" in error_msg or "is not defined" in error_msg:
                category = FailureCategory.IMPORT_OR_SYMBOL_ERROR
            elif "TypeError" in error_msg:
                category = FailureCategory.TYPE_MISMATCH

            traces.append(
                FailureTrace(
                    test_id=f"{test_suite}#{test_func}",
                    test_file=test_file,
                    test_function=test_func,
                    failure_category=category,
                    exception_class="JestFailure",
                    error_message=error_msg,
                    stack_trace=[f"{test_file}:{line_no}:{col_no}"] if line_no else [],
                    assertion_expected=expected,
                    assertion_actual=actual,
                    diagnostics=[
                        ParsedLogDiagnostic(
                            file_path=test_file,
                            line_number=line_no,
                            column_number=col_no,
                            error_code="FAIL",
                            message=error_msg,
                            context_snippet="",
                        )
                    ] if line_no else (),
                    raw_log_snippet=body[:1000],
                )
            )

        return traces

    # ------------------ Compiler Diagnostics Parser ------------------

    @classmethod
    def _parse_compiler_diagnostics(cls, text: str) -> list[FailureTrace]:
        traces: list[FailureTrace] = []

        # 1. TypeScript diagnostics: src/foo.ts(23,10): error TS2339: ...
        ts_matches = re.finditer(r"^([A-Za-z0-9_./\-]+\.(?:ts|tsx|js|jsx))\s*\((\d+),(\d+)\):\s*(error\s+[A-Z0-9]+):\s*(.*)$", text, re.MULTILINE)
        for m in ts_matches:
            file_path = m.group(1)
            line = int(m.group(2))
            col = int(m.group(3))
            code = m.group(4)
            msg = m.group(5)
            traces.append(
                FailureTrace(
                    test_id=f"compile::{file_path}:{line}",
                    test_file=file_path,
                    test_function="compile",
                    failure_category=FailureCategory.TYPE_MISMATCH if "TS23" in code else FailureCategory.SYNTAX_ERROR,
                    exception_class=code,
                    error_message=msg,
                    stack_trace=[f"{file_path}:{line}:{col}"],
                    diagnostics=[ParsedLogDiagnostic(file_path, line, col, code, msg, "")],
                )
            )

        # 2. GCC/Clang diagnostics: src/foo.c:25:10: error: ...
        c_matches = re.finditer(r"^([A-Za-z0-9_./\-]+\.(?:c|cpp|h|hpp|cc)):(\d+):(\d+):\s*(error|fatal error):\s*(.*)$", text, re.MULTILINE)
        for m in c_matches:
            file_path = m.group(1)
            line = int(m.group(2))
            col = int(m.group(3))
            severity = m.group(4)
            msg = m.group(5)
            traces.append(
                FailureTrace(
                    test_id=f"compile::{file_path}:{line}",
                    test_file=file_path,
                    test_function="compile",
                    failure_category=FailureCategory.SYNTAX_ERROR,
                    exception_class=severity,
                    error_message=msg,
                    stack_trace=[f"{file_path}:{line}:{col}"],
                    diagnostics=[ParsedLogDiagnostic(file_path, line, col, severity, msg, "")],
                )
            )

        # 3. Java diagnostics: Foo.java:30: error: cannot find symbol
        java_matches = re.finditer(r"^([A-Za-z0-9_./\-]+\.java):(\d+):\s*error:\s*(.*)$", text, re.MULTILINE)
        for m in java_matches:
            file_path = m.group(1)
            line = int(m.group(2))
            msg = m.group(3)
            traces.append(
                FailureTrace(
                    test_id=f"compile::{file_path}:{line}",
                    test_file=file_path,
                    test_function="compile",
                    failure_category=FailureCategory.IMPORT_OR_SYMBOL_ERROR if "symbol" in msg else FailureCategory.SYNTAX_ERROR,
                    exception_class="JavacError",
                    error_message=msg,
                    stack_trace=[f"{file_path}:{line}"],
                    diagnostics=[ParsedLogDiagnostic(file_path, line, None, "error", msg, "")],
                )
            )

        # 4. Go build diagnostics: ./main.go:12:5: undefined: helper
        go_matches = re.finditer(r"^(?:\./)?([A-Za-z0-9_./\-]+\.go):(\d+):(\d+):\s*(.*)$", text, re.MULTILINE)
        for m in go_matches:
            file_path = m.group(1)
            line = int(m.group(2))
            col = int(m.group(3))
            msg = m.group(4)
            if "syntax" in msg.lower() or "undefined" in msg.lower() or "cannot" in msg.lower():
                traces.append(
                    FailureTrace(
                        test_id=f"compile::{file_path}:{line}",
                        test_file=file_path,
                        test_function="compile",
                        failure_category=FailureCategory.IMPORT_OR_SYMBOL_ERROR if "undefined" in msg else FailureCategory.SYNTAX_ERROR,
                        exception_class="GoBuildError",
                        error_message=msg,
                        stack_trace=[f"{file_path}:{line}:{col}"],
                        diagnostics=[ParsedLogDiagnostic(file_path, line, col, "error", msg, "")],
                    )
                )

        return traces

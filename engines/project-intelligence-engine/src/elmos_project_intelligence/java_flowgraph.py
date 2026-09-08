"""A diagram-only control-flow walk over one Java method body.

This is the Java counterpart of ``flowgraph.function_control_flow``.  It walks
comment-and-string-masked source with brace matching -- not a Java language
spec parser -- and emits the same drawable node/edge kinds the diagram spec
already understands.

Facts it produces are still marked ``PARSED`` by the caller, matching
``java_structure``: the walk is structural over masked source, not a line
regex.  Unbalanced braces or a failed mask return ``None`` so the caller can
record a parse failure instead of drawing an empty method.
"""

from __future__ import annotations

from typing import Any, Final

from .flowgraph import (
    EDGE_BRANCH,
    EDGE_EXCEPTION,
    EDGE_FLOW,
    EDGE_LOOP_BACK,
    EDGE_LOOP_BODY,
    EDGE_LOOP_EXIT,
    NODE_DECISION,
    NODE_END,
    NODE_LOOP,
    NODE_MERGE,
    NODE_PROCESS,
    NODE_START,
)
from .java_structure import _get_line_number, prepare_java_source

_LABEL_MAX = 60
_IDENT_CHARS: Final = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$"
)
_CONTROL: Final = frozenset(
    {
        "if",
        "for",
        "while",
        "do",
        "switch",
        "try",
        "return",
        "throw",
        "break",
        "continue",
        "synchronized",
        "assert",
    }
)


class _Unbalanced(ValueError):
    """The masked source has unmatched parentheses or braces."""


class _Builder:
    def __init__(self) -> None:
        self.nodes: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []
        self._counter = 0
        self._loops: list[tuple[str, str]] = []
        self.end_id: str = ""

    def node(self, kind: str, label: str) -> str:
        self._counter += 1
        node_id = f"cf{self._counter}"
        self.nodes.append({"id": node_id, "kind": kind, "label": label})
        return node_id

    def edge(
        self,
        source: str,
        target: str,
        kind: str,
        label: str | None = None,
    ) -> None:
        edge: dict[str, Any] = {
            "id": f"{source}-{kind}-{target}-{len(self.edges)}",
            "source": source,
            "target": target,
            "kind": kind,
        }
        if label is not None:
            edge["label"] = label
        self.edges.append(edge)

    def connect(self, sources: list[str], target: str, kind: str = EDGE_FLOW) -> None:
        for source in sources:
            self.edge(source, target, kind)


class _Scanner:
    def __init__(self, text: str) -> None:
        self.text = text
        self.i = 0

    @property
    def remaining(self) -> bool:
        return self.i < len(self.text)

    def skip_ws(self) -> None:
        text = self.text
        i = self.i
        while i < len(text) and text[i].isspace():
            i += 1
        self.i = i

    def peek_ident(self) -> str | None:
        self.skip_ws()
        if not self.remaining:
            return None
        if self.text[self.i] not in _IDENT_CHARS or self.text[self.i].isdigit():
            return None
        j = self.i
        while j < len(self.text) and self.text[j] in _IDENT_CHARS:
            j += 1
        return self.text[self.i : j]

    def consume_ident(self) -> str:
        ident = self.peek_ident()
        if ident is None:
            raise _Unbalanced("expected identifier")
        self.i += len(ident)
        return ident

    def peek(self) -> str | None:
        self.skip_ws()
        if not self.remaining:
            return None
        return self.text[self.i]

    def consume(self, expected: str) -> None:
        self.skip_ws()
        if not self.text.startswith(expected, self.i):
            raise _Unbalanced(f"expected {expected!r}")
        self.i += len(expected)

    def group(self, open_ch: str, close_ch: str) -> str:
        self.skip_ws()
        if not self.remaining or self.text[self.i] != open_ch:
            raise _Unbalanced(f"expected {open_ch!r}")
        start = self.i
        depth = 0
        i = self.i
        text = self.text
        while i < len(text):
            ch = text[i]
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    self.i = i + 1
                    return text[start : i + 1]
            i += 1
        raise _Unbalanced(f"unbalanced {open_ch}{close_ch}")

    def until_semicolon(self) -> str:
        self.skip_ws()
        start = self.i
        depth_paren = 0
        depth_brace = 0
        text = self.text
        i = self.i
        while i < len(text):
            ch = text[i]
            if ch == "(":
                depth_paren += 1
            elif ch == ")":
                depth_paren -= 1
                if depth_paren < 0:
                    raise _Unbalanced("unbalanced )")
            elif ch == "{":
                depth_brace += 1
            elif ch == "}":
                if depth_brace == 0:
                    self.i = i
                    return text[start:i].rstrip()
                depth_brace -= 1
            elif ch == ";" and depth_paren == 0 and depth_brace == 0:
                self.i = i + 1
                return text[start:i].strip()
            i += 1
        self.i = i
        return text[start:i].strip()


def _collapse(text: str) -> str:
    collapsed = " ".join(text.split())
    return collapsed[:_LABEL_MAX] or "statement"


def _condition_label(paren_group: str) -> str:
    inner = paren_group[1:-1].strip() if len(paren_group) >= 2 else paren_group
    return _collapse(inner) or "condition"


def java_function_control_flow(
    text: str,
    function_name: str,
) -> dict[str, Any] | None:
    """Return a drawable control-flow graph for *function_name* in Java *text*.

    ``None`` means the source could not be masked or braces did not balance.
    A masked compilation unit that simply does not define *function_name*
    returns an empty graph with that fact in ``diagnostics``.
    """

    prepared = prepare_java_source(text)
    if prepared is None:
        return None
    masked, line_offsets = prepared
    try:
        methods = _find_method_bodies(masked, function_name, line_offsets)
    except _Unbalanced:
        return None

    if not methods:
        return {
            "function": function_name,
            "nodes": [],
            "edges": [],
            "diagnostics": [f"function not found: {function_name}"],
        }

    diagnostics: list[str] = []
    line, body = methods[0]
    if len(methods) > 1:
        lines = ", ".join(str(item[0]) for item in methods)
        diagnostics.append(
            f"{len(methods)} definitions named {function_name} at lines {lines}; "
            f"drew the one at line {line}"
        )

    builder = _Builder()
    start = builder.node(NODE_START, f"start {function_name}")
    end = builder.node(NODE_END, f"end {function_name}")
    builder.end_id = end

    inner = body[1:-1] if len(body) >= 2 else body
    try:
        entry, exits = _parse_block(builder, _Scanner(inner))
    except _Unbalanced:
        return None

    if entry is None:
        builder.edge(start, end, EDGE_FLOW)
    else:
        builder.edge(start, entry, EDGE_FLOW)
        builder.connect(exits, end)

    return {
        "function": function_name,
        "nodes": builder.nodes,
        "edges": builder.edges,
        "diagnostics": diagnostics,
    }


def _find_method_bodies(
    masked: str,
    name: str,
    line_offsets: list[int],
) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    i = 0
    n = len(masked)
    while True:
        idx = masked.find(name, i)
        if idx < 0:
            break
        if idx > 0 and masked[idx - 1] in _IDENT_CHARS:
            i = idx + 1
            continue
        after = idx + len(name)
        if after < n and masked[after] in _IDENT_CHARS:
            i = idx + 1
            continue
        scanner = _Scanner(masked[after:])
        scanner.skip_ws()
        if not scanner.remaining or scanner.text[scanner.i] != "(":
            i = idx + 1
            continue
        try:
            scanner.group("(", ")")
            scanner.skip_ws()
            ident = scanner.peek_ident()
            if ident == "throws":
                while scanner.remaining and scanner.peek() not in {"{", ";"}:
                    scanner.i += 1
            scanner.skip_ws()
            if not scanner.remaining or scanner.text[scanner.i] != "{":
                i = after
                continue
            body = scanner.group("{", "}")
        except _Unbalanced as exc:
            raise _Unbalanced(str(exc)) from exc
        line = _get_line_number(idx, line_offsets)
        found.append((line, body))
        i = after + scanner.i
    return found


def _parse_block(builder: _Builder, scanner: _Scanner) -> tuple[str | None, list[str]]:
    entry: str | None = None
    exits: list[str] = []
    while scanner.remaining:
        scanner.skip_ws()
        if not scanner.remaining:
            break
        if scanner.peek() == "}":
            break
        if scanner.peek() == ";":
            scanner.i += 1
            continue
        stmt_entry, stmt_exits = _parse_statement(builder, scanner)
        if entry is None:
            entry = stmt_entry
        else:
            builder.connect(exits, stmt_entry)
        exits = stmt_exits
        if not exits:
            # The rest of the block is unreachable for drawing fall-through,
            # but still walk it so a later catch/loop shape is not dropped.
            continue
    return entry, exits


def _parse_statement(builder: _Builder, scanner: _Scanner) -> tuple[str, list[str]]:
    scanner.skip_ws()
    if scanner.peek() == "{":
        inner = scanner.group("{", "}")
        nested_entry, nested_exits = _parse_block(builder, _Scanner(inner[1:-1]))
        if nested_entry is None:
            node_id = builder.node(NODE_PROCESS, "block")
            return node_id, [node_id]
        return nested_entry, nested_exits

    ident = scanner.peek_ident()
    if ident in _CONTROL:
        scanner.consume_ident()
        if ident == "if":
            return _parse_if(builder, scanner)
        if ident == "for":
            return _parse_for(builder, scanner)
        if ident == "while":
            return _parse_while(builder, scanner)
        if ident == "do":
            return _parse_do_while(builder, scanner)
        if ident == "switch":
            return _parse_switch(builder, scanner)
        if ident == "try":
            return _parse_try(builder, scanner)
        if ident == "synchronized":
            return _parse_synchronized(builder, scanner)
        if ident in {"return", "throw"}:
            rest = scanner.until_semicolon()
            node_id = builder.node(NODE_PROCESS, _collapse(f"{ident} {rest}".strip()))
            if ident == "throw":
                builder.edge(node_id, builder.end_id, EDGE_EXCEPTION, "throw")
            else:
                builder.edge(node_id, builder.end_id, EDGE_FLOW)
            return node_id, []
        if ident == "break":
            scanner.until_semicolon()
            node_id = builder.node(NODE_PROCESS, "break")
            if builder._loops:
                builder.edge(node_id, builder._loops[-1][1], EDGE_LOOP_EXIT, "break")
            return node_id, []
        if ident == "continue":
            scanner.until_semicolon()
            node_id = builder.node(NODE_PROCESS, "continue")
            if builder._loops:
                builder.edge(node_id, builder._loops[-1][0], EDGE_LOOP_BACK, "continue")
            return node_id, []
        if ident == "assert":
            rest = scanner.until_semicolon()
            node_id = builder.node(NODE_PROCESS, _collapse(f"assert {rest}"))
            return node_id, [node_id]

    rest = scanner.until_semicolon()
    node_id = builder.node(NODE_PROCESS, _collapse(rest) if rest else "statement")
    return node_id, [node_id]


def _parse_if(builder: _Builder, scanner: _Scanner) -> tuple[str, list[str]]:
    condition = _condition_label(scanner.group("(", ")"))
    decision = builder.node(NODE_DECISION, condition)
    merge = builder.node(NODE_MERGE, "merge")

    then_entry, then_exits = _parse_statement(builder, scanner)
    builder.edge(decision, then_entry, EDGE_BRANCH, "true")
    builder.connect(then_exits, merge)

    scanner.skip_ws()
    if scanner.peek_ident() == "else":
        scanner.consume_ident()
        else_entry, else_exits = _parse_statement(builder, scanner)
        builder.edge(decision, else_entry, EDGE_BRANCH, "false")
        builder.connect(else_exits, merge)
    else:
        builder.edge(decision, merge, EDGE_BRANCH, "false")
    return decision, [merge]


def _parse_loop_body(
    builder: _Builder,
    scanner: _Scanner,
    label: str,
) -> tuple[str, list[str]]:
    loop = builder.node(NODE_LOOP, label)
    exit_merge = builder.node(NODE_MERGE, "loop exit")
    builder._loops.append((loop, exit_merge))
    body_entry, body_exits = _parse_statement(builder, scanner)
    builder._loops.pop()
    builder.edge(loop, body_entry, EDGE_LOOP_BODY, "each")
    for source in body_exits:
        builder.edge(source, loop, EDGE_LOOP_BACK, "repeat")
    builder.edge(loop, exit_merge, EDGE_LOOP_EXIT, "done")
    return loop, [exit_merge]


def _parse_for(builder: _Builder, scanner: _Scanner) -> tuple[str, list[str]]:
    header = _condition_label(scanner.group("(", ")"))
    return _parse_loop_body(builder, scanner, _collapse(f"for {header}"))


def _parse_while(builder: _Builder, scanner: _Scanner) -> tuple[str, list[str]]:
    header = _condition_label(scanner.group("(", ")"))
    return _parse_loop_body(builder, scanner, _collapse(f"while {header}"))


def _parse_do_while(builder: _Builder, scanner: _Scanner) -> tuple[str, list[str]]:
    loop = builder.node(NODE_LOOP, "do")
    exit_merge = builder.node(NODE_MERGE, "loop exit")
    builder._loops.append((loop, exit_merge))
    body_entry, body_exits = _parse_statement(builder, scanner)
    builder._loops.pop()
    scanner.skip_ws()
    if scanner.peek_ident() != "while":
        raise _Unbalanced("do without while")
    scanner.consume_ident()
    header = _condition_label(scanner.group("(", ")"))
    scanner.skip_ws()
    if scanner.peek() == ";":
        scanner.i += 1
    loop_label = _collapse(f"do while {header}")
    loop_node = next(node for node in builder.nodes if node["id"] == loop)
    loop_node["label"] = loop_label
    builder.edge(loop, body_entry, EDGE_LOOP_BODY, "each")
    for source in body_exits:
        builder.edge(source, loop, EDGE_LOOP_BACK, "repeat")
    builder.edge(loop, exit_merge, EDGE_LOOP_EXIT, "done")
    return loop, [exit_merge]


def _parse_switch(builder: _Builder, scanner: _Scanner) -> tuple[str, list[str]]:
    header = _condition_label(scanner.group("(", ")"))
    decision = builder.node(NODE_DECISION, _collapse(f"switch {header}"))
    merge = builder.node(NODE_MERGE, "merge")
    body = scanner.group("{", "}")
    inner = body[1:-1]
    cases = _split_switch_cases(inner)
    if not cases:
        builder.edge(decision, merge, EDGE_BRANCH, "default")
        return decision, [merge]
    for label, case_body in cases:
        case_entry, case_exits = _parse_block(builder, _Scanner(case_body))
        if case_entry is None:
            builder.edge(decision, merge, EDGE_BRANCH, label)
        else:
            builder.edge(decision, case_entry, EDGE_BRANCH, label)
            builder.connect(case_exits, merge)
    return decision, [merge]


def _split_switch_cases(inner: str) -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    scanner = _Scanner(inner)
    current_label: str | None = None
    current_start = 0
    while scanner.remaining:
        scanner.skip_ws()
        if not scanner.remaining:
            break
        ident = scanner.peek_ident()
        if ident in {"case", "default"}:
            if current_label is not None:
                cases.append((current_label, inner[current_start : scanner.i]))
            scanner.consume_ident()
            if ident == "case":
                current_label = _collapse(f"case {_consume_case_label(scanner)}")
            else:
                scanner.skip_ws()
                if scanner.peek() == ":":
                    scanner.i += 1
                current_label = "default"
            current_start = scanner.i
            continue
        if scanner.peek() == "{":
            scanner.group("{", "}")
            continue
        scanner.i += 1
    if current_label is not None:
        cases.append((current_label, inner[current_start:]))
    return cases


def _consume_case_label(scanner: _Scanner) -> str:
    start = scanner.i
    while scanner.remaining and scanner.text[scanner.i] != ":":
        scanner.i += 1
    label = scanner.text[start : scanner.i].strip()
    if scanner.remaining and scanner.text[scanner.i] == ":":
        scanner.i += 1
    return label


def _parse_try(builder: _Builder, scanner: _Scanner) -> tuple[str, list[str]]:
    scanner.skip_ws()
    if scanner.peek() == "(":
        scanner.group("(", ")")
    try_entry, try_exits = _parse_statement(builder, scanner)
    merge = builder.node(NODE_MERGE, "try exit")
    builder.connect(try_exits, merge)
    while scanner.peek_ident() == "catch":
        scanner.consume_ident()
        header = _condition_label(scanner.group("(", ")"))
        catch_entry, catch_exits = _parse_statement(builder, scanner)
        builder.edge(try_entry, catch_entry, EDGE_EXCEPTION, _collapse(f"catch {header}"))
        builder.connect(catch_exits, merge)
    if scanner.peek_ident() == "finally":
        scanner.consume_ident()
        finally_entry, finally_exits = _parse_statement(builder, scanner)
        builder.edge(merge, finally_entry, EDGE_FLOW, "finally")
        return try_entry, finally_exits
    return try_entry, [merge]


def _parse_synchronized(builder: _Builder, scanner: _Scanner) -> tuple[str, list[str]]:
    header = _condition_label(scanner.group("(", ")"))
    node_id = builder.node(NODE_PROCESS, _collapse(f"synchronized {header}"))
    body_entry, body_exits = _parse_statement(builder, scanner)
    builder.edge(node_id, body_entry, EDGE_FLOW)
    return node_id, body_exits

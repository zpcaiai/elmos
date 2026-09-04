"""A diagram-only control-flow walk over a Python function body.

This produces the node and edge shapes the diagram spec understands --
``start``/``end``/``process``/``decision``/``loop``/``merge`` nodes and
labelled edges -- so a branch, a loop back-edge, and a merge point can be
*drawn*.  It answers "what shape is this function" for a reader.

What this is not
================

This is **not** the certified transpile IR and must never be mistaken for it.
That IR deliberately admits only ``return``, ``if`` and ``let``; it has no
loop construct at all, because everything it accepts has to survive being
re-emitted into another language with identical semantics.  A drawing carries
no such obligation, so this walk covers ``for``, ``while``, ``try``, ``with``,
``break``, ``continue`` and ``raise`` -- constructs the certified IR rejects
outright.

Consequently nothing here may be used as evidence that a function converts.
The two live in separate modules, share no code, and this one imports nothing
from the route engine on purpose.

Effects
------

Source arrives as text.  No file is opened, no process is spawned, no socket
is created, so this is safe to call from inside a dispatched handler.
"""

from __future__ import annotations

import ast
from typing import Any, Final


NODE_START: Final[str] = "start"
NODE_END: Final[str] = "end"
NODE_PROCESS: Final[str] = "process"
NODE_DECISION: Final[str] = "decision"
NODE_LOOP: Final[str] = "loop"
NODE_MERGE: Final[str] = "merge"

EDGE_FLOW: Final[str] = "flow"
EDGE_BRANCH: Final[str] = "branch"
EDGE_LOOP_BODY: Final[str] = "loop-body"
EDGE_LOOP_BACK: Final[str] = "loop-back"
EDGE_LOOP_EXIT: Final[str] = "loop-exit"
EDGE_EXCEPTION: Final[str] = "exception"

#: Statements that carry control flow of their own.  Everything else is
#: straight-line work and gets collapsed into one ``process`` node, because a
#: diagram that draws one box per assignment is unreadable and tells the
#: reader nothing the source does not already say.
_STRUCTURED: Final[tuple[type, ...]] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    # ``except*`` carries the same shape as ``except`` and is walked the same
    # way.  It was omitted at first, which meant a function using it was drawn
    # with its handlers silently missing rather than with a visible gap.
    ast.TryStar,
    ast.Match,
    ast.With,
    ast.AsyncWith,
    ast.Return,
    ast.Raise,
    ast.Break,
    ast.Continue,
)

_LABEL_MAX = 60


def _summarize(statement: ast.stmt) -> str:
    """Return a short human label for a statement."""

    try:
        text = ast.unparse(statement)
    except Exception:  # pragma: no cover - unparse is total for parsed trees
        return type(statement).__name__
    first = text.strip().splitlines()[0] if text.strip() else type(statement).__name__
    return first[:_LABEL_MAX]


def _case_label(case: ast.match_case) -> str:
    """Return a short label for one ``match`` case, guard included.

    The guard is part of the branch condition; dropping it would draw two
    visibly identical decisions for ``case X if a`` and ``case X if b``.
    """

    pattern = _expression_label(case.pattern, "pattern")
    if case.guard is None:
        return pattern
    return f"{pattern} if {_expression_label(case.guard, 'guard')}"


def _expression_label(node: ast.AST | None, fallback: str) -> str:
    if node is None:
        return fallback
    try:
        return ast.unparse(node).strip()[:_LABEL_MAX] or fallback
    except Exception:  # pragma: no cover
        return fallback


class _Builder:
    """Accumulates nodes and edges while walking one function body."""

    def __init__(self) -> None:
        self.nodes: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []
        self._counter = 0
        #: Stack of (continue_target, break_target) for the enclosing loops.
        self._loops: list[tuple[str, str]] = []
        #: The single terminal node every return and raise flows into.
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

    # -- block walking -------------------------------------------------

    def block(self, body: list[ast.stmt]) -> tuple[str | None, list[str]]:
        """Emit *body*.

        Returns ``(entry_id, exit_ids)``.  ``exit_ids`` are the nodes that
        fall through to whatever follows; an empty list means the block always
        leaves by another route (returned, raised, broke, continued), which is
        exactly what makes the ``end`` wiring correct.
        """

        entry: str | None = None
        pending: list[str] = []
        straight: list[ast.stmt] = []

        def flush() -> None:
            nonlocal entry, pending, straight
            if not straight:
                return
            label = _summarize(straight[0])
            if len(straight) > 1:
                label = f"{label} (+{len(straight) - 1} more)"
            node_id = self.node(NODE_PROCESS, label)
            if entry is None:
                entry = node_id
            self.connect(pending, node_id)
            pending = [node_id]
            straight = []

        for statement in body:
            if not isinstance(statement, _STRUCTURED):
                straight.append(statement)
                continue
            flush()
            sub_entry, sub_exits = self.statement(statement)
            if entry is None:
                entry = sub_entry
            self.connect(pending, sub_entry)
            pending = sub_exits

        flush()
        return entry, pending

    # -- individual statements ----------------------------------------

    def statement(self, statement: ast.stmt) -> tuple[str, list[str]]:
        if isinstance(statement, ast.If):
            return self._if(statement)
        if isinstance(statement, (ast.For, ast.AsyncFor)):
            return self._for(statement)
        if isinstance(statement, ast.While):
            return self._while(statement)
        if isinstance(statement, (ast.Try, ast.TryStar)):
            return self._try(statement)
        if isinstance(statement, ast.Match):
            return self._match(statement)
        if isinstance(statement, (ast.With, ast.AsyncWith)):
            return self._with(statement)
        if isinstance(statement, ast.Return):
            node_id = self.node(
                NODE_PROCESS,
                f"return {_expression_label(statement.value, '')}".strip(),
            )
            self.edge(node_id, self.end_id, EDGE_FLOW, "return")
            return node_id, []
        if isinstance(statement, ast.Raise):
            node_id = self.node(NODE_PROCESS, _summarize(statement))
            self.edge(node_id, self.end_id, EDGE_EXCEPTION, "raise")
            return node_id, []
        if isinstance(statement, ast.Break):
            node_id = self.node(NODE_PROCESS, "break")
            if self._loops:
                self.edge(node_id, self._loops[-1][1], EDGE_LOOP_EXIT, "break")
            return node_id, []
        if isinstance(statement, ast.Continue):
            node_id = self.node(NODE_PROCESS, "continue")
            if self._loops:
                self.edge(node_id, self._loops[-1][0], EDGE_LOOP_BACK, "continue")
            return node_id, []
        raise AssertionError(f"unhandled structured statement: {type(statement)}")

    def _if(self, statement: ast.If) -> tuple[str, list[str]]:
        decision = self.node(
            NODE_DECISION, _expression_label(statement.test, "condition")
        )
        merge = self.node(NODE_MERGE, "merge")

        then_entry, then_exits = self.block(statement.body)
        if then_entry is None:
            self.edge(decision, merge, EDGE_BRANCH, "true")
        else:
            self.edge(decision, then_entry, EDGE_BRANCH, "true")
            self.connect(then_exits, merge)

        if statement.orelse:
            else_entry, else_exits = self.block(statement.orelse)
            if else_entry is None:
                self.edge(decision, merge, EDGE_BRANCH, "false")
            else:
                self.edge(decision, else_entry, EDGE_BRANCH, "false")
                self.connect(else_exits, merge)
        else:
            self.edge(decision, merge, EDGE_BRANCH, "false")

        return decision, [merge]

    def _loop(
        self,
        label: str,
        body: list[ast.stmt],
        orelse: list[ast.stmt],
    ) -> tuple[str, list[str]]:
        loop = self.node(NODE_LOOP, label)
        exit_merge = self.node(NODE_MERGE, "loop exit")

        self._loops.append((loop, exit_merge))
        body_entry, body_exits = self.block(body)
        self._loops.pop()

        if body_entry is None:
            # An empty body still loops; the back-edge is the whole shape.
            self.edge(loop, loop, EDGE_LOOP_BACK, "repeat")
        else:
            self.edge(loop, body_entry, EDGE_LOOP_BODY, "each")
            for source in body_exits:
                self.edge(source, loop, EDGE_LOOP_BACK, "repeat")

        if orelse:
            else_entry, else_exits = self.block(orelse)
            if else_entry is None:
                self.edge(loop, exit_merge, EDGE_LOOP_EXIT, "done")
            else:
                self.edge(loop, else_entry, EDGE_LOOP_EXIT, "done")
                self.connect(else_exits, exit_merge)
        else:
            self.edge(loop, exit_merge, EDGE_LOOP_EXIT, "done")

        return loop, [exit_merge]

    def _for(self, statement: ast.For | ast.AsyncFor) -> tuple[str, list[str]]:
        target = _expression_label(statement.target, "item")
        iterator = _expression_label(statement.iter, "iterable")
        prefix = "async for" if isinstance(statement, ast.AsyncFor) else "for"
        return self._loop(
            f"{prefix} {target} in {iterator}"[:_LABEL_MAX],
            statement.body,
            statement.orelse,
        )

    def _while(self, statement: ast.While) -> tuple[str, list[str]]:
        return self._loop(
            f"while {_expression_label(statement.test, 'condition')}"[:_LABEL_MAX],
            statement.body,
            statement.orelse,
        )

    def _match(self, statement: ast.Match) -> tuple[str, list[str]]:
        """Draw a ``match`` as one decision per case.

        A ``match`` with five cases is five branches a reader can take.  Before
        this method existed ``ast.Match`` was not in ``_STRUCTURED``, so the
        whole statement collapsed into a single ``process`` box: the branches
        were not drawn *and* nothing said they were missing.  That is the exact
        failure mode this walk exists to prevent, so it is handled here rather
        than reported as a limitation.

        The shape is a chain, not a fan, because that is what ``match`` does:
        each case is tried only when every earlier case failed to match.
        """

        subject = _expression_label(statement.subject, "subject")
        merge = self.node(NODE_MERGE, "match merge")
        entry: str | None = None
        previous: str | None = None
        for case in statement.cases:
            label = f"match {subject} case {_case_label(case)}"[:_LABEL_MAX]
            decision = self.node(NODE_DECISION, label)
            if entry is None:
                entry = decision
            if previous is not None:
                self.edge(previous, decision, EDGE_BRANCH, "false")
            case_entry, case_exits = self.block(case.body)
            if case_entry is None:
                self.edge(decision, merge, EDGE_BRANCH, "true")
            else:
                self.edge(decision, case_entry, EDGE_BRANCH, "true")
                self.connect(case_exits, merge)
            previous = decision
        if previous is None or entry is None:
            # ``match`` with no cases does not parse; keep the graph connected
            # rather than leaving an orphan merge if one ever arrives.
            return merge, [merge]
        self.edge(previous, merge, EDGE_BRANCH, "false")
        return entry, [merge]

    def _try(self, statement: ast.Try | ast.TryStar) -> tuple[str, list[str]]:
        try_node = self.node(NODE_PROCESS, "try*" if isinstance(statement, ast.TryStar) else "try")
        merge = self.node(NODE_MERGE, "try merge")
        settled: list[str] = []

        body_entry, body_exits = self.block(statement.body)
        if body_entry is None:
            settled.append(try_node)
        else:
            self.edge(try_node, body_entry, EDGE_FLOW)
            if statement.orelse:
                else_entry, else_exits = self.block(statement.orelse)
                if else_entry is None:
                    settled.extend(body_exits)
                else:
                    self.connect(body_exits, else_entry)
                    settled.extend(else_exits)
            else:
                settled.extend(body_exits)

        for handler in statement.handlers:
            kind_label = _expression_label(handler.type, "Exception")
            handler_entry, handler_exits = self.block(handler.body)
            if handler_entry is None:
                self.edge(try_node, merge, EDGE_EXCEPTION, f"except {kind_label}")
            else:
                self.edge(
                    try_node, handler_entry, EDGE_EXCEPTION, f"except {kind_label}"
                )
                settled.extend(handler_exits)

        self.connect(settled, merge)

        if statement.finalbody:
            final_entry, final_exits = self.block(statement.finalbody)
            if final_entry is not None:
                self.edge(merge, final_entry, EDGE_FLOW, "finally")
                return try_node, final_exits

        return try_node, [merge]

    def _with(self, statement: ast.With | ast.AsyncWith) -> tuple[str, list[str]]:
        items = ", ".join(
            _expression_label(item.context_expr, "context") for item in statement.items
        )
        prefix = "async with" if isinstance(statement, ast.AsyncWith) else "with"
        node_id = self.node(NODE_PROCESS, f"{prefix} {items}"[:_LABEL_MAX])
        body_entry, body_exits = self.block(statement.body)
        if body_entry is None:
            return node_id, [node_id]
        self.edge(node_id, body_entry, EDGE_FLOW)
        return node_id, body_exits


def function_control_flow(
    text: str,
    function_name: str,
) -> dict[str, Any] | None:
    """Return a drawable control-flow graph for *function_name* in *text*.

    ``None`` means the text did not parse.  A parsed module that simply does
    not define *function_name* returns a graph carrying that fact in
    ``diagnostics`` rather than pretending the function was empty.
    """

    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return None

    target = _find_function(tree, function_name)
    if target is None:
        return {
            "function": function_name,
            "nodes": [],
            "edges": [],
            "diagnostics": [f"function not found: {function_name}"],
        }

    diagnostics: list[str] = []
    definitions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(definitions) > 1:
        # One module routinely defines the same method name on several classes
        # -- ``__init__`` thirteen times in one real file, measured.  Picking
        # one silently would hand a reader a diagram of a different function
        # than the one they asked for and give them no way to notice.
        lines = ", ".join(str(node.lineno) for node in sorted(definitions, key=lambda n: n.lineno))
        diagnostics.append(
            f"{len(definitions)} definitions named {function_name} at lines {lines}; "
            f"drew the one at line {target.lineno}"
        )

    builder = _Builder()
    start = builder.node(NODE_START, f"start {function_name}")
    end = builder.node(NODE_END, f"end {function_name}")
    builder.end_id = end

    entry, exits = builder.block(target.body)
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


def _find_function(
    tree: ast.Module, name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Return the first function named *name*, at any nesting depth."""

    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return node
    return None


__all__ = [
    "EDGE_BRANCH",
    "EDGE_EXCEPTION",
    "EDGE_FLOW",
    "EDGE_LOOP_BACK",
    "EDGE_LOOP_BODY",
    "EDGE_LOOP_EXIT",
    "NODE_DECISION",
    "NODE_END",
    "NODE_LOOP",
    "NODE_MERGE",
    "NODE_PROCESS",
    "NODE_START",
    "function_control_flow",
]

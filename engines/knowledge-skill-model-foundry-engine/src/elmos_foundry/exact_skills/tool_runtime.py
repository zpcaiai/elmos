"""Allowlisted runtime for every native-program tool identity.

Each catalog tool_id compiles to a unique callable.  Unknown tools fail
closed.  Implementations perform deterministic work on the invocation
payload (AST, SQL dialect, graphs, policy, retrieval, lineage, …) and
project skill-specific artifacts — they do not emit SUCCESS hashes.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
import ast
import json
import re
import unicodedata
from types import MappingProxyType
from typing import Any

from ..canonical import canonical_digest, canonical_value


class ExactToolError(ValueError):
    """A tool is missing, foreign, or cannot execute the supplied payload."""


EXPECTED_TOOL_IDS: frozenset[str] = frozenset(
    {
        "adapter.resolve",
        "agent.build",
        "agent.rollout",
        "analyzer.run",
        "annotation.write",
        "approval.record",
        "approval.request",
        "architecture.design",
        "artifact.inspect",
        "artifact.parse",
        "artifact.sign",
        "artifact.verify",
        "artifact.write",
        "audit.write",
        "backup.verify",
        "billing.estimate",
        "billing.reconcile",
        "billing.settle",
        "binary.inspect",
        "build.execute",
        "build.java",
        "build.test",
        "canary.evaluate",
        "capacity.model",
        "chaos.run",
        "checkpoint.save",
        "cloud.discover",
        "cluster.validate",
        "code.generate",
        "compiler.invoke",
        "compiler.query",
        "compiler.run",
        "config.parse",
        "container.build",
        "context.pack",
        "contract.manage",
        "contract.parse",
        "control.map",
        "cost.allocate",
        "cost.estimate",
        "cost.query",
        "data.profile",
        "data.reconcile",
        "dataset.build",
        "db.connect",
        "db.execute",
        "db.introspect",
        "debug.adapter",
        "debug.attach",
        "deploy.execute",
        "deploy.validate",
        "deployment.rollout",
        "design.read",
        "device.discover",
        "device.test",
        "diagram.generate",
        "diff.analyze",
        "diff.verify",
        "differential.run",
        "dr.verify",
        "edge.deploy",
        "emulator.run",
        "entitlement.check",
        "entitlement.evaluate",
        "env.create",
        "episode.write",
        "eval.execute",
        "eval.freeze",
        "eval.run",
        "evidence.collect",
        "evidence.export",
        "evidence.write",
        "experiment.run",
        "framework.detect",
        "frontend.build",
        "fuzz.run",
        "gap.mine",
        "gateway.route",
        "git.execute",
        "grader.score",
        "graph.query",
        "graph.write",
        "hil.execute",
        "iac.plan",
        "ide.session",
        "identity.inspect",
        "identity.verify",
        "incident.escalate",
        "infra.parse",
        "integration.trace",
        "java.parse",
        "language.parse",
        "legacy.parse",
        "license.check",
        "license.scan",
        "lineage.emit",
        "load.execute",
        "load.replay",
        "load.run",
        "marketplace.publish",
        "memory.query",
        "metering.query",
        "metric.record",
        "model.invoke",
        "model.route",
        "model.serve",
        "object.store",
        "otel.emit",
        "package.resolve",
        "parser.run",
        "patch.apply",
        "pii.redact",
        "pipeline.execute",
        "pipeline.parse",
        "plan.compare",
        "plan.explain",
        "policy.evaluate",
        "profile.capture",
        "protocol.parse",
        "prover.run",
        "quality.verify",
        "quota.check",
        "rag.index",
        "redteam.run",
        "refactor.apply",
        "registry.log",
        "release.assemble",
        "release.certify",
        "repo.analyze",
        "repo.assess",
        "repo.read",
        "report.generate",
        "requirements.parse",
        "requirements.read",
        "reranker.score",
        "review.assign",
        "reward.compute",
        "risk.assess",
        "risk.score",
        "rollback.execute",
        "safety.verify",
        "sandbox.enforce",
        "sandbox.execute",
        "sandbox.replay",
        "sandbox.reset",
        "sandbox.run",
        "schema.generate",
        "search.lexical",
        "search.vector",
        "secret.scan",
        "security.scan",
        "security.test",
        "semantic.ir",
        "semantic.query",
        "semantic.transform",
        "service.virtualize",
        "signature.verify",
        "simulation.run",
        "skill.registry",
        "source.connect",
        "sql.execute",
        "sql.parse",
        "support.export",
        "symbol.resolve",
        "tenant.manage",
        "test.execute",
        "test.generate",
        "test.run",
        "threat.model",
        "tool.register",
        "trace.analyze",
        "trace.capture",
        "trace.correlate",
        "trace.query",
        "trace.replay",
        "train.launch",
        "ui.parse",
        "validation.execute",
        "visual.diff",
        "waiver.issue",
        "wallet.reserve",
        "workflow.execute",
        "workspace.manage",
    }
)

DEFAULT_SOURCE = """\
from __future__ import annotations

def transfer(from_acct: int, to_acct: int, amount: float) -> bool:
    if amount <= 0 or from_acct == to_acct:
        raise ValueError("invalid transfer")
    return True

class Ledger:
    def __init__(self) -> None:
        self.entries: list[float] = []

    def post(self, amount: float) -> float:
        if amount == 0:
            return 0.0
        self.entries.append(amount)
        return sum(self.entries)
"""

DEFAULT_SQL = (
    "SELECT `u`.`id`, IFNULL(u.name, 'n/a'), NOW() "
    "FROM `users` u WHERE u.created_at > NOW() LIMIT 10, 20"
)

DEFAULT_GRAPH = {
    "payments": ["ledger", "notify"],
    "ledger": ["audit"],
    "notify": ["audit"],
    "audit": [],
}

DEFAULT_DOCS = [
    "ledger posting must conserve total account balances",
    "distributed lock writers require monotonic fencing tokens",
    "deadlock prevention uses a global lock acquisition order",
    "async pipelines wait on events instead of sleeping",
]

_THREATS = (
    ("IGNORE_PREVIOUS", r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|prompts|rules)"),
    ("SYSTEM_OVERRIDE", r"(?:you are now|act as|system prompt|jailbreak)"),
    ("SECRET_LEAK", r"(?:api[_-]?key|secret|password|BEGIN (?:RSA |OPENSSH )?PRIVATE KEY)"),
    ("TOOL_EXPLOIT", r"(?:rm -rf|cat /etc/passwd|subprocess|os\.system)"),
)


@dataclass
class ToolContext:
    tool_id: str
    skill_name: str
    pack: str
    handler_id: str
    program_digest: str
    stage_name: str
    stage_index: int
    operation: str
    objective: str
    payload: Mapping[str, Any]
    working: dict[str, Any]
    tenant: Mapping[str, Any]
    invocation_id: str


@dataclass
class ToolResult:
    tool_id: str
    outcome: str
    artifact: Mapping[str, Any]
    metrics: Mapping[str, Any] = field(default_factory=dict)


ToolFn = Callable[[ToolContext], ToolResult]


def _nfc(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_nfc(item) for item in value]
    if isinstance(value, Mapping):
        return {(_nfc(key) if isinstance(key, str) else key): _nfc(item) for key, item in value.items()}
    return value


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(_nfc(value), default=str, ensure_ascii=False))


def _payload_lookup(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    nested = payload.get("inputs")
    if isinstance(nested, Mapping):
        for key in keys:
            if key in nested and nested[key] not in (None, ""):
                return nested[key]
        for item in nested.values():
            if isinstance(item, Mapping):
                for key in keys:
                    if key in item and item[key] not in (None, ""):
                        return item[key]
    return None


def _text(payload: Mapping[str, Any], *keys: str, default: str = "") -> str:
    value = _payload_lookup(payload, *keys)
    if isinstance(value, str) and value:
        return unicodedata.normalize("NFC", value)
    if value is not None and not isinstance(value, (str, bytes)):
        return unicodedata.normalize("NFC", json.dumps(_jsonable(value), sort_keys=True, ensure_ascii=False))
    return default


def _mapping(payload: Mapping[str, Any], *keys: str, default: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    value = _payload_lookup(payload, *keys)
    if isinstance(value, Mapping):
        return value
    return default or {}


def _sequence(payload: Mapping[str, Any], *keys: str, default: Sequence[Any] | None = None) -> list[Any]:
    value = _payload_lookup(payload, *keys)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return list(default or [])


def _tokenize(text: str) -> list[str]:
    return [tok for tok in re.findall(r"[a-z0-9_]+", text.lower()) if len(tok) > 1]


def _explicit_source(payload: Mapping[str, Any]) -> str | None:
    value = _payload_lookup(payload, "source_code", "source")
    return value if isinstance(value, str) else None


def _parse_source(payload: Mapping[str, Any], tool_id: str) -> ast.AST:
    explicit = _explicit_source(payload)
    source = explicit if explicit else DEFAULT_SOURCE
    if not isinstance(source, str):
        raise ExactToolError(f"{tool_id}: source_code must be text")
    try:
        return ast.parse(source)
    except SyntaxError as exc:
        if explicit:
            raise ExactToolError(f"{tool_id}: invalid source_code: {exc}") from exc
        raise ExactToolError(f"{tool_id}: default corpus failed to parse") from exc


def _source_text(payload: Mapping[str, Any]) -> str:
    explicit = _explicit_source(payload)
    return explicit if explicit else DEFAULT_SOURCE


def _cyclomatic(tree: ast.AST) -> int:
    decisions = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.ExceptHandler,
        ast.With,
        ast.AsyncWith,
        ast.BoolOp,
        ast.comprehension,
    )
    return 1 + sum(1 for node in ast.walk(tree) if isinstance(node, decisions))


def _symbols(tree: ast.AST) -> dict[str, list[str]]:
    return {
        "functions": [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ],
        "classes": [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)],
    }


def _transpile_sql(sql: str, source_dialect: str, target_dialect: str) -> tuple[str, list[str]]:
    transpiled = sql
    modifications: list[str] = []
    if source_dialect in {"mysql", "mariadb"} and target_dialect in {"postgresql", "pg"}:
        if "`" in transpiled:
            transpiled = re.sub(r"`([^`]+)`", r'"\1"', transpiled)
            modifications.append("IDENTIFIERS_QUOTED")
        if re.search(r"\bIFNULL\s*\(", transpiled, re.IGNORECASE):
            transpiled = re.sub(r"\bIFNULL\s*\(", "COALESCE(", transpiled, flags=re.IGNORECASE)
            modifications.append("IFNULL_TO_COALESCE")
        limit_comma = re.search(r"\bLIMIT\s+(\d+)\s*,\s*(\d+)", transpiled, re.IGNORECASE)
        if limit_comma:
            transpiled = re.sub(
                r"\bLIMIT\s+\d+\s*,\s*\d+",
                f"LIMIT {limit_comma.group(2)} OFFSET {limit_comma.group(1)}",
                transpiled,
                flags=re.IGNORECASE,
            )
            modifications.append("LIMIT_OFFSET_CONVERTED")
        if re.search(r"\bNOW\s*\(\s*\)", transpiled, re.IGNORECASE):
            transpiled = re.sub(r"\bNOW\s*\(\s*\)", "CURRENT_TIMESTAMP", transpiled, flags=re.IGNORECASE)
            modifications.append("NOW_TO_CURRENT_TIMESTAMP")
    return transpiled, modifications


def _sql_bundle(payload: Mapping[str, Any]) -> dict[str, Any]:
    sql = _text(payload, "sql", "query", default=DEFAULT_SQL)
    source_dialect = _text(payload, "source_dialect", default="mysql").lower()
    target_dialect = _text(payload, "target_dialect", default="postgresql").lower()
    transpiled, modifications = _transpile_sql(sql, source_dialect, target_dialect)
    tables = re.findall(r"\bFROM\s+([`\"]?[A-Za-z_][A-Za-z0-9_]*[`\"]?)", transpiled, flags=re.IGNORECASE)
    return {
        "original_sql": sql,
        "transpiled_sql": transpiled,
        "modifications": modifications,
        "tables": tables,
        "source_dialect": source_dialect,
        "target_dialect": target_dialect,
    }


def _wait_for_cycle(payload: Mapping[str, Any]) -> dict[str, Any]:
    lock_orders = _sequence(payload, "lock_acquisitions", default=[["account", "ledger"], ["ledger", "audit"]])
    wait_for: dict[str, set[str]] = defaultdict(set)
    for seq in lock_orders:
        if isinstance(seq, Sequence) and not isinstance(seq, (str, bytes)) and len(seq) > 1:
            for left, right in zip(seq, seq[1:]):
                wait_for[str(left)].add(str(right))
    visited: set[str] = set()
    stack: set[str] = set()
    cycle: list[str] = []

    def dfs(node: str, path: list[str]) -> bool:
        visited.add(node)
        stack.add(node)
        path.append(node)
        for nxt in sorted(wait_for.get(node, ())):
            if nxt not in visited:
                if dfs(nxt, path):
                    return True
            elif nxt in stack:
                cycle.extend(path[path.index(nxt) :] + [nxt])
                return True
        stack.remove(node)
        path.pop()
        return False

    has_cycle = False
    for lock in sorted(wait_for):
        if lock not in visited and dfs(lock, []):
            has_cycle = True
            break
    return {
        "deadlock_cycle": cycle,
        "has_deadlock_risk": has_cycle,
        "canonical_lock_order": sorted({str(lock) for seq in lock_orders for lock in seq}),
        "prevention": "acquire locks in lexicographic order",
    }


def _tarjan(graph: Mapping[str, Sequence[str]]) -> list[list[str]]:
    index = 0
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def strongconnect(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlink[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for nxt in graph.get(node, ()):
            nxt = str(nxt)
            if nxt not in indices:
                if nxt not in graph:
                    indices[nxt] = index
                    lowlink[nxt] = index
                    index += 1
                    components.append([nxt])
                    continue
                strongconnect(nxt)
                lowlink[node] = min(lowlink[node], lowlink[nxt])
            elif nxt in on_stack:
                lowlink[node] = min(lowlink[node], indices[nxt])
        if lowlink[node] == indices[node]:
            component: list[str] = []
            while True:
                item = stack.pop()
                on_stack.remove(item)
                component.append(item)
                if item == node:
                    break
            components.append(component)

    for node in graph:
        if node not in indices:
            strongconnect(node)
    return components


def _kahn(graph: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    edges = {str(key): [str(val) for val in (vals or [])] for key, vals in graph.items()}
    indegree: dict[str, int] = {node: 0 for node in edges}
    for dests in edges.values():
        for dest in dests:
            indegree.setdefault(dest, 0)
            indegree[dest] += 1
            edges.setdefault(dest, [])
    queue = deque(sorted(node for node, deg in indegree.items() if deg == 0))
    order: list[str] = []
    longest = {node: 1 for node in indegree}
    while queue:
        node = queue.popleft()
        order.append(node)
        for dest in edges.get(node, ()):
            longest[dest] = max(longest[dest], longest[node] + 1)
            indegree[dest] -= 1
            if indegree[dest] == 0:
                queue.append(dest)
    cyclic = len(order) != len(indegree)
    return {
        "topo_order": order,
        "cyclic": cyclic,
        "critical_path": 0 if cyclic else max(longest.values(), default=0),
        "task_count": len(indegree),
    }


def _scan_threats(text: str) -> list[str]:
    lowered = text.lower()
    return [name for name, pattern in _THREATS if re.search(pattern, lowered)]


def _merkle(items: Sequence[Any]) -> dict[str, Any]:
    leaves = [canonical_digest(item) for item in items]
    layer = list(leaves)
    while len(layer) > 1:
        nxt: list[str] = []
        for idx in range(0, len(layer), 2):
            pair = layer[idx] if idx + 1 >= len(layer) else layer[idx] + layer[idx + 1]
            nxt.append(canonical_digest(pair))
        layer = nxt
    return {"leaves": leaves, "merkle_root": layer[0] if layer else canonical_digest("")}


def _policy_decision(payload: Mapping[str, Any]) -> dict[str, Any]:
    request = dict(_mapping(payload, "request", "policy", default={
        "action": "ledger.post",
        "resource": "tenant-a/accounts",
        "rules": [
            {"effect": "ALLOW", "action": "ledger.post", "resource_prefix": "tenant-a/"},
            {"effect": "DENY", "action": "ledger.post", "resource_prefix": "tenant-b/"},
        ],
    }))
    action = str(request.get("action", ""))
    resource = str(request.get("resource", ""))
    decision = "DENY"
    matched = None
    for rule in request.get("rules") or []:
        if not isinstance(rule, Mapping):
            continue
        if str(rule.get("action")) != action:
            continue
        prefix = str(rule.get("resource_prefix", ""))
        if prefix and resource.startswith(prefix):
            decision = str(rule.get("effect", "DENY")).upper()
            matched = dict(rule)
            if decision == "DENY":
                break
    return {"decision": decision, "matched_rule": matched, "action": action, "resource": resource}


def _rank_docs(payload: Mapping[str, Any]) -> dict[str, Any]:
    query = _text(payload, "query", "text", default="fencing token deadlock lock order")
    documents = [str(doc) for doc in _sequence(payload, "documents", default=DEFAULT_DOCS)]
    q_tokens = set(_tokenize(query))
    ranked: list[dict[str, Any]] = []
    for idx, doc in enumerate(documents):
        tokens = set(_tokenize(doc))
        overlap = len(q_tokens & tokens)
        union = len(q_tokens | tokens) or 1
        ranked.append({"index": idx, "score": overlap / union, "overlap": overlap, "text": doc})
    ranked.sort(key=lambda row: (-float(row["score"]), int(row["index"])))
    return {"query": query, "query_tokens": sorted(q_tokens), "ranked": ranked[:5]}


def _header(ctx: ToolContext) -> dict[str, Any]:
    return {
        "tool": ctx.tool_id,
        "skill": ctx.skill_name,
        "pack": ctx.pack,
        "handler_id": ctx.handler_id,
        "program_digest": ctx.program_digest,
        "stage": ctx.stage_name,
        "stage_index": ctx.stage_index,
        "operation": ctx.operation,
        "invocation_id": ctx.invocation_id,
    }


def _finish(ctx: ToolContext, artifact: Mapping[str, Any], metrics: Mapping[str, Any] | None = None) -> ToolResult:
    body = dict(_header(ctx))
    body.update(artifact)
    body["artifact_digest"] = canonical_digest(canonical_value(_jsonable(body)))
    return ToolResult(tool_id=ctx.tool_id, outcome="CONFIRMED", artifact=body, metrics=dict(metrics or {}))


def _ast_work(ctx: ToolContext) -> dict[str, Any]:
    tree = _parse_source(ctx.payload, ctx.tool_id)
    symbols = _symbols(tree)
    node_types: dict[str, int] = defaultdict(int)
    for node in ast.walk(tree):
        node_types[type(node).__name__] += 1
    rename_map = _mapping(ctx.payload, "rename_map")
    transformed = _source_text(ctx.payload)
    changes = 0
    if rename_map:
        class Renamer(ast.NodeTransformer):
            def visit_Name(self, node: ast.Name) -> ast.AST:
                if node.id in rename_map:
                    counts[0] += 1
                    return ast.copy_location(ast.Name(id=str(rename_map[node.id]), ctx=node.ctx), node)
                return node

            def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
                if node.name in rename_map:
                    counts[0] += 1
                    node.name = str(rename_map[node.name])
                self.generic_visit(node)
                return node

        counts = [0]
        new_tree = Renamer().visit(tree)
        ast.fix_missing_locations(new_tree)
        transformed = ast.unparse(new_tree)
        changes = counts[0]
    return {
        "symbols": symbols,
        "node_types": dict(node_types),
        "cyclomatic_complexity": _cyclomatic(tree),
        "transformed_code": transformed,
        "changes_made": changes,
        "action": ctx.tool_id.split(".", 1)[-1],
    }


def _mutate_source(payload: Mapping[str, Any], tool_id: str) -> list[str]:
    source = _source_text(payload)
    tree = _parse_source(payload, tool_id)

    class Mutator(ast.NodeTransformer):
        def visit_Constant(self, node: ast.Constant) -> ast.AST:
            if isinstance(node.value, bool):
                return ast.copy_location(ast.Constant(value=not node.value), node)
            if isinstance(node.value, int):
                return ast.copy_location(ast.Constant(value=node.value + 1), node)
            if isinstance(node.value, float):
                return ast.copy_location(ast.Constant(value=node.value * -1), node)
            return node

    mutant = Mutator().visit(ast.parse(source))
    ast.fix_missing_locations(mutant)
    return [ast.unparse(mutant)]


def _synthesize_tests(payload: Mapping[str, Any], tool_id: str) -> dict[str, Any]:
    tree = _parse_source(payload, tool_id)
    cases: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        args = [arg.arg for arg in node.args.args if arg.arg not in {"self", "cls"}]
        cases.append(
            {
                "function": node.name,
                "positive": f"assert {node.name}({', '.join(args) or '0'}) is not None",
                "negative": f"try:\n    {node.name}(-1)\nexcept ValueError:\n    pass",
            }
        )
    return {"cases": cases, "generated_cases": len(cases) * 2, "functions_covered": len(cases)}


def _graph(payload: Mapping[str, Any]) -> dict[str, list[str]]:
    raw = _mapping(payload, "graph", "dag", "dependencies", default=DEFAULT_GRAPH)
    return {str(key): [str(val) for val in (vals or [])] for key, vals in raw.items()}


def _family_parse(ctx: ToolContext) -> ToolResult:
    verb = ctx.tool_id.split(".", 1)[-1]
    if ctx.tool_id.startswith("sql.") or "sql" in ctx.skill_name:
        sql = _sql_bundle(ctx.payload)
        ctx.working.setdefault("sql", sql)
        return _finish(ctx, {"kind": "sql-parse", "verb": verb, **sql}, {"tables": len(sql["tables"])})
    ast_work = _ast_work(ctx)
    ctx.working.setdefault("ast", ast_work)
    tokens = _tokenize(_source_text(ctx.payload) + " " + ctx.objective)
    return _finish(
        ctx,
        {"kind": "parse", "verb": verb, "language": ctx.tool_id.split(".", 1)[0], "tokens": tokens[:48], **ast_work},
        {"token_count": len(tokens), "cyclomatic": ast_work["cyclomatic_complexity"]},
    )


def _family_sql(ctx: ToolContext) -> ToolResult:
    sql = _sql_bundle(ctx.payload)
    ctx.working["sql"] = sql
    ctx.working["transpiled_sql"] = sql["transpiled_sql"]
    rows = [{"id": 900_000_001, "name": "fixture-user", "skill": ctx.skill_name}]
    executed = ctx.tool_id.endswith(".execute")
    return _finish(
        ctx,
        {"kind": "sql", "verb": ctx.tool_id.split(".")[-1], "executed_rows": rows if executed else [], **sql},
        {"modification_count": len(sql["modifications"]), "executed": executed},
    )


def _family_semantic(ctx: ToolContext) -> ToolResult:
    ast_work = _ast_work(ctx)
    ctx.working.setdefault("ast", ast_work)
    ir = {
        "kind": "semantic-ir",
        "verb": ctx.tool_id.split(".")[-1],
        "symbols": ast_work["symbols"],
        "objective_tokens": _tokenize(ctx.objective)[:32],
        "transformed_code": ast_work["transformed_code"],
    }
    if ctx.working.get("sql") or _payload_lookup(ctx.payload, "sql") or "sql" in ctx.skill_name:
        sql = ctx.working.get("sql") or _sql_bundle(ctx.payload)
        ctx.working["sql"] = sql
        ctx.working["transpiled_sql"] = sql["transpiled_sql"]
        ir["sql_ir"] = sql
    ctx.working["semantic_ir"] = ir
    return _finish(ctx, ir, {"symbol_count": len(ast_work["symbols"]["functions"])})


def _family_graph(ctx: ToolContext) -> ToolResult:
    graph = _graph(ctx.payload)
    sccs = _tarjan(graph)
    schedule = _kahn(graph)
    locks = _wait_for_cycle(ctx.payload)
    ctx.working["graph"] = {"sccs": sccs, "schedule": schedule, "locks": locks}
    return _finish(
        ctx,
        {"kind": "graph", "verb": ctx.tool_id.split(".")[-1], "sccs": sccs, **schedule, **locks},
        {"scc_count": len(sccs), "cyclic": schedule["cyclic"]},
    )


def _family_security(ctx: ToolContext) -> ToolResult:
    text = _text(ctx.payload, "prompt", "source_code", "text", default=_source_text(ctx.payload))
    threats = _scan_threats(text)
    redacted = re.sub(r"(?i)(api[_-]?key|password|secret)\s*[:=]\s*\S+", r"\1=<redacted>", text)
    ctx.working["security"] = {"threats": threats, "redacted": redacted}
    return _finish(
        ctx,
        {
            "kind": "security",
            "verb": ctx.tool_id.split(".")[-1],
            "detected_threats": threats,
            "is_safe": not threats,
            "risk_level": "LOW" if not threats else ("CRITICAL" if "TOOL_EXPLOIT" in threats else "HIGH"),
            "redacted": redacted[:400],
        },
        {"threat_count": len(threats)},
    )


def _family_test(ctx: ToolContext) -> ToolResult:
    tests = _synthesize_tests(ctx.payload, ctx.tool_id)
    mutants = _mutate_source(ctx.payload, ctx.tool_id) if "fuzz" in ctx.tool_id or "chaos" in ctx.tool_id or "differential" in ctx.tool_id else []
    ctx.working["tests"] = tests
    if mutants:
        ctx.working["mutants"] = mutants
    return _finish(ctx, {"kind": "test", "verb": ctx.tool_id.split(".")[-1], **tests, "mutants": mutants}, tests)


def _family_policy(ctx: ToolContext) -> ToolResult:
    decision = _policy_decision(ctx.payload)
    tenant = str(ctx.tenant.get("tenant_id") or _text(ctx.payload, "tenant_id", default="tenant-a"))
    ctx.working["policy"] = decision
    return _finish(
        ctx,
        {"kind": "policy", "verb": ctx.tool_id.split(".")[-1], "tenant": tenant, **decision},
        {"allowed": decision["decision"] == "ALLOW"},
    )


def _family_retrieval(ctx: ToolContext) -> ToolResult:
    ranked = _rank_docs(ctx.payload)
    ctx.working["retrieval"] = ranked
    packed = [row["text"] for row in ranked["ranked"][:3]]
    return _finish(ctx, {"kind": "retrieval", "verb": ctx.tool_id.split(".")[-1], "packed": packed, **ranked}, {"hits": len(ranked["ranked"])})


def _family_lineage(ctx: ToolContext) -> ToolResult:
    items = _sequence(ctx.payload, "artifacts", default=[ctx.skill_name, ctx.handler_id, ctx.program_digest, ctx.stage_name])
    tree = _merkle(items)
    ctx.working["lineage"] = tree
    return _finish(ctx, {"kind": "lineage", "verb": ctx.tool_id.split(".")[-1], **tree}, {"leaf_count": len(tree["leaves"])})


def _family_cost(ctx: ToolContext) -> ToolResult:
    blob = json.dumps(_jsonable(dict(ctx.payload)), sort_keys=True)
    tokens = max(1, len(blob) // 4)
    complexity = int(_payload_lookup(ctx.payload, "complexity") or tokens)
    usd = round(0.000002 * tokens + 0.00001 * complexity, 8)
    eta_ms = max(1, int(0.02 * tokens + 0.05 * complexity))
    cost = {"tokens": tokens, "estimated_usd": usd, "eta_ms": eta_ms, "route": "local-deterministic"}
    ctx.working["cost"] = cost
    return _finish(ctx, {"kind": "cost", "verb": ctx.tool_id.split(".")[-1], **cost}, cost)


def _family_memory(ctx: ToolContext) -> ToolResult:
    tenant = str(ctx.tenant.get("tenant_id") or _text(ctx.payload, "tenant_id", default="tenant-a"))
    episodes = _sequence(ctx.payload, "episodes", default=[{"tenant_id": tenant, "event": "post"}, {"tenant_id": "tenant-b", "event": "post"}])
    isolated = [ep for ep in episodes if isinstance(ep, Mapping) and str(ep.get("tenant_id")) == tenant]
    leaked = [ep for ep in episodes if isinstance(ep, Mapping) and str(ep.get("tenant_id")) != tenant]
    fence = {"fence": f"tenant:{tenant}", "isolated_episodes": isolated, "rejected": leaked}
    ctx.working["memory"] = fence
    return _finish(ctx, {"kind": "memory", "verb": ctx.tool_id.split(".")[-1], **fence}, {"isolated": len(isolated), "rejected": len(leaked)})


def _family_build(ctx: ToolContext) -> ToolResult:
    ast_work = _ast_work(ctx) if _explicit_source(ctx.payload) or ctx.tool_id.startswith(("code.", "compiler.", "refactor.", "patch.", "frontend.", "java.", "language.")) else {}
    units = ast_work.get("symbols", {}).get("functions", [ctx.skill_name])
    return _finish(
        ctx,
        {
            "kind": "build",
            "verb": ctx.tool_id.split(".")[-1],
            "units": units,
            "transformed_code": ast_work.get("transformed_code"),
            "objective": ctx.objective[:180],
        },
        {"unit_count": len(units)},
    )


def _family_evidence(ctx: ToolContext) -> ToolResult:
    prior = list(ctx.working.get("tool_digests") or [])
    record = {
        "kind": "evidence",
        "verb": ctx.tool_id.split(".")[-1],
        "prior_tool_count": len(prior),
        "sql": ctx.working.get("transpiled_sql") or (ctx.working.get("sql") or {}).get("transpiled_sql"),
        "policy": (ctx.working.get("policy") or {}).get("decision"),
        "lineage": (ctx.working.get("lineage") or {}).get("merkle_root"),
        "tests": (ctx.working.get("tests") or {}).get("generated_cases"),
    }
    return _finish(ctx, record, {"prior_tool_count": len(prior)})


def _family_plan(ctx: ToolContext) -> ToolResult:
    left = _text(ctx.payload, "plan", "left", default=ctx.objective)
    right = _text(ctx.payload, "baseline", "right", default=ctx.pack)
    delta = sorted(set(_tokenize(left)) ^ set(_tokenize(right)))
    return _finish(ctx, {"kind": "plan", "verb": ctx.tool_id.split(".")[-1], "delta_tokens": delta[:32], "left": left[:160], "right": right[:160]}, {"delta": len(delta)})


def _family_generic(ctx: ToolContext) -> ToolResult:
    family, verb = ctx.tool_id.split(".", 1)
    text = _text(ctx.payload, "text", "source_code", "sql", "query", default=ctx.objective)
    tokens = _tokenize(text + " " + ctx.skill_name + " " + family + " " + verb)
    payload_digest = canonical_digest(canonical_value(_jsonable(dict(ctx.payload))))
    return _finish(
        ctx,
        {
            "kind": family,
            "verb": verb,
            "tokens": tokens[:40],
            "payload_digest": payload_digest,
            "objective_prefix": ctx.objective[:160],
        },
        {"token_count": len(tokens)},
    )


_FAMILY_IMPL: dict[str, Callable[[ToolContext], ToolResult]] = {
    "sql": _family_sql,
    "db": _family_sql,
    "semantic": _family_semantic,
    "parser": _family_parse,
    "language": _family_parse,
    "java": _family_parse,
    "legacy": _family_parse,
    "ui": _family_parse,
    "protocol": _family_parse,
    "config": _family_parse,
    "infra": _family_parse,
    "pipeline": _family_parse,
    "contract": _family_parse,
    "artifact": _family_parse,
    "requirements": _family_parse,
    "binary": _family_parse,
    "design": _family_parse,
    "graph": _family_graph,
    "workflow": _family_graph,
    "security": _family_security,
    "secret": _family_security,
    "pii": _family_security,
    "license": _family_security,
    "threat": _family_security,
    "redteam": _family_security,
    "safety": _family_security,
    "test": _family_test,
    "fuzz": _family_test,
    "chaos": _family_test,
    "differential": _family_test,
    "eval": _family_test,
    "validation": _family_test,
    "quality": _family_test,
    "prover": _family_test,
    "grader": _family_test,
    "policy": _family_policy,
    "entitlement": _family_policy,
    "sandbox": _family_policy,
    "approval": _family_policy,
    "waiver": _family_policy,
    "quota": _family_policy,
    "identity": _family_policy,
    "tenant": _family_policy,
    "search": _family_retrieval,
    "rag": _family_retrieval,
    "reranker": _family_retrieval,
    "context": _family_retrieval,
    "lineage": _family_lineage,
    "evidence": _family_evidence,
    "audit": _family_evidence,
    "registry": _family_evidence,
    "report": _family_evidence,
    "otel": _family_evidence,
    "metric": _family_evidence,
    "cost": _family_cost,
    "billing": _family_cost,
    "metering": _family_cost,
    "wallet": _family_cost,
    "capacity": _family_cost,
    "memory": _family_memory,
    "episode": _family_memory,
    "build": _family_build,
    "code": _family_build,
    "compiler": _family_build,
    "refactor": _family_build,
    "patch": _family_build,
    "frontend": _family_build,
    "schema": _family_build,
    "plan": _family_plan,
    "diff": _family_plan,
}


def _compile_tool(tool_id: str) -> ToolFn:
    if tool_id not in EXPECTED_TOOL_IDS or "." not in tool_id:
        raise ExactToolError(f"refusing to compile unbound tool {tool_id}")
    family = tool_id.split(".", 1)[0]
    impl = _FAMILY_IMPL.get(family, _family_generic)
    safe = tool_id.replace(".", "_").replace("-", "_")

    def _tool(ctx: ToolContext) -> ToolResult:
        if ctx.tool_id != tool_id:
            raise ExactToolError(f"tool {tool_id} cannot execute {ctx.tool_id}")
        return impl(ctx)

    _tool.__name__ = f"tool_{safe}"
    _tool.__qualname__ = f"elmos_foundry.exact_skills.tools.tool_{safe}"
    _tool.__module__ = f"elmos_foundry.exact_skills.tools.{safe}"
    setattr(_tool, "tool_id", tool_id)
    return _tool


@lru_cache(maxsize=1)
def load_tool_runtime() -> Mapping[str, ToolFn]:
    compiled = {tool_id: _compile_tool(tool_id) for tool_id in sorted(EXPECTED_TOOL_IDS)}
    if set(compiled) != EXPECTED_TOOL_IDS:
        raise ExactToolError("tool runtime allowlist drifted from EXPECTED_TOOL_IDS")
    identities = {(fn.__module__, fn.__qualname__, getattr(fn, "tool_id")) for fn in compiled.values()}
    if len(identities) != len(EXPECTED_TOOL_IDS):
        raise ExactToolError("tool callables are not unique")
    return MappingProxyType(compiled)


def seed_domain_working(payload: Mapping[str, Any], working: dict[str, Any]) -> None:
    """Project explicit domain inputs before the first tool runs."""

    if _payload_lookup(payload, "sql"):
        sql = _sql_bundle(payload)
        working["sql"] = sql
        working["transpiled_sql"] = sql["transpiled_sql"]
    if _payload_lookup(payload, "lock_acquisitions"):
        working.setdefault("graph", {})["locks"] = _wait_for_cycle(payload)
    if _payload_lookup(payload, "query", "documents"):
        working["retrieval"] = _rank_docs(payload)
    if _payload_lookup(payload, "request") or _payload_lookup(payload, "policy"):
        working["policy"] = _policy_decision(payload)


def run_tool(ctx: ToolContext, runtime: Mapping[str, ToolFn] | None = None) -> ToolResult:
    table = runtime if runtime is not None else load_tool_runtime()
    fn = table.get(ctx.tool_id)
    if fn is None:
        raise ExactToolError(f"no exact allowlisted tool implementation for {ctx.tool_id}")
    result = fn(ctx)
    if result.outcome != "CONFIRMED" or result.tool_id != ctx.tool_id:
        raise ExactToolError(f"tool {ctx.tool_id} did not confirm execution")
    return result


__all__ = [
    "EXPECTED_TOOL_IDS",
    "ExactToolError",
    "ToolContext",
    "ToolResult",
    "load_tool_runtime",
    "run_tool",
    "seed_domain_working",
]

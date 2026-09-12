"""Deterministic computational kernels used by the industrial Host Broker.

Each family runs a real algorithm on the invocation payload (or a typed
default corpus).  Outputs are input-digest dependent.  Invalid explicit
source fails closed instead of emitting a SUCCESS hash receipt.
"""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata
from typing import Any

from .families import KernelFamily, classify_skill


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


DEFAULT_AST_SOURCE = '''\
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
'''

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

DEFAULT_POLICY = {
    "subject": "payments-worker",
    "action": "ledger.post",
    "resource": "tenant-a/accounts",
    "rules": [
        {"effect": "ALLOW", "action": "ledger.post", "resource_prefix": "tenant-a/"},
        {"effect": "DENY", "action": "ledger.post", "resource_prefix": "tenant-b/"},
    ],
}

DEFAULT_LOCKS = [["account", "ledger"], ["ledger", "audit"], ["account", "audit"]]

DEFAULT_DEPENDENCIES = {
    "app": ["core", "sql"],
    "core": ["util"],
    "sql": ["util"],
    "util": [],
}

DEFAULT_LICENSES = {"app": "MIT", "core": "Apache-2.0", "sql": "BSD-3-Clause", "util": "MIT"}

DEFAULT_API = {
    "paths": {
        "/accounts/{id}": {"get": [200, 404], "post": [201, 400]},
        "/transfers": {"post": [202, 409, 422]},
    }
}

DEFAULT_ARTIFACTS = ["ledger.py", "locks.py", "schema.sql", "policy.json"]


@dataclass(frozen=True, slots=True)
class KernelResult:
    ok: bool
    family: str
    skill_name: str
    algorithm: str
    input_digest: str
    output_digest: str
    metrics: Mapping[str, Any]
    artifacts: Mapping[str, Any]
    error: str | None = None
    execution_mode: str = "LOCAL_DETERMINISTIC_KERNEL"
    broker_id: str = "elmos.foundry.industrial-local-host-broker"
    llm_required: bool = False
    pack: str = ""

    def materialize_output(self, output_name: str) -> dict[str, Any]:
        """Bind a declared skill output name to the real kernel evidence."""
        return {
            "name": output_name,
            "industrial": True,
            "ok": self.ok,
            "family": self.family,
            "algorithm": self.algorithm,
            "input_digest": self.input_digest,
            "output_digest": self.output_digest,
            "metrics": dict(self.metrics),
            "artifact": self.artifacts.get(output_name, dict(self.artifacts)),
            "error": self.error,
        }


def execute_kernel(
    skill_name: str,
    payload: Mapping[str, Any] | None,
    *,
    pack: str = "",
) -> KernelResult:
    """Execute the computational family for one skill."""
    body = dict(payload or {})
    family = classify_skill(skill_name, pack)
    input_digest = _digest({"skill": skill_name, "pack": pack, "payload": body, "family": family.value})

    try:
        artifacts, metrics, algorithm = _DISPATCH[family](skill_name, body)
    except KernelExecutionError as exc:
        return KernelResult(
            ok=False,
            family=family.value,
            skill_name=skill_name,
            algorithm=exc.algorithm,
            input_digest=input_digest,
            output_digest=_digest({"error": str(exc)}),
            metrics={},
            artifacts={},
            error=str(exc),
            pack=pack,
        )

    return KernelResult(
        ok=True,
        family=family.value,
        skill_name=skill_name,
        algorithm=algorithm,
        input_digest=input_digest,
        output_digest=_digest({"metrics": metrics, "artifacts": artifacts}),
        metrics=metrics,
        artifacts=artifacts,
        pack=pack,
    )


class KernelExecutionError(ValueError):
    def __init__(self, message: str, algorithm: str) -> None:
        super().__init__(message)
        self.algorithm = algorithm


def _source(payload: Mapping[str, Any]) -> str:
    source = payload.get("source_code")
    if source is None or source == "":
        return DEFAULT_AST_SOURCE
    if not isinstance(source, str):
        raise KernelExecutionError("source_code must be text", "ast.parse")
    return source


def _parse_or_fail(source: str, algorithm: str) -> ast.AST:
    try:
        return ast.parse(source)
    except SyntaxError as exc:
        if source is DEFAULT_AST_SOURCE:
            raise
        raise KernelExecutionError(f"invalid source_code: {exc}", algorithm) from exc


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


def _kernel_ast(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    source = _source(payload)
    tree = _parse_or_fail(source, "python_ast.cyclomatic_and_symbols")
    functions = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    node_types: dict[str, int] = defaultdict(int)
    for node in ast.walk(tree):
        node_types[type(node).__name__] += 1
    rename_map = payload.get("rename_map") if isinstance(payload.get("rename_map"), Mapping) else {}
    transformed = source
    changes = 0
    if rename_map:
        class Renamer(ast.NodeTransformer):
            def visit_Name(self, node: ast.Name) -> ast.AST:
                if node.id in rename_map:
                    nonlocal_changes[0] += 1
                    return ast.copy_location(ast.Name(id=str(rename_map[node.id]), ctx=node.ctx), node)
                return node

            def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
                if node.name in rename_map:
                    nonlocal_changes[0] += 1
                    node.name = str(rename_map[node.name])
                self.generic_visit(node)
                return node

        nonlocal_changes = [0]
        new_tree = Renamer().visit(tree)
        ast.fix_missing_locations(new_tree)
        transformed = ast.unparse(new_tree)
        changes = nonlocal_changes[0]
    metrics = {
        "function_count": len(functions),
        "class_count": len(classes),
        "cyclomatic_complexity": _cyclomatic(tree),
        "node_count": sum(node_types.values()),
        "changes_made": changes,
    }
    artifacts = {
        "symbols": {"functions": functions, "classes": classes},
        "node_types": dict(node_types),
        "transformed_code": transformed,
        "skill": skill_name,
    }
    return artifacts, metrics, "python_ast.cyclomatic_and_symbols"


def _kernel_sql(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    sql = str(payload.get("sql") or DEFAULT_SQL)
    source_dialect = str(payload.get("source_dialect", "mysql")).lower()
    target_dialect = str(payload.get("target_dialect", "postgresql")).lower()
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
    tables = re.findall(r"\bFROM\s+([`\"]?[A-Za-z_][A-Za-z0-9_]*[`\"]?)", transpiled, flags=re.IGNORECASE)
    metrics = {
        "modification_count": len(modifications),
        "table_count": len(tables),
        "sql_chars": len(transpiled),
    }
    artifacts = {
        "original_sql": sql,
        "transpiled_sql": transpiled,
        "modifications": modifications,
        "tables": tables,
        "skill": skill_name,
    }
    return artifacts, metrics, "sql.mysql_to_postgresql_dialect"


def _kernel_concurrency(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    lock_orders = payload.get("lock_acquisitions") or DEFAULT_LOCKS
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
    canonical_order = sorted({lock for seq in lock_orders for lock in seq}) if lock_orders else []
    metrics = {
        "locks_analyzed": len(wait_for),
        "has_deadlock_risk": has_cycle,
        "cycle_length": len(cycle),
    }
    artifacts = {
        "deadlock_cycle": cycle,
        "canonical_lock_order": canonical_order,
        "prevention": "acquire locks in lexicographic order",
        "skill": skill_name,
    }
    return artifacts, metrics, "concurrency.wait_for_graph_cycle"


def _kernel_security(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    text = str(payload.get("prompt") or payload.get("source_code") or payload.get("text") or DEFAULT_AST_SOURCE)
    lowered = text.lower()
    signatures = (
        ("IGNORE_PREVIOUS", r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|prompts|rules)"),
        ("SYSTEM_OVERRIDE", r"(?:you are now|act as|system prompt|jailbreak)"),
        ("SECRET_LEAK", r"(?:api[_-]?key|secret|password|BEGIN (?:RSA |OPENSSH )?PRIVATE KEY)"),
        ("TOOL_EXPLOIT", r"(?:rm -rf|cat /etc/passwd|subprocess|os\.system)"),
    )
    detected = [name for name, pattern in signatures if re.search(pattern, lowered)]
    metrics = {"threat_count": len(detected), "is_safe": not detected, "scanned_chars": len(text)}
    artifacts = {
        "detected_threats": detected,
        "risk_level": "LOW" if not detected else ("CRITICAL" if "TOOL_EXPLOIT" in detected else "HIGH"),
        "skill": skill_name,
    }
    return artifacts, metrics, "security.signature_scan"


def _kernel_dependency(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    dependencies = payload.get("dependencies") or DEFAULT_DEPENDENCIES
    licenses = payload.get("package_licenses") or DEFAULT_LICENSES
    graph = {str(pkg): [str(dep) for dep in (deps or [])] for pkg, deps in dict(dependencies).items()}
    visited: set[str] = set()
    stack: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        stack.add(node)
        path.append(node)
        for nxt in graph.get(node, ()):
            if nxt not in visited:
                dfs(nxt, path)
            elif nxt in stack:
                cycles.append(path[path.index(nxt) :] + [nxt])
        stack.remove(node)
        path.pop()

    for node in graph:
        if node not in visited:
            dfs(node, [])
    copyleft = [pkg for pkg, lic in dict(licenses).items() if "GPL" in str(lic).upper()]
    metrics = {
        "package_count": len(graph),
        "cycle_count": len(cycles),
        "copyleft_count": len(copyleft),
    }
    artifacts = {"cycles": cycles, "copyleft": copyleft, "skill": skill_name}
    return artifacts, metrics, "graph.dependency_cycle_and_license"


def _kernel_contract(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    source = _source(payload)
    tree = _parse_or_fail(source, "ast.contract_inference")
    invariants: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for arg in node.args.args:
            if arg.arg in {"self", "cls"}:
                continue
            anno = ast.unparse(arg.annotation) if arg.annotation else ""
            if anno in {"int", "float"}:
                invariants.append(
                    {
                        "target": node.name,
                        "variable": arg.arg,
                        "expression": f"{arg.arg} is finite {anno}",
                    }
                )
            if arg.arg in {"amount", "qty", "count"}:
                invariants.append(
                    {
                        "target": node.name,
                        "variable": arg.arg,
                        "expression": f"{arg.arg} > 0",
                    }
                )
        if node.returns:
            invariants.append(
                {
                    "target": node.name,
                    "variable": "return",
                    "expression": f"returns {ast.unparse(node.returns)}",
                }
            )
    metrics = {"invariant_count": len(invariants), "coverage": 1.0 if invariants else 0.0}
    artifacts = {"invariants": invariants, "skill": skill_name}
    return artifacts, metrics, "ast.precondition_inference"


def _tokenize(text: str) -> list[str]:
    return [tok for tok in re.findall(r"[a-z0-9_]+", text.lower()) if len(tok) > 1]


def _kernel_retrieval(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    query = str(payload.get("query") or "fencing token deadlock lock order")
    documents = list(payload.get("documents") or DEFAULT_DOCS)
    q_tokens = set(_tokenize(query))
    ranked: list[dict[str, Any]] = []
    for idx, doc in enumerate(documents):
        tokens = set(_tokenize(str(doc)))
        overlap = len(q_tokens & tokens)
        union = len(q_tokens | tokens) or 1
        ranked.append({"index": idx, "score": overlap / union, "overlap": overlap, "text": doc})
    ranked.sort(key=lambda row: (-row["score"], row["index"]))
    metrics = {"document_count": len(documents), "top_score": ranked[0]["score"] if ranked else 0.0}
    artifacts = {"ranked": ranked[:5], "query_tokens": sorted(q_tokens), "skill": skill_name}
    return artifacts, metrics, "retrieval.jaccard_overlap_rank"


def _kernel_test(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    source = _source(payload)
    tree = _parse_or_fail(source, "ast.test_synthesis")
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
    metrics = {"generated_cases": len(cases) * 2, "functions_covered": len(cases)}
    artifacts = {"cases": cases, "skill": skill_name}
    return artifacts, metrics, "ast.positive_negative_test_synthesis"


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


def _kernel_graph(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    raw = payload.get("graph") or DEFAULT_GRAPH
    graph = {str(k): [str(v) for v in (vals or [])] for k, vals in dict(raw).items()}
    components = _tarjan(graph)
    cyclic = [comp for comp in components if len(comp) > 1]
    metrics = {"node_count": len(graph), "scc_count": len(components), "cyclic_scc": len(cyclic)}
    artifacts = {"sccs": components, "cyclic": cyclic, "skill": skill_name}
    return artifacts, metrics, "graph.tarjan_scc"


def _kernel_policy(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    request = dict(payload.get("request") or DEFAULT_POLICY)
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
    metrics = {"decision": decision, "matched": matched is not None}
    artifacts = {"decision": decision, "matched_rule": matched, "skill": skill_name}
    return artifacts, metrics, "policy.allow_deny_prefix"


def _kernel_cost(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    blob = json.dumps(payload, sort_keys=True, default=str)
    tokens = max(1, len(blob) // 4)
    complexity = int(payload.get("complexity") or tokens)
    usd = round(0.000002 * tokens + 0.00001 * complexity, 8)
    eta_ms = max(1, int(0.02 * tokens + 0.05 * complexity))
    metrics = {"tokens": tokens, "estimated_usd": usd, "eta_ms": eta_ms}
    artifacts = {"route": "local-deterministic", "skill": skill_name}
    return artifacts, metrics, "cost.token_complexity_estimator"


def _kernel_lineage(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    artifacts_in = [str(item) for item in (payload.get("artifacts") or DEFAULT_ARTIFACTS)]
    leaves = [_digest(item) for item in artifacts_in]
    layer = list(leaves)
    while len(layer) > 1:
        nxt: list[str] = []
        for idx in range(0, len(layer), 2):
            pair = layer[idx] if idx + 1 >= len(layer) else layer[idx] + layer[idx + 1]
            nxt.append(_digest(pair))
        layer = nxt
    root = layer[0] if layer else _digest("")
    metrics = {"leaf_count": len(leaves), "merkle_root": root}
    artifacts = {"leaves": leaves, "merkle_root": root, "skill": skill_name}
    return artifacts, metrics, "lineage.merkle_tree"


def _kernel_normalize(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    text = str(payload.get("text") or payload.get("source_code") or json.dumps(payload or {"skill": skill_name}, sort_keys=True))
    normalized = unicodedata.normalize("NFC", text).strip()
    tokens = _tokenize(normalized)
    metrics = {"token_count": len(tokens), "char_count": len(normalized)}
    artifacts = {"normalized": normalized, "tokens": tokens[:64], "skill": skill_name}
    return artifacts, metrics, "unicode.nfc_tokenize"


def _kernel_fuzz(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    source = _source(payload)
    tree = _parse_or_fail(source, "ast.constant_mutation")
    mutants: list[str] = []

    class Mutator(ast.NodeTransformer):
        def visit_Constant(self, node: ast.Constant) -> ast.AST:
            if isinstance(node.value, bool):
                return ast.copy_location(ast.Constant(value=not node.value), node)
            if isinstance(node.value, int):
                return ast.copy_location(ast.Constant(value=node.value + 1), node)
            if isinstance(node.value, (float,)):
                return ast.copy_location(ast.Constant(value=node.value * -1), node)
            return node

    mutant_tree = Mutator().visit(ast.parse(source))
    ast.fix_missing_locations(mutant_tree)
    mutants.append(ast.unparse(mutant_tree))
    metrics = {"mutant_count": len(mutants), "source_nodes": sum(1 for _ in ast.walk(tree))}
    artifacts = {"mutants": mutants, "relations": ["negate_bool", "off_by_one"], "skill": skill_name}
    return artifacts, metrics, "ast.constant_mutation"


def _kernel_api(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    spec = dict(payload.get("openapi") or payload.get("paths") or DEFAULT_API)
    paths = spec.get("paths", spec)
    operations = 0
    status_codes: list[int] = []
    missing_error_paths: list[str] = []
    for path, methods in dict(paths).items():
        if not isinstance(methods, Mapping):
            continue
        for method, codes in methods.items():
            operations += 1
            code_list = [int(c) for c in codes] if isinstance(codes, Sequence) and not isinstance(codes, (str, bytes)) else []
            status_codes.extend(code_list)
            if not any(code >= 400 for code in code_list):
                missing_error_paths.append(f"{method.upper()} {path}")
    metrics = {
        "operation_count": operations,
        "status_code_count": len(status_codes),
        "missing_error_contracts": len(missing_error_paths),
    }
    artifacts = {"missing_error_paths": missing_error_paths, "skill": skill_name}
    return artifacts, metrics, "api.error_contract_coverage"


def _kernel_dataflow(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    source = _source(payload)
    tree = _parse_or_fail(source, "ast.def_use")
    defs: dict[str, int] = defaultdict(int)
    uses: dict[str, int] = defaultdict(int)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defs[node.id] += 1
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            uses[node.id] += 1
    unused = sorted(name for name in defs if uses.get(name, 0) == 0 and not name.startswith("_"))
    metrics = {"def_count": sum(defs.values()), "use_count": sum(uses.values()), "unused": len(unused)}
    artifacts = {"defs": dict(defs), "uses": dict(uses), "unused": unused, "skill": skill_name}
    return artifacts, metrics, "ast.def_use_chains"


def _kernel_schedule(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    graph = dict(payload.get("dag") or DEFAULT_GRAPH)
    edges = {str(k): [str(v) for v in (vals or [])] for k, vals in graph.items()}
    indegree: dict[str, int] = {node: 0 for node in edges}
    for node, dests in edges.items():
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
    metrics = {
        "task_count": len(indegree),
        "critical_path": 0 if cyclic else max(longest.values(), default=0),
        "cyclic": cyclic,
    }
    artifacts = {"topo_order": order, "skill": skill_name}
    return artifacts, metrics, "dag.kahn_critical_path"


def _kernel_memory(skill_name: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    tenant = str(payload.get("tenant_id") or "tenant-a")
    episodes = list(payload.get("episodes") or [{"tenant_id": tenant, "event": "post"}, {"tenant_id": "tenant-b", "event": "post"}])
    isolated = [ep for ep in episodes if str(ep.get("tenant_id")) == tenant]
    leaked = [ep for ep in episodes if str(ep.get("tenant_id")) != tenant]
    metrics = {"isolated_count": len(isolated), "rejected_cross_tenant": len(leaked)}
    artifacts = {
        "fence": f"tenant:{tenant}",
        "isolated_episodes": isolated,
        "rejected": leaked,
        "skill": skill_name,
    }
    return artifacts, metrics, "memory.tenant_fence_filter"


_DISPATCH = {
    KernelFamily.AST_TRANSFORM: _kernel_ast,
    KernelFamily.SQL_DIALECT: _kernel_sql,
    KernelFamily.CONCURRENCY_WFG: _kernel_concurrency,
    KernelFamily.SECURITY_SCAN: _kernel_security,
    KernelFamily.DEPENDENCY_GRAPH: _kernel_dependency,
    KernelFamily.CONTRACT_INFERENCE: _kernel_contract,
    KernelFamily.RETRIEVAL_RANK: _kernel_retrieval,
    KernelFamily.TEST_SYNTHESIS: _kernel_test,
    KernelFamily.GRAPH_REACHABILITY: _kernel_graph,
    KernelFamily.POLICY_EVAL: _kernel_policy,
    KernelFamily.COST_ROUTE: _kernel_cost,
    KernelFamily.LINEAGE_HASH: _kernel_lineage,
    KernelFamily.NORMALIZATION: _kernel_normalize,
    KernelFamily.FUZZ_MUTATION: _kernel_fuzz,
    KernelFamily.API_CONTRACT: _kernel_api,
    KernelFamily.DATAFLOW: _kernel_dataflow,
    KernelFamily.SCHEDULE_DAG: _kernel_schedule,
    KernelFamily.MEMORY_ISOLATION: _kernel_memory,
}

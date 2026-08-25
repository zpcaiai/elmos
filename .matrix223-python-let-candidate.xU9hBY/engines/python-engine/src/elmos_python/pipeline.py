from __future__ import annotations

import ast
import json
from pathlib import Path


class PipelineAndNotebookAnalyzer:
    def analyze(self, root: Path) -> dict[str, object]:
        notebooks = []
        findings: set[str] = set()
        nodes: set[str] = set()
        edges: list[dict[str, str]] = []
        for path in sorted(root.rglob("*.ipynb")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                code_cells = [cell for cell in data.get("cells", []) if cell.get("cell_type") == "code"]
                counts = [cell.get("execution_count") for cell in code_cells]
                clean = all(isinstance(value, int) for value in counts) and counts == sorted(counts)
                if not clean:
                    findings.add("NOTEBOOK_HIDDEN_STATE")
                definitions: dict[str, int] = {}
                for index, cell in enumerate(code_cells):
                    source = "".join(cell.get("source", []))
                    try:
                        tree = ast.parse(source)
                    except SyntaxError:
                        findings.add("NOTEBOOK_CELL_SYNTAX_ERROR")
                        continue
                    used = {
                        node.id
                        for node in ast.walk(tree)
                        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                    }
                    defined = {
                        node.id
                        for node in ast.walk(tree)
                        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
                    }
                    for name in sorted(used):
                        if name in definitions:
                            edges.append(
                                {"source": f"cell-{definitions[name]}", "target": f"cell-{index}", "kind": "VARIABLE"}
                            )
                    definitions.update({name: index for name in defined})
                notebooks.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "cleanKernelReady": clean,
                        "cellCount": len(code_cells),
                        "cleanKernelExecution": "NOT_RUN_REQUIRES_NOTEBOOK_RUNNER",
                    }
                )
            except OSError, json.JSONDecodeError:
                findings.add("NOTEBOOK_STATE_UNRESOLVED")
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8", errors="replace")
            relative = path.relative_to(root).as_posix()
            if any(marker in source for marker in ("DAG(", "@app.task", "SparkSession", "@task")):
                nodes.add(relative)
            if any(marker in source for marker in ("send_email", "requests.post", "delete(", "publish(")):
                findings.add("PIPELINE_SIDE_EFFECT_REQUIRES_SHADOW")
        return {
            "nodes": sorted(nodes),
            "edges": edges,
            "notebooks": notebooks,
            "requiredContracts": ["SCHEMA", "KEY", "ORDERING", "NULL", "TIMEZONE", "FRESHNESS", "QUALITY"],
            "requiredOperationalValidation": [
                "SCHEDULE",
                "RETRY",
                "BACKFILL",
                "IDEMPOTENCY",
                "PARTIAL_FAILURE",
                "SIDE_EFFECT_SHADOW",
            ],
            "findings": sorted(findings),
        }

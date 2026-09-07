"""Independent checks for compiled Skill identity, candidates, and DAG closure."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tooling/integrate_knowledge_skill_model_foundry_skills.py"
MODULE_NAME = "_knowledge_skill_model_foundry_importer_under_test"


def load_tool():
    existing = sys.modules.get(MODULE_NAME)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(MODULE_NAME, TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Foundry importer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def audited_package(tool):
    result = getattr(tool, "_FOCUSED_TEST_AUDIT", None)
    if result is None:
        result = tool.audit_archive(tool.resolve_archive())
        setattr(tool, "_FOCUSED_TEST_AUDIT", result)
    return result


class SkillCatalogDagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load_tool()
        cls.catalog = audited_package(cls.tool).compiled_catalog

    def test_exact_pack_counts_and_meta_candidate_closure(self) -> None:
        atomic = self.catalog["atomic_skills"]
        observed = Counter(row["pack"] for row in atomic)
        self.assertEqual(dict(observed), dict(self.tool.EXPECTED_PACK_COUNTS))
        atomic_by_pack: dict[str, list[str]] = defaultdict(list)
        for row in atomic:
            atomic_by_pack[row["pack"]].append(row["name"])
        for meta in self.catalog["meta_skills"]:
            self.assertEqual(meta["candidates"], sorted(atomic_by_pack[meta["pack"]]))

    def test_dependency_graph_is_complete_and_acyclic(self) -> None:
        atomic = self.catalog["atomic_skills"]
        names = {row["name"] for row in atomic}
        dependencies = {row["name"]: row["dependencies"] for row in atomic}
        self.assertEqual(sum(map(len, dependencies.values())), 9_090)
        self.assertFalse(
            [
                (name, dependency)
                for name, values in dependencies.items()
                for dependency in values
                if dependency not in names
            ]
        )
        self.assertFalse([name for name, values in dependencies.items() if name in values])

        indegree = {name: len(dependencies[name]) for name in names}
        outgoing: dict[str, list[str]] = defaultdict(list)
        for name, values in dependencies.items():
            for dependency in values:
                outgoing[dependency].append(name)
        queue = deque(sorted(name for name, degree in indegree.items() if degree == 0))
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for successor in outgoing[node]:
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    queue.append(successor)
        self.assertEqual(visited, 1_310)

    def test_dag_validator_fails_closed(self) -> None:
        with self.assertRaisesRegex(self.tool.IntegrationError, "unresolved"):
            self.tool._check_dag({"a"}, {"a": ["missing"]})
        with self.assertRaisesRegex(self.tool.IntegrationError, "self dependencies"):
            self.tool._check_dag({"a"}, {"a": ["a"]})
        with self.assertRaisesRegex(self.tool.IntegrationError, "cycle"):
            self.tool._check_dag({"a", "b"}, {"a": ["b"], "b": ["a"]})


if __name__ == "__main__":
    unittest.main()

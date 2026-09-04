"""Bootstrap check: the drawn control flow must match the source it came from.

The C1 acceptance bar is "the diagram agrees with a human reading the code, and
a missing branch or loop must be caught by a test".  A hand-written fixture
cannot carry that bar on its own: it only proves the walk handles the shapes
somebody already thought of.  So the corpus here is **this engine's own
source** -- every function it defines -- and the expectation is recomputed from
``ast`` by a walker written to reader semantics, independently of the walker
under test.

Reader semantics, stated so the two walkers can be compared:

* every ``if``/``elif`` test is one branch point;
* every ``case`` of a ``match`` is one branch point, because a reader has to
  decide whether it matches;
* every ``for``/``while`` header is one loop;
* a nested ``def``/``class`` body is *not* part of this function -- it is a
  separate function with its own diagram.

``test_the_conservation_check_fails_when_a_branch_goes_missing`` is the
negative control: it feeds the same assertion a graph with one decision node
deleted and requires it to fail.  Without that, a conservation check that
happened to compare two constants would pass forever.
"""

from __future__ import annotations

import ast
import unittest
from collections import Counter
from pathlib import Path
from typing import ClassVar

from elmos_project_intelligence.flowgraph import function_control_flow
from elmos_project_intelligence.runtime import dispatch_skill


SOURCE_ROOT = Path(__file__).resolve().parent.parent / "src" / "elmos_project_intelligence"

#: The corpus must not be allowed to quietly shrink to nothing: a conservation
#: test over zero functions passes and proves nothing.
MINIMUM_FUNCTIONS_CHECKED = 150


def _expected(body: list[ast.stmt], acc: dict[str, int]) -> dict[str, int]:
    """Count branch points and loops the way a reader of the source counts them."""

    for statement in body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(statement, ast.If):
            acc["branch"] += 1
            _expected(statement.body, acc)
            _expected(statement.orelse, acc)
        elif isinstance(statement, ast.Match):
            for case in statement.cases:
                acc["branch"] += 1
                _expected(case.body, acc)
        elif isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
            acc["loop"] += 1
            _expected(statement.body, acc)
            _expected(statement.orelse, acc)
        elif isinstance(statement, (ast.Try, ast.TryStar)):
            _expected(statement.body, acc)
            for handler in statement.handlers:
                _expected(handler.body, acc)
            _expected(statement.orelse, acc)
            _expected(statement.finalbody, acc)
        elif isinstance(statement, (ast.With, ast.AsyncWith)):
            _expected(statement.body, acc)
        else:
            # Any other statement that carries a nested body would hide branches
            # from the walk under test.  Record it so the failure names the
            # construct instead of appearing as an unexplained count drift.
            for field in ("body", "orelse", "finalbody"):
                nested = getattr(statement, field, None)
                if isinstance(nested, list) and nested and isinstance(nested[0], ast.stmt):
                    acc["unwalked"] += 1
                    _expected(nested, acc)
    return acc


def _observed(graph: dict[str, object]) -> dict[str, int]:
    nodes = graph["nodes"]
    edges = graph["edges"]
    assert isinstance(nodes, list) and isinstance(edges, list)
    kinds = Counter(str(node["kind"]) for node in nodes)
    edge_kinds = Counter(str(edge["kind"]) for edge in edges)
    return {
        "branch": kinds["decision"],
        "loop": kinds["loop"],
        "branch_edges": edge_kinds["branch"],
        "start": kinds["start"],
        "end": kinds["end"],
    }


def _unique_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Return functions whose name is unique in the module.

    ``function_control_flow`` selects by name, so a duplicated name would make
    "the function I walked" and "the function it drew" two different things and
    the comparison meaningless.  Duplicates get their own test.
    """

    found: list[ast.FunctionDef | ast.AsyncFunctionDef] = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    seen = Counter(node.name for node in found)
    return [node for node in found if seen[node.name] == 1]


class ControlFlowConservationTests(unittest.TestCase):
    def test_every_branch_and_loop_in_this_engine_is_drawn(self) -> None:
        checked = 0
        files = sorted(SOURCE_ROOT.glob("*.py"))
        self.assertTrue(files, f"no source files found under {SOURCE_ROOT}")
        for path in files:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
            for function in _unique_functions(tree):
                expected = _expected(
                    function.body, {"branch": 0, "loop": 0, "unwalked": 0}
                )
                graph = function_control_flow(text, function.name)
                self.assertIsNotNone(graph, f"{path.name} did not parse")
                assert graph is not None
                observed = _observed(graph)
                where = f"{path.name}:{function.lineno} {function.name}"
                with self.subTest(function=where):
                    self.assertEqual(
                        expected["unwalked"],
                        0,
                        f"{where}: a statement with a nested body is not walked, "
                        f"so branches inside it cannot be drawn",
                    )
                    self.assertEqual(
                        observed["branch"],
                        expected["branch"],
                        f"{where}: source has {expected['branch']} branch points, "
                        f"diagram drew {observed['branch']} decisions",
                    )
                    self.assertEqual(
                        observed["loop"],
                        expected["loop"],
                        f"{where}: source has {expected['loop']} loops, "
                        f"diagram drew {observed['loop']} loop nodes",
                    )
                    self.assertEqual(
                        observed["branch_edges"],
                        2 * expected["branch"],
                        f"{where}: every branch point owes exactly two branch edges",
                    )
                    self.assertEqual(observed["start"], 1, f"{where}: one start node")
                    self.assertEqual(observed["end"], 1, f"{where}: one end node")
                checked += 1
        self.assertGreaterEqual(
            checked,
            MINIMUM_FUNCTIONS_CHECKED,
            f"only {checked} functions checked; the corpus has shrunk and this "
            f"test no longer proves what it claims",
        )

    def test_the_conservation_check_fails_when_a_branch_goes_missing(self) -> None:
        """Negative control: the assertion above is not constant-true.

        A graph identical to the real one except for one deleted decision node
        must be rejected.  If this passes, the check above proves nothing.
        """

        source = "def f(x):\n    if x:\n        return 1\n    return 2\n"
        graph = function_control_flow(source, "f")
        assert graph is not None
        nodes = list(graph["nodes"])
        self.assertEqual(_observed({"nodes": nodes, "edges": graph["edges"]})["branch"], 1)
        lossy = [node for node in nodes if node["kind"] != "decision"]
        self.assertEqual(
            _observed({"nodes": lossy, "edges": graph["edges"]})["branch"], 0
        )
        with self.assertRaises(AssertionError):
            self.assertEqual(
                _observed({"nodes": lossy, "edges": graph["edges"]})["branch"], 1
            )

    def test_a_loop_that_goes_missing_is_caught_too(self) -> None:
        source = "def f(xs):\n    for x in xs:\n        g(x)\n    return 1\n"
        graph = function_control_flow(source, "f")
        assert graph is not None
        self.assertEqual(_observed(graph)["loop"], 1)
        nodes = [node for node in graph["nodes"] if node["kind"] != "loop"]
        with self.assertRaises(AssertionError):
            self.assertEqual(
                _observed({"nodes": nodes, "edges": graph["edges"]})["loop"], 1
            )


class MatchStatementTests(unittest.TestCase):
    #   match value
    #     case 0                -> decision 1
    #     case [x, y] if x > y  -> decision 2
    #     case _                -> decision 3
    # Each decision owes a true edge (into its case body) and a false edge
    # (to the next case, or to the merge for the last one): 6 branch edges.
    SOURCE = (
        "def classify(value):\n"
        "    match value:\n"
        "        case 0:\n"
        "            name = 'zero'\n"
        "        case [x, y] if x > y:\n"
        "            name = 'descending'\n"
        "        case _:\n"
        "            name = 'other'\n"
        "    return name\n"
    )

    def test_each_case_is_its_own_decision(self) -> None:
        graph = function_control_flow(self.SOURCE, "classify")
        assert graph is not None
        decisions = [n for n in graph["nodes"] if n["kind"] == "decision"]
        self.assertEqual(len(decisions), 3)
        branch_edges = [e for e in graph["edges"] if e["kind"] == "branch"]
        self.assertEqual(len(branch_edges), 6)

    def test_a_case_guard_is_part_of_the_label(self) -> None:
        """Two cases with the same pattern and different guards are different
        branches; a label that dropped the guard would draw them identically."""

        graph = function_control_flow(self.SOURCE, "classify")
        assert graph is not None
        labels = [n["label"] for n in graph["nodes"] if n["kind"] == "decision"]
        self.assertTrue(
            any("if x > y" in str(label) for label in labels),
            f"guard missing from {labels}",
        )

    def test_cases_are_chained_not_fanned(self) -> None:
        """``match`` tries a case only when the earlier cases failed."""

        graph = function_control_flow(self.SOURCE, "classify")
        assert graph is not None
        decisions = [n["id"] for n in graph["nodes"] if n["kind"] == "decision"]
        false_edges = {
            (e["source"], e["target"])
            for e in graph["edges"]
            if e["kind"] == "branch" and e.get("label") == "false"
        }
        self.assertIn((decisions[0], decisions[1]), false_edges)
        self.assertIn((decisions[1], decisions[2]), false_edges)


class ExceptStarTests(unittest.TestCase):
    SOURCE = (
        "def f():\n"
        "    try:\n"
        "        risky()\n"
        "    except* ValueError:\n"
        "        recover()\n"
        "    return 1\n"
    )

    def test_an_except_star_handler_is_drawn(self) -> None:
        graph = function_control_flow(self.SOURCE, "f")
        assert graph is not None
        exception_edges = [
            e for e in graph["edges"] if e["kind"] == "exception"
        ]
        self.assertTrue(
            any("ValueError" in str(e.get("label", "")) for e in exception_edges),
            f"no handler edge in {exception_edges}",
        )


class DuplicateDefinitionTests(unittest.TestCase):
    SOURCE = (
        "class A:\n"
        "    def run(self):\n"
        "        if 1:\n"
        "            pass\n"
        "class B:\n"
        "    def run(self):\n"
        "        while 1:\n"
        "            pass\n"
    )

    def test_an_ambiguous_name_is_reported_rather_than_silently_resolved(self) -> None:
        """One real module in this repository defines ``__init__`` thirteen
        times.  Asking for a diagram of it must not hand back one of the
        thirteen with nothing said."""

        graph = function_control_flow(self.SOURCE, "run")
        assert graph is not None
        diagnostics = graph["diagnostics"]
        assert isinstance(diagnostics, list)
        self.assertEqual(len(diagnostics), 1)
        self.assertIn("2 definitions named run", diagnostics[0])
        self.assertIn("lines 2, 6", diagnostics[0])
        self.assertIn("line 2", diagnostics[0])

    def test_an_unambiguous_name_reports_nothing(self) -> None:
        graph = function_control_flow("def only():\n    return 1\n", "only")
        assert graph is not None
        self.assertEqual(graph["diagnostics"], [])


class PresentationEdgeVocabularyTests(unittest.TestCase):
    """The deck must read the same edges the Diagram Spec engine accepts.

    ``compile_diagram_spec`` has always accepted both ``from``/``to`` and the
    canonical ``source``/``target``.  ``generate_presentation`` read only
    ``from``/``to``, so an end-to-end run that compiled a spec first and then
    asked for a deck produced a Relationships slide of ``None -> None`` -- a
    wrong slide, produced silently, with the handler still reporting success.
    """

    NODES: ClassVar[list[dict[str, object]]] = [
        {"id": "a", "kind": "component", "label": "a"},
        {"id": "b", "kind": "component", "label": "b"},
    ]

    def _relationships(self, edges: list[dict[str, object]]) -> list[str]:
        result = dispatch_skill(
            "elmos-presentation-generation",
            {
                "schema_version": "1.0",
                "request_id": "edge-vocabulary",
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "revision": "rev-1",
                "inputs": {"revision": "rev-1", "nodes": self.NODES, "edges": edges},
            },
        )
        self.assertEqual(result["state"], "PARTIAL_LOCAL_EXECUTED")
        slides = result["outputs"]["slides"]
        relationships = [s for s in slides if s["title"] == "Relationships"]
        self.assertEqual(len(relationships), 1)
        return [str(bullet) for bullet in relationships[0]["bullets"]]

    def test_canonical_source_target_edges_are_read(self) -> None:
        bullets = self._relationships(
            [{"id": "a-b", "source": "a", "target": "b", "kind": "imports"}]
        )
        self.assertEqual(bullets, ["a -> b"])
        for bullet in bullets:
            self.assertNotIn("None", bullet)

    def test_legacy_from_to_edges_still_work(self) -> None:
        bullets = self._relationships(
            [{"id": "a-b", "from": "a", "to": "b", "kind": "imports"}]
        )
        self.assertEqual(bullets, ["a -> b"])

    def test_the_handler_still_reports_that_it_wrote_no_pptx(self) -> None:
        """The contract boundary this fix must not move."""

        result = dispatch_skill(
            "elmos-presentation-generation",
            {
                "schema_version": "1.0",
                "request_id": "edge-vocabulary",
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "revision": "rev-1",
                "inputs": {
                    "revision": "rev-1",
                    "nodes": self.NODES,
                    "edges": [{"source": "a", "target": "b", "kind": "imports"}],
                },
            },
        )
        self.assertIs(result["outputs"]["pptx_generated"], False)
        self.assertEqual(
            sorted(result["outputs"]), ["digest", "pptx_generated", "slides"]
        )


class DiagramTitleTests(unittest.TestCase):
    """A compiled spec must be able to say what it is a diagram *of*.

    ``title`` is a documented top-level property of
    ``schemas/diagram-spec.schema.json`` and ``layout_diagram`` already reads
    it, but ``compile_diagram_spec`` never emitted it, so every diagram that
    reached a report or a deck through dispatch was headed "Diagram".
    """

    def _spec(self, extra: dict[str, object]) -> dict[str, object]:
        result = dispatch_skill(
            "elmos-diagram-spec-engine",
            {
                "schema_version": "1.0",
                "request_id": "title",
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "revision": "rev-1",
                "inputs": {
                    "revision": "rev-1",
                    "nodes": [{"id": "a", "kind": "component", "label": "a"}],
                    "edges": [],
                    **extra,
                },
            },
        )
        self.assertEqual(result["state"], "LOCAL_EXECUTED")
        return dict(result["outputs"]["diagram_spec"])

    def test_a_supplied_title_reaches_the_compiled_spec(self) -> None:
        spec = self._spec({"title": "translate control flow"})
        self.assertEqual(spec.get("title"), "translate control flow")

    def test_a_spec_without_a_title_stays_untitled(self) -> None:
        self.assertNotIn("title", self._spec({}))

    def test_the_title_changes_the_spec_digest(self) -> None:
        """Two specs that draw differently must not share an identity."""

        untitled = self._spec({})
        titled = self._spec({"title": "translate control flow"})
        self.assertNotEqual(untitled, titled)


class EdgeVocabularyAcrossHandlersTests(unittest.TestCase):
    """Every handler that reads an edge must read *both* spellings.

    ``compile_diagram_spec`` accepted ``source``/``target`` and ``from``/``to``
    from the start, so a pipeline that compiles a spec and then feeds the same
    edges to another handler is an ordinary thing to do.  Three handlers read
    only ``from``/``to``.  Two of them printed ``None``; ``analyze_impact``
    did something worse -- it answered "nothing else is affected", correctly
    shaped, with no rejection and no warning.  That is the silent-zero family.
    """

    NODES: ClassVar[list[dict[str, object]]] = [
        {"id": "a", "kind": "component", "label": "a"},
        {"id": "b", "kind": "component", "label": "b"},
    ]
    #: ``a`` imports ``b``, spelled both ways.  Same graph, same meaning.
    CANONICAL: ClassVar[list[dict[str, object]]] = [
        {"id": "a-b", "source": "a", "target": "b", "kind": "imports"}
    ]
    LEGACY: ClassVar[list[dict[str, object]]] = [
        {"id": "a-b", "from": "a", "to": "b", "kind": "imports"}
    ]

    def _dispatch(self, skill: str, inputs: dict[str, object]) -> dict[str, object]:
        result = dispatch_skill(
            skill,
            {
                "schema_version": "1.0",
                "request_id": "edge-vocabulary",
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "revision": "rev-1",
                "inputs": {"revision": "rev-1", "nodes": self.NODES, **inputs},
            },
        )
        self.assertNotEqual(result["state"], "BLOCKED", result)
        return dict(result["outputs"])

    def _impacted(self, edges: list[dict[str, object]]) -> list[str]:
        outputs = self._dispatch(
            "elmos-impact-analysis", {"edges": edges, "changed_paths": ["b"]}
        )
        return [str(item) for item in outputs["impacted"]]

    def test_impact_analysis_follows_canonical_edges(self) -> None:
        """``b`` changed and ``a`` imports ``b``, so ``a`` is impacted.

        Reading only from/to made this return ``['b']`` -- a wrong answer that
        looks exactly like a right one.
        """

        self.assertEqual(self._impacted(self.CANONICAL), ["a", "b"])

    def test_impact_analysis_follows_legacy_edges(self) -> None:
        self.assertEqual(self._impacted(self.LEGACY), ["a", "b"])

    def test_both_spellings_of_the_same_graph_give_the_same_answer(self) -> None:
        """The property that actually matters: spelling must not change meaning."""

        self.assertEqual(self._impacted(self.CANONICAL), self._impacted(self.LEGACY))

    def _relationship_lines(self, edges: list[dict[str, object]]) -> list[str]:
        outputs = self._dispatch("elmos-architecture-documentation", {"edges": edges})
        return [
            line
            for line in str(outputs["content"]).splitlines()
            if "->" in line
        ]

    def test_architecture_document_renders_canonical_edges(self) -> None:
        lines = self._relationship_lines(self.CANONICAL)
        self.assertEqual(lines, ["- a -> b (imports)"])

    def test_architecture_document_renders_legacy_edges(self) -> None:
        self.assertEqual(self._relationship_lines(self.LEGACY), ["- a -> b (imports)"])

    def test_no_handler_prints_none_for_an_endpoint(self) -> None:
        for edges, name in ((self.CANONICAL, "canonical"), (self.LEGACY, "legacy")):
            with self.subTest(vocabulary=name):
                for line in self._relationship_lines(edges):
                    self.assertNotIn("None", line)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

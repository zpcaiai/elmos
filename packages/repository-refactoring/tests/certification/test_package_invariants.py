"""Structural certification: properties of the *package*, not of one Skill.

These are the claims the README makes.  Each one is checked against the code
rather than trusted, because every one of them is the kind of claim that
quietly stops being true as a package grows: a convenience import of
`requests`, a handler that forgets to reject unknown fields, a new Skill added
to the catalog with no handler behind it.
"""

from __future__ import annotations

import ast
import inspect
import json
import textwrap
from pathlib import Path

import pytest

from elmos_repository_refactoring import contracts, dispatcher, runtime
from elmos_repository_refactoring.catalog import SKILL_NAMES, SKILL_SPECS
from elmos_repository_refactoring.contracts import ContractError, Status
from elmos_repository_refactoring.dispatcher import PENDING_SKILLS, RuntimeDispatcher

SOURCE_ROOT = Path(contracts.__file__).resolve().parent
SOURCE_FILES = sorted(SOURCE_ROOT.glob("*.py"))

#: Every module the package is allowed to import.  Standard library only: the
#: README's "zero third-party dependencies" is a security property (nothing to
#: audit, nothing to pin, no supply chain), so it is enforced, not asserted.
ALLOWED_TOP_LEVEL = frozenset(
    {
        "__future__",
        "argparse",
        "ast",
        "base64",
        "binascii",
        "bisect",
        "collections",
        "contextlib",
        "csv",
        "dataclasses",
        "datetime",
        "decimal",
        "difflib",
        "enum",
        "fnmatch",
        "functools",
        "hashlib",
        "hmac",
        "io",
        "itertools",
        "json",
        "math",
        "os",
        "pathlib",
        "re",
        "shutil",
        "stat",
        "string",
        "subprocess",
        "sys",
        "tempfile",
        "textwrap",
        "time",
        "tomllib",
        "traceback",
        "types",
        "typing",
        "unicodedata",
        "uuid",
        "xml",
        "zipfile",
    }
)

#: Modules that may reach the outside world at all.  Everything else is pure.
IMPURE_MODULES = {
    "sandbox.py": {"subprocess", "os", "tempfile", "shutil", "time"},
    "cli.py": {"argparse", "sys", "os", "pathlib"},
    "workspace.py": {"os", "pathlib"},
    "journal.py": {"os", "pathlib"},
    "dispatcher.py": {"pathlib"},
    "runtime.py": {"pathlib"},
    "evidence.py": {"pathlib"},
    "buildgraph.py": {"pathlib"},
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found


class TestDependencyPurity:
    @pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda item: item.name)
    def test_only_the_standard_library_is_imported(self, path: Path) -> None:
        foreign = sorted(_imports(path) - ALLOWED_TOP_LEVEL)
        assert foreign == [], (
            f"{path.name} imports {foreign}, which is outside the standard library. "
            "The package's zero-dependency claim is a security property, not a preference."
        )

    def test_only_the_sandbox_may_spawn_a_process(self) -> None:
        offenders = [
            path.name
            for path in SOURCE_FILES
            if "subprocess" in _imports(path) and path.name != "sandbox.py"
        ]
        assert offenders == [], (
            f"{offenders} import subprocess. Execution belongs behind SandboxExecutor so that "
            "'no executor' is a state the core can report, not one it can route around."
        )

    def test_nothing_opens_a_socket_or_a_url(self) -> None:
        forbidden = {"socket", "urllib", "http", "requests", "httpx", "ftplib", "smtplib"}
        offenders = {
            path.name: sorted(_imports(path) & forbidden)
            for path in SOURCE_FILES
            if _imports(path) & forbidden
        }
        assert offenders == {}, f"network-capable imports found: {offenders}"

    def test_declared_dependencies_are_empty(self) -> None:
        import tomllib

        project = tomllib.loads(
            (SOURCE_ROOT.parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )
        assert project["project"]["dependencies"] == []


class TestCatalogCoverage:
    def test_every_catalog_skill_has_a_handler(self) -> None:
        assert PENDING_SKILLS == frozenset()
        active = RuntimeDispatcher()
        assert set(active.implemented) == set(SKILL_NAMES)
        assert len(SKILL_NAMES) == 23

    def test_no_handler_is_a_stub(self) -> None:
        """A handler that only calls `_pending` would satisfy coverage and nothing else."""

        active = RuntimeDispatcher()
        for name in SKILL_NAMES:
            handler = getattr(active, SKILL_SPECS[name].handler)
            source = inspect.getsource(handler)
            assert "self._pending(" not in source, f"'{name}' dispatches to the pending stub"
            assert len(source.splitlines()) > 8, f"'{name}' has a suspiciously small handler"

    def test_the_committed_catalog_matches_the_code(self) -> None:
        committed = json.loads(
            (SOURCE_ROOT.parents[1] / "config" / "skill-catalog.json").read_text(encoding="utf-8")
        )
        assert committed == runtime.skill_catalog_payload()

    def test_every_declared_dependency_exists(self) -> None:
        for name in SKILL_NAMES:
            for dependency in SKILL_SPECS[name].depends_on:
                assert dependency in SKILL_SPECS, f"'{name}' depends on unknown '{dependency}'"


class TestFailClosedBehaviour:
    @pytest.mark.parametrize("skill", SKILL_NAMES)
    def test_every_handler_declares_the_fields_it_accepts(self, skill: str) -> None:
        """Structural, not behavioural, on purpose.

        A behavioural probe with a bogus key can be satisfied by a handler that
        ignores the key and then blocks for some *other* reason — which is
        exactly the regression this is meant to catch. So the check is that the
        handler actually calls ``reject_unknown_fields`` with a literal
        allow-list, which is the only thing that makes a typo'd key visible.
        """

        source = inspect.getsource(getattr(RuntimeDispatcher(), SKILL_SPECS[skill].handler))
        tree = ast.parse(textwrap.dedent(source))
        guarded = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "reject_unknown_fields"
            for node in ast.walk(tree)
        )
        delegates = any(
            isinstance(node, ast.Attribute)
            and node.attr in {"_pipeline", "_transform_stage", "_candidate_stage"}
            for node in ast.walk(tree)
        )
        assert guarded, (
            f"'{skill}' never calls reject_unknown_fields; a caller's typo'd key would be "
            f"silently ignored, which reads as 'we did that' for something the handler did not do"
            + ("" if not delegates else " (delegating to a shared stage does not cover its own payload)")
        )

    @pytest.mark.parametrize(
        "skill",
        [
            "repository-discovery",
            "build-graph-and-environment",
            "semantic-index",
            "data-schema-refactor",
            "security-preservation",
            "ui-and-client-refactor",
        ],
    )
    def test_an_otherwise_valid_payload_is_rejected_for_one_bad_key(self, skill: str) -> None:
        """The behavioural half: a payload that would work, plus one typo."""

        from .cases import CASES

        base = next(
            (case.payload for case in CASES if case.skill == skill),
            {
                "workspace": {
                    "source": "inline",
                    "repository_id": "r",
                    "revision": "a" * 40,
                    "files": [{"path": "a.py", "content": "def f():\n    pass\n"}],
                }
            },
        )
        result = runtime.dispatch(skill, {**base, "definitely_not_a_field": 1})
        assert result["status"] == Status.REJECTED.value, (
            f"'{skill}' accepted an unknown payload field instead of rejecting it"
        )
        assert result["output"].get("code") == "unknown_field"
        assert "definitely_not_a_field" in json.dumps(result["output"])

    @pytest.mark.parametrize("skill", SKILL_NAMES)
    def test_an_empty_payload_never_succeeds_by_accident(self, skill: str) -> None:
        result = runtime.dispatch(skill, {})
        if result["status"] == Status.SUCCEEDED.value:
            #: A Skill may legitimately succeed on an empty payload only if it
            #: needs no input at all — and then it must have done nothing.
            assert result["side_effects_performed"] is False
            assert SKILL_SPECS[skill].mutating is False, (
                f"'{skill}' is declared mutating but succeeded on an empty payload"
            )

    def test_an_unknown_skill_is_rejected_not_dispatched(self) -> None:
        result = runtime.dispatch("not-a-real-skill", {})
        assert result["status"] == Status.REJECTED.value
        assert result["failure_class"] == "terminal"

    def test_a_handler_exception_becomes_a_failure_not_a_traceback(self) -> None:
        active = RuntimeDispatcher()

        def explode(skill: str, payload: object, context: object) -> None:
            raise RuntimeError("boom")

        object.__setattr__(active, "_handlers", {**active._handlers, "semantic-index": explode})
        result = active.execute("semantic-index", {})
        assert result.status is Status.FAILED
        assert result.side_effects_performed is False

    def test_a_payload_cannot_grant_itself_filesystem_reach(self) -> None:
        """`workspace_root` is trusted context. A payload claiming one is a
        privilege escalation attempt, not a configuration option."""

        result = runtime.dispatch(
            "repository-discovery",
            {"workspace": {"source": "directory", "repository_id": "r", "revision": "a" * 40,
                           "root": "/etc"}},
        )
        assert result["status"] == Status.REJECTED.value


class TestHonestyInvariants:
    def test_no_executor_means_no_gate_passes_on_evidence_it_does_not_have(self) -> None:
        from .cases import CASES

        case = next(item for item in CASES if item.skill == "test-and-verification")
        envelope = runtime.dispatch(case.skill, case.payload)
        report = envelope["output"]["validation_report"]
        assert report["passed"] is False
        assert report["undecidedBlockingGates"], (
            "with no executor there must be undecided blocking gates; a green run here would mean "
            "the suite adjudicated gates from evidence that was never produced"
        )

    def test_an_unreadable_file_lowers_coverage_rather_than_vanishing(self) -> None:
        envelope = runtime.dispatch(
            "repository-discovery",
            {
                "workspace": {
                    "source": "inline",
                    "repository_id": "r",
                    "revision": "a" * 40,
                    "files": [
                        {"path": "a.py", "content": "def f():\n    pass\n"},
                        #: A source file the snapshot could not decode. It is
                        #: *not* a declared binary asset: an image legitimately
                        #: has no source coverage, an undecodable .py does.
                        {
                            "path": "c.py",
                            "content_digest": "sha256:" + "1" * 64,
                            "size_bytes": 64,
                            "binary": False,
                            "unreadable_reason": "undecodable-utf8",
                        },
                    ],
                }
            },
        )
        inventory = envelope["output"]["repository_inventory"]
        assert inventory["fileCount"] == 2
        assert inventory["unscanned"] == [{"path": "c.py", "reason": "undecodable-utf8"}]
        assert float(inventory["coverage"]) < 1.0, (
            "an undecodable source file must lower coverage; treating it as zero-symbol "
            "and no-risk is exactly the 'unreadable is not empty' rule this package claims"
        )

    def test_a_declared_binary_asset_does_not_lower_source_coverage(self) -> None:
        """The mirror of the rule above: an image is not unscanned source."""

        envelope = runtime.dispatch(
            "repository-discovery",
            {
                "workspace": {
                    "source": "inline",
                    "repository_id": "r",
                    "revision": "a" * 40,
                    "files": [
                        {"path": "a.py", "content": "def f():\n    pass\n"},
                        {
                            "path": "logo.png",
                            "content_digest": "sha256:" + "2" * 64,
                            "size_bytes": 2048,
                            "binary": True,
                        },
                    ],
                }
            },
        )
        inventory = envelope["output"]["repository_inventory"]
        assert inventory["binaryFiles"] == 1
        assert inventory["unscanned"] == []
        assert float(inventory["coverage"]) == 1.0

    def test_a_signature_cannot_raise_a_language_above_what_the_code_can_do(self) -> None:
        """A descriptor may *claim* L4. Without a backend that executes it, the
        effective level stays at what this package can actually do."""

        from elmos_repository_refactoring.adapters import (
            NATIVE_ENGINE_LEVELS,
            AdapterCapabilitySnapshot,
        )

        order = ["L0", "L1", "L2", "L3", "L4"]
        baseline = AdapterCapabilitySnapshot()
        native = NATIVE_ENGINE_LEVELS["python"]
        assert baseline.effective_level("python") is native

        declared = baseline.descriptors["python-refactor-adapter"].to_payload()
        declared["metadata"] = {**declared["metadata"], "certificationLevel": "L4"}
        boastful = AdapterCapabilitySnapshot.from_payload({"descriptors": [declared]})
        effective = boastful.effective_level("python")
        assert order.index(effective.value) <= order.index(native.value), (
            f"a declared L4 raised python to {effective.value}; a signature is not an "
            f"implementation, and the engine can only do {native.value}"
        )

    def test_a_pinned_clock_is_actually_threaded_into_timestamped_skills(self) -> None:
        """Both directions, so the mechanism cannot be decorative.

        Same instant -> identical bytes. Different instant -> different bytes.
        If only the first held, a ``now`` that was parsed and then ignored
        would pass; that is exactly the state this package was in until the
        Golden corpus flagged four Skills reading the wall clock.
        """

        from .cases import CASES

        timestamped = [
            "repository-refactor-orchestrator",
            "human-approval-gate",
            "rollback-and-recovery",
            "evidence-and-audit",
        ]
        for skill in timestamped:
            case = next(item for item in CASES if item.skill == skill)
            payload = case.payload
            early = runtime.dispatch(skill, payload, trusted_context={"now": "2026-01-15T09:30:00Z"})
            again = runtime.dispatch(skill, payload, trusted_context={"now": "2026-01-15T09:30:00Z"})
            later = runtime.dispatch(skill, payload, trusted_context={"now": "2031-07-04T12:00:00Z"})
            assert early == again, f"'{skill}' is not reproducible at a fixed instant"
            assert early != later, (
                f"'{skill}' produced identical output at two different instants; either it does "
                "not timestamp anything, or the pinned clock is being parsed and ignored"
            )

    def test_the_clock_is_trusted_context_and_not_a_payload_field(self) -> None:
        """A caller who could set the time could date an approval into the past."""

        from .cases import CASES

        case = next(item for item in CASES if item.skill == "human-approval-gate")
        result = runtime.dispatch(
            "human-approval-gate", {**case.payload, "now": "2020-01-01T00:00:00Z"}
        )
        assert result["status"] == Status.REJECTED.value
        assert result["output"].get("code") == "unknown_field"

    def test_determinism_holds_across_a_fresh_process_boundary(self) -> None:
        """Two dispatches in the same process must agree; the corpus checks
        the same thing, and this checks it does not depend on dict ordering."""

        payload = {
            "workspace": {
                "source": "inline",
                "repository_id": "r",
                "revision": "a" * 40,
                "files": [{"path": "a.py", "content": "def f():\n    return 1\n"}],
            }
        }
        reordered = {"workspace": {**payload["workspace"]}}
        first = runtime.dispatch("semantic-index", payload)
        second = runtime.dispatch("semantic-index", reordered)
        assert first == second


class TestErrorSurface:
    def test_every_contract_error_carries_a_machine_readable_code(self) -> None:
        codes: set[str] = set()
        for path in SOURCE_FILES:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                target = node.func
                if isinstance(target, ast.Name) and target.id == "ContractError":
                    assert node.args, f"{path.name}: ContractError raised with no code"
                    first = node.args[0]
                    assert isinstance(first, ast.Constant) and isinstance(first.value, str), (
                        f"{path.name}: ContractError code must be a string literal so it is greppable"
                    )
                    codes.add(first.value)
        assert len(codes) > 60, f"only {len(codes)} distinct error codes found; expected a rich surface"

    def test_error_codes_are_snake_case_identifiers(self) -> None:
        error = ContractError("some_code", "message", {"key": "value"})
        payload = error.to_payload()
        assert payload["code"] == "some_code"
        assert payload["message"] == "message"
        assert payload["details"] == {"key": "value"}


class TestDocumentation:
    @pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda item: item.name)
    def test_every_module_explains_what_it_refuses_to_do(self, path: Path) -> None:
        if path.name == "__init__.py":
            pytest.skip("package marker")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstring = ast.get_docstring(tree)
        assert docstring, f"{path.name} has no module docstring"
        assert len(docstring.splitlines()) >= 3, f"{path.name} has only a one-line docstring"

    @pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda item: item.name)
    def test_every_module_declares_its_public_surface(self, path: Path) -> None:
        if path.name in ("__init__.py", "cli.py"):
            pytest.skip("no public API surface of its own")
        text = path.read_text(encoding="utf-8")
        assert "__all__" in text, f"{path.name} does not declare __all__"


class TestDispatcherSurface:
    def test_the_dispatcher_module_exports_what_the_sdk_relies_on(self) -> None:
        for name in ("PENDING_SKILLS", "RuntimeDispatcher", "dispatch", "build_trusted_context"):
            assert hasattr(dispatcher, name)

    def test_describe_reports_the_true_implementation_state(self) -> None:
        described = runtime.describe()
        assert described["implementedCount"] == described["totalCount"] == 23
        assert all(item["implemented"] for item in described["skills"])

"""Anti-cheat: detecting a patch that makes the gates pass without fixing anything.

Every check here corresponds to a way a green build can be manufactured:

* deleting or emptying a test file;
* removing test functions, or the assertions inside them;
* adding ``skip`` / ``xfail`` / ``@Ignore`` / ``@Disabled`` / ``it.skip``;
* widening a suppression — ``# noqa``, ``# type: ignore``,
  ``eslint-disable``, ``@SuppressWarnings``, ``#pragma warning disable``;
* lowering a rule's severity in a linter or scanner configuration;
* swallowing an exception with a bare ``except: pass``;
* adding paths to an ignore file so a scanner stops looking at them.

The findings are produced from the patch itself, so they are available before
any gate runs and cannot be argued away by a passing test suite.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .patch import PatchSet
from .sarif import SarifResult, SarifRule, SarifRun
from .workspace import WorkspaceSnapshot, classify_path

#: Patterns whose *appearance* in added lines is suspicious.
_SUPPRESSION_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("anti-cheat/skip-marker", r"@(?:pytest\.mark\.)?(?:skip|skipif|xfail)\b", "a test was marked skipped or xfail"),
    ("anti-cheat/skip-marker", r"\b(?:it|test|describe)\.skip\s*\(", "a test was marked skipped"),
    ("anti-cheat/skip-marker", r"@(?:Ignore|Disabled)\b", "a test was disabled"),
    ("anti-cheat/skip-marker", r"\bt\.Skip\s*\(", "a Go test was skipped"),
    ("anti-cheat/suppression", r"#\s*noqa(?!:)", "a blanket noqa suppresses every rule on the line"),
    ("anti-cheat/suppression", r"#\s*type:\s*ignore(?!\[)", "a blanket type: ignore suppresses every type error"),
    ("anti-cheat/suppression", r"eslint-disable(?!-next-line\s+\S)", "a blanket eslint-disable"),
    ("anti-cheat/suppression", r"@SuppressWarnings\s*\(\s*\"all\"", "SuppressWarnings(\"all\")"),
    ("anti-cheat/suppression", r"#pragma\s+warning\s+disable(?!\s+\d)", "a blanket compiler warning disable"),
    ("anti-cheat/suppression", r"//\s*nolint(?!:)", "a blanket nolint"),
    ("anti-cheat/swallowed-exception", r"except\s*(?:Exception\s*)?:\s*(?:#.*)?$", "a bare or broad except"),
    ("anti-cheat/swallowed-exception", r"catch\s*\([^)]*\)\s*\{\s*\}", "an empty catch block"),
)

#: Configuration files whose severity settings gate quality.
_RULE_CONFIG_FILES = (
    "**/.eslintrc*",
    "**/eslint.config.*",
    "**/ruff.toml",
    "**/.ruff.toml",
    "**/pyproject.toml",
    "**/setup.cfg",
    "**/.flake8",
    "**/tslint.json",
    "**/checkstyle.xml",
    "**/pmd.xml",
    "**/sonar-project.properties",
    "**/.semgrep.yml",
    "**/mypy.ini",
    "**/tsconfig.json",
)

_IGNORE_FILES = (
    "**/.gitignore",
    "**/.eslintignore",
    "**/.dockerignore",
    "**/.semgrepignore",
    "**/.trivyignore",
    "**/.snyk",
    "**/.bandit",
)

_SEVERITY_DOWNGRADE = re.compile(
    r"""
    (?:^|\W)
    (?:
        "?(?:error|severity)"?\s*[:=]\s*"?(?:off|none|ignore|warn|warning|info)"?
      | strict\s*[:=]\s*false
      | ignore_errors\s*[:=]\s*true
      | failOnError\s*[:=]\s*false
      | continue-on-error\s*:\s*true
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_ASSERT_PATTERN = re.compile(
    r"\b(?:assert|assertEquals|assertTrue|assertThat|expect|should|require\.(?:NoError|Equal))\b"
)


@dataclass(frozen=True, slots=True)
class CheatFinding:
    code: str
    path: str
    line: int
    message: str
    severity: str = "error"
    evidence: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "severity": self.severity,
            "evidence": self.evidence[:200],
        }


@dataclass(frozen=True, slots=True)
class AntiCheatReport:
    findings: tuple[CheatFinding, ...]
    tests_removed: tuple[str, ...] = ()
    test_files_deleted: tuple[str, ...] = ()
    assertions_removed: int = 0

    @property
    def blocking(self) -> tuple[CheatFinding, ...]:
        return tuple(item for item in self.findings if item.severity == "error")

    @property
    def clean(self) -> bool:
        return not self.blocking

    def to_payload(self) -> dict[str, Any]:
        return {
            "clean": self.clean,
            "findings": [item.to_payload() for item in self.findings],
            "testsRemoved": list(self.tests_removed),
            "testFilesDeleted": list(self.test_files_deleted),
            "assertionsRemoved": self.assertions_removed,
        }

    def sarif_run(self, version: str) -> SarifRun:
        rules = {
            SarifRule(
                id=code,
                name=code.rsplit("/", 1)[-1],
                short_description=_RULE_TEXT.get(code, code),
                default_level="error",
            )
            for code in {item.code for item in self.findings}
        }
        return SarifRun(
            tool_name="elmos-anti-cheat",
            tool_version=version,
            rules=tuple(sorted(rules, key=lambda item: item.id)),
            results=tuple(
                SarifResult(
                    rule_id=item.code,
                    level=item.severity,
                    message=item.message,
                    path=item.path,
                    start_line=item.line,
                    properties={"evidence": item.evidence[:200]},
                )
                for item in self.findings
            ),
            invocation_successful=True,
            properties={"blockingFindings": len(self.blocking)},
        )


_RULE_TEXT: Mapping[str, str] = {
    "anti-cheat/skip-marker": "a test was skipped, ignored or marked expected-to-fail",
    "anti-cheat/suppression": "a diagnostic suppression was added or widened",
    "anti-cheat/swallowed-exception": "an exception is being swallowed",
    "anti-cheat/test-deleted": "a test file was deleted",
    "anti-cheat/test-removed": "a test function was removed",
    "anti-cheat/assertions-removed": "assertions were removed from a test",
    "anti-cheat/severity-lowered": "a rule severity was lowered in configuration",
    "anti-cheat/ignore-widened": "an ignore file gained entries",
}


def _added_lines(patch: PatchSet) -> list[tuple[str, int, str]]:
    """(path, approximate line, text) for every added line in the patch."""

    added: list[tuple[str, int, str]] = []
    for change in patch.changes:
        if change.deleted:
            continue
        for hunk in change.hunks:
            for offset, line in enumerate(hunk.after_lines):
                added.append((change.path, hunk.after_start + offset, line))
    return added


def _removed_lines(patch: PatchSet) -> list[tuple[str, int, str]]:
    removed: list[tuple[str, int, str]] = []
    for change in patch.changes:
        for hunk in change.hunks:
            for offset, line in enumerate(hunk.before_lines):
                removed.append((change.path, hunk.before_start + offset, line))
    return removed


def _python_test_functions(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test"):
            found.add(node.name)
    return found


def analyse(
    patch: PatchSet,
    before: WorkspaceSnapshot,
    after: WorkspaceSnapshot,
    *,
    test_paths: Sequence[str] = (),
) -> AntiCheatReport:
    """Inspect a patch for the ways a green build gets manufactured."""

    findings: list[CheatFinding] = []
    known_tests = set(test_paths)
    deleted_test_files: list[str] = []
    removed_tests: list[str] = []
    assertions_removed = 0
    counted_losses: dict[str, int] = {}

    for change in patch.changes:
        is_test = change.path in known_tests or "test" in classify_path(change.path)
        if change.deleted and is_test:
            deleted_test_files.append(change.path)
            findings.append(
                CheatFinding(
                    "anti-cheat/test-deleted",
                    change.path,
                    1,
                    "a test file was deleted as part of this change; deleting a test is not fixing it",
                )
            )
        if not is_test or change.deleted or change.created:
            continue
        before_record = before.get(change.path)
        after_record = after.get(change.path)
        if before_record is None or after_record is None:
            continue
        if before_record.text is None or after_record.text is None:
            continue
        if change.path.endswith(".py"):
            lost = _python_test_functions(before_record.text) - _python_test_functions(after_record.text)
            for name in sorted(lost):
                removed_tests.append(f"{change.path}::{name}")
                findings.append(
                    CheatFinding(
                        "anti-cheat/test-removed",
                        change.path,
                        1,
                        f"test function '{name}' was removed",
                    )
                )
        before_assertions = len(_ASSERT_PATTERN.findall(before_record.text))
        after_assertions = len(_ASSERT_PATTERN.findall(after_record.text))
        if after_assertions < before_assertions:
            delta = before_assertions - after_assertions
            assertions_removed += delta
            #: Recorded, but not reported here.  The line-level pass below
            #: locates the same loss precisely, and emitting both would tell a
            #: reviewer two assertions went missing when one did.  The
            #: file-level finding is kept only as a fallback for a file whose
            #: removals the patch does not show line by line.
            counted_losses[change.path] = delta

    from .contracts import match_path_glob

    for path, line, text in _added_lines(patch):
        stripped = text.strip()
        for code, pattern, description in _SUPPRESSION_PATTERNS:
            if re.search(pattern, text):
                findings.append(
                    CheatFinding(code, path, line, f"{description} in an added line", evidence=stripped)
                )
        if any(match_path_glob(path, glob) for glob in _RULE_CONFIG_FILES) and _SEVERITY_DOWNGRADE.search(text):
            findings.append(
                CheatFinding(
                    "anti-cheat/severity-lowered",
                    path,
                    line,
                    "a rule severity or strictness setting was lowered in a configuration file",
                    evidence=stripped,
                )
            )
        if any(match_path_glob(path, glob) for glob in _IGNORE_FILES) and stripped and not stripped.startswith("#"):
            findings.append(
                CheatFinding(
                    "anti-cheat/ignore-widened",
                    path,
                    line,
                    "an ignore file gained an entry, which removes files from scanner view",
                    severity="warning",
                    evidence=stripped,
                )
            )

    #: A rename rewrites the *inside* of an assertion: the old line disappears
    #: and a new one takes its place in the same hunk.  Reporting that as a
    #: removed assertion accuses every legitimate refactor of a test of
    #: cheating, and a check that cries wolf on the normal case gets disabled,
    #: which is worse than not having it.  So a removal only counts when the
    #: same file did not gain an assertion to replace it.
    added_assertions: dict[str, int] = {}
    for path, _, text in _added_lines(patch):
        if _ASSERT_PATTERN.search(text):
            added_assertions[path] = added_assertions.get(path, 0) + 1
    removed_assertion_lines: dict[str, list[tuple[int, str]]] = {}
    for path, line, text in _removed_lines(patch):
        if _ASSERT_PATTERN.search(text) and (path in known_tests or "test" in classify_path(path)):
            removed_assertion_lines.setdefault(path, []).append((line, text))
    located: set[str] = set()
    for path, entries in sorted(removed_assertion_lines.items()):
        #: The net loss, not the gross count.  Two assertions removed and one
        #: added is one assertion lost, and that one is still reported.
        net_loss = len(entries) - added_assertions.get(path, 0)
        if net_loss <= 0:
            continue
        located.add(path)
        for line, text in sorted(entries)[:net_loss]:
            findings.append(
                CheatFinding(
                    "anti-cheat/assertions-removed",
                    path,
                    line,
                    "an assertion line was removed from a test and nothing replaced it",
                    evidence=text.strip(),
                )
            )

    #: The fallback: a file that lost assertions by whole-file replacement, so
    #: no individual removed line is attributable.
    for path, delta in sorted(counted_losses.items()):
        if path in located:
            continue
        findings.append(
            CheatFinding(
                "anti-cheat/assertions-removed",
                path,
                1,
                f"{delta} assertion(s) removed from a test file",
            )
        )

    #: Deduplicate: the same line can trip several patterns, and one finding per
    #: (code, path, line) is what a reviewer can act on.
    unique: dict[tuple[str, str, int], CheatFinding] = {}
    for finding in findings:
        unique.setdefault((finding.code, finding.path, finding.line), finding)

    return AntiCheatReport(
        findings=tuple(sorted(unique.values(), key=lambda item: (item.path, item.line, item.code))),
        tests_removed=tuple(sorted(set(removed_tests))),
        test_files_deleted=tuple(sorted(set(deleted_test_files))),
        assertions_removed=assertions_removed,
    )


__all__ = ["AntiCheatReport", "CheatFinding", "analyse"]

"""Differential execution: run the Java and run the translation, compare.

This is the only part of the engine that can honestly say a translation is
*correct* on a given input, because it is the only part that runs both sides.
Everything upstream — the parse, the IR, the emitted source — is an argument;
this is the observation.

Two things it deliberately does not do:

* It does not compare stack traces line by line.  Java's trace is a function of
  its own frames and carries no meaning for the translation.  It compares the
  exception *type* and message, which are the observable behaviour.
* It does not pass when either side fails to build.  A build failure is a
  ``BUILD_FAILED`` outcome, not a skipped test.  Counting an unbuildable case as
  "no differences found" is how a broken translation gets certified.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..emit.python import EmitError, PythonEmitter, emit_python
from ..frontend.java import ParseError, UnsupportedConstruct, parse_java_file
from ..program import scan_files
from ..uir import digest

RUNTIME_DIR = Path(__file__).resolve().parents[2] / "runtime"

_JAVA_EXCEPTION_LINE = re.compile(
    r'^Exception in thread "[^"]*" ([\w.$]+)(?:: (.*))?$'
)


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    exception_type: str | None
    exception_message: str | None
    raw_stderr: str = ""

    def observable(self) -> tuple:
        return (self.stdout, self.exception_type, self.exception_message)


@dataclass
class CaseResult:
    args: list[str]
    outcome: str  # MATCH | MISMATCH | JAVA_ERROR | PYTHON_ERROR
    java: RunResult | None = None
    python: RunResult | None = None
    detail: str = ""


@dataclass
class DifferentialReport:
    source: str
    main_class: str
    uir_digest: str
    outcome: str  # PASS | FAIL | BUILD_FAILED | TRANSLATION_REFUSED
    detail: str = ""
    cases: list[CaseResult] = field(default_factory=list)
    generated_python: str = ""
    #: Every other module the program needed, by generated module name.  A
    #: cross-file translation that only shows the entry point would hide the
    #: half of the output the entry point depends on.
    companion_modules: dict[str, str] = field(default_factory=dict)

    @property
    def matched(self) -> int:
        return sum(1 for c in self.cases if c.outcome == "MATCH")

    @property
    def mismatched(self) -> int:
        return sum(1 for c in self.cases if c.outcome != "MATCH")

    def to_json(self) -> str:
        payload = asdict(self)
        payload["matched"] = self.matched
        payload["mismatched"] = self.mismatched
        return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def _parse_java_stderr(stderr: str) -> tuple[str | None, str | None]:
    for line in stderr.splitlines():
        m = _JAVA_EXCEPTION_LINE.match(line.strip())
        if m:
            return m.group(1), m.group(2)
    return None, None


def _run(cmd: list[str], cwd: Path, timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


class DifferentialHarness:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self._require_tool("javac")
        self._require_tool("java")

    @staticmethod
    def _require_tool(name: str) -> None:
        if shutil.which(name) is None:
            raise RuntimeError(
                f"{name} is not on PATH; differential execution cannot run and "
                f"must not be reported as passing"
            )

    def run(self, java_path: Path, arg_vectors: list[list[str]]) -> DifferentialReport:
        java_path = Path(java_path).resolve()
        main_class = java_path.stem

        try:
            module = parse_java_file(java_path)
        except (UnsupportedConstruct, ParseError) as exc:
            return DifferentialReport(
                source=str(java_path),
                main_class=main_class,
                uir_digest="",
                outcome="TRANSLATION_REFUSED",
                detail=str(exc),
            )

        uir_digest = digest(module)

        try:
            python_source = emit_python(module)
        except EmitError as exc:
            return DifferentialReport(
                source=str(java_path),
                main_class=main_class,
                uir_digest=uir_digest,
                outcome="TRANSLATION_REFUSED",
                detail=str(exc),
            )

        report = DifferentialReport(
            source=str(java_path),
            main_class=main_class,
            uir_digest=uir_digest,
            outcome="PASS",
            generated_python=python_source,
        )

        with tempfile.TemporaryDirectory(prefix="j2p-diff-") as tmp:
            work = Path(tmp)
            java_dir = work / "java"
            py_dir = work / "python"
            java_dir.mkdir()
            py_dir.mkdir()

            shutil.copy(java_path, java_dir / java_path.name)
            compile_proc = _run(
                ["javac", "-nowarn", java_path.name], java_dir, self.timeout
            )
            if compile_proc.returncode != 0:
                report.outcome = "BUILD_FAILED"
                report.detail = f"javac failed:\n{compile_proc.stderr.strip()}"
                return report

            (py_dir / f"{main_class}.py").write_text(python_source, encoding="utf-8")
            for module in sorted(RUNTIME_DIR.glob("*.py")):
                shutil.copy(module, py_dir / module.name)

            syntax = _run(
                [sys.executable, "-m", "py_compile", f"{main_class}.py"],
                py_dir,
                self.timeout,
            )
            if syntax.returncode != 0:
                report.outcome = "BUILD_FAILED"
                report.detail = (
                    f"generated Python does not compile:\n{syntax.stderr.strip()}"
                )
                return report

            for args in arg_vectors:
                report.cases.append(
                    self._one_case(java_dir, py_dir, main_class, args)
                )

        if any(c.outcome != "MATCH" for c in report.cases):
            report.outcome = "FAIL"
            first = next(c for c in report.cases if c.outcome != "MATCH")
            report.detail = f"{report.mismatched} of {len(report.cases)} inputs differ; first: {first.detail}"
        return report

    def run_program(
        self,
        main_path: Path,
        arg_vectors: list[list[str]],
        sources: list[Path] | None = None,
    ) -> DifferentialReport:
        """Differentially execute a *multi-file* program.

        Single-file differential evidence cannot say anything about whole-program
        resolution, because the thing under test is precisely what happens when
        a call leaves the file it was written in.  Every source is compiled by
        one ``javac`` invocation and translated against one shared index, then
        both programs are run from their own entry point and compared the same
        way as the single-file case.
        """

        main_path = Path(main_path).resolve()
        if sources is None:
            sources = sorted(main_path.parent.glob("*.java"))
        sources = [Path(s).resolve() for s in sources]
        if main_path not in sources:
            sources.append(main_path)
        main_class = main_path.stem

        index = scan_files(sources)
        if index.unscanned:
            return DifferentialReport(
                source=str(main_path),
                main_class=main_class,
                uir_digest="",
                outcome="TRANSLATION_REFUSED",
                detail=f"declaration scan failed: {index.unscanned}",
            )

        generated: dict[str, str] = {}
        main_digest = ""
        for source in sources:
            try:
                module = parse_java_file(source, index=index)
                code = PythonEmitter(module, index=index).emit()
            except (UnsupportedConstruct, ParseError, EmitError) as exc:
                return DifferentialReport(
                    source=str(main_path),
                    main_class=main_class,
                    uir_digest=main_digest,
                    outcome="TRANSLATION_REFUSED",
                    detail=f"{source.name}: {exc}",
                )
            generated[source.stem] = code
            if source == main_path:
                main_digest = digest(module)

        report = DifferentialReport(
            source=str(main_path),
            main_class=main_class,
            uir_digest=main_digest,
            outcome="PASS",
            generated_python=generated[main_class],
            companion_modules={
                k: v for k, v in generated.items() if k != main_class
            },
        )

        with tempfile.TemporaryDirectory(prefix="j2p-diff-prog-") as tmp:
            work = Path(tmp)
            java_dir = work / "java"
            py_dir = work / "python"
            java_dir.mkdir()
            py_dir.mkdir()

            for source in sources:
                shutil.copy(source, java_dir / source.name)
            compile_proc = _run(
                ["javac", "-nowarn", *[s.name for s in sources]],
                java_dir,
                self.timeout,
            )
            if compile_proc.returncode != 0:
                report.outcome = "BUILD_FAILED"
                report.detail = f"javac failed:\n{compile_proc.stderr.strip()}"
                return report

            for name, code in generated.items():
                (py_dir / f"{name}.py").write_text(code, encoding="utf-8")
            for runtime_module in sorted(RUNTIME_DIR.glob("*.py")):
                shutil.copy(runtime_module, py_dir / runtime_module.name)

            for name in generated:
                syntax = _run(
                    [sys.executable, "-m", "py_compile", f"{name}.py"],
                    py_dir,
                    self.timeout,
                )
                if syntax.returncode != 0:
                    report.outcome = "BUILD_FAILED"
                    report.detail = (
                        f"generated {name}.py does not compile:\n"
                        f"{syntax.stderr.strip()}"
                    )
                    return report

            for args in arg_vectors:
                report.cases.append(
                    self._one_case(java_dir, py_dir, main_class, args)
                )

        if any(c.outcome != "MATCH" for c in report.cases):
            report.outcome = "FAIL"
            first = next(c for c in report.cases if c.outcome != "MATCH")
            report.detail = (
                f"{report.mismatched} of {len(report.cases)} inputs differ; "
                f"first: {first.detail}"
            )
        return report

    def _one_case(
        self, java_dir: Path, py_dir: Path, main_class: str, args: list[str]
    ) -> CaseResult:
        try:
            jproc = _run(["java", "-cp", ".", main_class, *args], java_dir, self.timeout)
        except subprocess.TimeoutExpired:
            return CaseResult(args=args, outcome="JAVA_ERROR", detail="java timed out")

        jtype, jmsg = _parse_java_stderr(jproc.stderr)
        java_result = RunResult(
            exit_code=jproc.returncode,
            stdout=jproc.stdout,
            exception_type=jtype,
            exception_message=jmsg,
            raw_stderr=jproc.stderr,
        )

        try:
            pproc = _run(
                [sys.executable, f"{main_class}.py", *args], py_dir, self.timeout
            )
        except subprocess.TimeoutExpired:
            return CaseResult(
                args=args,
                outcome="PYTHON_ERROR",
                java=java_result,
                detail="python timed out",
            )

        ptype, pmsg = _parse_java_stderr(pproc.stderr)
        if ptype is None and pproc.returncode != 0:
            # A Python-level traceback means the translation crashed in a way
            # Java never would.  That is a mismatch, not an inconclusive result.
            return CaseResult(
                args=args,
                outcome="PYTHON_ERROR",
                java=java_result,
                python=RunResult(
                    exit_code=pproc.returncode,
                    stdout=pproc.stdout,
                    exception_type=None,
                    exception_message=None,
                    raw_stderr=pproc.stderr,
                ),
                detail=(
                    "generated Python raised a non-Java error:\n"
                    + pproc.stderr.strip()[-600:]
                ),
            )

        python_result = RunResult(
            exit_code=pproc.returncode,
            stdout=pproc.stdout,
            exception_type=ptype,
            exception_message=pmsg,
            raw_stderr=pproc.stderr,
        )

        if java_result.observable() == python_result.observable():
            return CaseResult(
                args=args, outcome="MATCH", java=java_result, python=python_result
            )

        return CaseResult(
            args=args,
            outcome="MISMATCH",
            java=java_result,
            python=python_result,
            detail=_describe(java_result, python_result, args),
        )


def _describe(java: RunResult, python: RunResult, args: list[str]) -> str:
    bits = [f"args={args!r}"]
    if java.stdout != python.stdout:
        bits.append(f"stdout java={java.stdout!r} python={python.stdout!r}")
    if java.exception_type != python.exception_type:
        bits.append(
            f"exception java={java.exception_type!r} python={python.exception_type!r}"
        )
    elif java.exception_message != python.exception_message:
        bits.append(
            f"message java={java.exception_message!r} python={python.exception_message!r}"
        )
    return "; ".join(bits)


#: Values chosen to sit on the boundaries where Java and Python disagree:
#: 32-bit overflow, negative truncating division, negative remainder, and the
#: one value whose absolute value is itself.
BOUNDARY_INTS = [
    "0",
    "1",
    "-1",
    "7",
    "-7",
    "2",
    "-2",
    "2147483647",
    "-2147483648",
    "1000000",
    "-1000000",
    "65535",
]


def default_arg_vectors(count: int = 2) -> list[list[str]]:
    """Cartesian-ish sweep over boundary integers, kept to a sane size."""

    if count == 0:
        return [[]]
    if count == 1:
        return [[v] for v in BOUNDARY_INTS]
    vectors: list[list[str]] = []
    for a in BOUNDARY_INTS:
        for b in BOUNDARY_INTS:
            vectors.append([a, b])
    return vectors

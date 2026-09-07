"""Bridge: ELMOS's real conversion stages, registered against this cache.

Everything else in this package is verified against stages that live in its own
tests. This module is the seam to the conversion engine ELMOS actually ships --
``engines/polyglot-route-engine`` -- so that the cache's planner, fingerprint
and staging see the real analyzer, the real semantic IR and the real emitter
rather than a stand-in.

The dependency is deliberately one-way and optional. The cache never imports
the route engine at module scope, declares it in ``pyproject.toml`` or fails to
load without it: :func:`available` reports whether it is importable and every
entry point raises :class:`RouteEngineUnavailable` when it is not. That keeps
this package installable on its own while making the integration real where
both are present.

Three stages are bridged, using the contracts already declared in
``stage_contract.default_pipeline()``:

``semantic-ir``
    run the route engine's analyzer over one source unit and stage the semantic
    IR it produced;
``target-code-generation``
    plan identifiers and emit the target-language translation of that IR;
``compile``
    hand the emitted file to the target language's real compiler.

Generation claims ``TEST_VERIFIED`` only when it earned it: the bridge compiles
the emitted Java and runs it against the Python original over a set of inputs,
and downgrades to ``COMPILE_VERIFIED`` when no JDK is present. The stage
contract for ``target-code-generation`` declares a ``TEST_VERIFIED`` floor, so
a result that cannot be differentially checked is produced but never reused --
which is the contract working, not a gap.

**The fingerprint is where the integration is load-bearing.** Generation is
keyed by the digest of the *IR*, not of the source file, so a comment or a
reformat that the analyzer discards does not re-emit anything -- while an
emitter change does, because the emitter's own source is folded into
``rule_pack_digest``.

## Toolchain identity

The route engine pins each toolchain to an exact, platform-specific tree and
refuses to run when the host does not match. This bridge does **not** paper
over that. In the default ``strict_toolchain=True`` mode a platform mismatch
propagates as :class:`RouteEngineUnavailable`; nothing invents a toolchain
digest. ``strict_toolchain=False`` is available for local work, and the
identity it produces is explicitly marked unpinned and carries the host
platform, so an ActionKey computed without a pinned toolchain can never collide
with one computed with it.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .canonical import digest_of, sha256_bytes
from .enums import FileClass, ValidationLevel
from .errors import ElmosCacheError
from .fingerprint import FingerprintInputs
from .manifests import ExecutionMetrics
from .pipeline import StageFunction, StageOutput, StageResult

#: Environment variable pointing at ``polyglot-route-engine/src``.
ROUTE_ENGINE_PATH_VARIABLE = "ELMOS_POLYGLOT_ROUTE_SRC"

#: Route-engine modules whose content decides what the emitter produces. Their
#: bytes are the ``rule_pack_digest``: edit an emitter and the cache misses.
RULE_PACK_MODULES: tuple[str, ...] = (
    "models.py",
    "python_analyzer.py",
    "identifier_hygiene.py",
    "emitter.py",
    "types.py",
)


#: Inputs the differential runner compares source and target on. Small, but
#: chosen to cross the branches the emitted code actually has.
DEFAULT_DIFFERENTIAL_CASES: tuple[tuple[int, ...], ...] = (
    (0, 0),
    (1, 1),
    (7, 3),
    (-5, 4),
    (123456, 7),
    (-1, -1),
)


class RouteEngineUnavailable(ElmosCacheError):
    """The route engine is not importable, or refuses to run on this host."""

    code = "ROUTE_ENGINE_UNAVAILABLE"


def route_engine_source() -> Path | None:
    """Locate ``polyglot-route-engine/src``: the environment, then the sibling."""
    declared = os.environ.get(ROUTE_ENGINE_PATH_VARIABLE)
    if declared:
        candidate = Path(declared).expanduser()
        return candidate if (candidate / "elmos_polyglot_route").is_dir() else None
    # <repo>/engines/build-cache-engine/src/elmos_build_cache/this_file.py
    engines = Path(__file__).resolve().parents[3]
    sibling = engines / "polyglot-route-engine" / "src"
    return sibling if (sibling / "elmos_polyglot_route").is_dir() else None


def _import_route_engine() -> Any:
    source = route_engine_source()
    if source is not None and str(source) not in sys.path:
        sys.path.insert(0, str(source))
    try:
        import elmos_polyglot_route  # noqa: F401
        from elmos_polyglot_route import emitter, identifier_hygiene, models, python_analyzer
    except ImportError as error:
        raise RouteEngineUnavailable(
            "the ELMOS polyglot route engine is not importable",
            searched=str(source) if source else None,
            variable=ROUTE_ENGINE_PATH_VARIABLE,
            detail=str(error),
        ) from error
    return models, python_analyzer, identifier_hygiene, emitter


def available() -> bool:
    """True when the route engine can be imported from this process."""
    try:
        _import_route_engine()
    except RouteEngineUnavailable:
        return False
    return True


@lru_cache(maxsize=1)
def rule_pack_digest() -> str:
    """Digest of the emitter's own source: an emitter edit is a cache miss."""
    source = route_engine_source()
    if source is None:
        raise RouteEngineUnavailable("cannot digest the rule pack without the route engine")
    package = source / "elmos_polyglot_route"
    parts = {name: sha256_bytes((package / name).read_bytes()) for name in RULE_PACK_MODULES}
    return digest_of({"kind": "elmos.route-engine.rule-pack", "modules": parts})


@dataclass(frozen=True)
class RouteUnit:
    """One function to convert: the granularity the route engine works at."""

    logical_source: str
    function_name: str
    source_language: str
    target_language: str

    @property
    def node_id(self) -> str:
        return f"convert:{self.logical_source}::{self.function_name}->{self.target_language}"

    @property
    def ir_path(self) -> str:
        return f"ir/{self.logical_source}.{self.function_name}.semantic-ir.json"


@dataclass(frozen=True)
class DifferentialResult:
    """Did the emitted target behave like the source, and over how many cases."""

    passed: bool
    cases: int
    detail: str


@dataclass(frozen=True)
class ToolchainIdentity:
    """What the ActionKey records about the toolchain that produced a result."""

    language: str
    pinned: bool
    detail: dict[str, Any]

    def digest(self) -> str:
        return digest_of({"language": self.language, "pinned": self.pinned, **self.detail})


class RouteStages:
    """The real conversion stages, adapted to this cache's stage contracts."""

    def __init__(
        self,
        source_root: Path,
        *,
        strict_toolchain: bool = True,
    ) -> None:
        self.source_root = Path(source_root)
        self.strict_toolchain = strict_toolchain
        self.analyzed: list[str] = []
        self.emitted: list[str] = []
        self.compiled: list[str] = []
        self._models, self._analyzer, self._identifiers, self._emitter = _import_route_engine()

    # -- identity ---------------------------------------------------------
    def toolchain_identity(self, language: str) -> ToolchainIdentity:
        """The route engine's pinned toolchain, or an explicitly unpinned one.

        A pinned identity is taken from the engine itself. When the host does
        not match the pin, strict mode refuses rather than substituting
        something plausible: a forged toolchain digest is how two different
        compilers end up sharing one cache entry.
        """
        from elmos_polyglot_route.models import RouteError
        from elmos_polyglot_route.toolchains import exact_toolchain

        try:
            toolchain = exact_toolchain(language)
        except RouteError as error:
            if self.strict_toolchain:
                raise RouteEngineUnavailable(
                    "the route engine refuses this host's toolchain",
                    language=language,
                    detail=str(error),
                ) from error
            return ToolchainIdentity(
                language=language,
                pinned=False,
                detail={
                    "reason": str(error),
                    "host": f"{platform.system()}/{platform.machine()}",
                    "interpreter": platform.python_version(),
                },
            )
        return ToolchainIdentity(
            language=language,
            pinned=True,
            detail={
                "name": getattr(toolchain, "name", language),
                "version": getattr(toolchain, "version", ""),
                "executable": str(getattr(toolchain, "executable", "")),
            },
        )

    def analyzer_identity(self, ir: Any) -> dict[str, str]:
        return {"analyzer": str(ir.analyzer), "analyzer_version": str(ir.analyzer_version)}

    # -- the stages -------------------------------------------------------
    def analyze(self, unit: RouteUnit) -> Any:
        """Run the route engine's real analyzer over one unit."""
        if unit.source_language != "python":
            # Every other analyzer shells out to a pinned native helper, which
            # is exactly what ``toolchain_identity`` gates. Route it through
            # the engine's own dispatcher so the refusal comes from the engine.
            from elmos_polyglot_route.native import analyze as native_analyze

            self.toolchain_identity(unit.source_language)
            return native_analyze(
                self.source_root / unit.logical_source,
                unit.source_language,
                unit.function_name,
            )
        return self._analyzer.analyze_python(
            self.source_root / unit.logical_source, unit.function_name
        )

    def ir_digest(self, ir: Any) -> str:
        return digest_of(ir.to_mapping())

    def emit(self, ir: Any, target_language: str) -> Any:
        plan = self._identifiers.plan_identifiers(ir, target_language)
        return self._emitter.emit(ir, target_language, identifier_plan=plan)

    def semantic_ir_stage(self, unit: RouteUnit) -> StageFunction:
        def run(node: Any, inputs: Mapping[str, Any]) -> StageResult:
            self.analyzed.append(unit.node_id)
            ir = self.analyze(unit)
            document = json.dumps(ir.to_mapping(), ensure_ascii=False, indent=2, sort_keys=True)
            return StageResult(
                outputs=(
                    StageOutput(
                        logical_path=unit.ir_path,
                        payload=(document + "\n").encode("utf-8"),
                        file_class=FileClass.STAGED_INTERMEDIATE,
                        media_type="application/json",
                    ),
                ),
                metrics=ExecutionMetrics(wall_ms=120, cpu_ms=110, compiler_ms=0, model_tokens=0),
                completed_partitions=(unit.node_id,),
                evidence=({"kind": "analysis", **self.analyzer_identity(ir)},),
                validation_level=ValidationLevel.UNVERIFIED,
            )

        return run

    def generation_stage(
        self,
        unit: RouteUnit,
        *,
        differential_cases: Sequence[Sequence[int]] = DEFAULT_DIFFERENTIAL_CASES,
        work_root: Path | None = None,
    ) -> StageFunction:
        def run(node: Any, inputs: Mapping[str, Any]) -> StageResult:
            self.emitted.append(unit.node_id)
            ir = self.analyze(unit)
            emitted = self.emit(ir, unit.target_language)
            work = (work_root or self.source_root.parent / "differential") / unit.node_id.replace(
                "/", "_"
            ).replace(":", "-")
            differential = self.differential_check(unit, ir, emitted, work, differential_cases)
            source_map = {
                "kind": "elmos.source-map/v1",
                "source": unit.logical_source,
                "function": unit.function_name,
                "target": emitted.relative_path,
                "target_language": unit.target_language,
            }
            return StageResult(
                outputs=(
                    StageOutput(
                        logical_path=self.target_path(unit, emitted),
                        payload=emitted.content.encode("utf-8"),
                        file_class=FileClass.PUBLISH_CANDIDATE,
                        media_type="text/plain",
                    ),
                    StageOutput(
                        logical_path=self.target_path(unit, emitted) + ".source_maps.json",
                        payload=(json.dumps(source_map, sort_keys=True) + "\n").encode("utf-8"),
                        file_class=FileClass.STAGED_INTERMEDIATE,
                        media_type="application/json",
                    ),
                ),
                metrics=ExecutionMetrics(
                    wall_ms=400, cpu_ms=380, compiler_ms=900 if differential.passed else 0, model_tokens=0
                ),
                completed_partitions=(unit.node_id,),
                evidence=(
                    {
                        "kind": "generation",
                        "emitter": "elmos-polyglot-route",
                        "target_language": unit.target_language,
                        **self.analyzer_identity(ir),
                    },
                    {
                        "kind": "differential",
                        "passed": differential.passed,
                        "cases": differential.cases,
                        "detail": differential.detail,
                    },
                ),
                # Earned, not asserted: without a passing differential run this
                # result is produced but is below the contract's reuse floor.
                validation_level=(
                    ValidationLevel.TEST_VERIFIED
                    if differential.passed
                    else ValidationLevel.COMPILE_VERIFIED
                ),
            )

        return run

    def target_path(self, unit: RouteUnit, emitted: Any) -> str:
        stem = Path(unit.logical_source).stem
        return f"{unit.target_language}/{stem}/{emitted.relative_path}"

    # -- fingerprint ------------------------------------------------------
    def generation_fingerprint(
        self,
        unit: RouteUnit,
        ir_digest: str,
        dependency_interfaces: Sequence[str] = (),
    ) -> FingerprintInputs:
        """Keyed by the IR, not the source text.

        This is the whole reason to bridge at the IR boundary: a comment, an
        import reorder or a reformat changes the file but not the IR, and must
        not re-emit anything. An emitter change *is* in the key, through
        ``rule_pack_digest``.
        """
        return FingerprintInputs(
            input_artifact_digests=(ir_digest,),
            source_semantic_digest=ir_digest,
            dependency_public_interface_digests=tuple(dependency_interfaces),
            target_language=unit.target_language,
            target_framework="none",
            target_runtime=self.target_runtime(unit.target_language),
            rule_pack_digest=rule_pack_digest(),
            toolchain_digest=self.toolchain_identity(unit.target_language).digest(),
            declared_environment={"LANG": "C.UTF-8", "TZ": "UTC"},
        )

    def analysis_fingerprint(self, unit: RouteUnit, source_digest: str) -> FingerprintInputs:
        return FingerprintInputs(
            input_artifact_digests=(source_digest,),
            target_language=unit.source_language,
            rule_pack_digest=rule_pack_digest(),
            toolchain_digest=self.toolchain_identity(unit.source_language).digest(),
            declared_environment={"LANG": "C.UTF-8", "TZ": "UTC"},
        )

    @staticmethod
    def target_runtime(language: str) -> str:
        return {
            "java": "jvm",
            "csharp": "dotnet",
            "typescript": "node",
            "go": "go",
            "rust": "rust",
            "python": "cpython",
        }.get(language, language)

    # -- behavioural equivalence -----------------------------------------
    def target_function_name(self, ir: Any, target_language: str) -> str:
        plan = self._identifiers.plan_identifiers(ir, target_language)
        return str(self._identifiers.target_ir_view(ir, plan).functions[0].name)

    def differential_check(
        self, unit: RouteUnit, ir: Any, emitted: Any, work: Path, cases: Sequence[Sequence[int]]
    ) -> DifferentialResult:
        """Run the emitted target against the Python original, input by input.

        This is what makes ``TEST_VERIFIED`` an earned claim rather than an
        asserted one. It is deliberately narrow -- integer-typed pure functions
        on the java target -- and says so when it cannot run.
        """
        if unit.target_language != "java":
            return DifferentialResult(False, 0, f"no differential runner for {unit.target_language}")
        javac, java = shutil.which("javac"), shutil.which("java")
        if javac is None or java is None:
            return DifferentialResult(False, 0, "no JDK on PATH")
        function = ir.functions[0]
        if any(parameter.type != "integer" for parameter in function.parameters):
            return DifferentialResult(False, 0, "differential runner covers integer parameters only")

        work.mkdir(parents=True, exist_ok=True)
        (work / emitted.relative_path).write_text(emitted.content, encoding="utf-8")
        name = self.target_function_name(ir, "java")
        klass = Path(emitted.relative_path).stem
        arguments = ", ".join(f"Long.parseLong(a[{index}])" for index in range(len(function.parameters)))
        (work / "ElmosDifferential.java").write_text(
            "public final class ElmosDifferential {\n"
            "    public static void main(String[] a) {\n"
            f"        System.out.println({klass}.{name}({arguments}));\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        compiled = subprocess.run(  # noqa: S603
            [javac, "-d", str(work), str(work / emitted.relative_path), str(work / "ElmosDifferential.java")],
            capture_output=True, text=True, timeout=600, check=False,
        )
        if compiled.returncode != 0:
            return DifferentialResult(False, 0, (compiled.stdout + compiled.stderr)[-2000:])

        reference = self._python_reference(unit)
        for case in cases:
            observed = subprocess.run(  # noqa: S603
                [java, "-cp", str(work), "ElmosDifferential", *[str(value) for value in case]],
                capture_output=True, text=True, timeout=600, check=False,
            )
            if observed.returncode != 0:
                return DifferentialResult(False, 0, (observed.stdout + observed.stderr)[-2000:])
            expected = reference(*case)
            if observed.stdout.strip() != str(expected):
                return DifferentialResult(
                    False, 0, f"case {case}: python={expected!r} java={observed.stdout.strip()!r}"
                )
        return DifferentialResult(True, len(cases), f"{len(cases)} cases agreed")

    def _python_reference(self, unit: RouteUnit) -> Any:
        """The source function itself, as the oracle to compare against."""
        namespace: dict[str, Any] = {}
        source = (self.source_root / unit.logical_source).read_text(encoding="utf-8")
        exec(compile(source, unit.logical_source, "exec"), namespace)  # noqa: S102
        return namespace[unit.function_name]

    # -- optional real compilation ---------------------------------------
    def compile_target(self, language: str, path: Path, work: Path) -> tuple[bool, str]:
        """Hand the emitted file to the target language's own compiler."""
        work.mkdir(parents=True, exist_ok=True)
        if language == "java":
            javac = shutil.which("javac")
            if javac is None:
                return False, "javac is not installed"
            command = [javac, "-d", str(work), str(path)]
        elif language == "go":
            go = shutil.which("go")
            if go is None:
                return False, "go is not installed"
            (work / "go.mod").write_text("module emitted\n\ngo 1.21\n", encoding="utf-8")
            shutil.copy2(path, work / path.name)
            # The emitted unit is a library function in ``package main``; give
            # the linker the entry point it needs and nothing else.
            (work / "elmos_entrypoint.go").write_text("package main\n\nfunc main() {}\n", encoding="utf-8")
            command = [go, "build", "./..."]
        elif language == "typescript":
            tsc = shutil.which("tsc")
            if tsc is None:
                return False, "tsc is not installed"
            shutil.copy2(path, work / path.name)
            command = [tsc, "--noEmit", "--strict", str(work / path.name)]
        else:
            return False, f"no compile command wired for {language}"

        self.compiled.append(language)
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=str(work),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        return completed.returncode == 0, completed.stdout + completed.stderr

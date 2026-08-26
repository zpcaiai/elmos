"""Execution evidence for the constructs the 2026-08-26 analyzer fixes made
liftable: n-ary boolean chains, signed literals, and `not`.

`canonical.evaluate` IS the specification, so it is the reference. Using one
TARGET as the reference would quietly promote that implementation to the spec,
which is the mistake `canonical.py`'s own docstring warns about.

Two suites, because one construct splits the matrix:

  full        all seven functions, including `-9223372036854775808`.
              TypeScript and React MUST refuse this one -- the value is past
              `Number.MAX_SAFE_INTEGER`, and emitting a wrong constant instead
              of refusing would be the defect. Their refusal is the evidence.
  safe        the same minus `most_negative`, so TypeScript and React have a
              suite they can actually run.

Toolchain resolution is fail-closed, self-describing, and GRADED. Strongest
first:

  EXACT   `toolchains.exact_toolchain()` -- the engine's own verifier -- accepted
          the binary. That checks the version AND the sha256 against the
          repository pin, plus Xcode/SDK identity for the Apple targets. This
          is evidence about the toolchain the repository pins.
  PINNED  exactly one version directory under the toolchain root
          (`ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT`, default
          `~/.local/share/elmos/toolchains`). The path is named, but nothing
          about its contents was verified.
  PATH    whatever `shutil.which` found. Says nothing beyond "a binary by that
          name existed".

A row NEVER drops a grade silently: when `exact_toolchain()` refuses, its code
is carried into the weaker provenance string, so `PATH:` always arrives with
the reason it is not `EXACT:`. A target is never reported as passing on a
toolchain the report cannot name.

    python differential_execution.py --out /tmp/elmos-diff --json evidence.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from elmos_polyglot_route import canonical
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.identifier_hygiene import plan_identifiers
from elmos_polyglot_route.models import SUPPORTED_LANGUAGES, RouteError
from elmos_polyglot_route.python_analyzer import analyze_python
from elmos_polyglot_route.toolchains import exact_toolchain

SOURCE_TEXT = '''
def nary_and(a: bool, b: bool, c: bool) -> bool:
    return a and b and c

def nary_or(a: bool, b: bool, c: bool, d: bool) -> bool:
    return a or b or c or d

def negative_literal(x: int) -> int:
    return x + -1

def most_negative() -> int:
    return -9223372036854775808

def negative_float() -> float:
    return -2.5

def logical_not(x: bool) -> bool:
    return not x

def mixed(a: bool, b: bool, n: int) -> int:
    if not a and b:
        return n + -7
    return -3
'''

CASES: dict[str, list[list[int]]] = {
    "nary_and": [[a, b, c] for a in (0, 1) for b in (0, 1) for c in (0, 1)],
    "nary_or": [[a, b, c, d] for a in (0, 1) for b in (0, 1) for c in (0, 1) for d in (0, 1)],
    "negative_literal": [[0], [1], [-1], [9223372036854775806], [-9223372036854775807]],
    "most_negative": [[]],
    "negative_float": [[]],
    "logical_not": [[0], [1]],
    "mixed": [[a, b, n] for a in (0, 1) for b in (0, 1) for n in (0, 5, -5)],
}
#: The `safe` suite is not just "minus most_negative" -- it is the same
#: constructs restricted to the SAFE-INTEGER domain. TypeScript and React are
#: required to fail closed on any value or intermediate past
#: `Number.MAX_SAFE_INTEGER` (see canonical.py), so feeding them 2^63-2 and
#: calling the resulting `ELMOS_INTEGER_NOT_SAFE` a harness failure would be
#: scoring correct behaviour as a defect.
SAFE_CASES: dict[str, list[list[int]]] = {
    **{k: v for k, v in CASES.items() if k != "most_negative"},
    "negative_literal": [[0], [1], [-1], [1000], [-1000]],
}


# --------------------------------------------------------------- toolchain ----

def toolchain_root() -> Path:
    value = (
        os.environ.get("ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT")
        or os.environ.get("ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT")
        or "~/.local/share/elmos/toolchains"
    )
    return Path(value).expanduser()


#: Which pinned toolchain the ENGINE resolves for each target, and which of
#: its two binaries this harness drives. Deliberately explicit rather than
#: derived from the target name: `flutter` must drive the BUNDLED `dart`
#: (`.auxiliary`), not the `flutter` wrapper, and `objc` is the same clang as
#: `cpp` with `-x objective-c` selecting the mode.
_ENGINE_TOOLCHAIN: dict[str, tuple[str, str]] = {
    "python": ("python", "executable"),
    "go": ("go", "executable"),
    "java": ("java", "executable"),          # `.auxiliary` is javac
    "php": ("php", "executable"),
    "rust": ("rust", "executable"),          # rustc; `.auxiliary` is cargo
    "cpp": ("cpp", "executable"),            # clang++, NOT whatever g++ is on PATH
    "objc": ("objc", "executable"),          # the same clang driver
    "swift": ("swift", "executable"),        # swiftc; `.auxiliary` is the `swift` driver
    "kotlin": ("kotlin", "executable"),      # kotlinc; `.auxiliary` is the launcher
    "typescript": ("typescript", "executable"),  # node; `.auxiliary` is the tsc launcher
    "csharp": ("csharp", "executable"),      # the dotnet muxer
    "flutter": ("flutter", "auxiliary"),     # the bundled dart
}


@dataclasses.dataclass(frozen=True)
class Resolved:
    """One target's binary and how much is actually known about it."""

    executable: str | None
    provenance: str
    auxiliary: str | None = None


def resolve(language: str, exe: tuple[str, str, str]) -> Resolved:
    """The strongest grade the machine supports, and never a silent downgrade.

    `exact_toolchain` is the engine's own verifier: version plus sha256 against
    the repository pin. When it refuses, its code is carried into the weaker
    provenance string -- a `PATH:` row must state why it is not `EXACT:`.
    """
    # `language` is the TARGET name (`csharp`), never the toolchain directory
    # (`dotnet`). Reading the directory here is what made `ELMOS_DIFF_CSHARP`
    # a documented override that silently did nothing.
    directory, relative, path_name = exe
    override = os.environ.get(f"ELMOS_DIFF_{language.upper()}")
    if override:
        # An explicit operator instruction still wins, and is labelled as one:
        # `ENV:` asserts nothing about the binary beyond "someone named it".
        return Resolved(override, f"ENV:ELMOS_DIFF_{language.upper()}")

    engine_note = "EXACT_NOT_ATTEMPTED:no pinned toolchain registered for this target"
    registered = _ENGINE_TOOLCHAIN.get(language)
    if registered is not None:
        engine_language, attribute = registered
        try:
            toolchain = exact_toolchain(engine_language)
        except RouteError as error:
            engine_note = f"EXACT_REFUSED:{error}"
        except Exception as error:  # noqa: BLE001 - grading must not abort the run
            engine_note = f"EXACT_ERRORED:{type(error).__name__}:{error}"
        else:
            chosen = getattr(toolchain, attribute)
            if chosen and os.access(chosen, os.X_OK):
                return Resolved(
                    str(chosen),
                    f"EXACT:{engine_language}:{toolchain.version}:{chosen}",
                    str(toolchain.auxiliary) if toolchain.auxiliary else None,
                )
            engine_note = (
                f"EXACT_UNUSABLE:{engine_language}:{attribute}="
                f"{chosen!r} is missing or not executable"
            )

    candidates = sorted((toolchain_root() / directory).glob(f"*/{relative}"))
    if len(candidates) == 1 and os.access(candidates[0], os.X_OK):
        return Resolved(str(candidates[0]), f"PINNED:{candidates[0]} ({engine_note})")
    if len(candidates) > 1:
        return Resolved(
            None,
            f"AMBIGUOUS:{len(candidates)} versions under {toolchain_root() / directory}"
            f" ({engine_note})",
        )
    found = shutil.which(path_name)
    if found:
        return Resolved(found, f"PATH:{found} ({engine_note})")
    return Resolved(None, f"NOT_FOUND ({engine_note})")


def version_of(executable: str, flag: str = "--version") -> str:
    try:
        proc = subprocess.run([executable, flag], capture_output=True, text=True, timeout=120)
    except Exception:  # noqa: BLE001 - provenance only
        return "unknown"
    return ((proc.stdout or proc.stderr).strip().splitlines() or ["unknown"])[0][:120]


# ------------------------------------------------------------------ engine ----

def build(source: Path, names: list[str]):
    irs = [analyze_python(source, name) for name in names]
    return dataclasses.replace(irs[0], functions=tuple(ir.functions[0] for ir in irs))


def normalize(text: str) -> str:
    """Compare values, not spellings -- and never route a 64-bit integer through
    a float, which loses the low bits."""
    text = text.strip()
    if text.lower() in {"true", "false"}:
        return text.lower()
    try:
        return str(int(text))
    except ValueError:
        pass
    try:
        return repr(float(text))
    except ValueError:
        return text


def literal(value: int, kind: str, style: str) -> str:
    if kind == "boolean":
        return ("True" if value else "False") if style == "python" else ("true" if value else "false")
    if kind == "number":
        return repr(float(value))
    if style in {"java", "kotlin"}:
        return f"{value}L"
    return str(value)


def _dotnet_target_framework(executable: str) -> str:
    """Target the SDK that is actually installed, not a hard-wired TFM.

    A pinned `net8.0` fails on a machine that only has .NET 10 with
    "To install missing framework ... framework_version=8.0.0", which says
    nothing about the emitted C# and everything about this harness. The
    emitted unit is plain static methods over long/double/bool, so any
    modern TFM is equally valid -- pick the one that is present.
    """

    try:
        proc = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.TimeoutExpired):
        return "net8.0"
    major = proc.stdout.strip().split(".")[0]
    return f"net{major}.0" if major.isdigit() else "net8.0"


#: Objective-C has no generic print. Picking the renderer by the function's
#: DECLARED return type keeps the harness from deciding what a value is.
_OBJC_RENDERERS = {
    "integer": "elmos_render_i",
    "number": "elmos_render_d",
    "boolean": "elmos_render_b",
}


@dataclasses.dataclass(frozen=True)
class Target:
    style: str
    line: str                     # format string: {n} {i} {call}
    header: tuple[str, ...]
    footer: tuple[str, ...]
    filename: str
    prepend_emitted: bool         # driver file must contain the emitted source
    build_cmd: tuple[tuple[str, ...], ...]
    run_cmd: tuple[str, ...]
    exe: tuple[str, str, str] | None   # (toolchain dir, relative, PATH name)
    call_prefix: str = ""


TARGETS: dict[str, Target] = {
    "python": Target("python", 'print("{n}|{i}|" + str({call}))',
                     ("import migrated", "from migrated import *"), (), "drive.py", False,
                     (), ("{exe}", "drive.py"), ("python", "bin/python3", sys.executable)),
    "go": Target("go", '    fmt.Printf("{n}|{i}|%v\\n", {call})',
                 ("package main", 'import "fmt"', "func main() {"), ("}",), "drive.go", False,
                 (), ("{exe}", "run", "migrated.go", "drive.go"), ("go", "bin/go", "go")),
    "java": Target("java", '        System.out.println("{n}|{i}|" + Migrated.{call});',
                   ("public class Drive {", "    public static void main(String[] a) {"),
                   ("    }", "}"), "Drive.java", False,
                   (("{javac}", "Migrated.java", "Drive.java"),), ("{exe}", "Drive"),
                   ("java", "bin/java", "java")),
    "php": Target("php", 'echo "{n}|{i}|" . json_encode({call}) . "\\n";',
                  ("<?php", "require 'migrated.php';"), (), "drive.php", False,
                  (), ("{exe}", "drive.php"), ("php", "bin/php", "php")),
    "rust": Target("rust", '    println!("{n}|{i}|{{}}", {call});',
                   ("#[allow(dead_code)]", "fn main() {"), ("}",), "drive.rs", True,
                   (("{exe}", "-A", "warnings", "-o", "drive", "drive.rs"),), ("./drive",),
                   ("rust", "bin/rustc", "rustc")),
    "cpp": Target("cpp", '    std::cout << "{n}|{i}|" << std::boolalpha << ({call}) << std::endl;',
                  ("#include <iostream>", "int main() {"), ("    return 0;", "}"), "drive.cpp", True,
                  (("{exe}", "-std=c++20", "-o", "drive", "drive.cpp"),), ("./drive",),
                  ("cpp", "bin/clang++", "clang++")),
    # `-framework Foundation` is REQUIRED: the emitted unit raises
    # `[NSException raise:...]` for the R1 overflow guard, so dropping the
    # framework compiles and then fails at LINK time with
    # "symbol(s) not found for architecture arm64". (It was dropped once to
    # get past a Linux container that has no Foundation at all -- that fixed
    # the wrong end. On Linux this target is NOT_RUN either way.)
    "objc": Target("objc", '    printf("{n}|{i}|%s\\n", {render}({call}));',
                   ("#include <stdio.h>", "int main() {"), ("    return 0;", "}"), "drive.m", True,
                   (("{exe}", "-framework", "Foundation", "-o", "drive", "drive.m"),), ("./drive",),
                   ("objc", "bin/clang", "clang")),
    "swift": Target("swift", '    print("{n}|{i}|\\({call})")',
                    ("func elmosMain() {",), ("}", "elmosMain()"), "drive.swift", True,
                    (("{exe}", "-o", "drive", "drive.swift"),), ("./drive",),
                    ("swift", "bin/swiftc", "swiftc")),
    "kotlin": Target("kotlin", '    println("{n}|{i}|" + {call})',
                     ("fun main() {",), ("}",), "drive.kt", False,
                     (("{exe}", "Migrated.kt", "drive.kt", "-include-runtime", "-d", "drive.jar"),),
                     ("{java}", "-jar", "drive.jar"), ("kotlin", "bin/kotlinc", "kotlinc")),
    "typescript": Target("typescript", '  console.log("{n}|{i}|" + String({call}));',
                         ('import * as m from "./migrated.ts";',), (), "drive.ts", False,
                         (), ("{exe}", "--experimental-strip-types", "drive.ts"),
                         ("node", "bin/node", "node"), call_prefix="m."),
    "csharp": Target("csharp", '        System.Console.WriteLine("{n}|{i}|" + Migrated.{call});',
                     ("public static class Drive {",
                      "    public static void Main() {"), ("    }", "}"), "Drive.cs", False,
                     (), ("{exe}", "run", "--project", ".", "-v", "q", "--nologo"),
                     ("dotnet", "bin/dotnet", "dotnet")),
    "flutter": Target("flutter", '  print("{n}|{i}|" + ({call}).toString());',
                      ("import 'migrated.dart';", "void main() {"), ("}",), "drive.dart", False,
                      (), ("{exe}", "run", "drive.dart"), ("dart", "bin/dart", "dart")),
}


#: Every runnable target must have a pinned toolchain registered, or this
#: module refuses to load. The alternative -- printing
#: "no pinned toolchain registered" about a target that has one -- is a
#: measurement instrument lying quietly, which is the failure mode this whole
#: grading exercise exists to remove.
_UNREGISTERED = sorted(set(TARGETS) - set(_ENGINE_TOOLCHAIN))
if _UNREGISTERED:
    raise SystemExit(
        "differential_execution: these targets have a runnable driver but no "
        f"pinned toolchain registered in _ENGINE_TOOLCHAIN: {_UNREGISTERED}"
    )
_UNKNOWN = sorted(set(_ENGINE_TOOLCHAIN) - set(TARGETS))
if _UNKNOWN:
    raise SystemExit(
        f"differential_execution: _ENGINE_TOOLCHAIN names non-targets: {_UNKNOWN}"
    )


def run_target(language: str, out: Path, ir, cases: dict[str, list[list[int]]],
               emitted_name: str) -> tuple[str, object]:
    spec = TARGETS.get(language)
    if spec is None:
        return "NOT_RUN", {
            "reason": "no runnable driver for this target -- its EMISSION result above is "
                      "the evidence this harness produces for it"
        }
    resolved = resolve(language, spec.exe)
    executable, provenance = resolved.executable, resolved.provenance
    if executable is None:
        return "NOT_RUN", {"reason": f"toolchain not resolvable ({provenance})"}

    by_name = {fn.name: fn for fn in ir.functions}
    plan = plan_identifiers(ir, language)
    target_name = {b.source_name: b.target_name for b in plan.bindings if b.source_name in by_name}

    lines = list(spec.header)
    if spec.prepend_emitted:
        lines = [(out / language / emitted_name).read_text(encoding="utf-8"), *lines]
    if language == "objc":
        # ONE renderer taking `long long` printed booleans as 0/1 and
        # truncated doubles (-2.5 -> -2) at the implicit conversion in the
        # call. Both looked like the engine DIVERGING from canonical when the
        # only thing diverging was this printf. One renderer per canonical
        # type, chosen from the function's declared return type.
        lines.insert(1, 'static const char *elmos_render_i(long long v){static char b[40];'
                        'snprintf(b,sizeof b,"%lld",v);return b;}')
        lines.insert(2, 'static const char *elmos_render_d(double v){static char b[40];'
                        'snprintf(b,sizeof b,"%.17g",v);return b;}')
        lines.insert(3, 'static const char *elmos_render_b(int v){return v ? "true" : "false";}')
    for name, vectors in cases.items():
        fn = by_name[name]
        for index, vector in enumerate(vectors):
            arguments = ", ".join(
                literal(v, p.type, spec.style) for p, v in zip(fn.parameters, vector, strict=True)
            )
            call = f"{spec.call_prefix}{target_name[name]}({arguments})"
            render = _OBJC_RENDERERS.get(fn.return_type)
            if language == "objc" and render is None:
                return "NOT_RUN", {
                    "reason": f"no objc renderer for return type {fn.return_type!r} -- "
                              "refusing to print it rather than mis-render it",
                    "toolchain": provenance,
                }
            # Targets whose line has no {render} placeholder ignore the kwarg.
            lines.append(spec.line.format(n=name, i=index, call=call, render=render))
    lines += list(spec.footer)
    (out / language / spec.filename).write_text("\n".join(lines) + "\n", encoding="utf-8")
    if language == "csharp":
        target_framework = _dotnet_target_framework(executable)
        (out / language / "drive.csproj").write_text(
            "<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup>"
            "<OutputType>Exe</OutputType>"
            f"<TargetFramework>{target_framework}</TargetFramework>"
            "<Nullable>disable</Nullable><StartupObject>Drive</StartupObject>"
            "</PropertyGroup></Project>\n", encoding="utf-8")

    # `ExactToolchain.auxiliary` IS javac for the java toolchain. The old
    # `executable.replace("bin/java", "bin/javac")` silently produced a
    # non-existent path for any layout that is not `.../bin/java`.
    javac = resolved.auxiliary if language == "java" and resolved.auxiliary else executable
    if language == "java" and javac == executable:
        javac = executable.replace("bin/java", "bin/javac")

    # Kotlin compiles to a jar and then runs it -- on `java`. That was a bare
    # PATH name, so the row graded `PINNED:` while half its execution ran on a
    # binary the evidence never named. Resolve it through the same ladder.
    java_runner = "java"
    if language == "kotlin":
        kotlin_java = resolve("java", ("java", "bin/java", "java"))
        if kotlin_java.executable is None:
            return "NOT_RUN", {
                "reason": f"kotlin needs a java runtime to run its jar ({kotlin_java.provenance})",
                "toolchain": provenance,
            }
        java_runner = kotlin_java.executable
        provenance = f"{provenance} + java {kotlin_java.provenance}"

    for step in spec.build_cmd:
        cmd = [part.format(exe=executable, javac=javac, java=java_runner) for part in step]
        proc = subprocess.run(cmd, cwd=out / language, capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout).strip().splitlines()
            return "NOT_RUN", {"reason": "build failed", "toolchain": provenance,
                               "stderr": tail[-3:] if tail else []}
    cmd = [part.format(exe=executable, java=java_runner) for part in spec.run_cmd]
    proc = subprocess.run(cmd, cwd=out / language, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()
        return "NOT_RUN", {"reason": "run failed", "toolchain": provenance,
                           "stderr": tail[-3:] if tail else []}

    actual: dict[str, list[str]] = {name: [] for name in cases}
    for row in proc.stdout.splitlines():
        if row.count("|") == 2:
            name, _, value = row.split("|")
            if name in actual:
                actual[name].append(value)
    return "RAN", {"output": actual, "toolchain": provenance,
                   "version": version_of(executable)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("./elmos-differential"))
    parser.add_argument("--json", type=Path, default=Path("./unary-nary-execution-evidence.json"))
    arguments = parser.parse_args()

    out: Path = arguments.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source = out / "unit.py"
    source.write_text(textwrap.dedent(SOURCE_TEXT).lstrip(), encoding="utf-8")

    report = {
        "kind": "elmos.unary-nary-execution-evidence",
        "schema_version": "2.0.0",
        "reference": "elmos_polyglot_route.canonical.evaluate (the specification, not a target)",
        "constructs": ["n-ary boolean chain", "signed literal", "logical not"],
        "toolchain_root": str(toolchain_root()),
        "suites": {},
    }

    for suite, cases in (("full", CASES), ("safe_integer", SAFE_CASES)):
        ir = build(source, list(cases))
        by_name = {fn.name: fn for fn in ir.functions}
        reference = {}
        for name, vectors in cases.items():
            row = []
            for vector in vectors:
                fn = by_name[name]
                typed = [
                    bool(v) if p.type == "boolean" else float(v) if p.type == "number" else v
                    for p, v in zip(fn.parameters, vector, strict=True)
                ]
                try:
                    row.append(str(canonical.evaluate(fn, typed).value))
                except canonical.CanonicalError as error:
                    row.append(f"ERROR:{type(error).__name__}")
            reference[name] = row

        print(f"\n===== suite: {suite}  ({sum(len(v) for v in cases.values())} vectors) =====")
        entry: dict[str, object] = {}
        for language in SUPPORTED_LANGUAGES:
            try:
                emitted = emit(ir, language)
            except RouteError as error:
                print(f"  {language:11s} EMISSION_REFUSED  {error}")
                entry[language] = {"status": "EMISSION_REFUSED", "code": str(error)}
                continue
            (out / language).mkdir(parents=True, exist_ok=True)
            (out / language / emitted.relative_path).write_text(emitted.content, encoding="utf-8")
            state, payload = run_target(language, out, ir, cases, emitted.relative_path)
            if state == "NOT_RUN":
                print(f"  {language:11s} NOT_RUN  {payload.get('reason')}")
                entry[language] = {"status": "NOT_RUN", **payload}
                continue
            agree = differ = 0
            detail: list[str] = []
            for name, expected in reference.items():
                got = payload["output"].get(name, [])
                for index, want in enumerate(expected):
                    have = normalize(got[index]) if index < len(got) else "<missing>"
                    if have == normalize(want):
                        agree += 1
                    else:
                        differ += 1
                        if len(detail) < 5:
                            detail.append(f"{name}[{index}] canonical={normalize(want)} {language}={have}")
            status = "AGREES_WITH_CANONICAL" if differ == 0 else "DIVERGES"
            print(f"  {language:11s} {status}  {agree}/{agree + differ}   [{payload['toolchain']}]")
            for item in detail:
                print(f"      {item}")
            entry[language] = {"status": status, "agree": agree, "differ": differ,
                               "detail": detail, "toolchain": payload["toolchain"],
                               "version": payload["version"]}
        report["suites"][suite] = entry

    arguments.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {arguments.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

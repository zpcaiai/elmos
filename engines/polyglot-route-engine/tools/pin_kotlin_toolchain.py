#!/usr/bin/env python3.12
"""Emit the `_EXPECTED_KOTLIN_*` pin block for `toolchains._kotlin`.

Run this on the pinning host, with the Kotlin compiler distribution that route
evidence should be bound to, and paste the printed block over the corresponding
lines in `src/elmos_polyglot_route/toolchains.py`. Nothing here is a substitute
for reading what it printed: the point of the pin is that a human agreed to this
exact tree once, and every later run compares against that agreement.

    python3.12 tools/pin_kotlin_toolchain.py                    # discover the install
    python3.12 tools/pin_kotlin_toolchain.py /path/to/kotlin-compiler-2.4.10   # or name it

With no argument it looks at `kotlinc` on PATH, the usual Homebrew locations,
the global npm package root and the usual places a JetBrains release zip gets
unpacked, and refuses to guess if it finds more than one.

What gets pinned is the *versioned* install directory, never a symlinked
selector like `/opt/homebrew/bin/kotlinc` or `/opt/homebrew/opt/kotlin` -- a
selector can be repointed without any file under it changing, which is exactly
the drift the tree manifest exists to catch.

Kotlin is pinned as a plain versioned tree the way Go is: there is no runtime
identity document, because `kotlinc` is a shell script over a JVM and every
semantic question the PHP probe asks a running interpreter is answered here by
the compiler jar's digest instead. What Kotlin adds over Go is that the jar the
analyzer actually loads is called out by name and digest as well as being inside
the tree, so a swapped `lib/kotlin-compiler.jar` fails with that name in the
error rather than as one changed record out of thousands.
"""
from __future__ import annotations

import glob
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT / "src"))

# Import the two modules this script needs *without* executing the package
# __init__, which pulls in the engine (and therefore z3). A pinning script has no
# business requiring an SMT solver to be installed.
import types  # noqa: E402

_PACKAGE = "elmos_polyglot_route"
if _PACKAGE not in sys.modules:
    _stub = types.ModuleType(_PACKAGE)
    _stub.__path__ = [str(ENGINE_ROOT / "src" / _PACKAGE)]
    sys.modules[_PACKAGE] = _stub

from elmos_polyglot_route.models import RouteError  # noqa: E402
from elmos_polyglot_route.toolchains import (  # noqa: E402
    _kotlin_jvm_binding,
    _qualified_file_record,
    php_tree_identity,
    sanitized_subprocess_env,
)

#: The four paths that make a directory a Kotlin compiler distribution rather
#: than some other directory that happens to contain a `bin`. `build.txt` is
#: included because it is Kotlin's own build identity and its absence means this
#: is a repackaging that dropped it, not a stock distribution.
_REQUIRED_LAYOUT: tuple[str, ...] = (
    "bin/kotlinc",
    "bin/kotlin",
    "lib/kotlin-compiler.jar",
    "lib/kotlin-stdlib.jar",
    "build.txt",
)


def _is_distribution(root: Path) -> bool:
    """Does this directory look like a Kotlin compiler distribution?"""
    return all((root / relative).is_file() for relative in _REQUIRED_LAYOUT)


def _versioned_root(executable: Path) -> Path | None:
    """`.../kotlin/2.4.10/libexec/bin/kotlinc` -> `.../libexec`, following every symlink.

    Homebrew's `/opt/homebrew/bin/kotlinc` and `/opt/homebrew/opt/kotlin/libexec`
    are both selectors that point into a versioned Cellar directory, and npm's
    global `bin/kotlinc` is a selector into `lib/node_modules/kotlin-compiler`.
    The directory the links land in is what gets pinned: a selector can be
    repointed at a different build without any file under it changing, which is
    exactly the drift the tree manifest exists to catch.
    """
    try:
        resolved = executable.resolve(strict=True)
    except OSError:
        return None
    if resolved.parent.name != "bin":
        return None
    root = resolved.parent.parent
    if root in (Path("/"), Path("/usr"), Path("/usr/local"), Path("/opt"), Path("/opt/homebrew")):
        # A system-wide prefix is not a pinnable unit: it is root-owned and
        # shared with everything else on the host, so a tree manifest over it
        # would be neither ownable nor stable. Homebrew's versioned Cellar
        # directory, and the unpacked distribution directory, are the pinnable
        # units.
        return None
    if not _is_distribution(root):
        return None
    return root


def _npm_global_roots() -> list[Path]:
    """`$(npm root -g)/kotlin-compiler`, if this host installs Kotlin that way.

    Asked rather than guessed: the global root moves with the Node install (nvm,
    Homebrew and a system Node all answer differently), and a wrong guess here
    turns into "no Kotlin install found" on a host that has one.
    """
    npm = shutil.which("npm")
    if npm is None:
        return []
    try:
        completed = subprocess.run(
            [npm, "root", "-g"], capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    lines = completed.stdout.strip().splitlines()
    return [Path(lines[0]) / "kotlin-compiler"] if lines else []


def discover_roots() -> list[Path]:
    """Every plausible pinnable Kotlin distribution on this host, most likely first."""
    seen: dict[Path, None] = {}
    on_path = shutil.which("kotlinc")
    if on_path:
        root = _versioned_root(Path(on_path))
        if root is not None:
            seen[root] = None
    patterns = (
        "/opt/homebrew/Cellar/kotlin/*/libexec/bin/kotlinc",
        "/usr/local/Cellar/kotlin/*/libexec/bin/kotlinc",
        "/opt/homebrew/opt/kotlin/libexec/bin/kotlinc",
        "/usr/local/opt/kotlin/libexec/bin/kotlinc",
        "/opt/homebrew/lib/node_modules/kotlin-compiler/bin/kotlinc",
        "/usr/local/lib/node_modules/kotlin-compiler/bin/kotlinc",
        # A JetBrains release zip unpacks to `kotlinc/`; `kotlin-compiler-<version>/`
        # is what it is usually renamed to so two versions can sit side by side.
        "/opt/kotlin-compiler-*/bin/kotlinc",
        "/usr/local/kotlin-compiler-*/bin/kotlinc",
        f"{Path.home()}/kotlin-compiler-*/bin/kotlinc",
        f"{Path.home()}/kotlinc/bin/kotlinc",
        f"{Path.home()}/.local/share/elmos/toolchains/kotlin/*/bin/kotlinc",
    )
    for pattern in patterns:
        for candidate in sorted(glob.glob(pattern)):
            root = _versioned_root(Path(candidate))
            if root is not None:
                seen.setdefault(root, None)
    for package_root in _npm_global_roots():
        root = _versioned_root(package_root / "bin" / "kotlinc")
        if root is not None:
            seen.setdefault(root, None)
    return list(seen)


def _explain_unsafe_tree(root: Path) -> list[tuple[str, str]]:
    """Name every path that fails the tree contract, and say which rule it broke.

    `php_tree_identity` raises one opaque code for the whole tree, which is
    correct for a gate but useless for a human trying to fix the install. This
    re-walks the tree applying the same rules and reports the offenders. It is
    diagnostic only: it never relaxes anything, and `php_tree_identity` remains
    the sole authority on whether a tree is pinnable.

    Note what is deliberately *not* an offender: an ordinary symlink. A Kotlin
    distribution laid down by Homebrew or npm links its `bin` entries and
    sometimes `lib/kotlin-stdlib.jar` at a versioned sibling, and the probe
    records links as part of the pinned identity instead of refusing them. Only
    an escaping link to something the compiler process would load is fatal.
    """
    offenders: list[tuple[str, str]] = []
    try:
        paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    except OSError as error:
        return [(str(root), f"could not be walked: {error}")]
    for path in paths:
        try:
            metadata = path.lstat()
        except OSError as error:
            offenders.append((str(path), f"could not be inspected: {error}"))
            continue
        if stat.S_ISLNK(metadata.st_mode):
            try:
                resolved = path.resolve(strict=True)
            except OSError:
                offenders.append((str(path), "broken symlink; it resolves to nothing"))
                continue
            if metadata.st_uid != os.getuid():
                offenders.append((str(path), f"symlink owned by uid {metadata.st_uid}, not you"))
            elif not resolved.is_relative_to(root) and resolved.suffix in {".so", ".dylib", ".bundle"}:
                offenders.append((
                    str(path),
                    f"symlink -> {resolved}, a loadable object OUTSIDE the tree. "
                    "Anything the compiler could dlopen has to live inside the tree "
                    "the pin binds; this one cannot be bound.",
                ))
            elif not resolved.is_relative_to(root) and resolved.suffix == ".jar":
                offenders.append((
                    str(path),
                    f"symlink -> {resolved}, a jar OUTSIDE the tree. On the JVM a jar is "
                    "loadable code; the compiler classpath has to be bound by the pin.",
                ))
            # A symlink's own mode is not a permission on POSIX and is not
            # portable (0755 on macOS, 0777 on Linux), so it is not checked.
            continue
        if metadata.st_uid != os.getuid():
            offenders.append((str(path), f"owned by uid {metadata.st_uid}, not you"))
            continue
        if stat.S_IMODE(metadata.st_mode) & 0o022:
            offenders.append((
                str(path),
                f"mode {stat.S_IMODE(metadata.st_mode):04o} is group- or world-writable",
            ))
            continue
        if not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
            offenders.append((str(path), "is neither a regular file nor a directory"))
    return offenders


def _unbound_classpath_links(tree: dict[str, object]) -> list[tuple[str, str]]:
    """Unbound links that land on something the compiler would load anyway.

    `php_tree_identity` refuses an escaping link only when it resolves to a
    `.so`/`.dylib`/`.bundle`, which is the right rule for a C interpreter and
    half a rule for a JVM one: a jar on the compiler classpath is loadable code
    just as much as a dylib is, and anything under `lib/` is on that classpath
    by construction. Escaping links elsewhere in the tree -- a doc directory, a
    license file -- stay merely unbound, as they are for PHP.
    """
    unbound = tree["unbound_symlinks"]
    assert type(unbound) is dict
    return sorted(
        (name, target)
        for name, target in unbound.items()
        if name.startswith("lib/") or name.endswith(".jar")
    )


def _kotlinc_version(executable: Path) -> tuple[str | None, str]:
    """The `kotlinc -version` banner, and everything the process printed.

    `kotlinc` reports its version on *stderr*, prefixed `info: `, and exits
    non-zero on some builds because no source files were given -- so the exit
    code is not the signal, the presence of the banner line is. stdin is closed
    because a `kotlinc` that failed to parse its arguments falls through to the
    REPL and would otherwise wait forever on a terminal.
    """
    # Run under the SAME JVM the gate will use.  `kotlinc` prints the JRE it is
    # running on inside the banner, and `toolchains._kotlin` records that banner
    # as the expected version -- so pinning it under whatever JDK happens to be
    # ambient in the pinning shell produces a string the gate can never
    # reproduce, i.e. a permanent EXACT_TOOLCHAIN_MISMATCH:kotlin.  Both are
    # set because the launcher prefers ${JAVA_HOME}/bin/java and falls back to a
    # bare `java` from PATH.
    # Reuse the route engine's fully verified Kotlin/JVM binding. CI binds
    # Temurin while developer qualification may bind the Homebrew bundle;
    # hard-coding either home here makes a fresh Kotlin archive appear to have
    # tree drift before the tree can be checked. `_kotlin_jvm_binding` verifies
    # the Java/Javac/module/JVM/release digests, version banners, declared home,
    # and bundle signature before returning the home used below.
    java_home, _ = _kotlin_jvm_binding()
    with tempfile.TemporaryDirectory(prefix="elmos-kotlin-pin-env-") as temporary:
        environment_root = Path(temporary)
        environment_home = environment_root / "home"
        environment_tmp = environment_root / "tmp"
        environment_home.mkdir(mode=0o700)
        environment_tmp.mkdir(mode=0o700)
        environment = sanitized_subprocess_env(
            home=environment_home,
            temp_dir=environment_tmp,
            executable_dirs=(java_home / "bin", executable.parent),
        )
        environment["JAVA_HOME"] = str(java_home)
        completed = subprocess.run(
            [str(executable), "-version"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=300,
            check=False,
            env=environment,
        )
    printed = f"{completed.stderr}{completed.stdout}"
    for line in printed.splitlines():
        candidate = line.strip().removeprefix("info:").strip()
        if candidate.startswith("kotlinc"):
            return candidate, printed
    return None, printed


def main() -> int:
    if len(sys.argv) > 2:
        print(__doc__, file=sys.stderr)
        return 2

    if len(sys.argv) == 2:
        try:
            root = Path(sys.argv[1]).resolve(strict=True)
        except OSError:
            print(f"no such directory: {sys.argv[1]}", file=sys.stderr)
            print("run with no argument to see what this host actually has.", file=sys.stderr)
            return 2
    else:
        roots = discover_roots()
        if not roots:
            print("no Kotlin compiler distribution found.", file=sys.stderr)
            print(
                "looked at `kotlinc` on PATH, the usual Homebrew locations, the global npm "
                "package root and the usual unpacked-release directories.",
                file=sys.stderr,
            )
            print("if this host has no Kotlin: brew install kotlin", file=sys.stderr)
            return 2
        if len(roots) > 1:
            print("more than one Kotlin distribution found; pass the one to pin:", file=sys.stderr)
            for candidate in roots:
                print(f"    python3.12 {sys.argv[0]} {candidate}", file=sys.stderr)
            return 2
        root = roots[0]
        print(f"# discovered {root}", file=sys.stderr)

    anchor = root.parent
    missing = [relative for relative in _REQUIRED_LAYOUT if not (root / relative).is_file()]
    if missing:
        print(f"{root} is not a Kotlin compiler distribution; it is missing:", file=sys.stderr)
        for relative in missing:
            print(f"    {relative}", file=sys.stderr)
        print(
            "the argument must be the distribution root -- the directory holding `bin`, `lib` "
            "and `build.txt` -- not a bin directory and not a Homebrew prefix.",
            file=sys.stderr,
        )
        return 2

    executable = root / "bin" / "kotlinc"
    compiler_jar = root / "lib" / "kotlin-compiler.jar"
    stdlib_jar = root / "lib" / "kotlin-stdlib.jar"

    try:
        tree = php_tree_identity(root, anchor, "PIN_KOTLIN_TREE_UNSAFE")
        # These three are inside the tree digest already. They are recorded again
        # by name because they are the parts a human reviewing a drifted pin
        # needs identified: the launcher that runs, the jar the analyzer's parser
        # comes out of, and the stdlib every emitted unit compiles against.
        executable_record = _qualified_file_record(executable, root, "PIN_KOTLIN_EXECUTABLE_UNSAFE")
        compiler_record = _qualified_file_record(compiler_jar, root, "PIN_KOTLIN_COMPILER_JAR_UNSAFE")
        stdlib_record = _qualified_file_record(stdlib_jar, root, "PIN_KOTLIN_STDLIB_JAR_UNSAFE")
    except RouteError as error:
        print(f"refusing to pin {root}: {error}", file=sys.stderr)
        print(
            "the install tree must be owned by you, must not be group- or world-writable, "
            "and must not reach a loadable object outside itself through a symlink.",
            file=sys.stderr,
        )
        offenders = _explain_unsafe_tree(root)
        if offenders:
            print("", file=sys.stderr)
            print("offending paths:", file=sys.stderr)
            for offender, reason in offenders:
                print(f"    {offender}\n        {reason}", file=sys.stderr)
        else:
            print(
                "a system-wide Kotlin (root-owned, shared with the OS) cannot be pinned "
                "this way; install a per-user one, e.g. brew install kotlin",
                file=sys.stderr,
            )
        return 1

    escaping = _unbound_classpath_links(tree)
    if escaping:
        print(f"refusing to pin {root}: the compiler classpath leaves the tree:", file=sys.stderr)
        for name, target in escaping:
            print(f"    {name} -> {target}", file=sys.stderr)
        print(
            "a jar under lib/ is loaded into the compiler JVM, so its content has to be bound "
            "by the tree digest. Unpack a self-contained distribution rather than one whose "
            "jars are links into a shared, mutable directory.",
            file=sys.stderr,
        )
        return 1

    version, printed = _kotlinc_version(executable)
    if version is None:
        print(f"{executable} did not print a version banner.", file=sys.stderr)
        print("it printed:", file=sys.stderr)
        print(f"    {printed.strip()[:400] or '(nothing)'}", file=sys.stderr)
        print(
            "`kotlinc` is a shell script over a JVM: a missing or unusable JDK, or a JAVA_HOME "
            "pointing at one, lands here. Fix the JDK before pinning -- the JRE build is part "
            "of the version string this pin records.",
            file=sys.stderr,
        )
        return 1

    # Read after the manifest, so the bytes quoted here are bytes the tree digest
    # already covers rather than a second, unbound read of the same path.
    try:
        build_number = (root / "build.txt").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as error:
        print(f"refusing to pin {root}: build.txt could not be read: {error}", file=sys.stderr)
        return 1
    if not build_number:
        print(f"refusing to pin {root}: build.txt is empty.", file=sys.stderr)
        print(
            "build.txt is Kotlin's own build identity -- the one field that distinguishes two "
            "distributions reporting the same marketing version -- and an empty one cannot "
            "serve as it.",
            file=sys.stderr,
        )
        return 1

    print(f'_EXPECTED_KOTLIN_VERSION = {version!r}')
    print(f'_EXPECTED_KOTLIN_ROOT = Path({str(root)!r})')
    print(f'_EXPECTED_KOTLIN_ANCHOR = Path({str(anchor)!r})')
    print('_EXPECTED_KOTLINC_EXECUTABLE = _EXPECTED_KOTLIN_ROOT / "bin" / "kotlinc"')
    print(f'_EXPECTED_KOTLINC_EXECUTABLE_SHA256 = {executable_record["sha256"]!r}')
    print(f'_EXPECTED_KOTLINC_EXECUTABLE_BYTES = {executable_record["bytes"]!r}')
    print('_EXPECTED_KOTLIN_COMPILER_JAR = _EXPECTED_KOTLIN_ROOT / "lib" / "kotlin-compiler.jar"')
    print(f'_EXPECTED_KOTLIN_COMPILER_JAR_SHA256 = {compiler_record["sha256"]!r}')
    print(f'_EXPECTED_KOTLIN_COMPILER_JAR_BYTES = {compiler_record["bytes"]!r}')
    print('_EXPECTED_KOTLIN_STDLIB_JAR = _EXPECTED_KOTLIN_ROOT / "lib" / "kotlin-stdlib.jar"')
    print(f'_EXPECTED_KOTLIN_STDLIB_JAR_SHA256 = {stdlib_record["sha256"]!r}')
    print(f'_EXPECTED_KOTLIN_STDLIB_JAR_BYTES = {stdlib_record["bytes"]!r}')
    print(f'_EXPECTED_KOTLIN_TREE_SHA256 = {tree["sha256"]!r}')
    print(f'_EXPECTED_KOTLIN_TREE_RECORD_COUNT = {tree["record_count"]!r}')
    print(f'_EXPECTED_KOTLIN_TREE_FILE_COUNT = {tree["file_count"]!r}')
    print(f'_EXPECTED_KOTLIN_TREE_DIRECTORY_COUNT = {tree["directory_count"]!r}')
    print(f'_EXPECTED_KOTLIN_TREE_BYTES = {tree["bytes"]!r}')
    # Annotated because `toolchains.py` is checked under mypy strict, where an
    # empty dict literal has no inferable value type.
    print("_EXPECTED_KOTLIN_TREE_SYMLINKS: dict[str, str] = {")
    symlinks = tree["symlinks"]
    assert type(symlinks) is dict
    for name, target in sorted(symlinks.items()):
        print(f"    {name!r}: {target!r},")
    print("}")
    print("_EXPECTED_KOTLIN_TREE_UNBOUND_SYMLINKS: dict[str, str] = {")
    unbound = tree["unbound_symlinks"]
    assert type(unbound) is dict
    for name, target in sorted(unbound.items()):
        print(f"    {name!r}: {target!r},")
    print("}")
    print(f'_EXPECTED_KOTLIN_BUILD_NUMBER = {build_number!r}')
    print()

    if unbound:
        print(
            f"# NOTE: {len(unbound)} symlink(s) point outside the install root. Their content "
            "is NOT bound by this pin; the names are recorded so the set itself cannot change "
            "unnoticed:",
            file=sys.stderr,
        )
        for name, target in sorted(unbound.items()):
            print(f"#   {name} -> {target}", file=sys.stderr)
        print(file=sys.stderr)
    print(f"# build.txt says: {build_number}", file=sys.stderr)
    print(f"# kotlinc -version says: {version}", file=sys.stderr)
    print(
        "# the JRE named in that banner is NOT part of this tree: `kotlinc` runs under whatever "
        "JDK JAVA_HOME or PATH selects, and the version constant pins the pair. A JDK upgrade on "
        "this host will fail the probe with an unchanged Kotlin tree -- which is the honest "
        "outcome, because it is a different compiler process.",
        file=sys.stderr,
    )
    print(file=sys.stderr)
    print(
        "# paste the block above into src/elmos_polyglot_route/toolchains.py, over the existing "
        "_EXPECTED_KOTLIN_* constants.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

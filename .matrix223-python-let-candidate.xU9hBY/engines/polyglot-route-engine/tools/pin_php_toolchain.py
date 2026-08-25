#!/usr/bin/env python3.12
"""Emit the `_EXPECTED_PHP_*` pin block for `toolchains._php`.

Run this on the pinning host, with the PHP build that route evidence should be
bound to, and paste the printed block over the corresponding lines in
`src/elmos_polyglot_route/toolchains.py`. Nothing here is a substitute for
reading what it printed: the point of the pin is that a human agreed to this
exact tree once, and every later run compares against that agreement.

    python3.12 tools/pin_php_toolchain.py                     # discover the install
    python3.12 tools/pin_php_toolchain.py /path/to/php/8.4.21 # or name it

With no argument it looks at `php` on PATH and the usual Homebrew and
MacPorts locations, and refuses to guess if it finds more than one.

What gets pinned is the *versioned* install directory, never a symlinked
selector like `/opt/homebrew/bin/php` -- a selector can be repointed without
any file under it changing, which is exactly the drift the tree manifest
exists to catch.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT / "src"))

# Import the two modules this script needs *without* executing the package
# __init__, which pulls in the engine (and therefore z3). A pinning script and a
# route-pack generator have no business requiring an SMT solver to be installed.
import types  # noqa: E402

_PACKAGE = "elmos_polyglot_route"
if _PACKAGE not in sys.modules:
    _stub = types.ModuleType(_PACKAGE)
    _stub.__path__ = [str(ENGINE_ROOT / "src" / _PACKAGE)]
    sys.modules[_PACKAGE] = _stub

from elmos_polyglot_route.models import RouteError  # noqa: E402
from elmos_polyglot_route.toolchains import (  # noqa: E402
    _PHP_RUNTIME_IDENTITY_SCRIPT,
    _qualified_file_record,
    php_tree_identity,
)


def _versioned_root(executable: Path) -> Path | None:
    """`.../php/8.4.21/bin/php` -> `.../php/8.4.21`, following every symlink.

    Homebrew's `/opt/homebrew/bin/php` and `/opt/homebrew/opt/php/bin/php` are
    both selectors that point into a versioned Cellar directory. The versioned
    directory is what gets pinned: a selector can be repointed at a different
    build without any file under it changing, which is exactly the drift the
    tree manifest exists to catch.
    """
    try:
        resolved = executable.resolve(strict=True)
    except OSError:
        return None
    if resolved.parent.name != "bin":
        return None
    root = resolved.parent.parent
    if root in (Path("/"), Path("/usr"), Path("/usr/local"), Path("/opt/homebrew")):
        # A system-wide prefix is not a pinnable unit: it is root-owned and
        # shared with everything else on the host, so a tree manifest over it
        # would be neither ownable nor stable. Homebrew's versioned Cellar
        # directory is the pinnable unit.
        return None
    return root


def discover_roots() -> list[Path]:
    """Every plausible pinned PHP install on this host, most likely first."""
    seen: dict[Path, None] = {}
    on_path = shutil.which("php")
    if on_path:
        root = _versioned_root(Path(on_path))
        if root is not None:
            seen[root] = None
    patterns = (
        "/opt/homebrew/Cellar/php*/*/bin/php",
        "/usr/local/Cellar/php*/*/bin/php",
        "/opt/homebrew/opt/php*/bin/php",
        "/usr/local/opt/php*/bin/php",
        "/opt/local/bin/php",
        "/usr/bin/php",
    )
    for pattern in patterns:
        for candidate in sorted(glob.glob(pattern)):
            root = _versioned_root(Path(candidate))
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

    Note what is deliberately *not* an offender any more: an ordinary symlink.
    A stock Homebrew PHP ships `bin/phar -> bin/phar.phar` and
    `pecl -> /opt/homebrew/lib/php/pecl`, and the probe now records links as
    part of the pinned identity instead of refusing them. Only an escaping link
    to a loadable object is still fatal.
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
                    "Anything the interpreter could dlopen has to live inside the tree "
                    "the pin binds; this one cannot be bound.",
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
            print("no PHP install found.", file=sys.stderr)
            print("looked at `php` on PATH and the usual Homebrew/MacPorts locations.", file=sys.stderr)
            print("if this host has no PHP: brew install php", file=sys.stderr)
            return 2
        if len(roots) > 1:
            print("more than one PHP install found; pass the one to pin:", file=sys.stderr)
            for candidate in roots:
                print(f"    python3.12 {sys.argv[0]} {candidate}", file=sys.stderr)
            return 2
        root = roots[0]
        print(f"# discovered {root}", file=sys.stderr)

    anchor = root.parent
    executable = root / "bin" / "php"
    if not executable.is_file():
        print(f"no php executable at {executable}", file=sys.stderr)
        print("the argument must be the versioned install root, not a bin directory.", file=sys.stderr)
        return 2

    try:
        tree = php_tree_identity(root, anchor, "PIN_PHP_TREE_UNSAFE")
        record = _qualified_file_record(executable, root, "PIN_PHP_EXECUTABLE_UNSAFE")
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
                "a system-wide PHP (root-owned, shared with the OS) cannot be pinned "
                "this way; install a per-user one, e.g. brew install php",
                file=sys.stderr,
            )
        return 1

    version = subprocess.run(
        [str(executable), "-n", "--version"], capture_output=True, text=True, check=True
    ).stdout.splitlines()[0].strip()
    identity_raw = subprocess.run(
        [str(executable), "-n", "-r", _PHP_RUNTIME_IDENTITY_SCRIPT],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    try:
        document = json.loads(identity_raw)
    except json.JSONDecodeError:
        print(f"{executable} did not return the runtime identity document.", file=sys.stderr)
        print("it printed:", file=sys.stderr)
        print(f"    {identity_raw.strip()[:400] or '(nothing)'}", file=sys.stderr)
        print(
            "this has to be a real PHP CLI binary that can run `-r`; a wrapper script or "
            "a build with a fatal startup error will land here.",
            file=sys.stderr,
        )
        return 1
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    identity_digest = hashlib.sha256(canonical).hexdigest()

    if document["int_size"] != 8:
        print(f"refusing to pin: PHP_INT_SIZE is {document['int_size']}, not 8", file=sys.stderr)
        return 1
    if document["float_dig"] != 15:
        print(f"refusing to pin: PHP_FLOAT_DIG is {document['float_dig']}, not 15", file=sys.stderr)
        return 1

    print(f'_EXPECTED_PHP_VERSION = {version!r}')
    print(f'_EXPECTED_PHP_ROOT = Path({str(root)!r})')
    print(f'_EXPECTED_PHP_ANCHOR = Path({str(anchor)!r})')
    print('_EXPECTED_PHP_EXECUTABLE = _EXPECTED_PHP_ROOT / "bin" / "php"')
    print(f'_EXPECTED_PHP_EXECUTABLE_SHA256 = {record["sha256"]!r}')
    print(f'_EXPECTED_PHP_EXECUTABLE_BYTES = {record["bytes"]!r}')
    print(f'_EXPECTED_PHP_TREE_SHA256 = {tree["sha256"]!r}')
    print(f'_EXPECTED_PHP_TREE_RECORD_COUNT = {tree["record_count"]!r}')
    print(f'_EXPECTED_PHP_TREE_FILE_COUNT = {tree["file_count"]!r}')
    print(f'_EXPECTED_PHP_TREE_DIRECTORY_COUNT = {tree["directory_count"]!r}')
    print(f'_EXPECTED_PHP_TREE_BYTES = {tree["bytes"]!r}')
    print("_EXPECTED_PHP_TREE_SYMLINKS = {")
    for name, target in sorted(tree["symlinks"].items()):
        print(f"    {name!r}: {target!r},")
    print("}")
    print("_EXPECTED_PHP_TREE_UNBOUND_SYMLINKS = {")
    for name, target in sorted(tree["unbound_symlinks"].items()):
        print(f"    {name!r}: {target!r},")
    print("}")
    if "tokenizer" in document["extensions"]:
        tokenizer = "builtin"
    else:
        # `-n` drops the ini that would have loaded it, so it has to be named
        # explicitly -- and from inside the install root, or the object the
        # frontend's own parser comes from is not covered by the tree digest.
        candidates = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("tokenizer.so")
            if path.is_file()
        )
        if not candidates:
            print(
                f"refusing to pin {root}: this build does not have ext/tokenizer compiled in, "
                "and no tokenizer.so was found inside the install root.",
                file=sys.stderr,
            )
            print(
                "the PHP frontend is built on token_get_all(); without it no PHP source can "
                "be analyzed. Install a PHP whose tokenizer is builtin, or one whose shared "
                "tokenizer.so lives under the versioned install root.",
                file=sys.stderr,
            )
            return 1
        if len(candidates) > 1:
            print(f"refusing to pin {root}: more than one tokenizer.so inside the root:", file=sys.stderr)
            for candidate in candidates:
                print(f"    {candidate}", file=sys.stderr)
            return 1
        tokenizer = candidates[0]
    print(f'_EXPECTED_PHP_TOKENIZER = {tokenizer!r}')
    print(f'_EXPECTED_PHP_RUNTIME_IDENTITY_SHA256 = {identity_digest!r}')
    print()
    if tree["unbound_symlinks"]:
        print(
            f"# NOTE: {len(tree['unbound_symlinks'])} symlink(s) point outside the install "
            "root. Their content is NOT bound by this pin; the names are recorded so the "
            "set itself cannot change unnoticed:",
            file=sys.stderr,
        )
        for name, target in sorted(tree["unbound_symlinks"].items()):
            print(f"#   {name} -> {target}", file=sys.stderr)
        print(file=sys.stderr)
    print("# runtime identity document this digest covers:", file=sys.stderr)
    print(json.dumps(document, indent=2, sort_keys=True), file=sys.stderr)
    print(file=sys.stderr)
    print(
        f"# also set identifier_hygiene._PHP_DIALECT to "
        f"'php-{document['php_version']}-strict-types'",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

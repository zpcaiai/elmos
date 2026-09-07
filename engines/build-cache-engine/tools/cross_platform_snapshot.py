#!/usr/bin/env python3
"""Build one fixed repository and print the snapshot digest this platform gets.

Gate 1 asks for the *same* root digest on Linux, macOS and Windows. That cannot
be asserted from one machine, so it is captured instead: run this script on each
platform and paste its JSON line into
``tests/fixtures/cross_platform_snapshot.json``. The test suite then asserts
that the platform it is running on agrees with every digest recorded there, and
says which platforms are still missing rather than passing quietly.

The fixture is built from bytes, not copied from a checkout, so the only thing
that can differ between platforms is the platform.

Runs on Python 3.10+ so it can be executed on hosts that cannot run the engine
itself. Usage::

    python3 tools/cross_platform_snapshot.py            # print the digest
    python3 tools/cross_platform_snapshot.py --directory /tmp/fixture --keep
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elmos_build_cache.snapshot import take_snapshot  # noqa: E402

#: ``(relative path, bytes, executable)``. Deliberately awkward: composed
#: Unicode, CRLF, a BOM, an empty file, a deep path and an executable bit.
FIXTURE: tuple[tuple[str, bytes, bool], ...] = (
    ("README.md", b"# cross-platform fixture\n", False),
    ("src/main/java/com/demo/App.java", b"public class App {}\n", False),
    ("src/main/resources/app.properties", b"name=demo\r\nversion=1\r\n", False),
    ("src/main/resources/bom.txt", b"\xef\xbb\xbfwith a byte order mark\n", False),
    ("docs/café/naïve.md", b"# accents stay composed\n", False),
    ("docs/empty.txt", b"", False),
    ("scripts/run.sh", b"#!/bin/sh\necho hello\n", True),
    ("a/b/c/d/e/f/g/deep.txt", b"deep\n", False),
)


def build(directory: Path) -> None:
    for relative, payload, executable in FIXTURE:
        # NFC explicitly: a macOS filesystem may hand the name back decomposed,
        # and the point of the fixture is that this does not matter.
        path = directory / unicodedata.normalize("NFC", relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        if executable:
            path.chmod(0o755)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=None)
    parser.add_argument("--keep", action="store_true")
    arguments = parser.parse_args()

    directory = arguments.directory or Path(tempfile.mkdtemp(prefix="elmos-xplat-"))
    directory.mkdir(parents=True, exist_ok=True)
    try:
        build(directory)
        snapshot = take_snapshot(directory)
        print(
            json.dumps(
                {
                    "platform": platform.system().lower(),
                    "release": platform.release(),
                    "python": platform.python_version(),
                    "files": len(snapshot.entries),
                    "root_digest": snapshot.root_digest,
                    "manifest_digest": snapshot.manifest_digest,
                },
                sort_keys=True,
            )
        )
    finally:
        if not arguments.keep and arguments.directory is None:
            shutil.rmtree(directory, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

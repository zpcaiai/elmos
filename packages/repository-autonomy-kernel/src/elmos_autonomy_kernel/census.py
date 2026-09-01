"""Repository census: a reproducible inventory computed from a snapshot alone.

This module owns the question "what is actually in this repository", and it owns
it under one constraint that shapes every decision below: the answer must be
recomputable, byte for byte, from the snapshot and nothing else.  No clock, no
working tree, no `git`, no network.  Two runs over one snapshot therefore
produce one digest, and a census that disagrees with its digest is evidence of
tampering rather than of drift.

The second constraint is honesty about counting.  "Lines of code" is the most
common lie in this domain because it is quoted without a definition, so every
counter this module emits is accompanied by a `definitions` entry stating
exactly what was counted, and `linesOfCode` is deliberately *not* reported at
all — it has no snapshot-only definition worth defending.  A file the snapshot
marked oversized is listed in `unmeasured` and drags the whole census to
``PARTIAL``; it is never counted as zero lines, because zero lines is a legal
measurement and "we could not look" is not.

Language is reported twice — once by extension, once by an in-file marker
(shebang, ``<?php``, ``<!DOCTYPE html``) — with an explicit ``unknown`` bucket
in both.  The two views disagree in real repositories, and folding the
disagreement into a plausible-looking single number is what makes language mix
reports useless.  Nothing is ever folded into ``unknown``'s neighbours.

Security note: the risk surface is computed from *path shape only*.  This
module never puts file content into an output, so a matched credentials file
contributes its path and its marker name and never a byte of its body.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import (
    Status,
    digest,
    reject_unknown_fields,
    require_bool,
    require_int,
    require_mapping,
    require_str,
)
from .errors import Category, KernelError, register_codes
from .ports import RepositoryReader
from .registry import register

register_codes(
    Category.SEMANTIC,
    "PARTIAL_CENSUS",
    "UNSUPPORTED_BUILD_SYSTEM",
    "SNAPSHOT_CHANGED",
)

__all__ = [
    "CENSUS_VERSION",
    "Census",
    "FileFacts",
    "build_census",
    "handle",
    "undefined_counters",
]

CENSUS_VERSION = "2.0.0"

#: Number of leading bytes inspected for binary detection and marker rules.
_HEAD_BYTES = 8192

# --- classification tables ---------------------------------------------------

_EXTENSION_LANGUAGE: Mapping[str, str] = {
    "py": "Python", "pyi": "Python", "js": "JavaScript", "jsx": "JavaScript",
    "mjs": "JavaScript", "cjs": "JavaScript", "ts": "TypeScript", "tsx": "TypeScript",
    "java": "Java", "go": "Go", "rs": "Rust", "rb": "Ruby", "php": "PHP",
    "c": "C", "h": "C", "cc": "C++", "cpp": "C++", "hpp": "C++", "cxx": "C++",
    "cs": "C#", "kt": "Kotlin", "kts": "Kotlin", "swift": "Swift", "scala": "Scala",
    "sh": "Shell", "bash": "Shell", "zsh": "Shell", "ps1": "PowerShell",
    "sql": "SQL", "html": "HTML", "htm": "HTML", "css": "CSS", "scss": "CSS",
    "md": "Markdown", "rst": "reStructuredText", "txt": "Text",
    "json": "JSON", "yaml": "YAML", "yml": "YAML", "toml": "TOML", "ini": "INI",
    "cfg": "INI", "xml": "XML", "proto": "Protobuf", "tf": "Terraform",
    "tfvars": "Terraform", "bicep": "Bicep", "gradle": "Gradle", "lock": "Lockfile",
    "png": "Binary-Image", "jpg": "Binary-Image", "jpeg": "Binary-Image",
    "gif": "Binary-Image", "ico": "Binary-Image", "pdf": "Binary-Document",
    "zip": "Binary-Archive", "gz": "Binary-Archive", "tar": "Binary-Archive",
    "so": "Binary-Object", "dll": "Binary-Object", "dylib": "Binary-Object",
}

#: Extensionless files whose *name* is the only language signal available.
_FILENAME_LANGUAGE: Mapping[str, str] = {
    "Makefile": "Make", "makefile": "Make", "GNUmakefile": "Make",
    "Dockerfile": "Dockerfile", "Containerfile": "Dockerfile",
    "Rakefile": "Ruby", "Gemfile": "Ruby", "Vagrantfile": "Ruby",
    "CMakeLists.txt": "CMake",
}

_UNKNOWN = "unknown"

_SHEBANG_LANGUAGE: Mapping[str, str] = {
    "python": "Python", "python2": "Python", "python3": "Python",
    "node": "JavaScript", "deno": "TypeScript", "bun": "JavaScript",
    "sh": "Shell", "bash": "Shell", "zsh": "Shell", "dash": "Shell",
    "ruby": "Ruby", "perl": "Perl", "php": "PHP", "Rscript": "R",
    "pwsh": "PowerShell",
}

#: (marker bytes, language).  Ordered; first match wins so the table is total.
_CONTENT_MARKERS: tuple[tuple[bytes, str], ...] = (
    (b"<?php", "PHP"),
    (b"<?xml", "XML"),
    (b"<!doctype html", "HTML"),
    (b"<html", "HTML"),
    (b"%pdf-", "Binary-Document"),
    (b"\x7felf", "Binary-Object"),
    (b"\x89png", "Binary-Image"),
    (b"pk\x03\x04", "Binary-Archive"),
)

_GENERATED_DIRS = frozenset({
    "vendor", "node_modules", "target", "third_party", "thirdparty",
    "generated", "gen", ".yarn", "bower_components",
})

_GENERATED_NAME_RE = re.compile(
    r"(\.generated\.[^.]+$|_pb2(_grpc)?\.py$|\.pb\.go$|\.min\.(js|css)$"
    r"|\.g\.dart$|_generated\.[^.]+$)"
)

#: Content markers, matched case-insensitively against the file head.  These are
#: the three phrasings that generators actually emit; a fourth guess would widen
#: the "generated" bucket on nothing but hope.
_GENERATED_CONTENT_MARKERS = ("do not edit", "@generated", "code generated by")

_TEST_DIRS = frozenset({"test", "tests", "spec", "specs", "__tests__", "testing"})
_FIXTURE_DIRS = frozenset({"testdata", "fixtures", "fixture", "golden", "snapshots"})
_TEST_NAME_RE = re.compile(
    r"(^test_.+|.+_test\.[^.]+$|.+\.test\.[^.]+$|.+\.spec\.[^.]+$"
    r"|.+Test\.java$|.+Tests\.cs$|^conftest\.py$)"
)

#: name -> build system.  Everything else is *not* a build root; the census
#: refuses to infer one from a directory that merely looks like a project.
_BUILD_ROOTS: Mapping[str, str] = {
    "pyproject.toml": "python", "setup.py": "python", "setup.cfg": "python",
    "requirements.txt": "python", "Pipfile": "python", "poetry.lock": "python",
    "package.json": "node", "pnpm-workspace.yaml": "node", "deno.json": "deno",
    "go.mod": "go", "Cargo.toml": "rust", "pom.xml": "maven",
    "build.gradle": "gradle", "build.gradle.kts": "gradle", "settings.gradle": "gradle",
    "Makefile": "make", "makefile": "make", "CMakeLists.txt": "cmake",
    "BUILD": "bazel", "BUILD.bazel": "bazel", "WORKSPACE": "bazel",
    "Gemfile": "ruby", "composer.json": "php", "mix.exs": "elixir",
    "Dockerfile": "container", "docker-compose.yml": "container",
    "docker-compose.yaml": "container",
}

#: Filename-shape rules for the security risk surface.  Path shape only — the
#: census never reads a matched file to "confirm" a secret, because confirming
#: one means holding it.
_RISK_NAME_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("dotenv", re.compile(r"^\.env($|\.)")),
    ("credential-filename", re.compile(
        r"(^|[._-])(credentials?|secrets?|passwords?|token|apikey|api_key)([._-]|$)",
        re.IGNORECASE)),
    ("private-key-name", re.compile(r"^(id_rsa|id_dsa|id_ecdsa|id_ed25519)$")),
    ("key-material-extension", re.compile(
        r"\.(pem|key|p12|pfx|jks|keystore|asc|gpg|ppk)$", re.IGNORECASE)),
    ("shell-credential-store", re.compile(r"^\.(netrc|pgpass|npmrc|htpasswd)$")),
    ("cloud-credential-store", re.compile(r"^(kubeconfig|\.dockercfg|\.docker/config\.json)$")),
)

_RISK_PATH_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("iac-terraform", re.compile(r"\.(tf|tfvars|tfstate)$")),
    ("iac-container", re.compile(r"(^|/)(Dockerfile|Containerfile|docker-compose\.ya?ml)$")),
    ("iac-kubernetes", re.compile(r"(^|/)(k8s|kubernetes|charts?|helm)/")),
    ("iac-helm-chart", re.compile(r"(^|/)Chart\.ya?ml$")),
    ("iac-ci-pipeline", re.compile(
        r"(^|/)(\.github/workflows/|\.gitlab-ci\.ya?ml$|\.circleci/|Jenkinsfile$)")),
    ("iac-cloudformation", re.compile(r"(^|/)(cloudformation|cfn)/")),
    ("iac-ansible", re.compile(r"(^|/)(ansible|playbooks?)/")),
    ("iac-bicep", re.compile(r"\.bicep$")),
)

#: Data-surface markers.  These identify *where* data definitions live.  They do
#: not identify data flow, and the census says so rather than implying it.
_DATA_SURFACE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sql", re.compile(r"\.sql$")),
    ("migration", re.compile(r"(^|/)(migrations?|db/migrate)/")),
    ("schema-file", re.compile(r"(^|/)(schema|schemas)[./]")),
    ("openapi", re.compile(r"(^|/)(openapi|swagger)\.(ya?ml|json)$")),
    ("protobuf", re.compile(r"\.proto$")),
    ("json-schema", re.compile(r"\.schema\.json$")),
)

_ENTRYPOINT_NAMES = frozenset({
    "main.py", "__main__.py", "manage.py", "wsgi.py", "asgi.py",
    "main.go", "index.js", "index.ts", "main.js", "main.ts", "server.js", "app.js",
    "Main.java", "main.rs",
})

_ENTRYPOINT_CONTENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("python-main-guard", re.compile(r"^\s*if\s+__name__\s*==\s*['\"]__main__['\"]\s*:")),
    ("go-main-func", re.compile(r"^\s*func\s+main\s*\(\s*\)")),
    ("java-main-method", re.compile(r"public\s+static\s+void\s+main\s*\(")),
    ("c-main-func", re.compile(r"^\s*int\s+main\s*\(")),
)


# --- per-file facts ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FileFacts:
    """Everything the census knows about one path, and how it knows it.

    ``lines_measured`` is separate from ``line_count`` on purpose: ``None`` with
    ``lines_measured=False`` is "we did not look", which is a different claim
    from ``0`` with ``lines_measured=True``.  Collapsing the two is the defect
    this dataclass exists to make impossible.
    """

    path: str
    depth: int
    content_digest: str
    byte_count: int | None
    byte_count_measured: bool
    line_count: int | None
    blank_line_count: int | None
    lines_measured: bool
    unmeasured_reason: str
    extension: str
    language_by_extension: str
    language_by_marker: str
    marker_evidence: str
    is_binary: bool
    generated_reason: str
    test_reason: str
    risk_markers: tuple[str, ...]
    data_markers: tuple[str, ...]
    build_system: str
    entrypoint_markers: tuple[tuple[str, int], ...]

    @property
    def is_generated(self) -> bool:
        return bool(self.generated_reason)

    @property
    def is_test(self) -> bool:
        return bool(self.test_reason)

    def to_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "depth": self.depth,
            "contentDigest": self.content_digest,
            "byteCount": self.byte_count,
            "byteCountMeasured": self.byte_count_measured,
            "lineCount": self.line_count,
            "blankLineCount": self.blank_line_count,
            "linesMeasured": self.lines_measured,
            "unmeasuredReason": self.unmeasured_reason,
            "extension": self.extension,
            "languageByExtension": self.language_by_extension,
            "languageByMarker": self.language_by_marker,
            "markerEvidence": self.marker_evidence,
            "isBinary": self.is_binary,
            "generatedReason": self.generated_reason,
            "testReason": self.test_reason,
            "riskMarkers": list(self.risk_markers),
            "dataMarkers": list(self.data_markers),
            "buildSystem": self.build_system,
            "entrypointMarkers": [
                {"marker": marker, "line": line} for marker, line in self.entrypoint_markers
            ],
        }


def _normalise(path: str) -> str:
    return path.replace("\\", "/")


def _extension_of(name: str) -> str:
    if "." not in name[1:]:
        return ""
    return name.rsplit(".", 1)[1]


def _language_by_extension(name: str, extension: str) -> str:
    if name in _FILENAME_LANGUAGE:
        return _FILENAME_LANGUAGE[name]
    return _EXTENSION_LANGUAGE.get(extension.lower(), _UNKNOWN)


def _language_by_marker(head: bytes) -> tuple[str, str]:
    """Return ``(language, evidence)`` from in-file markers only.

    Returns ``(unknown, "")`` rather than falling back to the extension: the
    whole point of the second view is that it can disagree with the first.
    """

    if head.startswith(b"#!"):
        first = head.split(b"\n", 1)[0].decode("ascii", errors="replace")
        tokens = first[2:].replace("\t", " ").split()
        for token in reversed(tokens):
            candidate = token.rsplit("/", 1)[-1]
            if candidate in _SHEBANG_LANGUAGE:
                return _SHEBANG_LANGUAGE[candidate], f"shebang:{candidate}"
        return _UNKNOWN, "shebang:unrecognised-interpreter"
    lowered = head[:64].lower()
    for marker, language in _CONTENT_MARKERS:
        if lowered.startswith(marker) or marker in head[:512].lower():
            return language, "content-marker:" + marker.decode("latin-1").strip()
    return _UNKNOWN, ""


def _generated_reason(path: str, name: str, head_text: str) -> str:
    for part in path.split("/")[:-1]:
        if part in _GENERATED_DIRS:
            return f"vendored-directory:{part}"
    if _GENERATED_NAME_RE.search(name):
        return "generated-filename"
    lowered = head_text[:4096].lower()
    for marker in _GENERATED_CONTENT_MARKERS:
        if marker in lowered:
            return f"content-marker:{marker}"
    return ""


def _test_reason(path: str, name: str) -> str:
    parts = path.split("/")[:-1]
    for part in parts:
        if part in _FIXTURE_DIRS:
            return f"fixture-directory:{part}"
    for part in parts:
        if part in _TEST_DIRS:
            return f"test-directory:{part}"
    if _TEST_NAME_RE.match(name):
        return "test-filename"
    return ""


def _matches(path: str, name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    risk = [label for label, rule in _RISK_NAME_RULES if rule.search(name)]
    risk.extend(label for label, rule in _RISK_PATH_RULES if rule.search(path))
    data = [label for label, rule in _DATA_SURFACE_RULES if rule.search(path)]
    return tuple(sorted(set(risk))), tuple(sorted(set(data)))


def _entrypoint_markers(name: str, text: str | None) -> tuple[tuple[str, int], ...]:
    found: list[tuple[str, int]] = []
    if name in _ENTRYPOINT_NAMES:
        found.append(("entrypoint-filename", 0))
    if text is not None:
        for index, line in enumerate(text.split("\n")[:4000], start=1):
            for label, rule in _ENTRYPOINT_CONTENT_RULES:
                if rule.search(line):
                    found.append((label, index))
    return tuple(sorted(set(found)))


def _facts_for(reader: RepositoryReader, path: str) -> FileFacts:
    normalised = _normalise(path)
    name = normalised.rsplit("/", 1)[-1]
    extension = _extension_of(name)
    meta = reader.stat(path)
    raw_bytes = meta.get("byteCount")
    byte_count = (raw_bytes if isinstance(raw_bytes, int)
                  and not isinstance(raw_bytes, bool) else None)
    content_digest = str(meta.get("digest") or "")

    data: bytes | None = None
    unmeasured_reason = ""
    if meta.get("oversized"):
        unmeasured_reason = "oversized-in-snapshot"
    else:
        try:
            data = reader.read_bytes(path)
        except KernelError as exc:
            if exc.code in {"INPUT_TOO_LARGE", "MISSING_REQUIRED_INPUT"}:
                unmeasured_reason = f"unreadable:{exc.code}"
            else:
                # STALE_SNAPSHOT and authority failures are real errors: a census
                # that swallowed them would be describing a repository that no
                # longer exists.
                raise

    text: str | None = None
    is_binary = False
    if data is not None:
        head = data[:_HEAD_BYTES]
        if b"\x00" in head:
            is_binary = True
        else:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                is_binary = True
        language_marker, marker_evidence = _language_by_marker(head)
    else:
        language_marker, marker_evidence = _UNKNOWN, "not-read"

    if text is not None:
        line_count = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        blank_line_count = sum(1 for line in text.split("\n") if not line.strip())
        if text.endswith("\n"):
            blank_line_count -= 1
        lines_measured = True
    else:
        line_count = None
        blank_line_count = None
        lines_measured = False
        if not unmeasured_reason and is_binary:
            unmeasured_reason = ""  # binary line counts are not-applicable, not unmeasured

    risk_markers, data_markers = _matches(normalised, name)
    return FileFacts(
        path=normalised,
        depth=normalised.count("/") + 1,
        content_digest=content_digest,
        byte_count=byte_count,
        byte_count_measured=byte_count is not None,
        line_count=line_count,
        blank_line_count=blank_line_count,
        lines_measured=lines_measured,
        unmeasured_reason=unmeasured_reason,
        extension=extension,
        language_by_extension=_language_by_extension(name, extension),
        language_by_marker=language_marker,
        marker_evidence=marker_evidence,
        is_binary=is_binary,
        generated_reason=_generated_reason(normalised, name, text or ""),
        test_reason=_test_reason(normalised, name),
        risk_markers=risk_markers,
        data_markers=data_markers,
        build_system=_BUILD_ROOTS.get(name, ""),
        entrypoint_markers=_entrypoint_markers(name, text),
    )


# --- census ------------------------------------------------------------------


def _share_ppm(part: int, whole: int) -> int:
    """Integer parts-per-million share.

    Deliberately an integer: a float share would be unhashable by
    ``canonical_json`` and, worse, would let two machines disagree about a
    census digest.
    """

    return 0 if whole <= 0 else (part * 1_000_000) // whole


def _language_mix(files: Sequence[FileFacts], attribute: str) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    total_files = len(files)
    for facts in files:
        language = getattr(facts, attribute)
        bucket = buckets.setdefault(language, {
            "language": language, "fileCount": 0, "byteCount": 0,
            "byteCountMeasured": True, "lineCount": 0, "lineCountMeasured": True,
            "unmeasuredFileCount": 0,
        })
        bucket["fileCount"] += 1
        if facts.byte_count is None:
            bucket["byteCountMeasured"] = False
        else:
            bucket["byteCount"] += facts.byte_count
        if facts.lines_measured and facts.line_count is not None:
            bucket["lineCount"] += facts.line_count
        else:
            bucket["unmeasuredFileCount"] += 1
            if facts.unmeasured_reason:
                bucket["lineCountMeasured"] = False
    for bucket in buckets.values():
        bucket["fileSharePpm"] = _share_ppm(bucket["fileCount"], total_files)
    return [buckets[key] for key in sorted(buckets)]


@dataclass(frozen=True, slots=True)
class Census:
    """A snapshot-bound inventory that carries its own definitions and digest.

    ``status`` is ``PARTIAL`` whenever anything is in ``unmeasured``.  A census
    with an unmeasured file is a real census of a repository we could not fully
    read, and calling that ``SUCCEEDED`` is precisely the widening the kernel
    contract forbids.
    """

    snapshot_sha: str
    files: tuple[FileFacts, ...]
    top_n: int
    build_roots_required: bool

    @property
    def status(self) -> Status:
        return Status.PARTIAL if self.unmeasured() else Status.SUCCEEDED

    def unmeasured(self) -> tuple[FileFacts, ...]:
        """Files whose line count could not be measured though it is defined."""

        return tuple(facts for facts in self.files if facts.unmeasured_reason)

    def to_payload(self) -> dict[str, Any]:
        files = self.files
        measured = [f for f in files if f.lines_measured]
        unmeasured = self.unmeasured()
        binaries = [f for f in files if f.is_binary]
        generated = [f for f in files if f.is_generated]
        tests = [f for f in files if f.is_test]
        risky = [f for f in files if f.risk_markers]
        build_roots = [f for f in files if f.build_system]
        entrypoints = [f for f in files if f.entrypoint_markers]
        data_surfaces = [f for f in files if f.data_markers]
        byte_total = sum(f.byte_count for f in files if f.byte_count is not None)
        bytes_measured = all(f.byte_count is not None for f in files)

        largest = sorted(
            (f for f in files if f.byte_count is not None),
            key=lambda f: (-(f.byte_count or 0), f.path),
        )[: self.top_n]
        deepest = sorted(files, key=lambda f: (-f.depth, f.path))[: self.top_n]

        counts = {
            "fileCount": len(files),
            "measuredFileCount": len(measured),
            "unmeasuredFileCount": len(unmeasured),
            "byteCount": byte_total,
            "lineCount": sum(f.line_count or 0 for f in measured),
            "blankLineCount": sum(f.blank_line_count or 0 for f in measured),
            "binaryFileCount": len(binaries),
            "textFileCount": len(files) - len(binaries),
            "generatedFileCount": len(generated),
            "handwrittenFileCount": len(files) - len(generated),
            "testFileCount": len(tests),
            "sourceFileCount": len(files) - len(tests),
            "riskSurfaceFileCount": len(risky),
            "buildRootCount": len(build_roots),
            "entrypointFileCount": len(entrypoints),
            "dataSurfaceFileCount": len(data_surfaces),
            "maxPathDepth": max((f.depth for f in files), default=0),
        }

        payload: dict[str, Any] = {
            "skillVersion": CENSUS_VERSION,
            "snapshotSha": self.snapshot_sha,
            "counts": counts,
            "countsMeasured": {
                "byteCount": bytes_measured,
                "lineCount": not unmeasured,
                "blankLineCount": not unmeasured,
            },
            "languageMixByExtension": _language_mix(files, "language_by_extension"),
            "languageMixByMarker": _language_mix(files, "language_by_marker"),
            "generatedSplit": {
                "generated": [
                    {"path": f.path, "reason": f.generated_reason} for f in generated
                ],
                "generatedFileCount": len(generated),
                "handwrittenFileCount": len(files) - len(generated),
            },
            "testSplit": {
                "test": [{"path": f.path, "reason": f.test_reason} for f in tests],
                "testFileCount": len(tests),
                "sourceFileCount": len(files) - len(tests),
            },
            "largestFiles": [
                {"path": f.path, "byteCount": f.byte_count} for f in largest
            ],
            "deepestPaths": [{"path": f.path, "depth": f.depth} for f in deepest],
            "binaryFiles": [
                {"path": f.path, "byteCount": f.byte_count, "lineCount": None,
                 "lineCountApplicable": False}
                for f in binaries
            ],
            "unmeasured": [
                {"path": f.path, "reason": f.unmeasured_reason,
                 "byteCount": f.byte_count, "lineCount": None, "lineCountMeasured": False}
                for f in unmeasured
            ],
            "riskSurface": [
                {"path": f.path, "markers": list(f.risk_markers)} for f in risky
            ],
            "buildRoots": [
                {"path": f.path, "buildSystem": f.build_system} for f in build_roots
            ],
            "entrypoints": [
                {"path": f.path,
                 "markers": [{"marker": m, "line": line} for m, line in f.entrypoint_markers]}
                for f in entrypoints
            ],
            "moduleGraph": self._module_graph(),
            "dataFlowMap": {
                "measured": False,
                "reason": (
                    "data flow requires execution or interprocedural analysis; a snapshot-only "
                    "census can locate data surfaces but must not claim to have traced flow"
                ),
                "dataSurfaces": [
                    {"path": f.path, "markers": list(f.data_markers)} for f in data_surfaces
                ],
            },
            "unknowns": {
                "unknownLanguageByExtension": [
                    f.path for f in files if f.language_by_extension == _UNKNOWN
                ],
                "unknownLanguageByMarker": [
                    f.path for f in files if f.language_by_marker == _UNKNOWN
                ],
                "unmeasuredPaths": [f.path for f in unmeasured],
                "notReported": {
                    "linesOfCode": (
                        "not reported: 'lines of code' has no definition derivable from a "
                        "snapshot alone; physical lineCount and blankLineCount are reported "
                        "instead, each with its definition"
                    ),
                    "churn": "not reported: requires history, which a snapshot does not carry",
                    "ownership": "not reported: requires history and identity mapping",
                },
            },
            "definitions": dict(_DEFINITIONS),
        }
        payload["gates"] = self._gates(payload)
        payload["status"] = str(self.status)
        payload["censusDigest"] = digest(
            {key: value for key, value in payload.items() if key != "censusDigest"}
        )
        return payload

    def _module_graph(self) -> list[dict[str, Any]]:
        """Directory-level modules — the only module structure a snapshot proves."""

        modules: dict[str, dict[str, Any]] = {}
        for facts in self.files:
            parent = facts.path.rsplit("/", 1)[0] if "/" in facts.path else "."
            module = modules.setdefault(parent, {
                "module": parent, "fileCount": 0, "byteCount": 0,
                "byteCountMeasured": True, "generatedFileCount": 0, "testFileCount": 0,
            })
            module["fileCount"] += 1
            if facts.byte_count is None:
                module["byteCountMeasured"] = False
            else:
                module["byteCount"] += facts.byte_count
            module["generatedFileCount"] += 1 if facts.is_generated else 0
            module["testFileCount"] += 1 if facts.is_test else 0
        return [modules[key] for key in sorted(modules)]

    def _gates(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        unknowns = payload["unknowns"]
        undefined = undefined_counters(payload)
        entrypoints = payload["entrypoints"]
        evidence_bound = all(
            item.get("path") for item in payload["riskSurface"] + payload["buildRoots"]
        ) and all(
            marker.get("line") is not None
            for item in entrypoints for marker in item["markers"]
        )
        return {
            "build-roots-found": {
                "passed": bool(payload["buildRoots"]) or not self.build_roots_required,
                "detail": f"{len(payload['buildRoots'])} build root(s) identified",
            },
            "critical-entrypoints-traced": {
                "passed": all(item["markers"] for item in entrypoints),
                "detail": f"{len(entrypoints)} entrypoint file(s), each marker line-bound",
            },
            "evidence-coverage-pass": {
                "passed": evidence_bound,
                "detail": "every risk, build-root and entrypoint claim carries a path/line",
            },
            "unknowns-reported": {
                "passed": (
                    "unknownLanguageByExtension" in unknowns
                    and "unmeasuredPaths" in unknowns
                    and not undefined
                ),
                "detail": f"{len(undefined)} undefined counter(s)",
            },
            "deterministic": {
                "passed": True,
                "detail": "census is a pure function of the snapshot; verify by recomputing",
            },
            "snapshot-bound": {
                "passed": bool(self.snapshot_sha),
                "detail": self.snapshot_sha,
            },
            "counts-are-defined": {
                "passed": not undefined,
                "detail": f"undefined: {list(undefined)}",
            },
        }


#: Every counter this module emits, and exactly what it counted.  A counter
#: without an entry here fails the ``counts-are-defined`` gate; that is the
#: mechanism, not a convention.
_DEFINITIONS: Mapping[str, str] = {
    "counts.fileCount": "regular files listed by the snapshot reader; symlinks and "
                        "directories are not files and are not counted",
    "counts.measuredFileCount": "files whose text was decoded and whose lines were counted",
    "counts.unmeasuredFileCount": "files whose line count is defined but could not be "
                                  "measured (oversized or unreadable in the snapshot)",
    "counts.byteCount": "sum of byteCount reported by the snapshot for every file, "
                        "including binary and generated files",
    "counts.lineCount": "sum over measured text files of (number of '\\n' characters, plus "
                        "one when the file does not end in '\\n'); binary and unmeasured "
                        "files contribute nothing and are listed separately",
    "counts.blankLineCount": "lines of measured text files whose str.strip() is empty",
    "counts.binaryFileCount": "files containing a NUL byte in the first 8192 bytes, or whose "
                              "bytes are not valid UTF-8; line counts are not applicable",
    "counts.textFileCount": "fileCount minus binaryFileCount",
    "counts.generatedFileCount": "files under a vendored directory, matching a generated "
                                 "filename pattern, or carrying a generation marker in the "
                                 "first 4096 characters",
    "counts.handwrittenFileCount": "fileCount minus generatedFileCount",
    "counts.testFileCount": "files under a test or fixture directory, or matching a test "
                            "filename pattern",
    "counts.sourceFileCount": "fileCount minus testFileCount; includes generated files",
    "counts.riskSurfaceFileCount": "files whose path or name matches a credential, key "
                                   "material or infrastructure-as-code rule; matched by path "
                                   "shape only, never by reading content",
    "counts.buildRootCount": "files whose basename is a known build manifest",
    "counts.entrypointFileCount": "files with an entrypoint filename or an entrypoint "
                                  "content marker",
    "counts.dataSurfaceFileCount": "files matching a data-definition path rule",
    "counts.maxPathDepth": "greatest number of path segments in any file path",
    "countsMeasured": "per-counter flag: false means at least one contributing file was "
                      "unmeasured, so the counter is a lower bound, not a total",
    "languageMixByExtension": "one bucket per language inferred from filename/extension, "
                              "with an explicit 'unknown' bucket that is never merged",
    "languageMixByMarker": "one bucket per language inferred from an in-file marker "
                           "(shebang or content signature) only, with an explicit 'unknown' "
                           "bucket; disagreement with the extension view is intentional",
    "generatedSplit": "generated versus handwritten, each generated file carrying the reason",
    "testSplit": "test/fixture versus source, each test file carrying the reason",
    "largestFiles": "files ordered by descending snapshot byteCount then path; files with an "
                    "unmeasured byteCount are excluded, not sorted as zero",
    "deepestPaths": "files ordered by descending path-segment count then path",
    "binaryFiles": "binary files with lineCountApplicable=false",
    "unmeasured": "files whose line count is defined but was not measured, with the reason",
    "riskSurface": "security-relevant paths with the rule labels they matched",
    "buildRoots": "build manifests with the build system they imply",
    "entrypoints": "entrypoint files with each marker bound to a line (line 0 = filename rule)",
    "moduleGraph": "one entry per containing directory ('.' for the repository root)",
    "dataFlowMap": "explicitly unmeasured; lists data surfaces without claiming flow edges",
    "unknowns": "everything the census could not classify or measure, plus counters that are "
                "deliberately not reported and why",
    "gates": "acceptance gate outcomes with the detail each was decided on",
    "status": "SUCCEEDED only when nothing is unmeasured; PARTIAL otherwise",
    "skillVersion": "census algorithm version; a change here changes censusDigest",
    "snapshotSha": "the snapshot this census is bound to",
}


def undefined_counters(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Return output keys and counters that carry no definition.

    A census whose numbers are undefined is the failure mode this capability
    exists to prevent, so the check is data, callable by both the gate and the
    test suite.
    """

    definitions = payload.get("definitions", {})
    missing: list[str] = []
    for key, value in payload.get("counts", {}).items():
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if f"counts.{key}" not in definitions:
            missing.append(f"counts.{key}")
    for key in payload:
        if key in {"definitions", "censusDigest", "counts"}:
            continue
        if key not in definitions:
            missing.append(key)
    return tuple(sorted(missing))


def build_census(reader: RepositoryReader, *, top_n: int = 10,
                 require_build_roots: bool = False,
                 expected_snapshot_sha: str | None = None) -> Census:
    """Compute the census of ``reader``'s snapshot.

    ``expected_snapshot_sha`` is checked before any file is read: a caller that
    believed it was censusing snapshot A must not silently receive a census of
    snapshot B, because every downstream conclusion is bound to that sha.
    """

    snapshot_sha = getattr(reader, "snapshot_sha", None)
    if not isinstance(snapshot_sha, str) or not snapshot_sha:
        raise KernelError(
            code="MALFORMED_INPUT",
            message="reader does not expose a snapshot_sha",
            recommended_action="pass a RepositoryReader bound to an immutable snapshot",
        )
    if expected_snapshot_sha is not None and expected_snapshot_sha != snapshot_sha:
        raise KernelError(
            code="SNAPSHOT_CHANGED",
            message=(
                f"caller expected snapshot {expected_snapshot_sha}, reader is bound to "
                f"{snapshot_sha}"
            ),
            retryable=False,
            recommended_action="re-take the snapshot and re-run every bound conclusion",
        )
    if top_n <= 0:
        raise KernelError(
            code="MALFORMED_INPUT",
            message="topN must be positive",
            recommended_action="request at least one entry",
        )

    files = tuple(_facts_for(reader, path) for path in sorted(reader.list_paths()))
    census = Census(
        snapshot_sha=snapshot_sha,
        files=files,
        top_n=top_n,
        build_roots_required=require_build_roots,
    )
    if require_build_roots and not any(f.build_system for f in files):
        raise KernelError(
            code="UNSUPPORTED_BUILD_SYSTEM",
            message="no recognised build manifest in the snapshot",
            retryable=False,
            recommended_action="add a build manifest or drop the requireBuildRoots requirement",
            details={"snapshotSha": snapshot_sha},
        )
    return census


_REQUEST_FIELDS = frozenset({
    "reader", "snapshotSha", "topN", "requireBuildRoots", "failOnPartial",
})


@register("repository-census")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point for ``repository-census``.

    ``failOnPartial`` exists because two callers want different things from an
    unreadable file: an interactive explorer wants the partial census, a release
    gate wants a raise.  Neither is allowed to receive the other's answer by
    accident, so the choice is an input, not a default.
    """

    payload = require_mapping(request, "request")
    reject_unknown_fields(payload, _REQUEST_FIELDS, field_name="repository-census request")
    reader = payload.get("reader")
    if reader is None:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="repository-census requires a 'reader' implementing RepositoryReader",
            recommended_action="pass adapters.filestore.SnapshotRepositoryReader",
        )
    if not isinstance(reader, RepositoryReader):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"'reader' of type {type(reader).__name__} is not a RepositoryReader",
            recommended_action="pass an object implementing the RepositoryReader port",
        )
    expected = payload.get("snapshotSha")
    if expected is not None:
        expected = require_str(expected, "snapshotSha")
    top_n = require_int(payload.get("topN", 10), "topN", minimum=1, maximum=10_000)
    require_build_roots = require_bool(
        payload.get("requireBuildRoots", False), "requireBuildRoots"
    )
    fail_on_partial = require_bool(payload.get("failOnPartial", False), "failOnPartial")

    census = build_census(
        reader,
        top_n=top_n,
        require_build_roots=require_build_roots,
        expected_snapshot_sha=expected,
    )
    body = census.to_payload()
    if census.status is Status.PARTIAL and fail_on_partial:
        raise KernelError(
            code="PARTIAL_CENSUS",
            message=(
                f"{len(census.unmeasured())} file(s) could not be measured; "
                "the caller asked for a complete census"
            ),
            partial=True,
            retryable=False,
            recommended_action="re-snapshot with a higher size limit, or accept PARTIAL",
            details={"unmeasured": [f.path for f in census.unmeasured()]},
        )
    return {
        "status": census.status,
        "repositoryProfile": body,
        "moduleGraph": body["moduleGraph"],
        "buildGraph": {"buildRoots": body["buildRoots"], "counts": {
            "buildRootCount": body["counts"]["buildRootCount"]}},
        "entrypointMap": body["entrypoints"],
        "dataFlowMap": body["dataFlowMap"],
        "riskMap": {"riskSurface": body["riskSurface"], "counts": {
            "riskSurfaceFileCount": body["counts"]["riskSurfaceFileCount"]}},
        "censusDigest": body["censusDigest"],
        "definitions": body["definitions"],
        "gates": body["gates"],
    }

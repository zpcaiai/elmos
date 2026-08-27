"""Skill 02 — build graph, toolchain lock and baseline.

Derives ``file -> target -> test -> artifact`` from the build files that are
actually in the repository, using real parsers (``tomllib`` for TOML,
``xml.etree`` for Maven/MSBuild, ``json`` for npm) rather than pattern guesses,
and falls back to explicitly-marked heuristics only where a format has no
machine-readable form (Gradle Groovy DSL, CMake).

Two honesty rules are enforced:

* A file that maps to no target is reported in ``unmapped_files``.  It is never
  quietly attached to the nearest target, because a wrong edge here becomes a
  missed test later.
* The baseline is only a baseline if something ran.  With no executor the
  baseline is ``NOT_RUN``, and :meth:`BaselineReport.trustworthy` is ``False``,
  which downstream gates treat as undecided rather than green.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree

from .contracts import (
    ContractError,
    match_path_glob,
    sha256_payload,
    sha256_text,
)
from .discovery import RepositoryInventory
from .sandbox import (
    ExecutionKind,
    ExecutionLedger,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    SandboxExecutor,
)
from .workspace import WorkspaceSnapshot

#: Lockfiles whose digest pins the dependency closure.  A build system without
#: one of these cannot claim a reproducible restore.
LOCKFILES: tuple[str, ...] = (
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "poetry.lock",
    "uv.lock",
    "pdm.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "go.sum",
    "composer.lock",
    "Gemfile.lock",
    "gradle/verification-metadata.xml",
    "packages.lock.json",
    "Package.resolved",
    "pubspec.lock",
)

#: Files that pin a *toolchain* version rather than a dependency set.
TOOLCHAIN_FILES: tuple[str, ...] = (
    ".tool-versions",
    ".nvmrc",
    ".node-version",
    ".python-version",
    ".ruby-version",
    ".sdkmanrc",
    "rust-toolchain",
    "rust-toolchain.toml",
    "global.json",
    ".java-version",
    "gradle/wrapper/gradle-wrapper.properties",
    ".mvn/wrapper/maven-wrapper.properties",
)

_MAVEN_NS = {"m": "http://maven.apache.org/POM/4.0.0"}


@dataclass(frozen=True, slots=True)
class BuildTarget:
    target_id: str
    kind: str
    build_system: str
    definition_path: str
    source_roots: tuple[str, ...] = ()
    test_roots: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    language: str = "unknown"

    @property
    def is_test(self) -> bool:
        return self.kind == "test"

    def to_payload(self) -> dict[str, Any]:
        return {
            "targetId": self.target_id,
            "kind": self.kind,
            "buildSystem": self.build_system,
            "definitionPath": self.definition_path,
            "sourceRoots": list(self.source_roots),
            "testRoots": list(self.test_roots),
            "dependencies": list(self.dependencies),
            "artifacts": list(self.artifacts),
            "language": self.language,
        }


@dataclass(frozen=True, slots=True)
class ToolchainPin:
    name: str
    version: str
    source_path: str
    digest: str

    def to_payload(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "sourcePath": self.source_path, "digest": self.digest}


@dataclass(frozen=True, slots=True)
class ToolchainLock:
    pins: tuple[ToolchainPin, ...]
    lockfiles: Mapping[str, str]
    unpinned: tuple[str, ...]

    @property
    def reproducible(self) -> bool:
        """A restore is reproducible only when nothing is left unpinned."""

        return not self.unpinned

    def to_payload(self) -> dict[str, Any]:
        return {
            "pins": [pin.to_payload() for pin in self.pins],
            "lockfiles": dict(sorted(self.lockfiles.items())),
            "unpinned": list(self.unpinned),
            "reproducible": self.reproducible,
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


@dataclass(frozen=True, slots=True)
class BuildGraph:
    repository_id: str
    revision: str
    targets: tuple[BuildTarget, ...]
    file_to_targets: Mapping[str, tuple[str, ...]]
    target_to_tests: Mapping[str, tuple[str, ...]]
    unmapped_files: tuple[str, ...]
    heuristic_targets: tuple[str, ...] = ()

    def target(self, target_id: str) -> BuildTarget:
        for item in self.targets:
            if item.target_id == target_id:
                return item
        raise ContractError("unknown_target", f"build graph has no target '{target_id}'")

    def targets_for(self, path: str) -> tuple[str, ...]:
        return self.file_to_targets.get(path, ())

    def tests_for_paths(self, paths: Sequence[str]) -> tuple[str, ...]:
        selected: set[str] = set()
        for path in paths:
            for target_id in self.targets_for(path):
                selected.update(self.target_to_tests.get(target_id, ()))
        return tuple(sorted(selected))

    @property
    def coverage(self) -> float:
        total = len(self.file_to_targets) + len(self.unmapped_files)
        return 0.0 if total == 0 else len(self.file_to_targets) / total

    def to_payload(self) -> dict[str, Any]:
        return {
            "repositoryId": self.repository_id,
            "revision": self.revision,
            "targets": [item.to_payload() for item in self.targets],
            "fileToTargets": {key: list(value) for key, value in sorted(self.file_to_targets.items())},
            "targetToTests": {key: list(value) for key, value in sorted(self.target_to_tests.items())},
            "unmappedFiles": list(self.unmapped_files),
            "heuristicTargets": list(self.heuristic_targets),
            "coverage": round(self.coverage, 4),
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


@dataclass(frozen=True, slots=True)
class BaselineReport:
    """The pre-change state of the repository as measured, not as assumed."""

    status: ExecutionStatus
    build_ok: bool | None
    test_ok: bool | None
    pre_existing_failures: tuple[str, ...] = ()
    ledger: ExecutionLedger = field(default_factory=ExecutionLedger)
    reason: str = ""

    @property
    def trustworthy(self) -> bool:
        """Whether later comparisons against this baseline mean anything."""

        return self.status.produced_evidence and self.build_ok is not None

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "buildOk": self.build_ok,
            "testOk": self.test_ok,
            "preExistingFailures": list(self.pre_existing_failures),
            "trustworthy": self.trustworthy,
            "reason": self.reason,
            "executions": self.ledger.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class SandboxImageSpec:
    base: str
    toolchains: tuple[ToolchainPin, ...]
    packages: tuple[str, ...]
    network: str
    digest_inputs: Mapping[str, str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "toolchains": [pin.to_payload() for pin in self.toolchains],
            "packages": list(self.packages),
            "network": self.network,
            "digestInputs": dict(sorted(self.digest_inputs.items())),
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _directory_of(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _join(directory: str, name: str) -> str:
    return f"{directory}/{name}" if directory else name


def _parse_maven(path: str, text: str) -> tuple[BuildTarget, ...]:
    try:
        root = ElementTree.fromstring(text)  # noqa: S314 - build metadata from the analysed snapshot
    except ElementTree.ParseError as exc:
        raise ContractError("unparsable_build_file", f"cannot parse Maven POM '{path}'") from exc
    directory = _directory_of(path)

    def find(node: ElementTree.Element, tag: str) -> str | None:
        child = node.find(f"m:{tag}", _MAVEN_NS)
        if child is None:
            child = node.find(tag)
        return child.text.strip() if child is not None and child.text else None

    artifact = find(root, "artifactId") or (directory.rsplit("/", 1)[-1] if directory else "root")
    group = find(root, "groupId") or ""
    packaging = find(root, "packaging") or "jar"
    modules_node = root.find("m:modules", _MAVEN_NS) or root.find("modules")
    dependencies: list[str] = []
    deps_node = root.find("m:dependencies", _MAVEN_NS) or root.find("dependencies")
    if deps_node is not None:
        for dependency in list(deps_node):
            dep_group = find(dependency, "groupId") or ""
            dep_artifact = find(dependency, "artifactId")
            if dep_artifact:
                dependencies.append(f"{dep_group}:{dep_artifact}" if dep_group else dep_artifact)
    target_id = f"maven:{group}:{artifact}" if group else f"maven:{artifact}"
    targets = [
        BuildTarget(
            target_id=target_id,
            kind="aggregator" if packaging == "pom" and modules_node is not None else "library",
            build_system="maven",
            definition_path=path,
            source_roots=(_join(directory, "src/main"),),
            test_roots=(_join(directory, "src/test"),),
            dependencies=tuple(sorted(set(dependencies))),
            artifacts=(f"{artifact}.{packaging}",) if packaging != "pom" else (),
            language="java",
        )
    ]
    if packaging != "pom":
        targets.append(
            BuildTarget(
                target_id=f"{target_id}:test",
                kind="test",
                build_system="maven",
                definition_path=path,
                source_roots=(_join(directory, "src/test"),),
                dependencies=(target_id,),
                language="java",
            )
        )
    return tuple(targets)


def _parse_package_json(path: str, text: str) -> tuple[BuildTarget, ...]:
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractError("unparsable_build_file", f"cannot parse '{path}'") from exc
    if not isinstance(document, dict):
        raise ContractError("unparsable_build_file", f"'{path}' is not a JSON object")
    directory = _directory_of(path)
    name = document.get("name") or (directory.rsplit("/", 1)[-1] if directory else "root")
    scripts = document.get("scripts") if isinstance(document.get("scripts"), dict) else {}
    dependencies = sorted(
        {
            *(document.get("dependencies") or {}),
            *(document.get("peerDependencies") or {}),
        }
    )
    target_id = f"npm:{name}"
    targets = [
        BuildTarget(
            target_id=target_id,
            kind="library",
            build_system="node",
            definition_path=path,
            source_roots=(_join(directory, "src"), directory or "."),
            test_roots=(_join(directory, "test"), _join(directory, "tests"), _join(directory, "__tests__")),
            dependencies=tuple(dependencies),
            artifacts=(f"{name}.tgz",),
            language="typescript" if _join(directory, "tsconfig.json") else "javascript",
        )
    ]
    if isinstance(scripts, dict) and "test" in scripts:
        targets.append(
            BuildTarget(
                target_id=f"{target_id}:test",
                kind="test",
                build_system="node",
                definition_path=path,
                source_roots=(
                    _join(directory, "test"),
                    _join(directory, "tests"),
                    _join(directory, "__tests__"),
                    _join(directory, "src"),
                ),
                dependencies=(target_id,),
                language="typescript",
            )
        )
    return tuple(targets)


def _parse_pyproject(path: str, text: str) -> tuple[BuildTarget, ...]:
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ContractError("unparsable_build_file", f"cannot parse '{path}'") from exc
    directory = _directory_of(path)
    project_raw = document.get("project")
    project: dict[str, Any] = project_raw if isinstance(project_raw, dict) else {}
    tool_raw = document.get("tool")
    poetry_raw = tool_raw.get("poetry") if isinstance(tool_raw, dict) else None
    poetry: dict[str, Any] = poetry_raw if isinstance(poetry_raw, dict) else {}
    name = project.get("name") or poetry.get("name") or (directory.rsplit("/", 1)[-1] if directory else "root")
    raw_dependencies = project.get("dependencies") or []
    dependencies = tuple(
        sorted(
            {
                re.split(r"[\[<>=!~; ]", item, maxsplit=1)[0]
                for item in raw_dependencies
                if isinstance(item, str) and item.strip()
            }
        )
    )
    target_id = f"python:{name}"
    return (
        BuildTarget(
            target_id=target_id,
            kind="library",
            build_system="python",
            definition_path=path,
            source_roots=(_join(directory, "src"), directory or "."),
            test_roots=(_join(directory, "tests"), _join(directory, "test")),
            dependencies=dependencies,
            artifacts=(f"{name}.whl",),
            language="python",
        ),
        BuildTarget(
            target_id=f"{target_id}:test",
            kind="test",
            build_system="python",
            definition_path=path,
            source_roots=(_join(directory, "tests"), _join(directory, "test")),
            dependencies=(target_id,),
            language="python",
        ),
    )


def _parse_cargo(path: str, text: str) -> tuple[BuildTarget, ...]:
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ContractError("unparsable_build_file", f"cannot parse '{path}'") from exc
    directory = _directory_of(path)
    package_raw = document.get("package")
    package: dict[str, Any] = package_raw if isinstance(package_raw, dict) else {}
    name = package.get("name") or (directory.rsplit("/", 1)[-1] if directory else "root")
    dependencies_raw = document.get("dependencies")
    dependencies = tuple(sorted(dependencies_raw)) if isinstance(dependencies_raw, dict) else ()
    target_id = f"cargo:{name}"
    return (
        BuildTarget(
            target_id=target_id,
            kind="workspace" if "workspace" in document and "package" not in document else "library",
            build_system="cargo",
            definition_path=path,
            source_roots=(_join(directory, "src"),),
            test_roots=(_join(directory, "tests"),),
            dependencies=dependencies,
            artifacts=(f"lib{name}.rlib",),
            language="rust",
        ),
    )


def _parse_go_mod(path: str, text: str) -> tuple[BuildTarget, ...]:
    directory = _directory_of(path)
    module = ""
    dependencies: list[str] = []
    in_require_block = False
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        if line.startswith("module "):
            module = line[len("module ") :].strip()
        elif line.startswith("require ("):
            in_require_block = True
        elif in_require_block and line == ")":
            in_require_block = False
        elif in_require_block and line:
            dependencies.append(line.split()[0])
        elif line.startswith("require "):
            parts = line[len("require ") :].split()
            if parts:
                dependencies.append(parts[0])
    name = module or (directory.rsplit("/", 1)[-1] if directory else "root")
    return (
        BuildTarget(
            target_id=f"go:{name}",
            kind="library",
            build_system="go-modules",
            definition_path=path,
            source_roots=(directory or ".",),
            test_roots=(directory or ".",),
            dependencies=tuple(sorted(set(dependencies))),
            language="go",
        ),
    )


def _parse_msbuild(path: str, text: str) -> tuple[BuildTarget, ...]:
    try:
        root = ElementTree.fromstring(text)  # noqa: S314 - build metadata from the analysed snapshot
    except ElementTree.ParseError as exc:
        raise ContractError("unparsable_build_file", f"cannot parse '{path}'") from exc
    directory = _directory_of(path)
    name = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    dependencies: list[str] = []
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "PackageReference":
            include = node.attrib.get("Include")
            if include:
                dependencies.append(include)
        elif tag == "ProjectReference":
            include = node.attrib.get("Include")
            if include:
                dependencies.append(include.replace("\\", "/"))
    is_test = name.lower().endswith(("tests", "test")) or any(
        "test" in dependency.lower() for dependency in dependencies[:20]
    )
    return (
        BuildTarget(
            target_id=f"msbuild:{name}",
            kind="test" if is_test else "library",
            build_system="msbuild",
            definition_path=path,
            source_roots=(directory or ".",),
            dependencies=tuple(sorted(set(dependencies))),
            artifacts=(f"{name}.dll",),
            language="csharp",
        ),
    )


_GRADLE_PROJECT = re.compile(r"""^\s*include\s*\(?\s*['"]([^'"]+)['"]""", re.MULTILINE)
_CMAKE_SUBDIR = re.compile(r"""add_subdirectory\s*\(\s*([^\s)]+)""", re.IGNORECASE)
_CMAKE_TARGET = re.compile(r"""add_(library|executable)\s*\(\s*([A-Za-z0-9_\-]+)""", re.IGNORECASE)


def _parse_gradle_settings(path: str, text: str) -> tuple[BuildTarget, ...]:
    """Gradle's DSL is a program, not data — these targets are heuristic."""

    directory = _directory_of(path)
    targets: list[BuildTarget] = []
    for match in _GRADLE_PROJECT.finditer(text):
        module = match.group(1).lstrip(":").replace(":", "/")
        module_dir = _join(directory, module)
        targets.append(
            BuildTarget(
                target_id=f"gradle:{module.replace('/', ':')}",
                kind="library",
                build_system="gradle",
                definition_path=path,
                source_roots=(_join(module_dir, "src/main"),),
                test_roots=(_join(module_dir, "src/test"),),
                language="java",
            )
        )
        targets.append(
            BuildTarget(
                target_id=f"gradle:{module.replace('/', ':')}:test",
                kind="test",
                build_system="gradle",
                definition_path=path,
                source_roots=(_join(module_dir, "src/test"),),
                dependencies=(f"gradle:{module.replace('/', ':')}",),
                language="java",
            )
        )
    if not targets:
        targets.append(
            BuildTarget(
                target_id="gradle:root",
                kind="library",
                build_system="gradle",
                definition_path=path,
                source_roots=(_join(directory, "src/main"),),
                test_roots=(_join(directory, "src/test"),),
                language="java",
            )
        )
    return tuple(targets)


def _parse_cmake(path: str, text: str) -> tuple[BuildTarget, ...]:
    directory = _directory_of(path)
    targets: list[BuildTarget] = []
    for kind, name in _CMAKE_TARGET.findall(text):
        targets.append(
            BuildTarget(
                target_id=f"cmake:{name}",
                kind="binary" if kind.lower() == "executable" else "library",
                build_system="cmake",
                definition_path=path,
                source_roots=(directory or ".",),
                language="cpp",
            )
        )
    for subdirectory in _CMAKE_SUBDIR.findall(text):
        cleaned = subdirectory.strip("\"'")
        if cleaned and not cleaned.startswith("$"):
            targets.append(
                BuildTarget(
                    target_id=f"cmake:dir:{_join(directory, cleaned)}",
                    kind="aggregator",
                    build_system="cmake",
                    definition_path=path,
                    source_roots=(_join(directory, cleaned),),
                    language="cpp",
                )
            )
    return tuple(targets)


_PARSERS: tuple[tuple[str, Any, bool], ...] = (
    ("**/pom.xml", _parse_maven, False),
    ("**/package.json", _parse_package_json, False),
    ("**/pyproject.toml", _parse_pyproject, False),
    ("**/Cargo.toml", _parse_cargo, False),
    ("**/go.mod", _parse_go_mod, False),
    ("**/*.csproj", _parse_msbuild, False),
    ("**/*.fsproj", _parse_msbuild, False),
    ("**/*.vbproj", _parse_msbuild, False),
    ("**/settings.gradle", _parse_gradle_settings, True),
    ("**/settings.gradle.kts", _parse_gradle_settings, True),
    ("**/CMakeLists.txt", _parse_cmake, True),
)


def build_graph(snapshot: WorkspaceSnapshot, inventory: RepositoryInventory) -> BuildGraph:
    """Derive the build graph from the build files actually present."""

    targets: list[BuildTarget] = []
    heuristic: list[str] = []
    seen_ids: set[str] = set()

    for record in snapshot:
        for pattern, parser, is_heuristic in _PARSERS:
            if not match_path_glob(record.path, pattern):
                continue
            if record.text is None:
                continue
            for target in parser(record.path, record.text):
                if target.target_id in seen_ids:
                    continue
                seen_ids.add(target.target_id)
                targets.append(target)
                if is_heuristic:
                    heuristic.append(target.target_id)
            break

    # Longest source root wins, so a nested module claims its own files rather
    # than being swallowed by the repository-root target.
    roots: list[tuple[str, str, bool]] = []
    for target in targets:
        for root in target.source_roots:
            roots.append((root.rstrip("/"), target.target_id, target.is_test))
        for root in target.test_roots:
            roots.append((root.rstrip("/"), target.target_id, True))
    roots.sort(key=lambda item: len(item[0]), reverse=True)

    file_to_targets: dict[str, tuple[str, ...]] = {}
    unmapped: list[str] = []
    generated = set(inventory.generated_paths)
    vendored = set(inventory.vendored_paths)
    for record in snapshot:
        if record.path in vendored:
            continue
        best_length = -1
        matched: list[str] = []
        for root, target_id, _ in roots:
            if root in ("", ".") or record.path == root or record.path.startswith(root + "/"):
                length = len(root)
                if length > best_length:
                    best_length, matched = length, [target_id]
                elif length == best_length and target_id not in matched:
                    matched.append(target_id)
        if matched:
            file_to_targets[record.path] = tuple(sorted(matched))
        elif record.path not in generated:
            unmapped.append(record.path)

    target_to_tests: dict[str, tuple[str, ...]] = {}
    for target in targets:
        if target.is_test:
            continue
        linked = sorted(
            item.target_id
            for item in targets
            if item.is_test and (target.target_id in item.dependencies or item.target_id == f"{target.target_id}:test")
        )
        if linked:
            target_to_tests[target.target_id] = tuple(linked)

    return BuildGraph(
        repository_id=snapshot.repository_id,
        revision=snapshot.revision,
        targets=tuple(sorted(targets, key=lambda item: item.target_id)),
        file_to_targets=file_to_targets,
        target_to_tests=target_to_tests,
        unmapped_files=tuple(sorted(unmapped)),
        heuristic_targets=tuple(sorted(heuristic)),
    )


_VERSION_LINE = re.compile(r"^\s*([A-Za-z0-9_.+-]+)\s*[= ]\s*([A-Za-z0-9_.+-]+)\s*$")


def toolchain_lock(snapshot: WorkspaceSnapshot, graph: BuildGraph) -> ToolchainLock:
    """Pin toolchains and lockfiles; report what is left floating."""

    pins: list[ToolchainPin] = []
    lockfiles: dict[str, str] = {}

    for name in LOCKFILES:
        for path in snapshot.match([name, f"**/{name}"]):
            record = snapshot.require(path)
            lockfiles[path] = record.content_digest

    for name in TOOLCHAIN_FILES:
        for path in snapshot.match([name, f"**/{name}"]):
            record = snapshot.require(path)
            if record.text is None:
                continue
            digest = record.content_digest
            basename = path.rsplit("/", 1)[-1]
            content = record.text.strip()
            if basename in (".nvmrc", ".node-version"):
                pins.append(ToolchainPin("node", content.splitlines()[0].strip(), path, digest))
            elif basename == ".python-version":
                pins.append(ToolchainPin("python", content.splitlines()[0].strip(), path, digest))
            elif basename == ".ruby-version":
                pins.append(ToolchainPin("ruby", content.splitlines()[0].strip(), path, digest))
            elif basename == ".java-version":
                pins.append(ToolchainPin("java", content.splitlines()[0].strip(), path, digest))
            elif basename in (".tool-versions", ".sdkmanrc"):
                for line in content.splitlines():
                    match = _VERSION_LINE.match(line.split("#", 1)[0])
                    if match:
                        pins.append(ToolchainPin(match.group(1), match.group(2), path, digest))
            elif basename == "global.json":
                try:
                    document = json.loads(record.text)
                    version = document.get("sdk", {}).get("version")
                    if isinstance(version, str):
                        pins.append(ToolchainPin("dotnet", version, path, digest))
                except (json.JSONDecodeError, AttributeError):
                    pass
            elif basename.startswith("rust-toolchain"):
                if basename.endswith(".toml"):
                    try:
                        document = tomllib.loads(record.text)
                        channel = document.get("toolchain", {}).get("channel")
                        if isinstance(channel, str):
                            pins.append(ToolchainPin("rust", channel, path, digest))
                    except tomllib.TOMLDecodeError:
                        pass
                else:
                    pins.append(ToolchainPin("rust", content.splitlines()[0].strip(), path, digest))
            elif basename.endswith("wrapper.properties"):
                for line in content.splitlines():
                    if "distributionUrl" in line:
                        pins.append(ToolchainPin(
                            "gradle" if "gradle" in path else "maven",
                            line.rsplit("/", 1)[-1].strip(),
                            path,
                            digest,
                        ))

    #: A build system that produced targets but contributed no lockfile cannot
    #: promise a reproducible restore, and says so by name.
    systems_with_targets = {target.build_system for target in graph.targets}
    lock_systems = {
        "node": ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb"),
        "python": ("poetry.lock", "uv.lock", "pdm.lock", "Pipfile.lock"),
        "cargo": ("Cargo.lock",),
        "go-modules": ("go.sum",),
        "msbuild": ("packages.lock.json",),
        "maven": ("gradle/verification-metadata.xml",),
    }
    unpinned = [
        system
        for system in sorted(systems_with_targets)
        if system in lock_systems
        and not any(path.rsplit("/", 1)[-1] in lock_systems[system] for path in lockfiles)
    ]

    return ToolchainLock(
        pins=tuple(sorted(pins, key=lambda pin: (pin.name, pin.source_path))),
        lockfiles=lockfiles,
        unpinned=tuple(unpinned),
    )


def baseline_requests(graph: BuildGraph, *, profile: str = "default") -> tuple[ExecutionRequest, ...]:
    """The commands that would establish a baseline for this build graph."""

    commands: dict[str, tuple[str, ...]] = {
        "maven": ("mvn", "-B", "-q", "test"),
        "gradle": ("gradle", "--no-daemon", "test"),
        "node": ("npm", "test", "--silent"),
        "python": ("pytest", "-q"),
        "cargo": ("cargo", "test", "--quiet"),
        "go-modules": ("go", "test", "./..."),
        "msbuild": ("dotnet", "test", "--nologo"),
        "cmake": ("ctest", "--output-on-failure"),
    }
    systems = sorted({target.build_system for target in graph.targets})
    requests: list[ExecutionRequest] = []
    for system in systems:
        argv = commands.get(system)
        if argv is None:
            continue
        requests.append(
            ExecutionRequest(
                request_id=f"baseline:{system}",
                kind=ExecutionKind.TEST,
                argv=argv,
                timeout_seconds=3600,
                description=f"baseline {system} test run ({profile})",
            )
        )
    return tuple(requests)


_FAILURE_LINE = re.compile(
    r"(?:^|\n)\s*(?:FAILED|FAIL|ERROR|\[ERROR\]|error\[)\s*[:\]]?\s*(?P<detail>[^\n]{1,200})",
)


def parse_failures(result: ExecutionResult) -> tuple[str, ...]:
    """Extract failure identities from tool output, normalised and bounded."""

    found: list[str] = []
    for stream in (result.stdout, result.stderr):
        for match in _FAILURE_LINE.finditer(stream):
            detail = match.group("detail").strip()
            if detail and detail not in found:
                found.append(detail)
            if len(found) >= 500:
                return tuple(found)
    return tuple(found)


def establish_baseline(
    graph: BuildGraph,
    executor: SandboxExecutor,
    *,
    profile: str = "default",
) -> BaselineReport:
    """Run the baseline, or report honestly that it was not run."""

    requests = baseline_requests(graph, profile=profile)
    if not requests:
        return BaselineReport(
            status=ExecutionStatus.NOT_RUN,
            build_ok=None,
            test_ok=None,
            reason="no-known-build-command-for-detected-build-systems",
        )
    ledger = ExecutionLedger()
    decisive: list[ExecutionResult] = []
    for request in requests:
        result = executor.execute(request)
        ledger = ledger.record(request, result)
        if result.decisive:
            decisive.append(result)
    if not decisive:
        return BaselineReport(
            status=ExecutionStatus.NOT_RUN,
            build_ok=None,
            test_ok=None,
            ledger=ledger,
            reason="executor-produced-no-decisive-result",
        )
    failures: list[str] = []
    for result in decisive:
        failures.extend(parse_failures(result))
    all_passed = all(result.succeeded for result in decisive)
    return BaselineReport(
        status=ExecutionStatus.COMPLETED if all_passed else ExecutionStatus.FAILED,
        build_ok=all_passed,
        test_ok=all_passed,
        pre_existing_failures=tuple(dict.fromkeys(failures)),
        ledger=ledger,
        reason="" if all_passed else "baseline-has-pre-existing-failures",
    )


def sandbox_image_spec(
    inventory: RepositoryInventory,
    lock: ToolchainLock,
    *,
    network: str = "deny",
) -> SandboxImageSpec:
    languages = [item.language for item in inventory.languages[:6]]
    base = "elmos/refactor-sandbox:multi"
    if languages[:1] == ["java"]:
        base = "elmos/refactor-sandbox:jvm"
    elif languages[:1] in (["python"], ["typescript"], ["javascript"], ["go"], ["rust"], ["csharp"]):
        base = f"elmos/refactor-sandbox:{languages[0]}"
    return SandboxImageSpec(
        base=base,
        toolchains=lock.pins,
        packages=tuple(sorted({*inventory.build_systems})),
        network=network,
        digest_inputs={
            "inventory": inventory.digest,
            "toolchainLock": lock.digest,
            "languages": sha256_text(",".join(languages)),
        },
    )


__all__ = [
    "LOCKFILES",
    "TOOLCHAIN_FILES",
    "BaselineReport",
    "BuildGraph",
    "BuildTarget",
    "SandboxImageSpec",
    "ToolchainLock",
    "ToolchainPin",
    "baseline_requests",
    "build_graph",
    "establish_baseline",
    "parse_failures",
    "sandbox_image_spec",
    "toolchain_lock",
]

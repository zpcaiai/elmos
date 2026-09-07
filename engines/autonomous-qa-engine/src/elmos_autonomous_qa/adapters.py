"""Typed, fail-closed test-toolchain adapter contracts.

The module deliberately describes commands as argv vectors.  It does not
provide a shell escape hatch and it never guesses a replacement toolchain when
an adapter or capability is unavailable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence


class Capability(str, Enum):
    BUILD = "build"
    UNIT = "unit"
    INTEGRATION = "integration"
    CONTRACT = "contract"
    DISCOVERY = "discovery"
    UI_E2E = "ui-e2e"


class SdkOperation(str, Enum):
    DETECT = "detect"
    GENERATE = "generate"
    VALIDATE = "validate"
    EXECUTE = "execute"
    COLLECT_COVERAGE = "collect_coverage"
    DIAGNOSE = "diagnose"
    APPLY_PATCH = "apply_patch"


class OperationMode(str, Enum):
    LOCAL = "LOCAL"
    EXTERNAL_ADAPTER_REQUIRED = "EXTERNAL_ADAPTER_REQUIRED"


class AdapterContractError(ValueError):
    """Raised when caller input cannot be represented safely or exactly."""


class UnsupportedAdapterError(AdapterContractError):
    """Raised when no exact adapter exists for a requested identifier."""


class UnsupportedCapabilityError(AdapterContractError):
    """Raised when an exact adapter does not implement a requested capability."""

    def __init__(self, adapter_key: str, capability: Capability) -> None:
        self.adapter_key = adapter_key
        self.capability = capability
        super().__init__(
            f"adapter {adapter_key!r} explicitly does not support "
            f"capability {capability.value!r}"
        )


_SHELL_EXECUTABLES = frozenset(
    {
        "sh",
        "bash",
        "zsh",
        "fish",
        "cmd",
        "cmd.exe",
        "powershell",
        "pwsh",
    }
)
_FORBIDDEN_TOKEN_PARTS = ("\x00", "\n", "\r", ";", "&&", "||", "|", "`", "$(", ">", "<")
_PARAMETER_PATTERN = re.compile(r"\{([a-z][a-z0-9_]*)\}")
_RESOURCE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_MAX_COLLECTION_ITEMS = 10_000
_MAX_PATH_LENGTH = 1_024
_PARAMETER_GRAMMARS: Mapping[str, re.Pattern[str]] = MappingProxyType(
    {
        "scheme": re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"),
        "ui_target": re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,255}"),
    }
)


def _validate_argv_token(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise AdapterContractError(f"{label} must be a non-empty string")
    if any(fragment in value for fragment in _FORBIDDEN_TOKEN_PARTS):
        raise AdapterContractError(f"{label} contains a forbidden shell/control token")
    return value


def _normalize_relative_path(raw: str) -> str:
    _validate_argv_token(raw, label="path")
    if len(raw) > _MAX_PATH_LENGTH:
        raise AdapterContractError("path exceeds the bounded adapter contract")
    if "\\" in raw:
        raise AdapterContractError("paths must use canonical POSIX separators")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts:
        raise AdapterContractError("paths must be repository-relative and may not traverse")
    normalized = path.as_posix()
    if normalized in {"", "."} or normalized != raw:
        raise AdapterContractError("path must identify a repository entry")
    return normalized


def _normalize_resource_id(raw: Any, *, label: str) -> str:
    if not isinstance(raw, str) or _RESOURCE_ID_PATTERN.fullmatch(raw) is None:
        raise AdapterContractError(f"{label} must be an exact resource identifier")
    return raw


def _normalize_text(raw: Any, *, label: str, maximum: int = 4096) -> str:
    if not isinstance(raw, str) or "\x00" in raw:
        raise AdapterContractError(f"{label} must be text without NUL bytes")
    if len(raw) > maximum * 4:
        raise AdapterContractError(f"{label} exceeds the bounded adapter contract")
    normalized = " ".join(raw.split())
    if not normalized or len(normalized) > maximum:
        raise AdapterContractError(
            f"{label} must contain between 1 and {maximum} normalized characters"
        )
    return normalized


def _normalize_sha256(raw: Any, *, label: str) -> str:
    if not isinstance(raw, str) or _SHA256_PATTERN.fullmatch(raw) is None:
        raise AdapterContractError(f"{label} must be a lowercase sha256 digest")
    return raw


def _require_exact_object(
    value: Any,
    *,
    label: str,
    allowed: frozenset[str],
    required: frozenset[str] = frozenset(),
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        raise AdapterContractError(f"{label} must be an exact string-keyed object")
    unexpected = sorted(set(value).difference(allowed))
    missing = sorted(required.difference(value))
    if unexpected:
        raise AdapterContractError(f"{label} has unsupported fields: {unexpected}")
    if missing:
        raise AdapterContractError(f"{label} is missing required fields: {missing}")
    return value


def _normalize_relative_paths(
    value: Any, *, label: str, allow_empty: bool = False
) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or len(value) > _MAX_COLLECTION_ITEMS
        or any(not isinstance(item, str) for item in value)
    ):
        raise AdapterContractError(f"{label} must be a string array")
    normalized = tuple(sorted({_normalize_relative_path(item) for item in value}))
    if not allow_empty and not normalized:
        raise AdapterContractError(f"{label} may not be empty")
    return normalized


def _normalize_resource_ids(value: Any, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > _MAX_COLLECTION_ITEMS:
        raise AdapterContractError(f"{label} must be a resource identifier array")
    normalized = tuple(
        sorted({_normalize_resource_id(item, label=f"{label} item") for item in value})
    )
    if not normalized:
        raise AdapterContractError(f"{label} may not be empty")
    return normalized


@dataclass(frozen=True)
class Command:
    """A subprocess contract which is structurally incapable of using a shell."""

    argv: tuple[str, ...]
    cwd: str = "."

    def __post_init__(self) -> None:
        if not self.argv:
            raise AdapterContractError("command argv may not be empty")
        for index, token in enumerate(self.argv):
            _validate_argv_token(token, label=f"argv[{index}]")
        executable = PurePosixPath(self.argv[0]).name.lower()
        if executable in _SHELL_EXECUTABLES:
            raise AdapterContractError("shell interpreters are not valid adapter commands")
        if self.cwd != ".":
            _normalize_relative_path(self.cwd)

    @property
    def shell(self) -> bool:
        return False

    def subprocess_options(self) -> dict[str, object]:
        """Return explicit options suitable for ``subprocess.run``."""

        return {"args": list(self.argv), "cwd": self.cwd, "shell": False}


@dataclass(frozen=True)
class CommandTemplate:
    steps: tuple[tuple[str, ...], ...]

    def render(self, parameters: Mapping[str, str] | None = None) -> tuple[Command, ...]:
        supplied = dict(parameters or {})
        required = {
            match.group(1)
            for step in self.steps
            for token in step
            for match in _PARAMETER_PATTERN.finditer(token)
        }
        missing = sorted(required.difference(supplied))
        extra = sorted(set(supplied).difference(required))
        if missing:
            raise AdapterContractError(f"missing command parameters: {missing}")
        if extra:
            raise AdapterContractError(f"unexpected command parameters: {extra}")
        safe_parameters = {
            key: _validate_argv_token(value, label=f"parameter {key!r}")
            for key, value in supplied.items()
        }
        for key, value in safe_parameters.items():
            grammar = _PARAMETER_GRAMMARS.get(key)
            if grammar is None or grammar.fullmatch(value) is None:
                raise AdapterContractError(
                    f"parameter {key!r} does not match its exact grammar"
                )
        rendered: list[Command] = []
        for step in self.steps:
            argv = tuple(
                _PARAMETER_PATTERN.sub(
                    lambda match: safe_parameters[match.group(1)],
                    token,
                )
                for token in step
            )
            rendered.append(Command(argv=argv))
        return tuple(rendered)


@dataclass(frozen=True)
class CapabilityPlan:
    adapter_key: str
    capability: Capability
    commands: tuple[Command, ...]
    unsupported_reason: str | None = None

    @property
    def supported(self) -> bool:
        return bool(self.commands) and self.unsupported_reason is None

    def require_commands(self) -> tuple[Command, ...]:
        if not self.supported:
            raise AdapterContractError(
                self.unsupported_reason
                or f"{self.adapter_key} does not support {self.capability.value}"
            )
        return self.commands


@dataclass(frozen=True)
class OperationSupport:
    operation: SdkOperation
    supported: bool
    mode: OperationMode
    reason: str


@dataclass(frozen=True)
class GeneratedTestCase:
    test_case_id: str
    adapter_key: str
    test_kind: str
    target_path: str
    requirement_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "test_case_id": self.test_case_id,
            "adapter_key": self.adapter_key,
            "test_kind": self.test_kind,
            "target_path": self.target_path,
            "requirement_ids": list(self.requirement_ids),
        }


@dataclass(frozen=True)
class GeneratedTestDescriptor:
    adapter_key: str
    suite_id: str
    test_kind: str
    target_paths: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    native_layout: str
    cases: tuple[GeneratedTestCase, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "elmos.autonomous-qa.adapter-test-descriptor.v1",
            "adapter_key": self.adapter_key,
            "suite_id": self.suite_id,
            "test_kind": self.test_kind,
            "target_paths": list(self.target_paths),
            "requirement_ids": list(self.requirement_ids),
            "native_layout": self.native_layout,
            "cases": [case.as_dict() for case in self.cases],
        }


@dataclass(frozen=True)
class NormalizedDiagnostic:
    code: str
    severity: str
    message: str
    path: str | None = None
    line: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "line": self.line,
        }


@dataclass(frozen=True)
class ProjectFingerprint:
    paths: tuple[str, ...]
    dependencies: frozenset[str]
    declared_languages: frozenset[str]

    @classmethod
    def create(
        cls,
        paths: Iterable[str],
        *,
        dependencies: Iterable[str] = (),
        declared_languages: Iterable[str] = (),
    ) -> "ProjectFingerprint":
        normalized_paths = tuple(sorted({_normalize_relative_path(path) for path in paths}))
        normalized_dependencies = frozenset(
            dependency.strip().lower()
            for dependency in dependencies
            if dependency and dependency.strip()
        )
        normalized_languages = frozenset(
            language.strip().lower()
            for language in declared_languages
            if language and language.strip()
        )
        return cls(normalized_paths, normalized_dependencies, normalized_languages)

    def has_marker(self, marker: str) -> bool:
        if marker.startswith("*."):
            suffix = marker[1:]
            return any(
                part.endswith(suffix)
                for path in self.paths
                for part in PurePosixPath(path).parts
            )
        return any(PurePosixPath(path).name == marker for path in self.paths)

    def has_source(self, suffixes: Sequence[str]) -> bool:
        return any(path.lower().endswith(tuple(suffixes)) for path in self.paths)


@dataclass(frozen=True)
class DetectionRule:
    marker_alternatives: tuple[tuple[str, ...], ...]
    source_suffixes: tuple[str, ...] = ()
    language_any: tuple[str, ...] = ()
    dependency_all: tuple[str, ...] = ()

    def matches(self, fingerprint: ProjectFingerprint) -> bool:
        if self.marker_alternatives and not any(
            all(fingerprint.has_marker(marker) for marker in alternative)
            for alternative in self.marker_alternatives
        ):
            return False
        if self.source_suffixes:
            language_match = bool(
                fingerprint.declared_languages.intersection(self.language_any)
            )
            if not language_match and not fingerprint.has_source(self.source_suffixes):
                return False
        if not set(self.dependency_all).issubset(fingerprint.dependencies):
            return False
        return True


@dataclass(frozen=True)
class AdapterSpec:
    key: str
    languages: tuple[str, ...]
    frameworks: tuple[str, ...]
    detection: DetectionRule
    native_test_layouts: tuple[str, ...]
    capabilities: Mapping[Capability, CommandTemplate]
    sdk_operations: Mapping[SdkOperation, OperationSupport]

    def plan(
        self,
        capability: Capability,
        *,
        parameters: Mapping[str, str] | None = None,
    ) -> CapabilityPlan:
        template = self.capabilities.get(capability)
        if template is None:
            return CapabilityPlan(
                adapter_key=self.key,
                capability=capability,
                commands=(),
                unsupported_reason=(
                    f"adapter {self.key!r} explicitly does not support "
                    f"capability {capability.value!r}"
                ),
            )
        return CapabilityPlan(
            adapter_key=self.key,
            capability=capability,
            commands=template.render(parameters),
        )


def _template(*steps: tuple[str, ...]) -> CommandTemplate:
    return CommandTemplate(tuple(tuple(step) for step in steps))


_LOCAL_SDK_OPERATIONS = frozenset(
    {
        SdkOperation.DETECT,
        SdkOperation.GENERATE,
        SdkOperation.VALIDATE,
        SdkOperation.DIAGNOSE,
    }
)


def _sdk_operation_support() -> Mapping[SdkOperation, OperationSupport]:
    support: dict[SdkOperation, OperationSupport] = {}
    for operation in SdkOperation:
        local = operation in _LOCAL_SDK_OPERATIONS
        support[operation] = OperationSupport(
            operation=operation,
            supported=True,
            mode=(
                OperationMode.LOCAL
                if local
                else OperationMode.EXTERNAL_ADAPTER_REQUIRED
            ),
            reason=(
                "bounded in-memory repository implementation"
                if local
                else "real execution, evidence collection, or mutation requires an "
                "authorized external adapter"
            ),
        )
    return MappingProxyType(support)


def _spec(
    key: str,
    *,
    languages: tuple[str, ...],
    frameworks: tuple[str, ...],
    detection: DetectionRule,
    layouts: tuple[str, ...],
    capabilities: Mapping[Capability, CommandTemplate],
) -> AdapterSpec:
    return AdapterSpec(
        key=key,
        languages=languages,
        frameworks=frameworks,
        detection=detection,
        native_test_layouts=layouts,
        capabilities=MappingProxyType(dict(capabilities)),
        sdk_operations=_sdk_operation_support(),
    )


_ADAPTERS = (
    _spec(
        "java-maven",
        languages=("java",),
        frameworks=("maven",),
        detection=DetectionRule((("pom.xml",),), (".java",), ("java",)),
        layouts=("src/test/java", "src/integrationTest/java"),
        capabilities={
            Capability.BUILD: _template(("mvn", "-B", "-DskipTests", "package")),
            Capability.UNIT: _template(("mvn", "-B", "test")),
            Capability.INTEGRATION: _template(("mvn", "-B", "verify")),
        },
    ),
    _spec(
        "java-gradle",
        languages=("java",),
        frameworks=("gradle",),
        detection=DetectionRule(
            (("build.gradle",), ("build.gradle.kts",)), (".java",), ("java",)
        ),
        layouts=("src/test/java", "src/integrationTest/java"),
        capabilities={
            Capability.BUILD: _template(("gradle", "assemble")),
            Capability.UNIT: _template(("gradle", "test")),
            Capability.INTEGRATION: _template(("gradle", "check")),
        },
    ),
    _spec(
        "kotlin-maven",
        languages=("kotlin",),
        frameworks=("maven",),
        detection=DetectionRule((("pom.xml",),), (".kt",), ("kotlin",)),
        layouts=("src/test/kotlin", "src/integrationTest/kotlin"),
        capabilities={
            Capability.BUILD: _template(("mvn", "-B", "-DskipTests", "package")),
            Capability.UNIT: _template(("mvn", "-B", "test")),
            Capability.INTEGRATION: _template(("mvn", "-B", "verify")),
        },
    ),
    _spec(
        "kotlin-gradle",
        languages=("kotlin",),
        frameworks=("gradle",),
        detection=DetectionRule(
            (("build.gradle",), ("build.gradle.kts",)), (".kt",), ("kotlin",)
        ),
        layouts=("src/test/kotlin", "src/integrationTest/kotlin"),
        capabilities={
            Capability.BUILD: _template(("gradle", "assemble")),
            Capability.UNIT: _template(("gradle", "test")),
            Capability.INTEGRATION: _template(("gradle", "check")),
        },
    ),
    _spec(
        "python",
        languages=("python",),
        frameworks=("pytest", "unittest"),
        detection=DetectionRule(
            (("pyproject.toml",), ("setup.cfg",), ("setup.py",), ("requirements.txt",)),
            (".py",),
            ("python",),
        ),
        layouts=("tests", "test", "src/*/tests"),
        capabilities={
            Capability.BUILD: _template(("python", "-m", "build")),
            Capability.UNIT: _template(("python", "-m", "pytest", "-q")),
            Capability.INTEGRATION: _template(
                ("python", "-m", "pytest", "-q", "-m", "integration")
            ),
            Capability.DISCOVERY: _template(
                ("python", "-m", "pytest", "--collect-only", "-q")
            ),
        },
    ),
    _spec(
        "dotnet",
        languages=("csharp", "fsharp", "visual-basic-dotnet"),
        frameworks=("dotnet", "xunit", "nunit", "mstest"),
        detection=DetectionRule((("*.sln",), ("*.csproj",), ("*.fsproj",), ("*.vbproj",))),
        layouts=("tests", "test", "*.Tests"),
        capabilities={
            Capability.BUILD: _template(("dotnet", "build", "--nologo")),
            Capability.UNIT: _template(("dotnet", "test", "--nologo")),
            Capability.DISCOVERY: _template(
                ("dotnet", "test", "--nologo", "--list-tests")
            ),
        },
    ),
    _spec(
        "go",
        languages=("go",),
        frameworks=("go-test",),
        detection=DetectionRule((("go.mod",),), (".go",), ("go",)),
        layouts=("*_test.go", "testdata"),
        capabilities={
            Capability.BUILD: _template(("go", "test", "-run=^$", "./...")),
            Capability.UNIT: _template(("go", "test", "./...")),
            Capability.DISCOVERY: _template(("go", "test", "-list", ".", "./...")),
        },
    ),
    _spec(
        "rust",
        languages=("rust",),
        frameworks=("cargo",),
        detection=DetectionRule((("Cargo.toml",),), (".rs",), ("rust",)),
        layouts=("tests", "benches", "src/**/tests"),
        capabilities={
            Capability.BUILD: _template(("cargo", "test", "--no-run")),
            Capability.UNIT: _template(("cargo", "test")),
            Capability.DISCOVERY: _template(("cargo", "test", "--", "--list")),
        },
    ),
    _spec(
        "cmake-c-cpp",
        languages=("c", "cpp"),
        frameworks=("cmake", "ctest"),
        detection=DetectionRule(
            (("CMakeLists.txt",),), (".c", ".cc", ".cpp", ".cxx"), ("c", "cpp")
        ),
        layouts=("test", "tests", "*_test.c", "*_test.cpp"),
        capabilities={
            Capability.BUILD: _template(
                ("cmake", "-S", ".", "-B", "build"),
                ("cmake", "--build", "build"),
            ),
            Capability.UNIT: _template(
                ("ctest", "--test-dir", "build", "--output-on-failure")
            ),
            Capability.DISCOVERY: _template(("ctest", "--test-dir", "build", "-N")),
        },
    ),
    _spec(
        "php-composer",
        languages=("php",),
        frameworks=("composer", "phpunit"),
        detection=DetectionRule((("composer.json",),), (".php",), ("php",)),
        layouts=("tests", "test"),
        capabilities={
            Capability.BUILD: _template(("composer", "validate", "--strict")),
            Capability.UNIT: _template(("vendor/bin/phpunit",)),
            Capability.DISCOVERY: _template(("vendor/bin/phpunit", "--list-tests")),
        },
    ),
    _spec(
        "javascript-node",
        languages=("javascript",),
        frameworks=("node",),
        detection=DetectionRule(
            (("package.json",),), (".js", ".jsx", ".mjs", ".cjs"), ("javascript",)
        ),
        layouts=("test", "tests", "__tests__", "*.test.js", "*.spec.js"),
        capabilities={
            Capability.BUILD: _template(("npm", "run", "build")),
            Capability.UNIT: _template(("npm", "test", "--", "--run")),
            Capability.INTEGRATION: _template(("npm", "run", "test:integration")),
        },
    ),
    _spec(
        "typescript-node",
        languages=("typescript",),
        frameworks=("node", "typescript"),
        detection=DetectionRule(
            (("package.json", "tsconfig.json"),), (".ts", ".tsx"), ("typescript",)
        ),
        layouts=("test", "tests", "__tests__", "*.test.ts", "*.spec.ts"),
        capabilities={
            Capability.BUILD: _template(("npm", "run", "build")),
            Capability.UNIT: _template(("npm", "test", "--", "--run")),
            Capability.INTEGRATION: _template(("npm", "run", "test:integration")),
        },
    ),
    _spec(
        "react",
        languages=("javascript", "typescript"),
        frameworks=("react",),
        detection=DetectionRule(
            (("package.json",),),
            (".js", ".jsx", ".ts", ".tsx"),
            ("javascript", "typescript"),
            ("react",),
        ),
        layouts=("src/**/__tests__", "src/**/*.test.*", "e2e"),
        capabilities={
            Capability.BUILD: _template(("npm", "run", "build")),
            Capability.UNIT: _template(("npm", "test", "--", "--run")),
            Capability.UI_E2E: _template(("npm", "run", "test:e2e")),
        },
    ),
    _spec(
        "vue",
        languages=("javascript", "typescript"),
        frameworks=("vue",),
        detection=DetectionRule(
            (("package.json",),),
            (".vue", ".js", ".ts"),
            ("javascript", "typescript", "vue"),
            ("vue",),
        ),
        layouts=("src/**/__tests__", "src/**/*.spec.*", "e2e"),
        capabilities={
            Capability.BUILD: _template(("npm", "run", "build")),
            Capability.UNIT: _template(("npm", "test", "--", "--run")),
            Capability.UI_E2E: _template(("npm", "run", "test:e2e")),
        },
    ),
    _spec(
        "objective-c-xcode",
        languages=("objective-c", "objective-cpp"),
        frameworks=("xcode", "xctest"),
        detection=DetectionRule(
            (("*.xcodeproj",), ("*.xcworkspace",)),
            (".m", ".mm"),
            ("objective-c", "objective-cpp"),
        ),
        layouts=("Tests", "UITests", "*Tests"),
        capabilities={
            Capability.BUILD: _template(
                ("xcodebuild", "-scheme", "{scheme}", "build")
            ),
            Capability.UNIT: _template(
                ("xcodebuild", "-scheme", "{scheme}", "test")
            ),
        },
    ),
    _spec(
        "swift-package",
        languages=("swift",),
        frameworks=("swift-package-manager", "xctest"),
        detection=DetectionRule((("Package.swift",),), (".swift",), ("swift",)),
        layouts=("Tests",),
        capabilities={
            Capability.BUILD: _template(("swift", "build")),
            Capability.UNIT: _template(("swift", "test")),
            Capability.DISCOVERY: _template(("swift", "test", "list")),
        },
    ),
    _spec(
        "swift-xcode",
        languages=("swift",),
        frameworks=("xcode", "xctest"),
        detection=DetectionRule(
            (("*.xcodeproj",), ("*.xcworkspace",)), (".swift",), ("swift",)
        ),
        layouts=("Tests", "UITests", "*Tests"),
        capabilities={
            Capability.BUILD: _template(
                ("xcodebuild", "-scheme", "{scheme}", "build")
            ),
            Capability.UNIT: _template(
                ("xcodebuild", "-scheme", "{scheme}", "test")
            ),
            Capability.UI_E2E: _template(
                ("xcodebuild", "-scheme", "{scheme}", "test", "-only-testing:{ui_target}")
            ),
        },
    ),
    _spec(
        "flutter",
        languages=("dart",),
        frameworks=("flutter",),
        detection=DetectionRule(
            (("pubspec.yaml",),), (".dart",), ("dart", "flutter"), ("flutter",)
        ),
        layouts=("test", "integration_test"),
        capabilities={
            Capability.BUILD: _template(("flutter", "build", "bundle")),
            Capability.UNIT: _template(("flutter", "test")),
            Capability.INTEGRATION: _template(("flutter", "test", "integration_test")),
        },
    ),
)


ADAPTER_REGISTRY: Mapping[str, AdapterSpec] = MappingProxyType(
    {adapter.key: adapter for adapter in _ADAPTERS}
)


def adapter_for(key: str) -> AdapterSpec:
    try:
        return ADAPTER_REGISTRY[key]
    except KeyError as exc:
        raise UnsupportedAdapterError(f"unsupported adapter: {key!r}") from exc


def detect_adapters(fingerprint: ProjectFingerprint) -> tuple[AdapterSpec, ...]:
    """Return every exact match; an empty tuple explicitly means unsupported."""

    return tuple(
        adapter for adapter in ADAPTER_REGISTRY.values() if adapter.detection.matches(fingerprint)
    )


def capability_plan(
    adapter_key: str,
    capability: Capability | str,
    *,
    parameters: Mapping[str, str] | None = None,
) -> CapabilityPlan:
    try:
        exact_capability = Capability(capability)
    except (TypeError, ValueError) as exc:
        raise AdapterContractError(f"unsupported capability: {capability!r}") from exc
    return adapter_for(adapter_key).plan(exact_capability, parameters=parameters)


def operation_support(
    adapter_key: str, operation: SdkOperation | str
) -> OperationSupport:
    try:
        exact_operation = SdkOperation(operation)
    except (TypeError, ValueError) as exc:
        raise AdapterContractError(f"unsupported SDK operation: {operation!r}") from exc
    return adapter_for(adapter_key).sdk_operations[exact_operation]


_GENERATABLE_TEST_KINDS = frozenset(
    {Capability.UNIT, Capability.INTEGRATION, Capability.CONTRACT, Capability.UI_E2E}
)


def generate_test_descriptor(
    adapter_key: str, request: Mapping[str, Any]
) -> GeneratedTestDescriptor:
    """Generate an in-memory typed descriptor; never materialize source files."""

    adapter = adapter_for(adapter_key)
    exact = _require_exact_object(
        request,
        label="generation request",
        allowed=frozenset(
            {"suite_id", "test_kind", "target_paths", "requirement_ids", "native_layout"}
        ),
        required=frozenset(
            {"suite_id", "test_kind", "target_paths", "requirement_ids"}
        ),
    )
    suite_id = _normalize_resource_id(exact["suite_id"], label="suite_id")
    raw_test_kind = exact["test_kind"]
    try:
        test_kind = Capability(raw_test_kind)
    except (TypeError, ValueError) as exc:
        raise AdapterContractError("test_kind is unsupported") from exc
    if test_kind not in _GENERATABLE_TEST_KINDS:
        raise AdapterContractError("test_kind is not a generatable test capability")
    if test_kind not in adapter.capabilities:
        raise UnsupportedCapabilityError(adapter.key, test_kind)
    target_paths = _normalize_relative_paths(
        exact["target_paths"], label="target_paths"
    )
    requirement_ids = _normalize_resource_ids(
        exact["requirement_ids"], label="requirement_ids"
    )
    native_layout = exact.get("native_layout", adapter.native_test_layouts[0])
    if not isinstance(native_layout, str) or native_layout not in adapter.native_test_layouts:
        raise AdapterContractError(
            f"native_layout is not declared by adapter {adapter.key!r}"
        )
    cases = tuple(
        GeneratedTestCase(
            test_case_id=f"CASE-{index:04d}",
            adapter_key=adapter.key,
            test_kind=test_kind.value,
            target_path=target_path,
            requirement_ids=requirement_ids,
        )
        for index, target_path in enumerate(target_paths, start=1)
    )
    return GeneratedTestDescriptor(
        adapter_key=adapter.key,
        suite_id=suite_id,
        test_kind=test_kind.value,
        target_paths=target_paths,
        requirement_ids=requirement_ids,
        native_layout=native_layout,
        cases=cases,
    )


def validate_test_descriptor(
    adapter_key: str, descriptor: Mapping[str, Any]
) -> GeneratedTestDescriptor:
    """Validate and normalize a descriptor without reading a repository."""

    adapter = adapter_for(adapter_key)
    exact = _require_exact_object(
        descriptor,
        label="test descriptor",
        allowed=frozenset(
            {
                "schema_version",
                "adapter_key",
                "suite_id",
                "test_kind",
                "target_paths",
                "requirement_ids",
                "native_layout",
                "cases",
            }
        ),
        required=frozenset(
            {
                "schema_version",
                "adapter_key",
                "suite_id",
                "test_kind",
                "target_paths",
                "requirement_ids",
                "native_layout",
                "cases",
            }
        ),
    )
    if exact["schema_version"] != "elmos.autonomous-qa.adapter-test-descriptor.v1":
        raise AdapterContractError("test descriptor schema_version is unsupported")
    if exact["adapter_key"] != adapter.key:
        raise AdapterContractError("test descriptor adapter identity does not match")
    raw_cases = exact["cases"]
    if not isinstance(raw_cases, list) or len(raw_cases) > _MAX_COLLECTION_ITEMS:
        raise AdapterContractError("test descriptor cases must be a bounded array")
    normalized = generate_test_descriptor(
        adapter.key,
        {
            "suite_id": exact["suite_id"],
            "test_kind": exact["test_kind"],
            "target_paths": exact["target_paths"],
            "requirement_ids": exact["requirement_ids"],
            "native_layout": exact["native_layout"],
        },
    )
    if dict(exact) != normalized.as_dict():
        raise AdapterContractError(
            "test descriptor cases are not the canonical generated representation"
        )
    return normalized


def normalize_diagnostics(
    adapter_key: str, diagnostics: Any
) -> tuple[NormalizedDiagnostic, ...]:
    """Normalize inert diagnostic data without invoking a compiler or test runner."""

    adapter_for(adapter_key)
    if (
        not isinstance(diagnostics, list)
        or len(diagnostics) > _MAX_COLLECTION_ITEMS
    ):
        raise AdapterContractError("diagnostics must be a bounded array")
    normalized: dict[tuple[Any, ...], NormalizedDiagnostic] = {}
    for index, value in enumerate(diagnostics):
        exact = _require_exact_object(
            value,
            label=f"diagnostics[{index}]",
            allowed=frozenset({"code", "severity", "message", "path", "line"}),
            required=frozenset({"code", "severity", "message"}),
        )
        code = _normalize_resource_id(exact["code"], label=f"diagnostics[{index}].code")
        severity_raw = exact["severity"]
        if not isinstance(severity_raw, str):
            raise AdapterContractError(f"diagnostics[{index}].severity must be text")
        severity = severity_raw.upper()
        if severity not in {"INFO", "WARNING", "ERROR"}:
            raise AdapterContractError(f"diagnostics[{index}].severity is unsupported")
        message = _normalize_text(
            exact["message"], label=f"diagnostics[{index}].message"
        )
        path_value = exact.get("path")
        path = (
            None
            if path_value is None
            else _normalize_relative_path(path_value)
        )
        line_value = exact.get("line")
        if line_value is not None and (type(line_value) is not int or line_value < 1):
            raise AdapterContractError(
                f"diagnostics[{index}].line must be a positive integer"
            )
        item = NormalizedDiagnostic(code, severity, message, path, line_value)
        normalized[(code, severity, message, path, line_value)] = item
    severity_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    return tuple(
        sorted(
            normalized.values(),
            key=lambda item: (
                severity_order[item.severity],
                item.path or "",
                item.line or 0,
                item.code,
                item.message,
            ),
        )
    )


def _adapter_record(adapter: AdapterSpec) -> dict[str, Any]:
    return {
        "adapter_key": adapter.key,
        "languages": list(adapter.languages),
        "frameworks": list(adapter.frameworks),
        "native_test_layouts": list(adapter.native_test_layouts),
        "capabilities": sorted(capability.value for capability in adapter.capabilities),
        "capability_support": [
            {
                "capability": capability.value,
                "supported": capability in adapter.capabilities,
                "mode": (
                    OperationMode.EXTERNAL_ADAPTER_REQUIRED.value
                    if capability in adapter.capabilities
                    else "UNSUPPORTED"
                ),
            }
            for capability in Capability
        ],
        "sdk_operations": [
            {
                "operation": operation.value,
                "supported": support.supported,
                "mode": support.mode.value,
                "reason": support.reason,
            }
            for operation, support in sorted(
                adapter.sdk_operations.items(), key=lambda item: item[0].value
            )
        ],
    }


def _safety_outputs(*, local_operation_performed: bool) -> dict[str, Any]:
    return {
        "fallback_selected": False,
        "shell_invocation_performed": False,
        "command_execution_performed": False,
        "file_reads_performed": False,
        "file_writes_performed": False,
        "local_operation_performed": local_operation_performed,
        "external_evidence_status": "NOT_RUN",
    }


def _local_result(code: str, outputs: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "state": "SUCCEEDED",
        "code": code,
        "outputs": {**dict(outputs), **_safety_outputs(local_operation_performed=True)},
        "implementation_state": "LOCAL_EXECUTED",
    }


def _unsupported_result(
    *, operation: str, adapter_key: str, capability: str | None = None
) -> Mapping[str, Any]:
    outputs: dict[str, Any] = {
        "operation": operation,
        "adapter_key": adapter_key,
        "supported": False,
        **_safety_outputs(local_operation_performed=False),
    }
    if capability is not None:
        outputs["capability"] = capability
    return {
        "state": "NOT_APPLICABLE",
        "code": (
            "UNSUPPORTED_ADAPTER_CAPABILITY"
            if capability is not None
            else "UNSUPPORTED_ADAPTER"
        ),
        "outputs": outputs,
        "implementation_state": "LOCAL_VALIDATED",
    }


def _external_plan_result(
    *, operation: SdkOperation, adapter: AdapterSpec, plan: Mapping[str, Any]
) -> Mapping[str, Any]:
    plan_document = dict(plan)
    commands = plan_document.get("commands", [])
    if not isinstance(commands, list):
        raise AdapterContractError("external adapter plan commands must be an array")
    return {
        "state": "NOT_RUN",
        "code": "EXTERNAL_ADAPTER_REQUIRED",
        "outputs": {
            "operation": operation.value,
            "adapter_key": adapter.key,
            "supported": True,
            "plan_only": True,
            "plan": plan_document,
            # Preserve the original command-plan response shape while making the
            # complete external-adapter plan available under ``plan``.
            "commands": list(commands),
            "qualification": {
                "status": "NOT_RUN",
                "caller_assertions_accepted": False,
                "trusted_probe_receipt": "NOT_RUN",
            },
            **_safety_outputs(local_operation_performed=False),
        },
        "implementation_state": "EXTERNAL_ADAPTER_REQUIRED",
    }


def execute_adapter_contract(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Run local SDK operations or create inert external-adapter plans."""

    if not isinstance(inputs, Mapping) or any(type(key) is not str for key in inputs):
        raise AdapterContractError("adapter request must be an exact string-keyed object")
    operation = inputs.get("operation", "list")
    supported_operations = {"list", "plan"} | {
        item.value for item in SdkOperation
    }
    if not isinstance(operation, str) or operation not in supported_operations:
        raise AdapterContractError(
            "operation must be list, plan, detect, generate, validate, execute, "
            "collect_coverage, diagnose, or apply_patch"
        )
    allowed_fields = {
        "list": frozenset({"operation", "_runtime_context"}),
        "detect": frozenset({"operation", "fingerprint", "_runtime_context"}),
        "generate": frozenset(
            {"operation", "adapter_key", "request", "_runtime_context"}
        ),
        "validate": frozenset(
            {"operation", "adapter_key", "descriptor", "_runtime_context"}
        ),
        "execute": frozenset(
            {
                "operation",
                "adapter_key",
                "capability",
                "parameters",
                "_runtime_context",
            }
        ),
        "plan": frozenset(
            {
                "operation",
                "adapter_key",
                "capability",
                "parameters",
                "_runtime_context",
            }
        ),
        "collect_coverage": frozenset(
            {"operation", "adapter_key", "request", "_runtime_context"}
        ),
        "diagnose": frozenset(
            {"operation", "adapter_key", "diagnostics", "_runtime_context"}
        ),
        "apply_patch": frozenset(
            {"operation", "adapter_key", "patch", "_runtime_context"}
        ),
    }[operation]
    unexpected = sorted(set(inputs).difference(allowed_fields))
    if unexpected:
        raise AdapterContractError(
            f"adapter {operation} request has unsupported fields: {unexpected}"
        )
    runtime_context = inputs.get("_runtime_context")
    if runtime_context is not None and not isinstance(runtime_context, Mapping):
        raise AdapterContractError("_runtime_context must be an object")
    canonical_operation = (
        SdkOperation.EXECUTE.value if operation == "plan" else operation
    )

    if operation == "list":
        return _local_result(
            "EXACT_ADAPTER_REGISTRY_LISTED",
            {
                "adapters": [
                    _adapter_record(adapter) for adapter in ADAPTER_REGISTRY.values()
                ],
                "adapter_count": len(ADAPTER_REGISTRY),
                "sdk_operations": [operation.value for operation in SdkOperation],
            },
        )

    if operation == "detect":
        fingerprint = _require_exact_object(
            inputs.get("fingerprint"),
            label="fingerprint",
            allowed=frozenset({"paths", "dependencies", "declared_languages"}),
            required=frozenset({"paths"}),
        )
        paths = fingerprint["paths"]
        dependencies = fingerprint.get("dependencies", [])
        languages = fingerprint.get("declared_languages", [])
        if not all(
            isinstance(value, list)
            and len(value) <= _MAX_COLLECTION_ITEMS
            and all(isinstance(item, str) for item in value)
            for value in (paths, dependencies, languages)
        ):
            raise AdapterContractError("fingerprint collections must be string arrays")
        matches = detect_adapters(
            ProjectFingerprint.create(
                paths,
                dependencies=dependencies,
                declared_languages=languages,
            )
        )
        result = _local_result(
            "EXACT_ADAPTERS_DETECTED" if matches else "NO_EXACT_ADAPTER_MATCH",
            {"matches": [_adapter_record(adapter) for adapter in matches]},
        )
        if not matches:
            result = {**result, "state": "NOT_APPLICABLE"}
        return result

    adapter_key = _normalize_resource_id(
        inputs.get("adapter_key"), label="adapter_key"
    )
    try:
        adapter = adapter_for(adapter_key)
    except UnsupportedAdapterError:
        return _unsupported_result(
            operation=canonical_operation, adapter_key=adapter_key
        )

    if operation == "generate":
        request = inputs.get("request")
        if not isinstance(request, Mapping):
            raise AdapterContractError("generation request must be an object")
        try:
            descriptor = generate_test_descriptor(adapter.key, request)
        except UnsupportedCapabilityError as exc:
            return _unsupported_result(
                operation=operation,
                adapter_key=adapter.key,
                capability=exc.capability.value,
            )
        capability = Capability(descriptor.test_kind)
        return _local_result(
            "IN_MEMORY_TEST_DESCRIPTOR_GENERATED",
            {
                "adapter_key": adapter.key,
                "descriptor": descriptor.as_dict(),
                "execution_supported": capability in adapter.capabilities,
                "artifact_materialized": False,
            },
        )

    if operation == "validate":
        descriptor = inputs.get("descriptor")
        if not isinstance(descriptor, Mapping):
            raise AdapterContractError("descriptor must be an object")
        try:
            normalized = validate_test_descriptor(adapter.key, descriptor)
        except UnsupportedCapabilityError as exc:
            return _unsupported_result(
                operation=operation,
                adapter_key=adapter.key,
                capability=exc.capability.value,
            )
        return _local_result(
            "TEST_DESCRIPTOR_VALIDATED",
            {
                "adapter_key": adapter.key,
                "valid": True,
                "normalized_descriptor": normalized.as_dict(),
            },
        )

    if operation == "diagnose":
        diagnostics = normalize_diagnostics(adapter.key, inputs.get("diagnostics"))
        counts = {
            severity: sum(item.severity == severity for item in diagnostics)
            for severity in ("ERROR", "WARNING", "INFO")
        }
        return _local_result(
            "DIAGNOSTICS_NORMALIZED",
            {
                "adapter_key": adapter.key,
                "diagnostics": [item.as_dict() for item in diagnostics],
                "counts": counts,
            },
        )

    if operation in {"execute", "plan"}:
        capability = inputs.get("capability")
        parameters = inputs.get("parameters", {})
        if not isinstance(capability, str):
            raise AdapterContractError("capability must be a string")
        if not isinstance(parameters, Mapping) or any(
            type(key) is not str or not isinstance(value, str)
            for key, value in parameters.items()
        ):
            raise AdapterContractError("parameters must be a string-to-string object")
        try:
            exact_capability = Capability(capability)
        except ValueError:
            unsupported_capability = _normalize_resource_id(
                capability, label="capability"
            )
            return _unsupported_result(
                operation=SdkOperation.EXECUTE.value,
                adapter_key=adapter.key,
                capability=unsupported_capability,
            )
        if exact_capability not in adapter.capabilities:
            return _unsupported_result(
                operation=SdkOperation.EXECUTE.value,
                adapter_key=adapter.key,
                capability=capability,
            )
        command_plan = adapter.plan(exact_capability, parameters=parameters)
        commands = [
            {"argv": list(command.argv), "cwd": command.cwd, "shell": False}
            for command in command_plan.require_commands()
        ]
        return _external_plan_result(
            operation=SdkOperation.EXECUTE,
            adapter=adapter,
            plan={
                "capability": exact_capability.value,
                "commands": commands,
                "required_external_evidence": [
                    "toolchain_identity",
                    "raw_exit_status",
                    "raw_stdout_stderr",
                ],
                "execution_status": "NOT_RUN",
            },
        )

    if operation == "collect_coverage":
        request = _require_exact_object(
            inputs.get("request"),
            label="coverage request",
            allowed=frozenset({"capability", "format", "include_paths"}),
            required=frozenset({"capability", "format"}),
        )
        raw_capability = request["capability"]
        if not isinstance(raw_capability, str):
            raise AdapterContractError("coverage capability must be a string")
        try:
            capability = Capability(raw_capability)
        except ValueError:
            unsupported_capability = _normalize_resource_id(
                raw_capability, label="coverage capability"
            )
            return _unsupported_result(
                operation=operation,
                adapter_key=adapter.key,
                capability=unsupported_capability,
            )
        if capability not in adapter.capabilities:
            return _unsupported_result(
                operation=operation,
                adapter_key=adapter.key,
                capability=capability.value,
            )
        coverage_format = request["format"]
        if not isinstance(coverage_format, str) or coverage_format not in {
            "native",
            "json",
            "lcov",
            "cobertura",
        }:
            raise AdapterContractError("coverage format is unsupported")
        include_paths = _normalize_relative_paths(
            request.get("include_paths", []),
            label="include_paths",
            allow_empty=True,
        )
        return _external_plan_result(
            operation=SdkOperation.COLLECT_COVERAGE,
            adapter=adapter,
            plan={
                "capability": capability.value,
                "format": coverage_format,
                "include_paths": list(include_paths),
                "commands": [],
                "required_external_evidence": [
                    "coverage_tool_identity",
                    "raw_coverage_artifact",
                    "source_digest_binding",
                ],
                "collection_status": "NOT_RUN",
            },
        )

    if operation == "apply_patch":
        patch = _require_exact_object(
            inputs.get("patch"),
            label="patch request",
            allowed=frozenset({"patch_id", "paths", "base_digest", "patch_digest"}),
            required=frozenset({"patch_id", "paths", "base_digest", "patch_digest"}),
        )
        patch_id = _normalize_resource_id(patch["patch_id"], label="patch_id")
        paths = _normalize_relative_paths(patch["paths"], label="patch paths")
        base_digest = _normalize_sha256(patch["base_digest"], label="base_digest")
        patch_digest = _normalize_sha256(patch["patch_digest"], label="patch_digest")
        return _external_plan_result(
            operation=SdkOperation.APPLY_PATCH,
            adapter=adapter,
            plan={
                "patch_id": patch_id,
                "paths": list(paths),
                "base_digest": base_digest,
                "patch_digest": patch_digest,
                "commands": [],
                "required_external_evidence": [
                    "authorization_receipt",
                    "preimage_digest_verification",
                    "postimage_digest_verification",
                    "rollback_receipt",
                ],
                "mutation_status": "NOT_RUN",
                "patch_applied": False,
            },
        )

    raise AdapterContractError(f"unhandled adapter operation: {operation!r}")

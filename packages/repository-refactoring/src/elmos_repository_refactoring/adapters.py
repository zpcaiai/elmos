"""Language adapters, capability levels and the honesty rules around them.

Three separate facts are kept separate on purpose, because conflating them is
how a platform ends up claiming L4 for a language it can only lex:

``declared``
    What an adapter descriptor *aspires* to (``adapters/*.yaml`` in the Skills
    package).  Always L0 unless a signed attestation says otherwise.
``attested``
    What a signed registry entry grants, bound to an adapter digest and a
    certification suite result.  Supplied by the host, never by a task payload.
``proven``
    What this process can actually do right now with the engines compiled into
    it.  :data:`NATIVE_ENGINE_LEVELS` is derived from the transform engines that
    genuinely exist in :mod:`elmos_repository_refactoring.transform`.

The effective level is the **minimum** of the three.  A capability that was
never probed is reported as ``not-probed`` and is never counted as present.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from .contracts import (
    AdapterLevel,
    ContractError,
    NetworkPolicy,
    integer_value,
    optional_string,
    reject_unknown_fields,
    require_digest,
    require_enum,
    require_mapping,
    require_mapping_sequence,
    require_string,
    require_string_sequence,
    sha256_payload,
)

ADAPTER_KIND = "LanguageAdapter"
API_VERSION = "elmos.dev/v1"

CAPABILITY_STATES = ("full", "partial", "none", "not-probed")

CAPABILITY_NAMES: tuple[str, ...] = (
    "losslessRoundTrip",
    "symbolResolution",
    "typeAttribution",
    "repositoryRename",
    "moveSymbol",
    "changeSignature",
    "buildGraph",
    "formatTouchedRange",
    "incrementalIndex",
    "generatedCodeAwareness",
    "dataflow",
    "callGraph",
    "dynamicReferenceDetection",
    "macroAwareness",
    "binaryCompatibility",
)

ADAPTER_OPERATIONS: tuple[str, ...] = (
    "probe",
    "restore",
    "parse",
    "index",
    "query",
    "lower",
    "apply",
    "format",
    "validate",
    "rollback",
)


@dataclass(frozen=True, slots=True)
class Toolchain:
    name: str
    version_range: str

    def to_payload(self) -> dict[str, Any]:
        return {"name": self.name, "versionRange": self.version_range}


@dataclass(frozen=True, slots=True)
class ResourceProfile:
    cpu: int = 2
    memory_mib: int = 4096
    disk_mib: int = 10240
    timeout_seconds: int = 3600

    def to_payload(self) -> dict[str, Any]:
        return {
            "cpu": self.cpu,
            "memoryMiB": self.memory_mib,
            "diskMiB": self.disk_mib,
            "timeoutSeconds": self.timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class AdapterSecurity:
    network: NetworkPolicy = NetworkPolicy.DENY
    exec_allowlist: tuple[str, ...] = ()
    write_paths: tuple[str, ...] = ("/workspace", "/artifacts", "/tmp")  # noqa: S108

    def to_payload(self) -> dict[str, Any]:
        return {
            "network": self.network.value,
            "exec": list(self.exec_allowlist),
            "writePaths": list(self.write_paths),
        }


@dataclass(frozen=True, slots=True)
class AdapterDescriptor:
    """A declared adapter.  ``certification_level`` here is an aspiration."""

    name: str
    version: str
    languages: tuple[str, ...]
    toolchains: tuple[Toolchain, ...]
    build_systems: tuple[str, ...]
    capabilities: Mapping[str, str]
    operations: tuple[str, ...]
    resource_profile: ResourceProfile
    security: AdapterSecurity
    owner: str | None = None
    declared_level: AdapterLevel = AdapterLevel.L0
    digest: str | None = None

    def to_payload(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "certificationLevel": self.declared_level.value,
        }
        if self.owner:
            metadata["owner"] = self.owner
        if self.digest:
            metadata["digest"] = self.digest
        return {
            "apiVersion": API_VERSION,
            "kind": ADAPTER_KIND,
            "metadata": metadata,
            "spec": {
                "languages": list(self.languages),
                "toolchains": [item.to_payload() for item in self.toolchains],
                "buildSystems": list(self.build_systems),
                "capabilities": dict(sorted(self.capabilities.items())),
                "operations": list(self.operations),
                "resourceProfile": self.resource_profile.to_payload(),
                "security": self.security.to_payload(),
            },
        }

    @property
    def content_digest(self) -> str:
        payload = self.to_payload()
        payload["metadata"].pop("digest", None)
        return sha256_payload(payload)

    def capability(self, name: str) -> str:
        return self.capabilities.get(name, "not-probed")

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> AdapterDescriptor:
        value = require_mapping(payload, "adapter")
        reject_unknown_fields(value, {"apiVersion", "kind", "metadata", "spec"}, "adapter")
        if value.get("apiVersion") != API_VERSION:
            raise ContractError("invalid_api_version", f"adapter.apiVersion must be {API_VERSION}")
        if value.get("kind") != ADAPTER_KIND:
            raise ContractError("invalid_kind", f"adapter.kind must be {ADAPTER_KIND}")
        metadata = require_mapping(value.get("metadata"), "adapter.metadata")
        reject_unknown_fields(
            metadata, {"name", "version", "digest", "owner", "certificationLevel"}, "adapter.metadata"
        )
        spec = require_mapping(value.get("spec"), "adapter.spec")
        reject_unknown_fields(
            spec,
            {"languages", "toolchains", "buildSystems", "capabilities", "operations", "resourceProfile", "security"},
            "adapter.spec",
        )
        capabilities_raw = require_mapping(spec.get("capabilities", {}), "adapter.spec.capabilities")
        capabilities: dict[str, str] = {}
        for key, item in capabilities_raw.items():
            name = require_string(key, "adapter.spec.capabilities key", max_length=64)
            state = require_string(item, f"adapter.spec.capabilities.{name}", max_length=32)
            if state not in CAPABILITY_STATES:
                raise ContractError(
                    "invalid_capability_state",
                    f"adapter capability '{name}' must be one of: {', '.join(CAPABILITY_STATES)}",
                )
            capabilities[name] = state
        operations = require_string_sequence(spec.get("operations", ()), "adapter.spec.operations", unique=True)
        for operation in operations:
            if operation not in ADAPTER_OPERATIONS:
                raise ContractError("unknown_adapter_operation", f"unknown adapter operation '{operation}'")
        profile = require_mapping(spec.get("resourceProfile", {}), "adapter.spec.resourceProfile")
        security = require_mapping(spec.get("security", {}), "adapter.spec.security")
        digest = metadata.get("digest")
        return cls(
            name=require_string(metadata.get("name"), "adapter.metadata.name", max_length=128),
            version=require_string(metadata.get("version"), "adapter.metadata.version", max_length=64),
            languages=require_string_sequence(
                spec.get("languages"), "adapter.spec.languages", allow_empty=False, unique=True
            ),
            toolchains=tuple(
                Toolchain(
                    name=require_string(item.get("name"), "adapter.spec.toolchains[].name", max_length=128),
                    version_range=require_string(
                        item.get("versionRange"), "adapter.spec.toolchains[].versionRange", max_length=64
                    ),
                )
                for item in require_mapping_sequence(spec.get("toolchains", ()), "adapter.spec.toolchains")
            ),
            build_systems=require_string_sequence(spec.get("buildSystems", ()), "adapter.spec.buildSystems"),
            capabilities=MappingProxyType(capabilities),
            operations=operations,
            resource_profile=ResourceProfile(
                cpu=integer_value(profile.get("cpu", 2), "adapter.spec.resourceProfile.cpu", minimum=1),
                memory_mib=integer_value(
                    profile.get("memoryMiB", 4096), "adapter.spec.resourceProfile.memoryMiB", minimum=64
                ),
                disk_mib=integer_value(
                    profile.get("diskMiB", 10240), "adapter.spec.resourceProfile.diskMiB", minimum=64
                ),
                timeout_seconds=integer_value(
                    profile.get("timeoutSeconds", 3600), "adapter.spec.resourceProfile.timeoutSeconds", minimum=1
                ),
            ),
            security=AdapterSecurity(
                network=require_enum(security.get("network", "deny"), NetworkPolicy, "adapter.spec.security.network"),
                exec_allowlist=require_string_sequence(security.get("exec", ()), "adapter.spec.security.exec"),
                write_paths=require_string_sequence(
                    security.get("writePaths", ("/workspace", "/artifacts", "/tmp")),  # noqa: S108
                    "adapter.spec.security.writePaths",
                ),
            ),
            owner=optional_string(metadata.get("owner"), "adapter.metadata.owner"),
            declared_level=require_enum(
                metadata.get("certificationLevel", "L0"), AdapterLevel, "adapter.metadata.certificationLevel"
            ),
            digest=None if digest in (None, "sha256:build-time") else require_digest(digest, "adapter.metadata.digest"),
        )


@dataclass(frozen=True, slots=True)
class AdapterAttestation:
    """A signed grant of a certification level for one adapter digest."""

    adapter_name: str
    adapter_digest: str
    level: AdapterLevel
    certification_suite_digest: str
    key_id: str
    signature: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter_name,
            "adapterDigest": self.adapter_digest,
            "level": self.level.value,
            "certificationSuiteDigest": self.certification_suite_digest,
            "keyId": self.key_id,
            "signature": self.signature,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> AdapterAttestation:
        value = require_mapping(payload, "attestation")
        reject_unknown_fields(
            value,
            {"adapter", "adapterDigest", "level", "certificationSuiteDigest", "keyId", "signature"},
            "attestation",
        )
        return cls(
            adapter_name=require_string(value.get("adapter"), "attestation.adapter", max_length=128),
            adapter_digest=require_digest(value.get("adapterDigest"), "attestation.adapterDigest"),
            level=require_enum(value.get("level"), AdapterLevel, "attestation.level"),
            certification_suite_digest=require_digest(
                value.get("certificationSuiteDigest"), "attestation.certificationSuiteDigest"
            ),
            key_id=require_string(value.get("keyId"), "attestation.keyId", max_length=128),
            signature=require_string(value.get("signature"), "attestation.signature", max_length=4096),
        )


# ---------------------------------------------------------------------------
# What this process can actually prove
# ---------------------------------------------------------------------------

#: Levels the in-process deterministic engines genuinely reach.  These values
#: are asserted by the engine test-suite, not by a descriptor file.
#:
#: * ``python`` — real ``ast``/token-level rewriting with lossless round-trip,
#:   project-wide symbol and import resolution.
#: * ``sql`` — dialect-neutral statement splitting plus expand-contract
#:   migration synthesis and phase-order checking.
#: * text-structured formats — lossless line/range editing only.
#: Everything else is inventory-only until a host plugs in a real backend.
NATIVE_ENGINE_LEVELS: Mapping[str, AdapterLevel] = MappingProxyType(
    {
        "python": AdapterLevel.L2,
        "sql": AdapterLevel.L2,
        "json": AdapterLevel.L1,
        "yaml": AdapterLevel.L1,
        "toml": AdapterLevel.L1,
        "properties": AdapterLevel.L1,
        "markdown": AdapterLevel.L1,
        "text": AdapterLevel.L1,
        "typescript": AdapterLevel.L1,
        "javascript": AdapterLevel.L1,
        "java": AdapterLevel.L1,
        "go": AdapterLevel.L1,
        "csharp": AdapterLevel.L1,
        "kotlin": AdapterLevel.L1,
        "rust": AdapterLevel.L1,
        "php": AdapterLevel.L1,
        "ruby": AdapterLevel.L1,
        "swift": AdapterLevel.L1,
        "dart": AdapterLevel.L1,
        "c": AdapterLevel.L1,
        "cpp": AdapterLevel.L1,
    }
)


def _descriptor(
    name: str,
    languages: Iterable[str],
    toolchains: Iterable[tuple[str, str]],
    build_systems: Iterable[str],
    capabilities: Mapping[str, str],
    *,
    exec_allowlist: Iterable[str] = (),
    cpu: int = 4,
    memory_mib: int = 8192,
) -> AdapterDescriptor:
    return AdapterDescriptor(
        name=name,
        version="1.0.0",
        languages=tuple(languages),
        toolchains=tuple(Toolchain(item, version) for item, version in toolchains),
        build_systems=tuple(build_systems),
        capabilities=MappingProxyType(dict(capabilities)),
        operations=ADAPTER_OPERATIONS,
        resource_profile=ResourceProfile(cpu=cpu, memory_mib=memory_mib),
        security=AdapterSecurity(
            network=NetworkPolicy.RESTORE_ONLY,
            exec_allowlist=tuple(exec_allowlist),
        ),
        owner="elmos-refactoring-platform",
        declared_level=AdapterLevel.L0,
    )


_FULL_SET = {name: "full" for name in CAPABILITY_NAMES}
_SYNTAX_ONLY = {
    "losslessRoundTrip": "full",
    "formatTouchedRange": "full",
    "symbolResolution": "partial",
    "typeAttribution": "none",
    "buildGraph": "partial",
    "incrementalIndex": "full",
    "repositoryRename": "partial",
    "moveSymbol": "partial",
    "changeSignature": "none",
    "generatedCodeAwareness": "partial",
    "dataflow": "none",
    "callGraph": "none",
    "dynamicReferenceDetection": "none",
}


BUILTIN_ADAPTERS: Mapping[str, AdapterDescriptor] = MappingProxyType(
    {
        descriptor.name: descriptor
        for descriptor in (
            _descriptor(
                "jvm-refactor-adapter",
                ("java", "kotlin", "groovy", "scala"),
                (("JDK", "17-25"), ("OpenRewrite", "locked"), ("Kotlin", "1.9-2.x")),
                ("Maven", "Gradle", "Bazel", "sbt"),
                {**_FULL_SET, "generatedCodeAwareness": "partial", "dataflow": "partial", "macroAwareness": "partial"},
                exec_allowlist=("java", "javac", "mvn", "gradle", "kotlinc"),
                cpu=8,
                memory_mib=16384,
            ),
            _descriptor(
                "js-ts-refactor-adapter",
                ("javascript", "typescript", "tsx", "jsx", "vue", "node"),
                (("Node.js", "20-24"), ("TypeScript", "5.x")),
                ("npm", "pnpm", "yarn", "Bun", "Nx", "Turborepo", "Bazel"),
                {**_FULL_SET, "binaryCompatibility": "none", "macroAwareness": "none"},
                exec_allowlist=("node", "npm", "pnpm", "yarn", "tsc", "eslint"),
            ),
            _descriptor(
                "python-refactor-adapter",
                ("python",),
                (("CPython", "3.9-3.14"), ("LibCST", "locked")),
                ("uv", "Poetry", "pip", "PDM", "Bazel"),
                {
                    **_FULL_SET,
                    "typeAttribution": "partial",
                    "generatedCodeAwareness": "partial",
                    "dataflow": "partial",
                    "callGraph": "partial",
                    "dynamicReferenceDetection": "partial",
                    "binaryCompatibility": "none",
                    "macroAwareness": "none",
                },
                exec_allowlist=("python", "uv", "poetry", "pip", "pytest", "mypy", "ruff"),
            ),
            _descriptor(
                "dotnet-refactor-adapter",
                ("csharp", "vbnet", "fsharp"),
                (("dotnet SDK", "8-10"), ("Roslyn", "locked")),
                ("dotnet", "MSBuild", "Bazel"),
                _FULL_SET,
                exec_allowlist=("dotnet", "msbuild"),
                cpu=8,
                memory_mib=16384,
            ),
            _descriptor(
                "go-refactor-adapter",
                ("go",),
                (("Go", "1.22-1.25"),),
                ("go modules", "Bazel"),
                {**_FULL_SET, "macroAwareness": "none"},
                exec_allowlist=("go", "gofmt", "gopls"),
            ),
            _descriptor(
                "rust-refactor-adapter",
                ("rust",),
                (("Rust", "1.75-1.90"),),
                ("Cargo", "Bazel"),
                {**_FULL_SET, "dynamicReferenceDetection": "partial"},
                exec_allowlist=("cargo", "rustc", "rustfmt"),
                cpu=8,
                memory_mib=16384,
            ),
            _descriptor(
                "cpp-refactor-adapter",
                ("c", "cpp", "objective-c"),
                (("Clang", "17-20"), ("CMake", "3.25+")),
                ("CMake", "Ninja", "Bazel", "Make", "Xcode"),
                {**_FULL_SET, "typeAttribution": "partial", "dataflow": "partial"},
                exec_allowlist=("clang", "clang++", "cmake", "ninja"),
                cpu=8,
                memory_mib=16384,
            ),
            _descriptor(
                "swift-objc-refactor-adapter",
                ("swift", "objective-c"),
                (("Swift", "5.9-6.x"), ("Xcode", "15-16")),
                ("SwiftPM", "Xcode", "Bazel"),
                {**_SYNTAX_ONLY, "symbolResolution": "full", "typeAttribution": "partial"},
                exec_allowlist=("swift", "swiftc", "xcodebuild"),
            ),
            _descriptor(
                "dart-flutter-refactor-adapter",
                ("dart", "flutter"),
                (("Dart", "3.3-3.9"), ("Flutter", "3.x")),
                ("pub", "Flutter"),
                {**_SYNTAX_ONLY, "symbolResolution": "full", "typeAttribution": "partial"},
                exec_allowlist=("dart", "flutter"),
            ),
            _descriptor(
                "php-refactor-adapter",
                ("php",),
                (("PHP", "8.1-8.4"), ("PHP-Parser", "locked")),
                ("Composer",),
                {**_SYNTAX_ONLY, "symbolResolution": "full"},
                exec_allowlist=("php", "composer", "phpstan"),
            ),
            _descriptor(
                "ruby-refactor-adapter",
                ("ruby",),
                (("Ruby", "3.1-3.4"), ("Prism", "locked")),
                ("Bundler", "Bazel"),
                {**_SYNTAX_ONLY, "symbolResolution": "partial"},
                exec_allowlist=("ruby", "bundle", "rubocop"),
            ),
            _descriptor(
                "sql-data-refactor-adapter",
                ("sql", "plsql", "tsql", "postgresql"),
                (("PostgreSQL", "13-17"), ("MySQL", "8.x")),
                ("Flyway", "Liquibase", "Alembic", "EF migrations", "Rails migrations"),
                {
                    "losslessRoundTrip": "full",
                    "symbolResolution": "full",
                    "typeAttribution": "full",
                    "buildGraph": "partial",
                    "formatTouchedRange": "full",
                    "incrementalIndex": "full",
                    "repositoryRename": "full",
                    "moveSymbol": "none",
                    "changeSignature": "partial",
                    "generatedCodeAwareness": "none",
                    "dataflow": "partial",
                    "callGraph": "none",
                    "dynamicReferenceDetection": "partial",
                },
                exec_allowlist=("psql", "mysql", "flyway", "liquibase", "alembic"),
            ),
            _descriptor(
                "config-iac-refactor-adapter",
                ("yaml", "json", "xml", "hcl", "terraform", "dockerfile", "bash"),
                (("Terraform", "1.6-1.11"), ("Tree-sitter", "locked")),
                ("Terraform", "Kubernetes validators", "ShellCheck"),
                {**_SYNTAX_ONLY, "symbolResolution": "partial", "buildGraph": "partial"},
                exec_allowlist=("terraform", "kubectl", "shellcheck"),
            ),
        )
    }
)


LANGUAGE_TO_ADAPTER: Mapping[str, str] = MappingProxyType(
    {
        language: descriptor.name
        for descriptor in BUILTIN_ADAPTERS.values()
        for language in descriptor.languages
    }
)


@dataclass(frozen=True, slots=True)
class AdapterCapabilitySnapshot:
    """The resolved, honest view of adapter capability for one run."""

    descriptors: Mapping[str, AdapterDescriptor] = field(default_factory=lambda: BUILTIN_ADAPTERS)
    attestations: Mapping[str, AdapterAttestation] = field(default_factory=dict)
    native_levels: Mapping[str, AdapterLevel] = field(default_factory=lambda: NATIVE_ENGINE_LEVELS)
    #: Levels contributed by host-registered execution backends (a real
    #: compiler-driven adapter plugged in behind :mod:`sandbox`).  Empty by
    #: default: the pure core claims only what it can do itself.
    backend_levels: Mapping[str, AdapterLevel] = field(default_factory=dict)

    def descriptor_for(self, language: str) -> AdapterDescriptor | None:
        name = LANGUAGE_TO_ADAPTER.get(language)
        if name is None:
            for descriptor in self.descriptors.values():
                if language in descriptor.languages:
                    return descriptor
            return None
        return self.descriptors.get(name)

    def attested_level(self, adapter_name: str) -> AdapterLevel:
        attestation = self.attestations.get(adapter_name)
        if attestation is None:
            return AdapterLevel.L0
        descriptor = self.descriptors.get(adapter_name)
        if descriptor is not None and descriptor.content_digest != attestation.adapter_digest:
            # An attestation that does not bind this exact adapter content is
            # not an attestation for it.
            return AdapterLevel.L0
        return attestation.level

    def proven_level(self, language: str) -> AdapterLevel:
        """What this process can actually do: native engines or a real backend."""

        native = self.native_levels.get(language, AdapterLevel.L0)
        backend = self.backend_levels.get(language, AdapterLevel.L0)
        return native if native.rank >= backend.rank else backend

    def effective_level(self, language: str) -> AdapterLevel:
        """min(proven, attested) — with no attestation, ``proven`` stands alone.

        An attestation can only ever *lower* the answer relative to what the
        code proves, or confirm it.  It can never raise a language above what
        this process can execute, because a signature is not an implementation.
        """

        proven = self.proven_level(language)
        descriptor = self.descriptor_for(language)
        if descriptor is None or descriptor.name not in self.attestations:
            return proven
        attested = self.attested_level(descriptor.name)
        return proven if proven.rank <= attested.rank else attested

    def supports(self, language: str, required: AdapterLevel) -> bool:
        return self.effective_level(language).rank >= required.rank

    def capability(self, language: str, capability: str) -> str:
        descriptor = self.descriptor_for(language)
        if descriptor is None:
            return "not-probed"
        state = descriptor.capability(capability)
        if state in ("none", "not-probed"):
            return state
        # A declared capability is only real up to the effective level.
        if self.effective_level(language).rank <= AdapterLevel.L1.rank and capability in {
            "typeAttribution",
            "callGraph",
            "dataflow",
            "changeSignature",
            "binaryCompatibility",
        }:
            return "not-probed"
        return state

    def unsupported_languages(self, languages: Iterable[str], required: AdapterLevel) -> tuple[str, ...]:
        return tuple(sorted({language for language in languages if not self.supports(language, required)}))

    def to_payload(self) -> dict[str, Any]:
        languages = sorted({language for descriptor in self.descriptors.values() for language in descriptor.languages})
        return {
            "adapters": [
                {
                    "name": descriptor.name,
                    "version": descriptor.version,
                    "digest": descriptor.content_digest,
                    "declaredLevel": descriptor.declared_level.value,
                    "attestedLevel": self.attested_level(descriptor.name).value,
                    "languages": list(descriptor.languages),
                }
                for descriptor in sorted(self.descriptors.values(), key=lambda item: item.name)
            ],
            "effectiveLevels": {language: self.effective_level(language).value for language in languages},
            "provenLevels": {language: self.proven_level(language).value for language in languages},
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> AdapterCapabilitySnapshot:
        if payload is None:
            return cls()
        value = require_mapping(payload, "adapter_capabilities")
        reject_unknown_fields(value, {"descriptors", "attestations"}, "adapter_capabilities")
        descriptors = dict(BUILTIN_ADAPTERS)
        for item in require_mapping_sequence(value.get("descriptors", ()), "adapter_capabilities.descriptors"):
            descriptor = AdapterDescriptor.from_payload(item)
            descriptors[descriptor.name] = descriptor
        attestations: dict[str, AdapterAttestation] = {}
        for item in require_mapping_sequence(value.get("attestations", ()), "adapter_capabilities.attestations"):
            attestation = AdapterAttestation.from_payload(item)
            attestations[attestation.adapter_name] = attestation
        return cls(descriptors=MappingProxyType(descriptors), attestations=MappingProxyType(attestations))


EXTENSION_LANGUAGE: Mapping[str, str] = MappingProxyType(
    {
        "py": "python", "pyi": "python",
        "java": "java", "kt": "kotlin", "kts": "kotlin", "groovy": "groovy", "scala": "scala", "sbt": "scala",
        "ts": "typescript", "tsx": "typescript", "mts": "typescript", "cts": "typescript",
        "js": "javascript", "jsx": "javascript", "mjs": "javascript", "cjs": "javascript",
        "vue": "vue", "svelte": "javascript",
        "cs": "csharp", "vb": "vbnet", "fs": "fsharp", "fsx": "fsharp",
        "go": "go", "rs": "rust",
        "c": "c", "h": "c", "cc": "cpp", "cpp": "cpp", "cxx": "cpp", "hpp": "cpp", "hh": "cpp", "hxx": "cpp",
        "m": "objective-c", "mm": "objective-c",
        "swift": "swift", "dart": "dart",
        "php": "php", "rb": "ruby", "rake": "ruby",
        "sql": "sql", "ddl": "sql", "psql": "postgresql",
        "yaml": "yaml", "yml": "yaml", "json": "json", "json5": "json", "xml": "xml",
        "tf": "terraform", "tfvars": "terraform", "hcl": "hcl",
        "sh": "bash", "bash": "bash", "zsh": "bash",
        "toml": "toml", "ini": "properties", "properties": "properties", "cfg": "properties",
        "md": "markdown", "markdown": "markdown", "rst": "text", "txt": "text",
        "proto": "protobuf", "graphql": "graphql", "gql": "graphql",
        "gradle": "groovy",
    }
)

FILENAME_LANGUAGE: Mapping[str, str] = MappingProxyType(
    {
        "dockerfile": "dockerfile",
        "makefile": "make",
        "cmakelists.txt": "cmake",
        "go.mod": "go-mod",
        "cargo.toml": "toml",
        "package.json": "json",
        "pom.xml": "xml",
        "build.gradle": "groovy",
        "build.gradle.kts": "kotlin",
        "pyproject.toml": "toml",
        "requirements.txt": "text",
    }
)


def language_of(path: str) -> str:
    """Best-effort language label for a path; ``unknown`` is a real answer."""

    basename = path.rsplit("/", 1)[-1].lower()
    if basename in FILENAME_LANGUAGE:
        return FILENAME_LANGUAGE[basename]
    if basename.startswith("dockerfile"):
        return "dockerfile"
    if "." not in basename:
        return "unknown"
    extension = basename.rsplit(".", 1)[-1]
    return EXTENSION_LANGUAGE.get(extension, "unknown")


__all__ = [
    "ADAPTER_OPERATIONS",
    "BUILTIN_ADAPTERS",
    "CAPABILITY_NAMES",
    "CAPABILITY_STATES",
    "EXTENSION_LANGUAGE",
    "LANGUAGE_TO_ADAPTER",
    "NATIVE_ENGINE_LEVELS",
    "AdapterAttestation",
    "AdapterCapabilitySnapshot",
    "AdapterDescriptor",
    "AdapterSecurity",
    "ResourceProfile",
    "Toolchain",
    "language_of",
]

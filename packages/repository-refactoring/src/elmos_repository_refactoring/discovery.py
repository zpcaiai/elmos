"""Skill 01 — repository discovery.

Builds the inventory every later stage trusts: what languages are present, what
builds them, which files are generated or vendored, who owns what, and which
areas are sensitive enough to change the risk class of any step that touches
them.

The rule that shapes the whole module: **unreadable is not empty**.  A file the
snapshot could not decode is reported in ``unscanned`` and lowers the coverage
confidence; it is never counted as "zero symbols, nothing to worry about".
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .adapters import language_of
from .contracts import (
    ContractError,
    match_path_glob,
    sha256_payload,
)
from .workspace import WorkspaceSnapshot, classify_path

#: Build-system marker files.  Order matters only for reporting; detection is
#: exhaustive, and a repository can legitimately match several.
BUILD_MARKERS: Mapping[str, tuple[str, ...]] = {
    "maven": ("pom.xml", "**/pom.xml"),
    "gradle": ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "**/build.gradle*"),
    "bazel": ("WORKSPACE", "WORKSPACE.bazel", "MODULE.bazel", "**/BUILD", "**/BUILD.bazel"),
    "cmake": ("CMakeLists.txt", "**/CMakeLists.txt"),
    "make": ("Makefile", "**/Makefile"),
    "msbuild": ("**/*.sln", "**/*.csproj", "**/*.vbproj", "**/*.fsproj"),
    "cargo": ("Cargo.toml", "**/Cargo.toml"),
    "go-modules": ("go.mod", "**/go.mod"),
    "npm": ("package-lock.json",),
    "pnpm": ("pnpm-lock.yaml", "pnpm-workspace.yaml"),
    "yarn": ("yarn.lock",),
    "bun": ("bun.lockb",),
    "node": ("package.json", "**/package.json"),
    "poetry": ("poetry.lock",),
    "uv": ("uv.lock",),
    "pdm": ("pdm.lock",),
    "pip": ("requirements.txt", "requirements*.txt", "setup.py", "setup.cfg"),
    "python-project": ("pyproject.toml", "**/pyproject.toml"),
    "composer": ("composer.json", "composer.lock"),
    "bundler": ("Gemfile", "Gemfile.lock"),
    "swiftpm": ("Package.swift",),
    "xcode": ("**/*.xcodeproj/**", "**/*.xcworkspace/**"),
    "flutter": ("pubspec.yaml", "**/pubspec.yaml"),
    "sbt": ("build.sbt",),
    "terraform": ("**/*.tf",),
    "helm": ("**/Chart.yaml",),
    "docker": ("Dockerfile", "**/Dockerfile", "**/Dockerfile.*"),
}

MONOREPO_MARKERS: Mapping[str, tuple[str, ...]] = {
    "nx": ("nx.json",),
    "turborepo": ("turbo.json",),
    "lerna": ("lerna.json",),
    "rush": ("rush.json",),
    "pnpm-workspaces": ("pnpm-workspace.yaml",),
    "cargo-workspace": ("Cargo.toml",),
    "bazel": ("WORKSPACE", "MODULE.bazel"),
    "gradle-composite": ("settings.gradle", "settings.gradle.kts"),
}

IDL_MARKERS: Mapping[str, tuple[str, ...]] = {
    "openapi": ("**/openapi.yaml", "**/openapi.yml", "**/openapi.json", "**/swagger.yaml", "**/swagger.json"),
    "protobuf": ("**/*.proto",),
    "graphql": ("**/*.graphql", "**/*.gql"),
    "avro": ("**/*.avsc",),
    "thrift": ("**/*.thrift",),
    "jsonschema": ("**/*.schema.json",),
    "asyncapi": ("**/asyncapi.yaml", "**/asyncapi.yml"),
    "wsdl": ("**/*.wsdl",),
}

#: Sensitive-area detection.  Each entry pairs *path* evidence with *content*
#: evidence; a hit on either is reported, and both together raise confidence.
#: These areas force a higher risk class regardless of how small the diff is.
SENSITIVE_AREAS: Mapping[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "authentication": (
        ("**/auth/**", "**/authn/**", "**/login/**", "**/session/**", "**/oauth/**", "**/*auth*.*"),
        (r"\bauthenticate\b", r"\bjwt\b", r"\boauth2?\b", r"\bpassword\b", r"\bbcrypt\b", r"\bsession_token\b"),
    ),
    "authorization": (
        ("**/authz/**", "**/permission*/**", "**/rbac/**", "**/policy/**", "**/acl/**"),
        (r"\brequire_role\b", r"\bhas_permission\b", r"\brbac\b", r"\bis_admin\b", r"\bROW LEVEL SECURITY\b"),
    ),
    "payment": (
        ("**/payment*/**", "**/billing/**", "**/checkout/**", "**/invoice*/**", "**/wallet/**", "**/ledger/**"),
        (r"\bstripe\b", r"\bpaypal\b", r"\bcharge\b", r"\brefund\b", r"\bcurrency\b", r"\bamount_cents\b"),
    ),
    "cryptography": (
        ("**/crypto/**", "**/cipher*/**", "**/keystore/**", "**/kms/**"),
        (r"\bAES\b", r"\bRSA\b", r"\bencrypt\b", r"\bdecrypt\b", r"\bhmac\b", r"\bprivate_key\b"),
    ),
    "secrets": (
        ("**/secret*/**", "**/.env", "**/.env.*", "**/*.pem", "**/*.p12", "**/vault/**"),
        (r"\bAPI_KEY\b", r"\bSECRET_KEY\b", r"\bACCESS_TOKEN\b", r"\bBEGIN (?:RSA )?PRIVATE KEY\b"),
    ),
    "personal-data": (
        ("**/pii/**", "**/gdpr/**", "**/privacy/**"),
        (r"\bssn\b", r"\bnational_id\b", r"\bdate_of_birth\b", r"\bemail_address\b", r"\bphone_number\b"),
    ),
    "data-deletion": (
        ("**/purge/**", "**/retention/**"),
        (r"\bDROP\s+TABLE\b", r"\bTRUNCATE\b", r"\bDELETE\s+FROM\b", r"\bhard_delete\b"),
    ),
    "concurrency": (
        ("**/concurren*/**", "**/scheduler/**", "**/worker*/**"),
        (r"\bthreading\.\b", r"\basyncio\.\b", r"\bgoroutine\b", r"\bsynchronized\b", r"\bmutex\b", r"\bLock\(\)"),
    ),
    "deployment": (
        ("**/deploy/**", "**/k8s/**", "**/kubernetes/**", "**/helm/**", "**/.github/workflows/**", "**/terraform/**"),
        (r"\bkind:\s*Deployment\b", r"\bimage:\s", r"\bresource\s+\"aws_"),
    ),
}

_GENERATED_HEADER = re.compile(
    r"^.{0,40}(?:@generated|DO NOT EDIT|Code generated by|autogenerated|auto-generated|Generated by)",
    re.IGNORECASE,
)

#: How many bytes of a file are scanned for generated-headers and sensitive
#: content markers.  Bounded so a 4 MiB file cannot dominate discovery cost.
_CONTENT_SCAN_BYTES = 8192

_LARGE_FILE_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class LanguageStat:
    language: str
    files: int
    bytes: int
    generated_files: int
    test_files: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "files": self.files,
            "bytes": self.bytes,
            "generatedFiles": self.generated_files,
            "testFiles": self.test_files,
        }


@dataclass(frozen=True, slots=True)
class OwnershipRule:
    """One CODEOWNERS line, kept in file order because last match wins."""

    pattern: str
    owners: tuple[str, ...]
    source_line: int

    def matches(self, path: str) -> bool:
        pattern = self.pattern
        candidates: tuple[str, ...]
        if pattern.startswith("/"):
            pattern = pattern[1:]
            candidates = (pattern, f"{pattern.rstrip('/')}/**")
        elif pattern.endswith("/"):
            candidates = (f"**/{pattern}**", f"{pattern}**")
        elif "/" in pattern:
            candidates = (pattern, f"{pattern.rstrip('/')}/**")
        else:
            candidates = (f"**/{pattern}", pattern, f"**/{pattern}/**")
        return any(match_path_glob(path, candidate) for candidate in candidates)


@dataclass(frozen=True, slots=True)
class SensitiveHit:
    area: str
    path: str
    evidence: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {"area": self.area, "path": self.path, "evidence": list(self.evidence)}


@dataclass(frozen=True, slots=True)
class RepositoryInventory:
    repository_id: str
    revision: str
    tree_digest: str
    file_count: int
    total_bytes: int
    languages: tuple[LanguageStat, ...]
    build_systems: tuple[str, ...]
    monorepo_tools: tuple[str, ...]
    idl_files: Mapping[str, tuple[str, ...]]
    generated_paths: tuple[str, ...]
    vendored_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    migration_paths: tuple[str, ...]
    configuration_paths: tuple[str, ...]
    large_files: tuple[str, ...]
    binary_files: int
    unknown_language_files: int
    unscanned: tuple[Mapping[str, str], ...]
    ownership: Mapping[str, tuple[str, ...]]
    sensitive_areas: tuple[SensitiveHit, ...]
    filters_applied: tuple[str, ...] = ()
    truncated: bool = False

    @property
    def coverage(self) -> Decimal:
        """Share of files that were fully scanned.

        Files that could not be read at all are excluded from the numerator,
        which is what keeps a repository full of unreadable blobs from looking
        like a clean 100 % scan.
        """

        if self.file_count == 0:
            return Decimal("0")
        scanned = self.file_count - len(self.unscanned)
        return (Decimal(scanned) / Decimal(self.file_count)).quantize(Decimal("0.0001"))

    @property
    def sensitive_area_names(self) -> tuple[str, ...]:
        return tuple(sorted({hit.area for hit in self.sensitive_areas}))

    def owners_of(self, path: str) -> tuple[str, ...]:
        return self.ownership.get(path, ())

    def to_payload(self) -> dict[str, Any]:
        return {
            "repositoryId": self.repository_id,
            "revision": self.revision,
            "treeDigest": self.tree_digest,
            "fileCount": self.file_count,
            "totalBytes": self.total_bytes,
            "languages": [item.to_payload() for item in self.languages],
            "buildSystems": list(self.build_systems),
            "monorepoTools": list(self.monorepo_tools),
            "idlFiles": {key: list(value) for key, value in sorted(self.idl_files.items())},
            "generatedPaths": list(self.generated_paths),
            "vendoredPaths": list(self.vendored_paths),
            "testPaths": list(self.test_paths),
            "migrationPaths": list(self.migration_paths),
            "configurationPaths": list(self.configuration_paths),
            "largeFiles": list(self.large_files),
            "binaryFiles": self.binary_files,
            "unknownLanguageFiles": self.unknown_language_files,
            "unscanned": [dict(item) for item in self.unscanned],
            "ownership": {key: list(value) for key, value in sorted(self.ownership.items())},
            "sensitiveAreas": [hit.to_payload() for hit in self.sensitive_areas],
            "coverage": str(self.coverage),
            "filtersApplied": list(self.filters_applied),
            "truncated": self.truncated,
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


def parse_codeowners(text: str) -> tuple[OwnershipRule, ...]:
    """Parse a CODEOWNERS file.

    GitHub/GitLab semantics: comments start with ``#``, blank lines are
    ignored, the first token is a pattern and the rest are owners, and the
    *last* matching rule wins — so rule order is preserved rather than sorted.
    """

    rules: list[OwnershipRule] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pattern, owners = parts[0], tuple(parts[1:])
        if not all(owner.startswith(("@", "$")) or "@" in owner for owner in owners):
            # A line whose "owners" are not identities is malformed; recording
            # it as ownership would invent an approver that does not exist.
            continue
        rules.append(OwnershipRule(pattern=pattern, owners=owners, source_line=number))
    return tuple(rules)


def _codeowners_paths(snapshot: WorkspaceSnapshot) -> tuple[str, ...]:
    candidates = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS")
    return tuple(path for path in candidates if path in snapshot)


def _scan_sensitive(path: str, text: str | None) -> tuple[SensitiveHit, ...]:
    hits: list[SensitiveHit] = []
    sample = "" if text is None else text[:_CONTENT_SCAN_BYTES]
    for area, (path_patterns, content_patterns) in SENSITIVE_AREAS.items():
        evidence: list[str] = []
        for pattern in path_patterns:
            if match_path_glob(path, pattern):
                evidence.append(f"path:{pattern}")
                break
        if sample:
            for pattern in content_patterns:
                if re.search(pattern, sample, re.IGNORECASE):
                    evidence.append(f"content:{pattern}")
                    break
        if evidence:
            hits.append(SensitiveHit(area=area, path=path, evidence=tuple(evidence)))
    return tuple(hits)


def discover(
    snapshot: WorkspaceSnapshot,
    *,
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
    max_sensitive_hits: int = 2000,
) -> RepositoryInventory:
    """Build a :class:`RepositoryInventory` from a workspace snapshot.

    ``include``/``exclude`` narrow the *analysis* view without changing the
    snapshot; both are recorded in the inventory so a later reader can tell an
    empty result from a filtered one.
    """

    considered = [
        record
        for record in snapshot
        if (not include or any(match_path_glob(record.path, pattern) for pattern in include))
        and not any(match_path_glob(record.path, pattern) for pattern in exclude)
    ]

    language_files: Counter[str] = Counter()
    language_bytes: Counter[str] = Counter()
    language_generated: Counter[str] = Counter()
    language_tests: Counter[str] = Counter()
    generated: list[str] = []
    vendored: list[str] = []
    tests: list[str] = []
    migrations: list[str] = []
    configuration: list[str] = []
    large: list[str] = []
    unscanned: list[dict[str, str]] = []
    sensitive: list[SensitiveHit] = []
    binary_files = 0
    unknown_files = 0

    for record in considered:
        language = language_of(record.path)
        labels = set(classify_path(record.path))
        sample = record.text[:_CONTENT_SCAN_BYTES] if record.text is not None else None
        if sample is not None and _GENERATED_HEADER.search(sample.lstrip()[:200]):
            labels.add("generated")

        language_files[language] += 1
        language_bytes[language] += record.size_bytes
        if language == "unknown":
            unknown_files += 1
        if record.binary:
            binary_files += 1
        if record.unreadable_reason is not None:
            unscanned.append({"path": record.path, "reason": record.unreadable_reason})
        if record.size_bytes >= _LARGE_FILE_BYTES:
            large.append(record.path)
        if "generated" in labels:
            generated.append(record.path)
            language_generated[language] += 1
        if "vendored" in labels:
            vendored.append(record.path)
        if "test" in labels:
            tests.append(record.path)
            language_tests[language] += 1
        if "data-migration" in labels:
            migrations.append(record.path)
        if "configuration" in labels:
            configuration.append(record.path)
        if len(sensitive) < max_sensitive_hits:
            sensitive.extend(_scan_sensitive(record.path, sample))

    paths = tuple(record.path for record in considered)
    build_systems = tuple(
        sorted(
            name
            for name, patterns in BUILD_MARKERS.items()
            if any(any(match_path_glob(path, pattern) for pattern in patterns) for path in paths)
        )
    )
    monorepo_tools = tuple(
        sorted(
            name
            for name, patterns in MONOREPO_MARKERS.items()
            if any(any(match_path_glob(path, pattern) for pattern in patterns) for path in paths)
        )
    )
    idl_files = {
        name: tuple(sorted(path for path in paths if any(match_path_glob(path, pattern) for pattern in patterns)))
        for name, patterns in IDL_MARKERS.items()
    }
    idl_files = {name: value for name, value in idl_files.items() if value}

    ownership: dict[str, tuple[str, ...]] = {}
    for owners_path in _codeowners_paths(snapshot):
        record = snapshot.require(owners_path)
        if record.text is None:
            unscanned.append({"path": owners_path, "reason": "codeowners-unreadable"})
            continue
        rules = parse_codeowners(record.text)
        for path in paths:
            matched: tuple[str, ...] = ()
            for rule in rules:
                if rule.matches(path):
                    matched = rule.owners  # last match wins
            if matched:
                ownership[path] = matched

    languages = tuple(
        LanguageStat(
            language=language,
            files=count,
            bytes=language_bytes[language],
            generated_files=language_generated[language],
            test_files=language_tests[language],
        )
        for language, count in sorted(language_files.items(), key=lambda item: (-item[1], item[0]))
    )

    return RepositoryInventory(
        repository_id=snapshot.repository_id,
        revision=snapshot.revision,
        tree_digest=snapshot.tree_digest,
        file_count=len(considered),
        total_bytes=sum(record.size_bytes for record in considered),
        languages=languages,
        build_systems=build_systems,
        monorepo_tools=monorepo_tools,
        idl_files=idl_files,
        generated_paths=tuple(sorted(generated)),
        vendored_paths=tuple(sorted(vendored)),
        test_paths=tuple(sorted(tests)),
        migration_paths=tuple(sorted(migrations)),
        configuration_paths=tuple(sorted(configuration)),
        large_files=tuple(sorted(large)),
        binary_files=binary_files,
        unknown_language_files=unknown_files,
        unscanned=tuple(sorted(unscanned, key=lambda item: item["path"])),
        ownership=ownership,
        sensitive_areas=tuple(sorted(sensitive, key=lambda hit: (hit.area, hit.path))),
        filters_applied=tuple(sorted({*include, *exclude, *snapshot.filters_applied})),
        truncated=snapshot.truncated or len(sensitive) >= max_sensitive_hits,
    )


@dataclass(frozen=True, slots=True)
class DiscoveryEvidence:
    """What was scanned, what was skipped, and how confident the result is."""

    inventory_digest: str
    coverage: Decimal
    unscanned_count: int
    filters_applied: tuple[str, ...]
    truncated: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return {
            "inventoryDigest": self.inventory_digest,
            "coverage": str(self.coverage),
            "unscannedCount": self.unscanned_count,
            "filtersApplied": list(self.filters_applied),
            "truncated": self.truncated,
            "warnings": list(self.warnings),
        }


def discovery_evidence(inventory: RepositoryInventory) -> DiscoveryEvidence:
    warnings: list[str] = []
    if inventory.truncated:
        warnings.append("snapshot-or-scan-truncated: the inventory is incomplete by construction")
    if inventory.unscanned:
        warnings.append(f"{len(inventory.unscanned)} file(s) could not be read and are not counted as empty")
    if not inventory.build_systems:
        warnings.append("no build system detected: build-graph and compile gates cannot be trusted")
    if inventory.unknown_language_files:
        warnings.append(f"{inventory.unknown_language_files} file(s) have no recognised language")
    if inventory.coverage < Decimal("0.99"):
        warnings.append("scan coverage below 99%: raise unknown-risk weight for any plan built on this inventory")
    return DiscoveryEvidence(
        inventory_digest=inventory.digest,
        coverage=inventory.coverage,
        unscanned_count=len(inventory.unscanned),
        filters_applied=inventory.filters_applied,
        truncated=inventory.truncated,
        warnings=tuple(warnings),
    )


def language_inventory_payload(inventory: RepositoryInventory) -> dict[str, Any]:
    total = sum(item.bytes for item in inventory.languages) or 1
    return {
        "primary": inventory.languages[0].language if inventory.languages else "unknown",
        "languages": [
            {
                **item.to_payload(),
                "byteShare": str((Decimal(item.bytes) / Decimal(total)).quantize(Decimal("0.0001"))),
            }
            for item in inventory.languages
        ],
    }


def sensitive_area_map(inventory: RepositoryInventory) -> dict[str, Any]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for hit in inventory.sensitive_areas:
        grouped[hit.area].append(hit.path)
    return {
        "areas": [
            {
                "area": area,
                "pathCount": len(paths),
                "paths": sorted(paths)[:200],
                "truncated": len(paths) > 200,
                "riskFloor": "R4" if area in {"payment", "cryptography", "secrets", "data-deletion"} else "R3",
            }
            for area, paths in sorted(grouped.items())
        ],
        "ownerCoverage": str(
            (Decimal(len(inventory.ownership)) / Decimal(max(inventory.file_count, 1))).quantize(Decimal("0.0001"))
        ),
    }


def require_inventory(value: Any) -> RepositoryInventory:
    if not isinstance(value, RepositoryInventory):
        raise ContractError("invalid_inventory", "a RepositoryInventory is required")
    return value


__all__ = [
    "BUILD_MARKERS",
    "IDL_MARKERS",
    "MONOREPO_MARKERS",
    "SENSITIVE_AREAS",
    "DiscoveryEvidence",
    "LanguageStat",
    "OwnershipRule",
    "RepositoryInventory",
    "SensitiveHit",
    "discover",
    "discovery_evidence",
    "language_inventory_payload",
    "parse_codeowners",
    "sensitive_area_map",
]

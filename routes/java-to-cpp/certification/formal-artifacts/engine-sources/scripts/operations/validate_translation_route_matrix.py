#!/usr/bin/env python3
"""Fail closed when the cross-language business line drifts across its owners.

The directed-route business line is described in four places that must agree:

* ``routes/inventory.json``       -- the repository route contract
* ``routes/<route_key>/``        -- the per-route packs and support matrices
* ``engines/polyglot-route-engine`` -- the only engine that can execute a route
* ``apps/web-console``           -- the console that renders route readiness

The generation business line already has
``validate_generation_support_matrix.py``. This is its cross-language peer: it
exists so a route can never advertise a local pass, an independent
verification, or a certification that the packs and the engine do not carry.
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "routes" / "inventory.json"
ENGINE_SOURCE = (
    ROOT / "engines" / "polyglot-route-engine" / "src" / "elmos_polyglot_route"
)
ENGINE_MODELS = ENGINE_SOURCE / "models.py"
BUSINESS_LINES = ROOT / "apps" / "web-console" / "app" / "lib" / "businessLines.ts"
CONTRACTS = ROOT / "apps" / "web-console" / "app" / "lib" / "contracts.ts"
TRANSLATION_READER = (
    ROOT / "apps" / "web-console" / "app" / "lib" / "server" / "translationRoutes.ts"
)
TRANSLATION_RUNNER = (
    ROOT / "apps" / "web-console" / "app" / "lib" / "server" / "translationRunner.ts"
)
TRANSLATION_STUDIO = (
    ROOT / "apps" / "web-console" / "app" / "translation" / "TranslationStudio.tsx"
)
sys.path.insert(0, str(ROOT / "scripts" / "batch29"))

from route_sets import (  # noqa: E402
    ALL_DECLARED_ROUTE_KEYS,
    COMPLETE_ROUTE_KEYS,
    COMPLETION_ROUTE_KEYS,
    CORE_LANGUAGES,
    CORE_ROUTE_KEYS,
    DEPRECATED_ROUTE_KEYS,
    DEPRECATED_ROUTE_LANGUAGES,
    ELEVEN_LANGUAGE_COMPLETE_ROUTE_KEYS,
    ELEVEN_LANGUAGE_MATRIX_LANGUAGES,
    EVIDENCED_ROUTE_KEYS,
    MODULE_EQUIVALENCE_ROUTE_KEYS,
    NINE_LANGUAGE_COMPLETE_ROUTE_KEYS,
    NINE_LANGUAGE_MATRIX_LANGUAGES,
    NODEJS_EXACT_ROUTE_KEYS,
    PHP_EXACT_ROUTE_KEYS,
    ROUTE_PROVENANCE_PARTITIONS,
    SPECIALIZED_ROUTE_KEYS,
    SUPPORTED_ROUTE_LANGUAGES,
    TEN_LANGUAGE_COMPLETE_ROUTE_KEYS,
    TEN_LANGUAGE_MATRIX_LANGUAGES,
    V3_EXACT_ROUTE_KEYS,
    V3_LANGUAGES,
    provenance_route_set,
)
from route_runtime_metadata import (  # noqa: E402
    ENGINE_PATHS,
    SHORT_VERSIONS,
    V3_RESEARCH_ROUTE_VERSION,
    VERSIONS,
    route_execution_authorities_document,
    support_matrix_markdown_bytes,
    v3_research_certification_document,
    v3_research_evidence_document,
    v3_research_support_document,
)

LOCAL_STATUSES = {"PASSED_LOCAL", "NOT_RUN", "FAILED"}
VERIFICATION_STATUSES = {"PASSED", "NOT_RUN", "FAILED"}
ROUTE_STATUSES = {"research", "experimental", "limited", "certified", "blocked"}
TARGET_EMITTER_RELATIVE_PATH = (
    "engines/polyglot-route-engine/src/elmos_polyglot_route/emitter.py"
)


class MatrixError(RuntimeError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise MatrixError(reason)


def read_stable_regular_file(root: Path, path: Path, reason: str) -> bytes:
    """Read a confined standalone file while rejecting links and replacement."""

    try:
        resolved_root = root.resolve(strict=True)
        root_metadata = root.lstat()
        relative = path.relative_to(root)
    except (OSError, ValueError) as error:
        raise MatrixError(reason) from error
    require(
        not root.is_symlink() and stat.S_ISDIR(root_metadata.st_mode),
        reason,
    )
    current = root
    try:
        for part in relative.parts[:-1]:
            current = current / part
            metadata = current.lstat()
            require(
                not current.is_symlink() and stat.S_ISDIR(metadata.st_mode),
                reason,
            )
        before = path.lstat()
        resolved = path.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as error:
        raise MatrixError(reason) from error
    require(
        not path.is_symlink()
        and stat.S_ISREG(before.st_mode)
        and before.st_nlink == 1,
        reason,
    )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            content = stream.read()
            after_descriptor = os.fstat(stream.fileno())
        after_path = path.lstat()
    except OSError as error:
        raise MatrixError(reason) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    def identity(metadata: os.stat_result) -> tuple[int, ...]:
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_size,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_nlink,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )

    require(
        identity(before) == identity(opened)
        and identity(opened) == identity(after_descriptor)
        and identity(after_descriptor) == identity(after_path)
        and after_path.st_nlink == 1
        and len(content) == after_path.st_size
        and bool(content),
        reason,
    )
    return content


def load_stable_json(root: Path, path: Path, reason: str) -> object:
    try:
        return json.loads(read_stable_regular_file(root, path, reason).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MatrixError(reason) from error


def require_safe_directory(root: Path, directory: Path, reason: str) -> None:
    try:
        resolved_root = root.resolve(strict=True)
        relative = directory.relative_to(root)
        root_metadata = root.lstat()
        require(
            not root.is_symlink() and stat.S_ISDIR(root_metadata.st_mode),
            reason,
        )
        current = root
        for part in relative.parts:
            current = current / part
            metadata = current.lstat()
            require(
                not current.is_symlink() and stat.S_ISDIR(metadata.st_mode),
                reason,
            )
        current.resolve(strict=True).relative_to(resolved_root)
    except (OSError, ValueError) as error:
        raise MatrixError(reason) from error


def check_v3_research_route_documents(
    route_key: str,
    manifest: dict[str, object],
    support: dict[str, object],
    certification: dict[str, object],
    evidence: dict[str, object],
) -> None:
    """Require the exact non-vacuous NOT_RUN contract for one V3 route."""

    require(
        manifest.get("version") == V3_RESEARCH_ROUTE_VERSION,
        f"V3_ROUTE_VERSION_DRIFT:{route_key}",
    )
    require(
        support == v3_research_support_document(route_key),
        f"V3_ROUTE_SUPPORT_DRIFT:{route_key}",
    )
    require(
        certification == v3_research_certification_document(route_key),
        f"V3_ROUTE_CERTIFICATION_OVERCLAIM:{route_key}",
    )
    require(
        evidence == v3_research_evidence_document(route_key),
        f"V3_ROUTE_RAW_EVIDENCE_OVERCLAIM:{route_key}",
    )


def require_safe_engine_path(relative: object, reason: str) -> str:
    """Require one non-symlinked repository path below ``engines/``."""

    require(isinstance(relative, str) and bool(relative), reason)
    assert isinstance(relative, str)
    candidate = Path(relative)
    require(
        not candidate.is_absolute()
        and "\\" not in relative
        and candidate.parts
        and candidate.parts[0] == "engines"
        and all(part not in {"", ".", ".."} for part in candidate.parts),
        reason,
    )
    current = ROOT
    try:
        for part in candidate.parts:
            current = current / part
            require(not current.is_symlink(), reason)
        resolved_root = ROOT.resolve(strict=True)
        resolved = current.resolve(strict=True)
    except OSError as error:
        raise MatrixError(reason) from error
    require(
        resolved.is_relative_to(resolved_root)
        and (resolved.is_file() or resolved.is_dir()),
        reason,
    )
    return relative


def require_version_metadata(
    versions: object,
    expected: object,
    reason: str,
) -> None:
    """Require exact ordered equality with the pure metadata authority."""

    require(
        isinstance(versions, list)
        and bool(versions)
        and all(isinstance(item, str) and bool(item) for item in versions)
        and isinstance(expected, (list, tuple))
        and bool(expected)
        and all(isinstance(item, str) and bool(item) for item in expected),
        reason,
    )
    assert isinstance(versions, list) and isinstance(expected, (list, tuple))
    require(versions == list(expected), reason)


def declared_engine_languages(name: str) -> tuple[str, ...]:
    """Read a declared language tuple without importing the engine.

    The engine targets a newer CPython than some verification hosts provide, so
    the tuple is parsed from source instead of imported.
    """
    text = ENGINE_MODELS.read_text(encoding="utf-8")
    escaped = re.escape(name)
    match = re.search(rf"^{escaped}\s*[:=][^=]*=\s*\(([^)]*)\)", text, re.MULTILINE)
    if match is None:
        match = re.search(rf"^{escaped}\s*=\s*\(([^)]*)\)", text, re.MULTILINE)
    require(match is not None, f"ENGINE_{name}_NOT_FOUND")
    assert match is not None
    return tuple(re.findall(r'"([a-z]+)"', match.group(1)))


def engine_languages() -> tuple[str, ...]:
    return declared_engine_languages("SUPPORTED_LANGUAGES")


def routed_languages() -> tuple[str, ...]:
    text = ENGINE_MODELS.read_text(encoding="utf-8")
    require(
        re.search(
            r"^COMPLETE_MATRIX_LANGUAGES[^=]*=\s*SUPPORTED_LANGUAGES\s*$",
            text,
            re.MULTILINE,
        )
        is not None,
        "ENGINE_COMPLETE_MATRIX_LANGUAGE_ALIAS_DRIFT",
    )
    require(
        re.search(
            r"^ROUTED_LANGUAGES[^=]*=\s*COMPLETE_MATRIX_LANGUAGES\s*$",
            text,
            re.MULTILINE,
        )
        is not None,
        "ENGINE_ROUTED_LANGUAGE_ALIAS_DRIFT",
    )
    return engine_languages()


def pending_analyzer_languages() -> tuple[str, ...]:
    return declared_engine_languages("PENDING_ANALYZER_LANGUAGES")


def pending_repository_languages() -> tuple[str, ...]:
    return declared_engine_languages("PENDING_REPOSITORY_LANGUAGES")


def deprecated_engine_languages() -> tuple[str, ...]:
    return declared_engine_languages("DEPRECATED_LANGUAGES")


def console_languages() -> dict[str, dict[str, str]]:
    text = BUSINESS_LINES.read_text(encoding="utf-8")
    block = re.search(
        r"export const translationLanguages: TranslationLanguage\[\] = \[(.*?)\n\];",
        text,
        re.DOTALL,
    )
    require(block is not None, "CONSOLE_LANGUAGE_BLOCK_NOT_FOUND")
    assert block is not None
    languages: dict[str, dict[str, str]] = {}
    pattern = re.compile(
        r'\{ id: "(?P<id>[a-z]+)", label: "(?P<label>[^"]+)", compiler: "(?P<compiler>[^"]+)", '
        r'runtime: "(?P<runtime>[^"]+)", enginePath: "(?P<engine_path>[^"]+)" \}'
    )
    for match in pattern.finditer(block.group(1)):
        languages[match.group("id")] = {
            "compiler": match.group("compiler"),
            "runtime": match.group("runtime"),
            "engine_path": match.group("engine_path"),
        }
    require(bool(languages), "CONSOLE_LANGUAGE_ENTRIES_NOT_PARSED")
    return languages


def console_exposed_languages() -> tuple[str, ...]:
    text = BUSINESS_LINES.read_text(encoding="utf-8")
    block = re.search(
        r"export const fallbackConsoleLanguageIds.*?= new Set<TranslationLanguageId>\(\[(.*?)\]\);",
        text,
        re.DOTALL,
    )
    require(block is not None, "CONSOLE_EXPOSED_LANGUAGE_BLOCK_NOT_FOUND")
    assert block is not None
    return tuple(re.findall(r'"([a-z]+)"', block.group(1)))


def console_contract_languages() -> tuple[str, ...]:
    text = CONTRACTS.read_text(encoding="utf-8")
    block = re.search(
        r"export type TranslationLanguageId\s*=\s*(.*?);",
        text,
        re.DOTALL,
    )
    require(block is not None, "CONSOLE_CONTRACT_LANGUAGE_TYPE_NOT_FOUND")
    assert block is not None
    return tuple(re.findall(r'\|\s*"([a-z]+)"', block.group(1)))


def console_runner_languages() -> tuple[str, ...]:
    text = TRANSLATION_RUNNER.read_text(encoding="utf-8")
    block = re.search(
        r"const languages = new Set<TranslationLanguageId>\(\[(.*?)\]\);",
        text,
        re.DOTALL,
    )
    require(block is not None, "CONSOLE_RUNNER_LANGUAGE_SET_NOT_FOUND")
    assert block is not None
    return tuple(re.findall(r'"([a-z]+)"', block.group(1)))


def require_exact_language_set(
    actual: tuple[str, ...], expected: tuple[str, ...], reason: str
) -> None:
    require(len(actual) == len(set(actual)), f"{reason}_DUPLICATED")
    require(set(actual) == set(expected), reason)


def load_inventory() -> dict[str, object]:
    inventory = load_stable_json(ROOT, INVENTORY, "ROUTE_INVENTORY_UNSAFE")
    require(isinstance(inventory, dict), "ROUTE_INVENTORY_INVALID")
    assert isinstance(inventory, dict)
    return inventory


def check_inventory_shape(inventory: dict[str, object]) -> list[dict[str, str]]:
    routes = inventory.get("routes")
    require(isinstance(routes, list) and routes, "ROUTE_LIST_INVALID")
    assert isinstance(routes, list)
    languages = inventory.get("languages")
    require(isinstance(languages, dict) and languages, "ROUTE_LANGUAGE_MAP_INVALID")
    assert isinstance(languages, dict)

    supported = set(engine_languages())
    declared_languages = set(languages)
    require(declared_languages == supported, "ROUTE_LANGUAGE_SET_DRIFT")
    expected = set(EVIDENCED_ROUTE_KEYS)
    deprecated_languages = tuple(DEPRECATED_ROUTE_LANGUAGES)
    repository_pending: tuple[str, ...] = ()

    require(
        tuple(inventory.get("deprecated_languages", ())) == deprecated_languages,
        "DEPRECATED_LANGUAGE_SET_DRIFT",
    )
    require(
        deprecated_engine_languages() == deprecated_languages,
        "ENGINE_DEPRECATED_LANGUAGE_SET_DRIFT",
    )
    require(
        not (declared_languages & set(deprecated_languages)),
        "DEPRECATED_LANGUAGE_REACTIVATED",
    )
    require(
        inventory.get("pending_analyzer_languages") == [],
        "PENDING_ANALYZER_LANGUAGE_SET_DRIFT",
    )
    require(
        pending_analyzer_languages() == (),
        "ENGINE_PENDING_ANALYZER_LANGUAGE_SET_DRIFT",
    )
    require(
        inventory.get("pending_repository_languages") == list(repository_pending),
        "PENDING_REPOSITORY_LANGUAGE_SET_DRIFT",
    )
    require(
        pending_repository_languages() == repository_pending,
        "ENGINE_PENDING_REPOSITORY_LANGUAGE_SET_DRIFT",
    )

    deprecated_details = inventory.get("deprecated_language_details")
    require(isinstance(deprecated_details, dict), "DEPRECATED_LANGUAGE_DETAILS_INVALID")
    assert isinstance(deprecated_details, dict)
    require(
        set(deprecated_details) == set(deprecated_languages),
        "DEPRECATED_LANGUAGE_DETAILS_DRIFT",
    )
    for language in deprecated_languages:
        detail = deprecated_details[language]
        require(
            isinstance(detail, dict), f"DEPRECATED_LANGUAGE_DETAIL_INVALID:{language}"
        )
        assert isinstance(detail, dict)
        require(
            detail.get("status") == "DEPRECATED",
            f"DEPRECATED_LANGUAGE_STATUS_DRIFT:{language}",
        )
        require(
            detail.get("retained_route_set") == "javascript-node26-completion-18",
            f"DEPRECATED_LANGUAGE_ROUTE_SET_DRIFT:{language}",
        )
        require(
            isinstance(detail.get("version"), str) and bool(detail.get("version")),
            f"DEPRECATED_LANGUAGE_VERSION_MISSING:{language}",
        )
        require(
            isinstance(detail.get("engine_path"), str)
            and bool(detail.get("engine_path")),
            f"DEPRECATED_LANGUAGE_ENGINE_PATH_MISSING:{language}",
        )

    policy = inventory.get("route_policy")
    require(
        policy
        == {
            "mode": "complete-directed-matrix",
            "cartesian_expansion": "EXPLICIT_THIRTEEN_LANGUAGE_MATRIX",
            "complete_route_set": "thirteen-language-complete-156",
            "legacy_route_set": "legacy-complete-30",
            "specialized_route_set": "cpp-objc-swift-java-exact-8",
            "completion_route_set": "nine-language-completion-34",
            "nodejs_route_set": "javascript-node26-completion-18",
            "php_route_set": "php-php85-completion-20",
            "v3_route_set": "kotlin-react-flutter-completion-66",
            "deprecated_route_set": "javascript-node26-completion-18",
            "preserved_nine_language_route_set": "nine-language-complete-72",
            "preserved_ten_language_route_set": "ten-language-complete-90",
            "preserved_eleven_language_route_set": "eleven-language-complete-110",
        },
        "ROUTE_POLICY_DRIFT",
    )

    execution_authorities = inventory.get("route_execution_authorities")
    require(
        isinstance(execution_authorities, dict),
        "ROUTE_EXECUTION_AUTHORITIES_INVALID",
    )
    require(
        execution_authorities == route_execution_authorities_document(),
        "ROUTE_EXECUTION_AUTHORITIES_DRIFT",
    )

    provenance = inventory.get("route_provenance_partition")
    require(isinstance(provenance, dict), "ROUTE_PROVENANCE_PARTITION_INVALID")
    assert isinstance(provenance, dict)
    require(
        provenance.get("policy") == "exact-disjoint-authority-partition",
        "ROUTE_PROVENANCE_POLICY_DRIFT",
    )
    require(
        provenance.get("route_count") == len(ALL_DECLARED_ROUTE_KEYS),
        "ROUTE_PROVENANCE_COUNT_DRIFT",
    )
    require(
        provenance.get("active_route_count") == len(COMPLETE_ROUTE_KEYS),
        "ROUTE_PROVENANCE_ACTIVE_COUNT_DRIFT",
    )
    require(
        provenance.get("deprecated_route_count") == len(DEPRECATED_ROUTE_KEYS),
        "ROUTE_PROVENANCE_DEPRECATED_COUNT_DRIFT",
    )
    expected_partitions = {
        name: list(route_keys)
        for name, route_keys in ROUTE_PROVENANCE_PARTITIONS.items()
    }
    require(
        provenance.get("sets") == expected_partitions,
        "ROUTE_PROVENANCE_SETS_DRIFT",
    )

    route_sets = inventory.get("route_sets")
    require(isinstance(route_sets, dict), "ROUTE_SETS_INVALID")
    assert isinstance(route_sets, dict)
    require(
        set(route_sets)
        == {
            "legacy-complete-30",
            "cpp-objc-swift-java-exact-8",
            "nine-language-completion-34",
            "nine-language-complete-72",
            "javascript-node26-completion-18",
            "ten-language-complete-90",
            "php-php85-completion-20",
            "eleven-language-complete-110",
            "kotlin-react-flutter-completion-66",
            "thirteen-language-complete-156",
        },
        "ROUTE_SET_KEYS_DRIFT",
    )
    core_set = route_sets.get("legacy-complete-30")
    specialized_set = route_sets.get("cpp-objc-swift-java-exact-8")
    completion_set = route_sets.get("nine-language-completion-34")
    nine_complete_set = route_sets.get("nine-language-complete-72")
    nodejs_set = route_sets.get("javascript-node26-completion-18")
    ten_complete_set = route_sets.get("ten-language-complete-90")
    php_set = route_sets.get("php-php85-completion-20")
    eleven_complete_set = route_sets.get("eleven-language-complete-110")
    v3_set = route_sets.get("kotlin-react-flutter-completion-66")
    complete_set = route_sets.get("thirteen-language-complete-156")
    require(isinstance(core_set, dict), "CORE_ROUTE_SET_INVALID")
    require(isinstance(specialized_set, dict), "SPECIALIZED_ROUTE_SET_INVALID")
    require(isinstance(completion_set, dict), "COMPLETION_ROUTE_SET_INVALID")
    require(isinstance(nine_complete_set, dict), "NINE_COMPLETE_ROUTE_SET_INVALID")
    require(isinstance(nodejs_set, dict), "NODEJS_ROUTE_SET_INVALID")
    require(isinstance(ten_complete_set, dict), "TEN_COMPLETE_ROUTE_SET_INVALID")
    require(isinstance(php_set, dict), "PHP_ROUTE_SET_INVALID")
    require(isinstance(eleven_complete_set, dict), "ELEVEN_COMPLETE_ROUTE_SET_INVALID")
    require(isinstance(v3_set, dict), "V3_ROUTE_SET_INVALID")
    require(isinstance(complete_set, dict), "COMPLETE_ROUTE_SET_INVALID")
    assert (
        isinstance(core_set, dict)
        and isinstance(specialized_set, dict)
        and isinstance(completion_set, dict)
        and isinstance(nine_complete_set, dict)
        and isinstance(nodejs_set, dict)
        and isinstance(ten_complete_set, dict)
        and isinstance(php_set, dict)
        and isinstance(eleven_complete_set, dict)
        and isinstance(v3_set, dict)
        and isinstance(complete_set, dict)
    )
    require(
        core_set.get("policy") == "complete-directed-permutation",
        "CORE_ROUTE_POLICY_DRIFT",
    )
    require(
        core_set.get("languages") == list(CORE_LANGUAGES),
        "CORE_ROUTE_LANGUAGE_ORDER_DRIFT",
    )
    require(core_set.get("route_count") == 30, "CORE_ROUTE_COUNT_DRIFT")
    require(
        core_set.get("route_keys") == list(CORE_ROUTE_KEYS), "CORE_ROUTE_KEYS_DRIFT"
    )
    legacy_authority = execution_authorities.get("legacy-complete-30")
    require(
        isinstance(legacy_authority, dict),
        "CORE_ROUTE_EXECUTION_AUTHORITY_INVALID",
    )
    require(
        core_set.get("execution_authority_sha256")
        == legacy_authority.get("authority_sha256"),
        "CORE_ROUTE_EXECUTION_AUTHORITY_DIGEST_DRIFT",
    )
    require(
        specialized_set.get("policy") == "exact-explicit-set",
        "SPECIALIZED_ROUTE_POLICY_DRIFT",
    )
    require(
        specialized_set.get("languages") == ["cpp", "objc", "swift", "java"],
        "SPECIALIZED_ROUTE_LANGUAGE_ORDER_DRIFT",
    )
    require(specialized_set.get("route_count") == 8, "SPECIALIZED_ROUTE_COUNT_DRIFT")
    require(
        specialized_set.get("route_keys") == list(SPECIALIZED_ROUTE_KEYS),
        "SPECIALIZED_ROUTE_KEYS_DRIFT",
    )
    require(
        specialized_set.get("module_profile") == "typed-pure-module-v1",
        "SPECIALIZED_MODULE_PROFILE_DRIFT",
    )
    nine_languages = list(NINE_LANGUAGE_MATRIX_LANGUAGES)
    active_languages = list(SUPPORTED_ROUTE_LANGUAGES)
    ten_languages = list(TEN_LANGUAGE_MATRIX_LANGUAGES)
    eleven_languages = list(ELEVEN_LANGUAGE_MATRIX_LANGUAGES)
    require(
        completion_set.get("policy") == "exact-matrix-completion-set",
        "COMPLETION_ROUTE_POLICY_DRIFT",
    )
    require(
        completion_set.get("languages") == nine_languages,
        "COMPLETION_ROUTE_LANGUAGE_ORDER_DRIFT",
    )
    require(completion_set.get("route_count") == 34, "COMPLETION_ROUTE_COUNT_DRIFT")
    require(
        completion_set.get("route_keys") == list(COMPLETION_ROUTE_KEYS),
        "COMPLETION_ROUTE_KEYS_DRIFT",
    )
    require(
        nine_complete_set.get("policy") == "complete-directed-permutation",
        "NINE_COMPLETE_ROUTE_POLICY_DRIFT",
    )
    require(
        nine_complete_set.get("languages") == nine_languages,
        "NINE_COMPLETE_ROUTE_LANGUAGE_ORDER_DRIFT",
    )
    require(
        nine_complete_set.get("route_count") == 72, "NINE_COMPLETE_ROUTE_COUNT_DRIFT"
    )
    require(
        nine_complete_set.get("route_keys") == list(NINE_LANGUAGE_COMPLETE_ROUTE_KEYS),
        "NINE_COMPLETE_ROUTE_KEYS_DRIFT",
    )
    require(
        nodejs_set.get("policy") == "exact-nodejs-matrix-completion-set",
        "NODEJS_ROUTE_POLICY_DRIFT",
    )
    require(
        nodejs_set.get("languages") == ten_languages,
        "NODEJS_ROUTE_LANGUAGE_ORDER_DRIFT",
    )
    require(nodejs_set.get("route_count") == 18, "NODEJS_ROUTE_COUNT_DRIFT")
    require(
        nodejs_set.get("route_keys") == list(NODEJS_EXACT_ROUTE_KEYS),
        "NODEJS_ROUTE_KEYS_DRIFT",
    )
    require(
        nodejs_set.get("runtime_profile") == "Node.js 26.0.0 / ES2022 / ESM",
        "NODEJS_RUNTIME_DRIFT",
    )
    require(
        nodejs_set.get("module_profile") == "typed-pure-module-v1",
        "NODEJS_MODULE_PROFILE_DRIFT",
    )
    require(
        nodejs_set.get("input_domain") == "nodejs-es2022-esm-safe-integer-finite-v1",
        "NODEJS_INPUT_DOMAIN_DRIFT",
    )
    require(
        ten_complete_set.get("policy") == "complete-directed-permutation",
        "TEN_COMPLETE_ROUTE_POLICY_DRIFT",
    )
    require(
        ten_complete_set.get("languages") == ten_languages,
        "TEN_COMPLETE_ROUTE_LANGUAGE_ORDER_DRIFT",
    )
    require(ten_complete_set.get("route_count") == 90, "TEN_COMPLETE_ROUTE_COUNT_DRIFT")
    require(
        ten_complete_set.get("route_keys") == list(TEN_LANGUAGE_COMPLETE_ROUTE_KEYS),
        "TEN_COMPLETE_ROUTE_KEYS_DRIFT",
    )
    require(
        php_set.get("policy") == "exact-matrix-completion-set", "PHP_ROUTE_POLICY_DRIFT"
    )
    require(
        php_set.get("languages") == eleven_languages, "PHP_ROUTE_LANGUAGE_ORDER_DRIFT"
    )
    require(php_set.get("route_count") == 20, "PHP_ROUTE_COUNT_DRIFT")
    require(
        php_set.get("route_keys") == list(PHP_EXACT_ROUTE_KEYS), "PHP_ROUTE_KEYS_DRIFT"
    )
    require(
        php_set.get("runtime_profile") == "PHP 8.5.9 (cli) (NTS) / strict_types=1",
        "PHP_RUNTIME_DRIFT",
    )
    require(
        eleven_complete_set.get("policy") == "complete-directed-permutation",
        "ELEVEN_COMPLETE_ROUTE_POLICY_DRIFT",
    )
    require(
        eleven_complete_set.get("languages") == eleven_languages,
        "ELEVEN_COMPLETE_ROUTE_LANGUAGE_ORDER_DRIFT",
    )
    require(
        eleven_complete_set.get("route_count") == 110,
        "ELEVEN_COMPLETE_ROUTE_COUNT_DRIFT",
    )
    require(
        eleven_complete_set.get("route_keys")
        == list(ELEVEN_LANGUAGE_COMPLETE_ROUTE_KEYS),
        "ELEVEN_COMPLETE_ROUTE_KEYS_DRIFT",
    )
    require(
        eleven_complete_set.get("deprecated_route_keys") == list(DEPRECATED_ROUTE_KEYS),
        "ELEVEN_COMPLETE_DEPRECATED_KEYS_DRIFT",
    )
    require(
        v3_set.get("policy") == "exact-matrix-completion-set", "V3_ROUTE_POLICY_DRIFT"
    )
    require(
        v3_set.get("languages") == active_languages, "V3_ROUTE_LANGUAGE_ORDER_DRIFT"
    )
    require(v3_set.get("route_count") == 66, "V3_ROUTE_COUNT_DRIFT")
    require(
        v3_set.get("route_keys") == list(V3_EXACT_ROUTE_KEYS), "V3_ROUTE_KEYS_DRIFT"
    )
    require(
        v3_set.get("analyzer_status") == "LOCAL_SINGLE_UNIT_READY",
        "V3_ANALYZER_STATUS_DRIFT",
    )
    require(v3_set.get("pending_analyzer_languages") == [], "V3_PENDING_ANALYZER_DRIFT")
    require(
        v3_set.get("repository_status") == "LOCAL_REPOSITORY_READY",
        "V3_REPOSITORY_STATUS_DRIFT",
    )
    require(
        v3_set.get("pending_repository_languages") == list(repository_pending),
        "V3_PENDING_REPOSITORY_DRIFT",
    )
    require(
        complete_set.get("policy") == "complete-directed-permutation",
        "COMPLETE_ROUTE_POLICY_DRIFT",
    )
    require(
        complete_set.get("languages") == active_languages,
        "COMPLETE_ROUTE_LANGUAGE_ORDER_DRIFT",
    )
    require(complete_set.get("route_count") == 156, "COMPLETE_ROUTE_COUNT_DRIFT")
    require(
        complete_set.get("route_keys") == list(COMPLETE_ROUTE_KEYS),
        "COMPLETE_ROUTE_KEYS_DRIFT",
    )

    require(inventory.get("route_count") == len(routes), "ROUTE_COUNT_DRIFT")
    require(inventory.get("route_count") == 156, "ROUTE_EXPLICIT_COUNT_DRIFT")
    require(
        isinstance(inventory.get("semantic_profile"), str), "SEMANTIC_PROFILE_MISSING"
    )

    for language in SUPPORTED_ROUTE_LANGUAGES:
        detail = languages.get(language)
        require(isinstance(detail, dict), f"LANGUAGE_DETAIL_INVALID:{language}")
        assert isinstance(detail, dict)
        require(
            detail.get("version") == SHORT_VERSIONS[language],
            f"LANGUAGE_SHORT_VERSION_DRIFT:{language}",
        )
        require(
            detail.get("exact_versions") == list(VERSIONS[language]),
            f"LANGUAGE_EXACT_VERSION_DRIFT:{language}",
        )
        require(
            detail.get("engine_path") == ENGINE_PATHS[language],
            f"LANGUAGE_ENGINE_PATH_DRIFT:{language}",
        )

    for language in V3_LANGUAGES:
        detail = languages.get(language)
        require(isinstance(detail, dict), f"V3_LANGUAGE_DETAIL_INVALID:{language}")
        assert isinstance(detail, dict)
        require(
            detail.get("analyzer_status") == "LOCAL_SINGLE_UNIT_READY",
            f"V3_ANALYZER_STATUS_DRIFT:{language}",
        )
        require(
            detail.get("repository_status") == "LOCAL_REPOSITORY_READY",
            f"V3_REPOSITORY_STATUS_DRIFT:{language}",
        )
        require(
            isinstance(detail.get("version"), str)
            and detail.get("version") not in {"", "PENDING_ANALYZER"},
            f"V3_VERSION_NOT_READY:{language}",
        )
        require(
            isinstance(detail.get("engine_path"), str)
            and bool(detail.get("engine_path")),
            f"V3_ENGINE_PATH_NOT_READY:{language}",
        )
    for field, allowed in (
        ("local_execution_evidence", LOCAL_STATUSES),
        ("independent_verification_evidence", VERIFICATION_STATUSES),
        ("external_certification_evidence", VERIFICATION_STATUSES),
    ):
        require(inventory.get(field) in allowed, f"{field.upper()}_INVALID")

    seen: set[str] = set()
    for entry in routes:
        require(isinstance(entry, dict), "ROUTE_ENTRY_INVALID")
        assert isinstance(entry, dict)
        key = entry.get("route_key")
        source = entry.get("source")
        target = entry.get("target")
        require(isinstance(key, str) and key not in seen, f"ROUTE_KEY_DUPLICATED:{key}")
        assert isinstance(key, str)
        seen.add(key)
        require(source != target, f"ROUTE_SELF_DIRECTED:{key}")
        require(key == f"{source}-to-{target}", f"ROUTE_KEY_DRIFT:{key}")
        require(entry.get("status") in ROUTE_STATUSES, f"ROUTE_STATUS_INVALID:{key}")
        require(
            entry.get("local_execution_status") in LOCAL_STATUSES,
            f"ROUTE_LOCAL_STATUS_INVALID:{key}",
        )
        for field in (
            "independent_verification_status",
            "external_certification_status",
        ):
            require(
                entry.get(field) in VERIFICATION_STATUSES,
                f"{field.upper()}_INVALID:{key}",
            )
        require(
            source in languages and target in languages, f"ROUTE_LANGUAGE_UNKNOWN:{key}"
        )
        expected_route_set = provenance_route_set(key)
        require(
            entry.get("route_set") == expected_route_set,
            f"ROUTE_SET_BINDING_DRIFT:{key}",
        )
        module_status = entry.get("module_execution_status")
        if key in MODULE_EQUIVALENCE_ROUTE_KEYS:
            require(
                module_status in LOCAL_STATUSES, f"ROUTE_MODULE_STATUS_INVALID:{key}"
            )
            if entry.get("local_execution_status") == "PASSED_LOCAL":
                require(
                    module_status == "PASSED_LOCAL",
                    f"ROUTE_MODULE_EVIDENCE_INVERTED:{key}",
                )
        else:
            require(
                module_status == "NOT_APPLICABLE", f"ROUTE_MODULE_STATUS_DRIFT:{key}"
            )
        require(
            languages[source]["version"] == entry.get("source_version")
            and languages[target]["version"] == entry.get("target_version"),
            f"ROUTE_VERSION_DRIFT:{key}",
        )
        if key in V3_EXACT_ROUTE_KEYS:
            require(
                entry.get("status") == "research"
                and entry.get("local_execution_status") == "NOT_RUN"
                and entry.get("local_execution_reason")
                == "V3_ROUTE_CAMPAIGN_NOT_RUN"
                and entry.get("repository_execution_status") == "NOT_RUN"
                and entry.get("repository_profile") is None
                and entry.get("repository_evidence_ref") is None
                and entry.get("repository_evidence_sha256") is None
                and entry.get("repository_evidence_bytes") is None
                and entry.get("independent_verification_status") == "NOT_RUN"
                and entry.get("external_certification_status") == "NOT_RUN",
                f"V3_ROUTE_EVIDENCE_OVERCLAIM:{key}",
            )
        # Evidence may never run ahead of itself: independent verification
        # requires a local pass, and external certification requires an
        # independent pass.
        if entry.get("independent_verification_status") == "PASSED":
            require(
                entry.get("local_execution_status") == "PASSED_LOCAL",
                f"ROUTE_EVIDENCE_INVERTED:{key}",
            )
        if entry.get("external_certification_status") == "PASSED":
            require(
                entry.get("local_execution_status") == "PASSED_LOCAL",
                f"ROUTE_EVIDENCE_INVERTED:{key}",
            )
            require(
                entry.get("independent_verification_status") == "PASSED",
                f"ROUTE_CERTIFICATION_PRECEDES_VERIFICATION:{key}",
            )
        if entry.get("status") == "certified":
            require(
                entry.get("external_certification_status") == "PASSED",
                f"ROUTE_CERTIFICATION_UNSUPPORTED:{key}",
            )

    missing = sorted(expected - seen)
    extra = sorted(seen - expected)
    require(not missing, f"ROUTE_PERMUTATION_MISSING:{','.join(missing)}")
    require(not extra, f"ROUTE_PERMUTATION_EXTRA:{','.join(extra)}")

    for status, field in (
        ("research", "research_route_count"),
        ("experimental", "experimental_route_count"),
        ("limited", "limited_route_count"),
        ("certified", "certified_route_count"),
        ("blocked", "blocked_route_count"),
    ):
        declared = inventory.get(field)
        actual = sum(1 for entry in routes if entry.get("status") == status)
        require(declared == actual, f"{field.upper()}_DRIFT")

    return [entry for entry in routes if isinstance(entry, dict)]


def check_route_packs(
    routes: list[dict[str, str]],
    semantic_profile: str,
    languages: dict[str, object],
) -> None:
    routes_root = ROOT / "routes"
    directories = {path.name for path in routes_root.iterdir() if path.is_dir()}
    active = {str(entry["route_key"]) for entry in routes}
    require(active == set(COMPLETE_ROUTE_KEYS), "ACTIVE_ROUTE_PACK_SET_DRIFT")
    require(
        directories == set(ALL_DECLARED_ROUTE_KEYS),
        "ROUTE_PACK_DIRECTORY_DRIFT",
    )

    # Deprecated JavaScript directions are absent from the active inventory,
    # but their packs and provenance addresses are immutable evidence history.
    # Validate them read-only alongside the active packs without treating them
    # as executable routes or console choices.
    pack_entries: list[dict[str, str | bool]] = [dict(entry) for entry in routes]
    pack_entries.extend(
        {
            "route_key": key,
            "source": key.split("-to-", 1)[0],
            "target": key.split("-to-", 1)[1],
            "status": "limited",
            "deprecated": True,
        }
        for key in DEPRECATED_ROUTE_KEYS
    )

    for entry in pack_entries:
        key = str(entry["route_key"])
        pack_dir = ROOT / "routes" / key
        route_json = pack_dir / "route.json"
        support_json = pack_dir / "support-matrix.json"
        certification_root = pack_dir / "certification"
        support_view_path = certification_root / "support-matrix.md"
        certification_path = certification_root / "certification.json"
        evidence_path = certification_root / "evidence.json"
        require_safe_directory(
            routes_root, pack_dir, f"ROUTE_PACK_DIRECTORY_UNSAFE:{key}"
        )
        require_safe_directory(
            routes_root,
            certification_root,
            f"ROUTE_CERTIFICATION_DIRECTORY_UNSAFE:{key}",
        )
        pack = load_stable_json(
            routes_root, route_json, f"ROUTE_PACK_FILE_UNSAFE:{key}"
        )
        support_bytes = read_stable_regular_file(
            routes_root,
            support_json,
            f"ROUTE_SUPPORT_MATRIX_UNSAFE:{key}",
        )
        try:
            support = json.loads(support_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MatrixError(f"ROUTE_SUPPORT_MATRIX_UNSAFE:{key}") from error
        support_view = read_stable_regular_file(
            routes_root,
            support_view_path,
            f"ROUTE_SUPPORT_VIEW_UNSAFE:{key}",
        )
        certification_document = load_stable_json(
            routes_root,
            certification_path,
            f"ROUTE_CERTIFICATION_FILE_UNSAFE:{key}",
        )
        evidence_document = load_stable_json(
            routes_root,
            evidence_path,
            f"ROUTE_EVIDENCE_FILE_UNSAFE:{key}",
        )
        require(isinstance(pack, dict), f"ROUTE_PACK_DOCUMENT_INVALID:{key}")
        require(isinstance(support, dict), f"ROUTE_SUPPORT_DOCUMENT_INVALID:{key}")
        require(
            isinstance(certification_document, dict)
            and isinstance(evidence_document, dict),
            f"ROUTE_CERTIFICATION_DOCUMENT_INVALID:{key}",
        )
        assert isinstance(pack, dict) and isinstance(support, dict)
        assert isinstance(certification_document, dict)
        assert isinstance(evidence_document, dict)
        try:
            expected_support_view = support_matrix_markdown_bytes(
                key,
                support_bytes,
                support,
            )
        except ValueError as error:
            raise MatrixError(f"ROUTE_SUPPORT_DOCUMENT_INVALID:{key}") from error
        require(
            support_view == expected_support_view,
            f"ROUTE_SUPPORT_VIEW_DRIFT:{key}",
        )
        require(pack.get("route_key") == key, f"ROUTE_PACK_KEY_DRIFT:{key}")
        require(
            pack.get("status") == entry.get("status"), f"ROUTE_PACK_STATUS_DRIFT:{key}"
        )
        require(
            pack.get("source", {}).get("language") == entry.get("source")
            and pack.get("target", {}).get("language") == entry.get("target"),
            f"ROUTE_PACK_DIRECTION_DRIFT:{key}",
        )

        capabilities = support.get("capabilities")
        require(
            isinstance(capabilities, list) and capabilities,
            f"ROUTE_SUPPORT_EMPTY:{key}",
        )
        require(support.get("route_key") == key, f"ROUTE_SUPPORT_KEY_DRIFT:{key}")
        capability_ids = [
            item.get("id") for item in capabilities if isinstance(item, dict)
        ]
        require(
            len(capability_ids) == len(capabilities)
            and all(isinstance(item, str) and bool(item) for item in capability_ids)
            and len(set(capability_ids)) == len(capability_ids),
            f"ROUTE_SUPPORT_CAPABILITY_ID_DRIFT:{key}",
        )
        source_language = str(entry["source"])
        target_language = str(entry["target"])
        require_version_metadata(
            pack.get("source", {}).get("versions"),
            VERSIONS[source_language],
            f"ROUTE_SOURCE_VERSION_DRIFT:{key}",
        )
        require_version_metadata(
            pack.get("target", {}).get("versions"),
            VERSIONS[target_language],
            f"ROUTE_TARGET_VERSION_DRIFT:{key}",
        )
        profile_entry = next(
            (item for item in capabilities if item.get("id") == semantic_profile), None
        )
        if key in V3_EXACT_ROUTE_KEYS:
            # Analyzer readiness is deliberately narrower than route support.
            # These research packs retain their unpromoted capability matrix
            # until route execution evidence exists. Their empty semantic
            # profile is conservative, but their exact analyzer/emitter paths
            # and toolchain versions are still executable metadata and must not
            # remain scaffold placeholders.
            require(pack.get("status") == "research", f"V3_ROUTE_STATUS_DRIFT:{key}")
            source = pack.get("source")
            target = pack.get("target")
            require(
                isinstance(source, dict) and isinstance(target, dict),
                f"V3_ROUTE_ENDPOINT_INVALID:{key}",
            )
            assert isinstance(source, dict) and isinstance(target, dict)
            source_declared = languages.get(source_language)
            target_declared = languages.get(target_language)
            require(
                isinstance(source_declared, dict)
                and isinstance(target_declared, dict),
                f"V3_ROUTE_LANGUAGE_METADATA_MISSING:{key}",
            )
            assert isinstance(source_declared, dict) and isinstance(target_declared, dict)
            require(
                source.get("engine_path") == source_declared.get("engine_path"),
                f"V3_ROUTE_SOURCE_ENGINE_DRIFT:{key}",
            )
            require(
                target.get("engine_path") == TARGET_EMITTER_RELATIVE_PATH,
                f"V3_ROUTE_TARGET_ENGINE_DRIFT:{key}",
            )
            require_safe_engine_path(
                source.get("engine_path"),
                f"V3_ROUTE_SOURCE_ENGINE_UNSAFE:{key}",
            )
            require_safe_engine_path(
                target.get("engine_path"),
                f"V3_ROUTE_TARGET_ENGINE_UNSAFE:{key}",
            )
            require_version_metadata(
                source.get("versions"),
                source_declared.get("exact_versions"),
                f"V3_ROUTE_SOURCE_VERSION_DRIFT:{key}",
            )
            require_version_metadata(
                target.get("versions"),
                target_declared.get("exact_versions"),
                f"V3_ROUTE_TARGET_VERSION_DRIFT:{key}",
            )
            require(
                pack.get("profiles")
                == {"semantic_profile": "", "target_profile": ""}
                and pack.get("framework_profiles") == [],
                f"V3_ROUTE_PROFILE_OVERCLAIM:{key}",
            )
            require(profile_entry is None, f"V3_ROUTE_SUPPORT_OVERCLAIM:{key}")
            require(
                all(
                    isinstance(item, dict)
                    and item.get("status")
                    in {"experimental", "detected-only", "blocked"}
                    for item in capabilities
                ),
                f"V3_ROUTE_CAPABILITY_OVERCLAIM:{key}",
            )
            check_v3_research_route_documents(
                key, pack, support, certification_document, evidence_document
            )
            continue

        require(
            pack.get("profiles", {}).get("semantic_profile") == semantic_profile,
            f"ROUTE_PACK_PROFILE_DRIFT:{key}",
        )
        require(profile_entry is not None, f"ROUTE_SUPPORT_PROFILE_MISSING:{key}")
        assert profile_entry is not None
        nodejs_preserved = key in DEPRECATED_ROUTE_KEYS
        expected_capability_status = (
            "conditional"
            if key in MODULE_EQUIVALENCE_ROUTE_KEYS or nodejs_preserved
            else {
                "research": "detected-only",
                "experimental": "experimental",
                "limited": "supported",
                "certified": "certified",
                "blocked": "blocked",
            }[str(entry.get("status"))]
        )
        require(
            profile_entry.get("status") == expected_capability_status,
            f"ROUTE_SUPPORT_STATUS_DRIFT:{key}",
        )
        if key in SPECIALIZED_ROUTE_KEYS:
            require(
                pack.get("profiles", {}).get("input_domain")
                == "canonical-finite-no-error-input-domain",
                f"SPECIALIZED_INPUT_DOMAIN_DRIFT:{key}",
            )
            require(
                pack.get("profiles", {}).get("module_profile")
                == "typed-pure-module-v1",
                f"SPECIALIZED_MODULE_PROFILE_DRIFT:{key}",
            )
            require(
                pack.get("gates", {}).get("concrete_spans_required") is True,
                f"SPECIALIZED_SPAN_POLICY_DRIFT:{key}",
            )
            types = load_stable_json(
                routes_root,
                pack_dir / "mappings" / "types.json",
                f"SPECIALIZED_TYPES_FILE_UNSAFE:{key}",
            )
            require(isinstance(types, dict), f"SPECIALIZED_TYPES_INVALID:{key}")
            assert isinstance(types, dict)
            require(
                types.get("types") == ["integer", "number", "boolean"],
                f"SPECIALIZED_TYPE_SET_DRIFT:{key}",
            )
        if nodejs_preserved:
            gates = pack.get("gates", {})
            profiles = pack.get("profiles", {})
            nodejs_typescript = {entry.get("source"), entry.get("target")} == {
                "javascript",
                "typescript",
            }
            require(pack.get("status") == "limited", f"NODEJS_ROUTE_STATUS_DRIFT:{key}")
            require(
                profiles.get("input_domain")
                == "nodejs-es2022-esm-safe-integer-finite-v1",
                f"NODEJS_INPUT_DOMAIN_DRIFT:{key}",
            )
            require(
                profiles.get("module_profile") == "typed-pure-module-v1",
                f"NODEJS_MODULE_PROFILE_DRIFT:{key}",
            )
            for field in ("module_equivalence_required", "concrete_spans_required"):
                require(gates.get(field) is True, f"NODEJS_GATE_DRIFT:{key}:{field}")
            require(
                gates.get("nodejs_safe_integer_finite_domain_required") is True,
                f"NODEJS_SAFE_DOMAIN_GATE_DRIFT:{key}",
            )
            require(
                gates.get("nodejs_effects_async_io_allowed") is False,
                f"NODEJS_EFFECT_GATE_DRIFT:{key}",
            )
            require(
                gates.get("nodejs_typescript_integer_semantics_allowed")
                is (not nodejs_typescript),
                f"NODEJS_TYPESCRIPT_INTEGER_GATE_DRIFT:{key}",
            )
            types = load_stable_json(
                routes_root,
                pack_dir / "mappings" / "types.json",
                f"NODEJS_TYPES_FILE_UNSAFE:{key}",
            )
            require(isinstance(types, dict), f"NODEJS_TYPES_INVALID:{key}")
            assert isinstance(types, dict)
            expected_types = (
                ["number", "boolean", "string"]
                if nodejs_typescript
                else ["integer", "number", "boolean"]
            )
            capability_by_id = {
                item.get("id"): item for item in capabilities if isinstance(item, dict)
            }
            expected_capability_statuses = {
                "typed-pure-function-v1": "conditional",
                "primitive-types": "conditional",
                "nodejs-es2022-esm-safe-integer-finite-v1": "conditional",
                "string-semantics": "conditional" if nodejs_typescript else "blocked",
                "number-arithmetic": "blocked",
                "if-return-control-flow": "conditional",
                "framework-database-async-concurrency": "blocked",
                "typed-pure-module-v1": "conditional",
            }
            for capability_id, expected_status in expected_capability_statuses.items():
                require(
                    capability_by_id.get(capability_id, {}).get("status")
                    == expected_status,
                    f"NODEJS_CAPABILITY_STATUS_DRIFT:{key}:{capability_id}",
                )
            require(
                types.get("types") == expected_types,
                f"NODEJS_TYPE_SET_DRIFT:{key}",
            )
            require(
                types.get("integer_semantics")
                == (
                    "BLOCK_NO_EXPLICIT_INTEGER_TYPE"
                    if nodejs_typescript
                    else "SAFE_INTEGER_CONDITIONAL"
                ),
                f"NODEJS_INTEGER_DOMAIN_DRIFT:{key}",
            )


def check_console(inventory: dict[str, object], routes: list[dict[str, str]]) -> None:
    languages = inventory["languages"]
    assert isinstance(languages, dict)
    console = console_languages()
    exposed = inventory.get("console_exposed_languages")
    expected_console_languages = SUPPORTED_ROUTE_LANGUAGES
    require(
        exposed == list(expected_console_languages),
        "CONSOLE_EXPOSED_LANGUAGE_POLICY_DRIFT",
    )
    require(
        console_exposed_languages() == expected_console_languages,
        "CONSOLE_EXPOSED_LANGUAGE_SET_DRIFT",
    )
    require_exact_language_set(
        console_contract_languages(),
        expected_console_languages,
        "CONSOLE_CONTRACT_LANGUAGE_SET_DRIFT",
    )
    require_exact_language_set(
        console_runner_languages(),
        expected_console_languages,
        "CONSOLE_RUNNER_LANGUAGE_SET_DRIFT",
    )
    require(
        set(console) == set(expected_console_languages), "CONSOLE_LANGUAGE_SET_DRIFT"
    )
    for language in expected_console_languages:
        declared = languages[language]
        entry = console[language]
        require(
            entry["engine_path"] == declared["engine_path"],
            f"CONSOLE_ENGINE_PATH_DRIFT:{language}",
        )
        # The contract records a single version string ("5.9.2 / Node 26.0.0");
        # the console splits it across a compiler and a runtime label. Require
        # every meaningful token to survive that split so a version bump in one
        # place cannot silently diverge from the other.
        toolchain = f"{entry['compiler']} {entry['runtime']}"
        tokens = [token for token in re.split(r"[\s/]+", declared["version"]) if token]
        require(bool(tokens), f"CONTRACT_VERSION_EMPTY:{language}")
        for token in tokens:
            require(token in toolchain, f"CONSOLE_VERSION_DRIFT:{language}:{token}")

    engine = set(engine_languages())
    require(set(languages) == engine, "ENGINE_LANGUAGE_COVERAGE_DRIFT")
    require(set(routed_languages()) == engine, "ENGINE_ROUTED_LANGUAGE_DRIFT")
    models = ENGINE_MODELS.read_text(encoding="utf-8")
    specialized_block = re.search(
        r"SPECIALIZED_DIRECTED_PAIRS[^=]*=\s*\((.*?)\n\)",
        models,
        re.DOTALL,
    )
    require(specialized_block is not None, "ENGINE_SPECIALIZED_ROUTE_SET_MISSING")
    assert specialized_block is not None
    engine_specialized = {
        f"{source}-to-{target}"
        for source, target in re.findall(
            r'\("([a-z]+)",\s*"([a-z]+)"\)', specialized_block.group(1)
        )
    }
    require(
        engine_specialized == set(SPECIALIZED_ROUTE_KEYS),
        "ENGINE_SPECIALIZED_ROUTE_SET_DRIFT",
    )

    # The static console fallback must never assert readiness. Only the server
    # reader, which parses routes/inventory.json, may report a pass.
    fallback = BUSINESS_LINES.read_text(encoding="utf-8")
    require(
        "consoleTranslationLanguages.flatMap" in fallback,
        "CONSOLE_FALLBACK_IGNORES_EXPOSURE_POLICY",
    )
    block = re.search(
        r"export const directedLanguageRoutes.*?\n\);", fallback, re.DOTALL
    )
    require(block is not None, "CONSOLE_FALLBACK_BLOCK_NOT_FOUND")
    assert block is not None
    for field in ("localExecution", "independentVerification", "externalVerification"):
        require(
            re.search(rf'{field}:\s*"NOT_RUN"\s*as\s*const', block.group(0))
            is not None,
            f"CONSOLE_FALLBACK_ASSERTS_STATUS:{field}",
        )
    require(
        'readiness: "NOT_RUN" as const' in block.group(0),
        "CONSOLE_FALLBACK_ASSERTS_READINESS",
    )

    reader = TRANSLATION_READER.read_text(encoding="utf-8")
    require(
        'ROUTE_INVENTORY_RELATIVE_PATH = "routes/inventory.json"' in reader,
        "CONSOLE_READER_CONTRACT_PATH_DRIFT",
    )
    require("TranslationContractError" in reader, "CONSOLE_READER_NOT_FAIL_CLOSED")
    for pending_field in (
        "pending_analyzer_languages",
        "pending_repository_languages",
    ):
        require(
            pending_field in reader,
            f"CONSOLE_READER_IGNORES_{pending_field.upper()}",
        )

    studio = TRANSLATION_STUDIO.read_text(encoding="utf-8")
    require(
        "routeCellLabel" in studio and "routeByPair" in studio,
        "CONSOLE_MATRIX_NOT_CONTRACT_BOUND",
    )
    # Guard the exact regression this validator was written for: a matrix cell
    # that prints a pass without consulting the route it renders.
    require(
        re.search(r"<span>LOCAL PASS</span>", studio) is None,
        "CONSOLE_MATRIX_HARDCODES_LOCAL_PASS",
    )
    require(
        len(routes) == inventory["route_count"],
        "CONSOLE_ROUTE_COUNT_DRIFT",
    )


def check_repository_pipeline() -> None:
    """The repository scope must be a real pipeline, not an inventory dead end.

    Inventory alone cannot answer whether a repository is migratable. Discovery
    must classify each unit with the same compiler-backed analyzer the migration
    uses, and the batch executor must be resumable and must refuse to round a
    partial result up to success.
    """
    cli = (ENGINE_SOURCE / "cli.py").read_text(encoding="utf-8")
    for subcommand in ("inventory", "discover", "batch"):
        require(f'"{subcommand}"' in cli, f"ENGINE_SUBCOMMAND_MISSING:{subcommand}")

    discovery = (ENGINE_SOURCE / "discovery.py").read_text(encoding="utf-8")
    # Discovery must defer to the public language-aware dispatcher, never to
    # its own scanner or the legacy native-only facade.
    require(
        "from .source_analyzer import analyze_many, inventory_module" in discovery,
        "DISCOVERY_NOT_ANALYZER_BOUND",
    )
    for verdict in ("READY", "UNSUPPORTED", "NO_CANDIDATE_DECLARATION", "UNREADABLE"):
        require(verdict in discovery, f"DISCOVERY_VERDICT_MISSING:{verdict}")
    require('"execution_status": "NOT_RUN"' in discovery, "DISCOVERY_CLAIMS_EXECUTION")
    require("WORK_UNIT_CONTENT_CHANGED" in discovery, "DISCOVERY_NOT_CONTENT_ADDRESSED")

    batch = (ENGINE_SOURCE / "batch.py").read_text(encoding="utf-8")
    require("CHECKPOINT_NAME" in batch, "BATCH_NOT_RESUMABLE")
    require("SKIPPED_NO_CASES" in batch, "BATCH_ACCEPTS_UNITS_WITHOUT_CORPUS")
    require(
        '"COMPLETE" if complete else "PARTIAL"' in batch,
        "BATCH_STATUS_NOT_CONSERVATIVE",
    )
    require("unattempted == 0" in batch, "BATCH_IGNORES_UNATTEMPTED_UNITS")

    console = ROOT / "apps" / "web-console" / "app"
    require(
        (console / "api" / "translation" / "repository-plan" / "_route.ts").is_file(),
        "CONSOLE_PLAN_ROUTE_MISSING",
    )
    require(
        (console / "api" / "translation" / "discovery-report" / "_route.ts").is_file(),
        "CONSOLE_DISCOVERY_ROUTE_MISSING",
    )
    discovery_server = (
        console / "lib" / "server" / "translationDiscovery.ts"
    ).read_text(encoding="utf-8")
    for guard in (
        "DISCOVERY_READY_WITHOUT_ANALYZER",
        "DISCOVERY_SNAPSHOT_MISMATCH",
        "DISCOVERY_EXECUTION_CLAIMED",
    ):
        require(guard in discovery_server, f"CONSOLE_DISCOVERY_GUARD_MISSING:{guard}")


def main() -> int:
    inventory = load_inventory()
    routes = check_inventory_shape(inventory)
    semantic_profile = str(inventory["semantic_profile"])
    languages = inventory.get("languages")
    require(isinstance(languages, dict), "LANGUAGE_METADATA_INVALID")
    assert isinstance(languages, dict)
    check_route_packs(routes, semantic_profile, languages)
    check_console(inventory, routes)
    check_repository_pipeline()
    print(
        json.dumps(
            {
                "status": "PASSED",
                "route_count": len(routes),
                "semantic_profile": semantic_profile,
                "locally_passed": sum(
                    1
                    for entry in routes
                    if entry.get("local_execution_status") == "PASSED_LOCAL"
                ),
                "repository_pipeline": "inventory -> discover -> resumable batch",
                "certified_route_count": inventory["certified_route_count"],
                "independent_verification_evidence": inventory[
                    "independent_verification_evidence"
                ],
                "external_certification_evidence": inventory[
                    "external_certification_evidence"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MatrixError as error:
        print(json.dumps({"status": "FAILED", "reason": str(error)}, sort_keys=True))
        raise SystemExit(2) from error

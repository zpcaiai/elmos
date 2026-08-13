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
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "routes" / "inventory.json"
ENGINE_SOURCE = ROOT / "engines" / "polyglot-route-engine" / "src" / "elmos_polyglot_route"
ENGINE_MODELS = ENGINE_SOURCE / "models.py"
BUSINESS_LINES = ROOT / "apps" / "web-console" / "app" / "lib" / "businessLines.ts"
TRANSLATION_READER = ROOT / "apps" / "web-console" / "app" / "lib" / "server" / "translationRoutes.ts"
TRANSLATION_STUDIO = ROOT / "apps" / "web-console" / "app" / "translation" / "TranslationStudio.tsx"
sys.path.insert(0, str(ROOT / "scripts" / "batch29"))

from route_sets import (  # noqa: E402
    COMPLETE_ROUTE_KEYS,
    COMPLETION_ROUTE_KEYS,
    CORE_LANGUAGES,
    CORE_ROUTE_KEYS,
    EVIDENCED_ROUTE_KEYS,
    MODULE_EQUIVALENCE_ROUTE_KEYS,
    NINE_LANGUAGE_COMPLETE_ROUTE_KEYS,
    NINE_LANGUAGE_MATRIX_LANGUAGES,
    NODEJS_EXACT_ROUTE_KEYS,
    SPECIALIZED_ROUTE_KEYS,
    SUPPORTED_ROUTE_LANGUAGES,
    provenance_route_set,
)

LOCAL_STATUSES = {"PASSED_LOCAL", "NOT_RUN", "FAILED"}
VERIFICATION_STATUSES = {"PASSED", "NOT_RUN", "FAILED"}
ROUTE_STATUSES = {"research", "experimental", "limited", "certified", "blocked"}


class MatrixError(RuntimeError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise MatrixError(reason)


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
            r"^ROUTED_LANGUAGES[^=]*=\s*COMPLETE_MATRIX_LANGUAGES\s*$",
            text,
            re.MULTILINE,
        )
        is not None,
        "ENGINE_ROUTED_LANGUAGE_ALIAS_DRIFT",
    )
    return declared_engine_languages("COMPLETE_MATRIX_LANGUAGES")


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


def load_inventory() -> dict[str, object]:
    require(INVENTORY.is_file(), "ROUTE_INVENTORY_MISSING")
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


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

    policy = inventory.get("route_policy")
    require(
        policy
        == {
            "mode": "complete-directed-matrix",
            "cartesian_expansion": "EXPLICIT_TEN_LANGUAGE_MATRIX",
            "complete_route_set": "ten-language-complete-90",
            "legacy_route_set": "legacy-complete-30",
            "specialized_route_set": "cpp-objc-swift-java-exact-8",
            "completion_route_set": "nine-language-completion-34",
            "nodejs_route_set": "javascript-node26-completion-18",
            "preserved_nine_language_route_set": "nine-language-complete-72",
        },
        "ROUTE_POLICY_DRIFT",
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
        },
        "ROUTE_SET_KEYS_DRIFT",
    )
    core_set = route_sets.get("legacy-complete-30")
    specialized_set = route_sets.get("cpp-objc-swift-java-exact-8")
    completion_set = route_sets.get("nine-language-completion-34")
    nine_complete_set = route_sets.get("nine-language-complete-72")
    nodejs_set = route_sets.get("javascript-node26-completion-18")
    complete_set = route_sets.get("ten-language-complete-90")
    require(isinstance(core_set, dict), "CORE_ROUTE_SET_INVALID")
    require(isinstance(specialized_set, dict), "SPECIALIZED_ROUTE_SET_INVALID")
    require(isinstance(completion_set, dict), "COMPLETION_ROUTE_SET_INVALID")
    require(isinstance(nine_complete_set, dict), "NINE_COMPLETE_ROUTE_SET_INVALID")
    require(isinstance(nodejs_set, dict), "NODEJS_ROUTE_SET_INVALID")
    require(isinstance(complete_set, dict), "COMPLETE_ROUTE_SET_INVALID")
    assert (
        isinstance(core_set, dict)
        and isinstance(specialized_set, dict)
        and isinstance(completion_set, dict)
        and isinstance(nine_complete_set, dict)
        and isinstance(nodejs_set, dict)
        and isinstance(complete_set, dict)
    )
    require(core_set.get("policy") == "complete-directed-permutation", "CORE_ROUTE_POLICY_DRIFT")
    require(core_set.get("languages") == list(CORE_LANGUAGES), "CORE_ROUTE_LANGUAGE_ORDER_DRIFT")
    require(core_set.get("route_count") == 30, "CORE_ROUTE_COUNT_DRIFT")
    require(core_set.get("route_keys") == list(CORE_ROUTE_KEYS), "CORE_ROUTE_KEYS_DRIFT")
    require(specialized_set.get("policy") == "exact-explicit-set", "SPECIALIZED_ROUTE_POLICY_DRIFT")
    require(
        specialized_set.get("languages") == ["cpp", "objc", "swift", "java"], "SPECIALIZED_ROUTE_LANGUAGE_ORDER_DRIFT"
    )
    require(specialized_set.get("route_count") == 8, "SPECIALIZED_ROUTE_COUNT_DRIFT")
    require(specialized_set.get("route_keys") == list(SPECIALIZED_ROUTE_KEYS), "SPECIALIZED_ROUTE_KEYS_DRIFT")
    require(specialized_set.get("module_profile") == "typed-pure-module-v1", "SPECIALIZED_MODULE_PROFILE_DRIFT")
    nine_languages = list(NINE_LANGUAGE_MATRIX_LANGUAGES)
    all_languages = list(SUPPORTED_ROUTE_LANGUAGES)
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
    require(nine_complete_set.get("route_count") == 72, "NINE_COMPLETE_ROUTE_COUNT_DRIFT")
    require(
        nine_complete_set.get("route_keys") == list(NINE_LANGUAGE_COMPLETE_ROUTE_KEYS),
        "NINE_COMPLETE_ROUTE_KEYS_DRIFT",
    )
    require(
        nodejs_set.get("policy") == "exact-nodejs-matrix-completion-set",
        "NODEJS_ROUTE_POLICY_DRIFT",
    )
    require(nodejs_set.get("languages") == all_languages, "NODEJS_ROUTE_LANGUAGE_ORDER_DRIFT")
    require(nodejs_set.get("route_count") == 18, "NODEJS_ROUTE_COUNT_DRIFT")
    require(nodejs_set.get("route_keys") == list(NODEJS_EXACT_ROUTE_KEYS), "NODEJS_ROUTE_KEYS_DRIFT")
    require(nodejs_set.get("runtime_profile") == "Node.js 26.0.0 / ES2022 / ESM", "NODEJS_RUNTIME_DRIFT")
    require(nodejs_set.get("module_profile") == "typed-pure-module-v1", "NODEJS_MODULE_PROFILE_DRIFT")
    require(
        nodejs_set.get("input_domain") == "nodejs-es2022-esm-safe-integer-finite-v1",
        "NODEJS_INPUT_DOMAIN_DRIFT",
    )
    require(
        complete_set.get("policy") == "complete-directed-permutation",
        "COMPLETE_ROUTE_POLICY_DRIFT",
    )
    require(
        complete_set.get("languages") == all_languages,
        "COMPLETE_ROUTE_LANGUAGE_ORDER_DRIFT",
    )
    require(complete_set.get("route_count") == 90, "COMPLETE_ROUTE_COUNT_DRIFT")
    require(
        complete_set.get("route_keys") == list(COMPLETE_ROUTE_KEYS),
        "COMPLETE_ROUTE_KEYS_DRIFT",
    )

    require(inventory.get("route_count") == len(routes), "ROUTE_COUNT_DRIFT")
    require(inventory.get("route_count") == 90, "ROUTE_EXPLICIT_COUNT_DRIFT")
    require(isinstance(inventory.get("semantic_profile"), str), "SEMANTIC_PROFILE_MISSING")
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
        for field in ("independent_verification_status", "external_certification_status"):
            require(entry.get(field) in VERIFICATION_STATUSES, f"{field.upper()}_INVALID:{key}")
        require(source in languages and target in languages, f"ROUTE_LANGUAGE_UNKNOWN:{key}")
        expected_route_set = provenance_route_set(key)
        require(entry.get("route_set") == expected_route_set, f"ROUTE_SET_BINDING_DRIFT:{key}")
        module_status = entry.get("module_execution_status")
        if key in MODULE_EQUIVALENCE_ROUTE_KEYS:
            require(module_status in LOCAL_STATUSES, f"ROUTE_MODULE_STATUS_INVALID:{key}")
            if entry.get("local_execution_status") == "PASSED_LOCAL":
                require(module_status == "PASSED_LOCAL", f"ROUTE_MODULE_EVIDENCE_INVERTED:{key}")
        else:
            require(module_status == "NOT_APPLICABLE", f"ROUTE_MODULE_STATUS_DRIFT:{key}")
        require(
            languages[source]["version"] == entry.get("source_version")
            and languages[target]["version"] == entry.get("target_version"),
            f"ROUTE_VERSION_DRIFT:{key}",
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


def check_route_packs(routes: list[dict[str, str]], semantic_profile: str) -> None:
    directories = {path.name for path in (ROOT / "routes").iterdir() if path.is_dir()}
    declared = {str(entry["route_key"]) for entry in routes}
    require(directories == declared, "ROUTE_PACK_DIRECTORY_DRIFT")

    for entry in routes:
        key = str(entry["route_key"])
        pack_dir = ROOT / "routes" / key
        route_json = pack_dir / "route.json"
        support_json = pack_dir / "support-matrix.json"
        require(route_json.is_file(), f"ROUTE_PACK_MISSING:{key}")
        require(support_json.is_file(), f"ROUTE_SUPPORT_MATRIX_MISSING:{key}")

        pack = json.loads(route_json.read_text(encoding="utf-8"))
        require(pack.get("route_key") == key, f"ROUTE_PACK_KEY_DRIFT:{key}")
        require(pack.get("status") == entry.get("status"), f"ROUTE_PACK_STATUS_DRIFT:{key}")
        require(
            pack.get("source", {}).get("language") == entry.get("source")
            and pack.get("target", {}).get("language") == entry.get("target"),
            f"ROUTE_PACK_DIRECTION_DRIFT:{key}",
        )
        require(
            pack.get("profiles", {}).get("semantic_profile") == semantic_profile,
            f"ROUTE_PACK_PROFILE_DRIFT:{key}",
        )

        support = json.loads(support_json.read_text(encoding="utf-8"))
        capabilities = support.get("capabilities")
        require(isinstance(capabilities, list) and capabilities, f"ROUTE_SUPPORT_EMPTY:{key}")
        profile_entry = next((item for item in capabilities if item.get("id") == semantic_profile), None)
        require(profile_entry is not None, f"ROUTE_SUPPORT_PROFILE_MISSING:{key}")
        assert profile_entry is not None
        expected_capability_status = (
            "conditional"
            if key in MODULE_EQUIVALENCE_ROUTE_KEYS
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
                pack.get("profiles", {}).get("input_domain") == "canonical-finite-no-error-input-domain",
                f"SPECIALIZED_INPUT_DOMAIN_DRIFT:{key}",
            )
            require(
                pack.get("profiles", {}).get("module_profile") == "typed-pure-module-v1",
                f"SPECIALIZED_MODULE_PROFILE_DRIFT:{key}",
            )
            require(
                pack.get("gates", {}).get("concrete_spans_required") is True,
                f"SPECIALIZED_SPAN_POLICY_DRIFT:{key}",
            )
            types = json.loads((pack_dir / "mappings" / "types.json").read_text(encoding="utf-8"))
            require(
                types.get("types") == ["integer", "number", "boolean"],
                f"SPECIALIZED_TYPE_SET_DRIFT:{key}",
            )
        if key in NODEJS_EXACT_ROUTE_KEYS:
            gates = pack.get("gates", {})
            profiles = pack.get("profiles", {})
            nodejs_typescript = {entry.get("source"), entry.get("target")} == {
                "javascript",
                "typescript",
            }
            require(pack.get("status") == "limited", f"NODEJS_ROUTE_STATUS_DRIFT:{key}")
            require(
                profiles.get("input_domain") == "nodejs-es2022-esm-safe-integer-finite-v1",
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
            types = json.loads((pack_dir / "mappings" / "types.json").read_text(encoding="utf-8"))
            expected_types = (
                ["number", "boolean", "string"]
                if nodejs_typescript
                else ["integer", "number", "boolean"]
            )
            capability_by_id = {
                item.get("id"): item
                for item in capabilities
                if isinstance(item, dict)
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
    require(set(console) == set(expected_console_languages), "CONSOLE_LANGUAGE_SET_DRIFT")
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
        for source, target in re.findall(r'\("([a-z]+)",\s*"([a-z]+)"\)', specialized_block.group(1))
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
    block = re.search(r"export const directedLanguageRoutes.*?\n\);", fallback, re.DOTALL)
    require(block is not None, "CONSOLE_FALLBACK_BLOCK_NOT_FOUND")
    assert block is not None
    for field in ("localExecution", "independentVerification", "externalVerification"):
        require(
            re.search(rf'{field}:\s*"NOT_RUN"\s*as\s*const', block.group(0)) is not None,
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
    # Discovery must defer to the native analyzer, never to its own scanner.
    require("from .native import analyze" in discovery, "DISCOVERY_NOT_ANALYZER_BOUND")
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
        (console / "api" / "translation" / "repository-plan" / "route.ts").is_file(),
        "CONSOLE_PLAN_ROUTE_MISSING",
    )
    require(
        (console / "api" / "translation" / "discovery-report" / "route.ts").is_file(),
        "CONSOLE_DISCOVERY_ROUTE_MISSING",
    )
    discovery_server = (console / "lib" / "server" / "translationDiscovery.ts").read_text(encoding="utf-8")
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
    check_route_packs(routes, semantic_profile)
    check_console(inventory, routes)
    check_repository_pipeline()
    print(
        json.dumps(
            {
                "status": "PASSED",
                "route_count": len(routes),
                "semantic_profile": semantic_profile,
                "locally_passed": sum(1 for entry in routes if entry.get("local_execution_status") == "PASSED_LOCAL"),
                "repository_pipeline": "inventory -> discover -> resumable batch",
                "certified_route_count": inventory["certified_route_count"],
                "independent_verification_evidence": inventory["independent_verification_evidence"],
                "external_certification_evidence": inventory["external_certification_evidence"],
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

#!/usr/bin/env python3
"""Fail closed when the Spring modernization catalog drifts across its owners.

`SpringRouteCatalog.java` is the only authority for which legacy Spring source
lines the engine can modernize and which single tuple carries recorded
end-to-end evidence. Four other places repeat parts of it: the OpenRewrite
recipe resources, the engine and console deployment guidance, the console proxy
fallback catalog, and the console page itself.

This validator keeps them identical, refuses a catalog that would let evidence
run ahead of itself, and guards the regression it was written for -- a console
page that prints a version pair it never read from the engine capability
contract.
"""
from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "apps" / "java-engine-worker" / "src" / "main"
WORKER_JAVA = WORKER / "java" / "io" / "elmos" / "worker"
CATALOG = WORKER_JAVA / "SpringRouteCatalog.java"
MODELS = WORKER_JAVA / "SpringUpgradeModels.java"
EXECUTION_PORT = WORKER_JAVA / "LocalSpringUpgradeExecutionPort.java"
ENGINE_GUIDANCE = WORKER_JAVA / "SpringDeploymentGuidance.java"
CONSOLE = ROOT / "apps" / "web-console" / "app"
CONSOLE_PROXY = CONSOLE / "api" / "spring-upgrades" / "[...path]" / "route.ts"
CONSOLE_GUIDANCE = CONSOLE / "lib" / "deploymentGuidance.ts"
CONSOLE_ROUTES = CONSOLE / "lib" / "springRoutes.ts"
CONSOLE_STUDIO = CONSOLE / "spring" / "SpringModernizationStudio.tsx"

EVIDENCE_STATUSES = {"PASSED_LOCAL", "NOT_RUN", "NOT_IMPLEMENTED"}

# SpringUpgradeModels binds one route's tuple into PACK_KEY / SOURCE_BOOT /
# SOURCE_JAVA, and the engine guidance document quotes that same pair. The
# binding is to this specific route, not to "whichever route is verified".
# While one route was recorded those were the same thing; with several recorded
# they are not, and `next(...)` would silently pick whichever sits earliest in
# the catalog -- validating a real pair, just not the one that is actually
# bound, and passing while doing it.
PACK_BOUND_ROUTE_ID = "boot-2.7-maven-to-boot-3.5.3-java-21"


def pack_bound_route(routes: list[dict[str, object]]) -> dict[str, object]:
    """The route whose tuple SpringUpgradeModels and the guidance doc quote."""
    match = [route for route in routes if route["route_id"] == PACK_BOUND_ROUTE_ID]
    require(len(match) == 1, f"PACK_BOUND_ROUTE_MISSING:{PACK_BOUND_ROUTE_ID}")
    require(
        match[0]["evidence"] == "PASSED_LOCAL",
        f"PACK_BOUND_ROUTE_NOT_VERIFIED:{PACK_BOUND_ROUTE_ID}",
    )
    return match[0]


class ContractError(RuntimeError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ContractError(reason)


def version_key(value: str) -> tuple[int, ...]:
    parts = []
    for segment in re.split(r"[^0-9]+", value):
        if segment:
            parts.append(int(segment))
    return tuple(parts) or (0,)


def catalog_constants() -> dict[str, str]:
    text = CATALOG.read_text(encoding="utf-8")
    values: dict[str, str] = {}
    for name in ("TARGET_BOOT", "TARGET_JAVA", "REWRITE_SPRING", "REWRITE_MAVEN_PLUGIN", "MAVEN_TOOLCHAIN"):
        match = re.search(rf'\b{name}\s*=\s*"([^"]+)"\s*;', text)
        require(match is not None, f"CATALOG_CONSTANT_MISSING:{name}")
        assert match is not None
        values[name] = match.group(1)
    return values


def parse_catalog() -> list[dict[str, object]]:
    """Parse the declared routes from the Java catalog source.

    The catalog is a static list of record constructor calls with fixed
    positional arguments, so it is read positionally rather than by importing a
    JVM. Any change to the record shape breaks this parse loudly instead of
    silently validating the wrong fields.
    """
    text = CATALOG.read_text(encoding="utf-8")
    block = re.search(r"private static final List<SpringRoute> ROUTES = List\.of\((.*?)\n    \);", text, re.DOTALL)
    require(block is not None, "CATALOG_ROUTE_LIST_NOT_FOUND")
    assert block is not None

    constants = catalog_constants()
    build_tools = {"MAVEN_BUILD_TOOL": "maven", "GRADLE_BUILD_TOOL": "gradle"}

    routes: list[dict[str, object]] = []
    chunks = block.group(1).split("new SpringRoute(")[1:]
    for body in chunks:
        java_versions = re.search(r"Set\.of\(([^)]*)\)", body)
        require(java_versions is not None, "CATALOG_ROUTE_JAVA_SET_MISSING")
        assert java_versions is not None
        java_set = re.findall(r'"([^"]+)"', java_versions.group(1))
        require(bool(java_set), "CATALOG_ROUTE_JAVA_SET_EMPTY")

        head, tail = body.split("Set.of(", 1)
        head_strings = re.findall(r'"([^"]*)"', head)
        require(len(head_strings) >= 5, "CATALOG_ROUTE_HEAD_FIELDS_MISSING")

        after_set = tail.split(")", 1)[1]
        build_token = re.search(r"\b(MAVEN_BUILD_TOOL|GRADLE_BUILD_TOOL)\b", after_set)
        require(build_token is not None, "CATALOG_ROUTE_BUILD_TOOL_MISSING")
        assert build_token is not None

        evidence = re.search(r"EvidenceStatus\.([A-Z_]+)", after_set)
        require(evidence is not None, "CATALOG_ROUTE_EVIDENCE_MISSING")
        assert evidence is not None
        require(evidence.group(1) in EVIDENCE_STATUSES, f"CATALOG_EVIDENCE_INVALID:{evidence.group(1)}")

        before_evidence, after_evidence = after_set.split("EvidenceStatus." + evidence.group(1), 1)
        recipe_strings = re.findall(r'"([^"]*)"', before_evidence)
        require(len(recipe_strings) >= 2, "CATALOG_ROUTE_RECIPE_FIELDS_MISSING")
        verified_strings = re.findall(r'"([^"]*)"', after_evidence)
        require(len(verified_strings) >= 2, "CATALOG_ROUTE_VERIFIED_FIELDS_MISSING")

        routes.append({
            "route_id": head_strings[0],
            "pack_key": head_strings[1],
            "label": head_strings[2],
            "source_boot_min": head_strings[3],
            "source_boot_max": head_strings[4],
            "build_tool": build_tools[build_token.group(1)],
            "target_boot": constants["TARGET_BOOT"],
            "target_java": constants["TARGET_JAVA"],
            "recipe_resource": recipe_strings[0],
            "recipe_id": recipe_strings[1],
            "verified_boot": verified_strings[0],
            "verified_java": verified_strings[1],
            "source_java_versions": sorted(java_set, key=lambda value: int(value)),
            "evidence": evidence.group(1),
        })
    require(bool(routes), "CATALOG_ROUTES_NOT_PARSED")
    return routes


def check_catalog_shape(routes: list[dict[str, object]], constants: dict[str, str]) -> None:
    ids = set()
    recipe_ids = set()
    for route in routes:
        route_id = str(route["route_id"])
        require(route_id not in ids, f"ROUTE_ID_DUPLICATED:{route_id}")
        ids.add(route_id)
        require(
            version_key(str(route["source_boot_min"])) < version_key(str(route["source_boot_max"])),
            f"ROUTE_RANGE_INVERTED:{route_id}",
        )
        require(route["target_boot"] == constants["TARGET_BOOT"], f"ROUTE_TARGET_BOOT_DRIFT:{route_id}")
        require(route["target_java"] == constants["TARGET_JAVA"], f"ROUTE_TARGET_JAVA_DRIFT:{route_id}")
        require(bool(route["source_java_versions"]), f"ROUTE_SOURCE_JAVA_EMPTY:{route_id}")

        if route["evidence"] == "NOT_IMPLEMENTED":
            require(route["recipe_resource"] == "", f"UNIMPLEMENTED_ROUTE_DECLARES_RECIPE:{route_id}")
            continue

        recipe_id = str(route["recipe_id"])
        require(recipe_id not in recipe_ids, f"RECIPE_ID_DUPLICATED:{recipe_id}")
        recipe_ids.add(recipe_id)
        resource = WORKER / "resources" / str(route["recipe_resource"]).lstrip("/")
        require(resource.is_file(), f"RECIPE_RESOURCE_MISSING:{route['recipe_resource']}")
        recipe = resource.read_text(encoding="utf-8")
        require(f"name: {recipe_id}" in recipe, f"RECIPE_NAME_DRIFT:{recipe_id}")
        require(
            f"newVersion: {constants['TARGET_BOOT']}" in recipe,
            f"RECIPE_TARGET_BOOT_DRIFT:{recipe_id}",
        )
        require(
            "org.openrewrite.java.migrate.UpgradeToJava21" in recipe,
            f"RECIPE_MISSING_JAVA_MIGRATION:{recipe_id}",
        )

        if route["evidence"] == "PASSED_LOCAL":
            verified_boot = str(route["verified_boot"])
            verified_java = str(route["verified_java"])
            require(verified_boot != "" and verified_java != "", f"VERIFIED_TUPLE_MISSING:{route_id}")
            require(
                version_key(str(route["source_boot_min"]))
                <= version_key(verified_boot)
                < version_key(str(route["source_boot_max"])),
                f"VERIFIED_TUPLE_OUTSIDE_RANGE:{route_id}",
            )
            require(verified_java in route["source_java_versions"], f"VERIFIED_JAVA_OUTSIDE_SET:{route_id}")
        else:
            require(
                route["verified_boot"] == "" and route["verified_java"] == "",
                f"UNVERIFIED_ROUTE_DECLARES_EVIDENCE:{route_id}",
            )

    # Ranges within one build tool must be disjoint or selection is ambiguous.
    for build_tool in {str(route["build_tool"]) for route in routes}:
        ordered = sorted(
            (route for route in routes if route["build_tool"] == build_tool),
            key=lambda route: version_key(str(route["source_boot_min"])),
        )
        for left, right in zip(ordered, ordered[1:]):
            require(
                version_key(str(left["source_boot_max"])) <= version_key(str(right["source_boot_min"])),
                f"ROUTE_RANGES_OVERLAP:{build_tool}:{left['route_id']}:{right['route_id']}",
            )

    verified = [route for route in routes if route["evidence"] == "PASSED_LOCAL"]
    # This used to require exactly one verified route. A count is the wrong
    # invariant: it fails as soon as a second route is legitimately recorded, so
    # the only way past it is to raise the number, which is the edit nobody
    # thinks about. What matters is that at least one route is recorded and that
    # no two routes claim the same tuple -- two routes reporting the same
    # source Boot and Java would mean one execution was counted twice.
    require(len(verified) >= 1, "NO_VERIFIED_ROUTE_RECORDED")
    tuples = [(str(route["verified_boot"]), str(route["verified_java"])) for route in verified]
    require(len(set(tuples)) == len(tuples), "VERIFIED_TUPLE_DUPLICATED_ACROSS_ROUTES")

    bound = pack_bound_route(routes)
    models = MODELS.read_text(encoding="utf-8")
    require(f'PACK_KEY = "{bound["pack_key"]}"' in models, "MODELS_PACK_KEY_DRIFT")
    require(f'SOURCE_BOOT = "{bound["verified_boot"]}"' in models, "MODELS_SOURCE_BOOT_DRIFT")
    require(f'SOURCE_JAVA = "{bound["verified_java"]}"' in models, "MODELS_SOURCE_JAVA_DRIFT")


def check_engine(routes: list[dict[str, object]], constants: dict[str, str]) -> None:
    port = EXECUTION_PORT.read_text(encoding="utf-8")
    # Route selection, recipe installation and the JDK registry must all be
    # catalog driven; a literal version here means a hardcoded route is back.
    for needle in (
        "SpringRouteCatalog.select(",
        "route.recipeId()",
        "route.recipeResource()",
        "route.artifactFileName()",
        "sourceJavaHome(",
        "SPRING_ROUTE_EVIDENCE_NOT_RUN",
    ):
        require(needle in port, f"ENGINE_NOT_CATALOG_BOUND:{needle}")
    require(
        "requireExactSupportedTuple" not in port,
        "ENGINE_STILL_ASSERTS_SINGLE_TUPLE",
    )

    bound = pack_bound_route(routes)
    guidance = ENGINE_GUIDANCE.read_text(encoding="utf-8")
    for needle in (
        f"Spring Boot {bound['verified_boot']} / Java {bound['verified_java']}",
        f"Spring Boot {constants['TARGET_BOOT']} / Java {constants['TARGET_JAVA']}",
        f'"framework": "Spring Boot {constants["TARGET_BOOT"]}"',
    ):
        require(needle in guidance, f"ENGINE_GUIDANCE_DRIFT:{needle}")


def check_console(routes: list[dict[str, object]], constants: dict[str, str]) -> None:
    # The proxy mirrors the pack-bound route's tuple specifically, so bind to it
    # by id rather than to whichever route happens to be verified first.
    verified = pack_bound_route(routes)

    # Parse the console mirror per route. A global substring check would let a
    # value drift onto the wrong route and still find a match elsewhere.
    mirror = CONSOLE_ROUTES.read_text(encoding="utf-8")
    blocks: dict[str, str] = {}
    for chunk in mirror.split("{\n    routeId:")[1:]:
        body = "routeId:" + chunk.split("\n  },", 1)[0]
        route_id = re.search(r'routeId:\s*"([^"]+)"', body)
        require(route_id is not None, "CONSOLE_ROUTE_ID_UNPARSEABLE")
        assert route_id is not None
        blocks[route_id.group(1)] = body
    require(len(blocks) == len(routes), "CONSOLE_ROUTE_COUNT_DRIFT")

    def field(body: str, name: str, route_id: str) -> str:
        match = re.search(rf'{name}:\s*"([^"]*)"', body)
        require(match is not None, f"CONSOLE_FIELD_MISSING:{route_id}:{name}")
        assert match is not None
        return match.group(1)

    for route in routes:
        route_id = str(route["route_id"])
        body = blocks.get(route_id)
        require(body is not None, f"CONSOLE_ROUTE_MISSING:{route_id}")
        assert body is not None
        for console_field, catalog_field in (
            ("packKey", "pack_key"),
            ("buildTool", "build_tool"),
            ("sourceBootMinInclusive", "source_boot_min"),
            ("sourceBootMaxExclusive", "source_boot_max"),
            ("targetSpringBoot", "target_boot"),
            ("targetJava", "target_java"),
            ("recipeId", "recipe_id"),
            ("evidenceStatus", "evidence"),
            ("verifiedSourceSpringBoot", "verified_boot"),
            ("verifiedSourceJava", "verified_java"),
        ):
            require(
                field(body, console_field, route_id) == route[catalog_field],
                f"CONSOLE_ROUTE_FIELD_DRIFT:{route_id}:{console_field}",
            )
        java_versions = re.search(r"sourceJavaVersions:\s*\[([^\]]*)\]", body)
        require(java_versions is not None, f"CONSOLE_ROUTE_JAVA_MISSING:{route_id}")
        assert java_versions is not None
        declared = sorted(re.findall(r'"([^"]+)"', java_versions.group(1)))
        require(
            declared == sorted(route["source_java_versions"]),  # type: ignore[arg-type]
            f"CONSOLE_ROUTE_JAVA_DRIFT:{route_id}",
        )

    proxy = CONSOLE_PROXY.read_text(encoding="utf-8")
    require(f'packKey: "{verified["pack_key"]}"' in proxy, "PROXY_PACK_KEY_DRIFT")
    require(
        f'sourceTuple: {{ springBoot: "{verified["verified_boot"]}", '
        f'java: "{verified["verified_java"]}"' in proxy,
        "PROXY_SOURCE_TUPLE_DRIFT",
    )
    require(
        f'targetTuple: {{ springBoot: "{constants["TARGET_BOOT"]}", '
        f'java: "{constants["TARGET_JAVA"]}"' in proxy,
        "PROXY_TARGET_TUPLE_DRIFT",
    )
    require(
        f'openRewrite: {{ rewriteSpring: "{constants["REWRITE_SPRING"]}", '
        f'mavenPlugin: "{constants["REWRITE_MAVEN_PLUGIN"]}" }}' in proxy,
        "PROXY_OPENREWRITE_DRIFT",
    )
    require("routes: springRouteCatalogFallback" in proxy, "PROXY_ROUTE_CATALOG_MISSING")
    for flag in ("transformerConfigured", "runtimeRunnerConfigured", "independentVerifierConfigured"):
        require(f"{flag}: false" in proxy, f"PROXY_FALLBACK_CLAIMS_READY:{flag}")

    guidance = CONSOLE_GUIDANCE.read_text(encoding="utf-8")
    for needle in (
        f'framework: "Spring Boot {constants["TARGET_BOOT"]}"',
        f'framework: "Boot {verified["verified_boot"]} / Java {verified["verified_java"]} '
        f'→ Boot {constants["TARGET_BOOT"]} / Java {constants["TARGET_JAVA"]}"',
        f'OpenRewrite {constants["REWRITE_SPRING"]}',
    ):
        require(needle in guidance, f"CONSOLE_GUIDANCE_DRIFT:{needle}")

    studio = CONSOLE_STUDIO.read_text(encoding="utf-8")
    for literal in (
        constants["TARGET_BOOT"],
        constants["REWRITE_SPRING"],
        constants["REWRITE_MAVEN_PLUGIN"],
        str(verified["verified_boot"]),
    ):
        require(literal not in studio, f"STUDIO_HARDCODES_VERSION:{literal}")
    for needle in (
        "capability.sourceTuple.springBoot",
        "capability.targetTuple.springBoot",
        "capability.openRewrite.rewriteSpring",
        "capability?.routes",
        "lockedRouteLabel",
    ):
        require(needle in studio, f"STUDIO_NOT_CONTRACT_BOUND:{needle}")


def main() -> int:
    constants = catalog_constants()
    routes = parse_catalog()
    check_catalog_shape(routes, constants)
    check_engine(routes, constants)
    check_console(routes, constants)
    recorded = [route for route in routes if route["evidence"] == "PASSED_LOCAL"]
    print(
        json.dumps(
            {
                "status": "PASSED",
                "declared_routes": len(routes),
                "implemented_routes": sum(1 for route in routes if route["evidence"] != "NOT_IMPLEMENTED"),
                "recorded_routes": len(recorded),
                # Report every recorded tuple. Printing one of several would
                # under-report the evidence while looking complete.
                "recorded_tuples": sorted(
                    f"{route['route_id']}: Spring Boot {route['verified_boot']}"
                    f" / Java {route['verified_java']}"
                    for route in recorded
                ),
                "pack_bound_route": PACK_BOUND_ROUTE_ID,
                "target": f"Spring Boot {constants['TARGET_BOOT']} / Java {constants['TARGET_JAVA']}",
                "open_rewrite": constants["REWRITE_SPRING"],
                "maven_plugin": constants["REWRITE_MAVEN_PLUGIN"],
                "external_evidence_status": "NOT_RUN",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(json.dumps({"status": "FAILED", "reason": str(error)}, sort_keys=True))
        raise SystemExit(2) from error

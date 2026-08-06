#!/usr/bin/env python3
"""Establish whether the Batch 23 Spring -> ASP.NET route can actually be executed.

The Batch 23 cases declare the precondition "Batch 23实现与契约可定位" and assert
"真实启动" and "受保护端点可用". Before any of that can be tested, a production
Spring -> ASP.NET transformation, a source corpus and an exact toolchain have to
exist. This probe checks each of those mechanically and records where it looked,
so a missing capability is an auditable finding rather than an opinion.

Exit code 0 only when the route is executable end to end.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUTE_ID = "java-spring-to-csharp-aspnet"
#: Every tree a framework recipe could legitimately live in. Recorded in the
#: report so "no recipe found" is auditable rather than a claim about the void.
RECIPE_SEARCH_ROOTS = (
    "contracts", "recipes", "modules", "engines", "packages", "convergence-packs",
    "templates", "schemas", "config", "product-convergence", "client-packs",
    "framework-packs", "database-packs", "cloud-packs", "marketplace-packs",
    "mature-product-packs", "portfolio-packs", "verification-packs",
    "developer-experience-packs", "quick-fix", "routes", "examples", "artifacts",
)
#: Skill trees (.agents/skills, agent-skills) hold SKILL.md definitions rather than
#: framework-recipe documents and are excluded to keep the probe inside a single
#: case timeout. The absence of a production spring -> aspnet recipe is established
#: independently by production-recipe-targets-aspnet and by
#: spring-to-aspnet-recipe-is-production-not-fixture.
RECIPE_SEARCH_EXCLUSIONS = (".agents", "agent-skills")
REFERENCE_ROUTE = REPO / "convergence-packs/reference-product/reference-route.json"
POLYGLOT = REPO / "engines/polyglot-route-engine"

# The eight capabilities the Batch 23 catalog cases are written against.
B23_CAPABILITIES = (
    ("REST与Binding", ("RestController", "MapControllers", "MapGet", "@RequestMapping")),
    ("DI与Lifecycle", ("IServiceCollection", "AddScoped", "@Component", "@Autowired")),
    ("Configuration/Options", ("IOptions", "appsettings", "@ConfigurationProperties")),
    ("Validation", ("DataAnnotations", "IValidatableObject", "@Valid", "javax.validation")),
    ("Security", ("AuthenticationHandler", "AuthorizationPolicy", "SecurityFilterChain")),
    ("JPA到EF Core", ("DbContext", "DbSet", "EntityTypeConfiguration", "@Entity")),
    ("Transaction/AOP", ("TransactionScope", "IInterceptor", "@Transactional", "@Aspect")),
    ("Messaging/Cache/Scheduler", ("IHostedService", "IDistributedCache", "@Scheduled", "@KafkaListener")),
)

findings: list[dict] = []


def record(check: str, ok: bool, detail: str, looked_at: list[str]) -> None:
    findings.append({"check": check, "ok": ok, "detail": detail, "looked_at": looked_at})
    print(f"[{'PASS' if ok else 'GAP '}] {check}: {detail}")


def rel(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def check_reference_route() -> None:
    if not REFERENCE_ROUTE.is_file():
        record("reference-route-declared", False, "reference-route.json missing", [rel(REFERENCE_ROUTE)])
        return
    route = json.loads(REFERENCE_ROUTE.read_text(encoding="utf-8"))
    declared = route.get("route_id") == ROUTE_ID
    record(
        "reference-route-declared",
        declared,
        f"route_id={route.get('route_id')} source={route.get('source', {}).get('framework_versions')} "
        f"target={route.get('target', {}).get('framework_versions')}",
        [rel(REFERENCE_ROUTE)],
    )
    stages = route.get("stage_results", [])
    not_run = [s["stage"] for s in stages if s.get("status") == "not-run"]
    record(
        "reference-route-stages-executed",
        not not_run,
        f"{len(stages) - len(not_run)}/{len(stages)} stages executed; not-run={not_run}",
        [rel(REFERENCE_ROUTE)],
    )
    without_evidence = [s["stage"] for s in stages if not s.get("evidence")]
    record(
        "reference-route-stages-have-evidence",
        not without_evidence,
        f"{len(stages) - len(without_evidence)}/{len(stages)} stages carry evidence",
        [rel(REFERENCE_ROUTE)],
    )


def check_corpora() -> None:
    corpus_root = REPO / "convergence-packs/reference-product/reference-repositories"
    entries = [p for p in corpus_root.iterdir() if not p.name.startswith(".")] if corpus_root.is_dir() else []
    with_sources = [p for p in entries if p.is_dir() and any(p.rglob("*.java"))]
    record(
        "source-repository-corpus-present",
        bool(with_sources),
        f"{len(entries)} non-placeholder entr(ies), {len(with_sources)} containing Java sources "
        f"(placeholders present: {sorted(q.name for q in corpus_root.iterdir()) if corpus_root.is_dir() else []})",
        [rel(corpus_root)],
    )
    for kind in ("holdout", "representative"):
        root = POLYGLOT / "fixtures" / kind
        java_units = sorted(root.glob("java/*.java")) if root.is_dir() else []
        spring_units = [p for p in java_units if "spring" in p.read_text(encoding="utf-8", errors="ignore").lower()]
        record(
            f"{kind}-corpus-contains-spring-application",
            bool(spring_units),
            f"{len(java_units)} java unit(s) present, {len(spring_units)} contain Spring constructs",
            [rel(root)],
        )


def check_production_recipe() -> None:
    recipe_root = REPO / "recipes"
    sources = [p for p in recipe_root.rglob("*.java") if "/target/" not in p.as_posix()] if recipe_root.is_dir() else []
    targeting_aspnet = [
        p for p in sources
        if "aspnet" in p.read_text(encoding="utf-8", errors="ignore").lower()
    ]
    record(
        "production-recipe-targets-aspnet",
        bool(targeting_aspnet),
        f"{len(sources)} recipe source(s) on disk, {len(targeting_aspnet)} target ASP.NET "
        f"({', '.join(p.stem for p in sources) or 'none'})",
        [rel(recipe_root)],
    )

    registry = REPO / "modules/framework-migration/src/main/java/io/elmos/frameworkmigration/FrameworkRecipeRegistry.java"
    main_root = REPO / "modules/framework-migration/src/main/java"
    test_root = REPO / "modules/framework-migration/src/test/java"
    in_main = [p for p in main_root.rglob("*.java") if "aspnet-core-controller" in p.read_text(encoding="utf-8", errors="ignore")]
    in_test = [p for p in test_root.rglob("*.java") if "aspnet-core-controller" in p.read_text(encoding="utf-8", errors="ignore")]
    record(
        "spring-to-aspnet-recipe-is-production-not-fixture",
        bool(in_main),
        f"'aspnet-core-controller' appears in {len(in_main)} main source(s) and {len(in_test)} test source(s); "
        f"registry blocks with 'no-production-recipe' when nothing matches",
        [rel(main_root), rel(test_root), rel(registry)],
    )


def check_code_generation() -> None:
    for label, path in (
        ("aspnet", REPO / "engines/dotnet-engine/src/Elmos.Dotnet.AspNet/AspNetMigrationAdvisor.cs"),
        ("ef-core", REPO / "engines/dotnet-engine/src/Elmos.Dotnet.Ef/EfMigrationPlanner.cs"),
    ):
        if not path.is_file():
            record(f"{label}-code-generation-implemented", False, "component missing", [rel(path)])
            continue
        text = path.read_text(encoding="utf-8")
        lines = len(text.splitlines())
        emits = any(marker in text for marker in ("SyntaxFactory", "StringBuilder", "WriteAllText", "Emit", "Generate"))
        record(
            f"{label}-code-generation-implemented",
            emits,
            f"{lines} lines; emits target source = {emits} (advisor/planner returns a decision record only)",
            [rel(path)],
        )


def _production_recipes() -> list[dict]:
    """Every on-disk document shaped like contracts/framework-schema/framework-recipe.schema.json."""
    required = {"recipeId", "sourceFramework", "targetFramework", "transformations", "production"}
    pruned = {".git", "node_modules", "obj", "bin", "target", ".venv", "build", "site-packages",
              "__pycache__", ".next", ".pytest_cache", ".ruff_cache", "_to_delete"}
    found: list[dict] = []
    for root in RECIPE_SEARCH_ROOTS:
      base = REPO / root
      if not base.is_dir():
        continue
      for directory, subdirs, files in os.walk(base):
        subdirs[:] = [d for d in subdirs if d not in pruned]
        for name in files:
            if not name.endswith(".json"):
                continue
            path = Path(directory) / name
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                blob = path.read_bytes()
                # "sourceFramework" is required by framework-recipe.schema.json, so a file
                # without it cannot be a recipe. Cheap prefilter before paying for a parse.
                if b"sourceFramework" not in blob:
                    continue
                payload = json.loads(blob.decode("utf-8"))
            except Exception:  # noqa: BLE001
                continue
            for candidate in (payload if isinstance(payload, list) else [payload]):
                if isinstance(candidate, dict) and required <= set(candidate):
                    candidate["_source_path"] = rel(path)
                    found.append(candidate)
    return found


def check_capability_inventory() -> None:
    recipes = _production_recipes()
    route_recipes = [
        r for r in recipes
        if str(r.get("sourceFramework", "")).lower().startswith("spring")
        and "aspnet" in str(r.get("targetFramework", "")).lower()
    ]
    record(
        "framework-recipe-documents-on-disk",
        bool(route_recipes),
        f"{len(recipes)} recipe-shaped document(s) found repository-wide, "
        f"{len(route_recipes)} of them spring-* -> aspnet-*",
        ["contracts/framework-schema/framework-recipe.schema.json", *RECIPE_SEARCH_ROOTS,
         f"(excluded: {list(RECIPE_SEARCH_EXCLUSIONS)})"],
    )

    covered = {str(r.get("entityKind", "")).lower() for r in route_recipes if r.get("production")}
    for capability, markers in B23_CAPABILITIES:
        hits = sorted(
            r["_source_path"] for r in route_recipes
            if any(marker.lower().lstrip("@").split(".")[-1] in str(r.get("entityKind", "")).lower() for marker in markers)
        )
        record(
            f"capability-has-production-recipe::{capability}",
            bool(hits),
            f"0 of {len(route_recipes)} route recipes cover this capability"
            if not hits else f"covered by {hits}",
            ["(spring-* -> aspnet-* framework recipes)"],
        )
    if covered:
        print(f"    (entityKinds covered by route recipes: {sorted(covered)})")


def check_toolchain() -> None:
    script = (
        "import sys; sys.path.insert(0, 'src');"
        "from elmos_polyglot_route.toolchains import resolve_toolchain\n"
    )
    for language, expected in (("java", "21.0.11"), ("csharp", "10.0.301")):
        probe = (
            "import sys; sys.path.insert(0, 'src')\n"
            "from elmos_polyglot_route import toolchains\n"
            "from elmos_polyglot_route.models import RouteError\n"
            f"fn = getattr(toolchains, '_{language}')\n"
            "try:\n"
            "    tc = fn()\n"
            "    print('OK', tc.version)\n"
            "except RouteError as exc:\n"
            "    print('REFUSED', exc)\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", probe], cwd=POLYGLOT, capture_output=True, text=True, check=False
        )
        output = (completed.stdout + completed.stderr).strip().splitlines()[-1] if (completed.stdout or completed.stderr) else "no output"
        record(
            f"exact-toolchain::{language}",
            output.startswith("OK"),
            f"required {expected}; engine says: {output}",
            [rel(POLYGLOT / "src/elmos_polyglot_route/toolchains.py")],
        )


def check_unit_level_route(work: Path) -> None:
    source = POLYGLOT / "fixtures/java/Pricing.java"
    cases = POLYGLOT / "fixtures/behavior-cases.json"
    unit_dir = work / "unit-route"
    unit_dir.mkdir(parents=True, exist_ok=True)
    output = unit_dir / "java-to-csharp.json"
    completed = subprocess.run(
        [
            sys.executable, "-m", "elmos_polyglot_route.cli",
            "--source", str(source), "--source-language", "java",
            "--target-language", "csharp", "--function", "calculate",
            "--cases", str(cases), "--output", str(output),
        ],
        cwd=POLYGLOT,
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(work)},
    )
    body = (completed.stdout + completed.stderr).strip()
    record(
        "unit-level-java-to-csharp-executes",
        completed.returncode == 0 and output.is_file(),
        f"exit={completed.returncode} response={body[:200]}",
        [rel(source), rel(cases)],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="", help="write the machine-readable gap report here")
    args = parser.parse_args()

    print(f"=== Batch 23 route readiness: {ROUTE_ID} ===\n")
    check_reference_route()
    check_corpora()
    check_production_recipe()
    check_code_generation()
    check_capability_inventory()
    check_toolchain()
    work = Path(args.report).parent if args.report else Path("/tmp")
    work.mkdir(parents=True, exist_ok=True)
    check_unit_level_route(work)

    gaps = [f for f in findings if not f["ok"]]
    print(f"\n{len(findings) - len(gaps)}/{len(findings)} readiness checks hold; {len(gaps)} gap(s)")
    for gap in gaps:
        print(f"  GAP {gap['check']}")
    report = {
        "route_id": ROUTE_ID,
        "ready": not gaps,
        "checks_total": len(findings),
        "gaps": len(gaps),
        "findings": findings,
    }
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"report written to {args.report}")
    return 0 if not gaps else 1


if __name__ == "__main__":
    raise SystemExit(main())

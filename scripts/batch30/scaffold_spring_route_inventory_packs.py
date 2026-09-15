#!/usr/bin/env python3
"""Materialize the nine declared but unqualified Spring route Pack contracts.

This is an inventory operation. It creates no source/target runtime receipt,
does not execute a recipe and cannot promote support or certification.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CATALOG_VALIDATOR = ROOT / "scripts/operations/validate_spring_route_contract.py"
SCAFFOLD = Path(__file__).with_name("scaffold_framework_pack.py")

# A seed is one exact source point inside a broader inventory route, not a
# claim that its other source versions or provider environments were replayed.
SEEDS = {
    "spring-boot-1-5-to-2-7-18": ("1.5.22.RELEASE", "8", "spring-boot"),
    "spring-boot-1-5-to-3-2-12": ("1.5.22.RELEASE", "8", "spring-boot"),
    "spring-boot-2-0-2-6-to-2-7-18": ("2.3.12.RELEASE", "11", "spring-boot"),
    "spring-boot-2-0-2-6-to-3-2-12": ("2.3.12.RELEASE", "11", "spring-boot"),
    "spring-boot-2-7-to-3-2-12": ("2.7.18", "17", "spring-boot"),
    "spring-boot-3-0-3-1-to-3-2-12": ("3.1.12", "17", "spring-boot"),
    "spring-boot-1-5-3-5-15-to-3-5-16": ("3.5.15", "21", "spring-boot"),
    "spring-framework-3-2-5-2-mvc-to-spring-boot-3-5-3": (
        "5.2.25.RELEASE", "11", "spring-mvc"
    ),
    "java-ee-servlet-2-5-to-spring-boot-3-5-3": ("2.5.0", "17", "java-ee-servlet"),
}


def routes_from_catalog() -> list[dict[str, object]]:
    spec = importlib.util.spec_from_file_location("spring_route_contract", CATALOG_VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.parse_catalog()


def validate_seed(route: dict[str, object], seed: tuple[str, str, str]) -> None:
    source_version, source_java, family = seed
    if (
        route["source_family_contract"] != family
        or source_java not in route["source_java_versions"]
        or route["evidence"] not in {"NOT_RUN", "NOT_IMPLEMENTED", "PASSED_LOCAL"}
        or not str(route["recipe_resource"]).startswith("/rewrite/")
    ):
        raise ValueError(f"inventory seed no longer binds its NOT_RUN route: {route['route_id']}")
    if route["evidence"] == "PASSED_LOCAL" and (
        route["verified_boot"] != source_version
        or route["verified_java"] != source_java
    ):
        raise ValueError(f"recorded raw route tuple differs from Pack seed: {route['route_id']}")
    # Existing broad catalog route rules remain the version-range authority.
    if source_version == "" or not str(route["target_boot"]).count(".") == 2:
        raise ValueError(f"inventory seed is not an exact version: {route['route_id']}")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def materialize(repo: Path, route: dict[str, object], seed: tuple[str, str, str]) -> Path:
    key = str(route["pack_key"])
    source_version, source_java, family = seed
    target_boot, target_java = str(route["target_boot"]), str(route["target_java"])
    pack = repo / "framework-packs" / key
    if pack.exists():
        raise ValueError(f"refusing to overwrite an existing Pack: {pack}")
    result = subprocess.run(
        [sys.executable, str(SCAFFOLD), "--repo-root", str(repo),
         "--source-framework", family, "--target-framework", "spring-boot",
         "--source-runtime", "java", "--target-runtime", "java",
         "--mode", "modernization" if family != "spring-boot" else "upgrade",
         "--pack-key", key],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"repository Pack scaffold failed: {result.stderr}")

    manifest = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    manifest.update(owner="ELMOS Java Modernization Team",
                    maintenance_owner="ELMOS Framework Pack Maintainers",
                    status="research", review_date="2026-10-26")
    manifest["source"].update(framework=family, framework_versions=[source_version],
                              runtime_versions=[source_java], build_tools=["maven-3.9.11"])
    manifest["target"].update(framework_versions=[target_boot],
                              runtime_versions=[target_java], build_tools=["maven-3.9.11"])
    write_json(pack / "pack.json", manifest)

    profile = json.loads((pack / "target-profile/profile.json").read_text(encoding="utf-8"))
    profile.update(owner="ELMOS Framework Pack Maintainers",
                   framework_versions=[target_boot], runtime_versions=[target_java],
                   architecture_style="INVENTORY_ONLY_NOT_RUN")
    write_json(pack / "target-profile/profile.json", profile)

    resource = str(route["recipe_resource"]).removeprefix("/rewrite/")
    worker = repo / "apps/java-engine-worker/src/main/resources/rewrite" / resource
    raw = worker.read_bytes()
    if b"\r" in raw.replace(b"\r\n", b""):
        raise ValueError(f"non-canonical Worker recipe has bare CR: {worker}")
    canonical = raw.replace(b"\r\n", b"\n")
    # Copy source data, not proof that this Pack executes the recipe.
    recipe = pack / "recipes" / resource
    recipe.write_bytes(canonical)
    digest = hashlib.sha256(canonical).hexdigest()
    write_json(pack / "recipes/manifest.json", {
        "schema_version": 1, "pack_key": key,
        "recipes": [route["recipe_id"]],
        "recipe_config": f"recipes/{resource}",
        "worker_recipe_resource": str(route["recipe_resource"]),
        "canonical_recipe_sha256": f"sha256:{digest}",
        "execution_status": "NOT_RUN", "raw_route_status": route["evidence"],
        "certification_eligible": False,
    })
    write_json(pack / "version-matrix.json", {
        "schema_version": 1, "pack_key": key,
        "tuples": [
            {"id": "inventory-source-seed", "framework": family,
             "version": source_version, "java": source_java,
             "build": "maven-3.9.11", "status": "NOT_RUN"},
            {"id": "exact-target", "framework": "spring-boot",
             "version": target_boot, "java": target_java,
             "build": "maven-3.9.11", "status": "NOT_RUN"},
        ],
        "upgrade_edges": [{"from": "inventory-source-seed", "to": "exact-target",
                           "directional": True, "recipes": [route["recipe_id"]],
                           "execution_status": "NOT_RUN"}],
    })
    (pack / "README.md").write_text(
        f"# {key}\n\nRoute `{route['route_id']}` is an exact directional inventory "
        f"contract, not a runnable or certified Pack. The source seed "
        f"{family} {source_version}/Java {source_java} and target Spring Boot "
        f"{target_boot}/Java {target_java} have not been built or started for "
        "this Pack. Active source behavior, FCM, provider/security/data/transaction "
        "contracts, holdout, representative, customer, Rootless and independent "
        "evidence are NOT_RUN. All capabilities remain research/experimental or "
        "blocked; certification is NOT_CERTIFIED.\n",
        encoding="utf-8", newline="\n",
    )
    for folder in ("contracts", "adapters", "corpus/development",
                   "corpus/holdout", "corpus/real-repository"):
        (pack / folder / "NOT_RUN.md").write_text(
            "No source-derived or independent evidence has been executed or authored.\n",
            encoding="utf-8", newline="\n",
        )
    return pack


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--fill-review-date", action="store_true",
                        help="Only fill the review date in previously generated research Packs")
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    routes = routes_from_catalog()
    by_key = {str(route["pack_key"]): route for route in routes
              if str(route["pack_key"]) in SEEDS}
    if set(by_key) != set(SEEDS):
        raise ValueError(f"catalog inventory keys drifted: {sorted(set(SEEDS) ^ set(by_key))}")
    for key, seed in SEEDS.items():
        validate_seed(by_key[key], seed)
        pack = repo / "framework-packs" / key
        if args.audit_only:
            print(f"{key}: {'PRESENT' if pack.is_dir() else 'MISSING_NOT_RUN'}")
        elif args.fill_review_date and pack.is_dir():
            path = pack / "pack.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if manifest.get("pack_key") != key or manifest.get("status") != "research":
                raise ValueError(f"refusing review edit on non-inventory Pack: {pack}")
            if not manifest.get("review_date"):
                manifest["review_date"] = "2026-10-26"
                write_json(path, manifest)
        elif not pack.exists():
            print(f"materialized NOT_RUN inventory: {materialize(repo, by_key[key], seed)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"SPRING_INVENTORY_PACK_FAILED: {error}", file=sys.stderr)
        raise SystemExit(2) from error

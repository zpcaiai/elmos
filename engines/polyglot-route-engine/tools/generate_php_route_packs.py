#!/usr/bin/env python3.12
"""Generate the 20 `php` route packs and fold them into `routes/inventory.json`.

Adding an 11th language takes the declared matrix from 90 directed pairs to 110.
`tests/test_language_set.py` asserts that `routes/` contains exactly one pack
per declared pair and nothing else, so the 20 new packs are not optional
paperwork -- the suite fails without them.

Every generated pack is a structural clone of an existing pack that already has
the same *shape* (same target profile, same gate set), with the language, the
version strings, the corpus fixtures and the route key rewritten. Nothing about
evidence is copied: every status field is written as NOT_RUN, because no php
route has been executed anywhere. A pack is a declaration that a direction
exists and what it would have to prove -- it is not a claim that it proved it.

    python3.12 tools/generate_php_route_packs.py            # dry run, prints a plan
    python3.12 tools/generate_php_route_packs.py --write

SUPERSEDED. `scripts/batch29/run_polyglot_routes.py` is the repository's own
route-pack factory and it is now php-aware:

    python3 scripts/batch29/run_polyglot_routes.py --prepare-route-set php-php85-completion-20
    python3 scripts/batch29/run_polyglot_routes.py --inventory-only

That path builds packs through `scaffold_route.py` in the canonical shape and
writes the inventory from `route_sets.py`, which is the single authority the
validator and the gate also read. This script predates that wiring -- it existed
because the php set was not registered there yet -- and it clones an existing
pack instead of building one. Keeping both means two definitions of what a route
pack is, which will drift; prefer the batch29 runner and delete this once the
packs have been regenerated through it.

Run from the engine directory. Re-running is safe: an existing pack is left
alone unless --overwrite is given.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ENGINE_ROOT.parents[1]
ROUTES = REPOSITORY_ROOT / "routes"

sys.path.insert(0, str(ENGINE_ROOT / "src"))

# Import the two modules this script needs *without* executing the package
# __init__, which pulls in the engine (and therefore z3). A pinning script and a
# route-pack generator have no business requiring an SMT solver to be installed.
import types  # noqa: E402

_PACKAGE = "elmos_polyglot_route"
if _PACKAGE not in sys.modules:
    _stub = types.ModuleType(_PACKAGE)
    _stub.__path__ = [str(ENGINE_ROOT / "src" / _PACKAGE)]
    sys.modules[_PACKAGE] = _stub

from elmos_polyglot_route.models import (  # noqa: E402
    COMPLETE_MATRIX_LANGUAGES,
    SPECIALIZED_DIRECTED_PAIRS,
)


def _php_versions() -> list[str]:
    """The version strings a generated pack records for the PHP end.

    Read from the toolchain pin when it has been filled in, so re-running with
    --overwrite after pinning produces packs that name the interpreter actually
    bound rather than whatever this file was last edited to say. Falls back to a
    label that is visibly not a version, because a pack that quietly asserts a
    plausible-looking wrong version is worse than one that says it does not know.
    """
    from elmos_polyglot_route.toolchains import (  # noqa: PLC0415
        _EXPECTED_PHP_TREE_SHA256,
        _EXPECTED_PHP_VERSION,
    )

    # The digest, not the version string, is what says "pinned": `_php()` refuses
    # to run until the digests are filled in, and the version constant carries a
    # plausible-looking placeholder until then.
    pinned = _EXPECTED_PHP_VERSION if _EXPECTED_PHP_TREE_SHA256 else ""
    return [
        pinned or "PHP (NOT_PINNED -- run tools/pin_php_toolchain.py)",
        "ext/tokenizer Zend token stream",
        "strict_types=1",
    ]


PHP_VERSIONS = _php_versions()
PHP_ENGINE_SOURCE_PATH = "engines/polyglot-route-engine/native/php/analyzer.php"
PHP_ENGINE_TARGET_PATH = "engines/polyglot-route-engine/src/elmos_polyglot_route/emitter.py"
PHP_TARGET_PROFILE = "php-native-interpreter"

#: The corpus fixture each pack carries, per corpus directory. Names match the
#: fixtures added under `fixtures/php/`, `fixtures/holdout/php/` and
#: `fixtures/representative/php/`.
PHP_CORPUS_FILES = {
    "development": ("pricing.php", "calculate"),
    "holdout": ("clamp.php", "clamp"),
    "real-repository": ("difference.php", "difference"),
    "module": ("equivalence_module.php", "calculate"),
}
PHP_FIXTURES = {
    "development": ENGINE_ROOT / "fixtures" / "php" / "pricing.php",
    "holdout": ENGINE_ROOT / "fixtures" / "holdout" / "php" / "clamp.php",
    "real-repository": ENGINE_ROOT / "fixtures" / "representative" / "php" / "difference.php",
    "module": ENGINE_ROOT / "fixtures" / "module" / "php" / "equivalence_module.php",
}

#: Preference order for the *other* end of the template route. A php direction
#: has no pack to copy from, so it borrows the shape of an existing direction
#: that shares its non-php end: `php-to-go` borrows from `java-to-go`, and
#: `go-to-php` borrows from `go-to-java`. The stand-in only ever supplies the
#: gate set and the file layout; every language-specific and evidence-bearing
#: field is rewritten afterwards.
#:
#: `javascript` is last because its packs carry the Node-specific gate set, and
#: the specialized cpp/objc/swift/java eight are never chosen as a stand-in
#: because their gates encode an immutable Batch 29 proof scope.
STAND_INS = ("java", "python", "csharp", "go", "rust", "typescript", "javascript")


def php_pairs() -> list[tuple[str, str]]:
    return [
        (source, target)
        for source in COMPLETE_MATRIX_LANGUAGES
        for target in COMPLETE_MATRIX_LANGUAGES
        if source != target and "php" in (source, target)
    ]


def template_pack(source: str, target: str) -> Path | None:
    """The existing pack whose shape the new one follows, or None if there is none.

    Returning None rather than a made-up path matters: the caller validates every
    template up front and refuses to write anything if one is missing, so a
    routes/ directory that is not what this script expects fails before it has
    half-generated a matrix.
    """
    fixed_end = target if source == "php" else source
    for stand_in in STAND_INS:
        if stand_in == fixed_end:
            # `java-to-java` is not a route. Skip to the next stand-in.
            continue
        pair = (stand_in, target) if source == "php" else (source, stand_in)
        if pair in SPECIALIZED_DIRECTED_PAIRS:
            # The cpp/objc/swift/java exact eight carry a stricter gate set --
            # concrete spans, module equivalence, a restricted input domain --
            # that encodes an immutable Batch 29 proof scope. Copying it would
            # silently claim obligations for a php direction that nothing has
            # established, so those packs are never a stand-in.
            continue
        candidate = ROUTES / f"{pair[0]}-to-{pair[1]}"
        if candidate.is_dir():
            return candidate
    return None


#: Paths removed from every generated pack, relative to the pack root. These are
#: records of a specific execution; the structural files that describe what the
#: direction *would* have to prove are kept and rewritten.
DROPPED_ON_GENERATION = (
    "certification/artifacts",
    "certification/formal-artifacts",
    "certification/formal-equivalence.json",
    "certification/local-*-evidence.json",
    "certification/module-equivalence.json",
)


def relabel_languages(value: object, stand_in: str, replacement: str, php_source_file: str | None) -> object:
    """Rewrite the stand-in language's identity out of a copied document.

    Only exact, whole-value matches are rewritten, and only for keys that name a
    language or a source file. A substring rewrite would corrupt prose and
    engine paths; a key-blind rewrite would hit unrelated fields that happen to
    hold the same word.
    """
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for key, item in value.items():
            if key in {"language", "source_language", "target_language"} and item == stand_in:
                out[key] = replacement
            elif key in {"source", "target"} and item == stand_in:
                out[key] = replacement
            elif key == "source_file" and php_source_file is not None and isinstance(item, str):
                out[key] = php_source_file
            else:
                out[key] = relabel_languages(item, stand_in, replacement, php_source_file)
        return out
    if isinstance(value, list):
        return [relabel_languages(item, stand_in, replacement, php_source_file) for item in value]
    return value


def scrub_evidence(value: object) -> object:
    """Rewrite every status-shaped field to NOT_RUN, recursively."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key.endswith("_status") and isinstance(item, str):
                out[key] = "NOT_APPLICABLE" if item == "NOT_APPLICABLE" else "NOT_RUN"
            elif key in {"observations", "commands", "cases", "evidence"} and isinstance(item, list):
                out[key] = []
            elif key.endswith("_sha256") or key.endswith("_ref") or key.endswith("_bytes"):
                out[key] = None
            else:
                out[key] = scrub_evidence(item)
        return out
    if isinstance(value, list):
        return [scrub_evidence(item) for item in value]
    return value


def rewrite_route_json(document: dict, source: str, target: str) -> dict:
    document = json.loads(json.dumps(document))
    document["route_key"] = f"{source}-to-{target}"
    document["status"] = "limited"
    if source == "php":
        document["source"] = {
            "engine_path": PHP_ENGINE_SOURCE_PATH,
            "language": "php",
            "versions": list(PHP_VERSIONS),
        }
    else:
        document["target"] = {
            "engine_path": PHP_ENGINE_TARGET_PATH,
            "language": "php",
            "versions": list(PHP_VERSIONS),
        }
        document.setdefault("profiles", {})["target_profile"] = PHP_TARGET_PROFILE
    return document


def generate(write: bool, overwrite: bool) -> int:
    if not ROUTES.is_dir():
        print(f"no routes directory at {ROUTES}", file=sys.stderr)
        return 2
    pairs = php_pairs()
    print(f"{len(pairs)} php directions to declare")

    # Resolve every template before touching the filesystem. Half a matrix is
    # worse than none: the pack-completeness assertion in test_language_set.py
    # would then fail for a different reason than the one that actually broke.
    plan: list[tuple[str, str, Path]] = []
    missing: list[str] = []
    for source, target in pairs:
        template = template_pack(source, target)
        if template is None:
            missing.append(f"{source}-to-{target}")
        else:
            plan.append((source, target, template))
    if missing:
        print(f"no stand-in pack found for: {', '.join(missing)}", file=sys.stderr)
        print(f"looked under {ROUTES} for a direction sharing the non-php end.", file=sys.stderr)
        return 1

    created = skipped = 0
    for source, target, template in plan:
        key = f"{source}-to-{target}"
        destination = ROUTES / key
        if destination.exists() and not overwrite:
            skipped += 1
            print(f"  skip     {key} (exists)")
            continue
        print(f"  generate {key:28} from {template.name}")
        if not write:
            continue
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(template, destination)

        # A NOT_RUN route has no run. Copying another direction's evidence and
        # only blanking its status fields would leave documents that still
        # describe that other run -- a java-to-go semantic IR, a formal proof
        # over java's engine sources, a per-corpus execution record -- sitting
        # inside a php pack. Absent is more honest than relabelled, and the
        # engine-sources snapshot alone is ~700KB of a different route's proof
        # input per pack.
        for relative in DROPPED_ON_GENERATION:
            for path in sorted(destination.glob(relative)):
                if path.is_dir():
                    shutil.rmtree(path)
                elif path.is_file():
                    path.unlink()

        route_path = destination / "route.json"
        route_path.write_text(
            json.dumps(
                rewrite_route_json(json.loads(route_path.read_text()), source, target),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        stand_in = template.name.split("-to-")[0] if source == "php" else template.name.split("-to-")[1]
        for path in sorted(destination.rglob("*.json")):
            if path.name == "route.json":
                continue
            document = json.loads(path.read_text())
            if isinstance(document, dict):
                document = scrub_evidence(document)
                document = relabel_languages(document, stand_in, "php", None)
                if "route_key" in document:
                    document["route_key"] = key
            path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")

        # Replace the corpus fixtures with the php ones when php is the source;
        # when php is the target the corpus stays in the source language.
        if source == "php":
            for corpus, (filename, _function) in PHP_CORPUS_FILES.items():
                directory = destination / "corpus" / corpus
                if not directory.is_dir():
                    continue
                for existing in directory.iterdir():
                    if existing.suffix not in {".json"}:
                        existing.unlink()
                shutil.copyfile(PHP_FIXTURES[corpus], directory / filename)
                manifest = directory / "manifest.json"
                if manifest.is_file():
                    document = json.loads(manifest.read_text())
                    document["source_language"] = "php"
                    if "source_file" in document:
                        document["source_file"] = filename
                    for entry in document.get("files", []):
                        entry["path"] = filename
                    manifest.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")

        gate_report = destination / "certification" / "gate-report.md"
        if gate_report.is_file():
            # The copied report asserts PASSED gates for the stand-in's run.
            # Rewriting it as NOT_RUN is not cosmetic: this is the human-facing
            # summary, and a file that says a php route passed its gates when no
            # php route has been executed is the single most misleading artifact
            # a generated pack could carry.
            gate_report.write_text(
                f"# {key} route gate\n\n"
                "- Local bounded profile: `NOT_RUN`\n"
                "- Route status: `limited`\n"
                "- Native source analyzer: `NOT_RUN`\n"
                "- Native target compiler/runtime: `NOT_RUN`\n"
                "- Separate holdout: `NOT_RUN`\n"
                "- Representative repository: `NOT_RUN`\n"
                "- Independent verification: `NOT_RUN`\n"
                "- External certification: `NOT_RUN`\n\n"
                "This direction is declared, not demonstrated. Nothing in this pack is\n"
                "evidence of an execution; the certification directory is where a run\n"
                "would write what it actually proved.\n",
                encoding="utf-8",
            )

        for name in ("customer-support-profile.md", "gap-inventory.md"):
            document = destination / "certification" / name
            if document.is_file():
                # Route-specific prose about the stand-in's direction. Left in
                # place it would describe a different pair of languages under a
                # php route's name.
                document.write_text(
                    f"# {key} -- {name.removesuffix('.md').replace('-', ' ')}\n\n"
                    "`NOT_RUN`. This direction is declared, not demonstrated, so there is\n"
                    "nothing here yet to profile or to inventory gaps against. Writing this\n"
                    "document is part of what a first execution of this route produces.\n",
                    encoding="utf-8",
                )

        readme = destination / "README.md"
        if readme.is_file():
            readme.write_text(
                f"# Route {key}\n\n"
                f"Declared direction in the eleven-language complete matrix.\n\n"
                f"Every evidence state in this pack is `NOT_RUN`. Declaring a direction is\n"
                f"not a claim that it has been executed, verified or certified; the pack\n"
                f"records what this direction would have to prove, and the certification\n"
                f"directory is where a run would write what it did prove.\n\n"
                f"PHP participates in `typed-pure-function-v1` only. Its integer is the\n"
                f"64-bit `int` of a build the toolchain probe has asserted has\n"
                f"`PHP_INT_SIZE == 8`, and its number is binary64. R1 is enforced by the\n"
                f"emitted `elmos_checked_*` helpers, which detect PHP's silent\n"
                f"overflow-to-float promotion; R2 by `intdiv` plus an explicit guard for\n"
                f"`PHP_INT_MIN % -1`, which PHP answers 0 for rather than failing.\n",
                encoding="utf-8",
            )
        created += 1

    inventory_path = ROUTES / "inventory.json"
    if inventory_path.is_file():
        inventory = json.loads(inventory_path.read_text())
        complete = {f"{a}-to-{b}" for a in COMPLETE_MATRIX_LANGUAGES for b in COMPLETE_MATRIX_LANGUAGES if a != b}
        php_keys = sorted({f"{a}-to-{b}" for a, b in pairs})
        ten = sorted(complete - set(php_keys))
        existing = {route["route_key"]: route for route in inventory["routes"]}
        template_route = existing["java-to-csharp"]
        for key in php_keys:
            source, target = key.split("-to-")
            route = json.loads(json.dumps(template_route))
            route.update(
                {
                    "route_key": key,
                    "source": source,
                    "target": target,
                    "source_version": PHP_VERSIONS[0] if source == "php" else existing_version(existing, source),
                    "target_version": PHP_VERSIONS[0] if target == "php" else existing_version(existing, target, False),
                    "route_set": "php-php85-completion-20",
                    "status": "limited",
                }
            )
            route = scrub_evidence(route)
            route["route_key"] = key
            route["source"] = source
            route["target"] = target
            existing[key] = route
        inventory["routes"] = [existing[key] for key in sorted(existing)]
        inventory["route_count"] = len(inventory["routes"])
        inventory["languages"] = sorted(COMPLETE_MATRIX_LANGUAGES)
        inventory["route_policy"].update(
            {
                "cartesian_expansion": "EXPLICIT_ELEVEN_LANGUAGE_MATRIX",
                "complete_route_set": "eleven-language-complete-110",
                "php_route_set": "php-php85-completion-20",
                "preserved_ten_language_route_set": "ten-language-complete-90",
            }
        )
        inventory["route_sets"]["php-php85-completion-20"] = {
            "languages": sorted(COMPLETE_MATRIX_LANGUAGES),
            "module_profile": "NOT_APPLICABLE",
            "policy": "complete-directed-completion",
            "route_count": len(php_keys),
            "route_keys": php_keys,
        }
        inventory["route_sets"]["eleven-language-complete-110"] = {
            "languages": sorted(COMPLETE_MATRIX_LANGUAGES),
            "module_profile": "typed-pure-module-v1",
            "policy": "complete-directed-matrix",
            "route_count": len(complete),
            "route_keys": sorted(complete),
        }
        inventory["route_sets"]["ten-language-complete-90"]["route_keys"] = ten
        inventory["route_sets"]["ten-language-complete-90"]["route_count"] = len(ten)
        print(f"inventory: {inventory['route_count']} routes, {len(inventory['route_sets'])} sets")
        if write:
            inventory_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")

    print(f"created={created} skipped={skipped} write={write}")
    if not write:
        print("\nnothing was written; re-run with --write")
    return 0


def existing_version(existing: dict, language: str, as_source: bool = True) -> str:
    for route in existing.values():
        if as_source and route["source"] == language:
            return route["source_version"]
        if not as_source and route["target"] == language:
            return route["target_version"]
    return "UNKNOWN"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="actually create the packs")
    parser.add_argument("--overwrite", action="store_true", help="replace packs that already exist")
    arguments = parser.parse_args()
    return generate(arguments.write, arguments.overwrite)


if __name__ == "__main__":
    raise SystemExit(main())

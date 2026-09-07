"""Skill 01 — project scope auditor.

Reads a repository and produces the three things a forecast needs before it can
be honest about what it is forecasting:

* ``scope-baseline.json`` / ``.md`` — what is actually in the tree
* ``risk-and-gap-register.json`` — what is declared but missing, and what two
  authorities disagree about
* a seeded ``project-profile.json`` — defaults filled from config, with every
  value the auditor could not measure left explicit rather than invented

The auditor never guesses a number it cannot measure. Anything it could not
determine is emitted as a gap with ``needs_human_input: true``.
"""
from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from .io_utils import load_json
from .token_scan import scan_tokens

#: Extension -> language identity. Deliberately coarse: this is a scope signal,
#: not an analyzer.
LANGUAGE_EXTENSIONS = {
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".cs": "csharp", ".go": "go",
    ".rs": "rust", ".py": "python", ".ts": "typescript", ".tsx": "react", ".jsx": "react",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".cpp": "cpp",
    ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".c": "c", ".h": "c", ".m": "objc",
    ".mm": "objc", ".swift": "swift", ".php": "php", ".dart": "flutter", ".rb": "ruby",
    ".ets": "arkts",
}

BUILD_FILES = {
    "pom.xml": "maven", "build.gradle": "gradle", "build.gradle.kts": "gradle",
    "package.json": "npm", "pyproject.toml": "python", "Cargo.toml": "cargo",
    "go.mod": "go", "CMakeLists.txt": "cmake", "Package.swift": "swiftpm",
    "composer.json": "composer", "pubspec.yaml": "pub", "Makefile": "make",
}

#: Denominator claims made in prose, e.g. "156 directed routes", "110 条有向路线",
#: or a success ratio like "0/72". Ratios are only read as denominators above
#: MIN_RATIO_DENOMINATOR, because small fractions in prose are usually not route
#: counts and would drown the real signal in noise.
MIN_RATIO_DENOMINATOR = 30

DENOMINATOR_PATTERNS = (
    re.compile(r"(\d{1,4})\s*(?:directed\s+routes|条有向路线|条路线|条有向路由)"),
    re.compile(r"routes?\s*[:=]\s*(\d{2,4})\b"),
)

RATIO_PATTERN = re.compile(r"\b\d{1,4}\s*/\s*(\d{2,4})\b")

#: A bare ``x/N`` is only read as a route denominator when its own line is about
#: routes. Without this, "P0/P1/P2 counts 312/120/18" and "174/1015 = 17.1%" get
#: reported as denominator drift, which is how a useful check turns into noise
#: nobody reads.
ROUTE_CONTEXT = re.compile(r"route|路线|路由|matrix|矩阵", re.IGNORECASE)

#: Documents that are *supposed* to state the current denominator. A mismatch in
#: one of these is a real defect: someone reading it will quote a dead number.
#: Everywhere else, an old denominator is usually a historical record that is
#: correct as history -- flagging those as defects buries the real signal, which
#: is exactly what the first version of this check did.
AUTHORITY_DOC_GLOBS = (
    ".ai/TASK.md",
    ".ai/IMPLEMENTATION_STATUS.md",
    ".ai/HANDOFF.md",
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
)


def _read_json_if_present(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return load_json(path)
    except ValueError:
        return None


def _route_inventory(root: Path) -> dict[str, Any] | None:
    """Recognise the elmos route inventory when the repository has one."""
    inventory = _read_json_if_present(root / "routes" / "inventory.json")
    if not inventory:
        return None
    languages = inventory.get("languages", {}) or {}
    pending = sorted(
        name for name, meta in languages.items()
        if isinstance(meta, dict) and meta.get("analyzer_status") == "PENDING_ANALYZER"
    )
    route_dirs = sorted(p.name for p in (root / "routes").iterdir() if p.is_dir() and "-to-" in p.name) \
        if (root / "routes").is_dir() else []
    surplus = _reconcile_directory_surplus(inventory, route_dirs)
    return {
        "declared_route_count": inventory.get("route_count"),
        "declared_routes": len(inventory.get("routes", []) or []),
        "languages": sorted(languages),
        "language_count": len(languages),
        "pending_analyzer_languages": pending,
        "route_set_names": sorted(inventory.get("route_sets") or {}),
        "route_directories": len(route_dirs),
        "directory_surplus_reconciled": surplus,
        "authority_path": "routes/inventory.json",
    }


def _reconcile_directory_surplus(inventory: dict[str, Any], route_dirs: list[str]) -> str | None:
    """Explain the on-disk surplus when a route set already accounts for it.

    A directory count above the declared route count is normal when deprecated
    packs are retained for evidence attribution. It only stops being a finding
    once the surplus is *exactly* a declared deprecated set -- an approximate
    match would let a genuinely stray directory hide behind the explanation.
    """
    active = {
        route.get("route_key") for route in inventory.get("routes", []) or []
        if isinstance(route, dict)
    }
    active.discard(None)
    surplus = set(route_dirs) - active
    if not surplus:
        return None
    for name, route_set in sorted((inventory.get("route_sets") or {}).items()):
        if not isinstance(route_set, dict):
            continue
        deprecated = set(route_set.get("deprecated_route_keys") or [])
        if deprecated and deprecated == surplus:
            return f"{len(surplus)} retained pack(s) = deprecated_route_keys of '{name}'"
    return None


def _prose_denominators(
    root: Path, relative_globs: tuple[str, ...]
) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    """Collect route-count claims made in prose.

    Returns ``(explicit, all_claims)``. ``explicit`` holds only claims written as
    a denominator in words ("156 directed routes", "156 条有向路线"); those are
    the ones an authority document is answerable for. ``all_claims`` additionally
    holds ratio denominators found on route-related lines, which are useful
    context but too noisy to treat as defects.
    """
    explicit: dict[str, list[int]] = {}
    combined: dict[str, list[int]] = {}
    for pattern in relative_globs:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            relative = path.relative_to(root).as_posix()
            phrase_claims = {
                int(match)
                for regex in DENOMINATOR_PATTERNS
                for match in regex.findall(text)
            }
            ratio_claims = {
                int(match)
                for line in text.splitlines() if ROUTE_CONTEXT.search(line)
                for match in RATIO_PATTERN.findall(line)
                if int(match) >= MIN_RATIO_DENOMINATOR
            }
            if phrase_claims:
                explicit[relative] = sorted(phrase_claims)
            if phrase_claims or ratio_claims:
                combined[relative] = sorted(phrase_claims | ratio_claims)
    return explicit, combined


def _walk_census(root: Path, ignore_dirs: set[str],
                 ignore_dir_globs: tuple[str, ...] = ()) -> tuple[dict[str, int], list[str]]:
    """One pruned walk producing both the language census and the build systems in use.

    Two performance rules learned the hard way on a monorepo:

    * use ``os.walk`` with in-place ``dirnames`` pruning, never ``rglob`` -- rglob
      descends into ``node_modules`` before any filter can reject it;
    * do every per-file question in a single pass. Twelve ``rglob("pom.xml")``-style
      lookups is twelve unpruned full-tree walks, which turns seconds into minutes.
    """
    census: dict[str, int] = {}
    build_systems: set[str] = set()
    for _, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name for name in dirnames
            if name not in ignore_dirs
            and not any(fnmatch.fnmatch(name, pattern) for pattern in ignore_dir_globs)
        ]
        for filename in filenames:
            language = LANGUAGE_EXTENSIONS.get(Path(filename).suffix.lower())
            if language:
                census[language] = census.get(language, 0) + 1
            label = BUILD_FILES.get(filename)
            if label:
                build_systems.add(label)
    ordered = dict(sorted(census.items(), key=lambda item: (-item[1], item[0])))
    return ordered, sorted(build_systems)


def audit_scope(
    root: str | Path,
    token_scan: dict[str, Any] | None = None,
    extra_ignore_dirs: tuple[str, ...] = (),
    authority_doc_globs: tuple[str, ...] = AUTHORITY_DOC_GLOBS,
) -> dict[str, Any]:
    base = Path(root).resolve()
    if not base.is_dir():
        raise ValueError(f"Scope root must be a directory: {base}")

    from .token_scan import DEFAULT_IGNORE_DIR_GLOBS, DEFAULT_IGNORE_DIRS

    ignore = set(DEFAULT_IGNORE_DIRS) | set(extra_ignore_dirs)
    scan = token_scan or scan_tokens(base, extra_ignore_dirs=tuple(extra_ignore_dirs))

    census, build_systems = _walk_census(base, ignore, DEFAULT_IGNORE_DIR_GLOBS)
    inventory = _route_inventory(base)
    explicit_claims, prose = _prose_denominators(base, (".ai/*.md", "*.md", "docs/*.md"))

    baseline: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact": "scope-baseline",
        "root": str(base),
        "corpus": {
            "files": scan["totals"]["files"],
            "characters": scan["totals"]["characters"],
            "estimated_tokens": scan["totals"]["estimated_tokens"],
            "counting_method": scan["counting_method"],
            "exact_counts": scan["exact_counts"],
        },
        "skills": {
            "files": scan["totals"]["skill_files"],
            "catalog_tokens": scan["totals"]["skill_catalog_tokens"],
            "body_tokens": scan["totals"]["skill_body_tokens"],
        },
        "languages_by_file_count": census,
        "language_count": len(census),
        "build_systems": build_systems,
        "largest_groups": scan["groups"][:15],
        "route_matrix": inventory,
        "denominator_claims_in_prose": prose,
        "explicit_denominator_claims": explicit_claims,
        "denominator_authority_docs": [
            path for path in prose
            if any(fnmatch.fnmatch(path, pattern) for pattern in authority_doc_globs)
        ],
        "has_git": (base / ".git").exists(),
    }
    baseline["risk_and_gap_register"] = build_register(baseline, scan)
    return baseline


def build_register(baseline: dict[str, Any], scan: dict[str, Any]) -> dict[str, Any]:
    """Turn scope observations into an explicit gap and risk list."""
    gaps: list[dict[str, Any]] = []
    inventory = baseline.get("route_matrix")

    if inventory:
        declared = inventory.get("declared_route_count")
        listed = inventory.get("declared_routes")
        directories = inventory.get("route_directories")
        if declared is not None and listed is not None and declared != listed:
            gaps.append({
                "id": "route-count-internal-mismatch",
                "severity": "high",
                "kind": "authority-inconsistency",
                "detail": f"inventory declares route_count={declared} but lists {listed} routes",
                "needs_human_input": True,
            })
        if declared is not None and directories and directories != declared:
            reconciled = inventory.get("directory_surplus_reconciled")
            gaps.append({
                "id": "route-directory-count-differs",
                "severity": "low" if reconciled else "medium",
                "kind": "informational" if reconciled else "authority-inconsistency",
                "detail": (
                    f"{directories} route directories on disk vs declared route_count={declared}; "
                    + (f"surplus reconciled: {reconciled}" if reconciled
                       else "the excess is usually retained/deprecated packs, but it must be stated explicitly")
                ),
                "needs_human_input": not bool(reconciled),
            })
        for language in inventory.get("pending_analyzer_languages", []):
            gaps.append({
                "id": f"pending-analyzer-{language}",
                "severity": "high",
                "kind": "missing-capability",
                "detail": f"language '{language}' is declared in the matrix but its analyzer is PENDING_ANALYZER",
                "needs_human_input": False,
            })

        claims = baseline.get("denominator_claims_in_prose", {})
        explicit = baseline.get("explicit_denominator_claims", {})
        authority = set(baseline.get("denominator_authority_docs", []))
        declared = inventory.get("declared_route_count")
        if declared is not None:
            drifting_authority = {
                path: values for path, values in explicit.items()
                if path in authority and declared not in values
            }
            if drifting_authority:
                gaps.append({
                    "id": "denominator-drift-in-authority-docs",
                    "severity": "high",
                    "kind": "authority-inconsistency",
                    "detail": (
                        f"{len(drifting_authority)} document(s) that are supposed to state the current "
                        f"denominator quote something other than {declared}"
                    ),
                    "evidence": dict(sorted(drifting_authority.items())),
                    "needs_human_input": True,
                })
            historical = {
                path: values for path, values in claims.items()
                if path not in authority and declared not in values
            }
            if historical:
                gaps.append({
                    "id": "historical-denominators-in-prose",
                    "severity": "low",
                    "kind": "informational",
                    "detail": (
                        f"{len(historical)} non-authoritative document(s) quote an older denominator. "
                        "That is usually correct as history; it is listed so nobody quotes one by accident."
                    ),
                    "evidence": dict(sorted(historical.items())[:10]),
                    "needs_human_input": False,
                })

    oversized = [f for f in scan.get("findings", []) if f["kind"] == "oversized-skill"]
    if oversized:
        gaps.append({
            "id": "oversized-skills",
            "severity": "medium",
            "kind": "context-pressure",
            "detail": f"{len(oversized)} SKILL.md bodies exceed the activation-cost threshold",
            "evidence": [f["path"] for f in oversized[:10]],
            "needs_human_input": False,
        })

    if scan.get("skipped_count"):
        gaps.append({
            "id": "unscanned-files",
            "severity": "low",
            "kind": "coverage",
            "detail": f"{scan['skipped_count']} files were skipped (too large or not UTF-8) and are not in any total",
            "needs_human_input": False,
        })

    if not baseline.get("has_git"):
        gaps.append({
            "id": "no-git-checkpointing",
            "severity": "medium",
            "kind": "missing-capability",
            "detail": "no .git directory: git-based checkpoints are unavailable for recovery",
            "needs_human_input": True,
        })

    return {
        "schema_version": "1.0.0",
        "artifact": "risk-and-gap-register",
        "gaps": gaps,
        "counts_by_severity": {
            severity: sum(1 for gap in gaps if gap["severity"] == severity)
            for severity in ("high", "medium", "low")
        },
        "rule": ("A gap with needs_human_input=true blocks a production-grade forecast; "
                 "the auditor will not invent the answer."),
    }


def seed_project_profile(
    baseline: dict[str, Any],
    defaults: dict[str, Any],
    human_baselines: dict[str, Any],
    project_id: str,
    mode: str = "verification",
    min_worker_units: float = 1.0,
) -> dict[str, Any]:
    """Build a project profile from measured scope plus configured defaults.

    ``min_worker_units`` is the widest single task the decomposition model can
    emit. The seeded worker count is raised until effective capacity can hold
    that task, because a profile that cannot schedule its own DAG is not a
    usable default.
    """
    import math

    system = dict(defaults["system"])
    efficiency = (
        float(system["worker_availability"]) * float(system["parallel_efficiency"])
        * float(system["model_concurrency_factor"]) * float(system["code_conflict_factor"])
    )
    if efficiency > 0:
        needed = math.ceil(float(min_worker_units) / efficiency)
        if needed > float(system["workers"]):
            system["workers"] = needed
            system["workers_raised_for_widest_task"] = float(min_worker_units)
    human = {key: value for key, value in defaults["human"].items()}
    human["roles"] = {
        role: {"headcount": config["headcount"]}
        for role, config in human_baselines["roles"].items()
    }
    register = baseline["risk_and_gap_register"]
    blocking = [gap for gap in register["gaps"] if gap.get("needs_human_input")]

    return {
        "project_id": project_id,
        "mode": mode,
        "description": (
            f"Seeded from a scope audit of {baseline['root']}: "
            f"{baseline['corpus']['files']} files, {baseline['language_count']} languages."
        ),
        "definition_of_done": {
            "level": "production_verified",
            "checks": [
                "source-compiles", "unit-tests", "integration-tests",
                "behavioral-equivalence", "security-and-license-scan",
                "performance-baseline", "evidence-recorded",
            ],
            "exclusions": [],
        },
        "simulation": {"runs": defaults["monte_carlo_runs"], "seed": defaults["seed"]},
        "system": system,
        "human": human,
        "human_assisted": {
            "review_person_hours": 0,
            "approval_wait_hours": 0,
            "external_wait_hours": 0,
            "review_parallel_fraction": 0.0,
        },
        "confidence": 0.35,
        "assumptions": [
            "Seeded by the scope auditor from measured repository facts plus configured defaults.",
            "Durations and token profiles are seeds, not measurements; calibrate after the first milestone.",
        ],
        "exclusions": [
            "Human approval and acceptance time (carried in human_assisted).",
            "Vendor pricing (supply a verified rate card).",
        ],
        "seed_provenance": {
            "widest_task_worker_units": float(min_worker_units),
            "defaults_version": defaults.get("version"),
            "human_baselines_version": human_baselines.get("version"),
            "measured_files": baseline["corpus"]["files"],
            "blocking_gaps": [gap["id"] for gap in blocking],
        },
    }


def render_scope_baseline(baseline: dict[str, Any]) -> str:
    from .io_utils import fmt, markdown_table

    corpus = baseline["corpus"]
    register = baseline["risk_and_gap_register"]
    inventory = baseline.get("route_matrix")

    body = [
        "# SCOPE_BASELINE",
        "",
        f"- 根：`{baseline['root']}`",
        f"- 文件 {fmt(corpus['files'])}，字符 {fmt(corpus['characters'])}，"
        f"一次性读取估算 {fmt(corpus['estimated_tokens'])} tokens（`{corpus['counting_method']}`）",
        f"- Skill 文件 {fmt(baseline['skills']['files'])}，目录常驻 {fmt(baseline['skills']['catalog_tokens'])} tokens",
        f"- 语言身份 {baseline['language_count']} 种，构建体系：{', '.join(baseline['build_systems']) or '未检出'}",
        f"- Git：{'有' if baseline['has_git'] else '无'}",
        "",
        "## 语言分布（按文件数）",
        "",
        markdown_table(["语言", "文件数"],
                       [[k, fmt(v)] for k, v in list(baseline["languages_by_file_count"].items())[:15]]),
        "",
        "## 体量最大的目录",
        "",
        markdown_table(["目录", "文件数", "估算 tokens"],
                       [[g["group"], fmt(g["files"]), fmt(g["estimated_tokens"])]
                        for g in baseline["largest_groups"][:10]]),
        "",
    ]

    if inventory:
        body += [
            "## 路由矩阵",
            "",
            f"- 权威源：`{inventory['authority_path']}`",
            f"- 声明路线数：**{inventory['declared_route_count']}**（列表长度 {inventory['declared_routes']}）",
            f"- 语言：{inventory['language_count']} 门",
            f"- 磁盘上的路由目录：{inventory['route_directories']}",
            f"- PENDING_ANALYZER：{', '.join(inventory['pending_analyzer_languages']) or '无'}",
            "",
        ]

    body += [
        "## 风险与缺口",
        "",
        f"高 {register['counts_by_severity']['high']} · "
        f"中 {register['counts_by_severity']['medium']} · "
        f"低 {register['counts_by_severity']['low']}",
        "",
        markdown_table(
            ["ID", "级别", "类型", "说明", "需人工决策"],
            [[gap["id"], gap["severity"], gap["kind"], gap["detail"],
              "是" if gap.get("needs_human_input") else "否"]
             for gap in register["gaps"]]),
        "",
        f"> {register['rule']}",
    ]
    return "\n".join(body)

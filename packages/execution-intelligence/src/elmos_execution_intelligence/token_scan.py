"""Static token scanning.

This answers one narrow question: *how many tokens does the material already on
disk cost to put in front of a model once*. It is an input to the project token
forecast; it is never the forecast itself. Deriving a whole-project token budget
from file sizes alone is explicitly forbidden by CLAUDE.md.
"""
from __future__ import annotations

import fnmatch
import importlib
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_EXTENSIONS = frozenset({
    ".md", ".txt", ".rst", ".py", ".java", ".kt", ".kts", ".cs", ".go", ".rs", ".cpp", ".cc", ".cxx",
    ".c", ".h", ".hpp", ".php", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".swift", ".m",
    ".mm", ".dart", ".rb", ".ets", ".sql", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".xml", ".html", ".css", ".scss", ".sh", ".bash", ".zsh", ".properties", ".gradle", ".proto",
    ".graphql", ".tf", ".cmake", ".mk",
})

DEFAULT_FILENAMES = frozenset({
    "Dockerfile", "Makefile", "AGENTS.md", "CLAUDE.md", "README", "LICENSE", "Jenkinsfile", "CMakeLists.txt",
})

# Directory names that are never part of the reviewable corpus. Keeping build
# output, vendored dependencies and agent scratch space out of the count is the
# difference between a usable number and a meaningless one.
DEFAULT_IGNORE_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "vendor", "target", "build", "dist",
    "out", ".next", ".turbo", ".gradle", ".m2", ".cargo", ".stack-work", "coverage", "htmlcov",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".idea", ".vscode",
    ".DS_Store", ".ai-tmp", "_to_delete", "_merge_conflicts", "__cmake_systeminformation",
    ".hvigor", "site-packages", ".eggs",
})

DEFAULT_IGNORE_GLOBS = (
    "*.min.js", "*.min.css", "*.lock", "*-lock.json", "*.map", "*.snap",
)

# Build output does not always use the canonical directory name -- a Next.js
# e2e run leaves ".next-e2e-31415" behind, which the exact-name list misses and
# which then dominates the largest-files list with generated bundles.
DEFAULT_IGNORE_DIR_GLOBS = (
    ".next*", "*.egg-info", "*.dSYM", "build-*", "cmake-build-*", ".terraform*",
)

# CJK-ish ranges. One CJK codepoint is close to one token for the tokenizers in
# use today; Latin text is closer to four characters per token.
CJK_PATTERN = re.compile(r"[㐀-䶿一-鿿豈-﫿぀-ヿ가-힯]")

LARGE_SKILL_TOKEN_THRESHOLD = 5_000
HUGE_FILE_TOKEN_THRESHOLD = 40_000


class TokenCounter:
    """Counts tokens with tiktoken when present, otherwise with a CJK-aware heuristic.

    The heuristic is documented as an estimate. Billing-grade static counts must
    come from the target provider's own counting endpoint.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model
        self._encoding = None
        try:  # pragma: no cover - depends on optional dependency
            # Resolve the optional tokenizer dynamically so strict type-checking
            # does not require an undeclared mandatory dependency. The fallback
            # remains explicit in every emitted scan via ``exact_counts``.
            tiktoken = importlib.import_module("tiktoken")

            if model:
                try:
                    self._encoding = tiktoken.encoding_for_model(model)
                except KeyError:
                    self._encoding = tiktoken.get_encoding("o200k_base")
            else:
                self._encoding = tiktoken.get_encoding("o200k_base")
        except Exception:
            self._encoding = None

    @property
    def method(self) -> str:
        return "tiktoken" if self._encoding is not None else "cjk-aware-heuristic"

    @property
    def exact(self) -> bool:
        return self._encoding is not None

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._encoding is not None:  # pragma: no cover - optional dependency
            return len(self._encoding.encode(text))
        cjk = len(CJK_PATTERN.findall(text))
        non_cjk = max(0, len(text) - cjk)
        return max(1, int(round(cjk + non_cjk / 4.0)))


def _parse_frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {"name", "description", "version"}:
            result[key] = value.strip().strip("\"'")
    return result or None


def _is_ignored(relative: str, ignore_globs: tuple[str, ...]) -> bool:
    name = relative.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(relative, pattern) for pattern in ignore_globs)


def _top_group(relative: str, depth: int) -> str:
    parts = relative.split("/")
    if len(parts) <= 1:
        return "<root>"
    return "/".join(parts[: min(depth, len(parts) - 1)])


def _calibration_factor(relative: str, calibration: dict[str, Any] | None) -> float:
    """How much the heuristic misses by, for this file's type.

    Returns 1.0 when there is no calibration, so an uncalibrated scan reports the
    raw heuristic rather than a silently adjusted number.
    """
    if not calibration:
        return 1.0
    suffix = Path(relative).suffix.lower()
    entry = (calibration.get("by_extension") or {}).get(suffix)
    if entry:
        return float(entry["factor"])
    return float(calibration.get("global_factor", 1.0))


def scan_tokens(
    root: str | Path,
    model: str | None = None,
    max_file_bytes: int = 2_000_000,
    extra_ignore_dirs: tuple[str, ...] = (),
    ignore_globs: tuple[str, ...] = DEFAULT_IGNORE_GLOBS,
    ignore_dir_globs: tuple[str, ...] = DEFAULT_IGNORE_DIR_GLOBS,
    group_depth: int = 1,
    top_n: int = 40,
    include_file_list: bool = False,
    calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = Path(root).resolve()
    if not base.exists():
        raise ValueError(f"Path does not exist: {base}")
    if not base.is_dir():
        raise ValueError(f"Scan root must be a directory: {base}")

    counter = TokenCounter(model)
    ignore_dirs = set(DEFAULT_IGNORE_DIRS) | set(extra_ignore_dirs)

    files: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    groups: dict[str, dict[str, float]] = defaultdict(lambda: {"files": 0, "estimated_tokens": 0, "bytes": 0})
    skills: list[dict[str, Any]] = []
    skill_catalog_tokens = 0
    skill_body_tokens = 0

    for current_root, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(
            name for name in dirnames
            if name not in ignore_dirs
            and not any(fnmatch.fnmatch(name, pattern) for pattern in ignore_dir_globs)
        )
        current = Path(current_root)
        for filename in sorted(filenames):
            path = current / filename
            if path.is_symlink():
                continue
            relative = path.relative_to(base).as_posix()
            if path.suffix.lower() not in DEFAULT_EXTENSIONS and filename not in DEFAULT_FILENAMES:
                continue
            if _is_ignored(relative, ignore_globs):
                continue
            try:
                size = path.stat().st_size
            except OSError as exc:
                skipped.append({"path": relative, "reason": f"stat failed: {exc}"})
                continue
            if size > max_file_bytes:
                skipped.append({"path": relative, "reason": f"larger than max_file_bytes={max_file_bytes}"})
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                skipped.append({"path": relative, "reason": f"unreadable as utf-8: {exc}"})
                continue

            token_count = counter.count(text)
            item: dict[str, Any] = {
                "path": relative,
                "bytes": size,
                "characters": len(text),
                "estimated_tokens": token_count,
            }
            if calibration and not counter.exact:
                factor = _calibration_factor(relative, calibration)
                item["calibrated_tokens"] = int(round(token_count / factor))
                item["calibration_factor"] = factor
            if filename == "SKILL.md":
                metadata = _parse_frontmatter(text)
                if metadata:
                    catalog_text = "{}\n{}".format(metadata.get("name", ""), metadata.get("description", ""))
                    catalog_tokens = counter.count(catalog_text)
                    item["skill"] = metadata
                    item["catalog_tokens"] = catalog_tokens
                    skill_catalog_tokens += catalog_tokens
                    skill_body_tokens += token_count
                    skills.append({
                        "path": relative,
                        "name": metadata.get("name"),
                        "catalog_tokens": catalog_tokens,
                        "body_tokens": token_count,
                    })
            files.append(item)
            group = _top_group(relative, group_depth)
            groups[group]["files"] += 1
            groups[group]["estimated_tokens"] += token_count
            groups[group]["bytes"] += size

    by_tokens = sorted(files, key=lambda item: (-int(item["estimated_tokens"]), str(item["path"])))
    group_rows: list[dict[str, Any]] = sorted(
        ({"group": key, **{k: int(v) for k, v in value.items()}} for key, value in groups.items()),
        key=lambda item: (-int(item["estimated_tokens"]), str(item["group"])),
    )

    findings: list[dict[str, Any]] = []
    for skill in sorted(skills, key=lambda item: -item["body_tokens"]):
        if skill["body_tokens"] >= LARGE_SKILL_TOKEN_THRESHOLD:
            findings.append({
                "severity": "warning",
                "kind": "oversized-skill",
                "path": skill["path"],
                "estimated_tokens": skill["body_tokens"],
                "detail": (f"SKILL.md body exceeds {LARGE_SKILL_TOKEN_THRESHOLD} tokens; "
                           "split references out so activation stays cheap."),
            })
    for item in by_tokens:
        if item["estimated_tokens"] >= HUGE_FILE_TOKEN_THRESHOLD:
            findings.append({
                "severity": "warning",
                "kind": "oversized-file",
                "path": item["path"],
                "estimated_tokens": item["estimated_tokens"],
                "detail": (f"Single file above {HUGE_FILE_TOKEN_THRESHOLD} tokens; "
                           "reading it whole will dominate a task's input budget."),
            })

    totals = {
        "files": len(files),
        "bytes": sum(int(item["bytes"]) for item in files),
        "characters": sum(int(item["characters"]) for item in files),
        "estimated_tokens": sum(int(item["estimated_tokens"]) for item in files),
        "calibrated_tokens": (
            sum(int(item["calibrated_tokens"]) for item in files)
            if calibration and not counter.exact and files else None
        ),
        "skill_files": len(skills),
        "skill_catalog_tokens": skill_catalog_tokens,
        "skill_body_tokens": skill_body_tokens,
    }

    result: dict[str, Any] = {
        "schema_version": "1.0.0",
        "root": str(base),
        "model": model,
        "counting_method": counter.method,
        "exact_counts": counter.exact,
        "calibration": (
            {
                "version": calibration.get("version"),
                "global_factor": calibration.get("global_factor"),
                "reference_tokenizer": (calibration.get("method") or {}).get("reference_tokenizer"),
                "applied": bool(calibration) and not counter.exact,
                "note": (
                    "calibrated_tokens = estimated_tokens / factor. The factor was measured against a "
                    "real BPE tokenizer; it narrows the error, it does not make the count exact."
                ),
            }
            if calibration else None
        ),
        "max_file_bytes": max_file_bytes,
        "ignored_directories": sorted(ignore_dirs),
        "ignored_globs": list(ignore_globs),
        "ignored_directory_globs": list(ignore_dir_globs),
        "totals": totals,
        "groups": group_rows,
        "largest_files": by_tokens[:top_n],
        "skills": sorted(skills, key=lambda item: (-item["body_tokens"], item["path"]))[:top_n],
        "findings": findings[:top_n],
        "skipped": skipped[:top_n],
        "skipped_count": len(skipped),
        "interpretation": [
            "estimated_tokens is the one-pass cost of the material on disk, not a project token budget.",
            "Repeated reads, retries, sub-agent fan-out and tool results are modelled by the task DAG, not here.",
        ],
    }
    if include_file_list:
        result["files"] = by_tokens
    if not counter.exact:
        result["warning"] = (
            "Counts are heuristic estimates. Use the target provider's official token counting endpoint "
            "before making any billing-grade claim."
        )
    return result

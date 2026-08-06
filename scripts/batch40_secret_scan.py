#!/usr/bin/env python3
"""Batch 40 credential leakage scan.

Pattern and entropy detection over the working tree, with an explicit allowlist
so every suppression carries a reason, an owner and an expiry rather than
silently disappearing.

A clean result does not prove there are no secrets — it proves these rules found
none in the scanned surface. The report states both, and the coverage numbers
are there so a reviewer can judge the false-negative surface.

Exit codes: 0 = no unallowlisted finding, 3 = findings, 2 = usage error.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import concurrent.futures
import hashlib
import json
import math
import os
import platform
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

SKIP_DIRECTORIES = {
    "node_modules", ".git", "_to_delete", "target", "build", "dist", ".next",
    "__pycache__", ".pytest_cache", ".ruff_cache", "venv", ".venv",
}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tgz", ".tar",
    ".jar", ".class", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".webm", ".lock",
}
MAX_BYTES = 2_000_000

# Ordered most specific first; the first matching rule wins for a given span.
PEM_HEADER = re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")
PEM_BODY = re.compile(r"^[A-Za-z0-9+/=]{40,}$")

RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("aws-access-key-id", "critical", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", "critical", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack-token", "critical", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", "high", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("stripe-secret-key", "critical", re.compile(r"\b[sr]k_(?:live|test)_[0-9A-Za-z]{16,}\b")),
    ("jwt", "high", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
    ("connection-string-password", "high",
     re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:([^\s/@]{6,})@", re.IGNORECASE)),
    ("assigned-credential", "medium",
     re.compile(r"(?i)\b(?:pass(?:word|wd)|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret)\b"
                r"\s*[:=]\s*['\"]([^'\"\s]{8,})['\"]")),
)

# Values that look like credentials but are structurally something else.
BENIGN = (
    re.compile(r"^sha\d{3}:[0-9a-f]+$"),
    re.compile(r"^\$\{[^}]+\}$"),                       # property placeholder
    re.compile(r"^\$\([^)]+\)$"),                       # shell substitution
    re.compile(r"^\{\{[^}]+\}\}$"),                     # template placeholder
    re.compile(r"^<[^>]+>$"),                           # <your-token-here>
    re.compile(r"(?i)^(?:changeme|replace_me|example|placeholder|redacted|dummy|sample|test|none|null|true|false)$"),
    re.compile(r"(?i)^(?:xxx+|yyy+|zzz+|\*+|\.+|-+|0+)$"),
    re.compile(r"(?i)^(?:process\.env|os\.environ|env)\."),
    # Credentials published by their vendor as documentation examples.
    re.compile(r"^(?:AKIAIOSFODNN7EXAMPLE|ASIAIOSFODNN7EXAMPLE|"
               r"wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY)$"),
)
ENTROPY_THRESHOLD = 4.2
ENTROPY_MIN_LENGTH = 24


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for character in value:
        counts[character] = counts.get(character, 0) + 1
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def is_benign(value: str) -> bool:
    if any(pattern.search(value) for pattern in BENIGN):
        return True
    if re.fullmatch(r"[0-9a-f]{32,}", value):
        return True  # a bare hex digest, not a credential
    if re.fullmatch(r"[0-9.\-:/ T]+", value):
        return True  # dates, versions, numeric ids
    return False


def redact(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}…{value[-2:]} (len={len(value)})"


def fingerprint(relative: str, rule: str, value: str) -> str:
    return "sha256:" + hashlib.sha256(f"{relative}|{rule}|{value}".encode()).hexdigest()[:32]


def looks_encoded(value: str) -> bool:
    """A base64 blob that decodes to text is usually config, not a key."""
    if len(value) % 4 or not re.fullmatch(r"[A-Za-z0-9+/=]+", value):
        return False
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return False
    try:
        decoded.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def scan_line(relative: str, number: int, line: str) -> list[dict]:
    findings = []
    # RULES is ordered most specific first, so the first rule to claim a value
    # wins. Without this a GitHub token assigned to a variable named `token`
    # reports twice — once as a token, once as a generic assignment.
    claimed: set[str] = set()
    for rule, severity, pattern in RULES:
        for match in pattern.finditer(line):
            value = match.group(1) if match.groups() else match.group(0)
            if is_benign(value) or value in claimed:
                continue
            claimed.add(value)
            findings.append({
                "rule": rule, "severity": severity, "path": relative, "line": number,
                "match": redact(value), "fingerprint": fingerprint(relative, rule, value),
                "detector": "pattern",
            })
            break  # one finding per rule per line is enough to act on
    if not findings:
        for candidate in re.findall(r"['\"]([A-Za-z0-9+/=_\-]{%d,})['\"]" % ENTROPY_MIN_LENGTH, line):
            if is_benign(candidate) or looks_encoded(candidate):
                continue
            if shannon_entropy(candidate) < ENTROPY_THRESHOLD:
                continue
            findings.append({
                "rule": "high-entropy-string", "severity": "advisory", "path": relative, "line": number,
                "match": redact(candidate),
                "fingerprint": fingerprint(relative, "high-entropy-string", candidate),
                "detector": "entropy",
            })
            break
    return findings


def scan_pem_blocks(relative: str, lines: list[str]) -> list[dict]:
    """Report a PEM header only when actual key material follows it.

    Source that parses, generates or documents keys mentions the header
    constantly. Requiring encoded body lines is what separates "this code knows
    what a private key looks like" from "a private key is checked in here".
    """
    findings = []
    for index, line in enumerate(lines):
        if not PEM_HEADER.search(line):
            continue
        body = 0
        for candidate in lines[index + 1: index + 6]:
            if PEM_BODY.fullmatch(candidate.strip()):
                body += 1
        if body >= 2:
            findings.append({
                "rule": "private-key-block", "severity": "critical", "path": relative,
                "line": index + 1, "match": "PEM header followed by key material",
                "fingerprint": fingerprint(relative, "private-key-block", str(index + 1)),
                "detector": "file-context",
            })
    return findings


def load_allowlist(path: Path | None) -> tuple[dict[str, dict], list[str]]:
    if path is None or not path.is_file():
        return {}, []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}, ["allowlist is not valid JSON and was ignored"]
    entries, problems = {}, []
    today = date.today()
    for entry in payload.get("allowed", []):
        if not isinstance(entry, dict):
            continue
        key = entry.get("fingerprint")
        if not key:
            problems.append("an allowlist entry has no fingerprint and was ignored")
            continue
        if not entry.get("reason") or not entry.get("owner"):
            problems.append(f"{key} has no reason or owner and was ignored")
            continue
        expiry = entry.get("expiresOn")
        if not expiry:
            problems.append(f"{key} has no expiresOn and was ignored")
            continue
        try:
            if date.fromisoformat(expiry) < today:
                problems.append(f"{key} expired on {expiry} and no longer suppresses its finding")
                continue
        except ValueError:
            problems.append(f"{key} has an invalid expiresOn and was ignored")
            continue
        entries[key] = entry
    return entries, problems


def merge_reports(directory: Path, output: Path | None) -> int:
    """Combine partial reports into one, deduplicating findings by fingerprint."""
    parts = sorted(directory.glob("*.json"))
    if not parts:
        print(f"ERROR: no partial reports found in {directory}", file=sys.stderr)
        return 2
    findings: dict[str, dict] = {}
    suppressed: dict[str, dict] = {}
    roots: set[str] = set()
    missing_roots: set[str] = set()
    problems: set[str] = set()
    scanned = binary = large = considered = 0
    started = finished = None
    tool_digest = rule_count = entropy = None
    for part in parts:
        try:
            report = json.loads(part.read_text(encoding="utf-8"))
        except (ValueError, json.JSONDecodeError):
            problems.add(f"{part.name} is not valid JSON and was excluded from the merge")
            continue
        if report.get("check") != "batch40-secret-scan":
            continue
        coverage = report.get("coverage", {})
        scanned += coverage.get("filesScanned", 0)
        binary += coverage.get("filesSkippedBinaryOrUndecodable", 0)
        large += coverage.get("filesSkippedTooLarge", 0)
        considered += coverage.get("filesConsidered", 0)
        roots.update(coverage.get("roots", []))
        missing_roots.update(coverage.get("rootsNotFound", []))
        rule_count = coverage.get("ruleCount", rule_count)
        entropy = coverage.get("entropyThreshold", entropy)
        tool_digest = report.get("toolDigest", tool_digest)
        problems.update(report.get("allowlist", {}).get("problems", []))
        for finding in report.get("findings", []):
            findings[finding["fingerprint"]] = finding
        for finding in report.get("suppressed", []):
            suppressed[finding["fingerprint"]] = finding
        for key, value in (("startedAt", "started"), ("finishedAt", "finished")):
            stamp = report.get(key)
            if not stamp:
                continue
            if value == "started":
                started = stamp if started is None or stamp < started else started
            else:
                finished = stamp if finished is None or stamp > finished else finished

    active = sorted(findings.values(), key=lambda item: (item["path"], item["line"], item["rule"]))
    by_severity: dict[str, int] = {}
    for finding in active:
        by_severity[finding["severity"]] = by_severity.get(finding["severity"], 0) + 1
    merged = {
        "check": "batch40-secret-scan",
        "batch": 40,
        "mergedFrom": [part.name for part in parts],
        "startedAt": started,
        "finishedAt": finished,
        "replayCommand": "python3 scripts/batch40_secret_scan.py --root <root> --output <partial>; "
                         "python3 scripts/batch40_secret_scan.py --merge <partial-dir> --output <report>",
        "toolDigest": tool_digest,
        "pythonVersion": platform.python_version(),
        "coverage": {
            "filesScanned": scanned,
            "filesSkippedBinaryOrUndecodable": binary,
            "filesSkippedTooLarge": large,
            "filesConsidered": considered,
            "ruleCount": rule_count,
            "entropyThreshold": entropy,
            "roots": sorted(roots),
            "rootsNotFound": sorted(missing_roots),
            "prunedDirectoryNames": sorted(SKIP_DIRECTORIES),
        },
        "allowlist": {"activeEntries": None, "problems": sorted(problems),
                      "suppressedFindings": len(suppressed)},
        "totals": {
            "findingCount": len(active),
            "actionableFindingCount": sum(1 for item in active if item["severity"] != "advisory"),
            "advisoryFindingCount": sum(1 for item in active if item["severity"] == "advisory"),
            "bySeverity": dict(sorted(by_severity.items())),
        },
        "metrics": {
            "secretLeakCount": float(sum(1 for item in active if item["severity"] != "advisory")),
            "advisoryEntropyHits": float(sum(1 for item in active if item["severity"] == "advisory")),
        },
        "limitations": [
            "secretLeakCount counts actionable findings only; high-entropy strings are advisory and require triage without gating.",
            "Merged from chunked runs; only the roots listed under coverage were scanned and anything outside them was not examined.",
            "Scans the working tree only; git history is not examined.",
            "Detection is rule and entropy based; a zero result bounds risk, it does not eliminate it.",
            "No secret is validated against its provider, so a finding may be an already-revoked credential.",
        ],
        "findings": active,
        "suppressed": sorted(suppressed.values(), key=lambda item: item["fingerprint"]),
    }
    payload = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        print(f"wrote {output}")
    else:
        print(payload)
    print(f"merged={len(parts)} roots={len(roots)} scanned={scanned} findings={len(active)}", file=sys.stderr)
    actionable = [item for item in active if item["severity"] != "advisory"]
    return 3 if actionable else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--root", action="append", default=[],
                        help="repository-relative root to scan; repeatable. "
                             "Defaults to the whole repository. Whatever is passed is "
                             "recorded in the report so the coverage boundary is reviewable.")
    parser.add_argument("--allowlist", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--merge", type=Path,
                        help="merge the partial reports in this directory into one report. "
                             "Chunked runs are sometimes the only way to scan a large tree "
                             "within a session limit; merging keeps the result a single "
                             "reviewable artifact instead of a pile of fragments.")
    parser.add_argument("--jobs", type=int, default=16,
                        help="parallel file readers; the scan is I/O bound, not CPU bound")
    parser.add_argument("--progress", action="store_true", help="emit a heartbeat to stderr")
    arguments = parser.parse_args()

    if arguments.merge is not None:
        return merge_reports(arguments.merge, arguments.output)

    repo = arguments.repo.resolve()
    if not repo.is_dir():
        print(f"ERROR: {repo} is not a directory", file=sys.stderr)
        return 2
    started = datetime.now(timezone.utc)
    allowlist, allowlist_problems = load_allowlist(arguments.allowlist)

    # Prune while descending. Filtering rglob's output still walks node_modules,
    # which turns a seconds-long scan into a minutes-long one.
    roots = arguments.root or ["."]
    missing_roots = [name for name in roots if not (repo / name).is_dir()]
    candidates: list[Path] = []
    for name in roots:
        base = repo / name
        if not base.is_dir():
            continue
        for directory, subdirectories, filenames in os.walk(base):
            subdirectories[:] = sorted(item for item in subdirectories if item not in SKIP_DIRECTORIES)
            candidates.extend(Path(directory) / filename for filename in sorted(filenames))
    candidates = sorted(set(candidates))

    def scan_file(path: Path) -> tuple[str, list[dict]]:
        """Return an outcome tag plus findings. Reading dominates the cost."""
        if not path.is_file() or path.is_symlink():
            return "ignored", []
        if path.suffix.lower() in SKIP_SUFFIXES:
            return "binary", []
        try:
            if path.stat().st_size > MAX_BYTES:
                return "large", []
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return "binary", []
        relative = path.relative_to(repo).as_posix()
        lines = text.splitlines()
        found: list[dict] = []
        for number, line in enumerate(lines, start=1):
            found.extend(scan_line(relative, number, line))
        found.extend(scan_pem_blocks(relative, lines))
        return "scanned", found

    findings: list[dict] = []
    scanned = skipped_binary = skipped_large = completed = 0
    heartbeat = max(1, len(candidates) // 20)
    # The work is I/O bound. On a network or bridged mount a serial read of tens
    # of thousands of files takes minutes while the regex work takes seconds, so
    # the reads are overlapped and progress is reported rather than silent.
    with concurrent.futures.ThreadPoolExecutor(max_workers=arguments.jobs) as pool:
        for outcome, found in pool.map(scan_file, candidates):
            completed += 1
            if outcome == "scanned":
                scanned += 1
                findings.extend(found)
            elif outcome == "binary":
                skipped_binary += 1
            elif outcome == "large":
                skipped_large += 1
            if arguments.progress and completed % heartbeat == 0:
                print(f"progress: {completed}/{len(candidates)} files, {scanned} scanned",
                      file=sys.stderr, flush=True)
    findings.sort(key=lambda item: (item["path"], item["line"], item["rule"]))

    active, suppressed = [], []
    for finding in findings:
        entry = allowlist.get(finding["fingerprint"])
        if entry:
            suppressed.append(finding | {"allowlistReason": entry["reason"], "allowlistOwner": entry["owner"]})
        else:
            active.append(finding)

    by_severity: dict[str, int] = {}
    for finding in active:
        by_severity[finding["severity"]] = by_severity.get(finding["severity"], 0) + 1

    finished = datetime.now(timezone.utc)
    report = {
        "check": "batch40-secret-scan",
        "batch": 40,
        "startedAt": started.isoformat().replace("+00:00", "Z"),
        "finishedAt": finished.isoformat().replace("+00:00", "Z"),
        "replayCommand": "python3 scripts/batch40_secret_scan.py --allowlist config/secret-scan-allowlist.json",
        "toolDigest": "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "pythonVersion": platform.python_version(),
        "coverage": {
            "filesScanned": scanned,
            "filesSkippedBinaryOrUndecodable": skipped_binary,
            "filesSkippedTooLarge": skipped_large,
            "ruleCount": len(RULES) + 1,
            "filesConsidered": len(candidates),
            "roots": sorted(roots),
            "rootsNotFound": sorted(missing_roots),
            "prunedDirectoryNames": sorted(SKIP_DIRECTORIES),
            "entropyThreshold": ENTROPY_THRESHOLD,
        },
        "allowlist": {
            "activeEntries": len(allowlist),
            "problems": allowlist_problems,
            "suppressedFindings": len(suppressed),
        },
        "totals": {
            "findingCount": len(active),
            "actionableFindingCount": sum(1 for item in active if item["severity"] != "advisory"),
            "advisoryFindingCount": sum(1 for item in active if item["severity"] == "advisory"),
            "bySeverity": dict(sorted(by_severity.items())),
        },
        "metrics": {
            "secretLeakCount": float(sum(1 for item in active if item["severity"] != "advisory")),
            "advisoryEntropyHits": float(sum(1 for item in active if item["severity"] == "advisory")),
        },
        "limitations": [
            "secretLeakCount counts actionable findings only. High-entropy strings are reported as advisory because on a large front-end and code-generation surface they are overwhelmingly hashes, ids and encoded assets; they still require triage but do not gate.",
            "Scans the working tree only; git history is not examined, so a credential removed in a later commit is not detected.",
            "Detection is rule and entropy based, so a credential that matches no rule and has low entropy is not found. A zero result bounds risk, it does not eliminate it.",
            "Binary, undecodable and oversized files are skipped, and the pruned directory names and scanned roots are listed under coverage; anything outside those roots was not examined.",
            "No secret is validated against its provider, so a finding may be an already-revoked credential.",
        ],
        "findings": active,
        "suppressed": suppressed,
    }

    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload, encoding="utf-8")
        print(f"wrote {arguments.output}")
    else:
        print(payload)
    for problem in allowlist_problems:
        print(f"ALLOWLIST: {problem}", file=sys.stderr)
    for finding in active[:20]:
        print(f"FINDING [{finding['severity']}/{finding['rule']}] "
              f"{finding['path']}:{finding['line']} {finding['match']}", file=sys.stderr)
    actionable = [item for item in active if item["severity"] != "advisory"]
    print(f"scanned={scanned} actionable={len(actionable)} advisory={len(active) - len(actionable)} "
          f"suppressed={len(suppressed)}", file=sys.stderr)
    return 3 if actionable else 0


if __name__ == "__main__":
    raise SystemExit(main())

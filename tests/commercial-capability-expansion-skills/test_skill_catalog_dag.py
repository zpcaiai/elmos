"""Tests for skill catalog frontmatter, kernel groupings, and DAG validation."""

from __future__ import annotations

from collections import defaultdict, deque
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = ROOT / "skills/elmos-commercial-capability-expansion-skills-v2.0.0"

EXPECTED_KERNEL_COUNTS = {
    "K1-skill-runtime": 10,
    "K2-repository-intelligence": 10,
    "K3-transformation": 10,
    "K4-build-execution": 9,
    "K5-verification": 14,
    "K6-security-governance": 10,
    "K7-database-data": 10,
    "K8-observability-evolution": 12,
}


@pytest.fixture
def manifest_data():
    return json.loads((PACKAGE_DIR / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_skill_counts_and_kernels(manifest_data):
    skills = manifest_data.get("skills", [])
    assert len(skills) == 85

    counts = defaultdict(int)
    seen_ids = set()
    for s in skills:
        sid = s["id"]
        assert sid not in seen_ids, f"Duplicate skill ID: {sid}"
        seen_ids.add(sid)

        kernel = s["kernel"]
        assert kernel in EXPECTED_KERNEL_COUNTS, f"Unknown kernel: {kernel}"
        counts[kernel] += 1

        assert s.get("priority") in ("P0", "P1", "P2")
        assert len(s.get("objective", "")) > 10
        assert len(s.get("inspirations", [])) >= 1

        path = PACKAGE_DIR / s["path"]
        assert path.is_file(), f"Missing skill file: {path}"
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n"), f"Missing frontmatter marker: {path}"
        assert f"name: {sid}" in text, f"Frontmatter name mismatch: {path}"

    for k, expected_cnt in EXPECTED_KERNEL_COUNTS.items():
        assert counts[k] == expected_cnt, f"Kernel {k} expected {expected_cnt}, got {counts[k]}"


def test_cross_kernel_dag_acyclicity(manifest_data):
    skills = manifest_data.get("skills", [])
    skill_ids = {s["id"] for s in skills}

    kernel_order = [
        "K1-skill-runtime",
        "K2-repository-intelligence",
        "K3-transformation",
        "K4-build-execution",
        "K5-verification",
        "K6-security-governance",
        "K7-database-data",
        "K8-observability-evolution",
    ]

    skills_by_kernel = defaultdict(list)
    for s in skills:
        skills_by_kernel[s["kernel"]].append(s["id"])

    adj = defaultdict(list)
    in_degree = defaultdict(int)

    for i in range(len(kernel_order) - 1):
        k_curr = kernel_order[i]
        k_next = kernel_order[i + 1]
        for src in skills_by_kernel[k_curr][:2]:
            for dst in skills_by_kernel[k_next][:2]:
                adj[src].append(dst)
                in_degree[dst] += 1

    queue = deque([sid for sid in skill_ids if in_degree[sid] == 0])
    visited = 0
    while queue:
        u = queue.popleft()
        visited += 1
        for v in adj.get(u, []):
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    assert visited == len(skill_ids), "Cycle detected in skill capability DAG"

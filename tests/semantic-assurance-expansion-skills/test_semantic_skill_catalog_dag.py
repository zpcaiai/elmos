"""Tests for skill catalog frontmatter, batch distribution, and DAG validation."""

from __future__ import annotations

from collections import defaultdict, deque
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = ROOT / "skills/elmos-semantic-assurance-expansion-skills-v1.0.0"

EXPECTED_BATCH_COUNTS = {
    "J": 16,
    "K": 14,
    "L": 16,
    "M": 18,
    "N": 16,
    "O": 14,
    "P": 12,
    "Q": 14,
    "R": 12,
}


@pytest.fixture
def manifest_data():
    return json.loads((PACKAGE_DIR / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_skill_counts_and_batches(manifest_data):
    skills = manifest_data.get("skills", [])
    assert len(skills) == 132

    counts = defaultdict(int)
    seen_ids = set()
    seen_names = set()

    for s in skills:
        sid = s["id"]
        name = s["name"]
        assert sid not in seen_ids, f"Duplicate skill ID: {sid}"
        assert name not in seen_names, f"Duplicate skill name: {name}"
        seen_ids.add(sid)
        seen_names.add(name)

        batch = s["batch"]
        assert batch in EXPECTED_BATCH_COUNTS, f"Unknown batch: {batch}"
        counts[batch] += 1

        assert len(s.get("description", "")) > 10
        assert s.get("risk") in ("critical", "high", "medium", "low")

        path = PACKAGE_DIR / s["path"]
        assert path.is_file(), f"Missing skill file: {path}"
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n"), f"Missing frontmatter marker: {path}"
        assert f"name: {name}" in text, f"Frontmatter name mismatch: {path}"

    for b, expected_cnt in EXPECTED_BATCH_COUNTS.items():
        assert counts[b] == expected_cnt, f"Batch {b} expected {expected_cnt}, got {counts[b]}"


def test_cross_batch_dag_acyclicity(manifest_data):
    skills = manifest_data.get("skills", [])
    skill_names = {s["name"] for s in skills}

    batch_order = ["J", "K", "L", "M", "N", "O", "P", "Q", "R"]

    skills_by_batch = defaultdict(list)
    for s in skills:
        skills_by_batch[s["batch"]].append(s["name"])

    adj = defaultdict(list)
    in_degree = defaultdict(int)

    for i in range(len(batch_order) - 1):
        b_curr = batch_order[i]
        b_next = batch_order[i + 1]
        for src in skills_by_batch[b_curr][:2]:
            for dst in skills_by_batch[b_next][:2]:
                adj[src].append(dst)
                in_degree[dst] += 1

    queue = deque([name for name in skill_names if in_degree[name] == 0])
    visited = 0
    while queue:
        u = queue.popleft()
        visited += 1
        for v in adj.get(u, []):
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    assert visited == len(skill_names), "Cycle detected in semantic assurance skill DAG"

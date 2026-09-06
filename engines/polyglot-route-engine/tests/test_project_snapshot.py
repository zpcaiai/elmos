from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import elmos_polyglot_route.project_graph as graphs


def test_materialization_matches_public_graph_without_recapturing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "math.py").write_text("def add(x: int, y: int) -> int:\n    return x + y\n")
    (tmp_path / "package.json").write_text('{"name":"snapshot","dependencies":{"other":"1.0"}}')
    expected = graphs.build_project_graph(tmp_path, "local:snapshot")
    snapshot = graphs.capture_project_snapshot(tmp_path)

    def forbidden_read(path: Path | str) -> bytes:
        pytest.fail(f"materialization reread source bytes: {path}")

    monkeypatch.setattr(graphs, "_stable_read", forbidden_read)
    for _ in range(3):
        assert graphs.materialize_project_graph(snapshot, "local:snapshot") == expected
        assert graphs.verify_project_snapshot(snapshot)


@pytest.mark.parametrize("change", ["same-size", "added", "removed", "symlink", "ignored"])
def test_snapshot_detects_live_drift(tmp_path: Path, change: str) -> None:
    source = tmp_path / "data.json"
    source.write_text('{"x":1}')
    before = source.stat()
    snapshot = graphs.capture_project_snapshot(tmp_path)
    if change == "same-size":
        source.write_text('{"x":2}')
        os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    elif change == "added":
        (tmp_path / "unselected.txt").write_text("new")
    elif change == "removed":
        source.unlink()
    elif change == "symlink":
        source.unlink()
        source.symlink_to("missing")
    else:
        (tmp_path / "node_modules").mkdir()
    assert not graphs.verify_project_snapshot(snapshot)


def test_parallel_snapshots_remain_repository_scoped(tmp_path: Path) -> None:
    roots = [tmp_path / str(index) for index in range(8)]
    for index, root in enumerate(roots):
        root.mkdir()
        (root / "data.json").write_text(f'{{"tenant":{index}}}')
    with ThreadPoolExecutor(max_workers=4) as pool:
        snapshots = list(pool.map(graphs.capture_project_snapshot, roots))
    assert len({snapshot.files[0].sha256 for snapshot in snapshots}) == len(roots)
    assert all(graphs.verify_project_snapshot(snapshot) for snapshot in snapshots)


def test_verification_refuses_fifo_without_blocking(tmp_path: Path) -> None:
    source = tmp_path / "data.json"
    source.write_text("{}")
    snapshot = graphs.capture_project_snapshot(tmp_path)
    source.unlink()
    os.mkfifo(source)
    assert not graphs.verify_project_snapshot(snapshot)

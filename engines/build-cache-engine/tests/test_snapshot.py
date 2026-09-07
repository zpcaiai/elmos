"""SNAP-001..003: deterministic snapshots, normalisation and rename detection."""

from __future__ import annotations

import shutil
from pathlib import Path

from elmos_build_cache.snapshot import (
    FileKind,
    SnapshotPolicy,
    diff_snapshots,
    impacted_modules,
    take_snapshot,
)


def build_repo(root: Path) -> Path:
    (root / "src" / "app").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "src" / "app" / "Main.java").write_text("class Main { void f(){} }\n", encoding="utf-8")
    (root / "src" / "app" / "Util.java").write_text("class Util {}\n", encoding="utf-8")
    (root / "src" / "vendor").mkdir()
    (root / "src" / "vendor" / "Third.java").write_text("class Third {}\n", encoding="utf-8")
    (root / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    (root / "go.sum").write_text("dep v1\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    return root


def test_snap_001_same_repository_different_absolute_paths(tmp_path: Path) -> None:
    """SNAP-001: identity depends on content, never on where it lives."""
    first = build_repo(tmp_path / "checkout-a")
    second = tmp_path / "some" / "deeply" / "nested" / "checkout-b"
    second.parent.mkdir(parents=True)
    shutil.copytree(first, second)
    assert take_snapshot(first).root_digest == take_snapshot(second).root_digest


def test_snap_001_windows_style_separators_normalise(tmp_path: Path) -> None:
    snapshot = take_snapshot(build_repo(tmp_path / "repo"))
    assert all("\\" not in entry.logical_path for entry in snapshot.entries)


def test_snap_002_formatting_only_change(tmp_path: Path) -> None:
    """SNAP-002: raw digest moves, normalised digest does not."""
    root = build_repo(tmp_path / "repo")
    before = take_snapshot(root)
    (root / "src" / "app" / "Main.java").write_text(
        "class Main { void f(){} }\r\n", encoding="utf-8"
    )
    after = take_snapshot(root)
    delta = diff_snapshots(before, after)

    assert delta.formatting_only == ("src/app/Main.java",)
    assert delta.modified == ()
    assert before.root_digest != after.root_digest
    entry_before = before.by_path()["src/app/Main.java"]
    entry_after = after.by_path()["src/app/Main.java"]
    assert entry_before.raw_digest != entry_after.raw_digest
    assert entry_before.normalized_digest == entry_after.normalized_digest


def test_snap_003_rename_detected_and_unrelated_subtrees_stable(tmp_path: Path) -> None:
    """SNAP-003: renames are content identity, not path guessing."""
    root = build_repo(tmp_path / "repo")
    before = take_snapshot(root)
    (root / "src" / "app" / "Util.java").rename(root / "src" / "app" / "Helper.java")
    after = take_snapshot(root)
    delta = diff_snapshots(before, after)

    assert delta.renamed == (("src/app/Util.java", "src/app/Helper.java"),)
    assert delta.added == () and delta.removed == ()
    assert before.by_path()["pom.xml"].raw_digest == after.by_path()["pom.xml"].raw_digest
    assert "src/app" in impacted_modules(delta)


def test_classification_and_lockfiles(tmp_path: Path) -> None:
    snapshot = take_snapshot(build_repo(tmp_path / "repo"))
    kinds = {entry.logical_path: entry.kind for entry in snapshot.entries}
    assert kinds["src/vendor/Third.java"] == FileKind.VENDOR
    assert kinds["go.sum"] == FileKind.DEPENDENCY
    assert kinds[".env"] == FileKind.SECRET
    assert set(snapshot.lockfile_digests) == {"go.sum"}
    assert not any(path.startswith(".git/") for path in snapshot.by_path())


def test_policy_version_participates_in_identity(tmp_path: Path) -> None:
    root = build_repo(tmp_path / "repo")
    strict = SnapshotPolicy(strip_trailing_whitespace=True)
    assert take_snapshot(root).policy_digest != take_snapshot(root, strict).policy_digest


def test_symlink_is_recorded_not_followed(tmp_path: Path) -> None:
    root = build_repo(tmp_path / "repo")
    (root / "src" / "link.java").symlink_to("/etc/hostname")
    snapshot = take_snapshot(root)
    entry = snapshot.by_path()["src/link.java"]
    assert entry.is_symlink and entry.symlink_target == "/etc/hostname"

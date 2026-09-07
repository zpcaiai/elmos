"""Sandbox overlay workspaces, on the filesystem rather than in principle.

`overlay.py` was the one module in this package exercised only through its
callers. What follows tests it directly, and where a claim is about the
*platform* -- copy-on-write breaking, a read-only source layer, a kernel
overlayfs underneath the workspace -- the test makes the platform actually do
it and reads back inode numbers and link counts rather than trusting the
bookkeeping.

Three properties carry the module:

1. **A write can never reach the base.** Projection may hardlink; the first
   write must break the link. The test compares ``st_ino`` before and after and
   verifies the source bytes are untouched.
2. **The source layer is read-only.** A stage that edits its own input would
   poison the next run's fingerprint, so the attempt fails at the filesystem.
3. **A stage sees only declared mounts.** Credential directories and host
   system paths are refused by name, not by hope.

The kernel-overlayfs test needs ``CAP_SYS_ADMIN`` and skips loudly without it.
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

import elmos_build_cache.overlay as overlay_module
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.config import WorkspaceConfig
from elmos_build_cache.errors import ContractViolation, PermissionDenied, QuotaExceeded, UnsafePath
from elmos_build_cache.overlay import (
    DENIED_BASENAMES,
    Mount,
    OverlayWorkspace,
    SandboxPolicy,
    detect_strategy,
)

CONTENT = {
    "src/main/java/App.java": b"public class App { public static void main(String[] a) {} }\n",
    "src/main/resources/app.properties": b"name=demo\n",
    "README.md": b"# demo\n",
}


@pytest.fixture
def cas(tmp_path: Path) -> ContentAddressableStore:
    return ContentAddressableStore(tmp_path / "cas")


@pytest.fixture
def entries(cas: ContentAddressableStore) -> list[tuple[str, str, int]]:
    return [(path, cas.put_bytes(payload), 0o644) for path, payload in CONTENT.items()]


def make_workspace(root: Path, cas: ContentAddressableStore, **kwargs: object) -> OverlayWorkspace:
    return OverlayWorkspace(
        root / "source", root / "overlay", root / "scratch", cas, **kwargs  # type: ignore[arg-type]
    )


# ==========================================================================
# strategy probe
# ==========================================================================
def test_the_strategy_is_probed_once_against_the_real_filesystem(tmp_path: Path) -> None:
    strategy = detect_strategy(tmp_path)
    assert strategy in ("reflink", "hardlink-cow", "copy")
    # Whatever it chose, the probe must leave nothing behind.
    assert not list(tmp_path.glob(".elmos-cow-*"))


def test_the_probe_survives_a_filesystem_that_supports_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("elmos_build_cache.overlay.try_reflink", lambda source, destination: False)

    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("hardlinks unsupported")

    monkeypatch.setattr(os, "link", refuse)
    assert detect_strategy(tmp_path) == "copy"


def test_a_reflink_capable_filesystem_is_used_when_it_reports_success(
    tmp_path: Path, cas: ContentAddressableStore, entries, monkeypatch: pytest.MonkeyPatch
) -> None:
    """APFS and Btrfs take this branch; this Linux CI filesystem does not."""
    calls: list[tuple[Path, Path]] = []

    def fake_reflink(source: Path, destination: Path) -> bool:
        calls.append((source, destination))
        shutil.copyfile(source, destination)
        return True

    monkeypatch.setattr("elmos_build_cache.overlay.try_reflink", fake_reflink)
    workspace = make_workspace(tmp_path, cas, strategy="reflink")
    workspace.materialize_source(entries)
    stats = workspace.populate_overlay()
    assert stats.strategy == "reflink"
    assert len(calls) == len(CONTENT)
    assert stats.linked == len(CONTENT) and stats.copied == 0


# ==========================================================================
# copy-on-write, measured in inodes
# ==========================================================================
def test_projection_shares_storage_and_the_first_write_breaks_it(
    tmp_path: Path, cas: ContentAddressableStore, entries
) -> None:
    workspace = make_workspace(tmp_path, cas, strategy="hardlink-cow")
    workspace.materialize_source(entries)
    workspace.populate_overlay()

    logical = "README.md"
    source = workspace.source_root / logical
    overlay = workspace.overlay_root / logical
    assert overlay.stat().st_ino == source.stat().st_ino, "projection did not share storage"
    assert overlay.stat().st_nlink >= 2

    before = overlay.stat().st_ino
    target = workspace.open_for_write(logical)
    assert target.stat().st_ino != before, "copy-on-write was not broken"
    target.write_bytes(b"# rewritten\n")

    assert source.read_bytes() == CONTENT[logical], "the base was mutated through the overlay"
    assert source.stat().st_nlink == 1


def test_writing_without_breaking_the_link_would_corrupt_the_base(
    tmp_path: Path, cas: ContentAddressableStore, entries
) -> None:
    """Why ``open_for_write`` exists, demonstrated rather than asserted."""
    workspace = make_workspace(tmp_path, cas, strategy="hardlink-cow")
    workspace.materialize_source(entries)
    workspace.populate_overlay()

    overlay = workspace.overlay_root / "README.md"
    os.chmod(overlay, 0o644)
    with overlay.open("r+b") as handle:  # deliberately bypassing the API
        handle.write(b"X")
    assert (workspace.source_root / "README.md").read_bytes().startswith(b"X")


def test_a_copy_strategy_shares_nothing(
    tmp_path: Path, cas: ContentAddressableStore, entries
) -> None:
    workspace = make_workspace(tmp_path, cas, strategy="copy")
    workspace.materialize_source(entries)
    stats = workspace.populate_overlay()
    assert stats.copied == len(CONTENT) and stats.linked == 0
    for logical in CONTENT:
        assert (workspace.overlay_root / logical).stat().st_ino != (
            workspace.source_root / logical
        ).stat().st_ino


def test_open_for_write_is_idempotent_and_reopens_a_private_file(
    tmp_path: Path, cas: ContentAddressableStore, entries
) -> None:
    workspace = make_workspace(tmp_path, cas, strategy="hardlink-cow")
    workspace.materialize_source(entries)
    workspace.populate_overlay()
    first = workspace.open_for_write("README.md")
    first.write_bytes(b"one\n")
    inode = first.stat().st_ino
    second = workspace.open_for_write("README.md")
    assert second.stat().st_ino == inode, "an unshared file was copied again"
    assert second.read_bytes() == b"one\n"


def test_open_for_write_creates_a_path_that_did_not_exist(
    tmp_path: Path, cas: ContentAddressableStore, entries
) -> None:
    workspace = make_workspace(tmp_path, cas, strategy="hardlink-cow")
    workspace.materialize_source(entries)
    target = workspace.open_for_write("generated/new/Deep.java")
    target.write_bytes(b"new\n")
    assert target.is_file() and target.parent.is_dir()


# ==========================================================================
# the source layer is genuinely read-only
# ==========================================================================
def test_the_materialised_source_is_read_only_on_disk(
    tmp_path: Path, cas: ContentAddressableStore, entries
) -> None:
    workspace = make_workspace(tmp_path, cas)
    workspace.materialize_source(entries)
    for logical in CONTENT:
        path = workspace.source_root / logical
        assert not stat.S_IMODE(path.stat().st_mode) & 0o222, logical
    if os.geteuid() == 0:
        pytest.skip("root ignores the write bit; the mode assertion above is the check")
    with pytest.raises(PermissionError):
        (workspace.source_root / "README.md").write_bytes(b"tampered")


def test_materialisation_verifies_digests_on_the_way_in(
    tmp_path: Path, cas: ContentAddressableStore
) -> None:
    from elmos_build_cache.errors import NotFound

    workspace = make_workspace(tmp_path, cas)
    with pytest.raises((NotFound, KeyError, OSError)):
        workspace.materialize_source([("a.txt", "sha256:" + "0" * 64, 0o644)])


# ==========================================================================
# mounts
# ==========================================================================
@pytest.mark.parametrize(
    "denied",
    [
        "/etc",
        "/etc/passwd",
        "/root",
        "/proc/self",
        "/sys/kernel",
        "/dev/null",
        "/home/someone",
        "/Users/someone",
    ],
)
def test_host_system_paths_cannot_be_mounted(denied: str) -> None:
    """A host system path is refused however *this* platform spells it.

    ``SandboxPolicy.check`` matches ``DENIED_MOUNT_PREFIXES`` against the
    *resolved* path, so the deny list has to carry every platform's spelling of
    the same location. It already does: ``/private/etc`` is there because macOS
    resolves ``/etc`` through a symlink, and ``/Users`` because that is where
    macOS keeps the home directories ``/home`` holds on linux -- so both
    spellings of "another user's home directory" are asserted on both
    platforms rather than one of them being skipped away. Mounting a stranger's
    home into a build stage is exactly as dangerous on darwin as on linux, so a
    failure here is a hole in the deny list, not a platform quirk; the message
    names the resolved path that got through so the missing prefix is obvious.
    """
    try:
        accepted = SandboxPolicy().check(Path(denied))
    except PermissionDenied:
        return
    pytest.fail(
        f"{denied} resolved to {accepted} on {platform.system()} and SandboxPolicy accepted it: "
        f"DENIED_MOUNT_PREFIXES (overlay.py) does not cover this platform's spelling of that path"
    )


@pytest.mark.parametrize("secret", sorted(DENIED_BASENAMES))
def test_credential_directories_cannot_be_mounted(tmp_path: Path, secret: str) -> None:
    path = tmp_path / "workspace" / secret / "config"
    path.parent.mkdir(parents=True)
    path.write_text("secret", encoding="utf-8")
    # Even inside an otherwise allowed root: the basename is the rule.
    policy = SandboxPolicy(allowed_roots=[tmp_path])
    with pytest.raises(PermissionDenied):
        policy.check(path)


def test_an_explicitly_allowed_root_is_accepted(tmp_path: Path) -> None:
    allowed = tmp_path / "toolchain"
    allowed.mkdir()
    policy = SandboxPolicy(allowed_roots=[allowed])
    assert policy.check(allowed / "bin" / "javac") == (allowed / "bin" / "javac").resolve()


def test_extra_mounts_are_checked_and_names_must_be_unique(
    tmp_path: Path, cas: ContentAddressableStore
) -> None:
    workspace = make_workspace(tmp_path, cas)
    toolchain = tmp_path / "toolchain"
    toolchain.mkdir()
    workspace.policy = SandboxPolicy(
        allowed_roots=[workspace.source_root, workspace.overlay_root, workspace.scratch_root, toolchain]
    )
    mounts = workspace.mounts([Mount("toolchain", toolchain, writable=False)])
    assert [mount.name for mount in mounts] == ["source", "overlay", "scratch", "toolchain"]

    with pytest.raises(ContractViolation, match="duplicate mount"):
        workspace.mounts([Mount("source", toolchain, writable=False)])
    with pytest.raises(PermissionDenied):
        workspace.mounts([Mount("etc", Path("/etc"), writable=False)])


def test_writes_are_refused_outside_writable_mounts(
    tmp_path: Path, cas: ContentAddressableStore, entries
) -> None:
    workspace = make_workspace(tmp_path, cas)
    workspace.materialize_source(entries)
    mounts = workspace.mounts()

    assert workspace.assert_writable(mounts, workspace.overlay_root / "x.java").name == "overlay"
    assert workspace.assert_writable(mounts, workspace.scratch_root / "tmp.o").name == "scratch"
    with pytest.raises(PermissionDenied, match="read-only"):
        workspace.assert_writable(mounts, workspace.source_root / "README.md")
    with pytest.raises(UnsafePath):
        workspace.assert_writable(mounts, tmp_path / "elsewhere" / "out.java")


# ==========================================================================
# quotas, export, scratch
# ==========================================================================
def test_the_byte_quota_stops_projection(tmp_path: Path, cas: ContentAddressableStore) -> None:
    big = [("big.bin", cas.put_bytes(b"x" * 200_000), 0o644)]
    config = WorkspaceConfig(quota_gb_per_run=0)
    workspace = make_workspace(tmp_path, cas, config=config, strategy="copy")
    workspace.materialize_source(big)
    with pytest.raises(QuotaExceeded):
        workspace.populate_overlay()


def test_the_file_count_quota_stops_projection(
    tmp_path: Path, cas: ContentAddressableStore, entries
) -> None:
    config = WorkspaceConfig(max_files_per_run=1)
    workspace = make_workspace(tmp_path, cas, config=config, strategy="copy")
    workspace.materialize_source(entries)
    with pytest.raises(QuotaExceeded):
        workspace.populate_overlay()


def test_export_separates_declared_outputs_from_leftovers(
    tmp_path: Path, cas: ContentAddressableStore, entries
) -> None:
    workspace = make_workspace(tmp_path, cas)
    workspace.materialize_source(entries)
    workspace.populate_overlay()
    workspace.open_for_write("generated/Out.cs").write_bytes(b"// generated\n")
    workspace.open_for_write("generated/scratch.tmp").write_bytes(b"junk\n")

    exported, undeclared = workspace.export(["generated/Out.cs"])
    assert exported == ["generated/Out.cs"]
    assert "generated/scratch.tmp" in undeclared
    assert "README.md" in undeclared


def test_scratch_is_disposable(tmp_path: Path, cas: ContentAddressableStore) -> None:
    workspace = make_workspace(tmp_path, cas)
    (workspace.scratch_root / "deep").mkdir(parents=True)
    (workspace.scratch_root / "deep" / "a.o").write_bytes(b"object")
    (workspace.scratch_root / "b.o").write_bytes(b"object")
    removed = workspace.discard_scratch()
    assert removed == 2
    assert list(workspace.scratch_root.rglob("*")) == []


def test_populate_can_project_a_subset(
    tmp_path: Path, cas: ContentAddressableStore, entries
) -> None:
    workspace = make_workspace(tmp_path, cas, strategy="copy")
    workspace.materialize_source(entries)
    stats = workspace.populate_overlay(["README.md"])
    assert stats.files == 1
    assert [p.name for p in workspace.overlay_root.rglob("*") if p.is_file()] == ["README.md"]


def test_describe_reports_the_platform_and_the_mounts(
    tmp_path: Path, cas: ContentAddressableStore, entries
) -> None:
    workspace = make_workspace(tmp_path, cas)
    workspace.materialize_source(entries)
    workspace.populate_overlay()
    description = workspace.describe()
    assert description["strategy"] == workspace.strategy
    assert description["file_count"] == len(CONTENT)
    assert [mount["name"] for mount in description["mounts"]] == ["source", "overlay", "scratch"]
    assert description["platform"]


# ==========================================================================
# on a real kernel overlayfs
# ==========================================================================
@contextmanager
def kernel_overlay(root: Path) -> Iterator[Path]:
    """Mount a genuine overlayfs, the way a container runtime does."""
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    lower, upper, work, merged = (root / name for name in ("lower", "upper", "work", "merged"))
    for directory in (lower, upper, work, merged):
        directory.mkdir(parents=True, exist_ok=True)
    options = f"lowerdir={lower},upperdir={upper},workdir={work}".encode()
    if libc.mount(b"overlay", str(merged).encode(), b"overlay", 0, options) != 0:
        pytest.skip(f"overlayfs is not mountable here (errno {ctypes.get_errno()})")
    try:
        yield merged
    finally:
        libc.umount(str(merged).encode())


@pytest.mark.skipif(
    sys.platform != "linux",
    reason=(
        "overlayfs is a Linux VFS driver and has no darwin equivalent, so this platform cannot "
        "host the layout under test. NOT COVERED off linux: the workspace's copy-on-write break "
        "when its base directory itself sits in the merged view of a kernel overlay -- that writes "
        "land in the overlay's upper layer, the lower layer stays byte-identical, and "
        "detect_strategy still picks a working strategy there. The pure-userspace CoW, read-only "
        "source and mount-policy properties are covered on every platform by the tests above."
    ),
)
def test_the_workspace_works_on_top_of_a_kernel_overlayfs(tmp_path: Path) -> None:
    """The layout every containerised CI runner actually has.

    The workspace is created inside a merged overlayfs view: writes land in the
    upper layer, the lower layer stays untouched, and the copy-on-write break
    still isolates the workspace's own base from its overlay.
    """
    with kernel_overlay(tmp_path / "kernel") as merged:
        (tmp_path / "kernel" / "lower" / "prior.txt").write_text("lower\n", encoding="utf-8")
        cas = ContentAddressableStore(merged / "cas")
        entries = [(path, cas.put_bytes(payload), 0o644) for path, payload in CONTENT.items()]
        workspace = make_workspace(merged / "ws", cas)
        assert workspace.strategy in ("reflink", "hardlink-cow", "copy")

        workspace.materialize_source(entries)
        workspace.populate_overlay()
        target = workspace.open_for_write("README.md")
        target.write_bytes(b"# rewritten on overlayfs\n")

        assert (workspace.source_root / "README.md").read_bytes() == CONTENT["README.md"]
        # The lower layer of the *kernel* overlay never saw any of it.
        assert (tmp_path / "kernel" / "lower" / "prior.txt").read_text(encoding="utf-8") == "lower\n"
        assert not (tmp_path / "kernel" / "lower" / "ws").exists()
        assert (tmp_path / "kernel" / "upper" / "ws").is_dir()

        exported, undeclared = workspace.export(["README.md"])
        assert exported == ["README.md"]
        assert undeclared


@pytest.mark.parametrize(
    ("resolved", "denied"),
    [
        # The case observed on the user's Mac: /home is an autofs mount and
        # realpath rewrites it onto the data volume, so a literal "/home"
        # prefix never fired and a stranger's home was mountable.
        ("/System/Volumes/Data/home/someone", True),
        ("/System/Volumes/Data/Users/someone", True),
        ("/System/Volumes/Data/etc/passwd", True),
        ("/System/Volumes/Data/root", True),
        # The data volume itself is not a deny entry, and a path under it that
        # maps to nothing denied must still be allowed -- stripping the prefix
        # must not turn into "deny everything on darwin".
        ("/System/Volumes/Data/opt/workspace", False),
        ("/System/Volumes/Data", False),
    ],
)
def test_the_macos_data_volume_spelling_is_denied_too(resolved: str, denied: bool) -> None:
    """Deny entries must fire on the data-volume spelling of the same location.

    macOS resolves some paths through ``/System/Volumes/Data``. Enumerating the
    rewritten spellings by hand is exactly what let ``/home/someone`` through on
    darwin, so ``_denied_spellings`` strips the prefix and every entry in
    ``DENIED_MOUNT_PREFIXES`` -- present and future -- covers both forms.

    This drives ``_denied_spellings`` directly rather than ``check``: the
    rewrite is done by the *host's* realpath, which linux will not perform, so
    a ``check(Path("/home/someone"))`` here would test nothing.
    """

    spellings = overlay_module._denied_spellings(Path(resolved))
    hit = any(
        spelling == prefix or spelling.startswith(prefix + "/")
        for spelling in spellings
        for prefix in overlay_module.DENIED_MOUNT_PREFIXES
    )
    assert hit is denied, spellings

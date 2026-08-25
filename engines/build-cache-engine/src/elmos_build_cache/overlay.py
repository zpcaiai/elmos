"""Sandbox and copy-on-write overlay workspaces.

The source snapshot is materialised read-only and every stage write is confined
to a declared root. Changing one run's overlay can never mutate the CAS, the
snapshot, or another run, because the overlay's base files are either hardlinks
to immutable CAS objects (broken on first write, which is exactly the
copy-on-write semantics we want) or private copies.

Strategy is chosen by platform capability, in descending order of cheapness:

``reflink``
    ``FICLONE`` on Btrfs/XFS/APFS -- copy-on-write in the kernel.
``hardlink-cow``
    hardlink, then break the link on first write. Cheap and portable.
``copy``
    always correct, always available, most expensive.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic import try_reflink
from .canonical import fsync_directory, normalize_logical_path, resolve_within
from .cas import ContentAddressableStore
from .config import WorkspaceConfig
from .errors import ContractViolation, PermissionDenied, QuotaExceeded, UnsafePath

#: Host locations a sandboxed stage must never be able to reach.
DENIED_MOUNT_PREFIXES: tuple[str, ...] = (
    "/etc",
    "/root",
    "/proc",
    "/sys",
    "/dev",
    "/var/run",
    "/run",
    "/private/etc",
    "/Users",
    "/home",
)

# macOS splits the root filesystem into a read-only system volume and a writable
# data volume, and ``realpath`` resolves some paths through the data volume's
# real mount point. ``/home`` is the one that bites: it is an autofs mount whose
# resolved form is ``/System/Volumes/Data/home/...``, so a literal ``/home``
# prefix match never fires and *another user's home directory was mountable into
# a build stage on darwin* -- observed on macOS 26 with
# ``/home/someone -> /System/Volumes/Data/home/someone``.
#
# Enumerating the rewritten spellings one at a time is what let this through in
# the first place (``/private/etc`` and ``/Users`` were each added by hand after
# someone noticed). Stripping the prefix instead makes every entry above -- and
# every entry added later -- cover its data-volume spelling automatically.
_DATA_VOLUME_PREFIX = "/System/Volumes/Data"


def _denied_spellings(resolved: Path) -> tuple[str, ...]:
    """Every spelling of ``resolved`` the deny list should be matched against.

    Returns the resolved path itself plus, on a macOS data-volume path, the
    equivalent path as it is spelled on the system volume. Both are checked, so
    a deny entry written in either form still fires.
    """

    text = resolved.as_posix()
    if text == _DATA_VOLUME_PREFIX:
        return (text, "/")
    if text.startswith(_DATA_VOLUME_PREFIX + "/"):
        return (text, text[len(_DATA_VOLUME_PREFIX) :])
    return (text,)

DENIED_BASENAMES: frozenset[str] = frozenset(
    {".ssh", ".aws", ".gnupg", ".netrc", ".docker", ".kube", ".npmrc", ".pypirc", ".git-credentials"}
)


@dataclass(frozen=True)
class Mount:
    """One root a stage may see, and whether it may write to it."""

    name: str
    path: Path
    writable: bool

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "path": str(self.path), "writable": self.writable}


@dataclass(frozen=True)
class OverlayStats:
    strategy: str
    files: int
    bytes: int
    linked: int
    copied: int


def detect_strategy(root: Path) -> str:
    """Probe the filesystem once, at workspace creation, not per file."""
    probe = root / ".elmos-cow-probe"
    clone = root / ".elmos-cow-clone"
    try:
        probe.write_bytes(b"probe")
        if try_reflink(probe, clone):
            return "reflink"
        clone.unlink(missing_ok=True)
        try:
            os.link(probe, clone)
            return "hardlink-cow"
        except OSError:
            return "copy"
    except OSError:  # pragma: no cover - unwritable root
        return "copy"
    finally:
        probe.unlink(missing_ok=True)
        clone.unlink(missing_ok=True)


class SandboxPolicy:
    """Decides which host paths may be mounted into a stage."""

    def __init__(self, allowed_roots: Sequence[Path] = ()) -> None:
        self.allowed_roots = [Path(root).resolve() for root in allowed_roots]

    def check(self, path: Path) -> Path:
        resolved = Path(path).resolve()
        text = resolved.as_posix()
        for part in resolved.parts:
            if part in DENIED_BASENAMES:
                raise PermissionDenied("credential directory cannot be mounted", path=text)
        if any(root == resolved or root in resolved.parents for root in self.allowed_roots):
            return resolved
        for spelling in _denied_spellings(resolved):
            for prefix in DENIED_MOUNT_PREFIXES:
                if spelling == prefix or spelling.startswith(prefix + "/"):
                    raise PermissionDenied("host path is outside the sandbox allowlist", path=text)
        if resolved.is_socket():  # pragma: no cover - rare in tests
            raise PermissionDenied("sockets cannot be mounted", path=text)
        return resolved


class OverlayWorkspace:
    """Read-only source plus a writable copy-on-write layer."""

    def __init__(
        self,
        source_root: Path,
        overlay_root: Path,
        scratch_root: Path,
        cas: ContentAddressableStore,
        config: WorkspaceConfig | None = None,
        policy: SandboxPolicy | None = None,
        strategy: str | None = None,
    ) -> None:
        self.source_root = Path(source_root)
        self.overlay_root = Path(overlay_root)
        self.scratch_root = Path(scratch_root)
        self.cas = cas
        self.config = config or WorkspaceConfig()
        self.policy = policy or SandboxPolicy(
            allowed_roots=[self.source_root, self.overlay_root, self.scratch_root]
        )
        for directory in (self.source_root, self.overlay_root, self.scratch_root):
            directory.mkdir(parents=True, exist_ok=True)
        self.strategy = strategy or detect_strategy(self.overlay_root)
        self._linked = 0
        self._copied = 0

    # -- source materialisation -------------------------------------------
    def materialize_source(self, entries: Iterable[tuple[str, str, int]]) -> OverlayStats:
        """Place ``(logical_path, digest, mode)`` into the read-only source root.

        Digests are verified on the way in and the result is made read-only, so
        a stage that tries to edit "its input" fails loudly rather than
        silently poisoning the next run's fingerprint.
        """
        files = 0
        total = 0
        for logical_path, digest, mode in entries:
            destination = resolve_within(self.source_root, logical_path)
            # ``auto`` never hardlinks: an in-place write to a source file
            # must not be able to corrupt the canonical CAS object.
            self.cas.materialize(digest, destination, mode=mode, verify=True, share="auto")
            read_only = stat.S_IMODE(mode) & ~0o222
            try:
                os.chmod(destination, read_only)
            except OSError:  # pragma: no cover - platform dependent
                pass
            files += 1
            total += destination.stat().st_size
        self._protect(self.source_root)
        return OverlayStats(self.strategy, files, total, self._linked, self._copied)

    @staticmethod
    def _protect(root: Path) -> None:
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                try:
                    os.chmod(path, stat.S_IMODE(path.stat().st_mode) & ~0o222)
                except OSError:  # pragma: no cover
                    pass

    # -- overlay ----------------------------------------------------------
    def populate_overlay(self, logical_paths: Iterable[str] | None = None) -> OverlayStats:
        """Project the source into the writable layer using the chosen strategy."""
        files = 0
        total = 0
        wanted = None if logical_paths is None else {normalize_logical_path(p) for p in logical_paths}
        for path in sorted(self.source_root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(self.source_root).as_posix()
            if wanted is not None and relative not in wanted:
                continue
            destination = resolve_within(self.overlay_root, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.unlink(missing_ok=True)
            self._project(path, destination)
            files += 1
            total += destination.stat().st_size
            self._check_quota(total)
        return OverlayStats(self.strategy, files, total, self._linked, self._copied)

    def _project(self, source: Path, destination: Path) -> None:
        if self.strategy == "reflink" and try_reflink(source, destination):
            self._linked += 1
            return
        if self.strategy in ("reflink", "hardlink-cow"):
            try:
                os.link(source, destination)
                self._linked += 1
                return
            except OSError:
                pass
        shutil.copyfile(source, destination)
        self._copied += 1

    def open_for_write(self, logical_path: str) -> Path:
        """Break copy-on-write sharing before the first write to ``logical_path``.

        Without this, writing through a hardlink would mutate the shared base --
        the exact cross-run contamination the overlay exists to prevent.
        """
        destination = resolve_within(self.overlay_root, logical_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and not destination.is_symlink():
            info = destination.stat()
            if info.st_nlink > 1:
                temporary = destination.with_name(destination.name + f".elmos-cow-{os.urandom(4).hex()}")
                shutil.copyfile(destination, temporary)
                os.replace(temporary, destination)
                self._copied += 1
            try:
                os.chmod(destination, stat.S_IMODE(info.st_mode) | 0o200)
            except OSError:  # pragma: no cover
                pass
        return destination

    # -- mounts -----------------------------------------------------------
    def mounts(self, extra: Sequence[Mount] = ()) -> list[Mount]:
        """The complete, checked set of roots a stage may see."""
        declared = [
            Mount("source", self.source_root, writable=False),
            Mount("overlay", self.overlay_root, writable=True),
            Mount("scratch", self.scratch_root, writable=True),
        ]
        for mount in extra:
            self.policy.check(mount.path)
            declared.append(mount)
        names = [mount.name for mount in declared]
        if len(set(names)) != len(names):
            raise ContractViolation("duplicate mount names", names=sorted(names))
        return declared

    def assert_writable(self, mounts: Sequence[Mount], path: Path) -> Mount:
        resolved = Path(path).resolve()
        for mount in mounts:
            root = mount.path.resolve()
            if root == resolved or root in resolved.parents:
                if not mount.writable:
                    raise PermissionDenied("write into a read-only mount", mount=mount.name, path=str(path))
                return mount
        raise UnsafePath("path is outside every declared mount", path=str(path))

    # -- accounting -------------------------------------------------------
    def usage(self) -> tuple[int, int]:
        total = 0
        count = 0
        for root in (self.overlay_root, self.scratch_root):
            for path in root.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    total += path.stat().st_size
                    count += 1
        return total, count

    def _check_quota(self, incoming: int) -> None:
        used, count = self.usage()
        if used + incoming > self.config.quota_bytes:
            raise QuotaExceeded("overlay exceeds the run quota", used=used, quota=self.config.quota_bytes)
        if count > self.config.max_files_per_run:
            raise QuotaExceeded("overlay exceeds the run file quota", files=count)

    def export(self, declared_outputs: Sequence[str]) -> tuple[list[str], list[str]]:
        """Split overlay content into declared exports and undeclared leftovers."""
        declared = {normalize_logical_path(path) for path in declared_outputs}
        exported: list[str] = []
        undeclared: list[str] = []
        for path in sorted(self.overlay_root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(self.overlay_root).as_posix()
            (exported if relative in declared else undeclared).append(relative)
        return exported, undeclared

    def discard_scratch(self) -> int:
        """Scratch is disposable by contract; never checkpointed by default."""
        removed = 0
        for path in sorted(self.scratch_root.rglob("*"), reverse=True):
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
                removed += 1
            elif path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass
        fsync_directory(self.scratch_root)
        return removed

    def describe(self) -> dict[str, Any]:
        used, count = self.usage()
        return {
            "strategy": self.strategy,
            "platform": platform.system(),
            "linked": self._linked,
            "copied": self._copied,
            "bytes_used": used,
            "file_count": count,
            "mounts": [mount.to_dict() for mount in self.mounts()],
        }

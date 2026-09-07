"""Gate 1: the same repository, the same root digest, on every platform.

A snapshot digest that differs by platform is worse than no digest at all --
every machine would miss every cache entry the others wrote, and the misses
would look like content changes. This file certifies that property two ways,
because neither is sufficient alone.

**Captured, not asserted.** ``tools/cross_platform_snapshot.py`` builds one
fixed repository from bytes and prints the digest the host computed.
``tests/fixtures/cross_platform_snapshot.json`` holds what each run reported --
by operating system, and separately by filesystem, because the interesting
variable is sometimes one and sometimes the other. The test below rebuilds that
fixture here and requires this host to agree with *every* recorded run. A
platform nobody has run yet is named in a skip, never silently treated as
passing.

**Predicted, not sampled.** Running the fixture on three machines only tells
you about that fixture. ``snapshot.portability_findings`` answers the question
for the repository actually in front of you: which of its paths would collide,
be refused, or come back spelled differently somewhere else. That is the part
that scales past the fixtures.
"""

from __future__ import annotations

import json
import platform
import sys
import unicodedata
from pathlib import Path

import pytest

from elmos_build_cache.snapshot import (
    PortabilityFinding,
    portability_findings,
    portable_everywhere,
    take_snapshot,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from cross_platform_snapshot import FIXTURE, build  # noqa: E402

FIXTURE_FILE = Path(__file__).parent / "fixtures" / "cross_platform_snapshot.json"

#: The platforms ELMOS supports. Anything here without a recorded digest is an
#: openly missing proof, not an assumed one.
EXPECTED_PLATFORMS: tuple[str, ...] = ("linux", "darwin", "windows")


def fixture_document() -> dict[str, dict[str, dict[str, object]]]:
    return json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))


def recorded() -> dict[str, dict[str, object]]:
    """Every run ever captured: by operating system and by filesystem."""
    document = fixture_document()
    captures: dict[str, dict[str, object]] = {}
    for scope in ("platforms", "filesystems"):
        for name, entry in document.get(scope, {}).items():
            captures[f"{scope}:{name}"] = entry
    return captures


# ==========================================================================
# the captured fixture
# ==========================================================================
def test_this_host_agrees_with_every_platform_ever_recorded(tmp_path: Path) -> None:
    build(tmp_path)
    snapshot = take_snapshot(tmp_path)
    entries = recorded()
    assert entries, "no platform has been captured yet"

    for name, entry in sorted(entries.items()):
        assert entry["root_digest"] == snapshot.root_digest, (
            f"{platform.system().lower()} disagrees with the digest captured on {name} "
            f"({entry.get('release')}, python {entry.get('python')})"
        )
        assert entry["manifest_digest"] == snapshot.manifest_digest
        assert entry["files"] == len(snapshot.entries)


def test_a_platform_with_no_capture_is_named_rather_than_assumed() -> None:
    captured = fixture_document().get("platforms", {})
    missing = [name for name in EXPECTED_PLATFORMS if name not in captured]
    if missing:
        pytest.skip(
            "no snapshot digest has been captured on: "
            + ", ".join(missing)
            + " -- run tools/cross_platform_snapshot.py there and add its output to "
            + FIXTURE_FILE.name
        )


def test_the_fixture_is_built_from_bytes_not_from_a_checkout(tmp_path: Path) -> None:
    """Nothing in the fixture can vary with how it was obtained."""
    build(tmp_path)
    for relative, payload, executable in FIXTURE:
        path = tmp_path / unicodedata.normalize("NFC", relative)
        assert path.read_bytes() == payload
        if executable and platform.system() != "Windows":
            assert path.stat().st_mode & 0o111


def test_the_digest_does_not_move_between_two_runs_on_this_host(tmp_path: Path) -> None:
    build(tmp_path / "first")
    build(tmp_path / "second")
    assert take_snapshot(tmp_path / "first").root_digest == take_snapshot(tmp_path / "second").root_digest


# ==========================================================================
# the macOS spelling problem, reproduced on this filesystem
# ==========================================================================
def test_a_decomposed_filename_snapshots_as_the_composed_one(tmp_path: Path) -> None:
    """The concrete way macOS used to break this.

    HFS+ stored names decomposed and APFS still accepts either spelling, so a
    file created as ``café.txt`` can be read back as ``cafe´.txt``. Without
    composing here, the same checkout would produce two different root digests
    on two machines -- exactly the failure gate 1 exists to rule out.
    """
    composed = tmp_path / "composed"
    decomposed = tmp_path / "decomposed"
    for directory, form in ((composed, "NFC"), (decomposed, "NFD")):
        (directory / "docs").mkdir(parents=True)
        (directory / "docs" / unicodedata.normalize(form, "café.md")).write_bytes(b"accents\n")

    left = take_snapshot(composed)
    right = take_snapshot(decomposed)
    assert [entry.logical_path for entry in left.entries] == ["docs/café.md"]
    assert [entry.logical_path for entry in right.entries] == ["docs/café.md"]
    assert left.root_digest == right.root_digest


def test_two_names_that_differ_only_in_normalisation_are_reported(tmp_path: Path) -> None:
    """When the two spellings are two real files, macOS cannot hold both."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / unicodedata.normalize("NFC", "café.md")).write_bytes(b"one\n")
    try:
        (tmp_path / "docs" / unicodedata.normalize("NFD", "café.md")).write_bytes(b"two\n")
    except OSError:  # pragma: no cover - a normalisation-insensitive filesystem
        pytest.skip("this filesystem folds the two spellings into one file")
    snapshot = take_snapshot(tmp_path)
    if len(snapshot.entries) == 1:
        pytest.skip("this filesystem folds the two spellings into one file")
    findings = [f for f in portability_findings(snapshot) if f.hazard == "UNICODE_NORMALIZATION"]
    assert findings, portability_findings(snapshot)
    assert findings[0].logical_path == "docs/café.md"
    assert findings[0].platforms == ("macos",)


# ==========================================================================
# predicted hazards
# ==========================================================================
def test_a_clean_repository_has_no_hazards(tmp_path: Path) -> None:
    build(tmp_path)
    assert portability_findings(take_snapshot(tmp_path)) == ()
    assert portable_everywhere(take_snapshot(tmp_path)) is True


def test_a_case_collision_is_reported_for_macos_and_windows(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.java").write_bytes(b"one\n")
    try:
        (tmp_path / "src" / "app.java").write_bytes(b"two\n")
    except OSError:  # pragma: no cover
        pytest.skip("this filesystem is case-insensitive; the collision cannot be created")
    snapshot = take_snapshot(tmp_path)
    if len(snapshot.entries) == 1:
        pytest.skip("this filesystem is case-insensitive; the collision cannot be created")

    findings = [f for f in portability_findings(snapshot) if f.hazard == "CASE_COLLISION"]
    assert len(findings) == 1
    assert findings[0].logical_path == "src/app.java"
    assert set(findings[0].platforms) == {"macos", "windows"}
    assert portable_everywhere(snapshot) is False


@pytest.mark.parametrize(
    ("name", "hazard"),
    [
        ("aux.txt", "WINDOWS_RESERVED_NAME"),
        ("con", "WINDOWS_RESERVED_NAME"),
        ("com1.log", "WINDOWS_RESERVED_NAME"),
        ("lpt9.dat", "WINDOWS_RESERVED_NAME"),
        ("what?.md", "WINDOWS_ILLEGAL_CHARACTER"),
        ("a:b.txt", "WINDOWS_ILLEGAL_CHARACTER"),
        ('quote".txt', "WINDOWS_ILLEGAL_CHARACTER"),
        ("pipe|d.txt", "WINDOWS_ILLEGAL_CHARACTER"),
        ("trailing.", "TRAILING_DOT_OR_SPACE"),
        ("trailing ", "TRAILING_DOT_OR_SPACE"),
    ],
)
def test_windows_hostile_names_are_reported(tmp_path: Path, name: str, hazard: str) -> None:
    try:
        (tmp_path / name).write_bytes(b"x\n")
    except OSError:  # pragma: no cover - the host filesystem refused it too
        pytest.skip(f"this filesystem cannot create {name!r}")
    findings = portability_findings(take_snapshot(tmp_path))
    assert hazard in {finding.hazard for finding in findings}, findings
    assert all(finding.platforms == ("windows",) for finding in findings if finding.hazard == hazard)


def test_a_symlink_is_reported_as_a_windows_hazard(tmp_path: Path) -> None:
    (tmp_path / "real.txt").write_bytes(b"real\n")
    try:
        (tmp_path / "link.txt").symlink_to("real.txt")
    except OSError:  # pragma: no cover - Windows without developer mode
        pytest.skip("this host cannot create symlinks, which is the hazard itself")
    findings = [f for f in portability_findings(take_snapshot(tmp_path)) if f.hazard == "SYMLINK"]
    assert [finding.logical_path for finding in findings] == ["link.txt"]


def test_an_over_long_path_is_reported(tmp_path: Path) -> None:
    deep = tmp_path
    for index in range(12):
        deep = deep / f"segment-{index:02d}-{'x' * 20}"
    deep.mkdir(parents=True)
    (deep / "file.txt").write_bytes(b"deep\n")
    findings = [f for f in portability_findings(take_snapshot(tmp_path)) if f.hazard == "PATH_TOO_LONG"]
    assert findings and findings[0].platforms == ("windows",)


def test_findings_are_serialisable_for_a_report(tmp_path: Path) -> None:
    (tmp_path / "aux.txt").write_bytes(b"x\n")
    finding = portability_findings(take_snapshot(tmp_path))[0]
    assert isinstance(finding, PortabilityFinding)
    assert json.loads(json.dumps(finding.to_dict()))["hazard"] == "WINDOWS_RESERVED_NAME"

"""Ownership, protected regions, three-way merge and deterministic mergers."""

from __future__ import annotations

import pytest

from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.enums import Ownership
from elmos_build_cache.errors import ConflictError
from elmos_build_cache.merge import (
    ConflictKind,
    ConflictStore,
    OwnershipMap,
    ResolutionRules,
    detect_tree_conflicts,
    extract_protected_regions,
    merge_config_mapping,
    merge_dependency_manifest,
    merge_registration_list,
    three_way_merge,
)

GENERATED_V1 = (
    "// header\n"
    "// ELMOS:BEGIN PROTECTED custom\n"
    "// placeholder\n"
    "// ELMOS:END PROTECTED custom\n"
    "// footer\n"
)
USER_EDIT = GENERATED_V1.replace("// placeholder", "int myCustomLogic() { return 42; }")
GENERATED_V2 = GENERATED_V1.replace("// header", "// header v2").replace("// footer", "// footer v2")


def test_ownership_uses_the_longest_matching_prefix() -> None:
    ownership = OwnershipMap()
    ownership.set("src", Ownership.GENERATED)
    ownership.set("src/custom", Ownership.USER)
    ownership.set("vendor", Ownership.EXTERNAL)
    assert ownership.of("src/App.cs") is Ownership.GENERATED
    assert ownership.of("src/custom/My.cs") is Ownership.USER
    assert ownership.of("vendor/lib.js") is Ownership.EXTERNAL
    assert ownership.of("unrelated/x") is Ownership.GENERATED  # the default


def test_user_owned_content_is_never_overwritten() -> None:
    result = three_way_merge("src/custom/My.cs", b"base", b"user edit", b"regenerated", Ownership.USER)
    assert result.clean
    assert result.merged == b"user edit"


def test_externally_managed_paths_are_left_alone() -> None:
    result = three_way_merge("vendor/lib.js", b"base", b"vendor", b"generated", Ownership.EXTERNAL)
    assert result.merged == b"vendor"


def test_hand_edited_generated_file_conflicts_instead_of_being_clobbered() -> None:
    result = three_way_merge(
        "src/App.cs", b"generated v1", b"hand edited", b"generated v2", Ownership.GENERATED
    )
    assert not result.clean
    assert result.merged is None
    assert result.conflicts[0].detail.startswith("generated-owned file was edited")


def test_untouched_generated_file_is_replaced() -> None:
    result = three_way_merge(
        "src/App.cs", b"generated v1", b"generated v1", b"generated v2", Ownership.GENERATED
    )
    assert result.merged == b"generated v2"


def test_protected_regions_survive_regeneration() -> None:
    result = three_way_merge(
        "src/App.cs",
        GENERATED_V1.encode(),
        USER_EDIT.encode(),
        GENERATED_V2.encode(),
        Ownership.GENERATED_PROTECTED,
    )
    assert result.clean
    merged = (result.merged or b"").decode()
    assert "int myCustomLogic() { return 42; }" in merged
    assert "// header v2" in merged and "// footer v2" in merged
    assert "// placeholder" not in merged


def test_dropped_protected_region_is_a_conflict() -> None:
    result = three_way_merge(
        "src/App.cs",
        GENERATED_V1.encode(),
        USER_EDIT.encode(),
        b"// header v2\n// footer v2\n",
        Ownership.GENERATED_PROTECTED,
    )
    assert not result.clean
    assert result.conflicts[0].kind == ConflictKind.PROTECTED_REGION
    assert result.conflicts[0].region == "custom"


def test_malformed_region_markers_fail_closed() -> None:
    with pytest.raises(ConflictError):
        extract_protected_regions("// ELMOS:BEGIN PROTECTED a\nbody\n")
    result = three_way_merge(
        "src/App.cs",
        GENERATED_V1.encode(),
        b"// ELMOS:BEGIN PROTECTED a\nbody\n",
        GENERATED_V2.encode(),
        Ownership.GENERATED_PROTECTED,
    )
    assert not result.clean


def test_three_way_merge_of_disjoint_edits() -> None:
    result = three_way_merge(
        "src/shared/x.py", b"a\nb\nc\nd\n", b"a2\nb\nc\nd\n", b"a\nb\nc\nd2\n", Ownership.SHARED
    )
    assert result.clean
    assert result.merged == b"a2\nb\nc\nd2\n"


def test_overlapping_edits_conflict_rather_than_pick_a_winner() -> None:
    result = three_way_merge(
        "src/shared/x.py", b"a\nb\n", b"a2\nb\n", b"a3\nb\n", Ownership.SHARED
    )
    assert not result.clean
    assert result.merged is None


def test_binary_and_unknown_types_fail_closed() -> None:
    assert three_way_merge("logo.png", b"\x00a", b"\x00b", b"\x00c", Ownership.SHARED).conflicts[0].kind == (
        ConflictKind.BINARY
    )
    assert not three_way_merge("data.unknownext", b"a", b"b", b"c", Ownership.SHARED).clean


def test_dependency_manifest_merger_is_deterministic() -> None:
    merged, conflicts = merge_dependency_manifest(
        {"a": "1", "b": "1", "c": "1"}, {"a": "1", "b": "2", "c": "1"}, {"a": "2", "b": "1"}
    )
    assert conflicts == []
    assert merged == {"a": "2", "b": "2"}  # c removed upstream, a taken, b kept

    _, disagreement = merge_dependency_manifest({"a": "1"}, {"a": "2"}, {"a": "3"})
    assert disagreement and disagreement[0].kind == ConflictKind.DEPENDENCY_MANIFEST


def test_registration_list_merger_unions_and_respects_removals() -> None:
    assert merge_registration_list(["r1", "r2"], ["r1", "r2", "r3"], ["r2", "r4"]) == ["r2", "r3", "r4"]


def test_config_merger_recurses_and_reports_disagreement() -> None:
    merged, conflicts = merge_config_mapping(
        {"a": {"x": 1}}, {"a": {"x": 1, "y": 2}}, {"a": {"x": 9}}
    )
    assert merged["a"] == {"x": 9, "y": 2}
    assert conflicts == []
    _, clash = merge_config_mapping({"k": 1}, {"k": 2}, {"k": 3})
    assert clash and clash[0].kind == ConflictKind.SCHEMA


def test_tree_level_conflicts_are_detected_before_publication() -> None:
    ownership = OwnershipMap()
    ownership.set("src/custom", Ownership.USER)
    conflicts = detect_tree_conflicts(
        {
            "a/B.cs": "sha256:" + "1" * 64,
            "a/b.cs": "sha256:" + "2" * 64,
            "src/custom/My.cs": "sha256:" + "3" * 64,
        },
        existing={"src/custom/My.cs": "sha256:" + "9" * 64},
        ownership=ownership,
    )
    kinds = {conflict.kind for conflict in conflicts}
    assert ConflictKind.CASE in kinds
    assert any("user-owned" in conflict.detail for conflict in conflicts)


def test_unresolved_conflicts_are_preserved_with_all_three_sides(cas: ContentAddressableStore) -> None:
    store = ConflictStore(cas)
    result = three_way_merge("src/x.py", b"a\nb\n", b"a2\nb\n", b"a3\nb\n", Ownership.SHARED)
    digest = store.preserve("src/x.py", result.conflicts, b"a\nb\n", b"a2\nb\n", b"a3\nb\n")

    record = store.load(digest)
    assert cas.get_bytes(record["base"]) == b"a\nb\n"
    assert cas.get_bytes(record["ours"]) == b"a2\nb\n"
    assert cas.get_bytes(record["theirs"]) == b"a3\nb\n"


def test_recorded_resolutions_replay_deterministically() -> None:
    rules = ResolutionRules()
    rules.record("src/x.py", b"base", b"ours", b"theirs", "theirs", "stephen")
    assert rules.apply("src/x.py", b"base", b"ours", b"theirs") == b"theirs"
    # A different input triple must not silently reuse the decision.
    assert rules.apply("src/x.py", b"base", b"ours", b"other") is None
    with pytest.raises(ConflictError):
        rules.record("src/x.py", b"base", b"ours", b"theirs", "coin-flip", "stephen")

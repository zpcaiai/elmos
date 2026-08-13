from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "batch29"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from route_sets import (  # noqa: E402
    COMPLETE_ROUTE_KEYS,
    CORE_ROUTE_KEYS,
    ROUTE_PROVENANCE_PARTITIONS,
)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runner():
    return _load(SCRIPTS / "run_polyglot_routes.py", "legacy_authority_runner")


def _generator():
    return _load(
        ROOT / "tooling/generate_polyglot_formal_verification_pack.py",
        "legacy_authority_generator",
    )


def test_route_authority_partition_is_exact_30_8_34_18() -> None:
    assert {
        name: len(route_keys)
        for name, route_keys in ROUTE_PROVENANCE_PARTITIONS.items()
    } == {
        "legacy-complete-30": 30,
        "cpp-objc-swift-java-exact-8": 8,
        "nine-language-completion-34": 34,
        "javascript-node26-completion-18": 18,
    }
    flattened = [
        route_key
        for route_keys in ROUTE_PROVENANCE_PARTITIONS.values()
        for route_key in route_keys
    ]
    assert len(flattened) == len(set(flattened)) == 90
    assert set(flattened) == set(COMPLETE_ROUTE_KEYS)


def test_legacy_campaign_authority_binds_campaign_schema_validator_and_method() -> None:
    runner = _runner()
    authority = runner.legacy_campaign_authority(ROOT)
    assert authority["route_count"] == 30
    assert authority["campaign"] == {
        "path": runner.LEGACY_CAMPAIGN_RELATIVE,
        "sha256": runner.LEGACY_CAMPAIGN_SHA256,
        "bytes": runner.LEGACY_CAMPAIGN_BYTES,
    }
    assert set(authority["replay_assets"]) == {"launcher", "schema", "validator"}
    assert authority["method_sha256"] == runner.LEGACY_REPLAY_METHOD_SHA256
    assert authority["native_reexecution_status"] == "NOT_RUN"
    assert authority["authority_sha256"].startswith("sha256:")


def test_default_runner_verifies_legacy_read_only_without_execute_or_inventory() -> (
    None
):
    runner = _runner()
    with (
        mock.patch.object(
            sys,
            "argv",
            [str(runner.__file__), "--repo-root", str(ROOT)],
        ),
        mock.patch.object(
            runner,
            "execute_route",
            side_effect=AssertionError("legacy execute forbidden"),
        ),
        mock.patch.object(
            runner,
            "write_inventory",
            side_effect=AssertionError("legacy inventory write forbidden"),
        ),
    ):
        assert runner.main() == 0


def test_complete_90_execution_skips_immutable_legacy_30() -> None:
    runner = _runner()
    executed: list[str] = []

    def record_execute(_repo: Path, _fixtures: Path, source: str, target: str) -> None:
        executed.append(f"{source}-to-{target}")

    with (
        mock.patch.object(
            sys,
            "argv",
            [
                str(runner.__file__),
                "--repo-root",
                str(ROOT),
                "--route-set",
                "ten-language-complete-90",
            ],
        ),
        mock.patch.object(runner, "legacy_campaign_authority"),
        mock.patch.object(runner, "execute_route", side_effect=record_execute),
        mock.patch.object(runner, "run_route_checks", return_value=0),
        mock.patch.object(runner, "write_inventory"),
    ):
        assert runner.main() == 0
    assert len(executed) == 60
    assert not set(executed) & set(CORE_ROUTE_KEYS)
    assert set(executed) == set(COMPLETE_ROUTE_KEYS) - set(CORE_ROUTE_KEYS)


def test_direct_legacy_execute_fails_before_any_route_write(tmp_path: Path) -> None:
    runner = _runner()
    before = set(tmp_path.rglob("*"))
    with pytest.raises(
        RuntimeError,
        match="LEGACY_ROUTE_IMMUTABLE_REEXECUTION_REQUIRES_NEW_PACK_VERSION",
    ):
        runner.execute_route(
            tmp_path,
            tmp_path / "fixtures",
            "java",
            "python",
        )
    assert set(tmp_path.rglob("*")) == before


def test_canonical_generator_default_is_zero_write_verify_existing() -> None:
    generator = _generator()
    pack = ROOT / "verification-packs" / generator.CANONICAL_PACK_KEY
    before = generator.immutable_tree_digest(pack)
    authority = generator.verify_existing_canonical_pack(
        ROOT,
        execute_frozen_replay=False,
    )
    after = generator.immutable_tree_digest(pack)
    assert before == after == authority["tree_sha256"]
    assert authority["method_sha256"] == generator.LEGACY_REPLAY_METHOD_SHA256


def test_generator_cli_default_never_builds_or_publishes_canonical() -> None:
    generator = _generator()
    expected = {
        "route_count": 30,
        "campaign_sha256": generator.LEGACY_CAMPAIGN_SHA256,
        "method_sha256": generator.LEGACY_REPLAY_METHOD_SHA256,
        "tree_sha256": "sha256:" + "1" * 64,
    }
    with (
        mock.patch.object(
            sys,
            "argv",
            [str(generator.__file__), "--repo-root", str(ROOT)],
        ),
        mock.patch.object(
            generator,
            "verify_existing_canonical_pack",
            return_value=expected,
        ) as verify,
        mock.patch.object(
            generator,
            "validate_source_routes",
            side_effect=AssertionError("live routes must not load"),
        ),
        mock.patch.object(
            generator,
            "publish_staged_pack",
            side_effect=AssertionError("canonical publish forbidden"),
        ),
    ):
        assert generator.main() == 0
    verify.assert_called_once_with(ROOT)


def test_generator_rejects_canonical_key_as_rebuild_target(tmp_path: Path) -> None:
    generator = _generator()
    arithmetic = tmp_path / "arithmetic.json"
    arithmetic.write_text("{}\n", encoding="utf-8")
    with (
        mock.patch.object(
            sys,
            "argv",
            [
                str(generator.__file__),
                "--repo-root",
                str(ROOT),
                "--build-new-pack-key",
                generator.CANONICAL_PACK_KEY,
                "--pack-version",
                "2.0.0",
                "--arithmetic-campaign",
                str(arithmetic),
            ],
        ),
        pytest.raises(SystemExit),
    ):
        generator.main()

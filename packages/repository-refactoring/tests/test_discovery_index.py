"""Discovery, build graph and semantic index over the fixture repository."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from elmos_repository_refactoring.buildgraph import build_graph, establish_baseline, toolchain_lock
from elmos_repository_refactoring.contracts import EntityKind
from elmos_repository_refactoring.discovery import discover, discovery_evidence, parse_codeowners
from elmos_repository_refactoring.index import build_index, incremental_update
from elmos_repository_refactoring.sandbox import NullExecutor
from elmos_repository_refactoring.workspace import WorkspaceSnapshot

from .fixtures import workspace_payload


@pytest.fixture
def snapshot() -> WorkspaceSnapshot:
    return WorkspaceSnapshot.from_payload(workspace_payload())


class TestWorkspace:
    def test_tree_digest_is_stable_across_insertion_order(self, snapshot: WorkspaceSnapshot) -> None:
        payload = workspace_payload()
        payload["files"] = list(reversed(payload["files"]))
        assert WorkspaceSnapshot.from_payload(payload).tree_digest == snapshot.tree_digest

    def test_declared_digest_mismatch_is_refused(self) -> None:
        payload = workspace_payload()
        payload["files"] = [
            {"path": "a.py", "content": "x = 1\n", "content_digest": "sha256:" + "0" * 64}
        ]
        with pytest.raises(Exception, match="content_digest_mismatch"):
            WorkspaceSnapshot.from_payload(payload)

    def test_unreadable_files_are_not_readable_text(self, snapshot: WorkspaceSnapshot) -> None:
        record = snapshot.require("docs/broken.bin")
        assert record.readable_text is False
        assert record.unreadable_reason == "not-utf8"

    def test_with_files_does_not_mutate_the_original(self, snapshot: WorkspaceSnapshot) -> None:
        before = snapshot.tree_digest
        updated = snapshot.with_files({"src/acme/ledger.py": "# replaced\n"})
        assert snapshot.tree_digest == before
        assert updated.tree_digest != before
        assert updated.text_of("src/acme/ledger.py") == "# replaced\n"

    def test_directory_read_refuses_without_approval(self, tmp_path: Path) -> None:
        from elmos_repository_refactoring.workspace import snapshot_from_context

        with pytest.raises(Exception, match="workspace_root_not_approved"):
            snapshot_from_context(
                {"source": "approved-root", "repository_id": "x", "revision": "abcdefg"},
                approved_root=None,
            )

    def test_directory_read_skips_symlinks_that_escape(self, tmp_path: Path) -> None:
        (tmp_path / "inside.txt").write_text("hello\n", encoding="utf-8")
        outside = tmp_path.parent / "outside-target.txt"
        outside.write_text("secret\n", encoding="utf-8")
        try:
            (tmp_path / "escape.txt").symlink_to(outside)
        except OSError:  # pragma: no cover - platform without symlink permission
            pytest.skip("symlinks unavailable")
        built = WorkspaceSnapshot.from_directory(tmp_path, repository_id="r", revision="abcdefg1")
        record = built.require("escape.txt")
        assert record.unreadable_reason == "symlink-outside-workspace"
        assert built.require("inside.txt").text == "hello\n"


class TestDiscovery:
    def test_languages_are_counted_with_generated_and_test_splits(self, snapshot: WorkspaceSnapshot) -> None:
        inventory = discover(snapshot)
        languages = {item.language: item for item in inventory.languages}
        assert languages["python"].files == 4
        assert languages["python"].test_files == 1
        assert languages["go"].generated_files == 1

    def test_generated_files_are_detected_by_header_not_only_by_path(
        self, snapshot: WorkspaceSnapshot
    ) -> None:
        inventory = discover(snapshot)
        assert "gen/billingpb/charge.pb.go" in inventory.generated_paths

    def test_vendored_paths_are_reported(self, snapshot: WorkspaceSnapshot) -> None:
        inventory = discover(snapshot)
        assert "vendor/left-pad/index.js" in inventory.vendored_paths

    def test_build_systems_and_idl_are_detected(self, snapshot: WorkspaceSnapshot) -> None:
        inventory = discover(snapshot)
        assert {"maven", "node", "python-project"} <= set(inventory.build_systems)
        assert inventory.idl_files["protobuf"] == ("contracts/billing.proto",)
        assert inventory.idl_files["openapi"] == ("contracts/openapi.yaml",)

    def test_codeowners_last_match_wins(self) -> None:
        rules = parse_codeowners(
            "* @everyone\n/services/billing/ @payments\n# comment\nbadline\n*.sql @data\n"
        )
        assert len(rules) == 3
        assert rules[-1].owners == ("@data",)

    def test_ownership_is_applied_with_last_match_semantics(self, snapshot: WorkspaceSnapshot) -> None:
        inventory = discover(snapshot)
        assert inventory.owners_of("db/migrations/001_init.sql") == ("@acme/data",)
        assert inventory.owners_of("src/acme/billing.py") == ("@acme/platform",)

    def test_sensitive_areas_are_found_by_path_and_content(self, snapshot: WorkspaceSnapshot) -> None:
        inventory = discover(snapshot)
        areas = set(inventory.sensitive_area_names)
        assert "payment" in areas
        payment_hits = [hit for hit in inventory.sensitive_areas if hit.area == "payment"]
        assert any(hit.path == "src/acme/billing.py" for hit in payment_hits)

    def test_unreadable_files_lower_coverage_and_are_listed(self, snapshot: WorkspaceSnapshot) -> None:
        inventory = discover(snapshot)
        assert any(item["path"] == "docs/broken.bin" for item in inventory.unscanned)
        assert inventory.coverage < Decimal("1")

    def test_evidence_warns_about_incomplete_scans(self, snapshot: WorkspaceSnapshot) -> None:
        evidence = discovery_evidence(discover(snapshot))
        assert any("not counted as empty" in warning for warning in evidence.warnings)

    def test_inventory_digest_is_stable(self, snapshot: WorkspaceSnapshot) -> None:
        assert discover(snapshot).digest == discover(snapshot).digest


class TestBuildGraph:
    def test_targets_are_parsed_from_real_build_files(self, snapshot: WorkspaceSnapshot) -> None:
        graph = build_graph(snapshot, discover(snapshot))
        ids = {target.target_id for target in graph.targets}
        assert "maven:com.acme:users" in ids
        assert "npm:@acme/web" in ids
        assert "python:acme-billing" in ids

    def test_nested_module_claims_its_own_files(self, snapshot: WorkspaceSnapshot) -> None:
        graph = build_graph(snapshot, discover(snapshot))
        targets = graph.targets_for("services/users/src/main/java/com/acme/users/UserDirectory.java")
        assert "maven:com.acme:users" in targets

    def test_test_targets_are_linked_to_their_library(self, snapshot: WorkspaceSnapshot) -> None:
        graph = build_graph(snapshot, discover(snapshot))
        assert graph.target_to_tests["python:acme-billing"] == ("python:acme-billing:test",)

    def test_unmapped_files_are_reported_not_guessed(self, snapshot: WorkspaceSnapshot) -> None:
        graph = build_graph(snapshot, discover(snapshot))
        assert isinstance(graph.unmapped_files, tuple)
        assert graph.coverage <= 1.0

    def test_toolchain_lock_reports_unpinned_systems(self, snapshot: WorkspaceSnapshot) -> None:
        graph = build_graph(snapshot, discover(snapshot))
        lock = toolchain_lock(snapshot, graph)
        assert not lock.reproducible
        assert "node" in lock.unpinned or "python" in lock.unpinned

    def test_baseline_without_an_executor_is_not_run_and_not_trustworthy(
        self, snapshot: WorkspaceSnapshot
    ) -> None:
        graph = build_graph(snapshot, discover(snapshot))
        baseline = establish_baseline(graph, NullExecutor())
        assert baseline.trustworthy is False
        assert baseline.build_ok is None
        assert baseline.status.value == "not-run"


class TestSemanticIndex:
    def test_python_symbols_are_exact(self, snapshot: WorkspaceSnapshot) -> None:
        inventory = discover(snapshot)
        index = build_index(snapshot, inventory, build_graph(snapshot, inventory))
        charge = index.by_qualified_name("acme.billing.BillingService.charge")
        assert len(charge) == 1
        assert charge[0].kind is EntityKind.METHOD
        assert "currency: str" in charge[0].signature
        assert charge[0].provenance_adapter == "compiler"

    def test_inheritance_edges_are_recorded(self, snapshot: WorkspaceSnapshot) -> None:
        inventory = discover(snapshot)
        index = build_index(snapshot, inventory, build_graph(snapshot, inventory))
        service = index.by_qualified_name("acme.billing.BillingService")[0]
        base = index.by_qualified_name("acme.billing.BillingBase")[0]
        assert base.id in {edge.to_id for edge in index.outgoing(service.id)}

    def test_dynamic_getattr_is_recorded_as_a_dynamic_edge(self, snapshot: WorkspaceSnapshot) -> None:
        inventory = discover(snapshot)
        index = build_index(snapshot, inventory, build_graph(snapshot, inventory))
        assert index.dynamic_relationships
        assert index.coverage.dynamic_files >= 1
        report = index.unknown_region_report()
        assert report["dynamicReferences"]

    def test_cross_file_call_is_resolved(self, snapshot: WorkspaceSnapshot) -> None:
        inventory = discover(snapshot)
        index = build_index(snapshot, inventory, build_graph(snapshot, inventory))
        post_entry = index.by_qualified_name("acme.ledger.post_entry")[0]
        assert index.incoming(post_entry.id)

    def test_java_and_typescript_are_syntactic_tier(self, snapshot: WorkspaceSnapshot) -> None:
        inventory = discover(snapshot)
        index = build_index(snapshot, inventory, build_graph(snapshot, inventory))
        java = index.by_qualified_name("com.acme.users.UserDirectory")
        assert java and java[0].provenance_adapter == "syntactic"
        assert java[0].confidence < Decimal("1")

    def test_contract_entities_are_indexed(self, snapshot: WorkspaceSnapshot) -> None:
        inventory = discover(snapshot)
        index = build_index(snapshot, inventory, build_graph(snapshot, inventory))
        names = {entity.name for entity in index.of_kind(EntityKind.API_CONTRACT)}
        assert "/v1/charges" in names
        assert "CreateCharge" in names
        assert {entity.name for entity in index.of_kind(EntityKind.EVENT_CONTRACT)} == {"ChargeCreated"}

    def test_generated_files_are_reported_as_unknown_regions_not_indexed(
        self, snapshot: WorkspaceSnapshot
    ) -> None:
        inventory = discover(snapshot)
        index = build_index(snapshot, inventory, build_graph(snapshot, inventory))
        reasons = {region.reason for region in index.unknown_regions}
        assert "generated-excluded" in reasons

    def test_unknown_risk_weight_is_positive_when_coverage_is_partial(
        self, snapshot: WorkspaceSnapshot
    ) -> None:
        inventory = discover(snapshot)
        index = build_index(snapshot, inventory, build_graph(snapshot, inventory))
        assert index.coverage.unknown_risk_weight > Decimal("0")

    def test_index_digest_is_deterministic(self, snapshot: WorkspaceSnapshot) -> None:
        inventory = discover(snapshot)
        graph = build_graph(snapshot, inventory)
        assert build_index(snapshot, inventory, graph).digest == build_index(snapshot, inventory, graph).digest

    def test_incremental_update_matches_a_full_rebuild_for_the_changed_file(
        self, snapshot: WorkspaceSnapshot
    ) -> None:
        inventory = discover(snapshot)
        graph = build_graph(snapshot, inventory)
        original = build_index(snapshot, inventory, graph)
        changed = snapshot.with_files(
            {"src/acme/ledger.py": "def post_entry(a, b, c):\n    return ''\n\n\ndef added(x):\n    return x\n"}
        )
        full = build_index(changed, discover(changed), build_graph(changed, discover(changed)))
        incremental = incremental_update(original, changed, inventory, graph, ["src/acme/ledger.py"])
        full_names = {entity.qualified_name for entity in full.entities if entity.path == "src/acme/ledger.py"}
        incremental_names = {
            entity.qualified_name for entity in incremental.entities if entity.path == "src/acme/ledger.py"
        }
        assert full_names == incremental_names
        assert "acme.ledger.added" in incremental_names

"""Patches, Python scope resolution, operations, Recipes and the executor."""

from __future__ import annotations

from decimal import Decimal

import pytest

from elmos_repository_refactoring.contracts import ContractError, Status
from elmos_repository_refactoring.dispatcher import dispatch
from elmos_repository_refactoring.patch import (
    TextEdit,
    apply_edits,
    check_overlaps,
    diff_snapshots,
    patch_from_edits,
)
from elmos_repository_refactoring.pyops import (
    ParameterChange,
    Severity,
    add_import,
    change_signature,
    dangling_references,
    remove_unreferenced_definition,
    remove_unused_imports,
    rename_binding,
    rename_imported_symbol,
    rewrite_module_imports,
)
from elmos_repository_refactoring.pyscope import BindingKind, ScopeKind, analyze
from elmos_repository_refactoring.recipe import (
    Recipe,
    bind_parameters,
    check_cardinality,
    evaluate_predicates,
    resolve_selector,
)
from elmos_repository_refactoring.synthesis import BUILTIN_RECIPES, registry_payload
from elmos_repository_refactoring.workspace import WorkspaceSnapshot

from .fixtures import request_payload, workspace_payload


def _snapshot() -> WorkspaceSnapshot:
    return WorkspaceSnapshot.from_payload(workspace_payload())


def _edit(path: str, line: int, start: int, end: int, replacement: str, action: str = "a") -> TextEdit:
    return TextEdit(
        path=path,
        start_line=line,
        start_column=start,
        end_line=line,
        end_column=end,
        replacement=replacement,
        action_id=action,
    )


class TestEditsAndPatches:
    def test_edits_apply_right_to_left_without_offset_drift(self) -> None:
        text = "alpha beta gamma\n"
        edits = [
            _edit("f.py", 1, 0, 5, "one"),
            _edit("f.py", 1, 6, 10, "two"),
            _edit("f.py", 1, 11, 16, "three"),
        ]
        assert apply_edits(text, edits) == "one two three\n"

    def test_reversed_input_order_produces_the_same_result(self) -> None:
        text = "alpha beta gamma\n"
        edits = [
            _edit("f.py", 1, 0, 5, "one"),
            _edit("f.py", 1, 11, 16, "three"),
        ]
        assert apply_edits(text, edits) == apply_edits(text, list(reversed(edits)))

    def test_overlapping_edits_are_refused(self) -> None:
        edits = [_edit("f.py", 1, 0, 6, "x", "a1"), _edit("f.py", 1, 3, 9, "y", "a2")]
        assert check_overlaps(edits)
        with pytest.raises(ContractError) as error:
            apply_edits("abcdefghij\n", edits)
        assert error.value.code == "overlapping_edits"

    def test_two_insertions_at_the_same_point_are_an_overlap(self) -> None:
        edits = [_edit("f.py", 1, 3, 3, "x", "a1"), _edit("f.py", 1, 3, 3, "y", "a2")]
        assert check_overlaps(edits)

    def test_crlf_files_keep_their_line_endings(self) -> None:
        text = "one\r\ntwo\r\n"
        result = apply_edits(text, [_edit("f.txt", 2, 0, 3, "TWO")])
        assert result == "one\r\nTWO\r\n"

    def test_multi_line_edit_replaces_the_span(self) -> None:
        text = "a\nb\nc\nd\n"
        edit = TextEdit(path="f", start_line=2, start_column=0, end_line=3, end_column=1, replacement="X")
        assert apply_edits(text, [edit]) == "a\nX\nd\n"

    def test_edit_beyond_the_end_of_file_is_refused(self) -> None:
        with pytest.raises(ContractError) as error:
            apply_edits("a\n", [_edit("f", 9, 0, 1, "x")])
        assert error.value.code == "edit_out_of_range"

    def test_patch_is_minimal_and_attributed(self) -> None:
        snapshot = _snapshot()
        patch, updated = patch_from_edits(
            snapshot,
            [_edit("src/acme/ledger.py", 5, 4, 14, "record_entry", "rename")],
            step_id="s1",
        )
        assert patch.changed_files == 1
        assert patch.changed_lines <= 2
        assert patch.hunks[0].action_ids == ("rename",)
        assert updated.tree_digest != snapshot.tree_digest

    def test_patch_inverts_back_to_the_original(self) -> None:
        snapshot = _snapshot()
        patch, updated = patch_from_edits(
            snapshot, [_edit("src/acme/ledger.py", 5, 4, 14, "renamed_fn")]
        )
        restored = patch.invert().apply(updated, verify_base=False)
        assert restored.tree_digest == snapshot.tree_digest

    def test_applying_to_a_drifted_tree_is_refused(self) -> None:
        snapshot = _snapshot()
        patch, _ = patch_from_edits(snapshot, [_edit("src/acme/ledger.py", 5, 4, 14, "renamed_fn")])
        drifted = snapshot.with_files({"src/acme/ledger.py": "# something else\n"})
        with pytest.raises(ContractError) as error:
            patch.apply(drifted)
        assert error.value.code == "patch_base_mismatch"

    def test_merging_patches_that_touch_the_same_file_is_refused(self) -> None:
        snapshot = _snapshot()
        left, _ = patch_from_edits(snapshot, [_edit("src/acme/ledger.py", 5, 4, 14, "one")])
        right, _ = patch_from_edits(snapshot, [_edit("src/acme/ledger.py", 5, 4, 14, "two")])
        with pytest.raises(ContractError) as error:
            left.merge(right)
        assert error.value.code == "patch_merge_conflict"

    def test_disjoint_patches_merge_and_the_digest_is_order_independent(self) -> None:
        snapshot = _snapshot()
        left, _ = patch_from_edits(snapshot, [_edit("src/acme/ledger.py", 5, 4, 14, "one")])
        right, _ = patch_from_edits(snapshot, [_edit("src/acme/billing.py", 12, 0, 16, "OTHER_CURRENCY")])
        assert left.merge(right).digest == right.merge(left).digest

    def test_identical_snapshots_produce_an_empty_patch(self) -> None:
        snapshot = _snapshot()
        assert diff_snapshots(snapshot, snapshot).empty


class TestPythonScope:
    SOURCE = """
value = 1

class Config:
    value = 2

    def read(self):
        return value

def outer():
    value = 3
    def inner():
        nonlocal value
        value = 4
    items = [value for value in range(3)]
    return inner, items

def uses_global():
    global value
    value = 9
"""

    def test_class_scope_is_invisible_to_nested_functions(self) -> None:
        table = analyze(self.SOURCE, module="m")
        module_binding = table.module_scope.bindings["value"]
        lines = {item.line for item in table.occurrences_of(module_binding)}
        # line 8 is `return value` inside Config.read
        assert 8 in lines

    def test_class_attribute_is_a_separate_binding(self) -> None:
        table = analyze(self.SOURCE, module="m")
        class_scope = next(item for item in table.scopes if item.kind is ScopeKind.CLASS)
        assert "value" in class_scope.bindings
        assert class_scope.bindings["value"] is not table.module_scope.bindings["value"]

    def test_comprehension_target_gets_its_own_scope(self) -> None:
        table = analyze(self.SOURCE, module="m")
        comprehensions = [item for item in table.scopes if item.kind is ScopeKind.COMPREHENSION]
        assert comprehensions and "value" in comprehensions[0].bindings

    def test_nonlocal_binds_to_the_enclosing_function(self) -> None:
        table = analyze(self.SOURCE, module="m")
        inner = next(item for item in table.scopes if item.name == "inner")
        assert "value" in inner.nonlocal_names

    def test_global_declaration_rebinds_module_scope(self) -> None:
        table = analyze(self.SOURCE, module="m")
        uses_global = next(item for item in table.scopes if item.name == "uses_global")
        assert "value" in uses_global.global_names
        assert table.resolve("value", uses_global.scope_id) is table.module_scope.bindings["value"]

    def test_walrus_and_with_and_except_targets_bind(self) -> None:
        source = (
            "import contextlib\n"
            "with contextlib.suppress(Exception) as ctx:\n"
            "    pass\n"
            "try:\n"
            "    pass\n"
            "except ValueError as err:\n"
            "    pass\n"
            "if (found := 1):\n"
            "    pass\n"
        )
        table = analyze(source, module="m")
        bindings = table.module_scope.bindings
        assert bindings["ctx"].kind is BindingKind.WITH_TARGET
        assert bindings["err"].kind is BindingKind.EXCEPT_TARGET
        assert bindings["found"].kind is BindingKind.ASSIGNMENT

    def test_two_same_named_siblings_get_distinct_scopes(self) -> None:
        source = "def f():\n    x = 1\n\ndef f():\n    y = 2\n"
        table = analyze(source, module="m")
        functions = [item for item in table.scopes if item.name == "f"]
        assert len(functions) == 2
        assert {"x"} == set(functions[0].bindings)
        assert {"y"} == set(functions[1].bindings)


class TestPythonOperations:
    def test_rename_respects_scope(self) -> None:
        source = (
            "VALUE = 1\n\n"
            "class Config:\n    VALUE = 2\n    def read(self):\n        return VALUE\n\n"
            "def compute(VALUE):\n    return VALUE + 1\n\n"
            "def use():\n    return VALUE\n"
        )
        result = rename_binding("m.py", source, old_name="VALUE", new_name="AMOUNT")
        updated = apply_edits(source, list(result.edits))
        assert "AMOUNT = 1" in updated
        assert "    VALUE = 2" in updated  # the class attribute is untouched
        assert "def compute(VALUE):" in updated  # the parameter is untouched
        assert "return AMOUNT" in updated

    def test_rename_refuses_a_capture(self) -> None:
        source = "def helper():\n    pass\n\ndef caller():\n    target = 1\n    return helper() + target\n"
        result = rename_binding("m.py", source, old_name="helper", new_name="target")
        assert result.blocked
        assert result.diagnostics[0].code == "rename_capture"

    def test_rename_warns_about_matching_string_literals(self) -> None:
        source = 'def handler():\n    pass\n\nROUTES = {"handler": handler}\n'
        result = rename_binding("m.py", source, old_name="handler", new_name="process")
        assert any(item.code == "string_literal_match" for item in result.diagnostics)
        assert result.edits  # a warning does not stop the rename

    def test_rename_is_idempotent(self) -> None:
        source = "def a():\n    return 1\n\nb = a()\n"
        once = apply_edits(source, list(rename_binding("m.py", source, old_name="a", new_name="c").edits))
        twice = rename_binding("m.py", once, old_name="a", new_name="c")
        assert twice.edits == ()

    def test_imported_symbol_rename_follows_plain_imports(self) -> None:
        source = "from acme.ledger import post_entry\n\nx = post_entry(1)\n"
        result = rename_imported_symbol(
            "m.py", source, module="acme.ledger", old_name="post_entry", new_name="record_entry"
        )
        updated = apply_edits(source, list(result.edits))
        assert updated == "from acme.ledger import record_entry\n\nx = record_entry(1)\n"

    def test_aliased_import_keeps_the_local_alias(self) -> None:
        source = "from acme.ledger import post_entry as pe\n\nx = pe(1)\n"
        result = rename_imported_symbol(
            "m.py", source, module="acme.ledger", old_name="post_entry", new_name="record_entry"
        )
        updated = apply_edits(source, list(result.edits))
        assert updated == "from acme.ledger import record_entry as pe\n\nx = pe(1)\n"

    def test_qualified_module_attribute_is_renamed(self) -> None:
        source = "import acme.ledger\n\nx = acme.ledger.post_entry(1)\n"
        result = rename_imported_symbol(
            "m.py", source, module="acme.ledger", old_name="post_entry", new_name="record_entry"
        )
        updated = apply_edits(source, list(result.edits))
        assert "acme.ledger.record_entry(1)" in updated
        assert "import acme.ledger\n" in updated

    def test_module_rename_leaves_similar_prefixes_alone(self) -> None:
        source = (
            "import acme_service.users\n"
            "from acme_service.users import find\n"
            "from acme_service_extra import x\n"
            "print(acme_service.users.find)\n"
        )
        result = rewrite_module_imports("m.py", source, old_module="acme_service", new_module="acme_core")
        updated = apply_edits(source, list(result.edits))
        assert "import acme_core.users" in updated
        assert "from acme_service_extra import x" in updated
        assert "print(acme_core.users.find)" in updated

    def test_relative_imports_are_reported_not_silently_skipped(self) -> None:
        source = "from . import sibling\nfrom .helpers import thing\n"
        result = rewrite_module_imports("m.py", source, old_module="pkg", new_module="pkg2")
        assert any(item.code == "relative_import_skipped" for item in result.diagnostics)

    def test_signature_change_preserves_untouched_parameter_text(self) -> None:
        source = 'def charge(customer, amount: int, currency="USD", *, retries=3, **kw):\n    return amount\n'
        result = change_signature(
            "m.py",
            source,
            qualified_function="charge",
            changes=[
                ParameterChange("rename", "currency", new_name="iso_code"),
                ParameterChange("add", "idempotency_key", annotation="str", default='""'),
            ],
        )
        updated = apply_edits(source, list(result.edits))
        assert 'iso_code="USD"' in updated  # quote style preserved, not normalised to '...'
        assert "retries=3" in updated
        assert "**kw" in updated
        assert 'idempotency_key: str=""' in updated

    def test_removing_a_parameter_that_a_call_site_passes_is_blocking(self) -> None:
        source = "def f(a, b=1):\n    return a\n\nf(1, b=2)\n"
        result = change_signature(
            "m.py", source, qualified_function="f", changes=[ParameterChange("remove", "b")]
        )
        assert any(item.code == "call_site_passes_removed_parameter" for item in result.diagnostics)
        assert result.blocked

    def test_method_signature_change_keeps_self(self) -> None:
        source = "class A:\n    def m(self, a, b=2):\n        return a\n"
        result = change_signature(
            "m.py", source, qualified_function="A.m", changes=[ParameterChange("remove", "b")]
        )
        assert "def m(self, a):" in apply_edits(source, list(result.edits))

    def test_unused_imports_are_removed_but_reexports_are_not(self) -> None:
        source = '"""D."""\nimport os\nimport sys\nfrom a import b\n\nprint(sys.argv, b)\n'
        updated = apply_edits(source, list(remove_unused_imports("m.py", source).edits))
        assert "import os" not in updated
        assert "import sys" in updated
        init = remove_unused_imports("pkg/__init__.py", source)
        assert init.edits == ()
        assert init.diagnostics[0].code == "package_init_skipped"

    def test_star_import_makes_unused_analysis_unsound_and_says_so(self) -> None:
        source = "from a import *\nimport os\n\nprint(thing)\n"
        result = remove_unused_imports("m.py", source)
        assert any(item.code == "star_import_present" for item in result.diagnostics)

    def test_add_import_is_idempotent(self) -> None:
        source = '"""D."""\nfrom __future__ import annotations\n\nimport os\n\nx = 1\n'
        once = apply_edits(source, list(add_import("m.py", source, module="acme.new", names=["Thing"]).edits))
        assert "from acme.new import Thing" in once
        assert add_import("m.py", once, module="acme.new", names=["Thing"]).edits == ()

    def test_dead_code_removal_refuses_on_a_string_reference(self) -> None:
        source = 'def unused():\n    pass\n\nHANDLERS = {"unused": 1}\n'
        result = remove_unreferenced_definition("m.py", source, name="unused")
        assert result.blocked
        assert result.diagnostics[0].code == "string_literal_match"

    def test_dead_code_removal_refuses_on_an_export(self) -> None:
        source = '__all__ = ["thing"]\n\ndef thing():\n    pass\n'
        result = remove_unreferenced_definition("m.py", source, name="thing")
        assert result.blocked
        assert result.diagnostics[0].code == "exported_symbol"

    def test_dangling_reference_detection_catches_a_half_done_rename(self) -> None:
        broken = "from acme.ledger import record_entry\n\nx = post_entry(1)\n"
        found = dangling_references("m.py", broken, names=["post_entry"])
        assert found and found[0].severity is Severity.BLOCKING


class TestRecipes:
    def test_every_builtin_recipe_round_trips_through_its_schema(self) -> None:
        for recipe in BUILTIN_RECIPES.values():
            assert Recipe.from_payload(recipe.to_payload()).digest == recipe.digest

    def test_every_builtin_recipe_declares_rollback_and_idempotence(self) -> None:
        for recipe in BUILTIN_RECIPES.values():
            assert recipe.rollback.strategy.value
            assert recipe.postconditions
            assert recipe.validation

    def test_a_recipe_without_idempotence_is_refused(self) -> None:
        payload = next(iter(BUILTIN_RECIPES.values())).to_payload()
        payload["spec"]["idempotence"] = {"secondRunExpectedDiff": "small"}
        with pytest.raises(ContractError) as error:
            Recipe.from_payload(payload)
        assert error.value.code in ("non_idempotent_recipe", "invalid_enum")

    def test_repository_wide_formatting_is_refused(self) -> None:
        payload = next(iter(BUILTIN_RECIPES.values())).to_payload()
        payload["spec"]["actions"][0]["formatPolicy"] = "repository"
        with pytest.raises(ContractError) as error:
            Recipe.from_payload(payload)
        assert error.value.code == "repository_wide_formatting_forbidden"

    def test_an_unsigned_plugin_is_refused(self) -> None:
        payload = next(iter(BUILTIN_RECIPES.values())).to_payload()
        payload["spec"]["plugin"] = {"runtime": "python", "entrypoint": "x:y"}
        with pytest.raises(ContractError) as error:
            Recipe.from_payload(payload)
        assert error.value.code == "unsigned_plugin"

    def test_declared_digest_must_match(self) -> None:
        payload = next(iter(BUILTIN_RECIPES.values())).to_payload()
        payload["metadata"]["digest"] = "sha256:" + "0" * 64
        with pytest.raises(ContractError) as error:
            Recipe.from_payload(payload)
        assert error.value.code == "recipe_digest_mismatch"

    def test_parameter_binding_validates_types_and_patterns(self) -> None:
        recipe = BUILTIN_RECIPES["python-rename-symbol@1.0.0"]
        bound = bind_parameters(recipe, {"from": "a", "to": "b", "module": "m"})
        assert bound["scope"] == "module"
        with pytest.raises(ContractError):
            bind_parameters(recipe, {"from": "a", "to": "not an identifier!", "module": "m"})
        with pytest.raises(ContractError):
            bind_parameters(recipe, {"from": "a", "to": "b", "module": "m", "surprise": 1})

    def test_cardinality_violation_is_reported(self) -> None:
        recipe = BUILTIN_RECIPES["python-rename-symbol@1.0.0"]
        action = recipe.action("rename")
        from elmos_repository_refactoring.recipe import SelectorResolution

        assert check_cardinality(action, SelectorResolution("rename", ())) is not None
        assert "matched 0 target(s)" in (check_cardinality(action, SelectorResolution("rename", ())) or "")

    def test_predicates_are_three_valued(self) -> None:
        recipe = BUILTIN_RECIPES["python-rename-symbol@1.0.0"]
        empty = evaluate_predicates(recipe.applicability, {})
        assert not empty.satisfied  # onUnknown=fail
        satisfied = evaluate_predicates(recipe.applicability, {"index": {"languages": ["python"]}})
        assert satisfied.satisfied

    def test_undecidable_approval_predicate_escalates(self) -> None:
        recipe = BUILTIN_RECIPES["python-rename-symbol@1.0.0"]
        report = evaluate_predicates(recipe.preconditions, {"index": {"symbol_exists": True}})
        assert report.requires_approval

    def test_selector_reports_out_of_scope_matches_instead_of_dropping_them(self) -> None:
        from elmos_repository_refactoring.buildgraph import build_graph
        from elmos_repository_refactoring.discovery import discover
        from elmos_repository_refactoring.index import build_index

        snapshot = _snapshot()
        inventory = discover(snapshot)
        index = build_index(snapshot, inventory, build_graph(snapshot, inventory))
        recipe = BUILTIN_RECIPES["python-rename-symbol@1.0.0"]
        resolution = resolve_selector(
            recipe.action("rename"),
            index,
            allowed_globs=["src/acme/ledger.py"],
            parameters={"from": "post_entry", "to": "x", "module": "acme.ledger"},
        )
        assert resolution.count == 1
        assert resolution.matches[0].path == "src/acme/ledger.py"

    def test_registry_payload_lists_operations(self) -> None:
        payload = registry_payload()
        assert payload["count"] == len(BUILTIN_RECIPES)
        rename = next(item for item in payload["recipes"] if item["reference"].startswith("python-rename-symbol"))
        assert "rename-symbol" in rename["operations"]
        assert "rename-imported-symbol" in rename["operations"]


class TestEndToEnd:
    RENAME_REQUEST = request_payload(
        intent={
            "type": "structural-refactor",
            "goals": ["rename `post_entry` to `record_entry` across the billing package"],
            "nonGoals": [],
        }
    )

    def test_intent_compiler_classifies_and_records_assumptions(self) -> None:
        result = dispatch(
            "refactor-intent-compiler",
            {"request": self.RENAME_REQUEST, "workspace": workspace_payload()},
        )
        intent = result["output"]["compiled_intent"]
        assert intent["operations"] == ["rename-symbol"]
        assert intent["goals"][0]["targets"][:2] == ["post_entry", "record_entry"]
        assert intent["acceptancePredicates"]

    def test_intent_compiler_reports_a_constraint_conflict(self) -> None:
        conflicting = request_payload(
            intent={"type": "performance-refactor", "goals": ["improve latency of the charge path"]},
            constraints={"behaviorCompatibility": "strict"},
        )
        result = dispatch(
            "refactor-intent-compiler", {"request": conflicting, "workspace": workspace_payload()}
        )
        assert result["status"] == Status.BLOCKED.value
        assert any("constraint conflict" in item for item in result["reasons"])

    def test_impact_analysis_reports_reasons_and_uncovered_paths(self) -> None:
        result = dispatch(
            "change-impact-analysis",
            {"request": self.RENAME_REQUEST, "workspace": workspace_payload()},
        )
        assert result["status"] == Status.SUCCEEDED.value
        report = result["output"]["impact_report"]
        assert report["changeClosure"]["seeds"]
        assert Decimal(report["riskAssessment"]["unknownPenalty"]) > 0
        assert report["riskAssessment"]["reasons"]

    def test_unknown_is_not_no_impact(self) -> None:
        result = dispatch(
            "change-impact-analysis",
            {"request": self.RENAME_REQUEST, "workspace": workspace_payload()},
        )
        risk = result["output"]["risk_assessment"]
        assert risk["riskClass"] in ("R2", "R3", "R4")

    def test_synthesis_locks_recipes_with_digests(self) -> None:
        result = dispatch(
            "recipe-synthesis", {"request": self.RENAME_REQUEST, "workspace": workspace_payload()}
        )
        assert result["status"] == Status.SUCCEEDED.value
        lock = result["output"]["recipeLock"]
        assert lock["recipes"][0]["digest"].startswith("sha256:")
        assert lock["indexDigest"].startswith("sha256:")
        assert result["output"]["dryRunPatch"]["changedFiles"] >= 2

    def test_transform_renames_definition_and_importers(self) -> None:
        result = dispatch(
            "deterministic-transform-executor",
            {"request": self.RENAME_REQUEST, "workspace": workspace_payload()},
        )
        assert result["status"] == Status.SUCCEEDED.value
        diff = result["output"]["unifiedDiff"]
        assert "-def post_entry(" in diff
        assert "+def record_entry(" in diff
        assert "-from acme.ledger import post_entry" in diff
        assert "+from acme.ledger import record_entry" in diff
        assert "-        entry = post_entry(" in diff

    def test_transform_proves_idempotence(self) -> None:
        result = dispatch(
            "deterministic-transform-executor",
            {"request": self.RENAME_REQUEST, "workspace": workspace_payload()},
        )
        assert result["output"]["transformEvidence"]["idempotent"] is True
        assert result["output"]["transformEvidence"]["secondRunPaths"] == []

    def test_transform_is_deterministic_across_runs(self) -> None:
        first = dispatch(
            "deterministic-transform-executor",
            {"request": self.RENAME_REQUEST, "workspace": workspace_payload()},
        )
        second = dispatch(
            "deterministic-transform-executor",
            {"request": self.RENAME_REQUEST, "workspace": workspace_payload()},
        )
        assert first["output"]["patchSet"]["changes"] == second["output"]["patchSet"]["changes"]
        assert first["evidence"]["patchDigest"] == second["evidence"]["patchDigest"]

    def test_source_map_traces_every_hunk_to_an_action(self) -> None:
        result = dispatch(
            "deterministic-transform-executor",
            {"request": self.RENAME_REQUEST, "workspace": workspace_payload()},
        )
        source_map = result["output"]["sourceMap"]
        assert source_map
        for entry in source_map:
            assert entry["actionIds"], f"hunk {entry['hunkId']} has no owning action"

    def test_analyze_only_mode_cannot_transform(self) -> None:
        analyze_only = request_payload(
            intent={"type": "structural-refactor", "goals": ["rename `post_entry` to `record_entry`"]},
            execution={"mode": "analyze-only", "createPullRequest": False},
        )
        result = dispatch(
            "deterministic-transform-executor",
            {"request": analyze_only, "workspace": workspace_payload()},
        )
        assert result["status"] == Status.REJECTED.value

    def test_a_goal_with_no_available_recipe_is_reported_not_faked(self) -> None:
        unsupported = request_payload(
            intent={
                "type": "architecture-refactor",
                "goals": ["split the payment orchestration out of the legacy order service"],
            }
        )
        result = dispatch("recipe-synthesis", {"request": unsupported, "workspace": workspace_payload()})
        assert result["status"] == Status.BLOCKED.value
        assert any("has no available recipe" in item for item in result["reasons"])

    def test_transform_blocks_when_nothing_is_applicable(self) -> None:
        unsupported = request_payload(
            intent={
                "type": "architecture-refactor",
                "goals": ["split the payment orchestration out of the legacy order service"],
            }
        )
        result = dispatch(
            "deterministic-transform-executor",
            {"request": unsupported, "workspace": workspace_payload()},
        )
        assert result["status"] == Status.BLOCKED.value
        assert result["output"]["patchSet"]["changedFiles"] == 0 if "patchSet" in result["output"] else True

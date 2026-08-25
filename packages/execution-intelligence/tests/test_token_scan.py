import pytest

from elmos_execution_intelligence.token_scan import TokenCounter, scan_tokens

SKILL = """---
name: demo-skill
description: A demo skill used by the token scan test.
version: 1.0.0
---

# demo

Body text.
"""


def _tree(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("hello world " * 200, encoding="utf-8")
    (tmp_path / "skills" / "demo").mkdir(parents=True)
    (tmp_path / "skills" / "demo" / "SKILL.md").write_text(SKILL, encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("x" * 100_000, encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return tmp_path


def test_scan_counts_text_and_skips_vendored_and_binary(tmp_path):
    result = scan_tokens(_tree(tmp_path))
    paths = {item["path"] for item in result["largest_files"]}
    assert "docs/guide.md" in paths
    assert "skills/demo/SKILL.md" in paths
    assert not any(path.startswith("node_modules/") for path in paths)
    assert "image.png" not in paths
    assert result["totals"]["files"] == 2


def test_skill_frontmatter_becomes_catalog_cost(tmp_path):
    result = scan_tokens(_tree(tmp_path))
    assert result["totals"]["skill_files"] == 1
    assert result["totals"]["skill_catalog_tokens"] > 0
    assert result["totals"]["skill_catalog_tokens"] < result["totals"]["skill_body_tokens"]
    assert result["skills"][0]["name"] == "demo-skill"


def test_group_totals_reconcile_with_the_grand_total(tmp_path):
    result = scan_tokens(_tree(tmp_path))
    assert sum(g["estimated_tokens"] for g in result["groups"]) == result["totals"]["estimated_tokens"]
    assert sum(g["files"] for g in result["groups"]) == result["totals"]["files"]


def test_oversized_file_raises_a_context_pressure_finding(tmp_path):
    _tree(tmp_path)
    (tmp_path / "huge.md").write_text("word " * 400_000, encoding="utf-8")
    result = scan_tokens(tmp_path)
    kinds = {finding["kind"] for finding in result["findings"]}
    assert "oversized-file" in kinds


def test_extra_ignore_dir_is_honoured(tmp_path):
    _tree(tmp_path)
    result = scan_tokens(tmp_path, extra_ignore_dirs=("docs",))
    assert all(not item["path"].startswith("docs/") for item in result["largest_files"])


def test_scan_root_must_exist_and_be_a_directory(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        scan_tokens(tmp_path / "missing")
    target = tmp_path / "file.md"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        scan_tokens(target)


def test_cjk_costs_more_tokens_per_character_than_latin():
    counter = TokenCounter()
    if counter.exact:
        return
    assert counter.count("中文字符测试") > counter.count("abcdef")
    assert counter.count("") == 0


def test_non_canonical_build_directories_are_ignored_by_glob(tmp_path):
    _tree(tmp_path)
    stale = tmp_path / "apps" / ".next-e2e-31415" / "static"
    stale.mkdir(parents=True)
    (stale / "bundle.js").write_text("var a=1;" * 20_000, encoding="utf-8")
    result = scan_tokens(tmp_path)
    assert all(".next-e2e" not in item["path"] for item in result["largest_files"])
    assert ".next*" in result["ignored_directory_globs"]


CALIBRATION = {
    "version": "test",
    "global_factor": 0.80,
    "by_extension": {".md": {"factor": 1.25, "files": 10, "real_tokens": 10000}},
    "method": {"reference_tokenizer": {"name": "test tokenizer"}},
}


def test_without_calibration_the_raw_heuristic_is_reported(tmp_path):
    _tree(tmp_path)
    result = scan_tokens(tmp_path)
    assert result["calibration"] is None
    assert result["totals"]["calibrated_tokens"] is None
    assert all("calibrated_tokens" not in item for item in result["largest_files"])


def test_calibration_corrects_per_extension_and_falls_back_globally(tmp_path):
    _tree(tmp_path)
    (tmp_path / "data.json").write_text('{"a": 1}\n' * 200, encoding="utf-8")
    result = scan_tokens(tmp_path, calibration=CALIBRATION)
    if result["exact_counts"]:
        return  # a real tokenizer is present; calibration is not applied and must not be

    by_path = {item["path"]: item for item in result["largest_files"]}
    md = by_path["docs/guide.md"]
    assert md["calibration_factor"] == 1.25
    assert md["calibrated_tokens"] == round(md["estimated_tokens"] / 1.25)

    other = by_path["data.json"]
    assert other["calibration_factor"] == 0.80, "an unlisted extension uses the global factor"
    assert other["calibrated_tokens"] > other["estimated_tokens"], "a factor below 1 corrects upward"


def test_calibrated_total_reconciles_with_the_per_file_numbers(tmp_path):
    _tree(tmp_path)
    result = scan_tokens(tmp_path, calibration=CALIBRATION, include_file_list=True)
    if result["exact_counts"]:
        return
    assert result["totals"]["calibrated_tokens"] == sum(
        item["calibrated_tokens"] for item in result["files"])


def test_calibration_provenance_is_carried_into_the_output(tmp_path):
    _tree(tmp_path)
    result = scan_tokens(tmp_path, calibration=CALIBRATION)
    assert result["calibration"]["version"] == "test"
    assert result["calibration"]["reference_tokenizer"]["name"] == "test tokenizer"
    assert "does not make the count exact" in result["calibration"]["note"]


def test_the_shipped_calibration_file_is_self_consistent():
    from conftest import ROOT

    from elmos_execution_intelligence.io_utils import load_json

    calibration = load_json(ROOT / "config" / "token-count-calibration.json")
    method = calibration["method"]
    assert method["heuristic_tokens"] / method["real_tokens"] == pytest.approx(
        calibration["global_factor"], abs=1e-4)
    for suffix, entry in calibration["by_extension"].items():
        assert suffix.startswith("."), suffix
        assert entry["files"] >= calibration["minimum_sample_files"]
        assert entry["real_tokens"] >= calibration["minimum_sample_tokens"]
    assert "not the tokenizer of any current model" in method["reference_tokenizer"]["caveat"].lower() \
        or "NOT the tokenizer" in method["reference_tokenizer"]["caveat"]

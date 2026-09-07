"""Skill split advice, and the git-derived human anchor."""

import pytest

from elmos_execution_intelligence.human_anchor import (
    anchor_from_log,
    compare_to_forecast,
    parse_git_log,
    render_anchor,
)
from elmos_execution_intelligence.skill_advice import advise, advise_file, render_advice, split_sections

BIG_SKILL = """---
name: heavy-skill
description: A skill that has grown too heavy.
---

# heavy-skill

## 目标

Do the thing.

## 触发条件

When asked.

## 执行流程

1. step one
2. step two

## 示例

""" + ("Example line with quite a lot of words in it to make this section heavy.\n" * 400) + """

## 故障排查

""" + ("Troubleshooting entry describing a failure mode and its remedy.\n" * 300) + """

## 输出

- a file
"""


def _skill(tmp_path, text=BIG_SKILL, name="SKILL.md"):
    path = tmp_path / "skills" / "heavy"
    path.mkdir(parents=True, exist_ok=True)
    target = path / name
    target.write_text(text, encoding="utf-8")
    return target


def test_sections_are_cut_at_headings_with_the_preamble_kept(tmp_path):
    sections = split_sections(BIG_SKILL)
    titles = [s["title"] for s in sections]
    assert titles[0] == "<preamble>"
    assert "示例" in titles and "目标" in titles
    assert all(s["tokens"] > 0 for s in sections)


def test_operational_sections_are_never_proposed_for_a_move(tmp_path):
    target = _skill(tmp_path)
    advice = advise_file(target, threshold=1000, root=tmp_path)
    moved = {item["title"] for item in advice["proposed_moves"]}
    for protected in ("目标", "触发条件", "执行流程", "输出"):
        assert protected not in moved


def test_reference_sections_are_proposed_largest_first(tmp_path):
    target = _skill(tmp_path)
    advice = advise_file(target, threshold=1000, root=tmp_path)
    moved = [item["title"] for item in advice["proposed_moves"]]
    assert moved[0] == "示例", moved
    assert advice["tokens_moved"] > 0
    assert advice["body_after"] < advice["tokens"]


def test_a_skill_under_the_threshold_gets_no_advice(tmp_path):
    target = _skill(tmp_path, text="# tiny\n\n## 目标\n\nsmall\n")
    assert advise_file(target, threshold=5000, root=tmp_path) is None


def test_a_skill_that_cannot_fit_is_told_to_split_instead(tmp_path):
    text = "# huge\n\n## 目标\n\n" + ("Mandatory operational detail.\n" * 3000)
    target = _skill(tmp_path, text=text)
    advice = advise_file(target, threshold=1000, root=tmp_path)
    assert advice["fits_after"] is False
    assert "splitting it into separate skills" in advice["residual_note"]


def test_advice_only_covers_what_the_scan_flagged(tmp_path):
    _skill(tmp_path)
    scan = {"findings": [
        {"kind": "oversized-skill", "path": "skills/heavy/SKILL.md"},
        {"kind": "oversized-file", "path": "somewhere/else.md"},
    ]}
    report = advise(tmp_path, scan, threshold=1000)
    assert report["flagged"] == 1
    assert [item["path"] for item in report["advice"]] == ["skills/heavy/SKILL.md"]
    assert "No file is rewritten" in report["not_applied"]


def test_the_rendered_advice_names_the_protection_rule(tmp_path):
    _skill(tmp_path)
    scan = {"findings": [{"kind": "oversized-skill", "path": "skills/heavy/SKILL.md"}]}
    text = render_advice(advise(tmp_path, scan, threshold=1000))
    assert "SKILL_SPLIT_ADVICE" in text
    assert "acceptance" in text or "验收" in text


# ------------------------------------------------------------------ human anchor ----

LOG = "\n".join([
    "aaa\tAlice\t2026-01-05\tfeat: one",
    "bbb\tAlice\t2026-01-05\tfeat: two",
    "ccc\tBob\t2026-01-07\tfix: three",
    "ddd\tAlice\t2026-01-20\tfeat: four",
])


def _log_file(tmp_path, text=LOG):
    path = tmp_path / "git.log"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_log_export_is_parsed_into_commits(tmp_path):
    rows = parse_git_log(_log_file(tmp_path))
    assert len(rows) == 4
    assert {row["author"] for row in rows} == {"Alice", "Bob"}


def test_an_unparseable_export_is_refused_with_the_command_shown(tmp_path):
    with pytest.raises(ValueError, match="git .*log"):
        parse_git_log(_log_file(tmp_path, "not a git log at all\n"))


def test_author_days_are_counted_once_per_day_not_per_commit(tmp_path):
    anchor = anchor_from_log(parse_git_log(_log_file(tmp_path)), "demo")
    # Alice on the 5th (two commits, one day) and the 20th; Bob on the 7th.
    assert anchor["author_active_days"] == 3
    assert anchor["distinct_active_days"] == 3
    assert anchor["commits"] == 4
    assert anchor["calendar_days"] == 16


def test_the_bounds_are_ordered_and_labelled_as_bounds(tmp_path):
    anchor = anchor_from_log(parse_git_log(_log_file(tmp_path)), "demo",
                             work_hours_per_day=8.0, focus_ratio=0.5)
    bounds = anchor["person_hours_bounds"]
    assert bounds["upper"] == pytest.approx(24.0)
    assert bounds["lower"] == pytest.approx(12.0)
    assert any("not a person-hour measurement" in item.lower() for item in anchor["what_this_is_not"])


def test_a_forecast_outside_the_bounds_is_called_out(tmp_path):
    anchor = anchor_from_log(parse_git_log(_log_file(tmp_path)), "demo")
    high = compare_to_forecast(anchor, {"person_hours": {"p50": 100_000},
                                        "calendar_weeks": {"p50": 40}})
    assert high["verdict"] == "forecast_above_anchor"
    low = compare_to_forecast(anchor, {"person_hours": {"p50": 1},
                                       "calendar_weeks": {"p50": 1}})
    assert low["verdict"] == "forecast_below_anchor"
    inside = compare_to_forecast(anchor, {"person_hours": {"p50": 20},
                                          "calendar_weeks": {"p50": 2}})
    assert inside["verdict"] == "consistent"
    assert "does not validate" in inside["caveat"]


def test_the_rendered_anchor_states_what_it_is_not(tmp_path):
    anchor = anchor_from_log(parse_git_log(_log_file(tmp_path)), "demo")
    text = render_anchor(anchor, None)
    assert "不是" in text
    assert "HUMAN_BASELINE_ANCHOR" in text

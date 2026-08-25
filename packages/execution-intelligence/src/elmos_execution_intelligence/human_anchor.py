"""Anchor the human baseline to something that actually happened.

The human estimate in a project profile is otherwise pure judgement. This module
derives a *measured* anchor from the repository's own git history: how many
distinct authors touched a scope, over how many calendar days, in how many
commits, with how many active days.

It deliberately does not run git. It reads an exported log, because the export is
a read-only operation someone runs deliberately in their own checkout, and
because that keeps this package free of any assumption about being inside a
working tree.

What it produces is an anchor, not a person-hour count. Git records when someone
committed, not how long they worked; active days are an upper bound on elapsed
effort and a lower bound on nothing. The report says so on every figure.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

#: The export this module reads. One record per line, fields tab-separated.
GIT_LOG_COMMAND = (
    "git -c gc.auto=0 log --no-merges --date=short "
    "--pretty=format:'%H%x09%an%x09%ad%x09%s' -- <paths>"
)


def parse_git_log(path: str | Path) -> list[dict[str, str]]:
    """Read the tab-separated export produced by GIT_LOG_COMMAND."""
    source = Path(path)
    rows: list[dict[str, str]] = []
    for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip().strip("'")
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        commit, author, day = parts[0], parts[1], parts[2]
        subject = parts[3] if len(parts) > 3 else ""
        try:
            parsed = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError:
            continue
        rows.append({"commit": commit, "author": author, "date": parsed.isoformat(),
                     "subject": subject})
    if not rows:
        raise ValueError(
            f"{source}: no commits parsed. Expected the tab-separated export from:\n  {GIT_LOG_COMMAND}"
        )
    return rows


def anchor_from_log(
    rows: list[dict[str, str]],
    scope_label: str,
    work_hours_per_day: float = 8.0,
    focus_ratio: float = 0.65,
) -> dict[str, Any]:
    """Turn commit records into a bounded human-effort anchor."""
    days = sorted({date.fromisoformat(row["date"]) for row in rows})
    authors = Counter(row["author"] for row in rows)
    per_author_days: dict[str, set[date]] = {}
    for row in rows:
        per_author_days.setdefault(row["author"], set()).add(date.fromisoformat(row["date"]))

    calendar_days = (days[-1] - days[0]).days + 1
    author_active_days = sum(len(seen) for seen in per_author_days.values())

    # Two bounds, both honest, deliberately far apart:
    #   upper: every author-day someone committed on was a full working day
    #   lower: the same author-days at the configured focus ratio
    upper_person_hours = author_active_days * work_hours_per_day
    lower_person_hours = upper_person_hours * focus_ratio

    return {
        "schema_version": "1.0.0",
        "artifact": "human-baseline-anchor",
        "scope": scope_label,
        "commits": len(rows),
        "authors": len(per_author_days),
        "authors_by_commits": dict(authors.most_common()),
        "first_commit_date": days[0].isoformat(),
        "last_commit_date": days[-1].isoformat(),
        "calendar_days": calendar_days,
        "calendar_weeks": round(calendar_days / 7.0, 2),
        "distinct_active_days": len(days),
        "author_active_days": author_active_days,
        "person_hours_bounds": {
            "lower": round(lower_person_hours, 1),
            "upper": round(upper_person_hours, 1),
            "basis": (
                f"author-active-days ({author_active_days}) x {work_hours_per_day}h, "
                f"lower bound applies focus_ratio {focus_ratio}"
            ),
        },
        "what_this_is_not": [
            "Not a person-hour measurement. Git records when someone committed, not how long they worked.",
            "A day with one commit and a day with forty both count once.",
            "Work that never landed as a commit is invisible here.",
            "Calendar span includes weekends, holidays and time on other projects.",
        ],
        "how_to_use": (
            "Compare the order of magnitude against the human baseline in the forecast. If the forecast "
            "sits outside these bounds, one of the two is wrong and it is worth finding out which."
        ),
    }


def compare_to_forecast(anchor: dict[str, Any], human_effort: dict[str, Any]) -> dict[str, Any]:
    """Put the anchor and the forecast side by side and say whether they agree."""
    forecast_hours = float(human_effort["person_hours"]["p50"])
    forecast_weeks = float(human_effort["calendar_weeks"]["p50"])
    lower = float(anchor["person_hours_bounds"]["lower"])
    upper = float(anchor["person_hours_bounds"]["upper"])

    if forecast_hours < lower:
        verdict = "forecast_below_anchor"
        detail = (
            f"The forecast ({forecast_hours:,.0f} person-hours) is below the anchor's lower bound "
            f"({lower:,.0f}). Either the scope being forecast is smaller than the scope that was "
            "committed, or the forecast is optimistic."
        )
    elif forecast_hours > upper:
        verdict = "forecast_above_anchor"
        detail = (
            f"The forecast ({forecast_hours:,.0f} person-hours) is above the anchor's upper bound "
            f"({upper:,.0f}). Either the remaining work is genuinely larger than what has been "
            "committed so far, or the forecast is pessimistic."
        )
    else:
        verdict = "consistent"
        detail = (
            f"The forecast ({forecast_hours:,.0f} person-hours) sits inside the anchor's bounds "
            f"({lower:,.0f}-{upper:,.0f}). Consistent, which is weak evidence of being right."
        )

    return {
        "verdict": verdict,
        "detail": detail,
        "forecast_person_hours_p50": forecast_hours,
        "forecast_calendar_weeks_p50": forecast_weeks,
        "anchor_person_hours_bounds": [lower, upper],
        "anchor_calendar_weeks": anchor["calendar_weeks"],
        "caveat": (
            "Agreement here does not validate the forecast. The anchor is coarse by construction; it "
            "can only catch an answer that is wrong by an order of magnitude."
        ),
    }


def render_anchor(anchor: dict[str, Any], comparison: dict[str, Any] | None) -> str:
    from .io_utils import fmt, markdown_table

    bounds = anchor["person_hours_bounds"]
    body = [
        "# HUMAN_BASELINE_ANCHOR",
        "",
        f"- 范围：`{anchor['scope']}`",
        f"- 提交：{fmt(anchor['commits'])}，作者：{anchor['authors']} 人",
        f"- 时间跨度：{anchor['first_commit_date']} → {anchor['last_commit_date']}"
        f"（{fmt(anchor['calendar_days'])} 个日历日 / {anchor['calendar_weeks']} 周）",
        f"- 有提交的日子：{anchor['distinct_active_days']} 天；作者-活跃日合计：{anchor['author_active_days']}",
        "",
        "## 人时区间（上下界，不是测量值）",
        "",
        markdown_table(["下界", "上界", "口径"],
                       [[fmt(bounds["lower"]), fmt(bounds["upper"]), bounds["basis"]]]),
        "",
        "## 按作者",
        "",
        markdown_table(["作者", "提交数"],
                       [[name, fmt(count)] for name, count in
                        list(anchor["authors_by_commits"].items())[:15]]),
        "",
        "## 这个数字**不是**什么",
        "",
        *[f"- {item}" for item in anchor["what_this_is_not"]],
        "",
        f"> {anchor['how_to_use']}",
    ]
    if comparison:
        body += [
            "",
            "## 与预测对照",
            "",
            f"- 结论：**{comparison['verdict']}**",
            f"- {comparison['detail']}",
            "",
            f"> {comparison['caveat']}",
        ]
    return "\n".join(body)

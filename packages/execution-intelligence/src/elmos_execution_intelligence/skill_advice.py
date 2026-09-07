"""Turn an oversized-skill finding into an actionable split.

The scanner already says *which* SKILL.md files are too heavy. That is where most
tooling stops, and it is not actionable: nobody wants to reread a 6,000-token file
to decide what to cut. This module says *which sections* to move and how much each
move buys.

The rule it applies is the one that makes a skill cheap to activate: the body
should carry what the agent needs on every activation, and everything it needs
only sometimes -- long examples, exhaustive tables, appendices, troubleshooting
catalogues -- belongs in ``references/`` where it is read on demand.

Nothing here rewrites a file. It produces advice a human approves.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .token_scan import TokenCounter

HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$", re.MULTILINE)

#: Sections whose titles mark reference material: useful, but not needed on every
#: activation. Matched case-insensitively against the heading text.
REFERENCE_HINTS = (
    "example", "examples", "样例", "示例", "范例",
    "appendix", "附录",
    "reference", "参考", "参考资料",
    "troubleshoot", "故障", "排查", "常见问题", "faq",
    "table", "表", "对照表", "清单",
    "changelog", "history", "历史", "变更",
    "advanced", "进阶", "深入",
    "full", "complete", "exhaustive", "完整",
)

#: Sections that must stay in the body whatever their size: without them the skill
#: cannot be activated correctly at all.
KEEP_HINTS = (
    "目标", "goal", "purpose",
    "触发", "trigger", "when to use",
    "输入", "input",
    "输出", "output",
    "执行流程", "steps", "procedure", "workflow",
    "验收", "acceptance",
    "失败", "failure", "降级",
)


def _classify(title: str) -> str:
    lowered = title.lower()
    if any(hint in lowered for hint in KEEP_HINTS):
        return "keep"
    if any(hint in lowered for hint in REFERENCE_HINTS):
        return "move"
    return "review"


def split_sections(text: str) -> list[dict[str, Any]]:
    """Cut a markdown document at its headings, preserving the preamble."""
    counter = TokenCounter()
    counter._encoding = None  # advice is about the scanner's own accounting
    matches = list(HEADING.finditer(text))
    sections: list[dict[str, Any]] = []

    if not matches or matches[0].start() > 0:
        head = text[: matches[0].start()] if matches else text
        if head.strip():
            sections.append({
                "title": "<preamble>", "level": 0, "tokens": counter.count(head),
                "characters": len(head), "classification": "keep",
            })

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.start():end]
        title = match.group("title")
        sections.append({
            "title": title,
            "level": len(match.group("hashes")),
            "tokens": counter.count(body),
            "characters": len(body),
            "classification": _classify(title),
        })
    return sections


def advise_file(path: str | Path, threshold: int, root: Path | None = None) -> dict[str, Any] | None:
    """Advice for one SKILL.md, or None when it is already under the threshold."""
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    counter = TokenCounter()
    counter._encoding = None
    total = counter.count(text)
    if total < threshold:
        return None

    sections = split_sections(text)
    movable = sorted(
        (s for s in sections if s["classification"] == "move"),
        key=lambda s: -int(s["tokens"]),
    )
    reviewable = sorted(
        (s for s in sections if s["classification"] == "review"),
        key=lambda s: -int(s["tokens"]),
    )

    # Take movable sections until the body would fit, then, if that is not enough,
    # name the review candidates. Never propose moving a "keep" section: an
    # activation that has lost its trigger conditions is worse than a fat one.
    plan: list[dict[str, Any]] = []
    remaining = total
    for section in movable:
        if remaining < threshold:
            break
        plan.append({**section, "reason": "reference material by heading"})
        remaining -= int(section["tokens"])
    if remaining >= threshold:
        for section in reviewable:
            if remaining < threshold:
                break
            if int(section["tokens"]) < total * 0.10:
                continue
            plan.append({**section, "reason": "large section with an unclassified heading; needs a human call"})
            remaining -= int(section["tokens"])

    relative = source.relative_to(root).as_posix() if root else source.as_posix()
    return {
        "path": relative,
        "tokens": total,
        "threshold": threshold,
        "over_by": total - threshold,
        "sections": len(sections),
        "proposed_moves": plan,
        "tokens_moved": sum(int(item["tokens"]) for item in plan),
        "body_after": remaining,
        "fits_after": remaining < threshold,
        "suggested_reference_dir": str(Path(relative).parent / "references"),
        "residual_note": (
            None if remaining < threshold else
            "Moving every reference-classified section is still not enough. This skill is doing "
            "too many jobs; splitting it into separate skills is the real fix."
        ),
    }


def advise(
    root: str | Path,
    scan: dict[str, Any],
    threshold: int = 5000,
    top_n: int = 50,
) -> dict[str, Any]:
    """Build split advice for every oversized skill the scan flagged."""
    base = Path(root).resolve()
    flagged = [
        finding["path"] for finding in scan.get("findings", [])
        if finding.get("kind") == "oversized-skill"
    ]
    advice = []
    for relative in flagged[:top_n]:
        item = advise_file(base / relative, threshold, root=base)
        if item:
            advice.append(item)
    advice.sort(key=lambda item: -int(item["tokens"]))

    return {
        "schema_version": "1.0.0",
        "artifact": "skill-split-advice",
        "root": str(base),
        "threshold": threshold,
        "flagged": len(flagged),
        "advised": len(advice),
        "total_tokens_over_threshold": sum(int(i["over_by"]) for i in advice),
        "total_tokens_movable": sum(int(i["tokens_moved"]) for i in advice),
        "cannot_fit_by_moving_alone": [i["path"] for i in advice if not i["fits_after"]],
        "advice": advice,
        "rule": (
            "Sections that state the goal, triggers, inputs, outputs, steps, acceptance or failure "
            "handling are never proposed for a move: a skill that has lost those is broken, not slim."
        ),
        "not_applied": "This is advice. No file is rewritten; a human decides and edits.",
    }


def render_advice(report: dict[str, Any]) -> str:
    from .io_utils import fmt, markdown_table

    rows = [
        [f"`{item['path']}`", fmt(item["tokens"]), fmt(item["tokens_moved"]),
         fmt(item["body_after"]), "是" if item["fits_after"] else "**否**",
         len(item["proposed_moves"])]
        for item in report["advice"][:30]
    ]
    body = [
        "# SKILL_SPLIT_ADVICE",
        "",
        f"- 阈值：{fmt(report['threshold'])} tokens",
        f"- 被扫描器标记：{report['flagged']} 个；本报告给出建议：{report['advised']} 个",
        f"- 超出阈值合计：{fmt(report['total_tokens_over_threshold'])} tokens",
        f"- 建议移出合计：{fmt(report['total_tokens_movable'])} tokens",
        "",
        markdown_table(["Skill", "当前", "建议移出", "移出后正文", "达标", "涉及小节"], rows),
        "",
    ]
    if report["cannot_fit_by_moving_alone"]:
        body += [
            "## 光靠搬小节不够的",
            "",
            *[f"- `{path}`" for path in report["cannot_fit_by_moving_alone"]],
            "",
            "> 这些 Skill 在做太多件事。真正的修法是拆成多个 Skill，而不是继续瘦身。",
            "",
        ]
    body += ["## 逐个建议", ""]
    for item in report["advice"][:15]:
        body += [
            f"### `{item['path']}`（{fmt(item['tokens'])} tokens，超出 {fmt(item['over_by'])}）",
            "",
            f"建议移到 `{item['suggested_reference_dir']}/`：",
            "",
        ]
        if item["proposed_moves"]:
            body.append(markdown_table(
                ["小节", "层级", "tokens", "依据"],
                [[m["title"], "#" * int(m["level"]) if m["level"] else "—",
                  fmt(m["tokens"]), m["reason"]] for m in item["proposed_moves"]]))
        else:
            body.append("_没有可搬的小节：正文里全是必须常驻的内容。_")
        body.append("")
    body += ["---", "", f"> {report['rule']}", "", f"> {report['not_applied']}"]
    return "\n".join(body)

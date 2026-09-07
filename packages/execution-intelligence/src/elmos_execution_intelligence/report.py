"""Markdown and CSV rendering of a forecast."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .io_utils import fmt, markdown_table, write_text
from .simulation import TOKEN_FIELDS

_ENVELOPE = ("p50", "p80", "p90", "worst_case")
_CATEGORY_LABELS = {
    "input": "input（未命中缓存的输入）",
    "cached_input": "cached_input（缓存命中读取）",
    "cache_write": "cache_write（写入缓存）",
    "output": "output（可见输出）",
    "reasoning_output": "reasoning_output（推理输出）",
    "total": "**total（分类之和）**",
}


def _envelope_row(label: str, values: dict[str, Any], digits: int = 0) -> list[str]:
    return [label] + [fmt(round(float(values[key]), digits) if digits else int(values[key]), digits)
                      for key in _ENVELOPE]


def write_token_budget(forecast: dict[str, Any], out: Path) -> None:
    project = forecast["project"]
    tokens = forecast["tokens"]
    task_rows = forecast.get("task_tokens", [])
    scan = forecast.get("static_scan")

    rows = [_envelope_row(_CATEGORY_LABELS[field], tokens[field]) for field in list(TOKEN_FIELDS) + ["total"]]
    body = [
        f"# TOKEN_BUDGET — {project['project_id']}",
        "",
        f"- 模式：`{project['mode']}`",
        f"- 完成定义：`{project['definition_of_done']['level']}`",
        f"- Monte Carlo：{forecast['system_runtime']['runs']} 次，seed={forecast['system_runtime']['seed']}",
        f"- 置信度：{project.get('confidence')}",
        "",
        "## 1. 整体 Token 区间",
        "",
        markdown_table(["类别", "P50", "P80", "P90", "Worst Case"], rows),
        "",
        "> 五个分类互不重叠，`total` 是它们的和；任何时候都不得把 `total` 再加回某个分类。",
        "",
        "## 2. 按任务追溯（P50 降序）",
        "",
    ]
    trace_rows = [
        [row["task_id"], row["name"], fmt(int(row["total_tokens"]["p50"])),
         fmt(int(row["total_tokens"]["p80"])), fmt(int(row["total_tokens"]["p90"])),
         fmt(int(row["total_tokens"]["worst_case"]))]
        for row in task_rows
    ]
    body.append(markdown_table(["Task", "名称", "P50", "P80", "P90", "Worst"], trace_rows))
    body.append("")
    body.append("> 任务分位数之和不等于项目分位数：分位数不可相加。项目区间来自整体 Monte Carlo 抽样。")
    body.append("")

    if scan:
        totals = scan["totals"]
        body += [
            "## 3. 静态语料扫描（一次性读取成本）",
            "",
            f"- 扫描根：`{scan['root']}`",
            f"- 计数方式：`{scan['counting_method']}`（exact={scan['exact_counts']}）",
            f"- 文件数：{fmt(totals['files'])}，字符数：{fmt(totals['characters'])}",
            f"- 一次性全量读取估算：**{fmt(totals['estimated_tokens'])} tokens**",
            f"- Skill 目录常驻（name+description）：{fmt(totals['skill_catalog_tokens'])} tokens，"
            f"Skill 正文合计：{fmt(totals['skill_body_tokens'])} tokens",
            "",
            markdown_table(
                ["目录", "文件数", "估算 tokens"],
                [[g["group"], fmt(g["files"]), fmt(g["estimated_tokens"])] for g in scan["groups"][:15]],
            ),
            "",
            "> 静态扫描回答的是「把磁盘上的材料喂给模型一次要多少 token」，它是预测的输入，不是预测本身。",
            "",
        ]
        if scan.get("findings"):
            body += [
                "### 上下文压力告警",
                "",
                markdown_table(
                    ["级别", "类型", "路径", "tokens", "说明"],
                    [[f["severity"], f["kind"], f"`{f['path']}`", fmt(f["estimated_tokens"]), f["detail"]]
                     for f in scan["findings"][:15]],
                ),
                "",
            ]

    body += [
        "## 假设与排除项",
        "",
        *[f"- 假设：{item}" for item in project.get("assumptions", [])],
        *[f"- 排除：{item}" for item in project.get("exclusions", [])],
        "",
        "> 执行后必须用真实 usage 回填 `calibrate`，再重新出预测。未校准的预测不构成任何承诺。",
    ]
    write_text(out / "TOKEN_BUDGET.md", "\n".join(body))


def write_task_token_csv(forecast: dict[str, Any], out: Path) -> None:
    destination = out / "task-token-estimates.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    header = ["task_id", "name"]
    for field in list(TOKEN_FIELDS) + ["total"]:
        header += [f"{field}_p50", f"{field}_p80", f"{field}_p90", f"{field}_worst_case"]
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in forecast.get("task_tokens", []):
            line = [row["task_id"], row["name"]]
            for field in TOKEN_FIELDS:
                values = row["by_category"][field]
                line += [int(values[key]) for key in _ENVELOPE]
            line += [int(row["total_tokens"][key]) for key in _ENVELOPE]
            writer.writerow(line)


def write_cost_comparison(forecast: dict[str, Any], out: Path) -> None:
    project = forecast["project"]
    costs = forecast["costs"]
    tokens = forecast["tokens"]

    rows = []
    for model in costs["models"]:
        rows.append([
            model["display_name"], model["model_id"], model["provider"], model["currency"],
            fmt(model["cost"]["p50"], 4), fmt(model["cost"]["p80"], 4),
            fmt(model["cost"]["p90"], 4), fmt(model["cost"]["worst_case"], 4),
            "示例，不可计费" if model["not_for_billing"] else "已核验",
        ])

    breakdown_rows = []
    for model in costs["models"]:
        share = model["mean_cost_by_category"]
        total = sum(share.values()) or 1.0
        breakdown_rows.append([
            model["display_name"],
            *[f"{100.0 * share[field] / total:.1f}%" for field in TOKEN_FIELDS],
        ])

    provenance_rows = [
        [model["model_id"], model.get("effective_date"), model.get("verified_at"),
         model.get("billing_mode"), model.get("source_reference")]
        for model in costs["models"]
    ]

    ranking_rows = [
        [currency, ", ".join(value["ranked_model_ids_by_p50"]), value["cheapest_p50"], value["ranking_pool"]]
        for currency, value in costs["rankings_by_currency"].items()
    ]

    body = [
        f"# MODEL_COST_COMPARISON — {project['project_id']}",
        "",
        f"- 费率注册表版本：`{costs['registry_version']}`",
        f"- 基准币种：`{costs['base_currency']}`，出现的币种：{', '.join(costs['currencies'])}",
        f"- 对应 Token 总量 P50：{fmt(int(tokens['total']['p50']))}，P90：{fmt(int(tokens['total']['p90']))}",
        "",
        "## 1. 各方案费用区间",
        "",
        markdown_table(
            ["方案", "model_id", "供应商", "币种", "P50", "P80", "P90", "Worst", "费率状态"], rows),
        "",
        "## 2. 费用构成（按类别占比，均值口径）",
        "",
        markdown_table(["方案", *TOKEN_FIELDS], breakdown_rows),
        "",
        "> 缓存命中率直接决定 `cached_input` 这一列的权重。它是这张表里最容易被高估的一项：",
        "> 预测里的命中率是假设值，执行后必须用真实 usage 校准。",
        "",
        *_mix_verification_lines(costs.get("mix_verification")),
        "## 3. 同币种排序",
        "",
        markdown_table(["币种", "按 P50 从便宜到贵", "最便宜", "排序池"], ranking_rows),
        "",
        f"> {costs['cross_currency_note']}",
        "",
        "## 4. 费率溯源",
        "",
        markdown_table(["model_id", "生效日期", "核验时间", "计费模式", "来源"], provenance_rows),
        "",
        f"> {costs['warning']}",
        "",
        "> 本包不写死任何厂商价格。要得到可用于预算的数字，把已核验费率填进",
        "> `config/model-pricing.json`（从 `model-pricing.template.json` 复制），`null` 不填校验会拒绝。",
    ]
    write_text(out / "MODEL_COST_COMPARISON.md", "\n".join(body))


def _mix_verification_lines(verification: dict[str, Any] | None) -> list[str]:
    """Say, in the cost report itself, whether its category mix was ever checked.

    A reader who opens only this file must not be able to mistake an assumed mix
    for a measured one.
    """
    if not verification:
        return []
    if not verification.get("checked"):
        return [f"> ⚠ **占比未经核对**：{verification['detail']}", ""]

    lines = [f"> **占比已对照实测**：{verification['detail']}", ""]
    observed = verification.get("observed_cached_input_share")
    forecast = verification.get("forecast_cached_input_share")
    if observed is not None and forecast is not None:
        lines += [
            f"> `cached_input` 占比：假设 {forecast * 100:.2f}%，实测 {observed * 100:.2f}%。",
            "",
        ]
    depths = [row for row in verification.get("overstatement_by_depth", []) if row.get("factor")]
    if depths:
        lines += [
            f"> 高估倍数随任务长度从 {depths[0]['factor']:.2f}x（{depths[0]['turns']} 轮）"
            f"到 {depths[-1]['factor']:.2f}x（{depths[-1]['turns']} 轮）。",
            "",
        ]
    if not verification.get("sample_sufficient"):
        lines += [
            f"> 但样本不足：{verification.get('sessions')} 个会话，门槛 "
            f"{verification.get('minimum_sessions')}。这是一个**发现**，不是一次校准。",
            "",
        ]
    return lines


def write_runtime_report(forecast: dict[str, Any], out: Path) -> None:
    project = forecast["project"]
    runtime = forecast["system_runtime"]
    completion = runtime.get("expected_completion_at", {})
    rows = [
        _envelope_row("Wall-clock 小时", runtime["wall_clock_hours"], 2),
        _envelope_row("Active worker 小时", runtime["active_worker_hours"], 2),
        _envelope_row("关键路径小时", runtime["critical_path_hours"], 2),
    ]
    body = [
        f"# SYSTEM_RUNTIME_ESTIMATE — {project['project_id']}",
        "",
        "本报告只表示**系统自主**生成/转换、编译、测试、修复、恢复与打包所需的机器时间。",
        "",
        markdown_table(["指标", "P50", "P80", "P90", "Worst Case"], rows),
        "",
        f"- 配置 Worker：{runtime['configured_workers']}",
        f"- 有效并行容量：{runtime['effective_worker_capacity']}（可用率 × 并行效率 × 模型并发 × 代码冲突系数）",
        f"- 全局开销系数：{runtime['global_overhead_ratio']}",
        f"- P50 预计完成：{completion.get('p50', '未配置 system.start_at')}",
        f"- P90 预计完成：{completion.get('p90', '未配置 system.start_at')}",
        "",
        "## 明确排除",
        "",
        *[f"- {item}" for item in runtime["excludes"]],
        "",
        "> 这些排除项属于 `human_assisted` 口径，出现在对比报告里，绝不并入系统 ETA。",
    ]
    write_text(out / "SYSTEM_RUNTIME_ESTIMATE.md", "\n".join(body))


def write_human_report(forecast: dict[str, Any], out: Path) -> None:
    project = forecast["project"]
    human = forecast["human_effort"]
    rows = [
        _envelope_row("人时 person-hours", human["person_hours"], 2),
        _envelope_row("人日 person-days", human["person_days"], 2),
        _envelope_row("人月 person-months", human["person_months"], 2),
        _envelope_row("日历周 calendar weeks", human["calendar_weeks"], 2),
    ]
    role_rows = [
        [role, fmt(values["p50"]), fmt(values["p80"]), fmt(values["p90"]), human["team"].get(role)]
        for role, values in human["role_person_hours"].items()
    ]
    body = [
        f"# HUMAN_EFFORT_ESTIMATE — {project['project_id']}",
        "",
        f"人工基线与系统估算使用**同一份任务 DAG 和同一个完成定义**：`{project['definition_of_done']['level']}`。",
        "",
        markdown_table(["指标", "P50", "P80", "P90", "Worst Case"], rows),
        "",
        f"- 有效投入系数 focus_ratio：{human['focus_ratio']}",
        f"- 复核/协调/返工合计开销系数：{human['overhead_multiplier']}",
        "",
        "## 角色分解",
        "",
        markdown_table(["角色", "P50 人时", "P80 人时", "P90 人时", "配置人数"], role_rows),
        "",
        "> 日历周同时受角色产能上限和关键路径约束，取两者的较大值。",
    ]
    write_text(out / "HUMAN_EFFORT_ESTIMATE.md", "\n".join(body))


def write_comparison_report(forecast: dict[str, Any], out: Path) -> None:
    project = forecast["project"]
    runtime = forecast["system_runtime"]
    human = forecast["human_effort"]
    comparison = forecast["comparison"]
    costs = forecast["costs"]
    comp = comparison["comparison"]
    assisted = comparison["human_assisted"]

    cost_rows = [
        [
            model["display_name"], model["currency"],
            fmt(model["cost"]["p50"], 4), fmt(model["cost"]["p80"], 4),
            fmt(model["cost"]["p90"], 4), fmt(model["cost"]["worst_case"], 4),
            "示例费率，不可计费" if model["not_for_billing"] else f"已核验 {model['verified_at']}",
        ]
        for model in costs["models"]
    ]
    ranking_rows = [
        [currency, ", ".join(value["ranked_model_ids_by_p50"]), value["ranking_pool"]]
        for currency, value in costs["rankings_by_currency"].items()
    ]
    labor = comp["labor_reduction_ratio"]
    body = [
        f"# SYSTEM_VS_HUMAN_COMPARISON — {project['project_id']}",
        "",
        "## 同一完成定义",
        "",
        f"- Level：`{project['definition_of_done']['level']}`",
        f"- Checks：{', '.join(project['definition_of_done'].get('checks', []))}",
        "",
        "## 三套时间",
        "",
        markdown_table(
            ["方案", "P50", "P90", "口径"],
            [
                ["系统自主", f"{fmt(runtime['wall_clock_hours']['p50'])} 小时",
                 f"{fmt(runtime['wall_clock_hours']['p90'])} 小时", "机器连续 Wall-clock，不含任何人工等待"],
                ["纯人工", f"{fmt(human['calendar_weeks']['p50'])} 周",
                 f"{fmt(human['calendar_weeks']['p90'])} 周", "配置团队 + 工作日历 + 同等 DoD"],
                ["人机协作端到端", f"{fmt(assisted['end_to_end_hours']['p50'])} 小时",
                 f"{fmt(assisted['end_to_end_hours']['p90'])} 小时", "系统 + 不可并行的人工复核 + 审批/外部等待"],
            ],
        ),
        "",
        "## 对比结论",
        "",
        f"- P50 日历加速：**{fmt(comp['calendar_speedup']['p50'])}×**",
        f"- P90 日历加速：**{fmt(comp['calendar_speedup']['p90'])}×**",
        f"- 人工投入减少：**{fmt(labor * 100 if labor is not None else None)}%**",
        f"- P50 节省人工：**{fmt(comp['human_hours_saved_p50'])} 人时**",
        f"- 自动化覆盖：**{fmt(comp['automation_coverage'] * 100)}%**",
        f"- 置信度：**{comparison['confidence']}**",
        "",
        f"> 口径提醒：{comp['calendar_speedup']['caveat']}",
        "",
        "## 模型费用场景",
        "",
        markdown_table(["模型", "币种", "P50", "P80", "P90", "Worst", "费率状态"], cost_rows),
        "",
        markdown_table(["币种", "按 P50 排序", "排序池"], ranking_rows),
        "",
        f"> {costs['cross_currency_note']}",
        "",
        f"> {costs['warning']}",
        "",
        "## 假设与排除项",
        "",
        *[f"- 假设：{item}" for item in comparison.get("assumptions", [])],
        *[f"- 排除：{item}" for item in comparison.get("exclusions", [])],
    ]
    write_text(out / "SYSTEM_VS_HUMAN_COMPARISON.md", "\n".join(body))


def write_reports(forecast: dict[str, Any], output: str | Path) -> list[str]:
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    write_token_budget(forecast, out)
    write_task_token_csv(forecast, out)
    write_cost_comparison(forecast, out)
    write_runtime_report(forecast, out)
    write_human_report(forecast, out)
    write_comparison_report(forecast, out)
    return [
        "TOKEN_BUDGET.md",
        "task-token-estimates.csv",
        "MODEL_COST_COMPARISON.md",
        "SYSTEM_RUNTIME_ESTIMATE.md",
        "HUMAN_EFFORT_ESTIMATE.md",
        "SYSTEM_VS_HUMAN_COMPARISON.md",
    ]

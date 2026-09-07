# 本批证据已撤回 — 不得用于任何认证判定

撤回时间：2026-08-06
撤回人：本次运行的执行者（zpchoney@gmail.com），经 run_case.py 缺陷复核后主动撤回
被撤回的结论：B29-001 `passed`

## 撤回理由

本批运行只执行了 development 一份语料（见同目录 `case-result.json`，
用例体步骤仅 `validate-route` 与 `migrate-development`），但同目录
`manifest.json` 的 corpora 声明了 development / holdout / representative 三份，
且当时写入的结果文件带有：

    holdout_passed                  true
    representative_workload_passed  true

这两个标记没有任何步骤支撑。成因是 `scripts/test-suite/run_case.py` 的
`build_corpora` 按「语料目录在盘上存在」推断语料已被使用，而非按「有步骤真的
跑过它」。catalog 对全部 8 个 B29 用例都标了 `holdout_required` 与
`representative_workload_required`，因此该结果构成 over-claim，属于严格 profile
反作弊条款直接禁止的行为（「只运行 Smoke Test」「用汇总状态替代原始证据」）。

## 本批中仍然成立的部分

以下事实由本批原始日志支撑，未被撤回：

- 前置条件 6/6 成立，java 21.0.11 与 dotnet 10.0.301 精确工具链解析通过
- `validate_route.py routes/java-to-csharp` 通过
- development 语料完成真实 Java 语义分析、C# 代码生成与 `dotnet build`
  （`Build succeeded. 0 Warning(s) 0 Error(s)`）及行为用例验证

被撤回的只是 holdout 与 representative 的通过声明。

## 修复与替代

`run_case.py` 已修正：步骤新增 `corpus` 声明，`build_corpora` 仅收录「有步骤
声明该语料且该步骤达成预期」的语料；`holdout_passed` /
`representative_workload_passed` 由实际执行集合推导；用例要求的语料若无任何
步骤跑过，状态强制为 `blocked` 而非 `passed`。

替代批次：`../run-2026-08-06T07-b29-java-csharp`，三份语料各有一个达成预期的
迁移步骤，三份语料摘要互异，标记为挣得而非推断。

本目录保留不删，作为该缺陷曾经存在的记录。

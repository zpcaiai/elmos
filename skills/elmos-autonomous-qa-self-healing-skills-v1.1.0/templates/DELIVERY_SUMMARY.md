# Project Delivery Summary

## 发布结论

- Output status: `<certified|verified|failed|partial>`
- Quality gates: `<passed|failed>`
- Project revision: `<revision-id>`
- Source snapshot: `<snapshot-id>`

## 可下载产出

| Bundle | 状态 | SHA-256 | 内容 |
|---|---|---|---|
| project-with-tests |  |  | 完整项目与原生测试文件 |
| tests-only |  |  | 测试源、配置、数据、基线与重放入口 |
| qa-evidence |  |  | 计划、结果、证据、缺陷、补丁与证书 |
| repair-patches |  |  | 可选修复补丁与验证证据 |

## 测试摘要

列出需求覆盖、测试文件数量、执行数量、Passed/Failed/Blocked/Flaky、性能容量、安全与 UI 结论。

## 运行命令

列出干净环境中安装、发现、冒烟、全量和失败重放命令。

## 时间与成本

分别报告系统自主生成/执行 wall-clock ETA、实际耗时、Token/算力成本与人工等效时间。

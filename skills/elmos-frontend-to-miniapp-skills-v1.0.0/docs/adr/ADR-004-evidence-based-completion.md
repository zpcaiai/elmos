# ADR-004：以证据而非代理陈述判定完成

- 状态：Accepted
- 日期：2026-08-19

## 决策

所有 build、parity、privacy、security、release claim 必须链接到当前 artifact、哈希、工具版本、时间和 evaluator。没有证据的状态为 unknown/blocked，不得为 passed。

## 理由

代码生成代理容易把计划、未执行测试、部分实现或静态检查误报为“全部完成”。证据图使结果可复核、恢复和统计。

## 最低证据

- 固定源修订；
- IR 与 trace；
- 生成目标哈希；
- 官方构建回执；
- 关键流程差分；
- 视觉结果；
- 隐私/secret 扫描；
- C/D/E 决策；
- 审批和发布回执（适用时）。

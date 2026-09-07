# Sample execution request

```text
$elmos-insight-orchestrator

目标：在当前 Elmos 仓库实施 Project Intelligence Studio 的 Batch 01–03。
约束：
- 保留现有架构和已实现接口；
- 使用 Vue 3 + TypeScript + Monaco；
- parser 核心使用 Rust/Tree-sitter；
- 长任务必须通过现有 durable workflow；
- 不执行导入仓库中的脚本；
- 先完成真实 P0 垂直切片，不接受仅接口桩。
Done when：
- Git/ZIP 导入、revision manifest、指纹、Java/TS 基础解析；
- Code Graph、Evidence Graph；
- 在线代码阅读、Definition/References、证据化函数讲解；
- 单元、契约、E2E、安全和恢复测试通过；
- 输出机器 wall-clock P50/P90 与人工审核时间分列；
- 更新 backlog/traceability 和 execution report。
```

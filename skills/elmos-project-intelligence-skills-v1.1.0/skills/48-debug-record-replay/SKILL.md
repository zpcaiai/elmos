---
name: elmos-debug-record-replay
description: 记录调试命令、暂停点、变量差异、副作用和环境检查点，并按能力等级实现会话回放、输入重放、检查点恢复和受支持运行时的反向调试。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills and Claude Code. Requires an isolated debug runtime; production attach is denied by default.
metadata:
  version: 1.1.0
  category: debug-runtime
  title_zh: 调试记录、检查点与运行回放
  batch: BATCH-14-online-debug-and-learning
  owner: elmos-project-intelligence
---

# 调试记录、检查点与运行回放

## 目标

提供可审计、可分享、可比较的调试时间线，同时明确区分通用事件回放与少数运行时原生 Time Travel，避免承诺不存在的通用反向执行。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个调试、学习、运行时或转换能力时，先调用 `elmos-insight-orchestrator`。
- 读取 `references/module-spec.md` 和 `docs/27-online-debug-learning.md` 后再修改代码。
- 不得把设计稿、协议桩、Mock Adapter、未运行的沙箱或手工截图标记为完成。
- 调试默认只允许固定 revision、非生产、一次性沙箱与脱敏数据；任何例外必须由策略和审计显式授权。

## 输入

- Debug Session 事件流
- Runtime Profile、输入、测试与环境摘要
- Adapter Replay Capabilities
- 脱敏、保留和加密策略

## 必须输出

- Replay Bundle
- Debug Checkpoints
- Timeline/Diff
- 重放与完整性报告

## 执行流程

1. 定义 R0 事件时间线、R1 输入/测试重放、R2 检查点恢复、R3 原生反向调试四级能力矩阵。
2. 记录调试命令、事件、Frame、变量差异、输出、副作用、Trace 关联和采样/截断元数据。
3. 生成带 manifest、内容哈希、签名、加密、脱敏和保留策略的 Replay Bundle。
4. 实现测试输入重放、环境快照恢复和可验证的 checkpoint 创建/恢复流程。
5. 运行时支持时提供 Reverse Continue/Step；不支持时自动降级到 checkpoint/input replay。
6. 实现 passing/failing、before/after、source/target 两次运行的状态与副作用时间线比较。

## 实施要求

- UI 和报告必须显示实际 replay level，不得把日志回放标为 Time Travel Debugging。
- Replay Bundle 必须记录不可复现因素、外部依赖、随机种子、时钟和容差。
- 变量、请求体、SQL 参数、文件内容和密钥必须按字段策略脱敏或省略。
- Bundle 完整性、版本、权限和过期状态在重放前验证。
- 超大或长时间会话必须分块、采样、摘要和设置硬上限，不得拖垮存储或浏览器。

## 安全与可信度约束

- Replay Bundle 采用租户级密钥加密和短期下载授权。
- 禁止在不受信任环境重放带副作用的外部调用；默认使用 Stub/Virtual Service。
- 删除会话时按保留策略删除 Bundle、快照和派生索引。

## 依赖技能

- `elmos-debug-adapter-gateway`
- `elmos-debug-sandbox-orchestration`
- `elmos-runtime-trace-fusion`
- `elmos-incremental-analysis-cache`

## 预期交付物

- `services/debug-replay`
- `debug-replay-bundle.schema.json`
- `debug-replay-determinism-report.md`

## 完成定义

- [ ] 不支持原生反向执行的运行时明确降级，UI 和报告不产生误导。
- [ ] 固定测试、输入和环境的 R1/R2 重放在定义容差内复现关键状态与输出。
- [ ] Replay Bundle 的 Secret/PII 扫描无高危泄漏，字段省略有明确标记。
- [ ] 损坏、篡改、过期或版本不兼容的 Bundle 在运行前被拒绝。
- [ ] 超大调试会话按策略分块与截断，仍可浏览摘要和关键检查点。

## 验证

1. 执行本模块的单元、协议合规、集成、E2E、沙箱逃逸、权限、恢复和性能测试。
2. 至少使用一个真实小型 fixture 项目完成“启动→断点→单步→变量→副作用→终止/回放”闭环。
3. 将需求、实现文件、测试、运行 revision、adapter/runtime 版本和证据写入追踪矩阵。
4. 运行：

```bash
python3 scripts/validate_skillpack.py --strict-jsonschema
python3 -m unittest discover -s tests -v
```

5. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
6. 对运行时不支持的能力、低置信度因果关系和不可复现外部依赖明确标注。

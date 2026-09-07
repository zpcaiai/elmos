---
name: elmos-distributed-debug-correlation
description: 把浏览器、API、微服务、数据库、缓存、消息和后台任务的 Trace 与调试会话关联。用于前后端链路、异步因果、受控协同断点、故障定位以及 Elmos Source/Target 对照调试。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills and Claude Code. Requires an isolated debug runtime; production attach is denied by default.
metadata:
  version: 1.1.0
  category: debug-integration
  title_zh: 分布式调试、异步因果与源目标对照
  batch: BATCH-14-online-debug-and-learning
  owner: elmos-project-intelligence
---

# 分布式调试、异步因果与源目标对照

## 目标

在不会冻结整个生产系统的前提下，让用户理解一次业务请求跨组件的真实执行，并识别源项目与转换后项目的语义分歧。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个调试、学习、运行时或转换能力时，先调用 `elmos-insight-orchestrator`。
- 读取 `references/module-spec.md` 和 `docs/27-online-debug-learning.md` 后再修改代码。
- 不得把设计稿、协议桩、Mock Adapter、未运行的沙箱或手工截图标记为完成。
- 调试默认只允许固定 revision、非生产、一次性沙箱与脱敏数据；任何例外必须由策略和审计显式授权。

## 输入

- Debug Session/Replay
- Trace/Log/Metric 与 API/Event Topology
- Correlation IDs 与测试场景
- Source/Target/IR Mapping

## 必须输出

- Distributed Debug Session Graph
- Async Causality Timeline
- Cross-service Navigation
- Source/Target Semantic Divergence Report

## 执行流程

1. 贯通 browser interaction、traceparent、request_id、message_id、workflow/task_id 和 debug_session_id。
2. 构建跨服务、线程、协程、消息、定时任务和数据库事务的因果 Session Graph。
3. 在非生产测试环境实现受控协同断点、超时预算、服务虚拟化和死锁/级联超时保护。
4. 在暂停点周围联动 Span、Log、Metric、SQL、Cache、MQ 和外部调用状态。
5. 实现 Source/IR/Target 同场景双运行、关键变量/状态/副作用对齐和语义分歧检测。
6. 实现测试失败→Trace→服务→Frame→变量/数据→代码→修复/学习任务的深链。

## 实施要求

- 跨进程因果关系保存证据和置信度；缺少上下文时不得伪造完整调用链。
- 协同暂停仅用于受控非生产环境，并设置全局超时、租约和自动恢复。
- 未授权服务、日志、变量和数据资产在 Session Graph 中必须完全过滤。
- Source/Target 比较使用相同输入、数据基线、时间/随机策略和容差定义。
- 单个服务或 adapter 失败不得无限阻塞其他服务、消息消费者或调试会话。

## 安全与可信度约束

- 分布式调试不直接控制生产全链路；生产问题优先使用 Trace、日志、快照和安全回放。
- Correlation ID 本身不得成为越权访问令牌。
- 跨服务数据仅保留最小必要字段，并按服务和数据域进行 ABAC 过滤。

## 依赖技能

- `elmos-online-debug-workbench`
- `elmos-debug-record-replay`
- `elmos-runtime-trace-fusion`
- `elmos-api-event-topology`
- `elmos-conversion-integration`

## 预期交付物

- `services/distributed-debug-correlation`
- `distributed-debug-session-graph.json`
- `source-target-debug-diff.md`

## 完成定义

- [ ] 一次前端操作能关联到正确的后端请求、服务、数据库和消息链路。
- [ ] 异步链路缺少 propagation 时会显示断点和不确定性，而不是伪造因果边。
- [ ] 固定 fixture 的 Source/Target 状态或副作用分歧能被定位到对应 Frame 和映射。
- [ ] 暂停单个服务不会造成无限死锁、消息租约泄漏或无界资源占用。
- [ ] 权限过滤后用户看不到未授权服务名称、日志摘要、变量或拓扑边。

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

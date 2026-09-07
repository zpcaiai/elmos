# P01 失败模式、恢复与人工升级

## 1. 本包失败目录

| 失败 | 恢复/处置 |
| --- | --- |
| Adapter 崩溃 | 隔离 run，保留 durable session，按政策重启/切换 Adapter；禁止重复副作用。 |
| Session 日志损坏 | 拒绝加载、保留原始 artifact、进入修复/人工审计；不得猜测缺失事件。 |
| 工具无响应 | per-request timeout + run cancellation + idempotency-aware retry。 |
| 上下文压缩丢任务状态 | 结构化 carryover 校验失败则回退到旧 Epoch，不发布 compact。 |
| 沙箱仅 partial | 需要 full 的任务拒绝；允许 partial 的低风险任务必须显式记录。 |
| 权限服务不可用 | fail closed，并输出 blocker；不得采用默认 allow。 |

## 2. 统一错误分类

| 类别 | 自动重试 | 处置 |
| --- | --- | --- |
| Transient infrastructure | 有界重试 | backoff+jitter，保持 idempotency。 |
| Rate limit / capacity | 有界重试或路由 | 读取 retry-after，P06 切合格 Provider。 |
| Deterministic validation failure | 不直接重试 | 诊断根因并修改实现。 |
| Policy/security denial | 不重试 | 明确 blocker；需要正式审批或缩小动作。 |
| Unsupported semantic/capability | 不盲重试 | 创建 gap，选择 bridge/re-design/human decision。 |
| No progress / doom loop | 有限 steering/escalation | 超过阈值停止并保存状态。 |
| External human decision | 等待 durable gate | 不占用计算 Worker，可恢复。 |

## 3. 恢复协议

1. 读取 durable session/task/workpad/ledger，不从文本摘要猜测已完成工作。
2. 确认最后提交的副作用与 idempotency settlement。
3. 验证 workspace/source/config/tool/model revisions；不一致时创建新 attempt。
4. 从最小未完成任务继续，避免重复扫描/测试，但相关变更后必须重跑影响闭包。
5. 恢复后写 `recovery record`，包含丢失、重放、跳过和风险。

## 4. 人工升级

只在真实外部 blocker、语义选择、风险接受、生产副作用、法规或预算决策时升级。升级包必须包含：上下文、尝试、证据、选项、影响和精确所需决定。

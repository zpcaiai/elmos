# P07 失败模式、恢复与人工升级

## 1. 本包失败目录

| 失败 | 恢复/处置 |
| --- | --- |
| 错误经验污染 | 隔离 candidate、撤销证据、降级规则、重跑受影响 corpus。 |
| 知识过拟合某项目 | 增加跨项目/负向验证与 applicability predicate。 |
| 框架版本漂移 | 按版本分支规则、标记 stale、触发兼容 benchmark。 |
| 租户数据误入全局 | 立即 quarantine、审计传播路径、删除派生数据并通知治理流程。 |
| 专项模型退化 | 停止 canary、回退 deterministic/通用模型、保存失败样本。 |

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

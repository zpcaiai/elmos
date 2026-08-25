# P06 失败模式、恢复与人工升级

## 1. 本包失败目录

| 失败 | 恢复/处置 |
| --- | --- |
| Catalog/health stale | 降低置信度、主动探测、使用保守 Route 或阻断高风险任务。 |
| 所有 Provider 失败 | 保存 run state，指数退避或切换合格模型；禁止无限重试。 |
| benchmark 领先模型不可用 | 从主候选移除并解释，选择已验证可用替代。 |
| 成本预测偏差 | 逐阶段更新 ETA/成本区间，触发预算 Gate 和重规划。 |
| TaskFit 数据稀疏 | 使用外部先验+探索流量+宽置信区间，不伪造精确排序。 |

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

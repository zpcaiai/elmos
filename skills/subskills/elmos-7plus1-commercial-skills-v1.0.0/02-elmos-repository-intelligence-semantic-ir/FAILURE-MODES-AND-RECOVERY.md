# P02 失败模式、恢复与人工升级

## 1. 本包失败目录

| 失败 | 恢复/处置 |
| --- | --- |
| 解析器版本不支持 | 回退到 token/tree-sitter/LSP/运行证据组合并标记低置信度。 |
| 代码生成产物缺失 | 定位生成入口，运行受控生成或把产物依赖记为 blocker。 |
| 动态调用无法静态确定 | 保留候选集合，注入运行 Trace/契约测试缩小范围。 |
| Monorepo 过大 | 按构建图分区、内容寻址缓存和分层摘要；全局图只保留必要边。 |
| 静态/动态证据冲突 | 创建 conflict record 并进入 P05 定向验证。 |

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

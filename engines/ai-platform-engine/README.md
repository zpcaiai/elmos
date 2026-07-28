# ELMOS AI ML and Generative AI Platform Engine

Batch 23 独立 Java 21 Worker，默认端口 `8097`。所有 Provider Adapter 初始为
`NOT_CONFIGURED`；无短期 Job Lease、精确环境范围、专用授权或独立生产批准时保持
`NOT_RUN`、`INCONCLUSIVE` 或 `BLOCKED`。控制面不执行客户操作，Worker 不得修改 Gate、接受风险或授予人工决定。

## Coding Agent 模型目录

`policies/model-catalog-v1.json` 登记了 project-synthesis-engine（一键生成项目）、
Spring `rewrite-spring` 底座的长尾修复步骤、以及跨语言迁移 Batch 5 惯用化步骤
共用的候选模型名单，详见 [ADR-0059](../../docs/adr/ADR-0059-coding-agent-model-catalog.md)。
目录只声明候选 `modelVersion`，所有条目保持 `status: NOT_CONFIGURED`；
真正可调用需要先在 `EnterpriseModels.ModelPolicy` 中放行、产生带
`approved=true, healthy=true` 的 `ModelEndpoint`，并通过本文件顶部同样
`NOT_CONFIGURED` 的 `INFERENCE_GATEWAY`/`CLOUD_AI` Adapter 转发。运行
`make model-catalog-check` 做结构与状态的失败关闭校验。

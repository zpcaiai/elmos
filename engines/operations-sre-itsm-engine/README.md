# ELMOS Operations SRE and ITSM Engine

Batch 25 独立 Java 21 Worker，默认端口 `8099`。所有 Provider Adapter 初始为
`NOT_CONFIGURED`；无短期 Job Lease、精确环境范围、专用授权或独立生产批准时保持
`NOT_RUN`、`INCONCLUSIVE` 或 `BLOCKED`。控制面不执行客户操作，Worker 不得修改 Gate、接受风险或授予人工决定。

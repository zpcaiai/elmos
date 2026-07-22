# ELMOS Test Quality Engine

Batch 18 的独立 Java 21 执行域，横向服务 Java、.NET、Python、Web/客户端、数据库/数据/模型、基础设施和组合业务 Journey。它归一化测试资产、风险覆盖、Characterization、Contract、Property、Mutation、Test Data、Environment、Flaky、Impact 与 Continuous Validation 证据。

控制平面和本 Worker 都不在宿主机执行客户测试。所有 Unit、Integration、Browser/Client、Data/ML、Performance 与 Mutation Runner 必须是 digest-pinned、rootless、短期、namespace 隔离并默认拒绝网络；Environment 和 Test Data 都必须持有短期 Lease。外部 Runner 未配置时 API 返回 `NOT_RUN`/`INCONCLUSIVE`，证据为空且 `customerCodeExecuted=false`。

AI 生成物始终从 `TEST_CANDIDATE` 开始；没有 Compile、Run、Fail-before-fix、Isolation、Repeatability、Mutation 和人工 Review 不得晋级。Worker 不能改 Gate、自动批准 Snapshot、隐藏 Retry/Flaky、把 Unknown/Skipped/Not Run 当作 Pass，或使用生产 Secret。

接口：`GET /engine/v1/capabilities`，`POST /engine/v1/discover`、`/plan`、`/generate`、`/execute`、`/evaluate`，以及 Job 查询/取消。端口默认 `8092`。

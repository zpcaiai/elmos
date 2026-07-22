# ADR 0002: 模块化单体与持久化工作流

- 状态：已接受
- 日期：2026-07-20

## 决策

控制平面采用 Java 21、Spring Boot 3 和 Maven 多模块的模块化单体。迁移真实状态写入 PostgreSQL，并以乐观锁、审计事件和 Outbox 保证恢复及幂等边界。

Java Engine Worker 独立进程部署，只通过版本化契约与控制平面交换命令和证据。Spring AI Alibaba 图只允许用于诊断、路由和报告等智能子流程，不拥有 MigrationRun 的最终状态。

## 后果

控制平面不能使用 `ProcessBuilder`、Shell 或嵌入式 OpenRewrite 执行客户代码。后续若拆分服务，必须保留相同 Port、契约和数据所有权。


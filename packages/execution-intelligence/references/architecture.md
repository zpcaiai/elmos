# 参考架构

```text
Task API (FastAPI / Spring Boot)
        │  Idempotency-Key、租户鉴权、BLOCKED 语义
        ▼
Durable Orchestrator（本包 durable.py 是 SQLite 参考实现；生产用 Temporal/Postgres）
        │  任务状态机、重试策略、Checkpoint 决策
        ▼
Agent Worker 池 ──► Sandbox / Build / Test / Security Worker
        │
        ├─► PostgreSQL：run / task / task_attempt / checkpoint / run_event / idempotency_key / outbox / artifact / model_usage
        ├─► 对象存储 + Git：工作区快照与不可变 Artifact
        └─► SSE / WebSocket + 轮询兜底：Last-Event-ID 重放
```

## 三个边界

**客户端连接不是执行宿主。** 浏览器、终端、WebSocket 断开不影响运行。进度靠重连恢复，
不靠重新提交。API 层任何"把执行挂在请求生命周期上"的写法都是架构错误。

**编排器不做业务判断。** 它只认任务状态机和失败分类。"这次失败该不该重试"由失败分类回答，
不由异常文本回答。

**估算器与执行器共用同一份任务 DAG。** 预测和执行读同一个文件，所以"预测的是 A、跑的是 B"
这种漂移在结构上不可能发生。执行产生的 `model_usage` 又反过来喂 `calibrate`，闭环成立。

## 本包提供什么、不提供什么

| | |
| --- | --- |
| 提供 | 估算器全链路、SQLite 上的持久执行参考实现、Postgres 表结构、API 契约、Chaos 验证器 |
| 不提供 | 生产部署、真实 Agent Worker、模型调用、对象存储适配、鉴权实现 |

参考实现存在的意义是**让契约可测**：幂等、重放、恢复这些性质在 SQLite 上能断言，
换成 Postgres + Temporal 时断言不变。

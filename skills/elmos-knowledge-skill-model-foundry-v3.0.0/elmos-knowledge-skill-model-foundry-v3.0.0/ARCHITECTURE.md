# Elmos Foundry v3 Architecture

```text
Experience / Customer / Public / Runtime Sources
                    │
                    ▼
┌──────────────── Knowledge & Provenance Plane ────────────────┐
│ ingestion · normalization · semantic graphs · rights · time │
└──────────────────────────┬────────────────────────────────────┘
                           ▼
┌──────────────── Repository Semantic Compiler ────────────────┐
│ language / framework / DB / UI / dataflow / infra / AI IR   │
│ Source Symbol ↔ Semantic IR ↔ Target Symbol                  │
└──────────────────────────┬────────────────────────────────────┘
                           ▼
┌──────────────── Skill & Execution OS ────────────────────────┐
│ meta routing · atomic skills · workspace lease/fencing       │
│ durable DAG · parallel agents · patch stack · compensation   │
└───────────┬───────────────────────────────┬───────────────────┘
            ▼                               ▼
┌──────── Business-Line Compilers ─┐  ┌── Model Foundry ──────┐
│ Spring · Cross-language · SQL    │  │ router · embedder      │
│ Project · Frontend · Data · AI   │  │ reranker · verifier    │
│ Legacy · Industrial · Cloud      │  │ adapters · SFT/DPO/RLVR│
└───────────┬──────────────────────┘  └──────────┬─────────────┘
            └──────────────────┬─────────────────┘
                               ▼
┌──────────────── Independent Verification & Evidence ─────────┐
│ build · tests · differential · property · mutation · formal  │
│ security · performance · chaos · human approval · E0–E5      │
└──────────────────────────┬────────────────────────────────────┘
                           ▼
┌──────────────── Release, Delivery & Commercial Plane ─────────┐
│ immutable bundle · shadow · canary · rollback · acceptance    │
│ metering · wallet · billing · SLA · marketplace · LTS         │
└──────────────────────────┬────────────────────────────────────┘
                           ▼
                Knowledge–Skill–Model Flywheel
```

## Authority and ownership

- Thread 不是权限主体；Environment、Attachment、Workspace、Tool Request 才是权限与数据边界主体。
- 远程执行器必须有 owner、lease、heartbeat、expiry 和 fencing token。
- 每个副作用绑定幂等键、检查点、补偿器和审计事件。
- 独立验证器不得共享生成 Agent 的可写工作区和越权凭据。

## Release identity

```text
Release = Base Model + Adapter Set + Skill Set + Knowledge Snapshot
        + Semantic IR Version + Toolchain Image + Policy Bundle
        + Evaluation Baseline + Evidence Bundle + Rollback Target
```

## Scale path

大型仓库通过语义地图、依赖图分片、增量分析、内容寻址缓存、并行 Worktree、语义三方合并和分层测试矩阵扩展；任何未验证分片不得被计入完成度。

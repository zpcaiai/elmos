# Architecture

## 定位

本包是 `Elmos Proof-Driven Agentic Harness / Repository Semantic Compiler v3` 的横向学习与资产化平面，不另造一个与 8-Kernel 架构冲突的单体子系统。

## 六类资产严格分离

1. **Knowledge**：可变、需引用、按时间和权限检索的事实。
2. **Skill**：可执行、可测试、可组合、带权限和回滚的程序化方法。
3. **Experience**：一次任务的完整可重放轨迹。
4. **Dataset**：经权利、质量、去重、隔离和证据门处理的训练产品。
5. **Model/Adapter**：对稳定、高频、可泛化模式的参数压缩。
6. **Evidence**：独立验证结果、来源、签名、审批和风险记录。

任何对象不得因“模型生成成功”直接跨层晋升。

## 分层 Skill 发现

```text
Session Startup
    -> 只加载 17 个 Meta-Skill 名称与 description
    -> Meta-Skill 根据任务读取 Registry
    -> Registry 按租户、版本、风险、兼容和置信度返回原子 Skill
    -> 最多激活少量原子 Skill
    -> 长任务压缩时固定 Skill Contract 与 Evidence Contract
```

## 端到端飞轮

```text
Sources -> Knowledge Objects -> Semantic IR/Graph -> Retrieval Context
   -> Meta-Skill Router -> Atomic Skills -> Tool Execution
   -> Compile/Test/Diff/Proof -> Experience Episode -> Dataset Gates
   -> Router/Embedder/Reranker/Verifier/Adapter Training
   -> Offline Evals -> Shadow -> Canary -> Immutable Release
   -> Telemetry/Failures/Human Edits -> next learning cycle
```

## 发布单元

```text
Release = Base Model + Adapters + Skill Set + Knowledge Snapshot
        + Semantic IR Version + Toolchain Image + Policy Bundle
        + Eval Baseline + Evidence Bundle + Rollback Target
```

生产回滚必须回滚整个组合，不能只回滚模型权重。

## 默认技术端口

- Metadata/transactions: PostgreSQL
- Objects: S3-compatible object storage
- Vector/search: replaceable vector + lexical adapters
- Graph: Semantic IR graph port, not a second ungoverned ontology
- Workflow: durable workflow/runtime adapter
- Policy: policy-as-code adapter
- Lineage: OpenLineage-compatible events
- Telemetry: OpenTelemetry-compatible signals
- Training: PyTorch/PEFT/TRL-compatible backends
- Registry: model/dataset/skill registries with immutable versions
- Serving: vLLM/SGLang/KServe-compatible adapters
- Signing: OCI/Sigstore-compatible artifacts

所有端口都必须可替换，Domain Pack 不依赖单一模型或 Agent 厂商。

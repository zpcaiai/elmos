# ELMOS 构建缓存、文件暂存与 Codex/Claude 级缓存命中 Skills 包

版本：**1.2.0**（2026-08-20）

本包在 v1.1.0 的 31 个构建缓存、文件暂存、断点恢复和 SOTA 自适应缓存 Skills 上，新增 11 个 Coding Agent 缓存专用 Skills，总计 **42 个**。

目标是在明确的热工作负载中达到或接近 Codex／Claude Code 的缓存体感：同一项目、稳定模型与工具集、连续回合、小范围修改、完全相同任务重跑、环境未变化、服务重启恢复。

> 重要：包内门槛是实现与认证目标，不是对尚未集成的生产 ELMOS 的实测声明。只有实际 ELMOS 仓库完成实现并生成绑定代码、配置、Provider、语料和平台的最新 Parity Report，才能称为“已达到”。

## v1.2.0 核心能力

```text
Provider Prompt Cache Adapter
  + Canonical Prompt Prefix Compiler
  + Append-only Repository Context Ledger
  + Cache-preserving Context Compaction
  + Exact Action Cache / CAS / Incremental DAG
  + Environment Snapshot Cache
  + Session / Model / Worker / Shard Affinity
  + Multi-layer Cache Coordinator + Singleflight
  + Cache Miss First-Difference Diagnostics
  + Codex/Claude-Class Parity Benchmark
  + SLO Autotuning / Shadow / Canary / Auto Rollback
```

## 强制认证门槛

| 指标 | 门槛 |
|---|---:|
| 稳定对话第 3 回合后 eligible cached-token reuse | >=90% |
| 意外完整前缀未命中 | <=2% |
| 完全相同任务重跑的计算加权 Action 复用 | >=99% |
| 已验证精确重跑中的重复模型/编译/测试调用 | 0 |
| 修改不超过 1% 文件且公共接口不变的计算加权复用 | >=90% |
| 仅实现变化导致的不必要下游失效 | <=5% |
| 环境输入不变时的环境快照命中 | >=95% |
| 热环境 p95 启动时间相对冷启动下降 | >=80% |
| 服务重启后的 sealed artifact 复用 | >=99.9% |
| 同项目稳定后续任务净 wall-clock 节省 | >=70% |
| 同项目稳定后续任务模型输入成本节省 | >=80% |
| 计划性上下文压缩后的长会话缓存 Token 复用 | >=80% |
| 错误命中、跨租户命中、损坏对象执行、低验证等级发布 | 0 |

这些门槛只适用于声明为 eligible 的工作负载。新仓库冷启动、Provider/模型切换、Effort 改变、工具 Schema 改变、TTL 到期、Lockfile/编译器大改等必须作为明确的必要未命中报告。

## 42 个 Skills

原 v1.1.0 的 31 个 Skills 全部保留。新增：

1. `elmos-provider-prompt-cache-adapters`
2. `elmos-canonical-prompt-prefix-layout`
3. `elmos-append-only-repository-context-ledger`
4. `elmos-cache-preserving-context-compaction`
5. `elmos-environment-snapshot-cache`
6. `elmos-cache-affinity-routing`
7. `elmos-multi-layer-cache-coordinator`
8. `elmos-cache-miss-diagnostics`
9. `elmos-codex-claude-parity-benchmark`
10. `elmos-cache-hit-slo-autotuning`
11. `elmos-codex-claude-cache-parity-rollout`

完整依赖顺序见 `PACKAGE_INDEX.md`，最终入口 Skill 是：

```text
elmos-codex-claude-cache-parity-rollout
```

## 关键设计

### 1. Provider Prompt Cache Adapter

分别适配 OpenAI、Anthropic 和自托管 Prefix-KV 运行时。统一记录 eligible input、cache read、cache write、uncached input、output tokens，以及模型、Effort、工具 Schema、Prefix Digest、TTL 和 Miss Reason。

Provider Prompt Cache 只复用输入前缀处理，不能当作模型输出的精确缓存，也不能替代 ActionKey、CAS、权限或验证证据。

### 2. Canonical Prompt Prefix

固定顺序：

```text
系统策略
安全策略
工具 Schema
输出 Schema
稳定 Skills
项目架构摘要
====== Cache Boundary ======
当前任务
当前 Diff
本轮检索文件
动态 Tool Result
```

时间戳、Run ID、临时目录、主机名、随机顺序和无关环境变量禁止进入稳定前缀。

### 3. Append-only Context Ledger

文件读取、摘要、修改、过期、重读、工具结果和检查点全部作为不可变事件追加。文件变化时追加 `CONTEXT_STALE`，不回头重写旧 Prompt 前缀；需要时才重读变化文件。

### 4. Environment Snapshot Cache

缓存基础镜像、SDK/编译器、依赖、索引和可复用环境层。Key 覆盖 Setup Script、Maintenance Script、Lockfile、Toolchain、Platform、批准的环境变量和 Secret Reference 版本。Secret 值不得进入快照。

### 5. Cache Affinity

同一租户、项目、分支、Provider、模型、Effort、工具 Profile 和稳定 Prefix 优先路由到兼容的 Provider Shard、模型副本、热环境 Worker 和已有本地 Artifact 的 Worker；但健康、权限、容量、公平性是硬约束。

### 6. Multi-layer Coordinator

优先顺序：

```text
有效检查点/已封存文件
  -> 精确 Action Result
  -> Local/Remote CAS Partial Hit
  -> Environment Snapshot / Native Build Cache
  -> Provider Prompt Prefix Cache
  -> Full Clean Execution
```

相同授权工作使用 Singleflight，避免缓存未命中风暴。所有层级的节省统一归因，禁止重复计算。

### 7. Miss Diagnostics

每次请求必须归类为：

```text
HIT
NECESSARY_MISS
UNEXPECTED_MISS
BYPASS
RESTORE_FAILURE
LOOKUP_ERROR
```

并定位到具体原因，例如 `MODEL_CHANGED`、`EFFORT_CHANGED`、`TOOL_SCHEMA_CHANGED`、`PROMPT_SEGMENT_CHANGED`、`PUBLIC_INTERFACE_CHANGED`、`LOCKFILE_CHANGED`、`TTL_EXPIRED`、`WRONG_SHARD`、`DIGEST_MISMATCH`。

## 包内工程资产

```text
agent-skills/runtime/                42 个 Skills
docs/source-packages/                3 份主规范
docs/research/                       SOTA 与官方机制研究说明
docs/architecture-decisions/        9 个 ADR
references/schemas/                  19 个 JSON Schema
references/openapi/                  基础 API + Parity API
references/sql/                      基础 Schema + v1.2 增量迁移
templates/config/                    Local/Production/SOTA/Parity 配置
examples/                            Trace、Benchmark、Parity 示例
tests/acceptance/                    基础/SOTA/Parity 验收矩阵
reference-implementation/            可运行 Python 参考组件
scripts/                             安装、校验、回放和 Parity Gate CLI
```

## 验证

```bash
./validate.sh
```

验证包括：

- 42 个 Skill Frontmatter、依赖 DAG、必需章节和文件；
- JSON 语法、Python 编译和内部 SHA-256；
- 34 个参考实现单元测试；
- 示例 Parity Gate；
- Installer 自定义目录 Smoke Test；
- 最终 Entry Skill 和 Package Version 一致性。

单独运行 Parity Gate 示例：

```bash
python3 scripts/run_cache_parity_benchmark.py \
  examples/cache-parity-observations.example.json
```

示例仅证明 Gate 可运行，不代表生产 ELMOS 实测。

## 安装

同时安装到 Codex 和 Claude Code：

```bash
./install.sh --all
```

仅 Codex：

```bash
./install.sh --codex
```

仅 Claude Code：

```bash
./install.sh --claude
```

自定义目录：

```bash
./install.sh --dest /path/to/skills
```

覆盖旧版：

```bash
./install.sh --all --overwrite
```

## 推荐实施顺序

1. 先保持 v1.1.0 确定性缓存、CAS、Staging、Checkpoint 和 SOTA 策略全部通过。
2. Observation-only 接入 Provider 统计、Prompt Prefix Manifest、Miss Reason 和 Environment/Worker Inventory。
3. 启用 Canonical Prompt 与 Context Ledger。
4. 启用 Environment Snapshot 与 Affinity。
5. 启用 Multi-layer Coordinator、Singleflight 和 Context Compaction。
6. 运行完整 Parity Corpus、Security、Chaos 和 Rollback。
7. Shadow -> Internal -> Canary -> 5% -> 25% -> 50% -> 100%。
8. 只有实测报告通过门槛，才发布达到或接近 Codex／Claude Code 缓存水平的声明。

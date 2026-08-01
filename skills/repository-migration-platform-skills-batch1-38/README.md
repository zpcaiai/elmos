# Repository Migration Platform — Batch 1–38 Skills Bag

版本：`3.0.0`

本包包含 **38个Batch级Codex Skills + 1个Master Skill**，覆盖：

```text
Source冻结与语义恢复
→ 10语言/90路径转换
→ Framework、依赖、数据、通信、并发与领域验证
→ Shadow、Canary、Rollback、Evidence、Formal Proof与Repair
→ Architecture Search、Execution OS、Complete Project与Skill产品化
→ 业务、数据、管理端、回归、高可用、事务、性能、安全与Provider闭环
→ Go-Live、生产运营、Source退休与SA1–SA5最终认证
```

## 重要说明

- 本包是根据已批准的Batch 1–38架构整理的**规范化、可安装、可执行实施版**，不是聊天记录逐字导出。
- Batch 13–20的详细架构源文档已收录到`source-specs/`；其余Batch以统一工程模板展开为可执行Skill。
- 共享运行时实现38个Batch Profile、Source指纹、真实仓库发现、90条路径清单、argv-only执行计划、内容寻址Typed Evidence、独立Verifier、依赖Gate和副作用账本。
- 权威状态使用SQLite WAL、`BEGIN IMMEDIATE`、外键、唯一约束、整数Fencing Token和哈希链事件；JSON文件只是可重建镜像。
- 本地Gate最多返回`LOCAL_TOOLKIT_PASS`。随包Trust Policy不含信任密钥并禁用`CERTIFIED`；真实客户、生产、Provider、Kernel Proof、独立评审与CA证据保持`NOT_RUN`。

## 安装

```bash
./install.sh ~/.codex/skills
```

使用`--overwrite`前先审查同名Skill：

```bash
./install.sh ~/.codex/skills --overwrite
```

## 验证

```bash
./validate.sh
```

验证会执行包结构、Skill接口、依赖DAG、Schema、Checksum和18个运行时、事务、并发、安装与负向行为测试。

## 可执行运行时

安装后设置共享运行时路径：

```bash
RMP_RUNTIME="$HOME/.codex/skills/.repository-migration-platform-runtime/migration_platform.py"
```

对一个真实Source创建不可变工作区并展开全部38个Batch：

```bash
python3 "$RMP_RUNTIME" prepare-all \
  --source /absolute/path/to/source \
  --workspace /absolute/path/to/evidence-workspace \
  --target-objective "明确、版本化的Target目标"
```

查看状态与逐Batch Profile：

```bash
python3 "$RMP_RUNTIME" status --workspace /absolute/path/to/evidence-workspace
python3 "$RMP_RUNTIME" catalog
```

每个Batch会生成`execution-plan.json`。填写精确argv、cwd、claim和超时后执行：

```bash
python3 "$RMP_RUNTIME" execute-plan \
  --workspace /absolute/path/to/evidence-workspace \
  --batch 1 \
  --plan /absolute/path/to/evidence-workspace/batches/batch-01/execution-plan.json
```

对于执行器之外产生的字节，先用`ingest-artifact`导入不可变主体，再把返回的digest、URI和bytes写入Typed Evidence envelope，使用`record`保存，由不同Actor运行`verify`，最后执行：

```bash
python3 "$RMP_RUNTIME" gate \
  --workspace /absolute/path/to/evidence-workspace \
  --batch 1 \
  --mode local
```

当前发行版的包内Trust Policy明确禁用`request-certificate`、`import-certificate`和`CERTIFIED`。只有独立治理、预置并固定信任根的新发行版才能启用该路径；调用者不能提供自己的Trust Store。

## 目录

```text
agent-skills/runtime/<skill-name>/SKILL.md
batches/BATCH_01...BATCH_38...
source-specs/
schemas/
templates/
scripts/validate_package.py
scripts/migration_platform.py
scripts/transaction_store.py
scripts/sync_skill_interfaces.py
trust-policy.json
tests/test_migration_platform.py
manifest.json
AGENTS.md
install.sh
validate.sh
CHECKSUMS.sha256
```

## Batch索引

| Batch | 名称 | Slug | Gate |
|---:|---|---|---|
| 01 | Migration Constitution与Source Executable Specification | `source-executable-specification` | B01 Source Baseline Gate |
| 02 | Differential Execution Harness与Deterministic Environment | `differential-execution-harness` | B02 Differential Gate |
| 03 | 10-Language Semantic Frontend与Unified Semantic IR | `semantic-frontends-unified-ir` | B03 Semantic Frontend Gate |
| 04 | 90 Directional Semantic Rule、Mutation、Test与Certification Packs | `directional-semantic-rule-packs` | DP1–DP5 |
| 05 | Framework Adapter与Framework Combination Matrix | `framework-adapter-matrix` | FA1–FA5 |
| 06 | Dependency、Native、License与Supply-Chain Graph | `dependency-supply-chain-graph` | DA/DR Certification |
| 07 | Database、Cache、Search、Object Storage与Messaging Migration | `data-messaging-migration` | DI1–DI5 |
| 08 | API、RPC、Serialization、Schema、Gateway与Service Mesh Migration | `api-gateway-mesh-migration` | CI1–CI5 |
| 09 | Concurrency、Async、Memory、Lifetime与Native Semantics | `concurrency-memory-native-semantics` | CM1–CM5 |
| 10 | Test Generation、Mutation、Fuzz、Property、Concurrency与Fault Platform | `test-mutation-fuzz-platform` | TQ1–TQ5 |
| 11 | Domain Packs与Full-Stack Journey Verification | `domain-journey-verification` | DV1–DV5 |
| 12 | Shadow、Strangler、Canary、Rollback与E1–E5 | `production-migration-runtime` | E1–E5 |
| 13 | Evidence Graph、独立裁判、红队与持续认证 | `evidence-graph-certification` | EA1–EA5 |
| 14 | Formal Verification与Proof-Carrying Migration | `formal-proof-carrying-migration` | F1–F5 |
| 15 | Counterexample-Guided Repair与自演进验证 | `counterexample-guided-repair` | CR1–CR5 |
| 16 | Target Architecture Search与Migration Planning | `architecture-search-planning` | AP1–AP5 |
| 17 | Migration Execution OS | `migration-execution-os` | MX1–MX5 |
| 18 | Complete Project Generation Standard | `complete-project-generation` | CP1–CP5 |
| 19 | 90路径Executable Generator Packs | `executable-generator-packs` | GP1–GP5 |
| 20 | Skill SDK、Runtime、Registry与产品化封装 | `skill-productization` | SC1–SC5 |
| 21 | System Capability Closure Registry | `capability-closure-registry` | Capability Closure Gate |
| 22 | Business-Line Functional Closure Packs | `business-line-closure` | Business-Line Closure Gate |
| 23 | Cross-Business Journey、Saga与逻辑闭环 | `cross-business-journey-closure` | Cross-Business Journey Gate |
| 24 | End-to-End Data Flow、Lineage与Completeness | `data-lineage-completeness` | Data Flow Closure Gate |
| 25 | Data Quality、Reconciliation与Accounting Integrity | `data-quality-reconciliation` | Data Integrity Gate |
| 26 | Management Console与Control Plane Functional Closure | `admin-control-plane-closure` | Admin Closure Gate |
| 27 | Identity、Authorization、Approval与Audit Closure | `identity-authorization-audit` | Identity & Authorization Gate |
| 28 | Functional Usability与Operational Usability | `functional-operational-usability` | Usability Closure Gate |
| 29 | System-Wide Regression与Change Impact Assurance | `system-regression-assurance` | System Regression Gate |
| 30 | High Availability、Resilience与Disaster Recovery | `ha-resilience-dr` | Resilience & DR Gate |
| 31 | Concurrency、Idempotency与Transaction Correctness | `concurrency-transaction-correctness` | Concurrency & Transaction Gate |
| 32 | Performance、Capacity、Scalability与Cost Assurance | `performance-capacity-cost` | Performance & Capacity Gate |
| 33 | Migration Security与Data Protection Assurance | `migration-security-data-protection` | Migration Security Gate |
| 34 | External Integration与Provider Reliability Closure | `provider-reliability-closure` | Provider Reliability Gate |
| 35 | Release、Go-Live与Production Acceptance | `go-live-production-acceptance` | Production Acceptance Gate |
| 36 | Production Operations、Support与Service Management | `production-operations-support` | Production Operations Gate |
| 37 | Post-Migration Stabilization与Source Retirement Closure | `source-retirement-closure` | Source Retirement Gate |
| 38 | Final System Assurance与SA1–SA5 Certification | `final-system-assurance` | SA1–SA5 |

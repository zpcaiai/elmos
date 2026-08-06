# Repository Migration Platform — Batch 1–38 Skills Bag

版本：`3.3.0`

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
- 347个输出、测试和外部Claim全部绑定不可变专属Oracle；38个Batch分别绑定唯一Domain Executor handler，原始工具链证据必须通过字节数和SHA-256校验。
- 38个handler均为可调用、互异的Batch领域策略；每个策略固定operation、capabilities和safety controls，并由全覆盖测试执行。跨Batch合同替换、能力证据缺失和安全断言缺失都会fail closed。
- Executor、Oracle Owner、Verifier使用Ed25519认证并强制角色冲突隔离；development、negative、holdout与production Corpus按Claim分别闭合，Holdout/Production使用独立角色。
- 权威状态使用SQLite WAL、`BEGIN IMMEDIATE`、外键、唯一约束、整数Fencing Token和哈希链事件；JSON文件只是可重建镜像。
- `trusted_adapters.py`只接受运维方Ed25519签名的Adapter Registry：可执行文件、SHA-256、版本、argv模板、参数类型、环境引用、超时、副作用等级与补偿操作均不可由仓库内容修改。变更操作要求独立Approver、幂等键和单调Fencing；超时造成的不确定副作用保持`UNKNOWN`并禁止自动重试。
- `production_closure.py`实现客户快照只读摄取、内容摘要最小化、独立Holdout封存、切换/回滚状态机、并发版本与Fencing、七天生产长稳下限、心跳间隔和独立认证报告导入。测试或Sandbox结果只能到`LOCAL_TOOLKIT_PASS`，导入报告也不能在仓库内开启认证。
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

验证会执行包结构、Skill接口、依赖DAG、Schema、Checksum以及运行时、事务、并发、安装、
真实工具链适配和负向行为测试。

## 真实数据库与Provider垂直切片

`scripts/real_toolchain_e2e.py`只创建唯一命名、可清理的一次性资源。它将精度和事务Fixture从
PostgreSQL 16经真实`pg_dump`/`pg_restore`迁移到PostgreSQL 17（或显式指定的目标镜像），
执行逐行对账、负向约束、事务回滚、校验和绑定的幂等Expand迁移和备份恢复；同时通过真实
S3 API执行MinIO put/get/delete/cleanup，并通过已认证只读GitHub Provider API核对精确Commit。

```bash
python3 scripts/real_toolchain_e2e.py \
  --output /absolute/new/evidence-directory \
  --github-repository zpcaiai/elmos \
  --github-sha "$(git rev-parse origin/main)"
```

命令会生成Batch 07和Batch 34的`domain-execution-result`并交给包内Claim-Oracle dispatcher
验证。这是真实的一次性development执行证据；独立Holdout、客户生产切换、破坏性Cloud apply
和外部认证机构仍为`NOT_RUN` / `NOT_CERTIFIED`。

生产闭环的 v2 切换计划必须绑定精确 Provider、账户摘要、Region、Adapter 以及 precheck / execute /
verify / rollback 操作。每次 Provider 状态转换同时校验包装回执和原生 Adapter 回执的真实字节；
生产 soak 只能在切换成功后近实时启动，至少运行七天，心跳间隔不超过六小时，并执行最低可用性、
最高错误率、最少观察数和独立最终验证者门禁。生产独立评估还必须绑定精确 run、cutover、release
及 Provider 账户；导入后依旧保持 `certified=false`。

Holdout 的 `SEALED` 只表示语料保管完成，不表示测试通过。`record-holdout-result` 必须导入逐 Claim
真实证据、Provider 执行回执，并由清单中预先声明且互不重叠的 Holdout Executor 与 Verifier 双签；
生产 v2 切换和 soak 都必须引用与同一 release、账户和 tenant 匹配的 `PASS` 结果。

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
  --actor-trust-store /absolute/path/to/actor-trust-store.json \
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

数据库、Cloud、SCM和迁移工具等Provider副作用应通过签名Adapter执行，而不是把仓库字符串直接当命令。安装后的入口为
`.repository-migration-platform-runtime/trusted_adapters.py`；请求必须绑定当前Source指纹、精确Batch、签名Registry、
幂等键和Fencing Token。成功Receipt仍需进入下面的Claim-Oracle与独立Verifier链，不能直接形成认证。

客户生产闭环通过`.repository-migration-platform-runtime/production_closure.py`记录。它只摄取已授权、
逐字节校验的Manifest和Provider Receipt，不保存客户文件内容；Snapshot、Holdout、Approver、Executor、
Verifier与独立Certifier身份必须分离。切换只允许预定义状态转移，任何竞态只有一个版本可提交；
生产长稳窗口少于七天、心跳断档、关键失败或证据摘要不一致均失败关闭。

真实领域工具链先生成`domain-execution-result`。包内dispatcher调用注册的唯一handler，要求其
`domain_contract`与该Batch的operation、capabilities和safety controls完全一致；每项能力都必须
同时绑定成功工具记录、原始证据字节角色和Claim专属Oracle断言。随后才会验证Claim、环境、
Corpus和工具版本并转换成专属Claim-Oracle主体。仓库内容不能选择命令或handler：

```bash
python3 "$HOME/.codex/skills/.repository-migration-platform-runtime/domain_executors.py" \
  /absolute/path/to/domain-execution-result.json \
  --evidence-root /absolute/path/to/approved-evidence-root \
  --output /absolute/path/to/claim-oracle-result.json
```

再把Claim-Oracle主体写入Typed Evidence envelope，以签名Executor和Oracle Owner运行`record`，由不同签名Verifier运行`verify`，最后执行：

```bash
python3 "$RMP_RUNTIME" gate \
  --workspace /absolute/path/to/evidence-workspace \
  --batch 1 \
  --mode local
```

工作区可以绑定Actor Trust Store来认证Executor、Oracle Owner和Verifier；绑定后Digest不可变。它与认证CA Trust Policy严格分离。当前发行版的包内CA Trust Policy仍明确禁用`request-certificate`、`import-certificate`和`CERTIFIED`，调用者不能用Actor Trust Store自行开启认证。

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
scripts/actor_trust.py
scripts/oracle_registry.py
scripts/domain_executors.py
scripts/domain_handlers.py
scripts/trusted_adapters.py
scripts/production_closure.py
oracle-registry.json
domain-executor-registry.json
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

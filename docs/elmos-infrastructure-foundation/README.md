# eLMOS Infrastructure Foundation Skills v1.0.0

面向 Codex、Claude Code 及其他支持仓库级 Skills 的编码代理，用于把 eLMOS 的基础设施增强需求落实为可执行的工程任务。

## 包含内容

- **22 个 Skills**
- **719 条带稳定 ID 的任务**
- 安全控制面、Temporal/Runner 可靠性、不可变 Snapshot、CAS/Action Cache、Staging、可复现工具链
- 增量语义索引、远程执行与调度、分级沙箱、Canonical Semantic IR
- Model Gateway、Agent 预算和工具控制、Verification Fabric、E1-E5 认证
- Evidence Pack、OPA/SBOM/SLSA/签名、OpenTelemetry/FinOps/系统运行时 ETA
- Shadow/Canary、备份恢复与确定性重放、规模与安全认证
- 第一条可收费的 Java 现代化闭环和最终生产就绪门禁
- JSON Schema、模板、示例、阶段计划、任务 CSV/JSON、安装/卸载/验证/打包脚本

## 关键边界

**Static bundle validation（静态包验证）不等于生产实现验证。**

本包是**实现规范和可执行任务包**。`verify.sh` 通过表示包结构、Schema、脚本和测试通过；它不等于目标 eLMOS 仓库中的真实数据库迁移、Provider 集成、Sandbox、Temporal、备份恢复、压力测试或客户 Pilot 已经执行。

生产状态只能由 `elmos-production-readiness-gate` 根据实际执行 Evidence 输出：

```text
CERTIFIED
LIMITED
EXPERIMENTAL
BLOCKED
```

## 安装

在包目录中运行：

```bash
# 通用 Agent Skills 目录
./install.sh /path/to/elmos --profile universal

# Claude Code
./install.sh /path/to/elmos --profile claude

# Codex
./install.sh /path/to/elmos --profile codex

# 同时安装到三种目录
./install.sh /path/to/elmos --profile all
```

安装位置：

```text
universal -> <target>/.agents/skills/
claude    -> <target>/.claude/skills/
codex     -> <target>/.codex/skills/
```

配套资料安装到：

```text
<target>/docs/elmos-infrastructure-foundation/
<target>/schemas/elmos-infrastructure-foundation/
<target>/templates/elmos-infrastructure-foundation/
<target>/scripts/elmos-infrastructure-foundation/
<target>/plans/elmos-infrastructure-foundation/
```

先预览：

```bash
./install.sh /path/to/elmos --profile all --dry-run
```

覆盖已安装文件：

```bash
./install.sh /path/to/elmos --profile all --force
```

## 验证

```bash
./verify.sh
```

手动执行：

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
bash scripts/smoke-test.sh
```

## 推荐入口

完整基础设施计划：

```text
$elmos-infrastructure-program-orchestrator
```

第一条商业闭环：

```text
$elmos-java-migration-production-loop
```

针对单个能力：

```text
$elmos-content-addressed-cache
$elmos-temporal-task-reliability
$elmos-secure-sandbox-runtime
$elmos-verification-fabric
```

最终发布判断：

```text
$elmos-production-readiness-gate
```

## 推荐执行顺序

1. `elmos-infrastructure-program-orchestrator`
2. `elmos-architecture-contract-governance`
3. `elmos-identity-tenant-security`
4. `elmos-temporal-task-reliability`
5. `elmos-repository-snapshot-workspace`
6. `elmos-content-addressed-cache`
7. `elmos-reproducible-toolchain`
8. `elmos-staging-snapshot-promotion`
9. `elmos-incremental-semantic-index`
10. `elmos-runner-scheduler-execution`
11. `elmos-semantic-ir-compiler-platform`
12. `elmos-secure-sandbox-runtime`
13. `elmos-model-gateway-agent-runtime`
14. `elmos-policy-supply-chain-signing`
15. `elmos-verification-fabric`
16. `elmos-evidence-pack-offline-verification`
17. `elmos-java-migration-production-loop`
18. `elmos-observability-finops`
19. `elmos-backup-recovery-replay`
20. `elmos-progressive-delivery`
21. `elmos-scale-benchmark-certification`
22. `elmos-production-readiness-gate`

## 运行时间报告规则

eLMOS 的时间估算必须分开报告：

```text
Autonomous system runtime:
  eLMOS 自主生成/转换实际占用的机器墙钟时间
  = queue + execution + model + validation + transfer + retry/recovery

Human-equivalent effort:
  人工从零实现、转换、测试、Review 的等价工程时间

Human-in-the-loop delay:
  等待审批、客户回复或人工处理的自然时间，单独列出
```

不得用“人天”代替系统自己的运行 ETA。详细契约见 `docs/RUNTIME-ESTIMATION.md` 和 `schemas/runtime-estimate.schema.json`。

## 主要索引

- `docs/SKILL-INDEX.md`
- `docs/IMPLEMENTATION-ROADMAP.md`
- `docs/REFERENCE-ARCHITECTURE.md`
- `docs/DEPENDENCY-GRAPH.md`
- `docs/ACCEPTANCE-GATES.md`
- `docs/FIRST-40-TASKS.md`
- `docs/JAVA-PRODUCTION-LOOP.md`
- `docs/TASK-MATRIX.csv`
- `docs/task-catalog.json`
- `skill-manifest.json`

## 包目录

```text
.
├── .agents/skills/                 # 22 个源 Skills
├── docs/
│   ├── epics/                      # 每个 Skill 的独立任务文档
│   ├── TASK-MATRIX.csv
│   └── task-catalog.json
├── schemas/                        # JSON Schema
├── templates/                      # 计划、ADR、报告、Runbook 等模板
├── examples/                       # 合法示例
├── plans/                          # 阶段与 Java 闭环计划
├── scripts/                        # 验证、索引、打包、Smoke Test
├── tests/
├── install.sh
├── uninstall.sh
├── verify.sh
└── skill-manifest.*
```

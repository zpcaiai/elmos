# Elmos FDE Autonomous Delivery & Repository Refactoring Skills v5.2.0

> 面向 Codex 实施的、兼容 Elmos `Proof-Driven Agentic Harness / Repository Semantic Compiler` 的商业生产级能力扩展包。

## 一句话定位

把 Elmos 扩展为 **FDE 自主交付与仓库级软件改造操作系统**：从客户发现、范围与价值、代码接管、可复现运行、全仓库语义建模、全问题域评估、目标架构、原子化重构、独立验证、发布准备、事故处置、采用与交接，形成证据驱动闭环。

## 本包不是

- 不是新增第 17 个路由入口；所有原子 Skill 均为 `routable: false`。
- 不是第二套 Goal、AI-SIR、运行时权限、证据或完成判定系统。
- 不是“读取源码即可保证发现所有问题”的不诚实承诺。
- 不是已经接入 Elmos 主仓库、真实编译器、数据库、云或客户生产环境的声明。
- 不是 E4/E5/P05、生产上线、合规认证或客户验收证书。

## 核心完整性模型

```text
可信审计完整性
= Observed / Detected
+ Verified-Absent
+ Unknown
+ Unsupported
+ Evidence Coverage
```

所有 Finding、Unknown、Invariant、ChangeSet、Claim 与 Readiness 必须绑定精确 `RevisionSet`、环境、版本、策略和证据。材料性 `UNKNOWN`、关键 `UNSUPPORTED`、陈旧证据、未解决副作用或缺失审批必须阻断相关完成声明。

## 包清单

- **45** 个非路由 Elmos 原子能力 Skill，每个均含 `SKILL.md / manifest.yaml / acceptance.yaml / implementation.yaml / runbook.md`。
- **12** 个 Codex 工作流 Skill，安装到 `.agents/skills/` 后按任务触发。
- **15** 个 Codex 自定义 Subagent 配置，覆盖发现、仓库考古、运行时、语义、审计、计划、执行、验证、SRE 与采用。
- **305** 条功能、非功能与治理需求。
- **279** 条正向、负向与系统边界场景。
- **21** 个问题域、**200** 个规范化问题类型。
- **26** 个可替换 Adapter 契约。
- **10** 条 Golden Route。
- **12** 个产品工作台/界面域。
- **19** 个实施批次、**506** 个 Codex 可执行任务。
- JSON Schema、示例、OpenAPI、AsyncAPI、MCP 工具草案、PostgreSQL 迁移、Rego 策略、工作流契约、模板、评测集和可执行参考内核。

## 与 Elmos 现有架构的边界

- 要求 Elmos `>=5.1.0`；本包版本为 `5.2.0`。
- K1–K8 仍分别拥有意图/目标、仓库事实与运行时、语义真值、推理规划、变换、验证、持久执行与副作用、独立完成判定。
- `routeOwnerRef` 使用符号绑定，安装到真实仓库时必须解析到现有唯一 owner。
- 本包独立最高声明为 **E3 capability readiness**；E4/E5/P05 由 `elmos-functional-assurance-certification-skills` 与真实授权环境承担。

## Codex 使用入口

```bash
# 1. 解压并验证本包
./validate.sh --strict

# 2. 查看安装计划，不改目标仓库
./install.sh --repo /path/to/elmos --host both --profile p0 --dry-run

# 3. 在干净 Git 工作区安装；冲突文件先备份并写 receipt
./install.sh --repo /path/to/elmos --host both --profile p0 --force

# 4. 在目标仓库中让 Codex 先执行
# “使用 elmos-fde-package-navigator，检查本包与现有 K1-K8/Domain Pack 的绑定差异，生成 B00-B05 实施计划，不修改生产代码。”
```

## 推荐实施顺序

1. **B00–B05**：契约、权威边界、账本、仓库接管、Native Runtime Lab、System Graph。
2. **B06–B09**：Finding/Unknown 统一模型、十域审计、根因组合、业务不变量与目标架构。
3. **B10–B13**：原子 ChangeSet、三类转换路线、验证网、发布准备/事故/交接。
4. **B14–B17**：产品工作台、Adapter 生态、多租户商业运营、复用学习与组合治理。
5. **B18**：500k/1M+ LOC、真实工具链、故障/恢复、客户隐藏集与独立发布门槛。

## 目录

```text
.agents/skills/                 Codex 工作流 Skills
.codex/agents/                  Codex 自定义 Subagents
skills/atomic/                  45 个 Elmos 原子能力契约
catalog/                        需求、场景、问题本体、路线、批次、任务和追踪矩阵
contracts/                      JSON Schema、示例、OpenAPI、AsyncAPI、MCP 草案
adapters/                       26 个 Adapter 契约及一致性测试要求
golden-routes/                  10 条端到端路线
workflows/                      持久工作流规范
policies/                       默认拒绝、证据、租户和生产写策略
migrations/                     参考持久化迁移
reference/                      可执行参考语义内核
evals/ fixtures/ tests/         触发、产品行为、故障与回归资产
templates/                      FDE 和软件改造交付模板
docs/ implementation/          产品、架构、UX、风险和实施说明
```

## 完成声明

本包生成和验证成功，只能证明包结构、契约、依赖、示例、参考逻辑、安装器和归档的一致性。真实 Elmos 实现仍需逐批接线、执行原生工具链和独立验证。

# Elmos Assurance v4 — 整合设计与实施总览

详细源码、schemas、workflows与每个Skill的验收见完整ZIP。以下为交付总览，非已实现产品认证。


---

## 文件：README.md

# Elmos Assurance & Ethen Independent Audit — Skills Package v4.0.0

**交付日期：2026-09-09 · 交付类型：工业实现契约 + Agent Skills + 可执行参考内核 + 验收规范。**

这不是已部署的 Elmos 产品，不是客户项目 E5 证书，也不是第三方认可/法定认证。本包自己的检查通过，只能说明本包相应文件与参考实现通过了列明的检查。真实仓库改造、数据库/框架原生运行、Lean 内核校验和 Ethen 真实签署必须分别记录证据；未运行项保持 `NOT_RUN`。

## 目标

把四条业务线统一接入可验证的软件交付闭环：

`需求/源仓库 → 接口发现与契约 → 覆盖义务 → 独立测试生成 → 构建 → 冒烟 → 全功能回归 → 差分/性质/变异 → 形式化义务 → 证据封存 → Ethen 审计 → K8 签署 → 持续复验/撤销`。

业务线保持：多语言项目生成、SQL/SQL routine 转换、Spring 老项目现代化、仓库级跨语言转换。认证能力是共享横切扩展，不新增第五条业务线；按既有设计约定不增加原 16 条 canonical routes，接入时仍须先核验真实仓库现状。包版本 v4 不代表将 Elmos Harness v3 整体升级或覆盖。

## 本包最重要的纠偏

1. “全覆盖”只能指**已批准范围内、具有明确分母的覆盖义务全部满足**，不承诺枚举任意输入/全部线程调度。
2. `PASS/FAIL/INCONCLUSIVE` 是判定；`NOT_RUN/RUNNING/TIMED_OUT` 是执行事实，不能混成成功率。
3. 旧系统行为是兼容性证据，不自动高于已批准需求和安全不变量；旧漏洞不应机械保留。
4. Lean 证明的是形式化命题。命题/假设/模型到源码的映射不成立，不能给项目背书。
5. Ethen 默认是一项**需真实身份配置的审计职责**，可由人、机构或独立系统承担。另一个模型不自动获得组织独立性、资格或签署权限。
6. 正式签署留在既有 K8 边界；Builder、Repair、模型、被测仓库永远拿不到签名私钥。
7. 证据绑定 source/target/build/contract/policy/environment/toolchain/tests/data/comparator/rules；更改其中任一受影响项必须失效传播或重跑。
8. 控制平面记录可幂等提交；跨外部系统不宣称无条件 exactly-once。超时后的支付/消息/部署先对账，后重试。

## 快速使用

在解压目录运行：

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-reference.txt
python scripts/validate_package.py
python -m pytest -q
python scripts/demo_reference.py
```

`demo_reference.py` 只运行隔离的演示，输出明确的 `DEMO_ONLY_NOT_A_CERTIFICATE`，没有生产签署功能。
`validation/VALIDATION_REPORT.md` 记录本次环境实测范围；依赖文件是本次参考环境的精确版本，不代替生产依赖安全审批与带哈希锁定。

### 接入现有 Elmos 仓库

```bash
# 先预览，再安装。把路径替换为真实 Elmos 根目录。
python scripts/install_skills.py --repo /absolute/path/to/elmos --agent codex
python scripts/install_skills.py --repo /absolute/path/to/elmos --agent codex --apply
```

安装器默认只计划，不覆盖已有 skill，不改用户 AGENTS.md，不执行仓库代码，不安装服务。
Codex 入口安装至 `.agents/skills/`；Claude Code 可选 `--agent claude` 安装至 `.claude/skills/`。
完整包复制到 `.elmos/assurance-package-v4.0.0/`，skill 中参考路径指向该位置。安装后按 `CODEX_START_HERE.md` 执行。

## 阅读顺序

`CODEX_START_HERE.md` → `docs/00-architecture.md` → `docs/01-contracts-and-states.md` → `docs/02-testing-and-metrics.md` → 对应 `domain-packs/*/DOMAIN.md` → `docs/03-ethen-trust.md` → `docs/04-formal-assurance.md` → `roadmap/implementation-batches.yaml`。

每个技能包含 `SKILL.md / manifest.yaml / implementation.yaml / acceptance.yaml / runbook.md`。不要一次把所有技能塞入模型上下文；由 master 按依赖和当前批次加载。

## 包内可执行范围

参考代码执行：输入模式校验、严格 JSON 摘要、测试覆盖义务计算、冒烟集合选择、类型化行比较、证据签名验证/过期/撤销检查、阻断式门禁、租约 fencing 与幂等提交的本地模型、已知缺陷的反例测试。

需要在真实 Elmos 中实现：生产 API/UI、可靠工作流/消息系统、原生语言与数据库适配器、原生回归执行器、Lean 独立复核、真实身份/KMS、商用部署、客户验收。不要把参考内核中的测试信任根接入生产。

## 既有架构兼容

保留 Elmos-owned Router、`ModelExecutionPlan`、`VerifiedSecurityContext`、`CapabilityLease`、结果拦截/提交、executor fencing；LiteLLM/Direct API/OpenRouter 均为可替换执行通道。Ethen 的模型调用也受自己的预算与数据策略约束，不复用 Builder 的记忆、凭据、测试隐藏集或签署权。

本包提供显式 `elmos.assurance/v4` gate profile。与旧 E0–E5 的映射必须经迁移记录批准；不静默重解释历史证书。详见 `docs/06-compatibility.md`。

## 交付索引

- 34个Skills，每个5文件；102个模块原生验收定义。
- 四条业务线分别提供Domain Pack、workflow、Golden Route和6项关键原生验收，共24项。
- 15份JSON Schema与15个明确标注SYNTHETIC的示例；14个控制平面HTTP操作定义。
- `contracts/ASSERTION_AND_NATIVE_RUNNER_CONTRACT.md`：可执行断言IR、wire schema绑定及受控runner计划。
- `migrations/`：12表PostgreSQL参考迁移、RLS/fencing/append-only/outbox与回滚实施约束；原生执行NOT_RUN。
- `formal/`：候选Lean/TLA模型、声明边界及禁止伪造PROVED的检查入口。
- `reference/`和`tests/`：独立可运行参考代码与针对错误放行路径的测试。
- `validation/`：本次实际命令、JUnit、结构检查、演示和边界说明。
- `PACKAGE_CONTENTS.sha256`：包内文件完整性清单，不是外部审计签名或产品认证。

安装后修改`.elmos/assurance-package-v4.0.0/`中的文件会使原始校验和失效，这是预期的。先保存原包作为基线，再把真正实现代码提交到既有Elmos模块；新版本重新生成独立证据与清单，不修改历史证明来追求绿灯。


---

## 文件：CODEX_START_HERE.md

# 给 Codex / Claude Code 的主执行指令

你要在当前实际 Elmos 仓库中实现本包，而不是再生成一套方案文档。

1. 先读取仓库 AGENTS.md/CLAUDE.md、当前路由/四业务线入口、K8、数据库迁移、工作流、身份权限、Router、测试与CI。只做授权范围内的读；不执行未知 install/build hook。
2. 运行 `elmos-assurance-bootstrap`，交付 `repo-map.json`、复用/差距清单、老新 gate 映射草案、真实 native 工具链可用性。未看到源码，不得声称对应功能已经存在。
3. 冻结本次 source/target/contract/policy/environment/toolchain/test/data/comparator/rule RevisionSet 与风险范围。先批准 normative contract、oracle 与测试义务，再写实现。推导事实与批准事实分开。
4. 按 `roadmap/implementation-batches.yaml` 执行一个纵向切片。P0 覆盖所有安全契约，并选定一条真实 Golden Route；不要同时铺开整个语言/数据库笛卡尔积。
5. 每项代码改动必须包括对应自动测试、负例、集成点、数据库兼容、观测、撤销/回滚方案。生成测试不得读取候选实现来决定 expected value。
6. 每次提交前执行真实命令，保留退出码、工具精确版本、不可变输入摘要、原始报告摘要、失败和跳过。环境缺失明确 `NOT_RUN`，不得用 mock 或包级测试替代原生测试。
7. 冒烟成功后执行完整的已批准回归计划；增量测试只能加速反馈，不能冒充最终全回归。故障修复不得删测试、放宽容差、减分母、降低安全门槛或擅改规范。
8. Ethen 身份未配置、签署服务缺失、关键证明 UNKNOWN、原生运行缺失、证据不匹配，停止正式签发，返回可定位的 INCONCLUSIVE。
9. 输出当前批次改动文件、执行命令和结果、验收ID→证据映射、剩余阻塞、下一可执行批次。只有引用当前真实证据才可标记完成。

禁止：重建一套平行 Harness；增加未经批准的 canonical route；把 Elmos Router 交给网关；让 LLM 执行 PASS 的最终决策；让 repo/agent 提交根证书/自选信任策略；自动推送主分支或部署生产；伪造 customer acceptance。

## 推荐启动文本

“读取 .elmos/assurance-package-v4.0.0/CODEX_START_HERE.md，使用 elmos-assurance-orchestrator。
对当前仓库先执行 B00，再实现 B01–B03 的可运行纵向切片；复用现有架构。
不要停在设计文档；必须交付代码、可执行测试与真实证据。遇到外部工具或权限缺失，完成其它非阻塞工作，并保持相关验收 NOT_RUN/INCONCLUSIVE。
禁止签发真实证书、修改认证范围或放宽失败测试。后续按照批次依赖继续。”


---

## 文件：SKILLS_INDEX.md

# Skills Index

每项是实施职责，不是新的业务路由。全部产品原生验收初始状态为NOT_RUN。

| Skill | 优先级 | 职责 |
|---|---|---|
| `elmos-assurance-bootstrap` | P0 | 仓库盘点与增量集成 |
| `elmos-assurance-scope` | P0 | 范围与风险保证配置 |
| `elmos-assurance-requirement-oracles` | P0 | 需求解析与独立判定基准 |
| `elmos-assurance-interface-discovery` | P0 | 多协议接口独立发现 |
| `elmos-assurance-contract-ir` | P0 | 可执行接口与语义契约 |
| `elmos-assurance-state-effects` | P0 | 状态机、副作用与时序模型 |
| `elmos-assurance-coverage-planner` | P0 | 覆盖义务与风险计划编译 |
| `elmos-assurance-test-generation` | P0 | 独立可执行用例生成 |
| `elmos-assurance-fixtures-environments` | P0 | 测试数据与原生环境工厂 |
| `elmos-assurance-smoke-gate` | P0 | 关键路径冒烟门禁 |
| `elmos-assurance-full-regression` | P0 | 全功能回归与测试资产管理 |
| `elmos-assurance-differential-runtime` | P0 | 类型化差分与行为回放 |
| `elmos-assurance-property-fuzz` | P1 | 性质、变形与模糊测试 |
| `elmos-assurance-mutation-auditor` | P0 | 领域变异与测试有效性审计 |
| `elmos-assurance-lean` | P1 | Lean命题、证明与源码绑定 |
| `elmos-assurance-model-checking` | P1 | SMT与有限状态协议校验 |
| `elmos-assurance-verified-rules` | P1 | 带证据变换规则注册中心 |
| `elmos-assurance-evidence-graph` | P0 | 证据DAG、封存与失效传播 |
| `elmos-assurance-gate-engine` | P0 | 确定性三态认证门禁 |
| `elmos-assurance-ethen-audit` | P0 | Ethen外部独立审计适配器 |
| `elmos-assurance-signed-attestations` | P0 | K8签署、发布与撤销 |
| `elmos-assurance-bounded-repair` | P0 | 有界修复与证据重新建立 |
| `elmos-assurance-generation-domain` | P0 | 项目生成业务线集成 |
| `elmos-assurance-sql-domain` | P0 | SQL/例程语义转换集成 |
| `elmos-assurance-spring-domain` | P0 | Spring旧项目原生翻新集成 |
| `elmos-assurance-repository-domain` | P0 | 全仓库语言转换集成 |
| `elmos-assurance-durable-execution` | P0 | 恢复、取消、fencing与结果提交 |
| `elmos-assurance-security-isolation` | P0 | 租户、供应链与不可信执行隔离 |
| `elmos-assurance-router-budget` | P0 | 模型路由与验证成本治理 |
| `elmos-assurance-commercial-control` | P1 | 多租户商业控制与交付产品化 |
| `elmos-assurance-calibration-holdout` | P1 | 正确率校准与隐藏基准治理 |
| `elmos-assurance-release-recertification` | P1 | 发布、持续验证与撤销链 |
| `elmos-assurance-workbench-ui` | P1 | 接口覆盖、审计和证据工作台 |
| `elmos-assurance-orchestrator` | P0 | 总编排：四业务线验证与Ethen独立审计 |


---

## 文件：docs/00-architecture.md

# 架构与商业交付边界

## 1. 三个平面，而非一个万能 Agent

**交付平面**：现有四个 Domain Pack、Generator/Converter、Repair；只产出候选物。
**验证平面**：契约、Oracle、测试、差分、变异、形式化、证据服务；读取冻结候选物，由受控执行器产生事实。
**审计/授权平面**：Ethen审计工作区、政策引擎、K8签署与撤销。独立账户、存储ACL、执行身份与审计日志。

最初可用模块化单体承载无权限冲突的控制逻辑。执行器与签署/审计信任域必须物理或等效安全隔离。不要为每个 Skill 建微服务。生产数据库沿用已验证的现有选择；本包 PostgreSQL 迁移是待适配参考，不强制替换。

## 2. 业务闭环

`Admit → Inventory → Approve scope/spec → Freeze plan → Build → Smoke → Regression → Risk verification → Seal → Audit → Decide → Sign → Observe/Revoke`。

形式化的**命题定义、规则证明**可在构建前或并行执行；不是把 Lean 全部放在最后。冒烟失败暂停依赖运行健康的昂贵作业，但不得销毁失败证据，独立可执行的规则证明可以继续。

## 3. 共享模块接口

| 模块 | 输入 → 输出 | 核心责任 |
|---|---|---|
| ScopeCompiler | 需求/资产清单 → AssuranceScope | 版本、支持范围、排除项、风险与有效期 |
| ContractCompiler | declared/observed/inferred → ContractSnapshot | 冲突、审批、接口与状态/副作用 |
| CoveragePlanner | scope+contract → ObligationSet+TestPlan | 冻结分母、可执行/可观察性 |
| RunnerBroker | TestExecutionPlan → Observations | 租户隔离、资源预算、原生执行 |
| Comparator | typed observations+policy → Differences | 不吞差异，不随意排序/容差 |
| FormalBroker | trusted challenge → VerifiedProofResult | 命题、假设、公理、源码绑定 |
| EvidenceService | observations+attestations → Evidence DAG | 内容寻址、provenance、失效传播 |
| EthenPort | sealed bundle → AuditDecision | 独立发现、挑战、利益冲突、人工确认 |
| K8Gate/K8Signer | policy+verified facts → scoped attestation | 确定性决策、授权签署、撤销 |

跨模块只用本包版本化 DTO；具体模型SDK、SQLGlot AST、Lean内存对象、JUnit类不可泄漏进入统一领域接口。

## 4. 准确率的产品目标

将“让更多项目通过”改成：降低缺陷项目获PASS的风险，同时提升在声明支持范围内的真实交付能力。
有资格缩小范围但必须明确新证书范围、原始排除风险、审批身份；不允许把有问题的接口悄悄从分母移除。

业务竞争力积累在经过反例检验的规则、Golden Route、回归资产、来源清晰的缺陷语料、能复核的证据与客户验收流程，不在 skill 数量或虚构的99.99%。

## 5. 资产而非仅接口

接口边界包含 HTTP、GraphQL、gRPC、事件、WebSocket、CLI、SDK、DB routine、文件、任务、UI流程与设备协议。
HTTP 100%不能覆盖 scheduler、数据迁移、事件重试、权限路径或UI。
不把所有内部函数都做公开接口；内部关键行为通过可信测试适配器或组件测试验证，测试端点不得进入生产镜像。

## 6. 需求到证据双向可追溯

`Requirement → Claim → Interface/State/Effect → Test obligation → Test case → Execution → Observation → Evidence → Audit finding → Decision → Attestation`。
保留 defeater（反证）、assumption、scope exclusion、waiver。发现冲突时，不以最新/最多票为真，交给明确的规范责任人。

## 7. 默认安全与经济性

每账号最多3个top-level run；子任务受同一信号量、CPU/内存/IO/token/费用预算控制。单位采用机器 wall-clock 秒和实际usage，不用人工人天冒充执行时间。
预算耗尽是 PAUSED_BUDGET/INCONCLUSIVE，绝不是缩小回归集后PASS。账户价格策略与验证门槛分离，不提供“付费放宽认证”。


---

## 文件：docs/01-contracts-and-states.md

# 契约、状态机、不可变绑定

## 1. RevisionSet

必须绑定：source或原始需求摘要、target source、实际build artifact、contract、scope、policy、toolchain、environment、test suite、fixture/data、comparator、rule set。Git commit不能替代容器/二进制摘要；同一commit在不同依赖和构建脚本下可产生不同产物。
引用格式 `sha256:<lowercase hex>` 或schema规定的裸hex，禁止混用。参考内核使用裸64位hex。

Scope与plan须经独立的控制平面批准。客户端不能通过提交更宽松policy、空obligations、自己的root keys来获得认证。可信验证配置从服务部署/受控policy存储读取，不来自被测repo。

## 2. ContractSnapshot

每条接口具有：稳定ID、协议、方向、版本、来源、路径/操作、schema、前置条件、身份/角色/租户、结果、状态转移、可观察副作用、错误、幂等性、时序、预算、兼容规则和需求关联。

`declared`、`observed`、`inferred`、`approved_normative`分别保存。静态缺失+运行时发现不是自动规范；运行时没观察到也不是不存在。发现算法记录扫描完整性、动态路由/反射盲点、编译条件、插件清单与审批排除。

Approval基于完整snapshot hash，不是基于页面标题。合同更新生成新版本，使受影响tests/proofs/evidence失效。

## 3. 四种正交状态

- 执行：QUEUED / RUNNING / PASSED / FAILED / TIMED_OUT / CANCELLED / INFRA_ERROR / NOT_RUN。
- 验证结论：PASS / FAIL / INCONCLUSIVE。
- 义务：REQUIRED / APPROVED_NOT_APPLICABLE / OPTIONAL；critical不得无审批豁免。
- 证书：DRAFT / ISSUED / SUSPENDED / REVOKED / EXPIRED / SUPERSEDED。

timeout不自动是语义错误。若deadline本身是验收要求，超限可为FAIL；若执行器故障则是INCONCLUSIVE。即使恢复重试PASS，也保留首次失败并判断flake。

## 4. 运行状态机

NEW→SCOPED→CONTRACT_APPROVED→PLANNED→BUILDING→SMOKE→REGRESSION→ADVANCED→SEALED→AUDITING→DECIDED。
失败候选经授权 REPAIRING→新RevisionSet→新run；不能修改SEALED run。
取消通过CANCEL_REQUESTED→CANCELLING→CANCELLED，提升fencing epoch，停止新作业，等待/对账已开始的副作用。
AUDITING后有代码变化必须回到新run，而不是保留原review批准。

## 5. Gate profile `elmos.assurance/v4`

本profile新增，不默默替换历史v3定义。

| level | 本profile必须的证据 |
|---|---|
| E0 | 资产/工具链/构建/环境可重建；完整性 |
| E1 | 已批准接口/需求/风险范围；覆盖分母与Oracle |
| E2 | 启动、依赖与关键业务路径冒烟 |
| E3 | 全部已批准功能/状态/权限/事务/副作用回归 |
| E4 | 适用差分/性质/变形/fuzz/变异/非功能风险门槛 |
| E5 | 风险规定的形式化义务 + Ethen独立审计 + 全部前置证据 + K8授权签署 |

E5不能意味着整个程序都被形式化证明。每张证书另列 formal_claims、model_bound、assumptions与未涵盖属性。仅E0构建通过也不得显示“软件正确”。

## 6. 通用执行合同

Task/Attempt携带 VerifiedSecurityContextRef、CapabilityLeaseRef、ModelExecutionPlanRef、deadline、tenant/project/run/step、fencingEpoch、retryBudget、idempotencyKey。
恢复时保留原权限上限，同时重验当前授权/吊销/期限；过期lease不得复活，换发必须记录链，不能继承过宽权限。
传输可at-least-once；持久结果 `(tenant,run,step,epoch,idempotencyKey)`幂等。外部effect用effect key+outbox/inbox+对账/补偿。Ambiguous outcome阻断自动重发。

## 7. 错误分类

CONTRACT_DRIFT / SCOPE_INCOMPLETE / ORACLE_CONFLICT / UNSUPPORTED_SEMANTICS / TEST_FAILURE /
INFRA_UNAVAILABLE / FLAKY_CRITICAL / EVIDENCE_TAMPERED / EVIDENCE_STALE / REVISION_MISMATCH /
PROOF_UNKNOWN / PROOF_AXIOM_DENIED / AUDITOR_NOT_CONFIGURED / AUDITOR_CONFLICT /
SIGNER_UNAVAILABLE / LEASE_EXPIRED / FENCE_REJECTED / BUDGET_EXHAUSTED / SIDE_EFFECT_UNKNOWN。
服务同时给machine code、stage、retryable、remediation、traceId；不返回密钥/源码正文。


---

## 文件：docs/02-testing-and-metrics.md

# 测试设计与可解释指标

## 1. 完整的测试不是输入笛卡尔积

将每项义务表达为 `interface × requirement × state/transition × input partition × role/tenant × failure mode × effect × platform` 的**已批准风险选择**。
关键权限/跨租户/资金/事务/幂等路径显式覆盖；普通组合可用pairwise/t-wise，但报告必须标记组合强度而非声称全部组合。

分别显示 planned、executable、executed、asserted、passed。HTTP请求被发出不等于响应语义、副作用或权限已被断言。分母为空显示 N/A/INCONCLUSIVE，不能100%。
覆盖计算基于冻结且有哈希的 ObligationSet，证据要求匹配该版本。独立接口发现以集合差异判断，不仅比较数量。

## 2. Oracle优先规则是职责，不是一个万能排序

- 正确性：客户/领域责任人批准的规范、不变量、安全政策。
- 兼容性：source runtime/golden traces，但要列明已批准的行为改变。
- 差分：source和target一致只能证明这次观测一致，可能共同犯错。
- 数学/性质：用独立reference implementation或经批准的代数/状态关系。
- 变形关系必须带前提；LLM生成的expected只是待审候选。

两种oracle冲突时新建finding；不得选择让测试通过的一方。规范生成与实现生成分支必须独立评审；同源规范本身错误仍可能使两者一起错。

## 3. 冒烟与全回归

冒烟按critical risk/dependency/历史故障选择低成本集合，必须包含真实业务canary，health=200不够。
若smoke不能覆盖所有规定关键义务，返回缺口而不是截断预算继续PASS。
Smoke通过才调度依赖其环境的全回归。全回归执行固定manifest中的全部必需case，不是把test runner恰好发现的集合当作“全部”。
最终发布全回归在同一候选artifact上运行。增量impact analysis只用于修复反馈；要复用证据须满足完整dependency closure、scope/policy批准、有效期与未变假设，不能复用旧artifact下的“全回归完成”。

## 4. 隔离、可复现、异步时序

每个scenario拥有独立DB schema/namespace、逻辑时钟和seed。真实secret由broker发短期token。
记录clock/timezone/locale/collation、随机seed、外部依赖版本。事件以correlationId和因果偏序比较，不用全局任意排序消除真实竞态；eventual consistency使用规范规定的deadline/稳定窗口。
UI单独记录DOM/无障碍树、网络、最终状态；视觉差异只在固定viewport/font/渲染版本下比较，不能仅凭截图判断功能。

## 5. 变异正确用法

标准化mutant状态：KILLED / SURVIVED / PROVEN_EQUIVALENT / INVALID / TIMEOUT / INFRA_ERROR / UNREACHED / UNKNOWN。
只允许有独立复核证据的equivalent/invalid从有效分母排除；TIMEOUT不默认算killed。
保守kill ratio：`KILLED / (KILLED + SURVIVED + UNREACHED + TIMEOUT + INFRA_ERROR + UNKNOWN)`；另报已确定有效分母上的ratio与未决数量。分母未收敛不能给critical PASS。

盲变异在克隆副本注入，不污染最终交付物；区分是在评估test suite、整个certifier还是Ethen。真实历史bug corpus与synthetic mutants分开报告。
禁止要求无依据的99.9% mutation目标。每个domain/profile先测baseline并经独立校准批准阈值；关键安全语义的指定must-kill集合必须全杀。

## 6. 两种“假通过率”不可混淆

`Defective-PASS rate = 缺陷样本中PASS数 / 经独立标注的缺陷样本数`，即P(PASS|defect)。
`Bad-certificate fraction = PASS样本中有缺陷数 / 经独立复核的PASS样本数`，即P(defect|PASS)。

还报 defect recall、false rejection、abstention、coverage debt、escaped critical defects、反例缩减率、每认证artifact的CPU/token/费用、P50/P95 wall-clock。

零失败不等于零风险。对独立同分布样本、固定判定规则、预先选定n，0/n事件的单侧95%二项上界为 `1 - 0.05**(1/n)`。例如 n=100约2.95%；n=3000约0.0998%。相关的同repo变异不能当3000个独立项目；按项目/缺陷族聚类并分层报告。该上界不自动适用于真实生产分布。

## 7. 测试质量红线

空suite、无assert、只assert status、过度mock关键effect、跳过critical、无限retry、泄露holdout、snapshot盲更新、放大浮点容差、把NULL变空串、bag去重、timestamp去时区、把未排序结果强行排序，均有专门负例。

## 8. 发布前完整测试组合

功能与契约 → 工作流/状态 → 权限/隔离 → DB/MQ/cache副作用 → 差分 → 性质/变形 → fuzz → 变异 → 安全/供应链 → 负载/故障/恢复 → 适用形式化 → Ethen challenge。
每层声明适用范围、原生工具、observation adapter和gate，不要求所有业务都使用所有工具。


---

## 文件：docs/03-ethen-trust.md

# Ethen：外部审计职责、独立性和签署

## 1. 身份语义

保留用户给定拼写 `Ethen`，不假定是某个公开产品，也不假定它已经存在、具备认可资质或必然是AI。
配置 `auditor_kind = human | organization | external_system`、subjectId、organizationId、controlDomain、key/identity ref、授权范围、有效期、利益冲突声明。
未配置默认 AUDITOR_NOT_CONFIGURED，E5无法签发。

若Ethen是Elmos作者本人，可以做个人复核/产品责任人审批，但不能标为组织独立的第三方认证。UI与证书区分 `self-reviewed`、`separate-agent`、`separate-control-domain`、`independent-organization`。换一个模型或Prompt仅减少部分同源偏差，不满足组织独立性。

## 2. 五权分离

Builder写候选代码；TestAuthor写公开测试候选；Runner运行被批准测试并产生事实；Ethen挑战/审核；K8Signer按规则签署。
生成/修复无权读隐藏集、改规范批准、改policy、注册根密钥、修改封存证据或发证。
Ethen可提出修复建议但不直接改待认证artifact；一旦参与代码修复，标记冲突，另请符合profile独立性的人/系统复核。

## 3. 审计步骤

核对scope与批准身份 → 独立发现接口（集合不是数量）→ 检查覆盖分母/排除与Oracle → 抽样重建/重跑高风险证据 → 隐藏challenge → 克隆副本盲变异 → proof statement/assumptions/绑定审核 → 缺陷处置 → 签署review decision。

不要把Elmos“为什么认为通过”的推理作为规范；审计必须得到原需求、批准合同、源/目标物、已知缺陷和限制。盲审不应隐瞒事实证据或风险。

## 4. 隐藏集治理

独立bucket/key/worker与访问日志；Builder仅可见已批准的最小反例，不能读seed、完整hidden prompts或下一轮case。
修复暴露的challenge进入public regression并退役；换新的holdout防止过拟合。保留commitment、seed escrow、dataset version、contamination检查和抽样设计。
同一人拥有两套凭据不等于独立机构；审计日志必须记录实际控制关系。

## 5. 人工模式协议

Ethen登录独立身份，读取seal ID，选择审核样本/提出challenge，查看原始证据和规范差异，作出 APPROVE/REJECT/NEEDS_EVIDENCE。
批准绑定 `(tenant, project, run, revisionSetHash, scopeHash, policyHash, evidenceRoot, reviewNonce, expiresAt)`。
双因素/强认证策略由现有IdP执行；server检查audience/nonce/授权与重放，不接受一个前端checkbox或普通JSON名字作真实签名。
审计approval不是最终certificate；K8重新验证授权、撤销列表和全部gate，才签署。

## 6. 系统模式协议

mTLS/workload identity + allowlisted issuer/subject/audience；异步audit job、有deadline与幂等键；报告自定义JSON Schema，产物使用内容寻址。repo中的任意回调URL禁止，需运营配置endpoint registry。
外部系统的LLM只能产生findings与测试建议；deterministic policy评估核验事实。审计服务自身也需校准/隔离/版本记录。

## 7. 原始数据与最小披露

来源授权、客户同意、个人信息脱敏、源码/data classification、地域与保留要求先于发送审计。不能因为名为“外部审计”就复制生产数据库给外部模型。
签名凭据在KMS/HSM或现有授权签署系统，代理只接收key ref；没有该环境本包只形成 unsigned draft。

## 8. 撤销与争议

发现遗漏接口、证据造假、关键新bug、签署密钥泄露或适用环境改变时 suspend/revoke；证书页实时展示status及最新查询时间。
保留appeal、复核者、原始决定与纠正动作，禁止覆盖历史FAIL。
提供的是明确范围的工程保证声明；获得真正外部认可资质需要另行流程，不能借E5命名暗示已有资质。


---

## 文件：docs/04-formal-assurance.md

# Lean / SMT / 状态模型的适用边界

## 1. 必须证明的是正确的命题

流程：已批准业务claim → 可信challenge statement → 形式语义/假设 → 待证rule/程序义务 → 不可信proof候选 → 隔离编译 → 内核/外部checker → statement一致性 → precondition实例检查 → source/IR/target/artifact绑定 → 证据。

Lean kernel接受proof term不意味着需求正确、SQL引擎符合模型、代码生成器无bug或目标可上线。所有这些都需单列义务。将trusted computing base、外部公理、FFI/native-evaluation、编译器、库、checker版本列入证据。

## 2. 技术选择

Lean：小型可组合变换规则、精确算术、数据不变量、DSL解释器与规范保持。
SMT：有界路径、约束/反例、类型/数值前置条件。SAT表示有模型，UNSAT只有在编码/逻辑/证明验证约束正确时支持所声明结论；UNKNOWN绝不是PASS。
TLC/状态模型：租约fencing、预算/幂等/取消、事件协议的有限模型。通过的是所声明的finite bound，不是无限部署的证明。
原生差分：处理真实运行时、框架、DB dialect与环境；不能用形式模型替代全部原生证据。

## 3. Lean严格模式

锁定工具链版本与下载/镜像摘要。示例候选为截至2026-09-09官方release页可见的 v4.33.1；**本交付环境没有Lean/Lake，示例未编译**，生产仍需完整工具链批准。
可信工作区保存challenge与imports允许清单；proof候选构建在无网络、限额沙箱。禁止导入候选仓库自带的“证明通过器”来审核自己。

对目标theorem做传递公理审计（不是只grep源码）；禁止 sorryAx、自定义未批准公理和扩大信任边界的途径。对native evaluation的处理按精确版本核实，不能沿用旧版本名称当充分检查。
标准公理也需profile允许。`#print axioms`只是检查的一部分；恶意metaprogram/build/olean仍需sandbox、可信statement comparator与独立核验。
严格profile使用官方验证文档描述的comparator+支持该精确语言版本的外部checker。没有兼容外部checker时保留INCONCLUSIVE或申请较低、准确命名的assurance profile，不伪称双核通过。

## 4. 规则证明与实例验证

VerifiedRule带 source/target DSL版本、preconditions、semantics model版本、theorem hash、known counterexamples、evaluator/encoder/lowering版本、runtime regression与批准身份。
“证明一次复用”只适用于相同rule/semantics/toolchain与precondition有效的实例。LLM声称满足前置条件不够，必须有静态可判定验证、证明或真实运行证据。规则撤销按依赖图撤销所有受影响结果。

## 5. SQL例子：不要遗漏外层NULL

将 `x NOT IN (SELECT y FROM T)` 改成相关 `NOT EXISTS(... WHERE y=x)`，只要求T.y非NULL仍不充分：当x为NULL且T非空时两者WHERE选择可能不同。
常用的**充分前提**需覆盖外层x与内层y都非NULL，并保证比较、类型转换/排序规则与相关条件一致；空集边界单列测试。更复杂谓词必须重新建模。
本包 `formal/lean/ElmosProofs.lean` 只给出Bool条件/列表bag子语言中的明确小定理；不是通用SQL等价证明。`examples/sql_null_counterexample.py` 可运行并复现NULL陷阱。

## 6. 项目级形式化覆盖

分母是已批准的critical formal obligations，不是函数行数或theorem数量。证明100个琐碎定理不能覆盖1个未证明的资金不变量。
存在未声明假设、模型不适用、前置条件未知、源码绑定缺失，formal_claim不能PASS。formal N/A也需scope说明，E5证书明确哪些不是formal assurance。

## 7. 反例与现实接口

保持源码span/IR node/rule instance/observation字段可追踪；将SMT或fuzz counterexample最小化成native regression；证明失败可以生成有价值测试，但不能自动删掉原claim。


---

## 文件：docs/05-runtime-and-security.md

# 执行安全、可靠性与运维

## 不可信输入

源码、构建脚本、测试、proof、OpenAPI external $ref、归档、DB dump、日志都视为不可信。禁止通过prompt或repo文件提升权限。
解压校验path traversal/symlink/压缩炸弹/绝对路径；解析器限depth/bytes/time；外部引用默认离线禁用，按allowlist resolver获取后固定hash，防SSRF/元数据地址/DNS rebinding。

## Runner

生产用现有安全隔离方案，普通容器不自动等于足够的敌对代码沙箱。按风险采用microVM/强化隔离；禁止host docker socket、hostPath、privileged、root凭据；限制syscalls、CPU/内存/PID/磁盘/egress。构建取依赖与测试执行分阶段，依赖mirror审批锁定，测试默认无公网。
旧Spring runtime放隔离lane，不把过时服务暴露公网。DB credentials和测试数据按scenario划分，执行销毁/TTL并记录清理证据。

## Workflow

现有durable workflow为首选，不为接入再强制引入Temporal/LangGraph。引擎需要：持久状态、可重放history、租约/epoch、取消、超时、版本隔离、幂等与outbox。
Control plane: admit/reserve预算与3并发名额→持久plan→dispatch；worker仅可执行lease内步骤。
结果进入Result Interception，检查schema/authority/epoch/subject/provenance后原子commit。旧worker的迟到结果拒绝且留审计。

## 预算与费用

预留≠消费；每次attempt实际CPU秒、DB秒、token和供应商usage按唯一计费键入账。超时usage未知标记pending reconciliation，不计作0。
重试消耗原任务retry预算且独立usage记录；同一真实attempt重复回执不得双记。退款/纠错用反向ledger，不删历史。
Ethen有独立成本中心，不因Builder预算不足跳过Ethen。未知残余费用保守留reservations。

## 可观测性

trace: tenant(受控内部)、project/run/step/attempt、revision hash、worker epoch、model plan、oracle/checker版本。默认不记录源码/提示词/测试真实PII。
指标：queue wait、各stage wall-clock、mandatory NOT_RUN、coverage debt、critical survivors、evidence rejection、audit waiting、false-pass calibration、cache hit、cost per certified artifact。
告警：签署绕过=page；cross-tenant访问=page；证据seal失败=block；deadline和预算耗尽=可见暂停。

## 灾难与演练

故障矩阵包括：worker启动前/副作用后/commit前崩溃、重复dispatch、消息乱序、DB failover、对象存储不可用、签署服务故障、时钟偏差、lease吊销、租户噪声、KMS轮换。
Backup/restore必须恢复run状态与证据hash一致，不能恢复已吊销证书为有效。RPO/RTO按真实环境实测批准；不在包中编造已达到指标。

## 数据保留

客户源码不进入跨租户cache或训练语料。跨项目规则可以复用抽象结构，但需provenance/授权/IP扫描，禁止重用客户机密片段。
WORM/证据保留与客户删除策略存在冲突时，以合同和合法授权的分层保留策略解决；脱敏摘要并不总等于匿名数据。正式政策须由责任人批准。


---

## 文件：docs/06-compatibility.md

# 与既有 Elmos v3 / Router / 认证体系兼容

本包是 assurance extension，不更换八核或现有route owner。既有资料中K8承担独立证书签署，已有scope compiler、holdout与assurance-case方向，本包优先复用并补齐实际缺口。

## Bootstrap必须建立实际映射

`existing module/path → this package contract → reuse | extend | absent | conflict`。
确认业务线dispatcher/16 canonical routes，不允许仅根据旧文档推断当前代码一致。若不一致，记录真实数量与迁移需求，不强改回假定值。

## E0–E5

旧文档对E级含义可能不同。本包使用namespace `elmos.assurance/v4`；历史证书保持旧profile ID、原字段、原有效期。显式迁移mapping要说明是否需要重跑，不给老E5自动换新E5徽章。
JSON Schema兼容以N-1 fixtures验证；breaking字段使用versioned envelope和upcaster。未知版本fail closed，不默默忽略字段。

## Router/Harness

每模型调用接收已持久 `ModelExecutionPlan`，经Elmos-owned policy routing。Direct/LiteLLM/OpenRouter不进入领域DTO。审计/测试生成不例外，但使用隔离purpose/security context与cost center。
模型输出只是CandidateArtifact/TestCandidate/ProofCandidate/FindingCandidate；需验证器接收并commit才能成为事实。

## 渐进发布

feature flags: assurance_v4_shadow、contract_ir_v4、ethen_external_audit、formal_strict、k8_v4_signing。
先shadow读既有任务→比较旧新决策→人工核对差异→小scope执行→Ethen审核→才允许新签署。
回滚关闭新admission；在途run按原profile安全完成或取消；不得删除新证据/回滚撤销记录。

## 不新增平行事实源

引用现有Tenant/Project/Task/Artifact/Usage模型，保留其主键/租户控制。示例迁移带独立schema只为评审，正式落地按实际实体归并。Skill文档中模块路径为逻辑建议，不是现有repo事实。


---

## 文件：docs/07-commercial-product.md

# 商业产品面：卖交付能力，不卖无边界的PASS

## 套餐按执行深度与服务范围

基础验证：接口清单/范围报告/冒烟/已批准回归；迁移保证：加原生差分、语义pack和盲变异；高保证：加适用formal obligations与Ethen独立审计。
正式名称带profile ID、业务路线和支持矩阵。不同价格只影响可承诺的服务范围/资源/审计服务，不降低同一profile的安全门槛。
不预设价格，不声称任何级别已有ISO/监管认可。工程attestation与法定/认可第三方认证分开。

## 用户可见交付物

接口文档与可执行contract；需求→测试→证据追踪；冒烟与完整回归报告；缺陷最小反例；source-target行为差异；形式化命题/假设与实际校验状态；Ethen发现和review身份；绑定artifact的保证声明；验收/回滚运行手册。
所有报告能导出机器JSON与人类HTML/Markdown。不能只给“98分”。

## 工作台页面

Project onboarding：repo授权、source/target选择、敏感数据分级、support matrix、估算与批准。
Contract review：declared/observed/inferred冲突、已发现接口、盲点、责任人审批和excluded理由。
Coverage：分母来源、计划/执行/断言/通过、关键缺口；点击到case和原始trace。
Run：真实stage进度、机器wall-clock、当前费用/保留预算、取消与阻塞原因。
Ethen：独立访问入口、隐藏challenge管理、proof命题diff、利益冲突和签署状态。
Attestation：范围/版本/产物摘要/validity/revocation/current status；不能将过期PDF截图当有效证明。

## 成本和增长

按变更范围缓存已验证rule/plan，缓存键包含语义模型与前置条件；不同租户不共享原始源码/数据。
质量收益用原始基线+固定holdout+真实escaped defects追踪；不可拿同一项目的百万随机样本宣称百万项目正确。
对成熟route扩展语言/DB版本；新adapter先experimental→native-tested→holdout-qualified→production-supported。未支持的feature显式拒绝或范围隔离。

## Acceptance不是技术gate的同义词

Customer acceptance由授权客户代表对原scope和业务验收结果确认，审计审查独立性，K8按policy签署。三者可有不同身份；合同审批不能代替测试，测试也不能代替客户确认。
未付款不能修改已记录的技术事实；付费不能强制Ethen批准FAIL。商业状态与技术verdict独立。


---

## 文件：docs/08-reference-boundary.md

# 可执行参考内核：明确边界

`reference/`是一个离线、可测试、没有网络服务与生产签署权限的参考实现。
它用Python数据结构展示：可信配置与不可信report分离，签名与artifact摘要核验，基于义务集合的coverage，mandatory证据缺失阻断，Ethen签名身份/control domain分离，有限模型fencing与幂等。

签名采用Ed25519演示格式 `elmos-demo-envelope-v1`，签名覆盖固定规范化JSON字节。为避免跨语言数值规范化歧义，该格式拒绝float；小数用字符串。它不是DSSE实现，不是生产证书格式。
生产采用审定的in-toto statement与DSSE/Cosign/KMS集成，见schemas与signer skill；签署必须绑定artifact及policy/evidence root，并验证issuer/subject/audience/revocation。

参考内核可信假设：operator传入的policy/approval/trust store与clock是可信的；演示runner仍可能签署错误事实，故真实系统需要受控执行器、独立复跑、raw reports核验与外审。签名保证完整性/来源，不保证业务正确。

参考测试不证明下列事实：生产多租户DB RLS、网络隔离、外部effect exactly-once、完整API功能、所有语言转换、Spring transaction、真正Lean theorem、Ethen真实身份或客户验收。
示例fixtures使用合成数据和临时密钥，只验证kernel约束，不得进入正式信任根。


---

## 文件：docs/09-acceptance-and-delivery.md

# 从Skill完成到产品验收

## 完成定义

每个skill必须交付：实际集成代码；versioned契约；数据库变更（如有）；unit+negative+native integration；observability；权限；rollback；验收ID→原始运行证据映射。
只有文档/接口桩/mock可标 SPECIFIED/REFERENCE_TESTED，不是 IMPLEMENTED/NATIVE_VERIFIED。

## 四层验收

1. Package validation：结构、依赖DAG、schema/examples、文档必需文件。
2. Reference validation：本包小型内核、负例、demo实测。
3. Product integration：真实Elmos代码、实际工作流/DB/原生runner/API与UI。
4. Customer route acceptance：客户scope、隐藏集、真实Ethen/K8、上线回滚与有效期。

本次交付仅执行validation报告中明确列出的1/2；3/4不假冒完成。

## 必需系统反例

提交空suite/删接口/放宽精度；重放旧run证据；修改同commit产物；跨tenant引用证据；假审计身份；Builder用另一个key冒充外部；proof statement收窄前提；critical case跳过；重试掩盖flake；暂停预算却PASS；unknown external effect盲重试；取消后的旧workercommit；旧证书密钥被撤销仍显示有效。

## 交付清单

每batch报已有功能复用清单、代码diff摘要、所有测试命令/退出码、NOT_RUN理由、dependency/support matrix变化、风险/成本、可恢复checkpoint。没有实测wall-clock基线时报告unknown，不编造ETA。


---

## 文件：docs/10-sources-and-design-decisions.md

# 来源与设计决策

核验日期：2026-09-09。下列来源支持工具能力/接口语义；本包架构、门槛与产品设计是本次建议，不代表这些项目替Elmos背书。

| ID | 一手来源 | 用途与边界 |
|---|---|---|
| S01 | https://agentskills.io/specification | SKILL.md frontmatter、渐进加载、资源组织 |
| S02 | https://developers.openai.com/codex/skills | 官方重定向至ChatGPT Learn，Codex .agents/skills本地发现 |
| S03 | https://spec.openapis.org/oas/v3.1.1.html | 本包选择3.1.1作为参考HTTP合同互操作基线 |
| S04 | https://spec.openapis.org/oas/v3.2.0.html | 已有3.2，不假称3.1最新；迁移需adapter兼容测试 |
| S05 | https://schemathesis.readthedocs.io/ | OpenAPI/GraphQL性质及stateful测试，非完整业务Oracle |
| S06 | https://lean-lang.org/doc/reference/latest/ValidatingProofs/ | 公理检查、trusted challenge、comparator、外部checker与残余信任 |
| S07 | https://github.com/leanprover/lean4/releases | 当前可见v4.33.1，非宣称本机已运行 |
| S08 | https://sqlglot.com/ | 解析/transpile适配器候选，非语义认证器 |
| S09 | https://github.com/sqlancer/sqlancer | DBMS测试oracle启发；不能单独认证跨dialect转换 |
| S10 | https://pitest.org/quickstart/basic_concepts/ | mutation、equivalent mutants；须正确处理分母 |
| S11 | https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html | proxy/self-invocation风险需真实框架测试 |
| S12 | https://docs.sigstore.dev/cosign/verifying/attestation/ | in-toto/DSSE签署验证；签名不等于正确性 |
| S13 | https://slsa.dev/spec/v1.2/build-provenance | artifact digest/provenance字段设计；不宣称SLSA认证 |
| S14 | https://docs.tlapl.us/using%3Atlc%3Astart | 有限模型边界；不把bounded通过当无限证明 |

## 继承的用户资料

Library中的 `ELMOS_ROUTER_SKILL_PACKAGE.md`：Elmos持有语义路由、ModelExecutionPlan、权限与结果commit；网关可替换。
`SKILL_INDEX(20260828-095237).md`与`SKILL_INDEX(20260828-104455).md`：独立K8、scope compiler、holdout、版本绑定、原16 routes约定。
只复用这些可见设计约定；没有读取实际Elmos源代码，不声称这些能力已实现。

## ADR摘要

A01：横切assurance扩展，不增业务线/重写Harness。
A02：冻结scope+oracle+obligations，拒绝自动缩分母。
A03：规范正确性与历史兼容性分开。
A04：Ethen是角色/身份/信任域，不是模型昵称即外部认证。
A05：Lean承担可表达的critical claims，必须绑定实际artifact。
A06：物理效应at-least-once+幂等/对账；不泛化exactly-once。
A07：参考内核不能生产签发；正式签署复用K8/KMS。
A08：最新文档不等于已验证依赖；生产锁定精确工具链。


---

## 文件：docs/11-delivery-boundaries.md

# Delivery boundaries and acceptance ownership

本包交付完整实现契约与参考内核，不代表34个生产模块都已在Elmos仓库实现。本文与VALIDATION_REPORT共同构成完成边界。

**已实现并可本地测试**：finite Assertion IR、schema/身份/摘要/签名证据核验、门禁参考逻辑、覆盖/冒烟集合选择、类型化比较、预算/租约本地模型、SQLite反例、包校验与显式无覆盖安装器。

**需要接入真实仓库实现**：接口静态/动态采集器、真实编译和测试adapter、数据库差分、Spring行为记录器、代码跨语言前后运行、客户测试数据、生产状态持久化、真实API/UI/IdP/KMS、Ethen实际身份签署、全量供应链锁定与部署演练。

**候选但未执行**：PostgreSQL DDL、Lean示例、TLC模型、四条native Golden Routes。Python里带有proof_checks字段的合成fixture只测试门禁消费该报告的逻辑，绝非Lean证明；Ed25519临时签名只测试数据真实性机制，绝非真实Ethen授权。

**不承诺**：任意项目/任意语言组合全功能穷举、99.99%真实业务正确率、付费保过、零风险上线、ISO/监管认可证书、外部副作用无条件exactly-once。

安装器信任正在操作本地工作区的用户；使用互斥lock防止并发安装，拒绝已存在目录和符号链接，但不充当对具备同一操作系统账号写权限的恶意进程的沙箱。迁移脚本必须由管理员在隔离数据库验证，再接入正式迁移系统，不能直接通过Agent对生产库执行。


---

## 文件：domain-packs/project-generation/DOMAIN.md

# 多语言项目生成 Domain Pack

## 保证目标
Approved requirements → contract/state/effect conformance

## 首个商业纵向切片
批准的订单需求 → 一个真实后端语言+真实数据库+接口回归；再加入第二语言差分

## 核心语义
先Domain/State/Interface/Acceptance，后实现。测试从approved normative spec生成，不从候选代码抽取expected。
多语言版本可以互相差分，但还必须分别满足同一规范，不能互相作唯一Oracle。关键内部能力无需变成公开API，可用受控test probe/组件接口。
需求模糊产生SpecQuestion/显式设计假设；关键规则未经责任人审批禁止发布。

## 必需验收场景
- **GEN-001** — 正常创建订单：请求/响应schema、DB行与业务字段一致，事件恰按声明语义产生。
- **GEN-002** — 跨tenant读取/修改：拒绝且DB/MQ无未授权副作用。
- **GEN-003** — 相同幂等键重复/并发创建：同一业务结果，无重复扣款/库存效果。
- **GEN-004** — 事务第二步故障：要求的原子状态不部分提交。
- **GEN-005** — 需求删实现但接口仍返回200：独立需求测试必须失败。
- **GEN-006** — UI重试/取消流程：UI/HTTP/最终数据状态一致。

## 形式化义务候选
金额/库存状态不变量；去重状态机的限定模型；纯领域规则保持。

## 不支持/阻塞
未批准业务假设；没有可执行规范且没有可观测结果的功能。

## 成熟度
本包仅SPECIFIED，原生适配与客户认证NOT_RUN。每种确切source/target/feature/environment组合独立晋级；不能用一个语言/DB测试结果覆盖整个矩阵。


---

## 文件：domain-packs/repository-conversion/DOMAIN.md

# 仓库级跨语言转换 Domain Pack

## 保证目标
Module refinement + boundary observations + repo-level workflows

## 首个商业纵向切片
Java→C#等一个明确语言对，先纯领域模块和HTTP/DB边界，再扩展并发/反射

## 核心语义
采用Semantic IR中的类型/数值/NULL/异常/ownership/effect/concurrency能力块，而非一次写全世界统一语言。
每个language pair单独声明支持特性和runtime/stdlib/serialization版本；泛型、反射、FFI、native库、动态加载必须显式适配或unsupported。
小模块证明不能自动组合成全库证明；需要依赖假设、模块边界契约、组合义务与实际lowering/codegen绑定。
跨语言通信比较规范化协议值，语言内部的raw memory/运行时异常文本不可作为默认业务oracle。
关键纯函数可用Lean证明IR变换，真实runtime语义仍需native golden tests。

## 必需验收场景
- **REP-001** — 整数min/max/overflow与除法：按照源目标精确语义判定，必要时引入compat shim。
- **REP-002** — Unicode代理对/组合字符：按声明length/encoding语义比较，不能默认所有string等价。
- **REP-003** — 异常/资源释放/取消：观察异常类型映射、finally/dispose和残余effect。
- **REP-004** — equals/hash集合与序列化：不因排序normalizer掩盖业务依赖顺序。
- **REP-005** — 并发更新/锁/异步重试：有限调度和原生stress共同发现状态/幂等错误。
- **REP-006** — 模块正确但repo装配错误：原生build、contract、端到端workflow失败必须阻断。

## 形式化义务候选
纯子语言的语义保持；rule preconditions与组合义务；类型/数值compat shim性质。

## 不支持/阻塞
未验证的反射/FFI/动态加载；未知第三方库语义；未固定并发和平台假设。

## 成熟度
本包仅SPECIFIED，原生适配与客户认证NOT_RUN。每种确切source/target/feature/environment组合独立晋级；不能用一个语言/DB测试结果覆盖整个矩阵。


---

## 文件：domain-packs/spring-modernization/DOMAIN.md

# Spring 老项目现代化 Domain Pack

## 保证目标
Approved compatibility contract + old/new native runtime observations

## 首个商业纵向切片
一个可原生启动的Struts/Servlet样例 → 指定并批准的Spring Boot目标版本；旧新隔离运行

## 核心语义
旧系统黄金行为包含HTTP、headers、cookie/session、DB delta、event/cache、安全判断、异常与视图；也采集批处理和scheduler。
用真实容器/框架/DB验证事务代理、事务边界、调用链与异常；仅MockMvc或mock repository不能覆盖所有真实效应。
目标Boot/Framework/JDK/Jakarta/Servlet版本必须兼容矩阵锁定，不把“升级Boot 4”视为逐行注解替换。
既有漏洞/不合规行为形成approved behavior change，设计修复与单独测试；其他兼容性继续保留。
旧系统无法运行：只能提供scoped静态/合同保证，不自动给行为等价E4/E5。

## 必需验收场景
- **SPR-001** — 未登录请求+returnUrl：status/Location/cookie/session及安全决策一致或有批准变化。
- **SPR-002** — invalid binding/validation：业务逻辑/DB写入不得先于校验。
- **SPR-003** — 事务中途异常/checked exception/self-invocation：验证实际rollback/propagation，不只扫描注解。
- **SPR-004** — filter/interceptor/shiro/security顺序：逐条拒绝/允许路径和副作用核对。
- **SPR-005** — multipart/i18n/JSP/forward/redirect：文件/编码/视图/headers/cookies语义正确。
- **SPR-006** — Quartz/定时任务重复触发及旧任务残留：副作用幂等和调度交接符合合同。

## 形式化义务候选
请求状态/权限映射DSL规则；已建模validation-before-effect规则；小型配置规则的前置条件。

## 不支持/阻塞
无法取得的旧runtime证据；未建模动态代理/插件行为；无许可闭源依赖。

## 成熟度
本包仅SPECIFIED，原生适配与客户认证NOT_RUN。每种确切source/target/feature/environment组合独立晋级；不能用一个语言/DB测试结果覆盖整个矩阵。


---

## 文件：domain-packs/sql-conversion/DOMAIN.md

# SQL / SQL routine 转换 Domain Pack

## 保证目标
Typed result bag + ordered result when specified + transaction/effect trace

## 首个商业纵向切片
冻结源/目标真实DB版本的一对SQL SELECT子集；存储过程/事务另立route范围

## 核心语义
AST不是完整语义。需要catalog、精确DB版本、SQL modes、timezone、collation、schema约束、UDF与transaction设置。
Comparator明确ordered/bag/set；默认bag，只有规范要求set时才去重。日期/小数/二进制保持类型；NaN/signed-zero按声明处理。
无序LIMIT、随机/时间函数、浮点聚合使用受控时钟/seed或性质与允许结果集合；无法界定则INCONCLUSIVE。
SQLancer用于启发DB oracle/发现引擎bug，不是跨dialect转换认证器。SQLGlot unsupported必须raise或报告，不默默best effort签PASS。
DDL/data migration另检查row count、约束、索引、默认值、权限、触发器/identity与回滚策略；query等价不涵盖迁移正确性。

## 必需验收场景
- **SQL-001** — 空表/重复行/全NULL/混合NULL：比较bag multiplicity和typed NULL，不转空字符串。
- **SQL-002** — 外层x=NULL、内层非NULL非空的NOT IN改写：检测与NOT EXISTS不等价。
- **SQL-003** — DECIMAL边界/舍入/负数/overflow：精确比较或contract批准的舍入，不用通用epsilon。
- **SQL-004** — LEFT JOIN谓词移位：捕获WHERE与ON选择语义差异。
- **SQL-005** — ORDER BY含并列值与分页：要求批准的tie-breaker或声明非确定性，不随意排序掩盖。
- **SQL-006** — routine失败、savepoint、sequence副作用：按真实引擎语义观察；不假设sequence回滚。

## 形式化义务候选
三值逻辑/关系bag受限DSL规则；rewrite充分前提；decimal/类型转换边界。

## 不支持/阻塞
未建模vendor extension/UDF；未验证的procedure异常语义；来源许可/环境缺失的真实DB。

## 成熟度
本包仅SPECIFIED，原生适配与客户认证NOT_RUN。每种确切source/target/feature/environment组合独立晋级；不能用一个语言/DB测试结果覆盖整个矩阵。


---

## 文件：contracts/ASSERTION_AND_NATIVE_RUNNER_CONTRACT.md

# Executable oracle boundary

InterfaceContract中的preconditions/outcomes/assertions描述用于审阅，不得直接作为任意代码eval。wire_schema_bindings绑定实际request/response/error schema的内容摘要，HTTP适配器须补全method/path、serialization/content-type、授权矩阵；其它协议通过明确schema_format适配。

每个TestCase同时绑定runner_plan_digest和assertion_program_digest。批准后的case_manifest不能由agent临时改动。NativeRunnerPlan只选择注册adapter+action，没有raw shell/URL/callback/环境变量值字段；服务器从审批过的命令模板解析参数并验证项目路径/挂载/输出/网络/secret scope。payload引用的VerifiedSecurityContext/lease需要broker真正验签核权，不能仅相信字符串存在。

AssertionProgram提供有限的JSON Pointer及equals/not_equals/exists/not_exists/count_equals/decimal_equals。equals严格区分true与1、null与缺失；count_equals只计数组条目；decimal只比较合法十进制字符串精确数值，不接受NaN/Infinity/float epsilon，精度/scale有业务含义时另加规则。未知路径用于equals时为UNKNOWN，不以默认空串/0蒙混；exists/not_exists可显式断言不存在。不存在正则执行、脚本、外部URL或SQL执行入口。

参考interpreter不证明approved_oracle_digest真的获批，不证明observation真实；生产runner必须从服务端批准的frozen plan读取程序并在授权沙箱执行实际项目，观测trace/DB delta/transaction/outbox，再由独立证据服务记录并验签。跨进程观察race/快照一致性需native实现。仅断言HTTP201不充分；实际回归同时断言金额、事务效果、事件次数、幂等与租户隔离。

本次examples都是SYNTHETIC；runner没有真实image/lease，必须NOT_RUN。schema合格不代表可执行或有权执行。未支持的API/协议/assertion op→UNSUPPORTED/INCONCLUSIVE，禁止自动忽略。


---

## 文件：validation/VALIDATION_REPORT.md

# 本次交付验证报告

**日期：2026-09-09 · 状态：REFERENCE_AND_STRUCTURE_CHECKED_NOT_PRODUCT_CERTIFIED**

本报告只确认当前skills package的文件结构和列明参考实现，不是Elmos或客户项目的认证结论。

## 实际执行

| 检查 | 结果 | 范围 |
|---|---|---|
| Python参考测试 | **138 passed；0 failures/errors** | 证据/门禁/身份/覆盖/断言/SQL反例/租约/预算本地模型 |
| 结构与依赖验证 | PASS | 34 skills，15 schemas，15 examples，14 API operations，DAG及本地引用 |
| 实施验收定义 | 102 + 24 | 102模块场景、24原生业务场景；定义已检查，原生验收未执行 |
| 合成演示 | PASS | 有效合成证据仅获DEMO verdict；篡改/缺审计/未知mutation/失败回归均阻断 |
| 安装器 | PASS | Codex与Claude各一次真实临时目录安装；dry-run不写入；重复安装拒绝；不改AGENTS/CLAUDE |
| Python语法检查 | PASS | reference/scripts/tests |
| Lean检查入口 | **NOT_RUN，exit2** | 本机没有Lean，未下载工具链 |

测试命令：`python -m pytest -q --junitxml=validation/reference-tests.xml`。Python 3.13.5；SQLite 3.46.1。JUnit及原始命令日志随包提供。

## 未执行与生产边界

四条原生业务Golden Routes、PostgreSQL迁移、完整OpenAPI标准验证器、Lean kernel及独立checker、TLC模型、真实Elmos代码集成、真实Ethen审计/签署、客户holdout、部署与回滚均**NOT_RUN**。Ethen真实身份UNCONFIGURED；生产K8签署DISABLED。

本次OpenAPI检查验证本地引用、operation唯一性、路径参数、认证/写入幂等及并发控制字段；没有谎称运行完整标准validator或HTTP server。Python临时Ed25519身份不是Ethen本人/机构，合成proof_checks不是Lean证明。SQLite反例不是Oracle/PostgreSQL跨数据库认证。DDL和TLA/Lean示例不计入138项Python验证之外的原生成绩。

## 完整性与复现

运行`python scripts/validate_package.py --verify-lock`检查包内SHA256完整性和inventory。清单不包括清单自身及运行缓存，包含源文件和本报告；它是文件一致性检查，不提供独立审计身份背书。

参考依赖的本次精确版本记录在requirements-reference.txt；实际客户runtime/compiler/database/image/security配置必须另行批准并锁定。代码修改、依赖变化或原生环境接入后须重新运行对应验证，不沿用本报告冒充新版本结果。

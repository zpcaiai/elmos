# ADR-0059: 共享 Coding Agent 模型目录

- 状态：已接受（目录声明层），底层模型接入保持 `NOT_CONFIGURED`
- 日期：2026-07-28

## 背景

三条现有业务线都在验证后的非确定性步骤上留有 Coding Agent 接口：

- `engines/project-synthesis-engine`（一键生成项目）在规格澄清与生成后的收尾步骤上可接入模型；
- Spring 现代化（`rewrite-spring` 底座）声明 "OpenRewrite 承担确定性转换；Coding Agent 只处理验证后的长尾问题"；
- 跨语言迁移 Batch 5（`core-language-lowering`）在静态验证后的惯用化步骤上同样保留 Coding Agent 接口。

此前三者若各自决定"用哪些模型"，会出现同一模型在不同业务线里拼写不一致、重复声明、或私自绕过 `EnterpriseModels.ModelPolicy` 治理的风险。

## 决策

新增单一权威登记表 `engines/ai-platform-engine/policies/model-catalog-v1.json`，由 `schemas/ai-platform/model-catalog-v1.schema.json` 定义结构，`scripts/operations/validate_model_catalog.py` 做失败关闭的一致性校验（`make model-catalog-check`，已并入 `business-line-contracts`）。

目录登记了运行时可选的模型名单（GPT-5.6 Sol/Terra、Claude Fable 5、Claude Opus 5、Gemini 3.6/3.5 Flash、Grok 4.5/Build 0.1、Qwen3.8-Max-Preview、GLM-5.2、DeepSeek V4-Pro/Flash、豆包 Seed2.1/Seed Code），每条只包含 `vendor`、`modelFamily`、建议角色（`suggestedRole`）与 `status`。三条业务线的 README 均指向同一份文件，不再各自维护模型名单。

## 边界（不做什么）

- 目录**不是**执行层：它不持有 API Key、不发起任何网络调用，也不声明这些模型确实可用或已通过评测。
- 每条模型的 `status` 被 Schema 与校验脚本硬性锁定为 `NOT_CONFIGURED`；任何门禁、渲染层或文档都不得把它折算成 `AVAILABLE`。
- 真正"可调用"需要走既有治理链路：由 `EnterpriseModels.ModelPolicy` 批准 Provider 类型与区域 → 生成 `ModelEndpoint`（`approved=true, healthy=true`）→ 经 `ModelRoutingDecision` 放行 → 通过 `engines/ai-platform-engine/policies/adapters-v1.json` 中已配置的 `INFERENCE_GATEWAY` 或 `CLOUD_AI` Adapter 转发。目录里的 `routesThroughAdapter` 字段只是声明"未来会走这两个 Adapter"，不代表 Adapter 已配置——`adapters-v1.json` 中它们本身也仍是 `NOT_CONFIGURED`。
- `suggestedRole` 是登记时给操作员的参考分类（规格澄清 / 长尾修复 / 惯用化复核 / 快速迭代草稿），不是运行时强制路由规则；实际选型仍由各业务线在真实证据下自行决定。
- 本 ADR 不批准、不暗示这些模型名称对应的厂商已与 ELMOS 达成任何商业或技术集成关系。

## 后续

若要让某个模型从 `NOT_CONFIGURED` 变为可用，需要：提交真实凭据与出网审批 → 在 `ModelPolicy` 中显式放行对应 `ModelProviderType` 与区域 → 产生 `ModelEndpoint` 健康检查证据 → 更新本目录状态并重跑 `make model-catalog-check`。跳过任一步都会被现有失败关闭门禁拒绝。

## 追加（2026-07-28）：三条业务线的真实接入情况

本 ADR 最初的"背景"一节把三条业务线并列描述为"都留有 Coding Agent 接口"，实际动手接入后发现这个说法不够精确，记录如下，避免误导后续读者：

- **Spring 现代化**：`apps/java-engine-worker` 新增 `SpringUpgradeCodingAgentPort` / `DisabledSpringUpgradeCodingAgentPort` / `EnterpriseGovernanceSpringUpgradeCodingAgentPort`，由 `SpringUpgradeConfiguration` 以 `elmos.worker.spring-upgrade.coding-agent-enabled`（默认 `false`）门控。该端口只回答"目录里 `LONG_TAIL_CODE_FIX` 角色的候选模型现在哪些真的能被 provision 出 `approved=true` 的 `ModelEndpoint`"，**没有**改动 `LocalSpringUpgradeExecutionPort.execute()` 里唯一有真实端到端本地执行证据的 `Stage.DETERMINISTIC_REPAIR` 重试逻辑——那段代码目前仍然只是重跑一次同一条 OpenRewrite Recipe，没有调用任何模型。把这个端口真正接进那段重试失败后的分支，是刻意留到下一次改动，因为那需要能编译测试着改，不能盲改一段已经有 `PASSED_LOCAL` 证据的代码路径。
- **跨语言迁移 Batch 5**：`modules/lowering` 新增结构完全相同的 `LoweringCodingAgentPort` / `DisabledLoweringCodingAgentPort` / `EnterpriseGovernanceLoweringCodingAgentPort`，消费 `MethodBodyLoweringService` 早已存在、但此前无人调用的 `LoweringModels.AgentPacket`（"Agent 升级包"）。同样地，没有修改 `MethodBodyLoweringService` 本身；确认过目前除测试外没有任何生产代码构造这个 Service，所以新增端口的风险比 Spring 那条更低。
- **一键生成项目（project-synthesis-engine）**：调研后确认这条业务线**没有、也不应该有**同类接入点。`engines/project-synthesis-engine` 是可独立 `pip install` 的纯 Python 包，`src/elmos_project_synthesis/` 下每个 emitter 都是确定性模板；"Drafting does not generate code; generation requires a reviewed approval artifact" 是刻意的架构边界，不是尚未实现的缺口。这条业务线真正的"Coding Agent"是仓库外、生成规格之前运行 `$elmos-project-synthesis` Skill 的那个会话（人或 Agent），它可以直接读 `engines/ai-platform-engine/policies/model-catalog-v1.json`，不需要、也不应该在这个可独立分发的 Python 包里再造一个 provisioning 类——那样反而会误导这个包的实际架构。详见 `engines/project-synthesis-engine/README.md` 的对应说明。

两个 Java 端口都配有单元测试（凭据缺失 fail-closed、无专用探针的模型 fail-closed、假凭据+假探针端到端跑通），且 `scripts/operations/validate_model_catalog.py` 新增了对 `SpringUpgradeConfiguration.java` 候选模型列表的交叉校验，防止候选名单里出现目录中不存在、或角色标签对不上的模型 id。

## 追加（2026-07-28，第二次）：`DETERMINISTIC_REPAIR` 二次失败证据 + 剩余厂商探针

在确认 Spring / Lowering 两个端口本身可编译可测试之后（`mvn -pl apps/java-engine-worker,modules/lowering -am test`，40 个测试全绿），继续做了用户要求的两件事：

1. **`LocalSpringUpgradeExecutionPort.execute()` 真正接入 `SpringUpgradeCodingAgentPort`**——但刻意保持一个明确边界：这里**没有**新增"模型生成补丁并自动应用"的能力，因为整个代码库里目前不存在这种能力，凭空造一个会是伪造而不是描述。真正改动的是 `Stage.DETERMINISTIC_REPAIR` 重试后的第二次 `runMaven` 调用：原来直接用会抛异常的 `runMaven(...)`，现在改成 `runMavenOutcome(...)` 拿到退出码；仍然失败时，先调用新增的纯函数 `LocalSpringUpgradeExecutionPort.codingAgentEvidencePayload(port, organizationId, runId)` 把"此刻哪些 `LONG_TAIL_CODE_FIX` 候选模型真的能被 provision 出 `approved=true`"写进 `evidence/coding-agent-candidates.json`，然后照旧抛出与今天完全相同的 `MAVEN_COMMAND_FAILED`。当 `codingAgentPort` 是默认的 `DisabledSpringUpgradeCodingAgentPort`（`elmos.worker.spring-upgrade.coding-agent-enabled` 默认 `false`）时，`configured()` 为 `false`，这个函数直接返回空、什么也不写——对唯一有 `PASSED_LOCAL` 端到端本地执行证据的这条路径零行为改动。新增的 `LocalSpringUpgradeExecutionPortCodingAgentEvidenceTest` 只测这个纯函数本身（不构造 `LocalSpringUpgradeExecutionPort`，因为它的构造函数需要磁盘上真实存在、版本号精确匹配的 JAVA_HOME 与 Maven 3.9.11 可执行文件，在普通单元测试环境里天然无法构造）。

2. **为剩余七个厂商写了真实探针**——`OpenAiModelHealthProbe`、`AnthropicModelHealthProbe`、`GoogleModelHealthProbe`、`XaiModelHealthProbe`、`QwenModelHealthProbe`、`ZhipuModelHealthProbe`、`DoubaoModelHealthProbe`，结构与 `DeepSeekModelHealthProbe` 完全一致：真实 `java.net.http.HttpClient` 调用各厂商 `/models` 端点、纯函数 `interpret(int statusCode)` 可无网络单测、包可见的可注入测试 `HttpClient` 构造函数、以及一个默认跳过、需要操作员导出对应 `ELMOS_MODEL_CREDENTIAL_*` 环境变量才会真正跑网络请求的 `@EnabledIfEnvironmentVariable` 测试。

   **重要限制**：除 DeepSeek 外，这七个探针目前都**没有**用真实凭据跑过真实流量——本项目里从未拿到过 OpenAI/Anthropic/Google/xAI/DashScope/Zhipu/Volcengine 的真实 Key。端点 URL、鉴权头、状态码映射都是按各厂商公开文档的 REST 惯例编写的，代码完整但未经现场验证；`ZhipuModelHealthProbe` 的 Javadoc 额外标注了它是本组里"端点最可能随 API 版本漂移"的一个。要让某个探针的可信度追平 DeepSeek，需要操作员导出该厂商的真实 Key 并本地跑一次对应的 `live*CredentialProvisionsARealApprovedEndpoint` 测试，把结果贴回来核对。

   `SpringUpgradeConfiguration` 的 `probesByModelId` 已经把 Spring 候选名单里除 DeepSeek 外的五个模型（`gpt-5.6-sol`、`claude-opus-5`、`grok-4.5`、`qwen3.8-max-preview`、`doubao-seed-code`）接上了各自的真实探针；`GoogleModelHealthProbe` 与 `ZhipuModelHealthProbe` 目前没有接入任何端口的默认候选名单——因为 `gemini-*`（`FAST_ITERATION`）与 `glm-5.2`（`IDIOMATIZATION_REVIEW`）都不属于 Spring 候选名单要求的 `LONG_TAIL_CODE_FIX` 角色，且 Lowering 端口目前也没有默认装配入口（见上文"跨语言迁移 Batch 5"一节）。这两个探针类本身是完整、可编译、有单测的，只是暂时没有一个默认候选名单去引用它们。

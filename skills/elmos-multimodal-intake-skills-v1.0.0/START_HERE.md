# START HERE：实施入口

## 1. 先做仓库发现，不要直接生成新系统

编码 Agent 首次进入 Elmos 仓库时，应先输出并保存：

1. 现有服务、模块、数据库、队列、对象存储、身份、权限和可观测栈；
2. 已有上传、任务、模型路由、RAG、代码索引和成本计量能力；
3. 可以复用、需要改造、需要新增的边界；
4. 数据迁移、兼容和回滚风险；
5. 依据 `templates/EXECPLAN.md` 创建的分阶段执行计划。

禁止在未阅读现有代码时另起一套重复平台。

## 2. 推荐首轮 Skill 组合

最小可运行闭环建议首先启用：

```text
01 elmos-multimodal-input-orchestrator
02 elmos-secure-resumable-upload
03 elmos-file-type-detection-and-validation
04 elmos-malware-quarantine-and-sandbox
12 elmos-unified-multimodal-content-ir
13 elmos-source-anchor-and-provenance
21 elmos-durable-processing-and-recovery
26 elmos-ingestion-api-and-sdk
29 elmos-codex-context-capacity-parity
30 elmos-context-budget-manager
39 elmos-model-capability-discovery
43 elmos-project-package-manifest
44 elmos-secure-zip-tar-extraction
45 elmos-archive-bomb-and-path-traversal-defense
```

然后按 `docs/IMPLEMENTATION_ROADMAP.md` 扩展。

## 3. 每次任务选择 Skill 的原则

- 只加载与当前工作流直接相关的 Skill，避免 50 个全部塞入活动上下文。
- 涉及跨阶段、数据库迁移、多个服务或预计机器执行超过一次普通编辑循环时，创建 ExecPlan。
- Skill 的 `references/contract.yaml` 是机器可读边界，`SKILL.md` 是 Agent 执行说明。
- 包级 `AGENTS.md`/`CLAUDE.md` 的安全与证据规则高于单个 Skill 的便利性。

## 4. 当前基线不是永久常量

```yaml
as_of: "2026-08-19"
parity_target: Codex
context_window_tokens: 1050000
max_output_tokens: 128000
source_of_truth: model capability registry
```

生产代码必须查询版本化能力注册表。任何 provider 返回未知或过期能力时，采取保守限制，不得假设无限上下文。

## 5. 交付顺序

```text
仓库发现
→ 领域/数据契约
→ 安全上传与不可变资产
→ 解析器沙箱与统一 IR
→ 来源锚点
→ 持久工作流
→ 长上下文预算与检索
→ 文件夹/归档与仓库地图
→ 工作台和下游 Agent
→ 全量功能/安全/性能/恢复验收
```

## 6. 每阶段完成报告

使用 `templates/ACCEPTANCE_REPORT.md`，至少记录：

- 实际修改文件和迁移；
- API/事件/状态机变化；
- 运行的命令和原始输出位置；
- 通过、失败、跳过的测试及理由；
- P50/P95/P99、峰值资源、机器 wall-clock 时间；
- 模型费用、计算/存储成本和重复计费检查；
- 来源覆盖率、完整性报告、安全发现；
- 回滚方式与剩余风险。

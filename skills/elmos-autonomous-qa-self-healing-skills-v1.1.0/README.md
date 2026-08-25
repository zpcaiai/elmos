# Elmos Autonomous QA & Self-Healing Verification Skills Package

版本：`1.1.0 — Project Deliverables Edition`

目标：让 Elmos 从需求文档、项目约束、用户要求、项目功能、源代码与运行环境中，自动生成完整测试体系，严格执行测试、定位缺陷并安全修复；同时把**可执行测试文件集本身作为项目的正式产出**，而不是只保留临时执行结果或测试报告。

> 本版本的强制原则：只要运行模式不是 `plan-only`，生成的测试源代码、测试配置、夹具、测试数据、Mock、视觉基线、性能脚本、重放脚本和 CI 配置都必须被物化、校验、登记并进入最终项目交付物。任何只存在于临时沙箱、Agent 上下文或执行容器中的测试，都不算完成。

## 1. 最终项目必须交付什么

每次项目生成、转换、升级或自动修复任务，默认产出以下三套可下载文件：

1. **Project-with-tests Bundle**：完整项目源代码，包含适配当前技术栈的原生测试目录、运行配置与 CI 入口。
2. **Tests-only Bundle**：仅包含测试源文件、测试配置、Fixture、Mock、测试数据、视觉/性能基线、运行器、README、Manifest 和重放命令。
3. **QA-evidence Bundle**：测试计划、需求追踪矩阵、执行结果、日志、Trace、截图、视频、HAR、覆盖率、性能报告、缺陷、补丁、回归证据和发布证书。

`repair` 与 `certify` 模式还可额外产出 `repair-patches` Bundle。即使测试失败或任务被阻塞，也必须生成标记为 `partial` 或 `failed` 的可下载产出，保留已经生成的测试文件与失败证据。

## 2. 端到端闭环

```text
需求/约束/用户要求/项目功能/代码/设计
                     ↓
            规范化 + 歧义/冲突检测
                     ↓
       需求—功能—代码—测试—证据追踪图
                     ↓
          风险建模 + 完整测试规划
                     ↓
      生成统一 Test DSL 与框架专用测试
                     ↓
  将测试物化到项目原生目录并登记文件 Manifest
                     ↓
        编译/静态检查/冒烟验证生成测试
                     ↓
          严格执行全部 Required 测试
                     ↓
       缺陷聚类 + 根因定位 + 隔离修复
                     ↓
    原失败测试 → 影响回归 → 全量回归
                     ↓
          质量门禁 + 报告 + 发布认证
                     ↓
完整项目包 + 测试文件包 + QA 证据包 + 校验和
```

## 3. “覆盖所有功能”的可审计定义

- 对规范化后的每一个 `REQ/CONSTRAINT/UXR/NFR/AC` 节点建立测试映射。
- P0/P1 节点必须达到 100% 可执行覆盖；P2 默认不低于 98%。
- 每个测试必须包含明确 Oracle，而不能只断言 HTTP 200、页面存在或无异常。
- 使用边界、状态模型、组合、属性、模糊、变异和差分测试扩展未枚举输入空间。
- 无法执行的 Required 项必须是 `BLOCKED` 并阻止认证，不能伪装成通过。
- 每个已生成测试用例都必须能追溯到一个或多个实际测试文件；每个测试文件也必须能反查需求和用例。

## 4. 测试文件作为一等项目产出

Elmos 支持三种输出模式：

- `embedded`：把测试文件写入项目技术栈的原生测试目录，例如 `src/test/java`、`tests/`、`*_test.go`、`Tests/`、`test/`、`integration_test/`。
- `sidecar`：不修改输入仓库，而是在不可变交付目录中输出包含应用副本与测试文件的项目产物。
- `both`：同时生成可应用到仓库的补丁/工作树和不可变交付包；这是默认模式。

所有测试文件均需满足：

- 有稳定 `artifact_id`、SHA-256、生成器版本、输入快照、需求引用和测试用例引用；
- 位于受控相对路径，不得逃逸交付根目录；
- 通过语法、构建或框架发现校验；
- 至少完成最小冒烟运行，不能运行时必须明确标记 `blocked`；
- 不得包含 `TODO` 占位测试、`assert true`、空断言、无界重试或为通过而硬编码的特例；
- 不得包含凭据、生产 Token、未脱敏个人数据或生产数据副本；
- 需求或代码变化后进行增量更新，旧版本进入 `superseded`，不得无审计静默删除。

完整目录与 Manifest 契约见 [`PROJECT_OUTPUT_CONTRACT.md`](PROJECT_OUTPUT_CONTRACT.md)。

## 5. 测试谱系

| 测试域 | 生成的项目文件示例 |
|---|---|
| 单元/组件/功能 | JUnit、pytest、xUnit、Go test、cargo test、Vitest/Jest、XCTest、Flutter test 等源文件 |
| API/契约 | OpenAPI/GraphQL/gRPC 契约用例、消费者契约、错误码和权限测试 |
| 数据库/迁移 | 事务、约束、隔离级别、升级/回滚、数据一致性测试与种子脚本 |
| 消息/工作流 | 重复、乱序、重试、死信、Saga、补偿与定时任务测试 |
| UI/E2E/视觉 | Playwright/Appium/原生 UI 测试、截图基线、响应式与错误态用例 |
| 可访问性/兼容性 | 键盘、焦点、语义、对比度、浏览器与设备矩阵配置 |
| 性能/压力 | k6/Gatling/JMeter 脚本，Load/Stress/Spike/Soak/Capacity 场景和阈值 |
| 安全/滥用 | SAST/DAST/依赖扫描配置、越权、多租户隔离、注入和业务滥用测试 |
| 韧性/混沌 | 故障注入、超时、断网、依赖失败、恢复与灾备验证脚本 |
| 高级测试 | 属性、模糊、变异、差分和隐藏回归测试文件 |

## 6. 严格执行与自动修复

Required 测试只允许：`PASSED`、`FAILED`、`BLOCKED`、`FLAKY_CONFIRMED`、`NOT_APPLICABLE`。`SKIPPED` 不是合法发布状态。

自动修复必须在隔离 Worktree/临时分支和沙箱中进行；按照“原失败测试 → 新增回归测试 → 影响回归 → 契约/安全/变异检查 → 全量 Required 回归”顺序验证。系统禁止通过删除测试、弱化断言、扩大容差、增加任意 `sleep`、绕过认证授权或修改质量门禁使结果变绿。

## 7. 包结构

```text
.
├── AGENTS.md
├── CLAUDE.md
├── ARCHITECTURE.md
├── PROJECT_OUTPUT_CONTRACT.md
├── API_SPEC.md
├── CLI_SPEC.md
├── IMPLEMENTATION_PLAN.md
├── QUALITY_GATES.yaml
├── MANIFEST.yaml
├── CHANGELOG.md
├── UPGRADE_FROM_V1.0.0.md
├── PACKAGE_VALIDATION_REPORT.md
├── skills/                  # 40 个技能
├── schemas/                 # 11 个核心 JSON Schema
├── workflows/               # QA 与项目产出工作流
├── policies/                # 执行、修复、证据、项目产出策略
├── mappings/                # 工具链与原生测试目录映射
├── prompts/                 # 生成、修复、验证和发布提示模板
├── templates/               # Manifest、README、交付摘要模板
├── reference/               # 数据库表与对象存储键参考
├── tools/                   # 产出校验与打包参考工具
└── examples/                # 示例输入与项目产出蓝图
```

## 8. 在 Codex / Claude Code 中使用

1. 将本目录放入 Elmos 仓库，例如 `.elmos/skills/autonomous-qa/`。
2. 编码代理首先读取 `AGENTS.md` 或 `CLAUDE.md`，再读取 `PROJECT_OUTPUT_CONTRACT.md`、`QUALITY_GATES.yaml` 与 `IMPLEMENTATION_PLAN.md`。
3. 按 Batch 00–39 实现；不能先做自动修复而跳过追踪图、文件物化、Manifest 和证据链。
4. 每个 Batch 必须交付代码、自动测试、Schema/API 更新、可观测性、恢复语义、文档和仓库内验收证据。
5. 使用 `python tools/validate_skill_package.py .` 校验 Skills Package；使用 `python tools/validate_project_output.py <deliverable-root>` 校验实际项目产出。

## 9. 运行模式

- `plan-only`：测试计划、覆盖矩阵与系统 wall-clock ETA；不要求生成测试源文件。
- `generate`：生成并物化全部测试文件，产出 Project-with-tests 与 Tests-only Bundle，但不执行完整测试。
- `verify`：物化并执行测试，产出三套 Bundle，不修改产品代码。
- `repair`：允许隔离修复，重新物化受影响测试与补丁，禁止直接写主分支。
- `certify`：全量门禁、签名 Manifest 与发布证书。
- `continuous`：PR 增量更新测试文件、夜间全量回归、周期性耐久和安全测试。

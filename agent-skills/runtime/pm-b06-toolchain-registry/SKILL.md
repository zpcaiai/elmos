---
name: pm-b06-toolchain-registry
description: "为每个支持语言和平台提供版本化、可复现、隔离的编译、运行、测试和诊断适配能力. Precision Migration B06 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 06：编译器、Runtime与工具链注册中心
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b06-toolchain-registry`.
- Immutable source identity: `batch-06-toolchain-registry` in `precision-migration-b01-44` (B06).
- Runtime adapter: `semantic-recovery-and-ir`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b06-toolchain-registry`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

为每个支持语言和平台提供版本化、可复现、隔离的编译、运行、测试和诊断适配能力。

## Position in the system

- Phase: `B 源码理解与可信执行底座`
- Included skills: `10`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 发现仓库与环境
2. 使用原生工具提取语义
3. 建立可复现工具链和沙箱
4. 执行最小验证任务
5. 持久化摘要、哈希和证据

## Shared gates

- 不执行未隔离的客户或AI代码
- 工具链版本与镜像必须锁定
- 未能解析的动态语义必须显式标记

## Dispatch rules

- 当任务涉及 **toolchain-manifest-detector** 时，调用 `../pm-b06-toolchain-manifest-detector/SKILL.md`。
- 当任务涉及 **compiler-version-resolver** 时，调用 `../pm-b06-compiler-version-resolver/SKILL.md`。
- 当任务涉及 **runtime-version-resolver** 时，调用 `../pm-b06-runtime-version-resolver/SKILL.md`。
- 当任务涉及 **package-manager-adapter** 时，调用 `../pm-b06-package-manager-adapter/SKILL.md`。
- 当任务涉及 **build-command-generator** 时，调用 `../pm-b06-build-command-generator/SKILL.md`。
- 当任务涉及 **test-runner-adapter** 时，调用 `../pm-b06-test-runner-adapter/SKILL.md`。
- 当任务涉及 **compiler-diagnostic-normalizer** 时，调用 `../pm-b06-compiler-diagnostic-normalizer/SKILL.md`。
- 当任务涉及 **runtime-environment-provisioner** 时，调用 `../pm-b06-runtime-environment-provisioner/SKILL.md`。
- 当任务涉及 **toolchain-reproducibility-certificate** 时，调用 `../pm-b06-toolchain-reproducibility-certificate/SKILL.md`。
- 当任务涉及 **platform-worker-router** 时，调用 `../pm-b06-platform-worker-router/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `toolchain-manifest-detector` | 从仓库和锁文件推断语言、版本、框架、构建系统、平台和工具链需求。 |
| `compiler-version-resolver` | 解析源与目标编译器版本，并处理兼容范围、废弃特性和交叉编译约束。 |
| `runtime-version-resolver` | 选择与项目和目标部署一致的 Runtime、解释器、虚拟机和系统库版本。 |
| `package-manager-adapter` | 统一 Maven、Gradle、NuGet、npm、pnpm、Cargo、pip、Go Modules 等包管理操作。 |
| `build-command-generator` | 根据仓库结构和工具链生成可复现的解析、构建、打包和产物定位命令。 |
| `test-runner-adapter` | 统一发现、选择、执行和解析不同语言及框架测试运行器。 |
| `compiler-diagnostic-normalizer` | 将编译、链接、类型、Lint 和构建诊断规范化为结构化问题。 |
| `runtime-environment-provisioner` | 按任务创建 Linux、Windows、macOS、浏览器、移动端或证明环境。 |
| `toolchain-reproducibility-certificate` | 记录镜像摘要、工具版本、依赖锁、环境摘要和命令，签发可复现证据。 |
| `platform-worker-router` | 将任务路由到 OCI、VM、macOS、设备、数据库、浏览器或 Proof Worker。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。

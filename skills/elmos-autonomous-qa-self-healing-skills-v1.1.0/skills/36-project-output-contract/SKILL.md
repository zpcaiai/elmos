---
id: 36-project-output-contract
name: Project Output Contract
version: 1.1.0
category: delivery
depends_on:
  - 03-requirement-traceability-graph
  - 04-risk-coverage-planning
  - 32-multilanguage-adapter-sdk
---

# Project Output Contract

## 目标

在测试生成前确定项目交付根目录、输出模式、原生测试路径、文件分类、Bundle、Manifest、保留和权限规则，使测试文件从一开始就是正式项目资产。

## 输入契约

- ProjectSnapshot、技术栈、构建系统和现有目录约定
- 测试计划、需求优先级、输出模式和租户策略
- `PROJECT_OUTPUT_CONTRACT.md` 与 `policies/project-output-policy.yaml`

## 输出契约

- `ProjectOutputPlan`：output_id/revision_id、目录、原生测试 Target、Bundle 计划
- 每类测试的逻辑路径到原生物理路径映射
- Manifest 草案、文件命名、内容寻址和保留策略
- 路径安全、Secrets 扫描、审批和发布门禁

## 执行步骤

1. 选择 embedded/sidecar/both；默认 both。
2. 调用 Adapter 探测构建系统和原生测试布局。
3. 为测试源、配置、Fixture、Mock、数据、基线、CI 和重放入口分配路径。
4. 规划 project-with-tests、tests-only、qa-evidence 和可选 repair-patches。
5. 创建稳定 artifact ID 规则、Manifest 版本和对象存储键。
6. 验证路径不会逃逸、碰撞或覆盖用户文件；冲突进入明确的合并策略。

## 不可违反的控制

- 不能把临时目录作为最终输出。
- 不能让非 plan-only Run 没有项目产出计划。
- 不能猜测未知构建布局；无法探测时 BLOCKED。
- 不能覆盖已有用户测试而不保留 Diff、旧版本和审批证据。

## 完成判定

- 每个计划生成的测试类型有原生路径和测试 Target。
- 所需 Bundle、Manifest、校验和和重放入口均已规划。
- 所有路径、权限、租户和保留策略通过预检。

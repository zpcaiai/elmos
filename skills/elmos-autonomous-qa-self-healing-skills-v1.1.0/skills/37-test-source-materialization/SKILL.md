---
id: 37-test-source-materialization
name: Test Source Materialization
version: 1.1.0
category: generation
depends_on:
  - 05-test-model-dsl
  - 06-functional-test-generation
  - 07-api-contract-testing
  - 08-data-database-testing
  - 09-message-workflow-testing
  - 10-ui-e2e-testing
  - 11-visual-responsive-testing
  - 12-accessibility-compatibility-testing
  - 13-performance-baseline-testing
  - 14-load-stress-spike-soak-testing
  - 15-security-abuse-testing
  - 16-resilience-chaos-recovery-testing
  - 27-mutation-property-fuzz-testing
  - 36-project-output-contract
---

# Test Source Materialization

## 目标

把 Test DSL 和各测试生成器结果转换成目标项目可直接运行的真实文件，并作为项目产出登记，不允许只返回代码片段或临时文件。

## 输入契约

- 已验证的 Test DSL、测试用例和 Oracle
- ProjectOutputPlan、Adapter、原生目录和构建配置
- 现有项目测试、格式规范、锁文件和 CI 约定

## 输出契约

- 测试源文件、配置、Fixture、Mock、合成/脱敏数据、视觉/性能基线
- 构建脚本/package scripts/测试 Target 的最小修改
- 测试发现、格式化、语法、构建和冒烟结果
- `OutputArtifact` 与 `TestArtifactSet` Manifest 条目
- 文件 Diff、需求/测试用例映射和重放命令

## 执行步骤

1. 使用 Adapter 选择原生测试路径和框架。
2. 在隔离 Worktree 或 Sidecar 项目中原子写入文件。
3. 生成或更新最小必要的构建/runner 配置。
4. 生成稳定 Fixture、Mock、数据和清理逻辑。
5. 运行 Formatter、Parser、Linter、测试发现、构建与最小冒烟。
6. 扫描 TODO、空断言、assert true、禁用标记、无界重试和 Secrets。
7. 逐文件计算 SHA-256，记录 artifact/test_case/requirement refs。
8. 与上个 revision 比较，标记新增、修改、过期和 superseded 文件。

## 不可违反的控制

- 禁止在无法编译或无法被发现时报告完成。
- 禁止静默覆盖用户现有测试。
- 禁止使用固定长 sleep、删除失败断言或制造仅适配当前实现的特例。
- 禁止将生产凭据、真实个人数据和生产数据库副本写入测试产出。
- 所有生成文件必须进入 Manifest；未登记文件不得进入 Bundle。

## 完成判定

- 每个 Required 测试用例至少映射到一个物化文件/配置。
- P0/P1 测试 Target 可构建并完成最小冒烟；无法执行者明确 BLOCKED。
- tests-only Bundle 所需文件完整，运行入口可在干净环境重建。

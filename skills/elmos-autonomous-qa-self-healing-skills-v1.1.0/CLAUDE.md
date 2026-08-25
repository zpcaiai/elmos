# Claude Code Project Instructions

本目录是 Elmos 自主测试、自动修复和项目产出系统 v1.1.0 的实现规范。

执行编码任务前，依次读取 `README.md`、`PROJECT_OUTPUT_CONTRACT.md`、`ARCHITECTURE.md`、`QUALITY_GATES.yaml`、`policies/project-output-policy.yaml`、`policies/auto-fix-policy.yaml` 和相关技能文件。

必须遵守：

1. 需求追踪覆盖是第一质量门禁。
2. 生成测试必须包含明确 Oracle，并物化为项目技术栈可直接运行的文件。
3. 非 `plan-only` 模式不得只输出报告；必须输出含测试完整项目包和 tests-only 包。
4. 测试文件、Fixture、Mock、数据、配置、基线、运行脚本和 CI 入口均需进入 Manifest。
5. 自动修复不得直接修改主分支或生产环境。
6. 修复后按“失败用例 → 新增回归 → 影响回归 → 全量回归”验证，并重新发布文件版本。
7. 测试变更不得降低断言强度、需求映射、变异得分或删除失败场景。
8. 认证、授权、支付、加密、数据迁移、删除和基础设施变更只生成建议，等待审批。
9. 失败运行也要发布 partial/failed 产出，不能丢失已生成测试文件。
10. 所有完成声明必须以仓库中的可运行测试、Manifest、校验和和 Bundle 为依据。

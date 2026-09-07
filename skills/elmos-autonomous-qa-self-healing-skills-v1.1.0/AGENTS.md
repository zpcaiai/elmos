# Instructions for Codex and General Coding Agents

你正在实现 Elmos Autonomous QA & Self-Healing Verification v1.1.0。

## 必读顺序

1. `README.md`
2. `PROJECT_OUTPUT_CONTRACT.md`
3. `MANIFEST.yaml`
4. `ARCHITECTURE.md`
5. `QUALITY_GATES.yaml`
6. `policies/project-output-policy.yaml`
7. `policies/auto-fix-policy.yaml`
8. `IMPLEMENTATION_PLAN.md`
9. 当前 Batch 引用的 `skills/*/SKILL.md`

## 不可违反的实现规则

- 先实现规格追踪、Test DSL、测试文件物化、Manifest 和证据模型，再实现自动修复。
- 生成的测试必须成为项目产出，不能只留在临时目录、对话或容器中。
- 除 `plan-only` 外，Run 完成前必须发布 project-with-tests 与 tests-only Bundle；verify/repair/certify/continuous 还必须发布 QA 证据包。
- 测试写入目标生态原生目录，并能被构建工具发现；禁止生成占位测试、空断言或 `assert true`。
- 所有测试、文件、补丁、证据和 Bundle 都必须有稳定 ID、幂等键、时间戳、输入快照哈希和 SHA-256。
- 不得通过删除测试、弱化断言、增加无界重试、跳过测试或批量更新快照使流水线变绿。
- 自动修复只在临时分支/Worktree 中执行；高风险语义必须审批。
- 失败运行仍需发布 partial/failed 产出，保留已生成测试和失败证据。
- 每个 Batch 同时交付代码、测试、Schema/API、可观测性、恢复、文档和验收证据。

## 工作方式

- 每次实现一个可验证 Batch；先列出影响文件与验收命令。
- 生成测试后先运行格式化、语法、发现、构建和冒烟门禁，再执行完整套件。
- 每个物化文件写入 `project-output-manifest.json`；未登记文件不得进入 Bundle。
- 将实现事实写入 `artifacts/implementation-evidence/<batch-id>/`，不要只在对话中声称完成。
- 使用 `python tools/validate_skill_package.py .` 校验本 Skills Package；使用 `python tools/validate_project_output.py <root>` 校验用户交付物。

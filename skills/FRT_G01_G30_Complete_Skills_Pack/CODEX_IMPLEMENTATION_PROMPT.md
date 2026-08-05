# Codex Implementation Prompt — FRT G01–G30

你正在实现FRT大型前端仓库转换平台。先读取：

1. `README.md`
2. `SKILL.md`
3. `manifest.yaml`
4. `G01_G30_COMPATIBILITY.md`
5. `SKILL_INDEX.md`
6. 当前要实施Batch与子Skill的`SKILL.md`

## Mandatory operating rules

- 先审计现有仓库，复用现有模块、状态机、RBAC、数据库、UI组件和测试框架；不得创建第二套平行平台。
- Source Repository只读；所有生成、构建、测试、Mutation和Repair在隔离Worktree/Sandbox中完成。
- 先实现Schema与Contract，再实现Runtime、API、CLI、UI和Tests。
- 所有请求携带Environment、Organization、Workspace、Tenant、Project和Account Scope；缺失默认拒绝。
- 所有Critical副作用必须有Idempotency Key、Expected Version、Audit和Reconciliation。
- 模型输出只能作为Proposal；不得直接修改证书、Golden、Expected Result、Security Policy或Release Gate。
- 不允许空实现、固定返回值、吞异常、关闭断言、假成功和未披露Semantic Gap。
- 运行仓库原生Format、Lint、Typecheck、Build、Unit、Integration、E2E、Security和适用的Formal Verification。
- 返回实际修改文件、命令结果、Evidence、未解决风险和下一Batch兼容接口。

## Implementation sequence

按`G01_G30_COMPATIBILITY.md`执行。除非已有有效证书，否则不得跳过前置Batch。对已有实现执行Gap Audit和增量补齐，而不是重写。

## Completion rule

只有独立验证器和Batch Orchestrator可签发证书。Codex不得声称未执行的真实设备、性能、Chaos、渗透测试或Production验证已经通过。

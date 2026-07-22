# Product Batch 27–34 / Migration Pack M29–M34 验证记录

验证日期：2026-07-22（Asia/Shanghai）

## 结论

- 仓库实现门禁：`PASS`
- 产品治理决策上限：`READY_FOR_HUMAN_DECISION`
- 迁移包准入决策上限：`READY_FOR_PACK_GATE`
- 外部客户仓库认证：`NOT_RUN`
- 生产变更、PR、切换和外部审批：`NOT_RUN`

产品批次与迁移包采用独立命名空间和独立裁决器。仓库内控制面不授予认证或生产批准；只有对应的 Batch 29–34 gate 脚本可裁决 pack readiness，且人工审批仍不可被软件替代。

## 聚合构建

执行 `make verify`，退出码为 0：

- Maven reactor：63 个项目全部 `BUILD SUCCESS`。
- Java：845 个测试，0 failures，0 errors，1 skipped。
- .NET：12/12 通过。
- Python：31/31 通过；Ruff 与 mypy 通过。
- Frontend Client Engine：34/34 通过。
- Web Console：TypeScript 检查及 Next.js 16.2.10 production build 通过。

唯一跳过项是 `FlywayMigrationTest`：当前机器没有 Docker 命令，测试以 `disabledWithoutDocker is true and Docker is not available` 跳过。V33–V41 已通过静态租户、RLS、append-only 和证据边界测试，但本次未宣称在真实 PostgreSQL/Testcontainers 中执行。

## 本次新增域的定向测试

- Product Batch 27–34 治理：10/10。
- Migration Pack M29–M34 准入：5/5。
- 两组控制面 Controller：2/2。
- 迁移静态契约：1/1。

## Skills 与资产

执行 `make batch27-34-skills`：

- 新增或导入 Skills：289 个，全部通过官方 quick validation。
- Runtime Skills：615 个有效 Skill 目录。
- Migration Pack Schemas：38 个。
- Migration Pack Templates：52 个。
- Flyway migrations：41 个。
- 外部认证证据：`NOT_RUN`。

执行 `make mature-product-skills`：

- Batch 29–45：17 个批次全部通过仓库内 bundle 校验。
- Skills：356 个。
- Schemas：82 个。
- 单元测试：77 个通过。

日志中预期出现的 `GATE FAIL` 属于负向语料：它们验证缺失证据、未知语义、空 holdout 或不完整代表性工作负载不能获得认证；对应测试均以 `OK` 结束。

## 证据边界

以下事项需要真实外部环境、客户资产或授权，因此保持 `NOT_RUN`，不得从本地测试推断完成：

- GitHub App 安装、短期 token 与客户仓库 snapshot。
- Rootless Docker 客户 workspace 与真实源/目标运行时。
- 独立 holdout/representative corpus 的客户级认证。
- 真实 PostgreSQL/Testcontainers 执行 V33–V41。
- PR 创建、合并、生产发布、切换、回滚演练与人工批准。


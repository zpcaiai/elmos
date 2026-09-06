# 与既有 Elmos 的增量集成

## 1. 基线与事实范围

本设计查阅了用户已保存的 `BATCH-03-code-reader-and-explanation.md`、
`BATCH-14-online-debug-and-learning.md` 及
`elmos-ai-capability-enhancement-skills-v4.1.0-PACKAGE_RELATIONSHIP.md`。
这些是设计与任务材料，不能证明当前生产仓库已经实现所有同名能力。
本轮没有读取或修改实时 Elmos Git 仓库，因此兼容性状态是 **design-aligned / repository-unverified**。

既有阅读、语义导航、代码解释、学习路径、DAP gateway、沙箱编排、工作台、学习copilot、
记录回放、分布式关联已存在设计所有权。本包扩展其交付与验收，不平行复制第二套系统。

## 2. 必须先产出的基线盘点

逐项记录 `existing / partial / missing / conflict`，每一项附实际路径、revision、测试和owner。
不得只凭任务文档或名称判断代码已经存在。盘点项目至少包括：

- 生成/转换作业完成事件；源码快照、Symbol/Type/Call/API/DB Graph、转换映射。
- 既有代码阅读器、UI框架、状态管理、API认证、工作流/任务编排、队列及对象存储。
- Authority、CapabilityLease、VerifiedSecurityContext、ResultInterception/Commit、fencing。
- 租户权限、每账号3个并发执行槽、计量、日志脱敏、审计及认证包的入口契约。

## 3. 与既有内核的边界

不新增K9，不改写K1–K8职责，不为了新增教学复制权限/任务/证据系统。
下面是语义依赖；具体K编号、API和事件版本以当前仓库实际契约为准。

| 边界 | 工作台提供 | 必须由宿主提供 |
|---|---|---|
| 语义/图谱 | 选区、教学视图、证据查询 | 不可变源码与解析/类型/调用事实 |
| 执行计划 | 运行目标、学习任务、资源需求 | 已授权的每步ExecutionPlan及模型路由 |
| 安全 | 操作所需能力、资源范围 | 环境绑定身份、Host-minted授权、调用租约 |
| 运行 | 适配器与生命周期请求 | 合格执行provider、generation/fencing、终止保障 |
| 证据 | 原始调试/预览/测试结果 | RAW→INTERCEPT→COMMIT之后才可发布事实 |
| 认证 | 可复核的场景/环境证据 | 独立认证平面与K8最终判定 |

根路由是本包可选的新入口；28个内部工作流不是28个新的全局Skill owner。
现有能力包的全球Skill数量或版本号，本包安装器一律不修改。

## 4. 版本、失效与恢复

`lw.v1` 是新增契约命名空间。采用适配层接入现有类型，禁止直接修改共享核心Schema。
外部事件附 `tenant/repository/snapshot/run/session/generation/sequence/schema_version`。
旧版本不兼容时创建新会话或适配转换；不得降低权限、放松schema或丢失原始证据恢复。

引用文件的实现位置在方案中都是建议位置。先查实际repo，再映射；
已有React/Vue前端、Java/TypeScript后端都可复用，不需要为本功能强制技术栈迁移。

## 5. 能力与认证分离

本包既不重新定义E0–E5，也不赋予自己E5/P05认证权。
本地样例通过不自动达到生产E3，部署资格报告也不等于全仓库行为等价证明。
独立认证消费固定revision的证据；认证接收后候选变更遵守既有冻结/重新入场规则。
公开预览前所有安全硬门禁必须真实执行，不能用waiver绕过。

## 6. 回滚

默认仅新增包和路由文件。发布API或数据库迁移必须在真实仓库里另做兼容变更。
停用时先禁止新session，再按deadline回收旧session，最后关闭UI入口；不能先删控制器留下执行实例。
参考安装器只撤回包文件，不触碰运行实例或数据库，因为本包从未替你部署这些资源。

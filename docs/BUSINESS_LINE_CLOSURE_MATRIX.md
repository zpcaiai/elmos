# ELMOS 业务线闭环矩阵

本矩阵用于区分两类状态：

- `REPOSITORY_CLOSED`：仓库内可以完成的实现、契约、测试、构建和保守门禁已经闭环。
- `EXTERNAL_GATE_REQUIRED`：必须依赖真实客户、生产等价环境、独立验证者或获授权的外部操作；在证据产生前保持 `NOT_RUN`，不得由本地测试替代。

## 业务线状态

| 业务线 | 用户入口与核心实现 | 仓库内闭环与验证 | 当前状态 | 尚需外部证据 |
| --- | --- | --- | --- | --- |
| 迁移与现代化 M1-M45 | Web Migration Studio、control-plane、语言与框架/数据/客户端/云迁移模块、各语言引擎 | 草稿创建/读取/删除形成浏览器内闭环；稳定错误契约；Java、.NET、Python、TypeScript 和 Web 构建测试纳入 `make verify` | `REPOSITORY_CLOSED` | 代表性客户仓库、目标平台运行、独立验证与正式认证保持 `NOT_RUN` |
| 多语言项目生成 B46-B95 | `/generation`、`/api/capabilities/generation`、project-synthesis engine、Batch 66-95 Skills | 能力选择、参数编辑、精确 CLI 生成与复制闭环；结构包、启动探针和生产就绪检查 | `REPOSITORY_CLOSED` | 非内置语言原生工具链、签名、设备/集群/云部署及生产交付保持 `NOT_RUN` |
| 工作区与 Private Runner | workspace-service、workspace manager、egress proxy、Compose 服务拓扑 | 工作区请求校验、策略拒绝、依赖故障统一为安全稳定响应；默认拒绝出口；Compose 和服务/端口唯一性审计 | `REPOSITORY_CLOSED` | 真实 rootless Runner 隔离、工作负载身份、远端证明、秘密租约与撤销演练保持 `NOT_RUN` |
| 验证、证据与认证 | java-engine-worker validation API、Batch 1-45 严格套件、补充套件、evidence contracts | 空值、防御性复制、有限且有序阈值校验；408/400/660/750/450/640 用例结构完整；权威门禁按缺失证据失败关闭 | `REPOSITORY_CLOSED` | 逐用例执行者/独立验证者、原始证据、签名请求和信任库保持 `NOT_RUN` |
| Skills 与能力目录 | `.agents/skills`、`agent-skills/runtime`、`/skills` | UI 动态展示实际可调用 Skill 数量；新增业务线审计、生成旅程、跨服务运维闭环 Skills；各批次不可变清单与接口校验通过 | `REPOSITORY_CLOSED` | Skill 静态通过不等于客户、生产、行业或监管认证；相关证据保持 `NOT_RUN` |
| Web 产品体验 | `/`、`/migration`、`/generation`、`/commercialization`、`/skills` 及三组 API | 响应式页面、表单状态、空/错/成功反馈、浏览器本地草稿、能力 API、TypeScript 与 Next.js 生产构建闭环 | `REPOSITORY_CLOSED` | 真实浏览器/设备矩阵、无障碍人工审查、客户可用性验收保持 `NOT_RUN` |
| 运维、部署与可观测性 | 18 个运行时服务、24 个 Compose 服务、健康检查、runtime operability validator | Web 到 control-plane 路由闭环；名称/端口唯一；36 个异常处理源经敏感错误泄漏扫描；本地 Compose 配置验证 | `REPOSITORY_CLOSED` | 生产部署、SLO、告警值班、备份恢复、跨区 DR 和故障演练保持 `NOT_RUN` |
| 产品商业化 B34-B56A 与 Convergence | commercialization UI/API、Product Skills、closure/convergence control plane | 产品闭环/收敛 Skills 的来源、摘要、接口和反伪造校验通过；本地 gate 对缺失设计伙伴和独立审查正确返回 `BLOCKED` | `REPOSITORY_CLOSED` | 至少两个独立设计伙伴、独立审查、客户验收、单位经济性、GA/生产批准保持 `NOT_RUN` |

## CI 业务线映射

CI 分别验证 Java reactor、.NET engine、Python engine、frontend-client engine、project-synthesis engine 和 Web console。所有依赖安装均使用锁文件；六条业务线中的任一条失败都会阻止 CI 成功。

## 失败关闭规则

以下情况均不得解释为成功：`UNKNOWN`、`INCONCLUSIVE`、`NOT_RUN`、缺失或过期证据、执行者与验证者相同、未授权的外部操作、未绑定精确产物摘要、局部/稀疏工作区被当作完整工作区，以及只通过静态检查却声称真实运行、生产就绪或认证。

权威认证与产品闭环 gate 当前仍应返回 `BLOCKED`，直到对应外部证据真实产生并经过独立核验。这是预期的安全行为，不是待用假数据修复的测试失败。

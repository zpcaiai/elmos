# ELMOS 业务线闭环矩阵

本文件是业务线状态的保守汇总，不是认证证书。机器可读清单、精确 Gate
输出和原始证据优先于本文；相互冲突时取更保守状态。

## 状态定义

- `REPOSITORY_CLOSED`：仓库内实现、契约、测试、构建和保守门禁在声明的
  有限范围内闭环。
- `LIMITED`：只有明确的版本、工具链、语义或环境子集有本地工程证据。
- `DECLARED`：已安装契约或 Handler，但没有可移植的本地执行收据。
- `NOT_RUN`：指定的真实环境、客户、Provider、设备或独立执行尚未发生。
- `NOT_CERTIFIED`：没有可接受的外部独立认证链。

当前总状态：精确支持矩阵内存在可用的本地工程能力；GA、通用生产就绪和
外部认证仍为 `EXTERNAL_GATE_REQUIRED / NOT_CERTIFIED`。本地测试、哈希、
Merkle 根、仓库内签名、合成客户名称或模拟环境不能提升外部证据状态。

## 权威事实快照

1. 跨语言权威库存为 210 条路线：90 条 `limited`、120 条 `research`、
   0 条 `certified`。210 条路线的本地、独立与外部执行均为 `NOT_RUN`。
   权威来源：`routes/inventory.json`。
2. Project Synthesis 只声明 8 个精确语言 Profile，全部为 `limited`；
   外部托管数据库/IdP、生产 Rootless、交付、恢复/DR、独立 UAT 和认证均为
   `NOT_RUN / NOT_CERTIFIED`。权威来源：
   `docs/project-synthesis/BUNDLED_EMITTER_SUPPORT.md`。
3. Frontend-to-MiniApp 22 个 Skill 有仓库 Handler，但可移植安装状态为
   `DECLARED`；官方工具、模拟器/真机旅程、外部证据和认证为
   `NOT_RUN / NOT_CERTIFIED`。权威来源：
   `docs/frontend-to-miniapp-skills/README.md`。
4. 所有曾提交到仓库的认证私钥自 2026-09-13 起视为泄露并撤销。旧签名只能
   证明某个仓库内私钥处理过文件，不能证明独立认证。详见
   `certification/KEY_REVOCATION_NOTICE.md`。
5. B38-B45 的 `Global Bank` DR 记录时长约 0.086 秒，所谓 `Deloitte`
   SOC 2/ISO/HIPAA 审查记录时长约 0.153 秒；两者均不足以构成真实客户演练或
   第三方审计证据。该业务线仍为 `NOT_RUN / NOT_CERTIFIED`。

## 业务线状态

| 业务线 | 本地工程状态 | 外部/独立状态 | 认证状态 | 上线前主要缺口 |
| --- | --- | --- | --- | --- |
| Spring 现代化 M30 | 13 条精确版本路线已有仓库自有源构建、转换、目标构建、启动/行为探针和本地测试；只能按具体路线判定 `LIMITED` 或 `READY_FOR_EXTERNAL_GATE` | 旧 campaign 将验证角色私钥提交在仓库内，相关“独立”证据全部作废；真实外部重放 `NOT_RUN` | `NOT_CERTIFIED` | 生产等价 Rootless Runner、安全/性能/回滚证据、客户验收；Ethan 仓外复核重签 |
| 全库跨语言 M29 | 210 路线中 90 `limited`、120 `research`、0 `certified` | 210/210 本地、独立、外部执行均 `NOT_RUN` | `NOT_CERTIFIED` | 每条方向路线的真实工具链、代表/holdout 语料、等价性、性能、安全、回滚和独立验证；本业务线不在当前 24×7 首批上线计划内 |
| SQL/ChinaDB M31 | 1,916/1,916 SQL 单元有显式处置；1,394 个自动候选中四目标共同可达 1,215，P0 route cell 为 0；ChinaDB 24,908/24,908 route unit 有处置 | 520 项人工迁移中仍有 85 项开放；13/13 厂商实库 `NOT_RUN`；75 ms 专用 Runner 性能门禁 `NOT_RUN_ENVIRONMENT_INVALID` | `NOT_CERTIFIED` | 先选一个精确 DM8 版本/驱动/字符集/时区/模式，完成双端执行、明细对账、性能、CDC、切换与回滚，再扩展其他厂商 |
| Frontend/MiniApp M32 | 22 个 Skill 有 allowlisted Handler；可移植状态 `DECLARED` | 官方 MiniApp 构建、浏览器/模拟器/真机旅程、权限隐私、视觉/无障碍、外部 holdout 均 `NOT_RUN` | `NOT_CERTIFIED` | 固定微信/支付宝等确切版本与设备矩阵，跑真实构建、核心旅程和 Batch 32 Gate，再由 Ethan 仓外复核 |
| 多语言项目生成 B46-B95 | 8 个精确语言 Profile 均为 `limited`；本地生成/构建/启动与 PostgreSQL Profile 证据只覆盖声明子集 | 托管 DB/IdP、生产 Rootless、交付、DR、独立 UAT 均 `NOT_RUN`；生产矩阵证据需按当前源码重新生成 | `NOT_CERTIFIED` | 在真实固定云/集群 Profile 中重新生成源码绑定证据，并完成部署、回滚、恢复、可观测性、安全和用户验收 |
| 成熟平台 B38-B45 | 模拟器、引擎和 gate 逻辑可作为本地工程证据 | 现有银行、医疗、审计记录是仓库生成/合成材料，不能代表客户或第三方；真实 field evidence `NOT_RUN` | `NOT_CERTIFIED` | 真实客户授权、生产等价多区环境、连续 SLO/故障/DR 数据、账单对账、外部审计底稿和独立复放 |
| 自主 QA / Project Intelligence / Foundry | 存在本地 Handler 和本地保守 Gate；Project Intelligence 仍有 `LOCAL/PARTIAL/PLAN`，源包任务与场景不能由绑定状态替代 | 云端 LLM、SCM Webhook、生产多租户调度、500 项任务、248 个验收场景及独立验收仍为 `NOT_RUN` | `NOT_CERTIFIED` | 执行真实 Provider/SCM/Runner 集成、代表项目与 holdout、权限/成本/回滚/长稳测试并完成外部复核 |

## 认证密钥事故处理

- 已从当前工作树删除全部 183 个已跟踪私钥文件。
- 中央 Ethan 信任锚与 13 组 Spring campaign 的旧锚均标记为 revoked。
- 公钥只保留作旧指纹识别和历史字节核验，不得批准新结论。
- Git 历史仍含泄露材料；所有旧密钥必须永久停用，不能通过“再次签名”恢复。
- Ethan 必须在仓库外生成和持有新密钥，并通过仓外认证渠道交付新公钥指纹。
- 新认证必须绑定精确 Git SHA、产物、环境、工作负载、授权、原始日志、重放命令、
  执行者与独立验证者；任何缺失、过期、同人执行/验证或不可重放状态都失败关闭。

## 失败关闭规则

以下情况不得解释为成功：`UNKNOWN`、`INCONCLUSIVE`、`NOT_RUN`、缺失或过期
证据、执行者与验证者相同、仓库能读取认证私钥、未授权外部操作、未绑定精确
产物与环境、合成客户/审计身份、局部工作区被当成全量工作区，以及静态检查被
描述成真实运行、生产就绪或认证。

权威认证与产品闭环 gate 当前应返回 `BLOCKED / NOT_CERTIFIED`，直到真实外部
证据产生并由 Ethan 使用仓外密钥独立核验。这是预期的工业级安全行为。

# 宿主API与持久化设计建议（lw.v1）

这些是待接入现有后端的接口边界，不是已经启动的服务。实际路由前缀和实体名以B0盘点为准。
`contracts/*.schema.json`约束数据形状；签名、授权、图有效性、时间关系和业务真实性需宿主额外验证。

## API

| 操作 | 建议路由 | 关键约束 |
|---|---|---|
| 读取交付能力 | GET /lw/v1/deliveries/{id} | tenant+ACL；分开read/teach/build/preview/debug/compare |
| 读取源码 | GET /lw/v1/snapshots/{digest}/source | 仓库授权、相对路径、字节范围和摘要；禁止任意URL |
| 解释源码/模块 | POST /lw/v1/explanations | 源码锚点+受众+模式；先事实再解释；不得附带执行权限 |
| 创建运行会话 | POST /lw/v1/sessions | delivery+profile+scenario+mode；原子配额+幂等key |
| 会话/剩余时间 | GET /lw/v1/sessions/{id} | 服务端now/ready/deadline、状态、generation、能力 |
| 就绪提交 | 内部ReadinessVerified事件 | 独立验证器签名、commit状态；浏览器不可直接调用 |
| 发送调试命令 | POST /lw/v1/sessions/{id}/debug-commands | 单控制lease、权限、epoch、generation、参数摘要 |
| 恢复事件流 | GET/WS /lw/v1/sessions/{id}/events | afterSequence；只恢复事件，不重放副作用请求 |
| 主动终止 | POST /lw/v1/sessions/{id}/terminate | 幂等；立即撤权并触发全部资源清理 |
| 获取课程 | GET /lw/v1/missions/{id} | 当前revision与stale状态；无隐藏答案 |
| 提交评估 | POST /lw/v1/missions/{id}/attempts | 服务端测试证据；不信任客户端passed=true |
| 来源映射 | GET /lw/v1/correspondences/{id} | source/IR/target多对多；每端独立权限 |

错误分类：401/403身份与权限；409版本/epoch/幂等参数冲突；410租约已过期；
422不可构建/入口无效/能力不支持；429并发或资源额度不足；503provider或适配器不可用。
操作幂等key绑定tenant+operation+payloadDigest，过期授权下不得重发缓存中的敏感响应。
控制命令丢响应不等于失败，返回UNKNOWN并要求状态对账。

## 实体与索引

- `lw_deliveries`：tenant、repo、snapshot、originRun、artifactDigest、manifestVersion、capabilities。
- `lw_sessions`：tenant、delivery、profile、mode、generation、state、runtimeStatus、created/ready/expires、resourceLease。
- `lw_resource_members`：session、app/db/cache/adapter/browser/volume/credential等member、providerID、deadline、cleanupState。
- `lw_debug_commands`：tenant/session/idempotencyKey唯一、payloadDigest、epoch、state、sent/committed、resultRef。
- `lw_runtime_events`：tenant/session/generation/sequence唯一、kind、payloadDigest、commitStatus、redaction。
- `lw_claims`/`lw_claim_evidence`：snapshot、scope、classification、rule/model版本、依赖证据与stale标记。
- `lw_missions`/`lw_attempts`：snapshot、mode、公开步骤、私有grader引用、用户私有进度。
- `lw_cleanup_receipts`：每个资源的已观测状态、verifier、证据、实际时间及隔离重试状态。

源码正文、日志、变量与截图不直接塞到session行；大对象放现有授权对象存储，主表保留摘要与引用。
所有跨表外键包含租户维度或经过同等隔离约束，查询与订阅都先授权。
API权限与数据库隔离需要双层验证，不能仅信任前端传来的tenantId。

## 原子性/恢复

准入在一个事务内扣占共享执行槽并建立资源lease；失败需要补偿释放。
first_ready_at采用 compare-and-swap，从NULL设置一次，并在同事务写deadline与outbox事件。
proxy只接受已提交session状态；provider容量检查失败则不能提交READY。
跨provider启动与数据库事务不存在自然的原子提交，使用状态机、幂等资源名、回查与补偿。
副作用已提交但通知失败时重发通知，不重新执行step或launch。
失联worker需要generation fencing；全局时钟异常与清理超时进入可观察的故障路径。

# 用户操作日志与运营管理端

## 目标与闭环

Web 控制台在根布局安装一次隐私安全采集器，记录页面访问、点击、表单提交、
字段变更、同源 API 成败与耗时、浏览器运行错误以及页面加载/FCP 指标。事件以
最多 20 条的批次发送到 `/api/telemetry/events`；失败批次保留在浏览器的
200 条有界队列中重试，不阻塞用户业务操作。

Next.js 同源 API 执行大小、字段、时间窗和 allow-list 校验，去除 URL 查询参数，
再使用只存在于服务端的内部凭证转发给 control-plane。control-plane 以可信配置
绑定组织与 Actor，并在同一事务中设置 PostgreSQL RLS 租户上下文。V50 扩展既有
`audit_events` 追加式审计表，事件重复提交按 `audit_id` 幂等忽略；V9 的禁止
UPDATE/DELETE 触发器继续生效。

`/admin` 管理端按 1 小时、24 小时、7 天或 30 天查询租户范围内的事件总量、
活跃会话、失败率、P95 耗时、各业务线表现、高频错误码和最近操作。管理员令牌
只保存在当前 React 页面内存，不进入 URL、localStorage 或操作日志。未配置管理
令牌、内部凭证、control-plane 或数据库时返回明确错误，不以空数组伪装健康。

## 数据最小化与禁止字段

允许字段仅包括：

- 随机事件 ID；浏览器会话 UUID 只用于同源传输，服务端写入前转换为 HMAC，
  PostgreSQL 不保存原始会话 UUID；
- 事件类型、稳定动作、业务线、无查询参数路由和稳定控件标识；
- 发生时间、耗时、成功/失败/取消结果和稳定错误码；
- 页面加载/FCP 等 allow-list 指标；
- 最多 8 个、每值不超过 64 字符的技术维度。

严禁采集输入值、项目/仓库内容、请求体、响应体、Bearer/API Token、Cookie、
URL 查询参数、错误原文、堆栈、原始 IP、原始 User-Agent 或可自由输入的文本。
管理端展示的 `target` 来自路由、元素类型、CSS 契约类或显式
`data-operation-id`，不读取按钮文字或输入内容。

## 运行配置

Web console 与 control-plane 共享：

- `ELMOS_OPERATIONS_API_KEY`：至少 24 字符的内部服务凭证；
- `ELMOS_OPERATIONS_TENANT_ID`：日志所属可信组织；
- `ELMOS_OPERATIONS_ACTOR_ID`：当前尚无统一 Web 登录时使用的服务端 Actor，
  默认仅限本地 `web-console-user`；
- `ELMOS_CONTROL_PLANE_BASE_URL`：control-plane 内部地址；
- `ELMOS_ADMIN_OBSERVABILITY_TOKEN`：至少 24 字符的短期管理员读取令牌。

control-plane 使用既有 `ELMOS_DATABASE_URL`、`ELMOS_DATABASE_USER` 和
`ELMOS_DATABASE_PASSWORD` 连接 PostgreSQL。生产环境不得把上述凭证打包进
浏览器、提交到仓库或写入日志。

## 保留、性能与运维边界

目标原始事件保留期为 30 天，但 V50 不创建自动删除任务，因为 `audit_events` 是追加式
审计链，生产删除需要获批的保留策略、归档证明和独立运维任务。当前本地实现与
测试不构成生产保留、告警路由、SLO、容量、成本或隐私审查证据；这些状态保持
`NOT_RUN`。

用户可在侧栏明确关闭匿名性能日志；关闭后会清空尚未发送的本地队列。采集采用
委托事件监听、2 秒批处理和 200 条有界队列，避免逐次点击产生同步网络
阻塞。管理查询最多 31 天、200 条明细，并使用组织/时间、业务线、结果和会话
索引。真实生产量级下仍需运行容量与成本基准，设置告警负责人并验证告警触发、
去重、恢复和 runbook。

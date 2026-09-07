# 生产运营管理端部署与验收

## 七个管理分区

`/admin` 按租户提供七个分区：

1. **用户与租户**：显示已验证的当前用户、选中组织、角色、权限和会话中的全部
   成员资格；不会用当前会话臆测 IdP 全量用户目录。
2. **任务队列**：显示生成、翻译和 Spring 的任务/运行事件；容量、TTL、租约、
   恢复和取消仍以 Runner 持久状态为准，浏览器不拥有执行权。
3. **仓库**：显示仓库工作区与交付审计，并进入受控工作区；Commit、Push、PR
   仍是分离权限。
4. **审计**：显示最近追加式审计，并按稳定游标导出有上限的 CSV；中断或达到页数
   上限时绝不把部分文件冒充完整导出。
5. **告警与事件**：执行 SLO 评估、告警确认、事件接手/解决、修复提案审批和 SCM
   准备，所有写操作均带角色和乐观版本检查。
6. **用量与性能**：显示各业务线事件量、活跃 HMAC 会话、失败率、P95 和稳定错误
   码；不生成个人生产力评分。
7. **配置与门禁**：只读显示脱敏后的 SLO 预算、自动化模式、保留证据和外部门禁；
   不返回 Secret 值。

页面不能自行提权。Web BFF 对每次管理读写都要求已验证邮箱精确等于
`zpchoney@gmail.com` 的 OIDC 会话，并分别要求 `VIEWER`、`OPERATOR` 或
`APPROVER` 对应的管理权限；浏览器短期令牌不再是管理端身份来源。

## 1. 组成与最低资源

- Web Console：Next.js 16，提供 `/admin`、业务 API 前置审计和匿名性能遥测。
- Control Plane：Spring Boot 3.5 / Java 21，提供结果审计、SLO、告警、事件、
  快修治理和保留 API。
- PostgreSQL 17：Flyway V1–V51；全部运营表强制 RLS。
- 可选外部组件：企业 IdP、Secret Manager、HTTPS 告警 webhook、SCM/CI/CD。

本地开发建议至少 4 核、16 GB RAM、20 GB 可用磁盘；Java 21、Maven 3.9+、
Node.js 22、pnpm 10.12.4、PostgreSQL 17。生产可从 Web 2 vCPU/2 GB、
Control Plane 2 vCPU/4 GB、PostgreSQL 2 vCPU/4 GB 起步，但这只是启动基线，
不是容量证明。副本、连接池、磁盘、IOPS、备份和 RPO/RTO 必须由真实压测决定。

## 2. 数据库

使用迁移专用、短期、最小权限凭证：

```bash
export ELMOS_COMMERCIAL_DATABASE_URL='jdbc:postgresql://<host>/<database>?sslmode=require'
export ELMOS_COMMERCIAL_DATABASE_MIGRATION_USERNAME='<migration-role>'
export ELMOS_COMMERCIAL_DATABASE_MIGRATION_PASSWORD='<secret-manager-injected>'
./scripts/commercial/migrate_neon.sh
```

确认 Flyway 至少迁移到当前仓库的 V79，运营、身份、执行队列、对象存储与支付目录所需表
及强制 RLS 策略均存在。应用运行身份不得拥有绕过 RLS 的角色属性。连接串和密码不得进入
仓库、镜像、日志或浏览器变量。

精确管理员邮箱首次成功建立 OIDC 账户后，还要由获准的数据库运维人员执行一次可审计的
跨租户管理员引导；`account_id` 必须对应状态为 `ACTIVE`、邮箱已验证且规范化后精确等于
`zpchoney@gmail.com` 的账户，V79 会拒绝其他账户：

```bash
ELMOS_DATABASE_URL='postgres://<host>/<database>?sslmode=require' \
  ./scripts/operations/bootstrap_platform_admin.sh \
  '<administrator-account-id>' \
  'initial production platform administrator'
```

脚本需要人工输入 `yes`，并在 `platform_admin_access_log` 留下原因。后续授予或撤销仍走
带审计的管理路径；管理员邮箱失去验证、停用或改名时，数据库触发器会自动撤销其平台权限。

## 3. Control Plane

```bash
export ELMOS_DATABASE_URL='jdbc:postgresql://<host>/<database>?sslmode=require'
export ELMOS_DATABASE_USER='<runtime-role>'
export ELMOS_DATABASE_PASSWORD='<secret-manager-injected>'
export ELMOS_OPERATIONS_API_KEY='<at-least-24-char-short-lived-secret>'
export ELMOS_OPERATIONS_API_KEY_EXPIRES_AT='<RFC3339-within-next-24-hours>'
export ELMOS_OPERATIONS_TENANT_ID='<tenant-id>'
export ELMOS_OPERATIONS_ACTOR_ID='<service-or-operator-id>'
export ELMOS_BUSINESS_AUDIT_REQUIRED='true'
export ELMOS_OPERATIONS_AUTOMATION_ENABLED='true'
export ELMOS_OPERATIONS_EVALUATION_INTERVAL_MS='300000'
export ELMOS_OPERATIONS_RETENTION_ENABLED='true'
export ELMOS_OPERATIONS_RETENTION_DAYS='30'
export ELMOS_OPERATIONS_RETENTION_INTERVAL_MS='86400000'
export ELMOS_OPERATIONS_NOTIFICATION_ENABLED='true'
export ELMOS_OPERATIONS_NOTIFICATION_WEBHOOK_URL='https://<exact-alert-endpoint>'
export ELMOS_OPERATIONS_NOTIFICATION_HMAC_SECRET_FILE='/run/secrets/elmos-alert-hmac'
export ELMOS_OPERATIONS_NOTIFICATION_INTERVAL_MS='15000'
export ELMOS_OIDC_ISSUER_URI='https://<idp>/'
export ELMOS_OIDC_JWKS_URI='https://<idp>/.well-known/jwks.json'
export ELMOS_OIDC_AUDIENCE='<control-plane-audience>'
```

内部租约过期或超过 24 小时会失败关闭。使用 Secret Manager 轮换密钥，限制网络
为 Web BFF 到 Control Plane 以及精确告警端点，数据库只允许应用和迁移身份。
告警 HMAC 文件至少 32 字节，必须使用绝对路径且不得授予 group/other 权限。
投递使用五分钟数据库租约、幂等通知 ID、HMAC-SHA256、禁止重定向、指数退避和
20 次失败封顶；未显式启用或配置不完整时不发起网络请求。

## 4. Web Console

生产先配置企业 OIDC（Issuer、Authorization、Token、JWKS、Client ID/Secret、
Audience、Redirect URI 和至少 32 字符 `ELMOS_SESSION_SECRET`），并确保 ID
Token 提供可信的 `sub`、`email` 与布尔值 `email_verified`。IdP 还必须为
`ELMOS_OIDC_AUDIENCE` 签发可由同一 Issuer/JWKS 验证的 JWT Access Token，并在其中
映射与 ID Token 完全一致的 `sub`、规范化后精确等于 `zpchoney@gmail.com` 的
`email` 和布尔值 `email_verified: true`。Opaque Access Token、缺失 claim 或身份
不一致都会在写入会话和发送管理员登录通知前失败关闭并撤销令牌。任何其他邮箱携带
的管理角色或权限都会在 Web 会话边界被移除。管理 API 继续验证加密会话、访问令牌
摘要、租户成员关系、权限与同源变更；Java Control Plane 仍会独立验证 Access Token
的签名、Issuer、Audience、有效期和身份 claims。

```bash
export ELMOS_CONTROL_PLANE_BASE_URL='https://<internal-control-plane>'
export ELMOS_OPERATIONS_API_KEY='<same-short-lived-secret>'
export ELMOS_OPERATIONS_API_KEY_EXPIRES_AT='<same-expiry>'
export ELMOS_OPERATIONS_TENANT_ID='<tenant-id>'
export ELMOS_OPERATIONS_ACTOR_ID='<service-or-operator-id>'
export ELMOS_ADMIN_LOGIN_NOTIFICATIONS_ENABLED='true'
export ELMOS_ADMIN_LOGIN_EMAIL_FROM='ELMOS Security <security@example.com>'
export ELMOS_RESEND_API_KEY_FILE='/run/secrets/elmos/resend-api-key'
```

管理员每次完成 OIDC 登录时，Web Console 都会先把安全通知提交到固定邮件服务，
收件人固定为 `zpchoney@gmail.com`；只有邮件服务返回有效投递 ID 后才写入会话
Cookie。通知未启用、配置不完整、超时、限流或被拒绝时均失败关闭。Resend API
Key 必须通过 Secret Manager 注入；`ELMOS_RESEND_API_KEY_FILE` 必须是绝对路径、
普通文件、非符号链接且不得授予 group/other 权限。浏览器不再接受共享管理令牌。
生产 Compose 以 UID `10001` 运行 Web Console，因此宿主 secret 的 owner 必须让该
UID 可读，同时保持 `0600`（或等价的无 group/other 权限）并只读挂载。

## 5. 构建

```bash
JAVA_HOME=$(/usr/libexec/java_home -v 21) \
  mvn -pl apps/control-plane -am clean package
pnpm --dir apps/web-console install --frozen-lockfile
pnpm --dir apps/web-console check
```

本地分别启动 PostgreSQL、Control Plane 和 Web。云端使用仓库既有容器/平台配置
部署保存的同一提交；一次本地构建不等于云部署成功。

## 6. 上线验收

1. 用未登录、错误邮箱、未验证邮箱、邮箱别名和伪造管理角色验证 401/403；确认普通
   用户会话和 Bearer 管理令牌均不能进入 `/admin` 或调用 `/api/admin/*`。
2. 每条业务线至少调用一个 GET 和一个有副作用 API，确认 BFF 的
   `BUSINESS_ATTEMPT`/`BUSINESS_OPERATION` 与 control-plane 的
   `SERVER_ATTEMPT`/`SERVER_OPERATION`，且路由无 ID/查询。
3. 注入安全失败/慢请求，确认 SLO 评估生成告警、事件、通知 outbox 和唯一提案；
   重复评估不能制造告警风暴；确认 webhook 收到可验证 HMAC 和幂等通知 ID。
4. 用 `OPERATOR` 确认告警、接手/解决事件；陈旧版本必须返回 409。
5. 用 `APPROVER` 审批并生成 `READY_FOR_SCM`；确认 SHA-256 存在，同时真实
   SCM、测试和部署仍为 `NOT_RUN`。
6. 对过期安全测试遥测执行保留，确认只删除 `product_telemetry_events`，保留
   聚合证据且 `audit_events` 未删除。
7. 完成真实 webhook 投递/恢复、值班接收、容量/成本、隐私评审、备份恢复和
   故障演练后，才可更新外部证据状态。

## 7. 回滚

- 应用可回滚到上一内容摘要，但不得通过删除 V51 表回滚数据库。
- 关闭自动评估/保留环境开关可停止后台动作，不影响查询和审计。
- 修复提案以 `artifactDigest` 绑定外部 SCM 回滚；工作流历史保持追加式。
- 审计不可用时有副作用的 Web BFF 操作返回 503；先恢复审计，不得绕过 middleware。

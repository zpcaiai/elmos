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

页面不能自行提权。Control Plane 对每次写操作重新解析 OIDC 租户角色，或验证获批
且有到期时间的 break-glass 绑定，并分别要求 `VIEWER`、`OPERATOR` 或
`APPROVER`。

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

确认 Flyway 至少迁移到当前仓库的 V64，运营、身份、执行队列、对象存储与支付目录所需表
及强制 RLS 策略均存在。应用运行身份不得拥有绕过 RLS 的角色属性。连接串和密码不得进入
仓库、镜像、日志或浏览器变量。

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
Audience、Redirect URI 和至少 32 字符 `ELMOS_SESSION_SECRET`），并把
`admin:read`、`admin:operate`、`admin:approve` 映射到分离角色。管理 API 会
验证加密会话、访问令牌摘要、租户成员关系、权限与同源变更。

```bash
export ELMOS_CONTROL_PLANE_BASE_URL='https://<internal-control-plane>'
export ELMOS_OPERATIONS_API_KEY='<same-short-lived-secret>'
export ELMOS_OPERATIONS_API_KEY_EXPIRES_AT='<same-expiry>'
export ELMOS_OPERATIONS_TENANT_ID='<tenant-id>'
export ELMOS_OPERATIONS_ACTOR_ID='<service-or-operator-id>'
export ELMOS_ADMIN_OBSERVABILITY_TOKEN='<at-least-24-char-admin-lease>'
export ELMOS_ADMIN_OBSERVABILITY_TOKEN_EXPIRES_AT='<RFC3339-within-next-24-hours>'
export ELMOS_ADMIN_OBSERVABILITY_TENANT_ID='<tenant-id>'
export ELMOS_ADMIN_OBSERVABILITY_ACTOR_ID='<service-or-operator-id>'
export ELMOS_ADMIN_OBSERVABILITY_ROLE='APPROVER'
export ELMOS_ADMIN_ALLOW_TOKEN_FALLBACK='false'
```

短期管理令牌仅用于本地或获批 break-glass；生产默认拒绝回退。日常值班通过
OIDC 分别授予读、运营、审批权限，不共享审批身份。角色只由服务端会话映射，
浏览器不能自行提升。

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

1. 用无令牌、过期令牌、错误租户/Actor 和低权限角色验证 403/503。
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

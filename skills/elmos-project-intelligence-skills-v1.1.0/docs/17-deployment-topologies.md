# 部署拓扑与环境

## 1. Developer Mode

```text
Docker Compose
├── insight-web
├── insight-api
├── analyzer-core
├── intelligence-worker
├── artifact-service
├── PostgreSQL
├── Redis
├── MinIO
├── Graph Store
└── Temporal
```

目标：本地功能开发和小仓库验证。默认禁用公网写连接器和生产凭据。

## 2. SaaS Shared Control Plane

- 多租户 Control Plane；
- 按租户/项目调度 worker；
- 共享但逻辑隔离 PostgreSQL/Graph/Search；
- KMS 分层密钥；
- egress allowlist；
- Enterprise 可选择专属模型和专属 worker pool。

## 3. Dedicated Tenant

- 独立 namespace、数据库/schema、bucket/key、worker pool；
- 专属网络和 KMS；
- 企业 SSO/SCIM；
- 可连接私有 Git、Trace、制品库；
- Control Plane 可由 Elmos 托管或客户托管。

## 4. Private Cloud / On-prem

- Helm Chart；
- 外部 PostgreSQL、S3、OIDC 可注入；
- 内网 Git/模型/制品库；
- 无公网依赖；
- 离线镜像包、SBOM、签名和升级包；
- 遥测可配置只留本地。

## 5. Worker 安全

- 每个分析任务独立工作目录；
- 非 root、只读基础镜像；
- 不挂载 Docker socket；
- CPU/Memory/PID/Disk/Time 配额；
- 网络默认关闭；
- Artifact renderer 单独沙箱；
- 模型调用通过受控 gateway；
- 任务结束清理临时数据。

## 6. 备份与恢复

| 数据 | 备份 | 恢复验证 |
|---|---|---|
| PostgreSQL | PITR + 定期全量 | 每月恢复演练 |
| Object Store | Versioning/Replication | hash 抽样 |
| Temporal | 数据库备份 | workflow resume 演练 |
| Graph/Search | 可重建快照 | 从 IR 重建 |
| Audit/Certification | WORM/签名 | 离线验证 |
| Secrets | 外部 Vault/KMS | 不备份明文 |

## 7. 升级

- 数据库 migration 向前/后兼容窗口；
- Workflow versioning；
- Parser/IR/Graph Schema migration；
- Artifact generator 版本并存；
- 蓝绿或滚动升级；
- 失败自动停止，不无备份强行迁移。

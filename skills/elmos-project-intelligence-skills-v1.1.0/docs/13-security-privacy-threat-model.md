# 安全、隐私与威胁模型

## 1. 受保护资产

- 私有源代码和 Git 历史；
- 架构、API、数据模型和漏洞；
- 模型输入输出、Prompt 和缓存；
- Git、云、数据库、模型凭据；
- Artifact、报告和客户商业信息；
- 用户身份、评论、审批和审计；
- 运行 Trace、日志和生产拓扑。

## 2. 信任边界

1. 用户浏览器；
2. API Gateway/BFF；
3. Control Plane；
4. 不可信仓库数据；
5. Analysis Worker/Sandbox；
6. Model Provider；
7. Graph/Search/Object Store；
8. External Connectors；
9. Export/Share Recipient；
10. SaaS Tenant Boundary。

## 3. 主要威胁与控制

| 威胁 | 示例 | 主要控制 |
|---|---|---|
| Prompt Injection | README 指示 Agent 读取密钥 | 仓库内容数据隔离、系统指令优先、工具白名单 |
| Secret Exfiltration | 代码/日志含 token | Secret scan、脱敏、模型上下文过滤 |
| Cross-tenant Leak | 搜索返回其他客户片段 | tenant scope、查询层授权、隔离缓存 |
| Broken Access Control | 深链绕过文件权限 | 服务端 evidence/node/file 权限检查 |
| Unsafe Rendering | SVG/PlantUML include | 沙箱、禁网、资源限制、SVG sanitize |
| Supply Chain | 恶意依赖/镜像 | SBOM、签名、扫描、固定 digest |
| SSRF/Egress | Worker 访问内网 | egress deny-by-default、allowlist |
| Duplicate Side Effect | 重试重复创建 PR/账单 | idempotency record、outbox |
| Data Retention Failure | 删除后对象仍存在 | 删除工作流、验证报告、备份策略 |
| Model Data Use | 代码被外部训练 | Provider policy、enterprise/local model routing |
| Audit Tampering | 管理员删除记录 | append-only、WORM/签名、职责分离 |
| Malicious Archive | Zip slip/bomb | 路径规范化、大小/文件数/压缩比限制 |

## 4. 安全默认值

- 只读导入；
- 不执行仓库脚本；
- 无任意终端；
- 网络默认关闭；
- 非 root、只读根文件系统；
- 短期凭据；
- 最小权限；
- 模型上下文按需、脱敏；
- 分享默认过期和水印；
- 高危自动修复必须人工批准；
- E4/E5 认证需要职责分离。

## 5. 数据分类

```text
PUBLIC
INTERNAL
CONFIDENTIAL
SOURCE_CODE
RESTRICTED_SECURITY
PERSONAL_DATA
SECRET
```

分类影响：

- 可用模型；
- 可用部署区域；
- 是否允许导出/分享；
- Artifact 水印；
- 保留期限；
- 审批要求；
- 日志/Trace 采样。

## 6. 安全验收

- SAST/SCA/Secret/IaC/Container/SBOM；
- API 权限矩阵；
- 跨租户红队；
- Prompt Injection 红队；
- 恶意仓库/Archive/Diagram DSL；
- 连接器 token 过期和撤销；
- 分享撤销；
- 日志和模型输入脱敏；
- 备份/删除；
- E4/E5 外部或独立安全评审。

## 在线调试专项威胁

| 威胁 | 主要控制 |
|---|---|
| 恶意项目利用调试执行逃逸 | microVM/容器隔离、非 Root、只读根、seccomp、无 Docker Socket、资源限制 |
| Evaluate/Breakpoint Condition 执行副作用 | 默认只读 AST/adapter policy、显式审批、一次性环境、审计 |
| 生产 attach 导致停顿或数据泄漏 | 默认拒绝、break-glass 双人审批、只读优先、短 TTL、自动终止 |
| 变量/日志/Replay 泄漏 Secret/PII | 服务端字段脱敏、大小限制、加密、签名、保留期与扫描 |
| 网络或依赖下载外泄代码 | egress deny、域名/制品白名单、代理审计 |
| 资源滥用/Fork bomb/无限输出 | CPU/内存/磁盘/PID/日志/时长配额和 kill switch |
| 跨租户会话或变量引用 | opaque session-local references、ABAC、网关服务端过滤 |
| Adapter 供应链或协议攻击 | 摘要钉住、签名、扫描、消息限长/校验、独立进程隔离 |

# P01 安全、隐私与治理

## 1. 威胁模型

- 不可信输入：仓库代码、Issue/PR 文本、文档、Prompt、依赖、模型输出、工具输出和外部网页。
- 高价值资产：源码、Secret、云/代码托管凭据、客户数据、规则库、证据、账单和生产环境。
- 主要风险：Prompt injection、越权工具、路径穿越、凭据继承、供应链、数据外泄、跨租户、重复副作用、证据篡改和不安全自动修复。

## 2. 本包专用控制

- 硬编码/组织级 sensitive resource deny 优先于租户和会话配置。
- Tracker、代码托管、云和模型凭据在 host-side Broker 使用，默认不进入 Agent 子进程。
- 工具执行参数与路径先 canonicalize，再做策略匹配，防止 symlink/../ 绕过。
- 网络、文件、进程、数据库、Secret 作为独立能力分别授权。
- Session 日志加密、租户密钥隔离、完整性校验和可配置保留/删除。

## 3. 通用权限模型

`subject × action × resource × context → allow | ask | deny`

优先级：平台硬拒绝 > 法规/组织 > 租户 > 项目 > Agent 角色 > 会话临时授权。下层不能覆盖上层 deny。

## 4. 凭据与 Secret

- 长期凭据只存在 Secret Broker；Agent 通过 host-side tool 或短期 capability 调用。
- 启动子进程时清理已知凭据变量及其别名；同时对输出/日志做 Secret scan。
- 仓库内明文凭据视为安全事件，不因 workspace 可读而认为合法。

## 5. 沙箱与副作用

- 默认 read-only；代码生成限定 workspace-write；网络、数据库、部署和删除独立审批。
- 沙箱报告 full/partial；需要绝对边界的任务不接受 partial。
- 非幂等副作用记录 idempotency/compensation，重试前确认结算状态。

## 6. 数据治理

- 数据分类：public/internal/confidential/restricted；决定 Provider、存储、日志、保留和学习 scope。
- 机密代码默认 ZDR/BYOK/私有部署；预览/匿名模型默认 deny。
- 进入 P07 前执行 consent、Secret/PII/IP/license 检测与不可逆抽象。

## 7. 安全 Gate

- Threat model 与 data-flow diagram 完成。
- 权限矩阵、硬拒绝、凭据隔离、沙箱和租户隔离测试通过。
- Critical/High 安全、供应链和 Secret finding 为 0 或正式风险接受。
- 审计日志完整、不可篡改，并支持按 tenant/job/run/evidence 查询。

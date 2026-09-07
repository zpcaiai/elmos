# 构建、发布与运维

## 1. 环境

建议环境：

- `dev`：本地与 mock；
- `test`：自动化测试和 sandbox；
- `preview`：平台预览/体验版；
- `staging`：候选发布，接近生产配置；
- `production`：正式版本。

平台账户与凭证按环境隔离。不得用生产凭证构建不可信分支。

## 2. Pipeline

```text
validate-request
→ inventory
→ analyze
→ validate-ir
→ resolve-plan
→ generate
→ static-check
→ native-build
→ semantic-test
→ visual-test
→ privacy-security
→ performance
→ evidence
→ approval-preview
→ preview
→ approval-upload
→ upload
→ approval-review
→ submit-review
→ approval-release
→ release
→ post-release-monitor
```

每个阶段生成独立回执。后续阶段不得覆盖前一阶段记录。

## 3. Toolchain Profile

```yaml
platform: alipay
profile_version: 2026-08-19.1
tool:
  name: official-miniapp-cli
  version: "<pinned>"
runtime:
  os: "<pinned>"
  architecture: "<pinned>"
commands:
  build: [...]
  preview: [...]
  upload: [...]
capabilities:
  headless_build: true
  headless_preview: true
  headless_upload: true
verified_at: "2026-08-19"
```

实际命令和版本应由当前官方文档及实测维护。不要在业务 generator 中硬编码安装路径。

## 4. Build Worker

- 一次性 workspace；
- 只读输入；
- 临时输出；
- 固定工具；
- 网络最小化；
- secret 按动作注入；
- 日志脱敏；
- 产物哈希；
- 资源配额；
- 超时和取消；
- 失败保留必要证据后销毁。

## 5. Versioning

目标版本由：

```text
source revision
+ IR schema version
+ rule set version
+ target generator version
+ platform profile version
```

共同决定。平台可见版本号和内部 build ID 分离，避免因自动重试产生不可追踪版本。

## 6. Preview

Preview 可自动化到何种程度由平台工具 profile 决定。输出：

- preview ID；
- 二维码或链接 artifact；
- 过期时间；
- target app；
- source/IR/build hashes；
- 操作人/审批；
- 设备验证清单。

二维码和链接可能包含敏感访问能力，应按 artifact ACL 保护。

## 7. Upload / Review / Release

### Upload

- 只上传已通过 G0–G9 适用门禁的同一 artifact；
- 验证 app binding；
- 记录平台回执；
- 不自动提交审核。

### Review

- 生成版本说明、隐私披露、权限用途、测试账号和审核材料；
- 业务、隐私和发布责任人审批；
- 提交后跟踪状态和拒绝原因；
- 拒绝原因进入 finding，不直接让模型无界修改。

### Release

- 明确灰度/全量；
- 保存上一稳定版本；
- 监控崩溃、关键流程、支付、性能和平台告警；
- 达到阈值自动建议或执行预授权回滚；
- 回滚也记录审批和回执。

## 8. Drift Detection

定期检测：

- 官方 CLI/IDE 版本；
- platform profile；
- API/组件/权限；
- 审核政策；
- 账户能力；
- 生成模板；
- 依赖漏洞；
- Schema/IR 版本。

漂移后：

- 标记受影响任务；
- 重新运行 registry fixtures；
- 旧 evidence 不改写；
- 新发布必须使用已验证 profile。

## 9. SLO 与运行时 ETA

Elmos UI 应显示：

- 当前阶段；
- 已完成节点；
- 阻断项；
- 机器墙钟已运行时间；
- 基于同类历史任务的 P50/P80 ETA；
- 置信区间；
- 主要剩余关键路径；
- 成本累计与预测。

不要显示人工开发人日作为系统转换 ETA。样本不足时显示“历史样本不足”，而不是给出虚假时间。

## 10. 运维指标

- conversion success rate；
- stage failure rate；
- cache hit rate；
- auto-repair convergence；
- native build pass rate；
- semantic/visual gate pass rate；
- C/D/E distribution；
- secret findings；
- cross-tenant policy violations；
- platform drift incidents；
- system wall-clock P50/P95；
- cost per source KLOC/page/target；
- rollback rate；
- review rejection reason。

## 11. 灾难恢复

- 任务状态、artifact index、approval 和 evidence 存数据库；
- 大文件进对象存储并多副本；
- 状态与 artifact 哈希可重建；
- worker 无状态；
- 检查点可在其他 worker 恢复；
- 平台副作用保存 idempotency key 与回执；
- 对象存储损坏时不声称任务可恢复；
- 定期演练恢复和跨区域备份。

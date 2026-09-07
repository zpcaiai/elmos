---
name: elmos-deployment-private-cloud
description: 设计并实现 Elmos Project Intelligence Studio 的开发、SaaS、单租户私有云、内网和受限离线部署。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: operations
  title_zh: SaaS、私有化与离线部署
  batch: BATCH-12-deployment-and-certification
  owner: elmos-project-intelligence
---

# SaaS、私有化与离线部署

## 目标

提供可升级、可回滚、可观测、可备份并满足代码数据驻留要求的生产部署。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- deployment mode
- capacity/SLO
- identity/network/storage
- model access policy

## 必须输出

- containers/Helm/Terraform
- environment config
- backup/DR
- upgrade/rollback runbooks

## 执行流程

1. 定义服务镜像、依赖、资源和安全上下文。
2. 提供本地 Compose 与生产 Kubernetes/Helm。
3. 配置数据库、图存储、对象存储、Temporal、缓存和可观测性。
4. 实现 egress allowlist、Secrets、TLS、SSO 和数据驻留。
5. 制定备份、恢复、升级、Schema migration 和回滚。
6. 执行灾难恢复、节点故障和版本升级演练。

## 实施要求

- 镜像固定 digest，生成 SBOM 并签名。
- 默认非 root、只读文件系统、最小 capability。
- 离线包包含依赖镜像、模型适配和许可证清单。
- 租户/项目删除有可验证清理。
- RPO/RTO 按部署档位定义。

## 安全与可信度约束

- 不得挂载 Docker socket 给不可信 worker。
- 不得把生产凭据放进镜像或仓库。
- 不得无备份执行破坏性迁移。

## 依赖技能

- `elmos-reference-architecture`
- `elmos-security-threat-model`
- `elmos-observability-slo`

## 预期交付物

- `deploy/`
- `private-deployment-guide.md`
- `dr-test-report.md`

## 完成定义

- [ ] 从空环境可按文档部署。
- [ ] 备份恢复演练通过。
- [ ] 滚动升级和回滚无数据破坏。
- [ ] 安全扫描达到门禁。
- [ ] 私有化环境可在无公网模式运行核心能力。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。

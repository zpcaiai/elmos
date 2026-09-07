---
name: elmos-project-report-bundle
description: 组合代码、架构、流程、数据、API、安全、技术债、转换和测试结果，生成项目介绍、尽调、交接、审计或认证报告包。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: artifacts
  title_zh: 项目全景报告与交付证据包
  batch: BATCH-06-documents-presentations-reports
  owner: elmos-project-intelligence
---

# 项目全景报告与交付证据包

## 目标

提供一次可下载、可审计、可复现的项目全景交付，而不是零散文件。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- 选定 artifact versions
- 报告场景
- 权限/脱敏策略
- 签名配置

## 必须输出

- 报告目录
- HTML/PDF
- 附件清单
- 证据包
- 哈希/签名 manifest

## 执行流程

1. 冻结项目 revision 和所有引用 artifact version。
2. 根据报告类型选取章节、图表、PPT 和原始证明。
3. 检查 claim/evidence 完整性和 stale 状态。
4. 应用脱敏、水印、受众权限和保留策略。
5. 生成目录、交叉链接、manifest、哈希和可选签名。
6. 执行离线打开与完整性验证。

## 实施要求

- 支持项目介绍、技术尽调、项目交接、架构评审、迁移方案、生产认证。
- 包内路径必须相对且可离线浏览。
- 引用的图表保留源 Spec。
- 敏感附件分层加密或排除。
- 报告状态分 Draft/Reviewed/Approved/Certified。

## 安全与可信度约束

- 存在 stale 或权限不足证据时不得标记 Certified。
- 不得将未选中的原始代码打包。
- 签名密钥不得进入报告工作区。

## 依赖技能

- `elmos-architecture-documentation`
- `elmos-presentation-generation`
- `elmos-evidence-provenance`

## 可选后置集成

- `elmos-release-certification`：仅在报告状态升级为 Certified 时要求，不阻塞 Draft/Reviewed/Approved 报告包。

## 预期交付物

- `delivery-bundle.zip`
- `bundle-manifest.json`

## 完成定义

- [ ] 离线包完整可导航。
- [ ] manifest 哈希验证成功。
- [ ] 所有关键引用可解析。
- [ ] 脱敏规则测试通过。
- [ ] 报告状态与审批记录一致。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。

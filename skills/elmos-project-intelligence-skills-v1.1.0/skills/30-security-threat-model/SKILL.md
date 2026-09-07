---
name: elmos-security-threat-model
description: 发现认证授权、敏感数据、信任边界、密钥、依赖、注入和供应链风险，并生成威胁模型、攻击路径和安全数据流图。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: intelligence
  title_zh: 代码与架构安全分析及威胁建模
  batch: BATCH-07-search-impact-governance-analysis
  owner: elmos-project-intelligence
---

# 代码与架构安全分析及威胁建模

## 目标

把安全证据嵌入项目图谱、代码阅读、文档和认证流程。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Code/Intelligence Graph
- DFD
- dependencies/SBOM
- deployment/network config

## 必须输出

- threat model
- security findings
- attack paths
- sensitive DFD
- remediation plan

## 执行流程

1. 识别资产、Actor、入口、信任边界和数据分类。
2. 执行 SAST/SCA/secret/IaC/API auth 检查。
3. 基于 STRIDE/项目规则生成威胁候选。
4. 构建攻击路径并结合可达性和运行证据排序。
5. 关联漏洞到功能、代码、数据、部署和测试。
6. 生成修复、验证和残余风险记录。

## 实施要求

- 高风险结论必须有工具或代码证据。
- 支持 SBOM、许可证和依赖可达性。
- 敏感数据流图按权限隔离。
- 误报抑制需带原因和到期。
- 生成内容本身进行 Prompt Injection 与数据泄漏防护。

## 安全与可信度约束

- 不得输出可直接利用客户系统的秘密或敏感 payload。
- 不得把扫描器未发现解释为无风险。
- 禁止自动升级权限或访问生产环境。

## 依赖技能

- `elmos-data-architecture-lineage`
- `elmos-api-event-topology`
- `elmos-architecture-rules`

## 预期交付物

- `threat-model.md`
- `security-findings.sarif`
- `attack-paths.json`

## 完成定义

- [ ] 关键入口有认证/授权检查覆盖。
- [ ] 已知测试漏洞可检测。
- [ ] 威胁模型包含资产、边界、威胁、控制和残余风险。
- [ ] 修复后可重跑并闭环证据。
- [ ] 高危未处置时不能通过生产认证。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。

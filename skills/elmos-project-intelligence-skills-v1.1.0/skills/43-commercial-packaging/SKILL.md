---
name: elmos-commercial-packaging
description: 设计 Elmos Project Intelligence Studio 的 Community/Professional/Enterprise/Private
  等版本、用量计量、配额、计费、试用和交付边界。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: product
  title_zh: 商业版本、计量与交付套餐
  batch: BATCH-13-commercialization
  owner: elmos-project-intelligence
---

# 商业版本、计量与交付套餐

## 目标

把技术能力组合为可售卖、可运营、不会破坏核心可信度和安全性的商业产品。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- customer segments
- cost model
- capabilities
- deployment/support policy

## 必须输出

- edition matrix
- metering events
- quota policy
- packaging/pricing hypotheses
- sales enablement

## 执行流程

1. 定义个人开发者、团队、软件现代化服务商和大型企业场景。
2. 按代码规模、分析 run、模型 Token、artifact、并发和保留期设计计量。
3. 设计 Reader、Architecture、Documentation、Modernization 等套餐。
4. 区分 SaaS、专属租户、私有化和离线授权。
5. 定义试用、超额、预算告警、用量可视化和成本归因。
6. 生成售前材料、实施清单和 SLA 边界。

## 实施要求

- 核心证据、权限和安全不得作为付费后才启用的可选正确性。
- 定价假设与实际基础设施/模型成本联动。
- 企业功能覆盖 SSO、审计、私有模型、驻留和支持。
- 版本能力通过 entitlement service 控制并可审计。
- 计量事件幂等且可对账。

## 安全与可信度约束

- 不得暗示无法达到的分析准确率或转换成功率。
- 不得按未披露的隐性指标收费。
- 不得因配额超限破坏已完成 artifact 的可访问性策略。

## 依赖技能

- `elmos-runtime-cost-estimator`
- `elmos-release-certification`

## 预期交付物

- `edition-matrix.md`
- `metering-event-schema.json`
- `commercial-model.md`

## 完成定义

- [ ] Edition matrix 无矛盾。
- [ ] 计量与账单样例可对账。
- [ ] 预算告警和硬限额测试通过。
- [ ] 销售材料与真实实现/认证一致。
- [ ] 单位经济模型能解释毛利主要驱动。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。

# FOUNDATION_COMPATIBILITY

`batch-01` 是本系列的产品与治理基础层；本文件定义它向后续 Batch 提供的稳定契约。

## 上游输入

- 无前置 Batch；输入来自产品战略、公开证据和人工批准。

## 本 Batch 输出

- `CompetitorRegistry`
- `CapabilityTaxonomy`
- `DirectionalRoutePolicy`
- `TrustLevelModel`
- `ProductPositioningDecision`
- `ProductBoundary`
- `ReferenceRouteDecision`
- `BattlecardPolicy`

## 兼容性规则

- 所有后续 Batch 使用同一 Capability ID 和 Route ID 命名空间。
- 产品定位和不支持范围是工程与销售的共同约束。
- 证据级别、Claim 类型和可信等级不得在下游重新定义。
- Route 必须始终方向性、版本化和工作负载限定。

## 版本策略

```yaml
versioning:
  schema:
    patch: 文档或约束澄清，不改变语义
    minor: 向后兼容新增字段或能力
    major: 语义、状态机或可信边界发生不兼容变化
  certificates:
    bind:
      - input-digests
      - schema-versions
      - policy-versions
      - tool-or-rule-versions
      - tenant-and-scope
  unknown-fields:
    preserve: true
  silent-downgrade:
    allowed: false
```

## 失效条件

- 关键竞争证据过期或被反证。
- 产品定位、目标客户或 Reference Route 改变。
- 主要竞品能力、价格、许可或部署模式发生重大变化。
- Capability Taxonomy major 版本变化。

## 回退与降级

- 证据不足时降级为 unknown，不进行主观补值。
- 比较无法合法公开时保留内部分析并阻断公开 Battlecard。
- 市场边界不清时停止评分，进入产品战略人工评审。

## 下游消费要求

- Batch 2 必须消费产品边界、目标客户、Capability Taxonomy 和 Reference Route。
- 后续转换与数据库 Batch 必须使用 Directional Route Policy。
- 验证 Batch 必须使用 Trust Level Model 和 Claim Evidence 规则。
- 任何销售承诺不得超出 Product Boundary 和当前证据。

# Project Intelligence Graph 规范

## 1. 图层

```text
Code Graph
  File / Module / Package / Symbol / Type / Call / Reference
Architecture Graph
  System / Service / Component / Layer / DeploymentUnit / ExternalSystem
Function Graph
  Domain / Capability / Feature / Page / UseCase
Flow Graph
  Flow / Step / Branch / State / Retry / Compensation
Data Graph
  Database / Table / Column / Entity / Cache / File / Index / Lineage
Integration Graph
  API / Endpoint / Event / Topic / Producer / Consumer / ThirdParty
Security Graph
  Actor / Identity / Role / Permission / TrustBoundary / SensitiveAsset / Threat
Test Graph
  Test / Fixture / Coverage / QualityGate
Evidence Graph
  Claim / Evidence / Inference / Recommendation
```

## 2. 关键关系

- `DEFINES`, `REFERENCES`, `CALLS`, `IMPLEMENTS`, `EXTENDS`
- `CONTAINS`, `DEPENDS_ON`, `DEPLOYED_AS`, `RUNS_ON`
- `EXPOSES`, `CONSUMES_API`, `PRODUCES_EVENT`, `CONSUMES_EVENT`
- `READS`, `WRITES`, `TRANSFORMS`, `CACHES`, `INDEXES`
- `IMPLEMENTS_FEATURE`, `TRIGGERS_FLOW`, `CHANGES_STATE`
- `TESTS`, `COVERS`, `VIOLATES`, `DRIFTS_FROM`
- `SUPPORTED_BY`, `CONTRADICTED_BY`, `INFERRED_FROM`
- `MAPS_TO_SOURCE`, `MAPS_TO_IR`, `MAPS_TO_TARGET`

## 3. Stable ID

推荐：

```text
node_id = hash(
  tenant_id +
  project_id +
  logical_kind +
  language +
  canonical_symbol_or_business_key
)
```

- Revision 变化但逻辑符号未变时尽量保持 ID；
- 文件位置作为 versioned locator，不作为唯一身份；
- 人工业务节点使用显式 UUID；
- 合并/拆分保留 alias 和 lineage。

## 4. 边可信度

| 类型 | 含义 |
|---|---|
| STATIC_EXACT | 编译器/LSP/精确 Schema 确认 |
| STATIC_RULE | 明确框架规则确认 |
| RUNTIME_OBSERVED | 特定环境/窗口观察到 |
| INFERRED_HIGH | 多个独立证据强推断 |
| INFERRED_LOW | 命名/文本等弱推断 |
| MANUAL_CONFIRMED | 用户确认 |
| MANUAL_OVERRIDE | 人工模型覆盖 |

## 5. 图质量指标

- Node evidence coverage；
- Edge evidence coverage；
- Unresolved reference rate；
- Orphan symbol rate；
- Runtime mapping rate；
- Feature traceability coverage；
- Entry-point coverage；
- Stale claim rate；
- Manual override ratio；
- Confidence distribution。

## 6. 查询约束

- 所有查询固定 tenant/project/revision；
- 默认限制深度、节点数和执行时间；
- 大图返回 summary + continuation cursor；
- 权限过滤必须发生在图查询内部或查询结果返回前；
- Graph diff 忽略纯布局变化；
- 查询返回 path explanation 和 evidence refs。

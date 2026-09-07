# Graph Query Contract

## Request

```json
{
  "project_id": "p1",
  "revision_id": "r1",
  "start_nodes": ["symbol:..."],
  "edge_kinds": ["CALLS", "READS", "WRITES"],
  "direction": "out",
  "max_depth": 5,
  "max_nodes": 500,
  "confidence_min": 0.5,
  "include_evidence": true,
  "cursor": null
}
```

租户范围由服务端身份派生，不接受客户端把任意 `tenant_id` 当作授权。

## Response

```json
{
  "nodes": [],
  "edges": [],
  "paths": [],
  "truncated": false,
  "next_cursor": null,
  "quality": {
    "coverage": 0.92,
    "unresolved_edges": 12
  },
  "query_explanation": []
}
```

## Rules

- revision 必填；
- max depth/nodes/time 强制；
- 每条边包含 method/confidence；
- 权限过滤覆盖 node/edge/evidence；
- truncation 明确；
- 非 diff/comparison 查询不得混合 revision。

## Debug runtime projections

The graph query layer may expose revision-scoped `DebugSession`, `StackFrame`, `RuntimeSideEffect`, `LearningMission`, `ReplayBundle` and `SemanticDivergence` projections. Runtime nodes are ephemeral or retention-bound and must never bypass source-code/data permissions.

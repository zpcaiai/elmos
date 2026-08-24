# P02 公共接口与兼容合同

## 1. 设计规则

- 公共接口使用 OpenAPI/JSON Schema/Protobuf 或语言无关 IDL；内部类不作为跨包合同。
- 所有请求携带 `tenant_id`、`project_id`、`correlation_id`、`policy_revision`、`source_revision` 和 idempotency key（适用时）。
- 所有结果携带 `status`、稳定错误码、可读 reason、evidence refs、retryability 和 contract version。
- 新增 optional 字段可向后兼容；删除、改义、收紧枚举、改变默认值必须升 major 并提供 migration。
- 不能支持的能力返回 typed unsupported error，禁止 accept-then-ignore。

## 2. 核心接口

| 接口 | 输入 | 输出 | 稳定错误码 |
| --- | --- | --- | --- |
| RepositoryScanner.scan | repository snapshot + scan policy | inventory snapshot + blind spots | UNSUPPORTED_BUILD / ACCESS_DENIED |
| SemanticIndexer.index | inventory + language packs | symbol/AST index | PARSE_PARTIAL / VERSION_UNSUPPORTED |
| GraphBuilder.build | indexes + configs + traces | versioned repository graph | GRAPH_INCONSISTENT |
| SemanticIR.compile | repository graph + normalization profile | IR snapshot + diagnostics | SEMANTIC_CONFLICT |
| CapabilityDiscovery.discover | IR + archetype hints | Capability Ledger candidate set | DISCOVERY_INCOMPLETE |
| RepoQuery.execute | snapshot id + typed graph query | bounded result + provenance | QUERY_TOO_EXPENSIVE |

## 3. 通用请求信封

```json
{
  "contract_version": "1.0",
  "tenant_id": "t-001",
  "project_id": "p-001",
  "correlation_id": "c-001",
  "idempotency_key": "job-001:attempt-1:operation",
  "policy_revision": "sha256:...",
  "source_revision": "git:...",
  "payload": {}
}
```

## 4. 通用结果信封

```json
{
  "contract_version": "1.0",
  "status": "succeeded",
  "result": {},
  "warnings": [],
  "evidence_refs": ["evidence://sha256/..."],
  "error": null,
  "retry": {"retryable": false, "after_ms": null}
}
```

## 5. 幂等与并发

- 具有外部副作用的操作必须要求 idempotency key，并保存 request hash 与已结算 outcome。
- 同 key + 不同 request hash 返回 `IDEMPOTENCY_CONFLICT`。
- 资源更新使用 expected revision；冲突返回 `REVISION_CONFLICT`，不得 last-write-wins。
- 长任务返回稳定 run/task id；客户端通过事件或查询获取进度，不依赖长 HTTP 连接。

## 6. Adapter Conformance

每个外部 Adapter 必须证明：能力发现、错误转换、取消、超时、事件顺序、usage/cost、权限、数据政策、重复调用、部分响应和版本升级行为符合 Elmos 合同。

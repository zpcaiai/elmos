const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "RepositoryOrchestratorWorkbench",
  "title": "/5",
  "role": "workbench",
  "source": {
    "file": "app/orchestration/RepositoryOrchestratorWorkbench.tsx",
    "componentName": "RepositoryOrchestratorWorkbench",
    "sha256": "sha256:1743a60296e6221e75adc6c14b3ca8dd592f9830b84e3818aae86db293d34380",
    "range": {
      "start": 1677,
      "end": 19957
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE",
    "reason": "state result.dag.tasks element has unsupported type \"unknown\"",
    "category": "data-contracts"
  },
  "props": [],
  "states": [
    {
      "name": "catalog",
      "type": "RepositoryModelCatalog | null"
    },
    {
      "name": "catalogError",
      "type": "string | null"
    },
    {
      "name": "loading",
      "type": "inferred"
    },
    {
      "name": "mode",
      "type": "Mode"
    },
    {
      "name": "selectedModel",
      "type": "string | null"
    },
    {
      "name": "fallbackEnabled",
      "type": "inferred"
    },
    {
      "name": "optimizationProfile",
      "type": "RepositoryPreflightRequest[\"optimizationProfile\"]"
    },
    {
      "name": "verificationPolicy",
      "type": "RepositoryPreflightRequest[\"verificationPolicy\"]"
    },
    {
      "name": "risk",
      "type": "RepositoryRiskProfile"
    },
    {
      "name": "result",
      "type": "RepositoryPreflightResult | null"
    },
    {
      "name": "preflightError",
      "type": "string | null"
    },
    {
      "name": "submitting",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useState",
    "useEffect",
    "useMemo"
  ],
  "resources": [
    "NETWORK"
  ],
  "apiPaths": [
    "/api/repository-orchestrator/models",
    "/api/repository-orchestrator/preflight"
  ],
  "labels": [
    "/5",
    "/api/repository-orchestrator/models",
    "/api/repository-orchestrator/preflight",
    "1.0",
    "784 路线精确语义重写",
    "AST 抽象树提取与依赖图",
    "Action Cache: ENABLED (SHA-256 CAS)",
    "CERTIFIED",
    "CLI 一键触发命令：",
    "Content-Type",
    "Cost",
    "DAG 就绪度",
    "ELMOS v3.0.0",
    "FUZZ_PASSED",
    "FinOps 计量",
    "GET",
    "INGESTED",
    "INTERACTIVE PIPELINE SANDBOX",
    "Immutable selection ·",
    "METERED",
    "Merkle 防篡改数字防伪",
    "POST",
    "Planning only",
    "Polyglot 语义转换"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "RepositoryOrchestratorWorkbench:source-blocker"
  ],
  "irDigest": "sha256:33c0dd69c64fe4ca7687dc78507e5026bd0e277542d542c48d11a2635370939b"
}));

const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "CommercializationConsole",
  "title": "/api/capabilities/product",
  "role": "workbench",
  "source": {
    "file": "app/commercialization/CommercializationConsole.tsx",
    "componentName": "CommercializationConsole",
    "sha256": "sha256:ee51fb034a155dbcd446de5ee5d6cfe9e0b07ff3c400a0858f427edc401e0e64",
    "range": {
      "start": 3107,
      "end": 14357
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
    "reason": "expression kind CallExpression is outside certified-component-v1",
    "category": "effects-and-resources"
  },
  "props": [],
  "states": [
    {
      "name": "payload",
      "type": "ProductCapabilityResponse"
    },
    {
      "name": "selected",
      "type": "inferred"
    },
    {
      "name": "refreshing",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useState",
    "useCallback",
    "useEffect"
  ],
  "resources": [
    "UNKNOWN"
  ],
  "apiPaths": [
    "/api/capabilities/product"
  ],
  "labels": [
    "/api/capabilities/product",
    "1,351 Skills",
    "1,351 Skills Total",
    "18 个 Batches (A–R)",
    "2-digit",
    "41 大能力 Pack (v3.0.0)",
    "784 Routes",
    "8 (K1–K8)",
    "85 个商业扩展 Skills",
    "ASSURANCE QUEUE",
    "ArrowLeft",
    "ArrowRight",
    "B37",
    "BLOCKED",
    "COMMERCIAL CAPABILITY KERNELS (K1–K8)",
    "CURRENT DECISION",
    "ENFORCED",
    "ENTERPRISE COMMERCIAL CONTROL PLANE · v3.0.0",
    "End",
    "FALSE",
    "FOUNDRY v3.0.0 ECOSYSTEM",
    "Foundry 知识库",
    "Gate / Human",
    "Home"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "CommercializationConsole:source-blocker"
  ],
  "irDigest": "sha256:ecd9b1c3cf1d208565f9b18668baad2a548fd9e8e1b2e284b826b63c30797023"
}));

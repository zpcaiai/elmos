const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "PricingPage",
  "title": "/api/pricing",
  "role": "shell",
  "source": {
    "file": "app/pricing/page.tsx",
    "componentName": "PricingPage",
    "sha256": "sha256:89fe2fda31ee4263c106c1011e815e849b27da2831658d3faf97f6c9c14b363d",
    "range": {
      "start": 467,
      "end": 6497
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
    "reason": "expression kind CallExpression is outside certified-component-v1",
    "category": "effects-and-resources"
  },
  "props": [],
  "states": [],
  "hooks": [],
  "resources": [],
  "apiPaths": [
    "/api/pricing"
  ],
  "labels": [
    "/api/pricing",
    "/commercialization",
    "/月，比连续月付节省 ¥258.00",
    "14 天",
    "14 天总额",
    "BILLING GUARDRAILS",
    "CONFIGURED",
    "Credit 扣减表",
    "ELMOS SELF-SERVE · CNY",
    "MONTHLY",
    "PLANS",
    "PUBLISHED",
    "Token 与 Credit 如何扣减",
    "Token 衡量模型实际推理量；Credit 衡量 ELMOS 的分析、隔离执行和验证资源。 使用模型的工作会同时扣减已确认 token 与对应操作 credits。",
    "USAGE METER",
    "VALIDATED",
    "_blank",
    "arrow",
    "cell",
    "check",
    "clock",
    "columnheader",
    "credit-meter-title",
    "credits"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-css-module-token-map-v1",
    "wechat-named-slot-projection-v1",
    "wechat-plain-collection-projection-v1"
  ],
  "obligations": [
    "PricingPage:source-blocker"
  ],
  "irDigest": "sha256:b976458d5c83a83e2a09aea2510478fe06f3730b8c0f86550a3d637beb63363a"
}));

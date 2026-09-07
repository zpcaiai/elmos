const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "PlanBillingAction",
  "title": "/api/billing/checkout",
  "role": "workbench",
  "source": {
    "file": "app/pricing/BillingActions.tsx",
    "componentName": "PlanBillingAction",
    "sha256": "sha256:f8886c700e43d4769668a30e60a5a02c8e801ccf7b8d3897e5ff16ef68f60e29",
    "range": {
      "start": 2759,
      "end": 6451
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
    "reason": "expression kind CallExpression is outside certified-component-v1",
    "category": "effects-and-resources"
  },
  "props": [
    {
      "name": "orderable",
      "type": "boolean",
      "optional": false
    },
    {
      "name": "plan",
      "type": "PricingPlan",
      "optional": false
    }
  ],
  "states": [
    {
      "name": "pending",
      "type": "inferred"
    },
    {
      "name": "message",
      "type": "inferred"
    },
    {
      "name": "failed",
      "type": "inferred"
    },
    {
      "name": "qrCode",
      "type": "{ svg: string; planId: string } | null"
    }
  ],
  "hooks": [
    "useRef",
    "useState"
  ],
  "resources": [],
  "apiPaths": [
    "/api/billing/checkout",
    "/api/billing/trial"
  ],
  "labels": [
    "/api/billing/checkout",
    "/api/billing/trial",
    "Content-Type",
    "Idempotency-Key",
    "POST",
    "WECHAT_PAY_NATIVE",
    "alert",
    "application/json",
    "arrow",
    "button",
    "button-primary",
    "button-secondary",
    "checkout",
    "clock",
    "elmos-free-trial",
    "elmos:billing-changed",
    "https:",
    "same-origin",
    "status",
    "trial",
    "weixin://wxpay/bizpayurl?",
    "二维码生成失败，请重试或改用其它支付方式。",
    "套餐操作暂时无法完成。",
    "安全结账"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "PlanBillingAction:source-blocker"
  ],
  "irDigest": "sha256:556f5fae22e727a8251d38eddb6c52d5ec584e93cbf5bbf3b1ef121804e22ad8"
}));

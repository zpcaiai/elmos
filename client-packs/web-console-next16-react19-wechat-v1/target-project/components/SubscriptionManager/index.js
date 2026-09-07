const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "SubscriptionManager",
  "title": "/api/billing/cancel",
  "role": "workbench",
  "source": {
    "file": "app/pricing/BillingActions.tsx",
    "componentName": "SubscriptionManager",
    "sha256": "sha256:f8886c700e43d4769668a30e60a5a02c8e801ccf7b8d3897e5ff16ef68f60e29",
    "range": {
      "start": 6453,
      "end": 10292
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
      "name": "subscription",
      "type": "Subscription | null"
    },
    {
      "name": "state",
      "type": "\"LOADING\" | \"READY\" | \"EMPTY\" | \"AUTH\" | \"UNAVAILABLE\""
    },
    {
      "name": "confirming",
      "type": "inferred"
    },
    {
      "name": "pending",
      "type": "inferred"
    },
    {
      "name": "message",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useRef",
    "useState",
    "useCallback",
    "useEffect"
  ],
  "resources": [
    "SUBSCRIPTION"
  ],
  "apiPaths": [
    "/api/billing/cancel",
    "/api/billing/subscription"
  ],
  "labels": [
    "/api/billing/cancel",
    "/api/billing/subscription",
    "ACTIVE_SUBSCRIPTION_NOT_FOUND",
    "AUTH",
    "EMPTY",
    "Idempotency-Key",
    "LOADING",
    "POST",
    "READY",
    "UNAVAILABLE",
    "button",
    "button button-primary",
    "button button-secondary",
    "cancel",
    "elmos:billing-changed",
    "no-store",
    "same-origin",
    "status",
    "· 已安排到期取消",
    "保留订阅",
    "到期取消",
    "当前没有有效套餐，可先开通一次免费体验。",
    "当前订阅",
    "正在提交…"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "SubscriptionManager:source-blocker"
  ],
  "irDigest": "sha256:b0af121a8fb782be13f0f14e7b62b3ede280f59bc68aaa16437cb4f0bff12598"
}));

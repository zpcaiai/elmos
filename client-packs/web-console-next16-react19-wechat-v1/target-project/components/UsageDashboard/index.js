const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "UsageDashboard",
  "title": "/api/usage/alerts",
  "role": "chart",
  "source": {
    "file": "app/pricing/UsageDashboard.tsx",
    "componentName": "UsageDashboard",
    "sha256": "sha256:13a07e674998e609a1dc106fc3cf96562f65fab44c27414a8b9990b98b216533",
    "range": {
      "start": 4460,
      "end": 22406
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL",
    "reason": "state initializer expression kind ConditionalExpression is not a closed literal",
    "category": "effects-and-resources"
  },
  "props": [
    {
      "name": "allowLocalCredentials",
      "type": "boolean",
      "optional": true
    },
    {
      "name": "emailAlertsEnabled",
      "type": "boolean",
      "optional": true
    }
  ],
  "states": [
    {
      "name": "form",
      "type": "Credentials"
    },
    {
      "name": "session",
      "type": "Session | null"
    },
    {
      "name": "readState",
      "type": "ReadState"
    },
    {
      "name": "insights",
      "type": "InsightsState"
    },
    {
      "name": "savingAlerts",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useState",
    "useEffect",
    "useMemo"
  ],
  "resources": [
    "NETWORK",
    "SUBSCRIPTION",
    "TIMER"
  ],
  "apiPaths": [
    "/api/usage/alerts",
    "/api/usage/current"
  ],
  "labels": [
    "/api/usage/alerts",
    "/api/usage/current",
    "AbortError",
    "CURRENT",
    "Content-Type",
    "Credit",
    "DAY",
    "DETAILS & ALERTS",
    "ERROR",
    "GET",
    "LIVE USAGE",
    "NOT_CONFIGURED",
    "PARTIAL",
    "PUT",
    "STALE",
    "Token",
    "Token 类别",
    "USAGE_ALERT_SAVE_FAILED",
    "USAGE_INSIGHTS_UNAVAILABLE",
    "USAGE_RESPONSE_CONTRACT_INVALID",
    "USAGE_TRANSPORT_ERROR",
    "[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
    "account",
    "alert"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "UsageDashboard:source-blocker"
  ],
  "irDigest": "sha256:14074f952b6ebd6d830acd06d46d8966720a4ec0945544065593c057017b9bd6"
}));

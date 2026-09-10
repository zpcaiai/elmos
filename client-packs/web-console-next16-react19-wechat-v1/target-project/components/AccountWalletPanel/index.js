const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "AccountWalletPanel",
  "title": "/api/wallet",
  "role": "workbench",
  "source": {
    "file": "app/account/AccountWalletPanel.tsx",
    "componentName": "AccountWalletPanel",
    "sha256": "sha256:200579d81e50f84e976dca0b711d7dfbc01da52b71a34ea99534828b8147a215",
    "range": {
      "start": 2113,
      "end": 11234
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
      "name": "wallet",
      "type": "WalletView | null"
    },
    {
      "name": "ledger",
      "type": "LedgerEntry[]"
    },
    {
      "name": "handoff",
      "type": "TopupHandoff | null"
    },
    {
      "name": "amountYuan",
      "type": "inferred"
    },
    {
      "name": "feedback",
      "type": "inferred"
    },
    {
      "name": "failure",
      "type": "inferred"
    },
    {
      "name": "busy",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useAccountSession",
    "useState",
    "useRef",
    "useCallback",
    "useEffect"
  ],
  "resources": [
    "UNKNOWN",
    "NETWORK",
    "TIMER"
  ],
  "apiPaths": [
    "/api/wallet",
    "/api/wallet/ledger?limit=50",
    "/api/wallet/topup"
  ],
  "labels": [
    "/api/wallet",
    "/api/wallet/ledger?limit=50",
    "/api/wallet/topup",
    "0 0 4px",
    "100",
    "ACTIVE",
    "CREDIT",
    "CREDITED",
    "Content-Type",
    "EXPIRED",
    "Idempotency-Key",
    "PAID",
    "POST",
    "WALLET_UNAVAILABLE",
    "WALLET_UNREACHABLE",
    "_blank",
    "alert",
    "application/json",
    "authenticated",
    "button",
    "button primary",
    "decimal",
    "no-store",
    "noopener noreferrer"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "AccountWalletPanel:source-blocker"
  ],
  "irDigest": "sha256:7a11936e2334fada2c035f94fe8de2fe7cd56976df129252642509ddea86cd65"
}));

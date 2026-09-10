const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "PlatformWalletPanel",
  "title": "(未回传编号)",
  "role": "table",
  "source": {
    "file": "app/admin/PlatformWalletPanel.tsx",
    "componentName": "PlatformWalletPanel",
    "sha256": "sha256:264530e63449713173afb307dd119d8d7d557ef0e6765879579b950df1e79c80",
    "range": {
      "start": 2475,
      "end": 17277
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE",
    "reason": "state wallets element.balanceMinor has unsupported type \"Amount\"",
    "category": "data-contracts"
  },
  "props": [
    {
      "name": "canAdjust",
      "type": "boolean",
      "optional": false
    }
  ],
  "states": [
    {
      "name": "wallets",
      "type": "WalletRow[]"
    },
    {
      "name": "topups",
      "type": "TopupRow[]"
    },
    {
      "name": "loaded",
      "type": "inferred"
    },
    {
      "name": "expanded",
      "type": "inferred"
    },
    {
      "name": "ledger",
      "type": "LedgerRow[]"
    },
    {
      "name": "ledgerBusy",
      "type": "inferred"
    },
    {
      "name": "denial",
      "type": "inferred"
    },
    {
      "name": "notice",
      "type": "inferred"
    },
    {
      "name": "busy",
      "type": "inferred"
    },
    {
      "name": "target",
      "type": "inferred"
    },
    {
      "name": "amountYuan",
      "type": "inferred"
    },
    {
      "name": "direction",
      "type": "\"CREDIT\" | \"DEBIT\""
    },
    {
      "name": "reason",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useState",
    "useRef",
    "useCallback"
  ],
  "resources": [],
  "apiPaths": [
    "/api/admin/topups?limit=50",
    "/api/admin/wallets/adjust",
    "/api/admin/wallets?limit=100"
  ],
  "labels": [
    "(未回传编号)",
    "/api/admin/topups?limit=50",
    "/api/admin/wallets/adjust",
    "/api/admin/wallets?limit=100",
    "100.00",
    "ACTIVE",
    "ADJUSTMENT_AMOUNT_INVALID",
    "ADJUSTMENT_RESULT_UNKNOWN",
    "CREDIT",
    "Content-Type",
    "DEBIT",
    "LEDGER",
    "MANUAL ADJUSTMENT",
    "PAID",
    "PLATFORM WALLETS",
    "PLATFORM_LEDGER_UNREACHABLE",
    "PLATFORM_WALLETS_UNREACHABLE",
    "POST",
    "TOP-UP RECONCILIATION",
    "[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
    "alert",
    "application/json",
    "button",
    "check"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-scroll-row-table-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "PlatformWalletPanel:source-blocker"
  ],
  "irDigest": "sha256:609e94c7a01f496091bf1b14b02288951552cc1d9cb35d65c62a5cbf13bf6f47"
}));

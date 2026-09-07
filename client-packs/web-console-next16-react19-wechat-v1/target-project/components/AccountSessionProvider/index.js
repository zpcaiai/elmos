const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "AccountSessionProvider",
  "title": "/api/auth/logout",
  "role": "provider",
  "source": {
    "file": "app/components/AccountSessionProvider.tsx",
    "componentName": "AccountSessionProvider",
    "sha256": "sha256:5eeb7245de7ee2b85a5fde36819b059a1c2e1e437b5225f1648e2091efec1945",
    "range": {
      "start": 1234,
      "end": 4969
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE",
    "reason": "state status has unsupported type \"AccountSessionState[\\\"status\\\"]\"",
    "category": "data-contracts"
  },
  "props": [
    {
      "name": "children",
      "type": "React.ReactNode",
      "optional": false
    }
  ],
  "states": [
    {
      "name": "status",
      "type": "AccountSessionState[\"status\"]"
    },
    {
      "name": "principal",
      "type": "AccountSessionPrincipal | null"
    },
    {
      "name": "expiresAt",
      "type": "string | null"
    }
  ],
  "hooks": [
    "useState",
    "useCallback",
    "useEffect",
    "useMemo"
  ],
  "resources": [
    "SUBSCRIPTION",
    "NETWORK",
    "TIMER"
  ],
  "apiPaths": [
    "/api/auth/logout",
    "/api/auth/refresh",
    "/api/auth/tenant"
  ],
  "labels": [
    "/api/auth/logout",
    "/api/auth/refresh",
    "/api/auth/tenant",
    "/login",
    "Content-Type",
    "POST",
    "TENANT_SWITCH_REJECTED",
    "anonymous",
    "application/json",
    "authenticated",
    "elmos:account-session-updated",
    "loading",
    "logout",
    "message",
    "not-configured",
    "same-origin",
    "status",
    "storage",
    "tenant-switched",
    "undefined"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-named-slot-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "AccountSessionProvider:source-blocker"
  ],
  "irDigest": "sha256:ba8119cd660e0b55719ea5b2c5bc2d556c8e177029b6f52ecaa10f43289eefa0"
}));

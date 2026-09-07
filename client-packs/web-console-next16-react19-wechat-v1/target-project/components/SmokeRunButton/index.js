const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "SmokeRunButton",
  "title": "/api/smoke/capability",
  "role": "disclosure",
  "source": {
    "file": "app/components/SmokeRunButton.tsx",
    "componentName": "SmokeRunButton",
    "sha256": "sha256:db3b9af0bb07b114d7fba77f72d2022b8a831fcc5d55c637be7689f0b3f43819",
    "range": {
      "start": 1455,
      "end": 17486
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE",
    "reason": "state capability has unsupported type \"SmokeCapabilityResponse\"",
    "category": "data-contracts"
  },
  "props": [
    {
      "name": "projectRef",
      "type": "string",
      "optional": false
    }
  ],
  "states": [
    {
      "name": "capability",
      "type": "SmokeCapabilityResponse | null"
    },
    {
      "name": "pack",
      "type": "SmokePackSummary | null"
    },
    {
      "name": "session",
      "type": "SmokeSession | null"
    },
    {
      "name": "evidence",
      "type": "SmokeEvidenceBundle | null"
    },
    {
      "name": "entry",
      "type": "SmokeEntry | \"\""
    },
    {
      "name": "error",
      "type": "string | null"
    },
    {
      "name": "busy",
      "type": "inferred"
    },
    {
      "name": "remaining",
      "type": "inferred"
    },
    {
      "name": "extendOpen",
      "type": "inferred"
    },
    {
      "name": "extendSeconds",
      "type": "inferred"
    },
    {
      "name": "extendReason",
      "type": "inferred"
    },
    {
      "name": "extendActor",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useState",
    "useRef",
    "useEffect",
    "useCallback",
    "useMemo"
  ],
  "resources": [
    "NETWORK",
    "TIMER"
  ],
  "apiPaths": [
    "/api/smoke/capability",
    "/api/smoke/sessions"
  ],
  "labels": [
    "/api/smoke/capability",
    "/api/smoke/sessions",
    "AVAILABLE",
    "NOT_RUN",
    "POST",
    "SMOKE_ACTION_FAILED",
    "SMOKE_EVIDENCE_FAILED",
    "SMOKE_LOAD_FAILED",
    "STARTING",
    "_blank",
    "absent",
    "application/json",
    "available",
    "button",
    "button button-primary",
    "button button-secondary",
    "content-type",
    "expired",
    "failed",
    "lease-result.json",
    "manual",
    "no-store",
    "noreferrer",
    "result.json"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-controlled-disclosure-v1",
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "SmokeRunButton:source-blocker"
  ],
  "irDigest": "sha256:8462c13edbd2efe5e3092553c9784c9e251f054e65b748c8c688712b311e59e0"
}));

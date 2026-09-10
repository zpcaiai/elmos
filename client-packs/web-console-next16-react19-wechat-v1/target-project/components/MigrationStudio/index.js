const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "MigrationStudio",
  "title": ".NET 10",
  "role": "workbench",
  "source": {
    "file": "app/migration/MigrationStudio.tsx",
    "componentName": "MigrationStudio",
    "sha256": "sha256:af0df409a9921bec3801daa9e7bce63619141ec81ca514c070476f1b25b80b5f",
    "range": {
      "start": 2430,
      "end": 17554
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE",
    "reason": "state view has unsupported type \"StudioView\"",
    "category": "data-contracts"
  },
  "props": [],
  "states": [
    {
      "name": "view",
      "type": "StudioView"
    },
    {
      "name": "query",
      "type": "inferred"
    },
    {
      "name": "statusFilter",
      "type": "inferred"
    },
    {
      "name": "selected",
      "type": "inferred"
    },
    {
      "name": "capabilities",
      "type": "inferred"
    },
    {
      "name": "source",
      "type": "CapabilityResponse<MigrationCapability>[\"source\"]"
    },
    {
      "name": "note",
      "type": "inferred"
    },
    {
      "name": "dialogOpen",
      "type": "inferred"
    },
    {
      "name": "drafts",
      "type": "Draft[]"
    },
    {
      "name": "draftsReady",
      "type": "inferred"
    },
    {
      "name": "draftCapability",
      "type": "string | null"
    },
    {
      "name": "feedback",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useState",
    "useRef",
    "useEffect",
    "useMemo"
  ],
  "resources": [
    "NETWORK",
    "STORAGE",
    "SUBSCRIPTION",
    "TIMER"
  ],
  "apiPaths": [
    "/api/capabilities/database-sql",
    "/api/capabilities/migration"
  ],
  "labels": [
    ".NET 10",
    "/api/capabilities/database-sql",
    "/api/capabilities/migration",
    "/migration/sql",
    "/spring",
    "/translation",
    "12 个本地实验 Profile 已精确验证",
    "47 个 Runtime Skills 和 13 个目标能力目录可发现；78 条路线仍需精确版本、模式、目标适配器、实库与独立证据。",
    "ALL",
    "AngularJS 1.8",
    "BLOCKED",
    "C# / .NET Framework 4.8",
    "ChinaDB 商业迁移扩展已接入",
    "DRAFT",
    "EXPERIMENTAL",
    "Escape",
    "Gate ready",
    "Java 21 / Spring Boot 3",
    "Java 8 / Spring 4",
    "LIVE_API",
    "LOCAL DRAFT",
    "M29",
    "M29–M37 精确分域",
    "M30"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "MigrationStudio:source-blocker",
    "MigrationStudio:effect-cleanup:3376",
    "MigrationStudio:effect-cleanup:3807",
    "MigrationStudio:effect-cleanup:4270"
  ],
  "irDigest": "sha256:bc6e60abd992258487a258d99d55a81ec78998685ca6261fd5800e44f0d0a4bd"
}));

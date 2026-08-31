const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "GovernanceWorkspace",
  "title": "+ Line",
  "role": "workbench",
  "source": {
    "file": "app/governance/GovernanceWorkspace.tsx",
    "componentName": "GovernanceWorkspace",
    "sha256": "sha256:6e4df100ea8494750f34ea97b13567df1002a14e00e44c3f5bf578a961b86e69",
    "range": {
      "start": 1797,
      "end": 9484
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
    "reason": "expression kind ArrowFunction is outside certified-component-v1",
    "category": "effects-and-resources"
  },
  "props": [],
  "states": [
    {
      "name": "activeTab",
      "type": "\"mutation\" | \"api-diff\" | \"cas-cache\""
    },
    {
      "name": "codeSnippet",
      "type": "inferred"
    },
    {
      "name": "isAnalyzing",
      "type": "inferred"
    },
    {
      "name": "cacheStats",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useState"
  ],
  "resources": [],
  "apiPaths": [],
  "labels": [
    "+ Line",
    "- Line",
    "1 处破坏性变更 (Breaking Change)",
    "3 / 4",
    "4 Operators Active",
    "75.0%",
    "API 契约向后兼容漂移差分 (API Diff)",
    "API 契约漂移与向后兼容性报告 (elmos polyglot api-diff)",
    "BREAKING",
    "Bloom Filter Active",
    "CAS 命中加速比",
    "Cache Hit Ratio",
    "ELMOS Governance & Assurance OS",
    "KILLED",
    "L1 Memory Items",
    "Total Cached DAG Units",
    "WARNING",
    "api-diff",
    "bits",
    "cas-cache",
    "database",
    "mutation",
    "play",
    "public int calculateDiscount(int price) {\n  if (price > 100) {\n    return price - 20;\n  }\n  return price;\n}"
  ],
  "adapters": [
    "wechat-css-module-token-map-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "GovernanceWorkspace:source-blocker"
  ],
  "irDigest": "sha256:88e14d52239a3908c82bc344888f33994a589a4ce5067ecb3dd421bbffb82361"
}));

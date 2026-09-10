const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "HelpCenter",
  "title": "/admin",
  "role": "table",
  "source": {
    "file": "app/help/HelpCenter.tsx",
    "componentName": "HelpCenter",
    "sha256": "sha256:3de4e8529ce03968e3b25f2be70bdb289440a398a14c535d25638132ad950498",
    "range": {
      "start": 2240,
      "end": 6556
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT",
    "reason": "expected a `const [x, setX] = useState(...)` declaration",
    "category": "effects-and-resources"
  },
  "props": [],
  "states": [],
  "hooks": [
    "useUiPreferences"
  ],
  "resources": [],
  "apiPaths": [],
  "labels": [
    "/admin",
    "/repositories",
    "01",
    "02",
    "03",
    "04",
    "Area",
    "Choose a business line",
    "Controlled repository delivery",
    "Current local evidence",
    "Evidence and remaining external gates",
    "External boundary",
    "Guidance · Evidence boundaries",
    "Help and readiness",
    "Merge, deployment, infrastructure apply, and production database migration are not automatic effects of this workflow.",
    "Open operations admin",
    "Open repository workspace",
    "Open workspace",
    "Operate and diagnose",
    "Readiness evidence table",
    "button button-primary",
    "col",
    "en",
    "help-admin-title"
  ],
  "adapters": [
    "wechat-effect-resource-lifecycle-v1",
    "wechat-named-slot-projection-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-scroll-row-table-v1"
  ],
  "obligations": [
    "HelpCenter:source-blocker"
  ],
  "irDigest": "sha256:cd58276643bcb76cf4ef9fa7295272e74def1f5aa184303097343c0965db4f24"
}));

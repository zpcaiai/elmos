const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "EventTable",
  "title": "FAILURE",
  "role": "table",
  "source": {
    "file": "app/admin/OperationsAdmin.tsx",
    "componentName": "EventTable",
    "sha256": "sha256:887dfc4ed913566b13192fb8ca4b4a86b6487f501806b3bc31b77183259f390f",
    "range": {
      "start": 92105,
      "end": 93135
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_TAG",
    "reason": "tag \"table\" is outside certified-component-v1",
    "category": "platform-semantics"
  },
  "props": [
    {
      "name": "empty",
      "type": "string",
      "optional": false
    },
    {
      "name": "events",
      "type": "OperationsConsoleView[\"activity\"][\"recentEvents\"]",
      "optional": false
    }
  ],
  "states": [],
  "hooks": [],
  "resources": [],
  "apiPaths": [],
  "labels": [
    "FAILURE",
    "activity",
    "recentEvents",
    "业务线",
    "动作",
    "时间",
    "目标",
    "结果",
    "耗时"
  ],
  "adapters": [
    "wechat-css-module-token-map-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-scroll-row-table-v1"
  ],
  "obligations": [
    "EventTable:source-blocker"
  ],
  "irDigest": "sha256:fb5d04447032bd15651065a550eb6777307cb0ca4544b1986840ab9b4db49991"
}));

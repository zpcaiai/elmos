const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "EvidenceGraph",
  "title": "evidence-edge-details",
  "role": "disclosure",
  "source": {
    "file": "app/components/ProjectEvidenceCharts.tsx",
    "componentName": "EvidenceGraph",
    "sha256": "sha256:ad59776ffb66f5cb0a2844508827422769445969adba9feb4ec0ad8cd97ca77f",
    "range": {
      "start": 5464,
      "end": 7534
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
    "reason": "expression kind NewExpression is outside certified-component-v1",
    "category": "effects-and-resources"
  },
  "props": [
    {
      "name": "description",
      "type": "string",
      "optional": false
    },
    {
      "name": "edges",
      "type": "DisplayGraphEdge[]",
      "optional": false
    },
    {
      "name": "nodes",
      "type": "DisplayGraphNode[]",
      "optional": false
    },
    {
      "name": "status",
      "type": "DisplayStatus",
      "optional": false
    },
    {
      "name": "title",
      "type": "string",
      "optional": false
    }
  ],
  "states": [],
  "hooks": [],
  "resources": [],
  "apiPaths": [],
  "labels": [
    "evidence-edge-details",
    "evidence-graph-card",
    "evidence-graph-layer",
    "evidence-graph-layers",
    "evidence-graph-node",
    "evidence-layer-label",
    "evidence-node-kind",
    "层级",
    "服务端未返回经过校验的结构化图；不会从文件名或日志推断关系。",
    "查看全部关系 ·"
  ],
  "adapters": [
    "wechat-controlled-disclosure-v1",
    "wechat-plain-collection-projection-v1"
  ],
  "obligations": [
    "EvidenceGraph:source-blocker"
  ],
  "irDigest": "sha256:5c7964c10595935a24db931d62d1b73d3206d4858f829a0079dbab56649921ec"
}));

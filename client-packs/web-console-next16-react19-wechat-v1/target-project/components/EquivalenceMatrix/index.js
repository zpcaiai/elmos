const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "EquivalenceMatrix",
  "title": "FAILED",
  "role": "table",
  "source": {
    "file": "app/components/ProjectEvidenceCharts.tsx",
    "componentName": "EquivalenceMatrix",
    "sha256": "sha256:ad59776ffb66f5cb0a2844508827422769445969adba9feb4ec0ad8cd97ca77f",
    "range": {
      "start": 11121,
      "end": 14308
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
    "reason": "expression kind CallExpression is outside certified-component-v1",
    "category": "effects-and-resources"
  },
  "props": [
    {
      "name": "behavior",
      "type": "GenerationBehaviorInsight",
      "optional": false
    },
    {
      "name": "dimension",
      "type": "\"semantic\" | \"behavior\"",
      "optional": false
    }
  ],
  "states": [],
  "hooks": [],
  "resources": [],
  "apiPaths": [],
  "labels": [
    "FAILED",
    "MATRIX_CELL_MISSING",
    "NOT_APPLICABLE",
    "NOT_RUN",
    "NxN ·",
    "NxN 状态矩阵，共",
    "PASSED",
    "SAME_TARGET",
    "UNKNOWN",
    "behavior",
    "behavior_status",
    "col",
    "evidence-matrix",
    "evidence-matrix-panel",
    "evidence-matrix-scroll",
    "region",
    "row",
    "semantic",
    "semantic_status",
    "sr-only",
    "个目标语言",
    "没有可验证的目标语言集合。",
    "源 \\ 目标",
    "直接行为等价"
  ],
  "adapters": [
    "wechat-controlled-disclosure-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-scroll-row-table-v1"
  ],
  "obligations": [
    "EquivalenceMatrix:source-blocker"
  ],
  "irDigest": "sha256:ca75212f87491733a77e44bcf08b7130d0498425eba1d3cf8485845894142c5c"
}));

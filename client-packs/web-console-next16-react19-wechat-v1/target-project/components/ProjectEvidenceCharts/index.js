const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "ProjectEvidenceCharts",
  "title": "NOT_CERTIFIED",
  "role": "chart",
  "source": {
    "file": "app/components/ProjectEvidenceCharts.tsx",
    "componentName": "ProjectEvidenceCharts",
    "sha256": "sha256:ad59776ffb66f5cb0a2844508827422769445969adba9feb4ec0ad8cd97ca77f",
    "range": {
      "start": 15842,
      "end": 19611
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
    "reason": "expression kind CallExpression is outside certified-component-v1",
    "category": "effects-and-resources"
  },
  "props": [
    {
      "name": "insights",
      "type": "GenerationInsights",
      "optional": true
    }
  ],
  "states": [],
  "hooks": [],
  "resources": [],
  "apiPaths": [],
  "labels": [
    "NOT_CERTIFIED",
    "NOT_RUN",
    "PASSED",
    "UNKNOWN",
    "evidence-boundary",
    "evidence-coverage-grid",
    "evidence-dimension",
    "evidence-graph-card",
    "evidence-graph-grid",
    "evidence-heading-statuses",
    "evidence-section-heading",
    "generation-coverage-title",
    "note",
    "project-evidence-charts",
    "project-evidence-title",
    "· 结论上限",
    "· 认证",
    "不会从 package 文件名或构建日志推断依赖完整性。",
    "仅接受服务端校验后的声明依赖",
    "声明依赖图",
    "声明依赖尚未返回",
    "外部验证",
    "多维完成度",
    "完整项目结构"
  ],
  "adapters": [
    "wechat-plain-collection-projection-v1"
  ],
  "obligations": [
    "ProjectEvidenceCharts:source-blocker"
  ],
  "irDigest": "sha256:1e4b05ec3ec13926e34ca1f8f4cabf91d7b3b1c14c4783034c16939817db5ff8"
}));

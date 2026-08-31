const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "ProjectEvidenceCharts",
  "title": "NOT_CERTIFIED",
  "role": "chart",
  "source": {
    "file": "app/components/ProjectEvidenceCharts.tsx",
    "componentName": "ProjectEvidenceCharts",
    "sha256": "sha256:1191ba4343eba89806266218465287a1169f436b763c4214b2a4dfd897e741db",
    "range": {
      "start": 15906,
      "end": 19675
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
  "irDigest": "sha256:969526c9b0040591ad40bc8930283317a03454fdde17346509b185d3f4a140e8"
}));

const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "PlatformJobsPanel",
  "title": "25",
  "role": "table",
  "source": {
    "file": "app/admin/PlatformJobsPanel.tsx",
    "componentName": "PlatformJobsPanel",
    "sha256": "sha256:3233268915de085f38d5e618a88ad6d47793570299b8bc8116bf950f1f837332",
    "range": {
      "start": 2139,
      "end": 7774
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
    "reason": "expression kind CallExpression is outside certified-component-v1",
    "category": "effects-and-resources"
  },
  "props": [],
  "states": [
    {
      "name": "rows",
      "type": "JobRow[]"
    },
    {
      "name": "loaded",
      "type": "inferred"
    },
    {
      "name": "status",
      "type": "string"
    },
    {
      "name": "organization",
      "type": "inferred"
    },
    {
      "name": "denial",
      "type": "inferred"
    },
    {
      "name": "busy",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useState",
    "useCallback"
  ],
  "resources": [],
  "apiPaths": [],
  "labels": [
    "25",
    "ALL",
    "FAILED",
    "LOST",
    "PLATFORM EXECUTION",
    "PLATFORM_JOBS_UNREACHABLE",
    "[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
    "alert",
    "button",
    "database",
    "no-store",
    "organizationId",
    "overline",
    "refresh",
    "search",
    "secondary-button",
    "status",
    "。跨组织任务视图需要平台管理员身份， 与本组织的运营角色是两回事。",
    "业务线",
    "任务",
    "全平台任务执行",
    "全平台任务状态",
    "创建",
    "失败码"
  ],
  "adapters": [
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-scroll-row-table-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "PlatformJobsPanel:source-blocker"
  ],
  "irDigest": "sha256:98b0fba6ae3ccaeead373b86ace7de1d75d82364ba3ad210fef6847c007f41bc"
}));

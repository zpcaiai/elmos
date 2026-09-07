const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "FrontendTransformationStudio",
  "title": "#frt-skill-catalog",
  "role": "disclosure",
  "source": {
    "file": "app/frontend/FrontendTransformationStudio.tsx",
    "componentName": "FrontendTransformationStudio",
    "sha256": "sha256:146c5d65be5d140ada7af4fb9e6a58921cce935e217379f15dd6034ada0b1695",
    "range": {
      "start": 4609,
      "end": 32766
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
      "name": "batch",
      "type": "BatchId | \"ALL\""
    },
    {
      "name": "query",
      "type": "inferred"
    },
    {
      "name": "source",
      "type": "Stack"
    },
    {
      "name": "target",
      "type": "Stack"
    },
    {
      "name": "selectedSkillId",
      "type": "inferred"
    },
    {
      "name": "workspaceId",
      "type": "inferred"
    },
    {
      "name": "projectId",
      "type": "inferred"
    },
    {
      "name": "environmentId",
      "type": "inferred"
    },
    {
      "name": "releaseId",
      "type": "inferred"
    },
    {
      "name": "policyVersion",
      "type": "inferred"
    },
    {
      "name": "risk",
      "type": "\"R0\" | \"R1\" | \"R2\" | \"R3\" | \"R4\" | \"R5\""
    },
    {
      "name": "tenantId",
      "type": "inferred"
    },
    {
      "name": "actorId",
      "type": "inferred"
    },
    {
      "name": "runnerToken",
      "type": "inferred"
    },
    {
      "name": "sourceFiles",
      "type": "Record<string, string>"
    },
    {
      "name": "inputJson",
      "type": "inferred"
    },
    {
      "name": "run",
      "type": "FrtRunView | null"
    },
    {
      "name": "audit",
      "type": "FrtAuditView[\"audit\"]"
    },
    {
      "name": "operationError",
      "type": "inferred"
    },
    {
      "name": "busy",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useUiPreferences",
    "useState",
    "useMemo",
    "useEffect"
  ],
  "resources": [
    "UNKNOWN",
    "TIMER"
  ],
  "apiPaths": [
    "/api/frt/runs"
  ],
  "labels": [
    "#frt-skill-catalog",
    "#route-planner",
    "* EXECUTE 只准备受限提案；客户代码、真实 Provider、设备与生产操作需要外部 Runner 和授权。",
    "/api/frt/runs",
    "1. 运行作用域",
    "2. Skill 类型化输入",
    "30",
    "30 / 30 路线已注册",
    "472",
    "472 implementation-level Skills",
    "472 个实现级 Skill",
    "ALL",
    "ANALYZE",
    "Artifacts",
    "Audit trail",
    "BLOCKED",
    "BLOCKING",
    "Batch Certificate、Production Closure、发布、回滚、客户验收和持续认证不能由页面或模型签发。",
    "Browse every Skill",
    "CANCELLED",
    "Capability",
    "Choose a directed route",
    "Choose an exact directed transformation route",
    "Delivery chain"
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
    "FrontendTransformationStudio:source-blocker"
  ],
  "irDigest": "sha256:74963e51052ef1bfcb96a87db1366450932ce2db12d2d73e5613b87df703a255"
}));

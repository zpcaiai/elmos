const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "PrecisionMigrationJobs",
  "title": "/api/precision-migration/jobs",
  "role": "disclosure",
  "source": {
    "file": "app/skills/PrecisionMigrationJobs.tsx",
    "componentName": "PrecisionMigrationJobs",
    "sha256": "sha256:f02823e4442841704d5832ef16e897dff1906c511ed66d5ccdf0551879bf5e39",
    "range": {
      "start": 730,
      "end": 8620
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
      "name": "skill",
      "type": "inferred"
    },
    {
      "name": "mode",
      "type": "inferred"
    },
    {
      "name": "workspacePath",
      "type": "inferred"
    },
    {
      "name": "runnerToken",
      "type": "inferred"
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
      "name": "job",
      "type": "PrecisionJob | null"
    },
    {
      "name": "busy",
      "type": "inferred"
    },
    {
      "name": "error",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useState",
    "useCallback",
    "useEffect"
  ],
  "resources": [
    "TIMER"
  ],
  "apiPaths": [
    "/api/precision-migration/jobs"
  ],
  "labels": [
    "/api/precision-migration/jobs",
    "ARTIFACT_DOWNLOAD_FAILED",
    "DELETE",
    "JOB_STATUS_FAILED",
    "JOB_SUBMIT_FAILED",
    "Job ID",
    "NOT_RUN",
    "POST",
    "Runtime Skill",
    "TENANT-ISOLATED RUNNER",
    "UI 只能触发清单中的受控 handler；缺少精确原生或外部能力时会失败关闭，不会执行请求携带的命令。",
    "alert",
    "application/json",
    "assess",
    "block",
    "business-actions",
    "button",
    "button button-primary",
    "button button-secondary",
    "bytes",
    "cancel",
    "card-heading",
    "certify",
    "content-type"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-controlled-disclosure-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "PrecisionMigrationJobs:source-blocker"
  ],
  "irDigest": "sha256:23a4e5936dc429cad61170eb401c9431bb2461d966a8cb73d50f088ca2f7874f"
}));

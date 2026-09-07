const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "MultimodalIntakeWorkbench",
  "title": "0.5",
  "role": "workbench",
  "source": {
    "file": "app/intake/MultimodalIntakeWorkbench.tsx",
    "componentName": "MultimodalIntakeWorkbench",
    "sha256": "sha256:2116ac344e8bff9551f28388582ad926d9f4a0f8d8a3a4d6caaa6999c3f1c8ac",
    "range": {
      "start": 84136,
      "end": 237658
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
      "name": "projectId",
      "type": "inferred"
    },
    {
      "name": "directText",
      "type": "inferred"
    },
    {
      "name": "assets",
      "type": "AssetDraft[]"
    },
    {
      "name": "recoveryRecordCount",
      "type": "inferred"
    },
    {
      "name": "legacyRecoveryCount",
      "type": "inferred"
    },
    {
      "name": "recoveryStoreReady",
      "type": "inferred"
    },
    {
      "name": "recoveryStoreError",
      "type": "inferred"
    },
    {
      "name": "busy",
      "type": "inferred"
    },
    {
      "name": "reviewBusy",
      "type": "inferred"
    },
    {
      "name": "feedback",
      "type": "inferred"
    },
    {
      "name": "treeQuery",
      "type": "inferred"
    },
    {
      "name": "packagePreview",
      "type": "SkillResponse | null"
    },
    {
      "name": "packagePage",
      "type": "ProjectPackagePage | null"
    },
    {
      "name": "packagePageCursors",
      "type": "Array<string | null>"
    },
    {
      "name": "packagePageIndex",
      "type": "inferred"
    },
    {
      "name": "estimate",
      "type": "ProcessingEstimate | null"
    },
    {
      "name": "estimateBusy",
      "type": "inferred"
    },
    {
      "name": "correction",
      "type": "inferred"
    },
    {
      "name": "correctionTouched",
      "type": "inferred"
    },
    {
      "name": "correctionTarget",
      "type": "inferred"
    },
    {
      "name": "reviewTasks",
      "type": "ReviewTask[]"
    },
    {
      "name": "reviewSources",
      "type": "ReviewSource[]"
    },
    {
      "name": "selectedReviewSourceKey",
      "type": "inferred"
    },
    {
      "name": "selectedReviewTaskId",
      "type": "inferred"
    },
    {
      "name": "reviewTargetKind",
      "type": "ReviewTargetKind"
    },
    {
      "name": "reviewTargetLocator",
      "type": "inferred"
    },
    {
      "name": "reviewOriginalValue",
      "type": "inferred"
    },
    {
      "name": "reviewConfidence",
      "type": "inferred"
    },
    {
      "name": "reviewReason",
      "type": "inferred"
    },
    {
      "name": "reviewPropagation",
      "type": "SkillResponse | null"
    },
    {
      "name": "reviewCurrentCorrection",
      "type": "Record<string, unknown> | null"
    },
    {
      "name": "reviewClaims",
      "type": "Record<string, ReviewClaim>"
    },
    {
      "name": "reviewIdentityScope",
      "type": "inferred"
    },
    {
      "name": "legacyReviewClaimDiscarded",
      "type": "inferred"
    },
    {
      "name": "reviewEnqueueRecoveryCount",
      "type": "inferred"
    },
    {
      "name": "reviewEnqueueRecoveryError",
      "type": "inferred"
    },
    {
      "name": "reviewClock",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useAccountSession",
    "useState",
    "useMemo",
    "useMicrophoneRecorder",
    "useRef",
    "useCallback",
    "useLayoutEffect",
    "useEffect"
  ],
  "resources": [
    "UNKNOWN",
    "STORAGE",
    "TIMER",
    "SUBSCRIPTION"
  ],
  "apiPaths": [],
  "labels": [
    "0.5",
    "01 · SESSION",
    "02 · PACKAGE REVIEW",
    "03 · HUMAN REVIEW",
    "APPLY",
    "APPROVED",
    "ASSET_IDENTITY_COLLISION",
    "ASSET_ID_CHANGED",
    "ASSET_ID_MISSING",
    "ASSET_PERMANENTLY_BLOCKED",
    "ASSET_PROJECT_BINDING_MISMATCH",
    "ASSET_VERSION_REQUIRED_FOR_CORRECTION",
    "BATCH_ASSET_COUNT_LIMIT_EXCEEDED",
    "BATCH_BYTE_LIMIT_EXCEEDED",
    "BBOX",
    "BFF 作用域已验证；重新校验内容后从确认分片继续。",
    "BLOCKED",
    "CANCELLED",
    "CLAIMED",
    "CODE_IMPLEMENTED_LOCAL",
    "COMPLETED",
    "CONFLICT",
    "CORRECTION_APPLIED_RECOVERY_CLEANUP_FAILED",
    "CORRECTION_FAILED"
  ],
  "adapters": [
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "MultimodalIntakeWorkbench:source-blocker",
    "MultimodalIntakeWorkbench:effect-cleanup:93593"
  ],
  "irDigest": "sha256:ea417819e48dc1680b5bdce62da2dc21842731d7f9a8da6a76a79f247992013f"
}));

const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "ProjectGenerationStudio",
  "title": "--:--",
  "role": "disclosure",
  "source": {
    "file": "app/generation/ProjectGenerationStudio.tsx",
    "componentName": "ProjectGenerationStudio",
    "sha256": "sha256:42160731ba1beea98e4bc4cafe94a3cb9e648b6b944abaa9f084808ef560b751",
    "range": {
      "start": 9032,
      "end": 72424
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
      "name": "name",
      "type": "inferred"
    },
    {
      "name": "namespace",
      "type": "inferred"
    },
    {
      "name": "description",
      "type": "inferred"
    },
    {
      "name": "entity",
      "type": "inferred"
    },
    {
      "name": "reviewer",
      "type": "inferred"
    },
    {
      "name": "targets",
      "type": "GenerationTargetId[]"
    },
    {
      "name": "persistence",
      "type": "\"in-memory\" | \"postgresql\""
    },
    {
      "name": "authMode",
      "type": "\"none\" | \"jwt\" | \"oidc\""
    },
    {
      "name": "sourceUrl",
      "type": "inferred"
    },
    {
      "name": "sourceSkills",
      "type": "inferred"
    },
    {
      "name": "repositoryWorkspaceId",
      "type": "inferred"
    },
    {
      "name": "repositoryPaths",
      "type": "inferred"
    },
    {
      "name": "sourceFiles",
      "type": "File[]"
    },
    {
      "name": "sourceBundle",
      "type": "GenerationSourceBundle | null"
    },
    {
      "name": "sourceBusy",
      "type": "inferred"
    },
    {
      "name": "draft",
      "type": "GenerationDraft | null"
    },
    {
      "name": "savedDrafts",
      "type": "GenerationDraft[]"
    },
    {
      "name": "draftsReady",
      "type": "inferred"
    },
    {
      "name": "capability",
      "type": "GenerationCapabilityResponse | null"
    },
    {
      "name": "capabilityError",
      "type": "inferred"
    },
    {
      "name": "runnerReadiness",
      "type": "RunnerReadiness | null"
    },
    {
      "name": "tenantId",
      "type": "inferred"
    },
    {
      "name": "runnerToken",
      "type": "inferred"
    },
    {
      "name": "analysis",
      "type": "GenerationAnalysis | null"
    },
    {
      "name": "approved",
      "type": "inferred"
    },
    {
      "name": "job",
      "type": "GenerationJob | null"
    },
    {
      "name": "recoveryJobId",
      "type": "inferred"
    },
    {
      "name": "runnerBusy",
      "type": "inferred"
    },
    {
      "name": "runtimeLanguage",
      "type": "GenerationTargetId"
    },
    {
      "name": "runtimePreviewPayload",
      "type": "unknown"
    },
    {
      "name": "githubOwner",
      "type": "inferred"
    },
    {
      "name": "githubRepositoryName",
      "type": "inferred"
    },
    {
      "name": "githubToken",
      "type": "inferred"
    },
    {
      "name": "githubConfirmed",
      "type": "inferred"
    },
    {
      "name": "githubBusy",
      "type": "inferred"
    },
    {
      "name": "githubIdempotencyKey",
      "type": "inferred"
    },
    {
      "name": "feedback",
      "type": "inferred"
    },
    {
      "name": "targetError",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useAccountSession",
    "useState",
    "useRef",
    "useEffect",
    "useMemo"
  ],
  "resources": [
    "UNKNOWN",
    "NETWORK",
    "NAVIGATION",
    "STORAGE",
    "TIMER"
  ],
  "apiPaths": [
    "/api/capabilities/generation",
    "/api/generation/analyze",
    "/api/generation/jobs",
    "/api/generation/sources",
    "/api/health?probe=readiness"
  ],
  "labels": [
    "--:--",
    ".git",
    "/ 50",
    "/api/capabilities/generation",
    "/api/generation/analyze",
    "/api/generation/jobs",
    "/api/generation/sources",
    "/api/health?probe=readiness",
    "01 / 02",
    "02 / 02",
    "1.0.0",
    "1.1.0",
    "8 个独立 emitter / verifier",
    "ARTIFACT_INTEGRITY_MISMATCH",
    "ARTIFACT_TICKET_IDENTITY_MISMATCH",
    "AbortError",
    "Authorization",
    "B46–B80 结构化能力",
    "BLOCKED",
    "CANCELLED",
    "CHECKING",
    "COMPLETED",
    "Content-Type",
    "DRAFT"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-controlled-disclosure-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "ProjectGenerationStudio:source-blocker",
    "ProjectGenerationStudio:effect-cleanup:15221",
    "ProjectGenerationStudio:effect-cleanup:16400",
    "ProjectGenerationStudio:effect-cleanup:17122"
  ],
  "irDigest": "sha256:99682a932552f3b96deb4994d6e40867660c1f267826e6922212c63512df3152"
}));

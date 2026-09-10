const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "TranslationStudio",
  "title": "\"\"",
  "role": "disclosure",
  "source": {
    "file": "app/translation/TranslationStudio.tsx",
    "componentName": "TranslationStudio",
    "sha256": "sha256:a3e4f64b8aab2060dc23ffd3ece9772eb0512c61f28ba35175bda4092fe87124",
    "range": {
      "start": 6082,
      "end": 56137
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
      "name": "sourceLanguage",
      "type": "TranslationLanguageId"
    },
    {
      "name": "targetLanguage",
      "type": "TranslationLanguageId"
    },
    {
      "name": "repositoryRef",
      "type": "inferred"
    },
    {
      "name": "scope",
      "type": "Handoff[\"scope\"]"
    },
    {
      "name": "handoff",
      "type": "Handoff | null"
    },
    {
      "name": "repositoryPlan",
      "type": "TranslationRepositoryPlan | null"
    },
    {
      "name": "discovery",
      "type": "TranslationDiscoveryReport | null"
    },
    {
      "name": "workUnitFilter",
      "type": "inferred"
    },
    {
      "name": "workUnitPage",
      "type": "inferred"
    },
    {
      "name": "capability",
      "type": "TranslationCapabilityResponse | null"
    },
    {
      "name": "capabilityError",
      "type": "inferred"
    },
    {
      "name": "importing",
      "type": "inferred"
    },
    {
      "name": "feedback",
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
      "name": "runnerToken",
      "type": "inferred"
    },
    {
      "name": "workspaceId",
      "type": "inferred"
    },
    {
      "name": "repositoryWorkspaceId",
      "type": "inferred"
    },
    {
      "name": "casesBundleId",
      "type": "inferred"
    },
    {
      "name": "recoveryJobId",
      "type": "inferred"
    },
    {
      "name": "runnerHealth",
      "type": "TranslationRunnerHealth | null"
    },
    {
      "name": "job",
      "type": "TranslationJob | null"
    },
    {
      "name": "jobBusy",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useAccountSession",
    "useState",
    "useEffect",
    "useMemo"
  ],
  "resources": [
    "UNKNOWN",
    "NAVIGATION",
    "NETWORK",
    "STORAGE",
    "TIMER"
  ],
  "apiPaths": [
    "/api/capabilities/translation",
    "/api/translation/discovery-report",
    "/api/translation/health",
    "/api/translation/jobs",
    "/api/translation/repository-plan"
  ],
  "labels": [
    "\"\"",
    "/api/capabilities/translation",
    "/api/translation/discovery-report",
    "/api/translation/health",
    "/api/translation/jobs",
    "/api/translation/repository-plan",
    "1 · 源语言",
    "1.1.0",
    "2 · 目标语言",
    "<SAFE_REPOSITORY_REF>",
    "ACCEPTED",
    "AbortError",
    "BLOCKED",
    "CERTIFIED",
    "CHECKING",
    "CONTROLLED HANDOFF",
    "DIRECTED LANGUAGE ROUTES · BATCH 29",
    "DIRECTION MATTERS",
    "DISCOVERY BACKLOG",
    "DISCOVERY_INVALID",
    "DRAFT",
    "EXPERIMENTAL",
    "EXPERIMENTAL_EVALUATION",
    "Inventory 未知范围"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-controlled-disclosure-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "TranslationStudio:source-blocker",
    "TranslationStudio:effect-cleanup:8052",
    "TranslationStudio:effect-cleanup:10202"
  ],
  "irDigest": "sha256:7e2dea0e31ff3e08f1519acf8670f42d28d7287412232a6cd87958722b2fe582"
}));

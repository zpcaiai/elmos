const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "ModernizationProofStudio",
  "title": "(?:sha256:)?[a-f0-9]{64}",
  "role": "disclosure",
  "source": {
    "file": "app/proof-loop/ModernizationProofStudio.tsx",
    "componentName": "ModernizationProofStudio",
    "sha256": "sha256:ad19b406e3b1afff3c4af5c1011eaac4f16e065d2fcc8ab75567a571479d721e",
    "range": {
      "start": 1104,
      "end": 11353
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
    "reason": "string method find is outside certified-component-v1",
    "category": "effects-and-resources"
  },
  "props": [],
  "states": [
    {
      "name": "contracts",
      "type": "ModernizationProofContract[]"
    },
    {
      "name": "targetSkillId",
      "type": "inferred"
    },
    {
      "name": "projectId",
      "type": "inferred"
    },
    {
      "name": "repositoryId",
      "type": "inferred"
    },
    {
      "name": "baselineCommit",
      "type": "inferred"
    },
    {
      "name": "candidateCommit",
      "type": "inferred"
    },
    {
      "name": "imageDigest",
      "type": "inferred"
    },
    {
      "name": "policyDigest",
      "type": "inferred"
    },
    {
      "name": "inputs",
      "type": "inferred"
    },
    {
      "name": "evidence",
      "type": "inferred"
    },
    {
      "name": "subjectDigest",
      "type": "inferred"
    },
    {
      "name": "job",
      "type": "ModernizationProofJob | null"
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
    "useMemo",
    "useEffect",
    "useCallback"
  ],
  "resources": [
    "NETWORK",
    "TIMER"
  ],
  "apiPaths": [
    "/api/modernization-proof/contracts",
    "/api/modernization-proof/jobs",
    "/api/modernization-proof/subject-digest"
  ],
  "labels": [
    "(?:sha256:)?[a-f0-9]{64}",
    "/api/modernization-proof/contracts",
    "/api/modernization-proof/jobs",
    "/api/modernization-proof/subject-digest",
    "AbortError",
    "B108-S16",
    "B108-S16 · customer-ready-modernization-certificate",
    "BATCH 105–108 · EVIDENCE-BOUND",
    "BLOCKED",
    "Baseline Commit（可选）",
    "CONTRACT_DISCOVERY_FAILED",
    "Candidate Commit（可选）",
    "DELETE",
    "DURABLE TENANT JOB",
    "EVIDENCE",
    "FAIL-CLOSED STATUS",
    "INPUTS",
    "Job",
    "NOT_RUN",
    "OCI 镜像摘要（可选）",
    "POST",
    "PROOF_JOB_CANCEL_FAILED",
    "PROOF_JOB_CREATE_FAILED",
    "PROOF_JOB_STATUS_FAILED"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-controlled-disclosure-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "ModernizationProofStudio:source-blocker"
  ],
  "irDigest": "sha256:7ed848e1d83acdc10f5c8025b6cf23aceecbed3f1b39e905695a3be6079e65f0"
}));

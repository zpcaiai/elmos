export type CapabilityStatus = "READY" | "ENFORCED" | "BLOCKED" | "NOT_RUN" | "NOT_CONFIGURED" | "EXPERIMENTAL" | "LIMITED" | "REVIEW" | "DRAFT";

export type MigrationCapability = {
  id: string;
  batch: number;
  title: string;
  domain: string;
  description: string;
  skillCount: number;
  schemaCount: number;
  gateCommand: string;
  status: CapabilityStatus;
  icon: "code" | "workflow" | "database" | "layers" | "cloud" | "box" | "spark" | "shield";
  accent: "cyan" | "blue" | "violet" | "amber" | "green";
};

export type CapabilityResponse<T> = {
  source: "LIVE_API" | "REPOSITORY_CONTRACT";
  fetchedAt: string;
  externalExecutionEvidence: "NOT_RUN";
  capabilities: T[];
  note?: string;
};

export type ProductStage = {
  batch: string;
  shortTitle: string;
  title: string;
  subtitle: string;
  status: CapabilityStatus;
  icon: "shield" | "repository" | "server" | "file" | "lock";
  checks: Array<{ label: string; status: CapabilityStatus; detail: string }>;
  restrictions: string[];
};

export type ProductCapabilityResponse = {
  source: "LIVE_API" | "REPOSITORY_CONTRACT";
  fetchedAt: string;
  namespace: string;
  decisionCeiling: string;
  externalExecutionEvidence: "NOT_RUN";
  stages: ProductStage[];
  note?: string;
};

export type GenerationTargetId =
  | "java"
  | "python"
  | "csharp"
  | "typescript"
  | "go"
  | "kotlin"
  | "php"
  | "rust";

export type GenerationTarget = {
  id: GenerationTargetId;
  language: string;
  runtime: string;
  framework: string;
  port: number;
  sourceSkill: string;
  verificationCommand: string;
  verificationStatus: "NOT_RUN";
  maturity: "limited" | "experimental";
  productionProfiles: Array<"postgresql+jwt" | "postgresql+oidc">;
  productionEntityScope: "multi-entity" | "single-entity";
  accent: "amber" | "blue" | "violet" | "cyan" | "green";
  icon: "code" | "spark" | "layers";
};

export type GenerationStage = {
  batch: string;
  title: string;
  detail: string;
};

export type DeploymentHardware = {
  cpu: number;
  memoryGb: number;
  diskGb: number;
};

export type LocalRuntimeProfile = {
  id: GenerationTargetId | "spring-modernization";
  label: string;
  framework: string;
  toolchain: string;
  minimum: DeploymentHardware;
  recommended: DeploymentHardware;
  scope: string;
  directory: string;
  port: number;
  healthPath: string;
  verifyCommands: string[];
  runCommands: string[];
};

export type CloudDeploymentOption = {
  id: "google-cloud-run" | "azure-container-apps" | "aws-ecs-fargate" | "kubernetes";
  name: string;
  status: "RECOMMENDED" | "OPTIONAL" | "CONDITIONAL";
  fit: string;
  tradeoff: string;
};

export type DeploymentGuidance = {
  status: "CONFIGURATION_REQUIRED";
  externalEvidence: "NOT_RUN";
  localProfiles: LocalRuntimeProfile[];
  cloudOptions: CloudDeploymentOption[];
  recommendation: {
    platform: "Google Cloud Run";
    reason: string;
    requiredInputs: string[];
    steps: Array<{ title: string; detail: string; commands?: string[] }>;
    rollback: string[];
    cleanup: string[];
    officialDocs: Array<{ label: string; url: string }>;
  };
};

export type GenerationCapabilityResponse = {
  source: "REPOSITORY_CONTRACT";
  fetchedAt: string;
  schemaVersion: "1.1.0";
  projectSkillCount: 417;
  targets: GenerationTarget[];
  stages: GenerationStage[];
  generationStatus: "NOT_RUN";
  externalExecutionEvidence: "NOT_RUN";
  productionDeliveryStatus: "NOT_RUN";
  certificationStatus: "NOT_CERTIFIED";
  localRunner: {
    enabled: boolean;
    persistence: "FILESYSTEM_ATOMIC";
    auth: "BEARER_TENANT_BOUND";
    isolation: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT" | "NOT_CONFIGURED";
    recovery: "PERSISTENT_RECONCILIATION";
  };
  deploymentGuidance: DeploymentGuidance;
  note: string;
};

export type GenerationSourceKind =
  | "description"
  | "text-file"
  | "markdown-file"
  | "word-file"
  | "html-file"
  | "pdf-file"
  | "online-html"
  | "skill";

export type GenerationSourceReference = {
  id: string;
  kind: GenerationSourceKind;
  label: string;
  mediaType: string;
  origin?: string;
  sha256: string;
  byteCount: number;
  extractedCharacters: number;
  includedCharacters: number;
  truncated: boolean;
  warnings: string[];
};

export type GenerationSourceBundle = {
  status: "READY_FOR_REVIEW";
  schemaVersion: "1.0.0";
  bundleSha256: string;
  combinedText: string;
  sources: GenerationSourceReference[];
  warnings: string[];
  extractedAt: string;
};

export type GenerationJobCreateRequest = {
  name: string;
  namespace: string;
  description: string;
  entity: string;
  reviewer: string;
  targets: GenerationTargetId[];
  persistence: "in-memory" | "postgresql";
  authMode: "none" | "jwt" | "oidc";
  approved: boolean;
  analysisDigest: string;
  sources?: GenerationSourceReference[];
  sourceBundleSha256?: string;
};

export type GenerationAnalyzeRequest = Omit<
  GenerationJobCreateRequest,
  "reviewer" | "approved" | "analysisDigest"
>;

export type GenerationRequirementReview = {
  schema_version: "1.1.0";
  project: {
    name: string;
    namespace: string;
    description: string;
    kind: "api";
    persistence: "in-memory" | "postgresql";
    auth_mode: "none" | "jwt" | "oidc";
  };
  entities: Array<{
    singular: string;
    plural: string;
    fields: Array<{
      name: string;
      type: "string" | "integer" | "number" | "boolean" | "datetime";
      required: boolean;
    }>;
  }>;
  relations: Array<{
    source: string;
    target: string;
    source_field?: string;
    target_field?: string;
    kind: "one-to-one" | "one-to-many" | "many-to-one" | "many-to-many";
    required: boolean;
  }>;
  business_rules: Array<{
    id: string;
    statement: string;
    enforcement: string;
    predicate?: {
      type: "record-exists-on-mutation" | "field-comparison";
      entity?: string;
      field?: string;
      operator?: "gte" | "gt" | "lte" | "lt" | "eq" | "neq";
      value?: string | number | boolean;
    };
  }>;
  permissions: Array<{
    actor: string;
    action: string;
    resource: string;
    effect: "allow" | "deny";
  }>;
  requirements: Array<{ id: string; statement: string; priority: string }>;
  acceptance_criteria: Array<{ id: string; statement: string }>;
  open_questions: Array<{ id: string; question: string; impact: string }>;
  targets: Array<{
    language: GenerationTargetId;
    framework: string;
    runtime: string;
    port: number;
  }>;
};

export type GenerationAnalysis = {
  status: "REVIEW_REQUIRED";
  analyzedAt: string;
  requestDigest: string;
  request: GenerationRequirementReview;
};

export type GenerationJobLog = {
  at: string;
  stream: "system" | "stdout" | "stderr" | "runtime";
  message: string;
};

export type GenerationArtifact = {
  path: string;
  sha256: string;
  ownership: "managed";
};

export type GenerationRuntimePlan = {
  language: GenerationTargetId;
  cwd: string;
  command: string[];
  environment: Record<string, string>;
  providers?: string[];
  port: number;
};

export type GenerationRuntime = {
  status: "STOPPED" | "STARTING" | "RUNNING" | "BLOCKED";
  language?: GenerationTargetId;
  executor?: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT";
  containerName?: string;
  pid?: number;
  reason?: string;
  plans: GenerationRuntimePlan[];
  updatedAt: string;
};

export type GenerationJob = {
  id: string;
  tenantId: string;
  actor: string;
  createdAt: string;
  updatedAt: string;
  status:
    | "QUEUED"
    | "ANALYZING"
    | "GENERATING"
    | "VERIFYING"
    | "ARCHIVING"
    | "COMPLETED"
    | "PARTIAL"
    | "BLOCKED"
    | "CANCELLED";
  stage:
    | "queued"
    | "analyze"
    | "pipeline"
    | "verify"
    | "archive"
    | "metering"
    | "complete"
    | "blocked"
    | "cancelled"
    | "restart-recovery";
  progress: number;
  resultStatus: string;
  artifactReady: boolean;
  artifactSha256?: string;
  artifactSize?: number;
  artifacts: GenerationArtifact[];
  recoveryAttempts?: number;
  reason?: string;
  logs: GenerationJobLog[];
  runtime: GenerationRuntime;
};

export type SpringModernizationStage = {
  id: "discover" | "baseline" | "contract" | "upgrade" | "verify" | "release";
  title: string;
  detail: string;
  status: CapabilityStatus;
  requiredEvidence: string;
};

export type SpringModernizationCapabilityResponse = {
  source: "REPOSITORY_CONTRACT";
  fetchedAt: string;
  target: {
    java: "21";
    framework: "Spring Boot 3.5.3";
    build: "Maven 3.9+ / Gradle exact wrapper";
  };
  recognizedSources: Array<{
    id: "spring-framework-xml" | "spring-framework-annotation" | "spring-boot-legacy";
    label: string;
    detail: string;
    status: CapabilityStatus;
  }>;
  researchPack: {
    key: "spring-boot-2-7-18-to-3-5-3";
    status: "LIMITED";
    externalEvidence: "NOT_RUN";
  };
  deploymentGuidance: DeploymentGuidance;
  stages: SpringModernizationStage[];
  note: string;
};

export type SpringRouteEvidenceStatus = "PASSED_LOCAL" | "NOT_RUN" | "NOT_IMPLEMENTED";

export type SpringRouteDescriptor = {
  routeId: string;
  packKey: string;
  label: string;
  buildTool: string;
  sourceBootMinInclusive: string;
  sourceBootMaxExclusive: string;
  sourceJavaVersions: string[];
  targetSpringBoot: string;
  targetJava: string;
  recipeId: string;
  evidenceStatus: SpringRouteEvidenceStatus;
  verifiedSourceSpringBoot: string;
  verifiedSourceJava: string;
  notes?: string;
};

export type TranslationLanguageId = "java" | "csharp" | "python" | "typescript";

export type TranslationLanguage = {
  id: TranslationLanguageId;
  label: string;
  compiler: string;
  runtime: string;
  enginePath: string;
};

export type RouteEvidenceStatus = "PASSED" | "NOT_RUN" | "FAILED";

export type DirectedLanguageRoute = {
  id: string;
  source: TranslationLanguageId;
  target: TranslationLanguageId;
  skill: string;
  status: "EXPERIMENTAL" | "LIMITED" | "SUPPORTED" | "CERTIFIED" | "BLOCKED";
  readiness: "LOCAL_PROFILE_PASSED" | "NOT_RUN";
  localExecution: RouteEvidenceStatus;
  independentVerification: RouteEvidenceStatus;
  externalVerification: RouteEvidenceStatus;
  sourceVersion: string;
  targetVersion: string;
  hazards: string[];
  blockers: string[];
};

export type TranslationCapabilityResponse = {
  source: "REPOSITORY_CONTRACT";
  fetchedAt: string;
  schemaVersion: "1.1.0";
  contractPath: string;
  semanticProfile: string;
  languages: TranslationLanguage[];
  routes: DirectedLanguageRoute[];
  routePackageCount: number;
  certifiedRouteCount: number;
  repositoryPlanning: "LOCAL_MANIFEST_SUPPORTED";
  localExecutionEvidence: "PASSED_LOCAL" | "NOT_RUN" | "FAILED";
  independentVerificationEvidence: RouteEvidenceStatus;
  externalExecutionEvidence: RouteEvidenceStatus;
  certificationStatus: "NOT_CERTIFIED" | "CERTIFIED";
  localRunner?: {
    enabled: boolean;
    persistence: "FILESYSTEM_ATOMIC";
    auth: "BEARER_TENANT_BOUND";
    isolation: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT" | "NOT_CONFIGURED";
    recovery: "PERSISTENT_RECONCILIATION";
  };
  note: string;
};

export type TranslationJobLog = {
  at: string;
  stream: "system" | "stdout" | "stderr";
  message: string;
};

export type TranslationJob = {
  id: string;
  tenantId: string;
  actor: string;
  createdAt: string;
  updatedAt: string;
  repositoryRef: string;
  workspaceId: string;
  casesBundleId: string;
  sourceLanguage: TranslationLanguageId;
  targetLanguage: TranslationLanguageId;
  status: "QUEUED" | "RUNNING" | "COMPLETE" | "PARTIAL" | "BLOCKED" | "CANCELLED";
  stage: "queued" | "pipeline" | "metering" | "complete" | "blocked" | "cancelled" | "restart-recovery";
  progress: number;
  executor: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT";
  recoveryAttempts: number;
  artifactReady: boolean;
  artifactSha256?: string;
  artifactSize?: number;
  snapshotSha256?: string;
  readyCount?: number;
  workUnitCount?: number;
  includedUnitCount?: number;
  statusCounts?: Record<string, number>;
  buildVerification?: { status: string; command?: string[]; toolchain?: string };
  independentVerificationStatus: "NOT_RUN";
  externalVerificationStatus: "NOT_RUN";
  certificationStatus: "NOT_CERTIFIED";
  reason?: string;
  logs: TranslationJobLog[];
};

export type TranslationCapabilityBlocked = {
  source: "REPOSITORY_CONTRACT";
  fetchedAt: string;
  status: "BLOCKED";
  errorCode: string;
  message: string;
};

export type TranslationRepositoryWorkUnit = {
  id: string;
  route_id: string;
  source_path: string;
  source_sha256: string;
  source_bytes: number;
  status: "DISCOVERY_REQUIRED";
  execution_status: "NOT_RUN";
  required_inputs: ["function_name", "behavior_cases_json"];
  declared_profile: "typed-pure-function-v1";
  unsupported_until_discovered: string[];
};

export type TranslationDiscoveryVerdict =
  | "READY"
  | "UNSUPPORTED"
  | "NO_CANDIDATE_DECLARATION"
  | "UNREADABLE";

export type TranslationDiscoveryResult = {
  id: string;
  source_path: string;
  declared_sha256: string;
  verdict: TranslationDiscoveryVerdict;
  profile: "typed-pure-function-v1";
  execution_status: "NOT_RUN";
  route_id: string;
  function_name?: string;
  parameter_count?: number;
  return_type?: string;
  analyzer?: string;
  reason?: string;
  rejected_candidates: Array<{ candidate: string; reason: string }>;
};

export type TranslationDiscoveryReport = {
  schema_version: "1.0.0";
  kind: "elmos.repository-discovery-report";
  status: "DISCOVERED";
  repository_ref: string;
  snapshot_sha256: string;
  route_id: string;
  source_language: TranslationLanguageId;
  target_language: TranslationLanguageId;
  profile: "typed-pure-function-v1";
  work_unit_count: number;
  discovered_count: number;
  ready_count: number;
  verdict_counts: Record<string, number>;
  results: TranslationDiscoveryResult[];
  execution_status: "NOT_RUN";
  external_verification_status: "NOT_RUN";
  certification_status: "NOT_CERTIFIED";
};

export type TranslationRepositoryPlan = {
  schema_version: "1.0.0";
  kind: "elmos.repository-route-plan";
  status: "PLANNED";
  repository_ref: string;
  snapshot_sha256: string;
  snapshot_consistency: "STABLE_READ_ONLY_SCAN";
  route_id: string;
  source_language: TranslationLanguageId;
  target_language: TranslationLanguageId;
  file_count: number;
  source_file_count: number;
  source_bytes: number;
  language_counts: Record<TranslationLanguageId, number>;
  ignored_symlink_count: number;
  work_units: TranslationRepositoryWorkUnit[];
  execution_status: "NOT_RUN";
  external_verification_status: "NOT_RUN";
  certification_status: "NOT_CERTIFIED";
  limitations: string[];
};

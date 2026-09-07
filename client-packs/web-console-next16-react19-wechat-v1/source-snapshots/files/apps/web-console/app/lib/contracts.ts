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

export type EvidenceChartStatus =
  | "PASSED"
  | "FAILED"
  | "NOT_RUN"
  | "UNKNOWN"
  | "NOT_APPLICABLE";

export type GenerationInsightGraphNode = {
  id: string;
  label: string;
  kind:
    | "baseline"
    | "semantic-ir"
    | "architecture"
    | "documentation"
    | "deployment"
    | "evidence"
    | "generated-target";
  path: string;
  status: Exclude<EvidenceChartStatus, "NOT_APPLICABLE">;
  language?: GenerationTargetId;
};

export type GenerationInsightGraph = {
  graph_kind: "project-synthesis-insight-graph";
  nodes: GenerationInsightGraphNode[];
  edges: Array<{
    from: string;
    to: string;
    relation: "normalizes" | "plans" | "documents" | "configures" | "generates" | "requires-verification";
  }>;
  node_count: number;
  edge_count: number;
  target_count: number;
};

export type GenerationProjectStructureNode = {
  id: string;
  kind:
    | "repository"
    | "requirements"
    | "documentation"
    | "deployment"
    | "continuous-integration"
    | "repository-metadata"
    | "operations"
    | "observability"
    | "security"
    | "database"
    | "application"
    | "build-manifest"
    | "api-contract"
    | "container"
    | "test-root"
    | "source-root"
    | "configuration"
    | "application-support";
  path: string;
  label: string;
  ownership: "managed";
  file_count: number;
  status: "REPRESENTED";
  language?: GenerationTargetId;
  framework?: string;
  runtime?: string;
};

export type GenerationProjectStructure = {
  schema_version: "1.0.0";
  graph_kind: "elmos.project-structure";
  project: {
    id: string;
    name: string;
    repository_mode: "polyglot-monorepo";
    approved_payload_sha256: string;
  };
  nodes: GenerationProjectStructureNode[];
  edges: Array<{ from: string; to: string; type: "contains" }>;
  coverage: {
    scope: "managed-generated-artifacts";
    managed_file_count: number;
    classified_file_count: number;
    declared_application_count: number;
    represented_application_count: number;
    unclassified_paths: string[];
    status: "PASSED" | "FAILED" | "UNKNOWN";
  };
};

export type GenerationDeclaredDependencyNode = {
  id: string;
  kind: "application" | "runtime" | "framework" | "build-tool" | "provider";
  coordinate: string;
  version_source: "project-blueprint" | "runtime-manifest" | "emitter-build-manifest";
};

export type GenerationDeclaredDependencyGraph = {
  schema_version: "1.0.0";
  graph_kind: "elmos.declared-dependency-graph";
  project_id: string;
  nodes: GenerationDeclaredDependencyNode[];
  edges: Array<{
    from: string;
    to: string;
    type: "requires" | "uses" | "builds-with" | "persists-to";
    scope: "runtime" | "application" | "build";
    evidence_status: "DECLARED";
  }>;
  resolution: {
    status: "PASSED" | "FAILED" | "NOT_RUN";
    resolved_graph_refs: string[];
  };
  complete: boolean;
  issues: string[];
};

export type GenerationSemanticInsight = {
  relation: "APPROVED_REQUIREMENTS_TO_GENERATED_TARGETS";
  mapping_status: Exclude<EvidenceChartStatus, "NOT_APPLICABLE">;
  equivalence_status: EvidenceChartStatus;
  subjects: Array<{
    id: string;
    label: string;
    source_count: number;
    mapped_count: number;
    mapping_status: Exclude<EvidenceChartStatus, "NOT_APPLICABLE">;
    semantic_equivalence_status: EvidenceChartStatus;
    evidence_strength: "HASH_BOUND_TRACEABILITY";
  }>;
  source_subject_count: number;
  mapped_subject_count: number;
  limitations: string[];
};

export type GenerationBehaviorInsight = {
  profile: "native-build-test-startup-v1";
  status: Exclude<EvidenceChartStatus, "NOT_APPLICABLE">;
  targets: Array<{
    language: GenerationTargetId;
    status: Exclude<EvidenceChartStatus, "NOT_APPLICABLE">;
    exact_toolchain_status: Exclude<EvidenceChartStatus, "NOT_APPLICABLE">;
    build_analysis: {
      total: number;
      status_counts: Record<EvidenceChartStatus, number>;
    };
    startup_status: Exclude<EvidenceChartStatus, "NOT_APPLICABLE">;
  }>;
  cross_target_matrix: Array<{
    source: GenerationTargetId;
    target: GenerationTargetId;
    semantic_status: EvidenceChartStatus;
    behavior_status: EvidenceChartStatus;
    reason: "SAME_TARGET" | "DIRECT_PAIRWISE_SOURCE_TARGET_COMPARISON_NOT_EXECUTED" | string;
  }>;
  limitations: string[];
};

export type GenerationCoverageDimensionId =
  | "project-structure"
  | "requirements-traceability"
  | "native-target-verification"
  | "direct-semantic-equivalence"
  | "direct-behavior-equivalence";

export type GenerationInsights = {
  schema_version: "1.0.0";
  kind: "elmos.project-generation-insights";
  stage: "GENERATED" | "VERIFIED";
  project: {
    id: string;
    name: string;
    request_sha256: string;
    approved_payload_sha256: string;
  };
  claim_ceiling: "LOCAL_ENGINEERING_EVIDENCE";
  project_structure?: GenerationProjectStructure;
  declared_dependencies?: GenerationDeclaredDependencyGraph;
  structure: GenerationInsightGraph;
  semantic: GenerationSemanticInsight;
  behavior: GenerationBehaviorInsight;
  coverage: Array<{
    id: GenerationCoverageDimensionId;
    label: string;
    status: EvidenceChartStatus;
    passed: number;
    total: number;
  }>;
  verification_status?: "PASSED" | "FAILED" | "PARTIAL" | "NOT_RUN" | "UNKNOWN";
  external_verification_status: "NOT_RUN";
  certification_status: "NOT_CERTIFIED";
};

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
  | "repository-file"
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
  requirement_sources?: GenerationSourceReference[];
  source_bundle_sha256?: string;
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
  previewPort?: number;
  pid?: number;
  reason?: string;
  leaseStartedAt?: string;
  leaseExpiresAt?: string;
  leaseDurationSeconds?: number;
  leaseId?: string;
  remainingSeconds?: number;
  plans: GenerationRuntimePlan[];
  updatedAt: string;
};

export type GenerationGitHubPublication = {
  status: "CREATING" | "PUBLISHED" | "BLOCKED";
  repositoryFullName?: string;
  repositoryId?: number;
  repositoryUrl?: string;
  branch?: "main";
  commitSha?: string;
  artifactSha256: string;
  fileCount?: number;
  idempotencyKey: string;
  reason?: string;
  updatedAt: string;
};

export type GenerationJob = {
  id: string;
  tenantId: string;
  actor: string;
  createdAt: string;
  updatedAt: string;
  terminalAt?: string;
  retentionExpiresAt?: string;
  retentionPolicySeconds?: number;
  retentionPolicyVersion?: "generation-storage-v1";
  legalHold?: boolean;
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
  insights?: GenerationInsights;
  reason?: string;
  logs: GenerationJobLog[];
  runtime: GenerationRuntime;
  githubPublication?: GenerationGitHubPublication;
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
    build: "Maven 3.9.11";
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
  sourceFrameworkFamily: "spring-boot" | "spring-mvc" | "spring-framework";
  buildTool: string;
  sourceBootMinInclusive: string;
  sourceBootMaxExclusive: string;
  exactSourceVersion?: string;
  sourceConstraint?: string;
  sourceVersionMatch?: "EXACT" | "RANGE";
  sourceJavaVersions: string[];
  targetSpringBoot: string;
  targetJava: string;
  recipeId: string;
  evidenceStatus: SpringRouteEvidenceStatus;
  verifiedSourceSpringBoot: string;
  verifiedSourceJava: string;
  notes?: string;
};

export type TranslationLanguageId =
  | "cpp"
  | "java"
  | "csharp"
  | "go"
  | "objc"
  | "rust"
  | "swift"
  | "python"
  | "typescript"
  | "php"
  | "kotlin"
  | "react"
  | "flutter";

/**
 * Repository inventory retains deprecated JavaScript files for digest-bound
 * exclusion evidence, but JavaScript is not an active source/target choice.
 */
export type TranslationRepositoryInventoryLanguageId = TranslationLanguageId | "javascript";

export type TranslationDeprecatedExcludedFile = {
  path: string;
  language: "javascript";
  sha256: string;
  bytes: number;
  status: "EXCLUDED_FROM_ACTIVE_ROUTE";
  reason: "DEPRECATED_LANGUAGE_REQUIRES_EXPLICIT_HISTORICAL_REPLAY";
};

export type TranslationLanguage = {
  id: TranslationLanguageId;
  label: string;
  compiler: string;
  runtime: string;
  enginePath: string;
};

export type RouteEvidenceStatus = "PASSED" | "NOT_RUN" | "FAILED";

export type RepositoryRouteExecutionStatus = RouteEvidenceStatus;

export type DirectedLanguageRoute = {
  id: string;
  source: TranslationLanguageId;
  target: TranslationLanguageId;
  skill: string;
  status: "RESEARCH" | "EXPERIMENTAL" | "LIMITED" | "SUPPORTED" | "CERTIFIED" | "BLOCKED";
  readiness: "LOCAL_PROFILE_PASSED" | "NOT_RUN";
  localExecution: RouteEvidenceStatus;
  repositoryExecutionStatus: RepositoryRouteExecutionStatus;
  repositoryProfile: string | null;
  repositoryEvidenceRef: string | null;
  repositoryEvidenceSha256: string | null;
  repositoryEvidenceBytes: number | null;
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
  repositoryExecutableRouteCount: number;
  repositoryPlanning: "LOCAL_MANIFEST_SUPPORTED";
  localExecutionEvidence: "PASSED_LOCAL" | "NOT_RUN" | "FAILED";
  repositoryExecutionEvidence: RepositoryRouteExecutionStatus;
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

export type TranslationSemanticCoverageStatus =
  | "BLOCKED"
  | "FAILED"
  | "NOT_RUN"
  | "PASSED"
  | "UNKNOWN";

export type TranslationSemanticCoverage = {
  profile: "compiler-semantic-symbol-coverage-v1";
  sourceLanguage: TranslationLanguageId;
  inventoryStatus: "PASSED" | "FAILED" | "NOT_RUN";
  status: "PASSED" | "LIMITED";
  complete: boolean;
  subjectCount: number;
  statusCounts: Record<TranslationSemanticCoverageStatus, number>;
};

export type TranslationBehaviorCoverageStatus = "FAILED" | "NOT_RUN" | "PASSED" | "UNKNOWN";

export type TranslationBehaviorCoverage = {
  profile: "typed-pure-function-v1";
  status: TranslationBehaviorCoverageStatus;
  complete: boolean;
  workUnitCount: number;
  accountedWorkUnitCount: number;
  attemptedWorkUnitCount: number;
  unresolvedWorkUnitCount: number;
  behaviorCaseCount: number;
  behaviorCaseCountScope: "PASSED_WORK_UNITS_ONLY";
  statusCounts: Record<TranslationBehaviorCoverageStatus, number>;
  evidenceStrength: "LOCAL_SOURCE_TARGET_RUNTIME_COMPARISON";
  independentVerificationStatus: "NOT_RUN";
  externalVerificationStatus: "NOT_RUN";
};

export type TranslationConversionReportFile = {
  path:
    | "functional-conversion-report.json"
    | "FUNCTION_CONVERSION_REPORT.md"
    | "FUNCTION_CONVERSION_REPORT_BUNDLE.zip";
  bytes: number;
  sha256: string;
};

/**
 * Polling responses deliberately contain no customer source or generated code.
 * Exact source/target blocks live only in the separately authorized,
 * content-addressed conversion report download.
 */
export type TranslationConversionFailureSummary = {
  obligationId: string;
  workUnitId: string;
  functionDescription: string;
  sourcePath: string;
  targetPath?: string;
  status: string;
  failureCode: string;
  failureReason: string;
  improvementActions: string[];
};

export type TranslationConversionSummary = {
  reportId: string;
  definitionId: string;
  measurementUnit: "FUNCTIONAL_OBLIGATION";
  comparisonBasis: "DECLARED_BEHAVIOR_ORACLE";
  storageMode: "SINGLE" | "SHARDED";
  shardCount: number;
  totalShardBytes: number;
  casesManifestSha256: string;
  numerator: number;
  denominator: number;
  reportedObligationCount: number;
  unknownScopeCount: number;
  unreportedObligationCount: number;
  unsuccessfulCount: number;
  exactFraction: string;
  successRateBasisPoints: number;
  displayPercent: string;
  projectSuccessRateLowerBoundBasisPoints: number;
  projectSuccessRateUpperBoundBasisPoints: number;
  projectSuccessRateDisplay: string;
  measurementStatus: "MEASURED" | "INDETERMINATE";
  denominatorComplete: boolean;
  verifiedCount: number;
  failedCount: number;
  codeArtifactReady: boolean;
  statusCounts: Record<string, number>;
  failureSummaries: TranslationConversionFailureSummary[];
  failureSummariesTruncated: boolean;
};

export type TranslationExecutionRuntimeReceipt = {
  schemaVersion: "1.0";
  executionId: string;
  phase: "preflight" | "pipeline";
  executor: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT";
  state: "STARTING" | "RUNNING" | "EXITED" | "CLEANUP_VERIFIED" | "CLEANUP_UNVERIFIED";
  processGroupId: number;
  containerName?: string;
  cidFile?: string;
  containerId?: string;
  labels?: {
    jobId: string;
    executionId: string;
    phase: "preflight" | "pipeline";
  };
  startedAt: string;
  updatedAt: string;
  cleanupVerifiedAt?: string;
};

export type TranslationJob = {
  id: string;
  tenantId: string;
  actor: string;
  createdAt: string;
  updatedAt: string;
  repositoryRef: string;
  workspaceId: string;
  repositoryWorkspaceId?: string;
  casesBundleId: string;
  sourceLanguage: TranslationLanguageId;
  targetLanguage: TranslationLanguageId;
  repositoryExecutionStatus: "PASSED";
  repositoryProfile: string;
  repositoryEvidenceRef: string;
  repositoryEvidenceSha256: string;
  repositoryEvidenceBytes: number;
  status: "QUEUED" | "PRECHECK" | "RUNNING" | "COMPLETE" | "PARTIAL" | "BLOCKED" | "CANCELLED";
  stage: "queued" | "preflight" | "pipeline" | "metering" | "complete" | "blocked" | "cancelled" | "restart-recovery";
  progress: number;
  executor: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT";
  executionId?: string;
  executionLeaseOwnerId?: string;
  cancelRequestedAt?: string;
  cancelRequestedBy?: string;
  runtimeReceipt?: TranslationExecutionRuntimeReceipt;
  recoveryAttempts: number;
  artifactReady: boolean;
  artifactSha256?: string;
  artifactSize?: number;
  reportReady: boolean;
  reportJson?: TranslationConversionReportFile;
  reportMarkdown?: TranslationConversionReportFile;
  reportBundle?: TranslationConversionReportFile;
  conversionSummary?: TranslationConversionSummary;
  snapshotSha256?: string;
  readyCount?: number;
  workUnitCount?: number;
  includedUnitCount?: number;
  statusCounts?: Record<string, number>;
  repositoryComplete?: boolean;
  projectGraph?: {
    path: "project-graph.json";
    graph_id: string;
    graph_sha256: string;
    snapshot_sha256: string;
    repository_complete: boolean;
    completeness_status: "COMPLETE" | "INCOMPLETE";
    obligation_count: number;
    obligation_status_counts: Record<"FAILED" | "NOT_RUN" | "PASSED" | "UNKNOWN", number>;
    verification_status: "PASSED";
  };
  semanticCoverage?: TranslationSemanticCoverage;
  behaviorCoverage?: TranslationBehaviorCoverage;
  buildVerification?: {
    // The engine reports NOT_RUN for a missing exact toolchain and FAILED for a
    // reportable build failure; only a verified build is PASSED.  `translationRunner`
    // already rejects anything outside this set before constructing the job.
    status: "PASSED" | "FAILED" | "NOT_RUN";
    commands: Array<{ command: string[]; stdout: string; stderr: string }>;
    toolchain: { language: TranslationLanguageId; version: string };
  };
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
  required_inputs: ["behavior_cases_json_per_discovered_function"];
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
  language_lifecycle: "ACTIVE";
  file_count: number;
  source_file_count: number;
  source_bytes: number;
  repository_scale: "small" | "medium";
  repository_limits: {
    maximum_source_files: number;
    maximum_source_bytes: number;
    maximum_bytes_per_file: number;
  };
  language_counts: Record<TranslationRepositoryInventoryLanguageId, number>;
  deprecated_excluded_files: TranslationDeprecatedExcludedFile[];
  ignored_symlink_count: number;
  work_units: TranslationRepositoryWorkUnit[];
  execution_status: "NOT_RUN";
  external_verification_status: "NOT_RUN";
  certification_status: "NOT_CERTIFIED";
  limitations: string[];
};

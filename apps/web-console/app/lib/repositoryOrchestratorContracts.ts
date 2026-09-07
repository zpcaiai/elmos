export const repositoryOrchestratorRequestLimitBytes = 32 * 1024;
export const repositoryOrchestratorResponseLimitBytes = 512 * 1024;

export type RepositoryModelPricing = {
  inputPerMillion: string | null;
  cachedInputPerMillion: string | null;
  outputPerMillion: string | null;
  currency: "USD";
  source: "operator_or_live_adapter";
  effectiveAt: string | null;
};

export type RepositoryModelLimits = {
  contextTokens: number | null;
  maxOutputTokens: number | null;
  concurrency: number | null;
};

export type RepositoryModelDescriptor = {
  alias: string;
  displayName: string;
  provider: string;
  roleHint: string;
  relativeCostTier: number;
  routingTiers: string[];
  highestRoutingTier: string;
  providerModelId: string | null;
  pricing: RepositoryModelPricing;
  limits: RepositoryModelLimits;
  capabilities: string[];
  deploymentId: string | null;
  exactModelRevision: string | null;
  providerGatewayAdapterId: string | null;
  observedAt: string | null;
  profileMaxAgeSeconds: number | null;
  quotaRemainingTokens: string | null;
  activeConcurrency: number | null;
  residencies: string[];
  privacyPolicyId: string | null;
  supportsPrivateRepositories: boolean | null;
  status: "AVAILABLE" | "NOT_CONFIGURED";
  available: boolean;
  selectable: boolean;
  reasons: string[];
};

export type RepositoryOrchestratorEvidence = {
  providerInvocation: "NOT_RUN";
  taskDecomposition: "NOT_RUN";
  runCreation: "NOT_RUN";
  workspaceMutation: "NOT_RUN";
  scmEffects: "NOT_RUN";
  externalVerification: "NOT_RUN";
  certification: "NOT_CERTIFIED";
};

export type RepositoryModelCatalog = {
  schemaVersion: "1.0";
  catalogVersion: string;
  selectionVersion: string;
  selectionModes: Array<"smart" | "manual">;
  defaultMode: "smart";
  optimizationProfiles: Array<"cost_performance" | "lowest_cost" | "max_quality" | "fastest">;
  fallbackPolicies: Array<"strict" | "smart_within_allowlist">;
  verificationPolicies: Array<"system_required_verifiers" | "selected_model_only">;
  models: RepositoryModelDescriptor[];
  status: "CONFIGURED" | "NOT_CONFIGURED";
  reasons: string[];
  runtimeProfilesAcceptedFromClient: false;
  evidence: RepositoryOrchestratorEvidence;
};

export type RepositoryRiskLevel = "none" | "low" | "medium" | "high" | "critical";

export type RepositoryRiskProfile = {
  security: RepositoryRiskLevel;
  dataMigration: RepositoryRiskLevel;
  concurrency: RepositoryRiskLevel;
  publicContract: RepositoryRiskLevel;
  blastRadius: RepositoryRiskLevel;
  longHorizon: boolean;
};

export type RepositoryPreflightRequest = {
  schemaVersion: "1.0";
  catalogVersion: string;
  selectionVersion: string;
  mode: "smart" | "manual";
  selectedModel: string | null;
  optimizationProfile: "cost_performance" | "lowest_cost" | "max_quality" | "fastest";
  fallbackPolicy: "strict" | "smart_within_allowlist" | null;
  verificationPolicy: "system_required_verifiers" | "selected_model_only";
  risk: RepositoryRiskProfile;
};

export type RepositorySelectionSnapshot = Omit<RepositoryPreflightRequest, "risk" | "fallbackPolicy"> & {
  fallbackPolicy: "router_policy" | "strict" | "smart_within_allowlist";
  selectionSource: "ui" | "api" | "cli" | "resume";
  lockedByUser: boolean;
  immutable: true;
  digest: string;
};

export type RepositoryPreflightResult = {
  schemaVersion: "1.0";
  catalogVersion: string;
  status: "BLOCKED" | "READY_FOR_TASK_DECOMPOSITION";
  validationStatus: "VALID" | "INVALID";
  configurationStatus: "CONFIGURED" | "NOT_CONFIGURED";
  reasons: string[];
  selection: RepositorySelectionSnapshot | null;
  risk: RepositoryRiskProfile | null;
  minimumRoutingTier: string;
  resolvedModel: string | null;
  dag: {
    status: "NOT_RUN";
    requiredStages: string[];
    tasks: unknown[];
    waves: string[][];
    criticalPath: string[];
    reason: string;
  };
  cost: {
    status: "NOT_CONFIGURED" | "DEFERRED_NOT_RUN";
    currency: "USD";
    estimatedRunCost: string | null;
    formula: string;
    reason: string;
  };
  auditExplanation: string[];
  runtimeProfilesAcceptedFromClient: false;
  evidence: RepositoryOrchestratorEvidence;
};

export class RepositoryOrchestratorContractError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message = code,
  ) {
    super(message);
    this.name = "RepositoryOrchestratorContractError";
  }
}

const aliasPattern = /^[a-z0-9][a-z0-9.-]{0,79}$/;
const tokenPattern = /^[a-z0-9][a-z0-9_]{0,79}$/;
const tierPattern = /^L[0-4]$/;
const digestPattern = /^[0-9a-f]{64}$/;
const decimalPattern = /^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/;
const integerStringPattern = /^(?:0|[1-9][0-9]*)$/;
const instantPattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$/;
const riskLevels = new Set<RepositoryRiskLevel>(["none", "low", "medium", "high", "critical"]);
const modes = new Set(["smart", "manual"]);
const optimizationProfiles = new Set(["cost_performance", "lowest_cost", "max_quality", "fastest"]);
const fallbackPolicies = new Set(["strict", "smart_within_allowlist"]);
const verificationPolicies = new Set(["system_required_verifiers", "selected_model_only"]);
const selectionSources = new Set(["ui", "api", "cli", "resume"]);

function fail(status: number, code: string, message = code): never {
  throw new RepositoryOrchestratorContractError(status, code, message);
}

function record(value: unknown, code: string, status = 502): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) fail(status, code);
  return value as Record<string, unknown>;
}

function exactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
  code: string,
  status = 502,
): void {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    fail(status, code);
  }
}

function text(value: unknown, code: string, pattern?: RegExp, status = 502): string {
  if (
    typeof value !== "string"
    || value.length < 1
    || value.length > 512
    || value.trim() !== value
    || /[\0\r\n]/.test(value)
    || (pattern && !pattern.test(value))
  ) fail(status, code);
  return value;
}

function optionalNumber(value: unknown, code: string): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) fail(502, code);
  return value;
}

function optionalDecimal(value: unknown, code: string): string | null {
  if (value === null) return null;
  if (typeof value !== "string" || !decimalPattern.test(value)) fail(502, code);
  return value;
}

function optionalInstant(value: unknown, code: string): string | null {
  if (value === null) return null;
  if (typeof value !== "string" || !instantPattern.test(value) || !Number.isFinite(Date.parse(value))) {
    fail(502, code);
  }
  return value;
}

function optionalText(value: unknown, code: string, pattern?: RegExp): string | null {
  if (value === null) return null;
  return text(value, code, pattern);
}

function optionalPositiveInteger(value: unknown, code: string): number | null {
  if (value === null) return null;
  if (!Number.isSafeInteger(value) || (value as number) < 1) fail(502, code);
  return value as number;
}

function optionalNonNegativeInteger(value: unknown, code: string): number | null {
  if (value === null) return null;
  if (!Number.isSafeInteger(value) || (value as number) < 0) fail(502, code);
  return value as number;
}

function stringArray(value: unknown, code: string, maximum = 64): string[] {
  if (!Array.isArray(value) || value.length > maximum) fail(502, code);
  return value.map((entry) => text(entry, code));
}

function exactLiteral<T extends string | number | boolean>(
  value: unknown,
  expected: T,
  code: string,
  status = 502,
): T {
  if (value !== expected) fail(status, code);
  return expected;
}

function evidence(value: unknown): RepositoryOrchestratorEvidence {
  const root = record(value, "REPOSITORY_ORCHESTRATOR_EVIDENCE_INVALID");
  exactKeys(root, [
    "providerInvocation", "taskDecomposition", "runCreation", "workspaceMutation",
    "scmEffects", "externalVerification", "certification",
  ], "REPOSITORY_ORCHESTRATOR_EVIDENCE_FIELDS_INVALID");
  return {
    providerInvocation: exactLiteral(root.providerInvocation, "NOT_RUN", "REPOSITORY_PROVIDER_STATE_INVALID"),
    taskDecomposition: exactLiteral(root.taskDecomposition, "NOT_RUN", "REPOSITORY_DAG_STATE_INVALID"),
    runCreation: exactLiteral(root.runCreation, "NOT_RUN", "REPOSITORY_RUN_STATE_INVALID"),
    workspaceMutation: exactLiteral(root.workspaceMutation, "NOT_RUN", "REPOSITORY_WORKSPACE_STATE_INVALID"),
    scmEffects: exactLiteral(root.scmEffects, "NOT_RUN", "REPOSITORY_SCM_STATE_INVALID"),
    externalVerification: exactLiteral(root.externalVerification, "NOT_RUN", "REPOSITORY_EXTERNAL_STATE_INVALID"),
    certification: exactLiteral(root.certification, "NOT_CERTIFIED", "REPOSITORY_CERTIFICATION_STATE_INVALID"),
  };
}

function pricing(value: unknown): RepositoryModelPricing {
  const root = record(value, "REPOSITORY_MODEL_PRICING_INVALID");
  exactKeys(root, [
    "inputPerMillion", "cachedInputPerMillion", "outputPerMillion", "currency", "source", "effectiveAt",
  ], "REPOSITORY_MODEL_PRICING_FIELDS_INVALID");
  return {
    inputPerMillion: optionalDecimal(root.inputPerMillion, "REPOSITORY_MODEL_INPUT_PRICE_INVALID"),
    cachedInputPerMillion: optionalDecimal(root.cachedInputPerMillion, "REPOSITORY_MODEL_CACHE_PRICE_INVALID"),
    outputPerMillion: optionalDecimal(root.outputPerMillion, "REPOSITORY_MODEL_OUTPUT_PRICE_INVALID"),
    currency: exactLiteral(root.currency, "USD", "REPOSITORY_MODEL_CURRENCY_INVALID"),
    source: exactLiteral(root.source, "operator_or_live_adapter", "REPOSITORY_MODEL_PRICE_SOURCE_INVALID"),
    effectiveAt: optionalInstant(root.effectiveAt, "REPOSITORY_MODEL_PRICE_EFFECTIVE_AT_INVALID"),
  };
}

function limits(value: unknown): RepositoryModelLimits {
  const root = record(value, "REPOSITORY_MODEL_LIMITS_INVALID");
  exactKeys(root, ["contextTokens", "maxOutputTokens", "concurrency"], "REPOSITORY_MODEL_LIMITS_FIELDS_INVALID");
  return {
    contextTokens: optionalPositiveInteger(root.contextTokens, "REPOSITORY_MODEL_CONTEXT_LIMIT_INVALID"),
    maxOutputTokens: optionalPositiveInteger(root.maxOutputTokens, "REPOSITORY_MODEL_OUTPUT_LIMIT_INVALID"),
    concurrency: optionalPositiveInteger(root.concurrency, "REPOSITORY_MODEL_CONCURRENCY_INVALID"),
  };
}

function model(value: unknown): RepositoryModelDescriptor {
  const root = record(value, "REPOSITORY_MODEL_INVALID");
  exactKeys(root, [
    "alias", "displayName", "provider", "roleHint", "relativeCostTier", "routingTiers",
    "highestRoutingTier", "providerModelId", "pricing", "limits", "capabilities", "status",
    "deploymentId", "exactModelRevision", "providerGatewayAdapterId", "observedAt", "profileMaxAgeSeconds",
    "quotaRemainingTokens", "activeConcurrency", "residencies", "privacyPolicyId",
    "supportsPrivateRepositories", "available", "selectable", "reasons",
  ], "REPOSITORY_MODEL_FIELDS_INVALID");
  const alias = text(root.alias, "REPOSITORY_MODEL_ALIAS_INVALID", aliasPattern);
  const routingTiers = stringArray(root.routingTiers, "REPOSITORY_MODEL_TIERS_INVALID", 5);
  if (routingTiers.length < 1 || routingTiers.some((tier) => !tierPattern.test(tier))) {
    fail(502, "REPOSITORY_MODEL_TIERS_INVALID");
  }
  if (!Number.isSafeInteger(root.relativeCostTier) || (root.relativeCostTier as number) < 1
      || (root.relativeCostTier as number) > 5) fail(502, "REPOSITORY_MODEL_COST_TIER_INVALID");
  if (typeof root.available !== "boolean" || typeof root.selectable !== "boolean") {
    fail(502, "REPOSITORY_MODEL_AVAILABILITY_INVALID");
  }
  if (root.selectable && !root.available) fail(502, "REPOSITORY_MODEL_SELECTABILITY_INVALID");
  if (root.status !== "AVAILABLE" && root.status !== "NOT_CONFIGURED") {
    fail(502, "REPOSITORY_MODEL_STATUS_INVALID");
  }
  if ((root.status === "AVAILABLE") !== root.available) fail(502, "REPOSITORY_MODEL_STATUS_MISMATCH");
  const providerModelId = root.providerModelId === null
    ? null
    : text(root.providerModelId, "REPOSITORY_PROVIDER_MODEL_ID_INVALID");
  return {
    alias,
    displayName: text(root.displayName, "REPOSITORY_MODEL_DISPLAY_NAME_INVALID"),
    provider: text(root.provider, "REPOSITORY_MODEL_PROVIDER_INVALID", aliasPattern),
    roleHint: text(root.roleHint, "REPOSITORY_MODEL_ROLE_INVALID", tokenPattern),
    relativeCostTier: root.relativeCostTier as number,
    routingTiers,
    highestRoutingTier: text(root.highestRoutingTier, "REPOSITORY_MODEL_HIGHEST_TIER_INVALID", tierPattern),
    providerModelId,
    pricing: pricing(root.pricing),
    limits: limits(root.limits),
    capabilities: stringArray(root.capabilities, "REPOSITORY_MODEL_CAPABILITIES_INVALID"),
    deploymentId: optionalText(root.deploymentId, "REPOSITORY_MODEL_DEPLOYMENT_ID_INVALID"),
    exactModelRevision: optionalText(root.exactModelRevision, "REPOSITORY_MODEL_REVISION_INVALID"),
    providerGatewayAdapterId: optionalText(root.providerGatewayAdapterId, "REPOSITORY_MODEL_ADAPTER_ID_INVALID"),
    observedAt: optionalInstant(root.observedAt, "REPOSITORY_MODEL_OBSERVED_AT_INVALID"),
    profileMaxAgeSeconds: optionalPositiveInteger(root.profileMaxAgeSeconds, "REPOSITORY_MODEL_MAX_AGE_INVALID"),
    quotaRemainingTokens: optionalText(root.quotaRemainingTokens, "REPOSITORY_MODEL_QUOTA_INVALID", integerStringPattern),
    activeConcurrency: optionalNonNegativeInteger(
      root.activeConcurrency,
      "REPOSITORY_MODEL_ACTIVE_CONCURRENCY_INVALID",
    ),
    residencies: stringArray(root.residencies, "REPOSITORY_MODEL_RESIDENCIES_INVALID"),
    privacyPolicyId: optionalText(root.privacyPolicyId, "REPOSITORY_MODEL_PRIVACY_POLICY_INVALID"),
    supportsPrivateRepositories: root.supportsPrivateRepositories === null
      ? null
      : typeof root.supportsPrivateRepositories === "boolean"
        ? root.supportsPrivateRepositories
        : fail(502, "REPOSITORY_MODEL_PRIVATE_REPOSITORY_POLICY_INVALID"),
    status: root.status,
    available: root.available,
    selectable: root.selectable,
    reasons: stringArray(root.reasons, "REPOSITORY_MODEL_REASONS_INVALID"),
  };
}

export function parseRepositoryModelCatalog(value: unknown): RepositoryModelCatalog {
  const root = record(value, "REPOSITORY_MODEL_CATALOG_INVALID");
  exactKeys(root, [
    "schemaVersion", "catalogVersion", "selectionVersion", "selectionModes", "defaultMode",
    "optimizationProfiles", "fallbackPolicies", "verificationPolicies", "models", "status", "reasons",
    "runtimeProfilesAcceptedFromClient", "evidence",
  ], "REPOSITORY_MODEL_CATALOG_FIELDS_INVALID");
  if (!Array.isArray(root.models) || root.models.length !== 10) fail(502, "REPOSITORY_MODEL_COUNT_INVALID");
  const models = root.models.map(model);
  if (new Set(models.map((entry) => entry.alias)).size !== 10) fail(502, "REPOSITORY_MODEL_ALIAS_DUPLICATE");
  if (root.status !== "CONFIGURED" && root.status !== "NOT_CONFIGURED") {
    fail(502, "REPOSITORY_MODEL_CATALOG_STATUS_INVALID");
  }
  const parsedModes = stringArray(root.selectionModes, "REPOSITORY_SELECTION_MODES_INVALID", 2);
  if (parsedModes.length !== 2 || !parsedModes.every((entry) => modes.has(entry))) {
    fail(502, "REPOSITORY_SELECTION_MODES_INVALID");
  }
  const parsedOptimization = stringArray(root.optimizationProfiles, "REPOSITORY_OPTIMIZATION_PROFILES_INVALID", 4);
  const parsedFallback = stringArray(root.fallbackPolicies, "REPOSITORY_FALLBACK_POLICIES_INVALID", 2);
  const parsedVerification = stringArray(root.verificationPolicies, "REPOSITORY_VERIFICATION_POLICIES_INVALID", 2);
  if (!parsedOptimization.every((entry) => optimizationProfiles.has(entry))) fail(502, "REPOSITORY_OPTIMIZATION_PROFILES_INVALID");
  if (!parsedFallback.every((entry) => fallbackPolicies.has(entry))) fail(502, "REPOSITORY_FALLBACK_POLICIES_INVALID");
  if (!parsedVerification.every((entry) => verificationPolicies.has(entry))) fail(502, "REPOSITORY_VERIFICATION_POLICIES_INVALID");
  return {
    schemaVersion: exactLiteral(root.schemaVersion, "1.0", "REPOSITORY_MODEL_CATALOG_SCHEMA_INVALID"),
    catalogVersion: text(root.catalogVersion, "REPOSITORY_MODEL_CATALOG_VERSION_INVALID"),
    selectionVersion: text(root.selectionVersion, "REPOSITORY_SELECTION_VERSION_INVALID"),
    selectionModes: parsedModes as Array<"smart" | "manual">,
    defaultMode: exactLiteral(root.defaultMode, "smart", "REPOSITORY_DEFAULT_MODE_INVALID"),
    optimizationProfiles: parsedOptimization as RepositoryModelCatalog["optimizationProfiles"],
    fallbackPolicies: parsedFallback as RepositoryModelCatalog["fallbackPolicies"],
    verificationPolicies: parsedVerification as RepositoryModelCatalog["verificationPolicies"],
    models,
    status: root.status,
    reasons: stringArray(root.reasons, "REPOSITORY_MODEL_CATALOG_REASONS_INVALID"),
    runtimeProfilesAcceptedFromClient: exactLiteral(
      root.runtimeProfilesAcceptedFromClient,
      false,
      "REPOSITORY_RUNTIME_PROFILE_BOUNDARY_INVALID",
    ),
    evidence: evidence(root.evidence),
  };
}

function parseRisk(value: unknown, status = 400): RepositoryRiskProfile {
  const root = record(value, "REPOSITORY_RISK_INVALID", status);
  exactKeys(root, [
    "security", "dataMigration", "concurrency", "publicContract", "blastRadius", "longHorizon",
  ], "REPOSITORY_RISK_FIELDS_INVALID", status);
  const fields = [root.security, root.dataMigration, root.concurrency, root.publicContract, root.blastRadius];
  if (fields.some((entry) => typeof entry !== "string" || !riskLevels.has(entry as RepositoryRiskLevel))) {
    fail(status, "REPOSITORY_RISK_LEVEL_INVALID");
  }
  if (typeof root.longHorizon !== "boolean") fail(status, "REPOSITORY_LONG_HORIZON_INVALID");
  return {
    security: root.security as RepositoryRiskLevel,
    dataMigration: root.dataMigration as RepositoryRiskLevel,
    concurrency: root.concurrency as RepositoryRiskLevel,
    publicContract: root.publicContract as RepositoryRiskLevel,
    blastRadius: root.blastRadius as RepositoryRiskLevel,
    longHorizon: root.longHorizon,
  };
}

export function parseRepositoryPreflightRequest(value: unknown): RepositoryPreflightRequest {
  const root = record(value, "REPOSITORY_PREFLIGHT_REQUEST_INVALID", 400);
  exactKeys(root, [
    "schemaVersion", "catalogVersion", "selectionVersion", "mode", "selectedModel",
    "optimizationProfile", "fallbackPolicy", "verificationPolicy", "risk",
  ], "REPOSITORY_PREFLIGHT_REQUEST_FIELDS_INVALID", 400);
  exactLiteral(root.schemaVersion, "1.0", "REPOSITORY_PREFLIGHT_SCHEMA_INVALID", 400);
  const mode = text(root.mode, "REPOSITORY_MODE_INVALID", tokenPattern, 400);
  const optimization = text(root.optimizationProfile, "REPOSITORY_OPTIMIZATION_INVALID", tokenPattern, 400);
  const fallback = root.fallbackPolicy === null
    ? null
    : text(root.fallbackPolicy, "REPOSITORY_FALLBACK_INVALID", tokenPattern, 400);
  const verification = text(root.verificationPolicy, "REPOSITORY_VERIFICATION_INVALID", tokenPattern, 400);
  if (!modes.has(mode)) fail(400, "REPOSITORY_MODE_INVALID");
  if (!optimizationProfiles.has(optimization)) fail(400, "REPOSITORY_OPTIMIZATION_INVALID");
  if (fallback !== null && !fallbackPolicies.has(fallback)) fail(400, "REPOSITORY_FALLBACK_INVALID");
  if (!verificationPolicies.has(verification)) fail(400, "REPOSITORY_VERIFICATION_INVALID");
  const selectedModel = root.selectedModel === null
    ? null
    : text(root.selectedModel, "REPOSITORY_SELECTED_MODEL_INVALID", aliasPattern, 400);
  if (mode === "smart" && (selectedModel !== null || fallback !== null)) {
    fail(400, "REPOSITORY_SMART_SELECTION_INVALID");
  }
  if (mode === "manual" && (selectedModel === null || fallback === null)) {
    fail(400, "REPOSITORY_MANUAL_SELECTION_INVALID");
  }
  return {
    schemaVersion: "1.0",
    catalogVersion: text(root.catalogVersion, "REPOSITORY_CATALOG_VERSION_INVALID", undefined, 400),
    selectionVersion: text(root.selectionVersion, "REPOSITORY_SELECTION_VERSION_INVALID", undefined, 400),
    mode: mode as "smart" | "manual",
    selectedModel,
    optimizationProfile: optimization as RepositoryPreflightRequest["optimizationProfile"],
    fallbackPolicy: fallback as RepositoryPreflightRequest["fallbackPolicy"],
    verificationPolicy: verification as RepositoryPreflightRequest["verificationPolicy"],
    risk: parseRisk(root.risk, 400),
  };
}

function selection(value: unknown): RepositorySelectionSnapshot | null {
  if (value === null) return null;
  const root = record(value, "REPOSITORY_SELECTION_SNAPSHOT_INVALID");
  exactKeys(root, [
    "schemaVersion", "catalogVersion", "selectionVersion", "mode", "selectedModel",
    "optimizationProfile", "fallbackPolicy", "verificationPolicy", "selectionSource", "lockedByUser",
    "immutable", "digest",
  ], "REPOSITORY_SELECTION_SNAPSHOT_FIELDS_INVALID");
  const mode = text(root.mode, "REPOSITORY_MODE_INVALID", tokenPattern);
  const snapshotFallback = text(root.fallbackPolicy, "REPOSITORY_FALLBACK_INVALID", tokenPattern);
  const snapshotSource = text(root.selectionSource, "REPOSITORY_SELECTION_SOURCE_INVALID", tokenPattern);
  if (!modes.has(mode) || !selectionSources.has(snapshotSource)) fail(502, "REPOSITORY_SELECTION_PROVENANCE_INVALID");
  if (typeof root.lockedByUser !== "boolean" || root.lockedByUser !== (mode === "manual")) {
    fail(502, "REPOSITORY_SELECTION_LOCK_INVALID");
  }
  if ((mode === "smart" && snapshotFallback !== "router_policy")
      || (mode === "manual" && !fallbackPolicies.has(snapshotFallback))) {
    fail(502, "REPOSITORY_SELECTION_FALLBACK_INVALID");
  }
  const parsedRequest = parseRepositoryPreflightRequest({
    schemaVersion: root.schemaVersion,
    catalogVersion: root.catalogVersion,
    selectionVersion: root.selectionVersion,
    mode: root.mode,
    selectedModel: root.selectedModel,
    optimizationProfile: root.optimizationProfile,
    fallbackPolicy: mode === "smart" ? null : snapshotFallback,
    verificationPolicy: root.verificationPolicy,
    risk: {
      security: "none",
      dataMigration: "none",
      concurrency: "none",
      publicContract: "none",
      blastRadius: "none",
      longHorizon: false,
    },
  });
  const { risk: _validatedSyntheticRisk, fallbackPolicy: _callerFallback, ...request } = parsedRequest;
  return {
    ...request,
    fallbackPolicy: snapshotFallback as RepositorySelectionSnapshot["fallbackPolicy"],
    selectionSource: snapshotSource as RepositorySelectionSnapshot["selectionSource"],
    lockedByUser: root.lockedByUser,
    immutable: exactLiteral(root.immutable, true, "REPOSITORY_SELECTION_IMMUTABILITY_INVALID"),
    digest: text(root.digest, "REPOSITORY_SELECTION_DIGEST_INVALID", digestPattern),
  };
}

export function parseRepositoryPreflightResult(value: unknown): RepositoryPreflightResult {
  const root = record(value, "REPOSITORY_PREFLIGHT_RESULT_INVALID");
  exactKeys(root, [
    "schemaVersion", "catalogVersion", "status", "validationStatus", "configurationStatus", "reasons",
    "selection", "risk", "minimumRoutingTier", "resolvedModel", "dag", "cost", "auditExplanation",
    "runtimeProfilesAcceptedFromClient", "evidence",
  ], "REPOSITORY_PREFLIGHT_RESULT_FIELDS_INVALID");
  if (root.status !== "BLOCKED" && root.status !== "READY_FOR_TASK_DECOMPOSITION") {
    fail(502, "REPOSITORY_PREFLIGHT_STATUS_INVALID");
  }
  if (root.validationStatus !== "VALID" && root.validationStatus !== "INVALID") {
    fail(502, "REPOSITORY_PREFLIGHT_VALIDATION_INVALID");
  }
  if (root.configurationStatus !== "CONFIGURED" && root.configurationStatus !== "NOT_CONFIGURED") {
    fail(502, "REPOSITORY_PREFLIGHT_CONFIGURATION_INVALID");
  }
  const dag = record(root.dag, "REPOSITORY_DAG_INVALID");
  exactKeys(dag, ["status", "requiredStages", "tasks", "waves", "criticalPath", "reason"], "REPOSITORY_DAG_FIELDS_INVALID");
  exactLiteral(dag.status, "NOT_RUN", "REPOSITORY_DAG_STATUS_INVALID");
  if (!Array.isArray(dag.tasks) || !Array.isArray(dag.waves)) fail(502, "REPOSITORY_DAG_CONTENT_INVALID");
  const waves = dag.waves.map((wave) => stringArray(wave, "REPOSITORY_DAG_WAVE_INVALID"));
  const cost = record(root.cost, "REPOSITORY_COST_INVALID");
  exactKeys(cost, ["status", "currency", "estimatedRunCost", "formula", "reason"], "REPOSITORY_COST_FIELDS_INVALID");
  if (cost.status !== "NOT_CONFIGURED" && cost.status !== "DEFERRED_NOT_RUN") {
    fail(502, "REPOSITORY_COST_STATUS_INVALID");
  }
  const resolvedModel = root.resolvedModel === null
    ? null
    : text(root.resolvedModel, "REPOSITORY_RESOLVED_MODEL_INVALID", aliasPattern);
  return {
    schemaVersion: exactLiteral(root.schemaVersion, "1.0", "REPOSITORY_PREFLIGHT_SCHEMA_INVALID"),
    catalogVersion: text(root.catalogVersion, "REPOSITORY_PREFLIGHT_CATALOG_INVALID"),
    status: root.status,
    validationStatus: root.validationStatus,
    configurationStatus: root.configurationStatus,
    reasons: stringArray(root.reasons, "REPOSITORY_PREFLIGHT_REASONS_INVALID"),
    selection: selection(root.selection),
    risk: root.risk === null ? null : parseRisk(root.risk, 502),
    minimumRoutingTier: text(root.minimumRoutingTier, "REPOSITORY_MINIMUM_TIER_INVALID", tierPattern),
    resolvedModel,
    dag: {
      status: "NOT_RUN",
      requiredStages: stringArray(dag.requiredStages, "REPOSITORY_DAG_STAGES_INVALID"),
      tasks: dag.tasks,
      waves,
      criticalPath: stringArray(dag.criticalPath, "REPOSITORY_DAG_CRITICAL_PATH_INVALID"),
      reason: text(dag.reason, "REPOSITORY_DAG_REASON_INVALID"),
    },
    cost: {
      status: cost.status,
      currency: exactLiteral(cost.currency, "USD", "REPOSITORY_COST_CURRENCY_INVALID"),
      estimatedRunCost: optionalDecimal(cost.estimatedRunCost, "REPOSITORY_COST_ESTIMATE_INVALID"),
      formula: text(cost.formula, "REPOSITORY_COST_FORMULA_INVALID"),
      reason: text(cost.reason, "REPOSITORY_COST_REASON_INVALID"),
    },
    auditExplanation: stringArray(root.auditExplanation, "REPOSITORY_AUDIT_EXPLANATION_INVALID"),
    runtimeProfilesAcceptedFromClient: exactLiteral(
      root.runtimeProfilesAcceptedFromClient,
      false,
      "REPOSITORY_RUNTIME_PROFILE_BOUNDARY_INVALID",
    ),
    evidence: evidence(root.evidence),
  };
}

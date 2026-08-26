import { createHash } from "node:crypto";

import {
  compileMiniappPackageConversionInput,
  type PackageConversionPolicyBinding,
} from "./miniapp-package-contract.js";
import {
  canonicalizeMiniappConversionRequest,
  MINIAPP_INVENTORY_HARD_LIMITS,
  normalizeMiniappRelativePath,
  validateMiniappConversionRequest,
} from "./miniapp-contract-validation.js";
import {
  canonicalizeMiniappSourceInventory,
  inventoryMiniappSource,
} from "./miniapp-inventory.js";
import {
  MINIAPP_DECLARED_OUTPUT_CATALOG,
  materializeMiniappDeclaredOutputs,
  type MiniappDeclaredOutputArtifact,
} from "./miniapp-output-contracts.js";
import {
  auditMiniappPrivacy,
  planMiniappConversion,
  type MiniappConversionPlan,
  type MiniappPrivacyAudit,
} from "./miniapp-planning.js";
import {
  analyzeMiniappSource,
  buildMiniappSemanticIr,
  canonicalizeMiniappSemanticIr,
  canonicalizeMiniappSourceAnalysis,
  miniappIrDigest,
  type MiniappSemanticIr,
  type MiniappSourceAnalysis,
} from "./miniapp-semantic-ir.js";
import {
  generateAllMiniappTargets,
  type MiniappGeneratedProject,
} from "./miniapp-target-generation.js";
import {
  evaluateMiniappLocalValidation,
  type MiniappLocalValidationEvaluation,
} from "./miniapp-validation.js";
import type {
  MiniappConversionRequest,
  MiniappInventoryInputFile,
  MiniappPlatform,
  MiniappSourceInventory,
} from "./miniapp-types.js";

export const MINIAPP_SKILL_CATALOG = [
  { name: "frontend-to-miniapp-orchestrator", stage: "orchestration", taskIds: ["MAPP-001", "MAPP-002"], dependsOn: [] },
  { name: "miniapp-source-framework-detector", stage: "discovery", taskIds: ["MAPP-003", "MAPP-004"], dependsOn: [] },
  { name: "vue-to-miniapp-analyzer", stage: "source-analysis", taskIds: ["MAPP-005", "MAPP-006"], dependsOn: ["miniapp-source-framework-detector"] },
  { name: "react-to-miniapp-analyzer", stage: "source-analysis", taskIds: ["MAPP-007", "MAPP-008"], dependsOn: ["miniapp-source-framework-detector"] },
  { name: "flutter-widget-semantic-reconstructor", stage: "source-analysis", taskIds: ["MAPP-009", "MAPP-010"], dependsOn: ["miniapp-source-framework-detector"] },
  { name: "miniapp-semantic-ir", stage: "ir", taskIds: ["MAPP-011", "MAPP-012"], dependsOn: ["vue-to-miniapp-analyzer", "react-to-miniapp-analyzer", "flutter-widget-semantic-reconstructor"] },
  { name: "miniapp-capability-registry", stage: "planning", taskIds: ["MAPP-013", "MAPP-014"], dependsOn: ["miniapp-semantic-ir"] },
  { name: "miniapp-component-mapping-engine", stage: "planning", taskIds: ["MAPP-015", "MAPP-016"], dependsOn: ["miniapp-semantic-ir", "miniapp-capability-registry"] },
  { name: "miniapp-state-event-lifecycle-converter", stage: "planning", taskIds: ["MAPP-017", "MAPP-018"], dependsOn: ["miniapp-semantic-ir", "miniapp-component-mapping-engine"] },
  { name: "miniapp-style-layout-converter", stage: "planning", taskIds: ["MAPP-019", "MAPP-020"], dependsOn: ["miniapp-semantic-ir", "miniapp-component-mapping-engine"] },
  { name: "miniapp-third-party-dependency-migrator", stage: "planning", taskIds: ["MAPP-021", "MAPP-022"], dependsOn: ["miniapp-source-framework-detector", "miniapp-capability-registry"] },
  { name: "wechat-miniapp-codegen", stage: "target-codegen", taskIds: ["MAPP-023"], dependsOn: ["miniapp-component-mapping-engine", "miniapp-state-event-lifecycle-converter", "miniapp-style-layout-converter", "miniapp-third-party-dependency-migrator"] },
  { name: "alipay-miniapp-codegen", stage: "target-codegen", taskIds: ["MAPP-024"], dependsOn: ["miniapp-component-mapping-engine", "miniapp-state-event-lifecycle-converter", "miniapp-style-layout-converter", "miniapp-third-party-dependency-migrator"] },
  { name: "douyin-miniapp-codegen", stage: "target-codegen", taskIds: ["MAPP-025"], dependsOn: ["miniapp-component-mapping-engine", "miniapp-state-event-lifecycle-converter", "miniapp-style-layout-converter", "miniapp-third-party-dependency-migrator"] },
  { name: "xiaohongshu-miniapp-codegen", stage: "target-codegen", taskIds: ["MAPP-026"], dependsOn: ["miniapp-component-mapping-engine", "miniapp-state-event-lifecycle-converter", "miniapp-style-layout-converter", "miniapp-third-party-dependency-migrator"] },
  { name: "miniapp-commerce-social-adapter", stage: "cross-cutting", taskIds: ["MAPP-027", "MAPP-028"], dependsOn: ["miniapp-capability-registry"] },
  { name: "miniapp-privacy-permission-auditor", stage: "validation", taskIds: ["MAPP-029", "MAPP-030"], dependsOn: ["miniapp-capability-registry", "miniapp-third-party-dependency-migrator", "wechat-miniapp-codegen", "alipay-miniapp-codegen", "douyin-miniapp-codegen", "xiaohongshu-miniapp-codegen"] },
  { name: "miniapp-differential-testing", stage: "validation", taskIds: ["MAPP-031", "MAPP-032"], dependsOn: ["wechat-miniapp-codegen", "alipay-miniapp-codegen", "douyin-miniapp-codegen", "xiaohongshu-miniapp-codegen"] },
  { name: "miniapp-visual-regression-testing", stage: "validation", taskIds: ["MAPP-033", "MAPP-034"], dependsOn: ["miniapp-style-layout-converter", "miniapp-differential-testing"] },
  { name: "miniapp-auto-repair-loop", stage: "repair", taskIds: ["MAPP-035", "MAPP-036"], dependsOn: ["miniapp-differential-testing", "miniapp-visual-regression-testing", "miniapp-privacy-permission-auditor"] },
  { name: "miniapp-ci-build-release", stage: "delivery", taskIds: ["MAPP-037", "MAPP-038"], dependsOn: ["miniapp-auto-repair-loop", "miniapp-privacy-permission-auditor"] },
  { name: "miniapp-migration-evidence-reporter", stage: "evidence", taskIds: ["MAPP-039", "MAPP-040"], dependsOn: ["miniapp-ci-build-release", "miniapp-differential-testing", "miniapp-visual-regression-testing", "miniapp-privacy-permission-auditor"] },
] as const;

export type MiniappSkillName = typeof MINIAPP_SKILL_CATALOG[number]["name"];
export type MiniappTaskId = typeof MINIAPP_SKILL_CATALOG[number]["taskIds"][number];
export type MiniappGateState = "PASSED" | "FAILED" | "BLOCKED" | "NOT_RUN";

const TARGET_BY_TASK: Readonly<Partial<Record<MiniappTaskId, MiniappPlatform>>> = {
  "MAPP-023": "wechat",
  "MAPP-024": "alipay",
  "MAPP-025": "douyin",
  "MAPP-026": "xiaohongshu",
};

export interface MiniappConversionExecutionInput {
  readonly schemaVersion: "1.0";
  readonly request: unknown;
  readonly files: readonly MiniappInventoryInputFile[];
  readonly localValidation?: unknown;
  readonly resumeFrom?: MiniappRunCheckpoint;
}

export interface MiniappRunCheckpoint {
  readonly schemaVersion: "1.0";
  readonly runId: string;
  readonly inputDigest: string;
  readonly idempotencyKey: string;
  readonly localValidationDigest: string | "NOT_RUN";
  readonly completedTaskIds: readonly MiniappTaskId[];
  readonly blockedTaskIds: readonly MiniappTaskId[];
  readonly checkpointDigest: string;
}

export interface MiniappTaskRecord {
  readonly taskId: MiniappTaskId;
  readonly skill: MiniappSkillName;
  readonly state: "EXECUTED_LOCAL" | "EXECUTED_LOCAL_EXTERNAL_PENDING" | "NOT_APPLICABLE" | "NOT_RUN_EXTERNAL" | "BLOCKED";
  readonly reason: string;
  readonly artifactDigests: readonly string[];
}

export interface MiniappGateDecision {
  readonly gate: `G${0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9}`;
  readonly state: MiniappGateState;
  readonly reason: string;
  readonly evidenceDigests: readonly string[];
}

export interface MiniappEvidenceNode {
  readonly id: string;
  readonly kind: "input" | "inventory" | "analysis" | "ir" | "plan" | "generated-project" | "gate";
  readonly digest: string;
  readonly byteCount: number;
  readonly state: MiniappGateState;
  readonly producer: string;
  readonly verifier: string;
  readonly synthetic: boolean;
}

export interface MiniappDifferentialStatus {
  readonly staticTraceCheck: "PASSED" | "BLOCKED";
  readonly traceCoverageByPlatform: Readonly<Record<MiniappPlatform, number | "NOT_REQUESTED">>;
  readonly sourceRuntimeCapture: "NOT_RUN";
  readonly targetRuntimeCapture: "NOT_RUN";
  readonly semanticParity: "NOT_ESTABLISHED";
  readonly findings: readonly string[];
}

export interface MiniappVisualStatus {
  readonly state: "NOT_RUN";
  readonly sourceScreenshots: "NOT_RUN";
  readonly targetScreenshots: "NOT_RUN";
  readonly requestedSimilarity: number;
  readonly reason: string;
}

export interface MiniappRepairStatus {
  readonly state: "PLAN_ONLY";
  readonly maximumIterations: number;
  readonly appliedIterations: 0;
  readonly candidates: readonly { readonly finding: string; readonly owner: "ir" | "mapping" | "adapter" | "generated-code"; readonly approvalRequired: boolean }[];
  readonly rollback: "NO_MUTATION_PERFORMED";
}

export interface MiniappDeliveryStatus {
  readonly state: "NOT_RUN";
  readonly profiles: readonly { readonly platform: MiniappPlatform; readonly toolchainVersion: string; readonly build: "NOT_RUN"; readonly preview: "NOT_RUN"; readonly upload: "NOT_RUN"; readonly review: "NOT_RUN"; readonly release: "NOT_RUN" }[];
  readonly approvalSeparation: readonly ["preview", "upload", "review", "release"];
  readonly credentials: "SECRET_REFERENCES_ONLY";
}

export interface MiniappConversionRun {
  readonly schemaVersion: "1.0";
  readonly runId: string;
  readonly request: MiniappConversionRequest;
  readonly requestDigest: string;
  readonly sourceFileSetDigest: string;
  readonly inputDigest: string;
  readonly inventory: MiniappSourceInventory;
  readonly analysis: MiniappSourceAnalysis;
  readonly semanticIr: MiniappSemanticIr;
  readonly plan: MiniappConversionPlan;
  readonly generatedProjects: readonly MiniappGeneratedProject[];
  readonly privacy: readonly MiniappPrivacyAudit[];
  readonly differential: MiniappDifferentialStatus;
  readonly visual: MiniappVisualStatus;
  readonly repair: MiniappRepairStatus;
  readonly delivery: MiniappDeliveryStatus;
  readonly localValidation: MiniappLocalValidationEvaluation;
  readonly taskRecords: readonly MiniappTaskRecord[];
  readonly gates: readonly MiniappGateDecision[];
  readonly evidenceGraph: readonly MiniappEvidenceNode[];
  readonly checkpoint: MiniappRunCheckpoint;
  readonly resumed: boolean;
  readonly localEngineering: "PASSED" | "BLOCKED";
  readonly readiness: "NOT_READY";
  readonly certification: "NOT_CERTIFIED";
  readonly deterministicDigest: string;
}

export interface MiniappSkillExecution {
  readonly schemaVersion: "1.0";
  readonly skill: MiniappSkillName;
  readonly state: "EXECUTED" | "NOT_APPLICABLE" | "NOT_RUN" | "BLOCKED";
  readonly taskRecords: readonly MiniappTaskRecord[];
  readonly payload: unknown;
  readonly declaredOutputs: readonly MiniappDeclaredOutputArtifact[];
  readonly runId: string;
  readonly inputDigest: string;
  readonly certification: "NOT_CERTIFIED";
  readonly deterministicDigest: string;
}

export type MiniappSkillHandlerRequest =
  | {
    readonly schemaVersion: "1.0";
    readonly action: "run-all";
    readonly conversion: MiniappConversionExecutionInput;
  }
  | {
    readonly schemaVersion: "1.0";
    readonly action: "run-skill";
    readonly skill: MiniappSkillName;
    readonly conversion: MiniappConversionExecutionInput;
  }
  | {
    readonly schemaVersion: "1.0";
    readonly action: "run-package";
    readonly packageInput: unknown;
  };

export interface MiniappPackageReleasePlan {
  readonly requestedMode: PackageConversionPolicyBinding["release"]["mode"];
  readonly state: "NOT_RUN";
  readonly humanApprovalRequired: boolean;
  readonly sideEffectsAuthorized: false;
  readonly credentialReferences: PackageConversionPolicyBinding["release"]["credentialReferences"];
  readonly stages: readonly {
    readonly stage: "build" | "preview" | "upload" | "review" | "release";
    readonly requested: boolean;
    readonly state: "NOT_RUN";
  }[];
  readonly reason: string;
}

export type MiniappPackageConversionRun = Omit<MiniappConversionRun, "deterministicDigest"> & {
  readonly executionDeterministicDigest: string;
  readonly packageRequestDigest: string;
  readonly inputBindingDigest: string;
  readonly sourceSnapshotDigest: string;
  readonly selectedSourceFileSetDigest: string;
  readonly policyBinding: PackageConversionPolicyBinding;
  readonly releasePlan: MiniappPackageReleasePlan;
  readonly deterministicDigest: string;
};

interface MiniappRuntimeQualityPolicy {
  readonly visualSimilarityMin: number;
  readonly criticalFlowPassRate: number;
  readonly maxAutoRepairIterations: number;
}

const DEFAULT_RUNTIME_QUALITY_POLICY: MiniappRuntimeQualityPolicy = {
  visualSimilarityMin: 0.95,
  criticalFlowPassRate: 1,
  maxAutoRepairIterations: 3,
};

function rawDigest(value: string | Uint8Array): string {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

function byteLength(value: string): number {
  return Buffer.byteLength(value, "utf8");
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Readonly<Record<string, unknown>>)
      .filter(([, item]) => item !== undefined)
      .sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function checkpointDigest(value: Omit<MiniappRunCheckpoint, "checkpointDigest">): string {
  return miniappIrDigest(value);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
    && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
}

function exactKeys(value: Record<string, unknown>, allowed: readonly string[], required: readonly string[], path: string): void {
  for (const key of required) if (!Object.hasOwn(value, key)) throw new Error(`${path}.${key} is required`);
  for (const key of Object.keys(value)) if (!allowed.includes(key)) throw new Error(`${path}.${key} is not allowed`);
}

function textFiles(files: readonly MiniappInventoryInputFile[]): Readonly<Record<string, string>> {
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const output = Object.create(null) as Record<string, string>;
  for (const [index, file] of files.entries()) {
    try {
      const path = normalizeMiniappRelativePath(file.path, `files[${index}].path`);
      output[path] = typeof file.content === "string" ? file.content : decoder.decode(file.content);
    } catch {
      // Binary inputs remain inventoried and content-addressed but are never parsed as source.
    }
  }
  return output;
}

/** Digest algorithm is identical to the inventory contract: path, raw digest and byte count. */
export function computeMiniappSourceFileSetDigest(files: readonly MiniappInventoryInputFile[]): string {
  if (!Array.isArray(files) || files.length === 0 || files.length > MINIAPP_INVENTORY_HARD_LIMITS.maxFileCount) {
    throw new Error(`files must contain 1 through ${MINIAPP_INVENTORY_HARD_LIMITS.maxFileCount} entries`);
  }
  const seen = new Set<string>();
  let totalBytes = 0;
  const normalized = files.map((file, index) => {
    if (!isPlainObject(file)) throw new Error(`files[${index}] must be an object`);
    exactKeys(file as unknown as Record<string, unknown>, ["path", "content"], ["path", "content"], `files[${index}]`);
    const path = normalizeMiniappRelativePath(file.path, `files[${index}].path`);
    if (seen.has(path)) throw new Error(`files[${index}].path duplicates ${path}`);
    seen.add(path);
    if (typeof file.content !== "string" && !(file.content instanceof Uint8Array)) {
      throw new Error(`files[${index}].content must be a string or Uint8Array`);
    }
    const bytes = typeof file.content === "string" ? Buffer.from(file.content, "utf8") : file.content;
    if (bytes.byteLength > MINIAPP_INVENTORY_HARD_LIMITS.maxFileBytes) {
      throw new Error(`files[${index}].content exceeds ${MINIAPP_INVENTORY_HARD_LIMITS.maxFileBytes} bytes`);
    }
    totalBytes += bytes.byteLength;
    if (!Number.isSafeInteger(totalBytes) || totalBytes > MINIAPP_INVENTORY_HARD_LIMITS.maxTotalBytes) {
      throw new Error(`files content exceeds ${MINIAPP_INVENTORY_HARD_LIMITS.maxTotalBytes} bytes`);
    }
    return { path, digest: rawDigest(bytes), byteCount: bytes.byteLength };
  }).sort((left, right) => left.path < right.path ? -1 : left.path > right.path ? 1 : 0);
  return rawDigest(normalized.map(file => `${file.path}\u0000${file.digest}\u0000${file.byteCount}`).join("\n"));
}

function validateCheckpoint(
  value: MiniappRunCheckpoint,
  runId: string,
  inputDigest: string,
  localValidationDigest: string | "NOT_RUN",
): void {
  if (!isPlainObject(value)) throw new Error("resumeFrom must be an object");
  exactKeys(value as unknown as Record<string, unknown>, ["schemaVersion", "runId", "inputDigest", "idempotencyKey", "localValidationDigest", "completedTaskIds", "blockedTaskIds", "checkpointDigest"], ["schemaVersion", "runId", "inputDigest", "idempotencyKey", "localValidationDigest", "completedTaskIds", "blockedTaskIds", "checkpointDigest"], "resumeFrom");
  if (value.schemaVersion !== "1.0" || value.runId !== runId || value.inputDigest !== inputDigest) throw new Error("resume checkpoint does not belong to this exact input");
  if (value.localValidationDigest !== localValidationDigest) throw new Error("resume checkpoint does not belong to this exact local validation input");
  const { checkpointDigest: supplied, ...base } = value;
  if (checkpointDigest(base) !== supplied) throw new Error("resume checkpoint digest mismatch");
}

function artifactNode(
  id: string,
  kind: MiniappEvidenceNode["kind"],
  content: string,
  state: MiniappGateState,
  synthetic = false,
): MiniappEvidenceNode {
  return {
    id,
    kind,
    digest: rawDigest(content),
    byteCount: byteLength(content),
    state,
    producer: "@elmos/frontend-client-engine",
    verifier: "local-deterministic-validator",
    synthetic,
  };
}

function differentialStatus(ir: MiniappSemanticIr, projects: readonly MiniappGeneratedProject[]): MiniappDifferentialStatus {
  const requested = new Map(projects.map(project => [project.platform, project]));
  const coverage = Object.fromEntries((["wechat", "alipay", "douyin", "xiaohongshu"] as const).map(platform => {
    const project = requested.get(platform);
    if (!project) return [platform, "NOT_REQUESTED"] as const;
    const traced = new Set(project.artifacts.filter(artifact => artifact.role === "runtime").flatMap(artifact => artifact.sourceNodeIds));
    return [platform, ir.nodes.length === 0 ? 0 : ir.nodes.filter(node => traced.has(node.id)).length / ir.nodes.length] as const;
  })) as Readonly<Record<MiniappPlatform, number | "NOT_REQUESTED">>;
  const findings = projects.flatMap(project => {
    const platformCoverage = coverage[project.platform];
    return [
      ...(project.staticValidation === "PASSED" ? [] : [`${project.platform}:STATIC_VALIDATION_BLOCKED`]),
      ...(project.status === "GENERATED" ? [] : [`${project.platform}:CONVERSION_PLAN_BLOCKED`]),
      ...(typeof platformCoverage === "number" && platformCoverage < 1 ? [`${project.platform}:EXECUTABLE_TRACE_INCOMPLETE:${platformCoverage}`] : []),
    ];
  });
  return {
    staticTraceCheck: findings.length === 0 ? "PASSED" : "BLOCKED",
    traceCoverageByPlatform: coverage,
    sourceRuntimeCapture: "NOT_RUN",
    targetRuntimeCapture: "NOT_RUN",
    semanticParity: "NOT_ESTABLISHED",
    findings,
  };
}

function taskState(
  taskId: MiniappTaskId,
  request: MiniappConversionRequest,
  localBlocked: boolean,
  localValidation: MiniappLocalValidationEvaluation,
): MiniappTaskRecord["state"] {
  const target = TARGET_BY_TASK[taskId];
  if (target && !request.targets.some(item => item.platform === target)) return "NOT_APPLICABLE";
  if (["MAPP-005", "MAPP-006"].includes(taskId) && !["vue2", "vue3", "uni-app"].includes(request.source.sourceLabel)) return "NOT_APPLICABLE";
  if (["MAPP-007", "MAPP-008"].includes(taskId) && !["react", "typescript", "javascript", "h5", "taro"].includes(request.source.sourceLabel)) return "NOT_APPLICABLE";
  if (["MAPP-009", "MAPP-010"].includes(taskId) && request.source.sourceLabel !== "flutter") return "NOT_APPLICABLE";
  if (taskId === "MAPP-022") return "NOT_RUN_EXTERNAL";
  if (["MAPP-031", "MAPP-032"].includes(taskId)) {
    return localValidation.differential.state === "NOT_RUN" ? "NOT_RUN_EXTERNAL" : "EXECUTED_LOCAL_EXTERNAL_PENDING";
  }
  if (["MAPP-033", "MAPP-034"].includes(taskId)) {
    return localValidation.visual.state === "NOT_RUN" ? "NOT_RUN_EXTERNAL" : "EXECUTED_LOCAL_EXTERNAL_PENDING";
  }
  if (["MAPP-035", "MAPP-036"].includes(taskId)) {
    return localValidation.repair.state === "NOT_RUN" ? "NOT_RUN_EXTERNAL" : "EXECUTED_LOCAL_EXTERNAL_PENDING";
  }
  if (["MAPP-037", "MAPP-038"].includes(taskId)) return "NOT_RUN_EXTERNAL";
  return localBlocked ? "BLOCKED" : "EXECUTED_LOCAL";
}

function taskRecords(
  request: MiniappConversionRequest,
  localBlocked: boolean,
  artifacts: readonly MiniappEvidenceNode[],
  localValidation: MiniappLocalValidationEvaluation,
): readonly MiniappTaskRecord[] {
  const digests = artifacts.map(item => item.digest);
  return MINIAPP_SKILL_CATALOG.flatMap(skill => skill.taskIds.map(taskId => {
  const state = taskState(taskId, request, localBlocked, localValidation);
    const targetTask = Boolean(TARGET_BY_TASK[taskId]);
    return {
      taskId,
      skill: skill.name,
      state,
      reason: state === "EXECUTED_LOCAL" ? "Deterministic local handler executed and emitted content-addressed output."
        : state === "EXECUTED_LOCAL_EXTERNAL_PENDING" ? "Bounded local candidate executed; official runtime/device/release evidence remains pending."
        : state === "NOT_APPLICABLE" ? targetTask
          ? "The exact request does not select this target platform."
          : `The exact source label ${request.source.sourceLabel} does not select this analyzer.`
          : state === "NOT_RUN_EXTERNAL" ? "Required official toolchain, runtime, screenshot or release-side evidence was not executed."
            : "A local fail-closed prerequisite is unresolved.",
      artifactDigests:
        state === "EXECUTED_LOCAL"
          ? digests
          : state === "EXECUTED_LOCAL_EXTERNAL_PENDING"
            ? [
              ...digests,
              ...(localValidation.inputDigest === "NOT_RUN" ? [] : [localValidation.inputDigest]),
            ]
            : [],
    };
  }));
}

function gateDecisions(
  request: MiniappConversionRequest,
  inventory: MiniappSourceInventory,
  analysis: MiniappSourceAnalysis,
  ir: MiniappSemanticIr,
  plan: MiniappConversionPlan,
  projects: readonly MiniappGeneratedProject[],
  differential: MiniappDifferentialStatus,
  privacy: readonly MiniappPrivacyAudit[],
  evidence: readonly MiniappEvidenceNode[],
): readonly MiniappGateDecision[] {
  // Self-attested local validation candidates are deliberately excluded from
  // structural gate evidence; they can inform pending work but cannot satisfy
  // an external or certification gate.
  const digests = evidence.filter(item => !item.synthetic).map(item => item.digest);
  const g1 = inventory.coverage.ratio === 1 && inventory.findings.every(item => !item.blocking)
    && inventory.selectedSourceLabel === request.source.sourceLabel;
  const g2 = analysis.coverage === 1 && analysis.failedFiles.length === 0 && ir.coverage.tracedNodes === 1;
  const g3 = plan.findings.every(item => !item.blocking) && plan.capabilities.every(item => Boolean(item.strategy));
  const generated = projects.length === request.targets.length
    && projects.every(item => item.staticValidation === "PASSED" && item.status === "GENERATED")
    && differential.staticTraceCheck === "PASSED";
  const privacyStatic = privacy.every(item => item.secretFindings.length === 0 && item.staticAudit === "EXECUTED");
  return [
    { gate: "G0", state: "PASSED", reason: "Request shape, references-only secrets and source snapshot digest were validated; source/target version support is decided at G3 and installed official runtimes remain NOT_RUN.", evidenceDigests: digests },
    { gate: "G1", state: g1 ? "PASSED" : "BLOCKED", reason: g1 ? "In-memory inventory covered every supplied file and selected the requested framework with evidence." : "Inventory coverage, framework selection or conflict requirements are unresolved.", evidenceDigests: digests },
    { gate: "G2", state: g2 ? "PASSED" : "BLOCKED", reason: g2 ? "Applicable parser completed and every IR node has a closed source trace." : "Parser or source-to-IR trace coverage is incomplete.", evidenceDigests: digests },
    { gate: "G3", state: g3 ? "PASSED" : "BLOCKED", reason: g3 ? "Capabilities, components, state, styles and dependencies have explicit decisions." : "At least one blocking or undecided conversion finding remains.", evidenceDigests: digests },
    { gate: "G4", state: generated ? "NOT_RUN" : "BLOCKED", reason: generated ? "Native project candidates passed static validation and executable trace closure; official platform CLI/IDE builds are NOT_RUN." : "Generated project static validation, plan state or executable trace closure is blocked.", evidenceDigests: digests },
    { gate: "G5", state: "NOT_RUN", reason: "Source and target runtime behavior traces, sandbox flows and failure semantics were not executed.", evidenceDigests: [] },
    { gate: "G6", state: "NOT_RUN", reason: "Deterministic screenshots, device matrix and visual/interaction comparison were not executed.", evidenceDigests: [] },
    { gate: "G7", state: "NOT_RUN", reason: "Startup, navigation, long-list, memory, network and package-size measurements were not executed.", evidenceDigests: [] },
    { gate: "G8", state: privacyStatic ? "NOT_RUN" : "FAILED", reason: privacyStatic ? "Static privacy/secret audit executed; platform review, dependency license/vulnerability and payment sandbox evidence remain NOT_RUN." : "Static privacy or secret audit failed.", evidenceDigests: privacyStatic ? digests : [] },
    { gate: "G9", state: "NOT_RUN", reason: "Independent approvals, uploads, platform receipts, review and release are intentionally NOT_RUN.", evidenceDigests: [] },
  ];
}

function executeMiniappConversion(
  input: MiniappConversionExecutionInput,
  qualityPolicy: MiniappRuntimeQualityPolicy,
): MiniappConversionRun {
  if (!isPlainObject(input)) throw new Error("conversion must be an object");
  exactKeys(input as unknown as Record<string, unknown>, ["schemaVersion", "request", "files", "localValidation", "resumeFrom"], ["schemaVersion", "request", "files"], "conversion");
  if (input.schemaVersion !== "1.0" || !Array.isArray(input.files) || input.files.length === 0) throw new Error("conversion requires schemaVersion 1.0 and at least one file");
  const request = validateMiniappConversionRequest(input.request);
  const inventory = inventoryMiniappSource({
    schemaVersion: "1.0",
    inventoryId: `inv-${request.requestId.replace(/^conv-/, "")}`,
    sourceRevision: request.source.revision,
    sourceSnapshotDigest: request.source.snapshotDigest,
    sourceLabelHint: request.source.sourceLabel,
    limits: request.policy.limits,
    files: input.files,
  });
  if (inventory.fileSetDigest !== request.source.snapshotDigest) {
    throw new Error(`source snapshot digest mismatch: request=${request.source.snapshotDigest} actual=${inventory.fileSetDigest}`);
  }
  const sourceFiles = textFiles(input.files);
  const analysis = analyzeMiniappSource(request, inventory, sourceFiles);
  const semanticIr = buildMiniappSemanticIr(request, inventory, analysis);
  const plan = planMiniappConversion(semanticIr, request, inventory);
  const generatedProjects = generateAllMiniappTargets(semanticIr, plan, request, inventory);
  const privacy = auditMiniappPrivacy(semanticIr, request, sourceFiles);
  const differential = differentialStatus(semanticIr, generatedProjects);
  const visual: MiniappVisualStatus = {
    state: "NOT_RUN", sourceScreenshots: "NOT_RUN", targetScreenshots: "NOT_RUN",
    requestedSimilarity: qualityPolicy.visualSimilarityMin,
    reason: "No browser/device screenshot executor was authorized for this local conversion run.",
  };
  const repairFindings = [...new Set([
    ...plan.findings.map(item => `${item.platform}:${item.classification}:${item.code}`),
    ...generatedProjects.flatMap(item => item.findings.map(finding => `${item.platform}:${finding}`)),
  ])].sort();
  const repair: MiniappRepairStatus = {
    state: "PLAN_ONLY", maximumIterations: qualityPolicy.maxAutoRepairIterations,
    appliedIterations: 0,
    candidates: repairFindings.map(finding => ({
      finding,
      owner: finding.includes("STYLE") ? "mapping" : finding.includes("CAPABILITY") ? "adapter" : "ir",
      approvalRequired: /:D:|:E:|SECRET|PRIVACY/.test(finding),
    })),
    rollback: "NO_MUTATION_PERFORMED",
  };
  const localValidation = evaluateMiniappLocalValidation(input.localValidation, {
    targets: generatedProjects.map(project => ({
      platform: project.platform,
      toolchainVersion: project.toolchainVersion,
      // The local validation contract binds to the exact evidence-node digest,
      // not merely the generator's internal project digest.
      projectDigest: rawDigest(canonicalJson(project)),
    })),
    requestedSimilarity: qualityPolicy.visualSimilarityMin,
    criticalFlowPassRate: qualityPolicy.criticalFlowPassRate,
    maximumRepairIterations: qualityPolicy.maxAutoRepairIterations,
    repairFindings: repair.candidates,
  });
  const delivery: MiniappDeliveryStatus = {
    state: "NOT_RUN",
    profiles: request.targets.map(target => ({ platform: target.platform, toolchainVersion: target.toolchainVersion, build: "NOT_RUN", preview: "NOT_RUN", upload: "NOT_RUN", review: "NOT_RUN", release: "NOT_RUN" })),
    approvalSeparation: ["preview", "upload", "review", "release"], credentials: "SECRET_REFERENCES_ONLY",
  };
  const requestText = canonicalizeMiniappConversionRequest(request);
  const inventoryText = canonicalizeMiniappSourceInventory(inventory);
  const analysisText = canonicalizeMiniappSourceAnalysis(analysis);
  const irText = canonicalizeMiniappSemanticIr(semanticIr);
  const planText = canonicalJson(plan);
  const requestDigest = rawDigest(requestText);
  const inputDigest = miniappIrDigest({
    requestDigest,
    sourceFileSetDigest: inventory.fileSetDigest,
    localValidationDigest: localValidation.inputDigest,
  });
  const runId = `miniapp-run-${request.requestId}-${inputDigest.slice(-16)}`;
  if (input.resumeFrom) validateCheckpoint(input.resumeFrom, runId, inputDigest, localValidation.inputDigest);
  const evidence: MiniappEvidenceNode[] = [
    artifactNode("request", "input", requestText, "PASSED"),
    artifactNode("inventory", "inventory", inventoryText, inventory.findings.some(item => item.blocking) ? "BLOCKED" : "PASSED"),
    artifactNode("analysis", "analysis", analysisText, analysis.failedFiles.length > 0 ? "BLOCKED" : "PASSED"),
    artifactNode("semantic-ir", "ir", irText, semanticIr.coverage.unresolvedCritical > 0 ? "BLOCKED" : "PASSED"),
    artifactNode("conversion-plan", "plan", planText, plan.findings.some(item => item.blocking) ? "BLOCKED" : "PASSED"),
    ...generatedProjects.map(project => artifactNode(
      `project-${project.platform}`,
      "generated-project",
      canonicalJson(project),
      project.staticValidation === "PASSED" && project.status === "GENERATED" ? "PASSED" : "BLOCKED",
    )),
    artifactNode("static-executable-trace", "gate", canonicalJson({
      staticTraceCheck: differential.staticTraceCheck,
      traceCoverageByPlatform: differential.traceCoverageByPlatform,
      findings: differential.findings,
    }), differential.staticTraceCheck === "PASSED" ? "PASSED" : "BLOCKED"),
    artifactNode(
      "local-validation-candidate",
      "gate",
      canonicalJson(localValidation),
      localValidation.evidenceBoundary.localCandidate === "NOT_RUN" ? "NOT_RUN" : "BLOCKED",
      true,
    ),
  ];
  const localBlocked = evidence.some(item => !item.synthetic && (item.state === "BLOCKED" || item.state === "FAILED"));
  const records = taskRecords(request, localBlocked, evidence.filter(item => !item.synthetic), localValidation);
  const gates = gateDecisions(request, inventory, analysis, semanticIr, plan, generatedProjects, differential, privacy, evidence);
  const completedTaskIds = records.filter(item => item.state === "EXECUTED_LOCAL" || item.state === "NOT_APPLICABLE").map(item => item.taskId);
  const blockedTaskIds = records.filter(item => item.state === "BLOCKED" || item.state === "NOT_RUN_EXTERNAL").map(item => item.taskId);
  const checkpointBase = {
    schemaVersion: "1.0" as const,
    runId,
    inputDigest,
    idempotencyKey: miniappIrDigest({ tenantId: request.tenantId, requestId: request.requestId, inputDigest }),
    localValidationDigest: localValidation.inputDigest,
    completedTaskIds,
    blockedTaskIds,
  };
  const checkpoint: MiniappRunCheckpoint = { ...checkpointBase, checkpointDigest: checkpointDigest(checkpointBase) };
  const base = {
    schemaVersion: "1.0" as const,
    runId, request, requestDigest, sourceFileSetDigest: inventory.fileSetDigest, inputDigest,
    inventory, analysis, semanticIr, plan, generatedProjects, privacy, differential, visual, repair, delivery, localValidation,
    taskRecords: records, gates, evidenceGraph: evidence, checkpoint, resumed: Boolean(input.resumeFrom),
    localEngineering: gates.slice(0, 4).every(gate => gate.state === "PASSED")
      && differential.staticTraceCheck === "PASSED"
      ? "PASSED" as const
      : "BLOCKED" as const,
    readiness: "NOT_READY" as const,
    certification: "NOT_CERTIFIED" as const,
  };
  return { ...base, deterministicDigest: miniappIrDigest(base) };
}

export function runMiniappConversion(input: MiniappConversionExecutionInput): MiniappConversionRun {
  return executeMiniappConversion(input, DEFAULT_RUNTIME_QUALITY_POLICY);
}

function packageReleasePlan(
  policy: PackageConversionPolicyBinding["release"],
): MiniappPackageReleasePlan {
  const stages = ["build", "preview", "upload", "review", "release"] as const;
  const requestedIndex = policy.mode === "build-only" ? 0 : stages.indexOf(policy.mode);
  return {
    requestedMode: policy.mode,
    state: "NOT_RUN",
    humanApprovalRequired: policy.humanApprovalRequired,
    sideEffectsAuthorized: false,
    credentialReferences: policy.credentialReferences,
    stages: stages.map((stage, index) => ({
      stage,
      requested: index <= requestedIndex,
      state: "NOT_RUN" as const,
    })),
    reason: "This handler only creates deterministic local candidates; official builds and release-side actions require separately authorized external execution evidence.",
  };
}

export function runMiniappPackageConversion(value: unknown): MiniappPackageConversionRun {
  const compiled = compileMiniappPackageConversionInput(value);
  const run = executeMiniappConversion(compiled.executionInput, {
    visualSimilarityMin: compiled.policyBinding.quality.visualSimilarityMin,
    criticalFlowPassRate: compiled.policyBinding.quality.criticalFlowPassRate,
    maxAutoRepairIterations: compiled.policyBinding.quality.maxAutoRepairIterations,
  });
  const { deterministicDigest: executionDeterministicDigest, ...execution } = run;
  const base = {
    ...execution,
    executionDeterministicDigest,
    packageRequestDigest: compiled.packageRequestDigest,
    inputBindingDigest: compiled.inputBindingDigest,
    sourceSnapshotDigest: compiled.sourceSnapshotDigest,
    selectedSourceFileSetDigest: compiled.selectedSourceFileSetDigest,
    policyBinding: compiled.policyBinding,
    releasePlan: packageReleasePlan(compiled.policyBinding.release),
  };
  return { ...base, deterministicDigest: miniappIrDigest(base) };
}

function platformForSkill(skill: MiniappSkillName): MiniappPlatform | undefined {
  if (skill === "wechat-miniapp-codegen") return "wechat";
  if (skill === "alipay-miniapp-codegen") return "alipay";
  if (skill === "douyin-miniapp-codegen") return "douyin";
  if (skill === "xiaohongshu-miniapp-codegen") return "xiaohongshu";
  return undefined;
}

function payloadForSkill(skill: MiniappSkillName, run: MiniappConversionRun): unknown {
  const platform = platformForSkill(skill);
  if (platform) return run.generatedProjects.find(item => item.platform === platform) ?? { state: "NOT_APPLICABLE", platform };
  switch (skill) {
    case "frontend-to-miniapp-orchestrator": return { checkpoint: run.checkpoint, gates: run.gates, readiness: run.readiness, localValidation: run.localValidation };
    case "miniapp-source-framework-detector": return run.inventory;
    case "vue-to-miniapp-analyzer": return ["vue2", "vue3", "uni-app"].includes(run.request.source.sourceLabel) ? run.analysis : { state: "NOT_APPLICABLE", sourceLabel: run.request.source.sourceLabel };
    case "react-to-miniapp-analyzer": return ["react", "typescript", "javascript", "h5", "taro"].includes(run.request.source.sourceLabel) ? run.analysis : { state: "NOT_APPLICABLE", sourceLabel: run.request.source.sourceLabel };
    case "flutter-widget-semantic-reconstructor": return run.request.source.sourceLabel === "flutter" ? run.analysis : { state: "NOT_APPLICABLE", sourceLabel: run.request.source.sourceLabel };
    case "miniapp-semantic-ir": return run.semanticIr;
    case "miniapp-capability-registry": return { platformProfiles: run.plan.platformProfiles, capabilities: run.plan.capabilities, findings: run.plan.findings };
    case "miniapp-component-mapping-engine": return run.plan.components;
    case "miniapp-state-event-lifecycle-converter": return run.plan.stateLifecycle;
    case "miniapp-style-layout-converter": return run.plan.styles;
    case "miniapp-third-party-dependency-migrator": return run.plan.dependencies;
    case "miniapp-commerce-social-adapter": return run.plan.commerceSocial;
    case "miniapp-privacy-permission-auditor": return run.privacy;
    case "miniapp-differential-testing": return { local: run.localValidation.differential, external: run.differential };
    case "miniapp-visual-regression-testing": return { local: run.localValidation.visual, external: run.visual };
    case "miniapp-auto-repair-loop": return { local: run.localValidation.repair, external: run.repair };
    case "miniapp-ci-build-release": return run.delivery;
    case "miniapp-migration-evidence-reporter": return { gates: run.gates, evidenceGraph: run.evidenceGraph, taskRecords: run.taskRecords, readiness: run.readiness, certification: run.certification };
  }
}

export function executeMiniappSkill(skill: MiniappSkillName, input: MiniappConversionExecutionInput): MiniappSkillExecution {
  const catalog = MINIAPP_SKILL_CATALOG.find(item => item.name === skill);
  if (!catalog) throw new Error(`unknown miniapp skill: ${String(skill)}`);
  const run = runMiniappConversion(input);
  const records = run.taskRecords.filter(item => item.skill === skill);
  const state = records.every(item => item.state === "NOT_APPLICABLE")
    || (platformForSkill(skill) && !run.request.targets.some(item => item.platform === platformForSkill(skill)))
    ? "NOT_APPLICABLE" as const
    : records.some(item => item.state === "BLOCKED") ? "BLOCKED" as const
      : records.some(item => item.state === "NOT_RUN_EXTERNAL") ? "NOT_RUN" as const
        : "EXECUTED" as const;
  const declaredOutputs = materializeMiniappDeclaredOutputs(run).filter(
    artifact => artifact.ownerSkill === skill,
  );
  const outputContract = MINIAPP_DECLARED_OUTPUT_CATALOG.find(
    candidate => candidate.ownerSkill === skill,
  );
  if (!outputContract) throw new Error(`missing declared output contract for miniapp Skill: ${skill}`);
  const expectedPatterns = new Set<string>(outputContract.requiredOutputs);
  if (declaredOutputs.length !== expectedPatterns.size
    || declaredOutputs.some(artifact => !expectedPatterns.delete(artifact.declaredPattern))
    || expectedPatterns.size !== 0) {
    throw new Error(`declared output contract mismatch for miniapp Skill: ${skill}`);
  }
  const base = {
    schemaVersion: "1.0" as const,
    skill,
    state,
    taskRecords: records,
    payload: payloadForSkill(skill, run),
    declaredOutputs,
    runId: run.runId,
    inputDigest: run.inputDigest,
    certification: "NOT_CERTIFIED" as const,
  };
  return { ...base, deterministicDigest: miniappIrDigest(base) };
}

export function handleMiniappSkillRequest(
  value: unknown,
): MiniappConversionRun | MiniappSkillExecution | MiniappPackageConversionRun {
  if (!isPlainObject(value)) throw new Error("handler request must be an object");
  exactKeys(value, ["schemaVersion", "action", "skill", "conversion", "packageInput"], ["schemaVersion", "action"], "handlerRequest");
  if (value.schemaVersion !== "1.0"
    || (value.action !== "run-all" && value.action !== "run-skill" && value.action !== "run-package")) {
    throw new Error("handler request schemaVersion/action is invalid");
  }
  if (value.action === "run-package") {
    exactKeys(value, ["schemaVersion", "action", "packageInput"], ["schemaVersion", "action", "packageInput"], "handlerRequest");
    return runMiniappPackageConversion(value.packageInput);
  }
  if (value.action === "run-all") {
    exactKeys(value, ["schemaVersion", "action", "conversion"], ["schemaVersion", "action", "conversion"], "handlerRequest");
    if (!isPlainObject(value.conversion)) throw new Error("handlerRequest.conversion must be an object");
    return runMiniappConversion(value.conversion as unknown as MiniappConversionExecutionInput);
  }
  exactKeys(value, ["schemaVersion", "action", "skill", "conversion"], ["schemaVersion", "action", "skill", "conversion"], "handlerRequest");
  if (!isPlainObject(value.conversion)) throw new Error("handlerRequest.conversion must be an object");
  if (typeof value.skill !== "string" || !MINIAPP_SKILL_CATALOG.some(item => item.name === value.skill)) throw new Error("handlerRequest.skill must be an installed miniapp Skill name");
  return executeMiniappSkill(value.skill as MiniappSkillName, value.conversion as unknown as MiniappConversionExecutionInput);
}

export function runMiniappSkillJson(input: string): string {
  if (Buffer.byteLength(input, "utf8") > 32 * 1024 * 1024) throw new Error("miniapp handler JSON exceeds 32 MiB");
  let value: unknown;
  try { value = JSON.parse(input); } catch { throw new Error("miniapp handler input must be valid JSON"); }
  return `${JSON.stringify(handleMiniappSkillRequest(value), null, 2)}\n`;
}

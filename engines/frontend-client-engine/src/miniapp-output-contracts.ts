import { createHash } from "node:crypto";
import { posix } from "node:path";

import type {
  MiniappConversionRun,
  MiniappSkillName,
  MiniappTaskId,
} from "./miniapp-skill-runtime.js";
import type { MiniappPlatform } from "./miniapp-types.js";

export type MiniappDeclaredOutputState =
  | "PASSED_LOCAL"
  | "BLOCKED"
  | "NOT_RUN"
  | "NOT_APPLICABLE";

export interface MiniappDeclaredOutputContract {
  readonly ownerSkill: MiniappSkillName;
  readonly taskIds: readonly MiniappTaskId[];
  readonly requiredOutputs: readonly string[];
}

export interface MiniappDeclaredOutputArtifact {
  readonly ownerSkill: MiniappSkillName;
  readonly declaredPattern: string;
  readonly materializedPath: string;
  readonly state: MiniappDeclaredOutputState;
  readonly content: string;
  readonly digest: string;
  readonly bytes: number;
}

export interface MiniappGeneratedProjectArtifact {
  readonly ownerSkill: MiniappSkillName;
  readonly platform: MiniappPlatform;
  readonly declaredPattern: `platforms/${MiniappPlatform}/**`;
  readonly declaredBasePath: string;
  readonly sourcePath: string;
  readonly materializedPath: string;
  readonly state: "PASSED_LOCAL";
  readonly content: string;
  readonly digest: string;
  readonly bytes: number;
}

export const MINIAPP_CANONICAL_SCHEMA_FILES = [
  "capability-registry-entry.schema.json",
  "compatibility-report.schema.json",
  "component-mapping.schema.json",
  "conversion-request.schema.json",
  "dependency-migration-plan.schema.json",
  "differential-result.schema.json",
  "migration-evidence.schema.json",
  "platform-profile.schema.json",
  "privacy-report.schema.json",
  "project-inventory.schema.json",
  "repair-action.schema.json",
  "semantic-ir.schema.json",
  "source-analysis.schema.json",
  "test-plan.schema.json",
] as const;

export type MiniappCanonicalSchemaFile =
  (typeof MINIAPP_CANONICAL_SCHEMA_FILES)[number];

export interface MiniappDeclaredOutputArtifactIndexEntry {
  readonly artifact_id: string;
  readonly owner_skill: MiniappSkillName;
  readonly task_ids: readonly MiniappTaskId[];
  readonly declared_pattern: string;
  readonly materialized_path: string;
  readonly state: MiniappDeclaredOutputState;
  readonly digest: string;
  readonly bytes: number;
  readonly schema: `schemas/${MiniappCanonicalSchemaFile}` | null;
}

export type MiniappOutputArtifactIndexEntry = MiniappDeclaredOutputArtifactIndexEntry;

export interface MiniappOutputPathTokens {
  readonly "run-id": string;
  readonly target: string;
  readonly framework: string;
}

export interface MiniappDeclaredOutputCatalogSummary {
  readonly skills: number;
  readonly tasks: number;
  readonly requiredOutputs: number;
}

interface MiniappDeclaredOutputSchemaBinding {
  readonly ownerSkill: MiniappSkillName;
  readonly declaredPattern: string;
  readonly schema: MiniappCanonicalSchemaFile;
}

/*
 * Canonical transcription of the immutable package output contracts under
 * skills/elmos-frontend-to-miniapp-skills-v1.0.0/.agents/skills. Keep the
 * declarations verbatim: declaredPattern is provenance, not a file-system
 * suggestion.
 */
export const MINIAPP_DECLARED_OUTPUT_CATALOG = [
  {
    ownerSkill: "frontend-to-miniapp-orchestrator",
    taskIds: ["MAPP-001", "MAPP-002"],
    requiredOutputs: [
      "runs/<run-id>/state.json",
      "runs/<run-id>/plan.json",
      "runs/<run-id>/artifacts-index.json",
      "最终 migration-evidence.json 与兼容性报告",
    ],
  },
  {
    ownerSkill: "miniapp-source-framework-detector",
    taskIds: ["MAPP-003", "MAPP-004"],
    requiredOutputs: [
      "project-inventory.json",
      "framework-detection.json",
      "entrypoint-map.json",
      "unresolved-signals.json",
    ],
  },
  {
    ownerSkill: "vue-to-miniapp-analyzer",
    taskIds: ["MAPP-005", "MAPP-006"],
    requiredOutputs: [
      "vue-analysis.json",
      "component-graph.json",
      "route-graph.json",
      "state-graph.json",
      "source-trace-map.json",
    ],
  },
  {
    ownerSkill: "react-to-miniapp-analyzer",
    taskIds: ["MAPP-007", "MAPP-008"],
    requiredOutputs: [
      "react-analysis.json",
      "component-graph.json",
      "hook-effect-graph.json",
      "route-graph.json",
      "source-trace-map.json",
    ],
  },
  {
    ownerSkill: "flutter-widget-semantic-reconstructor",
    taskIds: ["MAPP-009", "MAPP-010"],
    requiredOutputs: [
      "flutter-analysis.json",
      "widget-tree.json",
      "navigation-graph.json",
      "state-graph.json",
      "platform-channel-report.json",
    ],
  },
  {
    ownerSkill: "miniapp-semantic-ir",
    taskIds: ["MAPP-011", "MAPP-012"],
    requiredOutputs: [
      "semantic-ir.json",
      "ir-validation.json",
      "ir-trace-index.json",
      "ir-migration-log.json",
    ],
  },
  {
    ownerSkill: "miniapp-capability-registry",
    taskIds: ["MAPP-013", "MAPP-014"],
    requiredOutputs: [
      "capability-resolution.json",
      "compatibility-findings.json",
      "required-permissions.json",
      "backend-requirements.json",
    ],
  },
  {
    ownerSkill: "miniapp-component-mapping-engine",
    taskIds: ["MAPP-015", "MAPP-016"],
    requiredOutputs: [
      "component-mapping-plan.json",
      "generated-component-specs.json",
      "mapping-decisions.json",
    ],
  },
  {
    ownerSkill: "miniapp-state-event-lifecycle-converter",
    taskIds: ["MAPP-017", "MAPP-018"],
    requiredOutputs: [
      "state-lowering-plan.json",
      "event-binding-plan.json",
      "lifecycle-plan.json",
      "side-effect-ledger.json",
    ],
  },
  {
    ownerSkill: "miniapp-style-layout-converter",
    taskIds: ["MAPP-019", "MAPP-020"],
    requiredOutputs: [
      "style-plan.json",
      "token-map.json",
      "responsive-rules.json",
      "unsupported-style-report.json",
    ],
  },
  {
    ownerSkill: "miniapp-third-party-dependency-migrator",
    taskIds: ["MAPP-021", "MAPP-022"],
    requiredOutputs: [
      "dependency-migration-plan.json",
      "replacement-graph.json",
      "license-report.json",
      "supply-chain-findings.json",
    ],
  },
  {
    ownerSkill: "wechat-miniapp-codegen",
    taskIds: ["MAPP-023"],
    requiredOutputs: [
      "platforms/wechat/**",
      "wechat-codegen-report.json",
      "wechat-trace-map.json",
    ],
  },
  {
    ownerSkill: "alipay-miniapp-codegen",
    taskIds: ["MAPP-024"],
    requiredOutputs: [
      "platforms/alipay/**",
      "alipay-codegen-report.json",
      "alipay-trace-map.json",
    ],
  },
  {
    ownerSkill: "douyin-miniapp-codegen",
    taskIds: ["MAPP-025"],
    requiredOutputs: [
      "platforms/douyin/**",
      "douyin-codegen-report.json",
      "douyin-trace-map.json",
    ],
  },
  {
    ownerSkill: "xiaohongshu-miniapp-codegen",
    taskIds: ["MAPP-026"],
    requiredOutputs: [
      "platforms/xiaohongshu/**",
      "xiaohongshu-codegen-report.json",
      "xiaohongshu-trace-map.json",
    ],
  },
  {
    ownerSkill: "miniapp-commerce-social-adapter",
    taskIds: ["MAPP-027", "MAPP-028"],
    requiredOutputs: [
      "commerce-social-contracts.json",
      "backend-api-specs",
      "platform-adapter-specs",
      "risk-and-approval-plan.json",
    ],
  },
  {
    ownerSkill: "miniapp-privacy-permission-auditor",
    taskIds: ["MAPP-029", "MAPP-030"],
    requiredOutputs: [
      "privacy-report.json",
      "permission-manifest.json",
      "secret-scan.json",
      "review-disclosure-checklist.md",
    ],
  },
  {
    ownerSkill: "miniapp-differential-testing",
    taskIds: ["MAPP-031", "MAPP-032"],
    requiredOutputs: [
      "differential-result.json",
      "flow-traces/**",
      "semantic-diff-report.html",
      "repair-candidates.json",
    ],
  },
  {
    ownerSkill: "miniapp-visual-regression-testing",
    taskIds: ["MAPP-033", "MAPP-034"],
    requiredOutputs: [
      "visual-diff-report.html",
      "screenshots/**",
      "layout-diffs.json",
      "visual-repair-candidates.json",
    ],
  },
  {
    ownerSkill: "miniapp-auto-repair-loop",
    taskIds: ["MAPP-035", "MAPP-036"],
    requiredOutputs: [
      "repair-action.json",
      "patches/**",
      "repair-history.json",
      "post-repair-validation.json",
    ],
  },
  {
    ownerSkill: "miniapp-ci-build-release",
    taskIds: ["MAPP-037", "MAPP-038"],
    requiredOutputs: [
      "ci pipelines",
      "build manifests",
      "preview artifacts",
      "upload receipts",
      "release records",
    ],
  },
  {
    ownerSkill: "miniapp-migration-evidence-reporter",
    taskIds: ["MAPP-039", "MAPP-040"],
    requiredOutputs: [
      "migration-evidence.json",
      "compatibility-report.html",
      "validation-report.md",
      "release-readiness.md",
      "artifact-index.json",
    ],
  },
] as const satisfies readonly MiniappDeclaredOutputContract[];

export const MINIAPP_DECLARED_OUTPUT_SCHEMA_BINDINGS = [
  {
    ownerSkill: "miniapp-source-framework-detector",
    declaredPattern: "project-inventory.json",
    schema: "project-inventory.schema.json",
  },
  {
    ownerSkill: "vue-to-miniapp-analyzer",
    declaredPattern: "vue-analysis.json",
    schema: "source-analysis.schema.json",
  },
  {
    ownerSkill: "react-to-miniapp-analyzer",
    declaredPattern: "react-analysis.json",
    schema: "source-analysis.schema.json",
  },
  {
    ownerSkill: "flutter-widget-semantic-reconstructor",
    declaredPattern: "flutter-analysis.json",
    schema: "source-analysis.schema.json",
  },
  {
    ownerSkill: "miniapp-semantic-ir",
    declaredPattern: "semantic-ir.json",
    schema: "semantic-ir.schema.json",
  },
  {
    ownerSkill: "miniapp-capability-registry",
    declaredPattern: "capability-resolution.json",
    schema: "capability-registry-entry.schema.json",
  },
  {
    ownerSkill: "miniapp-component-mapping-engine",
    declaredPattern: "component-mapping-plan.json",
    schema: "component-mapping.schema.json",
  },
  {
    ownerSkill: "miniapp-third-party-dependency-migrator",
    declaredPattern: "dependency-migration-plan.json",
    schema: "dependency-migration-plan.schema.json",
  },
  {
    ownerSkill: "miniapp-privacy-permission-auditor",
    declaredPattern: "privacy-report.json",
    schema: "privacy-report.schema.json",
  },
  {
    ownerSkill: "miniapp-differential-testing",
    declaredPattern: "differential-result.json",
    schema: "differential-result.schema.json",
  },
  {
    ownerSkill: "miniapp-auto-repair-loop",
    declaredPattern: "repair-action.json",
    schema: "repair-action.schema.json",
  },
  {
    ownerSkill: "miniapp-migration-evidence-reporter",
    declaredPattern: "migration-evidence.json",
    schema: "migration-evidence.schema.json",
  },
] as const satisfies readonly MiniappDeclaredOutputSchemaBinding[];

export function miniappDeclaredOutputSchema(
  ownerSkill: MiniappSkillName,
  declaredPattern: string,
): MiniappCanonicalSchemaFile | undefined {
  return MINIAPP_DECLARED_OUTPUT_SCHEMA_BINDINGS.find(
    (binding) =>
      binding.ownerSkill === ownerSkill && binding.declaredPattern === declaredPattern,
  )?.schema;
}

const CODEGEN_PLATFORM_BY_SKILL = {
  "wechat-miniapp-codegen": "wechat",
  "alipay-miniapp-codegen": "alipay",
  "douyin-miniapp-codegen": "douyin",
  "xiaohongshu-miniapp-codegen": "xiaohongshu",
} as const satisfies Partial<Record<MiniappSkillName, MiniappPlatform>>;

const CODEGEN_SKILL_BY_PLATFORM = {
  wechat: "wechat-miniapp-codegen",
  alipay: "alipay-miniapp-codegen",
  douyin: "douyin-miniapp-codegen",
  xiaohongshu: "xiaohongshu-miniapp-codegen",
} as const satisfies Record<MiniappPlatform, MiniappSkillName>;

const ANALYZER_SKILLS = new Set<MiniappSkillName>([
  "vue-to-miniapp-analyzer",
  "react-to-miniapp-analyzer",
  "flutter-widget-semantic-reconstructor",
]);

const EXTERNAL_NOT_RUN_SKILLS = new Set<MiniappSkillName>([
  "miniapp-differential-testing",
  "miniapp-visual-regression-testing",
  "miniapp-ci-build-release",
]);

const SAFE_TOKEN = /^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$/u;
const SAFE_PATH_SEGMENT = /^[a-z0-9][a-z0-9._-]*$/u;
const TEMPLATE_TOKEN = /<([a-z-]+)>/gu;
const WINDOWS_RESERVED_PATH_SEGMENT = /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/iu;

function unsafePortablePathSegment(segment: string, allowed: RegExp): boolean {
  return segment === ""
    || segment === "."
    || segment === ".."
    || segment.length > 255
    || segment.endsWith(".")
    || WINDOWS_RESERVED_PATH_SEGMENT.test(segment)
    || !allowed.test(segment);
}

function assertSafeToken(value: string, label: keyof MiniappOutputPathTokens): string {
  const normalized = value.normalize("NFC").toLowerCase();
  if (
    value !== value.normalize("NFC") ||
    value !== normalized ||
    !SAFE_TOKEN.test(normalized) ||
    normalized === "." ||
    normalized === ".." ||
    normalized.includes("..") ||
    normalized.includes("%")
  ) {
    throw new Error(`unsafe miniapp output ${label} token: ${JSON.stringify(value)}`);
  }
  return normalized;
}

export function materializeMiniappOutputPath(
  template: string,
  tokens: MiniappOutputPathTokens,
): string {
  const safeTokens: MiniappOutputPathTokens = {
    "run-id": assertSafeToken(tokens["run-id"], "run-id"),
    target: assertSafeToken(tokens.target, "target"),
    framework: assertSafeToken(tokens.framework, "framework"),
  };
  const replaced = template.replace(TEMPLATE_TOKEN, (_match, token: string) => {
    if (token !== "run-id" && token !== "target" && token !== "framework") {
      throw new Error(`unknown miniapp output path token: <${token}>`);
    }
    return safeTokens[token];
  });
  if (TEMPLATE_TOKEN.test(replaced)) {
    throw new Error(`unresolved miniapp output path token in ${JSON.stringify(template)}`);
  }
  TEMPLATE_TOKEN.lastIndex = 0;
  if (
    replaced !== replaced.normalize("NFC") ||
    replaced.startsWith("/") ||
    replaced.includes("\\") ||
    replaced.includes("//") ||
    replaced.includes("%") ||
    replaced.includes("<") ||
    replaced.includes(">") ||
    /[\u0000-\u001f\u007f]/u.test(replaced) ||
    posix.normalize(replaced) !== replaced ||
    replaced
      .split("/")
      .some((segment) => unsafePortablePathSegment(segment, SAFE_PATH_SEGMENT))
  ) {
    throw new Error(`unsafe materialized miniapp output path: ${JSON.stringify(replaced)}`);
  }
  return replaced;
}

function canonicalize(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new Error("miniapp output content cannot contain non-finite numbers");
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalize(item)).join(",")}]`;
  }
  if (typeof value === "object" && value !== null) {
    const entries = Object.entries(value as Readonly<Record<string, unknown>>)
      .filter(([, item]) => item !== undefined)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0));
    return `{${entries
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalize(item)}`)
      .join(",")}}`;
  }
  throw new Error(`unsupported miniapp output content type: ${typeof value}`);
}

function canonicalJson(value: unknown): string {
  return `${canonicalize(value)}\n`;
}

function pathLeaf(
  ownerSkill: MiniappSkillName,
  declaredPattern: string,
  state?: MiniappDeclaredOutputState,
): string {
  if (declaredPattern === "最终 migration-evidence.json 与兼容性报告") {
    return "final-migration-evidence-and-compatibility-report.blocked.json";
  }
  if (declaredPattern.endsWith("/**")) {
    const indexName = codegenPlatform(ownerSkill) === undefined
      ? "not-run-placeholder-index.json"
      : state === "PASSED_LOCAL"
        ? "project-index.json"
        : state === "NOT_APPLICABLE"
          ? "not-applicable-placeholder-index.json"
          : "blocked-surrogate-index.json";
    return `${declaredPattern.slice(0, -3)}/${indexName}`;
  }
  if (declaredPattern.endsWith(".html")) {
    return `${declaredPattern}.not-run.json`;
  }
  if (declaredPattern.endsWith(".md")) {
    return declaredPattern;
  }
  if (declaredPattern === "backend-api-specs" || declaredPattern === "platform-adapter-specs") {
    return declaredPattern;
  }
  if (!declaredPattern.includes(".") || declaredPattern.includes(" ")) {
    return `${declaredPattern.replace(/ +/gu, "-")}.not-run.json`;
  }
  return declaredPattern;
}

function outputPathTemplate(
  ownerSkill: MiniappSkillName,
  declaredPattern: string,
  state?: MiniappDeclaredOutputState,
): string {
  if (
    ownerSkill === "frontend-to-miniapp-orchestrator" &&
    declaredPattern.startsWith("runs/<run-id>/")
  ) {
    return declaredPattern;
  }
  if (
    ownerSkill === "frontend-to-miniapp-orchestrator" &&
    declaredPattern === "最终 migration-evidence.json 与兼容性报告"
  ) {
    return `runs/<run-id>/${pathLeaf(ownerSkill, declaredPattern)}`;
  }
  const codegenTarget = codegenPlatform(ownerSkill);
  if (codegenTarget !== undefined) {
    return `runs/<run-id>/platforms/<target>/${posix.basename(
      pathLeaf(ownerSkill, declaredPattern, state),
    )}`;
  }
  const scope = ANALYZER_SKILLS.has(ownerSkill)
    ? "/<framework>"
    : "";
  return `runs/<run-id>/declared-outputs/${ownerSkill}${scope}/${pathLeaf(
    ownerSkill,
    declaredPattern,
    state,
  )}`;
}

function analyzerApplies(run: MiniappConversionRun, ownerSkill: MiniappSkillName): boolean {
  const source = run.request.source.sourceLabel;
  switch (ownerSkill) {
    case "vue-to-miniapp-analyzer":
      return source === "vue2" || source === "vue3" || source === "uni-app";
    case "react-to-miniapp-analyzer":
      return (
        source === "react" ||
        source === "typescript" ||
        source === "javascript" ||
        source === "h5" ||
        source === "taro"
      );
    case "flutter-widget-semantic-reconstructor":
      return source === "flutter";
    default:
      return true;
  }
}

function codegenPlatform(ownerSkill: MiniappSkillName): MiniappPlatform | undefined {
  if (ownerSkill in CODEGEN_PLATFORM_BY_SKILL) {
    return CODEGEN_PLATFORM_BY_SKILL[
      ownerSkill as keyof typeof CODEGEN_PLATFORM_BY_SKILL
    ];
  }
  return undefined;
}

function codegenProjectPassedLocally(
  run: MiniappConversionRun,
  platform: MiniappPlatform,
): boolean {
  const project = run.generatedProjects.find((candidate) => candidate.platform === platform);
  return (
    project?.status === "GENERATED" &&
    project.staticValidation === "PASSED" &&
    evidenceState(run, `project-${platform}`) === "PASSED_LOCAL"
  );
}

function evidenceState(
  run: MiniappConversionRun,
  evidenceId: string,
): MiniappDeclaredOutputState {
  const evidence = run.evidenceGraph.find((candidate) => candidate.id === evidenceId);
  switch (evidence?.state) {
    case "PASSED":
      return "PASSED_LOCAL";
    case "FAILED":
    case "BLOCKED":
      return "BLOCKED";
    case "NOT_RUN":
    case undefined:
      return "NOT_RUN";
  }
}

function localEngineeringState(run: MiniappConversionRun): MiniappDeclaredOutputState {
  return run.localEngineering === "PASSED" ? "PASSED_LOCAL" : "BLOCKED";
}

function outputState(
  run: MiniappConversionRun,
  ownerSkill: MiniappSkillName,
  declaredPattern: string,
): MiniappDeclaredOutputState {
  if (!analyzerApplies(run, ownerSkill)) {
    return "NOT_APPLICABLE";
  }
  const platform = codegenPlatform(ownerSkill);
  if (
    platform !== undefined &&
    !run.request.targets.some((target) => target.platform === platform)
  ) {
    return "NOT_APPLICABLE";
  }
  if (platform !== undefined && declaredPattern.endsWith("/**")) {
    return codegenProjectPassedLocally(run, platform) ? "PASSED_LOCAL" : "BLOCKED";
  }
  if (
    ownerSkill === "frontend-to-miniapp-orchestrator" &&
    declaredPattern === "最终 migration-evidence.json 与兼容性报告"
  ) {
    return "BLOCKED";
  }
  if (
    ownerSkill === "miniapp-migration-evidence-reporter" &&
    declaredPattern === "compatibility-report.html"
  ) {
    return "NOT_RUN";
  }
  if (
    ownerSkill === "miniapp-migration-evidence-reporter" &&
    declaredPattern === "migration-evidence.json"
  ) {
    return "BLOCKED";
  }
  if (
    ownerSkill === "react-to-miniapp-analyzer" &&
    declaredPattern === "react-analysis.json" &&
    (run.request.source.sourceLabel === "typescript" ||
      run.request.source.sourceLabel === "javascript")
  ) {
    return "BLOCKED";
  }
  if (
    ownerSkill === "miniapp-semantic-ir" &&
    declaredPattern === "semantic-ir.json" &&
    run.inventory.assets.some(
      (assetPath) => !run.inventory.files.some((file) => file.path === assetPath),
    )
  ) {
    return "BLOCKED";
  }
  if (EXTERNAL_NOT_RUN_SKILLS.has(ownerSkill)) {
    return "NOT_RUN";
  }
  if (ownerSkill === "miniapp-auto-repair-loop") {
    return "NOT_RUN";
  }
  if (
    ownerSkill === "miniapp-third-party-dependency-migrator" &&
    (declaredPattern === "license-report.json" ||
      declaredPattern === "supply-chain-findings.json")
  ) {
    return "NOT_RUN";
  }
  if (platform !== undefined) {
    return evidenceState(run, `project-${platform}`);
  }
  switch (ownerSkill) {
    case "frontend-to-miniapp-orchestrator":
    case "miniapp-migration-evidence-reporter":
      return localEngineeringState(run);
    case "miniapp-source-framework-detector":
      return evidenceState(run, "inventory");
    case "vue-to-miniapp-analyzer":
    case "react-to-miniapp-analyzer":
    case "flutter-widget-semantic-reconstructor":
      return evidenceState(run, "analysis");
    case "miniapp-semantic-ir":
      return evidenceState(run, "semantic-ir");
    case "miniapp-capability-registry":
    case "miniapp-component-mapping-engine":
    case "miniapp-state-event-lifecycle-converter":
    case "miniapp-style-layout-converter":
    case "miniapp-third-party-dependency-migrator":
    case "miniapp-commerce-social-adapter":
      return evidenceState(run, "conversion-plan");
    case "miniapp-privacy-permission-auditor":
      return run.privacy.some((audit) => audit.verdict === "failed" || audit.verdict === "blocked")
        ? "BLOCKED"
        : "PASSED_LOCAL";
    case "miniapp-differential-testing":
    case "miniapp-visual-regression-testing":
    case "miniapp-ci-build-release":
      return "NOT_RUN";
    default: {
      throw new Error(`unmapped miniapp output state owner: ${ownerSkill}`);
    }
  }
}

function sourceTracePayload(run: MiniappConversionRun): unknown {
  return {
    components: run.analysis.components.map((component) => ({
      id: component.id,
      sourceRefs: component.sourceRefs,
    })),
    effects: run.analysis.effects.map((effect) => ({
      id: effect.id,
      sourceRefs: effect.sourceRefs,
    })),
    routes: run.analysis.routes.map((route) => ({
      id: route.id,
      sourceRefs: route.sourceRefs,
    })),
    state: run.analysis.states.map((state) => ({
      id: state.id,
      sourceRefs: state.sourceRefs,
    })),
  };
}

function analyzerPayload(run: MiniappConversionRun, declaredPattern: string): unknown {
  switch (declaredPattern) {
    case "vue-analysis.json":
    case "react-analysis.json":
    case "flutter-analysis.json":
      return run.analysis;
    case "component-graph.json":
    case "widget-tree.json":
      return run.analysis.components;
    case "route-graph.json":
    case "navigation-graph.json":
      return run.analysis.routes;
    case "state-graph.json":
      return run.analysis.states;
    case "hook-effect-graph.json":
      return run.analysis.effects;
    case "source-trace-map.json":
      return sourceTracePayload(run);
    case "platform-channel-report.json":
      return {
        capabilities: run.analysis.capabilities,
        findings: run.analysis.findings,
      };
    default:
      throw new Error(`unmapped analyzer output: ${declaredPattern}`);
  }
}

const SAFE_GENERATED_PATH_SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]*$/u;
const DECLARED_OUTPUT_STATES = new Set<MiniappDeclaredOutputState>([
  "PASSED_LOCAL",
  "BLOCKED",
  "NOT_RUN",
  "NOT_APPLICABLE",
]);
const RESERVED_GENERATED_ROOT_FILES = new Set([
  "blocked-surrogate-index.json",
  "not-applicable-placeholder-index.json",
  "project-index.json",
]);

function generatedDeclaredPattern(
  platform: MiniappPlatform,
): `platforms/${MiniappPlatform}/**` {
  return `platforms/${platform}/**`;
}

function assertSafeGeneratedSourcePath(sourcePath: string): string {
  const rootSegment = sourcePath.split("/", 1)[0]?.normalize("NFC").toLowerCase();
  if (
    sourcePath !== sourcePath.normalize("NFC") ||
    posix.isAbsolute(sourcePath) ||
    sourcePath.includes("\\") ||
    sourcePath.includes("//") ||
    sourcePath.includes("%") ||
    /[\u0000-\u001f\u007f]/u.test(sourcePath) ||
    posix.normalize(sourcePath) !== sourcePath ||
    sourcePath
      .split("/")
      .some((segment) => unsafePortablePathSegment(segment, SAFE_GENERATED_PATH_SEGMENT)) ||
    (rootSegment !== undefined && RESERVED_GENERATED_ROOT_FILES.has(rootSegment))
  ) {
    throw new Error(`unsafe generated miniapp project path: ${JSON.stringify(sourcePath)}`);
  }
  return sourcePath;
}

function indexedOutputPathCollisionKey(materializedPath: string): string {
  if (
    materializedPath !== materializedPath.normalize("NFC") ||
    posix.isAbsolute(materializedPath) ||
    materializedPath.includes("\\") ||
    materializedPath.includes("//") ||
    materializedPath.includes("%") ||
    /[\u0000-\u001f\u007f]/u.test(materializedPath) ||
    posix.normalize(materializedPath) !== materializedPath ||
    materializedPath
      .split("/")
      .some((segment) => unsafePortablePathSegment(segment, SAFE_GENERATED_PATH_SEGMENT))
  ) {
    throw new Error(`unsafe indexed miniapp output path: ${JSON.stringify(materializedPath)}`);
  }
  return materializedPath.normalize("NFC").toLowerCase();
}

export function materializeMiniappGeneratedProjectBasePath(
  run: MiniappConversionRun,
  platform: MiniappPlatform,
): string {
  return materializeMiniappOutputPath(
    "runs/<run-id>/platforms/<target>",
    {
      "run-id": run.runId,
      framework: run.request.source.sourceLabel,
      target: platform,
    },
  );
}

/**
 * Materialize only locally closed generated projects. These are companion
 * files for a catalog wildcard, not additional required-output declarations.
 * BLOCKED and unrequested projects intentionally produce no candidate files.
 */
export function materializeMiniappGeneratedProjectArtifacts(
  run: MiniappConversionRun,
): readonly MiniappGeneratedProjectArtifact[] {
  const results: MiniappGeneratedProjectArtifact[] = [];
  const materializedPaths = new Set<string>();
  for (const platform of [
    "wechat",
    "alipay",
    "douyin",
    "xiaohongshu",
  ] as const satisfies readonly MiniappPlatform[]) {
    if (!codegenProjectPassedLocally(run, platform)) {
      continue;
    }
    const project = run.generatedProjects.find((candidate) => candidate.platform === platform);
    if (project === undefined) {
      throw new Error(`locally passed miniapp project is missing: ${platform}`);
    }
    const fileEntries = Object.entries(project.files).sort(([left], [right]) =>
      left < right ? -1 : left > right ? 1 : 0,
    );
    if (fileEntries.length === 0) {
      throw new Error(`locally passed miniapp project has no files: ${platform}`);
    }
    const artifactByPath = new Map<string, (typeof project.artifacts)[number]>();
    for (const artifact of project.artifacts) {
      const sourcePath = assertSafeGeneratedSourcePath(artifact.path);
      if (artifactByPath.has(sourcePath)) {
        throw new Error(`duplicate generated miniapp artifact path: ${platform}:${sourcePath}`);
      }
      artifactByPath.set(sourcePath, artifact);
    }
    if (artifactByPath.size !== fileEntries.length) {
      throw new Error(`generated miniapp project file/artifact count mismatch: ${platform}`);
    }

    const declaredPattern = generatedDeclaredPattern(platform);
    const declaredBasePath = materializeMiniappGeneratedProjectBasePath(run, platform);
    const sourceFileKeys = new Set<string>();
    const sourceDirectoryKeys = new Set<string>();
    for (const [rawSourcePath, content] of fileEntries) {
      const sourcePath = assertSafeGeneratedSourcePath(rawSourcePath);
      const collisionKey = sourcePath.normalize("NFC").toLowerCase();
      if (sourceFileKeys.has(collisionKey)) {
        throw new Error(
          `case-insensitive generated miniapp project path collision: ${platform}:${sourcePath}`,
        );
      }
      if (sourceDirectoryKeys.has(collisionKey)) {
        throw new Error(
          `generated miniapp project file/directory collision: ${platform}:${sourcePath}`,
        );
      }
      const segments = collisionKey.split("/");
      let directoryKey = "";
      for (const segment of segments.slice(0, -1)) {
        directoryKey = directoryKey.length === 0 ? segment : `${directoryKey}/${segment}`;
        if (sourceFileKeys.has(directoryKey)) {
          throw new Error(
            `generated miniapp project file/directory collision: ${platform}:${sourcePath}`,
          );
        }
        sourceDirectoryKeys.add(directoryKey);
      }
      sourceFileKeys.add(collisionKey);
      const sourceArtifact = artifactByPath.get(sourcePath);
      if (sourceArtifact === undefined) {
        throw new Error(`generated miniapp project artifact is missing: ${platform}:${sourcePath}`);
      }
      const bytes = Buffer.byteLength(content, "utf8");
      const digest = `sha256:${createHash("sha256").update(content, "utf8").digest("hex")}`;
      if (
        sourceArtifact.bytes !== bytes ||
        `sha256:${digestHex(sourceArtifact.sha256)}` !== digest
      ) {
        throw new Error(
          `generated miniapp project artifact identity mismatch: ${platform}:${sourcePath}`,
        );
      }
      const materializedPath = `${declaredBasePath}/${sourcePath}`;
      const materializedCollisionKey = materializedPath.normalize("NFC").toLowerCase();
      if (materializedPaths.has(materializedCollisionKey)) {
        throw new Error(`duplicate generated miniapp materialized path: ${materializedPath}`);
      }
      materializedPaths.add(materializedCollisionKey);
      results.push({
        ownerSkill: CODEGEN_SKILL_BY_PLATFORM[platform],
        platform,
        declaredPattern,
        declaredBasePath,
        sourcePath,
        materializedPath,
        state: "PASSED_LOCAL",
        content,
        digest,
        bytes,
      });
    }
    for (const artifactPath of artifactByPath.keys()) {
      if (!Object.hasOwn(project.files, artifactPath)) {
        throw new Error(
          `generated miniapp artifact has no project file: ${platform}:${artifactPath}`,
        );
      }
    }
  }
  return results;
}

function generatedPayload(
  run: MiniappConversionRun,
  platform: MiniappPlatform,
  declaredPattern: string,
): unknown {
  const project = run.generatedProjects.find((candidate) => candidate.platform === platform);
  if (project === undefined) {
    return {
      platform,
      reason: "target platform was not requested",
      requestedTargets: run.request.targets.map((target) => target.platform),
    };
  }
  if (declaredPattern.startsWith(`platforms/${platform}/`)) {
    const declaredBasePath = materializeMiniappGeneratedProjectBasePath(run, platform);
    if (codegenProjectPassedLocally(run, platform)) {
      const files = materializeMiniappGeneratedProjectArtifacts(run)
        .filter((artifact) => artifact.platform === platform)
        .map((artifact) => ({
          bytes: artifact.bytes,
          path: artifact.materializedPath,
          sha256: digestHex(artifact.digest),
          source_path: artifact.sourcePath,
        }));
      return {
        declared_base_path: declaredBasePath,
        declared_pattern: declaredPattern,
        exact_declared_files_materialized: true,
        files,
        owner_skill: CODEGEN_SKILL_BY_PLATFORM[platform],
        platform,
        project_status: project.status,
        schema_version: "1.0.0",
        static_validation: project.staticValidation,
      };
    }
    return {
      declared_base_path: declaredBasePath,
      declared_pattern: declaredPattern,
      exact_declared_files_materialized: false,
      files: [],
      official_build: project.officialBuild,
      owner_skill: CODEGEN_SKILL_BY_PLATFORM[platform],
      platform,
      project_status: project.status,
      reason: "generated project is not locally closed and was not materialized",
      schema_version: "1.0.0",
      static_validation: project.staticValidation,
      surrogate_only: true,
    };
  }
  if (declaredPattern.endsWith("-trace-map.json")) {
    return project.traceMap;
  }
  return {
    artifacts: project.artifacts,
    certification: project.certification,
    findings: project.findings,
    officialBuild: project.officialBuild,
    platform,
    staticValidation: project.staticValidation,
  };
}

function digestHex(value: string): string {
  const normalized = value.startsWith("sha256:") ? value.slice("sha256:".length) : value;
  if (!/^[a-f0-9]{64}$/u.test(normalized)) {
    throw new Error(`invalid sha256 value in miniapp output body: ${value}`);
  }
  return normalized;
}

function bodyDigestHex(value: unknown): string {
  return createHash("sha256").update(canonicalize(value), "utf8").digest("hex");
}

function sourceRefString(
  sourceRef: MiniappConversionRun["analysis"]["components"][number]["sourceRefs"][number],
): string {
  return `${sourceRef.path}:${sourceRef.startLine}:${sourceRef.startColumn}-${sourceRef.endLine}:${sourceRef.endColumn}`;
}

function projectInventorySchemaBody(run: MiniappConversionRun): unknown {
  return {
    inventory_id: run.inventory.inventoryId,
    source_revision: run.inventory.sourceRevision,
    files: run.inventory.files.map((file) => ({
      kind: file.kind,
      path: file.path,
      reason: file.reason,
      sha256: digestHex(file.digest),
      status: file.status,
    })),
    framework_candidates: run.inventory.frameworkCandidates.map((candidate) => ({
      confidence: candidate.confidence,
      evidence: candidate.evidence.map(
        (signal) => `${signal.path}:${signal.kind}:${signal.detail}`,
      ),
      framework: candidate.sourceLabel,
      version_range:
        candidate.sourceLabel === run.request.source.sourceLabel
          ? run.request.source.frameworkVersion
          : undefined,
    })),
    entrypoints: run.inventory.entrypoints,
    routes: run.inventory.routes,
    components: run.inventory.components,
    stores: run.inventory.stores,
    assets: run.inventory.assets,
    dependencies: run.inventory.dependencies.map((dependency) => ({
      name: dependency.name,
      scope: dependency.scope,
      source: dependency.sourcePath,
      version: dependency.version,
    })),
    platform_api_signals: run.inventory.platformApiSignals,
    coverage: {
      eligible_files: run.inventory.coverage.eligibleFiles,
      processed_files: run.inventory.coverage.processedFiles,
      ratio: run.inventory.coverage.ratio,
      total_files: run.inventory.coverage.totalFiles,
    },
  };
}

type SourceAnalysisSchemaFramework =
  | "vue2"
  | "vue3"
  | "react"
  | "flutter"
  | "h5"
  | "taro"
  | "uni-app"
  | "native-miniapp";

function schemaFrameworkForAnalyzer(
  run: MiniappConversionRun,
  ownerSkill: MiniappSkillName,
): SourceAnalysisSchemaFramework {
  if (!analyzerApplies(run, ownerSkill)) {
    if (ownerSkill === "vue-to-miniapp-analyzer") return "vue3";
    if (ownerSkill === "react-to-miniapp-analyzer") return "react";
    return "flutter";
  }
  const source = run.request.source.sourceLabel;
  return source === "typescript" || source === "javascript" ? "h5" : source;
}

function sourceAnalysisSchemaBody(
  run: MiniappConversionRun,
  ownerSkill: MiniappSkillName,
): unknown {
  const applies = analyzerApplies(run, ownerSkill);
  const components = applies
    ? run.analysis.components.map((component) => ({
        confidence: 1,
        data: {
          accessibility: component.accessibility,
          attributes: component.attributes,
          children: component.children,
          events: component.events,
          model_binding: component.modelBinding,
          props: component.props,
          semantic_role: component.semanticRole,
          source_tag: component.sourceTag,
          text_content: component.textContent,
        },
        id: component.id,
        kind: "component",
        name: component.name,
      }))
    : [];
  const routes = applies
    ? run.analysis.routes.map((route) => ({
        confidence: 1,
        data: {
          component: route.component,
          guards: route.guards,
          parameters: route.parameters,
          path: route.path,
        },
        id: route.id,
        kind: "route",
        name: route.path,
      }))
    : [];
  const states = applies
    ? run.analysis.states.map((state) => ({
        confidence: 1,
        data: {
          reads: state.reads,
          scope: state.scope,
          state_type: state.stateType,
          writes: state.writes,
        },
        id: state.id,
        kind: "state",
        name: state.name,
      }))
    : [];
  const effects = applies
    ? run.analysis.effects.map((effect) => ({
        confidence: 1,
        data: {
          asynchronous: effect.asynchronous,
          cleanup: effect.cleanup,
          trigger: effect.trigger,
        },
        id: effect.id,
        kind: "lifecycle",
        name: effect.name,
      }))
    : [];
  const capabilities = applies
    ? run.analysis.capabilities.map((capability) => ({
        confidence: 1,
        data: {
          category: capability.category,
          sensitive: capability.sensitive,
        },
        id: capability.id,
        kind: "capability",
        name: capability.name,
      }))
    : [];
  const unsupportedSignals = applies
    ? [
        ...run.analysis.findings.map((finding, index) => ({
          confidence: 1,
          data: {
            blocking: finding.blocking,
            classification: finding.classification,
            message: finding.message,
            severity: finding.severity,
          },
          id: `finding-${index}-${finding.code.toLowerCase().replace(/[^a-z0-9]+/gu, "-")}`,
          kind: "finding",
          name: finding.code,
        })),
        ...run.analysis.forms.map((form) => ({
          confidence: 1,
          data: {
            binding: form.binding,
            fields: form.fields,
            validation: form.validation,
          },
          id: form.id,
          kind: "schema-extension-form",
          name: form.name,
        })),
        ...run.analysis.styles.map((style) => ({
          confidence: 1,
          data: {
            declarations: style.declarations,
            responsive: style.responsive,
            selector: style.selector,
          },
          id: style.id,
          kind: "schema-extension-style",
          name: style.selector,
        })),
        ...run.analysis.interactions.map((interaction) => ({
          confidence: 1,
          data: {
            clear_after_submit: interaction.clearAfterSubmit,
            collection_state: interaction.collectionState,
            draft_state: interaction.draftState,
            ignore_blank: interaction.ignoreBlank,
            input_component_id: interaction.inputComponentId,
            list_component_id: interaction.listComponentId,
            submit_component_id: interaction.submitComponentId,
            submit_handler: interaction.submitHandler,
          },
          id: interaction.id,
          kind: "schema-extension-interaction",
          name: interaction.kind,
        })),
        {
          confidence: 1,
          data: {
            dependencies: run.analysis.dependencies,
            dependency_usage: Object.fromEntries(
              Object.entries(run.analysis.dependencyUsage).map(([dependency, sourceRefs]) => [
                dependency,
                sourceRefs.map(sourceRefString),
              ]),
            ),
          },
          id: "source-analysis-dependencies",
          kind: "schema-extension-dependencies",
          name: "source dependencies",
        },
        ...(run.request.source.sourceLabel === "typescript" ||
        run.request.source.sourceLabel === "javascript"
          ? [
              {
                confidence: 1,
                data: {
                  canonical_framework_encoding: "h5",
                  declared_source_label: run.request.source.sourceLabel,
                  reason:
                    "canonical source-analysis schema has no typescript/javascript framework enum",
                },
                id: "canonical-framework-enum-gap",
                kind: "schema-gap",
                name: "source framework enum gap",
              },
            ]
          : []),
      ]
    : [
        {
          confidence: 1,
          data: {
            declared_source_label: run.request.source.sourceLabel,
            owner_skill: ownerSkill,
          },
          id: "analyzer-not-applicable",
          kind: "not-applicable",
          name: "analyzer not applicable to declared source",
        },
      ];
  const traced = applies
    ? [
        ...run.analysis.components,
        ...run.analysis.routes,
        ...run.analysis.states,
        ...run.analysis.effects,
        ...run.analysis.capabilities,
        ...run.analysis.forms,
        ...run.analysis.styles,
        ...run.analysis.interactions,
      ].flatMap((fact) =>
        fact.sourceRefs.map((sourceRef) => ({
          end_line: sourceRef.endLine,
          fact_id: fact.id,
          path: sourceRef.path,
          start_line: sourceRef.startLine,
        })),
      )
    : [];
  return {
    analysis_id: applies
      ? run.analysis.analysisId
      : `${run.analysis.analysisId}-${ownerSkill}-not-applicable`,
    framework: schemaFrameworkForAnalyzer(run, ownerSkill),
    framework_version: applies ? run.analysis.frameworkVersion : "not-applicable",
    confidence: applies ? run.analysis.coverage : 0,
    components,
    routes,
    state_nodes: states,
    lifecycle_hooks: effects,
    capabilities,
    unsupported_signals: unsupportedSignals,
    trace: traced,
  };
}

function semanticNodeSchemaBody(
  run: MiniappConversionRun,
  node: MiniappConversionRun["semanticIr"]["nodes"][number],
): unknown {
  const component = run.semanticIr.components.find((candidate) => candidate.id === node.id);
  return {
    id: node.id,
    kind: node.kind,
    name: node.name,
    content_hash: bodyDigestHex(node),
    props: {
      obligations: node.obligations,
      semantic_role: node.semanticRole,
    },
    children: component?.children ?? [],
    references: node.references,
  };
}

function semanticIrSchemaBody(run: MiniappConversionRun): unknown {
  const nodes = run.semanticIr.nodes;
  const assetPaths = [...new Set([
    ...run.inventory.assets,
    ...run.inventory.files
      .filter((file) => file.status === "binary")
      .map((file) => file.path),
  ])].sort((left, right) => (left < right ? -1 : left > right ? 1 : 0));
  return {
    schema_version: "2.0.0",
    application: {
      id: run.semanticIr.application.id,
      name: run.semanticIr.application.title,
      routes: nodes
        .filter((node) => node.kind === "route")
        .map((node) => semanticNodeSchemaBody(run, node)),
      components: nodes
        .filter((node) => node.kind === "component")
        .map((node) => semanticNodeSchemaBody(run, node)),
      state_stores: nodes
        .filter((node) => node.kind === "state")
        .map((node) => semanticNodeSchemaBody(run, node)),
      events: nodes
        .filter((node) => node.kind === "effect" || node.kind === "interaction")
        .map((node) => semanticNodeSchemaBody(run, node)),
      styles: nodes
        .filter((node) => node.kind === "style")
        .map((node) => semanticNodeSchemaBody(run, node)),
      capabilities: nodes
        .filter((node) => node.kind === "capability")
        .map((node) => semanticNodeSchemaBody(run, node)),
      assets: assetPaths.map((assetPath) => {
        const file = run.inventory.files.find((candidate) => candidate.path === assetPath);
        const missing = file === undefined;
        return {
          id: `asset-${bodyDigestHex(assetPath).slice(0, 24)}`,
          kind: "asset",
          name: assetPath,
          content_hash:
            file === undefined
              ? bodyDigestHex({
                  asset_path: assetPath,
                  status: "inventory-file-missing",
                })
              : digestHex(file.digest),
          props: {
            byte_count: file?.byteCount ?? 0,
            file_kind: file?.kind ?? "unknown",
            path: assetPath,
            status: missing ? "inventory-file-missing" : file.status,
          },
          children: [],
          references: [],
        };
      }),
    },
    extensions: {
      source: {
        framework_version: run.semanticIr.source.frameworkVersion,
        label: run.semanticIr.source.label,
        parser: run.semanticIr.source.parser,
        revision: run.semanticIr.source.revision,
        snapshot_digest: run.semanticIr.source.snapshotDigest,
      },
      profile: run.semanticIr.profile,
      semantic_model: {
        routes: run.semanticIr.routes.map((route) => ({
          component: route.component,
          guards: route.guards,
          id: route.id,
          parameters: route.parameters,
          path: route.path,
          source_refs: route.sourceRefs.map(sourceRefString),
        })),
        components: run.semanticIr.components.map((component) => ({
          accessibility: component.accessibility,
          attributes: component.attributes,
          children: component.children,
          event_bindings: component.eventBindings.map((binding) => ({
            event: binding.event,
            handler: binding.handler,
            modifiers: binding.modifiers,
          })),
          events: component.events,
          id: component.id,
          model_binding: component.modelBinding,
          name: component.name,
          props: component.props,
          semantic_role: component.semanticRole,
          source_kind: component.sourceKind,
          source_refs: component.sourceRefs.map(sourceRefString),
          source_tag: component.sourceTag,
          text_content: component.textContent,
          collection_binding:
            component.collectionBinding === null
              ? null
              : {
                  collection: component.collectionBinding.collection,
                  index_alias: component.collectionBinding.indexAlias,
                  item_alias: component.collectionBinding.itemAlias,
                  key_expression: component.collectionBinding.keyExpression,
                  value_expression: component.collectionBinding.valueExpression,
                },
        })),
        states: run.semanticIr.states.map((state) => ({
          id: state.id,
          name: state.name,
          reads: state.reads,
          scope: state.scope,
          source_refs: state.sourceRefs.map(sourceRefString),
          state_type: state.stateType,
          writes: state.writes,
        })),
        effects: run.semanticIr.effects.map((effect) => ({
          asynchronous: effect.asynchronous,
          cleanup: effect.cleanup,
          id: effect.id,
          name: effect.name,
          source_refs: effect.sourceRefs.map(sourceRefString),
          trigger: effect.trigger,
        })),
        forms: run.semanticIr.forms.map((form) => ({
          binding: form.binding,
          fields: form.fields,
          id: form.id,
          name: form.name,
          source_refs: form.sourceRefs.map(sourceRefString),
          validation: form.validation,
        })),
        styles: run.semanticIr.styles.map((style) => ({
          declarations: style.declarations,
          id: style.id,
          responsive: style.responsive,
          selector: style.selector,
          source_refs: style.sourceRefs.map(sourceRefString),
        })),
        capabilities: run.semanticIr.capabilities.map((capability) => ({
          category: capability.category,
          id: capability.id,
          name: capability.name,
          sensitive: capability.sensitive,
          source_refs: capability.sourceRefs.map(sourceRefString),
        })),
        interactions: run.semanticIr.interactions.map((interaction) => ({
          clear_after_submit: interaction.clearAfterSubmit,
          collection_state: interaction.collectionState,
          draft_state: interaction.draftState,
          id: interaction.id,
          ignore_blank: interaction.ignoreBlank,
          input_component_id: interaction.inputComponentId,
          kind: interaction.kind,
          list_component_id: interaction.listComponentId,
          source_refs: interaction.sourceRefs.map(sourceRefString),
          submit_component_id: interaction.submitComponentId,
          submit_handler: interaction.submitHandler,
        })),
        dependencies: run.semanticIr.dependencies,
        dependency_usage: Object.fromEntries(
          Object.entries(run.semanticIr.dependencyUsage).map(([dependency, sourceRefs]) => [
            dependency,
            sourceRefs.map(sourceRefString),
          ]),
        ),
        unknowns: run.semanticIr.unknowns.map((finding) => ({
          blocking: finding.blocking,
          classification: finding.classification,
          code: finding.code,
          message: finding.message,
          severity: finding.severity,
          source_refs: finding.sourceRefs.map(sourceRefString),
        })),
      },
      coverage: {
        parsed_source: run.semanticIr.coverage.parsedSource,
        traced_nodes: run.semanticIr.coverage.tracedNodes,
        unresolved_critical: run.semanticIr.coverage.unresolvedCritical,
      },
      source_model_digest: run.semanticIr.deterministicDigest,
    },
    trace_index: Object.entries(run.semanticIr.traceIndex).flatMap(([irId, sourceRefs]) =>
      sourceRefs.map((sourceRef) => ({
        confidence: 1,
        ir_id: irId,
        source: {
          end_line: sourceRef.endLine,
          path: sourceRef.path,
          start_line: sourceRef.startLine,
        },
      })),
    ),
  };
}

const ALL_MINIAPP_PLATFORMS = [
  "wechat",
  "alipay",
  "douyin",
  "xiaohongshu",
] as const satisfies readonly MiniappPlatform[];

function highestClassification(
  values: readonly ("A" | "B" | "C" | "D" | "E")[],
): "A" | "B" | "C" | "D" | "E" {
  const order = ["A", "B", "C", "D", "E"] as const;
  return values.reduce(
    (highest, value) => (order.indexOf(value) > order.indexOf(highest) ? value : highest),
    "A",
  );
}

function supportForClassification(
  classification: "A" | "B" | "C" | "D" | "E",
): "native" | "adapter" | "redesign" | "decision" | "unsupported" {
  if (classification === "A") return "native";
  if (classification === "B") return "adapter";
  if (classification === "C") return "redesign";
  if (classification === "D") return "decision";
  return "unsupported";
}

function capabilityRegistrySchemaBody(run: MiniappConversionRun): unknown {
  const targets = Object.fromEntries(
    ALL_MINIAPP_PLATFORMS.map((platform) => {
      const decisions = run.plan.capabilities.filter(
        (capability) => capability.platform === platform,
      );
      const requested = run.request.targets.some((target) => target.platform === platform);
      const classification =
        decisions.length > 0
          ? highestClassification(decisions.map((decision) => decision.classification))
          : "D";
      const support = requested ? supportForClassification(classification) : "decision";
      const reviewOrder = ["low", "medium", "high", "critical"] as const;
      const reviewRisk = decisions.reduce<(typeof reviewOrder)[number]>(
        (highest, decision) =>
          reviewOrder.indexOf(decision.reviewRisk) > reviewOrder.indexOf(highest)
            ? decision.reviewRisk
            : highest,
        requested ? "low" : "high",
      );
      return [
        platform,
        {
          adapter: support === "adapter" ? `${platform}-capability-port` : undefined,
          notes: canonicalize({
            decisions,
            requested,
          }),
          permission: [
            ...new Set(decisions.flatMap((decision) => decision.permission)),
          ].sort(),
          required_tests: [
            ...new Set(
              decisions.length > 0
                ? decisions.flatMap((decision) => decision.requiredTests)
                : ["target-not-requested"],
            ),
          ].sort(),
          review_risk: reviewRisk,
          runtime: decisions.some((decision) => decision.backendRequired)
            ? "hybrid"
            : "client",
          support,
        },
      ];
    }),
  );
  const sourcePatterns = run.semanticIr.capabilities.map((capability) => ({
    framework: run.request.source.sourceLabel,
    symbol: capability.name,
  }));
  return {
    id: "capability.aggregate-resolution",
    category: "aggregate",
    source_patterns:
      sourcePatterns.length > 0
        ? sourcePatterns
        : [
            {
              framework: run.request.source.sourceLabel,
              symbol: "none-detected",
            },
          ],
    targets,
    fallback: {
      requires_approval: run.plan.capabilities.some(
        (decision) => decision.classification === "D" || decision.classification === "E",
      ),
      strategy: "explicit-per-capability-resolution",
    },
    verified_at: run.plan.platformProfiles[0]?.docsReviewedAt ?? "1970-01-01",
    source_refs: [
      ...new Set(
        run.semanticIr.capabilities.flatMap((capability) =>
          capability.sourceRefs.map(sourceRefString),
        ),
      ),
    ].sort(),
  };
}

function componentMappingSchemaBody(run: MiniappConversionRun): unknown {
  const requirements = {
    accessibility: [
      ...new Set(run.analysis.components.flatMap((component) => component.accessibility)),
    ].sort(),
    events: [
      ...new Set(run.analysis.components.flatMap((component) => component.events)),
    ].sort(),
    props: [...new Set(run.analysis.components.flatMap((component) => component.props))].sort(),
    slots: [
      ...new Set(run.analysis.components.flatMap((component) => component.children)),
    ].sort(),
  };
  return {
    mapping_id: `component-mapping-${run.request.requestId}`,
    source_component: {
      framework: run.request.source.sourceLabel,
      symbol: "application-components",
      usage_ref: run.request.source.root,
    },
    semantic_role: "aggregate-component-mapping",
    requirements,
    targets: run.request.targets.map((target) => {
      const decisions = run.plan.components.filter(
        (decision) => decision.platform === target.platform,
      );
      const classification =
        decisions.length > 0
          ? highestClassification(decisions.map((decision) => decision.classification))
          : "B";
      return {
        classification,
        platform: target.platform,
        strategy: canonicalize(
          decisions.map((decision) => ({
            component_id: decision.componentId,
            strategy: decision.strategy,
            target_component: decision.targetComponent,
          })),
        ),
        target_component:
          [...new Set(decisions.map((decision) => decision.targetComponent))].join(",") ||
          "none-detected",
        tests: [
          ...new Set(
            decisions.length > 0
              ? decisions.flatMap((decision) => decision.requiredTests)
              : ["schema-contract"],
          ),
        ].sort(),
      };
    }),
  };
}

function dependencyAction(
  action: MiniappConversionRun["plan"]["dependencies"][number]["action"],
): "retain" | "replace" | "rewrite" | "backend-move" | "isolate" | "remove-approved" | "block" {
  if (action === "retain-shared") return "retain";
  if (action === "remove-with-approval") return "remove-approved";
  if (action === "blocked") return "block";
  return action;
}

function dependencyPlanSchemaBody(run: MiniappConversionRun): unknown {
  const dependencies = run.plan.dependencies.map((decision) => {
    const inventory = run.inventory.dependencies.find(
      (dependency) => dependency.name === decision.dependency,
    );
    const action = dependencyAction(decision.action);
    const risk =
      action === "block"
        ? "critical"
        : decision.vulnerabilityState === "NOT_SCANNED" ||
            decision.licenseState === "NOT_SCANNED"
          ? "high"
          : action === "retain"
            ? "low"
            : "medium";
    const targetState =
      action === "block"
        ? "unsupported"
        : action === "retain"
          ? "supported"
          : "conditional";
    return {
      name: decision.dependency,
      source_version: inventory?.version ?? "unknown",
      usage_evidence: decision.usageEvidence,
      action,
      replacement: decision.replacement ?? undefined,
      risk,
      targets: Object.fromEntries(
        run.request.targets.map((target) => [target.platform, targetState]),
      ),
      required_tests: [
        ...run.request.targets.map(
          (target) => `dependency-contract-${target.platform}`,
        ),
        ...(decision.licenseState === "NOT_SCANNED" ? ["license-scan-not-run"] : []),
        ...(decision.vulnerabilityState === "NOT_SCANNED"
          ? ["vulnerability-scan-not-run"]
          : []),
      ],
    };
  });
  return {
    plan_id: `dependency-plan-${run.request.requestId}`,
    dependencies,
    summary: {
      blocked: dependencies.filter((dependency) => dependency.action === "block").length,
      high_risk: dependencies.filter(
        (dependency) => dependency.risk === "high" || dependency.risk === "critical",
      ).length,
      total: dependencies.length,
    },
  };
}

function differentialResultSchemaBody(run: MiniappConversionRun): unknown {
  const platform = run.request.targets[0]!.platform;
  const messages = [
    "NOT_RUN: source and target runtime traces were not captured",
    `requested platforms: ${run.request.targets.map((target) => target.platform).join(",")}`,
    ...run.differential.findings,
  ];
  return {
    result_id: `differential-${run.request.requestId}-${platform}`,
    flow_id: "runtime-not-run",
    platform,
    verdict: "unknown",
    source_trace: [],
    target_trace: [],
    diffs: messages.map((message) => ({
      kind: "not-run",
      message,
      severity: "high",
    })),
  };
}

function privacyReportSchemaBody(run: MiniappConversionRun): unknown {
  const audit = run.privacy[0]!;
  const additionalAudits = run.privacy.slice(1);
  return {
    report_id: `privacy-${run.request.requestId}-${audit.platform}`,
    platform: audit.platform,
    verdict: audit.verdict,
    data_flows: audit.dataFlows.map((flow) => ({
      consent: flow.consentRequired ? "required-missing" : "not-required",
      data_type: flow.capability,
      destination: flow.destination,
      purpose: flow.capability,
      sensitive: flow.sensitive,
      source: "source-capability",
    })),
    permissions: audit.permissions.map((permission) => ({
      permission: permission.permission,
      purpose: permission.purpose,
      status: permission.declared ? "valid" : "invalid",
      trigger: "runtime-not-run",
    })),
    secret_findings: audit.secretFindings.map((finding) => ({
      fingerprint: bodyDigestHex(finding),
      kind: finding,
      path: "not-disclosed",
      severity: "high",
    })),
    findings: [
      ...audit.findings.map((finding, index) => ({
        blocking: audit.verdict === "blocked" || audit.verdict === "failed",
        finding_id: `privacy-finding-${index}`,
        message: finding,
        severity: "high",
      })),
      ...additionalAudits.map((additionalAudit) => ({
        blocking:
          additionalAudit.verdict === "blocked" || additionalAudit.verdict === "failed",
        finding_id: `additional-platform-${additionalAudit.platform}`,
        message: canonicalize({
          note: "additional platform audit retained in aggregate report finding",
          report: additionalAudit,
        }),
        severity:
          additionalAudit.verdict === "failed" || additionalAudit.verdict === "blocked"
            ? "high"
            : "low",
      })),
    ],
  };
}

function repairActionSchemaBody(run: MiniappConversionRun): unknown {
  const candidate = run.repair.candidates[0];
  const strategy =
    candidate?.owner === "mapping"
      ? "mapping-rule"
      : candidate?.owner === "adapter"
        ? "platform-adapter"
        : candidate?.owner === "generated-code"
          ? "generated-local-patch"
          : "ir";
  return {
    repair_id: `repair-${run.request.requestId}-1`,
    finding_id: candidate?.finding ?? "no-repair-candidate",
    iteration: 1,
    strategy,
    patch_scope: [candidate ? `owner:${candidate.owner}` : "no-mutation"],
    validation: {
      affected_gates: ["G5", "G6"],
      reproduction: "blocked",
      targeted_tests: [],
    },
    status: "blocked",
    stop_reason: canonicalize({
      candidates: run.repair.candidates,
      execution:
        "PLAN_ONLY: patches and post-repair validation were NOT_RUN; no source mutation occurred",
    }),
  };
}

function migrationEvidenceSchemaBody(run: MiniappConversionRun): unknown {
  return {
    evidence_id: `migration-evidence-${run.request.requestId}`,
    request_id: run.request.requestId,
    source_revision: run.request.source.revision,
    artifacts: [],
    claims: [
      ...run.request.targets.map((target) => ({
        claim_id: `build-${target.platform}`,
        evidence_refs: [],
        status: "unknown",
        subject: target.platform,
        type: "build",
      })),
      {
        claim_id: "semantic-parity",
        evidence_refs: [],
        status: "unknown",
        subject: "all-requested-targets",
        type: "semantic-parity",
      },
      {
        claim_id: "visual-parity",
        evidence_refs: [],
        status: "unknown",
        subject: "all-requested-targets",
        type: "visual-parity",
      },
      ...run.privacy.map((audit) => ({
        claim_id: `privacy-${audit.platform}`,
        evidence_refs: [],
        status: "unknown",
        subject: audit.platform,
        type: "privacy",
      })),
      {
        claim_id: "release",
        evidence_refs: [],
        status: "unknown",
        subject: "all-requested-targets",
        type: "release",
      },
    ],
    gates: run.gates.map((gate) => ({
      evidence_refs: [],
      gate: gate.gate,
      status:
        gate.state === "FAILED"
          ? "failed"
          : gate.state === "BLOCKED"
            ? "blocked"
            : "unknown",
    })),
    approvals: [
      {
        action: "release",
        status: "pending",
      },
    ],
    cost: {
      currency: "NOT_RECORDED",
      system_wall_clock_ms: 0,
      total: 0,
    },
    release_status: "not-ready",
  };
}

function schemaExactOutputBody(
  run: MiniappConversionRun,
  ownerSkill: MiniappSkillName,
  schema: MiniappCanonicalSchemaFile,
): unknown {
  switch (schema) {
    case "project-inventory.schema.json":
      return projectInventorySchemaBody(run);
    case "source-analysis.schema.json":
      return sourceAnalysisSchemaBody(run, ownerSkill);
    case "semantic-ir.schema.json":
      return semanticIrSchemaBody(run);
    case "capability-registry-entry.schema.json":
      return capabilityRegistrySchemaBody(run);
    case "component-mapping.schema.json":
      return componentMappingSchemaBody(run);
    case "dependency-migration-plan.schema.json":
      return dependencyPlanSchemaBody(run);
    case "differential-result.schema.json":
      return differentialResultSchemaBody(run);
    case "privacy-report.schema.json":
      return privacyReportSchemaBody(run);
    case "repair-action.schema.json":
      return repairActionSchemaBody(run);
    case "migration-evidence.schema.json":
      return migrationEvidenceSchemaBody(run);
    case "compatibility-report.schema.json":
    case "conversion-request.schema.json":
    case "platform-profile.schema.json":
    case "test-plan.schema.json":
      throw new Error(`canonical schema ${schema} is not a declared-output body schema`);
    default: {
      const exhaustive: never = schema;
      return exhaustive;
    }
  }
}

function reporterPayload(run: MiniappConversionRun, declaredPattern: string): unknown {
  if (declaredPattern === "artifact-index.json") {
    return {
      evidenceGraph: run.evidenceGraph,
      generatedArtifacts: run.generatedProjects.flatMap((project) => project.artifacts),
    };
  }
  if (declaredPattern === "migration-evidence.json") {
    return {
      checkpoint: run.checkpoint,
      evidenceGraph: run.evidenceGraph,
      gates: run.gates,
      taskRecords: run.taskRecords,
    };
  }
  if (declaredPattern === "compatibility-report.html") {
    return {
      capabilities: run.plan.capabilities,
      compatibility: run.generatedProjects.map((project) => ({
        findings: project.findings,
        platform: project.platform,
        staticValidation: project.staticValidation,
      })),
      differential: run.differential,
      visual: run.visual,
    };
  }
  if (declaredPattern === "validation-report.md") {
    return {
      gates: run.gates,
      localEngineering: run.localEngineering,
      officialBuilds: run.generatedProjects.map((project) => ({
        officialBuild: project.officialBuild,
        platform: project.platform,
      })),
    };
  }
  return {
    certification: run.certification,
    delivery: run.delivery,
    readiness: run.readiness,
  };
}

function outputPayload(
  run: MiniappConversionRun,
  ownerSkill: MiniappSkillName,
  declaredPattern: string,
): unknown {
  const platform = codegenPlatform(ownerSkill);
  if (platform !== undefined) {
    return generatedPayload(run, platform, declaredPattern);
  }
  switch (ownerSkill) {
    case "frontend-to-miniapp-orchestrator":
      if (declaredPattern.endsWith("/state.json")) {
        return {
          certification: run.certification,
          checkpoint: run.checkpoint,
          gates: run.gates,
          localEngineering: run.localEngineering,
          readiness: run.readiness,
        };
      }
      if (declaredPattern.endsWith("/plan.json")) {
        return run.plan;
      }
      if (declaredPattern.endsWith("/artifacts-index.json")) {
        return {
          evidenceGraph: run.evidenceGraph,
          generatedArtifacts: run.generatedProjects.flatMap((project) => project.artifacts),
        };
      }
      return {
        certification: run.certification,
        compatibility: run.generatedProjects.map((project) => project.findings),
        evidenceGraph: run.evidenceGraph,
        readiness: run.readiness,
      };
    case "miniapp-source-framework-detector":
      if (declaredPattern === "project-inventory.json") {
        return run.inventory;
      }
      if (declaredPattern === "framework-detection.json") {
        return {
          candidates: run.inventory.frameworkCandidates,
          conflicts: run.inventory.frameworkConflicts,
          detected: run.inventory.selectedSourceLabel,
          requested: run.request.source.sourceLabel,
        };
      }
      if (declaredPattern === "entrypoint-map.json") {
        return {
          components: run.inventory.components,
          entrypoints: run.inventory.entrypoints,
          routes: run.inventory.routes,
          stores: run.inventory.stores,
        };
      }
      return {
        conflicts: run.inventory.frameworkConflicts,
        findings: run.inventory.findings,
      };
    case "vue-to-miniapp-analyzer":
    case "react-to-miniapp-analyzer":
    case "flutter-widget-semantic-reconstructor":
      return analyzerPayload(run, declaredPattern);
    case "miniapp-semantic-ir":
      if (declaredPattern === "semantic-ir.json") {
        return run.semanticIr;
      }
      if (declaredPattern === "ir-validation.json") {
        return {
          coverage: run.semanticIr.coverage,
          unknowns: run.semanticIr.unknowns,
        };
      }
      if (declaredPattern === "ir-trace-index.json") {
        return run.semanticIr.traceIndex;
      }
      return {
        fromSchema: run.analysis.schemaVersion,
        nodeCount: run.semanticIr.nodes.length,
        toSchema: run.semanticIr.schemaVersion,
      };
    case "miniapp-capability-registry":
      if (declaredPattern === "capability-resolution.json") {
        return run.plan.capabilities;
      }
      if (declaredPattern === "compatibility-findings.json") {
        return run.plan.findings;
      }
      if (declaredPattern === "required-permissions.json") {
        return run.plan.capabilities.map((capability) => ({
          capabilityId: capability.capabilityId,
          permission: capability.permission,
          platform: capability.platform,
        }));
      }
      return run.plan.capabilities
        .filter((capability) => capability.backendRequired)
        .map((capability) => ({
          capabilityId: capability.capabilityId,
          capabilityName: capability.capabilityName,
          platform: capability.platform,
          strategy: capability.strategy,
        }));
    case "miniapp-component-mapping-engine":
      if (declaredPattern === "component-mapping-plan.json") {
        return run.plan.components;
      }
      if (declaredPattern === "generated-component-specs.json") {
        return run.plan.components.map((mapping) => ({
          classification: mapping.classification,
          componentId: mapping.componentId,
          platform: mapping.platform,
          targetComponent: mapping.targetComponent,
        }));
      }
      return run.plan.components.map((mapping) => ({
        classification: mapping.classification,
        componentId: mapping.componentId,
        strategy: mapping.strategy,
      }));
    case "miniapp-state-event-lifecycle-converter":
      if (declaredPattern === "state-lowering-plan.json") {
        return run.plan.stateLifecycle.map((decision) => ({
          platform: decision.platform,
          states: decision.states,
        }));
      }
      if (declaredPattern === "event-binding-plan.json") {
        return run.plan.stateLifecycle.map((decision) => ({
          events: decision.events,
          platform: decision.platform,
        }));
      }
      if (declaredPattern === "lifecycle-plan.json") {
        return run.plan.stateLifecycle.map((decision) => ({
          effects: decision.effects,
          platform: decision.platform,
        }));
      }
      return run.plan.stateLifecycle.map((decision) => ({
        platform: decision.platform,
        sideEffectLedger: decision.sideEffectLedger,
      }));
    case "miniapp-style-layout-converter":
      if (declaredPattern === "style-plan.json") {
        return run.plan.styles;
      }
      if (declaredPattern === "token-map.json") {
        return run.plan.styles.map((style) => ({
          platform: style.platform,
          tokens: style.tokens,
        }));
      }
      if (declaredPattern === "responsive-rules.json") {
        return run.plan.styles.map((style) => ({
          platform: style.platform,
          responsivePolicy: style.responsivePolicy,
          responsiveRules: style.rules.filter((rule) =>
            run.analysis.styles.some(
              (sourceStyle) => sourceStyle.id === rule.styleId && sourceStyle.responsive,
            ),
          ),
        }));
      }
      return run.plan.styles.map((style) => ({
        platform: style.platform,
        unsupported: style.rules.flatMap((rule) => rule.unsupported),
      }));
    case "miniapp-third-party-dependency-migrator":
      if (declaredPattern === "dependency-migration-plan.json") {
        return run.plan.dependencies;
      }
      if (declaredPattern === "replacement-graph.json") {
        return run.plan.dependencies.map((dependency) => ({
          package: dependency.dependency,
          replacement: dependency.replacement,
          strategy: dependency.action,
        }));
      }
      if (declaredPattern === "license-report.json") {
        return run.plan.dependencies.map((dependency) => ({
          licenseState: dependency.licenseState,
          package: dependency.dependency,
        }));
      }
      return run.plan.dependencies.map((dependency) => ({
        package: dependency.dependency,
        vulnerabilityState: dependency.vulnerabilityState,
      }));
    case "miniapp-commerce-social-adapter":
      if (declaredPattern === "commerce-social-contracts.json") {
        return run.plan.commerceSocial;
      }
      if (declaredPattern === "backend-api-specs") {
        return {
          identity: run.plan.commerceSocial.identity,
          order: run.plan.commerceSocial.order,
          payment: run.plan.commerceSocial.payment,
        };
      }
      if (declaredPattern === "platform-adapter-specs") {
        return run.plan.commerceSocial.platformAdapters;
      }
      return {
        payment: run.plan.commerceSocial.payment,
        productionAuthority: Object.fromEntries(
          Object.entries(run.plan.commerceSocial.platformAdapters).map(([platformName, adapter]) => [
            platformName,
            adapter.productionAuthority,
          ]),
        ),
      };
    case "miniapp-privacy-permission-auditor":
      if (declaredPattern === "privacy-report.json") {
        return run.privacy;
      }
      if (declaredPattern === "permission-manifest.json") {
        return run.privacy.map((audit) => ({
          permissions: audit.permissions,
          platform: audit.platform,
        }));
      }
      if (declaredPattern === "secret-scan.json") {
        return run.privacy.map((audit) => ({
          secretFindings: audit.secretFindings,
          platform: audit.platform,
        }));
      }
      return run.privacy.map((audit) => ({
        findings: audit.findings,
        platform: audit.platform,
        verdict: audit.verdict,
      }));
    case "miniapp-differential-testing":
      return {
        authoritativeExecution: "NOT_RUN",
        differential: run.differential,
        semanticParity: "NOT_ESTABLISHED",
      };
    case "miniapp-visual-regression-testing":
      return {
        authoritativeExecution: "NOT_RUN",
        visual: run.visual,
      };
    case "miniapp-auto-repair-loop":
      if (declaredPattern === "repair-action.json") {
        return run.repair;
      }
      if (declaredPattern === "patches/**") {
        return {
          appliedIterations: run.repair.appliedIterations,
          execution: "NOT_RUN",
          mode: run.repair.state,
        };
      }
      if (declaredPattern === "repair-history.json") {
        return {
          appliedIterations: run.repair.appliedIterations,
          candidates: run.repair.candidates,
          mode: run.repair.state,
        };
      }
      return {
        differentialRuntime: run.differential.targetRuntimeCapture,
        execution: "NOT_RUN",
        visualExecution: run.visual.targetScreenshots,
      };
    case "miniapp-ci-build-release":
      return {
        certification: run.certification,
        delivery: run.delivery,
        execution: "NOT_RUN",
        officialProjectStates: run.generatedProjects.map((project) => ({
          officialBuild: project.officialBuild,
          platform: project.platform,
          preview: project.preview,
          release: project.release,
          upload: project.upload,
        })),
      };
    case "miniapp-migration-evidence-reporter":
      return reporterPayload(run, declaredPattern);
    case "wechat-miniapp-codegen":
    case "alipay-miniapp-codegen":
    case "douyin-miniapp-codegen":
    case "xiaohongshu-miniapp-codegen":
      throw new Error(`unreachable codegen payload dispatch for ${ownerSkill}`);
    default: {
      const exhaustive: never = ownerSkill;
      return exhaustive;
    }
  }
}

export function validateMiniappDeclaredOutputCatalog(): MiniappDeclaredOutputCatalogSummary {
  const owners = new Set<string>();
  const tasks = new Set<string>();
  let outputCount = 0;
  for (const contract of MINIAPP_DECLARED_OUTPUT_CATALOG) {
    if (owners.has(contract.ownerSkill)) {
      throw new Error(`duplicate miniapp declared-output owner: ${contract.ownerSkill}`);
    }
    owners.add(contract.ownerSkill);
    const ownerOutputs = new Set<string>();
    for (const taskId of contract.taskIds) {
      if (tasks.has(taskId)) {
        throw new Error(`duplicate miniapp declared-output task: ${taskId}`);
      }
      tasks.add(taskId);
    }
    for (const requiredOutput of contract.requiredOutputs) {
      if (requiredOutput.length === 0 || ownerOutputs.has(requiredOutput)) {
        throw new Error(
          `invalid or duplicate miniapp declared output for ${contract.ownerSkill}: ${requiredOutput}`,
        );
      }
      ownerOutputs.add(requiredOutput);
      outputCount += 1;
    }
  }
  const expectedTasks = Array.from(
    { length: 40 },
    (_value, index) => `MAPP-${String(index + 1).padStart(3, "0")}`,
  );
  if (
    owners.size !== 22 ||
    tasks.size !== 40 ||
    outputCount !== 88 ||
    expectedTasks.some((taskId) => !tasks.has(taskId))
  ) {
    throw new Error(
      `invalid miniapp declared-output catalog counts: skills=${owners.size} tasks=${tasks.size} outputs=${outputCount}`,
    );
  }
  if (
    MINIAPP_CANONICAL_SCHEMA_FILES.length !== 14 ||
    new Set(MINIAPP_CANONICAL_SCHEMA_FILES).size !== 14
  ) {
    throw new Error("canonical miniapp Schema inventory must contain exactly 14 files");
  }
  const schemaBindings = new Set<string>();
  for (const binding of MINIAPP_DECLARED_OUTPUT_SCHEMA_BINDINGS) {
    const contract = MINIAPP_DECLARED_OUTPUT_CATALOG.find(
      (candidate) => candidate.ownerSkill === binding.ownerSkill,
    );
    if (
      contract === undefined ||
      !(contract.requiredOutputs as readonly string[]).includes(binding.declaredPattern)
    ) {
      throw new Error(
        `miniapp Schema binding does not own a declared output: ${binding.ownerSkill}:${binding.declaredPattern}`,
      );
    }
    const key = `${binding.ownerSkill}\u0000${binding.declaredPattern}`;
    if (schemaBindings.has(key)) {
      throw new Error(`duplicate miniapp declared-output Schema binding: ${key}`);
    }
    schemaBindings.add(key);
  }
  return {
    requiredOutputs: outputCount,
    skills: owners.size,
    tasks: tasks.size,
  };
}

function declaredMarkdownContent(
  run: MiniappConversionRun,
  ownerSkill: MiniappSkillName,
  declaredPattern: string,
): string | undefined {
  if (
    ownerSkill === "miniapp-privacy-permission-auditor" &&
    declaredPattern === "review-disclosure-checklist.md"
  ) {
    const lines = [
      "# Privacy and Permission Review Checklist",
      "",
      `Request: ${run.request.requestId}`,
      "",
      "- [x] Static privacy and secret audit executed.",
      "- [ ] Official platform privacy review: NOT_RUN.",
      "- [ ] Production account permission verification: NOT_RUN.",
      "",
      "## Platform findings",
      "",
      ...run.privacy.flatMap((audit) => [
        `### ${audit.platform}`,
        "",
        `- Static verdict: ${audit.verdict}`,
        `- Platform review: ${audit.platformReview}`,
        `- Declared permissions: ${audit.permissions
          .map((permission) => permission.permission)
          .join(", ") || "none"}`,
        `- Findings: ${audit.findings.join("; ") || "none"}`,
        "",
      ]),
    ];
    return `${lines.join("\n").trimEnd()}\n`;
  }
  if (
    ownerSkill === "miniapp-migration-evidence-reporter" &&
    declaredPattern === "validation-report.md"
  ) {
    const lines = [
      "# Validation Report",
      "",
      `Request: ${run.request.requestId}`,
      `Local engineering: ${run.localEngineering}`,
      `Certification: ${run.certification}`,
      "",
      "| Gate | State | Reason |",
      "| --- | --- | --- |",
      ...run.gates.map(
        (gate) =>
          `| ${gate.gate} | ${gate.state} | ${gate.reason.replaceAll("|", "\\|")} |`,
      ),
      "",
      "Official builds, runtime differential, visual, performance, upload, review, and release remain NOT_RUN.",
    ];
    return `${lines.join("\n").trimEnd()}\n`;
  }
  if (
    ownerSkill === "miniapp-migration-evidence-reporter" &&
    declaredPattern === "release-readiness.md"
  ) {
    const lines = [
      "# Release Readiness",
      "",
      `Request: ${run.request.requestId}`,
      `Readiness: ${run.readiness}`,
      `Certification: ${run.certification}`,
      `Delivery execution: ${run.delivery.state}`,
      "",
      "This locally generated report does not authorize preview, upload, review, or release.",
      "All official release-side operations remain NOT_RUN.",
    ];
    return `${lines.join("\n").trimEnd()}\n`;
  }
  return undefined;
}

function buildArtifact(
  ownerSkill: MiniappSkillName,
  declaredPattern: string,
  materializedPath: string,
  state: MiniappDeclaredOutputState,
  body: unknown,
  media: "json" | "text" = "json",
): MiniappDeclaredOutputArtifact {
  if (media === "text" && typeof body !== "string") {
    throw new Error(`text miniapp declared output body must be a string: ${declaredPattern}`);
  }
  const content = media === "text" ? (body as string) : canonicalJson(body);
  const bytes = Buffer.byteLength(content, "utf8");
  return {
    bytes,
    content,
    declaredPattern,
    digest: `sha256:${createHash("sha256").update(content, "utf8").digest("hex")}`,
    materializedPath,
    ownerSkill,
    state,
  };
}

export function materializeMiniappDeclaredOutputIndex(
  artifacts: readonly MiniappDeclaredOutputArtifact[],
): readonly MiniappDeclaredOutputArtifactIndexEntry[] {
  const paths = new Set<string>();
  const declarations = new Set<string>();
  return artifacts.map((artifact) => {
    const pathKey = indexedOutputPathCollisionKey(artifact.materializedPath);
    if (paths.has(pathKey)) {
      throw new Error(
        `duplicate path while indexing miniapp declared output: ${artifact.materializedPath}`,
      );
    }
    paths.add(pathKey);
    const expectedBytes = Buffer.byteLength(artifact.content, "utf8");
    const expectedDigest = `sha256:${createHash("sha256")
      .update(artifact.content, "utf8")
      .digest("hex")}`;
    if (artifact.bytes !== expectedBytes || artifact.digest !== expectedDigest) {
      throw new Error(
        `miniapp declared output content identity mismatch: ${artifact.materializedPath}`,
      );
    }
    const contract = MINIAPP_DECLARED_OUTPUT_CATALOG.find(
      (candidate) => candidate.ownerSkill === artifact.ownerSkill,
    );
    if (
      contract === undefined ||
      !(contract.requiredOutputs as readonly string[]).includes(artifact.declaredPattern)
    ) {
      throw new Error(
        `cannot index undeclared miniapp output: ${artifact.ownerSkill}:${artifact.declaredPattern}`,
      );
    }
    const declarationKey = `${artifact.ownerSkill}\u0000${artifact.declaredPattern}`;
    if (declarations.has(declarationKey)) {
      throw new Error(`duplicate miniapp output declaration while indexing: ${artifact.ownerSkill}:${artifact.declaredPattern}`);
    }
    declarations.add(declarationKey);
    if (!DECLARED_OUTPUT_STATES.has(artifact.state)) {
      throw new Error(`invalid miniapp declared output state while indexing: ${String(artifact.state)}`);
    }
    const schema = miniappDeclaredOutputSchema(
      artifact.ownerSkill,
      artifact.declaredPattern,
    );
    return {
      artifact_id: `declared-output-${bodyDigestHex({
        declared_pattern: artifact.declaredPattern,
        materialized_path: artifact.materializedPath,
        owner_skill: artifact.ownerSkill,
      }).slice(0, 24)}`,
      owner_skill: artifact.ownerSkill,
      task_ids: contract.taskIds,
      declared_pattern: artifact.declaredPattern,
      materialized_path: artifact.materializedPath,
      state: artifact.state,
      digest: artifact.digest,
      bytes: artifact.bytes,
      schema: schema === undefined ? null : `schemas/${schema}`,
    };
  });
}

function materializeMiniappGeneratedMemberIndex(
  artifacts: readonly MiniappGeneratedProjectArtifact[],
): readonly MiniappOutputArtifactIndexEntry[] {
  const paths = new Set<string>();
  return artifacts.map((artifact) => {
    const pathKey = indexedOutputPathCollisionKey(artifact.materializedPath);
    if (paths.has(pathKey)) {
      throw new Error(
        `duplicate path while indexing generated miniapp member: ${artifact.materializedPath}`,
      );
    }
    paths.add(pathKey);
    const expectedBytes = Buffer.byteLength(artifact.content, "utf8");
    const expectedDigest = `sha256:${createHash("sha256")
      .update(artifact.content, "utf8")
      .digest("hex")}`;
    if (
      artifact.state !== "PASSED_LOCAL" ||
      artifact.bytes !== expectedBytes ||
      artifact.digest !== expectedDigest ||
      artifact.ownerSkill !== CODEGEN_SKILL_BY_PLATFORM[artifact.platform] ||
      artifact.declaredPattern !== generatedDeclaredPattern(artifact.platform) ||
      assertSafeGeneratedSourcePath(artifact.sourcePath) !== artifact.sourcePath ||
      artifact.materializedPath !== `${artifact.declaredBasePath}/${artifact.sourcePath}`
    ) {
      throw new Error(
        `generated miniapp member identity mismatch while indexing: ${artifact.materializedPath}`,
      );
    }
    const contract = MINIAPP_DECLARED_OUTPUT_CATALOG.find(
      (candidate) => candidate.ownerSkill === artifact.ownerSkill,
    );
    if (
      contract === undefined ||
      !(contract.requiredOutputs as readonly string[]).includes(artifact.declaredPattern)
    ) {
      throw new Error(
        `generated miniapp member has no owning wildcard: ${artifact.materializedPath}`,
      );
    }
    return {
      artifact_id: `generated-member-${bodyDigestHex({
        declared_pattern: artifact.declaredPattern,
        materialized_path: artifact.materializedPath,
        owner_skill: artifact.ownerSkill,
      }).slice(0, 24)}`,
      owner_skill: artifact.ownerSkill,
      task_ids: contract.taskIds,
      declared_pattern: artifact.declaredPattern,
      materialized_path: artifact.materializedPath,
      state: artifact.state,
      digest: artifact.digest,
      bytes: artifact.bytes,
      schema: null,
    };
  });
}

function combinedOutputIndexEntries(
  declaredArtifacts: readonly MiniappDeclaredOutputArtifact[],
  generatedArtifacts: readonly MiniappGeneratedProjectArtifact[],
): readonly MiniappOutputArtifactIndexEntry[] {
  const declared = materializeMiniappDeclaredOutputIndex(declaredArtifacts);
  const generated = materializeMiniappGeneratedMemberIndex(generatedArtifacts);
  const paths = new Set<string>();
  for (const entry of [...declared, ...generated]) {
    const collisionKey = entry.materialized_path.normalize("NFC").toLowerCase();
    if (paths.has(collisionKey)) {
      throw new Error(
        `duplicate combined miniapp output index path: ${entry.materialized_path}`,
      );
    }
    paths.add(collisionKey);
  }
  return [...declared, ...generated];
}

function isDeclaredArtifactIndex(declaredPattern: string): boolean {
  return (
    declaredPattern === "runs/<run-id>/artifacts-index.json" ||
    declaredPattern === "artifact-index.json"
  );
}

export function materializeMiniappDeclaredOutputs(
  run: MiniappConversionRun,
): readonly MiniappDeclaredOutputArtifact[] {
  validateMiniappDeclaredOutputCatalog();
  const artifacts: MiniappDeclaredOutputArtifact[] = [];
  const paths = new Set<string>();
  for (const contract of MINIAPP_DECLARED_OUTPUT_CATALOG) {
    const platform = codegenPlatform(contract.ownerSkill);
    const tokens: MiniappOutputPathTokens = {
      "run-id": run.runId,
      framework: run.request.source.sourceLabel,
      target: platform ?? run.request.targets[0]?.platform ?? "no-target",
    };
    for (const declaredPattern of contract.requiredOutputs) {
      const state = outputState(run, contract.ownerSkill, declaredPattern);
      const materializedPath = materializeMiniappOutputPath(
        outputPathTemplate(contract.ownerSkill, declaredPattern, state),
        tokens,
      );
      if (paths.has(materializedPath)) {
        throw new Error(`duplicate materialized miniapp output path: ${materializedPath}`);
      }
      paths.add(materializedPath);
      const schema = miniappDeclaredOutputSchema(contract.ownerSkill, declaredPattern);
      const markdown = declaredMarkdownContent(
        run,
        contract.ownerSkill,
        declaredPattern,
      );
      const body =
        markdown ??
        (schema === undefined
          ? outputPayload(run, contract.ownerSkill, declaredPattern)
          : schemaExactOutputBody(run, contract.ownerSkill, schema));
      artifacts.push(
        buildArtifact(
          contract.ownerSkill,
          declaredPattern,
          materializedPath,
          state,
          body,
          markdown === undefined ? "json" : "text",
        ),
      );
    }
  }
  const nonIndexArtifacts = artifacts.filter(
    (artifact) => !isDeclaredArtifactIndex(artifact.declaredPattern),
  );
  const generatedArtifacts = materializeMiniappGeneratedProjectArtifacts(run);
  const artifactIndex = combinedOutputIndexEntries(
    nonIndexArtifacts,
    generatedArtifacts,
  );
  const indexPaths = artifacts
    .filter((artifact) => isDeclaredArtifactIndex(artifact.declaredPattern))
    .map((artifact) => artifact.materializedPath);
  return artifacts.map((artifact) =>
    isDeclaredArtifactIndex(artifact.declaredPattern)
      ? buildArtifact(
          artifact.ownerSkill,
          artifact.declaredPattern,
          artifact.materializedPath,
          artifact.state,
          {
            artifacts: artifactIndex,
            run_id: run.runId,
            schema_version: "1.0.0",
            self_referential_outputs_excluded: indexPaths,
          },
        )
      : artifact,
  );
}

/**
 * Exact inventory written into both self-excluding global artifact indexes.
 * It contains the 86 non-index declarations plus every materialized member
 * owned by a locally passed codegen wildcard.
 */
export function materializeMiniappCombinedOutputIndex(
  run: MiniappConversionRun,
): readonly MiniappOutputArtifactIndexEntry[] {
  const declared = materializeMiniappDeclaredOutputs(run).filter(
    (artifact) => !isDeclaredArtifactIndex(artifact.declaredPattern),
  );
  return combinedOutputIndexEntries(
    declared,
    materializeMiniappGeneratedProjectArtifacts(run),
  );
}

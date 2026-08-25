import { createHash } from "node:crypto";

import {
  MINIAPP_INVENTORY_HARD_LIMITS,
  MiniappContractValidationError,
  normalizeMiniappRelativePath,
  validateMiniappConversionRequest,
  validateMiniappInventoryLimits,
} from "./miniapp-contract-validation.js";
import {
  inventoryMiniappSource,
  MiniappInventoryError,
} from "./miniapp-inventory.js";
import {
  computeMiniappSourceFileSetDigest,
  type MiniappConversionExecutionInput,
} from "./miniapp-skill-runtime.js";
import {
  MINIAPP_EVIDENCE_STATES,
  MINIAPP_PLATFORMS,
  type MiniappEvidenceReference,
  type MiniappEvidenceState,
  type MiniappInventoryInputFile,
  type MiniappInventoryLimits,
  type MiniappPlatform,
  type MiniappSecretReference,
  type MiniappSourceLabel,
} from "./miniapp-types.js";

const PACKAGE_FRAMEWORK_HINTS = [
  "auto",
  "vue2",
  "vue3",
  "react",
  "flutter",
  "h5",
  "taro",
  "uni-app",
  "native-miniapp",
] as const;

export type MiniappPackageFrameworkHint = typeof PACKAGE_FRAMEWORK_HINTS[number];

const requestIdPattern = /^conv-[a-z0-9][a-z0-9-]{2,63}$/;
const immutableRevisionPattern = /^(?:[a-f0-9]{7,64}|sha256:[a-f0-9]{64})$/;
const exactVersionPattern = /^[0-9]+(?:\.[0-9]+){1,3}(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/;
const sha256Pattern = /^sha256:[a-f0-9]{64}$/;
const scopedIdPattern = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$/;
const secretReferencePattern = /^(?:vault|secret|kms):\/\/[A-Za-z0-9][A-Za-z0-9._/@:-]{0,511}$/;
const evidenceUriPattern = /^(?:artifact|cas|evidence|file):\/\/[A-Za-z0-9][A-Za-z0-9._/@:+-]{0,1023}$/;

export type MiniappPackageJsonValue =
  | null
  | boolean
  | number
  | string
  | readonly MiniappPackageJsonValue[]
  | MiniappPackageJsonObject;

export interface MiniappPackageJsonObject {
  readonly [key: string]: MiniappPackageJsonValue;
}

export interface MiniappPackageSourceRequest {
  readonly root: string;
  readonly revision: string;
  readonly framework_hint: MiniappPackageFrameworkHint;
  readonly include: readonly string[];
  readonly exclude: readonly string[];
}

export interface MiniappPackageStrategyRequest {
  readonly priority: "fidelity" | "maintainability" | "platform-native" | "code-sharing" | "balanced";
  readonly webview_fallback: "deny" | "approval-required" | "allow";
  readonly full_page_canvas_fallback: "deny" | "approval-required";
  readonly unsupported_policy: "block" | "report-and-continue-noncritical" | "ask-decision";
}

export interface MiniappPackageQualityRequest {
  readonly critical_flow_pass_rate: number;
  readonly visual_similarity_min: number;
  readonly max_auto_repair_iterations: number;
  readonly performance_policy_ref?: string;
}

export interface MiniappPackageReleaseRequest {
  readonly mode: "build-only" | "preview" | "upload" | "review" | "release";
  readonly human_approval_required: boolean;
  readonly credential_refs: Readonly<Record<string, string>>;
}

export interface MiniappPackageConversionRequest {
  readonly request_id: string;
  readonly tenant_id: string;
  readonly source: MiniappPackageSourceRequest;
  readonly targets: readonly MiniappPlatform[];
  readonly strategy: MiniappPackageStrategyRequest;
  readonly quality: MiniappPackageQualityRequest;
  readonly release: MiniappPackageReleaseRequest;
  readonly metadata: MiniappPackageJsonObject;
}

export interface MiniappPackageSourceVersionBinding {
  readonly immutableRevision?: string;
  readonly frameworkVersion: string;
  readonly languageVersion: string;
  readonly runtimeVersion: string;
  readonly buildToolVersion: string;
}

export interface MiniappPackageTargetVersionBinding {
  readonly platform: MiniappPlatform;
  readonly platformVersion: string;
  readonly toolchainVersion: string;
}

export interface MiniappPackageVersionBindings {
  readonly source: MiniappPackageSourceVersionBinding;
  readonly targets: readonly MiniappPackageTargetVersionBinding[];
  readonly inventoryLimits: MiniappInventoryLimits;
}

export interface MiniappPackageConversionInput {
  readonly packageRequest: MiniappPackageConversionRequest;
  readonly files: readonly MiniappInventoryInputFile[];
  readonly versionBindings: MiniappPackageVersionBindings;
  readonly evidenceBindings: readonly MiniappEvidenceReference[];
}

export interface PackageConversionPolicyBinding {
  readonly sourceSelection: {
    readonly originalRoot: string;
    readonly normalizedRoot: string;
    readonly originalRevision: string;
    readonly immutableRevision: string;
    readonly frameworkHint: MiniappPackageFrameworkHint;
    readonly resolvedSourceLabel: MiniappSourceLabel;
    readonly include: readonly string[];
    readonly exclude: readonly string[];
    readonly suppliedFilePaths: readonly string[];
    readonly selectedSuppliedFilePaths: readonly string[];
    readonly selectedFilePaths: readonly string[];
    readonly excludedFilePaths: readonly string[];
    readonly outsideRootFilePaths: readonly string[];
    readonly suppliedSnapshotDigest: string;
    readonly selectedFileSetDigest: string;
  };
  readonly strategy: {
    readonly priority: MiniappPackageStrategyRequest["priority"];
    readonly webviewFallback: MiniappPackageStrategyRequest["webview_fallback"];
    readonly fullPageCanvasFallback: MiniappPackageStrategyRequest["full_page_canvas_fallback"];
    readonly unsupportedPolicy: MiniappPackageStrategyRequest["unsupported_policy"];
  };
  readonly quality: {
    readonly criticalFlowPassRate: number;
    readonly visualSimilarityMin: number;
    readonly maxAutoRepairIterations: number;
    readonly performancePolicyRef?: string;
  };
  readonly release: {
    readonly mode: MiniappPackageReleaseRequest["mode"];
    readonly humanApprovalRequired: boolean;
    readonly credentialReferences: readonly MiniappSecretReference[];
  };
  readonly inventoryLimits: MiniappInventoryLimits;
  readonly metadata: MiniappPackageJsonObject;
}

export interface CompiledMiniappPackageConversion {
  readonly schemaVersion: "1.0";
  readonly executionInput: MiniappConversionExecutionInput;
  readonly policyBinding: PackageConversionPolicyBinding;
  readonly packageRequestDigest: string;
  readonly sourceSnapshotDigest: string;
  readonly selectedSourceFileSetDigest: string;
  readonly inputBindingDigest: string;
}

export type MiniappPackageContractErrorCode =
  | "MINIAPP_PACKAGE_CONTRACT_INVALID"
  | "MINIAPP_PACKAGE_REVISION_BINDING_REQUIRED"
  | "MINIAPP_PACKAGE_REVISION_BINDING_MISMATCH"
  | "MINIAPP_PACKAGE_TARGET_BINDING_MISSING"
  | "MINIAPP_PACKAGE_TARGET_BINDING_UNEXPECTED"
  | "MINIAPP_PACKAGE_SOURCE_EVIDENCE_MISSING"
  | "MINIAPP_PACKAGE_SOURCE_EVIDENCE_MISMATCH"
  | "MINIAPP_PACKAGE_SOURCE_SELECTION_EMPTY"
  | "MINIAPP_PACKAGE_SECRET_MATERIAL_REJECTED"
  | "MINIAPP_PACKAGE_FRAMEWORK_AUTO_BLOCKED"
  | "MINIAPP_PACKAGE_FRAMEWORK_BINDING_BLOCKED"
  | "MINIAPP_PACKAGE_RELEASE_APPROVAL_REQUIRED"
  | "MINIAPP_PACKAGE_INVENTORY_BLOCKED"
  | "MINIAPP_PACKAGE_INTERNAL_BINDING_INVALID";

export class MiniappPackageContractError extends Error {
  readonly state = "BLOCKED" as const;

  constructor(
    readonly code: MiniappPackageContractErrorCode,
    readonly path: string,
    reason: string,
    readonly details: Readonly<Record<string, unknown>> = {},
  ) {
    super(`${path}: ${reason}`);
    this.name = "MiniappPackageContractError";
  }
}

function block(
  code: MiniappPackageContractErrorCode,
  path: string,
  reason: string,
  details: Readonly<Record<string, unknown>> = {},
): never {
  throw new MiniappPackageContractError(code, path, reason, details);
}

function plainObject(value: unknown, path: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return block("MINIAPP_PACKAGE_CONTRACT_INVALID", path, "must be an object");
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    return block("MINIAPP_PACKAGE_CONTRACT_INVALID", path, "must be a plain object");
  }
  return value as Record<string, unknown>;
}

function exactKeys(
  value: Readonly<Record<string, unknown>>,
  path: string,
  required: readonly string[],
  optional: readonly string[] = [],
): void {
  const allowed = new Set([...required, ...optional]);
  for (const key of required) {
    if (!Object.hasOwn(value, key)) block("MINIAPP_PACKAGE_CONTRACT_INVALID", `${path}.${key}`, "is required");
  }
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) block("MINIAPP_PACKAGE_CONTRACT_INVALID", `${path}.${key}`, "is not allowed");
  }
}

function packageText(value: unknown, path: string, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): string {
  if (typeof value !== "string" || value.length < minimum || value.length > maximum) {
    return block(
      "MINIAPP_PACKAGE_CONTRACT_INVALID",
      path,
      `must be a string from ${minimum} through ${maximum} characters`,
    );
  }
  return value;
}

function boundedText(value: unknown, path: string, pattern: RegExp, maximum: number): string {
  if (typeof value !== "string" || value.length === 0 || value.length > maximum || value !== value.trim()
    || /[\u0000-\u001f\u007f]/u.test(value) || !pattern.test(value)) {
    return block("MINIAPP_PACKAGE_CONTRACT_INVALID", path, "has an invalid format");
  }
  return value;
}

function choice<T extends string>(value: unknown, path: string, choices: readonly T[]): T {
  if (typeof value !== "string" || !choices.includes(value as T)) {
    return block("MINIAPP_PACKAGE_CONTRACT_INVALID", path, `must be one of ${choices.join(", ")}`);
  }
  return value as T;
}

function packageNumber(value: unknown, path: string, minimum: number, maximum: number): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < minimum || value > maximum) {
    return block("MINIAPP_PACKAGE_CONTRACT_INVALID", path, `must be a number from ${minimum} through ${maximum}`);
  }
  return value;
}

function packageInteger(value: unknown, path: string, minimum: number, maximum: number): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum || (value as number) > maximum) {
    return block("MINIAPP_PACKAGE_CONTRACT_INVALID", path, `must be an integer from ${minimum} through ${maximum}`);
  }
  return value as number;
}

function packageBoolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") return block("MINIAPP_PACKAGE_CONTRACT_INVALID", path, "must be a boolean");
  return value;
}

function stringArray(value: unknown, path: string, defaultValue: readonly string[]): readonly string[] {
  if (value === undefined) return [...defaultValue];
  if (!Array.isArray(value)) return block("MINIAPP_PACKAGE_CONTRACT_INVALID", path, "must be an array");
  return value.map((item, index) => normalizeSelectorPattern(item, `${path}[${index}]`));
}

function jsonValue(
  value: unknown,
  path: string,
  ancestors: ReadonlySet<object>,
  depth: number,
): MiniappPackageJsonValue {
  if (depth > 64) return block("MINIAPP_PACKAGE_CONTRACT_INVALID", path, "exceeds the JSON nesting limit");
  if (typeof value === "string") {
    assertNoMetadataSecretValue(value, path);
    return value;
  }
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (!value || typeof value !== "object") {
    return block("MINIAPP_PACKAGE_CONTRACT_INVALID", path, "must contain only JSON values");
  }
  if (ancestors.has(value)) return block("MINIAPP_PACKAGE_CONTRACT_INVALID", path, "must not contain cycles");
  const nextAncestors = new Set(ancestors);
  nextAncestors.add(value);
  if (Array.isArray(value)) {
    return value.map((item, index) => jsonValue(item, `${path}[${index}]`, nextAncestors, depth + 1));
  }
  const candidate = plainObject(value, path);
  return Object.fromEntries(Object.keys(candidate).sort(compareText).map(key => [
    safeMetadataKey(key, candidate[key], `${path}.${key}`),
    jsonValue(candidate[key], `${path}.${key}`, nextAncestors, depth + 1),
  ]));
}

function metadata(value: unknown, path: string): MiniappPackageJsonObject {
  if (value === undefined) return {};
  const candidate = plainObject(value, path);
  return Object.fromEntries(Object.keys(candidate).sort(compareText).map(key => [
    safeMetadataKey(key, candidate[key], `${path}.${key}`),
    jsonValue(candidate[key], `${path}.${key}`, new Set([candidate]), 1),
  ]));
}

function compareText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function safeMetadataKey(key: string, value: unknown, path: string): string {
  const normalized = key.normalize("NFKC").replace(/[^A-Za-z0-9]/gu, "").toLowerCase();
  if (/(?:secret|token|password|passwd|credential|privatekey|apikey|accesskey|authorization|auth|cookie|setcookie|session|header|refresh|access)(?:value|material|data)?$/u.test(normalized)
    && (typeof value !== "string" || !secretReferencePattern.test(value))) {
    return block(
      "MINIAPP_PACKAGE_SECRET_MATERIAL_REJECTED",
      path,
      "secret-like metadata fields must contain only vault://, secret:// or kms:// references",
    );
  }
  return key;
}

function assertNoMetadataSecretValue(value: string, path: string): void {
  const secretPatterns = [
    /-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE)-----/u,
    /\b(?:Bearer|Basic)\s+[A-Za-z0-9+/=_-]{8,}/iu,
    /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/u,
    /\b(?:sk|rk|pk)[_-](?:live|test)[_-][A-Za-z0-9_-]{12,}\b/iu,
    /\bsk-(?:(?:proj|svcacct)-)?[A-Za-z0-9_-]{20,}\b/u,
    /\bxox[baprs]-[A-Za-z0-9-]{10,}\b/u,
    /\bAIza[0-9A-Za-z_-]{30,}\b/u,
    /\bgh[pousr]_[A-Za-z0-9]{20,}\b/u,
    /\bAKIA[A-Z0-9]{16}\b/u,
    /[A-Za-z][A-Za-z0-9+.-]*:\/\/[^\s/:]+:[^\s/@]+@/u,
  ];
  if (secretPatterns.some(pattern => pattern.test(value))) {
    block(
      "MINIAPP_PACKAGE_SECRET_MATERIAL_REJECTED",
      path,
      "metadata contains secret-like material; use release.credential_refs",
    );
  }
}

function normalizeSelectorPattern(value: unknown, path: string): string {
  let pattern = packageText(value, path, 1, 1024);
  if (pattern !== pattern.normalize("NFC") || pattern.includes("\\")
    || /[\u0000-\u001f\u007f]/u.test(pattern)) {
    return block("MINIAPP_PACKAGE_CONTRACT_INVALID", path, "must be a normalized relative glob pattern");
  }
  while (pattern.startsWith("./")) pattern = pattern.slice(2);
  const segments = pattern.split("/");
  if (pattern.startsWith("/") || pattern.length === 0
    || segments.some(segment => segment.length === 0 || segment === "." || segment === "..")) {
    return block("MINIAPP_PACKAGE_CONTRACT_INVALID", path, "must be a normalized relative glob pattern");
  }
  if (/[{}[\]!()|]/u.test(pattern)) {
    return block(
      "MINIAPP_PACKAGE_CONTRACT_INVALID",
      path,
      "supports only literal path text, *, ?, and ** as a complete path segment",
    );
  }
  if (segments.some(segment => segment !== "**" && segment.includes("**"))) {
    return block(
      "MINIAPP_PACKAGE_CONTRACT_INVALID",
      path,
      "** is supported only as a complete path segment",
    );
  }
  return pattern;
}

function globExpression(pattern: string): RegExp {
  let expression = "^";
  for (let index = 0; index < pattern.length; index += 1) {
    const character = pattern[index]!;
    if (character === "*" && pattern[index + 1] === "*") {
      index += 1;
      if (pattern[index + 1] === "/") {
        index += 1;
        expression += "(?:[^/]+/)*";
      } else {
        expression += ".*";
      }
    } else if (character === "*") {
      expression += "[^/]*";
    } else if (character === "?") {
      expression += "[^/]";
    } else {
      expression += character.replace(/[\\^$.*+?()[\]{}|]/gu, "\\$&");
    }
  }
  return new RegExp(`${expression}$`, "u");
}

function selectSourceFiles(
  files: readonly MiniappInventoryInputFile[],
  source: MiniappPackageSourceRequest,
  normalizedRoot: string,
): {
  readonly selected: readonly MiniappInventoryInputFile[];
  readonly selectedSuppliedFilePaths: readonly string[];
  readonly excludedFilePaths: readonly string[];
  readonly outsideRootFilePaths: readonly string[];
} {
  const includes = source.include.map(globExpression);
  const excludes = source.exclude.map(globExpression);
  const selected: MiniappInventoryInputFile[] = [];
  const selectedSuppliedFilePaths: string[] = [];
  const excludedFilePaths: string[] = [];
  const outsideRootFilePaths: string[] = [];
  for (const file of files) {
    const rootRelativePath = normalizedRoot === "."
      ? file.path
      : file.path.startsWith(`${normalizedRoot}/`)
        ? file.path.slice(normalizedRoot.length + 1)
        : null;
    if (rootRelativePath === null || rootRelativePath.length === 0) {
      excludedFilePaths.push(file.path);
      outsideRootFilePaths.push(file.path);
      continue;
    }
    const included = includes.some(pattern => pattern.test(rootRelativePath));
    const explicitlyExcluded = excludes.some(pattern => pattern.test(rootRelativePath));
    if (included && !explicitlyExcluded) {
      selected.push({ path: rootRelativePath, content: file.content });
      selectedSuppliedFilePaths.push(file.path);
    } else {
      excludedFilePaths.push(file.path);
    }
  }
  if (selected.length === 0) {
    return block(
      "MINIAPP_PACKAGE_SOURCE_SELECTION_EMPTY",
      "packageRequest.source.include",
      "include/exclude selectors removed every supplied source file",
      {
        include: source.include,
        exclude: source.exclude,
        normalizedRoot,
        suppliedFilePaths: files.map(file => file.path),
        outsideRootFilePaths,
      },
    );
  }
  return {
    selected,
    selectedSuppliedFilePaths,
    excludedFilePaths,
    outsideRootFilePaths,
  };
}

function platformOrder(left: MiniappPlatform, right: MiniappPlatform): number {
  return MINIAPP_PLATFORMS.indexOf(left) - MINIAPP_PLATFORMS.indexOf(right);
}

function validatePackageSource(value: unknown): MiniappPackageSourceRequest {
  const candidate = plainObject(value, "packageRequest.source");
  exactKeys(candidate, "packageRequest.source", ["root", "revision"], ["framework_hint", "include", "exclude"]);
  return {
    root: packageText(candidate.root, "packageRequest.source.root", 1),
    revision: packageText(candidate.revision, "packageRequest.source.revision", 7),
    framework_hint: candidate.framework_hint === undefined
      ? "auto"
      : choice(candidate.framework_hint, "packageRequest.source.framework_hint", PACKAGE_FRAMEWORK_HINTS),
    include: stringArray(candidate.include, "packageRequest.source.include", ["**/*"]),
    exclude: stringArray(candidate.exclude, "packageRequest.source.exclude", []),
  };
}

function validatePackageStrategy(value: unknown): MiniappPackageStrategyRequest {
  const candidate = plainObject(value, "packageRequest.strategy");
  exactKeys(candidate, "packageRequest.strategy", [
    "priority", "webview_fallback", "full_page_canvas_fallback", "unsupported_policy",
  ]);
  return {
    priority: choice(candidate.priority, "packageRequest.strategy.priority", [
      "fidelity", "maintainability", "platform-native", "code-sharing", "balanced",
    ] as const),
    webview_fallback: choice(candidate.webview_fallback, "packageRequest.strategy.webview_fallback", [
      "deny", "approval-required", "allow",
    ] as const),
    full_page_canvas_fallback: choice(
      candidate.full_page_canvas_fallback,
      "packageRequest.strategy.full_page_canvas_fallback",
      ["deny", "approval-required"] as const,
    ),
    unsupported_policy: choice(candidate.unsupported_policy, "packageRequest.strategy.unsupported_policy", [
      "block", "report-and-continue-noncritical", "ask-decision",
    ] as const),
  };
}

function validatePackageQuality(value: unknown): MiniappPackageQualityRequest {
  const candidate = plainObject(value, "packageRequest.quality");
  exactKeys(candidate, "packageRequest.quality", [
    "critical_flow_pass_rate", "visual_similarity_min", "max_auto_repair_iterations",
  ], ["performance_policy_ref"]);
  const performancePolicyRef = candidate.performance_policy_ref === undefined
    ? undefined
    : packageText(candidate.performance_policy_ref, "packageRequest.quality.performance_policy_ref");
  return {
    critical_flow_pass_rate: packageNumber(
      candidate.critical_flow_pass_rate,
      "packageRequest.quality.critical_flow_pass_rate",
      0,
      1,
    ),
    visual_similarity_min: packageNumber(
      candidate.visual_similarity_min,
      "packageRequest.quality.visual_similarity_min",
      0,
      1,
    ),
    max_auto_repair_iterations: packageInteger(
      candidate.max_auto_repair_iterations,
      "packageRequest.quality.max_auto_repair_iterations",
      0,
      10,
    ),
    ...(performancePolicyRef === undefined ? {} : { performance_policy_ref: performancePolicyRef }),
  };
}

function validateCredentialReferences(value: unknown): Readonly<Record<string, string>> {
  if (value === undefined) return {};
  const candidate = plainObject(value, "packageRequest.release.credential_refs");
  const output = Object.create(null) as Record<string, string>;
  for (const key of Object.keys(candidate).sort(compareText)) {
    output[key] = boundedText(
      candidate[key],
      `packageRequest.release.credential_refs.${key}`,
      secretReferencePattern,
      520,
    );
  }
  return output;
}

function validatePackageRelease(value: unknown): MiniappPackageReleaseRequest {
  const candidate = plainObject(value, "packageRequest.release");
  exactKeys(candidate, "packageRequest.release", ["mode", "human_approval_required"], ["credential_refs"]);
  return {
    mode: choice(candidate.mode, "packageRequest.release.mode", [
      "build-only", "preview", "upload", "review", "release",
    ] as const),
    human_approval_required: packageBoolean(
      candidate.human_approval_required,
      "packageRequest.release.human_approval_required",
    ),
    credential_refs: validateCredentialReferences(candidate.credential_refs),
  };
}

export function validateMiniappPackageRequest(value: unknown): MiniappPackageConversionRequest {
  const candidate = plainObject(value, "packageRequest");
  exactKeys(candidate, "packageRequest", [
    "request_id", "tenant_id", "source", "targets", "strategy", "quality", "release",
  ], ["metadata"]);
  if (!Array.isArray(candidate.targets) || candidate.targets.length < 1) {
    block("MINIAPP_PACKAGE_CONTRACT_INVALID", "packageRequest.targets", "must be a non-empty array");
  }
  const targets = candidate.targets.map((target, index) =>
    choice<MiniappPlatform>(target, `packageRequest.targets[${index}]`, MINIAPP_PLATFORMS));
  if (new Set(targets).size !== targets.length) {
    block("MINIAPP_PACKAGE_CONTRACT_INVALID", "packageRequest.targets", "must contain unique platforms");
  }
  return {
    request_id: boundedText(candidate.request_id, "packageRequest.request_id", requestIdPattern, 68),
    tenant_id: packageText(candidate.tenant_id, "packageRequest.tenant_id", 1, 128),
    source: validatePackageSource(candidate.source),
    targets: [...targets].sort(platformOrder),
    strategy: validatePackageStrategy(candidate.strategy),
    quality: validatePackageQuality(candidate.quality),
    release: validatePackageRelease(candidate.release),
    metadata: metadata(candidate.metadata, "packageRequest.metadata"),
  };
}

function validateSourceVersionBinding(value: unknown): MiniappPackageSourceVersionBinding {
  const candidate = plainObject(value, "packageInput.versionBindings.source");
  exactKeys(candidate, "packageInput.versionBindings.source", [
    "frameworkVersion", "languageVersion", "runtimeVersion", "buildToolVersion",
  ], ["immutableRevision"]);
  const immutableRevision = candidate.immutableRevision === undefined
    ? undefined
    : boundedText(
      candidate.immutableRevision,
      "packageInput.versionBindings.source.immutableRevision",
      immutableRevisionPattern,
      71,
    );
  return {
    ...(immutableRevision === undefined ? {} : { immutableRevision }),
    frameworkVersion: boundedText(
      candidate.frameworkVersion,
      "packageInput.versionBindings.source.frameworkVersion",
      exactVersionPattern,
      128,
    ),
    languageVersion: boundedText(
      candidate.languageVersion,
      "packageInput.versionBindings.source.languageVersion",
      exactVersionPattern,
      128,
    ),
    runtimeVersion: boundedText(
      candidate.runtimeVersion,
      "packageInput.versionBindings.source.runtimeVersion",
      exactVersionPattern,
      128,
    ),
    buildToolVersion: boundedText(
      candidate.buildToolVersion,
      "packageInput.versionBindings.source.buildToolVersion",
      exactVersionPattern,
      128,
    ),
  };
}

function validateTargetVersionBinding(value: unknown, index: number): MiniappPackageTargetVersionBinding {
  const path = `packageInput.versionBindings.targets[${index}]`;
  const candidate = plainObject(value, path);
  exactKeys(candidate, path, ["platform", "platformVersion", "toolchainVersion"]);
  return {
    platform: choice<MiniappPlatform>(candidate.platform, `${path}.platform`, MINIAPP_PLATFORMS),
    platformVersion: boundedText(candidate.platformVersion, `${path}.platformVersion`, exactVersionPattern, 128),
    toolchainVersion: boundedText(candidate.toolchainVersion, `${path}.toolchainVersion`, exactVersionPattern, 128),
  };
}

function validateVersionBindings(value: unknown): MiniappPackageVersionBindings {
  const candidate = plainObject(value, "packageInput.versionBindings");
  exactKeys(candidate, "packageInput.versionBindings", ["source", "targets"], ["inventoryLimits"]);
  if (!Array.isArray(candidate.targets) || candidate.targets.length < 1) {
    block("MINIAPP_PACKAGE_CONTRACT_INVALID", "packageInput.versionBindings.targets", "must be a non-empty array");
  }
  const targets = candidate.targets.map(validateTargetVersionBinding);
  const platforms = new Set<MiniappPlatform>();
  for (const target of targets) {
    if (platforms.has(target.platform)) {
      block(
        "MINIAPP_PACKAGE_CONTRACT_INVALID",
        "packageInput.versionBindings.targets",
        `contains duplicate platform ${target.platform}`,
      );
    }
    platforms.add(target.platform);
  }
  let inventoryLimits: MiniappInventoryLimits;
  try {
    inventoryLimits = candidate.inventoryLimits === undefined
      ? { ...MINIAPP_INVENTORY_HARD_LIMITS }
      : validateMiniappInventoryLimits(candidate.inventoryLimits, "packageInput.versionBindings.inventoryLimits");
  } catch (error) {
    if (error instanceof MiniappContractValidationError) {
      return block("MINIAPP_PACKAGE_CONTRACT_INVALID", error.path, error.message.slice(error.path.length + 2));
    }
    throw error;
  }
  return {
    source: validateSourceVersionBinding(candidate.source),
    targets: [...targets].sort((left, right) => platformOrder(left.platform, right.platform)),
    inventoryLimits,
  };
}

function validateFiles(value: unknown): readonly MiniappInventoryInputFile[] {
  if (!Array.isArray(value) || value.length < 1) {
    return block("MINIAPP_PACKAGE_CONTRACT_INVALID", "packageInput.files", "must be a non-empty array");
  }
  const seen = new Set<string>();
  const files = value.map((item, index) => {
    const path = `packageInput.files[${index}]`;
    const candidate = plainObject(item, path);
    exactKeys(candidate, path, ["path", "content"]);
    let normalizedPath: string;
    try {
      normalizedPath = normalizeMiniappRelativePath(candidate.path, `${path}.path`);
    } catch (error) {
      if (error instanceof MiniappContractValidationError) {
        return block("MINIAPP_PACKAGE_CONTRACT_INVALID", error.path, error.message.slice(error.path.length + 2));
      }
      throw error;
    }
    if (normalizedPath === ".") {
      return block("MINIAPP_PACKAGE_CONTRACT_INVALID", `${path}.path`, "must identify a file");
    }
    if (seen.has(normalizedPath)) {
      return block("MINIAPP_PACKAGE_CONTRACT_INVALID", `${path}.path`, `duplicates ${normalizedPath}`);
    }
    seen.add(normalizedPath);
    if (typeof candidate.content !== "string" && !(candidate.content instanceof Uint8Array)) {
      return block("MINIAPP_PACKAGE_CONTRACT_INVALID", `${path}.content`, "must be a string or Uint8Array");
    }
    return {
      path: normalizedPath,
      content: typeof candidate.content === "string" ? candidate.content : new Uint8Array(candidate.content),
    };
  });
  try {
    computeMiniappSourceFileSetDigest(files);
  } catch (error) {
    return block(
      "MINIAPP_PACKAGE_CONTRACT_INVALID",
      "packageInput.files",
      error instanceof Error ? error.message : "failed source-file validation",
    );
  }
  return files.sort((left, right) => compareText(left.path, right.path));
}

function validateEvidenceBinding(value: unknown, index: number): MiniappEvidenceReference {
  const path = `packageInput.evidenceBindings[${index}]`;
  const candidate = plainObject(value, path);
  exactKeys(candidate, path, [
    "role", "uri", "digest", "state", "executor", "verifier", "synthetic", "byteCount",
  ]);
  return {
    role: boundedText(candidate.role, `${path}.role`, scopedIdPattern, 128),
    uri: boundedText(candidate.uri, `${path}.uri`, evidenceUriPattern, 1024),
    digest: boundedText(candidate.digest, `${path}.digest`, sha256Pattern, 71),
    state: choice<MiniappEvidenceState>(candidate.state, `${path}.state`, MINIAPP_EVIDENCE_STATES),
    executor: boundedText(candidate.executor, `${path}.executor`, scopedIdPattern, 128),
    verifier: boundedText(candidate.verifier, `${path}.verifier`, scopedIdPattern, 128),
    synthetic: packageBoolean(candidate.synthetic, `${path}.synthetic`),
    byteCount: packageInteger(candidate.byteCount, `${path}.byteCount`, 0, Number.MAX_SAFE_INTEGER),
  };
}

function validateEvidenceBindings(value: unknown): readonly MiniappEvidenceReference[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 256) {
    return block(
      "MINIAPP_PACKAGE_CONTRACT_INVALID",
      "packageInput.evidenceBindings",
      "must contain from 1 through 256 evidence references",
    );
  }
  return value.map(validateEvidenceBinding).sort((left, right) => compareText(
    `${left.role}\u0000${left.uri}\u0000${left.digest}`,
    `${right.role}\u0000${right.uri}\u0000${right.digest}`,
  ));
}

function effectiveRevision(
  request: MiniappPackageConversionRequest,
  bindings: MiniappPackageVersionBindings,
): string {
  const original = request.source.revision;
  const bound = bindings.source.immutableRevision;
  if (!immutableRevisionPattern.test(original)) {
    if (!bound) {
      return block(
        "MINIAPP_PACKAGE_REVISION_BINDING_REQUIRED",
        "packageInput.versionBindings.source.immutableRevision",
        "is required because packageRequest.source.revision is not an immutable 7-64 hex or sha256 revision",
        { originalRevision: original },
      );
    }
    return bound;
  }
  if (bound !== undefined && bound !== original) {
    return block(
      "MINIAPP_PACKAGE_REVISION_BINDING_MISMATCH",
      "packageInput.versionBindings.source.immutableRevision",
      "must equal the already-immutable package revision when supplied",
      { originalRevision: original, immutableRevision: bound },
    );
  }
  return original;
}

function assertExactTargetBindings(
  request: MiniappPackageConversionRequest,
  bindings: MiniappPackageVersionBindings,
): void {
  const requested = new Set(request.targets);
  const bound = new Set(bindings.targets.map(target => target.platform));
  for (const platform of request.targets) {
    if (!bound.has(platform)) {
      block(
        "MINIAPP_PACKAGE_TARGET_BINDING_MISSING",
        "packageInput.versionBindings.targets",
        `is missing exact platformVersion/toolchainVersion for ${platform}`,
        { platform },
      );
    }
  }
  for (const platform of bound) {
    if (!requested.has(platform)) {
      block(
        "MINIAPP_PACKAGE_TARGET_BINDING_UNEXPECTED",
        "packageInput.versionBindings.targets",
        `contains an unrequested target binding for ${platform}`,
        { platform },
      );
    }
  }
}

function sourceByteCount(files: readonly MiniappInventoryInputFile[]): number {
  return files.reduce((total, file) => total + (typeof file.content === "string"
    ? Buffer.byteLength(file.content, "utf8")
    : file.content.byteLength), 0);
}

function assertSourceEvidence(
  evidence: readonly MiniappEvidenceReference[],
  snapshotDigest: string,
  byteCount: number,
): void {
  const snapshots = evidence.filter(item => item.role === "source-snapshot");
  if (snapshots.length === 0) {
    block(
      "MINIAPP_PACKAGE_SOURCE_EVIDENCE_MISSING",
      "packageInput.evidenceBindings",
      "must contain a source-snapshot evidence binding",
    );
  }
  if (!snapshots.some(item => item.digest === snapshotDigest
    && item.byteCount === byteCount
    && item.state === "PASSED"
    && item.synthetic === false)) {
    block(
      "MINIAPP_PACKAGE_SOURCE_EVIDENCE_MISMATCH",
      "packageInput.evidenceBindings",
      "source-snapshot evidence must bind the exact supplied bytes as non-synthetic PASSED evidence",
      { snapshotDigest, byteCount },
    );
  }
}

export function validateMiniappPackageConversionInput(value: unknown): MiniappPackageConversionInput {
  const candidate = plainObject(value, "packageInput");
  exactKeys(candidate, "packageInput", ["packageRequest", "files", "versionBindings", "evidenceBindings"]);
  const packageRequest = validateMiniappPackageRequest(candidate.packageRequest);
  const files = validateFiles(candidate.files);
  const versionBindings = validateVersionBindings(candidate.versionBindings);
  const evidenceBindings = validateEvidenceBindings(candidate.evidenceBindings);
  effectiveRevision(packageRequest, versionBindings);
  assertExactTargetBindings(packageRequest, versionBindings);
  const snapshotDigest = computeMiniappSourceFileSetDigest(files);
  assertSourceEvidence(evidenceBindings, snapshotDigest, sourceByteCount(files));
  return { packageRequest, files, versionBindings, evidenceBindings };
}

function normalizePackageRoot(value: string): string {
  let normalized = value.normalize("NFC");
  while (normalized.startsWith("./")) normalized = normalized.slice(2);
  if (normalized.length === 0) normalized = ".";
  try {
    return normalizeMiniappRelativePath(normalized, "packageRequest.source.root");
  } catch (error) {
    if (error instanceof MiniappContractValidationError) {
      return block("MINIAPP_PACKAGE_INTERNAL_BINDING_INVALID", error.path, error.message.slice(error.path.length + 2));
    }
    throw error;
  }
}

function secretReferences(release: MiniappPackageReleaseRequest): readonly MiniappSecretReference[] {
  return Object.entries(release.credential_refs).map(([name, reference]) => {
    if (!scopedIdPattern.test(name)) {
      return block(
        "MINIAPP_PACKAGE_INTERNAL_BINDING_INVALID",
        `packageRequest.release.credential_refs.${name}`,
        "credential reference name cannot be represented by the internal exact request",
      );
    }
    return { name, reference };
  }).sort((left, right) => compareText(left.name, right.name));
}

function sha256(value: string): string {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

function canonicalValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (value && typeof value === "object") {
    const candidate = value as Readonly<Record<string, unknown>>;
    return Object.fromEntries(Object.keys(candidate).sort(compareText).map(key => [key, canonicalValue(candidate[key])]));
  }
  return value;
}

export function canonicalizeMiniappPackageRequest(value: unknown): string {
  return JSON.stringify(canonicalValue(validateMiniappPackageRequest(value)));
}

export function canonicalizeMiniappPackageConversionInput(value: unknown): string {
  const input = validateMiniappPackageConversionInput(value);
  return JSON.stringify(canonicalValue({
    packageRequest: input.packageRequest,
    files: input.files.map(file => ({
      path: file.path,
      contentEncoding: "base64",
      content: Buffer.from(
        typeof file.content === "string" ? Buffer.from(file.content, "utf8") : file.content,
      ).toString("base64"),
    })),
    versionBindings: input.versionBindings,
    evidenceBindings: input.evidenceBindings,
  }));
}

export function compileMiniappPackageConversionInput(value: unknown): CompiledMiniappPackageConversion {
  const input = validateMiniappPackageConversionInput(value);
  if (input.packageRequest.release.mode !== "build-only"
    && input.packageRequest.release.human_approval_required === false) {
    return block(
      "MINIAPP_PACKAGE_RELEASE_APPROVAL_REQUIRED",
      "packageRequest.release.human_approval_required",
      `must be true when release.mode is ${input.packageRequest.release.mode}`,
      { releaseMode: input.packageRequest.release.mode },
    );
  }
  const revision = effectiveRevision(input.packageRequest, input.versionBindings);
  const normalizedRoot = normalizePackageRoot(input.packageRequest.source.root);
  const snapshotDigest = computeMiniappSourceFileSetDigest(input.files);
  const selection = selectSourceFiles(
    input.files,
    input.packageRequest.source,
    normalizedRoot,
  );
  const selectedFileSetDigest = computeMiniappSourceFileSetDigest(selection.selected);
  let inventory;
  try {
    inventory = inventoryMiniappSource({
      schemaVersion: "1.0",
      inventoryId: `inv-${input.packageRequest.request_id.slice(5)}`,
      sourceRevision: revision,
      sourceSnapshotDigest: selectedFileSetDigest,
      sourceLabelHint: input.packageRequest.source.framework_hint,
      limits: input.versionBindings.inventoryLimits,
      files: selection.selected,
    });
  } catch (error) {
    if (error instanceof MiniappInventoryError) {
      return block("MINIAPP_PACKAGE_INVENTORY_BLOCKED", error.path, error.message.slice(error.path.length + 2), {
        inventoryCode: error.code,
      });
    }
    throw error;
  }
  const requestedHint = input.packageRequest.source.framework_hint;
  const blockingFindings = inventory.findings.filter(finding => finding.blocking);
  if (requestedHint === "auto" && (inventory.selectedSourceLabel === null || blockingFindings.length > 0)) {
    return block(
      "MINIAPP_PACKAGE_FRAMEWORK_AUTO_BLOCKED",
      "packageRequest.source.framework_hint",
      "auto detection did not produce one unblocked source label",
      {
        candidates: inventory.frameworkCandidates.map(candidate => ({
          sourceLabel: candidate.sourceLabel,
          confidence: candidate.confidence,
        })),
        conflicts: inventory.frameworkConflicts,
        findings: blockingFindings,
      },
    );
  }
  if (requestedHint !== "auto"
    && (inventory.selectedSourceLabel !== requestedHint || blockingFindings.length > 0)) {
    return block(
      "MINIAPP_PACKAGE_FRAMEWORK_BINDING_BLOCKED",
      "packageRequest.source.framework_hint",
      `explicit ${requestedHint} binding is not supported by the supplied source inventory`,
      {
        selectedSourceLabel: inventory.selectedSourceLabel,
        conflicts: inventory.frameworkConflicts,
        findings: blockingFindings,
      },
    );
  }
  if (inventory.selectedSourceLabel === null) {
    return block(
      "MINIAPP_PACKAGE_FRAMEWORK_AUTO_BLOCKED",
      "packageRequest.source.framework_hint",
      "source framework remains unresolved",
    );
  }
  const credentials = secretReferences(input.packageRequest.release);
  const targetVersions = new Map(input.versionBindings.targets.map(target => [target.platform, target]));
  let request;
  try {
    request = validateMiniappConversionRequest({
      schemaVersion: "1.0",
      requestId: input.packageRequest.request_id,
      tenantId: input.packageRequest.tenant_id,
      source: {
        root: normalizedRoot,
        revision,
        snapshotDigest: selectedFileSetDigest,
        sourceLabel: inventory.selectedSourceLabel,
        frameworkVersion: input.versionBindings.source.frameworkVersion,
        languageVersion: input.versionBindings.source.languageVersion,
        runtimeVersion: input.versionBindings.source.runtimeVersion,
        buildToolVersion: input.versionBindings.source.buildToolVersion,
      },
      targets: input.packageRequest.targets.map(platform => {
        const binding = targetVersions.get(platform)!;
        return {
          platform,
          platformVersion: binding.platformVersion,
          toolchainVersion: binding.toolchainVersion,
        };
      }),
      policy: {
        priority: input.packageRequest.strategy.priority,
        webviewFallback: input.packageRequest.strategy.webview_fallback,
        fullPageCanvasFallback: input.packageRequest.strategy.full_page_canvas_fallback,
        unsupportedPolicy: input.packageRequest.strategy.unsupported_policy,
        limits: input.versionBindings.inventoryLimits,
        secretReferences: credentials,
      },
      evidence: input.evidenceBindings,
    });
  } catch (error) {
    if (error instanceof MiniappContractValidationError) {
      return block("MINIAPP_PACKAGE_INTERNAL_BINDING_INVALID", error.path, error.message.slice(error.path.length + 2));
    }
    throw error;
  }
  const quality = input.packageRequest.quality;
  const performancePolicyRef = quality.performance_policy_ref;
  const policyBinding: PackageConversionPolicyBinding = {
    sourceSelection: {
      originalRoot: input.packageRequest.source.root,
      normalizedRoot: request.source.root,
      originalRevision: input.packageRequest.source.revision,
      immutableRevision: revision,
      frameworkHint: requestedHint,
      resolvedSourceLabel: inventory.selectedSourceLabel,
      include: [...input.packageRequest.source.include],
      exclude: [...input.packageRequest.source.exclude],
      suppliedFilePaths: input.files.map(file => file.path),
      selectedSuppliedFilePaths: selection.selectedSuppliedFilePaths,
      selectedFilePaths: selection.selected.map(file => file.path),
      excludedFilePaths: selection.excludedFilePaths,
      outsideRootFilePaths: selection.outsideRootFilePaths,
      suppliedSnapshotDigest: snapshotDigest,
      selectedFileSetDigest,
    },
    strategy: {
      priority: input.packageRequest.strategy.priority,
      webviewFallback: input.packageRequest.strategy.webview_fallback,
      fullPageCanvasFallback: input.packageRequest.strategy.full_page_canvas_fallback,
      unsupportedPolicy: input.packageRequest.strategy.unsupported_policy,
    },
    quality: {
      criticalFlowPassRate: quality.critical_flow_pass_rate,
      visualSimilarityMin: quality.visual_similarity_min,
      maxAutoRepairIterations: quality.max_auto_repair_iterations,
      ...(performancePolicyRef === undefined ? {} : { performancePolicyRef }),
    },
    release: {
      mode: input.packageRequest.release.mode,
      humanApprovalRequired: input.packageRequest.release.human_approval_required,
      credentialReferences: credentials,
    },
    inventoryLimits: { ...input.versionBindings.inventoryLimits },
    metadata: input.packageRequest.metadata,
  };
  const packageRequestText = canonicalizeMiniappPackageRequest(input.packageRequest);
  const inputBindingText = canonicalizeMiniappPackageConversionInput(input);
  return {
    schemaVersion: "1.0",
    executionInput: { schemaVersion: "1.0", request, files: selection.selected },
    policyBinding,
    packageRequestDigest: sha256(packageRequestText),
    sourceSnapshotDigest: snapshotDigest,
    selectedSourceFileSetDigest: selectedFileSetDigest,
    inputBindingDigest: sha256(inputBindingText),
  };
}

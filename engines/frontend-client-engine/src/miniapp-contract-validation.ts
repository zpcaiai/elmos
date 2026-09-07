import {
  MINIAPP_EVIDENCE_STATES,
  MINIAPP_PLATFORMS,
  MINIAPP_SOURCE_LABELS,
  type MiniappConversionPolicy,
  type MiniappConversionRequest,
  type MiniappConversionSource,
  type MiniappConversionTarget,
  type MiniappEvidenceReference,
  type MiniappEvidenceState,
  type MiniappInventoryLimits,
  type MiniappPlatform,
  type MiniappSecretReference,
  type MiniappSourceLabel,
} from "./miniapp-types.js";

const requestIdPattern = /^conv-[a-z0-9][a-z0-9-]{2,63}$/;
const scopedIdPattern = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$/;
const revisionPattern = /^(?:[a-f0-9]{7,64}|sha256:[a-f0-9]{64})$/;
const sha256Pattern = /^sha256:[a-f0-9]{64}$/;
// Some official miniapp developer tools use zero-padded numeric segments (for
// example 1.06.x). They are still exact versions; ranges and mutable aliases are not.
const exactVersionPattern = /^[0-9]+(?:\.[0-9]+){1,3}(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/;
const secretReferencePattern = /^(?:vault|secret|kms):\/\/[A-Za-z0-9][A-Za-z0-9._/@:-]{0,511}$/;
const evidenceUriPattern = /^(?:artifact|cas|evidence|file):\/\/[A-Za-z0-9][A-Za-z0-9._/@:+-]{0,1023}$/;

export const MINIAPP_INVENTORY_HARD_LIMITS: MiniappInventoryLimits = {
  maxFileCount: 20_000,
  maxFileBytes: 16 * 1024 * 1024,
  maxTotalBytes: 256 * 1024 * 1024,
};

export class MiniappContractValidationError extends Error {
  readonly code = "MINIAPP_CONTRACT_INVALID";
  readonly path: string;

  constructor(path: string, reason: string) {
    super(`${path}: ${reason}`);
    this.name = "MiniappContractValidationError";
    this.path = path;
  }
}

function fail(path: string, reason: string): never {
  throw new MiniappContractValidationError(path, reason);
}

function object(value: unknown, path: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return fail(path, "must be an object");
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    return fail(path, "must be a plain object");
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
    if (!Object.hasOwn(value, key)) fail(`${path}.${key}`, "is required");
  }
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) fail(`${path}.${key}`, "is not allowed");
  }
}

function text(value: unknown, path: string, pattern?: RegExp, maximum = 1024): string {
  if (typeof value !== "string" || value.length === 0 || value.length > maximum) {
    return fail(path, `must be a non-empty string of at most ${maximum} characters`);
  }
  if (value !== value.trim() || /[\u0000-\u001f\u007f]/u.test(value)) {
    return fail(path, "must not contain surrounding whitespace or control characters");
  }
  if (pattern && !pattern.test(value)) return fail(path, "has an invalid format");
  return value;
}

function oneOf<T extends string>(value: unknown, path: string, choices: readonly T[]): T {
  if (typeof value !== "string" || !choices.includes(value as T)) {
    return fail(path, `must be one of ${choices.join(", ")}`);
  }
  return value as T;
}

function boolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") return fail(path, "must be a boolean");
  return value;
}

function boundedInteger(value: unknown, path: string, minimum: number, maximum: number): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum || (value as number) > maximum) {
    return fail(path, `must be a safe integer from ${minimum} through ${maximum}`);
  }
  return value as number;
}

function exactVersion(value: unknown, path: string): string {
  return text(value, path, exactVersionPattern, 128);
}

/** Normalize a workspace-relative path without resolving or reading it. */
export function normalizeMiniappRelativePath(value: unknown, path: string): string {
  const candidate = text(value, path, undefined, 1024).normalize("NFC");
  if (candidate === ".") return candidate;
  if (candidate.startsWith("/") || candidate.startsWith("\\") || /^[A-Za-z]:/u.test(candidate)) {
    return fail(path, "must be relative");
  }
  if (candidate.includes("\\")) return fail(path, "must use forward slashes");
  const segments = candidate.split("/");
  if (segments.some(segment => segment.length === 0 || segment === "." || segment === "..")) {
    return fail(path, "must be normalized and must not contain . or .. segments");
  }
  for (const segment of segments) {
    let decoded: string;
    try {
      decoded = decodeURIComponent(segment);
    } catch {
      return fail(path, "contains invalid percent encoding");
    }
    if (decoded === "." || decoded === ".." || decoded.includes("/") || decoded.includes("\\")) {
      return fail(path, "contains encoded path traversal");
    }
  }
  return segments.join("/");
}

export function validateMiniappInventoryLimits(value: unknown, path = "limits"): MiniappInventoryLimits {
  const candidate = object(value, path);
  exactKeys(candidate, path, ["maxFileCount", "maxFileBytes", "maxTotalBytes"]);
  return {
    maxFileCount: boundedInteger(
      candidate.maxFileCount,
      `${path}.maxFileCount`,
      1,
      MINIAPP_INVENTORY_HARD_LIMITS.maxFileCount,
    ),
    maxFileBytes: boundedInteger(
      candidate.maxFileBytes,
      `${path}.maxFileBytes`,
      1,
      MINIAPP_INVENTORY_HARD_LIMITS.maxFileBytes,
    ),
    maxTotalBytes: boundedInteger(
      candidate.maxTotalBytes,
      `${path}.maxTotalBytes`,
      1,
      MINIAPP_INVENTORY_HARD_LIMITS.maxTotalBytes,
    ),
  };
}

function source(value: unknown, path: string): MiniappConversionSource {
  const candidate = object(value, path);
  exactKeys(candidate, path, [
    "root",
    "revision",
    "snapshotDigest",
    "sourceLabel",
    "frameworkVersion",
    "languageVersion",
    "runtimeVersion",
    "buildToolVersion",
  ]);
  return {
    root: normalizeMiniappRelativePath(candidate.root, `${path}.root`),
    revision: text(candidate.revision, `${path}.revision`, revisionPattern, 71),
    snapshotDigest: text(candidate.snapshotDigest, `${path}.snapshotDigest`, sha256Pattern, 71),
    sourceLabel: oneOf<MiniappSourceLabel>(candidate.sourceLabel, `${path}.sourceLabel`, MINIAPP_SOURCE_LABELS),
    frameworkVersion: exactVersion(candidate.frameworkVersion, `${path}.frameworkVersion`),
    languageVersion: exactVersion(candidate.languageVersion, `${path}.languageVersion`),
    runtimeVersion: exactVersion(candidate.runtimeVersion, `${path}.runtimeVersion`),
    buildToolVersion: exactVersion(candidate.buildToolVersion, `${path}.buildToolVersion`),
  };
}

function target(value: unknown, path: string): MiniappConversionTarget {
  const candidate = object(value, path);
  exactKeys(candidate, path, ["platform", "platformVersion", "toolchainVersion"]);
  return {
    platform: oneOf<MiniappPlatform>(candidate.platform, `${path}.platform`, MINIAPP_PLATFORMS),
    platformVersion: exactVersion(candidate.platformVersion, `${path}.platformVersion`),
    toolchainVersion: exactVersion(candidate.toolchainVersion, `${path}.toolchainVersion`),
  };
}

function secretReference(value: unknown, path: string): MiniappSecretReference {
  const candidate = object(value, path);
  exactKeys(candidate, path, ["name", "reference"]);
  return {
    name: text(candidate.name, `${path}.name`, scopedIdPattern, 128),
    reference: text(candidate.reference, `${path}.reference`, secretReferencePattern, 520),
  };
}

function policy(value: unknown, path: string): MiniappConversionPolicy {
  const candidate = object(value, path);
  exactKeys(candidate, path, [
    "priority",
    "webviewFallback",
    "fullPageCanvasFallback",
    "unsupportedPolicy",
    "limits",
    "secretReferences",
  ]);
  if (!Array.isArray(candidate.secretReferences) || candidate.secretReferences.length > 64) {
    return fail(`${path}.secretReferences`, "must be an array with at most 64 entries");
  }
  const secretReferences = candidate.secretReferences.map((item, index) =>
    secretReference(item, `${path}.secretReferences[${index}]`));
  const names = new Set<string>();
  for (const item of secretReferences) {
    if (names.has(item.name)) fail(`${path}.secretReferences`, `contains duplicate name ${item.name}`);
    names.add(item.name);
  }
  return {
    priority: oneOf(candidate.priority, `${path}.priority`, [
      "fidelity", "maintainability", "platform-native", "code-sharing", "balanced",
    ] as const),
    webviewFallback: oneOf(candidate.webviewFallback, `${path}.webviewFallback`, [
      "deny", "approval-required", "allow",
    ] as const),
    fullPageCanvasFallback: oneOf(candidate.fullPageCanvasFallback, `${path}.fullPageCanvasFallback`, [
      "deny", "approval-required",
    ] as const),
    unsupportedPolicy: oneOf(candidate.unsupportedPolicy, `${path}.unsupportedPolicy`, [
      "block", "report-and-continue-noncritical", "ask-decision",
    ] as const),
    limits: validateMiniappInventoryLimits(candidate.limits, `${path}.limits`),
    secretReferences,
  };
}

function evidence(value: unknown, path: string): MiniappEvidenceReference {
  const candidate = object(value, path);
  exactKeys(candidate, path, [
    "role", "uri", "digest", "state", "executor", "verifier", "synthetic", "byteCount",
  ]);
  return {
    role: text(candidate.role, `${path}.role`, scopedIdPattern, 128),
    uri: text(candidate.uri, `${path}.uri`, evidenceUriPattern, 1024),
    digest: text(candidate.digest, `${path}.digest`, sha256Pattern, 71),
    state: oneOf<MiniappEvidenceState>(candidate.state, `${path}.state`, MINIAPP_EVIDENCE_STATES),
    executor: text(candidate.executor, `${path}.executor`, scopedIdPattern, 128),
    verifier: text(candidate.verifier, `${path}.verifier`, scopedIdPattern, 128),
    synthetic: boolean(candidate.synthetic, `${path}.synthetic`),
    byteCount: boundedInteger(candidate.byteCount, `${path}.byteCount`, 0, Number.MAX_SAFE_INTEGER),
  };
}

function compareText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

export function normalizeMiniappConversionRequest(request: MiniappConversionRequest): MiniappConversionRequest {
  const platformIndex = new Map(MINIAPP_PLATFORMS.map((platform, index) => [platform, index]));
  return {
    schemaVersion: "1.0",
    requestId: request.requestId,
    tenantId: request.tenantId,
    source: { ...request.source },
    targets: [...request.targets]
      .map(item => ({ ...item }))
      .sort((left, right) => (platformIndex.get(left.platform) ?? 99) - (platformIndex.get(right.platform) ?? 99)),
    policy: {
      ...request.policy,
      limits: { ...request.policy.limits },
      secretReferences: [...request.policy.secretReferences]
        .map(item => ({ ...item }))
        .sort((left, right) => compareText(left.name, right.name)),
    },
    evidence: [...request.evidence]
      .map(item => ({ ...item }))
      .sort((left, right) => compareText(
        `${left.role}\u0000${left.uri}\u0000${left.digest}`,
        `${right.role}\u0000${right.uri}\u0000${right.digest}`,
      )),
  };
}

export function validateMiniappConversionRequest(value: unknown): MiniappConversionRequest {
  const candidate = object(value, "request");
  exactKeys(candidate, "request", [
    "schemaVersion", "requestId", "tenantId", "source", "targets", "policy", "evidence",
  ]);
  if (candidate.schemaVersion !== "1.0") fail("request.schemaVersion", "must equal 1.0");
  if (!Array.isArray(candidate.targets) || candidate.targets.length < 1 || candidate.targets.length > 4) {
    fail("request.targets", "must contain from 1 through 4 targets");
  }
  const targets = candidate.targets.map((item, index) => target(item, `request.targets[${index}]`));
  const platforms = new Set<MiniappPlatform>();
  for (const item of targets) {
    if (platforms.has(item.platform)) fail("request.targets", `contains duplicate platform ${item.platform}`);
    platforms.add(item.platform);
  }
  if (!Array.isArray(candidate.evidence) || candidate.evidence.length < 1 || candidate.evidence.length > 256) {
    fail("request.evidence", "must contain from 1 through 256 evidence references");
  }
  const parsed: MiniappConversionRequest = {
    schemaVersion: "1.0",
    requestId: text(candidate.requestId, "request.requestId", requestIdPattern, 69),
    tenantId: text(candidate.tenantId, "request.tenantId", scopedIdPattern, 128),
    source: source(candidate.source, "request.source"),
    targets,
    policy: policy(candidate.policy, "request.policy"),
    evidence: candidate.evidence.map((item, index) => evidence(item, `request.evidence[${index}]`)),
  };
  return normalizeMiniappConversionRequest(parsed);
}

function canonicalValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (value && typeof value === "object") {
    const candidate = value as Readonly<Record<string, unknown>>;
    return Object.fromEntries(Object.keys(candidate).sort(compareText).map(key => [key, canonicalValue(candidate[key])]));
  }
  return value;
}

export function canonicalizeMiniappConversionRequest(request: MiniappConversionRequest): string {
  return JSON.stringify(canonicalValue(validateMiniappConversionRequest(request)));
}

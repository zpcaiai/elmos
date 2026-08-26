import { createHash } from "node:crypto";
import { types as nodeUtilTypes } from "node:util";

import type { MiniappPlatform } from "./miniapp-types.js";

export type MiniappLocalCandidateState =
  | "PASSED_LOCAL"
  | "FAILED_LOCAL"
  | "BLOCKED"
  | "NOT_RUN";

export interface MiniappValidationTraceEvent {
  readonly sequence: number;
  readonly type: string;
  readonly value?: MiniappValidationJson;
  readonly metadata: Readonly<Record<string, MiniappValidationJson>>;
}

export type MiniappValidationJson =
  | null
  | boolean
  | number
  | string
  | readonly MiniappValidationJson[]
  | { readonly [key: string]: MiniappValidationJson };

export interface MiniappLocalDifferentialComparison {
  readonly flowId: string;
  readonly platform: MiniappPlatform;
  readonly verdict: "passed" | "failed";
  readonly sourceTrace: readonly MiniappValidationTraceEvent[];
  readonly targetTrace: readonly MiniappValidationTraceEvent[];
  readonly sourceTraceDigest: string;
  readonly targetTraceDigest: string;
  readonly targetProjectDigest: string;
  readonly sourceExecutor: string;
  readonly targetExecutor: string;
  readonly verifier: string;
  readonly attributionState: "SELF_ASSERTED_UNVERIFIED";
  readonly diffs: readonly {
    readonly kind: "event-count" | "event-type" | "event-value" | "event-metadata";
    readonly severity: "high";
    readonly message: string;
    readonly sequence?: number;
  }[];
}

export interface MiniappLocalDifferentialEvaluation {
  readonly state: MiniappLocalCandidateState;
  readonly authoritativeExecution: "NOT_RUN";
  readonly captureTrust: "UNATTESTED_LOCAL_INPUT" | "NOT_RUN";
  readonly semanticParity: "PASSED_LOCAL" | "FAILED_LOCAL" | "NOT_ESTABLISHED";
  readonly normalizerVersion: string | "NOT_RUN";
  readonly ignoredMetadataKeys: readonly string[];
  readonly testPlanId: string | "NOT_RUN";
  readonly testPlanDigest: string | "NOT_RUN";
  readonly criticalFlowPassRate: number;
  readonly expectedFlowCount: number;
  readonly observedFlowCount: number;
  readonly comparisons: readonly MiniappLocalDifferentialComparison[];
  readonly findings: readonly string[];
}

export interface MiniappLocalVisualComparison {
  readonly comparisonId: string;
  readonly platform: MiniappPlatform;
  readonly width: number;
  readonly height: number;
  readonly sourceDigest: string;
  readonly targetDigest: string;
  readonly targetProjectDigest: string;
  readonly sourceExecutor: string;
  readonly targetExecutor: string;
  readonly verifier: string;
  readonly attributionState: "SELF_ASSERTED_UNVERIFIED";
  readonly similarity: number;
  readonly threshold: number;
  readonly maskedPixels: number;
  readonly comparedPixels: number;
  readonly maskAudit: readonly {
    readonly x: number;
    readonly y: number;
    readonly width: number;
    readonly height: number;
    readonly reason: string;
  }[];
  readonly verdict: "passed" | "failed" | "blocked";
}

export interface MiniappLocalVisualEvaluation {
  readonly state: MiniappLocalCandidateState;
  readonly authoritativeExecution: "NOT_RUN";
  readonly captureTrust: "UNATTESTED_LOCAL_INPUT" | "NOT_RUN";
  readonly sourceScreenshots: "NOT_RUN";
  readonly targetScreenshots: "NOT_RUN";
  readonly rawCaptureReplay: "BLOCKED_RAW_CAPTURE_NOT_MATERIALIZED" | "NOT_RUN";
  readonly requestedSimilarity: number;
  readonly functionalPrerequisite: MiniappLocalCandidateState;
  readonly comparisons: readonly MiniappLocalVisualComparison[];
  readonly reason: string;
}

export interface MiniappLocalRepairAction {
  readonly finding: string;
  readonly owner: "ir" | "mapping" | "adapter" | "generated-code";
  readonly strategy: "ir" | "mapping-rule" | "platform-adapter" | "generator-template";
  readonly patchDigest: string;
  readonly patchScope: readonly string[];
  readonly targetedTests: readonly string[];
  readonly affectedGates: readonly string[];
  readonly risk: "low" | "medium" | "high";
  readonly status: "PROPOSED" | "BLOCKED";
  readonly stopReason?: string;
}

export interface MiniappLocalRepairEvaluation {
  readonly state: "PLAN_READY" | "BLOCKED" | "NOT_RUN";
  readonly maximumIterations: number;
  readonly appliedIterations: 0;
  readonly actions: readonly MiniappLocalRepairAction[];
  readonly rollback: "NO_MUTATION_PERFORMED";
  readonly executionEvidence: "NOT_RUN";
  readonly stopReasons: readonly string[];
}

export interface MiniappLocalDeliveryPlan {
  readonly state: "PLANNED_LOCAL";
  readonly officialExecution: "NOT_RUN";
  readonly idempotencyKey: string;
  readonly profiles: readonly {
    readonly platform: MiniappPlatform;
    readonly toolchainVersion: string;
    readonly projectDigest: string;
    readonly stages: readonly {
      readonly stage: "lint" | "schema" | "build" | "preview" | "upload" | "review" | "release";
      readonly state: "NOT_RUN";
      readonly sideEffect: boolean;
      readonly approvalRequired: boolean;
    }[];
  }[];
  readonly credentials: "SECRET_REFERENCES_ONLY";
}

export interface MiniappLocalValidationEvaluation {
  readonly schemaVersion: "1.0";
  readonly inputDigest: string | "NOT_RUN";
  readonly differential: MiniappLocalDifferentialEvaluation;
  readonly visual: MiniappLocalVisualEvaluation;
  readonly repair: MiniappLocalRepairEvaluation;
  readonly deliveryPlan: MiniappLocalDeliveryPlan;
  readonly evidenceBoundary: {
    readonly localCandidate: "SELF_ATTESTED" | "NOT_RUN";
    readonly officialSourceRuntime: "NOT_RUN";
    readonly officialTargetRuntime: "NOT_RUN";
    readonly officialDeviceVisual: "NOT_RUN";
    readonly upload: "NOT_RUN";
    readonly review: "NOT_RUN";
    readonly release: "NOT_RUN";
    readonly certification: "NOT_CERTIFIED";
  };
  readonly deterministicDigest: string;
}

export interface MiniappLocalValidationContext {
  readonly targets: readonly {
    readonly platform: MiniappPlatform;
    readonly toolchainVersion: string;
    readonly projectDigest: string;
  }[];
  readonly requestedSimilarity: number;
  readonly criticalFlowPassRate: number;
  readonly maximumRepairIterations: number;
  readonly repairFindings: readonly {
    readonly finding: string;
    readonly owner: "ir" | "mapping" | "adapter" | "generated-code";
    readonly approvalRequired: boolean;
  }[];
}

const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/u;
const DIGEST = /^sha256:[a-f0-9]{64}$/u;
const NORMALIZER_KEY_ALLOWLIST = new Set([
  "captureDurationMs",
  "platformTraceId",
  "runtimeTimestamp",
]);
const PATCH_ROOTS = new Set(["ir", "mappings", "adapters", "generators"]);
const MAX_TRACE_EVENTS = 4096;
const MAX_TRACE_BYTES = 4 * 1024 * 1024;
const MAX_VISUAL_PIXELS = 1024 * 1024;
const MAX_VISUAL_BYTES = 16 * 1024 * 1024;

export const MINIAPP_LOCAL_VALIDATION_HARD_LIMITS = Object.freeze({
  maxCanonicalBytes: 32 * 1024 * 1024,
  maxJsonNodes: 262_144,
});

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value)
    && typeof value === "object"
    && !Array.isArray(value)
    && !nodeUtilTypes.isProxy(value)
    && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
}

function exactKeys(
  value: Record<string, unknown>,
  allowed: readonly string[],
  required: readonly string[],
  path: string,
): void {
  for (const key of required) {
    if (!Object.hasOwn(value, key)) throw new Error(`${path}.${key} is required`);
  }
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) throw new Error(`${path}.${key} is not allowed`);
  }
}

function object(value: unknown, path: string): Record<string, unknown> {
  if (!isObject(value)) throw new Error(`${path} must be an object`);
  return value;
}

function string(
  value: unknown,
  path: string,
  pattern: RegExp = IDENTIFIER,
  maximum = 128,
): string {
  if (typeof value !== "string" || value.length === 0 || value.length > maximum || !pattern.test(value)) {
    throw new Error(`${path} is invalid`);
  }
  return value;
}

function integer(value: unknown, path: string, minimum: number, maximum: number): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum || (value as number) > maximum) {
    throw new Error(`${path} must be an integer from ${minimum} through ${maximum}`);
  }
  return value as number;
}

function number(value: unknown, path: string, minimum: number, maximum: number): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < minimum || value > maximum) {
    throw new Error(`${path} must be a finite number from ${minimum} through ${maximum}`);
  }
  return value;
}

function digest(value: unknown, path: string): string {
  return string(value, path, DIGEST, 71);
}

function jsonValue(value: unknown, path: string, depth = 0): MiniappValidationJson {
  return snapshotDataOnlyJson(value, path, undefined, depth);
}

/**
 * Canonical keys retain their exact Unicode spelling and are ordered by UTF-16
 * code units. NFC and NFD spellings therefore remain distinct identities; no
 * locale- or ICU-dependent collation or implicit normalization is permitted.
 */
export function compareMiniappCanonicalKeys(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

export function canonicalizeMiniappDeterministicJson(value: unknown): string {
  // Always snapshot through the data-only boundary first.  In particular, a
  // caller must not be able to make canonicalization invoke a getter, Proxy
  // trap, sparse-array lookup, or custom prototype method.
  return canonicalizeMiniappSnapshot(snapshotDataOnlyJson(value, "canonical", undefined));
}

interface MiniappJsonBudget {
  bytes: number;
  nodes: number;
}

function addBudgetBytes(budget: MiniappJsonBudget | undefined, bytes: number, path: string): void {
  if (!budget) return;
  budget.bytes += bytes;
  if (!Number.isSafeInteger(budget.bytes)
    || budget.bytes > MINIAPP_LOCAL_VALIDATION_HARD_LIMITS.maxCanonicalBytes) {
    throw new Error(
      `${path} exceeds the aggregate localValidation canonical byte budget of ${MINIAPP_LOCAL_VALIDATION_HARD_LIMITS.maxCanonicalBytes}`,
    );
  }
}

function addBudgetNodes(budget: MiniappJsonBudget | undefined, nodes: number, path: string): void {
  if (!budget) return;
  budget.nodes += nodes;
  if (!Number.isSafeInteger(budget.nodes)
    || budget.nodes > MINIAPP_LOCAL_VALIDATION_HARD_LIMITS.maxJsonNodes) {
    throw new Error(
      `${path} exceeds the aggregate localValidation JSON node budget of ${MINIAPP_LOCAL_VALIDATION_HARD_LIMITS.maxJsonNodes}`,
    );
  }
}

function addCanonicalStringBudget(
  value: string,
  budget: MiniappJsonBudget | undefined,
  path: string,
): void {
  if (!budget) return;
  const rawBytes = Buffer.byteLength(value, "utf8");
  if (rawBytes + 2 > MINIAPP_LOCAL_VALIDATION_HARD_LIMITS.maxCanonicalBytes - budget.bytes) {
    addBudgetBytes(budget, rawBytes + 2, path);
    return;
  }
  if (!/["\\\u0000-\u001f\ud800-\udfff]/u.test(value)) {
    addBudgetBytes(budget, rawBytes + 2, path);
    return;
  }
  let bytes = 2;
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code === 0x22 || code === 0x5c
      || code === 0x08 || code === 0x09 || code === 0x0a || code === 0x0c || code === 0x0d) {
      bytes += 2;
    } else if (code <= 0x1f) {
      bytes += 6;
    } else if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        bytes += 4;
        index += 1;
      } else {
        bytes += 6;
      }
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      bytes += 6;
    } else if (code <= 0x7f) {
      bytes += 1;
    } else if (code <= 0x7ff) {
      bytes += 2;
    } else {
      bytes += 3;
    }
    if (bytes > MINIAPP_LOCAL_VALIDATION_HARD_LIMITS.maxCanonicalBytes - budget.bytes) {
      addBudgetBytes(budget, bytes, path);
      return;
    }
  }
  addBudgetBytes(budget, bytes, path);
}

function snapshotDataOnlyJson(
  value: unknown,
  path: string,
  budget: MiniappJsonBudget | undefined,
  depth = 0,
): MiniappValidationJson {
  if (depth > 32) throw new Error(`${path} exceeds the JSON depth limit`);
  addBudgetNodes(budget, 1, path);
  if (value === null) {
    addBudgetBytes(budget, 4, path);
    return null;
  }
  if (typeof value === "boolean") {
    addBudgetBytes(budget, value ? 4 : 5, path);
    return value;
  }
  if (typeof value === "string") {
    addCanonicalStringBudget(value, budget, path);
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error(`${path} must not contain a non-finite number`);
    addBudgetBytes(budget, JSON.stringify(value).length, path);
    return value;
  }
  if (typeof value === "object" && value !== null && nodeUtilTypes.isProxy(value)) {
    throw new Error(`${path} must not be a Proxy`);
  }
  if (Array.isArray(value)) {
    if (value.length > 4096) throw new Error(`${path} exceeds the array length limit`);
    if (Object.getOwnPropertySymbols(value).length > 0) throw new Error(`${path} must not contain symbol properties`);
    const descriptors = Object.getOwnPropertyDescriptors(value);
    for (const key of Object.keys(descriptors)) {
      if (key === "length") continue;
      const index = Number(key);
      if (!Number.isSafeInteger(index) || index < 0 || index >= value.length || String(index) !== key) {
        throw new Error(`${path} must not contain non-index array properties`);
      }
    }
    addBudgetBytes(budget, 2 + Math.max(0, value.length - 1), path);
    const output: MiniappValidationJson[] = [];
    for (let index = 0; index < value.length; index += 1) {
      const descriptor = descriptors[String(index)];
      if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
        throw new Error(`${path}[${index}] must be a dense enumerable data property`);
      }
      output.push(snapshotDataOnlyJson(descriptor.value, `${path}[${index}]`, budget, depth + 1));
    }
    return output;
  }
  if (isObject(value)) {
    if (Object.getOwnPropertySymbols(value).length > 0) throw new Error(`${path} must not contain symbol properties`);
    const descriptors = Object.getOwnPropertyDescriptors(value);
    const keys = Object.keys(descriptors);
    if (keys.length > 4096) throw new Error(`${path} exceeds the object key limit`);
    addBudgetNodes(budget, keys.length, path);
    addBudgetBytes(budget, 2 + Math.max(0, keys.length - 1) + keys.length, path);
    const output = Object.create(null) as Record<string, MiniappValidationJson>;
    for (const key of keys) {
      if (key.length === 0 || key.length > 256 || /[\u0000-\u001f\u007f]/u.test(key)) {
        throw new Error(`${path} contains an invalid key`);
      }
      const descriptor = descriptors[key]!;
      if (!("value" in descriptor) || !descriptor.enumerable) {
        throw new Error(`${path}.${key} must be an enumerable data property; accessors are forbidden`);
      }
      addCanonicalStringBudget(key, budget, `${path} key`);
      output[key] = snapshotDataOnlyJson(descriptor.value, `${path}.${key}`, budget, depth + 1);
    }
    return output;
  }
  throw new Error(`${path} must contain JSON values only`);
}

function canonicalizeMiniappSnapshot(value: MiniappValidationJson): string {
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalizeMiniappSnapshot(item)).join(",")}]`;
  }
  return `{${Object.entries(value)
    .sort(([left], [right]) => compareMiniappCanonicalKeys(left, right))
    .map(([key, item]) => `${JSON.stringify(key)}:${canonicalizeMiniappSnapshot(item)}`)
    .join(",")}}`;
}

function snapshotLocalValidation(value: unknown): MiniappValidationJson {
  return snapshotDataOnlyJson(value, "localValidation", { bytes: 0, nodes: 0 });
}

function digestValidatedMiniappValidationPayload(value: MiniappValidationJson): string {
  return `sha256:${createHash("sha256").update(canonicalizeMiniappSnapshot(value), "utf8").digest("hex")}`;
}

export function digestMiniappValidationPayload(value: unknown): string {
  const validated = jsonValue(value, "payload");
  return digestValidatedMiniappValidationPayload(validated);
}

export function digestMiniappValidationBytes(value: Uint8Array): string {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

function platform(value: unknown, path: string): MiniappPlatform {
  if (value !== "wechat" && value !== "alipay" && value !== "douyin" && value !== "xiaohongshu") {
    throw new Error(`${path} must be a MiniApp platform`);
  }
  return value;
}

function traceEvent(value: unknown, path: string, expectedSequence: number): MiniappValidationTraceEvent {
  const candidate = object(value, path);
  exactKeys(candidate, ["sequence", "type", "value", "metadata"], ["sequence", "type"], path);
  const sequence = integer(candidate.sequence, `${path}.sequence`, 0, MAX_TRACE_EVENTS - 1);
  if (sequence !== expectedSequence) throw new Error(`${path}.sequence must be contiguous from zero`);
  const metadataCandidate = candidate.metadata === undefined ? {} : object(candidate.metadata, `${path}.metadata`);
  const metadata = Object.fromEntries(Object.entries(metadataCandidate).map(([key, item]) => [
    string(key, `${path}.metadata key`, /^[A-Za-z][A-Za-z0-9._-]{0,127}$/u),
    jsonValue(item, `${path}.metadata.${key}`),
  ]));
  const base = {
    sequence,
    type: string(candidate.type, `${path}.type`, /^[A-Za-z][A-Za-z0-9._:-]{0,127}$/u),
    metadata,
  };
  return candidate.value === undefined
    ? base
    : { ...base, value: jsonValue(candidate.value, `${path}.value`) };
}

function trace(value: unknown, path: string): readonly MiniappValidationTraceEvent[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > MAX_TRACE_EVENTS) {
    throw new Error(`${path} must contain 1 through ${MAX_TRACE_EVENTS} events`);
  }
  const result = value.map((event, index) => traceEvent(event, `${path}[${index}]`, index));
  if (Buffer.byteLength(canonicalizeMiniappDeterministicJson(jsonValue(result, path)), "utf8") > MAX_TRACE_BYTES) {
    throw new Error(`${path} exceeds ${MAX_TRACE_BYTES} canonical bytes`);
  }
  return result;
}

function normalizedEvent(
  event: MiniappValidationTraceEvent,
  ignoredMetadataKeys: ReadonlySet<string>,
): MiniappValidationTraceEvent {
  const metadata = Object.fromEntries(Object.entries(event.metadata)
    .filter(([key]) => !ignoredMetadataKeys.has(key))
    .sort(([left], [right]) => compareMiniappCanonicalKeys(left, right)));
  const base = { sequence: event.sequence, type: event.type, metadata };
  return event.value === undefined ? base : { ...base, value: event.value };
}

function compareTraces(
  source: readonly MiniappValidationTraceEvent[],
  target: readonly MiniappValidationTraceEvent[],
  ignoredMetadataKeys: ReadonlySet<string>,
): MiniappLocalDifferentialComparison["diffs"] {
  const diffs: Array<MiniappLocalDifferentialComparison["diffs"][number]> = [];
  if (source.length !== target.length) {
    diffs.push({ kind: "event-count", severity: "high", message: `source=${source.length} target=${target.length}` });
  }
  for (let index = 0; index < Math.min(source.length, target.length); index += 1) {
    const left = normalizedEvent(source[index]!, ignoredMetadataKeys);
    const right = normalizedEvent(target[index]!, ignoredMetadataKeys);
    if (left.type !== right.type) {
      diffs.push({ kind: "event-type", severity: "high", message: `${left.type} != ${right.type}`, sequence: index });
    }
    const leftHasValue = Object.hasOwn(left, "value");
    const rightHasValue = Object.hasOwn(right, "value");
    if (leftHasValue !== rightHasValue) {
      diffs.push({ kind: "event-value", severity: "high", message: "event value presence differs", sequence: index });
    } else if (leftHasValue && canonicalizeMiniappDeterministicJson(jsonValue(left.value, `source[${index}].value`))
      !== canonicalizeMiniappDeterministicJson(jsonValue(right.value, `target[${index}].value`))) {
      diffs.push({ kind: "event-value", severity: "high", message: "event values differ", sequence: index });
    }
    if (canonicalizeMiniappDeterministicJson(jsonValue(left.metadata, `source[${index}].metadata`))
      !== canonicalizeMiniappDeterministicJson(jsonValue(right.metadata, `target[${index}].metadata`))) {
      diffs.push({ kind: "event-metadata", severity: "high", message: "event metadata differs", sequence: index });
    }
  }
  return diffs;
}

function evaluateDifferential(
  value: unknown,
  context: MiniappLocalValidationContext,
): MiniappLocalDifferentialEvaluation {
  if (value === undefined) {
    return {
      state: "NOT_RUN",
      authoritativeExecution: "NOT_RUN",
      captureTrust: "NOT_RUN",
      semanticParity: "NOT_ESTABLISHED",
      normalizerVersion: "NOT_RUN",
      ignoredMetadataKeys: [],
      testPlanId: "NOT_RUN",
      testPlanDigest: "NOT_RUN",
      criticalFlowPassRate: context.criticalFlowPassRate,
      expectedFlowCount: 0,
      observedFlowCount: 0,
      comparisons: [],
      findings: ["LOCAL_DIFFERENTIAL_INPUT_NOT_PROVIDED"],
    };
  }
  const candidate = object(value, "localValidation.differential");
  exactKeys(candidate, ["normalizerVersion", "ignoredMetadataKeys", "testPlan", "flows"], ["normalizerVersion", "ignoredMetadataKeys", "testPlan", "flows"], "localValidation.differential");
  const normalizerVersion = string(candidate.normalizerVersion, "localValidation.differential.normalizerVersion", /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/u, 64);
  if (!Array.isArray(candidate.ignoredMetadataKeys) || candidate.ignoredMetadataKeys.length > NORMALIZER_KEY_ALLOWLIST.size) {
    throw new Error("localValidation.differential.ignoredMetadataKeys is invalid");
  }
  const ignoredMetadataKeys = candidate.ignoredMetadataKeys.map((item, index) => {
    const key = string(item, `localValidation.differential.ignoredMetadataKeys[${index}]`, /^[A-Za-z][A-Za-z0-9]{0,63}$/u, 64);
    if (!NORMALIZER_KEY_ALLOWLIST.has(key)) throw new Error(`metadata normalizer key is not allowlisted: ${key}`);
    return key;
  });
  if (new Set(ignoredMetadataKeys).size !== ignoredMetadataKeys.length) throw new Error("ignored metadata keys must be unique");
  const testPlan = object(candidate.testPlan, "localValidation.differential.testPlan");
  exactKeys(testPlan, ["testPlanId", "criticalFlowPassRate", "expectedFlows", "digest"], ["testPlanId", "criticalFlowPassRate", "expectedFlows", "digest"], "localValidation.differential.testPlan");
  const testPlanId = string(testPlan.testPlanId, "localValidation.differential.testPlan.testPlanId");
  const criticalFlowPassRate = number(testPlan.criticalFlowPassRate, "localValidation.differential.testPlan.criticalFlowPassRate", 0, 1);
  if (criticalFlowPassRate !== context.criticalFlowPassRate) {
    throw new Error("localValidation differential test plan does not bind the requested critical flow pass rate");
  }
  if (!Array.isArray(testPlan.expectedFlows) || testPlan.expectedFlows.length === 0 || testPlan.expectedFlows.length > 128) {
    throw new Error("localValidation.differential.testPlan.expectedFlows must contain 1 through 128 flows");
  }
  const expectedFlowKeys = new Set<string>();
  const expectedFlows = testPlan.expectedFlows.map((expectedValue, index) => {
    const path = `localValidation.differential.testPlan.expectedFlows[${index}]`;
    const expected = object(expectedValue, path);
    exactKeys(expected, ["flowId", "platform"], ["flowId", "platform"], path);
    const expectedFlow = {
      flowId: string(expected.flowId, `${path}.flowId`),
      platform: platform(expected.platform, `${path}.platform`),
    };
    if (!context.targets.some(target => target.platform === expectedFlow.platform)) {
      throw new Error(`${path}.platform is not requested`);
    }
    const key = `${expectedFlow.platform}:${expectedFlow.flowId}`;
    if (expectedFlowKeys.has(key)) throw new Error(`${path} duplicates ${key}`);
    expectedFlowKeys.add(key);
    return expectedFlow;
  });
  const testPlanDigest = digest(testPlan.digest, "localValidation.differential.testPlan.digest");
  if (testPlanDigest !== digestMiniappValidationPayload({ testPlanId, criticalFlowPassRate, expectedFlows })) {
    throw new Error("localValidation.differential.testPlan.digest mismatch");
  }
  if (!Array.isArray(candidate.flows) || candidate.flows.length === 0 || candidate.flows.length > 64) {
    throw new Error("localValidation.differential.flows must contain 1 through 64 flows");
  }
  const targetMap = new Map(context.targets.map((target) => [target.platform, target]));
  const flowKeys = new Set<string>();
  const comparisons = candidate.flows.map((flowValue, index): MiniappLocalDifferentialComparison => {
    const path = `localValidation.differential.flows[${index}]`;
    const flow = object(flowValue, path);
    exactKeys(flow, ["flowId", "platform", "sourceTrace", "targetTrace", "sourceTraceDigest", "targetTraceDigest", "targetProjectDigest", "sourceExecutor", "targetExecutor", "verifier"], ["flowId", "platform", "sourceTrace", "targetTrace", "sourceTraceDigest", "targetTraceDigest", "targetProjectDigest", "sourceExecutor", "targetExecutor", "verifier"], path);
    const flowId = string(flow.flowId, `${path}.flowId`);
    const targetPlatform = platform(flow.platform, `${path}.platform`);
    const key = `${targetPlatform}:${flowId}`;
    if (flowKeys.has(key)) throw new Error(`${path} duplicates ${key}`);
    flowKeys.add(key);
    const requestedTarget = targetMap.get(targetPlatform);
    if (!requestedTarget) throw new Error(`${path}.platform is not requested`);
    const targetProjectDigest = digest(flow.targetProjectDigest, `${path}.targetProjectDigest`);
    if (targetProjectDigest !== requestedTarget.projectDigest) throw new Error(`${path}.targetProjectDigest does not bind the generated project`);
    const sourceExecutor = string(flow.sourceExecutor, `${path}.sourceExecutor`);
    const targetExecutor = string(flow.targetExecutor, `${path}.targetExecutor`);
    const verifier = string(flow.verifier, `${path}.verifier`);
    if (new Set([sourceExecutor, targetExecutor, verifier]).size !== 3) {
      throw new Error(`${path} requires distinct source executor, target executor and verifier identities`);
    }
    const sourceTrace = trace(flow.sourceTrace, `${path}.sourceTrace`);
    const targetTrace = trace(flow.targetTrace, `${path}.targetTrace`);
    const sourceTraceDigest = digest(flow.sourceTraceDigest, `${path}.sourceTraceDigest`);
    const targetTraceDigest = digest(flow.targetTraceDigest, `${path}.targetTraceDigest`);
    if (sourceTraceDigest !== digestMiniappValidationPayload(sourceTrace)) throw new Error(`${path}.sourceTraceDigest mismatch`);
    if (targetTraceDigest !== digestMiniappValidationPayload(targetTrace)) throw new Error(`${path}.targetTraceDigest mismatch`);
    const diffs = compareTraces(sourceTrace, targetTrace, new Set(ignoredMetadataKeys));
    return {
      flowId,
      platform: targetPlatform,
      verdict: diffs.length === 0 ? "passed" : "failed",
      sourceTrace,
      targetTrace,
      sourceTraceDigest,
      targetTraceDigest,
      targetProjectDigest,
      sourceExecutor,
      targetExecutor,
      verifier,
      attributionState: "SELF_ASSERTED_UNVERIFIED",
      diffs,
    };
  });
  const missingPlatforms = context.targets
    .filter((target) => !expectedFlows.some((expected) => expected.platform === target.platform))
    .map((target) => target.platform);
  const missingExpectedFlows = expectedFlows.filter(expected => !comparisons.some(
    comparison => comparison.platform === expected.platform && comparison.flowId === expected.flowId,
  ));
  const failed = comparisons.filter((comparison) => comparison.verdict === "failed");
  const passedExpectedFlows = expectedFlows.filter(expected => comparisons.some(
    comparison => comparison.platform === expected.platform
      && comparison.flowId === expected.flowId
      && comparison.verdict === "passed",
  ));
  const observedPassRate = passedExpectedFlows.length / expectedFlows.length;
  const state = missingPlatforms.length > 0 || missingExpectedFlows.length > 0
    ? "BLOCKED"
    : failed.length > 0 || observedPassRate < criticalFlowPassRate
      ? "FAILED_LOCAL"
      : "PASSED_LOCAL";
  return {
    state,
    authoritativeExecution: "NOT_RUN",
    captureTrust: "UNATTESTED_LOCAL_INPUT",
    semanticParity: state === "PASSED_LOCAL" ? "PASSED_LOCAL" : state === "FAILED_LOCAL" ? "FAILED_LOCAL" : "NOT_ESTABLISHED",
    normalizerVersion,
    ignoredMetadataKeys: [...ignoredMetadataKeys].sort(),
    testPlanId,
    testPlanDigest,
    criticalFlowPassRate,
    expectedFlowCount: expectedFlows.length,
    observedFlowCount: comparisons.length,
    comparisons,
    findings: [
      ...missingPlatforms.map(item => `${item}:LOCAL_FLOW_PLAN_COVERAGE_MISSING`),
      ...missingExpectedFlows.map(item => `${item.platform}:${item.flowId}:LOCAL_EXPECTED_FLOW_MISSING`),
      ...(observedPassRate < criticalFlowPassRate ? [`LOCAL_CRITICAL_FLOW_PASS_RATE:${observedPassRate}`] : []),
      ...failed.flatMap(item => item.diffs.map(diff => `${item.platform}:${item.flowId}:${diff.kind}:${diff.sequence ?? "all"}`)),
    ],
  };
}

function base64Bytes(value: unknown, path: string): Uint8Array {
  if (typeof value !== "string" || value.length === 0 || value.length > Math.ceil(MAX_VISUAL_BYTES * 4 / 3) + 4 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/u.test(value)) {
    throw new Error(`${path} must be canonical base64`);
  }
  const decoded = Buffer.from(value, "base64");
  if (decoded.toString("base64") !== value) throw new Error(`${path} must use canonical base64 padding`);
  return decoded;
}

function evaluateVisual(
  value: unknown,
  differential: MiniappLocalDifferentialEvaluation,
  context: MiniappLocalValidationContext,
): MiniappLocalVisualEvaluation {
  if (value === undefined) {
    return {
      state: "NOT_RUN",
      authoritativeExecution: "NOT_RUN",
      captureTrust: "NOT_RUN",
      sourceScreenshots: "NOT_RUN",
      targetScreenshots: "NOT_RUN",
      rawCaptureReplay: "NOT_RUN",
      requestedSimilarity: context.requestedSimilarity,
      functionalPrerequisite: differential.state,
      comparisons: [],
      reason: "LOCAL_VISUAL_INPUT_NOT_PROVIDED; official browser/device screenshots remain NOT_RUN.",
    };
  }
  const candidate = object(value, "localValidation.visual");
  exactKeys(candidate, ["comparisons"], ["comparisons"], "localValidation.visual");
  if (!Array.isArray(candidate.comparisons) || candidate.comparisons.length === 0 || candidate.comparisons.length > 32) {
    throw new Error("localValidation.visual.comparisons must contain 1 through 32 comparisons");
  }
  const targetMap = new Map(context.targets.map((target) => [target.platform, target]));
  const seen = new Set<string>();
  let totalBytes = 0;
  const comparisons = candidate.comparisons.map((comparisonValue, index): MiniappLocalVisualComparison => {
    const path = `localValidation.visual.comparisons[${index}]`;
    const comparison = object(comparisonValue, path);
    exactKeys(comparison, ["comparisonId", "platform", "width", "height", "sourceRgbaBase64", "targetRgbaBase64", "sourceDigest", "targetDigest", "targetProjectDigest", "masks", "sourceExecutor", "targetExecutor", "verifier"], ["comparisonId", "platform", "width", "height", "sourceRgbaBase64", "targetRgbaBase64", "sourceDigest", "targetDigest", "targetProjectDigest", "masks", "sourceExecutor", "targetExecutor", "verifier"], path);
    const comparisonId = string(comparison.comparisonId, `${path}.comparisonId`);
    const targetPlatform = platform(comparison.platform, `${path}.platform`);
    const key = `${targetPlatform}:${comparisonId}`;
    if (seen.has(key)) throw new Error(`${path} duplicates ${key}`);
    seen.add(key);
    const requestedTarget = targetMap.get(targetPlatform);
    if (!requestedTarget) throw new Error(`${path}.platform is not requested`);
    if (digest(comparison.targetProjectDigest, `${path}.targetProjectDigest`) !== requestedTarget.projectDigest) {
      throw new Error(`${path}.targetProjectDigest does not bind the generated project`);
    }
    const identities = ["sourceExecutor", "targetExecutor", "verifier"].map(field => string(comparison[field], `${path}.${field}`));
    if (new Set(identities).size !== 3) throw new Error(`${path} requires distinct executor and verifier identities`);
    const width = integer(comparison.width, `${path}.width`, 1, 1024);
    const height = integer(comparison.height, `${path}.height`, 1, 1024);
    const pixels = width * height;
    if (pixels > MAX_VISUAL_PIXELS) throw new Error(`${path} exceeds ${MAX_VISUAL_PIXELS} pixels`);
    const source = base64Bytes(comparison.sourceRgbaBase64, `${path}.sourceRgbaBase64`);
    const target = base64Bytes(comparison.targetRgbaBase64, `${path}.targetRgbaBase64`);
    const expectedBytes = pixels * 4;
    if (source.byteLength !== expectedBytes || target.byteLength !== expectedBytes) throw new Error(`${path} RGBA byte length does not match dimensions`);
    totalBytes += source.byteLength + target.byteLength;
    if (totalBytes > MAX_VISUAL_BYTES) throw new Error(`localValidation.visual exceeds ${MAX_VISUAL_BYTES} decoded bytes`);
    const sourceDigest = digest(comparison.sourceDigest, `${path}.sourceDigest`);
    const targetDigest = digest(comparison.targetDigest, `${path}.targetDigest`);
    if (sourceDigest !== digestMiniappValidationBytes(source)) throw new Error(`${path}.sourceDigest mismatch`);
    if (targetDigest !== digestMiniappValidationBytes(target)) throw new Error(`${path}.targetDigest mismatch`);
    if (!Array.isArray(comparison.masks) || comparison.masks.length > 64) throw new Error(`${path}.masks is invalid`);
    const masked = new Uint8Array(pixels);
    const maskAudit: Array<MiniappLocalVisualComparison["maskAudit"][number]> = [];
    for (const [maskIndex, maskValue] of comparison.masks.entries()) {
      const maskPath = `${path}.masks[${maskIndex}]`;
      const mask = object(maskValue, maskPath);
      exactKeys(mask, ["x", "y", "width", "height", "reason"], ["x", "y", "width", "height", "reason"], maskPath);
      const x = integer(mask.x, `${maskPath}.x`, 0, width - 1);
      const y = integer(mask.y, `${maskPath}.y`, 0, height - 1);
      const maskWidth = integer(mask.width, `${maskPath}.width`, 1, width - x);
      const maskHeight = integer(mask.height, `${maskPath}.height`, 1, height - y);
      const reason = string(mask.reason, `${maskPath}.reason`, /^[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,255}$/u, 256);
      maskAudit.push({ x, y, width: maskWidth, height: maskHeight, reason });
      for (let row = y; row < y + maskHeight; row += 1) {
        for (let column = x; column < x + maskWidth; column += 1) masked[row * width + column] = 1;
      }
      if (masked.reduce((sum, item) => sum + item, 0) / pixels > 0.1) {
        throw new Error(`${path}.masks conceal more than 10% of pixels`);
      }
    }
    const maskedPixels = masked.reduce((sum, item) => sum + item, 0);
    if (maskedPixels / pixels > 0.1) throw new Error(`${path}.masks conceal more than 10% of pixels`);
    const comparedPixels = pixels - maskedPixels;
    if (comparedPixels === 0) throw new Error(`${path}.masks conceal every pixel`);
    let channelDifference = 0;
    for (let pixel = 0; pixel < pixels; pixel += 1) {
      if (masked[pixel] === 1) continue;
      for (let channel = 0; channel < 4; channel += 1) {
        const offset = pixel * 4 + channel;
        channelDifference += Math.abs(source[offset]! - target[offset]!);
      }
    }
    const similarity = 1 - channelDifference / (comparedPixels * 4 * 255);
    const functionalPass = differential.state === "PASSED_LOCAL";
    return {
      comparisonId,
      platform: targetPlatform,
      width,
      height,
      sourceDigest,
      targetDigest,
      targetProjectDigest: requestedTarget.projectDigest,
      sourceExecutor: identities[0]!,
      targetExecutor: identities[1]!,
      verifier: identities[2]!,
      attributionState: "SELF_ASSERTED_UNVERIFIED",
      similarity,
      threshold: context.requestedSimilarity,
      maskedPixels,
      comparedPixels,
      maskAudit,
      verdict: !functionalPass ? "blocked" : similarity >= context.requestedSimilarity ? "passed" : "failed",
    };
  });
  const missingPlatforms = context.targets.filter(target => !comparisons.some(item => item.platform === target.platform));
  const failed = comparisons.some(item => item.verdict === "failed");
  const blocked = differential.state !== "PASSED_LOCAL" || missingPlatforms.length > 0;
  return {
    state: blocked ? "BLOCKED" : failed ? "FAILED_LOCAL" : "PASSED_LOCAL",
    authoritativeExecution: "NOT_RUN",
    captureTrust: "UNATTESTED_LOCAL_INPUT",
    sourceScreenshots: "NOT_RUN",
    targetScreenshots: "NOT_RUN",
    rawCaptureReplay: "BLOCKED_RAW_CAPTURE_NOT_MATERIALIZED",
    requestedSimilarity: context.requestedSimilarity,
    functionalPrerequisite: differential.state,
    comparisons,
    reason: blocked
      ? "Local pixel candidates cannot pass because functional parity or platform coverage is unresolved; official device screenshots remain NOT_RUN."
      : failed
        ? "At least one local byte-bound pixel comparison is below threshold; official device screenshots remain NOT_RUN."
        : "Local byte-bound pixel candidates meet threshold; official device screenshots and visual parity remain NOT_RUN.",
  };
}

function repairOwner(value: unknown, path: string): MiniappLocalRepairAction["owner"] {
  if (value !== "ir" && value !== "mapping" && value !== "adapter" && value !== "generated-code") {
    throw new Error(`${path} is invalid`);
  }
  return value;
}

function strictJsonPointer(value: unknown, path: string): string {
  if (typeof value !== "string" || value.length < 2 || value.length > 512 || !value.startsWith("/")) {
    throw new Error(`${path} must be a bounded JSON Pointer`);
  }
  const rawSegments = value.slice(1).split("/");
  if (rawSegments.some(segment => segment.length === 0 || !/^(?:[A-Za-z0-9._-]|~[01])+$/u.test(segment))) {
    throw new Error(`${path} contains an invalid RFC 6901 segment or escape`);
  }
  const decoded = rawSegments.map(segment => segment.replace(/~1/gu, "/").replace(/~0/gu, "~"));
  if (!PATCH_ROOTS.has(decoded[0]!) || decoded.some(segment =>
    segment === "__proto__"
      || segment === "prototype"
      || segment === "constructor"
      || segment === "."
      || segment === ".."
      || segment.includes("/"))) {
    throw new Error(`${path} is outside repairable roots`);
  }
  return value;
}

function evaluateRepair(
  value: unknown,
  context: MiniappLocalValidationContext,
  differential: MiniappLocalDifferentialEvaluation,
  visual: MiniappLocalVisualEvaluation,
): MiniappLocalRepairEvaluation {
  const maximumIterations = Math.min(3, Math.max(0, context.maximumRepairIterations));
  if (value === undefined) {
    return {
      state: "NOT_RUN",
      maximumIterations,
      appliedIterations: 0,
      actions: [],
      rollback: "NO_MUTATION_PERFORMED",
      executionEvidence: "NOT_RUN",
      stopReasons: ["LOCAL_REPAIR_PROPOSALS_NOT_PROVIDED"],
    };
  }
  const candidate = object(value, "localValidation.repair");
  exactKeys(candidate, ["priorPatchDigests", "proposals"], ["priorPatchDigests", "proposals"], "localValidation.repair");
  if (!Array.isArray(candidate.priorPatchDigests) || candidate.priorPatchDigests.length > 64) throw new Error("localValidation.repair.priorPatchDigests is invalid");
  const prior = new Set(candidate.priorPatchDigests.map((item, index) => digest(item, `localValidation.repair.priorPatchDigests[${index}]`)));
  if (!Array.isArray(candidate.proposals) || candidate.proposals.length === 0 || candidate.proposals.length > 16) throw new Error("localValidation.repair.proposals must contain 1 through 16 proposals");
  const knownFindings = new Map(context.repairFindings.map(item => [item.finding, item]));
  for (const comparison of differential.comparisons) {
    for (const diff of comparison.diffs) knownFindings.set(`${comparison.platform}:${comparison.flowId}:${diff.kind}:${diff.sequence ?? "all"}`, { finding: `${comparison.platform}:${comparison.flowId}:${diff.kind}:${diff.sequence ?? "all"}`, owner: "ir", approvalRequired: false });
  }
  for (const comparison of visual.comparisons.filter(item => item.verdict === "failed")) {
    knownFindings.set(`${comparison.platform}:${comparison.comparisonId}:VISUAL_THRESHOLD`, { finding: `${comparison.platform}:${comparison.comparisonId}:VISUAL_THRESHOLD`, owner: "mapping", approvalRequired: false });
  }
  const seen = new Set<string>();
  const actions = candidate.proposals.map((proposalValue, index): MiniappLocalRepairAction => {
    const path = `localValidation.repair.proposals[${index}]`;
    const proposal = object(proposalValue, path);
    exactKeys(proposal, ["finding", "owner", "patch", "patchDigest", "targetedTests", "affectedGates", "risk"], ["finding", "owner", "patch", "patchDigest", "targetedTests", "affectedGates", "risk"], path);
    const finding = string(proposal.finding, `${path}.finding`, /^[A-Za-z0-9][A-Za-z0-9._:;-]{0,511}$/u, 512);
    const owner = repairOwner(proposal.owner, `${path}.owner`);
    const known = knownFindings.get(finding);
    if (!known || known.owner !== owner) throw new Error(`${path} does not bind an observed finding and owner`);
    if (!Array.isArray(proposal.patch) || proposal.patch.length === 0 || proposal.patch.length > 64) throw new Error(`${path}.patch must contain 1 through 64 operations`);
    const patch = proposal.patch.map((operationValue, operationIndex) => {
      const operationPath = `${path}.patch[${operationIndex}]`;
      const operation = object(operationValue, operationPath);
      exactKeys(operation, ["op", "path", "value"], ["op", "path", "value"], operationPath);
      if (operation.op !== "replace") throw new Error(`${operationPath}.op must be replace`);
      const pointer = strictJsonPointer(operation.path, `${operationPath}.path`);
      return { op: "replace" as const, path: pointer, value: jsonValue(operation.value, `${operationPath}.value`) };
    });
    const patchDigest = digest(proposal.patchDigest, `${path}.patchDigest`);
    if (patchDigest !== digestMiniappValidationPayload(patch)) throw new Error(`${path}.patchDigest mismatch`);
    const targetedTests = parseStringList(proposal.targetedTests, `${path}.targetedTests`, 1, 32);
    const affectedGates = parseStringList(proposal.affectedGates, `${path}.affectedGates`, 1, 10, /^G[0-9]$/u);
    const risk = proposal.risk;
    if (risk !== "low" && risk !== "medium" && risk !== "high") throw new Error(`${path}.risk is invalid`);
    const stopReasons = [
      ...(index >= maximumIterations ? ["MAXIMUM_ITERATIONS_REACHED"] : []),
      ...(prior.has(patchDigest) || seen.has(patchDigest) ? ["DUPLICATE_PATCH_FINGERPRINT"] : []),
      ...(known.approvalRequired || risk === "high" ? ["APPROVAL_OR_HIGH_RISK_REQUIRED"] : []),
    ];
    seen.add(patchDigest);
    return {
      finding,
      owner,
      strategy: owner === "mapping" ? "mapping-rule" : owner === "adapter" ? "platform-adapter" : owner === "generated-code" ? "generator-template" : "ir",
      patchDigest,
      patchScope: patch.map(operation => operation.path),
      targetedTests,
      affectedGates,
      risk,
      status: stopReasons.length === 0 ? "PROPOSED" : "BLOCKED",
      ...(stopReasons.length > 0 ? { stopReason: stopReasons.join(",") } : {}),
    };
  });
  const stopReasons = [...new Set(actions.flatMap(action => action.stopReason?.split(",") ?? []))].sort();
  return {
    state: maximumIterations === 0 || actions.some(action => action.status === "BLOCKED") ? "BLOCKED" : "PLAN_READY",
    maximumIterations,
    appliedIterations: 0,
    actions,
    rollback: "NO_MUTATION_PERFORMED",
    executionEvidence: "NOT_RUN",
    stopReasons: maximumIterations === 0 ? [...new Set([...stopReasons, "AUTO_REPAIR_DISABLED"])].sort() : stopReasons,
  };
}

function parseStringList(
  value: unknown,
  path: string,
  minimum: number,
  maximum: number,
  pattern: RegExp = IDENTIFIER,
): readonly string[] {
  if (!Array.isArray(value) || value.length < minimum || value.length > maximum) throw new Error(`${path} is invalid`);
  const result = value.map((item, index) => string(item, `${path}[${index}]`, pattern));
  if (new Set(result).size !== result.length) throw new Error(`${path} must contain unique values`);
  return result;
}

function deliveryPlan(context: MiniappLocalValidationContext): MiniappLocalDeliveryPlan {
  const stages = ["lint", "schema", "build", "preview", "upload", "review", "release"] as const;
  const profiles = context.targets.map(target => ({
    platform: target.platform,
    toolchainVersion: target.toolchainVersion,
    projectDigest: target.projectDigest,
    stages: stages.map(stage => ({
      stage,
      state: "NOT_RUN" as const,
      sideEffect: stage === "upload" || stage === "review" || stage === "release",
      approvalRequired: stage === "preview" || stage === "upload" || stage === "review" || stage === "release",
    })),
  }));
  return {
    state: "PLANNED_LOCAL",
    officialExecution: "NOT_RUN",
    idempotencyKey: digestMiniappValidationPayload(profiles),
    profiles,
    credentials: "SECRET_REFERENCES_ONLY",
  };
}

export function evaluateMiniappLocalValidation(
  value: unknown,
  context: MiniappLocalValidationContext,
): MiniappLocalValidationEvaluation {
  if (!Number.isFinite(context.requestedSimilarity) || context.requestedSimilarity < 0 || context.requestedSimilarity > 1) {
    throw new Error("requestedSimilarity must be from 0 through 1");
  }
  if (!Number.isFinite(context.criticalFlowPassRate) || context.criticalFlowPassRate < 0 || context.criticalFlowPassRate > 1) {
    throw new Error("criticalFlowPassRate must be from 0 through 1");
  }
  if (!Number.isSafeInteger(context.maximumRepairIterations) || context.maximumRepairIterations < 0 || context.maximumRepairIterations > 10) {
    throw new Error("maximumRepairIterations must be an integer from 0 through 10");
  }
  if (context.targets.length === 0 || new Set(context.targets.map(target => target.platform)).size !== context.targets.length) {
    throw new Error("validation context targets must be non-empty and unique");
  }
  const candidateSnapshot = value === undefined ? undefined : snapshotLocalValidation(value);
  const candidate = candidateSnapshot === undefined ? undefined : object(candidateSnapshot, "localValidation");
  if (candidate) {
    exactKeys(candidate, ["schemaVersion", "differential", "visual", "repair"], ["schemaVersion"], "localValidation");
    if (candidate.schemaVersion !== "1.0") throw new Error("localValidation.schemaVersion must be 1.0");
    if (candidate.differential === undefined && candidate.visual === undefined && candidate.repair === undefined) {
      throw new Error("localValidation must request at least one local handler");
    }
    if (candidate.visual !== undefined && context.requestedSimilarity < 0.95) {
      throw new Error("local visual comparison cannot lower requestedSimilarity below 0.95");
    }
  }
  const differential = evaluateDifferential(candidate?.differential, context);
  const visual = evaluateVisual(candidate?.visual, differential, context);
  const repair = evaluateRepair(candidate?.repair, context, differential, visual);
  const plan = deliveryPlan(context);
  const inputDigest = candidateSnapshot ? digestValidatedMiniappValidationPayload(candidateSnapshot) : "NOT_RUN";
  const base = {
    schemaVersion: "1.0" as const,
    inputDigest,
    differential,
    visual,
    repair,
    deliveryPlan: plan,
    evidenceBoundary: {
      localCandidate: candidate ? "SELF_ATTESTED" as const : "NOT_RUN" as const,
      officialSourceRuntime: "NOT_RUN" as const,
      officialTargetRuntime: "NOT_RUN" as const,
      officialDeviceVisual: "NOT_RUN" as const,
      upload: "NOT_RUN" as const,
      review: "NOT_RUN" as const,
      release: "NOT_RUN" as const,
      certification: "NOT_CERTIFIED" as const,
    },
  };
  return { ...base, deterministicDigest: digestMiniappValidationPayload(base) };
}

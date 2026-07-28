import type {
  TranslationLanguageId,
  TranslationRepositoryPlan,
  TranslationRepositoryWorkUnit,
} from "../contracts";
import { TranslationContractError, readTranslationCapability } from "./translationRoutes";

/**
 * Repository-scope handoff used to be accepted after browser-only validation,
 * which any modified client could skip. The authoritative check now runs on the
 * server against the same route contract the capability endpoint serves, so an
 * inventory that names an unknown route, a route whose local profile has not
 * passed, or a plan that claims execution can never be accepted.
 */

export const MAX_PLAN_BYTES = 8 * 1024 * 1024;
const MAX_FILE_COUNT = 5_000;
const MAX_SOURCE_BYTES = 64 * 1024 * 1024;
const MAX_WORK_UNIT_BYTES = 2 * 1024 * 1024;
const SHA256 = /^[0-9a-f]{64}$/;

export class RepositoryPlanError extends Error {
  readonly errorCode: string;

  constructor(errorCode: string, message: string) {
    super(message);
    this.name = "RepositoryPlanError";
    this.errorCode = errorCode;
  }
}

function fail(errorCode: string, message: string): never {
  throw new RepositoryPlanError(errorCode, message);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isSafeRepositoryRef(value: string): boolean {
  if (
    value.length < 3
    || value.length > 180
    || /[\s\\?#]/.test(value)
    || value.startsWith("/")
    || value.startsWith("~")
  ) return false;
  if (/^local:[a-z0-9][a-z0-9._/-]{2,170}$/i.test(value)) return true;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:"
      && !parsed.username
      && !parsed.password
      && Boolean(parsed.hostname);
  } catch {
    return false;
  }
}

function parseWorkUnit(value: unknown, index: number, routeId: string): TranslationRepositoryWorkUnit {
  if (!isRecord(value)) fail("WORK_UNIT_INVALID", `work_units[${index}] 不是对象。`);
  const sourcePath = value.source_path;
  if (typeof sourcePath !== "string" || sourcePath.length === 0 || sourcePath.length > 500) {
    fail("WORK_UNIT_PATH_INVALID", `work_units[${index}].source_path 长度非法。`);
  }
  if (sourcePath.startsWith("/") || sourcePath.split("/").includes("..")) {
    fail("WORK_UNIT_PATH_ESCAPES_REPOSITORY", `work_units[${index}].source_path 不是仓库内相对路径。`);
  }
  if (value.route_id !== routeId) {
    fail("WORK_UNIT_ROUTE_MISMATCH", `work_units[${index}].route_id 与清单路线不一致。`);
  }
  if (typeof value.source_sha256 !== "string" || !SHA256.test(value.source_sha256)) {
    fail("WORK_UNIT_DIGEST_INVALID", `work_units[${index}].source_sha256 不是 64 位十六进制摘要。`);
  }
  if (
    !Number.isInteger(value.source_bytes)
    || (value.source_bytes as number) < 0
    || (value.source_bytes as number) > MAX_WORK_UNIT_BYTES
  ) {
    fail("WORK_UNIT_SIZE_INVALID", `work_units[${index}].source_bytes 超出单文件上限。`);
  }
  if (value.status !== "DISCOVERY_REQUIRED") {
    fail("WORK_UNIT_STATUS_INVALID", `work_units[${index}].status 必须是 DISCOVERY_REQUIRED。`);
  }
  if (value.execution_status !== "NOT_RUN") {
    fail("WORK_UNIT_EXECUTION_CLAIMED", `work_units[${index}] 声称已执行；只读清单不得携带执行结果。`);
  }
  if (value.declared_profile !== "typed-pure-function-v1") {
    fail("WORK_UNIT_PROFILE_UNSUPPORTED", `work_units[${index}].declared_profile 超出当前受限 Profile。`);
  }
  const unsupported = value.unsupported_until_discovered;
  if (!Array.isArray(unsupported) || unsupported.length > 20
    || !unsupported.every((item) => typeof item === "string" && item.length <= 300)) {
    fail("WORK_UNIT_BLOCKERS_INVALID", `work_units[${index}].unsupported_until_discovered 非法。`);
  }
  if (typeof value.id !== "string" || value.id.length === 0 || value.id.length > 200) {
    fail("WORK_UNIT_ID_INVALID", `work_units[${index}].id 非法。`);
  }
  return {
    id: value.id,
    route_id: routeId,
    source_path: sourcePath,
    source_sha256: value.source_sha256,
    source_bytes: value.source_bytes as number,
    status: "DISCOVERY_REQUIRED",
    execution_status: "NOT_RUN",
    required_inputs: ["function_name", "behavior_cases_json"],
    declared_profile: "typed-pure-function-v1",
    unsupported_until_discovered: unsupported as string[],
  };
}

export type RepositoryPlanContext = {
  repositoryRef: string;
  routeId: string;
  sourceLanguage: TranslationLanguageId;
  targetLanguage: TranslationLanguageId;
};

export function validateRepositoryPlan(
  raw: unknown,
  context: RepositoryPlanContext,
): TranslationRepositoryPlan {
  let capability;
  try {
    capability = readTranslationCapability();
  } catch (error) {
    fail(
      error instanceof TranslationContractError ? error.errorCode : "TRANSLATION_CONTRACT_UNAVAILABLE",
      "无法读取路线能力契约，整库清单一律拒绝。",
    );
  }

  if (!isRecord(raw)) fail("PLAN_INVALID", "清单顶层不是对象。");
  if (raw.schema_version !== "1.0.0") fail("PLAN_SCHEMA_VERSION_UNSUPPORTED", "清单 schema_version 不受支持。");
  if (raw.kind !== "elmos.repository-route-plan") fail("PLAN_KIND_INVALID", "清单 kind 不是 elmos.repository-route-plan。");
  if (raw.status !== "PLANNED") fail("PLAN_STATUS_INVALID", "清单 status 必须是 PLANNED。");
  if (raw.snapshot_consistency !== "STABLE_READ_ONLY_SCAN") {
    fail("PLAN_SNAPSHOT_CONSISTENCY_INVALID", "清单未声明稳定只读扫描。");
  }
  for (const field of ["execution_status", "external_verification_status"] as const) {
    if (raw[field] !== "NOT_RUN") fail("PLAN_EXECUTION_CLAIMED", `清单 ${field} 必须是 NOT_RUN。`);
  }
  if (raw.certification_status !== "NOT_CERTIFIED") {
    fail("PLAN_CERTIFICATION_CLAIMED", "清单 certification_status 必须是 NOT_CERTIFIED。");
  }

  const repositoryRef = raw.repository_ref;
  if (typeof repositoryRef !== "string" || !isSafeRepositoryRef(repositoryRef)) {
    fail("PLAN_REPOSITORY_REF_INVALID", "清单仓库引用含凭证、查询参数或本机路径。");
  }
  if (repositoryRef !== context.repositoryRef) {
    fail("PLAN_REPOSITORY_REF_MISMATCH", "清单仓库引用与当前页面输入不一致。");
  }
  if (typeof raw.snapshot_sha256 !== "string" || !SHA256.test(raw.snapshot_sha256)) {
    fail("PLAN_SNAPSHOT_DIGEST_INVALID", "清单 snapshot_sha256 不是 64 位十六进制摘要。");
  }

  const route = capability.routes.find((candidate) => candidate.id === raw.route_id);
  if (!route) fail("PLAN_ROUTE_UNKNOWN", "清单引用的路线不在仓库路线契约中。");
  if (route.id !== context.routeId) fail("PLAN_ROUTE_MISMATCH", "清单路线与当前选择的路线不一致。");
  if (raw.source_language !== context.sourceLanguage || raw.target_language !== context.targetLanguage) {
    fail("PLAN_LANGUAGE_MISMATCH", "清单源语言或目标语言与当前选择不一致。");
  }
  if (route.source !== context.sourceLanguage || route.target !== context.targetLanguage) {
    fail("PLAN_ROUTE_DIRECTION_MISMATCH", "清单路线方向与源/目标语言不一致。");
  }
  if (route.localExecution !== "PASSED") {
    fail(
      "PLAN_ROUTE_LOCAL_PROFILE_NOT_PASSED",
      `路线 ${route.id} 的本地受限 Profile 状态为 ${route.localExecution}，不接受整库拆分。`,
    );
  }

  const fileCount = raw.file_count;
  const sourceFileCount = raw.source_file_count;
  const sourceBytes = raw.source_bytes;
  if (!Number.isInteger(fileCount) || (fileCount as number) < 1 || (fileCount as number) > MAX_FILE_COUNT) {
    fail("PLAN_FILE_COUNT_INVALID", "清单 file_count 超出 1–5000 范围。");
  }
  if (
    !Number.isInteger(sourceFileCount)
    || (sourceFileCount as number) < 1
    || (sourceFileCount as number) > (fileCount as number)
  ) {
    fail("PLAN_SOURCE_FILE_COUNT_INVALID", "清单 source_file_count 非法或超过 file_count。");
  }
  if (
    !Number.isInteger(sourceBytes)
    || (sourceBytes as number) < 1
    || (sourceBytes as number) > MAX_SOURCE_BYTES
  ) {
    fail("PLAN_SOURCE_BYTES_INVALID", "清单 source_bytes 超出 64 MB 聚合上限。");
  }
  if (
    !Number.isInteger(raw.ignored_symlink_count)
    || (raw.ignored_symlink_count as number) < 0
  ) {
    fail("PLAN_SYMLINK_COUNT_INVALID", "清单 ignored_symlink_count 非法。");
  }

  const counts = raw.language_counts;
  if (!isRecord(counts)) fail("PLAN_LANGUAGE_COUNTS_INVALID", "清单缺少 language_counts。");
  for (const language of capability.languages) {
    const value = counts[language.id];
    if (!Number.isInteger(value) || (value as number) < 0) {
      fail("PLAN_LANGUAGE_COUNT_INVALID", `清单 language_counts.${language.id} 非法。`);
    }
  }

  if (!Array.isArray(raw.work_units)) fail("PLAN_WORK_UNITS_INVALID", "清单缺少 work_units 数组。");
  if (raw.work_units.length !== sourceFileCount) {
    fail("PLAN_WORK_UNIT_COUNT_DRIFT", "work_units 数量与 source_file_count 不一致。");
  }
  const workUnits = raw.work_units.map((unit, index) => parseWorkUnit(unit, index, route.id));
  const seenPaths = new Set<string>();
  let aggregateBytes = 0;
  for (const unit of workUnits) {
    if (seenPaths.has(unit.source_path)) {
      fail("PLAN_WORK_UNIT_PATH_DUPLICATED", `清单重复声明了源文件 ${unit.source_path}。`);
    }
    seenPaths.add(unit.source_path);
    aggregateBytes += unit.source_bytes;
  }
  if (aggregateBytes > (sourceBytes as number)) {
    fail("PLAN_SOURCE_BYTES_DRIFT", "work_units 字节合计超过清单声明的 source_bytes。");
  }

  const limitations = raw.limitations;
  if (
    !Array.isArray(limitations)
    || limitations.length === 0
    || limitations.length > 20
    || !limitations.every((item) => typeof item === "string" && item.length > 0 && item.length <= 500)
  ) {
    fail("PLAN_LIMITATIONS_INVALID", "清单必须显式声明 1–20 条适用边界。");
  }

  return {
    schema_version: "1.0.0",
    kind: "elmos.repository-route-plan",
    status: "PLANNED",
    repository_ref: repositoryRef,
    snapshot_sha256: raw.snapshot_sha256,
    snapshot_consistency: "STABLE_READ_ONLY_SCAN",
    route_id: route.id,
    source_language: context.sourceLanguage,
    target_language: context.targetLanguage,
    file_count: fileCount as number,
    source_file_count: sourceFileCount as number,
    source_bytes: sourceBytes as number,
    language_counts: counts as Record<TranslationLanguageId, number>,
    ignored_symlink_count: raw.ignored_symlink_count as number,
    work_units: workUnits,
    execution_status: "NOT_RUN",
    external_verification_status: "NOT_RUN",
    certification_status: "NOT_CERTIFIED",
    limitations: limitations as string[],
  };
}

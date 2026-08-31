import type {
  TranslationDiscoveryReport,
  TranslationDiscoveryResult,
  TranslationLanguageId,
} from "../contracts";
import { RepositoryPlanError, isSafeRepositoryRef } from "./translationRepositoryPlan";
import { TranslationContractError, readTranslationCapability } from "./translationRoutes";

/**
 * Server-side acceptance for the engine's repository discovery report.
 *
 * Discovery is the step that turns "this file exists" into "this file is or is
 * not migratable, and here is why". The console must therefore refuse a report
 * that claims execution, that belongs to a different snapshot than the plan the
 * operator already imported, or that marks a unit READY without the analyzer
 * facts a READY verdict requires.
 */

const SHA256 = /^[0-9a-f]{64}$/;
const VERDICTS = ["READY", "UNSUPPORTED", "NO_CANDIDATE_DECLARATION", "UNREADABLE"] as const;
export const MAX_DISCOVERY_BYTES = 8 * 1024 * 1024;
const MAX_RESULTS = 5_000;

type Verdict = (typeof VERDICTS)[number];

function fail(errorCode: string, message: string): never {
  throw new RepositoryPlanError(errorCode, message);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseResult(value: unknown, index: number, routeId: string): TranslationDiscoveryResult {
  if (!isRecord(value)) fail("DISCOVERY_RESULT_INVALID", `results[${index}] 不是对象。`);
  const verdict = value.verdict;
  if (typeof verdict !== "string" || !(VERDICTS as readonly string[]).includes(verdict)) {
    fail("DISCOVERY_VERDICT_INVALID", `results[${index}].verdict 不是受支持的判定值。`);
  }
  const sourcePath = value.source_path;
  if (typeof sourcePath !== "string" || sourcePath.length === 0 || sourcePath.length > 500) {
    fail("DISCOVERY_PATH_INVALID", `results[${index}].source_path 长度非法。`);
  }
  if (sourcePath.startsWith("/") || sourcePath.split("/").includes("..")) {
    fail("DISCOVERY_PATH_ESCAPES_REPOSITORY", `results[${index}].source_path 不是仓库内相对路径。`);
  }
  if (typeof value.id !== "string" || value.id.length === 0 || value.id.length > 200) {
    fail("DISCOVERY_ID_INVALID", `results[${index}].id 非法。`);
  }
  if (value.execution_status !== "NOT_RUN") {
    fail("DISCOVERY_EXECUTION_CLAIMED", `results[${index}] 声称已执行；发现阶段不得携带执行结果。`);
  }
  if (value.profile !== "typed-pure-function-v1") {
    fail("DISCOVERY_PROFILE_UNSUPPORTED", `results[${index}].profile 超出当前受限 Profile。`);
  }
  if (typeof value.declared_sha256 !== "string" || !SHA256.test(value.declared_sha256)) {
    fail("DISCOVERY_DIGEST_INVALID", `results[${index}].declared_sha256 不是 64 位十六进制摘要。`);
  }

  const result: TranslationDiscoveryResult = {
    id: value.id,
    source_path: sourcePath,
    declared_sha256: value.declared_sha256,
    verdict: verdict as Verdict,
    profile: "typed-pure-function-v1",
    execution_status: "NOT_RUN",
    route_id: routeId,
    rejected_candidates: [],
  };

  if (verdict === "READY") {
    // A READY verdict is a claim that the compiler-backed analyzer accepted a
    // declaration. Without the analyzer facts the claim is unverifiable, so it
    // is refused rather than displayed.
    if (typeof value.function_name !== "string" || value.function_name.length === 0) {
      fail("DISCOVERY_READY_WITHOUT_FUNCTION", `results[${index}] 判定为 READY 但没有函数名。`);
    }
    if (!Number.isInteger(value.parameter_count) || (value.parameter_count as number) < 0) {
      fail("DISCOVERY_READY_WITHOUT_SIGNATURE", `results[${index}] 判定为 READY 但没有参数个数。`);
    }
    if (typeof value.analyzer !== "string" || value.analyzer.length === 0) {
      fail("DISCOVERY_READY_WITHOUT_ANALYZER", `results[${index}] 判定为 READY 但没有分析器来源。`);
    }
    result.function_name = value.function_name;
    result.parameter_count = value.parameter_count as number;
    result.analyzer = value.analyzer;
    result.return_type = typeof value.return_type === "string" ? value.return_type : undefined;
  } else if (typeof value.reason === "string" && value.reason.length <= 500) {
    result.reason = value.reason;
  }

  const rejections = value.rejected_candidates;
  if (Array.isArray(rejections)) {
    result.rejected_candidates = rejections.slice(0, 20).flatMap((entry) => {
      if (!isRecord(entry)) return [];
      const candidate = entry.candidate;
      const reason = entry.reason;
      if (typeof candidate !== "string" || typeof reason !== "string") return [];
      return [{ candidate: candidate.slice(0, 200), reason: reason.slice(0, 300) }];
    });
  }
  return result;
}

export type DiscoveryContext = {
  repositoryRef: string;
  routeId: string;
  snapshotSha256: string;
  sourceLanguage: TranslationLanguageId;
  targetLanguage: TranslationLanguageId;
};

export function validateDiscoveryReport(
  raw: unknown,
  context: DiscoveryContext,
): TranslationDiscoveryReport {
  let capability;
  try {
    capability = readTranslationCapability();
  } catch (error) {
    fail(
      error instanceof TranslationContractError ? error.errorCode : "TRANSLATION_CONTRACT_UNAVAILABLE",
      "无法读取路线能力契约，发现报告一律拒绝。",
    );
  }

  if (!isRecord(raw)) fail("DISCOVERY_INVALID", "发现报告顶层不是对象。");
  if (raw.kind !== "elmos.repository-discovery-report") {
    fail("DISCOVERY_KIND_INVALID", "kind 不是 elmos.repository-discovery-report。");
  }
  if (raw.schema_version !== "1.0.0") fail("DISCOVERY_SCHEMA_VERSION_UNSUPPORTED", "schema_version 不受支持。");
  if (raw.status !== "DISCOVERED") fail("DISCOVERY_STATUS_INVALID", "status 必须是 DISCOVERED。");
  for (const field of ["execution_status", "external_verification_status"] as const) {
    if (raw[field] !== "NOT_RUN") fail("DISCOVERY_EXECUTION_CLAIMED", `${field} 必须是 NOT_RUN。`);
  }
  if (raw.certification_status !== "NOT_CERTIFIED") {
    fail("DISCOVERY_CERTIFICATION_CLAIMED", "certification_status 必须是 NOT_CERTIFIED。");
  }

  const repositoryRef = raw.repository_ref;
  if (typeof repositoryRef !== "string" || !isSafeRepositoryRef(repositoryRef)) {
    fail("DISCOVERY_REPOSITORY_REF_INVALID", "发现报告的仓库引用不安全。");
  }
  if (repositoryRef !== context.repositoryRef) {
    fail("DISCOVERY_REPOSITORY_REF_MISMATCH", "发现报告的仓库引用与当前页面输入不一致。");
  }
  if (typeof raw.snapshot_sha256 !== "string" || !SHA256.test(raw.snapshot_sha256)) {
    fail("DISCOVERY_SNAPSHOT_INVALID", "snapshot_sha256 不是 64 位十六进制摘要。");
  }
  if (raw.snapshot_sha256 !== context.snapshotSha256) {
    // Binding discovery to the imported plan's snapshot is what stops a report
    // produced from a different tree being shown against this decomposition.
    fail("DISCOVERY_SNAPSHOT_MISMATCH", "发现报告与已导入清单的 Snapshot 摘要不一致。");
  }

  const route = capability.routes.find((candidate) => candidate.id === raw.route_id);
  if (!route) fail("DISCOVERY_ROUTE_UNKNOWN", "发现报告引用的路线不在仓库路线契约中。");
  if (route.id !== context.routeId) fail("DISCOVERY_ROUTE_MISMATCH", "发现报告路线与当前选择不一致。");
  if (raw.source_language !== context.sourceLanguage || raw.target_language !== context.targetLanguage) {
    fail("DISCOVERY_LANGUAGE_MISMATCH", "发现报告的源或目标语言与当前选择不一致。");
  }
  if (route.localExecution !== "PASSED") {
    fail(
      "DISCOVERY_ROUTE_LOCAL_PROFILE_NOT_PASSED",
      `路线 ${route.id} 的本地受限 Profile 状态为 ${route.localExecution}，不接受发现报告。`,
    );
  }

  const results = raw.results;
  if (!Array.isArray(results) || results.length === 0 || results.length > MAX_RESULTS) {
    fail("DISCOVERY_RESULTS_INVALID", "results 数组为空或超过上限。");
  }
  if (!Number.isInteger(raw.work_unit_count) || (raw.work_unit_count as number) < results.length) {
    fail("DISCOVERY_WORK_UNIT_COUNT_INVALID", "work_unit_count 小于已判定的结果数。");
  }

  const parsed = results.map((result, index) => parseResult(result, index, route.id));
  const seen = new Set<string>();
  for (const result of parsed) {
    if (seen.has(result.id)) fail("DISCOVERY_RESULT_DUPLICATED", `发现报告重复声明了工作单元 ${result.id}。`);
    seen.add(result.id);
  }

  const counts: Record<string, number> = {};
  for (const result of parsed) counts[result.verdict] = (counts[result.verdict] ?? 0) + 1;
  const readyCount = counts.READY ?? 0;
  if (Number.isInteger(raw.ready_count) && raw.ready_count !== readyCount) {
    fail("DISCOVERY_READY_COUNT_DRIFT", "ready_count 与实际 READY 判定数不一致。");
  }

  return {
    schema_version: "1.0.0",
    kind: "elmos.repository-discovery-report",
    status: "DISCOVERED",
    repository_ref: repositoryRef,
    snapshot_sha256: raw.snapshot_sha256,
    route_id: route.id,
    source_language: context.sourceLanguage,
    target_language: context.targetLanguage,
    profile: "typed-pure-function-v1",
    work_unit_count: raw.work_unit_count as number,
    discovered_count: parsed.length,
    ready_count: readyCount,
    verdict_counts: counts,
    results: parsed,
    execution_status: "NOT_RUN",
    external_verification_status: "NOT_RUN",
    certification_status: "NOT_CERTIFIED",
  };
}

import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import type { FileHandle } from "node:fs/promises";
import path from "node:path";
import { Unzip, UnzipInflate } from "fflate";
import type {
  TranslationConversionReportFile,
  TranslationConversionSummary,
} from "../contracts";

const DEFINITION_ID = "verified-functional-obligation-success-rate/v1";
const COMPARISON_BASIS = "DECLARED_BEHAVIOR_ORACLE";
const JSON_REPORT_PATH = "functional-conversion-report.json";
const MARKDOWN_REPORT_PATH = "FUNCTION_CONVERSION_REPORT.md";
const BUNDLE_REPORT_PATH = "FUNCTION_CONVERSION_REPORT_BUNDLE.zip";
export const BUNDLE_MANIFEST_PATH = "FUNCTION_CONVERSION_REPORT_BUNDLE_MANIFEST.json";
const CODE_ARTIFACT_PATH = "repository-migration-artifact.zip";
const CODE_ARTIFACT_MANIFEST_PATH = "artifact-manifest.json";
const SHARD_DIRECTORY = "functional-conversion-report-shards";
const MAX_OBLIGATIONS_PER_SHARD = 2_000;
const MAX_SHARDS = 5;
const DIGEST_PATTERN = /^[0-9a-f]{64}$/;
const REPORT_ID_PATTERN = /^sha256:[0-9a-f]{64}$/;
const WORK_UNIT_PATTERN = /^WU-[0-9]{5}$/;
const OBLIGATION_PATTERN = /^WU-[0-9]{5}:FO-[0-9]{3,6}$/;
const FUNCTION_STATUSES = ["VERIFIED", "FAILED", "NOT_RUN", "UNSUPPORTED", "UNKNOWN"] as const;
const FAILURE_STAGES = [
  "INVENTORY",
  "ANALYSIS",
  "LOWERING",
  "EMISSION",
  "TARGET_BUILD",
  "SOURCE_BEHAVIOR_REPLAY",
  "BEHAVIOR_REPLAY",
  "ASSEMBLY",
] as const;
export const MAX_FUNCTIONAL_REPORT_BYTES = 64 * 1024 * 1024;
export const MAX_FUNCTIONAL_REPORT_BUNDLE_BYTES = 256 * 1024 * 1024;
const MAX_CODE_ARTIFACT_BYTES = 256 * 1024 * 1024;
const MAX_CODE_ARTIFACT_ENTRIES = 100_000;

type JsonRecord = Record<string, unknown>;

export type ValidatedTranslationConversion = {
  summary: TranslationConversionSummary;
  jsonReport: TranslationConversionReportFile;
  markdownReport: TranslationConversionReportFile;
  reportBundle?: TranslationConversionReportFile;
};

export type TranslationConversionShardDescriptor = {
  sequence: number;
  functionCount: number;
  statusCounts: Record<string, number>;
  firstObligationId: string;
  lastObligationId: string;
  obligationIdsSha256: string;
  json: { path: string; bytes: number; sha256: string };
  markdown: { path: string; bytes: number; sha256: string };
};

export type TranslationConversionBundleFileDescriptor = {
  path: string;
  bytes: number;
  sha256: string;
};

export type ValidatedTranslationPreflight = {
  preflightId: string;
  status: "PASSED" | "PASSED_WITH_INCOMPLETE_INVENTORY" | "REJECTED";
  snapshotSha256: string;
  obligationCount: number;
  reportedObligationLowerBound: number;
  countComplete: boolean;
};

export type TranslationCodeArtifactContext = {
  pipelineStatus: "COMPLETE" | "PARTIAL";
  repositoryRef: string;
  snapshotSha256: string;
  routeId: string;
  profile: string;
  summary: TranslationConversionSummary;
};

export type TranslationCodeArtifactDescriptor = {
  path: "repository-migration-artifact.zip";
  bytes: number;
  sha256: string;
};

function invalid(): never {
  throw new Error("TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID");
}

function invalidArtifact(): never {
  throw new Error("TRANSLATION_ARTIFACT_EVIDENCE_INVALID");
}

function record(value: unknown): JsonRecord {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid();
  return value as JsonRecord;
}

function integer(value: unknown, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): number {
  if (!Number.isSafeInteger(value) || Number(value) < minimum || Number(value) > maximum) invalid();
  return Number(value);
}

function boundedString(value: unknown, maximum: number): string {
  if (typeof value !== "string" || value.length < 1 || value.length > maximum * 2) invalid();
  let length = 0;
  for (const unused of value) {
    void unused;
    length += 1;
    if (length > maximum) invalid();
  }
  return value;
}

function codePointPrefix(value: string, maximum: number): string {
  const result: string[] = [];
  for (const codePoint of value) {
    if (result.length === maximum) break;
    result.push(codePoint);
  }
  return result.join("");
}

function relativePath(value: unknown, maximum = 500): string {
  const candidate = boundedString(value, maximum);
  if (
    candidate.includes("\\")
    || /[\u0000-\u001f\u007f]/u.test(candidate)
    || path.posix.isAbsolute(candidate)
    || candidate.split("/").some((segment) => segment === "" || segment === "." || segment === "..")
  ) invalid();
  return candidate;
}

function reportFile(
  value: unknown,
  expectedPath: TranslationConversionReportFile["path"],
  maximumBytes = MAX_FUNCTIONAL_REPORT_BYTES,
): TranslationConversionReportFile {
  const descriptor = record(value);
  const descriptorPath = relativePath(descriptor.path);
  const bytes = integer(descriptor.bytes, 1, maximumBytes);
  const sha256 = boundedString(descriptor.sha256, 64);
  if (descriptorPath !== expectedPath || !DIGEST_PATTERN.test(sha256)) invalid();
  return { path: expectedPath, bytes, sha256 };
}

function statusCounts(value: unknown, reportedCount: number, numerator: number): Record<string, number> {
  const raw = record(value);
  const entries = Object.entries(raw);
  if (entries.length < 1 || entries.length > 32) invalid();
  const counts: Record<string, number> = {};
  let total = 0;
  for (const [status, countValue] of entries) {
    if (!FUNCTION_STATUSES.includes(status as typeof FUNCTION_STATUSES[number])) invalid();
    const count = integer(countValue, 0, reportedCount);
    counts[status] = count;
    total += count;
  }
  if (total !== reportedCount || (counts.VERIFIED ?? 0) !== numerator) invalid();
  return counts;
}

function failureSummaries(
  value: unknown,
  failedCount: number,
  declaredCount: unknown,
  declaredTotal: unknown,
  truncatedValue: unknown,
): {
  failures: TranslationConversionSummary["failureSummaries"];
  truncated: boolean;
} {
  if (!Array.isArray(value) || value.length > 50) invalid();
  const declared = integer(declaredCount, 0, 50);
  if (declared !== value.length || typeof truncatedValue !== "boolean") invalid();
  if (declaredTotal !== undefined && integer(declaredTotal, 0, 10_000) !== failedCount) invalid();
  const expectedLength = Math.min(failedCount, 50);
  if (value.length !== expectedLength || truncatedValue !== (failedCount > 50)) invalid();

  const seen = new Set<string>();
  const failures = value.map((entryValue) => {
    const entry = record(entryValue);
    const obligationId = boundedString(entry.obligation_id, 64);
    const workUnitId = boundedString(entry.work_unit_id, 32);
    if (
      !OBLIGATION_PATTERN.test(obligationId)
      || !WORK_UNIT_PATTERN.test(workUnitId)
      || !obligationId.startsWith(`${workUnitId}:`)
      || seen.has(obligationId)
    ) invalid();
    seen.add(obligationId);
    const status = boundedString(entry.status, 20);
    const failureCode = boundedString(entry.failure_code, 120);
    if (
      !FUNCTION_STATUSES.includes(status as typeof FUNCTION_STATUSES[number])
      || !/^[A-Z][A-Z0-9_]{2,119}$/.test(failureCode)
    ) invalid();
    const actions = entry.improvement_actions;
    if (
      !Array.isArray(actions)
      || actions.length < 1
      || actions.length > 20
      || !actions.every((action) => {
        try {
          boundedString(action, 600);
          return true;
        } catch {
          return false;
        }
      })
    ) invalid();
    let targetPath: string | undefined;
    if (entry.target_path !== null) targetPath = relativePath(entry.target_path, 1_024);
    return {
      obligationId,
      workUnitId,
      functionDescription: boundedString(entry.function_description, 600),
      sourcePath: relativePath(entry.source_path, 1_024),
      ...(targetPath ? { targetPath } : {}),
      status,
      failureCode,
      failureReason: boundedString(entry.failure_reason, 1_200),
      improvementActions: [...actions] as string[],
    };
  });
  return { failures, truncated: truncatedValue };
}

/**
 * Validate and normalize the fail-closed pipeline measurement. Percentages are
 * recomputed from integer counts; neither rounded display text nor a producer
 * supplied floating-point value is trusted.
 */
export function validateTranslationConversion(
  value: unknown,
  expectedWorkUnitCount: unknown,
): ValidatedTranslationConversion {
  const raw = record(value);
  if (raw.definition_id !== DEFINITION_ID || raw.comparison_basis !== COMPARISON_BASIS) invalid();
  const reportId = boundedString(raw.report_id, 71);
  if (!REPORT_ID_PATTERN.test(reportId)) invalid();
  const storageMode = raw.storage_mode;
  if (storageMode !== "SINGLE" && storageMode !== "SHARDED") invalid();
  const shardCount = integer(raw.shard_count, 0, MAX_SHARDS);
  const totalShardBytes = integer(raw.total_shard_bytes, 0, MAX_FUNCTIONAL_REPORT_BUNDLE_BYTES);
  const casesManifestSha256 = boundedString(raw.cases_manifest_sha256, 64);
  if (!DIGEST_PATTERN.test(casesManifestSha256)) invalid();
  const denominator = integer(raw.denominator, 0, 10_000);
  const reportedObligationCount = integer(raw.reported_obligation_count, 1, 10_000);
  const unknownScopeCount = integer(raw.unknown_scope_count, 0, reportedObligationCount);
  const unreportedObligationCount = integer(raw.unreported_obligation_count, 0);
  const workUnitCount = integer(expectedWorkUnitCount, 1, 5_000);
  const numerator = integer(raw.numerator, 0, denominator);
  const failedCount = integer(raw.failed_count, 0, reportedObligationCount);
  const verifiedCount = integer(raw.verified_count, 0, denominator);
  if (
    raw.measurement_unit !== "FUNCTIONAL_OBLIGATION"
    || reportedObligationCount < workUnitCount
    || denominator > reportedObligationCount
    || unknownScopeCount !== reportedObligationCount - denominator
    || unreportedObligationCount !== 0
    || (storageMode === "SINGLE" && (
      shardCount !== 0
      || totalShardBytes !== 0
      || reportedObligationCount > MAX_OBLIGATIONS_PER_SHARD
    ))
    || (storageMode === "SHARDED" && (
      shardCount < 2
      || totalShardBytes < 1
      || reportedObligationCount <= MAX_OBLIGATIONS_PER_SHARD
      || shardCount !== Math.ceil(reportedObligationCount / MAX_OBLIGATIONS_PER_SHARD)
    ))
    || verifiedCount !== numerator
    || failedCount !== reportedObligationCount - numerator
    || raw.exact_fraction !== `${numerator}/${denominator}`
  ) invalid();

  const basisPoints = integer(raw.success_rate_basis_points, 0, 10_000);
  const expectedBasisPoints = denominator > 0
    ? Math.floor((numerator * 10_000) / denominator)
    : 0;
  const expectedDisplay = `${(expectedBasisPoints / 100).toFixed(2)}%`;
  const scopeIsComplete = unknownScopeCount === 0 && unreportedObligationCount === 0;
  const expectedLowerBound = scopeIsComplete ? expectedBasisPoints : 0;
  const expectedUpperBound = scopeIsComplete ? expectedBasisPoints : 10_000;
  const expectedProjectDisplay = scopeIsComplete
    ? expectedDisplay
    : `${(expectedLowerBound / 100).toFixed(2)}%–${(expectedUpperBound / 100).toFixed(2)}% (INDETERMINATE)`;
  const lowerBound = integer(raw.project_success_rate_lower_bound_basis_points, 0, 10_000);
  const upperBound = integer(raw.project_success_rate_upper_bound_basis_points, lowerBound, 10_000);
  if (basisPoints !== expectedBasisPoints || raw.display_percent !== expectedDisplay) invalid();
  if (
    lowerBound !== expectedLowerBound
    || upperBound !== expectedUpperBound
    || raw.project_success_rate_display !== expectedProjectDisplay
  ) invalid();
  const denominatorComplete = raw.denominator_complete;
  const measurementStatus = raw.measurement_status;
  if (
    typeof denominatorComplete !== "boolean"
    || (measurementStatus !== "MEASURED" && measurementStatus !== "INDETERMINATE")
    || (denominatorComplete && measurementStatus !== "MEASURED")
    || (!denominatorComplete && measurementStatus !== "INDETERMINATE")
    || denominatorComplete !== scopeIsComplete
    || typeof raw.code_artifact_ready !== "boolean"
  ) invalid();

  const counts = statusCounts(raw.status_counts, reportedObligationCount, numerator);
  const { failures, truncated } = failureSummaries(
    raw.failure_summaries,
    failedCount,
    raw.failure_summary_count,
    raw.total_failure_count,
    raw.failure_summaries_truncated,
  );
  const jsonReport = reportFile(raw.json_report, JSON_REPORT_PATH);
  const markdownReport = reportFile(raw.markdown_report, MARKDOWN_REPORT_PATH);
  return {
    summary: {
      reportId,
      definitionId: DEFINITION_ID,
      measurementUnit: "FUNCTIONAL_OBLIGATION",
      comparisonBasis: COMPARISON_BASIS,
      storageMode,
      shardCount,
      totalShardBytes,
      casesManifestSha256,
      numerator,
      denominator,
      reportedObligationCount,
      unknownScopeCount,
      unreportedObligationCount,
      unsuccessfulCount: failedCount,
      exactFraction: `${numerator}/${denominator}`,
      successRateBasisPoints: basisPoints,
      displayPercent: expectedDisplay,
      projectSuccessRateLowerBoundBasisPoints: lowerBound,
      projectSuccessRateUpperBoundBasisPoints: upperBound,
      projectSuccessRateDisplay: expectedProjectDisplay,
      measurementStatus,
      denominatorComplete,
      verifiedCount,
      failedCount,
      codeArtifactReady: raw.code_artifact_ready,
      statusCounts: counts,
      failureSummaries: failures,
      failureSummariesTruncated: truncated,
    },
    jsonReport,
    markdownReport,
    ...(storageMode === "SHARDED"
      ? {
          reportBundle: reportFile(
            raw.report_bundle,
            BUNDLE_REPORT_PATH,
            MAX_FUNCTIONAL_REPORT_BUNDLE_BYTES,
          ),
        }
      : raw.report_bundle === undefined ? {} : invalid()),
  };
}

export function validateTranslationPreflight(
  value: unknown,
  expected: {
    repositoryRef: string;
    routeId: string;
    sourceLanguage: string;
    targetLanguage: string;
  },
): ValidatedTranslationPreflight {
  const report = record(value);
  const requiredFields = [
    "schema_version", "kind", "preflight_id", "status", "reason_code",
    "repository_ref", "snapshot_sha256", "route_id", "source_language", "target_language",
    "obligation_count", "reported_obligation_lower_bound", "obligation_count_semantics",
    "actual_obligation_count", "actual_obligation_count_status", "obligation_limit",
    "count_complete", "execution_status", "certification_status",
  ].sort();
  if (
    Object.keys(report).sort().join("\u0000") !== requiredFields.join("\u0000")
    || report.schema_version !== "1.0.0"
    || report.kind !== "elmos.repository-conversion-preflight"
    || report.repository_ref !== expected.repositoryRef
    || report.route_id !== expected.routeId
    || report.source_language !== expected.sourceLanguage
    || report.target_language !== expected.targetLanguage
    || report.obligation_limit !== 10_000
    || report.execution_status !== "NOT_RUN"
    || report.certification_status !== "NOT_CERTIFIED"
  ) invalid();
  const preflightId = boundedString(report.preflight_id, 71);
  const snapshotSha256 = boundedString(report.snapshot_sha256, 64);
  const obligationCount = integer(report.obligation_count, 0, 10_001);
  const reportedObligationLowerBound = integer(report.reported_obligation_lower_bound, 0, 10_001);
  if (
    !REPORT_ID_PATTERN.test(preflightId)
    || !DIGEST_PATTERN.test(snapshotSha256)
    || reportedObligationLowerBound !== obligationCount
  ) invalid();
  const identity = Object.fromEntries(
    Object.entries(report).filter(([key]) => key !== "preflight_id"),
  );
  const expectedIdentity = `sha256:${createHash("sha256")
    .update(pythonCanonicalJson(identity), "utf8")
    .digest("hex")}`;
  if (preflightId !== expectedIdentity) invalid();
  const status = report.status;
  if (status === "PASSED") {
    if (
      obligationCount > 10_000
      || report.reason_code !== null
      || report.obligation_count_semantics !== "EXACT_REPORTED_ROWS"
      || integer(report.actual_obligation_count, 0, 10_000) > obligationCount
      || report.actual_obligation_count_status !== "EXACT"
      || report.count_complete !== true
    ) invalid();
  } else if (status === "PASSED_WITH_INCOMPLETE_INVENTORY") {
    if (
      obligationCount > 10_000
      || report.reason_code !== null
      || report.obligation_count_semantics !== "REPORTED_ROW_LOWER_BOUND"
      || report.actual_obligation_count !== null
      || report.actual_obligation_count_status !== "UNKNOWN"
      || report.count_complete !== false
    ) invalid();
  } else if (status === "REJECTED") {
    if (
      obligationCount !== 10_001
      || report.reason_code !== "FUNCTIONAL_OBLIGATION_LIMIT_EXCEEDED"
      || report.obligation_count_semantics !== "REPORTED_ROW_LOWER_BOUND"
      || report.actual_obligation_count !== null
      || report.actual_obligation_count_status !== "UNKNOWN"
      || report.count_complete !== false
    ) invalid();
  } else invalid();
  return {
    preflightId,
    status,
    snapshotSha256,
    obligationCount,
    reportedObligationLowerBound,
    countComplete: report.count_complete,
  };
}

type ConversionDocumentContext = {
  pipelineStatus: "COMPLETE" | "PARTIAL" | "BLOCKED";
  repositoryRef: string;
  snapshotSha256: string;
  routeId: string;
  sourceLanguage: string;
  targetLanguage: string;
  profile: string;
  buildStatus: string;
  buildReason: string | null;
  markdownSha256: string;
  casesManifestSha256: string;
};

function stringArray(value: unknown, maximumItems: number, maximumLength: number): string[] {
  if (!Array.isArray(value) || value.length > maximumItems) invalid();
  return value.map((item) => boundedString(item, maximumLength));
}

function sameCounts(left: Record<string, number>, rightValue: unknown): boolean {
  const right = record(rightValue);
  const leftKeys = Object.keys(left).sort();
  const rightKeys = Object.keys(right).sort();
  return leftKeys.length === rightKeys.length
    && leftKeys.every((key, index) => (
      key === rightKeys[index] && right[key] === left[key]
    ));
}

function codeBlock(
  value: unknown,
  obligationId: string,
  direction: "SOURCE" | "TARGET",
  expectedLanguage: string,
): JsonRecord {
  const block = record(value);
  const blockId = boundedString(block.block_id, 96);
  if (blockId !== `${obligationId}:${direction}-001` || block.language !== expectedLanguage) invalid();
  relativePath(block.path, 1_024);
  const documentBytes = integer(block.document_bytes, 0, 64 * 1024 * 1024);
  const documentSha256 = boundedString(block.document_sha256, 64);
  const blockSha256 = boundedString(block.block_sha256, 64);
  if (!DIGEST_PATTERN.test(documentSha256) || !DIGEST_PATTERN.test(blockSha256)) invalid();
  if (block.symbol_id !== null) boundedString(block.symbol_id, 200);
  if (typeof block.truncated !== "boolean") invalid();
  const extractionMethod = String(block.extraction_method);
  if (![
    "PYTHON_AST_FUNCTION",
    "NAME_ANCHORED_DOCUMENT_EXCERPT",
    "DOCUMENT_PREFIX_EXCERPT",
  ].includes(extractionMethod)) invalid();
  const range = record(block.range);
  const startByte = integer(range.start_byte, 0, documentBytes);
  const endByte = integer(range.end_byte, startByte, documentBytes);
  const startLine = integer(range.start_line, 1, 10_000_000);
  const endLine = integer(range.end_line, startLine, 10_000_000);
  integer(range.start_column, 1, 10_000_000);
  integer(range.end_column, 1, 10_000_000);
  if (block.snippet === null) {
    if (
      block.truncated !== true
      || typeof block.omission_reason !== "string"
    ) invalid();
    boundedString(block.omission_reason, 120);
    return block;
  }
  if (
    typeof block.snippet !== "string"
    || block.omission_reason !== null
  ) invalid();
  const snippetBytes = Buffer.byteLength(block.snippet, "utf8");
  if (snippetBytes > 4 * 1024 || snippetBytes > endByte - startByte) invalid();
  if (!block.truncated && (
    endByte - startByte !== snippetBytes
    || blockSha256 !== createHash("sha256").update(block.snippet, "utf8").digest("hex")
  )) invalid();
  return block;
}

function blockMappingPrecision(block: JsonRecord | undefined): number {
  if (!block) return 0;
  if (block.extraction_method === "PYTHON_AST_FUNCTION") return 1;
  if (block.extraction_method === "NAME_ANCHORED_DOCUMENT_EXCERPT") return 0.7;
  return 0;
}

function improvementMethods(value: unknown, obligationId: string): string[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 20) invalid();
  return value.map((actionValue, index) => {
    const action = record(actionValue);
    if (
      action.action_id !== `${obligationId}:ACTION-${String(index + 1).padStart(3, "0")}`
      || !["P0", "P1", "P2"].includes(String(action.priority))
      || !["AUTOMATIC", "ASSISTED", "MANUAL"].includes(String(action.automation))
    ) invalid();
    const verificationSteps = stringArray(action.verification_steps, 20, 500);
    if (verificationSteps.length < 1) invalid();
    return boundedString(action.method, 2_000);
  });
}

function pythonCanonicalJson(value: unknown, parentKey?: string): string {
  if (value === null) return "null";
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) invalid();
    if (parentKey === "confidence" && Number.isInteger(value)) return `${value}.0`;
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => pythonCanonicalJson(item)).join(",")}]`;
  }
  const object = record(value);
  return `{${Object.keys(object).sort().map((key) => (
    `${JSON.stringify(key)}:${pythonCanonicalJson(object[key], key)}`
  )).join(",")}}`;
}

export function functionalConversionReportId(value: unknown): string {
  const report = record(value);
  const identity: JsonRecord = {};
  const excluded = new Set([
    "report_id",
    "markdown_sha256",
    "code_artifact_ready",
    "storage_mode",
    "shard_count",
    "total_shard_bytes",
    "shards",
  ]);
  for (const [key, item] of Object.entries(report)) {
    if (!excluded.has(key)) identity[key] = item;
  }
  return `sha256:${createHash("sha256").update(pythonCanonicalJson(identity), "utf8").digest("hex")}`;
}

function markdownPlain(value: unknown): string {
  let text = String(value ?? "").replace(/[\u0000-\u001f\u007f]/gu, " ");
  for (const [source, replacement] of [
    ["!", "！"], ["[", "［"], ["]", "］"], ["(", "（"], [")", "）"],
    ["<", "＜"], [">", "＞"], ["&", "＆"],
  ]) text = text.replaceAll(source, replacement);
  return text;
}

function fenced(snippet: string, language: string): string {
  let maximumRun = 0;
  for (const match of snippet.matchAll(/`+/gu)) maximumRun = Math.max(maximumRun, match[0].length);
  const fence = "`".repeat(Math.max(3, maximumRun + 1));
  return `${fence}${language}\n${snippet}\n${fence}`;
}

function renderedBlock(value: unknown, language: string, absent: string): string {
  if (value === null || value === undefined) return fenced(absent, language);
  const block = record(value);
  if (typeof block.snippet !== "string") {
    return fenced(`NOT_EMBEDDED: ${String(block.omission_reason || "NOT_EMBEDDED")}`, language);
  }
  return fenced(block.snippet, language);
}

function renderedBlockMetadata(value: unknown, absent: string): string[] {
  if (value === null || value === undefined) return [`- 状态：\`${markdownPlain(absent)}\``];
  const block = record(value);
  const range = record(block.range);
  const method = String(block.extraction_method);
  const precision = method === "PYTHON_AST_FUNCTION"
    ? "EXACT_DECLARATION_RANGE"
    : method === "NAME_ANCHORED_DOCUMENT_EXCERPT"
      ? "APPROXIMATE_NAME_ANCHORED_RANGE"
      : "UNMAPPED_DOCUMENT_RANGE";
  return [
    `- 路径：\`${markdownPlain(block.path)}\``,
    `- 字节范围：\`${String(range.start_byte)}..${String(range.end_byte)}\`；行列范围：\`${String(range.start_line)}:${String(range.start_column)}..${String(range.end_line)}:${String(range.end_column)}\``,
    `- 代码块 SHA-256：\`${String(block.block_sha256)}\``,
    `- 文档 SHA-256：\`${String(block.document_sha256)}\``,
    `- 提取方式：\`${markdownPlain(block.extraction_method)}\``,
    `- 范围精度：\`${precision}\``,
  ];
}

function renderConversionMarkdown(value: unknown, shardHeading?: string): string {
  const report = record(value);
  const metric = record(report.metric);
  const route = record(report.route);
  const sourceLanguage = String(route.source_language);
  const targetLanguage = String(route.target_language);
  const lines = ["# 项目语言功能转换报告", ""];
  if (shardHeading) lines.push(`> ${markdownPlain(shardHeading)}`, "");
  lines.push(
    "## 转换总览",
    "",
    `- 路由：\`${markdownPlain(route.route_id)}\``,
    `- 原语言：\`${sourceLanguage}\`；目标语言：\`${targetLanguage}\``,
    `- 报告状态：\`${String(report.status)}\``,
    `- 代码工件可交付：\`${String(report.code_artifact_ready).toLowerCase()}\``,
    `- 已验证功能：\`${String(metric.numerator)}\`；已报告可调用功能：\`${String(metric.denominator)}\``,
  );
  if (Number(metric.denominator)) {
    lines.push(`- 功能转换成功率：\`${String(metric.exact_fraction)} = ${String(metric.display_percent)}\``);
  } else {
    lines.push("- 已报告可调用功能成功率：N/A (NO_REPORTED_CALLABLE_DENOMINATOR)");
  }
  lines.push(
    `- 项目成功率：\`${String(metric.project_success_rate_display)}\``,
    `- 分母是否完整：\`${String(metric.denominator_complete).toLowerCase()}\``,
    "",
    "## 证据边界",
    "",
    "本报告的比较基础为 DECLARED_BEHAVIOR_ORACLE；源/目标运行时等价仍为 NOT_RUN。",
    "独立验证与外部认证保持 NOT_RUN / NOT_CERTIFIED。",
    "",
    "## 逐功能转换结果",
    "",
  );
  const functions = report.functions;
  if (!Array.isArray(functions)) invalid();
  for (const valueForFunction of functions) {
    const item = record(valueForFunction);
    const description = record(item.functional_description);
    const sourceBlocks = item.source_blocks;
    const targetBlocks = item.target_blocks;
    if (!Array.isArray(sourceBlocks) || !Array.isArray(targetBlocks)) invalid();
    const sourceBlock = sourceBlocks[0];
    const targetBlock = targetBlocks[0];
    lines.push(
      `### ${markdownPlain(item.obligation_id)} — ${markdownPlain(item.status)}`,
      "",
      `功能描述：${markdownPlain(description.text)}`,
      "",
      "原代码块：",
      "",
      ...renderedBlockMetadata(sourceBlock, "SOURCE_NOT_AVAILABLE"),
      "",
      renderedBlock(sourceBlock, sourceLanguage, "SOURCE_NOT_AVAILABLE"),
      "",
      "目标代码块：",
      "",
      ...renderedBlockMetadata(targetBlock, "NOT_GENERATED"),
      "",
      renderedBlock(targetBlock, targetLanguage, "NOT_GENERATED"),
      "",
      `映射置信度：\`${Number(record(item.mapping).confidence).toFixed(2)}\`（\`${
        Number(record(item.mapping).confidence) === 1
          ? "EXACT"
          : Number(record(item.mapping).confidence) > 0
            ? "APPROXIMATE"
            : "UNMAPPED"
      }\`）`,
      "",
    );
    if (item.failure !== null) {
      const failure = record(item.failure);
      lines.push(
        `失败阶段：\`${markdownPlain(failure.stage)}\``,
        `失败代码：\`${markdownPlain(failure.reason_code)}\``,
        `未成功原因：${markdownPlain(failure.description)}`,
        "",
        "后续提高成功率的方法：",
        "",
      );
      if (!Array.isArray(item.improvement_actions)) invalid();
      for (const valueForAction of item.improvement_actions) {
        lines.push(`1. ${markdownPlain(record(valueForAction).method)}`);
      }
      lines.push("");
    }
  }
  return `${lines.join("\n").trimEnd()}\n`;
}

function renderIndexMarkdown(value: unknown): string {
  const index = record(value);
  const metric = record(index.metric);
  const lines = [
    "# 项目语言功能转换报告（分片索引）",
    "",
    "## 转换总览",
    "",
    `- 报告 ID：\`${String(index.report_id)}\``,
    `- 路由：\`${String(record(index.route).route_id)}\``,
    `- 功能转换成功率：\`${String(metric.exact_fraction)} = ${String(metric.display_percent)}\``,
    `- 项目成功率：\`${String(metric.project_success_rate_display)}\``,
    `- 代码工件可交付：\`${String(index.code_artifact_ready).toLowerCase()}\``,
    `- 功能总数：\`${String(metric.reported_obligation_count)}\``,
    `- 分片数：\`${String(index.shard_count)}\``,
    `- 分片文件总字节：\`${String(index.total_shard_bytes)}\``,
    "",
    "## 分片目录",
    "",
  ];
  if (!Array.isArray(index.shards)) invalid();
  for (const valueForShard of index.shards) {
    const shard = record(valueForShard);
    const json = record(shard.json);
    const markdown = record(shard.markdown);
    lines.push(
      `### 分片 ${String(integer(shard.sequence, 1, MAX_SHARDS)).padStart(5, "0")}`,
      "",
      `- 功能数：\`${String(shard.function_count)}\``,
      `- 义务 ID 摘要：\`${String(shard.obligation_ids_sha256)}\``,
      `- JSON：\`${String(json.path)}\` (\`${String(json.sha256)}\`)`,
      `- Markdown：\`${String(markdown.path)}\` (\`${String(markdown.sha256)}\`)`,
      "",
    );
  }
  lines.push(
    "## 证据边界",
    "",
    "所有指标均由上述全部分片重新聚合；容量分片不制造 UNKNOWN，也不缩减分母。",
    "源/目标运行时等价仍为 NOT_RUN；独立验证与外部认证保持 NOT_RUN / NOT_CERTIFIED。",
    "",
  );
  return lines.join("\n");
}

export function validateTranslationConversionMarkdown(
  reportValue: unknown,
  markdownBytes: Uint8Array,
  shardHeading?: string,
): void {
  const report = record(reportValue);
  const rendered = report.kind === "elmos.project-language-conversion-report-index"
    ? renderIndexMarkdown(report)
    : renderConversionMarkdown(report, shardHeading);
  const renderedBytes = Buffer.from(rendered, "utf8");
  if (
    renderedBytes.byteLength !== markdownBytes.byteLength
    || !renderedBytes.equals(Buffer.from(markdownBytes))
    || report.markdown_sha256 !== createHash("sha256").update(renderedBytes).digest("hex")
  ) invalid();
}

/**
 * Cross-check the complete content-addressed JSON report before exposing its
 * small polling summary. This prevents a valid digest from authenticating a
 * structurally incomplete comparison document or a summary with altered
 * counts, reasons, blocks, or remediation methods.
 */
export function validateTranslationConversionDocument(
  value: unknown,
  expected: ConversionDocumentContext,
  summary: TranslationConversionSummary,
): void {
  const report = record(value);
  const repository = record(report.repository);
  const route = record(report.route);
  const metric = record(report.metric);
  const build = record(report.build_verification);
  const boundary = record(report.evidence_boundary);
  if (!Array.isArray(report.exclusions) || report.exclusions.length !== 0) invalid();
  const blockers = stringArray(report.blockers, 10_000, 120);
  if (
    report.schema_version !== "1.0.0"
    || report.kind !== "elmos.project-language-conversion-report"
    || report.markdown_renderer_version !== "elmos-functional-conversion-markdown/v1"
    || report.markdown_sha256 !== expected.markdownSha256
    || report.status !== expected.pipelineStatus
    || repository.reference !== expected.repositoryRef
    || repository.snapshot_sha256 !== expected.snapshotSha256
    || route.route_id !== expected.routeId
    || route.source_language !== expected.sourceLanguage
    || route.target_language !== expected.targetLanguage
    || route.profile !== expected.profile
    || report.report_id !== summary.reportId
    || report.report_id !== functionalConversionReportId(report)
    || report.code_artifact_ready !== summary.codeArtifactReady
    || metric.definition_id !== summary.definitionId
    || metric.measurement_unit !== summary.measurementUnit
    || metric.comparison_basis !== summary.comparisonBasis
    || metric.numerator !== summary.numerator
    || metric.denominator !== summary.denominator
    || metric.reported_obligation_count !== summary.reportedObligationCount
    || metric.unknown_scope_count !== summary.unknownScopeCount
    || metric.unreported_obligation_count !== summary.unreportedObligationCount
    || metric.exact_fraction !== summary.exactFraction
    || metric.success_rate_basis_points !== summary.successRateBasisPoints
    || metric.display_percent !== summary.displayPercent
    || metric.project_success_rate_lower_bound_basis_points !== summary.projectSuccessRateLowerBoundBasisPoints
    || metric.project_success_rate_upper_bound_basis_points !== summary.projectSuccessRateUpperBoundBasisPoints
    || metric.project_success_rate_display !== summary.projectSuccessRateDisplay
    || metric.measurement_status !== summary.measurementStatus
    || metric.denominator_complete !== summary.denominatorComplete
    || build.status !== expected.buildStatus
    || build.reason !== expected.buildReason
    || report.certification_status !== "NOT_CERTIFIED"
    || boundary.local_target_build !== expected.buildStatus
    || boundary.target_behavior_oracle !== (
      summary.numerator > 0 ? "PASSED_PER_VERIFIED_FUNCTION" : "NOT_RUN"
    )
    || boundary.source_target_declared_case_equivalence !== (
      summary.numerator > 0 ? "PASSED_PER_VERIFIED_FUNCTION" : "NOT_RUN"
    )
    || boundary.source_target_runtime_equivalence !== "NOT_RUN"
    || boundary.independent_verification !== "NOT_RUN"
    || boundary.external_verification !== "NOT_RUN"
    || boundary.cases_manifest_sha256 !== expected.casesManifestSha256
    || !sameCounts(summary.statusCounts, report.status_counts)
  ) invalid();
  const expectedFormula = summary.denominatorComplete
    ? "VERIFIED functional obligations / compiler-completely inventoried functional obligations"
    : "Reported VERIFIED obligations / reported known callable obligations; project rate remains indeterminate because inventory-unknown or capacity-unreported functional scope remains";
  if (metric.formula !== expectedFormula) invalid();

  const functions = report.functions;
  if (!Array.isArray(functions) || functions.length !== summary.reportedObligationCount) invalid();
  const seen = new Set<string>();
  const observedCounts: Record<string, number> = {};
  let observedCallableCount = 0;
  let observedUnknownScopeCount = 0;
  const observedFailures: Array<{
    obligationId: string;
    workUnitId: string;
    description: string;
    sourcePath: string;
    targetPath?: string;
    status: string;
    code: string;
    reason: string;
    methods: string[];
  }> = [];

  for (const functionValue of functions) {
    const item = record(functionValue);
    const obligationId = boundedString(item.obligation_id, 64);
    const workUnitId = boundedString(item.work_unit_id, 32);
    const status = boundedString(item.status, 20);
    const kind = boundedString(item.kind, 100);
    if (
      !OBLIGATION_PATTERN.test(obligationId)
      || !WORK_UNIT_PATTERN.test(workUnitId)
      || !obligationId.startsWith(`${workUnitId}:`)
      || seen.has(obligationId)
      || !["CALLABLE", "UNKNOWN_SOURCE_UNIT"].includes(kind)
      || !FUNCTION_STATUSES.includes(status as typeof FUNCTION_STATUSES[number])
    ) invalid();
    if (kind === "CALLABLE") observedCallableCount += 1;
    else observedUnknownScopeCount += 1;
    seen.add(obligationId);
    observedCounts[status] = (observedCounts[status] ?? 0) + 1;
    const description = record(item.functional_description);
    const descriptionText = boundedString(description.text, 1_000);
    if (
      (kind === "CALLABLE" && ![
        "AST_SIGNATURE_DERIVED",
        "IR_SIGNATURE_DERIVED",
        "NAME_DERIVED",
      ].includes(String(description.source)))
      || (kind === "UNKNOWN_SOURCE_UNIT" && description.source !== "UNKNOWN")
      || (kind === "UNKNOWN_SOURCE_UNIT" && status !== "UNKNOWN")
    ) invalid();
    if (!Array.isArray(item.source_blocks) || item.source_blocks.length !== 1) invalid();
    const sourceBlocks = item.source_blocks.map((block) => (
      codeBlock(block, obligationId, "SOURCE", expected.sourceLanguage)
    ));
    if (!Array.isArray(item.target_blocks) || item.target_blocks.length > 1) invalid();
    const targetBlocks = item.target_blocks.map((block) => (
      codeBlock(block, obligationId, "TARGET", expected.targetLanguage)
    ));
    const sourceIds = sourceBlocks.map((block) => String(block.block_id));
    const targetIds = targetBlocks.map((block) => String(block.block_id));
    const mapping = record(item.mapping);
    const confidence = mapping.confidence;
    const expectedConfidence = targetBlocks[0]
      ? Math.min(blockMappingPrecision(sourceBlocks[0]), blockMappingPrecision(targetBlocks[0]))
      : 0;
    const provenanceRefs = stringArray(mapping.provenance_refs, 10, 500);
    const evidenceRefs = stringArray(item.evidence_refs, 20, 500);
    if (
      mapping.mapping_id !== `${obligationId}:MAP-001`
      || !["SYNTHESIZED", "UNMAPPED"].includes(String(mapping.kind))
      || mapping.freshness !== "FRESH"
      || typeof confidence !== "number"
      || !Number.isFinite(confidence)
      || confidence !== expectedConfidence
      || JSON.stringify(mapping.source_block_ids) !== JSON.stringify(sourceIds)
      || JSON.stringify(mapping.target_block_ids) !== JSON.stringify(targetIds)
      || (targetBlocks.length > 0 && mapping.kind !== "SYNTHESIZED")
      || (targetBlocks.length === 0 && (mapping.kind !== "UNMAPPED" || confidence !== 0))
    ) invalid();
    if (
      evidenceRefs.length < 1
      || JSON.stringify(provenanceRefs) !== JSON.stringify([evidenceRefs[0]])
    ) invalid();
    provenanceRefs.forEach((reference) => relativePath(reference, 500));
    evidenceRefs.forEach((reference) => relativePath(reference, 500));

    if (status === "VERIFIED") {
      if (
        kind !== "CALLABLE"
        || targetBlocks.length < 1
        || item.failure !== null
        || !Array.isArray(item.improvement_actions)
        || item.improvement_actions.length !== 0
      ) invalid();
      continue;
    }
    const failure = record(item.failure);
    const stage = boundedString(failure.stage, 20);
    const code = boundedString(failure.reason_code, 120);
    const reason = boundedString(failure.description, 2_000);
    if (
      !FAILURE_STAGES.includes(stage as typeof FAILURE_STAGES[number])
      || !/^[A-Z][A-Z0-9_]{2,119}$/.test(code)
    ) invalid();
    if (targetBlocks.length === 0 && failure.target_absence_reason !== "NOT_GENERATED") invalid();
    if (targetBlocks.length > 0 && failure.target_absence_reason !== null) invalid();
    const methods = improvementMethods(item.improvement_actions, obligationId);
    observedFailures.push({
      obligationId,
      workUnitId,
      description: descriptionText,
      sourcePath: String(sourceBlocks[0].path),
      ...(targetBlocks[0] ? { targetPath: String(targetBlocks[0].path) } : {}),
      status,
      code,
      reason,
      methods,
    });
  }
  if (
    !sameCounts(observedCounts, summary.statusCounts)
    || (observedCounts.VERIFIED ?? 0) !== summary.numerator
    || observedCallableCount !== summary.denominator
    || observedUnknownScopeCount !== summary.unknownScopeCount
    || summary.unreportedObligationCount !== 0
    || observedCallableCount + observedUnknownScopeCount !== summary.reportedObligationCount
    || observedFailures.length !== summary.failedCount
    || JSON.stringify(blockers) !== JSON.stringify(observedFailures.map((failure) => failure.code))
    || (summary.codeArtifactReady && !(expected.buildStatus === "PASSED" && summary.numerator > 0))
  ) invalid();
  const expectedSummaries = observedFailures.slice(0, 50);
  if (expectedSummaries.length !== summary.failureSummaries.length) invalid();
  for (let index = 0; index < expectedSummaries.length; index += 1) {
    const expectedFailure = expectedSummaries[index];
    const actual = summary.failureSummaries[index];
    if (
      actual.obligationId !== expectedFailure.obligationId
      || actual.workUnitId !== expectedFailure.workUnitId
      || actual.functionDescription !== codePointPrefix(expectedFailure.description, 600)
      || actual.sourcePath !== expectedFailure.sourcePath
      || actual.targetPath !== expectedFailure.targetPath
      || actual.status !== expectedFailure.status
      || actual.failureCode !== expectedFailure.code
      || actual.failureReason !== codePointPrefix(expectedFailure.reason, 1_200)
      || JSON.stringify(actual.improvementActions) !== JSON.stringify(
        expectedFailure.methods.map((method) => codePointPrefix(method, 600)),
      )
    ) invalid();
  }
}

function deepJsonEqual(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left)
      && Array.isArray(right)
      && left.length === right.length
      && left.every((item, index) => deepJsonEqual(item, right[index]));
  }
  if (
    left === null || right === null
    || typeof left !== "object" || typeof right !== "object"
  ) return false;
  const leftRecord = left as JsonRecord;
  const rightRecord = right as JsonRecord;
  const leftKeys = Object.keys(leftRecord).sort();
  const rightKeys = Object.keys(rightRecord).sort();
  return leftKeys.length === rightKeys.length
    && leftKeys.every((key, index) => (
      key === rightKeys[index] && deepJsonEqual(leftRecord[key], rightRecord[key])
    ));
}

function arbitraryReportFile(
  value: unknown,
  expectedPath: string,
): TranslationConversionBundleFileDescriptor {
  const descriptor = record(value);
  const descriptorPath = relativePath(descriptor.path, 1_024);
  const bytes = integer(descriptor.bytes, 1, MAX_FUNCTIONAL_REPORT_BYTES);
  const sha256 = boundedString(descriptor.sha256, 64);
  if (descriptorPath !== expectedPath || !DIGEST_PATTERN.test(sha256)) invalid();
  return { path: descriptorPath, bytes, sha256 };
}

function localStatusCounts(value: unknown, functionCount: number): Record<string, number> {
  const raw = record(value);
  const verified = raw.VERIFIED === undefined ? 0 : integer(raw.VERIFIED, 0, functionCount);
  return statusCounts(raw, functionCount, verified);
}

/**
 * Validate a sharded root index far enough to safely resolve its bounded,
 * content-addressed child files. Report readiness still requires the later
 * full shard-set and ZIP-bundle validation.
 */
export function validateTranslationConversionIndex(
  value: unknown,
  expected: ConversionDocumentContext,
  summary: TranslationConversionSummary,
): TranslationConversionShardDescriptor[] {
  if (summary.storageMode !== "SHARDED") invalid();
  const index = record(value);
  if (
    index.schema_version !== "1.0.0"
    || index.kind !== "elmos.project-language-conversion-report-index"
    || index.report_id !== summary.reportId
    || index.status !== expected.pipelineStatus
    || index.storage_mode !== "SHARDED"
    || index.shard_count !== summary.shardCount
    || index.total_shard_bytes !== summary.totalShardBytes
    || index.markdown_renderer_version !== "elmos-functional-conversion-markdown/v1"
    || index.markdown_sha256 !== expected.markdownSha256
    || index.code_artifact_ready !== summary.codeArtifactReady
    || index.functions !== undefined
  ) invalid();
  const rawShards = index.shards;
  if (!Array.isArray(rawShards) || rawShards.length !== summary.shardCount) invalid();
  const seenPaths = new Set<string>();
  let observedFunctions = 0;
  let observedBytes = 0;
  const aggregateCounts: Record<string, number> = {};
  const descriptors = rawShards.map((valueForShard, offset) => {
    const shard = record(valueForShard);
    const sequence = integer(shard.sequence, 1, MAX_SHARDS);
    if (sequence !== offset + 1) invalid();
    const expectedFunctionCount = sequence < summary.shardCount
      ? MAX_OBLIGATIONS_PER_SHARD
      : summary.reportedObligationCount - MAX_OBLIGATIONS_PER_SHARD * (sequence - 1);
    const functionCount = integer(shard.function_count, 1, MAX_OBLIGATIONS_PER_SHARD);
    if (functionCount !== expectedFunctionCount) invalid();
    const counts = localStatusCounts(shard.status_counts, functionCount);
    const firstObligationId = boundedString(shard.first_obligation_id, 64);
    const lastObligationId = boundedString(shard.last_obligation_id, 64);
    const obligationIdsSha256 = boundedString(shard.obligation_ids_sha256, 64);
    if (
      !OBLIGATION_PATTERN.test(firstObligationId)
      || !OBLIGATION_PATTERN.test(lastObligationId)
      || !DIGEST_PATTERN.test(obligationIdsSha256)
    ) invalid();
    const basename = `report-${String(sequence).padStart(5, "0")}`;
    const json = arbitraryReportFile(shard.json, `${SHARD_DIRECTORY}/${basename}.json`);
    const markdown = arbitraryReportFile(shard.markdown, `${SHARD_DIRECTORY}/${basename}.md`);
    for (const descriptor of [json, markdown]) {
      if (seenPaths.has(descriptor.path)) invalid();
      seenPaths.add(descriptor.path);
      observedBytes += descriptor.bytes;
    }
    observedFunctions += functionCount;
    for (const [status, count] of Object.entries(counts)) {
      aggregateCounts[status] = (aggregateCounts[status] ?? 0) + count;
    }
    return {
      sequence,
      functionCount,
      statusCounts: counts,
      firstObligationId,
      lastObligationId,
      obligationIdsSha256,
      json,
      markdown,
    };
  });
  if (
    observedFunctions !== summary.reportedObligationCount
    || observedBytes !== summary.totalShardBytes
    || !sameCounts(summary.statusCounts, aggregateCounts)
  ) invalid();
  return descriptors;
}

const SHARD_COMMON_FIELDS = [
  "schema_version",
  "report_id",
  "status",
  "repository",
  "route",
  "metric",
  "status_counts",
  "code_artifact_ready",
  "build_verification",
  "evidence_boundary",
  "markdown_renderer_version",
  "certification_status",
] as const;

/** Deeply validate every shard and then reconstruct the complete ordered report. */
export function validateTranslationConversionShardDocuments(
  indexValue: unknown,
  shardValues: unknown[],
  expected: ConversionDocumentContext,
  summary: TranslationConversionSummary,
  descriptors: TranslationConversionShardDescriptor[],
): void {
  const index = record(indexValue);
  if (
    shardValues.length !== descriptors.length
    || descriptors.length !== summary.shardCount
  ) invalid();
  const allFunctions: unknown[] = [];
  const seenObligations = new Set<string>();

  for (let offset = 0; offset < descriptors.length; offset += 1) {
    const descriptor = descriptors[offset];
    const shard = record(shardValues[offset]);
    if (
      shard.kind !== "elmos.project-language-conversion-report-shard"
      || shard.markdown_sha256 !== descriptor.markdown.sha256
      || !Array.isArray(shard.exclusions)
      || shard.exclusions.length !== 0
      || SHARD_COMMON_FIELDS.some((field) => !deepJsonEqual(shard[field], index[field]))
    ) invalid();
    const shardMetadata = record(shard.shard);
    if (
      shardMetadata.sequence !== descriptor.sequence
      || shardMetadata.total !== summary.shardCount
      || shardMetadata.function_count !== descriptor.functionCount
      || shardMetadata.obligation_ids_sha256 !== descriptor.obligationIdsSha256
      || !sameCounts(descriptor.statusCounts, shardMetadata.status_counts)
    ) invalid();
    const functions = shard.functions;
    if (!Array.isArray(functions) || functions.length !== descriptor.functionCount) invalid();
    const obligationIds: string[] = [];
    const observedLocalCounts: Record<string, number> = {};
    const observedLocalBlockers: string[] = [];
    for (const valueForFunction of functions) {
      const item = record(valueForFunction);
      const obligationId = boundedString(item.obligation_id, 64);
      const status = boundedString(item.status, 20);
      if (
        !OBLIGATION_PATTERN.test(obligationId)
        || !FUNCTION_STATUSES.includes(status as typeof FUNCTION_STATUSES[number])
        || seenObligations.has(obligationId)
      ) invalid();
      seenObligations.add(obligationId);
      obligationIds.push(obligationId);
      observedLocalCounts[status] = (observedLocalCounts[status] ?? 0) + 1;
      if (item.failure !== null) {
        observedLocalBlockers.push(boundedString(record(item.failure).reason_code, 120));
      }
      allFunctions.push(valueForFunction);
    }
    const idsDigest = createHash("sha256").update(obligationIds.join("\n"), "utf8").digest("hex");
    if (
      obligationIds[0] !== descriptor.firstObligationId
      || obligationIds.at(-1) !== descriptor.lastObligationId
      || idsDigest !== descriptor.obligationIdsSha256
      || !sameCounts(descriptor.statusCounts, observedLocalCounts)
      || !deepJsonEqual(shard.blockers, observedLocalBlockers)
    ) invalid();
  }

  const aggregate: JsonRecord = {
    ...index,
    kind: "elmos.project-language-conversion-report",
    markdown_sha256: expected.markdownSha256,
    functions: allFunctions,
  };
  delete aggregate.storage_mode;
  delete aggregate.shard_count;
  delete aggregate.total_shard_bytes;
  delete aggregate.shards;
  validateTranslationConversionDocument(aggregate, expected, summary);
}

export function translationConversionBundleFiles(
  conversion: ValidatedTranslationConversion,
  shards: TranslationConversionShardDescriptor[],
): TranslationConversionBundleFileDescriptor[] {
  if (conversion.summary.storageMode !== "SHARDED" || !conversion.reportBundle) invalid();
  const files: TranslationConversionBundleFileDescriptor[] = [
    conversion.jsonReport,
    conversion.markdownReport,
    ...shards.flatMap((shard) => [shard.json, shard.markdown]),
  ];
  const seen = new Set<string>();
  for (const file of files) {
    if (seen.has(file.path)) invalid();
    seen.add(file.path);
  }
  return files.sort((left, right) => (
    left.path < right.path ? -1 : left.path > right.path ? 1 : 0
  ));
}

export function validateTranslationConversionBundleManifest(
  bytes: Uint8Array,
  reportId: string,
  expectedFiles: TranslationConversionBundleFileDescriptor[],
): TranslationConversionBundleFileDescriptor {
  if (bytes.byteLength < 1 || bytes.byteLength > 1024 * 1024) invalid();
  let manifestValue: unknown;
  try {
    manifestValue = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    invalid();
  }
  const manifest = record(manifestValue);
  const totalUncompressedBytes = expectedFiles.reduce((total, file) => total + file.bytes, 0);
  if (
    manifest.schema_version !== "1.0.0"
    || manifest.kind !== "elmos.project-language-conversion-report-bundle-manifest"
    || manifest.report_id !== reportId
    || manifest.file_count !== expectedFiles.length
    || manifest.total_uncompressed_bytes !== totalUncompressedBytes
    || !deepJsonEqual(manifest.files, expectedFiles)
    || totalUncompressedBytes + bytes.byteLength > MAX_FUNCTIONAL_REPORT_BUNDLE_BYTES
  ) invalid();
  return {
    path: BUNDLE_MANIFEST_PATH,
    bytes: bytes.byteLength,
    sha256: createHash("sha256").update(bytes).digest("hex"),
  };
}

export async function validateTranslationConversionBundleArchive(
  archiveSource: string | FileHandle,
  descriptor: TranslationConversionReportFile,
  expectedFiles: TranslationConversionBundleFileDescriptor[],
  manifestDescriptor: TranslationConversionBundleFileDescriptor,
): Promise<void> {
  if (descriptor.path !== BUNDLE_REPORT_PATH || descriptor.bytes > MAX_FUNCTIONAL_REPORT_BUNDLE_BYTES) invalid();
  const allExpected = [...expectedFiles, manifestDescriptor];
  const expectedByPath = new Map(allExpected.map((file) => [file.path, file]));
  const seen = new Set<string>();
  const completed = new Set<string>();
  let validationError: Error | null = null;
  const unzip = new Unzip((file) => {
    const expected = expectedByPath.get(file.name);
    if (
      validationError
      || !expected
      || seen.has(file.name)
      || file.compression !== 8
      || file.size === undefined
      || file.originalSize === undefined
      || file.originalSize !== expected.bytes
      || file.originalSize > MAX_FUNCTIONAL_REPORT_BYTES
      || file.size > descriptor.bytes
    ) {
      validationError = new Error("TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID");
      file.terminate();
      return;
    }
    seen.add(file.name);
    const digest = createHash("sha256");
    let observedBytes = 0;
    file.ondata = (error, chunk, final) => {
      if (validationError) return;
      if (error) {
        validationError = error;
        return;
      }
      observedBytes += chunk.byteLength;
      if (observedBytes > expected.bytes) {
        validationError = new Error("TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID");
        file.terminate();
        return;
      }
      digest.update(chunk);
      if (final) {
        if (observedBytes !== expected.bytes || digest.digest("hex") !== expected.sha256) {
          validationError = new Error("TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID");
          return;
        }
        completed.add(file.name);
      }
    };
    file.start();
  });
  unzip.register(UnzipInflate);
  const archiveDigest = createHash("sha256");
  let archiveBytes = 0;
  try {
    const stream = typeof archiveSource === "string"
      ? createReadStream(archiveSource)
      : archiveSource.createReadStream({ start: 0, autoClose: false });
    for await (const chunk of stream) {
      const bytes = chunk as Buffer;
      archiveBytes += bytes.byteLength;
      if (archiveBytes > descriptor.bytes) invalid();
      archiveDigest.update(bytes);
      unzip.push(bytes, false);
      if (validationError) throw validationError;
    }
    unzip.push(new Uint8Array(), true);
    if (validationError) throw validationError;
  } catch {
    invalid();
  }
  if (
    validationError
    || archiveBytes !== descriptor.bytes
    || archiveDigest.digest("hex") !== descriptor.sha256
    || seen.size !== allExpected.length
    || completed.size !== allExpected.length
  ) invalid();
}

/**
 * Validate the downloadable code ZIP itself, not just its outer digest.
 * The caller may pass the same already-opened handle used for confinement and
 * digest checks so a pathname replacement cannot swap the bytes under review.
 */
export async function validateTranslationCodeArtifactArchive(
  archiveSource: string | FileHandle,
  descriptor: TranslationCodeArtifactDescriptor,
  expected: TranslationCodeArtifactContext,
): Promise<void> {
  if (
    descriptor.path !== CODE_ARTIFACT_PATH
    || descriptor.bytes < 1
    || descriptor.bytes > MAX_CODE_ARTIFACT_BYTES
    || !DIGEST_PATTERN.test(descriptor.sha256)
    || expected.profile !== "typed-pure-function-v1"
    || expected.summary.codeArtifactReady !== true
  ) invalidArtifact();

  const seen = new Set<string>();
  const completed = new Set<string>();
  const archivedFiles = new Map<string, TranslationConversionBundleFileDescriptor>();
  const manifestChunks: Buffer[] = [];
  let validationError: Error | null = null;
  let totalUncompressedBytes = 0;
  const unzip = new Unzip((file) => {
    let entryPath: string;
    try {
      entryPath = relativePath(file.name, 1_024);
    } catch {
      validationError = new Error("TRANSLATION_ARTIFACT_EVIDENCE_INVALID");
      file.terminate();
      return;
    }
    if (
      validationError
      || seen.has(entryPath)
      || seen.size >= MAX_CODE_ARTIFACT_ENTRIES
      || file.compression !== 8
      || file.size === undefined
      || file.originalSize === undefined
      || file.originalSize < 0
      || file.originalSize > MAX_CODE_ARTIFACT_BYTES
      || file.size > descriptor.bytes
    ) {
      validationError = new Error("TRANSLATION_ARTIFACT_EVIDENCE_INVALID");
      file.terminate();
      return;
    }
    totalUncompressedBytes += file.originalSize;
    if (totalUncompressedBytes > MAX_CODE_ARTIFACT_BYTES) {
      validationError = new Error("TRANSLATION_ARTIFACT_EVIDENCE_INVALID");
      file.terminate();
      return;
    }
    seen.add(entryPath);
    const digest = createHash("sha256");
    let observedBytes = 0;
    file.ondata = (error, chunk, final) => {
      if (validationError) return;
      if (error) {
        validationError = new Error("TRANSLATION_ARTIFACT_EVIDENCE_INVALID");
        return;
      }
      observedBytes += chunk.byteLength;
      if (
        observedBytes > file.originalSize!
        || (entryPath === CODE_ARTIFACT_MANIFEST_PATH && observedBytes > MAX_FUNCTIONAL_REPORT_BYTES)
      ) {
        validationError = new Error("TRANSLATION_ARTIFACT_EVIDENCE_INVALID");
        file.terminate();
        return;
      }
      digest.update(chunk);
      if (entryPath === CODE_ARTIFACT_MANIFEST_PATH) manifestChunks.push(Buffer.from(chunk));
      if (final) {
        if (observedBytes !== file.originalSize) {
          validationError = new Error("TRANSLATION_ARTIFACT_EVIDENCE_INVALID");
          return;
        }
        archivedFiles.set(entryPath, {
          path: entryPath,
          bytes: observedBytes,
          sha256: digest.digest("hex"),
        });
        completed.add(entryPath);
      }
    };
    file.start();
  });
  unzip.register(UnzipInflate);

  const archiveDigest = createHash("sha256");
  let archiveBytes = 0;
  try {
    const stream = typeof archiveSource === "string"
      ? createReadStream(archiveSource)
      : archiveSource.createReadStream({ start: 0, autoClose: false });
    for await (const chunk of stream) {
      const bytes = chunk as Buffer;
      archiveBytes += bytes.byteLength;
      if (archiveBytes > descriptor.bytes) invalidArtifact();
      archiveDigest.update(bytes);
      unzip.push(bytes, false);
      if (validationError) throw validationError;
    }
    unzip.push(new Uint8Array(), true);
    if (validationError) throw validationError;
  } catch {
    invalidArtifact();
  }
  if (
    validationError
    || archiveBytes !== descriptor.bytes
    || archiveDigest.digest("hex") !== descriptor.sha256
    || seen.size < 2
    || completed.size !== seen.size
    || !completed.has(CODE_ARTIFACT_MANIFEST_PATH)
  ) invalidArtifact();

  let manifestValue: unknown;
  try {
    const manifestBytes = Buffer.concat(manifestChunks);
    manifestValue = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(manifestBytes));
  } catch {
    invalidArtifact();
  }
  try {
    const manifest = record(manifestValue);
    const expectedTopLevelKeys = [
      "certification_status",
      "external_verification_status",
      "files",
      "functional_conversion",
      "kind",
      "profile",
      "repository_ref",
      "route_id",
      "schema_version",
      "snapshot_sha256",
      "status",
    ];
    if (JSON.stringify(Object.keys(manifest).sort()) !== JSON.stringify(expectedTopLevelKeys)) {
      invalidArtifact();
    }
    const expectedFunctionalConversion = {
      definition_id: expected.summary.definitionId,
      numerator: expected.summary.numerator,
      denominator: expected.summary.denominator,
      success_rate_basis_points: expected.summary.successRateBasisPoints,
      measurement_status: expected.summary.measurementStatus,
      denominator_complete: expected.summary.denominatorComplete,
      project_success_rate_display: expected.summary.projectSuccessRateDisplay,
      code_artifact_ready: true,
      cases_manifest_sha256: expected.summary.casesManifestSha256,
    };
    if (
      manifest.schema_version !== "1.0.0"
      || manifest.kind !== "elmos.repository-migration-artifact-manifest"
      || manifest.status !== expected.pipelineStatus
      || manifest.repository_ref !== expected.repositoryRef
      || manifest.snapshot_sha256 !== expected.snapshotSha256
      || manifest.route_id !== expected.routeId
      || manifest.profile !== expected.profile
      || manifest.external_verification_status !== "NOT_RUN"
      || manifest.certification_status !== "NOT_CERTIFIED"
      || !deepJsonEqual(manifest.functional_conversion, expectedFunctionalConversion)
      || !Array.isArray(manifest.files)
      || manifest.files.length !== archivedFiles.size - 1
      || manifest.files.length > MAX_CODE_ARTIFACT_ENTRIES - 1
    ) invalidArtifact();

    const declaredFiles: TranslationConversionBundleFileDescriptor[] = [];
    const declaredPaths = new Set<string>();
    for (const rawFile of manifest.files) {
      const file = record(rawFile);
      if (JSON.stringify(Object.keys(file).sort()) !== JSON.stringify(["bytes", "path", "sha256"])) {
        invalidArtifact();
      }
      const filePath = relativePath(file.path, 1_024);
      const bytes = integer(file.bytes, 0, MAX_CODE_ARTIFACT_BYTES);
      const sha256 = boundedString(file.sha256, 64);
      if (
        filePath === CODE_ARTIFACT_MANIFEST_PATH
        || declaredPaths.has(filePath)
        || !DIGEST_PATTERN.test(sha256)
      ) invalidArtifact();
      declaredPaths.add(filePath);
      declaredFiles.push({ path: filePath, bytes, sha256 });
    }
    for (const declared of declaredFiles) {
      if (!deepJsonEqual(archivedFiles.get(declared.path), declared)) invalidArtifact();
    }
    if ([...archivedFiles.keys()].some((entryPath) => (
      entryPath !== CODE_ARTIFACT_MANIFEST_PATH && !declaredPaths.has(entryPath)
    ))) invalidArtifact();
  } catch {
    invalidArtifact();
  }
}

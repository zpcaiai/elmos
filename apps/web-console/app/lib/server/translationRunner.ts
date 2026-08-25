import { createHash, randomUUID } from "node:crypto";
import { spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import { inflateRawSync } from "node:zlib";
import {
  access,
  lstat,
  mkdir,
  readFile,
  realpath,
  rename,
  stat,
  writeFile,
} from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import path from "node:path";
import type { NextRequest } from "next/server";
import type {
  TranslationBehaviorCoverage,
  TranslationJob,
  TranslationJobLog,
  TranslationCapabilityResponse,
  TranslationLanguageId,
  TranslationSemanticCoverage,
} from "../contracts";
import {
  authorize as authorizeLocalRunner,
  GenerationRunnerError,
  health as generationRunnerHealth,
} from "./generationRunner";
import { readTranslationExecutionCapability, resolveRepositoryRoot } from "./translationRoutes";
import { repositoryTranslationWorkspace } from "./repositoryWorkspaceProxy";
import { beginMeteredExecution, type MeteredExecution } from "./commercialUsageProducer";
import {
  DurableJobLease,
  DurableLeaseError,
  durableQueueConfiguration,
} from "./durableJobLease";

type AuthorizedContext = ReturnType<typeof authorizeLocalRunner>;
type TranslationRunnerConfig = {
  root: string;
  repositoryRoot: string;
  sourceRoot: string;
  casesRoot: string;
  uv: string;
  executor: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT";
  containerEngine?: string;
  containerImage?: string;
};

type TranslationProcessState = {
  active: Map<string, ChildProcess>;
  scheduled: Set<string>;
  cancelled: Set<string>;
};

const globalState = globalThis as typeof globalThis & {
  __elmosTranslationRunnerState?: TranslationProcessState;
};
const state = globalState.__elmosTranslationRunnerState ??= {
  active: new Map<string, ChildProcess>(),
  scheduled: new Set<string>(),
  cancelled: new Set<string>(),
};
state.active ??= new Map<string, ChildProcess>();
state.scheduled ??= new Set<string>();
state.cancelled ??= new Set<string>();

const identifierPattern = /^[a-z0-9][a-z0-9._-]{2,80}$/;
const jobIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const digestPattern = /^[0-9a-f]{64}$/;
const immutableImagePattern = /^[^@\s]+@sha256:[0-9a-f]{64}$/;
const languages = new Set<TranslationLanguageId>([
  "cpp",
  "java",
  "csharp",
  "go",
  "objc",
  "rust",
  "swift",
  "python",
  "typescript",
  "php",
  "kotlin",
  "react",
  "flutter",
]);
const sensitivePattern = /(authorization|token|secret|password|cookie|api[-_]?key)\s*[:=]\s*\S+/gi;

export type TranslationRunnerHealth = {
  status: "READY" | "DISABLED" | "BLOCKED";
  persistence: "FILESYSTEM_ATOMIC";
  auth: "BEARER_TENANT_BOUND";
  isolation: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT" | "NOT_CONFIGURED";
  recovery: "PERSISTENT_RECONCILIATION";
  sourceStorage: "READ_ONLY" | "NOT_RUN" | "BLOCKED";
  activeJobs: number;
  reason?: string;
  checkedAt: string;
};

function fail(status: number, code: string): never {
  throw new GenerationRunnerError(status, code);
}

function confined(base: string, ...segments: string[]): string {
  const candidate = path.resolve(/* turbopackIgnore: true */ base, ...segments);
  if (candidate !== base && !candidate.startsWith(`${base}${path.sep}`)) {
    fail(400, "TRANSLATION_PATH_CONFINEMENT_FAILED");
  }
  return candidate;
}

function runnerConfig(): TranslationRunnerConfig {
  if (process.env.ELMOS_LOCAL_RUNNER_ENABLED !== "true") {
    fail(503, "LOCAL_RUNNER_NOT_ENABLED");
  }
  const root = process.env.ELMOS_LOCAL_RUNNER_ROOT;
  const sourceRoot = process.env.ELMOS_TRANSLATION_SOURCE_ROOT;
  const casesRoot = process.env.ELMOS_TRANSLATION_CASES_ROOT;
  const uv = process.env.ELMOS_UV_PATH;
  const executor = process.env.ELMOS_LOCAL_RUNNER_EXECUTOR;
  if (
    !root || !path.isAbsolute(root)
    || !sourceRoot || !path.isAbsolute(sourceRoot)
    || !casesRoot || !path.isAbsolute(casesRoot)
    || !uv || !path.isAbsolute(uv)
  ) {
    fail(503, "TRANSLATION_RUNNER_PATHS_NOT_CONFIGURED");
  }
  if (!["ROOTLESS_CONTAINER", "HOST_DEVELOPMENT"].includes(executor ?? "")) {
    fail(503, "LOCAL_RUNNER_EXECUTOR_NOT_CONFIGURED");
  }
  if (executor === "HOST_DEVELOPMENT" && process.env.NODE_ENV === "production") {
    fail(503, "HOST_EXECUTOR_FORBIDDEN_IN_PRODUCTION");
  }
  const repositoryRoot = resolveRepositoryRoot();
  const resolved = {
    root: path.resolve(/* turbopackIgnore: true */ root),
    repositoryRoot: path.resolve(/* turbopackIgnore: true */ repositoryRoot),
    sourceRoot: path.resolve(/* turbopackIgnore: true */ sourceRoot),
    casesRoot: path.resolve(/* turbopackIgnore: true */ casesRoot),
    uv: path.resolve(/* turbopackIgnore: true */ uv),
  };
  if (
    resolved.root === path.parse(resolved.root).root
    || resolved.root === resolved.repositoryRoot
    || resolved.repositoryRoot.startsWith(`${resolved.root}${path.sep}`)
    || resolved.sourceRoot === resolved.root
    || resolved.sourceRoot.startsWith(`${resolved.root}${path.sep}`)
    || resolved.casesRoot === resolved.root
    || resolved.casesRoot.startsWith(`${resolved.root}${path.sep}`)
  ) {
    fail(503, "TRANSLATION_RUNNER_ROOT_UNSAFE");
  }
  for (const required of [
    resolved.repositoryRoot,
    resolved.sourceRoot,
    resolved.casesRoot,
    resolved.uv,
    path.join(/* turbopackIgnore: true */ resolved.repositoryRoot, "engines/polyglot-route-engine"),
  ]) {
    if (!existsSync(/* turbopackIgnore: true */ required)) {
      fail(503, "TRANSLATION_RUNNER_EXECUTION_ASSET_MISSING");
    }
  }
  const containerEngine = process.env.ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE;
  const containerImage = process.env.ELMOS_TRANSLATION_RUNNER_IMAGE;
  if (executor === "ROOTLESS_CONTAINER") {
    if (
      !containerEngine
      || !path.isAbsolute(containerEngine)
      || !existsSync(containerEngine)
      || !["docker", "podman"].includes(path.basename(containerEngine))
    ) {
      fail(503, "ROOTLESS_CONTAINER_ENGINE_NOT_CONFIGURED");
    }
    if (!containerImage || !immutableImagePattern.test(containerImage)) {
      fail(503, "TRANSLATION_RUNNER_IMAGE_NOT_IMMUTABLE");
    }
  }
  return {
    ...resolved,
    executor: executor as TranslationRunnerConfig["executor"],
    containerEngine,
    containerImage,
  };
}

export function authorizeTranslation(request: NextRequest): AuthorizedContext {
  return authorizeLocalRunner(request, "translation:execute");
}

function jobRoot(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  jobId: string,
): string {
  if (!jobIdPattern.test(jobId)) fail(400, "TRANSLATION_JOB_ID_INVALID");
  return confined(runner.root, "tenants", context.tenantId, "translation-jobs", jobId);
}

function jobFile(runner: TranslationRunnerConfig, context: AuthorizedContext, jobId: string): string {
  return confined(jobRoot(runner, context, jobId), "job.json");
}

function key(context: AuthorizedContext, jobId: string): string {
  return `${context.tenantId}:${jobId}`;
}

function redact(value: string): string {
  return value.replace(sensitivePattern, "$1=[REDACTED]").slice(0, 4_000);
}

function appendLog(job: TranslationJob, stream: TranslationJobLog["stream"], raw: string): void {
  for (const line of raw.split(/\r?\n/)) {
    const message = redact(line).trim();
    if (!message) continue;
    job.logs.push({ at: new Date().toISOString(), stream, message });
    if (job.logs.length > 400) job.logs.shift();
  }
}

function nonNegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) >= 0;
}

function validProjectGraphSummary(
  value: unknown,
  repositoryComplete: boolean,
): value is NonNullable<TranslationJob["projectGraph"]> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const graph = value as Record<string, unknown>;
  if (
    graph.path !== "project-graph.json"
    || typeof graph.graph_sha256 !== "string"
    || !digestPattern.test(graph.graph_sha256)
    || graph.graph_id !== `elmos:project-graph:sha256:${graph.graph_sha256}`
    || typeof graph.snapshot_sha256 !== "string"
    || !digestPattern.test(graph.snapshot_sha256)
    || graph.repository_complete !== repositoryComplete
    || graph.completeness_status !== (repositoryComplete ? "COMPLETE" : "INCOMPLETE")
    || graph.verification_status !== "PASSED"
    || !nonNegativeInteger(graph.obligation_count)
    || typeof graph.obligation_status_counts !== "object"
    || graph.obligation_status_counts === null
    || Array.isArray(graph.obligation_status_counts)
  ) return false;
  const counts = graph.obligation_status_counts as Record<string, unknown>;
  const statuses = ["FAILED", "NOT_RUN", "PASSED", "UNKNOWN"] as const;
  if (
    Object.keys(counts).sort().join(",") !== [...statuses].sort().join(",")
    || statuses.some((status) => !nonNegativeInteger(counts[status]))
    || statuses.reduce((total, status) => total + Number(counts[status]), 0) !== graph.obligation_count
    || (repositoryComplete && graph.obligation_count !== 0)
  ) return false;
  return true;
}

function validBuildVerification(value: unknown): value is NonNullable<TranslationJob["buildVerification"]> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const build = value as Record<string, unknown>;
  if (build.status !== "PASSED" || !Array.isArray(build.commands) || build.commands.length < 1) return false;
  if (typeof build.toolchain !== "object" || build.toolchain === null || Array.isArray(build.toolchain)) return false;
  const toolchain = build.toolchain as Record<string, unknown>;
  if (!languages.has(toolchain.language as TranslationLanguageId) || typeof toolchain.version !== "string") return false;
  return build.commands.every((entry) => {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) return false;
    const command = entry as Record<string, unknown>;
    return Array.isArray(command.command)
      && command.command.length > 0
      && command.command.every((argument) => typeof argument === "string" && argument.length > 0)
      && typeof command.stdout === "string"
      && typeof command.stderr === "string";
  });
}

async function atomicJson(destination: string, value: unknown): Promise<void> {
  await mkdir(path.dirname(destination), { recursive: true, mode: 0o700 });
  const temporary = `${destination}.${randomUUID()}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  await rename(temporary, destination);
}

async function persist(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
): Promise<void> {
  job.updatedAt = new Date().toISOString();
  await atomicJson(jobFile(runner, context, job.id), job);
}

const MAX_PIPELINE_JSON_BYTES = 16 * 1024 * 1024;
const MAX_PIPELINE_ARTIFACT_BYTES = 512 * 1024 * 1024;
const MAX_ZIP_ENTRIES = 20_000;
const MAX_ZIP_UNCOMPRESSED_BYTES = 768 * 1024 * 1024;
const BATCH_STATUSES = ["PASSED", "FAILED", "SKIPPED_NOT_READY", "SKIPPED_NO_CASES"] as const;
const COVERAGE_STATUSES = ["BLOCKED", "FAILED", "NOT_RUN", "PASSED", "UNKNOWN"] as const;
const BEHAVIOR_COVERAGE_STATUSES = ["FAILED", "NOT_RUN", "PASSED", "UNKNOWN"] as const;

type StableFile = {
  path: string;
  content: Buffer;
  bytes: number;
  sha256: string;
};

type ValidatedPipelineEvidence = {
  report: Record<string, unknown>;
  semanticCoverage: TranslationSemanticCoverage;
  behaviorCoverage: TranslationBehaviorCoverage;
  artifactPath: string;
  artifactBytes: number;
  artifactSha256: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "number") {
    return JSON.stringify(value);
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (!isRecord(value)) fail(409, "TRANSLATION_PIPELINE_CANONICAL_JSON_INVALID");
  return `{${Object.keys(value).sort().map((key) =>
    `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
}

function canonicalEqual(left: unknown, right: unknown): boolean {
  return canonicalJson(left) === canonicalJson(right);
}

function safeRelativeArtifactPath(value: unknown): value is string {
  if (typeof value !== "string" || value.length === 0 || value.length > 1_000) return false;
  if (value.includes("\\") || value.includes("\0") || path.posix.isAbsolute(value)) return false;
  const parts = value.split("/");
  return parts.every((part) => part.length > 0 && part !== "." && part !== "..");
}

async function readStablePipelineFile(
  pipeline: string,
  relative: string,
  maximumBytes: number,
  allowEmpty = false,
): Promise<StableFile> {
  if (!safeRelativeArtifactPath(relative)) fail(409, "TRANSLATION_PIPELINE_FILE_PATH_INVALID");
  let current = pipeline;
  for (const segment of relative.split("/")) {
    current = confined(current, segment);
    let details;
    try {
      details = await lstat(current);
    } catch {
      fail(409, "TRANSLATION_PIPELINE_FILE_MISSING");
    }
    if (details.isSymbolicLink()) fail(409, "TRANSLATION_PIPELINE_FILE_SYMLINK_REJECTED");
  }
  const before = await stat(current, { bigint: true });
  if (!before.isFile() || before.nlink !== 1n) {
    fail(409, "TRANSLATION_PIPELINE_FILE_NOT_INDEPENDENT_REGULAR_FILE");
  }
  if ((!allowEmpty && before.size < 1n) || before.size > BigInt(maximumBytes)) {
    fail(409, "TRANSLATION_PIPELINE_FILE_SIZE_INVALID");
  }
  const content = await readFile(current);
  const after = await stat(current, { bigint: true });
  if (
    before.dev !== after.dev
    || before.ino !== after.ino
    || before.size !== after.size
    || before.mtimeNs !== after.mtimeNs
    || content.byteLength !== Number(before.size)
  ) {
    fail(409, "TRANSLATION_PIPELINE_FILE_CHANGED_DURING_READ");
  }
  return {
    path: current,
    content,
    bytes: content.byteLength,
    sha256: createHash("sha256").update(content).digest("hex"),
  };
}

function parseJsonRecord(file: StableFile, code: string): Record<string, unknown> {
  let value: unknown;
  try {
    value = JSON.parse(file.content.toString("utf-8"));
  } catch {
    fail(409, code);
  }
  if (!isRecord(value)) fail(409, code);
  return value;
}

let crcTable: Uint32Array | undefined;

function crc32(content: Buffer): number {
  if (!crcTable) {
    crcTable = new Uint32Array(256);
    for (let index = 0; index < 256; index += 1) {
      let value = index;
      for (let bit = 0; bit < 8; bit += 1) {
        value = (value & 1) !== 0 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
      }
      crcTable[index] = value >>> 0;
    }
  }
  let value = 0xffffffff;
  for (const byte of content) value = crcTable[(value ^ byte) & 0xff] ^ (value >>> 8);
  return (value ^ 0xffffffff) >>> 0;
}

function unzipEvidence(archive: Buffer): Map<string, Buffer> {
  const minimumEocd = 22;
  if (archive.byteLength < minimumEocd) fail(409, "TRANSLATION_ARTIFACT_ZIP_INVALID");
  const lowerBound = Math.max(0, archive.byteLength - minimumEocd - 65_535);
  let eocd = -1;
  for (let offset = archive.byteLength - minimumEocd; offset >= lowerBound; offset -= 1) {
    if (archive.readUInt32LE(offset) === 0x06054b50) {
      eocd = offset;
      break;
    }
  }
  if (eocd < 0) fail(409, "TRANSLATION_ARTIFACT_ZIP_INVALID");
  const disk = archive.readUInt16LE(eocd + 4);
  const centralDisk = archive.readUInt16LE(eocd + 6);
  const diskEntries = archive.readUInt16LE(eocd + 8);
  const totalEntries = archive.readUInt16LE(eocd + 10);
  const centralBytes = archive.readUInt32LE(eocd + 12);
  const centralOffset = archive.readUInt32LE(eocd + 16);
  const commentBytes = archive.readUInt16LE(eocd + 20);
  if (
    disk !== 0
    || centralDisk !== 0
    || diskEntries !== totalEntries
    || totalEntries < 1
    || totalEntries > MAX_ZIP_ENTRIES
    || centralOffset + centralBytes !== eocd
    || eocd + minimumEocd + commentBytes !== archive.byteLength
  ) fail(409, "TRANSLATION_ARTIFACT_ZIP_LAYOUT_INVALID");

  const entries = new Map<string, Buffer>();
  let central = centralOffset;
  let aggregateBytes = 0;
  for (let index = 0; index < totalEntries; index += 1) {
    if (central + 46 > eocd || archive.readUInt32LE(central) !== 0x02014b50) {
      fail(409, "TRANSLATION_ARTIFACT_ZIP_CENTRAL_DIRECTORY_INVALID");
    }
    const flags = archive.readUInt16LE(central + 8);
    const method = archive.readUInt16LE(central + 10);
    const expectedCrc = archive.readUInt32LE(central + 16);
    const compressedBytes = archive.readUInt32LE(central + 20);
    const uncompressedBytes = archive.readUInt32LE(central + 24);
    const nameBytes = archive.readUInt16LE(central + 28);
    const extraBytes = archive.readUInt16LE(central + 30);
    const entryCommentBytes = archive.readUInt16LE(central + 32);
    const startDisk = archive.readUInt16LE(central + 34);
    const externalAttributes = archive.readUInt32LE(central + 38);
    const localOffset = archive.readUInt32LE(central + 42);
    const centralEnd = central + 46 + nameBytes + extraBytes + entryCommentBytes;
    if (
      centralEnd > eocd
      || startDisk !== 0
      || (flags & 0x0001) !== 0
      || (flags & 0x0008) !== 0
      || ![0, 8].includes(method)
      || uncompressedBytes > MAX_PIPELINE_ARTIFACT_BYTES
    ) fail(409, "TRANSLATION_ARTIFACT_ZIP_ENTRY_INVALID");
    const name = archive.subarray(central + 46, central + 46 + nameBytes).toString("utf-8");
    const unixMode = (externalAttributes >>> 16) & 0xffff;
    if (
      !safeRelativeArtifactPath(name)
      || entries.has(name)
      || (unixMode & 0o170000) === 0o120000
      || localOffset + 30 > centralOffset
      || archive.readUInt32LE(localOffset) !== 0x04034b50
    ) fail(409, "TRANSLATION_ARTIFACT_ZIP_ENTRY_UNSAFE");
    const localFlags = archive.readUInt16LE(localOffset + 6);
    const localMethod = archive.readUInt16LE(localOffset + 8);
    const localNameBytes = archive.readUInt16LE(localOffset + 26);
    const localExtraBytes = archive.readUInt16LE(localOffset + 28);
    const localName = archive.subarray(localOffset + 30, localOffset + 30 + localNameBytes).toString("utf-8");
    const dataStart = localOffset + 30 + localNameBytes + localExtraBytes;
    const dataEnd = dataStart + compressedBytes;
    if (
      localFlags !== flags
      || localMethod !== method
      || localName !== name
      || dataEnd > centralOffset
    ) fail(409, "TRANSLATION_ARTIFACT_ZIP_LOCAL_HEADER_INVALID");
    let content: Buffer;
    try {
      content = method === 0
        ? Buffer.from(archive.subarray(dataStart, dataEnd))
        : inflateRawSync(archive.subarray(dataStart, dataEnd), {
          maxOutputLength: Math.max(1, uncompressedBytes),
        });
    } catch {
      fail(409, "TRANSLATION_ARTIFACT_ZIP_DECOMPRESSION_FAILED");
    }
    aggregateBytes += content.byteLength;
    if (
      content.byteLength !== uncompressedBytes
      || crc32(content) !== expectedCrc
      || aggregateBytes > MAX_ZIP_UNCOMPRESSED_BYTES
    ) fail(409, "TRANSLATION_ARTIFACT_ZIP_CONTENT_INVALID");
    entries.set(name, content);
    central = centralEnd;
  }
  if (central !== eocd) fail(409, "TRANSLATION_ARTIFACT_ZIP_CENTRAL_DIRECTORY_INVALID");
  return entries;
}

function exactNonNegativeCounts(
  value: unknown,
  allowed: readonly string[],
  requireEveryKey: boolean,
  code: string,
): Record<string, number> {
  if (!isRecord(value)) fail(409, code);
  const keys = Object.keys(value);
  if (
    keys.some((key) => !allowed.includes(key))
    || (requireEveryKey && [...allowed].sort().join(",") !== keys.sort().join(","))
    || keys.some((key) => !nonNegativeInteger(value[key]))
  ) fail(409, code);
  return Object.fromEntries(allowed.map((key) => [key, Number(value[key] ?? 0)]));
}

function validateBatchClosure(
  report: Record<string, unknown>,
  reportStatus: "COMPLETE" | "PARTIAL",
): {
  workUnitCount: number;
  readyCount: number;
  includedUnitCount: number;
  counts: Record<string, number>;
  excludedUnits: Map<string, string>;
} {
  if (
    !nonNegativeInteger(report.work_unit_count)
    || report.work_unit_count < 1
    || !nonNegativeInteger(report.ready_count)
    || !nonNegativeInteger(report.included_unit_count)
    || report.included_unit_count < 1
    || report.ready_count > report.work_unit_count
    || report.included_unit_count > report.ready_count
    || !Array.isArray(report.excluded_units)
  ) fail(409, "TRANSLATION_PIPELINE_UNIT_COUNTS_INVALID");
  const workUnitCount = report.work_unit_count;
  const readyCount = report.ready_count;
  const includedUnitCount = report.included_unit_count;
  const counts = exactNonNegativeCounts(
    report.status_counts,
    BATCH_STATUSES,
    false,
    "TRANSLATION_PIPELINE_STATUS_COUNTS_INVALID",
  );
  const total = BATCH_STATUSES.reduce((sum, status) => sum + counts[status], 0);
  if (
    total !== workUnitCount
    || counts.PASSED !== includedUnitCount
    || counts.PASSED + counts.FAILED + counts.SKIPPED_NO_CASES !== readyCount
    || counts.SKIPPED_NOT_READY !== workUnitCount - readyCount
  ) fail(409, "TRANSLATION_PIPELINE_STATUS_COUNTS_NOT_CLOSED");
  const batchComplete = counts.PASSED === workUnitCount
    && counts.FAILED === 0
    && counts.SKIPPED_NOT_READY === 0
    && counts.SKIPPED_NO_CASES === 0;
  if (
    report.unit_batch_status !== (batchComplete ? "COMPLETE" : "PARTIAL")
    || (reportStatus === "COMPLETE" && !batchComplete)
  ) fail(409, "TRANSLATION_PIPELINE_BATCH_STATUS_CONTRADICTORY");

  const excludedCounts: Record<string, number> = {
    FAILED: 0,
    SKIPPED_NOT_READY: 0,
    SKIPPED_NO_CASES: 0,
  };
  const excludedIds = new Set<string>();
  const excludedUnits = new Map<string, string>();
  for (const raw of report.excluded_units) {
    if (!isRecord(raw) || typeof raw.id !== "string" || raw.id.length === 0 || excludedIds.has(raw.id)) {
      fail(409, "TRANSLATION_PIPELINE_EXCLUDED_UNIT_INVALID");
    }
    const status = raw.status;
    if (typeof status !== "string" || !(status in excludedCounts)) {
      fail(409, "TRANSLATION_PIPELINE_EXCLUDED_UNIT_INVALID");
    }
    excludedIds.add(raw.id);
    excludedUnits.set(raw.id, status);
    excludedCounts[status] += 1;
  }
  if (
    report.excluded_units.length !== workUnitCount - includedUnitCount
    || excludedCounts.FAILED !== counts.FAILED
    || excludedCounts.SKIPPED_NOT_READY !== counts.SKIPPED_NOT_READY
    || excludedCounts.SKIPPED_NO_CASES !== counts.SKIPPED_NO_CASES
  ) fail(409, "TRANSLATION_PIPELINE_EXCLUDED_UNITS_NOT_CLOSED");
  return { workUnitCount, readyCount, includedUnitCount, counts, excludedUnits };
}

function validateProjectGraphEvidence(
  graph: Record<string, unknown>,
  summary: unknown,
  repositoryRef: string,
  repositoryComplete: boolean,
): void {
  if (!validProjectGraphSummary(summary, repositoryComplete) || !isRecord(summary)) {
    fail(409, "TRANSLATION_PIPELINE_PROJECT_GRAPH_SUMMARY_INVALID");
  }
  if (
    graph.kind !== "elmos.content-addressed-project-graph"
    || graph.repository_ref !== repositoryRef
    || graph.graph_id !== summary.graph_id
    || graph.graph_sha256 !== summary.graph_sha256
    || graph.snapshot_sha256 !== summary.snapshot_sha256
    || graph.repository_complete !== repositoryComplete
    || graph.completeness_status !== (repositoryComplete ? "COMPLETE" : "INCOMPLETE")
    || !Array.isArray(graph.diagnostic_obligations)
  ) fail(409, "TRANSLATION_PIPELINE_PROJECT_GRAPH_BINDING_INVALID");
  const digestPayload = Object.fromEntries(
    Object.entries(graph).filter(([key]) => !["graph_id", "graph_sha256"].includes(key)),
  );
  const observedDigest = createHash("sha256").update(canonicalJson(digestPayload)).digest("hex");
  if (observedDigest !== graph.graph_sha256) {
    fail(409, "TRANSLATION_PIPELINE_PROJECT_GRAPH_DIGEST_INVALID");
  }
  const obligationCounts = { FAILED: 0, NOT_RUN: 0, PASSED: 0, UNKNOWN: 0 };
  for (const obligation of graph.diagnostic_obligations) {
    if (
      !isRecord(obligation)
      || obligation.blocks_repository_complete !== true
      || typeof obligation.verification_status !== "string"
      || !(obligation.verification_status in obligationCounts)
    ) fail(409, "TRANSLATION_PIPELINE_PROJECT_GRAPH_OBLIGATION_INVALID");
    obligationCounts[obligation.verification_status as keyof typeof obligationCounts] += 1;
  }
  if (
    graph.diagnostic_obligations.length !== summary.obligation_count
    || !canonicalEqual(obligationCounts, summary.obligation_status_counts)
    || repositoryComplete !== (graph.diagnostic_obligations.length === 0)
  ) fail(409, "TRANSLATION_PIPELINE_PROJECT_GRAPH_OBLIGATIONS_NOT_CLOSED");
}

function validateConversionCoverage(
  value: unknown,
  sourceLanguage: TranslationLanguageId,
  reportStatus: "COMPLETE" | "PARTIAL",
  graph: Record<string, unknown>,
  includedUnitCount: number,
): TranslationSemanticCoverage {
  if (
    !isRecord(value)
    || value.profile !== "compiler-semantic-symbol-coverage-v1"
    || value.source_language !== sourceLanguage
  ) {
    fail(409, "TRANSLATION_PIPELINE_CONVERSION_COVERAGE_INVALID");
  }
  if (
    !nonNegativeInteger(value.subject_count)
    || !Array.isArray(value.subjects)
    || value.subjects.length !== value.subject_count
    || typeof value.complete !== "boolean"
  ) fail(409, "TRANSLATION_PIPELINE_CONVERSION_COVERAGE_INVALID");
  const counts = exactNonNegativeCounts(
    value.status_counts,
    COVERAGE_STATUSES,
    true,
    "TRANSLATION_PIPELINE_CONVERSION_COVERAGE_COUNTS_INVALID",
  );
  if (COVERAGE_STATUSES.reduce((sum, status) => sum + counts[status], 0) !== value.subject_count) {
    fail(409, "TRANSLATION_PIPELINE_CONVERSION_COVERAGE_COUNTS_NOT_CLOSED");
  }

  const graphSubjects = new Map<string, Record<string, unknown>>();
  const moduleInventoryStatuses: string[] = [];
  if (!Array.isArray(graph.nodes)) fail(409, "TRANSLATION_PIPELINE_PROJECT_GRAPH_NODES_INVALID");
  for (const node of graph.nodes) {
    if (!isRecord(node) || !isRecord(node.attributes)) continue;
    if (node.language !== sourceLanguage) continue;
    if (node.kind === "module") {
      if (typeof node.attributes.semantic_index_status !== "string") {
        fail(409, "TRANSLATION_PIPELINE_CONVERSION_MODULE_INVENTORY_INVALID");
      }
      moduleInventoryStatuses.push(node.attributes.semantic_index_status);
      continue;
    }
    if (node.attributes.conversion_coverage_requirement !== "REQUIRED") continue;
    const coverageKey = node.attributes.coverage_key;
    if (
      !["symbol", "effect"].includes(String(node.kind))
      || typeof coverageKey !== "string"
      || !coverageKey.startsWith(`${sourceLanguage}:sha256:`)
      || graphSubjects.has(coverageKey)
    ) {
      fail(409, "TRANSLATION_PIPELINE_PROJECT_GRAPH_COVERAGE_SUBJECT_INVALID");
    }
    graphSubjects.set(coverageKey, node);
  }
  if (graphSubjects.size !== value.subject_count) {
    fail(409, "TRANSLATION_PIPELINE_CONVERSION_GRAPH_COVERAGE_MISMATCH");
  }
  const expectedInventoryStatus = moduleInventoryStatuses.length > 0
    && moduleInventoryStatuses.every((status) => status === "PASSED")
    ? "PASSED"
    : moduleInventoryStatuses.some((status) => status === "FAILED")
      ? "FAILED"
      : "NOT_RUN";
  const observedCounts = Object.fromEntries(COVERAGE_STATUSES.map((status) => [status, 0])) as Record<string, number>;
  const seenCoverageKeys = new Set<string>();
  const seenReadyUnits = new Set<string>();
  for (const subject of value.subjects) {
    if (
      !isRecord(subject)
      || typeof subject.coverage_key !== "string"
      || seenCoverageKeys.has(subject.coverage_key)
      || typeof subject.status !== "string"
      || !COVERAGE_STATUSES.includes(subject.status as typeof COVERAGE_STATUSES[number])
      || !Array.isArray(subject.ready_unit_ids)
      || !Array.isArray(subject.blocker_codes)
    ) fail(409, "TRANSLATION_PIPELINE_CONVERSION_SUBJECT_INVALID");
    const graphSubject = graphSubjects.get(subject.coverage_key);
    if (
      !graphSubject
      || graphSubject.id !== subject.node_id
      || graphSubject.path !== subject.path
      || graphSubject.source_location === undefined
      || !canonicalEqual(graphSubject.source_location, subject.source_location)
    ) fail(409, "TRANSLATION_PIPELINE_CONVERSION_SUBJECT_GRAPH_MISMATCH");
    seenCoverageKeys.add(subject.coverage_key);
    observedCounts[subject.status] += 1;
    if (subject.status === "PASSED") {
      if (
        subject.ready_unit_ids.length !== 1
        || typeof subject.ready_unit_ids[0] !== "string"
        || seenReadyUnits.has(subject.ready_unit_ids[0])
        || subject.batch_status !== "PASSED"
        || subject.blocker_codes.length !== 0
      ) fail(409, "TRANSLATION_PIPELINE_CONVERSION_PASSED_SUBJECT_INVALID");
      seenReadyUnits.add(subject.ready_unit_ids[0]);
    }
  }
  if (!canonicalEqual(observedCounts, counts)) {
    fail(409, "TRANSLATION_PIPELINE_CONVERSION_SUBJECT_COUNTS_NOT_CLOSED");
  }
  const complete = expectedInventoryStatus === "PASSED"
    && value.subject_count > 0
    && counts.PASSED === value.subject_count;
  if (
    value.complete !== complete
    || value.status !== (complete ? "PASSED" : "LIMITED")
    || value.inventory_status !== expectedInventoryStatus
    || (complete && seenReadyUnits.size !== includedUnitCount)
    || (reportStatus === "COMPLETE" && !complete)
  ) fail(409, "TRANSLATION_PIPELINE_CONVERSION_COVERAGE_CONTRADICTORY");
  return {
    profile: "compiler-semantic-symbol-coverage-v1",
    sourceLanguage,
    inventoryStatus: value.inventory_status as TranslationSemanticCoverage["inventoryStatus"],
    status: value.status as TranslationSemanticCoverage["status"],
    complete,
    subjectCount: value.subject_count,
    statusCounts: counts as TranslationSemanticCoverage["statusCounts"],
  };
}

function validateBehaviorCoverage(
  value: unknown,
  reportStatus: "COMPLETE" | "PARTIAL",
  closure: ReturnType<typeof validateBatchClosure>,
): TranslationBehaviorCoverage {
  if (
    !isRecord(value)
    || value.profile !== "typed-pure-function-v1"
    || typeof value.complete !== "boolean"
    || !BEHAVIOR_COVERAGE_STATUSES.includes(
      value.status as typeof BEHAVIOR_COVERAGE_STATUSES[number],
    )
  ) fail(409, "TRANSLATION_PIPELINE_BEHAVIOR_COVERAGE_INVALID");
  for (const field of [
    "work_unit_denominator",
    "work_unit_count",
    "accounted_work_unit_count",
    "attempted_work_unit_count",
    "unresolved_work_unit_count",
    "behavior_case_count",
  ]) {
    if (!nonNegativeInteger(value[field])) {
      fail(409, "TRANSLATION_PIPELINE_BEHAVIOR_COVERAGE_COUNTS_INVALID");
    }
  }
  const counts = exactNonNegativeCounts(
    value.status_counts,
    BEHAVIOR_COVERAGE_STATUSES,
    true,
    "TRANSLATION_PIPELINE_BEHAVIOR_COVERAGE_STATUS_COUNTS_INVALID",
  );
  const workUnitCount = Number(value.work_unit_count);
  const accountedWorkUnitCount = Number(value.accounted_work_unit_count);
  const attemptedWorkUnitCount = Number(value.attempted_work_unit_count);
  const unresolvedWorkUnitCount = Number(value.unresolved_work_unit_count);
  const behaviorCaseCount = Number(value.behavior_case_count);
  const expectedNotRun = closure.counts.SKIPPED_NOT_READY + closure.counts.SKIPPED_NO_CASES;
  const expectedComplete = workUnitCount > 0
    && counts.PASSED === workUnitCount
    && counts.FAILED === 0
    && counts.NOT_RUN === 0
    && counts.UNKNOWN === 0;
  const expectedStatus = expectedComplete
    ? "PASSED"
    : counts.FAILED > 0
      ? "FAILED"
      : counts.UNKNOWN > 0
        ? "UNKNOWN"
        : "NOT_RUN";
  if (
    workUnitCount !== closure.workUnitCount
    || value.work_unit_denominator !== workUnitCount
    || accountedWorkUnitCount !== workUnitCount
    || BEHAVIOR_COVERAGE_STATUSES.reduce((sum, status) => sum + counts[status], 0)
      !== workUnitCount
    || counts.PASSED !== closure.counts.PASSED
    || counts.FAILED !== closure.counts.FAILED
    || counts.NOT_RUN !== expectedNotRun
    || counts.UNKNOWN !== 0
    || attemptedWorkUnitCount !== counts.PASSED + counts.FAILED
    || unresolvedWorkUnitCount !== counts.NOT_RUN + counts.UNKNOWN
    || value.complete !== expectedComplete
    || value.status !== expectedStatus
    || value.pass_rate !== counts.PASSED / workUnitCount
    || value.behavior_case_count_scope !== "PASSED_WORK_UNITS_ONLY"
    || value.evidence_strength !== "LOCAL_SOURCE_TARGET_RUNTIME_COMPARISON"
    || value.independent_verification_status !== "NOT_RUN"
    || value.external_verification_status !== "NOT_RUN"
    || (reportStatus === "COMPLETE" && !expectedComplete)
    || !Array.isArray(value.units)
    || value.units.length !== workUnitCount
  ) fail(409, "TRANSLATION_PIPELINE_BEHAVIOR_COVERAGE_CONTRADICTORY");

  const observedCounts = Object.fromEntries(
    BEHAVIOR_COVERAGE_STATUSES.map((status) => [status, 0]),
  ) as Record<string, number>;
  const seenUnits = new Set<string>();
  const seenExcludedUnits = new Set<string>();
  let observedBehaviorCases = 0;
  for (const unit of value.units) {
    if (
      !isRecord(unit)
      || typeof unit.id !== "string"
      || unit.id.length === 0
      || seenUnits.has(unit.id)
      || typeof unit.status !== "string"
      || !BEHAVIOR_COVERAGE_STATUSES.includes(
        unit.status as typeof BEHAVIOR_COVERAGE_STATUSES[number],
      )
      || typeof unit.batch_status !== "string"
      || !BATCH_STATUSES.includes(unit.batch_status as typeof BATCH_STATUSES[number])
    ) fail(409, "TRANSLATION_PIPELINE_BEHAVIOR_COVERAGE_UNIT_INVALID");
    seenUnits.add(unit.id);
    observedCounts[unit.status] += 1;
    const expectedUnitStatus = unit.batch_status === "PASSED"
      ? "PASSED"
      : unit.batch_status === "FAILED"
        ? "FAILED"
        : ["SKIPPED_NOT_READY", "SKIPPED_NO_CASES"].includes(unit.batch_status)
          ? "NOT_RUN"
          : "UNKNOWN";
    if (unit.status !== expectedUnitStatus) {
      fail(409, "TRANSLATION_PIPELINE_BEHAVIOR_COVERAGE_UNIT_CONTRADICTORY");
    }
    const excludedStatus = closure.excludedUnits.get(unit.id);
    if (
      (unit.status === "PASSED" && excludedStatus !== undefined)
      || (unit.status !== "PASSED" && excludedStatus !== unit.batch_status)
    ) fail(409, "TRANSLATION_PIPELINE_BEHAVIOR_COVERAGE_EXCLUDED_UNIT_MISMATCH");
    if (excludedStatus !== undefined) seenExcludedUnits.add(unit.id);
    if (unit.status === "PASSED") {
      if (
        !nonNegativeInteger(unit.behavior_case_count)
        || unit.behavior_case_count < 1
        || unit.evidence_path !== `units/${unit.id}/route-evidence.json`
        || typeof unit.evidence_sha256 !== "string"
        || !/^sha256:[0-9a-f]{64}$/.test(unit.evidence_sha256)
      ) fail(409, "TRANSLATION_PIPELINE_BEHAVIOR_COVERAGE_PASSED_UNIT_INVALID");
      observedBehaviorCases += unit.behavior_case_count;
    } else if (
      unit.behavior_case_count !== (unit.batch_status === "SKIPPED_NO_CASES" ? 0 : null)
      || unit.evidence_path !== null
      || unit.evidence_sha256 !== null
    ) {
      fail(409, "TRANSLATION_PIPELINE_BEHAVIOR_COVERAGE_NON_PASSED_UNIT_INVALID");
    }
  }
  if (
    !canonicalEqual(observedCounts, counts)
    || observedBehaviorCases !== behaviorCaseCount
    || seenExcludedUnits.size !== closure.excludedUnits.size
  ) fail(409, "TRANSLATION_PIPELINE_BEHAVIOR_COVERAGE_UNITS_NOT_CLOSED");

  return {
    profile: "typed-pure-function-v1",
    status: expectedStatus,
    complete: expectedComplete,
    workUnitCount,
    accountedWorkUnitCount,
    attemptedWorkUnitCount,
    unresolvedWorkUnitCount,
    behaviorCaseCount,
    behaviorCaseCountScope: "PASSED_WORK_UNITS_ONLY",
    statusCounts: counts as TranslationBehaviorCoverage["statusCounts"],
    evidenceStrength: "LOCAL_SOURCE_TARGET_RUNTIME_COMPARISON",
    independentVerificationStatus: "NOT_RUN",
    externalVerificationStatus: "NOT_RUN",
  };
}

/**
 * Validate the shared behavior claim before either the report or the artifact
 * manifest can be admitted. Exported so recovery and adversarial verification
 * exercise the exact production comparison instead of a duplicate parser.
 */
export function validateTranslationBehaviorCoverageClaims(
  reportValue: unknown,
  manifestValue: unknown,
  reportStatus: "COMPLETE" | "PARTIAL",
  closure: ReturnType<typeof validateBatchClosure>,
): TranslationBehaviorCoverage {
  if (!isRecord(reportValue) || !isRecord(manifestValue)) {
    fail(409, "TRANSLATION_ARTIFACT_MANIFEST_REPORT_MISMATCH");
  }
  if (!canonicalEqual(manifestValue.behavior_coverage, reportValue.behavior_coverage)) {
    fail(409, "TRANSLATION_ARTIFACT_MANIFEST_REPORT_MISMATCH");
  }
  return validateBehaviorCoverage(reportValue.behavior_coverage, reportStatus, closure);
}

async function validateManifestFiles(
  pipeline: string,
  manifest: Record<string, unknown>,
  archiveEntries: Map<string, Buffer>,
  manifestFile: StableFile,
): Promise<void> {
  if (!Array.isArray(manifest.files) || manifest.files.length < 1) {
    fail(409, "TRANSLATION_ARTIFACT_MANIFEST_FILES_INVALID");
  }
  const expectedPaths = new Set<string>();
  for (const descriptor of manifest.files) {
    if (
      !isRecord(descriptor)
      || !safeRelativeArtifactPath(descriptor.path)
      || expectedPaths.has(descriptor.path)
      || !nonNegativeInteger(descriptor.bytes)
      || typeof descriptor.sha256 !== "string"
      || !digestPattern.test(descriptor.sha256)
    ) fail(409, "TRANSLATION_ARTIFACT_MANIFEST_FILE_DESCRIPTOR_INVALID");
    expectedPaths.add(descriptor.path);
    const disk = await readStablePipelineFile(
      pipeline,
      descriptor.path,
      MAX_PIPELINE_ARTIFACT_BYTES,
      true,
    );
    const archived = archiveEntries.get(descriptor.path);
    if (
      disk.bytes !== descriptor.bytes
      || disk.sha256 !== descriptor.sha256
      || !archived
      || archived.byteLength !== descriptor.bytes
      || createHash("sha256").update(archived).digest("hex") !== descriptor.sha256
      || !archived.equals(disk.content)
    ) fail(409, "TRANSLATION_ARTIFACT_MANIFEST_FILE_INTEGRITY_MISMATCH");
  }
  for (const required of [
    "project-graph.json",
    "repository-route-plan.json",
    "repository-discovery-report.json",
    "batch/batch-report.json",
    "batch/batch-checkpoint.jsonl",
    "assembled/assembly-manifest.json",
  ]) {
    if (!expectedPaths.has(required)) fail(409, "TRANSLATION_ARTIFACT_REQUIRED_EVIDENCE_MISSING");
  }
  const archiveManifest = archiveEntries.get("artifact-manifest.json");
  if (!archiveManifest || !archiveManifest.equals(manifestFile.content)) {
    fail(409, "TRANSLATION_ARTIFACT_ARCHIVED_MANIFEST_MISMATCH");
  }
  expectedPaths.add("artifact-manifest.json");
  if (
    archiveEntries.size !== expectedPaths.size
    || [...archiveEntries.keys()].some((entry) => !expectedPaths.has(entry))
  ) fail(409, "TRANSLATION_ARTIFACT_ZIP_ENTRY_SET_MISMATCH");
}

export type TranslationPipelineAdmission = {
  repositoryRef: string;
  sourceLanguage: TranslationLanguageId;
  targetLanguage: TranslationLanguageId;
  repositoryProfile: string;
  repositoryEvidenceSha256: string;
  repositoryEvidenceBytes: number;
};

/**
 * Re-derive the pipeline decision from raw disk and ZIP bytes. This is kept
 * separate from process execution so recovery and adversarial tests exercise
 * the same fail-closed admission logic.
 */
export async function validateTranslationPipelineEvidence(
  pipeline: string,
  admission: TranslationPipelineAdmission,
): Promise<ValidatedPipelineEvidence> {
  let pipelineDetails;
  try {
    pipelineDetails = await lstat(pipeline);
  } catch {
    fail(409, "TRANSLATION_PIPELINE_OUTPUT_MISSING");
  }
  if (pipelineDetails.isSymbolicLink() || !pipelineDetails.isDirectory()) {
    fail(409, "TRANSLATION_PIPELINE_OUTPUT_UNSAFE");
  }
  if (
    !digestPattern.test(admission.repositoryEvidenceSha256)
    || !nonNegativeInteger(admission.repositoryEvidenceBytes)
    || admission.repositoryEvidenceBytes < 1
  ) fail(409, "TRANSLATION_JOB_REPOSITORY_GATE_MISSING");

  const reportFile = await readStablePipelineFile(
    pipeline,
    "repository-pipeline-report.json",
    MAX_PIPELINE_JSON_BYTES,
  );
  const manifestFile = await readStablePipelineFile(
    pipeline,
    "artifact-manifest.json",
    MAX_PIPELINE_JSON_BYTES,
  );
  const graphFile = await readStablePipelineFile(
    pipeline,
    "project-graph.json",
    MAX_PIPELINE_JSON_BYTES,
  );
  const artifactFile = await readStablePipelineFile(
    pipeline,
    "repository-migration-artifact.zip",
    MAX_PIPELINE_ARTIFACT_BYTES,
  );
  const report = parseJsonRecord(reportFile, "TRANSLATION_PIPELINE_REPORT_INVALID");
  const manifest = parseJsonRecord(manifestFile, "TRANSLATION_ARTIFACT_MANIFEST_INVALID");
  const graph = parseJsonRecord(graphFile, "TRANSLATION_PIPELINE_PROJECT_GRAPH_INVALID");
  const archiveEntries = unzipEvidence(artifactFile.content);

  const reportStatus = report.status;
  if (reportStatus !== "COMPLETE" && reportStatus !== "PARTIAL") {
    fail(409, "TRANSLATION_PIPELINE_STATUS_INVALID");
  }
  const repositoryComplete = report.repository_complete;
  const expectedRepositoryStatus = reportStatus === "COMPLETE" ? "PASSED_LOCAL" : "LIMITED";
  const expectedLocalEvidence = reportStatus === "COMPLETE" ? "PASSED" : "LIMITED";
  if (
    report.schema_version !== "1.0.0"
    || report.kind !== "elmos.repository-pipeline-report"
    || typeof repositoryComplete !== "boolean"
    || report.repository_ref !== admission.repositoryRef
    || report.source_language !== admission.sourceLanguage
    || report.target_language !== admission.targetLanguage
    || report.route_id !== `${admission.sourceLanguage}-to-${admission.targetLanguage}`
    || report.profile !== admission.repositoryProfile
    || typeof report.snapshot_sha256 !== "string"
    || !digestPattern.test(report.snapshot_sha256)
    || report.repository_execution_status !== expectedRepositoryStatus
    || report.local_execution_evidence !== expectedLocalEvidence
    || (reportStatus === "COMPLETE" && repositoryComplete !== true)
    || report.independent_verification_status !== "NOT_RUN"
    || report.external_verification_status !== "NOT_RUN"
    || report.certification_status !== "NOT_CERTIFIED"
  ) fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");

  const closure = validateBatchClosure(report, reportStatus);
  validateProjectGraphEvidence(
    graph,
    report.project_graph,
    admission.repositoryRef,
    repositoryComplete,
  );
  const semanticCoverage = validateConversionCoverage(
    report.conversion_coverage,
    admission.sourceLanguage,
    reportStatus,
    graph,
    closure.includedUnitCount,
  );
  const behaviorCoverage = validateTranslationBehaviorCoverageClaims(
    report,
    manifest,
    reportStatus,
    closure,
  );
  if (
    !validBuildVerification(report.build_verification)
    || !isRecord(report.build_verification)
    || !isRecord(report.build_verification.toolchain)
    || report.build_verification.toolchain.language !== admission.targetLanguage
  ) fail(409, "TRANSLATION_PIPELINE_BUILD_VERIFICATION_INVALID");
  const artifact = report.artifact;
  if (
    !isRecord(artifact)
    || artifact.path !== "repository-migration-artifact.zip"
    || artifact.sha256 !== artifactFile.sha256
    || artifact.bytes !== artifactFile.bytes
  ) fail(409, "TRANSLATION_PIPELINE_ARTIFACT_DESCRIPTOR_INVALID");

  if (
    manifest.schema_version !== "1.0.0"
    || manifest.kind !== "elmos.repository-migration-artifact-manifest"
    || manifest.status !== reportStatus
    || manifest.repository_ref !== admission.repositoryRef
    || manifest.snapshot_sha256 !== report.snapshot_sha256
    || manifest.route_id !== report.route_id
    || manifest.source_language !== admission.sourceLanguage
    || manifest.target_language !== admission.targetLanguage
    || manifest.profile !== admission.repositoryProfile
    || manifest.unit_batch_status !== report.unit_batch_status
    || manifest.repository_complete !== repositoryComplete
    || manifest.local_execution_evidence !== expectedLocalEvidence
    || manifest.repository_execution_status !== expectedRepositoryStatus
    || manifest.independent_verification_status !== "NOT_RUN"
    || manifest.external_verification_status !== "NOT_RUN"
    || manifest.certification_status !== "NOT_CERTIFIED"
    || !canonicalEqual(manifest.project_graph, report.project_graph)
    || !canonicalEqual(manifest.conversion_coverage, report.conversion_coverage)
    || !canonicalEqual(manifest.behavior_coverage, report.behavior_coverage)
  ) fail(409, "TRANSLATION_ARTIFACT_MANIFEST_REPORT_MISMATCH");
  await validateManifestFiles(pipeline, manifest, archiveEntries, manifestFile);

  return {
    report,
    semanticCoverage,
    behaviorCoverage,
    artifactPath: artifactFile.path,
    artifactBytes: artifactFile.bytes,
    artifactSha256: artifactFile.sha256,
  };
}

async function materializedDirectory(base: string, identifier: string, code: string): Promise<string> {
  if (!identifierPattern.test(identifier)) fail(400, `${code}_ID_INVALID`);
  const candidate = confined(base, identifier);
  let resolved: string;
  try {
    resolved = await realpath(candidate);
  } catch {
    fail(400, `${code}_NOT_FOUND`);
  }
  if (resolved !== candidate || !resolved.startsWith(`${base}${path.sep}`)) {
    fail(400, `${code}_PATH_UNSAFE`);
  }
  const details = await stat(resolved);
  if (!details.isDirectory()) fail(400, `${code}_NOT_DIRECTORY`);
  return resolved;
}

function command(
  runner: TranslationRunnerConfig,
  job: TranslationJob,
  source: string,
  cases: string,
  pipeline: string,
): { executable: string; args: string[] } {
  const routeArgs = [
    "repository-pipeline",
    "--repository", source,
    "--repository-ref", job.repositoryRef,
    "--source-language", job.sourceLanguage,
    "--target-language", job.targetLanguage,
    "--cases-directory", cases,
    "--output", pipeline,
  ];
  if (runner.executor === "HOST_DEVELOPMENT") {
    return {
      executable: runner.uv,
      args: [
        "--directory",
        path.join(/* turbopackIgnore: true */ runner.repositoryRoot, "engines/polyglot-route-engine"),
        "run",
        "--locked",
        "elmos-polyglot-route",
        ...routeArgs,
      ],
    };
  }
  return {
    executable: runner.containerEngine ?? "",
    args: [
      "run", "--rm",
      "--network", "none",
      "--read-only",
      "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=256m",
      "--cap-drop", "ALL",
      "--security-opt", "no-new-privileges",
      "--pids-limit", "512",
      "--memory", "3g",
      "--cpus", "2",
      "--mount", `type=bind,source=${runner.repositoryRoot},destination=/elmos,readonly`,
      "--mount", `type=bind,source=${source},destination=/source,readonly`,
      "--mount", `type=bind,source=${cases},destination=/cases,readonly`,
      "--mount", `type=bind,source=${pipeline},destination=/work`,
      "--env", "PYTHONPATH=/elmos/engines/polyglot-route-engine/src",
      runner.containerImage ?? "",
      "python", "-m", "elmos_polyglot_route.cli",
      ...routeArgs.map((argument) => argument
        .replace(source, "/source")
        .replace(cases, "/cases")
        .replace(pipeline, "/work")),
    ],
  };
}

async function runChild(
  executable: string,
  args: string[],
  job: TranslationJob,
  processKey: string,
): Promise<number> {
  return new Promise((resolve, reject) => {
    const child = spawn(executable, args, {
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, NO_COLOR: "1" },
    });
    state.active.set(processKey, child);
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      setTimeout(() => child.kill("SIGKILL"), 5_000).unref();
    }, 20 * 60_000);
    child.stdout.on("data", (chunk: Buffer) => appendLog(job, "stdout", chunk.toString("utf-8")));
    child.stderr.on("data", (chunk: Buffer) => appendLog(job, "stderr", chunk.toString("utf-8")));
    child.once("error", reject);
    child.once("close", (exitCode) => {
      clearTimeout(timer);
      state.active.delete(processKey);
      resolve(exitCode ?? 1);
    });
  });
}

async function execute(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
): Promise<void> {
  const processKey = key(context, job.id);
  state.scheduled.delete(processKey);
  if (state.cancelled.has(processKey)) return;
  let requeued = false;
  let queueLease: DurableJobLease | null = null;
  let leaseHeartbeat: NodeJS.Timeout | null = null;
  let metering: MeteredExecution | null = null;
  try {
    assertCurrentRepositoryAdmission(job);
    try {
      queueLease = await DurableJobLease.acquire({
        configuration: durableQueueConfiguration(runner.root, "translation"),
        tenantId: context.tenantId,
        jobId: job.id,
        createdAt: job.createdAt,
        inputDigest: createHash("sha256").update(JSON.stringify({
          repositoryRef: job.repositoryRef,
          casesBundleId: job.casesBundleId,
          sourceLanguage: job.sourceLanguage,
          targetLanguage: job.targetLanguage,
          repositoryExecutionStatus: job.repositoryExecutionStatus,
          repositoryProfile: job.repositoryProfile,
          repositoryEvidenceRef: job.repositoryEvidenceRef,
          repositoryEvidenceSha256: job.repositoryEvidenceSha256,
          repositoryEvidenceBytes: job.repositoryEvidenceBytes,
        })).digest("hex"),
      });
      leaseHeartbeat = setInterval(() => {
        void queueLease?.heartbeat().catch(() => {
          state.active.get(processKey)?.kill("SIGTERM");
        });
      }, queueLease.heartbeatIntervalMs);
      leaseHeartbeat.unref();
    } catch (error) {
      if (error instanceof DurableLeaseError && error.retryable) {
        job.status = "QUEUED";
        job.stage = "queued";
        job.reason = error.code;
        appendLog(job, "system", `Queue admission delayed: ${error.code}.`);
        await persist(runner, context, job);
        state.scheduled.add(processKey);
        requeued = true;
        setTimeout(
          () => void execute(runner, context, job),
          1_000 + Math.floor(Math.random() * 2_000),
        ).unref();
        return;
      }
      throw error;
    }
    metering = await beginMeteredExecution(`translation-${job.id}`);
    const source = await materializedDirectory(
      runner.sourceRoot,
      job.workspaceId,
      "TRANSLATION_SOURCE_WORKSPACE",
    );
    const cases = await materializedDirectory(
      runner.casesRoot,
      job.casesBundleId,
      "TRANSLATION_CASES_BUNDLE",
    );
    const pipeline = confined(jobRoot(runner, context, job.id), "pipeline");
    await mkdir(pipeline, { recursive: true, mode: 0o700 });
    job.status = "RUNNING";
    job.stage = "pipeline";
    job.progress = 15;
    appendLog(job, "system", `Pipeline started with ${runner.executor}; source and cases are read-only.`);
    await persist(runner, context, job);
    const invocation = command(runner, job, source, cases, pipeline);
    const exitCode = await runChild(invocation.executable, invocation.args, job, processKey);
    if (state.cancelled.has(processKey)) {
      job.status = "CANCELLED";
      job.stage = "cancelled";
      job.reason = "CANCELLED_BY_AUTHORIZED_ACTOR";
      job.progress = 100;
      await persist(runner, context, job);
      return;
    }
    if (exitCode !== 0) fail(409, "TRANSLATION_PIPELINE_BLOCKED");
    const validated = await validateTranslationPipelineEvidence(pipeline, {
      repositoryRef: job.repositoryRef,
      sourceLanguage: job.sourceLanguage,
      targetLanguage: job.targetLanguage,
      repositoryProfile: job.repositoryProfile,
      repositoryEvidenceSha256: job.repositoryEvidenceSha256,
      repositoryEvidenceBytes: job.repositoryEvidenceBytes,
    });
    const report = validated.report;
    const repositoryComplete = report.repository_complete as boolean;
    job.artifactSha256 = validated.artifactSha256;
    job.artifactSize = validated.artifactBytes;
    job.snapshotSha256 = String(report.snapshot_sha256);
    job.readyCount = Number(report.ready_count);
    job.workUnitCount = Number(report.work_unit_count);
    job.includedUnitCount = Number(report.included_unit_count);
    job.statusCounts = report.status_counts as Record<string, number>;
    job.repositoryComplete = repositoryComplete;
    job.projectGraph = report.project_graph as NonNullable<TranslationJob["projectGraph"]>;
    job.semanticCoverage = validated.semanticCoverage;
    job.behaviorCoverage = validated.behaviorCoverage;
    job.buildVerification = report.build_verification as NonNullable<TranslationJob["buildVerification"]>;
    job.stage = "metering";
    job.progress = 99;
    job.artifactReady = false;
    await metering?.finish(true);
    metering = null;
    job.status = report.status as "COMPLETE" | "PARTIAL";
    job.stage = "complete";
    job.progress = 100;
    job.artifactReady = true;
    appendLog(job, "system", `Pipeline ${job.status}; artifact digest ${validated.artifactSha256}.`);
    await persist(runner, context, job);
  } catch (error) {
    if (metering) {
      try {
        await metering.finish(false);
      } catch (meteringError) {
        error = meteringError;
      }
      metering = null;
    }
    if (job.status === "CANCELLED") return;
    job.status = "BLOCKED";
    job.stage = "blocked";
    job.progress = 100;
    job.artifactReady = false;
    job.reason = error instanceof Error ? error.message : "TRANSLATION_PIPELINE_BLOCKED";
    appendLog(job, "system", `Pipeline blocked: ${job.reason}`);
    await persist(runner, context, job);
  } finally {
    if (metering) {
      try {
        await metering.finish(false);
      } catch (error) {
        job.status = "BLOCKED";
        job.stage = "blocked";
        job.artifactReady = false;
        job.reason = error instanceof Error ? error.message : "USAGE_SETTLEMENT_FAILED";
        await persist(runner, context, job);
      }
    }
    state.active.delete(processKey);
    if (leaseHeartbeat) clearInterval(leaseHeartbeat);
    if (queueLease) {
      const outcome = job.status === "COMPLETE" || job.status === "PARTIAL"
        ? "SUCCEEDED"
        : job.status === "CANCELLED"
          ? "CANCELLED"
          : job.status === "BLOCKED"
            ? "BLOCKED"
            : "FAILED";
      try {
        await queueLease.release(outcome);
      } catch {
        job.status = "BLOCKED";
        job.stage = "blocked";
        job.reason = "QUEUE_LEASE_RELEASE_FAILED";
        await persist(runner, context, job);
      }
    }
    if (!requeued) {
      state.scheduled.delete(processKey);
      state.cancelled.delete(processKey);
    }
  }
}

function schedule(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
): void {
  const processKey = key(context, job.id);
  if (state.active.has(processKey) || state.scheduled.has(processKey)) return;
  state.scheduled.add(processKey);
  setImmediate(() => void execute(runner, context, job));
}

function repositoryRouteAdmission(
  capability: TranslationCapabilityResponse,
  sourceLanguage: TranslationLanguageId,
  targetLanguage: TranslationLanguageId,
): {
  repositoryProfile: string;
  repositoryEvidenceRef: string;
  repositoryEvidenceSha256: string;
  repositoryEvidenceBytes: number;
} {
  const route = capability.routes.find(
    (candidate) => candidate.source === sourceLanguage && candidate.target === targetLanguage,
  );
  if (!route || route.localExecution !== "PASSED") {
    fail(409, "TRANSLATION_ROUTE_NOT_LOCALLY_EXECUTABLE");
  }
  if (
    route.repositoryExecutionStatus !== "PASSED"
    || !route.repositoryProfile
    || !route.repositoryEvidenceRef
    || !route.repositoryEvidenceSha256
    || !nonNegativeInteger(route.repositoryEvidenceBytes)
    || route.repositoryEvidenceBytes < 1
  ) {
    fail(409, "TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE");
  }
  return {
    repositoryProfile: route.repositoryProfile,
    repositoryEvidenceRef: route.repositoryEvidenceRef,
    repositoryEvidenceSha256: route.repositoryEvidenceSha256,
    repositoryEvidenceBytes: route.repositoryEvidenceBytes,
  };
}

function assertCurrentRepositoryAdmission(job: TranslationJob): void {
  if (
    job.repositoryExecutionStatus !== "PASSED"
    || !job.repositoryProfile
    || !job.repositoryEvidenceRef
    || !digestPattern.test(job.repositoryEvidenceSha256)
    || !nonNegativeInteger(job.repositoryEvidenceBytes)
    || job.repositoryEvidenceBytes < 1
  ) {
    fail(409, "TRANSLATION_JOB_REPOSITORY_GATE_MISSING");
  }
  let capability: TranslationCapabilityResponse;
  try {
    capability = readTranslationExecutionCapability();
  } catch {
    fail(409, "TRANSLATION_REPOSITORY_GATE_UNAVAILABLE");
  }
  const current = repositoryRouteAdmission(
    capability,
    job.sourceLanguage,
    job.targetLanguage,
  );
  if (
    job.repositoryProfile !== current.repositoryProfile
    || job.repositoryEvidenceRef !== current.repositoryEvidenceRef
    || job.repositoryEvidenceSha256 !== current.repositoryEvidenceSha256
    || job.repositoryEvidenceBytes !== current.repositoryEvidenceBytes
  ) {
    fail(409, "TRANSLATION_REPOSITORY_GATE_CHANGED");
  }
}

export async function createTranslationJob(
  context: AuthorizedContext,
  request: {
    workspaceId?: string;
    repositoryWorkspaceId?: string;
    casesBundleId?: string;
    sourceLanguage?: TranslationLanguageId;
    targetLanguage?: TranslationLanguageId;
  },
): Promise<TranslationJob> {
  const runner = runnerConfig();
  const sourceLanguage = request.sourceLanguage;
  const targetLanguage = request.targetLanguage;
  if (
    !sourceLanguage || !targetLanguage
    || !languages.has(sourceLanguage) || !languages.has(targetLanguage)
    || sourceLanguage === targetLanguage
  ) {
    fail(400, "TRANSLATION_ROUTE_INVALID");
  }
  const capability = readTranslationExecutionCapability();
  const repositoryAdmission = repositoryRouteAdmission(
    capability,
    sourceLanguage,
    targetLanguage,
  );
  let workspaceId = request.workspaceId ?? "";
  const casesBundleId = request.casesBundleId ?? "";
  let repositoryWorkspaceId: string | undefined;
  let repositoryCommit: string | undefined;
  if (request.repositoryWorkspaceId) {
    const materialized = await repositoryTranslationWorkspace({
      tenantId: context.tenantId,
      actor: context.actor,
      accessToken: context.accessToken,
      workspaceId: request.repositoryWorkspaceId,
      sourceRoot: runner.sourceRoot,
    });
    workspaceId = materialized.materializedId;
    repositoryWorkspaceId = request.repositoryWorkspaceId;
    repositoryCommit = materialized.currentHeadCommit;
  }
  await materializedDirectory(runner.sourceRoot, workspaceId, "TRANSLATION_SOURCE_WORKSPACE");
  await materializedDirectory(runner.casesRoot, casesBundleId, "TRANSLATION_CASES_BUNDLE");
  const now = new Date().toISOString();
  const job: TranslationJob = {
    id: randomUUID(),
    tenantId: context.tenantId,
    actor: context.actor,
    createdAt: now,
    updatedAt: now,
    repositoryRef: repositoryCommit
      ? `repository-workspace:${repositoryWorkspaceId}@${repositoryCommit}`
      : `local:${workspaceId}`,
    workspaceId,
    ...(repositoryWorkspaceId ? { repositoryWorkspaceId } : {}),
    casesBundleId,
    sourceLanguage,
    targetLanguage,
    repositoryExecutionStatus: "PASSED",
    repositoryProfile: repositoryAdmission.repositoryProfile,
    repositoryEvidenceRef: repositoryAdmission.repositoryEvidenceRef,
    repositoryEvidenceSha256: repositoryAdmission.repositoryEvidenceSha256,
    repositoryEvidenceBytes: repositoryAdmission.repositoryEvidenceBytes,
    status: "QUEUED",
    stage: "queued",
    progress: 0,
    executor: runner.executor,
    recoveryAttempts: 0,
    artifactReady: false,
    independentVerificationStatus: "NOT_RUN",
    externalVerificationStatus: "NOT_RUN",
    certificationStatus: "NOT_CERTIFIED",
    logs: [],
  };
  appendLog(
    job,
    "system",
    `Job accepted for ${sourceLanguage}-to-${targetLanguage} under repository profile ${job.repositoryProfile}.`,
  );
  await persist(runner, context, job);
  schedule(runner, context, job);
  return job;
}

async function load(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  jobId: string,
): Promise<TranslationJob> {
  let job: TranslationJob;
  try {
    job = JSON.parse(await readFile(jobFile(runner, context, jobId), "utf-8")) as TranslationJob;
  } catch {
    fail(404, "TRANSLATION_JOB_NOT_FOUND");
  }
  if (job.tenantId !== context.tenantId) fail(404, "TRANSLATION_JOB_NOT_FOUND");
  assertCurrentRepositoryAdmission(job);
  return job;
}

export async function getTranslationJob(
  context: AuthorizedContext,
  jobId: string,
): Promise<TranslationJob> {
  const runner = runnerConfig();
  const job = await load(runner, context, jobId);
  const processKey = key(context, job.id);
  if (
    ["QUEUED", "RUNNING"].includes(job.status)
    && !state.active.has(processKey)
    && !state.scheduled.has(processKey)
  ) {
    job.recoveryAttempts += 1;
    job.stage = "restart-recovery";
    if (job.recoveryAttempts > 2) {
      job.status = "BLOCKED";
      job.stage = "blocked";
      job.reason = "TRANSLATION_RESTART_RECOVERY_LIMIT_EXCEEDED";
    } else {
      job.status = "QUEUED";
      appendLog(job, "system", "Persistent checkpoint recovered; pipeline will resume.");
      schedule(runner, context, job);
    }
    await persist(runner, context, job);
  }
  return job;
}

export async function cancelTranslationJob(
  context: AuthorizedContext,
  jobId: string,
): Promise<TranslationJob> {
  const runner = runnerConfig();
  const job = await load(runner, context, jobId);
  if (!["QUEUED", "RUNNING"].includes(job.status)) fail(409, "TRANSLATION_JOB_NOT_CANCELLABLE");
  const processKey = key(context, job.id);
  state.cancelled.add(processKey);
  state.scheduled.delete(processKey);
  state.active.get(processKey)?.kill("SIGTERM");
  job.status = "CANCELLED";
  job.stage = "cancelled";
  job.progress = 100;
  job.reason = "CANCELLED_BY_AUTHORIZED_ACTOR";
  appendLog(job, "system", `Job cancelled by ${context.actor}.`);
  await persist(runner, context, job);
  return job;
}

export async function translationArtifact(
  context: AuthorizedContext,
  jobId: string,
): Promise<{ path: string; size: number; sha256: string }> {
  const runner = runnerConfig();
  const job = await load(runner, context, jobId);
  if (!job.artifactReady || !job.artifactSha256 || !job.artifactSize) {
    fail(409, "TRANSLATION_ARTIFACT_NOT_READY");
  }
  const pipeline = confined(jobRoot(runner, context, jobId), "pipeline");
  const artifact = await readStablePipelineFile(
    pipeline,
    "repository-migration-artifact.zip",
    MAX_PIPELINE_ARTIFACT_BYTES,
  );
  if (artifact.bytes !== job.artifactSize || artifact.sha256 !== job.artifactSha256) {
    fail(409, "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH");
  }
  return { path: artifact.path, size: artifact.bytes, sha256: artifact.sha256 };
}

export function translationRunnerCapability(): TranslationCapabilityResponse["localRunner"] {
  try {
    const runner = runnerConfig();
    return {
      enabled: true,
      persistence: "FILESYSTEM_ATOMIC",
      auth: "BEARER_TENANT_BOUND",
      isolation: runner.executor,
      recovery: "PERSISTENT_RECONCILIATION",
    };
  } catch {
    return {
      enabled: false,
      persistence: "FILESYSTEM_ATOMIC",
      auth: "BEARER_TENANT_BOUND",
      isolation: "NOT_CONFIGURED",
      recovery: "PERSISTENT_RECONCILIATION",
    };
  }
}

export async function translationRunnerHealth(): Promise<TranslationRunnerHealth> {
  const checkedAt = new Date().toISOString();
  const base = {
    persistence: "FILESYSTEM_ATOMIC" as const,
    auth: "BEARER_TENANT_BOUND" as const,
    recovery: "PERSISTENT_RECONCILIATION" as const,
    activeJobs: state.active.size + state.scheduled.size,
    checkedAt,
  };
  if (process.env.ELMOS_LOCAL_RUNNER_ENABLED !== "true") {
    return {
      ...base,
      status: "DISABLED",
      isolation: "NOT_CONFIGURED",
      sourceStorage: "NOT_RUN",
    };
  }
  try {
    const runner = runnerConfig();
    await mkdir(runner.root, { recursive: true, mode: 0o700 });
    await access(runner.root, fsConstants.R_OK | fsConstants.W_OK | fsConstants.X_OK);
    await access(runner.sourceRoot, fsConstants.R_OK | fsConstants.X_OK);
    await access(runner.casesRoot, fsConstants.R_OK | fsConstants.X_OK);
    if (runner.executor === "ROOTLESS_CONTAINER") {
      const sharedRunnerHealth = await generationRunnerHealth();
      if (sharedRunnerHealth.status !== "READY" || sharedRunnerHealth.isolation !== "ROOTLESS_CONTAINER") {
        fail(503, sharedRunnerHealth.reason ?? "ROOTLESS_RUNNER_PREFLIGHT_BLOCKED");
      }
    }
    return {
      ...base,
      status: "READY",
      isolation: runner.executor,
      sourceStorage: "READ_ONLY",
    };
  } catch (error) {
    return {
      ...base,
      status: "BLOCKED",
      isolation: "NOT_CONFIGURED",
      sourceStorage: "BLOCKED",
      reason: error instanceof Error ? error.message : "TRANSLATION_RUNNER_BLOCKED",
    };
  }
}

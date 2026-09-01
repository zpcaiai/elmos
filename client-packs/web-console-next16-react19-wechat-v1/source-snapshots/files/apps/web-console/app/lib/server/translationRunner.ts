import { createHash, randomUUID } from "node:crypto";
import { spawn, type ChildProcess } from "node:child_process";
import {
  accessSync,
  existsSync,
  lstatSync,
  mkdirSync,
  realpathSync,
  statSync,
  type Stats,
} from "node:fs";
import { inflateRawSync } from "node:zlib";
import {
  access,
  lstat,
  mkdir,
  open,
  readFile,
  realpath,
  rename,
  rm,
  stat,
  writeFile,
  type FileHandle,
} from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import path from "node:path";
import type { NextRequest } from "next/server";
import type {
  TranslationBehaviorCoverage,
  TranslationJob,
  TranslationJobLog,
  TranslationCapabilityResponse,
  TranslationExecutionRuntimeReceipt,
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
  withDurableQueueControlLock,
} from "./durableJobLease";
import {
  BUNDLE_MANIFEST_PATH,
  MAX_FUNCTIONAL_REPORT_BUNDLE_BYTES,
  translationConversionBundleFiles,
  validateTranslationConversion,
  validateTranslationConversionBundleArchive,
  validateTranslationConversionBundleManifest,
  validateTranslationCodeArtifactArchive,
  validateTranslationConversionDocument,
  validateTranslationConversionIndex,
  validateTranslationConversionMarkdown,
  validateTranslationConversionShardDocuments,
  validateTranslationPreflight,
} from "./translationConversionReport";

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
  generations: Map<string, number>;
  writes: Map<string, Promise<void>>;
};

const globalState = globalThis as typeof globalThis & {
  __elmosTranslationRunnerState?: TranslationProcessState;
};
const state = globalState.__elmosTranslationRunnerState ??= {
  active: new Map<string, ChildProcess>(),
  scheduled: new Set<string>(),
  cancelled: new Set<string>(),
  generations: new Map<string, number>(),
  writes: new Map<string, Promise<void>>(),
};
state.active ??= new Map<string, ChildProcess>();
state.scheduled ??= new Set<string>();
state.cancelled ??= new Set<string>();
state.generations ??= new Map<string, number>();
state.writes ??= new Map<string, Promise<void>>();

function executionIsCurrent(processKey: string, generation: number): boolean {
  return state.generations.get(processKey) === generation
    && !state.cancelled.has(processKey);
}

const identifierPattern = /^[a-z0-9][a-z0-9._-]{2,80}$/;
const jobIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const digestPattern = /^[0-9a-f]{64}$/;
const immutableImagePattern = /^[^@\s]+@sha256:[0-9a-f]{64}$/;
const containerIdPattern = /^[0-9a-f]{12,64}$/;
const translationJobLabel = "io.elmos.translation.job-id";
const translationExecutionLabel = "io.elmos.translation.execution-id";
const translationPhaseLabel = "io.elmos.translation.phase";
const terminalTranslationStatuses = new Set<TranslationJob["status"]>([
  "COMPLETE",
  "PARTIAL",
  "BLOCKED",
  "CANCELLED",
]);
export const MAX_TRANSLATION_ARTIFACT_BYTES = 256 * 1024 * 1024;
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

function pathsOverlap(left: string, right: string): boolean {
  return left === right
    || left.startsWith(`${right}${path.sep}`)
    || right.startsWith(`${left}${path.sep}`);
}

function canonicalDirectory(raw: string, code: string, create = false): string {
  try {
    if (create) mkdirSync(raw, { recursive: true, mode: 0o700 });
    const lexical = lstatSync(raw);
    if (lexical.isSymbolicLink() || !lexical.isDirectory()) fail(503, code);
    const resolved = realpathSync(raw);
    if (!statSync(resolved).isDirectory()) fail(503, code);
    return resolved;
  } catch (error) {
    if (error instanceof GenerationRunnerError) throw error;
    fail(503, code);
  }
}

function canonicalExecutable(raw: string, code: string): string {
  try {
    const lexical = lstatSync(raw);
    if (lexical.isSymbolicLink() || !lexical.isFile()) fail(503, code);
    const resolved = realpathSync(raw);
    if (!statSync(resolved).isFile()) fail(503, code);
    accessSync(resolved, fsConstants.R_OK | fsConstants.X_OK);
    return resolved;
  } catch (error) {
    if (error instanceof GenerationRunnerError) throw error;
    fail(503, code);
  }
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
    root: canonicalDirectory(path.resolve(/* turbopackIgnore: true */ root), "TRANSLATION_RUNNER_ROOT_UNSAFE", true),
    repositoryRoot: canonicalDirectory(
      path.resolve(/* turbopackIgnore: true */ repositoryRoot),
      "TRANSLATION_REPOSITORY_ROOT_UNSAFE",
    ),
    sourceRoot: canonicalDirectory(
      path.resolve(/* turbopackIgnore: true */ sourceRoot),
      "TRANSLATION_SOURCE_ROOT_UNSAFE",
    ),
    casesRoot: canonicalDirectory(
      path.resolve(/* turbopackIgnore: true */ casesRoot),
      "TRANSLATION_CASES_ROOT_UNSAFE",
    ),
    uv: canonicalExecutable(
      path.resolve(/* turbopackIgnore: true */ uv),
      "TRANSLATION_RUNNER_UV_UNSAFE",
    ),
  };
  const storageLocations = [
    resolved.root,
    resolved.repositoryRoot,
    resolved.sourceRoot,
    resolved.casesRoot,
  ];
  if (
    resolved.root === path.parse(resolved.root).root
    || storageLocations.some((left, index) => (
      storageLocations.slice(index + 1).some((right) => pathsOverlap(left, right))
    ))
  ) {
    fail(503, "TRANSLATION_RUNNER_ROOT_UNSAFE");
  }
  for (const required of [
    resolved.repositoryRoot,
    resolved.sourceRoot,
    resolved.casesRoot,
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

function clearUnvalidatedReport(job: TranslationJob): void {
  job.reportReady = false;
  delete job.reportJson;
  delete job.reportMarkdown;
  delete job.reportBundle;
  delete job.conversionSummary;
}

function clearPriorExecutionOutputs(job: TranslationJob): void {
  clearUnvalidatedReport(job);
  job.artifactReady = false;
  delete job.artifactSha256;
  delete job.artifactSize;
  delete job.snapshotSha256;
  delete job.readyCount;
  delete job.workUnitCount;
  delete job.includedUnitCount;
  delete job.statusCounts;
  delete job.buildVerification;
}

async function atomicJson(destination: string, serialized: string): Promise<void> {
  await mkdir(path.dirname(destination), { recursive: true, mode: 0o700 });
  const temporary = `${destination}.${randomUUID()}.tmp`;
  await writeFile(temporary, serialized, { mode: 0o600 });
  await rename(temporary, destination);
}

async function persist(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
): Promise<void> {
  job.updatedAt = new Date().toISOString();
  const destination = jobFile(runner, context, job.id);
  const serialized = `${JSON.stringify(job, null, 2)}\n`;
  const prior = state.writes.get(destination) ?? Promise.resolve();
  const queued = prior
    .catch(() => undefined)
    .then(() => atomicJson(destination, serialized));
  state.writes.set(destination, queued);
  try {
    await queued;
  } finally {
    if (state.writes.get(destination) === queued) state.writes.delete(destination);
  }
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

function translationInputDigest(job: TranslationJob): string {
  // The five repository* fields were part of this digest where it was computed
  // inline on the other side of this merge. Extracting the function without them
  // would let two jobs that differ only in their repository evidence collide on
  // one input digest, which nothing downstream would report.
  return createHash("sha256").update(JSON.stringify({
    repositoryRef: job.repositoryRef,
    casesBundleId: job.casesBundleId,
    sourceLanguage: job.sourceLanguage,
    targetLanguage: job.targetLanguage,
    repositoryExecutionStatus: job.repositoryExecutionStatus,
    repositoryProfile: job.repositoryProfile,
    repositoryEvidenceRef: job.repositoryEvidenceRef,
    repositoryEvidenceSha256: job.repositoryEvidenceSha256,
    repositoryEvidenceBytes: job.repositoryEvidenceBytes,
  })).digest("hex");
}

function synchronizeJob(target: TranslationJob, source: TranslationJob): void {
  for (const field of Object.keys(target) as Array<keyof TranslationJob>) {
    if (!(field in source)) delete target[field];
  }
  Object.assign(target, source);
}

async function withTranslationControl<T>(
  runner: TranslationRunnerConfig,
  operation: () => Promise<T>,
): Promise<T> {
  return withDurableQueueControlLock(
    durableQueueConfiguration(runner.root, "translation"),
    operation,
  );
}

async function writeControlledJob(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
): Promise<void> {
  job.updatedAt = new Date().toISOString();
  await atomicJson(jobFile(runner, context, job.id), `${JSON.stringify(job, null, 2)}\n`);
}

async function claimExecution(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  localJob: TranslationJob,
  leaseOwnerId: string,
): Promise<string | undefined> {
  return withTranslationControl(runner, async () => {
    const current = await load(runner, context, localJob.id);
    if (
      terminalTranslationStatuses.has(current.status)
      || current.cancelRequestedAt
    ) return undefined;
    const executionId = randomUUID();
    clearPriorExecutionOutputs(current);
    current.executionId = executionId;
    current.executionLeaseOwnerId = leaseOwnerId;
    delete current.runtimeReceipt;
    await writeControlledJob(runner, context, current);
    synchronizeJob(localJob, current);
    return executionId;
  });
}

async function persistUnclaimedIfActive(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  localJob: TranslationJob,
): Promise<boolean> {
  return withTranslationControl(runner, async () => {
    const current = await load(runner, context, localJob.id);
    if (
      terminalTranslationStatuses.has(current.status)
      || current.cancelRequestedAt
      || current.executionId
      || current.executionLeaseOwnerId
    ) return false;
    const next = { ...localJob, logs: [...localJob.logs] };
    await writeControlledJob(runner, context, next);
    synchronizeJob(localJob, next);
    return true;
  });
}

async function persistExecutionIfCurrent(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  localJob: TranslationJob,
  executionId: string,
): Promise<boolean> {
  return withTranslationControl(runner, async () => {
    const current = await load(runner, context, localJob.id);
    if (
      current.executionId !== executionId
      || current.cancelRequestedAt
      || current.status === "CANCELLED"
    ) return false;
    const next = {
      ...localJob,
      executionId,
      executionLeaseOwnerId: current.executionLeaseOwnerId,
      logs: [...localJob.logs],
    };
    delete next.cancelRequestedAt;
    delete next.cancelRequestedBy;
    await writeControlledJob(runner, context, next);
    synchronizeJob(localJob, next);
    return true;
  });
}

async function durableExecutionIsCurrent(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  jobId: string,
  executionId: string,
): Promise<boolean> {
  try {
    const current = await load(runner, context, jobId);
    return current.executionId === executionId
      && !current.cancelRequestedAt
      && current.status !== "CANCELLED";
  } catch {
    return false;
  }
}

async function sha256OpenPipelineFile(
  handle: FileHandle,
  expected: Stats,
  errorCode: string,
): Promise<string> {
  const digest = createHash("sha256");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  let position = 0;
  while (position < expected.size) {
    const { bytesRead } = await handle.read(
      buffer,
      0,
      Math.min(buffer.length, expected.size - position),
      position,
    );
    if (bytesRead <= 0) fail(409, errorCode);
    digest.update(buffer.subarray(0, bytesRead));
    position += bytesRead;
  }
  const after = await handle.stat();
  if (
    after.dev !== expected.dev
    || after.ino !== expected.ino
    || after.size !== expected.size
    || after.mtimeMs !== expected.mtimeMs
    || after.ctimeMs !== expected.ctimeMs
    || after.nlink !== expected.nlink
  ) fail(409, errorCode);
  return digest.digest("hex");
}

type OpenedPipelineFile = {
  handle: FileHandle;
  path: string;
  size: number;
  sha256: string;
  stats: Stats;
};

function sameOpenFileStats(left: Stats, right: Stats): boolean {
  return left.dev === right.dev
    && left.ino === right.ino
    && left.size === right.size
    && left.mtimeMs === right.mtimeMs
    && left.ctimeMs === right.ctimeMs
    && left.nlink === right.nlink;
}

async function boundedOpenPipelineFile(
  pipeline: string,
  relativePath: string,
  maximumBytes: number,
  errorCode: string,
): Promise<OpenedPipelineFile> {
  const candidate = confined(pipeline, relativePath);
  let resolved: string;
  let resolvedPipeline: string;
  try {
    const linkInfo = await lstat(candidate);
    if (!linkInfo.isFile() || linkInfo.isSymbolicLink()) fail(409, errorCode);
    resolvedPipeline = await realpath(pipeline);
    resolved = await realpath(candidate);
  } catch (error) {
    if (error instanceof GenerationRunnerError) throw error;
    fail(409, errorCode);
  }
  if (
    resolved !== path.resolve(resolvedPipeline, relativePath)
    || !resolved.startsWith(`${resolvedPipeline}${path.sep}`)
  ) fail(409, errorCode);
  let handle: FileHandle;
  try {
    handle = await open(resolved, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
  } catch {
    fail(409, errorCode);
  }
  try {
    const info = await handle.stat();
    if (!info.isFile() || info.nlink !== 1 || info.size < 1 || info.size > maximumBytes) {
      fail(409, errorCode);
    }
    const sha256 = await sha256OpenPipelineFile(handle, info, errorCode);
    return { handle, path: resolved, size: info.size, sha256, stats: info };
  } catch (error) {
    await handle.close().catch(() => undefined);
    throw error;
  }
}

async function verifiedOpenPipelineFile(
  pipeline: string,
  descriptor: { path: string; bytes: number; sha256: string },
  errorCode: string,
): Promise<OpenedPipelineFile> {
  const opened = await boundedOpenPipelineFile(pipeline, descriptor.path, descriptor.bytes, errorCode);
  if (opened.size !== descriptor.bytes || opened.sha256 !== descriptor.sha256) {
    await opened.handle.close().catch(() => undefined);
    fail(409, errorCode);
  }
  return opened;
}

async function readOpenedPipelineFile(opened: OpenedPipelineFile, errorCode: string): Promise<Buffer> {
  const content = Buffer.allocUnsafe(opened.size);
  let position = 0;
  while (position < content.length) {
    const { bytesRead } = await opened.handle.read(
      content,
      position,
      content.length - position,
      position,
    );
    if (bytesRead <= 0) fail(409, errorCode);
    position += bytesRead;
  }
  const after = await opened.handle.stat();
  if (
    !sameOpenFileStats(opened.stats, after)
    || createHash("sha256").update(content).digest("hex") !== opened.sha256
  ) fail(409, errorCode);
  return content;
}

async function readBoundedPipelineFile(
  pipeline: string,
  relativePath: string,
  maximumBytes: number,
  errorCode: string,
): Promise<{ content: Buffer; path: string; size: number; sha256: string }> {
  const opened = await boundedOpenPipelineFile(pipeline, relativePath, maximumBytes, errorCode);
  try {
    return {
      content: await readOpenedPipelineFile(opened, errorCode),
      path: opened.path,
      size: opened.size,
      sha256: opened.sha256,
    };
  } finally {
    await opened.handle.close().catch(() => undefined);
  }
}

async function readVerifiedPipelineFile(
  pipeline: string,
  descriptor: { path: string; bytes: number; sha256: string },
  errorCode: string,
): Promise<{ content: Buffer; path: string; size: number; sha256: string }> {
  const opened = await verifiedOpenPipelineFile(pipeline, descriptor, errorCode);
  try {
    return {
      content: await readOpenedPipelineFile(opened, errorCode),
      path: opened.path,
      size: opened.size,
      sha256: opened.sha256,
    };
  } finally {
    await opened.handle.close().catch(() => undefined);
  }
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

export function translationCasesBase(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
): string {
  if (process.env.NODE_ENV !== "production") return runner.casesRoot;
  if (!identifierPattern.test(context.tenantId)) {
    fail(403, "TRANSLATION_TENANT_CASES_BINDING_INVALID");
  }
  return confined(runner.casesRoot, context.tenantId);
}

type TranslationRuntimePhase = TranslationExecutionRuntimeReceipt["phase"];
type BoundedCommandResult = { exitCode: number; stdout: string; stderr: string };

function expectedContainerName(
  jobId: string,
  executionId: string,
  phase: TranslationRuntimePhase,
): string {
  return `elmos-tr-${jobId}-${executionId.replaceAll("-", "")}-${phase}`;
}

function expectedCidFile(
  executionId: string,
  phase: TranslationRuntimePhase,
): string {
  return path.posix.join("runtime", executionId, `${phase}.cid`);
}

function receiptCidPath(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  jobId: string,
  receipt: TranslationExecutionRuntimeReceipt,
): string {
  if (!receipt.cidFile) fail(409, "TRANSLATION_RUNTIME_RECEIPT_INVALID");
  return confined(jobRoot(runner, context, jobId), ...receipt.cidFile.split("/"));
}

function validateRuntimeReceipt(
  job: TranslationJob,
  receipt: TranslationExecutionRuntimeReceipt,
): void {
  if (
    receipt.schemaVersion !== "1.0"
    || !jobIdPattern.test(receipt.executionId)
    || receipt.executionId !== job.executionId
    || !["preflight", "pipeline"].includes(receipt.phase)
    || receipt.executor !== job.executor
    || !["STARTING", "RUNNING", "EXITED", "CLEANUP_VERIFIED", "CLEANUP_UNVERIFIED"].includes(receipt.state)
    || !Number.isSafeInteger(receipt.processGroupId)
    || receipt.processGroupId <= 1
    || receipt.processGroupId === process.pid
    || !Number.isFinite(Date.parse(receipt.startedAt))
    || !Number.isFinite(Date.parse(receipt.updatedAt))
  ) fail(409, "TRANSLATION_RUNTIME_RECEIPT_INVALID");
  if (receipt.executor === "ROOTLESS_CONTAINER") {
    if (
      receipt.containerName !== expectedContainerName(job.id, receipt.executionId, receipt.phase)
      || receipt.cidFile !== expectedCidFile(receipt.executionId, receipt.phase)
      || receipt.labels?.jobId !== job.id
      || receipt.labels.executionId !== receipt.executionId
      || receipt.labels.phase !== receipt.phase
      || (receipt.containerId !== undefined && !containerIdPattern.test(receipt.containerId))
    ) fail(409, "TRANSLATION_RUNTIME_RECEIPT_INVALID");
  } else if (
    receipt.containerName !== undefined
    || receipt.cidFile !== undefined
    || receipt.containerId !== undefined
    || receipt.labels !== undefined
  ) fail(409, "TRANSLATION_RUNTIME_RECEIPT_INVALID");
}

function processGroupAlive(processGroupId: number): boolean {
  try {
    process.kill(-processGroupId, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code !== "ESRCH";
  }
}

function signalProcessGroup(processGroupId: number, signal: NodeJS.Signals): void {
  try {
    process.kill(-processGroupId, signal);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
  }
}

async function waitForProcessGroupExit(processGroupId: number, attempts = 40): Promise<boolean> {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (!processGroupAlive(processGroupId)) return true;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return !processGroupAlive(processGroupId);
}

async function terminateProcessGroup(processGroupId: number): Promise<boolean> {
  if (!Number.isSafeInteger(processGroupId) || processGroupId <= 1 || processGroupId === process.pid) {
    return false;
  }
  if (!processGroupAlive(processGroupId)) return true;
  try {
    signalProcessGroup(processGroupId, "SIGTERM");
  } catch {
    return false;
  }
  if (await waitForProcessGroupExit(processGroupId)) return true;
  try {
    signalProcessGroup(processGroupId, "SIGKILL");
  } catch {
    return false;
  }
  return waitForProcessGroupExit(processGroupId);
}

async function boundedCommand(
  executable: string,
  args: string[],
  timeoutMs = 15_000,
): Promise<BoundedCommandResult> {
  return new Promise((resolve, reject) => {
    let stdout = "";
    let stderr = "";
    let settled = false;
    const child = spawn(executable, args, {
      shell: false,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, NO_COLOR: "1" },
    });
    const finish = (result?: BoundedCommandResult, error?: Error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) reject(error);
      else resolve(result ?? { exitCode: 1, stdout, stderr });
    };
    const timer = setTimeout(() => {
      if (child.pid) {
        try {
          signalProcessGroup(child.pid, "SIGKILL");
        } catch {
          child.kill("SIGKILL");
        }
      }
      finish(undefined, new GenerationRunnerError(502, "CANCEL_CLEANUP_UNVERIFIED"));
    }, timeoutMs);
    timer.unref();
    const capture = (stream: "stdout" | "stderr", chunk: Buffer) => {
      if (stream === "stdout") stdout += chunk.toString("utf8");
      else stderr += chunk.toString("utf8");
      if (Buffer.byteLength(stdout) + Buffer.byteLength(stderr) > 1024 * 1024) {
        if (child.pid) {
          try {
            signalProcessGroup(child.pid, "SIGKILL");
          } catch {
            child.kill("SIGKILL");
          }
        }
        finish(undefined, new GenerationRunnerError(502, "CANCEL_CLEANUP_UNVERIFIED"));
      }
    };
    child.stdout.on("data", (chunk: Buffer) => capture("stdout", chunk));
    child.stderr.on("data", (chunk: Buffer) => capture("stderr", chunk));
    child.once("error", () => finish(
      undefined,
      new GenerationRunnerError(502, "CANCEL_CLEANUP_UNVERIFIED"),
    ));
    child.once("close", (exitCode) => finish({
      exitCode: exitCode ?? 1,
      stdout,
      stderr,
    }));
  });
}

async function readExpectedContainerId(cidFile: string): Promise<string | undefined> {
  try {
    const candidate = (await readFile(cidFile, "utf8")).trim();
    return containerIdPattern.test(candidate) ? candidate : undefined;
  } catch {
    return undefined;
  }
}

async function inspectRuntimeContainer(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
  receipt: TranslationExecutionRuntimeReceipt,
): Promise<{ status: "ABSENT" } | { status: "PRESENT"; containerId: string }> {
  if (!runner.containerEngine || !receipt.containerName || !receipt.labels) {
    fail(409, "TRANSLATION_RUNTIME_RECEIPT_INVALID");
  }
  const inspected = await boundedCommand(runner.containerEngine, [
    "inspect",
    "--format",
    "{{json .}}",
    receipt.containerName,
  ]);
  if (inspected.exitCode !== 0) {
    const absent = await boundedCommand(runner.containerEngine, [
      "ps",
      "--all",
      "--filter", `label=${translationJobLabel}=${job.id}`,
      "--filter", `label=${translationExecutionLabel}=${receipt.executionId}`,
      "--filter", `label=${translationPhaseLabel}=${receipt.phase}`,
      "--format", "{{.ID}}",
    ]);
    if (absent.exitCode === 0 && absent.stdout.trim() === "") return { status: "ABSENT" };
    fail(502, "CANCEL_CLEANUP_UNVERIFIED");
  }
  let document: Record<string, unknown>;
  try {
    document = JSON.parse(inspected.stdout) as Record<string, unknown>;
  } catch {
    fail(502, "CANCEL_CLEANUP_UNVERIFIED");
  }
  const labels = (document.Config as { Labels?: unknown } | undefined)?.Labels;
  const containerId = String(document.Id ?? "");
  const observedName = String(document.Name ?? "").replace(/^\//, "");
  if (
    !containerIdPattern.test(containerId)
    || observedName !== receipt.containerName
    || !labels
    || typeof labels !== "object"
    || Array.isArray(labels)
    || (labels as Record<string, unknown>)[translationJobLabel] !== job.id
    || (labels as Record<string, unknown>)[translationExecutionLabel] !== receipt.executionId
    || (labels as Record<string, unknown>)[translationPhaseLabel] !== receipt.phase
  ) fail(502, "CANCEL_CLEANUP_UNVERIFIED");
  const cidPath = receiptCidPath(runner, context, job.id, receipt);
  let cid = await readExpectedContainerId(cidPath);
  for (let attempt = 0; !cid && attempt < 20; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 25));
    cid = await readExpectedContainerId(cidPath);
  }
  if (!cid || cid !== containerId) fail(502, "CANCEL_CLEANUP_UNVERIFIED");
  return { status: "PRESENT", containerId };
}

async function cleanupRuntimeReceipt(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
): Promise<TranslationExecutionRuntimeReceipt | undefined> {
  const receipt = job.runtimeReceipt;
  if (!receipt) return undefined;
  validateRuntimeReceipt(job, receipt);
  const processExited = receipt.state === "EXITED" || receipt.state === "CLEANUP_VERIFIED"
    ? !processGroupAlive(receipt.processGroupId)
    : await terminateProcessGroup(receipt.processGroupId);
  if (!processExited) fail(502, "CANCEL_CLEANUP_UNVERIFIED");
  if (receipt.executor === "ROOTLESS_CONTAINER") {
    let observation = await inspectRuntimeContainer(runner, context, job, receipt);
    if (observation.status === "PRESENT") {
      receipt.containerId = observation.containerId;
      const stop = await boundedCommand(runner.containerEngine ?? "", [
        "stop", "--time", "5", receipt.containerName ?? "",
      ]);
      if (stop.exitCode !== 0) {
        const kill = await boundedCommand(runner.containerEngine ?? "", [
          "kill", receipt.containerName ?? "",
        ]);
        if (kill.exitCode !== 0) fail(502, "CANCEL_CLEANUP_UNVERIFIED");
      }
      const remove = await boundedCommand(runner.containerEngine ?? "", [
        "rm", "--force", receipt.containerName ?? "",
      ]);
      if (remove.exitCode !== 0) fail(502, "CANCEL_CLEANUP_UNVERIFIED");
      observation = await inspectRuntimeContainer(runner, context, job, receipt);
      if (observation.status !== "ABSENT") fail(502, "CANCEL_CLEANUP_UNVERIFIED");
    }
    await rm(receiptCidPath(runner, context, job.id, receipt), { force: true });
  }
  const now = new Date().toISOString();
  return {
    ...receipt,
    state: "CLEANUP_VERIFIED",
    updatedAt: now,
    cleanupVerifiedAt: now,
  };
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

function preflightCommand(
  runner: TranslationRunnerConfig,
  job: TranslationJob,
  source: string,
  preflightDirectory: string,
  outputName: string,
): { executable: string; args: string[] } {
  const output = confined(preflightDirectory, outputName);
  const routeArgs = [
    "repository-preflight",
    "--repository", source,
    "--repository-ref", job.repositoryRef,
    "--source-language", job.sourceLanguage,
    "--target-language", job.targetLanguage,
    "--output", output,
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
      "--mount", `type=bind,source=${preflightDirectory},destination=/preflight`,
      "--env", "PYTHONPATH=/elmos/engines/polyglot-route-engine/src",
      runner.containerImage ?? "",
      "python", "-m", "elmos_polyglot_route.cli",
      ...routeArgs.map((argument) => argument
        .replace(source, "/source")
        .replace(output, `/preflight/${outputName}`)),
    ],
  };
}

async function runChild(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  executable: string,
  args: string[],
  job: TranslationJob,
  processKey: string,
  executionId: string,
  phase: TranslationRuntimePhase,
  timeoutCode = "TRANSLATION_PIPELINE_TIMEOUT",
  executionCode = "TRANSLATION_PIPELINE_EXECUTION_FAILED",
): Promise<number> {
  const relativeCidFile = expectedCidFile(executionId, phase);
  const cidFile = confined(jobRoot(runner, context, job.id), ...relativeCidFile.split("/"));
  if (runner.executor === "ROOTLESS_CONTAINER") {
    await mkdir(path.dirname(cidFile), { recursive: true, mode: 0o700 });
    await rm(cidFile, { force: true });
  }
  const containerName = expectedContainerName(job.id, executionId, phase);
  const executionArgs = runner.executor === "ROOTLESS_CONTAINER"
    ? [
        args[0],
        "--name", containerName,
        "--cidfile", cidFile,
        "--label", `${translationJobLabel}=${job.id}`,
        "--label", `${translationExecutionLabel}=${executionId}`,
        "--label", `${translationPhaseLabel}=${phase}`,
        ...args.slice(1),
      ]
    : args;

  let child: ChildProcess | undefined;
  let completion: Promise<number> | undefined;
  await withTranslationControl(runner, async () => {
    const current = await load(runner, context, job.id);
    if (
      current.executionId !== executionId
      || current.cancelRequestedAt
      || current.status === "CANCELLED"
    ) return;
    child = spawn(executable, executionArgs, {
      shell: false,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, NO_COLOR: "1" },
    });
    if (!child.pid || child.pid <= 1 || child.pid === process.pid) {
      child.kill("SIGKILL");
      child = undefined;
      fail(409, executionCode);
    }
    const startedAt = new Date().toISOString();
    const receipt: TranslationExecutionRuntimeReceipt = {
      schemaVersion: "1.0",
      executionId,
      phase,
      executor: runner.executor,
      state: "RUNNING",
      processGroupId: child.pid,
      ...(runner.executor === "ROOTLESS_CONTAINER" ? {
        containerName,
        cidFile: relativeCidFile,
        labels: {
          jobId: job.id,
          executionId,
          phase,
        },
      } : {}),
      startedAt,
      updatedAt: startedAt,
    };
    current.runtimeReceipt = receipt;
    await writeControlledJob(runner, context, current);
    job.runtimeReceipt = receipt;
    state.active.set(processKey, child);

    completion = new Promise<number>((resolve, reject) => {
      let settled = false;
      let timedOut = false;
      const finish = async (exitCode: number | null, spawnFailed = false) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (state.active.get(processKey) === child) state.active.delete(processKey);
        try {
          const durable = await load(runner, context, job.id);
          if (!durable.cancelRequestedAt && durable.executionId === executionId) {
            const cleaned = await cleanupRuntimeReceipt(runner, context, durable);
            if (!cleaned) fail(502, "TRANSLATION_RUNTIME_CLEANUP_UNVERIFIED");
            const recorded = await withTranslationControl(runner, async () => {
              const latest = await load(runner, context, job.id);
              if (latest.executionId !== executionId || latest.cancelRequestedAt) return false;
              latest.runtimeReceipt = cleaned;
              await writeControlledJob(runner, context, latest);
              job.runtimeReceipt = cleaned;
              return true;
            });
            if (!recorded) return resolve(exitCode ?? 1);
          }
          if (timedOut) reject(new GenerationRunnerError(409, timeoutCode));
          else if (spawnFailed) reject(new GenerationRunnerError(409, executionCode));
          else resolve(exitCode ?? 1);
        } catch (error) {
          reject(error);
        }
      };
      const timer = setTimeout(() => {
        timedOut = true;
        if (child?.pid) {
          void terminateProcessGroup(child.pid).then((exited) => {
            if (!exited) void finish(null, true);
          });
        } else {
          void finish(null, true);
        }
      }, 20 * 60_000);
      timer.unref();
      child?.stdout?.on("data", (chunk: Buffer) => appendLog(job, "stdout", chunk.toString("utf-8")));
      child?.stderr?.on("data", (chunk: Buffer) => appendLog(job, "stderr", chunk.toString("utf-8")));
      child?.once("error", () => void finish(null, true));
      child?.once("close", (exitCode) => void finish(exitCode));
    });
  });
  if (!child || !completion) fail(409, "TRANSLATION_EXECUTION_FENCED");
  return completion;
}

async function execute(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
  generation: number,
): Promise<void> {
  const processKey = key(context, job.id);
  if (!executionIsCurrent(processKey, generation)) return;
  state.scheduled.delete(processKey);
  let requeued = false;
  let queueLease: DurableJobLease | null = null;
  let leaseHeartbeat: NodeJS.Timeout | null = null;
  let metering: MeteredExecution | null = null;
  let finalizedReportValidated = false;
  let executionId: string | undefined;
  try {
    assertCurrentRepositoryAdmission(job);
    try {
      queueLease = await DurableJobLease.acquire({
        configuration: durableQueueConfiguration(runner.root, "translation"),
        tenantId: context.tenantId,
        jobId: job.id,
        createdAt: job.createdAt,
        inputDigest: translationInputDigest(job),
      });
      if (!executionIsCurrent(processKey, generation)) return;
      executionId = await claimExecution(
        runner,
        context,
        job,
        String(queueLease.ownerId ?? "unavailable-owner"),
      );
      if (!executionId) return;
      leaseHeartbeat = setInterval(() => {
        void queueLease?.heartbeat().catch(() => {
          const child = state.active.get(processKey);
          if (child?.pid) void terminateProcessGroup(child.pid);
        });
      }, queueLease.heartbeatIntervalMs);
      leaseHeartbeat.unref();
    } catch (error) {
      if (!executionIsCurrent(processKey, generation)) return;
      if (error instanceof DurableLeaseError && error.retryable) {
        job.status = "QUEUED";
        job.stage = "queued";
        job.reason = error.code;
        appendLog(job, "system", `Queue admission delayed: ${error.code}.`);
        if (!await persistUnclaimedIfActive(runner, context, job)) return;
        if (!executionIsCurrent(processKey, generation)) return;
        state.scheduled.add(processKey);
        requeued = true;
        setTimeout(
          () => {
            if (executionIsCurrent(processKey, generation)) {
              void execute(runner, context, job, generation);
            }
          },
          1_000 + Math.floor(Math.random() * 2_000),
        ).unref();
        return;
      }
      throw error;
    }
    if (!executionId || !await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    const source = await materializedDirectory(
      runner.sourceRoot,
      job.workspaceId,
      "TRANSLATION_SOURCE_WORKSPACE",
    );
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    const cases = await materializedDirectory(
      translationCasesBase(runner, context),
      job.casesBundleId,
      "TRANSLATION_CASES_BUNDLE",
    );
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    const durableJobRoot = jobRoot(runner, context, job.id);
    const pipeline = confined(durableJobRoot, "pipeline");
    const preflightDirectory = confined(durableJobRoot, "preflight");
    const preflightOutputName = `repository-preflight-${randomUUID()}.json`;
    await Promise.all([
      mkdir(pipeline, { recursive: true, mode: 0o700 }),
      mkdir(preflightDirectory, { recursive: true, mode: 0o700 }),
    ]);
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    job.status = "PRECHECK";
    job.stage = "preflight";
    job.progress = 5;
    appendLog(job, "system", `Non-billing repository preflight started with ${runner.executor}.`);
    if (!await persistExecutionIfCurrent(runner, context, job, executionId)) return;
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    const preflightInvocation = preflightCommand(
      runner,
      job,
      source,
      preflightDirectory,
      preflightOutputName,
    );
    const preflightExitCode = await runChild(
      runner,
      context,
      preflightInvocation.executable,
      preflightInvocation.args,
      job,
      processKey,
      executionId,
      "preflight",
      "TRANSLATION_PREFLIGHT_TIMEOUT",
      "TRANSLATION_PREFLIGHT_EXECUTION_FAILED",
    );
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    if (preflightExitCode !== 0) fail(409, "TRANSLATION_PREFLIGHT_BLOCKED");
    const preflightFile = await readBoundedPipelineFile(
      preflightDirectory,
      preflightOutputName,
      1024 * 1024,
      "TRANSLATION_PREFLIGHT_EVIDENCE_INVALID",
    );
    let preflightDocument: unknown;
    try {
      preflightDocument = JSON.parse(preflightFile.content.toString("utf8"));
    } catch {
      fail(409, "TRANSLATION_PREFLIGHT_EVIDENCE_INVALID");
    }
    const preflight = validateTranslationPreflight(preflightDocument, {
      repositoryRef: job.repositoryRef,
      routeId: `${job.sourceLanguage}-to-${job.targetLanguage}`,
      sourceLanguage: job.sourceLanguage,
      targetLanguage: job.targetLanguage,
    });
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    job.snapshotSha256 = preflight.snapshotSha256;
    if (preflight.status === "REJECTED") {
      job.status = "BLOCKED";
      job.stage = "blocked";
      job.progress = 100;
      job.reason = "FUNCTIONAL_OBLIGATION_LIMIT_EXCEEDED";
      appendLog(
        job,
        "system",
        "Precheck rejected at 10,001 reported obligation rows; conversion and metering were not accepted.",
      );
      if (!await persistExecutionIfCurrent(runner, context, job, executionId)) return;
      return;
    }
    job.status = "RUNNING";
    job.stage = "metering";
    job.progress = 10;
    appendLog(
      job,
      "system",
      preflight.status === "PASSED"
        ? `Precheck passed for ${preflight.obligationCount} exact reported rows; conversion accepted and metering begins.`
        : `Precheck passed with an incomplete inventory at ${preflight.reportedObligationLowerBound} reported rows; conversion accepted, project rate remains indeterminate, and metering begins.`,
    );
    if (!await persistExecutionIfCurrent(runner, context, job, executionId)) return;
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    metering = await beginMeteredExecution(`translation-${job.id}`);
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    job.status = "RUNNING";
    job.stage = "pipeline";
    job.progress = 15;
    appendLog(job, "system", `Pipeline started with ${runner.executor}; source and cases are read-only.`);
    if (!await persistExecutionIfCurrent(runner, context, job, executionId)) return;
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    const invocation = command(runner, job, source, cases, pipeline);
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    const exitCode = await runChild(
      runner,
      context,
      invocation.executable,
      invocation.args,
      job,
      processKey,
      executionId,
      "pipeline",
    );
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    if (exitCode !== 0) fail(409, "TRANSLATION_PIPELINE_BLOCKED");
    const pipelineReport = await readBoundedPipelineFile(
      pipeline,
      "repository-pipeline-report.json",
      64 * 1024 * 1024,
      "TRANSLATION_PIPELINE_EVIDENCE_INVALID",
    );
    let report: Record<string, unknown>;
    try {
      report = JSON.parse(pipelineReport.content.toString("utf8")) as Record<string, unknown>;
    } catch {
      fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    }
    const status = String(report.status);
    const workUnitCount = Number(report.work_unit_count);
    const conversion = validateTranslationConversion(report.functional_conversion, workUnitCount);
    const artifact = report.artifact as Record<string, unknown> | null | undefined;
    if (
      report.schema_version !== "1.0.0"
      || report.kind !== "elmos.repository-pipeline-report"
      || !["COMPLETE", "PARTIAL", "BLOCKED"].includes(status)
      || report.repository_ref !== job.repositoryRef
      || report.source_language !== job.sourceLanguage
      || report.target_language !== job.targetLanguage
      || report.route_id !== `${job.sourceLanguage}-to-${job.targetLanguage}`
      || report.profile !== "typed-pure-function-v1"
      || !digestPattern.test(String(report.snapshot_sha256))
      || report.snapshot_sha256 !== preflight.snapshotSha256
      || !digestPattern.test(String(report.cases_manifest_sha256))
      || report.cases_manifest_sha256 !== conversion.summary.casesManifestSha256
      || report.independent_verification_status !== "NOT_RUN"
      || report.external_verification_status !== "NOT_RUN"
      || report.certification_status !== "NOT_CERTIFIED"
    ) {
      fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    }

    const batchStatusCounts = report.status_counts;
    const readyCount = Number(report.ready_count);
    const includedUnitCount = Number(report.included_unit_count);
    const buildRaw = report.build_verification;
    if (
      !batchStatusCounts || typeof batchStatusCounts !== "object" || Array.isArray(batchStatusCounts)
      || !Number.isSafeInteger(readyCount) || readyCount < 0 || readyCount > workUnitCount
      || !Number.isSafeInteger(includedUnitCount) || includedUnitCount < 0 || includedUnitCount > workUnitCount
      || !buildRaw || typeof buildRaw !== "object" || Array.isArray(buildRaw)
    ) fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    const batchCounts = batchStatusCounts as Record<string, unknown>;
    if (
      Object.keys(batchCounts).length < 1
      || Object.keys(batchCounts).length > 16
      || Object.entries(batchCounts).some(([key, value]) => (
        !/^[A-Z][A-Z0-9_]{1,99}$/.test(key)
        || !Number.isSafeInteger(value)
        || Number(value) < 0
      ))
      || Object.values(batchCounts).reduce<number>((total, value) => total + Number(value), 0) !== workUnitCount
    ) fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    const build = buildRaw as Record<string, unknown>;
    // Narrowed here, checked on the very next line.  The engine reports NOT_RUN
    // for a missing exact toolchain and FAILED for a reportable build failure;
    // anything outside that set is rejected before the job is constructed.
    const buildStatus = String(build.status) as NonNullable<
      TranslationJob["buildVerification"]
    >["status"];
    // Resolved once, before the guard chain: calling a type predicate inside
    // `||` would narrow `build` for every clause after it.
    const verifiedBuild = validBuildVerification(build) ? build : null;
    if (
      // The pipeline writes `commands: [{command, stdout, stderr}]` and
      // `toolchain: {language, version}`.  The other side of this merge read a
      // singular `command: string[]` and a string `toolchain`, a shape the
      // engine has never emitted -- so every real report was rejected here as
      // TRANSLATION_PIPELINE_EVIDENCE_INVALID.  `validBuildVerification` above
      // is the reader for the shape that is actually written.
      !["PASSED", "FAILED", "NOT_RUN"].includes(buildStatus)
      || !Array.isArray(build.commands)
      || build.commands.length > 100
      || !isRecord(build.toolchain)
      || (buildStatus === "PASSED" && verifiedBuild === null)
      || (buildStatus !== "PASSED" && build.commands.length > 0)
      || (build.reason !== null && (
        typeof build.reason !== "string" || build.reason.length > 4_000
      ))
    ) fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    const buildReason = typeof build.reason === "string" ? build.reason : null;
    const functionalStatus: "COMPLETE" | "PARTIAL" | "BLOCKED" =
      conversion.summary.numerator === 0
        ? "BLOCKED"
        : conversion.summary.denominatorComplete
          && conversion.summary.numerator === conversion.summary.denominator
          && buildStatus === "PASSED"
          ? "COMPLETE"
          : "PARTIAL";
    const packagingRaw = report.artifact_packaging;
    if (!packagingRaw || typeof packagingRaw !== "object" || Array.isArray(packagingRaw)) {
      fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    }
    const packaging = packagingRaw as Record<string, unknown>;
    const packagingStatus = String(packaging.status);
    const packagingReasonCode = packaging.reason_code;
    const packagingReason = packaging.reason;
    const packagingLimitsValid =
      packaging.max_uncompressed_bytes === MAX_TRANSLATION_ARTIFACT_BYTES
      && packaging.max_compressed_bytes === MAX_TRANSLATION_ARTIFACT_BYTES;
    const packagingPassed = packagingStatus === "PASSED"
      && packagingReasonCode === null
      && packagingReason === null
      && conversion.summary.codeArtifactReady
      && artifact !== null
      && artifact !== undefined
      && status === functionalStatus
      && functionalStatus !== "BLOCKED";
    const packagingNotRun = packagingStatus === "NOT_RUN"
      && packagingReasonCode === "FUNCTIONAL_CONVERSION_NOT_CODE_READY"
      && typeof packagingReason === "string"
      && packagingReason.length >= 1
      && packagingReason.length <= 2_000
      && !conversion.summary.codeArtifactReady
      && (artifact === null || artifact === undefined)
      && status === functionalStatus;
    const packagingCapacityFailed = packagingStatus === "FAILED"
      && [
        "PIPELINE_ARTIFACT_UNCOMPRESSED_LIMIT_EXCEEDED",
        "PIPELINE_ARTIFACT_COMPRESSED_LIMIT_EXCEEDED",
      ].includes(String(packagingReasonCode))
      && typeof packagingReason === "string"
      && packagingReason.length >= 1
      && packagingReason.length <= 2_000
      && !conversion.summary.codeArtifactReady
      && (artifact === null || artifact === undefined)
      && status === "BLOCKED"
      && functionalStatus !== "BLOCKED";
    if (
      !packagingLimitsValid
      || Object.keys(packaging).some((key) => ![
        "status",
        "reason_code",
        "reason",
        "max_uncompressed_bytes",
        "max_compressed_bytes",
      ].includes(key))
      || !(packagingPassed || packagingNotRun || packagingCapacityFailed)
    ) fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    // A build that did not verify carries no verification to attach; the field
    // is optional on TranslationJob precisely so NOT_RUN and FAILED can say so
    // by omission rather than by a half-populated record.
    const buildVerification: TranslationJob["buildVerification"] = verifiedBuild ?? undefined;

    const [verifiedJsonReport, verifiedMarkdownReport] = await Promise.all([
      readVerifiedPipelineFile(
        pipeline,
        conversion.jsonReport,
        "TRANSLATION_REPORT_INTEGRITY_MISMATCH",
      ),
      readVerifiedPipelineFile(
        pipeline,
        conversion.markdownReport,
        "TRANSLATION_REPORT_INTEGRITY_MISMATCH",
      ),
    ]);
    let conversionDocument: unknown;
    try {
      conversionDocument = JSON.parse(verifiedJsonReport.content.toString("utf8"));
    } catch {
      fail(409, "TRANSLATION_REPORT_DOCUMENT_INVALID");
    }
    const conversionContext = {
      pipelineStatus: functionalStatus,
      repositoryRef: job.repositoryRef,
      snapshotSha256: String(report.snapshot_sha256),
      routeId: `${job.sourceLanguage}-to-${job.targetLanguage}`,
      sourceLanguage: job.sourceLanguage,
      targetLanguage: job.targetLanguage,
      profile: String(report.profile),
      buildStatus,
      buildReason,
      markdownSha256: conversion.markdownReport.sha256,
      casesManifestSha256: conversion.summary.casesManifestSha256,
    };
    if (conversion.summary.storageMode === "SINGLE") {
      validateTranslationConversionDocument(
        conversionDocument,
        conversionContext,
        conversion.summary,
      );
      validateTranslationConversionMarkdown(
        conversionDocument,
        verifiedMarkdownReport.content,
      );
    } else {
      const shardDescriptors = validateTranslationConversionIndex(
        conversionDocument,
        conversionContext,
        conversion.summary,
      );
      validateTranslationConversionMarkdown(
        conversionDocument,
        verifiedMarkdownReport.content,
      );
      const shardOutputs = await Promise.all(shardDescriptors.map(async (descriptor) => {
        const [jsonFile, markdownFile] = await Promise.all([
          readVerifiedPipelineFile(
            pipeline,
            descriptor.json,
            "TRANSLATION_REPORT_INTEGRITY_MISMATCH",
          ),
          readVerifiedPipelineFile(
            pipeline,
            descriptor.markdown,
            "TRANSLATION_REPORT_INTEGRITY_MISMATCH",
          ),
        ]);
        try {
          return {
            document: JSON.parse(jsonFile.content.toString("utf8")) as unknown,
            markdown: markdownFile.content,
          };
        } catch {
          fail(409, "TRANSLATION_REPORT_DOCUMENT_INVALID");
        }
      }));
      shardOutputs.forEach((output, offset) => {
        const descriptor = shardDescriptors[offset];
        validateTranslationConversionMarkdown(
          output.document,
          output.markdown,
          `分片 ${descriptor.sequence}/${conversion.summary.shardCount}；本分片 ${descriptor.functionCount} 个功能；总指标来自全部分片`,
        );
      });
      validateTranslationConversionShardDocuments(
        conversionDocument,
        shardOutputs.map((output) => output.document),
        conversionContext,
        conversion.summary,
        shardDescriptors,
      );
      const expectedBundleFiles = translationConversionBundleFiles(
        conversion,
        shardDescriptors,
      );
      const manifestFile = await readBoundedPipelineFile(
        pipeline,
        BUNDLE_MANIFEST_PATH,
        1024 * 1024,
        "TRANSLATION_REPORT_INTEGRITY_MISMATCH",
      );
      const manifestDescriptor = validateTranslationConversionBundleManifest(
        manifestFile.content,
        conversion.summary.reportId,
        expectedBundleFiles,
      );
      if (
        manifestDescriptor.bytes !== manifestFile.size
        || manifestDescriptor.sha256 !== manifestFile.sha256
        || !conversion.reportBundle
      ) fail(409, "TRANSLATION_REPORT_INTEGRITY_MISMATCH");
      const bundleFile = await verifiedOpenPipelineFile(
        pipeline,
        conversion.reportBundle,
        "TRANSLATION_REPORT_INTEGRITY_MISMATCH",
      );
      if (bundleFile.size > MAX_FUNCTIONAL_REPORT_BUNDLE_BYTES) {
        await bundleFile.handle.close().catch(() => undefined);
        fail(409, "TRANSLATION_REPORT_INTEGRITY_MISMATCH");
      }
      try {
        await validateTranslationConversionBundleArchive(
          bundleFile.handle,
          conversion.reportBundle,
          expectedBundleFiles,
          manifestDescriptor,
        );
      } finally {
        await bundleFile.handle.close().catch(() => undefined);
      }
    }

    let verifiedArtifact: { path: string; size: number; sha256: string } | undefined;
    if (conversion.summary.codeArtifactReady) {
      if (
        !artifact
        || artifact.path !== "repository-migration-artifact.zip"
        || !Number.isSafeInteger(artifact.bytes)
        || Number(artifact.bytes) < 1
        || Number(artifact.bytes) > MAX_TRANSLATION_ARTIFACT_BYTES
        || !digestPattern.test(String(artifact.sha256))
      ) fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
      if (functionalStatus === "BLOCKED") {
        fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
      }
      const artifactDescriptor = {
        path: "repository-migration-artifact.zip" as const,
        bytes: Number(artifact.bytes),
        sha256: String(artifact.sha256),
      };
      const artifactFile = await verifiedOpenPipelineFile(
        pipeline,
        artifactDescriptor,
        "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH",
      );
      try {
        await validateTranslationCodeArtifactArchive(
          artifactFile.handle,
          artifactDescriptor,
          {
            pipelineStatus: functionalStatus,
            repositoryRef: job.repositoryRef,
            snapshotSha256: String(report.snapshot_sha256),
            routeId: `${job.sourceLanguage}-to-${job.targetLanguage}`,
            profile: String(report.profile),
            summary: conversion.summary,
          },
        );
        verifiedArtifact = {
          path: artifactFile.path,
          size: artifactFile.size,
          sha256: artifactFile.sha256,
        };
      } catch {
        fail(409, "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH");
      } finally {
        await artifactFile.handle.close().catch(() => undefined);
      }
    } else if (artifact !== null && artifact !== undefined) {
      fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    }

    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;

    job.reportJson = conversion.jsonReport;
    job.reportMarkdown = conversion.markdownReport;
    if (conversion.reportBundle) job.reportBundle = conversion.reportBundle;
    else delete job.reportBundle;
    job.conversionSummary = conversion.summary;
    job.reportReady = true;
    job.artifactReady = false;
    if (verifiedArtifact) {
      job.artifactSha256 = verifiedArtifact.sha256;
      job.artifactSize = verifiedArtifact.size;
    } else {
      delete job.artifactSha256;
      delete job.artifactSize;
    }
    job.snapshotSha256 = String(report.snapshot_sha256);
    job.readyCount = readyCount;
    job.workUnitCount = workUnitCount;
    job.includedUnitCount = includedUnitCount;
    job.statusCounts = Object.fromEntries(
      Object.entries(batchCounts).map(([key, value]) => [key, Number(value)]),
    );
    job.buildVerification = buildVerification;
    finalizedReportValidated = true;
    job.stage = "metering";
    job.progress = 99;
    job.artifactReady = false;
    await metering?.finish(status !== "BLOCKED");
    metering = null;
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    job.status = status as "COMPLETE" | "PARTIAL" | "BLOCKED";
    job.stage = status === "BLOCKED" ? "blocked" : "complete";
    job.progress = 100;
    job.artifactReady = conversion.summary.codeArtifactReady;
    if (status === "BLOCKED") {
      job.reason = packagingCapacityFailed
        ? String(packagingReasonCode)
        : typeof report.reason === "string"
        ? redact(report.reason)
        : conversion.summary.failureSummaries[0]?.failureCode
          ?? "TRANSLATION_PIPELINE_REPORTED_BLOCKED";
    } else {
      delete job.reason;
    }
    appendLog(
      job,
      "system",
      conversion.summary.denominatorComplete
        ? `Pipeline ${job.status}; project functional conversion ${conversion.summary.exactFraction} (${conversion.summary.displayPercent}); report digest ${conversion.markdownReport.sha256}.`
        : `Pipeline ${job.status}; reported CALLABLE diagnostic ${conversion.summary.exactFraction} (${conversion.summary.displayPercent}); project rate ${conversion.summary.projectSuccessRateDisplay}; report digest ${conversion.markdownReport.sha256}.`,
    );
    if (!await persistExecutionIfCurrent(runner, context, job, executionId)) return;
  } catch (error) {
    if (metering) {
      try {
        await metering.finish(false);
      } catch (meteringError) {
        error = meteringError;
      }
      metering = null;
    }
    if (
      !executionId
      || !await durableExecutionIsCurrent(runner, context, job.id, executionId)
    ) return;
    if (!finalizedReportValidated) clearUnvalidatedReport(job);
    job.status = "BLOCKED";
    job.stage = "blocked";
    job.progress = 100;
    job.artifactReady = false;
    job.reason = error instanceof GenerationRunnerError
      ? error.message
      : "TRANSLATION_PIPELINE_BLOCKED";
    appendLog(job, "system", `Pipeline blocked: ${job.reason}`);
    await persistExecutionIfCurrent(runner, context, job, executionId);
  } finally {
    if (metering) {
      try {
        await metering.finish(false);
      } catch (error) {
        if (
          executionId
          && await durableExecutionIsCurrent(runner, context, job.id, executionId)
        ) {
          if (!finalizedReportValidated) clearUnvalidatedReport(job);
          job.status = "BLOCKED";
          job.stage = "blocked";
          job.artifactReady = false;
          job.reason = error instanceof GenerationRunnerError
            ? error.message
            : "USAGE_SETTLEMENT_FAILED";
          await persistExecutionIfCurrent(runner, context, job, executionId);
        }
      }
    }
    if (state.generations.get(processKey) === generation) state.active.delete(processKey);
    if (leaseHeartbeat) clearInterval(leaseHeartbeat);
    if (queueLease) {
      let durableJob = job;
      try {
        durableJob = await load(runner, context, job.id);
      } catch {
        // Release still fails closed below if durable storage disappeared.
      }
      const outcome = durableJob.cancelRequestedAt || durableJob.status === "CANCELLED"
        ? "CANCELLED"
        : durableJob.status === "COMPLETE" || durableJob.status === "PARTIAL"
        ? "SUCCEEDED"
        : durableJob.status === "BLOCKED"
            ? "BLOCKED"
            : "FAILED";
      try {
        await queueLease.release(outcome);
      } catch {
        if (
          executionId
          && await durableExecutionIsCurrent(runner, context, job.id, executionId)
        ) {
          job.status = "BLOCKED";
          job.stage = "blocked";
          job.artifactReady = false;
          job.reason = "QUEUE_LEASE_RELEASE_FAILED";
          await persistExecutionIfCurrent(runner, context, job, executionId);
        }
      }
    }
    if (!requeued) {
      if (executionIsCurrent(processKey, generation)) {
        state.scheduled.delete(processKey);
        state.cancelled.delete(processKey);
        state.generations.delete(processKey);
      } else if (
        state.cancelled.has(processKey)
        && state.generations.get(processKey) !== generation
        && !state.active.has(processKey)
      ) {
        state.scheduled.delete(processKey);
        state.cancelled.delete(processKey);
        state.generations.delete(processKey);
      }
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
  const generation = (state.generations.get(processKey) ?? 0) + 1;
  state.generations.set(processKey, generation);
  state.scheduled.add(processKey);
  setImmediate(() => void execute(runner, context, job, generation));
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
  if (process.env.NODE_ENV === "production" && request.workspaceId) {
    fail(400, "TRANSLATION_DIRECT_WORKSPACE_FORBIDDEN");
  }
  if (process.env.NODE_ENV === "production" && !request.repositoryWorkspaceId) {
    fail(400, "TRANSLATION_REPOSITORY_WORKSPACE_REQUIRED");
  }
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
  await materializedDirectory(
    translationCasesBase(runner, context),
    casesBundleId,
    "TRANSLATION_CASES_BUNDLE",
  );
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
    reportReady: false,
    independentVerificationStatus: "NOT_RUN",
    externalVerificationStatus: "NOT_RUN",
    certificationStatus: "NOT_CERTIFIED",
    logs: [],
  };
  appendLog(
    job,
    "system",
    `Precheck queued for ${sourceLanguage}-to-${targetLanguage}; conversion and metering are not yet accepted.`,
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
  let job = await load(runner, context, jobId);
  const processKey = key(context, job.id);
  if (!["QUEUED", "PRECHECK", "RUNNING"].includes(job.status)) return job;
  const lease = await DurableJobLease.observe({
    configuration: durableQueueConfiguration(runner.root, "translation"),
    tenantId: context.tenantId,
    jobId: job.id,
    inputDigest: translationInputDigest(job),
  });
  if (lease.active) {
    if (!lease.inputDigestMatches) fail(409, "TRANSLATION_QUEUE_LEASE_IDENTITY_MISMATCH");
    return job;
  }

  let cleanedReceipt: TranslationExecutionRuntimeReceipt | undefined;
  try {
    cleanedReceipt = await cleanupRuntimeReceipt(runner, context, job);
  } catch {
    job = await withTranslationControl(runner, async () => {
      const current = await load(runner, context, jobId);
      if (current.runtimeReceipt) {
        current.runtimeReceipt.state = "CLEANUP_UNVERIFIED";
        current.runtimeReceipt.updatedAt = new Date().toISOString();
      }
      current.status = "BLOCKED";
      current.stage = "blocked";
      current.progress = 100;
      current.reason = "CANCEL_CLEANUP_UNVERIFIED";
      clearPriorExecutionOutputs(current);
      appendLog(current, "system", "Persistent execution recovery could not verify runtime cleanup.");
      await writeControlledJob(runner, context, current);
      return current;
    });
    return job;
  }

  let shouldSchedule = false;
  job = await withTranslationControl(runner, async () => {
    const current = await load(runner, context, jobId);
    if (!["QUEUED", "PRECHECK", "RUNNING"].includes(current.status)) return current;
    if (cleanedReceipt && current.executionId === cleanedReceipt.executionId) {
      current.runtimeReceipt = cleanedReceipt;
    }
    if (current.cancelRequestedAt) {
      current.status = "CANCELLED";
      current.stage = "cancelled";
      current.progress = 100;
      current.reason = "CANCELLED_BY_AUTHORIZED_ACTOR";
      clearPriorExecutionOutputs(current);
      appendLog(current, "system", "Durable cancellation reconciled after the prior worker lease ended.");
    } else {
      const recoveryAlreadyQueued = current.stage === "restart-recovery"
        && Date.now() - Date.parse(current.updatedAt) < 30_000;
      if (!recoveryAlreadyQueued) current.recoveryAttempts += 1;
      current.stage = "restart-recovery";
      if (current.recoveryAttempts > 2) {
        current.status = "BLOCKED";
        current.stage = "blocked";
        current.reason = "TRANSLATION_RESTART_RECOVERY_LIMIT_EXCEEDED";
      } else {
        current.status = "QUEUED";
        if (!recoveryAlreadyQueued) {
          appendLog(current, "system", "Expired worker lease reconciled; pipeline will resume.");
        }
        shouldSchedule = true;
      }
    }
    await writeControlledJob(runner, context, current);
    return current;
  });
  if (shouldSchedule && !state.active.has(processKey) && !state.scheduled.has(processKey)) {
    schedule(runner, context, job);
  }
  return job;
}

export async function cancelTranslationJob(
  context: AuthorizedContext,
  jobId: string,
): Promise<TranslationJob> {
  const runner = runnerConfig();
  const requestedAt = new Date().toISOString();
  let job = await withTranslationControl(runner, async () => {
    const current = await load(runner, context, jobId);
    const retryingCleanup = current.status === "BLOCKED"
      && current.reason === "CANCEL_CLEANUP_UNVERIFIED"
      && Boolean(current.cancelRequestedAt);
    if (!["QUEUED", "PRECHECK", "RUNNING"].includes(current.status) && !retryingCleanup) {
      fail(409, "TRANSLATION_JOB_NOT_CANCELLABLE");
    }
    clearPriorExecutionOutputs(current);
    current.cancelRequestedAt ??= requestedAt;
    current.cancelRequestedBy ??= context.actor;
    current.reason = "CANCEL_REQUESTED";
    appendLog(current, "system", `Durable cancellation requested by ${context.actor}.`);
    await writeControlledJob(runner, context, current);
    return current;
  });
  const processKey = key(context, job.id);
  state.generations.set(processKey, (state.generations.get(processKey) ?? 0) + 1);
  state.cancelled.add(processKey);
  state.scheduled.delete(processKey);
  let cleanedReceipt: TranslationExecutionRuntimeReceipt | undefined;
  try {
    cleanedReceipt = await cleanupRuntimeReceipt(runner, context, job);
  } catch {
    job = await withTranslationControl(runner, async () => {
      const current = await load(runner, context, jobId);
      if (current.runtimeReceipt) {
        current.runtimeReceipt.state = "CLEANUP_UNVERIFIED";
        current.runtimeReceipt.updatedAt = new Date().toISOString();
      }
      current.status = "BLOCKED";
      current.stage = "blocked";
      current.progress = 100;
      current.reason = "CANCEL_CLEANUP_UNVERIFIED";
      clearPriorExecutionOutputs(current);
      appendLog(current, "system", "Cancellation blocked because runtime cleanup could not be verified.");
      await writeControlledJob(runner, context, current);
      return current;
    });
    return job;
  }
  job = await withTranslationControl(runner, async () => {
    const current = await load(runner, context, jobId);
    if (cleanedReceipt && current.executionId === cleanedReceipt.executionId) {
      current.runtimeReceipt = cleanedReceipt;
    }
    current.status = "CANCELLED";
    current.stage = "cancelled";
    current.progress = 100;
    current.reason = "CANCELLED_BY_AUTHORIZED_ACTOR";
    clearPriorExecutionOutputs(current);
    appendLog(current, "system", `Job cancellation and runtime cleanup verified for ${context.actor}.`);
    await writeControlledJob(runner, context, current);
    return current;
  });
  if (!state.active.has(processKey)) {
    state.cancelled.delete(processKey);
    state.generations.delete(processKey);
  }
  return job;
}

export async function translationArtifact(
  context: AuthorizedContext,
  jobId: string,
): Promise<{ handle: FileHandle; path: string; size: number; sha256: string }> {
  const runner = runnerConfig();
  const job = await load(runner, context, jobId);
  if (!job.artifactReady || !job.artifactSha256 || !job.artifactSize) {
    fail(409, "TRANSLATION_ARTIFACT_NOT_READY");
  }
  if (
    !digestPattern.test(job.artifactSha256)
    || !Number.isSafeInteger(job.artifactSize)
    || job.artifactSize < 1
    || job.artifactSize > MAX_TRANSLATION_ARTIFACT_BYTES
  ) {
    fail(409, "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH");
  }
  if (
    (job.status !== "COMPLETE" && job.status !== "PARTIAL")
    || !job.snapshotSha256
    || !job.conversionSummary
    || !job.conversionSummary.codeArtifactReady
  ) fail(409, "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH");
  const descriptor = {
    path: "repository-migration-artifact.zip" as const,
    bytes: job.artifactSize,
    sha256: job.artifactSha256,
  };
  const artifact = await verifiedOpenPipelineFile(
    confined(jobRoot(runner, context, jobId), "pipeline"),
    descriptor,
    "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH",
  );
  try {
    await validateTranslationCodeArtifactArchive(
      artifact.handle,
      descriptor,
      {
        pipelineStatus: job.status,
        repositoryRef: job.repositoryRef,
        snapshotSha256: job.snapshotSha256,
        routeId: `${job.sourceLanguage}-to-${job.targetLanguage}`,
        profile: "typed-pure-function-v1",
        summary: job.conversionSummary,
      },
    );
    return artifact;
  } catch {
    await artifact.handle.close().catch(() => undefined);
    fail(409, "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH");
  }
}

export async function translationReport(
  context: AuthorizedContext,
  jobId: string,
  format: "json" | "markdown" | "bundle",
): Promise<{ handle: FileHandle; path: string; size: number; sha256: string }> {
  const runner = runnerConfig();
  const job = await load(runner, context, jobId);
  const descriptor = format === "json"
    ? job.reportJson
    : format === "bundle" ? job.reportBundle : job.reportMarkdown;
  if (!job.reportReady || !descriptor) fail(409, "TRANSLATION_REPORT_NOT_READY");
  const expectedPath = format === "json"
    ? "functional-conversion-report.json"
    : format === "bundle"
      ? "FUNCTION_CONVERSION_REPORT_BUNDLE.zip"
      : "FUNCTION_CONVERSION_REPORT.md";
  const maximumBytes = format === "bundle"
    ? MAX_FUNCTIONAL_REPORT_BUNDLE_BYTES
    : 64 * 1024 * 1024;
  if (
    descriptor.path !== expectedPath
    || !Number.isSafeInteger(descriptor.bytes)
    || descriptor.bytes < 1
    || descriptor.bytes > maximumBytes
    || !digestPattern.test(descriptor.sha256)
  ) fail(409, "TRANSLATION_REPORT_INTEGRITY_MISMATCH");
  return verifiedOpenPipelineFile(
    confined(jobRoot(runner, context, jobId), "pipeline"),
    descriptor,
    "TRANSLATION_REPORT_INTEGRITY_MISMATCH",
  );
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
      reason: error instanceof GenerationRunnerError
        ? error.message
        : "TRANSLATION_RUNNER_BLOCKED",
    };
  }
}

import { createHash } from "node:crypto";
import {
  closeSync,
  constants as fsConstants,
  existsSync,
  fstatSync,
  lstatSync,
  openSync,
  readFileSync,
  realpathSync,
  statSync,
  type BigIntStats,
} from "node:fs";
import path from "node:path";
import {
  translationCertificationSkill,
  translationHazards,
  translationLanguages,
} from "../businessLines";
import type {
  DirectedLanguageRoute,
  TranslationCapabilityResponse,
  TranslationLanguageId,
} from "../contracts";
import { parseStrictJson, StrictJsonError } from "./strictJson";

/**
 * The cross-language business line advertises directed route readiness. That
 * readiness is owned by `routes/inventory.json` and the per-route packs beside
 * it, never by a constant compiled into the web console. This reader resolves
 * the repository contract at request time and fails closed on any drift so the
 * console can never assert a local pass it has not read.
 */

const ROUTE_INVENTORY_RELATIVE_PATH = "routes/inventory.json";
const ROUTE_INVENTORY_SCHEMA_VERSION = "1.4.0";
const TARGET_EMITTER_RELATIVE_PATH =
  "engines/polyglot-route-engine/src/elmos_polyglot_route/emitter.py";
const ACTIVE_TRANSLATION_LANGUAGE_IDS = [
  "java",
  "csharp",
  "go",
  "rust",
  "python",
  "typescript",
  "cpp",
  "objc",
  "swift",
  "php",
  "kotlin",
  "react",
  "flutter",
] as const satisfies readonly TranslationLanguageId[];
const RESEARCH_ONLY_LANGUAGE_IDS = new Set<TranslationLanguageId>([
  "kotlin",
  "react",
  "flutter",
]);
const ACTIVE_ROUTE_COUNT = ACTIVE_TRANSLATION_LANGUAGE_IDS.length
  * (ACTIVE_TRANSLATION_LANGUAGE_IDS.length - 1);
const LOCAL_EXECUTION_STATUSES = ["PASSED_LOCAL", "NOT_RUN", "FAILED"] as const;
const MODULE_EXECUTION_STATUSES = [...LOCAL_EXECUTION_STATUSES, "NOT_APPLICABLE"] as const;
const VERIFICATION_STATUSES = ["PASSED", "NOT_RUN", "FAILED"] as const;
const ROUTE_STATUSES = ["research", "experimental", "limited", "certified", "blocked"] as const;
const MAX_ROOT_WALK_DEPTH = 8;
const REPOSITORY_PROFILE_PATTERN = /^[a-z0-9][a-z0-9._-]{2,120}$/;
const REPOSITORY_EVIDENCE_REF_PATTERN = /^certification\/[a-z0-9][a-z0-9._/-]{1,260}\.json$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const MAX_REPOSITORY_EVIDENCE_BYTES = 8 * 1024 * 1024;
const MAX_ROUTE_PACK_BYTES = 128 * 1024;
const MAX_ROUTE_CERTIFICATION_BYTES = 2 * 1024 * 1024;
const V3_RESEARCH_ROUTE_VERSION = "0.1.0";
const V3_RESEARCH_DECLARED_SCOPE = "NO_ROUTE_PROFILE_ADMITTED";
const V3_RESEARCH_ISSUED_AT = "2026-08-09T00:00:00+00:00";
const V3_RESEARCH_NEXT_REVIEW_AT = "2026-11-24T00:00:00+00:00";
const V3_RESEARCH_GATE_KEYS = [
  "local_execution",
  "external_execution",
  "independent_verification",
] as const;
const V3_RESEARCH_METRIC_KEYS = [
  "build_green_rate",
  "first_build_pass_rate",
  "p0_behavior_pass_rate",
  "source_map_coverage",
  "manual_hours",
  "cost_per_verified_workload",
] as const;
const V3_RESEARCH_CERTIFICATION_KEYS = [
  "schema_version",
  "route_key",
  "route_version",
  "status",
  "certification_decision",
  "declared_scope",
  "gate_results",
  "metrics",
  "evidence_refs",
  "issued_at",
  "next_review_at",
] as const;
const V3_RESEARCH_EVIDENCE_KEYS = [
  "schema_version",
  "route_key",
  "route_version",
  "route_maturity",
  "execution_status",
  "module_execution_status",
  "repository_execution_status",
  "independent_verification_status",
  "external_certification_status",
  "runs",
  "negative_runs",
  "metrics",
  "critical_unknown_semantics",
  "critical_behavior_regressions",
  "test_integrity_violations",
  "notes",
] as const;
const V3_RESEARCH_EVIDENCE_NOTES = [
  "No V3 route-level semantic profile or target profile has been admitted.",
  "Analyzer and emitter bindings are metadata, not route execution evidence.",
  "Local, repository, independent, external, customer, and production evidence remain NOT_RUN.",
] as const;
const V3_RESEARCH_SUPPORT_CAPABILITIES = [
  ["type-system", "experimental", "deterministic-lowering", "Initial scaffold; evidence required"],
  ["generics", "detected-only", "obligation", "Not yet implemented"],
  ["nullability", "detected-only", "obligation", "Not yet implemented"],
  ["numeric", "detected-only", "obligation", "Not yet implemented"],
  ["time", "detected-only", "obligation", "Not yet implemented"],
  ["exceptions", "detected-only", "obligation", "Not yet implemented"],
  ["async", "detected-only", "obligation", "Not yet implemented"],
  ["concurrency", "blocked", "human-review", "Requires route-specific certification"],
  ["reflection", "blocked", "human-review", "Requires route-specific certification"],
  ["serialization", "detected-only", "contract-mapping", "Not yet implemented"],
  ["interop", "blocked", "retain-runtime-or-sidecar", "Requires explicit boundary plan"],
] as const;
const V3_RESEARCH_SUPPORT_KEYS = ["schema_version", "route_key", "capabilities"] as const;
const V3_RESEARCH_CAPABILITY_KEYS = [
  "id",
  "status",
  "strategy",
  "reason",
  "evidence_refs",
] as const;
const V3_ROUTE_SET = "kotlin-react-flutter-completion-66";
const V3_LOCAL_EXECUTION_REASON = "V3_ROUTE_CAMPAIGN_NOT_RUN";

type LocalExecutionStatus = (typeof LOCAL_EXECUTION_STATUSES)[number];
type ModuleExecutionStatus = (typeof MODULE_EXECUTION_STATUSES)[number];
type VerificationStatus = (typeof VERIFICATION_STATUSES)[number];
type RouteStatus = (typeof ROUTE_STATUSES)[number];

type InventoryRoute = {
  route_key: string;
  source: string;
  target: string;
  source_version: string;
  target_version: string;
  status: RouteStatus;
  route_set: string;
  local_execution_reason: string;
  local_execution_status: LocalExecutionStatus;
  module_execution_status: ModuleExecutionStatus;
  repository_execution_status: VerificationStatus;
  repository_profile: string | null;
  repository_evidence_ref: string | null;
  repository_evidence_sha256: string | null;
  repository_evidence_bytes: number | null;
  independent_verification_status: VerificationStatus;
  external_certification_status: VerificationStatus;
};

type InventoryLanguage = {
  version: string;
  exact_versions: string[];
  engine_path: string;
};

type RoutePackEndpoint = {
  language: string;
  versions: string[];
  engine_path: string;
};

type RouteInventory = {
  schema_version: string;
  semantic_profile: string;
  route_count: number;
  research_route_count: number;
  limited_route_count: number;
  blocked_route_count: number;
  certified_route_count: number;
  experimental_route_count: number;
  local_execution_evidence: LocalExecutionStatus;
  independent_verification_evidence: VerificationStatus;
  external_certification_evidence: VerificationStatus;
  deprecated_languages: string[];
  pending_analyzer_languages: string[];
  pending_repository_languages: string[];
  console_exposed_languages: string[];
  languages: Record<string, InventoryLanguage>;
  routes: InventoryRoute[];
};

export class TranslationContractError extends Error {
  readonly errorCode: string;

  constructor(errorCode: string, message: string) {
    super(message);
    this.name = "TranslationContractError";
    this.errorCode = errorCode;
  }
}

function fail(errorCode: string, message: string): never {
  throw new TranslationContractError(errorCode, message);
}

type StableReadOptions = {
  unsafeCode: string;
  changedCode: string;
  label: string;
  minBytes?: number;
  maxBytes: number;
};

function sameStableIdentity(
  left: BigIntStats,
  right: BigIntStats,
): boolean {
  return left.dev === right.dev
    && left.ino === right.ino
    && left.mode === right.mode
    && left.size === right.size
    && left.nlink === right.nlink
    && left.mtimeNs === right.mtimeNs
    && left.ctimeNs === right.ctimeNs;
}

function assertSafeConfinedDirectory(
  root: string,
  directory: string,
  errorCode: string,
  label: string,
): void {
  try {
    const resolvedRoot = realpathSync(root);
    const relative = path.relative(root, directory);
    if (relative === "" || path.isAbsolute(relative) || relative.startsWith(`..${path.sep}`)) {
      fail(errorCode, `${label} 未约束在预期根目录内。`);
    }
    let current = root;
    const rootDetails = lstatSync(root);
    if (rootDetails.isSymbolicLink() || !rootDetails.isDirectory()) {
      fail(errorCode, `${label} 的约束根目录不安全。`);
    }
    for (const segment of relative.split(path.sep)) {
      current = path.join(/* turbopackIgnore: true */ current, segment);
      const details = lstatSync(current);
      if (details.isSymbolicLink() || !details.isDirectory()) {
        fail(errorCode, `${label} 含符号链接或非目录节点。`);
      }
    }
    const resolved = realpathSync(directory);
    if (!resolved.startsWith(`${resolvedRoot}${path.sep}`)) {
      fail(errorCode, `${label} 解析到约束根目录之外。`);
    }
  } catch (error) {
    if (error instanceof TranslationContractError) throw error;
    fail(errorCode, `${label} 无法安全解析。`);
  }
}

function readStableRegularFile(
  root: string,
  candidate: string,
  options: StableReadOptions,
): Buffer {
  let descriptor = -1;
  try {
    const resolvedRoot = realpathSync(root);
    const relative = path.relative(root, candidate);
    if (
      relative === ""
      || path.isAbsolute(relative)
      || relative === ".."
      || relative.startsWith(`..${path.sep}`)
    ) {
      fail(options.unsafeCode, `${options.label} 未约束在预期根目录内。`);
    }
    let current = root;
    const rootDetails = lstatSync(root, { bigint: true });
    if (rootDetails.isSymbolicLink() || !rootDetails.isDirectory()) {
      fail(options.unsafeCode, `${options.label} 的约束根目录不安全。`);
    }
    const segments = relative.split(path.sep);
    for (const segment of segments.slice(0, -1)) {
      current = path.join(/* turbopackIgnore: true */ current, segment);
      const details = lstatSync(current, { bigint: true });
      if (details.isSymbolicLink() || !details.isDirectory()) {
        fail(options.unsafeCode, `${options.label} 的父目录含符号链接。`);
      }
    }
    const before = lstatSync(candidate, { bigint: true });
    const resolvedCandidate = realpathSync(candidate);
    const minBytes = BigInt(options.minBytes ?? 1);
    if (
      before.isSymbolicLink()
      || !before.isFile()
      || before.nlink !== 1n
      || before.size < minBytes
      || before.size > BigInt(options.maxBytes)
      || !resolvedCandidate.startsWith(`${resolvedRoot}${path.sep}`)
    ) {
      fail(options.unsafeCode, `${options.label} 不是约束目录内的独立普通文件。`);
    }
    descriptor = openSync(
      candidate,
      fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW,
    );
    const opened = fstatSync(descriptor, { bigint: true });
    if (
      !opened.isFile()
      || opened.nlink !== 1n
      || !sameStableIdentity(before, opened)
    ) {
      fail(options.changedCode, `${options.label} 在打开前被替换。`);
    }
    const raw = readFileSync(descriptor);
    const afterDescriptor = fstatSync(descriptor, { bigint: true });
    const afterPath = lstatSync(candidate, { bigint: true });
    if (
      !sameStableIdentity(opened, afterDescriptor)
      || !sameStableIdentity(afterDescriptor, afterPath)
      || afterPath.nlink !== 1n
      || raw.byteLength !== Number(afterPath.size)
    ) {
      fail(options.changedCode, `${options.label} 在读取期间发生变化。`);
    }
    return raw;
  } catch (error) {
    if (error instanceof TranslationContractError) throw error;
    return fail(options.unsafeCode, `${options.label} 无法安全读取。`);
  } finally {
    if (descriptor >= 0) closeSync(descriptor);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(value: unknown, errorCode: string, label: string): string {
  if (typeof value !== "string" || value.length === 0 || value.length > 300) {
    fail(errorCode, `${label} 不是长度合法的字符串。`);
  }
  return value;
}

function requireCount(value: unknown, errorCode: string, label: string): number {
  if (!Number.isInteger(value) || (value as number) < 0 || (value as number) > 10_000) {
    fail(errorCode, `${label} 不是合法的非负整数。`);
  }
  return value as number;
}

function requireStringArray(
  value: unknown,
  errorCode: string,
  label: string,
): string[] {
  if (
    !Array.isArray(value)
    || !value.every(
      (entry) => typeof entry === "string" && entry.length > 0 && entry.length <= 40,
    )
    || new Set(value).size !== value.length
  ) {
    fail(errorCode, `${label} 必须是不含重复项的语言标识数组。`);
  }
  return [...value] as string[];
}

function requireVersionArray(value: unknown, label: string): string[] {
  if (
    !Array.isArray(value)
    || value.length === 0
    || !value.every(
      (entry) => typeof entry === "string" && entry.length > 0 && entry.length <= 300,
    )
    || new Set(value).size !== value.length
  ) {
    fail(
      "TRANSLATION_ROUTE_PACK_VERSION_METADATA_INVALID",
      `${label} 必须是不含重复项的非空精确版本数组。`,
    );
  }
  return [...value] as string[];
}

function requireEnum<T extends string>(
  value: unknown,
  allowed: readonly T[],
  errorCode: string,
  label: string,
): T {
  if (typeof value !== "string" || !(allowed as readonly string[]).includes(value)) {
    fail(errorCode, `${label} 必须是 ${allowed.join(" / ")} 之一。`);
  }
  return value as T;
}

function repositoryProfile(value: unknown, index: number): string | null {
  if (value === undefined || value === null) return null;
  const profile = requireString(
    value,
    "TRANSLATION_ROUTE_REPOSITORY_PROFILE_INVALID",
    `routes[${index}].repository_profile`,
  );
  if (!REPOSITORY_PROFILE_PATTERN.test(profile)) {
    fail(
      "TRANSLATION_ROUTE_REPOSITORY_PROFILE_INVALID",
      `routes[${index}].repository_profile 不是合法的版本化 Profile 标识。`,
    );
  }
  return profile;
}

function repositoryEvidenceRef(value: unknown, index: number): string | null {
  if (value === undefined || value === null) return null;
  const reference = requireString(
    value,
    "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_REF_INVALID",
    `routes[${index}].repository_evidence_ref`,
  );
  if (
    !REPOSITORY_EVIDENCE_REF_PATTERN.test(reference)
    || reference.includes("..")
    || reference.includes("\\")
    || path.posix.normalize(reference) !== reference
  ) {
    fail(
      "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_REF_INVALID",
      `routes[${index}].repository_evidence_ref 必须是 certification 下的受限 JSON 相对路径。`,
    );
  }
  return reference;
}

function repositoryEvidenceSha256(value: unknown, index: number): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) {
    fail(
      "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_DIGEST_INVALID",
      `routes[${index}].repository_evidence_sha256 必须是 64 位小写十六进制摘要。`,
    );
  }
  return value;
}

function repositoryEvidenceBytes(value: unknown, index: number): number | null {
  if (value === undefined || value === null) return null;
  if (
    !Number.isInteger(value)
    || (value as number) < 1
    || (value as number) > MAX_REPOSITORY_EVIDENCE_BYTES
  ) {
    fail(
      "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_BYTES_INVALID",
      `routes[${index}].repository_evidence_bytes 必须是 1–${MAX_REPOSITORY_EVIDENCE_BYTES}。`,
    );
  }
  return value as number;
}

/**
 * Locate the repository root without trusting a relative guess. An explicit
 * `ELMOS_REPOSITORY_ROOT` wins when it is absolute and actually carries the
 * contract; otherwise walk up from the process directory looking for the same
 * two markers. A miss is a blocked capability, never a silent default.
 */
export function resolveRepositoryRoot(): string {
  const carriesContract = (candidate: string) =>
    existsSync(path.join(/* turbopackIgnore: true */ candidate, ROUTE_INVENTORY_RELATIVE_PATH))
    && existsSync(path.join(/* turbopackIgnore: true */ candidate, "pom.xml"));

  const configured = process.env.ELMOS_REPOSITORY_ROOT;
  if (configured && path.isAbsolute(configured)) {
    const resolved = path.resolve(/* turbopackIgnore: true */ configured);
    if (carriesContract(resolved)) return resolved;
    fail(
      "TRANSLATION_REPOSITORY_ROOT_INVALID",
      "ELMOS_REPOSITORY_ROOT 指向的目录不包含 routes/inventory.json 与 pom.xml。",
    );
  }

  let candidate = path.resolve(/* turbopackIgnore: true */ process.cwd());
  for (let depth = 0; depth <= MAX_ROOT_WALK_DEPTH; depth += 1) {
    if (carriesContract(candidate)) return candidate;
    const parent = path.dirname(candidate);
    if (parent === candidate) break;
    candidate = parent;
  }
  fail(
    "TRANSLATION_REPOSITORY_ROOT_NOT_FOUND",
    "未能从当前工作目录向上定位到包含 routes/inventory.json 的仓库根目录。",
  );
}

function parseInventoryRoute(value: unknown, index: number): InventoryRoute {
  if (!isRecord(value)) {
    fail("TRANSLATION_ROUTE_ENTRY_INVALID", `routes[${index}] 不是对象。`);
  }
  const repositoryExecutionStatus = value.repository_execution_status === undefined
    ? "NOT_RUN"
    : requireEnum(
      value.repository_execution_status,
      VERIFICATION_STATUSES,
      "TRANSLATION_ROUTE_REPOSITORY_STATUS_INVALID",
      `routes[${index}].repository_execution_status`,
    );
  const parsedRepositoryProfile = repositoryProfile(value.repository_profile, index);
  const parsedRepositoryEvidenceRef = repositoryEvidenceRef(value.repository_evidence_ref, index);
  const parsedRepositoryEvidenceSha256 = repositoryEvidenceSha256(
    value.repository_evidence_sha256,
    index,
  );
  const parsedRepositoryEvidenceBytes = repositoryEvidenceBytes(
    value.repository_evidence_bytes,
    index,
  );
  const repositoryEvidenceDescriptor = [
    parsedRepositoryProfile,
    parsedRepositoryEvidenceRef,
    parsedRepositoryEvidenceSha256,
    parsedRepositoryEvidenceBytes,
  ];
  if (
    repositoryExecutionStatus === "PASSED"
    && repositoryEvidenceDescriptor.some((part) => part === null)
  ) {
    fail(
      "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_INCOMPLETE",
      `routes[${index}] 声明仓库级 PASSED，但 Profile、证据路径、摘要或字节数不完整。`,
    );
  }
  if (
    repositoryExecutionStatus !== "PASSED"
    && repositoryEvidenceDescriptor.some((part) => part !== null)
  ) {
    fail(
      "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_STALE",
      `routes[${index}] 仓库级状态不是 PASSED，却携带了可放行的证据描述符。`,
    );
  }
  return {
    route_key: requireString(value.route_key, "TRANSLATION_ROUTE_KEY_INVALID", `routes[${index}].route_key`),
    source: requireString(value.source, "TRANSLATION_ROUTE_SOURCE_INVALID", `routes[${index}].source`),
    target: requireString(value.target, "TRANSLATION_ROUTE_TARGET_INVALID", `routes[${index}].target`),
    source_version: requireString(
      value.source_version,
      "TRANSLATION_ROUTE_SOURCE_VERSION_INVALID",
      `routes[${index}].source_version`,
    ),
    target_version: requireString(
      value.target_version,
      "TRANSLATION_ROUTE_TARGET_VERSION_INVALID",
      `routes[${index}].target_version`,
    ),
    status: requireEnum(value.status, ROUTE_STATUSES, "TRANSLATION_ROUTE_STATUS_INVALID", `routes[${index}].status`),
    route_set: requireString(
      value.route_set,
      "TRANSLATION_ROUTE_SET_INVALID",
      `routes[${index}].route_set`,
    ),
    local_execution_reason: requireString(
      value.local_execution_reason,
      "TRANSLATION_ROUTE_LOCAL_REASON_INVALID",
      `routes[${index}].local_execution_reason`,
    ),
    local_execution_status: requireEnum(
      value.local_execution_status,
      LOCAL_EXECUTION_STATUSES,
      "TRANSLATION_ROUTE_LOCAL_STATUS_INVALID",
      `routes[${index}].local_execution_status`,
    ),
    module_execution_status: requireEnum(
      value.module_execution_status,
      MODULE_EXECUTION_STATUSES,
      "TRANSLATION_ROUTE_MODULE_STATUS_INVALID",
      `routes[${index}].module_execution_status`,
    ),
    repository_execution_status: repositoryExecutionStatus,
    repository_profile: parsedRepositoryProfile,
    repository_evidence_ref: parsedRepositoryEvidenceRef,
    repository_evidence_sha256: parsedRepositoryEvidenceSha256,
    repository_evidence_bytes: parsedRepositoryEvidenceBytes,
    independent_verification_status: requireEnum(
      value.independent_verification_status,
      VERIFICATION_STATUSES,
      "TRANSLATION_ROUTE_INDEPENDENT_STATUS_INVALID",
      `routes[${index}].independent_verification_status`,
    ),
    external_certification_status: requireEnum(
      value.external_certification_status,
      VERIFICATION_STATUSES,
      "TRANSLATION_ROUTE_EXTERNAL_STATUS_INVALID",
      `routes[${index}].external_certification_status`,
    ),
  };
}

function parseInventory(raw: string): RouteInventory {
  let value: unknown;
  try {
    value = parseStrictJson(raw);
  } catch (error) {
    if (error instanceof StrictJsonError && error.code === "DUPLICATE_JSON_FIELD") {
      fail(
        "TRANSLATION_ROUTE_INVENTORY_DUPLICATE_FIELD",
        "routes/inventory.json 含重复 JSON 字段。",
      );
    }
    fail("TRANSLATION_ROUTE_INVENTORY_UNPARSEABLE", "routes/inventory.json 不是合法 JSON。");
  }
  if (!isRecord(value)) {
    fail("TRANSLATION_ROUTE_INVENTORY_INVALID", "routes/inventory.json 顶层不是对象。");
  }
  if (!Array.isArray(value.routes)) {
    fail("TRANSLATION_ROUTE_LIST_INVALID", "routes/inventory.json 缺少 routes 数组。");
  }
  if (!isRecord(value.languages)) {
    fail("TRANSLATION_LANGUAGE_MAP_INVALID", "routes/inventory.json 缺少 languages 映射。");
  }
  if (!Array.isArray(value.console_exposed_languages) || value.console_exposed_languages.length === 0) {
    fail(
      "TRANSLATION_CONSOLE_LANGUAGE_LIST_INVALID",
      "routes/inventory.json 缺少非空 console_exposed_languages。",
    );
  }
  if (value.schema_version !== ROUTE_INVENTORY_SCHEMA_VERSION) {
    fail(
      "TRANSLATION_SCHEMA_VERSION_UNSUPPORTED",
      `routes/inventory.json 必须使用 ${ROUTE_INVENTORY_SCHEMA_VERSION}。`,
    );
  }

  const languages: Record<string, InventoryLanguage> = {};
  for (const [id, entry] of Object.entries(value.languages)) {
    if (!isRecord(entry)) {
      fail("TRANSLATION_LANGUAGE_ENTRY_INVALID", `languages.${id} 不是对象。`);
    }
    languages[id] = {
      version: requireString(entry.version, "TRANSLATION_LANGUAGE_VERSION_INVALID", `languages.${id}.version`),
      exact_versions: requireVersionArray(
        entry.exact_versions,
        `languages.${id}.exact_versions`,
      ),
      engine_path: requireString(
        entry.engine_path,
        "TRANSLATION_LANGUAGE_ENGINE_PATH_INVALID",
        `languages.${id}.engine_path`,
      ),
    };
  }

  return {
    schema_version: requireString(value.schema_version, "TRANSLATION_SCHEMA_VERSION_INVALID", "schema_version"),
    semantic_profile: requireString(
      value.semantic_profile,
      "TRANSLATION_SEMANTIC_PROFILE_INVALID",
      "semantic_profile",
    ),
    route_count: requireCount(value.route_count, "TRANSLATION_ROUTE_COUNT_INVALID", "route_count"),
    research_route_count: requireCount(
      value.research_route_count,
      "TRANSLATION_RESEARCH_COUNT_INVALID",
      "research_route_count",
    ),
    limited_route_count: requireCount(
      value.limited_route_count,
      "TRANSLATION_LIMITED_COUNT_INVALID",
      "limited_route_count",
    ),
    blocked_route_count: requireCount(
      value.blocked_route_count,
      "TRANSLATION_BLOCKED_COUNT_INVALID",
      "blocked_route_count",
    ),
    certified_route_count: requireCount(
      value.certified_route_count,
      "TRANSLATION_CERTIFIED_COUNT_INVALID",
      "certified_route_count",
    ),
    experimental_route_count: requireCount(
      value.experimental_route_count,
      "TRANSLATION_EXPERIMENTAL_COUNT_INVALID",
      "experimental_route_count",
    ),
    local_execution_evidence: requireEnum(
      value.local_execution_evidence,
      LOCAL_EXECUTION_STATUSES,
      "TRANSLATION_LOCAL_EVIDENCE_INVALID",
      "local_execution_evidence",
    ),
    independent_verification_evidence: requireEnum(
      value.independent_verification_evidence,
      VERIFICATION_STATUSES,
      "TRANSLATION_INDEPENDENT_EVIDENCE_INVALID",
      "independent_verification_evidence",
    ),
    external_certification_evidence: requireEnum(
      value.external_certification_evidence,
      VERIFICATION_STATUSES,
      "TRANSLATION_EXTERNAL_EVIDENCE_INVALID",
      "external_certification_evidence",
    ),
    deprecated_languages: requireStringArray(
      value.deprecated_languages,
      "TRANSLATION_DEPRECATED_LANGUAGE_LIST_INVALID",
      "deprecated_languages",
    ),
    pending_analyzer_languages: requireStringArray(
      value.pending_analyzer_languages,
      "TRANSLATION_PENDING_ANALYZER_LANGUAGE_LIST_INVALID",
      "pending_analyzer_languages",
    ),
    pending_repository_languages: requireStringArray(
      value.pending_repository_languages,
      "TRANSLATION_PENDING_REPOSITORY_LANGUAGE_LIST_INVALID",
      "pending_repository_languages",
    ),
    console_exposed_languages: requireStringArray(
      value.console_exposed_languages,
      "TRANSLATION_CONSOLE_LANGUAGE_LIST_INVALID",
      "console_exposed_languages",
    ),
    languages,
    routes: value.routes.map(parseInventoryRoute),
  };
}

function sameExactStringSet(actual: readonly string[], expected: readonly string[]): boolean {
  return actual.length === expected.length
    && expected.every((entry) => actual.includes(entry));
}

function assertSafeRepositoryEnginePath(
  root: string,
  relative: string,
  label: string,
): void {
  if (
    !relative.startsWith("engines/")
    || relative.includes("\\")
    || relative.includes("..")
    || path.posix.isAbsolute(relative)
    || path.posix.normalize(relative) !== relative
  ) {
    fail(
      "TRANSLATION_ENGINE_PATH_INVALID",
      `${label} 不是 engines/ 下的规范仓库相对路径。`,
    );
  }
  const resolvedRoot = realpathSync(root);
  let current = root;
  try {
    for (const segment of relative.split("/")) {
      current = path.join(/* turbopackIgnore: true */ current, segment);
      if (lstatSync(current).isSymbolicLink()) {
        fail(
          "TRANSLATION_ENGINE_PATH_UNSAFE",
          `${label} 含符号链接。`,
        );
      }
    }
    const resolved = realpathSync(current);
    const details = statSync(resolved);
    if (
      !resolved.startsWith(`${resolvedRoot}${path.sep}`)
      || (!details.isFile() && !details.isDirectory())
    ) {
      fail(
        "TRANSLATION_ENGINE_PATH_UNSAFE",
        `${label} 未解析到仓库内的普通文件或目录。`,
      );
    }
  } catch (error) {
    if (error instanceof TranslationContractError) throw error;
    fail(
      "TRANSLATION_ENGINE_PATH_MISSING",
      `${label} 在仓库中不存在。`,
    );
  }
}

function assertLanguagesMatchCatalog(root: string, inventory: RouteInventory): void {
  if (
    inventory.pending_analyzer_languages.length !== 0
    || inventory.pending_repository_languages.length !== 0
  ) {
    fail(
      "TRANSLATION_LANGUAGE_SURFACE_PENDING",
      "活动语言仍有 analyzer 或 repository surface 未接入，控制台拒绝宣称路线就绪。",
    );
  }
  if (
    inventory.deprecated_languages.length !== 1
    || inventory.deprecated_languages[0] !== "javascript"
  ) {
    fail(
      "TRANSLATION_DEPRECATED_LANGUAGE_SET_DRIFT",
      "废弃语言集合必须仅保留 JavaScript 历史分区。",
    );
  }
  const declared = new Set(Object.keys(inventory.languages));
  const catalogIds = translationLanguages.map((language) => language.id);
  const catalog = new Set<string>(catalogIds);
  if (
    !sameExactStringSet(catalogIds, ACTIVE_TRANSLATION_LANGUAGE_IDS)
    || !sameExactStringSet([...declared], ACTIVE_TRANSLATION_LANGUAGE_IDS)
  ) {
    fail(
      "TRANSLATION_ACTIVE_LANGUAGE_SET_DRIFT",
      "Web 类型目录与 inventory.languages 必须精确绑定 13 个活动语言标识。",
    );
  }
  for (const id of catalog) {
    if (!declared.has(id)) {
      fail(
        "TRANSLATION_LANGUAGE_MISSING_IN_CONTRACT",
        `Web/API 支持的语言 ${id} 未出现在 routes/inventory.json 的 languages 中。`,
      );
    }
  }
  for (const id of declared) {
    if (!catalog.has(id)) {
      fail(
        "TRANSLATION_LANGUAGE_MISSING_IN_WEB_CATALOG",
        `routes/inventory.json 声明了 Web/API 类型目录未知的语言 ${id}。`,
      );
    }
  }
  const exposed = inventory.console_exposed_languages;
  if (!sameExactStringSet(exposed, ACTIVE_TRANSLATION_LANGUAGE_IDS)) {
    fail(
      "TRANSLATION_CONSOLE_LANGUAGE_SET_DRIFT",
      "console_exposed_languages 必须精确暴露 13 个活动语言标识。",
    );
  }
  for (const language of translationLanguages) {
    const entry = inventory.languages[language.id];
    if (entry.engine_path !== language.enginePath) {
      fail(
        "TRANSLATION_ENGINE_PATH_DRIFT",
        `语言 ${language.id} 的引擎路径在契约与控制台之间不一致。`,
      );
    }
    // The contract stores one version string per language ("5.9.2 / Node
    // 26.0.0") while the console splits it into a compiler and a runtime label.
    // Every meaningful token must survive that split, so a version bump on one
    // side cannot silently diverge from the other.
    const toolchain = `${language.compiler} ${language.runtime}`;
    const tokens = entry.version.split(/[\s/]+/).filter(Boolean);
    if (tokens.length === 0) {
      fail("TRANSLATION_LANGUAGE_VERSION_EMPTY", `语言 ${language.id} 的契约版本为空。`);
    }
    for (const token of tokens) {
      if (!toolchain.includes(token)) {
        fail(
          "TRANSLATION_LANGUAGE_VERSION_DRIFT",
          `语言 ${language.id} 的版本片段 ${token} 未出现在控制台展示的工具链描述中。`,
        );
      }
    }
    assertSafeRepositoryEnginePath(root, entry.engine_path, `languages.${language.id}.engine_path`);
  }
}

function parseRoutePackEndpoint(
  value: unknown,
  label: string,
): RoutePackEndpoint {
  if (!isRecord(value)) {
    fail("TRANSLATION_ROUTE_PACK_ENDPOINT_INVALID", `${label} 不是对象。`);
  }
  return {
    language: requireString(
      value.language,
      "TRANSLATION_ROUTE_PACK_LANGUAGE_INVALID",
      `${label}.language`,
    ),
    versions: requireVersionArray(value.versions, `${label}.versions`),
    engine_path: requireString(
      value.engine_path,
      "TRANSLATION_ROUTE_PACK_ENGINE_PATH_INVALID",
      `${label}.engine_path`,
    ),
  };
}

function assertVersionMetadataMatchesInventory(
  versions: readonly string[],
  exactVersions: readonly string[],
  label: string,
): void {
  if (
    versions.length !== exactVersions.length
    || versions.some((value, index) => value !== exactVersions[index])
  ) {
    fail(
      "TRANSLATION_ROUTE_PACK_VERSION_BINDING_INVALID",
      `${label} 未与 inventory 的精确有序版本清单一致。`,
    );
  }
}

function isV3ResearchRoute(route: InventoryRoute): boolean {
  return RESEARCH_ONLY_LANGUAGE_IDS.has(route.source as TranslationLanguageId)
    || RESEARCH_ONLY_LANGUAGE_IDS.has(route.target as TranslationLanguageId);
}

function assertExactRoutePack(
  root: string,
  raw: Buffer,
  route: InventoryRoute,
  inventory: RouteInventory,
): void {
  let value: unknown;
  try {
    value = parseStrictJson(raw.toString("utf-8"));
  } catch (error) {
    if (error instanceof StrictJsonError && error.code === "DUPLICATE_JSON_FIELD") {
      fail(
        "TRANSLATION_ROUTE_PACK_DUPLICATE_FIELD",
        `路线 ${route.route_key} 的 route.json 含重复字段。`,
      );
    }
    fail(
      "TRANSLATION_ROUTE_PACK_UNPARSEABLE",
      `路线 ${route.route_key} 的 route.json 不是严格 JSON。`,
    );
  }
  if (!isRecord(value) || value.schema_version !== 1) {
    fail(
      "TRANSLATION_ROUTE_PACK_SCHEMA_INVALID",
      `路线 ${route.route_key} 的 route.json 必须使用 schema_version=1。`,
    );
  }
  const routeKey = requireString(
    value.route_key,
    "TRANSLATION_ROUTE_PACK_KEY_INVALID",
    `${route.route_key}.route_key`,
  );
  const routeVersion = requireString(
    value.version,
    "TRANSLATION_ROUTE_PACK_VERSION_INVALID",
    `${route.route_key}.version`,
  );
  const status = requireEnum(
    value.status,
    ROUTE_STATUSES,
    "TRANSLATION_ROUTE_PACK_STATUS_INVALID",
    `${route.route_key}.status`,
  );
  const source = parseRoutePackEndpoint(value.source, `${route.route_key}.source`);
  const target = parseRoutePackEndpoint(value.target, `${route.route_key}.target`);
  if (
    routeKey !== route.route_key
    || source.language !== route.source
    || target.language !== route.target
    || status !== route.status
  ) {
    fail(
      "TRANSLATION_ROUTE_PACK_BINDING_INVALID",
      `路线 ${route.route_key} 的 Route Pack 未绑定同一方向和状态。`,
    );
  }
  const researchOnly = isV3ResearchRoute(route);
  if (researchOnly && status !== "research") {
    fail(
      "TRANSLATION_ROUTE_RESEARCH_BOUNDARY_VIOLATED",
      `路线 ${route.route_key} 尚属 Kotlin/React/Flutter research 边界，不能静默升级。`,
    );
  }
  if (researchOnly && routeVersion !== V3_RESEARCH_ROUTE_VERSION) {
    fail(
      "TRANSLATION_ROUTE_V3_VERSION_INVALID",
      `路线 ${route.route_key} 的 V3 Route Pack 必须保持 0.1.0 research 版本。`,
    );
  }
  if (researchOnly) {
    const profiles = value.profiles;
    const paths = value.paths;
    if (
      !isRecord(profiles)
      || !hasExactKeys(profiles, ["semantic_profile", "target_profile"])
      || profiles.semantic_profile !== ""
      || profiles.target_profile !== ""
      || !Array.isArray(value.framework_profiles)
      || value.framework_profiles.length !== 0
      || !isRecord(paths)
      || paths.support_matrix !== "support-matrix.json"
      || paths.corpus !== "corpus"
      || paths.certification !== "certification"
    ) {
      fail(
        "TRANSLATION_ROUTE_V3_PROFILE_OVERCLAIM",
        `路线 ${route.route_key} 的 V3 Route Pack 必须保持空语义/目标 Profile 与规范路径绑定。`,
      );
    }
  }
  const sourceLanguage = inventory.languages[route.source];
  const targetLanguage = inventory.languages[route.target];
  if (
    source.engine_path !== sourceLanguage.engine_path
    || target.engine_path !== TARGET_EMITTER_RELATIVE_PATH
  ) {
    fail(
      "TRANSLATION_ROUTE_PACK_ENGINE_BINDING_INVALID",
      `路线 ${route.route_key} 未绑定真实源分析器或统一目标 emitter。`,
    );
  }
  assertVersionMetadataMatchesInventory(
    source.versions,
    sourceLanguage.exact_versions,
    `${route.route_key}.source.versions`,
  );
  assertVersionMetadataMatchesInventory(
    target.versions,
    targetLanguage.exact_versions,
    `${route.route_key}.target.versions`,
  );
  assertSafeRepositoryEnginePath(root, source.engine_path, `${route.route_key}.source.engine_path`);
  assertSafeRepositoryEnginePath(root, target.engine_path, `${route.route_key}.target.engine_path`);
}

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const observed = Object.keys(value).sort();
  const canonical = [...expected].sort();
  return observed.length === canonical.length
    && observed.every((key, index) => key === canonical[index]);
}

function assertExactV3ResearchCertification(
  raw: Buffer,
  route: InventoryRoute,
): void {
  let value: unknown;
  try {
    value = parseStrictJson(raw.toString("utf-8"));
  } catch (error) {
    if (error instanceof StrictJsonError && error.code === "DUPLICATE_JSON_FIELD") {
      fail(
        "TRANSLATION_ROUTE_V3_CERTIFICATION_DUPLICATE_FIELD",
        `路线 ${route.route_key} 的 V3 certification 含重复 JSON 字段。`,
      );
    }
    fail(
      "TRANSLATION_ROUTE_V3_CERTIFICATION_UNPARSEABLE",
      `路线 ${route.route_key} 的 V3 certification 不是严格 JSON。`,
    );
  }
  if (!isRecord(value)) {
    fail(
      "TRANSLATION_ROUTE_V3_CERTIFICATION_SHAPE_INVALID",
      `路线 ${route.route_key} 的 V3 certification 顶层不是对象。`,
    );
  }
  const gateResults = value.gate_results;
  const metrics = value.metrics;
  const evidenceRefs = value.evidence_refs;
  if (
    !hasExactKeys(value, V3_RESEARCH_CERTIFICATION_KEYS)
    || !isRecord(gateResults)
    || !hasExactKeys(gateResults, V3_RESEARCH_GATE_KEYS)
    || !isRecord(metrics)
    || !hasExactKeys(metrics, V3_RESEARCH_METRIC_KEYS)
    || !Array.isArray(evidenceRefs)
  ) {
    fail(
      "TRANSLATION_ROUTE_V3_CERTIFICATION_SHAPE_INVALID",
      `路线 ${route.route_key} 的 V3 certification 字段与 canonical contract 不一致。`,
    );
  }
  if (
    value.schema_version !== 1
    || value.route_key !== route.route_key
    || value.route_version !== V3_RESEARCH_ROUTE_VERSION
    || value.status !== "research"
    || value.certification_decision !== "NOT_CERTIFIED"
    || value.declared_scope !== V3_RESEARCH_DECLARED_SCOPE
    || value.issued_at !== V3_RESEARCH_ISSUED_AT
    || value.next_review_at !== V3_RESEARCH_NEXT_REVIEW_AT
    || evidenceRefs.length !== 0
    || V3_RESEARCH_GATE_KEYS.some(
      (key) => gateResults[key] !== "NOT_RUN",
    )
    || V3_RESEARCH_METRIC_KEYS.some(
      (key) => metrics[key] !== null,
    )
  ) {
    fail(
      "TRANSLATION_ROUTE_V3_CERTIFICATION_CONTRACT_INVALID",
      `路线 ${route.route_key} 的 V3 certification 未保持 research / NOT_RUN / NOT_CERTIFIED 边界。`,
    );
  }
}

function assertExactV3ResearchSupportMatrix(
  raw: Buffer,
  route: InventoryRoute,
): void {
  let value: unknown;
  try {
    value = parseStrictJson(raw.toString("utf-8"));
  } catch (error) {
    if (error instanceof StrictJsonError && error.code === "DUPLICATE_JSON_FIELD") {
      fail(
        "TRANSLATION_ROUTE_V3_SUPPORT_DUPLICATE_FIELD",
        `路线 ${route.route_key} 的 V3 support-matrix.json 含重复 JSON 字段。`,
      );
    }
    fail(
      "TRANSLATION_ROUTE_V3_SUPPORT_UNPARSEABLE",
      `路线 ${route.route_key} 的 V3 support-matrix.json 不是严格 JSON。`,
    );
  }
  if (
    !isRecord(value)
    || !hasExactKeys(value, V3_RESEARCH_SUPPORT_KEYS)
    || !Array.isArray(value.capabilities)
    || value.capabilities.length !== V3_RESEARCH_SUPPORT_CAPABILITIES.length
  ) {
    fail(
      "TRANSLATION_ROUTE_V3_SUPPORT_SHAPE_INVALID",
      `路线 ${route.route_key} 的 V3 support-matrix.json 与 canonical scaffold 形状不一致。`,
    );
  }
  if (value.schema_version !== 1 || value.route_key !== route.route_key) {
    fail(
      "TRANSLATION_ROUTE_V3_SUPPORT_CONTRACT_INVALID",
      `路线 ${route.route_key} 的 V3 support-matrix.json 未绑定精确路线。`,
    );
  }
  const seen = new Set<string>();
  value.capabilities.forEach((capability, index) => {
    const expected = V3_RESEARCH_SUPPORT_CAPABILITIES[index];
    if (
      !isRecord(capability)
      || !hasExactKeys(capability, V3_RESEARCH_CAPABILITY_KEYS)
      || capability.id !== expected[0]
      || capability.status !== expected[1]
      || capability.strategy !== expected[2]
      || capability.reason !== expected[3]
      || !Array.isArray(capability.evidence_refs)
      || capability.evidence_refs.length !== 0
      || seen.has(expected[0])
    ) {
      fail(
        "TRANSLATION_ROUTE_V3_SUPPORT_CONTRACT_INVALID",
        `路线 ${route.route_key} 的 V3 capability 不是未执行的 canonical research 声明。`,
      );
    }
    seen.add(expected[0]);
  });
}

function assertExactV3ResearchEvidence(
  raw: Buffer,
  route: InventoryRoute,
): void {
  let value: unknown;
  try {
    value = parseStrictJson(raw.toString("utf-8"));
  } catch (error) {
    if (error instanceof StrictJsonError && error.code === "DUPLICATE_JSON_FIELD") {
      fail(
        "TRANSLATION_ROUTE_V3_EVIDENCE_DUPLICATE_FIELD",
        `路线 ${route.route_key} 的 V3 evidence.json 含重复 JSON 字段。`,
      );
    }
    fail(
      "TRANSLATION_ROUTE_V3_EVIDENCE_UNPARSEABLE",
      `路线 ${route.route_key} 的 V3 evidence.json 不是严格 JSON。`,
    );
  }
  if (!isRecord(value)) {
    fail(
      "TRANSLATION_ROUTE_V3_EVIDENCE_SHAPE_INVALID",
      `路线 ${route.route_key} 的 V3 evidence.json 顶层不是对象。`,
    );
  }
  const metrics = value.metrics;
  const notes = value.notes;
  if (
    !hasExactKeys(value, V3_RESEARCH_EVIDENCE_KEYS)
    || !isRecord(metrics)
    || !hasExactKeys(metrics, V3_RESEARCH_METRIC_KEYS)
    || !Array.isArray(value.runs)
    || !Array.isArray(value.negative_runs)
    || !Array.isArray(notes)
  ) {
    fail(
      "TRANSLATION_ROUTE_V3_EVIDENCE_SHAPE_INVALID",
      `路线 ${route.route_key} 的 V3 evidence.json 字段与 canonical contract 不一致。`,
    );
  }
  if (
    value.schema_version !== 1
    || value.route_key !== route.route_key
    || value.route_version !== V3_RESEARCH_ROUTE_VERSION
    || value.route_maturity !== "RESEARCH"
    || value.execution_status !== "NOT_RUN"
    || value.module_execution_status !== "NOT_RUN"
    || value.repository_execution_status !== "NOT_RUN"
    || value.independent_verification_status !== "NOT_RUN"
    || value.external_certification_status !== "NOT_RUN"
    || value.runs.length !== 0
    || value.negative_runs.length !== 0
    || V3_RESEARCH_METRIC_KEYS.some((key) => metrics[key] !== null)
    || value.critical_unknown_semantics !== null
    || value.critical_behavior_regressions !== null
    || value.test_integrity_violations !== null
    || notes.length !== V3_RESEARCH_EVIDENCE_NOTES.length
    || V3_RESEARCH_EVIDENCE_NOTES.some((note, index) => notes[index] !== note)
  ) {
    fail(
      "TRANSLATION_ROUTE_V3_EVIDENCE_CONTRACT_INVALID",
      `路线 ${route.route_key} 的 V3 evidence.json 未保持 research / NOT_RUN / null-metrics 边界。`,
    );
  }
}

function assertExactRepositoryEvidence(
  raw: Buffer,
  route: InventoryRoute,
): void {
  let value: unknown;
  try {
    value = JSON.parse(raw.toString("utf-8"));
  } catch {
    fail(
      "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_UNPARSEABLE",
      `路线 ${route.route_key} 的仓库级证据不是合法 JSON。`,
    );
  }
  if (!isRecord(value)) {
    fail(
      "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_INVALID",
      `路线 ${route.route_key} 的仓库级证据顶层不是对象。`,
    );
  }
  const required = [
    "schema_version",
    "kind",
    "route_id",
    "source_language",
    "target_language",
    "profile",
    "status",
    "repository_execution_status",
    "external_verification_status",
    "certification_status",
  ].sort();
  if (Object.keys(value).sort().join(",") !== required.join(",")) {
    fail(
      "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_SHAPE_INVALID",
      `路线 ${route.route_key} 的仓库级证据字段不完整或含未声明字段。`,
    );
  }
  if (
    value.schema_version !== "1.0.0"
    || value.kind !== "elmos.repository-route-execution-evidence"
    || value.route_id !== route.route_key
    || value.source_language !== route.source
    || value.target_language !== route.target
    || value.profile !== route.repository_profile
    || value.status !== "PASSED"
    || value.repository_execution_status !== "PASSED"
    || value.external_verification_status !== "NOT_RUN"
    || value.certification_status !== "NOT_CERTIFIED"
  ) {
    fail(
      "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_BINDING_INVALID",
      `路线 ${route.route_key} 的仓库级证据未绑定精确方向、Profile 或 PASSED 状态。`,
    );
  }
}

function readVerifiedRepositoryEvidence(routeRoot: string, route: InventoryRoute): Buffer {
  const reference = route.repository_evidence_ref;
  const expectedDigest = route.repository_evidence_sha256;
  const expectedBytes = route.repository_evidence_bytes;
  if (!reference || !expectedDigest || expectedBytes === null) {
    fail(
      "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_INCOMPLETE",
      `路线 ${route.route_key} 缺少仓库级证据描述符。`,
    );
  }
  const evidence = path.resolve(/* turbopackIgnore: true */ routeRoot, reference);
  const raw = readStableRegularFile(routeRoot, evidence, {
    unsafeCode: "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_UNSAFE",
    changedCode: "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_CHANGED",
    label: `路线 ${route.route_key} 的仓库级证据`,
    maxBytes: MAX_REPOSITORY_EVIDENCE_BYTES,
  });
  const observedDigest = createHash("sha256").update(raw).digest("hex");
  if (raw.byteLength !== expectedBytes || observedDigest !== expectedDigest) {
    fail(
      "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_INTEGRITY_MISMATCH",
      `路线 ${route.route_key} 的仓库级证据摘要或字节数与 inventory 不一致。`,
    );
  }
  return raw;
}

function assertRoutePacksExist(root: string, inventory: RouteInventory): void {
  for (const route of inventory.routes) {
    const routeRoot = path.join(
      /* turbopackIgnore: true */ root,
      "routes",
      route.route_key,
    );
    const pack = path.join(/* turbopackIgnore: true */ routeRoot, "route.json");
    const support = path.join(/* turbopackIgnore: true */ routeRoot, "support-matrix.json");
    const certificationRoot = path.join(
      /* turbopackIgnore: true */ routeRoot,
      "certification",
    );
    const certification = path.join(
      /* turbopackIgnore: true */ certificationRoot,
      "certification.json",
    );
    const evidence = path.join(
      /* turbopackIgnore: true */ certificationRoot,
      "evidence.json",
    );
    let packRaw: Buffer;
    let certificationRaw: Buffer;
    let supportRaw: Buffer | null = null;
    let evidenceRaw: Buffer | null = null;
    try {
      const routesRoot = path.join(/* turbopackIgnore: true */ root, "routes");
      assertSafeConfinedDirectory(
        routesRoot,
        routeRoot,
        "TRANSLATION_ROUTE_PACK_UNSAFE",
        `路线 ${route.route_key} 的 Route Pack 目录`,
      );
      assertSafeConfinedDirectory(
        routeRoot,
        certificationRoot,
        "TRANSLATION_ROUTE_CERTIFICATION_DIRECTORY_UNSAFE",
        `路线 ${route.route_key} 的 certification 目录`,
      );
      packRaw = readStableRegularFile(routeRoot, pack, {
        unsafeCode: "TRANSLATION_ROUTE_PACK_UNSAFE",
        changedCode: "TRANSLATION_ROUTE_PACK_CHANGED",
        label: `路线 ${route.route_key} 的 route.json`,
        maxBytes: MAX_ROUTE_PACK_BYTES,
      });
      certificationRaw = readStableRegularFile(routeRoot, certification, {
        unsafeCode: "TRANSLATION_ROUTE_CERTIFICATION_FILE_UNSAFE",
        changedCode: "TRANSLATION_ROUTE_CERTIFICATION_FILE_CHANGED",
        label: `路线 ${route.route_key} 的 certification.json`,
        maxBytes: MAX_ROUTE_CERTIFICATION_BYTES,
      });
      if (isV3ResearchRoute(route)) {
        supportRaw = readStableRegularFile(routeRoot, support, {
          unsafeCode: "TRANSLATION_ROUTE_V3_SUPPORT_FILE_UNSAFE",
          changedCode: "TRANSLATION_ROUTE_V3_SUPPORT_FILE_CHANGED",
          label: `路线 ${route.route_key} 的 support-matrix.json`,
          maxBytes: MAX_ROUTE_PACK_BYTES,
        });
        evidenceRaw = readStableRegularFile(routeRoot, evidence, {
          unsafeCode: "TRANSLATION_ROUTE_V3_EVIDENCE_FILE_UNSAFE",
          changedCode: "TRANSLATION_ROUTE_V3_EVIDENCE_FILE_CHANGED",
          label: `路线 ${route.route_key} 的 certification/evidence.json`,
          maxBytes: MAX_ROUTE_CERTIFICATION_BYTES,
        });
      }
    } catch (error) {
      if (error instanceof TranslationContractError) throw error;
      fail(
        "TRANSLATION_ROUTE_PACK_MISSING",
        `路线 ${route.route_key} 在 inventory 中声明，但缺少安全的 route.json。`,
      );
    }
    assertExactRoutePack(root, packRaw, route, inventory);
    if (isV3ResearchRoute(route)) {
      if (supportRaw === null || evidenceRaw === null) {
        fail(
          "TRANSLATION_ROUTE_V3_DOCUMENT_SET_INCOMPLETE",
          `路线 ${route.route_key} 缺少 V3 research 四件套。`,
        );
      }
      assertExactV3ResearchSupportMatrix(supportRaw, route);
      assertExactV3ResearchCertification(certificationRaw, route);
      assertExactV3ResearchEvidence(evidenceRaw, route);
    }
    if (route.repository_execution_status === "PASSED") {
      let raw: Buffer;
      try {
        raw = readVerifiedRepositoryEvidence(routeRoot, route);
      } catch (error) {
        if (error instanceof TranslationContractError) throw error;
        fail(
          "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_MISSING",
          `路线 ${route.route_key} 的仓库级证据无法安全读取。`,
        );
      }
      assertExactRepositoryEvidence(raw, route);
    }
  }
}

function assertCountsAreConsistent(inventory: RouteInventory): void {
  if (inventory.route_count !== ACTIVE_ROUTE_COUNT) {
    fail(
      "TRANSLATION_ROUTE_MATRIX_SIZE_INVALID",
      `活动路线必须精确覆盖 13×12=${ACTIVE_ROUTE_COUNT} 个方向。`,
    );
  }
  if (inventory.route_count !== inventory.routes.length) {
    fail("TRANSLATION_ROUTE_COUNT_DRIFT", "route_count 与 routes 数组长度不一致。");
  }
  const byStatus = (status: RouteStatus) =>
    inventory.routes.filter((route) => route.status === status).length;
  if (byStatus("research") !== inventory.research_route_count) {
    fail("TRANSLATION_RESEARCH_COUNT_DRIFT", "research_route_count 与实际路线状态不一致。");
  }
  if (byStatus("experimental") !== inventory.experimental_route_count) {
    fail("TRANSLATION_EXPERIMENTAL_COUNT_DRIFT", "experimental_route_count 与实际路线状态不一致。");
  }
  if (byStatus("limited") !== inventory.limited_route_count) {
    fail("TRANSLATION_LIMITED_COUNT_DRIFT", "limited_route_count 与实际路线状态不一致。");
  }
  if (byStatus("certified") !== inventory.certified_route_count) {
    fail("TRANSLATION_CERTIFIED_COUNT_DRIFT", "certified_route_count 与实际路线状态不一致。");
  }
  if (byStatus("blocked") !== inventory.blocked_route_count) {
    fail("TRANSLATION_BLOCKED_COUNT_DRIFT", "blocked_route_count 与实际路线状态不一致。");
  }
  const active = new Set<string>(ACTIVE_TRANSLATION_LANGUAGE_IDS);
  const expected = new Set(
    ACTIVE_TRANSLATION_LANGUAGE_IDS.flatMap((source) =>
      ACTIVE_TRANSLATION_LANGUAGE_IDS
        .filter((target) => target !== source)
        .map((target) => `${source}-to-${target}`)),
  );
  const seen = new Set<string>();
  for (const route of inventory.routes) {
    if (route.route_key !== `${route.source}-to-${route.target}`) {
      fail("TRANSLATION_ROUTE_KEY_DRIFT", `路线键 ${route.route_key} 与 source/target 不一致。`);
    }
    if (route.source === route.target) {
      fail("TRANSLATION_ROUTE_SELF_DIRECTED", `路线 ${route.route_key} 的源与目标相同。`);
    }
    if (
      !active.has(route.source)
      || !active.has(route.target)
      || route.source === "javascript"
      || route.target === "javascript"
    ) {
      fail(
        "TRANSLATION_ROUTE_INACTIVE_LANGUAGE",
        `路线 ${route.route_key} 引用了非活动或已废弃语言。`,
      );
    }
    if (seen.has(route.route_key)) {
      fail("TRANSLATION_ROUTE_DUPLICATED", `路线 ${route.route_key} 重复声明。`);
    }
    seen.add(route.route_key);
    const language = inventory.languages[route.source];
    const target = inventory.languages[route.target];
    if (!language || !target) {
      fail("TRANSLATION_ROUTE_LANGUAGE_UNKNOWN", `路线 ${route.route_key} 引用了未声明的语言。`);
    }
    if (language.version !== route.source_version || target.version !== route.target_version) {
      fail(
        "TRANSLATION_ROUTE_VERSION_DRIFT",
        `路线 ${route.route_key} 的语言版本与 languages 映射不一致。`,
      );
    }
    const researchOnly = isV3ResearchRoute(route);
    if (
      researchOnly
      && (
        route.status !== "research"
        || route.route_set !== V3_ROUTE_SET
        || route.local_execution_reason !== V3_LOCAL_EXECUTION_REASON
        || route.local_execution_status !== "NOT_RUN"
        || route.module_execution_status !== "NOT_APPLICABLE"
        || route.repository_execution_status !== "NOT_RUN"
        || route.repository_profile !== null
        || route.repository_evidence_ref !== null
        || route.repository_evidence_sha256 !== null
        || route.repository_evidence_bytes !== null
        || route.independent_verification_status !== "NOT_RUN"
        || route.external_certification_status !== "NOT_RUN"
      )
    ) {
      fail(
        "TRANSLATION_ROUTE_RESEARCH_EVIDENCE_OVERCLAIM",
        `路线 ${route.route_key} 仍属 V3 research 分区，所有 route/repository/external 证据必须保持 NOT_RUN。`,
      );
    }
    // Evidence may never run ahead of itself: independent verification needs a
    // local pass, and external certification needs an independent pass.
    if (route.independent_verification_status === "PASSED" && route.local_execution_status !== "PASSED_LOCAL") {
      fail(
        "TRANSLATION_ROUTE_EVIDENCE_INVERTED",
        `路线 ${route.route_key} 在本地未通过的情况下声明了独立验证通过。`,
      );
    }
    if (route.repository_execution_status === "PASSED" && route.local_execution_status !== "PASSED_LOCAL") {
      fail(
        "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_INVERTED",
        `路线 ${route.route_key} 在片段级本地执行未通过的情况下声明了仓库级执行通过。`,
      );
    }
    if (route.external_certification_status === "PASSED") {
      if (route.local_execution_status !== "PASSED_LOCAL") {
        fail(
          "TRANSLATION_ROUTE_EVIDENCE_INVERTED",
          `路线 ${route.route_key} 在本地未通过的情况下声明了外部认证通过。`,
        );
      }
      if (route.independent_verification_status !== "PASSED") {
        fail(
          "TRANSLATION_ROUTE_CERTIFICATION_PRECEDES_VERIFICATION",
          `路线 ${route.route_key} 在独立验证未通过的情况下声明了外部认证通过。`,
        );
      }
    }
    if (route.status === "certified" && route.external_certification_status !== "PASSED") {
      fail(
        "TRANSLATION_ROUTE_CERTIFICATION_UNSUPPORTED",
        `路线 ${route.route_key} 标记为 certified，但外部认证证据不是 PASSED。`,
      );
    }
  }
  if (seen.size !== expected.size || [...expected].some((routeKey) => !seen.has(routeKey))) {
    fail(
      "TRANSLATION_ROUTE_MATRIX_INCOMPLETE",
      "routes 必须精确包含 13 个活动语言的全部 156 个有向排列。",
    );
  }
}

function toConsoleRoute(route: InventoryRoute): DirectedLanguageRoute {
  const source = route.source as TranslationLanguageId;
  const target = route.target as TranslationLanguageId;
  const researchOnly = route.status === "research";
  const localExecution = route.local_execution_status === "PASSED_LOCAL"
    ? "PASSED"
    : route.local_execution_status;
  return {
    id: route.route_key,
    source,
    target,
    skill: translationCertificationSkill(source, target),
    status: route.status === "certified"
      ? "CERTIFIED"
      : route.status === "limited"
        ? "LIMITED"
        : route.status === "research"
          ? "RESEARCH"
          : route.status === "blocked"
            ? "BLOCKED"
            : "EXPERIMENTAL",
    readiness: localExecution === "PASSED" ? "LOCAL_PROFILE_PASSED" : "NOT_RUN",
    localExecution,
    repositoryExecutionStatus: route.repository_execution_status,
    repositoryProfile: route.repository_profile,
    repositoryEvidenceRef: route.repository_evidence_ref,
    repositoryEvidenceSha256: route.repository_evidence_sha256,
    repositoryEvidenceBytes: route.repository_evidence_bytes,
    independentVerification: route.independent_verification_status,
    externalVerification: route.external_certification_status,
    sourceVersion: route.source_version,
    targetVersion: route.target_version,
    hazards: translationHazards(source, target),
    blockers: [
      ...(route.repository_execution_status === "PASSED"
        ? []
        : [`仓库级执行 ${route.repository_execution_status}；片段级本地通过不会放行整库任务`]),
      ...(researchOnly
        ? [
            "路线仍为 research：语义 Profile 与目标 Profile 均未准入",
            "分析器与发射器的精确版本绑定不构成路线执行或行为等价证据",
          ]
        : [
            "仅支持 typed-pure-function-v1：显式基本类型、if、return 与受限二元运算",
            "对象图、异常、async、I/O、反射、框架、数据库与并发必须拆到精确 Pack",
          ]),
      "独立验证者、真实客户仓库与外部认证仍为 NOT_RUN",
    ],
  };
}

function readTranslationCapabilityForAudience(
  audience: "CONSOLE" | "EXECUTION",
): TranslationCapabilityResponse {
  const root = resolveRepositoryRoot();
  const contractPath = path.join(
    /* turbopackIgnore: true */ root,
    ROUTE_INVENTORY_RELATIVE_PATH,
  );
  const raw = readStableRegularFile(root, contractPath, {
    unsafeCode: "TRANSLATION_ROUTE_INVENTORY_UNSAFE",
    changedCode: "TRANSLATION_ROUTE_INVENTORY_CHANGED",
    label: "routes/inventory.json",
    maxBytes: 2 * 1024 * 1024,
  }).toString("utf8");
  const inventory = parseInventory(raw);
  assertLanguagesMatchCatalog(root, inventory);
  assertCountsAreConsistent(inventory);
  assertRoutePacksExist(root, inventory);

  const exposed = new Set(inventory.console_exposed_languages);
  const selectedInventoryRoutes = audience === "EXECUTION"
    ? inventory.routes
    : inventory.routes.filter((route) => exposed.has(route.source) && exposed.has(route.target));
  const languages = audience === "EXECUTION"
    ? translationLanguages
    : inventory.console_exposed_languages.map((id) => {
      const language = translationLanguages.find((candidate) => candidate.id === id);
      if (!language) {
        fail("TRANSLATION_CONSOLE_LANGUAGE_UNKNOWN", `控制台语言 ${id} 不在 Web/API 类型目录中。`);
      }
      return language;
    });
  const routes = selectedInventoryRoutes.map(toConsoleRoute);
  const locallyPassed = routes.filter((route) => route.localExecution === "PASSED").length;
  const repositoryPassed = routes.filter(
    (route) => route.repositoryExecutionStatus === "PASSED",
  ).length;
  const repositoryExecutionEvidence = routes.some(
    (route) => route.repositoryExecutionStatus === "FAILED",
  )
    ? "FAILED"
    : routes.length > 0 && repositoryPassed === routes.length
      ? "PASSED"
      : "NOT_RUN";
  return {
    source: "REPOSITORY_CONTRACT",
    fetchedAt: new Date().toISOString(),
    schemaVersion: "1.1.0",
    contractPath: ROUTE_INVENTORY_RELATIVE_PATH,
    semanticProfile: inventory.semantic_profile,
    languages,
    routes,
    routePackageCount: inventory.route_count,
    certifiedRouteCount: inventory.certified_route_count,
    repositoryExecutableRouteCount: repositoryPassed,
    repositoryPlanning: "LOCAL_MANIFEST_SUPPORTED",
    localExecutionEvidence: inventory.local_execution_evidence,
    repositoryExecutionEvidence,
    independentVerificationEvidence: inventory.independent_verification_evidence,
    externalExecutionEvidence: inventory.external_certification_evidence,
    // Individual route certification is directional and cannot certify the
    // complete 13-language product surface. Schema 1.4 has no independently
    // verified full-matrix gate receipt, so the aggregate must remain closed.
    certificationStatus: "NOT_CERTIFIED",
    note: `${inventory.route_count} 条有向路线的状态直接来自 ${ROUTE_INVENTORY_RELATIVE_PATH} 与同级 Route Pack：`
      + `${locallyPassed} 条已在精确本地工具链上完成 ${inventory.semantic_profile} 的编译与行为回放，`
      + `${repositoryPassed} 条具有独立仓库级 Profile 与证据引用，`
      + `独立验证 ${inventory.independent_verification_evidence}，外部认证 ${inventory.external_certification_evidence}。`
      + "片段级本地通过不会放行整库任务；整库受控 Runner 只接受 repositoryExecutionStatus=PASSED 的路线，"
      + "并以只读源码和独立行为用例逐单元执行；任何跳过或失败保持 PARTIAL，"
      + "本地归档不会改变独立验证与外部认证状态；单条 certified 路线仅计数，"
      + "没有独立的完整 156 路线矩阵门禁时，全局状态始终为 NOT_CERTIFIED。",
  };
}

export function readTranslationCapability(): TranslationCapabilityResponse {
  return readTranslationCapabilityForAudience("CONSOLE");
}

/** Server-side execution admission sees every explicit inventory route. */
export function readTranslationExecutionCapability(): TranslationCapabilityResponse {
  return readTranslationCapabilityForAudience("EXECUTION");
}

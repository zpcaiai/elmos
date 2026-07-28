import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { translationHazards, translationLanguages } from "../businessLines";
import type {
  DirectedLanguageRoute,
  TranslationCapabilityResponse,
  TranslationLanguageId,
} from "../contracts";

/**
 * The cross-language business line advertises directed route readiness. That
 * readiness is owned by `routes/inventory.json` and the per-route packs beside
 * it, never by a constant compiled into the web console. This reader resolves
 * the repository contract at request time and fails closed on any drift so the
 * console can never assert a local pass it has not read.
 */

const ROUTE_INVENTORY_RELATIVE_PATH = "routes/inventory.json";
const LOCAL_EXECUTION_STATUSES = ["PASSED_LOCAL", "NOT_RUN", "FAILED"] as const;
const VERIFICATION_STATUSES = ["PASSED", "NOT_RUN", "FAILED"] as const;
const ROUTE_STATUSES = ["research", "experimental", "limited", "certified", "blocked"] as const;
const MAX_ROOT_WALK_DEPTH = 8;

type LocalExecutionStatus = (typeof LOCAL_EXECUTION_STATUSES)[number];
type VerificationStatus = (typeof VERIFICATION_STATUSES)[number];
type RouteStatus = (typeof ROUTE_STATUSES)[number];

type InventoryRoute = {
  route_key: string;
  source: string;
  target: string;
  source_version: string;
  target_version: string;
  status: RouteStatus;
  local_execution_status: LocalExecutionStatus;
  independent_verification_status: VerificationStatus;
  external_certification_status: VerificationStatus;
};

type InventoryLanguage = { version: string; engine_path: string };

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
    local_execution_status: requireEnum(
      value.local_execution_status,
      LOCAL_EXECUTION_STATUSES,
      "TRANSLATION_ROUTE_LOCAL_STATUS_INVALID",
      `routes[${index}].local_execution_status`,
    ),
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
    value = JSON.parse(raw);
  } catch {
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

  const languages: Record<string, InventoryLanguage> = {};
  for (const [id, entry] of Object.entries(value.languages)) {
    if (!isRecord(entry)) {
      fail("TRANSLATION_LANGUAGE_ENTRY_INVALID", `languages.${id} 不是对象。`);
    }
    languages[id] = {
      version: requireString(entry.version, "TRANSLATION_LANGUAGE_VERSION_INVALID", `languages.${id}.version`),
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
    languages,
    routes: value.routes.map(parseInventoryRoute),
  };
}

function assertLanguagesMatchConsole(inventory: RouteInventory): void {
  const declared = new Set(Object.keys(inventory.languages));
  const console = new Set<string>(translationLanguages.map((language) => language.id));
  for (const id of console) {
    if (!declared.has(id)) {
      fail(
        "TRANSLATION_LANGUAGE_MISSING_IN_CONTRACT",
        `控制台展示的语言 ${id} 未出现在 routes/inventory.json 的 languages 中。`,
      );
    }
  }
  for (const id of declared) {
    if (!console.has(id)) {
      fail(
        "TRANSLATION_LANGUAGE_MISSING_IN_CONSOLE",
        `routes/inventory.json 声明了控制台未展示的语言 ${id}。`,
      );
    }
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
  }
}

function assertRoutePacksExist(root: string, inventory: RouteInventory): void {
  for (const route of inventory.routes) {
    const pack = path.join(
      /* turbopackIgnore: true */ root,
      "routes",
      route.route_key,
      "route.json",
    );
    if (!existsSync(pack)) {
      fail(
        "TRANSLATION_ROUTE_PACK_MISSING",
        `路线 ${route.route_key} 在 inventory 中声明，但缺少 routes/${route.route_key}/route.json。`,
      );
    }
  }
}

function assertCountsAreConsistent(inventory: RouteInventory): void {
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
  const seen = new Set<string>();
  for (const route of inventory.routes) {
    if (route.route_key !== `${route.source}-to-${route.target}`) {
      fail("TRANSLATION_ROUTE_KEY_DRIFT", `路线键 ${route.route_key} 与 source/target 不一致。`);
    }
    if (route.source === route.target) {
      fail("TRANSLATION_ROUTE_SELF_DIRECTED", `路线 ${route.route_key} 的源与目标相同。`);
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
    // Evidence may never run ahead of itself: independent verification needs a
    // local pass, and external certification needs an independent pass.
    if (route.independent_verification_status === "PASSED" && route.local_execution_status !== "PASSED_LOCAL") {
      fail(
        "TRANSLATION_ROUTE_EVIDENCE_INVERTED",
        `路线 ${route.route_key} 在本地未通过的情况下声明了独立验证通过。`,
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
}

function toConsoleRoute(route: InventoryRoute): DirectedLanguageRoute {
  const source = route.source as TranslationLanguageId;
  const target = route.target as TranslationLanguageId;
  const localExecution = route.local_execution_status === "PASSED_LOCAL"
    ? "PASSED"
    : route.local_execution_status;
  return {
    id: route.route_key,
    source,
    target,
    skill: `b29-certify-${source}-to-${target}`,
    status: route.status === "certified"
      ? "CERTIFIED"
      : route.status === "limited"
        ? "LIMITED"
        : route.status === "blocked"
          ? "BLOCKED"
          : "EXPERIMENTAL",
    readiness: localExecution === "PASSED" ? "LOCAL_PROFILE_PASSED" : "NOT_RUN",
    localExecution,
    independentVerification: route.independent_verification_status,
    externalVerification: route.external_certification_status,
    sourceVersion: route.source_version,
    targetVersion: route.target_version,
    hazards: translationHazards(source, target),
    blockers: [
      "仅支持 typed-pure-function-v1：显式基本类型、if、return 与受限二元运算",
      "对象图、异常、async、I/O、反射、框架、数据库与并发必须拆到精确 Pack",
      "独立验证者、真实客户仓库与外部认证仍为 NOT_RUN",
    ],
  };
}

export function readTranslationCapability(): TranslationCapabilityResponse {
  const root = resolveRepositoryRoot();
  const contractPath = path.join(
    /* turbopackIgnore: true */ root,
    ROUTE_INVENTORY_RELATIVE_PATH,
  );
  let raw: string;
  try {
    raw = readFileSync(contractPath, "utf8");
  } catch {
    fail("TRANSLATION_ROUTE_INVENTORY_UNREADABLE", "无法读取 routes/inventory.json。");
  }
  if (raw.length > 2 * 1024 * 1024) {
    fail("TRANSLATION_ROUTE_INVENTORY_TOO_LARGE", "routes/inventory.json 超过 2 MB 上限。");
  }
  const inventory = parseInventory(raw);
  assertLanguagesMatchConsole(inventory);
  assertCountsAreConsistent(inventory);
  assertRoutePacksExist(root, inventory);

  const routes = inventory.routes.map(toConsoleRoute);
  const locallyPassed = routes.filter((route) => route.localExecution === "PASSED").length;
  return {
    source: "REPOSITORY_CONTRACT",
    fetchedAt: new Date().toISOString(),
    schemaVersion: "1.1.0",
    contractPath: ROUTE_INVENTORY_RELATIVE_PATH,
    semanticProfile: inventory.semantic_profile,
    languages: translationLanguages,
    routes,
    routePackageCount: inventory.route_count,
    certifiedRouteCount: inventory.certified_route_count,
    repositoryPlanning: "LOCAL_MANIFEST_SUPPORTED",
    localExecutionEvidence: inventory.local_execution_evidence,
    independentVerificationEvidence: inventory.independent_verification_evidence,
    externalExecutionEvidence: inventory.external_certification_evidence,
    certificationStatus: inventory.certified_route_count > 0 ? "CERTIFIED" : "NOT_CERTIFIED",
    note: `${inventory.route_count} 条有向路线的状态直接来自 ${ROUTE_INVENTORY_RELATIVE_PATH} 与同级 Route Pack：`
      + `${locallyPassed} 条已在精确本地工具链上完成 ${inventory.semantic_profile} 的编译与行为回放，`
      + `独立验证 ${inventory.independent_verification_evidence}，外部认证 ${inventory.external_certification_evidence}。`
      + "整库受控 Runner 以只读源码和独立行为用例逐单元执行；任何跳过或失败保持 PARTIAL，"
      + "本地归档不会改变独立验证与外部认证状态。",
  };
}

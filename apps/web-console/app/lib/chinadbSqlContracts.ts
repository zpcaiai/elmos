export const chinaDbSqlRequestLimitBytes = 1_310_720;
export const chinaDbSqlInputLimitBytes = 256 * 1024;
export const chinaDbSqlParameterLimit = 256;
export const chinaDbSqlStatementLimit = 256;
export const chinaDbSqlResponseLimitBytes = 4 * 1024 * 1024;

export const chinaDbSqlTargetIds = [
  "dm8",
  "kingbasees",
  "opengauss",
  "tidb",
  "gbase-8s",
  "gbase-8c",
  "gbase-8a",
  "highgo-hgdb",
  "oceanbase-oracle",
  "oceanbase-mysql",
  "gaussdb-oracle",
  "gaussdb-m",
  "goldendb",
] as const;

export const chinaDbSqlSourceProfiles = [
  "postgresql-17.5",
  "postgresql-18.4",
  "mysql-8.4.10-lts",
  "sqlserver-2022-cu26",
  "oracle-26ai-ee",
  "sqlite-3.53.3",
  "duckdb-1.5.4",
] as const;

export type ChinaDbSqlTargetId = (typeof chinaDbSqlTargetIds)[number];
export type ChinaDbSqlSourceProfile = (typeof chinaDbSqlSourceProfiles)[number];

type CommercialState = "SPEC_ONLY";
type ExecutionState = "NOT_RUN";
type CertificationState = "NOT_CERTIFIED";

export type ChinaDbSqlTarget = {
  id: ChinaDbSqlTargetId;
  label: string;
  adapterId: string;
  versionRequirement: string;
  compatibilityModeRequirement: string;
  implementationStatus: CommercialState;
  externalExecution: ExecutionState;
  certification: CertificationState;
};

export type ChinaDbSqlRoute = {
  id: string;
  sourceFamily: string;
  targetId: ChinaDbSqlTargetId;
  priority: "T1" | "T2" | "ANALYTICAL";
  state: CommercialState;
  externalExecution: ExecutionState;
  certification: CertificationState;
};

export type ChinaDbSqlCapabilities = {
  schemaVersion: "1.0";
  package: "chinadb-commercial-migration-skills";
  version: "1.0.0";
  targets: ChinaDbSqlTarget[];
  plannedRoutes: ChinaDbSqlRoute[];
  excludedTargets: Array<{ id: string; label: string; reason: string }>;
  implementationStatus: CommercialState;
  externalExecution: ExecutionState;
  certification: CertificationState;
  capabilitySnapshotDigest: string;
  targetCount: 13;
  plannedRouteCount: 78;
  boundaries: {
    exactCommercialTargetProfilesRegistered: false;
    verifiedTargetRenderers: 0;
    productionDatabaseAccess: false;
    targetSqlMayBeEmitted: false;
    claim: string;
  };
};

export type ChinaDbSqlParameter = {
  name: string;
  logicalType: string;
  nullable: boolean;
};

export type ChinaDbSqlPreflightRequest = {
  schemaVersion: "1.0";
  queryId: string;
  sourceProfile: ChinaDbSqlSourceProfile;
  targetId: ChinaDbSqlTargetId;
  targetVersion: string;
  targetEdition: string;
  compatibilityMode: string;
  targetDriver: string;
  targetCharset: string;
  targetCollation: string;
  targetTimeZone: string;
  capabilitySnapshotDigest: string;
  sql: string;
  parameters: ChinaDbSqlParameter[];
};

export type ChinaDbSqlStatement = {
  index: number;
  kind: string;
  sourceAst: Record<string, unknown> | unknown[];
  obligations: string[];
};

export type ChinaDbSqlBlocker = {
  code: string;
  severity: "ERROR" | "WARNING";
  statementIndex: number | null;
  message: string;
};

export type ChinaDbSqlVerification = {
  sourceParse: "PASSED" | "FAILED";
  targetAdapter: ExecutionState;
  targetEmit: ExecutionState;
  targetReparse: ExecutionState;
  sourceExecution: ExecutionState;
  targetExecution: ExecutionState;
  resultEquivalence: ExecutionState;
  externalExecution: ExecutionState;
};

export type ChinaDbSqlPreflightResult = {
  schemaVersion: "1.0";
  queryId: string;
  sourceProfile: ChinaDbSqlSourceProfile;
  target: {
    id: ChinaDbSqlTargetId;
    label: string;
    version: string;
    edition: string;
    compatibilityMode: string;
    driver: string;
    charset: string;
    collation: string;
    timeZone: string;
    adapterId: string;
    implementationStatus: CommercialState;
  };
  routeId: string;
  state: "BLOCKED";
  sourceDigest: string;
  capabilitySnapshotDigest: string;
  statements: ChinaDbSqlStatement[];
  blockers: ChinaDbSqlBlocker[];
  targetSql: null;
  verification: ChinaDbSqlVerification;
  certification: CertificationState;
};

export class ChinaDbSqlPolicyError extends Error {
  readonly status: number;
  readonly errorCode: string;

  constructor(
    status: number,
    errorCode: string,
    message = errorCode,
  ) {
    super(message);
    this.name = "ChinaDbSqlPolicyError";
    this.status = status;
    this.errorCode = errorCode;
  }
}

const targetIdSet = new Set<string>(chinaDbSqlTargetIds);
const sourceProfileSet = new Set<string>(chinaDbSqlSourceProfiles);
const digestPattern = /^sha256:[0-9a-f]{64}$/;
const queryIdPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/;
const exactVersionPattern = /^[A-Za-z0-9][A-Za-z0-9._+~-]*$/;
const exactContextPattern = /^[A-Za-z0-9][A-Za-z0-9._+:/~-]*$/;
const codePattern = /^[A-Z][A-Z0-9_]*$/;
const statementKindPattern = /^[A-Z][A-Z0-9_]*$/;
const sourceFamilies = [
  ["Oracle", "oracle"],
  ["SQL Server", "sql-server"],
  ["PostgreSQL", "postgresql"],
  ["MySQL/MariaDB", "mysql-mariadb"],
  ["DB2 LUW", "db2-luw"],
  ["Sybase ASE", "sybase-ase"],
] as const;
const excludedTargetIds = ["polardb", "polardb-x", "tdsql"] as const;
const routeSlugBySourceProfile: Record<ChinaDbSqlSourceProfile, string> = {
  "postgresql-17.5": "postgresql",
  "postgresql-18.4": "postgresql",
  "mysql-8.4.10-lts": "mysql-mariadb",
  "sqlserver-2022-cu26": "sql-server",
  "oracle-26ai-ee": "oracle",
  "sqlite-3.53.3": "sqlite-3-53-3",
  "duckdb-1.5.4": "duckdb-1-5-4",
};

function fail(status: number, code: string, message = code): never {
  throw new ChinaDbSqlPolicyError(status, code, message);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function record(value: unknown, code: string, status = 502): Record<string, unknown> {
  if (!isRecord(value)) fail(status, code);
  return value;
}

function exactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
  code: string,
  status = 502,
): void {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    fail(status, code);
  }
}

function boundedText(
  value: unknown,
  maximum: number,
  code: string,
  status = 502,
): string {
  if (
    typeof value !== "string"
    || value.length < 1
    || value.length > maximum
    || value.trim() !== value
    || /[\0\r\n]/.test(value)
    || hasUnpairedSurrogate(value)
  ) {
    fail(status, code);
  }
  return value;
}

function hasUnpairedSurrogate(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return true;
      index += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      return true;
    }
  }
  return false;
}

function digest(value: unknown, code: string, status = 502): string {
  if (typeof value !== "string" || !digestPattern.test(value)) fail(status, code);
  return value;
}

function targetId(value: unknown, code: string, status = 502): ChinaDbSqlTargetId {
  if (typeof value !== "string" || !targetIdSet.has(value)) fail(status, code);
  return value as ChinaDbSqlTargetId;
}

function sourceProfile(value: unknown, status = 400): ChinaDbSqlSourceProfile {
  if (typeof value !== "string" || !sourceProfileSet.has(value)) {
    fail(status, "CHINADB_SQL_SOURCE_PROFILE_INVALID");
  }
  return value as ChinaDbSqlSourceProfile;
}

function isFloating(value: string): boolean {
  const normalized = value.toLocaleLowerCase("en-US");
  return ["latest", "current", "unknown", "unspecified", "*", "x"].includes(normalized)
    || normalized.endsWith(".*")
    || normalized.endsWith(".x");
}

function exactToken(
  value: unknown,
  pattern: RegExp,
  code: string,
  status = 400,
): string {
  const token = boundedText(value, 128, code, status);
  if (isFloating(token) || !pattern.test(token)) fail(status, code);
  return token;
}

function exactLiteral<T extends string | number | boolean | null>(
  value: unknown,
  expected: T,
  code: string,
  status = 502,
): T {
  if (value !== expected) fail(status, code);
  return expected;
}

export function parseChinaDbSqlCapabilities(value: unknown): ChinaDbSqlCapabilities {
  const root = record(value, "CHINADB_SQL_CAPABILITIES_INVALID");
  exactKeys(root, [
    "schemaVersion",
    "package",
    "version",
    "targets",
    "plannedRoutes",
    "excludedTargets",
    "implementationStatus",
    "externalExecution",
    "certification",
    "capabilitySnapshotDigest",
    "targetCount",
    "plannedRouteCount",
    "boundaries",
  ], "CHINADB_SQL_CAPABILITIES_FIELDS_INVALID");
  exactLiteral(root.schemaVersion, "1.0", "CHINADB_SQL_CAPABILITIES_IDENTITY_INVALID");
  exactLiteral(root.package, "chinadb-commercial-migration-skills", "CHINADB_SQL_CAPABILITIES_IDENTITY_INVALID");
  exactLiteral(root.version, "1.0.0", "CHINADB_SQL_CAPABILITIES_IDENTITY_INVALID");
  exactLiteral(root.implementationStatus, "SPEC_ONLY", "CHINADB_SQL_CAPABILITIES_STATE_INVALID");
  exactLiteral(root.externalExecution, "NOT_RUN", "CHINADB_SQL_CAPABILITIES_STATE_INVALID");
  exactLiteral(root.certification, "NOT_CERTIFIED", "CHINADB_SQL_CAPABILITIES_STATE_INVALID");
  exactLiteral(root.targetCount, 13, "CHINADB_SQL_TARGET_COUNT_INVALID");
  exactLiteral(root.plannedRouteCount, 78, "CHINADB_SQL_ROUTE_COUNT_INVALID");

  if (!Array.isArray(root.targets) || root.targets.length !== 13) {
    fail(502, "CHINADB_SQL_TARGET_COUNT_INVALID");
  }
  const targets = root.targets.map((entry, index): ChinaDbSqlTarget => {
    const item = record(entry, "CHINADB_SQL_TARGET_INVALID");
    exactKeys(item, [
      "id",
      "label",
      "adapterId",
      "versionRequirement",
      "compatibilityModeRequirement",
      "implementationStatus",
      "externalExecution",
      "certification",
    ], "CHINADB_SQL_TARGET_FIELDS_INVALID");
    const id = targetId(item.id, "CHINADB_SQL_TARGET_ID_INVALID");
    const adapterId = boundedText(item.adapterId, 160, "CHINADB_SQL_TARGET_ADAPTER_INVALID");
    if (adapterId !== `chinadb.${id}.target-adapter.v1`) {
      fail(502, "CHINADB_SQL_TARGET_ADAPTER_INVALID");
    }
    return {
      id,
      label: boundedText(item.label, 128, `CHINADB_SQL_TARGET_${index}_LABEL_INVALID`),
      adapterId,
      versionRequirement: boundedText(item.versionRequirement, 256, "CHINADB_SQL_TARGET_REQUIREMENT_INVALID"),
      compatibilityModeRequirement: boundedText(item.compatibilityModeRequirement, 256, "CHINADB_SQL_TARGET_REQUIREMENT_INVALID"),
      implementationStatus: exactLiteral(item.implementationStatus, "SPEC_ONLY", "CHINADB_SQL_TARGET_STATE_INVALID"),
      externalExecution: exactLiteral(item.externalExecution, "NOT_RUN", "CHINADB_SQL_TARGET_STATE_INVALID"),
      certification: exactLiteral(item.certification, "NOT_CERTIFIED", "CHINADB_SQL_TARGET_STATE_INVALID"),
    };
  });
  const observedTargetIds = new Set(targets.map((target) => target.id));
  if (observedTargetIds.size !== 13 || chinaDbSqlTargetIds.some((id) => !observedTargetIds.has(id))) {
    fail(502, "CHINADB_SQL_TARGET_SET_INVALID");
  }

  if (!Array.isArray(root.plannedRoutes) || root.plannedRoutes.length !== 78) {
    fail(502, "CHINADB_SQL_ROUTE_COUNT_INVALID");
  }
  const plannedRoutes = root.plannedRoutes.map((entry): ChinaDbSqlRoute => {
    const item = record(entry, "CHINADB_SQL_ROUTE_INVALID");
    exactKeys(item, [
      "id",
      "sourceFamily",
      "targetId",
      "priority",
      "state",
      "externalExecution",
      "certification",
    ], "CHINADB_SQL_ROUTE_FIELDS_INVALID");
    const routeTargetId = targetId(item.targetId, "CHINADB_SQL_ROUTE_TARGET_INVALID");
    const sourceFamily = boundedText(item.sourceFamily, 128, "CHINADB_SQL_ROUTE_SOURCE_INVALID");
    const source = sourceFamilies.find(([family]) => family === sourceFamily);
    const id = boundedText(item.id, 160, "CHINADB_SQL_ROUTE_ID_INVALID");
    if (!source || id !== `${source[1]}--to--${routeTargetId}`) {
      fail(502, "CHINADB_SQL_ROUTE_ID_INVALID");
    }
    if (!(["T1", "T2", "ANALYTICAL"] as const).includes(item.priority as "T1" | "T2" | "ANALYTICAL")) {
      fail(502, "CHINADB_SQL_ROUTE_PRIORITY_INVALID");
    }
    return {
      id,
      sourceFamily,
      targetId: routeTargetId,
      priority: item.priority as ChinaDbSqlRoute["priority"],
      state: exactLiteral(item.state, "SPEC_ONLY", "CHINADB_SQL_ROUTE_STATE_INVALID"),
      externalExecution: exactLiteral(item.externalExecution, "NOT_RUN", "CHINADB_SQL_ROUTE_STATE_INVALID"),
      certification: exactLiteral(item.certification, "NOT_CERTIFIED", "CHINADB_SQL_ROUTE_STATE_INVALID"),
    };
  });
  const expectedRoutes = new Set(
    sourceFamilies.flatMap(([, slug]) => chinaDbSqlTargetIds.map((id) => `${slug}--to--${id}`)),
  );
  const observedRoutes = new Set(plannedRoutes.map((route) => route.id));
  if (observedRoutes.size !== 78 || [...expectedRoutes].some((id) => !observedRoutes.has(id))) {
    fail(502, "CHINADB_SQL_ROUTE_MATRIX_INVALID");
  }

  if (!Array.isArray(root.excludedTargets) || root.excludedTargets.length !== 3) {
    fail(502, "CHINADB_SQL_EXCLUSION_INVALID");
  }
  const excludedTargets = root.excludedTargets.map((entry, index) => {
    const item = record(entry, "CHINADB_SQL_EXCLUSION_INVALID");
    exactKeys(item, ["id", "label", "reason"], "CHINADB_SQL_EXCLUSION_FIELDS_INVALID");
    const id = boundedText(item.id, 64, "CHINADB_SQL_EXCLUSION_INVALID");
    if (id !== excludedTargetIds[index] || observedTargetIds.has(id as ChinaDbSqlTargetId)) {
      fail(502, "CHINADB_SQL_EXCLUSION_INVALID");
    }
    return {
      id,
      label: boundedText(item.label, 128, "CHINADB_SQL_EXCLUSION_INVALID"),
      reason: boundedText(item.reason, 512, "CHINADB_SQL_EXCLUSION_INVALID"),
    };
  });

  const boundaries = record(root.boundaries, "CHINADB_SQL_BOUNDARIES_INVALID");
  exactKeys(boundaries, [
    "exactCommercialTargetProfilesRegistered",
    "verifiedTargetRenderers",
    "productionDatabaseAccess",
    "targetSqlMayBeEmitted",
    "claim",
  ], "CHINADB_SQL_BOUNDARIES_FIELDS_INVALID");

  return {
    schemaVersion: "1.0",
    package: "chinadb-commercial-migration-skills",
    version: "1.0.0",
    targets,
    plannedRoutes,
    excludedTargets,
    implementationStatus: "SPEC_ONLY",
    externalExecution: "NOT_RUN",
    certification: "NOT_CERTIFIED",
    capabilitySnapshotDigest: digest(root.capabilitySnapshotDigest, "CHINADB_SQL_CAPABILITY_DIGEST_INVALID"),
    targetCount: 13,
    plannedRouteCount: 78,
    boundaries: {
      exactCommercialTargetProfilesRegistered: exactLiteral(boundaries.exactCommercialTargetProfilesRegistered, false, "CHINADB_SQL_BOUNDARIES_INVALID"),
      verifiedTargetRenderers: exactLiteral(boundaries.verifiedTargetRenderers, 0, "CHINADB_SQL_BOUNDARIES_INVALID"),
      productionDatabaseAccess: exactLiteral(boundaries.productionDatabaseAccess, false, "CHINADB_SQL_BOUNDARIES_INVALID"),
      targetSqlMayBeEmitted: exactLiteral(boundaries.targetSqlMayBeEmitted, false, "CHINADB_SQL_BOUNDARIES_INVALID"),
      claim: boundedText(boundaries.claim, 1024, "CHINADB_SQL_BOUNDARIES_INVALID"),
    },
  };
}

export function parseChinaDbSqlPreflightRequest(value: unknown): ChinaDbSqlPreflightRequest {
  const root = record(value, "CHINADB_SQL_REQUEST_INVALID", 400);
  exactKeys(root, [
    "schemaVersion",
    "queryId",
    "sourceProfile",
    "targetId",
    "targetVersion",
    "targetEdition",
    "compatibilityMode",
    "targetDriver",
    "targetCharset",
    "targetCollation",
    "targetTimeZone",
    "capabilitySnapshotDigest",
    "sql",
    "parameters",
  ], "CHINADB_SQL_REQUEST_FIELDS_INVALID", 400);
  exactLiteral(root.schemaVersion, "1.0", "CHINADB_SQL_REQUEST_SCHEMA_INVALID", 400);
  if (typeof root.queryId !== "string" || !queryIdPattern.test(root.queryId)) {
    fail(400, "CHINADB_SQL_QUERY_ID_INVALID");
  }
  const parsedSourceProfile = sourceProfile(root.sourceProfile);
  const parsedTargetId = targetId(root.targetId, "CHINADB_SQL_TARGET_ID_INVALID", 400);
  if (
    typeof root.sql !== "string"
    || !root.sql.trim()
    || root.sql.includes("\0")
    || hasUnpairedSurrogate(root.sql)
  ) {
    fail(400, "CHINADB_SQL_INPUT_INVALID");
  }
  if (new TextEncoder().encode(root.sql).byteLength > chinaDbSqlInputLimitBytes) {
    fail(413, "CHINADB_SQL_INPUT_TOO_LARGE");
  }
  if (!Array.isArray(root.parameters) || root.parameters.length > chinaDbSqlParameterLimit) {
    fail(root.parameters instanceof Array ? 413 : 400, "CHINADB_SQL_PARAMETERS_INVALID");
  }
  const parameters = root.parameters.map((entry): ChinaDbSqlParameter => {
    const item = record(entry, "CHINADB_SQL_PARAMETER_INVALID", 400);
    exactKeys(item, ["name", "logicalType", "nullable"], "CHINADB_SQL_PARAMETER_FIELDS_INVALID", 400);
    if (typeof item.nullable !== "boolean") fail(400, "CHINADB_SQL_PARAMETER_NULLABILITY_INVALID");
    return {
      name: boundedText(item.name, 128, "CHINADB_SQL_PARAMETER_NAME_INVALID", 400),
      logicalType: boundedText(item.logicalType, 128, "CHINADB_SQL_PARAMETER_TYPE_INVALID", 400),
      nullable: item.nullable,
    };
  });
  if (new Set(parameters.map((parameter) => parameter.name)).size !== parameters.length) {
    fail(400, "CHINADB_SQL_PARAMETER_DUPLICATE");
  }
  return {
    schemaVersion: "1.0",
    queryId: root.queryId,
    sourceProfile: parsedSourceProfile,
    targetId: parsedTargetId,
    targetVersion: exactToken(root.targetVersion, exactVersionPattern, "CHINADB_SQL_TARGET_VERSION_INVALID"),
    targetEdition: exactToken(root.targetEdition, exactContextPattern, "CHINADB_SQL_TARGET_EDITION_INVALID"),
    compatibilityMode: exactToken(root.compatibilityMode, exactContextPattern, "CHINADB_SQL_COMPATIBILITY_MODE_INVALID"),
    targetDriver: exactToken(root.targetDriver, exactContextPattern, "CHINADB_SQL_TARGET_DRIVER_INVALID"),
    targetCharset: exactToken(root.targetCharset, exactContextPattern, "CHINADB_SQL_TARGET_CHARSET_INVALID"),
    targetCollation: exactToken(root.targetCollation, exactContextPattern, "CHINADB_SQL_TARGET_COLLATION_INVALID"),
    targetTimeZone: exactToken(root.targetTimeZone, exactContextPattern, "CHINADB_SQL_TARGET_TIMEZONE_INVALID"),
    capabilitySnapshotDigest: digest(root.capabilitySnapshotDigest, "CHINADB_SQL_CAPABILITY_DIGEST_INVALID", 400),
    sql: root.sql,
    parameters,
  };
}

export function bindChinaDbSqlRequestToCapabilities(
  request: ChinaDbSqlPreflightRequest,
  capabilities: ChinaDbSqlCapabilities,
): ChinaDbSqlTarget {
  if (request.capabilitySnapshotDigest !== capabilities.capabilitySnapshotDigest) {
    fail(409, "CHINADB_SQL_CAPABILITY_SNAPSHOT_STALE");
  }
  const target = capabilities.targets.find((candidate) => candidate.id === request.targetId);
  if (!target) fail(409, "CHINADB_SQL_TARGET_NOT_IN_SNAPSHOT");
  return target;
}

export function expectedChinaDbSqlRouteId(request: ChinaDbSqlPreflightRequest): string {
  return `${routeSlugBySourceProfile[request.sourceProfile]}--to--${request.targetId}`;
}

function assertAstBudget(root: unknown): void {
  const stack: Array<{ value: unknown; depth: number }> = [{ value: root, depth: 0 }];
  const encoder = new TextEncoder();
  let nodes = 0;
  let textBytes = 0;
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current) break;
    nodes += 1;
    if (nodes > 50_000 || current.depth > 64) {
      fail(502, "CHINADB_SQL_RESPONSE_AST_BUDGET_EXCEEDED");
    }
    if (typeof current.value === "string") {
      if (hasUnpairedSurrogate(current.value)) {
        fail(502, "CHINADB_SQL_RESPONSE_AST_INVALID");
      }
      textBytes += encoder.encode(current.value).byteLength;
    } else if (Array.isArray(current.value)) {
      current.value.forEach((value) => stack.push({ value, depth: current.depth + 1 }));
    } else if (isRecord(current.value)) {
      for (const [key, value] of Object.entries(current.value)) {
        if (["__proto__", "prototype", "constructor"].includes(key)) {
          fail(502, "CHINADB_SQL_RESPONSE_AST_INVALID");
        }
        textBytes += encoder.encode(key).byteLength;
        stack.push({ value, depth: current.depth + 1 });
      }
    }
    if (textBytes > 2 * 1024 * 1024) {
      fail(502, "CHINADB_SQL_RESPONSE_AST_BUDGET_EXCEEDED");
    }
  }
}

export function parseChinaDbSqlPreflightResult(
  value: unknown,
  request: ChinaDbSqlPreflightRequest,
  capabilities: ChinaDbSqlCapabilities,
  expectedSourceDigest: string,
): ChinaDbSqlPreflightResult {
  const root = record(value, "CHINADB_SQL_RESPONSE_INVALID");
  exactKeys(root, [
    "schemaVersion",
    "queryId",
    "sourceProfile",
    "target",
    "routeId",
    "state",
    "sourceDigest",
    "capabilitySnapshotDigest",
    "statements",
    "blockers",
    "targetSql",
    "verification",
    "certification",
  ], "CHINADB_SQL_RESPONSE_FIELDS_INVALID");
  exactLiteral(root.schemaVersion, "1.0", "CHINADB_SQL_RESPONSE_SCHEMA_INVALID");
  exactLiteral(root.queryId, request.queryId, "CHINADB_SQL_RESPONSE_QUERY_MISMATCH");
  exactLiteral(root.sourceProfile, request.sourceProfile, "CHINADB_SQL_RESPONSE_SOURCE_MISMATCH");
  exactLiteral(root.routeId, expectedChinaDbSqlRouteId(request), "CHINADB_SQL_RESPONSE_ROUTE_MISMATCH");
  exactLiteral(root.state, "BLOCKED", "CHINADB_SQL_RESPONSE_NOT_BLOCKED");
  exactLiteral(root.targetSql, null, "CHINADB_SQL_RESPONSE_TARGET_SQL_PROHIBITED");
  exactLiteral(root.capabilitySnapshotDigest, request.capabilitySnapshotDigest, "CHINADB_SQL_RESPONSE_DIGEST_MISMATCH");
  exactLiteral(root.sourceDigest, expectedSourceDigest, "CHINADB_SQL_RESPONSE_SOURCE_DIGEST_MISMATCH");
  exactLiteral(root.certification, "NOT_CERTIFIED", "CHINADB_SQL_RESPONSE_CERTIFICATION_INVALID");

  const snapshotTarget = bindChinaDbSqlRequestToCapabilities(request, capabilities);
  const target = record(root.target, "CHINADB_SQL_RESPONSE_TARGET_INVALID");
  exactKeys(target, [
    "id",
    "label",
    "version",
    "edition",
    "compatibilityMode",
    "driver",
    "charset",
    "collation",
    "timeZone",
    "adapterId",
    "implementationStatus",
  ], "CHINADB_SQL_RESPONSE_TARGET_FIELDS_INVALID");
  exactLiteral(target.id, request.targetId, "CHINADB_SQL_RESPONSE_TARGET_MISMATCH");
  exactLiteral(target.label, snapshotTarget.label, "CHINADB_SQL_RESPONSE_TARGET_MISMATCH");
  exactLiteral(target.version, request.targetVersion, "CHINADB_SQL_RESPONSE_TARGET_MISMATCH");
  exactLiteral(target.edition, request.targetEdition, "CHINADB_SQL_RESPONSE_TARGET_MISMATCH");
  exactLiteral(target.compatibilityMode, request.compatibilityMode, "CHINADB_SQL_RESPONSE_TARGET_MISMATCH");
  exactLiteral(target.driver, request.targetDriver, "CHINADB_SQL_RESPONSE_TARGET_MISMATCH");
  exactLiteral(target.charset, request.targetCharset, "CHINADB_SQL_RESPONSE_TARGET_MISMATCH");
  exactLiteral(target.collation, request.targetCollation, "CHINADB_SQL_RESPONSE_TARGET_MISMATCH");
  exactLiteral(target.timeZone, request.targetTimeZone, "CHINADB_SQL_RESPONSE_TARGET_MISMATCH");
  exactLiteral(target.adapterId, snapshotTarget.adapterId, "CHINADB_SQL_RESPONSE_ADAPTER_MISMATCH");
  exactLiteral(target.implementationStatus, "SPEC_ONLY", "CHINADB_SQL_RESPONSE_TARGET_STATE_INVALID");

  if (!Array.isArray(root.statements) || root.statements.length > chinaDbSqlStatementLimit) {
    fail(502, "CHINADB_SQL_RESPONSE_STATEMENTS_INVALID");
  }
  const statements = root.statements.map((entry, index): ChinaDbSqlStatement => {
    const item = record(entry, "CHINADB_SQL_RESPONSE_STATEMENT_INVALID");
    exactKeys(item, ["index", "kind", "sourceAst", "obligations"], "CHINADB_SQL_RESPONSE_STATEMENT_FIELDS_INVALID");
    if (item.index !== index) fail(502, "CHINADB_SQL_RESPONSE_STATEMENT_INDEX_INVALID");
    if (typeof item.kind !== "string" || item.kind.length > 128 || !statementKindPattern.test(item.kind)) {
      fail(502, "CHINADB_SQL_RESPONSE_STATEMENT_KIND_INVALID");
    }
    const validAst = (isRecord(item.sourceAst) && Object.keys(item.sourceAst).length > 0)
      || (Array.isArray(item.sourceAst) && item.sourceAst.length > 0);
    if (!validAst) fail(502, "CHINADB_SQL_RESPONSE_AST_INVALID");
    assertAstBudget(item.sourceAst);
    if (
      !Array.isArray(item.obligations)
      || item.obligations.length < 1
      || item.obligations.length > 256
    ) {
      fail(502, "CHINADB_SQL_RESPONSE_OBLIGATIONS_INVALID");
    }
    const obligations = item.obligations.map((obligation) => (
      boundedText(obligation, 256, "CHINADB_SQL_RESPONSE_OBLIGATION_INVALID")
    ));
    if (new Set(obligations).size !== obligations.length) {
      fail(502, "CHINADB_SQL_RESPONSE_OBLIGATIONS_INVALID");
    }
    return {
      index,
      kind: item.kind,
      sourceAst: item.sourceAst as Record<string, unknown> | unknown[],
      obligations,
    };
  });

  if (!Array.isArray(root.blockers) || root.blockers.length < 1 || root.blockers.length > 4096) {
    fail(502, "CHINADB_SQL_RESPONSE_BLOCKERS_INVALID");
  }
  const blockers = root.blockers.map((entry): ChinaDbSqlBlocker => {
    const item = record(entry, "CHINADB_SQL_RESPONSE_BLOCKER_INVALID");
    exactKeys(item, ["code", "severity", "statementIndex", "message"], "CHINADB_SQL_RESPONSE_BLOCKER_FIELDS_INVALID");
    if (typeof item.code !== "string" || item.code.length > 128 || !codePattern.test(item.code)) {
      fail(502, "CHINADB_SQL_RESPONSE_BLOCKER_CODE_INVALID");
    }
    if (item.severity !== "ERROR" && item.severity !== "WARNING") {
      fail(502, "CHINADB_SQL_RESPONSE_BLOCKER_SEVERITY_INVALID");
    }
    if (
      item.statementIndex !== null
      && (!Number.isInteger(item.statementIndex)
        || Number(item.statementIndex) < 0
        || Number(item.statementIndex) >= statements.length)
    ) {
      fail(502, "CHINADB_SQL_RESPONSE_BLOCKER_INDEX_INVALID");
    }
    return {
      code: item.code,
      severity: item.severity,
      statementIndex: item.statementIndex as number | null,
      message: boundedText(item.message, 2048, "CHINADB_SQL_RESPONSE_BLOCKER_MESSAGE_INVALID"),
    };
  });
  if (!blockers.some((blocker) => blocker.severity === "ERROR")) {
    fail(502, "CHINADB_SQL_RESPONSE_ERROR_BLOCKER_REQUIRED");
  }

  const verification = record(root.verification, "CHINADB_SQL_RESPONSE_VERIFICATION_INVALID");
  exactKeys(verification, [
    "sourceParse",
    "targetAdapter",
    "targetEmit",
    "targetReparse",
    "sourceExecution",
    "targetExecution",
    "resultEquivalence",
    "externalExecution",
  ], "CHINADB_SQL_RESPONSE_VERIFICATION_FIELDS_INVALID");
  if (verification.sourceParse !== "PASSED" && verification.sourceParse !== "FAILED") {
    fail(502, "CHINADB_SQL_RESPONSE_SOURCE_PARSE_INVALID");
  }
  for (const field of [
    "targetAdapter",
    "targetEmit",
    "targetReparse",
    "sourceExecution",
    "targetExecution",
    "resultEquivalence",
    "externalExecution",
  ] as const) {
    exactLiteral(verification[field], "NOT_RUN", "CHINADB_SQL_RESPONSE_FALSE_EVIDENCE");
  }
  if (
    (verification.sourceParse === "PASSED" && statements.length < 1)
    || (verification.sourceParse === "FAILED" && statements.length !== 0)
  ) {
    fail(502, "CHINADB_SQL_RESPONSE_PARSE_STATEMENT_MISMATCH");
  }

  return {
    schemaVersion: "1.0",
    queryId: request.queryId,
    sourceProfile: request.sourceProfile,
    target: {
      id: request.targetId,
      label: snapshotTarget.label,
      version: request.targetVersion,
      edition: request.targetEdition,
      compatibilityMode: request.compatibilityMode,
      driver: request.targetDriver,
      charset: request.targetCharset,
      collation: request.targetCollation,
      timeZone: request.targetTimeZone,
      adapterId: snapshotTarget.adapterId,
      implementationStatus: "SPEC_ONLY",
    },
    routeId: expectedChinaDbSqlRouteId(request),
    state: "BLOCKED",
    sourceDigest: expectedSourceDigest,
    capabilitySnapshotDigest: request.capabilitySnapshotDigest,
    statements,
    blockers,
    targetSql: null,
    verification: {
      sourceParse: verification.sourceParse,
      targetAdapter: "NOT_RUN",
      targetEmit: "NOT_RUN",
      targetReparse: "NOT_RUN",
      sourceExecution: "NOT_RUN",
      targetExecution: "NOT_RUN",
      resultEquivalence: "NOT_RUN",
      externalExecution: "NOT_RUN",
    },
    certification: "NOT_CERTIFIED",
  };
}

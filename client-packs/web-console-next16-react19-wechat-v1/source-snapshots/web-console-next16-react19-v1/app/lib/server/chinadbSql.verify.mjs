import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

import {
  bindChinaDbSqlRequestToCapabilities,
  ChinaDbSqlPolicyError,
  expectedChinaDbSqlRouteId,
  parseChinaDbSqlCapabilities,
  parseChinaDbSqlPreflightRequest,
  parseChinaDbSqlPreflightResult,
} from "../chinadbSqlContracts.ts";
import { parseStrictJson, StrictJsonError } from "./strictJson.ts";

let checks = 0;
const catalogUrl = new URL(
  "../../../../../engines/database-data-engine/sql-transpiler/src/elmos_sql_transpiler/data/chinadb-commercial-v1.json",
  import.meta.url,
);
const catalogText = readFileSync(catalogUrl, "utf8");
const catalog = JSON.parse(catalogText);
const snapshot = `sha256:${createHash("sha256").update(catalogText, "utf8").digest("hex")}`;
const capabilities = parseChinaDbSqlCapabilities({
  ...catalog,
  capabilitySnapshotDigest: snapshot,
  targetCount: 13,
  plannedRouteCount: 78,
  boundaries: {
    exactCommercialTargetProfilesRegistered: false,
    verifiedTargetRenderers: 0,
    productionDatabaseAccess: false,
    targetSqlMayBeEmitted: false,
    claim: "Static commercial planning registry and source-side typed preflight only.",
  },
});
assert.equal(capabilities.targets.length, 13);
assert.equal(capabilities.plannedRoutes.length, 78);
checks += 2;

assert.deepEqual(parseStrictJson('{"a":[1,true,null,{"b":"c"}]}'), {
  a: [1, true, null, { b: "c" }],
});
assert.throws(
  () => parseStrictJson('{"a":1,"a":2}'),
  (error) => error instanceof StrictJsonError && error.code === "DUPLICATE_JSON_FIELD",
);
assert.throws(() => parseStrictJson("{} []"), StrictJsonError);
checks += 3;

const request = parseChinaDbSqlPreflightRequest({
  schemaVersion: "1.0",
  queryId: "web-policy-1",
  sourceProfile: "postgresql-17.5",
  targetId: "dm8",
  targetVersion: "8.1.3.140",
  targetEdition: "enterprise",
  compatibilityMode: "oracle-compatible-explicit",
  targetDriver: "dmjdbc-8.1.3.140",
  targetCharset: "UTF-8",
  targetCollation: "BINARY",
  targetTimeZone: "Asia/Shanghai",
  capabilitySnapshotDigest: snapshot,
  sql: "SELECT 1\nFROM t",
  parameters: [],
});
assert.equal(bindChinaDbSqlRequestToCapabilities(request, capabilities).id, "dm8");
assert.equal(expectedChinaDbSqlRouteId(request), "postgresql--to--dm8");
assert.throws(
  () => parseChinaDbSqlPreflightRequest({ ...request, sql: `SELECT ${String.fromCharCode(0xd800)}` }),
  ChinaDbSqlPolicyError,
);
assert.throws(
  () => bindChinaDbSqlRequestToCapabilities(
    { ...request, capabilitySnapshotDigest: `sha256:${"0".repeat(64)}` },
    capabilities,
  ),
  (error) => error instanceof ChinaDbSqlPolicyError && error.status === 409,
);
checks += 4;

const sourceDigest = `sha256:${createHash("sha256").update(request.sql, "utf8").digest("hex")}`;
const result = {
  schemaVersion: "1.0",
  queryId: request.queryId,
  sourceProfile: request.sourceProfile,
  target: {
    id: "dm8",
    label: capabilities.targets.find((target) => target.id === "dm8").label,
    version: request.targetVersion,
    edition: request.targetEdition,
    compatibilityMode: request.compatibilityMode,
    driver: request.targetDriver,
    charset: request.targetCharset,
    collation: request.targetCollation,
    timeZone: request.targetTimeZone,
    adapterId: "chinadb.dm8.target-adapter.v1",
    implementationStatus: "SPEC_ONLY",
  },
  routeId: "postgresql--to--dm8",
  state: "BLOCKED",
  sourceDigest,
  capabilitySnapshotDigest: snapshot,
  statements: [{
    index: 0,
    kind: "SELECT",
    sourceAst: { type: "Select", expressions: [{ type: "Literal", value: "1" }] },
    obligations: ["TARGET_ADAPTER_REQUIRED"],
  }],
  blockers: [{
    code: "TARGET_ADAPTER_NOT_IMPLEMENTED",
    severity: "ERROR",
    statementIndex: null,
    message: "Target rendering is unavailable.",
  }],
  targetSql: null,
  verification: {
    sourceParse: "PASSED",
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
const accepted = parseChinaDbSqlPreflightResult(result, request, capabilities, sourceDigest);
assert.equal(accepted.state, "BLOCKED");
assert.equal(accepted.targetSql, null);
assert.equal(accepted.certification, "NOT_CERTIFIED");
assert.ok(Object.values(accepted.verification).slice(1).every((state) => state === "NOT_RUN"));
checks += 4;

assert.throws(
  () => parseChinaDbSqlPreflightResult({ ...result, targetSql: "SELECT 1" }, request, capabilities, sourceDigest),
  ChinaDbSqlPolicyError,
);
assert.throws(
  () => parseChinaDbSqlPreflightResult({
    ...result,
    blockers: [{ ...result.blockers[0], severity: "WARNING" }],
  }, request, capabilities, sourceDigest),
  ChinaDbSqlPolicyError,
);
let deepAst = { value: "leaf" };
for (let depth = 0; depth < 66; depth += 1) deepAst = { child: deepAst };
assert.throws(
  () => parseChinaDbSqlPreflightResult({
    ...result,
    statements: [{ ...result.statements[0], sourceAst: deepAst }],
  }, request, capabilities, sourceDigest),
  ChinaDbSqlPolicyError,
);
checks += 3;

const parseOnly = parseChinaDbSqlPreflightRequest({ ...request, sourceProfile: "sqlite-3.53.3" });
assert.equal(expectedChinaDbSqlRouteId(parseOnly), "sqlite-3-53-3--to--dm8");
checks += 1;

console.log(`ChinaDB SQL policy: ${checks} checks passed`);

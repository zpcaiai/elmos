import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  readChinaDbSqlRepositoryCapabilities,
  assessChinaDbSqlLocally,
  fetchChinaDbSqlCapabilities,
  resolveChinaDbSqlCatalogPath,
} from "../app/lib/server/chinadbSqlPreflight.ts";
import { parseChinaDbSqlPreflightRequest } from "../app/lib/chinadbSqlContracts.ts";

console.log("Testing ChinaDB SQL local pipeline...");

// 1. Catalog path resolution
const catalogPath = resolveChinaDbSqlCatalogPath();
assert.ok(catalogPath.endsWith("chinadb-commercial-v1.json"));
console.log("  ✓ resolveChinaDbSqlCatalogPath");

// 2. Read repository capabilities
const capabilities = readChinaDbSqlRepositoryCapabilities();
assert.equal(capabilities.schemaVersion, "1.0");
assert.equal(capabilities.package, "chinadb-commercial-migration-skills");
assert.equal(capabilities.targetCount, 13);
assert.equal(capabilities.plannedRouteCount, 78);
assert.equal(capabilities.implementationStatus, "LOCAL_ADAPTER");
assert.equal(capabilities.externalExecution, "NOT_RUN");
assert.equal(capabilities.certification, "NOT_CERTIFIED");
assert.ok(capabilities.capabilitySnapshotDigest.startsWith("sha256:"));
console.log("  ✓ readChinaDbSqlRepositoryCapabilities");

// 3. fetchChinaDbSqlCapabilities fallback
const fetchedCaps = await fetchChinaDbSqlCapabilities(null);
assert.equal(fetchedCaps.capabilitySnapshotDigest, capabilities.capabilitySnapshotDigest);
console.log("  ✓ fetchChinaDbSqlCapabilities fallback");

// 4. Local assessment execution via elmos-sql-transpiler
const request = parseChinaDbSqlPreflightRequest({
  schemaVersion: "1.0",
  queryId: "test-query",
  sourceProfile: "oracle-26ai-ee",
  targetId: "dm8",
  targetVersion: "8.1.3.140",
  targetEdition: "enterprise",
  compatibilityMode: "oracle-compatible-explicit",
  targetDriver: "dmjdbc-8.1.3.140",
  targetCharset: "UTF-8",
  targetCollation: "BINARY",
  targetTimeZone: "Asia/Shanghai",
  capabilitySnapshotDigest: capabilities.capabilitySnapshotDigest,
  sql: "SELECT SYSDATE FROM dual;\n",
  parameters: [],
});

const sourceDigest = "sha256:" + createHash("sha256").update(request.sql).digest("hex");
const result = await assessChinaDbSqlLocally(request, capabilities, sourceDigest);
assert.equal(result.state, "LOCAL_EMITTED");
assert.equal(result.certification, "NOT_CERTIFIED");
assert.equal(result.verification.sourceParse, "PASSED");
assert.equal(result.verification.targetAdapter, "PASSED");
assert.equal(result.verification.targetEmit, "PASSED");
assert.equal(result.verification.targetReparse, "PASSED");
assert.equal(result.verification.sourceExecution, "NOT_RUN");
assert.equal(result.verification.targetExecution, "NOT_RUN");
assert.equal(result.verification.resultEquivalence, "NOT_RUN");
assert.equal(result.verification.externalExecution, "NOT_RUN");
assert.ok(typeof result.targetSql === "string" && result.targetSql.length > 0);
console.log("  ✓ assessChinaDbSqlLocally: state =", result.state, ", targetSql =", result.targetSql.trim());

console.log("All ChinaDB SQL local tests passed successfully!");

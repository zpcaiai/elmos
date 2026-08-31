import { ChinaDbSqlPolicyError } from "../chinadbSqlContracts";
import {
  validateControlPlaneBaseUrl,
  type UpstreamEnvironment,
} from "./trustedUpstream";

function fail(status: number, errorCode: string, message: string): never {
  throw new ChinaDbSqlPolicyError(status, errorCode, message);
}

export function resolveChinaDbSqlPreflightBaseUrl(
  environment: UpstreamEnvironment = process.env,
): string {
  if (environment.ELMOS_DATABASE_SQL_PREFLIGHT_ENABLED !== "true") {
    fail(503, "CHINADB_SQL_PREFLIGHT_DISABLED", "ChinaDB SQL 预检尚未启用。");
  }
  const configured = environment.ELMOS_CONTROL_PLANE_BASE_URL?.trim() ?? "";
  if (!configured) {
    fail(503, "CHINADB_SQL_PREFLIGHT_NOT_CONFIGURED", "ChinaDB SQL 预检上游尚未配置。");
  }
  try {
    return validateControlPlaneBaseUrl(configured, environment);
  } catch {
    fail(503, "CHINADB_SQL_PREFLIGHT_CONFIGURATION_INVALID", "ChinaDB SQL 预检上游配置无效。");
  }
}

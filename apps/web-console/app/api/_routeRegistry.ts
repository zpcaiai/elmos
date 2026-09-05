import type { NextRequest } from "next/server";
import { compileRoutes, matchRoute, type RouteParams } from "./_routeMatcher";
import * as route000 from "./account/[[...path]]/_route";
import * as route001 from "./admin/audit-export/_route";
import * as route002 from "./admin/billing/reconciliation/_route";
import * as route003 from "./admin/execution-jobs/_route";
import * as route004 from "./admin/jobs/[jobId]/cancel/_route";
import * as route005 from "./admin/jobs/_route";
import * as route006 from "./admin/operations/_route";
import * as route007 from "./admin/platform-admins/_route";
import * as route008 from "./admin/run-replay/[migrationRunId]/_route";
import * as route009 from "./admin/runners/[runnerNodeId]/attestation/verify/_route";
import * as route010 from "./admin/runners/[runnerNodeId]/drain/_route";
import * as route011 from "./admin/runners/_route";
import * as route012 from "./admin/tenant-quota/_route";
import * as route013 from "./admin/topups/_route";
import * as route014 from "./admin/wallets/[organizationId]/ledger/_route";
import * as route015 from "./admin/wallets/_route";
import * as route016 from "./admin/wallets/adjust/_route";
import * as route017 from "./auth/callback/_route";
import * as route018 from "./auth/login/_route";
import * as route019 from "./auth/logout/_route";
import * as route020 from "./auth/refresh/_route";
import * as route021 from "./auth/register/_route";
import * as route022 from "./auth/session/_route";
import * as route023 from "./auth/tenant/_route";
import * as route024 from "./billing/cancel/_route";
import * as route025 from "./billing/checkout/_route";
import * as route026 from "./billing/subscription/_route";
import * as route027 from "./billing/trial/_route";
import * as route028 from "./capabilities/database-sql/_route";
import * as route029 from "./capabilities/generation/_route";
import * as route030 from "./capabilities/migration/_route";
import * as route031 from "./capabilities/product/_route";
import * as route032 from "./capabilities/spring/_route";
import * as route033 from "./capabilities/translation/_route";
import * as route034 from "./database-sql/preflight/_route";
import * as route035 from "./frt/runs/[runId]/[operation]/_route";
import * as route036 from "./frt/runs/[runId]/_route";
import * as route037 from "./frt/runs/[runId]/audit/_route";
import * as route038 from "./frt/runs/_route";
import * as route039 from "./generation/analyze/_route";
import * as route040 from "./generation/jobs/[jobId]/_route";
import * as route041 from "./generation/jobs/[jobId]/artifact/_route";
import * as route042 from "./generation/jobs/[jobId]/cancel/_route";
import * as route043 from "./generation/jobs/[jobId]/github/_route";
import * as route044 from "./generation/jobs/[jobId]/preview/_route";
import * as route045 from "./generation/jobs/[jobId]/run/_route";
import * as route046 from "./generation/jobs/[jobId]/stop/_route";
import * as route047 from "./generation/jobs/_route";
import * as route048 from "./generation/sources/_route";
import * as route049 from "./github-installation/_route";
import * as route050 from "./github-repositories/_route";
import * as route051 from "./health/_route";
import * as route052 from "./modernization-proof/contracts/_route";
import * as route053 from "./modernization-proof/jobs/[jobId]/_route";
import * as route054 from "./modernization-proof/jobs/_route";
import * as route055 from "./modernization-proof/subject-digest/_route";
import * as route056 from "./multimodal-intake/v1/execute/_route";
import * as route057 from "./multimodal-intake/v1/progress/jobs/[jobId]/_route";
import * as route058 from "./precision-migration/jobs/[jobId]/_route";
import * as route059 from "./precision-migration/jobs/[jobId]/artifacts/[artifact]/_route";
import * as route060 from "./precision-migration/jobs/_route";
import * as route061 from "./precision-migration/jobs/gc/_route";
import * as route062 from "./pricing/_route";
import * as route063 from "./repository-orchestrator/models/_route";
import * as route064 from "./repository-orchestrator/preflight/_route";
import * as route065 from "./repository-workspaces/[[...path]]/_route";
import * as route066 from "./smoke/capability/_route";
import * as route067 from "./smoke/pack/_route";
import * as route068 from "./smoke/sessions/[sessionId]/_route";
import * as route069 from "./smoke/sessions/[sessionId]/evidence/_route";
import * as route070 from "./smoke/sessions/[sessionId]/extend/_route";
import * as route071 from "./smoke/sessions/[sessionId]/stop/_route";
import * as route072 from "./smoke/sessions/_route";
import * as route073 from "./spring-upgrades/[...path]/_route";
import * as route074 from "./spring-upgrades/_route";
import * as route075 from "./telemetry/events/_route";
import * as route076 from "./translation/discovery-report/_route";
import * as route077 from "./translation/health/_route";
import * as route078 from "./translation/jobs/[jobId]/_route";
import * as route079 from "./translation/jobs/[jobId]/artifact/_route";
import * as route080 from "./translation/jobs/[jobId]/cancel/_route";
import * as route081 from "./translation/jobs/[jobId]/report/_route";
import * as route082 from "./translation/jobs/_route";
import * as route083 from "./translation/repository-plan/_route";
import * as route084 from "./usage/alerts/_route";
import * as route085 from "./usage/current/_route";
import * as route086 from "./usage/export/_route";
import * as route087 from "./usage/history/_route";
import * as route088 from "./wallet/_route";
import * as route089 from "./wallet/ledger/_route";
import * as route090 from "./wallet/topup/[topupOrderId]/_route";
import * as route091 from "./wallet/topup/_route";

type ApiMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
type ApiHandler = (
  request: NextRequest,
  context: { params: Promise<RouteParams> },
) => Response | Promise<Response>;
type ApiRouteModule = Readonly<Partial<Record<ApiMethod, unknown>>>;

const METHOD_ORDER: readonly ApiMethod[] = ["GET", "POST", "PUT", "PATCH", "DELETE"];
const ROUTES = compileRoutes<ApiRouteModule>([
  { template: "account/[[...path]]", value: route000 as ApiRouteModule },
  { template: "admin/audit-export", value: route001 as ApiRouteModule },
  { template: "admin/billing/reconciliation", value: route002 as ApiRouteModule },
  { template: "admin/execution-jobs", value: route003 as ApiRouteModule },
  { template: "admin/jobs/[jobId]/cancel", value: route004 as ApiRouteModule },
  { template: "admin/jobs", value: route005 as ApiRouteModule },
  { template: "admin/operations", value: route006 as ApiRouteModule },
  { template: "admin/platform-admins", value: route007 as ApiRouteModule },
  { template: "admin/run-replay/[migrationRunId]", value: route008 as ApiRouteModule },
  { template: "admin/runners/[runnerNodeId]/attestation/verify", value: route009 as ApiRouteModule },
  { template: "admin/runners/[runnerNodeId]/drain", value: route010 as ApiRouteModule },
  { template: "admin/runners", value: route011 as ApiRouteModule },
  { template: "admin/tenant-quota", value: route012 as ApiRouteModule },
  { template: "admin/topups", value: route013 as ApiRouteModule },
  { template: "admin/wallets/[organizationId]/ledger", value: route014 as ApiRouteModule },
  { template: "admin/wallets", value: route015 as ApiRouteModule },
  { template: "admin/wallets/adjust", value: route016 as ApiRouteModule },
  { template: "auth/callback", value: route017 as ApiRouteModule },
  { template: "auth/login", value: route018 as ApiRouteModule },
  { template: "auth/logout", value: route019 as ApiRouteModule },
  { template: "auth/refresh", value: route020 as ApiRouteModule },
  { template: "auth/register", value: route021 as ApiRouteModule },
  { template: "auth/session", value: route022 as ApiRouteModule },
  { template: "auth/tenant", value: route023 as ApiRouteModule },
  { template: "billing/cancel", value: route024 as ApiRouteModule },
  { template: "billing/checkout", value: route025 as ApiRouteModule },
  { template: "billing/subscription", value: route026 as ApiRouteModule },
  { template: "billing/trial", value: route027 as ApiRouteModule },
  { template: "capabilities/database-sql", value: route028 as ApiRouteModule },
  { template: "capabilities/generation", value: route029 as ApiRouteModule },
  { template: "capabilities/migration", value: route030 as ApiRouteModule },
  { template: "capabilities/product", value: route031 as ApiRouteModule },
  { template: "capabilities/spring", value: route032 as ApiRouteModule },
  { template: "capabilities/translation", value: route033 as ApiRouteModule },
  { template: "database-sql/preflight", value: route034 as ApiRouteModule },
  { template: "frt/runs/[runId]/[operation]", value: route035 as ApiRouteModule },
  { template: "frt/runs/[runId]", value: route036 as ApiRouteModule },
  { template: "frt/runs/[runId]/audit", value: route037 as ApiRouteModule },
  { template: "frt/runs", value: route038 as ApiRouteModule },
  { template: "generation/analyze", value: route039 as ApiRouteModule },
  { template: "generation/jobs/[jobId]", value: route040 as ApiRouteModule },
  { template: "generation/jobs/[jobId]/artifact", value: route041 as ApiRouteModule },
  { template: "generation/jobs/[jobId]/cancel", value: route042 as ApiRouteModule },
  { template: "generation/jobs/[jobId]/github", value: route043 as ApiRouteModule },
  { template: "generation/jobs/[jobId]/preview", value: route044 as ApiRouteModule },
  { template: "generation/jobs/[jobId]/run", value: route045 as ApiRouteModule },
  { template: "generation/jobs/[jobId]/stop", value: route046 as ApiRouteModule },
  { template: "generation/jobs", value: route047 as ApiRouteModule },
  { template: "generation/sources", value: route048 as ApiRouteModule },
  { template: "github-installation", value: route049 as ApiRouteModule },
  { template: "github-repositories", value: route050 as ApiRouteModule },
  { template: "health", value: route051 as ApiRouteModule },
  { template: "modernization-proof/contracts", value: route052 as ApiRouteModule },
  { template: "modernization-proof/jobs/[jobId]", value: route053 as ApiRouteModule },
  { template: "modernization-proof/jobs", value: route054 as ApiRouteModule },
  { template: "modernization-proof/subject-digest", value: route055 as ApiRouteModule },
  { template: "multimodal-intake/v1/execute", value: route056 as ApiRouteModule },
  { template: "multimodal-intake/v1/progress/jobs/[jobId]", value: route057 as ApiRouteModule },
  { template: "precision-migration/jobs/[jobId]", value: route058 as ApiRouteModule },
  { template: "precision-migration/jobs/[jobId]/artifacts/[artifact]", value: route059 as ApiRouteModule },
  { template: "precision-migration/jobs", value: route060 as ApiRouteModule },
  { template: "precision-migration/jobs/gc", value: route061 as ApiRouteModule },
  { template: "pricing", value: route062 as ApiRouteModule },
  { template: "repository-orchestrator/models", value: route063 as ApiRouteModule },
  { template: "repository-orchestrator/preflight", value: route064 as ApiRouteModule },
  { template: "repository-workspaces/[[...path]]", value: route065 as ApiRouteModule },
  { template: "smoke/capability", value: route066 as ApiRouteModule },
  { template: "smoke/pack", value: route067 as ApiRouteModule },
  { template: "smoke/sessions/[sessionId]", value: route068 as ApiRouteModule },
  { template: "smoke/sessions/[sessionId]/evidence", value: route069 as ApiRouteModule },
  { template: "smoke/sessions/[sessionId]/extend", value: route070 as ApiRouteModule },
  { template: "smoke/sessions/[sessionId]/stop", value: route071 as ApiRouteModule },
  { template: "smoke/sessions", value: route072 as ApiRouteModule },
  { template: "spring-upgrades/[...path]", value: route073 as ApiRouteModule },
  { template: "spring-upgrades", value: route074 as ApiRouteModule },
  { template: "telemetry/events", value: route075 as ApiRouteModule },
  { template: "translation/discovery-report", value: route076 as ApiRouteModule },
  { template: "translation/health", value: route077 as ApiRouteModule },
  { template: "translation/jobs/[jobId]", value: route078 as ApiRouteModule },
  { template: "translation/jobs/[jobId]/artifact", value: route079 as ApiRouteModule },
  { template: "translation/jobs/[jobId]/cancel", value: route080 as ApiRouteModule },
  { template: "translation/jobs/[jobId]/report", value: route081 as ApiRouteModule },
  { template: "translation/jobs", value: route082 as ApiRouteModule },
  { template: "translation/repository-plan", value: route083 as ApiRouteModule },
  { template: "usage/alerts", value: route084 as ApiRouteModule },
  { template: "usage/current", value: route085 as ApiRouteModule },
  { template: "usage/export", value: route086 as ApiRouteModule },
  { template: "usage/history", value: route087 as ApiRouteModule },
  { template: "wallet", value: route088 as ApiRouteModule },
  { template: "wallet/ledger", value: route089 as ApiRouteModule },
  { template: "wallet/topup/[topupOrderId]", value: route090 as ApiRouteModule },
  { template: "wallet/topup", value: route091 as ApiRouteModule },
]);

function allowedMethods(module: ApiRouteModule): string {
  const methods: string[] = METHOD_ORDER.filter((method) => typeof module[method] === "function");
  if (methods.includes("GET")) methods.push("HEAD");
  return [...methods, "OPTIONS"].join(", ");
}

function jsonError(status: number, code: string, allow?: string): Response {
  const headers = new Headers({ "content-type": "application/json; charset=utf-8" });
  if (allow) headers.set("allow", allow);
  return new Response(JSON.stringify({ error: code }), { status, headers });
}

export async function dispatchApiRoute(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
  method: ApiMethod | "HEAD" | "OPTIONS",
): Promise<Response> {
  const { path = [] } = await context.params;
  const match = matchRoute(path, ROUTES);
  if (match === null) return jsonError(404, "API_ROUTE_NOT_FOUND");

  const allow = allowedMethods(match.value);
  if (method === "OPTIONS") return new Response(null, { status: 204, headers: { allow } });

  const effectiveMethod: ApiMethod = method === "HEAD" ? "GET" : method;
  const candidate = match.value[effectiveMethod];
  if (typeof candidate !== "function") {
    return jsonError(405, "METHOD_NOT_ALLOWED", allow);
  }

  const response = await (candidate as ApiHandler)(request, {
    params: Promise.resolve(match.params),
  });
  if (method !== "HEAD") return response;
  return new Response(null, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { FrontendClientEngine } from "./engine.js";
import type { EngineJobRequest, ExecuteStepRequest, JobResponse } from "./contracts.js";
import {
  validateFrtBatchPlanRequest,
  validateFrtRunCompletionRequest,
  validateFrtRunTransitionRequest,
  validateFrtSkillRunRequest,
} from "./frt-contract-validation.js";
import { FrtRuntime } from "./frt-runtime.js";
import type { FrtRunStore } from "./frt-run-store.js";
import {
  frtSecurityFromEnvironment,
  FrtSecurityError,
  verifyFrtIdentityToken,
  type FrtIdentityClaims,
  type FrtSecurityContext,
} from "./frt-security.js";
import type { FrtBatchPlanRequest, FrtSkillRunRequest } from "./frt-types.js";
import { uiProjectGenerationCapabilities } from "./project-generation.js";

const maximumBodyBytes = 1_048_576;
// Per docs/frt-g01-g30/RUNNER_CONTRACT.md section 2. Creating a run carries a source
// snapshot and needs real headroom; every other FRT call is a small control message, so
// it gets a much tighter ceiling. Non-FRT engine routes keep the original 1 MiB.
const maximumFrtRunBytes = 16 * 1024 * 1024;
const maximumFrtControlBytes = 64 * 1024;
// A modest oversized request is drained without buffering so the server can return a
// deterministic 413 instead of resetting a client that is still uploading. Requests
// beyond the largest supported FRT envelope are terminated rather than drained forever.
const maximumRejectedBodyDrainBytes = maximumFrtRunBytes;

export interface FrontendClientServerOptions {
  readonly engine?: FrontendClientEngine;
  readonly frtRuntime?: FrtRuntime;
  readonly frtSecurity?: FrtSecurityContext;
  readonly frtRunStore?: FrtRunStore;
}

/**
 * Raised when a request body exceeds its route limit. It is distinct from a contract
 * rejection because the body is outside the route contract. Small rejected envelopes
 * are drained without buffering; envelopes beyond the hard ceiling are reset.
 */
class PayloadTooLargeError extends Error {
  constructor(
    readonly limitBytes: number,
    readonly requestDrained: boolean,
  ) {
    super("REQUEST_TOO_LARGE");
    this.name = "PayloadTooLargeError";
  }
}

class FrtHttpAuthorizationError extends Error {
  readonly status: 401 | 403;
  readonly errorCode: string;

  constructor(status: 401 | 403, errorCode: string) {
    super(errorCode);
    this.status = status;
    this.errorCode = errorCode;
  }
}

function authorizeFrt(
  request: IncomingMessage,
  security: FrtSecurityContext,
  permission: FrtIdentityClaims["permissions"][number],
): FrtIdentityClaims {
  const header = request.headers.authorization;
  if (!header?.startsWith("Bearer ") || header.length <= 7) {
    throw new FrtHttpAuthorizationError(401, "FRT_AUTHENTICATION_REQUIRED");
  }
  let claims: FrtIdentityClaims;
  try {
    claims = verifyFrtIdentityToken(header.slice(7), security.trustStore, security.now());
  } catch (error) {
    const code = error instanceof FrtSecurityError ? error.code : "FRT_IDENTITY_TOKEN_INVALID";
    const publicCode = code.includes("EXPIRED") ? "FRT_IDENTITY_EXPIRED"
      : code.includes("SIGNATURE") ? "FRT_IDENTITY_SIGNATURE_INVALID"
        : code.includes("TRUST_KEY") ? "FRT_IDENTITY_TRUST_REJECTED"
          : "FRT_IDENTITY_TOKEN_INVALID";
    throw new FrtHttpAuthorizationError(401, publicCode);
  }
  if (!claims.permissions.includes(permission)) {
    throw new FrtHttpAuthorizationError(403, "FRT_PERMISSION_DENIED");
  }
  return claims;
}

function assertFrtScope(claims: FrtIdentityClaims, request: FrtBatchPlanRequest | FrtSkillRunRequest): void {
  const exactScope = Object.entries(claims.scope).every(
    ([key, value]) => request.context[key as keyof typeof claims.scope] === value,
  );
  if (!exactScope || request.context.requestedBy !== claims.subject) {
    throw new FrtHttpAuthorizationError(403, "FRT_SCOPE_MISMATCH");
  }
}

async function body(request: IncomingMessage, maximumBytes = maximumBodyBytes): Promise<unknown> {
  const chunks: Buffer[] = [];
  let size = 0;
  let exceeded = false;
  const contentLength = Number.parseInt(request.headers["content-length"] ?? "", 10);
  if (Number.isFinite(contentLength) && contentLength > maximumRejectedBodyDrainBytes) {
    throw new PayloadTooLargeError(maximumBytes, false);
  }
  for await (const chunk of request) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buffer.length;
    if (size > maximumRejectedBodyDrainBytes) {
      throw new PayloadTooLargeError(maximumBytes, false);
    }
    if (size > maximumBytes) {
      exceeded = true;
      continue;
    }
    if (!exceeded) chunks.push(buffer);
  }
  if (exceeded) throw new PayloadTooLargeError(maximumBytes, true);
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function send(response: ServerResponse, status: number, value: unknown): void {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  response.end(JSON.stringify(value));
}

function statusFor(response: JobResponse, successStatus: 200 | 202): number {
  if (response.error?.errorCode === "IDEMPOTENCY_CONFLICT" || response.error?.errorCode === "JOB_TERMINAL") return 409;
  if (response.error?.errorCode === "JOB_NOT_FOUND") return 404;
  return successStatus;
}

function sendJob(response: ServerResponse, value: JobResponse, successStatus: 200 | 202): void {
  const status = statusFor(value, successStatus);
  send(response, status, status >= 400 ? value.error : value);
}

export function createFrontendClientServer(options: FrontendClientServerOptions = {}) {
  const engine = options.engine ?? new FrontendClientEngine();
  const security = options.frtSecurity ?? frtSecurityFromEnvironment();
  const frtRuntime = options.frtRuntime ?? new FrtRuntime({
    security,
    ...(options.frtRunStore ? { store: options.frtRunStore } : {}),
  });
  return createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? "/", "http://localhost");
    if (request.method === "GET" && url.pathname === "/engine/v1/capabilities") return send(response, 200, engine.capabilities());
    if (request.method === "GET" && url.pathname === "/engine/v1/ui-projects/capabilities") {
      return send(response, 200, uiProjectGenerationCapabilities());
    }
    if (request.method === "GET" && url.pathname === "/engine/v1/frt/catalog") {
      return send(response, 200, frtRuntime.catalog(
        url.searchParams.get("batch") ?? undefined,
        url.searchParams.get("query") ?? undefined,
      ));
    }
    if (request.method === "GET" && url.pathname === "/engine/v1/frt/routes") {
      return send(response, 200, {
        schemaVersion: "1.0",
        directedRouteCount: frtRuntime.routes().length,
        routes: frtRuntime.routes(),
        certification: "NOT_CERTIFIED",
      });
    }
    const skillDefinition = url.pathname.match(/^\/engine\/v1\/frt\/skills\/([^/]+)$/);
    if (request.method === "GET" && skillDefinition) {
      const skill = frtRuntime.skill(skillDefinition[1]!);
      return skill ? send(response, 200, skill) : send(response, 404, { errorCode: "FRT_SKILL_NOT_FOUND" });
    }
    const skillRun = url.pathname.match(/^\/engine\/v1\/frt\/skills\/([^/]+)\/runs$/);
    if (request.method === "POST" && skillRun) {
      const principal = authorizeFrt(request, security, "frt:run");
      const value = validateFrtSkillRunRequest(await body(request, maximumFrtRunBytes)) as FrtSkillRunRequest;
      assertFrtScope(principal, value);
      if (value.action === "VERIFY" && !principal.permissions.includes("frt:evidence")) {
        throw new FrtHttpAuthorizationError(403, "FRT_PERMISSION_DENIED");
      }
      if (frtRuntime.skill(skillRun[1]!)?.id !== frtRuntime.skill(value.skillId)?.id) {
        return send(response, 400, { errorCode: "FRT_SKILL_SCOPE_MISMATCH" });
      }
      const result = frtRuntime.run(value);
      return send(response, result.state === "FAILED" ? 400 : 202, result);
    }
    const scopedSkillRun = url.pathname.match(
      /^\/engine\/v1\/frt\/skills\/([^/]+)\/runs\/([^/]+)(?:\/(findings|evidence))?$/,
    );
    if (request.method === "GET" && scopedSkillRun) {
      const principal = authorizeFrt(request, security, "frt:read");
      const skill = frtRuntime.skill(scopedSkillRun[1]!);
      const result = frtRuntime.getRun(principal.scope, scopedSkillRun[2]!);
      if (!skill || !result || result.skillId !== skill.id) {
        return send(response, 404, { errorCode: "FRT_RUN_NOT_FOUND" });
      }
      if (scopedSkillRun[3] === "findings") {
        return send(response, 200, { runId: result.runId, findings: result.findings });
      }
      if (scopedSkillRun[3] === "evidence") {
        return send(response, 200, {
          runId: result.runId,
          inputDigest: result.inputDigest,
          resultDigest: result.resultDigest,
          evidence: result.evidence,
          certificateFragment: result.certificateFragment,
        });
      }
      return send(response, 200, result);
    }
    const scopedSkillVerify = url.pathname.match(
      /^\/engine\/v1\/frt\/skills\/([^/]+)\/runs\/([^/]+)\/verify$/,
    );
    if (request.method === "POST" && scopedSkillVerify) {
      authorizeFrt(request, security, "frt:run");
      const principal = authorizeFrt(request, security, "frt:evidence");
      const value = validateFrtSkillRunRequest(await body(request, maximumFrtRunBytes)) as FrtSkillRunRequest;
      assertFrtScope(principal, value);
      const skill = frtRuntime.skill(scopedSkillVerify[1]!);
      const subject = frtRuntime.getRun(principal.scope, scopedSkillVerify[2]!);
      if (value.action !== "VERIFY" || !skill || !subject || subject.skillId !== skill.id
          || frtRuntime.skill(value.skillId)?.id !== skill.id
          || value.verificationSubject?.runId !== subject.runId
          || value.verificationSubject.resultDigest !== subject.resultDigest) {
        return send(response, 400, { errorCode: "FRT_VERIFICATION_SUBJECT_MISMATCH" });
      }
      const result = frtRuntime.run(value);
      return send(response, result.state === "FAILED" ? 400 : 202, result);
    }
    const batchPlan = url.pathname.match(/^\/engine\/v1\/frt\/batches\/([^/]+)\/plans$/);
    if (request.method === "POST" && batchPlan) {
      const principal = authorizeFrt(request, security, "frt:plan");
      const value = validateFrtBatchPlanRequest(await body(request, maximumFrtControlBytes)) as FrtBatchPlanRequest;
      assertFrtScope(principal, value);
      if (value.batch.toLocaleUpperCase("en-US") !== batchPlan[1]!.toLocaleUpperCase("en-US")) {
        return send(response, 400, { errorCode: "FRT_BATCH_SCOPE_MISMATCH" });
      }
      const result = frtRuntime.planBatch(value);
      return send(response, result.state === "BLOCKED" ? 409 : 200, result);
    }
    const frtRun = url.pathname.match(/^\/engine\/v1\/frt\/runs\/([^/]+)$/);
    if (request.method === "GET" && frtRun) {
      const principal = authorizeFrt(request, security, "frt:read");
      const result = frtRuntime.getRun(principal.scope, frtRun[1]!);
      return result ? send(response, 200, result) : send(response, 404, { errorCode: "FRT_RUN_NOT_FOUND" });
    }
    const frtAudit = url.pathname.match(/^\/engine\/v1\/frt\/runs\/([^/]+)\/audit$/);
    if (request.method === "GET" && frtAudit) {
      const principal = authorizeFrt(request, security, "frt:read");
      const audit = frtRuntime.audit(principal.scope, frtAudit[1]!);
      return audit ? send(response, 200, { runId: frtAudit[1], audit })
        : send(response, 404, { errorCode: "FRT_RUN_NOT_FOUND" });
    }
    const frtTransition = url.pathname.match(
      /^\/engine\/v1\/frt\/runs\/([^/]+)\/(claim|heartbeat|cancel|retry)$/,
    );
    if (request.method === "POST" && frtTransition) {
      const principal = authorizeFrt(request, security, "frt:run");
      const command = validateFrtRunTransitionRequest(await body(request, maximumFrtControlBytes));
      try {
        // A renewal is holder-only and refused once the lease has expired, so a runner that
        // stalled past its lease cannot quietly regain authority by heartbeating.
        const result = frtTransition[2] === "claim"
          ? frtRuntime.claim(principal.scope, frtTransition[1]!, command.expectedVersion, principal.subject)
          : frtTransition[2] === "heartbeat"
            ? frtRuntime.heartbeat(principal.scope, frtTransition[1]!, command.expectedVersion, principal.subject)
            : frtTransition[2] === "cancel"
              ? frtRuntime.cancel(principal.scope, frtTransition[1]!, command.expectedVersion, principal.subject)
              : frtRuntime.retry(principal.scope, frtTransition[1]!, command.expectedVersion, principal.subject);
        return result ? send(response, 200, result)
          : send(response, 404, { errorCode: "FRT_RUN_NOT_FOUND" });
      } catch {
        return send(response, 409, { errorCode: "FRT_RUN_TRANSITION_REJECTED" });
      }
    }
    const frtComplete = url.pathname.match(/^\/engine\/v1\/frt\/runs\/([^/]+)\/complete$/);
    if (request.method === "POST" && frtComplete) {
      // Recording an execution registers evidence, so it needs the evidence permission on
      // top of frt:run. It still certifies nothing: the batch gate stays ineligible and the
      // certificate family stays NOT_CERTIFIED until a separate VERIFY run passes.
      authorizeFrt(request, security, "frt:run");
      const principal = authorizeFrt(request, security, "frt:evidence");
      const command = validateFrtRunCompletionRequest(await body(request, maximumFrtControlBytes));
      try {
        const result = frtRuntime.complete(
          principal.scope,
          frtComplete[1]!,
          command.expectedVersion,
          principal.subject,
          command.completion,
        );
        return result ? send(response, result.state === "SUCCEEDED" ? 200 : 409, result)
          : send(response, 404, { errorCode: "FRT_RUN_NOT_FOUND" });
      } catch {
        return send(response, 409, { errorCode: "FRT_RUN_TRANSITION_REJECTED" });
      }
    }
    const frtFindings = url.pathname.match(/^\/engine\/v1\/frt\/runs\/([^/]+)\/findings$/);
    if (request.method === "GET" && frtFindings) {
      const principal = authorizeFrt(request, security, "frt:read");
      const result = frtRuntime.getRun(principal.scope, frtFindings[1]!);
      return result ? send(response, 200, { runId: result.runId, findings: result.findings })
        : send(response, 404, { errorCode: "FRT_RUN_NOT_FOUND" });
    }
    const frtEvidence = url.pathname.match(/^\/engine\/v1\/frt\/runs\/([^/]+)\/evidence$/);
    if (request.method === "GET" && frtEvidence) {
      const principal = authorizeFrt(request, security, "frt:read");
      const result = frtRuntime.getRun(principal.scope, frtEvidence[1]!);
      return result ? send(response, 200, {
        runId: result.runId,
        inputDigest: result.inputDigest,
        resultDigest: result.resultDigest,
        evidence: result.evidence,
        certificateFragment: result.certificateFragment,
      }) : send(response, 404, { errorCode: "FRT_RUN_NOT_FOUND" });
    }
    if (request.method === "GET" && url.pathname === "/health") return send(response, 200, { status: "UP", engine: "ELMOS_FRONTEND_CLIENT" });
    const match = url.pathname.match(/^\/engine\/v1\/jobs\/([^/]+)$/);
    if (request.method === "GET" && match) {
      const result = engine.job(url.searchParams.get("organizationId") ?? "", match[1]!);
      return sendJob(response, result, 200);
    }
    const cancel = url.pathname.match(/^\/engine\/v1\/jobs\/([^/]+)\/cancel$/);
    if (request.method === "POST" && cancel) {
      const result = engine.cancel(url.searchParams.get("organizationId") ?? "", cancel[1]!);
      return sendJob(response, result, 200);
    }
    if (request.method === "POST" && url.pathname.startsWith("/engine/v1/")) {
      const value = await body(request) as EngineJobRequest;
      const result = url.pathname === "/engine/v1/scan" ? engine.scan(value)
        : url.pathname === "/engine/v1/plan" ? engine.plan(value)
        : url.pathname === "/engine/v1/validate" ? engine.validate(value)
        : url.pathname === "/engine/v1/generate-project" ? engine.generateProject(value)
        : url.pathname === "/engine/v1/execute-step" ? engine.executeStep(value as ExecuteStepRequest)
        : undefined;
      if (result) return sendJob(response, result, 202);
    }
    send(response, 404, { errorCode: "NOT_FOUND" });
  } catch (error) {
    if (error instanceof PayloadTooLargeError) {
      // Modest rejected bodies have already been drained without buffering. Only an
      // envelope beyond the hard drain ceiling is reset immediately.
      if (!error.requestDrained) request.destroy();
      response.writeHead(413, {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store",
        connection: "close",
      });
      return response.end(JSON.stringify({ errorCode: "REQUEST_TOO_LARGE", limitBytes: error.limitBytes }));
    }
    if (error instanceof FrtHttpAuthorizationError) {
      return send(response, error.status, { errorCode: error.errorCode });
    }
    send(response, 400, { errorCode: "FRONTEND_REQUEST_REJECTED", message: "The frontend engine request was rejected by its contract." });
  }
  });
}

export const server = createFrontendClientServer();

if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  const port = Number.parseInt(process.env.ELMOS_FRONTEND_PORT ?? "8088", 10);
  const host = process.env.ELMOS_FRONTEND_HOST ?? "127.0.0.1";
  server.listen(port, host);
}

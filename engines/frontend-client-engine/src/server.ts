import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { FrontendClientEngine } from "./engine.js";
import type { EngineJobRequest, ExecuteStepRequest, JobResponse } from "./contracts.js";

const engine = new FrontendClientEngine();
const maximumBodyBytes = 1_048_576;

async function body(request: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buffer.length;
    if (size > maximumBodyBytes) throw new Error("request body exceeds 1 MiB");
    chunks.push(buffer);
  }
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

export const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? "/", "http://localhost");
    if (request.method === "GET" && url.pathname === "/engine/v1/capabilities") return send(response, 200, engine.capabilities());
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
        : url.pathname === "/engine/v1/execute-step" ? engine.executeStep(value as ExecuteStepRequest)
        : undefined;
      if (result) return sendJob(response, result, 202);
    }
    send(response, 404, { errorCode: "NOT_FOUND" });
  } catch {
    send(response, 400, { errorCode: "FRONTEND_REQUEST_REJECTED", message: "The frontend engine request was rejected by its contract." });
  }
});

if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  const port = Number.parseInt(process.env.ELMOS_FRONTEND_PORT ?? "8088", 10);
  const host = process.env.ELMOS_FRONTEND_HOST ?? "127.0.0.1";
  server.listen(port, host);
}

#!/usr/bin/env node

import { timingSafeEqual } from "node:crypto";
import { createServer } from "node:http";

const host = process.env.ELMOS_FRT_AUDIT_FIXTURE_HOST ?? "127.0.0.1";
const port = Number.parseInt(process.env.ELMOS_FRT_AUDIT_FIXTURE_PORT ?? "5264", 10);
const key = process.env.ELMOS_FRT_AUDIT_FIXTURE_KEY ?? "";
const tenant = process.env.ELMOS_FRT_AUDIT_FIXTURE_TENANT ?? "";
const actor = process.env.ELMOS_FRT_AUDIT_FIXTURE_ACTOR ?? "";
const identifier = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

if (host !== "127.0.0.1" || !Number.isInteger(port) || port < 1_024 || port > 65_535
    || key.length < 24 || !identifier.test(tenant) || !identifier.test(actor)) {
  throw new Error("FRT_AUDIT_FIXTURE_CONFIGURATION_INVALID");
}

function same(left, right) {
  const leftBytes = Buffer.from(left);
  const rightBytes = Buffer.from(right);
  return leftBytes.byteLength === rightBytes.byteLength && timingSafeEqual(leftBytes, rightBytes);
}

const server = createServer((request, response) => {
  response.setHeader("cache-control", "no-store");
  if (request.method === "GET" && request.url === "/health") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end('{"status":"UP","kind":"LOCAL_QUALIFICATION_AUDIT_FIXTURE"}\n');
    return;
  }
  if (request.method !== "POST" || request.url !== "/api/v1/operations-observability/audit-events"
      || !same(String(request.headers["x-elmos-operations-key"] ?? ""), key)
      || request.headers["x-elmos-organization-id"] !== tenant
      || request.headers["x-elmos-actor-id"] !== actor) {
    response.writeHead(403, { "content-type": "application/json" });
    response.end('{"error":"AUDIT_FIXTURE_REQUEST_REJECTED"}\n');
    return;
  }
  const chunks = [];
  let byteCount = 0;
  request.on("data", (chunk) => {
    byteCount += chunk.byteLength;
    if (byteCount > 64 * 1_024) request.destroy(new Error("AUDIT_FIXTURE_BODY_TOO_LARGE"));
    else chunks.push(chunk);
  });
  request.on("end", () => {
    try {
      const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      if (!payload || !Array.isArray(payload.events) || payload.events.length !== 1
          || payload.events[0]?.eventKind !== "SERVER_ATTEMPT") {
        throw new Error("AUDIT_FIXTURE_BODY_INVALID");
      }
      response.writeHead(204);
      response.end();
    } catch {
      response.writeHead(400, { "content-type": "application/json" });
      response.end('{"error":"AUDIT_FIXTURE_BODY_INVALID"}\n');
    }
  });
});

server.listen(port, host, () => {
  process.stdout.write(`FRT local audit fixture listening on http://${host}:${port}\n`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}

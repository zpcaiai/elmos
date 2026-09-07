import { createHash, randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import http from "node:http";
import https from "node:https";
import {
  exportJWK,
  generateKeyPair,
  SignJWT,
} from "jose";

const idpPort = requiredPort("ELMOS_E2E_OIDC_PORT");
const proxyPort = requiredPort("ELMOS_E2E_TLS_PROXY_PORT");
const upstreamPort = requiredPort("ELMOS_E2E_NEXT_UPSTREAM_PORT");
const auditUpstreamPort = requiredPort("ELMOS_E2E_AUDIT_UPSTREAM_PORT");
const healthPort = requiredPort("ELMOS_E2E_HARNESS_HEALTH_PORT");
const clientId = required("ELMOS_E2E_OIDC_CLIENT_ID");
const clientSecret = required("ELMOS_E2E_OIDC_CLIENT_SECRET", 16);
const redirectUri = requiredUrl("ELMOS_E2E_OIDC_REDIRECT_URI");
const issuer = requiredOrigin("ELMOS_E2E_OIDC_ISSUER");
const idpListenHost = required("ELMOS_E2E_OIDC_LISTEN_HOST");
const tls = {
  key: readFileSync(required("ELMOS_E2E_TLS_KEY_PATH")),
  cert: readFileSync(required("ELMOS_E2E_TLS_CERT_PATH")),
};
const codeLifetimeMs = 2 * 60_000;
const pendingLifetimeMs = 5 * 60_000;
const maximumOutstandingRecords = 128;
const pending = new Map();
const codes = new Map();
const issuedAccessTokens = new Map();
const signingKeyId = "elmos-local-oidc-e2e-20260809";
const { privateKey, publicKey } = await generateKeyPair("RS256", {
  modulusLength: 2048,
  extractable: true,
});
const publicJwk = {
  ...(await exportJWK(publicKey)),
  alg: "RS256",
  kid: signingKeyId,
  use: "sig",
};

function required(name, minimumLength = 1) {
  const value = process.env[name]?.trim() ?? "";
  if (value.length < minimumLength) throw new Error(`${name}_REQUIRED`);
  return value;
}

function requiredPort(name) {
  const value = Number.parseInt(required(name), 10);
  if (!Number.isInteger(value) || value < 1024 || value > 65_535) {
    throw new Error(`${name}_INVALID`);
  }
  return value;
}

function requiredUrl(name) {
  const value = required(name);
  const parsed = new URL(value);
  if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.hash) {
    throw new Error(`${name}_INVALID`);
  }
  return parsed.toString();
}

function requiredOrigin(name) {
  const parsed = new URL(requiredUrl(name));
  if (parsed.pathname !== "/" || parsed.search) throw new Error(`${name}_INVALID`);
  return parsed.origin;
}

function randomId(bytes = 32) {
  return randomBytes(bytes).toString("base64url");
}

function safeEqualText(left, right) {
  const leftDigest = createHash("sha256").update(left).digest();
  const rightDigest = createHash("sha256").update(right).digest();
  return leftDigest.equals(rightDigest);
}

function baseHeaders(contentType) {
  return {
    "cache-control": "no-store, private",
    "content-type": contentType,
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
  };
}

function sendJson(response, status, value) {
  response.writeHead(status, baseHeaders("application/json; charset=utf-8"));
  response.end(`${JSON.stringify(value)}\n`);
}

function sendText(response, status, value) {
  response.writeHead(status, baseHeaders("text/plain; charset=utf-8"));
  response.end(value);
}

function sendHtml(response, status, value) {
  response.writeHead(status, {
    ...baseHeaders("text/html; charset=utf-8"),
    "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
  });
  response.end(value);
}

function redirect(response, target) {
  response.writeHead(302, {
    ...baseHeaders("text/plain; charset=utf-8"),
    location: target,
  });
  response.end("Redirecting\n");
}

async function readForm(request) {
  const chunks = [];
  let total = 0;
  for await (const chunk of request) {
    total += chunk.length;
    if (total > 16_384) throw new Error("REQUEST_TOO_LARGE");
    chunks.push(chunk);
  }
  return new URLSearchParams(Buffer.concat(chunks).toString("utf8"));
}

function prune() {
  const now = Date.now();
  for (const [key, value] of pending) {
    if (value.expiresAt <= now) pending.delete(key);
  }
  for (const [key, value] of codes) {
    if (value.expiresAt <= now) codes.delete(key);
  }
  while (pending.size >= maximumOutstandingRecords) {
    pending.delete(pending.keys().next().value);
  }
  while (codes.size >= maximumOutstandingRecords) {
    codes.delete(codes.keys().next().value);
  }
  for (const [key, expiresAt] of issuedAccessTokens) {
    if (expiresAt <= now) issuedAccessTokens.delete(key);
  }
  while (issuedAccessTokens.size >= maximumOutstandingRecords) {
    issuedAccessTokens.delete(issuedAccessTokens.keys().next().value);
  }
}

function validateAuthorization(url) {
  const responseType = url.searchParams.get("response_type") ?? "";
  const requestedClientId = url.searchParams.get("client_id") ?? "";
  const requestedRedirect = url.searchParams.get("redirect_uri") ?? "";
  const scope = url.searchParams.get("scope") ?? "";
  const state = url.searchParams.get("state") ?? "";
  const nonce = url.searchParams.get("nonce") ?? "";
  const codeChallenge = url.searchParams.get("code_challenge") ?? "";
  const challengeMethod = url.searchParams.get("code_challenge_method") ?? "";
  if (
    responseType !== "code"
    || requestedClientId !== clientId
    || requestedRedirect !== redirectUri
    || !scope.split(/\s+/).includes("openid")
    || state.length < 32 || state.length > 512
    || nonce.length < 32 || nonce.length > 512
    || !/^[A-Za-z0-9_-]{43}$/.test(codeChallenge)
    || challengeMethod !== "S256"
  ) {
    return null;
  }
  return { state, nonce, codeChallenge, expiresAt: Date.now() + pendingLifetimeMs };
}

const identities = {
  developer: {
    identity: {
      sub: "user:spring-production-e2e",
      organization_id: "spring-production-e2e",
      name: "Spring Production E2E Developer",
      roles: ["DEVELOPER"],
    },
  },
  viewer: {
    identity: {
      sub: "user:spring-production-viewer",
      organization_id: "spring-production-e2e",
      name: "Spring Production E2E Viewer",
      roles: ["VIEWER"],
    },
  },
  wrongTenant: {
    identity: {
      sub: "user:spring-production-cross-tenant",
      organization_id: "other-production-tenant",
      name: "Spring Production E2E Cross Tenant",
      roles: ["DEVELOPER"],
    },
  },
  nonceMismatch: {
    identity: {
      sub: "user:spring-production-e2e",
      organization_id: "spring-production-e2e",
      name: "Spring Production E2E Nonce Negative",
      roles: ["DEVELOPER"],
    },
    nonceMismatch: true,
  },
  pkceMismatch: {
    identity: {
      sub: "user:spring-production-e2e",
      organization_id: "spring-production-e2e",
      name: "Spring Production E2E PKCE Negative",
      roles: ["DEVELOPER"],
    },
    pkceMismatch: true,
  },
  stateMismatch: {
    identity: {
      sub: "user:spring-production-e2e",
      organization_id: "spring-production-e2e",
      name: "Spring Production E2E State Negative",
      roles: ["DEVELOPER"],
    },
    stateMismatch: true,
  },
};

async function issueIdToken(record) {
  const now = Math.floor(Date.now() / 1_000);
  return new SignJWT({
    ...record.identity,
    nonce: record.nonce,
  })
    .setProtectedHeader({ alg: "RS256", kid: signingKeyId, typ: "JWT" })
    .setIssuer(issuer)
    .setAudience(clientId)
    .setIssuedAt(now)
    .setExpirationTime(now + 600)
    .sign(privateKey);
}

function proxyAudit(request, response) {
  return new Promise((resolve) => {
    process.stdout.write("OIDC harness forwarding one production audit event\n");
    const headers = { ...request.headers, host: `127.0.0.1:${auditUpstreamPort}` };
    delete headers.connection;
    const upstream = http.request({
      hostname: "127.0.0.1",
      port: auditUpstreamPort,
      method: request.method,
      path: request.url,
      headers,
    }, (upstreamResponse) => {
      process.stdout.write(`OIDC harness audit fixture status ${upstreamResponse.statusCode ?? 502}\n`);
      response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers);
      upstreamResponse.pipe(response);
      upstreamResponse.on("end", resolve);
    });
    upstream.on("error", (error) => {
      process.stderr.write(`OIDC harness audit fixture transport error: ${error.code ?? "UNKNOWN"}\n`);
      sendText(response, 502, "Audit fixture unavailable\n");
      resolve();
    });
    request.pipe(upstream);
  });
}

async function handleIdp(request, response) {
  const url = new URL(request.url ?? "/", issuer);
  prune();
  const cookieNames = (request.headers.cookie ?? "")
    .split(";")
    .map((cookie) => cookie.trim().split("=", 1)[0]);
  if (cookieNames.some((name) => name.startsWith("__Host-elmos_"))) {
    return sendText(response, 400, "Application cookie rejected by isolated IdP\n");
  }
  if (request.method === "GET" && url.pathname === "/health") {
    return sendJson(response, 200, { status: "ok", service: "isolated-e2e-oidc" });
  }
  if (request.method === "GET" && url.pathname === "/.well-known/jwks.json") {
    return sendJson(response, 200, { keys: [publicJwk] });
  }
  if (request.method === "GET" && url.pathname === "/authorize") {
    const authorization = validateAuthorization(url);
    if (!authorization) return sendText(response, 400, "Invalid authorization request\n");
    const requestId = randomId();
    pending.set(requestId, authorization);
    return sendHtml(response, 200, `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ELMOS 隔离测试身份提供商</title><style>
body{font-family:system-ui,sans-serif;max-width:44rem;margin:4rem auto;padding:0 1.5rem;line-height:1.5;color:#14213d}
main{border:1px solid #ccd4e0;border-radius:1rem;padding:2rem;box-shadow:0 1rem 3rem #14213d16}
.actions{display:grid;gap:.75rem;margin-top:1.5rem}button{font:inherit;text-align:left;padding:.85rem 1rem;border-radius:.6rem;border:1px solid #7b8aa5;background:#f8fafc;cursor:pointer}button:first-of-type{background:#14213d;color:white}
small{display:block;margin-top:1.25rem;color:#526078}</style></head>
<body><main aria-labelledby="idp-title"><p>LOCAL ISOLATED OIDC</p><h1 id="idp-title">选择合成测试身份</h1>
<p>该身份提供商只在本机 E2E 进程中存在；不会读取或保存真实账户凭据。</p>
<form method="post" action="/approve"><input type="hidden" name="request_id" value="${requestId}"><div class="actions">
<button name="identity" value="developer">以 Spring E2E 开发者登录</button>
<button name="identity" value="viewer">以只读 Viewer 登录</button>
<button name="identity" value="wrongTenant">以其他租户开发者登录</button>
<button name="identity" value="nonceMismatch">负例：返回 nonce 不匹配令牌</button>
<button name="identity" value="pkceMismatch">负例：拒绝 PKCE verifier</button>
<button name="identity" value="stateMismatch">负例：返回不匹配 state</button>
</div></form><small>授权码为一次性、短时效，并绑定 PKCE challenge 与 OIDC nonce。</small></main></body></html>`);
  }
  if (request.method === "POST" && url.pathname === "/approve") {
    const form = await readForm(request);
    const requestId = form.get("request_id") ?? "";
    const identityKey = form.get("identity") ?? "";
    const authorization = pending.get(requestId);
    const approval = identities[identityKey];
    pending.delete(requestId);
    if (!authorization || authorization.expiresAt <= Date.now() || !approval) {
      return sendText(response, 400, "Authorization approval expired or invalid\n");
    }
    const code = randomId();
    codes.set(code, {
      ...authorization,
      identity: approval.identity,
      nonce: approval.nonceMismatch ? randomId() : authorization.nonce,
      codeChallenge: approval.pkceMismatch ? randomId() : authorization.codeChallenge,
      expiresAt: Date.now() + codeLifetimeMs,
    });
    const target = new URL(redirectUri);
    target.searchParams.set("code", code);
    target.searchParams.set("state", approval.stateMismatch ? randomId() : authorization.state);
    return redirect(response, target.toString());
  }
  if (request.method === "POST" && url.pathname === "/token") {
    const form = await readForm(request);
    const code = form.get("code") ?? "";
    const record = codes.get(code);
    codes.delete(code);
    const verifier = form.get("code_verifier") ?? "";
    const challenge = createHash("sha256").update(verifier).digest("base64url");
    if (
      form.get("grant_type") !== "authorization_code"
      || form.get("client_id") !== clientId
      || !safeEqualText(form.get("client_secret") ?? "", clientSecret)
      || form.get("redirect_uri") !== redirectUri
      || !record || record.expiresAt <= Date.now()
      || !/^[A-Za-z0-9_-]{43,128}$/.test(verifier)
      || !safeEqualText(challenge, record.codeChallenge)
    ) {
      return sendJson(response, 400, { error: "invalid_grant" });
    }
    const accessToken = `e2e-at-${randomId()}`;
    issuedAccessTokens.set(accessToken, Date.now() + 600_000);
    return sendJson(response, 200, {
      token_type: "Bearer",
      access_token: accessToken,
      id_token: await issueIdToken(record),
      expires_in: 600,
    });
  }
  if (request.method === "POST" && url.pathname === "/revoke") {
    const form = await readForm(request);
    const token = form.get("token") ?? "";
    if (
      form.get("client_id") !== clientId
      || !safeEqualText(form.get("client_secret") ?? "", clientSecret)
      || !issuedAccessTokens.has(token)
    ) {
      return sendText(response, 400, "Invalid revocation request\n");
    }
    issuedAccessTokens.delete(token);
    response.writeHead(200, baseHeaders("text/plain; charset=utf-8"));
    return response.end();
  }
  if (url.pathname === "/api/v1/operations-observability/audit-events") {
    return proxyAudit(request, response);
  }
  return sendText(response, 404, "Not found\n");
}

const idpServer = https.createServer(tls, (request, response) => {
  handleIdp(request, response).catch(() => sendText(response, 500, "OIDC fixture failure\n"));
});

const proxyServer = https.createServer(tls, (request, response) => {
  if (request.method === "GET" && request.url === "/__elmos_e2e_oidc_health") {
    return sendJson(response, 200, { status: "ok", service: "tls-next-proxy" });
  }
  if (!request.url?.startsWith("/") || request.url.startsWith("//")) {
    return sendText(response, 400, "Invalid proxy target\n");
  }
  const externalHost = `127.0.0.1:${proxyPort}`;
  const headers = {
    ...request.headers,
    host: externalHost,
    "x-forwarded-host": externalHost,
    "x-forwarded-port": String(proxyPort),
    "x-forwarded-proto": "https",
  };
  delete headers.connection;
  const upstream = http.request({
    hostname: "127.0.0.1",
    port: upstreamPort,
    method: request.method,
    path: request.url,
    headers,
  }, (upstreamResponse) => {
    const responseHeaders = { ...upstreamResponse.headers };
    const location = responseHeaders.location;
    if (typeof location === "string") {
      responseHeaders.location = location.replace(
        `http://127.0.0.1:${upstreamPort}`,
        `https://${externalHost}`,
      );
    }
    response.writeHead(upstreamResponse.statusCode ?? 502, responseHeaders);
    upstreamResponse.pipe(response);
  });
  upstream.on("error", () => {
    if (!response.headersSent) sendText(response, 502, "Next production server unavailable\n");
    else response.destroy();
  });
  request.pipe(upstream);
});

// Playwright readiness must not disable TLS verification merely to poll the
// HTTPS facade. This server is loopback-only and exposes no application or IdP
// traffic; Chrome reaches the two HTTPS origins through their exact leaf-SPKI
// pin instead.
const healthServer = http.createServer((request, response) => {
  if (request.method === "GET" && request.url === "/health") {
    return sendJson(response, 200, { status: "ok", service: "production-oidc-harness" });
  }
  return sendText(response, 404, "Not found\n");
});

idpServer.listen(idpPort, idpListenHost);
proxyServer.listen(proxyPort, "127.0.0.1");
healthServer.listen(healthPort, "127.0.0.1");

function close() {
  idpServer.close();
  proxyServer.close();
  healthServer.close();
}

process.on("SIGINT", close);
process.on("SIGTERM", close);

import assert from "node:assert/strict";
import { randomBytes, scryptSync } from "node:crypto";
import { registerHooks } from "node:module";
import test from "node:test";
import { NextRequest } from "next/server.js";

registerHooks({ resolve(specifier, context, nextResolve) {
  return nextResolve(specifier === "next/server" ? "next/server.js" : specifier, context);
} });
const account = await import("../app/lib/server/accountSession.ts");
const { POST } = await import("../app/api/auth/admin/login/route.ts");
const { POST: userLogin } = await import("../app/api/auth/login/route.ts");
const { POST: logout } = await import("../app/api/auth/logout/route.ts");
const { authorizeAdmin } = await import("../app/lib/server/operationsProxy.ts");
const { requireRunnerFleetOidcAdmin } = await import("../app/lib/server/runnerFleetPolicy.ts");
const password = randomBytes(24).toString("hex");
const salt = randomBytes(16).toString("hex");
const environment = {
  NODE_ENV: "test", ELMOS_TEMP_ADMIN_ENABLED: "true",
  ELMOS_TEMP_ADMIN_PASSWORD_SALT: salt,
  ELMOS_TEMP_ADMIN_PASSWORD_HASH: scryptSync(password, Buffer.from(salt, "hex"), 64).toString("hex"),
  ELMOS_SESSION_SECRET: randomBytes(48).toString("hex"),
  ELMOS_PUBLIC_ORIGIN: "http://localhost:3000",
  ELMOS_ALLOW_LOCAL_CREDENTIALS: "true",
};
let saved;
test.beforeEach(() => {
  saved = { ...process.env };
  for (const key of Object.keys(process.env)) if (key.startsWith("ELMOS_")) delete process.env[key];
  Object.assign(process.env, environment);
});
test.afterEach(() => {
  for (const key of Object.keys(process.env)) if (!(key in saved)) delete process.env[key];
  Object.assign(process.env, saved);
});
function request(fields = {}, origin = "http://localhost:3000") {
  return new NextRequest("http://localhost:3000/api/auth/admin/login", {
    method: "POST", headers: { host: "localhost:3000", origin, "content-type": "application/json" },
    body: JSON.stringify({ username: account.ADMINISTRATOR_EMAIL, password, ...fields }),
  });
}
function sessionRequest(cookie) {
  return new Request("http://localhost:3000/api/admin/operations-console", {
    headers: { host: "localhost:3000", cookie },
  });
}
async function login() {
  const response = await POST(request());
  assert.equal(response.status, 200);
  const cookie = response.cookies.get(account.localAccountCookieNames.administratorSession);
  return { response, cookie: `${cookie.name}=${cookie.value}` };
}

test("password login yields a real admin session without claiming mailbox verification", async () => {
  const { response, cookie } = await login();
  const body = await response.json();
  assert.equal(body.principal.emailVerified, false);
  assert.equal(body.principal.isPlatformAdmin, true);
  const options = response.cookies.get(account.localAccountCookieNames.administratorSession);
  assert.equal(options.httpOnly, true);
  assert.equal(options.sameSite, "strict");
  assert.ok(options.maxAge > 0 && options.maxAge <= 3600);
  const session = account.accountSessionFromRequest(sessionRequest(cookie), "admin:read");
  assert.equal(session.principal.email, account.ADMINISTRATOR_EMAIL);
  assert.equal(session.accessToken, "");
  const admin = authorizeAdmin(sessionRequest(cookie));
  assert.equal(admin.authentication, "TEMPORARY_ADMIN_PASSWORD");
  assert.equal(admin.accessToken, undefined);
  assert.throws(() => requireRunnerFleetOidcAdmin(admin, "OPERATOR"), /企业账户/);
});

test("wrong password and wrong username cannot create a session", async () => {
  for (const fields of [{ password: "incorrect" }, { username: "other@example.test" }]) {
    const response = await POST(request(fields));
    assert.equal(response.status, 401);
    assert.equal(response.headers.get("set-cookie"), null);
  }
  await login(); // clear development throttle
});

test("disabled flag, rotated password, and production reject existing sessions", async () => {
  const { cookie } = await login();
  process.env.ELMOS_TEMP_ADMIN_ENABLED = "false";
  assert.throws(() => account.accountSessionFromRequest(sessionRequest(cookie)));
  process.env.ELMOS_TEMP_ADMIN_ENABLED = "true";
  process.env.ELMOS_TEMP_ADMIN_PASSWORD_HASH = "ab".repeat(64);
  assert.throws(() => account.accountSessionFromRequest(sessionRequest(cookie)));
  process.env.ELMOS_TEMP_ADMIN_PASSWORD_HASH = environment.ELMOS_TEMP_ADMIN_PASSWORD_HASH;
  process.env.NODE_ENV = "production";
  process.env.ELMOS_PUBLIC_ORIGIN = "https://console.example.test";
  assert.equal(account.temporaryAdministratorConfigured(), false);
  assert.equal((await POST(request({}, "https://console.example.test"))).status, 404);
  assert.throws(() => account.accountSessionFromRequest(sessionRequest(cookie)));
});

test("missing signing secret, foreign host, and cross-origin login fail closed", async () => {
  assert.equal((await POST(request({}, "https://evil.example"))).status, 403);
  const remote = new NextRequest("http://remote.example/api/auth/admin/login", {
    method: "POST", headers: { host: "remote.example", origin: "http://localhost:3000", "content-type": "application/json" },
    body: JSON.stringify({ username: account.ADMINISTRATOR_EMAIL, password }),
  });
  assert.equal((await POST(remote)).status, 403);
  delete process.env.ELMOS_SESSION_SECRET;
  assert.equal((await POST(request())).status, 404);
});

test("user login endpoint cannot use administrator bootstrap credentials", async () => {
  const response = await userLogin(request());
  assert.equal(response.status, 401);
  assert.equal(response.headers.get("set-cookie"), null);
  const userResponse = await userLogin(request({ username: "test", password: "test" }));
  assert.equal(userResponse.status, 200);
  assert.equal(userResponse.cookies.get(account.localAccountCookieNames.administratorSession).maxAge, 0);
  assert.equal((await userResponse.json()).principal.isPlatformAdmin, false);
});

test("form login constrains redirects to admin surfaces and logout clears bootstrap cookie", async () => {
  const response = await POST(new NextRequest("http://localhost:3000/api/auth/admin/login", {
    method: "POST", headers: { host: "localhost:3000", origin: "http://localhost:3000",
      "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: account.ADMINISTRATOR_EMAIL, password, returnTo: "https://evil.example" }),
  }));
  assert.equal(response.status, 303);
  assert.match(response.headers.get("location"), /^http:\/\/localhost:3000\//);
  const loggedOut = await logout(request());
  assert.equal(loggedOut.cookies.get(account.localAccountCookieNames.administratorSession).maxAge, 0);
});

test("malformed, oversized, and tampered requests do not establish authentication", async () => {
  assert.equal((await POST(request({ password: "x".repeat(17000) }))).status, 413);
  const malformed = new NextRequest("http://localhost:3000/api/auth/admin/login", {
    method: "POST", headers: { host: "localhost:3000", origin: "http://localhost:3000", "content-type": "application/json" }, body: "null",
  });
  assert.equal((await POST(malformed)).status, 400);
  const { cookie } = await login();
  assert.throws(() => account.accountSessionFromRequest(sessionRequest(`${cookie}tamper`)));
});

test("five wrong passwords lock the local administrator even for a correct password", async () => {
  await login();
  for (let attempt = 0; attempt < 5; attempt++) {
    assert.equal((await POST(request({ password: "incorrect" }))).status, 401);
  }
  assert.equal((await POST(request())).status, 429);
});

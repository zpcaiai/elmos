import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { liveWorkbenchRouteAllowed } from "../app/lib/server/liveWorkbenchRoutePolicy.ts";

test("browser BFF exposes only administrator workbench operations", () => {
  assert.equal(liveWorkbenchRouteAllowed(["sessions"], "POST"), true);
  assert.equal(liveWorkbenchRouteAllowed(["sessions", "session-a"], "GET"), true);
  assert.equal(liveWorkbenchRouteAllowed(["sessions", "session-a", "preview-access"], "GET"), true);
  assert.equal(liveWorkbenchRouteAllowed(["sessions", "session-a", "debug-commands"], "POST"), true);
  assert.equal(liveWorkbenchRouteAllowed(["sessions", "session-a", "terminate"], "POST"), true);
  assert.equal(liveWorkbenchRouteAllowed(["anchors", "anchor-a", "source"], "GET"), true);
  assert.equal(liveWorkbenchRouteAllowed(["missions", "mission-a", "attempts"], "POST"), true);
});

test("browser BFF requires administrator scope, OIDC and same-origin mutation", async () => {
  const route = await readFile(
    new URL("../app/api/live-workbench/[[...path]]/_route.ts", import.meta.url),
    "utf8",
  );
  assert.match(route, /authorizeAdmin\(request, request\.method === "GET" \? "VIEWER" : "OPERATOR"\)/);
  assert.match(route, /requireAdminMutationSameOrigin\(request\)/);
  assert.match(route, /LIVE_WORKBENCH_OIDC_SESSION_REQUIRED/);
  assert.doesNotMatch(route, /accountSessionFromRequest/);
});

test("browser BFF cannot commit readiness or forge runtime events", () => {
  assert.equal(liveWorkbenchRouteAllowed(["sessions", "session-a", "readiness"], "POST"), false);
  assert.equal(liveWorkbenchRouteAllowed(["sessions", "session-a", "events"], "POST"), false);
  assert.equal(liveWorkbenchRouteAllowed(["catalog", "deliveries"], "POST"), false);
  assert.equal(liveWorkbenchRouteAllowed(["sessions", "..", "terminate"], "POST"), false);
});

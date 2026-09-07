import assert from "node:assert/strict";
import test from "node:test";
import { liveWorkbenchRouteAllowed } from "../app/lib/server/liveWorkbenchRoutePolicy.ts";

test("browser BFF exposes only user workbench operations", () => {
  assert.equal(liveWorkbenchRouteAllowed(["sessions"], "POST"), true);
  assert.equal(liveWorkbenchRouteAllowed(["sessions", "session-a"], "GET"), true);
  assert.equal(liveWorkbenchRouteAllowed(["sessions", "session-a", "preview-access"], "GET"), true);
  assert.equal(liveWorkbenchRouteAllowed(["sessions", "session-a", "debug-commands"], "POST"), true);
  assert.equal(liveWorkbenchRouteAllowed(["sessions", "session-a", "terminate"], "POST"), true);
  assert.equal(liveWorkbenchRouteAllowed(["anchors", "anchor-a", "source"], "GET"), true);
  assert.equal(liveWorkbenchRouteAllowed(["missions", "mission-a", "attempts"], "POST"), true);
});

test("browser BFF cannot commit readiness or forge runtime events", () => {
  assert.equal(liveWorkbenchRouteAllowed(["sessions", "session-a", "readiness"], "POST"), false);
  assert.equal(liveWorkbenchRouteAllowed(["sessions", "session-a", "events"], "POST"), false);
  assert.equal(liveWorkbenchRouteAllowed(["catalog", "deliveries"], "POST"), false);
  assert.equal(liveWorkbenchRouteAllowed(["sessions", "..", "terminate"], "POST"), false);
});

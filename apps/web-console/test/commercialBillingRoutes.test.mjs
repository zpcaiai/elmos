import assert from "node:assert/strict";
import test from "node:test";
import { NextRequest } from "next/server";

import { POST as buyCredits } from "../app/api/billing/orders/credit-packs/_route.ts";
import { POST as buyProject } from "../app/api/billing/orders/project-generations/_route.ts";
import { GET as usageEvents } from "../app/api/usage/events/_route.ts";

function jsonRequest(path, body, key = "billing-test-key") {
  return new NextRequest(`http://localhost${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", "idempotency-key": key },
    body: JSON.stringify(body),
  });
}

test("Credit order rejects client-selected products and malformed idempotency", async () => {
  const wrongSku = await buyCredits(jsonRequest(
    "/api/billing/orders/credit-packs", { sku: "client-price-1" },
  ));
  assert.equal(wrongSku.status, 400);
  assert.equal((await wrongSku.json()).code, "COMMERCIAL_ORDER_REQUEST_INVALID");

  const shortKey = await buyCredits(jsonRequest(
    "/api/billing/orders/credit-packs", { sku: "elmos-credit-500" }, "short",
  ));
  assert.equal(shortKey.status, 400);
});

test("one-time generation order requires an exact safe project identity", async () => {
  for (const projectId of ["", "../other-project", "project/child", "空项目"]) {
    const response = await buyProject(jsonRequest(
      "/api/billing/orders/project-generations",
      { sku: "elmos-project-generation-once", projectId, amountFen: 1 },
    ));
    assert.equal(response.status, 400);
    assert.equal((await response.json()).code, "COMMERCIAL_ORDER_REQUEST_INVALID");
  }
});

test("raw usage history rejects invalid time windows before proxying", async () => {
  const response = await usageEvents(new NextRequest(
    "http://localhost/api/usage/events?from=not-a-date&to=also-bad&scope=SELF",
  ));
  assert.equal(response.status, 400);
  assert.equal((await response.json()).code, "USAGE_EVENTS_QUERY_INVALID");
});

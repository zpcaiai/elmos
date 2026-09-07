import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const schedulerClaim = new Trend("elmos_scheduler_claim_ms", true);
const billingCycle = new Trend("elmos_billing_reserve_settle_ms", true);
const projectionFreshness = new Trend("elmos_projection_freshness_ms", true);
const gateFailures = new Rate("elmos_gate_failures");

export const options = {
  discardResponseBodies: false,
  thresholds: {
    "http_req_failed": ["rate<0.01"],
    "http_req_duration{scenario:scheduler_claim}": ["p(95)<100"],
    "http_req_duration{scenario:billing_cycle}": ["p(95)<150"],
    "elmos_scheduler_claim_ms": ["p(95)<100"],
    "elmos_billing_reserve_settle_ms": ["p(95)<150"],
    "elmos_projection_freshness_ms": ["p(95)<2000"],
    "elmos_gate_failures": ["rate==0"],
  },
};

function required(name) {
  const value = __ENV[name];
  if (!value) throw new Error(`${name} is required`);
  return value.replace(/\/$/, "");
}

function parse(response, scenario) {
  let body;
  try {
    body = response.json();
  } catch (_) {
    gateFailures.add(1, { scenario });
    return null;
  }
  const passed = check(response, {
    [`${scenario} returned HTTP 2xx`]: (value) => value.status >= 200 && value.status < 300,
    [`${scenario} returned PASS`]: () => body.status === "PASS",
  });
  gateFailures.add(passed ? 0 : 1, { scenario });
  return body;
}

export default function () {
  const schedulerUrl = required("ELMOS_RUNTIME_SCHEDULER_BASE_URL");
  const billingUrl = required("ELMOS_RUNTIME_BILLING_BASE_URL");
  const token = required("ELMOS_RUNTIME_GATE_TOKEN");
  const runId = required("ELMOS_GATE_RUN_ID");
  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };

  let response = http.get(
    `${schedulerUrl}/internal/v1/production-runtime/gate/scheduler-frontier?limit=64`,
    { headers, tags: { scenario: "scheduler_claim" } },
  );
  let body = parse(response, "scheduler_claim");
  if (body) schedulerClaim.add(body.claimLatencyMs);

  const key = `${runId}:${__VU}:${__ITER}:${Date.now()}`;
  response = http.post(
    `${billingUrl}/internal/v1/production-runtime/gate/billing-cycle`,
    JSON.stringify({ idempotencyKey: key }),
    { headers, tags: { scenario: "billing_cycle" } },
  );
  body = parse(response, "billing_cycle");
  if (body) billingCycle.add(body.reserveSettleLatencyMs);

  response = http.get(
    `${schedulerUrl}/internal/v1/production-runtime/gate/projection-freshness`,
    { headers, tags: { scenario: "projection_freshness" } },
  );
  body = parse(response, "projection_freshness");
  if (body) projectionFreshness.add(body.freshnessMs);

  response = http.get(
    `${schedulerUrl}/internal/v1/production-runtime/gate/invariants`,
    { headers, tags: { scenario: "runtime_invariants" } },
  );
  parse(response, "runtime_invariants");
  sleep(0.2);
}

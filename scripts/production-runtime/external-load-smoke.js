import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  discardResponseBodies: true,
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<2000"],
  },
};

export default function () {
  const baseUrl = __ENV.ELMOS_RUNTIME_BASE_URL;
  if (!baseUrl) {
    throw new Error("ELMOS_RUNTIME_BASE_URL is required");
  }
  const response = http.get(`${baseUrl.replace(/\/$/, "")}/actuator/health/readiness`, {
    tags: { scenario: "production-runtime-readiness" },
  });
  check(response, {
    "readiness endpoint is healthy": (value) => value.status === 200,
  });
  sleep(1);
}

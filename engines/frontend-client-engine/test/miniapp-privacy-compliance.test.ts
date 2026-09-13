import assert from "node:assert/strict";
import test from "node:test";

import { auditMiniappPrivacy } from "../src/miniapp-planning.js";
import { runMiniappConversion } from "../src/miniapp-skill-runtime.js";
import { conversionInput, vueTodoFiles } from "./miniapp-test-fixture.js";

test("privacy audit fails forbidden dynamic code and remote scripts closed", () => {
  const files = [
    ...vueTodoFiles,
    {
      path: "src/unsafe.html",
      content: '<script src="https://cdn.example.invalid/runtime.js"></script><script>eval("1")</script>',
    },
  ];
  const run = runMiniappConversion(conversionInput(files));
  const sources = Object.fromEntries(files.map(file => [file.path, String(file.content)]));
  const audits = auditMiniappPrivacy(run.semanticIr, run.request, sources);

  assert.ok(audits.every(audit => audit.verdict === "failed"));
  assert.ok(audits.every(audit => audit.findings.includes("MINIAPP_DYNAMIC_CODE_FORBIDDEN:src/unsafe.html")));
  assert.ok(audits.every(audit => audit.findings.includes("MINIAPP_REMOTE_SCRIPT_FORBIDDEN:src/unsafe.html")));
  assert.ok(audits.every(audit => audit.platformReview === "NOT_RUN"));
});

test("sensitive capabilities require an exact per-platform privacy authorization aspect", () => {
  const run = runMiniappConversion(conversionInput());
  const ir = {
    ...run.semanticIr,
    capabilities: [{
      id: "cap-location",
      name: "location.get",
      category: "location",
      sensitive: true,
      sourceRefs: run.semanticIr.nodes[0]!.sourceRefs,
    }],
  };
  const audits = auditMiniappPrivacy(ir, run.request, Object.fromEntries(vueTodoFiles.map(file => [file.path, String(file.content)])));

  for (const audit of audits) {
    assert.equal(audit.verdict, "blocked");
    assert.ok(audit.findings.includes(`MINIAPP_PRIVACY_AUTHORIZATION_ASPECT_REQUIRED:${audit.platform}`));
    assert.ok(audit.findings.includes("PLATFORM_PERMISSION_AND_DISCLOSURE_EXTERNAL_REVIEW_NOT_RUN"));
  }
});

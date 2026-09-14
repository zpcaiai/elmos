import assert from "node:assert/strict";
import test from "node:test";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { auditMiniappCompliance } from "../src/miniapp-compliance-auditor.js";

test("miniapp-compliance: flags eval and Function constructor as blocking", () => {
  const tempDir = join(tmpdir(), `miniapp-compliance-test-${Date.now()}`);
  mkdirSync(tempDir, { recursive: true });

  writeFileSync(
    join(tempDir, "unsafe.js"),
    `
    function runDynamic(code) {
      return eval(code);
    }
    const fn = new Function("a", "return a * 2");
    `
  );

  try {
    const report = auditMiniappCompliance(tempDir, "wechat");
    assert.equal(report.passed, false);
    assert.equal(report.blockingFindingsCount, 2);
    assert.ok(report.findings.some(f => f.ruleId === "NO_DYNAMIC_EVAL"));
    assert.ok(report.findings.some(f => f.ruleId === "NO_FUNCTION_CONSTRUCTOR"));
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

test("miniapp-compliance: detects sensitive APIs and generates WeChat privacy authorization shim", () => {
  const tempDir = join(tmpdir(), `miniapp-compliance-privacy-${Date.now()}`);
  mkdirSync(tempDir, { recursive: true });

  writeFileSync(
    join(tempDir, "location.js"),
    `
    export function fetchCoords() {
      wx.getLocation({
        type: 'wgs84',
        success(res) { console.log(res); }
      });
      wx.getClipboardData({
        success(res) { console.log(res.data); }
      });
    }
    `
  );

  try {
    const report = auditMiniappCompliance(tempDir, "wechat");
    assert.equal(report.passed, true); // Sensitive APIs alone are warnings with recommended shims, not blocking
    assert.ok(report.findings.some(f => f.ruleId === "WECHAT_PRIVACY_AUTHORIZATION_REQUIRED"));
    assert.equal(report.recommendedShims.length, 1);
    assert.ok(report.recommendedShims[0]!.content.includes("wx.onNeedPrivacyAuthorization"));
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

test("miniapp-compliance: warns on iOS virtual payment keyword proximity", () => {
  const tempDir = join(tmpdir(), `miniapp-compliance-pay-${Date.now()}`);
  mkdirSync(tempDir, { recursive: true });

  writeFileSync(
    join(tempDir, "pay.js"),
    `
    // VIP Membership Recharge
    export function buyVipSubscription() {
      wx.requestPayment({
        timeStamp: '123',
        nonceStr: 'abc',
        package: 'prepay_id=123',
        signType: 'RSA',
        paySign: 'xyz',
      });
    }
    `
  );

  try {
    const report = auditMiniappCompliance(tempDir, "wechat");
    assert.ok(report.findings.some(f => f.ruleId === "IOS_VIRTUAL_PAYMENT_RISK"));
    assert.equal(report.blockingFindingsCount, 0); // Warning, not hard-blocking
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

import assert from "node:assert/strict";
import test from "node:test";
import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";

const CLI_PATH = resolve("dist/src/miniapp-cli.js");

test("miniapp-cli: catalog command outputs skill catalog", () => {
  const stdout = execFileSync("node", [CLI_PATH, "catalog"], { encoding: "utf8" });
  const result = JSON.parse(stdout);
  assert.equal(result.schemaVersion, "1.0");
  assert.ok(Array.isArray(result.skills));
  assert.ok(result.skills.some((s: any) => s.name === "frontend-to-miniapp-orchestrator"));
});

test("miniapp-cli: audit command inspects directory compliance and outputs report", () => {
  const tempDir = join(tmpdir(), `miniapp-cli-audit-${Date.now()}`);
  mkdirSync(tempDir, { recursive: true });

  writeFileSync(
    join(tempDir, "sample.js"),
    `
    export function executeCode(code) {
      return eval(code);
    }
    `
  );

  try {
    const stdout = execFileSync(
      "node",
      [CLI_PATH, "audit", "--dir", tempDir, "--platform", "wechat"],
      { encoding: "utf8" }
    );
    const result = JSON.parse(stdout);
    assert.equal(result.schemaVersion, "1.0");
    assert.ok(result.report);
    assert.equal(result.report.platform, "wechat");
    assert.equal(result.report.passed, false);
    assert.equal(result.report.blockingFindingsCount, 1);
    assert.ok(result.report.findings.some((f: any) => f.ruleId === "NO_DYNAMIC_EVAL"));
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

test("miniapp-cli: toolchain command supports dry-run build & analyze across platforms", () => {
  const tempDir = join(tmpdir(), `miniapp-cli-toolchain-${Date.now()}`);
  mkdirSync(tempDir, { recursive: true });

  writeFileSync(
    join(tempDir, "app.json"),
    JSON.stringify({ pages: ["pages/index/index"] }, null, 2)
  );
  writeFileSync(join(tempDir, "project.config.json"), "{}");
  mkdirSync(join(tempDir, "pages", "index"), { recursive: true });
  writeFileSync(join(tempDir, "pages", "index", "index.ttml"), "<view>Hello Douyin</view>");
  writeFileSync(join(tempDir, "pages", "index", "index.ttss"), "view { color: #333; }");
  writeFileSync(join(tempDir, "pages", "index", "index.js"), "Page({});");

  try {
    // 1. Douyin dry-run build with token provided
    const douyinWithTokenStdout = execFileSync(
      "node",
      [
        CLI_PATH,
        "toolchain",
        "--dir",
        tempDir,
        "--platform",
        "douyin",
        "--action",
        "build",
        "--private-key",
        "mock_douyin_token",
        "--dry-run",
      ],
      { encoding: "utf8" }
    );
    const douyinWithTokenResult = JSON.parse(douyinWithTokenStdout);
    assert.equal(douyinWithTokenResult.schemaVersion, "1.0");
    assert.ok(douyinWithTokenResult.toolchainResult);
    assert.equal(douyinWithTokenResult.toolchainResult.platform, "douyin");
    assert.equal(douyinWithTokenResult.toolchainResult.action, "build");
    assert.equal(douyinWithTokenResult.toolchainResult.status, "PASSED");
    assert.ok(douyinWithTokenResult.toolchainResult.command.includes("[REDACTED_TOKEN]"));

    // 2. Douyin dry-run build without token (fail-closed credential check)
    const douyinNoTokenStdout = execFileSync(
      "node",
      [
        CLI_PATH,
        "toolchain",
        "--dir",
        tempDir,
        "--platform",
        "douyin",
        "--action",
        "build",
        "--dry-run",
      ],
      { encoding: "utf8" }
    );
    const douyinNoTokenResult = JSON.parse(douyinNoTokenStdout);
    assert.equal(douyinNoTokenResult.toolchainResult.status, "CREDENTIAL_REQUIRED");

    // 3. WeChat analyze action (requires no credentials)
    const wechatStdout = execFileSync(
      "node",
      [
        CLI_PATH,
        "toolchain",
        "--dir",
        tempDir,
        "--platform",
        "wechat",
        "--action",
        "analyze",
        "--dry-run",
      ],
      { encoding: "utf8" }
    );
    const wechatResult = JSON.parse(wechatStdout);
    assert.equal(wechatResult.schemaVersion, "1.0");
    assert.ok(wechatResult.toolchainResult);
    assert.equal(wechatResult.toolchainResult.platform, "wechat");
    assert.equal(wechatResult.toolchainResult.action, "analyze");
    assert.equal(wechatResult.toolchainResult.status, "PASSED");
    assert.ok(wechatResult.toolchainResult.bundleMetrics);
    assert.ok(wechatResult.toolchainResult.bundleMetrics.fileCount >= 4);

    // 4. WeChat preview action with private key provided
    const wechatPreviewStdout = execFileSync(
      "node",
      [
        CLI_PATH,
        "toolchain",
        "--dir",
        tempDir,
        "--platform",
        "wechat",
        "--action",
        "preview",
        "--private-key",
        "mock_private_key_path",
        "--dry-run",
      ],
      { encoding: "utf8" }
    );
    const wechatPreviewResult = JSON.parse(wechatPreviewStdout);
    assert.equal(wechatPreviewResult.schemaVersion, "1.0");
    assert.ok(wechatPreviewResult.toolchainResult);
    assert.equal(wechatPreviewResult.toolchainResult.platform, "wechat");
    assert.equal(wechatPreviewResult.toolchainResult.action, "preview");
    assert.equal(wechatPreviewResult.toolchainResult.status, "PASSED");
    assert.ok(wechatPreviewResult.toolchainResult.command.includes("miniprogram-ci preview"));

    // 5. Alipay preview action without toolId (fail-closed check)
    const alipayStdout = execFileSync(
      "node",
      [
        CLI_PATH,
        "toolchain",
        "--dir",
        tempDir,
        "--platform",
        "alipay",
        "--action",
        "preview",
        "--private-key",
        "mock_private_key",
        "--dry-run",
      ],
      { encoding: "utf8" }
    );
    const alipayResult = JSON.parse(alipayStdout);
    assert.equal(alipayResult.schemaVersion, "1.0");
    assert.ok(alipayResult.toolchainResult);
    assert.equal(alipayResult.toolchainResult.platform, "alipay");
    assert.equal(alipayResult.toolchainResult.status, "CREDENTIAL_REQUIRED");
    assert.ok(alipayResult.toolchainResult.command.includes("minidev preview"));
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

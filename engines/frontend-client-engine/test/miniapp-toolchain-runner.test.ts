import assert from "node:assert/strict";
import test from "node:test";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import {
  analyzeMiniappBundle,
  buildToolchainCliCommand,
  executeMiniappToolchain,
  type WechatCiConfig,
  type AlipayMinidevConfig,
  type DouyinCiConfig,
} from "../src/miniapp-toolchain-runner.js";

test("miniapp-toolchain: bundle size and subpackage metrics analyzer", () => {
  const tempDir = join(tmpdir(), `miniapp-test-bundle-${Date.now()}`);
  mkdirSync(tempDir, { recursive: true });
  mkdirSync(join(tempDir, "pages", "index"), { recursive: true });
  mkdirSync(join(tempDir, "subpkg", "detail"), { recursive: true });

  writeFileSync(
    join(tempDir, "app.json"),
    JSON.stringify({
      pages: ["pages/index/index"],
      subpackages: [
        {
          root: "subpkg",
          pages: ["detail/detail"],
        },
      ],
    })
  );

  writeFileSync(join(tempDir, "pages", "index", "index.wxml"), "<view>Main</view>");
  writeFileSync(join(tempDir, "subpkg", "detail", "detail.wxml"), "<view>Subpackage Detail</view>");
  writeFileSync(join(tempDir, "logo.png"), Buffer.alloc(1024)); // 1KB asset

  try {
    const metrics = analyzeMiniappBundle(tempDir);
    assert.equal(metrics.fileCount, 4);
    assert.ok(metrics.totalBytes > 1024);
    assert.equal(metrics.assetBytes, 1024);
    assert.ok(metrics.mainPackageBytes > 0);
    assert.ok((metrics.subpackageBytes["subpkg"] ?? 0) > 0);
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

test("miniapp-toolchain: CLI command builder handles platforms and redacts secrets", () => {
  const wechatReq = {
    action: "upload" as const,
    config: {
      platform: "wechat" as const,
      appid: "wx1234567890abcdef",
      projectPath: "/workspace/wx-app",
      privateKeyPath: "/secrets/private.key",
      version: "1.2.0",
      desc: "Test upload",
    },
  };
  const wxResult = buildToolchainCliCommand(wechatReq);
  assert.equal(wxResult.cmd, "miniprogram-ci");
  assert.ok(wxResult.args.includes("--appid"));
  assert.ok(wxResult.args.includes("wx1234567890abcdef"));
  assert.ok(wxResult.args.includes("--pkp"));
  assert.equal(wxResult.missingCredentials.length, 0);

  const alipayReq = {
    action: "preview" as const,
    config: {
      platform: "alipay" as const,
      appid: "2021000000000000",
      projectPath: "/workspace/alipay-app",
      toolId: "tool-test-id",
      privateKeyPath: "/secrets/alipay.key",
    },
  };
  const aliResult = buildToolchainCliCommand(alipayReq);
  assert.equal(aliResult.cmd, "minidev");
  assert.ok(aliResult.args.includes("--app-id"));
  assert.equal(aliResult.missingCredentials.length, 0);

  const douyinReq = {
    action: "upload" as const,
    config: {
      platform: "douyin" as const,
      appid: "tt0000000000000000",
      projectPath: "/workspace/tt-app",
      token: "secret-token-value",
      version: "2.0.0",
    },
  };
  const dyResult = buildToolchainCliCommand(douyinReq);
  assert.equal(dyResult.cmd, "tt");
  assert.ok(dyResult.displayCommand.includes("[REDACTED_TOKEN]"));
  assert.doesNotMatch(dyResult.displayCommand, /secret-token-value/);
});

test("miniapp-toolchain: dry-run mode computes metrics without executing system commands", async () => {
  const tempDir = join(tmpdir(), `miniapp-test-dryrun-${Date.now()}`);
  mkdirSync(tempDir, { recursive: true });
  writeFileSync(join(tempDir, "app.json"), "{}");
  writeFileSync(join(tempDir, "app.js"), "App({})");

  try {
    const config: WechatCiConfig = {
      platform: "wechat",
      appid: "wx9999999999999999",
      projectPath: tempDir,
      privateKeyPath: "/dev/null",
      version: "1.0.1",
    };

    const result = await executeMiniappToolchain({
      action: "upload",
      config,
      dryRun: true,
    });

    assert.equal(result.platform, "wechat");
    assert.equal(result.action, "upload");
    assert.equal(result.status, "PASSED");
    assert.equal(result.exitCode, 0);
    assert.ok(result.bundleMetrics);
    assert.ok(result.stdout.includes("[DRY_RUN]"));
    assert.equal(result.uploadedVersion, "1.0.1");
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

test("miniapp-toolchain: missing credentials fail closed and require real configuration", async () => {
  const tempDir = join(tmpdir(), `miniapp-test-nocred-${Date.now()}`);
  mkdirSync(tempDir, { recursive: true });
  writeFileSync(join(tempDir, "app.json"), "{}");

  try {
    const config: WechatCiConfig = {
      platform: "wechat",
      appid: "wx9999999999999999",
      projectPath: tempDir,
      // privateKeyPath intentionally omitted
    };

    // 1. Dry run highlights missing credentials
    const dryRunRes = await executeMiniappToolchain({
      action: "upload",
      config,
      dryRun: true,
    });
    assert.equal(dryRunRes.status, "CREDENTIAL_REQUIRED");
    assert.ok(dryRunRes.errors.some(e => e.includes("privateKeyPath")));

    // 2. Real run fails closed without credentials
    const realRes = await executeMiniappToolchain({
      action: "upload",
      config,
      dryRun: false,
    });
    assert.equal(realRes.status, "CREDENTIAL_REQUIRED");
    assert.equal(realRes.exitCode, 2);
    assert.ok(realRes.stderr.includes("Non-self-certification contract prohibits faking credentials"));
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

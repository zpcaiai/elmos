import { defineConfig } from "@playwright/test";
import path from "node:path";

import baseConfig from "./playwright.config";

const approvedVisualRoot = path.resolve(
  __dirname,
  "../../client-packs/frt-g01-g30-platform/visual-baselines/approved",
);

export default defineConfig({
  ...baseConfig,
  // 基础配置把本 spec 排除在默认跑之外；这里是它唯一被授权执行的入口，必须解除继承来的排除。
  testIgnore: undefined,
  testMatch: /frt-external-quality\.spec\.ts/,
  outputDir: "./test-results/frt-external-quality",
  reporter: [
    ["list"],
    ["json", { outputFile: "./test-results/frt-external-quality/results.json" }],
    ["html", { outputFolder: "./test-results/frt-external-quality-report", open: "never" }],
  ],
  // A failed comparison may never create or replace an approved baseline.
  updateSnapshots: "none",
  snapshotPathTemplate: path.join(
    approvedVisualRoot,
    "{projectName}",
    "{testFilePath}",
    "{arg}{ext}",
  ),
  expect: {
    ...baseConfig.expect,
    toHaveScreenshot: {
      animations: "disabled",
      maxDiffPixels: 0,
      threshold: 0,
    },
  },
});

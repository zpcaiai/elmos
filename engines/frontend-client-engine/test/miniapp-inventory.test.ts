import { createHash } from "node:crypto";
import assert from "node:assert/strict";
import test from "node:test";

import {
  canonicalizeMiniappSourceInventory,
  inventoryMiniappSource,
  MiniappInventoryError,
} from "../src/miniapp-inventory.js";

const snapshotDigest = `sha256:${"c".repeat(64)}`;

function inventoryInput(files: readonly Readonly<Record<string, unknown>>[]): Record<string, unknown> {
  return {
    schemaVersion: "1.0",
    inventoryId: "inv-miniapp-001",
    sourceRevision: "0123456789abcdef",
    sourceSnapshotDigest: snapshotDigest,
    sourceLabelHint: "auto",
    limits: {
      maxFileCount: 100,
      maxFileBytes: 1024 * 1024,
      maxTotalBytes: 4 * 1024 * 1024,
    },
    files,
  };
}

const reactFiles = [
  {
    path: "package.json",
    content: JSON.stringify({
      name: "safe-react-app",
      scripts: { build: "vite build", postinstall: "node ./untrusted-hook.js" },
      dependencies: { react: "19.2.7", "react-dom": "19.2.7" },
      devDependencies: { typescript: "5.9.2" },
    }),
  },
  { path: "tsconfig.json", content: JSON.stringify({ compilerOptions: { strict: true } }) },
  { path: "src/App.tsx", content: "import React from 'react'; export const App = () => <main>Hello</main>;" },
  { path: "src/main.tsx", content: "import { App } from './App.js'; void App;" },
] as const;

test("the in-memory scanner fingerprints files, dependencies, entrypoints, and coverage without running scripts", () => {
  const inventory = inventoryMiniappSource(inventoryInput(reactFiles));
  assert.equal(inventory.selectedSourceLabel, "react");
  assert.deepEqual(inventory.frameworkConflicts, []);
  assert.equal(inventory.coverage.totalFiles, 4);
  assert.equal(inventory.coverage.processedFiles, 4);
  assert.equal(inventory.coverage.ratio, 1);
  assert.ok(inventory.entrypoints.includes("src/main.tsx"));
  assert.ok(inventory.components.includes("src/App.tsx"));
  assert.ok(inventory.dependencies.some(item => item.name === "react" && item.version === "19.2.7"));
  const packageEvidence = inventory.configurationEvidence.find(item => item.kind === "package-json")!;
  assert.equal(packageEvidence.parsed, true);
  assert.ok(packageEvidence.signals.includes("scripts-declared-not-executed:build,postinstall"));
  const tsconfigEvidence = inventory.configurationEvidence.find(item => item.kind === "tsconfig")!;
  assert.equal(tsconfigEvidence.parsed, true);
  assert.ok(tsconfigEvidence.signals.includes("compiler-options:strict"));
  const expectedDigest = `sha256:${createHash("sha256").update(reactFiles[0].content).digest("hex")}`;
  assert.equal(inventory.files.find(file => file.path === "package.json")?.digest, expectedDigest);
});

test("tsconfig and npmrc are parsed as digest-bound build configuration without executing lifecycle scripts", () => {
  const inventory = inventoryMiniappSource(inventoryInput([
    ...reactFiles,
    { path: ".npmrc", content: "auto-install-peers=false\nignore-scripts=true\n" },
    { path: "vite.config.ts", content: 'import { defineConfig } from "vite"; export default defineConfig({ plugins: [] });' },
  ]));
  assert.deepEqual(inventory.findings, []);
  const npmrc = inventory.configurationEvidence.find(item => item.kind === "npmrc");
  assert.equal(npmrc?.parsed, true);
  assert.ok(npmrc?.signals.includes("key:auto-install-peers"));
  assert.ok(npmrc?.signals.includes("lifecycle-scripts:disabled"));
  assert.equal(inventory.configurationEvidence.find(item => item.kind === "tsconfig")?.parsed, true);
  const vite = inventory.configurationEvidence.find(item => item.kind === "vite-config");
  assert.equal(vite?.parsed, true);
  assert.match(vite?.digest ?? "", /^sha256:[a-f0-9]{64}$/u);
  assert.ok(vite?.signals.includes("define-config-call:direct-object"));
  assert.ok(vite?.signals.includes("plugin-import:@vitejs/plugin-vue:absent"));

  const duplicate = [...reactFiles, { path: ".npmrc", content: "ignore-scripts=true\nignore-scripts=false\n" }];
  const invalid = inventoryMiniappSource(inventoryInput(duplicate));
  assert.ok(invalid.findings.some(item => item.code === "MINIAPP_CONFIG_PARSE_ERROR" && item.paths.includes(".npmrc")));

  assert.throws(
    () => inventoryMiniappSource(inventoryInput([...reactFiles, { path: ".npmrc", content: "auth-token=raw-secret-value\n" }])),
    (error: unknown) => error instanceof MiniappInventoryError && error.code === "MINIAPP_UNSAFE_SECRET_VALUE",
  );
  const referenceOnly = inventoryMiniappSource(inventoryInput([
    ...reactFiles,
    { path: ".npmrc", content: "auth-token=vault://tenant/npm-token\n" },
  ]));
  assert.equal(referenceOnly.configurationEvidence.find(item => item.kind === "npmrc")?.parsed, true);
});

test("inventory output and its canonical form are deterministic for reordered input", () => {
  const forward = inventoryMiniappSource(inventoryInput(reactFiles));
  const reverse = inventoryMiniappSource(inventoryInput([...reactFiles].reverse()));
  assert.deepEqual(forward, reverse);
  assert.equal(canonicalizeMiniappSourceInventory(forward), canonicalizeMiniappSourceInventory(reverse));
  assert.deepEqual(forward.files.map(file => file.path), ["package.json", "src/App.tsx", "src/main.tsx", "tsconfig.json"]);
});

test("package.json, pubspec.yaml, and native app configuration all produce typed evidence", () => {
  const inventory = inventoryMiniappSource(inventoryInput([
    {
      path: "package.json",
      content: JSON.stringify({ dependencies: { react: "19.2.7" } }),
    },
    {
      path: "flutter/pubspec.yaml",
      content: "name: dashboard\ndependencies:\n  flutter:\n    sdk: flutter\n  provider: 6.1.5\n",
    },
    {
      path: "miniapp/app.json",
      content: JSON.stringify({ pages: ["pages/index/index"], window: { navigationBarTitleText: "Demo" } }),
    },
  ]));
  assert.deepEqual(new Set(inventory.configurationEvidence.map(item => item.kind)),
    new Set(["package-json", "pubspec", "app-config"]));
  assert.ok(inventory.frameworkCandidates.some(item => item.sourceLabel === "flutter" && item.confidence >= 0.9));
  assert.ok(inventory.frameworkCandidates.some(item => item.sourceLabel === "native-miniapp" && item.confidence >= 0.8));
  assert.equal(inventory.selectedSourceLabel, null);
  assert.ok(inventory.findings.some(item => item.code === "MINIAPP_FRAMEWORK_CONFLICT" && item.blocking));
});

test("package-lock resolutions are byte-bound typed evidence, not inferred installed runtimes", () => {
  const lockContent = JSON.stringify({
    name: "locked-react",
    lockfileVersion: 3,
    packages: {
      "": { dependencies: { react: "19.2.7" } },
      "node_modules/react": { version: "19.2.7" },
      "node_modules/parent/node_modules/transitive": { version: "1.0.0" },
    },
  });
  const inventory = inventoryMiniappSource(inventoryInput([
    { path: "package.json", content: JSON.stringify({ dependencies: { react: "19.2.7" } }) },
    { path: "package-lock.json", content: lockContent },
    { path: "src/App.tsx", content: "import React from 'react'; export function App(){ return <main>Locked</main>; }" },
  ]));
  assert.deepEqual(inventory.lockedDependencies, [{
    name: "react",
    version: "19.2.7",
    sourcePath: "package-lock.json",
    sourceDigest: `sha256:${createHash("sha256").update(lockContent).digest("hex")}`,
    packageManager: "npm",
  }]);
  assert.ok(inventory.configurationEvidence.some(item => item.kind === "package-lock" && item.parsed));
});

test("pnpm importer resolutions are parsed as byte-bound typed evidence", () => {
  const lockContent = [
    "lockfileVersion: '9.0'",
    "",
    "importers:",
    "  .:",
    "    dependencies:",
    "      vue:",
    "        specifier: 3.5.39",
    "        version: 3.5.39",
    "    devDependencies:",
    "      typescript:",
    "        specifier: 5.9.2",
    "        version: 5.9.2",
    "      vite:",
    "        specifier: 6.0.0",
    "        version: 6.0.0",
    "packages:",
    "  vue@3.5.39:",
    "    resolution: {}",
  ].join("\n");
  const inventory = inventoryMiniappSource(inventoryInput([
    { path: "package.json", content: JSON.stringify({ dependencies: { vue: "3.5.39" }, devDependencies: { typescript: "5.9.2", vite: "6.0.0" } }) },
    { path: "pnpm-lock.yaml", content: lockContent },
    { path: "src/App.vue", content: "<template><main>Locked</main></template>" },
  ]));
  assert.deepEqual(inventory.lockedDependencies, [
    { name: "vite", version: "6.0.0", sourcePath: "pnpm-lock.yaml", sourceDigest: `sha256:${createHash("sha256").update(lockContent).digest("hex")}`, packageManager: "pnpm" },
    { name: "typescript", version: "5.9.2", sourcePath: "pnpm-lock.yaml", sourceDigest: `sha256:${createHash("sha256").update(lockContent).digest("hex")}`, packageManager: "pnpm" },
    { name: "vue", version: "3.5.39", sourcePath: "pnpm-lock.yaml", sourceDigest: `sha256:${createHash("sha256").update(lockContent).digest("hex")}`, packageManager: "pnpm" },
  ].sort((left, right) => `${left.name}\u0000${left.version}`.localeCompare(`${right.name}\u0000${right.version}`)));
  assert.ok(inventory.configurationEvidence.some(item => item.kind === "pnpm-lock" && item.parsed));
});

test("strong React and Vue evidence is retained as a blocking multi-framework conflict", () => {
  const inventory = inventoryMiniappSource(inventoryInput([
    {
      path: "package.json",
      content: JSON.stringify({ dependencies: { react: "19.2.7", vue: "3.5.39" } }),
    },
    { path: "src/App.tsx", content: "import React from 'react'; export const App = () => null;" },
    { path: "src/Legacy.vue", content: "<template><main>legacy</main></template>" },
  ]));
  assert.equal(inventory.selectedSourceLabel, null);
  assert.ok(inventory.frameworkConflicts.some(conflict =>
    conflict.sourceLabels.includes("react") && conflict.sourceLabels.includes("vue3")));
  assert.ok(inventory.frameworkCandidates.every(candidate => candidate.evidence.length > 0));
});

test("an exact Vue major manifest suppresses generic sibling-major SFC signals", () => {
  const input = inventoryInput([
    { path: "package.json", content: JSON.stringify({ dependencies: { vue: "^3.0.0" } }) },
    { path: "src/App.vue", content: '<template><main/></template><script>import { ref } from "vue";</script>' },
    { path: "src/View.vue", content: '<template><section/></template><script>import { computed } from "vue";</script>' },
    { path: "src/main.ts", content: 'import { createApp } from "vue";' },
  ]);
  input.sourceLabelHint = "vue3";
  const inventory = inventoryMiniappSource(input);
  assert.equal(inventory.selectedSourceLabel, "vue3");
  assert.deepEqual(inventory.frameworkConflicts, []);
  assert.ok(inventory.frameworkCandidates.some(candidate => candidate.sourceLabel === "vue2" && candidate.confidence >= 0.75));
});

test("unsafe or ambiguous paths and extra input properties fail closed", () => {
  for (const path of ["../secret.ts", "src/../secret.ts", "/tmp/source.ts", "C:/source.ts", "%2e%2e/secret.ts"]) {
    assert.throws(() => inventoryMiniappSource(inventoryInput([{ path, content: "safe" }])), (error: unknown) =>
      error instanceof MiniappInventoryError && error.code === "MINIAPP_SOURCE_PATH_INVALID", path);
  }
  assert.throws(() => inventoryMiniappSource(inventoryInput([
    { path: "src/App.ts", content: "a" },
    { path: "src/App.ts", content: "b" },
  ])), /duplicates src\/App\.ts/u);

  const extra = inventoryInput([{ path: "src/App.ts", content: "safe", mode: "execute" }]);
  assert.throws(() => inventoryMiniappSource(extra), /inventoryInput\.files\[0\]\.mode: is not allowed/u);
});

test("file-count, per-file, and aggregate byte limits are enforced before scanning", () => {
  const count = inventoryInput([
    { path: "a.ts", content: "a" },
    { path: "b.ts", content: "b" },
  ]);
  (count.limits as Record<string, unknown>).maxFileCount = 1;
  assert.throws(() => inventoryMiniappSource(count), (error: unknown) =>
    error instanceof MiniappInventoryError && error.code === "MINIAPP_FILE_COUNT_LIMIT_EXCEEDED");

  const fileSize = inventoryInput([{ path: "a.ts", content: "abcd" }]);
  (fileSize.limits as Record<string, unknown>).maxFileBytes = 3;
  assert.throws(() => inventoryMiniappSource(fileSize), (error: unknown) =>
    error instanceof MiniappInventoryError && error.code === "MINIAPP_FILE_SIZE_LIMIT_EXCEEDED");

  const total = inventoryInput([
    { path: "a.ts", content: "abc" },
    { path: "b.ts", content: "def" },
  ]);
  (total.limits as Record<string, unknown>).maxTotalBytes = 5;
  assert.throws(() => inventoryMiniappSource(total), (error: unknown) =>
    error instanceof MiniappInventoryError && error.code === "MINIAPP_TOTAL_SIZE_LIMIT_EXCEEDED");
});

test("secret material is rejected while broker references remain inventory-safe", () => {
  const rawSecret = inventoryInput([{
    path: "config.json",
    content: JSON.stringify({ appSecret: "super-secret-value" }),
  }]);
  assert.throws(() => inventoryMiniappSource(rawSecret), (error: unknown) =>
    error instanceof MiniappInventoryError && error.code === "MINIAPP_UNSAFE_SECRET_VALUE");

  const privateKey = inventoryInput([{
    path: "private.pem",
    content: "-----BEGIN PRIVATE KEY-----\nnot-real-but-forbidden\n-----END PRIVATE KEY-----",
  }]);
  assert.throws(() => inventoryMiniappSource(privateKey), /recognizable secret material/u);

  for (const [path, content] of [
    ["config.json", JSON.stringify({ refresh_token: "abcdefghijklmnop" })],
    ["nested-config.json", JSON.stringify({ appSecret: { value: "raw-secret-123456" } })],
    ["array-config.json", JSON.stringify({ access_token: ["raw-secret-123456"] })],
    ["src/config.ts", 'export const accessToken = "abcdefghijklmnop";'],
    ["src/template-config.ts", "export const accessToken = `abcdefghijklmnop`;"],
    ["src/interpolated-config.ts", "export const accessToken = `secret-${value}`;"],
    ["config.yaml", 'authorization: "Bearer abcdefghijklmnop"'],
    ["raw-config.yaml", "refresh_token: raw-secret-123456"],
    ["raw-config.toml", "session_key = raw-secret-123456"],
    [".env.local", 'SESSION_COOKIE="abcdefghijklmnop"'],
    [".env.session", 'SESSION_ID="abcdefghijklmnop"'],
  ] as const) {
    assert.throws(() => inventoryMiniappSource(inventoryInput([{ path, content }])), (error: unknown) =>
      error instanceof MiniappInventoryError && error.code === "MINIAPP_UNSAFE_SECRET_VALUE", path);
  }

  const referenceOnly = inventoryMiniappSource(inventoryInput([
    {
      path: "package.json",
      content: JSON.stringify({
        dependencies: { react: "19.2.7", "access-token": "1.0.0" },
        config: {
          appSecret: "secret://tenant/app-secret",
          refresh_token: "vault://tenant/refresh-token",
          authorization: "kms://tenant/authorization",
        },
      }),
    },
    { path: "src/tokenizer.ts", content: 'export const tokenizer = "ordinary-non-secret-text";' },
    { path: "config.yaml", content: "refresh_token: secret://tenant/refresh-token" },
  ]));
  assert.equal(referenceOnly.selectedSourceLabel, "react");
});

test("binary files remain digested and malformed configs remain explicit, never silently dropped", () => {
  const inventory = inventoryMiniappSource(inventoryInput([
    { path: "src/App.ts", content: "export const App = 1;" },
    { path: "assets/image.bin", content: new Uint8Array([0, 1, 2, 3]) },
    { path: "app.json", content: "{not-json" },
  ]));
  assert.equal(inventory.files.find(file => file.path === "assets/image.bin")?.status, "binary");
  assert.match(inventory.files.find(file => file.path === "assets/image.bin")?.digest ?? "", /^sha256:[a-f0-9]{64}$/u);
  assert.equal(inventory.files.find(file => file.path === "app.json")?.status, "parse-error");
  assert.ok(inventory.findings.some(item => item.code === "MINIAPP_CONFIG_PARSE_ERROR" && item.blocking));
  assert.equal(inventory.coverage.processedFiles, 3);

  const textContainer = inventoryMiniappSource(inventoryInput([
    { path: "src/App.ts", content: "export const App = 1;" },
    { path: "assets/readable.bin", content: "printable-but-still-an-opaque-container" },
  ]));
  assert.equal(textContainer.files.find(file => file.path === "assets/readable.bin")?.kind, "asset");
  assert.deepEqual(textContainer.assets, ["assets/readable.bin"]);
});

test("framework hints cannot override contradictory or absent evidence", () => {
  const input = inventoryInput(reactFiles);
  input.sourceLabelHint = "flutter";
  const inventory = inventoryMiniappSource(input);
  assert.equal(inventory.selectedSourceLabel, null);
  assert.ok(inventory.findings.some(item => item.code === "MINIAPP_FRAMEWORK_HINT_MISMATCH"));
});

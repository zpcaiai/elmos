#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const packDir = path.resolve(here, "..");
const root = path.resolve(packDir, "..", "..");
const sourceRoot = path.join(root, "apps", "web-console");
const targetRoot = path.join(packDir, "target-project");
const engineRoot = path.join(root, "engines", "component-dialect-engine");
const sourceSnapshotRelative = "source-snapshots/web-console-next16-react19-v1";
const sourceSnapshotRoot = path.join(packDir, sourceSnapshotRelative);
const { runRepository } = require(path.join(engineRoot, "dist", "pipeline.js"));
const { scanRepository } = require(path.join(engineRoot, "dist", "scan.js"));
const { markPorted } = require(path.join(engineRoot, "dist", "handoff.js"));
const { buildManualComponentIR } = require(path.join(engineRoot, "dist", "manual-component-ir.js"));
const { emitWechatHandPort, WECHAT_HAND_PORT_RUNTIME, WECHAT_PLATFORM_ADAPTERS } = require(path.join(engineRoot, "dist", "wechat-hand-port.js"));

const PACK_KEY = "web-console-next16-react19-wechat-v1";
const SOURCE_VERSION = "next-16.3.0-react-19.2.7-typescript-5.9.2";
const TARGET_VERSION = "wechat-base-library-3.9.1";
const DEVTOOLS_VERSION = "wechat-devtools-2.01.2510290";
const SOURCE_TUPLE = {
  stack: "nextjs-react-web-console",
  versions: [SOURCE_VERSION],
  language: "typescript",
  language_versions: ["5.9.2"],
  runtime: "nodejs",
  runtime_versions: [process.version.replace(/^v/, "")],
  build_tool: "next-16.3.0",
  package_manager: "pnpm-10.12.4",
  router: ["next-app-router-16.3.0"],
  renderer: ["react-dom-19.2.7", "next-server-client-components-16.3.0"],
  state: ["react-hooks-19.2.7", "context-providers"],
  forms: ["react-controlled-and-uncontrolled-forms"],
  styling: ["css-modules", "global-css", "inline-style"],
  design_system: ["web-console-local-design-system"],
  api_client: ["fetch-relative-api-contract"],
  identity: ["account-session-context", "server-cookie-session"],
  i18n: ["zh-CN", "en-US"],
  test_tools: ["typescript-5.9.2", "next-build-16.3.0", "playwright-1.61.1"],
  browsers: ["chromium-playwright-source-NOT_RUN"],
  devices: [],
};
const TARGET_TUPLE = {
  stack: "wechat-native-miniapp-candidate",
  versions: [TARGET_VERSION],
  language: "javascript",
  language_versions: ["ecmascript-2022"],
  runtime: "wechat-miniapp-runtime-candidate",
  runtime_versions: ["3.9.1"],
  build_tool: DEVTOOLS_VERSION,
  package_manager: "none-native-project",
  router: ["app-json-native-pages-v1"],
  renderer: ["native-wxml"],
  state: ["component-data-setData", "typed-plain-state-decoder-v1"],
  forms: ["native-input-change-contract-v1"],
  styling: ["native-wxss", "css-module-token-map-v1"],
  design_system: ["web-console-wechat-token-adapter-v1"],
  api_client: ["cancellable-wx-request-adapter-v1"],
  identity: ["storage-backed-session-adapter-v1"],
  i18n: ["zh-CN-source-copy-candidate", "en-US-source-copy-candidate"],
  test_tools: ["component-dialect-real-wxml-parser", `${DEVTOOLS_VERSION}-local-installation`],
  browsers: [],
  devices: ["wechat-devtools-emulator-NOT_RUN", "wechat-physical-device-NOT_RUN"],
};

function hashBytes(value) {
  return `sha256:${crypto.createHash("sha256").update(value).digest("hex")}`;
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  return value;
}

function canonicalDigest(value) {
  return hashBytes(JSON.stringify(canonical(value)));
}

function atomicWrite(file, contents) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temporary = `${file}.tmp-${process.pid}`;
  fs.writeFileSync(temporary, contents);
  fs.renameSync(temporary, file);
}

function writeJson(relative, value) {
  atomicWrite(path.join(packDir, relative), `${JSON.stringify(value, null, 2)}\n`);
}

function filesRecursively(dir) {
  const result = [];
  const visit = (current) => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (entry.isSymbolicLink()) throw new Error(`GENERATED_SYMLINK_FORBIDDEN: ${path.join(current, entry.name)}`);
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) visit(full);
      else if (entry.isFile()) result.push(full);
    }
  };
  visit(dir);
  return result;
}

function directoryDigest(dir) {
  const hash = crypto.createHash("sha256");
  for (const file of filesRecursively(dir)) {
    hash.update(path.relative(dir, file));
    hash.update("\0");
    hash.update(fs.readFileSync(file));
    hash.update("\0");
  }
  return `sha256:${hash.digest("hex")}`;
}

function git(...args) {
  return execFileSync("git", args, { cwd: root, encoding: "utf8" }).trim();
}

function sourceManifest(sourceRevision, observedAt) {
  const tracked = git("ls-files", "apps/web-console").split("\n").filter(Boolean).sort();
  const files = tracked.map((relative) => {
    const full = path.join(root, relative);
    if (!fs.existsSync(full) || !fs.statSync(full).isFile()) throw new Error(`PINNED_SOURCE_FILE_MISSING: ${relative}`);
    const sourceRelative = path.relative("apps/web-console", relative);
    return { path: sourceRelative, sha256: hashBytes(fs.readFileSync(full)), bytes: fs.statSync(full).size };
  });
  const snapshotDigest = hashBytes(
    files
      .map(({ path: file, sha256, bytes }) => `${file}\0${sha256}\0${bytes}`)
      .join("\n"),
  );
  return {
    schema_version: 1,
    kind: "elmos.git-source-snapshot-manifest",
    source_root: sourceSnapshotRelative,
    aggregate_digest: snapshotDigest,
    source_revision: sourceRevision,
    observed_at: observedAt,
    repository_relative_root: "apps/web-console",
    file_count: files.length,
    files,
    snapshot_digest: snapshotDigest,
    boundary: "References exact tracked source bytes at source_revision; source scripts are not executed by this generator.",
  };
}

function materializeSourceSnapshot(snapshot) {
  const temporary = fs.mkdtempSync(path.join(path.dirname(sourceSnapshotRoot), ".web-console-source-snapshot-"));
  try {
    for (const entry of snapshot.files) {
      const destination = path.join(temporary, entry.path);
      const relativeDestination = path.relative(temporary, destination);
      if (!relativeDestination || relativeDestination.startsWith("..")) throw new Error(`SOURCE_SNAPSHOT_PATH_ESCAPE: ${entry.path}`);
      const source = path.join(sourceRoot, entry.path);
      atomicWrite(destination, fs.readFileSync(source));
    }
    if (fs.existsSync(sourceSnapshotRoot)) fs.rmSync(sourceSnapshotRoot, { recursive: true, force: true });
    fs.renameSync(temporary, sourceSnapshotRoot);
  } catch (error) {
    if (fs.existsSync(temporary)) fs.rmSync(temporary, { recursive: true, force: true });
    throw error;
  }
}

function unitKey(item) {
  return `${item.sourcePath}#${item.componentName}`;
}

function slug(value) {
  return value.replace(/([a-z0-9])([A-Z])/g, "$1-$2").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "").toLowerCase();
}

function routeFor(sourcePath) {
  if (sourcePath === "app/page.tsx") return "/";
  if (!sourcePath.endsWith("/page.tsx")) return null;
  return `/${sourcePath.slice(4, -9)}`.replace(/\/$/, "") || "/";
}

function sourceRef(sourcePath) {
  return `apps/web-console/${sourcePath}`;
}

function makeUiIr(units, manualIrs, snapshotDigest) {
  const componentIds = new Map(units.map((unit) => [unitKey(unit), `component.${slug(unit.componentName)}`]));
  const components = units.map((unit) => ({
    id: componentIds.get(unitKey(unit)),
    kind: unit.status === "IN_SUBSET" ? "automatic-certified-subset-component" : "explicit-hand-ported-component",
    name: unit.componentName,
    ownership: unit.status === "IN_SUBSET" ? "ENGINE_GENERATED" : "HAND_PORTED",
    disposition: unit.status === "IN_SUBSET" ? "AUTOMATIC" : "HAND_PORTED",
    references: [],
    source_refs: [sourceRef(unit.sourcePath)],
  }));
  const routeUnits = units.filter((unit) => routeFor(unit.sourcePath) !== null);
  const routes = routeUnits.map((unit) => ({
    id: `route.${slug(unit.componentName)}`,
    kind: "next-app-route-to-wechat-catalog-entry",
    name: routeFor(unit.sourcePath),
    path: routeFor(unit.sourcePath),
    references: [componentIds.get(unitKey(unit))],
    source_refs: [sourceRef(unit.sourcePath)],
  }));
  const views = routeUnits.map((unit) => ({
    id: `view.${slug(unit.componentName)}`,
    kind: "route-view",
    name: unit.componentName,
    references: [componentIds.get(unitKey(unit))],
    source_refs: [sourceRef(unit.sourcePath)],
  }));
  const states = manualIrs.flatMap((ir) => ir.state.map((state, index) => ({
    id: `state.${slug(ir.source.componentName)}.${slug(state.name)}.${index}`,
    kind: "typed-hand-port-state",
    name: `${ir.source.componentName}.${state.name}`,
    type: state.type,
    references: [componentIds.get(`${ir.source.file}#${ir.source.componentName}`)],
    source_refs: [sourceRef(ir.source.file)],
  })));
  const effects = manualIrs.flatMap((ir) => ir.effects.map((effect, index) => ({
    id: `effect.${slug(ir.source.componentName)}.${index}`,
    kind: "cancellable-lifecycle-effect",
    name: `${ir.source.componentName}.${effect.hook}.${index}`,
    resources: effect.resources,
    cleanup: effect.cleanup,
    target_cleanup: "abort-on-detached-and-stale-epoch-suppression",
    references: [componentIds.get(`${ir.source.file}#${ir.source.componentName}`)],
    source_refs: [sourceRef(ir.source.file)],
  })));
  const actions = manualIrs.flatMap((ir) => ir.apiPaths.map((apiPath, index) => ({
    id: `action.${slug(ir.source.componentName)}.api.${index}`,
    kind: "allowlisted-cancellable-request",
    name: `${ir.source.componentName} ${apiPath}`,
    api_path: apiPath,
    references: [componentIds.get(`${ir.source.file}#${ir.source.componentName}`)],
    source_refs: [sourceRef(ir.source.file)],
  })));
  const forms = [{
    id: "form.runtime-api-base-url",
    kind: "configuration-form-contract",
    name: "Target API base URL configuration",
    validation: "nonempty explicit base URL required before any migrated network effect runs",
    references: [],
    source_refs: ["apps/web-console/package.json"],
  }];
  const bindings = [{
    id: "binding.source-ir-target",
    kind: "digest-bound-source-ir-target-binding",
    name: "Source component to manual IR to native target trace",
    references: [],
    source_refs: ["apps/web-console/package.json"],
  }];
  const permissions = [{
    id: "permission.fail-closed-external-effects",
    kind: "negative-permission-contract",
    name: "No upload review release payment or undeclared network authority",
    references: [],
    source_refs: ["apps/web-console/package.json"],
  }];
  const resources = [{
    id: "resource.source-snapshot",
    kind: "content-addressed-git-snapshot",
    name: "Pinned web console source snapshot",
    digest: snapshotDigest,
    references: [],
    source_refs: ["apps/web-console/package.json"],
  }];
  const designTokens = [{
    id: "token.wechat-workbench",
    kind: "wxss-token-adapter",
    name: "Web console card, status, table and chart target tokens",
    references: [],
    source_refs: ["apps/web-console/app/globals.css"],
  }];
  const accessibility = [{
    id: "a11y.native-component-contract",
    kind: "wechat-accessibility-review-contract",
    name: "Accessible names, expanded state, status and native controls",
    references: [],
    source_refs: ["apps/web-console/app/globals.css"],
  }];
  const groups = { routes, views, components, states, actions, effects, forms, bindings, permissions, resources, design_tokens: designTokens, accessibility };
  const sourceMap = Object.values(groups).flat().map((node) => ({ node_id: node.id, owner: "elmos-web-console-wechat-migration" }));
  return {
    schema_version: 1,
    pack_key: PACK_KEY,
    source_snapshot_digest: snapshotDigest,
    ...groups,
    source_map: sourceMap,
    unknowns: [
      { id: "unknown.official-wechat-build", severity: "critical", status: "NOT_RUN", detail: "Official WeChat compile/preview evidence is attached only after the installed exact tool executes successfully." },
      { id: "unknown.device-equivalence", severity: "critical", status: "NOT_RUN", detail: "Physical-device source/target differential journeys remain NOT_RUN." },
      { id: "unknown.independent-quality", severity: "critical", status: "NOT_RUN", detail: "Independent holdout, visual, accessibility, privacy, performance and customer evidence remain NOT_RUN." },
    ],
  };
}

function targetCatalog(manualIrs) {
  const names = manualIrs.map((ir) => ir.source.componentName);
  const usingComponents = Object.fromEntries(names.map((name) => [slug(name), `/components/${name}/index`]));
  atomicWrite(path.join(targetRoot, "pages", "index", "index.json"), `${JSON.stringify({ usingComponents, navigationBarTitleText: "ELMOS WeChat Migration" }, null, 2)}\n`);
  atomicWrite(path.join(targetRoot, "pages", "index", "index.js"), `Page({\n  data: {\n    activeIndex: 0,\n    apiBaseUrl: "",\n    components: ${JSON.stringify(names.map((name, index) => ({ index, name, tag: slug(name) })), null, 4)}\n  },\n  selectComponent(event) { this.setData({ activeIndex: Number(event.currentTarget.dataset.index) }); },\n  setApiBaseUrl(event) { this.setData({ apiBaseUrl: event.detail.value }); }\n});\n`);
  const components = names.map((name, index) => `  <${slug(name)} wx:if="{{activeIndex == ${index}}}" api-base-url="{{apiBaseUrl}}" />`).join("\n");
  atomicWrite(path.join(targetRoot, "pages", "index", "index.wxml"), `<view class="page">\n  <view class="config"><text>API base URL（执行网络动作前必填）</text><input value="{{apiBaseUrl}}" bindinput="setApiBaseUrl" placeholder="https://approved.example" /></view>\n  <scroll-view scroll-x class="tabs"><button wx:for="{{components}}" wx:key="name" size="mini" data-index="{{item.index}}" bindtap="selectComponent">{{item.name}}</button></scroll-view>\n${components}\n</view>\n`);
  atomicWrite(path.join(targetRoot, "pages", "index", "index.wxss"), `.page { padding: 24rpx; background: #f4f6fa; min-height: 100vh; }\n.config { padding: 20rpx; background: #fff; border-radius: 16rpx; }\n.config input { margin-top: 12rpx; padding: 12rpx; border: 1rpx solid #ccd5e3; }\n.tabs { width: 100%; white-space: nowrap; margin: 20rpx 0; }\n.tabs button { margin-right: 10rpx; }\n`);
  writeJsonToTarget("app.json", { pages: ["pages/index/index"], window: { navigationBarTitleText: "ELMOS WeChat Migration", backgroundColor: "#f4f6fa" }, sitemapLocation: "sitemap.json" });
  writeJsonToTarget("project.config.json", {
    appid: "touristappid",
    compileType: "miniprogram",
    libVersion: "3.9.1",
    projectname: PACK_KEY,
    setting: { es6: true, minified: false, urlCheck: true, postcss: true },
  });
  writeJsonToTarget("sitemap.json", { desc: "Local migration candidate; no release authority", rules: [{ action: "disallow", page: "*" }] });
}

function writeJsonToTarget(relative, value) {
  atomicWrite(path.join(targetRoot, relative), `${JSON.stringify(value, null, 2)}\n`);
}

async function main() {
  const sourceRevision = git("rev-parse", "HEAD");
  const observedAt = git("show", "-s", "--format=%cI", sourceRevision);
  const snapshot = sourceManifest(sourceRevision, observedAt);
  const scan = scanRepository({ repository: sourceRoot, sourceFramework: "react", includeAllFindings: true });
  const units = scan.findings.filter((item) => item.status === "IN_SUBSET" || item.status === "OUT_OF_SUBSET")
    .sort((a, b) => unitKey(a).localeCompare(unitKey(b)));
  if (scan.totals.scanErrors !== 0 || units.length !== scan.totals.discovered) throw new Error("SOURCE_SCAN_NOT_CLOSED");

  const temporary = fs.mkdtempSync(path.join(packDir, ".target-project.tmp-"));
  try {
    await runRepository({ repository: sourceRoot, sourceFramework: "react", targetFramework: "miniprogram", destination: temporary, skipExecution: true });
    atomicWrite(path.join(temporary, "runtime", "hand-port-runtime.js"), WECHAT_HAND_PORT_RUNTIME);
    atomicWrite(path.join(temporary, "runtime", "platform-adapters.js"), WECHAT_PLATFORM_ADAPTERS);

    const manualIrs = [];
    for (const finding of units.filter((item) => item.status === "OUT_OF_SUBSET")) {
      const source = fs.readFileSync(path.join(sourceRoot, finding.sourcePath), "utf8");
      const ir = buildManualComponentIR({
        source,
        sourceFile: finding.sourcePath,
        componentName: finding.componentName,
        reasonCode: finding.reasonCode,
        reason: finding.reason,
        category: finding.category,
      });
      manualIrs.push(ir);
      const emitted = emitWechatHandPort(ir);
      const relativeTarget = path.join("components", finding.componentName);
      const dir = path.join(temporary, relativeTarget);
      for (const [extension, contents] of Object.entries(emitted.files)) atomicWrite(path.join(dir, `index.${extension}`), contents);
      markPorted({
        destination: temporary,
        repository: sourceRoot,
        sourcePath: finding.sourcePath,
        componentName: finding.componentName,
        targetPath: relativeTarget,
        assignee: "elmos-web-console-wechat-migration",
        note: `${finding.category} via ${ir.targetPlan.adapters.join(", ")}`,
      });
    }
    const handoffPath = path.join(temporary, "handoff.json");
    const handoff = JSON.parse(fs.readFileSync(handoffPath, "utf8"));
    for (const entry of handoff.entries) {
      entry.markedAt = observedAt;
      entry.updatedAt = observedAt;
      const finding = units.find((item) => item.sourcePath === entry.sourcePath && item.componentName === entry.componentName);
      entry.reasonCode = finding?.reasonCode ?? null;
    }
    atomicWrite(handoffPath, `${JSON.stringify(handoff, null, 2)}\n`);

    const finalCoverage = await runRepository({ repository: sourceRoot, sourceFramework: "react", targetFramework: "miniprogram", destination: temporary, skipExecution: true });
    if (finalCoverage.deliveryStatus !== "COMPLETE_WITH_HANDOFF" || finalCoverage.totals.blocked !== 0 || finalCoverage.totals.discovered !== units.length) {
      throw new Error(`MIGRATION_CLOSURE_FAILED: ${JSON.stringify({ deliveryStatus: finalCoverage.deliveryStatus, totals: finalCoverage.totals, unresolvedReferences: finalCoverage.unresolvedReferences })}`);
    }
    for (const file of filesRecursively(temporary).filter((file) => /\/components\/.*\/index\.(?:js|wxml)$/.test(file))) {
      const contents = fs.readFileSync(file, "utf8");
      if (contents.includes("NOT TRANSLATED") || contents.includes("must be ported by hand")) throw new Error(`PLACEHOLDER_REMAINS: ${file}`);
    }
    if (fs.existsSync(targetRoot)) fs.rmSync(targetRoot, { recursive: true, force: true });
    fs.renameSync(temporary, targetRoot);

    targetCatalog(manualIrs);
    writeJson("manual-ir/components.json", {
      schema_version: 1,
      kind: "elmos.manual-component-ir-bundle",
      pack_key: PACK_KEY,
      source_revision: sourceRevision,
      component_count: manualIrs.length,
      components: manualIrs,
      bundle_digest: canonicalDigest(manualIrs.map((ir) => ({ component: ir.source.componentName, digest: ir.irDigest }))),
    });

    const checkedCoverage = JSON.parse(fs.readFileSync(path.join(targetRoot, "coverage-report.json"), "utf8"));
    const coverageByKey = new Map(checkedCoverage.files.map((file) => [`${file.sourcePath}#${path.basename(file.targetPath)}`, file]));
    const manualByKey = new Map(manualIrs.map((ir) => [`${ir.source.file}#${ir.source.componentName}`, ir]));
    const entries = units.map((unit) => {
      const key = unitKey(unit);
      const targetDir = path.join(targetRoot, "components", unit.componentName);
      const outcome = coverageByKey.get(key);
      if (!outcome || !fs.existsSync(targetDir)) throw new Error(`TARGET_OUTCOME_MISSING: ${key}`);
      const manual = manualByKey.get(key);
      return {
        source_path: unit.sourcePath,
        component_name: unit.componentName,
        source_sha256: hashBytes(fs.readFileSync(path.join(sourceRoot, unit.sourcePath))),
        disposition: unit.status === "IN_SUBSET" ? "AUTOMATIC" : "HAND_PORTED",
        automatic_subset_status: unit.status,
        blocker: unit.status === "OUT_OF_SUBSET" ? { reason_code: unit.reasonCode, reason: unit.reason, semantic_category: unit.category } : null,
        manual_ir_digest: manual?.irDigest ?? null,
        target_path: `target-project/components/${unit.componentName}`,
        target_sha256: directoryDigest(targetDir),
        target_files: filesRecursively(targetDir).map((file) => path.relative(packDir, file)).sort(),
        syntax_evidence: unit.status === "IN_SUBSET" ? outcome.syntaxStatus : "LOCAL_WXML_PARSE_PENDING",
        runtime_evidence: "NOT_RUN",
        independent_evidence: "NOT_RUN",
        certification: "NOT_CERTIFIED",
      };
    });
    const closure = {
      schema_version: 1,
      kind: "elmos.frontend-component-migration-closure",
      pack_key: PACK_KEY,
      source_revision: sourceRevision,
      source_snapshot_digest: snapshot.snapshot_digest,
      target_tuple: TARGET_TUPLE,
      totals: {
        discovered: entries.length,
        automatic: entries.filter((item) => item.disposition === "AUTOMATIC").length,
        hand_ported: entries.filter((item) => item.disposition === "HAND_PORTED").length,
        unhandled: 0,
        scan_errors: scan.totals.scanErrors,
      },
      automatic_coverage: Number((entries.filter((item) => item.disposition === "AUTOMATIC").length / entries.length).toFixed(6)),
      implementation_coverage: 1,
      delivery_status: checkedCoverage.deliveryStatus,
      runtime_evidence: "NOT_RUN",
      production_evidence: "NOT_RUN",
      certification: "NOT_CERTIFIED",
      entries,
      registry_digest: canonicalDigest(entries),
    };
    writeJson("transformations/component-migration-closure.json", closure);
    materializeSourceSnapshot(snapshot);
    writeJson("source-snapshots/manifest.json", snapshot);
    writeJson("source-fingerprint/fingerprint.json", {
      schema_version: 1,
      pack_key: PACK_KEY,
      source_tuple: SOURCE_TUPLE,
      source_revision: sourceRevision,
      snapshot_digest: snapshot.snapshot_digest,
      coverage: 1,
      routes: units.filter((unit) => routeFor(unit.sourcePath) !== null).map((unit) => ({ path: routeFor(unit.sourcePath), source_ref: sourceRef(unit.sourcePath), discovery: "next-app-router-static" })),
      components: units.map((unit) => ({ name: unit.componentName, source_ref: sourceRef(unit.sourcePath), discovery: "typescript-compiler-api" })),
      templates: units.map((unit) => `${sourceRef(unit.sourcePath)}#${unit.componentName}`),
      state_stores: manualIrs.flatMap((ir) => ir.state.map((state) => ({ name: `${ir.source.componentName}.${state.name}`, source_ref: sourceRef(ir.source.file), provider: "react-hook-or-context" }))),
      forms: [{ name: "web-console-forms", source_ref: "apps/web-console/app", binding: "react-event-contracts" }],
      api_clients: [...new Set(manualIrs.flatMap((ir) => ir.apiPaths))].map((apiPath) => ({ name: apiPath, source_ref: "apps/web-console/app", provider: "fetch" })),
      auth: [{ name: "account-session", source_ref: "apps/web-console/app/components/AccountSessionProvider.tsx" }],
      i18n: [{ locale: "zh-CN", mode: "source-copy-candidate" }, { locale: "en-US", mode: "source-copy-candidate" }],
      design_assets: [{ name: "web-console-css", source_ref: "apps/web-console/app/globals.css", mode: "css-and-css-modules" }],
      accessibility: [{ name: "source-accessibility-inventory", source_ref: "apps/web-console/app", mode: "ast-static-candidate" }],
      runtime_evidence: [],
      evidence_refs: ["source-snapshots/manifest.json", "transformations/component-migration-closure.json", "certification/local-static-evidence.json"],
      critical_unknowns: ["source browser journeys NOT_RUN", "target emulator/device journeys NOT_RUN", "independent equivalence NOT_RUN"],
    });
    writeJson("source-fingerprint/evidence.json", { schema_version: 1, pack_key: PACK_KEY, state: "LOCAL_STATIC_EXECUTED", source_revision: sourceRevision, snapshot_digest: snapshot.snapshot_digest, file_count: snapshot.file_count, component_count: units.length, scan_errors: 0, certification: "NOT_CERTIFIED" });
    writeJson("ui-ir/model.json", makeUiIr(units, manualIrs, snapshot.snapshot_digest));

    const exactRoutes = units.filter((unit) => routeFor(unit.sourcePath) !== null).map((unit) => routeFor(unit.sourcePath));
    writeJson("pack.json", {
      schema_version: 1, pack_key: PACK_KEY, version: "1.0.0", mode: "migration", status: "experimental",
      owner: "elmos-frontend-client-engine", maintenance_owner: "elmos-client-modernization-maintainers", ux_owner: "elmos-web-console-miniapp-review", accessibility_owner: "elmos-accessibility-review",
      source: SOURCE_TUPLE, target: TARGET_TUPLE,
      scope: {
        journeys: ["catalog-open-component", "configure-api-base", "load-workbench-data", "session-and-preference-provider", "table-disclosure-icon-slot-rendering"],
        routes: exactRoutes,
        component_roots: [...new Set(units.map((unit) => sourceRef(unit.sourcePath)))],
        excluded: ["reverse MiniApp-to-frontend route", "upload review release payment refund", "production data and credentials", "certification without official runtime device and independent evidence"],
      },
      paths: { source_fingerprint: "source-fingerprint/fingerprint.json", ui_ir: "ui-ir/model.json", target_profile: "target-profile/profile.json", acceptance_profile: "acceptance/acceptance-profile.json", support_matrix: "support-matrix.json", evidence: "certification/evidence.json", certification: "certification/certification.json", component_closure: "transformations/component-migration-closure.json", target_project: "target-project" },
      gates: { build: "required-NOT_RUN", startup_or_launch: "required-NOT_RUN", p0_journeys: "required-NOT_RUN", visual: "required-NOT_RUN", accessibility: "required-NOT_RUN", security: "required-NOT_RUN", holdout: "required-NOT_RUN" },
    });
    writeJson("target-profile/profile.json", {
      profile_key: `${PACK_KEY}-target`, version: "2026-08-30.1", owner: "elmos-client-modernization-maintainers", framework: "wechat-native-miniapp-candidate", versions: [TARGET_VERSION], language: "javascript", language_versions: ["ecmascript-2022"], runtime: "wechat-miniapp-runtime-candidate", runtime_versions: ["3.9.1"], build_tool: DEVTOOLS_VERSION, package_manager: "none-native-project", router: ["app-json-native-pages-v1"], rendering_strategy: { mode: "native-wxml-no-webview", status: "LOCAL_GENERATED" }, state_strategy: { provider: "component-data-setData-with-typed-plain-decoder", cleanup: "detached-abort-and-epoch" }, form_strategy: { provider: "native-input-bindinput", validation: "fail-closed-before-effects" }, styling_strategy: { mode: "native-wxss-plus-css-module-token-map", unsupported: "explicit-manual-review" }, design_system_strategy: { mode: "web-console-wechat-token-adapter-v1" }, api_client_strategy: { provider: "cancellable-wx-request", base_url: "explicit-runtime-property", undeclared_network: "denied" }, auth_strategy: { mode: "storage-backed-session-candidate", server_authority: "not-in-client" }, i18n_strategy: { provider: "source-label-copy-candidate", locales: ["zh-CN", "en-US"] }, accessibility_profile: { standard: "native-control-and-source-contract-candidate", manual_review: "NOT_RUN" }, browser_matrix: ["wechat-devtools-renderer-NOT_RUN"], device_profiles: ["wechat-devtools-emulator-NOT_RUN", "wechat-physical-device-NOT_RUN"], test_profiles: ["real-wxml-parser-local", `${DEVTOOLS_VERSION}-NOT_RUN`, "physical-device-p0-NOT_RUN"], provision: { commands: [`/Applications/wechatwebdevtools.app/Contents/MacOS/cli open --project ${path.relative(root, targetRoot)}`] }, health_check: { commands: ["official compile plus catalog P0 journey; NOT_RUN until evidence is attached"] }, security: { credential_policy: "no app secret key token or production credential", network: "explicit apiBaseUrl and platform domain allowlist required", forbidden_effects: ["upload", "review", "release", "payment", "refund"] }, lifecycle: { support_until: "not-established-experimental-pack", upgrade_policy: "new exact tuple and evidence required for any source target or toolchain change" }, authorization: { official_build: true, preview: false, upload: false, review: false, release: false } });
    writeJson("support-matrix.json", { schema_version: 1, pack_key: PACK_KEY, capabilities: [
      { id: "component-implementation-closure", domain: "component", status: "experimental", owner: "elmos-frontend-client-engine", source_versions: [SOURCE_VERSION], target_versions: [TARGET_VERSION], evidence_refs: ["transformations/component-migration-closure.json", "target-project/coverage-report.json"], reason: `${entries.length}/${entries.length} components have target implementations: ${closure.totals.automatic} automatic and ${closure.totals.hand_ported} explicit hand ports; runtime equivalence remains NOT_RUN.` },
      { id: "typed-hook-effect-and-collection-ir", domain: "semantic-ir", status: "experimental", owner: "elmos-frontend-client-engine", source_versions: [SOURCE_VERSION], target_versions: [TARGET_VERSION], evidence_refs: ["manual-ir/components.json", "ui-ir/model.json"], reason: "All blocked components carry exact AST ranges, source digests, hooks, state, effects, cleanup obligations, collections, platform semantics and target adapters." },
      { id: "wechat-native-target-adapters", domain: "target-generation", status: "experimental", owner: "elmos-client-modernization-maintainers", source_versions: [SOURCE_VERSION], target_versions: [TARGET_VERSION], evidence_refs: ["target-project/runtime/hand-port-runtime.js", "target-project/runtime/platform-adapters.js"], reason: "Native WXML/WXSS/JS implements cancellable requests, typed plain-state projection, Map/Set projection, session/preferences, table, disclosure, icon, slot and document lifecycle adapters without WebView or full-page Canvas." },
      { id: "official-wechat-build-and-device", domain: "runtime-validation", status: "blocked", owner: "elmos-web-console-miniapp-review", source_versions: [SOURCE_VERSION], target_versions: [TARGET_VERSION], evidence_refs: [], reason: `The installed ${DEVTOOLS_VERSION} has been detected, but official compile, preview, emulator and physical-device evidence are NOT_RUN until executed and attached.` },
      { id: "independent-equivalence-and-quality", domain: "quality", status: "blocked", owner: "elmos-accessibility-review", source_versions: [SOURCE_VERSION], target_versions: [TARGET_VERSION], evidence_refs: [], reason: "Independent holdout, differential behavior, visual, accessibility, privacy, performance, security and customer acceptance remain NOT_RUN." },
    ] });
    writeJson("route-matrix.json", { schema_version: 1, pack_key: PACK_KEY, tuples: exactRoutes.map((route) => ({ source_stack: "nextjs-react-web-console", source_version: SOURCE_VERSION, source_snapshot_digest: snapshot.snapshot_digest, target_stack: "wechat-native-miniapp-candidate", target_version: TARGET_VERSION, target_toolchain_version: DEVTOOLS_VERSION, generator_profile: "2026-08-30.1", journey: "web-console-component-catalog", route, status: "experimental", evidence_refs: ["transformations/component-migration-closure.json", "ui-ir/model.json"], runtime_state: "LOCAL_GENERATED_NOT_OFFICIALLY_EXECUTED", certification: "NOT_CERTIFIED" })), recertification_triggers: ["source revision or tracked file digest change", "component inventory or blocker change", "Next React TypeScript pnpm Node version change", "WeChat base library DevTools runtime or generator change", "adapter policy IR corpus baseline or acceptance change"] });
    writeJson("acceptance/acceptance-profile.json", { profile_key: `${PACK_KEY}-acceptance`, version: "1.0.0", owner: "elmos-web-console-miniapp-review", browser_matrix: [], device_matrix: ["wechat-devtools-emulator-NOT_RUN", "wechat-physical-device-NOT_RUN"], locales: ["zh-CN", "en-US"], themes: ["wechat-candidate-default"], rendering: { modes: ["native-wxml"], webview: "forbidden", official_runtime_state: "NOT_RUN" }, visual: { baseline_policy: "approved-only-no-auto-update", max_unapproved_differences: 0, state: "NOT_RUN" }, accessibility: { standard: "source-contract-plus-native-control-review", critical_violations: null, automated_state: "NOT_RUN", assistive_technology_state: "NOT_RUN" }, interaction: { p0_pass_rate: 1, state: "NOT_RUN" }, performance: { budgets: { launch_ms: 2500, interaction_ms: 150 }, state: "NOT_RUN" }, seo: { required: false, reason: "native Mini Program" }, i18n: { missing_keys: null, state: "NOT_RUN" }, security: { authorization_regressions: null, forbidden_generated_capabilities: ["upload", "review", "release", "payment", "refund", "undeclared-network"], state: "NOT_RUN" }, p0_journeys: [
      { id: "catalog-open-component", steps: ["open catalog", "select every migrated component", "observe non-placeholder native view"], source_expected: "all 71 source components have an explicit target implementation", target_runtime_state: "NOT_RUN" },
      { id: "async-resource-cancellation", steps: ["configure approved API base", "start request", "detach component", "observe task abort and stale response suppression"], source_expected: "no write after unmount and no stale response overwrite", target_runtime_state: "NOT_RUN" },
      { id: "platform-semantics", steps: ["open table disclosure icon slot and document-root ports", "exercise native controls"], source_expected: "explicit target semantics without silent drop", target_runtime_state: "NOT_RUN" },
    ], thresholds: { source_fingerprint_coverage: 1, ui_ir_source_map_coverage: 1, implementation_coverage: 1, unhandled_components: 0, target_build_green_rate: 1, target_startup_or_launch_rate: 1, p0_journey_pass_rate: 1, visual_regressions: 0, critical_accessibility_violations: 0 }, exclusions: ["upload review release payment refund", "production credentials and data", "reverse route"] });
    writeJson("design-system/contract.json", { schema_version: 1, pack_key: PACK_KEY, source: ["apps/web-console/app/globals.css", "apps/web-console/app/**/*.module.css"], target: "target-project/**/*.wxss", token_adapter: "web-console-wechat-token-adapter-v1", rules: { global_important: false, unsupported_styles: "explicit review", css_module_tokens: "traceable generated classes", units: "rpx target with device review NOT_RUN" }, state: "LOCAL_GENERATED", runtime_evidence: "NOT_RUN" });
    writeJson("corpus/development/cases.json", { schema_version: 1, independence: "development", cases: [{ id: "dev-effect-cleanup", target: "cancellable request and detached cleanup" }, { id: "dev-map-set", target: "plain collection projection" }, { id: "dev-platform", target: "table disclosure svg html slot adapters" }] });
    writeJson("corpus/negative/cases.json", { schema_version: 1, independence: "negative", cases: [{ id: "neg-source-drift", expected: "closure validation fails" }, { id: "neg-api-base-absent", expected: "configuration-required and no request" }, { id: "neg-stale-response", expected: "epoch mismatch suppresses setData" }, { id: "neg-placeholder", expected: "target validation fails" }] });
    writeJson("corpus/holdout/cases.json", { schema_version: 1, independence: "independent-holdout", state: "NOT_RUN", cases: [{ id: "holdout-async-race", evidence: "NOT_RUN" }, { id: "holdout-complex-collection", evidence: "NOT_RUN" }, { id: "holdout-platform-accessibility", evidence: "NOT_RUN" }] });
    writeJson("corpus/representative-workloads/cases.json", { schema_version: 1, independence: "representative", state: "NOT_RUN", cases: [{ id: "representative-all-71-components", evidence: "NOT_RUN" }, { id: "representative-console-journeys", evidence: "NOT_RUN" }] });
    writeJson("visual-baselines/policy.json", { schema_version: 1, automatic_updates: false, candidate_and_approved_roots_are_distinct: true, approved_baselines: [], state: "NOT_RUN" });
    writeJson("accessibility/status.json", { schema_version: 1, automated: "NOT_RUN", assistive_technology: "NOT_RUN", critical_violations: null, certification: "NOT_CERTIFIED" });
    writeJson("certification/local-static-evidence.json", { schema_version: 1, pack_key: PACK_KEY, status: "PASSED_LOCAL_STATIC", source_revision: sourceRevision, source_snapshot_digest: snapshot.snapshot_digest, component_scan: scan.totals, implementation_closure: closure.totals, manual_ir_components: manualIrs.length, target_component_directories: entries.length, placeholder_count: 0, runtime_evidence: "NOT_RUN", independent_evidence: "NOT_RUN", certification: "NOT_CERTIFIED" });
    writeJson("certification/source-build-evidence.json", { schema_version: 1, pack_key: PACK_KEY, status: "NOT_RUN", command: "pnpm build", exact_source_revision: sourceRevision, executor: null, artifact_digest: null, certification: "NOT_CERTIFIED" });
    writeJson("certification/official-wechat-build-evidence.json", { schema_version: 1, pack_key: PACK_KEY, status: "NOT_RUN", toolchain: DEVTOOLS_VERSION, command: `/Applications/wechatwebdevtools.app/Contents/MacOS/cli open --project ${path.relative(root, targetRoot)}`, executor: null, artifact_digest: null, preview: "NOT_RUN", emulator: "NOT_RUN", physical_device: "NOT_RUN", certification: "NOT_CERTIFIED" });
    writeJson("certification/external-evidence-status.json", { schema_version: 1, pack_key: PACK_KEY, official_target_build: "NOT_RUN", emulator: "NOT_RUN", physical_device: "NOT_RUN", differential_journeys: "NOT_RUN", visual: "NOT_RUN", accessibility: "NOT_RUN", privacy: "NOT_RUN", performance: "NOT_RUN", security: "NOT_RUN", independent_holdout: "NOT_RUN", customer_acceptance: "NOT_RUN", certification: "NOT_CERTIFIED" });
    writeJson("certification/evidence.json", { schema_version: 1, pack_key: PACK_KEY, metrics: { source_fingerprint_coverage: 1, ui_ir_source_map_coverage: 1, implementation_coverage: 1, automatic_coverage: closure.automatic_coverage, target_build_green_rate: 0, target_startup_or_launch_rate: 0, p0_journey_pass_rate: 0, route_contract_pass_rate: 0, state_contract_pass_rate: 0, form_contract_pass_rate: 0, identity_permission_pass_rate: 0, visual_pass_rate: 0, accessibility_pass_rate: 0, i18n_pass_rate: 0, browser_matrix_pass_rate: 0, representative_workload_pass_rate: 0, source_map_coverage: 1 }, critical_unknowns: 3, unhandled_components: 0, silent_ui_drops: null, silent_ui_drops_state: "UNKNOWN_NOT_EVALUATED", critical_visual_regressions: null, critical_visual_regressions_state: "UNKNOWN_NOT_EVALUATED", critical_accessibility_violations: null, critical_accessibility_violations_state: "UNKNOWN_NOT_EVALUATED", critical_security_regressions: null, critical_security_regressions_state: "UNKNOWN_NOT_EVALUATED", critical_interaction_regressions: null, critical_interaction_regressions_state: "UNKNOWN_NOT_EVALUATED", test_integrity_violations: 0, unapproved_baseline_changes: 0, unapproved_dependency_changes: 0, evidence_refs: ["source-snapshots/manifest.json", "manual-ir/components.json", "ui-ir/model.json", "transformations/component-migration-closure.json", "target-project/coverage-report.json", "certification/local-static-evidence.json", "certification/source-build-evidence.json", "certification/official-wechat-build-evidence.json", "certification/external-evidence-status.json"], evidence_boundary: "71/71 implementation closure is local engineering evidence. Official target runtime, source-target equivalence, quality, independent review and certification remain NOT_RUN/NOT_CERTIFIED." });
    writeJson("certification/certification.json", { schema_version: 1, pack_key: PACK_KEY, status: "experimental", owner: "independent-client-gate", exact_tuple: { source: SOURCE_TUPLE, target: TARGET_TUPLE }, evidence_refs: ["certification/local-static-evidence.json", "certification/source-build-evidence.json", "certification/official-wechat-build-evidence.json", "certification/external-evidence-status.json"], recertification_triggers: ["source snapshot change", "component inventory or closure change", "target profile toolchain or base library change", "adapter runtime change", "corpus baseline acceptance or evidence policy change"], certification_decision: "NOT_CERTIFIED", production_claim_authorized: false });
    atomicWrite(path.join(packDir, "certification", "gap-inventory.md"), `# Remaining external gates\n\nLocal code-level implementation closure is **${entries.length}/${entries.length}**: ${closure.totals.automatic} automatic and ${closure.totals.hand_ported} HAND_PORTED, with zero unhandled components and zero scan errors.\n\nThe following remain fail-closed: official WeChat build/preview, emulator and physical-device journeys, source-target differential behavior, visual and accessibility review, privacy and security review, performance, independent holdout, customer acceptance, upload/review/release, and production certification.\n`);
    atomicWrite(path.join(packDir, "README.md"), `# ${PACK_KEY}\n\nExact directional candidate pack for ${SOURCE_VERSION} at \`${sourceRevision}\` to ${TARGET_VERSION} with ${DEVTOOLS_VERSION}.\n\n- Automatic safe subset: ${closure.totals.automatic}/${entries.length} (${(closure.automatic_coverage * 100).toFixed(1)}%).\n- Explicit native HAND_PORTED implementations: ${closure.totals.hand_ported}/${entries.length}.\n- Implementation closure: ${entries.length}/${entries.length}; unhandled: 0; scan errors: 0.\n- Runtime, device, independent, production and certification evidence: NOT_RUN / NOT_CERTIFIED until attached by the named gates.\n\nRegenerate after building \`engines/component-dialect-engine\`:\n\n\`\`\`bash\nnode client-packs/${PACK_KEY}/tooling/generate-pack.mjs\n\`\`\`\n`);
    const targetFiles = filesRecursively(targetRoot).map((file) => ({ path: path.relative(packDir, file), sha256: hashBytes(fs.readFileSync(file)), bytes: fs.statSync(file).size }));
    writeJson("target-project-manifest.json", { schema_version: 1, pack_key: PACK_KEY, file_count: targetFiles.length, files: targetFiles, target_digest: canonicalDigest(targetFiles.map(({ path: file, sha256 }) => ({ path: file, sha256 }))), official_build: "NOT_RUN", certification: "NOT_CERTIFIED" });
    process.stdout.write(`${JSON.stringify({ pack: PACK_KEY, source_revision: sourceRevision, source_snapshot_digest: snapshot.snapshot_digest, totals: closure.totals, automatic_coverage: closure.automatic_coverage, implementation_coverage: closure.implementation_coverage, target_files: targetFiles.length, certification: "NOT_CERTIFIED" }, null, 2)}\n`);
  } catch (error) {
    if (fs.existsSync(temporary)) fs.rmSync(temporary, { recursive: true, force: true });
    throw error;
  }
}

await main();

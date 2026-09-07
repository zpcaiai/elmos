#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { lstatSync, readFileSync, realpathSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const replayScriptPath = fileURLToPath(import.meta.url);
const certificationRoot = dirname(replayScriptPath);
const MAX_CONTROL_FILE_BYTES = 4 * 1024 * 1024;
const MAX_SOURCE_ARCHIVE_BYTES = 64 * 1024 * 1024;
const arguments_ = process.argv.slice(2);
if (arguments_.length > 1 || (arguments_.length === 1 && !["--check", "--emit"].includes(arguments_[0]))) {
  throw new Error("usage: replay-local-runtime.mjs [--check|--emit]");
}
const emitOnly = arguments_[0] === "--emit";
const packRoot = realpathSync(resolve(certificationRoot, ".."));
const repositoryRoot = realpathSync(resolve(packRoot, "../.."));
const assertStrictDescendant = (root, candidate, label) => {
  const relativeCandidate = relative(root, candidate);
  assert.ok(
    relativeCandidate &&
      relativeCandidate !== ".." &&
      !relativeCandidate.startsWith(`..${sep}`) &&
      !isAbsolute(relativeCandidate),
    `${label}: containment failed`,
  );
};
const engineRootCandidate = resolve(repositoryRoot, "engines/frontend-client-engine");
assertStrictDescendant(repositoryRoot, engineRootCandidate, "engine root");
const engineRootStat = lstatSync(engineRootCandidate);
assert.ok(engineRootStat.isDirectory() && !engineRootStat.isSymbolicLink(), "engine root must be a directory and not a symlink");
const engineRoot = realpathSync(engineRootCandidate);
assertStrictDescendant(repositoryRoot, engineRoot, "canonical engine root");
const sourceRootRelative = "client-packs/frontend-to-miniapp-vue3-wechat-v1/source-snapshots/vue3-todo-v1.0.1";
const sourceRootCandidate = resolve(repositoryRoot, sourceRootRelative);
assertStrictDescendant(repositoryRoot, sourceRootCandidate, "source root");
const sourceRootStat = lstatSync(sourceRootCandidate);
assert.ok(sourceRootStat.isDirectory() && !sourceRootStat.isSymbolicLink(), "source root must be a directory and not a symlink");
const sourceRoot = realpathSync(sourceRootCandidate);
assertStrictDescendant(repositoryRoot, sourceRoot, "canonical source root");
const sourceArchiveRelative = "skills/subskills/elmos-frontend-to-miniapp-skills-v1.0.0.zip";
const sourceArchiveCandidate = resolve(repositoryRoot, sourceArchiveRelative);
assertStrictDescendant(repositoryRoot, sourceArchiveCandidate, "source archive");
const sourceArchiveStat = lstatSync(sourceArchiveCandidate);
assert.ok(sourceArchiveStat.isFile() && !sourceArchiveStat.isSymbolicLink(), "source archive must be a regular non-symlink file");
assert.ok(sourceArchiveStat.size <= MAX_SOURCE_ARCHIVE_BYTES, "source archive exceeds bounded replay limit");
const sourceArchivePath = realpathSync(sourceArchiveCandidate);
assertStrictDescendant(repositoryRoot, sourceArchivePath, "canonical source archive");
const sourceArchiveRaw = readFileSync(sourceArchivePath);
const sourceArchiveDigest = `sha256:${createHash("sha256").update(sourceArchiveRaw).digest("hex")}`;
const expectedSourceArchiveDigest = "sha256:e8fabbe19f96a432e3ba77470e1c35a000cc683cd4ac0c084bbabcf31df79d82";
assert.equal(sourceArchiveDigest, expectedSourceArchiveDigest, "pinned source archive digest drift");
const targetProfileCandidate = resolve(packRoot, "target-profile/profile.json");
assertStrictDescendant(packRoot, targetProfileCandidate, "target profile");
const targetProfileStat = lstatSync(targetProfileCandidate);
assert.ok(targetProfileStat.isFile() && !targetProfileStat.isSymbolicLink(), "target profile must be a regular non-symlink file");
assert.ok(targetProfileStat.size <= MAX_CONTROL_FILE_BYTES, "target profile exceeds bounded replay limit");
const targetProfilePath = realpathSync(targetProfileCandidate);
assertStrictDescendant(packRoot, targetProfilePath, "canonical target profile");
const expectedEvidenceCandidate = resolve(certificationRoot, "local-runtime-candidate-evidence.json");
assertStrictDescendant(certificationRoot, expectedEvidenceCandidate, "expected evidence");
const expected = emitOnly ? null : (() => {
  const stat = lstatSync(expectedEvidenceCandidate);
  assert.ok(stat.isFile() && !stat.isSymbolicLink(), "expected evidence must be a regular non-symlink file");
  assert.ok(stat.size <= MAX_CONTROL_FILE_BYTES, "expected evidence exceeds bounded replay limit");
  const canonical = realpathSync(expectedEvidenceCandidate);
  assertStrictDescendant(certificationRoot, canonical, "canonical expected evidence");
  return JSON.parse(readFileSync(canonical, "utf8"));
})();
const implementationPaths = [
  "package.json", "pnpm-lock.yaml", "tsconfig.json",
  "src/miniapp-types.ts", "src/miniapp-contract-validation.ts", "src/miniapp-inventory.ts",
  "src/miniapp-semantic-ir.ts", "src/miniapp-planning.ts", "src/miniapp-target-generation.ts",
  "src/miniapp-package-contract.ts", "src/miniapp-output-contracts.ts", "src/miniapp-skill-runtime.ts",
  "src/miniapp-validation.ts",
  "dist/src/miniapp-types.js", "dist/src/miniapp-contract-validation.js", "dist/src/miniapp-inventory.js",
  "dist/src/miniapp-semantic-ir.js", "dist/src/miniapp-planning.js", "dist/src/miniapp-target-generation.js",
  "dist/src/miniapp-package-contract.js", "dist/src/miniapp-output-contracts.js", "dist/src/miniapp-skill-runtime.js",
  "dist/src/miniapp-validation.js",
];
const engineImplementationEntries = implementationPaths.map(path => {
  const candidate = resolve(engineRoot, path);
  const relativeCandidate = relative(engineRoot, candidate);
  assert.ok(relativeCandidate && relativeCandidate !== ".." && !relativeCandidate.startsWith(`..${sep}`) && !isAbsolute(relativeCandidate), `${path}: implementation containment failed`);
  const stat = lstatSync(candidate);
  assert.ok(stat.isFile() && !stat.isSymbolicLink(), `${path}: regular implementation file required`);
  const raw = readFileSync(candidate);
  return { path, bytes: raw.byteLength, sha256: `sha256:${createHash("sha256").update(raw).digest("hex")}` };
});
const replayScriptStat = lstatSync(replayScriptPath);
assert.ok(replayScriptStat.isFile() && !replayScriptStat.isSymbolicLink(), "replay script must be a regular non-symlink file");
const replayScriptRaw = readFileSync(replayScriptPath);
const implementationEntries = [
  ...engineImplementationEntries,
  {
    path: "client-packs/frontend-to-miniapp-vue3-wechat-v1/certification/replay-local-runtime.mjs",
    bytes: replayScriptRaw.byteLength,
    sha256: `sha256:${createHash("sha256").update(replayScriptRaw).digest("hex")}`,
  },
].sort((left, right) => left.path < right.path ? -1 : left.path > right.path ? 1 : 0);
const implementationDigest = `sha256:${createHash("sha256").update(
  implementationEntries.map(entry => `${entry.path}\u0000${entry.sha256}\u0000${entry.bytes}`).join("\n"),
  "utf8",
).digest("hex")}`;
const enginePackage = JSON.parse(readFileSync(resolve(engineRoot, "package.json"), "utf8"));
assert.equal(enginePackage.dependencies?.["@vue/compiler-sfc"], "3.5.39", "Vue parser version drift");
assert.equal(enginePackage.devDependencies?.typescript, "5.9.2", "TypeScript parser version drift");
if (expected !== null) {
  assert.equal(expected.runtime_implementation?.digest, implementationDigest, "runtime implementation drift before execution");
}
const runtimeUrl = pathToFileURL(resolve(
  repositoryRoot,
  "engines/frontend-client-engine/dist/src/miniapp-skill-runtime.js",
)).href;
const {
  computeMiniappSourceFileSetDigest,
  runMiniappConversion,
} = await import(runtimeUrl);

const sourceManifestCandidate = resolve(packRoot, "source-snapshots/manifest.json");
assertStrictDescendant(packRoot, sourceManifestCandidate, "source manifest");
const sourceManifestStat = lstatSync(sourceManifestCandidate);
assert.ok(sourceManifestStat.isFile() && !sourceManifestStat.isSymbolicLink(), "source manifest must be a regular non-symlink file");
assert.ok(sourceManifestStat.size <= MAX_CONTROL_FILE_BYTES, "source manifest exceeds bounded replay limit");
const sourceManifestPath = realpathSync(sourceManifestCandidate);
assertStrictDescendant(packRoot, sourceManifestPath, "canonical source manifest");
const sourceManifestRaw = readFileSync(sourceManifestPath);
const sourceManifestDigest = `sha256:${createHash("sha256").update(sourceManifestRaw).digest("hex")}`;
const sourceManifest = JSON.parse(sourceManifestRaw.toString("utf8"));
const exactKeys = (value, keys, label) => {
  assert.ok(value && typeof value === "object" && !Array.isArray(value), `${label}: object required`);
  assert.deepEqual(Object.keys(value).sort(), [...keys].sort(), `${label}: exact keys required`);
};
exactKeys(sourceManifest, [
  "schema_version", "snapshot_id", "source_root", "aggregate_digest", "file_count", "files", "privacy", "source_scripts_executed",
], "source manifest");
assert.equal(sourceManifest.schema_version, 1, "source manifest schema drift");
assert.equal(sourceManifest.source_root, sourceRootRelative, "source root drift");
assert.match(sourceManifest.aggregate_digest, /^sha256:[a-f0-9]{64}$/u, "aggregate digest format");
assert.equal(sourceManifest.source_scripts_executed, false, "replay must not execute source scripts");
assert.ok(Array.isArray(sourceManifest.files) && sourceManifest.files.length > 0 && sourceManifest.files.length <= 100, "bounded source files required");
assert.equal(sourceManifest.file_count, sourceManifest.files.length, "manifest file_count drift");
const seenPaths = new Set();
const seenCasefoldPaths = new Set();
let previousPath = "";
const decoder = new TextDecoder("utf-8", { fatal: true });
const files = sourceManifest.files.map((entry, index) => {
  exactKeys(entry, ["path", "bytes", "sha256"], `source manifest files[${index}]`);
  assert.equal(typeof entry.path, "string", `${index}: path must be a string`);
  const normalizedPath = entry.path.normalize("NFC");
  assert.equal(entry.path, normalizedPath, `${entry.path}: path must already be NFC normalized`);
  assert.ok(!isAbsolute(normalizedPath) && !normalizedPath.includes("\\") && !/[\u0000-\u001f\u007f]/u.test(normalizedPath), `${entry.path}: unsafe path`);
  const segments = normalizedPath.split("/");
  assert.ok(segments.length > 0 && segments.every(segment => segment && segment !== "." && segment !== ".."), `${entry.path}: traversal path`);
  assert.ok(!seenPaths.has(normalizedPath), `${entry.path}: duplicate path`);
  const casefoldPath = normalizedPath.toLowerCase();
  assert.ok(!seenCasefoldPaths.has(casefoldPath), `${entry.path}: case-fold collision`);
  assert.ok(previousPath < normalizedPath, `${entry.path}: manifest paths must be strictly sorted`);
  previousPath = normalizedPath;
  seenPaths.add(normalizedPath);
  seenCasefoldPaths.add(casefoldPath);
  assert.ok(Number.isSafeInteger(entry.bytes) && entry.bytes >= 0 && entry.bytes <= 1_048_576, `${entry.path}: invalid byte count`);
  assert.match(entry.sha256, /^sha256:[a-f0-9]{64}$/u, `${entry.path}: invalid digest`);
  const candidate = resolve(sourceRoot, normalizedPath);
  const relativeCandidate = relative(sourceRoot, candidate);
  assert.ok(relativeCandidate && relativeCandidate !== ".." && !relativeCandidate.startsWith(`..${sep}`) && !isAbsolute(relativeCandidate), `${entry.path}: source containment failed`);
  const candidateStat = lstatSync(candidate);
  assert.ok(candidateStat.isFile() && !candidateStat.isSymbolicLink(), `${entry.path}: regular non-symlink file required`);
  const realCandidate = realpathSync(candidate);
  const realRelative = relative(sourceRoot, realCandidate);
  assert.ok(realRelative && realRelative !== ".." && !realRelative.startsWith(`..${sep}`) && !isAbsolute(realRelative), `${entry.path}: real path escaped source root`);
  const raw = readFileSync(realCandidate);
  assert.equal(raw.byteLength, entry.bytes, `${entry.path}: source byte-count drift`);
  const digest = `sha256:${createHash("sha256").update(raw).digest("hex")}`;
  assert.equal(digest, entry.sha256, `${entry.path}: source digest drift`);
  return { path: normalizedPath, content: decoder.decode(raw) };
});
const snapshotDigest = computeMiniappSourceFileSetDigest(files);
assert.equal(snapshotDigest, sourceManifest.aggregate_digest, "manifest aggregate digest drift");
const byteCount = files.reduce((total, file) => total + Buffer.byteLength(file.content, "utf8"), 0);
const targetProfileRaw = readFileSync(targetProfilePath);
const targetProfileDigest = `sha256:${createHash("sha256").update(targetProfileRaw).digest("hex")}`;
const targetProfile = JSON.parse(targetProfileRaw.toString("utf8"));
const requestedTarget = {
  platform: "wechat",
  platformVersion: "3.9.1",
  toolchainVersion: "1.06.2504010",
};
assert.equal(targetProfile.profile_key, "frontend-to-miniapp-vue3-wechat-v1-target", "target profile identity drift");
assert.equal(targetProfile.framework, "wechat-native-miniapp-candidate", "target framework drift");
assert.deepEqual(targetProfile.versions, [requestedTarget.platformVersion], "target base-library tuple drift");
assert.deepEqual(targetProfile.runtime_versions, [requestedTarget.platformVersion], "target runtime tuple drift");
assert.equal(targetProfile.official_toolchain_version, requestedTarget.toolchainVersion, "target toolchain tuple drift");
assert.deepEqual(targetProfile.toolchain_resolution, {
  requested_platform_version: requestedTarget.platformVersion,
  requested_toolchain_version: requestedTarget.toolchainVersion,
  resolved_toolchain_digest: null,
  evidence_state: "NOT_RUN",
}, "target toolchain resolution must remain explicit and unresolved");
assert.equal(targetProfile.generator_profile_version, "2026-08-20.1", "generator profile tuple drift");
assert.deepEqual(targetProfile.authorization, {
  official_build: false,
  preview: false,
  upload: false,
  review: false,
  release: false,
}, "target authorization must remain exact and deny external effects");
assert.deepEqual(targetProfile.file_model, {
  application_config: "app.json",
  page_config: "<page>.json",
  template_extension: ".wxml",
  style_extension: ".wxss",
  script_extension: ".js",
}, "target file model drift");
const readBoundedRepositoryEntry = (path, maximumBytes = MAX_CONTROL_FILE_BYTES) => {
  const candidate = resolve(repositoryRoot, path);
  assertStrictDescendant(repositoryRoot, candidate, `${path}: evidence-root entry`);
  const stat = lstatSync(candidate);
  assert.ok(stat.isFile() && !stat.isSymbolicLink(), `${path}: regular non-symlink evidence-root entry required`);
  assert.ok(stat.size <= maximumBytes, `${path}: evidence-root entry exceeds bounded size`);
  const canonical = realpathSync(candidate);
  assertStrictDescendant(repositoryRoot, canonical, `${path}: canonical evidence-root entry`);
  const raw = readFileSync(canonical);
  return {
    path,
    bytes: raw.byteLength,
    sha256: `sha256:${createHash("sha256").update(raw).digest("hex")}`,
    raw,
  };
};
const evidenceControlPaths = [
  "client-packs/frontend-to-miniapp-vue3-wechat-v1/pack.json",
  "client-packs/frontend-to-miniapp-vue3-wechat-v1/route-matrix.json",
  "client-packs/frontend-to-miniapp-vue3-wechat-v1/source-snapshots/manifest.json",
  "client-packs/frontend-to-miniapp-vue3-wechat-v1/target-profile/profile.json",
  "client-packs/frontend-to-miniapp-vue3-wechat-v1/acceptance/acceptance-profile.json",
  "client-packs/frontend-to-miniapp-vue3-wechat-v1/ui-ir/model.json",
  "client-packs/frontend-to-miniapp-vue3-wechat-v1/transformations/vue3-todo-to-wechat-native.json",
  "client-packs/frontend-to-miniapp-vue3-wechat-v1/certification/source-build-evidence.json",
  "client-packs/frontend-to-miniapp-vue3-wechat-v1/certification/external-evidence-status.json",
  "client-packs/frontend-to-miniapp-vue3-wechat-v1/certification/certification.json",
  "scripts/batch32/validate_client_pack.py",
  "scripts/batch32/validate_ui_ir.py",
  "scripts/batch32/run_client_gate.py",
  sourceArchiveRelative,
];
const evidenceControlEntries = evidenceControlPaths.map(path => readBoundedRepositoryEntry(
  path,
  path === sourceArchiveRelative ? MAX_SOURCE_ARCHIVE_BYTES : MAX_CONTROL_FILE_BYTES,
));
const evidenceRootEntries = [
  ...implementationEntries,
  ...evidenceControlEntries.map(({ raw: _raw, ...entry }) => entry),
].sort((left, right) => left.path < right.path ? -1 : left.path > right.path ? 1 : 0);
const evidenceRootDigest = `sha256:${createHash("sha256").update(
  evidenceRootEntries.map(entry => `${entry.path}\u0000${entry.sha256}\u0000${entry.bytes}`).join("\n"),
  "utf8",
).digest("hex")}`;
const uiIrEntry = evidenceControlEntries.find(entry => entry.path.endsWith("/ui-ir/model.json"));
const transformationEntry = evidenceControlEntries.find(entry => entry.path.endsWith("/transformations/vue3-todo-to-wechat-native.json"));
assert.ok(uiIrEntry && transformationEntry, "review UI IR and transformation evidence-root entries are required");
const reviewUiIr = JSON.parse(uiIrEntry.raw.toString("utf8"));
const transformation = JSON.parse(transformationEntry.raw.toString("utf8"));
assert.equal(reviewUiIr.schema_version, 1, "review UI IR schema drift");
assert.equal(reviewUiIr.pack_key, "frontend-to-miniapp-vue3-wechat-v1", "review UI IR pack drift");
assert.equal(reviewUiIr.source_snapshot_digest, snapshotDigest, "review UI IR source digest drift");
const reviewGroups = [
  "routes", "views", "components", "states", "actions", "effects", "forms", "bindings",
  "permissions", "resources", "design_tokens", "accessibility",
];
const reviewNodes = reviewGroups.flatMap(group => {
  assert.ok(Array.isArray(reviewUiIr[group]), `review UI IR ${group} must be an array`);
  return reviewUiIr[group];
});
const reviewNodeIds = reviewNodes.map(node => node.id);
assert.equal(new Set(reviewNodeIds).size, reviewNodeIds.length, "review UI IR node IDs must be unique");
const sourceManifestByPath = new Map(sourceManifest.files.map(entry => [entry.path, entry]));
const reviewSourcePrefix = `${sourceRootRelative}/`;
const reviewSourcePaths = new Map(reviewNodes.map(node => {
  assert.ok(Array.isArray(node.source_refs) && node.source_refs.length > 0, `${node.id}: review source_refs required`);
  const normalized = node.source_refs.map((sourceRef, index) => {
    assert.equal(typeof sourceRef, "string", `${node.id}: source_refs[${index}] must be a string`);
    assert.ok(sourceRef.startsWith(reviewSourcePrefix), `${node.id}: source ref must stay inside the pinned source snapshot`);
    const sourcePath = sourceRef.slice(reviewSourcePrefix.length);
    assert.ok(sourcePath && sourceManifestByPath.has(sourcePath), `${node.id}: source ref is absent from the source manifest`);
    return sourcePath;
  });
  assert.equal(new Set(normalized).size, normalized.length, `${node.id}: duplicate review source refs`);
  return [node.id, normalized.sort()];
}));
assert.deepEqual(
  [...reviewUiIr.source_map.map(entry => entry.node_id)].sort(),
  [...reviewNodeIds].sort(),
  "review UI IR source map must cover every declared node exactly once",
);
assert.equal(transformation.source_snapshot_digest, snapshotDigest, "transformation source digest drift");
assert.equal(transformation.input_contract, "ui-ir/model.json", "transformation input contract drift");
assert.equal(transformation.target_profile, "target-profile/profile.json", "transformation target profile drift");
assert.deepEqual(transformation.fallbacks, { webview: "DENIED", full_page_canvas: "DENIED", silent_drop: "DENIED" });
assert.ok(Array.isArray(transformation.mappings) && transformation.mappings.length === 8, "eight declared transformation mappings required");
const expectedTransformationContracts = new Map([
  ["route.home", "app.json pages[0] equals pages/index/index and pages/index/index.json exists"],
  ["component.app-shell", "pages/index/index.wxml contains the source-traced application shell"],
  ["component.todo-input", "pages/index/index.wxml input value binds text and bindinput targets handleInput0"],
  ["component.add-button", "pages/index/index.wxml button disabled binds !canSubmit0 and bindtap targets handleSubmit0"],
  ["component.todo-list", "pages/index/index.wxml iterates itemsRender with __elmosKey and pages/index/index.js derives each key from item plus source index"],
  ["effect.add-todo", "pages/index/index.js trims text appends one value persists application items and clears text"],
  ["token.app-shell", "pages/index/index.wxss scopes .app-shell with the deterministic scope class and preserves max-width auto margins and padding"],
  ["permission.local-only", "adapters/platform.js exposes no network identity payment upload review or release capability"],
]);
assert.deepEqual(
  transformation.mappings.map(mapping => mapping.source_node).sort(),
  [...expectedTransformationContracts.keys()].sort(),
  "transformation mapping identities must be exact",
);
for (const mapping of transformation.mappings) {
  assert.ok(reviewNodeIds.includes(mapping.source_node), `${mapping.source_node}: transformation source node is not in review UI IR`);
  assert.equal(
    mapping.target_contract,
    expectedTransformationContracts.get(mapping.source_node),
    `${mapping.source_node}: target_contract drift`,
  );
}
const request = {
  schemaVersion: "1.0",
  requestId: "conv-vue3-todo-wechat",
  tenantId: "tenant-local-engineering",
  source: {
    root: "source-snapshots/vue3-todo-v1.0.1",
    revision: sourceManifest.aggregate_digest,
    snapshotDigest,
    sourceLabel: "vue3",
    frameworkVersion: "3.5.39",
    languageVersion: "5.9.2",
    runtimeVersion: "26.0.0",
    buildToolVersion: "6.0.0",
  },
  targets: [requestedTarget],
  policy: {
    priority: "balanced",
    webviewFallback: "deny",
    fullPageCanvasFallback: "deny",
    unsupportedPolicy: "block",
    limits: { maxFileCount: 100, maxFileBytes: 1_048_576, maxTotalBytes: 10_485_760 },
    secretReferences: [],
  },
  evidence: [{
    role: "source-snapshot",
    uri: "artifact://frontend-to-miniapp/vue3-todo",
    digest: snapshotDigest,
    state: "PASSED",
    executor: "local-frontend-client-engine",
    verifier: "local-deterministic-validator",
    synthetic: true,
    byteCount,
  }],
};
assert.equal(process.versions.node, request.source.runtimeVersion, "local replay Node version drift");
const run = runMiniappConversion({ schemaVersion: "1.0", request, files });
assert.equal(run.generatedProjects.length, 1);
const project = run.generatedProjects[0];
assert.equal(project.platform, request.targets[0].platform, "generated platform drift");
assert.equal(project.platformVersion, request.targets[0].platformVersion, "generated platform version drift");
assert.equal(project.toolchainVersion, request.targets[0].toolchainVersion, "generated toolchain version drift");
assert.equal(project.profileVersion, targetProfile.generator_profile_version, "generated profile version drift");
const one = (values, label) => {
  assert.equal(values.length, 1, `${label}: exactly one runtime subject is required`);
  return values[0];
};
const runtimeRoute = one(run.semanticIr.routes.filter(route => route.path === "/"), "root route");
const appShell = one(run.semanticIr.components.filter(component => component.sourceTag === "main" && component.sourceRefs.some(ref => ref.path === "src/App.vue")), "app shell");
const homeView = one(run.semanticIr.components.filter(component => component.sourceTag === "section" && component.sourceRefs.some(ref => ref.path === "src/views/HomeView.vue")), "home view");
const todoInput = one(run.semanticIr.components.filter(component => component.sourceTag === "input" && component.modelBinding === "text"), "todo input");
const addButton = one(run.semanticIr.components.filter(component => component.sourceTag === "button" && component.textContent === "Add"), "add button");
const todoList = one(run.semanticIr.components.filter(component => component.collectionBinding?.collection === "todos.items"), "todo list");
const todoText = one(run.semanticIr.states.filter(state => state.name === "text" && state.scope === "component"), "todo text state");
const todoItems = one(run.semanticIr.states.filter(state => state.name === "items" && state.scope === "application"), "todo items state");
const todoInteraction = one(run.semanticIr.interactions.filter(interaction => interaction.draftStateId === todoText.id
  && interaction.collectionStateId === todoItems.id
  && interaction.inputComponentId === todoInput.id
  && interaction.submitComponentId === addButton.id
  && interaction.listComponentId === todoList.id), "todo interaction");
const todoForm = one(run.semanticIr.forms.filter(form => form.sourceRefs.some(ref => ref.path === "src/views/HomeView.vue")), "todo form");
const appShellStyle = one(run.semanticIr.styles.filter(style => style.selector === ".app-shell"), "app shell style");
const templateEntry = one(Object.entries(project.files).filter(([path]) => path.endsWith(".wxml")), "generated WXML");
const styleEntry = one(Object.entries(project.files).filter(([path]) => path.endsWith(".wxss") && path.startsWith("pages/")), "generated page WXSS");
const scriptEntry = one(Object.entries(project.files).filter(([path]) => path.endsWith(".js") && path.startsWith("pages/")), "generated page script");
const adapterSource = project.files["adapters/platform.js"] ?? "";
const appManifest = JSON.parse(project.files["app.json"] ?? "{}");
assert.equal(transformation.local_contract_state, "LOCAL_REPLAY_VERIFIED_DIRECTIONAL_MAPPING_ONLY_NOT_CERTIFIED", "transformation local contract state drift");
assert.deepEqual(transformation.execution_binding, {
  state: "PASSED_LOCAL_SELF_ATTESTED_MAPPING_ONLY",
  scope: "one-way review UI IR to source-derived runtime subjects and content-addressed generated artifacts",
  evidence: "certification/local-runtime-candidate-evidence.json",
  source_snapshot_digest: snapshotDigest,
  runtime_input_digest: run.requestDigest,
  runtime_semantic_ir_digest: run.semanticIr.deterministicDigest,
  runtime_plan_digest: run.plan.deterministicDigest,
  generated_project_digest: project.deterministicDigest,
  runtime_mapping_coverage: {
    declared_mappings: 8,
    verified_mappings: 8,
    review_nodes: reviewNodeIds.length,
    review_node_source_ref_coverage: 1,
  },
  full_runtime_ir_reverse_equivalence: "NOT_EVALUATED",
  independent_verification: "NOT_RUN",
  official_runtime_verification: "NOT_RUN",
}, "transformation execution binding must match this exact one-way local replay");
assert.equal(transformation.local_runtime_evidence, "certification/local-runtime-candidate-evidence.json", "transformation local evidence path drift");
assert.equal(transformation.official_build_state, "NOT_RUN", "official build must remain NOT_RUN");
assert.equal(transformation.runtime_equivalence_state, "LOCAL_DIRECTIONAL_MAPPING_ONLY_FULL_REVERSE_NOT_EVALUATED", "full reverse runtime equivalence must remain unevaluated");
assert.equal(transformation.certification, "NOT_CERTIFIED", "transformation certification must remain NOT_CERTIFIED");
const artifactByPath = new Map(project.artifacts.map(artifact => {
  assert.equal(typeof project.files[artifact.path], "string", `${artifact.path}: generated artifact content missing`);
  const raw = Buffer.from(project.files[artifact.path], "utf8");
  assert.equal(artifact.bytes, raw.byteLength, `${artifact.path}: generated artifact byte count drift`);
  assert.equal(
    artifact.sha256,
    `sha256:${createHash("sha256").update(raw).digest("hex")}`,
    `${artifact.path}: generated artifact digest drift`,
  );
  return [artifact.path, { path: artifact.path, sha256: artifact.sha256, bytes: artifact.bytes }];
}));
assert.equal(artifactByPath.size, project.artifacts.length, "generated artifact paths must be unique");
const sourceManifestArtifact = {
  path: "source-snapshots/manifest.json",
  sha256: sourceManifestDigest,
  bytes: sourceManifestRaw.byteLength,
};
const bindTargetArtifacts = (paths, label) => paths.map(path => {
  if (path === sourceManifestArtifact.path) return sourceManifestArtifact;
  const artifact = artifactByPath.get(path);
  assert.ok(artifact, `${label}: generated target artifact ${path} is missing`);
  return artifact;
});

const templateLines = new Set(templateEntry[1].split("\n").map(line => line.trim()).filter(Boolean));
const stylePlan = one(run.plan.styles.filter(item => item.platform === "wechat"), "WeChat style plan");
const appShellRule = one(stylePlan.rules.filter(rule => rule.styleId === appShellStyle.id), "app shell style rule");
assert.deepEqual(appManifest.pages, ["pages/index/index"], "route.home must be the only emitted WeChat page");
assert.deepEqual(JSON.parse(project.files["pages/index/index.json"] ?? "null"), {
  navigationBarTitleText: "Todo",
  usingComponents: {},
}, "route.home page configuration drift");
assert.match(appShellStyle.scopeClass ?? "", /^elmos-scope-[a-f0-9]{12}$/u, "app shell deterministic scope class missing");
assert.deepEqual(appShell.styleScopeClasses, [appShellStyle.scopeClass], "app shell template/style scope binding drift");
assert.deepEqual(appShellStyle.declarations, { margin: "0 auto", "max-width": "640px", padding: "16px" }, "source app shell layout token drift");
assert.equal(appShellRule.selector, `.app-shell.${appShellStyle.scopeClass}`, "scoped app shell selector drift");
assert.deepEqual(appShellRule.declarations, { margin: "0 auto", "max-width": "1280rpx", padding: "32rpx" }, "lowered app shell layout token drift");
const exactAppShellRule = `${appShellRule.selector} {\n  margin: 0 auto;\n  max-width: 1280rpx;\n  padding: 32rpx;\n}`;
assert.ok(styleEntry[1].includes(exactAppShellRule), "generated WXSS must contain the exact scoped app shell rule");
assert.ok(templateLines.has(`<view class="elmos-node app-shell ${appShellStyle.scopeClass}" data-source-node="${appShell.id}" aria-role="main">`), "generated WXML app shell opening tag drift");
assert.ok(templateLines.has(`<input class="elmos-control" data-source-node="${todoInput.id}" aria-label="Todo text" value="{{text}}" bindinput="handleInput0" />`), "generated WXML todo input contract drift");
assert.ok(templateLines.has(`<button class="elmos-control" data-source-node="${addButton.id}" disabled="{{!canSubmit0}}" bindtap="handleSubmit0">Add</button>`), "generated WXML add button contract drift");
assert.ok(templateLines.has('<block wx:for="{{itemsRender}}" wx:for-item="item" wx:key="__elmosKey">'), "generated WXML todo iteration contract drift");
assert.ok(templateLines.has(`<view class="elmos-list-item" data-source-node="${todoList.id}" aria-role="listitem"><text>{{item.value}}</text></view>`), "generated WXML todo item contract drift");
assert.equal(todoInput.modelBinding, "text", "typed todo input model binding drift");
assert.equal(todoInteraction.draftStateId, todoText.id, "typed todo draft-state edge drift");
assert.equal(todoInteraction.collectionStateId, todoItems.id, "typed todo collection-state edge drift");
assert.equal(todoInteraction.inputComponentId, todoInput.id, "typed todo input edge drift");
assert.equal(todoInteraction.submitComponentId, addButton.id, "typed todo submit edge drift");
assert.equal(todoInteraction.listComponentId, todoList.id, "typed todo list edge drift");
assert.deepEqual(todoList.collectionBinding, {
  collection: "todos.items",
  itemAlias: "item",
  indexAlias: "index",
  keyExpression: "`${item}-${index}`",
  valueExpression: "item",
}, "typed todo item-plus-index binding drift");
assert.equal(todoInteraction.ignoreBlank, true, "typed blank-todo rejection drift");
assert.equal(todoInteraction.clearAfterSubmit, true, "typed todo clear-after-submit drift");
assert.equal(todoForm.binding, "template-event-binding", "typed todo form binding drift");
const itemIndexKeyExpression = '__elmosKey: `${item}-${index}`';
assert.equal(scriptEntry[1].split(itemIndexKeyExpression).length - 1, 2, "item-plus-source-index key must be derived on load and submit");
assert.ok(scriptEntry[1].includes('const value = String(this.data.text ?? "").trim();'), "todo submit must trim the draft value");
assert.ok(scriptEntry[1].includes("const next = [...current, value];"), "todo submit must append exactly one trimmed value");
assert.ok(scriptEntry[1].includes('if (application && application.globalData) application.globalData.items = next;'), "todo submit must persist application-scoped items");
assert.ok(scriptEntry[1].includes('this.setData({ items: next, itemsRender: rendered, text: "", canSubmit0: false });'), "todo submit must atomically render and clear the draft");
assert.ok(scriptEntry[1].includes('this.setData({ text: value, canSubmit0: value.trim().length > 0 });'), "todo input must derive disabled state from the trimmed value");
assert.equal(project.files["app.js"]?.includes('"items":[]'), true, "application-scoped todo state drift");
assert.equal(adapterSource, [
  '"use strict";',
  'const platformApi = typeof wx === "object" ? wx : null;',
  "module.exports = Object.freeze({",
  '  platform: "wechat",',
  "});",
  "",
].join("\n"), "zero-capability platform adapter drift");
assert.equal(run.semanticIr.capabilities.length, 0, "local-only fixture must not declare platform capabilities");
assert.equal(run.sourceFileSetDigest, snapshotDigest, "runtime source file-set digest drift");

const runtimeSourcePathsFor = (subjects, reviewNodeId) => {
  const sourcePaths = subjects.flatMap(subject => {
    assert.ok(subject && typeof subject === "object", `${reviewNodeId}: runtime subject object required`);
    assert.ok(Array.isArray(subject.sourceRefs), `${reviewNodeId}: runtime subject sourceRefs required`);
    return subject.sourceRefs.map(sourceRef => {
      const manifestEntry = sourceManifestByPath.get(sourceRef.path);
      assert.ok(manifestEntry, `${reviewNodeId}: runtime source ref ${sourceRef.path} is absent from the source manifest`);
      assert.equal(sourceRef.sha256, manifestEntry.sha256, `${reviewNodeId}: runtime source ref digest drift for ${sourceRef.path}`);
      return sourceRef.path;
    });
  });
  return [...new Set(sourcePaths)].sort();
};
const crosswalkItem = ({ reviewNodeId, runtimeSubjects = [], runtimeSubjectIds, targetArtifactPaths, manifestOnly = false }) => {
  const reviewPaths = reviewSourcePaths.get(reviewNodeId);
  assert.ok(reviewPaths, `${reviewNodeId}: review source binding missing`);
  const runtimePaths = runtimeSourcePathsFor(runtimeSubjects, reviewNodeId);
  if (!manifestOnly) {
    assert.ok(runtimePaths.length > 0, `${reviewNodeId}: runtime source refs required`);
    for (const path of reviewPaths) {
      assert.ok(runtimePaths.includes(path), `${reviewNodeId}: review source ${path} is not covered by runtime source refs`);
    }
  }
  const subjectIds = runtimeSubjectIds ?? runtimeSubjects.map(subject => subject.id);
  assert.ok(subjectIds.length > 0 && subjectIds.every(value => typeof value === "string" && value), `${reviewNodeId}: runtime subject IDs required`);
  return {
    review_node_id: reviewNodeId,
    runtime_subject_ids: subjectIds,
    review_source_paths: reviewPaths,
    runtime_source_paths: runtimePaths,
    source_manifest_entries: reviewPaths.map(path => {
      const entry = sourceManifestByPath.get(path);
      return { path, sha256: entry.sha256, bytes: entry.bytes };
    }),
    source_ref_coverage: 1,
    source_binding: manifestOnly ? "SOURCE_MANIFEST_ONLY_NEGATIVE_OR_RESOURCE_CONTRACT" : "RUNTIME_SOURCE_REFS_AND_SOURCE_MANIFEST",
    target_artifacts: bindTargetArtifacts(targetArtifactPaths, reviewNodeId),
    verified: true,
  };
};
const crosswalk = [
  crosswalkItem({ reviewNodeId: "route.home", runtimeSubjects: [runtimeRoute], targetArtifactPaths: ["app.json", "pages/index/index.json"] }),
  crosswalkItem({ reviewNodeId: "view.app-shell", runtimeSubjects: [appShell], targetArtifactPaths: [templateEntry[0]] }),
  crosswalkItem({ reviewNodeId: "view.home", runtimeSubjects: [homeView], targetArtifactPaths: [templateEntry[0]] }),
  crosswalkItem({ reviewNodeId: "component.app-shell", runtimeSubjects: [appShell], targetArtifactPaths: [templateEntry[0]] }),
  crosswalkItem({ reviewNodeId: "component.home-view", runtimeSubjects: [homeView], targetArtifactPaths: [templateEntry[0]] }),
  crosswalkItem({ reviewNodeId: "component.todo-input", runtimeSubjects: [todoInput], targetArtifactPaths: [templateEntry[0], scriptEntry[0]] }),
  crosswalkItem({ reviewNodeId: "component.add-button", runtimeSubjects: [addButton], targetArtifactPaths: [templateEntry[0], scriptEntry[0]] }),
  crosswalkItem({ reviewNodeId: "component.todo-list", runtimeSubjects: [todoList], targetArtifactPaths: [templateEntry[0], scriptEntry[0]] }),
  crosswalkItem({ reviewNodeId: "state.todo-text", runtimeSubjects: [todoText], targetArtifactPaths: [scriptEntry[0]] }),
  crosswalkItem({ reviewNodeId: "state.todo-items", runtimeSubjects: [todoItems], targetArtifactPaths: ["app.js", scriptEntry[0]] }),
  crosswalkItem({ reviewNodeId: "action.input-todo", runtimeSubjects: [todoInteraction], targetArtifactPaths: [scriptEntry[0]] }),
  crosswalkItem({ reviewNodeId: "action.submit-todo", runtimeSubjects: [todoInteraction], targetArtifactPaths: [scriptEntry[0]] }),
  crosswalkItem({ reviewNodeId: "effect.add-todo", runtimeSubjects: [todoInteraction], targetArtifactPaths: [scriptEntry[0]] }),
  crosswalkItem({ reviewNodeId: "form.todo-entry", runtimeSubjects: [todoForm], targetArtifactPaths: [templateEntry[0], scriptEntry[0]] }),
  crosswalkItem({ reviewNodeId: "binding.todo-text", runtimeSubjects: [todoInteraction, todoInput], targetArtifactPaths: [templateEntry[0], scriptEntry[0]] }),
  crosswalkItem({ reviewNodeId: "permission.local-only", runtimeSubjectIds: ["policy.no-declared-platform-capabilities"], targetArtifactPaths: ["adapters/platform.js"], manifestOnly: true }),
  crosswalkItem({ reviewNodeId: "resource.source-snapshot", runtimeSubjectIds: [snapshotDigest], targetArtifactPaths: [sourceManifestArtifact.path], manifestOnly: true }),
  crosswalkItem({ reviewNodeId: "token.app-shell", runtimeSubjects: [appShellStyle], targetArtifactPaths: [styleEntry[0]] }),
  crosswalkItem({ reviewNodeId: "a11y.todo-input-label", runtimeSubjects: [todoInput], targetArtifactPaths: [templateEntry[0]] }),
  crosswalkItem({ reviewNodeId: "a11y.disabled-state", runtimeSubjects: [addButton, todoText, todoInteraction], targetArtifactPaths: [templateEntry[0], scriptEntry[0]] }),
];
assert.deepEqual(crosswalk.map(item => item.review_node_id).sort(), [...reviewNodeIds].sort(), "runtime crosswalk must cover every review UI IR node exactly once");
for (const item of crosswalk) assert.equal(item.verified, true, `${item.review_node_id}: local runtime crosswalk failed`);
const declaredTransformationArtifactPaths = new Map([
  ["route.home", ["app.json", "pages/index/index.json"]],
  ["component.app-shell", [templateEntry[0]]],
  ["component.todo-input", [templateEntry[0], scriptEntry[0]]],
  ["component.add-button", [templateEntry[0], scriptEntry[0]]],
  ["component.todo-list", [templateEntry[0], scriptEntry[0]]],
  ["effect.add-todo", [scriptEntry[0]]],
  ["token.app-shell", [styleEntry[0]]],
  ["permission.local-only", ["adapters/platform.js"]],
]);
const declaredTransformationBindings = transformation.mappings.map(mapping => ({
  source_node: mapping.source_node,
  target_contract: mapping.target_contract,
  target_artifacts: bindTargetArtifacts(declaredTransformationArtifactPaths.get(mapping.source_node), mapping.source_node),
  verified: true,
}));
assert.equal(declaredTransformationBindings.length, 8, "all declared transformation mappings must be bound to artifacts");
const countStates = values => Object.fromEntries(
  [...new Set(values)].sort().map(state => [state, values.filter(item => item === state).length]),
);
const observed = {
  schema_version: 1,
  evidence_key: "vue3-todo-wechat-local-runtime-2026-08-20",
  scope: "bounded local conversion runtime and generated-candidate static validation",
  source: {
    archive_path: sourceArchiveRelative,
    archive_sha256: sourceArchiveDigest,
    archive_bytes: sourceArchiveRaw.byteLength,
    manifest_sha256: sourceManifestDigest,
    manifest_bytes: sourceManifestRaw.byteLength,
    snapshot_id: sourceManifest.snapshot_id,
    privacy: sourceManifest.privacy,
    manifest_aggregate_digest: sourceManifest.aggregate_digest,
    runtime_file_set_digest: snapshotDigest,
    file_count: files.length,
    byte_count: byteCount,
    source_scripts_executed: false,
  },
  runtime_implementation: {
    digest: implementationDigest,
    file_count: implementationEntries.length,
    node_version: process.versions.node,
    typescript_version: enginePackage.devDependencies.typescript,
    vue_compiler_sfc_version: enginePackage.dependencies["@vue/compiler-sfc"],
  },
  evidence_root: {
    digest: evidenceRootDigest,
    entry_count: evidenceRootEntries.length,
    entries: evidenceRootEntries,
  },
  request: {
    request_id: request.requestId,
    request_digest: run.requestDigest,
    source_revision: request.source.revision,
    target: request.targets[0],
    target_profile_digest: targetProfileDigest,
    target_profile: {
      profile_key: targetProfile.profile_key,
      framework: targetProfile.framework,
      versions: targetProfile.versions,
      runtime_versions: targetProfile.runtime_versions,
      generator_profile_version: targetProfile.generator_profile_version,
      official_toolchain_version: targetProfile.official_toolchain_version,
      authorization: targetProfile.authorization,
      file_model: targetProfile.file_model,
    },
  },
  conversion: {
    run_id: run.runId,
    deterministic_digest: run.deterministicDigest,
    analysis_digest: run.analysis.deterministicDigest,
    semantic_ir_digest: run.semanticIr.deterministicDigest,
    plan_digest: run.plan.deterministicDigest,
    checkpoint_digest: run.checkpoint.checkpointDigest,
  },
  analysis: {
    parser: run.analysis.parser,
    coverage: run.analysis.coverage,
    parsed_files: run.analysis.parsedFiles,
    failed_files: run.analysis.failedFiles,
    component_count: run.analysis.components.length,
    route_count: run.analysis.routes.length,
    state_count: run.analysis.states.length,
    findings: run.analysis.findings,
  },
  semantic_ir: {
    profile: run.semanticIr.profile,
    node_count: run.semanticIr.nodes.length,
    trace_coverage: run.semanticIr.coverage.tracedNodes,
    batch32_pack_model: "ui-ir/model.json is a separate 20-node review model, not this runtime IR",
  },
  review_model_binding: {
    ui_ir_digest: uiIrEntry.sha256,
    transformation_digest: transformationEntry.sha256,
    review_node_count: reviewNodeIds.length,
    review_node_mapping_coverage: 1,
    declared_transformation_mapping_count: transformation.mappings.length,
    declared_transformation_mapping_coverage: 1,
    directional_scope: transformation.execution_binding.scope,
    declared_transformation_bindings: declaredTransformationBindings,
    crosswalk,
    state: "PASSED_LOCAL_SELF_ATTESTED_MAPPING_ONLY",
    full_runtime_ir_reverse_equivalence: "NOT_EVALUATED",
    independent_verification: "NOT_RUN",
    official_runtime_verification: "NOT_RUN",
  },
  plan: { summary: run.plan.summary, findings: run.plan.findings },
  generated_project: {
    platform: project.platform,
    platform_version: project.platformVersion,
    toolchain_version: project.toolchainVersion,
    profile_version: project.profileVersion,
    deterministic_digest: project.deterministicDigest,
    file_count: Object.keys(project.files).length,
    static_validation: project.staticValidation,
    official_build: project.officialBuild,
    device_runtime: project.deviceRuntime,
    certification: project.certification,
    artifacts: project.artifacts.map(({ path, sha256, bytes }) => ({ path, sha256, bytes })),
  },
  gates: Object.fromEntries(run.gates.map(({ gate, state }) => [gate, state])),
  task_states: countStates(run.taskRecords.map(record => record.state)),
  local_engineering: run.localEngineering,
  readiness: run.readiness,
  certification: run.certification,
  external_evidence: "NOT_RUN",
  official_wechat_build_preview_device_upload_review_release: "NOT_RUN",
  replay: "pnpm --dir engines/frontend-client-engine run build && node client-packs/frontend-to-miniapp-vue3-wechat-v1/certification/replay-local-runtime.mjs --check",
};

if (expected !== null) assert.deepEqual(observed, expected, "local runtime evidence drift");
process.stdout.write(arguments_[0] === "--check"
  ? `${JSON.stringify({ evidence_key: observed.evidence_key, run_id: observed.conversion.run_id, project_digest: observed.generated_project.deterministic_digest, local_engineering: observed.local_engineering, readiness: observed.readiness, certification: observed.certification })}\n`
  : `${JSON.stringify(observed, null, 2)}\n`);

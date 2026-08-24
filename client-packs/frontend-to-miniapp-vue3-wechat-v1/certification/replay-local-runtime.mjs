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
const sourceRootRelative = "skills/elmos-frontend-to-miniapp-skills-v1.0.0/examples/vue3-todo/source";
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
  "dist/src/miniapp-types.js", "dist/src/miniapp-contract-validation.js", "dist/src/miniapp-inventory.js",
  "dist/src/miniapp-semantic-ir.js", "dist/src/miniapp-planning.js", "dist/src/miniapp-target-generation.js",
  "dist/src/miniapp-package-contract.js", "dist/src/miniapp-output-contracts.js", "dist/src/miniapp-skill-runtime.js",
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
assert.deepEqual(targetProfile.versions, [`wechat-base-library-${requestedTarget.platformVersion}-requested-NOT_RUN`], "target base-library tuple drift");
assert.deepEqual(targetProfile.runtime_versions, [`wechat-base-library-${requestedTarget.platformVersion}-requested-NOT_RUN`], "target runtime tuple drift");
assert.equal(targetProfile.official_toolchain_version, `wechat-devtools-${requestedTarget.toolchainVersion}-NOT_RUN`, "target toolchain tuple drift");
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
const request = {
  schemaVersion: "1.0",
  requestId: "conv-vue3-todo-wechat",
  tenantId: "tenant-local-engineering",
  source: {
    root: "examples/vue3-todo/source",
    revision: expectedSourceArchiveDigest.slice("sha256:".length),
    snapshotDigest,
    sourceLabel: "vue3",
    frameworkVersion: "3.5.39",
    languageVersion: "5.9.2",
    runtimeVersion: "26.0.0",
    buildToolVersion: "5.9.2",
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
    synthetic: false,
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

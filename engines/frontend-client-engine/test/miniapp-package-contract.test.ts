import assert from "node:assert/strict";
import {
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  statSync,
  symlinkSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

import {
  canonicalizeMiniappPackageConversionInput,
  compileMiniappPackageConversionInput,
  MiniappPackageContractError,
  validateMiniappPackageConversionInput,
  validateMiniappPackageRequest,
} from "../src/miniapp-package-contract.js";
import {
  materializeMiniappCombinedOutputIndex,
  materializeMiniappDeclaredOutputs,
  materializeMiniappGeneratedProjectArtifacts,
} from "../src/miniapp-output-contracts.js";
import { materializeMiniappRun } from "../src/miniapp-cli.js";
import {
  computeMiniappSourceFileSetDigest,
  handleMiniappSkillRequest,
  type MiniappPackageConversionRun,
} from "../src/miniapp-skill-runtime.js";
import type { MiniappInventoryInputFile } from "../src/miniapp-types.js";

const immutableRevision = "0123456789abcdef0123456789abcdef01234567";

const vueFiles: readonly MiniappInventoryInputFile[] = [
  {
    path: "apps/client/package.json",
    content: JSON.stringify({
      name: "package-contract-fixture",
      dependencies: { vue: "3.5.39" },
      devDependencies: { typescript: "5.9.2", vite: "6.0.0" },
      engines: { node: "24.3.0" },
    }),
  },
  {
    path: "apps/client/package-lock.json",
    content: JSON.stringify({
      name: "package-contract-fixture",
      lockfileVersion: 3,
      packages: {
        "": {
          dependencies: { vue: "3.5.39" },
          devDependencies: { typescript: "5.9.2", vite: "6.0.0" },
          engines: { node: "24.3.0" },
        },
        "node_modules/typescript": { version: "5.9.2" },
        "node_modules/vue": { version: "3.5.39" },
        "node_modules/vite": { version: "6.0.0" },
      },
    }),
  },
  {
    path: "apps/client/src/App.vue",
    content: '<template><div aria-label="Package contract">Package contract</div></template>',
  },
  { path: "apps/client/src/main.ts", content: 'import { createApp } from "vue"; import App from "./App.vue"; createApp(App).mount("#app");' },
];

const selectedVueFiles: readonly MiniappInventoryInputFile[] = vueFiles.map(file => ({
  ...file,
  path: file.path.slice("apps/client/".length),
}));

function packageRequest(): Record<string, unknown> {
  return {
    request_id: "conv-package-contract",
    tenant_id: "tenant-package",
    source: {
      root: "./apps/client",
      revision: "release-2026-08",
      framework_hint: "vue3",
      include: ["src/**/*", "package.json", "package-lock.json"],
      exclude: ["dist/**", "node_modules/**"],
    },
    targets: ["alipay", "wechat"],
    strategy: {
      priority: "balanced",
      webview_fallback: "approval-required",
      full_page_canvas_fallback: "deny",
      unsupported_policy: "ask-decision",
    },
    quality: {
      critical_flow_pass_rate: 1,
      visual_similarity_min: 0.97,
      max_auto_repair_iterations: 4,
      performance_policy_ref: "plans/strict-performance.yaml",
    },
    release: {
      mode: "preview",
      human_approval_required: true,
      credential_refs: {
        wechat: "vault://tenant-package/wechat/build",
        alipay: "kms://tenant-package/alipay/signing-key",
      },
    },
    metadata: {
      owner: "client-modernization",
      nested: { approved: false, ticket: null },
    },
  };
}

function packageInput(files: readonly MiniappInventoryInputFile[] = vueFiles): Record<string, unknown> {
  const snapshotDigest = computeMiniappSourceFileSetDigest(files);
  const byteCount = files.reduce((total, file) => total + (typeof file.content === "string"
    ? Buffer.byteLength(file.content, "utf8")
    : file.content.byteLength), 0);
  return {
    packageRequest: packageRequest(),
    files,
    versionBindings: {
      source: {
        immutableRevision,
        frameworkVersion: "3.5.39",
        languageVersion: "5.9.2",
        runtimeVersion: "24.3.0",
        buildToolVersion: "6.0.0",
      },
      targets: [
        { platform: "alipay", platformVersion: "2.10.2", toolchainVersion: "3.9.4" },
        { platform: "wechat", platformVersion: "3.9.1", toolchainVersion: "1.06.2504010" },
      ],
      inventoryLimits: {
        maxFileCount: 100,
        maxFileBytes: 1_048_576,
        maxTotalBytes: 8_388_608,
      },
    },
    evidenceBindings: [{
      role: "source-snapshot",
      uri: "artifact://package-contract/source-snapshot",
      digest: snapshotDigest,
      state: "PASSED",
      executor: "package-contract-executor",
      verifier: "package-contract-verifier",
      synthetic: false,
      byteCount,
    }],
  };
}

test("valid package snake_case requests compile to exact internal execution input and preserve policy", () => {
  const validated = validateMiniappPackageConversionInput(packageInput());
  assert.deepEqual(validated.packageRequest.targets, ["wechat", "alipay"]);
  assert.equal(validated.packageRequest.metadata.owner, "client-modernization");

  const compiled = compileMiniappPackageConversionInput(validated);
  const request = compiled.executionInput.request as {
    readonly source: { readonly root: string; readonly revision: string; readonly snapshotDigest: string; readonly sourceLabel: string };
    readonly targets: readonly { readonly platform: string; readonly platformVersion: string; readonly toolchainVersion: string }[];
  };
  assert.equal(request.source.root, "apps/client");
  assert.equal(request.source.revision, immutableRevision);
  assert.equal(request.source.sourceLabel, "vue3");
  assert.equal(request.source.snapshotDigest, computeMiniappSourceFileSetDigest(selectedVueFiles));
  assert.equal(compiled.sourceSnapshotDigest, computeMiniappSourceFileSetDigest(vueFiles));
  assert.equal(
    compiled.selectedSourceFileSetDigest,
    computeMiniappSourceFileSetDigest(selectedVueFiles),
  );
  assert.deepEqual(request.targets, [
    { platform: "wechat", platformVersion: "3.9.1", toolchainVersion: "1.06.2504010" },
    { platform: "alipay", platformVersion: "2.10.2", toolchainVersion: "3.9.4" },
  ]);
  assert.deepEqual(compiled.policyBinding.quality, {
    criticalFlowPassRate: 1,
    visualSimilarityMin: 0.97,
    maxAutoRepairIterations: 4,
    performancePolicyRef: "plans/strict-performance.yaml",
  });
  assert.deepEqual(compiled.policyBinding.release, {
    mode: "preview",
    humanApprovalRequired: true,
    credentialReferences: [
      { name: "alipay", reference: "kms://tenant-package/alipay/signing-key" },
      { name: "wechat", reference: "vault://tenant-package/wechat/build" },
    ],
  });
  assert.equal(compiled.policyBinding.metadata.nested !== null, true);
  assert.match(compiled.packageRequestDigest, /^sha256:[a-f0-9]{64}$/u);
  assert.match(compiled.inputBindingDigest, /^sha256:[a-f0-9]{64}$/u);
});

test("mutable revisions and every requested target require exact bindings", () => {
  const missingRevision = packageInput();
  delete ((missingRevision.versionBindings as Record<string, unknown>).source as Record<string, unknown>).immutableRevision;
  assert.throws(() => validateMiniappPackageConversionInput(missingRevision), (error: unknown) =>
    error instanceof MiniappPackageContractError
      && error.state === "BLOCKED"
      && error.code === "MINIAPP_PACKAGE_REVISION_BINDING_REQUIRED");

  const missingTarget = packageInput();
  (missingTarget.versionBindings as Record<string, unknown>).targets = [
    { platform: "wechat", platformVersion: "3.9.1", toolchainVersion: "1.06.2504010" },
  ];
  assert.throws(() => validateMiniappPackageConversionInput(missingTarget), (error: unknown) =>
    error instanceof MiniappPackageContractError
      && error.code === "MINIAPP_PACKAGE_TARGET_BINDING_MISSING"
      && error.details.platform === "alipay");
});

test("package and wrapper additionalProperties false constraints fail closed at nested boundaries", () => {
  const requestExtra = packageRequest();
  (requestExtra.source as Record<string, unknown>).branch = "main";
  assert.throws(() => validateMiniappPackageRequest(requestExtra), (error: unknown) =>
    error instanceof MiniappPackageContractError && error.path === "packageRequest.source.branch");

  const wrapperExtra = packageInput();
  wrapperExtra.executeScripts = true;
  assert.throws(() => validateMiniappPackageConversionInput(wrapperExtra), (error: unknown) =>
    error instanceof MiniappPackageContractError && error.path === "packageInput.executeScripts");

  const bindingExtra = packageInput();
  (((bindingExtra.versionBindings as Record<string, unknown>).targets as Array<Record<string, unknown>>)[0]!).channel = "latest";
  assert.throws(() => validateMiniappPackageConversionInput(bindingExtra), (error: unknown) =>
    error instanceof MiniappPackageContractError
      && error.path === "packageInput.versionBindings.targets[0].channel");

  for (const unsupportedPattern of [
    "src/{App,Main}.vue",
    "src/[AM]pp.vue",
    "!src/secret.ts",
    "src/**main.ts",
    "src/***/main.ts",
  ]) {
    const unsupportedGlob = packageRequest();
    (unsupportedGlob.source as Record<string, unknown>).include = [unsupportedPattern];
    assert.throws(() => validateMiniappPackageRequest(unsupportedGlob), (error: unknown) =>
      error instanceof MiniappPackageContractError
        && error.path === "packageRequest.source.include[0]");
  }
  const supportedGlob = packageRequest();
  (supportedGlob.source as Record<string, unknown>).include = ["src/**/main.?s", "*.json"];
  assert.deepEqual(validateMiniappPackageRequest(supportedGlob).source.include, [
    "src/**/main.?s",
    "*.json",
  ]);
});

test("credential_refs accept secret references only and reject raw secret material", () => {
  const rawSecret = packageRequest();
  ((rawSecret.release as Record<string, unknown>).credential_refs as Record<string, unknown>).wechat = "plain-app-secret";
  assert.throws(() => validateMiniappPackageRequest(rawSecret), (error: unknown) =>
    error instanceof MiniappPackageContractError
      && error.path === "packageRequest.release.credential_refs.wechat");

  const metadataSecret = packageRequest();
  (metadataSecret.metadata as Record<string, unknown>).appSecret = "raw-token";
  assert.throws(() => validateMiniappPackageRequest(metadataSecret), (error: unknown) =>
    error instanceof MiniappPackageContractError
      && error.code === "MINIAPP_PACKAGE_SECRET_MATERIAL_REJECTED"
      && error.path === "packageRequest.metadata.appSecret");

  const unicodeKeySecret = packageRequest();
  (unicodeKeySecret.metadata as Record<string, unknown>)["app\uFF33ecret"] = "raw-token";
  assert.throws(() => validateMiniappPackageRequest(unicodeKeySecret), (error: unknown) =>
    error instanceof MiniappPackageContractError
      && error.code === "MINIAPP_PACKAGE_SECRET_MATERIAL_REJECTED");

  const nestedBearer = packageRequest();
  (nestedBearer.metadata as Record<string, unknown>).notes = {
    deployment: "Bearer abcdefghijklmnopqrstuvwxyz012345",
  };
  assert.throws(() => validateMiniappPackageRequest(nestedBearer), (error: unknown) =>
    error instanceof MiniappPackageContractError
      && error.code === "MINIAPP_PACKAGE_SECRET_MATERIAL_REJECTED"
      && error.path === "packageRequest.metadata.notes.deployment");

  for (const [key, value] of [
    ["authorization", ["raw-session-secret"]],
    ["cookie", "sid=raw-session-secret"],
    ["session", "raw-session-secret"],
    ["headers", { authorization: "raw-session-secret" }],
    ["refresh", "raw-session-secret"],
    ["access", "raw-session-secret"],
  ] as const) {
    const sensitiveMetadata = packageRequest();
    (sensitiveMetadata.metadata as Record<string, unknown>)[key] = value;
    assert.throws(() => validateMiniappPackageRequest(sensitiveMetadata), (error: unknown) =>
      error instanceof MiniappPackageContractError
        && error.code === "MINIAPP_PACKAGE_SECRET_MATERIAL_REJECTED"
        && error.path.startsWith(`packageRequest.metadata.${key}`));
  }

  const referencedSecret = packageRequest();
  (referencedSecret.metadata as Record<string, unknown>).appSecret =
    "vault://tenant-package/metadata/app-secret";
  assert.equal(
    (validateMiniappPackageRequest(referencedSecret).metadata as Record<string, unknown>)
      .appSecret,
    "vault://tenant-package/metadata/app-secret",
  );
});

test("framework_hint auto uses inventory and reports multi-framework ambiguity as structured BLOCKED", () => {
  const conflictFiles: readonly MiniappInventoryInputFile[] = [
    {
      path: "apps/client/package.json",
      content: JSON.stringify({ dependencies: { react: "19.2.7", vue: "3.5.39" } }),
    },
    { path: "apps/client/src/App.tsx", content: 'import React from "react"; export const App = () => null;' },
    { path: "apps/client/src/Legacy.vue", content: "<template><main>legacy</main></template>" },
  ];
  const input = packageInput(conflictFiles);
  (input.packageRequest as Record<string, unknown>).source = {
    ...((input.packageRequest as Record<string, unknown>).source as Record<string, unknown>),
    framework_hint: "auto",
  };
  assert.throws(() => compileMiniappPackageConversionInput(input), (error: unknown) =>
    error instanceof MiniappPackageContractError
      && error.state === "BLOCKED"
      && error.code === "MINIAPP_PACKAGE_FRAMEWORK_AUTO_BLOCKED"
      && Array.isArray(error.details.conflicts));
});

test("canonicalization and compilation are deterministic across non-semantic input ordering", () => {
  const forward = packageInput();
  const reverse = packageInput([...vueFiles].reverse());
  const reverseRequest = reverse.packageRequest as Record<string, unknown>;
  reverseRequest.targets = [...(reverseRequest.targets as unknown[])].reverse();
  const release = reverseRequest.release as Record<string, unknown>;
  const credentials = release.credential_refs as Record<string, unknown>;
  release.credential_refs = { wechat: credentials.wechat, alipay: credentials.alipay };
  const bindings = reverse.versionBindings as Record<string, unknown>;
  bindings.targets = [...(bindings.targets as unknown[])].reverse();

  assert.equal(
    canonicalizeMiniappPackageConversionInput(forward),
    canonicalizeMiniappPackageConversionInput(reverse),
  );
  const first = compileMiniappPackageConversionInput(forward);
  const second = compileMiniappPackageConversionInput(reverse);
  assert.deepEqual(first, second);
});

test("run-package applies source selectors and quality policy while preserving exact package bindings", () => {
  const ignored = { path: "apps/client/dist/generated.js", content: "throw new Error('must not execute');" };
  const outsideRoot = { path: "backend/secret.ts", content: "export const serverOnly = true;" };
  const files = [...vueFiles, ignored, outsideRoot];
  const input = packageInput(files);
  const result = handleMiniappSkillRequest({
    schemaVersion: "1.0",
    action: "run-package",
    packageInput: input,
  }) as MiniappPackageConversionRun;
  const repeated = handleMiniappSkillRequest({
    schemaVersion: "1.0",
    action: "run-package",
    packageInput: input,
  }) as MiniappPackageConversionRun;

  assert.deepEqual(result.policyBinding.sourceSelection.selectedFilePaths, [
    "package-lock.json",
    "package.json",
    "src/App.vue",
    "src/main.ts",
  ]);
  assert.deepEqual(result.policyBinding.sourceSelection.excludedFilePaths, [
    "apps/client/dist/generated.js",
    "backend/secret.ts",
  ]);
  assert.deepEqual(result.policyBinding.sourceSelection.selectedSuppliedFilePaths, [
    "apps/client/package-lock.json",
    "apps/client/package.json",
    "apps/client/src/App.vue",
    "apps/client/src/main.ts",
  ]);
  assert.deepEqual(result.policyBinding.sourceSelection.outsideRootFilePaths, [
    "backend/secret.ts",
  ]);
  assert.equal(result.sourceSnapshotDigest, computeMiniappSourceFileSetDigest(files));
  assert.equal(result.selectedSourceFileSetDigest, computeMiniappSourceFileSetDigest(selectedVueFiles));
  assert.equal(result.sourceFileSetDigest, result.selectedSourceFileSetDigest);
  assert.equal(result.visual.requestedSimilarity, 0.97);
  assert.equal(result.repair.maximumIterations, 4);
  assert.equal(result.policyBinding.quality.criticalFlowPassRate, 1);
  assert.match(result.packageRequestDigest, /^sha256:[a-f0-9]{64}$/u);
  assert.match(result.inputBindingDigest, /^sha256:[a-f0-9]{64}$/u);
  assert.equal(result.releasePlan.requestedMode, "preview");
  assert.equal(result.releasePlan.state, "NOT_RUN");
  assert.equal(result.releasePlan.sideEffectsAuthorized, false);
  assert.deepEqual(
    result.releasePlan.stages.map(stage => [stage.stage, stage.requested, stage.state]),
    [
      ["build", true, "NOT_RUN"],
      ["preview", true, "NOT_RUN"],
      ["upload", false, "NOT_RUN"],
      ["review", false, "NOT_RUN"],
      ["release", false, "NOT_RUN"],
    ],
  );
  assert.equal(result.delivery.state, "NOT_RUN");
  assert.equal(result.certification, "NOT_CERTIFIED");
  const isVersionBindingFinding = (code: string): boolean =>
    code.startsWith("MINIAPP_SOURCE_VERSION_")
    || code.startsWith("MINIAPP_SOURCE_LANGUAGE_")
    || code.startsWith("MINIAPP_SOURCE_RUNTIME_")
    || code.startsWith("MINIAPP_SOURCE_BUILD_TOOL_")
    || code.startsWith("MINIAPP_TARGET_VERSION_");
  assert.deepEqual(result.plan.findings.filter(finding => isVersionBindingFinding(finding.code)), []);
  assert.equal(result.deterministicDigest, repeated.deterministicDigest);

  const unsupported = packageInput();
  const sourceBinding = ((unsupported.versionBindings as Record<string, unknown>).source as Record<string, unknown>);
  sourceBinding.frameworkVersion = "99.0.0";
  sourceBinding.languageVersion = "99.0.0";
  sourceBinding.runtimeVersion = "99.0.0";
  sourceBinding.buildToolVersion = "99.0.0";
  const targetBindings = (unsupported.versionBindings as Record<string, unknown>).targets as Record<string, unknown>[];
  targetBindings.find(binding => binding.platform === "wechat")!.toolchainVersion = "99.0.0";
  const blocked = handleMiniappSkillRequest({
    schemaVersion: "1.0",
    action: "run-package",
    packageInput: unsupported,
  }) as MiniappPackageConversionRun;
  assert.equal(blocked.gates.find(gate => gate.gate === "G3")?.state, "BLOCKED");
  assert.deepEqual(
    blocked.plan.findings
      .filter(finding => isVersionBindingFinding(finding.code))
      .map(finding => finding.code)
      .sort(),
    [
      "MINIAPP_SOURCE_BUILD_TOOL_VERSION_MISMATCH",
      "MINIAPP_SOURCE_LANGUAGE_LOCK_MISMATCH",
      "MINIAPP_SOURCE_LANGUAGE_MANIFEST_MISMATCH",
      "MINIAPP_SOURCE_RUNTIME_MANIFEST_MISMATCH",
      "MINIAPP_SOURCE_VERSION_BINDING_MISMATCH",
      "MINIAPP_SOURCE_VERSION_MANIFEST_MISMATCH",
      "MINIAPP_SOURCE_VERSION_TUPLE_UNSUPPORTED",
      "MINIAPP_TARGET_VERSION_TUPLE_UNSUPPORTED",
    ],
  );
});

test("run-package fails closed for unapproved release side effects and empty source selection", () => {
  const unapproved = packageInput();
  (unapproved.packageRequest as Record<string, unknown>).release = {
    mode: "upload",
    human_approval_required: false,
    credential_refs: {},
  };
  assert.throws(() => handleMiniappSkillRequest({
    schemaVersion: "1.0",
    action: "run-package",
    packageInput: unapproved,
  }), (error: unknown) => error instanceof MiniappPackageContractError
    && error.code === "MINIAPP_PACKAGE_RELEASE_APPROVAL_REQUIRED"
    && error.state === "BLOCKED");

  const emptySelection = packageInput();
  ((emptySelection.packageRequest as Record<string, unknown>).source as Record<string, unknown>).include = [
    "not-present/**",
  ];
  assert.throws(() => compileMiniappPackageConversionInput(emptySelection), (error: unknown) =>
    error instanceof MiniappPackageContractError
      && error.code === "MINIAPP_PACKAGE_SOURCE_SELECTION_EMPTY");

  const outsideRoot = packageInput([{
    path: "backend/package.json",
    content: JSON.stringify({ dependencies: { vue: "3.5.39" } }),
  }]);
  assert.throws(() => compileMiniappPackageConversionInput(outsideRoot), (error: unknown) =>
    error instanceof MiniappPackageContractError
      && error.code === "MINIAPP_PACKAGE_SOURCE_SELECTION_EMPTY"
      && Array.isArray(error.details.outsideRootFilePaths));

  assert.throws(() => handleMiniappSkillRequest({
    schemaVersion: "1.0",
    action: "run-package",
    packageInput: packageInput(),
    conversion: {},
  }), /handlerRequest\.conversion is not allowed/u);
});

test("CLI package command materializes only indexed native candidates and exact declared outputs", () => {
  const temporary = mkdtempSync(join(tmpdir(), "elmos-miniapp-package-cli-"));
  const target = join(temporary, "generated");
  try {
    const result = spawnSync(
      process.execPath,
      ["dist/src/miniapp-cli.js", "package", "--materialize", target],
      {
        input: JSON.stringify(packageInput()),
        encoding: "utf8",
        maxBuffer: 16 * 1024 * 1024,
      },
    );
    assert.equal(result.status, 0, result.stderr);
    const response = JSON.parse(result.stdout) as MiniappPackageConversionRun;
    const rejectedTarget = join(temporary, "rejected-generated");
    const rejectedOutput = join(temporary, "rejected-result.json");
    const rejectedCombination = spawnSync(
      process.execPath,
      [
        "dist/src/miniapp-cli.js",
        "package",
        "--materialize",
        rejectedTarget,
        "--output",
        rejectedOutput,
      ],
      {
        input: JSON.stringify(packageInput()),
        encoding: "utf8",
        maxBuffer: 16 * 1024 * 1024,
      },
    );
    assert.notEqual(rejectedCombination.status, 0);
    assert.match(rejectedCombination.stderr, /--output cannot be combined with --materialize/u);
    assert.equal(existsSync(rejectedTarget), false);
    assert.equal(existsSync(rejectedOutput), false);
    assert.equal(statSync(target).mode & 0o077, 0, "published materialization root must not grant group/world access");
    assert.equal(existsSync(join(target, "migration-evidence.json")), false);
    assert.equal(existsSync(join(target, "local-run-summary.json")), false);

    const declared = materializeMiniappDeclaredOutputs(response);
    const generated = materializeMiniappGeneratedProjectArtifacts(response);
    assert.equal(declared.length, 88);
    for (const artifact of declared) {
      assert.equal(
        readFileSync(join(target, artifact.materializedPath), "utf8"),
        artifact.content,
        artifact.materializedPath,
      );
    }
    assert.equal(
      generated.length,
      response.generatedProjects.reduce(
        (total, project) => total + Object.keys(project.files).length,
        0,
      ),
    );
    for (const artifact of generated) {
      assert.equal(
        readFileSync(join(target, artifact.materializedPath), "utf8"),
        artifact.content,
        artifact.materializedPath,
      );
      assert.equal(
        existsSync(join(target, artifact.platform, artifact.sourcePath)),
        false,
        `legacy top-level candidate path must be absent: ${artifact.platform}/${artifact.sourcePath}`,
      );
    }
    for (const platform of ["wechat", "alipay"] as const) {
      const projectFiles = generated.filter(artifact => artifact.platform === platform);
      const projectIndex = declared.find(artifact =>
        artifact.declaredPattern === `platforms/${platform}/**`);
      assert.ok(projectIndex);
      assert.equal(projectIndex.state, "PASSED_LOCAL");
      assert.equal(
        projectIndex.materializedPath,
        `${projectFiles[0]?.declaredBasePath}/project-index.json`,
      );
      const indexBody = JSON.parse(projectIndex.content) as {
        readonly exact_declared_files_materialized: boolean;
        readonly files: readonly {
          readonly bytes: number;
          readonly path: string;
          readonly sha256: string;
          readonly source_path: string;
        }[];
      };
      assert.equal(indexBody.exact_declared_files_materialized, true);
      assert.deepEqual(indexBody.files, projectFiles.map(artifact => ({
        bytes: artifact.bytes,
        path: artifact.materializedPath,
        sha256: artifact.digest.slice("sha256:".length),
        source_path: artifact.sourcePath,
      })));
    }
    const runIndex = declared.find(artifact =>
      artifact.declaredPattern === "runs/<run-id>/artifacts-index.json");
    const reporterIndex = declared.find(artifact =>
      artifact.ownerSkill === "miniapp-migration-evidence-reporter"
      && artifact.declaredPattern === "artifact-index.json");
    assert.ok(runIndex);
    assert.ok(reporterIndex);
    assert.deepEqual(JSON.parse(runIndex.content), JSON.parse(reporterIndex.content));
    const combinedIndex = materializeMiniappCombinedOutputIndex(response);
    assert.deepEqual(JSON.parse(runIndex.content).artifacts, combinedIndex);
    assert.deepEqual(JSON.parse(runIndex.content).self_referential_outputs_excluded, [
      runIndex.materializedPath,
      reporterIndex.materializedPath,
    ]);
    const canonicalEvidence = declared.find(artifact =>
      artifact.ownerSkill === "miniapp-migration-evidence-reporter"
      && artifact.declaredPattern === "migration-evidence.json");
    assert.ok(canonicalEvidence);
    assert.equal(canonicalEvidence.state, "BLOCKED");
    assert.equal(canonicalEvidence.materializedPath, `runs/${response.runId}/declared-outputs/miniapp-migration-evidence-reporter/migration-evidence.json`);
    assert.deepEqual(Object.keys(JSON.parse(canonicalEvidence.content)).sort(), [
      "approvals",
      "artifacts",
      "claims",
      "cost",
      "evidence_id",
      "gates",
      "release_status",
      "request_id",
      "source_revision",
    ]);
    assert.equal(generated.some(artifact => artifact.sourcePath === "app.json"), true);

    const parentSymlinkTarget = join(temporary, "parent-symlink-generated");
    const externalWriteTarget = join(temporary, "parent-symlink-external");
    mkdirSync(externalWriteTarget, { mode: 0o700 });
    let replacedArtifactParent = false;
    assert.throws(() => materializeMiniappRun(response, parentSymlinkTarget, {
      beforeArtifactWrite: ({ staging, artifactPath }) => {
        if (replacedArtifactParent) return;
        replacedArtifactParent = true;
        const artifactParent = dirname(join(staging, artifactPath));
        renameSync(artifactParent, `${artifactParent}.owned-displaced`);
        symlinkSync(externalWriteTarget, artifactParent, "dir");
      },
    }), /materialize artifact parent .* identity drifted/u);
    assert.equal(replacedArtifactParent, true);
    assert.deepEqual(
      readdirSync(externalWriteTarget),
      [],
      "a replaced intermediate directory must fail before an artifact can be written outside staging",
    );
    assert.equal(existsSync(parentSymlinkTarget), false);
    assert.equal(existsSync(`${parentSymlinkTarget}.elmos-miniapp-materialize.lock`), false);

    const undefinedThrowTarget = join(temporary, "undefined-throw-generated");
    let caughtUndefined = false;
    let caughtUndefinedValue: unknown = "not-caught";
    try {
      materializeMiniappRun(response, undefinedThrowTarget, {
        beforeArtifactWrite: () => {
          throw undefined;
        },
      });
    } catch (error) {
      caughtUndefined = true;
      caughtUndefinedValue = error;
    }
    assert.equal(caughtUndefined, true, "a hook throwing undefined must still fail materialization");
    assert.equal(caughtUndefinedValue, undefined);
    assert.equal(existsSync(undefinedThrowTarget), false);
    assert.equal(existsSync(`${undefinedThrowTarget}.elmos-miniapp-materialize.lock`), false);

    const writableParent = join(temporary, "group-world-writable-parent");
    mkdirSync(writableParent, { mode: 0o700 });
    chmodSync(writableParent, 0o777);
    assert.throws(
      () => materializeMiniappRun(response, join(writableParent, "generated")),
      /materialize parent directory must be owned by the current user and not group\/world writable/u,
    );
    assert.deepEqual(readdirSync(writableParent), []);

    const replacedReservationTarget = join(temporary, "replaced-reservation-generated");
    const replacedReservationLock = `${replacedReservationTarget}.elmos-miniapp-materialize.lock`;
    let replacedReservation = false;
    assert.throws(() => materializeMiniappRun(response, replacedReservationTarget, {
      beforeArtifactWrite: () => {
        if (replacedReservation) return;
        replacedReservation = true;
        unlinkSync(replacedReservationLock);
        writeFileSync(replacedReservationLock, "competing reservation\n", { mode: 0o600 });
      },
    }), /materialize reservation identity drifted before artifact write/u);
    assert.equal(readFileSync(replacedReservationLock, "utf8"), "competing reservation\n");
    assert.equal(existsSync(replacedReservationTarget), false);
    unlinkSync(replacedReservationLock);

    const racedTarget = join(temporary, "raced-generated");
    const competingMarker = join(racedTarget, "competing-writer.txt");
    assert.throws(() => materializeMiniappRun(response, racedTarget, {
      beforeCommit: ({ root }) => {
        mkdirSync(root);
        writeFileSync(competingMarker, "competing writer owns this directory\n", "utf8");
      },
    }), /materialize target appeared during staging/u);
    assert.equal(
      readFileSync(competingMarker, "utf8"),
      "competing writer owns this directory\n",
    );
    assert.deepEqual(
      readdirSync(temporary).filter(name => name.startsWith("raced-generated")).sort(),
      ["raced-generated"],
      "failed commit must remove its staging tree and reservation without touching the competing target",
    );

    const tamperedTarget = join(temporary, "tampered-generated");
    const tamperedArtifact = declared.find(artifact =>
      artifact.declaredPattern === "migration-evidence.json");
    assert.ok(tamperedArtifact);
    assert.throws(() => materializeMiniappRun(response, tamperedTarget, {
      beforeCommit: ({ staging }) => {
        writeFileSync(
          join(staging, tamperedArtifact.materializedPath),
          "tampered after initial verification\n",
          "utf8",
        );
      },
    }), /artifact identity drifted before commit/u);
    assert.equal(existsSync(tamperedTarget), false);
    assert.deepEqual(
      readdirSync(temporary).filter(name => name.startsWith("tampered-generated")),
      [],
      "tampered staging and its reservation must be removed without publishing a target",
    );

    const replacedTarget = join(temporary, "replaced-staging-generated");
    let replacementStaging = "";
    let displacedStaging = "";
    assert.throws(() => materializeMiniappRun(response, replacedTarget, {
      beforeCommit: ({ staging }) => {
        replacementStaging = staging;
        displacedStaging = `${staging}.displaced`;
        renameSync(staging, displacedStaging);
        mkdirSync(staging);
        writeFileSync(join(staging, "competing-writer.txt"), "do not delete\n", "utf8");
      },
    }), /materialize staging directory(?: during cleanup)? identity drifted/u);
    assert.equal(
      readFileSync(join(replacementStaging, "competing-writer.txt"), "utf8"),
      "do not delete\n",
      "cleanup must not remove a staging path replaced by another writer",
    );
    assert.equal(existsSync(displacedStaging), true);
    assert.equal(existsSync(`${replacedTarget}.elmos-miniapp-materialize.lock`), false);
    rmSync(replacementStaging, { recursive: true });
    rmSync(displacedStaging, { recursive: true });

    const finalRaceTarget = join(temporary, "final-race-generated");
    let finalRaceReplacement = "";
    let finalRaceDisplaced = "";
    assert.throws(() => materializeMiniappRun(response, finalRaceTarget, {
      beforePublish: ({ staging }) => {
        finalRaceReplacement = staging;
        finalRaceDisplaced = `${staging}.displaced`;
        renameSync(staging, finalRaceDisplaced);
        mkdirSync(staging);
        writeFileSync(join(staging, "competing-writer.txt"), "preserve final-race writer\n", "utf8");
      },
    }), /staging directory before publish identity drifted/u);
    assert.equal(readFileSync(join(finalRaceReplacement, "competing-writer.txt"), "utf8"), "preserve final-race writer\n");
    assert.equal(existsSync(finalRaceDisplaced), true);
    assert.equal(existsSync(`${finalRaceTarget}.elmos-miniapp-materialize.lock`), false);
    rmSync(finalRaceReplacement, { recursive: true });
    rmSync(finalRaceDisplaced, { recursive: true });

    const publishedTamperTarget = join(temporary, "published-tamper-generated");
    assert.throws(() => materializeMiniappRun(response, publishedTamperTarget, {
      afterPublish: ({ root }) => {
        writeFileSync(join(root, tamperedArtifact.materializedPath), "tampered after publish\n", "utf8");
      },
    }), /artifact identity drifted after publish/u);
    assert.equal(existsSync(publishedTamperTarget), false, "failed owned publication must be removed by exact inode identity");
    assert.equal(existsSync(`${publishedTamperTarget}.elmos-miniapp-materialize.lock`), false);

    const replacedPublishedTarget = join(temporary, "replaced-published-generated");
    let displacedPublished = "";
    assert.throws(() => materializeMiniappRun(response, replacedPublishedTarget, {
      afterPublish: ({ root }) => {
        displacedPublished = `${root}.displaced`;
        renameSync(root, displacedPublished);
        mkdirSync(root);
        writeFileSync(join(root, "competing-writer.txt"), "do not delete published replacement\n", "utf8");
      },
    }), /published directory identity drifted/u);
    assert.equal(
      readFileSync(join(replacedPublishedTarget, "competing-writer.txt"), "utf8"),
      "do not delete published replacement\n",
    );
    assert.equal(existsSync(displacedPublished), true);
    assert.equal(existsSync(`${replacedPublishedTarget}.elmos-miniapp-materialize.lock`), false);
    rmSync(replacedPublishedTarget, { recursive: true });
    rmSync(displacedPublished, { recursive: true });
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
});

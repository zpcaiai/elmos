import test, { after } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash, generateKeyPairSync } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { frtCatalog } from "../src/frt-catalog.generated.js";
import { frtHandlerRegistry } from "../src/frt-handler-registry.generated.js";
import {
  convertDirectionalRoute,
  createDirectionalRouteFixture,
  frtRouteStacks,
  type FrtRouteStack,
} from "../src/directional-route.js";
import { FrtRuntime } from "../src/frt-runtime.js";
import {
  ConfinedFileFrtEvidenceResolver,
  FrtTrustStore,
  type FrtTrustRole,
  canonicalFrtJson,
  digestFrtEvidence,
  evidenceReferencePayload,
  prerequisiteCertificatePayload,
  runnerCompletionPayload,
  signFrtPayload,
} from "../src/frt-security.js";
import {
  ContentAddressedFrtArtifactStore,
  DenyAllFrtArtifactStore,
} from "../src/frt-artifact-store.js";
import {
  FileFrtRunStore,
  backupFrtRunStore,
  restoreFrtRunStore,
  type FrtRunStore,
} from "../src/frt-run-store.js";
import { convertVue3ToReact } from "../src/vue3-react-route.js";
import type {
  FrtEvidenceReference,
  FrtExecutionContext,
  FrtPrerequisiteCertificate,
  FrtRunnerCompletion,
  FrtSkillRunRequest,
} from "../src/frt-types.js";

const scope = {
  organizationId: "org-frt-test",
  tenantId: "tenant-frt-test",
  workspaceId: "workspace-frt-test",
  projectId: "project-frt-test",
  accountId: "account-frt-test",
  environmentId: "environment-frt-test",
  releaseId: "release-frt-test",
} as const;

const context: FrtExecutionContext = {
  ...scope,
  sourceSnapshotDigest: `sha256:${"1".repeat(64)}`,
  policyVersion: "frt-policy-1.0.0",
  requestedBy: "operator-frt-test",
  risk: "R4",
};

const signingAuthority = "frt-test-authority";
const signingKeyId = "frt-test-key";
const issuedAt = "2026-07-31T00:00:00Z";
const expiresAt = "2026-08-02T00:00:00Z";
const fixedNow = new Date("2026-08-01T00:00:00Z");
const evidenceRoot = mkdtempSync(join(tmpdir(), "elmos-frt-evidence-"));
const runStoreRoot = mkdtempSync(join(tmpdir(), "elmos-frt-runs-"));
const runnerKeyId = "frt-test-runner-key";
const { privateKey, publicKey } = generateKeyPairSync("ed25519");
const { privateKey: runnerPrivateKey, publicKey: runnerPublicKey } = generateKeyPairSync("ed25519");
const trustKey = (
  keyId: string,
  pem: string,
  roles: readonly FrtTrustRole[],
) => ({
  keyId,
  authority: signingAuthority,
  publicKeyPem: pem,
  purposes: [] as const,
  roles,
  activeFrom: "2026-01-01T00:00:00Z",
  expiresAt: "2027-01-01T00:00:00Z",
  revoked: false,
});
const attestingPem = publicKey.export({ type: "spki", format: "pem" }).toString();
const runnerPem = runnerPublicKey.export({ type: "spki", format: "pem" }).toString();
// A key may attest or execute, never both, so the runner signs with its own key.
const trustStore = new FrtTrustStore({
  schemaVersion: "1.0",
  keys: [
    trustKey(signingKeyId, attestingPem, ["identity-issuer", "gate-evidence-authorizer", "evidence-authorizer"]),
    trustKey(runnerKeyId, runnerPem, ["execution-attester"]),
  ],
});
const security = {
  trustStore,
  evidenceResolver: new ConfinedFileFrtEvidenceResolver([evidenceRoot]),
  now: () => fixedNow,
};
let evidenceCounter = 0;
let runStoreCounter = 0;

const vue3Fixture = {
  "package.json": JSON.stringify({ dependencies: { vue: "3.5.39" } }),
  "src/App.vue": [
    `<script setup lang="ts">`,
    `import { ref } from "vue";`,
    `const count = ref(0);`,
    `function increment() { count.value++; }`,
    `</script>`,
    `<template><main class="counter"><h1>{{ count }}</h1><button @click="increment">Add</button></main></template>`,
    `<style scoped>.counter button { color: #b34838; }</style>`,
  ].join("\n"),
} as const;

after(() => {
  rmSync(evidenceRoot, { recursive: true, force: true });
  rmSync(runStoreRoot, { recursive: true, force: true });
});

function createRuntime(
  store: FrtRunStore = new FileFrtRunStore(join(runStoreRoot, String(runStoreCounter++))),
): FrtRuntime {
  return new FrtRuntime({ security, store });
}

function certificate(batch: string): FrtPrerequisiteCertificate {
  const unsigned = {
    batch,
    state: "ACTIVE",
    scope,
    artifactDigest: `sha256:${"2".repeat(64)}`,
    evidenceRefs: [`fixture://certificate/${batch}`],
    authority: signingAuthority,
    keyId: signingKeyId,
    issuedAt,
    expiresAt,
  } as const;
  const pending = { ...unsigned, signature: "pending" };
  return {
    ...unsigned,
    signature: signFrtPayload(privateKey, prerequisiteCertificatePayload(pending)),
  };
}

function signedEvidence(role: string, index = 0): FrtEvidenceReference {
  const bytes = Buffer.from(`immutable evidence for ${role} ${index}\n`);
  const path = join(
    evidenceRoot,
    `${String(evidenceCounter++).padStart(3, "0")}-${role.toLocaleLowerCase("en-US")}.json`,
  );
  writeFileSync(path, bytes);
  const unsigned = {
    role,
    uri: pathToFileURL(path).href,
    digest: digestFrtEvidence(bytes),
    state: "PASSED" as const,
    executor: `executor-${index}`,
    verifier: `verifier-${index}`,
    synthetic: false,
    byteCount: bytes.byteLength,
    authority: signingAuthority,
    keyId: signingKeyId,
    issuedAt,
    expiresAt,
  };
  const pending = { ...unsigned, signature: "pending" };
  return {
    ...unsigned,
    signature: signFrtPayload(privateKey, evidenceReferencePayload(pending)),
  };
}

function attributedEvidence(
  role: string,
  executor: string,
  verifier: string,
  keyId: string = signingKeyId,
): FrtEvidenceReference {
  const bytes = Buffer.from(`runner evidence for ${role} by ${executor}\n`);
  const path = join(
    evidenceRoot,
    `${String(evidenceCounter++).padStart(3, "0")}-runner-${role.toLocaleLowerCase("en-US")}.json`,
  );
  writeFileSync(path, bytes);
  const unsigned = {
    role,
    uri: pathToFileURL(path).href,
    digest: digestFrtEvidence(bytes),
    state: "PASSED" as const,
    executor,
    verifier,
    synthetic: false,
    byteCount: bytes.byteLength,
    authority: signingAuthority,
    keyId,
    issuedAt,
    expiresAt,
  };
  const pending = { ...unsigned, signature: "pending" };
  return {
    ...unsigned,
    signature: signFrtPayload(keyId === runnerKeyId ? runnerPrivateKey : privateKey, evidenceReferencePayload(pending)),
  };
}

function runnerCompletion(
  runnerId: string,
  options: {
    readonly exitStatus?: FrtRunnerCompletion["exitStatus"];
    readonly customerCodeExecuted?: boolean;
    readonly evidence?: readonly FrtEvidenceReference[];
    readonly artifacts?: FrtRunnerCompletion["artifacts"];
    readonly keyId?: string;
  } = {},
): FrtRunnerCompletion {
  const unsigned = {
    schemaVersion: "1.0" as const,
    runnerId,
    exitStatus: options.exitStatus ?? ("COMPLETED" as const),
    startedAt: "2026-07-31T12:00:00Z",
    finishedAt: "2026-07-31T12:30:00Z",
    customerCodeExecuted: options.customerCodeExecuted ?? true,
    productionOperationExecuted: false,
    artifacts: options.artifacts ?? [{
      name: "target-workspace",
      uri: "file:///tmp/frt-runner/target-workspace.tar",
      digest: `sha256:${"a".repeat(64)}`,
      byteCount: 4096,
    }],
    evidence: options.evidence ?? [],
    authority: signingAuthority,
    keyId: options.keyId ?? runnerKeyId,
    issuedAt,
    expiresAt,
  };
  const pending = { ...unsigned, signature: "pending" };
  return {
    ...unsigned,
    signature: signFrtPayload(options.keyId === signingKeyId ? privateKey : runnerPrivateKey, runnerCompletionPayload(pending)),
  };
}

function request(
  skillId: string,
  action: FrtSkillRunRequest["action"],
  options: {
    readonly key?: string;
    readonly certificateBatch?: string;
    readonly evidence?: readonly FrtEvidenceReference[];
    readonly input?: Readonly<Record<string, unknown>>;
    readonly expectedVersion?: number;
  } = {},
): FrtSkillRunRequest {
  const base = {
    schemaVersion: "1.0" as const,
    skillId,
    action,
    idempotencyKey: options.key ?? `${skillId}-${action.toLocaleLowerCase("en-US")}`,
    expectedVersion: options.expectedVersion ?? 0,
    context,
    prerequisiteCertificates: options.certificateBatch ? [certificate(options.certificateBatch)] : [],
    evidence: options.evidence ?? [],
  };
  return options.input === undefined ? base : { ...base, input: options.input };
}

test("FRT catalog preserves all 30 batches, 472 Skills, and immutable source identities", () => {
  assert.equal(frtCatalog.batchCount, 30);
  assert.equal(frtCatalog.skillCount, 472);
  assert.equal(frtCatalog.batches.length, 30);
  assert.equal(frtCatalog.skills.length, 472);
  assert.equal(new Set(frtCatalog.skills.map(skill => skill.id)).size, 472);
  assert.equal(new Set(frtCatalog.skills.map(skill => skill.name)).size, 472);
  assert.ok(frtCatalog.skills.every(skill => /^sha256:[a-f0-9]{64}$/.test(skill.sourceSha256)));
  assert.equal(frtCatalog.evidenceBoundary.production, "NOT_RUN");
  assert.equal(frtCatalog.evidenceBoundary.certification, "NOT_CERTIFIED");
});

test("all 472 Skills have explicit semantic handlers and six exact surface manifests", () => {
  assert.equal(frtHandlerRegistry.length, 472);
  assert.equal(new Set(frtHandlerRegistry.map(item => item.skillId)).size, 472);
  assert.deepEqual(
    new Set(frtHandlerRegistry.map(item => item.skillId)),
    new Set(frtCatalog.skills.map(item => item.id)),
  );
  for (const handler of frtHandlerRegistry) {
    const surfaces = Object.entries(handler.surfaceManifestPaths);
    assert.equal(surfaces.length, 6, handler.skillId);
    for (const [surface, relativePath] of surfaces) {
      const manifest = JSON.parse(
        readFileSync(new URL(`../../../../${relativePath}`, import.meta.url), "utf8"),
      ) as {
        skill_id: string;
        surface: string;
        status: string;
        handler_kind: string;
        implementation_paths: string[];
      };
      assert.equal(manifest.skill_id, handler.skillId);
      assert.equal(manifest.surface, surface);
      assert.equal(manifest.status, "shared_implementation");
      assert.equal(manifest.handler_kind, handler.handlerKind);
      assert.ok(manifest.implementation_paths.length > 0);
    }
  }
});

test("runtime contract rejects unknown actions and additional properties", () => {
  const runtime = createRuntime();
  const invalidAction = runtime.run({
    ...request("FRT-0100", "PLAN", { key: "invalid-action" }),
    action: "INVALID_ACTION",
  } as unknown as FrtSkillRunRequest);
  assert.equal(invalidAction.state, "FAILED");
  assert.equal(invalidAction.outcome, "REQUEST_REJECTED");
  assert.ok(invalidAction.findings.some(item => item.message.includes("request.action")));

  const extraProperty = runtime.run({
    ...request("FRT-0100", "PLAN", { key: "extra-property" }),
    unexpectedCustomerField: "must-not-be-accepted",
  } as unknown as FrtSkillRunRequest);
  assert.equal(extraProperty.state, "FAILED");
  assert.ok(extraProperty.findings.some(item => item.message.includes("unexpectedCustomerField")));
});

test("runtime action enum remains aligned with the checked-in JSON Schema", () => {
  const schemaUrl = new URL(
    "../../../../schemas/frt-g01-g30/skill-run-request.schema.json",
    import.meta.url,
  );
  const schema = JSON.parse(readFileSync(schemaUrl, "utf8")) as {
    properties: { action: { enum: string[] } };
  };
  assert.deepEqual(schema.properties.action.enum, ["PLAN", "ANALYZE", "EXECUTE", "VERIFY"]);
});

test("FRT route matrix covers every directed non-self pair across six stacks", () => {
  assert.equal(frtCatalog.routes.length, 30);
  assert.equal(new Set(frtCatalog.routes.map(route => route.routeId)).size, 30);
  for (const source of frtCatalog.technologyStacks) {
    for (const target of frtCatalog.technologyStacks) {
      const expected = source === target ? 0 : 1;
      assert.equal(
        frtCatalog.routes.filter(route => route.source === source && route.target === target).length,
        expected,
        `${source} -> ${target}`,
      );
    }
  }
  assert.ok(frtCatalog.routes.every(route => route.certification === "NOT_CERTIFIED"));
});

test("every FRT Skill has an executable scoped plan path", () => {
  const runtime = createRuntime();
  for (const skill of frtCatalog.skills) {
    const result = runtime.run(request(
      skill.id,
      "PLAN",
      {
        key: `all-${skill.id}`,
        ...(skill.requiresCertificate === null ? {} : { certificateBatch: skill.requiresCertificate }),
      },
    ));
    assert.equal(result.state, "SUCCEEDED", skill.id);
    assert.equal(result.outcome, "PLAN_READY", skill.id);
    assert.equal(result.skillName, skill.name);
    assert.ok(result.obligations.length >= 5);
    assert.equal(
      (result.artifacts.executionPlan as { handlerKind: string }).handlerKind,
      frtHandlerRegistry.find(item => item.skillId === skill.id)?.handlerKind,
      skill.id,
    );
    assert.equal(result.certificateFragment.certification, "NOT_CERTIFIED");
    assert.equal(result.customerCodeExecuted, false);
    assert.equal(result.productionOperationExecuted, false);
  }
});

test("downstream Skills fail closed on missing, inactive, or cross-tenant certificates", () => {
  const runtime = createRuntime();
  const missing = runtime.run(request("FRT-1305", "PLAN", { key: "missing-certificate" }));
  assert.equal(missing.state, "BLOCKED");
  assert.equal(missing.outcome, "BLOCKED_BY_PREREQUISITE");
  assert.ok(missing.findings.some(item => item.code === "FRT_PREREQUISITE_CERTIFICATE_MISSING"));

  const wrongScope: FrtPrerequisiteCertificate = {
    ...certificate("G12"),
    scope: { ...scope, tenantId: "another-tenant" },
  };
  const mismatch = runtime.run({
    ...request("FRT-1305", "PLAN", { key: "wrong-certificate" }),
    prerequisiteCertificates: [wrongScope],
  });
  assert.equal(mismatch.state, "BLOCKED");
  assert.ok(mismatch.findings.some(item => item.code === "FRT_PREREQUISITE_SCOPE_MISMATCH"));
});

test("real static discovery reuses the frontend engine and never executes customer code", () => {
  const runtime = createRuntime();
  const result = runtime.run(request("FRT-0202", "ANALYZE", {
    key: "react-discovery",
    certificateBatch: "G01",
    input: {
      files: {
        "package.json": JSON.stringify({ dependencies: { react: "19.2.8" } }),
        "pnpm-lock.yaml": "lockfileVersion: '9.0'",
        "src/App.tsx": "export function App(){ return <main>Ready</main> }",
      },
    },
  }));
  assert.equal(result.state, "SUCCEEDED");
  assert.equal(result.outcome, "STATIC_ANALYSIS_COMPLETE");
  const inventory = result.artifacts.inventory as { frameworks: string[]; packageManager: string };
  assert.deepEqual(inventory.frameworks, ["REACT"]);
  assert.equal(inventory.packageManager, "PNPM");
  assert.equal(result.customerCodeExecuted, false);
});

test("route execution produces a bounded proposal while runtime and certification remain external", () => {
  const runtime = createRuntime();
  const result = runtime.run(request("FRT-1305", "EXECUTE", {
    key: "route-proposal",
    certificateBatch: "G12",
    input: { files: vue3Fixture },
  }));
  assert.equal(result.state, "QUEUED");
  assert.equal(result.outcome, "PROPOSAL_READY_FOR_RUNNER");
  assert.equal((result.artifacts.route as { source: string }).source, "Vue 3");
  assert.equal(
    (result.artifacts.routeMigration as { status: string }).status,
    "GENERATED",
  );
  assert.ok(result.findings.some(item => item.code === "FRT_EXTERNAL_RUNNER_REQUIRED"));
  assert.equal(result.certificateFragment.eligibleForBatchGate, false);
});

test("Vue 3 to React vertical slice parses the SFC AST and emits target code that typechecks", () => {
  const migration = convertVue3ToReact(vue3Fixture);
  assert.equal(migration.status, "GENERATED");
  assert.deepEqual(migration.typedGaps, []);
  assert.match(migration.generatedFiles["src/App.tsx"]!, /const \[count, setCount\] = useState\(0\)/);
  assert.match(migration.generatedFiles["src/App.tsx"]!, /onClick=\{increment\}/);
  assert.match(migration.generatedFiles["src/App.css"]!, /\[data-v-frt-/);

  const projectRoot = mkdtempSync(join(tmpdir(), "elmos-frt-vue-react-build-"));
  try {
    for (const [relativePath, content] of Object.entries(migration.generatedFiles)) {
      const destination = join(projectRoot, relativePath);
      mkdirSync(join(destination, ".."), { recursive: true });
      writeFileSync(destination, content);
    }
    const engineRoot = fileURLToPath(new URL("../..", import.meta.url));
    symlinkSync(join(engineRoot, "node_modules"), join(projectRoot, "node_modules"), "dir");
    execFileSync(join(engineRoot, "node_modules", ".bin", "tsc"), ["-p", projectRoot], {
      cwd: projectRoot,
      stdio: "pipe",
    });
  } finally {
    rmSync(projectRoot, { recursive: true, force: true });
  }
});

test("development, negative, holdout, and synthetic representative corpora stay separate", () => {
  const entries = [
    ["development", "vue3-counter.json"],
    ["negative", "vue3-v-for.json"],
    ["holdout", "vue3-toggle.json"],
    ["representative", "vue3-form.json"],
  ] as const;
  const digests = new Set<string>();
  for (const [directory, name] of entries) {
    const source = readFileSync(
      new URL(`../../test/fixtures/frt/${directory}/${name}`, import.meta.url),
      "utf8",
    );
    digests.add(createHash("sha256").update(source).digest("hex"));
    const fixture = JSON.parse(source) as {
      corpusRole: string;
      files: Record<string, string>;
      expectedStatus: "GENERATED" | "BLOCKED";
    };
    const result = convertVue3ToReact(fixture.files);
    assert.equal(result.status, fixture.expectedStatus, fixture.corpusRole);
    if (fixture.corpusRole === "negative") {
      assert.ok(result.typedGaps.some(item => item.code === "FRT_VUE_DIRECTIVE_UNSUPPORTED"));
    }
    if (fixture.corpusRole === "holdout") {
      assert.match(result.generatedFiles["src/App.tsx"]!, /setEnabled\(!enabled\)/);
    }
    if (fixture.corpusRole === "synthetic-representative") {
      assert.match(result.generatedFiles["src/App.tsx"]!, /onChange=\{event => setName/);
    }
  }
  assert.equal(digests.size, entries.length);
});

test("all 30 exact directional routes transform the bounded typed UI IR slice", () => {
  assert.equal(frtCatalog.routes.length, 30);
  for (const route of frtCatalog.routes) {
    assert.ok(frtRouteStacks.includes(route.source as FrtRouteStack));
    assert.ok(frtRouteStacks.includes(route.target as FrtRouteStack));
    const migration = convertDirectionalRoute(
      route.source as FrtRouteStack,
      route.target as FrtRouteStack,
      createDirectionalRouteFixture(route.source as FrtRouteStack),
    );
    assert.equal(migration.status, "GENERATED", route.routeId);
    assert.equal(migration.sourceValidation, "PASSED", route.routeId);
    assert.equal(migration.targetValidation, "PASSED", route.routeId);
    assert.deepEqual(migration.typedGaps, [], route.routeId);
    assert.ok(Object.keys(migration.generatedFiles).length >= 2, route.routeId);
    assert.equal(migration.certification, "NOT_CERTIFIED", route.routeId);
  }
});

test("directional route runtime queues every exact route with typed source input", () => {
  for (const [index, route] of frtCatalog.routes.entries()) {
    const runtime = createRuntime();
    const skill = frtCatalog.skills.find(item => item.id === route.skillId);
    assert.ok(skill, route.skillId);
    const result = runtime.run(request(route.skillId, "EXECUTE", {
      key: `route-${index}`,
      ...(skill.requiresCertificate ? { certificateBatch: skill.requiresCertificate } : {}),
      input: { files: createDirectionalRouteFixture(route.source as FrtRouteStack) },
    }));
    assert.equal(result.state, "QUEUED", route.routeId);
    assert.equal(result.outcome, "PROPOSAL_READY_FOR_RUNNER", route.routeId);
    assert.equal((result.artifacts.routeMigration as { status: string }).status, "GENERATED", route.routeId);
  }
});

test("directional routes fail closed on missing or tampered typed source provenance", () => {
  const runtime = createRuntime();
  const result = runtime.run(request("FRT-1306", "EXECUTE", {
    key: "react-vue3-gap",
    certificateBatch: "G12",
    input: { files: createDirectionalRouteFixture("React") },
  }));
  assert.equal(result.state, "QUEUED");

  const fixture = createDirectionalRouteFixture("React");
  const tampered = { ...fixture, "src/App.tsx": `${fixture["src/App.tsx"]}\n// tampered` };
  const blocked = convertDirectionalRoute("React", "Vue 3", tampered);
  assert.equal(blocked.status, "BLOCKED");
  assert.ok(blocked.typedGaps.some(item => item.code === "FRT_TYPED_UI_IR_OR_SOURCE_INVALID"));

  // React has an extractor, so dropping the declaration falls back to reading
  // the source. An incomplete snapshot still fails closed rather than emitting
  // a partially guessed target.
  const partial = convertDirectionalRoute("React", "Vue 3", { "src/App.tsx": fixture["src/App.tsx"]! });
  assert.equal(partial.status, "BLOCKED");
  assert.equal(partial.irProvenance, "NONE");
  assert.deepEqual(partial.generatedFiles, {});
  assert.ok(partial.typedGaps.every(item => item.blocking));

  // Vue 2 now has a source extractor too: dropping only the declaration is a
  // supported source-derived route rather than a reason to trust less input.
  const vue2 = createDirectionalRouteFixture("Vue 2");
  const missing = convertDirectionalRoute("Vue 2", "React", {
    "src/App.vue": vue2["src/App.vue"]!,
    "package.json": vue2["package.json"]!,
  });
  assert.equal(missing.status, "GENERATED");
  assert.equal(missing.irProvenance, "SOURCE_DERIVED");
  assert.deepEqual(missing.typedGaps, []);
  assert.ok(Object.keys(missing.generatedFiles).length > 0);
});

test("a Vue 3 route run derives its IR from source while FRT-1305 keeps its deeper slice", () => {
  const fixture = createDirectionalRouteFixture("Vue 3");
  const sourceOnly = Object.fromEntries(
    Object.entries(fixture).filter(([path]) => path !== "frt-ui-ir.json"),
  );

  const runtime = createRuntime();
  const flutter = frtCatalog.skills.find(item => item.id === "FRT-1603");
  assert.ok(flutter);
  const derivedRun = runtime.run(request("FRT-1603", "EXECUTE", {
    key: "vue3-flutter-derived",
    ...(flutter.requiresCertificate ? { certificateBatch: flutter.requiresCertificate } : {}),
    input: { files: sourceOnly },
  }));
  assert.equal(derivedRun.state, "QUEUED");
  assert.equal(derivedRun.outcome, "PROPOSAL_READY_FOR_RUNNER");
  const migration = derivedRun.artifacts.routeMigration as { status: string; irProvenance: string };
  assert.equal(migration.status, "GENERATED");
  assert.equal(migration.irProvenance, "SOURCE_DERIVED");
  assert.equal(derivedRun.artifacts.routeRuntime, "TYPED_UI_IR_DIRECTIONAL_ROUTE_GENERATED");
  // Deriving the IR does not manufacture execution evidence: still a proposal.
  assert.ok(derivedRun.findings.some(item => item.code === "FRT_EXTERNAL_RUNNER_REQUIRED"));
  assert.equal(derivedRun.certificateFragment.eligibleForBatchGate, false);

  // FRT-1305 keeps routing source-only input through its own vertical slice,
  // which supports template and script constructs the counter IR cannot hold.
  const slice = createRuntime();
  const sliceSkill = frtCatalog.skills.find(item => item.id === "FRT-1305");
  assert.ok(sliceSkill);
  const sliceRun = slice.run(request("FRT-1305", "EXECUTE", {
    key: "vue3-react-slice",
    ...(sliceSkill.requiresCertificate ? { certificateBatch: sliceSkill.requiresCertificate } : {}),
    input: { files: sourceOnly },
  }));
  assert.equal(sliceRun.artifacts.routeRuntime, "VUE3_REACT_VERTICAL_SLICE_GENERATED");
});

test("typed UI IR derivation corpora stay separate and match their declared outcome", () => {
  const entries = [
    ["development", "vue3-increment-source.json"],
    ["negative", "vue3-missing-accessibility.json"],
    ["holdout", "vue3-decrement-source.json"],
    ["representative", "vue3-literal-title-source.json"],
  ] as const;
  const digests = new Set<string>();
  for (const [directory, name] of entries) {
    const raw = readFileSync(
      new URL(`../../test/fixtures/frt-ir/${directory}/${name}`, import.meta.url),
      "utf8",
    );
    digests.add(createHash("sha256").update(raw).digest("hex"));
    const fixture = JSON.parse(raw) as {
      corpusRole: string;
      files: Record<string, string>;
      expectedStatus: "GENERATED" | "BLOCKED";
      expectedGapCodes: readonly string[];
    };
    const result = convertDirectionalRoute("Vue 3", "Flutter", fixture.files);
    assert.equal(result.status, fixture.expectedStatus, fixture.corpusRole);
    assert.equal(
      result.irProvenance,
      fixture.expectedStatus === "GENERATED" ? "SOURCE_DERIVED" : "NONE",
      fixture.corpusRole,
    );
    for (const code of fixture.expectedGapCodes) {
      assert.ok(result.typedGaps.some(item => item.code === code), `${fixture.corpusRole} -> ${code}`);
    }
    if (fixture.expectedStatus === "GENERATED") {
      assert.deepEqual(result.typedGaps, [], fixture.corpusRole);
      assert.ok(Object.keys(result.generatedFiles).length >= 2, fixture.corpusRole);
    } else {
      assert.deepEqual(result.generatedFiles, {}, fixture.corpusRole);
    }
  }
  // Independent corpora, not four copies of one case.
  assert.equal(digests.size, entries.length);
});

test("the Vue 3 vertical slice converts compound assignment without a typed gap", () => {
  const compound = {
    "package.json": JSON.stringify({ dependencies: { vue: "3.5.39" } }),
    "src/App.vue": [
      `<script setup lang="ts">`,
      `import { ref } from "vue";`,
      `const count = ref(0);`,
      `function increment() { count.value += 2; }`,
      `</script>`,
      `<template><main><h1>{{ count }}</h1><button @click="increment">Add</button></main></template>`,
    ].join("\n"),
  };
  const migration = convertVue3ToReact(compound);
  assert.equal(migration.status, "GENERATED");
  assert.deepEqual(migration.typedGaps, []);
  assert.match(migration.generatedFiles["src/App.tsx"]!, /setCount\(previous => previous \+ 2\)/);
});

test("verification exposes missing evidence roles and never treats NOT_RUN as passed", () => {
  const runtime = createRuntime();
  const result = runtime.run(request("FRT-1701", "VERIFY", {
    key: "not-run-evidence",
    certificateBatch: "G16",
  }));
  assert.equal(result.state, "BLOCKED");
  assert.equal(result.outcome, "BLOCKED_BY_EVIDENCE");
  assert.equal(
    result.findings.filter(item => item.code === "FRT_EVIDENCE_NOT_RUN").length,
    result.requiredEvidenceRoles.length,
  );
  assert.equal(result.certificateFragment.eligibleForBatchGate, false);
});

test("complete independent evidence reaches the batch gate but cannot self-certify", () => {
  const runtime = createRuntime();
  const planned = runtime.run(request("FRT-1301", "PLAN", {
    key: "evidence-role-plan",
    certificateBatch: "G12",
  }));
  const evidence = planned.requiredEvidenceRoles.map((role, index) => signedEvidence(role, index));
  const verified = runtime.run(request("FRT-1301", "VERIFY", {
    key: "complete-evidence",
    certificateBatch: "G12",
    evidence,
  }));
  assert.equal(verified.state, "SUCCEEDED");
  assert.equal(verified.outcome, "READY_FOR_BATCH_GATE");
  assert.equal(verified.certificateFragment.eligibleForBatchGate, true);
  assert.equal(verified.certificateFragment.certification, "NOT_CERTIFIED");
  assert.equal(verified.certificateFragment.externalAuthorityRequired, true);
});

test("tampered certificates and evidence fail closed", () => {
  const runtime = createRuntime();
  const tamperedCertificate = {
    ...certificate("G12"),
    artifactDigest: `sha256:${"9".repeat(64)}`,
  };
  const certificateResult = runtime.run({
    ...request("FRT-1305", "PLAN", { key: "tampered-certificate" }),
    prerequisiteCertificates: [tamperedCertificate],
  });
  assert.equal(certificateResult.state, "BLOCKED");
  assert.ok(certificateResult.findings.some(item => item.code === "FRT_PREREQUISITE_UNVERIFIED"));

  const planned = runtime.run(request("FRT-1301", "PLAN", {
    key: "tampered-evidence-plan",
    certificateBatch: "G12",
  }));
  const evidence = planned.requiredEvidenceRoles.map((role, index) => signedEvidence(role, index));
  writeFileSync(new URL(evidence[0]!.uri), "content changed after attestation\n");
  const evidenceResult = runtime.run(request("FRT-1301", "VERIFY", {
    key: "tampered-evidence-verify",
    certificateBatch: "G12",
    evidence,
  }));
  assert.equal(evidenceResult.state, "BLOCKED");
  assert.ok(evidenceResult.findings.some(item => item.code === "FRT_EVIDENCE_ATTESTATION_INVALID"));
});

test("duplicate evidence roles and invalid attestations fail closed", () => {
  const runtime = createRuntime();
  const planned = runtime.run(request("FRT-1301", "PLAN", {
    key: "duplicate-evidence-plan",
    certificateBatch: "G12",
  }));
  const evidence = planned.requiredEvidenceRoles.map((role, index) => signedEvidence(role, index));
  const duplicate = signedEvidence(planned.requiredEvidenceRoles[0]!, 99);
  const duplicateResult = runtime.run(request("FRT-1301", "VERIFY", {
    key: "duplicate-evidence-verify",
    certificateBatch: "G12",
    evidence: [...evidence, duplicate],
  }));
  assert.equal(duplicateResult.state, "BLOCKED");
  assert.ok(duplicateResult.findings.some(item => item.code === "FRT_EVIDENCE_ROLE_DUPLICATED"));

  const invalidSignature = {
    ...evidence[1]!,
    signature: `${evidence[1]!.signature[0] === "A" ? "B" : "A"}${evidence[1]!.signature.slice(1)}`,
  };
  const signatureResult = runtime.run(request("FRT-1301", "VERIFY", {
    key: "invalid-evidence-signature",
    certificateBatch: "G12",
    evidence: evidence.map((item, index) => index === 1 ? invalidSignature : item),
  }));
  assert.equal(signatureResult.state, "BLOCKED");
  assert.ok(signatureResult.findings.some(item => item.code === "FRT_EVIDENCE_ATTESTATION_INVALID"));
});

test("idempotency is tenant scoped and rejects changed-input reuse", () => {
  const runtime = createRuntime();
  const first = runtime.run(request("FRT-0101", "PLAN", { key: "same-key" }));
  const replay = runtime.run(request("FRT-0101", "PLAN", { key: "same-key" }));
  assert.equal(replay.resultDigest, first.resultDigest);
  const conflict = runtime.run(request("FRT-0101", "PLAN", {
    key: "same-key",
    expectedVersion: 9,
  }));
  assert.equal(conflict.state, "FAILED");
  assert.ok(conflict.findings.some(item => item.message.includes("idempotency")));
});

test("batch plans are ordered and preserve the linear certificate dependency", () => {
  const runtime = createRuntime();
  const plan = runtime.planBatch({
    schemaVersion: "1.0",
    batch: "G13",
    idempotencyKey: "batch-g13",
    expectedVersion: 0,
    context,
    prerequisiteCertificates: [certificate("G12")],
  });
  assert.equal(plan.state, "READY");
  assert.equal(plan.dependsOn, "G12");
  assert.equal(plan.skillIds.length, 11);
  assert.deepEqual(plan.stages[0]?.dependsOn, []);
  assert.deepEqual(plan.stages[1]?.dependsOn, [plan.skillIds[0]]);
  assert.equal(plan.productionCertification, "NOT_CERTIFIED");
});

test("a live lease survives restart, heartbeats extend it, and expiry reclaims the run", () => {
  // A movable clock: leases are the one thing in this runtime that depends on real time.
  let clock = new Date(fixedNow);
  const leasedSecurity = { ...security, now: () => clock };
  const durableRoot = join(runStoreRoot, "lease-lifecycle");
  const build = () => new FrtRuntime({ security: leasedSecurity, store: new FileFrtRunStore(durableRoot) });

  const queued = build().run(request("FRT-0100", "EXECUTE", { key: "lease-lifecycle" }));
  assert.equal(queued.state, "QUEUED");
  assert.equal(queued.lease, null);

  const running = build().claim(scope, queued.runId, queued.version, "runner-one", 60)!;
  assert.equal(running.state, "RUNNING");
  assert.equal(running.lease?.runnerId, "runner-one");
  assert.equal(running.lease?.heartbeatCount, 0);

  // Restarting a control-plane instance must not kill a runner that is still healthy
  // on another instance, so a RUNNING run under a live lease is left alone.
  const afterRestart = build().getRun(scope, queued.runId)!;
  assert.equal(afterRestart.state, "RUNNING");
  assert.equal(afterRestart.version, running.version);

  // Only the holder may renew, and each renewal bumps the version.
  const runtime = build();
  assert.throws(
    () => runtime.heartbeat(scope, queued.runId, running.version, "runner-two"),
    /only the lease holder can renew the lease/,
  );
  clock = new Date(fixedNow.getTime() + 30_000);
  const renewed = runtime.heartbeat(scope, queued.runId, running.version, "runner-one", 60)!;
  assert.equal(renewed.state, "RUNNING");
  assert.equal(renewed.version, running.version + 1);
  assert.equal(renewed.lease?.heartbeatCount, 1);
  assert.ok(Date.parse(renewed.lease!.expiresAt) > Date.parse(running.lease!.expiresAt));

  // Past expiry the run is reclaimed, and an expired lease is never revived.
  clock = new Date(fixedNow.getTime() + 10 * 60_000);
  const sweeper = build();
  const expired = sweeper.getRun(scope, queued.runId)!;
  assert.equal(expired.state, "BLOCKED");
  assert.equal(expired.outcome, "BLOCKED_BY_LEASE_EXPIRED");
  assert.equal(expired.lease, null);
  assert.ok(expired.findings.some(item => item.code === "FRT_RUN_LEASE_EXPIRED" && item.blocking));
  assert.equal(sweeper.sweepExpiredLeases(), 0);

  const retried = sweeper.retry(scope, queued.runId, expired.version, "operator-retry")!;
  assert.equal(retried.state, "QUEUED");
  assert.equal(retried.lease, null);
  const cancelled = sweeper.cancel(scope, queued.runId, retried.version, "operator-cancel")!;
  assert.equal(cancelled.state, "CANCELLED");
  assert.deepEqual(
    sweeper.audit(scope, queued.runId)?.map(item => item.event),
    ["RUN_CREATED", "RUN_CLAIMED", "RUN_HEARTBEAT", "RUN_LEASE_EXPIRED", "RUN_RETRIED", "RUN_CANCELLED"],
  );

  const replayed = build().run(request("FRT-0100", "EXECUTE", { key: "lease-lifecycle" }));
  assert.equal(replayed.resultDigest, cancelled.resultDigest);
});
test("an attested runner completion closes the EXECUTE lifecycle without certifying it", () => {
  const durableRoot = join(runStoreRoot, "runner-completion");
  const runtime = createRuntime(new FileFrtRunStore(durableRoot));
  const queued = runtime.run(request("FRT-0100", "EXECUTE", { key: "runner-completion" }));
  assert.equal(queued.state, "QUEUED");
  assert.equal(queued.outcome, "PROPOSAL_READY_FOR_RUNNER");
  assert.ok(queued.findings.some(item => item.code === "FRT_EXTERNAL_RUNNER_REQUIRED"));
  assert.equal(queued.customerCodeExecuted, false);

  const running = runtime.claim(scope, queued.runId, queued.version, "runner-alpha")!;
  assert.equal(running.state, "RUNNING");

  const completed = runtime.complete(
    scope,
    queued.runId,
    running.version,
    "runner-alpha",
    runnerCompletion("runner-alpha", {
      evidence: [attributedEvidence("TARGET_BUILD", "runner-alpha", "verifier-independent")],
    }),
  )!;
  assert.equal(completed.state, "SUCCEEDED");
  assert.equal(completed.outcome, "RUNNER_EXECUTION_RECORDED");
  assert.equal(completed.version, running.version + 1);
  assert.equal(completed.customerCodeExecuted, true);
  assert.equal(completed.productionOperationExecuted, false);
  assert.ok(!completed.findings.some(item => item.code === "FRT_EXTERNAL_RUNNER_REQUIRED"));
  assert.ok(!completed.findings.some(item => item.blocking));
  assert.equal(completed.evidence.length, 1);

  // Recording an execution is never a certification.
  assert.equal(completed.certificateFragment.eligibleForBatchGate, false);
  assert.equal(completed.certificateFragment.certification, "NOT_CERTIFIED");
  assert.equal(completed.certificateFragment.externalAuthorityRequired, true);

  const summary = (completed.artifacts as { runnerCompletion?: Record<string, unknown> }).runnerCompletion;
  assert.equal(summary?.runnerId, "runner-alpha");
  assert.equal(summary?.attested, true);
  assert.match(String(summary?.completionDigest), /^sha256:[a-f0-9]{64}$/);

  assert.deepEqual(
    runtime.audit(scope, queued.runId)?.map(item => item.event),
    ["RUN_CREATED", "RUN_CLAIMED", "RUN_COMPLETED"],
  );

  // A terminal run is not reclaimed by restart recovery.
  const restarted = createRuntime(new FileFrtRunStore(durableRoot));
  const persisted = restarted.getRun(scope, queued.runId)!;
  assert.equal(persisted.state, "SUCCEEDED");
  assert.equal(persisted.version, completed.version);
});

test("runner completion rejects stale versions, unclaimed runs, and mismatched runner identity", () => {
  const runtime = createRuntime();
  const queued = runtime.run(request("FRT-0100", "EXECUTE", { key: "runner-completion-guards" }));
  assert.throws(
    () => runtime.complete(scope, queued.runId, queued.version, "runner-alpha", runnerCompletion("runner-alpha")),
    /only a claimed run can be completed/,
  );
  const running = runtime.claim(scope, queued.runId, queued.version, "runner-alpha")!;
  assert.throws(
    () => runtime.complete(scope, queued.runId, queued.version, "runner-alpha", runnerCompletion("runner-alpha")),
    /run version conflict/,
  );
  assert.throws(
    () => runtime.complete(scope, queued.runId, running.version, "runner-beta", runnerCompletion("runner-alpha")),
    /only the lease holder can complete the run/,
  );
  const completed = runtime.complete(
    scope,
    queued.runId,
    running.version,
    "runner-alpha",
    runnerCompletion("runner-alpha"),
  )!;
  assert.equal(completed.state, "SUCCEEDED");
  assert.throws(
    () => runtime.complete(scope, queued.runId, running.version, "runner-alpha", runnerCompletion("runner-alpha")),
    /run version conflict/,
  );
  assert.equal(runtime.complete(scope, "0".repeat(24), 0, "runner-alpha", runnerCompletion("runner-alpha")), undefined);
});

test("an unattested runner completion cannot report that customer code executed", () => {
  const runtime = createRuntime();
  const queued = runtime.run(request("FRT-0100", "EXECUTE", { key: "runner-unattested" }));
  const running = runtime.claim(scope, queued.runId, queued.version, "runner-alpha")!;
  const tampered: FrtRunnerCompletion = {
    ...runnerCompletion("runner-alpha", { customerCodeExecuted: true }),
    finishedAt: "2026-07-31T23:59:00Z",
  };
  const blocked = runtime.complete(scope, queued.runId, running.version, "runner-alpha", tampered)!;
  assert.equal(blocked.state, "BLOCKED");
  assert.equal(blocked.outcome, "BLOCKED_BY_RUNNER_ATTESTATION");
  assert.equal(blocked.customerCodeExecuted, false);
  assert.equal(blocked.productionOperationExecuted, false);
  assert.deepEqual(blocked.evidence, queued.evidence);
  assert.ok(blocked.findings.some(item => item.code === "FRT_RUNNER_ATTESTATION_INVALID" && item.blocking));

  const retried = runtime.retry(scope, queued.runId, blocked.version, "operator-retry")!;
  assert.equal(retried.state, "QUEUED");
});

test("a runner cannot verify its own evidence or report a failed run as successful", () => {
  const runtime = createRuntime();
  const queued = runtime.run(request("FRT-0100", "EXECUTE", { key: "runner-self-verified" }));
  const running = runtime.claim(scope, queued.runId, queued.version, "runner-alpha")!;
  const selfVerified = runtime.complete(
    scope,
    queued.runId,
    running.version,
    "runner-alpha",
    runnerCompletion("runner-alpha", {
      evidence: [attributedEvidence("TARGET_BUILD", "runner-alpha", "runner-alpha")],
    }),
  )!;
  assert.equal(selfVerified.state, "BLOCKED");
  assert.equal(selfVerified.outcome, "BLOCKED_BY_RUNNER_EVIDENCE");
  assert.ok(selfVerified.findings.some(
    item => item.code === "FRT_INDEPENDENT_VERIFIER_MISSING" && item.blocking,
  ));

  const failingRuntime = createRuntime();
  const failingQueued = failingRuntime.run(request("FRT-0100", "EXECUTE", { key: "runner-failed" }));
  const failingRunning = failingRuntime.claim(
    scope,
    failingQueued.runId,
    failingQueued.version,
    "runner-alpha",
  )!;
  const failed = failingRuntime.complete(
    scope,
    failingQueued.runId,
    failingRunning.version,
    "runner-alpha",
    runnerCompletion("runner-alpha", { exitStatus: "FAILED", customerCodeExecuted: true }),
  )!;
  assert.equal(failed.state, "FAILED");
  assert.equal(failed.outcome, "RUNNER_EXECUTION_FAILED");
  assert.equal(failed.customerCodeExecuted, true);
  assert.equal(failed.certificateFragment.eligibleForBatchGate, false);
});

test("canonical JSON is code-point ordered and matches the Python trust implementation", () => {
  // Locale collation is not code-point order. `localeCompare` reorders these keys under
  // cs, sk, lv, lt, az, uz, cy and the Spanish traditional collation, so a signature
  // minted on one host would fail to verify on another. It must never come back here.
  assert.equal(
    canonicalFrtJson({ ab: 4, _x: 1, "a-b": 3, Zulu: 2, a1: 5, aA: 6 }),
    '{"Zulu":2,"_x":1,"a-b":3,"a1":5,"aA":6,"ab":4}',
  );

  // Frozen parity vectors. These are byte-for-byte what
  // scripts/precision_migration/trust.py canonical_bytes() emits for the same values,
  // so both sides can share one trust store. Non-ASCII stays raw UTF-8: Python needs
  // ensure_ascii=False to match, and nested objects and arrays keep their own rules
  // (objects sorted, array order preserved).
  assert.equal(
    canonicalFrtJson({ note: "路径/名称", authority: "frt-认证" }),
    '{"authority":"frt-认证","note":"路径/名称"}',
  );
  assert.equal(
    canonicalFrtJson({ state: null, scope: { tenantId: "t", organizationId: "o" }, evidenceRefs: ["b", "a"] }),
    '{"evidenceRefs":["b","a"],"scope":{"organizationId":"o","tenantId":"t"},"state":null}',
  );

  // Key order in the source object must not reach the canonical form.
  const forward = { authority: "a", byteCount: 1, keyId: "k" };
  const reversed = { keyId: "k", byteCount: 1, authority: "a" };
  assert.equal(canonicalFrtJson(forward), canonicalFrtJson(reversed));
});

test("the trust store refuses a key that both executes and attests", () => {
  // Fail closed at load: an all-powerful key is a deployment error, and catching it here
  // means every call path inherits "the executor cannot vouch for itself" for free.
  assert.throws(
    () => new FrtTrustStore({
      schemaVersion: "1.0",
      keys: [trustKey("frt-all-powerful", attestingPem, ["execution-attester", "evidence-authorizer"])],
    }),
    /FRT_TRUST_KEY_ROLE_CONFLICT/,
  );
  assert.throws(
    () => new FrtTrustStore({
      schemaVersion: "1.0",
      keys: [trustKey("frt-all-powerful", attestingPem, ["execution-attester", "gate-evidence-authorizer"])],
    }),
    /FRT_TRUST_KEY_ROLE_CONFLICT/,
  );
  // The same conflict expressed through raw purposes is rejected identically.
  assert.throws(
    () => new FrtTrustStore({
      schemaVersion: "1.0",
      keys: [{
        ...trustKey("frt-raw-purposes", attestingPem, []),
        purposes: ["RUNNER", "EVIDENCE"],
      }],
    }),
    /FRT_TRUST_KEY_ROLE_CONFLICT/,
  );
  // Separated roles load fine and resolve to the purposes their names imply.
  const separated = new FrtTrustStore({
    schemaVersion: "1.0",
    keys: [
      trustKey("frt-attest", attestingPem, ["evidence-authorizer"]),
      trustKey("frt-execute", runnerPem, ["execution-attester"]),
    ],
  });
  assert.equal(separated.isRecordRevoked("sha256:" + "0".repeat(64)), false);
});

test("evidence signed with the runner's own key is not independent", () => {
  const runtime = createRuntime();
  const queued = runtime.run(request("FRT-0100", "EXECUTE", { key: "runner-shared-key" }));
  const running = runtime.claim(scope, queued.runId, queued.version, "runner-alpha")!;
  // Two different names, one key. Names are cheap to fake, so the key is what decides.
  const blocked = runtime.complete(
    scope,
    queued.runId,
    running.version,
    "runner-alpha",
    runnerCompletion("runner-alpha", {
      evidence: [attributedEvidence("TARGET_BUILD", "runner-alpha", "verifier-independent", runnerKeyId)],
    }),
  )!;
  assert.equal(blocked.state, "BLOCKED");
  assert.equal(blocked.outcome, "BLOCKED_BY_RUNNER_EVIDENCE");
  assert.ok(blocked.findings.some(
    item => item.code === "FRT_EVIDENCE_KEY_NOT_INDEPENDENT" && item.blocking,
  ));
});

test("a revoked record fails closed without revoking the key that signed everything else", () => {
  const evidence = attributedEvidence("TARGET_BUILD", "runner-alpha", "verifier-independent");
  const revoking = {
    trustStore: new FrtTrustStore({
      schemaVersion: "1.0",
      keys: [
        trustKey(signingKeyId, attestingPem, ["identity-issuer", "gate-evidence-authorizer", "evidence-authorizer"]),
        trustKey(runnerKeyId, runnerPem, ["execution-attester"]),
      ],
      revokedRecordIds: [evidence.digest],
    }),
    evidenceResolver: new ConfinedFileFrtEvidenceResolver([evidenceRoot]),
    now: () => fixedNow,
  };
  const runtime = new FrtRuntime({
    security: revoking,
    store: new FileFrtRunStore(join(runStoreRoot, "revocation")),
  });
  const queued = runtime.run(request("FRT-0100", "EXECUTE", { key: "revoked-record" }));
  const running = runtime.claim(scope, queued.runId, queued.version, "runner-alpha")!;
  const blocked = runtime.complete(
    scope,
    queued.runId,
    running.version,
    "runner-alpha",
    runnerCompletion("runner-alpha", { evidence: [evidence] }),
  )!;
  assert.equal(blocked.state, "BLOCKED");
  assert.ok(blocked.findings.some(
    item => item.code === "FRT_EVIDENCE_RECORD_REVOKED" && item.blocking,
  ));
  // The signing key itself is untouched: a different record still verifies.
  const other = attributedEvidence("TYPECHECK", "runner-alpha", "verifier-independent");
  assert.equal(revoking.trustStore.isRecordRevoked(other.digest), false);
});

test("a generated route is materialized into the artifact store, and says so when it is not", () => {
  const route = frtCatalog.routes.find(item => item.skillId === "FRT-1301")!;
  const input = { files: createDirectionalRouteFixture(route.source as FrtRouteStack) };

  const artifactRoot = mkdtempSync(join(tmpdir(), "elmos-frt-artifacts-"));
  try {
    const runtime = new FrtRuntime({
      security,
      store: new FileFrtRunStore(join(runStoreRoot, "materialize")),
      artifacts: new ContentAddressedFrtArtifactStore(artifactRoot),
    });
    const executed = runtime.run(request("FRT-1301", "EXECUTE", {
      key: "materialize-route",
      certificateBatch: "G12",
      input,
    }));
    const materialized = executed.artifacts.materializedArtifacts as {
      bundle: { uri: string; digest: string; byteCount: number };
      files: readonly { name: string; uri: string; digest: string }[];
    };
    assert.ok(materialized, "the generated workspace should be persisted");
    assert.match(materialized.bundle.digest, /^sha256:[a-f0-9]{64}$/);
    assert.ok(materialized.files.length > 0);
    // Names stay the paths inside the generated workspace even though the store keys by digest.
    assert.ok(materialized.files.every(file => file.name && file.digest.startsWith("sha256:")));
    assert.ok(!executed.findings.some(item => item.code === "FRT_ARTIFACT_STORE_NOT_CONFIGURED"));

    // Objects are addressed by content, so re-reading returns exactly what was written.
    const store = new ContentAddressedFrtArtifactStore(artifactRoot);
    assert.equal(store.resolve(materialized.bundle.uri).byteLength, materialized.bundle.byteCount);
  } finally {
    rmSync(artifactRoot, { recursive: true, force: true });
  }

  // Unconfigured is reported, not silently swallowed, and never blocks the proposal.
  const unconfigured = new FrtRuntime({
    security,
    store: new FileFrtRunStore(join(runStoreRoot, "materialize-off")),
    artifacts: new DenyAllFrtArtifactStore(),
  }).run(request("FRT-1301", "EXECUTE", {
    key: "materialize-route-off",
    certificateBatch: "G12",
    input,
  }));
  assert.equal(unconfigured.state, "QUEUED");
  assert.equal(unconfigured.artifacts.materializedArtifacts, undefined);
  const notConfigured = unconfigured.findings.find(
    item => item.code === "FRT_ARTIFACT_STORE_NOT_CONFIGURED",
  );
  assert.ok(notConfigured);
  assert.equal(notConfigured.blocking, false);
});

test("content-addressed backup restores run and idempotency state and rejects tampering", () => {
  const primaryRoot = join(runStoreRoot, "dr-primary");
  const runtime = createRuntime(new FileFrtRunStore(primaryRoot));
  const queued = runtime.run(request("FRT-0100", "EXECUTE", { key: "dr-replay" }));
  assert.equal(queued.state, "QUEUED");

  const backupPath = join(runStoreRoot, "dr-backups", "run-store.json");
  const backup = backupFrtRunStore(primaryRoot, backupPath, fixedNow);
  assert.ok(backup.entries.length >= 2);
  assert.match(backup.manifestDigest, /^sha256:[a-f0-9]{64}$/);

  const restoredRoot = join(runStoreRoot, "dr-restored");
  const restoration = restoreFrtRunStore(backupPath, restoredRoot);
  assert.equal(restoration.entryCount, backup.entries.length);
  assert.equal(restoration.manifestDigest, backup.manifestDigest);
  const restoredRuntime = createRuntime(new FileFrtRunStore(restoredRoot));
  assert.equal(restoredRuntime.getRun(scope, queued.runId)?.resultDigest, queued.resultDigest);
  const replayed = restoredRuntime.run(request("FRT-0100", "EXECUTE", { key: "dr-replay" }));
  assert.equal(replayed.resultDigest, queued.resultDigest);

  const tamperedPath = join(runStoreRoot, "dr-backups", "tampered.json");
  const tampered = JSON.parse(readFileSync(backupPath, "utf8")) as {
    entries: Array<{ contentBase64: string }>;
  };
  tampered.entries[0]!.contentBase64 = Buffer.from("tampered\n").toString("base64");
  writeFileSync(tamperedPath, `${JSON.stringify(tampered)}\n`);
  assert.throws(
    () => restoreFrtRunStore(tamperedPath, join(runStoreRoot, "dr-tampered-target")),
    /FRT_BACKUP_DIGEST_MISMATCH/,
  );
});

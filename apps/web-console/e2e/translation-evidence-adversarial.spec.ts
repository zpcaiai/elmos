import { createHash } from "node:crypto";
import {
  link,
  mkdir,
  mkdtemp,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { strToU8, zipSync } from "fflate";
import { translationLanguages } from "../app/lib/businessLines";
import type { TranslationLanguageId } from "../app/lib/contracts";
import type { GenerationRunnerError } from "../app/lib/server/generationRunner";
import {
  TranslationContractError,
  readTranslationCapability,
  readTranslationExecutionCapability,
} from "../app/lib/server/translationRoutes";
import {
  createTranslationJob,
  validateTranslationPipelineEvidence,
  type TranslationPipelineAdmission,
} from "../app/lib/server/translationRunner";

const sha256 = (content: Buffer | string) => createHash("sha256").update(content).digest("hex");

function expectTranslationContractError(
  operation: () => unknown,
  expectedCode?: string,
): void {
  try {
    operation();
  } catch (error) {
    expect(error).toBeInstanceOf(TranslationContractError);
    if (expectedCode) {
      expect((error as TranslationContractError).errorCode).toBe(expectedCode);
    }
    return;
  }
  throw new Error("预期 translation contract fail closed，但调用成功。");
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "number") return JSON.stringify(value);
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().map((key) =>
    `${JSON.stringify(key)}:${canonicalJson(record[key])}`).join(",")}}`;
}

const inventoryVersions: Record<string, string> = {
  cpp: "C++20 / Apple clang 21.0.0 / arm64-apple-darwin25.6.0",
  csharp: "10.0.301",
  go: "1.25.0",
  java: "21.0.11",
  objc: "Objective-C / Apple clang 21.0.0 / arm64-apple-darwin25.6.0",
  python: "3.12.12",
  rust: "1.89.0",
  swift: "Swift 6.3.3 / arm64-apple-macosx26.0",
  typescript: "5.9.2 / Node 26.0.0",
};

const consoleLanguageIds = [
  "java",
  "csharp",
  "go",
  "rust",
  "python",
  "typescript",
] as const satisfies readonly TranslationLanguageId[];

const currentSpecialistPairs = [
  ["cpp", "objc"],
  ["objc", "cpp"],
  ["cpp", "swift"],
  ["swift", "cpp"],
  ["objc", "swift"],
  ["swift", "objc"],
  ["cpp", "java"],
  ["java", "cpp"],
] as const satisfies readonly (readonly [TranslationLanguageId, TranslationLanguageId])[];

const repositoryEvidence = (overrides: Record<string, unknown> = {}) => ({
  schema_version: "1.0.0",
  kind: "elmos.repository-route-execution-evidence",
  route_id: "python-to-typescript",
  source_language: "python",
  target_language: "typescript",
  profile: "repository-wide-v1",
  status: "PASSED",
  repository_execution_status: "PASSED",
  external_verification_status: "NOT_RUN",
  certification_status: "NOT_CERTIFIED",
  ...overrides,
});

async function routeContractFixture(
  evidence: Record<string, unknown>,
  options: { descriptorContent?: Buffer; linkKind?: "symlink" | "hardlink" } = {},
) {
  const root = await mkdtemp(path.join(tmpdir(), "elmos-web-route-evidence-"));
  const routeRoot = path.join(root, "routes", "python-to-typescript");
  const certification = path.join(routeRoot, "certification");
  await mkdir(certification, { recursive: true });
  await writeFile(path.join(root, "pom.xml"), "<project/>\n");
  await writeFile(path.join(routeRoot, "route.json"), "{}\n");
  const evidenceContent = Buffer.from(`${JSON.stringify(evidence)}\n`);
  const descriptorContent = options.descriptorContent ?? evidenceContent;
  const evidencePath = path.join(certification, "repository-evidence.json");
  if (options.linkKind) {
    const external = path.join(root, "external-evidence.json");
    await writeFile(external, evidenceContent);
    if (options.linkKind === "symlink") await symlink(external, evidencePath);
    else await link(external, evidencePath);
  } else {
    await writeFile(evidencePath, evidenceContent);
  }
  const inventory = {
    schema_version: "1.3.0",
    semantic_profile: "typed-pure-function-v1",
    console_exposed_languages: ["java", "csharp", "go", "rust", "python", "typescript"],
    route_count: 1,
    research_route_count: 0,
    experimental_route_count: 0,
    limited_route_count: 1,
    blocked_route_count: 0,
    certified_route_count: 0,
    local_execution_evidence: "PASSED_LOCAL",
    independent_verification_evidence: "NOT_RUN",
    external_certification_evidence: "NOT_RUN",
    languages: Object.fromEntries(translationLanguages.map((language) => [language.id, {
      version: inventoryVersions[language.id],
      engine_path: language.enginePath,
    }])),
    routes: [{
      route_key: "python-to-typescript",
      source: "python",
      target: "typescript",
      source_version: inventoryVersions.python,
      target_version: inventoryVersions.typescript,
      status: "limited",
      local_execution_status: "PASSED_LOCAL",
      repository_execution_status: "PASSED",
      repository_profile: "repository-wide-v1",
      repository_evidence_ref: "certification/repository-evidence.json",
      repository_evidence_sha256: sha256(descriptorContent),
      repository_evidence_bytes: descriptorContent.byteLength,
      independent_verification_status: "NOT_RUN",
      external_certification_status: "NOT_RUN",
    }],
  };
  await writeFile(path.join(root, "routes", "inventory.json"), `${JSON.stringify(inventory)}\n`);
  return { root, evidencePath, evidenceContent };
}

function inventoryRoute(
  source: TranslationLanguageId,
  target: TranslationLanguageId,
) {
  return {
    route_key: `${source}-to-${target}`,
    source,
    target,
    source_version: inventoryVersions[source],
    target_version: inventoryVersions[target],
    status: "limited",
    local_execution_status: "PASSED_LOCAL",
    repository_execution_status: "NOT_RUN",
    repository_profile: null,
    repository_evidence_ref: null,
    repository_evidence_sha256: null,
    repository_evidence_bytes: null,
    independent_verification_status: "NOT_RUN",
    external_certification_status: "NOT_RUN",
  } as const;
}

async function matrixContractFixture(
  routeMode: "LEGACY_38" | "COMPLETE_72",
  exposedLanguages: readonly TranslationLanguageId[],
) {
  const container = await mkdtemp(path.join(tmpdir(), "elmos-web-route-matrix-"));
  const root = path.join(container, "repository");
  const sourceRoot = path.join(container, "sources");
  const casesRoot = path.join(container, "cases");
  const runnerRoot = path.join(container, "runner");
  await Promise.all([
    mkdir(path.join(root, "routes"), { recursive: true }),
    mkdir(path.join(root, "engines", "polyglot-route-engine"), { recursive: true }),
    mkdir(sourceRoot, { recursive: true }),
    mkdir(casesRoot, { recursive: true }),
    mkdir(runnerRoot, { recursive: true }),
  ]);
  await writeFile(path.join(root, "pom.xml"), "<project/>\n");

  const corePairs = consoleLanguageIds.flatMap((source) =>
    consoleLanguageIds
      .filter((target) => target !== source)
      .map((target) => [source, target] as const));
  const pairs = routeMode === "COMPLETE_72"
    ? translationLanguages.flatMap((source) =>
      translationLanguages
        .filter((target) => target.id !== source.id)
        .map((target) => [source.id, target.id] as const))
    : [...corePairs, ...currentSpecialistPairs];
  const routes = pairs.map(([source, target]) => inventoryRoute(source, target));
  await Promise.all(routes.map(async (route) => {
    const routeRoot = path.join(root, "routes", route.route_key);
    await mkdir(routeRoot, { recursive: true });
    await writeFile(path.join(routeRoot, "route.json"), "{}\n");
  }));
  await writeFile(path.join(root, "routes", "inventory.json"), `${JSON.stringify({
    schema_version: "1.3.0",
    semantic_profile: "typed-pure-function-v1",
    console_exposed_languages: exposedLanguages,
    route_count: routes.length,
    research_route_count: 0,
    experimental_route_count: 0,
    limited_route_count: routes.length,
    blocked_route_count: 0,
    certified_route_count: 0,
    local_execution_evidence: "PASSED_LOCAL",
    independent_verification_evidence: "NOT_RUN",
    external_certification_evidence: "NOT_RUN",
    languages: Object.fromEntries(translationLanguages.map((language) => [language.id, {
      version: inventoryVersions[language.id],
      engine_path: language.enginePath,
    }])),
    routes,
  })}\n`);
  return { container, root, sourceRoot, casesRoot, runnerRoot };
}

const runnerEnvironmentKeys = [
  "ELMOS_REPOSITORY_ROOT",
  "ELMOS_LOCAL_RUNNER_ENABLED",
  "ELMOS_LOCAL_RUNNER_ROOT",
  "ELMOS_TRANSLATION_SOURCE_ROOT",
  "ELMOS_TRANSLATION_CASES_ROOT",
  "ELMOS_UV_PATH",
  "ELMOS_LOCAL_RUNNER_EXECUTOR",
  "NODE_ENV",
] as const;

async function expectRepositoryAdmissionRejected(
  fixture: Awaited<ReturnType<typeof matrixContractFixture>>,
  sourceLanguage: TranslationLanguageId,
  targetLanguage: TranslationLanguageId,
  expectedCode = "TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE",
): Promise<void> {
  const previous = new Map(runnerEnvironmentKeys.map((key) => [key, process.env[key]]));
  try {
    process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
    process.env.ELMOS_LOCAL_RUNNER_ENABLED = "true";
    process.env.ELMOS_LOCAL_RUNNER_ROOT = fixture.runnerRoot;
    process.env.ELMOS_TRANSLATION_SOURCE_ROOT = fixture.sourceRoot;
    process.env.ELMOS_TRANSLATION_CASES_ROOT = fixture.casesRoot;
    process.env.ELMOS_UV_PATH = process.execPath;
    process.env.ELMOS_LOCAL_RUNNER_EXECUTOR = "HOST_DEVELOPMENT";
    Reflect.set(process.env, "NODE_ENV", "test");
    await expect(createTranslationJob(
      { tenantId: "matrix-e2e", actor: "user:matrix-e2e" },
      { sourceLanguage, targetLanguage },
    )).rejects.toMatchObject({
      status: 409,
      code: expectedCode,
    } satisfies Partial<GenerationRunnerError>);
  } finally {
    for (const [key, value] of previous) {
      if (value === undefined) Reflect.deleteProperty(process.env, key);
      else Reflect.set(process.env, key, value);
    }
  }
}

test.describe.serial("仓库路线证据描述符 fail closed", () => {
  const originalRoot = process.env.ELMOS_REPOSITORY_ROOT;

  test.afterEach(async () => {
    if (originalRoot === undefined) delete process.env.ELMOS_REPOSITORY_ROOT;
    else process.env.ELMOS_REPOSITORY_ROOT = originalRoot;
  });

  test("有效证据按 9 语言执行目录读取，但公开控制台仍只暴露 inventory 的 6 语言", async () => {
    const fixture = await routeContractFixture(repositoryEvidence());
    try {
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      const consoleCapability = readTranslationCapability();
      const executionCapability = readTranslationExecutionCapability();
      expect(consoleCapability.languages.map((language) => language.id)).toEqual([
        "java", "csharp", "go", "rust", "python", "typescript",
      ]);
      expect(consoleCapability.routes.map((route) => route.id)).toEqual(["python-to-typescript"]);
      expect(executionCapability.languages).toHaveLength(9);
      expect(executionCapability.routes[0]).toMatchObject({
        repositoryExecutionStatus: "PASSED",
        repositoryProfile: "repository-wide-v1",
        repositoryEvidenceSha256: sha256(fixture.evidenceContent),
        repositoryEvidenceBytes: fixture.evidenceContent.byteLength,
      });
    } finally {
      await rm(fixture.root, { recursive: true, force: true });
    }
  });

  for (const scenario of [
    { name: "空对象", evidence: {} },
    { name: "反向路线", evidence: repositoryEvidence({ source_language: "typescript", target_language: "python" }) },
    { name: "NOT_RUN", evidence: repositoryEvidence({ repository_execution_status: "NOT_RUN" }) },
    { name: "Profile mismatch", evidence: repositoryEvidence({ profile: "typed-pure-function-v1" }) },
  ]) {
    test(`拒绝${scenario.name}证据`, async () => {
      const fixture = await routeContractFixture(scenario.evidence);
      try {
        process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
        expectTranslationContractError(() => readTranslationExecutionCapability());
      } finally {
        await rm(fixture.root, { recursive: true, force: true });
      }
    });
  }

  test("拒绝 descriptor 绑定后被篡改的证据", async () => {
    const original = Buffer.from(`${JSON.stringify(repositoryEvidence())}\n`);
    const fixture = await routeContractFixture(
      repositoryEvidence({ status: "FAILED" }),
      { descriptorContent: original },
    );
    try {
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      expectTranslationContractError(
        () => readTranslationExecutionCapability(),
        "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_INTEGRITY_MISMATCH",
      );
    } finally {
      await rm(fixture.root, { recursive: true, force: true });
    }
  });

  for (const linkKind of ["symlink", "hardlink"] as const) {
    test(`拒绝${linkKind}仓库证据`, async () => {
      const fixture = await routeContractFixture(repositoryEvidence(), { linkKind });
      try {
        process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
        expectTranslationContractError(
          () => readTranslationExecutionCapability(),
          "TRANSLATION_ROUTE_REPOSITORY_EVIDENCE_UNSAFE",
        );
      } finally {
        await rm(fixture.root, { recursive: true, force: true });
      }
    });
  }

  test("专业 8 路线重放变为 PASSED_LOCAL 仍不越过 6 语言公开策略或仓库证据门禁", async () => {
    const fixture = await matrixContractFixture("LEGACY_38", consoleLanguageIds);
    try {
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      const consoleCapability = readTranslationCapability();
      const executionCapability = readTranslationExecutionCapability();
      expect(consoleCapability.languages.map((language) => language.id)).toEqual(consoleLanguageIds);
      expect(consoleCapability.routes).toHaveLength(30);
      expect(executionCapability.languages).toHaveLength(9);
      expect(executionCapability.routes).toHaveLength(38);
      expect(executionCapability.routes.filter((route) =>
        route.source === "cpp" || route.source === "objc" || route.source === "swift"
        || route.target === "cpp" || route.target === "objc" || route.target === "swift"))
        .toHaveLength(8);
      expect(executionCapability.routes.every((route) =>
        route.localExecution === "PASSED"
        && route.repositoryExecutionStatus === "NOT_RUN"
        && route.repositoryProfile === null
        && route.repositoryEvidenceRef === null)).toBe(true);
      expect(executionCapability.repositoryExecutableRouteCount).toBe(0);
      await expectRepositoryAdmissionRejected(fixture, "cpp", "swift");
    } finally {
      await rm(fixture.container, { recursive: true, force: true });
    }
  });

  test("旧 38 路线清单即使公开 9 语言也不会伪造缺失的 34 条方向", async () => {
    const fixture = await matrixContractFixture(
      "LEGACY_38",
      translationLanguages.map((language) => language.id),
    );
    try {
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      const capability = readTranslationCapability();
      expect(capability.languages).toHaveLength(9);
      expect(capability.routes).toHaveLength(38);
      expect(capability.routePackageCount).toBe(38);
      expect(capability.routes.some((route) => route.id === "python-to-swift")).toBe(false);
      expect(capability.repositoryExecutableRouteCount).toBe(0);
      expect(capability.repositoryExecutionEvidence).toBe("NOT_RUN");
    } finally {
      await rm(fixture.container, { recursive: true, force: true });
    }
  });

  test("真实 72 路线公开 9 语言且新增路线 409；未来 PASSED_LOCAL 仍不能创建仓库任务", async () => {
    const actualContainer = await mkdtemp(path.join(tmpdir(), "elmos-web-actual-matrix-"));
    const actualFixture = {
      container: actualContainer,
      root: path.resolve(__dirname, "../../.."),
      sourceRoot: path.join(actualContainer, "sources"),
      casesRoot: path.join(actualContainer, "cases"),
      runnerRoot: path.join(actualContainer, "runner"),
    };
    try {
      await Promise.all([
        mkdir(actualFixture.sourceRoot, { recursive: true }),
        mkdir(actualFixture.casesRoot, { recursive: true }),
        mkdir(actualFixture.runnerRoot, { recursive: true }),
      ]);
      process.env.ELMOS_REPOSITORY_ROOT = actualFixture.root;
      const actualCapability = readTranslationCapability();
      expect(actualCapability.languages).toHaveLength(9);
      expect(actualCapability.routes).toHaveLength(72);
      expect(new Set(actualCapability.routes.map((route) => route.id))).toHaveProperty("size", 72);
      expect(actualCapability.repositoryExecutableRouteCount).toBe(0);
      expect(actualCapability.repositoryExecutionEvidence).toBe("NOT_RUN");
      expect(actualCapability.routes.find((route) => route.id === "objc-to-go"))
        .toMatchObject({
          localExecution: "NOT_RUN",
          repositoryExecutionStatus: "NOT_RUN",
          repositoryProfile: null,
          repositoryEvidenceRef: null,
          skill: "b29-route-certification-gate",
        });
      await expectRepositoryAdmissionRejected(
        actualFixture,
        "objc",
        "go",
        "TRANSLATION_ROUTE_NOT_LOCALLY_EXECUTABLE",
      );
    } finally {
      await rm(actualContainer, { recursive: true, force: true });
    }

    const fixture = await matrixContractFixture(
      "COMPLETE_72",
      translationLanguages.map((language) => language.id),
    );
    try {
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      const capability = readTranslationCapability();
      expect(capability.languages).toHaveLength(9);
      expect(capability.routes).toHaveLength(72);
      expect(new Set(capability.routes.map((route) => route.id))).toHaveProperty("size", 72);
      expect(capability.routes.every((route) =>
        route.localExecution === "PASSED"
        && route.repositoryExecutionStatus === "NOT_RUN")).toBe(true);
      expect(capability.routes.find((route) => route.id === "java-to-python")?.skill)
        .toBe("b29-certify-java-to-python");
      expect(capability.routes.find((route) => route.id === "objc-to-go")?.skill)
        .toBe("b29-route-certification-gate");
      expect(capability.repositoryExecutableRouteCount).toBe(0);
      expect(capability.repositoryExecutionEvidence).toBe("NOT_RUN");
      await expectRepositoryAdmissionRejected(fixture, "objc", "go");
    } finally {
      await rm(fixture.container, { recursive: true, force: true });
    }
  });
});

async function writePipelineFixture(root: string): Promise<{
  pipeline: string;
  admission: TranslationPipelineAdmission;
  report: Record<string, unknown>;
  manifest: Record<string, unknown>;
}> {
  const pipeline = path.join(root, "pipeline");
  await mkdir(path.join(pipeline, "batch"), { recursive: true });
  await mkdir(path.join(pipeline, "assembled"), { recursive: true });
  const snapshot = "1".repeat(64);
  const coverageKey = `python:sha256:${"2".repeat(64)}`;
  const graphPayload = {
    schema_version: "1.0.0",
    kind: "elmos.content-addressed-project-graph",
    discovery_profile: "static-project-graph-v1",
    repository_ref: "local:pipeline-fixture",
    repository_id: `elmos:repository:sha256:${"3".repeat(64)}`,
    snapshot_sha256: snapshot,
    snapshot_consistency: "PER_FILE_STABLE_READ_NON_ATOMIC",
    supported_languages: ["python", "typescript"],
    indexers: {},
    repository_complete: true,
    completeness_status: "COMPLETE",
    inventory: {},
    nodes: [{
      id: `elmos:symbol:sha256:${"4".repeat(64)}`,
      kind: "symbol",
      name: "add",
      path: "math.py",
      language: "python",
      source_location: { path: "math.py", start_line: 1 },
      attributes: {
        coverage_key: coverageKey,
        conversion_coverage_requirement: "REQUIRED",
      },
    }],
    edges: [],
    diagnostic_obligations: [],
    execution_status: "NOT_RUN",
    external_verification_status: "NOT_RUN",
    certification_status: "NOT_CERTIFIED",
    limitations: [],
  };
  const graphSha256 = sha256(canonicalJson(graphPayload));
  const graph = {
    ...graphPayload,
    graph_sha256: graphSha256,
    graph_id: `elmos:project-graph:sha256:${graphSha256}`,
  };
  const graphSummary = {
    path: "project-graph.json",
    graph_id: graph.graph_id,
    graph_sha256: graphSha256,
    snapshot_sha256: snapshot,
    repository_complete: true,
    completeness_status: "COMPLETE",
    obligation_count: 0,
    obligation_status_counts: { FAILED: 0, NOT_RUN: 0, PASSED: 0, UNKNOWN: 0 },
    verification_status: "PASSED",
  };
  const coverage = {
    profile: "python-ast-symbol-coverage-v1",
    source_language: "python",
    inventory_status: "PASSED",
    status: "PASSED",
    complete: true,
    subject_count: 1,
    status_counts: { BLOCKED: 0, FAILED: 0, NOT_RUN: 0, PASSED: 1, UNKNOWN: 0 },
    subjects: [{
      coverage_key: coverageKey,
      node_id: graphPayload.nodes[0].id,
      path: "math.py",
      qualified_name: "add",
      subject_kind: "top-level-function",
      source_location: { path: "math.py", start_line: 1 },
      status: "PASSED",
      reason: null,
      ready_unit_ids: ["WU-00001"],
      batch_status: "PASSED",
      blocker_codes: [],
    }],
    reason: null,
  };
  const behaviorCoverage = {
    profile: "typed-pure-function-v1",
    status: "PASSED",
    complete: true,
    work_unit_denominator: 1,
    work_unit_count: 1,
    accounted_work_unit_count: 1,
    attempted_work_unit_count: 1,
    unresolved_work_unit_count: 0,
    pass_rate: 1,
    behavior_case_count: 3,
    behavior_case_count_scope: "PASSED_WORK_UNITS_ONLY",
    status_counts: { FAILED: 0, NOT_RUN: 0, PASSED: 1, UNKNOWN: 0 },
    units: [{
      id: "WU-00001",
      source_path: "math.py",
      function_name: "add",
      batch_status: "PASSED",
      status: "PASSED",
      behavior_case_count: 3,
      evidence_path: "units/WU-00001/route-evidence.json",
      evidence_sha256: `sha256:${"7".repeat(64)}`,
    }],
    evidence_strength: "LOCAL_SOURCE_TARGET_RUNTIME_COMPARISON",
    independent_verification_status: "NOT_RUN",
    external_verification_status: "NOT_RUN",
  };
  const files: Record<string, Buffer> = {
    "project-graph.json": Buffer.from(`${JSON.stringify(graph)}\n`),
    "repository-route-plan.json": Buffer.from("{}\n"),
    "repository-discovery-report.json": Buffer.from("{}\n"),
    "batch/batch-report.json": Buffer.from("{}\n"),
    "batch/batch-checkpoint.jsonl": Buffer.from('{"id":"WU-00001","status":"PASSED"}\n'),
    "assembled/assembly-manifest.json": Buffer.from("{}\n"),
  };
  for (const [relative, content] of Object.entries(files)) {
    const destination = path.join(pipeline, ...relative.split("/"));
    await mkdir(path.dirname(destination), { recursive: true });
    await writeFile(destination, content);
  }
  const descriptors = Object.entries(files).map(([relative, content]) => ({
    path: relative,
    bytes: content.byteLength,
    sha256: sha256(content),
  }));
  const manifest: Record<string, unknown> = {
    schema_version: "1.0.0",
    kind: "elmos.repository-migration-artifact-manifest",
    status: "COMPLETE",
    repository_ref: "local:pipeline-fixture",
    snapshot_sha256: snapshot,
    repository_scale: "small",
    repository_limits: {},
    route_id: "python-to-typescript",
    source_language: "python",
    target_language: "typescript",
    profile: "typed-pure-function-v1",
    unit_batch_status: "COMPLETE",
    project_graph: graphSummary,
    conversion_coverage: coverage,
    behavior_coverage: behaviorCoverage,
    repository_complete: true,
    local_execution_evidence: "PASSED",
    repository_execution_status: "PASSED_LOCAL",
    files: descriptors,
    independent_verification_status: "NOT_RUN",
    external_verification_status: "NOT_RUN",
    certification_status: "NOT_CERTIFIED",
  };
  const manifestContent = Buffer.from(`${JSON.stringify(manifest)}\n`);
  await writeFile(path.join(pipeline, "artifact-manifest.json"), manifestContent);
  const zipFiles = Object.fromEntries([
    ...Object.entries(files).map(([relative, content]) => [relative, new Uint8Array(content)]),
    ["artifact-manifest.json", strToU8(manifestContent.toString("utf-8"))],
  ]);
  const archive = Buffer.from(zipSync(zipFiles, { level: 6 }));
  await writeFile(path.join(pipeline, "repository-migration-artifact.zip"), archive);
  const report: Record<string, unknown> = {
    schema_version: "1.0.0",
    kind: "elmos.repository-pipeline-report",
    status: "COMPLETE",
    repository_ref: "local:pipeline-fixture",
    snapshot_sha256: snapshot,
    route_id: "python-to-typescript",
    source_language: "python",
    target_language: "typescript",
    profile: "typed-pure-function-v1",
    unit_batch_status: "COMPLETE",
    project_graph: graphSummary,
    conversion_coverage: coverage,
    behavior_coverage: behaviorCoverage,
    repository_complete: true,
    work_unit_count: 1,
    ready_count: 1,
    resumed_count: 0,
    status_counts: { PASSED: 1 },
    included_unit_count: 1,
    excluded_units: [],
    build_verification: {
      status: "PASSED",
      commands: [{ command: ["tsc", "-p", "tsconfig.json"], stdout: "", stderr: "" }],
      toolchain: { language: "typescript", version: "5.9.2 / Node 26.0.0" },
    },
    artifact: {
      path: "repository-migration-artifact.zip",
      bytes: archive.byteLength,
      sha256: sha256(archive),
    },
    local_execution_evidence: "PASSED",
    repository_execution_status: "PASSED_LOCAL",
    independent_verification_status: "NOT_RUN",
    external_verification_status: "NOT_RUN",
    certification_status: "NOT_CERTIFIED",
  };
  await writeFile(path.join(pipeline, "repository-pipeline-report.json"), `${JSON.stringify(report)}\n`);
  return {
    pipeline,
    admission: {
      repositoryRef: "local:pipeline-fixture",
      sourceLanguage: "python",
      targetLanguage: "typescript",
      repositoryProfile: "typed-pure-function-v1",
      repositoryEvidenceSha256: "5".repeat(64),
      repositoryEvidenceBytes: 100,
    },
    report,
    manifest,
  };
}

test("Runner 从 report/graph/manifest/ZIP 原始字节重算完整闭包", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "elmos-web-pipeline-evidence-"));
  try {
    const fixture = await writePipelineFixture(root);
    const validated = await validateTranslationPipelineEvidence(fixture.pipeline, fixture.admission);
    expect(validated.report.status).toBe("COMPLETE");
    expect(validated.semanticCoverage).toMatchObject({
      status: "PASSED",
      subjectCount: 1,
      statusCounts: { PASSED: 1, NOT_RUN: 0 },
    });
    expect(validated.behaviorCoverage).toMatchObject({
      status: "PASSED",
      workUnitCount: 1,
      behaviorCaseCount: 3,
      statusCounts: { PASSED: 1, NOT_RUN: 0 },
      independentVerificationStatus: "NOT_RUN",
    });
    expect(validated.artifactSha256).toHaveLength(64);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

for (const scenario of [
  { name: "unit_batch_status", mutate: (report: Record<string, unknown>) => { report.unit_batch_status = "PARTIAL"; } },
  { name: "status_counts", mutate: (report: Record<string, unknown>) => { report.status_counts = { PASSED: 0 }; } },
  { name: "included/work units", mutate: (report: Record<string, unknown>) => { report.included_unit_count = 0; } },
  {
    name: "conversion_coverage",
    mutate: (report: Record<string, unknown>) => {
      report.conversion_coverage = { ...(report.conversion_coverage as object), complete: false };
    },
  },
  {
    name: "behavior_coverage",
    mutate: (report: Record<string, unknown>) => {
      report.behavior_coverage = {
        ...(report.behavior_coverage as object),
        accounted_work_unit_count: 0,
      };
    },
  },
  {
    name: "project graph",
    mutate: (report: Record<string, unknown>) => {
      report.project_graph = { ...(report.project_graph as object), graph_sha256: "6".repeat(64) };
    },
  },
] as const) {
  test(`Runner 对 ${scenario.name} 不一致返回 409`, async () => {
    const root = await mkdtemp(path.join(tmpdir(), "elmos-web-pipeline-mismatch-"));
    try {
      const fixture = await writePipelineFixture(root);
      scenario.mutate(fixture.report);
      await writeFile(
        path.join(fixture.pipeline, "repository-pipeline-report.json"),
        `${JSON.stringify(fixture.report)}\n`,
      );
      await expect(validateTranslationPipelineEvidence(fixture.pipeline, fixture.admission)).rejects.toMatchObject({
        status: 409,
      } satisfies Partial<GenerationRunnerError>);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
}

test("Runner 拒绝 artifact manifest 与 ZIP 引用不一致", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "elmos-web-pipeline-artifact-mismatch-"));
  try {
    const fixture = await writePipelineFixture(root);
    fixture.manifest.route_id = "typescript-to-python";
    await writeFile(
      path.join(fixture.pipeline, "artifact-manifest.json"),
      `${JSON.stringify(fixture.manifest)}\n`,
    );
    await expect(validateTranslationPipelineEvidence(fixture.pipeline, fixture.admission)).rejects.toMatchObject({
      status: 409,
    } satisfies Partial<GenerationRunnerError>);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

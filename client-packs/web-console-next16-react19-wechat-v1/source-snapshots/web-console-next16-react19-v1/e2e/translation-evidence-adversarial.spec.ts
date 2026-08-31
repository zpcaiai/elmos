import { createHash } from "node:crypto";
import {
  link,
  mkdir,
  mkdtemp,
  readFile,
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
  RepositoryPlanError,
  validateRepositoryPlan,
} from "../app/lib/server/translationRepositoryPlan";
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

function expectRepositoryPlanError(operation: () => unknown, expectedCode: string): void {
  try {
    operation();
  } catch (error) {
    expect(error).toBeInstanceOf(RepositoryPlanError);
    expect((error as RepositoryPlanError).errorCode).toBe(expectedCode);
    return;
  }
  throw new Error("预期 repository plan fail closed，但调用成功。");
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "number") return JSON.stringify(value);
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().map((key) =>
    `${JSON.stringify(key)}:${canonicalJson(record[key])}`).join(",")}}`;
}

const activeLanguageIds = [
  "java",
  "csharp",
  "go",
  "rust",
  "python",
  "typescript",
  "cpp",
  "objc",
  "swift",
  "php",
  "kotlin",
  "react",
  "flutter",
] as const satisfies readonly TranslationLanguageId[];

const legacyConsoleLanguageIds = [
  "java",
  "csharp",
  "go",
  "rust",
  "python",
  "typescript",
] as const satisfies readonly TranslationLanguageId[];

const researchOnlyLanguageIds = new Set<TranslationLanguageId>([
  "kotlin",
  "react",
  "flutter",
]);

const targetEmitterPath =
  "engines/polyglot-route-engine/src/elmos_polyglot_route/emitter.py";

const inventoryVersions: Record<TranslationLanguageId, string> = {
  cpp: "C++20 / Apple clang 21.0.0 / arm64-apple-darwin25.6.0",
  csharp: "10.0.301",
  flutter: "Flutter 3.44.1 / Dart 3.12.1 / analyzer 10.1.0",
  go: "1.25.0",
  java: "21.0.11",
  kotlin: "Kotlin 2.2.20 / JDK 21.0.11 / compiler PSI",
  objc: "Objective-C / Apple clang 21.0.0 / arm64-apple-darwin25.6.0",
  php: "PHP 8.5.9 (NTS) / ext/tokenizer",
  python: "3.12.12",
  react: "React 19.2.7 / TypeScript 5.9.2 / Node 26.0.0",
  rust: "1.89.0",
  swift: "Swift 6.3.3 / arm64-apple-macosx26.0",
  typescript: "5.9.2 / Node 26.0.0",
};

const exactInventoryVersions: Record<TranslationLanguageId, string[]> = {
  java: ["Java 21.0.11", "JDK Compiler Tree API"],
  python: ["Python 3.12.12", "CPython AST"],
  csharp: ["C# 14", ".NET SDK 10.0.301", "Roslyn 5.6.0"],
  typescript: ["TypeScript 5.9.2", "Node.js 26.0.0"],
  go: ["Go 1.25.0", "go/parser AST"],
  rust: ["Rust 1.89.0", "syn 2.0.119"],
  cpp: [
    "C++20",
    "Apple clang version 21.0.0 (clang-2100.1.1.101)",
    "arm64-apple-darwin25.6.0",
  ],
  objc: [
    "Objective-C",
    "Apple clang version 21.0.0 (clang-2100.1.1.101)",
    "arm64-apple-darwin25.6.0",
    "Foundation",
  ],
  swift: [
    "Apple Swift 6.3.3 (swiftlang-6.3.3.1.3 clang-2100.1.1.101)",
    "arm64-apple-macosx26.0",
    "SwiftSyntax 600.0.1",
  ],
  php: [
    "PHP 8.5.9 (cli) (built: Jul 28 2026 13:06:52) (NTS)",
    "ext/tokenizer Zend token stream",
    "strict_types=1",
  ],
  kotlin: ["Kotlin 2.2.20", "JDK 21.0.11", "Kotlin compiler PSI"],
  react: [
    "React 19.2.7",
    "React DOM 19.2.7",
    "TypeScript 5.9.2 Compiler API",
    "Node.js 26.0.0",
  ],
  flutter: [
    "Flutter 3.44.1 revision 924134a44c189315be2148659913dda1671cbe99",
    "Dart 3.12.1",
    "analyzer 10.1.0",
    "_fe_analyzer_shared 95.0.0",
  ],
};

const activePairs = activeLanguageIds.flatMap((source) =>
  activeLanguageIds
    .filter((target) => target !== source)
    .map((target) => [source, target] as const));

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

const v3ResearchCertification = (routeKey: string) => ({
  schema_version: 1,
  route_key: routeKey,
  route_version: "0.1.0",
  status: "research",
  certification_decision: "NOT_CERTIFIED",
  declared_scope: "NO_ROUTE_PROFILE_ADMITTED",
  gate_results: {
    local_execution: "NOT_RUN",
    external_execution: "NOT_RUN",
    independent_verification: "NOT_RUN",
  },
  metrics: {
    build_green_rate: null,
    first_build_pass_rate: null,
    p0_behavior_pass_rate: null,
    source_map_coverage: null,
    manual_hours: null,
    cost_per_verified_workload: null,
  },
  evidence_refs: [],
  issued_at: "2026-08-09T00:00:00+00:00",
  next_review_at: "2026-11-24T00:00:00+00:00",
});

const v3ResearchEvidence = (routeKey: string) => ({
  schema_version: 1,
  route_key: routeKey,
  route_version: "0.1.0",
  route_maturity: "RESEARCH",
  execution_status: "NOT_RUN",
  module_execution_status: "NOT_RUN",
  repository_execution_status: "NOT_RUN",
  independent_verification_status: "NOT_RUN",
  external_certification_status: "NOT_RUN",
  runs: [],
  negative_runs: [],
  metrics: {
    build_green_rate: null,
    first_build_pass_rate: null,
    p0_behavior_pass_rate: null,
    source_map_coverage: null,
    manual_hours: null,
    cost_per_verified_workload: null,
  },
  critical_unknown_semantics: null,
  critical_behavior_regressions: null,
  test_integrity_violations: null,
  notes: [
    "No V3 route-level semantic profile or target profile has been admitted.",
    "Analyzer and emitter bindings are metadata, not route execution evidence.",
    "Local, repository, independent, external, customer, and production evidence remain NOT_RUN.",
  ],
});

const v3ResearchSupportMatrix = (routeKey: string) => ({
  schema_version: 1,
  route_key: routeKey,
  capabilities: [
    ["type-system", "experimental", "deterministic-lowering", "Initial scaffold; evidence required"],
    ["generics", "detected-only", "obligation", "Not yet implemented"],
    ["nullability", "detected-only", "obligation", "Not yet implemented"],
    ["numeric", "detected-only", "obligation", "Not yet implemented"],
    ["time", "detected-only", "obligation", "Not yet implemented"],
    ["exceptions", "detected-only", "obligation", "Not yet implemented"],
    ["async", "detected-only", "obligation", "Not yet implemented"],
    ["concurrency", "blocked", "human-review", "Requires route-specific certification"],
    ["reflection", "blocked", "human-review", "Requires route-specific certification"],
    ["serialization", "detected-only", "contract-mapping", "Not yet implemented"],
    ["interop", "blocked", "retain-runtime-or-sidecar", "Requires explicit boundary plan"],
  ].map(([id, status, strategy, reason]) => ({
    id,
    status,
    strategy,
    reason,
    evidence_refs: [],
  })),
});

async function routeContractFixture(
  evidence: Record<string, unknown>,
  options: {
    certifiedRoute?: boolean;
    descriptorContent?: Buffer;
    linkKind?: "symlink" | "hardlink";
  } = {},
) {
  const root = await mkdtemp(path.join(tmpdir(), "elmos-web-route-evidence-"));
  const routeRoot = path.join(root, "routes", "python-to-typescript");
  const certification = path.join(routeRoot, "certification");
  await writeFile(path.join(root, "pom.xml"), "<project/>\n");
  await writeFixtureEnginePaths(root);
  const evidenceContent = Buffer.from(`${JSON.stringify(evidence)}\n`);
  const descriptorContent = options.descriptorContent ?? evidenceContent;
  const evidencePath = path.join(certification, "repository-evidence.json");
  const routes = activePairs.map(([source, target]) => {
    const route = inventoryRoute(source, target);
    if (route.route_key !== "python-to-typescript") return route;
    return {
      ...route,
      status: options.certifiedRoute ? "certified" as const : "limited" as const,
      local_execution_status: "PASSED_LOCAL" as const,
      repository_execution_status: "PASSED" as const,
      repository_profile: "repository-wide-v1",
      repository_evidence_ref: "certification/repository-evidence.json",
      repository_evidence_sha256: sha256(descriptorContent),
      repository_evidence_bytes: descriptorContent.byteLength,
      independent_verification_status: options.certifiedRoute ? "PASSED" as const : "NOT_RUN" as const,
      external_certification_status: options.certifiedRoute ? "PASSED" as const : "NOT_RUN" as const,
    };
  });
  await writeRoutePacks(root, routes);
  await mkdir(certification, { recursive: true });
  if (options.linkKind) {
    const external = path.join(root, "external-evidence.json");
    await writeFile(external, evidenceContent);
    if (options.linkKind === "symlink") await symlink(external, evidencePath);
    else await link(external, evidencePath);
  } else {
    await writeFile(evidencePath, evidenceContent);
  }
  const inventory = fixtureInventory(routes, activeLanguageIds);
  await writeFile(path.join(root, "routes", "inventory.json"), `${JSON.stringify(inventory)}\n`);
  return {
    root,
    evidencePath,
    evidenceContent,
    inventoryPath: path.join(root, "routes", "inventory.json"),
    routePackPath: path.join(routeRoot, "route.json"),
    certificationRoot: certification,
    certificationPath: path.join(certification, "certification.json"),
  };
}

type FixtureRoute = {
  route_key: string;
  source: TranslationLanguageId;
  target: TranslationLanguageId;
  source_version: string;
  target_version: string;
  status: "research" | "limited" | "certified";
  route_set: string;
  local_execution_reason: string;
  local_execution_status: "PASSED_LOCAL" | "NOT_RUN" | "FAILED";
  module_execution_status: "PASSED_LOCAL" | "NOT_RUN" | "FAILED" | "NOT_APPLICABLE";
  repository_execution_status: "PASSED" | "NOT_RUN" | "FAILED";
  repository_profile: string | null;
  repository_evidence_ref: string | null;
  repository_evidence_sha256: string | null;
  repository_evidence_bytes: number | null;
  independent_verification_status: "PASSED" | "NOT_RUN" | "FAILED";
  external_certification_status: "PASSED" | "NOT_RUN" | "FAILED";
};

function inventoryRoute(
  source: TranslationLanguageId,
  target: TranslationLanguageId,
): FixtureRoute {
  const research = researchOnlyLanguageIds.has(source) || researchOnlyLanguageIds.has(target);
  return {
    route_key: `${source}-to-${target}`,
    source,
    target,
    source_version: inventoryVersions[source],
    target_version: inventoryVersions[target],
    status: research ? "research" as const : "limited" as const,
    route_set: research ? "kotlin-react-flutter-completion-66" : "fixture-active-route-set",
    local_execution_reason: research
      ? "V3_ROUTE_CAMPAIGN_NOT_RUN"
      : "FIXTURE_LOCAL_EXECUTION_PASSED",
    local_execution_status: research ? "NOT_RUN" as const : "PASSED_LOCAL" as const,
    module_execution_status: "NOT_APPLICABLE",
    repository_execution_status: "NOT_RUN",
    repository_profile: null,
    repository_evidence_ref: null,
    repository_evidence_sha256: null,
    repository_evidence_bytes: null,
    independent_verification_status: "NOT_RUN",
    external_certification_status: "NOT_RUN",
  };
}

function fixtureInventory(
  routes: readonly FixtureRoute[],
  exposedLanguages: readonly TranslationLanguageId[],
) {
  const count = (status: string) => routes.filter((route) => route.status === status).length;
  return {
    schema_version: "1.4.0",
    semantic_profile: "typed-pure-function-v1",
    console_exposed_languages: [...exposedLanguages],
    deprecated_languages: ["javascript"],
    pending_analyzer_languages: [],
    pending_repository_languages: [],
    route_count: routes.length,
    research_route_count: count("research"),
    experimental_route_count: count("experimental"),
    limited_route_count: count("limited"),
    blocked_route_count: count("blocked"),
    certified_route_count: count("certified"),
    local_execution_evidence: routes.every((route) => route.local_execution_status === "PASSED_LOCAL")
      ? "PASSED_LOCAL"
      : "NOT_RUN",
    independent_verification_evidence: "NOT_RUN",
    external_certification_evidence: "NOT_RUN",
    languages: Object.fromEntries(translationLanguages.map((language) => [language.id, {
      version: inventoryVersions[language.id],
      exact_versions: exactInventoryVersions[language.id],
      engine_path: language.enginePath,
    }])),
    routes,
  };
}

async function writeFixtureEnginePaths(root: string): Promise<void> {
  const relativePaths = new Set([
    ...translationLanguages.map((language) => language.enginePath),
    targetEmitterPath,
  ]);
  for (const relative of relativePaths) {
    const destination = path.join(root, ...relative.split("/"));
    await mkdir(path.dirname(destination), { recursive: true });
    await writeFile(destination, `fixture for ${relative}\n`);
  }
}

function routePack(route: FixtureRoute) {
  const source = translationLanguages.find((language) => language.id === route.source);
  if (!source) throw new Error(`fixture source language missing: ${route.source}`);
  return {
    schema_version: 1,
    route_key: route.route_key,
    version: route.status === "research" ? "0.1.0" : "1.0.0",
    status: route.status,
    owner: route.status === "research" ? "UNASSIGNED" : "ELMOS Migration Platform",
    review_date: route.status === "research" ? "" : "2026-10-26",
    source: {
      language: route.source,
      versions: exactInventoryVersions[route.source],
      engine_path: source.enginePath,
    },
    target: {
      language: route.target,
      versions: exactInventoryVersions[route.target],
      engine_path: targetEmitterPath,
    },
    profiles: {
      semantic_profile: route.status === "research" ? "" : "typed-pure-function-v1",
      target_profile: route.status === "research" ? "" : `${route.target}-native-compiler`,
    },
    framework_profiles: [],
    paths: {
      support_matrix: "support-matrix.json",
      corpus: "corpus",
      certification: "certification",
    },
    gates: {
      real_target_compiler: true,
      source_map_required: true,
      holdout_required: true,
      representative_repository_required: true,
      critical_unknowns_allowed: 0,
      critical_behavior_regressions_allowed: 0,
    },
  };
}

async function writeRoutePacks(root: string, routes: readonly FixtureRoute[]): Promise<void> {
  await Promise.all(routes.map(async (route) => {
    const routeRoot = path.join(root, "routes", route.route_key);
    const certificationRoot = path.join(routeRoot, "certification");
    await mkdir(certificationRoot, { recursive: true });
    const documents = [
      writeFile(path.join(routeRoot, "route.json"), `${JSON.stringify(routePack(route))}\n`),
      writeFile(
        path.join(certificationRoot, "certification.json"),
        `${JSON.stringify(
          route.status === "research"
            ? v3ResearchCertification(route.route_key)
            : {
              route_key: route.route_key,
              certification_decision: "NOT_CERTIFIED",
            },
          )}\n`,
      ),
    ];
    if (route.status === "research") {
      documents.push(
        writeFile(
          path.join(routeRoot, "support-matrix.json"),
          `${JSON.stringify(v3ResearchSupportMatrix(route.route_key))}\n`,
        ),
        writeFile(
          path.join(certificationRoot, "evidence.json"),
          `${JSON.stringify(v3ResearchEvidence(route.route_key))}\n`,
        ),
      );
    }
    await Promise.all(documents);
  }));
}

async function replaceFileWithLink(
  target: string,
  external: string,
  linkKind: "symlink" | "hardlink",
): Promise<void> {
  const content = await readFile(target);
  await writeFile(external, content);
  await rm(target);
  if (linkKind === "symlink") await symlink(external, target);
  else await link(external, target);
}

async function legacyPartialContractFixture() {
  const root = await mkdtemp(path.join(tmpdir(), "elmos-web-route-partial-"));
  await writeFile(path.join(root, "pom.xml"), "<project/>\n");
  await writeFixtureEnginePaths(root);
  const routes = [inventoryRoute("python", "typescript")];
  await writeRoutePacks(root, routes);
  await writeFile(
    path.join(root, "routes", "inventory.json"),
    `${JSON.stringify(fixtureInventory(routes, legacyConsoleLanguageIds))}\n`,
  );
  return { root };
}

async function matrixContractFixture() {
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
  await writeFixtureEnginePaths(root);
  const routes = activePairs.map(([source, target]) => inventoryRoute(source, target));
  await writeRoutePacks(root, routes);
  await writeFile(
    path.join(root, "routes", "inventory.json"),
    `${JSON.stringify(fixtureInventory(routes, activeLanguageIds))}\n`,
  );
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

  test("旧 6 语言/1 路线 partial inventory 即使字段完整也 fail closed", async () => {
    const fixture = await legacyPartialContractFixture();
    try {
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      expectTranslationContractError(
        () => readTranslationCapability(),
        "TRANSLATION_CONSOLE_LANGUAGE_SET_DRIFT",
      );
    } finally {
      await rm(fixture.root, { recursive: true, force: true });
    }
  });

  test("有效证据仅在精确 13 语言/156 路线矩阵中读取", async () => {
    const fixture = await routeContractFixture(repositoryEvidence());
    try {
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      const consoleCapability = readTranslationCapability();
      const executionCapability = readTranslationExecutionCapability();
      expect(consoleCapability.languages.map((language) => language.id)).toEqual(activeLanguageIds);
      expect(consoleCapability.routes).toHaveLength(156);
      expect(consoleCapability.routePackageCount).toBe(156);
      expect(executionCapability.languages).toHaveLength(13);
      expect(executionCapability.routes.find((route) => route.id === "python-to-typescript"))
        .toMatchObject({
        repositoryExecutionStatus: "PASSED",
        repositoryProfile: "repository-wide-v1",
        repositoryEvidenceSha256: sha256(fixture.evidenceContent),
        repositoryEvidenceBytes: fixture.evidenceContent.byteLength,
      });
      expect(consoleCapability.certifiedRouteCount).toBe(0);
      expect(consoleCapability.certificationStatus).toBe("NOT_CERTIFIED");
    } finally {
      await rm(fixture.root, { recursive: true, force: true });
    }
  });

  test("单条 route certified 只增加计数，不会认证完整 156 路线产品面", async () => {
    const fixture = await routeContractFixture(repositoryEvidence(), { certifiedRoute: true });
    try {
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      const capability = readTranslationCapability();
      expect(capability.certifiedRouteCount).toBe(1);
      expect(capability.routes.find((route) => route.id === "python-to-typescript")?.status)
        .toBe("CERTIFIED");
      expect(capability.certificationStatus).toBe("NOT_CERTIFIED");
    } finally {
      await rm(fixture.root, { recursive: true, force: true });
    }
  });

  test("Route Pack strict JSON 拒绝重复字段", async () => {
    const fixture = await routeContractFixture(repositoryEvidence());
    try {
      await writeFile(
        fixture.routePackPath,
        '{"schema_version":1,"route_key":"python-to-typescript","route_key":"python-to-typescript"}\n',
      );
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      expectTranslationContractError(
        () => readTranslationCapability(),
        "TRANSLATION_ROUTE_PACK_DUPLICATE_FIELD",
      );
    } finally {
      await rm(fixture.root, { recursive: true, force: true });
    }
  });

  for (const linkKind of ["symlink", "hardlink"] as const) {
    for (const target of ["inventory", "route-pack", "certification-file"] as const) {
      test(`拒绝${linkKind} ${target}`, async () => {
        const fixture = await routeContractFixture(repositoryEvidence());
        try {
          const targetPath = target === "inventory"
            ? fixture.inventoryPath
            : target === "route-pack"
              ? fixture.routePackPath
              : fixture.certificationPath;
          await replaceFileWithLink(
            targetPath,
            path.join(fixture.root, `external-${target}.json`),
            linkKind,
          );
          process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
          expectTranslationContractError(
            () => readTranslationCapability(),
            target === "inventory"
              ? "TRANSLATION_ROUTE_INVENTORY_UNSAFE"
              : target === "route-pack"
                ? "TRANSLATION_ROUTE_PACK_UNSAFE"
                : "TRANSLATION_ROUTE_CERTIFICATION_FILE_UNSAFE",
          );
        } finally {
          await rm(fixture.root, { recursive: true, force: true });
        }
      });
    }
  }

  test("拒绝 symlink certification 目录", async () => {
    const fixture = await routeContractFixture(repositoryEvidence());
    try {
      const external = path.join(fixture.root, "external-certification");
      await mkdir(external, { recursive: true });
      await writeFile(
        path.join(external, "certification.json"),
        '{"certification_decision":"NOT_CERTIFIED"}\n',
      );
      await rm(fixture.certificationRoot, { recursive: true });
      await symlink(external, fixture.certificationRoot, "dir");
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      expectTranslationContractError(
        () => readTranslationCapability(),
        "TRANSLATION_ROUTE_CERTIFICATION_DIRECTORY_UNSAFE",
      );
    } finally {
      await rm(fixture.root, { recursive: true, force: true });
    }
  });

  test("拒绝偏离 canonical contract 的 V3 certification", async () => {
    const fixture = await routeContractFixture(repositoryEvidence());
    const routeKey = "java-to-kotlin";
    const certificationPath = path.join(
      fixture.root,
      "routes",
      routeKey,
      "certification",
      "certification.json",
    );
    const canonical = v3ResearchCertification(routeKey);
    const adversarialDocuments = [
      {
        expectedCode: "TRANSLATION_ROUTE_V3_CERTIFICATION_SHAPE_INVALID",
        document: { ...canonical, kind: "forged-certification" },
      },
      {
        expectedCode: "TRANSLATION_ROUTE_V3_CERTIFICATION_CONTRACT_INVALID",
        document: { ...canonical, route_version: "1.0.0" },
      },
      {
        expectedCode: "TRANSLATION_ROUTE_V3_CERTIFICATION_CONTRACT_INVALID",
        document: { ...canonical, route_key: "kotlin-to-java" },
      },
      {
        expectedCode: "TRANSLATION_ROUTE_V3_CERTIFICATION_CONTRACT_INVALID",
        document: { ...canonical, status: "limited" },
      },
      {
        expectedCode: "TRANSLATION_ROUTE_V3_CERTIFICATION_CONTRACT_INVALID",
        document: { ...canonical, declared_scope: "typed-pure-function-v1" },
      },
      {
        expectedCode: "TRANSLATION_ROUTE_V3_CERTIFICATION_CONTRACT_INVALID",
        document: {
          ...canonical,
          gate_results: { ...canonical.gate_results, local_execution: "PASSED" },
        },
      },
      {
        expectedCode: "TRANSLATION_ROUTE_V3_CERTIFICATION_CONTRACT_INVALID",
        document: {
          ...canonical,
          metrics: { ...canonical.metrics, build_green_rate: 0 },
        },
      },
    ];
    try {
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      for (const scenario of adversarialDocuments) {
        await writeFile(
          certificationPath,
          `${JSON.stringify(scenario.document)}\n`,
        );
        expectTranslationContractError(
          () => readTranslationCapability(),
          scenario.expectedCode,
        );
      }
    } finally {
      await rm(fixture.root, { recursive: true, force: true });
    }
  });

  test("V3 support/evidence 缺失、链接、重复字段与越权声明均 fail closed", async () => {
    const fixture = await routeContractFixture(repositoryEvidence());
    const routeKey = "java-to-kotlin";
    const routeRoot = path.join(fixture.root, "routes", routeKey);
    const supportPath = path.join(routeRoot, "support-matrix.json");
    const evidencePath = path.join(routeRoot, "certification", "evidence.json");
    const canonicalSupport = Buffer.from(`${JSON.stringify(v3ResearchSupportMatrix(routeKey))}\n`);
    const canonicalEvidence = Buffer.from(`${JSON.stringify(v3ResearchEvidence(routeKey))}\n`);
    try {
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      for (const [label, target, canonical, unsafeCode] of [
        ["support", supportPath, canonicalSupport, "TRANSLATION_ROUTE_V3_SUPPORT_FILE_UNSAFE"],
        ["evidence", evidencePath, canonicalEvidence, "TRANSLATION_ROUTE_V3_EVIDENCE_FILE_UNSAFE"],
      ] as const) {
        await rm(target);
        expectTranslationContractError(() => readTranslationCapability(), unsafeCode);
        await writeFile(target, canonical);
        for (const linkKind of ["symlink", "hardlink"] as const) {
          const external = path.join(fixture.root, `external-v3-${label}-${linkKind}.json`);
          await replaceFileWithLink(target, external, linkKind);
          expectTranslationContractError(() => readTranslationCapability(), unsafeCode);
          await rm(target);
          await writeFile(target, canonical);
          await rm(external);
        }
      }

      await writeFile(
        supportPath,
        `{"schema_version":1,"route_key":"${routeKey}","route_key":"${routeKey}","capabilities":[]}\n`,
      );
      expectTranslationContractError(
        () => readTranslationCapability(),
        "TRANSLATION_ROUTE_V3_SUPPORT_DUPLICATE_FIELD",
      );
      await writeFile(supportPath, canonicalSupport);
      await writeFile(
        evidencePath,
        `{"schema_version":1,"route_key":"${routeKey}","route_key":"${routeKey}"}\n`,
      );
      expectTranslationContractError(
        () => readTranslationCapability(),
        "TRANSLATION_ROUTE_V3_EVIDENCE_DUPLICATE_FIELD",
      );
      await writeFile(evidencePath, canonicalEvidence);

      const support = v3ResearchSupportMatrix(routeKey);
      const supportScenarios = [
        { ...support, forged: true },
        { ...support, route_key: "kotlin-to-java" },
        {
          ...support,
          capabilities: support.capabilities.map((entry, index) =>
            index === 0 ? { ...entry, status: "supported" } : entry),
        },
        {
          ...support,
          capabilities: support.capabilities.map((entry, index) =>
            index === 0 ? { ...entry, evidence_refs: ["certification/forged.json"] } : entry),
        },
      ];
      for (const document of supportScenarios) {
        await writeFile(supportPath, `${JSON.stringify(document)}\n`);
        expectTranslationContractError(() => readTranslationCapability());
      }
      await writeFile(supportPath, canonicalSupport);

      const evidence = v3ResearchEvidence(routeKey);
      const evidenceScenarios = [
        { ...evidence, forged: true },
        { ...evidence, route_key: "kotlin-to-java" },
        { ...evidence, execution_status: "PASSED_LOCAL" },
        { ...evidence, runs: [{ status: "PASSED" }] },
        { ...evidence, metrics: { ...evidence.metrics, build_green_rate: 1 } },
        { ...evidence, critical_unknown_semantics: 0 },
      ];
      for (const document of evidenceScenarios) {
        await writeFile(evidencePath, `${JSON.stringify(document)}\n`);
        expectTranslationContractError(() => readTranslationCapability());
      }
    } finally {
      await rm(fixture.root, { recursive: true, force: true });
    }
  });

  test("V3 inventory 必须保留 route_set/reason/module 精确 NOT_RUN 来源", async () => {
    const fixture = await routeContractFixture(repositoryEvidence());
    const inventory = JSON.parse(await readFile(fixture.inventoryPath, "utf-8")) as {
      routes: Array<Record<string, unknown>>;
    };
    const canonical = JSON.stringify(inventory);
    try {
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      for (const [field, value] of [
        ["route_set", "fixture-forged-set"],
        ["local_execution_reason", "LOCAL_EXECUTION_NOT_RUN"],
        ["module_execution_status", "NOT_RUN"],
      ] as const) {
        const scenario = JSON.parse(canonical) as typeof inventory;
        const route = scenario.routes.find((entry) => entry.route_key === "java-to-kotlin");
        if (!route) throw new Error("V3 fixture route missing");
        route[field] = value;
        await writeFile(fixture.inventoryPath, `${JSON.stringify(scenario)}\n`);
        expectTranslationContractError(
          () => readTranslationCapability(),
          "TRANSLATION_ROUTE_RESEARCH_EVIDENCE_OVERCLAIM",
        );
      }
    } finally {
      await rm(fixture.root, { recursive: true, force: true });
    }
  });

  test("Route Pack 拒绝伪造源 engine path", async () => {
    const fixture = await routeContractFixture(repositoryEvidence());
    try {
      const pack = routePack(inventoryRoute("python", "typescript"));
      pack.source.engine_path = "engines/fake/analyzer.py";
      await writeFile(fixture.routePackPath, `${JSON.stringify(pack)}\n`);
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      expectTranslationContractError(
        () => readTranslationCapability(),
        "TRANSLATION_ROUTE_PACK_ENGINE_BINDING_INVALID",
      );
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

  test("真实与 fixture 均精确公开 13 语言/156 路线，research 与整库门禁保持关闭", async () => {
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
      expect(actualCapability.languages.map((language) => language.id)).toEqual(activeLanguageIds);
      expect(actualCapability.routes).toHaveLength(156);
      expect(new Set(actualCapability.routes.map((route) => route.id))).toHaveProperty("size", 156);
      expect(actualCapability.repositoryExecutableRouteCount).toBe(0);
      expect(actualCapability.repositoryExecutionEvidence).toBe("NOT_RUN");
      const actualResearchRoute = actualCapability.routes.find(
        (route) => route.id === "kotlin-to-react",
      );
      expect(actualResearchRoute).toMatchObject({
        localExecution: "NOT_RUN",
        repositoryExecutionStatus: "NOT_RUN",
        repositoryProfile: null,
        repositoryEvidenceRef: null,
        skill: "b29-route-certification-gate",
        status: "RESEARCH",
      });
      expect(actualResearchRoute?.blockers).toContain(
        "路线仍为 research：语义 Profile 与目标 Profile 均未准入",
      );
      expect(actualResearchRoute?.blockers.join("\n")).not.toContain("typed-pure");
      await expectRepositoryAdmissionRejected(
        actualFixture,
        "kotlin",
        "react",
        "TRANSLATION_ROUTE_NOT_LOCALLY_EXECUTABLE",
      );
    } finally {
      await rm(actualContainer, { recursive: true, force: true });
    }

    const fixture = await matrixContractFixture();
    try {
      process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
      const capability = readTranslationCapability();
      expect(capability.languages.map((language) => language.id)).toEqual(activeLanguageIds);
      expect(capability.routes).toHaveLength(156);
      expect(new Set(capability.routes.map((route) => route.id))).toHaveProperty("size", 156);
      expect(capability.routes.filter((route) => route.status === "RESEARCH")).toHaveLength(66);
      expect(capability.routes.filter((route) => route.status === "EXPERIMENTAL")).toHaveLength(0);
      expect(capability.routes.filter((route) => route.localExecution === "PASSED")).toHaveLength(90);
      expect(capability.routes.every((route) => route.repositoryExecutionStatus === "NOT_RUN"))
        .toBe(true);
      expect(capability.routes.find((route) => route.id === "java-to-python")?.skill)
        .toBe("b29-certify-java-to-python");
      expect(capability.routes.find((route) => route.id === "kotlin-to-react")?.skill)
        .toBe("b29-route-certification-gate");
      expect(capability.repositoryExecutableRouteCount).toBe(0);
      expect(capability.repositoryExecutionEvidence).toBe("NOT_RUN");
      expect(capability.certificationStatus).toBe("NOT_CERTIFIED");
      await expectRepositoryAdmissionRejected(fixture, "objc", "go");
    } finally {
      await rm(fixture.container, { recursive: true, force: true });
    }
  });
});

function activeRepositoryPlan() {
  const languageCounts = Object.fromEntries(
    [...activeLanguageIds, "javascript"].map((language) => [language, 0]),
  );
  languageCounts.python = 1;
  languageCounts.javascript = 1;
  return {
    schema_version: "1.0.0",
    kind: "elmos.repository-route-plan",
    status: "PLANNED",
    repository_ref: "local:plan-fixture",
    snapshot_sha256: "1".repeat(64),
    snapshot_consistency: "STABLE_READ_ONLY_SCAN",
    route_id: "python-to-typescript",
    source_language: "python",
    target_language: "typescript",
    language_lifecycle: "ACTIVE",
    file_count: 2,
    source_file_count: 1,
    source_bytes: 42,
    repository_scale: "small",
    repository_limits: {
      maximum_source_files: 5_000,
      maximum_source_bytes: 64 * 1024 * 1024,
      maximum_bytes_per_file: 2 * 1024 * 1024,
    },
    language_counts: languageCounts,
    javascript_esm_descriptors: [],
    deprecated_excluded_files: [{
      path: "legacy.js",
      language: "javascript",
      sha256: "2".repeat(64),
      bytes: 22,
      status: "EXCLUDED_FROM_ACTIVE_ROUTE",
      reason: "DEPRECATED_LANGUAGE_REQUIRES_EXPLICIT_HISTORICAL_REPLAY",
    }],
    react_project_descriptor: null,
    ignored_symlink_count: 0,
    work_units: [{
      id: "WU-00001",
      route_id: "python-to-typescript",
      source_path: "main.py",
      source_sha256: "3".repeat(64),
      source_bytes: 20,
      status: "DISCOVERY_REQUIRED",
      execution_status: "NOT_RUN",
      required_inputs: ["behavior_cases_json_per_discovered_function"],
      declared_profile: "typed-pure-function-v1",
      unsupported_until_discovered: ["framework"],
    }],
    execution_status: "NOT_RUN",
    external_verification_status: "NOT_RUN",
    certification_status: "NOT_CERTIFIED",
    limitations: ["Deprecated JavaScript is inventoried but excluded from active work units."],
  };
}

test("Repository plan 保留 ACTIVE 生命周期、13+1 语言计数与 JavaScript 排除证据", async () => {
  const fixture = await routeContractFixture(repositoryEvidence());
  const originalRoot = process.env.ELMOS_REPOSITORY_ROOT;
  try {
    process.env.ELMOS_REPOSITORY_ROOT = fixture.root;
    const context = {
      repositoryRef: "local:plan-fixture",
      routeId: "python-to-typescript",
      sourceLanguage: "python" as const,
      targetLanguage: "typescript" as const,
    };
    const accepted = validateRepositoryPlan(activeRepositoryPlan(), context);
    expect(accepted.language_lifecycle).toBe("ACTIVE");
    expect(Object.keys(accepted.language_counts).sort()).toEqual(
      [...activeLanguageIds, "javascript"].sort(),
    );
    expect(accepted.language_counts.javascript).toBe(1);
    expect(accepted.deprecated_excluded_files).toEqual([
      expect.objectContaining({
        path: "legacy.js",
        language: "javascript",
        status: "EXCLUDED_FROM_ACTIVE_ROUTE",
      }),
    ]);

    const lifecycleTamper = activeRepositoryPlan();
    lifecycleTamper.language_lifecycle = "DEPRECATED_REPLAY";
    expectRepositoryPlanError(
      () => validateRepositoryPlan(lifecycleTamper, context),
      "PLAN_LANGUAGE_LIFECYCLE_INVALID",
    );

    const missingHistoricalKey = activeRepositoryPlan();
    Reflect.deleteProperty(missingHistoricalKey.language_counts, "javascript");
    expectRepositoryPlanError(
      () => validateRepositoryPlan(missingHistoricalKey, context),
      "PLAN_LANGUAGE_COUNT_KEY_SET_INVALID",
    );

    const extraLanguageKey = activeRepositoryPlan();
    Object.assign(extraLanguageKey.language_counts, { dart: 0 });
    expectRepositoryPlanError(
      () => validateRepositoryPlan(extraLanguageKey, context),
      "PLAN_LANGUAGE_COUNT_KEY_SET_INVALID",
    );

    const droppedExclusion = activeRepositoryPlan();
    droppedExclusion.deprecated_excluded_files = [];
    expectRepositoryPlanError(
      () => validateRepositoryPlan(droppedExclusion, context),
      "PLAN_DEPRECATED_EXCLUSIONS_NOT_CLOSED",
    );

    const forgedExclusion = activeRepositoryPlan();
    forgedExclusion.deprecated_excluded_files[0].status = "PASSED";
    expectRepositoryPlanError(
      () => validateRepositoryPlan(forgedExclusion, context),
      "PLAN_DEPRECATED_EXCLUSION_INVALID",
    );

    const scheduledDeprecatedFile = activeRepositoryPlan();
    scheduledDeprecatedFile.work_units[0].source_path = "legacy.js";
    expectRepositoryPlanError(
      () => validateRepositoryPlan(scheduledDeprecatedFile, context),
      "PLAN_DEPRECATED_EXCLUSION_WORK_UNIT_CONFLICT",
    );
  } finally {
    if (originalRoot === undefined) delete process.env.ELMOS_REPOSITORY_ROOT;
    else process.env.ELMOS_REPOSITORY_ROOT = originalRoot;
    await rm(fixture.root, { recursive: true, force: true });
  }
});

async function writePipelineFixture(
  root: string,
  sourceLanguage: TranslationLanguageId = "python",
): Promise<{
  pipeline: string;
  admission: TranslationPipelineAdmission;
  report: Record<string, unknown>;
  manifest: Record<string, unknown>;
}> {
  const pipeline = path.join(root, "pipeline");
  await mkdir(path.join(pipeline, "batch"), { recursive: true });
  await mkdir(path.join(pipeline, "assembled"), { recursive: true });
  const snapshot = "1".repeat(64);
  const targetLanguage: TranslationLanguageId = sourceLanguage === "typescript" ? "java" : "typescript";
  const sourcePath = sourceLanguage === "python" ? "math.py" : `source-${sourceLanguage}.txt`;
  const coverageKey = `${sourceLanguage}:sha256:${"2".repeat(64)}`;
  const graphPayload = {
    schema_version: "1.0.0",
    kind: "elmos.content-addressed-project-graph",
    discovery_profile: "static-project-graph-v1",
    repository_ref: "local:pipeline-fixture",
    repository_id: `elmos:repository:sha256:${"3".repeat(64)}`,
    snapshot_sha256: snapshot,
    snapshot_consistency: "PER_FILE_STABLE_READ_NON_ATOMIC",
    supported_languages: [sourceLanguage, targetLanguage],
    indexers: {},
    repository_complete: true,
    completeness_status: "COMPLETE",
    inventory: {},
    nodes: [{
      id: `elmos:module:sha256:${"8".repeat(64)}`,
      kind: "module",
      name: "source-module",
      path: sourcePath,
      language: sourceLanguage,
      source_location: { path: sourcePath, start_line: 1 },
      attributes: {
        semantic_index_status: "PASSED",
        semantic_indexer: "compiler-module-inventory",
      },
    }, {
      id: `elmos:symbol:sha256:${"4".repeat(64)}`,
      kind: "symbol",
      name: "add",
      path: sourcePath,
      language: sourceLanguage,
      source_location: { path: sourcePath, start_line: 1 },
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
    profile: "compiler-semantic-symbol-coverage-v1",
    source_language: sourceLanguage,
    inventory_status: "PASSED",
    status: "PASSED",
    complete: true,
    subject_count: 1,
    status_counts: { BLOCKED: 0, FAILED: 0, NOT_RUN: 0, PASSED: 1, UNKNOWN: 0 },
    subjects: [{
      coverage_key: coverageKey,
      node_id: graphPayload.nodes[1].id,
      path: sourcePath,
      qualified_name: "add",
      subject_kind: "top-level-function",
      source_location: { path: sourcePath, start_line: 1 },
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
      source_path: sourcePath,
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
    route_id: `${sourceLanguage}-to-${targetLanguage}`,
    source_language: sourceLanguage,
    target_language: targetLanguage,
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
    route_id: `${sourceLanguage}-to-${targetLanguage}`,
    source_language: sourceLanguage,
    target_language: targetLanguage,
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
      toolchain: { language: targetLanguage, version: "fixture exact target toolchain" },
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
      sourceLanguage,
      targetLanguage,
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

test("Runner 对非 Python 活动语言同样绑定 compiler semantic inventory", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "elmos-web-kotlin-coverage-"));
  try {
    const fixture = await writePipelineFixture(root, "kotlin");
    const validated = await validateTranslationPipelineEvidence(fixture.pipeline, fixture.admission);
    expect(validated.semanticCoverage).toMatchObject({
      sourceLanguage: "kotlin",
      inventoryStatus: "PASSED",
      status: "PASSED",
      complete: true,
      subjectCount: 1,
    });
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
    name: "conversion compiler profile",
    mutate: (report: Record<string, unknown>) => {
      report.conversion_coverage = {
        ...(report.conversion_coverage as object),
        profile: "python-ast-symbol-coverage-v1",
      };
    },
  },
  {
    name: "conversion inventory status",
    mutate: (report: Record<string, unknown>) => {
      report.conversion_coverage = {
        ...(report.conversion_coverage as object),
        inventory_status: "NOT_RUN",
      };
    },
  },
  {
    name: "conversion subject graph binding",
    mutate: (report: Record<string, unknown>) => {
      const coverage = report.conversion_coverage as Record<string, unknown>;
      const subjects = coverage.subjects as Array<Record<string, unknown>>;
      report.conversion_coverage = {
        ...coverage,
        subjects: [{ ...subjects[0], node_id: `elmos:symbol:sha256:${"9".repeat(64)}` }],
      };
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

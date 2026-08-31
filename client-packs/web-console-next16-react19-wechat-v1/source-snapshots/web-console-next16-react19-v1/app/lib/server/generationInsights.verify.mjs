import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";

// translationRunner has production dependencies that use extensionless local
// TypeScript imports and parameter properties. Keep this verification script
// dependency-free by using the checked-in TypeScript compiler as a test-only
// ESM transform; the application build still goes through normal Next/tsc.
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (
      (specifier.startsWith("./") || specifier.startsWith("../"))
      && context.parentURL
      && !/\.[cm]?[jt]sx?$/.test(specifier)
      && !specifier.endsWith(".json")
    ) {
      const base = fileURLToPath(new URL(specifier, context.parentURL));
      for (const suffix of [".ts", ".tsx", "/index.ts"]) {
        if (existsSync(`${base}${suffix}`)) {
          return { url: pathToFileURL(`${base}${suffix}`).href, shortCircuit: true };
        }
      }
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.endsWith(".ts") || url.endsWith(".tsx")) {
      const source = readFileSync(fileURLToPath(url), "utf-8");
      const transformed = ts.transpileModule(source, {
        compilerOptions: {
          target: ts.ScriptTarget.ES2022,
          module: ts.ModuleKind.ESNext,
          jsx: ts.JsxEmit.ReactJSX,
          verbatimModuleSyntax: true,
        },
        fileName: fileURLToPath(url),
      });
      return { format: "module", source: transformed.outputText, shortCircuit: true };
    }
    if (url.endsWith(".json")) {
      const source = readFileSync(fileURLToPath(url), "utf-8");
      JSON.parse(source);
      return { format: "module", source: `export default ${source}`, shortCircuit: true };
    }
    return nextLoad(url, context);
  },
});

const {
  GenerationInsightsValidationError,
  validateGenerationInsights,
  validateVerifiedInsightProjection,
} = await import("./generationInsights.ts");
const { validateTranslationBehaviorCoverageClaims } = await import("./translationRunner.ts");

const statuses = (passed = 0, failed = 0, notRun = 0, unknown = 0) => ({
  PASSED: passed,
  FAILED: failed,
  NOT_RUN: notRun,
  UNKNOWN: unknown,
  NOT_APPLICABLE: 0,
});
const languages = ["java", "python"];
const semanticIds = [
  "requirements",
  "entities",
  "fields",
  "relations",
  "business-rules",
  "permissions",
  "acceptance-criteria",
];

function generatedInsights() {
  const dependencyNodes = [];
  const dependencyEdges = [];
  for (const language of languages) {
    const app = `app:${language}`;
    const runtime = `runtime:${language}:runtime-v1`;
    const framework = `framework:${language}:framework-v1`;
    const buildTool = `build-tool:${language}:tool-v1`;
    dependencyNodes.push(
      { id: app, kind: "application", coordinate: language, version_source: "project-blueprint" },
      { id: runtime, kind: "runtime", coordinate: `${language}@runtime-v1`, version_source: "project-blueprint" },
      {
        id: framework,
        kind: "framework",
        coordinate: `${language}-framework`,
        version_source: "emitter-build-manifest",
      },
      { id: buildTool, kind: "build-tool", coordinate: `${language}-tool`, version_source: "runtime-manifest" },
    );
    dependencyEdges.push(
      { from: app, to: runtime, type: "requires", scope: "runtime", evidence_status: "DECLARED" },
      { from: app, to: framework, type: "uses", scope: "application", evidence_status: "DECLARED" },
      { from: app, to: buildTool, type: "builds-with", scope: "build", evidence_status: "DECLARED" },
    );
  }
  const structureNodes = [
    { id: "approved", label: "Approved request", kind: "baseline", path: "requirements/approved.json", status: "PASSED" },
    { id: "psir", label: "PSIR", kind: "semantic-ir", path: "requirements/psir.json", status: "PASSED" },
    { id: "blueprint", label: "Blueprint", kind: "architecture", path: "requirements/blueprint.json", status: "PASSED" },
    { id: "docs", label: "Docs", kind: "documentation", path: "docs", status: "PASSED" },
    { id: "deploy", label: "Deploy", kind: "deployment", path: "deploy", status: "PASSED" },
    { id: "evidence", label: "Evidence", kind: "evidence", path: ".elmos/verification.json", status: "NOT_RUN" },
    ...languages.map((language) => ({
      id: `target-${language}`,
      label: language,
      kind: "generated-target",
      language,
      path: language,
      status: "PASSED",
    })),
  ];
  const structureEdges = [
    { from: "approved", to: "psir", relation: "normalizes" },
    { from: "psir", to: "blueprint", relation: "plans" },
    { from: "blueprint", to: "docs", relation: "documents" },
    { from: "blueprint", to: "deploy", relation: "configures" },
    ...languages.flatMap((language) => [
      { from: "blueprint", to: `target-${language}`, relation: "generates" },
      { from: `target-${language}`, to: "evidence", relation: "requires-verification" },
    ]),
  ];
  const semanticSubjects = semanticIds.map((id) => ({
    id,
    label: id,
    source_count: 1,
    mapped_count: 1,
    mapping_status: "PASSED",
    semantic_equivalence_status: "NOT_RUN",
    evidence_strength: "HASH_BOUND_TRACEABILITY",
  }));
  return {
    schema_version: "1.0.0",
    kind: "elmos.project-generation-insights",
    stage: "GENERATED",
    project: {
      id: "project-insights-test",
      name: "insights-test",
      request_sha256: "a".repeat(64),
      approved_payload_sha256: "b".repeat(64),
    },
    claim_ceiling: "LOCAL_ENGINEERING_EVIDENCE",
    project_structure: {
      schema_version: "1.0.0",
      graph_kind: "elmos.project-structure",
      project: {
        id: "project-insights-test",
        name: "insights-test",
        repository_mode: "polyglot-monorepo",
        approved_payload_sha256: "b".repeat(64),
      },
      nodes: [
        { id: "repository", kind: "repository", path: ".", label: "repository", ownership: "managed", file_count: 20, status: "REPRESENTED" },
        ...languages.map((language) => ({
          id: `app:${language}`,
          kind: "application",
          path: language,
          label: language,
          ownership: "managed",
          file_count: 10,
          status: "REPRESENTED",
          language,
          framework: `${language}-framework`,
          runtime: "runtime-v1",
        })),
      ],
      edges: languages.map((language) => ({ from: "repository", to: `app:${language}`, type: "contains" })),
      coverage: {
        scope: "managed-generated-artifacts",
        managed_file_count: 20,
        classified_file_count: 20,
        declared_application_count: languages.length,
        represented_application_count: languages.length,
        unclassified_paths: [],
        status: "PASSED",
      },
    },
    declared_dependencies: {
      schema_version: "1.0.0",
      graph_kind: "elmos.declared-dependency-graph",
      project_id: "project-insights-test",
      nodes: dependencyNodes,
      edges: dependencyEdges,
      resolution: { status: "NOT_RUN", resolved_graph_refs: [] },
      complete: false,
      issues: ["NATIVE_TRANSITIVE_RESOLUTION_NOT_RUN"],
    },
    structure: {
      graph_kind: "project-synthesis-insight-graph",
      nodes: structureNodes,
      edges: structureEdges,
      node_count: structureNodes.length,
      edge_count: structureEdges.length,
      target_count: languages.length,
    },
    semantic: {
      relation: "APPROVED_REQUIREMENTS_TO_GENERATED_TARGETS",
      mapping_status: "PASSED",
      equivalence_status: "NOT_RUN",
      subjects: semanticSubjects,
      source_subject_count: semanticSubjects.length,
      mapped_subject_count: semanticSubjects.length,
      limitations: ["Traceability is not semantic equivalence.", "Direct source-target execution is not run."],
    },
    behavior: {
      profile: "native-build-test-startup-v1",
      status: "NOT_RUN",
      targets: languages.map((language) => ({
        language,
        status: "NOT_RUN",
        exact_toolchain_status: "NOT_RUN",
        build_analysis: { total: 0, status_counts: statuses() },
        startup_status: "NOT_RUN",
      })),
      cross_target_matrix: languages.flatMap((source) => languages.map((target) => ({
        source,
        target,
        semantic_status: source === target ? "NOT_APPLICABLE" : "NOT_RUN",
        behavior_status: source === target ? "NOT_APPLICABLE" : "NOT_RUN",
        reason: source === target ? "SAME_TARGET" : "DIRECT_PAIRWISE_SOURCE_TARGET_COMPARISON_NOT_EXECUTED",
      }))),
      limitations: ["Native target checks are not pairwise equivalence.", "External verification remains NOT_RUN."],
    },
    coverage: [
      { id: "project-structure", label: "Project structure", status: "PASSED", passed: 1, total: 1 },
      { id: "requirements-traceability", label: "Traceability", status: "PASSED", passed: 7, total: 7 },
      { id: "native-target-verification", label: "Native target verification", status: "NOT_RUN", passed: 0, total: 2 },
      { id: "direct-semantic-equivalence", label: "Direct semantic equivalence", status: "NOT_RUN", passed: 0, total: 2 },
      { id: "direct-behavior-equivalence", label: "Direct behavior equivalence", status: "NOT_RUN", passed: 0, total: 2 },
    ],
    external_verification_status: "NOT_RUN",
    certification_status: "NOT_CERTIFIED",
  };
}

function verifiedInsights() {
  const verified = structuredClone(generatedInsights());
  verified.stage = "VERIFIED";
  verified.verification_status = "PASSED";
  verified.behavior.status = "PASSED";
  for (const target of verified.behavior.targets) {
    target.status = "PASSED";
    target.exact_toolchain_status = "PASSED";
    target.startup_status = "PASSED";
    target.build_analysis = { total: 1, status_counts: statuses(1) };
  }
  const native = verified.coverage.find((dimension) => dimension.id === "native-target-verification");
  native.status = "PASSED";
  native.passed = languages.length;
  return verified;
}

let checks = 0;

function generationRejected(value, code, projection = false) {
  assert.throws(
    () => projection
      ? validateVerifiedInsightProjection(generatedInsights(), value)
      : validateGenerationInsights(value),
    (error) => {
      assert.ok(error instanceof GenerationInsightsValidationError);
      assert.equal(error.message, code);
      return true;
    },
  );
  checks += 1;
}

const generated = generatedInsights();
assert.equal(validateGenerationInsights(generated, "GENERATED").stage, "GENERATED");
assert.equal(
  generated.declared_dependencies.nodes.find((node) => node.kind === "framework").version_source,
  "emitter-build-manifest",
);
checks += 2;

const verified = verifiedInsights();
assert.equal(validateGenerationInsights(verified, "VERIFIED").verification_status, "PASSED");
assert.equal(validateVerifiedInsightProjection(generated, verified).stage, "VERIFIED");
checks += 2;

{
  const value = generatedInsights();
  value.project_structure.nodes.push(structuredClone(value.project_structure.nodes[1]));
  generationRejected(value, "GENERATION_PROJECT_STRUCTURE_NODE_INVALID");
}
{
  const value = generatedInsights();
  value.project_structure.edges[0].to = "missing-node";
  generationRejected(value, "GENERATION_PROJECT_STRUCTURE_EDGE_INVALID");
}
{
  const value = generatedInsights();
  value.project_structure.edges[1] = structuredClone(value.project_structure.edges[0]);
  generationRejected(value, "GENERATION_PROJECT_STRUCTURE_EDGE_DUPLICATED");
}
{
  const value = generatedInsights();
  value.project_structure.coverage.managed_file_count += 1;
  value.project_structure.coverage.classified_file_count += 1;
  generationRejected(value, "GENERATION_PROJECT_STRUCTURE_COVERAGE_INVALID");
}
{
  const value = generatedInsights();
  value.declared_dependencies.edges[1] = structuredClone(value.declared_dependencies.edges[0]);
  generationRejected(value, "GENERATION_DECLARED_DEPENDENCY_EDGE_DUPLICATED");
}
{
  const value = generatedInsights();
  value.behavior.targets[0].build_analysis.status_counts.PASSED = 1;
  generationRejected(value, "GENERATION_BEHAVIOR_BUILD_STATUS_COUNTS_INVALID");
}
{
  const value = generatedInsights();
  const pair = value.behavior.cross_target_matrix.find((cell) => cell.source !== cell.target);
  pair.semantic_status = "PASSED";
  generationRejected(value, "GENERATION_BEHAVIOR_PAIR_CLAIM_INVALID");
}
{
  const value = verifiedInsights();
  value.project.name = "drifted-name";
  value.project_structure.project.name = "drifted-name";
  generationRejected(value, "GENERATION_VERIFIED_INSIGHTS_PROJECTION_INVALID", true);
}
{
  const value = verifiedInsights();
  value.coverage.find((dimension) => dimension.id === "native-target-verification").label = "drifted-label";
  generationRejected(value, "GENERATION_VERIFIED_NATIVE_COVERAGE_IDENTITY_DRIFTED", true);
}
{
  const value = verifiedInsights();
  value.behavior.targets.reverse();
  generationRejected(value, "GENERATION_VERIFIED_BEHAVIOR_TARGET_IDENTITY_DRIFTED", true);
}

function behaviorCoverage() {
  return {
    profile: "typed-pure-function-v1",
    status: "NOT_RUN",
    complete: false,
    work_unit_denominator: 2,
    work_unit_count: 2,
    accounted_work_unit_count: 2,
    attempted_work_unit_count: 1,
    unresolved_work_unit_count: 1,
    pass_rate: 0.5,
    behavior_case_count: 2,
    behavior_case_count_scope: "PASSED_WORK_UNITS_ONLY",
    status_counts: { FAILED: 0, NOT_RUN: 1, PASSED: 1, UNKNOWN: 0 },
    units: [
      {
        id: "WU-00001",
        source_path: "math.py",
        function_name: "add",
        batch_status: "PASSED",
        status: "PASSED",
        behavior_case_count: 2,
        evidence_path: "units/WU-00001/route-evidence.json",
        evidence_sha256: `sha256:${"c".repeat(64)}`,
      },
      {
        id: "WU-00002",
        source_path: "math.py",
        function_name: "subtract",
        batch_status: "SKIPPED_NO_CASES",
        status: "NOT_RUN",
        behavior_case_count: 0,
        evidence_path: null,
        evidence_sha256: null,
      },
    ],
    evidence_strength: "LOCAL_SOURCE_TARGET_RUNTIME_COMPARISON",
    independent_verification_status: "NOT_RUN",
    external_verification_status: "NOT_RUN",
  };
}

const closure = {
  workUnitCount: 2,
  readyCount: 2,
  includedUnitCount: 1,
  counts: { PASSED: 1, FAILED: 0, SKIPPED_NOT_READY: 0, SKIPPED_NO_CASES: 1 },
  excludedUnits: new Map([["WU-00002", "SKIPPED_NO_CASES"]]),
};
const report = { behavior_coverage: behaviorCoverage() };
const manifest = { behavior_coverage: structuredClone(report.behavior_coverage) };
assert.equal(
  validateTranslationBehaviorCoverageClaims(report, manifest, "PARTIAL", closure).status,
  "NOT_RUN",
);
checks += 1;

{
  const mismatched = structuredClone(manifest);
  mismatched.behavior_coverage.pass_rate = 1;
  assert.throws(
    () => validateTranslationBehaviorCoverageClaims(report, mismatched, "PARTIAL", closure),
    (error) => {
      assert.equal(error.code, "TRANSLATION_ARTIFACT_MANIFEST_REPORT_MISMATCH");
      return true;
    },
  );
  checks += 1;
}

function translationRejected(mutator, code) {
  const rejectedReport = structuredClone(report);
  const rejectedManifest = structuredClone(manifest);
  mutator(rejectedReport.behavior_coverage);
  rejectedManifest.behavior_coverage = structuredClone(rejectedReport.behavior_coverage);
  assert.throws(
    () => validateTranslationBehaviorCoverageClaims(
      rejectedReport,
      rejectedManifest,
      "PARTIAL",
      closure,
    ),
    (error) => {
      assert.equal(error.code, code);
      return true;
    },
  );
  checks += 1;
}

translationRejected(
  (coverage) => {
    coverage.units[1].id = coverage.units[0].id;
  },
  "TRANSLATION_PIPELINE_BEHAVIOR_COVERAGE_UNIT_INVALID",
);
translationRejected(
  (coverage) => {
    coverage.units[1].id = "WU-00999";
  },
  "TRANSLATION_PIPELINE_BEHAVIOR_COVERAGE_EXCLUDED_UNIT_MISMATCH",
);
translationRejected(
  (coverage) => {
    coverage.status_counts.NOT_RUN = 0;
  },
  "TRANSLATION_PIPELINE_BEHAVIOR_COVERAGE_CONTRADICTORY",
);

console.log(`generation/translation insight validation: ${checks} checks passed`);

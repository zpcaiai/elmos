import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { copyFile, mkdtemp, open, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { Sha256Accumulator } from "../app/lib/sha256Accumulator.ts";
import {
  BUNDLE_MANIFEST_PATH,
  functionalConversionReportId,
  translationConversionBundleFiles,
  validateTranslationConversion,
  validateTranslationConversionBundleArchive,
  validateTranslationConversionBundleManifest,
  validateTranslationConversionDocument,
  validateTranslationConversionIndex,
  validateTranslationConversionMarkdown,
  validateTranslationConversionShardDocuments,
} from "../app/lib/server/translationConversionReport.ts";

const digest = (value) => createHash("sha256").update(value, "utf8").digest("hex");
const snapshot = digest("snapshot");
const routeId = "python-to-typescript";
const definitionId = "verified-functional-obligation-success-rate/v1";
const casesManifestSha256 = digest("cases-manifest");

test("incremental browser download hashing matches SHA-256 across arbitrary chunk boundaries", () => {
  const content = Buffer.from("abc😀".repeat(20_001), "utf8");
  const accumulator = new Sha256Accumulator();
  for (let offset = 0; offset < content.length; offset += 7_919) {
    accumulator.update(content.subarray(offset, offset + 7_919));
  }
  assert.equal(accumulator.digestHex(), createHash("sha256").update(content).digest("hex"));
});

function block({ obligationId, direction, language, path, snippet, symbol }) {
  const bytes = Buffer.byteLength(snippet, "utf8");
  return {
    block_id: `${obligationId}:${direction}-001`,
    path,
    language,
    symbol_id: symbol,
    document_bytes: bytes,
    document_sha256: digest(snippet),
    block_sha256: digest(snippet),
    range: {
      start_byte: 0,
      end_byte: bytes,
      start_line: 1,
      start_column: 1,
      end_line: 2,
      end_column: 1,
    },
    snippet,
    truncated: false,
    omission_reason: null,
    extraction_method: language === "python"
      ? "PYTHON_AST_FUNCTION"
      : "NAME_ANCHORED_DOCUMENT_EXCERPT",
  };
}

function fixture() {
  const firstId = "WU-00001:FO-001";
  const secondId = "WU-00001:FO-002";
  const sourceOne = block({
    obligationId: firstId,
    direction: "SOURCE",
    language: "python",
    path: "src/order.py",
    snippet: "def subtotal(value):\n    return value\n",
    symbol: "subtotal",
  });
  const targetOne = block({
    obligationId: firstId,
    direction: "TARGET",
    language: "typescript",
    path: "batch/units/WU-00001/migrated.ts",
    snippet: "export function subtotal(value: number) { return value; }\n",
    symbol: "subtotal",
  });
  const sourceTwo = block({
    obligationId: secondId,
    direction: "SOURCE",
    language: "python",
    path: "src/order.py",
    snippet: "def total(value):\n    return value\n",
    symbol: "total",
  });
  const action = {
    action_id: `${secondId}:ACTION-001`,
    priority: "P0",
    method: "生成显式函数拆分清单并为该函数补齐独立行为用例。",
    automation: "ASSISTED",
    verification_steps: ["校验拆分清单", "重新执行目标编译与行为回放"],
  };
  const document = {
    schema_version: "1.0.0",
    kind: "elmos.project-language-conversion-report",
    report_id: "sha256:pending",
    markdown_renderer_version: "elmos-functional-conversion-markdown/v1",
    markdown_sha256: "b".repeat(64),
    status: "PARTIAL",
    repository: { reference: "local:pure-python", snapshot_sha256: snapshot },
    route: {
      route_id: routeId,
      source_language: "python",
      target_language: "typescript",
      profile: "typed-pure-function-v1",
    },
    metric: {
      definition_id: definitionId,
      measurement_unit: "FUNCTIONAL_OBLIGATION",
      comparison_basis: "DECLARED_BEHAVIOR_ORACLE",
      numerator: 1,
      denominator: 2,
      reported_obligation_count: 2,
      unknown_scope_count: 0,
      unreported_obligation_count: 0,
      exact_fraction: "1/2",
      success_rate_basis_points: 5_000,
      display_percent: "50.00%",
      project_success_rate_lower_bound_basis_points: 5_000,
      project_success_rate_upper_bound_basis_points: 5_000,
      project_success_rate_display: "50.00%",
      measurement_status: "MEASURED",
      denominator_complete: true,
      formula: "VERIFIED functional obligations / compiler-completely inventoried functional obligations",
    },
    status_counts: { VERIFIED: 1, UNSUPPORTED: 1 },
    code_artifact_ready: true,
    functions: [
      {
        obligation_id: firstId,
        work_unit_id: "WU-00001",
        kind: "CALLABLE",
        functional_description: { text: "Function subtotal in src/order.py", source: "AST_SIGNATURE_DERIVED" },
        status: "VERIFIED",
        source_blocks: [sourceOne],
        target_blocks: [targetOne],
        mapping: {
          mapping_id: `${firstId}:MAP-001`,
          kind: "SYNTHESIZED",
          freshness: "FRESH",
          confidence: 0.7,
          source_block_ids: [sourceOne.block_id],
          target_block_ids: [targetOne.block_id],
          provenance_refs: ["repository-route-plan.json"],
        },
        evidence_refs: ["repository-route-plan.json", "batch/batch-report.json"],
        failure: null,
        improvement_actions: [],
      },
      {
        obligation_id: secondId,
        work_unit_id: "WU-00001",
        kind: "CALLABLE",
        functional_description: { text: "Function total in src/order.py", source: "AST_SIGNATURE_DERIVED" },
        status: "UNSUPPORTED",
        source_blocks: [sourceTwo],
        target_blocks: [],
        mapping: {
          mapping_id: `${secondId}:MAP-001`,
          kind: "UNMAPPED",
          freshness: "FRESH",
          confidence: 0,
          source_block_ids: [sourceTwo.block_id],
          target_block_ids: [],
          provenance_refs: ["repository-route-plan.json"],
        },
        evidence_refs: ["repository-route-plan.json", "batch/batch-report.json"],
        failure: {
          stage: "ANALYSIS",
          reason_code: "MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION",
          description: "Multiple eligible functions require explicit partition.",
          target_absence_reason: "NOT_GENERATED",
        },
        improvement_actions: [action],
      },
    ],
    exclusions: [],
    blockers: ["MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION"],
    build_verification: { status: "PASSED", reason: null },
    evidence_boundary: {
      local_target_build: "PASSED",
      target_behavior_oracle: "PASSED_PER_VERIFIED_FUNCTION",
      source_target_declared_case_equivalence: "PASSED_PER_VERIFIED_FUNCTION",
      source_target_runtime_equivalence: "NOT_RUN",
      independent_verification: "NOT_RUN",
      external_verification: "NOT_RUN",
      cases_manifest_sha256: casesManifestSha256,
    },
    certification_status: "NOT_CERTIFIED",
  };
  document.report_id = functionalConversionReportId(document);
  const rawSummary = {
    report_id: document.report_id,
    definition_id: definitionId,
    measurement_unit: "FUNCTIONAL_OBLIGATION",
    comparison_basis: "DECLARED_BEHAVIOR_ORACLE",
    storage_mode: "SINGLE",
    shard_count: 0,
    total_shard_bytes: 0,
    cases_manifest_sha256: casesManifestSha256,
    numerator: 1,
    denominator: 2,
    reported_obligation_count: 2,
    unknown_scope_count: 0,
    unreported_obligation_count: 0,
    exact_fraction: "1/2",
    success_rate_basis_points: 5_000,
    display_percent: "50.00%",
    project_success_rate_lower_bound_basis_points: 5_000,
    project_success_rate_upper_bound_basis_points: 5_000,
    project_success_rate_display: "50.00%",
    measurement_status: "MEASURED",
    denominator_complete: true,
    verified_count: 1,
    failed_count: 1,
    status_counts: { VERIFIED: 1, UNSUPPORTED: 1 },
    code_artifact_ready: true,
    json_report: { path: "functional-conversion-report.json", bytes: 1_024, sha256: "a".repeat(64) },
    markdown_report: { path: "FUNCTION_CONVERSION_REPORT.md", bytes: 2_048, sha256: "b".repeat(64) },
    failure_summary_count: 1,
    total_failure_count: 1,
    failure_summaries_truncated: false,
    failure_summaries: [{
      obligation_id: secondId,
      work_unit_id: "WU-00001",
      function_description: "Function total in src/order.py",
      source_path: "src/order.py",
      target_path: null,
      status: "UNSUPPORTED",
      failure_code: "MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION",
      failure_reason: "Multiple eligible functions require explicit partition.",
      improvement_actions: [action.method],
    }],
  };
  return { document, rawSummary };
}

function context() {
  return {
    pipelineStatus: "PARTIAL",
    repositoryRef: "local:pure-python",
    snapshotSha256: snapshot,
    routeId,
    sourceLanguage: "python",
    targetLanguage: "typescript",
    profile: "typed-pure-function-v1",
    buildStatus: "PASSED",
    buildReason: null,
    markdownSha256: "b".repeat(64),
    casesManifestSha256,
  };
}

function rebindReportIdentity(document, rawSummary) {
  document.report_id = functionalConversionReportId(document);
  rawSummary.report_id = document.report_id;
}

test("functional denominator may contain multiple obligations from one work unit", () => {
  const { document, rawSummary } = fixture();
  const validated = validateTranslationConversion(rawSummary, 1);
  assert.equal(validated.summary.exactFraction, "1/2");
  assert.equal(validated.summary.failureSummaries[0].obligationId, "WU-00001:FO-002");
  validateTranslationConversionDocument(document, context(), validated.summary);
});

test("a verified functional report can remain downloadable when code artifact packaging is unavailable", () => {
  const { document, rawSummary } = fixture();
  document.code_artifact_ready = false;
  rawSummary.code_artifact_ready = false;
  const validated = validateTranslationConversion(rawSummary, 1);
  validateTranslationConversionDocument(document, context(), validated.summary);
});

test("a generated document-prefix target remains valid without claiming mapping confidence", () => {
  const { document, rawSummary } = fixture();
  document.functions[0].target_blocks[0].extraction_method = "DOCUMENT_PREFIX_EXCERPT";
  document.functions[0].mapping.confidence = 0;
  rebindReportIdentity(document, rawSummary);
  const validated = validateTranslationConversion(rawSummary, 1);
  validateTranslationConversionDocument(document, context(), validated.summary);
});

test("producer supplied percentage cannot round up or drift from integer counts", () => {
  const { rawSummary } = fixture();
  rawSummary.success_rate_basis_points = 5_001;
  assert.throws(
    () => validateTranslationConversion(rawSummary, 1),
    /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
  );
});

test("tampered source code block digest fails the complete report check", () => {
  const { document, rawSummary } = fixture();
  const validated = validateTranslationConversion(rawSummary, 1);
  document.functions[1].source_blocks[0].snippet += "# altered\n";
  rebindReportIdentity(document, rawSummary);
  assert.throws(
    () => validateTranslationConversionDocument(document, context(), validated.summary),
    /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
  );
});

test("polling failure summary must match the content-addressed full report", () => {
  const { document, rawSummary } = fixture();
  const validated = validateTranslationConversion(rawSummary, 1);
  document.functions[1].failure.description = "A different reason.";
  rebindReportIdentity(document, rawSummary);
  assert.throws(
    () => validateTranslationConversionDocument(document, context(), validated.summary),
    /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
  );
});

test("tampered source-target mapping provenance fails closed", () => {
  const { document, rawSummary } = fixture();
  const validated = validateTranslationConversion(rawSummary, 1);
  document.functions[0].mapping.confidence = Number.NaN;
  assert.throws(
    () => validateTranslationConversionDocument(document, context(), validated.summary),
    /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
  );
});

test("full report identity must match the batch-bound pipeline summary", () => {
  const { document, rawSummary } = fixture();
  const validated = validateTranslationConversion(rawSummary, 1);
  document.report_id = `sha256:${"c".repeat(64)}`;
  assert.throws(
    () => validateTranslationConversionDocument(document, context(), validated.summary),
    /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
  );
});

test("an incomplete functional inventory is indeterminate and only exposes a known-scope diagnostic", () => {
  const { rawSummary } = fixture();
  rawSummary.denominator = 1;
  rawSummary.reported_obligation_count = 2;
  rawSummary.unknown_scope_count = 1;
  rawSummary.exact_fraction = "1/1";
  rawSummary.success_rate_basis_points = 10_000;
  rawSummary.display_percent = "100.00%";
  rawSummary.project_success_rate_lower_bound_basis_points = 0;
  rawSummary.project_success_rate_upper_bound_basis_points = 10_000;
  rawSummary.project_success_rate_display = "0.00%–100.00% (INDETERMINATE)";
  rawSummary.denominator_complete = false;
  rawSummary.measurement_status = "INDETERMINATE";
  rawSummary.status_counts = { VERIFIED: 1, UNKNOWN: 1 };
  rawSummary.failure_summaries[0].status = "UNKNOWN";
  const validated = validateTranslationConversion(rawSummary, 1);
  assert.equal(validated.summary.denominatorComplete, false);
  assert.equal(validated.summary.measurementStatus, "INDETERMINATE");
  assert.equal(validated.summary.exactFraction, "1/1");
  assert.equal(validated.summary.displayPercent, "100.00%");
  assert.equal(validated.summary.projectSuccessRateDisplay, "0.00%–100.00% (INDETERMINATE)");
});

test("an incomplete denominator cannot claim a measured project success rate", () => {
  const { rawSummary } = fixture();
  rawSummary.denominator = 1;
  rawSummary.reported_obligation_count = 2;
  rawSummary.unknown_scope_count = 1;
  rawSummary.exact_fraction = "1/1";
  rawSummary.success_rate_basis_points = 10_000;
  rawSummary.display_percent = "100.00%";
  rawSummary.project_success_rate_lower_bound_basis_points = 0;
  rawSummary.project_success_rate_upper_bound_basis_points = 10_000;
  rawSummary.project_success_rate_display = "0.00%–100.00% (INDETERMINATE)";
  rawSummary.denominator_complete = false;
  rawSummary.status_counts = { VERIFIED: 1, UNKNOWN: 1 };
  assert.throws(
    () => validateTranslationConversion(rawSummary, 1),
    /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
  );
});

test("an incomplete project always retains a 100 percent upper bound", () => {
  const { rawSummary } = fixture();
  Object.assign(rawSummary, {
    numerator: 0,
    denominator: 1,
    reported_obligation_count: 2,
    unknown_scope_count: 1,
    exact_fraction: "0/1",
    success_rate_basis_points: 0,
    display_percent: "0.00%",
    project_success_rate_lower_bound_basis_points: 0,
    project_success_rate_upper_bound_basis_points: 10_000,
    project_success_rate_display: "0.00%–100.00% (INDETERMINATE)",
    measurement_status: "INDETERMINATE",
    denominator_complete: false,
    verified_count: 0,
    failed_count: 2,
    status_counts: { FAILED: 1, UNKNOWN: 1 },
    failure_summary_count: 2,
    total_failure_count: 2,
  });
  rawSummary.failure_summaries = [{
    ...rawSummary.failure_summaries[0],
    obligation_id: "WU-00001:FO-001",
    status: "FAILED",
    failure_code: "BEHAVIOR_REPLAY_FAILED",
  }, {
    ...rawSummary.failure_summaries[0],
    status: "UNKNOWN",
  }];
  const validated = validateTranslationConversion(rawSummary, 1);
  assert.equal(validated.summary.projectSuccessRateUpperBoundBasisPoints, 10_000);
  rawSummary.project_success_rate_upper_bound_basis_points = 0;
  rawSummary.project_success_rate_display = "0.00%–0.00% (INDETERMINATE)";
  assert.throws(
    () => validateTranslationConversion(rawSummary, 1),
    /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
  );
});

test("the full report separates callable denominator rows from unknown scope sentinels", () => {
  const { document, rawSummary } = fixture();
  Object.assign(document.metric, {
    denominator: 1,
    reported_obligation_count: 2,
    unknown_scope_count: 1,
    exact_fraction: "1/1",
    success_rate_basis_points: 10_000,
    display_percent: "100.00%",
    project_success_rate_lower_bound_basis_points: 0,
    project_success_rate_upper_bound_basis_points: 10_000,
    project_success_rate_display: "0.00%–100.00% (INDETERMINATE)",
    denominator_complete: false,
    measurement_status: "INDETERMINATE",
    formula: "Reported VERIFIED obligations / reported known callable obligations; project rate remains indeterminate because inventory-unknown or capacity-unreported functional scope remains",
  });
  document.status_counts = { VERIFIED: 1, UNKNOWN: 1 };
  document.functions[1].kind = "UNKNOWN_SOURCE_UNIT";
  document.functions[1].functional_description.source = "UNKNOWN";
  document.functions[1].status = "UNKNOWN";
  Object.assign(rawSummary, {
    denominator: 1,
    reported_obligation_count: 2,
    unknown_scope_count: 1,
    exact_fraction: "1/1",
    success_rate_basis_points: 10_000,
    display_percent: "100.00%",
    project_success_rate_lower_bound_basis_points: 0,
    project_success_rate_upper_bound_basis_points: 10_000,
    project_success_rate_display: "0.00%–100.00% (INDETERMINATE)",
    denominator_complete: false,
    measurement_status: "INDETERMINATE",
    status_counts: { VERIFIED: 1, UNKNOWN: 1 },
  });
  rawSummary.failure_summaries[0].status = "UNKNOWN";
  rebindReportIdentity(document, rawSummary);
  const validated = validateTranslationConversion(rawSummary, 1);
  validateTranslationConversionDocument(document, context(), validated.summary);
});

test("full JSON cannot authorize a different Markdown report", () => {
  const { document, rawSummary } = fixture();
  const validated = validateTranslationConversion(rawSummary, 1);
  document.markdown_sha256 = "d".repeat(64);
  assert.throws(
    () => validateTranslationConversionDocument(document, context(), validated.summary),
    /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
  );
});

test("producer contract maximum description, failure, method, and verification lengths remain valid", () => {
  const { document, rawSummary } = fixture();
  const description = "D".repeat(1_000);
  const reason = "R".repeat(2_000);
  const method = "M".repeat(2_000);
  const verification = "V".repeat(500);
  document.functions[1].functional_description.text = description;
  document.functions[1].failure.description = reason;
  document.functions[1].improvement_actions[0].method = method;
  document.functions[1].improvement_actions[0].verification_steps = [verification];
  rawSummary.failure_summaries[0].function_description = description.slice(0, 600);
  rawSummary.failure_summaries[0].failure_reason = reason.slice(0, 1_200);
  rawSummary.failure_summaries[0].improvement_actions = [method.slice(0, 600)];
  rebindReportIdentity(document, rawSummary);
  const validated = validateTranslationConversion(rawSummary, 1);
  validateTranslationConversionDocument(document, context(), validated.summary);
});

test("failure reason codes accept 120 code points and reject 121", () => {
  const { document, rawSummary } = fixture();
  const maximumCode = "E".repeat(120);
  document.functions[1].failure.reason_code = maximumCode;
  document.blockers = [maximumCode];
  rawSummary.failure_summaries[0].failure_code = maximumCode;
  rebindReportIdentity(document, rawSummary);
  const validated = validateTranslationConversion(rawSummary, 1);
  validateTranslationConversionDocument(document, context(), validated.summary);
  rawSummary.failure_summaries[0].failure_code = "E".repeat(121);
  assert.throws(
    () => validateTranslationConversion(rawSummary, 1),
    /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
  );
});

test("polling summary truncation follows producer Unicode code-point semantics", () => {
  const { document, rawSummary } = fixture();
  const description = `${"D".repeat(599)}😀full-report-tail`;
  const reason = `${"R".repeat(1_199)}😀full-report-tail`;
  const method = `${"M".repeat(599)}😀full-report-tail`;
  document.functions[1].functional_description.text = description;
  document.functions[1].failure.description = reason;
  document.functions[1].improvement_actions[0].method = method;
  rawSummary.failure_summaries[0].function_description = `${"D".repeat(599)}😀`;
  rawSummary.failure_summaries[0].failure_reason = `${"R".repeat(1_199)}😀`;
  rawSummary.failure_summaries[0].improvement_actions = [`${"M".repeat(599)}😀`];
  rebindReportIdentity(document, rawSummary);
  const validated = validateTranslationConversion(rawSummary, 1);
  validateTranslationConversionDocument(document, context(), validated.summary);
});

test("explicitly omitted code snippets retain document identity and pass the report check", () => {
  const { document, rawSummary } = fixture();
  Object.assign(document.functions[1].source_blocks[0], {
    snippet: null,
    truncated: true,
    omission_reason: "GLOBAL_REPORT_SNIPPET_BUDGET_EXCEEDED",
  });
  rebindReportIdentity(document, rawSummary);
  const validated = validateTranslationConversion(rawSummary, 1);
  validateTranslationConversionDocument(document, context(), validated.summary);
});

test("an omitted snippet cannot discard its logical range and digest", () => {
  const { document, rawSummary } = fixture();
  Object.assign(document.functions[1].source_blocks[0], {
    range: null,
    snippet: null,
    truncated: true,
    omission_reason: "GLOBAL_REPORT_SNIPPET_BUDGET_EXCEEDED",
  });
  const validated = validateTranslationConversion(rawSummary, 1);
  assert.throws(
    () => validateTranslationConversionDocument(document, context(), validated.summary),
    /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
  );
});

test("a sharded summary can account for 2500 work units without a capacity sentinel", () => {
  const { rawSummary } = fixture();
  Object.assign(rawSummary, {
    storage_mode: "SHARDED",
    shard_count: 2,
    total_shard_bytes: 4_096,
    numerator: 2_500,
    denominator: 2_500,
    reported_obligation_count: 2_500,
    unknown_scope_count: 0,
    unreported_obligation_count: 0,
    exact_fraction: "2500/2500",
    success_rate_basis_points: 10_000,
    display_percent: "100.00%",
    project_success_rate_lower_bound_basis_points: 10_000,
    project_success_rate_upper_bound_basis_points: 10_000,
    project_success_rate_display: "100.00%",
    denominator_complete: true,
    measurement_status: "MEASURED",
    verified_count: 2_500,
    failed_count: 0,
    status_counts: { VERIFIED: 2_500 },
    failure_summary_count: 0,
    total_failure_count: 0,
    failure_summaries_truncated: false,
    failure_summaries: [],
    report_bundle: {
      path: "FUNCTION_CONVERSION_REPORT_BUNDLE.zip",
      bytes: 8_192,
      sha256: "c".repeat(64),
    },
  });
  const validated = validateTranslationConversion(rawSummary, 2_500);
  assert.equal(validated.summary.reportedObligationCount, 2_500);
  assert.equal(validated.summary.shardCount, 2);
  assert.equal(validated.reportBundle?.path, "FUNCTION_CONVERSION_REPORT_BUNDLE.zip");
  rawSummary.report_bundle.bytes = 256 * 1024 * 1024 + 1;
  assert.throws(
    () => validateTranslationConversion(rawSummary, 2_500),
    /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
  );
});

test("producer contract source and target paths up to 1024 characters remain valid", () => {
  const { document, rawSummary } = fixture();
  const sourcePath = `src/${"s".repeat(1_017)}.py`;
  const targetPath = `out/${"t".repeat(1_017)}.ts`;
  document.functions[1].source_blocks[0].path = sourcePath;
  document.functions[1].target_blocks = [block({
    obligationId: "WU-00001:FO-002",
    direction: "TARGET",
    language: "typescript",
    path: targetPath,
    snippet: "export function total(value: number) { return value; }\n",
    symbol: "total",
  })];
  document.functions[1].mapping.kind = "SYNTHESIZED";
  document.functions[1].mapping.confidence = 0.7;
  document.functions[1].mapping.target_block_ids = ["WU-00001:FO-002:TARGET-001"];
  document.functions[1].failure.target_absence_reason = null;
  rawSummary.failure_summaries[0].source_path = sourcePath;
  rawSummary.failure_summaries[0].target_path = targetPath;
  rebindReportIdentity(document, rawSummary);
  const validated = validateTranslationConversion(rawSummary, 1);
  validateTranslationConversionDocument(document, context(), validated.summary);
});

test("astral Unicode symbol and verification limits count code points", () => {
  const { document, rawSummary } = fixture();
  document.functions[1].source_blocks[0].symbol_id = "𐐀".repeat(200);
  document.functions[1].improvement_actions[0].verification_steps = ["𐐀".repeat(500)];
  rebindReportIdentity(document, rawSummary);
  const validated = validateTranslationConversion(rawSummary, 1);
  validateTranslationConversionDocument(document, context(), validated.summary);
});

test("report paths reject C0 and DEL control characters", () => {
  const { rawSummary } = fixture();
  rawSummary.failure_summaries[0].source_path = "src/order.py\nforged.md";
  assert.throws(
    () => validateTranslationConversion(rawSummary, 1),
    /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
  );
});

test("real producer output validates every shard and rejects missing, reordered, duplicate, Markdown, manifest, and ZIP tampering", async () => {
  const repositoryRoot = path.resolve(import.meta.dirname, "../../..");
  const engineRoot = path.join(repositoryRoot, "engines/polyglot-route-engine");
  const producer = path.join(import.meta.dirname, "produceShardedTranslationReport.py");
  const output = await mkdtemp(path.join(tmpdir(), "elmos-web-sharded-report-"));
  try {
    const produced = spawnSync(
      process.env.ELMOS_UV_PATH || "uv",
      ["run", "--project", engineRoot, "python", producer, output],
      { encoding: "utf8", timeout: 120_000 },
    );
    assert.equal(produced.status, 0, `${produced.stdout}\n${produced.stderr}`);
    const parse = async (relative) => JSON.parse(await readFile(path.join(output, relative), "utf8"));
    const rawSummary = await parse("web-test-summary.json");
    const conversion = validateTranslationConversion(rawSummary, 2_001);
    assert.equal(conversion.summary.storageMode, "SHARDED");
    assert.equal(conversion.summary.shardCount, 2);
    const index = await parse(conversion.jsonReport.path);
    const expected = {
      pipelineStatus: "COMPLETE",
      repositoryRef: "local:web-real-producer-sharded",
      snapshotSha256: digest("web-real-producer-sharded-snapshot"),
      routeId: "python-to-typescript",
      sourceLanguage: "python",
      targetLanguage: "typescript",
      profile: "typed-pure-function-v1",
      buildStatus: "PASSED",
      buildReason: null,
      markdownSha256: conversion.markdownReport.sha256,
      casesManifestSha256: digest("web-real-producer-sharded-cases"),
    };
    const descriptors = validateTranslationConversionIndex(index, expected, conversion.summary);
    validateTranslationConversionMarkdown(
      index,
      await readFile(path.join(output, conversion.markdownReport.path)),
    );
    const shardDocuments = [];
    for (const descriptor of descriptors) {
      const document = await parse(descriptor.json.path);
      shardDocuments.push(document);
      validateTranslationConversionMarkdown(
        document,
        await readFile(path.join(output, descriptor.markdown.path)),
        `分片 ${descriptor.sequence}/${descriptors.length}；本分片 ${descriptor.functionCount} 个功能；总指标来自全部分片`,
      );
    }
    validateTranslationConversionShardDocuments(
      index,
      shardDocuments,
      expected,
      conversion.summary,
      descriptors,
    );
    const bundleFiles = translationConversionBundleFiles(conversion, descriptors);
    const manifestBytes = await readFile(path.join(output, BUNDLE_MANIFEST_PATH));
    const manifestDescriptor = validateTranslationConversionBundleManifest(
      manifestBytes,
      conversion.summary.reportId,
      bundleFiles,
    );
    await validateTranslationConversionBundleArchive(
      path.join(output, conversion.reportBundle.path),
      conversion.reportBundle,
      bundleFiles,
      manifestDescriptor,
    );
    const bundlePath = path.join(output, conversion.reportBundle.path);
    const movedBundlePath = path.join(output, "verified-open-bundle.zip");
    const bundleHandle = await open(bundlePath, "r");
    try {
      await rename(bundlePath, movedBundlePath);
      await writeFile(bundlePath, Buffer.from("pathname replacement"));
      await validateTranslationConversionBundleArchive(
        bundleHandle,
        conversion.reportBundle,
        bundleFiles,
        manifestDescriptor,
      );
    } finally {
      await bundleHandle.close();
      await rm(bundlePath, { force: true });
      await rename(movedBundlePath, bundlePath);
    }

    const reordered = structuredClone(index);
    reordered.shards.reverse();
    assert.throws(
      () => validateTranslationConversionIndex(reordered, expected, conversion.summary),
      /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
    );
    const localCountsTamper = structuredClone(index);
    localCountsTamper.shards[0].status_counts.VERIFIED -= 1;
    assert.throws(
      () => validateTranslationConversionIndex(localCountsTamper, expected, conversion.summary),
      /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
    );
    assert.throws(
      () => validateTranslationConversionShardDocuments(
        index,
        shardDocuments.slice(0, 1),
        expected,
        conversion.summary,
        descriptors,
      ),
      /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
    );
    const idsDigestTamper = structuredClone(descriptors);
    idsDigestTamper[1].obligationIdsSha256 = "f".repeat(64);
    assert.throws(
      () => validateTranslationConversionShardDocuments(
        index,
        shardDocuments,
        expected,
        conversion.summary,
        idsDigestTamper,
      ),
      /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
    );
    const duplicate = structuredClone(shardDocuments);
    duplicate[1].functions[0].obligation_id = duplicate[0].functions[0].obligation_id;
    assert.throws(
      () => validateTranslationConversionShardDocuments(
        index,
        duplicate,
        expected,
        conversion.summary,
        descriptors,
      ),
      /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
    );
    const markdownTamper = Buffer.concat([
      await readFile(path.join(output, descriptors[1].markdown.path)),
      Buffer.from("tampered\n"),
    ]);
    assert.throws(
      () => validateTranslationConversionMarkdown(
        shardDocuments[1],
        markdownTamper,
        `分片 2/2；本分片 1 个功能；总指标来自全部分片`,
      ),
      /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
    );
    const manifest = JSON.parse(manifestBytes.toString("utf8"));
    manifest.files.push({ path: "extra.json", bytes: 1, sha256: "f".repeat(64) });
    const tamperedManifestBytes = Buffer.from(`${JSON.stringify(manifest)}\n`);
    assert.throws(
      () => validateTranslationConversionBundleManifest(
        tamperedManifestBytes,
        conversion.summary.reportId,
        bundleFiles,
      ),
      /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
    );
    const bundleBytes = await readFile(path.join(output, conversion.reportBundle.path));
    bundleBytes[Math.floor(bundleBytes.length / 2)] ^= 0xff;
    const tamperedBundle = path.join(output, "tampered-bundle.zip");
    await writeFile(tamperedBundle, bundleBytes);
    await assert.rejects(
      validateTranslationConversionBundleArchive(
        tamperedBundle,
        conversion.reportBundle,
        bundleFiles,
        manifestDescriptor,
      ),
      /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
    );
    const extraEntryBundle = path.join(output, "extra-entry-bundle.zip");
    await copyFile(path.join(output, conversion.reportBundle.path), extraEntryBundle);
    const appended = spawnSync(
      process.env.ELMOS_UV_PATH || "uv",
      [
        "run", "--project", engineRoot, "python", "-c",
        "import sys,zipfile; z=zipfile.ZipFile(sys.argv[1],'a'); z.writestr('extra.json',b'{}'); z.close()",
        extraEntryBundle,
      ],
      { encoding: "utf8", timeout: 30_000 },
    );
    assert.equal(appended.status, 0, `${appended.stdout}\n${appended.stderr}`);
    const extraEntryBytes = await readFile(extraEntryBundle);
    const extraEntryDetails = await stat(extraEntryBundle);
    await assert.rejects(
      validateTranslationConversionBundleArchive(
        extraEntryBundle,
        {
          ...conversion.reportBundle,
          bytes: extraEntryDetails.size,
          sha256: createHash("sha256").update(extraEntryBytes).digest("hex"),
        },
        bundleFiles,
        manifestDescriptor,
      ),
      /TRANSLATION_FUNCTIONAL_CONVERSION_EVIDENCE_INVALID/,
    );
  } finally {
    await rm(output, { recursive: true, force: true });
  }
});

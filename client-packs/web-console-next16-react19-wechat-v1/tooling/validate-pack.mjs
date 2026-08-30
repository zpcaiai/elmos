#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const pack = path.resolve(here, "..");
const root = path.resolve(pack, "..", "..");
const sourceRoot = path.join(root, "apps", "web-console");
const targetRoot = path.join(pack, "target-project");
const { scanRepository } = require(path.join(root, "engines", "component-dialect-engine", "dist", "scan.js"));
const wxml = require(path.join(root, "engines", "component-dialect-engine", "node_modules", "@wxml", "parser"));

function load(relative) {
  return JSON.parse(fs.readFileSync(path.join(pack, relative), "utf8"));
}

function hash(value) {
  return `sha256:${crypto.createHash("sha256").update(value).digest("hex")}`;
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  return value;
}

function canonicalDigest(value) {
  return hash(JSON.stringify(canonical(value)));
}

function filesRecursively(dir) {
  const result = [];
  const visit = (current) => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (entry.isSymbolicLink()) throw new Error(`TARGET_SYMLINK_FORBIDDEN: ${path.join(current, entry.name)}`);
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) visit(full);
      else if (entry.isFile()) result.push(full);
    }
  };
  visit(dir);
  return result;
}

function directoryDigest(dir) {
  const digest = crypto.createHash("sha256");
  for (const file of filesRecursively(dir)) {
    digest.update(path.relative(dir, file));
    digest.update("\0");
    digest.update(fs.readFileSync(file));
    digest.update("\0");
  }
  return `sha256:${digest.digest("hex")}`;
}

function key(item) {
  return `${item.source_path ?? item.sourcePath}#${item.component_name ?? item.componentName}`;
}

function fail(errors, condition, message) {
  if (!condition) errors.push(message);
}

const errors = [];
const closure = load("transformations/component-migration-closure.json");
const manualBundle = load("manual-ir/components.json");
const snapshot = load("source-snapshots/manifest.json");
const targetManifest = load("target-project-manifest.json");
const coverage = load("target-project/coverage-report.json");
const handoff = load("target-project/handoff.json");
const external = load("certification/external-evidence-status.json");
const certification = load("certification/certification.json");
const scan = scanRepository({ repository: sourceRoot, sourceFramework: "react", includeAllFindings: true });
const units = scan.findings.filter((item) => item.status === "IN_SUBSET" || item.status === "OUT_OF_SUBSET");
const scanByKey = new Map(units.map((item) => [key(item), item]));
const manualByKey = new Map(manualBundle.components.map((item) => [`${item.source.file}#${item.source.componentName}`, item]));

fail(errors, scan.totals.scanErrors === 0, `scan errors: ${scan.totals.scanErrors}`);
fail(errors, closure.totals.discovered === units.length, "closure denominator differs from live scan");
fail(errors, closure.entries.length === units.length, "closure entry inventory is incomplete");
fail(errors, new Set(closure.entries.map(key)).size === units.length, "closure component identities are not unique");
fail(errors, closure.totals.automatic === units.filter((item) => item.status === "IN_SUBSET").length, "automatic count differs from live scan");
fail(errors, closure.totals.hand_ported === units.filter((item) => item.status === "OUT_OF_SUBSET").length, "HAND_PORTED count differs from live scan");
fail(errors, closure.totals.unhandled === 0 && closure.implementation_coverage === 1, "implementation closure is not 100%/0-unhandled");
fail(errors, closure.delivery_status === "COMPLETE_WITH_HANDOFF", "delivery status is not COMPLETE_WITH_HANDOFF");
fail(errors, closure.runtime_evidence === "NOT_RUN" && closure.certification === "NOT_CERTIFIED", "closure exceeds available evidence");
fail(errors, closure.registry_digest === canonicalDigest(closure.entries), "closure registry digest mismatch");
fail(errors, manualBundle.component_count === closure.totals.hand_ported, "manual IR count differs from HAND_PORTED count");
fail(errors, manualBundle.bundle_digest === canonicalDigest(manualBundle.components.map((item) => ({ component: item.source.componentName, digest: item.irDigest }))), "manual IR bundle digest mismatch");

for (const entry of closure.entries) {
  const identity = key(entry);
  const finding = scanByKey.get(identity);
  if (!finding) { errors.push(`closure entry not present in live scan: ${identity}`); continue; }
  const source = path.join(sourceRoot, entry.source_path);
  fail(errors, fs.existsSync(source), `source missing: ${entry.source_path}`);
  if (fs.existsSync(source)) fail(errors, hash(fs.readFileSync(source)) === entry.source_sha256, `source digest stale: ${identity}`);
  const expectedDisposition = finding.status === "IN_SUBSET" ? "AUTOMATIC" : "HAND_PORTED";
  fail(errors, entry.disposition === expectedDisposition, `wrong disposition for ${identity}`);
  if (finding.status === "OUT_OF_SUBSET") {
    fail(errors, entry.blocker?.reason_code === finding.reasonCode, `blocker drift for ${identity}`);
    const ir = manualByKey.get(identity);
    fail(errors, ir !== undefined, `manual IR missing: ${identity}`);
    if (ir) {
      fail(errors, ir.irDigest === entry.manual_ir_digest, `manual IR digest mismatch: ${identity}`);
      fail(errors, ir.source.sha256 === entry.source_sha256, `manual IR source digest mismatch: ${identity}`);
      fail(errors, ir.source.range.start >= 0 && ir.source.range.end > ir.source.range.start, `manual IR exact range missing: ${identity}`);
      fail(errors, ir.targetPlan.disposition === "HAND_PORTED" && ir.targetPlan.runtimeEvidence === "NOT_RUN" && ir.targetPlan.certification === "NOT_CERTIFIED", `manual IR evidence boundary invalid: ${identity}`);
      fail(errors, ir.obligations.length > 0 && ir.targetPlan.adapters.length > 0, `manual IR obligations/adapters missing: ${identity}`);
    }
  }
  const targetDir = path.join(pack, entry.target_path);
  fail(errors, fs.existsSync(targetDir) && fs.statSync(targetDir).isDirectory(), `target component directory missing: ${identity}`);
  if (!fs.existsSync(targetDir)) continue;
  fail(errors, directoryDigest(targetDir) === entry.target_sha256, `target digest mismatch: ${identity}`);
  for (const extension of ["js", "json", "wxml", "wxss"]) {
    fail(errors, fs.existsSync(path.join(targetDir, `index.${extension}`)), `target ${extension} missing: ${identity}`);
  }
  const js = fs.readFileSync(path.join(targetDir, "index.js"), "utf8");
  const template = fs.readFileSync(path.join(targetDir, "index.wxml"), "utf8");
  fail(errors, !js.includes("NOT TRANSLATED") && !template.includes("NOT TRANSLATED") && !js.includes("must be ported by hand"), `placeholder remains: ${identity}`);
  try { new vm.Script(js, { filename: `${identity}.js` }); } catch (error) { errors.push(`JS parse failed ${identity}: ${error.message}`); }
  try { wxml.parse(template); } catch (error) { errors.push(`WXML parse failed ${identity}: ${error.message}`); }
  try { JSON.parse(fs.readFileSync(path.join(targetDir, "index.json"), "utf8")); } catch (error) { errors.push(`component JSON failed ${identity}: ${error.message}`); }
}

const snapshotRecords = snapshot.files.map(({ path: file, sha256 }) => ({ path: file, sha256 }));
fail(errors, snapshot.snapshot_digest === canonicalDigest(snapshotRecords), "source snapshot digest mismatch");
for (const item of snapshot.files) {
  const full = path.join(root, item.path);
  fail(errors, fs.existsSync(full), `snapshot source missing: ${item.path}`);
  if (fs.existsSync(full)) fail(errors, hash(fs.readFileSync(full)) === item.sha256, `snapshot source drift: ${item.path}`);
}

const currentTargetFiles = filesRecursively(targetRoot).map((file) => ({ path: path.relative(pack, file), sha256: hash(fs.readFileSync(file)), bytes: fs.statSync(file).size }));
fail(errors, targetManifest.file_count === currentTargetFiles.length, "target manifest file count mismatch");
fail(errors, JSON.stringify(targetManifest.files) === JSON.stringify(currentTargetFiles), "target file manifest mismatch");
fail(errors, targetManifest.target_digest === canonicalDigest(currentTargetFiles.map(({ path: file, sha256 }) => ({ path: file, sha256 }))), "target project digest mismatch");
fail(errors, coverage.totals.discovered === units.length && coverage.totals.converted === closure.totals.automatic && coverage.totals.blocked === 0 && coverage.totals.manuallyPorted === closure.totals.hand_ported, "coverage report totals mismatch");
fail(errors, coverage.deliveryStatus === "COMPLETE_WITH_HANDOFF" && coverage.unresolvedReferences.length === 0, "coverage report has unresolved delivery items");
fail(errors, handoff.entries.length === closure.totals.hand_ported, "handoff inventory mismatch");
fail(errors, handoff.entries.every((entry) => entry.componentName && entry.targetPathAtPort && entry.sourceHashAtPort && entry.targetHashAtPort), "handoff entries are not component/digest/target bound");
fail(errors, fs.readFileSync(path.join(targetRoot, "runtime", "hand-port-runtime.js"), "utf8").includes("task.abort()"), "target runtime lacks detached cancellation");
fail(errors, fs.readFileSync(path.join(targetRoot, "runtime", "hand-port-runtime.js"), "utf8").includes("epoch !== this.__requestEpoch"), "target runtime lacks stale response fencing");
fail(errors, Object.values(external).filter((value) => value === "NOT_RUN").length >= 10 && external.certification === "NOT_CERTIFIED", "external evidence boundary invalid");
fail(errors, certification.status === "experimental" && certification.certification_decision === "NOT_CERTIFIED" && certification.production_claim_authorized === false, "certification boundary invalid");

if (errors.length) {
  process.stderr.write(`${errors.map((error) => `ERROR: ${error}`).join("\n")}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write(`${JSON.stringify({
    status: "PASSED_LOCAL_STATIC",
    discovered: units.length,
    automatic: closure.totals.automatic,
    hand_ported: closure.totals.hand_ported,
    unhandled: 0,
    scan_errors: 0,
    target_files: currentTargetFiles.length,
    runtime_evidence: "NOT_RUN",
    certification: "NOT_CERTIFIED",
  }, null, 2)}\n`);
}

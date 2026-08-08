#!/usr/bin/env node

/**
 * Materialize one bounded FRT route and attach its Batch 46 runnable smoke pack.
 *
 * The conversion engine remains pure and never executes customer code. This
 * handoff command writes into a create-only staging directory, invokes the
 * repository-owned Batch 46 scaffold/validator, and publishes the directory
 * atomically only when both the target generator and smoke pack validate.
 */

import { spawnSync } from "node:child_process";
import {
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const scriptRoot = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(scriptRoot, "../..");
const engineModule = resolve(repositoryRoot, "engines/frontend-client-engine/dist/src/directional-route.js");
const scaffold = resolve(repositoryRoot, "scripts/batch46/scaffold_smoke_pack.py");
const validate = resolve(repositoryRoot, "scripts/batch46/validate_smoke_pack.py");
const safePath = /^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))[A-Za-z0-9._@\/-]{1,512}$/;
const maxFiles = 64;
const maxRequestBytes = 5 * 1024 * 1024;
const maxFileBytes = 1024 * 1024;
const maxTotalBytes = 4 * 1024 * 1024;

function fail(code, detail = "") {
  if (detail) process.stderr.write(`${code}: ${detail.slice(0, 2_000)}\n`);
  else process.stderr.write(`${code}\n`);
  process.exit(2);
}

function parseArguments() {
  const allowed = new Set(["--request", "--output"]);
  const values = new Map();
  for (let index = 2; index < process.argv.length; index += 2) {
    const name = process.argv[index];
    const value = process.argv[index + 1];
    if (!allowed.has(name) || !value || values.has(name)) fail("FRT_ROUTE_MATERIALIZE_ARGUMENTS_INVALID");
    values.set(name, value);
  }
  if (values.size !== allowed.size) fail("FRT_ROUTE_MATERIALIZE_ARGUMENTS_INCOMPLETE");
  return { request: resolve(values.get("--request")), output: resolve(values.get("--output")) };
}

function validateFiles(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail("FRT_ROUTE_SOURCE_FILES_INVALID");
  const entries = Object.entries(value);
  if (entries.length < 1 || entries.length > maxFiles) fail("FRT_ROUTE_SOURCE_FILES_INVALID");
  let total = 0;
  for (const [name, content] of entries) {
    if (!safePath.test(name) || typeof content !== "string") fail("FRT_ROUTE_SOURCE_FILE_INVALID", name);
    const bytes = Buffer.byteLength(content);
    total += bytes;
    if (bytes > maxFileBytes || total > maxTotalBytes) fail("FRT_ROUTE_SOURCE_BYTES_EXCEEDED");
  }
  return Object.fromEntries(entries);
}

function confined(root, candidate) {
  const item = resolve(candidate);
  const rel = relative(root, item);
  return rel !== "" && !rel.startsWith(`..${sep}`) && rel !== ".." && !isAbsolute(rel);
}

function runPython(python, script, project) {
  const result = spawnSync(python, [script, project, ...(script === scaffold ? ["--write"] : [])], {
    cwd: repositoryRoot,
    encoding: "utf8",
    timeout: 120_000,
    maxBuffer: 4 * 1024 * 1024,
    env: { ...process.env, NO_PROXY: "127.0.0.1,localhost", no_proxy: "127.0.0.1,localhost" },
  });
  if (result.status !== 0) {
    throw new Error(`FRT_ROUTE_SMOKE_PACK_FAILED: ${`${result.stdout ?? ""}${result.stderr ?? ""}`.slice(0, 2_000)}`);
  }
}

const args = parseArguments();
if (!existsSync(args.request)) fail("FRT_ROUTE_REQUEST_INVALID");
const requestStat = lstatSync(args.request);
if (!requestStat.isFile() || requestStat.isSymbolicLink() || requestStat.size > maxRequestBytes) {
  fail("FRT_ROUTE_REQUEST_INVALID");
}
if (existsSync(args.output)) fail("FRT_ROUTE_OUTPUT_MUST_NOT_EXIST");
if (args.output === resolve("/") || args.output === repositoryRoot || args.output === resolve(process.cwd())) {
  fail("FRT_ROUTE_OUTPUT_UNSAFE");
}
if (!existsSync(engineModule)) fail("FRT_ROUTE_ENGINE_NOT_BUILT");

let request;
try {
  request = JSON.parse(readFileSync(args.request, "utf8"));
} catch {
  fail("FRT_ROUTE_REQUEST_INVALID");
}
if (!request || typeof request !== "object" || Array.isArray(request)
    || Object.keys(request).sort().join(",") !== "files,source,target") {
  fail("FRT_ROUTE_REQUEST_FIELDS_INVALID");
}
const files = validateFiles(request.files);
const { convertDirectionalRoute, frtRouteStacks } = await import(engineModule);
if (!frtRouteStacks.includes(request.source) || !frtRouteStacks.includes(request.target)
    || request.source === request.target) {
  fail("FRT_ROUTE_DIRECTION_INVALID");
}
const converted = convertDirectionalRoute(request.source, request.target, files);
if (converted.status !== "GENERATED") {
  fail("FRT_ROUTE_GENERATION_BLOCKED", JSON.stringify(converted.typedGaps));
}

mkdirSync(dirname(args.output), { recursive: true });
const staging = `${args.output}.staging-${process.pid}`;
if (existsSync(staging)) fail("FRT_ROUTE_STAGING_EXISTS");
mkdirSync(staging, { recursive: false, mode: 0o700 });
try {
  for (const [name, content] of Object.entries(converted.generatedFiles)) {
    const destination = resolve(staging, name);
    if (!safePath.test(name) || !confined(staging, destination)) {
      throw new Error(`FRT_ROUTE_GENERATED_PATH_INVALID: ${name}`);
    }
    mkdirSync(dirname(destination), { recursive: true });
    writeFileSync(destination, content, { encoding: "utf8", flag: "wx" });
  }
  const python = process.env.ELMOS_BATCH46_PYTHON ?? "python3";
  runPython(python, scaffold, staging);
  runPython(python, validate, staging);
  writeFileSync(resolve(staging, "materialization-report.json"), `${JSON.stringify({
    schemaVersion: "1.0",
    route: converted.route,
    sourceSnapshotDigest: converted.sourceSnapshotDigest,
    generatedFileCount: Object.keys(converted.generatedFiles).length,
    smokePack: "ATTACHED_VALIDATED",
    smokeExecution: "NOT_RUN",
    runnableGate: "NOT_RUN",
    targetBuild: "NOT_RUN",
    browserOrDeviceJourney: "NOT_RUN",
    certification: "NOT_CERTIFIED",
  }, null, 2)}\n`, { encoding: "utf8", flag: "wx" });
  renameSync(staging, args.output);
} catch (error) {
  rmSync(staging, { recursive: true, force: true });
  fail("FRT_ROUTE_MATERIALIZATION_FAILED", error instanceof Error ? error.message : String(error));
}

process.stdout.write(`${JSON.stringify({
  route: converted.route,
  output: args.output,
  generatedFileCount: Object.keys(converted.generatedFiles).length,
  smokePack: "ATTACHED_VALIDATED",
  runnableGate: "NOT_RUN",
  certification: "NOT_CERTIFIED",
})}\n`);

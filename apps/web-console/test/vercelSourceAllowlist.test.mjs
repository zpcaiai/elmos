import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { lstatSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const repositoryRoot = execFileSync(
  "git",
  ["rev-parse", "--show-toplevel"],
  { encoding: "utf8" },
).trim();
const projectRoot = path.join(repositoryRoot, "apps", "web-console");
const policyPath = path.join(projectRoot, ".vercelignore");
const meaningfulRules = readFileSync(policyPath, "utf8")
  .split(/\r?\n/u)
  .map((line) => line.trim())
  .filter((line) => line.length > 0 && !line.startsWith("#"));

function nulGitFiles(args, cwd = projectRoot) {
  return execFileSync(
    "git",
    [...args, "-z"],
    { cwd, encoding: "buffer", maxBuffer: 64 * 1024 * 1024 },
  )
    .toString("utf8")
    .split("\0")
    .filter(Boolean);
}

function listedProjectFiles() {
  const prefix = "apps/web-console/";
  return nulGitFiles([
    "ls-files",
    "--cached",
    "--others",
    "--exclude-standard",
    "--full-name",
  ], repositoryRoot)
    .filter((relative) => relative.startsWith(prefix))
    .map((relative) => relative.slice(prefix.length));
}

function intendedProjectInput(relative) {
  if ([
    ".vercelignore",
    ".npmrc",
    "next-env.d.ts",
    "next.config.ts",
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "proxy.ts",
    "tsconfig.json",
    "vercel.json",
  ].includes(relative)) {
    return true;
  }
  return ["app/", "lib/", "public/"].some((prefix) => relative.startsWith(prefix));
}

function assertExactRegularFile(relative) {
  const absolute = path.join(repositoryRoot, relative);
  const details = lstatSync(absolute);
  assert.ok(details.isFile(), `not a regular runtime binding: ${relative}`);
  assert.ok(!details.isSymbolicLink(), `symlink runtime binding: ${relative}`);
}

test("project-root Vercel upload policy is default deny and exact", () => {
  assert.deepEqual(meaningfulRules, [
    "/*",
    "!app",
    "!app/**",
    "!lib",
    "!lib/**",
    "!public",
    "!public/**",
    "!.vercelignore",
    "!.npmrc",
    "!next-env.d.ts",
    "!next.config.ts",
    "!package.json",
    "!pnpm-lock.yaml",
    "!pnpm-workspace.yaml",
    "!proxy.ts",
    "!tsconfig.json",
    "!vercel.json",
    "/.next/**",
    "/node_modules/**",
    "/test-results/**",
    "/playwright-report/**",
    "/coverage/**",
    "/.turbo/**",
  ]);
});

test("project-root deployment manifest equals the reviewed allowlist", () => {
  const included = listedProjectFiles().filter(intendedProjectInput).sort();
  for (const relative of [
    "package.json",
    "pnpm-lock.yaml",
    "next.config.ts",
    "vercel.json",
    "public/.gitkeep",
    "app/capabilities/page.tsx",
    "app/api/capabilities/generation/route.ts",
    "app/api/health/route.ts",
    "app/lib/server/fallbacks/inventory.json",
  ]) {
    assert.ok(included.includes(relative), `missing project input ${relative}`);
  }
  assert.ok(included.length > 100, "manifest unexpectedly empty");
  assert.ok(included.length < 1_000, `manifest too large: ${included.length}`);

  let totalBytes = 0;
  for (const relative of included) {
    const absolute = path.join(projectRoot, relative);
    const details = lstatSync(absolute);
    assert.ok(details.isFile(), `non-regular deployment input: ${relative}`);
    assert.ok(!details.isSymbolicLink(), `symlink deployment input: ${relative}`);
    totalBytes += details.size;
  }
  assert.ok(totalBytes < 32 * 1024 * 1024, `manifest exceeds 32 MiB: ${totalBytes}`);
});

test("source files outside the project root retain exact runtime bindings", () => {
  for (const relative of [
    "contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json",
    "routes/inventory.json",
    "pom.xml",
    "engines/database-data-engine/sql-transpiler/src/elmos_sql_transpiler/data/chinadb-commercial-v1.json",
    "engines/dotnet-engine/src/Elmos.Dotnet.SemanticCli/Elmos.Dotnet.SemanticCli.csproj",
    "engines/frontend-client-engine/src/polyglot.ts",
    "engines/polyglot-route-engine/native/dart/analyzer.dart",
    "engines/polyglot-route-engine/native/go/analyzer.go",
    "engines/polyglot-route-engine/native/java/Analyzer.java",
    "engines/polyglot-route-engine/native/kotlin/analyzer.kt",
    "engines/polyglot-route-engine/native/php/analyzer.php",
    "engines/polyglot-route-engine/native/react/analyzer.mjs",
    "engines/polyglot-route-engine/native/rust/src/main.rs",
    "engines/polyglot-route-engine/native/swift/Sources/ElmosSwiftAnalyzer/main.swift",
    "engines/polyglot-route-engine/src/elmos_polyglot_route/clang_analyzer.py",
    "engines/polyglot-route-engine/src/elmos_polyglot_route/emitter.py",
    "engines/polyglot-route-engine/src/elmos_polyglot_route/python_analyzer.py",
  ]) {
    assertExactRegularFile(relative);
  }
});

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
const policyPath = path.join(repositoryRoot, ".vercelignore");
const meaningfulRules = readFileSync(policyPath, "utf8")
  .split(/\r?\n/u)
  .map((line) => line.trim())
  .filter((line) => line.length > 0 && !line.startsWith("#"));

function listedFiles() {
  return execFileSync(
    "git",
    [
      "ls-files",
      "--cached",
      "--others",
      "--exclude-standard",
      "-z",
    ],
    { cwd: repositoryRoot, encoding: "buffer", maxBuffer: 64 * 1024 * 1024 },
  )
    .toString("utf8")
    .split("\0")
    .filter(Boolean);
}

function nulGitFiles(args) {
  return execFileSync(
    "git",
    [...args, "-z"],
    { cwd: repositoryRoot, encoding: "buffer", maxBuffer: 64 * 1024 * 1024 },
  )
    .toString("utf8")
    .split("\0")
    .filter(Boolean);
}

function actualVercelManifest() {
  // Git's exclude engine is the contract used by Vercel for .vercelignore.
  // Compute the complement for tracked files and apply the same policy to
  // untracked, non-gitignored inputs. This makes an added broad negation visible
  // to the exact-set assertion below.
  const tracked = nulGitFiles(["ls-files", "--cached"]);
  const ignoredTracked = new Set(nulGitFiles([
    "ls-files", "--cached", "--ignored", "--exclude-from=.vercelignore",
  ]));
  const includedUntracked = nulGitFiles([
    "ls-files", "--others", "--exclude-standard", "--exclude-from=.vercelignore",
  ]);
  return [...tracked.filter((relative) => !ignoredTracked.has(relative)), ...includedUntracked];
}

function intendedForVercel(relative) {
  if (relative === ".vercelignore" || relative === "pom.xml") return true;
  if (
    /^apps\/web-console\/(?:\.next|node_modules|test-results|playwright-report|coverage|\.turbo)(?:\/|$)/u
      .test(relative)
  ) {
    return false;
  }
  if (relative.startsWith("apps/web-console/")) return true;
  if (relative === "contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json") {
    return true;
  }
  if (relative === "routes/inventory.json") return true;
  if (
    /^routes\/[^/]+\/(?:route|support-matrix)\.json$/u.test(relative)
    || /^routes\/[^/]+\/certification\/(?:certification|evidence)\.json$/u.test(relative)
  ) {
    return true;
  }
  return new Set([
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
  ]).has(relative);
}

test("Vercel upload policy is default deny and preserves exact runtime inputs", () => {
  assert.equal(meaningfulRules[0], "*");
  for (const requiredRule of [
    "!.vercelignore",
    "!/app/**",
    "!/lib/**",
    "!/public/**",
    "!/package.json",
    "!/pnpm-lock.yaml",
    "!/next.config.ts",
    "!/vercel.json",
    "!apps/web-console/**",
    "!contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json",
    "!routes/inventory.json",
    "!routes/*/route.json",
    "!routes/*/certification/certification.json",
    "!/pom.xml",
    "!engines/polyglot-route-engine/src/elmos_polyglot_route/emitter.py",
  ]) {
    assert.ok(meaningfulRules.includes(requiredRule), `missing ${requiredRule}`);
  }
  assert.ok(!meaningfulRules.includes("!engines/**"));
  assert.ok(!meaningfulRules.includes("!routes/**"));
  for (const excluded of [
    "apps/web-console/.next/**",
    "apps/web-console/node_modules/**",
    "apps/web-console/test-results/**",
    "apps/web-console/playwright-report/**",
    "apps/web-console/coverage/**",
    "apps/web-console/.turbo/**",
    ".next/**",
    "node_modules/**",
    "test-results/**",
    "playwright-report/**",
    "coverage/**",
    ".turbo/**",
  ]) {
    assert.ok(meaningfulRules.includes(excluded), `missing ${excluded}`);
  }
});

test("intended deployment manifest is bounded and contains no special files", () => {
  const intended = listedFiles().filter(intendedForVercel).sort();
  const included = actualVercelManifest().sort();
  assert.deepEqual(
    included,
    intended,
    ".vercelignore result must equal the reviewed allowlist exactly",
  );
  const required = [
    "apps/web-console/package.json",
    "apps/web-console/pnpm-lock.yaml",
    "apps/web-console/next.config.ts",
    "apps/web-console/vercel.json",
    "apps/web-console/public/.gitkeep",
    "apps/web-console/app/capabilities/page.tsx",
    "apps/web-console/app/api/capabilities/generation/route.ts",
    "apps/web-console/app/api/health/route.ts",
    "apps/web-console/app/lib/server/fallbacks/inventory.json",
    "contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json",
    "routes/inventory.json",
    "pom.xml",
  ];
  for (const relative of required) {
    assert.ok(included.includes(relative), `missing runtime input ${relative}`);
  }
  assert.ok(included.length > 100, "manifest unexpectedly empty");
  assert.ok(included.length < 2_000, `manifest too large: ${included.length}`);

  let totalBytes = 0;
  for (const relative of included) {
    const absolute = path.join(repositoryRoot, relative);
    const details = lstatSync(absolute);
    assert.ok(details.isFile(), `non-regular deployment input: ${relative}`);
    assert.ok(!details.isSymbolicLink(), `symlink deployment input: ${relative}`);
    totalBytes += details.size;
  }
  assert.ok(totalBytes < 64 * 1024 * 1024, `manifest exceeds 64 MiB: ${totalBytes}`);
});

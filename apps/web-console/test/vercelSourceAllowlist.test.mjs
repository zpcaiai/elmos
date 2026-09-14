import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, lstatSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const repositoryRoot = execFileSync(
  "git",
  ["rev-parse", "--show-toplevel"],
  { encoding: "utf8" },
).trim();
const projectRoot = path.join(repositoryRoot, "apps", "web-console");

function nulGitFiles(args, cwd = repositoryRoot) {
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
  ])
    .filter((relative) => relative.startsWith(prefix))
    .map((relative) => relative.slice(prefix.length))
    .filter((relative) => existsSync(path.join(projectRoot, relative)));
}

function assertExactRegularFile(relative) {
  const absolute = path.join(repositoryRoot, relative);
  const details = lstatSync(absolute);
  assert.ok(details.isFile(), `not a regular runtime binding: ${relative}`);
  assert.ok(!details.isSymbolicLink(), `symlink runtime binding: ${relative}`);
}

test("Vercel Git source tracing is not replaced by a default-deny ignore file", () => {
  // With sourceFilesOutsideRootDirectory enabled, Vercel must trace imports from
  // the configured monorepo project root. A repository or project-root
  // default-deny .vercelignore can make Git deployments fail before a build
  // exists, even when a local archive deployment succeeds.
  assert.equal(existsSync(path.join(repositoryRoot, ".vercelignore")), false);
  assert.equal(existsSync(path.join(projectRoot, ".vercelignore")), false);
});

test("tracked project inputs are bounded regular files", () => {
  const included = listedProjectFiles().sort();
  for (const relative of [
    ".npmrc",
    "package.json",
    "pnpm-lock.yaml",
    "next.config.ts",
    "vercel.json",
    "public/.gitkeep",
    "app/capabilities/page.tsx",
    "app/api/[[...path]]/route.ts",
    "app/api/capabilities/generation/_route.ts",
    "app/api/health/_route.ts",
    "app/lib/server/fallbacks/inventory.json",
  ]) {
    assert.ok(included.includes(relative), `missing project input ${relative}`);
  }
  assert.ok(included.length > 100, "project input unexpectedly empty");
  assert.ok(included.length < 1_000, `project input too large: ${included.length}`);

  let totalBytes = 0;
  for (const relative of included) {
    const absolute = path.join(projectRoot, relative);
    const details = lstatSync(absolute);
    assert.ok(details.isFile(), `non-regular project input: ${relative}`);
    assert.ok(!details.isSymbolicLink(), `symlink project input: ${relative}`);
    totalBytes += details.size;
  }
  assert.ok(totalBytes < 32 * 1024 * 1024, `project input exceeds 32 MiB: ${totalBytes}`);
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

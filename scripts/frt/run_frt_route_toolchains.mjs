#!/usr/bin/env node

import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptRoot, "../..");
const engineRoot = path.join(repositoryRoot, "engines/frontend-client-engine");
const engineModule = path.join(engineRoot, "dist/src/directional-route.js");
const defaultOutput = path.join(
  repositoryRoot,
  "client-packs/frt-g01-g30-platform/certification/route-toolchain-evidence.json",
);
const outputIndex = process.argv.indexOf("--output");
const outputPath = outputIndex >= 0
  ? path.resolve(process.argv[outputIndex + 1] ?? "")
  : defaultOutput;
const keepWorkspace = process.argv.includes("--keep-workspace");
const maximumLogBytes = 64 * 1024;

function sha256(value) {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function boundedLog(value) {
  const buffer = Buffer.from(value ?? "", "utf8");
  return buffer.length <= maximumLogBytes
    ? buffer.toString("utf8")
    : `${buffer.subarray(0, maximumLogBytes).toString("utf8")}\n<TRUNCATED>`;
}

function run(command, args, options = {}) {
  const startedAt = new Date().toISOString();
  const started = process.hrtime.bigint();
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? repositoryRoot,
    encoding: "utf8",
    env: {
      ...process.env,
      NO_PROXY: "127.0.0.1,localhost",
      no_proxy: "127.0.0.1,localhost",
      ...options.env,
    },
    timeout: options.timeoutMs ?? 120_000,
    maxBuffer: 8 * 1024 * 1024,
    ...(options.input === undefined ? {} : { input: options.input }),
  });
  const durationMs = Number(process.hrtime.bigint() - started) / 1_000_000;
  const stdout = boundedLog(result.stdout);
  const stderr = boundedLog(result.stderr);
  return {
    command: [command, ...args],
    cwd: options.cwd ?? repositoryRoot,
    startedAt,
    durationMs: Math.round(durationMs),
    exitCode: result.status,
    signal: result.signal,
    error: result.error?.message ?? null,
    stdout,
    stderr,
    stdoutSha256: sha256(stdout),
    stderrSha256: sha256(stderr),
    status: result.status === 0 ? "PASSED" : "FAILED",
  };
}

function materialize(root, files) {
  for (const [relativePath, content] of Object.entries(files)) {
    if (relativePath === "frt-route.json") continue;
    const destination = path.join(root, relativePath);
    mkdirSync(path.dirname(destination), { recursive: true });
    writeFileSync(destination, content, { flag: "wx" });
  }
}

function commandAvailable(command) {
  return run("/usr/bin/which", [command], { timeoutMs: 10_000 }).status === "PASSED";
}

if (!existsSync(engineModule)) {
  const build = run("pnpm", ["run", "build"], { cwd: engineRoot, timeoutMs: 180_000 });
  if (build.status !== "PASSED") {
    throw new Error(`frontend engine build failed: ${build.stderr}`);
  }
}

const { convertDirectionalRoute, createDirectionalRouteFixture, frtRouteStacks } = await import(engineModule);
const workspace = mkdtempSync(path.join(tmpdir(), "elmos-frt-route-toolchains-"));
const allRoutes = [];
const representativeByTarget = new Map();

try {
  for (const source of frtRouteStacks) {
    for (const target of frtRouteStacks) {
      if (source === target) continue;
      const result = convertDirectionalRoute(source, target, createDirectionalRouteFixture(source));
      allRoutes.push({
        route: result.route,
        status: result.status,
        sourceValidation: result.sourceValidation,
        targetValidation: result.targetValidation,
        sourceSnapshotDigest: result.sourceSnapshotDigest ?? null,
        generatedFiles: Object.fromEntries(
          Object.entries(result.generatedFiles)
            .sort(([left], [right]) => left.localeCompare(right))
            .map(([name, content]) => [name, sha256(content)]),
        ),
        typedGaps: result.typedGaps,
      });
      if (result.status === "GENERATED" && !representativeByTarget.has(target)) {
        representativeByTarget.set(target, result);
      }
    }
  }

  if (allRoutes.length !== 30 || allRoutes.some((route) => route.status !== "GENERATED")) {
    throw new Error("the exact 30-route matrix did not generate successfully");
  }

  const targetEvidence = [];
  for (const target of frtRouteStacks) {
    const result = representativeByTarget.get(target);
    if (!result) throw new Error(`missing representative output for ${target}`);
    const targetRoot = path.join(workspace, target.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-"));
    mkdirSync(targetRoot, { recursive: true });
    materialize(targetRoot, result.generatedFiles);
    const generatedDigest = sha256(canonical(
      Object.entries(result.generatedFiles)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([name, content]) => ({ name, sha256: sha256(content) })),
    ));

    if (target === "React") {
      symlinkSync(path.join(engineRoot, "node_modules"), path.join(targetRoot, "node_modules"), "dir");
      const execution = run(
        path.join(engineRoot, "node_modules/.bin/tsc"),
        ["-p", path.join(targetRoot, "tsconfig.json")],
        { cwd: targetRoot, timeoutMs: 120_000 },
      );
      targetEvidence.push({ target, sourceRoute: result.route, generatedDigest, evidenceType: "REAL_TYPESCRIPT_BUILD", execution });
      continue;
    }

    if (target === "Vue 3") {
      const validator = [
        'import { readFileSync } from "node:fs";',
        'import { parse, compileTemplate } from "@vue/compiler-sfc";',
        'const source=readFileSync(process.argv[1],"utf8");',
        'const parsed=parse(source,{filename:"App.vue"});',
        'if(parsed.errors.length||!parsed.descriptor.template)process.exit(2);',
        'const built=compileTemplate({source:parsed.descriptor.template.content,filename:"App.vue",id:"frt-real-build"});',
        'if(built.errors.length){console.error(built.errors);process.exit(3)}',
        'console.log("vue3-template-build-passed", built.code.length);',
      ].join("");
      const execution = run(process.execPath, ["--disable-proto=throw", "--input-type=module", "-e", validator, path.join(targetRoot, "src/App.vue")], {
        cwd: engineRoot,
        timeoutMs: 120_000,
      });
      targetEvidence.push({ target, sourceRoute: result.route, generatedDigest, evidenceType: "REAL_VUE3_TEMPLATE_BUILD", execution });
      continue;
    }

    if (target === "Vue 2") {
      const validator = [
        'import { readFileSync } from "node:fs";',
        'import { createRequire } from "node:module";',
        'const require=createRequire(import.meta.url);',
        'const compiler=require("vue-template-compiler");',
        'const source=readFileSync(process.argv[1],"utf8");',
        'const matched=source.match(/<template>([\\s\\S]*?)<\\/template>/);',
        'if(!matched)process.exit(2);',
        'const built=compiler.compile(matched[1],{outputSourceRange:true});',
        'if(built.errors.length){console.error(built.errors);process.exit(3)}',
        'console.log("vue2-template-build-passed", built.render.length);',
      ].join("");
      const execution = run(process.execPath, ["--disable-proto=throw", "--input-type=module", "-e", validator, path.join(targetRoot, "src/App.vue")], {
        cwd: engineRoot,
        timeoutMs: 120_000,
      });
      targetEvidence.push({ target, sourceRoute: result.route, generatedDigest, evidenceType: "REAL_VUE2_TEMPLATE_BUILD", execution });
      continue;
    }

    if (target === "Flutter") {
      if (!commandAvailable("flutter")) {
        targetEvidence.push({ target, sourceRoute: result.route, generatedDigest, evidenceType: "FLUTTER_BUILD", status: "NOT_RUN", reason: "FLUTTER_TOOLCHAIN_UNAVAILABLE" });
        continue;
      }
      // Prefer the hermetic cache, but a clean machine must be able to resolve
      // the exact SDK-owned graph instead of failing solely because its cache
      // is cold.  Both attempts are retained as evidence; online fallback is
      // never reported as an offline pass.
      const offlinePubGet = run("flutter", ["pub", "get", "--offline"], {
        cwd: targetRoot,
        timeoutMs: 240_000,
      });
      const onlinePubGet = offlinePubGet.status === "PASSED" ? null : run(
        "flutter",
        ["pub", "get"],
        { cwd: targetRoot, timeoutMs: 360_000 },
      );
      const pubGet = offlinePubGet.status === "PASSED" ? offlinePubGet : onlinePubGet;
      const resolutionMode = offlinePubGet.status === "PASSED" ? "OFFLINE_CACHE" : "ONLINE_COLD_CACHE_FALLBACK";
      const analyze = pubGet?.status === "PASSED"
        ? run("flutter", ["analyze", "--no-pub"], { cwd: targetRoot, timeoutMs: 240_000 })
        : null;
      const test = analyze?.status === "PASSED"
        ? run("flutter", ["test", "--no-pub"], { cwd: targetRoot, timeoutMs: 300_000 })
        : null;
      targetEvidence.push({
        target,
        sourceRoute: result.route,
        generatedDigest,
        evidenceType: "REAL_FLUTTER_ANALYZE_AND_WIDGET_TEST",
        status: pubGet?.status === "PASSED" && analyze?.status === "PASSED" && test?.status === "PASSED" ? "PASSED" : "FAILED",
        dependencyResolution: {
          mode: resolutionMode,
          lockfileSha256: existsSync(path.join(targetRoot, "pubspec.lock"))
            ? sha256(readFileSync(path.join(targetRoot, "pubspec.lock")))
            : null,
        },
        executions: { offlinePubGet, onlinePubGet, analyze, test },
      });
      continue;
    }

    if (target === "WeChat Mini Program") {
      const cli = "/Applications/wechatwebdevtools.app/Contents/MacOS/cli";
      if (!existsSync(cli)) {
        targetEvidence.push({ target, sourceRoute: result.route, generatedDigest, evidenceType: "WECHAT_DEVTOOLS_PROJECT_OPEN", status: "NOT_RUN", reason: "WECHAT_DEVTOOLS_UNAVAILABLE" });
        continue;
      }
      const execution = run(cli, ["open", "--project", targetRoot, "--port", "19420", "--lang", "en", "--disable-gpu"], {
        cwd: targetRoot,
        timeoutMs: 120_000,
        input: "y\n",
      });
      const close = run(cli, ["close", "--project", targetRoot, "--port", "19420"], {
        cwd: targetRoot,
        timeoutMs: 30_000,
      });
      targetEvidence.push({ target, sourceRoute: result.route, generatedDigest, evidenceType: "REAL_WECHAT_DEVTOOLS_PROJECT_OPEN", execution, close });
      continue;
    }

    const configuredHvigor = process.env.ELMOS_HVIGORW;
    const hvigorCommand = configuredHvigor && existsSync(configuredHvigor)
      ? configuredHvigor
      : commandAvailable("hvigorw") ? "hvigorw"
        : commandAvailable("hvigor") ? "hvigor" : null;
    if (hvigorCommand) {
      const execution = run(hvigorCommand, [
        "assembleHap",
        "--mode", "module",
        "-p", "product=default",
        "-p", "module=entry@default",
      ], { cwd: targetRoot, timeoutMs: 600_000 });
      targetEvidence.push({
        target,
        sourceRoute: result.route,
        generatedDigest,
        evidenceType: "REAL_ARKUI_HVIGOR_BUILD",
        status: execution.status,
        toolSource: configuredHvigor ? "ELMOS_HVIGORW" : "PATH",
        execution,
      });
      continue;
    }
    targetEvidence.push({
      target,
      sourceRoute: result.route,
      generatedDigest,
      evidenceType: "ARKUI_NATIVE_BUILD",
      status: "NOT_RUN",
      reason: "DEVECO_HVIGOR_TOOLCHAIN_UNAVAILABLE",
      remediation: "Install DevEco Studio/hvigor or set ELMOS_HVIGORW to the exact executable path, then rerun this script.",
    });
  }

  const evidence = {
    schemaVersion: "1.0",
    evidenceKind: "FRT_DIRECTIONAL_ROUTE_LOCAL_TOOLCHAIN_EXECUTION",
    generatedAt: new Date().toISOString(),
    repositoryRoot,
    workspacePolicy: keepWorkspace ? "PRESERVED" : "REMOVED_AFTER_HASHING",
    scope: "bounded-single-public-counter-route-v1",
    routeCount: allRoutes.length,
    routeStatus: allRoutes.every((route) => route.status === "GENERATED") ? "PASSED" : "FAILED",
    allRoutes,
    targetEvidence,
    boundaries: {
      externalRepresentativeRepositories: "NOT_RUN",
      independentHoldout: "NOT_RUN",
      customerAcceptance: "NOT_RUN",
      productionCertification: "NOT_CERTIFIED",
    },
  };
  mkdirSync(path.dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, `${JSON.stringify(evidence, null, 2)}\n`);
  const bytes = readFileSync(outputPath);
  process.stdout.write(`${JSON.stringify({
    outputPath,
    sha256: sha256(bytes),
    routeCount: allRoutes.length,
    targetStatuses: Object.fromEntries(targetEvidence.map((item) => [
      item.target,
      item.status ?? item.execution?.status ?? "UNKNOWN",
    ])),
    workspace: keepWorkspace ? workspace : null,
  }, null, 2)}\n`);
} finally {
  if (!keepWorkspace && existsSync(workspace)) rmSync(workspace, { recursive: true, force: true });
}

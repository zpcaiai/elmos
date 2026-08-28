/**
 * Repository-level translation: scan a source project, translate every
 * component it can, and write a target project that actually builds.
 *
 * The honest contract, which is what makes "完整能运行 / fully runnable"
 * achievable at all:
 *
 *   - Components inside certified-component-v1 are really translated, with
 *     their emitted source validated by the target framework's real
 *     compiler (and, where both sides can run, by real SSR rendering).
 *
 *   - Components outside the subset are NOT guessed at. Each one gets an
 *     explicit, loudly-failing placeholder that throws with the exact
 *     reason code the parser produced. The project still compiles and
 *     starts; touching an unconverted component fails immediately and
 *     visibly instead of silently rendering something subtly wrong.
 *
 *   - `coverage-report.json` records every file with CONVERTED or BLOCKED
 *     plus the reason, so the fraction that is real is never in doubt.
 *
 * This mirrors `engines/polyglot-route-engine`'s repository pipeline, which
 * likewise reports PARTIAL rather than rounding an incomplete run up to
 * COMPLETE.
 */
import * as fs from "fs";
import * as path from "path";
import { Framework, RouteError } from "./models";
import { translateComponent, translateFile, TranslationReport } from "./engine";
import { referencedComponents } from "./emitters/react";
import { parseComponents } from "./engine";
import { createReactProjectContext } from "./parsers/react";
import {
  HandoffAlert, HandoffCheck, HandoffSummary, PortOwnership, checkPortedEntry, findEntry,
  loadManifest, summarize,
} from "./handoff";

const SOURCE_EXTENSIONS: Record<Framework, readonly string[]> = {
  react: [".tsx", ".jsx"],
  typescript: [".tsx"],
  "react-native": [".tsx", ".jsx"],
  vue3: [".vue"],
  vue2: [".vue"],
  angular: [".component.ts"],
  svelte: [".svelte"],
  miniprogram: [".wxml"],
  arkui: [".ets"],
  flutter: [".dart"],
};

const TARGET_EXTENSION: Record<Framework, string> = {
  react: ".tsx",
  typescript: ".tsx",
  "react-native": ".tsx",
  vue3: ".vue",
  vue2: ".vue",
  angular: ".component.ts",
  svelte: ".svelte",
  miniprogram: "", // four-file bundle, handled separately
  arkui: ".ets",
  flutter: ".dart",
};

function targetComponentPath(destination: string, framework: Framework, componentName: string): string {
  const root = framework === "flutter" ? path.join(destination, "lib") : path.join(destination, "src");
  return path.join(root, "components", `${componentName}${TARGET_EXTENSION[framework]}`);
}

const IGNORED_DIRECTORIES = new Set([
  "node_modules", ".git", "dist", "build", "out", "coverage", ".next", ".nuxt",
  ".svelte-kit", "vendor", "target", "__pycache__", ".cde-scratch",
]);

export interface FileOutcome {
  sourcePath: string;
  targetPath: string;
  /** MANUALLY_PORTED means a human owns this file. The engine did not
   * produce it, did not validate it, and did not overwrite it. */
  status: "CONVERTED" | "BLOCKED" | "MANUALLY_PORTED";
  /** Stable review label. MANUALLY_PORTED remains the operational status for
   * compatibility with existing coverage consumers. */
  ownership: "ENGINE_GENERATED" | PortOwnership;
  reasonCode: string | null;
  reason: string | null;
  syntaxStatus: string | null;
  executionStatus: string | null;
  notes: string[];
  /** Only ever populated for MANUALLY_PORTED files. */
  handoffAlerts?: HandoffAlert[];
}

/** A child component a converted component renders, that this run did not
 * produce. The parent compiles; it breaks at build or render time. */
export interface UnresolvedReference {
  component: string;
  referencedBy: string[];
  reason: string;
}

export interface CoverageReport {
  schemaVersion: "1.0";
  kind: "elmos.component-dialect-repository-run";
  profile: "certified-component-v1";
  sourceFramework: Framework;
  targetFramework: Framework;
  /** COMPLETE only when every discovered component was converted BY THE
   * ENGINE. Hand-ported components carry no engine evidence, so they leave
   * this PARTIAL -- see `deliveryStatus` for the migration-level view. */
  status: "COMPLETE" | "PARTIAL" | "EMPTY";
  /**
   * The migration-level view, which is a different question from "did the
   * engine convert everything":
   *
   *   ENGINE_COMPLETE        every component converted and verified by the engine
   *   COMPLETE_WITH_HANDOFF  nothing left unhandled, but some parts are
   *                          hand-written and carry NO engine evidence
   *   INCOMPLETE             components are still blocked, or a hand port
   *                          has gone stale against its source
   */
  deliveryStatus: "ENGINE_COMPLETE" | "COMPLETE_WITH_HANDOFF" | "INCOMPLETE" | "EMPTY";
  totals: { discovered: number; converted: number; blocked: number; manuallyPorted: number };
  handoff: HandoffSummary;
  handoffChecks: HandoffCheck[];
  /** Empty on a healthy run. Non-empty means some converted component
   * renders a child this run did not produce. */
  unresolvedReferences: UnresolvedReference[];
  /** Functions found beside the components that return no JSX. They are
   * not components, so nothing was emitted for them -- and their logic is
   * therefore NOT in the generated project. Listed so that is explicit. */
  helpersNotMigrated: { sourcePath: string; name: string | null }[];
  files: FileOutcome[];
}

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) continue; // never follow symlinks out of the tree
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (IGNORED_DIRECTORIES.has(entry.name)) continue;
      walk(full, out);
    } else if (entry.isFile()) {
      out.push(full);
    }
  }
  return out;
}

export function discoverComponents(repository: string, framework: Framework): string[] {
  const extensions = SOURCE_EXTENSIONS[framework];
  return walk(repository)
    .filter((f) => extensions.some((ext) => f.endsWith(ext)))
    .filter((f) => !f.endsWith(".test.tsx") && !f.endsWith(".spec.tsx") && !f.endsWith(".d.ts"))
    .sort();
}

function componentNameFromPath(file: string): string {
  const base = path.basename(file).replace(/\.[^.]+$/, "").replace(/\.component$/, "");
  const cleaned = base.replace(/[^A-Za-z0-9]/g, " ").split(/\s+/).filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join("");
  return cleaned.length > 0 ? cleaned : "Component";
}

/**
 * A placeholder for a component that could not be translated.
 *
 * It is deliberately loud. It compiles (so the surrounding project still
 * builds and starts) but throws the moment it is rendered, carrying the
 * exact reason code. Silently rendering an empty box here would be the
 * single most dangerous thing this pipeline could do: the app would look
 * like it migrated.
 */
function blockedPlaceholder(framework: Framework, name: string, reasonCode: string, reason: string): string {
  const message = `${name} was NOT translated by ELMOS certified-component-v1 (${reasonCode}: ${reason}). It must be ported by hand.`;
  const escaped = message.replace(/"/g, '\\"');
  switch (framework) {
    case "react":
    case "typescript":
    case "react-native":
      return `// NOT TRANSLATED -- ${reasonCode}\n// ${reason}\nexport default function ${name}(): never {\n  throw new Error("${escaped}");\n}\n`;
    case "vue3":
    case "vue2":
      return `<!-- NOT TRANSLATED -- ${reasonCode}: ${reason} -->\n<script setup lang="ts">\nthrow new Error("${escaped}");\n</script>\n\n<template>\n  <div />\n</template>\n`;
    case "svelte":
      return `<!-- NOT TRANSLATED -- ${reasonCode}: ${reason} -->\n<script lang="ts">\n  throw new Error("${escaped}");\n</script>\n`;
    case "angular":
      return `// NOT TRANSLATED -- ${reasonCode}\n// ${reason}\nimport { Component } from "@angular/core";\n\n@Component({ selector: "app-${name.toLowerCase()}", template: "" })\nexport class ${name}Component {\n  constructor() { throw new Error("${escaped}"); }\n}\n`;
    case "arkui":
      return `// NOT TRANSLATED -- ${reasonCode}\n// ${reason}\n@Component\nexport struct ${name} {\n  build() {\n    Text('${escaped.replace(/'/g, "")}')\n  }\n}\n`;
    case "flutter":
      return `// NOT TRANSLATED -- ${reasonCode}\n// ${reason}\nimport 'package:flutter/material.dart';\n\nclass ${name} extends StatelessWidget {\n  const ${name}({super.key});\n\n  @override\n  Widget build(BuildContext context) {\n    throw UnimplementedError('${escaped.replace(/'/g, "")}');\n  }\n}\n`;
    case "miniprogram":
      return `// NOT TRANSLATED -- ${reasonCode}\n// ${reason}\nComponent({\n  attached() {\n    throw new Error("${escaped}");\n  },\n});\n`;
  }
}

function writeFileEnsuringDir(file: string, contents: string): void {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, contents, "utf8");
}

export interface RepositoryRunOptions {
  repository: string;
  sourceFramework: Framework;
  targetFramework: Framework;
  destination: string;
  /** Skip SSR comparison per file (much faster on large repositories). */
  skipExecution?: boolean;
}

export async function runRepository(options: RepositoryRunOptions): Promise<CoverageReport> {
  const { repository, sourceFramework, targetFramework, destination } = options;
  if (sourceFramework === targetFramework) {
    throw new RouteError("SOURCE_AND_TARGET_MUST_DIFFER");
  }
  if (!fs.existsSync(repository)) {
    throw new RouteError(`REPOSITORY_NOT_FOUND: ${repository}`);
  }

  const files = discoverComponents(repository, sourceFramework);
  const reactProject = sourceFramework === "react" || sourceFramework === "typescript" || sourceFramework === "react-native"
    ? createReactProjectContext(repository)
    : undefined;
  const outcomes: FileOutcome[] = [];
  // Loaded before anything is written. A component a human has taken over
  // must be skipped on write, not written and then restored.
  const manifest = loadManifest(destination);
  const handoffChecks: HandoffCheck[] = [];
  const extraOutcomes: { name: string; report: TranslationReport; relative: string }[] = [];
  /** child component name -> the parents that render it. */
  const references = new Map<string, string[]>();
  const helpersNotMigrated: { sourcePath: string; name: string | null }[] = [];

  for (const file of files) {
    const relative = path.relative(repository, file);
    const name = componentNameFromPath(file);
    // A WeChat component is not one file: discovery finds the `.wxml`, and
    // the `Component({...})` definition it needs lives in the sibling
    // `.js`. Reading only the template would hand the parser a bundle with
    // no script and fail every mini program source repository.
    let source: string | { wxml: string; js: string };
    if (sourceFramework === "miniprogram") {
      const jsFile = file.replace(/\.wxml$/, ".js");
      if (!fs.existsSync(jsFile)) {
        outcomes.push({
          sourcePath: relative,
          targetPath: "",
          status: "BLOCKED",
          ownership: "ENGINE_GENERATED",
          reasonCode: "CERTIFIED_COMPONENT_MISSING_SCRIPT",
          reason: `no sibling ${path.basename(jsFile)} was found next to ${path.basename(file)}`,
          syntaxStatus: null, executionStatus: null, notes: [],
        });
        continue;
      }
      source = { wxml: fs.readFileSync(file, "utf8"), js: fs.readFileSync(jsFile, "utf8") };
    } else {
      source = fs.readFileSync(file, "utf8");
    }

    // A file can declare several components; each is translated and
    // reported independently so one blocked component does not blank out
    // the ones beside it.
    const outcomesForFile = await translateFile(source, sourceFramework, targetFramework, {
      fileName: path.basename(file),
      skipExecution: options.skipExecution,
      reactOptions: reactProject === undefined ? {} : {
        project: reactProject,
        sourceFile: reactProject.program.getSourceFile(path.resolve(file)),
      },
    });
    // A function that returns no JSX is a helper, not a component. Writing
    // a throwing placeholder for it would be wrong -- there is nothing to
    // render -- and counting it BLOCKED would understate coverage. It is
    // recorded so the fact that its logic was not migrated stays visible.
    for (const helper of outcomesForFile.filter((o) => o.report.reasonCode === "CERTIFIED_COMPONENT_NOT_A_COMPONENT")) {
      helpersNotMigrated.push({ sourcePath: relative, name: helper.name });
    }
    const migratable = outcomesForFile.filter((o) => o.report.reasonCode !== "CERTIFIED_COMPONENT_NOT_A_COMPONENT");
    const primary = migratable[0];
    if (primary === undefined) continue;
    const report: TranslationReport = primary.report;
    // Name the output after the COMPONENT, not the file. For the common
    // one-component-per-file case these agree; when they do not, the file
    // name is the wrong answer -- a child referencing `<Badge />` must find
    // `Badge`, whatever the file it was declared in was called.
    const primaryName = primary.name ?? name;
    // Extra components in the same file are written alongside the first
    // under their own declared names.
    for (const extra of migratable.slice(1)) {
      if (extra.name === null) continue;
      extraOutcomes.push({ name: extra.name, report: extra.report, relative });
    }

    // Record which children this file's components reference, so the run
    // can tell the customer whether those children actually resolved.
    try {
      for (const parsed of parseComponents(source, sourceFramework, path.basename(file), reactProject === undefined ? {} : {
        project: reactProject,
        sourceFile: reactProject.program.getSourceFile(path.resolve(file)),
      })) {
        for (const child of referencedComponents(parsed)) {
          const bucket = references.get(child) ?? [];
          bucket.push(parsed.name);
          references.set(child, bucket);
        }
      }
    } catch {
      // Already reported as BLOCKED above; reference data is a bonus.
    }

    const ported = findEntry(manifest, relative);
    const isPorted = ported?.state === "MANUALLY_PORTED";

    if (targetFramework === "miniprogram") {
      const dir = path.join(destination, "components", primaryName);
      if (isPorted && ported) {
        const check = checkPortedEntry(ported, {
          repository, destination, targetPath: path.relative(destination, dir),
          engineCouldConvertNow: report.status === "PASSED",
        });
        handoffChecks.push(check);
        outcomes.push({
          sourcePath: relative, targetPath: path.relative(destination, dir), status: "MANUALLY_PORTED",
          ownership: "HAND_PORTED",
          reasonCode: report.reasonCode, reason: report.reason,
          syntaxStatus: null, executionStatus: null,
          notes: check.detail, handoffAlerts: check.alerts,
        });
        continue;
      }
      if (report.status === "PASSED" && report.emittedFiles) {
        for (const [ext, contents] of Object.entries(report.emittedFiles)) {
          writeFileEnsuringDir(path.join(dir, `index.${ext}`), contents);
        }
        outcomes.push({
          sourcePath: relative, targetPath: path.relative(destination, dir), status: "CONVERTED",
          ownership: "ENGINE_GENERATED",
          reasonCode: null, reason: null,
          syntaxStatus: report.validation?.syntaxStatus ?? null,
          executionStatus: report.validation?.executionStatus ?? null,
          notes: report.notes,
        });
      } else {
        writeFileEnsuringDir(path.join(dir, "index.js"), blockedPlaceholder("miniprogram", primaryName, report.reasonCode ?? "UNKNOWN", report.reason ?? ""));
        writeFileEnsuringDir(path.join(dir, "index.wxml"), `<!-- NOT TRANSLATED -->\n<view />\n`);
        writeFileEnsuringDir(path.join(dir, "index.json"), `{ "component": true, "usingComponents": {} }\n`);
        outcomes.push({
          sourcePath: relative, targetPath: path.relative(destination, dir), status: "BLOCKED",
          ownership: "ENGINE_GENERATED",
          reasonCode: report.reasonCode, reason: report.reason,
          syntaxStatus: report.validation?.syntaxStatus ?? null,
          executionStatus: report.validation?.executionStatus ?? null,
          notes: report.notes,
        });
      }
      continue;
    }

    const targetFile = targetComponentPath(destination, targetFramework, primaryName);
    if (isPorted && ported) {
      // The whole point: this file is NOT written. A week of hand work
      // must survive someone re-running the pipeline.
      const check = checkPortedEntry(ported, {
        repository, destination, targetPath: path.relative(destination, targetFile),
        engineCouldConvertNow: report.status === "PASSED",
      });
      handoffChecks.push(check);
      outcomes.push({
        sourcePath: relative, targetPath: path.relative(destination, targetFile), status: "MANUALLY_PORTED",
        ownership: "HAND_PORTED",
        reasonCode: report.reasonCode, reason: report.reason,
        syntaxStatus: null, executionStatus: null,
        notes: check.detail, handoffAlerts: check.alerts,
      });
      continue;
    }
    if (report.status === "PASSED" && report.emitted !== null) {
      writeFileEnsuringDir(targetFile, report.emitted);
      outcomes.push({
        sourcePath: relative, targetPath: path.relative(destination, targetFile), status: "CONVERTED",
        ownership: "ENGINE_GENERATED",
        reasonCode: null, reason: null,
        syntaxStatus: report.validation?.syntaxStatus ?? null,
        executionStatus: report.validation?.executionStatus ?? null,
        notes: report.notes,
      });
    } else {
      writeFileEnsuringDir(targetFile, blockedPlaceholder(targetFramework, primaryName, report.reasonCode ?? "UNKNOWN", report.reason ?? ""));
      outcomes.push({
        sourcePath: relative, targetPath: path.relative(destination, targetFile), status: "BLOCKED",
        ownership: "ENGINE_GENERATED",
        reasonCode: report.reasonCode, reason: report.reason,
        syntaxStatus: report.validation?.syntaxStatus ?? null,
        executionStatus: report.validation?.executionStatus ?? null,
        notes: report.notes,
      });
    }
  }

  // Additional components declared in the same source file.
  for (const extra of extraOutcomes) {
    if (targetFramework === "miniprogram") {
      const dir = path.join(destination, "components", extra.name);
      if (extra.report.status === "PASSED" && extra.report.emittedFiles) {
        for (const [ext, contents] of Object.entries(extra.report.emittedFiles)) {
          writeFileEnsuringDir(path.join(dir, `index.${ext}`), contents);
        }
      } else {
        writeFileEnsuringDir(path.join(dir, "index.js"), blockedPlaceholder("miniprogram", extra.name, extra.report.reasonCode ?? "UNKNOWN", extra.report.reason ?? ""));
        writeFileEnsuringDir(path.join(dir, "index.wxml"), `<!-- NOT TRANSLATED -->\n<view />\n`);
        writeFileEnsuringDir(path.join(dir, "index.json"), `{ "component": true, "usingComponents": {} }\n`);
      }
      outcomes.push({
        sourcePath: extra.relative, targetPath: path.relative(destination, dir),
        ownership: "ENGINE_GENERATED",
        status: extra.report.status === "PASSED" ? "CONVERTED" : "BLOCKED",
        reasonCode: extra.report.reasonCode, reason: extra.report.reason,
        syntaxStatus: extra.report.validation?.syntaxStatus ?? null,
        executionStatus: extra.report.validation?.executionStatus ?? null,
        notes: extra.report.notes,
      });
      continue;
    }
    const extraFile = targetComponentPath(destination, targetFramework, extra.name);
    writeFileEnsuringDir(extraFile, extra.report.status === "PASSED" && extra.report.emitted !== null
      ? extra.report.emitted
      : blockedPlaceholder(targetFramework, extra.name, extra.report.reasonCode ?? "UNKNOWN", extra.report.reason ?? ""));
    outcomes.push({
      sourcePath: extra.relative, targetPath: path.relative(destination, extraFile),
      ownership: "ENGINE_GENERATED",
      status: extra.report.status === "PASSED" ? "CONVERTED" : "BLOCKED",
      reasonCode: extra.report.reasonCode, reason: extra.report.reason,
      syntaxStatus: extra.report.validation?.syntaxStatus ?? null,
      executionStatus: extra.report.validation?.executionStatus ?? null,
      notes: extra.report.notes,
    });
  }

  // Cross-check component references. A single-component translation cannot
  // know whether `<Child />` resolves; a repository run can, and a dangling
  // or blocked child is exactly the case where the emitted parent compiles
  // and then fails at build or render time.
  const producedNames = new Set(outcomes
    .filter((o) => o.status !== "BLOCKED")
    .map((o) => path.basename(o.targetPath).replace(/\..*$/, "")));
  const blockedNames = new Set(outcomes
    .filter((o) => o.status === "BLOCKED")
    .map((o) => path.basename(o.targetPath).replace(/\..*$/, "")));
  const unresolvedReferences: UnresolvedReference[] = [];
  for (const [child, parents] of [...references.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    if (producedNames.has(child)) continue;
    unresolvedReferences.push({
      component: child,
      referencedBy: [...new Set(parents)].sort(),
      reason: blockedNames.has(child)
        ? `${child} is rendered by ${[...new Set(parents)].sort().join(", ")} but was itself BLOCKED, so the parent renders a placeholder that throws.`
        : `${child} is rendered by ${[...new Set(parents)].sort().join(", ")} but no component of that name was produced in this run; the emitted import will not resolve.`,
    });
  }

  writeProjectScaffold(destination, targetFramework, outcomes);

  const converted = outcomes.filter((o) => o.status === "CONVERTED").length;
  const manuallyPorted = outcomes.filter((o) => o.status === "MANUALLY_PORTED").length;
  const blockedCount = outcomes.length - converted - manuallyPorted;
  const handoff = summarize(manifest, handoffChecks);
  // A stale hand port is an open item even though the file exists, so it
  // keeps delivery INCOMPLETE rather than being quietly tolerated.
  const deliveryStatus: CoverageReport["deliveryStatus"] =
    outcomes.length === 0 ? "EMPTY"
    : blockedCount > 0 || handoff.stale > 0 || unresolvedReferences.length > 0 ? "INCOMPLETE"
    : manuallyPorted > 0 ? "COMPLETE_WITH_HANDOFF"
    : "ENGINE_COMPLETE";

  const coverage: CoverageReport = {
    schemaVersion: "1.0",
    kind: "elmos.component-dialect-repository-run",
    profile: "certified-component-v1",
    sourceFramework,
    targetFramework,
    // Unchanged meaning: engine-converted only. Hand work never makes an
    // engine run look complete.
    status: outcomes.length === 0 ? "EMPTY" : blockedCount === 0 && manuallyPorted === 0 ? "COMPLETE" : "PARTIAL",
    deliveryStatus,
    totals: { discovered: outcomes.length, converted, blocked: blockedCount, manuallyPorted },
    handoff,
    handoffChecks,
    unresolvedReferences,
    helpersNotMigrated,
    files: outcomes,
  };
  writeFileEnsuringDir(path.join(destination, "coverage-report.json"), JSON.stringify(coverage, null, 2) + "\n");
  return coverage;
}

/**
 * Writes the real build manifests the target project needs to actually
 * build and start. Without these the emitted components are just loose
 * files -- "runnable" would be a claim rather than a fact.
 */
function writeProjectScaffold(destination: string, framework: Framework, outcomes: FileOutcome[]): void {
  const componentNames = outcomes.map((o) => path.basename(o.targetPath).replace(/\..*$/, ""));

  if (framework === "react" || framework === "typescript") {
    writeFileEnsuringDir(path.join(destination, "package.json"), JSON.stringify({
      name: "elmos-translated-app", private: true, version: "0.1.0", type: "module",
      scripts: { dev: "vite", build: "tsc -b && vite build", preview: "vite preview" },
      dependencies: { react: "^18.3.1", "react-dom": "^18.3.1" },
      devDependencies: { "@types/react": "^18.3.18", "@types/react-dom": "^18.3.5", "@vitejs/plugin-react": "^4.3.4", typescript: "^5.9.2", vite: "^6.0.7" },
    }, null, 2) + "\n");
    writeFileEnsuringDir(path.join(destination, "tsconfig.json"), JSON.stringify({
      compilerOptions: { target: "ES2022", lib: ["ES2022", "DOM"], module: "ESNext", moduleResolution: "bundler", jsx: "react-jsx", strict: true, noEmit: true, skipLibCheck: true },
      include: ["src"],
    }, null, 2) + "\n");
    writeFileEnsuringDir(path.join(destination, "vite.config.ts"), `import { defineConfig } from "vite";\nimport react from "@vitejs/plugin-react";\n\nexport default defineConfig({ plugins: [react()] });\n`);
    writeFileEnsuringDir(path.join(destination, "index.html"), `<!doctype html>\n<html>\n  <head><meta charset="utf-8" /><title>ELMOS translated app</title></head>\n  <body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body>\n</html>\n`);
    const imports = componentNames.map((n) => `import ${n} from "./components/${n}";`).join("\n");
    writeFileEnsuringDir(path.join(destination, "src", "main.tsx"),
      `import { StrictMode } from "react";\nimport { createRoot } from "react-dom/client";\n${imports}\n\nexport const components = { ${componentNames.join(", ")} };\n\ncreateRoot(document.getElementById("root")!).render(\n  <StrictMode>\n    <div>ELMOS translated components: ${componentNames.join(", ")}</div>\n  </StrictMode>,\n);\n`);
    return;
  }

  if (framework === "vue3") {
    writeFileEnsuringDir(path.join(destination, "package.json"), JSON.stringify({
      name: "elmos-translated-app", private: true, version: "0.1.0", type: "module",
      scripts: { dev: "vite", build: "vue-tsc -b && vite build", preview: "vite preview" },
      dependencies: { vue: "^3.5.42" },
      devDependencies: { "@vitejs/plugin-vue": "^5.2.1", typescript: "^5.9.2", vite: "^6.0.7", "vue-tsc": "^2.2.0" },
    }, null, 2) + "\n");
    writeFileEnsuringDir(path.join(destination, "tsconfig.json"), JSON.stringify({
      compilerOptions: { target: "ES2022", lib: ["ES2022", "DOM"], module: "ESNext", moduleResolution: "bundler", strict: true, noEmit: true, skipLibCheck: true, jsx: "preserve" },
      include: ["src/**/*.ts", "src/**/*.vue"],
    }, null, 2) + "\n");
    writeFileEnsuringDir(path.join(destination, "vite.config.ts"), `import { defineConfig } from "vite";\nimport vue from "@vitejs/plugin-vue";\n\nexport default defineConfig({ plugins: [vue()] });\n`);
    writeFileEnsuringDir(path.join(destination, "index.html"), `<!doctype html>\n<html>\n  <head><meta charset="utf-8" /><title>ELMOS translated app</title></head>\n  <body><div id="app"></div><script type="module" src="/src/main.ts"></script></body>\n</html>\n`);
    const imports = componentNames.map((n) => `import ${n} from "./components/${n}.vue";`).join("\n");
    writeFileEnsuringDir(path.join(destination, "src", "main.ts"),
      `import { createApp, h } from "vue";\n${imports}\n\nexport const components = { ${componentNames.join(", ")} };\n\ncreateApp({ render: () => h("div", "ELMOS translated components: ${componentNames.join(", ")}") }).mount("#app");\n`);
    return;
  }

  if (framework === "miniprogram") {
    writeFileEnsuringDir(path.join(destination, "app.json"), JSON.stringify({
      pages: ["pages/index/index"],
      window: { navigationBarTitleText: "ELMOS translated app" },
    }, null, 2) + "\n");
    writeFileEnsuringDir(path.join(destination, "app.js"), `App({});\n`);
    writeFileEnsuringDir(path.join(destination, "app.wxss"), `page { font-size: 28rpx; }\n`);
    const using = Object.fromEntries(componentNames.map((n) => [n.toLowerCase(), `/components/${n}/index`]));
    writeFileEnsuringDir(path.join(destination, "pages", "index", "index.json"), JSON.stringify({ usingComponents: using }, null, 2) + "\n");
    writeFileEnsuringDir(path.join(destination, "pages", "index", "index.js"), `Page({});\n`);
    writeFileEnsuringDir(path.join(destination, "pages", "index", "index.wxml"), `<view>ELMOS translated components</view>\n`);
    writeFileEnsuringDir(path.join(destination, "project.config.json"), JSON.stringify({
      appid: "REPLACE_WITH_YOUR_APPID", projectname: "elmos-translated-app",
      setting: { es6: true, minified: false },
    }, null, 2) + "\n");
    return;
  }

  if (framework === "react-native") {
    writeFileEnsuringDir(path.join(destination, "package.json"), JSON.stringify({
      name: "elmos-translated-app", private: true, version: "0.1.0",
      scripts: { start: "expo start", android: "expo start --android", ios: "expo start --ios" },
      dependencies: { expo: "~52.0.0", react: "18.3.1", "react-native": "0.76.5" },
      devDependencies: { "@types/react": "~18.3.12", typescript: "^5.9.2" },
    }, null, 2) + "\n");
    writeFileEnsuringDir(path.join(destination, "tsconfig.json"), JSON.stringify({
      compilerOptions: { target: "ES2022", lib: ["ES2022"], jsx: "react", strict: true, noEmit: true, skipLibCheck: true },
      include: ["src"],
    }, null, 2) + "\n");
    writeFileEnsuringDir(path.join(destination, "app.json"), JSON.stringify({ expo: { name: "elmos-translated-app", slug: "elmos-translated-app" } }, null, 2) + "\n");
    return;
  }

  if (framework === "flutter") {
    writeFileEnsuringDir(path.join(destination, "pubspec.yaml"),
      `name: elmos_translated_app\ndescription: Components translated by ELMOS certified-component-v1.\npublish_to: 'none'\nversion: 0.1.0\n\nenvironment:\n  sdk: '>=3.4.0 <4.0.0'\n\ndependencies:\n  flutter:\n    sdk: flutter\n\nflutter:\n  uses-material-design: true\n`);
    writeFileEnsuringDir(path.join(destination, "lib", "main.dart"),
      `import 'package:flutter/material.dart';\n\nvoid main() {\n  runApp(const MaterialApp(home: Scaffold(body: SizedBox.expand())));\n}\n`);
    return;
  }

  if (framework === "arkui") {
    writeFileEnsuringDir(path.join(destination, "oh-package.json5"),
      `{\n  "name": "elmos_translated_app",\n  "version": "0.1.0",\n  "description": "Components translated by ELMOS certified-component-v1."\n}\n`);
    return;
  }
}

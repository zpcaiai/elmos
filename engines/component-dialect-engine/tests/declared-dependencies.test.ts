/**
 * Guards against the one bug class that unit tests structurally cannot see:
 * a module that is installed in the *development* tree but never declared
 * in `package.json`.
 *
 * Every framework toolchain here is loaded with a runtime `require(...)`
 * rather than a static import, because several are ESM-only
 * and driven in a subprocess. TypeScript therefore cannot verify them, and
 * a locally-installed-but-undeclared package makes the whole suite pass on
 * the author's machine and fail on a fresh clone with
 * `Cannot find module ...` — which is exactly what happened.
 *
 * Only genuine `require(...)` calls are scanned. Import specifiers that
 * appear inside template literals are deliberately NOT treated as this
 * package's dependencies, because the emitters and the project scaffold
 * write import statements into the *generated* project (`vite`,
 * `@vitejs/plugin-react`, `@angular/core`, `react-native`, ...). Those are
 * dependencies of the output, not of this engine. The handful of
 * specifiers this engine really does load inside a subprocess script are
 * listed explicitly below so they stay covered.
 */
import { execFileSync } from "child_process";
import * as fs from "fs";
import * as path from "path";

const ENGINE_ROOT = path.join(__dirname, "..");
const SOURCE_ROOT = path.join(ENGINE_ROOT, "src");

/**
 * Specifiers this engine loads from a short-lived Node subprocess rather
 * than in-process, because the packages are ESM-only. They resolve from
 * this package's node_modules and so must be declared, but they appear in
 * the sources only inside an embedded script literal.
 */
const SUBPROCESS_SPECIFIERS = ["svelte/server", "@angular/compiler"] as const;

const NODE_BUILTINS = new Set([
  "fs", "path", "os", "child_process", "url", "util", "crypto", "assert",
  "events", "stream", "buffer", "process", "module", "worker_threads",
]);

interface PackageJson {
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
}

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) sourceFiles(full, out);
    else if (entry.name.endsWith(".ts")) out.push(full);
  }
  return out;
}

/** Resolve a package name from a runtime module specifier. */
function packageNameOf(specifier: string): string {
  const parts = specifier.split("/");
  return specifier.startsWith("@") ? parts.slice(0, 2).join("/") : (parts[0] as string);
}

function requiredSpecifiers(): Map<string, string[]> {
  const found = new Map<string, string[]>();
  for (const file of sourceFiles(SOURCE_ROOT)) {
    const source = fs.readFileSync(file, "utf8");
    for (const match of source.matchAll(/\brequire\(\s*["']([^"']+)["']\s*\)/g)) {
      const specifier = match[1];
      if (specifier === undefined) continue;
      if (specifier.startsWith(".") || specifier.startsWith("/")) continue;
      if (specifier.startsWith("node:")) continue;
      if (!specifier.includes("/") && NODE_BUILTINS.has(specifier)) continue;
      const relative = path.relative(ENGINE_ROOT, file);
      found.set(specifier, [...(found.get(specifier) ?? []), relative]);
    }
  }
  for (const specifier of SUBPROCESS_SPECIFIERS) {
    found.set(specifier, [...(found.get(specifier) ?? []), "(subprocess script)"]);
  }
  return found;
}

describe("every runtime dependency is declared", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(ENGINE_ROOT, "package.json"), "utf8")) as PackageJson;
  const declared = new Set([
    ...Object.keys(pkg.dependencies ?? {}),
    ...Object.keys(pkg.devDependencies ?? {}),
  ]);
  const specifiers = requiredSpecifiers();

  it("finds the framework toolchains it is supposed to be checking", () => {
    // A regression in the extractor itself would make the checks below
    // vacuously pass, so assert it really sees the runtime-loaded compilers.
    const packages = new Set([...specifiers.keys()].map(packageNameOf));
    for (const expected of [
      "@vue/compiler-sfc",
      "svelte", "@wxml/parser", "@angular/compiler", "react", "react-dom", "vue",
    ]) {
      expect(packages).toContain(expected);
    }
  });

  it("declares every package the sources load at runtime", () => {
    const missing: string[] = [];
    for (const [specifier, files] of specifiers) {
      const name = packageNameOf(specifier);
      if (!declared.has(name)) missing.push(`${name} (via ${JSON.stringify(specifier)} in ${files.join(", ")})`);
    }
    expect(missing).toEqual([]);
  });

  it("does not reintroduce the retired Vue 2 runtime toolchain", () => {
    expect(declared.has("vue-template-compiler")).toBe(false);
    expect(declared.has("vue-server-renderer")).toBe(false);
    expect(declared.has("vue2")).toBe(false);
  });

  it("resolves every in-process specifier", () => {
    const unresolvable: string[] = [];
    for (const specifier of specifiers.keys()) {
      if ((SUBPROCESS_SPECIFIERS as readonly string[]).includes(specifier)) continue;
      try {
        require.resolve(specifier);
      } catch {
        unresolvable.push(specifier);
      }
    }
    expect(unresolvable).toEqual([]);
  });

  it("resolves the ESM-only specifiers under native ESM, where they are actually used", () => {
    // These cannot be `require`d from this CommonJS runner at all, which is
    // precisely why they run in a subprocess. Checking them the same way
    // the engine loads them keeps the guarantee real.
    for (const specifier of SUBPROCESS_SPECIFIERS) {
      const script = `import(${JSON.stringify(specifier)}).then(() => process.exit(0), (e) => { console.error(e.message); process.exit(1); });`;
      expect(() =>
        execFileSync(process.execPath, ["--input-type=module", "-e", script], {
          cwd: ENGINE_ROOT, stdio: ["ignore", "pipe", "pipe"], timeout: 60_000,
        }),
      ).not.toThrow();
    }
  }, 60000);
});

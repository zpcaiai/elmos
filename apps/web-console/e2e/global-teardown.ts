import { readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

const temporaryNextTypeGlob = /^\.next-e2e-\d{4,5}\/(?:dev\/)?types\/\*\*\/\*\.ts$/;
const temporaryNextRouteImport =
  /^import "\.\/\.next-e2e-\d{4,5}\/(?:dev\/)?types\/routes\.d\.ts";$/m;

async function removeTemporaryNextTypeReferences(applicationRoot: string): Promise<void> {
  const tsconfigPath = path.join(applicationRoot, "tsconfig.json");
  const tsconfigSource = await readFile(tsconfigPath, "utf8");
  const tsconfig = JSON.parse(tsconfigSource) as {
    include?: unknown;
    [key: string]: unknown;
  };
  if (Array.isArray(tsconfig.include)) {
    const stableInclude = tsconfig.include.filter(
      (entry) => typeof entry !== "string" || !temporaryNextTypeGlob.test(entry),
    );
    if (stableInclude.length !== tsconfig.include.length) {
      tsconfig.include = stableInclude;
      await writeFile(tsconfigPath, `${JSON.stringify(tsconfig, null, 2)}\n`, "utf8");
    }
  }

  const nextEnvironmentPath = path.join(applicationRoot, "next-env.d.ts");
  const nextEnvironmentSource = await readFile(nextEnvironmentPath, "utf8");
  const stableNextEnvironment = nextEnvironmentSource.replace(
    temporaryNextRouteImport,
    'import "./.next/types/routes.d.ts";',
  );
  if (stableNextEnvironment !== nextEnvironmentSource) {
    await writeFile(nextEnvironmentPath, stableNextEnvironment, "utf8");
  }
}

export default async function globalTeardown(): Promise<void> {
  const runnerRoot = process.env.ELMOS_E2E_EFFECTIVE_RUNNER_ROOT;
  if (
    process.env.ELMOS_E2E_AUTO_RUNNER_ROOT === "true"
    && runnerRoot
    && path.dirname(path.resolve(runnerRoot)) === path.resolve(tmpdir())
    && path.basename(runnerRoot).startsWith("elmos-web-console-e2e-")
  ) {
    await rm(runnerRoot, { recursive: true, force: true });
  }

  const distDir = process.env.ELMOS_E2E_EFFECTIVE_DIST_DIR;
  const applicationRoot = path.resolve(process.cwd());
  if (
    distDir
    && path.dirname(path.resolve(distDir)) === applicationRoot
    && /^\.next-e2e-\d{4,5}$/.test(path.basename(distDir))
  ) {
    await rm(distDir, { recursive: true, force: true });
  }
  await removeTemporaryNextTypeReferences(applicationRoot);
}

import { readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

const temporaryNextTypeGlob = /^\.next-e2e-\d{4,5}\/(?:dev\/)?types\/\*\*\/\*\.ts$/;
const temporaryNextTypeImport =
  /^import "\.\/\.next-e2e-\d{4,5}\/(?:dev\/)?types\/(routes|root-params)\.d\.ts";$/gm;

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
    temporaryNextTypeImport,
    'import "./.next/types/$1.d.ts";',
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
    await rm(runnerRoot, {
      recursive: true,
      force: true,
      maxRetries: 5,
      retryDelay: 100,
    });
  }

  const applicationRoot = path.resolve(process.cwd());
  // Playwright runs globalTeardown before it terminates configured webServer
  // processes. Removing the active Next dist directory here corrupts the live
  // server and can also break a concurrent run using the same port. Dist output
  // is intentionally left as a disposable cache; a run owns its port-specific
  // directory and Next invalidates changed inputs itself.
  await removeTemporaryNextTypeReferences(applicationRoot);
}

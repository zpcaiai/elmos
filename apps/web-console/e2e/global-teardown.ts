import { rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

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
}

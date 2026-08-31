import { writeFile } from "node:fs/promises";

import { createTranslationJob } from "../app/lib/server/translationRunner.ts";

const job = await createTranslationJob(
  {
    tenantId: process.env.ELMOS_TEST_TENANT_ID,
    actor: "worker:translation-cancellation-test",
  },
  {
    workspaceId: process.env.ELMOS_TEST_WORKSPACE_ID,
    casesBundleId: process.env.ELMOS_TEST_CASES_BUNDLE_ID,
    sourceLanguage: "python",
    targetLanguage: "typescript",
  },
);

await writeFile(process.env.ELMOS_TEST_JOB_ID_FILE, `${job.id}\n`, "utf8");
const keepAlive = setInterval(() => undefined, 60_000);
await new Promise((resolve) => process.once("SIGTERM", resolve));
clearInterval(keepAlive);

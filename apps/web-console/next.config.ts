import type { NextConfig } from "next";
import { readFileSync } from "node:fs";
import path from "node:path";

const configuredDistDir = process.env.ELMOS_NEXT_DIST_DIR;
if (
  configuredDistDir
  && configuredDistDir !== ".next"
  && !/^\.next-e2e-\d{4,5}$/.test(configuredDistDir)
) {
  throw new Error("ELMOS_NEXT_DIST_DIR_INVALID");
}

const repositoryRoot = path.resolve(__dirname, "../..");
const routeInventory = JSON.parse(
  readFileSync(path.join(repositoryRoot, "routes/inventory.json"), "utf-8"),
) as unknown;
if (
  typeof routeInventory !== "object"
  || routeInventory === null
  || !("routes" in routeInventory)
  || !Array.isArray(routeInventory.routes)
  || routeInventory.routes.length !== 72
) {
  throw new Error("VERCEL_TRANSLATION_ROUTE_INVENTORY_INVALID");
}
const tracedRepositoryEvidence = routeInventory.routes.flatMap((entry: unknown) => {
  if (typeof entry !== "object" || entry === null) {
    throw new Error("VERCEL_TRANSLATION_ROUTE_ENTRY_INVALID");
  }
  const route = entry as Record<string, unknown>;
  if (route.repository_execution_status !== "PASSED") return [];
  const key = route.route_key;
  const reference = route.repository_evidence_ref;
  if (
    typeof key !== "string"
    || !/^[a-z0-9][a-z0-9-]{2,120}$/.test(key)
    || typeof reference !== "string"
    || !/^certification\/[a-z0-9][a-z0-9._/-]{1,260}\.json$/.test(reference)
    || reference.includes("..")
    || reference.includes("\\")
    || path.posix.normalize(reference) !== reference
  ) {
    throw new Error("VERCEL_TRANSLATION_ROUTE_EVIDENCE_REF_INVALID");
  }
  return [`../../routes/${key}/${reference}`];
});
const translationContractAssets = [
  "../../pom.xml",
  "../../routes/inventory.json",
  "../../routes/*/route.json",
  ...tracedRepositoryEvidence,
];

const nextConfig: NextConfig = {
  distDir: configuredDistDir ?? ".next",
  outputFileTracingRoot: repositoryRoot,
  outputFileTracingIncludes: {
    "/api/capabilities/translation": translationContractAssets,
    "/api/translation/**/*": translationContractAssets,
  },
  serverExternalPackages: ["html-to-text", "mammoth", "pdfjs-dist"],
  experimental: {
    externalDir: true,
  },
  turbopack: {
    root: repositoryRoot,
  },
};

export default nextConfig;

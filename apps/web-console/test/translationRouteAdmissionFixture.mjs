import { createHash } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import {
  lstat,
  mkdir,
  mkdtemp,
  open,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { translationLanguages } from "../app/lib/businessLines.ts";
import { parseStrictJson } from "../app/lib/server/strictJson.ts";

const routeId = "python-to-typescript";
const repositoryProfile = "test-only-repository-wide-v1";
const repositoryEvidenceRef = "certification/repository-evidence.json";
const targetEmitterPath =
  "engines/polyglot-route-engine/src/elmos_polyglot_route/emitter.py";
const directoryEnginePaths = new Set([
  "engines/dotnet-engine/src/Elmos.Dotnet.SemanticCli",
]);
const MAX_INVENTORY_BYTES = 2 * 1024 * 1024;
const MAX_ROUTE_CONTRACT_BYTES = 2 * 1024 * 1024;
const repositoryEvidence = Buffer.from(`${JSON.stringify({
  schema_version: "1.0.0",
  kind: "elmos.repository-route-execution-evidence",
  route_id: routeId,
  source_language: "python",
  target_language: "typescript",
  profile: repositoryProfile,
  status: "PASSED",
  repository_execution_status: "PASSED",
  external_verification_status: "NOT_RUN",
  certification_status: "NOT_CERTIFIED",
})}\n`);

export const TEST_ROUTE_JOB_ADMISSION = Object.freeze({
  sourceLanguage: "python",
  targetLanguage: "typescript",
  repositoryExecutionStatus: "PASSED",
  repositoryProfile,
  repositoryEvidenceRef,
  repositoryEvidenceSha256: createHash("sha256").update(repositoryEvidence).digest("hex"),
  repositoryEvidenceBytes: repositoryEvidence.byteLength,
});

function sameStableIdentity(left, right) {
  return left.dev === right.dev
    && left.ino === right.ino
    && left.size === right.size
    && left.mtimeNs === right.mtimeNs
    && left.ctimeNs === right.ctimeNs;
}

function confinedPath(root, relative) {
  if (
    typeof relative !== "string"
    || relative.length === 0
    || path.isAbsolute(relative)
    || relative.split("/").some((segment) => segment === "" || segment === "." || segment === "..")
  ) {
    throw new Error(`TEST_ROUTE_RELATIVE_PATH_INVALID:${relative}`);
  }
  const candidate = path.resolve(root, ...relative.split("/"));
  const confined = path.relative(root, candidate);
  if (
    confined === ""
    || path.isAbsolute(confined)
    || confined === ".."
    || confined.startsWith(`..${path.sep}`)
  ) {
    throw new Error(`TEST_ROUTE_PATH_ESCAPE:${relative}`);
  }
  return candidate;
}

async function readStableRegularFile(repositoryRoot, relative, maxBytes) {
  const candidate = confinedPath(repositoryRoot, relative);
  let current = repositoryRoot;
  const rootDetails = await lstat(repositoryRoot, { bigint: true });
  if (rootDetails.isSymbolicLink() || !rootDetails.isDirectory()) {
    throw new Error("TEST_ROUTE_REPOSITORY_ROOT_UNSAFE");
  }
  for (const segment of path.relative(repositoryRoot, candidate).split(path.sep).slice(0, -1)) {
    current = path.join(current, segment);
    const details = await lstat(current, { bigint: true });
    if (details.isSymbolicLink() || !details.isDirectory()) {
      throw new Error(`TEST_ROUTE_SOURCE_ANCESTOR_UNSAFE:${relative}`);
    }
  }

  const before = await lstat(candidate, { bigint: true });
  const resolved = await realpath(candidate);
  if (
    before.isSymbolicLink()
    || !before.isFile()
    || before.nlink !== 1n
    || before.size < 1n
    || before.size > BigInt(maxBytes)
    || !resolved.startsWith(`${repositoryRoot}${path.sep}`)
  ) {
    throw new Error(`TEST_ROUTE_SOURCE_FILE_UNSAFE:${relative}`);
  }

  const handle = await open(candidate, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
  try {
    const opened = await handle.stat({ bigint: true });
    if (!opened.isFile() || opened.nlink !== 1n || !sameStableIdentity(before, opened)) {
      throw new Error(`TEST_ROUTE_SOURCE_FILE_CHANGED:${relative}`);
    }
    const raw = await handle.readFile();
    const afterHandle = await handle.stat({ bigint: true });
    const afterPath = await lstat(candidate, { bigint: true });
    if (
      !sameStableIdentity(opened, afterHandle)
      || !sameStableIdentity(afterHandle, afterPath)
      || afterPath.nlink !== 1n
      || raw.byteLength !== Number(afterPath.size)
    ) {
      throw new Error(`TEST_ROUTE_SOURCE_FILE_CHANGED:${relative}`);
    }
    return raw;
  } finally {
    await handle.close();
  }
}

function validatedInventory(value) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("TEST_ROUTE_INVENTORY_INVALID");
  }
  const ids = translationLanguages.map((language) => language.id);
  const expectedRoutes = new Map(
    ids.flatMap((source) => ids
      .filter((target) => target !== source)
      .map((target) => [`${source}-to-${target}`, { source, target }])),
  );
  if (
    !Array.isArray(value.routes)
    || value.routes.length !== expectedRoutes.size
    || value.route_count !== expectedRoutes.size
    || typeof value.languages !== "object"
    || value.languages === null
    || Array.isArray(value.languages)
    || new Set(Object.keys(value.languages)).size !== ids.length
    || ids.some((id) => !Object.hasOwn(value.languages, id))
    || !Array.isArray(value.console_exposed_languages)
    || value.console_exposed_languages.length !== ids.length
    || ids.some((id) => !value.console_exposed_languages.includes(id))
  ) {
    throw new Error("TEST_ROUTE_INVENTORY_MATRIX_INVALID");
  }
  const seen = new Set();
  for (const candidate of value.routes) {
    if (typeof candidate !== "object" || candidate === null || Array.isArray(candidate)) {
      throw new Error("TEST_ROUTE_INVENTORY_ENTRY_INVALID");
    }
    const expected = expectedRoutes.get(candidate.route_key);
    if (
      !expected
      || seen.has(candidate.route_key)
      || candidate.source !== expected.source
      || candidate.target !== expected.target
    ) {
      throw new Error(`TEST_ROUTE_INVENTORY_IDENTITY_INVALID:${candidate.route_key}`);
    }
    seen.add(candidate.route_key);
  }
  if (seen.size !== expectedRoutes.size) throw new Error("TEST_ROUTE_INVENTORY_INCOMPLETE");
  return value;
}

async function copyStableContract(repositoryRoot, fixtureRoot, relative) {
  const raw = await readStableRegularFile(
    repositoryRoot,
    relative,
    MAX_ROUTE_CONTRACT_BYTES,
  );
  const destination = confinedPath(fixtureRoot, relative);
  await mkdir(path.dirname(destination), { recursive: true, mode: 0o700 });
  await writeFile(destination, raw, { mode: 0o600, flag: "wx" });
}

/**
 * Materialize a temporary route-admission authority for Runner unit and race
 * tests. This fixture never edits routes/inventory.json, never publishes an
 * evidence receipt, and never changes the production NOT_RUN/NOT_CERTIFIED
 * boundary. It admits one exact direction only so lifecycle tests can reach
 * the code they own without weakening the production route gate.
 */
export async function createTranslationRouteAdmissionFixture(repositoryRoot) {
  const canonicalRepositoryRoot = await realpath(repositoryRoot);
  const root = await realpath(
    await mkdtemp(path.join(tmpdir(), "elmos-translation-route-admission-test-")),
  );
  try {
    const inventory = validatedInventory(parseStrictJson(
      (await readStableRegularFile(
        canonicalRepositoryRoot,
        "routes/inventory.json",
        MAX_INVENTORY_BYTES,
      )).toString("utf8"),
    ));
    const route = inventory.routes.find((candidate) => candidate.route_key === routeId);
    if (!route) throw new Error("TEST_ROUTE_ADMISSION_ROUTE_MISSING");
    Object.assign(route, {
      local_execution_reason: "TEST_ONLY_ADMISSION_FIXTURE",
      local_execution_status: "PASSED_LOCAL",
      repository_execution_status: "PASSED",
      repository_profile: repositoryProfile,
      repository_evidence_ref: repositoryEvidenceRef,
      repository_evidence_sha256: TEST_ROUTE_JOB_ADMISSION.repositoryEvidenceSha256,
      repository_evidence_bytes: TEST_ROUTE_JOB_ADMISSION.repositoryEvidenceBytes,
      independent_verification_status: "NOT_RUN",
      external_certification_status: "NOT_RUN",
    });

    await writeFile(path.join(root, "pom.xml"), "<project/>\n", { mode: 0o600 });
    for (const candidate of inventory.routes) {
      const routeRoot = `routes/${candidate.route_key}`;
      await copyStableContract(canonicalRepositoryRoot, root, `${routeRoot}/route.json`);
      await copyStableContract(
        canonicalRepositoryRoot,
        root,
        `${routeRoot}/certification/certification.json`,
      );
      if (candidate.status === "research") {
        await copyStableContract(canonicalRepositoryRoot, root, `${routeRoot}/support-matrix.json`);
        await copyStableContract(
          canonicalRepositoryRoot,
          root,
          `${routeRoot}/certification/evidence.json`,
        );
      }
    }
    const evidencePath = path.join(root, "routes", routeId, repositoryEvidenceRef);
    await mkdir(path.dirname(evidencePath), { recursive: true, mode: 0o700 });
    await writeFile(evidencePath, repositoryEvidence, { mode: 0o600 });

    const enginePaths = new Set([
      ...translationLanguages.map((language) => language.enginePath),
      targetEmitterPath,
    ]);
    for (const relative of enginePaths) {
      const destination = confinedPath(root, relative);
      if (directoryEnginePaths.has(relative)) {
        await mkdir(destination, { recursive: true, mode: 0o700 });
      } else {
        await mkdir(path.dirname(destination), { recursive: true, mode: 0o700 });
        await writeFile(destination, "test-only engine path marker\n", {
          mode: 0o600,
          flag: "wx",
        });
      }
    }
    await mkdir(path.join(root, "routes"), { recursive: true, mode: 0o700 });
    await writeFile(
      path.join(root, "routes", "inventory.json"),
      `${JSON.stringify(inventory)}\n`,
      { mode: 0o600 },
    );
    return {
      root,
      admission: TEST_ROUTE_JOB_ADMISSION,
      cleanup: () => rm(root, { recursive: true, force: true }),
    };
  } catch (error) {
    await rm(root, { recursive: true, force: true });
    throw error;
  }
}

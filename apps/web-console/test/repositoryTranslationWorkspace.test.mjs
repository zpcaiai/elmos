import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  repositoryTranslationWorkspace,
} from "../app/lib/server/repositoryWorkspaceProxy.ts";

const workspaceId = "11111111-1111-4111-8111-111111111111";
const sourceCommit = "1".repeat(40);
const currentHeadCommit = "2".repeat(40);
const protectedSource = "def protected_rule(value: int) -> int:\n    return value + 1\n";
const writableSource = "def writable_rule(value: int) -> int:\n    return value * 2\n";
const sha256 = (value) => createHash("sha256").update(value).digest("hex");

function snapshot() {
  return {
    workspaceId,
    provider: "GITHUB",
    providerInstanceId: "github.com",
    nativeRepositoryId: "repository-1",
    sourceCommit,
    currentHeadCommit,
    completeness: "COMPLETE",
    files: [
      {
        path: "src/protected.py",
        bytes: Buffer.byteLength(protectedSource),
        sha256: sha256(protectedSource),
        category: "SOURCE",
        readable: true,
        writable: false,
      },
      {
        path: "src/writable.py",
        bytes: Buffer.byteLength(writableSource),
        sha256: sha256(writableSource),
        category: "SOURCE",
        readable: true,
        writable: true,
      },
      {
        path: ".env.example",
        bytes: 12,
        sha256: sha256("SECRET=none\n"),
        category: "CONFIGURATION",
        readable: false,
        writable: false,
      },
    ],
    pendingPaths: [],
    externalOperationExecuted: false,
  };
}

test("translation materialization is tenant-and-snapshot bound, includes protected source, and rehashes cache hits", async () => {
  const sandbox = await realpath(await mkdtemp(path.join(tmpdir(), "elmos-repository-translation-")));
  const sourceRoot = path.join(sandbox, "sources");
  await mkdir(sourceRoot);
  const previousBaseUrl = process.env.ELMOS_REPOSITORY_WORKSPACE_BASE_URL;
  const originalFetch = globalThis.fetch;
  let currentSnapshot = snapshot();
  process.env.ELMOS_REPOSITORY_WORKSPACE_BASE_URL = "http://127.0.0.1:18080";
  globalThis.fetch = async (input) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith(`/${workspaceId}`)) {
      return Response.json(currentSnapshot);
    }
    const requestedPath = url.searchParams.get("path");
    const entry = currentSnapshot.files.find((candidate) => candidate.path === requestedPath);
    assert.ok(entry, `unexpected file request ${requestedPath}`);
    const content = requestedPath === "src/protected.py" ? protectedSource : writableSource;
    return Response.json({
      workspaceId,
      path: requestedPath,
      sha256: entry.sha256,
      category: entry.category,
      encoding: "UTF-8",
      content,
    });
  };

  try {
    const input = {
      tenantId: "tenant-repository-a",
      actor: "user:repository-a",
      accessToken: "short-lived-workspace-token",
      workspaceId,
      sourceRoot,
    };
    const first = await repositoryTranslationWorkspace(input);
    assert.equal(first.fileCount, 2);
    assert.match(first.materializedId, /^repo-[0-9a-f]{48}$/);
    assert.equal(first.materializedId.includes(workspaceId), false);
    const materialized = path.join(sourceRoot, first.materializedId);
    assert.equal(await readFile(path.join(materialized, "src/protected.py"), "utf8"), protectedSource);
    const marker = JSON.parse(await readFile(path.join(materialized, ".elmos-repository-source.json"), "utf8"));
    assert.equal(marker.tenantId, input.tenantId);
    assert.equal(marker.includedReadableReadOnlySources, true);
    assert.equal(marker.files.length, 2);
    await assert.rejects(readFile(path.join(materialized, ".env.example")), { code: "ENOENT" });

    await writeFile(path.join(materialized, "src/protected.py"), "tampered\n");
    await assert.rejects(
      repositoryTranslationWorkspace(input),
      (error) => error?.errorCode === "REPOSITORY_TRANSLATION_MATERIALIZATION_DRIFT",
    );

    await writeFile(path.join(materialized, "src/protected.py"), protectedSource);
    await writeFile(path.join(materialized, "unexpected.py"), "extra\n");
    await assert.rejects(
      repositoryTranslationWorkspace(input),
      (error) => error?.errorCode === "REPOSITORY_TRANSLATION_MATERIALIZATION_DRIFT",
    );

    const otherTenant = await repositoryTranslationWorkspace({
      ...input,
      tenantId: "tenant-repository-b",
      actor: "user:repository-b",
    });
    assert.notEqual(otherTenant.materializedId, first.materializedId);
    assert.equal(
      await readFile(path.join(sourceRoot, otherTenant.materializedId, "src/protected.py"), "utf8"),
      protectedSource,
    );

    currentSnapshot = { ...currentSnapshot, currentHeadCommit: "3".repeat(40) };
    const newerCommit = await repositoryTranslationWorkspace(input);
    assert.notEqual(newerCommit.materializedId, first.materializedId);
    assert.equal(newerCommit.currentHeadCommit, "3".repeat(40));

    const concurrentInput = {
      ...input,
      tenantId: "tenant-repository-c",
      actor: "user:repository-c",
    };
    const [concurrentA, concurrentB] = await Promise.all([
      repositoryTranslationWorkspace(concurrentInput),
      repositoryTranslationWorkspace(concurrentInput),
    ]);
    assert.equal(concurrentA.materializedId, concurrentB.materializedId);

    currentSnapshot = {
      ...currentSnapshot,
      files: [
        ...currentSnapshot.files,
        {
          path: "secrets/policy.py",
          bytes: 9,
          sha256: sha256("value = 1"),
          category: "SOURCE",
          readable: false,
          writable: false,
        },
      ],
    };
    await assert.rejects(
      repositoryTranslationWorkspace({
        ...input,
        tenantId: "tenant-repository-d",
        actor: "user:repository-d",
      }),
      (error) => error?.errorCode === "REPOSITORY_TRANSLATION_PROTECTED_SOURCE_EXCLUDED",
    );
  } finally {
    globalThis.fetch = originalFetch;
    if (previousBaseUrl === undefined) delete process.env.ELMOS_REPOSITORY_WORKSPACE_BASE_URL;
    else process.env.ELMOS_REPOSITORY_WORKSPACE_BASE_URL = previousBaseUrl;
    await rm(sandbox, { recursive: true, force: true });
  }
});

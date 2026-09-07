import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readdirSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  ContentAddressedFrtArtifactStore,
  FrtArtifactStoreError,
} from "../src/frt-artifact-store.js";
import { collectRunnerEvidenceCandidates } from "../src/frt-evidence.js";

test("artifact lifecycle archives unreferenced objects recoverably and never moves live evidence", () => {
  const root = mkdtempSync(join(tmpdir(), "elmos-frt-artifacts-"));
  try {
    const store = new ContentAddressedFrtArtifactStore(root);
    const live = store.put("live", Buffer.from("live evidence\n"));
    const garbage = store.put("garbage", Buffer.from("old candidate\n"));
    assert.equal(store.list().length, 2);

    const report = store.archiveGarbage({
      liveDigests: [live.digest],
      minimumAgeSeconds: 0,
      retentionSeconds: 0,
      maximumActiveBytes: live.byteCount,
      now: new Date("2030-08-05T00:00:00Z"),
    });
    assert.equal(report.activeObjectsBefore, 2);
    assert.equal(report.activeObjectsAfter, 1);
    assert.deepEqual(report.archived.map(item => item.digest), [garbage.digest]);
    assert.equal(report.quotaSatisfied, true);
    assert.ok(report.recoveryRoot);
    assert.equal(existsSync(fileURLToPath(report.archived[0]!.uri)), true);
    assert.deepEqual(store.resolve(live.uri), Buffer.from("live evidence\n"));
    assert.throws(() => store.resolve(garbage.uri), (error: unknown) =>
      error instanceof FrtArtifactStoreError && error.code === "FRT_ARTIFACT_NOT_FOUND");

    const hex = garbage.digest.slice("sha256:".length);
    const recoveredPath = join(fileURLToPath(report.recoveryRoot!), hex.slice(0, 2), `${hex.slice(2)}.bin`);
    assert.equal(existsSync(recoveredPath), true);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("artifact storage rejects a symlinked objects directory before writing outside its root", () => {
  const root = mkdtempSync(join(tmpdir(), "elmos-frt-artifact-root-"));
  const outside = mkdtempSync(join(tmpdir(), "elmos-frt-artifact-outside-"));
  try {
    const store = new ContentAddressedFrtArtifactStore(root);
    symlinkSync(outside, join(root, "objects"), "dir");
    assert.throws(
      () => store.put("escape", Buffer.from("must stay inside the approved root")),
      (error: unknown) => error instanceof FrtArtifactStoreError
        && error.code === "FRT_ARTIFACT_DIRECTORY_COMPONENT_UNSAFE",
    );
    assert.deepEqual(readdirSync(outside), []);
  } finally {
    rmSync(root, { recursive: true, force: true });
    rmSync(outside, { recursive: true, force: true });
  }
});

test("artifact quota fails closed when live objects alone exceed it", () => {
  const root = mkdtempSync(join(tmpdir(), "elmos-frt-artifact-quota-"));
  try {
    const store = new ContentAddressedFrtArtifactStore(root);
    const live = store.put("live", Buffer.from("cannot archive a referenced object"));
    const report = store.archiveGarbage({ liveDigests: [live.digest], maximumActiveBytes: 1 });
    assert.equal(report.archived.length, 0);
    assert.equal(report.quotaSatisfied, false);
    assert.equal(report.activeObjectsAfter, 1);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("runner outputs are automatically collected as immutable unsigned evidence candidates", () => {
  const root = mkdtempSync(join(tmpdir(), "elmos-frt-evidence-collection-"));
  try {
    const store = new ContentAddressedFrtArtifactStore(root);
    const candidates = collectRunnerEvidenceCandidates({
      executor: "runner-independent-a",
      store,
      outputs: [
        { role: "SOURCE_BUILD", state: "PASSED", bytes: Buffer.from("source build passed\n") },
        { role: "TARGET_BUILD", state: "PASSED", bytes: Buffer.from("target build passed\n") },
      ],
    });
    assert.deepEqual(candidates.map(item => item.role), ["SOURCE_BUILD", "TARGET_BUILD"]);
    assert.ok(candidates.every(item => item.executor === "runner-independent-a"));
    assert.ok(candidates.every(item => /^sha256:[a-f0-9]{64}$/.test(item.digest)));
    assert.ok(candidates.every(item => store.resolve(item.uri).byteLength === item.byteCount));
    assert.throws(
      () => collectRunnerEvidenceCandidates({
        executor: "runner-independent-a",
        store,
        outputs: [
          { role: "SOURCE_BUILD", state: "PASSED", bytes: Buffer.from("one") },
          { role: "SOURCE_BUILD", state: "PASSED", bytes: Buffer.from("two") },
        ],
      }),
      /FRT_EVIDENCE_ROLE_DUPLICATED/,
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

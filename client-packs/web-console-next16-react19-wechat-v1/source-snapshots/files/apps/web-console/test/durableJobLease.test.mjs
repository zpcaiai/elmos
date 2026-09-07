import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import {
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { hostname, tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  DurableJobLease,
  DurableLeaseError,
  withDurableQueueControlLock,
} from "../app/lib/server/durableJobLease.ts";

function configuration(root) {
  return {
    root,
    line: "durable-lock-replay",
    globalCapacity: 2,
    tenantCapacity: 1,
    queueTtlMs: 60_000,
    leaseTtlMs: 30_000,
  };
}

function controlPath(root) {
  return path.join(root, ".durable-queue", "control", "durable-lock-replay.lock");
}

function lockDocument({ ownerToken = randomUUID(), pid = process.pid, ageMs = 0 } = {}) {
  const timestamp = new Date(Date.now() - ageMs).toISOString();
  return {
    schemaVersion: "1.0",
    line: "durable-lock-replay",
    ownerToken,
    hostname: hostname(),
    pid,
    createdAt: timestamp,
    heartbeatAt: timestamp,
  };
}

async function temporaryRoot() {
  return mkdtemp(path.join(tmpdir(), "elmos-durable-lock-test-"));
}

test("an old owner cannot delete a replacement control lock after an ABA rename", async () => {
  const root = await temporaryRoot();
  try {
    let entered;
    const operationEntered = new Promise((resolve) => {
      entered = resolve;
    });
    let unblock;
    const operationBlocked = new Promise((resolve) => {
      unblock = resolve;
    });
    const firstOwner = withDurableQueueControlLock(configuration(root), async () => {
      entered();
      await operationBlocked;
    });
    await operationEntered;

    const canonical = controlPath(root);
    const displaced = `${canonical}.forced-stale`;
    await rename(canonical, displaced);
    const replacement = lockDocument();
    await writeFile(canonical, `${JSON.stringify(replacement, null, 2)}\n`, {
      encoding: "utf8",
      mode: 0o600,
      flag: "wx",
    });

    unblock();
    await assert.rejects(firstOwner, (error) => (
      error instanceof DurableLeaseError
      && error.code === "QUEUE_CONTROL_LOCK_UNAVAILABLE"
      && error.retryable
    ));
    const retained = JSON.parse(await readFile(canonical, "utf8"));
    assert.equal(retained.ownerToken, replacement.ownerToken);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("a stale timestamp does not fence a live process on the same host", async () => {
  const root = await temporaryRoot();
  try {
    const canonical = controlPath(root);
    await mkdir(path.dirname(canonical), { recursive: true, mode: 0o700 });
    const liveOwner = lockDocument({ ageMs: 60_000 });
    await writeFile(canonical, `${JSON.stringify(liveOwner, null, 2)}\n`, {
      encoding: "utf8",
      mode: 0o600,
      flag: "wx",
    });
    const startedAt = Date.now();
    const releaseLiveOwner = new Promise((resolve, reject) => {
      setTimeout(() => {
        void (async () => {
          const retained = JSON.parse(await readFile(canonical, "utf8"));
          assert.equal(retained.ownerToken, liveOwner.ownerToken);
          await rm(canonical);
          resolve();
        })().catch(reject);
      }, 150);
    });
    let contenderEnteredAt = 0;
    await Promise.all([
      withDurableQueueControlLock(configuration(root), async () => {
        contenderEnteredAt = Date.now();
      }),
      releaseLiveOwner,
    ]);
    assert.ok(contenderEnteredAt - startedAt >= 100);
    assert.deepEqual(await readdir(path.dirname(canonical)), []);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("a dead stale owner is reclaimed and leaves no canonical or quarantine lock", async () => {
  const root = await temporaryRoot();
  try {
    const canonical = controlPath(root);
    await mkdir(path.dirname(canonical), { recursive: true, mode: 0o700 });
    await writeFile(
      canonical,
      `${JSON.stringify(lockDocument({ pid: 2_147_483_647, ageMs: 60_000 }), null, 2)}\n`,
      { encoding: "utf8", mode: 0o600, flag: "wx" },
    );
    let entered = false;
    await withDurableQueueControlLock(configuration(root), async () => {
      entered = true;
    });
    assert.equal(entered, true);
    assert.deepEqual(await readdir(path.dirname(canonical)), []);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("concurrent acquisition has one winner and replayable already-leased losers", async () => {
  const root = await temporaryRoot();
  try {
    const jobId = randomUUID();
    const inputDigest = createHash("sha256").update("durable-lock-replay").digest("hex");
    const attempts = await Promise.allSettled(Array.from({ length: 12 }, () => (
      DurableJobLease.acquire({
        configuration: configuration(root),
        tenantId: "tenant-replay",
        jobId,
        createdAt: new Date().toISOString(),
        inputDigest,
      })
    )));
    const winners = attempts.filter((attempt) => attempt.status === "fulfilled");
    const losers = attempts.filter((attempt) => attempt.status === "rejected");
    assert.equal(winners.length, 1);
    assert.equal(losers.length, 11);
    assert.ok(losers.every((attempt) => (
      attempt.reason instanceof DurableLeaseError
      && attempt.reason.code === "QUEUE_JOB_ALREADY_LEASED"
      && attempt.reason.retryable
    )));
    await winners[0].value.release("SUCCEEDED");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

import assert from "node:assert/strict";
import test from "node:test";
import { OrderedSnapshotPersistence } from "./orderedSnapshotPersistence.ts";

function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

test("a delayed RUNNING write cannot replace a later STOPPED snapshot", async () => {
  const firstWrite = deferred();
  const writes = [];
  const persistence = new OrderedSnapshotPersistence(async (_destination, snapshot) => {
    const status = snapshot.runtime.status;
    writes.push(status);
    if (status === "RUNNING") await firstWrite.promise;
  });
  const job = { runtime: { status: "RUNNING" } };

  const runningWrite = persistence.persist("job.json", job);
  job.runtime.status = "STOPPED";
  const stoppedWrite = persistence.persist("job.json", job);
  await new Promise((resolve) => setImmediate(resolve));

  assert.deepEqual(writes, ["RUNNING"]);
  firstWrite.resolve();
  await Promise.all([runningWrite, stoppedWrite]);
  assert.deepEqual(writes, ["RUNNING", "STOPPED"]);
});

test("a failed earlier write does not starve a later terminal snapshot", async () => {
  const writes = [];
  const persistence = new OrderedSnapshotPersistence(async (_destination, snapshot) => {
    const status = snapshot.runtime.status;
    writes.push(status);
    if (status === "RUNNING") throw new Error("seeded write failure");
  });

  await assert.rejects(
    persistence.persist("job.json", { runtime: { status: "RUNNING" } }),
    /seeded write failure/,
  );
  await persistence.persist("job.json", { runtime: { status: "STOPPED" } });
  assert.deepEqual(writes, ["RUNNING", "STOPPED"]);
});

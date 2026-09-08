import assert from "node:assert/strict";
import test from "node:test";
import { CoalescingFlush } from "../app/lib/server/coalescingFlush.ts";

test("10,000 log chunks coalesce and final flush persists the newest state", async () => {
  let current = 0;
  const persisted = [];
  const flush = new CoalescingFlush(async () => { persisted.push(current); });
  for (; current < 10_000; current++) flush.request();
  await flush.flush();
  assert.deepEqual(persisted, [10_000]);
});
test("updates during a slow write occupy one dirty bit and serialize writes", async () => {
  let unblock;
  let current = 1;
  let running = 0;
  const persisted = [];
  const flush = new CoalescingFlush(async () => {
    assert.equal(++running, 1);
    const snapshot = current;
    if (snapshot === 1) await new Promise((resolve) => { unblock = resolve; });
    persisted.push(snapshot);
    running--;
  });
  flush.request();
  const first = flush.flush();
  for (current = 2; current < 10_000; current++) flush.request();
  unblock();
  await first;
  await flush.flush();
  assert.deepEqual(persisted, [1, 10_000]);
});
test("failed writes remain observable at the terminal durability barrier", async () => {
  const failure = new Error("disk failure");
  const flush = new CoalescingFlush(async () => { throw failure; }, 1);
  flush.request();
  await new Promise((resolve) => setTimeout(resolve, 20));
  await assert.rejects(flush.flush(), (error) => error === failure);
});

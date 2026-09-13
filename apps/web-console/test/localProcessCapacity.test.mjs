import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import test from "node:test";
import { LocalProcessCapacity } from "../app/lib/server/localProcessCapacity.ts";

test("global and tenant limits reject before spawn and retirement is idempotent", () => {
  const capacity = new LocalProcessCapacity();
  const first = capacity.acquire("a", 2, 1);
  assert.throws(() => capacity.acquire("a", 2, 1), /CAPACITY_REACHED/);
  const second = capacity.acquire("b", 2, 1);
  assert.throws(() => capacity.acquire("c", 2, 1), /CAPACITY_REACHED/);
  first.release(); first.release();
  const third = capacity.acquire("c", 2, 1);
  assert.throws(() => capacity.acquire("d", 2, 1), /CAPACITY_REACHED/);
  third.release(); second.release();
});
test("a timed-out HTTP waiter does not retire a still-live child", async () => {
  const capacity = new LocalProcessCapacity();
  const lease = capacity.acquire("a", 1, 1);
  const child = spawn(process.execPath, ["-e", "setTimeout(() => process.exit(0), 150)"]);
  lease.track(child);
  await new Promise((resolve) => setTimeout(resolve, 20)); // HTTP wait ends here.
  assert.throws(() => capacity.acquire("a", 1, 1), /CAPACITY_REACHED/);
  await once(child, "close");
  capacity.acquire("a", 1, 1).release();
});
test("failed spawn closes and releases its reserved slot", async () => {
  const capacity = new LocalProcessCapacity();
  const lease = capacity.acquire("a", 1, 1);
  const child = spawn("/elmos-nonexistent-capacity-test-executable", []);
  child.on("error", () => undefined);
  lease.track(child);
  await new Promise((resolve) => child.once("close", resolve));
  capacity.acquire("a", 1, 1).release();
});
test("invalid and unbounded configurations fail closed", () => {
  for (const limits of [[0, 1], [129, 1], [2, 3], [NaN, 1], [2, 1.5]]) {
    assert.throws(() => new LocalProcessCapacity().acquire("a", ...limits), /CONFIGURATION_INVALID/);
  }
});

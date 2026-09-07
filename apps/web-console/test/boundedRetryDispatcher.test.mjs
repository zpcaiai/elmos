import assert from "node:assert/strict";
import test from "node:test";

import {
  BoundedRetryDispatcher,
  RetryDispatcherError,
} from "../app/lib/server/boundedRetryDispatcher.ts";

function fakeClock() {
  let now = 0;
  let sequence = 0;
  const timers = new Map();
  return {
    now: () => now,
    setTimer(callback, delayMs) {
      const token = sequence += 1;
      timers.set(token, { callback, dueAt: now + delayMs });
      return token;
    },
    clearTimer(token) {
      timers.delete(token);
    },
    timerCount: () => timers.size,
    async advance(milliseconds) {
      now += milliseconds;
      while (true) {
        const due = [...timers.entries()]
          .filter(([, timer]) => timer.dueAt <= now)
          .sort((left, right) => left[1].dueAt - right[1].dueAt)[0];
        if (!due) break;
        timers.delete(due[0]);
        due[1].callback();
        await new Promise((resolve) => setImmediate(resolve));
      }
    },
  };
}

test("deduplicates by key and keeps exactly one pending timer", async () => {
  const clock = fakeClock();
  const observed = [];
  const dispatcher = new BoundedRetryDispatcher({
    capacity: 8,
    maxConcurrent: 2,
    maxDispatchPerTurn: 4,
    now: clock.now,
    setTimer: clock.setTimer,
    clearTimer: clock.clearTimer,
  });
  for (let index = 0; index < 10_000; index += 1) {
    dispatcher.schedule("same-job", 100, () => observed.push(index));
    assert.equal(clock.timerCount(), 1);
  }
  assert.equal(dispatcher.snapshot().pending, 1);
  await clock.advance(100);
  assert.deepEqual(observed, [9_999]);
  assert.equal(dispatcher.snapshot().pending, 0);
});

test("fails closed at capacity and never exceeds callback concurrency", async () => {
  const clock = fakeClock();
  let running = 0;
  let maximumRunning = 0;
  const releases = [];
  const dispatcher = new BoundedRetryDispatcher({
    capacity: 3,
    maxConcurrent: 2,
    maxDispatchPerTurn: 3,
    now: clock.now,
    setTimer: clock.setTimer,
    clearTimer: clock.clearTimer,
  });
  for (const key of ["one", "two", "three"]) {
    dispatcher.schedule(key, 0, async () => {
      running += 1;
      maximumRunning = Math.max(maximumRunning, running);
      await new Promise((resolve) => releases.push(resolve));
      running -= 1;
    });
  }
  assert.throws(
    () => dispatcher.schedule("four", 0, () => undefined),
    (error) => error instanceof RetryDispatcherError
      && error.code === "RETRY_DISPATCHER_CAPACITY_REACHED",
  );
  await clock.advance(0);
  assert.equal(running, 2);
  assert.equal(maximumRunning, 2);
  releases.shift()();
  await new Promise((resolve) => setImmediate(resolve));
  await clock.advance(0);
  assert.equal(maximumRunning, 2);
  while (releases.length) releases.shift()();
  await new Promise((resolve) => setImmediate(resolve));
});

test("cancel and close prevent pending callbacks", async () => {
  const clock = fakeClock();
  let calls = 0;
  const dispatcher = new BoundedRetryDispatcher({
    capacity: 2,
    maxConcurrent: 1,
    maxDispatchPerTurn: 1,
    now: clock.now,
    setTimer: clock.setTimer,
    clearTimer: clock.clearTimer,
  });
  dispatcher.schedule("cancelled", 1, () => calls += 1);
  assert.equal(dispatcher.cancel("cancelled"), true);
  await clock.advance(1);
  assert.equal(calls, 0);
  dispatcher.schedule("closed", 1, () => calls += 1);
  dispatcher.close();
  await clock.advance(1);
  assert.equal(calls, 0);
  assert.throws(
    () => dispatcher.schedule("late", 0, () => undefined),
    (error) => error instanceof RetryDispatcherError
      && error.code === "RETRY_DISPATCHER_CLOSED",
  );
});

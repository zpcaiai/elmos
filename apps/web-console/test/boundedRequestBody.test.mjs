import assert from "node:assert/strict";
import test from "node:test";
import { readBoundedRequestBody } from "../app/lib/server/boundedRequestBody.ts";

const request = (stream, headers = {}, signal) => new Request("http://localhost/", {
  method: "POST", body: stream, duplex: "half", headers, signal,
});
const fails = (code) => (error) => error.message === code;

test("bounded body accepts exact UTF-8 byte boundary, not character count", async () => {
  const bytes = Buffer.from("中😀");
  const body = new ReadableStream({ start(c) { c.enqueue(bytes.subarray(0, 4)); c.enqueue(bytes.subarray(4)); c.close(); } });
  assert.equal(await readBoundedRequestBody(request(body), 7), "中😀");
});
test("unknown and understated lengths stop and cancel during reading", async () => {
  for (const headers of [{}, { "content-length": "1" }]) {
    let cancelled = false;
    const body = new ReadableStream({ pull(c) { c.enqueue(new Uint8Array(64)); }, cancel() { cancelled = true; } });
    await assert.rejects(readBoundedRequestBody(request(body, headers), 96), fails("REQUEST_TOO_LARGE"));
    assert.equal(cancelled, true);
  }
});
test("oversized declared length fails before body pull", async () => {
  const body = new ReadableStream({ pull() { throw new Error("must not read"); } }, { highWaterMark: 0 });
  await assert.rejects(readBoundedRequestBody(request(body, { "content-length": "97" }), 96), fails("REQUEST_TOO_LARGE"));
});
test("malformed UTF-8 and false content lengths fail closed", async () => {
  await assert.rejects(readBoundedRequestBody(request(new Uint8Array([255])), 96), fails("REQUEST_UTF8_INVALID"));
  await assert.rejects(readBoundedRequestBody(request("a", { "content-length": "2" }), 96), fails("CONTENT_LENGTH_MISMATCH"));
  await assert.rejects(readBoundedRequestBody(request("a", { "content-length": "-1" }), 96), fails("CONTENT_LENGTH_INVALID"));
});
test("deadline does not wait for a nonsettling cancellation hook", async () => {
  const body = new ReadableStream({ pull() {}, cancel() { return new Promise(() => {}); } });
  await assert.rejects(readBoundedRequestBody(request(body), 96, 20), fails("REQUEST_BODY_TIMEOUT"));
  assert.equal(body.locked, false);
});
test("client cancellation ends stalled body read", async () => {
  const controller = new AbortController();
  const body = new ReadableStream({ pull() {} });
  const result = readBoundedRequestBody(request(body, {}, controller.signal), 96);
  controller.abort();
  await assert.rejects(result, fails("REQUEST_ABORTED"));
  assert.equal(body.locked, false);
});
test("100,000 empty or one-byte chunks retain only the fixed byte budget", async () => {
  for (const size of [0, 1]) {
    let count = 0;
    const body = new ReadableStream({ pull(c) {
      if (count++ === 100_000) c.close();
      else c.enqueue(new Uint8Array(size).fill(97));
    } });
    assert.equal((await readBoundedRequestBody(request(body), 128 * 1024, 120_000)).length, size * 100_000);
  }
});
test("an immediately-ready empty stream still processes the abort race", async () => {
  const controller = new AbortController();
  const body = new ReadableStream({ pull(c) { c.enqueue(new Uint8Array()); } });
  const result = readBoundedRequestBody(request(body, {}, controller.signal), 96 * 1024);
  setImmediate(() => controller.abort());
  await assert.rejects(result, fails("REQUEST_ABORTED"));
});

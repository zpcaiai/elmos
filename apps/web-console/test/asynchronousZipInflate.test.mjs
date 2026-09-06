import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";
import { Unzip, zipSync } from "fflate";
import { AsynchronousZipInflate } from "../app/lib/server/asynchronousZipInflate.ts";

test("native asynchronous ZIP inflate preserves bytes across arbitrary archive chunks", async () => {
  const files = Object.fromEntries(Array.from({ length: 130 }, (_, i) => [
    `file-${i}.txt`, Buffer.from(`${i}:中:${"abc".repeat(i * 73)}`),
  ]));
  const zip = zipSync(files);
  const controller = new AsynchronousZipInflate();
  const results = new Map();
  const unzip = new Unzip((file) => {
    const digest = createHash("sha256");
    file.ondata = (error, bytes, final) => {
      assert.ifError(error);
      digest.update(bytes);
      if (final) results.set(file.name, digest.digest("hex"));
    };
    file.start();
  });
  unzip.register(controller.decoder);
  try {
    for (let offset = 0; offset < zip.length; offset += 113) {
      unzip.push(zip.subarray(offset, offset + 113), false);
      await controller.drain();
    }
    unzip.push(new Uint8Array(), true);
    await controller.drain();
    assert.equal(results.size, 130);
    for (const [name, bytes] of Object.entries(files)) {
      assert.equal(results.get(name), createHash("sha256").update(bytes).digest("hex"));
    }
  } finally { controller.close(); }
});

test("large compression ratio yields the event loop and cancellation fails closed", async () => {
  const zip = zipSync({ "large.txt": new Uint8Array(8 * 1024 * 1024) });
  const controller = new AsynchronousZipInflate();
  let observed = 0;
  let ticks = 0;
  const interval = setInterval(() => ticks++, 1);
  const unzip = new Unzip((file) => {
    file.ondata = (_error, bytes) => {
      observed += bytes.length;
      if (observed > 1024 * 1024) file.terminate();
    };
    file.start();
  });
  unzip.register(controller.decoder);
  try {
    unzip.push(zip, true);
    await assert.rejects(controller.drain(), /ZIP_ENTRY_TERMINATED/);
    assert.ok(observed < 8 * 1024 * 1024);
    assert.ok(ticks > 0, "the native inflate did not monopolize the event loop");
  } finally { clearInterval(interval); controller.close(); }
});
